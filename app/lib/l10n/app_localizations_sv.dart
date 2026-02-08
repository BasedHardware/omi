// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Swedish (`sv`).
class AppLocalizationsSv extends AppLocalizations {
  AppLocalizationsSv([String locale = 'sv']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'Konversation';

  @override
  String get transcriptTab => 'Transkription';

  @override
  String get actionItemsTab => 'Åtgärder';

  @override
  String get deleteConversationTitle => 'Ta bort konversation?';

  @override
  String get deleteConversationMessage =>
      'Är du säker på att du vill ta bort denna konversation? Detta kan inte ångras.';

  @override
  String get confirm => 'Bekräfta';

  @override
  String get cancel => 'Avbryt';

  @override
  String get ok => 'OK';

  @override
  String get delete => 'Radera';

  @override
  String get add => 'Lägg till';

  @override
  String get update => 'Uppdatera';

  @override
  String get save => 'Spara';

  @override
  String get edit => 'Redigera';

  @override
  String get close => 'Stäng';

  @override
  String get clear => 'Rensa';

  @override
  String get copyTranscript => 'Kopiera transkription';

  @override
  String get copySummary => 'Kopiera sammanfattning';

  @override
  String get testPrompt => 'Testa prompt';

  @override
  String get reprocessConversation => 'Bearbeta konversation igen';

  @override
  String get deleteConversation => 'Radera konversation';

  @override
  String get contentCopied => 'Innehåll kopierat till urklipp';

  @override
  String get failedToUpdateStarred => 'Det gick inte att uppdatera stjärnstatus.';

  @override
  String get conversationUrlNotShared => 'Konversationens URL kunde inte delas.';

  @override
  String get errorProcessingConversation => 'Fel vid bearbetning av konversation. Försök igen senare.';

  @override
  String get noInternetConnection => 'Ingen internetanslutning';

  @override
  String get unableToDeleteConversation => 'Kan inte ta bort konversation';

  @override
  String get somethingWentWrong => 'Något gick fel! Försök igen senare.';

  @override
  String get copyErrorMessage => 'Kopiera felmeddelande';

  @override
  String get errorCopied => 'Felmeddelande kopierat till urklipp';

  @override
  String get remaining => 'Återstår';

  @override
  String get loading => 'Läser in...';

  @override
  String get loadingDuration => 'Läser in längd...';

  @override
  String secondsCount(int count) {
    return '$count sekunder';
  }

  @override
  String get people => 'Personer';

  @override
  String get addNewPerson => 'Lägg till ny person';

  @override
  String get editPerson => 'Redigera person';

  @override
  String get createPersonHint => 'Skapa en ny person och träna Omi att känna igen deras röst också!';

  @override
  String get speechProfile => 'Talprofil';

  @override
  String sampleNumber(int number) {
    return 'Exempel $number';
  }

  @override
  String get settings => 'Inställningar';

  @override
  String get language => 'Språk';

  @override
  String get selectLanguage => 'Välj språk';

  @override
  String get deleting => 'Tar bort...';

  @override
  String get pleaseCompleteAuthentication =>
      'Slutför autentiseringen i din webbläsare. När du är klar, återvänd till appen.';

  @override
  String get failedToStartAuthentication => 'Det gick inte att starta autentisering';

  @override
  String get importStarted => 'Import har startat! Du får ett meddelande när den är klar.';

  @override
  String get failedToStartImport => 'Det gick inte att starta import. Försök igen.';

  @override
  String get couldNotAccessFile => 'Kunde inte komma åt den valda filen';

  @override
  String get askOmi => 'Fråga Omi';

  @override
  String get done => 'Klar';

  @override
  String get disconnected => 'Frånkopplad';

  @override
  String get searching => 'Söker...';

  @override
  String get connectDevice => 'Anslut enhet';

  @override
  String get monthlyLimitReached => 'Du har nått din månatliga gräns.';

  @override
  String get checkUsage => 'Kontrollera användning';

  @override
  String get syncingRecordings => 'Synkroniserar inspelningar';

  @override
  String get recordingsToSync => 'Inspelningar att synkronisera';

  @override
  String get allCaughtUp => 'Allt är klart';

  @override
  String get sync => 'Synkronisera';

  @override
  String get pendantUpToDate => 'Hängsmycket är uppdaterat';

  @override
  String get allRecordingsSynced => 'Alla inspelningar är synkroniserade';

  @override
  String get syncingInProgress => 'Synkronisering pågår';

  @override
  String get readyToSync => 'Redo att synkronisera';

  @override
  String get tapSyncToStart => 'Tryck på Synkronisera för att starta';

  @override
  String get pendantNotConnected => 'Hängsmycket är inte anslutet. Anslut för att synkronisera.';

  @override
  String get everythingSynced => 'Allt är redan synkroniserat.';

  @override
  String get recordingsNotSynced => 'Du har inspelningar som inte är synkroniserade ännu.';

  @override
  String get syncingBackground => 'Vi fortsätter synkronisera dina inspelningar i bakgrunden.';

  @override
  String get noConversationsYet => 'Inga konversationer än';

  @override
  String get noStarredConversations => 'Inga stjärnmärkta konversationer';

  @override
  String get starConversationHint =>
      'För att stjärnmärka en konversation, öppna den och tryck på stjärnikonen i sidhuvudet.';

  @override
  String get searchConversations => 'Sök konversationer...';

  @override
  String selectedCount(int count, Object s) {
    return '$count valda';
  }

  @override
  String get merge => 'Slå ihop';

  @override
  String get mergeConversations => 'Slå ihop konversationer';

  @override
  String mergeConversationsMessage(int count) {
    return 'Detta kommer att kombinera $count konversationer till en. Allt innehåll kommer att slås ihop och genereras på nytt.';
  }

  @override
  String get mergingInBackground => 'Slår ihop i bakgrunden. Detta kan ta en stund.';

  @override
  String get failedToStartMerge => 'Det gick inte att starta ihopslagning';

  @override
  String get askAnything => 'Fråga vad som helst';

  @override
  String get noMessagesYet => 'Inga meddelanden ännu!\nVarför inte starta en konversation?';

  @override
  String get deletingMessages => 'Raderar dina meddelanden från Omis minne...';

  @override
  String get messageCopied => '✨ Meddelande kopierat till urklipp';

  @override
  String get cannotReportOwnMessage => 'Du kan inte rapportera dina egna meddelanden.';

  @override
  String get reportMessage => 'Rapportera meddelande';

  @override
  String get reportMessageConfirm => 'Är du säker på att du vill rapportera detta meddelande?';

  @override
  String get messageReported => 'Meddelande rapporterat.';

  @override
  String get thankYouFeedback => 'Tack för din återkoppling!';

  @override
  String get clearChat => 'Rensa chatt';

  @override
  String get clearChatConfirm => 'Är du säker på att du vill rensa chatten? Detta kan inte ångras.';

  @override
  String get maxFilesLimit => 'Du kan bara ladda upp 4 filer åt gången';

  @override
  String get chatWithOmi => 'Chatta med Omi';

  @override
  String get apps => 'Appar';

  @override
  String get noAppsFound => 'Inga appar hittades';

  @override
  String get tryAdjustingSearch => 'Prova att justera din sökning eller filter';

  @override
  String get createYourOwnApp => 'Skapa din egen app';

  @override
  String get buildAndShareApp => 'Bygg och dela din anpassade app';

  @override
  String get searchApps => 'Sök appar...';

  @override
  String get myApps => 'Mina appar';

  @override
  String get installedApps => 'Installerade appar';

  @override
  String get unableToFetchApps => 'Kunde inte hämta appar :(\n\nKontrollera din internetanslutning och försök igen.';

  @override
  String get aboutOmi => 'Om Omi';

  @override
  String get privacyPolicy => 'Integritetspolicy';

  @override
  String get visitWebsite => 'Besök webbplatsen';

  @override
  String get helpOrInquiries => 'Hjälp eller frågor?';

  @override
  String get joinCommunity => 'Gå med i communityn!';

  @override
  String get membersAndCounting => '8000+ medlemmar och ökar.';

  @override
  String get deleteAccountTitle => 'Ta bort konto';

  @override
  String get deleteAccountConfirm => 'Är du säker på att du vill ta bort ditt konto?';

  @override
  String get cannotBeUndone => 'Detta kan inte ångras.';

  @override
  String get allDataErased => 'Alla dina minnen och konversationer kommer att raderas permanent.';

  @override
  String get appsDisconnected => 'Dina appar och integrationer kommer att kopplas från omedelbart.';

  @override
  String get exportBeforeDelete =>
      'Du kan exportera dina data innan du tar bort ditt konto, men när det väl är borttaget kan det inte återställas.';

  @override
  String get deleteAccountCheckbox =>
      'Jag förstår att borttagning av mitt konto är permanent och att all data, inklusive minnen och konversationer, kommer att förloras och inte kan återställas.';

  @override
  String get areYouSure => 'Är du säker?';

  @override
  String get deleteAccountFinal =>
      'Denna åtgärd är oåterkallelig och kommer permanent ta bort ditt konto och all associerad data. Är du säker på att du vill fortsätta?';

  @override
  String get deleteNow => 'Ta bort nu';

  @override
  String get goBack => 'Gå tillbaka';

  @override
  String get checkBoxToConfirm =>
      'Markera kryssrutan för att bekräfta att du förstår att borttagning av ditt konto är permanent och oåterkalleligt.';

  @override
  String get profile => 'Profil';

  @override
  String get name => 'Namn';

  @override
  String get email => 'E-post';

  @override
  String get customVocabulary => 'Anpassat Ordförråd';

  @override
  String get identifyingOthers => 'Identifiering av Andra';

  @override
  String get paymentMethods => 'Betalningsmetoder';

  @override
  String get conversationDisplay => 'Konversationsvisning';

  @override
  String get dataPrivacy => 'Dataintegritet';

  @override
  String get userId => 'Användar-ID';

  @override
  String get notSet => 'Inte inställd';

  @override
  String get userIdCopied => 'Användar-ID kopierat till urklipp';

  @override
  String get systemDefault => 'Systemstandard';

  @override
  String get planAndUsage => 'Plan och användning';

  @override
  String get offlineSync => 'Offlinesynkronisering';

  @override
  String get deviceSettings => 'Enhetsinställningar';

  @override
  String get integrations => 'Integrationer';

  @override
  String get feedbackBug => 'Återkoppling / Bugg';

  @override
  String get helpCenter => 'Hjälpcenter';

  @override
  String get developerSettings => 'Utvecklarinställningar';

  @override
  String get getOmiForMac => 'Hämta Omi för Mac';

  @override
  String get referralProgram => 'Hänvisningsprogram';

  @override
  String get signOut => 'Logga Ut';

  @override
  String get appAndDeviceCopied => 'App- och enhetsdetaljer kopierade';

  @override
  String get wrapped2025 => 'Årssummering 2025';

  @override
  String get yourPrivacyYourControl => 'Din integritet, din kontroll';

  @override
  String get privacyIntro =>
      'På Omi är vi engagerade i att skydda din integritet. Denna sida låter dig kontrollera hur din data lagras och används.';

  @override
  String get learnMore => 'Läs mer...';

  @override
  String get dataProtectionLevel => 'Dataskyddsnivå';

  @override
  String get dataProtectionDesc =>
      'Din data är säkrad som standard med stark kryptering. Granska dina inställningar och framtida integritetsalternativ nedan.';

  @override
  String get appAccess => 'Appåtkomst';

  @override
  String get appAccessDesc =>
      'Följande appar kan komma åt din data. Tryck på en app för att hantera dess behörigheter.';

  @override
  String get noAppsExternalAccess => 'Inga installerade appar har extern åtkomst till din data.';

  @override
  String get deviceName => 'Enhetsnamn';

  @override
  String get deviceId => 'Enhets-ID';

  @override
  String get firmware => 'Firmware';

  @override
  String get sdCardSync => 'SD-kort synkronisering';

  @override
  String get hardwareRevision => 'Hårdvarurevision';

  @override
  String get modelNumber => 'Modellnummer';

  @override
  String get manufacturer => 'Tillverkare';

  @override
  String get doubleTap => 'Dubbeltryck';

  @override
  String get ledBrightness => 'LED-ljusstyrka';

  @override
  String get micGain => 'Mikrofonförstärkning';

  @override
  String get disconnect => 'Koppla från';

  @override
  String get forgetDevice => 'Glöm enhet';

  @override
  String get chargingIssues => 'Laddningsproblem';

  @override
  String get disconnectDevice => 'Koppla från enhet';

  @override
  String get unpairDevice => 'Koppla bort enhet';

  @override
  String get unpairAndForget => 'Koppla bort och glöm enhet';

  @override
  String get deviceDisconnectedMessage => 'Din Omi har kopplats från 😔';

  @override
  String get deviceUnpairedMessage =>
      'Enhet bortkopplad. Gå till Inställningar > Bluetooth och glöm enheten för att slutföra bortkopplingen.';

  @override
  String get unpairDialogTitle => 'Koppla bort enhet';

  @override
  String get unpairDialogMessage =>
      'Detta kommer att koppla bort enheten så att den kan anslutas till en annan telefon. Du behöver gå till Inställningar > Bluetooth och glömma enheten för att slutföra processen.';

  @override
  String get deviceNotConnected => 'Enheten är inte ansluten';

  @override
  String get connectDeviceMessage =>
      'Anslut din Omi-enhet för att få tillgång till\nenhetsinställningar och anpassning';

  @override
  String get deviceInfoSection => 'Enhetsinformation';

  @override
  String get customizationSection => 'Anpassning';

  @override
  String get hardwareSection => 'Hårdvara';

  @override
  String get v2Undetected => 'V2 ej upptäckt';

  @override
  String get v2UndetectedMessage =>
      'Vi ser att du antingen har en V1-enhet eller att din enhet inte är ansluten. SD-kortsfunktionalitet är endast tillgänglig för V2-enheter.';

  @override
  String get endConversation => 'Avsluta konversation';

  @override
  String get pauseResume => 'Pausa/Återuppta';

  @override
  String get starConversation => 'Stjärnmärk konversation';

  @override
  String get doubleTapAction => 'Dubbeltrycksåtgärd';

  @override
  String get endAndProcess => 'Avsluta och bearbeta konversation';

  @override
  String get pauseResumeRecording => 'Pausa/Återuppta inspelning';

  @override
  String get starOngoing => 'Stjärnmärk pågående konversation';

  @override
  String get off => 'Av';

  @override
  String get max => 'Max';

  @override
  String get mute => 'Tysta';

  @override
  String get quiet => 'Tyst';

  @override
  String get normal => 'Normal';

  @override
  String get high => 'Hög';

  @override
  String get micGainDescMuted => 'Mikrofon är tystad';

  @override
  String get micGainDescLow => 'Mycket tyst - för högljudda miljöer';

  @override
  String get micGainDescModerate => 'Tyst - för måttligt buller';

  @override
  String get micGainDescNeutral => 'Neutral - balanserad inspelning';

  @override
  String get micGainDescSlightlyBoosted => 'Lätt förstärkt - normal användning';

  @override
  String get micGainDescBoosted => 'Förstärkt - för tysta miljöer';

  @override
  String get micGainDescHigh => 'Hög - för avlägsna eller svaga röster';

  @override
  String get micGainDescVeryHigh => 'Mycket hög - för mycket tysta källor';

  @override
  String get micGainDescMax => 'Maximum - använd med försiktighet';

  @override
  String get developerSettingsTitle => 'Utvecklarinställningar';

  @override
  String get saving => 'Sparar...';

  @override
  String get personaConfig => 'Konfigurera din AI-persona';

  @override
  String get beta => 'BETA';

  @override
  String get transcription => 'Transkription';

  @override
  String get transcriptionConfig => 'Konfigurera STT-leverantör';

  @override
  String get conversationTimeout => 'Konversations timeout';

  @override
  String get conversationTimeoutConfig => 'Ställ in när konversationer avslutas automatiskt';

  @override
  String get importData => 'Importera data';

  @override
  String get importDataConfig => 'Importera data från andra källor';

  @override
  String get debugDiagnostics => 'Felsökning och diagnostik';

  @override
  String get endpointUrl => 'Slutpunkts-URL';

  @override
  String get noApiKeys => 'Inga API-nycklar ännu';

  @override
  String get createKeyToStart => 'Skapa en nyckel för att komma igång';

  @override
  String get createKey => 'Skapa Nyckel';

  @override
  String get docs => 'Dokumentation';

  @override
  String get yourOmiInsights => 'Dina Omi-insikter';

  @override
  String get today => 'Idag';

  @override
  String get thisMonth => 'Denna månad';

  @override
  String get thisYear => 'Detta år';

  @override
  String get allTime => 'All tid';

  @override
  String get noActivityYet => 'Ingen aktivitet ännu';

  @override
  String get startConversationToSeeInsights =>
      'Starta en konversation med Omi\nför att se dina användningsinsikter här.';

  @override
  String get listening => 'Lyssnar';

  @override
  String get listeningSubtitle => 'Total tid Omi har aktivt lyssnat.';

  @override
  String get understanding => 'Förstår';

  @override
  String get understandingSubtitle => 'Ord förstådda från dina konversationer.';

  @override
  String get providing => 'Tillhandahåller';

  @override
  String get providingSubtitle => 'Åtgärder och anteckningar automatiskt fångade.';

  @override
  String get remembering => 'Kommer ihåg';

  @override
  String get rememberingSubtitle => 'Fakta och detaljer som kommer ihåg för dig.';

  @override
  String get unlimitedPlan => 'Obegränsad plan';

  @override
  String get managePlan => 'Hantera plan';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'Din plan kommer att avbrytas den $date.';
  }

  @override
  String renewsOn(String date) {
    return 'Din plan förnyas den $date.';
  }

  @override
  String get basicPlan => 'Gratisplan';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used av $limit min använt';
  }

  @override
  String get upgrade => 'Uppgradera';

  @override
  String get upgradeToUnlimited => 'Uppgradera till obegränsat';

  @override
  String basicPlanDesc(int limit) {
    return 'Din plan inkluderar $limit gratis minuter per månad. Uppgradera för att få obegränsat.';
  }

  @override
  String get shareStatsMessage => 'Delar mina Omi-statistik! (omi.me - din alltid påslagna AI-assistent)';

  @override
  String get sharePeriodToday => 'Idag har Omi:';

  @override
  String get sharePeriodMonth => 'Denna månad har Omi:';

  @override
  String get sharePeriodYear => 'Detta år har Omi:';

  @override
  String get sharePeriodAllTime => 'Hittills har Omi:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 Lyssnat i $minutes minuter';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 Förstått $words ord';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ Tillhandahållit $count insikter';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 Kommit ihåg $count minnen';
  }

  @override
  String get debugLogs => 'Felsökningsloggar';

  @override
  String get debugLogsAutoDelete => 'Raderas automatiskt efter 3 dagar.';

  @override
  String get debugLogsDesc => 'Hjälper till att diagnostisera problem';

  @override
  String get noLogFilesFound => 'Inga loggfiler hittades.';

  @override
  String get omiDebugLog => 'Omi felsökningslogg';

  @override
  String get logShared => 'Logg delad';

  @override
  String get selectLogFile => 'Välj loggfil';

  @override
  String get shareLogs => 'Dela loggar';

  @override
  String get debugLogCleared => 'Felsökningslogg rensad';

  @override
  String get exportStarted => 'Export har startat. Detta kan ta några sekunder...';

  @override
  String get exportAllData => 'Exportera all data';

  @override
  String get exportDataDesc => 'Exportera konversationer till en JSON-fil';

  @override
  String get exportedConversations => 'Exporterade konversationer från Omi';

  @override
  String get exportShared => 'Export delad';

  @override
  String get deleteKnowledgeGraphTitle => 'Ta bort kunskapsgraf?';

  @override
  String get deleteKnowledgeGraphMessage =>
      'Detta kommer att ta bort all härledd kunskapsgrafsdata (noder och kopplingar). Dina ursprungliga minnen förblir säkra. Grafen kommer att byggas om över tid eller vid nästa begäran.';

  @override
  String get knowledgeGraphDeleted => 'Kunskapsgraf raderad';

  @override
  String deleteGraphFailed(String error) {
    return 'Det gick inte att ta bort graf: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'Ta bort kunskapsgraf';

  @override
  String get deleteKnowledgeGraphDesc => 'Rensa alla noder och kopplingar';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'MCP-server';

  @override
  String get mcpServerDesc => 'Anslut AI-assistenter till din data';

  @override
  String get serverUrl => 'Server-URL';

  @override
  String get urlCopied => 'URL kopierad';

  @override
  String get apiKeyAuth => 'API-nyckel autentisering';

  @override
  String get header => 'Rubrik';

  @override
  String get authorizationBearer => 'Authorization: Bearer <key>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'Klient-ID';

  @override
  String get clientSecret => 'Klienthemlighet';

  @override
  String get useMcpApiKey => 'Använd din MCP API-nyckel';

  @override
  String get webhooks => 'Webhooks';

  @override
  String get conversationEvents => 'Konversationshändelser';

  @override
  String get newConversationCreated => 'Ny konversation skapad';

  @override
  String get realtimeTranscript => 'Realtidstranskription';

  @override
  String get transcriptReceived => 'Transkription mottagen';

  @override
  String get audioBytes => 'Ljudbytes';

  @override
  String get audioDataReceived => 'Ljuddata mottagen';

  @override
  String get intervalSeconds => 'Intervall (sekunder)';

  @override
  String get daySummary => 'Dagssammanfattning';

  @override
  String get summaryGenerated => 'Sammanfattning genererad';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'Lägg till i claude_desktop_config.json';

  @override
  String get copyConfig => 'Kopiera konfiguration';

  @override
  String get configCopied => 'Konfiguration kopierad till urklipp';

  @override
  String get listeningMins => 'Lyssnar (min)';

  @override
  String get understandingWords => 'Förstår (ord)';

  @override
  String get insights => 'Insikter';

  @override
  String get memories => 'Minnen';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '$used av $limit min använt denna månad';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '$used av $limit ord använt denna månad';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '$used av $limit insikter vunna denna månad';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return '$used av $limit minnen skapade denna månad';
  }

  @override
  String get visibility => 'Synlighet';

  @override
  String get visibilitySubtitle => 'Kontrollera vilka konversationer som visas i din lista';

  @override
  String get showShortConversations => 'Visa korta konversationer';

  @override
  String get showShortConversationsDesc => 'Visa konversationer som är kortare än tröskelvärdet';

  @override
  String get showDiscardedConversations => 'Visa kasserade konversationer';

  @override
  String get showDiscardedConversationsDesc => 'Inkludera konversationer markerade som kasserade';

  @override
  String get shortConversationThreshold => 'Kort konversationströskel';

  @override
  String get shortConversationThresholdSubtitle => 'Konversationer kortare än detta döljs om de inte aktiveras ovan';

  @override
  String get durationThreshold => 'Varaktighetströskel';

  @override
  String get durationThresholdDesc => 'Dölj konversationer kortare än detta';

  @override
  String minLabel(int count) {
    return '$count min';
  }

  @override
  String get customVocabularyTitle => 'Anpassat ordförråd';

  @override
  String get addWords => 'Lägg till ord';

  @override
  String get addWordsDesc => 'Namn, termer eller ovanliga ord';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'Connect';

  @override
  String get comingSoon => 'Kommer snart';

  @override
  String get integrationsFooter => 'Anslut dina appar för att visa data och mått i chatten.';

  @override
  String get completeAuthInBrowser => 'Slutför autentiseringen i din webbläsare. När du är klar, återvänd till appen.';

  @override
  String failedToStartAuth(String appName) {
    return 'Det gick inte att starta $appName-autentisering';
  }

  @override
  String disconnectAppTitle(String appName) {
    return 'Koppla från $appName?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'Är du säker på att du vill koppla från $appName? Du kan ansluta igen när som helst.';
  }

  @override
  String disconnectedFrom(String appName) {
    return 'Frånkopplad från $appName';
  }

  @override
  String get failedToDisconnect => 'Det gick inte att koppla från';

  @override
  String connectTo(String appName) {
    return 'Anslut till $appName';
  }

  @override
  String authAccessMessage(String appName) {
    return 'Du behöver auktorisera Omi för att komma åt din $appName-data. Detta öppnar din webbläsare för autentisering.';
  }

  @override
  String get continueAction => 'Fortsätt';

  @override
  String get languageTitle => 'Språk';

  @override
  String get primaryLanguage => 'Primärt språk';

  @override
  String get automaticTranslation => 'Automatisk översättning';

  @override
  String get detectLanguages => 'Upptäck 10+ språk';

  @override
  String get authorizeSavingRecordings => 'Auktorisera lagring av inspelningar';

  @override
  String get thanksForAuthorizing => 'Tack för auktoriseringen!';

  @override
  String get needYourPermission => 'Vi behöver ditt tillstånd';

  @override
  String get alreadyGavePermission =>
      'Du har redan gett oss tillstånd att spara dina inspelningar. Här är en påminnelse om varför vi behöver det:';

  @override
  String get wouldLikePermission => 'Vi skulle vilja ha ditt tillstånd att spara dina röstinspelningar. Här är varför:';

  @override
  String get improveSpeechProfile => 'Förbättra din röstprofil';

  @override
  String get improveSpeechProfileDesc =>
      'Vi använder inspelningar för att ytterligare träna och förbättra din personliga röstprofil.';

  @override
  String get trainFamilyProfiles => 'Träna profiler för vänner och familj';

  @override
  String get trainFamilyProfilesDesc =>
      'Dina inspelningar hjälper oss att känna igen och skapa profiler för dina vänner och familj.';

  @override
  String get enhanceTranscriptAccuracy => 'Förbättra transkriptionsnoggrannhet';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'När vår modell förbättras kan vi ge bättre transkriptionsresultat för dina inspelningar.';

  @override
  String get legalNotice =>
      'Juridiskt meddelande: Lagligheten av att spela in och lagra röstdata kan variera beroende på var du befinner dig och hur du använder denna funktion. Det är ditt ansvar att säkerställa efterlevnad av lokala lagar och förordningar.';

  @override
  String get alreadyAuthorized => 'Redan auktoriserad';

  @override
  String get authorize => 'Auktorisera';

  @override
  String get revokeAuthorization => 'Återkalla auktorisering';

  @override
  String get authorizationSuccessful => 'Auktorisering lyckades!';

  @override
  String get failedToAuthorize => 'Det gick inte att auktorisera. Försök igen.';

  @override
  String get authorizationRevoked => 'Auktorisering återkallad.';

  @override
  String get recordingsDeleted => 'Inspelningar raderade.';

  @override
  String get failedToRevoke => 'Det gick inte att återkalla auktorisering. Försök igen.';

  @override
  String get permissionRevokedTitle => 'Tillstånd återkallat';

  @override
  String get permissionRevokedMessage => 'Vill du att vi tar bort alla dina befintliga inspelningar också?';

  @override
  String get yes => 'Ja';

  @override
  String get editName => 'Redigera namn';

  @override
  String get howShouldOmiCallYou => 'Vad ska Omi kalla dig?';

  @override
  String get enterYourName => 'Ange ditt namn';

  @override
  String get nameCannotBeEmpty => 'Namnet kan inte vara tomt';

  @override
  String get nameUpdatedSuccessfully => 'Namnet har uppdaterats!';

  @override
  String get calendarSettings => 'Kalenderinställningar';

  @override
  String get calendarProviders => 'Kalenderleverantörer';

  @override
  String get macOsCalendar => 'macOS Kalender';

  @override
  String get connectMacOsCalendar => 'Anslut din lokala macOS-kalender';

  @override
  String get googleCalendar => 'Google Kalender';

  @override
  String get syncGoogleAccount => 'Synkronisera med ditt Google-konto';

  @override
  String get showMeetingsMenuBar => 'Visa kommande möten i menyraden';

  @override
  String get showMeetingsMenuBarDesc => 'Visa ditt nästa möte och tid tills det börjar i macOS menyraden';

  @override
  String get showEventsNoParticipants => 'Visa händelser utan deltagare';

  @override
  String get showEventsNoParticipantsDesc =>
      'När det är aktiverat visar Kommande händelser utan deltagare eller en videolänk.';

  @override
  String get yourMeetings => 'Dina möten';

  @override
  String get refresh => 'Uppdatera';

  @override
  String get noUpcomingMeetings => 'Inga kommande möten';

  @override
  String get checkingNextDays => 'Kontrollerar nästa 30 dagar';

  @override
  String get tomorrow => 'Imorgon';

  @override
  String get googleCalendarComingSoon => 'Google Kalender-integration kommer snart!';

  @override
  String connectedAsUser(String userId) {
    return 'Ansluten som användare: $userId';
  }

  @override
  String get defaultWorkspace => 'Standardarbetsyta';

  @override
  String get tasksCreatedInWorkspace => 'Uppgifter skapas i denna arbetsyta';

  @override
  String get defaultProjectOptional => 'Standardprojekt (valfritt)';

  @override
  String get leaveUnselectedTasks => 'Lämna omarkerad för att skapa uppgifter utan projekt';

  @override
  String get noProjectsInWorkspace => 'Inga projekt hittades i denna arbetsyta';

  @override
  String get conversationTimeoutDesc =>
      'Välj hur länge du vill vänta i tystnad innan en konversation avslutas automatiskt:';

  @override
  String get timeout2Minutes => '2 minuter';

  @override
  String get timeout2MinutesDesc => 'Avsluta konversation efter 2 minuters tystnad';

  @override
  String get timeout5Minutes => '5 minuter';

  @override
  String get timeout5MinutesDesc => 'Avsluta konversation efter 5 minuters tystnad';

  @override
  String get timeout10Minutes => '10 minuter';

  @override
  String get timeout10MinutesDesc => 'Avsluta konversation efter 10 minuters tystnad';

  @override
  String get timeout30Minutes => '30 minuter';

  @override
  String get timeout30MinutesDesc => 'Avsluta konversation efter 30 minuters tystnad';

  @override
  String get timeout4Hours => '4 timmar';

  @override
  String get timeout4HoursDesc => 'Avsluta konversation efter 4 timmars tystnad';

  @override
  String get conversationEndAfterHours => 'Konversationer avslutas nu efter 4 timmars tystnad';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Konversationer avslutas nu efter $minutes minuters tystnad';
  }

  @override
  String get tellUsPrimaryLanguage => 'Berätta ditt primära språk';

  @override
  String get languageForTranscription =>
      'Ställ in ditt språk för skarpare transkriptioner och en personlig upplevelse.';

  @override
  String get singleLanguageModeInfo => 'Enspråksläge är aktiverat. Översättning är inaktiverad för högre noggrannhet.';

  @override
  String get searchLanguageHint => 'Sök språk efter namn eller kod';

  @override
  String get noLanguagesFound => 'Inga språk hittades';

  @override
  String get skip => 'Hoppa över';

  @override
  String languageSetTo(String language) {
    return 'Språk inställt på $language';
  }

  @override
  String get failedToSetLanguage => 'Det gick inte att ställa in språk';

  @override
  String appSettings(String appName) {
    return '$appName-inställningar';
  }

  @override
  String disconnectFromApp(String appName) {
    return 'Koppla från $appName?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'Detta tar bort din $appName-autentisering. Du måste ansluta igen för att använda den.';
  }

  @override
  String connectedToApp(String appName) {
    return 'Ansluten till $appName';
  }

  @override
  String get account => 'Konto';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Dina åtgärder kommer att synkroniseras till ditt $appName-konto';
  }

  @override
  String get defaultSpace => 'Standardutrymme';

  @override
  String get selectSpaceInWorkspace => 'Välj ett utrymme i din arbetsyta';

  @override
  String get noSpacesInWorkspace => 'Inga utrymmen hittades i denna arbetsyta';

  @override
  String get defaultList => 'Standardlista';

  @override
  String get tasksAddedToList => 'Uppgifter läggs till i denna lista';

  @override
  String get noListsInSpace => 'Inga listor hittades i detta utrymme';

  @override
  String failedToLoadRepos(String error) {
    return 'Det gick inte att ladda repositories: $error';
  }

  @override
  String get defaultRepoSaved => 'Standardrepository sparad';

  @override
  String get failedToSaveDefaultRepo => 'Det gick inte att spara standardrepository';

  @override
  String get defaultRepository => 'Standardrepository';

  @override
  String get selectDefaultRepoDesc =>
      'Välj en standardrepository för att skapa ärenden. Du kan fortfarande ange en annan repository när du skapar ärenden.';

  @override
  String get noReposFound => 'Inga repositories hittades';

  @override
  String get private => 'Privat';

  @override
  String updatedDate(String date) {
    return 'Uppdaterad $date';
  }

  @override
  String get yesterday => 'Igår';

  @override
  String daysAgo(int count) {
    return '$count dagar sedan';
  }

  @override
  String get oneWeekAgo => '1 vecka sedan';

  @override
  String weeksAgo(int count) {
    return '$count veckor sedan';
  }

  @override
  String get oneMonthAgo => '1 månad sedan';

  @override
  String monthsAgo(int count) {
    return '$count månader sedan';
  }

  @override
  String get issuesCreatedInRepo => 'Ärenden skapas i din standardrepository';

  @override
  String get taskIntegrations => 'Uppgiftsintegrationer';

  @override
  String get configureSettings => 'Konfigurera inställningar';

  @override
  String get completeAuthBrowser => 'Slutför autentiseringen i din webbläsare. När du är klar, återvänd till appen.';

  @override
  String failedToStartAppAuth(String appName) {
    return 'Det gick inte att starta $appName-autentisering';
  }

  @override
  String connectToAppTitle(String appName) {
    return 'Anslut till $appName';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Du behöver auktorisera Omi för att skapa uppgifter i ditt $appName-konto. Detta öppnar din webbläsare för autentisering.';
  }

  @override
  String get continueButton => 'Fortsätt';

  @override
  String appIntegration(String appName) {
    return '$appName-integration';
  }

  @override
  String integrationComingSoon(String appName) {
    return 'Integration med $appName kommer snart! Vi arbetar hårt för att ge dig fler alternativ för uppgiftshantering.';
  }

  @override
  String get gotIt => 'Uppfattat';

  @override
  String get tasksExportedOneApp => 'Uppgifter kan exporteras till en app åt gången.';

  @override
  String get completeYourUpgrade => 'Slutför din uppgradering';

  @override
  String get importConfiguration => 'Importera konfiguration';

  @override
  String get exportConfiguration => 'Exportera konfiguration';

  @override
  String get bringYourOwn => 'Ta med din egen';

  @override
  String get payYourSttProvider => 'Använd Omi fritt. Du betalar bara din STT-leverantör direkt.';

  @override
  String get freeMinutesMonth => '1 200 gratis minuter/månad ingår. Obegränsat med ';

  @override
  String get omiUnlimited => 'Omi Unlimited';

  @override
  String get hostRequired => 'Värd krävs';

  @override
  String get validPortRequired => 'Giltig port krävs';

  @override
  String get validWebsocketUrlRequired => 'Giltig WebSocket-URL krävs (wss://)';

  @override
  String get apiUrlRequired => 'API-URL krävs';

  @override
  String get apiKeyRequired => 'API-nyckel krävs';

  @override
  String get invalidJsonConfig => 'Ogiltig JSON-konfiguration';

  @override
  String errorSaving(String error) {
    return 'Fel vid sparande: $error';
  }

  @override
  String get configCopiedToClipboard => 'Konfiguration kopierad till urklipp';

  @override
  String get pasteJsonConfig => 'Klistra in din JSON-konfiguration nedan:';

  @override
  String get addApiKeyAfterImport => 'Du behöver lägga till din egen API-nyckel efter import';

  @override
  String get paste => 'Klistra in';

  @override
  String get import => 'Importera';

  @override
  String get invalidProviderInConfig => 'Ogiltig leverantör i konfiguration';

  @override
  String importedConfig(String providerName) {
    return 'Importerad $providerName-konfiguration';
  }

  @override
  String invalidJson(String error) {
    return 'Ogiltig JSON: $error';
  }

  @override
  String get provider => 'Leverantör';

  @override
  String get live => 'Live';

  @override
  String get onDevice => 'På enhet';

  @override
  String get apiUrl => 'API-URL';

  @override
  String get enterSttHttpEndpoint => 'Ange din STT HTTP-endpoint';

  @override
  String get websocketUrl => 'WebSocket-URL';

  @override
  String get enterLiveSttWebsocket => 'Ange din live STT WebSocket-endpoint';

  @override
  String get apiKey => 'API-nyckel';

  @override
  String get enterApiKey => 'Ange din API-nyckel';

  @override
  String get storedLocallyNeverShared => 'Lagras lokalt, delas aldrig';

  @override
  String get host => 'Värd';

  @override
  String get port => 'Port';

  @override
  String get advanced => 'Avancerat';

  @override
  String get configuration => 'Konfiguration';

  @override
  String get requestConfiguration => 'Begäran konfiguration';

  @override
  String get responseSchema => 'Svarsschema';

  @override
  String get modified => 'Modifierad';

  @override
  String get resetRequestConfig => 'Återställ begäran konfiguration till standard';

  @override
  String get logs => 'Loggar';

  @override
  String get logsCopied => 'Loggar kopierade';

  @override
  String get noLogsYet => 'Inga loggar ännu. Börja spela in för att se anpassad STT-aktivitet.';

  @override
  String deviceUsesCodec(String device, String reason) {
    return '$device använder $reason. Omi kommer att användas.';
  }

  @override
  String get omiTranscription => 'Omi-transkription';

  @override
  String get bestInClassTranscription => 'Bästa i klassen transkription utan konfiguration';

  @override
  String get instantSpeakerLabels => 'Omedelbara talaretiketter';

  @override
  String get languageTranslation => '100+ språköversättning';

  @override
  String get optimizedForConversation => 'Optimerad för konversation';

  @override
  String get autoLanguageDetection => 'Automatisk språkdetektering';

  @override
  String get highAccuracy => 'Hög noggrannhet';

  @override
  String get privacyFirst => 'Integritet först';

  @override
  String get saveChanges => 'Spara ändringar';

  @override
  String get resetToDefault => 'Återställ till standard';

  @override
  String get viewTemplate => 'Visa mall';

  @override
  String get trySomethingLike => 'Prova något som...';

  @override
  String get tryIt => 'Prova det';

  @override
  String get creatingPlan => 'Skapar plan';

  @override
  String get developingLogic => 'Utvecklar logik';

  @override
  String get designingApp => 'Designar app';

  @override
  String get generatingIconStep => 'Genererar ikon';

  @override
  String get finalTouches => 'Sista finishen';

  @override
  String get processing => 'Bearbetar...';

  @override
  String get features => 'Funktioner';

  @override
  String get creatingYourApp => 'Skapar din app...';

  @override
  String get generatingIcon => 'Genererar ikon...';

  @override
  String get whatShouldWeMake => 'Vad ska vi skapa?';

  @override
  String get appName => 'App Name';

  @override
  String get description => 'Beskrivning';

  @override
  String get publicLabel => 'Offentlig';

  @override
  String get privateLabel => 'Privat';

  @override
  String get free => 'Gratis';

  @override
  String get perMonth => '/ Månad';

  @override
  String get tailoredConversationSummaries => 'Skräddarsydda konversationssammanfattningar';

  @override
  String get customChatbotPersonality => 'Anpassad chatbot-personlighet';

  @override
  String get makePublic => 'Gör offentlig';

  @override
  String get anyoneCanDiscover => 'Vem som helst kan upptäcka din app';

  @override
  String get onlyYouCanUse => 'Endast du kan använda denna app';

  @override
  String get paidApp => 'Betald app';

  @override
  String get usersPayToUse => 'Användare betalar för att använda din app';

  @override
  String get freeForEveryone => 'Gratis för alla';

  @override
  String get perMonthLabel => '/ månad';

  @override
  String get creating => 'Skapar...';

  @override
  String get createApp => 'Skapa App';

  @override
  String get searchingForDevices => 'Söker efter enheter...';

  @override
  String devicesFoundNearby(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'ENHETER',
      one: 'ENHET',
    );
    return '$count $_temp0 HITTAD(E) I NÄRHETEN';
  }

  @override
  String get pairingSuccessful => 'PARKOPPLING LYCKADES';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Fel vid anslutning till Apple Watch: $error';
  }

  @override
  String get dontShowAgain => 'Visa inte igen';

  @override
  String get iUnderstand => 'Jag förstår';

  @override
  String get enableBluetooth => 'Aktivera Bluetooth';

  @override
  String get bluetoothNeeded =>
      'Omi behöver Bluetooth för att ansluta till din bärbara enhet. Aktivera Bluetooth och försök igen.';

  @override
  String get contactSupport => 'Kontakta support?';

  @override
  String get connectLater => 'Anslut senare';

  @override
  String get grantPermissions => 'Bevilja behörigheter';

  @override
  String get backgroundActivity => 'Bakgrundsaktivitet';

  @override
  String get backgroundActivityDesc => 'Låt Omi köra i bakgrunden för bättre stabilitet';

  @override
  String get locationAccess => 'Platsåtkomst';

  @override
  String get locationAccessDesc => 'Aktivera bakgrundsplats för den fullständiga upplevelsen';

  @override
  String get notifications => 'Aviseringar';

  @override
  String get notificationsDesc => 'Aktivera notifieringar för att hålla dig informerad';

  @override
  String get locationServiceDisabled => 'Platstjänst inaktiverad';

  @override
  String get locationServiceDisabledDesc =>
      'Platstjänsten är inaktiverad. Gå till Inställningar > Integritet och säkerhet > Platstjänster och aktivera den';

  @override
  String get backgroundLocationDenied => 'Bakgrundsplatsåtkomst nekad';

  @override
  String get backgroundLocationDeniedDesc =>
      'Gå till enhetsinställningar och ställ in platsbehörighet till \"Tillåt alltid\"';

  @override
  String get lovingOmi => 'Älskar du Omi?';

  @override
  String get leaveReviewIos =>
      'Hjälp oss att nå fler människor genom att lämna en recension i App Store. Din återkoppling betyder världen för oss!';

  @override
  String get leaveReviewAndroid =>
      'Hjälp oss att nå fler människor genom att lämna en recension i Google Play Store. Din återkoppling betyder världen för oss!';

  @override
  String get rateOnAppStore => 'Betygsätt i App Store';

  @override
  String get rateOnGooglePlay => 'Betygsätt i Google Play';

  @override
  String get maybeLater => 'Kanske senare';

  @override
  String get speechProfileIntro => 'Omi behöver lära sig dina mål och din röst. Du kan ändra det senare.';

  @override
  String get getStarted => 'Kom igång';

  @override
  String get allDone => 'Allt klart!';

  @override
  String get keepGoing => 'Fortsätt, du gör det bra';

  @override
  String get skipThisQuestion => 'Hoppa över denna fråga';

  @override
  String get skipForNow => 'Hoppa över för tillfället';

  @override
  String get connectionError => 'Anslutningsfel';

  @override
  String get connectionErrorDesc =>
      'Det gick inte att ansluta till servern. Kontrollera din internetanslutning och försök igen.';

  @override
  String get invalidRecordingMultipleSpeakers => 'Ogiltig inspelning upptäckt';

  @override
  String get multipleSpeakersDesc =>
      'Det verkar som det finns flera talare i inspelningen. Se till att du är på en tyst plats och försök igen.';

  @override
  String get tooShortDesc => 'Det finns inte tillräckligt med tal upptäckt. Tala mer och försök igen.';

  @override
  String get invalidRecordingDesc => 'Se till att du talar i minst 5 sekunder och inte mer än 90.';

  @override
  String get areYouThere => 'Är du där?';

  @override
  String get noSpeechDesc =>
      'Vi kunde inte upptäcka något tal. Se till att tala i minst 10 sekunder och inte mer än 3 minuter.';

  @override
  String get connectionLost => 'Anslutning förlorad';

  @override
  String get connectionLostDesc => 'Anslutningen avbröts. Kontrollera din internetanslutning och försök igen.';

  @override
  String get tryAgain => 'Försök igen';

  @override
  String get connectOmiOmiGlass => 'Anslut Omi / OmiGlass';

  @override
  String get continueWithoutDevice => 'Fortsätt utan enhet';

  @override
  String get permissionsRequired => 'Behörigheter krävs';

  @override
  String get permissionsRequiredDesc =>
      'Denna app behöver Bluetooth- och platsbehörigheter för att fungera korrekt. Aktivera dem i inställningarna.';

  @override
  String get openSettings => 'Öppna inställningar';

  @override
  String get wantDifferentName => 'Vill du kallas något annat?';

  @override
  String get whatsYourName => 'Vad heter du?';

  @override
  String get speakTranscribeSummarize => 'Tala. Transkribera. Sammanfatta.';

  @override
  String get signInWithApple => 'Logga in med Apple';

  @override
  String get signInWithGoogle => 'Logga in med Google';

  @override
  String get byContinuingAgree => 'Genom att fortsätta godkänner du vår ';

  @override
  String get termsOfUse => 'Användarvillkor';

  @override
  String get omiYourAiCompanion => 'Omi – Din AI-följeslagare';

  @override
  String get captureEveryMoment =>
      'Fånga varje ögonblick. Få AI-drivna\nsammanfattningar. Ta aldrig anteckningar igen.';

  @override
  String get appleWatchSetup => 'Apple Watch-konfiguration';

  @override
  String get permissionRequestedExclaim => 'Behörighet begärd!';

  @override
  String get microphonePermission => 'Mikrofonbehörighet';

  @override
  String get permissionGrantedNow =>
      'Behörighet beviljad! Nu:\n\nÖppna Omi-appen på din klocka och tryck på \"Fortsätt\" nedan';

  @override
  String get needMicrophonePermission =>
      'Vi behöver mikrofonbehörighet.\n\n1. Tryck på \"Bevilja behörighet\"\n2. Tillåt på din iPhone\n3. Klockappen stängs\n4. Öppna igen och tryck på \"Fortsätt\"';

  @override
  String get grantPermissionButton => 'Bevilja behörighet';

  @override
  String get needHelp => 'Behöver du hjälp?';

  @override
  String get troubleshootingSteps =>
      'Felsökning:\n\n1. Se till att Omi är installerat på din klocka\n2. Öppna Omi-appen på din klocka\n3. Leta efter behörighetspopupen\n4. Tryck på \"Tillåt\" när du uppmanas\n5. Appen på din klocka stängs - öppna den igen\n6. Kom tillbaka och tryck på \"Fortsätt\" på din iPhone';

  @override
  String get recordingStartedSuccessfully => 'Inspelning startade!';

  @override
  String get permissionNotGrantedYet =>
      'Behörighet har inte beviljats ännu. Se till att du tillät mikrofonåtkomst och öppnade appen igen på din klocka.';

  @override
  String errorRequestingPermission(String error) {
    return 'Fel vid begäran av behörighet: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'Fel vid start av inspelning: $error';
  }

  @override
  String get selectPrimaryLanguage => 'Välj ditt primära språk';

  @override
  String get languageBenefits => 'Ställ in ditt språk för skarpare transkriptioner och en personlig upplevelse';

  @override
  String get whatsYourPrimaryLanguage => 'Vilket är ditt primära språk?';

  @override
  String get selectYourLanguage => 'Välj ditt språk';

  @override
  String get personalGrowthJourney => 'Din personliga tillväxtresa med AI som lyssnar på varje ord.';

  @override
  String get actionItemsTitle => 'Att göra';

  @override
  String get actionItemsDescription => 'Tryck för att redigera • Långtryck för att välja • Svep för åtgärder';

  @override
  String get tabToDo => 'Att göra';

  @override
  String get tabDone => 'Klar';

  @override
  String get tabOld => 'Gamla';

  @override
  String get emptyTodoMessage => '🎉 Allt klart!\nInga väntande åtgärder';

  @override
  String get emptyDoneMessage => 'Inga avslutade objekt ännu';

  @override
  String get emptyOldMessage => '✅ Inga gamla uppgifter';

  @override
  String get noItems => 'Inga objekt';

  @override
  String get actionItemMarkedIncomplete => 'Åtgärd markerad som ofullständig';

  @override
  String get actionItemCompleted => 'Åtgärd slutförd';

  @override
  String get deleteActionItemTitle => 'Ta bort åtgärdspost';

  @override
  String get deleteActionItemMessage => 'Är du säker på att du vill ta bort denna åtgärdspost?';

  @override
  String get deleteSelectedItemsTitle => 'Ta bort valda objekt';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Är du säker på att du vill ta bort $count vald$s åtgärd$s?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'Åtgärd \"$description\" borttagen';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count åtgärd$s borttagen$s';
  }

  @override
  String get failedToDeleteItem => 'Det gick inte att ta bort åtgärd';

  @override
  String get failedToDeleteItems => 'Det gick inte att ta bort objekt';

  @override
  String get failedToDeleteSomeItems => 'Det gick inte att ta bort vissa objekt';

  @override
  String get welcomeActionItemsTitle => 'Redo för åtgärder';

  @override
  String get welcomeActionItemsDescription =>
      'Din AI kommer automatiskt att extrahera uppgifter och att-göra-saker från dina konversationer. De kommer att visas här när de skapas.';

  @override
  String get autoExtractionFeature => 'Automatiskt extraherat från konversationer';

  @override
  String get editSwipeFeature => 'Tryck för att redigera, svep för att slutföra eller ta bort';

  @override
  String itemsSelected(int count) {
    return '$count valda';
  }

  @override
  String get selectAll => 'Välj alla';

  @override
  String get deleteSelected => 'Ta bort valda';

  @override
  String get searchMemories => 'Sök minnen...';

  @override
  String get memoryDeleted => 'Minne borttaget.';

  @override
  String get undo => 'Ångra';

  @override
  String get noMemoriesYet => '🧠 Inga minnen ännu';

  @override
  String get noAutoMemories => 'Inga automatiskt extraherade minnen ännu';

  @override
  String get noManualMemories => 'Inga manuella minnen ännu';

  @override
  String get noMemoriesInCategories => 'Inga minnen i dessa kategorier';

  @override
  String get noMemoriesFound => '🔍 Inga minnen hittades';

  @override
  String get addFirstMemory => 'Lägg till ditt första minne';

  @override
  String get clearMemoryTitle => 'Rensa Omis minne';

  @override
  String get clearMemoryMessage => 'Är du säker på att du vill rensa Omis minne? Detta kan inte ångras.';

  @override
  String get clearMemoryButton => 'Rensa minne';

  @override
  String get memoryClearedSuccess => 'Omis minne om dig har rensats';

  @override
  String get noMemoriesToDelete => 'Inga minnen att ta bort';

  @override
  String get createMemoryTooltip => 'Skapa nytt minne';

  @override
  String get createActionItemTooltip => 'Skapa ny åtgärd';

  @override
  String get memoryManagement => 'Minneshantering';

  @override
  String get filterMemories => 'Filtrera minnen';

  @override
  String totalMemoriesCount(int count) {
    return 'Du har $count totala minnen';
  }

  @override
  String get publicMemories => 'Offentliga minnen';

  @override
  String get privateMemories => 'Privata minnen';

  @override
  String get makeAllPrivate => 'Gör alla minnen privata';

  @override
  String get makeAllPublic => 'Gör alla minnen offentliga';

  @override
  String get deleteAllMemories => 'Ta bort alla minnen';

  @override
  String get allMemoriesPrivateResult => 'Alla minnen är nu privata';

  @override
  String get allMemoriesPublicResult => 'Alla minnen är nu offentliga';

  @override
  String get newMemory => '✨ Nytt minne';

  @override
  String get editMemory => '✏️ Redigera minne';

  @override
  String get memoryContentHint => 'Jag gillar att äta glass...';

  @override
  String get failedToSaveMemory => 'Det gick inte att spara. Kontrollera din anslutning.';

  @override
  String get saveMemory => 'Spara minne';

  @override
  String get retry => 'Försök igen';

  @override
  String get createActionItem => 'Skapa åtgärd';

  @override
  String get editActionItem => 'Redigera åtgärd';

  @override
  String get actionItemDescriptionHint => 'Vad behöver göras?';

  @override
  String get actionItemDescriptionEmpty => 'Åtgärdsbeskrivning kan inte vara tom.';

  @override
  String get actionItemUpdated => 'Åtgärd uppdaterad';

  @override
  String get failedToUpdateActionItem => 'Misslyckades med att uppdatera åtgärd';

  @override
  String get actionItemCreated => 'Åtgärd skapad';

  @override
  String get failedToCreateActionItem => 'Misslyckades med att skapa åtgärd';

  @override
  String get dueDate => 'Förfallodatum';

  @override
  String get time => 'Tid';

  @override
  String get addDueDate => 'Lägg till förfallodatum';

  @override
  String get pressDoneToSave => 'Tryck på klar för att spara';

  @override
  String get pressDoneToCreate => 'Tryck på klar för att skapa';

  @override
  String get filterAll => 'Alla';

  @override
  String get filterSystem => 'Om dig';

  @override
  String get filterInteresting => 'Insikter';

  @override
  String get filterManual => 'Manuell';

  @override
  String get completed => 'Klar';

  @override
  String get markComplete => 'Markera som slutförd';

  @override
  String get actionItemDeleted => 'Åtgärdspost borttagen';

  @override
  String get failedToDeleteActionItem => 'Misslyckades med att radera åtgärd';

  @override
  String get deleteActionItemConfirmTitle => 'Ta bort åtgärd';

  @override
  String get deleteActionItemConfirmMessage => 'Är du säker på att du vill ta bort denna åtgärd?';

  @override
  String get appLanguage => 'Appspråk';

  @override
  String get appInterfaceSectionTitle => 'APPGRÄNSSNITT';

  @override
  String get speechTranscriptionSectionTitle => 'TAL OCH TRANSKRIPTION';

  @override
  String get languageSettingsHelperText =>
      'Appspråk ändrar menyer och knappar. Talspråk påverkar hur dina inspelningar transkriberas.';

  @override
  String get translationNotice => 'Översättningsmeddelande';

  @override
  String get translationNoticeMessage =>
      'Omi översätter konversationer till ditt primära språk. Uppdatera det när som helst i Inställningar → Profiler.';

  @override
  String get pleaseCheckInternetConnection => 'Kontrollera din internetanslutning och försök igen';

  @override
  String get pleaseSelectReason => 'Vänligen välj en anledning';

  @override
  String get tellUsMoreWhatWentWrong => 'Berätta mer om vad som gick fel...';

  @override
  String get selectText => 'Välj text';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Maximalt $count mål tillåtna';
  }

  @override
  String get conversationCannotBeMerged => 'Denna konversation kan inte slås samman (låst eller redan sammanfogas)';

  @override
  String get pleaseEnterFolderName => 'Ange ett mappnamn';

  @override
  String get failedToCreateFolder => 'Det gick inte att skapa mappen';

  @override
  String get failedToUpdateFolder => 'Det gick inte att uppdatera mappen';

  @override
  String get folderName => 'Mappnamn';

  @override
  String get descriptionOptional => 'Description (optional)';

  @override
  String get failedToDeleteFolder => 'Det gick inte att ta bort mappen';

  @override
  String get editFolder => 'Redigera mapp';

  @override
  String get deleteFolder => 'Ta bort mapp';

  @override
  String get transcriptCopiedToClipboard => 'Transkription kopierad till urklipp';

  @override
  String get summaryCopiedToClipboard => 'Sammanfattning kopierad till urklipp';

  @override
  String get conversationUrlCouldNotBeShared => 'Samtals-URL kunde inte delas.';

  @override
  String get urlCopiedToClipboard => 'URL kopierad till urklipp';

  @override
  String get exportTranscript => 'Exportera transkription';

  @override
  String get exportSummary => 'Exportera sammanfattning';

  @override
  String get exportButton => 'Exportera';

  @override
  String get actionItemsCopiedToClipboard => 'Åtgärdspunkter kopierade till urklipp';

  @override
  String get summarize => 'Sammanfatta';

  @override
  String get generateSummary => 'Generera sammanfattning';

  @override
  String get conversationNotFoundOrDeleted => 'Konversation hittades inte eller har raderats';

  @override
  String get deleteMemory => 'Ta bort minne';

  @override
  String get thisActionCannotBeUndone => 'Denna åtgärd kan inte ångras.';

  @override
  String memoriesCount(int count) {
    return '$count minnen';
  }

  @override
  String get noMemoriesInCategory => 'Inga minnen i denna kategori ännu';

  @override
  String get addYourFirstMemory => 'Lägg till ditt första minne';

  @override
  String get firmwareDisconnectUsb => 'Koppla från USB';

  @override
  String get firmwareUsbWarning => 'USB-anslutning under uppdateringar kan skada din enhet.';

  @override
  String get firmwareBatteryAbove15 => 'Batteri över 15%';

  @override
  String get firmwareEnsureBattery => 'Se till att din enhet har 15% batteri.';

  @override
  String get firmwareStableConnection => 'Stabil anslutning';

  @override
  String get firmwareConnectWifi => 'Anslut till WiFi eller mobildata.';

  @override
  String failedToStartUpdate(String error) {
    return 'Misslyckades med att starta uppdatering: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'Innan uppdatering, se till att:';

  @override
  String get confirmed => 'Bekräftad!';

  @override
  String get release => 'Släpp';

  @override
  String get slideToUpdate => 'Dra för att uppdatera';

  @override
  String copiedToClipboard(String title) {
    return '$title kopierat till urklipp';
  }

  @override
  String get batteryLevel => 'Batterinivå';

  @override
  String get productUpdate => 'Produktuppdatering';

  @override
  String get offline => 'Offline';

  @override
  String get available => 'Tillgänglig';

  @override
  String get unpairDeviceDialogTitle => 'Koppla bort enhet';

  @override
  String get unpairDeviceDialogMessage =>
      'Detta kommer att koppla bort enheten så att den kan anslutas till en annan telefon. Du måste gå till Inställningar > Bluetooth och glömma enheten för att slutföra processen.';

  @override
  String get unpair => 'Koppla bort';

  @override
  String get unpairAndForgetDevice => 'Koppla bort och glöm enhet';

  @override
  String get unknownDevice => 'Okänd';

  @override
  String get unknown => 'Okänd';

  @override
  String get productName => 'Produktnamn';

  @override
  String get serialNumber => 'Serienummer';

  @override
  String get connected => 'Ansluten';

  @override
  String get privacyPolicyTitle => 'Sekretesspolicy';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label kopierad';
  }

  @override
  String get noApiKeysYet => 'Inga API-nycklar ännu. Skapa en för att integrera med din app.';

  @override
  String get createKeyToGetStarted => 'Skapa en nyckel för att komma igång';

  @override
  String get persona => 'Persona';

  @override
  String get configureYourAiPersona => 'Konfigurera din AI-persona';

  @override
  String get configureSttProvider => 'Konfigurera STT-leverantör';

  @override
  String get setWhenConversationsAutoEnd => 'Ställ in när konversationer avslutas automatiskt';

  @override
  String get importDataFromOtherSources => 'Importera data från andra källor';

  @override
  String get debugAndDiagnostics => 'Felsökning och diagnostik';

  @override
  String get autoDeletesAfter3Days => 'Raderas automatiskt efter 3 dagar';

  @override
  String get helpsDiagnoseIssues => 'Hjälper till att diagnostisera problem';

  @override
  String get exportStartedMessage => 'Export startad. Detta kan ta några sekunder...';

  @override
  String get exportConversationsToJson => 'Exportera konversationer till en JSON-fil';

  @override
  String get knowledgeGraphDeletedSuccess => 'Kunskapsgraf raderad';

  @override
  String failedToDeleteGraph(String error) {
    return 'Kunde inte radera graf: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'Rensa alla noder och anslutningar';

  @override
  String get addToClaudeDesktopConfig => 'Lägg till i claude_desktop_config.json';

  @override
  String get connectAiAssistantsToData => 'Anslut AI-assistenter till dina data';

  @override
  String get useYourMcpApiKey => 'Använd din MCP API-nyckel';

  @override
  String get realTimeTranscript => 'Realtidstranskription';

  @override
  String get experimental => 'Experimentell';

  @override
  String get transcriptionDiagnostics => 'Transkriptionsdiagnostik';

  @override
  String get detailedDiagnosticMessages => 'Detaljerade diagnostiska meddelanden';

  @override
  String get autoCreateSpeakers => 'Skapa talare automatiskt';

  @override
  String get autoCreateWhenNameDetected => 'Skapa automatiskt när namn upptäcks';

  @override
  String get followUpQuestions => 'Uppföljningsfrågor';

  @override
  String get suggestQuestionsAfterConversations => 'Föreslå frågor efter konversationer';

  @override
  String get goalTracker => 'Målspårare';

  @override
  String get trackPersonalGoalsOnHomepage => 'Spåra dina personliga mål på startsidan';

  @override
  String get dailyReflection => 'Daglig reflektion';

  @override
  String get get9PmReminderToReflect => 'Få en påminnelse kl. 21 att reflektera över din dag';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'Åtgärdspostbeskrivning kan inte vara tom';

  @override
  String get saved => 'Sparad';

  @override
  String get overdue => 'Försenad';

  @override
  String get failedToUpdateDueDate => 'Det gick inte att uppdatera förfallodatumet';

  @override
  String get markIncomplete => 'Markera som ofullständig';

  @override
  String get editDueDate => 'Redigera förfallodatum';

  @override
  String get setDueDate => 'Ange förfallodatum';

  @override
  String get clearDueDate => 'Rensa förfallodatum';

  @override
  String get failedToClearDueDate => 'Det gick inte att rensa förfallodatumet';

  @override
  String get mondayAbbr => 'Mån';

  @override
  String get tuesdayAbbr => 'Tis';

  @override
  String get wednesdayAbbr => 'Ons';

  @override
  String get thursdayAbbr => 'Tor';

  @override
  String get fridayAbbr => 'Fre';

  @override
  String get saturdayAbbr => 'Lör';

  @override
  String get sundayAbbr => 'Sön';

  @override
  String get howDoesItWork => 'Hur fungerar det?';

  @override
  String get sdCardSyncDescription =>
      'SD-kortssynkronisering kommer att importera dina minnen från SD-kortet till appen';

  @override
  String get checksForAudioFiles => 'Kontrollerar ljudfiler på SD-kortet';

  @override
  String get omiSyncsAudioFiles => 'Omi synkroniserar sedan ljudfilerna med servern';

  @override
  String get serverProcessesAudio => 'Servern bearbetar ljudfilerna och skapar minnen';

  @override
  String get youreAllSet => 'Du är redo!';

  @override
  String get welcomeToOmiDescription =>
      'Välkommen till Omi! Din AI-följeslagare är redo att hjälpa dig med samtal, uppgifter och mer.';

  @override
  String get startUsingOmi => 'Börja använda Omi';

  @override
  String get back => 'Tillbaka';

  @override
  String get keyboardShortcuts => 'Tangentbordsgenvägar';

  @override
  String get toggleControlBar => 'Växla kontrollfält';

  @override
  String get pressKeys => 'Tryck på tangenter...';

  @override
  String get cmdRequired => '⌘ krävs';

  @override
  String get invalidKey => 'Ogiltig tangent';

  @override
  String get space => 'Mellanslag';

  @override
  String get search => 'Sök';

  @override
  String get searchPlaceholder => 'Sök...';

  @override
  String get untitledConversation => 'Namnlös konversation';

  @override
  String countRemaining(String count) {
    return '$count återstår';
  }

  @override
  String get addGoal => 'Lägg till mål';

  @override
  String get editGoal => 'Redigera mål';

  @override
  String get icon => 'Ikon';

  @override
  String get goalTitle => 'Måltitel';

  @override
  String get current => 'Nuvarande';

  @override
  String get target => 'Mål';

  @override
  String get saveGoal => 'Spara';

  @override
  String get goals => 'Mål';

  @override
  String get tapToAddGoal => 'Tryck för att lägga till ett mål';

  @override
  String welcomeBack(String name) {
    return 'Välkommen tillbaka, $name';
  }

  @override
  String get yourConversations => 'Dina konversationer';

  @override
  String get reviewAndManageConversations => 'Granska och hantera dina inspelade konversationer';

  @override
  String get startCapturingConversations => 'Börja fånga konversationer med din Omi-enhet för att se dem här.';

  @override
  String get useMobileAppToCapture => 'Använd din mobilapp för att spela in ljud';

  @override
  String get conversationsProcessedAutomatically => 'Konversationer bearbetas automatiskt';

  @override
  String get getInsightsInstantly => 'Få insikter och sammanfattningar omedelbart';

  @override
  String get showAll => 'Visa alla →';

  @override
  String get noTasksForToday => 'Inga uppgifter för idag.\\nFråga Omi om fler uppgifter eller skapa manuellt.';

  @override
  String get dailyScore => 'DAGLIG POÄNG';

  @override
  String get dailyScoreDescription => 'En poäng för att hjälpa dig\nfokusera bättre på utförande.';

  @override
  String get searchResults => 'Sökresultat';

  @override
  String get actionItems => 'Åtgärdspunkter';

  @override
  String get tasksToday => 'Idag';

  @override
  String get tasksTomorrow => 'Imorgon';

  @override
  String get tasksNoDeadline => 'Ingen deadline';

  @override
  String get tasksLater => 'Senare';

  @override
  String get loadingTasks => 'Laddar uppgifter...';

  @override
  String get tasks => 'Uppgifter';

  @override
  String get swipeTasksToIndent => 'Svep uppgifter för indentering, dra mellan kategorier';

  @override
  String get create => 'Skapa';

  @override
  String get noTasksYet => 'Inga uppgifter ännu';

  @override
  String get tasksFromConversationsWillAppear =>
      'Uppgifter från dina konversationer visas här.\nKlicka på Skapa för att lägga till en manuellt.';

  @override
  String get monthJan => 'jan';

  @override
  String get monthFeb => 'feb';

  @override
  String get monthMar => 'mar';

  @override
  String get monthApr => 'apr';

  @override
  String get monthMay => 'Maj';

  @override
  String get monthJun => 'jun';

  @override
  String get monthJul => 'jul';

  @override
  String get monthAug => 'aug';

  @override
  String get monthSep => 'sep';

  @override
  String get monthOct => 'Okt';

  @override
  String get monthNov => 'nov';

  @override
  String get monthDec => 'dec';

  @override
  String get timePM => 'EM';

  @override
  String get timeAM => 'FM';

  @override
  String get actionItemUpdatedSuccessfully => 'Åtgärd uppdaterades framgångsrikt';

  @override
  String get actionItemCreatedSuccessfully => 'Åtgärd skapades framgångsrikt';

  @override
  String get actionItemDeletedSuccessfully => 'Åtgärd raderades framgångsrikt';

  @override
  String get deleteActionItem => 'Radera åtgärd';

  @override
  String get deleteActionItemConfirmation =>
      'Är du säker på att du vill radera denna åtgärd? Denna handling kan inte ångras.';

  @override
  String get enterActionItemDescription => 'Ange beskrivning av åtgärd...';

  @override
  String get markAsCompleted => 'Markera som slutförd';

  @override
  String get setDueDateAndTime => 'Ange förfallodatum och tid';

  @override
  String get reloadingApps => 'Laddar om appar...';

  @override
  String get loadingApps => 'Laddar appar...';

  @override
  String get browseInstallCreateApps => 'Bläddra, installera och skapa appar';

  @override
  String get all => 'Alla';

  @override
  String get open => 'Öppna';

  @override
  String get install => 'Installera';

  @override
  String get noAppsAvailable => 'Inga appar tillgängliga';

  @override
  String get unableToLoadApps => 'Kunde inte ladda appar';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'Försök justera dina söktermer eller filter';

  @override
  String get checkBackLaterForNewApps => 'Kom tillbaka senare för nya appar';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'Kontrollera din internetanslutning och försök igen';

  @override
  String get createNewApp => 'Skapa ny app';

  @override
  String get buildSubmitCustomOmiApp => 'Bygg och skicka in din anpassade Omi-app';

  @override
  String get submittingYourApp => 'Skickar in din app...';

  @override
  String get preparingFormForYou => 'Förbereder formuläret för dig...';

  @override
  String get appDetails => 'Appdetaljer';

  @override
  String get paymentDetails => 'Betalningsdetaljer';

  @override
  String get previewAndScreenshots => 'Förhandsvisning och skärmdumpar';

  @override
  String get appCapabilities => 'App-funktioner';

  @override
  String get aiPrompts => 'AI-uppmaningar';

  @override
  String get chatPrompt => 'Chattuppmaning';

  @override
  String get chatPromptPlaceholder =>
      'Du är en fantastisk app, ditt jobb är att svara på användarfrågor och få dem att må bra...';

  @override
  String get conversationPrompt => 'Samtalsprompt';

  @override
  String get conversationPromptPlaceholder =>
      'Du är en fantastisk app, du kommer att få en transkription och sammanfattning av ett samtal...';

  @override
  String get notificationScopes => 'Aviseringsomfång';

  @override
  String get appPrivacyAndTerms => 'App-integritet och -villkor';

  @override
  String get makeMyAppPublic => 'Gör min app offentlig';

  @override
  String get submitAppTermsAgreement =>
      'Genom att skicka in denna app godkänner jag Omi AI:s användarvillkor och sekretesspolicy';

  @override
  String get submitApp => 'Skicka in app';

  @override
  String get needHelpGettingStarted => 'Behöver du hjälp att komma igång?';

  @override
  String get clickHereForAppBuildingGuides => 'Klicka här för appbyggguider och dokumentation';

  @override
  String get submitAppQuestion => 'Skicka in app?';

  @override
  String get submitAppPublicDescription =>
      'Din app kommer att granskas och göras offentlig. Du kan börja använda den omedelbart, även under granskningen!';

  @override
  String get submitAppPrivateDescription =>
      'Din app kommer att granskas och göras tillgänglig för dig privat. Du kan börja använda den omedelbart, även under granskningen!';

  @override
  String get startEarning => 'Börja tjäna! 💰';

  @override
  String get connectStripeOrPayPal => 'Anslut Stripe eller PayPal för att ta emot betalningar för din app.';

  @override
  String get connectNow => 'Anslut nu';

  @override
  String get installsCount => 'Installationer';

  @override
  String get uninstallApp => 'Avinstallera app';

  @override
  String get subscribe => 'Prenumerera';

  @override
  String get dataAccessNotice => 'Meddelande om dataåtkomst';

  @override
  String get dataAccessWarning =>
      'Denna app kommer att få åtkomst till dina data. Omi AI är inte ansvarig för hur dina data används, modifieras eller raderas av denna app';

  @override
  String get installApp => 'Installera app';

  @override
  String get betaTesterNotice =>
      'Du är betatestare för denna app. Den är inte offentlig ännu. Den blir offentlig när den godkänns.';

  @override
  String get appUnderReviewOwner => 'Din app granskas och är bara synlig för dig. Den blir offentlig när den godkänns.';

  @override
  String get appRejectedNotice =>
      'Din app har avvisats. Uppdatera appens detaljer och skicka in den igen för granskning.';

  @override
  String get setupSteps => 'Installationssteg';

  @override
  String get setupInstructions => 'Installationsinstruktioner';

  @override
  String get integrationInstructions => 'Integrationsinstruktioner';

  @override
  String get preview => 'Förhandsvisning';

  @override
  String get aboutTheApp => 'Om appen';

  @override
  String get aboutThePersona => 'Om personan';

  @override
  String get chatPersonality => 'Chattpersonlighet';

  @override
  String get ratingsAndReviews => 'Betyg och recensioner';

  @override
  String get noRatings => 'inga betyg';

  @override
  String ratingsCount(String count) {
    return '$count+ betyg';
  }

  @override
  String get errorActivatingApp => 'Fel vid aktivering av app';

  @override
  String get integrationSetupRequired => 'Om detta är en integrationsapp, se till att installationen är klar.';

  @override
  String get installed => 'Installerad';

  @override
  String get appIdLabel => 'App-ID';

  @override
  String get appNameLabel => 'Appnamn';

  @override
  String get appNamePlaceholder => 'Min fantastiska app';

  @override
  String get pleaseEnterAppName => 'Ange appnamn';

  @override
  String get categoryLabel => 'Kategori';

  @override
  String get selectCategory => 'Välj kategori';

  @override
  String get descriptionLabel => 'Beskrivning';

  @override
  String get appDescriptionPlaceholder =>
      'Min fantastiska app är en fantastisk app som gör fantastiska saker. Det är den bästa appen!';

  @override
  String get pleaseProvideValidDescription => 'Ange en giltig beskrivning';

  @override
  String get appPricingLabel => 'Apppriser';

  @override
  String get noneSelected => 'Ingen vald';

  @override
  String get appIdCopiedToClipboard => 'App-ID kopierat till urklipp';

  @override
  String get appCategoryModalTitle => 'Appkategori';

  @override
  String get pricingFree => 'Gratis';

  @override
  String get pricingPaid => 'Betald';

  @override
  String get loadingCapabilities => 'Laddar funktioner...';

  @override
  String get filterInstalled => 'Installerade';

  @override
  String get filterMyApps => 'Mina appar';

  @override
  String get clearSelection => 'Rensa val';

  @override
  String get filterCategory => 'Kategori';

  @override
  String get rating4PlusStars => '4+ stjärnor';

  @override
  String get rating3PlusStars => '3+ stjärnor';

  @override
  String get rating2PlusStars => '2+ stjärnor';

  @override
  String get rating1PlusStars => '1+ stjärna';

  @override
  String get filterRating => 'Betyg';

  @override
  String get filterCapabilities => 'Funktioner';

  @override
  String get noNotificationScopesAvailable => 'Inga aviseringsområden tillgängliga';

  @override
  String get popularApps => 'Populära appar';

  @override
  String get pleaseProvidePrompt => 'Ange en prompt';

  @override
  String chatWithAppName(String appName) {
    return 'Chatta med $appName';
  }

  @override
  String get defaultAiAssistant => 'Standard AI-assistent';

  @override
  String get readyToChat => '✨ Redo att chatta!';

  @override
  String get connectionNeeded => '🌐 Anslutning krävs';

  @override
  String get startConversation => 'Starta en konversation och låt magin börja';

  @override
  String get checkInternetConnection => 'Kontrollera din internetanslutning';

  @override
  String get wasThisHelpful => 'Var detta hjälpsamt?';

  @override
  String get thankYouForFeedback => 'Tack för din feedback!';

  @override
  String get maxFilesUploadError => 'Du kan bara ladda upp 4 filer åt gången';

  @override
  String get attachedFiles => '📎 Bifogade filer';

  @override
  String get takePhoto => 'Ta foto';

  @override
  String get captureWithCamera => 'Fånga med kamera';

  @override
  String get selectImages => 'Välj bilder';

  @override
  String get chooseFromGallery => 'Välj från galleri';

  @override
  String get selectFile => 'Välj en fil';

  @override
  String get chooseAnyFileType => 'Välj vilken filtyp som helst';

  @override
  String get cannotReportOwnMessages => 'Du kan inte rapportera dina egna meddelanden';

  @override
  String get messageReportedSuccessfully => '✅ Meddelande rapporterat';

  @override
  String get confirmReportMessage => 'Är du säker på att du vill rapportera detta meddelande?';

  @override
  String get selectChatAssistant => 'Välj chattassistent';

  @override
  String get enableMoreApps => 'Aktivera fler appar';

  @override
  String get chatCleared => 'Chatt rensad';

  @override
  String get clearChatTitle => 'Rensa chatt?';

  @override
  String get confirmClearChat => 'Är du säker på att du vill rensa chatten? Denna åtgärd kan inte ångras.';

  @override
  String get copy => 'Kopiera';

  @override
  String get share => 'Dela';

  @override
  String get report => 'Rapportera';

  @override
  String get microphonePermissionRequired => 'Mikrofontillstånd krävs för röstinspelning.';

  @override
  String get microphonePermissionDenied =>
      'Mikrofontillstånd nekat. Ge tillstånd i Systeminställningar > Integritet och säkerhet > Mikrofon.';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'Kunde inte kontrollera mikrofontillstånd: $error';
  }

  @override
  String get failedToTranscribeAudio => 'Kunde inte transkribera ljud';

  @override
  String get transcribing => 'Transkriberar...';

  @override
  String get transcriptionFailed => 'Transkription misslyckades';

  @override
  String get discardedConversation => 'Kasserat samtal';

  @override
  String get at => 'kl.';

  @override
  String get from => 'från';

  @override
  String get copied => 'Kopierat!';

  @override
  String get copyLink => 'Kopiera länk';

  @override
  String get hideTranscript => 'Dölj transkription';

  @override
  String get viewTranscript => 'Visa transkription';

  @override
  String get conversationDetails => 'Konversationsdetaljer';

  @override
  String get transcript => 'Transkription';

  @override
  String segmentsCount(int count) {
    return '$count segment';
  }

  @override
  String get noTranscriptAvailable => 'Ingen transkription tillgänglig';

  @override
  String get noTranscriptMessage => 'Den här konversationen har ingen transkription.';

  @override
  String get conversationUrlCouldNotBeGenerated => 'Konversations-URL kunde inte genereras.';

  @override
  String get failedToGenerateConversationLink => 'Misslyckades generera konversationslänk';

  @override
  String get failedToGenerateShareLink => 'Misslyckades generera delningslänk';

  @override
  String get reloadingConversations => 'Laddar om konversationer...';

  @override
  String get user => 'Användare';

  @override
  String get starred => 'Stjärnmärkt';

  @override
  String get date => 'Datum';

  @override
  String get noResultsFound => 'Inga resultat hittades';

  @override
  String get tryAdjustingSearchTerms => 'Försök justera dina söktermer';

  @override
  String get starConversationsToFindQuickly => 'Stjärnmärk konversationer för att hitta dem snabbt här';

  @override
  String noConversationsOnDate(String date) {
    return 'Inga konversationer den $date';
  }

  @override
  String get trySelectingDifferentDate => 'Försök välja ett annat datum';

  @override
  String get conversations => 'Konversationer';

  @override
  String get chat => 'Chatt';

  @override
  String get actions => 'Åtgärder';

  @override
  String get syncAvailable => 'Synkronisering tillgänglig';

  @override
  String get referAFriend => 'Rekommendera en vän';

  @override
  String get help => 'Hjälp';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'Uppgradera till Pro';

  @override
  String get getOmiDevice => 'Skaffa Omi-enhet';

  @override
  String get wearableAiCompanion => 'Bärbar AI-följeslagare';

  @override
  String get loadingMemories => 'Laddar minnen...';

  @override
  String get allMemories => 'Alla minnen';

  @override
  String get aboutYou => 'Om dig';

  @override
  String get manual => 'Manuell';

  @override
  String get loadingYourMemories => 'Laddar dina minnen...';

  @override
  String get createYourFirstMemory => 'Skapa ditt första minne för att komma igång';

  @override
  String get tryAdjustingFilter => 'Försök justera din sökning eller filter';

  @override
  String get whatWouldYouLikeToRemember => 'Vad vill du komma ihåg?';

  @override
  String get category => 'Kategori';

  @override
  String get public => 'Offentlig';

  @override
  String get failedToSaveCheckConnection => 'Kunde inte spara. Kontrollera din anslutning.';

  @override
  String get createMemory => 'Skapa minne';

  @override
  String get deleteMemoryConfirmation =>
      'Är du säker på att du vill ta bort detta minne? Denna åtgärd kan inte ångras.';

  @override
  String get makePrivate => 'Gör privat';

  @override
  String get organizeAndControlMemories => 'Organisera och kontrollera dina minnen';

  @override
  String get total => 'Totalt';

  @override
  String get makeAllMemoriesPrivate => 'Gör alla minnen privata';

  @override
  String get setAllMemoriesToPrivate => 'Ställ in alla minnen till privat synlighet';

  @override
  String get makeAllMemoriesPublic => 'Gör alla minnen offentliga';

  @override
  String get setAllMemoriesToPublic => 'Ställ in alla minnen till offentlig synlighet';

  @override
  String get permanentlyRemoveAllMemories => 'Ta bort alla minnen permanent från Omi';

  @override
  String get allMemoriesAreNowPrivate => 'Alla minnen är nu privata';

  @override
  String get allMemoriesAreNowPublic => 'Alla minnen är nu offentliga';

  @override
  String get clearOmisMemory => 'Rensa Omis minne';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Är du säker på att du vill rensa Omis minne? Denna åtgärd kan inte ångras och kommer permanent ta bort alla $count minnen.';
  }

  @override
  String get omisMemoryCleared => 'Omis minne om dig har rensats';

  @override
  String get welcomeToOmi => 'Välkommen till Omi';

  @override
  String get continueWithApple => 'Fortsätt med Apple';

  @override
  String get continueWithGoogle => 'Fortsätt med Google';

  @override
  String get byContinuingYouAgree => 'Genom att fortsätta godkänner du våra ';

  @override
  String get termsOfService => 'Användarvillkor';

  @override
  String get and => ' och ';

  @override
  String get dataAndPrivacy => 'Data och integritet';

  @override
  String get secureAuthViaAppleId => 'Säker autentisering via Apple ID';

  @override
  String get secureAuthViaGoogleAccount => 'Säker autentisering via Google-konto';

  @override
  String get whatWeCollect => 'Vad vi samlar in';

  @override
  String get dataCollectionMessage =>
      'Genom att fortsätta kommer dina konversationer, inspelningar och personlig information att lagras säkert på våra servrar för att tillhandahålla AI-drivna insikter och aktivera alla appfunktioner.';

  @override
  String get dataProtection => 'Dataskydd';

  @override
  String get yourDataIsProtected => 'Din data är skyddad och styrs av vår ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'Välj ditt primära språk';

  @override
  String get chooseYourLanguage => 'Välj ditt språk';

  @override
  String get selectPreferredLanguageForBestExperience => 'Välj ditt föredragna språk för den bästa Omi-upplevelsen';

  @override
  String get searchLanguages => 'Sök språk...';

  @override
  String get selectALanguage => 'Välj ett språk';

  @override
  String get tryDifferentSearchTerm => 'Prova ett annat sökord';

  @override
  String get pleaseEnterYourName => 'Vänligen ange ditt namn';

  @override
  String get nameMustBeAtLeast2Characters => 'Namnet måste vara minst 2 tecken';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'Berätta för oss hur du vill bli tilltalad. Detta hjälper till att personalisera din Omi-upplevelse.';

  @override
  String charactersCount(int count) {
    return '$count tecken';
  }

  @override
  String get enableFeaturesForBestExperience => 'Aktivera funktioner för den bästa Omi-upplevelsen på din enhet.';

  @override
  String get microphoneAccess => 'Mikrofonåtkomst';

  @override
  String get recordAudioConversations => 'Spela in ljudsamtal';

  @override
  String get microphoneAccessDescription =>
      'Omi behöver mikrofonåtkomst för att spela in dina samtal och tillhandahålla transkriptioner.';

  @override
  String get screenRecording => 'Skärminspelning';

  @override
  String get captureSystemAudioFromMeetings => 'Fånga systemljud från möten';

  @override
  String get screenRecordingDescription =>
      'Omi behöver tillstånd för skärminspelning för att fånga systemljud från dina webbläsarbaserade möten.';

  @override
  String get accessibility => 'Tillgänglighet';

  @override
  String get detectBrowserBasedMeetings => 'Upptäck webbläsarbaserade möten';

  @override
  String get accessibilityDescription =>
      'Omi behöver tillgänglighetstillstånd för att upptäcka när du ansluter till Zoom-, Meet- eller Teams-möten i din webbläsare.';

  @override
  String get pleaseWait => 'Vänta...';

  @override
  String get joinTheCommunity => 'Gå med i communityn!';

  @override
  String get loadingProfile => 'Laddar profil...';

  @override
  String get profileSettings => 'Profilinställningar';

  @override
  String get noEmailSet => 'Ingen e-post inställd';

  @override
  String get userIdCopiedToClipboard => 'Användar-ID kopierat';

  @override
  String get yourInformation => 'Din Information';

  @override
  String get setYourName => 'Ange ditt namn';

  @override
  String get changeYourName => 'Ändra ditt namn';

  @override
  String get manageYourOmiPersona => 'Hantera din Omi-persona';

  @override
  String get voiceAndPeople => 'Röst och Personer';

  @override
  String get teachOmiYourVoice => 'Lär Omi din röst';

  @override
  String get tellOmiWhoSaidIt => 'Berätta för Omi vem som sa det 🗣️';

  @override
  String get payment => 'Betalning';

  @override
  String get addOrChangeYourPaymentMethod => 'Lägg till eller ändra betalningsmetod';

  @override
  String get preferences => 'Inställningar';

  @override
  String get helpImproveOmiBySharing => 'Hjälp till att förbättra Omi genom att dela anonymiserade analysdata';

  @override
  String get deleteAccount => 'Radera Konto';

  @override
  String get deleteYourAccountAndAllData => 'Radera ditt konto och alla data';

  @override
  String get clearLogs => 'Rensa loggar';

  @override
  String get debugLogsCleared => 'Felsökningsloggar rensade';

  @override
  String get exportConversations => 'Exportera konversationer';

  @override
  String get exportAllConversationsToJson => 'Exportera alla dina konversationer till en JSON-fil.';

  @override
  String get conversationsExportStarted =>
      'Export av konversationer startad. Detta kan ta några sekunder, vänligen vänta.';

  @override
  String get mcpDescription =>
      'För att ansluta Omi till andra applikationer för att läsa, söka och hantera dina minnen och konversationer. Skapa en nyckel för att komma igång.';

  @override
  String get apiKeys => 'API-nycklar';

  @override
  String errorLabel(String error) {
    return 'Fel: $error';
  }

  @override
  String get noApiKeysFound => 'Inga API-nycklar hittades. Skapa en för att komma igång.';

  @override
  String get advancedSettings => 'Avancerade inställningar';

  @override
  String get triggersWhenNewConversationCreated => 'Utlöses när en ny konversation skapas.';

  @override
  String get triggersWhenNewTranscriptReceived => 'Utlöses när en ny transkription tas emot.';

  @override
  String get realtimeAudioBytes => 'Realtids-ljudbytes';

  @override
  String get triggersWhenAudioBytesReceived => 'Utlöses när ljudbytes tas emot.';

  @override
  String get everyXSeconds => 'Varje x sekunder';

  @override
  String get triggersWhenDaySummaryGenerated => 'Utlöses när dagssammanfattningen genereras.';

  @override
  String get tryLatestExperimentalFeatures => 'Prova de senaste experimentella funktionerna från Omi-teamet.';

  @override
  String get transcriptionServiceDiagnosticStatus => 'Diagnostisk status för transkriptionstjänsten';

  @override
  String get enableDetailedDiagnosticMessages =>
      'Aktivera detaljerade diagnostiska meddelanden från transkriptionstjänsten';

  @override
  String get autoCreateAndTagNewSpeakers => 'Skapa och tagga nya talare automatiskt';

  @override
  String get automaticallyCreateNewPerson => 'Skapa automatiskt en ny person när ett namn upptäcks i transkriptionen.';

  @override
  String get pilotFeatures => 'Pilotfunktioner';

  @override
  String get pilotFeaturesDescription => 'Dessa funktioner är tester och ingen support garanteras.';

  @override
  String get suggestFollowUpQuestion => 'Föreslå uppföljningsfråga';

  @override
  String get saveSettings => 'Spara Inställningar';

  @override
  String get syncingDeveloperSettings => 'Synkroniserar utvecklarinställningar...';

  @override
  String get summary => 'Sammanfattning';

  @override
  String get auto => 'Automatisk';

  @override
  String get noSummaryForApp =>
      'Ingen sammanfattning tillgänglig för denna app. Prova en annan app för bättre resultat.';

  @override
  String get tryAnotherApp => 'Prova en annan app';

  @override
  String generatedBy(String appName) {
    return 'Genererad av $appName';
  }

  @override
  String get overview => 'Översikt';

  @override
  String get otherAppResults => 'Resultat från andra appar';

  @override
  String get unknownApp => 'Okänd app';

  @override
  String get noSummaryAvailable => 'Ingen sammanfattning tillgänglig';

  @override
  String get conversationNoSummaryYet => 'Den här konversationen har ingen sammanfattning ännu.';

  @override
  String get chooseSummarizationApp => 'Välj sammanfattningsapp';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName inställd som standardapp för sammanfattning';
  }

  @override
  String get letOmiChooseAutomatically => 'Låt Omi automatiskt välja den bästa appen';

  @override
  String get deleteConversationConfirmation =>
      'Är du säker på att du vill radera den här konversationen? Denna åtgärd kan inte ångras.';

  @override
  String get conversationDeleted => 'Konversation raderad';

  @override
  String get generatingLink => 'Genererar länk...';

  @override
  String get editConversation => 'Redigera konversation';

  @override
  String get conversationLinkCopiedToClipboard => 'Konversationslänk kopierad till urklipp';

  @override
  String get conversationTranscriptCopiedToClipboard => 'Konversationstranskription kopierad till urklipp';

  @override
  String get editConversationDialogTitle => 'Redigera konversation';

  @override
  String get changeTheConversationTitle => 'Ändra konversationens titel';

  @override
  String get conversationTitle => 'Konversationstitel';

  @override
  String get enterConversationTitle => 'Ange konversationstitel...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'Konversationstitel uppdaterad';

  @override
  String get failedToUpdateConversationTitle => 'Misslyckades uppdatera konversationstitel';

  @override
  String get errorUpdatingConversationTitle => 'Fel vid uppdatering av konversationstitel';

  @override
  String get settingUp => 'Konfigurerar...';

  @override
  String get startYourFirstRecording => 'Starta din första inspelning';

  @override
  String get preparingSystemAudioCapture => 'Förbereder systemljudupptagning';

  @override
  String get clickTheButtonToCaptureAudio =>
      'Klicka på knappen för att fånga ljud för livetranskriptioner, AI-insikter och automatisk sparning.';

  @override
  String get reconnecting => 'Återansluter...';

  @override
  String get recordingPaused => 'Inspelning pausad';

  @override
  String get recordingActive => 'Inspelning aktiv';

  @override
  String get startRecording => 'Starta inspelning';

  @override
  String resumingInCountdown(String countdown) {
    return 'Återupptar om ${countdown}s...';
  }

  @override
  String get tapPlayToResume => 'Tryck på spela upp för att fortsätta';

  @override
  String get listeningForAudio => 'Lyssnar efter ljud...';

  @override
  String get preparingAudioCapture => 'Förbereder ljudupptagning';

  @override
  String get clickToBeginRecording => 'Klicka för att börja inspelningen';

  @override
  String get translated => 'översatt';

  @override
  String get liveTranscript => 'Livetranskription';

  @override
  String segmentsSingular(String count) {
    return '$count segment';
  }

  @override
  String segmentsPlural(String count) {
    return '$count segment';
  }

  @override
  String get startRecordingToSeeTranscript => 'Starta inspelning för att se livetranskription';

  @override
  String get paused => 'Pausad';

  @override
  String get initializing => 'Initialiserar...';

  @override
  String get recording => 'Spelar in';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'Mikrofon ändrad. Återupptar om ${countdown}s';
  }

  @override
  String get clickPlayToResumeOrStop => 'Klicka på spela upp för att fortsätta eller stoppa för att avsluta';

  @override
  String get settingUpSystemAudioCapture => 'Konfigurerar systemljudupptagning';

  @override
  String get capturingAudioAndGeneratingTranscript => 'Fångar ljud och genererar transkription';

  @override
  String get clickToBeginRecordingSystemAudio => 'Klicka för att börja spela in systemljud';

  @override
  String get you => 'Du';

  @override
  String speakerWithId(String speakerId) {
    return 'Talare $speakerId';
  }

  @override
  String get translatedByOmi => 'översatt av omi';

  @override
  String get backToConversations => 'Tillbaka till samtal';

  @override
  String get systemAudio => 'System';

  @override
  String get mic => 'Mikrofon';

  @override
  String audioInputSetTo(String deviceName) {
    return 'Ljudingång inställd på $deviceName';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'Fel vid byte av ljudenhet: $error';
  }

  @override
  String get selectAudioInput => 'Välj ljudingång';

  @override
  String get loadingDevices => 'Laddar enheter...';

  @override
  String get settingsHeader => 'INSTÄLLNINGAR';

  @override
  String get plansAndBilling => 'Planer och Fakturering';

  @override
  String get calendarIntegration => 'Kalenderintegration';

  @override
  String get dailySummary => 'Daglig sammanfattning';

  @override
  String get developer => 'Utvecklare';

  @override
  String get about => 'Om';

  @override
  String get selectTime => 'Välj tid';

  @override
  String get accountGroup => 'Konto';

  @override
  String get signOutQuestion => 'Logga ut?';

  @override
  String get signOutConfirmation => 'Är du säker på att du vill logga ut?';

  @override
  String get customVocabularyHeader => 'ANPASSAT ORDFÖRRÅD';

  @override
  String get addWordsDescription => 'Lägg till ord som Omi ska känna igen under transkription.';

  @override
  String get enterWordsHint => 'Ange ord (kommaseparerade)';

  @override
  String get dailySummaryHeader => 'DAGLIG SAMMANFATTNING';

  @override
  String get dailySummaryTitle => 'Daglig Sammanfattning';

  @override
  String get dailySummaryDescription => 'Få en personlig sammanfattning av dagens konversationer som en avisering.';

  @override
  String get deliveryTime => 'Leveranstid';

  @override
  String get deliveryTimeDescription => 'När du ska få din dagliga sammanfattning';

  @override
  String get subscription => 'Prenumeration';

  @override
  String get viewPlansAndUsage => 'Visa Planer och Användning';

  @override
  String get viewPlansDescription => 'Hantera din prenumeration och se användningsstatistik';

  @override
  String get addOrChangePaymentMethod => 'Lägg till eller ändra din betalningsmetod';

  @override
  String get displayOptions => 'Visningsalternativ';

  @override
  String get showMeetingsInMenuBar => 'Visa möten i menyraden';

  @override
  String get displayUpcomingMeetingsDescription => 'Visa kommande möten i menyraden';

  @override
  String get showEventsWithoutParticipants => 'Visa händelser utan deltagare';

  @override
  String get includePersonalEventsDescription => 'Inkludera personliga händelser utan deltagare';

  @override
  String get upcomingMeetings => 'Kommande möten';

  @override
  String get checkingNext7Days => 'Kontrollerar de kommande 7 dagarna';

  @override
  String get shortcuts => 'Genvägar';

  @override
  String get shortcutChangeInstruction => 'Klicka på en genväg för att ändra den. Tryck på Escape för att avbryta.';

  @override
  String get configurePersonaDescription => 'Konfigurera din AI-persona';

  @override
  String get configureSTTProvider => 'Konfigurera STT-leverantör';

  @override
  String get setConversationEndDescription => 'Ställ in när konversationer avslutas automatiskt';

  @override
  String get importDataDescription => 'Importera data från andra källor';

  @override
  String get exportConversationsDescription => 'Exportera konversationer till JSON';

  @override
  String get exportingConversations => 'Exporterar konversationer...';

  @override
  String get clearNodesDescription => 'Rensa alla noder och anslutningar';

  @override
  String get deleteKnowledgeGraphQuestion => 'Ta bort kunskapsgraf?';

  @override
  String get deleteKnowledgeGraphWarning =>
      'Detta raderar all härledd kunskapsgrafdata. Dina ursprungliga minnen förblir säkra.';

  @override
  String get connectOmiWithAI => 'Anslut Omi till AI-assistenter';

  @override
  String get noAPIKeys => 'Inga API-nycklar. Skapa en för att komma igång.';

  @override
  String get autoCreateWhenDetected => 'Skapa automatiskt när namn upptäcks';

  @override
  String get trackPersonalGoals => 'Spåra personliga mål på startsidan';

  @override
  String get dailyReflectionDescription =>
      'Få en påminnelse kl. 21 för att reflektera över din dag och fånga dina tankar.';

  @override
  String get endpointURL => 'Slutpunkts-URL';

  @override
  String get links => 'Länkar';

  @override
  String get discordMemberCount => 'Över 8000 medlemmar på Discord';

  @override
  String get userInformation => 'Användarinformation';

  @override
  String get capabilities => 'Funktioner';

  @override
  String get previewScreenshots => 'Förhandsgranskning av skärmdumpar';

  @override
  String get holdOnPreparingForm => 'Vänta, vi förbereder formuläret åt dig';

  @override
  String get bySubmittingYouAgreeToOmi => 'Genom att skicka godkänner du Omi ';

  @override
  String get termsAndPrivacyPolicy => 'Villkor och Integritetspolicy';

  @override
  String get helpsDiagnoseIssuesAutoDeletes =>
      'Hjälper till att diagnostisera problem. Raderas automatiskt efter 3 dagar.';

  @override
  String get manageYourApp => 'Hantera din app';

  @override
  String get updatingYourApp => 'Uppdaterar din app';

  @override
  String get fetchingYourAppDetails => 'Hämtar appdetaljer';

  @override
  String get updateAppQuestion => 'Uppdatera app?';

  @override
  String get updateAppConfirmation =>
      'Är du säker på att du vill uppdatera din app? Ändringarna visas efter granskning av vårt team.';

  @override
  String get updateApp => 'Uppdatera app';

  @override
  String get createAndSubmitNewApp => 'Skapa och skicka in en ny app';

  @override
  String appsCount(String count) {
    return 'Appar ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'Privata appar ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'Offentliga appar ($count)';
  }

  @override
  String get newVersionAvailable => 'Ny version tillgänglig  🎉';

  @override
  String get no => 'Nej';

  @override
  String get subscriptionCancelledSuccessfully =>
      'Prenumeration avbruten. Den förblir aktiv till slutet av den aktuella faktureringsperioden.';

  @override
  String get failedToCancelSubscription => 'Det gick inte att avbryta prenumerationen. Försök igen.';

  @override
  String get invalidPaymentUrl => 'Ogiltig betalnings-URL';

  @override
  String get permissionsAndTriggers => 'Behörigheter och utlösare';

  @override
  String get chatFeatures => 'Chattfunktioner';

  @override
  String get uninstall => 'Avinstallera';

  @override
  String get installs => 'INSTALLATIONER';

  @override
  String get priceLabel => 'PRIS';

  @override
  String get updatedLabel => 'UPPDATERAD';

  @override
  String get createdLabel => 'SKAPAD';

  @override
  String get featuredLabel => 'UTVALD';

  @override
  String get cancelSubscriptionQuestion => 'Avbryt prenumeration?';

  @override
  String get cancelSubscriptionConfirmation =>
      'Är du säker på att du vill avbryta din prenumeration? Du kommer att ha tillgång till slutet av din nuvarande faktureringsperiod.';

  @override
  String get cancelSubscriptionButton => 'Avbryt prenumeration';

  @override
  String get cancelling => 'Avbryter...';

  @override
  String get betaTesterMessage =>
      'Du är betatestare för denna app. Den är inte offentlig ännu. Den blir offentlig efter godkännande.';

  @override
  String get appUnderReviewMessage =>
      'Din app granskas och är endast synlig för dig. Den blir offentlig efter godkännande.';

  @override
  String get appRejectedMessage => 'Din app har avvisats. Uppdatera uppgifterna och skicka in igen för granskning.';

  @override
  String get invalidIntegrationUrl => 'Ogiltig integrations-URL';

  @override
  String get tapToComplete => 'Tryck för att slutföra';

  @override
  String get invalidSetupInstructionsUrl => 'Ogiltig URL för installationsinstruktioner';

  @override
  String get pushToTalk => 'Tryck för att prata';

  @override
  String get summaryPrompt => 'Sammanfattningsprompt';

  @override
  String get pleaseSelectARating => 'Välj ett betyg';

  @override
  String get reviewAddedSuccessfully => 'Recension tillagd 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'Recension uppdaterad 🚀';

  @override
  String get failedToSubmitReview => 'Kunde inte skicka recension. Försök igen.';

  @override
  String get addYourReview => 'Lägg till din recension';

  @override
  String get editYourReview => 'Redigera din recension';

  @override
  String get writeAReviewOptional => 'Skriv en recension (valfritt)';

  @override
  String get submitReview => 'Skicka recension';

  @override
  String get updateReview => 'Uppdatera recension';

  @override
  String get yourReview => 'Din recension';

  @override
  String get anonymousUser => 'Anonym användare';

  @override
  String get issueActivatingApp => 'Det uppstod ett problem vid aktivering av denna app. Försök igen.';

  @override
  String get dataAccessNoticeDescription =>
      'Denna app kommer att få tillgång till dina data. Omi AI ansvarar inte för hur dina data används av tredjepartsappar.';

  @override
  String get copyUrl => 'Kopiera URL';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => 'Mån';

  @override
  String get weekdayTue => 'Tis';

  @override
  String get weekdayWed => 'Ons';

  @override
  String get weekdayThu => 'Tor';

  @override
  String get weekdayFri => 'Fre';

  @override
  String get weekdaySat => 'Lör';

  @override
  String get weekdaySun => 'Sön';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return '$serviceName-integration kommer snart';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'Redan exporterad till $platform';
  }

  @override
  String get anotherPlatform => 'en annan plattform';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'Vänligen autentisera med $serviceName i Inställningar > Uppgiftsintegrationer';
  }

  @override
  String addingToService(String serviceName) {
    return 'Lägger till i $serviceName...';
  }

  @override
  String addedToService(String serviceName) {
    return 'Tillagd i $serviceName';
  }

  @override
  String failedToAddToService(String serviceName) {
    return 'Kunde inte lägga till i $serviceName';
  }

  @override
  String get permissionDeniedForAppleReminders => 'Behörighet nekad för Apple Påminnelser';

  @override
  String failedToCreateApiKey(String error) {
    return 'Kunde inte skapa leverantörens API-nyckel: $error';
  }

  @override
  String get createAKey => 'Skapa en nyckel';

  @override
  String get apiKeyRevokedSuccessfully => 'API-nyckel återkallad';

  @override
  String failedToRevokeApiKey(String error) {
    return 'Kunde inte återkalla API-nyckel: $error';
  }

  @override
  String get omiApiKeys => 'Omi API-nycklar';

  @override
  String get apiKeysDescription =>
      'API-nycklar används för autentisering när din app kommunicerar med OMI-servern. De låter din applikation skapa minnen och få säker åtkomst till andra OMI-tjänster.';

  @override
  String get aboutOmiApiKeys => 'Om Omi API-nycklar';

  @override
  String get yourNewKey => 'Din nya nyckel:';

  @override
  String get copyToClipboard => 'Kopiera till urklipp';

  @override
  String get pleaseCopyKeyNow => 'Vänligen kopiera den nu och skriv ner den på ett säkert ställe. ';

  @override
  String get willNotSeeAgain => 'Du kommer inte att kunna se den igen.';

  @override
  String get revokeKey => 'Återkalla nyckel';

  @override
  String get revokeApiKeyQuestion => 'Återkalla API-nyckel?';

  @override
  String get revokeApiKeyWarning =>
      'Denna åtgärd kan inte ångras. Alla applikationer som använder denna nyckel kommer inte längre att kunna komma åt API:et.';

  @override
  String get revoke => 'Återkalla';

  @override
  String get whatWouldYouLikeToCreate => 'Vad vill du skapa?';

  @override
  String get createAnApp => 'Skapa en app';

  @override
  String get createAndShareYourApp => 'Skapa och dela din app';

  @override
  String get createMyClone => 'Skapa min klon';

  @override
  String get createYourDigitalClone => 'Skapa din digitala klon';

  @override
  String get itemApp => 'App';

  @override
  String get itemPersona => 'Persona';

  @override
  String keepItemPublic(String item) {
    return 'Behåll $item offentlig';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return 'Gör $item offentlig?';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return 'Gör $item privat?';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'Om du gör $item offentlig kan den användas av alla';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'Om du gör $item privat nu slutar den fungera för alla och blir endast synlig för dig';
  }

  @override
  String get manageApp => 'Hantera app';

  @override
  String get updatePersonaDetails => 'Uppdatera persona-detaljer';

  @override
  String deleteItemTitle(String item) {
    return 'Radera $item';
  }

  @override
  String deleteItemQuestion(String item) {
    return 'Radera $item?';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'Är du säker på att du vill radera denna $item? Denna åtgärd kan inte ångras.';
  }

  @override
  String get revokeKeyQuestion => 'Återkalla nyckel?';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'Är du säker på att du vill återkalla nyckeln \"$keyName\"? Denna åtgärd kan inte ångras.';
  }

  @override
  String get createNewKey => 'Skapa ny nyckel';

  @override
  String get keyNameHint => 't.ex. Claude Desktop';

  @override
  String get pleaseEnterAName => 'Ange ett namn.';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'Det gick inte att skapa nyckel: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'Det gick inte att skapa nyckel. Försök igen.';

  @override
  String get keyCreated => 'Nyckel skapad';

  @override
  String get keyCreatedMessage => 'Din nya nyckel har skapats. Kopiera den nu. Du kommer inte att kunna se den igen.';

  @override
  String get keyWord => 'Nyckel';

  @override
  String get externalAppAccess => 'Extern app-åtkomst';

  @override
  String get externalAppAccessDescription =>
      'Följande installerade appar har externa integrationer och kan komma åt dina data, såsom konversationer och minnen.';

  @override
  String get noExternalAppsHaveAccess => 'Inga externa appar har åtkomst till dina data.';

  @override
  String get maximumSecurityE2ee => 'Maximal säkerhet (E2EE)';

  @override
  String get e2eeDescription =>
      'End-to-end-kryptering är guldstandarden för integritet. När det är aktiverat krypteras dina data på din enhet innan de skickas till våra servrar. Det betyder att ingen, inte ens Omi, kan komma åt ditt innehåll.';

  @override
  String get importantTradeoffs => 'Viktiga avvägningar:';

  @override
  String get e2eeTradeoff1 => '• Vissa funktioner som externa app-integrationer kan vara inaktiverade.';

  @override
  String get e2eeTradeoff2 => '• Om du tappar ditt lösenord kan dina data inte återställas.';

  @override
  String get featureComingSoon => 'Den här funktionen kommer snart!';

  @override
  String get migrationInProgressMessage => 'Migrering pågår. Du kan inte ändra skyddsnivån förrän den är klar.';

  @override
  String get migrationFailed => 'Migreringen misslyckades';

  @override
  String migratingFromTo(String source, String target) {
    return 'Migrerar från $source till $target';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total objekt';
  }

  @override
  String get secureEncryption => 'Säker kryptering';

  @override
  String get secureEncryptionDescription =>
      'Dina data krypteras med en nyckel som är unik för dig på våra servrar, som finns på Google Cloud. Det betyder att ditt råa innehåll är otillgängligt för alla, inklusive Omi-personal eller Google, direkt från databasen.';

  @override
  String get endToEndEncryption => 'End-to-end-kryptering';

  @override
  String get e2eeCardDescription =>
      'Aktivera för maximal säkerhet där endast du kan komma åt dina data. Tryck för att lära dig mer.';

  @override
  String get dataAlwaysEncrypted => 'Oavsett nivå är dina data alltid krypterade i vila och under överföring.';

  @override
  String get readOnlyScope => 'Endast läsning';

  @override
  String get fullAccessScope => 'Full åtkomst';

  @override
  String get readScope => 'Läs';

  @override
  String get writeScope => 'Skriv';

  @override
  String get apiKeyCreated => 'API-nyckel skapad!';

  @override
  String get saveKeyWarning => 'Spara denna nyckel nu! Du kommer inte att kunna se den igen.';

  @override
  String get yourApiKey => 'DIN API-NYCKEL';

  @override
  String get tapToCopy => 'Tryck för att kopiera';

  @override
  String get copyKey => 'Kopiera nyckel';

  @override
  String get createApiKey => 'Skapa API-nyckel';

  @override
  String get accessDataProgrammatically => 'Få programmatisk åtkomst till dina data';

  @override
  String get keyNameLabel => 'NYCKELNAMN';

  @override
  String get keyNamePlaceholder => 't.ex., Min app-integration';

  @override
  String get permissionsLabel => 'BEHÖRIGHETER';

  @override
  String get permissionsInfoNote => 'R = Läs, W = Skriv. Standard endast läsning om inget är valt.';

  @override
  String get developerApi => 'Utvecklar-API';

  @override
  String get createAKeyToGetStarted => 'Skapa en nyckel för att komma igång';

  @override
  String errorWithMessage(String error) {
    return 'Fel: $error';
  }

  @override
  String get omiTraining => 'Omi Träning';

  @override
  String get trainingDataProgram => 'Träningsdataprogram';

  @override
  String get getOmiUnlimitedFree => 'Få Omi Unlimited gratis genom att bidra med dina data för att träna AI-modeller.';

  @override
  String get trainingDataBullets =>
      '• Dina data hjälper till att förbättra AI-modeller\n• Endast icke-känsliga data delas\n• Helt transparent process';

  @override
  String get learnMoreAtOmiTraining => 'Läs mer på omi.me/training';

  @override
  String get agreeToContributeData => 'Jag förstår och godkänner att bidra med mina data för AI-träning';

  @override
  String get submitRequest => 'Skicka förfrågan';

  @override
  String get thankYouRequestUnderReview => 'Tack! Din förfrågan granskas. Vi meddelar dig när den har godkänts.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'Din plan förblir aktiv till $date. Efter det förlorar du tillgång till dina obegränsade funktioner. Är du säker?';
  }

  @override
  String get confirmCancellation => 'Bekräfta avbokning';

  @override
  String get keepMyPlan => 'Behåll min plan';

  @override
  String get subscriptionSetToCancel => 'Din prenumeration är inställd på att avslutas vid periodens slut.';

  @override
  String get switchedToOnDevice => 'Bytte till transkription på enheten';

  @override
  String get couldNotSwitchToFreePlan => 'Kunde inte byta till gratisplan. Försök igen.';

  @override
  String get couldNotLoadPlans => 'Kunde inte ladda tillgängliga planer. Försök igen.';

  @override
  String get selectedPlanNotAvailable => 'Vald plan är inte tillgänglig. Försök igen.';

  @override
  String get upgradeToAnnualPlan => 'Uppgradera till årsplan';

  @override
  String get importantBillingInfo => 'Viktig faktureringsinformation:';

  @override
  String get monthlyPlanContinues => 'Din nuvarande månadsplan fortsätter till slutet av din faktureringsperiod';

  @override
  String get paymentMethodCharged => 'Din befintliga betalningsmetod debiteras automatiskt när din månadsplan avslutas';

  @override
  String get annualSubscriptionStarts => 'Din 12-månaders årsprenumeration startar automatiskt efter debiteringen';

  @override
  String get thirteenMonthsCoverage => 'Du får totalt 13 månaders täckning (nuvarande månad + 12 månader årligen)';

  @override
  String get confirmUpgrade => 'Bekräfta uppgradering';

  @override
  String get confirmPlanChange => 'Bekräfta planändring';

  @override
  String get confirmAndProceed => 'Bekräfta och fortsätt';

  @override
  String get upgradeScheduled => 'Uppgradering schemalagd';

  @override
  String get changePlan => 'Ändra plan';

  @override
  String get upgradeAlreadyScheduled => 'Din uppgradering till årsplanen är redan schemalagd';

  @override
  String get youAreOnUnlimitedPlan => 'Du har den obegränsade planen.';

  @override
  String get yourOmiUnleashed => 'Din Omi, frigjord. Bli obegränsad för oändliga möjligheter.';

  @override
  String planEndedOn(String date) {
    return 'Din plan avslutades $date.\\nPrenumerera igen nu - du debiteras omedelbart för en ny faktureringsperiod.';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'Din plan är inställd på att avbrytas $date.\\nPrenumerera igen nu för att behålla dina fördelar - ingen avgift till $date.';
  }

  @override
  String get annualPlanStartsAutomatically => 'Din årsplan startar automatiskt när din månadsplan avslutas.';

  @override
  String planRenewsOn(String date) {
    return 'Din plan förnyas $date.';
  }

  @override
  String get unlimitedConversations => 'Obegränsade samtal';

  @override
  String get askOmiAnything => 'Fråga Omi vad som helst om ditt liv';

  @override
  String get unlockOmiInfiniteMemory => 'Lås upp Omis oändliga minne';

  @override
  String get youreOnAnnualPlan => 'Du har årsplanen';

  @override
  String get alreadyBestValuePlan => 'Du har redan den bästa värdeplanen. Inga ändringar behövs.';

  @override
  String get unableToLoadPlans => 'Kan inte ladda planer';

  @override
  String get checkConnectionTryAgain => 'Kontrollera din anslutning och försök igen';

  @override
  String get useFreePlan => 'Använd gratisplan';

  @override
  String get continueText => 'Fortsätt';

  @override
  String get resubscribe => 'Prenumerera igen';

  @override
  String get couldNotOpenPaymentSettings => 'Kunde inte öppna betalningsinställningar. Försök igen.';

  @override
  String get managePaymentMethod => 'Hantera betalningsmetod';

  @override
  String get cancelSubscription => 'Avsluta prenumeration';

  @override
  String endsOnDate(String date) {
    return 'Slutar $date';
  }

  @override
  String get active => 'Aktiv';

  @override
  String get freePlan => 'Gratisplan';

  @override
  String get configure => 'Konfigurera';

  @override
  String get privacyInformation => 'Integritetsinformation';

  @override
  String get yourPrivacyMattersToUs => 'Din integritet är viktig för oss';

  @override
  String get privacyIntroText =>
      'På Omi tar vi din integritet på största allvar. Vi vill vara transparenta om de uppgifter vi samlar in och hur vi använder dem. Här är vad du behöver veta:';

  @override
  String get whatWeTrack => 'Vad vi spårar';

  @override
  String get anonymityAndPrivacy => 'Anonymitet och integritet';

  @override
  String get optInAndOptOutOptions => 'Samtyckes- och avanmälningsalternativ';

  @override
  String get ourCommitment => 'Vårt åtagande';

  @override
  String get commitmentText =>
      'Vi förbinder oss att endast använda de uppgifter vi samlar in för att göra Omi till en bättre produkt för dig. Din integritet och ditt förtroende är av största vikt för oss.';

  @override
  String get thankYouText =>
      'Tack för att du är en uppskattad användare av Omi. Om du har frågor eller funderingar, kontakta oss gärna på team@basedhardware.com.';

  @override
  String get wifiSyncSettings => 'WiFi-synkroniseringsinställningar';

  @override
  String get enterHotspotCredentials => 'Ange din telefons hotspot-uppgifter';

  @override
  String get wifiSyncUsesHotspot =>
      'WiFi-synkronisering använder din telefon som hotspot. Hitta namnet och lösenordet i Inställningar > Internetdelning.';

  @override
  String get hotspotNameSsid => 'Hotspotnamn (SSID)';

  @override
  String get exampleIphoneHotspot => 't.ex. iPhone Hotspot';

  @override
  String get password => 'Lösenord';

  @override
  String get enterHotspotPassword => 'Ange hotspot-lösenord';

  @override
  String get saveCredentials => 'Spara uppgifter';

  @override
  String get clearCredentials => 'Rensa uppgifter';

  @override
  String get pleaseEnterHotspotName => 'Ange ett hotspotnamn';

  @override
  String get wifiCredentialsSaved => 'WiFi-uppgifter sparade';

  @override
  String get wifiCredentialsCleared => 'WiFi-uppgifter rensade';

  @override
  String summaryGeneratedForDate(String date) {
    return 'Sammanfattning genererad för $date';
  }

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'Kunde inte generera sammanfattning. Se till att du har samtal för den dagen.';

  @override
  String get summaryNotFound => 'Sammanfattning hittades inte';

  @override
  String get yourDaysJourney => 'Din dags resa';

  @override
  String get highlights => 'Höjdpunkter';

  @override
  String get unresolvedQuestions => 'Olösta frågor';

  @override
  String get decisions => 'Beslut';

  @override
  String get learnings => 'Lärdomar';

  @override
  String get autoDeletesAfterThreeDays => 'Raderas automatiskt efter 3 dagar.';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'Kunskapsgraf borttagen';

  @override
  String get exportStartedMayTakeFewSeconds => 'Export startad. Detta kan ta några sekunder...';

  @override
  String get knowledgeGraphDeleteDescription =>
      'Detta kommer att radera alla härledda kunskapsgrafdata (noder och anslutningar). Dina ursprungliga minnen förblir säkra. Grafen kommer att byggas om över tid eller vid nästa begäran.';

  @override
  String get configureDailySummaryDigest => 'Konfigurera din dagliga uppgiftssammanfattning';

  @override
  String accessesDataTypes(String dataTypes) {
    return 'Åtkomst till $dataTypes';
  }

  @override
  String triggeredByType(String triggerType) {
    return 'utlöst av $triggerType';
  }

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription och är $triggerDescription.';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return 'Är $triggerDescription.';
  }

  @override
  String get noSpecificDataAccessConfigured => 'Ingen specifik dataåtkomst konfigurerad.';

  @override
  String get basicPlanDescription => '1 200 premium-minuter + obegränsat på enheten';

  @override
  String get minutes => 'minuter';

  @override
  String get omiHas => 'Omi har:';

  @override
  String get premiumMinutesUsed => 'Premium-minuter använda.';

  @override
  String get setupOnDevice => 'Konfigurera på enheten';

  @override
  String get forUnlimitedFreeTranscription => 'för obegränsad gratis transkription.';

  @override
  String premiumMinsLeft(int count) {
    return '$count premium-minuter kvar.';
  }

  @override
  String get alwaysAvailable => 'alltid tillgängligt.';

  @override
  String get importHistory => 'Importhistorik';

  @override
  String get noImportsYet => 'Inga importer ännu';

  @override
  String get selectZipFileToImport => 'Välj .zip-filen att importera!';

  @override
  String get otherDevicesComingSoon => 'Andra enheter kommer snart';

  @override
  String get deleteAllLimitlessConversations => 'Ta bort alla Limitless-konversationer?';

  @override
  String get deleteAllLimitlessWarning =>
      'Detta kommer permanent att radera alla konversationer importerade från Limitless. Denna åtgärd kan inte ångras.';

  @override
  String deletedLimitlessConversations(int count) {
    return 'Raderade $count Limitless-konversationer';
  }

  @override
  String get failedToDeleteConversations => 'Kunde inte ta bort konversationer';

  @override
  String get deleteImportedData => 'Ta bort importerad data';

  @override
  String get statusPending => 'Väntar';

  @override
  String get statusProcessing => 'Bearbetar';

  @override
  String get statusCompleted => 'Slutfört';

  @override
  String get statusFailed => 'Misslyckades';

  @override
  String nConversations(int count) {
    return '$count konversationer';
  }

  @override
  String get pleaseEnterName => 'Ange ett namn';

  @override
  String get nameMustBeBetweenCharacters => 'Namnet måste vara mellan 2 och 40 tecken';

  @override
  String get deleteSampleQuestion => 'Ta bort prov?';

  @override
  String deleteSampleConfirmation(String name) {
    return 'Är du säker på att du vill ta bort ${name}s prov?';
  }

  @override
  String get confirmDeletion => 'Bekräfta borttagning';

  @override
  String deletePersonConfirmation(String name) {
    return 'Är du säker på att du vill ta bort $name? Detta tar också bort alla tillhörande röstprover.';
  }

  @override
  String get howItWorksTitle => 'Hur fungerar det?';

  @override
  String get howPeopleWorks =>
      'När en person har skapats kan du gå till en konversationsutskrift och tilldela dem deras motsvarande segment, på så sätt kommer Omi att kunna känna igen deras tal också!';

  @override
  String get tapToDelete => 'Tryck för att ta bort';

  @override
  String get newTag => 'NY';

  @override
  String get needHelpChatWithUs => 'Behöver du hjälp? Chatta med oss';

  @override
  String get localStorageEnabled => 'Lokal lagring aktiverad';

  @override
  String get localStorageDisabled => 'Lokal lagring inaktiverad';

  @override
  String failedToUpdateSettings(String error) {
    return 'Det gick inte att uppdatera inställningarna: $error';
  }

  @override
  String get privacyNotice => 'Sekretessmeddelande';

  @override
  String get recordingsMayCaptureOthers =>
      'Inspelningar kan fånga andras röster. Se till att du har samtycke från alla deltagare innan du aktiverar.';

  @override
  String get enable => 'Aktivera';

  @override
  String get storeAudioOnPhone => 'Lagra ljud på telefonen';

  @override
  String get on => 'På';

  @override
  String get storeAudioDescription =>
      'Behåll alla ljudinspelningar lagrade lokalt på din telefon. När inaktiverad sparas endast misslyckade uppladdningar för att spara lagringsutrymme.';

  @override
  String get enableLocalStorage => 'Aktivera lokal lagring';

  @override
  String get cloudStorageEnabled => 'Molnlagring aktiverad';

  @override
  String get cloudStorageDisabled => 'Molnlagring inaktiverad';

  @override
  String get enableCloudStorage => 'Aktivera molnlagring';

  @override
  String get storeAudioOnCloud => 'Lagra ljud i molnet';

  @override
  String get cloudStorageDialogMessage => 'Dina realtidsinspelningar lagras i privat molnlagring medan du talar.';

  @override
  String get storeAudioCloudDescription =>
      'Lagra dina realtidsinspelningar i privat molnlagring medan du talar. Ljud fångas upp och sparas säkert i realtid.';

  @override
  String get downloadingFirmware => 'Laddar ner firmware';

  @override
  String get installingFirmware => 'Installerar firmware';

  @override
  String get firmwareUpdateWarning => 'Stäng inte appen eller stäng av enheten. Detta kan skada din enhet.';

  @override
  String get firmwareUpdated => 'Firmware uppdaterad';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'Starta om din $deviceName för att slutföra uppdateringen.';
  }

  @override
  String get yourDeviceIsUpToDate => 'Din enhet är uppdaterad';

  @override
  String get currentVersion => 'Nuvarande version';

  @override
  String get latestVersion => 'Senaste versionen';

  @override
  String get whatsNew => 'Nyheter';

  @override
  String get installUpdate => 'Installera uppdatering';

  @override
  String get updateNow => 'Uppdatera nu';

  @override
  String get updateGuide => 'Uppdateringsguide';

  @override
  String get checkingForUpdates => 'Söker efter uppdateringar';

  @override
  String get checkingFirmwareVersion => 'Kontrollerar firmware-version...';

  @override
  String get firmwareUpdate => 'Firmwareuppdatering';

  @override
  String get payments => 'Betalningar';

  @override
  String get connectPaymentMethodInfo =>
      'Anslut en betalningsmetod nedan för att börja ta emot utbetalningar för dina appar.';

  @override
  String get selectedPaymentMethod => 'Vald betalningsmetod';

  @override
  String get availablePaymentMethods => 'Tillgängliga betalningsmetoder';

  @override
  String get activeStatus => 'Aktiv';

  @override
  String get connectedStatus => 'Ansluten';

  @override
  String get notConnectedStatus => 'Inte ansluten';

  @override
  String get setActive => 'Ange som aktiv';

  @override
  String get getPaidThroughStripe => 'Få betalt för dina appförsäljningar genom Stripe';

  @override
  String get monthlyPayouts => 'Månatliga utbetalningar';

  @override
  String get monthlyPayoutsDescription =>
      'Få månatliga utbetalningar direkt till ditt konto när du når \$10 i intäkter';

  @override
  String get secureAndReliable => 'Säkert och pålitligt';

  @override
  String get stripeSecureDescription => 'Stripe säkerställer säkra och snabba överföringar av dina appintäkter';

  @override
  String get selectYourCountry => 'Välj ditt land';

  @override
  String get countrySelectionPermanent => 'Ditt landsval är permanent och kan inte ändras senare.';

  @override
  String get byClickingConnectNow => 'Genom att klicka på \"Anslut nu\" godkänner du';

  @override
  String get stripeConnectedAccountAgreement => 'Stripe Connected Account-avtal';

  @override
  String get errorConnectingToStripe => 'Fel vid anslutning till Stripe! Försök igen senare.';

  @override
  String get connectingYourStripeAccount => 'Ansluter ditt Stripe-konto';

  @override
  String get stripeOnboardingInstructions =>
      'Slutför Stripe-onboardingprocessen i din webbläsare. Denna sida uppdateras automatiskt när processen är klar.';

  @override
  String get failedTryAgain => 'Misslyckades? Försök igen';

  @override
  String get illDoItLater => 'Jag gör det senare';

  @override
  String get successfullyConnected => 'Framgångsrikt ansluten!';

  @override
  String get stripeReadyForPayments =>
      'Ditt Stripe-konto är nu redo att ta emot betalningar. Du kan börja tjäna pengar på dina appförsäljningar direkt.';

  @override
  String get updateStripeDetails => 'Uppdatera Stripe-uppgifter';

  @override
  String get errorUpdatingStripeDetails => 'Fel vid uppdatering av Stripe-uppgifter! Försök igen senare.';

  @override
  String get updatePayPal => 'Uppdatera PayPal';

  @override
  String get setUpPayPal => 'Konfigurera PayPal';

  @override
  String get updatePayPalAccountDetails => 'Uppdatera dina PayPal-kontouppgifter';

  @override
  String get connectPayPalToReceivePayments =>
      'Anslut ditt PayPal-konto för att börja ta emot betalningar för dina appar';

  @override
  String get paypalEmail => 'PayPal-e-post';

  @override
  String get paypalMeLink => 'PayPal.me-länk';

  @override
  String get stripeRecommendation =>
      'Om Stripe är tillgängligt i ditt land rekommenderar vi starkt att använda det för snabbare och enklare utbetalningar.';

  @override
  String get updatePayPalDetails => 'Uppdatera PayPal-uppgifter';

  @override
  String get savePayPalDetails => 'Spara PayPal-uppgifter';

  @override
  String get pleaseEnterPayPalEmail => 'Ange din PayPal-e-post';

  @override
  String get pleaseEnterPayPalMeLink => 'Ange din PayPal.me-länk';

  @override
  String get doNotIncludeHttpInLink => 'Inkludera inte http eller https eller www i länken';

  @override
  String get pleaseEnterValidPayPalMeLink => 'Ange en giltig PayPal.me-länk';

  @override
  String get pleaseEnterValidEmail => 'Ange en giltig e-postadress';

  @override
  String get syncingYourRecordings => 'Synkroniserar dina inspelningar';

  @override
  String get syncYourRecordings => 'Synkronisera dina inspelningar';

  @override
  String get syncNow => 'Synkronisera nu';

  @override
  String get error => 'Fel';

  @override
  String get speechSamples => 'Röstprover';

  @override
  String additionalSampleIndex(String index) {
    return 'Ytterligare prov $index';
  }

  @override
  String durationSeconds(String seconds) {
    return 'Längd: $seconds sekunder';
  }

  @override
  String get additionalSpeechSampleRemoved => 'Ytterligare röstprov borttaget';

  @override
  String get consentDataMessage =>
      'Genom att fortsätta kommer all data du delar med denna app (inklusive dina konversationer, inspelningar och personlig information) att lagras säkert på våra servrar för att ge dig AI-drivna insikter och aktivera alla appfunktioner.';

  @override
  String get tasksEmptyStateMessage =>
      'Uppgifter från dina konversationer visas här.\nTryck på + för att skapa manuellt.';

  @override
  String get clearChatAction => 'Rensa chatt';

  @override
  String get enableApps => 'Aktivera appar';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => 'visa mer ↓';

  @override
  String get showLess => 'visa mindre ↑';

  @override
  String get loadingYourRecording => 'Laddar din inspelning...';

  @override
  String get photoDiscardedMessage => 'Detta foto kasserades eftersom det inte var betydelsefullt.';

  @override
  String get analyzing => 'Analyserar...';

  @override
  String get searchCountries => 'Sök länder...';

  @override
  String get checkingAppleWatch => 'Kontrollerar Apple Watch...';

  @override
  String get installOmiOnAppleWatch => 'Installera Omi på din\nApple Watch';

  @override
  String get installOmiOnAppleWatchDescription =>
      'För att använda din Apple Watch med Omi måste du först installera Omi-appen på din klocka.';

  @override
  String get openOmiOnAppleWatch => 'Öppna Omi på din\nApple Watch';

  @override
  String get openOmiOnAppleWatchDescription =>
      'Omi-appen är installerad på din Apple Watch. Öppna den och tryck på Start för att börja.';

  @override
  String get openWatchApp => 'Öppna Watch-appen';

  @override
  String get iveInstalledAndOpenedTheApp => 'Jag har installerat och öppnat appen';

  @override
  String get unableToOpenWatchApp =>
      'Kan inte öppna Apple Watch-appen. Öppna Watch-appen manuellt på din Apple Watch och installera Omi från avsnittet \"Tillgängliga appar\".';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch ansluten!';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch är fortfarande inte nåbar. Se till att Omi-appen är öppen på din klocka.';

  @override
  String errorCheckingConnection(String error) {
    return 'Fel vid kontroll av anslutning: $error';
  }

  @override
  String get muted => 'Tystad';

  @override
  String get processNow => 'Bearbeta nu';

  @override
  String get finishedConversation => 'Konversation avslutad?';

  @override
  String get stopRecordingConfirmation =>
      'Är du säker på att du vill stoppa inspelningen och sammanfatta konversationen nu?';

  @override
  String get conversationEndsManually => 'Konversationen avslutas endast manuellt.';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'Konversationen sammanfattas efter $minutes minut$suffix utan tal.';
  }

  @override
  String get dontAskAgain => 'Fråga inte igen';

  @override
  String get waitingForTranscriptOrPhotos => 'Väntar på transkription eller foton...';

  @override
  String get noSummaryYet => 'Ingen sammanfattning än';

  @override
  String hints(String text) {
    return 'Tips: $text';
  }

  @override
  String get testConversationPrompt => 'Testa en samtalsprompt';

  @override
  String get prompt => 'Prompt';

  @override
  String get result => 'Resultat:';

  @override
  String get compareTranscripts => 'Jämför transkriptioner';

  @override
  String get notHelpful => 'Inte hjälpsam';

  @override
  String get exportTasksWithOneTap => 'Exportera uppgifter med ett tryck!';

  @override
  String get inProgress => 'Pågår';

  @override
  String get photos => 'Foton';

  @override
  String get rawData => 'Rådata';

  @override
  String get content => 'Innehåll';

  @override
  String get noContentToDisplay => 'Inget innehåll att visa';

  @override
  String get noSummary => 'Ingen sammanfattning';

  @override
  String get updateOmiFirmware => 'Uppdatera omi-firmware';

  @override
  String get anErrorOccurredTryAgain => 'Ett fel uppstod. Försök igen.';

  @override
  String get welcomeBackSimple => 'Välkommen tillbaka';

  @override
  String get addVocabularyDescription => 'Lägg till ord som Omi ska känna igen under transkription.';

  @override
  String get enterWordsCommaSeparated => 'Ange ord (kommaseparerade)';

  @override
  String get whenToReceiveDailySummary => 'När du vill få din dagliga sammanfattning';

  @override
  String get checkingNextSevenDays => 'Kontrollerar de kommande 7 dagarna';

  @override
  String failedToDeleteError(String error) {
    return 'Det gick inte att radera: $error';
  }

  @override
  String get developerApiKeys => 'Utvecklar-API-nycklar';

  @override
  String get noApiKeysCreateOne => 'Inga API-nycklar. Skapa en för att komma igång.';

  @override
  String get commandRequired => '⌘ krävs';

  @override
  String get spaceKey => 'Mellanslag';

  @override
  String loadMoreRemaining(String count) {
    return 'Ladda mer ($count kvar)';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'Topp $percentile% användare';
  }

  @override
  String get wrappedMinutes => 'minuter';

  @override
  String get wrappedConversations => 'konversationer';

  @override
  String get wrappedDaysActive => 'aktiva dagar';

  @override
  String get wrappedYouTalkedAbout => 'Du pratade om';

  @override
  String get wrappedActionItems => 'Uppgifter';

  @override
  String get wrappedTasksCreated => 'skapade uppgifter';

  @override
  String get wrappedCompleted => 'slutförda';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% slutförandegrad';
  }

  @override
  String get wrappedYourTopDays => 'Dina bästa dagar';

  @override
  String get wrappedBestMoments => 'Bästa stunderna';

  @override
  String get wrappedMyBuddies => 'Mina vänner';

  @override
  String get wrappedCouldntStopTalkingAbout => 'Kunde inte sluta prata om';

  @override
  String get wrappedShow => 'SERIE';

  @override
  String get wrappedMovie => 'FILM';

  @override
  String get wrappedBook => 'BOK';

  @override
  String get wrappedCelebrity => 'KÄNDIS';

  @override
  String get wrappedFood => 'MAT';

  @override
  String get wrappedMovieRecs => 'Filmrekommendationer till vänner';

  @override
  String get wrappedBiggest => 'Största';

  @override
  String get wrappedStruggle => 'Utmaning';

  @override
  String get wrappedButYouPushedThrough => 'Men du klarade det 💪';

  @override
  String get wrappedWin => 'Vinst';

  @override
  String get wrappedYouDidIt => 'Du klarade det! 🎉';

  @override
  String get wrappedTopPhrases => 'Topp 5 fraser';

  @override
  String get wrappedMins => 'min';

  @override
  String get wrappedConvos => 'konversationer';

  @override
  String get wrappedDays => 'dagar';

  @override
  String get wrappedMyBuddiesLabel => 'MINA VÄNNER';

  @override
  String get wrappedObsessionsLabel => 'BESATTHETER';

  @override
  String get wrappedStruggleLabel => 'UTMANING';

  @override
  String get wrappedWinLabel => 'VINST';

  @override
  String get wrappedTopPhrasesLabel => 'TOPP FRASER';

  @override
  String get wrappedLetsHitRewind => 'Låt oss spola tillbaka ditt';

  @override
  String get wrappedGenerateMyWrapped => 'Generera min Wrapped';

  @override
  String get wrappedProcessingDefault => 'Bearbetar...';

  @override
  String get wrappedCreatingYourStory => 'Skapar din\n2025-historia...';

  @override
  String get wrappedSomethingWentWrong => 'Något gick\nfel';

  @override
  String get wrappedAnErrorOccurred => 'Ett fel uppstod';

  @override
  String get wrappedTryAgain => 'Försök igen';

  @override
  String get wrappedNoDataAvailable => 'Ingen data tillgänglig';

  @override
  String get wrappedOmiLifeRecap => 'Omi livssammanfattning';

  @override
  String get wrappedSwipeUpToBegin => 'Svep uppåt för att börja';

  @override
  String get wrappedShareText => 'Min 2025, ihågkommen av Omi ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare => 'Delning misslyckades. Försök igen.';

  @override
  String get wrappedFailedToStartGeneration => 'Kunde inte starta generering. Försök igen.';

  @override
  String get wrappedStarting => 'Startar...';

  @override
  String get wrappedShare => 'Dela';

  @override
  String get wrappedShareYourWrapped => 'Dela din Wrapped';

  @override
  String get wrappedMy2025 => 'Min 2025';

  @override
  String get wrappedRememberedByOmi => 'ihågkommen av Omi';

  @override
  String get wrappedMostFunDay => 'Roligast';

  @override
  String get wrappedMostProductiveDay => 'Mest produktiv';

  @override
  String get wrappedMostIntenseDay => 'Mest intensiv';

  @override
  String get wrappedFunniestMoment => 'Roligast';

  @override
  String get wrappedMostCringeMoment => 'Mest pinsam';

  @override
  String get wrappedMinutesLabel => 'minuter';

  @override
  String get wrappedConversationsLabel => 'konversationer';

  @override
  String get wrappedDaysActiveLabel => 'aktiva dagar';

  @override
  String get wrappedTasksGenerated => 'uppgifter genererade';

  @override
  String get wrappedTasksCompleted => 'uppgifter slutförda';

  @override
  String get wrappedTopFivePhrases => 'Topp 5 fraser';

  @override
  String get wrappedAGreatDay => 'En fantastisk dag';

  @override
  String get wrappedGettingItDone => 'Få det gjort';

  @override
  String get wrappedAChallenge => 'En utmaning';

  @override
  String get wrappedAHilariousMoment => 'Ett roligt ögonblick';

  @override
  String get wrappedThatAwkwardMoment => 'Det pinsamma ögonblicket';

  @override
  String get wrappedYouHadFunnyMoments => 'Du hade roliga ögonblick i år!';

  @override
  String get wrappedWeveAllBeenThere => 'Vi har alla varit där!';

  @override
  String get wrappedFriend => 'Vän';

  @override
  String get wrappedYourBuddy => 'Din kompis!';

  @override
  String get wrappedNotMentioned => 'Inte nämnt';

  @override
  String get wrappedTheHardPart => 'Den svåra delen';

  @override
  String get wrappedPersonalGrowth => 'Personlig utveckling';

  @override
  String get wrappedFunDay => 'Rolig';

  @override
  String get wrappedProductiveDay => 'Produktiv';

  @override
  String get wrappedIntenseDay => 'Intensiv';

  @override
  String get wrappedFunnyMomentTitle => 'Roligt ögonblick';

  @override
  String get wrappedCringeMomentTitle => 'Pinsamt ögonblick';

  @override
  String get wrappedYouTalkedAboutBadge => 'Du pratade om';

  @override
  String get wrappedCompletedLabel => 'Slutförd';

  @override
  String get wrappedMyBuddiesCard => 'Mina vänner';

  @override
  String get wrappedBuddiesLabel => 'VÄNNER';

  @override
  String get wrappedObsessionsLabelUpper => 'PASSIONER';

  @override
  String get wrappedStruggleLabelUpper => 'KAMP';

  @override
  String get wrappedWinLabelUpper => 'VINST';

  @override
  String get wrappedTopPhrasesLabelUpper => 'TOPP FRASER';

  @override
  String get wrappedYourHeader => 'Dina';

  @override
  String get wrappedTopDaysHeader => 'Bästa dagar';

  @override
  String get wrappedYourTopDaysBadge => 'Dina bästa dagar';

  @override
  String get wrappedBestHeader => 'Bästa';

  @override
  String get wrappedMomentsHeader => 'Ögonblick';

  @override
  String get wrappedBestMomentsBadge => 'Bästa ögonblick';

  @override
  String get wrappedBiggestHeader => 'Största';

  @override
  String get wrappedStruggleHeader => 'Kamp';

  @override
  String get wrappedWinHeader => 'Vinst';

  @override
  String get wrappedButYouPushedThroughEmoji => 'Men du klarade det 💪';

  @override
  String get wrappedYouDidItEmoji => 'Du klarade det! 🎉';

  @override
  String get wrappedHours => 'timmar';

  @override
  String get wrappedActions => 'åtgärder';

  @override
  String get multipleSpeakersDetected => 'Flera talare upptäckta';

  @override
  String get multipleSpeakersDescription =>
      'Det verkar som att det finns flera talare i inspelningen. Se till att du är på en lugn plats och försök igen.';

  @override
  String get invalidRecordingDetected => 'Ogiltig inspelning upptäckt';

  @override
  String get notEnoughSpeechDescription => 'Inte tillräckligt med tal upptäcktes. Vänligen prata mer och försök igen.';

  @override
  String get speechDurationDescription => 'Se till att du pratar minst 5 sekunder och inte mer än 90.';

  @override
  String get connectionLostDescription => 'Anslutningen avbröts. Kontrollera din internetanslutning och försök igen.';

  @override
  String get howToTakeGoodSample => 'Hur tar man ett bra prov?';

  @override
  String get goodSampleInstructions =>
      '1. Se till att du är på en lugn plats.\n2. Prata tydligt och naturligt.\n3. Se till att din enhet är i sin naturliga position på halsen.\n\nNär det är skapat kan du alltid förbättra det eller göra det igen.';

  @override
  String get noDeviceConnectedUseMic => 'Ingen enhet ansluten. Telefonens mikrofon kommer att användas.';

  @override
  String get doItAgain => 'Gör det igen';

  @override
  String get listenToSpeechProfile => 'Lyssna på min röstprofil ➡️';

  @override
  String get recognizingOthers => 'Känner igen andra 👀';

  @override
  String get keepGoingGreat => 'Fortsätt, du gör det jättebra';

  @override
  String get somethingWentWrongTryAgain => 'Något gick fel! Försök igen senare.';

  @override
  String get uploadingVoiceProfile => 'Laddar upp din röstprofil....';

  @override
  String get memorizingYourVoice => 'Memorerar din röst...';

  @override
  String get personalizingExperience => 'Anpassar din upplevelse...';

  @override
  String get keepSpeakingUntil100 => 'Fortsätt prata tills du når 100%.';

  @override
  String get greatJobAlmostThere => 'Bra jobbat, du är nästan klar';

  @override
  String get soCloseJustLittleMore => 'Så nära, bara lite till';

  @override
  String get notificationFrequency => 'Aviseringsfrekvens';

  @override
  String get controlNotificationFrequency => 'Kontrollera hur ofta Omi skickar proaktiva aviseringar till dig.';

  @override
  String get yourScore => 'Din poäng';

  @override
  String get dailyScoreBreakdown => 'Daglig poängöversikt';

  @override
  String get todaysScore => 'Dagens poäng';

  @override
  String get tasksCompleted => 'Uppgifter slutförda';

  @override
  String get completionRate => 'Slutförandegrad';

  @override
  String get howItWorks => 'Så fungerar det';

  @override
  String get dailyScoreExplanation =>
      'Din dagliga poäng baseras på uppgiftsslutförande. Slutför dina uppgifter för att förbättra din poäng!';

  @override
  String get notificationFrequencyDescription =>
      'Kontrollera hur ofta Omi skickar dig proaktiva aviseringar och påminnelser.';

  @override
  String get sliderOff => 'Av';

  @override
  String get sliderMax => 'Max.';

  @override
  String summaryGeneratedFor(String date) {
    return 'Sammanfattning genererad för $date';
  }

  @override
  String get failedToGenerateSummary =>
      'Kunde inte generera sammanfattning. Se till att du har konversationer för den dagen.';

  @override
  String get recap => 'Sammanfattning';

  @override
  String deleteQuoted(String name) {
    return 'Ta bort \"$name\"';
  }

  @override
  String moveConversationsTo(int count) {
    return 'Flytta $count konversationer till:';
  }

  @override
  String get noFolder => 'Ingen mapp';

  @override
  String get removeFromAllFolders => 'Ta bort från alla mappar';

  @override
  String get buildAndShareYourCustomApp => 'Bygg och dela din anpassade app';

  @override
  String get searchAppsPlaceholder => 'Sök bland 1500+ appar';

  @override
  String get filters => 'Filter';

  @override
  String get frequencyOff => 'Av';

  @override
  String get frequencyMinimal => 'Minimal';

  @override
  String get frequencyLow => 'Låg';

  @override
  String get frequencyBalanced => 'Balanserad';

  @override
  String get frequencyHigh => 'Hög';

  @override
  String get frequencyMaximum => 'Maximal';

  @override
  String get frequencyDescOff => 'Inga proaktiva aviseringar';

  @override
  String get frequencyDescMinimal => 'Endast kritiska påminnelser';

  @override
  String get frequencyDescLow => 'Endast viktiga uppdateringar';

  @override
  String get frequencyDescBalanced => 'Regelbundna hjälpsamma påminnelser';

  @override
  String get frequencyDescHigh => 'Frekventa kontroller';

  @override
  String get frequencyDescMaximum => 'Håll dig ständigt engagerad';

  @override
  String get clearChatQuestion => 'Rensa chatt?';

  @override
  String get syncingMessages => 'Synkroniserar meddelanden med servern...';

  @override
  String get chatAppsTitle => 'Chattappar';

  @override
  String get selectApp => 'Välj app';

  @override
  String get noChatAppsEnabled => 'Inga chattappar aktiverade.\nTryck på \"Aktivera appar\" för att lägga till.';

  @override
  String get disable => 'Inaktivera';

  @override
  String get photoLibrary => 'Bildbibliotek';

  @override
  String get chooseFile => 'Välj fil';

  @override
  String get configureAiPersona => 'Konfigurera din AI-persona';

  @override
  String get connectAiAssistantsToYourData => 'Anslut AI-assistenter till dina data';

  @override
  String get oAuth => 'OAuth';

  @override
  String get trackYourGoalsOnHomepage => 'Spåra dina personliga mål på startsidan';

  @override
  String get deleteRecording => 'Ta bort inspelning';

  @override
  String get thisCannotBeUndone => 'Detta kan inte ångras.';

  @override
  String get sdCard => 'SD-kort';

  @override
  String get fromSd => 'Från SD';

  @override
  String get limitless => 'Limitless';

  @override
  String get fastTransfer => 'Snabb överföring';

  @override
  String get syncingStatus => 'Synkroniserar';

  @override
  String get failedStatus => 'Misslyckades';

  @override
  String etaLabel(String time) {
    return 'Beräknad tid: $time';
  }

  @override
  String get transferMethod => 'Överföringsmetod';

  @override
  String get fast => 'Snabb';

  @override
  String get ble => 'BLE';

  @override
  String get phone => 'Telefon';

  @override
  String get cancelSync => 'Avbryt synkronisering';

  @override
  String get cancelSyncMessage => 'Data som redan laddats ned kommer att sparas. Du kan återuppta senare.';

  @override
  String get syncCancelled => 'Synkronisering avbruten';

  @override
  String get deleteProcessedFiles => 'Ta bort behandlade filer';

  @override
  String get processedFilesDeleted => 'Behandlade filer borttagna';

  @override
  String get wifiEnableFailed => 'Kunde inte aktivera WiFi på enheten. Försök igen.';

  @override
  String get deviceNoFastTransfer => 'Din enhet stöder inte snabb överföring. Använd Bluetooth istället.';

  @override
  String get enableHotspotMessage => 'Aktivera telefonens hotspot och försök igen.';

  @override
  String get transferStartFailed => 'Kunde inte starta överföringen. Försök igen.';

  @override
  String get deviceNotResponding => 'Enheten svarar inte. Försök igen.';

  @override
  String get invalidWifiCredentials => 'Ogiltiga WiFi-uppgifter. Kontrollera dina hotspot-inställningar.';

  @override
  String get wifiConnectionFailed => 'WiFi-anslutningen misslyckades. Försök igen.';

  @override
  String get sdCardProcessing => 'SD-kortbehandling';

  @override
  String sdCardProcessingMessage(int count) {
    return 'Behandlar $count inspelning(ar). Filer kommer att tas bort från SD-kortet efteråt.';
  }

  @override
  String get process => 'Behandla';

  @override
  String get wifiSyncFailed => 'WiFi-synkronisering misslyckades';

  @override
  String get processingFailed => 'Behandlingen misslyckades';

  @override
  String get downloadingFromSdCard => 'Laddar ned från SD-kort';

  @override
  String processingProgress(int current, int total) {
    return 'Behandlar $current/$total';
  }

  @override
  String conversationsCreated(int count) {
    return '$count konversationer skapade';
  }

  @override
  String get internetRequired => 'Internet krävs';

  @override
  String get processAudio => 'Behandla ljud';

  @override
  String get start => 'Starta';

  @override
  String get noRecordings => 'Inga inspelningar';

  @override
  String get audioFromOmiWillAppearHere => 'Ljud från din Omi-enhet kommer att visas här';

  @override
  String get deleteProcessed => 'Ta bort behandlade';

  @override
  String get tryDifferentFilter => 'Prova ett annat filter';

  @override
  String get recordings => 'Inspelningar';

  @override
  String get enableRemindersAccess =>
      'Aktivera åtkomst till Påminnelser i Inställningar för att använda Apple Påminnelser';

  @override
  String todayAtTime(String time) {
    return 'Idag kl. $time';
  }

  @override
  String yesterdayAtTime(String time) {
    return 'Igår kl. $time';
  }

  @override
  String get lessThanAMinute => 'Mindre än en minut';

  @override
  String estimatedMinutes(int count) {
    return '~$count minut(er)';
  }

  @override
  String estimatedHours(int count) {
    return '~$count timme/timmar';
  }

  @override
  String estimatedTimeRemaining(String time) {
    return 'Beräknat: $time kvar';
  }

  @override
  String get summarizingConversation => 'Sammanfattar samtal...\nDetta kan ta några sekunder';

  @override
  String get resummarizingConversation => 'Sammanfattar samtal igen...\nDetta kan ta några sekunder';

  @override
  String get nothingInterestingRetry => 'Inget intressant hittades,\nvill du försöka igen?';

  @override
  String get noSummaryForConversation => 'Ingen sammanfattning tillgänglig\nför detta samtal.';

  @override
  String get unknownLocation => 'Okänd plats';

  @override
  String get couldNotLoadMap => 'Kunde inte ladda kartan';

  @override
  String get triggerConversationIntegration => 'Utlös samtal skapad-integration';

  @override
  String get webhookUrlNotSet => 'Webhook URL inte inställd';

  @override
  String get setWebhookUrlInSettings =>
      'Vänligen ställ in webhook URL i utvecklarinställningar för att använda denna funktion.';

  @override
  String get sendWebUrl => 'Skicka webb-URL';

  @override
  String get sendTranscript => 'Skicka transkription';

  @override
  String get sendSummary => 'Skicka sammanfattning';

  @override
  String get debugModeDetected => 'Felsökningsläge upptäckt';

  @override
  String get performanceReduced => 'Prestanda kan vara reducerad';

  @override
  String autoClosingInSeconds(int seconds) {
    return 'Stängs automatiskt om $seconds sekunder';
  }

  @override
  String get modelRequired => 'Modell krävs';

  @override
  String get downloadWhisperModel => 'Ladda ner en whisper-modell för att använda transkription på enheten';

  @override
  String get deviceNotCompatible => 'Din enhet är inte kompatibel med transkription på enheten';

  @override
  String get deviceRequirements => 'Din enhet uppfyller inte kraven för transkription på enheten.';

  @override
  String get willLikelyCrash => 'Att aktivera detta kommer troligen att få appen att krascha eller frysa.';

  @override
  String get transcriptionSlowerLessAccurate => 'Transkription kommer att vara betydligt långsammare och mindre exakt.';

  @override
  String get proceedAnyway => 'Fortsätt ändå';

  @override
  String get olderDeviceDetected => 'Äldre enhet upptäckt';

  @override
  String get onDeviceSlower => 'Transkription på enheten kan vara långsammare på denna enhet.';

  @override
  String get batteryUsageHigher => 'Batterianvändningen blir högre än molntranskription.';

  @override
  String get considerOmiCloud => 'Överväg att använda Omi Cloud för bättre prestanda.';

  @override
  String get highResourceUsage => 'Hög resursanvändning';

  @override
  String get onDeviceIntensive => 'Transkription på enheten är beräkningsintensiv.';

  @override
  String get batteryDrainIncrease => 'Batterianvändningen kommer att öka avsevärt.';

  @override
  String get deviceMayWarmUp => 'Enheten kan bli varm vid längre användning.';

  @override
  String get speedAccuracyLower => 'Hastighet och noggrannhet kan vara lägre än molnmodeller.';

  @override
  String get cloudProvider => 'Molnleverantör';

  @override
  String get premiumMinutesInfo =>
      '1 200 premiumminuter/månad. Fliken På enheten erbjuder obegränsad gratis transkription.';

  @override
  String get viewUsage => 'Visa användning';

  @override
  String get localProcessingInfo => 'Ljud bearbetas lokalt. Fungerar offline, mer privat, men använder mer batteri.';

  @override
  String get model => 'Modell';

  @override
  String get performanceWarning => 'Prestandavarning';

  @override
  String get largeModelWarning =>
      'Den här modellen är stor och kan krascha appen eller köras mycket långsamt på mobila enheter.\n\n\"small\" eller \"base\" rekommenderas.';

  @override
  String get usingNativeIosSpeech => 'Använder inbyggd iOS-taligenkänning';

  @override
  String get noModelDownloadRequired =>
      'Din enhets inbyggda talmotor kommer att användas. Ingen modellnedladdning krävs.';

  @override
  String get modelReady => 'Modellen är redo';

  @override
  String get redownload => 'Ladda ner igen';

  @override
  String get doNotCloseApp => 'Stäng inte appen.';

  @override
  String get downloading => 'Laddar ner...';

  @override
  String get downloadModel => 'Ladda ner modell';

  @override
  String estimatedSize(String size) {
    return 'Uppskattad storlek: ~$size MB';
  }

  @override
  String availableSpace(String space) {
    return 'Tillgängligt utrymme: $space';
  }

  @override
  String get notEnoughSpace => 'Varning: Inte tillräckligt med utrymme!';

  @override
  String get download => 'Ladda ner';

  @override
  String downloadError(String error) {
    return 'Nedladdningsfel: $error';
  }

  @override
  String get cancelled => 'Avbruten';

  @override
  String get deviceNotCompatibleTitle => 'Enhet ej kompatibel';

  @override
  String get deviceNotMeetRequirements => 'Din enhet uppfyller inte kraven för transkription på enheten.';

  @override
  String get transcriptionSlowerOnDevice => 'Transkription på enheten kan vara långsammare på denna enhet.';

  @override
  String get computationallyIntensive => 'Transkription på enheten är beräkningsintensiv.';

  @override
  String get batteryDrainSignificantly => 'Batteritömningen kommer att öka avsevärt.';

  @override
  String get premiumMinutesMonth =>
      '1 200 premiumminuter/månad. Fliken På enheten erbjuder obegränsad gratis transkription. ';

  @override
  String get audioProcessedLocally => 'Ljud behandlas lokalt. Fungerar offline, mer privat, men använder mer batteri.';

  @override
  String get languageLabel => 'Språk';

  @override
  String get modelLabel => 'Modell';

  @override
  String get modelTooLargeWarning =>
      'Denna modell är stor och kan få appen att krascha eller köra mycket långsamt på mobila enheter.\n\nsmall eller base rekommenderas.';

  @override
  String get nativeEngineNoDownload =>
      'Din enhets inbyggda talmotor kommer att användas. Ingen modellnedladdning krävs.';

  @override
  String modelReadyWithName(String model) {
    return 'Modell redo ($model)';
  }

  @override
  String get reDownload => 'Ladda ner igen';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return 'Laddar ner $model: $received / $total MB';
  }

  @override
  String preparingModel(String model) {
    return 'Förbereder $model...';
  }

  @override
  String downloadErrorWithMessage(String error) {
    return 'Nedladdningsfel: $error';
  }

  @override
  String estimatedSizeWithValue(String size) {
    return 'Uppskattad storlek: ~$size MB';
  }

  @override
  String availableSpaceWithValue(String space) {
    return 'Tillgängligt utrymme: $space';
  }

  @override
  String get omiTranscriptionOptimized =>
      'Omis inbyggda livetranskription är optimerad för realtidskonversationer med automatisk talarigenkänning och diarisering.';

  @override
  String get reset => 'Återställ';

  @override
  String get useTemplateFrom => 'Använd mall från';

  @override
  String get selectProviderTemplate => 'Välj en leverantörsmall...';

  @override
  String get quicklyPopulateResponse => 'Fyll snabbt i med känt leverantörssvarsformat';

  @override
  String get quicklyPopulateRequest => 'Fyll snabbt i med känt leverantörsförfrågningsformat';

  @override
  String get invalidJsonError => 'Ogiltig JSON';

  @override
  String downloadModelWithName(String model) {
    return 'Ladda ner modell ($model)';
  }

  @override
  String modelNameWithFile(String model) {
    return 'Modell: $model';
  }

  @override
  String get device => 'Enhet';

  @override
  String get chatAssistantsTitle => 'Chattassistenter';

  @override
  String get permissionReadConversations => 'Läs konversationer';

  @override
  String get permissionReadMemories => 'Läs minnen';

  @override
  String get permissionReadTasks => 'Läs uppgifter';

  @override
  String get permissionCreateConversations => 'Skapa konversationer';

  @override
  String get permissionCreateMemories => 'Skapa minnen';

  @override
  String get permissionTypeAccess => 'Åtkomst';

  @override
  String get permissionTypeCreate => 'Skapa';

  @override
  String get permissionTypeTrigger => 'Utlösare';

  @override
  String get permissionDescReadConversations => 'Denna app kan komma åt dina konversationer.';

  @override
  String get permissionDescReadMemories => 'Denna app kan komma åt dina minnen.';

  @override
  String get permissionDescReadTasks => 'Denna app kan komma åt dina uppgifter.';

  @override
  String get permissionDescCreateConversations => 'Denna app kan skapa nya konversationer.';

  @override
  String get permissionDescCreateMemories => 'Denna app kan skapa nya minnen.';

  @override
  String get realtimeListening => 'Realtidslyssning';

  @override
  String get setupCompleted => 'Slutfört';

  @override
  String get pleaseSelectRating => 'Välj ett betyg';

  @override
  String get writeReviewOptional => 'Skriv en recension (valfritt)';

  @override
  String get setupQuestionsIntro => 'Hjälp oss förbättra Omi genom att svara på några frågor. 🫶 💜';

  @override
  String get setupQuestionProfession => '1. Vad arbetar du med?';

  @override
  String get setupQuestionUsage => '2. Var planerar du att använda din Omi?';

  @override
  String get setupQuestionAge => '3. Vad är din åldersgrupp?';

  @override
  String get setupAnswerAllQuestions => 'Du har inte svarat på alla frågor än! 🥺';

  @override
  String get setupSkipHelp => 'Hoppa över, jag vill inte hjälpa :C';

  @override
  String get professionEntrepreneur => 'Företagare';

  @override
  String get professionSoftwareEngineer => 'Mjukvaruutvecklare';

  @override
  String get professionProductManager => 'Produktchef';

  @override
  String get professionExecutive => 'Företagsledare';

  @override
  String get professionSales => 'Försäljning';

  @override
  String get professionStudent => 'Student';

  @override
  String get usageAtWork => 'På jobbet';

  @override
  String get usageIrlEvents => 'IRL-evenemang';

  @override
  String get usageOnline => 'Online';

  @override
  String get usageSocialSettings => 'I sociala sammanhang';

  @override
  String get usageEverywhere => 'Överallt';

  @override
  String get customBackendUrlTitle => 'Anpassad server-URL';

  @override
  String get backendUrlLabel => 'Server-URL';

  @override
  String get saveUrlButton => 'Spara URL';

  @override
  String get enterBackendUrlError => 'Ange server-URL';

  @override
  String get urlMustEndWithSlashError => 'URL måste sluta med \"/\"';

  @override
  String get invalidUrlError => 'Ange en giltig URL';

  @override
  String get backendUrlSavedSuccess => 'Server-URL sparad!';

  @override
  String get signInTitle => 'Logga in';

  @override
  String get signInButton => 'Logga in';

  @override
  String get enterEmailError => 'Ange din e-postadress';

  @override
  String get invalidEmailError => 'Ange en giltig e-postadress';

  @override
  String get enterPasswordError => 'Ange ditt lösenord';

  @override
  String get passwordMinLengthError => 'Lösenordet måste vara minst 8 tecken';

  @override
  String get signInSuccess => 'Inloggning lyckades!';

  @override
  String get alreadyHaveAccountLogin => 'Har du redan ett konto? Logga in';

  @override
  String get emailLabel => 'E-post';

  @override
  String get passwordLabel => 'Lösenord';

  @override
  String get createAccountTitle => 'Skapa konto';

  @override
  String get nameLabel => 'Namn';

  @override
  String get repeatPasswordLabel => 'Upprepa lösenord';

  @override
  String get signUpButton => 'Registrera';

  @override
  String get enterNameError => 'Ange ditt namn';

  @override
  String get passwordsDoNotMatch => 'Lösenorden matchar inte';

  @override
  String get signUpSuccess => 'Registrering lyckades!';

  @override
  String get loadingKnowledgeGraph => 'Laddar kunskapsgraf...';

  @override
  String get noKnowledgeGraphYet => 'Ingen kunskapsgraf ännu';

  @override
  String get buildingKnowledgeGraphFromMemories => 'Bygger kunskapsgraf från minnen...';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'Din kunskapsgraf kommer att byggas automatiskt när du skapar nya minnen.';

  @override
  String get buildGraphButton => 'Bygg graf';

  @override
  String get checkOutMyMemoryGraph => 'Kolla in min minnesgraf!';

  @override
  String get getButton => 'Hämta';

  @override
  String openingApp(String appName) {
    return 'Öppnar $appName...';
  }

  @override
  String get writeSomething => 'Skriv något';

  @override
  String get submitReply => 'Skicka svar';

  @override
  String get editYourReply => 'Redigera ditt svar';

  @override
  String get replyToReview => 'Svara på recension';

  @override
  String get rateAndReviewThisApp => 'Betygsätt och recensera den här appen';

  @override
  String get noChangesInReview => 'Inga ändringar i recensionen att uppdatera.';

  @override
  String get cantRateWithoutInternet => 'Kan inte betygsätta appen utan internetanslutning.';

  @override
  String get appAnalytics => 'App-analys';

  @override
  String get learnMoreLink => 'läs mer';

  @override
  String get moneyEarned => 'Intjänade pengar';

  @override
  String get writeYourReply => 'Skriv ditt svar...';

  @override
  String get replySentSuccessfully => 'Svaret skickades';

  @override
  String failedToSendReply(String error) {
    return 'Kunde inte skicka svar: $error';
  }

  @override
  String get send => 'Skicka';

  @override
  String starFilter(int count) {
    return '$count stjärna';
  }

  @override
  String get noReviewsFound => 'Inga recensioner hittades';

  @override
  String get editReply => 'Redigera svar';

  @override
  String get reply => 'Svar';

  @override
  String starFilterLabel(int count) {
    return '$count stjärna';
  }

  @override
  String get sharePublicLink => 'Dela offentlig länk';

  @override
  String get makePersonaPublic => 'Gör persona offentlig';

  @override
  String get connectedKnowledgeData => 'Ansluten kunskapsdata';

  @override
  String get enterName => 'Ange namn';

  @override
  String get disconnectTwitter => 'Koppla från Twitter';

  @override
  String get disconnectTwitterConfirmation =>
      'Är du säker på att du vill koppla från ditt Twitter-konto? Din persona kommer inte längre att använda din Twitter-aktivitet.';

  @override
  String get getOmiDeviceDescription => 'Skapa en mer exakt klon med dina personliga konversationer';

  @override
  String get getOmi => 'Skaffa Omi';

  @override
  String get iHaveOmiDevice => 'Jag har en Omi-enhet';

  @override
  String get goal => 'MÅL';

  @override
  String get tapToTrackThisGoal => 'Tryck för att spåra detta mål';

  @override
  String get tapToSetAGoal => 'Tryck för att sätta ett mål';

  @override
  String get processedConversations => 'Bearbetade samtal';

  @override
  String get updatedConversations => 'Uppdaterade samtal';

  @override
  String get newConversations => 'Nya samtal';

  @override
  String get summaryTemplate => 'Sammanfattningsmall';

  @override
  String get suggestedTemplates => 'Föreslagna mallar';

  @override
  String get otherTemplates => 'Andra mallar';

  @override
  String get availableTemplates => 'Tillgängliga mallar';

  @override
  String get getCreative => 'Var kreativ';

  @override
  String get defaultLabel => 'Standard';

  @override
  String get lastUsedLabel => 'Senast använd';

  @override
  String get setDefaultApp => 'Ange standardapp';

  @override
  String setDefaultAppContent(String appName) {
    return 'Ange $appName som din standardapp för sammanfattningar?\\n\\nDenna app kommer automatiskt att användas för alla framtida konversationssammanfattningar.';
  }

  @override
  String get setDefaultButton => 'Ange standard';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName angiven som standardapp för sammanfattningar';
  }

  @override
  String get createCustomTemplate => 'Skapa anpassad mall';

  @override
  String get allTemplates => 'Alla mallar';

  @override
  String failedToInstallApp(String appName) {
    return 'Kunde inte installera $appName. Försök igen.';
  }

  @override
  String errorInstallingApp(String appName, String error) {
    return 'Fel vid installation av $appName: $error';
  }

  @override
  String tagSpeaker(int speakerId) {
    return 'Tagga talare $speakerId';
  }

  @override
  String get personNameAlreadyExists => 'En person med detta namn finns redan.';

  @override
  String get selectYouFromList => 'För att tagga dig själv, välj \"Du\" från listan.';

  @override
  String get enterPersonsName => 'Ange personens namn';

  @override
  String get addPerson => 'Lägg till person';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'Tagga andra segment från denna talare ($selected/$total)';
  }

  @override
  String get tagOtherSegments => 'Tagga andra segment';

  @override
  String get managePeople => 'Hantera personer';

  @override
  String get shareViaSms => 'Dela via SMS';

  @override
  String get selectContactsToShareSummary => 'Välj kontakter för att dela din samtalssammanfattning';

  @override
  String get searchContactsHint => 'Sök kontakter...';

  @override
  String contactsSelectedCount(int count) {
    return '$count valda';
  }

  @override
  String get clearAllSelection => 'Rensa allt';

  @override
  String get selectContactsToShare => 'Välj kontakter att dela med';

  @override
  String shareWithContactCount(int count) {
    return 'Dela med $count kontakt';
  }

  @override
  String shareWithContactsCount(int count) {
    return 'Dela med $count kontakter';
  }

  @override
  String get contactsPermissionRequired => 'Kontaktbehörighet krävs';

  @override
  String get contactsPermissionRequiredForSms => 'Kontaktbehörighet krävs för att dela via SMS';

  @override
  String get grantContactsPermissionForSms => 'Ge kontaktbehörighet för att dela via SMS';

  @override
  String get noContactsWithPhoneNumbers => 'Inga kontakter med telefonnummer hittades';

  @override
  String get noContactsMatchSearch => 'Inga kontakter matchar din sökning';

  @override
  String get failedToLoadContacts => 'Kunde inte ladda kontakter';

  @override
  String get failedToPrepareConversationForSharing => 'Kunde inte förbereda samtalet för delning. Försök igen.';

  @override
  String get couldNotOpenSmsApp => 'Kunde inte öppna SMS-appen. Försök igen.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'Här är vad vi just diskuterade: $link';
  }

  @override
  String get wifiSync => 'WiFi-synkronisering';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item kopierat till urklipp';
  }

  @override
  String get wifiConnectionFailedTitle => 'Anslutningen misslyckades';

  @override
  String connectingToDeviceName(String deviceName) {
    return 'Ansluter till $deviceName';
  }

  @override
  String enableDeviceWifi(String deviceName) {
    return 'Aktivera ${deviceName}s WiFi';
  }

  @override
  String connectToDeviceName(String deviceName) {
    return 'Anslut till $deviceName';
  }

  @override
  String get recordingDetails => 'Inspelningsdetaljer';

  @override
  String get storageLocationSdCard => 'SD-kort';

  @override
  String get storageLocationLimitlessPendant => 'Limitless Pendant';

  @override
  String get storageLocationPhone => 'Telefon';

  @override
  String get storageLocationPhoneMemory => 'Telefon (minne)';

  @override
  String storedOnDevice(String deviceName) {
    return 'Lagrat på $deviceName';
  }

  @override
  String get transferring => 'Överför...';

  @override
  String get transferRequired => 'Överföring krävs';

  @override
  String get downloadingAudioFromSdCard => 'Laddar ned ljud från enhetens SD-kort';

  @override
  String get transferRequiredDescription =>
      'Denna inspelning är lagrad på enhetens SD-kort. Överför den till din telefon för att lyssna.';

  @override
  String get cancelTransfer => 'Avbryt överföring';

  @override
  String get transferToPhone => 'Överför till telefon';

  @override
  String get privateAndSecureOnDevice => 'Privat och säker på din enhet';

  @override
  String get recordingInfo => 'Inspelningsinformation';

  @override
  String get transferInProgress => 'Överföring pågår...';

  @override
  String get shareRecording => 'Dela inspelning';

  @override
  String get deleteRecordingConfirmation =>
      'Är du säker på att du vill ta bort denna inspelning permanent? Detta kan inte ångras.';

  @override
  String get recordingIdLabel => 'Inspelnings-ID';

  @override
  String get dateTimeLabel => 'Datum och tid';

  @override
  String get durationLabel => 'Varaktighet';

  @override
  String get audioFormatLabel => 'Ljudformat';

  @override
  String get storageLocationLabel => 'Lagringsplats';

  @override
  String get estimatedSizeLabel => 'Uppskattad storlek';

  @override
  String get deviceModelLabel => 'Enhetsmodell';

  @override
  String get deviceIdLabel => 'Enhets-ID';

  @override
  String get statusLabel => 'Status';

  @override
  String get statusProcessed => 'Behandlad';

  @override
  String get statusUnprocessed => 'Obehandlad';

  @override
  String get switchedToFastTransfer => 'Bytte till snabb överföring';

  @override
  String get transferCompleteMessage => 'Överföring slutförd! Du kan nu spela upp denna inspelning.';

  @override
  String transferFailedMessage(String error) {
    return 'Överföring misslyckades: $error';
  }

  @override
  String get transferCancelled => 'Överföring avbruten';

  @override
  String get fastTransferEnabled => 'Snabb överföring aktiverad';

  @override
  String get bluetoothSyncEnabled => 'Bluetooth-synkronisering aktiverad';

  @override
  String get enableFastTransfer => 'Aktivera snabb överföring';

  @override
  String get fastTransferDescription =>
      'Snabb överföring använder WiFi för ~5x snabbare hastigheter. Din telefon ansluter tillfälligt till Omi-enhetens WiFi-nätverk under överföringen.';

  @override
  String get internetAccessPausedDuringTransfer => 'Internetåtkomst pausas under överföring';

  @override
  String get chooseTransferMethodDescription => 'Välj hur inspelningar överförs från Omi-enheten till din telefon.';

  @override
  String get wifiSpeed => '~150 KB/s via WiFi';

  @override
  String get fiveTimesFaster => '5X SNABBARE';

  @override
  String get fastTransferMethodDescription =>
      'Skapar en direkt WiFi-anslutning till din Omi-enhet. Din telefon kopplas tillfälligt från ditt vanliga WiFi under överföringen.';

  @override
  String get bluetooth => 'Bluetooth';

  @override
  String get bleSpeed => '~30 KB/s via BLE';

  @override
  String get bluetoothMethodDescription =>
      'Använder standard Bluetooth Low Energy-anslutning. Långsammare men påverkar inte din WiFi-anslutning.';

  @override
  String get selected => 'Vald';

  @override
  String get selectOption => 'Välj';

  @override
  String get lowBatteryAlertTitle => 'Varning för lågt batteri';

  @override
  String get lowBatteryAlertBody => 'Enhetens batteri är lågt. Dags att ladda! 🔋';

  @override
  String get deviceDisconnectedNotificationTitle => 'Din Omi-enhet har kopplats från';

  @override
  String get deviceDisconnectedNotificationBody => 'Anslut igen för att fortsätta använda Omi.';

  @override
  String get firmwareUpdateAvailable => 'Firmware-uppdatering tillgänglig';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'En ny firmware-uppdatering ($version) finns tillgänglig för din Omi-enhet. Vill du uppdatera nu?';
  }

  @override
  String get later => 'Senare';

  @override
  String get appDeletedSuccessfully => 'Appen har tagits bort';

  @override
  String get appDeleteFailed => 'Kunde inte ta bort appen. Försök igen senare.';

  @override
  String get appVisibilityChangedSuccessfully =>
      'Appens synlighet har ändrats. Det kan ta några minuter innan ändringen syns.';

  @override
  String get errorActivatingAppIntegration =>
      'Fel vid aktivering av appen. Om det är en integrationsapp, se till att konfigurationen är slutförd.';

  @override
  String get errorUpdatingAppStatus => 'Ett fel uppstod vid uppdatering av appstatus.';

  @override
  String get calculatingETA => 'Beräknar...';

  @override
  String aboutMinutesRemaining(int minutes) {
    return 'Ungefär $minutes minuter kvar';
  }

  @override
  String get aboutAMinuteRemaining => 'Ungefär en minut kvar';

  @override
  String get almostDone => 'Nästan klart...';

  @override
  String get omiSays => 'omi säger';

  @override
  String get analyzingYourData => 'Analyserar dina data...';

  @override
  String migratingToProtection(String level) {
    return 'Migrerar till $level-skydd...';
  }

  @override
  String get noDataToMigrateFinalizing => 'Ingen data att migrera. Slutför...';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return 'Migrerar $itemType... $percentage%';
  }

  @override
  String get allObjectsMigratedFinalizing => 'Alla objekt migrerade. Slutför...';

  @override
  String get migrationErrorOccurred => 'Ett fel uppstod under migreringen. Försök igen.';

  @override
  String get migrationComplete => 'Migrering slutförd!';

  @override
  String dataProtectedWithSettings(String level) {
    return 'Dina data är nu skyddade med de nya $level-inställningarna.';
  }

  @override
  String get chatsLowercase => 'chattar';

  @override
  String get dataLowercase => 'data';

  @override
  String get fallNotificationTitle => 'Aj';

  @override
  String get fallNotificationBody => 'Föll du?';

  @override
  String get importantConversationTitle => 'Viktigt samtal';

  @override
  String get importantConversationBody => 'Du hade precis ett viktigt samtal. Tryck för att dela sammanfattningen.';

  @override
  String get templateName => 'Mallnamn';

  @override
  String get templateNameHint => 't.ex. Mötesåtgärdspunkter Extraktor';

  @override
  String get nameMustBeAtLeast3Characters => 'Namnet måste vara minst 3 tecken';

  @override
  String get conversationPromptHint =>
      't.ex., Extrahera åtgärdspunkter, fattade beslut och viktiga slutsatser från samtalet.';

  @override
  String get pleaseEnterAppPrompt => 'Ange en prompt för din app';

  @override
  String get promptMustBeAtLeast10Characters => 'Prompten måste vara minst 10 tecken';

  @override
  String get anyoneCanDiscoverTemplate => 'Vem som helst kan upptäcka din mall';

  @override
  String get onlyYouCanUseTemplate => 'Endast du kan använda denna mall';

  @override
  String get generatingDescription => 'Genererar beskrivning...';

  @override
  String get creatingAppIcon => 'Skapar appikon...';

  @override
  String get installingApp => 'Installerar app...';

  @override
  String get appCreatedAndInstalled => 'App skapad och installerad!';

  @override
  String get appCreatedSuccessfully => 'App skapad!';

  @override
  String get failedToCreateApp => 'Kunde inte skapa app. Försök igen.';

  @override
  String get addAppSelectCoreCapability => 'Välj ytterligare en kärnfunktion för din app';

  @override
  String get addAppSelectPaymentPlan => 'Välj en betalningsplan och ange ett pris för din app';

  @override
  String get addAppSelectCapability => 'Välj minst en funktion för din app';

  @override
  String get addAppSelectLogo => 'Välj en logotyp för din app';

  @override
  String get addAppEnterChatPrompt => 'Ange en chattuppmaning för din app';

  @override
  String get addAppEnterConversationPrompt => 'Ange en konversationsuppmaning för din app';

  @override
  String get addAppSelectTriggerEvent => 'Välj en utlösarhändelse för din app';

  @override
  String get addAppEnterWebhookUrl => 'Ange en webhook-URL för din app';

  @override
  String get addAppSelectCategory => 'Välj en kategori för din app';

  @override
  String get addAppFillRequiredFields => 'Fyll i alla obligatoriska fält korrekt';

  @override
  String get addAppUpdatedSuccess => 'Appen har uppdaterats 🚀';

  @override
  String get addAppUpdateFailed => 'Uppdatering misslyckades. Försök igen senare';

  @override
  String get addAppSubmittedSuccess => 'Appen har skickats 🚀';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'Fel vid öppning av filväljare: $message';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'Fel vid val av bild: $error';
  }

  @override
  String get addAppPhotosPermissionDenied => 'Fotoåtkomst nekad. Tillåt åtkomst till foton';

  @override
  String get addAppErrorSelectingImageRetry => 'Fel vid val av bild. Försök igen.';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'Fel vid val av miniatyrbild: $error';
  }

  @override
  String get addAppErrorSelectingThumbnailRetry => 'Fel vid val av miniatyrbild. Försök igen.';

  @override
  String get addAppCapabilityConflictWithPersona => 'Andra funktioner kan inte väljas med Persona';

  @override
  String get addAppPersonaConflictWithCapabilities => 'Persona kan inte väljas med andra funktioner';

  @override
  String get personaTwitterHandleNotFound => 'Twitter-konto hittades inte';

  @override
  String get personaTwitterHandleSuspended => 'Twitter-konto är avstängt';

  @override
  String get personaFailedToVerifyTwitter => 'Kunde inte verifiera Twitter-konto';

  @override
  String get personaFailedToFetch => 'Kunde inte hämta din persona';

  @override
  String get personaFailedToCreate => 'Kunde inte skapa persona';

  @override
  String get personaConnectKnowledgeSource => 'Anslut minst en datakälla (Omi eller Twitter)';

  @override
  String get personaUpdatedSuccessfully => 'Persona uppdaterad';

  @override
  String get personaFailedToUpdate => 'Kunde inte uppdatera persona';

  @override
  String get personaPleaseSelectImage => 'Välj en bild';

  @override
  String get personaFailedToCreateTryLater => 'Kunde inte skapa persona. Försök igen senare.';

  @override
  String personaFailedToCreateWithError(String error) {
    return 'Kunde inte skapa persona: $error';
  }

  @override
  String get personaFailedToEnable => 'Kunde inte aktivera persona';

  @override
  String personaErrorEnablingWithError(String error) {
    return 'Fel vid aktivering av persona: $error';
  }

  @override
  String get paymentFailedToFetchCountries => 'Kunde inte hämta länder. Försök igen senare.';

  @override
  String get paymentFailedToSetDefault => 'Kunde inte ange standardbetalningsmetod. Försök igen senare.';

  @override
  String get paymentFailedToSavePaypal => 'Kunde inte spara PayPal-uppgifter. Försök igen senare.';

  @override
  String get paypalEmailHint => 'nik@example.com';

  @override
  String get paypalMeLinkHint => 'paypal.me/nik';

  @override
  String get paymentMethodStripe => 'Stripe';

  @override
  String get paymentMethodPayPal => 'PayPal';

  @override
  String get paymentStatusActive => 'Aktiv';

  @override
  String get paymentStatusConnected => 'Ansluten';

  @override
  String get paymentStatusNotConnected => 'Ej ansluten';

  @override
  String get paymentAppCost => 'Appkostnad';

  @override
  String get paymentEnterValidAmount => 'Ange ett giltigt belopp';

  @override
  String get paymentEnterAmountGreaterThanZero => 'Ange ett belopp större än 0';

  @override
  String get paymentPlan => 'Betalningsplan';

  @override
  String get paymentNoneSelected => 'Inget valt';

  @override
  String get aiGenPleaseEnterDescription => 'Ange en beskrivning för din app';

  @override
  String get aiGenCreatingAppIcon => 'Skapar appikon...';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'Ett fel uppstod: $message';
  }

  @override
  String get aiGenAppCreatedSuccessfully => 'Appen har skapats!';

  @override
  String get aiGenFailedToCreateApp => 'Kunde inte skapa appen';

  @override
  String get aiGenErrorWhileCreatingApp => 'Ett fel uppstod när appen skapades';

  @override
  String get aiGenFailedToGenerateApp => 'Kunde inte generera appen. Försök igen.';

  @override
  String get aiGenFailedToRegenerateIcon => 'Kunde inte återskapa ikonen';

  @override
  String get aiGenPleaseGenerateAppFirst => 'Generera en app först';

  @override
  String get xHandleTitle => 'Vad är ditt X-användarnamn?';

  @override
  String get xHandleDescription => 'Vi kommer att förträna din Omi-klon\nbaserat på ditt kontos aktivitet';

  @override
  String get xHandleHint => '@nikshevchenko';

  @override
  String get xHandlePleaseEnter => 'Ange ditt X-användarnamn';

  @override
  String get xHandlePleaseEnterValid => 'Ange ett giltigt X-användarnamn';

  @override
  String get nextButton => 'Nästa';

  @override
  String get connectOmiDevice => 'Anslut Omi-enhet';

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'Du byter din Unlimited-plan till $title. Är du säker på att du vill fortsätta?';
  }

  @override
  String get planUpgradeScheduledMessage =>
      'Uppgradering schemalagd! Din månadsplan fortsätter till slutet av din faktureringsperiod.';

  @override
  String get couldNotSchedulePlanChange => 'Kunde inte schemalägga planbyte. Försök igen.';

  @override
  String get subscriptionReactivatedDefault =>
      'Din prenumeration har återaktiverats! Ingen debitering nu - du faktureras i slutet av din faktureringsperiod.';

  @override
  String get subscriptionSuccessfulCharged =>
      'Prenumerationen lyckades! Du har debiterats för den nya faktureringsperioden.';

  @override
  String get couldNotProcessSubscription => 'Kunde inte behandla prenumerationen. Försök igen.';

  @override
  String get couldNotLaunchUpgradePage => 'Kunde inte öppna uppgraderingssidan. Försök igen.';

  @override
  String get transcriptionJsonPlaceholder => 'Klistra in din JSON-konfiguration här...';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get pricePlaceholder => '0,00';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'Fel vid öppning av filväljare: $message';
  }

  @override
  String importErrorGeneric(String error) {
    return 'Fel: $error';
  }

  @override
  String get mergeConversationsSuccessTitle => 'Konversationer sammanfogade';

  @override
  String mergeConversationsSuccessBody(int count) {
    return '$count konversationer har sammanfogats';
  }

  @override
  String get dailyReflectionNotificationTitle => 'Dags för daglig reflektion';

  @override
  String get dailyReflectionNotificationBody => 'Berätta om din dag';

  @override
  String get actionItemReminderTitle => 'Omi-påminnelse';

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName frånkopplad';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'Anslut igen för att fortsätta använda din $deviceName.';
  }

  @override
  String get onboardingSignIn => 'Logga in';

  @override
  String get onboardingYourName => 'Ditt namn';

  @override
  String get onboardingLanguage => 'Språk';

  @override
  String get onboardingPermissions => 'Behörigheter';

  @override
  String get onboardingComplete => 'Klart';

  @override
  String get onboardingWelcomeToOmi => 'Välkommen till Omi';

  @override
  String get onboardingTellUsAboutYourself => 'Berätta om dig själv';

  @override
  String get onboardingChooseYourPreference => 'Välj dina inställningar';

  @override
  String get onboardingGrantRequiredAccess => 'Bevilja nödvändig åtkomst';

  @override
  String get onboardingYoureAllSet => 'Du är redo';

  @override
  String get searchTranscriptOrSummary => 'Sök i transkription eller sammanfattning...';

  @override
  String get myGoal => 'Mitt mål';

  @override
  String get appNotAvailable => 'Hoppsan! Det verkar som att appen du letar efter inte är tillgänglig.';

  @override
  String get failedToConnectTodoist => 'Det gick inte att ansluta till Todoist';

  @override
  String get failedToConnectAsana => 'Det gick inte att ansluta till Asana';

  @override
  String get failedToConnectGoogleTasks => 'Det gick inte att ansluta till Google Tasks';

  @override
  String get failedToConnectClickUp => 'Det gick inte att ansluta till ClickUp';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return 'Det gick inte att ansluta till $serviceName: $error';
  }

  @override
  String get successfullyConnectedTodoist => 'Ansluten till Todoist!';

  @override
  String get failedToConnectTodoistRetry => 'Det gick inte att ansluta till Todoist. Försök igen.';

  @override
  String get successfullyConnectedAsana => 'Ansluten till Asana!';

  @override
  String get failedToConnectAsanaRetry => 'Det gick inte att ansluta till Asana. Försök igen.';

  @override
  String get successfullyConnectedGoogleTasks => 'Ansluten till Google Tasks!';

  @override
  String get failedToConnectGoogleTasksRetry => 'Det gick inte att ansluta till Google Tasks. Försök igen.';

  @override
  String get successfullyConnectedClickUp => 'Ansluten till ClickUp!';

  @override
  String get failedToConnectClickUpRetry => 'Det gick inte att ansluta till ClickUp. Försök igen.';

  @override
  String get successfullyConnectedNotion => 'Ansluten till Notion!';

  @override
  String get failedToRefreshNotionStatus => 'Det gick inte att uppdatera Notion-anslutningsstatus.';

  @override
  String get successfullyConnectedGoogle => 'Ansluten till Google!';

  @override
  String get failedToRefreshGoogleStatus => 'Det gick inte att uppdatera Google-anslutningsstatus.';

  @override
  String get successfullyConnectedWhoop => 'Ansluten till Whoop!';

  @override
  String get failedToRefreshWhoopStatus => 'Det gick inte att uppdatera Whoop-anslutningsstatus.';

  @override
  String get successfullyConnectedGitHub => 'Ansluten till GitHub!';

  @override
  String get failedToRefreshGitHubStatus => 'Det gick inte att uppdatera GitHub-anslutningsstatus.';

  @override
  String get authFailedToSignInWithGoogle => 'Kunde inte logga in med Google, försök igen.';

  @override
  String get authenticationFailed => 'Autentisering misslyckades. Försök igen.';

  @override
  String get authFailedToSignInWithApple => 'Kunde inte logga in med Apple, försök igen.';

  @override
  String get authFailedToRetrieveToken => 'Kunde inte hämta Firebase-token, försök igen.';

  @override
  String get authUnexpectedErrorFirebase => 'Oväntat fel vid inloggning, Firebase-fel, försök igen.';

  @override
  String get authUnexpectedError => 'Oväntat fel vid inloggning, försök igen';

  @override
  String get authFailedToLinkGoogle => 'Kunde inte koppla till Google, försök igen.';

  @override
  String get authFailedToLinkApple => 'Kunde inte koppla till Apple, försök igen.';

  @override
  String get onboardingBluetoothRequired => 'Bluetooth-behörighet krävs för att ansluta till din enhet.';

  @override
  String get onboardingBluetoothDeniedSystemPrefs =>
      'Bluetooth-behörighet nekad. Bevilja behörighet i Systeminställningar.';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'Bluetooth-behörighetsstatus: $status. Kontrollera Systeminställningar.';
  }

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'Kunde inte kontrollera Bluetooth-behörighet: $error';
  }

  @override
  String get onboardingNotificationDeniedSystemPrefs =>
      'Aviseringsbehörighet nekad. Bevilja behörighet i Systeminställningar.';

  @override
  String get onboardingNotificationDeniedNotifications =>
      'Aviseringsbehörighet nekad. Bevilja behörighet i Systeminställningar > Aviseringar.';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return 'Aviseringsbehörighetsstatus: $status. Kontrollera Systeminställningar.';
  }

  @override
  String onboardingFailedCheckNotification(String error) {
    return 'Kunde inte kontrollera aviseringsbehörighet: $error';
  }

  @override
  String get onboardingLocationGrantInSettings =>
      'Bevilja platsbehörighet i Inställningar > Integritet och säkerhet > Platstjänster';

  @override
  String get onboardingMicrophoneRequired => 'Mikrofonbehörighet krävs för inspelning.';

  @override
  String get onboardingMicrophoneDenied =>
      'Mikrofonbehörighet nekad. Bevilja behörighet i Systeminställningar > Integritet och säkerhet > Mikrofon.';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'Mikrofonbehörighetsstatus: $status. Kontrollera Systeminställningar.';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'Kunde inte kontrollera mikrofonbehörighet: $error';
  }

  @override
  String get onboardingScreenCaptureRequired => 'Skärminspelningsbehörighet krävs för systemljudinspelning.';

  @override
  String get onboardingScreenCaptureDenied =>
      'Skärminspelningsbehörighet nekad. Bevilja behörighet i Systeminställningar > Integritet och säkerhet > Skärminspelning.';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return 'Skärminspelningsbehörighetsstatus: $status. Kontrollera Systeminställningar.';
  }

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return 'Kunde inte kontrollera skärminspelningsbehörighet: $error';
  }

  @override
  String get onboardingAccessibilityRequired => 'Tillgänglighetsbehörighet krävs för att upptäcka webbläsarmöten.';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'Tillgänglighetsbehörighetsstatus: $status. Kontrollera Systeminställningar.';
  }

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'Kunde inte kontrollera tillgänglighetsbehörighet: $error';
  }

  @override
  String get msgCameraNotAvailable => 'Kamerainspelning är inte tillgänglig på denna plattform';

  @override
  String get msgCameraPermissionDenied => 'Kameratillstånd nekad. Vänligen tillåt åtkomst till kameran';

  @override
  String msgCameraAccessError(String error) {
    return 'Fel vid åtkomst till kamera: $error';
  }

  @override
  String get msgPhotoError => 'Fel vid fotografering. Försök igen.';

  @override
  String get msgMaxImagesLimit => 'Du kan bara välja upp till 4 bilder';

  @override
  String msgFilePickerError(String error) {
    return 'Fel vid öppning av filväljare: $error';
  }

  @override
  String msgSelectImagesError(String error) {
    return 'Fel vid val av bilder: $error';
  }

  @override
  String get msgPhotosPermissionDenied =>
      'Fototillstånd nekad. Vänligen tillåt åtkomst till foton för att välja bilder';

  @override
  String get msgSelectImagesGenericError => 'Fel vid val av bilder. Försök igen.';

  @override
  String get msgMaxFilesLimit => 'Du kan bara välja upp till 4 filer';

  @override
  String msgSelectFilesError(String error) {
    return 'Fel vid val av filer: $error';
  }

  @override
  String get msgSelectFilesGenericError => 'Fel vid val av filer. Försök igen.';

  @override
  String get msgUploadFileFailed => 'Kunde inte ladda upp fil, försök igen senare';

  @override
  String get msgReadingMemories => 'Läser dina minnen...';

  @override
  String get msgLearningMemories => 'Lär sig från dina minnen...';

  @override
  String get msgUploadAttachedFileFailed => 'Kunde inte ladda upp bifogad fil.';

  @override
  String captureRecordingError(String error) {
    return 'Ett fel uppstod under inspelningen: $error';
  }

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return 'Inspelningen stoppades: $reason. Du kan behöva återansluta externa skärmar eller starta om inspelningen.';
  }

  @override
  String get captureMicrophonePermissionRequired => 'Mikrofonbehörighet krävs';

  @override
  String get captureMicrophonePermissionInSystemPreferences => 'Ge mikrofonbehörighet i Systeminställningar';

  @override
  String get captureScreenRecordingPermissionRequired => 'Skärminspelningsbehörighet krävs';

  @override
  String get captureDisplayDetectionFailed => 'Skärmigenkänning misslyckades. Inspelningen stoppades.';

  @override
  String get devModeInvalidAudioBytesWebhookUrl => 'Ogiltig webhook-URL för ljudbytes';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl => 'Ogiltig webhook-URL för realtidstranskription';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl => 'Ogiltig webhook-URL för skapad konversation';

  @override
  String get devModeInvalidDaySummaryWebhookUrl => 'Ogiltig webhook-URL för daglig sammanfattning';

  @override
  String get devModeSettingsSaved => 'Inställningar sparade!';

  @override
  String get voiceFailedToTranscribe => 'Kunde inte transkribera ljud';

  @override
  String get locationPermissionRequired => 'Platstillstånd krävs';

  @override
  String get locationPermissionContent =>
      'Snabb överföring kräver platstillstånd för att verifiera WiFi-anslutningen. Vänligen ge platstillstånd för att fortsätta.';

  @override
  String get pdfTranscriptExport => 'Transkriptionsexport';

  @override
  String get pdfConversationExport => 'Samtalsexport';

  @override
  String pdfTitleLabel(String title) {
    return 'Titel: $title';
  }

  @override
  String get conversationNewIndicator => 'Ny 🚀';

  @override
  String conversationPhotosCount(int count) {
    return '$count foton';
  }

  @override
  String get mergingStatus => 'Sammanfogar...';

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
    return '$count timme';
  }

  @override
  String timeHoursPlural(int count) {
    return '$count timmar';
  }

  @override
  String timeHoursAndMins(int hours, int mins) {
    return '$hours timmar $mins min';
  }

  @override
  String timeDaySingular(int count) {
    return '$count dag';
  }

  @override
  String timeDaysPlural(int count) {
    return '$count dagar';
  }

  @override
  String timeDaysAndHours(int days, int hours) {
    return '$days dagar $hours timmar';
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
  String get moveToFolder => 'Flytta till mapp';

  @override
  String get noFoldersAvailable => 'Inga mappar tillgängliga';

  @override
  String get newFolder => 'Ny mapp';

  @override
  String get color => 'Färg';

  @override
  String get waitingForDevice => 'Väntar på enhet...';

  @override
  String get saySomething => 'Säg något...';

  @override
  String get initialisingSystemAudio => 'Initierar systemljud';

  @override
  String get stopRecording => 'Stoppa inspelning';

  @override
  String get continueRecording => 'Fortsätt inspelning';

  @override
  String get initialisingRecorder => 'Initierar inspelaren';

  @override
  String get pauseRecording => 'Pausa inspelning';

  @override
  String get resumeRecording => 'Återuppta inspelning';

  @override
  String get noDailyRecapsYet => 'Inga dagliga sammanfattningar ännu';

  @override
  String get dailyRecapsDescription => 'Dina dagliga sammanfattningar visas här när de har skapats';

  @override
  String get chooseTransferMethod => 'Välj överföringsmetod';

  @override
  String get fastTransferSpeed => '~150 KB/s via WiFi';

  @override
  String largeTimeGapDetected(String gap) {
    return 'Stort tidsgap upptäckt ($gap)';
  }

  @override
  String largeTimeGapsDetected(String gaps) {
    return 'Stora tidsgap upptäckta ($gaps)';
  }

  @override
  String get deviceDoesNotSupportWifiSwitchingToBle => 'Enheten stöder inte WiFi-synkronisering, byter till Bluetooth';

  @override
  String get appleHealthNotAvailable => 'Apple Health är inte tillgängligt på denna enhet';

  @override
  String get downloadAudio => 'Ladda ner ljud';

  @override
  String get audioDownloadSuccess => 'Ljud nedladdat framgångsrikt';

  @override
  String get audioDownloadFailed => 'Misslyckades att ladda ner ljud';

  @override
  String get downloadingAudio => 'Laddar ner ljud...';

  @override
  String get shareAudio => 'Dela ljud';

  @override
  String get preparingAudio => 'Förbereder ljud';

  @override
  String get gettingAudioFiles => 'Hämtar ljudfiler...';

  @override
  String get downloadingAudioProgress => 'Laddar ner ljud';

  @override
  String get processingAudio => 'Bearbetar ljud';

  @override
  String get combiningAudioFiles => 'Kombinerar ljudfiler...';

  @override
  String get audioReady => 'Ljud klart';

  @override
  String get openingShareSheet => 'Öppnar delningsblad...';

  @override
  String get audioShareFailed => 'Delning misslyckades';

  @override
  String get dailyRecaps => 'Dagliga Sammanfattningar';

  @override
  String get removeFilter => 'Ta Bort Filter';

  @override
  String get categoryConversationAnalysis => 'Samtalsanalys';

  @override
  String get categoryPersonalityClone => 'Personlighetsklon';

  @override
  String get categoryHealth => 'Hälsa';

  @override
  String get categoryEducation => 'Utbildning';

  @override
  String get categoryCommunication => 'Kommunikation';

  @override
  String get categoryEmotionalSupport => 'Emotionellt stöd';

  @override
  String get categoryProductivity => 'Produktivitet';

  @override
  String get categoryEntertainment => 'Underhållning';

  @override
  String get categoryFinancial => 'Ekonomi';

  @override
  String get categoryTravel => 'Resor';

  @override
  String get categorySafety => 'Säkerhet';

  @override
  String get categoryShopping => 'Shopping';

  @override
  String get categorySocial => 'Socialt';

  @override
  String get categoryNews => 'Nyheter';

  @override
  String get categoryUtilities => 'Verktyg';

  @override
  String get categoryOther => 'Övrigt';

  @override
  String get capabilityChat => 'Chatt';

  @override
  String get capabilityConversations => 'Samtal';

  @override
  String get capabilityExternalIntegration => 'Extern integration';

  @override
  String get capabilityNotification => 'Avisering';

  @override
  String get triggerAudioBytes => 'Ljudbytes';

  @override
  String get triggerConversationCreation => 'Skapande av samtal';

  @override
  String get triggerTranscriptProcessed => 'Transkription bearbetad';

  @override
  String get actionCreateConversations => 'Skapa samtal';

  @override
  String get actionCreateMemories => 'Skapa minnen';

  @override
  String get actionReadConversations => 'Läs samtal';

  @override
  String get actionReadMemories => 'Läs minnen';

  @override
  String get actionReadTasks => 'Läs uppgifter';

  @override
  String get scopeUserName => 'Användarnamn';

  @override
  String get scopeUserFacts => 'Användarfakta';

  @override
  String get scopeUserConversations => 'Användarsamtal';

  @override
  String get scopeUserChat => 'Användarchatt';

  @override
  String get capabilitySummary => 'Sammanfattning';

  @override
  String get capabilityFeatured => 'Utvalda';

  @override
  String get capabilityTasks => 'Uppgifter';

  @override
  String get capabilityIntegrations => 'Integrationer';

  @override
  String get categoryPersonalityClones => 'Personlighetskloner';

  @override
  String get categoryProductivityLifestyle => 'Produktivitet & livsstil';

  @override
  String get categorySocialEntertainment => 'Socialt & underhållning';

  @override
  String get categoryProductivityTools => 'Produktivitetsverktyg';

  @override
  String get categoryPersonalWellness => 'Personligt välbefinnande';

  @override
  String get rating => 'Betyg';

  @override
  String get categories => 'Kategorier';

  @override
  String get sortBy => 'Sortera';

  @override
  String get highestRating => 'Högsta betyg';

  @override
  String get lowestRating => 'Lägsta betyg';

  @override
  String get resetFilters => 'Återställ filter';

  @override
  String get applyFilters => 'Tillämpa filter';

  @override
  String get mostInstalls => 'Flest installationer';

  @override
  String get couldNotOpenUrl => 'Det gick inte att öppna URL:en. Försök igen.';

  @override
  String get newTask => 'Ny uppgift';

  @override
  String get viewAll => 'Visa alla';

  @override
  String get addTask => 'Lägg till uppgift';

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
  String get audioPlaybackUnavailable => 'Ljudfilen är inte tillgänglig för uppspelning';

  @override
  String get audioPlaybackFailed => 'Kan inte spela upp ljud. Filen kan vara skadad eller saknas.';

  @override
  String get connectionGuide => 'Anslutningsguide';

  @override
  String get iveDoneThis => 'Jag har gjort detta';

  @override
  String get pairNewDevice => 'Parkoppla ny enhet';

  @override
  String get dontSeeYourDevice => 'Ser du inte din enhet?';

  @override
  String get reportAnIssue => 'Rapportera ett problem';

  @override
  String get pairingTitleOmi => 'Slå på Omi';

  @override
  String get pairingDescOmi => 'Tryck och håll enheten tills den vibrerar för att slå på den.';

  @override
  String get pairingTitleOmiDevkit => 'Sätt Omi DevKit i parkopplingsläge';

  @override
  String get pairingDescOmiDevkit => 'Tryck på knappen en gång för att slå på. LED:en blinkar lila i parkopplingsläge.';

  @override
  String get pairingTitleOmiGlass => 'Slå på Omi Glass';

  @override
  String get pairingDescOmiGlass => 'Tryck och håll sidoknappen i 3 sekunder för att slå på.';

  @override
  String get pairingTitlePlaudNote => 'Sätt Plaud Note i parkopplingsläge';

  @override
  String get pairingDescPlaudNote =>
      'Tryck och håll sidoknappen i 2 sekunder. Den röda LED:en blinkar när den är redo att parkoppla.';

  @override
  String get pairingTitleBee => 'Sätt Bee i parkopplingsläge';

  @override
  String get pairingDescBee => 'Tryck på knappen 5 gånger i rad. Ljuset börjar blinka blått och grönt.';

  @override
  String get pairingTitleLimitless => 'Sätt Limitless i parkopplingsläge';

  @override
  String get pairingDescLimitless =>
      'När en lampa lyser, tryck en gång och tryck sedan och håll tills enheten visar ett rosa ljus, släpp sedan.';

  @override
  String get pairingTitleFriendPendant => 'Sätt Friend Pendant i parkopplingsläge';

  @override
  String get pairingDescFriendPendant =>
      'Tryck på knappen på hänget för att slå på det. Det går automatiskt till parkopplingsläge.';

  @override
  String get pairingTitleFieldy => 'Sätt Fieldy i parkopplingsläge';

  @override
  String get pairingDescFieldy => 'Tryck och håll enheten tills ljuset visas för att slå på den.';

  @override
  String get pairingTitleAppleWatch => 'Anslut Apple Watch';

  @override
  String get pairingDescAppleWatch =>
      'Installera och öppna Omi-appen på din Apple Watch, tryck sedan på Anslut i appen.';

  @override
  String get pairingTitleNeoOne => 'Sätt Neo One i parkopplingsläge';

  @override
  String get pairingDescNeoOne => 'Tryck och håll strömknappen tills LED:en blinkar. Enheten kommer att vara synlig.';
}
