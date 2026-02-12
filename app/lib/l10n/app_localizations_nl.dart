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
  String get transcriptTab => 'Transcriptie';

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
  String get copyTranscript => 'Kopieer transcript';

  @override
  String get copySummary => 'Kopieer samenvatting';

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
  String get noInternetConnection => 'Geen internetverbinding';

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
  String get disconnected => 'Verbroken';

  @override
  String get searching => 'Zoeken...';

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
  String get noConversationsYet => 'Nog geen gesprekken';

  @override
  String get noStarredConversations => 'Geen gesprekken met ster';

  @override
  String get starConversationHint =>
      'Om een gesprek als favoriet te markeren, open het en tik op het stericoon in de header.';

  @override
  String get searchConversations => 'Zoek gesprekken...';

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
  String get deletingMessages => 'Uw berichten verwijderen uit het geheugen van Omi...';

  @override
  String get messageCopied => '✨ Bericht gekopieerd naar klembord';

  @override
  String get cannotReportOwnMessage => 'Je kunt je eigen berichten niet rapporteren.';

  @override
  String get reportMessage => 'Bericht melden';

  @override
  String get reportMessageConfirm => 'Weet je zeker dat je dit bericht wilt rapporteren?';

  @override
  String get messageReported => 'Bericht succesvol gerapporteerd.';

  @override
  String get thankYouFeedback => 'Bedankt voor je feedback!';

  @override
  String get clearChat => 'Chat wissen';

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
  String get searchApps => 'Apps zoeken...';

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
  String get visitWebsite => 'Bezoek website';

  @override
  String get helpOrInquiries => 'Hulp of vragen?';

  @override
  String get joinCommunity => 'Word lid van de community!';

  @override
  String get membersAndCounting => '8000+ leden en groeiend.';

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
  String get customVocabulary => 'Aangepaste Woordenschat';

  @override
  String get identifyingOthers => 'Identificatie van Anderen';

  @override
  String get paymentMethods => 'Betaalmethoden';

  @override
  String get conversationDisplay => 'Gespreksweergave';

  @override
  String get dataPrivacy => 'Gegevensprivacy';

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
  String get integrations => 'Integraties';

  @override
  String get feedbackBug => 'Feedback / Fout';

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
  String get endpointUrl => 'Eindpunt-URL';

  @override
  String get noApiKeys => 'Nog geen API-sleutels';

  @override
  String get createKeyToStart => 'Maak een sleutel aan om te beginnen';

  @override
  String get createKey => 'Sleutel Maken';

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
  String get debugLogs => 'Debuglogboeken';

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
  String get knowledgeGraphDeleted => 'Kennisgraaf verwijderd';

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
  String get header => 'Koptekst';

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
  String get realtimeTranscript => 'Realtime transcriptie';

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
  String get connect => 'Connect';

  @override
  String get comingSoon => 'Binnenkort beschikbaar';

  @override
  String get integrationsFooter => 'Verbind je apps om gegevens en statistieken in de chat te bekijken.';

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
  String get enterYourName => 'Voer uw naam in';

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
  String get noUpcomingMeetings => 'Geen aankomende vergaderingen';

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
  String get yesterday => 'Gisteren';

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
  String deviceUsesCodec(String device, String reason) {
    return '$device gebruikt $reason. Omi wordt gebruikt.';
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
  String get resetToDefault => 'Terugzetten naar standaard';

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
  String get appName => 'App Name';

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
  String get dontShowAgain => 'Niet meer weergeven';

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
  String get speechProfileIntro => 'Omi moet je doelen en je stem leren. Je kunt het later aanpassen.';

  @override
  String get getStarted => 'Aan de slag';

  @override
  String get allDone => 'Helemaal klaar!';

  @override
  String get keepGoing => 'Ga zo door, je doet het geweldig';

  @override
  String get skipThisQuestion => 'Sla deze vraag over';

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
  String get whatsYourName => 'Wat is je naam?';

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
  String get personalGrowthJourney => 'Jouw persoonlijke groeireis met AI die naar elk woord luistert.';

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
  String get deleteActionItemMessage => 'Weet u zeker dat u dit actiepunt wilt verwijderen?';

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
  String get searchMemories => 'Herinneringen zoeken...';

  @override
  String get memoryDeleted => 'Herinnering verwijderd.';

  @override
  String get undo => 'Ongedaan maken';

  @override
  String get noMemoriesYet => '🧠 Nog geen herinneringen';

  @override
  String get noAutoMemories => 'Nog geen automatisch geëxtraheerde herinneringen';

  @override
  String get noManualMemories => 'Nog geen handmatige herinneringen';

  @override
  String get noMemoriesInCategories => 'Geen herinneringen in deze categorieën';

  @override
  String get noMemoriesFound => '🔍 Geen herinneringen gevonden';

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
  String get newMemory => '✨ Nieuw geheugen';

  @override
  String get editMemory => '✏️ Geheugen bewerken';

  @override
  String get memoryContentHint => 'Ik hou van ijs eten...';

  @override
  String get failedToSaveMemory => 'Opslaan mislukt. Controleer je verbinding.';

  @override
  String get saveMemory => 'Herinnering opslaan';

  @override
  String get retry => 'Opnieuw proberen';

  @override
  String get createActionItem => 'Actie-item aanmaken';

  @override
  String get editActionItem => 'Actie-item bewerken';

  @override
  String get actionItemDescriptionHint => 'Wat moet er gedaan worden?';

  @override
  String get actionItemDescriptionEmpty => 'Actiepuntbeschrijving mag niet leeg zijn.';

  @override
  String get actionItemUpdated => 'Actiepunt bijgewerkt';

  @override
  String get failedToUpdateActionItem => 'Actie-item bijwerken mislukt';

  @override
  String get actionItemCreated => 'Actiepunt aangemaakt';

  @override
  String get failedToCreateActionItem => 'Actie-item aanmaken mislukt';

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
  String get markComplete => 'Markeren als voltooid';

  @override
  String get actionItemDeleted => 'Actiepunt verwijderd';

  @override
  String get failedToDeleteActionItem => 'Actie-item verwijderen mislukt';

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

  @override
  String get translationNotice => 'Vertaalbericht';

  @override
  String get translationNoticeMessage =>
      'Omi vertaalt gesprekken naar uw primaire taal. Update deze op elk moment in Instellingen → Profielen.';

  @override
  String get pleaseCheckInternetConnection => 'Controleer uw internetverbinding en probeer het opnieuw';

  @override
  String get pleaseSelectReason => 'Selecteer een reden';

  @override
  String get tellUsMoreWhatWentWrong => 'Vertel ons meer over wat er fout ging...';

  @override
  String get selectText => 'Tekst selecteren';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Maximaal $count doelen toegestaan';
  }

  @override
  String get conversationCannotBeMerged =>
      'Dit gesprek kan niet worden samengevoegd (vergrendeld of al aan het samenvoegen)';

  @override
  String get pleaseEnterFolderName => 'Voer een mapnaam in';

  @override
  String get failedToCreateFolder => 'Kan map niet aanmaken';

  @override
  String get failedToUpdateFolder => 'Kan map niet bijwerken';

  @override
  String get folderName => 'Mapnaam';

  @override
  String get descriptionOptional => 'Description (optional)';

  @override
  String get failedToDeleteFolder => 'Kan map niet verwijderen';

  @override
  String get editFolder => 'Map bewerken';

  @override
  String get deleteFolder => 'Map verwijderen';

  @override
  String get transcriptCopiedToClipboard => 'Transcriptie gekopieerd naar klembord';

  @override
  String get summaryCopiedToClipboard => 'Samenvatting gekopieerd naar klembord';

  @override
  String get conversationUrlCouldNotBeShared => 'Gesprek-URL kon niet worden gedeeld.';

  @override
  String get urlCopiedToClipboard => 'URL gekopieerd naar klembord';

  @override
  String get exportTranscript => 'Transcriptie exporteren';

  @override
  String get exportSummary => 'Samenvatting exporteren';

  @override
  String get exportButton => 'Exporteren';

  @override
  String get actionItemsCopiedToClipboard => 'Actiepunten gekopieerd naar klembord';

  @override
  String get summarize => 'Samenvatten';

  @override
  String get generateSummary => 'Samenvatting genereren';

  @override
  String get conversationNotFoundOrDeleted => 'Gesprek niet gevonden of is verwijderd';

  @override
  String get deleteMemory => 'Geheugen verwijderen';

  @override
  String get thisActionCannotBeUndone => 'Deze actie kan niet ongedaan worden gemaakt.';

  @override
  String memoriesCount(int count) {
    return '$count herinneringen';
  }

  @override
  String get noMemoriesInCategory => 'Nog geen herinneringen in deze categorie';

  @override
  String get addYourFirstMemory => 'Voeg je eerste herinnering toe';

  @override
  String get firmwareDisconnectUsb => 'USB ontkoppelen';

  @override
  String get firmwareUsbWarning => 'USB-verbinding tijdens updates kan uw apparaat beschadigen.';

  @override
  String get firmwareBatteryAbove15 => 'Batterij boven 15%';

  @override
  String get firmwareEnsureBattery => 'Zorg ervoor dat uw apparaat 15% batterij heeft.';

  @override
  String get firmwareStableConnection => 'Stabiele verbinding';

  @override
  String get firmwareConnectWifi => 'Verbind met WiFi of mobiel netwerk.';

  @override
  String failedToStartUpdate(String error) {
    return 'Kan update niet starten: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'Voordat u update, zorg ervoor:';

  @override
  String get confirmed => 'Bevestigd!';

  @override
  String get release => 'Loslaten';

  @override
  String get slideToUpdate => 'Schuif om bij te werken';

  @override
  String copiedToClipboard(String title) {
    return '$title gekopieerd naar klembord';
  }

  @override
  String get batteryLevel => 'Batterijniveau';

  @override
  String get productUpdate => 'Productupdate';

  @override
  String get offline => 'Offline';

  @override
  String get available => 'Beschikbaar';

  @override
  String get unpairDeviceDialogTitle => 'Apparaat ontkoppelen';

  @override
  String get unpairDeviceDialogMessage =>
      'Dit zal het apparaat ontkoppelen zodat het kan worden verbonden met een andere telefoon. U moet naar Instellingen > Bluetooth gaan en het apparaat vergeten om het proces te voltooien.';

  @override
  String get unpair => 'Ontkoppelen';

  @override
  String get unpairAndForgetDevice => 'Ontkoppelen en apparaat vergeten';

  @override
  String get unknownDevice => 'Onbekend';

  @override
  String get unknown => 'Onbekend';

  @override
  String get productName => 'Productnaam';

  @override
  String get serialNumber => 'Serienummer';

  @override
  String get connected => 'Verbonden';

  @override
  String get privacyPolicyTitle => 'Privacybeleid';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label gekopieerd';
  }

  @override
  String get noApiKeysYet => 'Nog geen API-sleutels. Maak er een aan om te integreren met uw app.';

  @override
  String get createKeyToGetStarted => 'Maak een sleutel aan om te beginnen';

  @override
  String get persona => 'Persona';

  @override
  String get configureYourAiPersona => 'Configureer je AI-persona';

  @override
  String get configureSttProvider => 'STT-provider configureren';

  @override
  String get setWhenConversationsAutoEnd => 'Stel in wanneer gesprekken automatisch eindigen';

  @override
  String get importDataFromOtherSources => 'Gegevens importeren uit andere bronnen';

  @override
  String get debugAndDiagnostics => 'Debug & Diagnostiek';

  @override
  String get autoDeletesAfter3Days => 'Wordt automatisch verwijderd na 3 dagen';

  @override
  String get helpsDiagnoseIssues => 'Helpt problemen diagnosticeren';

  @override
  String get exportStartedMessage => 'Export gestart. Dit kan enkele seconden duren...';

  @override
  String get exportConversationsToJson => 'Gesprekken exporteren naar een JSON-bestand';

  @override
  String get knowledgeGraphDeletedSuccess => 'Kennisgraaf succesvol verwijderd';

  @override
  String failedToDeleteGraph(String error) {
    return 'Kon graaf niet verwijderen: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'Alle knooppunten en verbindingen wissen';

  @override
  String get addToClaudeDesktopConfig => 'Toevoegen aan claude_desktop_config.json';

  @override
  String get connectAiAssistantsToData => 'Verbind AI-assistenten met je gegevens';

  @override
  String get useYourMcpApiKey => 'Gebruik je MCP API-sleutel';

  @override
  String get realTimeTranscript => 'Realtime transcriptie';

  @override
  String get experimental => 'Experimenteel';

  @override
  String get transcriptionDiagnostics => 'Transcriptie-diagnostics';

  @override
  String get detailedDiagnosticMessages => 'Gedetailleerde diagnostische berichten';

  @override
  String get autoCreateSpeakers => 'Sprekers automatisch aanmaken';

  @override
  String get autoCreateWhenNameDetected => 'Automatisch aanmaken wanneer naam gedetecteerd wordt';

  @override
  String get followUpQuestions => 'Vervolgvragen';

  @override
  String get suggestQuestionsAfterConversations => 'Vragen voorstellen na gesprekken';

  @override
  String get goalTracker => 'Doel-tracker';

  @override
  String get trackPersonalGoalsOnHomepage => 'Volg je persoonlijke doelen op de startpagina';

  @override
  String get dailyReflection => 'Dagelijkse reflectie';

  @override
  String get get9PmReminderToReflect => 'Ontvang om 21:00 uur een herinnering om te reflecteren op je dag';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'Actiepuntomschrijving mag niet leeg zijn';

  @override
  String get saved => 'Opgeslagen';

  @override
  String get overdue => 'Achterstallig';

  @override
  String get failedToUpdateDueDate => 'Kan vervaldatum niet bijwerken';

  @override
  String get markIncomplete => 'Markeren als onvolledig';

  @override
  String get editDueDate => 'Vervaldatum bewerken';

  @override
  String get setDueDate => 'Vervaldatum instellen';

  @override
  String get clearDueDate => 'Vervaldatum wissen';

  @override
  String get failedToClearDueDate => 'Kan vervaldatum niet wissen';

  @override
  String get mondayAbbr => 'Ma';

  @override
  String get tuesdayAbbr => 'Di';

  @override
  String get wednesdayAbbr => 'Wo';

  @override
  String get thursdayAbbr => 'Do';

  @override
  String get fridayAbbr => 'Vr';

  @override
  String get saturdayAbbr => 'Za';

  @override
  String get sundayAbbr => 'Zo';

  @override
  String get howDoesItWork => 'Hoe werkt het?';

  @override
  String get sdCardSyncDescription => 'SD-kaartsynchronisatie importeert je herinneringen van de SD-kaart naar de app';

  @override
  String get checksForAudioFiles => 'Controleert op audiobestanden op de SD-kaart';

  @override
  String get omiSyncsAudioFiles => 'Omi synchroniseert vervolgens de audiobestanden met de server';

  @override
  String get serverProcessesAudio => 'De server verwerkt de audiobestanden en creëert herinneringen';

  @override
  String get youreAllSet => 'Je bent klaar!';

  @override
  String get welcomeToOmiDescription =>
      'Welkom bij Omi! Je AI-metgezel is klaar om je te helpen met gesprekken, taken en meer.';

  @override
  String get startUsingOmi => 'Begin met Omi';

  @override
  String get back => 'Terug';

  @override
  String get keyboardShortcuts => 'Sneltoetsen';

  @override
  String get toggleControlBar => 'Schakel bedieningsbalk';

  @override
  String get pressKeys => 'Druk op toetsen...';

  @override
  String get cmdRequired => '⌘ vereist';

  @override
  String get invalidKey => 'Ongeldige toets';

  @override
  String get space => 'Spatie';

  @override
  String get search => 'Zoeken';

  @override
  String get searchPlaceholder => 'Zoeken...';

  @override
  String get untitledConversation => 'Naamloos gesprek';

  @override
  String countRemaining(String count) {
    return '$count resterend';
  }

  @override
  String get addGoal => 'Doel toevoegen';

  @override
  String get editGoal => 'Doel bewerken';

  @override
  String get icon => 'Pictogram';

  @override
  String get goalTitle => 'Doeltitel';

  @override
  String get current => 'Huidig';

  @override
  String get target => 'Doel';

  @override
  String get saveGoal => 'Opslaan';

  @override
  String get goals => 'Doelen';

  @override
  String get tapToAddGoal => 'Tik om een doel toe te voegen';

  @override
  String welcomeBack(String name) {
    return 'Welkom terug, $name';
  }

  @override
  String get yourConversations => 'Je gesprekken';

  @override
  String get reviewAndManageConversations => 'Bekijk en beheer je opgenomen gesprekken';

  @override
  String get startCapturingConversations => 'Begin gesprekken vast te leggen met je Omi-apparaat om ze hier te zien.';

  @override
  String get useMobileAppToCapture => 'Gebruik je mobiele app om audio vast te leggen';

  @override
  String get conversationsProcessedAutomatically => 'Gesprekken worden automatisch verwerkt';

  @override
  String get getInsightsInstantly => 'Krijg direct inzichten en samenvattingen';

  @override
  String get showAll => 'Alles tonen →';

  @override
  String get noTasksForToday => 'Geen taken voor vandaag.\\nVraag Omi om meer taken of maak ze handmatig aan.';

  @override
  String get dailyScore => 'DAGELIJKSE SCORE';

  @override
  String get dailyScoreDescription => 'Een score om je te helpen\nbeter te focussen op uitvoering.';

  @override
  String get searchResults => 'Zoekresultaten';

  @override
  String get actionItems => 'Actiepunten';

  @override
  String get tasksToday => 'Vandaag';

  @override
  String get tasksTomorrow => 'Morgen';

  @override
  String get tasksNoDeadline => 'Geen deadline';

  @override
  String get tasksLater => 'Later';

  @override
  String get loadingTasks => 'Taken laden...';

  @override
  String get tasks => 'Taken';

  @override
  String get swipeTasksToIndent => 'Veeg taken om in te springen, sleep tussen categorieën';

  @override
  String get create => 'Aanmaken';

  @override
  String get noTasksYet => 'Nog geen taken';

  @override
  String get tasksFromConversationsWillAppear =>
      'Taken uit je gesprekken verschijnen hier.\nKlik op Aanmaken om er handmatig een toe te voegen.';

  @override
  String get monthJan => 'Jan';

  @override
  String get monthFeb => 'Feb';

  @override
  String get monthMar => 'Mrt';

  @override
  String get monthApr => 'Apr';

  @override
  String get monthMay => 'Mei';

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
  String get actionItemUpdatedSuccessfully => 'Actie-item succesvol bijgewerkt';

  @override
  String get actionItemCreatedSuccessfully => 'Actie-item succesvol aangemaakt';

  @override
  String get actionItemDeletedSuccessfully => 'Actie-item succesvol verwijderd';

  @override
  String get deleteActionItem => 'Actie-item verwijderen';

  @override
  String get deleteActionItemConfirmation =>
      'Weet je zeker dat je dit actie-item wilt verwijderen? Deze actie kan niet ongedaan worden gemaakt.';

  @override
  String get enterActionItemDescription => 'Voer actie-itembeschrijving in...';

  @override
  String get markAsCompleted => 'Markeren als voltooid';

  @override
  String get setDueDateAndTime => 'Vervaldatum en tijd instellen';

  @override
  String get reloadingApps => 'Apps opnieuw laden...';

  @override
  String get loadingApps => 'Apps laden...';

  @override
  String get browseInstallCreateApps => 'Blader, installeer en maak apps';

  @override
  String get all => 'Alles';

  @override
  String get open => 'Openen';

  @override
  String get install => 'Installeren';

  @override
  String get noAppsAvailable => 'Geen apps beschikbaar';

  @override
  String get unableToLoadApps => 'Kan apps niet laden';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'Probeer je zoektermen of filters aan te passen';

  @override
  String get checkBackLaterForNewApps => 'Kom later terug voor nieuwe apps';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'Controleer je internetverbinding en probeer opnieuw';

  @override
  String get createNewApp => 'Nieuwe app maken';

  @override
  String get buildSubmitCustomOmiApp => 'Bouw en dien je aangepaste Omi-app in';

  @override
  String get submittingYourApp => 'Je app wordt ingediend...';

  @override
  String get preparingFormForYou => 'Het formulier wordt voor je voorbereid...';

  @override
  String get appDetails => 'App-gegevens';

  @override
  String get paymentDetails => 'Betalingsgegevens';

  @override
  String get previewAndScreenshots => 'Voorbeeld en schermafbeeldingen';

  @override
  String get appCapabilities => 'App-mogelijkheden';

  @override
  String get aiPrompts => 'AI-prompts';

  @override
  String get chatPrompt => 'Chat-prompt';

  @override
  String get chatPromptPlaceholder =>
      'Je bent een geweldige app, je taak is om te reageren op gebruikersvragen en hen zich goed te laten voelen...';

  @override
  String get conversationPrompt => 'Gespreksprompt';

  @override
  String get conversationPromptPlaceholder =>
      'Je bent een geweldige app, je krijgt een transcriptie en samenvatting van een gesprek...';

  @override
  String get notificationScopes => 'Meldingsbereiken';

  @override
  String get appPrivacyAndTerms => 'App-privacy en -voorwaarden';

  @override
  String get makeMyAppPublic => 'Mijn app openbaar maken';

  @override
  String get submitAppTermsAgreement =>
      'Door deze app in te dienen, ga ik akkoord met de Servicevoorwaarden en het Privacybeleid van Omi AI';

  @override
  String get submitApp => 'App indienen';

  @override
  String get needHelpGettingStarted => 'Hulp nodig om te beginnen?';

  @override
  String get clickHereForAppBuildingGuides => 'Klik hier voor app-bouwgidsen en documentatie';

  @override
  String get submitAppQuestion => 'App indienen?';

  @override
  String get submitAppPublicDescription =>
      'Je app wordt beoordeeld en openbaar gemaakt. Je kunt het onmiddellijk gebruiken, zelfs tijdens de beoordeling!';

  @override
  String get submitAppPrivateDescription =>
      'Je app wordt beoordeeld en privé beschikbaar gemaakt voor jou. Je kunt het onmiddellijk gebruiken, zelfs tijdens de beoordeling!';

  @override
  String get startEarning => 'Begin met verdienen! 💰';

  @override
  String get connectStripeOrPayPal => 'Verbind Stripe of PayPal om betalingen voor je app te ontvangen.';

  @override
  String get connectNow => 'Nu verbinden';

  @override
  String get installsCount => 'Installaties';

  @override
  String get uninstallApp => 'App verwijderen';

  @override
  String get subscribe => 'Abonneren';

  @override
  String get dataAccessNotice => 'Melding gegevenstoegang';

  @override
  String get dataAccessWarning =>
      'Deze app heeft toegang tot uw gegevens. Omi AI is niet verantwoordelijk voor hoe uw gegevens worden gebruikt, gewijzigd of verwijderd door deze app';

  @override
  String get installApp => 'App installeren';

  @override
  String get betaTesterNotice =>
      'U bent een bètatester voor deze app. Het is nog niet openbaar. Het wordt openbaar zodra het is goedgekeurd.';

  @override
  String get appUnderReviewOwner =>
      'Uw app wordt beoordeeld en is alleen zichtbaar voor u. Het wordt openbaar zodra het is goedgekeurd.';

  @override
  String get appRejectedNotice =>
      'Uw app is afgewezen. Werk de app-details bij en dien deze opnieuw in ter beoordeling.';

  @override
  String get setupSteps => 'Installatiestappen';

  @override
  String get setupInstructions => 'Installatie-instructies';

  @override
  String get integrationInstructions => 'Integratie-instructies';

  @override
  String get preview => 'Voorbeeld';

  @override
  String get aboutTheApp => 'Over de app';

  @override
  String get aboutThePersona => 'Over de persona';

  @override
  String get chatPersonality => 'Chatpersoonlijkheid';

  @override
  String get ratingsAndReviews => 'Beoordelingen en recensies';

  @override
  String get noRatings => 'geen beoordelingen';

  @override
  String ratingsCount(String count) {
    return '$count+ beoordelingen';
  }

  @override
  String get errorActivatingApp => 'Fout bij activeren van de app';

  @override
  String get integrationSetupRequired =>
      'Als dit een integratie-app is, zorg er dan voor dat de installatie is voltooid.';

  @override
  String get installed => 'Geïnstalleerd';

  @override
  String get appIdLabel => 'App-ID';

  @override
  String get appNameLabel => 'App-naam';

  @override
  String get appNamePlaceholder => 'Mijn geweldige app';

  @override
  String get pleaseEnterAppName => 'Voer de app-naam in';

  @override
  String get categoryLabel => 'Categorie';

  @override
  String get selectCategory => 'Selecteer categorie';

  @override
  String get descriptionLabel => 'Beschrijving';

  @override
  String get appDescriptionPlaceholder =>
      'Mijn geweldige app is een geweldige app die geweldige dingen doet. Het is de beste app ooit!';

  @override
  String get pleaseProvideValidDescription => 'Geef een geldige beschrijving op';

  @override
  String get appPricingLabel => 'App-prijzen';

  @override
  String get noneSelected => 'Geen geselecteerd';

  @override
  String get appIdCopiedToClipboard => 'App-ID gekopieerd naar klembord';

  @override
  String get appCategoryModalTitle => 'App-categorie';

  @override
  String get pricingFree => 'Gratis';

  @override
  String get pricingPaid => 'Betaald';

  @override
  String get loadingCapabilities => 'Functies laden...';

  @override
  String get filterInstalled => 'Geïnstalleerd';

  @override
  String get filterMyApps => 'Mijn apps';

  @override
  String get clearSelection => 'Selectie wissen';

  @override
  String get filterCategory => 'Categorie';

  @override
  String get rating4PlusStars => '4+ sterren';

  @override
  String get rating3PlusStars => '3+ sterren';

  @override
  String get rating2PlusStars => '2+ sterren';

  @override
  String get rating1PlusStars => '1+ ster';

  @override
  String get filterRating => 'Beoordeling';

  @override
  String get filterCapabilities => 'Functies';

  @override
  String get noNotificationScopesAvailable => 'Geen meldingsbereiken beschikbaar';

  @override
  String get popularApps => 'Populaire apps';

  @override
  String get pleaseProvidePrompt => 'Geef een prompt op';

  @override
  String chatWithAppName(String appName) {
    return 'Chat met $appName';
  }

  @override
  String get defaultAiAssistant => 'Standaard AI-assistent';

  @override
  String get readyToChat => '✨ Klaar om te chatten!';

  @override
  String get connectionNeeded => '🌐 Verbinding nodig';

  @override
  String get startConversation => 'Begin een gesprek en laat de magie beginnen';

  @override
  String get checkInternetConnection => 'Controleer uw internetverbinding';

  @override
  String get wasThisHelpful => 'Was dit nuttig?';

  @override
  String get thankYouForFeedback => 'Bedankt voor uw feedback!';

  @override
  String get maxFilesUploadError => 'U kunt slechts 4 bestanden tegelijk uploaden';

  @override
  String get attachedFiles => '📎 Bijgevoegde bestanden';

  @override
  String get takePhoto => 'Foto maken';

  @override
  String get captureWithCamera => 'Opnemen met camera';

  @override
  String get selectImages => 'Selecteer afbeeldingen';

  @override
  String get chooseFromGallery => 'Kies uit galerij';

  @override
  String get selectFile => 'Selecteer een bestand';

  @override
  String get chooseAnyFileType => 'Kies elk bestandstype';

  @override
  String get cannotReportOwnMessages => 'U kunt uw eigen berichten niet melden';

  @override
  String get messageReportedSuccessfully => '✅ Bericht succesvol gemeld';

  @override
  String get confirmReportMessage => 'Weet u zeker dat u dit bericht wilt melden?';

  @override
  String get selectChatAssistant => 'Selecteer chat-assistent';

  @override
  String get enableMoreApps => 'Meer apps inschakelen';

  @override
  String get chatCleared => 'Chat gewist';

  @override
  String get clearChatTitle => 'Chat wissen?';

  @override
  String get confirmClearChat => 'Weet u zeker dat u de chat wilt wissen? Deze actie kan niet ongedaan worden gemaakt.';

  @override
  String get copy => 'Kopiëren';

  @override
  String get share => 'Delen';

  @override
  String get report => 'Melden';

  @override
  String get microphonePermissionRequired => 'Microfoontoegang is vereist voor spraakopname.';

  @override
  String get microphonePermissionDenied =>
      'Microfoontoegang geweigerd. Verleen toestemming in Systeemvoorkeuren > Privacy & beveiliging > Microfoon.';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'Controleren microfoontoegang mislukt: $error';
  }

  @override
  String get failedToTranscribeAudio => 'Audio transcriberen mislukt';

  @override
  String get transcribing => 'Transcriberen...';

  @override
  String get transcriptionFailed => 'Transcriptie mislukt';

  @override
  String get discardedConversation => 'Verwijderd gesprek';

  @override
  String get at => 'om';

  @override
  String get from => 'van';

  @override
  String get copied => 'Gekopieerd!';

  @override
  String get copyLink => 'Link kopiëren';

  @override
  String get hideTranscript => 'Transcript verbergen';

  @override
  String get viewTranscript => 'Transcript bekijken';

  @override
  String get conversationDetails => 'Gespreksdetails';

  @override
  String get transcript => 'Transcriptie';

  @override
  String segmentsCount(int count) {
    return '$count segmenten';
  }

  @override
  String get noTranscriptAvailable => 'Geen transcript beschikbaar';

  @override
  String get noTranscriptMessage => 'Dit gesprek heeft geen transcript.';

  @override
  String get conversationUrlCouldNotBeGenerated => 'Gesprek-URL kon niet worden gegenereerd.';

  @override
  String get failedToGenerateConversationLink => 'Kan geen gesprekslink genereren';

  @override
  String get failedToGenerateShareLink => 'Kan geen deellink genereren';

  @override
  String get reloadingConversations => 'Gesprekken opnieuw laden...';

  @override
  String get user => 'Gebruiker';

  @override
  String get starred => 'Met ster';

  @override
  String get date => 'Datum';

  @override
  String get noResultsFound => 'Geen resultaten gevonden';

  @override
  String get tryAdjustingSearchTerms => 'Probeer je zoektermen aan te passen';

  @override
  String get starConversationsToFindQuickly => 'Geef gesprekken een ster om ze hier snel te vinden';

  @override
  String noConversationsOnDate(String date) {
    return 'Geen gesprekken op $date';
  }

  @override
  String get trySelectingDifferentDate => 'Probeer een andere datum te selecteren';

  @override
  String get conversations => 'Gesprekken';

  @override
  String get chat => 'Chat';

  @override
  String get actions => 'Acties';

  @override
  String get syncAvailable => 'Synchronisatie beschikbaar';

  @override
  String get referAFriend => 'Verwijs een vriend';

  @override
  String get help => 'Hulp';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'Upgraden naar Pro';

  @override
  String get getOmiDevice => 'Omi apparaat aanschaffen';

  @override
  String get wearableAiCompanion => 'Draagbare AI-metgezel';

  @override
  String get loadingMemories => 'Herinneringen laden...';

  @override
  String get allMemories => 'Alle herinneringen';

  @override
  String get aboutYou => 'Over jou';

  @override
  String get manual => 'Handmatig';

  @override
  String get loadingYourMemories => 'Je herinneringen laden...';

  @override
  String get createYourFirstMemory => 'Maak je eerste herinnering om te beginnen';

  @override
  String get tryAdjustingFilter => 'Probeer je zoekopdracht of filter aan te passen';

  @override
  String get whatWouldYouLikeToRemember => 'Wat wil je onthouden?';

  @override
  String get category => 'Categorie';

  @override
  String get public => 'Openbaar';

  @override
  String get failedToSaveCheckConnection => 'Opslaan mislukt. Controleer je verbinding.';

  @override
  String get createMemory => 'Geheugen maken';

  @override
  String get deleteMemoryConfirmation =>
      'Weet je zeker dat je dit geheugen wilt verwijderen? Deze actie kan niet ongedaan worden gemaakt.';

  @override
  String get makePrivate => 'Privé maken';

  @override
  String get organizeAndControlMemories => 'Organiseer en beheer je herinneringen';

  @override
  String get total => 'Totaal';

  @override
  String get makeAllMemoriesPrivate => 'Alle herinneringen privé maken';

  @override
  String get setAllMemoriesToPrivate => 'Alle herinneringen op privé zetten';

  @override
  String get makeAllMemoriesPublic => 'Alle herinneringen openbaar maken';

  @override
  String get setAllMemoriesToPublic => 'Alle herinneringen op openbaar zetten';

  @override
  String get permanentlyRemoveAllMemories => 'Alle herinneringen permanent verwijderen uit Omi';

  @override
  String get allMemoriesAreNowPrivate => 'Alle herinneringen zijn nu privé';

  @override
  String get allMemoriesAreNowPublic => 'Alle herinneringen zijn nu openbaar';

  @override
  String get clearOmisMemory => 'Omi\'s geheugen wissen';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Weet je zeker dat je Omi\'s geheugen wilt wissen? Deze actie kan niet ongedaan worden gemaakt en zal alle $count herinneringen permanent verwijderen.';
  }

  @override
  String get omisMemoryCleared => 'Omi\'s geheugen over jou is gewist';

  @override
  String get welcomeToOmi => 'Welkom bij Omi';

  @override
  String get continueWithApple => 'Doorgaan met Apple';

  @override
  String get continueWithGoogle => 'Doorgaan met Google';

  @override
  String get byContinuingYouAgree => 'Door door te gaan, ga je akkoord met onze ';

  @override
  String get termsOfService => 'Servicevoorwaarden';

  @override
  String get and => ' en ';

  @override
  String get dataAndPrivacy => 'Data en privacy';

  @override
  String get secureAuthViaAppleId => 'Veilige authenticatie via Apple ID';

  @override
  String get secureAuthViaGoogleAccount => 'Veilige authenticatie via Google-account';

  @override
  String get whatWeCollect => 'Wat we verzamelen';

  @override
  String get dataCollectionMessage =>
      'Door door te gaan, worden je gesprekken, opnames en persoonlijke informatie veilig opgeslagen op onze servers om AI-gedreven inzichten te bieden en alle app-functies mogelijk te maken.';

  @override
  String get dataProtection => 'Gegevensbescherming';

  @override
  String get yourDataIsProtected => 'Je gegevens zijn beschermd en worden beheerst door ons ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'Selecteer uw primaire taal';

  @override
  String get chooseYourLanguage => 'Kies uw taal';

  @override
  String get selectPreferredLanguageForBestExperience => 'Selecteer uw voorkeurstaal voor de beste Omi-ervaring';

  @override
  String get searchLanguages => 'Zoek talen...';

  @override
  String get selectALanguage => 'Selecteer een taal';

  @override
  String get tryDifferentSearchTerm => 'Probeer een andere zoekterm';

  @override
  String get pleaseEnterYourName => 'Voer uw naam in';

  @override
  String get nameMustBeAtLeast2Characters => 'Naam moet minstens 2 tekens bevatten';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'Vertel ons hoe u aangesproken wilt worden. Dit helpt uw Omi-ervaring te personaliseren.';

  @override
  String charactersCount(int count) {
    return '$count tekens';
  }

  @override
  String get enableFeaturesForBestExperience => 'Schakel functies in voor de beste Omi-ervaring op uw apparaat.';

  @override
  String get microphoneAccess => 'Microfoontoegang';

  @override
  String get recordAudioConversations => 'Audiogesprekken opnemen';

  @override
  String get microphoneAccessDescription =>
      'Omi heeft microfoontoegang nodig om uw gesprekken op te nemen en transcripties te leveren.';

  @override
  String get screenRecording => 'Schermopname';

  @override
  String get captureSystemAudioFromMeetings => 'Systeemaudio van vergaderingen vastleggen';

  @override
  String get screenRecordingDescription =>
      'Omi heeft toestemming voor schermopname nodig om systeemaudio van uw browsergebaseerde vergaderingen vast te leggen.';

  @override
  String get accessibility => 'Toegankelijkheid';

  @override
  String get detectBrowserBasedMeetings => 'Browsergebaseerde vergaderingen detecteren';

  @override
  String get accessibilityDescription =>
      'Omi heeft toegankelijkheidstoestemming nodig om te detecteren wanneer u deelneemt aan Zoom-, Meet- of Teams-vergaderingen in uw browser.';

  @override
  String get pleaseWait => 'Even geduld...';

  @override
  String get joinTheCommunity => 'Word lid van de community!';

  @override
  String get loadingProfile => 'Profiel laden...';

  @override
  String get profileSettings => 'Profielinstellingen';

  @override
  String get noEmailSet => 'Geen e-mail ingesteld';

  @override
  String get userIdCopiedToClipboard => 'Gebruikers-ID gekopieerd';

  @override
  String get yourInformation => 'Uw Informatie';

  @override
  String get setYourName => 'Stel uw naam in';

  @override
  String get changeYourName => 'Wijzig uw naam';

  @override
  String get manageYourOmiPersona => 'Beheer uw Omi-persona';

  @override
  String get voiceAndPeople => 'Stem & Mensen';

  @override
  String get teachOmiYourVoice => 'Leer Omi uw stem';

  @override
  String get tellOmiWhoSaidIt => 'Vertel Omi wie het zei 🗣️';

  @override
  String get payment => 'Betaling';

  @override
  String get addOrChangeYourPaymentMethod => 'Betalingsmethode toevoegen of wijzigen';

  @override
  String get preferences => 'Voorkeuren';

  @override
  String get helpImproveOmiBySharing => 'Help Omi te verbeteren door geanonimiseerde analysegegevens te delen';

  @override
  String get deleteAccount => 'Account Verwijderen';

  @override
  String get deleteYourAccountAndAllData => 'Verwijder uw account en alle gegevens';

  @override
  String get clearLogs => 'Logboeken wissen';

  @override
  String get debugLogsCleared => 'Debuglogboeken gewist';

  @override
  String get exportConversations => 'Gesprekken exporteren';

  @override
  String get exportAllConversationsToJson => 'Exporteer al uw gesprekken naar een JSON-bestand.';

  @override
  String get conversationsExportStarted => 'Export van gesprekken gestart. Dit kan enkele seconden duren, even geduld.';

  @override
  String get mcpDescription =>
      'Om Omi te verbinden met andere applicaties om uw herinneringen en gesprekken te lezen, te zoeken en te beheren. Maak een sleutel om te beginnen.';

  @override
  String get apiKeys => 'API-sleutels';

  @override
  String errorLabel(String error) {
    return 'Fout: $error';
  }

  @override
  String get noApiKeysFound => 'Geen API-sleutels gevonden. Maak er een om te beginnen.';

  @override
  String get advancedSettings => 'Geavanceerde instellingen';

  @override
  String get triggersWhenNewConversationCreated => 'Wordt geactiveerd wanneer een nieuw gesprek wordt aangemaakt.';

  @override
  String get triggersWhenNewTranscriptReceived => 'Wordt geactiveerd wanneer een nieuwe transcriptie wordt ontvangen.';

  @override
  String get realtimeAudioBytes => 'Realtime audiobytes';

  @override
  String get triggersWhenAudioBytesReceived => 'Wordt geactiveerd wanneer audiobytes worden ontvangen.';

  @override
  String get everyXSeconds => 'Elke x seconden';

  @override
  String get triggersWhenDaySummaryGenerated => 'Wordt geactiveerd wanneer de dagsamenvatting wordt gegenereerd.';

  @override
  String get tryLatestExperimentalFeatures => 'Probeer de nieuwste experimentele functies van het Omi-team.';

  @override
  String get transcriptionServiceDiagnosticStatus => 'Diagnostische status van transcriptieservice';

  @override
  String get enableDetailedDiagnosticMessages =>
      'Gedetailleerde diagnostische berichten van de transcriptieservice inschakelen';

  @override
  String get autoCreateAndTagNewSpeakers => 'Nieuwe sprekers automatisch aanmaken en taggen';

  @override
  String get automaticallyCreateNewPerson =>
      'Maak automatisch een nieuwe persoon aan wanneer een naam wordt gedetecteerd in de transcriptie.';

  @override
  String get pilotFeatures => 'Pilotfuncties';

  @override
  String get pilotFeaturesDescription => 'Deze functies zijn tests en er wordt geen ondersteuning gegarandeerd.';

  @override
  String get suggestFollowUpQuestion => 'Vervolgvraag voorstellen';

  @override
  String get saveSettings => 'Instellingen Opslaan';

  @override
  String get syncingDeveloperSettings => 'Ontwikkelaarsinstellingen synchroniseren...';

  @override
  String get summary => 'Samenvatting';

  @override
  String get auto => 'Automatisch';

  @override
  String get noSummaryForApp =>
      'Geen samenvatting beschikbaar voor deze app. Probeer een andere app voor betere resultaten.';

  @override
  String get tryAnotherApp => 'Probeer een andere app';

  @override
  String generatedBy(String appName) {
    return 'Gegenereerd door $appName';
  }

  @override
  String get overview => 'Overzicht';

  @override
  String get otherAppResults => 'Resultaten van andere apps';

  @override
  String get unknownApp => 'Onbekende app';

  @override
  String get noSummaryAvailable => 'Geen samenvatting beschikbaar';

  @override
  String get conversationNoSummaryYet => 'Dit gesprek heeft nog geen samenvatting.';

  @override
  String get chooseSummarizationApp => 'Kies samenvattingsapp';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName ingesteld als standaard samenvattingsapp';
  }

  @override
  String get letOmiChooseAutomatically => 'Laat Omi automatisch de beste app kiezen';

  @override
  String get deleteConversationConfirmation =>
      'Weet u zeker dat u dit gesprek wilt verwijderen? Deze actie kan niet ongedaan worden gemaakt.';

  @override
  String get conversationDeleted => 'Gesprek verwijderd';

  @override
  String get generatingLink => 'Link wordt gegenereerd...';

  @override
  String get editConversation => 'Gesprek bewerken';

  @override
  String get conversationLinkCopiedToClipboard => 'Gesprekslink gekopieerd naar klembord';

  @override
  String get conversationTranscriptCopiedToClipboard => 'Gesprekstranscript gekopieerd naar klembord';

  @override
  String get editConversationDialogTitle => 'Gesprek bewerken';

  @override
  String get changeTheConversationTitle => 'Gesprekstitel wijzigen';

  @override
  String get conversationTitle => 'Gesprekstitel';

  @override
  String get enterConversationTitle => 'Voer gesprekstitel in...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'Gesprekstitel succesvol bijgewerkt';

  @override
  String get failedToUpdateConversationTitle => 'Kan gesprekstitel niet bijwerken';

  @override
  String get errorUpdatingConversationTitle => 'Fout bij bijwerken van gesprekstitel';

  @override
  String get settingUp => 'Instellen...';

  @override
  String get startYourFirstRecording => 'Start uw eerste opname';

  @override
  String get preparingSystemAudioCapture => 'Systeemaudio-opname voorbereiden';

  @override
  String get clickTheButtonToCaptureAudio =>
      'Klik op de knop om audio vast te leggen voor live transcripties, AI-inzichten en automatisch opslaan.';

  @override
  String get reconnecting => 'Opnieuw verbinden...';

  @override
  String get recordingPaused => 'Opname gepauzeerd';

  @override
  String get recordingActive => 'Opname actief';

  @override
  String get startRecording => 'Opname starten';

  @override
  String resumingInCountdown(String countdown) {
    return 'Hervatten over ${countdown}s...';
  }

  @override
  String get tapPlayToResume => 'Tik op afspelen om te hervatten';

  @override
  String get listeningForAudio => 'Luisteren naar audio...';

  @override
  String get preparingAudioCapture => 'Audio-opname voorbereiden';

  @override
  String get clickToBeginRecording => 'Klik om opname te starten';

  @override
  String get translated => 'vertaald';

  @override
  String get liveTranscript => 'Live transcriptie';

  @override
  String segmentsSingular(String count) {
    return '$count segment';
  }

  @override
  String segmentsPlural(String count) {
    return '$count segmenten';
  }

  @override
  String get startRecordingToSeeTranscript => 'Start opname om live transcriptie te zien';

  @override
  String get paused => 'Gepauzeerd';

  @override
  String get initializing => 'Initialiseren...';

  @override
  String get recording => 'Opnemen';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'Microfoon gewijzigd. Hervatten over ${countdown}s';
  }

  @override
  String get clickPlayToResumeOrStop => 'Klik op afspelen om te hervatten of stop om te voltooien';

  @override
  String get settingUpSystemAudioCapture => 'Systeemaudio-opname instellen';

  @override
  String get capturingAudioAndGeneratingTranscript => 'Audio vastleggen en transcriptie genereren';

  @override
  String get clickToBeginRecordingSystemAudio => 'Klik om systeemaudio-opname te starten';

  @override
  String get you => 'Jij';

  @override
  String speakerWithId(String speakerId) {
    return 'Spreker $speakerId';
  }

  @override
  String get translatedByOmi => 'vertaald door omi';

  @override
  String get backToConversations => 'Terug naar gesprekken';

  @override
  String get systemAudio => 'Systeem';

  @override
  String get mic => 'Microfoon';

  @override
  String audioInputSetTo(String deviceName) {
    return 'Audio-ingang ingesteld op $deviceName';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'Fout bij wisselen van audio-apparaat: $error';
  }

  @override
  String get selectAudioInput => 'Selecteer audio-ingang';

  @override
  String get loadingDevices => 'Apparaten laden...';

  @override
  String get settingsHeader => 'INSTELLINGEN';

  @override
  String get plansAndBilling => 'Plannen & Facturering';

  @override
  String get calendarIntegration => 'Agenda-integratie';

  @override
  String get dailySummary => 'Dagelijkse samenvatting';

  @override
  String get developer => 'Ontwikkelaar';

  @override
  String get about => 'Over';

  @override
  String get selectTime => 'Tijd selecteren';

  @override
  String get accountGroup => 'Account';

  @override
  String get signOutQuestion => 'Uitloggen?';

  @override
  String get signOutConfirmation => 'Weet je zeker dat je wilt uitloggen?';

  @override
  String get customVocabularyHeader => 'AANGEPASTE WOORDENSCHAT';

  @override
  String get addWordsDescription => 'Voeg woorden toe die Omi moet herkennen tijdens transcriptie.';

  @override
  String get enterWordsHint => 'Voer woorden in (kommagescheiden)';

  @override
  String get dailySummaryHeader => 'DAGELIJKSE SAMENVATTING';

  @override
  String get dailySummaryTitle => 'Dagelijkse Samenvatting';

  @override
  String get dailySummaryDescription =>
      'Ontvang een gepersonaliseerde samenvatting van je dagelijkse gesprekken als melding.';

  @override
  String get deliveryTime => 'Bezorgtijd';

  @override
  String get deliveryTimeDescription => 'Wanneer je dagelijkse samenvatting ontvangen';

  @override
  String get subscription => 'Abonnement';

  @override
  String get viewPlansAndUsage => 'Bekijk Plannen & Gebruik';

  @override
  String get viewPlansDescription => 'Beheer je abonnement en bekijk gebruiksstatistieken';

  @override
  String get addOrChangePaymentMethod => 'Voeg toe of wijzig je betaalmethode';

  @override
  String get displayOptions => 'Weergaveopties';

  @override
  String get showMeetingsInMenuBar => 'Vergaderingen weergeven in menubalk';

  @override
  String get displayUpcomingMeetingsDescription => 'Aankomende vergaderingen weergeven in menubalk';

  @override
  String get showEventsWithoutParticipants => 'Evenementen zonder deelnemers weergeven';

  @override
  String get includePersonalEventsDescription => 'Persoonlijke evenementen zonder deelnemers opnemen';

  @override
  String get upcomingMeetings => 'Aankomende vergaderingen';

  @override
  String get checkingNext7Days => 'Controleren van de komende 7 dagen';

  @override
  String get shortcuts => 'Sneltoetsen';

  @override
  String get shortcutChangeInstruction => 'Klik op een sneltoets om deze te wijzigen. Druk op Escape om te annuleren.';

  @override
  String get configurePersonaDescription => 'Configureer je AI-persona';

  @override
  String get configureSTTProvider => 'STT-provider configureren';

  @override
  String get setConversationEndDescription => 'Instellen wanneer gesprekken automatisch eindigen';

  @override
  String get importDataDescription => 'Gegevens importeren uit andere bronnen';

  @override
  String get exportConversationsDescription => 'Gesprekken exporteren naar JSON';

  @override
  String get exportingConversations => 'Gesprekken exporteren...';

  @override
  String get clearNodesDescription => 'Wis alle knooppunten en verbindingen';

  @override
  String get deleteKnowledgeGraphQuestion => 'Kennisgrafiek verwijderen?';

  @override
  String get deleteKnowledgeGraphWarning =>
      'Dit verwijdert alle afgeleide kennisgrafiekgegevens. Uw originele herinneringen blijven veilig.';

  @override
  String get connectOmiWithAI => 'Verbind Omi met AI-assistenten';

  @override
  String get noAPIKeys => 'Geen API-sleutels. Maak er een aan om te beginnen.';

  @override
  String get autoCreateWhenDetected => 'Automatisch aanmaken wanneer naam wordt gedetecteerd';

  @override
  String get trackPersonalGoals => 'Persoonlijke doelen volgen op de homepage';

  @override
  String get dailyReflectionDescription =>
      'Ontvang om 21:00 een herinnering om te reflecteren op je dag en je gedachten vast te leggen.';

  @override
  String get endpointURL => 'Eindpunt-URL';

  @override
  String get links => 'Links';

  @override
  String get discordMemberCount => 'Meer dan 8000 leden op Discord';

  @override
  String get userInformation => 'Gebruikersinformatie';

  @override
  String get capabilities => 'Mogelijkheden';

  @override
  String get previewScreenshots => 'Voorbeeld schermafbeeldingen';

  @override
  String get holdOnPreparingForm => 'Even geduld, we bereiden het formulier voor u voor';

  @override
  String get bySubmittingYouAgreeToOmi => 'Door in te dienen, gaat u akkoord met Omi ';

  @override
  String get termsAndPrivacyPolicy => 'Voorwaarden en Privacybeleid';

  @override
  String get helpsDiagnoseIssuesAutoDeletes =>
      'Helpt bij het diagnosticeren van problemen. Wordt na 3 dagen automatisch verwijderd.';

  @override
  String get manageYourApp => 'Beheer uw app';

  @override
  String get updatingYourApp => 'Uw app bijwerken';

  @override
  String get fetchingYourAppDetails => 'App-details ophalen';

  @override
  String get updateAppQuestion => 'App bijwerken?';

  @override
  String get updateAppConfirmation =>
      'Weet u zeker dat u uw app wilt bijwerken? De wijzigingen worden doorgevoerd na beoordeling door ons team.';

  @override
  String get updateApp => 'App bijwerken';

  @override
  String get createAndSubmitNewApp => 'Maak en dien een nieuwe app in';

  @override
  String appsCount(String count) {
    return 'Apps ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'Privé-apps ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'Openbare apps ($count)';
  }

  @override
  String get newVersionAvailable => 'Nieuwe versie beschikbaar  🎉';

  @override
  String get no => 'Nee';

  @override
  String get subscriptionCancelledSuccessfully =>
      'Abonnement succesvol geannuleerd. Het blijft actief tot het einde van de huidige factureringsperiode.';

  @override
  String get failedToCancelSubscription => 'Annuleren van abonnement mislukt. Probeer het opnieuw.';

  @override
  String get invalidPaymentUrl => 'Ongeldige betalings-URL';

  @override
  String get permissionsAndTriggers => 'Machtigingen & triggers';

  @override
  String get chatFeatures => 'Chat-functies';

  @override
  String get uninstall => 'Verwijderen';

  @override
  String get installs => 'INSTALLATIES';

  @override
  String get priceLabel => 'PRIJS';

  @override
  String get updatedLabel => 'BIJGEWERKT';

  @override
  String get createdLabel => 'AANGEMAAKT';

  @override
  String get featuredLabel => 'UITGELICHT';

  @override
  String get cancelSubscriptionQuestion => 'Abonnement annuleren?';

  @override
  String get cancelSubscriptionConfirmation =>
      'Weet u zeker dat u uw abonnement wilt annuleren? U behoudt toegang tot het einde van uw huidige factureringsperiode.';

  @override
  String get cancelSubscriptionButton => 'Abonnement annuleren';

  @override
  String get cancelling => 'Annuleren...';

  @override
  String get betaTesterMessage =>
      'U bent een bètatester voor deze app. Deze is nog niet openbaar. Deze wordt openbaar na goedkeuring.';

  @override
  String get appUnderReviewMessage =>
      'Uw app wordt beoordeeld en is alleen voor u zichtbaar. Deze wordt openbaar na goedkeuring.';

  @override
  String get appRejectedMessage => 'Uw app is afgewezen. Werk de gegevens bij en dien opnieuw in ter beoordeling.';

  @override
  String get invalidIntegrationUrl => 'Ongeldige integratie-URL';

  @override
  String get tapToComplete => 'Tik om te voltooien';

  @override
  String get invalidSetupInstructionsUrl => 'Ongeldige URL voor installatie-instructies';

  @override
  String get pushToTalk => 'Druk om te praten';

  @override
  String get summaryPrompt => 'Samenvattingsprompt';

  @override
  String get pleaseSelectARating => 'Selecteer een beoordeling';

  @override
  String get reviewAddedSuccessfully => 'Recensie succesvol toegevoegd 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'Recensie succesvol bijgewerkt 🚀';

  @override
  String get failedToSubmitReview => 'Verzenden van recensie mislukt. Probeer het opnieuw.';

  @override
  String get addYourReview => 'Voeg uw beoordeling toe';

  @override
  String get editYourReview => 'Bewerk uw beoordeling';

  @override
  String get writeAReviewOptional => 'Schrijf een beoordeling (optioneel)';

  @override
  String get submitReview => 'Beoordeling verzenden';

  @override
  String get updateReview => 'Beoordeling bijwerken';

  @override
  String get yourReview => 'Uw beoordeling';

  @override
  String get anonymousUser => 'Anonieme gebruiker';

  @override
  String get issueActivatingApp => 'Er is een probleem opgetreden bij het activeren van deze app. Probeer het opnieuw.';

  @override
  String get dataAccessNoticeDescription =>
      'Deze app krijgt toegang tot je gegevens. Omi AI is niet verantwoordelijk voor hoe je gegevens worden gebruikt, gewijzigd of verwijderd door deze app';

  @override
  String get copyUrl => 'URL kopiëren';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => 'Ma';

  @override
  String get weekdayTue => 'Di';

  @override
  String get weekdayWed => 'Wo';

  @override
  String get weekdayThu => 'Do';

  @override
  String get weekdayFri => 'Vr';

  @override
  String get weekdaySat => 'Za';

  @override
  String get weekdaySun => 'Zo';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return '$serviceName-integratie binnenkort beschikbaar';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'Al geëxporteerd naar $platform';
  }

  @override
  String get anotherPlatform => 'een ander platform';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'Authenticeer a.u.b. met $serviceName in Instellingen > Taakintegraties';
  }

  @override
  String addingToService(String serviceName) {
    return 'Toevoegen aan $serviceName...';
  }

  @override
  String addedToService(String serviceName) {
    return 'Toegevoegd aan $serviceName';
  }

  @override
  String failedToAddToService(String serviceName) {
    return 'Toevoegen aan $serviceName mislukt';
  }

  @override
  String get permissionDeniedForAppleReminders => 'Toestemming geweigerd voor Apple Herinneringen';

  @override
  String failedToCreateApiKey(String error) {
    return 'Kan provider API-sleutel niet maken: $error';
  }

  @override
  String get createAKey => 'Sleutel maken';

  @override
  String get apiKeyRevokedSuccessfully => 'API-sleutel succesvol ingetrokken';

  @override
  String failedToRevokeApiKey(String error) {
    return 'Kan API-sleutel niet intrekken: $error';
  }

  @override
  String get omiApiKeys => 'Omi API-sleutels';

  @override
  String get apiKeysDescription =>
      'API-sleutels worden gebruikt voor authenticatie wanneer uw app communiceert met de OMI-server. Ze stellen uw applicatie in staat om herinneringen te maken en veilig toegang te krijgen tot andere OMI-services.';

  @override
  String get aboutOmiApiKeys => 'Over Omi API-sleutels';

  @override
  String get yourNewKey => 'Uw nieuwe sleutel:';

  @override
  String get copyToClipboard => 'Kopiëren naar klembord';

  @override
  String get pleaseCopyKeyNow => 'Kopieer het nu en schrijf het ergens veilig op. ';

  @override
  String get willNotSeeAgain => 'U zult het niet meer kunnen zien.';

  @override
  String get revokeKey => 'Sleutel intrekken';

  @override
  String get revokeApiKeyQuestion => 'API-sleutel intrekken?';

  @override
  String get revokeApiKeyWarning =>
      'Deze actie kan niet ongedaan worden gemaakt. Applicaties die deze sleutel gebruiken, hebben geen toegang meer tot de API.';

  @override
  String get revoke => 'Intrekken';

  @override
  String get whatWouldYouLikeToCreate => 'Wat wilt u maken?';

  @override
  String get createAnApp => 'Een app maken';

  @override
  String get createAndShareYourApp => 'Maak en deel uw app';

  @override
  String get createMyClone => 'Mijn kloon maken';

  @override
  String get createYourDigitalClone => 'Maak uw digitale kloon';

  @override
  String get itemApp => 'App';

  @override
  String get itemPersona => 'Persona';

  @override
  String keepItemPublic(String item) {
    return '$item openbaar houden';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return '$item openbaar maken?';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return '$item privé maken?';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'Als u $item openbaar maakt, kan het door iedereen worden gebruikt';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'Als u $item nu privé maakt, werkt het voor niemand meer en is het alleen voor u zichtbaar';
  }

  @override
  String get manageApp => 'App beheren';

  @override
  String get updatePersonaDetails => 'Persona-details bijwerken';

  @override
  String deleteItemTitle(String item) {
    return '$item verwijderen';
  }

  @override
  String deleteItemQuestion(String item) {
    return '$item verwijderen?';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'Weet u zeker dat u deze $item wilt verwijderen? Deze actie kan niet ongedaan worden gemaakt.';
  }

  @override
  String get revokeKeyQuestion => 'Sleutel intrekken?';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'Weet u zeker dat u de sleutel \"$keyName\" wilt intrekken? Deze actie kan niet ongedaan worden gemaakt.';
  }

  @override
  String get createNewKey => 'Nieuwe sleutel maken';

  @override
  String get keyNameHint => 'bijv. Claude Desktop';

  @override
  String get pleaseEnterAName => 'Voer een naam in.';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'Sleutel maken mislukt: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'Sleutel maken mislukt. Probeer het opnieuw.';

  @override
  String get keyCreated => 'Sleutel aangemaakt';

  @override
  String get keyCreatedMessage => 'Uw nieuwe sleutel is aangemaakt. Kopieer deze nu. U kunt deze niet meer zien.';

  @override
  String get keyWord => 'Sleutel';

  @override
  String get externalAppAccess => 'Externe app-toegang';

  @override
  String get externalAppAccessDescription =>
      'De volgende geïnstalleerde apps hebben externe integraties en kunnen toegang krijgen tot uw gegevens, zoals gesprekken en herinneringen.';

  @override
  String get noExternalAppsHaveAccess => 'Geen externe apps hebben toegang tot uw gegevens.';

  @override
  String get maximumSecurityE2ee => 'Maximale beveiliging (E2EE)';

  @override
  String get e2eeDescription =>
      'End-to-end-encryptie is de gouden standaard voor privacy. Wanneer ingeschakeld, worden uw gegevens op uw apparaat versleuteld voordat ze naar onze servers worden verzonden. Dit betekent dat niemand, zelfs Omi niet, toegang heeft tot uw inhoud.';

  @override
  String get importantTradeoffs => 'Belangrijke afwegingen:';

  @override
  String get e2eeTradeoff1 => '• Sommige functies zoals externe app-integraties kunnen worden uitgeschakeld.';

  @override
  String get e2eeTradeoff2 => '• Als u uw wachtwoord verliest, kunnen uw gegevens niet worden hersteld.';

  @override
  String get featureComingSoon => 'Deze functie komt binnenkort!';

  @override
  String get migrationInProgressMessage =>
      'Migratie bezig. U kunt het beveiligingsniveau niet wijzigen totdat deze is voltooid.';

  @override
  String get migrationFailed => 'Migratie mislukt';

  @override
  String migratingFromTo(String source, String target) {
    return 'Migreren van $source naar $target';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total objecten';
  }

  @override
  String get secureEncryption => 'Veilige versleuteling';

  @override
  String get secureEncryptionDescription =>
      'Uw gegevens worden versleuteld met een voor u unieke sleutel op onze servers, gehost op Google Cloud. Dit betekent dat uw ruwe inhoud ontoegankelijk is voor iedereen, inclusief Omi-medewerkers of Google, rechtstreeks vanuit de database.';

  @override
  String get endToEndEncryption => 'End-to-end-encryptie';

  @override
  String get e2eeCardDescription =>
      'Schakel in voor maximale beveiliging waarbij alleen u toegang heeft tot uw gegevens. Tik om meer te weten te komen.';

  @override
  String get dataAlwaysEncrypted =>
      'Ongeacht het niveau zijn uw gegevens altijd versleuteld in rust en tijdens overdracht.';

  @override
  String get readOnlyScope => 'Alleen lezen';

  @override
  String get fullAccessScope => 'Volledige toegang';

  @override
  String get readScope => 'Lezen';

  @override
  String get writeScope => 'Schrijven';

  @override
  String get apiKeyCreated => 'API-sleutel aangemaakt!';

  @override
  String get saveKeyWarning => 'Sla deze sleutel nu op! U kunt hem niet meer zien.';

  @override
  String get yourApiKey => 'UW API-SLEUTEL';

  @override
  String get tapToCopy => 'Tik om te kopiëren';

  @override
  String get copyKey => 'Sleutel kopiëren';

  @override
  String get createApiKey => 'API-sleutel maken';

  @override
  String get accessDataProgrammatically => 'Toegang tot uw gegevens via programmering';

  @override
  String get keyNameLabel => 'SLEUTELNAAM';

  @override
  String get keyNamePlaceholder => 'bijv., Mijn app-integratie';

  @override
  String get permissionsLabel => 'MACHTIGINGEN';

  @override
  String get permissionsInfoNote => 'R = Lezen, W = Schrijven. Standaard alleen lezen als niets is geselecteerd.';

  @override
  String get developerApi => 'Ontwikkelaar-API';

  @override
  String get createAKeyToGetStarted => 'Maak een sleutel om te beginnen';

  @override
  String errorWithMessage(String error) {
    return 'Fout: $error';
  }

  @override
  String get omiTraining => 'Omi Training';

  @override
  String get trainingDataProgram => 'Trainingsdataprogramma';

  @override
  String get getOmiUnlimitedFree =>
      'Krijg Omi Unlimited gratis door uw gegevens bij te dragen voor het trainen van AI-modellen.';

  @override
  String get trainingDataBullets =>
      '• Uw gegevens helpen AI-modellen te verbeteren\n• Alleen niet-gevoelige gegevens worden gedeeld\n• Volledig transparant proces';

  @override
  String get learnMoreAtOmiTraining => 'Meer informatie op omi.me/training';

  @override
  String get agreeToContributeData => 'Ik begrijp en ga akkoord met het bijdragen van mijn gegevens voor AI-training';

  @override
  String get submitRequest => 'Verzoek indienen';

  @override
  String get thankYouRequestUnderReview =>
      'Bedankt! Uw verzoek wordt beoordeeld. We laten u weten wanneer het is goedgekeurd.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'Uw plan blijft actief tot $date. Daarna verliest u de toegang tot uw onbeperkte functies. Weet u het zeker?';
  }

  @override
  String get confirmCancellation => 'Annulering bevestigen';

  @override
  String get keepMyPlan => 'Mijn plan behouden';

  @override
  String get subscriptionSetToCancel => 'Uw abonnement wordt aan het einde van de periode geannuleerd.';

  @override
  String get switchedToOnDevice => 'Overgeschakeld naar transcriptie op apparaat';

  @override
  String get couldNotSwitchToFreePlan => 'Kon niet overschakelen naar gratis abonnement. Probeer het opnieuw.';

  @override
  String get couldNotLoadPlans => 'Kon beschikbare abonnementen niet laden. Probeer het opnieuw.';

  @override
  String get selectedPlanNotAvailable => 'Geselecteerd abonnement is niet beschikbaar. Probeer het opnieuw.';

  @override
  String get upgradeToAnnualPlan => 'Upgraden naar jaarabonnement';

  @override
  String get importantBillingInfo => 'Belangrijke factureringsinformatie:';

  @override
  String get monthlyPlanContinues => 'Uw huidige maandabonnement loopt door tot het einde van uw factureringsperiode';

  @override
  String get paymentMethodCharged =>
      'Uw bestaande betaalmethode wordt automatisch belast wanneer uw maandabonnement eindigt';

  @override
  String get annualSubscriptionStarts => 'Uw 12-maanden jaarabonnement start automatisch na de betaling';

  @override
  String get thirteenMonthsCoverage => 'U krijgt in totaal 13 maanden dekking (huidige maand + 12 maanden jaarlijks)';

  @override
  String get confirmUpgrade => 'Upgrade bevestigen';

  @override
  String get confirmPlanChange => 'Planwijziging bevestigen';

  @override
  String get confirmAndProceed => 'Bevestigen en doorgaan';

  @override
  String get upgradeScheduled => 'Upgrade gepland';

  @override
  String get changePlan => 'Plan wijzigen';

  @override
  String get upgradeAlreadyScheduled => 'Uw upgrade naar het jaarabonnement is al gepland';

  @override
  String get youAreOnUnlimitedPlan => 'U bent op het Unlimited-abonnement.';

  @override
  String get yourOmiUnleashed => 'Uw Omi, ontketend. Ga unlimited voor eindeloze mogelijkheden.';

  @override
  String planEndedOn(String date) {
    return 'Uw plan eindigde op $date.\\nAbonneer nu opnieuw - u wordt direct belast voor een nieuwe factureringsperiode.';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'Uw plan wordt geannuleerd op $date.\\nAbonneer nu opnieuw om uw voordelen te behouden - geen kosten tot $date.';
  }

  @override
  String get annualPlanStartsAutomatically => 'Uw jaarabonnement start automatisch wanneer uw maandabonnement eindigt.';

  @override
  String planRenewsOn(String date) {
    return 'Uw plan wordt verlengd op $date.';
  }

  @override
  String get unlimitedConversations => 'Onbeperkte gesprekken';

  @override
  String get askOmiAnything => 'Vraag Omi alles over uw leven';

  @override
  String get unlockOmiInfiniteMemory => 'Ontgrendel Omi\'s oneindige geheugen';

  @override
  String get youreOnAnnualPlan => 'U bent op het jaarabonnement';

  @override
  String get alreadyBestValuePlan => 'U heeft al het beste abonnement qua waarde. Geen wijzigingen nodig.';

  @override
  String get unableToLoadPlans => 'Kan abonnementen niet laden';

  @override
  String get checkConnectionTryAgain => 'Controleer uw verbinding en probeer het opnieuw';

  @override
  String get useFreePlan => 'Gratis abonnement gebruiken';

  @override
  String get continueText => 'Doorgaan';

  @override
  String get resubscribe => 'Opnieuw abonneren';

  @override
  String get couldNotOpenPaymentSettings => 'Kon betalingsinstellingen niet openen. Probeer het opnieuw.';

  @override
  String get managePaymentMethod => 'Betalingsmethode beheren';

  @override
  String get cancelSubscription => 'Abonnement opzeggen';

  @override
  String endsOnDate(String date) {
    return 'Eindigt op $date';
  }

  @override
  String get active => 'Actief';

  @override
  String get freePlan => 'Gratis abonnement';

  @override
  String get configure => 'Configureren';

  @override
  String get privacyInformation => 'Privacyinformatie';

  @override
  String get yourPrivacyMattersToUs => 'Uw privacy is belangrijk voor ons';

  @override
  String get privacyIntroText =>
      'Bij Omi nemen we uw privacy zeer serieus. We willen transparant zijn over de gegevens die we verzamelen en hoe we deze gebruiken. Dit moet u weten:';

  @override
  String get whatWeTrack => 'Wat we bijhouden';

  @override
  String get anonymityAndPrivacy => 'Anonimiteit en privacy';

  @override
  String get optInAndOptOutOptions => 'Opt-in en opt-out opties';

  @override
  String get ourCommitment => 'Onze toezegging';

  @override
  String get commitmentText =>
      'We zijn toegewijd om de verzamelde gegevens alleen te gebruiken om Omi een beter product voor u te maken. Uw privacy en vertrouwen zijn van het grootste belang voor ons.';

  @override
  String get thankYouText =>
      'Bedankt dat u een gewaardeerde gebruiker van Omi bent. Als u vragen of zorgen heeft, neem dan gerust contact met ons op via team@basedhardware.com.';

  @override
  String get wifiSyncSettings => 'WiFi-synchronisatie-instellingen';

  @override
  String get enterHotspotCredentials => 'Voer de hotspot-inloggegevens van uw telefoon in';

  @override
  String get wifiSyncUsesHotspot =>
      'WiFi-sync gebruikt uw telefoon als hotspot. Vind de naam en het wachtwoord in Instellingen > Persoonlijke hotspot.';

  @override
  String get hotspotNameSsid => 'Hotspotnaam (SSID)';

  @override
  String get exampleIphoneHotspot => 'bijv. iPhone Hotspot';

  @override
  String get password => 'Wachtwoord';

  @override
  String get enterHotspotPassword => 'Voer hotspot-wachtwoord in';

  @override
  String get saveCredentials => 'Inloggegevens opslaan';

  @override
  String get clearCredentials => 'Inloggegevens wissen';

  @override
  String get pleaseEnterHotspotName => 'Voer een hotspotnaam in';

  @override
  String get wifiCredentialsSaved => 'WiFi-inloggegevens opgeslagen';

  @override
  String get wifiCredentialsCleared => 'WiFi-inloggegevens gewist';

  @override
  String summaryGeneratedForDate(String date) {
    return 'Samenvatting gegenereerd voor $date';
  }

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'Kon samenvatting niet genereren. Zorg ervoor dat u gesprekken heeft voor die dag.';

  @override
  String get summaryNotFound => 'Samenvatting niet gevonden';

  @override
  String get yourDaysJourney => 'Uw dagreis';

  @override
  String get highlights => 'Hoogtepunten';

  @override
  String get unresolvedQuestions => 'Onopgeloste vragen';

  @override
  String get decisions => 'Beslissingen';

  @override
  String get learnings => 'Inzichten';

  @override
  String get autoDeletesAfterThreeDays => 'Automatisch verwijderd na 3 dagen.';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'Kennisgrafiek succesvol verwijderd';

  @override
  String get exportStartedMayTakeFewSeconds => 'Export gestart. Dit kan enkele seconden duren...';

  @override
  String get knowledgeGraphDeleteDescription =>
      'Dit verwijdert alle afgeleide kennisgraafgegevens (knooppunten en verbindingen). Uw originele herinneringen blijven veilig. De grafiek wordt in de loop van de tijd of bij het volgende verzoek opnieuw opgebouwd.';

  @override
  String get configureDailySummaryDigest => 'Configureer je dagelijkse taaknoverzicht';

  @override
  String accessesDataTypes(String dataTypes) {
    return 'Toegang tot $dataTypes';
  }

  @override
  String triggeredByType(String triggerType) {
    return 'getriggerd door $triggerType';
  }

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription en is $triggerDescription.';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return 'Wordt $triggerDescription geactiveerd.';
  }

  @override
  String get noSpecificDataAccessConfigured => 'Geen specifieke gegevenstoegang geconfigureerd.';

  @override
  String get basicPlanDescription => '1.200 premium minuten + onbeperkt op apparaat';

  @override
  String get minutes => 'minuten';

  @override
  String get omiHas => 'Omi heeft:';

  @override
  String get premiumMinutesUsed => 'Premium minuten gebruikt.';

  @override
  String get setupOnDevice => 'Instellen op apparaat';

  @override
  String get forUnlimitedFreeTranscription => 'voor onbeperkte gratis transcriptie.';

  @override
  String premiumMinsLeft(int count) {
    return '$count premium minuten over.';
  }

  @override
  String get alwaysAvailable => 'altijd beschikbaar.';

  @override
  String get importHistory => 'Importgeschiedenis';

  @override
  String get noImportsYet => 'Nog geen imports';

  @override
  String get selectZipFileToImport => 'Selecteer het .zip-bestand om te importeren!';

  @override
  String get otherDevicesComingSoon => 'Andere apparaten binnenkort';

  @override
  String get deleteAllLimitlessConversations => 'Alle Limitless-gesprekken verwijderen?';

  @override
  String get deleteAllLimitlessWarning =>
      'Dit verwijdert permanent alle gesprekken die zijn geïmporteerd uit Limitless. Deze actie kan niet ongedaan worden gemaakt.';

  @override
  String deletedLimitlessConversations(int count) {
    return '$count Limitless-gesprekken verwijderd';
  }

  @override
  String get failedToDeleteConversations => 'Gesprekken verwijderen mislukt';

  @override
  String get deleteImportedData => 'Geïmporteerde gegevens verwijderen';

  @override
  String get statusPending => 'In behandeling';

  @override
  String get statusProcessing => 'Verwerken';

  @override
  String get statusCompleted => 'Voltooid';

  @override
  String get statusFailed => 'Mislukt';

  @override
  String nConversations(int count) {
    return '$count gesprekken';
  }

  @override
  String get pleaseEnterName => 'Voer een naam in';

  @override
  String get nameMustBeBetweenCharacters => 'Naam moet tussen 2 en 40 tekens zijn';

  @override
  String get deleteSampleQuestion => 'Voorbeeld verwijderen?';

  @override
  String deleteSampleConfirmation(String name) {
    return 'Weet u zeker dat u het voorbeeld van $name wilt verwijderen?';
  }

  @override
  String get confirmDeletion => 'Verwijdering bevestigen';

  @override
  String deletePersonConfirmation(String name) {
    return 'Weet u zeker dat u $name wilt verwijderen? Dit verwijdert ook alle bijbehorende spraaksamples.';
  }

  @override
  String get howItWorksTitle => 'Hoe werkt het?';

  @override
  String get howPeopleWorks =>
      'Zodra een persoon is aangemaakt, kun je naar een gesprekstranscriptie gaan en de bijbehorende segmenten toewijzen, zo kan Omi ook hun spraak herkennen!';

  @override
  String get tapToDelete => 'Tik om te verwijderen';

  @override
  String get newTag => 'NIEUW';

  @override
  String get needHelpChatWithUs => 'Hulp nodig? Chat met ons';

  @override
  String get localStorageEnabled => 'Lokale opslag ingeschakeld';

  @override
  String get localStorageDisabled => 'Lokale opslag uitgeschakeld';

  @override
  String failedToUpdateSettings(String error) {
    return 'Instellingen bijwerken mislukt: $error';
  }

  @override
  String get privacyNotice => 'Privacyverklaring';

  @override
  String get recordingsMayCaptureOthers =>
      'Opnames kunnen de stemmen van anderen vastleggen. Zorg ervoor dat u toestemming hebt van alle deelnemers voordat u inschakelt.';

  @override
  String get enable => 'Inschakelen';

  @override
  String get storeAudioOnPhone => 'Audio opslaan op telefoon';

  @override
  String get on => 'Aan';

  @override
  String get storeAudioDescription =>
      'Bewaar alle audio-opnames lokaal op uw telefoon. Wanneer uitgeschakeld, worden alleen mislukte uploads bewaard om opslagruimte te besparen.';

  @override
  String get enableLocalStorage => 'Lokale opslag inschakelen';

  @override
  String get cloudStorageEnabled => 'Cloudopslag ingeschakeld';

  @override
  String get cloudStorageDisabled => 'Cloudopslag uitgeschakeld';

  @override
  String get enableCloudStorage => 'Cloudopslag inschakelen';

  @override
  String get storeAudioOnCloud => 'Audio opslaan in de cloud';

  @override
  String get cloudStorageDialogMessage =>
      'Uw realtime opnames worden opgeslagen in privé cloudopslag terwijl u spreekt.';

  @override
  String get storeAudioCloudDescription =>
      'Sla uw realtime opnames op in privé cloudopslag terwijl u spreekt. Audio wordt veilig vastgelegd en opgeslagen in realtime.';

  @override
  String get downloadingFirmware => 'Firmware downloaden';

  @override
  String get installingFirmware => 'Firmware installeren';

  @override
  String get firmwareUpdateWarning =>
      'Sluit de app niet en schakel het apparaat niet uit. Dit kan uw apparaat beschadigen.';

  @override
  String get firmwareUpdated => 'Firmware bijgewerkt';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'Start uw $deviceName opnieuw op om de update te voltooien.';
  }

  @override
  String get yourDeviceIsUpToDate => 'Uw apparaat is up-to-date';

  @override
  String get currentVersion => 'Huidige versie';

  @override
  String get latestVersion => 'Nieuwste versie';

  @override
  String get whatsNew => 'Wat is nieuw';

  @override
  String get installUpdate => 'Update installeren';

  @override
  String get updateNow => 'Nu bijwerken';

  @override
  String get updateGuide => 'Update-handleiding';

  @override
  String get checkingForUpdates => 'Controleren op updates';

  @override
  String get checkingFirmwareVersion => 'Firmware-versie controleren...';

  @override
  String get firmwareUpdate => 'Firmware-update';

  @override
  String get payments => 'Betalingen';

  @override
  String get connectPaymentMethodInfo =>
      'Verbind hieronder een betaalmethode om uitbetalingen voor uw apps te ontvangen.';

  @override
  String get selectedPaymentMethod => 'Geselecteerde betaalmethode';

  @override
  String get availablePaymentMethods => 'Beschikbare betaalmethoden';

  @override
  String get activeStatus => 'Actief';

  @override
  String get connectedStatus => 'Verbonden';

  @override
  String get notConnectedStatus => 'Niet verbonden';

  @override
  String get setActive => 'Instellen als actief';

  @override
  String get getPaidThroughStripe => 'Ontvang betalingen voor uw app-verkopen via Stripe';

  @override
  String get monthlyPayouts => 'Maandelijkse uitbetalingen';

  @override
  String get monthlyPayoutsDescription =>
      'Ontvang maandelijkse betalingen rechtstreeks op uw rekening wanneer u \$10 aan inkomsten bereikt';

  @override
  String get secureAndReliable => 'Veilig en betrouwbaar';

  @override
  String get stripeSecureDescription => 'Stripe zorgt voor veilige en tijdige overdrachten van uw app-inkomsten';

  @override
  String get selectYourCountry => 'Selecteer uw land';

  @override
  String get countrySelectionPermanent => 'Uw landselectie is permanent en kan later niet worden gewijzigd.';

  @override
  String get byClickingConnectNow => 'Door op \"Nu verbinden\" te klikken gaat u akkoord met';

  @override
  String get stripeConnectedAccountAgreement => 'Stripe Connected Account-overeenkomst';

  @override
  String get errorConnectingToStripe => 'Fout bij verbinden met Stripe! Probeer het later opnieuw.';

  @override
  String get connectingYourStripeAccount => 'Uw Stripe-account verbinden';

  @override
  String get stripeOnboardingInstructions =>
      'Voltooi het Stripe-onboardingproces in uw browser. Deze pagina wordt automatisch bijgewerkt zodra het proces is voltooid.';

  @override
  String get failedTryAgain => 'Mislukt? Probeer opnieuw';

  @override
  String get illDoItLater => 'Ik doe het later';

  @override
  String get successfullyConnected => 'Succesvol verbonden!';

  @override
  String get stripeReadyForPayments =>
      'Uw Stripe-account is nu klaar om betalingen te ontvangen. U kunt direct beginnen met verdienen aan uw app-verkopen.';

  @override
  String get updateStripeDetails => 'Stripe-gegevens bijwerken';

  @override
  String get errorUpdatingStripeDetails => 'Fout bij het bijwerken van Stripe-gegevens! Probeer het later opnieuw.';

  @override
  String get updatePayPal => 'PayPal bijwerken';

  @override
  String get setUpPayPal => 'PayPal instellen';

  @override
  String get updatePayPalAccountDetails => 'Werk uw PayPal-accountgegevens bij';

  @override
  String get connectPayPalToReceivePayments => 'Verbind uw PayPal-account om betalingen voor uw apps te ontvangen';

  @override
  String get paypalEmail => 'PayPal-e-mail';

  @override
  String get paypalMeLink => 'PayPal.me-link';

  @override
  String get stripeRecommendation =>
      'Als Stripe beschikbaar is in uw land, raden we het ten zeerste aan voor snellere en gemakkelijkere uitbetalingen.';

  @override
  String get updatePayPalDetails => 'PayPal-gegevens bijwerken';

  @override
  String get savePayPalDetails => 'PayPal-gegevens opslaan';

  @override
  String get pleaseEnterPayPalEmail => 'Voer uw PayPal-e-mailadres in';

  @override
  String get pleaseEnterPayPalMeLink => 'Voer uw PayPal.me-link in';

  @override
  String get doNotIncludeHttpInLink => 'Neem geen http, https of www op in de link';

  @override
  String get pleaseEnterValidPayPalMeLink => 'Voer een geldige PayPal.me-link in';

  @override
  String get pleaseEnterValidEmail => 'Voer een geldig e-mailadres in';

  @override
  String get syncingYourRecordings => 'Je opnames synchroniseren';

  @override
  String get syncYourRecordings => 'Synchroniseer je opnames';

  @override
  String get syncNow => 'Nu synchroniseren';

  @override
  String get error => 'Fout';

  @override
  String get speechSamples => 'Spraakvoorbeelden';

  @override
  String additionalSampleIndex(String index) {
    return 'Extra voorbeeld $index';
  }

  @override
  String durationSeconds(String seconds) {
    return 'Duur: $seconds seconden';
  }

  @override
  String get additionalSpeechSampleRemoved => 'Extra spraakvoorbeeld verwijderd';

  @override
  String get consentDataMessage =>
      'Door verder te gaan, worden alle gegevens die je deelt met deze app (inclusief je gesprekken, opnames en persoonlijke informatie) veilig opgeslagen op onze servers om je AI-aangedreven inzichten te bieden en alle app-functies mogelijk te maken.';

  @override
  String get tasksEmptyStateMessage =>
      'Taken uit je gesprekken verschijnen hier.\nTik op + om er handmatig een te maken.';

  @override
  String get clearChatAction => 'Chat wissen';

  @override
  String get enableApps => 'Apps inschakelen';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => 'toon meer ↓';

  @override
  String get showLess => 'toon minder ↑';

  @override
  String get loadingYourRecording => 'Uw opname laden...';

  @override
  String get photoDiscardedMessage => 'Deze foto is verwijderd omdat deze niet significant was.';

  @override
  String get analyzing => 'Analyseren...';

  @override
  String get searchCountries => 'Landen zoeken...';

  @override
  String get checkingAppleWatch => 'Apple Watch controleren...';

  @override
  String get installOmiOnAppleWatch => 'Installeer Omi op je\nApple Watch';

  @override
  String get installOmiOnAppleWatchDescription =>
      'Om je Apple Watch met Omi te gebruiken, moet je eerst de Omi-app op je horloge installeren.';

  @override
  String get openOmiOnAppleWatch => 'Open Omi op je\nApple Watch';

  @override
  String get openOmiOnAppleWatchDescription =>
      'De Omi-app is geïnstalleerd op je Apple Watch. Open deze en tik op Start om te beginnen.';

  @override
  String get openWatchApp => 'Watch-app openen';

  @override
  String get iveInstalledAndOpenedTheApp => 'Ik heb de app geïnstalleerd en geopend';

  @override
  String get unableToOpenWatchApp =>
      'Kan Apple Watch-app niet openen. Open handmatig de Watch-app op je Apple Watch en installeer Omi vanuit het gedeelte \"Beschikbare apps\".';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch succesvol verbonden!';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch nog steeds niet bereikbaar. Zorg ervoor dat de Omi-app geopend is op je horloge.';

  @override
  String errorCheckingConnection(String error) {
    return 'Fout bij controleren verbinding: $error';
  }

  @override
  String get muted => 'Gedempt';

  @override
  String get processNow => 'Nu verwerken';

  @override
  String get finishedConversation => 'Gesprek beëindigd?';

  @override
  String get stopRecordingConfirmation =>
      'Weet je zeker dat je de opname wilt stoppen en het gesprek nu wilt samenvatten?';

  @override
  String get conversationEndsManually => 'Het gesprek eindigt alleen handmatig.';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'Het gesprek wordt samengevat na $minutes minuut$suffix stilte.';
  }

  @override
  String get dontAskAgain => 'Niet opnieuw vragen';

  @override
  String get waitingForTranscriptOrPhotos => 'Wachten op transcriptie of foto\'s...';

  @override
  String get noSummaryYet => 'Nog geen samenvatting';

  @override
  String hints(String text) {
    return 'Tips: $text';
  }

  @override
  String get testConversationPrompt => 'Test een gespreks-prompt';

  @override
  String get prompt => 'Prompt';

  @override
  String get result => 'Resultaat:';

  @override
  String get compareTranscripts => 'Transcripties vergelijken';

  @override
  String get notHelpful => 'Niet nuttig';

  @override
  String get exportTasksWithOneTap => 'Exporteer taken met één tik!';

  @override
  String get inProgress => 'Bezig';

  @override
  String get photos => 'Foto\'s';

  @override
  String get rawData => 'Ruwe gegevens';

  @override
  String get content => 'Inhoud';

  @override
  String get noContentToDisplay => 'Geen inhoud om weer te geven';

  @override
  String get noSummary => 'Geen samenvatting';

  @override
  String get updateOmiFirmware => 'Omi-firmware bijwerken';

  @override
  String get anErrorOccurredTryAgain => 'Er is een fout opgetreden. Probeer het opnieuw.';

  @override
  String get welcomeBackSimple => 'Welkom terug';

  @override
  String get addVocabularyDescription => 'Voeg woorden toe die Omi moet herkennen tijdens transcriptie.';

  @override
  String get enterWordsCommaSeparated => 'Voer woorden in (gescheiden door komma)';

  @override
  String get whenToReceiveDailySummary => 'Wanneer je dagelijkse samenvatting ontvangen';

  @override
  String get checkingNextSevenDays => 'De komende 7 dagen controleren';

  @override
  String failedToDeleteError(String error) {
    return 'Verwijderen mislukt: $error';
  }

  @override
  String get developerApiKeys => 'Ontwikkelaar API-sleutels';

  @override
  String get noApiKeysCreateOne => 'Geen API-sleutels. Maak er een aan om te beginnen.';

  @override
  String get commandRequired => '⌘ vereist';

  @override
  String get spaceKey => 'Spatie';

  @override
  String loadMoreRemaining(String count) {
    return 'Meer laden ($count over)';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'Top $percentile% gebruiker';
  }

  @override
  String get wrappedMinutes => 'minuten';

  @override
  String get wrappedConversations => 'gesprekken';

  @override
  String get wrappedDaysActive => 'actieve dagen';

  @override
  String get wrappedYouTalkedAbout => 'Je sprak over';

  @override
  String get wrappedActionItems => 'Taken';

  @override
  String get wrappedTasksCreated => 'aangemaakte taken';

  @override
  String get wrappedCompleted => 'voltooid';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% voltooiingspercentage';
  }

  @override
  String get wrappedYourTopDays => 'Je beste dagen';

  @override
  String get wrappedBestMoments => 'Beste momenten';

  @override
  String get wrappedMyBuddies => 'Mijn vrienden';

  @override
  String get wrappedCouldntStopTalkingAbout => 'Kon niet stoppen met praten over';

  @override
  String get wrappedShow => 'SERIE';

  @override
  String get wrappedMovie => 'FILM';

  @override
  String get wrappedBook => 'BOEK';

  @override
  String get wrappedCelebrity => 'BEROEMDHEID';

  @override
  String get wrappedFood => 'ETEN';

  @override
  String get wrappedMovieRecs => 'Filmaanbevelingen voor vrienden';

  @override
  String get wrappedBiggest => 'Grootste';

  @override
  String get wrappedStruggle => 'Uitdaging';

  @override
  String get wrappedButYouPushedThrough => 'Maar je hebt het gehaald 💪';

  @override
  String get wrappedWin => 'Overwinning';

  @override
  String get wrappedYouDidIt => 'Je hebt het gedaan! 🎉';

  @override
  String get wrappedTopPhrases => 'Top 5 zinnen';

  @override
  String get wrappedMins => 'min';

  @override
  String get wrappedConvos => 'gesprekken';

  @override
  String get wrappedDays => 'dagen';

  @override
  String get wrappedMyBuddiesLabel => 'MIJN VRIENDEN';

  @override
  String get wrappedObsessionsLabel => 'OBSESSIES';

  @override
  String get wrappedStruggleLabel => 'UITDAGING';

  @override
  String get wrappedWinLabel => 'OVERWINNING';

  @override
  String get wrappedTopPhrasesLabel => 'TOP ZINNEN';

  @override
  String get wrappedLetsHitRewind => 'Laten we terugspoelen naar je';

  @override
  String get wrappedGenerateMyWrapped => 'Genereer mijn Wrapped';

  @override
  String get wrappedProcessingDefault => 'Verwerken...';

  @override
  String get wrappedCreatingYourStory => 'Je 2025\nverhaal maken...';

  @override
  String get wrappedSomethingWentWrong => 'Er ging iets\nmis';

  @override
  String get wrappedAnErrorOccurred => 'Er is een fout opgetreden';

  @override
  String get wrappedTryAgain => 'Opnieuw proberen';

  @override
  String get wrappedNoDataAvailable => 'Geen gegevens beschikbaar';

  @override
  String get wrappedOmiLifeRecap => 'Omi levenssamenvatting';

  @override
  String get wrappedSwipeUpToBegin => 'Veeg omhoog om te beginnen';

  @override
  String get wrappedShareText => 'Mijn 2025, onthouden door Omi ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare => 'Delen mislukt. Probeer het opnieuw.';

  @override
  String get wrappedFailedToStartGeneration => 'Starten van generatie mislukt. Probeer het opnieuw.';

  @override
  String get wrappedStarting => 'Starten...';

  @override
  String get wrappedShare => 'Delen';

  @override
  String get wrappedShareYourWrapped => 'Deel je Wrapped';

  @override
  String get wrappedMy2025 => 'Mijn 2025';

  @override
  String get wrappedRememberedByOmi => 'onthouden door Omi';

  @override
  String get wrappedMostFunDay => 'Leukste';

  @override
  String get wrappedMostProductiveDay => 'Meest productief';

  @override
  String get wrappedMostIntenseDay => 'Meest intens';

  @override
  String get wrappedFunniestMoment => 'Grappigste';

  @override
  String get wrappedMostCringeMoment => 'Meest gênant';

  @override
  String get wrappedMinutesLabel => 'minuten';

  @override
  String get wrappedConversationsLabel => 'gesprekken';

  @override
  String get wrappedDaysActiveLabel => 'actieve dagen';

  @override
  String get wrappedTasksGenerated => 'taken gegenereerd';

  @override
  String get wrappedTasksCompleted => 'taken voltooid';

  @override
  String get wrappedTopFivePhrases => 'Top 5 zinnen';

  @override
  String get wrappedAGreatDay => 'Een geweldige dag';

  @override
  String get wrappedGettingItDone => 'Het gedaan krijgen';

  @override
  String get wrappedAChallenge => 'Een uitdaging';

  @override
  String get wrappedAHilariousMoment => 'Een hilarisch moment';

  @override
  String get wrappedThatAwkwardMoment => 'Dat ongemakkelijke moment';

  @override
  String get wrappedYouHadFunnyMoments => 'Je had grappige momenten dit jaar!';

  @override
  String get wrappedWeveAllBeenThere => 'We zijn er allemaal geweest!';

  @override
  String get wrappedFriend => 'Vriend';

  @override
  String get wrappedYourBuddy => 'Je maat!';

  @override
  String get wrappedNotMentioned => 'Niet genoemd';

  @override
  String get wrappedTheHardPart => 'Het moeilijke deel';

  @override
  String get wrappedPersonalGrowth => 'Persoonlijke groei';

  @override
  String get wrappedFunDay => 'Leuk';

  @override
  String get wrappedProductiveDay => 'Productief';

  @override
  String get wrappedIntenseDay => 'Intens';

  @override
  String get wrappedFunnyMomentTitle => 'Grappig moment';

  @override
  String get wrappedCringeMomentTitle => 'Gênant moment';

  @override
  String get wrappedYouTalkedAboutBadge => 'Je praatte over';

  @override
  String get wrappedCompletedLabel => 'Voltooid';

  @override
  String get wrappedMyBuddiesCard => 'Mijn vrienden';

  @override
  String get wrappedBuddiesLabel => 'VRIENDEN';

  @override
  String get wrappedObsessionsLabelUpper => 'OBSESSIES';

  @override
  String get wrappedStruggleLabelUpper => 'STRIJD';

  @override
  String get wrappedWinLabelUpper => 'OVERWINNING';

  @override
  String get wrappedTopPhrasesLabelUpper => 'TOP ZINNEN';

  @override
  String get wrappedYourHeader => 'Je';

  @override
  String get wrappedTopDaysHeader => 'Beste dagen';

  @override
  String get wrappedYourTopDaysBadge => 'Je beste dagen';

  @override
  String get wrappedBestHeader => 'Beste';

  @override
  String get wrappedMomentsHeader => 'Momenten';

  @override
  String get wrappedBestMomentsBadge => 'Beste momenten';

  @override
  String get wrappedBiggestHeader => 'Grootste';

  @override
  String get wrappedStruggleHeader => 'Strijd';

  @override
  String get wrappedWinHeader => 'Overwinning';

  @override
  String get wrappedButYouPushedThroughEmoji => 'Maar je hebt het gered 💪';

  @override
  String get wrappedYouDidItEmoji => 'Je hebt het gedaan! 🎉';

  @override
  String get wrappedHours => 'uren';

  @override
  String get wrappedActions => 'acties';

  @override
  String get multipleSpeakersDetected => 'Meerdere sprekers gedetecteerd';

  @override
  String get multipleSpeakersDescription =>
      'Het lijkt erop dat er meerdere sprekers in de opname zijn. Zorg ervoor dat je op een rustige plek bent en probeer het opnieuw.';

  @override
  String get invalidRecordingDetected => 'Ongeldige opname gedetecteerd';

  @override
  String get notEnoughSpeechDescription =>
      'Er is niet genoeg spraak gedetecteerd. Spreek alsjeblieft meer en probeer het opnieuw.';

  @override
  String get speechDurationDescription => 'Zorg ervoor dat je minimaal 5 seconden en maximaal 90 seconden spreekt.';

  @override
  String get connectionLostDescription =>
      'De verbinding werd onderbroken. Controleer je internetverbinding en probeer het opnieuw.';

  @override
  String get howToTakeGoodSample => 'Hoe maak je een goed voorbeeld?';

  @override
  String get goodSampleInstructions =>
      '1. Zorg ervoor dat je op een rustige plek bent.\n2. Spreek duidelijk en natuurlijk.\n3. Zorg ervoor dat je apparaat in zijn natuurlijke positie op je nek zit.\n\nNa het maken kun je het altijd verbeteren of opnieuw doen.';

  @override
  String get noDeviceConnectedUseMic => 'Geen apparaat verbonden. De telefoonmicrofoon wordt gebruikt.';

  @override
  String get doItAgain => 'Opnieuw doen';

  @override
  String get listenToSpeechProfile => 'Luister naar mijn stemprofiel ➡️';

  @override
  String get recognizingOthers => 'Anderen herkennen 👀';

  @override
  String get keepGoingGreat => 'Ga zo door, je doet het geweldig';

  @override
  String get somethingWentWrongTryAgain => 'Er is iets misgegaan! Probeer het later opnieuw.';

  @override
  String get uploadingVoiceProfile => 'Je stemprofiel wordt geüpload....';

  @override
  String get memorizingYourVoice => 'Je stem wordt onthouden...';

  @override
  String get personalizingExperience => 'Je ervaring wordt gepersonaliseerd...';

  @override
  String get keepSpeakingUntil100 => 'Blijf praten tot je 100% bereikt.';

  @override
  String get greatJobAlmostThere => 'Goed bezig, je bent er bijna';

  @override
  String get soCloseJustLittleMore => 'Zo dichtbij, nog even';

  @override
  String get notificationFrequency => 'Meldingsfrequentie';

  @override
  String get controlNotificationFrequency => 'Bepaal hoe vaak Omi u proactieve meldingen stuurt.';

  @override
  String get yourScore => 'Jouw score';

  @override
  String get dailyScoreBreakdown => 'Dagelijkse score overzicht';

  @override
  String get todaysScore => 'Score van vandaag';

  @override
  String get tasksCompleted => 'Taken voltooid';

  @override
  String get completionRate => 'Voltooiingspercentage';

  @override
  String get howItWorks => 'Hoe het werkt';

  @override
  String get dailyScoreExplanation =>
      'Je dagelijkse score is gebaseerd op taakvoltooiing. Voltooi je taken om je score te verbeteren!';

  @override
  String get notificationFrequencyDescription => 'Bepaal hoe vaak Omi je proactieve meldingen en herinneringen stuurt.';

  @override
  String get sliderOff => 'Uit';

  @override
  String get sliderMax => 'Max.';

  @override
  String summaryGeneratedFor(String date) {
    return 'Samenvatting gegenereerd voor $date';
  }

  @override
  String get failedToGenerateSummary =>
      'Kon samenvatting niet genereren. Zorg ervoor dat je gesprekken hebt voor die dag.';

  @override
  String get recap => 'Samenvatting';

  @override
  String deleteQuoted(String name) {
    return '\"$name\" verwijderen';
  }

  @override
  String moveConversationsTo(int count) {
    return '$count gesprekken verplaatsen naar:';
  }

  @override
  String get noFolder => 'Geen map';

  @override
  String get removeFromAllFolders => 'Uit alle mappen verwijderen';

  @override
  String get buildAndShareYourCustomApp => 'Bouw en deel je aangepaste app';

  @override
  String get searchAppsPlaceholder => 'Zoek in 1500+ apps';

  @override
  String get filters => 'Filters';

  @override
  String get frequencyOff => 'Uit';

  @override
  String get frequencyMinimal => 'Minimaal';

  @override
  String get frequencyLow => 'Laag';

  @override
  String get frequencyBalanced => 'Gebalanceerd';

  @override
  String get frequencyHigh => 'Hoog';

  @override
  String get frequencyMaximum => 'Maximum';

  @override
  String get frequencyDescOff => 'Geen proactieve meldingen';

  @override
  String get frequencyDescMinimal => 'Alleen kritieke herinneringen';

  @override
  String get frequencyDescLow => 'Alleen belangrijke updates';

  @override
  String get frequencyDescBalanced => 'Regelmatige nuttige herinneringen';

  @override
  String get frequencyDescHigh => 'Frequente check-ins';

  @override
  String get frequencyDescMaximum => 'Blijf constant betrokken';

  @override
  String get clearChatQuestion => 'Chat wissen?';

  @override
  String get syncingMessages => 'Berichten synchroniseren met de server...';

  @override
  String get chatAppsTitle => 'Chat-apps';

  @override
  String get selectApp => 'App selecteren';

  @override
  String get noChatAppsEnabled => 'Geen chat-apps ingeschakeld.\nTik op \"Apps inschakelen\" om toe te voegen.';

  @override
  String get disable => 'Uitschakelen';

  @override
  String get photoLibrary => 'Fotobibliotheek';

  @override
  String get chooseFile => 'Bestand kiezen';

  @override
  String get configureAiPersona => 'Configureer je AI-persona';

  @override
  String get connectAiAssistantsToYourData => 'Verbind AI-assistenten met je gegevens';

  @override
  String get oAuth => 'OAuth';

  @override
  String get trackYourGoalsOnHomepage => 'Volg je persoonlijke doelen op de startpagina';

  @override
  String get deleteRecording => 'Opname verwijderen';

  @override
  String get thisCannotBeUndone => 'Dit kan niet ongedaan worden gemaakt.';

  @override
  String get sdCard => 'SD-kaart';

  @override
  String get fromSd => 'Van SD';

  @override
  String get limitless => 'Limitless';

  @override
  String get fastTransfer => 'Snelle overdracht';

  @override
  String get syncingStatus => 'Synchroniseren';

  @override
  String get failedStatus => 'Mislukt';

  @override
  String etaLabel(String time) {
    return 'ETA: $time';
  }

  @override
  String get transferMethod => 'Overdrachtsmethode';

  @override
  String get fast => 'Snel';

  @override
  String get ble => 'BLE';

  @override
  String get phone => 'Telefoon';

  @override
  String get cancelSync => 'Synchronisatie annuleren';

  @override
  String get cancelSyncMessage => 'Reeds gedownloade gegevens worden opgeslagen. Je kunt later hervatten.';

  @override
  String get syncCancelled => 'Synchronisatie geannuleerd';

  @override
  String get deleteProcessedFiles => 'Verwerkte bestanden verwijderen';

  @override
  String get processedFilesDeleted => 'Verwerkte bestanden verwijderd';

  @override
  String get wifiEnableFailed => 'Kon WiFi niet inschakelen op apparaat. Probeer opnieuw.';

  @override
  String get deviceNoFastTransfer =>
      'Je apparaat ondersteunt geen snelle overdracht. Gebruik Bluetooth in plaats daarvan.';

  @override
  String get enableHotspotMessage => 'Schakel de hotspot van je telefoon in en probeer opnieuw.';

  @override
  String get transferStartFailed => 'Kon overdracht niet starten. Probeer opnieuw.';

  @override
  String get deviceNotResponding => 'Apparaat reageerde niet. Probeer opnieuw.';

  @override
  String get invalidWifiCredentials => 'Ongeldige WiFi-gegevens. Controleer je hotspot-instellingen.';

  @override
  String get wifiConnectionFailed => 'WiFi-verbinding mislukt. Probeer opnieuw.';

  @override
  String get sdCardProcessing => 'SD-kaart verwerking';

  @override
  String sdCardProcessingMessage(int count) {
    return '$count opname(s) verwerken. Bestanden worden na verwerking van de SD-kaart verwijderd.';
  }

  @override
  String get process => 'Verwerken';

  @override
  String get wifiSyncFailed => 'WiFi-synchronisatie mislukt';

  @override
  String get processingFailed => 'Verwerking mislukt';

  @override
  String get downloadingFromSdCard => 'Downloaden van SD-kaart';

  @override
  String processingProgress(int current, int total) {
    return 'Verwerken $current/$total';
  }

  @override
  String conversationsCreated(int count) {
    return '$count gesprekken aangemaakt';
  }

  @override
  String get internetRequired => 'Internet vereist';

  @override
  String get processAudio => 'Audio verwerken';

  @override
  String get start => 'Starten';

  @override
  String get noRecordings => 'Geen opnames';

  @override
  String get audioFromOmiWillAppearHere => 'Audio van je Omi-apparaat verschijnt hier';

  @override
  String get deleteProcessed => 'Verwerkte verwijderen';

  @override
  String get tryDifferentFilter => 'Probeer een ander filter';

  @override
  String get recordings => 'Opnames';

  @override
  String get enableRemindersAccess =>
      'Schakel toegang tot Herinneringen in via Instellingen om Apple Herinneringen te gebruiken';

  @override
  String todayAtTime(String time) {
    return 'Vandaag om $time';
  }

  @override
  String yesterdayAtTime(String time) {
    return 'Gisteren om $time';
  }

  @override
  String get lessThanAMinute => 'Minder dan een minuut';

  @override
  String estimatedMinutes(int count) {
    return '~$count minuut/minuten';
  }

  @override
  String estimatedHours(int count) {
    return '~$count uur';
  }

  @override
  String estimatedTimeRemaining(String time) {
    return 'Geschat: $time resterend';
  }

  @override
  String get summarizingConversation => 'Gesprek samenvatten...\nDit kan enkele seconden duren';

  @override
  String get resummarizingConversation => 'Gesprek opnieuw samenvatten...\nDit kan enkele seconden duren';

  @override
  String get nothingInterestingRetry => 'Niets interessants gevonden,\nwil je het opnieuw proberen?';

  @override
  String get noSummaryForConversation => 'Geen samenvatting beschikbaar\nvoor dit gesprek.';

  @override
  String get unknownLocation => 'Onbekende locatie';

  @override
  String get couldNotLoadMap => 'Kaart kon niet worden geladen';

  @override
  String get triggerConversationIntegration => 'Gesprek aanmaak-integratie activeren';

  @override
  String get webhookUrlNotSet => 'Webhook URL niet ingesteld';

  @override
  String get setWebhookUrlInSettings =>
      'Stel de webhook URL in bij ontwikkelaarsinstellingen om deze functie te gebruiken.';

  @override
  String get sendWebUrl => 'Verstuur web-URL';

  @override
  String get sendTranscript => 'Verstuur transcript';

  @override
  String get sendSummary => 'Verstuur samenvatting';

  @override
  String get debugModeDetected => 'Debug-modus gedetecteerd';

  @override
  String get performanceReduced => 'Prestaties kunnen verminderd zijn';

  @override
  String autoClosingInSeconds(int seconds) {
    return 'Sluit automatisch over $seconds seconden';
  }

  @override
  String get modelRequired => 'Model vereist';

  @override
  String get downloadWhisperModel => 'Download een whisper-model om on-device transcriptie te gebruiken';

  @override
  String get deviceNotCompatible => 'Je apparaat is niet compatibel met on-device transcriptie';

  @override
  String get deviceRequirements => 'Je apparaat voldoet niet aan de vereisten voor on-device transcriptie.';

  @override
  String get willLikelyCrash => 'Dit inschakelen zal waarschijnlijk de app laten crashen of vastlopen.';

  @override
  String get transcriptionSlowerLessAccurate => 'Transcriptie zal aanzienlijk langzamer en minder nauwkeurig zijn.';

  @override
  String get proceedAnyway => 'Toch doorgaan';

  @override
  String get olderDeviceDetected => 'Ouder apparaat gedetecteerd';

  @override
  String get onDeviceSlower => 'On-device transcriptie kan trager zijn op dit apparaat.';

  @override
  String get batteryUsageHigher => 'Batterijverbruik zal hoger zijn dan cloud transcriptie.';

  @override
  String get considerOmiCloud => 'Overweeg Omi Cloud te gebruiken voor betere prestaties.';

  @override
  String get highResourceUsage => 'Hoog bronnengebruik';

  @override
  String get onDeviceIntensive => 'On-device transcriptie is rekenintensief.';

  @override
  String get batteryDrainIncrease => 'Het batterijverbruik zal aanzienlijk toenemen.';

  @override
  String get deviceMayWarmUp => 'Apparaat kan warm worden tijdens langdurig gebruik.';

  @override
  String get speedAccuracyLower => 'Snelheid en nauwkeurigheid kunnen lager zijn dan Cloud-modellen.';

  @override
  String get cloudProvider => 'Cloud-provider';

  @override
  String get premiumMinutesInfo =>
      '1.200 premium minuten/maand. Het On-Device tabblad biedt onbeperkte gratis transcriptie.';

  @override
  String get viewUsage => 'Bekijk gebruik';

  @override
  String get localProcessingInfo =>
      'Audio wordt lokaal verwerkt. Werkt offline, meer privacy, maar gebruikt meer batterij.';

  @override
  String get model => 'Model';

  @override
  String get performanceWarning => 'Prestatiewaarschuwing';

  @override
  String get largeModelWarning =>
      'Dit model is groot en kan de app laten crashen of zeer traag draaien op mobiele apparaten.\n\n\"small\" of \"base\" wordt aanbevolen.';

  @override
  String get usingNativeIosSpeech => 'Gebruik van native iOS spraakherkenning';

  @override
  String get noModelDownloadRequired =>
      'De native spraakengine van je apparaat wordt gebruikt. Geen modeldownload vereist.';

  @override
  String get modelReady => 'Model gereed';

  @override
  String get redownload => 'Opnieuw downloaden';

  @override
  String get doNotCloseApp => 'Sluit de app niet.';

  @override
  String get downloading => 'Downloaden...';

  @override
  String get downloadModel => 'Model downloaden';

  @override
  String estimatedSize(String size) {
    return 'Geschatte grootte: ~$size MB';
  }

  @override
  String availableSpace(String space) {
    return 'Beschikbare ruimte: $space';
  }

  @override
  String get notEnoughSpace => 'Waarschuwing: Niet genoeg ruimte!';

  @override
  String get download => 'Downloaden';

  @override
  String downloadError(String error) {
    return 'Downloadfout: $error';
  }

  @override
  String get cancelled => 'Geannuleerd';

  @override
  String get deviceNotCompatibleTitle => 'Apparaat niet compatibel';

  @override
  String get deviceNotMeetRequirements => 'Je apparaat voldoet niet aan de vereisten voor on-device transcriptie.';

  @override
  String get transcriptionSlowerOnDevice => 'On-device transcriptie kan langzamer zijn op dit apparaat.';

  @override
  String get computationallyIntensive => 'On-device transcriptie is rekenintensief.';

  @override
  String get batteryDrainSignificantly => 'Batterijverbruik zal aanzienlijk toenemen.';

  @override
  String get premiumMinutesMonth =>
      '1.200 premium minuten/maand. Het tabblad On-device biedt onbeperkte gratis transcriptie. ';

  @override
  String get audioProcessedLocally =>
      'Audio wordt lokaal verwerkt. Werkt offline, meer privacy, maar gebruikt meer batterij.';

  @override
  String get languageLabel => 'Taal';

  @override
  String get modelLabel => 'Model';

  @override
  String get modelTooLargeWarning =>
      'Dit model is groot en kan de app laten crashen of zeer langzaam werken op mobiele apparaten.\n\nsmall of base wordt aanbevolen.';

  @override
  String get nativeEngineNoDownload =>
      'De native spraakengine van je apparaat wordt gebruikt. Geen model download nodig.';

  @override
  String modelReadyWithName(String model) {
    return 'Model gereed ($model)';
  }

  @override
  String get reDownload => 'Opnieuw downloaden';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return '$model downloaden: $received / $total MB';
  }

  @override
  String preparingModel(String model) {
    return '$model voorbereiden...';
  }

  @override
  String downloadErrorWithMessage(String error) {
    return 'Downloadfout: $error';
  }

  @override
  String estimatedSizeWithValue(String size) {
    return 'Geschatte grootte: ~$size MB';
  }

  @override
  String availableSpaceWithValue(String space) {
    return 'Beschikbare ruimte: $space';
  }

  @override
  String get omiTranscriptionOptimized =>
      'Omis ingebouwde live transcriptie is geoptimaliseerd voor realtime gesprekken met automatische sprekersdetectie en diarisatie.';

  @override
  String get reset => 'Resetten';

  @override
  String get useTemplateFrom => 'Gebruik sjabloon van';

  @override
  String get selectProviderTemplate => 'Selecteer een provider sjabloon...';

  @override
  String get quicklyPopulateResponse => 'Snel invullen met bekend provider antwoordformaat';

  @override
  String get quicklyPopulateRequest => 'Snel invullen met bekend provider verzoekformaat';

  @override
  String get invalidJsonError => 'Ongeldige JSON';

  @override
  String downloadModelWithName(String model) {
    return 'Model downloaden ($model)';
  }

  @override
  String modelNameWithFile(String model) {
    return 'Model: $model';
  }

  @override
  String get device => 'Apparaat';

  @override
  String get chatAssistantsTitle => 'Chat-assistenten';

  @override
  String get permissionReadConversations => 'Gesprekken lezen';

  @override
  String get permissionReadMemories => 'Herinneringen lezen';

  @override
  String get permissionReadTasks => 'Taken lezen';

  @override
  String get permissionCreateConversations => 'Gesprekken maken';

  @override
  String get permissionCreateMemories => 'Herinneringen maken';

  @override
  String get permissionTypeAccess => 'Toegang';

  @override
  String get permissionTypeCreate => 'Maken';

  @override
  String get permissionTypeTrigger => 'Trigger';

  @override
  String get permissionDescReadConversations => 'Deze app heeft toegang tot je gesprekken.';

  @override
  String get permissionDescReadMemories => 'Deze app heeft toegang tot je herinneringen.';

  @override
  String get permissionDescReadTasks => 'Deze app heeft toegang tot je taken.';

  @override
  String get permissionDescCreateConversations => 'Deze app kan nieuwe gesprekken maken.';

  @override
  String get permissionDescCreateMemories => 'Deze app kan nieuwe herinneringen maken.';

  @override
  String get realtimeListening => 'Realtime luisteren';

  @override
  String get setupCompleted => 'Voltooid';

  @override
  String get pleaseSelectRating => 'Selecteer een beoordeling';

  @override
  String get writeReviewOptional => 'Schrijf een recensie (optioneel)';

  @override
  String get setupQuestionsIntro => 'Help ons Omi te verbeteren door een paar vragen te beantwoorden. 🫶 💜';

  @override
  String get setupQuestionProfession => '1. Wat doe je voor werk?';

  @override
  String get setupQuestionUsage => '2. Waar ben je van plan je Omi te gebruiken?';

  @override
  String get setupQuestionAge => '3. Wat is je leeftijdscategorie?';

  @override
  String get setupAnswerAllQuestions => 'Je hebt nog niet alle vragen beantwoord! 🥺';

  @override
  String get setupSkipHelp => 'Overslaan, ik wil niet helpen :C';

  @override
  String get professionEntrepreneur => 'Ondernemer';

  @override
  String get professionSoftwareEngineer => 'Software-ontwikkelaar';

  @override
  String get professionProductManager => 'Productmanager';

  @override
  String get professionExecutive => 'Directeur';

  @override
  String get professionSales => 'Verkoop';

  @override
  String get professionStudent => 'Student';

  @override
  String get usageAtWork => 'Op het werk';

  @override
  String get usageIrlEvents => 'Bij evenementen';

  @override
  String get usageOnline => 'Online';

  @override
  String get usageSocialSettings => 'In sociale omgevingen';

  @override
  String get usageEverywhere => 'Overal';

  @override
  String get customBackendUrlTitle => 'Aangepaste backend-URL';

  @override
  String get backendUrlLabel => 'Backend-URL';

  @override
  String get saveUrlButton => 'URL opslaan';

  @override
  String get enterBackendUrlError => 'Voer de backend-URL in';

  @override
  String get urlMustEndWithSlashError => 'URL moet eindigen met \"/\"';

  @override
  String get invalidUrlError => 'Voer een geldige URL in';

  @override
  String get backendUrlSavedSuccess => 'Backend-URL succesvol opgeslagen!';

  @override
  String get signInTitle => 'Inloggen';

  @override
  String get signInButton => 'Inloggen';

  @override
  String get enterEmailError => 'Voer uw e-mailadres in';

  @override
  String get invalidEmailError => 'Voer een geldig e-mailadres in';

  @override
  String get enterPasswordError => 'Voer uw wachtwoord in';

  @override
  String get passwordMinLengthError => 'Wachtwoord moet minimaal 8 tekens zijn';

  @override
  String get signInSuccess => 'Inloggen gelukt!';

  @override
  String get alreadyHaveAccountLogin => 'Heeft u al een account? Log in';

  @override
  String get emailLabel => 'E-mail';

  @override
  String get passwordLabel => 'Wachtwoord';

  @override
  String get createAccountTitle => 'Account aanmaken';

  @override
  String get nameLabel => 'Naam';

  @override
  String get repeatPasswordLabel => 'Wachtwoord herhalen';

  @override
  String get signUpButton => 'Registreren';

  @override
  String get enterNameError => 'Voer uw naam in';

  @override
  String get passwordsDoNotMatch => 'Wachtwoorden komen niet overeen';

  @override
  String get signUpSuccess => 'Registratie gelukt!';

  @override
  String get loadingKnowledgeGraph => 'Kennisgrafiek laden...';

  @override
  String get noKnowledgeGraphYet => 'Nog geen kennisgrafiek';

  @override
  String get buildingKnowledgeGraphFromMemories => 'Kennisgrafiek opbouwen vanuit herinneringen...';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'Uw kennisgrafiek wordt automatisch opgebouwd wanneer u nieuwe herinneringen maakt.';

  @override
  String get buildGraphButton => 'Grafiek bouwen';

  @override
  String get checkOutMyMemoryGraph => 'Bekijk mijn geheugengrafiek!';

  @override
  String get getButton => 'Download';

  @override
  String openingApp(String appName) {
    return '$appName openen...';
  }

  @override
  String get writeSomething => 'Schrijf iets';

  @override
  String get submitReply => 'Antwoord verzenden';

  @override
  String get editYourReply => 'Antwoord bewerken';

  @override
  String get replyToReview => 'Reageer op review';

  @override
  String get rateAndReviewThisApp => 'Beoordeel en recenseer deze app';

  @override
  String get noChangesInReview => 'Geen wijzigingen in de recensie om bij te werken.';

  @override
  String get cantRateWithoutInternet => 'Kan app niet beoordelen zonder internetverbinding.';

  @override
  String get appAnalytics => 'App-analyse';

  @override
  String get learnMoreLink => 'meer informatie';

  @override
  String get moneyEarned => 'Verdiend geld';

  @override
  String get writeYourReply => 'Schrijf je reactie...';

  @override
  String get replySentSuccessfully => 'Reactie succesvol verzonden';

  @override
  String failedToSendReply(String error) {
    return 'Reactie verzenden mislukt: $error';
  }

  @override
  String get send => 'Verzenden';

  @override
  String starFilter(int count) {
    return '$count ster';
  }

  @override
  String get noReviewsFound => 'Geen recensies gevonden';

  @override
  String get editReply => 'Reactie bewerken';

  @override
  String get reply => 'Reageren';

  @override
  String starFilterLabel(int count) {
    return '$count ster';
  }

  @override
  String get sharePublicLink => 'Openbare link delen';

  @override
  String get makePersonaPublic => 'Persona openbaar maken';

  @override
  String get connectedKnowledgeData => 'Verbonden kennisgegevens';

  @override
  String get enterName => 'Voer naam in';

  @override
  String get disconnectTwitter => 'Twitter ontkoppelen';

  @override
  String get disconnectTwitterConfirmation =>
      'Weet je zeker dat je je Twitter-account wilt ontkoppelen? Je persona heeft dan geen toegang meer tot je Twitter-gegevens.';

  @override
  String get getOmiDeviceDescription => 'Maak een nauwkeuriger kloon met je persoonlijke gesprekken';

  @override
  String get getOmi => 'Omi aanschaffen';

  @override
  String get iHaveOmiDevice => 'Ik heb een Omi-apparaat';

  @override
  String get goal => 'DOEL';

  @override
  String get tapToTrackThisGoal => 'Tik om dit doel te volgen';

  @override
  String get tapToSetAGoal => 'Tik om een doel in te stellen';

  @override
  String get processedConversations => 'Verwerkte gesprekken';

  @override
  String get updatedConversations => 'Bijgewerkte gesprekken';

  @override
  String get newConversations => 'Nieuwe gesprekken';

  @override
  String get summaryTemplate => 'Samenvattingssjabloon';

  @override
  String get suggestedTemplates => 'Voorgestelde sjablonen';

  @override
  String get otherTemplates => 'Andere sjablonen';

  @override
  String get availableTemplates => 'Beschikbare sjablonen';

  @override
  String get getCreative => 'Wees creatief';

  @override
  String get defaultLabel => 'Standaard';

  @override
  String get lastUsedLabel => 'Laatst gebruikt';

  @override
  String get setDefaultApp => 'Standaardapp instellen';

  @override
  String setDefaultAppContent(String appName) {
    return '$appName instellen als je standaard samenvattingsapp?\\n\\nDeze app wordt automatisch gebruikt voor alle toekomstige gesprekssamenvattingen.';
  }

  @override
  String get setDefaultButton => 'Als standaard instellen';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName ingesteld als standaard samenvattingsapp';
  }

  @override
  String get createCustomTemplate => 'Aangepast sjabloon maken';

  @override
  String get allTemplates => 'Alle sjablonen';

  @override
  String failedToInstallApp(String appName) {
    return 'Installatie van $appName mislukt. Probeer het opnieuw.';
  }

  @override
  String errorInstallingApp(String appName, String error) {
    return 'Fout bij installeren van $appName: $error';
  }

  @override
  String tagSpeaker(int speakerId) {
    return 'Spreker $speakerId taggen';
  }

  @override
  String get personNameAlreadyExists => 'Er bestaat al een persoon met deze naam.';

  @override
  String get selectYouFromList => 'Om jezelf te taggen, selecteer \"Jij\" uit de lijst.';

  @override
  String get enterPersonsName => 'Voer naam van persoon in';

  @override
  String get addPerson => 'Persoon toevoegen';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'Andere segmenten van deze spreker taggen ($selected/$total)';
  }

  @override
  String get tagOtherSegments => 'Andere segmenten taggen';

  @override
  String get managePeople => 'Personen beheren';

  @override
  String get shareViaSms => 'Delen via SMS';

  @override
  String get selectContactsToShareSummary => 'Selecteer contacten om je gesprekssamenvatting te delen';

  @override
  String get searchContactsHint => 'Contacten zoeken...';

  @override
  String contactsSelectedCount(int count) {
    return '$count geselecteerd';
  }

  @override
  String get clearAllSelection => 'Alles wissen';

  @override
  String get selectContactsToShare => 'Selecteer contacten om te delen';

  @override
  String shareWithContactCount(int count) {
    return 'Delen met $count contact';
  }

  @override
  String shareWithContactsCount(int count) {
    return 'Delen met $count contacten';
  }

  @override
  String get contactsPermissionRequired => 'Contactentoestemming vereist';

  @override
  String get contactsPermissionRequiredForSms => 'Contactentoestemming is vereist om via SMS te delen';

  @override
  String get grantContactsPermissionForSms => 'Geef contactentoestemming om via SMS te delen';

  @override
  String get noContactsWithPhoneNumbers => 'Geen contacten met telefoonnummers gevonden';

  @override
  String get noContactsMatchSearch => 'Geen contacten komen overeen met uw zoekopdracht';

  @override
  String get failedToLoadContacts => 'Kan contacten niet laden';

  @override
  String get failedToPrepareConversationForSharing => 'Kan gesprek niet voorbereiden om te delen. Probeer het opnieuw.';

  @override
  String get couldNotOpenSmsApp => 'Kan SMS-app niet openen. Probeer het opnieuw.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'Hier is waar we net over spraken: $link';
  }

  @override
  String get wifiSync => 'WiFi-synchronisatie';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item gekopieerd naar klembord';
  }

  @override
  String get wifiConnectionFailedTitle => 'Verbinding mislukt';

  @override
  String connectingToDeviceName(String deviceName) {
    return 'Verbinden met $deviceName';
  }

  @override
  String enableDeviceWifi(String deviceName) {
    return 'WiFi van $deviceName inschakelen';
  }

  @override
  String connectToDeviceName(String deviceName) {
    return 'Verbinden met $deviceName';
  }

  @override
  String get recordingDetails => 'Opnamegegevens';

  @override
  String get storageLocationSdCard => 'SD-kaart';

  @override
  String get storageLocationLimitlessPendant => 'Limitless Pendant';

  @override
  String get storageLocationPhone => 'Telefoon';

  @override
  String get storageLocationPhoneMemory => 'Telefoon (Geheugen)';

  @override
  String storedOnDevice(String deviceName) {
    return 'Opgeslagen op $deviceName';
  }

  @override
  String get transferring => 'Bezig met overdragen...';

  @override
  String get transferRequired => 'Overdracht vereist';

  @override
  String get downloadingAudioFromSdCard => 'Audio downloaden van de SD-kaart van je apparaat';

  @override
  String get transferRequiredDescription =>
      'Deze opname staat op de SD-kaart van je apparaat. Zet deze over naar je telefoon om af te spelen of te delen.';

  @override
  String get cancelTransfer => 'Overdracht annuleren';

  @override
  String get transferToPhone => 'Overdragen naar telefoon';

  @override
  String get privateAndSecureOnDevice => 'Privé en veilig op je apparaat';

  @override
  String get recordingInfo => 'Opname-informatie';

  @override
  String get transferInProgress => 'Overdracht bezig...';

  @override
  String get shareRecording => 'Opname delen';

  @override
  String get deleteRecordingConfirmation =>
      'Weet je zeker dat je deze opname permanent wilt verwijderen? Dit kan niet ongedaan worden gemaakt.';

  @override
  String get recordingIdLabel => 'Opname-ID';

  @override
  String get dateTimeLabel => 'Datum & Tijd';

  @override
  String get durationLabel => 'Duur';

  @override
  String get audioFormatLabel => 'Audioformaat';

  @override
  String get storageLocationLabel => 'Opslaglocatie';

  @override
  String get estimatedSizeLabel => 'Geschatte grootte';

  @override
  String get deviceModelLabel => 'Apparaatmodel';

  @override
  String get deviceIdLabel => 'Apparaat-ID';

  @override
  String get statusLabel => 'Status';

  @override
  String get statusProcessed => 'Verwerkt';

  @override
  String get statusUnprocessed => 'Niet verwerkt';

  @override
  String get switchedToFastTransfer => 'Overgeschakeld naar snelle overdracht';

  @override
  String get transferCompleteMessage => 'Overdracht voltooid! Je kunt deze opname nu afspelen.';

  @override
  String transferFailedMessage(String error) {
    return 'Overdracht mislukt: $error';
  }

  @override
  String get transferCancelled => 'Overdracht geannuleerd';

  @override
  String get fastTransferEnabled => 'Snelle overdracht ingeschakeld';

  @override
  String get bluetoothSyncEnabled => 'Bluetooth-synchronisatie ingeschakeld';

  @override
  String get enableFastTransfer => 'Snelle overdracht inschakelen';

  @override
  String get fastTransferDescription =>
      'Snelle overdracht gebruikt WiFi voor ~5x snellere snelheden. Je telefoon maakt tijdens de overdracht tijdelijk verbinding met het WiFi-netwerk van je Omi-apparaat.';

  @override
  String get internetAccessPausedDuringTransfer => 'Internettoegang is onderbroken tijdens overdracht';

  @override
  String get chooseTransferMethodDescription =>
      'Kies hoe opnames worden overgedragen van je Omi-apparaat naar je telefoon.';

  @override
  String get wifiSpeed => '~150 KB/s via WiFi';

  @override
  String get fiveTimesFaster => '5X SNELLER';

  @override
  String get fastTransferMethodDescription =>
      'Maakt een directe WiFi-verbinding met je Omi-apparaat. Je telefoon wordt tijdens de overdracht tijdelijk losgekoppeld van je normale WiFi.';

  @override
  String get bluetooth => 'Bluetooth';

  @override
  String get bleSpeed => '~30 KB/s via BLE';

  @override
  String get bluetoothMethodDescription =>
      'Gebruikt standaard Bluetooth Low Energy-verbinding. Langzamer maar beïnvloedt je WiFi-verbinding niet.';

  @override
  String get selected => 'Geselecteerd';

  @override
  String get selectOption => 'Selecteren';

  @override
  String get lowBatteryAlertTitle => 'Waarschuwing lage batterij';

  @override
  String get lowBatteryAlertBody => 'De batterij van uw apparaat is bijna leeg. Tijd om op te laden! 🔋';

  @override
  String get deviceDisconnectedNotificationTitle => 'Uw Omi-apparaat is losgekoppeld';

  @override
  String get deviceDisconnectedNotificationBody => 'Verbind opnieuw om Omi te blijven gebruiken.';

  @override
  String get firmwareUpdateAvailable => 'Firmware-update beschikbaar';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'Er is een nieuwe firmware-update ($version) beschikbaar voor uw Omi-apparaat. Wilt u nu bijwerken?';
  }

  @override
  String get later => 'Later';

  @override
  String get appDeletedSuccessfully => 'App succesvol verwijderd';

  @override
  String get appDeleteFailed => 'Kan app niet verwijderen. Probeer het later opnieuw.';

  @override
  String get appVisibilityChangedSuccessfully =>
      'Zichtbaarheid van app succesvol gewijzigd. Het kan enkele minuten duren voordat dit zichtbaar is.';

  @override
  String get errorActivatingAppIntegration =>
      'Fout bij het activeren van de app. Als het een integratie-app is, zorg ervoor dat de installatie is voltooid.';

  @override
  String get errorUpdatingAppStatus => 'Er is een fout opgetreden bij het bijwerken van de app-status.';

  @override
  String get calculatingETA => 'Berekenen...';

  @override
  String aboutMinutesRemaining(int minutes) {
    return 'Ongeveer $minutes minuten resterend';
  }

  @override
  String get aboutAMinuteRemaining => 'Ongeveer een minuut resterend';

  @override
  String get almostDone => 'Bijna klaar...';

  @override
  String get omiSays => 'omi zegt';

  @override
  String get analyzingYourData => 'Je gegevens analyseren...';

  @override
  String migratingToProtection(String level) {
    return 'Migreren naar $level beveiliging...';
  }

  @override
  String get noDataToMigrateFinalizing => 'Geen gegevens om te migreren. Afronden...';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return '$itemType migreren... $percentage%';
  }

  @override
  String get allObjectsMigratedFinalizing => 'Alle objecten gemigreerd. Afronden...';

  @override
  String get migrationErrorOccurred => 'Er is een fout opgetreden tijdens de migratie. Probeer opnieuw.';

  @override
  String get migrationComplete => 'Migratie voltooid!';

  @override
  String dataProtectedWithSettings(String level) {
    return 'Je gegevens zijn nu beschermd met de nieuwe $level instellingen.';
  }

  @override
  String get chatsLowercase => 'chats';

  @override
  String get dataLowercase => 'gegevens';

  @override
  String get fallNotificationTitle => 'Au';

  @override
  String get fallNotificationBody => 'Ben je gevallen?';

  @override
  String get importantConversationTitle => 'Belangrijk gesprek';

  @override
  String get importantConversationBody => 'Je hebt net een belangrijk gesprek gehad. Tik om de samenvatting te delen.';

  @override
  String get templateName => 'Sjabloonnaam';

  @override
  String get templateNameHint => 'bijv. Vergaderactiepunten Extractor';

  @override
  String get nameMustBeAtLeast3Characters => 'Naam moet minimaal 3 tekens zijn';

  @override
  String get conversationPromptHint =>
      'bijv., Haal actiepunten, genomen beslissingen en belangrijke punten uit het gesprek.';

  @override
  String get pleaseEnterAppPrompt => 'Voer een prompt in voor uw app';

  @override
  String get promptMustBeAtLeast10Characters => 'Prompt moet minimaal 10 tekens zijn';

  @override
  String get anyoneCanDiscoverTemplate => 'Iedereen kan uw sjabloon ontdekken';

  @override
  String get onlyYouCanUseTemplate => 'Alleen u kunt deze sjabloon gebruiken';

  @override
  String get generatingDescription => 'Beschrijving genereren...';

  @override
  String get creatingAppIcon => 'App-pictogram maken...';

  @override
  String get installingApp => 'App installeren...';

  @override
  String get appCreatedAndInstalled => 'App gemaakt en geïnstalleerd!';

  @override
  String get appCreatedSuccessfully => 'App succesvol gemaakt!';

  @override
  String get failedToCreateApp => 'Kan app niet maken. Probeer het opnieuw.';

  @override
  String get addAppSelectCoreCapability => 'Selecteer nog een kernfunctie voor uw app';

  @override
  String get addAppSelectPaymentPlan => 'Selecteer een betalingsplan en voer een prijs in voor uw app';

  @override
  String get addAppSelectCapability => 'Selecteer minstens één functie voor uw app';

  @override
  String get addAppSelectLogo => 'Selecteer een logo voor uw app';

  @override
  String get addAppEnterChatPrompt => 'Voer een chatprompt in voor uw app';

  @override
  String get addAppEnterConversationPrompt => 'Voer een gespreksprompt in voor uw app';

  @override
  String get addAppSelectTriggerEvent => 'Selecteer een triggergebeurtenis voor uw app';

  @override
  String get addAppEnterWebhookUrl => 'Voer een webhook-URL in voor uw app';

  @override
  String get addAppSelectCategory => 'Selecteer een categorie voor uw app';

  @override
  String get addAppFillRequiredFields => 'Vul alle verplichte velden correct in';

  @override
  String get addAppUpdatedSuccess => 'App succesvol bijgewerkt 🚀';

  @override
  String get addAppUpdateFailed => 'Bijwerken mislukt. Probeer het later opnieuw';

  @override
  String get addAppSubmittedSuccess => 'App succesvol ingediend 🚀';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'Fout bij openen bestandskiezer: $message';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'Fout bij selecteren afbeelding: $error';
  }

  @override
  String get addAppPhotosPermissionDenied => 'Fototoegang geweigerd. Geef toegang tot foto\'s';

  @override
  String get addAppErrorSelectingImageRetry => 'Fout bij selecteren afbeelding. Probeer opnieuw.';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'Fout bij selecteren miniatuur: $error';
  }

  @override
  String get addAppErrorSelectingThumbnailRetry => 'Fout bij selecteren miniatuur. Probeer opnieuw.';

  @override
  String get addAppCapabilityConflictWithPersona => 'Andere functies kunnen niet worden geselecteerd met Persona';

  @override
  String get addAppPersonaConflictWithCapabilities => 'Persona kan niet worden geselecteerd met andere functies';

  @override
  String get personaTwitterHandleNotFound => 'Twitter-handle niet gevonden';

  @override
  String get personaTwitterHandleSuspended => 'Twitter-handle is geschorst';

  @override
  String get personaFailedToVerifyTwitter => 'Twitter-handle verificatie mislukt';

  @override
  String get personaFailedToFetch => 'Ophalen van persona mislukt';

  @override
  String get personaFailedToCreate => 'Aanmaken van persona mislukt';

  @override
  String get personaConnectKnowledgeSource => 'Verbind minstens één gegevensbron (Omi of Twitter)';

  @override
  String get personaUpdatedSuccessfully => 'Persona succesvol bijgewerkt';

  @override
  String get personaFailedToUpdate => 'Bijwerken van persona mislukt';

  @override
  String get personaPleaseSelectImage => 'Selecteer een afbeelding';

  @override
  String get personaFailedToCreateTryLater => 'Aanmaken van persona mislukt. Probeer het later opnieuw.';

  @override
  String personaFailedToCreateWithError(String error) {
    return 'Aanmaken van persona mislukt: $error';
  }

  @override
  String get personaFailedToEnable => 'Activeren van persona mislukt';

  @override
  String personaErrorEnablingWithError(String error) {
    return 'Fout bij activeren persona: $error';
  }

  @override
  String get paymentFailedToFetchCountries => 'Ophalen van ondersteunde landen mislukt. Probeer het later opnieuw.';

  @override
  String get paymentFailedToSetDefault => 'Instellen standaard betaalmethode mislukt. Probeer het later opnieuw.';

  @override
  String get paymentFailedToSavePaypal => 'Opslaan PayPal-gegevens mislukt. Probeer het later opnieuw.';

  @override
  String get paypalEmailHint => 'nik@example.com';

  @override
  String get paypalMeLinkHint => 'paypal.me/nik';

  @override
  String get paymentMethodStripe => 'Stripe';

  @override
  String get paymentMethodPayPal => 'PayPal';

  @override
  String get paymentStatusActive => 'Actief';

  @override
  String get paymentStatusConnected => 'Verbonden';

  @override
  String get paymentStatusNotConnected => 'Niet verbonden';

  @override
  String get paymentAppCost => 'App-kosten';

  @override
  String get paymentEnterValidAmount => 'Voer een geldig bedrag in';

  @override
  String get paymentEnterAmountGreaterThanZero => 'Voer een bedrag groter dan 0 in';

  @override
  String get paymentPlan => 'Betalingsplan';

  @override
  String get paymentNoneSelected => 'Geen geselecteerd';

  @override
  String get aiGenPleaseEnterDescription => 'Voer een beschrijving in voor je app';

  @override
  String get aiGenCreatingAppIcon => 'App-pictogram maken...';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'Er is een fout opgetreden: $message';
  }

  @override
  String get aiGenAppCreatedSuccessfully => 'App succesvol aangemaakt!';

  @override
  String get aiGenFailedToCreateApp => 'Kan app niet aanmaken';

  @override
  String get aiGenErrorWhileCreatingApp => 'Er is een fout opgetreden bij het aanmaken van de app';

  @override
  String get aiGenFailedToGenerateApp => 'Kan app niet genereren. Probeer het opnieuw.';

  @override
  String get aiGenFailedToRegenerateIcon => 'Kan pictogram niet opnieuw genereren';

  @override
  String get aiGenPleaseGenerateAppFirst => 'Genereer eerst een app';

  @override
  String get xHandleTitle => 'Wat is je X-handle?';

  @override
  String get xHandleDescription => 'We trainen je Omi-kloon voor\nop basis van de activiteit van je account';

  @override
  String get xHandleHint => '@nikshevchenko';

  @override
  String get xHandlePleaseEnter => 'Voer je X-handle in';

  @override
  String get xHandlePleaseEnterValid => 'Voer een geldige X-handle in';

  @override
  String get nextButton => 'Volgende';

  @override
  String get connectOmiDevice => 'Omi-apparaat verbinden';

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'Je schakelt je Onbeperkt Plan over naar het $title. Weet je zeker dat je wilt doorgaan?';
  }

  @override
  String get planUpgradeScheduledMessage =>
      'Upgrade gepland! Je maandelijkse abonnement loopt door tot het einde van je factureringsperiode en schakelt dan automatisch over naar jaarlijks.';

  @override
  String get couldNotSchedulePlanChange => 'Kon planwijziging niet plannen. Probeer opnieuw.';

  @override
  String get subscriptionReactivatedDefault =>
      'Je abonnement is opnieuw geactiveerd! Geen kosten nu - je wordt gefactureerd aan het einde van je huidige periode.';

  @override
  String get subscriptionSuccessfulCharged =>
      'Abonnement succesvol! Je bent gefactureerd voor de nieuwe factureringsperiode.';

  @override
  String get couldNotProcessSubscription => 'Kon abonnement niet verwerken. Probeer opnieuw.';

  @override
  String get couldNotLaunchUpgradePage => 'Kon upgradepagina niet openen. Probeer opnieuw.';

  @override
  String get transcriptionJsonPlaceholder => 'Plak hier je JSON-configuratie...';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get pricePlaceholder => '0,00';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'Fout bij openen bestandskiezer: $message';
  }

  @override
  String importErrorGeneric(String error) {
    return 'Fout: $error';
  }

  @override
  String get mergeConversationsSuccessTitle => 'Gesprekken succesvol samengevoegd';

  @override
  String mergeConversationsSuccessBody(int count) {
    return '$count gesprekken zijn succesvol samengevoegd';
  }

  @override
  String get dailyReflectionNotificationTitle => 'Tijd voor dagelijkse reflectie';

  @override
  String get dailyReflectionNotificationBody => 'Vertel me over je dag';

  @override
  String get actionItemReminderTitle => 'Omi-herinnering';

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName losgekoppeld';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'Maak opnieuw verbinding om uw $deviceName te blijven gebruiken.';
  }

  @override
  String get onboardingSignIn => 'Inloggen';

  @override
  String get onboardingYourName => 'Je naam';

  @override
  String get onboardingLanguage => 'Taal';

  @override
  String get onboardingPermissions => 'Machtigingen';

  @override
  String get onboardingComplete => 'Voltooid';

  @override
  String get onboardingWelcomeToOmi => 'Welkom bij Omi';

  @override
  String get onboardingTellUsAboutYourself => 'Vertel ons over jezelf';

  @override
  String get onboardingChooseYourPreference => 'Kies je voorkeur';

  @override
  String get onboardingGrantRequiredAccess => 'Verleen de vereiste toegang';

  @override
  String get onboardingYoureAllSet => 'Je bent klaar';

  @override
  String get searchTranscriptOrSummary => 'Zoeken in transcript of samenvatting...';

  @override
  String get myGoal => 'Mijn doel';

  @override
  String get appNotAvailable => 'Oeps! Het lijkt erop dat de app die je zoekt niet beschikbaar is.';

  @override
  String get failedToConnectTodoist => 'Verbinding met Todoist mislukt';

  @override
  String get failedToConnectAsana => 'Verbinding met Asana mislukt';

  @override
  String get failedToConnectGoogleTasks => 'Verbinding met Google Tasks mislukt';

  @override
  String get failedToConnectClickUp => 'Verbinding met ClickUp mislukt';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return 'Verbinding met $serviceName mislukt: $error';
  }

  @override
  String get successfullyConnectedTodoist => 'Succesvol verbonden met Todoist!';

  @override
  String get failedToConnectTodoistRetry => 'Verbinding met Todoist mislukt. Probeer het opnieuw.';

  @override
  String get successfullyConnectedAsana => 'Succesvol verbonden met Asana!';

  @override
  String get failedToConnectAsanaRetry => 'Verbinding met Asana mislukt. Probeer het opnieuw.';

  @override
  String get successfullyConnectedGoogleTasks => 'Succesvol verbonden met Google Tasks!';

  @override
  String get failedToConnectGoogleTasksRetry => 'Verbinding met Google Tasks mislukt. Probeer het opnieuw.';

  @override
  String get successfullyConnectedClickUp => 'Succesvol verbonden met ClickUp!';

  @override
  String get failedToConnectClickUpRetry => 'Verbinding met ClickUp mislukt. Probeer het opnieuw.';

  @override
  String get successfullyConnectedNotion => 'Succesvol verbonden met Notion!';

  @override
  String get failedToRefreshNotionStatus => 'Kan de Notion-verbindingsstatus niet vernieuwen.';

  @override
  String get successfullyConnectedGoogle => 'Succesvol verbonden met Google!';

  @override
  String get failedToRefreshGoogleStatus => 'Kan de Google-verbindingsstatus niet vernieuwen.';

  @override
  String get successfullyConnectedWhoop => 'Succesvol verbonden met Whoop!';

  @override
  String get failedToRefreshWhoopStatus => 'Kan de Whoop-verbindingsstatus niet vernieuwen.';

  @override
  String get successfullyConnectedGitHub => 'Succesvol verbonden met GitHub!';

  @override
  String get failedToRefreshGitHubStatus => 'Kan de GitHub-verbindingsstatus niet vernieuwen.';

  @override
  String get authFailedToSignInWithGoogle => 'Aanmelden met Google mislukt, probeer het opnieuw.';

  @override
  String get authenticationFailed => 'Authenticatie mislukt. Probeer het opnieuw.';

  @override
  String get authFailedToSignInWithApple => 'Aanmelden met Apple mislukt, probeer het opnieuw.';

  @override
  String get authFailedToRetrieveToken => 'Kon Firebase-token niet ophalen, probeer het opnieuw.';

  @override
  String get authUnexpectedErrorFirebase => 'Onverwachte fout bij aanmelden, Firebase-fout, probeer het opnieuw.';

  @override
  String get authUnexpectedError => 'Onverwachte fout bij aanmelden, probeer het opnieuw';

  @override
  String get authFailedToLinkGoogle => 'Koppelen met Google mislukt, probeer het opnieuw.';

  @override
  String get authFailedToLinkApple => 'Koppelen met Apple mislukt, probeer het opnieuw.';

  @override
  String get onboardingBluetoothRequired => 'Bluetooth-toestemming is vereist om verbinding te maken met uw apparaat.';

  @override
  String get onboardingBluetoothDeniedSystemPrefs =>
      'Bluetooth-toestemming geweigerd. Verleen toestemming in Systeemvoorkeuren.';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'Bluetooth-toestemmingsstatus: $status. Controleer Systeemvoorkeuren.';
  }

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'Kan Bluetooth-toestemming niet controleren: $error';
  }

  @override
  String get onboardingNotificationDeniedSystemPrefs =>
      'Meldingstoestemming geweigerd. Verleen toestemming in Systeemvoorkeuren.';

  @override
  String get onboardingNotificationDeniedNotifications =>
      'Meldingstoestemming geweigerd. Verleen toestemming in Systeemvoorkeuren > Meldingen.';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return 'Meldingstoestemmingsstatus: $status. Controleer Systeemvoorkeuren.';
  }

  @override
  String onboardingFailedCheckNotification(String error) {
    return 'Kan meldingstoestemming niet controleren: $error';
  }

  @override
  String get onboardingLocationGrantInSettings =>
      'Verleen locatietoestemming in Instellingen > Privacy en beveiliging > Locatievoorzieningen';

  @override
  String get onboardingMicrophoneRequired => 'Microfoontoestemming is vereist voor opname.';

  @override
  String get onboardingMicrophoneDenied =>
      'Microfoontoestemming geweigerd. Verleen toestemming in Systeemvoorkeuren > Privacy en beveiliging > Microfoon.';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'Microfoontoestemmingsstatus: $status. Controleer Systeemvoorkeuren.';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'Kan microfoontoestemming niet controleren: $error';
  }

  @override
  String get onboardingScreenCaptureRequired => 'Schermopnametoestemming is vereist voor systeemaudio-opname.';

  @override
  String get onboardingScreenCaptureDenied =>
      'Schermopnametoestemming geweigerd. Verleen toestemming in Systeemvoorkeuren > Privacy en beveiliging > Schermopname.';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return 'Schermopnametoestemmingsstatus: $status. Controleer Systeemvoorkeuren.';
  }

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return 'Kan schermopnametoestemming niet controleren: $error';
  }

  @override
  String get onboardingAccessibilityRequired =>
      'Toegankelijkheidstoestemming is vereist voor het detecteren van browservergaderingen.';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'Toegankelijkheidstoestemmingsstatus: $status. Controleer Systeemvoorkeuren.';
  }

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'Kan toegankelijkheidstoestemming niet controleren: $error';
  }

  @override
  String get msgCameraNotAvailable => 'Camera-opname is niet beschikbaar op dit platform';

  @override
  String get msgCameraPermissionDenied => 'Cameratoestemming geweigerd. Geef alstublieft toegang tot de camera';

  @override
  String msgCameraAccessError(String error) {
    return 'Fout bij toegang tot camera: $error';
  }

  @override
  String get msgPhotoError => 'Fout bij het maken van foto. Probeer het opnieuw.';

  @override
  String get msgMaxImagesLimit => 'U kunt maximaal 4 afbeeldingen selecteren';

  @override
  String msgFilePickerError(String error) {
    return 'Fout bij openen bestandskiezer: $error';
  }

  @override
  String msgSelectImagesError(String error) {
    return 'Fout bij selecteren van afbeeldingen: $error';
  }

  @override
  String get msgPhotosPermissionDenied =>
      'Fototoestemming geweigerd. Geef alstublieft toegang tot foto\'s om afbeeldingen te selecteren';

  @override
  String get msgSelectImagesGenericError => 'Fout bij selecteren van afbeeldingen. Probeer het opnieuw.';

  @override
  String get msgMaxFilesLimit => 'U kunt maximaal 4 bestanden selecteren';

  @override
  String msgSelectFilesError(String error) {
    return 'Fout bij selecteren van bestanden: $error';
  }

  @override
  String get msgSelectFilesGenericError => 'Fout bij selecteren van bestanden. Probeer het opnieuw.';

  @override
  String get msgUploadFileFailed => 'Bestand uploaden mislukt, probeer het later opnieuw';

  @override
  String get msgReadingMemories => 'Je herinneringen lezen...';

  @override
  String get msgLearningMemories => 'Leren van je herinneringen...';

  @override
  String get msgUploadAttachedFileFailed => 'Uploaden van bijgevoegd bestand mislukt.';

  @override
  String captureRecordingError(String error) {
    return 'Er is een fout opgetreden tijdens de opname: $error';
  }

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return 'Opname gestopt: $reason. Mogelijk moet u externe beeldschermen opnieuw aansluiten of de opname opnieuw starten.';
  }

  @override
  String get captureMicrophonePermissionRequired => 'Microfoontoestemming vereist';

  @override
  String get captureMicrophonePermissionInSystemPreferences => 'Geef microfoontoestemming in Systeemvoorkeuren';

  @override
  String get captureScreenRecordingPermissionRequired => 'Schermopnametoestemming vereist';

  @override
  String get captureDisplayDetectionFailed => 'Schermdetectie mislukt. Opname gestopt.';

  @override
  String get devModeInvalidAudioBytesWebhookUrl => 'Ongeldige webhook-URL voor audiobytes';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl => 'Ongeldige webhook-URL voor realtime-transcriptie';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl => 'Ongeldige webhook-URL voor aangemaakte conversatie';

  @override
  String get devModeInvalidDaySummaryWebhookUrl => 'Ongeldige webhook-URL voor dagsamenvatting';

  @override
  String get devModeSettingsSaved => 'Instellingen opgeslagen!';

  @override
  String get voiceFailedToTranscribe => 'Audiotranscriptie mislukt';

  @override
  String get locationPermissionRequired => 'Locatiemachtiging vereist';

  @override
  String get locationPermissionContent =>
      'Snelle overdracht vereist locatietoestemming om de WiFi-verbinding te verifiëren. Verleen alstublieft locatietoestemming om door te gaan.';

  @override
  String get pdfTranscriptExport => 'Transcript exporteren';

  @override
  String get pdfConversationExport => 'Gesprek exporteren';

  @override
  String pdfTitleLabel(String title) {
    return 'Titel: $title';
  }

  @override
  String get conversationNewIndicator => 'Nieuw 🚀';

  @override
  String conversationPhotosCount(int count) {
    return '$count foto\'s';
  }

  @override
  String get mergingStatus => 'Samenvoegen...';

  @override
  String timeSecsSingular(int count) {
    return '$count sec';
  }

  @override
  String timeSecsPlural(int count) {
    return '$count sec';
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
    return '$mins min $secs sec';
  }

  @override
  String timeHourSingular(int count) {
    return '$count uur';
  }

  @override
  String timeHoursPlural(int count) {
    return '$count uur';
  }

  @override
  String timeHoursAndMins(int hours, int mins) {
    return '$hours uur $mins min';
  }

  @override
  String timeDaySingular(int count) {
    return '$count dag';
  }

  @override
  String timeDaysPlural(int count) {
    return '$count dagen';
  }

  @override
  String timeDaysAndHours(int days, int hours) {
    return '$days dagen $hours uur';
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
    return '${count}u';
  }

  @override
  String timeCompactHoursAndMins(int hours, int mins) {
    return '${hours}u ${mins}m';
  }

  @override
  String get moveToFolder => 'Verplaatsen naar map';

  @override
  String get noFoldersAvailable => 'Geen mappen beschikbaar';

  @override
  String get newFolder => 'Nieuwe map';

  @override
  String get color => 'Kleur';

  @override
  String get waitingForDevice => 'Wachten op apparaat...';

  @override
  String get saySomething => 'Zeg iets...';

  @override
  String get initialisingSystemAudio => 'Systeemaudio initialiseren';

  @override
  String get stopRecording => 'Opname stoppen';

  @override
  String get continueRecording => 'Opname voortzetten';

  @override
  String get initialisingRecorder => 'Recorder initialiseren';

  @override
  String get pauseRecording => 'Opname pauzeren';

  @override
  String get resumeRecording => 'Opname hervatten';

  @override
  String get noDailyRecapsYet => 'Nog geen dagelijkse samenvattingen';

  @override
  String get dailyRecapsDescription => 'Uw dagelijkse samenvattingen verschijnen hier zodra ze zijn gegenereerd';

  @override
  String get chooseTransferMethod => 'Kies overdrachtsmethode';

  @override
  String get fastTransferSpeed => '~150 KB/s via WiFi';

  @override
  String largeTimeGapDetected(String gap) {
    return 'Groot tijdsverschil gedetecteerd ($gap)';
  }

  @override
  String largeTimeGapsDetected(String gaps) {
    return 'Grote tijdsverschillen gedetecteerd ($gaps)';
  }

  @override
  String get deviceDoesNotSupportWifiSwitchingToBle =>
      'Apparaat ondersteunt geen WiFi-synchronisatie, overschakelen naar Bluetooth';

  @override
  String get appleHealthNotAvailable => 'Apple Health is niet beschikbaar op dit apparaat';

  @override
  String get downloadAudio => 'Audio downloaden';

  @override
  String get audioDownloadSuccess => 'Audio succesvol gedownload';

  @override
  String get audioDownloadFailed => 'Audio downloaden mislukt';

  @override
  String get downloadingAudio => 'Audio downloaden...';

  @override
  String get shareAudio => 'Audio delen';

  @override
  String get preparingAudio => 'Audio voorbereiden';

  @override
  String get gettingAudioFiles => 'Audiobestanden ophalen...';

  @override
  String get downloadingAudioProgress => 'Audio downloaden';

  @override
  String get processingAudio => 'Audio verwerken';

  @override
  String get combiningAudioFiles => 'Audiobestanden combineren...';

  @override
  String get audioReady => 'Audio klaar';

  @override
  String get openingShareSheet => 'Deelvenster openen...';

  @override
  String get audioShareFailed => 'Delen mislukt';

  @override
  String get dailyRecaps => 'Dagelijkse Samenvattingen';

  @override
  String get removeFilter => 'Filter Verwijderen';

  @override
  String get categoryConversationAnalysis => 'Gesprekanalyse';

  @override
  String get categoryPersonalityClone => 'Persoonlijkheidskloon';

  @override
  String get categoryHealth => 'Gezondheid';

  @override
  String get categoryEducation => 'Onderwijs';

  @override
  String get categoryCommunication => 'Communicatie';

  @override
  String get categoryEmotionalSupport => 'Emotionele ondersteuning';

  @override
  String get categoryProductivity => 'Productiviteit';

  @override
  String get categoryEntertainment => 'Entertainment';

  @override
  String get categoryFinancial => 'Financiën';

  @override
  String get categoryTravel => 'Reizen';

  @override
  String get categorySafety => 'Veiligheid';

  @override
  String get categoryShopping => 'Winkelen';

  @override
  String get categorySocial => 'Sociaal';

  @override
  String get categoryNews => 'Nieuws';

  @override
  String get categoryUtilities => 'Hulpmiddelen';

  @override
  String get categoryOther => 'Overig';

  @override
  String get capabilityChat => 'Chat';

  @override
  String get capabilityConversations => 'Gesprekken';

  @override
  String get capabilityExternalIntegration => 'Externe integratie';

  @override
  String get capabilityNotification => 'Melding';

  @override
  String get triggerAudioBytes => 'Audiobytes';

  @override
  String get triggerConversationCreation => 'Gesprek aanmaken';

  @override
  String get triggerTranscriptProcessed => 'Transcript verwerkt';

  @override
  String get actionCreateConversations => 'Gesprekken aanmaken';

  @override
  String get actionCreateMemories => 'Herinneringen aanmaken';

  @override
  String get actionReadConversations => 'Gesprekken lezen';

  @override
  String get actionReadMemories => 'Herinneringen lezen';

  @override
  String get actionReadTasks => 'Taken lezen';

  @override
  String get scopeUserName => 'Gebruikersnaam';

  @override
  String get scopeUserFacts => 'Gebruikersgegevens';

  @override
  String get scopeUserConversations => 'Gebruikersgesprekken';

  @override
  String get scopeUserChat => 'Gebruikerschat';

  @override
  String get capabilitySummary => 'Samenvatting';

  @override
  String get capabilityFeatured => 'Uitgelicht';

  @override
  String get capabilityTasks => 'Taken';

  @override
  String get capabilityIntegrations => 'Integraties';

  @override
  String get categoryPersonalityClones => 'Persoonlijkheidsklonen';

  @override
  String get categoryProductivityLifestyle => 'Productiviteit & levensstijl';

  @override
  String get categorySocialEntertainment => 'Sociaal & entertainment';

  @override
  String get categoryProductivityTools => 'Productiviteitstools';

  @override
  String get categoryPersonalWellness => 'Persoonlijk welzijn';

  @override
  String get rating => 'Beoordeling';

  @override
  String get categories => 'Categorieën';

  @override
  String get sortBy => 'Sorteren';

  @override
  String get highestRating => 'Hoogste beoordeling';

  @override
  String get lowestRating => 'Laagste beoordeling';

  @override
  String get resetFilters => 'Filters resetten';

  @override
  String get applyFilters => 'Filters toepassen';

  @override
  String get mostInstalls => 'Meeste installaties';

  @override
  String get couldNotOpenUrl => 'Kan de URL niet openen. Probeer het opnieuw.';

  @override
  String get newTask => 'Nieuwe taak';

  @override
  String get viewAll => 'Alles bekijken';

  @override
  String get addTask => 'Taak toevoegen';

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
  String get audioPlaybackUnavailable => 'Audiobestand is niet beschikbaar voor afspelen';

  @override
  String get audioPlaybackFailed => 'Kan audio niet afspelen. Het bestand is mogelijk beschadigd of ontbreekt.';

  @override
  String get connectionGuide => 'Verbindingshandleiding';

  @override
  String get iveDoneThis => 'Dit heb ik gedaan';

  @override
  String get pairNewDevice => 'Nieuw apparaat koppelen';

  @override
  String get dontSeeYourDevice => 'Zie je je apparaat niet?';

  @override
  String get reportAnIssue => 'Een probleem melden';

  @override
  String get pairingTitleOmi => 'Zet Omi aan';

  @override
  String get pairingDescOmi => 'Houd het apparaat ingedrukt totdat het trilt om het in te schakelen.';

  @override
  String get pairingTitleOmiDevkit => 'Zet Omi DevKit in koppelingsmodus';

  @override
  String get pairingDescOmiDevkit =>
      'Druk eenmaal op de knop om in te schakelen. De LED knippert paars in koppelingsmodus.';

  @override
  String get pairingTitleOmiGlass => 'Zet Omi Glass aan';

  @override
  String get pairingDescOmiGlass => 'Houd de zijknop 3 seconden ingedrukt om in te schakelen.';

  @override
  String get pairingTitlePlaudNote => 'Zet Plaud Note in koppelingsmodus';

  @override
  String get pairingDescPlaudNote =>
      'Houd de zijknop 2 seconden ingedrukt. De rode LED knippert wanneer het klaar is om te koppelen.';

  @override
  String get pairingTitleBee => 'Zet Bee in koppelingsmodus';

  @override
  String get pairingDescBee => 'Druk 5 keer achter elkaar op de knop. Het lampje gaat blauw en groen knipperen.';

  @override
  String get pairingTitleLimitless => 'Zet Limitless in koppelingsmodus';

  @override
  String get pairingDescLimitless =>
      'Wanneer een lampje brandt, druk eenmaal en houd dan ingedrukt totdat het apparaat een roze licht toont, laat dan los.';

  @override
  String get pairingTitleFriendPendant => 'Zet Friend Pendant in koppelingsmodus';

  @override
  String get pairingDescFriendPendant =>
      'Druk op de knop op de hanger om deze in te schakelen. Het gaat automatisch naar de koppelingsmodus.';

  @override
  String get pairingTitleFieldy => 'Zet Fieldy in koppelingsmodus';

  @override
  String get pairingDescFieldy => 'Houd het apparaat ingedrukt totdat het lampje verschijnt om het in te schakelen.';

  @override
  String get pairingTitleAppleWatch => 'Verbind Apple Watch';

  @override
  String get pairingDescAppleWatch =>
      'Installeer en open de Omi-app op je Apple Watch en tik vervolgens op Verbinden in de app.';

  @override
  String get pairingTitleNeoOne => 'Zet Neo One in koppelingsmodus';

  @override
  String get pairingDescNeoOne =>
      'Houd de aan-/uitknop ingedrukt totdat de LED knippert. Het apparaat is dan vindbaar.';
}
