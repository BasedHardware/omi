// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Dutch Flemish (`nl`).
class AppLocalizationsNl extends AppLocalizations {
  AppLocalizationsNl([String locale = 'nl']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'Gesprek';

  @override
  String get transcriptTab => 'Transcript';

  @override
  String get actionItemsTab => 'Actiepunten';

  @override
  String get deleteConversationTitle => 'Gesprek verwijderen?';

  @override
  String get deleteConversationMessage =>
      'Weet je zeker dat je dit gesprek wilt verwijderen? Deze actie kan niet ongedaan worden gemaakt.';

  @override
  String get confirm => 'Bevestigen';

  @override
  String get cancel => 'Annuleren';

  @override
  String get ok => 'OK';

  @override
  String get delete => 'Verwijderen';

  @override
  String get add => 'Toevoegen';

  @override
  String get update => 'Bijwerken';

  @override
  String get save => 'Opslaan';

  @override
  String get edit => 'Bewerken';

  @override
  String get close => 'Sluiten';

  @override
  String get clear => 'Wissen';

  @override
  String get copyTranscript => 'Transcript kopiëren';

  @override
  String get copySummary => 'Samenvatting kopiëren';

  @override
  String get testPrompt => 'Prompt testen';

  @override
  String get reprocessConversation => 'Gesprek opnieuw verwerken';

  @override
  String get deleteConversation => 'Gesprek verwijderen';

  @override
  String get contentCopied => 'Inhoud gekopieerd naar klembord';

  @override
  String get failedToUpdateStarred => 'Kan favorietenstatus niet bijwerken.';

  @override
  String get conversationUrlNotShared => 'Gesprek-URL kon niet worden gedeeld.';

  @override
  String get errorProcessingConversation => 'Fout bij het verwerken van gesprek. Probeer het later opnieuw.';

  @override
  String get noInternetConnection => 'Controleer je internetverbinding en probeer het opnieuw.';

  @override
  String get unableToDeleteConversation => 'Kan gesprek niet verwijderen';

  @override
  String get somethingWentWrong => 'Er is iets misgegaan! Probeer het later opnieuw.';

  @override
  String get copyErrorMessage => 'Foutmelding kopiëren';

  @override
  String get errorCopied => 'Foutmelding gekopieerd naar klembord';

  @override
  String get remaining => 'Resterend';

  @override
  String get loading => 'Laden...';

  @override
  String get loadingDuration => 'Duur laden...';

  @override
  String secondsCount(int count) {
    return '$count seconden';
  }

  @override
  String get people => 'Mensen';

  @override
  String get addNewPerson => 'Nieuwe persoon toevoegen';

  @override
  String get editPerson => 'Persoon bewerken';

  @override
  String get createPersonHint => 'Maak een nieuwe persoon aan en train Omi om hun stem te herkennen!';

  @override
  String get speechProfile => 'Spraakprofiel';

  @override
  String sampleNumber(int number) {
    return 'Monster $number';
  }

  @override
  String get settings => 'Instellingen';

  @override
  String get language => 'Taal';

  @override
  String get selectLanguage => 'Selecteer taal';

  @override
  String get deleting => 'Verwijderen...';

  @override
  String get pleaseCompleteAuthentication => 'Voltooi de authenticatie in je browser. Keer daarna terug naar de app.';

  @override
  String get failedToStartAuthentication => 'Kan authenticatie niet starten';

  @override
  String get importStarted => 'Import gestart! Je krijgt een melding wanneer het klaar is.';

  @override
  String get failedToStartImport => 'Kan import niet starten. Probeer het opnieuw.';

  @override
  String get couldNotAccessFile => 'Kan het geselecteerde bestand niet openen';

  @override
  String get askOmi => 'Vraag Omi';

  @override
  String get done => 'Klaar';

  @override
  String get disconnected => 'Niet verbonden';

  @override
  String get searching => 'Zoeken';

  @override
  String get connectDevice => 'Apparaat verbinden';

  @override
  String get monthlyLimitReached => 'Je hebt je maandelijkse limiet bereikt.';

  @override
  String get checkUsage => 'Verbruik controleren';

  @override
  String get syncingRecordings => 'Opnames synchroniseren';

  @override
  String get recordingsToSync => 'Opnames om te synchroniseren';

  @override
  String get allCaughtUp => 'Alles is bijgewerkt';

  @override
  String get sync => 'Synchroniseren';

  @override
  String get pendantUpToDate => 'Hanger is up-to-date';

  @override
  String get allRecordingsSynced => 'Alle opnames zijn gesynchroniseerd';

  @override
  String get syncingInProgress => 'Synchronisatie bezig';

  @override
  String get readyToSync => 'Klaar om te synchroniseren';

  @override
  String get tapSyncToStart => 'Tik op Synchroniseren om te starten';

  @override
  String get pendantNotConnected => 'Hanger niet verbonden. Verbind om te synchroniseren.';

  @override
  String get everythingSynced => 'Alles is al gesynchroniseerd.';

  @override
  String get recordingsNotSynced => 'Je hebt opnames die nog niet zijn gesynchroniseerd.';

  @override
  String get syncingBackground => 'We blijven je opnames op de achtergrond synchroniseren.';

  @override
  String get noConversationsYet => 'Nog geen gesprekken.';

  @override
  String get noStarredConversations => 'Nog geen favoriete gesprekken.';

  @override
  String get starConversationHint =>
      'Om een gesprek als favoriet te markeren, open het en tik op het stericoon in de header.';

  @override
  String get searchConversations => 'Gesprekken zoeken';

  @override
  String selectedCount(int count, Object s) {
    return '$count geselecteerd';
  }

  @override
  String get merge => 'Samenvoegen';

  @override
  String get mergeConversations => 'Gesprekken samenvoegen';

  @override
  String mergeConversationsMessage(int count) {
    return 'Dit combineert $count gesprekken tot één. Alle inhoud wordt samengevoegd en opnieuw gegenereerd.';
  }

  @override
  String get mergingInBackground => 'Samenvoegen op de achtergrond. Dit kan even duren.';

  @override
  String get failedToStartMerge => 'Kan samenvoegen niet starten';

  @override
  String get askAnything => 'Vraag wat je wilt';

  @override
  String get noMessagesYet => 'Nog geen berichten!\nWaarom begin je geen gesprek?';

  @override
  String get deletingMessages => 'Je berichten verwijderen uit Omi\'s geheugen...';

  @override
  String get messageCopied => 'Bericht gekopieerd naar klembord.';

  @override
  String get cannotReportOwnMessage => 'Je kunt je eigen berichten niet rapporteren.';

  @override
  String get reportMessage => 'Bericht rapporteren';

  @override
  String get reportMessageConfirm => 'Weet je zeker dat je dit bericht wilt rapporteren?';

  @override
  String get messageReported => 'Bericht succesvol gerapporteerd.';

  @override
  String get thankYouFeedback => 'Bedankt voor je feedback!';

  @override
  String get clearChat => 'Chat wissen?';

  @override
  String get clearChatConfirm =>
      'Weet je zeker dat je de chat wilt wissen? Deze actie kan niet ongedaan worden gemaakt.';

  @override
  String get maxFilesLimit => 'Je kunt maximaal 4 bestanden tegelijk uploaden';

  @override
  String get chatWithOmi => 'Chat met Omi';

  @override
  String get apps => 'Apps';

  @override
  String get noAppsFound => 'Geen apps gevonden';

  @override
  String get tryAdjustingSearch => 'Probeer je zoekopdracht of filters aan te passen';

  @override
  String get createYourOwnApp => 'Maak je eigen app';

  @override
  String get buildAndShareApp => 'Bouw en deel je aangepaste app';

  @override
  String get searchApps => 'Zoek in 1500+ apps';

  @override
  String get myApps => 'Mijn apps';

  @override
  String get installedApps => 'Geïnstalleerde apps';

  @override
  String get unableToFetchApps =>
      'Kan apps niet ophalen :(\n\nControleer je internetverbinding en probeer het opnieuw.';

  @override
  String get aboutOmi => 'Over Omi';

  @override
  String get privacyPolicy => 'Privacybeleid';

  @override
  String get visitWebsite => 'Website bezoeken';

  @override
  String get helpOrInquiries => 'Hulp of vragen?';

  @override
  String get joinCommunity => 'Word lid van de community!';

  @override
  String get membersAndCounting => '8000+ leden en groeiende.';

  @override
  String get deleteAccountTitle => 'Account verwijderen';

  @override
  String get deleteAccountConfirm => 'Weet je zeker dat je je account wilt verwijderen?';

  @override
  String get cannotBeUndone => 'Dit kan niet ongedaan worden gemaakt.';

  @override
  String get allDataErased => 'Al je herinneringen en gesprekken worden permanent verwijderd.';

  @override
  String get appsDisconnected => 'Je apps en integraties worden direct losgekoppeld.';

  @override
  String get exportBeforeDelete =>
      'Je kunt je gegevens exporteren voordat je je account verwijdert, maar eenmaal verwijderd kan het niet worden hersteld.';

  @override
  String get deleteAccountCheckbox =>
      'Ik begrijp dat het verwijderen van mijn account permanent is en alle gegevens, inclusief herinneringen en gesprekken, verloren gaan en niet kunnen worden hersteld.';

  @override
  String get areYouSure => 'Weet je het zeker?';

  @override
  String get deleteAccountFinal =>
      'Deze actie is onomkeerbaar en verwijdert permanent je account en alle bijbehorende gegevens. Weet je zeker dat je wilt doorgaan?';

  @override
  String get deleteNow => 'Nu verwijderen';

  @override
  String get goBack => 'Terug';

  @override
  String get checkBoxToConfirm =>
      'Vink het vakje aan om te bevestigen dat je begrijpt dat het verwijderen van je account permanent en onomkeerbaar is.';

  @override
  String get profile => 'Profiel';

  @override
  String get name => 'Naam';

  @override
  String get email => 'E-mail';

  @override
  String get customVocabulary => 'Aangepaste woordenlijst';

  @override
  String get identifyingOthers => 'Anderen identificeren';

  @override
  String get paymentMethods => 'Betaalmethoden';

  @override
  String get conversationDisplay => 'Gespreksweergave';

  @override
  String get dataPrivacy => 'Gegevens en privacy';

  @override
  String get userId => 'Gebruikers-ID';

  @override
  String get notSet => 'Niet ingesteld';

  @override
  String get userIdCopied => 'Gebruikers-ID gekopieerd naar klembord';

  @override
  String get systemDefault => 'Systeemstandaard';

  @override
  String get planAndUsage => 'Abonnement en gebruik';

  @override
  String get offlineSync => 'Offline synchronisatie';

  @override
  String get deviceSettings => 'Apparaatinstellingen';

  @override
  String get chatTools => 'Chat-tools';

  @override
  String get feedbackBug => 'Feedback / Bug';

  @override
  String get helpCenter => 'Helpcentrum';

  @override
  String get developerSettings => 'Ontwikkelaarsinstellingen';

  @override
  String get getOmiForMac => 'Omi voor Mac downloaden';

  @override
  String get referralProgram => 'Doorverwijsprogramma';

  @override
  String get signOut => 'Uitloggen';

  @override
  String get appAndDeviceCopied => 'App- en apparaatgegevens gekopieerd';

  @override
  String get wrapped2025 => 'Terugblik 2025';

  @override
  String get yourPrivacyYourControl => 'Jouw privacy, jouw controle';

  @override
  String get privacyIntro =>
      'Bij Omi zijn we toegewijd aan het beschermen van je privacy. Deze pagina stelt je in staat om te bepalen hoe je gegevens worden opgeslagen en gebruikt.';

  @override
  String get learnMore => 'Meer informatie...';

  @override
  String get dataProtectionLevel => 'Gegevensbeschermingsniveau';

  @override
  String get dataProtectionDesc =>
      'Je gegevens zijn standaard beveiligd met sterke encryptie. Bekijk hieronder je instellingen en toekomstige privacy-opties.';

  @override
  String get appAccess => 'App-toegang';

  @override
  String get appAccessDesc =>
      'De volgende apps hebben toegang tot je gegevens. Tik op een app om de machtigingen te beheren.';

  @override
  String get noAppsExternalAccess => 'Geen geïnstalleerde apps hebben externe toegang tot je gegevens.';

  @override
  String get deviceName => 'Apparaatnaam';

  @override
  String get deviceId => 'Apparaat-ID';

  @override
  String get firmware => 'Firmware';

  @override
  String get sdCardSync => 'SD-kaart synchronisatie';

  @override
  String get hardwareRevision => 'Hardwarerevisie';

  @override
  String get modelNumber => 'Modelnummer';

  @override
  String get manufacturer => 'Fabrikant';

  @override
  String get doubleTap => 'Dubbel tikken';

  @override
  String get ledBrightness => 'LED-helderheid';

  @override
  String get micGain => 'Microfoonversterking';

  @override
  String get disconnect => 'Loskoppelen';

  @override
  String get forgetDevice => 'Apparaat vergeten';

  @override
  String get chargingIssues => 'Oplaadproblemen';

  @override
  String get disconnectDevice => 'Apparaat loskoppelen';

  @override
  String get unpairDevice => 'Apparaat ontkoppelen';

  @override
  String get unpairAndForget => 'Apparaat ontkoppelen en vergeten';

  @override
  String get deviceDisconnectedMessage => 'Je Omi is losgekoppeld 😔';

  @override
  String get deviceUnpairedMessage =>
      'Apparaat ontkoppeld. Ga naar Instellingen > Bluetooth en vergeet het apparaat om het ontkoppelen te voltooien.';

  @override
  String get unpairDialogTitle => 'Apparaat ontkoppelen';

  @override
  String get unpairDialogMessage =>
      'Dit ontkoppelt het apparaat zodat het met een andere telefoon kan worden verbonden. Je moet naar Instellingen > Bluetooth gaan en het apparaat vergeten om het proces te voltooien.';

  @override
  String get deviceNotConnected => 'Apparaat niet verbonden';

  @override
  String get connectDeviceMessage =>
      'Verbind je Omi-apparaat om toegang te krijgen tot\napparaatinstellingen en aanpassingen';

  @override
  String get deviceInfoSection => 'Apparaatinformatie';

  @override
  String get customizationSection => 'Aanpassingen';

  @override
  String get hardwareSection => 'Hardware';

  @override
  String get v2Undetected => 'V2 niet gedetecteerd';

  @override
  String get v2UndetectedMessage =>
      'We zien dat je een V1-apparaat hebt of je apparaat is niet verbonden. SD-kaartfunctionaliteit is alleen beschikbaar voor V2-apparaten.';

  @override
  String get endConversation => 'Gesprek beëindigen';

  @override
  String get pauseResume => 'Pauzeren/Hervatten';

  @override
  String get starConversation => 'Gesprek als favoriet markeren';

  @override
  String get doubleTapAction => 'Dubbel tikken actie';

  @override
  String get endAndProcess => 'Gesprek beëindigen en verwerken';

  @override
  String get pauseResumeRecording => 'Opname pauzeren/hervatten';

  @override
  String get starOngoing => 'Lopend gesprek als favoriet markeren';

  @override
  String get off => 'Uit';

  @override
  String get max => 'Max';

  @override
  String get mute => 'Dempen';

  @override
  String get quiet => 'Stil';

  @override
  String get normal => 'Normaal';

  @override
  String get high => 'Hoog';

  @override
  String get micGainDescMuted => 'Microfoon is gedempt';

  @override
  String get micGainDescLow => 'Zeer stil - voor luidruchtige omgevingen';

  @override
  String get micGainDescModerate => 'Stil - voor matig geluid';

  @override
  String get micGainDescNeutral => 'Neutraal - gebalanceerde opname';

  @override
  String get micGainDescSlightlyBoosted => 'Licht versterkt - normaal gebruik';

  @override
  String get micGainDescBoosted => 'Versterkt - voor stille omgevingen';

  @override
  String get micGainDescHigh => 'Hoog - voor verre of zachte stemmen';

  @override
  String get micGainDescVeryHigh => 'Zeer hoog - voor zeer stille bronnen';

  @override
  String get micGainDescMax => 'Maximum - gebruik met voorzichtigheid';

  @override
  String get developerSettingsTitle => 'Ontwikkelaarsinstellingen';

  @override
  String get saving => 'Opslaan...';

  @override
  String get personaConfig => 'Configureer je AI-persona';

  @override
  String get beta => 'BETA';

  @override
  String get transcription => 'Transcriptie';

  @override
  String get transcriptionConfig => 'STT-provider configureren';

  @override
  String get conversationTimeout => 'Gesprekstime-out';

  @override
  String get conversationTimeoutConfig => 'Instellen wanneer gesprekken automatisch eindigen';

  @override
  String get importData => 'Gegevens importeren';

  @override
  String get importDataConfig => 'Gegevens importeren uit andere bronnen';

  @override
  String get debugDiagnostics => 'Debug en diagnostiek';

  @override
  String get endpointUrl => 'Endpoint-URL';

  @override
  String get noApiKeys => 'Nog geen API-sleutels';

  @override
  String get createKeyToStart => 'Maak een sleutel aan om te beginnen';

  @override
  String get createKey => 'Sleutel aanmaken';

  @override
  String get docs => 'Documentatie';

  @override
  String get yourOmiInsights => 'Je Omi-inzichten';

  @override
  String get today => 'Vandaag';

  @override
  String get thisMonth => 'Deze maand';

  @override
  String get thisYear => 'Dit jaar';

  @override
  String get allTime => 'Altijd';

  @override
  String get noActivityYet => 'Nog geen activiteit';

  @override
  String get startConversationToSeeInsights => 'Start een gesprek met Omi\nom je gebruiksinzichten hier te zien.';

  @override
  String get listening => 'Luisteren';

  @override
  String get listeningSubtitle => 'Totale tijd dat Omi actief heeft geluisterd.';

  @override
  String get understanding => 'Begrijpen';

  @override
  String get understandingSubtitle => 'Woorden begrepen uit je gesprekken.';

  @override
  String get providing => 'Leveren';

  @override
  String get providingSubtitle => 'Actiepunten en notities automatisch vastgelegd.';

  @override
  String get remembering => 'Onthouden';

  @override
  String get rememberingSubtitle => 'Feiten en details voor je onthouden.';

  @override
  String get unlimitedPlan => 'Onbeperkt abonnement';

  @override
  String get managePlan => 'Abonnement beheren';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'Je abonnement wordt geannuleerd op $date.';
  }

  @override
  String renewsOn(String date) {
    return 'Je abonnement wordt verlengd op $date.';
  }

  @override
  String get basicPlan => 'Gratis abonnement';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used van $limit min gebruikt';
  }

  @override
  String get upgrade => 'Upgraden';

  @override
  String get upgradeToUnlimited => 'Upgraden naar onbeperkt';

  @override
  String basicPlanDesc(int limit) {
    return 'Je abonnement bevat $limit gratis minuten per maand. Upgrade naar onbeperkt.';
  }

  @override
  String get shareStatsMessage => 'Ik deel mijn Omi-statistieken! (omi.me - je altijd-aan AI-assistent)';

  @override
  String get sharePeriodToday => 'Vandaag heeft Omi:';

  @override
  String get sharePeriodMonth => 'Deze maand heeft Omi:';

  @override
  String get sharePeriodYear => 'Dit jaar heeft Omi:';

  @override
  String get sharePeriodAllTime => 'Tot nu toe heeft Omi:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 $minutes minuten geluisterd';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 $words woorden begrepen';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ $count inzichten gegeven';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 $count herinneringen onthouden';
  }

  @override
  String get debugLogs => 'Debug-logboeken';

  @override
  String get debugLogsAutoDelete => 'Automatisch verwijderd na 3 dagen.';

  @override
  String get debugLogsDesc => 'Helpt bij het diagnosticeren van problemen';

  @override
  String get noLogFilesFound => 'Geen logbestanden gevonden.';

  @override
  String get omiDebugLog => 'Omi debug-log';

  @override
  String get logShared => 'Log gedeeld';

  @override
  String get selectLogFile => 'Logbestand selecteren';

  @override
  String get shareLogs => 'Logboeken delen';

  @override
  String get debugLogCleared => 'Debug-log gewist';

  @override
  String get exportStarted => 'Export gestart. Dit kan enkele seconden duren...';

  @override
  String get exportAllData => 'Alle gegevens exporteren';

  @override
  String get exportDataDesc => 'Gesprekken exporteren naar een JSON-bestand';

  @override
  String get exportedConversations => 'Geëxporteerde gesprekken van Omi';

  @override
  String get exportShared => 'Export gedeeld';

  @override
  String get deleteKnowledgeGraphTitle => 'Kennisgraaf verwijderen?';

  @override
  String get deleteKnowledgeGraphMessage =>
      'Dit verwijdert alle afgeleide kennisgraafgegevens (knooppunten en verbindingen). Je originele herinneringen blijven veilig. De graaf wordt na verloop van tijd of bij het volgende verzoek opnieuw opgebouwd.';

  @override
  String get knowledgeGraphDeleted => 'Kennisgraaf succesvol verwijderd';

  @override
  String deleteGraphFailed(String error) {
    return 'Verwijderen graaf mislukt: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'Kennisgraaf verwijderen';

  @override
  String get deleteKnowledgeGraphDesc => 'Alle knooppunten en verbindingen wissen';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'MCP-server';

  @override
  String get mcpServerDesc => 'AI-assistenten verbinden met je gegevens';

  @override
  String get serverUrl => 'Server-URL';

  @override
  String get urlCopied => 'URL gekopieerd';

  @override
  String get apiKeyAuth => 'API-sleutel authenticatie';

  @override
  String get header => 'Header';

  @override
  String get authorizationBearer => 'Authorization: Bearer <sleutel>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'Client-ID';

  @override
  String get clientSecret => 'Client-geheim';

  @override
  String get useMcpApiKey => 'Gebruik je MCP API-sleutel';

  @override
  String get webhooks => 'Webhooks';

  @override
  String get conversationEvents => 'Gespreksgebeurtenissen';

  @override
  String get newConversationCreated => 'Nieuw gesprek aangemaakt';

  @override
  String get realtimeTranscript => 'Realtime transcript';

  @override
  String get transcriptReceived => 'Transcript ontvangen';

  @override
  String get audioBytes => 'Audiobytes';

  @override
  String get audioDataReceived => 'Audiogegevens ontvangen';

  @override
  String get intervalSeconds => 'Interval (seconden)';

  @override
  String get daySummary => 'Dagsamenvatting';

  @override
  String get summaryGenerated => 'Samenvatting gegenereerd';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'Toevoegen aan claude_desktop_config.json';

  @override
  String get copyConfig => 'Configuratie kopiëren';

  @override
  String get configCopied => 'Configuratie gekopieerd naar klembord';

  @override
  String get listeningMins => 'Luisteren (min)';

  @override
  String get understandingWords => 'Begrijpen (woorden)';

  @override
  String get insights => 'Inzichten';

  @override
  String get memories => 'Herinneringen';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '$used van $limit min gebruikt deze maand';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '$used van $limit woorden gebruikt deze maand';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '$used van $limit inzichten verkregen deze maand';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return '$used van $limit herinneringen aangemaakt deze maand';
  }

  @override
  String get visibility => 'Zichtbaarheid';

  @override
  String get visibilitySubtitle => 'Bepaal welke gesprekken in je lijst verschijnen';

  @override
  String get showShortConversations => 'Korte gesprekken tonen';

  @override
  String get showShortConversationsDesc => 'Gesprekken korter dan de drempel weergeven';

  @override
  String get showDiscardedConversations => 'Verwijderde gesprekken tonen';

  @override
  String get showDiscardedConversationsDesc => 'Gesprekken gemarkeerd als verwijderd opnemen';

  @override
  String get shortConversationThreshold => 'Drempel voor korte gesprekken';

  @override
  String get shortConversationThresholdSubtitle =>
      'Gesprekken korter dan dit worden verborgen tenzij hierboven ingeschakeld';

  @override
  String get durationThreshold => 'Duurdrempel';

  @override
  String get durationThresholdDesc => 'Gesprekken korter dan dit verbergen';

  @override
  String minLabel(int count) {
    return '$count min';
  }

  @override
  String get customVocabularyTitle => 'Aangepaste woordenlijst';

  @override
  String get addWords => 'Woorden toevoegen';

  @override
  String get addWordsDesc => 'Namen, termen of ongewone woorden';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'Verbinden';

  @override
  String get comingSoon => 'Binnenkort beschikbaar';

  @override
  String get chatToolsFooter => 'Verbind je apps om gegevens en statistieken in de chat te bekijken.';

  @override
  String get completeAuthInBrowser => 'Voltooi de authenticatie in je browser. Keer daarna terug naar de app.';

  @override
  String failedToStartAuth(String appName) {
    return 'Kan $appName-authenticatie niet starten';
  }

  @override
  String disconnectAppTitle(String appName) {
    return '$appName loskoppelen?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'Weet je zeker dat je de verbinding met $appName wilt verbreken? Je kunt altijd opnieuw verbinden.';
  }

  @override
  String disconnectedFrom(String appName) {
    return 'Losgekoppeld van $appName';
  }

  @override
  String get failedToDisconnect => 'Loskoppelen mislukt';

  @override
  String connectTo(String appName) {
    return 'Verbinden met $appName';
  }

  @override
  String authAccessMessage(String appName) {
    return 'Je moet Omi autoriseren om toegang te krijgen tot je $appName-gegevens. Dit opent je browser voor authenticatie.';
  }

  @override
  String get continueAction => 'Doorgaan';

  @override
  String get languageTitle => 'Taal';

  @override
  String get primaryLanguage => 'Primaire taal';

  @override
  String get automaticTranslation => 'Automatische vertaling';

  @override
  String get detectLanguages => 'Detecteer 10+ talen';

  @override
  String get authorizeSavingRecordings => 'Opnames opslaan autoriseren';

  @override
  String get thanksForAuthorizing => 'Bedankt voor het autoriseren!';

  @override
  String get needYourPermission => 'We hebben je toestemming nodig';

  @override
  String get alreadyGavePermission =>
      'Je hebt ons al toestemming gegeven om je opnames op te slaan. Hier is een herinnering waarom we het nodig hebben:';

  @override
  String get wouldLikePermission => 'We willen graag je toestemming om je spraakopnames op te slaan. Dit is waarom:';

  @override
  String get improveSpeechProfile => 'Verbeter je spraakprofiel';

  @override
  String get improveSpeechProfileDesc =>
      'We gebruiken opnames om je persoonlijke spraakprofiel verder te trainen en te verbeteren.';

  @override
  String get trainFamilyProfiles => 'Train profielen voor vrienden en familie';

  @override
  String get trainFamilyProfilesDesc =>
      'Je opnames helpen ons om profielen voor je vrienden en familie te herkennen en aan te maken.';

  @override
  String get enhanceTranscriptAccuracy => 'Verbeter transcriptnauwkeurigheid';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'Naarmate ons model verbetert, kunnen we betere transcriptieresultaten voor je opnames bieden.';

  @override
  String get legalNotice =>
      'Juridische kennisgeving: De legaliteit van het opnemen en opslaan van spraakgegevens kan variëren afhankelijk van je locatie en hoe je deze functie gebruikt. Het is jouw verantwoordelijkheid om naleving van lokale wet- en regelgeving te waarborgen.';

  @override
  String get alreadyAuthorized => 'Al geautoriseerd';

  @override
  String get authorize => 'Autoriseren';

  @override
  String get revokeAuthorization => 'Autorisatie intrekken';

  @override
  String get authorizationSuccessful => 'Autorisatie succesvol!';

  @override
  String get failedToAuthorize => 'Autorisatie mislukt. Probeer het opnieuw.';

  @override
  String get authorizationRevoked => 'Autorisatie ingetrokken.';

  @override
  String get recordingsDeleted => 'Opnames verwijderd.';

  @override
  String get failedToRevoke => 'Autorisatie intrekken mislukt. Probeer het opnieuw.';

  @override
  String get permissionRevokedTitle => 'Toestemming ingetrokken';

  @override
  String get permissionRevokedMessage => 'Wil je dat we ook al je bestaande opnames verwijderen?';

  @override
  String get yes => 'Ja';

  @override
  String get editName => 'Naam bewerken';

  @override
  String get howShouldOmiCallYou => 'Hoe moet Omi je noemen?';

  @override
  String get enterYourName => 'Voer je naam in';

  @override
  String get nameCannotBeEmpty => 'Naam mag niet leeg zijn';

  @override
  String get nameUpdatedSuccessfully => 'Naam succesvol bijgewerkt!';

  @override
  String get calendarSettings => 'Agenda-instellingen';

  @override
  String get calendarProviders => 'Agenda-providers';

  @override
  String get macOsCalendar => 'macOS-agenda';

  @override
  String get connectMacOsCalendar => 'Verbind je lokale macOS-agenda';

  @override
  String get googleCalendar => 'Google Agenda';

  @override
  String get syncGoogleAccount => 'Synchroniseer met je Google-account';

  @override
  String get showMeetingsMenuBar => 'Toon aankomende vergaderingen in menubalk';

  @override
  String get showMeetingsMenuBarDesc => 'Toon je volgende vergadering en tijd tot deze begint in de macOS-menubalk';

  @override
  String get showEventsNoParticipants => 'Evenementen zonder deelnemers tonen';

  @override
  String get showEventsNoParticipantsDesc =>
      'Wanneer ingeschakeld, toont Binnenkort evenementen zonder deelnemers of videolink.';

  @override
  String get yourMeetings => 'Je vergaderingen';

  @override
  String get refresh => 'Vernieuwen';

  @override
  String get noUpcomingMeetings => 'Geen aankomende vergaderingen gevonden';

  @override
  String get checkingNextDays => 'Volgende 30 dagen controleren';

  @override
  String get tomorrow => 'Morgen';

  @override
  String get googleCalendarComingSoon => 'Google Agenda-integratie komt binnenkort!';

  @override
  String connectedAsUser(String userId) {
    return 'Verbonden als gebruiker: $userId';
  }

  @override
  String get defaultWorkspace => 'Standaard werkruimte';

  @override
  String get tasksCreatedInWorkspace => 'Taken worden aangemaakt in deze werkruimte';

  @override
  String get defaultProjectOptional => 'Standaardproject (optioneel)';

  @override
  String get leaveUnselectedTasks => 'Laat niet geselecteerd om taken zonder project aan te maken';

  @override
  String get noProjectsInWorkspace => 'Geen projecten gevonden in deze werkruimte';

  @override
  String get conversationTimeoutDesc =>
      'Kies hoe lang te wachten in stilte voordat een gesprek automatisch wordt beëindigd:';

  @override
  String get timeout2Minutes => '2 minuten';

  @override
  String get timeout2MinutesDesc => 'Gesprek beëindigen na 2 minuten stilte';

  @override
  String get timeout5Minutes => '5 minuten';

  @override
  String get timeout5MinutesDesc => 'Gesprek beëindigen na 5 minuten stilte';

  @override
  String get timeout10Minutes => '10 minuten';

  @override
  String get timeout10MinutesDesc => 'Gesprek beëindigen na 10 minuten stilte';

  @override
  String get timeout30Minutes => '30 minuten';

  @override
  String get timeout30MinutesDesc => 'Gesprek beëindigen na 30 minuten stilte';

  @override
  String get timeout4Hours => '4 uur';

  @override
  String get timeout4HoursDesc => 'Gesprek beëindigen na 4 uur stilte';

  @override
  String get conversationEndAfterHours => 'Gesprekken eindigen nu na 4 uur stilte';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Gesprekken eindigen nu na $minutes minuut/minuten stilte';
  }

  @override
  String get tellUsPrimaryLanguage => 'Vertel ons je primaire taal';

  @override
  String get languageForTranscription =>
      'Stel je taal in voor scherpere transcripties en een gepersonaliseerde ervaring.';

  @override
  String get singleLanguageModeInfo =>
      'Enkeltaalmodus is ingeschakeld. Vertaling is uitgeschakeld voor hogere nauwkeurigheid.';

  @override
  String get searchLanguageHint => 'Zoek taal op naam of code';

  @override
  String get noLanguagesFound => 'Geen talen gevonden';

  @override
  String get skip => 'Overslaan';

  @override
  String languageSetTo(String language) {
    return 'Taal ingesteld op $language';
  }

  @override
  String get failedToSetLanguage => 'Kan taal niet instellen';

  @override
  String appSettings(String appName) {
    return '$appName-instellingen';
  }

  @override
  String disconnectFromApp(String appName) {
    return 'Loskoppelen van $appName?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'Dit verwijdert je $appName-authenticatie. Je moet opnieuw verbinden om het weer te gebruiken.';
  }

  @override
  String connectedToApp(String appName) {
    return 'Verbonden met $appName';
  }

  @override
  String get account => 'Account';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Je actiepunten worden gesynchroniseerd met je $appName-account';
  }

  @override
  String get defaultSpace => 'Standaardruimte';

  @override
  String get selectSpaceInWorkspace => 'Selecteer een ruimte in je werkruimte';

  @override
  String get noSpacesInWorkspace => 'Geen ruimtes gevonden in deze werkruimte';

  @override
  String get defaultList => 'Standaardlijst';

  @override
  String get tasksAddedToList => 'Taken worden toegevoegd aan deze lijst';

  @override
  String get noListsInSpace => 'Geen lijsten gevonden in deze ruimte';

  @override
  String failedToLoadRepos(String error) {
    return 'Laden van repositories mislukt: $error';
  }

  @override
  String get defaultRepoSaved => 'Standaard repository opgeslagen';

  @override
  String get failedToSaveDefaultRepo => 'Opslaan van standaard repository mislukt';

  @override
  String get defaultRepository => 'Standaard repository';

  @override
  String get selectDefaultRepoDesc =>
      'Selecteer een standaard repository voor het aanmaken van issues. Je kunt nog steeds een andere repository opgeven bij het aanmaken van issues.';

  @override
  String get noReposFound => 'Geen repositories gevonden';

  @override
  String get private => 'Privé';

  @override
  String updatedDate(String date) {
    return 'Bijgewerkt $date';
  }

  @override
  String get yesterday => 'gisteren';

  @override
  String daysAgo(int count) {
    return '$count dagen geleden';
  }

  @override
  String get oneWeekAgo => '1 week geleden';

  @override
  String weeksAgo(int count) {
    return '$count weken geleden';
  }

  @override
  String get oneMonthAgo => '1 maand geleden';

  @override
  String monthsAgo(int count) {
    return '$count maanden geleden';
  }

  @override
  String get issuesCreatedInRepo => 'Issues worden aangemaakt in je standaard repository';

  @override
  String get taskIntegrations => 'Taakintegraties';

  @override
  String get configureSettings => 'Instellingen configureren';

  @override
  String get completeAuthBrowser => 'Voltooi de authenticatie in je browser. Keer daarna terug naar de app.';

  @override
  String failedToStartAppAuth(String appName) {
    return 'Kan $appName-authenticatie niet starten';
  }

  @override
  String connectToAppTitle(String appName) {
    return 'Verbinden met $appName';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Je moet Omi autoriseren om taken aan te maken in je $appName-account. Dit opent je browser voor authenticatie.';
  }

  @override
  String get continueButton => 'Doorgaan';

  @override
  String appIntegration(String appName) {
    return '$appName-integratie';
  }

  @override
  String integrationComingSoon(String appName) {
    return 'Integratie met $appName komt binnenkort! We werken hard om je meer taakbeheeropties te bieden.';
  }

  @override
  String get gotIt => 'Begrepen';

  @override
  String get tasksExportedOneApp => 'Taken kunnen naar één app tegelijk worden geëxporteerd.';

  @override
  String get completeYourUpgrade => 'Voltooi je upgrade';

  @override
  String get importConfiguration => 'Configuratie importeren';

  @override
  String get exportConfiguration => 'Configuratie exporteren';

  @override
  String get bringYourOwn => 'Breng je eigen mee';

  @override
  String get payYourSttProvider => 'Gebruik Omi vrij. Je betaalt alleen je STT-provider rechtstreeks.';

  @override
  String get freeMinutesMonth => '1.200 gratis minuten/maand inbegrepen. Onbeperkt met ';

  @override
  String get omiUnlimited => 'Omi Onbeperkt';

  @override
  String get hostRequired => 'Host is vereist';

  @override
  String get validPortRequired => 'Geldige poort is vereist';

  @override
  String get validWebsocketUrlRequired => 'Geldige WebSocket-URL is vereist (wss://)';

  @override
  String get apiUrlRequired => 'API-URL is vereist';

  @override
  String get apiKeyRequired => 'API-sleutel is vereist';

  @override
  String get invalidJsonConfig => 'Ongeldige JSON-configuratie';

  @override
  String errorSaving(String error) {
    return 'Fout bij opslaan: $error';
  }

  @override
  String get configCopiedToClipboard => 'Configuratie gekopieerd naar klembord';

  @override
  String get pasteJsonConfig => 'Plak je JSON-configuratie hieronder:';

  @override
  String get addApiKeyAfterImport => 'Je moet je eigen API-sleutel toevoegen na het importeren';

  @override
  String get paste => 'Plakken';

  @override
  String get import => 'Importeren';

  @override
  String get invalidProviderInConfig => 'Ongeldige provider in configuratie';

  @override
  String importedConfig(String providerName) {
    return '$providerName-configuratie geïmporteerd';
  }

  @override
  String invalidJson(String error) {
    return 'Ongeldige JSON: $error';
  }

  @override
  String get provider => 'Provider';

  @override
  String get live => 'Live';

  @override
  String get onDevice => 'Op apparaat';

  @override
  String get apiUrl => 'API-URL';

  @override
  String get enterSttHttpEndpoint => 'Voer je STT HTTP-endpoint in';

  @override
  String get websocketUrl => 'WebSocket-URL';

  @override
  String get enterLiveSttWebsocket => 'Voer je live STT WebSocket-endpoint in';

  @override
  String get apiKey => 'API-sleutel';

  @override
  String get enterApiKey => 'Voer je API-sleutel in';

  @override
  String get storedLocallyNeverShared => 'Lokaal opgeslagen, nooit gedeeld';

  @override
  String get host => 'Host';

  @override
  String get port => 'Poort';

  @override
  String get advanced => 'Geavanceerd';

  @override
  String get configuration => 'Configuratie';

  @override
  String get requestConfiguration => 'Verzoek configuratie';

  @override
  String get responseSchema => 'Response schema';

  @override
  String get modified => 'Aangepast';

  @override
  String get resetRequestConfig => 'Verzoekconfiguratie resetten naar standaard';

  @override
  String get logs => 'Logboeken';

  @override
  String get logsCopied => 'Logboeken gekopieerd';

  @override
  String get noLogsYet => 'Nog geen logboeken. Start een opname om aangepaste STT-activiteit te zien.';

  @override
  String deviceUsesCodec(String deviceName, String codecReason) {
    return '$deviceName gebruikt $codecReason. Omi wordt gebruikt.';
  }

  @override
  String get omiTranscription => 'Omi-transcriptie';

  @override
  String get bestInClassTranscription => 'Beste transcriptie zonder configuratie';

  @override
  String get instantSpeakerLabels => 'Directe sprekerslabels';

  @override
  String get languageTranslation => '100+ taalvertaling';

  @override
  String get optimizedForConversation => 'Geoptimaliseerd voor gesprekken';

  @override
  String get autoLanguageDetection => 'Automatische taaldetectie';

  @override
  String get highAccuracy => 'Hoge nauwkeurigheid';

  @override
  String get privacyFirst => 'Privacy eerst';

  @override
  String get saveChanges => 'Wijzigingen opslaan';

  @override
  String get resetToDefault => 'Resetten naar standaard';

  @override
  String get viewTemplate => 'Template bekijken';

  @override
  String get trySomethingLike => 'Probeer iets als...';

  @override
  String get tryIt => 'Probeer het';

  @override
  String get creatingPlan => 'Plan maken';

  @override
  String get developingLogic => 'Logica ontwikkelen';

  @override
  String get designingApp => 'App ontwerpen';

  @override
  String get generatingIconStep => 'Icoon genereren';

  @override
  String get finalTouches => 'Laatste aanpassingen';

  @override
  String get processing => 'Verwerken...';

  @override
  String get features => 'Functies';

  @override
  String get creatingYourApp => 'Je app maken...';

  @override
  String get generatingIcon => 'Icoon genereren...';

  @override
  String get whatShouldWeMake => 'Wat zullen we maken?';

  @override
  String get appName => 'App-naam';

  @override
  String get description => 'Beschrijving';

  @override
  String get publicLabel => 'Openbaar';

  @override
  String get privateLabel => 'Privé';

  @override
  String get free => 'Gratis';

  @override
  String get perMonth => '/ Maand';

  @override
  String get tailoredConversationSummaries => 'Op maat gemaakte gesprekssamenvattingen';

  @override
  String get customChatbotPersonality => 'Aangepaste chatbot-persoonlijkheid';

  @override
  String get makePublic => 'Openbaar maken';

  @override
  String get anyoneCanDiscover => 'Iedereen kan je app ontdekken';

  @override
  String get onlyYouCanUse => 'Alleen jij kunt deze app gebruiken';

  @override
  String get paidApp => 'Betaalde app';

  @override
  String get usersPayToUse => 'Gebruikers betalen om je app te gebruiken';

  @override
  String get freeForEveryone => 'Gratis voor iedereen';

  @override
  String get perMonthLabel => '/ maand';

  @override
  String get creating => 'Maken...';

  @override
  String get createApp => 'App maken';

  @override
  String get searchingForDevices => 'Zoeken naar apparaten...';

  @override
  String devicesFoundNearby(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'APPARATEN',
      one: 'APPARAAT',
    );
    return '$count $_temp0 GEVONDEN IN DE BUURT';
  }

  @override
  String get pairingSuccessful => 'KOPPELEN SUCCESVOL';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Fout bij verbinden met Apple Watch: $error';
  }

  @override
  String get dontShowAgain => 'Niet meer tonen';

  @override
  String get iUnderstand => 'Ik begrijp het';

  @override
  String get enableBluetooth => 'Bluetooth inschakelen';

  @override
  String get bluetoothNeeded =>
      'Omi heeft Bluetooth nodig om verbinding te maken met je wearable. Schakel Bluetooth in en probeer het opnieuw.';

  @override
  String get contactSupport => 'Contact opnemen met support?';

  @override
  String get connectLater => 'Later verbinden';

  @override
  String get grantPermissions => 'Machtigingen verlenen';

  @override
  String get backgroundActivity => 'Achtergrondactiviteit';

  @override
  String get backgroundActivityDesc => 'Laat Omi op de achtergrond draaien voor betere stabiliteit';

  @override
  String get locationAccess => 'Locatietoegang';

  @override
  String get locationAccessDesc => 'Schakel achtergrondlocatie in voor de volledige ervaring';

  @override
  String get notifications => 'Meldingen';

  @override
  String get notificationsDesc => 'Schakel meldingen in om op de hoogte te blijven';

  @override
  String get locationServiceDisabled => 'Locatieservice uitgeschakeld';

  @override
  String get locationServiceDisabledDesc =>
      'Locatieservice is uitgeschakeld. Ga naar Instellingen > Privacy en beveiliging > Locatievoorzieningen en schakel deze in';

  @override
  String get backgroundLocationDenied => 'Achtergrondlocatietoegang geweigerd';

  @override
  String get backgroundLocationDeniedDesc =>
      'Ga naar apparaatinstellingen en stel locatiemachtiging in op \"Altijd toestaan\"';

  @override
  String get lovingOmi => 'Ben je blij met Omi?';

  @override
  String get leaveReviewIos =>
      'Help ons meer mensen te bereiken door een review achter te laten in de App Store. Je feedback betekent enorm veel voor ons!';

  @override
  String get leaveReviewAndroid =>
      'Help ons meer mensen te bereiken door een review achter te laten in de Google Play Store. Je feedback betekent enorm veel voor ons!';

  @override
  String get rateOnAppStore => 'Beoordelen in App Store';

  @override
  String get rateOnGooglePlay => 'Beoordelen in Google Play';

  @override
  String get maybeLater => 'Misschien later';

  @override
  String get speechProfileIntro => 'Omi moet je doelen en je stem leren. Je kunt dit later aanpassen.';

  @override
  String get getStarted => 'Aan de slag';

  @override
  String get allDone => 'Helemaal klaar!';

  @override
  String get keepGoing => 'Ga zo door, je doet het geweldig';

  @override
  String get skipThisQuestion => 'Deze vraag overslaan';

  @override
  String get skipForNow => 'Voorlopig overslaan';

  @override
  String get connectionError => 'Verbindingsfout';

  @override
  String get connectionErrorDesc =>
      'Kan geen verbinding maken met de server. Controleer je internetverbinding en probeer het opnieuw.';

  @override
  String get invalidRecordingMultipleSpeakers => 'Ongeldige opname gedetecteerd';

  @override
  String get multipleSpeakersDesc =>
      'Het lijkt erop dat er meerdere sprekers in de opname zijn. Zorg ervoor dat je op een rustige locatie bent en probeer het opnieuw.';

  @override
  String get tooShortDesc => 'Er is niet genoeg spraak gedetecteerd. Spreek meer en probeer het opnieuw.';

  @override
  String get invalidRecordingDesc => 'Zorg ervoor dat je minimaal 5 seconden en niet meer dan 90 seconden spreekt.';

  @override
  String get areYouThere => 'Ben je er nog?';

  @override
  String get noSpeechDesc =>
      'We konden geen spraak detecteren. Zorg ervoor dat je minimaal 10 seconden en niet meer dan 3 minuten spreekt.';

  @override
  String get connectionLost => 'Verbinding verbroken';

  @override
  String get connectionLostDesc =>
      'De verbinding is onderbroken. Controleer je internetverbinding en probeer het opnieuw.';

  @override
  String get tryAgain => 'Opnieuw proberen';

  @override
  String get connectOmiOmiGlass => 'Omi / OmiGlass verbinden';

  @override
  String get continueWithoutDevice => 'Doorgaan zonder apparaat';

  @override
  String get permissionsRequired => 'Machtigingen vereist';

  @override
  String get permissionsRequiredDesc =>
      'Deze app heeft Bluetooth- en locatiemachtigingen nodig om correct te functioneren. Schakel deze in via de instellingen.';

  @override
  String get openSettings => 'Instellingen openen';

  @override
  String get wantDifferentName => 'Wil je een andere naam gebruiken?';

  @override
  String get whatsYourName => 'Hoe heet je?';

  @override
  String get speakTranscribeSummarize => 'Spreek. Transcribeer. Vat samen.';

  @override
  String get signInWithApple => 'Inloggen met Apple';

  @override
  String get signInWithGoogle => 'Inloggen met Google';

  @override
  String get byContinuingAgree => 'Door verder te gaan, ga je akkoord met ons ';

  @override
  String get termsOfUse => 'Gebruiksvoorwaarden';

  @override
  String get omiYourAiCompanion => 'Omi – Je AI-metgezel';

  @override
  String get captureEveryMoment =>
      'Leg elk moment vast. Krijg AI-aangedreven\nsamenvattingen. Nooit meer notities maken.';

  @override
  String get appleWatchSetup => 'Apple Watch instellen';

  @override
  String get permissionRequestedExclaim => 'Toestemming gevraagd!';

  @override
  String get microphonePermission => 'Microfoontoestemming';

  @override
  String get permissionGrantedNow =>
      'Toestemming verleend! Nu:\n\nOpen de Omi-app op je horloge en tik hieronder op \"Doorgaan\"';

  @override
  String get needMicrophonePermission =>
      'We hebben microfoontoestemming nodig.\n\n1. Tik op \"Toestemming verlenen\"\n2. Sta toe op je iPhone\n3. Horloge-app sluit\n4. Heropen en tik op \"Doorgaan\"';

  @override
  String get grantPermissionButton => 'Toestemming verlenen';

  @override
  String get needHelp => 'Hulp nodig?';

  @override
  String get troubleshootingSteps =>
      'Probleemoplossing:\n\n1. Zorg dat Omi op je horloge is geïnstalleerd\n2. Open de Omi-app op je horloge\n3. Zoek naar de toestemmingspopup\n4. Tik op \"Toestaan\" wanneer gevraagd\n5. App op je horloge sluit - heropen deze\n6. Kom terug en tik op \"Doorgaan\" op je iPhone';

  @override
  String get recordingStartedSuccessfully => 'Opname succesvol gestart!';

  @override
  String get permissionNotGrantedYet =>
      'Toestemming nog niet verleend. Zorg dat je microfoontoestemming hebt gegeven en de app op je horloge hebt heropend.';

  @override
  String errorRequestingPermission(String error) {
    return 'Fout bij het vragen van toestemming: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'Fout bij het starten van opname: $error';
  }

  @override
  String get selectPrimaryLanguage => 'Selecteer je primaire taal';

  @override
  String get languageBenefits => 'Stel je taal in voor scherpere transcripties en een gepersonaliseerde ervaring';

  @override
  String get whatsYourPrimaryLanguage => 'Wat is je primaire taal?';

  @override
  String get selectYourLanguage => 'Selecteer je taal';

  @override
  String get personalGrowthJourney => 'Je persoonlijke groeireis met AI die naar elk woord luistert.';

  @override
  String get actionItemsTitle => 'Taken';

  @override
  String get actionItemsDescription => 'Tik om te bewerken • Lang indrukken om te selecteren • Veeg voor acties';

  @override
  String get tabToDo => 'Te doen';

  @override
  String get tabDone => 'Klaar';

  @override
  String get tabOld => 'Oud';

  @override
  String get emptyTodoMessage => '🎉 Alles bijgewerkt!\nGeen openstaande actiepunten';

  @override
  String get emptyDoneMessage => 'Nog geen voltooide items';

  @override
  String get emptyOldMessage => '✅ Geen oude taken';

  @override
  String get noItems => 'Geen items';

  @override
  String get actionItemMarkedIncomplete => 'Actiepunt gemarkeerd als niet voltooid';

  @override
  String get actionItemCompleted => 'Actiepunt voltooid';

  @override
  String get deleteActionItemTitle => 'Actiepunt verwijderen';

  @override
  String get deleteActionItemMessage => 'Weet je zeker dat je dit actiepunt wilt verwijderen?';

  @override
  String get deleteSelectedItemsTitle => 'Geselecteerde items verwijderen';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Weet je zeker dat je $count geselecteerde actiepunt(en) wilt verwijderen?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'Actiepunt \"$description\" verwijderd';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count actiepunt(en) verwijderd';
  }

  @override
  String get failedToDeleteItem => 'Kan actiepunt niet verwijderen';

  @override
  String get failedToDeleteItems => 'Kan items niet verwijderen';

  @override
  String get failedToDeleteSomeItems => 'Kan sommige items niet verwijderen';

  @override
  String get welcomeActionItemsTitle => 'Klaar voor actiepunten';

  @override
  String get welcomeActionItemsDescription =>
      'Je AI haalt automatisch taken en to-do\'s uit je gesprekken. Ze verschijnen hier wanneer ze zijn aangemaakt.';

  @override
  String get autoExtractionFeature => 'Automatisch geëxtraheerd uit gesprekken';

  @override
  String get editSwipeFeature => 'Tik om te bewerken, veeg om te voltooien of te verwijderen';

  @override
  String itemsSelected(int count) {
    return '$count geselecteerd';
  }

  @override
  String get selectAll => 'Alles selecteren';

  @override
  String get deleteSelected => 'Geselecteerde verwijderen';

  @override
  String searchMemories(int count) {
    return 'Zoek in $count herinneringen';
  }

  @override
  String get memoryDeleted => 'Herinnering verwijderd.';

  @override
  String get undo => 'Ongedaan maken';

  @override
  String get noMemoriesYet => 'Nog geen herinneringen';

  @override
  String get noAutoMemories => 'Nog geen automatisch geëxtraheerde herinneringen';

  @override
  String get noManualMemories => 'Nog geen handmatige herinneringen';

  @override
  String get noMemoriesInCategories => 'Geen herinneringen in deze categorieën';

  @override
  String get noMemoriesFound => 'Geen herinneringen gevonden';

  @override
  String get addFirstMemory => 'Voeg je eerste herinnering toe';

  @override
  String get clearMemoryTitle => 'Omi\'s geheugen wissen';

  @override
  String get clearMemoryMessage =>
      'Weet je zeker dat je Omi\'s geheugen wilt wissen? Deze actie kan niet ongedaan worden gemaakt.';

  @override
  String get clearMemoryButton => 'Geheugen wissen';

  @override
  String get memoryClearedSuccess => 'Omi\'s geheugen over jou is gewist';

  @override
  String get noMemoriesToDelete => 'Geen herinneringen om te verwijderen';

  @override
  String get createMemoryTooltip => 'Nieuwe herinnering maken';

  @override
  String get createActionItemTooltip => 'Nieuw actiepunt maken';

  @override
  String get memoryManagement => 'Geheugenbeheer';

  @override
  String get filterMemories => 'Herinneringen filteren';

  @override
  String totalMemoriesCount(int count) {
    return 'Je hebt $count herinneringen in totaal';
  }

  @override
  String get publicMemories => 'Openbare herinneringen';

  @override
  String get privateMemories => 'Privé herinneringen';

  @override
  String get makeAllPrivate => 'Alle herinneringen privé maken';

  @override
  String get makeAllPublic => 'Alle herinneringen openbaar maken';

  @override
  String get deleteAllMemories => 'Alle herinneringen verwijderen';

  @override
  String get allMemoriesPrivateResult => 'Alle herinneringen zijn nu privé';

  @override
  String get allMemoriesPublicResult => 'Alle herinneringen zijn nu openbaar';

  @override
  String get newMemory => 'Nieuwe herinnering';

  @override
  String get editMemory => 'Herinnering bewerken';

  @override
  String get memoryContentHint => 'Ik hou van ijs eten...';

  @override
  String get failedToSaveMemory => 'Opslaan mislukt. Controleer je verbinding.';

  @override
  String get saveMemory => 'Herinnering opslaan';

  @override
  String get retry => 'Opnieuw proberen';

  @override
  String get createActionItem => 'Actiepunt maken';

  @override
  String get editActionItem => 'Actiepunt bewerken';

  @override
  String get actionItemDescriptionHint => 'Wat moet er gedaan worden?';

  @override
  String get actionItemDescriptionEmpty => 'Actiepuntbeschrijving mag niet leeg zijn.';

  @override
  String get actionItemUpdated => 'Actiepunt bijgewerkt';

  @override
  String get failedToUpdateActionItem => 'Kan actiepunt niet bijwerken';

  @override
  String get actionItemCreated => 'Actiepunt aangemaakt';

  @override
  String get failedToCreateActionItem => 'Kan actiepunt niet maken';

  @override
  String get dueDate => 'Vervaldatum';

  @override
  String get time => 'Tijd';

  @override
  String get addDueDate => 'Vervaldatum toevoegen';

  @override
  String get pressDoneToSave => 'Druk op Klaar om op te slaan';

  @override
  String get pressDoneToCreate => 'Druk op Klaar om aan te maken';

  @override
  String get filterAll => 'Alle';

  @override
  String get filterSystem => 'Over jou';

  @override
  String get filterInteresting => 'Inzichten';

  @override
  String get filterManual => 'Handmatig';

  @override
  String get completed => 'Voltooid';

  @override
  String get markComplete => 'Markeer als voltooid';

  @override
  String get actionItemDeleted => 'Actiepunt verwijderd';

  @override
  String get failedToDeleteActionItem => 'Kan actiepunt niet verwijderen';

  @override
  String get deleteActionItemConfirmTitle => 'Actiepunt verwijderen';

  @override
  String get deleteActionItemConfirmMessage => 'Weet je zeker dat je dit actiepunt wilt verwijderen?';

  @override
  String get appLanguage => 'App-taal';

  @override
  String get appInterfaceSectionTitle => 'APP-INTERFACE';

  @override
  String get speechTranscriptionSectionTitle => 'SPRAAK & TRANSCRIPTIE';

  @override
  String get languageSettingsHelperText =>
      'App-taal verandert menu\'s en knoppen. Spraaktaal beïnvloedt hoe je opnames worden getranscribeerd.';
}
