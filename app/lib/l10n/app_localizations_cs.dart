// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Czech (`cs`).
class AppLocalizationsCs extends AppLocalizations {
  AppLocalizationsCs([String locale = 'cs']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'Konverzace';

  @override
  String get transcriptTab => 'Přepis';

  @override
  String get actionItemsTab => 'Úkoly';

  @override
  String get deleteConversationTitle => 'Smazat konverzaci?';

  @override
  String get deleteConversationMessage => 'Opravdu chcete smazat tuto konverzaci? Tuto akci nelze vrátit zpět.';

  @override
  String get confirm => 'Potvrdit';

  @override
  String get cancel => 'Zrušit';

  @override
  String get ok => 'OK';

  @override
  String get delete => 'Smazat';

  @override
  String get add => 'Přidat';

  @override
  String get update => 'Aktualizovat';

  @override
  String get save => 'Uložit';

  @override
  String get edit => 'Upravit';

  @override
  String get close => 'Zavřít';

  @override
  String get clear => 'Vymazat';

  @override
  String get copyTranscript => 'Kopírovat přepis';

  @override
  String get copySummary => 'Kopírovat shrnutí';

  @override
  String get testPrompt => 'Testovat výzvu';

  @override
  String get reprocessConversation => 'Znovu zpracovat konverzaci';

  @override
  String get deleteConversation => 'Smazat konverzaci';

  @override
  String get contentCopied => 'Obsah zkopírován do schránky';

  @override
  String get failedToUpdateStarred => 'Nepodařilo se aktualizovat stav oblíbených.';

  @override
  String get conversationUrlNotShared => 'URL konverzace nelze sdílet.';

  @override
  String get errorProcessingConversation => 'Chyba při zpracování konverzace. Zkuste to prosím později.';

  @override
  String get noInternetConnection => 'Žádné připojení k internetu';

  @override
  String get unableToDeleteConversation => 'Nelze smazat konverzaci';

  @override
  String get somethingWentWrong => 'Něco se pokazilo! Zkuste to prosím později.';

  @override
  String get copyErrorMessage => 'Kopírovat chybovou zprávu';

  @override
  String get errorCopied => 'Chybová zpráva zkopírována do schránky';

  @override
  String get remaining => 'Zbývá';

  @override
  String get loading => 'Načítání...';

  @override
  String get loadingDuration => 'Načítání délky...';

  @override
  String secondsCount(int count) {
    return '$count sekund';
  }

  @override
  String get people => 'Lidé';

  @override
  String get addNewPerson => 'Přidat novou osobu';

  @override
  String get editPerson => 'Upravit osobu';

  @override
  String get createPersonHint => 'Vytvořte novou osobu a naučte Omi rozpoznat i její řeč!';

  @override
  String get speechProfile => 'Řečový Profil';

  @override
  String sampleNumber(int number) {
    return 'Vzorek $number';
  }

  @override
  String get settings => 'Nastavení';

  @override
  String get language => 'Jazyk';

  @override
  String get selectLanguage => 'Vybrat jazyk';

  @override
  String get deleting => 'Mazání...';

  @override
  String get pleaseCompleteAuthentication =>
      'Dokončete prosím ověření v prohlížeči. Jakmile budete hotovi, vraťte se do aplikace.';

  @override
  String get failedToStartAuthentication => 'Nepodařilo se spustit ověření';

  @override
  String get importStarted => 'Import byl zahájen! Budete informováni, až bude dokončen.';

  @override
  String get failedToStartImport => 'Nepodařilo se spustit import. Zkuste to prosím znovu.';

  @override
  String get couldNotAccessFile => 'K vybranému souboru se nepodařilo získat přístup';

  @override
  String get askOmi => 'Zeptat se Omi';

  @override
  String get done => 'Hotovo';

  @override
  String get disconnected => 'Odpojeno';

  @override
  String get searching => 'Vyhledávání...';

  @override
  String get connectDevice => 'Připojit zařízení';

  @override
  String get monthlyLimitReached => 'Dosáhli jste měsíčního limitu.';

  @override
  String get checkUsage => 'Zkontrolovat využití';

  @override
  String get syncingRecordings => 'Synchronizace nahrávek';

  @override
  String get recordingsToSync => 'Nahrávky k synchronizaci';

  @override
  String get allCaughtUp => 'Vše je aktuální';

  @override
  String get sync => 'Synchronizovat';

  @override
  String get pendantUpToDate => 'Přívěsek je aktuální';

  @override
  String get allRecordingsSynced => 'Všechny nahrávky jsou synchronizovány';

  @override
  String get syncingInProgress => 'Probíhá synchronizace';

  @override
  String get readyToSync => 'Připraveno k synchronizaci';

  @override
  String get tapSyncToStart => 'Klepněte na Synchronizovat';

  @override
  String get pendantNotConnected => 'Přívěsek není připojen. Připojte jej pro synchronizaci.';

  @override
  String get everythingSynced => 'Vše je již synchronizováno.';

  @override
  String get recordingsNotSynced => 'Máte nahrávky, které ještě nejsou synchronizovány.';

  @override
  String get syncingBackground => 'Budeme pokračovat v synchronizaci vašich nahrávek na pozadí.';

  @override
  String get noConversationsYet => 'Zatím žádné konverzace';

  @override
  String get noStarredConversations => 'Žádné konverzace s hvězdičkou';

  @override
  String get starConversationHint =>
      'Chcete-li konverzaci označit hvězdičkou, otevřete ji a klepněte na ikonu hvězdičky v záhlaví.';

  @override
  String get searchConversations => 'Hledat konverzace...';

  @override
  String selectedCount(int count, Object s) {
    return 'Vybráno: $count';
  }

  @override
  String get merge => 'Sloučit';

  @override
  String get mergeConversations => 'Sloučit konverzace';

  @override
  String mergeConversationsMessage(int count) {
    return 'Tím se spojí $count konverzací do jedné. Veškerý obsah bude sloučen a znovu vygenerován.';
  }

  @override
  String get mergingInBackground => 'Slučování na pozadí. Může to chvíli trvat.';

  @override
  String get failedToStartMerge => 'Nepodařilo se spustit sloučení';

  @override
  String get askAnything => 'Zeptejte se na cokoliv';

  @override
  String get noMessagesYet => 'Zatím žádné zprávy!\nProč nezačít konverzaci?';

  @override
  String get deletingMessages => 'Mazání vašich zpráv z paměti Omi...';

  @override
  String get messageCopied => '✨ Zpráva zkopírována do schránky';

  @override
  String get cannotReportOwnMessage => 'Nemůžete nahlásit vlastní zprávy.';

  @override
  String get reportMessage => 'Nahlásit zprávu';

  @override
  String get reportMessageConfirm => 'Opravdu chcete nahlásit tuto zprávu?';

  @override
  String get messageReported => 'Zpráva úspěšně nahlášena.';

  @override
  String get thankYouFeedback => 'Děkujeme za vaši zpětnou vazbu!';

  @override
  String get clearChat => 'Vymazat chat';

  @override
  String get clearChatConfirm => 'Opravdu chcete vymazat chat? Tuto akci nelze vrátit zpět.';

  @override
  String get maxFilesLimit => 'Najednou můžete nahrát pouze 4 soubory';

  @override
  String get chatWithOmi => 'Chat s Omi';

  @override
  String get apps => 'Aplikace';

  @override
  String get noAppsFound => 'Nebyly nalezeny žádné aplikace';

  @override
  String get tryAdjustingSearch => 'Zkuste upravit vyhledávání nebo filtry';

  @override
  String get createYourOwnApp => 'Vytvořte si vlastní aplikaci';

  @override
  String get buildAndShareApp => 'Vytvořte a sdílejte vlastní aplikaci';

  @override
  String get searchApps => 'Hledat aplikace...';

  @override
  String get myApps => 'Moje aplikace';

  @override
  String get installedApps => 'Nainstalované aplikace';

  @override
  String get unableToFetchApps =>
      'Nelze načíst aplikace :(\n\nZkontrolujte prosím připojení k internetu a zkuste to znovu.';

  @override
  String get aboutOmi => 'O Omi';

  @override
  String get privacyPolicy => 'Zásadami ochrany osobních údajů';

  @override
  String get visitWebsite => 'Navštívit web';

  @override
  String get helpOrInquiries => 'Pomoc nebo dotazy?';

  @override
  String get joinCommunity => 'Připojte se ke komunitě!';

  @override
  String get membersAndCounting => '8000+ členů a stále přibývá.';

  @override
  String get deleteAccountTitle => 'Smazat účet';

  @override
  String get deleteAccountConfirm => 'Opravdu chcete smazat svůj účet?';

  @override
  String get cannotBeUndone => 'Toto nelze vrátit zpět.';

  @override
  String get allDataErased => 'Všechny vaše vzpomínky a konverzace budou trvale smazány.';

  @override
  String get appsDisconnected => 'Vaše aplikace a integrace budou okamžitě odpojeny.';

  @override
  String get exportBeforeDelete => 'Před smazáním účtu si můžete exportovat data, ale po smazání je nelze obnovit.';

  @override
  String get deleteAccountCheckbox =>
      'Rozumím tomu, že smazání mého účtu je trvalé a všechna data včetně vzpomínek a konverzací budou ztracena a nelze je obnovit.';

  @override
  String get areYouSure => 'Jste si jisti?';

  @override
  String get deleteAccountFinal =>
      'Tato akce je nevratná a trvale smaže váš účet a všechna související data. Opravdu chcete pokračovat?';

  @override
  String get deleteNow => 'Smazat nyní';

  @override
  String get goBack => 'Zpět';

  @override
  String get checkBoxToConfirm =>
      'Zaškrtněte políčko pro potvrzení, že rozumíte tomu, že smazání účtu je trvalé a nevratné.';

  @override
  String get profile => 'Profil';

  @override
  String get name => 'Jméno';

  @override
  String get email => 'E-mail';

  @override
  String get customVocabulary => 'Vlastní Slovník';

  @override
  String get identifyingOthers => 'Identifikace Ostatních';

  @override
  String get paymentMethods => 'Platební Metody';

  @override
  String get conversationDisplay => 'Zobrazení Konverzací';

  @override
  String get dataPrivacy => 'Soukromí Dat';

  @override
  String get userId => 'ID Uživatele';

  @override
  String get notSet => 'Nenastaveno';

  @override
  String get userIdCopied => 'ID uživatele zkopírováno do schránky';

  @override
  String get systemDefault => 'Výchozí systém';

  @override
  String get planAndUsage => 'Plán a využití';

  @override
  String get offlineSync => 'Offline synchronizace';

  @override
  String get deviceSettings => 'Nastavení zařízení';

  @override
  String get integrations => 'Integrace';

  @override
  String get feedbackBug => 'Zpětná vazba / Chyba';

  @override
  String get helpCenter => 'Centrum nápovědy';

  @override
  String get developerSettings => 'Vývojářské nastavení';

  @override
  String get getOmiForMac => 'Získat Omi pro Mac';

  @override
  String get referralProgram => 'Doporučovací program';

  @override
  String get signOut => 'Odhlásit Se';

  @override
  String get appAndDeviceCopied => 'Podrobnosti o aplikaci a zařízení zkopírovány';

  @override
  String get wrapped2025 => 'Shrnutí 2025';

  @override
  String get yourPrivacyYourControl => 'Vaše soukromí, vaše kontrola';

  @override
  String get privacyIntro =>
      'V Omi se zavazujeme chránit vaše soukromí. Tato stránka vám umožňuje kontrolovat, jak jsou vaše data ukládána a používána.';

  @override
  String get learnMore => 'Dozvědět se více...';

  @override
  String get dataProtectionLevel => 'Úroveň ochrany dat';

  @override
  String get dataProtectionDesc =>
      'Vaše data jsou standardně zabezpečena silným šifrováním. Níže si prohlédněte svá nastavení a budoucí možnosti ochrany soukromí.';

  @override
  String get appAccess => 'Přístup aplikací';

  @override
  String get appAccessDesc =>
      'Následující aplikace mají přístup k vašim datům. Klepnutím na aplikaci spravujete její oprávnění.';

  @override
  String get noAppsExternalAccess => 'Žádné nainstalované aplikace nemají externí přístup k vašim datům.';

  @override
  String get deviceName => 'Název zařízení';

  @override
  String get deviceId => 'ID zařízení';

  @override
  String get firmware => 'Firmware';

  @override
  String get sdCardSync => 'Synchronizace SD karty';

  @override
  String get hardwareRevision => 'Revize hardwaru';

  @override
  String get modelNumber => 'Číslo modelu';

  @override
  String get manufacturer => 'Výrobce';

  @override
  String get doubleTap => 'Dvojité klepnutí';

  @override
  String get ledBrightness => 'Jas LED';

  @override
  String get micGain => 'Zesílení mikrofonu';

  @override
  String get disconnect => 'Odpojit';

  @override
  String get forgetDevice => 'Zapomenout zařízení';

  @override
  String get chargingIssues => 'Problémy s nabíjením';

  @override
  String get disconnectDevice => 'Odpojit zařízení';

  @override
  String get unpairDevice => 'Zrušit párování zařízení';

  @override
  String get unpairAndForget => 'Zrušit párování a zapomenout zařízení';

  @override
  String get deviceDisconnectedMessage => 'Vaše Omi bylo odpojeno 😔';

  @override
  String get deviceUnpairedMessage =>
      'Párování zařízení zrušeno. Přejděte do Nastavení > Bluetooth a zapomeňte zařízení pro dokončení zrušení párování.';

  @override
  String get unpairDialogTitle => 'Zrušit párování zařízení';

  @override
  String get unpairDialogMessage =>
      'Tím se zruší párování zařízení, aby mohlo být připojeno k jinému telefonu. Budete muset přejít do Nastavení > Bluetooth a zapomenout zařízení pro dokončení procesu.';

  @override
  String get deviceNotConnected => 'Zařízení není připojeno';

  @override
  String get connectDeviceMessage => 'Připojte své zařízení Omi pro přístup\nk nastavením a přizpůsobení zařízení';

  @override
  String get deviceInfoSection => 'Informace o zařízení';

  @override
  String get customizationSection => 'Přizpůsobení';

  @override
  String get hardwareSection => 'Hardware';

  @override
  String get v2Undetected => 'V2 nedetekováno';

  @override
  String get v2UndetectedMessage =>
      'Vidíme, že máte buď zařízení V1, nebo vaše zařízení není připojeno. Funkce SD karty je dostupná pouze pro zařízení V2.';

  @override
  String get endConversation => 'Ukončit konverzaci';

  @override
  String get pauseResume => 'Pozastavit/Obnovit';

  @override
  String get starConversation => 'Označit konverzaci hvězdičkou';

  @override
  String get doubleTapAction => 'Akce dvojitého klepnutí';

  @override
  String get endAndProcess => 'Ukončit a zpracovat konverzaci';

  @override
  String get pauseResumeRecording => 'Pozastavit/Obnovit nahrávání';

  @override
  String get starOngoing => 'Označit probíhající konverzaci hvězdičkou';

  @override
  String get off => 'Vyp';

  @override
  String get max => 'Maximum';

  @override
  String get mute => 'Ztlumit';

  @override
  String get quiet => 'Tiché';

  @override
  String get normal => 'Normální';

  @override
  String get high => 'Vysoké';

  @override
  String get micGainDescMuted => 'Mikrofon je ztlumený';

  @override
  String get micGainDescLow => 'Velmi tiché - pro hlučná prostředí';

  @override
  String get micGainDescModerate => 'Tiché - pro mírný hluk';

  @override
  String get micGainDescNeutral => 'Neutrální - vyvážené nahrávání';

  @override
  String get micGainDescSlightlyBoosted => 'Mírně zesílené - běžné použití';

  @override
  String get micGainDescBoosted => 'Zesílené - pro tichá prostředí';

  @override
  String get micGainDescHigh => 'Vysoké - pro vzdálené nebo tiché hlasy';

  @override
  String get micGainDescVeryHigh => 'Velmi vysoké - pro velmi tiché zdroje';

  @override
  String get micGainDescMax => 'Maximum - používejte opatrně';

  @override
  String get developerSettingsTitle => 'Nastavení pro vývojáře';

  @override
  String get saving => 'Ukládání...';

  @override
  String get personaConfig => 'Nakonfigurujte svou AI personu';

  @override
  String get beta => 'BETA';

  @override
  String get transcription => 'Přepis';

  @override
  String get transcriptionConfig => 'Nakonfigurovat poskytovatele STT';

  @override
  String get conversationTimeout => 'Časový limit konverzace';

  @override
  String get conversationTimeoutConfig => 'Nastavit, kdy konverzace automaticky skončí';

  @override
  String get importData => 'Importovat data';

  @override
  String get importDataConfig => 'Importovat data z jiných zdrojů';

  @override
  String get debugDiagnostics => 'Ladění a diagnostika';

  @override
  String get endpointUrl => 'URL koncového bodu';

  @override
  String get noApiKeys => 'Zatím žádné API klíče';

  @override
  String get createKeyToStart => 'Vytvořte klíč pro začátek';

  @override
  String get createKey => 'Vytvořit Klíč';

  @override
  String get docs => 'Dokumentace';

  @override
  String get yourOmiInsights => 'Vaše přehledy Omi';

  @override
  String get today => 'Dnes';

  @override
  String get thisMonth => 'Tento měsíc';

  @override
  String get thisYear => 'Letos';

  @override
  String get allTime => 'Vždy';

  @override
  String get noActivityYet => 'Zatím žádná aktivita';

  @override
  String get startConversationToSeeInsights => 'Začněte konverzaci s Omi,\nabyste zde viděli své přehledy využití.';

  @override
  String get listening => 'Naslouchání';

  @override
  String get listeningSubtitle => 'Celková doba, po kterou Omi aktivně naslouchalo.';

  @override
  String get understanding => 'Porozumění';

  @override
  String get understandingSubtitle => 'Slova pochopená z vašich konverzací.';

  @override
  String get providing => 'Poskytování';

  @override
  String get providingSubtitle => 'Úkoly a poznámky automaticky zachycené.';

  @override
  String get remembering => 'Zapamatování';

  @override
  String get rememberingSubtitle => 'Fakta a detaily zapamatované pro vás.';

  @override
  String get unlimitedPlan => 'Neomezený plán';

  @override
  String get managePlan => 'Spravovat plán';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'Váš plán bude zrušen dne $date.';
  }

  @override
  String renewsOn(String date) {
    return 'Váš plán se obnoví dne $date.';
  }

  @override
  String get basicPlan => 'Bezplatný plán';

  @override
  String usageLimitMessage(String used, int limit) {
    return 'Využito $used z $limit min';
  }

  @override
  String get upgrade => 'Upgradovat';

  @override
  String get upgradeToUnlimited => 'Upgradovat na neomezené';

  @override
  String basicPlanDesc(int limit) {
    return 'Váš plán zahrnuje $limit bezplatných minut měsíčně. Upgradujte pro neomezený přístup.';
  }

  @override
  String get shareStatsMessage => 'Sdílím své statistiky Omi! (omi.me - váš AI asistent, který je vždy online)';

  @override
  String get sharePeriodToday => 'Dnes Omi:';

  @override
  String get sharePeriodMonth => 'Tento měsíc Omi:';

  @override
  String get sharePeriodYear => 'Letos Omi:';

  @override
  String get sharePeriodAllTime => 'Dosud Omi:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 Naslouchalo $minutes minut';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 Porozumělo $words slovům';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ Poskytlo $count přehledů';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 Zapamatovalo si $count vzpomínek';
  }

  @override
  String get debugLogs => 'Protokoly ladění';

  @override
  String get debugLogsAutoDelete => 'Automaticky se smažou po 3 dnech.';

  @override
  String get debugLogsDesc => 'Pomáhá diagnostikovat problémy';

  @override
  String get noLogFilesFound => 'Nebyly nalezeny žádné soubory protokolu.';

  @override
  String get omiDebugLog => 'Protokol ladění Omi';

  @override
  String get logShared => 'Protokol sdílen';

  @override
  String get selectLogFile => 'Vybrat soubor protokolu';

  @override
  String get shareLogs => 'Sdílet protokoly';

  @override
  String get debugLogCleared => 'Protokol ladění vymazán';

  @override
  String get exportStarted => 'Export zahájen. Může to trvat několik sekund...';

  @override
  String get exportAllData => 'Exportovat všechna data';

  @override
  String get exportDataDesc => 'Exportovat konverzace do souboru JSON';

  @override
  String get exportedConversations => 'Exportované konverzace z Omi';

  @override
  String get exportShared => 'Export sdílen';

  @override
  String get deleteKnowledgeGraphTitle => 'Smazat graf znalostí?';

  @override
  String get deleteKnowledgeGraphMessage =>
      'Tím se smažou všechna odvozená data grafu znalostí (uzly a spojení). Vaše původní vzpomínky zůstanou v bezpečí. Graf bude v průběhu času znovu vytvořen nebo při dalším požadavku.';

  @override
  String get knowledgeGraphDeleted => 'Graf znalostí smazán';

  @override
  String deleteGraphFailed(String error) {
    return 'Smazání grafu se nezdařilo: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'Smazat graf znalostí';

  @override
  String get deleteKnowledgeGraphDesc => 'Vymazat všechny uzly a spojení';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'Server MCP';

  @override
  String get mcpServerDesc => 'Připojit AI asistenty k vašim datům';

  @override
  String get serverUrl => 'URL serveru';

  @override
  String get urlCopied => 'URL zkopírována';

  @override
  String get apiKeyAuth => 'Ověření API klíčem';

  @override
  String get header => 'Záhlaví';

  @override
  String get authorizationBearer => 'Authorization: Bearer <klíč>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'ID klienta';

  @override
  String get clientSecret => 'Tajný klíč klienta';

  @override
  String get useMcpApiKey => 'Použijte svůj MCP API klíč';

  @override
  String get webhooks => 'Webhooky';

  @override
  String get conversationEvents => 'Události konverzace';

  @override
  String get newConversationCreated => 'Vytvořena nová konverzace';

  @override
  String get realtimeTranscript => 'Přepis v reálném čase';

  @override
  String get transcriptReceived => 'Přepis přijat';

  @override
  String get audioBytes => 'Audio bajty';

  @override
  String get audioDataReceived => 'Audio data přijata';

  @override
  String get intervalSeconds => 'Interval (sekundy)';

  @override
  String get daySummary => 'Denní souhrn';

  @override
  String get summaryGenerated => 'Souhrn vygenerován';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'Přidat do claude_desktop_config.json';

  @override
  String get copyConfig => 'Kopírovat konfiguraci';

  @override
  String get configCopied => 'Konfigurace zkopírována do schránky';

  @override
  String get listeningMins => 'Naslouchání (min)';

  @override
  String get understandingWords => 'Porozumění (slova)';

  @override
  String get insights => 'Postřehy';

  @override
  String get memories => 'Vzpomínky';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return 'Tento měsíc využito $used z $limit min';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return 'Tento měsíc pochopeno $used z $limit slov';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return 'Tento měsíc získáno $used z $limit přehledů';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return 'Tento měsíc vytvořeno $used z $limit vzpomínek';
  }

  @override
  String get visibility => 'Viditelnost';

  @override
  String get visibilitySubtitle => 'Kontrolujte, které konverzace se zobrazují ve vašem seznamu';

  @override
  String get showShortConversations => 'Zobrazit krátké konverzace';

  @override
  String get showShortConversationsDesc => 'Zobrazit konverzace kratší než prahová hodnota';

  @override
  String get showDiscardedConversations => 'Zobrazit zahozené konverzace';

  @override
  String get showDiscardedConversationsDesc => 'Zahrnout konverzace označené jako zahozené';

  @override
  String get shortConversationThreshold => 'Prahová hodnota krátkých konverzací';

  @override
  String get shortConversationThresholdSubtitle =>
      'Konverzace kratší než tato hodnota budou skryty, pokud nejsou výše povoleny';

  @override
  String get durationThreshold => 'Prahová hodnota trvání';

  @override
  String get durationThresholdDesc => 'Skrýt konverzace kratší než tato hodnota';

  @override
  String minLabel(int count) {
    return '$count min';
  }

  @override
  String get customVocabularyTitle => 'Vlastní slovník';

  @override
  String get addWords => 'Přidat slova';

  @override
  String get addWordsDesc => 'Jména, výrazy nebo neobvyklá slova';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'Connect';

  @override
  String get comingSoon => 'Již brzy';

  @override
  String get integrationsFooter => 'Připojte své aplikace k zobrazení dat a metrik v chatu.';

  @override
  String get completeAuthInBrowser =>
      'Dokončete prosím ověření v prohlížeči. Jakmile budete hotovi, vraťte se do aplikace.';

  @override
  String failedToStartAuth(String appName) {
    return 'Nepodařilo se spustit ověření $appName';
  }

  @override
  String disconnectAppTitle(String appName) {
    return 'Odpojit $appName?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'Opravdu chcete odpojit od $appName? Můžete se kdykoli znovu připojit.';
  }

  @override
  String disconnectedFrom(String appName) {
    return 'Odpojeno od $appName';
  }

  @override
  String get failedToDisconnect => 'Nepodařilo se odpojit';

  @override
  String connectTo(String appName) {
    return 'Připojit k $appName';
  }

  @override
  String authAccessMessage(String appName) {
    return 'Budete muset autorizovat Omi pro přístup k vašim datům $appName. Tím se otevře váš prohlížeč pro ověření.';
  }

  @override
  String get continueAction => 'Pokračovat';

  @override
  String get languageTitle => 'Jazyk';

  @override
  String get primaryLanguage => 'Hlavní jazyk';

  @override
  String get automaticTranslation => 'Automatický překlad';

  @override
  String get detectLanguages => 'Detekovat 10+ jazyků';

  @override
  String get authorizeSavingRecordings => 'Autorizovat ukládání nahrávek';

  @override
  String get thanksForAuthorizing => 'Děkujeme za autorizaci!';

  @override
  String get needYourPermission => 'Potřebujeme vaše povolení';

  @override
  String get alreadyGavePermission =>
      'Již jste nám dali povolení k ukládání vašich nahrávek. Zde je připomenutí, proč to potřebujeme:';

  @override
  String get wouldLikePermission => 'Rádi bychom vaše povolení k ukládání vašich hlasových nahrávek. Zde je proč:';

  @override
  String get improveSpeechProfile => 'Vylepšit váš hlasový profil';

  @override
  String get improveSpeechProfileDesc =>
      'Nahrávky používáme k dalšímu trénování a vylepšování vašeho osobního hlasového profilu.';

  @override
  String get trainFamilyProfiles => 'Trénovat profily pro přátele a rodinu';

  @override
  String get trainFamilyProfilesDesc =>
      'Vaše nahrávky nám pomáhají rozpoznat a vytvářet profily pro vaše přátele a rodinu.';

  @override
  String get enhanceTranscriptAccuracy => 'Zvýšit přesnost přepisu';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'S vylepšením našeho modelu můžeme pro vaše nahrávky poskytovat lepší výsledky přepisu.';

  @override
  String get legalNotice =>
      'Právní upozornění: Legálnost nahrávání a ukládání hlasových dat se může lišit v závislosti na vaší lokalitě a způsobu použití této funkce. Je vaší odpovědností zajistit dodržování místních zákonů a předpisů.';

  @override
  String get alreadyAuthorized => 'Již autorizováno';

  @override
  String get authorize => 'Autorizovat';

  @override
  String get revokeAuthorization => 'Zrušit autorizaci';

  @override
  String get authorizationSuccessful => 'Autorizace úspěšná!';

  @override
  String get failedToAuthorize => 'Autorizace se nezdařila. Zkuste to prosím znovu.';

  @override
  String get authorizationRevoked => 'Autorizace zrušena.';

  @override
  String get recordingsDeleted => 'Nahrávky smazány.';

  @override
  String get failedToRevoke => 'Zrušení autorizace se nezdařilo. Zkuste to prosím znovu.';

  @override
  String get permissionRevokedTitle => 'Povolení zrušeno';

  @override
  String get permissionRevokedMessage => 'Chcete, abychom odstranili také všechny vaše existující nahrávky?';

  @override
  String get yes => 'Ano';

  @override
  String get editName => 'Upravit jméno';

  @override
  String get howShouldOmiCallYou => 'Jak vás má Omi oslovovat?';

  @override
  String get enterYourName => 'Zadejte své jméno';

  @override
  String get nameCannotBeEmpty => 'Jméno nemůže být prázdné';

  @override
  String get nameUpdatedSuccessfully => 'Jméno úspěšně aktualizováno!';

  @override
  String get calendarSettings => 'Nastavení kalendáře';

  @override
  String get calendarProviders => 'Poskytovatelé kalendáře';

  @override
  String get macOsCalendar => 'Kalendář macOS';

  @override
  String get connectMacOsCalendar => 'Připojit váš místní kalendář macOS';

  @override
  String get googleCalendar => 'Kalendář Google';

  @override
  String get syncGoogleAccount => 'Synchronizovat s vaším účtem Google';

  @override
  String get showMeetingsMenuBar => 'Zobrazit nadcházející schůzky v menu baru';

  @override
  String get showMeetingsMenuBarDesc => 'Zobrazit vaši další schůzku a čas do jejího začátku v menu baru macOS';

  @override
  String get showEventsNoParticipants => 'Zobrazit události bez účastníků';

  @override
  String get showEventsNoParticipantsDesc =>
      'Pokud je povoleno, Již brzy zobrazuje události bez účastníků nebo video odkazu.';

  @override
  String get yourMeetings => 'Vaše schůzky';

  @override
  String get refresh => 'Obnovit';

  @override
  String get noUpcomingMeetings => 'Žádné nadcházející schůzky';

  @override
  String get checkingNextDays => 'Kontrola dalších 30 dnů';

  @override
  String get tomorrow => 'Zítra';

  @override
  String get googleCalendarComingSoon => 'Integrace s Kalendářem Google již brzy!';

  @override
  String connectedAsUser(String userId) {
    return 'Připojeno jako uživatel: $userId';
  }

  @override
  String get defaultWorkspace => 'Výchozí pracovní prostor';

  @override
  String get tasksCreatedInWorkspace => 'Úkoly budou vytvořeny v tomto pracovním prostoru';

  @override
  String get defaultProjectOptional => 'Výchozí projekt (volitelné)';

  @override
  String get leaveUnselectedTasks => 'Ponechte nevybrané pro vytváření úkolů bez projektu';

  @override
  String get noProjectsInWorkspace => 'V tomto pracovním prostoru nebyly nalezeny žádné projekty';

  @override
  String get conversationTimeoutDesc => 'Vyberte, jak dlouho čekat v tichosti před automatickým ukončením konverzace:';

  @override
  String get timeout2Minutes => '2 minuty';

  @override
  String get timeout2MinutesDesc => 'Ukončit konverzaci po 2 minutách ticha';

  @override
  String get timeout5Minutes => '5 minut';

  @override
  String get timeout5MinutesDesc => 'Ukončit konverzaci po 5 minutách ticha';

  @override
  String get timeout10Minutes => '10 minut';

  @override
  String get timeout10MinutesDesc => 'Ukončit konverzaci po 10 minutách ticha';

  @override
  String get timeout30Minutes => '30 minut';

  @override
  String get timeout30MinutesDesc => 'Ukončit konverzaci po 30 minutách ticha';

  @override
  String get timeout4Hours => '4 hodiny';

  @override
  String get timeout4HoursDesc => 'Ukončit konverzaci po 4 hodinách ticha';

  @override
  String get conversationEndAfterHours => 'Konverzace nyní skončí po 4 hodinách ticha';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Konverzace nyní skončí po $minutes minutě/minutách ticha';
  }

  @override
  String get tellUsPrimaryLanguage => 'Řekněte nám svůj primární jazyk';

  @override
  String get languageForTranscription => 'Nastavte svůj jazyk pro ostřejší přepisy a personalizovaný zážitek.';

  @override
  String get singleLanguageModeInfo => 'Režim jednoho jazyka je povolen. Překlad je zakázán pro vyšší přesnost.';

  @override
  String get searchLanguageHint => 'Hledat jazyk podle názvu nebo kódu';

  @override
  String get noLanguagesFound => 'Nebyly nalezeny žádné jazyky';

  @override
  String get skip => 'Přeskočit';

  @override
  String languageSetTo(String language) {
    return 'Jazyk nastaven na $language';
  }

  @override
  String get failedToSetLanguage => 'Nastavení jazyka se nezdařilo';

  @override
  String appSettings(String appName) {
    return 'Nastavení $appName';
  }

  @override
  String disconnectFromApp(String appName) {
    return 'Odpojit od $appName?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'Tím se odstraní vaše ověření $appName. Pro opětovné použití se budete muset znovu připojit.';
  }

  @override
  String connectedToApp(String appName) {
    return 'Připojeno k $appName';
  }

  @override
  String get account => 'Účet';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Vaše úkoly budou synchronizovány s vaším účtem $appName';
  }

  @override
  String get defaultSpace => 'Výchozí prostor';

  @override
  String get selectSpaceInWorkspace => 'Vyberte prostor ve vašem pracovním prostoru';

  @override
  String get noSpacesInWorkspace => 'V tomto pracovním prostoru nebyly nalezeny žádné prostory';

  @override
  String get defaultList => 'Výchozí seznam';

  @override
  String get tasksAddedToList => 'Úkoly budou přidány do tohoto seznamu';

  @override
  String get noListsInSpace => 'V tomto prostoru nebyly nalezeny žádné seznamy';

  @override
  String failedToLoadRepos(String error) {
    return 'Načtení repozitářů se nezdařilo: $error';
  }

  @override
  String get defaultRepoSaved => 'Výchozí repozitář uložen';

  @override
  String get failedToSaveDefaultRepo => 'Uložení výchozího repozitáře se nezdařilo';

  @override
  String get defaultRepository => 'Výchozí repozitář';

  @override
  String get selectDefaultRepoDesc =>
      'Vyberte výchozí repozitář pro vytváření problémů. Při vytváření problémů můžete stále specifikovat jiný repozitář.';

  @override
  String get noReposFound => 'Nenalezeny žádné repozitáře';

  @override
  String get private => 'Soukromé';

  @override
  String updatedDate(String date) {
    return 'Aktualizováno $date';
  }

  @override
  String get yesterday => 'Včera';

  @override
  String daysAgo(int count) {
    return 'před $count dny';
  }

  @override
  String get oneWeekAgo => 'před 1 týdnem';

  @override
  String weeksAgo(int count) {
    return 'před $count týdny';
  }

  @override
  String get oneMonthAgo => 'před 1 měsícem';

  @override
  String monthsAgo(int count) {
    return 'před $count měsíci';
  }

  @override
  String get issuesCreatedInRepo => 'Problémy budou vytvořeny ve vašem výchozím repozitáři';

  @override
  String get taskIntegrations => 'Integrace úkolů';

  @override
  String get configureSettings => 'Nakonfigurovat nastavení';

  @override
  String get completeAuthBrowser =>
      'Dokončete prosím ověření v prohlížeči. Jakmile budete hotovi, vraťte se do aplikace.';

  @override
  String failedToStartAppAuth(String appName) {
    return 'Spuštění ověření $appName se nezdařilo';
  }

  @override
  String connectToAppTitle(String appName) {
    return 'Připojit k $appName';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Budete muset autorizovat Omi k vytváření úkolů ve vašem účtu $appName. Tím se otevře váš prohlížeč pro ověření.';
  }

  @override
  String get continueButton => 'Pokračovat';

  @override
  String appIntegration(String appName) {
    return 'Integrace $appName';
  }

  @override
  String integrationComingSoon(String appName) {
    return 'Integrace s $appName již brzy! Usilovně pracujeme na tom, abychom vám přinesli více možností správy úkolů.';
  }

  @override
  String get gotIt => 'Rozumím';

  @override
  String get tasksExportedOneApp => 'Úkoly lze exportovat do jedné aplikace najednou.';

  @override
  String get completeYourUpgrade => 'Dokončete svůj upgrade';

  @override
  String get importConfiguration => 'Importovat konfiguraci';

  @override
  String get exportConfiguration => 'Exportovat konfiguraci';

  @override
  String get bringYourOwn => 'Přineste si vlastní';

  @override
  String get payYourSttProvider => 'Používejte Omi zdarma. Platíte pouze svému poskytovateli STT přímo.';

  @override
  String get freeMinutesMonth => '1 200 bezplatných minut měsíčně. Neomezené s ';

  @override
  String get omiUnlimited => 'Omi Unlimited';

  @override
  String get hostRequired => 'Host je povinný';

  @override
  String get validPortRequired => 'Je vyžadován platný port';

  @override
  String get validWebsocketUrlRequired => 'Je vyžadována platná URL WebSocket (wss://)';

  @override
  String get apiUrlRequired => 'URL API je povinná';

  @override
  String get apiKeyRequired => 'API klíč je povinný';

  @override
  String get invalidJsonConfig => 'Neplatná konfigurace JSON';

  @override
  String errorSaving(String error) {
    return 'Chyba při ukládání: $error';
  }

  @override
  String get configCopiedToClipboard => 'Konfigurace zkopírována do schránky';

  @override
  String get pasteJsonConfig => 'Vložte níže svou konfiguraci JSON:';

  @override
  String get addApiKeyAfterImport => 'Po importu budete muset přidat svůj vlastní API klíč';

  @override
  String get paste => 'Vložit';

  @override
  String get import => 'Importovat';

  @override
  String get invalidProviderInConfig => 'Neplatný poskytovatel v konfiguraci';

  @override
  String importedConfig(String providerName) {
    return 'Importována konfigurace $providerName';
  }

  @override
  String invalidJson(String error) {
    return 'Neplatný JSON: $error';
  }

  @override
  String get provider => 'Poskytovatel';

  @override
  String get live => 'Živě';

  @override
  String get onDevice => 'Na zařízení';

  @override
  String get apiUrl => 'URL API';

  @override
  String get enterSttHttpEndpoint => 'Zadejte koncový bod HTTP vašeho STT';

  @override
  String get websocketUrl => 'URL WebSocket';

  @override
  String get enterLiveSttWebsocket => 'Zadejte WebSocket koncový bod vašeho živého STT';

  @override
  String get apiKey => 'API klíč';

  @override
  String get enterApiKey => 'Zadejte svůj API klíč';

  @override
  String get storedLocallyNeverShared => 'Uloženo lokálně, nikdy nesdíleno';

  @override
  String get host => 'Hostitel';

  @override
  String get port => 'Port';

  @override
  String get advanced => 'Pokročilé';

  @override
  String get configuration => 'Konfigurace';

  @override
  String get requestConfiguration => 'Konfigurace požadavku';

  @override
  String get responseSchema => 'Schéma odpovědi';

  @override
  String get modified => 'Upraveno';

  @override
  String get resetRequestConfig => 'Obnovit výchozí konfiguraci požadavku';

  @override
  String get logs => 'Protokoly';

  @override
  String get logsCopied => 'Protokoly zkopírovány';

  @override
  String get noLogsYet => 'Zatím žádné protokoly. Začněte nahrávat, abyste viděli aktivitu vlastního STT.';

  @override
  String deviceUsesCodec(String device, String reason) {
    return '$device používá $reason. Bude použito Omi.';
  }

  @override
  String get omiTranscription => 'Přepis Omi';

  @override
  String get bestInClassTranscription => 'Nejlepší přepis ve své třídě bez nutnosti nastavení';

  @override
  String get instantSpeakerLabels => 'Okamžité štítky mluvčích';

  @override
  String get languageTranslation => 'Překlad 100+ jazyků';

  @override
  String get optimizedForConversation => 'Optimalizováno pro konverzaci';

  @override
  String get autoLanguageDetection => 'Automatická detekce jazyka';

  @override
  String get highAccuracy => 'Vysoká přesnost';

  @override
  String get privacyFirst => 'Soukromí na prvním místě';

  @override
  String get saveChanges => 'Uložit změny';

  @override
  String get resetToDefault => 'Obnovit výchozí';

  @override
  String get viewTemplate => 'Zobrazit šablonu';

  @override
  String get trySomethingLike => 'Zkuste něco jako...';

  @override
  String get tryIt => 'Vyzkoušejte to';

  @override
  String get creatingPlan => 'Vytváření plánu';

  @override
  String get developingLogic => 'Vývoj logiky';

  @override
  String get designingApp => 'Navrhování aplikace';

  @override
  String get generatingIconStep => 'Generování ikony';

  @override
  String get finalTouches => 'Závěrečné úpravy';

  @override
  String get processing => 'Zpracování...';

  @override
  String get features => 'Funkce';

  @override
  String get creatingYourApp => 'Vytváření vaší aplikace...';

  @override
  String get generatingIcon => 'Generování ikony...';

  @override
  String get whatShouldWeMake => 'Co bychom měli vytvořit?';

  @override
  String get appName => 'App Name';

  @override
  String get description => 'Popis';

  @override
  String get publicLabel => 'Veřejné';

  @override
  String get privateLabel => 'Soukromé';

  @override
  String get free => 'Zdarma';

  @override
  String get perMonth => '/ Měsíc';

  @override
  String get tailoredConversationSummaries => 'Přizpůsobená shrnutí konverzací';

  @override
  String get customChatbotPersonality => 'Vlastní osobnost chatbota';

  @override
  String get makePublic => 'Zveřejnit';

  @override
  String get anyoneCanDiscover => 'Kdokoli může objevit vaši aplikaci';

  @override
  String get onlyYouCanUse => 'Pouze vy můžete používat tuto aplikaci';

  @override
  String get paidApp => 'Placená aplikace';

  @override
  String get usersPayToUse => 'Uživatelé platí za použití vaší aplikace';

  @override
  String get freeForEveryone => 'Zdarma pro všechny';

  @override
  String get perMonthLabel => '/ měsíc';

  @override
  String get creating => 'Vytváření...';

  @override
  String get createApp => 'Vytvořit aplikaci';

  @override
  String get searchingForDevices => 'Hledání zařízení...';

  @override
  String devicesFoundNearby(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'ZAŘÍZENÍ',
      one: 'ZAŘÍZENÍ',
    );
    return '$count $_temp0 NALEZENO V BLÍZKOSTI';
  }

  @override
  String get pairingSuccessful => 'PÁROVÁNÍ ÚSPĚŠNÉ';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Chyba při připojování k Apple Watch: $error';
  }

  @override
  String get dontShowAgain => 'Nezobrazovat znovu';

  @override
  String get iUnderstand => 'Rozumím';

  @override
  String get enableBluetooth => 'Povolit Bluetooth';

  @override
  String get bluetoothNeeded =>
      'Omi potřebuje Bluetooth pro připojení k vašemu nositelného zařízení. Povolte prosím Bluetooth a zkuste to znovu.';

  @override
  String get contactSupport => 'Kontaktovat podporu?';

  @override
  String get connectLater => 'Připojit později';

  @override
  String get grantPermissions => 'Udělit oprávnění';

  @override
  String get backgroundActivity => 'Aktivita na pozadí';

  @override
  String get backgroundActivityDesc => 'Umožněte Omi běžet na pozadí pro lepší stabilitu';

  @override
  String get locationAccess => 'Přístup k poloze';

  @override
  String get locationAccessDesc => 'Povolte polohu na pozadí pro plný zážitek';

  @override
  String get notifications => 'Oznámení';

  @override
  String get notificationsDesc => 'Povolte oznámení, abyste byli informováni';

  @override
  String get locationServiceDisabled => 'Služba určování polohy zakázána';

  @override
  String get locationServiceDisabledDesc =>
      'Služba určování polohy je zakázána. Přejděte do Nastavení > Soukromí a zabezpečení > Služby určování polohy a povolte ji';

  @override
  String get backgroundLocationDenied => 'Přístup k poloze na pozadí odepřen';

  @override
  String get backgroundLocationDeniedDesc =>
      'Přejděte do nastavení zařízení a nastavte oprávnění k poloze na \"Vždy povolit\"';

  @override
  String get lovingOmi => 'Líbí se vám Omi?';

  @override
  String get leaveReviewIos =>
      'Pomozte nám oslovit více lidí tím, že zanecháte hodnocení v App Store. Vaše zpětná vazba pro nás hodně znamená!';

  @override
  String get leaveReviewAndroid =>
      'Pomozte nám oslovit více lidí tím, že zanecháte hodnocení v Obchodě Google Play. Vaše zpětná vazba pro nás hodně znamená!';

  @override
  String get rateOnAppStore => 'Ohodnotit v App Store';

  @override
  String get rateOnGooglePlay => 'Ohodnotit v Google Play';

  @override
  String get maybeLater => 'Možná později';

  @override
  String get speechProfileIntro => 'Omi potřebuje poznat vaše cíle a váš hlas. Později to budete moci upravit.';

  @override
  String get getStarted => 'Začít';

  @override
  String get allDone => 'Vše hotovo!';

  @override
  String get keepGoing => 'Pokračujte dál, jde vám to skvěle';

  @override
  String get skipThisQuestion => 'Přeskočit tuto otázku';

  @override
  String get skipForNow => 'Zatím přeskočit';

  @override
  String get connectionError => 'Chyba připojení';

  @override
  String get connectionErrorDesc =>
      'Nepodařilo se připojit k serveru. Zkontrolujte prosím připojení k internetu a zkuste to znovu.';

  @override
  String get invalidRecordingMultipleSpeakers => 'Detekována neplatná nahrávka';

  @override
  String get multipleSpeakersDesc =>
      'Zdá se, že v nahrávce je více mluvčích. Ujistěte se prosím, že jste na tichém místě, a zkuste to znovu.';

  @override
  String get tooShortDesc => 'Není detekován dostatek řeči. Mluvte prosím více a zkuste to znovu.';

  @override
  String get invalidRecordingDesc => 'Ujistěte se prosím, že mluvíte alespoň 5 sekund a ne více než 90.';

  @override
  String get areYouThere => 'Jste tam?';

  @override
  String get noSpeechDesc =>
      'Nemohli jsme detekovat žádnou řeč. Ujistěte se prosím, že mluvíte alespoň 10 sekund a ne více než 3 minuty.';

  @override
  String get connectionLost => 'Spojení ztraceno';

  @override
  String get connectionLostDesc =>
      'Spojení bylo přerušeno. Zkontrolujte prosím připojení k internetu a zkuste to znovu.';

  @override
  String get tryAgain => 'Zkusit znovu';

  @override
  String get connectOmiOmiGlass => 'Připojit Omi / OmiGlass';

  @override
  String get continueWithoutDevice => 'Pokračovat bez zařízení';

  @override
  String get permissionsRequired => 'Vyžadována oprávnění';

  @override
  String get permissionsRequiredDesc =>
      'Tato aplikace potřebuje oprávnění Bluetooth a Poloha, aby fungovala správně. Povolte je prosím v nastavení.';

  @override
  String get openSettings => 'Otevřít nastavení';

  @override
  String get wantDifferentName => 'Chcete jiné jméno?';

  @override
  String get whatsYourName => 'Jak se jmenujete?';

  @override
  String get speakTranscribeSummarize => 'Mluvte. Přepisujte. Shrňte.';

  @override
  String get signInWithApple => 'Přihlásit se přes Apple';

  @override
  String get signInWithGoogle => 'Přihlásit se přes Google';

  @override
  String get byContinuingAgree => 'Pokračováním souhlasíte s našimi ';

  @override
  String get termsOfUse => 'Podmínkami použití';

  @override
  String get omiYourAiCompanion => 'Omi – Váš AI společník';

  @override
  String get captureEveryMoment =>
      'Zachyťte každý okamžik. Získejte souhrny\npodporované AI. Už nikdy si nedělejte poznámky.';

  @override
  String get appleWatchSetup => 'Nastavení Apple Watch';

  @override
  String get permissionRequestedExclaim => 'Oprávnění požadováno!';

  @override
  String get microphonePermission => 'Oprávnění k mikrofonu';

  @override
  String get permissionGrantedNow =>
      'Oprávnění uděleno! Nyní:\n\nOtevřete aplikaci Omi na hodinkách a klepněte níže na \"Pokračovat\"';

  @override
  String get needMicrophonePermission =>
      'Potřebujeme oprávnění k mikrofonu.\n\n1. Klepněte na \"Udělit oprávnění\"\n2. Povolte na svém iPhone\n3. Aplikace na hodinkách se zavře\n4. Znovu otevřete a klepněte na \"Pokračovat\"';

  @override
  String get grantPermissionButton => 'Udělit oprávnění';

  @override
  String get needHelp => 'Potřebujete pomoc?';

  @override
  String get troubleshootingSteps =>
      'Řešení problémů:\n\n1. Ujistěte se, že Omi je nainstalováno na vašich hodinkách\n2. Otevřete aplikaci Omi na hodinkách\n3. Hledejte vyskakovací okno s oprávněním\n4. Klepněte na \"Povolit\", když budete vyzváni\n5. Aplikace na hodinkách se zavře - znovu ji otevřete\n6. Vraťte se a klepněte na \"Pokračovat\" na svém iPhone';

  @override
  String get recordingStartedSuccessfully => 'Nahrávání úspěšně zahájeno!';

  @override
  String get permissionNotGrantedYet =>
      'Oprávnění ještě nebylo uděleno. Ujistěte se prosím, že jste povolili přístup k mikrofonu a znovu otevřeli aplikaci na hodinkách.';

  @override
  String errorRequestingPermission(String error) {
    return 'Chyba při žádosti o oprávnění: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'Chyba při zahájení nahrávání: $error';
  }

  @override
  String get selectPrimaryLanguage => 'Vyberte svůj primární jazyk';

  @override
  String get languageBenefits => 'Nastavte svůj jazyk pro ostřejší přepisy a personalizovaný zážitek';

  @override
  String get whatsYourPrimaryLanguage => 'Jaký je váš primární jazyk?';

  @override
  String get selectYourLanguage => 'Vyberte svůj jazyk';

  @override
  String get personalGrowthJourney => 'Vaše cesta osobního růstu s AI, které naslouchá každému vašemu slovu.';

  @override
  String get actionItemsTitle => 'Úkoly';

  @override
  String get actionItemsDescription => 'Klepněte pro úpravu • Dlouze stiskněte pro výběr • Přejeďte pro akce';

  @override
  String get tabToDo => 'K provedení';

  @override
  String get tabDone => 'Hotovo';

  @override
  String get tabOld => 'Staré';

  @override
  String get emptyTodoMessage => '🎉 Vše máte hotové!\nŽádné nevyřízené úkoly';

  @override
  String get emptyDoneMessage => 'Zatím žádné dokončené položky';

  @override
  String get emptyOldMessage => '✅ Žádné staré úkoly';

  @override
  String get noItems => 'Žádné položky';

  @override
  String get actionItemMarkedIncomplete => 'Úkol označen jako nedokončený';

  @override
  String get actionItemCompleted => 'Úkol dokončen';

  @override
  String get deleteActionItemTitle => 'Smazat úkol';

  @override
  String get deleteActionItemMessage => 'Opravdu chcete tento úkol smazat?';

  @override
  String get deleteSelectedItemsTitle => 'Smazat vybrané položky';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Opravdu chcete smazat $count vybraný/vybrané/vybraných úkol$s?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'Úkol \"$description\" smazán';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return 'Smazáno $count úkol$s';
  }

  @override
  String get failedToDeleteItem => 'Smazání úkolu se nezdařilo';

  @override
  String get failedToDeleteItems => 'Smazání položek se nezdařilo';

  @override
  String get failedToDeleteSomeItems => 'Smazání některých položek se nezdařilo';

  @override
  String get welcomeActionItemsTitle => 'Připraveno na úkoly';

  @override
  String get welcomeActionItemsDescription =>
      'Vaše AI automaticky extrahuje úkoly a to-dos z vašich konverzací. Objeví se zde, když budou vytvořeny.';

  @override
  String get autoExtractionFeature => 'Automaticky extrahováno z konverzací';

  @override
  String get editSwipeFeature => 'Klepněte pro úpravu, přejeďte pro dokončení nebo smazání';

  @override
  String itemsSelected(int count) {
    return 'Vybráno: $count';
  }

  @override
  String get selectAll => 'Vybrat vše';

  @override
  String get deleteSelected => 'Smazat vybrané';

  @override
  String get searchMemories => 'Hledat vzpomínky...';

  @override
  String get memoryDeleted => 'Vzpomínka smazána.';

  @override
  String get undo => 'Vrátit zpět';

  @override
  String get noMemoriesYet => '🧠 Zatím žádné vzpomínky';

  @override
  String get noAutoMemories => 'Zatím žádné automaticky extrahované vzpomínky';

  @override
  String get noManualMemories => 'Zatím žádné manuální vzpomínky';

  @override
  String get noMemoriesInCategories => 'Žádné vzpomínky v těchto kategoriích';

  @override
  String get noMemoriesFound => '🔍 Nenalezeny žádné vzpomínky';

  @override
  String get addFirstMemory => 'Přidat první vzpomínku';

  @override
  String get clearMemoryTitle => 'Vymazat paměť Omi';

  @override
  String get clearMemoryMessage => 'Opravdu chcete vymazat paměť Omi? Tuto akci nelze vrátit zpět.';

  @override
  String get clearMemoryButton => 'Vymazat paměť';

  @override
  String get memoryClearedSuccess => 'Paměť Omi o vás byla vymazána';

  @override
  String get noMemoriesToDelete => 'Žádné vzpomínky ke smazání';

  @override
  String get createMemoryTooltip => 'Vytvořit novou vzpomínku';

  @override
  String get createActionItemTooltip => 'Vytvořit nový úkol';

  @override
  String get memoryManagement => 'Správa vzpomínek';

  @override
  String get filterMemories => 'Filtrovat vzpomínky';

  @override
  String totalMemoriesCount(int count) {
    return 'Máte celkem $count vzpomínek';
  }

  @override
  String get publicMemories => 'Veřejné vzpomínky';

  @override
  String get privateMemories => 'Soukromé vzpomínky';

  @override
  String get makeAllPrivate => 'Nastavit všechny vzpomínky jako soukromé';

  @override
  String get makeAllPublic => 'Nastavit všechny vzpomínky jako veřejné';

  @override
  String get deleteAllMemories => 'Smazat všechny vzpomínky';

  @override
  String get allMemoriesPrivateResult => 'Všechny vzpomínky jsou nyní soukromé';

  @override
  String get allMemoriesPublicResult => 'Všechny vzpomínky jsou nyní veřejné';

  @override
  String get newMemory => '✨ Nová vzpomínka';

  @override
  String get editMemory => '✏️ Upravit vzpomínku';

  @override
  String get memoryContentHint => 'Rád/a jím zmrzlinu...';

  @override
  String get failedToSaveMemory => 'Uložení se nezdařilo. Zkontrolujte prosím připojení.';

  @override
  String get saveMemory => 'Uložit vzpomínku';

  @override
  String get retry => 'Opakovat';

  @override
  String get createActionItem => 'Vytvořit úkol';

  @override
  String get editActionItem => 'Upravit úkol';

  @override
  String get actionItemDescriptionHint => 'Co je třeba udělat?';

  @override
  String get actionItemDescriptionEmpty => 'Popis úkolu nemůže být prázdný.';

  @override
  String get actionItemUpdated => 'Úkol aktualizován';

  @override
  String get failedToUpdateActionItem => 'Aktualizace úkolu selhala';

  @override
  String get actionItemCreated => 'Úkol vytvořen';

  @override
  String get failedToCreateActionItem => 'Vytvoření úkolu selhalo';

  @override
  String get dueDate => 'Termín';

  @override
  String get time => 'Čas';

  @override
  String get addDueDate => 'Přidat termín dokončení';

  @override
  String get pressDoneToSave => 'Stiskněte hotovo pro uložení';

  @override
  String get pressDoneToCreate => 'Stiskněte hotovo pro vytvoření';

  @override
  String get filterAll => 'Vše';

  @override
  String get filterSystem => 'O vás';

  @override
  String get filterInteresting => 'Přehledy';

  @override
  String get filterManual => 'Manuální';

  @override
  String get completed => 'Dokončeno';

  @override
  String get markComplete => 'Označit jako dokončené';

  @override
  String get actionItemDeleted => 'Úkol smazán';

  @override
  String get failedToDeleteActionItem => 'Smazání úkolu selhalo';

  @override
  String get deleteActionItemConfirmTitle => 'Smazat úkol';

  @override
  String get deleteActionItemConfirmMessage => 'Opravdu chcete smazat tento úkol?';

  @override
  String get appLanguage => 'Jazyk aplikace';

  @override
  String get appInterfaceSectionTitle => 'ROZHRANÍ APLIKACE';

  @override
  String get speechTranscriptionSectionTitle => 'ŘEČ A PŘEPIS';

  @override
  String get languageSettingsHelperText =>
      'Jazyk aplikace mění nabídky a tlačítka. Jazyk řeči ovlivňuje, jak jsou vaše nahrávky přepisovány.';

  @override
  String get translationNotice => 'Oznámení o překladu';

  @override
  String get translationNoticeMessage =>
      'Omi překládá konverzace do vašeho hlavního jazyka. Aktualizujte to kdykoli v Nastavení → Profily.';

  @override
  String get pleaseCheckInternetConnection => 'Zkontrolujte prosím připojení k internetu a zkuste to znovu';

  @override
  String get pleaseSelectReason => 'Vyberte prosím důvod';

  @override
  String get tellUsMoreWhatWentWrong => 'Řekněte nám více o tom, co se pokazilo...';

  @override
  String get selectText => 'Vybrat text';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Maximum $count cílů povoleno';
  }

  @override
  String get conversationCannotBeMerged => 'Tuto konverzaci nelze sloučit (zamčena nebo se již slučuje)';

  @override
  String get pleaseEnterFolderName => 'Zadejte prosím název složky';

  @override
  String get failedToCreateFolder => 'Vytvoření složky selhalo';

  @override
  String get failedToUpdateFolder => 'Aktualizace složky selhala';

  @override
  String get folderName => 'Název složky';

  @override
  String get descriptionOptional => 'Description (optional)';

  @override
  String get failedToDeleteFolder => 'Odstranění složky selhalo';

  @override
  String get editFolder => 'Upravit složku';

  @override
  String get deleteFolder => 'Smazat složku';

  @override
  String get transcriptCopiedToClipboard => 'Přepis zkopírován do schránky';

  @override
  String get summaryCopiedToClipboard => 'Souhrn zkopírován do schránky';

  @override
  String get conversationUrlCouldNotBeShared => 'URL konverzace se nepodařilo sdílet.';

  @override
  String get urlCopiedToClipboard => 'URL zkopírována do schránky';

  @override
  String get exportTranscript => 'Exportovat přepis';

  @override
  String get exportSummary => 'Exportovat souhrn';

  @override
  String get exportButton => 'Exportovat';

  @override
  String get actionItemsCopiedToClipboard => 'Položky akcí zkopírovány do schránky';

  @override
  String get summarize => 'Shrnout';

  @override
  String get generateSummary => 'Vygenerovat shrnutí';

  @override
  String get conversationNotFoundOrDeleted => 'Konverzace nenalezena nebo byla smazána';

  @override
  String get deleteMemory => 'Smazat vzpomínku';

  @override
  String get thisActionCannotBeUndone => 'Tuto akci nelze vrátit zpět.';

  @override
  String memoriesCount(int count) {
    return '$count vzpomínek';
  }

  @override
  String get noMemoriesInCategory => 'V této kategorii ještě nejsou žádné vzpomínky';

  @override
  String get addYourFirstMemory => 'Přidejte svou první vzpomínku';

  @override
  String get firmwareDisconnectUsb => 'Odpojte USB';

  @override
  String get firmwareUsbWarning => 'Připojení USB během aktualizací může poškodit vaše zařízení.';

  @override
  String get firmwareBatteryAbove15 => 'Baterie nad 15%';

  @override
  String get firmwareEnsureBattery => 'Ujistěte se, že vaše zařízení má 15% baterie.';

  @override
  String get firmwareStableConnection => 'Stabilní připojení';

  @override
  String get firmwareConnectWifi => 'Připojte se k WiFi nebo mobilním datům.';

  @override
  String failedToStartUpdate(String error) {
    return 'Nepodařilo se spustit aktualizaci: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'Před aktualizací se ujistěte:';

  @override
  String get confirmed => 'Potvrzeno!';

  @override
  String get release => 'Uvolnit';

  @override
  String get slideToUpdate => 'Přejeďte pro aktualizaci';

  @override
  String copiedToClipboard(String title) {
    return '$title zkopírováno do schránky';
  }

  @override
  String get batteryLevel => 'Stav baterie';

  @override
  String get productUpdate => 'Aktualizace produktu';

  @override
  String get offline => 'Offline';

  @override
  String get available => 'K dispozici';

  @override
  String get unpairDeviceDialogTitle => 'Zrušit párování zařízení';

  @override
  String get unpairDeviceDialogMessage =>
      'Tím se zruší párování zařízení, aby se mohlo připojit k jinému telefonu. Budete muset přejít do Nastavení > Bluetooth a zapomenout zařízení pro dokončení procesu.';

  @override
  String get unpair => 'Zrušit párování';

  @override
  String get unpairAndForgetDevice => 'Zrušit párování a zapomenout zařízení';

  @override
  String get unknownDevice => 'Neznámé';

  @override
  String get unknown => 'Neznámé';

  @override
  String get productName => 'Název produktu';

  @override
  String get serialNumber => 'Sériové číslo';

  @override
  String get connected => 'Připojeno';

  @override
  String get privacyPolicyTitle => 'Zásady ochrany osobních údajů';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label zkopírováno';
  }

  @override
  String get noApiKeysYet => 'Zatím žádné API klíče. Vytvořte jeden pro integraci s vaší aplikací.';

  @override
  String get createKeyToGetStarted => 'Vytvořte klíč pro začátek';

  @override
  String get persona => 'Persona';

  @override
  String get configureYourAiPersona => 'Nakonfigurujte svou AI osobnost';

  @override
  String get configureSttProvider => 'Konfigurace poskytovatele STT';

  @override
  String get setWhenConversationsAutoEnd => 'Nastavte, kdy konverzace automaticky končí';

  @override
  String get importDataFromOtherSources => 'Import dat z jiných zdrojů';

  @override
  String get debugAndDiagnostics => 'Ladění a diagnostika';

  @override
  String get autoDeletesAfter3Days => 'Automatické smazání po 3 dnech';

  @override
  String get helpsDiagnoseIssues => 'Pomáhá diagnostikovat problémy';

  @override
  String get exportStartedMessage => 'Export zahájen. Může to trvat několik sekund...';

  @override
  String get exportConversationsToJson => 'Exportovat konverzace do souboru JSON';

  @override
  String get knowledgeGraphDeletedSuccess => 'Graf znalostí byl úspěšně smazán';

  @override
  String failedToDeleteGraph(String error) {
    return 'Nepodařilo se smazat graf: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'Vymazat všechny uzly a spojení';

  @override
  String get addToClaudeDesktopConfig => 'Přidat do claude_desktop_config.json';

  @override
  String get connectAiAssistantsToData => 'Připojte AI asistenty k vašim datům';

  @override
  String get useYourMcpApiKey => 'Použijte svůj MCP API klíč';

  @override
  String get realTimeTranscript => 'Přepis v reálném čase';

  @override
  String get experimental => 'Experimentální';

  @override
  String get transcriptionDiagnostics => 'Diagnostika přepisu';

  @override
  String get detailedDiagnosticMessages => 'Podrobné diagnostické zprávy';

  @override
  String get autoCreateSpeakers => 'Automaticky vytvářet řečníky';

  @override
  String get autoCreateWhenNameDetected => 'Automaticky vytvořit při detekci jména';

  @override
  String get followUpQuestions => 'Následné otázky';

  @override
  String get suggestQuestionsAfterConversations => 'Navrhovat otázky po konverzacích';

  @override
  String get goalTracker => 'Sledování cílů';

  @override
  String get trackPersonalGoalsOnHomepage => 'Sledujte své osobní cíle na domovské stránce';

  @override
  String get dailyReflection => 'Denní reflexe';

  @override
  String get get9PmReminderToReflect => 'Získejte připomínku v 21:00 k zamyšlení nad svým dnem';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'Popis úkolu nesmí být prázdný';

  @override
  String get saved => 'Uloženo';

  @override
  String get overdue => 'Po termínu';

  @override
  String get failedToUpdateDueDate => 'Nepodařilo se aktualizovat termín';

  @override
  String get markIncomplete => 'Označit jako nedokončené';

  @override
  String get editDueDate => 'Upravit termín';

  @override
  String get setDueDate => 'Nastavit termín';

  @override
  String get clearDueDate => 'Vymazat termín';

  @override
  String get failedToClearDueDate => 'Nepodařilo se vymazat termín';

  @override
  String get mondayAbbr => 'Po';

  @override
  String get tuesdayAbbr => 'Út';

  @override
  String get wednesdayAbbr => 'St';

  @override
  String get thursdayAbbr => 'Čt';

  @override
  String get fridayAbbr => 'Pá';

  @override
  String get saturdayAbbr => 'So';

  @override
  String get sundayAbbr => 'Ne';

  @override
  String get howDoesItWork => 'Jak to funguje?';

  @override
  String get sdCardSyncDescription => 'Synchronizace SD karty importuje vaše vzpomínky z SD karty do aplikace';

  @override
  String get checksForAudioFiles => 'Kontroluje zvukové soubory na SD kartě';

  @override
  String get omiSyncsAudioFiles => 'Omi poté synchronizuje zvukové soubory se serverem';

  @override
  String get serverProcessesAudio => 'Server zpracovává zvukové soubory a vytváří vzpomínky';

  @override
  String get youreAllSet => 'Vše je připraveno!';

  @override
  String get welcomeToOmiDescription =>
      'Vítejte v Omi! Váš AI společník je připraven vám pomoci s rozhovory, úkoly a mnoho dalšího.';

  @override
  String get startUsingOmi => 'Začít používat Omi';

  @override
  String get back => 'Zpět';

  @override
  String get keyboardShortcuts => 'Klávesové Zkratky';

  @override
  String get toggleControlBar => 'Přepnout ovládací panel';

  @override
  String get pressKeys => 'Stiskněte klávesy...';

  @override
  String get cmdRequired => '⌘ vyžadováno';

  @override
  String get invalidKey => 'Neplatná klávesa';

  @override
  String get space => 'Mezerník';

  @override
  String get search => 'Hledat';

  @override
  String get searchPlaceholder => 'Hledat...';

  @override
  String get untitledConversation => 'Konverzace bez názvu';

  @override
  String countRemaining(String count) {
    return '$count zbývá';
  }

  @override
  String get addGoal => 'Přidat cíl';

  @override
  String get editGoal => 'Upravit cíl';

  @override
  String get icon => 'Ikona';

  @override
  String get goalTitle => 'Název cíle';

  @override
  String get current => 'Aktuální';

  @override
  String get target => 'Cíl';

  @override
  String get saveGoal => 'Uložit';

  @override
  String get goals => 'Cíle';

  @override
  String get tapToAddGoal => 'Klepnutím přidejte cíl';

  @override
  String welcomeBack(String name) {
    return 'Vítejte zpět, $name';
  }

  @override
  String get yourConversations => 'Vaše konverzace';

  @override
  String get reviewAndManageConversations => 'Prohlížejte a spravujte své zachycené konverzace';

  @override
  String get startCapturingConversations => 'Začněte zachytávat konverzace pomocí zařízení Omi a zobrazí se zde.';

  @override
  String get useMobileAppToCapture => 'Použijte mobilní aplikaci k zachycení zvuku';

  @override
  String get conversationsProcessedAutomatically => 'Konverzace se zpracovávají automaticky';

  @override
  String get getInsightsInstantly => 'Získejte poznatky a souhrny okamžitě';

  @override
  String get showAll => 'Zobrazit vše →';

  @override
  String get noTasksForToday => 'Žádné úkoly pro dnešek.\\nZeptejte se Omi na další úkoly nebo je vytvořte ručně.';

  @override
  String get dailyScore => 'DENNÍ SKÓRE';

  @override
  String get dailyScoreDescription => 'Skóre, které vám pomůže\nlépe se soustředit na plnění.';

  @override
  String get searchResults => 'Výsledky vyhledávání';

  @override
  String get actionItems => 'Úkoly';

  @override
  String get tasksToday => 'Dnes';

  @override
  String get tasksTomorrow => 'Zítra';

  @override
  String get tasksNoDeadline => 'Bez termínu';

  @override
  String get tasksLater => 'Později';

  @override
  String get loadingTasks => 'Načítání úkolů...';

  @override
  String get tasks => 'Úkoly';

  @override
  String get swipeTasksToIndent => 'Přejeďte prstem pro odsazení úkolů, přetáhněte mezi kategoriemi';

  @override
  String get create => 'Vytvořit';

  @override
  String get noTasksYet => 'Zatím žádné úkoly';

  @override
  String get tasksFromConversationsWillAppear =>
      'Úkoly z vašich konverzací se zde zobrazí.\nKliknutím na Vytvořit přidáte jeden ručně.';

  @override
  String get monthJan => 'Led';

  @override
  String get monthFeb => 'Úno';

  @override
  String get monthMar => 'Bře';

  @override
  String get monthApr => 'Dub';

  @override
  String get monthMay => 'Kvě';

  @override
  String get monthJun => 'Čer';

  @override
  String get monthJul => 'Čvc';

  @override
  String get monthAug => 'Srp';

  @override
  String get monthSep => 'Zář';

  @override
  String get monthOct => 'Říj';

  @override
  String get monthNov => 'List';

  @override
  String get monthDec => 'Pro';

  @override
  String get timePM => 'odp.';

  @override
  String get timeAM => 'dop.';

  @override
  String get actionItemUpdatedSuccessfully => 'Úkol byl úspěšně aktualizován';

  @override
  String get actionItemCreatedSuccessfully => 'Úkol byl úspěšně vytvořen';

  @override
  String get actionItemDeletedSuccessfully => 'Úkol byl úspěšně smazán';

  @override
  String get deleteActionItem => 'Smazat úkol';

  @override
  String get deleteActionItemConfirmation => 'Opravdu chcete smazat tento úkol? Tuto akci nelze vrátit zpět.';

  @override
  String get enterActionItemDescription => 'Zadejte popis úkolu...';

  @override
  String get markAsCompleted => 'Označit jako dokončené';

  @override
  String get setDueDateAndTime => 'Nastavit termín a čas';

  @override
  String get reloadingApps => 'Znovu načítání aplikací...';

  @override
  String get loadingApps => 'Načítání aplikací...';

  @override
  String get browseInstallCreateApps => 'Procházejte, instalujte a vytvářejte aplikace';

  @override
  String get all => 'Vše';

  @override
  String get open => 'Otevřít';

  @override
  String get install => 'Instalovat';

  @override
  String get noAppsAvailable => 'Nejsou k dispozici žádné aplikace';

  @override
  String get unableToLoadApps => 'Nelze načíst aplikace';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'Zkuste upravit hledané výrazy nebo filtry';

  @override
  String get checkBackLaterForNewApps => 'Zkontrolujte později nové aplikace';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'Zkontrolujte prosím připojení k internetu a zkuste to znovu';

  @override
  String get createNewApp => 'Vytvořit novou aplikaci';

  @override
  String get buildSubmitCustomOmiApp => 'Vytvořte a odešlete svou vlastní Omi aplikaci';

  @override
  String get submittingYourApp => 'Odesílání vaší aplikace...';

  @override
  String get preparingFormForYou => 'Příprava formuláře pro vás...';

  @override
  String get appDetails => 'Podrobnosti aplikace';

  @override
  String get paymentDetails => 'Platební údaje';

  @override
  String get previewAndScreenshots => 'Náhled a snímky obrazovky';

  @override
  String get appCapabilities => 'Možnosti aplikace';

  @override
  String get aiPrompts => 'AI výzvy';

  @override
  String get chatPrompt => 'Výzva chatu';

  @override
  String get chatPromptPlaceholder =>
      'Jste úžasná aplikace, vaším úkolem je reagovat na dotazy uživatelů a dát jim dobrý pocit...';

  @override
  String get conversationPrompt => 'Výzva konverzace';

  @override
  String get conversationPromptPlaceholder => 'Jste úžasná aplikace, dostanete přepis a shrnutí konverzace...';

  @override
  String get notificationScopes => 'Rozsahy oznámení';

  @override
  String get appPrivacyAndTerms => 'Ochrana soukromí a podmínky aplikace';

  @override
  String get makeMyAppPublic => 'Zveřejnit mou aplikaci';

  @override
  String get submitAppTermsAgreement =>
      'Odesláním této aplikace souhlasím se Smluvními podmínkami a Zásadami ochrany osobních údajů Omi AI';

  @override
  String get submitApp => 'Odeslat aplikaci';

  @override
  String get needHelpGettingStarted => 'Potřebujete pomoc se začátkem?';

  @override
  String get clickHereForAppBuildingGuides => 'Klikněte zde pro návody k vytváření aplikací a dokumentaci';

  @override
  String get submitAppQuestion => 'Odeslat aplikaci?';

  @override
  String get submitAppPublicDescription =>
      'Vaše aplikace bude zkontrolována a zveřejněna. Můžete ji začít používat okamžitě, i během kontroly!';

  @override
  String get submitAppPrivateDescription =>
      'Vaše aplikace bude zkontrolována a zpřístupněna vám soukromě. Můžete ji začít používat okamžitě, i během kontroly!';

  @override
  String get startEarning => 'Začněte vydělávat! 💰';

  @override
  String get connectStripeOrPayPal => 'Připojte Stripe nebo PayPal, abyste mohli přijímat platby za svou aplikaci.';

  @override
  String get connectNow => 'Připojit nyní';

  @override
  String get installsCount => 'Instalace';

  @override
  String get uninstallApp => 'Odinstalovat aplikaci';

  @override
  String get subscribe => 'Přihlásit se k odběru';

  @override
  String get dataAccessNotice => 'Upozornění na přístup k datům';

  @override
  String get dataAccessWarning =>
      'Tato aplikace bude mít přístup k vašim datům. Omi AI nenese odpovědnost za to, jak jsou vaše data touto aplikací používána, upravována nebo mazána';

  @override
  String get installApp => 'Nainstalovat aplikaci';

  @override
  String get betaTesterNotice => 'Jste beta tester této aplikace. Ještě není veřejná. Stane se veřejnou po schválení.';

  @override
  String get appUnderReviewOwner =>
      'Vaše aplikace je v recenzi a viditelná pouze pro vás. Stane se veřejnou po schválení.';

  @override
  String get appRejectedNotice =>
      'Vaše aplikace byla zamítnuta. Aktualizujte prosím detaily aplikace a znovu ji odešlete k recenzi.';

  @override
  String get setupSteps => 'Kroky nastavení';

  @override
  String get setupInstructions => 'Pokyny k nastavení';

  @override
  String get integrationInstructions => 'Pokyny k integraci';

  @override
  String get preview => 'Náhled';

  @override
  String get aboutTheApp => 'O aplikaci';

  @override
  String get aboutThePersona => 'O personě';

  @override
  String get chatPersonality => 'Osobnost chatu';

  @override
  String get ratingsAndReviews => 'Hodnocení a recenze';

  @override
  String get noRatings => 'žádná hodnocení';

  @override
  String ratingsCount(String count) {
    return '$count+ hodnocení';
  }

  @override
  String get errorActivatingApp => 'Chyba při aktivaci aplikace';

  @override
  String get integrationSetupRequired =>
      'Pokud se jedná o integrační aplikaci, ujistěte se, že je nastavení dokončeno.';

  @override
  String get installed => 'Nainstalováno';

  @override
  String get appIdLabel => 'ID aplikace';

  @override
  String get appNameLabel => 'Název aplikace';

  @override
  String get appNamePlaceholder => 'Má úžasná aplikace';

  @override
  String get pleaseEnterAppName => 'Zadejte prosím název aplikace';

  @override
  String get categoryLabel => 'Kategorie';

  @override
  String get selectCategory => 'Vyberte kategorii';

  @override
  String get descriptionLabel => 'Popis';

  @override
  String get appDescriptionPlaceholder =>
      'Má úžasná aplikace je skvělá aplikace, která dělá úžasné věci. Je to nejlepší aplikace!';

  @override
  String get pleaseProvideValidDescription => 'Zadejte prosím platný popis';

  @override
  String get appPricingLabel => 'Cena aplikace';

  @override
  String get noneSelected => 'Nic nevybráno';

  @override
  String get appIdCopiedToClipboard => 'ID aplikace zkopírováno do schránky';

  @override
  String get appCategoryModalTitle => 'Kategorie aplikace';

  @override
  String get pricingFree => 'Zdarma';

  @override
  String get pricingPaid => 'Placené';

  @override
  String get loadingCapabilities => 'Načítání funkcí...';

  @override
  String get filterInstalled => 'Nainstalováno';

  @override
  String get filterMyApps => 'Moje aplikace';

  @override
  String get clearSelection => 'Vymazat výběr';

  @override
  String get filterCategory => 'Kategorie';

  @override
  String get rating4PlusStars => '4+ hvězdiček';

  @override
  String get rating3PlusStars => '3+ hvězdiček';

  @override
  String get rating2PlusStars => '2+ hvězdiček';

  @override
  String get rating1PlusStars => '1+ hvězdička';

  @override
  String get filterRating => 'Hodnocení';

  @override
  String get filterCapabilities => 'Funkce';

  @override
  String get noNotificationScopesAvailable => 'Nejsou k dispozici žádné rozsahy oznámení';

  @override
  String get popularApps => 'Oblíbené aplikace';

  @override
  String get pleaseProvidePrompt => 'Zadejte prosím výzvu';

  @override
  String chatWithAppName(String appName) {
    return 'Chat s $appName';
  }

  @override
  String get defaultAiAssistant => 'Výchozí AI asistent';

  @override
  String get readyToChat => '✨ Připraven k chatu!';

  @override
  String get connectionNeeded => '🌐 Vyžadováno připojení';

  @override
  String get startConversation => 'Začněte konverzaci a nechte kouzlo začít';

  @override
  String get checkInternetConnection => 'Zkontrolujte prosím své připojení k internetu';

  @override
  String get wasThisHelpful => 'Bylo to užitečné?';

  @override
  String get thankYouForFeedback => 'Děkujeme za zpětnou vazbu!';

  @override
  String get maxFilesUploadError => 'Můžete nahrát pouze 4 soubory najednou';

  @override
  String get attachedFiles => '📎 Připojené soubory';

  @override
  String get takePhoto => 'Vyfotit';

  @override
  String get captureWithCamera => 'Zachytit kamerou';

  @override
  String get selectImages => 'Vybrat obrázky';

  @override
  String get chooseFromGallery => 'Vybrat z galerie';

  @override
  String get selectFile => 'Vybrat soubor';

  @override
  String get chooseAnyFileType => 'Vybrat jakýkoli typ souboru';

  @override
  String get cannotReportOwnMessages => 'Nemůžete nahlásit vlastní zprávy';

  @override
  String get messageReportedSuccessfully => '✅ Zpráva úspěšně nahlášena';

  @override
  String get confirmReportMessage => 'Opravdu chcete nahlásit tuto zprávu?';

  @override
  String get selectChatAssistant => 'Vybrat chatovacího asistenta';

  @override
  String get enableMoreApps => 'Povolit více aplikací';

  @override
  String get chatCleared => 'Chat vymazán';

  @override
  String get clearChatTitle => 'Vymazat chat?';

  @override
  String get confirmClearChat => 'Opravdu chcete vymazat chat? Tuto akci nelze vrátit zpět.';

  @override
  String get copy => 'Kopírovat';

  @override
  String get share => 'Sdílet';

  @override
  String get report => 'Nahlásit';

  @override
  String get microphonePermissionRequired => 'Pro hlasový záznam je vyžadováno oprávnění k mikrofonu.';

  @override
  String get microphonePermissionDenied =>
      'Oprávnění k mikrofonu bylo zamítnuto. Udělte prosím oprávnění v Předvolby systému > Soukromí a zabezpečení > Mikrofon.';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'Nepodařilo se zkontrolovat oprávnění k mikrofonu: $error';
  }

  @override
  String get failedToTranscribeAudio => 'Nepodařilo se přepsat zvuk';

  @override
  String get transcribing => 'Přepisování...';

  @override
  String get transcriptionFailed => 'Přepis se nezdařil';

  @override
  String get discardedConversation => 'Zahozená konverzace';

  @override
  String get at => 'v';

  @override
  String get from => 'od';

  @override
  String get copied => 'Zkopírováno!';

  @override
  String get copyLink => 'Kopírovat odkaz';

  @override
  String get hideTranscript => 'Skrýt přepis';

  @override
  String get viewTranscript => 'Zobrazit přepis';

  @override
  String get conversationDetails => 'Detaily konverzace';

  @override
  String get transcript => 'Přepis';

  @override
  String segmentsCount(int count) {
    return '$count segmentů';
  }

  @override
  String get noTranscriptAvailable => 'Přepis není k dispozici';

  @override
  String get noTranscriptMessage => 'Tato konverzace nemá přepis.';

  @override
  String get conversationUrlCouldNotBeGenerated => 'URL konverzace nelze vygenerovat.';

  @override
  String get failedToGenerateConversationLink => 'Nepodařilo se vygenerovat odkaz na konverzaci';

  @override
  String get failedToGenerateShareLink => 'Nepodařilo se vygenerovat odkaz ke sdílení';

  @override
  String get reloadingConversations => 'Načítání konverzací...';

  @override
  String get user => 'Uživatel';

  @override
  String get starred => 'S hvězdičkou';

  @override
  String get date => 'Datum';

  @override
  String get noResultsFound => 'Nenalezeny žádné výsledky';

  @override
  String get tryAdjustingSearchTerms => 'Zkuste upravit vyhledávací výrazy';

  @override
  String get starConversationsToFindQuickly => 'Označte konverzace hvězdičkou, abyste je zde rychle našli';

  @override
  String noConversationsOnDate(String date) {
    return 'Žádné konverzace dne $date';
  }

  @override
  String get trySelectingDifferentDate => 'Zkuste vybrat jiné datum';

  @override
  String get conversations => 'Konverzace';

  @override
  String get chat => 'Chat';

  @override
  String get actions => 'Akce';

  @override
  String get syncAvailable => 'Synchronizace k dispozici';

  @override
  String get referAFriend => 'Doporučit příteli';

  @override
  String get help => 'Nápověda';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'Upgrade na Pro';

  @override
  String get getOmiDevice => 'Získat zařízení Omi';

  @override
  String get wearableAiCompanion => 'Nositelný AI společník';

  @override
  String get loadingMemories => 'Načítání vzpomínek...';

  @override
  String get allMemories => 'Všechny vzpomínky';

  @override
  String get aboutYou => 'O tobě';

  @override
  String get manual => 'Ruční';

  @override
  String get loadingYourMemories => 'Načítání vašich vzpomínek...';

  @override
  String get createYourFirstMemory => 'Vytvořte svou první vzpomínku a začněte';

  @override
  String get tryAdjustingFilter => 'Zkuste upravit vyhledávání nebo filtr';

  @override
  String get whatWouldYouLikeToRemember => 'Co si chcete zapamatovat?';

  @override
  String get category => 'Kategorie';

  @override
  String get public => 'Veřejné';

  @override
  String get failedToSaveCheckConnection => 'Uložení se nezdařilo. Zkontrolujte připojení.';

  @override
  String get createMemory => 'Vytvořit vzpomínku';

  @override
  String get deleteMemoryConfirmation => 'Opravdu chcete smazat tuto vzpomínku? Tuto akci nelze vrátit zpět.';

  @override
  String get makePrivate => 'Nastavit jako soukromé';

  @override
  String get organizeAndControlMemories => 'Organizujte a ovládejte své vzpomínky';

  @override
  String get total => 'Celkem';

  @override
  String get makeAllMemoriesPrivate => 'Nastavit všechny vzpomínky jako soukromé';

  @override
  String get setAllMemoriesToPrivate => 'Nastavit všechny vzpomínky na soukromou viditelnost';

  @override
  String get makeAllMemoriesPublic => 'Nastavit všechny vzpomínky jako veřejné';

  @override
  String get setAllMemoriesToPublic => 'Nastavit všechny vzpomínky na veřejnou viditelnost';

  @override
  String get permanentlyRemoveAllMemories => 'Trvale odstranit všechny vzpomínky z Omi';

  @override
  String get allMemoriesAreNowPrivate => 'Všechny vzpomínky jsou nyní soukromé';

  @override
  String get allMemoriesAreNowPublic => 'Všechny vzpomínky jsou nyní veřejné';

  @override
  String get clearOmisMemory => 'Vymazat paměť Omi';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Opravdu chcete vymazat paměť Omi? Tuto akci nelze vrátit zpět a trvale odstraní všech $count vzpomínek.';
  }

  @override
  String get omisMemoryCleared => 'Paměť Omi o vás byla vymazána';

  @override
  String get welcomeToOmi => 'Vítejte v Omi';

  @override
  String get continueWithApple => 'Pokračovat s Apple';

  @override
  String get continueWithGoogle => 'Pokračovat s Google';

  @override
  String get byContinuingYouAgree => 'Pokračováním souhlasíte s našimi ';

  @override
  String get termsOfService => 'Podmínkami služby';

  @override
  String get and => ' a ';

  @override
  String get dataAndPrivacy => 'Data a soukromí';

  @override
  String get secureAuthViaAppleId => 'Bezpečné ověření přes Apple ID';

  @override
  String get secureAuthViaGoogleAccount => 'Bezpečné ověření přes účet Google';

  @override
  String get whatWeCollect => 'Co sbíráme';

  @override
  String get dataCollectionMessage =>
      'Pokračováním budou vaše konverzace, nahrávky a osobní údaje bezpečně uloženy na našich serverech, aby poskytly přehledy založené na AI a umožnily všechny funkce aplikace.';

  @override
  String get dataProtection => 'Ochrana dat';

  @override
  String get yourDataIsProtected => 'Vaše data jsou chráněna a řídí se našimi ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'Prosím vyberte svůj primární jazyk';

  @override
  String get chooseYourLanguage => 'Vyberte svůj jazyk';

  @override
  String get selectPreferredLanguageForBestExperience => 'Vyberte si preferovaný jazyk pro nejlepší Omi zážitek';

  @override
  String get searchLanguages => 'Hledat jazyky...';

  @override
  String get selectALanguage => 'Vyberte jazyk';

  @override
  String get tryDifferentSearchTerm => 'Zkuste jiný výraz pro vyhledávání';

  @override
  String get pleaseEnterYourName => 'Prosím zadejte své jméno';

  @override
  String get nameMustBeAtLeast2Characters => 'Jméno musí mít alespoň 2 znaky';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'Řekněte nám, jak byste chtěli být oslovováni. To pomáhá personalizovat váš Omi zážitek.';

  @override
  String charactersCount(int count) {
    return '$count znaků';
  }

  @override
  String get enableFeaturesForBestExperience => 'Povolte funkce pro nejlepší Omi zážitek na vašem zařízení.';

  @override
  String get microphoneAccess => 'Přístup k mikrofonu';

  @override
  String get recordAudioConversations => 'Nahrávat audio konverzace';

  @override
  String get microphoneAccessDescription =>
      'Omi potřebuje přístup k mikrofonu pro nahrávání vašich konverzací a poskytování přepisů.';

  @override
  String get screenRecording => 'Záznam obrazovky';

  @override
  String get captureSystemAudioFromMeetings => 'Zachytit systémový zvuk ze schůzek';

  @override
  String get screenRecordingDescription =>
      'Omi potřebuje oprávnění k záznamu obrazovky pro zachycení systémového zvuku z vašich schůzek v prohlížeči.';

  @override
  String get accessibility => 'Přístupnost';

  @override
  String get detectBrowserBasedMeetings => 'Detekovat schůzky v prohlížeči';

  @override
  String get accessibilityDescription =>
      'Omi potřebuje oprávnění k přístupnosti pro detekci, kdy se připojujete ke schůzkám Zoom, Meet nebo Teams ve vašem prohlížeči.';

  @override
  String get pleaseWait => 'Prosím čekejte...';

  @override
  String get joinTheCommunity => 'Připojte se ke komunitě!';

  @override
  String get loadingProfile => 'Načítání profilu...';

  @override
  String get profileSettings => 'Nastavení profilu';

  @override
  String get noEmailSet => 'Email není nastaven';

  @override
  String get userIdCopiedToClipboard => 'ID uživatele zkopírováno';

  @override
  String get yourInformation => 'Vaše Informace';

  @override
  String get setYourName => 'Nastavit své jméno';

  @override
  String get changeYourName => 'Změnit své jméno';

  @override
  String get manageYourOmiPersona => 'Spravovat svou Omi personu';

  @override
  String get voiceAndPeople => 'Hlas a Lidé';

  @override
  String get teachOmiYourVoice => 'Naučit Omi svůj hlas';

  @override
  String get tellOmiWhoSaidIt => 'Řekněte Omi, kdo to řekl 🗣️';

  @override
  String get payment => 'Platba';

  @override
  String get addOrChangeYourPaymentMethod => 'Přidat nebo změnit platební metodu';

  @override
  String get preferences => 'Předvolby';

  @override
  String get helpImproveOmiBySharing => 'Pomozte vylepšit Omi sdílením anonymizovaných analytických dat';

  @override
  String get deleteAccount => 'Smazat Účet';

  @override
  String get deleteYourAccountAndAllData => 'Smazat účet a všechna data';

  @override
  String get clearLogs => 'Vymazat protokoly';

  @override
  String get debugLogsCleared => 'Protokoly ladění vymazány';

  @override
  String get exportConversations => 'Exportovat konverzace';

  @override
  String get exportAllConversationsToJson => 'Exportujte všechny své konverzace do souboru JSON.';

  @override
  String get conversationsExportStarted => 'Export konverzací zahájen. Může to trvat několik sekund, počkejte prosím.';

  @override
  String get mcpDescription =>
      'Pro připojení Omi k dalším aplikacím pro čtení, vyhledávání a správu vašich vzpomínek a konverzací. Začněte vytvořením klíče.';

  @override
  String get apiKeys => 'API klíče';

  @override
  String errorLabel(String error) {
    return 'Chyba: $error';
  }

  @override
  String get noApiKeysFound => 'Nebyly nalezeny žádné API klíče. Začněte vytvořením jednoho.';

  @override
  String get advancedSettings => 'Pokročilé nastavení';

  @override
  String get triggersWhenNewConversationCreated => 'Spouští se při vytvoření nové konverzace.';

  @override
  String get triggersWhenNewTranscriptReceived => 'Spouští se při příjmu nového přepisu.';

  @override
  String get realtimeAudioBytes => 'Zvukové bajty v reálném čase';

  @override
  String get triggersWhenAudioBytesReceived => 'Spouští se při příjmu zvukových bajtů.';

  @override
  String get everyXSeconds => 'Každých x sekund';

  @override
  String get triggersWhenDaySummaryGenerated => 'Spouští se při vygenerování denního souhrnu.';

  @override
  String get tryLatestExperimentalFeatures => 'Vyzkoušejte nejnovější experimentální funkce od týmu Omi.';

  @override
  String get transcriptionServiceDiagnosticStatus => 'Diagnostický stav služby přepisu';

  @override
  String get enableDetailedDiagnosticMessages => 'Povolit podrobné diagnostické zprávy ze služby přepisu';

  @override
  String get autoCreateAndTagNewSpeakers => 'Automaticky vytvářet a označovat nové mluvčí';

  @override
  String get automaticallyCreateNewPerson => 'Automaticky vytvořit novou osobu, když je v přepisu detekováno jméno.';

  @override
  String get pilotFeatures => 'Pilotní funkce';

  @override
  String get pilotFeaturesDescription => 'Tyto funkce jsou testy a není zaručena podpora.';

  @override
  String get suggestFollowUpQuestion => 'Navrhnout následnou otázku';

  @override
  String get saveSettings => 'Uložit Nastavení';

  @override
  String get syncingDeveloperSettings => 'Synchronizace vývojářského nastavení...';

  @override
  String get summary => 'Souhrn';

  @override
  String get auto => 'Automaticky';

  @override
  String get noSummaryForApp => 'Pro tuto aplikaci není k dispozici shrnutí. Zkuste jinou aplikaci pro lepší výsledky.';

  @override
  String get tryAnotherApp => 'Zkusit jinou aplikaci';

  @override
  String generatedBy(String appName) {
    return 'Vygenerováno aplikací $appName';
  }

  @override
  String get overview => 'Přehled';

  @override
  String get otherAppResults => 'Výsledky z jiných aplikací';

  @override
  String get unknownApp => 'Neznámá aplikace';

  @override
  String get noSummaryAvailable => 'Není k dispozici žádný souhrn';

  @override
  String get conversationNoSummaryYet => 'Tato konverzace ještě nemá souhrn.';

  @override
  String get chooseSummarizationApp => 'Vybrat aplikaci pro souhrn';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return 'Aplikace $appName nastavena jako výchozí aplikace pro souhrn';
  }

  @override
  String get letOmiChooseAutomatically => 'Nechte Omi automaticky vybrat nejlepší aplikaci';

  @override
  String get deleteConversationConfirmation => 'Opravdu chcete smazat tuto konverzaci? Tuto akci nelze vrátit zpět.';

  @override
  String get conversationDeleted => 'Konverzace smazána';

  @override
  String get generatingLink => 'Generování odkazu...';

  @override
  String get editConversation => 'Upravit konverzaci';

  @override
  String get conversationLinkCopiedToClipboard => 'Odkaz na konverzaci zkopírován do schránky';

  @override
  String get conversationTranscriptCopiedToClipboard => 'Přepis konverzace zkopírován do schránky';

  @override
  String get editConversationDialogTitle => 'Upravit konverzaci';

  @override
  String get changeTheConversationTitle => 'Změnit název konverzace';

  @override
  String get conversationTitle => 'Název konverzace';

  @override
  String get enterConversationTitle => 'Zadejte název konverzace...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'Název konverzace úspěšně aktualizován';

  @override
  String get failedToUpdateConversationTitle => 'Nepodařilo se aktualizovat název konverzace';

  @override
  String get errorUpdatingConversationTitle => 'Chyba při aktualizaci názvu konverzace';

  @override
  String get settingUp => 'Nastavování...';

  @override
  String get startYourFirstRecording => 'Zahajte svůj první záznam';

  @override
  String get preparingSystemAudioCapture => 'Příprava záznamu systémového zvuku';

  @override
  String get clickTheButtonToCaptureAudio =>
      'Klikněte na tlačítko pro záznam zvuku pro živé přepisy, poznatky AI a automatické ukládání.';

  @override
  String get reconnecting => 'Opětovné připojování...';

  @override
  String get recordingPaused => 'Záznam pozastaven';

  @override
  String get recordingActive => 'Záznam aktivní';

  @override
  String get startRecording => 'Spustit záznam';

  @override
  String resumingInCountdown(String countdown) {
    return 'Pokračování za ${countdown}s...';
  }

  @override
  String get tapPlayToResume => 'Klepněte na přehrát pro pokračování';

  @override
  String get listeningForAudio => 'Poslouchání zvuku...';

  @override
  String get preparingAudioCapture => 'Příprava záznamu zvuku';

  @override
  String get clickToBeginRecording => 'Klikněte pro zahájení záznamu';

  @override
  String get translated => 'přeloženo';

  @override
  String get liveTranscript => 'Živý přepis';

  @override
  String segmentsSingular(String count) {
    return '$count segment';
  }

  @override
  String segmentsPlural(String count) {
    return '$count segmentů';
  }

  @override
  String get startRecordingToSeeTranscript => 'Spusťte záznam pro zobrazení živého přepisu';

  @override
  String get paused => 'Pozastaveno';

  @override
  String get initializing => 'Inicializace...';

  @override
  String get recording => 'Nahrávání';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'Mikrofon změněn. Pokračování za ${countdown}s';
  }

  @override
  String get clickPlayToResumeOrStop => 'Klikněte na přehrát pro pokračování nebo zastavit pro dokončení';

  @override
  String get settingUpSystemAudioCapture => 'Nastavení záznamu systémového zvuku';

  @override
  String get capturingAudioAndGeneratingTranscript => 'Záznam zvuku a generování přepisu';

  @override
  String get clickToBeginRecordingSystemAudio => 'Klikněte pro zahájení záznamu systémového zvuku';

  @override
  String get you => 'Vy';

  @override
  String speakerWithId(String speakerId) {
    return 'Mluvčí $speakerId';
  }

  @override
  String get translatedByOmi => 'přeloženo pomocí omi';

  @override
  String get backToConversations => 'Zpět na Konverzace';

  @override
  String get systemAudio => 'Systém';

  @override
  String get mic => 'Mikrofon';

  @override
  String audioInputSetTo(String deviceName) {
    return 'Vstup zvuku nastaven na $deviceName';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'Chyba při přepínání zvukového zařízení: $error';
  }

  @override
  String get selectAudioInput => 'Vyberte vstup zvuku';

  @override
  String get loadingDevices => 'Načítání zařízení...';

  @override
  String get settingsHeader => 'NASTAVENÍ';

  @override
  String get plansAndBilling => 'Plány a Fakturace';

  @override
  String get calendarIntegration => 'Integrace Kalendáře';

  @override
  String get dailySummary => 'Denní shrnutí';

  @override
  String get developer => 'Vývojář';

  @override
  String get about => 'O aplikaci';

  @override
  String get selectTime => 'Vybrat čas';

  @override
  String get accountGroup => 'Účet';

  @override
  String get signOutQuestion => 'Odhlásit se?';

  @override
  String get signOutConfirmation => 'Opravdu se chcete odhlásit?';

  @override
  String get customVocabularyHeader => 'VLASTNÍ SLOVNÍK';

  @override
  String get addWordsDescription => 'Přidejte slova, která má Omi rozpoznávat během přepisu.';

  @override
  String get enterWordsHint => 'Zadejte slova (oddělená čárkami)';

  @override
  String get dailySummaryHeader => 'DENNÍ SOUHRN';

  @override
  String get dailySummaryTitle => 'Denní Souhrn';

  @override
  String get dailySummaryDescription => 'Získejte personalizované shrnutí konverzací dne jako oznámení.';

  @override
  String get deliveryTime => 'Čas doručení';

  @override
  String get deliveryTimeDescription => 'Kdy přijímat denní souhrn';

  @override
  String get subscription => 'Předplatné';

  @override
  String get viewPlansAndUsage => 'Zobrazit Plány a Využití';

  @override
  String get viewPlansDescription => 'Spravujte své předplatné a prohlédněte si statistiky využití';

  @override
  String get addOrChangePaymentMethod => 'Přidejte nebo změňte svou platební metodu';

  @override
  String get displayOptions => 'Možnosti zobrazení';

  @override
  String get showMeetingsInMenuBar => 'Zobrazit schůzky v řádku nabídek';

  @override
  String get displayUpcomingMeetingsDescription => 'Zobrazit nadcházející schůzky v řádku nabídek';

  @override
  String get showEventsWithoutParticipants => 'Zobrazit události bez účastníků';

  @override
  String get includePersonalEventsDescription => 'Zahrnout osobní události bez účastníků';

  @override
  String get upcomingMeetings => 'Nadcházející schůzky';

  @override
  String get checkingNext7Days => 'Kontrola následujících 7 dní';

  @override
  String get shortcuts => 'Klávesové zkratky';

  @override
  String get shortcutChangeInstruction => 'Klikněte na zkratku a změňte ji. Stisknutím Escape zrušíte.';

  @override
  String get configurePersonaDescription => 'Nakonfigurujte svou AI personu';

  @override
  String get configureSTTProvider => 'Nakonfigurovat poskytovatele STT';

  @override
  String get setConversationEndDescription => 'Nastavte, kdy konverzace automaticky končí';

  @override
  String get importDataDescription => 'Importovat data z jiných zdrojů';

  @override
  String get exportConversationsDescription => 'Exportovat konverzace do JSON';

  @override
  String get exportingConversations => 'Exportování konverzací...';

  @override
  String get clearNodesDescription => 'Vymazat všechny uzly a připojení';

  @override
  String get deleteKnowledgeGraphQuestion => 'Smazat graf znalostí?';

  @override
  String get deleteKnowledgeGraphWarning =>
      'Tím se smažou všechna odvozená data grafu znalostí. Vaše původní vzpomínky zůstanou v bezpečí.';

  @override
  String get connectOmiWithAI => 'Připojte Omi k AI asistentům';

  @override
  String get noAPIKeys => 'Žádné klíče API. Vytvořte jeden, abyste mohli začít.';

  @override
  String get autoCreateWhenDetected => 'Automaticky vytvořit při detekci jména';

  @override
  String get trackPersonalGoals => 'Sledovat osobní cíle na domovské stránce';

  @override
  String get dailyReflectionDescription =>
      'Získejte připomínku ve 21:00, abyste se zamysleli nad svým dnem a zachytili své myšlenky.';

  @override
  String get endpointURL => 'URL koncového bodu';

  @override
  String get links => 'Odkazy';

  @override
  String get discordMemberCount => 'Více než 8000 členů na Discordu';

  @override
  String get userInformation => 'Informace o uživateli';

  @override
  String get capabilities => 'Schopnosti';

  @override
  String get previewScreenshots => 'Náhled snímků obrazovky';

  @override
  String get holdOnPreparingForm => 'Počkejte, připravujeme pro vás formulář';

  @override
  String get bySubmittingYouAgreeToOmi => 'Odesláním souhlasíte s Omi ';

  @override
  String get termsAndPrivacyPolicy => 'Podmínky a Zásady ochrany osobních údajů';

  @override
  String get helpsDiagnoseIssuesAutoDeletes => 'Pomáhá diagnostikovat problémy. Automaticky maže po 3 dnech.';

  @override
  String get manageYourApp => 'Správa vaší aplikace';

  @override
  String get updatingYourApp => 'Aktualizace vaší aplikace';

  @override
  String get fetchingYourAppDetails => 'Načítání podrobností vaší aplikace';

  @override
  String get updateAppQuestion => 'Aktualizovat aplikaci?';

  @override
  String get updateAppConfirmation =>
      'Opravdu chcete aktualizovat svou aplikaci? Změny se projeví po kontrole naším týmem.';

  @override
  String get updateApp => 'Aktualizovat aplikaci';

  @override
  String get createAndSubmitNewApp => 'Vytvořte a odešlete novou aplikaci';

  @override
  String appsCount(String count) {
    return 'Aplikace ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'Soukromé aplikace ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'Veřejné aplikace ($count)';
  }

  @override
  String get newVersionAvailable => 'K dispozici je nová verze  🎉';

  @override
  String get no => 'Ne';

  @override
  String get subscriptionCancelledSuccessfully =>
      'Předplatné bylo úspěšně zrušeno. Zůstane aktivní do konce aktuálního fakturačního období.';

  @override
  String get failedToCancelSubscription => 'Zrušení předplatného se nezdařilo. Zkuste to prosím znovu.';

  @override
  String get invalidPaymentUrl => 'Neplatná adresa URL platby';

  @override
  String get permissionsAndTriggers => 'Oprávnění a spouštěče';

  @override
  String get chatFeatures => 'Funkce chatu';

  @override
  String get uninstall => 'Odinstalovat';

  @override
  String get installs => 'INSTALACE';

  @override
  String get priceLabel => 'CENA';

  @override
  String get updatedLabel => 'AKTUALIZOVÁNO';

  @override
  String get createdLabel => 'VYTVOŘENO';

  @override
  String get featuredLabel => 'DOPORUČENÉ';

  @override
  String get cancelSubscriptionQuestion => 'Zrušit předplatné?';

  @override
  String get cancelSubscriptionConfirmation =>
      'Opravdu chcete zrušit předplatné? Budete mít přístup do konce aktuálního fakturačního období.';

  @override
  String get cancelSubscriptionButton => 'Zrušit předplatné';

  @override
  String get cancelling => 'Rušení...';

  @override
  String get betaTesterMessage => 'Jste beta tester této aplikace. Zatím není veřejná. Bude veřejná po schválení.';

  @override
  String get appUnderReviewMessage =>
      'Vaše aplikace je v procesu kontroly a viditelná pouze pro vás. Bude veřejná po schválení.';

  @override
  String get appRejectedMessage => 'Vaše aplikace byla zamítnuta. Aktualizujte údaje a znovu odešlete ke kontrole.';

  @override
  String get invalidIntegrationUrl => 'Neplatná URL integrace';

  @override
  String get tapToComplete => 'Klepněte pro dokončení';

  @override
  String get invalidSetupInstructionsUrl => 'Neplatná URL pokynů k nastavení';

  @override
  String get pushToTalk => 'Stiskni a mluv';

  @override
  String get summaryPrompt => 'Výzva pro shrnutí';

  @override
  String get pleaseSelectARating => 'Vyberte prosím hodnocení';

  @override
  String get reviewAddedSuccessfully => 'Recenze úspěšně přidána 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'Recenze úspěšně aktualizována 🚀';

  @override
  String get failedToSubmitReview => 'Odeslání recenze se nezdařilo. Zkuste to prosím znovu.';

  @override
  String get addYourReview => 'Přidejte svou recenzi';

  @override
  String get editYourReview => 'Upravte svou recenzi';

  @override
  String get writeAReviewOptional => 'Napište recenzi (volitelné)';

  @override
  String get submitReview => 'Odeslat recenzi';

  @override
  String get updateReview => 'Aktualizovat recenzi';

  @override
  String get yourReview => 'Vaše recenze';

  @override
  String get anonymousUser => 'Anonymní uživatel';

  @override
  String get issueActivatingApp => 'Při aktivaci této aplikace došlo k problému. Zkuste to prosím znovu.';

  @override
  String get dataAccessNoticeDescription =>
      'Tato aplikace bude mít přístup k vašim datům. Omi AI nenese odpovědnost za to, jak jsou vaše data používána třetími stranami.';

  @override
  String get copyUrl => 'Kopírovat URL';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => 'Po';

  @override
  String get weekdayTue => 'Út';

  @override
  String get weekdayWed => 'St';

  @override
  String get weekdayThu => 'Čt';

  @override
  String get weekdayFri => 'Pá';

  @override
  String get weekdaySat => 'So';

  @override
  String get weekdaySun => 'Ne';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return 'Integrace s $serviceName již brzy';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'Již exportováno do $platform';
  }

  @override
  String get anotherPlatform => 'jinou platformu';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'Prosím ověřte se pomocí $serviceName v Nastavení > Integrace úkolů';
  }

  @override
  String addingToService(String serviceName) {
    return 'Přidávání do $serviceName...';
  }

  @override
  String addedToService(String serviceName) {
    return 'Přidáno do $serviceName';
  }

  @override
  String failedToAddToService(String serviceName) {
    return 'Nepodařilo se přidat do $serviceName';
  }

  @override
  String get permissionDeniedForAppleReminders => 'Oprávnění pro Apple Reminders bylo zamítnuto';

  @override
  String failedToCreateApiKey(String error) {
    return 'Nepodařilo se vytvořit API klíč poskytovatele: $error';
  }

  @override
  String get createAKey => 'Vytvořit klíč';

  @override
  String get apiKeyRevokedSuccessfully => 'API klíč byl úspěšně odvolán';

  @override
  String failedToRevokeApiKey(String error) {
    return 'Nepodařilo se odvolat API klíč: $error';
  }

  @override
  String get omiApiKeys => 'Omi API klíče';

  @override
  String get apiKeysDescription =>
      'API klíče se používají pro ověření, když vaše aplikace komunikuje se serverem OMI. Umožňují vaší aplikaci vytvářet vzpomínky a bezpečně přistupovat k dalším službám OMI.';

  @override
  String get aboutOmiApiKeys => 'O Omi API klíčích';

  @override
  String get yourNewKey => 'Váš nový klíč:';

  @override
  String get copyToClipboard => 'Kopírovat do schránky';

  @override
  String get pleaseCopyKeyNow => 'Prosím zkopírujte si ho nyní a zapište si ho na bezpečné místo. ';

  @override
  String get willNotSeeAgain => 'Nebudete jej moci znovu zobrazit.';

  @override
  String get revokeKey => 'Odvolat klíč';

  @override
  String get revokeApiKeyQuestion => 'Odvolat API klíč?';

  @override
  String get revokeApiKeyWarning =>
      'Tuto akci nelze vrátit zpět. Všechny aplikace používající tento klíč již nebudou mít přístup k API.';

  @override
  String get revoke => 'Odvolat';

  @override
  String get whatWouldYouLikeToCreate => 'Co byste chtěli vytvořit?';

  @override
  String get createAnApp => 'Vytvořit aplikaci';

  @override
  String get createAndShareYourApp => 'Vytvořte a sdílejte svou aplikaci';

  @override
  String get createMyClone => 'Vytvořit můj klon';

  @override
  String get createYourDigitalClone => 'Vytvořte svůj digitální klon';

  @override
  String get itemApp => 'Aplikace';

  @override
  String get itemPersona => 'Persona';

  @override
  String keepItemPublic(String item) {
    return 'Ponechat $item veřejnou';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return 'Zveřejnit $item?';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return 'Zneveřejnit $item?';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'Pokud zveřejníte $item, může ji používat kdokoli';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'Pokud nyní zneveřejníte $item, přestane fungovat pro všechny a bude viditelná pouze pro vás';
  }

  @override
  String get manageApp => 'Spravovat aplikaci';

  @override
  String get updatePersonaDetails => 'Aktualizovat detaily persony';

  @override
  String deleteItemTitle(String item) {
    return 'Smazat $item';
  }

  @override
  String deleteItemQuestion(String item) {
    return 'Smazat $item?';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'Opravdu chcete smazat tuto $item? Tuto akci nelze vrátit zpět.';
  }

  @override
  String get revokeKeyQuestion => 'Odvolat klíč?';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'Opravdu chcete odvolat klíč \"$keyName\"? Tuto akci nelze vrátit zpět.';
  }

  @override
  String get createNewKey => 'Vytvořit nový klíč';

  @override
  String get keyNameHint => 'např. Claude Desktop';

  @override
  String get pleaseEnterAName => 'Prosím zadejte název.';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'Nepodařilo se vytvořit klíč: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'Nepodařilo se vytvořit klíč. Zkuste to prosím znovu.';

  @override
  String get keyCreated => 'Klíč vytvořen';

  @override
  String get keyCreatedMessage => 'Váš nový klíč byl vytvořen. Prosím zkopírujte si ho nyní. Již ho neuvidíte.';

  @override
  String get keyWord => 'Klíč';

  @override
  String get externalAppAccess => 'Přístup externích aplikací';

  @override
  String get externalAppAccessDescription =>
      'Následující nainstalované aplikace mají externí integrace a mohou přistupovat k vašim datům, jako jsou konverzace a vzpomínky.';

  @override
  String get noExternalAppsHaveAccess => 'Žádné externí aplikace nemají přístup k vašim datům.';

  @override
  String get maximumSecurityE2ee => 'Maximální zabezpečení (E2EE)';

  @override
  String get e2eeDescription =>
      'End-to-end šifrování je zlatý standard ochrany soukromí. Když je povoleno, vaše data jsou šifrována na vašem zařízení před odesláním na naše servery. To znamená, že nikdo, ani Omi, nemůže přistupovat k vašemu obsahu.';

  @override
  String get importantTradeoffs => 'Důležité kompromisy:';

  @override
  String get e2eeTradeoff1 => '• Některé funkce jako integrace externích aplikací mohou být zakázány.';

  @override
  String get e2eeTradeoff2 => '• Pokud ztratíte heslo, vaše data nelze obnovit.';

  @override
  String get featureComingSoon => 'Tato funkce bude brzy k dispozici!';

  @override
  String get migrationInProgressMessage => 'Migrace probíhá. Úroveň ochrany nelze změnit, dokud nebude dokončena.';

  @override
  String get migrationFailed => 'Migrace selhala';

  @override
  String migratingFromTo(String source, String target) {
    return 'Migrace z $source na $target';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total objektů';
  }

  @override
  String get secureEncryption => 'Bezpečné šifrování';

  @override
  String get secureEncryptionDescription =>
      'Vaše data jsou šifrována klíčem jedinečným pro vás na našich serverech hostovaných v Google Cloud. To znamená, že váš surový obsah je nepřístupný nikomu, včetně zaměstnanců Omi nebo Google, přímo z databáze.';

  @override
  String get endToEndEncryption => 'End-to-end šifrování';

  @override
  String get e2eeCardDescription =>
      'Povolte pro maximální zabezpečení, kde pouze vy máte přístup k vašim datům. Klepnutím se dozvíte více.';

  @override
  String get dataAlwaysEncrypted => 'Bez ohledu na úroveň jsou vaše data vždy šifrována v klidu i při přenosu.';

  @override
  String get readOnlyScope => 'Pouze pro čtení';

  @override
  String get fullAccessScope => 'Plný přístup';

  @override
  String get readScope => 'Čtení';

  @override
  String get writeScope => 'Zápis';

  @override
  String get apiKeyCreated => 'API klíč vytvořen!';

  @override
  String get saveKeyWarning => 'Uložte si tento klíč nyní! Znovu ho neuvidíte.';

  @override
  String get yourApiKey => 'VÁŠ API KLÍČ';

  @override
  String get tapToCopy => 'Klepnutím zkopírujete';

  @override
  String get copyKey => 'Kopírovat klíč';

  @override
  String get createApiKey => 'Vytvořit API klíč';

  @override
  String get accessDataProgrammatically => 'Programově přistupujte ke svým datům';

  @override
  String get keyNameLabel => 'NÁZEV KLÍČE';

  @override
  String get keyNamePlaceholder => 'např. Moje integrace aplikace';

  @override
  String get permissionsLabel => 'OPRÁVNĚNÍ';

  @override
  String get permissionsInfoNote => 'R = Čtení, W = Zápis. Výchozí je pouze pro čtení, pokud není nic vybráno.';

  @override
  String get developerApi => 'Vývojářské API';

  @override
  String get createAKeyToGetStarted => 'Vytvořte klíč pro začátek';

  @override
  String errorWithMessage(String error) {
    return 'Chyba: $error';
  }

  @override
  String get omiTraining => 'Omi Trénink';

  @override
  String get trainingDataProgram => 'Program trénovacích dat';

  @override
  String get getOmiUnlimitedFree => 'Získejte Omi Unlimited zdarma přispěním vašich dat k trénování AI modelů.';

  @override
  String get trainingDataBullets =>
      '• Vaše data pomáhají vylepšovat AI modely\n• Sdílena jsou pouze necitlivá data\n• Plně transparentní proces';

  @override
  String get learnMoreAtOmiTraining => 'Zjistěte více na omi.me/training';

  @override
  String get agreeToContributeData => 'Rozumím a souhlasím s přispěním mých dat pro trénování AI';

  @override
  String get submitRequest => 'Odeslat žádost';

  @override
  String get thankYouRequestUnderReview => 'Děkujeme! Vaše žádost se posuzuje. Budeme vás informovat po schválení.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'Váš plán zůstane aktivní do $date. Poté ztratíte přístup k neomezeným funkcím. Jste si jisti?';
  }

  @override
  String get confirmCancellation => 'Potvrdit zrušení';

  @override
  String get keepMyPlan => 'Ponechat můj plán';

  @override
  String get subscriptionSetToCancel => 'Vaše předplatné je nastaveno na zrušení na konci období.';

  @override
  String get switchedToOnDevice => 'Přepnuto na přepis na zařízení';

  @override
  String get couldNotSwitchToFreePlan => 'Nelze přepnout na bezplatný plán. Zkuste to prosím znovu.';

  @override
  String get couldNotLoadPlans => 'Nelze načíst dostupné plány. Zkuste to prosím znovu.';

  @override
  String get selectedPlanNotAvailable => 'Vybraný plán není k dispozici. Zkuste to prosím znovu.';

  @override
  String get upgradeToAnnualPlan => 'Upgradovat na roční plán';

  @override
  String get importantBillingInfo => 'Důležité informace o fakturaci:';

  @override
  String get monthlyPlanContinues => 'Váš aktuální měsíční plán bude pokračovat do konce fakturačního období';

  @override
  String get paymentMethodCharged =>
      'Vaše stávající platební metoda bude automaticky účtována po skončení měsíčního plánu';

  @override
  String get annualSubscriptionStarts => 'Vaše 12měsíční roční předplatné začne automaticky po zaúčtování';

  @override
  String get thirteenMonthsCoverage => 'Získáte celkem 13 měsíců pokrytí (aktuální měsíc + 12 měsíců ročně)';

  @override
  String get confirmUpgrade => 'Potvrdit upgrade';

  @override
  String get confirmPlanChange => 'Potvrdit změnu plánu';

  @override
  String get confirmAndProceed => 'Potvrdit a pokračovat';

  @override
  String get upgradeScheduled => 'Upgrade naplánován';

  @override
  String get changePlan => 'Změnit plán';

  @override
  String get upgradeAlreadyScheduled => 'Váš upgrade na roční plán je již naplánován';

  @override
  String get youAreOnUnlimitedPlan => 'Jste na plánu Unlimited.';

  @override
  String get yourOmiUnleashed => 'Váš Omi, uvolněný. Přejděte na neomezený pro nekonečné možnosti.';

  @override
  String planEndedOn(String date) {
    return 'Váš plán skončil $date.\\nZnovu se přihlaste nyní - budete okamžitě účtováni za nové fakturační období.';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'Váš plán je nastaven na zrušení $date.\\nZnovu se přihlaste nyní, abyste si zachovali výhody - bez poplatku do $date.';
  }

  @override
  String get annualPlanStartsAutomatically => 'Váš roční plán začne automaticky, když skončí váš měsíční plán.';

  @override
  String planRenewsOn(String date) {
    return 'Váš plán se obnovuje $date.';
  }

  @override
  String get unlimitedConversations => 'Neomezené konverzace';

  @override
  String get askOmiAnything => 'Zeptejte se Omi na cokoli o svém životě';

  @override
  String get unlockOmiInfiniteMemory => 'Odemkněte nekonečnou paměť Omi';

  @override
  String get youreOnAnnualPlan => 'Jste na ročním plánu';

  @override
  String get alreadyBestValuePlan => 'Již máte plán s nejlepší hodnotou. Nejsou potřeba žádné změny.';

  @override
  String get unableToLoadPlans => 'Nelze načíst plány';

  @override
  String get checkConnectionTryAgain => 'Zkontrolujte připojení a zkuste to znovu';

  @override
  String get useFreePlan => 'Použít bezplatný plán';

  @override
  String get continueText => 'Pokračovat';

  @override
  String get resubscribe => 'Znovu se přihlásit';

  @override
  String get couldNotOpenPaymentSettings => 'Nelze otevřít nastavení platby. Zkuste to prosím znovu.';

  @override
  String get managePaymentMethod => 'Spravovat platební metodu';

  @override
  String get cancelSubscription => 'Zrušit předplatné';

  @override
  String endsOnDate(String date) {
    return 'Končí $date';
  }

  @override
  String get active => 'Aktivní';

  @override
  String get freePlan => 'Bezplatný plán';

  @override
  String get configure => 'Konfigurovat';

  @override
  String get privacyInformation => 'Informace o soukromí';

  @override
  String get yourPrivacyMattersToUs => 'Na vašem soukromí nám záleží';

  @override
  String get privacyIntroText =>
      'V Omi bereme vaše soukromí velmi vážně. Chceme být transparentní ohledně dat, která shromažďujeme a jak je používáme ke zlepšení produktu. Zde je to, co potřebujete vědět:';

  @override
  String get whatWeTrack => 'Co sledujeme';

  @override
  String get anonymityAndPrivacy => 'Anonymita a soukromí';

  @override
  String get optInAndOptOutOptions => 'Možnosti přihlášení a odhlášení';

  @override
  String get ourCommitment => 'Náš závazek';

  @override
  String get commitmentText =>
      'Zavazujeme se používat shromážděná data pouze k tomu, abychom z Omi udělali lepší produkt. Vaše soukromí a důvěra jsou pro nás prvořadé.';

  @override
  String get thankYouText =>
      'Děkujeme, že jste váženým uživatelem Omi. Máte-li jakékoli dotazy nebo obavy, neváhejte nás kontaktovat na team@basedhardware.com.';

  @override
  String get wifiSyncSettings => 'Nastavení WiFi synchronizace';

  @override
  String get enterHotspotCredentials => 'Zadejte přihlašovací údaje hotspotu telefonu';

  @override
  String get wifiSyncUsesHotspot =>
      'WiFi synchronizace používá váš telefon jako hotspot. Název a heslo najdete v Nastavení > Osobní hotspot.';

  @override
  String get hotspotNameSsid => 'Název hotspotu (SSID)';

  @override
  String get exampleIphoneHotspot => 'např. iPhone Hotspot';

  @override
  String get password => 'Heslo';

  @override
  String get enterHotspotPassword => 'Zadejte heslo hotspotu';

  @override
  String get saveCredentials => 'Uložit přihlašovací údaje';

  @override
  String get clearCredentials => 'Vymazat přihlašovací údaje';

  @override
  String get pleaseEnterHotspotName => 'Prosím zadejte název hotspotu';

  @override
  String get wifiCredentialsSaved => 'WiFi přihlašovací údaje uloženy';

  @override
  String get wifiCredentialsCleared => 'WiFi přihlašovací údaje vymazány';

  @override
  String summaryGeneratedForDate(String date) {
    return 'Shrnutí vygenerováno pro $date';
  }

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'Nepodařilo se vygenerovat shrnutí. Ujistěte se, že máte konverzace pro daný den.';

  @override
  String get summaryNotFound => 'Shrnutí nenalezeno';

  @override
  String get yourDaysJourney => 'Vaše denní cesta';

  @override
  String get highlights => 'Zajímavosti';

  @override
  String get unresolvedQuestions => 'Nevyřešené otázky';

  @override
  String get decisions => 'Rozhodnutí';

  @override
  String get learnings => 'Poznatky';

  @override
  String get autoDeletesAfterThreeDays => 'Automaticky smazáno po 3 dnech.';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'Graf znalostí úspěšně smazán';

  @override
  String get exportStartedMayTakeFewSeconds => 'Export zahájen. Může to trvat několik sekund...';

  @override
  String get knowledgeGraphDeleteDescription =>
      'Tímto se odstraní všechna odvozená data grafu znalostí (uzly a spojení). Vaše původní vzpomínky zůstanou v bezpečí. Graf bude postupně obnoven nebo při dalším požadavku.';

  @override
  String get configureDailySummaryDigest => 'Nastavte si denní přehled úkolů';

  @override
  String accessesDataTypes(String dataTypes) {
    return 'Přistupuje k $dataTypes';
  }

  @override
  String triggeredByType(String triggerType) {
    return 'spuštěno $triggerType';
  }

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription a je $triggerDescription.';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return 'Je $triggerDescription.';
  }

  @override
  String get noSpecificDataAccessConfigured => 'Není nakonfigurován žádný specifický přístup k datům.';

  @override
  String get basicPlanDescription => '1 200 prémiových minut + neomezené na zařízení';

  @override
  String get minutes => 'minut';

  @override
  String get omiHas => 'Omi má:';

  @override
  String get premiumMinutesUsed => 'Prémiové minuty vyčerpány.';

  @override
  String get setupOnDevice => 'Nastavit na zařízení';

  @override
  String get forUnlimitedFreeTranscription => 'pro neomezenou bezplatnou transkripci.';

  @override
  String premiumMinsLeft(int count) {
    return 'Zbývá $count prémiových minut.';
  }

  @override
  String get alwaysAvailable => 'vždy k dispozici.';

  @override
  String get importHistory => 'Historie importu';

  @override
  String get noImportsYet => 'Zatím žádné importy';

  @override
  String get selectZipFileToImport => 'Vyberte soubor .zip pro import!';

  @override
  String get otherDevicesComingSoon => 'Další zařízení již brzy';

  @override
  String get deleteAllLimitlessConversations => 'Smazat všechny konverzace z Limitless?';

  @override
  String get deleteAllLimitlessWarning =>
      'Toto trvale smaže všechny konverzace importované z Limitless. Tuto akci nelze vrátit zpět.';

  @override
  String deletedLimitlessConversations(int count) {
    return 'Smazáno $count konverzací z Limitless';
  }

  @override
  String get failedToDeleteConversations => 'Nepodařilo se smazat konverzace';

  @override
  String get deleteImportedData => 'Smazat importovaná data';

  @override
  String get statusPending => 'Čeká';

  @override
  String get statusProcessing => 'Zpracovává se';

  @override
  String get statusCompleted => 'Dokončeno';

  @override
  String get statusFailed => 'Selhalo';

  @override
  String nConversations(int count) {
    return '$count konverzací';
  }

  @override
  String get pleaseEnterName => 'Prosím zadejte jméno';

  @override
  String get nameMustBeBetweenCharacters => 'Jméno musí mít 2 až 40 znaků';

  @override
  String get deleteSampleQuestion => 'Smazat vzorek?';

  @override
  String deleteSampleConfirmation(String name) {
    return 'Opravdu chcete smazat vzorek uživatele $name?';
  }

  @override
  String get confirmDeletion => 'Potvrdit smazání';

  @override
  String deletePersonConfirmation(String name) {
    return 'Opravdu chcete smazat $name? Tím se také odstraní všechny přidružené hlasové vzorky.';
  }

  @override
  String get howItWorksTitle => 'Jak to funguje?';

  @override
  String get howPeopleWorks =>
      'Jakmile je osoba vytvořena, můžete přejít k přepisu konverzace a přiřadit jim odpovídající segmenty, tak Omi bude moci rozpoznat i jejich řeč!';

  @override
  String get tapToDelete => 'Klepněte pro smazání';

  @override
  String get newTag => 'NOVÉ';

  @override
  String get needHelpChatWithUs => 'Potřebujete pomoc? Napište nám';

  @override
  String get localStorageEnabled => 'Místní úložiště povoleno';

  @override
  String get localStorageDisabled => 'Místní úložiště zakázáno';

  @override
  String failedToUpdateSettings(String error) {
    return 'Nepodařilo se aktualizovat nastavení: $error';
  }

  @override
  String get privacyNotice => 'Oznámení o ochraně soukromí';

  @override
  String get recordingsMayCaptureOthers =>
      'Nahrávky mohou zachytit hlasy ostatních. Před povolením se ujistěte, že máte souhlas všech účastníků.';

  @override
  String get enable => 'Povolit';

  @override
  String get storeAudioOnPhone => 'Ukládat zvuk v telefonu';

  @override
  String get on => 'Zap';

  @override
  String get storeAudioDescription =>
      'Uchovávejte všechny zvukové nahrávky uložené místně v telefonu. Při vypnutí se ukládají pouze neúspěšné nahrávky pro úsporu místa.';

  @override
  String get enableLocalStorage => 'Povolit místní úložiště';

  @override
  String get cloudStorageEnabled => 'Cloudové úložiště povoleno';

  @override
  String get cloudStorageDisabled => 'Cloudové úložiště zakázáno';

  @override
  String get enableCloudStorage => 'Povolit cloudové úložiště';

  @override
  String get storeAudioOnCloud => 'Ukládat zvuk do cloudu';

  @override
  String get cloudStorageDialogMessage =>
      'Vaše nahrávky v reálném čase budou ukládány do soukromého cloudového úložiště, zatímco mluvíte.';

  @override
  String get storeAudioCloudDescription =>
      'Ukládejte své nahrávky v reálném čase do soukromého cloudového úložiště, zatímco mluvíte. Zvuk je zachycen a bezpečně uložen v reálném čase.';

  @override
  String get downloadingFirmware => 'Stahování firmwaru';

  @override
  String get installingFirmware => 'Instalace firmwaru';

  @override
  String get firmwareUpdateWarning =>
      'Nezavírejte aplikaci ani nevypínejte zařízení. Mohlo by to poškodit vaše zařízení.';

  @override
  String get firmwareUpdated => 'Firmware aktualizován';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'Pro dokončení aktualizace restartujte $deviceName.';
  }

  @override
  String get yourDeviceIsUpToDate => 'Vaše zařízení je aktuální';

  @override
  String get currentVersion => 'Aktuální verze';

  @override
  String get latestVersion => 'Nejnovější verze';

  @override
  String get whatsNew => 'Co je nového';

  @override
  String get installUpdate => 'Nainstalovat aktualizaci';

  @override
  String get updateNow => 'Aktualizovat nyní';

  @override
  String get updateGuide => 'Průvodce aktualizací';

  @override
  String get checkingForUpdates => 'Kontrola aktualizací';

  @override
  String get checkingFirmwareVersion => 'Kontrola verze firmwaru...';

  @override
  String get firmwareUpdate => 'Aktualizace firmwaru';

  @override
  String get payments => 'Platby';

  @override
  String get connectPaymentMethodInfo => 'Připojte níže platební metodu a začněte přijímat platby za své aplikace.';

  @override
  String get selectedPaymentMethod => 'Vybraná platební metoda';

  @override
  String get availablePaymentMethods => 'Dostupné platební metody';

  @override
  String get activeStatus => 'Aktivní';

  @override
  String get connectedStatus => 'Připojeno';

  @override
  String get notConnectedStatus => 'Nepřipojeno';

  @override
  String get setActive => 'Nastavit jako aktivní';

  @override
  String get getPaidThroughStripe => 'Získejte platby za prodej aplikací přes Stripe';

  @override
  String get monthlyPayouts => 'Měsíční výplaty';

  @override
  String get monthlyPayoutsDescription => 'Dostávejte měsíční platby přímo na účet, když dosáhnete výdělku 10 \$';

  @override
  String get secureAndReliable => 'Bezpečné a spolehlivé';

  @override
  String get stripeSecureDescription => 'Stripe zajišťuje bezpečné a včasné převody příjmů z vaší aplikace';

  @override
  String get selectYourCountry => 'Vyberte svou zemi';

  @override
  String get countrySelectionPermanent => 'Výběr země je trvalý a nelze jej později změnit.';

  @override
  String get byClickingConnectNow => 'Kliknutím na \"Připojit nyní\" souhlasíte s';

  @override
  String get stripeConnectedAccountAgreement => 'Smlouva o propojeném účtu Stripe';

  @override
  String get errorConnectingToStripe => 'Chyba při připojování k Stripe! Zkuste to prosím později.';

  @override
  String get connectingYourStripeAccount => 'Připojování vašeho účtu Stripe';

  @override
  String get stripeOnboardingInstructions =>
      'Dokončete prosím proces registrace Stripe ve vašem prohlížeči. Tato stránka se automaticky aktualizuje po dokončení.';

  @override
  String get failedTryAgain => 'Selhalo? Zkusit znovu';

  @override
  String get illDoItLater => 'Udělám to později';

  @override
  String get successfullyConnected => 'Úspěšně připojeno!';

  @override
  String get stripeReadyForPayments =>
      'Váš účet Stripe je nyní připraven přijímat platby. Můžete začít vydělávat z prodeje aplikací ihned.';

  @override
  String get updateStripeDetails => 'Aktualizovat údaje Stripe';

  @override
  String get errorUpdatingStripeDetails => 'Chyba při aktualizaci údajů Stripe! Zkuste to prosím později.';

  @override
  String get updatePayPal => 'Aktualizovat PayPal';

  @override
  String get setUpPayPal => 'Nastavit PayPal';

  @override
  String get updatePayPalAccountDetails => 'Aktualizujte údaje svého účtu PayPal';

  @override
  String get connectPayPalToReceivePayments => 'Připojte svůj účet PayPal a začněte přijímat platby za své aplikace';

  @override
  String get paypalEmail => 'E-mail PayPal';

  @override
  String get paypalMeLink => 'Odkaz PayPal.me';

  @override
  String get stripeRecommendation =>
      'Pokud je Stripe k dispozici ve vaší zemi, důrazně doporučujeme jej používat pro rychlejší a snadnější výplaty.';

  @override
  String get updatePayPalDetails => 'Aktualizovat údaje PayPal';

  @override
  String get savePayPalDetails => 'Uložit údaje PayPal';

  @override
  String get pleaseEnterPayPalEmail => 'Zadejte prosím svůj e-mail PayPal';

  @override
  String get pleaseEnterPayPalMeLink => 'Zadejte prosím svůj odkaz PayPal.me';

  @override
  String get doNotIncludeHttpInLink => 'Nezahrnujte http nebo https nebo www do odkazu';

  @override
  String get pleaseEnterValidPayPalMeLink => 'Zadejte prosím platný odkaz PayPal.me';

  @override
  String get pleaseEnterValidEmail => 'Zadejte prosím platnou e-mailovou adresu';

  @override
  String get syncingYourRecordings => 'Synchronizace vašich nahrávek';

  @override
  String get syncYourRecordings => 'Synchronizujte své nahrávky';

  @override
  String get syncNow => 'Synchronizovat nyní';

  @override
  String get error => 'Chyba';

  @override
  String get speechSamples => 'Hlasové vzorky';

  @override
  String additionalSampleIndex(String index) {
    return 'Další vzorek $index';
  }

  @override
  String durationSeconds(String seconds) {
    return 'Délka: $seconds sekund';
  }

  @override
  String get additionalSpeechSampleRemoved => 'Další hlasový vzorek byl odstraněn';

  @override
  String get consentDataMessage =>
      'Pokračováním budou všechna data, která s touto aplikací sdílíte (včetně vašich konverzací, nahrávek a osobních informací), bezpečně uložena na našich serverech, abychom vám mohli poskytovat poznatky založené na AI a umožnit všechny funkce aplikace.';

  @override
  String get tasksEmptyStateMessage => 'Úkoly z vašich konverzací se zobrazí zde.\nKlepněte na + pro ruční vytvoření.';

  @override
  String get clearChatAction => 'Vymazat chat';

  @override
  String get enableApps => 'Povolit aplikace';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => 'zobrazit více ↓';

  @override
  String get showLess => 'zobrazit méně ↑';

  @override
  String get loadingYourRecording => 'Načítání nahrávky...';

  @override
  String get photoDiscardedMessage => 'Tato fotografie byla zahozena, protože nebyla významná.';

  @override
  String get analyzing => 'Analyzování...';

  @override
  String get searchCountries => 'Hledat země...';

  @override
  String get checkingAppleWatch => 'Kontrola Apple Watch...';

  @override
  String get installOmiOnAppleWatch => 'Nainstalujte Omi na\nApple Watch';

  @override
  String get installOmiOnAppleWatchDescription =>
      'Chcete-li používat Apple Watch s Omi, musíte nejprve nainstalovat aplikaci Omi na hodinky.';

  @override
  String get openOmiOnAppleWatch => 'Otevřete Omi na\nApple Watch';

  @override
  String get openOmiOnAppleWatchDescription =>
      'Aplikace Omi je nainstalována na vašem Apple Watch. Otevřete ji a klepněte na Start.';

  @override
  String get openWatchApp => 'Otevřít aplikaci Watch';

  @override
  String get iveInstalledAndOpenedTheApp => 'Nainstaloval(a) jsem a otevřel(a) aplikaci';

  @override
  String get unableToOpenWatchApp =>
      'Nelze otevřít aplikaci Apple Watch. Ručně otevřete aplikaci Watch na Apple Watch a nainstalujte Omi ze sekce \"Dostupné aplikace\".';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch úspěšně připojeny!';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch stále není dostupné. Ujistěte se, že aplikace Omi je na hodinkách otevřená.';

  @override
  String errorCheckingConnection(String error) {
    return 'Chyba při kontrole připojení: $error';
  }

  @override
  String get muted => 'Ztlumeno';

  @override
  String get processNow => 'Zpracovat nyní';

  @override
  String get finishedConversation => 'Dokončená konverzace?';

  @override
  String get stopRecordingConfirmation => 'Opravdu chcete zastavit nahrávání a shrnout konverzaci nyní?';

  @override
  String get conversationEndsManually => 'Konverzace skončí pouze ručně.';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'Konverzace je shrnuta po $minutes minut$suffix bez řeči.';
  }

  @override
  String get dontAskAgain => 'Neptej se mě znovu';

  @override
  String get waitingForTranscriptOrPhotos => 'Čekání na přepis nebo fotografie...';

  @override
  String get noSummaryYet => 'Zatím žádné shrnutí';

  @override
  String hints(String text) {
    return 'Tipy: $text';
  }

  @override
  String get testConversationPrompt => 'Test výzvy konverzace';

  @override
  String get prompt => 'Výzva';

  @override
  String get result => 'Výsledek:';

  @override
  String get compareTranscripts => 'Porovnat přepisy';

  @override
  String get notHelpful => 'Nebylo užitečné';

  @override
  String get exportTasksWithOneTap => 'Exportujte úkoly jedním klepnutím!';

  @override
  String get inProgress => 'Probíhá';

  @override
  String get photos => 'Fotky';

  @override
  String get rawData => 'Nezpracovaná data';

  @override
  String get content => 'Obsah';

  @override
  String get noContentToDisplay => 'Žádný obsah k zobrazení';

  @override
  String get noSummary => 'Žádný souhrn';

  @override
  String get updateOmiFirmware => 'Aktualizovat firmware omi';

  @override
  String get anErrorOccurredTryAgain => 'Došlo k chybě. Zkuste to prosím znovu.';

  @override
  String get welcomeBackSimple => 'Vítejte zpět';

  @override
  String get addVocabularyDescription => 'Přidejte slova, která má Omi rozpoznat během přepisu.';

  @override
  String get enterWordsCommaSeparated => 'Zadejte slova (oddělená čárkou)';

  @override
  String get whenToReceiveDailySummary => 'Kdy obdržet denní shrnutí';

  @override
  String get checkingNextSevenDays => 'Kontrola následujících 7 dnů';

  @override
  String failedToDeleteError(String error) {
    return 'Smazání se nezdařilo: $error';
  }

  @override
  String get developerApiKeys => 'Vývojářské API klíče';

  @override
  String get noApiKeysCreateOne => 'Žádné API klíče. Vytvořte jeden pro začátek.';

  @override
  String get commandRequired => '⌘ je vyžadováno';

  @override
  String get spaceKey => 'Mezerník';

  @override
  String loadMoreRemaining(String count) {
    return 'Načíst více ($count zbývá)';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'Top $percentile% uživatel';
  }

  @override
  String get wrappedMinutes => 'minut';

  @override
  String get wrappedConversations => 'konverzací';

  @override
  String get wrappedDaysActive => 'aktivních dnů';

  @override
  String get wrappedYouTalkedAbout => 'Mluvili jste o';

  @override
  String get wrappedActionItems => 'Úkoly';

  @override
  String get wrappedTasksCreated => 'vytvořených úkolů';

  @override
  String get wrappedCompleted => 'dokončeno';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% míra dokončení';
  }

  @override
  String get wrappedYourTopDays => 'Vaše nejlepší dny';

  @override
  String get wrappedBestMoments => 'Nejlepší momenty';

  @override
  String get wrappedMyBuddies => 'Moji kamarádi';

  @override
  String get wrappedCouldntStopTalkingAbout => 'Nemohl jsem přestat mluvit o';

  @override
  String get wrappedShow => 'SERIÁL';

  @override
  String get wrappedMovie => 'FILM';

  @override
  String get wrappedBook => 'KNIHA';

  @override
  String get wrappedCelebrity => 'CELEBRITA';

  @override
  String get wrappedFood => 'JÍDLO';

  @override
  String get wrappedMovieRecs => 'Filmová doporučení pro přátele';

  @override
  String get wrappedBiggest => 'Největší';

  @override
  String get wrappedStruggle => 'Výzva';

  @override
  String get wrappedButYouPushedThrough => 'Ale zvládli jste to 💪';

  @override
  String get wrappedWin => 'Výhra';

  @override
  String get wrappedYouDidIt => 'Dokázali jste to! 🎉';

  @override
  String get wrappedTopPhrases => 'Top 5 frází';

  @override
  String get wrappedMins => 'min';

  @override
  String get wrappedConvos => 'konverzací';

  @override
  String get wrappedDays => 'dnů';

  @override
  String get wrappedMyBuddiesLabel => 'MOJI KAMARÁDI';

  @override
  String get wrappedObsessionsLabel => 'POSEDLOSTI';

  @override
  String get wrappedStruggleLabel => 'VÝZVA';

  @override
  String get wrappedWinLabel => 'VÝHRA';

  @override
  String get wrappedTopPhrasesLabel => 'TOP FRÁZE';

  @override
  String get wrappedLetsHitRewind => 'Přetočme zpět tvůj';

  @override
  String get wrappedGenerateMyWrapped => 'Vygenerovat můj Wrapped';

  @override
  String get wrappedProcessingDefault => 'Zpracování...';

  @override
  String get wrappedCreatingYourStory => 'Vytváříme tvůj\npříběh roku 2025...';

  @override
  String get wrappedSomethingWentWrong => 'Něco se\npokazilo';

  @override
  String get wrappedAnErrorOccurred => 'Došlo k chybě';

  @override
  String get wrappedTryAgain => 'Zkusit znovu';

  @override
  String get wrappedNoDataAvailable => 'Žádná data nejsou k dispozici';

  @override
  String get wrappedOmiLifeRecap => 'Omi shrnutí života';

  @override
  String get wrappedSwipeUpToBegin => 'Přejeď nahoru pro začátek';

  @override
  String get wrappedShareText => 'Můj rok 2025, zachycený Omi ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare => 'Sdílení se nezdařilo. Zkuste to prosím znovu.';

  @override
  String get wrappedFailedToStartGeneration => 'Spuštění generování se nezdařilo. Zkuste to prosím znovu.';

  @override
  String get wrappedStarting => 'Spouštím...';

  @override
  String get wrappedShare => 'Sdílet';

  @override
  String get wrappedShareYourWrapped => 'Sdílej svůj Wrapped';

  @override
  String get wrappedMy2025 => 'Můj 2025';

  @override
  String get wrappedRememberedByOmi => 'zachycený Omi';

  @override
  String get wrappedMostFunDay => 'Nejzábavnější';

  @override
  String get wrappedMostProductiveDay => 'Nejproduktivnější';

  @override
  String get wrappedMostIntenseDay => 'Nejintenzivnější';

  @override
  String get wrappedFunniestMoment => 'Nejvtipnější';

  @override
  String get wrappedMostCringeMoment => 'Nejtrapnější';

  @override
  String get wrappedMinutesLabel => 'minut';

  @override
  String get wrappedConversationsLabel => 'konverzací';

  @override
  String get wrappedDaysActiveLabel => 'aktivních dnů';

  @override
  String get wrappedTasksGenerated => 'vytvořených úkolů';

  @override
  String get wrappedTasksCompleted => 'dokončených úkolů';

  @override
  String get wrappedTopFivePhrases => 'Top 5 frází';

  @override
  String get wrappedAGreatDay => 'Skvělý den';

  @override
  String get wrappedGettingItDone => 'Dostat to hotové';

  @override
  String get wrappedAChallenge => 'Výzva';

  @override
  String get wrappedAHilariousMoment => 'Vtipný moment';

  @override
  String get wrappedThatAwkwardMoment => 'Ten trapný moment';

  @override
  String get wrappedYouHadFunnyMoments => 'Letos jsi měl/a vtipné chvíle!';

  @override
  String get wrappedWeveAllBeenThere => 'Všichni jsme tam byli!';

  @override
  String get wrappedFriend => 'Přítel';

  @override
  String get wrappedYourBuddy => 'Tvůj kamarád!';

  @override
  String get wrappedNotMentioned => 'Nezmíněno';

  @override
  String get wrappedTheHardPart => 'Těžká část';

  @override
  String get wrappedPersonalGrowth => 'Osobní růst';

  @override
  String get wrappedFunDay => 'Zábavný';

  @override
  String get wrappedProductiveDay => 'Produktivní';

  @override
  String get wrappedIntenseDay => 'Intenzivní';

  @override
  String get wrappedFunnyMomentTitle => 'Vtipný moment';

  @override
  String get wrappedCringeMomentTitle => 'Trapný moment';

  @override
  String get wrappedYouTalkedAboutBadge => 'Mluvil/a jsi o';

  @override
  String get wrappedCompletedLabel => 'Dokončeno';

  @override
  String get wrappedMyBuddiesCard => 'Moji kamarádi';

  @override
  String get wrappedBuddiesLabel => 'KAMARÁDI';

  @override
  String get wrappedObsessionsLabelUpper => 'POSEDLOSTI';

  @override
  String get wrappedStruggleLabelUpper => 'BOJ';

  @override
  String get wrappedWinLabelUpper => 'VÝHRA';

  @override
  String get wrappedTopPhrasesLabelUpper => 'TOP FRÁZE';

  @override
  String get wrappedYourHeader => 'Tvoje';

  @override
  String get wrappedTopDaysHeader => 'Nejlepší dny';

  @override
  String get wrappedYourTopDaysBadge => 'Tvoje nejlepší dny';

  @override
  String get wrappedBestHeader => 'Nejlepší';

  @override
  String get wrappedMomentsHeader => 'Momenty';

  @override
  String get wrappedBestMomentsBadge => 'Nejlepší momenty';

  @override
  String get wrappedBiggestHeader => 'Největší';

  @override
  String get wrappedStruggleHeader => 'Boj';

  @override
  String get wrappedWinHeader => 'Výhra';

  @override
  String get wrappedButYouPushedThroughEmoji => 'Ale zvládl/a jsi to 💪';

  @override
  String get wrappedYouDidItEmoji => 'Dokázal/a jsi to! 🎉';

  @override
  String get wrappedHours => 'hodin';

  @override
  String get wrappedActions => 'akcí';

  @override
  String get multipleSpeakersDetected => 'Bylo detekováno více mluvčích';

  @override
  String get multipleSpeakersDescription =>
      'Zdá se, že v nahrávce je více mluvčích. Ujistěte se, že jste na tichém místě a zkuste to znovu.';

  @override
  String get invalidRecordingDetected => 'Byla detekována neplatná nahrávka';

  @override
  String get notEnoughSpeechDescription => 'Nebylo detekováno dostatek řeči. Mluvte více a zkuste to znovu.';

  @override
  String get speechDurationDescription => 'Ujistěte se, že mluvíte alespoň 5 sekund a ne více než 90.';

  @override
  String get connectionLostDescription =>
      'Připojení bylo přerušeno. Zkontrolujte své internetové připojení a zkuste to znovu.';

  @override
  String get howToTakeGoodSample => 'Jak pořídit dobrý vzorek?';

  @override
  String get goodSampleInstructions =>
      '1. Ujistěte se, že jste na tichém místě.\n2. Mluvte jasně a přirozeně.\n3. Ujistěte se, že je vaše zařízení v přirozené poloze na krku.\n\nJakmile je vytvořen, můžete jej vždy vylepšit nebo udělat znovu.';

  @override
  String get noDeviceConnectedUseMic => 'Žádné připojené zařízení. Bude použit mikrofon telefonu.';

  @override
  String get doItAgain => 'Udělat znovu';

  @override
  String get listenToSpeechProfile => 'Poslechnout můj hlasový profil ➡️';

  @override
  String get recognizingOthers => 'Rozpoznávání ostatních 👀';

  @override
  String get keepGoingGreat => 'Pokračuj, jde ti to skvěle';

  @override
  String get somethingWentWrongTryAgain => 'Něco se pokazilo! Zkuste to prosím znovu později.';

  @override
  String get uploadingVoiceProfile => 'Nahrávání vašeho hlasového profilu....';

  @override
  String get memorizingYourVoice => 'Ukládání vašeho hlasu...';

  @override
  String get personalizingExperience => 'Přizpůsobování vašeho zážitku...';

  @override
  String get keepSpeakingUntil100 => 'Mluvte dál, dokud nedosáhnete 100%.';

  @override
  String get greatJobAlmostThere => 'Skvělá práce, už jste skoro tam';

  @override
  String get soCloseJustLittleMore => 'Tak blízko, jen ještě trochu';

  @override
  String get notificationFrequency => 'Frekvence oznámení';

  @override
  String get controlNotificationFrequency => 'Ovládejte, jak často vám Omi posílá proaktivní oznámení.';

  @override
  String get yourScore => 'Vaše skóre';

  @override
  String get dailyScoreBreakdown => 'Rozpis denního skóre';

  @override
  String get todaysScore => 'Dnešní skóre';

  @override
  String get tasksCompleted => 'Dokončené úkoly';

  @override
  String get completionRate => 'Míra dokončení';

  @override
  String get howItWorks => 'Jak to funguje';

  @override
  String get dailyScoreExplanation =>
      'Vaše denní skóre je založeno na plnění úkolů. Dokončete své úkoly pro zlepšení skóre!';

  @override
  String get notificationFrequencyDescription =>
      'Ovládejte, jak často vám Omi zasílá proaktivní oznámení a připomínky.';

  @override
  String get sliderOff => 'Vyp.';

  @override
  String get sliderMax => 'Max.';

  @override
  String summaryGeneratedFor(String date) {
    return 'Shrnutí vygenerováno pro $date';
  }

  @override
  String get failedToGenerateSummary =>
      'Nepodařilo se vygenerovat shrnutí. Ujistěte se, že máte konverzace pro tento den.';

  @override
  String get recap => 'Rekapitulace';

  @override
  String deleteQuoted(String name) {
    return 'Smazat \"$name\"';
  }

  @override
  String moveConversationsTo(int count) {
    return 'Přesunout $count konverzací do:';
  }

  @override
  String get noFolder => 'Bez složky';

  @override
  String get removeFromAllFolders => 'Odebrat ze všech složek';

  @override
  String get buildAndShareYourCustomApp => 'Vytvořte a sdílejte svou vlastní aplikaci';

  @override
  String get searchAppsPlaceholder => 'Hledat v 1500+ aplikacích';

  @override
  String get filters => 'Filtry';

  @override
  String get frequencyOff => 'Vypnuto';

  @override
  String get frequencyMinimal => 'Minimální';

  @override
  String get frequencyLow => 'Nízká';

  @override
  String get frequencyBalanced => 'Vyvážená';

  @override
  String get frequencyHigh => 'Vysoká';

  @override
  String get frequencyMaximum => 'Maximální';

  @override
  String get frequencyDescOff => 'Žádná proaktivní upozornění';

  @override
  String get frequencyDescMinimal => 'Pouze kritická připomenutí';

  @override
  String get frequencyDescLow => 'Pouze důležité aktualizace';

  @override
  String get frequencyDescBalanced => 'Pravidelné užitečné připomínky';

  @override
  String get frequencyDescHigh => 'Časté kontroly';

  @override
  String get frequencyDescMaximum => 'Zůstaňte neustále zapojeni';

  @override
  String get clearChatQuestion => 'Vymazat chat?';

  @override
  String get syncingMessages => 'Synchronizace zpráv se serverem...';

  @override
  String get chatAppsTitle => 'Chat aplikace';

  @override
  String get selectApp => 'Vybrat aplikaci';

  @override
  String get noChatAppsEnabled => 'Žádné chat aplikace nejsou povoleny.\nKlepněte na \"Povolit aplikace\" pro přidání.';

  @override
  String get disable => 'Zakázat';

  @override
  String get photoLibrary => 'Knihovna fotek';

  @override
  String get chooseFile => 'Vybrat soubor';

  @override
  String get configureAiPersona => 'Nakonfigurujte svou AI personu';

  @override
  String get connectAiAssistantsToYourData => 'Připojte AI asistenty k vašim datům';

  @override
  String get oAuth => 'OAuth';

  @override
  String get trackYourGoalsOnHomepage => 'Sledujte své osobní cíle na domovské stránce';

  @override
  String get deleteRecording => 'Smazat nahrávku';

  @override
  String get thisCannotBeUndone => 'Tuto akci nelze vrátit zpět.';

  @override
  String get sdCard => 'SD karta';

  @override
  String get fromSd => 'Z SD';

  @override
  String get limitless => 'Limitless';

  @override
  String get fastTransfer => 'Rychlý přenos';

  @override
  String get syncingStatus => 'Synchronizace';

  @override
  String get failedStatus => 'Selhalo';

  @override
  String etaLabel(String time) {
    return 'Odhadovaný čas: $time';
  }

  @override
  String get transferMethod => 'Metoda přenosu';

  @override
  String get fast => 'Rychle';

  @override
  String get ble => 'BLE';

  @override
  String get phone => 'Telefon';

  @override
  String get cancelSync => 'Zrušit synchronizaci';

  @override
  String get cancelSyncMessage => 'Již stažená data budou uložena. Můžete pokračovat později.';

  @override
  String get syncCancelled => 'Synchronizace zrušena';

  @override
  String get deleteProcessedFiles => 'Smazat zpracované soubory';

  @override
  String get processedFilesDeleted => 'Zpracované soubory smazány';

  @override
  String get wifiEnableFailed => 'Nepodařilo se povolit WiFi na zařízení. Zkuste to prosím znovu.';

  @override
  String get deviceNoFastTransfer => 'Vaše zařízení nepodporuje rychlý přenos. Použijte místo toho Bluetooth.';

  @override
  String get enableHotspotMessage => 'Povolte prosím hotspot telefonu a zkuste to znovu.';

  @override
  String get transferStartFailed => 'Nepodařilo se spustit přenos. Zkuste to prosím znovu.';

  @override
  String get deviceNotResponding => 'Zařízení neodpovídá. Zkuste to prosím znovu.';

  @override
  String get invalidWifiCredentials => 'Neplatné přihlašovací údaje WiFi. Zkontrolujte nastavení hotspotu.';

  @override
  String get wifiConnectionFailed => 'Připojení WiFi selhalo. Zkuste to prosím znovu.';

  @override
  String get sdCardProcessing => 'Zpracování SD karty';

  @override
  String sdCardProcessingMessage(int count) {
    return 'Zpracovávání $count nahrávek. Soubory budou poté odstraněny z SD karty.';
  }

  @override
  String get process => 'Zpracovat';

  @override
  String get wifiSyncFailed => 'WiFi synchronizace selhala';

  @override
  String get processingFailed => 'Zpracování selhalo';

  @override
  String get downloadingFromSdCard => 'Stahování z SD karty';

  @override
  String processingProgress(int current, int total) {
    return 'Zpracovávání $current/$total';
  }

  @override
  String conversationsCreated(int count) {
    return 'Vytvořeno $count konverzací';
  }

  @override
  String get internetRequired => 'Vyžadováno připojení k internetu';

  @override
  String get processAudio => 'Zpracovat zvuk';

  @override
  String get start => 'Start';

  @override
  String get noRecordings => 'Žádné nahrávky';

  @override
  String get audioFromOmiWillAppearHere => 'Zvuk z vašeho zařízení Omi se zobrazí zde';

  @override
  String get deleteProcessed => 'Smazat zpracované';

  @override
  String get tryDifferentFilter => 'Zkuste jiný filtr';

  @override
  String get recordings => 'Nahrávky';

  @override
  String get enableRemindersAccess => 'Pro použití Apple Připomínek povolte přístup k Připomínkám v Nastavení';

  @override
  String todayAtTime(String time) {
    return 'Dnes v $time';
  }

  @override
  String yesterdayAtTime(String time) {
    return 'Včera v $time';
  }

  @override
  String get lessThanAMinute => 'Méně než minuta';

  @override
  String estimatedMinutes(int count) {
    return '~$count minut(a)';
  }

  @override
  String estimatedHours(int count) {
    return '~$count hodin(a)';
  }

  @override
  String estimatedTimeRemaining(String time) {
    return 'Odhad: zbývá $time';
  }

  @override
  String get summarizingConversation => 'Shrnutí konverzace...\nMůže to trvat několik sekund';

  @override
  String get resummarizingConversation => 'Opětovné shrnutí konverzace...\nMůže to trvat několik sekund';

  @override
  String get nothingInterestingRetry => 'Nic zajímavého nenalezeno,\nchcete to zkusit znovu?';

  @override
  String get noSummaryForConversation => 'Pro tuto konverzaci\nnení k dispozici shrnutí.';

  @override
  String get unknownLocation => 'Neznámá poloha';

  @override
  String get couldNotLoadMap => 'Mapu se nepodařilo načíst';

  @override
  String get triggerConversationIntegration => 'Spustit integraci vytvoření konverzace';

  @override
  String get webhookUrlNotSet => 'URL webhooku není nastavena';

  @override
  String get setWebhookUrlInSettings => 'Pro použití této funkce nastavte URL webhooku v nastavení vývojáře.';

  @override
  String get sendWebUrl => 'Odeslat webovou URL';

  @override
  String get sendTranscript => 'Odeslat přepis';

  @override
  String get sendSummary => 'Odeslat shrnutí';

  @override
  String get debugModeDetected => 'Zjištěn režim ladění';

  @override
  String get performanceReduced => 'Výkon snížen 5-10x. Použijte režim Release.';

  @override
  String autoClosingInSeconds(int seconds) {
    return 'Automatické zavření za ${seconds}s';
  }

  @override
  String get modelRequired => 'Vyžadován model';

  @override
  String get downloadWhisperModel => 'Před uložením prosím stáhněte model Whisper.';

  @override
  String get deviceNotCompatible => 'Zařízení není kompatibilní';

  @override
  String get deviceRequirements => 'Vaše zařízení nesplňuje požadavky pro přepis na zařízení.';

  @override
  String get willLikelyCrash => 'Povolení pravděpodobně způsobí pád nebo zamrznutí aplikace.';

  @override
  String get transcriptionSlowerLessAccurate => 'Přepis bude výrazně pomalejší a méně přesný.';

  @override
  String get proceedAnyway => 'Přesto pokračovat';

  @override
  String get olderDeviceDetected => 'Zjištěno starší zařízení';

  @override
  String get onDeviceSlower => 'Přepis na zařízení může být na tomto zařízení pomalejší.';

  @override
  String get batteryUsageHigher => 'Spotřeba baterie bude vyšší než u cloudového přepisu.';

  @override
  String get considerOmiCloud => 'Zvažte použití Omi Cloud pro lepší výkon.';

  @override
  String get highResourceUsage => 'Vysoká spotřeba prostředků';

  @override
  String get onDeviceIntensive => 'Přepis na zařízení je výpočetně náročný.';

  @override
  String get batteryDrainIncrease => 'Spotřeba baterie se výrazně zvýší.';

  @override
  String get deviceMayWarmUp => 'Zařízení se může při delším používání zahřát.';

  @override
  String get speedAccuracyLower => 'Rychlost a přesnost mohou být nižší než u cloudových modelů.';

  @override
  String get cloudProvider => 'Cloudový poskytovatel';

  @override
  String get premiumMinutesInfo => '1 200 prémiových minut/měsíc. Karta Na zařízení nabízí neomezený bezplatný přepis.';

  @override
  String get viewUsage => 'Zobrazit využití';

  @override
  String get localProcessingInfo =>
      'Zvuk je zpracováván lokálně. Funguje offline, je soukromější, ale spotřebovává více baterie.';

  @override
  String get model => 'Model';

  @override
  String get performanceWarning => 'Varování o výkonu';

  @override
  String get largeModelWarning =>
      'Tento model je velký a může způsobit pád aplikace nebo velmi pomalý běh na mobilních zařízeních.\n\nDoporučuje se \"small\" nebo \"base\".';

  @override
  String get usingNativeIosSpeech => 'Používání nativního rozpoznávání řeči iOS';

  @override
  String get noModelDownloadRequired => 'Bude použit nativní hlasový modul vašeho zařízení. Není nutné stahovat model.';

  @override
  String get modelReady => 'Model připraven';

  @override
  String get redownload => 'Stáhnout znovu';

  @override
  String get doNotCloseApp => 'Prosím nezavírejte aplikaci.';

  @override
  String get downloading => 'Stahování...';

  @override
  String get downloadModel => 'Stáhnout model';

  @override
  String estimatedSize(String size) {
    return 'Odhadovaná velikost: ~$size MB';
  }

  @override
  String availableSpace(String space) {
    return 'Dostupné místo: $space';
  }

  @override
  String get notEnoughSpace => 'Varování: Nedostatek místa!';

  @override
  String get download => 'Stáhnout';

  @override
  String downloadError(String error) {
    return 'Chyba stahování: $error';
  }

  @override
  String get cancelled => 'Zrušeno';

  @override
  String get deviceNotCompatibleTitle => 'Zařízení není kompatibilní';

  @override
  String get deviceNotMeetRequirements => 'Vaše zařízení nesplňuje požadavky pro přepis na zařízení.';

  @override
  String get transcriptionSlowerOnDevice => 'Přepis na zařízení může být na tomto zařízení pomalejší.';

  @override
  String get computationallyIntensive => 'Přepis na zařízení je výpočetně náročný.';

  @override
  String get batteryDrainSignificantly => 'Vybíjení baterie se výrazně zvýší.';

  @override
  String get premiumMinutesMonth =>
      '1 200 prémiových minut/měsíc. Karta Na zařízení nabízí neomezený bezplatný přepis. ';

  @override
  String get audioProcessedLocally =>
      'Zvuk je zpracováván lokálně. Funguje offline, je soukromější, ale spotřebovává více baterie.';

  @override
  String get languageLabel => 'Jazyk';

  @override
  String get modelLabel => 'Model';

  @override
  String get modelTooLargeWarning =>
      'Tento model je velký a může způsobit pád aplikace nebo velmi pomalý běh na mobilních zařízeních.\n\nDoporučuje se small nebo base.';

  @override
  String get nativeEngineNoDownload => 'Bude použit nativní hlasový engine vašeho zařízení. Není nutné stahovat model.';

  @override
  String modelReadyWithName(String model) {
    return 'Model připraven ($model)';
  }

  @override
  String get reDownload => 'Znovu stáhnout';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return 'Stahování $model: $received / $total MB';
  }

  @override
  String preparingModel(String model) {
    return 'Příprava $model...';
  }

  @override
  String downloadErrorWithMessage(String error) {
    return 'Chyba stahování: $error';
  }

  @override
  String estimatedSizeWithValue(String size) {
    return 'Odhadovaná velikost: ~$size MB';
  }

  @override
  String availableSpaceWithValue(String space) {
    return 'Dostupné místo: $space';
  }

  @override
  String get omiTranscriptionOptimized =>
      'Vestavěný živý přepis Omi je optimalizován pro konverzace v reálném čase s automatickou detekcí mluvčích a diarizací.';

  @override
  String get reset => 'Resetovat';

  @override
  String get useTemplateFrom => 'Použít šablonu od';

  @override
  String get selectProviderTemplate => 'Vyberte šablonu poskytovatele...';

  @override
  String get quicklyPopulateResponse => 'Rychle vyplnit známým formátem odpovědi poskytovatele';

  @override
  String get quicklyPopulateRequest => 'Rychle vyplnit známým formátem požadavku poskytovatele';

  @override
  String get invalidJsonError => 'Neplatný JSON';

  @override
  String downloadModelWithName(String model) {
    return 'Stáhnout model ($model)';
  }

  @override
  String modelNameWithFile(String model) {
    return 'Model: $model';
  }

  @override
  String get device => 'Zařízení';

  @override
  String get chatAssistantsTitle => 'Chat asistenti';

  @override
  String get permissionReadConversations => 'Číst konverzace';

  @override
  String get permissionReadMemories => 'Číst vzpomínky';

  @override
  String get permissionReadTasks => 'Číst úkoly';

  @override
  String get permissionCreateConversations => 'Vytvářet konverzace';

  @override
  String get permissionCreateMemories => 'Vytvářet vzpomínky';

  @override
  String get permissionTypeAccess => 'Přístup';

  @override
  String get permissionTypeCreate => 'Vytvořit';

  @override
  String get permissionTypeTrigger => 'Spouštěč';

  @override
  String get permissionDescReadConversations => 'Tato aplikace může přistupovat k vašim konverzacím.';

  @override
  String get permissionDescReadMemories => 'Tato aplikace může přistupovat k vašim vzpomínkám.';

  @override
  String get permissionDescReadTasks => 'Tato aplikace může přistupovat k vašim úkolům.';

  @override
  String get permissionDescCreateConversations => 'Tato aplikace může vytvářet nové konverzace.';

  @override
  String get permissionDescCreateMemories => 'Tato aplikace může vytvářet nové vzpomínky.';

  @override
  String get realtimeListening => 'Poslech v reálném čase';

  @override
  String get setupCompleted => 'Dokončeno';

  @override
  String get pleaseSelectRating => 'Prosím vyberte hodnocení';

  @override
  String get writeReviewOptional => 'Napsat recenzi (volitelné)';

  @override
  String get setupQuestionsIntro => 'Pomozte nám vylepšit Omi odpověďmi na pár otázek. 🫶 💜';

  @override
  String get setupQuestionProfession => '1. Čím se zabýváte?';

  @override
  String get setupQuestionUsage => '2. Kde plánujete Omi používat?';

  @override
  String get setupQuestionAge => '3. Jaká je vaše věková kategorie?';

  @override
  String get setupAnswerAllQuestions => 'Ještě jste neodpověděli na všechny otázky! 🥺';

  @override
  String get setupSkipHelp => 'Přeskočit, nechci pomáhat :C';

  @override
  String get professionEntrepreneur => 'Podnikatel';

  @override
  String get professionSoftwareEngineer => 'Softwarový inženýr';

  @override
  String get professionProductManager => 'Produktový manažer';

  @override
  String get professionExecutive => 'Manažer';

  @override
  String get professionSales => 'Obchod';

  @override
  String get professionStudent => 'Student';

  @override
  String get usageAtWork => 'V práci';

  @override
  String get usageIrlEvents => 'Na akcích';

  @override
  String get usageOnline => 'Online';

  @override
  String get usageSocialSettings => 'Ve společnosti';

  @override
  String get usageEverywhere => 'Všude';

  @override
  String get customBackendUrlTitle => 'Vlastní URL serveru';

  @override
  String get backendUrlLabel => 'URL serveru';

  @override
  String get saveUrlButton => 'Uložit URL';

  @override
  String get enterBackendUrlError => 'Zadejte prosím URL serveru';

  @override
  String get urlMustEndWithSlashError => 'URL musí končit \"/\"';

  @override
  String get invalidUrlError => 'Zadejte prosím platnou URL';

  @override
  String get backendUrlSavedSuccess => 'URL serveru byla úspěšně uložena!';

  @override
  String get signInTitle => 'Přihlásit se';

  @override
  String get signInButton => 'Přihlásit se';

  @override
  String get enterEmailError => 'Zadejte prosím svůj e-mail';

  @override
  String get invalidEmailError => 'Zadejte prosím platný e-mail';

  @override
  String get enterPasswordError => 'Zadejte prosím své heslo';

  @override
  String get passwordMinLengthError => 'Heslo musí mít alespoň 8 znaků';

  @override
  String get signInSuccess => 'Přihlášení úspěšné!';

  @override
  String get alreadyHaveAccountLogin => 'Máte již účet? Přihlaste se';

  @override
  String get emailLabel => 'E-mail';

  @override
  String get passwordLabel => 'Heslo';

  @override
  String get createAccountTitle => 'Vytvořit účet';

  @override
  String get nameLabel => 'Jméno';

  @override
  String get repeatPasswordLabel => 'Zopakujte heslo';

  @override
  String get signUpButton => 'Registrovat se';

  @override
  String get enterNameError => 'Zadejte prosím své jméno';

  @override
  String get passwordsDoNotMatch => 'Hesla se neshodují';

  @override
  String get signUpSuccess => 'Registrace úspěšná!';

  @override
  String get loadingKnowledgeGraph => 'Načítání znalostního grafu...';

  @override
  String get noKnowledgeGraphYet => 'Zatím žádný znalostní graf';

  @override
  String get buildingKnowledgeGraphFromMemories => 'Vytváření znalostního grafu ze vzpomínek...';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'Váš znalostní graf se vytvoří automaticky, jakmile vytvoříte nové vzpomínky.';

  @override
  String get buildGraphButton => 'Vytvořit graf';

  @override
  String get checkOutMyMemoryGraph => 'Podívejte se na můj graf paměti!';

  @override
  String get getButton => 'Získat';

  @override
  String openingApp(String appName) {
    return 'Otevírám $appName...';
  }

  @override
  String get writeSomething => 'Napište něco';

  @override
  String get submitReply => 'Odeslat odpověď';

  @override
  String get editYourReply => 'Upravit odpověď';

  @override
  String get replyToReview => 'Odpovědět na recenzi';

  @override
  String get rateAndReviewThisApp => 'Ohodnoťte a recenzujte tuto aplikaci';

  @override
  String get noChangesInReview => 'Žádné změny v recenzi k aktualizaci.';

  @override
  String get cantRateWithoutInternet => 'Nelze hodnotit aplikaci bez připojení k internetu.';

  @override
  String get appAnalytics => 'Analytika aplikace';

  @override
  String get learnMoreLink => 'zjistit více';

  @override
  String get moneyEarned => 'Vyděláno';

  @override
  String get writeYourReply => 'Napište svou odpověď...';

  @override
  String get replySentSuccessfully => 'Odpověď byla úspěšně odeslána';

  @override
  String failedToSendReply(String error) {
    return 'Nepodařilo se odeslat odpověď: $error';
  }

  @override
  String get send => 'Odeslat';

  @override
  String starFilter(int count) {
    return '$count hvězda';
  }

  @override
  String get noReviewsFound => 'Nebyly nalezeny žádné recenze';

  @override
  String get editReply => 'Upravit odpověď';

  @override
  String get reply => 'Odpověď';

  @override
  String starFilterLabel(int count) {
    return '$count hvězda';
  }

  @override
  String get sharePublicLink => 'Sdílet veřejný odkaz';

  @override
  String get makePersonaPublic => 'Zveřejnit personu';

  @override
  String get connectedKnowledgeData => 'Připojená znalostní data';

  @override
  String get enterName => 'Zadejte jméno';

  @override
  String get disconnectTwitter => 'Odpojit Twitter';

  @override
  String get disconnectTwitterConfirmation =>
      'Opravdu chcete odpojit svůj účet Twitter? Vaše persona již nebude mít přístup k vašim datům z Twitteru.';

  @override
  String get getOmiDeviceDescription => 'Vytvořte přesnější klon s vašimi osobními konverzacemi';

  @override
  String get getOmi => 'Získat Omi';

  @override
  String get iHaveOmiDevice => 'Mám zařízení Omi';

  @override
  String get goal => 'CÍL';

  @override
  String get tapToTrackThisGoal => 'Klepnutím začnete sledovat tento cíl';

  @override
  String get tapToSetAGoal => 'Klepnutím nastavte cíl';

  @override
  String get processedConversations => 'Zpracované konverzace';

  @override
  String get updatedConversations => 'Aktualizované konverzace';

  @override
  String get newConversations => 'Nové konverzace';

  @override
  String get summaryTemplate => 'Šablona souhrnu';

  @override
  String get suggestedTemplates => 'Navrhované šablony';

  @override
  String get otherTemplates => 'Ostatní šablony';

  @override
  String get availableTemplates => 'Dostupné šablony';

  @override
  String get getCreative => 'Buďte kreativní';

  @override
  String get defaultLabel => 'Výchozí';

  @override
  String get lastUsedLabel => 'Naposledy použito';

  @override
  String get setDefaultApp => 'Nastavit výchozí aplikaci';

  @override
  String setDefaultAppContent(String appName) {
    return 'Nastavit $appName jako výchozí aplikaci pro shrnutí?\\n\\nTato aplikace bude automaticky použita pro všechna budoucí shrnutí konverzací.';
  }

  @override
  String get setDefaultButton => 'Nastavit výchozí';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName nastavena jako výchozí aplikace pro shrnutí';
  }

  @override
  String get createCustomTemplate => 'Vytvořit vlastní šablonu';

  @override
  String get allTemplates => 'Všechny šablony';

  @override
  String failedToInstallApp(String appName) {
    return 'Nepodařilo se nainstalovat $appName. Zkuste to prosím znovu.';
  }

  @override
  String errorInstallingApp(String appName, String error) {
    return 'Chyba při instalaci $appName: $error';
  }

  @override
  String tagSpeaker(int speakerId) {
    return 'Označit mluvčího $speakerId';
  }

  @override
  String get personNameAlreadyExists => 'Osoba s tímto jménem již existuje.';

  @override
  String get selectYouFromList => 'Pro označení sebe vyberte prosím \"Vy\" ze seznamu.';

  @override
  String get enterPersonsName => 'Zadejte jméno osoby';

  @override
  String get addPerson => 'Přidat osobu';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'Označit ostatní segmenty od tohoto mluvčího ($selected/$total)';
  }

  @override
  String get tagOtherSegments => 'Označit ostatní segmenty';

  @override
  String get managePeople => 'Správa osob';

  @override
  String get shareViaSms => 'Sdílet přes SMS';

  @override
  String get selectContactsToShareSummary => 'Vyberte kontakty pro sdílení shrnutí konverzace';

  @override
  String get searchContactsHint => 'Hledat kontakty...';

  @override
  String contactsSelectedCount(int count) {
    return '$count vybráno';
  }

  @override
  String get clearAllSelection => 'Vymazat vše';

  @override
  String get selectContactsToShare => 'Vyberte kontakty ke sdílení';

  @override
  String shareWithContactCount(int count) {
    return 'Sdílet s $count kontaktem';
  }

  @override
  String shareWithContactsCount(int count) {
    return 'Sdílet s $count kontakty';
  }

  @override
  String get contactsPermissionRequired => 'Vyžadováno oprávnění ke kontaktům';

  @override
  String get contactsPermissionRequiredForSms => 'Pro sdílení přes SMS je vyžadováno oprávnění ke kontaktům';

  @override
  String get grantContactsPermissionForSms => 'Pro sdílení přes SMS prosím udělte oprávnění ke kontaktům';

  @override
  String get noContactsWithPhoneNumbers => 'Nebyly nalezeny kontakty s telefonními čísly';

  @override
  String get noContactsMatchSearch => 'Žádné kontakty neodpovídají vašemu hledání';

  @override
  String get failedToLoadContacts => 'Nepodařilo se načíst kontakty';

  @override
  String get failedToPrepareConversationForSharing =>
      'Nepodařilo se připravit konverzaci ke sdílení. Zkuste to prosím znovu.';

  @override
  String get couldNotOpenSmsApp => 'Nepodařilo se otevřít aplikaci SMS. Zkuste to prosím znovu.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'Tady je to, o čem jsme mluvili: $link';
  }

  @override
  String get wifiSync => 'Synchronizace WiFi';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item zkopírováno do schránky';
  }

  @override
  String get wifiConnectionFailedTitle => 'Připojení selhalo';

  @override
  String connectingToDeviceName(String deviceName) {
    return 'Připojování k $deviceName';
  }

  @override
  String enableDeviceWifi(String deviceName) {
    return 'Povolit WiFi na $deviceName';
  }

  @override
  String connectToDeviceName(String deviceName) {
    return 'Připojit k $deviceName';
  }

  @override
  String get recordingDetails => 'Podrobnosti nahrávky';

  @override
  String get storageLocationSdCard => 'SD karta';

  @override
  String get storageLocationLimitlessPendant => 'Limitless Pendant';

  @override
  String get storageLocationPhone => 'Telefon';

  @override
  String get storageLocationPhoneMemory => 'Telefon (paměť)';

  @override
  String storedOnDevice(String deviceName) {
    return 'Uloženo na $deviceName';
  }

  @override
  String get transferring => 'Přenášení...';

  @override
  String get transferRequired => 'Vyžadován přenos';

  @override
  String get downloadingAudioFromSdCard => 'Stahování zvuku z SD karty vašeho zařízení';

  @override
  String get transferRequiredDescription =>
      'Tato nahrávka je uložena na SD kartě vašeho zařízení. Přeneste ji do telefonu pro přehrání.';

  @override
  String get cancelTransfer => 'Zrušit přenos';

  @override
  String get transferToPhone => 'Přenést do telefonu';

  @override
  String get privateAndSecureOnDevice => 'Soukromé a bezpečné na vašem zařízení';

  @override
  String get recordingInfo => 'Informace o nahrávce';

  @override
  String get transferInProgress => 'Probíhá přenos...';

  @override
  String get shareRecording => 'Sdílet nahrávku';

  @override
  String get deleteRecordingConfirmation => 'Opravdu chcete trvale smazat tuto nahrávku? Tuto akci nelze vrátit zpět.';

  @override
  String get recordingIdLabel => 'ID nahrávky';

  @override
  String get dateTimeLabel => 'Datum a čas';

  @override
  String get durationLabel => 'Délka';

  @override
  String get audioFormatLabel => 'Formát zvuku';

  @override
  String get storageLocationLabel => 'Umístění úložiště';

  @override
  String get estimatedSizeLabel => 'Odhadovaná velikost';

  @override
  String get deviceModelLabel => 'Model zařízení';

  @override
  String get deviceIdLabel => 'ID zařízení';

  @override
  String get statusLabel => 'Stav';

  @override
  String get statusProcessed => 'Zpracováno';

  @override
  String get statusUnprocessed => 'Nezpracováno';

  @override
  String get switchedToFastTransfer => 'Přepnuto na rychlý přenos';

  @override
  String get transferCompleteMessage => 'Přenos dokončen! Nyní můžete tuto nahrávku přehrát.';

  @override
  String transferFailedMessage(String error) {
    return 'Přenos selhal: $error';
  }

  @override
  String get transferCancelled => 'Přenos zrušen';

  @override
  String get fastTransferEnabled => 'Rychlý přenos povolen';

  @override
  String get bluetoothSyncEnabled => 'Synchronizace Bluetooth povolena';

  @override
  String get enableFastTransfer => 'Povolit rychlý přenos';

  @override
  String get fastTransferDescription =>
      'Rychlý přenos používá WiFi pro ~5x rychlejší přenosy. Váš telefon se dočasně připojí k WiFi síti zařízení Omi během přenosu.';

  @override
  String get internetAccessPausedDuringTransfer => 'Přístup k internetu je během přenosu pozastaven';

  @override
  String get chooseTransferMethodDescription => 'Zvolte, jak se nahrávky přenášejí ze zařízení Omi do telefonu.';

  @override
  String get wifiSpeed => '~150 KB/s přes WiFi';

  @override
  String get fiveTimesFaster => '5X RYCHLEJŠÍ';

  @override
  String get fastTransferMethodDescription =>
      'Vytvoří přímé WiFi připojení k zařízení Omi. Telefon se dočasně odpojí od běžné WiFi během přenosu.';

  @override
  String get bluetooth => 'Bluetooth';

  @override
  String get bleSpeed => '~30 KB/s přes BLE';

  @override
  String get bluetoothMethodDescription =>
      'Používá standardní Bluetooth Low Energy připojení. Pomalejší, ale neovlivňuje WiFi připojení.';

  @override
  String get selected => 'Vybráno';

  @override
  String get selectOption => 'Vybrat';

  @override
  String get lowBatteryAlertTitle => 'Upozornění na vybitou baterii';

  @override
  String get lowBatteryAlertBody => 'Baterie vašeho zařízení je vybitá. Je čas ji dobít! 🔋';

  @override
  String get deviceDisconnectedNotificationTitle => 'Vaše zařízení Omi bylo odpojeno';

  @override
  String get deviceDisconnectedNotificationBody =>
      'Prosím, znovu se připojte, abyste mohli pokračovat v používání Omi.';

  @override
  String get firmwareUpdateAvailable => 'K dispozici je aktualizace firmwaru';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'Pro vaše zařízení Omi je k dispozici nová aktualizace firmwaru ($version). Chcete aktualizovat nyní?';
  }

  @override
  String get later => 'Později';

  @override
  String get appDeletedSuccessfully => 'Aplikace byla úspěšně smazána';

  @override
  String get appDeleteFailed => 'Nepodařilo se smazat aplikaci. Zkuste to prosím později.';

  @override
  String get appVisibilityChangedSuccessfully =>
      'Viditelnost aplikace byla úspěšně změněna. Může to trvat několik minut.';

  @override
  String get errorActivatingAppIntegration =>
      'Chyba při aktivaci aplikace. Pokud jde o integrační aplikaci, ujistěte se, že je nastavení dokončeno.';

  @override
  String get errorUpdatingAppStatus => 'Při aktualizaci stavu aplikace došlo k chybě.';

  @override
  String get calculatingETA => 'Vypočítávám...';

  @override
  String aboutMinutesRemaining(int minutes) {
    return 'Zbývá přibližně $minutes minut';
  }

  @override
  String get aboutAMinuteRemaining => 'Zbývá přibližně minuta';

  @override
  String get almostDone => 'Téměř hotovo...';

  @override
  String get omiSays => 'Omi říká';

  @override
  String get analyzingYourData => 'Analyzuji vaše data...';

  @override
  String migratingToProtection(String level) {
    return 'Přecházení na ochranu $level...';
  }

  @override
  String get noDataToMigrateFinalizing => 'Žádná data k přenosu. Dokončování...';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return 'Přenášení $itemType... $percentage %';
  }

  @override
  String get allObjectsMigratedFinalizing => 'Všechny objekty přeneseny. Dokončování...';

  @override
  String get migrationErrorOccurred => 'Během přenosu došlo k chybě. Zkuste to prosím znovu.';

  @override
  String get migrationComplete => 'Přenos dokončen!';

  @override
  String dataProtectedWithSettings(String level) {
    return 'Vaše data jsou nyní chráněna novým nastavením $level.';
  }

  @override
  String get chatsLowercase => 'chaty';

  @override
  String get dataLowercase => 'data';

  @override
  String get fallNotificationTitle => 'Au';

  @override
  String get fallNotificationBody => 'Upadli jste?';

  @override
  String get importantConversationTitle => 'Důležitá konverzace';

  @override
  String get importantConversationBody => 'Právě jste měli důležitý rozhovor. Klepnutím sdílejte shrnutí s ostatními.';

  @override
  String get templateName => 'Název šablony';

  @override
  String get templateNameHint => 'např. Extraktor akcí ze schůzky';

  @override
  String get nameMustBeAtLeast3Characters => 'Název musí mít alespoň 3 znaky';

  @override
  String get conversationPromptHint =>
      'např. Extrahujte úkoly, přijatá rozhodnutí a klíčové poznatky z poskytnuté konverzace.';

  @override
  String get pleaseEnterAppPrompt => 'Zadejte prosím výzvu pro vaši aplikaci';

  @override
  String get promptMustBeAtLeast10Characters => 'Výzva musí mít alespoň 10 znaků';

  @override
  String get anyoneCanDiscoverTemplate => 'Kdokoli může objevit vaši šablonu';

  @override
  String get onlyYouCanUseTemplate => 'Pouze vy můžete používat tuto šablonu';

  @override
  String get generatingDescription => 'Generování popisu...';

  @override
  String get creatingAppIcon => 'Vytváření ikony aplikace...';

  @override
  String get installingApp => 'Instalace aplikace...';

  @override
  String get appCreatedAndInstalled => 'Aplikace vytvořena a nainstalována!';

  @override
  String get appCreatedSuccessfully => 'Aplikace úspěšně vytvořena!';

  @override
  String get failedToCreateApp => 'Nepodařilo se vytvořit aplikaci. Zkuste to prosím znovu.';

  @override
  String get addAppSelectCoreCapability => 'Vyberte další základní schopnost pro vaši aplikaci';

  @override
  String get addAppSelectPaymentPlan => 'Vyberte platební plán a zadejte cenu aplikace';

  @override
  String get addAppSelectCapability => 'Vyberte alespoň jednu schopnost pro vaši aplikaci';

  @override
  String get addAppSelectLogo => 'Vyberte logo pro vaši aplikaci';

  @override
  String get addAppEnterChatPrompt => 'Zadejte chatovou výzvu pro vaši aplikaci';

  @override
  String get addAppEnterConversationPrompt => 'Zadejte konverzační výzvu pro vaši aplikaci';

  @override
  String get addAppSelectTriggerEvent => 'Vyberte spouštěcí událost pro vaši aplikaci';

  @override
  String get addAppEnterWebhookUrl => 'Zadejte webhook URL pro vaši aplikaci';

  @override
  String get addAppSelectCategory => 'Vyberte kategorii pro vaši aplikaci';

  @override
  String get addAppFillRequiredFields => 'Vyplňte správně všechna povinná pole';

  @override
  String get addAppUpdatedSuccess => 'Aplikace úspěšně aktualizována 🚀';

  @override
  String get addAppUpdateFailed => 'Aktualizace se nezdařila. Zkuste to později';

  @override
  String get addAppSubmittedSuccess => 'Aplikace úspěšně odeslána 🚀';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'Chyba při otevírání výběru souborů: $message';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'Chyba při výběru obrázku: $error';
  }

  @override
  String get addAppPhotosPermissionDenied => 'Přístup k fotkám zamítnut. Povolte přístup k fotkám';

  @override
  String get addAppErrorSelectingImageRetry => 'Chyba při výběru obrázku. Zkuste to znovu.';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'Chyba při výběru náhledu: $error';
  }

  @override
  String get addAppErrorSelectingThumbnailRetry => 'Chyba při výběru náhledu. Zkuste to znovu.';

  @override
  String get addAppCapabilityConflictWithPersona => 'Jiné schopnosti nelze vybrat s Personou';

  @override
  String get addAppPersonaConflictWithCapabilities => 'Personu nelze vybrat s jinými schopnostmi';

  @override
  String get personaTwitterHandleNotFound => 'Twitter účet nenalezen';

  @override
  String get personaTwitterHandleSuspended => 'Twitter účet je pozastaven';

  @override
  String get personaFailedToVerifyTwitter => 'Ověření Twitter účtu se nezdařilo';

  @override
  String get personaFailedToFetch => 'Nepodařilo se načíst vaši personu';

  @override
  String get personaFailedToCreate => 'Nepodařilo se vytvořit personu';

  @override
  String get personaConnectKnowledgeSource => 'Připojte alespoň jeden zdroj dat (Omi nebo Twitter)';

  @override
  String get personaUpdatedSuccessfully => 'Persona úspěšně aktualizována';

  @override
  String get personaFailedToUpdate => 'Aktualizace persony se nezdařila';

  @override
  String get personaPleaseSelectImage => 'Vyberte obrázek';

  @override
  String get personaFailedToCreateTryLater => 'Vytvoření persony se nezdařilo. Zkuste to později.';

  @override
  String personaFailedToCreateWithError(String error) {
    return 'Vytvoření persony se nezdařilo: $error';
  }

  @override
  String get personaFailedToEnable => 'Aktivace persony se nezdařila';

  @override
  String personaErrorEnablingWithError(String error) {
    return 'Chyba při aktivaci persony: $error';
  }

  @override
  String get paymentFailedToFetchCountries => 'Nepodařilo se načíst podporované země. Zkuste to později.';

  @override
  String get paymentFailedToSetDefault => 'Nepodařilo se nastavit výchozí platební metodu. Zkuste to později.';

  @override
  String get paymentFailedToSavePaypal => 'Nepodařilo se uložit PayPal údaje. Zkuste to později.';

  @override
  String get paypalEmailHint => 'nik@example.com';

  @override
  String get paypalMeLinkHint => 'paypal.me/nik';

  @override
  String get paymentMethodStripe => 'Stripe';

  @override
  String get paymentMethodPayPal => 'PayPal';

  @override
  String get paymentStatusActive => 'Aktivní';

  @override
  String get paymentStatusConnected => 'Připojeno';

  @override
  String get paymentStatusNotConnected => 'Nepřipojeno';

  @override
  String get paymentAppCost => 'Cena aplikace';

  @override
  String get paymentEnterValidAmount => 'Zadejte platnou částku';

  @override
  String get paymentEnterAmountGreaterThanZero => 'Zadejte částku větší než 0';

  @override
  String get paymentPlan => 'Platební plán';

  @override
  String get paymentNoneSelected => 'Nic nevybráno';

  @override
  String get aiGenPleaseEnterDescription => 'Zadejte prosím popis vaší aplikace';

  @override
  String get aiGenCreatingAppIcon => 'Vytvářím ikonu aplikace...';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'Došlo k chybě: $message';
  }

  @override
  String get aiGenAppCreatedSuccessfully => 'Aplikace byla úspěšně vytvořena!';

  @override
  String get aiGenFailedToCreateApp => 'Nepodařilo se vytvořit aplikaci';

  @override
  String get aiGenErrorWhileCreatingApp => 'Při vytváření aplikace došlo k chybě';

  @override
  String get aiGenFailedToGenerateApp => 'Nepodařilo se vygenerovat aplikaci. Zkuste to prosím znovu.';

  @override
  String get aiGenFailedToRegenerateIcon => 'Nepodařilo se znovu vygenerovat ikonu';

  @override
  String get aiGenPleaseGenerateAppFirst => 'Nejprve prosím vygenerujte aplikaci';

  @override
  String get xHandleTitle => 'Jaký je váš X handle?';

  @override
  String get xHandleDescription => 'Předtrénujeme váš Omi klon\nna základě aktivity vašeho účtu';

  @override
  String get xHandleHint => '@nikshevchenko';

  @override
  String get xHandlePleaseEnter => 'Zadejte prosím svůj X handle';

  @override
  String get xHandlePleaseEnterValid => 'Zadejte prosím platný X handle';

  @override
  String get nextButton => 'Další';

  @override
  String get connectOmiDevice => 'Připojit zařízení Omi';

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'Měníte svůj plán Unlimited na $title. Opravdu chcete pokračovat?';
  }

  @override
  String get planUpgradeScheduledMessage =>
      'Upgrade naplánován! Váš měsíční plán pokračuje do konce fakturačního období.';

  @override
  String get couldNotSchedulePlanChange => 'Nepodařilo se naplánovat změnu plánu. Zkuste to prosím znovu.';

  @override
  String get subscriptionReactivatedDefault =>
      'Vaše předplatné bylo obnoveno! Nyní nebude účtován žádný poplatek - fakturováno bude na konci fakturačního období.';

  @override
  String get subscriptionSuccessfulCharged => 'Předplatné úspěšné! Byli jste účtováni za nové fakturační období.';

  @override
  String get couldNotProcessSubscription => 'Nepodařilo se zpracovat předplatné. Zkuste to prosím znovu.';

  @override
  String get couldNotLaunchUpgradePage => 'Nepodařilo se otevřít stránku upgradu. Zkuste to prosím znovu.';

  @override
  String get transcriptionJsonPlaceholder => 'Vložte sem svou JSON konfiguraci...';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get pricePlaceholder => '0,00';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'Chyba při otevírání výběru souborů: $message';
  }

  @override
  String importErrorGeneric(String error) {
    return 'Chyba: $error';
  }

  @override
  String get mergeConversationsSuccessTitle => 'Konverzace úspěšně sloučeny';

  @override
  String mergeConversationsSuccessBody(int count) {
    return '$count konverzací bylo úspěšně sloučeno';
  }

  @override
  String get dailyReflectionNotificationTitle => 'Čas na denní reflexi';

  @override
  String get dailyReflectionNotificationBody => 'Pověz mi o svém dni';

  @override
  String get actionItemReminderTitle => 'Připomínka Omi';

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName odpojeno';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'Prosím, znovu se připojte, abyste mohli pokračovat v používání vašeho $deviceName.';
  }

  @override
  String get onboardingSignIn => 'Přihlásit se';

  @override
  String get onboardingYourName => 'Vaše jméno';

  @override
  String get onboardingLanguage => 'Jazyk';

  @override
  String get onboardingPermissions => 'Oprávnění';

  @override
  String get onboardingComplete => 'Hotovo';

  @override
  String get onboardingWelcomeToOmi => 'Vítejte v Omi';

  @override
  String get onboardingTellUsAboutYourself => 'Řekněte nám o sobě';

  @override
  String get onboardingChooseYourPreference => 'Vyberte si preference';

  @override
  String get onboardingGrantRequiredAccess => 'Udělit požadovaný přístup';

  @override
  String get onboardingYoureAllSet => 'Vše je připraveno';

  @override
  String get searchTranscriptOrSummary => 'Hledat v přepisu nebo shrnutí...';

  @override
  String get myGoal => 'Můj cíl';

  @override
  String get appNotAvailable => 'Jejda! Zdá se, že aplikace, kterou hledáte, není k dispozici.';

  @override
  String get failedToConnectTodoist => 'Připojení k Todoist se nezdařilo';

  @override
  String get failedToConnectAsana => 'Připojení k Asana se nezdařilo';

  @override
  String get failedToConnectGoogleTasks => 'Připojení k Google Tasks se nezdařilo';

  @override
  String get failedToConnectClickUp => 'Připojení k ClickUp se nezdařilo';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return 'Připojení k $serviceName se nezdařilo: $error';
  }

  @override
  String get successfullyConnectedTodoist => 'Úspěšně připojeno k Todoist!';

  @override
  String get failedToConnectTodoistRetry => 'Připojení k Todoist se nezdařilo. Zkuste to prosím znovu.';

  @override
  String get successfullyConnectedAsana => 'Úspěšně připojeno k Asana!';

  @override
  String get failedToConnectAsanaRetry => 'Připojení k Asana se nezdařilo. Zkuste to prosím znovu.';

  @override
  String get successfullyConnectedGoogleTasks => 'Úspěšně připojeno k Google Tasks!';

  @override
  String get failedToConnectGoogleTasksRetry => 'Připojení k Google Tasks se nezdařilo. Zkuste to prosím znovu.';

  @override
  String get successfullyConnectedClickUp => 'Úspěšně připojeno k ClickUp!';

  @override
  String get failedToConnectClickUpRetry => 'Připojení k ClickUp se nezdařilo. Zkuste to prosím znovu.';

  @override
  String get successfullyConnectedNotion => 'Úspěšně připojeno k Notion!';

  @override
  String get failedToRefreshNotionStatus => 'Aktualizace stavu připojení Notion se nezdařila.';

  @override
  String get successfullyConnectedGoogle => 'Úspěšně připojeno k Google!';

  @override
  String get failedToRefreshGoogleStatus => 'Aktualizace stavu připojení Google se nezdařila.';

  @override
  String get successfullyConnectedWhoop => 'Úspěšně připojeno k Whoop!';

  @override
  String get failedToRefreshWhoopStatus => 'Aktualizace stavu připojení Whoop se nezdařila.';

  @override
  String get successfullyConnectedGitHub => 'Úspěšně připojeno k GitHub!';

  @override
  String get failedToRefreshGitHubStatus => 'Aktualizace stavu připojení GitHub se nezdařila.';

  @override
  String get authFailedToSignInWithGoogle => 'Přihlášení přes Google se nezdařilo, zkuste to prosím znovu.';

  @override
  String get authenticationFailed => 'Ověření se nezdařilo. Zkuste to prosím znovu.';

  @override
  String get authFailedToSignInWithApple => 'Přihlášení přes Apple se nezdařilo, zkuste to prosím znovu.';

  @override
  String get authFailedToRetrieveToken => 'Nepodařilo se získat Firebase token, zkuste to prosím znovu.';

  @override
  String get authUnexpectedErrorFirebase =>
      'Neočekávaná chyba při přihlašování, chyba Firebase, zkuste to prosím znovu.';

  @override
  String get authUnexpectedError => 'Neočekávaná chyba při přihlašování, zkuste to prosím znovu';

  @override
  String get authFailedToLinkGoogle => 'Propojení s Google se nezdařilo, zkuste to prosím znovu.';

  @override
  String get authFailedToLinkApple => 'Propojení s Apple se nezdařilo, zkuste to prosím znovu.';

  @override
  String get onboardingBluetoothRequired => 'K připojení k zařízení je vyžadováno oprávnění Bluetooth.';

  @override
  String get onboardingBluetoothDeniedSystemPrefs =>
      'Oprávnění Bluetooth bylo zamítnuto. Udělte prosím oprávnění v Předvolbách systému.';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'Stav oprávnění Bluetooth: $status. Zkontrolujte prosím Předvolby systému.';
  }

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'Nepodařilo se zkontrolovat oprávnění Bluetooth: $error';
  }

  @override
  String get onboardingNotificationDeniedSystemPrefs =>
      'Oprávnění pro oznámení bylo zamítnuto. Udělte prosím oprávnění v Předvolbách systému.';

  @override
  String get onboardingNotificationDeniedNotifications =>
      'Oprávnění pro oznámení bylo zamítnuto. Udělte prosím oprávnění v Předvolbách systému > Oznámení.';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return 'Stav oprávnění pro oznámení: $status. Zkontrolujte prosím Předvolby systému.';
  }

  @override
  String onboardingFailedCheckNotification(String error) {
    return 'Nepodařilo se zkontrolovat oprávnění pro oznámení: $error';
  }

  @override
  String get onboardingLocationGrantInSettings =>
      'Udělte prosím oprávnění k poloze v Nastavení > Soukromí a zabezpečení > Polohové služby';

  @override
  String get onboardingMicrophoneRequired => 'K nahrávání je vyžadováno oprávnění mikrofonu.';

  @override
  String get onboardingMicrophoneDenied =>
      'Oprávnění mikrofonu bylo zamítnuto. Udělte prosím oprávnění v Předvolbách systému > Soukromí a zabezpečení > Mikrofon.';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'Stav oprávnění mikrofonu: $status. Zkontrolujte prosím Předvolby systému.';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'Nepodařilo se zkontrolovat oprávnění mikrofonu: $error';
  }

  @override
  String get onboardingScreenCaptureRequired =>
      'K nahrávání systémového zvuku je vyžadováno oprávnění pro snímání obrazovky.';

  @override
  String get onboardingScreenCaptureDenied =>
      'Oprávnění pro snímání obrazovky bylo zamítnuto. Udělte prosím oprávnění v Předvolbách systému > Soukromí a zabezpečení > Nahrávání obrazovky.';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return 'Stav oprávnění pro snímání obrazovky: $status. Zkontrolujte prosím Předvolby systému.';
  }

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return 'Nepodařilo se zkontrolovat oprávnění pro snímání obrazovky: $error';
  }

  @override
  String get onboardingAccessibilityRequired => 'K detekci schůzek v prohlížeči je vyžadováno oprávnění přístupnosti.';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'Stav oprávnění přístupnosti: $status. Zkontrolujte prosím Předvolby systému.';
  }

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'Nepodařilo se zkontrolovat oprávnění přístupnosti: $error';
  }

  @override
  String get msgCameraNotAvailable => 'Snímání fotoaparátem není na této platformě k dispozici';

  @override
  String get msgCameraPermissionDenied =>
      'Oprávnění k fotoaparátu bylo zamítnuto. Povolte prosím přístup k fotoaparátu';

  @override
  String msgCameraAccessError(String error) {
    return 'Chyba při přístupu k fotoaparátu: $error';
  }

  @override
  String get msgPhotoError => 'Chyba při pořizování fotografie. Zkuste to prosím znovu.';

  @override
  String get msgMaxImagesLimit => 'Můžete vybrat maximálně 4 obrázky';

  @override
  String msgFilePickerError(String error) {
    return 'Chyba při otevírání výběru souborů: $error';
  }

  @override
  String msgSelectImagesError(String error) {
    return 'Chyba při výběru obrázků: $error';
  }

  @override
  String get msgPhotosPermissionDenied =>
      'Oprávnění k fotografiím bylo zamítnuto. Povolte prosím přístup k fotografiím pro výběr obrázků';

  @override
  String get msgSelectImagesGenericError => 'Chyba při výběru obrázků. Zkuste to prosím znovu.';

  @override
  String get msgMaxFilesLimit => 'Můžete vybrat maximálně 4 soubory';

  @override
  String msgSelectFilesError(String error) {
    return 'Chyba při výběru souborů: $error';
  }

  @override
  String get msgSelectFilesGenericError => 'Chyba při výběru souborů. Zkuste to prosím znovu.';

  @override
  String get msgUploadFileFailed => 'Nahrávání souboru se nezdařilo, zkuste to prosím později';

  @override
  String get msgReadingMemories => 'Čtení vašich vzpomínek...';

  @override
  String get msgLearningMemories => 'Učení se z vašich vzpomínek...';

  @override
  String get msgUploadAttachedFileFailed => 'Nahrání přiloženého souboru se nezdařilo.';

  @override
  String captureRecordingError(String error) {
    return 'Při nahrávání došlo k chybě: $error';
  }

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return 'Nahrávání zastaveno: $reason. Možná budete muset znovu připojit externí displeje nebo restartovat nahrávání.';
  }

  @override
  String get captureMicrophonePermissionRequired => 'Vyžadováno oprávnění k mikrofonu';

  @override
  String get captureMicrophonePermissionInSystemPreferences => 'Udělte oprávnění k mikrofonu v Předvolbách systému';

  @override
  String get captureScreenRecordingPermissionRequired => 'Vyžadováno oprávnění k nahrávání obrazovky';

  @override
  String get captureDisplayDetectionFailed => 'Detekce displeje selhala. Nahrávání zastaveno.';

  @override
  String get devModeInvalidAudioBytesWebhookUrl => 'Neplatná URL adresa webhooku pro audio bajty';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl => 'Neplatná URL adresa webhooku pro přepis v reálném čase';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl => 'Neplatná URL adresa webhooku pro vytvořenou konverzaci';

  @override
  String get devModeInvalidDaySummaryWebhookUrl => 'Neplatná URL adresa webhooku pro denní shrnutí';

  @override
  String get devModeSettingsSaved => 'Nastavení uloženo!';

  @override
  String get voiceFailedToTranscribe => 'Nepodařilo se přepsat zvuk';

  @override
  String get locationPermissionRequired => 'Vyžadováno oprávnění k poloze';

  @override
  String get locationPermissionContent =>
      'Rychlý přenos vyžaduje oprávnění k poloze pro ověření WiFi připojení. Prosím, udělte oprávnění k poloze pro pokračování.';

  @override
  String get pdfTranscriptExport => 'Export přepisu';

  @override
  String get pdfConversationExport => 'Export konverzace';

  @override
  String pdfTitleLabel(String title) {
    return 'Název: $title';
  }

  @override
  String get conversationNewIndicator => 'Nové 🚀';

  @override
  String conversationPhotosCount(int count) {
    return '$count fotek';
  }

  @override
  String get mergingStatus => 'Slučování...';

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
    return '$count hodina';
  }

  @override
  String timeHoursPlural(int count) {
    return '$count hodin';
  }

  @override
  String timeHoursAndMins(int hours, int mins) {
    return '$hours hodin $mins min';
  }

  @override
  String timeDaySingular(int count) {
    return '$count den';
  }

  @override
  String timeDaysPlural(int count) {
    return '$count dní';
  }

  @override
  String timeDaysAndHours(int days, int hours) {
    return '$days dní $hours hodin';
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
    return '${count}h';
  }

  @override
  String timeCompactHoursAndMins(int hours, int mins) {
    return '${hours}h ${mins}m';
  }

  @override
  String get moveToFolder => 'Přesunout do složky';

  @override
  String get noFoldersAvailable => 'Žádné složky nejsou k dispozici';

  @override
  String get newFolder => 'Nová složka';

  @override
  String get color => 'Barva';

  @override
  String get waitingForDevice => 'Čekání na zařízení...';

  @override
  String get saySomething => 'Řekněte něco...';

  @override
  String get initialisingSystemAudio => 'Inicializace systémového zvuku';

  @override
  String get stopRecording => 'Zastavit nahrávání';

  @override
  String get continueRecording => 'Pokračovat v nahrávání';

  @override
  String get initialisingRecorder => 'Inicializace záznamníku';

  @override
  String get pauseRecording => 'Pozastavit nahrávání';

  @override
  String get resumeRecording => 'Obnovit nahrávání';

  @override
  String get noDailyRecapsYet => 'Zatím žádné denní přehledy';

  @override
  String get dailyRecapsDescription => 'Vaše denní přehledy se zde zobrazí po vygenerování';

  @override
  String get chooseTransferMethod => 'Vyberte metodu přenosu';

  @override
  String get fastTransferSpeed => '~150 KB/s přes WiFi';

  @override
  String largeTimeGapDetected(String gap) {
    return 'Zjištěna velká časová mezera ($gap)';
  }

  @override
  String largeTimeGapsDetected(String gaps) {
    return 'Zjištěny velké časové mezery ($gaps)';
  }

  @override
  String get deviceDoesNotSupportWifiSwitchingToBle =>
      'Zařízení nepodporuje WiFi synchronizaci, přepínání na Bluetooth';

  @override
  String get appleHealthNotAvailable => 'Apple Health není na tomto zařízení k dispozici';

  @override
  String get downloadAudio => 'Stáhnout zvuk';

  @override
  String get audioDownloadSuccess => 'Zvuk byl úspěšně stažen';

  @override
  String get audioDownloadFailed => 'Stažení zvuku se nezdařilo';

  @override
  String get downloadingAudio => 'Stahování zvuku...';

  @override
  String get shareAudio => 'Sdílet zvuk';

  @override
  String get preparingAudio => 'Příprava zvuku';

  @override
  String get gettingAudioFiles => 'Získávání zvukových souborů...';

  @override
  String get downloadingAudioProgress => 'Stahování zvuku';

  @override
  String get processingAudio => 'Zpracování zvuku';

  @override
  String get combiningAudioFiles => 'Kombinování zvukových souborů...';

  @override
  String get audioReady => 'Zvuk je připraven';

  @override
  String get openingShareSheet => 'Otevírání listu sdílení...';

  @override
  String get audioShareFailed => 'Sdílení se nezdařilo';

  @override
  String get dailyRecaps => 'Denní Souhrny';

  @override
  String get removeFilter => 'Odstranit Filtr';

  @override
  String get categoryConversationAnalysis => 'Analýza konverzací';

  @override
  String get categoryPersonalityClone => 'Klon osobnosti';

  @override
  String get categoryHealth => 'Zdraví';

  @override
  String get categoryEducation => 'Vzdělávání';

  @override
  String get categoryCommunication => 'Komunikace';

  @override
  String get categoryEmotionalSupport => 'Emoční podpora';

  @override
  String get categoryProductivity => 'Produktivita';

  @override
  String get categoryEntertainment => 'Zábava';

  @override
  String get categoryFinancial => 'Finance';

  @override
  String get categoryTravel => 'Cestování';

  @override
  String get categorySafety => 'Bezpečnost';

  @override
  String get categoryShopping => 'Nakupování';

  @override
  String get categorySocial => 'Sociální';

  @override
  String get categoryNews => 'Zprávy';

  @override
  String get categoryUtilities => 'Nástroje';

  @override
  String get categoryOther => 'Ostatní';

  @override
  String get capabilityChat => 'Chat';

  @override
  String get capabilityConversations => 'Konverzace';

  @override
  String get capabilityExternalIntegration => 'Externí integrace';

  @override
  String get capabilityNotification => 'Oznámení';

  @override
  String get triggerAudioBytes => 'Audio bajty';

  @override
  String get triggerConversationCreation => 'Vytvoření konverzace';

  @override
  String get triggerTranscriptProcessed => 'Přepis zpracován';

  @override
  String get actionCreateConversations => 'Vytvořit konverzace';

  @override
  String get actionCreateMemories => 'Vytvořit vzpomínky';

  @override
  String get actionReadConversations => 'Číst konverzace';

  @override
  String get actionReadMemories => 'Číst vzpomínky';

  @override
  String get actionReadTasks => 'Číst úkoly';

  @override
  String get scopeUserName => 'Uživatelské jméno';

  @override
  String get scopeUserFacts => 'Fakta o uživateli';

  @override
  String get scopeUserConversations => 'Konverzace uživatele';

  @override
  String get scopeUserChat => 'Chat uživatele';

  @override
  String get capabilitySummary => 'Souhrn';

  @override
  String get capabilityFeatured => 'Doporučené';

  @override
  String get capabilityTasks => 'Úkoly';

  @override
  String get capabilityIntegrations => 'Integrace';

  @override
  String get categoryPersonalityClones => 'Klony osobností';

  @override
  String get categoryProductivityLifestyle => 'Produktivita a životní styl';

  @override
  String get categorySocialEntertainment => 'Sociální a zábava';

  @override
  String get categoryProductivityTools => 'Nástroje produktivity';

  @override
  String get categoryPersonalWellness => 'Osobní pohoda';

  @override
  String get rating => 'Hodnocení';

  @override
  String get categories => 'Kategorie';

  @override
  String get sortBy => 'Řadit';

  @override
  String get highestRating => 'Nejvyšší hodnocení';

  @override
  String get lowestRating => 'Nejnižší hodnocení';

  @override
  String get resetFilters => 'Resetovat filtry';

  @override
  String get applyFilters => 'Použít filtry';

  @override
  String get mostInstalls => 'Nejvíce instalací';

  @override
  String get couldNotOpenUrl => 'Nepodařilo se otevřít URL. Zkuste to prosím znovu.';

  @override
  String get newTask => 'Nový úkol';

  @override
  String get viewAll => 'Zobrazit vše';

  @override
  String get addTask => 'Přidat úkol';

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
  String get audioPlaybackUnavailable => 'Zvukový soubor není k dispozici pro přehrávání';

  @override
  String get audioPlaybackFailed => 'Nelze přehrát zvuk. Soubor může být poškozený nebo chybět.';

  @override
  String get connectionGuide => 'Průvodce připojením';

  @override
  String get iveDoneThis => 'Hotovo';

  @override
  String get pairNewDevice => 'Spárovat nové zařízení';

  @override
  String get dontSeeYourDevice => 'Nevidíte své zařízení?';

  @override
  String get reportAnIssue => 'Nahlásit problém';

  @override
  String get pairingTitleOmi => 'Zapněte Omi';

  @override
  String get pairingDescOmi => 'Stiskněte a podržte zařízení, dokud nezavibruje, pro zapnutí.';

  @override
  String get pairingTitleOmiDevkit => 'Přepněte Omi DevKit do režimu párování';

  @override
  String get pairingDescOmiDevkit =>
      'Stiskněte tlačítko jednou pro zapnutí. LED bude blikat fialově v režimu párování.';

  @override
  String get pairingTitleOmiGlass => 'Zapněte Omi Glass';

  @override
  String get pairingDescOmiGlass => 'Stiskněte a podržte boční tlačítko po dobu 3 sekund pro zapnutí.';

  @override
  String get pairingTitlePlaudNote => 'Přepněte Plaud Note do režimu párování';

  @override
  String get pairingDescPlaudNote =>
      'Stiskněte a podržte boční tlačítko po dobu 2 sekund. Červená LED bude blikat, když je připraveno k párování.';

  @override
  String get pairingTitleBee => 'Přepněte Bee do režimu párování';

  @override
  String get pairingDescBee => 'Stiskněte tlačítko 5krát za sebou. Kontrolka začne blikat modře a zeleně.';

  @override
  String get pairingTitleLimitless => 'Přepněte Limitless do režimu párování';

  @override
  String get pairingDescLimitless =>
      'Když svítí jakýkoli indikátor, stiskněte jednou a poté stiskněte a podržte, dokud zařízení neukáže růžové světlo, poté uvolněte.';

  @override
  String get pairingTitleFriendPendant => 'Přepněte Friend Pendant do režimu párování';

  @override
  String get pairingDescFriendPendant =>
      'Stiskněte tlačítko na přívěsku pro zapnutí. Automaticky přejde do režimu párování.';

  @override
  String get pairingTitleFieldy => 'Přepněte Fieldy do režimu párování';

  @override
  String get pairingDescFieldy => 'Stiskněte a podržte zařízení, dokud se nerozsvítí kontrolka pro zapnutí.';

  @override
  String get pairingTitleAppleWatch => 'Připojte Apple Watch';

  @override
  String get pairingDescAppleWatch =>
      'Nainstalujte a otevřete aplikaci Omi na Apple Watch, poté klepněte na Připojit v aplikaci.';

  @override
  String get pairingTitleNeoOne => 'Přepněte Neo One do režimu párování';

  @override
  String get pairingDescNeoOne =>
      'Stiskněte a podržte tlačítko napájení, dokud LED nezabliká. Zařízení bude viditelné.';
}
