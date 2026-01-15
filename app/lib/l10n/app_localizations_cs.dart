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
  String get ok => 'Ok';

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
  String get noInternetConnection => 'Zkontrolujte prosím připojení k internetu a zkuste to znovu.';

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
  String get speechProfile => 'Hlasový profil';

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
  String get searching => 'Vyhledávání';

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
  String get noConversationsYet => 'Zatím žádné konverzace.';

  @override
  String get noStarredConversations => 'Zatím žádné oblíbené konverzace.';

  @override
  String get starConversationHint =>
      'Chcete-li konverzaci označit hvězdičkou, otevřete ji a klepněte na ikonu hvězdičky v záhlaví.';

  @override
  String get searchConversations => 'Hledat konverzace';

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
  String get messageCopied => 'Zpráva zkopírována do schránky.';

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
  String get clearChat => 'Vymazat chat?';

  @override
  String get clearChatConfirm => 'Opravdu chcete vymazat chat? Tuto akci nelze vrátit zpět.';

  @override
  String get maxFilesLimit => 'Najednou můžete nahrát pouze 4 soubory';

  @override
  String get chatWithOmi => 'Chat s Omi';

  @override
  String get apps => 'Aplikace';

  @override
  String get noAppsFound => 'Nenalezeny žádné aplikace';

  @override
  String get tryAdjustingSearch => 'Zkuste upravit vyhledávání nebo filtry';

  @override
  String get createYourOwnApp => 'Vytvořte vlastní aplikaci';

  @override
  String get buildAndShareApp => 'Vytvořte a sdílejte vlastní aplikaci';

  @override
  String get searchApps => 'Hledat v 1500+ aplikacích';

  @override
  String get myApps => 'Moje aplikace';

  @override
  String get installedApps => 'Nainstalované aplikace';

  @override
  String get unableToFetchApps =>
      'Nelze načíst aplikace :(\n\nZkontrolujte prosím připojení k internetu a zkuste to znovu.';

  @override
  String get aboutOmi => 'O aplikaci Omi';

  @override
  String get privacyPolicy => 'Zásadami ochrany osobních údajů';

  @override
  String get visitWebsite => 'Navštívit webové stránky';

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
  String get customVocabulary => 'Vlastní slovník';

  @override
  String get identifyingOthers => 'Identifikace ostatních';

  @override
  String get paymentMethods => 'Platební metody';

  @override
  String get conversationDisplay => 'Zobrazení konverzace';

  @override
  String get dataPrivacy => 'Data a soukromí';

  @override
  String get userId => 'ID uživatele';

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
  String get chatTools => 'Nástroje chatu';

  @override
  String get feedbackBug => 'Zpětná vazba / Chyba';

  @override
  String get helpCenter => 'Centrum nápovědy';

  @override
  String get developerSettings => 'Nastavení pro vývojáře';

  @override
  String get getOmiForMac => 'Získat Omi pro Mac';

  @override
  String get referralProgram => 'Doporučovací program';

  @override
  String get signOut => 'Odhlásit se';

  @override
  String get appAndDeviceCopied => 'Podrobnosti o aplikaci a zařízení zkopírovány';

  @override
  String get wrapped2025 => 'Wrapped 2025';

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
  String get off => 'Vypnuto';

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
  String get createKey => 'Vytvořit klíč';

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
  String get upgradeToUnlimited => 'Upgradovat na neomezený';

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
  String get noLogFilesFound => 'Nenalezeny žádné soubory protokolu.';

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
  String get knowledgeGraphDeleted => 'Graf znalostí úspěšně smazán';

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
  String get insights => 'Přehledy';

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
  String get connect => 'Připojit';

  @override
  String get comingSoon => 'Již brzy';

  @override
  String get chatToolsFooter => 'Připojte své aplikace k zobrazení dat a metrik v chatu.';

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
  String get primaryLanguage => 'Primární jazyk';

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
  String get noUpcomingMeetings => 'Nenalezeny žádné nadcházející schůzky';

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
  String get noLanguagesFound => 'Nenalezeny žádné jazyky';

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
  String get yesterday => 'včera';

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
  String get host => 'Host';

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
  String deviceUsesCodec(String deviceName, String codecReason) {
    return '$deviceName používá $codecReason. Bude použito Omi.';
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
  String get resetToDefault => 'Obnovit na výchozí';

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
  String get appName => 'Název aplikace';

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
  String get dontShowAgain => 'Už nezobrazovat';

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
  String get deleteActionItemMessage => 'Opravdu chcete smazat tento úkol?';

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
  String searchMemories(int count) {
    return 'Hledat ve $count vzpomínkách';
  }

  @override
  String get memoryDeleted => 'Vzpomínka smazána.';

  @override
  String get undo => 'Vrátit zpět';

  @override
  String get noMemoriesYet => 'Zatím žádné vzpomínky';

  @override
  String get noAutoMemories => 'Zatím žádné automaticky extrahované vzpomínky';

  @override
  String get noManualMemories => 'Zatím žádné manuální vzpomínky';

  @override
  String get noMemoriesInCategories => 'Žádné vzpomínky v těchto kategoriích';

  @override
  String get noMemoriesFound => 'Nenalezeny žádné vzpomínky';

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
  String get newMemory => 'Nová vzpomínka';

  @override
  String get editMemory => 'Upravit vzpomínku';

  @override
  String get memoryContentHint => 'Rád/a jím zmrzlinu...';

  @override
  String get failedToSaveMemory => 'Uložení se nezdařilo. Zkontrolujte prosím připojení.';

  @override
  String get saveMemory => 'Uložit vzpomínku';

  @override
  String get retry => 'Zkusit znovu';

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
  String get failedToUpdateActionItem => 'Aktualizace úkolu se nezdařila';

  @override
  String get actionItemCreated => 'Úkol vytvořen';

  @override
  String get failedToCreateActionItem => 'Vytvoření úkolu se nezdařilo';

  @override
  String get dueDate => 'Termín dokončení';

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
  String get failedToDeleteActionItem => 'Smazání úkolu se nezdařilo';

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
}
