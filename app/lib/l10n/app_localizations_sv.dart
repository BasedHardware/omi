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
  String get searchApps => 'Sök appar...';

  @override
  String get myApps => 'Mina Appar';

  @override
  String get installedApps => 'Installerade Appar';

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
  String get descriptionOptional => 'Beskrivning (valfritt)';

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
  String get conversationUrlCouldNotBeShared => 'Konversations-URL kunde inte delas.';

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
  String get unknownDevice => 'Okänd enhet';

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
  String get debugAndDiagnostics => 'Felsökning och diagnostik';

  @override
  String get autoDeletesAfter3Days => 'Raderas automatiskt efter 3 dagar';

  @override
  String get helpsDiagnoseIssues => 'Hjälper till att diagnostisera problem';

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
  String get autoCreateWhenNameDetected => 'Auto-create when name detected';

  @override
  String get followUpQuestions => 'Uppföljningsfrågor';

  @override
  String get suggestQuestionsAfterConversations => 'Föreslå frågor efter konversationer';

  @override
  String get goalTracker => 'Målspårare';

  @override
  String get trackPersonalGoalsOnHomepage => 'Track your personal goals on homepage';

  @override
  String get dailyReflection => 'Daglig reflektion';

  @override
  String get get9PmReminderToReflect => 'Get a 9 PM reminder to reflect on your day';

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
  String get dailyScoreDescription => 'Ett poäng som hjälper dig att fokusera bättre på genomförande.';

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
  String get timePM => 'PM';

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
  String installsCount(String count) {
    return '$count+ installationer';
  }

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
  String get takePhoto => 'Ta ett foto';

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
  String get discardedConversation => 'Kasserad konversation';

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
  String get starred => 'Stjärnmärkta';

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
      'Ingen sammanfattning tillgänglig för den här appen. Prova en annan app för bättre resultat.';

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
  String get dailySummary => 'Daglig Sammanfattning';

  @override
  String get developer => 'Utvecklare';

  @override
  String get about => 'Om';

  @override
  String get selectTime => 'Välj Tid';

  @override
  String get accountGroup => 'Konto';

  @override
  String get signOutQuestion => 'Logga Ut?';

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
  String get dailySummaryDescription => 'Få en personlig sammanfattning av dina konversationer';

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
  String get upcomingMeetings => 'KOMMANDE MÖTEN';

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
  String get dailyReflectionDescription => '21:00 påminnelse att reflektera över din dag';

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
  String get failedToSubmitReview => 'Det gick inte att skicka recensionen. Försök igen.';

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
      'This app will access your data. Omi AI is not responsible for how your data is used, modified, or deleted by this app';

  @override
  String get copyUrl => 'Kopiera URL';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';
}
