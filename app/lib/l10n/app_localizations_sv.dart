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
  String get ok => 'Ok';

  @override
  String get delete => 'Ta bort';

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
  String get deleteConversation => 'Ta bort konversation';

  @override
  String get contentCopied => 'Innehåll kopierat till urklipp';

  @override
  String get failedToUpdateStarred => 'Det gick inte att uppdatera stjärnstatus.';

  @override
  String get conversationUrlNotShared => 'Konversationens URL kunde inte delas.';

  @override
  String get errorProcessingConversation => 'Fel vid bearbetning av konversation. Försök igen senare.';

  @override
  String get noInternetConnection => 'Kontrollera din internetanslutning och försök igen.';

  @override
  String get unableToDeleteConversation => 'Kan inte ta bort konversation';

  @override
  String get somethingWentWrong => 'Något gick fel! Försök igen senare.';

  @override
  String get copyErrorMessage => 'Kopiera felmeddelande';

  @override
  String get errorCopied => 'Felmeddelande kopierat till urklipp';

  @override
  String get remaining => 'Återstående';

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
  String get speechProfile => 'Röstprofil';

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
  String get searching => 'Söker';

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
  String get noConversationsYet => 'Inga konversationer ännu.';

  @override
  String get noStarredConversations => 'Inga stjärnmärkta konversationer ännu.';

  @override
  String get starConversationHint =>
      'För att stjärnmärka en konversation, öppna den och tryck på stjärnikonen i sidhuvudet.';

  @override
  String get searchConversations => 'Sök konversationer';

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
  String get deletingMessages => 'Tar bort dina meddelanden från Omis minne...';

  @override
  String get messageCopied => 'Meddelande kopierat till urklipp.';

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
  String get clearChat => 'Rensa chatt?';

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
  String get searchApps => 'Sök bland 1500+ appar';

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
  String get membersAndCounting => '8000+ medlemmar och fler tillkommer.';

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
  String get customVocabulary => 'Anpassat ordförråd';

  @override
  String get identifyingOthers => 'Identifiera andra';

  @override
  String get paymentMethods => 'Betalningsmetoder';

  @override
  String get conversationDisplay => 'Konversationsvisning';

  @override
  String get dataPrivacy => 'Data och integritet';

  @override
  String get userId => 'Användar-ID';

  @override
  String get notSet => 'Inte inställt';

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
  String get chatTools => 'Chattverktyg';

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
  String get signOut => 'Logga ut';

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
  String get sdCardSync => 'SD-kortssynkronisering';

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
      'Enhet bortkopplad. Gå till Inställningar > Bluetooth och glöm enheten för att slutföra.';

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
  String get endpointUrl => 'Endpoint-URL';

  @override
  String get noApiKeys => 'Inga API-nycklar ännu';

  @override
  String get createKeyToStart => 'Skapa en nyckel för att komma igång';

  @override
  String get createKey => 'Skapa nyckel';

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
  String get knowledgeGraphDeleted => 'Kunskapsgraf borttagen';

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
  String get header => 'Header';

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
  String get daySummary => 'Dagsammanfattning';

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
  String get connect => 'Anslut';

  @override
  String get comingSoon => 'Kommer snart';

  @override
  String get chatToolsFooter => 'Anslut dina appar för att visa data och mått i chatten.';

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
  String get noUpcomingMeetings => 'Inga kommande möten hittades';

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
  String get yesterday => 'igår';

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
  String get gotIt => 'Förstår';

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
  String deviceUsesCodec(String deviceName, String codecReason) {
    return '$deviceName använder $codecReason. Omi kommer att användas.';
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
  String get appName => 'Appnamn';

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
  String get createApp => 'Skapa app';

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
  String get notifications => 'Notifieringar';

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
  String get personalGrowthJourney => 'Din personliga utvecklingsresa med AI som lyssnar på varje ord.';

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
  String get deleteActionItemTitle => 'Ta bort åtgärd';

  @override
  String get deleteActionItemMessage => 'Är du säker på att du vill ta bort denna åtgärd?';

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
  String searchMemories(int count) {
    return 'Sök $count minnen';
  }

  @override
  String get memoryDeleted => 'Minne borttaget.';

  @override
  String get undo => 'Ångra';

  @override
  String get noMemoriesYet => 'Inga minnen ännu';

  @override
  String get noAutoMemories => 'Inga automatiskt extraherade minnen ännu';

  @override
  String get noManualMemories => 'Inga manuella minnen ännu';

  @override
  String get noMemoriesInCategories => 'Inga minnen i dessa kategorier';

  @override
  String get noMemoriesFound => 'Inga minnen hittades';

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
  String get newMemory => 'Nytt minne';

  @override
  String get editMemory => 'Redigera minne';

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
  String get failedToUpdateActionItem => 'Det gick inte att uppdatera åtgärd';

  @override
  String get actionItemCreated => 'Åtgärd skapad';

  @override
  String get failedToCreateActionItem => 'Det gick inte att skapa åtgärd';

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
  String get completed => 'Slutförd';

  @override
  String get markComplete => 'Markera som slutförd';

  @override
  String get actionItemDeleted => 'Åtgärd borttagen';

  @override
  String get failedToDeleteActionItem => 'Det gick inte att ta bort åtgärd';

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
}
