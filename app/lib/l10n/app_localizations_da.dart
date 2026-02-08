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
  String get cancel => 'Annuller';

  @override
  String get ok => 'Ok';

  @override
  String get delete => 'Slet';

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
  String get copyTranscript => 'Kopier transskription';

  @override
  String get copySummary => 'Kopier opsummering';

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
  String get noInternetConnection => 'Ingen internetforbindelse';

  @override
  String get unableToDeleteConversation => 'Kan ikke slette samtale';

  @override
  String get somethingWentWrong => 'Noget gik galt! Prøv venligst igen senere.';

  @override
  String get copyErrorMessage => 'Kopier fejlbesked';

  @override
  String get errorCopied => 'Fejlbesked kopieret til udklipsholder';

  @override
  String get remaining => 'Tilbage';

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
  String get done => 'Færdig';

  @override
  String get disconnected => 'Afbrudt';

  @override
  String get searching => 'Søger...';

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
  String get noConversationsYet => 'Ingen samtaler endnu';

  @override
  String get noStarredConversations => 'Ingen stjernemarkerede samtaler';

  @override
  String get starConversationHint =>
      'For at stjernemarkere en samtale skal du åbne den og trykke på stjerneikonet i overskriften.';

  @override
  String get searchConversations => 'Søg samtaler...';

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
  String get messageCopied => '✨ Besked kopieret til udklipsholder';

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
  String get clearChat => 'Ryd chat';

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
  String get searchApps => 'Søg apps...';

  @override
  String get myApps => 'Mine apps';

  @override
  String get installedApps => 'Installerede apps';

  @override
  String get unableToFetchApps => 'Kan ikke hente apps :(\n\nTjek venligst din internetforbindelse og prøv igen.';

  @override
  String get aboutOmi => 'Om Omi';

  @override
  String get privacyPolicy => 'Privatlivspolitik';

  @override
  String get visitWebsite => 'Besøg hjemmesiden';

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
  String get customVocabulary => 'Brugerdefineret Ordforråd';

  @override
  String get identifyingOthers => 'Identificering af Andre';

  @override
  String get paymentMethods => 'Betalingsmetoder';

  @override
  String get conversationDisplay => 'Samtalevisning';

  @override
  String get dataPrivacy => 'Databeskyttelse';

  @override
  String get userId => 'Bruger-ID';

  @override
  String get notSet => 'Ikke indstillet';

  @override
  String get userIdCopied => 'Bruger-ID kopieret til udklipsholder';

  @override
  String get systemDefault => 'Systemstandard';

  @override
  String get planAndUsage => 'Plan og forbrug';

  @override
  String get offlineSync => 'Offline-synkronisering';

  @override
  String get deviceSettings => 'Enhedsindstillinger';

  @override
  String get integrations => 'Integrationer';

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
  String get signOut => 'Log Ud';

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
  String get saving => 'Gemmer...';

  @override
  String get personaConfig => 'Konfigurer din AI-persona';

  @override
  String get beta => 'Beta';

  @override
  String get transcription => 'Transskription';

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
  String get endpointUrl => 'Slutpunkt-URL';

  @override
  String get noApiKeys => 'Ingen API-nøgler endnu';

  @override
  String get createKeyToStart => 'Opret en nøgle for at komme i gang';

  @override
  String get createKey => 'Opret Nøgle';

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
  String get debugLogs => 'Fejlfindingslogs';

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
  String get shareLogs => 'Del logs';

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
  String get knowledgeGraphDeleted => 'Vidensgraf slettet';

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
  String get authorizationBearer => 'Godkendelse Bearer';

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
  String get realtimeTranscript => 'Realtidsudskrift';

  @override
  String get transcriptReceived => 'Udskrift modtaget';

  @override
  String get audioBytes => 'Lyd-bytes';

  @override
  String get audioDataReceived => 'Lyddata modtaget';

  @override
  String get intervalSeconds => 'Interval (sekunder)';

  @override
  String get daySummary => 'Dagens resumé';

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
  String get insights => 'Indsigt';

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
    return 'Min';
  }

  @override
  String get customVocabularyTitle => 'Brugerdefineret ordforråd';

  @override
  String get addWords => 'Tilføj ord';

  @override
  String get addWordsDesc => 'Navne, termer eller usædvanlige ord';

  @override
  String get vocabularyHint => 'Ordforråd';

  @override
  String get connect => 'Connect';

  @override
  String get comingSoon => 'Kommer snart';

  @override
  String get integrationsFooter => 'Forbind dine apps for at se data og målinger i chat.';

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
  String get enterYourName => 'Indtast dit navn';

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
  String get googleCalendar => 'Google Kalender';

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
  String get noUpcomingMeetings => 'Ingen kommende møder';

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
  String get searchLanguageHint => 'Søg sprog';

  @override
  String get noLanguagesFound => 'Ingen sprog fundet';

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
    return 'App-indstillinger';
  }

  @override
  String disconnectFromApp(String appName) {
    return 'Frakobl fra app';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'Frakobl fra denne app?';
  }

  @override
  String connectedToApp(String appName) {
    return 'Forbundet til app';
  }

  @override
  String get account => 'Konto';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Handlingspunkter synkroniseret til';
  }

  @override
  String get defaultSpace => 'Standardrum';

  @override
  String get selectSpaceInWorkspace => 'Vælg rum i arbejdsområde';

  @override
  String get noSpacesInWorkspace => 'Ingen rum i arbejdsområdet';

  @override
  String get defaultList => 'Standardliste';

  @override
  String get tasksAddedToList => 'Opgaver tilføjet til listen';

  @override
  String get noListsInSpace => 'Ingen lister i rummet';

  @override
  String failedToLoadRepos(String error) {
    return 'Kunne ikke indlæse repositories';
  }

  @override
  String get defaultRepoSaved => 'Standard-repository gemt';

  @override
  String get failedToSaveDefaultRepo => 'Kunne ikke gemme standard-repository';

  @override
  String get defaultRepository => 'Standard-repository';

  @override
  String get selectDefaultRepoDesc => 'Vælg standard-repository til problemer';

  @override
  String get noReposFound => 'Ingen repositories fundet';

  @override
  String get private => 'Privat';

  @override
  String updatedDate(String date) {
    return 'Opdateret dato';
  }

  @override
  String get yesterday => 'I går';

  @override
  String daysAgo(int count) {
    return '$count dage siden';
  }

  @override
  String get oneWeekAgo => 'For en uge siden';

  @override
  String weeksAgo(int count) {
    return '$count uger siden';
  }

  @override
  String get oneMonthAgo => 'For en måned siden';

  @override
  String monthsAgo(int count) {
    return '$count måneder siden';
  }

  @override
  String get issuesCreatedInRepo => 'Problemer oprettet i repository';

  @override
  String get taskIntegrations => 'Opgaveintegrationer';

  @override
  String get configureSettings => 'Konfigurer indstillinger';

  @override
  String get completeAuthBrowser => 'Fuldfør godkendelse i browser';

  @override
  String failedToStartAppAuth(String appName) {
    return 'Kunne ikke starte app-godkendelse';
  }

  @override
  String connectToAppTitle(String appName) {
    return 'Forbind til $appName';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Godkend Omi til opgaver';
  }

  @override
  String get continueButton => 'Fortsæt';

  @override
  String appIntegration(String appName) {
    return 'App-integration';
  }

  @override
  String integrationComingSoon(String appName) {
    return 'Integration kommer snart';
  }

  @override
  String get gotIt => 'Forstået';

  @override
  String get tasksExportedOneApp => 'Opgaver eksporteret til én app';

  @override
  String get completeYourUpgrade => 'Fuldfør din opgradering';

  @override
  String get importConfiguration => 'Importér konfiguration';

  @override
  String get exportConfiguration => 'Eksportér konfiguration';

  @override
  String get bringYourOwn => 'Medbring din egen';

  @override
  String get payYourSttProvider => 'Betal din STT-udbyder';

  @override
  String get freeMinutesMonth => 'Gratis minutter/måned';

  @override
  String get omiUnlimited => 'Omi Unlimited';

  @override
  String get hostRequired => 'Vært påkrævet';

  @override
  String get validPortRequired => 'Gyldig port påkrævet';

  @override
  String get validWebsocketUrlRequired => 'Gyldig WebSocket-URL påkrævet';

  @override
  String get apiUrlRequired => 'API-URL påkrævet';

  @override
  String get apiKeyRequired => 'API-nøgle påkrævet';

  @override
  String get invalidJsonConfig => 'Ugyldig JSON-konfiguration';

  @override
  String errorSaving(String error) {
    return 'Fejl ved gemning';
  }

  @override
  String get configCopiedToClipboard => 'Configuration copied to clipboard';

  @override
  String get pasteJsonConfig => 'Indsæt JSON-konfiguration';

  @override
  String get addApiKeyAfterImport => 'Tilføj API-nøgle efter import';

  @override
  String get paste => 'Indsæt';

  @override
  String get import => 'Importér';

  @override
  String get invalidProviderInConfig => 'Ugyldig udbyder i konfiguration';

  @override
  String importedConfig(String providerName) {
    return 'Importeret konfiguration';
  }

  @override
  String invalidJson(String error) {
    return 'Ugyldig JSON';
  }

  @override
  String get provider => 'Udbyder';

  @override
  String get live => 'Live';

  @override
  String get onDevice => 'På enhed';

  @override
  String get apiUrl => 'API-URL';

  @override
  String get enterSttHttpEndpoint => 'Indtast STT HTTP-slutpunkt';

  @override
  String get websocketUrl => 'WebSocket-URL';

  @override
  String get enterLiveSttWebsocket => 'Indtast live STT WebSocket';

  @override
  String get apiKey => 'API-nøgle';

  @override
  String get enterApiKey => 'Indtast API-nøgle';

  @override
  String get storedLocallyNeverShared => 'Gemt lokalt, deles aldrig';

  @override
  String get host => 'Vært';

  @override
  String get port => 'Port';

  @override
  String get advanced => 'Avanceret';

  @override
  String get configuration => 'Konfiguration';

  @override
  String get requestConfiguration => 'Anmod om konfiguration';

  @override
  String get responseSchema => 'Svarskema';

  @override
  String get modified => 'Ændret';

  @override
  String get resetRequestConfig => 'Nulstil anmodningskonfiguration';

  @override
  String get logs => 'Logfiler';

  @override
  String get logsCopied => 'Logfiler kopieret';

  @override
  String get noLogsYet => 'Ingen logfiler endnu';

  @override
  String deviceUsesCodec(String device, String reason) {
    return '$device bruger $reason. Omi vil blive brugt.';
  }

  @override
  String get omiTranscription => 'Omi-transskription';

  @override
  String get bestInClassTranscription => 'Bedste transskription i klassen';

  @override
  String get instantSpeakerLabels => 'Øjeblikkelige talermarkører';

  @override
  String get languageTranslation => 'Sprogoversættelse';

  @override
  String get optimizedForConversation => 'Optimeret til samtale';

  @override
  String get autoLanguageDetection => 'Automatisk sprogregistrering';

  @override
  String get highAccuracy => 'Høj nøjagtighed';

  @override
  String get privacyFirst => 'Privatliv først';

  @override
  String get saveChanges => 'Gem ændringer';

  @override
  String get resetToDefault => 'Nulstil til standard';

  @override
  String get viewTemplate => 'Vis skabelon';

  @override
  String get trySomethingLike => 'Prøv noget som';

  @override
  String get tryIt => 'Prøv det';

  @override
  String get creatingPlan => 'Opretter plan';

  @override
  String get developingLogic => 'Udvikler logik';

  @override
  String get designingApp => 'Designer app';

  @override
  String get generatingIconStep => 'Genererer ikon';

  @override
  String get finalTouches => 'Sidste detaljer';

  @override
  String get processing => 'Behandler';

  @override
  String get features => 'Funktioner';

  @override
  String get creatingYourApp => 'Opretter din app';

  @override
  String get generatingIcon => 'Genererer ikon';

  @override
  String get whatShouldWeMake => 'Hvad skal vi lave?';

  @override
  String get appName => 'App Name';

  @override
  String get description => 'Beskrivelse';

  @override
  String get publicLabel => 'Offentlig';

  @override
  String get privateLabel => 'Privat';

  @override
  String get free => 'Gratis';

  @override
  String get perMonth => 'pr. måned';

  @override
  String get tailoredConversationSummaries => 'Skræddersyede samtaleresuméer';

  @override
  String get customChatbotPersonality => 'Tilpasset chatbot-personlighed';

  @override
  String get makePublic => 'Gør offentlig';

  @override
  String get anyoneCanDiscover => 'Alle kan opdage';

  @override
  String get onlyYouCanUse => 'Kun du kan bruge';

  @override
  String get paidApp => 'Betalt app';

  @override
  String get usersPayToUse => 'Brugere betaler for at bruge';

  @override
  String get freeForEveryone => 'Gratis for alle';

  @override
  String get perMonthLabel => 'pr. måned';

  @override
  String get creating => 'Opretter';

  @override
  String get createApp => 'Opret app';

  @override
  String get searchingForDevices => 'Søger efter enheder';

  @override
  String devicesFoundNearby(int count) {
    return 'Enheder fundet i nærheden';
  }

  @override
  String get pairingSuccessful => 'Parring lykkedes';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Fejl ved forbindelse til Apple Watch';
  }

  @override
  String get dontShowAgain => 'Vis ikke igen';

  @override
  String get iUnderstand => 'Jeg forstår';

  @override
  String get enableBluetooth => 'Aktivér Bluetooth';

  @override
  String get bluetoothNeeded => 'Bluetooth påkrævet';

  @override
  String get contactSupport => 'Kontakt support';

  @override
  String get connectLater => 'Forbind senere';

  @override
  String get grantPermissions => 'Giv tilladelser';

  @override
  String get backgroundActivity => 'Baggrundsaktivitet';

  @override
  String get backgroundActivityDesc => 'Tillad app at køre i baggrunden';

  @override
  String get locationAccess => 'Placeringsadgang';

  @override
  String get locationAccessDesc => 'Påkrævet for enhedsforbindelse';

  @override
  String get notifications => 'Notifikationer';

  @override
  String get notificationsDesc => 'Modtag vigtige opdateringer';

  @override
  String get locationServiceDisabled => 'Placeringstjeneste deaktiveret';

  @override
  String get locationServiceDisabledDesc => 'Aktivér venligst placeringstjenester';

  @override
  String get backgroundLocationDenied => 'Baggrundsplacering nægtet';

  @override
  String get backgroundLocationDeniedDesc => 'Aktivér venligst baggrundsplacering i indstillinger';

  @override
  String get lovingOmi => 'Elsker du Omi?';

  @override
  String get leaveReviewIos => 'Efterlad en anmeldelse på App Store';

  @override
  String get leaveReviewAndroid => 'Efterlad en anmeldelse på Google Play';

  @override
  String get rateOnAppStore => 'Bedøm på App Store';

  @override
  String get rateOnGooglePlay => 'Bedøm på Google Play';

  @override
  String get maybeLater => 'Måske senere';

  @override
  String get speechProfileIntro => 'Omi skal lære dine mål og din stemme. Du kan ændre det senere.';

  @override
  String get getStarted => 'Kom i gang';

  @override
  String get allDone => 'Helt færdig';

  @override
  String get keepGoing => 'Fortsæt';

  @override
  String get skipThisQuestion => 'Spring dette spørgsmål over';

  @override
  String get skipForNow => 'Spring over for nu';

  @override
  String get connectionError => 'Forbindelsesfejl';

  @override
  String get connectionErrorDesc => 'Kunne ikke oprette forbindelse til enheden';

  @override
  String get invalidRecordingMultipleSpeakers => 'Ugyldig optagelse: Flere talere';

  @override
  String get multipleSpeakersDesc => 'Optagelsen indeholder flere talere';

  @override
  String get tooShortDesc => 'Optagelsen er for kort';

  @override
  String get invalidRecordingDesc => 'Ugyldig optagelse';

  @override
  String get areYouThere => 'Er du der?';

  @override
  String get noSpeechDesc => 'Ingen tale registreret';

  @override
  String get connectionLost => 'Forbindelse mistet';

  @override
  String get connectionLostDesc => 'Forbindelsen til enheden blev mistet';

  @override
  String get tryAgain => 'Prøv igen';

  @override
  String get connectOmiOmiGlass => 'Forbind Omi eller Omi Glass';

  @override
  String get continueWithoutDevice => 'Fortsæt uden enhed';

  @override
  String get permissionsRequired => 'Tilladelser påkrævet';

  @override
  String get permissionsRequiredDesc => 'Giv venligst de nødvendige tilladelser';

  @override
  String get openSettings => 'Åbn indstillinger';

  @override
  String get wantDifferentName => 'Vil du have et andet navn?';

  @override
  String get whatsYourName => 'Hvad hedder du?';

  @override
  String get speakTranscribeSummarize => 'Tal, transskribér, opsummér';

  @override
  String get signInWithApple => 'Log ind med Apple';

  @override
  String get signInWithGoogle => 'Log ind med Google';

  @override
  String get byContinuingAgree => 'Ved at fortsætte accepterer du';

  @override
  String get termsOfUse => 'Brugsbetingelser';

  @override
  String get omiYourAiCompanion => 'Omi - Din AI-ledsager';

  @override
  String get captureEveryMoment => 'Fang hvert øjeblik';

  @override
  String get appleWatchSetup => 'Apple Watch-opsætning';

  @override
  String get permissionRequestedExclaim => 'Tilladelse anmodet!';

  @override
  String get microphonePermission => 'Mikrofontilladelse';

  @override
  String get permissionGrantedNow => 'Tilladelse givet';

  @override
  String get needMicrophonePermission => 'Mikrofontilladelse påkrævet';

  @override
  String get grantPermissionButton => 'Giv tilladelse';

  @override
  String get needHelp => 'Brug for hjælp?';

  @override
  String get troubleshootingSteps => 'Fejlfindingstrin';

  @override
  String get recordingStartedSuccessfully => 'Optagelse startet';

  @override
  String get permissionNotGrantedYet => 'Tilladelse ikke givet endnu';

  @override
  String errorRequestingPermission(String error) {
    return 'Fejl ved anmodning om tilladelse';
  }

  @override
  String errorStartingRecording(String error) {
    return 'Fejl ved start af optagelse';
  }

  @override
  String get selectPrimaryLanguage => 'Vælg primært sprog';

  @override
  String get languageBenefits => 'Sprogfordele';

  @override
  String get whatsYourPrimaryLanguage => 'Hvad er dit primære sprog?';

  @override
  String get selectYourLanguage => 'Vælg dit sprog';

  @override
  String get personalGrowthJourney => 'Din personlige vækstrejse med AI, der lytter til hvert ord.';

  @override
  String get actionItemsTitle => 'Handlingspunkter';

  @override
  String get actionItemsDescription => 'Administrer dine handlingspunkter';

  @override
  String get tabToDo => 'At gøre';

  @override
  String get tabDone => 'Færdig';

  @override
  String get tabOld => 'Gamle';

  @override
  String get emptyTodoMessage => 'Ingen opgaver at gøre';

  @override
  String get emptyDoneMessage => 'Ingen færdige opgaver';

  @override
  String get emptyOldMessage => 'Ingen gamle opgaver';

  @override
  String get noItems => 'Ingen elementer';

  @override
  String get actionItemMarkedIncomplete => 'Handlingspunkt markeret som ufuldstændig';

  @override
  String get actionItemCompleted => 'Handlingspunkt fuldført';

  @override
  String get deleteActionItemTitle => 'Slet handlingselement';

  @override
  String get deleteActionItemMessage => 'Er du sikker på, at du vil slette dette handlingselement?';

  @override
  String get deleteSelectedItemsTitle => 'Slet valgte elementer';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Er du sikker på, at du vil slette de valgte elementer?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'Handlingspunkt slettet';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return 'Elementer slettet';
  }

  @override
  String get failedToDeleteItem => 'Kunne ikke slette element';

  @override
  String get failedToDeleteItems => 'Kunne ikke slette elementer';

  @override
  String get failedToDeleteSomeItems => 'Kunne ikke slette nogle elementer';

  @override
  String get welcomeActionItemsTitle => 'Velkommen til handlingspunkter';

  @override
  String get welcomeActionItemsDescription => 'Hold styr på dine opgaver';

  @override
  String get autoExtractionFeature => 'Automatisk udtrækning';

  @override
  String get editSwipeFeature => 'Stryg for at redigere';

  @override
  String itemsSelected(int count) {
    return '$count valgt';
  }

  @override
  String get selectAll => 'Vælg alle';

  @override
  String get deleteSelected => 'Slet valgte';

  @override
  String get searchMemories => 'Søg minder...';

  @override
  String get memoryDeleted => 'Hukommelse slettet';

  @override
  String get undo => 'Fortryd';

  @override
  String get noMemoriesYet => '🧠 Ingen minder endnu';

  @override
  String get noAutoMemories => 'Ingen automatiske hukommelser';

  @override
  String get noManualMemories => 'Ingen manuelle hukommelser';

  @override
  String get noMemoriesInCategories => 'Ingen hukommelser i kategorier';

  @override
  String get noMemoriesFound => '🔍 Ingen minder fundet';

  @override
  String get addFirstMemory => 'Tilføj din første hukommelse';

  @override
  String get clearMemoryTitle => 'Ryd hukommelse';

  @override
  String get clearMemoryMessage => 'Er du sikker på, at du vil rydde hukommelsen?';

  @override
  String get clearMemoryButton => 'Ryd hukommelse';

  @override
  String get memoryClearedSuccess => 'Hukommelse ryddet';

  @override
  String get noMemoriesToDelete => 'Ingen minder at slette';

  @override
  String get createMemoryTooltip => 'Opret hukommelse';

  @override
  String get createActionItemTooltip => 'Opret handlingspunkt';

  @override
  String get memoryManagement => 'Hukommelsesstyring';

  @override
  String get filterMemories => 'Filtrer hukommelser';

  @override
  String totalMemoriesCount(int count) {
    return 'Samlede hukommelser: $count';
  }

  @override
  String get publicMemories => 'Offentlige hukommelser';

  @override
  String get privateMemories => 'Private hukommelser';

  @override
  String get makeAllPrivate => 'Gør alle private';

  @override
  String get makeAllPublic => 'Gør alle offentlige';

  @override
  String get deleteAllMemories => 'Slet alle minder';

  @override
  String get allMemoriesPrivateResult => 'Alle hukommelser er nu private';

  @override
  String get allMemoriesPublicResult => 'Alle hukommelser er nu offentlige';

  @override
  String get newMemory => '✨ Ny hukommelse';

  @override
  String get editMemory => '✏️ Rediger hukommelse';

  @override
  String get memoryContentHint => 'Indtast hukommelsesindhold';

  @override
  String get failedToSaveMemory => 'Kunne ikke gemme hukommelse';

  @override
  String get saveMemory => 'Gem hukommelse';

  @override
  String get retry => 'Prøv igen';

  @override
  String get createActionItem => 'Opret opgave';

  @override
  String get editActionItem => 'Rediger opgave';

  @override
  String get actionItemDescriptionHint => 'Indtast beskrivelse';

  @override
  String get actionItemDescriptionEmpty => 'Beskrivelse kan ikke være tom';

  @override
  String get actionItemUpdated => 'Handlingspunkt opdateret';

  @override
  String get failedToUpdateActionItem => 'Kunne ikke opdatere opgave';

  @override
  String get actionItemCreated => 'Handlingspunkt oprettet';

  @override
  String get failedToCreateActionItem => 'Kunne ikke oprette opgave';

  @override
  String get dueDate => 'Forfaldsdato';

  @override
  String get time => 'Tid';

  @override
  String get addDueDate => 'Tilføj forfaldsdato';

  @override
  String get pressDoneToSave => 'Tryk på færdig for at gemme';

  @override
  String get pressDoneToCreate => 'Tryk på færdig for at oprette';

  @override
  String get filterAll => 'Alle';

  @override
  String get filterSystem => 'System';

  @override
  String get filterInteresting => 'Interessant';

  @override
  String get filterManual => 'Manuel';

  @override
  String get completed => 'Fuldført';

  @override
  String get markComplete => 'Marker som fuldført';

  @override
  String get actionItemDeleted => 'Handlingselement slettet';

  @override
  String get failedToDeleteActionItem => 'Kunne ikke slette opgave';

  @override
  String get deleteActionItemConfirmTitle => 'Slet handlingspunkt';

  @override
  String get deleteActionItemConfirmMessage => 'Er du sikker på, at du vil slette dette handlingspunkt?';

  @override
  String get appLanguage => 'App-sprog';

  @override
  String get appInterfaceSectionTitle => 'APP-GRÆNSEFLADE';

  @override
  String get speechTranscriptionSectionTitle => 'TALE OG TRANSSKRIPTION';

  @override
  String get languageSettingsHelperText =>
      'App-sprog ændrer menuer og knapper. Talesprog påvirker, hvordan dine optagelser transskriberes.';

  @override
  String get translationNotice => 'Oversættelsesmeddelelse';

  @override
  String get translationNoticeMessage =>
      'Omi oversætter samtaler til dit primære sprog. Opdater det når som helst i Indstillinger → Profiler.';

  @override
  String get pleaseCheckInternetConnection => 'Tjek venligst din internetforbindelse og prøv igen';

  @override
  String get pleaseSelectReason => 'Vælg venligst en årsag';

  @override
  String get tellUsMoreWhatWentWrong => 'Fortæl os mere om, hvad der gik galt...';

  @override
  String get selectText => 'Vælg tekst';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Maksimum $count mål tilladt';
  }

  @override
  String get conversationCannotBeMerged => 'Denne samtale kan ikke flettes (låst eller allerede ved at flette)';

  @override
  String get pleaseEnterFolderName => 'Indtast venligst et mappenavn';

  @override
  String get failedToCreateFolder => 'Kunne ikke oprette mappe';

  @override
  String get failedToUpdateFolder => 'Kunne ikke opdatere mappe';

  @override
  String get folderName => 'Mappenavn';

  @override
  String get descriptionOptional => 'Description (optional)';

  @override
  String get failedToDeleteFolder => 'Kunne ikke slette mappe';

  @override
  String get editFolder => 'Rediger mappe';

  @override
  String get deleteFolder => 'Slet mappe';

  @override
  String get transcriptCopiedToClipboard => 'Transskription kopieret til udklipsholder';

  @override
  String get summaryCopiedToClipboard => 'Resumé kopieret til udklipsholder';

  @override
  String get conversationUrlCouldNotBeShared => 'Samtale URL kunne ikke deles.';

  @override
  String get urlCopiedToClipboard => 'URL kopieret til udklipsholder';

  @override
  String get exportTranscript => 'Eksportér transskription';

  @override
  String get exportSummary => 'Eksportér resumé';

  @override
  String get exportButton => 'Eksportér';

  @override
  String get actionItemsCopiedToClipboard => 'Handlingspunkter kopieret til udklipsholder';

  @override
  String get summarize => 'Opsummer';

  @override
  String get generateSummary => 'Generer opsummering';

  @override
  String get conversationNotFoundOrDeleted => 'Samtale ikke fundet eller er blevet slettet';

  @override
  String get deleteMemory => 'Slet hukommelse';

  @override
  String get thisActionCannotBeUndone => 'Denne handling kan ikke fortrydes.';

  @override
  String memoriesCount(int count) {
    return '$count erindringer';
  }

  @override
  String get noMemoriesInCategory => 'Ingen erindringer i denne kategori endnu';

  @override
  String get addYourFirstMemory => 'Tilføj dit første minde';

  @override
  String get firmwareDisconnectUsb => 'Afbryd USB';

  @override
  String get firmwareUsbWarning => 'USB-forbindelse under opdateringer kan beskadige din enhed.';

  @override
  String get firmwareBatteryAbove15 => 'Batteri over 15%';

  @override
  String get firmwareEnsureBattery => 'Sørg for, at din enhed har 15% batteri.';

  @override
  String get firmwareStableConnection => 'Stabil forbindelse';

  @override
  String get firmwareConnectWifi => 'Tilslut til WiFi eller mobildata.';

  @override
  String failedToStartUpdate(String error) {
    return 'Kunne ikke starte opdatering: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'Før opdatering, sørg for:';

  @override
  String get confirmed => 'Bekræftet!';

  @override
  String get release => 'Slip';

  @override
  String get slideToUpdate => 'Glid for at opdatere';

  @override
  String copiedToClipboard(String title) {
    return '$title kopieret til udklipsholder';
  }

  @override
  String get batteryLevel => 'Batteriniveau';

  @override
  String get productUpdate => 'Produktopdatering';

  @override
  String get offline => 'Offline';

  @override
  String get available => 'Tilgængelig';

  @override
  String get unpairDeviceDialogTitle => 'Afpar enhed';

  @override
  String get unpairDeviceDialogMessage =>
      'Dette vil afparre enheden, så den kan forbindes til en anden telefon. Du skal gå til Indstillinger > Bluetooth og glemme enheden for at fuldføre processen.';

  @override
  String get unpair => 'Afpar';

  @override
  String get unpairAndForgetDevice => 'Afpar og glem enhed';

  @override
  String get unknownDevice => 'Ukendt enhed';

  @override
  String get unknown => 'Ukendt';

  @override
  String get productName => 'Produktnavn';

  @override
  String get serialNumber => 'Serienummer';

  @override
  String get connected => 'Forbundet';

  @override
  String get privacyPolicyTitle => 'Fortrolighedspolitik';

  @override
  String get omiSttProvider => 'Omi STT-udbyder';

  @override
  String labelCopied(String label) {
    return '$label kopieret';
  }

  @override
  String get noApiKeysYet => 'Ingen API-nøgler endnu. Opret en for at integrere med din app.';

  @override
  String get createKeyToGetStarted => 'Opret en nøgle for at komme i gang';

  @override
  String get persona => 'Persona';

  @override
  String get configureYourAiPersona => 'Konfigurer din AI-persona';

  @override
  String get configureSttProvider => 'Konfigurer STT-udbyder';

  @override
  String get setWhenConversationsAutoEnd => 'Indstil hvornår samtaler afsluttes automatisk';

  @override
  String get importDataFromOtherSources => 'Importer data fra andre kilder';

  @override
  String get debugAndDiagnostics => 'Fejlfinding og diagnostik';

  @override
  String get autoDeletesAfter3Days => 'Slettes automatisk efter 3 dage';

  @override
  String get helpsDiagnoseIssues => 'Hjælper med at diagnosticere problemer';

  @override
  String get exportStartedMessage => 'Eksport startet. Dette kan tage et par sekunder...';

  @override
  String get exportConversationsToJson => 'Eksporter samtaler til en JSON-fil';

  @override
  String get knowledgeGraphDeletedSuccess => 'Vidensgraf slettet succesfuldt';

  @override
  String failedToDeleteGraph(String error) {
    return 'Kunne ikke slette graf: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'Ryd alle noder og forbindelser';

  @override
  String get addToClaudeDesktopConfig => 'Tilføj til claude_desktop_config.json';

  @override
  String get connectAiAssistantsToData => 'Forbind AI-assistenter til dine data';

  @override
  String get useYourMcpApiKey => 'Brug din MCP API-nøgle';

  @override
  String get realTimeTranscript => 'Realtidstranskription';

  @override
  String get experimental => 'Eksperimentel';

  @override
  String get transcriptionDiagnostics => 'Transkriptionsdiagnostik';

  @override
  String get detailedDiagnosticMessages => 'Detaljerede diagnostiske beskeder';

  @override
  String get autoCreateSpeakers => 'Opret talere automatisk';

  @override
  String get autoCreateWhenNameDetected => 'Opret automatisk når navn registreres';

  @override
  String get followUpQuestions => 'Opfølgende spørgsmål';

  @override
  String get suggestQuestionsAfterConversations => 'Foreslå spørgsmål efter samtaler';

  @override
  String get goalTracker => 'Målsporer';

  @override
  String get trackPersonalGoalsOnHomepage => 'Spor dine personlige mål på startsiden';

  @override
  String get dailyReflection => 'Daglig refleksion';

  @override
  String get get9PmReminderToReflect => 'Få en påmindelse kl. 21 om at reflektere over din dag';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'Handlingselementbeskrivelse kan ikke være tom';

  @override
  String get saved => 'Gemt';

  @override
  String get overdue => 'Forsinket';

  @override
  String get failedToUpdateDueDate => 'Kunne ikke opdatere forfaldsdato';

  @override
  String get markIncomplete => 'Marker som ufuldstændig';

  @override
  String get editDueDate => 'Rediger forfaldsdato';

  @override
  String get setDueDate => 'Indstil forfaldsdato';

  @override
  String get clearDueDate => 'Ryd forfaldsdato';

  @override
  String get failedToClearDueDate => 'Kunne ikke rydde forfaldsdato';

  @override
  String get mondayAbbr => 'Man';

  @override
  String get tuesdayAbbr => 'Tir';

  @override
  String get wednesdayAbbr => 'Ons';

  @override
  String get thursdayAbbr => 'Tor';

  @override
  String get fridayAbbr => 'Fre';

  @override
  String get saturdayAbbr => 'Lør';

  @override
  String get sundayAbbr => 'Søn';

  @override
  String get howDoesItWork => 'Hvordan virker det?';

  @override
  String get sdCardSyncDescription => 'SD-kortsynkronisering vil importere dine minder fra SD-kortet til appen';

  @override
  String get checksForAudioFiles => 'Kontrollerer for lydfiler på SD-kortet';

  @override
  String get omiSyncsAudioFiles => 'Omi synkroniserer derefter lydfilerne med serveren';

  @override
  String get serverProcessesAudio => 'Serveren behandler lydfilerne og opretter minder';

  @override
  String get youreAllSet => 'Du er klar!';

  @override
  String get welcomeToOmiDescription =>
      'Velkommen til Omi! Din AI-ledsager er klar til at hjælpe dig med samtaler, opgaver og meget mere.';

  @override
  String get startUsingOmi => 'Begynd at bruge Omi';

  @override
  String get back => 'Tilbage';

  @override
  String get keyboardShortcuts => 'Tastaturgenveje';

  @override
  String get toggleControlBar => 'Skift kontrolbjælke';

  @override
  String get pressKeys => 'Tryk på taster...';

  @override
  String get cmdRequired => '⌘ påkrævet';

  @override
  String get invalidKey => 'Ugyldig tast';

  @override
  String get space => 'Mellemrum';

  @override
  String get search => 'Søg';

  @override
  String get searchPlaceholder => 'Søg...';

  @override
  String get untitledConversation => 'Unavngivet samtale';

  @override
  String countRemaining(String count) {
    return '$count tilbage';
  }

  @override
  String get addGoal => 'Tilføj mål';

  @override
  String get editGoal => 'Rediger mål';

  @override
  String get icon => 'Ikon';

  @override
  String get goalTitle => 'Måltitel';

  @override
  String get current => 'Nuværende';

  @override
  String get target => 'Mål';

  @override
  String get saveGoal => 'Gem';

  @override
  String get goals => 'Mål';

  @override
  String get tapToAddGoal => 'Tryk for at tilføje et mål';

  @override
  String welcomeBack(String name) {
    return 'Velkommen tilbage, $name';
  }

  @override
  String get yourConversations => 'Dine samtaler';

  @override
  String get reviewAndManageConversations => 'Gennemgå og administrer dine optagede samtaler';

  @override
  String get startCapturingConversations => 'Begynd at optage samtaler med din Omi-enhed for at se dem her.';

  @override
  String get useMobileAppToCapture => 'Brug din mobilapp til at optage lyd';

  @override
  String get conversationsProcessedAutomatically => 'Samtaler behandles automatisk';

  @override
  String get getInsightsInstantly => 'Få indsigter og resuméer øjeblikkeligt';

  @override
  String get showAll => 'Vis alle →';

  @override
  String get noTasksForToday => 'Ingen opgaver for i dag.\\nSpørg Omi om flere opgaver eller opret manuelt.';

  @override
  String get dailyScore => 'DAGLIG SCORE';

  @override
  String get dailyScoreDescription => 'En score til at hjælpe dig\nmed at fokusere på udførelse.';

  @override
  String get searchResults => 'Søgeresultater';

  @override
  String get actionItems => 'Handlingspunkter';

  @override
  String get tasksToday => 'I dag';

  @override
  String get tasksTomorrow => 'I morgen';

  @override
  String get tasksNoDeadline => 'Ingen frist';

  @override
  String get tasksLater => 'Senere';

  @override
  String get loadingTasks => 'Indlæser opgaver...';

  @override
  String get tasks => 'Opgaver';

  @override
  String get swipeTasksToIndent => 'Stryg opgaver for indrykkning, træk mellem kategorier';

  @override
  String get create => 'Opret';

  @override
  String get noTasksYet => 'Ingen opgaver endnu';

  @override
  String get tasksFromConversationsWillAppear =>
      'Opgaver fra dine samtaler vises her.\nKlik på Opret for at tilføje en manuelt.';

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
  String get timePM => 'EM';

  @override
  String get timeAM => 'FM';

  @override
  String get actionItemUpdatedSuccessfully => 'Opgave opdateret succesfuldt';

  @override
  String get actionItemCreatedSuccessfully => 'Opgave oprettet succesfuldt';

  @override
  String get actionItemDeletedSuccessfully => 'Opgave slettet succesfuldt';

  @override
  String get deleteActionItem => 'Slet opgave';

  @override
  String get deleteActionItemConfirmation =>
      'Er du sikker på, at du vil slette denne opgave? Denne handling kan ikke fortrydes.';

  @override
  String get enterActionItemDescription => 'Indtast opgavebeskrivelse...';

  @override
  String get markAsCompleted => 'Marker som fuldført';

  @override
  String get setDueDateAndTime => 'Indstil forfaldsdato og tid';

  @override
  String get reloadingApps => 'Genindlæser apps...';

  @override
  String get loadingApps => 'Indlæser apps...';

  @override
  String get browseInstallCreateApps => 'Gennemse, installer og opret apps';

  @override
  String get all => 'Alle';

  @override
  String get open => 'Åbn';

  @override
  String get install => 'Installer';

  @override
  String get noAppsAvailable => 'Ingen apps tilgængelige';

  @override
  String get unableToLoadApps => 'Kan ikke indlæse apps';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'Prøv at justere dine søgetermer eller filtre';

  @override
  String get checkBackLaterForNewApps => 'Tjek tilbage senere for nye apps';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'Tjek venligst din internetforbindelse og prøv igen';

  @override
  String get createNewApp => 'Opret ny app';

  @override
  String get buildSubmitCustomOmiApp => 'Byg og indsend din tilpassede Omi-app';

  @override
  String get submittingYourApp => 'Sender din app...';

  @override
  String get preparingFormForYou => 'Forbereder formularen til dig...';

  @override
  String get appDetails => 'App-detaljer';

  @override
  String get paymentDetails => 'Betalingsoplysninger';

  @override
  String get previewAndScreenshots => 'Forhåndsvisning og skærmbilleder';

  @override
  String get appCapabilities => 'App-funktioner';

  @override
  String get aiPrompts => 'AI-prompter';

  @override
  String get chatPrompt => 'Chat-prompt';

  @override
  String get chatPromptPlaceholder =>
      'Du er en fantastisk app, dit job er at svare på brugerforespørgsler og få dem til at føle sig godt tilpas...';

  @override
  String get conversationPrompt => 'Samtaleprompt';

  @override
  String get conversationPromptPlaceholder =>
      'Du er en fantastisk app, du vil få en transskription og opsummering af en samtale...';

  @override
  String get notificationScopes => 'Notifikationsområder';

  @override
  String get appPrivacyAndTerms => 'App-privatliv og vilkår';

  @override
  String get makeMyAppPublic => 'Gør min app offentlig';

  @override
  String get submitAppTermsAgreement =>
      'Ved at indsende denne app accepterer jeg Omi AI\'s servicevilkår og privatlivspolitik';

  @override
  String get submitApp => 'Indsend app';

  @override
  String get needHelpGettingStarted => 'Har du brug for hjælp til at komme i gang?';

  @override
  String get clickHereForAppBuildingGuides => 'Klik her for app-bygningsvejledninger og dokumentation';

  @override
  String get submitAppQuestion => 'Indsend app?';

  @override
  String get submitAppPublicDescription =>
      'Din app vil blive gennemgået og gjort offentlig. Du kan begynde at bruge den med det samme, selv under gennemgangen!';

  @override
  String get submitAppPrivateDescription =>
      'Din app vil blive gennemgået og gjort tilgængelig for dig privat. Du kan begynde at bruge den med det samme, selv under gennemgangen!';

  @override
  String get startEarning => 'Begynd at tjene! 💰';

  @override
  String get connectStripeOrPayPal => 'Tilslut Stripe eller PayPal for at modtage betalinger for din app.';

  @override
  String get connectNow => 'Tilslut nu';

  @override
  String get installsCount => 'Installationer';

  @override
  String get uninstallApp => 'Afinstaller app';

  @override
  String get subscribe => 'Abonner';

  @override
  String get dataAccessNotice => 'Meddelelse om dataadgang';

  @override
  String get dataAccessWarning =>
      'Denne app vil få adgang til dine data. Omi AI er ikke ansvarlig for, hvordan dine data bruges, ændres eller slettes af denne app';

  @override
  String get installApp => 'Installer app';

  @override
  String get betaTesterNotice =>
      'Du er betatester for denne app. Den er ikke offentlig endnu. Den bliver offentlig, når den er godkendt.';

  @override
  String get appUnderReviewOwner =>
      'Din app er under gennemgang og kun synlig for dig. Den bliver offentlig, når den er godkendt.';

  @override
  String get appRejectedNotice =>
      'Din app er blevet afvist. Opdater venligst app-detaljerne og indsend den igen til gennemgang.';

  @override
  String get setupSteps => 'Opsætningstrin';

  @override
  String get setupInstructions => 'Opsætningsinstruktioner';

  @override
  String get integrationInstructions => 'Integrationsinstruktioner';

  @override
  String get preview => 'Forhåndsvisning';

  @override
  String get aboutTheApp => 'Om appen';

  @override
  String get aboutThePersona => 'Om personaen';

  @override
  String get chatPersonality => 'Chat-personlighed';

  @override
  String get ratingsAndReviews => 'Bedømmelser og anmeldelser';

  @override
  String get noRatings => 'ingen vurderinger';

  @override
  String ratingsCount(String count) {
    return '$count+ vurderinger';
  }

  @override
  String get errorActivatingApp => 'Fejl ved aktivering af app';

  @override
  String get integrationSetupRequired =>
      'Hvis dette er en integrationsapp, skal du sørge for, at opsætningen er fuldført.';

  @override
  String get installed => 'Installeret';

  @override
  String get appIdLabel => 'App-ID';

  @override
  String get appNameLabel => 'Appnavn';

  @override
  String get appNamePlaceholder => 'Min fantastiske app';

  @override
  String get pleaseEnterAppName => 'Indtast venligst appnavn';

  @override
  String get categoryLabel => 'Kategori';

  @override
  String get selectCategory => 'Vælg kategori';

  @override
  String get descriptionLabel => 'Beskrivelse';

  @override
  String get appDescriptionPlaceholder =>
      'Min fantastiske app er en fantastisk app, der gør fantastiske ting. Det er den bedste app nogensinde!';

  @override
  String get pleaseProvideValidDescription => 'Angiv venligst en gyldig beskrivelse';

  @override
  String get appPricingLabel => 'App-priser';

  @override
  String get noneSelected => 'Ingen valgt';

  @override
  String get appIdCopiedToClipboard => 'App-ID kopieret til udklipsholder';

  @override
  String get appCategoryModalTitle => 'App-kategori';

  @override
  String get pricingFree => 'Gratis';

  @override
  String get pricingPaid => 'Betalt';

  @override
  String get loadingCapabilities => 'Indlæser funktioner...';

  @override
  String get filterInstalled => 'Installeret';

  @override
  String get filterMyApps => 'Mine apps';

  @override
  String get clearSelection => 'Ryd valg';

  @override
  String get filterCategory => 'Kategori';

  @override
  String get rating4PlusStars => '4+ stjerner';

  @override
  String get rating3PlusStars => '3+ stjerner';

  @override
  String get rating2PlusStars => '2+ stjerner';

  @override
  String get rating1PlusStars => '1+ stjerner';

  @override
  String get filterRating => 'Bedømmelse';

  @override
  String get filterCapabilities => 'Funktioner';

  @override
  String get noNotificationScopesAvailable => 'Ingen notifikationsområder tilgængelige';

  @override
  String get popularApps => 'Populære apps';

  @override
  String get pleaseProvidePrompt => 'Angiv venligst en prompt';

  @override
  String chatWithAppName(String appName) {
    return 'Chat med $appName';
  }

  @override
  String get defaultAiAssistant => 'Standard AI-assistent';

  @override
  String get readyToChat => '✨ Klar til at chatte!';

  @override
  String get connectionNeeded => '🌐 Forbindelse påkrævet';

  @override
  String get startConversation => 'Start en samtale og lad magien begynde';

  @override
  String get checkInternetConnection => 'Tjek venligst din internetforbindelse';

  @override
  String get wasThisHelpful => 'Var dette nyttigt?';

  @override
  String get thankYouForFeedback => 'Tak for din feedback!';

  @override
  String get maxFilesUploadError => 'Du kan kun uploade 4 filer ad gangen';

  @override
  String get attachedFiles => '📎 Vedhæftede filer';

  @override
  String get takePhoto => 'Tag billede';

  @override
  String get captureWithCamera => 'Optag med kamera';

  @override
  String get selectImages => 'Vælg billeder';

  @override
  String get chooseFromGallery => 'Vælg fra galleri';

  @override
  String get selectFile => 'Vælg en fil';

  @override
  String get chooseAnyFileType => 'Vælg enhver filtype';

  @override
  String get cannotReportOwnMessages => 'Du kan ikke rapportere dine egne beskeder';

  @override
  String get messageReportedSuccessfully => '✅ Besked rapporteret';

  @override
  String get confirmReportMessage => 'Er du sikker på, at du vil rapportere denne besked?';

  @override
  String get selectChatAssistant => 'Vælg chatassistent';

  @override
  String get enableMoreApps => 'Aktiver flere apps';

  @override
  String get chatCleared => 'Chat ryddet';

  @override
  String get clearChatTitle => 'Ryd chat?';

  @override
  String get confirmClearChat => 'Er du sikker på, at du vil rydde chatten? Denne handling kan ikke fortrydes.';

  @override
  String get copy => 'Kopiér';

  @override
  String get share => 'Del';

  @override
  String get report => 'Rapportér';

  @override
  String get microphonePermissionRequired => 'Mikrofontilladelse er påkrævet til stemmeoptagelse.';

  @override
  String get microphonePermissionDenied =>
      'Mikrofontilladelse nægtet. Giv venligst tilladelse i Systemindstillinger > Privatliv og sikkerhed > Mikrofon.';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'Kunne ikke kontrollere mikrofontilladelse: $error';
  }

  @override
  String get failedToTranscribeAudio => 'Kunne ikke transkribere lyd';

  @override
  String get transcribing => 'Transskriberer...';

  @override
  String get transcriptionFailed => 'Transskription mislykkedes';

  @override
  String get discardedConversation => 'Kasseret samtale';

  @override
  String get at => 'kl.';

  @override
  String get from => 'fra';

  @override
  String get copied => 'Kopieret!';

  @override
  String get copyLink => 'Kopier link';

  @override
  String get hideTranscript => 'Skjul transskription';

  @override
  String get viewTranscript => 'Vis transskription';

  @override
  String get conversationDetails => 'Samtaledetaljer';

  @override
  String get transcript => 'Transskription';

  @override
  String segmentsCount(int count) {
    return '$count segmenter';
  }

  @override
  String get noTranscriptAvailable => 'Ingen transskription tilgængelig';

  @override
  String get noTranscriptMessage => 'Denne samtale har ingen transskription.';

  @override
  String get conversationUrlCouldNotBeGenerated => 'Samtale-URL kunne ikke genereres.';

  @override
  String get failedToGenerateConversationLink => 'Kunne ikke generere samtalelink';

  @override
  String get failedToGenerateShareLink => 'Kunne ikke generere delingslink';

  @override
  String get reloadingConversations => 'Genindlæser samtaler...';

  @override
  String get user => 'Bruger';

  @override
  String get starred => 'Stjernemarkeret';

  @override
  String get date => 'Dato';

  @override
  String get noResultsFound => 'Ingen resultater fundet';

  @override
  String get tryAdjustingSearchTerms => 'Prøv at justere dine søgeord';

  @override
  String get starConversationsToFindQuickly => 'Stjernemarkér samtaler for at finde dem hurtigt her';

  @override
  String noConversationsOnDate(String date) {
    return 'Ingen samtaler d. $date';
  }

  @override
  String get trySelectingDifferentDate => 'Prøv at vælge en anden dato';

  @override
  String get conversations => 'Samtaler';

  @override
  String get chat => 'Chat';

  @override
  String get actions => 'Handlinger';

  @override
  String get syncAvailable => 'Synkronisering tilgængelig';

  @override
  String get referAFriend => 'Henvis en ven';

  @override
  String get help => 'Hjælp';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'Opgrader til Pro';

  @override
  String get getOmiDevice => 'Få Omi-enhed';

  @override
  String get wearableAiCompanion => 'Bærbar AI-ledsager';

  @override
  String get loadingMemories => 'Indlæser minder...';

  @override
  String get allMemories => 'Alle minder';

  @override
  String get aboutYou => 'Om dig';

  @override
  String get manual => 'Manuel';

  @override
  String get loadingYourMemories => 'Indlæser dine minder...';

  @override
  String get createYourFirstMemory => 'Opret dit første minde for at komme i gang';

  @override
  String get tryAdjustingFilter => 'Prøv at justere din søgning eller filter';

  @override
  String get whatWouldYouLikeToRemember => 'Hvad vil du huske?';

  @override
  String get category => 'Kategori';

  @override
  String get public => 'Offentlig';

  @override
  String get failedToSaveCheckConnection => 'Kunne ikke gemme. Tjek din forbindelse.';

  @override
  String get createMemory => 'Opret hukommelse';

  @override
  String get deleteMemoryConfirmation =>
      'Er du sikker på, at du vil slette denne hukommelse? Denne handling kan ikke fortrydes.';

  @override
  String get makePrivate => 'Gør privat';

  @override
  String get organizeAndControlMemories => 'Organiser og kontroller dine minder';

  @override
  String get total => 'I alt';

  @override
  String get makeAllMemoriesPrivate => 'Gør alle minder private';

  @override
  String get setAllMemoriesToPrivate => 'Indstil alle minder til privat synlighed';

  @override
  String get makeAllMemoriesPublic => 'Gør alle minder offentlige';

  @override
  String get setAllMemoriesToPublic => 'Indstil alle minder til offentlig synlighed';

  @override
  String get permanentlyRemoveAllMemories => 'Fjern permanent alle minder fra Omi';

  @override
  String get allMemoriesAreNowPrivate => 'Alle minder er nu private';

  @override
  String get allMemoriesAreNowPublic => 'Alle minder er nu offentlige';

  @override
  String get clearOmisMemory => 'Ryd Omis hukommelse';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Er du sikker på, at du vil rydde Omis hukommelse? Denne handling kan ikke fortrydes og vil permanent slette alle $count minder.';
  }

  @override
  String get omisMemoryCleared => 'Omis hukommelse om dig er blevet ryddet';

  @override
  String get welcomeToOmi => 'Velkommen til Omi';

  @override
  String get continueWithApple => 'Fortsæt med Apple';

  @override
  String get continueWithGoogle => 'Fortsæt med Google';

  @override
  String get byContinuingYouAgree => 'Ved at fortsætte accepterer du vores ';

  @override
  String get termsOfService => 'Servicevilkår';

  @override
  String get and => ' og ';

  @override
  String get dataAndPrivacy => 'Data og privatliv';

  @override
  String get secureAuthViaAppleId => 'Sikker godkendelse via Apple ID';

  @override
  String get secureAuthViaGoogleAccount => 'Sikker godkendelse via Google-konto';

  @override
  String get whatWeCollect => 'Hvad vi indsamler';

  @override
  String get dataCollectionMessage =>
      'Ved at fortsætte vil dine samtaler, optagelser og personlige oplysninger blive sikkert gemt på vores servere for at levere AI-drevne indsigter og aktivere alle app-funktioner.';

  @override
  String get dataProtection => 'Databeskyttelse';

  @override
  String get yourDataIsProtected => 'Dine data er beskyttet og styret af vores ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'Vælg venligst dit primære sprog';

  @override
  String get chooseYourLanguage => 'Vælg dit sprog';

  @override
  String get selectPreferredLanguageForBestExperience => 'Vælg dit foretrukne sprog for den bedste Omi-oplevelse';

  @override
  String get searchLanguages => 'Søg sprog...';

  @override
  String get selectALanguage => 'Vælg et sprog';

  @override
  String get tryDifferentSearchTerm => 'Prøv et andet søgeord';

  @override
  String get pleaseEnterYourName => 'Indtast venligst dit navn';

  @override
  String get nameMustBeAtLeast2Characters => 'Navnet skal være mindst 2 tegn';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'Fortæl os, hvordan du gerne vil tiltales. Dette hjælper med at personalisere din Omi-oplevelse.';

  @override
  String charactersCount(int count) {
    return '$count tegn';
  }

  @override
  String get enableFeaturesForBestExperience => 'Aktiver funktioner for den bedste Omi-oplevelse på din enhed.';

  @override
  String get microphoneAccess => 'Mikrofonadgang';

  @override
  String get recordAudioConversations => 'Optag lydsamtaler';

  @override
  String get microphoneAccessDescription =>
      'Omi har brug for mikrofonadgang for at optage dine samtaler og give transkriptioner.';

  @override
  String get screenRecording => 'Skærmoptagelse';

  @override
  String get captureSystemAudioFromMeetings => 'Optag systemlyd fra møder';

  @override
  String get screenRecordingDescription =>
      'Omi har brug for skærmoptagelsestilladelse for at optage systemlyd fra dine browserbaserede møder.';

  @override
  String get accessibility => 'Tilgængelighed';

  @override
  String get detectBrowserBasedMeetings => 'Opdage browserbaserede møder';

  @override
  String get accessibilityDescription =>
      'Omi har brug for tilgængelighedstilladelse for at opdage, når du deltager i Zoom-, Meet- eller Teams-møder i din browser.';

  @override
  String get pleaseWait => 'Vent venligst...';

  @override
  String get joinTheCommunity => 'Bliv en del af fællesskabet!';

  @override
  String get loadingProfile => 'Indlæser profil...';

  @override
  String get profileSettings => 'Profilindstillinger';

  @override
  String get noEmailSet => 'Ingen e-mail angivet';

  @override
  String get userIdCopiedToClipboard => 'Bruger-ID kopieret';

  @override
  String get yourInformation => 'Dine Oplysninger';

  @override
  String get setYourName => 'Angiv dit navn';

  @override
  String get changeYourName => 'Skift dit navn';

  @override
  String get manageYourOmiPersona => 'Administrer din Omi-persona';

  @override
  String get voiceAndPeople => 'Stemme og Personer';

  @override
  String get teachOmiYourVoice => 'Lær Omi din stemme';

  @override
  String get tellOmiWhoSaidIt => 'Fortæl Omi hvem der sagde det 🗣️';

  @override
  String get payment => 'Betaling';

  @override
  String get addOrChangeYourPaymentMethod => 'Tilføj eller skift betalingsmetode';

  @override
  String get preferences => 'Præferencer';

  @override
  String get helpImproveOmiBySharing => 'Hjælp med at forbedre Omi ved at dele anonymiserede analysedata';

  @override
  String get deleteAccount => 'Slet Konto';

  @override
  String get deleteYourAccountAndAllData => 'Slet din konto og alle data';

  @override
  String get clearLogs => 'Ryd logs';

  @override
  String get debugLogsCleared => 'Fejlfindingslogfiler ryddet';

  @override
  String get exportConversations => 'Eksporter samtaler';

  @override
  String get exportAllConversationsToJson => 'Eksporter alle dine samtaler til en JSON-fil.';

  @override
  String get conversationsExportStarted =>
      'Eksport af samtaler startet. Dette kan tage et par sekunder, vent venligst.';

  @override
  String get mcpDescription =>
      'For at forbinde Omi med andre applikationer for at læse, søge og administrere dine minder og samtaler. Opret en nøgle for at komme i gang.';

  @override
  String get apiKeys => 'API-nøgler';

  @override
  String errorLabel(String error) {
    return 'Fejl: $error';
  }

  @override
  String get noApiKeysFound => 'Ingen API-nøgler fundet. Opret en for at komme i gang.';

  @override
  String get advancedSettings => 'Avancerede indstillinger';

  @override
  String get triggersWhenNewConversationCreated => 'Udløses, når en ny samtale oprettes.';

  @override
  String get triggersWhenNewTranscriptReceived => 'Udløses, når en ny udskrift modtages.';

  @override
  String get realtimeAudioBytes => 'Realtids-lydbytes';

  @override
  String get triggersWhenAudioBytesReceived => 'Udløses, når lydbytes modtages.';

  @override
  String get everyXSeconds => 'Hvert x sekund';

  @override
  String get triggersWhenDaySummaryGenerated => 'Udløses, når dagens resumé genereres.';

  @override
  String get tryLatestExperimentalFeatures => 'Prøv de nyeste eksperimentelle funktioner fra Omi-teamet.';

  @override
  String get transcriptionServiceDiagnosticStatus => 'Transskriptionstjenestens diagnostiske status';

  @override
  String get enableDetailedDiagnosticMessages =>
      'Aktiver detaljerede diagnostiske meddelelser fra transskriptionstjenesten';

  @override
  String get autoCreateAndTagNewSpeakers => 'Opret og tag nye talere automatisk';

  @override
  String get automaticallyCreateNewPerson => 'Opret automatisk en ny person, når et navn registreres i udskriften.';

  @override
  String get pilotFeatures => 'Pilotfunktioner';

  @override
  String get pilotFeaturesDescription => 'Disse funktioner er tests, og der garanteres ingen support.';

  @override
  String get suggestFollowUpQuestion => 'Foreslå opfølgende spørgsmål';

  @override
  String get saveSettings => 'Gem Indstillinger';

  @override
  String get syncingDeveloperSettings => 'Synkroniserer udviklerindstillinger...';

  @override
  String get summary => 'Resumé';

  @override
  String get auto => 'Automatisk';

  @override
  String get noSummaryForApp => 'Ingen opsummering tilgængelig for denne app. Prøv en anden app for bedre resultater.';

  @override
  String get tryAnotherApp => 'Prøv en anden app';

  @override
  String generatedBy(String appName) {
    return 'Genereret af $appName';
  }

  @override
  String get overview => 'Oversigt';

  @override
  String get otherAppResults => 'Andre app-resultater';

  @override
  String get unknownApp => 'Ukendt app';

  @override
  String get noSummaryAvailable => 'Intet resumé tilgængeligt';

  @override
  String get conversationNoSummaryYet => 'Denne samtale har endnu ikke et resumé.';

  @override
  String get chooseSummarizationApp => 'Vælg resumé-app';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName indstillet som standard resumé-app';
  }

  @override
  String get letOmiChooseAutomatically => 'Lad Omi automatisk vælge den bedste app';

  @override
  String get deleteConversationConfirmation =>
      'Er du sikker på, at du vil slette denne samtale? Denne handling kan ikke fortrydes.';

  @override
  String get conversationDeleted => 'Samtale slettet';

  @override
  String get generatingLink => 'Genererer link...';

  @override
  String get editConversation => 'Rediger samtale';

  @override
  String get conversationLinkCopiedToClipboard => 'Samtalelink kopieret til udklipsholder';

  @override
  String get conversationTranscriptCopiedToClipboard => 'Samtaleudskrift kopieret til udklipsholder';

  @override
  String get editConversationDialogTitle => 'Rediger samtale';

  @override
  String get changeTheConversationTitle => 'Skift samtalens titel';

  @override
  String get conversationTitle => 'Samtaletitel';

  @override
  String get enterConversationTitle => 'Indtast samtaletitel...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'Samtaletitel opdateret';

  @override
  String get failedToUpdateConversationTitle => 'Kunne ikke opdatere samtaletitel';

  @override
  String get errorUpdatingConversationTitle => 'Fejl ved opdatering af samtaletitel';

  @override
  String get settingUp => 'Konfigurerer...';

  @override
  String get startYourFirstRecording => 'Start din første optagelse';

  @override
  String get preparingSystemAudioCapture => 'Forbereder systemlydoptagelse';

  @override
  String get clickTheButtonToCaptureAudio =>
      'Klik på knappen for at optage lyd til direkte transkriptioner, AI-indsigt og automatisk lagring.';

  @override
  String get reconnecting => 'Genopretter forbindelse...';

  @override
  String get recordingPaused => 'Optagelse sat på pause';

  @override
  String get recordingActive => 'Optagelse aktiv';

  @override
  String get startRecording => 'Start optagelse';

  @override
  String resumingInCountdown(String countdown) {
    return 'Genoptager om ${countdown}s...';
  }

  @override
  String get tapPlayToResume => 'Tryk på afspil for at fortsætte';

  @override
  String get listeningForAudio => 'Lytter efter lyd...';

  @override
  String get preparingAudioCapture => 'Forbereder lydoptagelse';

  @override
  String get clickToBeginRecording => 'Klik for at begynde optagelse';

  @override
  String get translated => 'oversat';

  @override
  String get liveTranscript => 'Direkte transskription';

  @override
  String segmentsSingular(String count) {
    return 'segment';
  }

  @override
  String segmentsPlural(String count) {
    return '$count segmenter';
  }

  @override
  String get startRecordingToSeeTranscript => 'Start optagelse for at se direkte transskription';

  @override
  String get paused => 'På pause';

  @override
  String get initializing => 'Initialiserer...';

  @override
  String get recording => 'Optager';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'Mikrofon ændret. Genoptager om ${countdown}s';
  }

  @override
  String get clickPlayToResumeOrStop => 'Klik på afspil for at fortsætte eller stop for at afslutte';

  @override
  String get settingUpSystemAudioCapture => 'Konfigurerer systemlydoptagelse';

  @override
  String get capturingAudioAndGeneratingTranscript => 'Optager lyd og genererer transskription';

  @override
  String get clickToBeginRecordingSystemAudio => 'Klik for at begynde optagelse af systemlyd';

  @override
  String get you => 'Dig';

  @override
  String speakerWithId(String speakerId) {
    return 'Taler $speakerId';
  }

  @override
  String get translatedByOmi => 'oversat af omi';

  @override
  String get backToConversations => 'Tilbage til Samtaler';

  @override
  String get systemAudio => 'Systemlyd';

  @override
  String get mic => 'Mikrofon';

  @override
  String audioInputSetTo(String deviceName) {
    return 'Lydindgang indstillet til $deviceName';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'Fejl ved skift af lydenhed: $error';
  }

  @override
  String get selectAudioInput => 'Vælg lydindgang';

  @override
  String get loadingDevices => 'Indlæser enheder...';

  @override
  String get settingsHeader => 'INDSTILLINGER';

  @override
  String get plansAndBilling => 'Planer og Fakturering';

  @override
  String get calendarIntegration => 'Kalenderintegration';

  @override
  String get dailySummary => 'Daglig opsummering';

  @override
  String get developer => 'Udvikler';

  @override
  String get about => 'Om';

  @override
  String get selectTime => 'Vælg tid';

  @override
  String get accountGroup => 'Konto';

  @override
  String get signOutQuestion => 'Log ud?';

  @override
  String get signOutConfirmation => 'Er du sikker på, at du vil logge ud?';

  @override
  String get customVocabularyHeader => 'BRUGERDEFINERET ORDFORRÅD';

  @override
  String get addWordsDescription => 'Tilføj ord, som Omi skal genkende under transskription.';

  @override
  String get enterWordsHint => 'Indtast ord (kommasepareret)';

  @override
  String get dailySummaryHeader => 'DAGLIG OPSUMMERING';

  @override
  String get dailySummaryTitle => 'Daglig Opsummering';

  @override
  String get dailySummaryDescription => 'Få en personlig opsummering af dagens samtaler leveret som en notifikation.';

  @override
  String get deliveryTime => 'Leveringstid';

  @override
  String get deliveryTimeDescription => 'Hvornår du modtager din daglige opsummering';

  @override
  String get subscription => 'Abonnement';

  @override
  String get viewPlansAndUsage => 'Se Planer og Forbrug';

  @override
  String get viewPlansDescription => 'Administrer dit abonnement og se forbrugsstatistikker';

  @override
  String get addOrChangePaymentMethod => 'Tilføj eller skift din betalingsmetode';

  @override
  String get displayOptions => 'Visningsmuligheder';

  @override
  String get showMeetingsInMenuBar => 'Vis møder i menulinjen';

  @override
  String get displayUpcomingMeetingsDescription => 'Vis kommende møder i menulinjen';

  @override
  String get showEventsWithoutParticipants => 'Vis begivenheder uden deltagere';

  @override
  String get includePersonalEventsDescription => 'Inkluder personlige begivenheder uden deltagere';

  @override
  String get upcomingMeetings => 'Kommende møder';

  @override
  String get checkingNext7Days => 'Kontrollerer de næste 7 dage';

  @override
  String get shortcuts => 'Genveje';

  @override
  String get shortcutChangeInstruction => 'Klik på en genvej for at ændre den. Tryk på Escape for at annullere.';

  @override
  String get configurePersonaDescription => 'Konfigurer din AI-persona';

  @override
  String get configureSTTProvider => 'Konfigurer STT-udbyder';

  @override
  String get setConversationEndDescription => 'Indstil, hvornår samtaler afsluttes automatisk';

  @override
  String get importDataDescription => 'Importer data fra andre kilder';

  @override
  String get exportConversationsDescription => 'Eksporter samtaler til JSON';

  @override
  String get exportingConversations => 'Eksporterer samtaler...';

  @override
  String get clearNodesDescription => 'Ryd alle knudepunkter og forbindelser';

  @override
  String get deleteKnowledgeGraphQuestion => 'Slet vidensgraf?';

  @override
  String get deleteKnowledgeGraphWarning =>
      'Dette vil slette alle afledte vidensgrafsdata. Dine originale minder forbliver sikre.';

  @override
  String get connectOmiWithAI => 'Forbind Omi med AI-assistenter';

  @override
  String get noAPIKeys => 'Ingen API-nøgler. Opret en for at komme i gang.';

  @override
  String get autoCreateWhenDetected => 'Opret automatisk, når navn registreres';

  @override
  String get trackPersonalGoals => 'Spor personlige mål på startsiden';

  @override
  String get dailyReflectionDescription =>
      'Få en påmindelse kl. 21 om at reflektere over din dag og fange dine tanker.';

  @override
  String get endpointURL => 'Endepunkts-URL';

  @override
  String get links => 'Links';

  @override
  String get discordMemberCount => 'Over 8000 medlemmer på Discord';

  @override
  String get userInformation => 'Brugeroplysninger';

  @override
  String get capabilities => 'Funktioner';

  @override
  String get previewScreenshots => 'Forhåndsvisning af skærmbilleder';

  @override
  String get holdOnPreparingForm => 'Vent venligst, vi forbereder formularen til dig';

  @override
  String get bySubmittingYouAgreeToOmi => 'Ved at indsende accepterer du Omi ';

  @override
  String get termsAndPrivacyPolicy => 'Vilkår og Privatlivspolitik';

  @override
  String get helpsDiagnoseIssuesAutoDeletes =>
      'Hjælper med at diagnosticere problemer. Slettes automatisk efter 3 dage.';

  @override
  String get manageYourApp => 'Administrer din app';

  @override
  String get updatingYourApp => 'Opdaterer din app';

  @override
  String get fetchingYourAppDetails => 'Henter dine app-detaljer';

  @override
  String get updateAppQuestion => 'Opdater app?';

  @override
  String get updateAppConfirmation =>
      'Er du sikker på, at du vil opdatere din app? Ændringerne vil blive synlige efter gennemgang af vores team.';

  @override
  String get updateApp => 'Opdater app';

  @override
  String get createAndSubmitNewApp => 'Opret og indsend en ny app';

  @override
  String appsCount(String count) {
    return '$count apps';
  }

  @override
  String privateAppsCount(String count) {
    return 'Private apps ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'Offentlige apps ($count)';
  }

  @override
  String get newVersionAvailable => 'Ny version tilgængelig  🎉';

  @override
  String get no => 'Nej';

  @override
  String get subscriptionCancelledSuccessfully =>
      'Abonnement annulleret. Det forbliver aktivt indtil slutningen af den aktuelle faktureringsperiode.';

  @override
  String get failedToCancelSubscription => 'Kunne ikke annullere abonnement. Prøv venligst igen.';

  @override
  String get invalidPaymentUrl => 'Ugyldig betalings-URL';

  @override
  String get permissionsAndTriggers => 'Tilladelser og triggere';

  @override
  String get chatFeatures => 'Chat-funktioner';

  @override
  String get uninstall => 'Afinstaller';

  @override
  String get installs => 'INSTALLATIONER';

  @override
  String get priceLabel => 'PRIS';

  @override
  String get updatedLabel => 'OPDATERET';

  @override
  String get createdLabel => 'OPRETTET';

  @override
  String get featuredLabel => 'FREMHÆVET';

  @override
  String get cancelSubscriptionQuestion => 'Annuller abonnement?';

  @override
  String get cancelSubscriptionConfirmation =>
      'Er du sikker på, at du vil annullere dit abonnement? Du vil fortsat have adgang indtil slutningen af din nuværende faktureringsperiode.';

  @override
  String get cancelSubscriptionButton => 'Annuller abonnement';

  @override
  String get cancelling => 'Annullerer...';

  @override
  String get betaTesterMessage =>
      'Du er betatester for denne app. Den er ikke offentlig endnu. Den bliver offentlig efter godkendelse.';

  @override
  String get appUnderReviewMessage =>
      'Din app er under gennemgang og kun synlig for dig. Den bliver offentlig efter godkendelse.';

  @override
  String get appRejectedMessage => 'Din app er blevet afvist. Opdater appdetaljerne og indsend igen til gennemgang.';

  @override
  String get invalidIntegrationUrl => 'Ugyldig integrations-URL';

  @override
  String get tapToComplete => 'Tryk for at fuldføre';

  @override
  String get invalidSetupInstructionsUrl => 'Ugyldig URL til opsætningsinstruktioner';

  @override
  String get pushToTalk => 'Tryk for at tale';

  @override
  String get summaryPrompt => 'Resuméprompt';

  @override
  String get pleaseSelectARating => 'Vælg venligst en vurdering';

  @override
  String get reviewAddedSuccessfully => 'Anmeldelse tilføjet 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'Anmeldelse opdateret 🚀';

  @override
  String get failedToSubmitReview => 'Kunne ikke indsende anmeldelse. Prøv igen.';

  @override
  String get addYourReview => 'Tilføj din anmeldelse';

  @override
  String get editYourReview => 'Rediger din anmeldelse';

  @override
  String get writeAReviewOptional => 'Skriv en anmeldelse (valgfrit)';

  @override
  String get submitReview => 'Indsend anmeldelse';

  @override
  String get updateReview => 'Opdater anmeldelse';

  @override
  String get yourReview => 'Din anmeldelse';

  @override
  String get anonymousUser => 'Anonym bruger';

  @override
  String get issueActivatingApp => 'Der opstod et problem ved aktivering af denne app. Prøv venligst igen.';

  @override
  String get dataAccessNoticeDescription => 'Dataadgangsmeddelelse';

  @override
  String get copyUrl => 'Kopiér URL';

  @override
  String get txtFormat => 'TXT-format';

  @override
  String get pdfFormat => 'PDF-format';

  @override
  String get weekdayMon => 'Man';

  @override
  String get weekdayTue => 'Tir';

  @override
  String get weekdayWed => 'Ons';

  @override
  String get weekdayThu => 'Tor';

  @override
  String get weekdayFri => 'Fre';

  @override
  String get weekdaySat => 'Lør';

  @override
  String get weekdaySun => 'Søn';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return '$serviceName-integration kommer snart';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'Allerede eksporteret til $platform';
  }

  @override
  String get anotherPlatform => 'en anden platform';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'Log venligst ind med $serviceName i Indstillinger > Opgaveintegrationer';
  }

  @override
  String addingToService(String serviceName) {
    return 'Tilføjer til $serviceName...';
  }

  @override
  String addedToService(String serviceName) {
    return 'Tilføjet til $serviceName';
  }

  @override
  String failedToAddToService(String serviceName) {
    return 'Kunne ikke tilføje til $serviceName';
  }

  @override
  String get permissionDeniedForAppleReminders => 'Tilladelse afvist for Apple Reminders';

  @override
  String failedToCreateApiKey(String error) {
    return 'Kunne ikke oprette udbyderens API-nøgle: $error';
  }

  @override
  String get createAKey => 'Opret en nøgle';

  @override
  String get apiKeyRevokedSuccessfully => 'API-nøgle tilbagekaldt';

  @override
  String failedToRevokeApiKey(String error) {
    return 'Kunne ikke tilbagekalde API-nøgle: $error';
  }

  @override
  String get omiApiKeys => 'Omi API-nøgler';

  @override
  String get apiKeysDescription =>
      'API-nøgler bruges til godkendelse, når din app kommunikerer med OMI-serveren. De gør det muligt for din applikation at oprette minder og få sikker adgang til andre OMI-tjenester.';

  @override
  String get aboutOmiApiKeys => 'Om Omi API-nøgler';

  @override
  String get yourNewKey => 'Din nye nøgle:';

  @override
  String get copyToClipboard => 'Kopiér til udklipsholder';

  @override
  String get pleaseCopyKeyNow => 'Kopiér den nu og skriv den ned et sikkert sted. ';

  @override
  String get willNotSeeAgain => 'Du vil ikke kunne se den igen.';

  @override
  String get revokeKey => 'Tilbagekald nøgle';

  @override
  String get revokeApiKeyQuestion => 'Tilbagekald API-nøgle?';

  @override
  String get revokeApiKeyWarning =>
      'Denne handling kan ikke fortrydes. Alle applikationer, der bruger denne nøgle, vil ikke længere kunne få adgang til API\'et.';

  @override
  String get revoke => 'Tilbagekald';

  @override
  String get whatWouldYouLikeToCreate => 'Hvad vil du gerne oprette?';

  @override
  String get createAnApp => 'Opret en app';

  @override
  String get createAndShareYourApp => 'Opret og del din app';

  @override
  String get createMyClone => 'Opret min klon';

  @override
  String get createYourDigitalClone => 'Opret din digitale klon';

  @override
  String get itemApp => 'App';

  @override
  String get itemPersona => 'Persona';

  @override
  String keepItemPublic(String item) {
    return 'Behold $item offentlig';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return 'Gør $item offentlig?';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return 'Gør $item privat?';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'Hvis du gør $item offentlig, kan den bruges af alle';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'Hvis du gør $item privat nu, stopper den med at fungere for alle og vil kun være synlig for dig';
  }

  @override
  String get manageApp => 'Administrer app';

  @override
  String get updatePersonaDetails => 'Opdater persona-detaljer';

  @override
  String deleteItemTitle(String item) {
    return 'Slet $item';
  }

  @override
  String deleteItemQuestion(String item) {
    return 'Slet $item?';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'Er du sikker på, at du vil slette denne $item? Denne handling kan ikke fortrydes.';
  }

  @override
  String get revokeKeyQuestion => 'Tilbagekald nøgle?';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'Er du sikker på, at du vil tilbagekalde nøglen \"$keyName\"? Denne handling kan ikke fortrydes.';
  }

  @override
  String get createNewKey => 'Opret ny nøgle';

  @override
  String get keyNameHint => 'f.eks. Claude Desktop';

  @override
  String get pleaseEnterAName => 'Indtast venligst et navn.';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'Kunne ikke oprette nøgle: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'Kunne ikke oprette nøgle. Prøv venligst igen.';

  @override
  String get keyCreated => 'Nøgle oprettet';

  @override
  String get keyCreatedMessage =>
      'Din nye nøgle er blevet oprettet. Kopiér den venligst nu. Du vil ikke kunne se den igen.';

  @override
  String get keyWord => 'Nøgle';

  @override
  String get externalAppAccess => 'Ekstern app-adgang';

  @override
  String get externalAppAccessDescription =>
      'Følgende installerede apps har eksterne integrationer og kan få adgang til dine data, såsom samtaler og minder.';

  @override
  String get noExternalAppsHaveAccess => 'Ingen eksterne apps har adgang til dine data.';

  @override
  String get maximumSecurityE2ee => 'Maksimal sikkerhed (E2EE)';

  @override
  String get e2eeDescription =>
      'End-to-end-kryptering er guldstandarden for privatliv. Når det er aktiveret, krypteres dine data på din enhed, før de sendes til vores servere. Det betyder, at ingen, ikke engang Omi, kan få adgang til dit indhold.';

  @override
  String get importantTradeoffs => 'Vigtige kompromiser:';

  @override
  String get e2eeTradeoff1 => '• Nogle funktioner som eksterne app-integrationer kan være deaktiveret.';

  @override
  String get e2eeTradeoff2 => '• Hvis du mister din adgangskode, kan dine data ikke gendannes.';

  @override
  String get featureComingSoon => 'Denne funktion kommer snart!';

  @override
  String get migrationInProgressMessage =>
      'Migrering i gang. Du kan ikke ændre beskyttelsesniveauet, før det er fuldført.';

  @override
  String get migrationFailed => 'Migrering mislykkedes';

  @override
  String migratingFromTo(String source, String target) {
    return 'Migrerer fra $source til $target';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total objekter';
  }

  @override
  String get secureEncryption => 'Sikker kryptering';

  @override
  String get secureEncryptionDescription =>
      'Dine data er krypteret med en nøgle, der er unik for dig, på vores servere, der er hostet på Google Cloud. Det betyder, at dit rå indhold er utilgængeligt for alle, inklusive Omi-personale eller Google, direkte fra databasen.';

  @override
  String get endToEndEncryption => 'End-to-end-kryptering';

  @override
  String get e2eeCardDescription =>
      'Aktiver for maksimal sikkerhed, hvor kun du kan få adgang til dine data. Tryk for at lære mere.';

  @override
  String get dataAlwaysEncrypted => 'Uanset niveau er dine data altid krypteret i hvile og under overførsel.';

  @override
  String get readOnlyScope => 'Kun læsning';

  @override
  String get fullAccessScope => 'Fuld adgang';

  @override
  String get readScope => 'Læsning';

  @override
  String get writeScope => 'Skrivning';

  @override
  String get apiKeyCreated => 'API-nøgle oprettet!';

  @override
  String get saveKeyWarning => 'Gem denne nøgle nu! Du vil ikke kunne se den igen.';

  @override
  String get yourApiKey => 'DIN API-NØGLE';

  @override
  String get tapToCopy => 'Tryk for at kopiere';

  @override
  String get copyKey => 'Kopiér nøgle';

  @override
  String get createApiKey => 'Opret API-nøgle';

  @override
  String get accessDataProgrammatically => 'Få adgang til dine data programmatisk';

  @override
  String get keyNameLabel => 'NØGLENAVN';

  @override
  String get keyNamePlaceholder => 'f.eks. Min app-integration';

  @override
  String get permissionsLabel => 'TILLADELSER';

  @override
  String get permissionsInfoNote => 'R = Læs, W = Skriv. Standard kun læsning, hvis intet er valgt.';

  @override
  String get developerApi => 'Udvikler-API';

  @override
  String get createAKeyToGetStarted => 'Opret en nøgle for at komme i gang';

  @override
  String errorWithMessage(String error) {
    return 'Fejl: $error';
  }

  @override
  String get omiTraining => 'Omi Træning';

  @override
  String get trainingDataProgram => 'Træningsdataprogram';

  @override
  String get getOmiUnlimitedFree => 'Få Omi Unlimited gratis ved at bidrage med dine data til at træne AI-modeller.';

  @override
  String get trainingDataBullets =>
      '• Dine data hjælper med at forbedre AI-modeller\n• Kun ikke-følsomme data deles\n• Fuldstændig gennemsigtig proces';

  @override
  String get learnMoreAtOmiTraining => 'Lær mere på omi.me/training';

  @override
  String get agreeToContributeData => 'Jeg forstår og accepterer at bidrage med mine data til AI-træning';

  @override
  String get submitRequest => 'Send anmodning';

  @override
  String get thankYouRequestUnderReview =>
      'Tak! Din anmodning er under behandling. Vi giver dig besked, når den er godkendt.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'Dit abonnement forbliver aktivt indtil $date. Derefter mister du adgang til dine ubegrænsede funktioner. Er du sikker?';
  }

  @override
  String get confirmCancellation => 'Bekræft annullering';

  @override
  String get keepMyPlan => 'Behold mit abonnement';

  @override
  String get subscriptionSetToCancel => 'Dit abonnement er sat til at blive annulleret ved periodens udløb.';

  @override
  String get switchedToOnDevice => 'Skiftet til transskription på enheden';

  @override
  String get couldNotSwitchToFreePlan => 'Kunne ikke skifte til gratis abonnement. Prøv igen.';

  @override
  String get couldNotLoadPlans => 'Kunne ikke indlæse tilgængelige abonnementer. Prøv igen.';

  @override
  String get selectedPlanNotAvailable => 'Det valgte abonnement er ikke tilgængeligt. Prøv igen.';

  @override
  String get upgradeToAnnualPlan => 'Opgrader til årligt abonnement';

  @override
  String get importantBillingInfo => 'Vigtig faktureringsinformation:';

  @override
  String get monthlyPlanContinues =>
      'Dit nuværende månedlige abonnement fortsætter indtil udgangen af din faktureringsperiode';

  @override
  String get paymentMethodCharged =>
      'Din eksisterende betalingsmetode vil automatisk blive opkrævet, når dit månedlige abonnement udløber';

  @override
  String get annualSubscriptionStarts => 'Dit 12-måneders årlige abonnement starter automatisk efter opkrævningen';

  @override
  String get thirteenMonthsCoverage => 'Du får 13 måneders dækning i alt (nuværende måned + 12 måneder årligt)';

  @override
  String get confirmUpgrade => 'Bekræft opgradering';

  @override
  String get confirmPlanChange => 'Bekræft planændring';

  @override
  String get confirmAndProceed => 'Bekræft og fortsæt';

  @override
  String get upgradeScheduled => 'Opgradering planlagt';

  @override
  String get changePlan => 'Skift abonnement';

  @override
  String get upgradeAlreadyScheduled => 'Din opgradering til det årlige abonnement er allerede planlagt';

  @override
  String get youAreOnUnlimitedPlan => 'Du er på det ubegrænsede abonnement.';

  @override
  String get yourOmiUnleashed => 'Din Omi, frigjort. Bliv ubegrænset for uendelige muligheder.';

  @override
  String planEndedOn(String date) {
    return 'Dit abonnement sluttede $date.\\nGentilmeld dig nu - du vil straks blive opkrævet for en ny faktureringsperiode.';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'Dit abonnement er sat til at blive annulleret $date.\\nGentilmeld dig nu for at beholde dine fordele - ingen opkrævning indtil $date.';
  }

  @override
  String get annualPlanStartsAutomatically =>
      'Dit årlige abonnement starter automatisk, når dit månedlige abonnement slutter.';

  @override
  String planRenewsOn(String date) {
    return 'Dit abonnement fornyes $date.';
  }

  @override
  String get unlimitedConversations => 'Ubegrænsede samtaler';

  @override
  String get askOmiAnything => 'Spørg Omi om hvad som helst om dit liv';

  @override
  String get unlockOmiInfiniteMemory => 'Lås op for Omis uendelige hukommelse';

  @override
  String get youreOnAnnualPlan => 'Du er på det årlige abonnement';

  @override
  String get alreadyBestValuePlan => 'Du har allerede det bedste abonnement. Ingen ændringer nødvendige.';

  @override
  String get unableToLoadPlans => 'Kan ikke indlæse abonnementer';

  @override
  String get checkConnectionTryAgain => 'Tjek venligst din forbindelse og prøv igen';

  @override
  String get useFreePlan => 'Brug gratis abonnement';

  @override
  String get continueText => 'Fortsæt';

  @override
  String get resubscribe => 'Gentilmeld';

  @override
  String get couldNotOpenPaymentSettings => 'Kunne ikke åbne betalingsindstillinger. Prøv igen.';

  @override
  String get managePaymentMethod => 'Administrer betalingsmetode';

  @override
  String get cancelSubscription => 'Annuller abonnement';

  @override
  String endsOnDate(String date) {
    return 'Slutter $date';
  }

  @override
  String get active => 'Aktiv';

  @override
  String get freePlan => 'Gratis abonnement';

  @override
  String get configure => 'Konfigurer';

  @override
  String get privacyInformation => 'Fortrolighedsoplysninger';

  @override
  String get yourPrivacyMattersToUs => 'Dit privatliv er vigtigt for os';

  @override
  String get privacyIntroText =>
      'Hos Omi tager vi dit privatliv meget alvorligt. Vi ønsker at være transparente om de data, vi indsamler, og hvordan vi bruger dem til at forbedre vores produkt. Her er hvad du skal vide:';

  @override
  String get whatWeTrack => 'Hvad vi sporer';

  @override
  String get anonymityAndPrivacy => 'Anonymitet og privatliv';

  @override
  String get optInAndOptOutOptions => 'Tilvalg og fravalg';

  @override
  String get ourCommitment => 'Vores forpligtelse';

  @override
  String get commitmentText =>
      'Vi er forpligtet til kun at bruge de data, vi indsamler, til at gøre Omi til et bedre produkt for dig. Dit privatliv og din tillid er altafgørende for os.';

  @override
  String get thankYouText =>
      'Tak fordi du er en værdsat bruger af Omi. Hvis du har spørgsmål eller bekymringer, er du velkommen til at kontakte os på team@basedhardware.com.';

  @override
  String get wifiSyncSettings => 'WiFi-synkroniseringsindstillinger';

  @override
  String get enterHotspotCredentials => 'Indtast din telefons hotspot-legitimationsoplysninger';

  @override
  String get wifiSyncUsesHotspot =>
      'WiFi-synkronisering bruger din telefon som hotspot. Find dit hotspot-navn og adgangskode i Indstillinger > Personligt hotspot.';

  @override
  String get hotspotNameSsid => 'Hotspot-navn (SSID)';

  @override
  String get exampleIphoneHotspot => 'f.eks. iPhone Hotspot';

  @override
  String get password => 'Adgangskode';

  @override
  String get enterHotspotPassword => 'Indtast hotspot-adgangskode';

  @override
  String get saveCredentials => 'Gem legitimationsoplysninger';

  @override
  String get clearCredentials => 'Ryd legitimationsoplysninger';

  @override
  String get pleaseEnterHotspotName => 'Indtast venligst et hotspot-navn';

  @override
  String get wifiCredentialsSaved => 'WiFi-legitimationsoplysninger gemt';

  @override
  String get wifiCredentialsCleared => 'WiFi-legitimationsoplysninger ryddet';

  @override
  String summaryGeneratedForDate(String date) {
    return 'Resumé genereret for $date';
  }

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'Kunne ikke generere resumé. Sørg for, at du har samtaler for den dag.';

  @override
  String get summaryNotFound => 'Resumé ikke fundet';

  @override
  String get yourDaysJourney => 'Din dags rejse';

  @override
  String get highlights => 'Højdepunkter';

  @override
  String get unresolvedQuestions => 'Uløste spørgsmål';

  @override
  String get decisions => 'Beslutninger';

  @override
  String get learnings => 'Læringer';

  @override
  String get autoDeletesAfterThreeDays => 'Slettes automatisk efter 3 dage.';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'Videngraf slettet';

  @override
  String get exportStartedMayTakeFewSeconds => 'Eksport startet. Dette kan tage et par sekunder...';

  @override
  String get knowledgeGraphDeleteDescription =>
      'Dette vil slette alle afledte videngrafdata (noder og forbindelser). Dine originale minder forbliver sikre. Grafen vil blive genopbygget over tid eller ved næste anmodning.';

  @override
  String get configureDailySummaryDigest => 'Konfigurer dit daglige opgaveoversigt';

  @override
  String accessesDataTypes(String dataTypes) {
    return 'Adgang til $dataTypes';
  }

  @override
  String triggeredByType(String triggerType) {
    return 'udløst af $triggerType';
  }

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription og er $triggerDescription.';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return 'Er $triggerDescription.';
  }

  @override
  String get noSpecificDataAccessConfigured => 'Ingen specifik dataadgang konfigureret.';

  @override
  String get basicPlanDescription => '1.200 premium minutter + ubegrænset on-device';

  @override
  String get minutes => 'minutter';

  @override
  String get omiHas => 'Omi har:';

  @override
  String get premiumMinutesUsed => 'Premium minutter brugt.';

  @override
  String get setupOnDevice => 'Opsæt on-device';

  @override
  String get forUnlimitedFreeTranscription => 'for ubegrænset gratis transskription.';

  @override
  String premiumMinsLeft(int count) {
    return '$count premium minutter tilbage.';
  }

  @override
  String get alwaysAvailable => 'altid tilgængeligt.';

  @override
  String get importHistory => 'Importhistorik';

  @override
  String get noImportsYet => 'Ingen importer endnu';

  @override
  String get selectZipFileToImport => 'Vælg .zip-filen til import!';

  @override
  String get otherDevicesComingSoon => 'Andre enheder kommer snart';

  @override
  String get deleteAllLimitlessConversations => 'Slet alle Limitless samtaler?';

  @override
  String get deleteAllLimitlessWarning =>
      'Dette vil permanent slette alle samtaler importeret fra Limitless. Denne handling kan ikke fortrydes.';

  @override
  String deletedLimitlessConversations(int count) {
    return 'Slettet $count Limitless samtaler';
  }

  @override
  String get failedToDeleteConversations => 'Kunne ikke slette samtaler';

  @override
  String get deleteImportedData => 'Slet importerede data';

  @override
  String get statusPending => 'Afventer';

  @override
  String get statusProcessing => 'Behandler';

  @override
  String get statusCompleted => 'Fuldført';

  @override
  String get statusFailed => 'Fejlet';

  @override
  String nConversations(int count) {
    return '$count samtaler';
  }

  @override
  String get pleaseEnterName => 'Indtast venligst et navn';

  @override
  String get nameMustBeBetweenCharacters => 'Navnet skal være mellem 2 og 40 tegn';

  @override
  String get deleteSampleQuestion => 'Slet prøve?';

  @override
  String deleteSampleConfirmation(String name) {
    return 'Er du sikker på, at du vil slette ${name}s prøve?';
  }

  @override
  String get confirmDeletion => 'Bekræft sletning';

  @override
  String deletePersonConfirmation(String name) {
    return 'Er du sikker på, at du vil slette $name? Dette vil også fjerne alle tilknyttede taleprøver.';
  }

  @override
  String get howItWorksTitle => 'Hvordan virker det?';

  @override
  String get howPeopleWorks =>
      'Når en person er oprettet, kan du gå til en samtaleudskrift og tildele dem deres tilsvarende segmenter, på den måde vil Omi også kunne genkende deres tale!';

  @override
  String get tapToDelete => 'Tryk for at slette';

  @override
  String get newTag => 'NY';

  @override
  String get needHelpChatWithUs => 'Brug for hjælp? Chat med os';

  @override
  String get localStorageEnabled => 'Lokal lagring aktiveret';

  @override
  String get localStorageDisabled => 'Lokal lagring deaktiveret';

  @override
  String failedToUpdateSettings(String error) {
    return 'Kunne ikke opdatere indstillinger: $error';
  }

  @override
  String get privacyNotice => 'Fortrolighedsmeddelelse';

  @override
  String get recordingsMayCaptureOthers =>
      'Optagelser kan optage andres stemmer. Sørg for at have samtykke fra alle deltagere, før du aktiverer.';

  @override
  String get enable => 'Aktiver';

  @override
  String get storeAudioOnPhone => 'Gem lyd på telefonen';

  @override
  String get on => 'Til';

  @override
  String get storeAudioDescription =>
      'Behold alle lydoptagelser gemt lokalt på din telefon. Når deaktiveret, gemmes kun mislykkede uploads for at spare lagerplads.';

  @override
  String get enableLocalStorage => 'Aktiver lokal lagring';

  @override
  String get cloudStorageEnabled => 'Cloud-lagring aktiveret';

  @override
  String get cloudStorageDisabled => 'Cloud-lagring deaktiveret';

  @override
  String get enableCloudStorage => 'Aktiver cloud-lagring';

  @override
  String get storeAudioOnCloud => 'Gem lyd i skyen';

  @override
  String get cloudStorageDialogMessage => 'Dine optagelser i realtid gemmes i privat cloud-lagring, mens du taler.';

  @override
  String get storeAudioCloudDescription =>
      'Gem dine optagelser i realtid i privat cloud-lagring, mens du taler. Lyd optages og gemmes sikkert i realtid.';

  @override
  String get downloadingFirmware => 'Downloader firmware';

  @override
  String get installingFirmware => 'Installerer firmware';

  @override
  String get firmwareUpdateWarning => 'Luk ikke appen eller sluk enheden. Dette kan ødelægge din enhed.';

  @override
  String get firmwareUpdated => 'Firmware opdateret';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'Genstart venligst din $deviceName for at fuldføre opdateringen.';
  }

  @override
  String get yourDeviceIsUpToDate => 'Din enhed er opdateret';

  @override
  String get currentVersion => 'Nuværende version';

  @override
  String get latestVersion => 'Seneste version';

  @override
  String get whatsNew => 'Hvad er nyt';

  @override
  String get installUpdate => 'Installer opdatering';

  @override
  String get updateNow => 'Opdater nu';

  @override
  String get updateGuide => 'Opdateringsvejledning';

  @override
  String get checkingForUpdates => 'Søger efter opdateringer';

  @override
  String get checkingFirmwareVersion => 'Kontrollerer firmware-version...';

  @override
  String get firmwareUpdate => 'Firmwareopdatering';

  @override
  String get payments => 'Betalinger';

  @override
  String get connectPaymentMethodInfo =>
      'Tilslut en betalingsmetode nedenfor for at begynde at modtage udbetalinger for dine apps.';

  @override
  String get selectedPaymentMethod => 'Valgt betalingsmetode';

  @override
  String get availablePaymentMethods => 'Tilgængelige betalingsmetoder';

  @override
  String get activeStatus => 'Aktiv';

  @override
  String get connectedStatus => 'Forbundet';

  @override
  String get notConnectedStatus => 'Ikke forbundet';

  @override
  String get setActive => 'Sæt aktiv';

  @override
  String get getPaidThroughStripe => 'Få betaling for dine app-salg gennem Stripe';

  @override
  String get monthlyPayouts => 'Månedlige udbetalinger';

  @override
  String get monthlyPayoutsDescription =>
      'Modtag månedlige betalinger direkte til din konto, når du når \$10 i indtjening';

  @override
  String get secureAndReliable => 'Sikker og pålidelig';

  @override
  String get stripeSecureDescription => 'Stripe sikrer sikre og rettidige overførsler af dine app-indtægter';

  @override
  String get selectYourCountry => 'Vælg dit land';

  @override
  String get countrySelectionPermanent => 'Dit landevalg er permanent og kan ikke ændres senere.';

  @override
  String get byClickingConnectNow => 'Ved at klikke på \"Tilslut nu\" accepterer du';

  @override
  String get stripeConnectedAccountAgreement => 'Stripe Connected Account-aftale';

  @override
  String get errorConnectingToStripe => 'Fejl ved tilslutning til Stripe! Prøv venligst igen senere.';

  @override
  String get connectingYourStripeAccount => 'Tilslutter din Stripe-konto';

  @override
  String get stripeOnboardingInstructions =>
      'Fuldfør venligst Stripe-onboarding-processen i din browser. Denne side opdateres automatisk, når den er fuldført.';

  @override
  String get failedTryAgain => 'Mislykkedes? Prøv igen';

  @override
  String get illDoItLater => 'Jeg gør det senere';

  @override
  String get successfullyConnected => 'Succesfuldt forbundet!';

  @override
  String get stripeReadyForPayments =>
      'Din Stripe-konto er nu klar til at modtage betalinger. Du kan begynde at tjene på dine app-salg med det samme.';

  @override
  String get updateStripeDetails => 'Opdater Stripe-detaljer';

  @override
  String get errorUpdatingStripeDetails => 'Fejl ved opdatering af Stripe-detaljer! Prøv venligst igen senere.';

  @override
  String get updatePayPal => 'Opdater PayPal';

  @override
  String get setUpPayPal => 'Konfigurer PayPal';

  @override
  String get updatePayPalAccountDetails => 'Opdater dine PayPal-kontooplysninger';

  @override
  String get connectPayPalToReceivePayments =>
      'Tilslut din PayPal-konto for at begynde at modtage betalinger for dine apps';

  @override
  String get paypalEmail => 'PayPal e-mail';

  @override
  String get paypalMeLink => 'PayPal.me link';

  @override
  String get stripeRecommendation =>
      'Hvis Stripe er tilgængelig i dit land, anbefaler vi stærkt at bruge det til hurtigere og nemmere udbetalinger.';

  @override
  String get updatePayPalDetails => 'Opdater PayPal-detaljer';

  @override
  String get savePayPalDetails => 'Gem PayPal-detaljer';

  @override
  String get pleaseEnterPayPalEmail => 'Indtast venligst din PayPal e-mail';

  @override
  String get pleaseEnterPayPalMeLink => 'Indtast venligst dit PayPal.me link';

  @override
  String get doNotIncludeHttpInLink => 'Inkluder ikke http eller https eller www i linket';

  @override
  String get pleaseEnterValidPayPalMeLink => 'Indtast venligst et gyldigt PayPal.me link';

  @override
  String get pleaseEnterValidEmail => 'Indtast venligst en gyldig e-mailadresse';

  @override
  String get syncingYourRecordings => 'Synkroniserer dine optagelser';

  @override
  String get syncYourRecordings => 'Synkroniser dine optagelser';

  @override
  String get syncNow => 'Synkroniser nu';

  @override
  String get error => 'Fejl';

  @override
  String get speechSamples => 'Stemmeprøver';

  @override
  String additionalSampleIndex(String index) {
    return 'Yderligere prøve $index';
  }

  @override
  String durationSeconds(String seconds) {
    return 'Varighed: $seconds sekunder';
  }

  @override
  String get additionalSpeechSampleRemoved => 'Yderligere stemmeprøve fjernet';

  @override
  String get consentDataMessage =>
      'Ved at fortsætte vil alle data, du deler med denne app (inklusive dine samtaler, optagelser og personlige oplysninger), blive sikkert gemt på vores servere for at give dig AI-drevne indsigter og aktivere alle app-funktioner.';

  @override
  String get tasksEmptyStateMessage => 'Opgaver fra dine samtaler vises her.\nTryk på + for at oprette en manuelt.';

  @override
  String get clearChatAction => 'Ryd chat';

  @override
  String get enableApps => 'Aktivér apps';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => 'vis mere ↓';

  @override
  String get showLess => 'vis mindre ↑';

  @override
  String get loadingYourRecording => 'Indlæser din optagelse...';

  @override
  String get photoDiscardedMessage => 'Dette foto blev kasseret, da det ikke var betydningsfuldt.';

  @override
  String get analyzing => 'Analyserer...';

  @override
  String get searchCountries => 'Søg lande...';

  @override
  String get checkingAppleWatch => 'Tjekker Apple Watch...';

  @override
  String get installOmiOnAppleWatch => 'Installer Omi på dit\nApple Watch';

  @override
  String get installOmiOnAppleWatchDescription =>
      'For at bruge dit Apple Watch med Omi skal du først installere Omi-appen på dit ur.';

  @override
  String get openOmiOnAppleWatch => 'Åbn Omi på dit\nApple Watch';

  @override
  String get openOmiOnAppleWatchDescription =>
      'Omi-appen er installeret på dit Apple Watch. Åbn den og tryk på Start for at begynde.';

  @override
  String get openWatchApp => 'Åbn Watch-appen';

  @override
  String get iveInstalledAndOpenedTheApp => 'Jeg har installeret og åbnet appen';

  @override
  String get unableToOpenWatchApp =>
      'Kunne ikke åbne Apple Watch-appen. Åbn manuelt Watch-appen på dit Apple Watch og installer Omi fra sektionen \"Tilgængelige apps\".';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch tilsluttet!';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch er stadig ikke tilgængeligt. Sørg for, at Omi-appen er åben på dit ur.';

  @override
  String errorCheckingConnection(String error) {
    return 'Fejl ved kontrol af forbindelse: $error';
  }

  @override
  String get muted => 'Lydløs';

  @override
  String get processNow => 'Behandl nu';

  @override
  String get finishedConversation => 'Samtale afsluttet?';

  @override
  String get stopRecordingConfirmation => 'Er du sikker på, at du vil stoppe optagelsen og opsummere samtalen nu?';

  @override
  String get conversationEndsManually => 'Samtalen afsluttes kun manuelt.';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'Samtalen opsummeres efter $minutes minut$suffix uden tale.';
  }

  @override
  String get dontAskAgain => 'Spørg mig ikke igen';

  @override
  String get waitingForTranscriptOrPhotos => 'Venter på transskription eller billeder...';

  @override
  String get noSummaryYet => 'Intet resumé endnu';

  @override
  String hints(String text) {
    return 'Tips';
  }

  @override
  String get testConversationPrompt => 'Test en samtale prompt';

  @override
  String get prompt => 'Prompt';

  @override
  String get result => 'Resultat:';

  @override
  String get compareTranscripts => 'Sammenlign transskriptioner';

  @override
  String get notHelpful => 'Ikke nyttigt';

  @override
  String get exportTasksWithOneTap => 'Eksporter opgaver med ét tryk!';

  @override
  String get inProgress => 'I gang';

  @override
  String get photos => 'Fotos';

  @override
  String get rawData => 'Rådata';

  @override
  String get content => 'Indhold';

  @override
  String get noContentToDisplay => 'Intet indhold at vise';

  @override
  String get noSummary => 'Ingen oversigt';

  @override
  String get updateOmiFirmware => 'Opdater omi-firmware';

  @override
  String get anErrorOccurredTryAgain => 'Der opstod en fejl. Prøv venligst igen.';

  @override
  String get welcomeBackSimple => 'Velkommen tilbage';

  @override
  String get addVocabularyDescription => 'Tilføj ord, som Omi skal genkende under transskription.';

  @override
  String get enterWordsCommaSeparated => 'Indtast ord (adskilt af komma)';

  @override
  String get whenToReceiveDailySummary => 'Hvornår du vil modtage dit daglige resumé';

  @override
  String get checkingNextSevenDays => 'Tjekker de næste 7 dage';

  @override
  String failedToDeleteError(String error) {
    return 'Kunne ikke slette: $error';
  }

  @override
  String get developerApiKeys => 'Udvikler API-nøgler';

  @override
  String get noApiKeysCreateOne => 'Ingen API-nøgler. Opret en for at komme i gang.';

  @override
  String get commandRequired => '⌘ påkrævet';

  @override
  String get spaceKey => 'Mellemrum';

  @override
  String loadMoreRemaining(String count) {
    return 'Indlæs mere ($count tilbage)';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'Top $percentile% bruger';
  }

  @override
  String get wrappedMinutes => 'minutter';

  @override
  String get wrappedConversations => 'samtaler';

  @override
  String get wrappedDaysActive => 'aktive dage';

  @override
  String get wrappedYouTalkedAbout => 'Du talte om';

  @override
  String get wrappedActionItems => 'Handlingspunkter';

  @override
  String get wrappedTasksCreated => 'oprettede opgaver';

  @override
  String get wrappedCompleted => 'fuldført';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% fuldførelsesrate';
  }

  @override
  String get wrappedYourTopDays => 'Dine bedste dage';

  @override
  String get wrappedBestMoments => 'Bedste øjeblikke';

  @override
  String get wrappedMyBuddies => 'Mine venner';

  @override
  String get wrappedCouldntStopTalkingAbout => 'Kunne ikke stoppe med at tale om';

  @override
  String get wrappedShow => 'SERIE';

  @override
  String get wrappedMovie => 'FILM';

  @override
  String get wrappedBook => 'BOG';

  @override
  String get wrappedCelebrity => 'KENDIS';

  @override
  String get wrappedFood => 'MAD';

  @override
  String get wrappedMovieRecs => 'Filmanbefalinger til venner';

  @override
  String get wrappedBiggest => 'Største';

  @override
  String get wrappedStruggle => 'Udfordring';

  @override
  String get wrappedButYouPushedThrough => 'Men du klarede det 💪';

  @override
  String get wrappedWin => 'Sejr';

  @override
  String get wrappedYouDidIt => 'Du klarede det! 🎉';

  @override
  String get wrappedTopPhrases => 'Top 5 sætninger';

  @override
  String get wrappedMins => 'min';

  @override
  String get wrappedConvos => 'samtaler';

  @override
  String get wrappedDays => 'dage';

  @override
  String get wrappedMyBuddiesLabel => 'MINE VENNER';

  @override
  String get wrappedObsessionsLabel => 'OBSESSIONER';

  @override
  String get wrappedStruggleLabel => 'UDFORDRING';

  @override
  String get wrappedWinLabel => 'SEJR';

  @override
  String get wrappedTopPhrasesLabel => 'TOP SÆTNINGER';

  @override
  String get wrappedLetsHitRewind => 'Lad os spole tilbage på din';

  @override
  String get wrappedGenerateMyWrapped => 'Generer min Wrapped';

  @override
  String get wrappedProcessingDefault => 'Behandler...';

  @override
  String get wrappedCreatingYourStory => 'Skaber din\n2025 historie...';

  @override
  String get wrappedSomethingWentWrong => 'Noget gik\ngalt';

  @override
  String get wrappedAnErrorOccurred => 'Der opstod en fejl';

  @override
  String get wrappedTryAgain => 'Prøv igen';

  @override
  String get wrappedNoDataAvailable => 'Ingen data tilgængelig';

  @override
  String get wrappedOmiLifeRecap => 'Omi livsopsummering';

  @override
  String get wrappedSwipeUpToBegin => 'Swipe op for at begynde';

  @override
  String get wrappedShareText => 'Min 2025, husket af Omi ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare => 'Deling mislykkedes. Prøv venligst igen.';

  @override
  String get wrappedFailedToStartGeneration => 'Start af generering mislykkedes. Prøv venligst igen.';

  @override
  String get wrappedStarting => 'Starter...';

  @override
  String get wrappedShare => 'Del';

  @override
  String get wrappedShareYourWrapped => 'Del din Wrapped';

  @override
  String get wrappedMy2025 => 'Min 2025';

  @override
  String get wrappedRememberedByOmi => 'husket af Omi';

  @override
  String get wrappedMostFunDay => 'Sjovest';

  @override
  String get wrappedMostProductiveDay => 'Mest produktiv';

  @override
  String get wrappedMostIntenseDay => 'Mest intens';

  @override
  String get wrappedFunniestMoment => 'Sjoveste';

  @override
  String get wrappedMostCringeMoment => 'Mest pinlig';

  @override
  String get wrappedMinutesLabel => 'minutter';

  @override
  String get wrappedConversationsLabel => 'samtaler';

  @override
  String get wrappedDaysActiveLabel => 'aktive dage';

  @override
  String get wrappedTasksGenerated => 'opgaver genereret';

  @override
  String get wrappedTasksCompleted => 'opgaver fuldført';

  @override
  String get wrappedTopFivePhrases => 'Top 5 sætninger';

  @override
  String get wrappedAGreatDay => 'En fantastisk dag';

  @override
  String get wrappedGettingItDone => 'Få det gjort';

  @override
  String get wrappedAChallenge => 'En udfordring';

  @override
  String get wrappedAHilariousMoment => 'Et sjovt øjeblik';

  @override
  String get wrappedThatAwkwardMoment => 'Det pinlige øjeblik';

  @override
  String get wrappedYouHadFunnyMoments => 'Du havde sjove øjeblikke i år!';

  @override
  String get wrappedWeveAllBeenThere => 'Vi har alle været der!';

  @override
  String get wrappedFriend => 'Ven';

  @override
  String get wrappedYourBuddy => 'Din ven!';

  @override
  String get wrappedNotMentioned => 'Ikke nævnt';

  @override
  String get wrappedTheHardPart => 'Den svære del';

  @override
  String get wrappedPersonalGrowth => 'Personlig vækst';

  @override
  String get wrappedFunDay => 'Sjov';

  @override
  String get wrappedProductiveDay => 'Produktiv';

  @override
  String get wrappedIntenseDay => 'Intens';

  @override
  String get wrappedFunnyMomentTitle => 'Sjovt øjeblik';

  @override
  String get wrappedCringeMomentTitle => 'Pinligt øjeblik';

  @override
  String get wrappedYouTalkedAboutBadge => 'Du talte om';

  @override
  String get wrappedCompletedLabel => 'Fuldført';

  @override
  String get wrappedMyBuddiesCard => 'Mine venner';

  @override
  String get wrappedBuddiesLabel => 'VENNER';

  @override
  String get wrappedObsessionsLabelUpper => 'OBSESSIONER';

  @override
  String get wrappedStruggleLabelUpper => 'KAMP';

  @override
  String get wrappedWinLabelUpper => 'SEJR';

  @override
  String get wrappedTopPhrasesLabelUpper => 'TOP SÆTNINGER';

  @override
  String get wrappedYourHeader => 'Dine';

  @override
  String get wrappedTopDaysHeader => 'Bedste dage';

  @override
  String get wrappedYourTopDaysBadge => 'Dine bedste dage';

  @override
  String get wrappedBestHeader => 'Bedste';

  @override
  String get wrappedMomentsHeader => 'Øjeblikke';

  @override
  String get wrappedBestMomentsBadge => 'Bedste øjeblikke';

  @override
  String get wrappedBiggestHeader => 'Største';

  @override
  String get wrappedStruggleHeader => 'Kamp';

  @override
  String get wrappedWinHeader => 'Sejr';

  @override
  String get wrappedButYouPushedThroughEmoji => 'Men du klarede det 💪';

  @override
  String get wrappedYouDidItEmoji => 'Du gjorde det! 🎉';

  @override
  String get wrappedHours => 'timer';

  @override
  String get wrappedActions => 'handlinger';

  @override
  String get multipleSpeakersDetected => 'Flere talere registreret';

  @override
  String get multipleSpeakersDescription =>
      'Det ser ud til, at der er flere talere i optagelsen. Sørg for, at du er et roligt sted, og prøv igen.';

  @override
  String get invalidRecordingDetected => 'Ugyldig optagelse registreret';

  @override
  String get notEnoughSpeechDescription => 'Der er ikke registreret nok tale. Tal venligst mere og prøv igen.';

  @override
  String get speechDurationDescription => 'Sørg for, at du taler i mindst 5 sekunder og ikke mere end 90.';

  @override
  String get connectionLostDescription => 'Forbindelsen blev afbrudt. Tjek din internetforbindelse og prøv igen.';

  @override
  String get howToTakeGoodSample => 'Hvordan tager man en god prøve?';

  @override
  String get goodSampleInstructions =>
      '1. Sørg for, at du er et roligt sted.\n2. Tal tydeligt og naturligt.\n3. Sørg for, at din enhed er i sin naturlige position på din hals.\n\nNår den er oprettet, kan du altid forbedre den eller gøre det igen.';

  @override
  String get noDeviceConnectedUseMic => 'Ingen enhed tilsluttet. Telefonens mikrofon bruges.';

  @override
  String get doItAgain => 'Gør det igen';

  @override
  String get listenToSpeechProfile => 'Lyt til min stemmeprofil ➡️';

  @override
  String get recognizingOthers => 'Genkender andre 👀';

  @override
  String get keepGoingGreat => 'Bliv ved, du klarer det godt';

  @override
  String get somethingWentWrongTryAgain => 'Noget gik galt! Prøv venligst igen senere.';

  @override
  String get uploadingVoiceProfile => 'Uploader din stemmeprofil....';

  @override
  String get memorizingYourVoice => 'Husker din stemme...';

  @override
  String get personalizingExperience => 'Tilpasser din oplevelse...';

  @override
  String get keepSpeakingUntil100 => 'Bliv ved med at tale indtil du når 100%.';

  @override
  String get greatJobAlmostThere => 'Godt arbejde, du er næsten i mål';

  @override
  String get soCloseJustLittleMore => 'Så tæt på, bare lidt mere';

  @override
  String get notificationFrequency => 'Notifikationsfrekvens';

  @override
  String get controlNotificationFrequency => 'Kontroller, hvor ofte Omi sender dig proaktive notifikationer.';

  @override
  String get yourScore => 'Din score';

  @override
  String get dailyScoreBreakdown => 'Daglig score oversigt';

  @override
  String get todaysScore => 'Dagens score';

  @override
  String get tasksCompleted => 'Opgaver fuldført';

  @override
  String get completionRate => 'Fuldførelsesrate';

  @override
  String get howItWorks => 'Sådan fungerer det';

  @override
  String get dailyScoreExplanation =>
      'Din daglige score er baseret på opgavefuldførelse. Fuldfør dine opgaver for at forbedre din score!';

  @override
  String get notificationFrequencyDescription =>
      'Kontroller hvor ofte Omi sender dig proaktive notifikationer og påmindelser.';

  @override
  String get sliderOff => 'Fra';

  @override
  String get sliderMax => 'Maks.';

  @override
  String summaryGeneratedFor(String date) {
    return 'Opsummering genereret for $date';
  }

  @override
  String get failedToGenerateSummary => 'Kunne ikke generere opsummering. Sørg for at du har samtaler for den dag.';

  @override
  String get recap => 'Resumé';

  @override
  String deleteQuoted(String name) {
    return 'Slet \"$name\"';
  }

  @override
  String moveConversationsTo(int count) {
    return 'Flyt $count samtaler til:';
  }

  @override
  String get noFolder => 'Ingen mappe';

  @override
  String get removeFromAllFolders => 'Fjern fra alle mapper';

  @override
  String get buildAndShareYourCustomApp => 'Byg og del din tilpassede app';

  @override
  String get searchAppsPlaceholder => 'Søg i 1500+ apps';

  @override
  String get filters => 'Filtre';

  @override
  String get frequencyOff => 'Fra';

  @override
  String get frequencyMinimal => 'Minimal';

  @override
  String get frequencyLow => 'Lav';

  @override
  String get frequencyBalanced => 'Balanceret';

  @override
  String get frequencyHigh => 'Høj';

  @override
  String get frequencyMaximum => 'Maksimal';

  @override
  String get frequencyDescOff => 'Ingen proaktive notifikationer';

  @override
  String get frequencyDescMinimal => 'Kun kritiske påmindelser';

  @override
  String get frequencyDescLow => 'Kun vigtige opdateringer';

  @override
  String get frequencyDescBalanced => 'Regelmæssige nyttige påmindelser';

  @override
  String get frequencyDescHigh => 'Hyppige tjek';

  @override
  String get frequencyDescMaximum => 'Forbliv konstant engageret';

  @override
  String get clearChatQuestion => 'Ryd chat?';

  @override
  String get syncingMessages => 'Synkroniserer beskeder med serveren...';

  @override
  String get chatAppsTitle => 'Chat apps';

  @override
  String get selectApp => 'Vælg app';

  @override
  String get noChatAppsEnabled => 'Ingen chat apps aktiveret.\nTryk på \"Aktiver apps\" for at tilføje.';

  @override
  String get disable => 'Deaktiver';

  @override
  String get photoLibrary => 'Billedbibliotek';

  @override
  String get chooseFile => 'Vælg fil';

  @override
  String get configureAiPersona => 'Konfigurer din AI-persona';

  @override
  String get connectAiAssistantsToYourData => 'Forbind AI-assistenter til dine data';

  @override
  String get oAuth => 'OAuth';

  @override
  String get trackYourGoalsOnHomepage => 'Følg dine mål på startsiden';

  @override
  String get deleteRecording => 'Slet optagelse';

  @override
  String get thisCannotBeUndone => 'Dette kan ikke fortrydes.';

  @override
  String get sdCard => 'SD-kort';

  @override
  String get fromSd => 'Fra SD';

  @override
  String get limitless => 'Ubegrænset';

  @override
  String get fastTransfer => 'Hurtig overførsel';

  @override
  String get syncingStatus => 'Synkroniserer';

  @override
  String get failedStatus => 'Mislykket';

  @override
  String etaLabel(String time) {
    return 'Estimeret tid';
  }

  @override
  String get transferMethod => 'Overførselsmetode';

  @override
  String get fast => 'Hurtig';

  @override
  String get ble => 'BLE';

  @override
  String get phone => 'Telefon';

  @override
  String get cancelSync => 'Annuller synkronisering';

  @override
  String get cancelSyncMessage => 'Allerede downloadede data gemmes. Du kan genoptage senere.';

  @override
  String get syncCancelled => 'Synkronisering annulleret';

  @override
  String get deleteProcessedFiles => 'Slet behandlede filer';

  @override
  String get processedFilesDeleted => 'Behandlede filer slettet';

  @override
  String get wifiEnableFailed => 'Kunne ikke aktivere WiFi på enheden. Prøv venligst igen.';

  @override
  String get deviceNoFastTransfer => 'Enheden understøtter ikke hurtig overførsel';

  @override
  String get enableHotspotMessage => 'Aktivér venligst hotspot på din telefon for at fortsætte';

  @override
  String get transferStartFailed => 'Kunne ikke starte overførsel. Prøv venligst igen.';

  @override
  String get deviceNotResponding => 'Enheden reagerer ikke. Prøv venligst igen.';

  @override
  String get invalidWifiCredentials => 'Ugyldige WiFi-legitimationsoplysninger';

  @override
  String get wifiConnectionFailed => 'WiFi-forbindelse mislykkedes';

  @override
  String get sdCardProcessing => 'SD-kort behandles';

  @override
  String sdCardProcessingMessage(int count) {
    return 'Behandler $count optagelse(r). Filer fjernes fra SD-kortet bagefter.';
  }

  @override
  String get process => 'Behandl';

  @override
  String get wifiSyncFailed => 'WiFi-synkronisering mislykkedes';

  @override
  String get processingFailed => 'Behandling mislykkedes';

  @override
  String get downloadingFromSdCard => 'Downloader fra SD-kort';

  @override
  String processingProgress(int current, int total) {
    return 'Behandler $current af $total';
  }

  @override
  String conversationsCreated(int count) {
    return 'Samtaler oprettet';
  }

  @override
  String get internetRequired => 'Internetforbindelse påkrævet';

  @override
  String get processAudio => 'Behandl lyd';

  @override
  String get start => 'Start';

  @override
  String get noRecordings => 'Ingen optagelser';

  @override
  String get audioFromOmiWillAppearHere => 'Lyd fra Omi vises her';

  @override
  String get deleteProcessed => 'Slet behandlede';

  @override
  String get tryDifferentFilter => 'Prøv et andet filter';

  @override
  String get recordings => 'Optagelser';

  @override
  String get enableRemindersAccess =>
      'Aktivér venligst påmindelsesadgang i Indstillinger for at bruge Apple Påmindelser';

  @override
  String todayAtTime(String time) {
    return 'I dag kl. $time';
  }

  @override
  String yesterdayAtTime(String time) {
    return 'I går kl. $time';
  }

  @override
  String get lessThanAMinute => 'Mindre end et minut';

  @override
  String estimatedMinutes(int count) {
    return '~$count minut(ter)';
  }

  @override
  String estimatedHours(int count) {
    return '~$count time(r)';
  }

  @override
  String estimatedTimeRemaining(String time) {
    return 'Anslået: $time tilbage';
  }

  @override
  String get summarizingConversation => 'Opsummerer samtale...\nDette kan tage et par sekunder';

  @override
  String get resummarizingConversation => 'Gen-opsummerer samtale...\nDette kan tage et par sekunder';

  @override
  String get nothingInterestingRetry => 'Intet interessant fundet,\nvil du prøve igen?';

  @override
  String get noSummaryForConversation => 'Ingen opsummering tilgængelig\nfor denne samtale.';

  @override
  String get unknownLocation => 'Ukendt placering';

  @override
  String get couldNotLoadMap => 'Kunne ikke indlæse kort';

  @override
  String get triggerConversationIntegration => 'Udløs samtale oprettet integration';

  @override
  String get webhookUrlNotSet => 'Webhook URL ikke angivet';

  @override
  String get setWebhookUrlInSettings =>
      'Angiv venligst webhook URL i udviklerindstillinger for at bruge denne funktion.';

  @override
  String get sendWebUrl => 'Send web URL';

  @override
  String get sendTranscript => 'Send transskription';

  @override
  String get sendSummary => 'Send opsummering';

  @override
  String get debugModeDetected => 'Fejlretningstilstand registreret';

  @override
  String get performanceReduced => 'Ydeevne reduceret 5-10x. Brug Release-tilstand.';

  @override
  String autoClosingInSeconds(int seconds) {
    return 'Lukker automatisk om ${seconds}s';
  }

  @override
  String get modelRequired => 'Model påkrævet';

  @override
  String get downloadWhisperModel => 'Download venligst en Whisper-model før du gemmer.';

  @override
  String get deviceNotCompatible => 'Enhed ikke kompatibel';

  @override
  String get deviceRequirements => 'Din enhed opfylder ikke kravene til lokal transskription.';

  @override
  String get willLikelyCrash => 'Aktivering vil sandsynligvis få appen til at gå ned eller fryse.';

  @override
  String get transcriptionSlowerLessAccurate => 'Transskription vil være markant langsommere og mindre præcis.';

  @override
  String get proceedAnyway => 'Fortsæt alligevel';

  @override
  String get olderDeviceDetected => 'Ældre enhed registreret';

  @override
  String get onDeviceSlower => 'Lokal transskription kan være langsommere på denne enhed.';

  @override
  String get batteryUsageHigher => 'Batteriforbrug vil være højere end cloud-transskription.';

  @override
  String get considerOmiCloud => 'Overvej at bruge Omi Cloud for bedre ydeevne.';

  @override
  String get highResourceUsage => 'Højt ressourceforbrug';

  @override
  String get onDeviceIntensive => 'Lokal transskription er beregningskrævende.';

  @override
  String get batteryDrainIncrease => 'Batteriforbrug vil stige betydeligt.';

  @override
  String get deviceMayWarmUp => 'Enheden kan blive varm ved længere brug.';

  @override
  String get speedAccuracyLower => 'Hastighed og nøjagtighed kan være lavere end cloud-modeller.';

  @override
  String get cloudProvider => 'Cloud-udbyder';

  @override
  String get premiumMinutesInfo =>
      '1.200 premium minutter/måned. Lokal-fanen tilbyder ubegrænset gratis transskription.';

  @override
  String get viewUsage => 'Se forbrug';

  @override
  String get localProcessingInfo => 'Lyd behandles lokalt. Fungerer offline, mere privat, men bruger mere batteri.';

  @override
  String get model => 'Model';

  @override
  String get performanceWarning => 'Ydelsesadvarsel';

  @override
  String get largeModelWarning =>
      'Denne model er stor og kan få appen til at gå ned eller køre meget langsomt på mobile enheder.\n\n\"small\" eller \"base\" anbefales.';

  @override
  String get usingNativeIosSpeech => 'Bruger indbygget iOS-talegenkendelse';

  @override
  String get noModelDownloadRequired =>
      'Din enheds indbyggede talegenkendelse vil blive brugt. Ingen model-download påkrævet.';

  @override
  String get modelReady => 'Model klar';

  @override
  String get redownload => 'Download igen';

  @override
  String get doNotCloseApp => 'Luk venligst ikke appen.';

  @override
  String get downloading => 'Downloader...';

  @override
  String get downloadModel => 'Download model';

  @override
  String estimatedSize(String size) {
    return 'Anslået størrelse: ~$size MB';
  }

  @override
  String availableSpace(String space) {
    return 'Tilgængelig plads: $space';
  }

  @override
  String get notEnoughSpace => 'Advarsel: Ikke nok plads!';

  @override
  String get download => 'Download';

  @override
  String downloadError(String error) {
    return 'Downloadfejl: $error';
  }

  @override
  String get cancelled => 'Annulleret';

  @override
  String get deviceNotCompatibleTitle => 'Enhed ikke kompatibel';

  @override
  String get deviceNotMeetRequirements => 'Din enhed opfylder ikke kravene til transskription på enheden.';

  @override
  String get transcriptionSlowerOnDevice => 'Transskription på enheden kan være langsommere på denne enhed.';

  @override
  String get computationallyIntensive => 'Transskription på enheden er beregningsintensiv.';

  @override
  String get batteryDrainSignificantly => 'Batteriforbrug vil øges betydeligt.';

  @override
  String get premiumMinutesMonth =>
      '1.200 premium minutter/måned. Fanen På enheden tilbyder ubegrænset gratis transskription. ';

  @override
  String get audioProcessedLocally => 'Lyd behandles lokalt. Fungerer offline, mere privat, men bruger mere batteri.';

  @override
  String get languageLabel => 'Sprog';

  @override
  String get modelLabel => 'Model';

  @override
  String get modelTooLargeWarning =>
      'Denne model er stor og kan få appen til at gå ned eller køre meget langsomt på mobile enheder.\n\nsmall eller base anbefales.';

  @override
  String get nativeEngineNoDownload =>
      'Din enheds indbyggede talemotor vil blive brugt. Ingen model-download påkrævet.';

  @override
  String modelReadyWithName(String model) {
    return 'Model klar ($model)';
  }

  @override
  String get reDownload => 'Download igen';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return 'Downloader $model: $received / $total MB';
  }

  @override
  String preparingModel(String model) {
    return 'Forbereder $model...';
  }

  @override
  String downloadErrorWithMessage(String error) {
    return 'Downloadfejl: $error';
  }

  @override
  String estimatedSizeWithValue(String size) {
    return 'Anslået størrelse: ~$size MB';
  }

  @override
  String availableSpaceWithValue(String space) {
    return 'Tilgængelig plads: $space';
  }

  @override
  String get omiTranscriptionOptimized =>
      'Omis indbyggede live-transskription er optimeret til samtaler i realtid med automatisk talerdetektering og diarization.';

  @override
  String get reset => 'Nulstil';

  @override
  String get useTemplateFrom => 'Brug skabelon fra';

  @override
  String get selectProviderTemplate => 'Vælg en udbyders skabelon...';

  @override
  String get quicklyPopulateResponse => 'Udfyld hurtigt med en kendt udbyders svarformat';

  @override
  String get quicklyPopulateRequest => 'Udfyld hurtigt med en kendt udbyders anmodningsformat';

  @override
  String get invalidJsonError => 'Ugyldig JSON';

  @override
  String downloadModelWithName(String model) {
    return 'Download model ($model)';
  }

  @override
  String modelNameWithFile(String model) {
    return 'Modelnavn med fil';
  }

  @override
  String get device => 'Enhed';

  @override
  String get chatAssistantsTitle => 'Chat-assistenter';

  @override
  String get permissionReadConversations => 'Læs samtaler';

  @override
  String get permissionReadMemories => 'Læs minder';

  @override
  String get permissionReadTasks => 'Læs opgaver';

  @override
  String get permissionCreateConversations => 'Opret samtaler';

  @override
  String get permissionCreateMemories => 'Opret minder';

  @override
  String get permissionTypeAccess => 'Adgang';

  @override
  String get permissionTypeCreate => 'Opret';

  @override
  String get permissionTypeTrigger => 'Udløser';

  @override
  String get permissionDescReadConversations => 'Denne app kan få adgang til dine samtaler.';

  @override
  String get permissionDescReadMemories => 'Denne app kan få adgang til dine minder.';

  @override
  String get permissionDescReadTasks => 'Denne app kan få adgang til dine opgaver.';

  @override
  String get permissionDescCreateConversations => 'Denne app kan oprette nye samtaler.';

  @override
  String get permissionDescCreateMemories => 'Denne app kan oprette nye minder.';

  @override
  String get realtimeListening => 'Realtidslytning';

  @override
  String get setupCompleted => 'Fuldført';

  @override
  String get pleaseSelectRating => 'Vælg venligst en bedømmelse';

  @override
  String get writeReviewOptional => 'Skriv en anmeldelse (valgfrit)';

  @override
  String get setupQuestionsIntro => 'Lad os lære dig lidt bedre at kende';

  @override
  String get setupQuestionProfession => 'Hvad er dit erhverv?';

  @override
  String get setupQuestionUsage => 'Hvor vil du bruge Omi?';

  @override
  String get setupQuestionAge => 'Hvad er din alder?';

  @override
  String get setupAnswerAllQuestions => 'Besvar venligst alle spørgsmål';

  @override
  String get setupSkipHelp => 'Spring over for nu';

  @override
  String get professionEntrepreneur => 'Iværksætter';

  @override
  String get professionSoftwareEngineer => 'Softwareingeniør';

  @override
  String get professionProductManager => 'Produktchef';

  @override
  String get professionExecutive => 'Direktør';

  @override
  String get professionSales => 'Salg';

  @override
  String get professionStudent => 'Studerende';

  @override
  String get usageAtWork => 'På arbejde';

  @override
  String get usageIrlEvents => 'IRL-begivenheder';

  @override
  String get usageOnline => 'Online';

  @override
  String get usageSocialSettings => 'Sociale sammenhænge';

  @override
  String get usageEverywhere => 'Overalt';

  @override
  String get customBackendUrlTitle => 'Tilpasset backend-URL';

  @override
  String get backendUrlLabel => 'Backend-URL';

  @override
  String get saveUrlButton => 'Gem URL';

  @override
  String get enterBackendUrlError => 'Indtast venligst backend-URL';

  @override
  String get urlMustEndWithSlashError => 'URL skal ende med \"/\"';

  @override
  String get invalidUrlError => 'Indtast venligst en gyldig URL';

  @override
  String get backendUrlSavedSuccess => 'Backend-URL gemt!';

  @override
  String get signInTitle => 'Log ind';

  @override
  String get signInButton => 'Log ind';

  @override
  String get enterEmailError => 'Indtast venligst din e-mail';

  @override
  String get invalidEmailError => 'Indtast venligst en gyldig e-mail';

  @override
  String get enterPasswordError => 'Indtast venligst din adgangskode';

  @override
  String get passwordMinLengthError => 'Adgangskoden skal være mindst 8 tegn';

  @override
  String get signInSuccess => 'Login lykkedes!';

  @override
  String get alreadyHaveAccountLogin => 'Har du allerede en konto? Log ind';

  @override
  String get emailLabel => 'E-mail';

  @override
  String get passwordLabel => 'Adgangskode';

  @override
  String get createAccountTitle => 'Opret konto';

  @override
  String get nameLabel => 'Navn';

  @override
  String get repeatPasswordLabel => 'Gentag adgangskode';

  @override
  String get signUpButton => 'Tilmeld dig';

  @override
  String get enterNameError => 'Indtast venligst dit navn';

  @override
  String get passwordsDoNotMatch => 'Adgangskoderne stemmer ikke overens';

  @override
  String get signUpSuccess => 'Tilmelding gennemført!';

  @override
  String get loadingKnowledgeGraph => 'Indlæser vidensgraf...';

  @override
  String get noKnowledgeGraphYet => 'Ingen vidensgraf endnu';

  @override
  String get buildingKnowledgeGraphFromMemories => 'Opbygger vidensgraf fra minder...';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'Din vidensgraf vil blive opbygget automatisk, når du opretter nye minder.';

  @override
  String get buildGraphButton => 'Opbyg graf';

  @override
  String get checkOutMyMemoryGraph => 'Se min hukommelsesgraf!';

  @override
  String get getButton => 'Hent';

  @override
  String openingApp(String appName) {
    return 'Åbner $appName...';
  }

  @override
  String get writeSomething => 'Skriv noget';

  @override
  String get submitReply => 'Send svar';

  @override
  String get editYourReply => 'Rediger dit svar';

  @override
  String get replyToReview => 'Svar på anmeldelse';

  @override
  String get rateAndReviewThisApp => 'Bedøm og anmeld denne app';

  @override
  String get noChangesInReview => 'Ingen ændringer i anmeldelsen at opdatere.';

  @override
  String get cantRateWithoutInternet => 'Kan ikke bedømme app uden internetforbindelse.';

  @override
  String get appAnalytics => 'App-analyse';

  @override
  String get learnMoreLink => 'lær mere';

  @override
  String get moneyEarned => 'Penge tjent';

  @override
  String get writeYourReply => 'Skriv dit svar...';

  @override
  String get replySentSuccessfully => 'Svar sendt';

  @override
  String failedToSendReply(String error) {
    return 'Kunne ikke sende svar: $error';
  }

  @override
  String get send => 'Send';

  @override
  String starFilter(int count) {
    return '$count stjerne';
  }

  @override
  String get noReviewsFound => 'Ingen anmeldelser fundet';

  @override
  String get editReply => 'Rediger svar';

  @override
  String get reply => 'Svar';

  @override
  String starFilterLabel(int count) {
    return '$count stjerne';
  }

  @override
  String get sharePublicLink => 'Del offentligt link';

  @override
  String get makePersonaPublic => 'Gør persona offentlig';

  @override
  String get connectedKnowledgeData => 'Tilsluttede vidensdata';

  @override
  String get enterName => 'Indtast navn';

  @override
  String get disconnectTwitter => 'Frakobl Twitter';

  @override
  String get disconnectTwitterConfirmation =>
      'Er du sikker på, at du vil frakoble din Twitter-konto? Din persona vil ikke længere have adgang til dine Twitter-data.';

  @override
  String get getOmiDeviceDescription => 'Få en Omi-enhed for at begynde';

  @override
  String get getOmi => 'Få Omi';

  @override
  String get iHaveOmiDevice => 'Jeg har en Omi-enhed';

  @override
  String get goal => 'MÅL';

  @override
  String get tapToTrackThisGoal => 'Tryk for at spore dette mål';

  @override
  String get tapToSetAGoal => 'Tryk for at sætte et mål';

  @override
  String get processedConversations => 'Behandlede samtaler';

  @override
  String get updatedConversations => 'Opdaterede samtaler';

  @override
  String get newConversations => 'Nye samtaler';

  @override
  String get summaryTemplate => 'Resuméskabelon';

  @override
  String get suggestedTemplates => 'Foreslåede skabeloner';

  @override
  String get otherTemplates => 'Andre skabeloner';

  @override
  String get availableTemplates => 'Tilgængelige skabeloner';

  @override
  String get getCreative => 'Vær kreativ';

  @override
  String get defaultLabel => 'Standard';

  @override
  String get lastUsedLabel => 'Sidst brugt';

  @override
  String get setDefaultApp => 'Angiv standardapp';

  @override
  String setDefaultAppContent(String appName) {
    return 'Angiv $appName som din standardapp til resuméer?\\n\\nDenne app vil automatisk blive brugt til alle fremtidige samtaleresuméer.';
  }

  @override
  String get setDefaultButton => 'Angiv standard';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName angivet som standardapp til resuméer';
  }

  @override
  String get createCustomTemplate => 'Opret brugerdefineret skabelon';

  @override
  String get allTemplates => 'Alle skabeloner';

  @override
  String failedToInstallApp(String appName) {
    return 'Kunne ikke installere $appName. Prøv igen.';
  }

  @override
  String errorInstallingApp(String appName, String error) {
    return 'Fejl ved installation af $appName: $error';
  }

  @override
  String tagSpeaker(int speakerId) {
    return 'Markér taler';
  }

  @override
  String get personNameAlreadyExists => 'Dette navn findes allerede';

  @override
  String get selectYouFromList => 'Vælg dig selv fra listen';

  @override
  String get enterPersonsName => 'Indtast personens navn';

  @override
  String get addPerson => 'Tilføj person';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'Markér andre segmenter fra denne taler';
  }

  @override
  String get tagOtherSegments => 'Markér andre segmenter';

  @override
  String get managePeople => 'Administrer personer';

  @override
  String get shareViaSms => 'Del via SMS';

  @override
  String get selectContactsToShareSummary => 'Vælg kontakter til at dele dit samtaleresumé';

  @override
  String get searchContactsHint => 'Søg kontakter...';

  @override
  String contactsSelectedCount(int count) {
    return '$count valgt';
  }

  @override
  String get clearAllSelection => 'Ryd alt';

  @override
  String get selectContactsToShare => 'Vælg kontakter at dele med';

  @override
  String shareWithContactCount(int count) {
    return 'Del med $count kontakt';
  }

  @override
  String shareWithContactsCount(int count) {
    return 'Del med $count kontakter';
  }

  @override
  String get contactsPermissionRequired => 'Kontakttilladelse påkrævet';

  @override
  String get contactsPermissionRequiredForSms => 'Kontakttilladelse er påkrævet for at dele via SMS';

  @override
  String get grantContactsPermissionForSms => 'Giv venligst kontakttilladelse for at dele via SMS';

  @override
  String get noContactsWithPhoneNumbers => 'Ingen kontakter med telefonnumre fundet';

  @override
  String get noContactsMatchSearch => 'Ingen kontakter matcher din søgning';

  @override
  String get failedToLoadContacts => 'Kunne ikke indlæse kontakter';

  @override
  String get failedToPrepareConversationForSharing => 'Kunne ikke forberede samtalen til deling. Prøv venligst igen.';

  @override
  String get couldNotOpenSmsApp => 'Kunne ikke åbne SMS-appen. Prøv venligst igen.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'Her er hvad vi lige har diskuteret: $link';
  }

  @override
  String get wifiSync => 'WiFi-synkronisering';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item kopieret til udklipsholder';
  }

  @override
  String get wifiConnectionFailedTitle => 'WiFi-forbindelse mislykkedes';

  @override
  String connectingToDeviceName(String deviceName) {
    return 'Forbinder til $deviceName';
  }

  @override
  String enableDeviceWifi(String deviceName) {
    return 'Aktivér WiFi på enheden';
  }

  @override
  String connectToDeviceName(String deviceName) {
    return 'Forbind til $deviceName';
  }

  @override
  String get recordingDetails => 'Optagelsesdetaljer';

  @override
  String get storageLocationSdCard => 'SD-kort';

  @override
  String get storageLocationLimitlessPendant => 'Limitless Pendant';

  @override
  String get storageLocationPhone => 'Telefon';

  @override
  String get storageLocationPhoneMemory => 'Telefonhukommelse';

  @override
  String storedOnDevice(String deviceName) {
    return 'Gemt på enhed';
  }

  @override
  String get transferring => 'Overfører...';

  @override
  String get transferRequired => 'Overførsel påkrævet';

  @override
  String get downloadingAudioFromSdCard => 'Downloader lyd fra SD-kort';

  @override
  String get transferRequiredDescription => 'Overfør optagelser fra din enhed til din telefon';

  @override
  String get cancelTransfer => 'Annuller overførsel';

  @override
  String get transferToPhone => 'Overfør til telefon';

  @override
  String get privateAndSecureOnDevice => 'Privat og sikker på enheden';

  @override
  String get recordingInfo => 'Optagelsesinfo';

  @override
  String get transferInProgress => 'Overførsel i gang';

  @override
  String get shareRecording => 'Del optagelse';

  @override
  String get deleteRecordingConfirmation => 'Er du sikker på, at du vil slette denne optagelse?';

  @override
  String get recordingIdLabel => 'Optagelses-ID';

  @override
  String get dateTimeLabel => 'Dato og tid';

  @override
  String get durationLabel => 'Varighed';

  @override
  String get audioFormatLabel => 'Lydformat';

  @override
  String get storageLocationLabel => 'Lagerplacering';

  @override
  String get estimatedSizeLabel => 'Estimeret størrelse';

  @override
  String get deviceModelLabel => 'Enhedsmodel';

  @override
  String get deviceIdLabel => 'Enheds-ID';

  @override
  String get statusLabel => 'Status';

  @override
  String get statusProcessed => 'Behandlet';

  @override
  String get statusUnprocessed => 'Ubehandlet';

  @override
  String get switchedToFastTransfer => 'Skiftet til hurtig overførsel';

  @override
  String get transferCompleteMessage => 'Overførsel fuldført! Du kan nu afspille denne optagelse.';

  @override
  String transferFailedMessage(String error) {
    return 'Overførsel mislykkedes. Prøv venligst igen.';
  }

  @override
  String get transferCancelled => 'Overførsel annulleret';

  @override
  String get fastTransferEnabled => 'Hurtig overførsel aktiveret';

  @override
  String get bluetoothSyncEnabled => 'Bluetooth-synkronisering aktiveret';

  @override
  String get enableFastTransfer => 'Aktiver hurtig overførsel';

  @override
  String get fastTransferDescription =>
      'Hurtig overførsel bruger WiFi for ~5x hurtigere hastigheder. Din telefon vil midlertidigt forbinde til din Omi-enheds WiFi-netværk under overførsel.';

  @override
  String get internetAccessPausedDuringTransfer => 'Internetadgang er sat på pause under overførsel';

  @override
  String get chooseTransferMethodDescription => 'Vælg hvordan optagelser overføres fra din Omi-enhed til din telefon.';

  @override
  String get wifiSpeed => 'WiFi-hastighed';

  @override
  String get fiveTimesFaster => '5X HURTIGERE';

  @override
  String get fastTransferMethodDescription =>
      'Opretter en direkte WiFi-forbindelse til din Omi-enhed. Din telefon afbrydes midlertidigt fra dit normale WiFi under overførsel.';

  @override
  String get bluetooth => 'Bluetooth';

  @override
  String get bleSpeed => 'BLE-hastighed';

  @override
  String get bluetoothMethodDescription =>
      'Bruger standard Bluetooth Low Energy forbindelse. Langsommere men påvirker ikke din WiFi-forbindelse.';

  @override
  String get selected => 'Valgt';

  @override
  String get selectOption => 'Vælg';

  @override
  String get lowBatteryAlertTitle => 'Advarsel om lavt batteri';

  @override
  String get lowBatteryAlertBody => 'Din enheds batteri er lavt. Det er tid til at genoplade! 🔋';

  @override
  String get deviceDisconnectedNotificationTitle => 'Din Omi-enhed er afbrudt';

  @override
  String get deviceDisconnectedNotificationBody => 'Tilslut venligst igen for at fortsætte med at bruge din Omi.';

  @override
  String get firmwareUpdateAvailable => 'Firmwareopdatering tilgængelig';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'En ny firmwareopdatering ($version) er tilgængelig til din Omi-enhed. Vil du opdatere nu?';
  }

  @override
  String get later => 'Senere';

  @override
  String get appDeletedSuccessfully => 'App slettet med succes';

  @override
  String get appDeleteFailed => 'Kunne ikke slette app. Prøv venligst igen senere.';

  @override
  String get appVisibilityChangedSuccessfully =>
      'App-synlighed ændret med succes. Det kan tage et par minutter at træde i kraft.';

  @override
  String get errorActivatingAppIntegration =>
      'Fejl ved aktivering af app. Hvis det er en integrationsapp, skal du sikre dig, at opsætningen er fuldført.';

  @override
  String get errorUpdatingAppStatus => 'Der opstod en fejl under opdatering af app-status.';

  @override
  String get calculatingETA => 'Beregner estimeret tid';

  @override
  String aboutMinutesRemaining(int minutes) {
    return 'Ca. $minutes minutter tilbage';
  }

  @override
  String get aboutAMinuteRemaining => 'Ca. et minut tilbage';

  @override
  String get almostDone => 'Næsten færdig';

  @override
  String get omiSays => 'Omi siger';

  @override
  String get analyzingYourData => 'Analyserer dine data';

  @override
  String migratingToProtection(String level) {
    return 'Migrerer til beskyttelse';
  }

  @override
  String get noDataToMigrateFinalizing => 'Ingen data at migrere, færdiggør';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return 'Migrerer $itemType... $percentage%';
  }

  @override
  String get allObjectsMigratedFinalizing => 'Alle objekter migreret, færdiggør';

  @override
  String get migrationErrorOccurred => 'Der opstod en fejl under migreringen';

  @override
  String get migrationComplete => 'Migrering fuldført';

  @override
  String dataProtectedWithSettings(String level) {
    return 'Data beskyttet med indstillinger';
  }

  @override
  String get chatsLowercase => 'chats';

  @override
  String get dataLowercase => 'data';

  @override
  String get fallNotificationTitle => 'Fald registreret';

  @override
  String get fallNotificationBody => 'Et fald er blevet registreret. Er du okay?';

  @override
  String get importantConversationTitle => 'Vigtig samtale';

  @override
  String get importantConversationBody => 'Du har lige haft en vigtig samtale. Tryk for at dele resuméet med andre.';

  @override
  String get templateName => 'Skabelonnavn';

  @override
  String get templateNameHint => 'f.eks. Mødehandlingspunkter Ekstraktor';

  @override
  String get nameMustBeAtLeast3Characters => 'Navnet skal være mindst 3 tegn';

  @override
  String get conversationPromptHint => 'f.eks. Udtræk handlingspunkter, beslutninger og vigtige pointer fra samtalen.';

  @override
  String get pleaseEnterAppPrompt => 'Indtast venligst en prompt til din app';

  @override
  String get promptMustBeAtLeast10Characters => 'Prompten skal være mindst 10 tegn';

  @override
  String get anyoneCanDiscoverTemplate => 'Alle kan finde din skabelon';

  @override
  String get onlyYouCanUseTemplate => 'Kun du kan bruge denne skabelon';

  @override
  String get generatingDescription => 'Genererer beskrivelse...';

  @override
  String get creatingAppIcon => 'Opretter app-ikon...';

  @override
  String get installingApp => 'Installerer app...';

  @override
  String get appCreatedAndInstalled => 'App oprettet og installeret!';

  @override
  String get appCreatedSuccessfully => 'App oprettet!';

  @override
  String get failedToCreateApp => 'Kunne ikke oprette app. Prøv venligst igen.';

  @override
  String get addAppSelectCoreCapability => 'Vælg endnu en kernefunktion til din app';

  @override
  String get addAppSelectPaymentPlan => 'Vælg en betalingsplan og indtast en pris for din app';

  @override
  String get addAppSelectCapability => 'Vælg mindst én funktion til din app';

  @override
  String get addAppSelectLogo => 'Vælg et logo til din app';

  @override
  String get addAppEnterChatPrompt => 'Indtast en chatprompt til din app';

  @override
  String get addAppEnterConversationPrompt => 'Indtast en samtaleprompt til din app';

  @override
  String get addAppSelectTriggerEvent => 'Vælg en udløserhændelse til din app';

  @override
  String get addAppEnterWebhookUrl => 'Indtast en webhook-URL til din app';

  @override
  String get addAppSelectCategory => 'Vælg en kategori til din app';

  @override
  String get addAppFillRequiredFields => 'Udfyld alle påkrævede felter korrekt';

  @override
  String get addAppUpdatedSuccess => 'App opdateret succesfuldt 🚀';

  @override
  String get addAppUpdateFailed => 'Opdatering mislykkedes. Prøv igen senere';

  @override
  String get addAppSubmittedSuccess => 'App indsendt succesfuldt 🚀';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'Fejl ved åbning af filvælger: $message';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'Fejl ved valg af billede: $error';
  }

  @override
  String get addAppPhotosPermissionDenied => 'Fototilladelse nægtet. Tillad adgang til fotos';

  @override
  String get addAppErrorSelectingImageRetry => 'Fejl ved valg af billede. Prøv igen.';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'Fejl ved valg af miniature: $error';
  }

  @override
  String get addAppErrorSelectingThumbnailRetry => 'Fejl ved valg af miniature. Prøv igen.';

  @override
  String get addAppCapabilityConflictWithPersona => 'Andre funktioner kan ikke vælges med Persona';

  @override
  String get addAppPersonaConflictWithCapabilities => 'Persona kan ikke vælges med andre funktioner';

  @override
  String get personaTwitterHandleNotFound => 'Twitter-konto ikke fundet';

  @override
  String get personaTwitterHandleSuspended => 'Twitter-konto er suspenderet';

  @override
  String get personaFailedToVerifyTwitter => 'Kunne ikke verificere Twitter-konto';

  @override
  String get personaFailedToFetch => 'Kunne ikke hente din persona';

  @override
  String get personaFailedToCreate => 'Kunne ikke oprette persona';

  @override
  String get personaConnectKnowledgeSource => 'Tilslut mindst én datakilde (Omi eller Twitter)';

  @override
  String get personaUpdatedSuccessfully => 'Persona opdateret succesfuldt';

  @override
  String get personaFailedToUpdate => 'Kunne ikke opdatere persona';

  @override
  String get personaPleaseSelectImage => 'Vælg et billede';

  @override
  String get personaFailedToCreateTryLater => 'Kunne ikke oprette persona. Prøv igen senere.';

  @override
  String personaFailedToCreateWithError(String error) {
    return 'Kunne ikke oprette persona: $error';
  }

  @override
  String get personaFailedToEnable => 'Kunne ikke aktivere persona';

  @override
  String personaErrorEnablingWithError(String error) {
    return 'Fejl ved aktivering af persona: $error';
  }

  @override
  String get paymentFailedToFetchCountries => 'Kunne ikke hente understøttede lande. Prøv igen senere.';

  @override
  String get paymentFailedToSetDefault => 'Kunne ikke indstille standardbetalingsmetode. Prøv igen senere.';

  @override
  String get paymentFailedToSavePaypal => 'Kunne ikke gemme PayPal-oplysninger. Prøv igen senere.';

  @override
  String get paypalEmailHint => 'PayPal e-mail';

  @override
  String get paypalMeLinkHint => 'PayPal.me-link';

  @override
  String get paymentMethodStripe => 'Stripe';

  @override
  String get paymentMethodPayPal => 'PayPal';

  @override
  String get paymentStatusActive => 'Aktiv';

  @override
  String get paymentStatusConnected => 'Tilsluttet';

  @override
  String get paymentStatusNotConnected => 'Ikke tilsluttet';

  @override
  String get paymentAppCost => 'App-pris';

  @override
  String get paymentEnterValidAmount => 'Indtast et gyldigt beløb';

  @override
  String get paymentEnterAmountGreaterThanZero => 'Indtast et beløb større end 0';

  @override
  String get paymentPlan => 'Betalingsplan';

  @override
  String get paymentNoneSelected => 'Ingen valgt';

  @override
  String get aiGenPleaseEnterDescription => 'Indtast venligst en beskrivelse af din app';

  @override
  String get aiGenCreatingAppIcon => 'Opretter app-ikon...';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'Der opstod en fejl: $message';
  }

  @override
  String get aiGenAppCreatedSuccessfully => 'App oprettet!';

  @override
  String get aiGenFailedToCreateApp => 'Kunne ikke oprette app';

  @override
  String get aiGenErrorWhileCreatingApp => 'Der opstod en fejl under oprettelse af appen';

  @override
  String get aiGenFailedToGenerateApp => 'Kunne ikke generere app. Prøv venligst igen.';

  @override
  String get aiGenFailedToRegenerateIcon => 'Kunne ikke genskabe ikonet';

  @override
  String get aiGenPleaseGenerateAppFirst => 'Generer venligst en app først';

  @override
  String get xHandleTitle => 'Hvad er dit X-brugernavn?';

  @override
  String get xHandleDescription => 'Indtast dit X-brugernavn (uden @) for at forbinde din profil.';

  @override
  String get xHandleHint => 'Dit X-brugernavn';

  @override
  String get xHandlePleaseEnter => 'Indtast venligst dit X-brugernavn';

  @override
  String get xHandlePleaseEnterValid => 'Indtast venligst et gyldigt X-brugernavn';

  @override
  String get nextButton => 'Næste';

  @override
  String get connectOmiDevice => 'Forbind Omi-enhed';

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'Du skifter dit Unlimited-abonnement til $title. Er du sikker på, at du vil fortsætte?';
  }

  @override
  String get planUpgradeScheduledMessage =>
      'Din planopgradering er planlagt og træder i kraft ved udgangen af din nuværende faktureringsperiode.';

  @override
  String get couldNotSchedulePlanChange => 'Kunne ikke planlægge abonnementsændring. Prøv venligst igen.';

  @override
  String get subscriptionReactivatedDefault =>
      'Dit abonnement er blevet genaktiveret! Ingen opkrævning nu - du faktureres ved udgangen af din nuværende periode.';

  @override
  String get subscriptionSuccessfulCharged => 'Abonnement opkrævet! Tak for din støtte.';

  @override
  String get couldNotProcessSubscription => 'Kunne ikke behandle abonnement. Prøv venligst igen.';

  @override
  String get couldNotLaunchUpgradePage => 'Kunne ikke åbne opgraderingssiden. Prøv venligst igen.';

  @override
  String get transcriptionJsonPlaceholder => 'Transskription JSON';

  @override
  String get transcriptionSourceOmi => 'Kilde: Omi';

  @override
  String get pricePlaceholder => 'Pris';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'Fejl ved åbning af filvælger: $message';
  }

  @override
  String importErrorGeneric(String error) {
    return 'Fejl: $error';
  }

  @override
  String get mergeConversationsSuccessTitle => 'Samtaler flettet succesfuldt';

  @override
  String mergeConversationsSuccessBody(int count) {
    return '$count samtaler er blevet flettet';
  }

  @override
  String get dailyReflectionNotificationTitle => 'Tid til daglig refleksion';

  @override
  String get dailyReflectionNotificationBody => 'Fortæl mig om din dag';

  @override
  String get actionItemReminderTitle => 'Omi-påmindelse';

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName frakoblet';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'Tilslut venligst igen for at fortsætte med at bruge din $deviceName.';
  }

  @override
  String get onboardingSignIn => 'Log ind';

  @override
  String get onboardingYourName => 'Dit navn';

  @override
  String get onboardingLanguage => 'Sprog';

  @override
  String get onboardingPermissions => 'Tilladelser';

  @override
  String get onboardingComplete => 'Færdig';

  @override
  String get onboardingWelcomeToOmi => 'Velkommen til Omi';

  @override
  String get onboardingTellUsAboutYourself => 'Fortæl os om dig selv';

  @override
  String get onboardingChooseYourPreference => 'Vælg din præference';

  @override
  String get onboardingGrantRequiredAccess => 'Giv den nødvendige adgang';

  @override
  String get onboardingYoureAllSet => 'Du er klar';

  @override
  String get searchTranscriptOrSummary => 'Søg i transskription eller resumé...';

  @override
  String get myGoal => 'Mit mål';

  @override
  String get appNotAvailable => 'Ups! Det ser ud til, at den app, du leder efter, ikke er tilgængelig.';

  @override
  String get failedToConnectTodoist => 'Kunne ikke oprette forbindelse til Todoist';

  @override
  String get failedToConnectAsana => 'Kunne ikke oprette forbindelse til Asana';

  @override
  String get failedToConnectGoogleTasks => 'Kunne ikke oprette forbindelse til Google Tasks';

  @override
  String get failedToConnectClickUp => 'Kunne ikke oprette forbindelse til ClickUp';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return 'Kunne ikke oprette forbindelse til $serviceName: $error';
  }

  @override
  String get successfullyConnectedTodoist => 'Forbundet til Todoist!';

  @override
  String get failedToConnectTodoistRetry => 'Kunne ikke oprette forbindelse til Todoist. Prøv venligst igen.';

  @override
  String get successfullyConnectedAsana => 'Forbundet til Asana!';

  @override
  String get failedToConnectAsanaRetry => 'Kunne ikke oprette forbindelse til Asana. Prøv venligst igen.';

  @override
  String get successfullyConnectedGoogleTasks => 'Forbundet til Google Tasks!';

  @override
  String get failedToConnectGoogleTasksRetry => 'Kunne ikke oprette forbindelse til Google Tasks. Prøv venligst igen.';

  @override
  String get successfullyConnectedClickUp => 'Forbundet til ClickUp!';

  @override
  String get failedToConnectClickUpRetry => 'Kunne ikke oprette forbindelse til ClickUp. Prøv venligst igen.';

  @override
  String get successfullyConnectedNotion => 'Forbundet til Notion!';

  @override
  String get failedToRefreshNotionStatus => 'Kunne ikke opdatere Notion-forbindelsesstatus.';

  @override
  String get successfullyConnectedGoogle => 'Forbundet til Google!';

  @override
  String get failedToRefreshGoogleStatus => 'Kunne ikke opdatere Google-forbindelsesstatus.';

  @override
  String get successfullyConnectedWhoop => 'Forbundet til Whoop!';

  @override
  String get failedToRefreshWhoopStatus => 'Kunne ikke opdatere Whoop-forbindelsesstatus.';

  @override
  String get successfullyConnectedGitHub => 'Forbundet til GitHub!';

  @override
  String get failedToRefreshGitHubStatus => 'Kunne ikke opdatere GitHub-forbindelsesstatus.';

  @override
  String get authFailedToSignInWithGoogle => 'Kunne ikke logge ind med Google, prøv venligst igen.';

  @override
  String get authenticationFailed => 'Godkendelse mislykkedes. Prøv venligst igen.';

  @override
  String get authFailedToSignInWithApple => 'Kunne ikke logge ind med Apple, prøv venligst igen.';

  @override
  String get authFailedToRetrieveToken => 'Kunne ikke hente Firebase-token, prøv venligst igen.';

  @override
  String get authUnexpectedErrorFirebase => 'Uventet fejl under login, Firebase-fejl, prøv venligst igen.';

  @override
  String get authUnexpectedError => 'Uventet fejl under login, prøv venligst igen';

  @override
  String get authFailedToLinkGoogle => 'Kunne ikke forbinde med Google, prøv venligst igen.';

  @override
  String get authFailedToLinkApple => 'Kunne ikke forbinde med Apple, prøv venligst igen.';

  @override
  String get onboardingBluetoothRequired =>
      'Bluetooth-tilladelse er påkrævet for at oprette forbindelse til din enhed.';

  @override
  String get onboardingBluetoothDeniedSystemPrefs =>
      'Bluetooth-tilladelse afvist. Giv venligst tilladelse i Systemindstillinger.';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'Bluetooth-tilladelsestatus: $status. Tjek venligst Systemindstillinger.';
  }

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'Kunne ikke kontrollere Bluetooth-tilladelse: $error';
  }

  @override
  String get onboardingNotificationDeniedSystemPrefs =>
      'Notifikationstilladelse afvist. Giv venligst tilladelse i Systemindstillinger.';

  @override
  String get onboardingNotificationDeniedNotifications =>
      'Notifikationstilladelse afvist. Giv venligst tilladelse i Systemindstillinger > Notifikationer.';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return 'Notifikationstilladelsestatus: $status. Tjek venligst Systemindstillinger.';
  }

  @override
  String onboardingFailedCheckNotification(String error) {
    return 'Kunne ikke kontrollere notifikationstilladelse: $error';
  }

  @override
  String get onboardingLocationGrantInSettings =>
      'Giv venligst placeringstilladelse i Indstillinger > Privatliv og sikkerhed > Placeringstjenester';

  @override
  String get onboardingMicrophoneRequired => 'Mikrofontilladelse er påkrævet for optagelse.';

  @override
  String get onboardingMicrophoneDenied =>
      'Mikrofontilladelse afvist. Giv venligst tilladelse i Systemindstillinger > Privatliv og sikkerhed > Mikrofon.';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'Mikrofontilladelsestatus: $status. Tjek venligst Systemindstillinger.';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'Kunne ikke kontrollere mikrofontilladelse: $error';
  }

  @override
  String get onboardingScreenCaptureRequired => 'Skærmoptagelsestilladelse er påkrævet for systemlydoptagelse.';

  @override
  String get onboardingScreenCaptureDenied =>
      'Skærmoptagelsestilladelse afvist. Giv venligst tilladelse i Systemindstillinger > Privatliv og sikkerhed > Skærmoptagelse.';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return 'Skærmoptagelsestilladelsestatus: $status. Tjek venligst Systemindstillinger.';
  }

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return 'Kunne ikke kontrollere skærmoptagelsestilladelse: $error';
  }

  @override
  String get onboardingAccessibilityRequired => 'Tilgængelighedstilladelse er påkrævet for at registrere browsermøder.';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'Tilgængelighedstilladelsestatus: $status. Tjek venligst Systemindstillinger.';
  }

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'Kunne ikke kontrollere tilgængelighedstilladelse: $error';
  }

  @override
  String get msgCameraNotAvailable => 'Kameraoptagelse er ikke tilgængelig på denne platform';

  @override
  String get msgCameraPermissionDenied => 'Kameratilladelse nægtet. Tillad venligst adgang til kameraet';

  @override
  String msgCameraAccessError(String error) {
    return 'Fejl ved adgang til kamera: $error';
  }

  @override
  String get msgPhotoError => 'Fejl ved at tage foto. Prøv venligst igen.';

  @override
  String get msgMaxImagesLimit => 'Du kan kun vælge op til 4 billeder';

  @override
  String msgFilePickerError(String error) {
    return 'Fejl ved åbning af filvælger: $error';
  }

  @override
  String msgSelectImagesError(String error) {
    return 'Fejl ved valg af billeder: $error';
  }

  @override
  String get msgPhotosPermissionDenied =>
      'Fototilladelse nægtet. Tillad venligst adgang til fotos for at vælge billeder';

  @override
  String get msgSelectImagesGenericError => 'Fejl ved valg af billeder. Prøv venligst igen.';

  @override
  String get msgMaxFilesLimit => 'Du kan kun vælge op til 4 filer';

  @override
  String msgSelectFilesError(String error) {
    return 'Fejl ved valg af filer: $error';
  }

  @override
  String get msgSelectFilesGenericError => 'Fejl ved valg af filer. Prøv venligst igen.';

  @override
  String get msgUploadFileFailed => 'Kunne ikke uploade fil, prøv venligst igen senere';

  @override
  String get msgReadingMemories => 'Læser dine minder...';

  @override
  String get msgLearningMemories => 'Lærer fra dine minder...';

  @override
  String get msgUploadAttachedFileFailed => 'Kunne ikke uploade den vedhæftede fil.';

  @override
  String captureRecordingError(String error) {
    return 'Der opstod en fejl under optagelsen: $error';
  }

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return 'Optagelse stoppet: $reason. Du skal muligvis tilslutte eksterne skærme igen eller genstarte optagelsen.';
  }

  @override
  String get captureMicrophonePermissionRequired => 'Mikrofontilladelse påkrævet';

  @override
  String get captureMicrophonePermissionInSystemPreferences => 'Giv mikrofontilladelse i Systemindstillinger';

  @override
  String get captureScreenRecordingPermissionRequired => 'Skærmoptagelsestilladelse påkrævet';

  @override
  String get captureDisplayDetectionFailed => 'Skærmregistrering mislykkedes. Optagelse stoppet.';

  @override
  String get devModeInvalidAudioBytesWebhookUrl => 'Ugyldig webhook-URL til lydbytes';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl => 'Ugyldig webhook-URL til realtidstransskription';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl => 'Ugyldig webhook-URL til oprettet samtale';

  @override
  String get devModeInvalidDaySummaryWebhookUrl => 'Ugyldig webhook-URL til daglig opsummering';

  @override
  String get devModeSettingsSaved => 'Indstillinger gemt!';

  @override
  String get voiceFailedToTranscribe => 'Kunne ikke transskribere lyd';

  @override
  String get locationPermissionRequired => 'Placeringstilladelse påkrævet';

  @override
  String get locationPermissionContent =>
      'Hurtig overførsel kræver placeringstilladelse for at bekræfte WiFi-forbindelse. Giv venligst placeringstilladelse for at fortsætte.';

  @override
  String get pdfTranscriptExport => 'Eksport af transskription';

  @override
  String get pdfConversationExport => 'Eksport af samtale';

  @override
  String pdfTitleLabel(String title) {
    return 'Titel: $title';
  }

  @override
  String get conversationNewIndicator => 'Ny 🚀';

  @override
  String conversationPhotosCount(int count) {
    return '$count fotos';
  }

  @override
  String get mergingStatus => 'Fletter...';

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
    return '$count time';
  }

  @override
  String timeHoursPlural(int count) {
    return '$count timer';
  }

  @override
  String timeHoursAndMins(int hours, int mins) {
    return '$hours timer $mins min';
  }

  @override
  String timeDaySingular(int count) {
    return '$count dag';
  }

  @override
  String timeDaysPlural(int count) {
    return '$count dage';
  }

  @override
  String timeDaysAndHours(int days, int hours) {
    return '$days dage $hours timer';
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
  String get moveToFolder => 'Flyt til mappe';

  @override
  String get noFoldersAvailable => 'Ingen mapper tilgængelige';

  @override
  String get newFolder => 'Ny mappe';

  @override
  String get color => 'Farve';

  @override
  String get waitingForDevice => 'Venter på enhed...';

  @override
  String get saySomething => 'Sig noget...';

  @override
  String get initialisingSystemAudio => 'Initialiserer systemlyd';

  @override
  String get stopRecording => 'Stop optagelse';

  @override
  String get continueRecording => 'Fortsæt optagelse';

  @override
  String get initialisingRecorder => 'Initialiserer optager';

  @override
  String get pauseRecording => 'Pause optagelse';

  @override
  String get resumeRecording => 'Genoptag optagelse';

  @override
  String get noDailyRecapsYet => 'Ingen daglige opsamlinger endnu';

  @override
  String get dailyRecapsDescription => 'Dine daglige opsamlinger vises her, når de er genereret';

  @override
  String get chooseTransferMethod => 'Vælg overførselsmetode';

  @override
  String get fastTransferSpeed => '~150 KB/s via WiFi';

  @override
  String largeTimeGapDetected(String gap) {
    return 'Stort tidsgab opdaget ($gap)';
  }

  @override
  String largeTimeGapsDetected(String gaps) {
    return 'Store tidsgab opdaget ($gaps)';
  }

  @override
  String get deviceDoesNotSupportWifiSwitchingToBle =>
      'Enheden understøtter ikke WiFi-synkronisering, skifter til Bluetooth';

  @override
  String get appleHealthNotAvailable => 'Apple Health er ikke tilgængelig på denne enhed';

  @override
  String get downloadAudio => 'Download lyd';

  @override
  String get audioDownloadSuccess => 'Lyd downloadet succesfuldt';

  @override
  String get audioDownloadFailed => 'Kunne ikke downloade lyd';

  @override
  String get downloadingAudio => 'Downloader lyd...';

  @override
  String get shareAudio => 'Del lyd';

  @override
  String get preparingAudio => 'Forbereder lyd';

  @override
  String get gettingAudioFiles => 'Henter lydfiler...';

  @override
  String get downloadingAudioProgress => 'Downloader lyd';

  @override
  String get processingAudio => 'Behandler lyd';

  @override
  String get combiningAudioFiles => 'Kombinerer lydfiler...';

  @override
  String get audioReady => 'Lyd klar';

  @override
  String get openingShareSheet => 'Åbner delingsark...';

  @override
  String get audioShareFailed => 'Deling mislykkedes';

  @override
  String get dailyRecaps => 'Daglige Opsummeringer';

  @override
  String get removeFilter => 'Fjern Filter';

  @override
  String get categoryConversationAnalysis => 'Samtaleanalyse';

  @override
  String get categoryPersonalityClone => 'Personlighedsklon';

  @override
  String get categoryHealth => 'Sundhed';

  @override
  String get categoryEducation => 'Uddannelse';

  @override
  String get categoryCommunication => 'Kommunikation';

  @override
  String get categoryEmotionalSupport => 'Følelsesmæssig støtte';

  @override
  String get categoryProductivity => 'Produktivitet';

  @override
  String get categoryEntertainment => 'Underholdning';

  @override
  String get categoryFinancial => 'Økonomi';

  @override
  String get categoryTravel => 'Rejser';

  @override
  String get categorySafety => 'Sikkerhed';

  @override
  String get categoryShopping => 'Shopping';

  @override
  String get categorySocial => 'Socialt';

  @override
  String get categoryNews => 'Nyheder';

  @override
  String get categoryUtilities => 'Værktøjer';

  @override
  String get categoryOther => 'Andet';

  @override
  String get capabilityChat => 'Chat';

  @override
  String get capabilityConversations => 'Samtaler';

  @override
  String get capabilityExternalIntegration => 'Ekstern integration';

  @override
  String get capabilityNotification => 'Notifikation';

  @override
  String get triggerAudioBytes => 'Lyd-bytes';

  @override
  String get triggerConversationCreation => 'Samtaleoprettelse';

  @override
  String get triggerTranscriptProcessed => 'Transskription behandlet';

  @override
  String get actionCreateConversations => 'Opret samtaler';

  @override
  String get actionCreateMemories => 'Opret minder';

  @override
  String get actionReadConversations => 'Læs samtaler';

  @override
  String get actionReadMemories => 'Læs minder';

  @override
  String get actionReadTasks => 'Læs opgaver';

  @override
  String get scopeUserName => 'Brugernavn';

  @override
  String get scopeUserFacts => 'Brugerfakta';

  @override
  String get scopeUserConversations => 'Brugersamtaler';

  @override
  String get scopeUserChat => 'Brugerchat';

  @override
  String get capabilitySummary => 'Resumé';

  @override
  String get capabilityFeatured => 'Udvalgte';

  @override
  String get capabilityTasks => 'Opgaver';

  @override
  String get capabilityIntegrations => 'Integrationer';

  @override
  String get categoryPersonalityClones => 'Personlighedskloner';

  @override
  String get categoryProductivityLifestyle => 'Produktivitet og livsstil';

  @override
  String get categorySocialEntertainment => 'Socialt og underholdning';

  @override
  String get categoryProductivityTools => 'Produktivitetsværktøjer';

  @override
  String get categoryPersonalWellness => 'Personlig velvære';

  @override
  String get rating => 'Bedømmelse';

  @override
  String get categories => 'Kategorier';

  @override
  String get sortBy => 'Sorter';

  @override
  String get highestRating => 'Højeste bedømmelse';

  @override
  String get lowestRating => 'Laveste bedømmelse';

  @override
  String get resetFilters => 'Nulstil filtre';

  @override
  String get applyFilters => 'Anvend filtre';

  @override
  String get mostInstalls => 'Flest installationer';

  @override
  String get couldNotOpenUrl => 'Kunne ikke åbne URL. Prøv venligst igen.';

  @override
  String get newTask => 'Ny opgave';

  @override
  String get viewAll => 'Vis alle';

  @override
  String get addTask => 'Tilføj opgave';

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
  String get audioPlaybackUnavailable => 'Lydfilen er ikke tilgængelig til afspilning';

  @override
  String get audioPlaybackFailed => 'Kan ikke afspille lyd. Filen kan være beskadiget eller manglende.';

  @override
  String get connectionGuide => 'Tilslutningsguide';

  @override
  String get iveDoneThis => 'Det har jeg gjort';

  @override
  String get pairNewDevice => 'Par ny enhed';

  @override
  String get dontSeeYourDevice => 'Kan du ikke se din enhed?';

  @override
  String get reportAnIssue => 'Rapportér et problem';

  @override
  String get pairingTitleOmi => 'Tænd Omi';

  @override
  String get pairingDescOmi => 'Tryk og hold på enheden, indtil den vibrerer, for at tænde den.';

  @override
  String get pairingTitleOmiDevkit => 'Sæt Omi DevKit i parringstilstand';

  @override
  String get pairingDescOmiDevkit => 'Tryk på knappen én gang for at tænde. LED\'en blinker lilla i parringstilstand.';

  @override
  String get pairingTitleOmiGlass => 'Tænd Omi Glass';

  @override
  String get pairingDescOmiGlass => 'Tryk og hold sideknappen i 3 sekunder for at tænde.';

  @override
  String get pairingTitlePlaudNote => 'Sæt Plaud Note i parringstilstand';

  @override
  String get pairingDescPlaudNote =>
      'Tryk og hold sideknappen i 2 sekunder. Den røde LED blinker, når den er klar til parring.';

  @override
  String get pairingTitleBee => 'Sæt Bee i parringstilstand';

  @override
  String get pairingDescBee => 'Tryk på knappen 5 gange i træk. Lyset begynder at blinke blåt og grønt.';

  @override
  String get pairingTitleLimitless => 'Sæt Limitless i parringstilstand';

  @override
  String get pairingDescLimitless =>
      'Når et lys er synligt, tryk én gang og tryk derefter og hold, indtil enheden viser et pink lys, slip derefter.';

  @override
  String get pairingTitleFriendPendant => 'Sæt Friend Pendant i parringstilstand';

  @override
  String get pairingDescFriendPendant =>
      'Tryk på knappen på vedhænget for at tænde det. Det går automatisk i parringstilstand.';

  @override
  String get pairingTitleFieldy => 'Sæt Fieldy i parringstilstand';

  @override
  String get pairingDescFieldy => 'Tryk og hold på enheden, indtil lyset vises, for at tænde den.';

  @override
  String get pairingTitleAppleWatch => 'Tilslut Apple Watch';

  @override
  String get pairingDescAppleWatch =>
      'Installer og åbn Omi-appen på dit Apple Watch, tryk derefter på Tilslut i appen.';

  @override
  String get pairingTitleNeoOne => 'Sæt Neo One i parringstilstand';

  @override
  String get pairingDescNeoOne => 'Tryk og hold tænd/sluk-knappen, indtil LED\'en blinker. Enheden vil være synlig.';
}
