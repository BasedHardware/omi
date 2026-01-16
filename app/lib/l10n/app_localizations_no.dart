// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Norwegian (`no`).
class AppLocalizationsNo extends AppLocalizations {
  AppLocalizationsNo([String locale = 'no']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'Samtale';

  @override
  String get transcriptTab => 'Transkripsjon';

  @override
  String get actionItemsTab => 'Handlingspunkter';

  @override
  String get deleteConversationTitle => 'Slette samtale?';

  @override
  String get deleteConversationMessage => 'Er du sikker på at du vil slette denne samtalen? Dette kan ikke angres.';

  @override
  String get confirm => 'Bekreft';

  @override
  String get cancel => 'Avbryt';

  @override
  String get ok => 'Ok';

  @override
  String get delete => 'Slett';

  @override
  String get add => 'Legg til';

  @override
  String get update => 'Oppdater';

  @override
  String get save => 'Lagre';

  @override
  String get edit => 'Rediger';

  @override
  String get close => 'Lukk';

  @override
  String get clear => 'Tøm';

  @override
  String get copyTranscript => 'Kopier transkripsjon';

  @override
  String get copySummary => 'Kopier sammendrag';

  @override
  String get testPrompt => 'Test prompt';

  @override
  String get reprocessConversation => 'Behandle samtale på nytt';

  @override
  String get deleteConversation => 'Slett samtale';

  @override
  String get contentCopied => 'Innhold kopiert til utklippstavlen';

  @override
  String get failedToUpdateStarred => 'Kunne ikke oppdatere favoritt-status.';

  @override
  String get conversationUrlNotShared => 'Samtale-URL kunne ikke deles.';

  @override
  String get errorProcessingConversation => 'Feil under behandling av samtale. Prøv igjen senere.';

  @override
  String get noInternetConnection => 'Ingen internettilkobling';

  @override
  String get unableToDeleteConversation => 'Kan ikke slette samtale';

  @override
  String get somethingWentWrong => 'Noe gikk galt! Prøv igjen senere.';

  @override
  String get copyErrorMessage => 'Kopier feilmelding';

  @override
  String get errorCopied => 'Feilmelding kopiert til utklippstavlen';

  @override
  String get remaining => 'Gjenstående';

  @override
  String get loading => 'Laster...';

  @override
  String get loadingDuration => 'Laster varighet...';

  @override
  String secondsCount(int count) {
    return '$count sekunder';
  }

  @override
  String get people => 'Personer';

  @override
  String get addNewPerson => 'Legg til ny person';

  @override
  String get editPerson => 'Rediger person';

  @override
  String get createPersonHint => 'Opprett en ny person og tren Omi til å gjenkjenne deres tale også!';

  @override
  String get speechProfile => 'Taleprofil';

  @override
  String sampleNumber(int number) {
    return 'Prøve $number';
  }

  @override
  String get settings => 'Innstillinger';

  @override
  String get language => 'Språk';

  @override
  String get selectLanguage => 'Velg språk';

  @override
  String get deleting => 'Sletter...';

  @override
  String get pleaseCompleteAuthentication =>
      'Fullfør autentisering i nettleseren din. Når du er ferdig, gå tilbake til appen.';

  @override
  String get failedToStartAuthentication => 'Kunne ikke starte autentisering';

  @override
  String get importStarted => 'Import startet! Du vil bli varslet når den er fullført.';

  @override
  String get failedToStartImport => 'Kunne ikke starte import. Prøv igjen.';

  @override
  String get couldNotAccessFile => 'Kunne ikke åpne den valgte filen';

  @override
  String get askOmi => 'Spør Omi';

  @override
  String get done => 'Ferdig';

  @override
  String get disconnected => 'Frakoblet';

  @override
  String get searching => 'Søker...';

  @override
  String get connectDevice => 'Koble til enhet';

  @override
  String get monthlyLimitReached => 'Du har nådd din månedlige grense.';

  @override
  String get checkUsage => 'Sjekk forbruk';

  @override
  String get syncingRecordings => 'Synkroniserer opptak';

  @override
  String get recordingsToSync => 'Opptak å synkronisere';

  @override
  String get allCaughtUp => 'Alt er oppdatert';

  @override
  String get sync => 'Synkroniser';

  @override
  String get pendantUpToDate => 'Anheng er oppdatert';

  @override
  String get allRecordingsSynced => 'Alle opptak er synkronisert';

  @override
  String get syncingInProgress => 'Synkronisering pågår';

  @override
  String get readyToSync => 'Klar til synkronisering';

  @override
  String get tapSyncToStart => 'Trykk Synkroniser for å starte';

  @override
  String get pendantNotConnected => 'Anheng ikke tilkoblet. Koble til for å synkronisere.';

  @override
  String get everythingSynced => 'Alt er allerede synkronisert.';

  @override
  String get recordingsNotSynced => 'Du har opptak som ikke er synkronisert ennå.';

  @override
  String get syncingBackground => 'Vi fortsetter å synkronisere opptakene dine i bakgrunnen.';

  @override
  String get noConversationsYet => 'Ingen samtaler ennå';

  @override
  String get noStarredConversations => 'Ingen stjernede samtaler';

  @override
  String get starConversationHint =>
      'For å favorittmarkere en samtale, åpne den og trykk på stjerneikonet i overskriften.';

  @override
  String get searchConversations => 'Søk i samtaler...';

  @override
  String selectedCount(int count, Object s) {
    return '$count valgt';
  }

  @override
  String get merge => 'Slå sammen';

  @override
  String get mergeConversations => 'Slå sammen samtaler';

  @override
  String mergeConversationsMessage(int count) {
    return 'Dette vil kombinere $count samtaler til én. Alt innhold vil bli slått sammen og regenerert.';
  }

  @override
  String get mergingInBackground => 'Slår sammen i bakgrunnen. Dette kan ta et øyeblikk.';

  @override
  String get failedToStartMerge => 'Kunne ikke starte sammenslåing';

  @override
  String get askAnything => 'Spør om hva som helst';

  @override
  String get noMessagesYet => 'Ingen meldinger ennå!\nHvorfor ikke starte en samtale?';

  @override
  String get deletingMessages => 'Sletter meldingene dine fra Omis minne...';

  @override
  String get messageCopied => '✨ Melding kopiert til utklippstavle';

  @override
  String get cannotReportOwnMessage => 'Du kan ikke rapportere dine egne meldinger.';

  @override
  String get reportMessage => 'Rapporter melding';

  @override
  String get reportMessageConfirm => 'Er du sikker på at du vil rapportere denne meldingen?';

  @override
  String get messageReported => 'Melding rapportert.';

  @override
  String get thankYouFeedback => 'Takk for tilbakemeldingen!';

  @override
  String get clearChat => 'Tøm chat?';

  @override
  String get clearChatConfirm => 'Er du sikker på at du vil tømme chatten? Dette kan ikke angres.';

  @override
  String get maxFilesLimit => 'Du kan bare laste opp 4 filer om gangen';

  @override
  String get chatWithOmi => 'Chat med Omi';

  @override
  String get apps => 'Apper';

  @override
  String get noAppsFound => 'Ingen apper funnet';

  @override
  String get tryAdjustingSearch => 'Prøv å justere søket eller filtrene dine';

  @override
  String get createYourOwnApp => 'Lag din egen app';

  @override
  String get buildAndShareApp => 'Bygg og del din egendefinerte app';

  @override
  String get searchApps => 'Søk apper...';

  @override
  String get myApps => 'Mine Apper';

  @override
  String get installedApps => 'Installerte Apper';

  @override
  String get unableToFetchApps => 'Kan ikke hente apper :(\n\nSjekk internettforbindelsen din og prøv igjen.';

  @override
  String get aboutOmi => 'Om Omi';

  @override
  String get privacyPolicy => 'Personvernserklæring';

  @override
  String get visitWebsite => 'Besøk nettstedet';

  @override
  String get helpOrInquiries => 'Hjelp eller henvendelser?';

  @override
  String get joinCommunity => 'Bli med i fellesskapet!';

  @override
  String get membersAndCounting => '8000+ medlemmer og tallet øker.';

  @override
  String get deleteAccountTitle => 'Slett konto';

  @override
  String get deleteAccountConfirm => 'Er du sikker på at du vil slette kontoen din?';

  @override
  String get cannotBeUndone => 'Dette kan ikke angres.';

  @override
  String get allDataErased => 'Alle minnene og samtalene dine vil bli permanent slettet.';

  @override
  String get appsDisconnected => 'Appene og integrasjonene dine vil bli frakoblet umiddelbart.';

  @override
  String get exportBeforeDelete =>
      'Du kan eksportere dataene dine før du sletter kontoen, men når den er slettet, kan den ikke gjenopprettes.';

  @override
  String get deleteAccountCheckbox =>
      'Jeg forstår at sletting av kontoen min er permanent og at alle data, inkludert minner og samtaler, vil gå tapt og ikke kan gjenopprettes.';

  @override
  String get areYouSure => 'Er du sikker?';

  @override
  String get deleteAccountFinal =>
      'Denne handlingen kan ikke angres og vil permanent slette kontoen din og alle tilknyttede data. Er du sikker på at du vil fortsette?';

  @override
  String get deleteNow => 'Slett nå';

  @override
  String get goBack => 'Gå tilbake';

  @override
  String get checkBoxToConfirm =>
      'Kryss av for å bekrefte at du forstår at sletting av kontoen din er permanent og irreversibel.';

  @override
  String get profile => 'Profil';

  @override
  String get name => 'Navn';

  @override
  String get email => 'E-post';

  @override
  String get customVocabulary => 'Tilpasset Vokabular';

  @override
  String get identifyingOthers => 'Identifisering av Andre';

  @override
  String get paymentMethods => 'Betalingsmetoder';

  @override
  String get conversationDisplay => 'Samtalevisning';

  @override
  String get dataPrivacy => 'Datapersonvern';

  @override
  String get userId => 'Bruker-ID';

  @override
  String get notSet => 'Ikke angitt';

  @override
  String get userIdCopied => 'Bruker-ID kopiert til utklippstavlen';

  @override
  String get systemDefault => 'Systemstandard';

  @override
  String get planAndUsage => 'Abonnement og forbruk';

  @override
  String get offlineSync => 'Frakoblet synkronisering';

  @override
  String get deviceSettings => 'Enhetsinnstillinger';

  @override
  String get chatTools => 'Chatverktøy';

  @override
  String get feedbackBug => 'Tilbakemelding / Feil';

  @override
  String get helpCenter => 'Hjelpesenter';

  @override
  String get developerSettings => 'Utviklerinnstillinger';

  @override
  String get getOmiForMac => 'Få Omi for Mac';

  @override
  String get referralProgram => 'Henvisningsprogram';

  @override
  String get signOut => 'Logg Ut';

  @override
  String get appAndDeviceCopied => 'App- og enhetsdetaljer kopiert';

  @override
  String get wrapped2025 => 'Oppsummert 2025';

  @override
  String get yourPrivacyYourControl => 'Ditt personvern, din kontroll';

  @override
  String get privacyIntro =>
      'Hos Omi er vi opptatt av å beskytte ditt personvern. Denne siden lar deg kontrollere hvordan dataene dine lagres og brukes.';

  @override
  String get learnMore => 'Lær mer...';

  @override
  String get dataProtectionLevel => 'Databeskyttelsesnivå';

  @override
  String get dataProtectionDesc =>
      'Dataene dine er sikret som standard med sterk kryptering. Se gjennom innstillingene dine og fremtidige personvernalternativer nedenfor.';

  @override
  String get appAccess => 'Apptilgang';

  @override
  String get appAccessDesc =>
      'Følgende apper har tilgang til dataene dine. Trykk på en app for å administrere tillatelsene.';

  @override
  String get noAppsExternalAccess => 'Ingen installerte apper har ekstern tilgang til dataene dine.';

  @override
  String get deviceName => 'Enhetsnavn';

  @override
  String get deviceId => 'Enhets-ID';

  @override
  String get firmware => 'Fastvare';

  @override
  String get sdCardSync => 'SD-kort synkronisering';

  @override
  String get hardwareRevision => 'Maskinvarerevisjon';

  @override
  String get modelNumber => 'Modellnummer';

  @override
  String get manufacturer => 'Produsent';

  @override
  String get doubleTap => 'Dobbelttrykk';

  @override
  String get ledBrightness => 'LED-lysstyrke';

  @override
  String get micGain => 'Mikrofonforsterkning';

  @override
  String get disconnect => 'Koble fra';

  @override
  String get forgetDevice => 'Glem enhet';

  @override
  String get chargingIssues => 'Ladeproblemer';

  @override
  String get disconnectDevice => 'Koble fra enheten';

  @override
  String get unpairDevice => 'Opphev sammenkoblingen av enheten';

  @override
  String get unpairAndForget => 'Fjern paring og glem enhet';

  @override
  String get deviceDisconnectedMessage => 'Din Omi har blitt frakoblet 😔';

  @override
  String get deviceUnpairedMessage =>
      'Enhet frakoblet. Gå til Innstillinger > Bluetooth og glem enheten for å fullføre frakoblingen.';

  @override
  String get unpairDialogTitle => 'Fjern paring av enhet';

  @override
  String get unpairDialogMessage =>
      'Dette vil fjerne paringen av enheten slik at den kan kobles til en annen telefon. Du må gå til Innstillinger > Bluetooth og glemme enheten for å fullføre prosessen.';

  @override
  String get deviceNotConnected => 'Enhet ikke tilkoblet';

  @override
  String get connectDeviceMessage =>
      'Koble til Omi-enheten din for å få tilgang til\nenhetsinnstillinger og tilpasning';

  @override
  String get deviceInfoSection => 'Enhetsinformasjon';

  @override
  String get customizationSection => 'Tilpasning';

  @override
  String get hardwareSection => 'Maskinvare';

  @override
  String get v2Undetected => 'V2 ikke oppdaget';

  @override
  String get v2UndetectedMessage =>
      'Vi ser at du enten har en V1-enhet eller at enheten din ikke er tilkoblet. SD-kortfunksjonalitet er kun tilgjengelig for V2-enheter.';

  @override
  String get endConversation => 'Avslutt samtale';

  @override
  String get pauseResume => 'Pause/Fortsett';

  @override
  String get starConversation => 'Favorittmerk samtale';

  @override
  String get doubleTapAction => 'Dobbelttrykk-handling';

  @override
  String get endAndProcess => 'Avslutt og behandle samtale';

  @override
  String get pauseResumeRecording => 'Pause/Fortsett opptak';

  @override
  String get starOngoing => 'Favorittmerk pågående samtale';

  @override
  String get off => 'Av';

  @override
  String get max => 'Maks';

  @override
  String get mute => 'Demp';

  @override
  String get quiet => 'Stille';

  @override
  String get normal => 'Normal';

  @override
  String get high => 'Høy';

  @override
  String get micGainDescMuted => 'Mikrofon er dempet';

  @override
  String get micGainDescLow => 'Veldig stille - for høylydte omgivelser';

  @override
  String get micGainDescModerate => 'Stille - for moderat støy';

  @override
  String get micGainDescNeutral => 'Nøytral - balansert opptak';

  @override
  String get micGainDescSlightlyBoosted => 'Litt forsterket - normal bruk';

  @override
  String get micGainDescBoosted => 'Forsterket - for stille omgivelser';

  @override
  String get micGainDescHigh => 'Høy - for fjerne eller myke stemmer';

  @override
  String get micGainDescVeryHigh => 'Veldig høy - for veldig stille kilder';

  @override
  String get micGainDescMax => 'Maksimal - bruk med forsiktighet';

  @override
  String get developerSettingsTitle => 'Utviklerinnstillinger';

  @override
  String get saving => 'Lagrer...';

  @override
  String get personaConfig => 'Konfigurer din AI-persona';

  @override
  String get beta => 'BETA';

  @override
  String get transcription => 'Transkripsjon';

  @override
  String get transcriptionConfig => 'Konfigurer STT-leverandør';

  @override
  String get conversationTimeout => 'Samtale-timeout';

  @override
  String get conversationTimeoutConfig => 'Angi når samtaler avsluttes automatisk';

  @override
  String get importData => 'Importer data';

  @override
  String get importDataConfig => 'Importer data fra andre kilder';

  @override
  String get debugDiagnostics => 'Feilsøking og diagnostikk';

  @override
  String get endpointUrl => 'Endepunkt-URL';

  @override
  String get noApiKeys => 'Ingen API-nøkler ennå';

  @override
  String get createKeyToStart => 'Opprett en nøkkel for å komme i gang';

  @override
  String get createKey => 'Opprett Nøkkel';

  @override
  String get docs => 'Dokumentasjon';

  @override
  String get yourOmiInsights => 'Dine Omi-innsikter';

  @override
  String get today => 'I dag';

  @override
  String get thisMonth => 'Denne måneden';

  @override
  String get thisYear => 'Dette året';

  @override
  String get allTime => 'All tid';

  @override
  String get noActivityYet => 'Ingen aktivitet ennå';

  @override
  String get startConversationToSeeInsights => 'Start en samtale med Omi\nfor å se forbruksinnsiktene dine her.';

  @override
  String get listening => 'Lytter';

  @override
  String get listeningSubtitle => 'Total tid Omi har lyttet aktivt.';

  @override
  String get understanding => 'Forstår';

  @override
  String get understandingSubtitle => 'Ord forstått fra samtalene dine.';

  @override
  String get providing => 'Gir';

  @override
  String get providingSubtitle => 'Handlingspunkter og notater automatisk registrert.';

  @override
  String get remembering => 'Husker';

  @override
  String get rememberingSubtitle => 'Fakta og detaljer husket for deg.';

  @override
  String get unlimitedPlan => 'Ubegrenset abonnement';

  @override
  String get managePlan => 'Administrer abonnement';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'Abonnementet ditt vil kanselleres $date.';
  }

  @override
  String renewsOn(String date) {
    return 'Abonnementet ditt fornyes $date.';
  }

  @override
  String get basicPlan => 'Gratis abonnement';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used av $limit min brukt';
  }

  @override
  String get upgrade => 'Oppgrader';

  @override
  String get upgradeToUnlimited => 'Oppgrader til ubegrenset';

  @override
  String basicPlanDesc(int limit) {
    return 'Abonnementet ditt inkluderer $limit gratis minutter per måned. Oppgrader for ubegrenset bruk.';
  }

  @override
  String get shareStatsMessage => 'Deler mine Omi-statistikker! (omi.me - din alltid tilgjengelige AI-assistent)';

  @override
  String get sharePeriodToday => 'I dag har omi:';

  @override
  String get sharePeriodMonth => 'Denne måneden har omi:';

  @override
  String get sharePeriodYear => 'Dette året har omi:';

  @override
  String get sharePeriodAllTime => 'Så langt har omi:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 Lyttet i $minutes minutter';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 Forstått $words ord';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ Gitt $count innsikter';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 Husket $count minner';
  }

  @override
  String get debugLogs => 'Feilsøkingslogger';

  @override
  String get debugLogsAutoDelete => 'Slettes automatisk etter 3 dager.';

  @override
  String get debugLogsDesc => 'Hjelper med å diagnostisere problemer';

  @override
  String get noLogFilesFound => 'Ingen loggfiler funnet.';

  @override
  String get omiDebugLog => 'Omi feilsøkingslogg';

  @override
  String get logShared => 'Logg delt';

  @override
  String get selectLogFile => 'Velg loggfil';

  @override
  String get shareLogs => 'Del logger';

  @override
  String get debugLogCleared => 'Feilsøkingslogg tømt';

  @override
  String get exportStarted => 'Eksport startet. Dette kan ta noen sekunder...';

  @override
  String get exportAllData => 'Eksporter alle data';

  @override
  String get exportDataDesc => 'Eksporter samtaler til en JSON-fil';

  @override
  String get exportedConversations => 'Eksporterte samtaler fra Omi';

  @override
  String get exportShared => 'Eksport delt';

  @override
  String get deleteKnowledgeGraphTitle => 'Slette kunnskapsgraf?';

  @override
  String get deleteKnowledgeGraphMessage =>
      'Dette vil slette alle utledede kunnskapsdata (noder og forbindelser). De originale minnene dine vil forbli trygge. Grafen vil bli gjenoppbygget over tid eller ved neste forespørsel.';

  @override
  String get knowledgeGraphDeleted => 'Kunnskapsgraf slettet';

  @override
  String deleteGraphFailed(String error) {
    return 'Kunne ikke slette graf: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'Slett kunnskapsgraf';

  @override
  String get deleteKnowledgeGraphDesc => 'Tøm alle noder og forbindelser';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'MCP-server';

  @override
  String get mcpServerDesc => 'Koble AI-assistenter til dataene dine';

  @override
  String get serverUrl => 'Server-URL';

  @override
  String get urlCopied => 'URL kopiert';

  @override
  String get apiKeyAuth => 'API-nøkkelautentisering';

  @override
  String get header => 'Topptekst';

  @override
  String get authorizationBearer => 'Authorization: Bearer <key>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'Klient-ID';

  @override
  String get clientSecret => 'Klienthemmelighet';

  @override
  String get useMcpApiKey => 'Bruk din MCP API-nøkkel';

  @override
  String get webhooks => 'Webhooker';

  @override
  String get conversationEvents => 'Samtalehendelser';

  @override
  String get newConversationCreated => 'Ny samtale opprettet';

  @override
  String get realtimeTranscript => 'Sanntidstranskript';

  @override
  String get transcriptReceived => 'Transkripsjon mottatt';

  @override
  String get audioBytes => 'Lydbytes';

  @override
  String get audioDataReceived => 'Lyddata mottatt';

  @override
  String get intervalSeconds => 'Intervall (sekunder)';

  @override
  String get daySummary => 'Dagsammendrag';

  @override
  String get summaryGenerated => 'Sammendrag generert';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'Legg til i claude_desktop_config.json';

  @override
  String get copyConfig => 'Kopier konfigurasjon';

  @override
  String get configCopied => 'Konfigurasjon kopiert til utklippstavlen';

  @override
  String get listeningMins => 'Lytting (min)';

  @override
  String get understandingWords => 'Forståelse (ord)';

  @override
  String get insights => 'Innsikt';

  @override
  String get memories => 'Minner';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '$used av $limit min brukt denne måneden';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '$used av $limit ord brukt denne måneden';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '$used av $limit innsikter fått denne måneden';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return '$used av $limit minner opprettet denne måneden';
  }

  @override
  String get visibility => 'Synlighet';

  @override
  String get visibilitySubtitle => 'Kontroller hvilke samtaler som vises i listen din';

  @override
  String get showShortConversations => 'Vis korte samtaler';

  @override
  String get showShortConversationsDesc => 'Vis samtaler kortere enn terskelen';

  @override
  String get showDiscardedConversations => 'Vis forkastede samtaler';

  @override
  String get showDiscardedConversationsDesc => 'Inkluder samtaler merket som forkastet';

  @override
  String get shortConversationThreshold => 'Terskel for korte samtaler';

  @override
  String get shortConversationThresholdSubtitle =>
      'Samtaler kortere enn dette vil være skjult med mindre aktivert ovenfor';

  @override
  String get durationThreshold => 'Varighetsterskel';

  @override
  String get durationThresholdDesc => 'Skjul samtaler kortere enn dette';

  @override
  String minLabel(int count) {
    return '$count min';
  }

  @override
  String get customVocabularyTitle => 'Tilpasset ordforråd';

  @override
  String get addWords => 'Legg til ord';

  @override
  String get addWordsDesc => 'Navn, termer eller uvanlige ord';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'Koble til';

  @override
  String get comingSoon => 'Kommer snart';

  @override
  String get chatToolsFooter => 'Koble til appene dine for å se data og måledata i chat.';

  @override
  String get completeAuthInBrowser =>
      'Fullfør autentisering i nettleseren din. Når du er ferdig, gå tilbake til appen.';

  @override
  String failedToStartAuth(String appName) {
    return 'Kunne ikke starte $appName-autentisering';
  }

  @override
  String disconnectAppTitle(String appName) {
    return 'Koble fra $appName?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'Er du sikker på at du vil koble fra $appName? Du kan koble til igjen når som helst.';
  }

  @override
  String disconnectedFrom(String appName) {
    return 'Frakoblet fra $appName';
  }

  @override
  String get failedToDisconnect => 'Kunne ikke koble fra';

  @override
  String connectTo(String appName) {
    return 'Koble til $appName';
  }

  @override
  String authAccessMessage(String appName) {
    return 'Du må autorisere Omi til å få tilgang til $appName-dataene dine. Dette vil åpne nettleseren din for autentisering.';
  }

  @override
  String get continueAction => 'Fortsett';

  @override
  String get languageTitle => 'Språk';

  @override
  String get primaryLanguage => 'Primærspråk';

  @override
  String get automaticTranslation => 'Automatisk oversettelse';

  @override
  String get detectLanguages => 'Oppdage 10+ språk';

  @override
  String get authorizeSavingRecordings => 'Autoriser lagring av opptak';

  @override
  String get thanksForAuthorizing => 'Takk for at du autoriserte!';

  @override
  String get needYourPermission => 'Vi trenger din tillatelse';

  @override
  String get alreadyGavePermission =>
      'Du har allerede gitt oss tillatelse til å lagre opptakene dine. Her er en påminnelse om hvorfor vi trenger det:';

  @override
  String get wouldLikePermission => 'Vi vil gjerne ha tillatelse til å lagre stemmeopptakene dine. Her er hvorfor:';

  @override
  String get improveSpeechProfile => 'Forbedre taleprofilen din';

  @override
  String get improveSpeechProfileDesc => 'Vi bruker opptak for å videreutvikle og forbedre din personlige taleprofil.';

  @override
  String get trainFamilyProfiles => 'Tren profiler for venner og familie';

  @override
  String get trainFamilyProfilesDesc =>
      'Opptakene dine hjelper oss med å gjenkjenne og opprette profiler for venner og familie.';

  @override
  String get enhanceTranscriptAccuracy => 'Forbedre transkripsjonsnøyaktighet';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'Etter hvert som modellen vår forbedres, kan vi gi bedre transkripsjon av opptakene dine.';

  @override
  String get legalNotice =>
      'Juridisk merknad: Lovligheten av å ta opp og lagre taledata kan variere avhengig av hvor du befinner deg og hvordan du bruker denne funksjonen. Det er ditt ansvar å sikre overholdelse av lokale lover og forskrifter.';

  @override
  String get alreadyAuthorized => 'Allerede autorisert';

  @override
  String get authorize => 'Autoriser';

  @override
  String get revokeAuthorization => 'Tilbakekall autorisasjon';

  @override
  String get authorizationSuccessful => 'Autorisasjon vellykket!';

  @override
  String get failedToAuthorize => 'Kunne ikke autorisere. Prøv igjen.';

  @override
  String get authorizationRevoked => 'Autorisasjon tilbakekalt.';

  @override
  String get recordingsDeleted => 'Opptak slettet.';

  @override
  String get failedToRevoke => 'Kunne ikke tilbakekalle autorisasjon. Prøv igjen.';

  @override
  String get permissionRevokedTitle => 'Tillatelse tilbakekalt';

  @override
  String get permissionRevokedMessage => 'Vil du at vi skal fjerne alle eksisterende opptak også?';

  @override
  String get yes => 'Ja';

  @override
  String get editName => 'Rediger navn';

  @override
  String get howShouldOmiCallYou => 'Hva skal Omi kalle deg?';

  @override
  String get enterYourName => 'Skriv inn navnet ditt';

  @override
  String get nameCannotBeEmpty => 'Navn kan ikke være tomt';

  @override
  String get nameUpdatedSuccessfully => 'Navn oppdatert!';

  @override
  String get calendarSettings => 'Kalenderinnstillinger';

  @override
  String get calendarProviders => 'Kalenderleverandører';

  @override
  String get macOsCalendar => 'macOS-kalender';

  @override
  String get connectMacOsCalendar => 'Koble til din lokale macOS-kalender';

  @override
  String get googleCalendar => 'Google-kalender';

  @override
  String get syncGoogleAccount => 'Synkroniser med Google-kontoen din';

  @override
  String get showMeetingsMenuBar => 'Vis kommende møter i menylinje';

  @override
  String get showMeetingsMenuBarDesc => 'Vis neste møte og tid til det starter i macOS-menylinjen';

  @override
  String get showEventsNoParticipants => 'Vis hendelser uten deltakere';

  @override
  String get showEventsNoParticipantsDesc => 'Når aktivert, viser Kommende hendelser uten deltakere eller videolenke.';

  @override
  String get yourMeetings => 'Dine møter';

  @override
  String get refresh => 'Oppdater';

  @override
  String get noUpcomingMeetings => 'Ingen kommende møter funnet';

  @override
  String get checkingNextDays => 'Sjekker neste 30 dager';

  @override
  String get tomorrow => 'I morgen';

  @override
  String get googleCalendarComingSoon => 'Google-kalenderintegrasjon kommer snart!';

  @override
  String connectedAsUser(String userId) {
    return 'Tilkoblet som bruker: $userId';
  }

  @override
  String get defaultWorkspace => 'Standard arbeidsområde';

  @override
  String get tasksCreatedInWorkspace => 'Oppgaver vil bli opprettet i dette arbeidsområdet';

  @override
  String get defaultProjectOptional => 'Standard prosjekt (valgfritt)';

  @override
  String get leaveUnselectedTasks => 'La være uvalgt for å opprette oppgaver uten prosjekt';

  @override
  String get noProjectsInWorkspace => 'Ingen prosjekter funnet i dette arbeidsområdet';

  @override
  String get conversationTimeoutDesc => 'Velg hvor lenge du vil vente i stillhet før samtalen avsluttes automatisk:';

  @override
  String get timeout2Minutes => '2 minutter';

  @override
  String get timeout2MinutesDesc => 'Avslutt samtale etter 2 minutters stillhet';

  @override
  String get timeout5Minutes => '5 minutter';

  @override
  String get timeout5MinutesDesc => 'Avslutt samtale etter 5 minutters stillhet';

  @override
  String get timeout10Minutes => '10 minutter';

  @override
  String get timeout10MinutesDesc => 'Avslutt samtale etter 10 minutters stillhet';

  @override
  String get timeout30Minutes => '30 minutter';

  @override
  String get timeout30MinutesDesc => 'Avslutt samtale etter 30 minutters stillhet';

  @override
  String get timeout4Hours => '4 timer';

  @override
  String get timeout4HoursDesc => 'Avslutt samtale etter 4 timers stillhet';

  @override
  String get conversationEndAfterHours => 'Samtaler vil nå avsluttes etter 4 timers stillhet';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Samtaler vil nå avsluttes etter $minutes minutt(er) stillhet';
  }

  @override
  String get tellUsPrimaryLanguage => 'Fortell oss ditt hovedspråk';

  @override
  String get languageForTranscription => 'Angi språket ditt for skarpere transkripsjoner og en personlig opplevelse.';

  @override
  String get singleLanguageModeInfo =>
      'Enkeltspråkmodus er aktivert. Oversettelse er deaktivert for høyere nøyaktighet.';

  @override
  String get searchLanguageHint => 'Søk etter språk med navn eller kode';

  @override
  String get noLanguagesFound => 'Ingen språk funnet';

  @override
  String get skip => 'Hopp over';

  @override
  String languageSetTo(String language) {
    return 'Språk satt til $language';
  }

  @override
  String get failedToSetLanguage => 'Kunne ikke angi språk';

  @override
  String appSettings(String appName) {
    return '$appName-innstillinger';
  }

  @override
  String disconnectFromApp(String appName) {
    return 'Koble fra $appName?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'Dette vil fjerne $appName-autentiseringen din. Du må koble til igjen for å bruke den.';
  }

  @override
  String connectedToApp(String appName) {
    return 'Tilkoblet $appName';
  }

  @override
  String get account => 'Konto';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Handlingspunktene dine vil bli synkronisert til $appName-kontoen din';
  }

  @override
  String get defaultSpace => 'Standard område';

  @override
  String get selectSpaceInWorkspace => 'Velg et område i arbeidsområdet ditt';

  @override
  String get noSpacesInWorkspace => 'Ingen områder funnet i dette arbeidsområdet';

  @override
  String get defaultList => 'Standard liste';

  @override
  String get tasksAddedToList => 'Oppgaver vil bli lagt til denne listen';

  @override
  String get noListsInSpace => 'Ingen lister funnet i dette området';

  @override
  String failedToLoadRepos(String error) {
    return 'Kunne ikke laste inn repositorier: $error';
  }

  @override
  String get defaultRepoSaved => 'Standard repositorium lagret';

  @override
  String get failedToSaveDefaultRepo => 'Kunne ikke lagre standard repositorium';

  @override
  String get defaultRepository => 'Standard repositorium';

  @override
  String get selectDefaultRepoDesc =>
      'Velg et standard repositorium for å opprette problemer. Du kan fortsatt spesifisere et annet repositorium når du oppretter problemer.';

  @override
  String get noReposFound => 'Ingen repositorier funnet';

  @override
  String get private => 'Privat';

  @override
  String updatedDate(String date) {
    return 'Oppdatert $date';
  }

  @override
  String get yesterday => 'I går';

  @override
  String daysAgo(int count) {
    return '$count dager siden';
  }

  @override
  String get oneWeekAgo => '1 uke siden';

  @override
  String weeksAgo(int count) {
    return '$count uker siden';
  }

  @override
  String get oneMonthAgo => '1 måned siden';

  @override
  String monthsAgo(int count) {
    return '$count måneder siden';
  }

  @override
  String get issuesCreatedInRepo => 'Problemer vil bli opprettet i ditt standard repositorium';

  @override
  String get taskIntegrations => 'Oppgaveintegrasjoner';

  @override
  String get configureSettings => 'Konfigurer innstillinger';

  @override
  String get completeAuthBrowser => 'Fullfør autentisering i nettleseren din. Når du er ferdig, gå tilbake til appen.';

  @override
  String failedToStartAppAuth(String appName) {
    return 'Kunne ikke starte $appName-autentisering';
  }

  @override
  String connectToAppTitle(String appName) {
    return 'Koble til $appName';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Du må autorisere Omi til å opprette oppgaver i $appName-kontoen din. Dette vil åpne nettleseren din for autentisering.';
  }

  @override
  String get continueButton => 'Fortsett';

  @override
  String appIntegration(String appName) {
    return '$appName-integrasjon';
  }

  @override
  String integrationComingSoon(String appName) {
    return 'Integrasjon med $appName kommer snart! Vi jobber hardt for å gi deg flere oppgavebehandlingsalternativer.';
  }

  @override
  String get gotIt => 'Skjønner';

  @override
  String get tasksExportedOneApp => 'Oppgaver kan eksporteres til én app om gangen.';

  @override
  String get completeYourUpgrade => 'Fullfør oppgraderingen din';

  @override
  String get importConfiguration => 'Importer konfigurasjon';

  @override
  String get exportConfiguration => 'Eksporter konfigurasjon';

  @override
  String get bringYourOwn => 'Ta med din egen';

  @override
  String get payYourSttProvider => 'Bruk omi fritt. Du betaler bare STT-leverandøren direkte.';

  @override
  String get freeMinutesMonth => '1 200 gratis minutter/måned inkludert. Ubegrenset med ';

  @override
  String get omiUnlimited => 'Omi Ubegrenset';

  @override
  String get hostRequired => 'Vert er påkrevd';

  @override
  String get validPortRequired => 'Gyldig port er påkrevd';

  @override
  String get validWebsocketUrlRequired => 'Gyldig WebSocket-URL er påkrevd (wss://)';

  @override
  String get apiUrlRequired => 'API-URL er påkrevd';

  @override
  String get apiKeyRequired => 'API-nøkkel er påkrevd';

  @override
  String get invalidJsonConfig => 'Ugyldig JSON-konfigurasjon';

  @override
  String errorSaving(String error) {
    return 'Feil ved lagring: $error';
  }

  @override
  String get configCopiedToClipboard => 'Konfigurasjon kopiert til utklippstavlen';

  @override
  String get pasteJsonConfig => 'Lim inn JSON-konfigurasjonen din nedenfor:';

  @override
  String get addApiKeyAfterImport => 'Du må legge til din egen API-nøkkel etter import';

  @override
  String get paste => 'Lim inn';

  @override
  String get import => 'Importer';

  @override
  String get invalidProviderInConfig => 'Ugyldig leverandør i konfigurasjon';

  @override
  String importedConfig(String providerName) {
    return 'Importert $providerName-konfigurasjon';
  }

  @override
  String invalidJson(String error) {
    return 'Ugyldig JSON: $error';
  }

  @override
  String get provider => 'Leverandør';

  @override
  String get live => 'Live';

  @override
  String get onDevice => 'På enhet';

  @override
  String get apiUrl => 'API-URL';

  @override
  String get enterSttHttpEndpoint => 'Skriv inn ditt STT HTTP-endepunkt';

  @override
  String get websocketUrl => 'WebSocket-URL';

  @override
  String get enterLiveSttWebsocket => 'Skriv inn ditt live STT WebSocket-endepunkt';

  @override
  String get apiKey => 'API-nøkkel';

  @override
  String get enterApiKey => 'Skriv inn API-nøkkelen din';

  @override
  String get storedLocallyNeverShared => 'Lagret lokalt, aldri delt';

  @override
  String get host => 'Vert';

  @override
  String get port => 'Port';

  @override
  String get advanced => 'Avansert';

  @override
  String get configuration => 'Konfigurasjon';

  @override
  String get requestConfiguration => 'Forespørselskonfigurasjon';

  @override
  String get responseSchema => 'Responsskjema';

  @override
  String get modified => 'Endret';

  @override
  String get resetRequestConfig => 'Tilbakestill forespørselskonfigurasjon til standard';

  @override
  String get logs => 'Logger';

  @override
  String get logsCopied => 'Logger kopiert';

  @override
  String get noLogsYet => 'Ingen logger ennå. Start opptak for å se tilpasset STT-aktivitet.';

  @override
  String deviceUsesCodec(String deviceName, String codecReason) {
    return '$deviceName bruker $codecReason. Omi vil bli brukt.';
  }

  @override
  String get omiTranscription => 'Omi-transkripsjon';

  @override
  String get bestInClassTranscription => 'Beste transkripsjon i sin klasse uten oppsett';

  @override
  String get instantSpeakerLabels => 'Øyeblikkelige talermerkinger';

  @override
  String get languageTranslation => '100+ språkoversettelser';

  @override
  String get optimizedForConversation => 'Optimalisert for samtaler';

  @override
  String get autoLanguageDetection => 'Automatisk språkdeteksjon';

  @override
  String get highAccuracy => 'Høy nøyaktighet';

  @override
  String get privacyFirst => 'Personvern først';

  @override
  String get saveChanges => 'Lagre endringer';

  @override
  String get resetToDefault => 'Tilbakestill til standard';

  @override
  String get viewTemplate => 'Vis mal';

  @override
  String get trySomethingLike => 'Prøv noe som...';

  @override
  String get tryIt => 'Prøv det';

  @override
  String get creatingPlan => 'Oppretter plan';

  @override
  String get developingLogic => 'Utvikler logikk';

  @override
  String get designingApp => 'Designer app';

  @override
  String get generatingIconStep => 'Genererer ikon';

  @override
  String get finalTouches => 'Siste finpuss';

  @override
  String get processing => 'Behandler...';

  @override
  String get features => 'Funksjoner';

  @override
  String get creatingYourApp => 'Oppretter appen din...';

  @override
  String get generatingIcon => 'Genererer ikon...';

  @override
  String get whatShouldWeMake => 'Hva skal vi lage?';

  @override
  String get appName => 'Appnavn';

  @override
  String get description => 'Beskrivelse';

  @override
  String get publicLabel => 'Offentlig';

  @override
  String get privateLabel => 'Privat';

  @override
  String get free => 'Gratis';

  @override
  String get perMonth => '/ Måned';

  @override
  String get tailoredConversationSummaries => 'Tilpassede samtalesammendrag';

  @override
  String get customChatbotPersonality => 'Tilpasset chatbot-personlighet';

  @override
  String get makePublic => 'Gjør offentlig';

  @override
  String get anyoneCanDiscover => 'Alle kan oppdage appen din';

  @override
  String get onlyYouCanUse => 'Bare du kan bruke denne appen';

  @override
  String get paidApp => 'Betalt app';

  @override
  String get usersPayToUse => 'Brukere betaler for å bruke appen din';

  @override
  String get freeForEveryone => 'Gratis for alle';

  @override
  String get perMonthLabel => '/ måned';

  @override
  String get creating => 'Oppretter...';

  @override
  String get createApp => 'Opprett App';

  @override
  String get searchingForDevices => 'Søker etter enheter...';

  @override
  String devicesFoundNearby(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'ENHETER',
      one: 'ENHET',
    );
    return '$count $_temp0 FUNNET I NÆRHETEN';
  }

  @override
  String get pairingSuccessful => 'PARING VELLYKKET';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Feil ved tilkobling til Apple Watch: $error';
  }

  @override
  String get dontShowAgain => 'Ikke vis igjen';

  @override
  String get iUnderstand => 'Jeg forstår';

  @override
  String get enableBluetooth => 'Aktiver Bluetooth';

  @override
  String get bluetoothNeeded =>
      'Omi trenger Bluetooth for å koble til den bærbare enheten din. Aktiver Bluetooth og prøv igjen.';

  @override
  String get contactSupport => 'Kontakte support?';

  @override
  String get connectLater => 'Koble til senere';

  @override
  String get grantPermissions => 'Gi tillatelser';

  @override
  String get backgroundActivity => 'Bakgrunnsaktivitet';

  @override
  String get backgroundActivityDesc => 'La Omi kjøre i bakgrunnen for bedre stabilitet';

  @override
  String get locationAccess => 'Posisjonstilgang';

  @override
  String get locationAccessDesc => 'Aktiver bakgrunnsposisjon for full opplevelse';

  @override
  String get notifications => 'Varsler';

  @override
  String get notificationsDesc => 'Aktiver varsler for å holde deg informert';

  @override
  String get locationServiceDisabled => 'Posisjonstjeneste deaktivert';

  @override
  String get locationServiceDisabledDesc =>
      'Posisjonstjeneste er deaktivert. Gå til Innstillinger > Personvern og sikkerhet > Posisjonstjenester og aktiver den';

  @override
  String get backgroundLocationDenied => 'Bakgrunnsposisjonstilgang nektet';

  @override
  String get backgroundLocationDeniedDesc =>
      'Gå til enhetsinnstillinger og sett posisjonstillatelse til \"Alltid tillat\"';

  @override
  String get lovingOmi => 'Liker du Omi?';

  @override
  String get leaveReviewIos =>
      'Hjelp oss med å nå flere personer ved å legge igjen en anmeldelse i App Store. Tilbakemeldingen din betyr alt for oss!';

  @override
  String get leaveReviewAndroid =>
      'Hjelp oss med å nå flere personer ved å legge igjen en anmeldelse i Google Play Store. Tilbakemeldingen din betyr alt for oss!';

  @override
  String get rateOnAppStore => 'Vurder i App Store';

  @override
  String get rateOnGooglePlay => 'Vurder i Google Play';

  @override
  String get maybeLater => 'Kanskje senere';

  @override
  String get speechProfileIntro => 'Omi må lære målene og stemmen din. Du kan endre det senere.';

  @override
  String get getStarted => 'Kom i gang';

  @override
  String get allDone => 'Alt ferdig!';

  @override
  String get keepGoing => 'Fortsett, du gjør det bra';

  @override
  String get skipThisQuestion => 'Hopp over dette spørsmålet';

  @override
  String get skipForNow => 'Hopp over foreløpig';

  @override
  String get connectionError => 'Tilkoblingsfeil';

  @override
  String get connectionErrorDesc => 'Kunne ikke koble til serveren. Sjekk internettforbindelsen din og prøv igjen.';

  @override
  String get invalidRecordingMultipleSpeakers => 'Ugyldig opptak oppdaget';

  @override
  String get multipleSpeakersDesc =>
      'Det ser ut til å være flere talere i opptaket. Pass på at du er på et stille sted og prøv igjen.';

  @override
  String get tooShortDesc => 'Det er ikke nok tale oppdaget. Snakk mer og prøv igjen.';

  @override
  String get invalidRecordingDesc => 'Pass på at du snakker i minst 5 sekunder og ikke mer enn 90.';

  @override
  String get areYouThere => 'Er du der?';

  @override
  String get noSpeechDesc =>
      'Vi kunne ikke oppdage noen tale. Pass på å snakke i minst 10 sekunder og ikke mer enn 3 minutter.';

  @override
  String get connectionLost => 'Tilkobling tapt';

  @override
  String get connectionLostDesc => 'Tilkoblingen ble avbrutt. Sjekk internettforbindelsen din og prøv igjen.';

  @override
  String get tryAgain => 'Prøv igjen';

  @override
  String get connectOmiOmiGlass => 'Koble til Omi / OmiGlass';

  @override
  String get continueWithoutDevice => 'Fortsett uten enhet';

  @override
  String get permissionsRequired => 'Tillatelser kreves';

  @override
  String get permissionsRequiredDesc =>
      'Denne appen trenger Bluetooth- og posisjonstillatelser for å fungere ordentlig. Aktiver dem i innstillingene.';

  @override
  String get openSettings => 'Åpne innstillinger';

  @override
  String get wantDifferentName => 'Vil du bli kalt noe annet?';

  @override
  String get whatsYourName => 'Hva heter du?';

  @override
  String get speakTranscribeSummarize => 'Snakk. Transkriber. Sammenfatt.';

  @override
  String get signInWithApple => 'Logg inn med Apple';

  @override
  String get signInWithGoogle => 'Logg inn med Google';

  @override
  String get byContinuingAgree => 'Ved å fortsette godtar du vår ';

  @override
  String get termsOfUse => 'Bruksvilkår';

  @override
  String get omiYourAiCompanion => 'Omi – Din AI-følgesvenn';

  @override
  String get captureEveryMoment => 'Fang hvert øyeblikk. Få AI-drevne\nsammendrag. Aldri ta notater igjen.';

  @override
  String get appleWatchSetup => 'Apple Watch-oppsett';

  @override
  String get permissionRequestedExclaim => 'Tillatelse forespurt!';

  @override
  String get microphonePermission => 'Mikrofontillatelse';

  @override
  String get permissionGrantedNow =>
      'Tillatelse gitt! Nå:\n\nÅpne Omi-appen på klokken din og trykk \"Fortsett\" nedenfor';

  @override
  String get needMicrophonePermission =>
      'Vi trenger mikrofontillatelse.\n\n1. Trykk \"Gi tillatelse\"\n2. Tillat på iPhone\n3. Klokkeapp vil lukkes\n4. Åpne på nytt og trykk \"Fortsett\"';

  @override
  String get grantPermissionButton => 'Gi tillatelse';

  @override
  String get needHelp => 'Trenger du hjelp?';

  @override
  String get troubleshootingSteps =>
      'Feilsøking:\n\n1. Sørg for at Omi er installert på klokken din\n2. Åpne Omi-appen på klokken din\n3. Se etter tillatelsespopup\n4. Trykk \"Tillat\" når du blir bedt om det\n5. App på klokken vil lukkes - åpne den på nytt\n6. Kom tilbake og trykk \"Fortsett\" på iPhone';

  @override
  String get recordingStartedSuccessfully => 'Opptak startet!';

  @override
  String get permissionNotGrantedYet =>
      'Tillatelse ikke gitt ennå. Pass på at du tillot mikrofontilgang og åpnet appen på nytt på klokken din.';

  @override
  String errorRequestingPermission(String error) {
    return 'Feil ved forespørsel om tillatelse: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'Feil ved oppstart av opptak: $error';
  }

  @override
  String get selectPrimaryLanguage => 'Velg hovedspråket ditt';

  @override
  String get languageBenefits => 'Angi språket ditt for skarpere transkripsjoner og en personlig opplevelse';

  @override
  String get whatsYourPrimaryLanguage => 'Hva er ditt hovedspråk?';

  @override
  String get selectYourLanguage => 'Velg språket ditt';

  @override
  String get personalGrowthJourney => 'Din personlige vekstreise med AI som lytter til hvert ord.';

  @override
  String get actionItemsTitle => 'Gjøremål';

  @override
  String get actionItemsDescription => 'Trykk for å redigere • Langt trykk for å velge • Sveip for handlinger';

  @override
  String get tabToDo => 'Å gjøre';

  @override
  String get tabDone => 'Ferdig';

  @override
  String get tabOld => 'Gamle';

  @override
  String get emptyTodoMessage => '🎉 Alt ferdig!\nIngen ventende handlingspunkter';

  @override
  String get emptyDoneMessage => 'Ingen fullførte elementer ennå';

  @override
  String get emptyOldMessage => '✅ Ingen gamle oppgaver';

  @override
  String get noItems => 'Ingen elementer';

  @override
  String get actionItemMarkedIncomplete => 'Handlingspunkt merket som ufullført';

  @override
  String get actionItemCompleted => 'Handlingspunkt fullført';

  @override
  String get deleteActionItemTitle => 'Slett handlingselement';

  @override
  String get deleteActionItemMessage => 'Er du sikker på at du vil slette dette handlingselementet?';

  @override
  String get deleteSelectedItemsTitle => 'Slette valgte elementer';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Er du sikker på at du vil slette $count valgte handlingspunkt$s?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'Handlingspunkt \"$description\" slettet';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count handlingspunkt$s slettet';
  }

  @override
  String get failedToDeleteItem => 'Kunne ikke slette handlingspunkt';

  @override
  String get failedToDeleteItems => 'Kunne ikke slette elementer';

  @override
  String get failedToDeleteSomeItems => 'Kunne ikke slette noen elementer';

  @override
  String get welcomeActionItemsTitle => 'Klar for handlingspunkter';

  @override
  String get welcomeActionItemsDescription =>
      'AI-en din vil automatisk trekke ut oppgaver og gjøremål fra samtalene dine. De vil dukke opp her når de opprettes.';

  @override
  String get autoExtractionFeature => 'Automatisk trukket ut fra samtaler';

  @override
  String get editSwipeFeature => 'Trykk for å redigere, sveip for å fullføre eller slette';

  @override
  String itemsSelected(int count) {
    return '$count valgt';
  }

  @override
  String get selectAll => 'Velg alle';

  @override
  String get deleteSelected => 'Slett valgte';

  @override
  String get searchMemories => 'Søk i minner...';

  @override
  String get memoryDeleted => 'Minne slettet.';

  @override
  String get undo => 'Angre';

  @override
  String get noMemoriesYet => '🧠 Ingen minner ennå';

  @override
  String get noAutoMemories => 'Ingen automatisk uttrukne minner ennå';

  @override
  String get noManualMemories => 'Ingen manuelle minner ennå';

  @override
  String get noMemoriesInCategories => 'Ingen minner i disse kategoriene';

  @override
  String get noMemoriesFound => '🔍 Ingen minner funnet';

  @override
  String get addFirstMemory => 'Legg til ditt første minne';

  @override
  String get clearMemoryTitle => 'Tømme Omis minne';

  @override
  String get clearMemoryMessage => 'Er du sikker på at du vil tømme Omis minne? Dette kan ikke angres.';

  @override
  String get clearMemoryButton => 'Tøm minne';

  @override
  String get memoryClearedSuccess => 'Omis minne om deg har blitt tømt';

  @override
  String get noMemoriesToDelete => 'Ingen minner å slette';

  @override
  String get createMemoryTooltip => 'Opprett nytt minne';

  @override
  String get createActionItemTooltip => 'Opprett nytt handlingspunkt';

  @override
  String get memoryManagement => 'Minnehåndtering';

  @override
  String get filterMemories => 'Filtrer minner';

  @override
  String totalMemoriesCount(int count) {
    return 'Du har $count totale minner';
  }

  @override
  String get publicMemories => 'Offentlige minner';

  @override
  String get privateMemories => 'Private minner';

  @override
  String get makeAllPrivate => 'Gjør alle minner private';

  @override
  String get makeAllPublic => 'Gjør alle minner offentlige';

  @override
  String get deleteAllMemories => 'Slett alle minner';

  @override
  String get allMemoriesPrivateResult => 'Alle minner er nå private';

  @override
  String get allMemoriesPublicResult => 'Alle minner er nå offentlige';

  @override
  String get newMemory => '✨ Nytt minne';

  @override
  String get editMemory => '✏️ Rediger minne';

  @override
  String get memoryContentHint => 'Jeg liker å spise iskrem...';

  @override
  String get failedToSaveMemory => 'Kunne ikke lagre. Sjekk forbindelsen din.';

  @override
  String get saveMemory => 'Lagre minne';

  @override
  String get retry => 'Prøv igjen';

  @override
  String get createActionItem => 'Opprett handlingselement';

  @override
  String get editActionItem => 'Rediger handlingselement';

  @override
  String get actionItemDescriptionHint => 'Hva må gjøres?';

  @override
  String get actionItemDescriptionEmpty => 'Beskrivelse av handlingspunkt kan ikke være tom.';

  @override
  String get actionItemUpdated => 'Handlingspunkt oppdatert';

  @override
  String get failedToUpdateActionItem => 'Kunne ikke oppdatere handlingselement';

  @override
  String get actionItemCreated => 'Handlingspunkt opprettet';

  @override
  String get failedToCreateActionItem => 'Kunne ikke opprette handlingselement';

  @override
  String get dueDate => 'Forfallsdato';

  @override
  String get time => 'Tid';

  @override
  String get addDueDate => 'Legg til forfallsdato';

  @override
  String get pressDoneToSave => 'Trykk ferdig for å lagre';

  @override
  String get pressDoneToCreate => 'Trykk ferdig for å opprette';

  @override
  String get filterAll => 'Alle';

  @override
  String get filterSystem => 'Om deg';

  @override
  String get filterInteresting => 'Innsikter';

  @override
  String get filterManual => 'Manuell';

  @override
  String get completed => 'Fullført';

  @override
  String get markComplete => 'Marker som fullført';

  @override
  String get actionItemDeleted => 'Handlingselement slettet';

  @override
  String get failedToDeleteActionItem => 'Kunne ikke slette handlingselement';

  @override
  String get deleteActionItemConfirmTitle => 'Slette handlingspunkt';

  @override
  String get deleteActionItemConfirmMessage => 'Er du sikker på at du vil slette dette handlingspunktet?';

  @override
  String get appLanguage => 'Appspråk';

  @override
  String get appInterfaceSectionTitle => 'APP-GRENSESNITT';

  @override
  String get speechTranscriptionSectionTitle => 'TALE OG TRANSKRIPSJON';

  @override
  String get languageSettingsHelperText =>
      'App-språk endrer menyer og knapper. Talespråk påvirker hvordan opptakene dine transkriberes.';

  @override
  String get translationNotice => 'Oversettelsesvarsel';

  @override
  String get translationNoticeMessage =>
      'Omi oversetter samtaler til hovedspråket ditt. Oppdater det når som helst i Innstillinger → Profiler.';

  @override
  String get pleaseCheckInternetConnection => 'Vennligst sjekk internettforbindelsen din og prøv igjen';

  @override
  String get pleaseSelectReason => 'Vennligst velg en grunn';

  @override
  String get tellUsMoreWhatWentWrong => 'Fortell oss mer om hva som gikk galt...';

  @override
  String get selectText => 'Velg tekst';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Maksimum $count mål tillatt';
  }

  @override
  String get conversationCannotBeMerged => 'Denne samtalen kan ikke slås sammen (låst eller allerede slås sammen)';

  @override
  String get pleaseEnterFolderName => 'Vennligst skriv inn et mappenavn';

  @override
  String get failedToCreateFolder => 'Kunne ikke opprette mappe';

  @override
  String get failedToUpdateFolder => 'Kunne ikke oppdatere mappe';

  @override
  String get folderName => 'Mappenavn';

  @override
  String get descriptionOptional => 'Beskrivelse (valgfritt)';

  @override
  String get failedToDeleteFolder => 'Kunne ikke slette mappe';

  @override
  String get editFolder => 'Rediger mappe';

  @override
  String get deleteFolder => 'Slett mappe';

  @override
  String get transcriptCopiedToClipboard => 'Transkript kopiert til utklippstavlen';

  @override
  String get summaryCopiedToClipboard => 'Sammendrag kopiert til utklippstavle';

  @override
  String get conversationUrlCouldNotBeShared => 'Samtale-URL kunne ikke deles.';

  @override
  String get urlCopiedToClipboard => 'URL kopiert til utklippstavlen';

  @override
  String get exportTranscript => 'Eksporter transkript';

  @override
  String get exportSummary => 'Eksporter sammendrag';

  @override
  String get exportButton => 'Eksporter';

  @override
  String get actionItemsCopiedToClipboard => 'Handlingspunkter kopiert til utklippstavlen';

  @override
  String get summarize => 'Oppsummer';

  @override
  String get generateSummary => 'Generer sammendrag';

  @override
  String get conversationNotFoundOrDeleted => 'Samtale ikke funnet eller har blitt slettet';

  @override
  String get deleteMemory => 'Slett minne';

  @override
  String get thisActionCannotBeUndone => 'Denne handlingen kan ikke angres.';

  @override
  String memoriesCount(int count) {
    return '$count minner';
  }

  @override
  String get noMemoriesInCategory => 'Ingen minner i denne kategorien ennå';

  @override
  String get addYourFirstMemory => 'Legg til ditt første minne';

  @override
  String get firmwareDisconnectUsb => 'Koble fra USB';

  @override
  String get firmwareUsbWarning => 'USB-tilkobling under oppdateringer kan skade enheten din.';

  @override
  String get firmwareBatteryAbove15 => 'Batteri over 15%';

  @override
  String get firmwareEnsureBattery => 'Sørg for at enheten din har 15% batteri.';

  @override
  String get firmwareStableConnection => 'Stabil tilkobling';

  @override
  String get firmwareConnectWifi => 'Koble til WiFi eller mobildata.';

  @override
  String failedToStartUpdate(String error) {
    return 'Kunne ikke starte oppdatering: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'Før oppdatering, sørg for:';

  @override
  String get confirmed => 'Bekreftet!';

  @override
  String get release => 'Slipp';

  @override
  String get slideToUpdate => 'Gli for å oppdatere';

  @override
  String copiedToClipboard(String title) {
    return '$title kopiert til utklippstavlen';
  }

  @override
  String get batteryLevel => 'Batterinivå';

  @override
  String get productUpdate => 'Produktoppdatering';

  @override
  String get offline => 'Frakoblet';

  @override
  String get available => 'Tilgjengelig';

  @override
  String get unpairDeviceDialogTitle => 'Opphev sammenkoblingen av enheten';

  @override
  String get unpairDeviceDialogMessage =>
      'Dette vil oppheve sammenkoblingen av enheten slik at den kan kobles til en annen telefon. Du må gå til Innstillinger > Bluetooth og glemme enheten for å fullføre prosessen.';

  @override
  String get unpair => 'Opphev sammenkobling';

  @override
  String get unpairAndForgetDevice => 'Opphev sammenkobling og glem enheten';

  @override
  String get unknownDevice => 'Ukjent enhet';

  @override
  String get unknown => 'Ukjent';

  @override
  String get productName => 'Produktnavn';

  @override
  String get serialNumber => 'Serienummer';

  @override
  String get connected => 'Tilkoblet';

  @override
  String get privacyPolicyTitle => 'Personvernregler';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label copied';
  }

  @override
  String get noApiKeysYet => 'Ingen API-nøkler ennå. Opprett en for å integrere med appen din.';

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
  String get debugAndDiagnostics => 'Feilsøking og diagnostikk';

  @override
  String get autoDeletesAfter3Days => 'Slettes automatisk etter 3 dager';

  @override
  String get helpsDiagnoseIssues => 'Hjelper med å diagnostisere problemer';

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
  String get realTimeTranscript => 'Sanntidstranskript';

  @override
  String get experimental => 'Eksperimentell';

  @override
  String get transcriptionDiagnostics => 'Transkripsjon-diagnostikk';

  @override
  String get detailedDiagnosticMessages => 'Detaljerte diagnostiske meldinger';

  @override
  String get autoCreateSpeakers => 'Opprett talere automatisk';

  @override
  String get autoCreateWhenNameDetected => 'Auto-create when name detected';

  @override
  String get followUpQuestions => 'Oppfølgingsspørsmål';

  @override
  String get suggestQuestionsAfterConversations => 'Foreslå spørsmål etter samtaler';

  @override
  String get goalTracker => 'Målsporer';

  @override
  String get trackPersonalGoalsOnHomepage => 'Track your personal goals on homepage';

  @override
  String get dailyReflection => 'Daglig refleksjon';

  @override
  String get get9PmReminderToReflect => 'Get a 9 PM reminder to reflect on your day';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'Handlingselementbeskrivelse kan ikke være tom';

  @override
  String get saved => 'Lagret';

  @override
  String get overdue => 'Forsinket';

  @override
  String get failedToUpdateDueDate => 'Kunne ikke oppdatere forfallsdato';

  @override
  String get markIncomplete => 'Marker som ufullstendig';

  @override
  String get editDueDate => 'Rediger forfallsdato';

  @override
  String get setDueDate => 'Angi forfallsdato';

  @override
  String get clearDueDate => 'Fjern forfallsdato';

  @override
  String get failedToClearDueDate => 'Kunne ikke fjerne forfallsdato';

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
  String get howDoesItWork => 'Hvordan fungerer det?';

  @override
  String get sdCardSyncDescription => 'SD-kortsynkronisering vil importere minnene dine fra SD-kortet til appen';

  @override
  String get checksForAudioFiles => 'Sjekker for lydfiler på SD-kortet';

  @override
  String get omiSyncsAudioFiles => 'Omi synkroniserer deretter lydfilene med serveren';

  @override
  String get serverProcessesAudio => 'Serveren behandler lydfilene og oppretter minner';

  @override
  String get youreAllSet => 'Du er klar!';

  @override
  String get welcomeToOmiDescription =>
      'Velkommen til Omi! Din AI-følgesvenn er klar til å hjelpe deg med samtaler, oppgaver og mer.';

  @override
  String get startUsingOmi => 'Begynn å bruke Omi';

  @override
  String get back => 'Tilbake';

  @override
  String get keyboardShortcuts => 'Tastatursnarveier';

  @override
  String get toggleControlBar => 'Veksle kontrollinje';

  @override
  String get pressKeys => 'Trykk taster...';

  @override
  String get cmdRequired => '⌘ påkrevd';

  @override
  String get invalidKey => 'Ugyldig tast';

  @override
  String get space => 'Mellomrom';

  @override
  String get search => 'Søk';

  @override
  String get searchPlaceholder => 'Søk...';

  @override
  String get untitledConversation => 'Navnløs samtale';

  @override
  String countRemaining(String count) {
    return '$count gjenstående';
  }

  @override
  String get addGoal => 'Legg til mål';

  @override
  String get editGoal => 'Rediger mål';

  @override
  String get icon => 'Ikon';

  @override
  String get goalTitle => 'Måltittel';

  @override
  String get current => 'Nåværende';

  @override
  String get target => 'Mål';

  @override
  String get saveGoal => 'Lagre';

  @override
  String get goals => 'Mål';

  @override
  String get tapToAddGoal => 'Trykk for å legge til et mål';

  @override
  String welcomeBack(String name) {
    return 'Velkommen tilbake, $name';
  }

  @override
  String get yourConversations => 'Dine samtaler';

  @override
  String get reviewAndManageConversations => 'Gjennomgå og administrer dine registrerte samtaler';

  @override
  String get startCapturingConversations => 'Begynn å fange opp samtaler med Omi-enheten din for å se dem her.';

  @override
  String get useMobileAppToCapture => 'Bruk mobilappen din til å ta opp lyd';

  @override
  String get conversationsProcessedAutomatically => 'Samtaler behandles automatisk';

  @override
  String get getInsightsInstantly => 'Få innsikt og sammendrag øyeblikkelig';

  @override
  String get showAll => 'Vis alle →';

  @override
  String get noTasksForToday => 'Ingen oppgaver for i dag.\\nSpør Omi om flere oppgaver eller opprett manuelt.';

  @override
  String get dailyScore => 'DAGLIG POENGSUM';

  @override
  String get dailyScoreDescription => 'En poengsum som hjelper deg med å fokusere bedre på gjennomføring.';

  @override
  String get searchResults => 'Søkeresultater';

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
  String get loadingTasks => 'Laster oppgaver...';

  @override
  String get tasks => 'Oppgaver';

  @override
  String get swipeTasksToIndent => 'Sveip oppgaver for innrykk, dra mellom kategorier';

  @override
  String get create => 'Opprett';

  @override
  String get noTasksYet => 'Ingen oppgaver ennå';

  @override
  String get tasksFromConversationsWillAppear =>
      'Oppgaver fra samtalene dine vises her.\nKlikk på Opprett for å legge til en manuelt.';

  @override
  String get monthJan => 'Jan';

  @override
  String get monthFeb => 'Feb';

  @override
  String get monthMar => 'Mar';

  @override
  String get monthApr => 'Apr';

  @override
  String get monthMay => 'Mai';

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
  String get monthDec => 'Des';

  @override
  String get timePM => 'PM';

  @override
  String get timeAM => 'AM';

  @override
  String get actionItemUpdatedSuccessfully => 'Handlingselement oppdatert';

  @override
  String get actionItemCreatedSuccessfully => 'Handlingselement opprettet';

  @override
  String get actionItemDeletedSuccessfully => 'Handlingselement slettet';

  @override
  String get deleteActionItem => 'Slett handlingselement';

  @override
  String get deleteActionItemConfirmation =>
      'Er du sikker på at du vil slette dette handlingselementet? Denne handlingen kan ikke angres.';

  @override
  String get enterActionItemDescription => 'Skriv inn beskrivelse av handlingselement...';

  @override
  String get markAsCompleted => 'Merk som fullført';

  @override
  String get setDueDateAndTime => 'Angi forfallsdato og klokkeslett';

  @override
  String get reloadingApps => 'Laster inn apper på nytt...';

  @override
  String get loadingApps => 'Laster inn apper...';

  @override
  String get browseInstallCreateApps => 'Bla gjennom, installer og opprett apper';

  @override
  String get all => 'Alle';

  @override
  String get open => 'Åpne';

  @override
  String get install => 'Installer';

  @override
  String get noAppsAvailable => 'Ingen apper tilgjengelige';

  @override
  String get unableToLoadApps => 'Kan ikke laste inn apper';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'Prøv å justere søkeordene eller filtrene dine';

  @override
  String get checkBackLaterForNewApps => 'Sjekk tilbake senere for nye apper';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'Vennligst sjekk internettilkoblingen din og prøv igjen';

  @override
  String get createNewApp => 'Opprett ny app';

  @override
  String get buildSubmitCustomOmiApp => 'Bygg og send inn din tilpassede Omi-app';

  @override
  String get submittingYourApp => 'Sender inn appen din...';

  @override
  String get preparingFormForYou => 'Forbereder skjemaet for deg...';

  @override
  String get appDetails => 'App-detaljer';

  @override
  String get paymentDetails => 'Betalingsdetaljer';

  @override
  String get previewAndScreenshots => 'Forhåndsvisning og skjermbilder';

  @override
  String get appCapabilities => 'App-funksjoner';

  @override
  String get aiPrompts => 'AI-instrukser';

  @override
  String get chatPrompt => 'Chat-instruksjon';

  @override
  String get chatPromptPlaceholder =>
      'Du er en fantastisk app, jobben din er å svare på brukerforespørsler og få dem til å føle seg bra...';

  @override
  String get conversationPrompt => 'Samtaleprompt';

  @override
  String get conversationPromptPlaceholder =>
      'Du er en fantastisk app, du vil få en transkripsjon og sammendrag av en samtale...';

  @override
  String get notificationScopes => 'Varslingsområder';

  @override
  String get appPrivacyAndTerms => 'App-personvern og -vilkår';

  @override
  String get makeMyAppPublic => 'Gjør appen min offentlig';

  @override
  String get submitAppTermsAgreement =>
      'Ved å sende inn denne appen godtar jeg Omi AI sine tjenestevilkår og personvernerklæring';

  @override
  String get submitApp => 'Send inn app';

  @override
  String get needHelpGettingStarted => 'Trenger du hjelp til å komme i gang?';

  @override
  String get clickHereForAppBuildingGuides => 'Klikk her for app-byggingsveiledninger og dokumentasjon';

  @override
  String get submitAppQuestion => 'Send inn app?';

  @override
  String get submitAppPublicDescription =>
      'Appen din vil bli gjennomgått og gjort offentlig. Du kan begynne å bruke den umiddelbart, selv under gjennomgangen!';

  @override
  String get submitAppPrivateDescription =>
      'Appen din vil bli gjennomgått og gjort tilgjengelig for deg privat. Du kan begynne å bruke den umiddelbart, selv under gjennomgangen!';

  @override
  String get startEarning => 'Begynn å tjene! 💰';

  @override
  String get connectStripeOrPayPal => 'Koble til Stripe eller PayPal for å motta betalinger for appen din.';

  @override
  String get connectNow => 'Koble til nå';

  @override
  String installsCount(String count) {
    return '$count+ installasjoner';
  }

  @override
  String get uninstallApp => 'Avinstaller app';

  @override
  String get subscribe => 'Abonner';

  @override
  String get dataAccessNotice => 'Datatilgangsvarsel';

  @override
  String get dataAccessWarning =>
      'Denne appen vil få tilgang til dataene dine. Omi AI er ikke ansvarlig for hvordan dataene dine brukes, endres eller slettes av denne appen';

  @override
  String get installApp => 'Installer app';

  @override
  String get betaTesterNotice =>
      'Du er betatester for denne appen. Den er ikke offentlig ennå. Den vil bli offentlig når den er godkjent.';

  @override
  String get appUnderReviewOwner =>
      'Appen din er under vurdering og bare synlig for deg. Den vil bli offentlig når den er godkjent.';

  @override
  String get appRejectedNotice =>
      'Appen din har blitt avvist. Vennligst oppdater appdetaljene og send inn på nytt for vurdering.';

  @override
  String get setupSteps => 'Oppsettstrinn';

  @override
  String get setupInstructions => 'Oppsettsanvisninger';

  @override
  String get integrationInstructions => 'Integrasjonsanvisninger';

  @override
  String get preview => 'Forhåndsvisning';

  @override
  String get aboutTheApp => 'Om appen';

  @override
  String get aboutThePersona => 'Om personaen';

  @override
  String get chatPersonality => 'Chatpersonlighet';

  @override
  String get ratingsAndReviews => 'Vurderinger og anmeldelser';

  @override
  String get noRatings => 'ingen vurderinger';

  @override
  String ratingsCount(String count) {
    return '$count+ vurderinger';
  }

  @override
  String get errorActivatingApp => 'Feil ved aktivering av app';

  @override
  String get integrationSetupRequired => 'Hvis dette er en integrasjonsapp, sørg for at oppsettet er fullført.';

  @override
  String get installed => 'Installert';

  @override
  String get appIdLabel => 'App-ID';

  @override
  String get appNameLabel => 'Appnavn';

  @override
  String get appNamePlaceholder => 'Min fantastiske app';

  @override
  String get pleaseEnterAppName => 'Vennligst oppgi appnavn';

  @override
  String get categoryLabel => 'Kategori';

  @override
  String get selectCategory => 'Velg kategori';

  @override
  String get descriptionLabel => 'Beskrivelse';

  @override
  String get appDescriptionPlaceholder =>
      'Min fantastiske app er en flott app som gjør fantastiske ting. Det er den beste appen!';

  @override
  String get pleaseProvideValidDescription => 'Vennligst oppgi en gyldig beskrivelse';

  @override
  String get appPricingLabel => 'App-priser';

  @override
  String get noneSelected => 'Ingen valgt';

  @override
  String get appIdCopiedToClipboard => 'App-ID kopiert til utklippstavle';

  @override
  String get appCategoryModalTitle => 'App-kategori';

  @override
  String get pricingFree => 'Gratis';

  @override
  String get pricingPaid => 'Betalt';

  @override
  String get loadingCapabilities => 'Laster inn funksjoner...';

  @override
  String get filterInstalled => 'Installert';

  @override
  String get filterMyApps => 'Mine apper';

  @override
  String get clearSelection => 'Tøm valg';

  @override
  String get filterCategory => 'Kategori';

  @override
  String get rating4PlusStars => '4+ stjerner';

  @override
  String get rating3PlusStars => '3+ stjerner';

  @override
  String get rating2PlusStars => '2+ stjerner';

  @override
  String get rating1PlusStars => '1+ stjerne';

  @override
  String get filterRating => 'Vurdering';

  @override
  String get filterCapabilities => 'Funksjoner';

  @override
  String get noNotificationScopesAvailable => 'Ingen varslingsområder tilgjengelig';

  @override
  String get popularApps => 'Populære apper';

  @override
  String get pleaseProvidePrompt => 'Vennligst oppgi en ledetekst';

  @override
  String chatWithAppName(String appName) {
    return 'Chat med $appName';
  }

  @override
  String get defaultAiAssistant => 'Standard AI-assistent';

  @override
  String get readyToChat => '✨ Klar til å chatte!';

  @override
  String get connectionNeeded => '🌐 Tilkobling kreves';

  @override
  String get startConversation => 'Start en samtale og la magien begynne';

  @override
  String get checkInternetConnection => 'Vennligst sjekk internettforbindelsen din';

  @override
  String get wasThisHelpful => 'Var dette nyttig?';

  @override
  String get thankYouForFeedback => 'Takk for tilbakemeldingen!';

  @override
  String get maxFilesUploadError => 'Du kan bare laste opp 4 filer om gangen';

  @override
  String get attachedFiles => '📎 Vedlagte filer';

  @override
  String get takePhoto => 'Ta et bilde';

  @override
  String get captureWithCamera => 'Ta opp med kamera';

  @override
  String get selectImages => 'Velg bilder';

  @override
  String get chooseFromGallery => 'Velg fra galleri';

  @override
  String get selectFile => 'Velg en fil';

  @override
  String get chooseAnyFileType => 'Velg hvilken som helst filtype';

  @override
  String get cannotReportOwnMessages => 'Du kan ikke rapportere dine egne meldinger';

  @override
  String get messageReportedSuccessfully => '✅ Melding rapportert';

  @override
  String get confirmReportMessage => 'Er du sikker på at du vil rapportere denne meldingen?';

  @override
  String get selectChatAssistant => 'Velg chat-assistent';

  @override
  String get enableMoreApps => 'Aktiver flere apper';

  @override
  String get chatCleared => 'Chat tømt';

  @override
  String get clearChatTitle => 'Tøm chat?';

  @override
  String get confirmClearChat => 'Er du sikker på at du vil tømme chatten? Denne handlingen kan ikke angres.';

  @override
  String get copy => 'Kopiér';

  @override
  String get share => 'Del';

  @override
  String get report => 'Rapporter';

  @override
  String get microphonePermissionRequired => 'Mikrofontillatelse kreves for stemmeoptak.';

  @override
  String get microphonePermissionDenied =>
      'Mikrofontillatelse nektet. Vennligst gi tillatelse i Systeminnstillinger > Personvern og sikkerhet > Mikrofon.';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'Kunne ikke sjekke mikrofontillatelse: $error';
  }

  @override
  String get failedToTranscribeAudio => 'Kunne ikke transkribere lyd';

  @override
  String get transcribing => 'Transkriberer...';

  @override
  String get transcriptionFailed => 'Transkripsjon mislyktes';

  @override
  String get discardedConversation => 'Forkastet samtale';

  @override
  String get at => 'kl.';

  @override
  String get from => 'fra';

  @override
  String get copied => 'Kopiert!';

  @override
  String get copyLink => 'Kopier lenke';

  @override
  String get hideTranscript => 'Skjul transkripsjon';

  @override
  String get viewTranscript => 'Vis transkripsjon';

  @override
  String get conversationDetails => 'Samtaledetaljer';

  @override
  String get transcript => 'Transkripsjon';

  @override
  String segmentsCount(int count) {
    return '$count segmenter';
  }

  @override
  String get noTranscriptAvailable => 'Ingen transkripsjon tilgjengelig';

  @override
  String get noTranscriptMessage => 'Denne samtalen har ikke en transkripsjon.';

  @override
  String get conversationUrlCouldNotBeGenerated => 'Samtale-URL kunne ikke genereres.';

  @override
  String get failedToGenerateConversationLink => 'Kunne ikke generere samtalelenke';

  @override
  String get failedToGenerateShareLink => 'Kunne ikke generere delingslenke';

  @override
  String get reloadingConversations => 'Laster samtaler på nytt...';

  @override
  String get user => 'Bruker';

  @override
  String get starred => 'Stjerne';

  @override
  String get date => 'Dato';

  @override
  String get noResultsFound => 'Ingen resultater funnet';

  @override
  String get tryAdjustingSearchTerms => 'Prøv å justere søkeordene dine';

  @override
  String get starConversationsToFindQuickly => 'Merk samtaler med stjerne for å finne dem raskt her';

  @override
  String noConversationsOnDate(String date) {
    return 'Ingen samtaler $date';
  }

  @override
  String get trySelectingDifferentDate => 'Prøv å velge en annen dato';

  @override
  String get conversations => 'Samtaler';

  @override
  String get chat => 'Chat';

  @override
  String get actions => 'Handlinger';

  @override
  String get syncAvailable => 'Synkronisering tilgjengelig';

  @override
  String get referAFriend => 'Henvis en venn';

  @override
  String get help => 'Hjelp';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'Oppgrader til Pro';

  @override
  String get getOmiDevice => 'Få Omi-enhet';

  @override
  String get wearableAiCompanion => 'Bærbar AI-følgesvenn';

  @override
  String get loadingMemories => 'Laster minner...';

  @override
  String get allMemories => 'Alle minner';

  @override
  String get aboutYou => 'Om deg';

  @override
  String get manual => 'Manuell';

  @override
  String get loadingYourMemories => 'Laster minnene dine...';

  @override
  String get createYourFirstMemory => 'Opprett ditt første minne for å komme i gang';

  @override
  String get tryAdjustingFilter => 'Prøv å justere søket eller filteret ditt';

  @override
  String get whatWouldYouLikeToRemember => 'Hva vil du huske?';

  @override
  String get category => 'Kategori';

  @override
  String get public => 'Offentlig';

  @override
  String get failedToSaveCheckConnection => 'Kunne ikke lagre. Sjekk tilkoblingen din.';

  @override
  String get createMemory => 'Opprett minne';

  @override
  String get deleteMemoryConfirmation =>
      'Er du sikker på at du vil slette dette minnet? Denne handlingen kan ikke angres.';

  @override
  String get makePrivate => 'Gjør privat';

  @override
  String get organizeAndControlMemories => 'Organiser og kontroller minnene dine';

  @override
  String get total => 'Totalt';

  @override
  String get makeAllMemoriesPrivate => 'Gjør alle minner private';

  @override
  String get setAllMemoriesToPrivate => 'Sett alle minner til privat synlighet';

  @override
  String get makeAllMemoriesPublic => 'Gjør alle minner offentlige';

  @override
  String get setAllMemoriesToPublic => 'Sett alle minner til offentlig synlighet';

  @override
  String get permanentlyRemoveAllMemories => 'Fjern permanent alle minner fra Omi';

  @override
  String get allMemoriesAreNowPrivate => 'Alle minner er nå private';

  @override
  String get allMemoriesAreNowPublic => 'Alle minner er nå offentlige';

  @override
  String get clearOmisMemory => 'Tøm Omis minne';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Er du sikker på at du vil tømme Omis minne? Denne handlingen kan ikke angres og vil permanent slette alle $count minner.';
  }

  @override
  String get omisMemoryCleared => 'Omis minne om deg er tømt';

  @override
  String get welcomeToOmi => 'Velkommen til Omi';

  @override
  String get continueWithApple => 'Fortsett med Apple';

  @override
  String get continueWithGoogle => 'Fortsett med Google';

  @override
  String get byContinuingYouAgree => 'Ved å fortsette godtar du våre ';

  @override
  String get termsOfService => 'Tjenestevilkår';

  @override
  String get and => ' og ';

  @override
  String get dataAndPrivacy => 'Data og personvern';

  @override
  String get secureAuthViaAppleId => 'Sikker autentisering via Apple ID';

  @override
  String get secureAuthViaGoogleAccount => 'Sikker autentisering via Google-konto';

  @override
  String get whatWeCollect => 'Hva vi samler inn';

  @override
  String get dataCollectionMessage =>
      'Ved å fortsette vil samtalene, opptakene og personlige informasjon bli sikkert lagret på våre servere for å gi AI-drevne innsikter og aktivere alle appfunksjoner.';

  @override
  String get dataProtection => 'Databeskyttelse';

  @override
  String get yourDataIsProtected => 'Dataene dine er beskyttet og styres av vår ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'Vennligst velg ditt primære språk';

  @override
  String get chooseYourLanguage => 'Velg språket ditt';

  @override
  String get selectPreferredLanguageForBestExperience => 'Velg ditt foretrukne språk for den beste Omi-opplevelsen';

  @override
  String get searchLanguages => 'Søk språk...';

  @override
  String get selectALanguage => 'Velg et språk';

  @override
  String get tryDifferentSearchTerm => 'Prøv et annet søkeord';

  @override
  String get pleaseEnterYourName => 'Vennligst skriv inn navnet ditt';

  @override
  String get nameMustBeAtLeast2Characters => 'Navnet må være minst 2 tegn';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'Fortell oss hvordan du vil bli tiltalt. Dette hjelper til med å personalisere Omi-opplevelsen din.';

  @override
  String charactersCount(int count) {
    return '$count tegn';
  }

  @override
  String get enableFeaturesForBestExperience => 'Aktiver funksjoner for den beste Omi-opplevelsen på enheten din.';

  @override
  String get microphoneAccess => 'Mikrofontilgang';

  @override
  String get recordAudioConversations => 'Ta opp lydsamtaler';

  @override
  String get microphoneAccessDescription =>
      'Omi trenger mikrofontilgang for å ta opp samtalene dine og gi transkripsjoner.';

  @override
  String get screenRecording => 'Skjermopptak';

  @override
  String get captureSystemAudioFromMeetings => 'Fang opp systemlyd fra møter';

  @override
  String get screenRecordingDescription =>
      'Omi trenger tillatelse til skjermopptak for å fange opp systemlyd fra nettleserbaserte møter.';

  @override
  String get accessibility => 'Tilgjengelighet';

  @override
  String get detectBrowserBasedMeetings => 'Oppdag nettleserbaserte møter';

  @override
  String get accessibilityDescription =>
      'Omi trenger tilgjengelighetstillatelse for å oppdage når du deltar i Zoom-, Meet- eller Teams-møter i nettleseren din.';

  @override
  String get pleaseWait => 'Vennligst vent...';

  @override
  String get joinTheCommunity => 'Bli med i fellesskapet!';

  @override
  String get loadingProfile => 'Laster profil...';

  @override
  String get profileSettings => 'Profilinnstillinger';

  @override
  String get noEmailSet => 'Ingen e-post angitt';

  @override
  String get userIdCopiedToClipboard => 'Bruker-ID kopiert';

  @override
  String get yourInformation => 'Din Informasjon';

  @override
  String get setYourName => 'Angi navnet ditt';

  @override
  String get changeYourName => 'Endre navnet ditt';

  @override
  String get manageYourOmiPersona => 'Administrer din Omi-persona';

  @override
  String get voiceAndPeople => 'Stemme og Personer';

  @override
  String get teachOmiYourVoice => 'Lær Omi stemmen din';

  @override
  String get tellOmiWhoSaidIt => 'Fortell Omi hvem som sa det 🗣️';

  @override
  String get payment => 'Betaling';

  @override
  String get addOrChangeYourPaymentMethod => 'Legg til eller endre betalingsmetode';

  @override
  String get preferences => 'Innstillinger';

  @override
  String get helpImproveOmiBySharing => 'Hjelp til med å forbedre Omi ved å dele anonymiserte analysedata';

  @override
  String get deleteAccount => 'Slett Konto';

  @override
  String get deleteYourAccountAndAllData => 'Slett kontoen din og alle data';

  @override
  String get clearLogs => 'Tøm logger';

  @override
  String get debugLogsCleared => 'Feilsøkingslogger tømt';

  @override
  String get exportConversations => 'Eksporter samtaler';

  @override
  String get exportAllConversationsToJson => 'Eksporter alle samtalene dine til en JSON-fil.';

  @override
  String get conversationsExportStarted => 'Eksport av samtaler startet. Dette kan ta noen sekunder, vennligst vent.';

  @override
  String get mcpDescription =>
      'For å koble Omi til andre applikasjoner for å lese, søke og administrere minnene og samtalene dine. Opprett en nøkkel for å komme i gang.';

  @override
  String get apiKeys => 'API-nøkler';

  @override
  String errorLabel(String error) {
    return 'Feil: $error';
  }

  @override
  String get noApiKeysFound => 'Ingen API-nøkler funnet. Opprett en for å komme i gang.';

  @override
  String get advancedSettings => 'Avanserte innstillinger';

  @override
  String get triggersWhenNewConversationCreated => 'Utløses når en ny samtale opprettes.';

  @override
  String get triggersWhenNewTranscriptReceived => 'Utløses når et nytt transkript mottas.';

  @override
  String get realtimeAudioBytes => 'Sanntids lydbytes';

  @override
  String get triggersWhenAudioBytesReceived => 'Utløses når lydbytes mottas.';

  @override
  String get everyXSeconds => 'Hvert x sekund';

  @override
  String get triggersWhenDaySummaryGenerated => 'Utløses når dagsammendraget genereres.';

  @override
  String get tryLatestExperimentalFeatures => 'Prøv de nyeste eksperimentelle funksjonene fra Omi-teamet.';

  @override
  String get transcriptionServiceDiagnosticStatus => 'Diagnostisk status for transkripsjonst jeneste';

  @override
  String get enableDetailedDiagnosticMessages =>
      'Aktiver detaljerte diagnostiske meldinger fra transkripsjonst jenesten';

  @override
  String get autoCreateAndTagNewSpeakers => 'Opprett og merk nye talere automatisk';

  @override
  String get automaticallyCreateNewPerson => 'Opprett automatisk en ny person når et navn oppdages i transkriptet.';

  @override
  String get pilotFeatures => 'Pilotfunksjoner';

  @override
  String get pilotFeaturesDescription => 'Disse funksjonene er tester og ingen støtte er garantert.';

  @override
  String get suggestFollowUpQuestion => 'Foreslå oppfølgingsspørsmål';

  @override
  String get saveSettings => 'Lagre Innstillinger';

  @override
  String get syncingDeveloperSettings => 'Synkroniserer utviklerinnstillinger...';

  @override
  String get summary => 'Sammendrag';

  @override
  String get auto => 'Automatisk';

  @override
  String get noSummaryForApp =>
      'Ingen sammendrag tilgjengelig for denne appen. Prøv en annen app for bedre resultater.';

  @override
  String get tryAnotherApp => 'Prøv en annen app';

  @override
  String generatedBy(String appName) {
    return 'Generert av $appName';
  }

  @override
  String get overview => 'Oversikt';

  @override
  String get otherAppResults => 'Resultater fra andre apper';

  @override
  String get unknownApp => 'Ukjent app';

  @override
  String get noSummaryAvailable => 'Ingen sammendrag tilgjengelig';

  @override
  String get conversationNoSummaryYet => 'Denne samtalen har ikke et sammendrag ennå.';

  @override
  String get chooseSummarizationApp => 'Velg sammendragsapp';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName satt som standard sammendragsapp';
  }

  @override
  String get letOmiChooseAutomatically => 'La Omi velge beste app automatisk';

  @override
  String get deleteConversationConfirmation =>
      'Er du sikker på at du vil slette denne samtalen? Denne handlingen kan ikke angres.';

  @override
  String get conversationDeleted => 'Samtale slettet';

  @override
  String get generatingLink => 'Genererer lenke...';

  @override
  String get editConversation => 'Rediger samtale';

  @override
  String get conversationLinkCopiedToClipboard => 'Samtalelenke kopiert til utklippstavle';

  @override
  String get conversationTranscriptCopiedToClipboard => 'Samtaletranskipsjon kopiert til utklippstavle';

  @override
  String get editConversationDialogTitle => 'Rediger samtale';

  @override
  String get changeTheConversationTitle => 'Endre samtaleens tittel';

  @override
  String get conversationTitle => 'Samtaletittel';

  @override
  String get enterConversationTitle => 'Skriv inn samtaletittel...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'Samtaletittel oppdatert';

  @override
  String get failedToUpdateConversationTitle => 'Kunne ikke oppdatere samtaletittel';

  @override
  String get errorUpdatingConversationTitle => 'Feil ved oppdatering av samtaletittel';

  @override
  String get settingUp => 'Setter opp...';

  @override
  String get startYourFirstRecording => 'Start ditt første opptak';

  @override
  String get preparingSystemAudioCapture => 'Forbereder systemlydopptak';

  @override
  String get clickTheButtonToCaptureAudio =>
      'Klikk på knappen for å ta opp lyd for direkte transkripsjoner, AI-innsikt og automatisk lagring.';

  @override
  String get reconnecting => 'Kobler til på nytt...';

  @override
  String get recordingPaused => 'Opptak satt på pause';

  @override
  String get recordingActive => 'Opptak aktivt';

  @override
  String get startRecording => 'Start opptak';

  @override
  String resumingInCountdown(String countdown) {
    return 'Gjenopptar om ${countdown}s...';
  }

  @override
  String get tapPlayToResume => 'Trykk på spill av for å fortsette';

  @override
  String get listeningForAudio => 'Lytter etter lyd...';

  @override
  String get preparingAudioCapture => 'Forbereder lydopptak';

  @override
  String get clickToBeginRecording => 'Klikk for å starte opptak';

  @override
  String get translated => 'oversatt';

  @override
  String get liveTranscript => 'Direktetranskribering';

  @override
  String segmentsSingular(String count) {
    return '$count segment';
  }

  @override
  String segmentsPlural(String count) {
    return '$count segmenter';
  }

  @override
  String get startRecordingToSeeTranscript => 'Start opptak for å se direktetranskribering';

  @override
  String get paused => 'På pause';

  @override
  String get initializing => 'Initialiserer...';

  @override
  String get recording => 'Tar opp';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'Mikrofon endret. Gjenopptar om ${countdown}s';
  }

  @override
  String get clickPlayToResumeOrStop => 'Klikk på spill av for å fortsette eller stopp for å fullføre';

  @override
  String get settingUpSystemAudioCapture => 'Setter opp systemlydopptak';

  @override
  String get capturingAudioAndGeneratingTranscript => 'Tar opp lyd og genererer transkripsjon';

  @override
  String get clickToBeginRecordingSystemAudio => 'Klikk for å starte systemlydopptak';

  @override
  String get you => 'Deg';

  @override
  String speakerWithId(String speakerId) {
    return 'Taler $speakerId';
  }

  @override
  String get translatedByOmi => 'oversatt av omi';

  @override
  String get backToConversations => 'Tilbake til samtaler';

  @override
  String get systemAudio => 'System';

  @override
  String get mic => 'Mikrofon';

  @override
  String audioInputSetTo(String deviceName) {
    return 'Lydinngang satt til $deviceName';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'Feil ved bytte av lydenhet: $error';
  }

  @override
  String get selectAudioInput => 'Velg lydinngang';

  @override
  String get loadingDevices => 'Laster inn enheter...';

  @override
  String get settingsHeader => 'INNSTILLINGER';

  @override
  String get plansAndBilling => 'Planer og Fakturering';

  @override
  String get calendarIntegration => 'Kalenderintegrasjon';

  @override
  String get dailySummary => 'Daglig Sammendrag';

  @override
  String get developer => 'Utvikler';

  @override
  String get about => 'Om';

  @override
  String get selectTime => 'Velg Tid';

  @override
  String get accountGroup => 'Konto';

  @override
  String get signOutQuestion => 'Logg Ut?';

  @override
  String get signOutConfirmation => 'Er du sikker på at du vil logge ut?';

  @override
  String get customVocabularyHeader => 'TILPASSET VOKABULAR';

  @override
  String get addWordsDescription => 'Legg til ord som Omi skal gjenkjenne under transkripsjon.';

  @override
  String get enterWordsHint => 'Skriv inn ord (kommaseparert)';

  @override
  String get dailySummaryHeader => 'DAGLIG SAMMENDRAG';

  @override
  String get dailySummaryTitle => 'Daglig Sammendrag';

  @override
  String get dailySummaryDescription => 'Få et personlig sammendrag av samtalene dine';

  @override
  String get deliveryTime => 'Leveringstid';

  @override
  String get deliveryTimeDescription => 'Når du skal motta det daglige sammendraget';

  @override
  String get subscription => 'Abonnement';

  @override
  String get viewPlansAndUsage => 'Se Planer og Bruk';

  @override
  String get viewPlansDescription => 'Administrer abonnementet ditt og se bruksstatistikk';

  @override
  String get addOrChangePaymentMethod => 'Legg til eller endre betalingsmåten din';

  @override
  String get displayOptions => 'Visningsalternativer';

  @override
  String get showMeetingsInMenuBar => 'Vis møter i menylinjen';

  @override
  String get displayUpcomingMeetingsDescription => 'Vis kommende møter i menylinjen';

  @override
  String get showEventsWithoutParticipants => 'Vis hendelser uten deltakere';

  @override
  String get includePersonalEventsDescription => 'Inkluder personlige hendelser uten deltakere';

  @override
  String get upcomingMeetings => 'KOMMENDE MØTER';

  @override
  String get checkingNext7Days => 'Sjekker de neste 7 dagene';

  @override
  String get shortcuts => 'Snarveier';

  @override
  String get shortcutChangeInstruction => 'Klikk på en snarvei for å endre den. Trykk Escape for å avbryte.';

  @override
  String get configurePersonaDescription => 'Konfigurer din AI-persona';

  @override
  String get configureSTTProvider => 'Konfigurer STT-leverandør';

  @override
  String get setConversationEndDescription => 'Angi når samtaler avsluttes automatisk';

  @override
  String get importDataDescription => 'Importer data fra andre kilder';

  @override
  String get exportConversationsDescription => 'Eksporter samtaler til JSON';

  @override
  String get exportingConversations => 'Eksporterer samtaler...';

  @override
  String get clearNodesDescription => 'Tøm alle noder og tilkoblinger';

  @override
  String get deleteKnowledgeGraphQuestion => 'Slette kunnskapsgraf?';

  @override
  String get deleteKnowledgeGraphWarning =>
      'Dette sletter alle avledede kunnskapsgrafdata. Dine opprinnelige minner forblir trygge.';

  @override
  String get connectOmiWithAI => 'Koble Omi til AI-assistenter';

  @override
  String get noAPIKeys => 'Ingen API-nøkler. Opprett en for å komme i gang.';

  @override
  String get autoCreateWhenDetected => 'Opprett automatisk når navn oppdages';

  @override
  String get trackPersonalGoals => 'Spor personlige mål på startsiden';

  @override
  String get dailyReflectionDescription => '21:00 påminnelse for å reflektere over dagen';

  @override
  String get endpointURL => 'Endepunkt-URL';

  @override
  String get links => 'Lenker';

  @override
  String get discordMemberCount => 'Over 8000 medlemmer på Discord';

  @override
  String get userInformation => 'Brukerinformasjon';

  @override
  String get capabilities => 'Funksjoner';

  @override
  String get previewScreenshots => 'Forhåndsvisning av skjermbilder';

  @override
  String get holdOnPreparingForm => 'Vent litt, vi forbereder skjemaet for deg';

  @override
  String get bySubmittingYouAgreeToOmi => 'Ved å sende inn godtar du Omi ';

  @override
  String get termsAndPrivacyPolicy => 'Vilkår og Personvernpolicy';

  @override
  String get helpsDiagnoseIssuesAutoDeletes =>
      'Hjelper med å diagnostisere problemer. Slettes automatisk etter 3 dager.';

  @override
  String get manageYourApp => 'Administrer appen din';

  @override
  String get updatingYourApp => 'Oppdaterer appen din';

  @override
  String get fetchingYourAppDetails => 'Henter app-detaljer';

  @override
  String get updateAppQuestion => 'Oppdater app?';

  @override
  String get updateAppConfirmation =>
      'Er du sikker på at du vil oppdatere appen din? Endringene vil vises etter gjennomgang av teamet vårt.';

  @override
  String get updateApp => 'Oppdater app';

  @override
  String get createAndSubmitNewApp => 'Opprett og send inn en ny app';

  @override
  String appsCount(String count) {
    return 'Apper ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'Private apper ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'Offentlige apper ($count)';
  }

  @override
  String get newVersionAvailable => 'Ny versjon tilgjengelig  🎉';

  @override
  String get no => 'Nei';

  @override
  String get subscriptionCancelledSuccessfully =>
      'Abonnement kansellert. Det forblir aktivt til slutten av gjeldende faktureringsperiode.';

  @override
  String get failedToCancelSubscription => 'Kunne ikke kansellere abonnement. Prøv igjen.';

  @override
  String get invalidPaymentUrl => 'Ugyldig betalings-URL';

  @override
  String get permissionsAndTriggers => 'Tillatelser og utløsere';

  @override
  String get chatFeatures => 'Chat-funksjoner';

  @override
  String get uninstall => 'Avinstaller';

  @override
  String get installs => 'INSTALLASJONER';

  @override
  String get priceLabel => 'PRIS';

  @override
  String get updatedLabel => 'OPPDATERT';

  @override
  String get createdLabel => 'OPPRETTET';

  @override
  String get featuredLabel => 'FREMHEVET';

  @override
  String get cancelSubscriptionQuestion => 'Kanseller abonnement?';

  @override
  String get cancelSubscriptionConfirmation =>
      'Er du sikker på at du vil kansellere abonnementet? Du vil fortsatt ha tilgang til slutten av gjeldende faktureringsperiode.';

  @override
  String get cancelSubscriptionButton => 'Kanseller abonnement';

  @override
  String get cancelling => 'Kansellerer...';

  @override
  String get betaTesterMessage =>
      'Du er betatester for denne appen. Den er ikke offentlig ennå. Den blir offentlig etter godkjenning.';

  @override
  String get appUnderReviewMessage =>
      'Appen din er under vurdering og bare synlig for deg. Den blir offentlig etter godkjenning.';

  @override
  String get appRejectedMessage => 'Appen din er avvist. Oppdater detaljene og send inn på nytt for vurdering.';

  @override
  String get invalidIntegrationUrl => 'Ugyldig integrasjons-URL';

  @override
  String get tapToComplete => 'Trykk for å fullføre';

  @override
  String get invalidSetupInstructionsUrl => 'Ugyldig URL for oppsettsinstruksjoner';

  @override
  String get pushToTalk => 'Trykk for å snakke';

  @override
  String get summaryPrompt => 'Sammendragsprompt';

  @override
  String get pleaseSelectARating => 'Velg en vurdering';

  @override
  String get reviewAddedSuccessfully => 'Anmeldelse lagt til 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'Anmeldelse oppdatert 🚀';

  @override
  String get failedToSubmitReview => 'Kunne ikke sende anmeldelse. Prøv igjen.';

  @override
  String get addYourReview => 'Legg til din anmeldelse';

  @override
  String get editYourReview => 'Rediger din anmeldelse';

  @override
  String get writeAReviewOptional => 'Skriv en anmeldelse (valgfritt)';

  @override
  String get submitReview => 'Send anmeldelse';

  @override
  String get updateReview => 'Oppdater anmeldelse';

  @override
  String get yourReview => 'Din anmeldelse';

  @override
  String get anonymousUser => 'Anonym bruker';

  @override
  String get issueActivatingApp => 'Det oppstod et problem ved aktivering av denne appen. Prøv igjen.';

  @override
  String get dataAccessNoticeDescription =>
      'This app will access your data. Omi AI is not responsible for how your data is used, modified, or deleted by this app';

  @override
  String get copyUrl => 'Kopier URL';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

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
    return '$serviceName-integrasjon kommer snart';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'Allerede eksportert til $platform';
  }

  @override
  String get anotherPlatform => 'en annen plattform';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'Vennligst autentiser med $serviceName i Innstillinger > Oppgaveintegrasjoner';
  }

  @override
  String addingToService(String serviceName) {
    return 'Legger til i $serviceName...';
  }

  @override
  String addedToService(String serviceName) {
    return 'Lagt til i $serviceName';
  }

  @override
  String failedToAddToService(String serviceName) {
    return 'Kunne ikke legge til i $serviceName';
  }

  @override
  String get permissionDeniedForAppleReminders => 'Tillatelse avslått for Apple Påminnelser';

  @override
  String failedToCreateApiKey(String error) {
    return 'Kunne ikke opprette leverandør-API-nøkkel: $error';
  }

  @override
  String get createAKey => 'Opprett en nøkkel';

  @override
  String get apiKeyRevokedSuccessfully => 'API-nøkkel tilbakekalt';

  @override
  String failedToRevokeApiKey(String error) {
    return 'Kunne ikke tilbakekalle API-nøkkel: $error';
  }

  @override
  String get omiApiKeys => 'Omi API-nøkler';

  @override
  String get apiKeysDescription =>
      'API-nøkler brukes til autentisering når appen din kommuniserer med OMI-serveren. De lar applikasjonen din opprette minner og få sikker tilgang til andre OMI-tjenester.';

  @override
  String get aboutOmiApiKeys => 'Om Omi API-nøkler';

  @override
  String get yourNewKey => 'Din nye nøkkel:';

  @override
  String get copyToClipboard => 'Kopier til utklippstavle';

  @override
  String get pleaseCopyKeyNow => 'Vennligst kopier den nå og skriv den ned på et trygt sted. ';

  @override
  String get willNotSeeAgain => 'Du vil ikke kunne se den igjen.';

  @override
  String get revokeKey => 'Tilbakekall nøkkel';

  @override
  String get revokeApiKeyQuestion => 'Tilbakekalle API-nøkkel?';

  @override
  String get revokeApiKeyWarning =>
      'Denne handlingen kan ikke angres. Alle applikasjoner som bruker denne nøkkelen vil ikke lenger kunne få tilgang til API-et.';

  @override
  String get revoke => 'Tilbakekall';

  @override
  String get whatWouldYouLikeToCreate => 'Hva vil du lage?';

  @override
  String get createAnApp => 'Lag en app';

  @override
  String get createAndShareYourApp => 'Lag og del appen din';

  @override
  String get createMyClone => 'Lag min klon';

  @override
  String get createYourDigitalClone => 'Lag din digitale klon';

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
    return 'Gjøre $item offentlig?';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return 'Gjøre $item privat?';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'Hvis du gjør $item offentlig, kan den brukes av alle';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'Hvis du gjør $item privat nå, slutter den å fungere for alle og vil bare være synlig for deg';
  }

  @override
  String get manageApp => 'Administrer app';

  @override
  String get updatePersonaDetails => 'Oppdater persona-detaljer';

  @override
  String deleteItemTitle(String item) {
    return 'Slett $item';
  }

  @override
  String deleteItemQuestion(String item) {
    return 'Slette $item?';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'Er du sikker på at du vil slette denne $item? Denne handlingen kan ikke angres.';
  }

  @override
  String get revokeKeyQuestion => 'Tilbakekall nøkkel?';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'Er du sikker på at du vil tilbakekalle nøkkelen \"$keyName\"? Denne handlingen kan ikke angres.';
  }

  @override
  String get createNewKey => 'Opprett ny nøkkel';

  @override
  String get keyNameHint => 'f.eks. Claude Desktop';

  @override
  String get pleaseEnterAName => 'Vennligst skriv inn et navn.';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'Kunne ikke opprette nøkkel: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'Kunne ikke opprette nøkkel. Vennligst prøv igjen.';

  @override
  String get keyCreated => 'Nøkkel opprettet';

  @override
  String get keyCreatedMessage =>
      'Din nye nøkkel er opprettet. Vennligst kopier den nå. Du vil ikke kunne se den igjen.';

  @override
  String get keyWord => 'Nøkkel';

  @override
  String get externalAppAccess => 'Ekstern app-tilgang';

  @override
  String get externalAppAccessDescription =>
      'Følgende installerte apper har eksterne integrasjoner og kan få tilgang til dataene dine, som samtaler og minner.';

  @override
  String get noExternalAppsHaveAccess => 'Ingen eksterne apper har tilgang til dataene dine.';

  @override
  String get maximumSecurityE2ee => 'Maksimal sikkerhet (E2EE)';

  @override
  String get e2eeDescription =>
      'Ende-til-ende-kryptering er gullstandarden for personvern. Når det er aktivert, krypteres dataene dine på enheten din før de sendes til serverne våre. Dette betyr at ingen, ikke engang Omi, kan få tilgang til innholdet ditt.';

  @override
  String get importantTradeoffs => 'Viktige avveininger:';

  @override
  String get e2eeTradeoff1 => '• Noen funksjoner som eksterne app-integrasjoner kan være deaktivert.';

  @override
  String get e2eeTradeoff2 => '• Hvis du mister passordet ditt, kan dataene dine ikke gjenopprettes.';

  @override
  String get featureComingSoon => 'Denne funksjonen kommer snart!';

  @override
  String get migrationInProgressMessage => 'Migrering pågår. Du kan ikke endre beskyttelsesnivået før det er fullført.';

  @override
  String get migrationFailed => 'Migrering mislyktes';

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
      'Dataene dine er kryptert med en nøkkel som er unik for deg på våre servere, hostet på Google Cloud. Dette betyr at råinnholdet ditt er utilgjengelig for alle, inkludert Omi-ansatte eller Google, direkte fra databasen.';

  @override
  String get endToEndEncryption => 'Ende-til-ende-kryptering';

  @override
  String get e2eeCardDescription =>
      'Aktiver for maksimal sikkerhet der bare du har tilgang til dataene dine. Trykk for å lære mer.';

  @override
  String get dataAlwaysEncrypted => 'Uavhengig av nivå er dataene dine alltid kryptert i hvile og under overføring.';

  @override
  String get readOnlyScope => 'Kun lesing';

  @override
  String get fullAccessScope => 'Full tilgang';

  @override
  String get readScope => 'Les';

  @override
  String get writeScope => 'Skriv';

  @override
  String get apiKeyCreated => 'API-nøkkel opprettet!';

  @override
  String get saveKeyWarning => 'Lagre denne nøkkelen nå! Du vil ikke kunne se den igjen.';

  @override
  String get yourApiKey => 'DIN API-NØKKEL';

  @override
  String get tapToCopy => 'Trykk for å kopiere';

  @override
  String get copyKey => 'Kopier nøkkel';

  @override
  String get createApiKey => 'Opprett API-nøkkel';

  @override
  String get accessDataProgrammatically => 'Få tilgang til dataene dine programmatisk';

  @override
  String get keyNameLabel => 'NØKKELNAVN';

  @override
  String get keyNamePlaceholder => 'f.eks., Min app-integrasjon';

  @override
  String get permissionsLabel => 'TILLATELSER';

  @override
  String get permissionsInfoNote => 'R = Les, W = Skriv. Standard kun lesing hvis ingenting er valgt.';
}
