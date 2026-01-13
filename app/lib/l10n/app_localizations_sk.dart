// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Slovak (`sk`).
class AppLocalizationsSk extends AppLocalizations {
  AppLocalizationsSk([String locale = 'sk']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'Konverzácia';

  @override
  String get transcriptTab => 'Prepis';

  @override
  String get actionItemsTab => 'Úlohy';

  @override
  String get deleteConversationTitle => 'Odstrániť konverzáciu?';

  @override
  String get deleteConversationMessage =>
      'Naozaj chcete odstrániť túto konverzáciu? Túto akciu nie je možné vrátiť späť.';

  @override
  String get confirm => 'Potvrdiť';

  @override
  String get cancel => 'Zrušiť';

  @override
  String get ok => 'Ok';

  @override
  String get delete => 'Odstrániť';

  @override
  String get add => 'Pridať';

  @override
  String get update => 'Aktualizovať';

  @override
  String get save => 'Uložiť';

  @override
  String get edit => 'Upraviť';

  @override
  String get close => 'Zavrieť';

  @override
  String get clear => 'Vymazať';

  @override
  String get copyTranscript => 'Skopírovať prepis';

  @override
  String get copySummary => 'Skopírovať zhrnutie';

  @override
  String get testPrompt => 'Otestovať výzvu';

  @override
  String get reprocessConversation => 'Znovu spracovať konverzáciu';

  @override
  String get deleteConversation => 'Odstrániť konverzáciu';

  @override
  String get contentCopied => 'Obsah bol skopírovaný do schránky';

  @override
  String get failedToUpdateStarred => 'Nepodarilo sa aktualizovať stav obľúbenej.';

  @override
  String get conversationUrlNotShared => 'URL konverzácie sa nepodarilo zdieľať.';

  @override
  String get errorProcessingConversation => 'Chyba pri spracovaní konverzácie. Skúste to prosím neskôr.';

  @override
  String get noInternetConnection => 'Skontrolujte prosím svoje internetové pripojenie a skúste to znova.';

  @override
  String get unableToDeleteConversation => 'Nepodarilo sa odstrániť konverzáciu';

  @override
  String get somethingWentWrong => 'Niečo sa pokazilo! Skúste to prosím neskôr.';

  @override
  String get copyErrorMessage => 'Skopírovať chybovú správu';

  @override
  String get errorCopied => 'Chybová správa bola skopírovaná do schránky';

  @override
  String get remaining => 'Zostáva';

  @override
  String get loading => 'Načítava sa...';

  @override
  String get loadingDuration => 'Načítava sa trvanie...';

  @override
  String secondsCount(int count) {
    return '$count sekúnd';
  }

  @override
  String get people => 'Ľudia';

  @override
  String get addNewPerson => 'Pridať novú osobu';

  @override
  String get editPerson => 'Upraviť osobu';

  @override
  String get createPersonHint => 'Vytvorte novú osobu a naučte Omi rozpoznávať aj jej hlas!';

  @override
  String get speechProfile => 'Hlasový profil';

  @override
  String sampleNumber(int number) {
    return 'Vzorka $number';
  }

  @override
  String get settings => 'Nastavenia';

  @override
  String get language => 'Jazyk';

  @override
  String get selectLanguage => 'Vyberte jazyk';

  @override
  String get deleting => 'Odstraňuje sa...';

  @override
  String get pleaseCompleteAuthentication =>
      'Dokončite prosím autentifikáciu vo vašom prehliadači. Po dokončení sa vráťte do aplikácie.';

  @override
  String get failedToStartAuthentication => 'Nepodarilo sa spustiť autentifikáciu';

  @override
  String get importStarted => 'Import bol spustený! Budete upozornení, keď bude dokončený.';

  @override
  String get failedToStartImport => 'Nepodarilo sa spustiť import. Skúste to prosím znova.';

  @override
  String get couldNotAccessFile => 'Nepodarilo sa pristúpiť k vybranému súboru';

  @override
  String get askOmi => 'Spýtať sa Omi';

  @override
  String get done => 'Hotovo';

  @override
  String get disconnected => 'Odpojené';

  @override
  String get searching => 'Vyhľadáva sa';

  @override
  String get connectDevice => 'Pripojiť zariadenie';

  @override
  String get monthlyLimitReached => 'Dosiahli ste váš mesačný limit.';

  @override
  String get checkUsage => 'Skontrolovať využitie';

  @override
  String get syncingRecordings => 'Synchronizujú sa nahrávky';

  @override
  String get recordingsToSync => 'Nahrávky na synchronizáciu';

  @override
  String get allCaughtUp => 'Všetko je aktuálne';

  @override
  String get sync => 'Synchronizovať';

  @override
  String get pendantUpToDate => 'Prívesok je aktuálny';

  @override
  String get allRecordingsSynced => 'Všetky nahrávky sú synchronizované';

  @override
  String get syncingInProgress => 'Prebieha synchronizácia';

  @override
  String get readyToSync => 'Pripravené na synchronizáciu';

  @override
  String get tapSyncToStart => 'Ťuknite na Synchronizovať pre spustenie';

  @override
  String get pendantNotConnected => 'Prívesok nie je pripojený. Pripojte ho pre synchronizáciu.';

  @override
  String get everythingSynced => 'Všetko je už synchronizované.';

  @override
  String get recordingsNotSynced => 'Máte nahrávky, ktoré ešte nie sú synchronizované.';

  @override
  String get syncingBackground => 'Budeme naďalej synchronizovať vaše nahrávky na pozadí.';

  @override
  String get noConversationsYet => 'Zatiaľ žiadne konverzácie.';

  @override
  String get noStarredConversations => 'Zatiaľ žiadne obľúbené konverzácie.';

  @override
  String get starConversationHint =>
      'Ak chcete označiť konverzáciu hviezdičkou, otvorte ju a ťuknite na ikonu hviezdy v hlavičke.';

  @override
  String get searchConversations => 'Hľadať konverzácie';

  @override
  String selectedCount(int count, Object s) {
    return '$count vybraných';
  }

  @override
  String get merge => 'Zlúčiť';

  @override
  String get mergeConversations => 'Zlúčiť konverzácie';

  @override
  String mergeConversationsMessage(int count) {
    return 'Toto zlúči $count konverzácií do jednej. Celý obsah bude zlúčený a znovu vygenerovaný.';
  }

  @override
  String get mergingInBackground => 'Zlučovanie prebieha na pozadí. Môže to chvíľu trvať.';

  @override
  String get failedToStartMerge => 'Nepodarilo sa spustiť zlučovanie';

  @override
  String get askAnything => 'Spýtajte sa na čokoľvek';

  @override
  String get noMessagesYet => 'Zatiaľ žiadne správy!\nPrečo nespustíte konverzáciu?';

  @override
  String get deletingMessages => 'Odstraňujú sa vaše správy z pamäte Omi...';

  @override
  String get messageCopied => 'Správa bola skopírovaná do schránky.';

  @override
  String get cannotReportOwnMessage => 'Nemôžete nahlásiť vlastné správy.';

  @override
  String get reportMessage => 'Nahlásiť správu';

  @override
  String get reportMessageConfirm => 'Naozaj chcete nahlásiť túto správu?';

  @override
  String get messageReported => 'Správa bola úspešne nahlásená.';

  @override
  String get thankYouFeedback => 'Ďakujeme za vašu spätnú väzbu!';

  @override
  String get clearChat => 'Vymazať chat?';

  @override
  String get clearChatConfirm => 'Naozaj chcete vymazať chat? Túto akciu nie je možné vrátiť späť.';

  @override
  String get maxFilesLimit => 'Môžete nahrať maximálne 4 súbory naraz';

  @override
  String get chatWithOmi => 'Chat s Omi';

  @override
  String get apps => 'Aplikácie';

  @override
  String get noAppsFound => 'Neboli nájdené žiadne aplikácie';

  @override
  String get tryAdjustingSearch => 'Skúste upraviť vyhľadávanie alebo filtre';

  @override
  String get createYourOwnApp => 'Vytvorte si vlastnú aplikáciu';

  @override
  String get buildAndShareApp => 'Vytvorte a zdieľajte vlastnú aplikáciu';

  @override
  String get searchApps => 'Hľadať v 1500+ aplikáciách';

  @override
  String get myApps => 'Moje aplikácie';

  @override
  String get installedApps => 'Nainštalované aplikácie';

  @override
  String get unableToFetchApps =>
      'Nepodarilo sa načítať aplikácie :(\n\nSkontrolujte prosím svoje internetové pripojenie a skúste to znova.';

  @override
  String get aboutOmi => 'O aplikácii Omi';

  @override
  String get privacyPolicy => 'Zásady ochrany osobných údajov';

  @override
  String get visitWebsite => 'Navštíviť webovú stránku';

  @override
  String get helpOrInquiries => 'Pomoc alebo otázky?';

  @override
  String get joinCommunity => 'Pridajte sa ku komunite!';

  @override
  String get membersAndCounting => 'Viac ako 8000 členov a stále pribúdajú.';

  @override
  String get deleteAccountTitle => 'Odstrániť účet';

  @override
  String get deleteAccountConfirm => 'Naozaj chcete odstrániť svoj účet?';

  @override
  String get cannotBeUndone => 'Túto akciu nie je možné vrátiť späť.';

  @override
  String get allDataErased => 'Všetky vaše spomienky a konverzácie budú natrvalo odstránené.';

  @override
  String get appsDisconnected => 'Vaše aplikácie a integrácie budú okamžite odpojené.';

  @override
  String get exportBeforeDelete =>
      'Pred odstránením účtu môžete exportovať svoje údaje, ale po odstránení ich nebude možné obnoviť.';

  @override
  String get deleteAccountCheckbox =>
      'Rozumiem, že odstránenie môjho účtu je trvalé a všetky údaje vrátane spomienok a konverzácií budú stratené a nebude ich možné obnoviť.';

  @override
  String get areYouSure => 'Ste si istí?';

  @override
  String get deleteAccountFinal =>
      'Táto akcia je nezvratná a natrvalo odstráni váš účet a všetky súvisiace údaje. Naozaj chcete pokračovať?';

  @override
  String get deleteNow => 'Odstrániť teraz';

  @override
  String get goBack => 'Vrátiť sa';

  @override
  String get checkBoxToConfirm =>
      'Začiarknite políčko na potvrdenie, že rozumiete, že odstránenie vášho účtu je trvalé a nezvratné.';

  @override
  String get profile => 'Profil';

  @override
  String get name => 'Meno';

  @override
  String get email => 'E-mail';

  @override
  String get customVocabulary => 'Vlastný slovník';

  @override
  String get identifyingOthers => 'Identifikácia ostatných';

  @override
  String get paymentMethods => 'Platobné metódy';

  @override
  String get conversationDisplay => 'Zobrazenie konverzácií';

  @override
  String get dataPrivacy => 'Údaje a súkromie';

  @override
  String get userId => 'ID používateľa';

  @override
  String get notSet => 'Nie je nastavené';

  @override
  String get userIdCopied => 'ID používateľa bolo skopírované do schránky';

  @override
  String get systemDefault => 'Predvolené nastavenie systému';

  @override
  String get planAndUsage => 'Plán a využitie';

  @override
  String get offlineSync => 'Offline synchronizácia';

  @override
  String get deviceSettings => 'Nastavenia zariadenia';

  @override
  String get chatTools => 'Nástroje chatu';

  @override
  String get feedbackBug => 'Spätná väzba / chyba';

  @override
  String get helpCenter => 'Centrum pomoci';

  @override
  String get developerSettings => 'Vývojárske nastavenia';

  @override
  String get getOmiForMac => 'Získať Omi pre Mac';

  @override
  String get referralProgram => 'Odporúčací program';

  @override
  String get signOut => 'Odhlásiť sa';

  @override
  String get appAndDeviceCopied => 'Podrobnosti o aplikácii a zariadení boli skopírované';

  @override
  String get wrapped2025 => 'Wrapped 2025';

  @override
  String get yourPrivacyYourControl => 'Vaše súkromie, vaša kontrola';

  @override
  String get privacyIntro =>
      'V Omi sa zaväzujeme chrániť vaše súkromie. Táto stránka vám umožňuje kontrolovať, ako sú vaše údaje ukladané a používané.';

  @override
  String get learnMore => 'Dozvedieť sa viac...';

  @override
  String get dataProtectionLevel => 'Úroveň ochrany údajov';

  @override
  String get dataProtectionDesc =>
      'Vaše údaje sú predvolene zabezpečené silným šifrovaním. Skontrolujte svoje nastavenia a budúce možnosti ochrany súkromia nižšie.';

  @override
  String get appAccess => 'Prístup aplikácií';

  @override
  String get appAccessDesc =>
      'Nasledujúce aplikácie majú prístup k vašim údajom. Ťuknutím na aplikáciu spravujte jej oprávnenia.';

  @override
  String get noAppsExternalAccess => 'Žiadne nainštalované aplikácie nemajú externý prístup k vašim údajom.';

  @override
  String get deviceName => 'Názov zariadenia';

  @override
  String get deviceId => 'ID zariadenia';

  @override
  String get firmware => 'Firmvér';

  @override
  String get sdCardSync => 'Synchronizácia SD karty';

  @override
  String get hardwareRevision => 'Revízia hardvéru';

  @override
  String get modelNumber => 'Číslo modelu';

  @override
  String get manufacturer => 'Výrobca';

  @override
  String get doubleTap => 'Dvojité ťuknutie';

  @override
  String get ledBrightness => 'Jas LED';

  @override
  String get micGain => 'Zosilnenie mikrofónu';

  @override
  String get disconnect => 'Odpojiť';

  @override
  String get forgetDevice => 'Zabudnúť zariadenie';

  @override
  String get chargingIssues => 'Problémy s nabíjaním';

  @override
  String get disconnectDevice => 'Odpojiť zariadenie';

  @override
  String get unpairDevice => 'Zrušiť párovanie zariadenia';

  @override
  String get unpairAndForget => 'Zrušiť párovanie a zabudnúť zariadenie';

  @override
  String get deviceDisconnectedMessage => 'Vaše Omi bolo odpojené 😔';

  @override
  String get deviceUnpairedMessage =>
      'Párovanie zariadenia bolo zrušené. Prejdite do Nastavenia > Bluetooth a zabudnite zariadenie pre dokončenie.';

  @override
  String get unpairDialogTitle => 'Zrušiť párovanie zariadenia';

  @override
  String get unpairDialogMessage =>
      'Týmto sa zruší párovanie zariadenia, aby sa mohlo pripojiť k inému telefónu. Budete musieť prejsť do Nastavenia > Bluetooth a zabudnúť zariadenie pre dokončenie procesu.';

  @override
  String get deviceNotConnected => 'Zariadenie nie je pripojené';

  @override
  String get connectDeviceMessage =>
      'Pripojte svoje zariadenie Omi pre prístup\nk nastaveniam a prispôsobeniu zariadenia';

  @override
  String get deviceInfoSection => 'Informácie o zariadení';

  @override
  String get customizationSection => 'Prispôsobenie';

  @override
  String get hardwareSection => 'Hardvér';

  @override
  String get v2Undetected => 'V2 nebolo zistené';

  @override
  String get v2UndetectedMessage =>
      'Zistili sme, že máte zariadenie V1 alebo vaše zariadenie nie je pripojené. Funkcia SD karty je dostupná len pre zariadenia V2.';

  @override
  String get endConversation => 'Ukončiť konverzáciu';

  @override
  String get pauseResume => 'Pozastaviť/Pokračovať';

  @override
  String get starConversation => 'Označiť konverzáciu hviezdičkou';

  @override
  String get doubleTapAction => 'Akcia dvojitého ťuknutia';

  @override
  String get endAndProcess => 'Ukončiť a spracovať konverzáciu';

  @override
  String get pauseResumeRecording => 'Pozastaviť/Pokračovať nahrávanie';

  @override
  String get starOngoing => 'Označiť prebiehajúcu konverzáciu hviezdičkou';

  @override
  String get off => 'Vypnuté';

  @override
  String get max => 'Maximum';

  @override
  String get mute => 'Stlmiť';

  @override
  String get quiet => 'Tiché';

  @override
  String get normal => 'Normálne';

  @override
  String get high => 'Vysoké';

  @override
  String get micGainDescMuted => 'Mikrofón je stlmený';

  @override
  String get micGainDescLow => 'Veľmi tiché - pre hlučné prostredia';

  @override
  String get micGainDescModerate => 'Tiché - pre mierne hlučné prostredie';

  @override
  String get micGainDescNeutral => 'Neutrálne - vyvážené nahrávanie';

  @override
  String get micGainDescSlightlyBoosted => 'Mierne zosilnené - normálne použitie';

  @override
  String get micGainDescBoosted => 'Zosilnené - pre tiché prostredia';

  @override
  String get micGainDescHigh => 'Vysoké - pre vzdialené alebo tiché hlasy';

  @override
  String get micGainDescVeryHigh => 'Veľmi vysoké - pre veľmi tiché zdroje';

  @override
  String get micGainDescMax => 'Maximálne - používať opatrne';

  @override
  String get developerSettingsTitle => 'Vývojárske nastavenia';

  @override
  String get saving => 'Ukladá sa...';

  @override
  String get personaConfig => 'Nakonfigurujte svoju AI persónu';

  @override
  String get beta => 'BETA';

  @override
  String get transcription => 'Prepis';

  @override
  String get transcriptionConfig => 'Nakonfigurovať poskytovateľa STT';

  @override
  String get conversationTimeout => 'Časový limit konverzácie';

  @override
  String get conversationTimeoutConfig => 'Nastaviť, kedy sa konverzácie automaticky ukončia';

  @override
  String get importData => 'Importovať údaje';

  @override
  String get importDataConfig => 'Importovať údaje z iných zdrojov';

  @override
  String get debugDiagnostics => 'Ladenie a diagnostika';

  @override
  String get endpointUrl => 'URL koncového bodu';

  @override
  String get noApiKeys => 'Zatiaľ žiadne API kľúče';

  @override
  String get createKeyToStart => 'Vytvorte kľúč pre začiatok';

  @override
  String get createKey => 'Vytvoriť kľúč';

  @override
  String get docs => 'Dokumentácia';

  @override
  String get yourOmiInsights => 'Vaše štatistiky Omi';

  @override
  String get today => 'Dnes';

  @override
  String get thisMonth => 'Tento mesiac';

  @override
  String get thisYear => 'Tento rok';

  @override
  String get allTime => 'Celkovo';

  @override
  String get noActivityYet => 'Zatiaľ žiadna aktivita';

  @override
  String get startConversationToSeeInsights =>
      'Začnite konverzáciu s Omi,\naby ste tu videli svoje štatistiky využitia.';

  @override
  String get listening => 'Počúvanie';

  @override
  String get listeningSubtitle => 'Celkový čas, počas ktorého Omi aktívne počúvalo.';

  @override
  String get understanding => 'Porozumenie';

  @override
  String get understandingSubtitle => 'Slová pochopené z vašich konverzácií.';

  @override
  String get providing => 'Poskytovanie';

  @override
  String get providingSubtitle => 'Úlohy a poznámky automaticky zachytené.';

  @override
  String get remembering => 'Pamätanie';

  @override
  String get rememberingSubtitle => 'Fakty a detaily zapamätané pre vás.';

  @override
  String get unlimitedPlan => 'Neobmedzený plán';

  @override
  String get managePlan => 'Spravovať plán';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'Váš plán bude zrušený $date.';
  }

  @override
  String renewsOn(String date) {
    return 'Váš plán sa obnoví $date.';
  }

  @override
  String get basicPlan => 'Bezplatný plán';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used z $limit min použitých';
  }

  @override
  String get upgrade => 'Upgradovať';

  @override
  String get upgradeToUnlimited => 'Upgradovať na neobmedzený';

  @override
  String basicPlanDesc(int limit) {
    return 'Váš plán zahŕňa $limit bezplatných minút mesačne. Upgradujte na neobmedzený.';
  }

  @override
  String get shareStatsMessage => 'Zdieľam svoje štatistiky Omi! (omi.me - váš AI asistent vždy po ruke)';

  @override
  String get sharePeriodToday => 'Dnes Omi:';

  @override
  String get sharePeriodMonth => 'Tento mesiac Omi:';

  @override
  String get sharePeriodYear => 'Tento rok Omi:';

  @override
  String get sharePeriodAllTime => 'Doteraz Omi:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 Počúvalo $minutes minút';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 Porozumelo $words slovám';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ Poskytlo $count postrehov';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 Zapamätalo si $count spomienok';
  }

  @override
  String get debugLogs => 'Debug logy';

  @override
  String get debugLogsAutoDelete => 'Automaticky sa odstránia po 3 dňoch.';

  @override
  String get debugLogsDesc => 'Pomáha diagnostikovať problémy';

  @override
  String get noLogFilesFound => 'Neboli nájdené žiadne súbory logov.';

  @override
  String get omiDebugLog => 'Omi debug log';

  @override
  String get logShared => 'Log bol zdieľaný';

  @override
  String get selectLogFile => 'Vyberte súbor logu';

  @override
  String get shareLogs => 'Zdieľať logy';

  @override
  String get debugLogCleared => 'Debug log bol vymazaný';

  @override
  String get exportStarted => 'Export bol spustený. Môže to trvať niekoľko sekúnd...';

  @override
  String get exportAllData => 'Exportovať všetky údaje';

  @override
  String get exportDataDesc => 'Exportovať konverzácie do JSON súboru';

  @override
  String get exportedConversations => 'Exportované konverzácie z Omi';

  @override
  String get exportShared => 'Export bol zdieľaný';

  @override
  String get deleteKnowledgeGraphTitle => 'Odstrániť graf znalostí?';

  @override
  String get deleteKnowledgeGraphMessage =>
      'Týmto odstránite všetky odvodené údaje grafu znalostí (uzly a prepojenia). Vaše pôvodné spomienky zostanú v bezpečí. Graf bude znovu vytvorený postupom času alebo na ďalšiu požiadavku.';

  @override
  String get knowledgeGraphDeleted => 'Graf znalostí bol úspešne odstránený';

  @override
  String deleteGraphFailed(String error) {
    return 'Nepodarilo sa odstrániť graf: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'Odstrániť graf znalostí';

  @override
  String get deleteKnowledgeGraphDesc => 'Vymazať všetky uzly a prepojenia';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'MCP server';

  @override
  String get mcpServerDesc => 'Pripojte AI asistentov k vašim údajom';

  @override
  String get serverUrl => 'URL servera';

  @override
  String get urlCopied => 'URL bola skopírovaná';

  @override
  String get apiKeyAuth => 'Autentifikácia API kľúčom';

  @override
  String get header => 'Hlavička';

  @override
  String get authorizationBearer => 'Authorization: Bearer <key>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'Client ID';

  @override
  String get clientSecret => 'Client Secret';

  @override
  String get useMcpApiKey => 'Použite svoj MCP API kľúč';

  @override
  String get webhooks => 'Webhooky';

  @override
  String get conversationEvents => 'Udalosti konverzácií';

  @override
  String get newConversationCreated => 'Nová konverzácia bola vytvorená';

  @override
  String get realtimeTranscript => 'Prepis v reálnom čase';

  @override
  String get transcriptReceived => 'Prepis bol prijatý';

  @override
  String get audioBytes => 'Audio bajty';

  @override
  String get audioDataReceived => 'Audio dáta boli prijaté';

  @override
  String get intervalSeconds => 'Interval (sekundy)';

  @override
  String get daySummary => 'Denné zhrnutie';

  @override
  String get summaryGenerated => 'Zhrnutie bolo vygenerované';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'Pridať do claude_desktop_config.json';

  @override
  String get copyConfig => 'Skopírovať konfiguráciu';

  @override
  String get configCopied => 'Konfigurácia bola skopírovaná do schránky';

  @override
  String get listeningMins => 'Počúvanie (min)';

  @override
  String get understandingWords => 'Porozumenie (slová)';

  @override
  String get insights => 'Postrehy';

  @override
  String get memories => 'Spomienky';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '$used z $limit min použitých tento mesiac';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '$used z $limit slov použitých tento mesiac';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '$used z $limit postrehov získaných tento mesiac';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return '$used z $limit spomienok vytvorených tento mesiac';
  }

  @override
  String get visibility => 'Viditeľnosť';

  @override
  String get visibilitySubtitle => 'Kontrolujte, ktoré konverzácie sa zobrazia vo vašom zozname';

  @override
  String get showShortConversations => 'Zobraziť krátke konverzácie';

  @override
  String get showShortConversationsDesc => 'Zobraziť konverzácie kratšie ako hranica';

  @override
  String get showDiscardedConversations => 'Zobraziť zahodené konverzácie';

  @override
  String get showDiscardedConversationsDesc => 'Zahrnúť konverzácie označené ako zahodené';

  @override
  String get shortConversationThreshold => 'Hranica krátkej konverzácie';

  @override
  String get shortConversationThresholdSubtitle =>
      'Konverzácie kratšie ako toto budú skryté, pokiaľ nie sú povolené vyššie';

  @override
  String get durationThreshold => 'Hranica trvania';

  @override
  String get durationThresholdDesc => 'Skryť konverzácie kratšie ako toto';

  @override
  String minLabel(int count) {
    return '$count min';
  }

  @override
  String get customVocabularyTitle => 'Vlastný slovník';

  @override
  String get addWords => 'Pridať slová';

  @override
  String get addWordsDesc => 'Mená, výrazy alebo neobvyklé slová';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'Pripojiť';

  @override
  String get comingSoon => 'Čoskoro';

  @override
  String get chatToolsFooter => 'Pripojte svoje aplikácie na zobrazenie údajov a metrík v chate.';

  @override
  String get completeAuthInBrowser =>
      'Dokončite prosím autentifikáciu vo vašom prehliadači. Po dokončení sa vráťte do aplikácie.';

  @override
  String failedToStartAuth(String appName) {
    return 'Nepodarilo sa spustiť autentifikáciu $appName';
  }

  @override
  String disconnectAppTitle(String appName) {
    return 'Odpojiť $appName?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'Naozaj chcete odpojiť $appName? Môžete sa znovu pripojiť kedykoľvek.';
  }

  @override
  String disconnectedFrom(String appName) {
    return 'Odpojené od $appName';
  }

  @override
  String get failedToDisconnect => 'Nepodarilo sa odpojiť';

  @override
  String connectTo(String appName) {
    return 'Pripojiť k $appName';
  }

  @override
  String authAccessMessage(String appName) {
    return 'Budete musieť autorizovať Omi na prístup k vašim údajom $appName. Toto otvorí váš prehliadač pre autentifikáciu.';
  }

  @override
  String get continueAction => 'Pokračovať';

  @override
  String get languageTitle => 'Jazyk';

  @override
  String get primaryLanguage => 'Primárny jazyk';

  @override
  String get automaticTranslation => 'Automatický preklad';

  @override
  String get detectLanguages => 'Zistiť 10+ jazykov';

  @override
  String get authorizeSavingRecordings => 'Autorizovať ukladanie nahrávok';

  @override
  String get thanksForAuthorizing => 'Ďakujeme za autorizáciu!';

  @override
  String get needYourPermission => 'Potrebujeme vaše povolenie';

  @override
  String get alreadyGavePermission =>
      'Už ste nám dali povolenie uložiť vaše nahrávky. Tu je pripomenutie, prečo ho potrebujeme:';

  @override
  String get wouldLikePermission => 'Chceli by sme vaše povolenie na uloženie vašich hlasových nahrávok. Tu je dôvod:';

  @override
  String get improveSpeechProfile => 'Zlepšiť váš hlasový profil';

  @override
  String get improveSpeechProfileDesc =>
      'Používame nahrávky na ďalšie trénovanie a vylepšenie vášho osobného hlasového profilu.';

  @override
  String get trainFamilyProfiles => 'Trénovať profily pre priateľov a rodinu';

  @override
  String get trainFamilyProfilesDesc =>
      'Vaše nahrávky nám pomáhajú rozpoznávať a vytvárať profily pre vašich priateľov a rodinu.';

  @override
  String get enhanceTranscriptAccuracy => 'Zlepšiť presnosť prepisu';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'Keď sa náš model zlepší, môžeme poskytovať lepšie výsledky prepisu pre vaše nahrávky.';

  @override
  String get legalNotice =>
      'Právne upozornenie: Zákonnosť nahrávania a ukladania hlasových dát sa môže líšiť v závislosti od vašej lokality a spôsobu používania tejto funkcie. Je vašou zodpovednosťou zabezpečiť súlad s miestnymi zákonmi a predpismi.';

  @override
  String get alreadyAuthorized => 'Už autorizované';

  @override
  String get authorize => 'Autorizovať';

  @override
  String get revokeAuthorization => 'Zrušiť autorizáciu';

  @override
  String get authorizationSuccessful => 'Autorizácia bola úspešná!';

  @override
  String get failedToAuthorize => 'Nepodarilo sa autorizovať. Skúste to prosím znova.';

  @override
  String get authorizationRevoked => 'Autorizácia bola zrušená.';

  @override
  String get recordingsDeleted => 'Nahrávky boli odstránené.';

  @override
  String get failedToRevoke => 'Nepodarilo sa zrušiť autorizáciu. Skúste to prosím znova.';

  @override
  String get permissionRevokedTitle => 'Povolenie bolo zrušené';

  @override
  String get permissionRevokedMessage => 'Chcete, aby sme odstránili aj všetky vaše existujúce nahrávky?';

  @override
  String get yes => 'Áno';

  @override
  String get editName => 'Upraviť meno';

  @override
  String get howShouldOmiCallYou => 'Ako by vás malo Omi oslovovať?';

  @override
  String get enterYourName => 'Zadajte svoje meno';

  @override
  String get nameCannotBeEmpty => 'Meno nemôže byť prázdne';

  @override
  String get nameUpdatedSuccessfully => 'Meno bolo úspešne aktualizované!';

  @override
  String get calendarSettings => 'Nastavenia kalendára';

  @override
  String get calendarProviders => 'Poskytovatelia kalendára';

  @override
  String get macOsCalendar => 'macOS kalendár';

  @override
  String get connectMacOsCalendar => 'Pripojte svoj lokálny macOS kalendár';

  @override
  String get googleCalendar => 'Google kalendár';

  @override
  String get syncGoogleAccount => 'Synchronizovať s vaším Google účtom';

  @override
  String get showMeetingsMenuBar => 'Zobraziť nadchádzajúce stretnutia v paneli ponúk';

  @override
  String get showMeetingsMenuBarDesc => 'Zobraziť vaše ďalšie stretnutie a čas do jeho začiatku v paneli ponúk macOS';

  @override
  String get showEventsNoParticipants => 'Zobraziť udalosti bez účastníkov';

  @override
  String get showEventsNoParticipantsDesc =>
      'Keď je povolené, Nadchádzajúce zobrazí udalosti bez účastníkov alebo video odkazu.';

  @override
  String get yourMeetings => 'Vaše stretnutia';

  @override
  String get refresh => 'Obnoviť';

  @override
  String get noUpcomingMeetings => 'Neboli nájdené žiadne nadchádzajúce stretnutia';

  @override
  String get checkingNextDays => 'Kontrola nasledujúcich 30 dní';

  @override
  String get tomorrow => 'Zajtra';

  @override
  String get googleCalendarComingSoon => 'Integrácia Google kalendára čoskoro!';

  @override
  String connectedAsUser(String userId) {
    return 'Pripojený ako používateľ: $userId';
  }

  @override
  String get defaultWorkspace => 'Predvolený pracovný priestor';

  @override
  String get tasksCreatedInWorkspace => 'Úlohy budú vytvorené v tomto pracovnom priestore';

  @override
  String get defaultProjectOptional => 'Predvolený projekt (voliteľné)';

  @override
  String get leaveUnselectedTasks => 'Nechajte nevybrané pre vytvorenie úloh bez projektu';

  @override
  String get noProjectsInWorkspace => 'V tomto pracovnom priestore neboli nájdené žiadne projekty';

  @override
  String get conversationTimeoutDesc => 'Vyberte, ako dlho čakať v tichosti pred automatickým ukončením konverzácie:';

  @override
  String get timeout2Minutes => '2 minúty';

  @override
  String get timeout2MinutesDesc => 'Ukončiť konverzáciu po 2 minútach ticha';

  @override
  String get timeout5Minutes => '5 minút';

  @override
  String get timeout5MinutesDesc => 'Ukončiť konverzáciu po 5 minútach ticha';

  @override
  String get timeout10Minutes => '10 minút';

  @override
  String get timeout10MinutesDesc => 'Ukončiť konverzáciu po 10 minútach ticha';

  @override
  String get timeout30Minutes => '30 minút';

  @override
  String get timeout30MinutesDesc => 'Ukončiť konverzáciu po 30 minútach ticha';

  @override
  String get timeout4Hours => '4 hodiny';

  @override
  String get timeout4HoursDesc => 'Ukončiť konverzáciu po 4 hodinách ticha';

  @override
  String get conversationEndAfterHours => 'Konverzácie sa teraz ukončia po 4 hodinách ticha';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Konverzácie sa teraz ukončia po $minutes minúte/minútach ticha';
  }

  @override
  String get tellUsPrimaryLanguage => 'Povedzte nám váš primárny jazyk';

  @override
  String get languageForTranscription => 'Nastavte svoj jazyk pre presnejšie prepisy a personalizovaný zážitok.';

  @override
  String get singleLanguageModeInfo => 'Režim jedného jazyka je povolený. Preklad je vypnutý pre vyššiu presnosť.';

  @override
  String get searchLanguageHint => 'Hľadať jazyk podľa názvu alebo kódu';

  @override
  String get noLanguagesFound => 'Neboli nájdené žiadne jazyky';

  @override
  String get skip => 'Preskočiť';

  @override
  String languageSetTo(String language) {
    return 'Jazyk bol nastavený na $language';
  }

  @override
  String get failedToSetLanguage => 'Nepodarilo sa nastaviť jazyk';

  @override
  String appSettings(String appName) {
    return '$appName Nastavenia';
  }

  @override
  String disconnectFromApp(String appName) {
    return 'Odpojiť od $appName?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'Toto odstráni vašu autentifikáciu $appName. Budete sa musieť znovu pripojiť, aby ste ho mohli použiť.';
  }

  @override
  String connectedToApp(String appName) {
    return 'Pripojené k $appName';
  }

  @override
  String get account => 'Účet';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Vaše úlohy budú synchronizované s vaším účtom $appName';
  }

  @override
  String get defaultSpace => 'Predvolený priestor';

  @override
  String get selectSpaceInWorkspace => 'Vyberte priestor vo vašom pracovnom priestore';

  @override
  String get noSpacesInWorkspace => 'V tomto pracovnom priestore neboli nájdené žiadne priestory';

  @override
  String get defaultList => 'Predvolený zoznam';

  @override
  String get tasksAddedToList => 'Úlohy budú pridané do tohto zoznamu';

  @override
  String get noListsInSpace => 'V tomto priestore neboli nájdené žiadne zoznamy';

  @override
  String failedToLoadRepos(String error) {
    return 'Nepodarilo sa načítať repozitáre: $error';
  }

  @override
  String get defaultRepoSaved => 'Predvolený repozitár bol uložený';

  @override
  String get failedToSaveDefaultRepo => 'Nepodarilo sa uložiť predvolený repozitár';

  @override
  String get defaultRepository => 'Predvolený repozitár';

  @override
  String get selectDefaultRepoDesc =>
      'Vyberte predvolený repozitár pre vytváranie problémov. Pri vytváraní problémov môžete stále zadať iný repozitár.';

  @override
  String get noReposFound => 'Neboli nájdené žiadne repozitáre';

  @override
  String get private => 'Súkromný';

  @override
  String updatedDate(String date) {
    return 'Aktualizované $date';
  }

  @override
  String get yesterday => 'včera';

  @override
  String daysAgo(int count) {
    return 'pred $count dňami';
  }

  @override
  String get oneWeekAgo => 'pred 1 týždňom';

  @override
  String weeksAgo(int count) {
    return 'pred $count týždňami';
  }

  @override
  String get oneMonthAgo => 'pred 1 mesiacom';

  @override
  String monthsAgo(int count) {
    return 'pred $count mesiacmi';
  }

  @override
  String get issuesCreatedInRepo => 'Problémy budú vytvorené vo vašom predvolenom repozitári';

  @override
  String get taskIntegrations => 'Integrácie úloh';

  @override
  String get configureSettings => 'Konfigurovať nastavenia';

  @override
  String get completeAuthBrowser =>
      'Dokončite prosím autentifikáciu vo vašom prehliadači. Po dokončení sa vráťte do aplikácie.';

  @override
  String failedToStartAppAuth(String appName) {
    return 'Nepodarilo sa spustiť autentifikáciu $appName';
  }

  @override
  String connectToAppTitle(String appName) {
    return 'Pripojiť k $appName';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Budete musieť autorizovať Omi na vytváranie úloh vo vašom účte $appName. Toto otvorí váš prehliadač pre autentifikáciu.';
  }

  @override
  String get continueButton => 'Pokračovať';

  @override
  String appIntegration(String appName) {
    return '$appName Integrácia';
  }

  @override
  String integrationComingSoon(String appName) {
    return 'Integrácia s $appName čoskoro! Usilovne pracujeme na tom, aby sme vám priniesli viac možností správy úloh.';
  }

  @override
  String get gotIt => 'Rozumiem';

  @override
  String get tasksExportedOneApp => 'Úlohy možno exportovať do jednej aplikácie naraz.';

  @override
  String get completeYourUpgrade => 'Dokončite svoj upgrade';

  @override
  String get importConfiguration => 'Importovať konfiguráciu';

  @override
  String get exportConfiguration => 'Exportovať konfiguráciu';

  @override
  String get bringYourOwn => 'Prineste si vlastný';

  @override
  String get payYourSttProvider => 'Voľne používajte omi. Platíte len svojmu poskytovateľovi STT priamo.';

  @override
  String get freeMinutesMonth => '1 200 bezplatných minút/mesiac je zahrnutých. Neobmedzené s ';

  @override
  String get omiUnlimited => 'Omi Unlimited';

  @override
  String get hostRequired => 'Hostiteľ je povinný';

  @override
  String get validPortRequired => 'Platný port je povinný';

  @override
  String get validWebsocketUrlRequired => 'Platná WebSocket URL je povinná (wss://)';

  @override
  String get apiUrlRequired => 'API URL je povinná';

  @override
  String get apiKeyRequired => 'API kľúč je povinný';

  @override
  String get invalidJsonConfig => 'Neplatná JSON konfigurácia';

  @override
  String errorSaving(String error) {
    return 'Chyba pri ukladaní: $error';
  }

  @override
  String get configCopiedToClipboard => 'Konfigurácia bola skopírovaná do schránky';

  @override
  String get pasteJsonConfig => 'Vložte svoju JSON konfiguráciu nižšie:';

  @override
  String get addApiKeyAfterImport => 'Po importe budete musieť pridať svoj vlastný API kľúč';

  @override
  String get paste => 'Vložiť';

  @override
  String get import => 'Importovať';

  @override
  String get invalidProviderInConfig => 'Neplatný poskytovateľ v konfigurácii';

  @override
  String importedConfig(String providerName) {
    return 'Importovaná konfigurácia $providerName';
  }

  @override
  String invalidJson(String error) {
    return 'Neplatný JSON: $error';
  }

  @override
  String get provider => 'Poskytovateľ';

  @override
  String get live => 'Naživo';

  @override
  String get onDevice => 'Na zariadení';

  @override
  String get apiUrl => 'API URL';

  @override
  String get enterSttHttpEndpoint => 'Zadajte svoj STT HTTP koncový bod';

  @override
  String get websocketUrl => 'WebSocket URL';

  @override
  String get enterLiveSttWebsocket => 'Zadajte svoj live STT WebSocket koncový bod';

  @override
  String get apiKey => 'API kľúč';

  @override
  String get enterApiKey => 'Zadajte svoj API kľúč';

  @override
  String get storedLocallyNeverShared => 'Uložené lokálne, nikdy nezdieľané';

  @override
  String get host => 'Hostiteľ';

  @override
  String get port => 'Port';

  @override
  String get advanced => 'Pokročilé';

  @override
  String get configuration => 'Konfigurácia';

  @override
  String get requestConfiguration => 'Konfigurácia požiadavky';

  @override
  String get responseSchema => 'Schéma odpovede';

  @override
  String get modified => 'Zmenené';

  @override
  String get resetRequestConfig => 'Obnoviť konfiguráciu požiadavky na predvolenú';

  @override
  String get logs => 'Logy';

  @override
  String get logsCopied => 'Logy boli skopírované';

  @override
  String get noLogsYet => 'Zatiaľ žiadne logy. Začnite nahrávanie, aby ste videli vlastnú STT aktivitu.';

  @override
  String deviceUsesCodec(String deviceName, String codecReason) {
    return '$deviceName používa $codecReason. Omi bude použité.';
  }

  @override
  String get omiTranscription => 'Omi Prepis';

  @override
  String get bestInClassTranscription => 'Najlepší prepis v triede s nulovou konfiguráciou';

  @override
  String get instantSpeakerLabels => 'Okamžité značky rečníkov';

  @override
  String get languageTranslation => 'Preklad do 100+ jazykov';

  @override
  String get optimizedForConversation => 'Optimalizované pre konverzáciu';

  @override
  String get autoLanguageDetection => 'Automatická detekcia jazyka';

  @override
  String get highAccuracy => 'Vysoká presnosť';

  @override
  String get privacyFirst => 'Súkromie na prvom mieste';

  @override
  String get saveChanges => 'Uložiť zmeny';

  @override
  String get resetToDefault => 'Obnoviť na predvolené';

  @override
  String get viewTemplate => 'Zobraziť šablónu';

  @override
  String get trySomethingLike => 'Skúste niečo ako...';

  @override
  String get tryIt => 'Vyskúšajte to';

  @override
  String get creatingPlan => 'Vytváranie plánu';

  @override
  String get developingLogic => 'Vyvíjanie logiky';

  @override
  String get designingApp => 'Navrhovanie aplikácie';

  @override
  String get generatingIconStep => 'Generovanie ikony';

  @override
  String get finalTouches => 'Záverečné úpravy';

  @override
  String get processing => 'Spracováva sa...';

  @override
  String get features => 'Funkcie';

  @override
  String get creatingYourApp => 'Vytváranie vašej aplikácie...';

  @override
  String get generatingIcon => 'Generovanie ikony...';

  @override
  String get whatShouldWeMake => 'Čo by sme mali vytvoriť?';

  @override
  String get appName => 'Názov aplikácie';

  @override
  String get description => 'Popis';

  @override
  String get publicLabel => 'Verejná';

  @override
  String get privateLabel => 'Súkromná';

  @override
  String get free => 'Zadarmo';

  @override
  String get perMonth => '/ Mesiac';

  @override
  String get tailoredConversationSummaries => 'Prispôsobené zhrnutia konverzácií';

  @override
  String get customChatbotPersonality => 'Vlastná osobnosť chatbota';

  @override
  String get makePublic => 'Zverejniť';

  @override
  String get anyoneCanDiscover => 'Ktokoľvek môže objaviť vašu aplikáciu';

  @override
  String get onlyYouCanUse => 'Túto aplikáciu môžete používať len vy';

  @override
  String get paidApp => 'Platená aplikácia';

  @override
  String get usersPayToUse => 'Používatelia platia za používanie vašej aplikácie';

  @override
  String get freeForEveryone => 'Bezplatné pre všetkých';

  @override
  String get perMonthLabel => '/ mesiac';

  @override
  String get creating => 'Vytvára sa...';

  @override
  String get createApp => 'Vytvoriť aplikáciu';

  @override
  String get searchingForDevices => 'Vyhľadávajú sa zariadenia...';

  @override
  String devicesFoundNearby(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'ZARIADENIA',
      one: 'ZARIADENIE',
    );
    return '$count $_temp0 NÁJDENÉ V BLÍZKOSTI';
  }

  @override
  String get pairingSuccessful => 'PÁROVANIE ÚSPEŠNÉ';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Chyba pri pripájaní Apple Watch: $error';
  }

  @override
  String get dontShowAgain => 'Znovu to neukazovať';

  @override
  String get iUnderstand => 'Rozumiem';

  @override
  String get enableBluetooth => 'Povoliť Bluetooth';

  @override
  String get bluetoothNeeded =>
      'Omi potrebuje Bluetooth na pripojenie k vášmu nositeľnému zariadeniu. Povoľte prosím Bluetooth a skúste to znova.';

  @override
  String get contactSupport => 'Kontaktovať podporu?';

  @override
  String get connectLater => 'Pripojiť neskôr';

  @override
  String get grantPermissions => 'Udeliť povolenia';

  @override
  String get backgroundActivity => 'Aktivita na pozadí';

  @override
  String get backgroundActivityDesc => 'Nechajte Omi bežať na pozadí pre lepšiu stabilitu';

  @override
  String get locationAccess => 'Prístup k polohe';

  @override
  String get locationAccessDesc => 'Povoliť polohu na pozadí pre plný zážitok';

  @override
  String get notifications => 'Upozornenia';

  @override
  String get notificationsDesc => 'Povoliť upozornenia, aby ste zostali informovaní';

  @override
  String get locationServiceDisabled => 'Služba polohy je vypnutá';

  @override
  String get locationServiceDisabledDesc =>
      'Služba polohy je vypnutá. Prejdite do Nastavenia > Súkromie a zabezpečenie > Služby polohy a povoľte ju';

  @override
  String get backgroundLocationDenied => 'Prístup k polohe na pozadí bol zamietnutý';

  @override
  String get backgroundLocationDeniedDesc =>
      'Prejdite do nastavení zariadenia a nastavte povolenie polohy na \"Vždy povoliť\"';

  @override
  String get lovingOmi => 'Páči sa vám Omi?';

  @override
  String get leaveReviewIos =>
      'Pomôžte nám osloviť viac ľudí tým, že zanecháte recenziu v App Store. Vaša spätná väzba pre nás znamená celý svet!';

  @override
  String get leaveReviewAndroid =>
      'Pomôžte nám osloviť viac ľudí tým, že zanecháte recenziu v Google Play Store. Vaša spätná väzba pre nás znamená celý svet!';

  @override
  String get rateOnAppStore => 'Ohodnotiť v App Store';

  @override
  String get rateOnGooglePlay => 'Ohodnotiť v Google Play';

  @override
  String get maybeLater => 'Možno neskôr';

  @override
  String get speechProfileIntro => 'Omi potrebuje naučiť sa vaše ciele a váš hlas. Neskôr to budete môcť upraviť.';

  @override
  String get getStarted => 'Začať';

  @override
  String get allDone => 'Všetko hotové!';

  @override
  String get keepGoing => 'Pokračujte, darí sa vám to skvele';

  @override
  String get skipThisQuestion => 'Preskočiť túto otázku';

  @override
  String get skipForNow => 'Preskočiť zatiaľ';

  @override
  String get connectionError => 'Chyba pripojenia';

  @override
  String get connectionErrorDesc =>
      'Nepodarilo sa pripojiť k serveru. Skontrolujte prosím svoje internetové pripojenie a skúste to znova.';

  @override
  String get invalidRecordingMultipleSpeakers => 'Bola zistená neplatná nahrávka';

  @override
  String get multipleSpeakersDesc =>
      'Zdá sa, že v nahrávke je viacero rečníkov. Uistite sa, že ste na tichom mieste, a skúste to znova.';

  @override
  String get tooShortDesc => 'Nezistilo sa dostatok reči. Hovorte viac a skúste to znova.';

  @override
  String get invalidRecordingDesc => 'Uistite sa, že hovoríte minimálne 5 sekúnd a najviac 90.';

  @override
  String get areYouThere => 'Ste tam?';

  @override
  String get noSpeechDesc =>
      'Nepodarilo sa zistiť žiadnu reč. Uistite sa, že hovoríte minimálne 10 sekúnd a najviac 3 minúty.';

  @override
  String get connectionLost => 'Pripojenie bolo stratené';

  @override
  String get connectionLostDesc =>
      'Pripojenie bolo prerušené. Skontrolujte prosím svoje internetové pripojenie a skúste to znova.';

  @override
  String get tryAgain => 'Skúsiť znova';

  @override
  String get connectOmiOmiGlass => 'Pripojiť Omi / OmiGlass';

  @override
  String get continueWithoutDevice => 'Pokračovať bez zariadenia';

  @override
  String get permissionsRequired => 'Vyžadujú sa povolenia';

  @override
  String get permissionsRequiredDesc =>
      'Táto aplikácia potrebuje povolenia Bluetooth a Poloha, aby mohla správne fungovať. Povoľte ich prosím v nastaveniach.';

  @override
  String get openSettings => 'Otvoriť nastavenia';

  @override
  String get wantDifferentName => 'Chcete sa volať inak?';

  @override
  String get whatsYourName => 'Ako sa voláte?';

  @override
  String get speakTranscribeSummarize => 'Hovoriť. Prepisovať. Sumarizovať.';

  @override
  String get signInWithApple => 'Prihlásiť sa cez Apple';

  @override
  String get signInWithGoogle => 'Prihlásiť sa cez Google';

  @override
  String get byContinuingAgree => 'Pokračovaním súhlasíte s našimi ';

  @override
  String get termsOfUse => 'Podmienky používania';

  @override
  String get omiYourAiCompanion => 'Omi – Váš AI spoločník';

  @override
  String get captureEveryMoment =>
      'Zachyťte každý moment. Získajte zhrnutia\npoháňané AI. Nikdy viac si nerobte poznámky.';

  @override
  String get appleWatchSetup => 'Nastavenie Apple Watch';

  @override
  String get permissionRequestedExclaim => 'Povolenie bolo vyžiadané!';

  @override
  String get microphonePermission => 'Povolenie mikrofónu';

  @override
  String get permissionGrantedNow =>
      'Povolenie bolo udelené! Teraz:\n\nOtvorte aplikáciu Omi na hodinkách a ťuknite na \"Pokračovať\" nižšie';

  @override
  String get needMicrophonePermission =>
      'Potrebujeme povolenie mikrofónu.\n\n1. Ťuknite na \"Udeliť povolenie\"\n2. Povoľte na vašom iPhone\n3. Aplikácia na hodinkách sa zatvorí\n4. Znovu ju otvorte a ťuknite na \"Pokračovať\"';

  @override
  String get grantPermissionButton => 'Udeliť povolenie';

  @override
  String get needHelp => 'Potrebujete pomoc?';

  @override
  String get troubleshootingSteps =>
      'Riešenie problémov:\n\n1. Uistite sa, že Omi je nainštalované na vašich hodinkách\n2. Otvorte aplikáciu Omi na hodinkách\n3. Hľadajte vyskakovacie okno s povolením\n4. Ťuknite na \"Povoliť\", keď sa zobrazí\n5. Aplikácia na hodinkách sa zatvorí - znovu ju otvorte\n6. Vráťte sa a ťuknite na \"Pokračovať\" na vašom iPhone';

  @override
  String get recordingStartedSuccessfully => 'Nahrávanie bolo úspešne spustené!';

  @override
  String get permissionNotGrantedYet =>
      'Povolenie ešte nebolo udelené. Uistite sa, že ste povolili prístup k mikrofónu a znovu otvorili aplikáciu na hodinkách.';

  @override
  String errorRequestingPermission(String error) {
    return 'Chyba pri vyžiadaní povolenia: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'Chyba pri spustení nahrávania: $error';
  }

  @override
  String get selectPrimaryLanguage => 'Vyberte svoj primárny jazyk';

  @override
  String get languageBenefits => 'Nastavte svoj jazyk pre presnejšie prepisy a personalizovaný zážitok';

  @override
  String get whatsYourPrimaryLanguage => 'Aký je váš primárny jazyk?';

  @override
  String get selectYourLanguage => 'Vyberte svoj jazyk';

  @override
  String get personalGrowthJourney => 'Vaša cesta osobného rastu s AI, ktorá počúva každé vaše slovo.';

  @override
  String get actionItemsTitle => 'Úlohy';

  @override
  String get actionItemsDescription => 'Ťuknite pre úpravu • Dlhé stlačenie pre výber • Potiahnutím pre akcie';

  @override
  String get tabToDo => 'Urobiť';

  @override
  String get tabDone => 'Hotové';

  @override
  String get tabOld => 'Staré';

  @override
  String get emptyTodoMessage => '🎉 Všetko je aktuálne!\nŽiadne čakajúce úlohy';

  @override
  String get emptyDoneMessage => 'Zatiaľ žiadne dokončené položky';

  @override
  String get emptyOldMessage => '✅ Žiadne staré úlohy';

  @override
  String get noItems => 'Žiadne položky';

  @override
  String get actionItemMarkedIncomplete => 'Úloha bola označená ako nedokončená';

  @override
  String get actionItemCompleted => 'Úloha bola dokončená';

  @override
  String get deleteActionItemTitle => 'Odstrániť úlohu';

  @override
  String get deleteActionItemMessage => 'Naozaj chcete odstrániť túto úlohu?';

  @override
  String get deleteSelectedItemsTitle => 'Odstrániť vybrané položky';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Naozaj chcete odstrániť $count vybranú úlohu/úlohy$s?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'Úloha \"$description\" bola odstránená';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count úloha/úlohy$s bola odstránená';
  }

  @override
  String get failedToDeleteItem => 'Nepodarilo sa odstrániť úlohu';

  @override
  String get failedToDeleteItems => 'Nepodarilo sa odstrániť položky';

  @override
  String get failedToDeleteSomeItems => 'Nepodarilo sa odstrániť niektoré položky';

  @override
  String get welcomeActionItemsTitle => 'Pripravené na úlohy';

  @override
  String get welcomeActionItemsDescription =>
      'Vaša AI automaticky extrahuje úlohy z vašich konverzácií. Objavia sa tu, keď budú vytvorené.';

  @override
  String get autoExtractionFeature => 'Automaticky extrahované z konverzácií';

  @override
  String get editSwipeFeature => 'Ťuknite pre úpravu, potiahnutím dokončíte alebo odstránite';

  @override
  String itemsSelected(int count) {
    return '$count vybraných';
  }

  @override
  String get selectAll => 'Vybrať všetko';

  @override
  String get deleteSelected => 'Odstrániť vybrané';

  @override
  String searchMemories(int count) {
    return 'Hľadať v $count spomienkach';
  }

  @override
  String get memoryDeleted => 'Spomienka bola odstránená.';

  @override
  String get undo => 'Vrátiť späť';

  @override
  String get noMemoriesYet => 'Zatiaľ žiadne spomienky';

  @override
  String get noAutoMemories => 'Zatiaľ žiadne automaticky extrahované spomienky';

  @override
  String get noManualMemories => 'Zatiaľ žiadne manuálne spomienky';

  @override
  String get noMemoriesInCategories => 'Žiadne spomienky v týchto kategóriách';

  @override
  String get noMemoriesFound => 'Neboli nájdené žiadne spomienky';

  @override
  String get addFirstMemory => 'Pridajte svoju prvú spomienku';

  @override
  String get clearMemoryTitle => 'Vymazať pamäť Omi';

  @override
  String get clearMemoryMessage => 'Naozaj chcete vymazať pamäť Omi? Túto akciu nie je možné vrátiť späť.';

  @override
  String get clearMemoryButton => 'Vymazať pamäť';

  @override
  String get memoryClearedSuccess => 'Pamäť Omi o vás bola vymazaná';

  @override
  String get noMemoriesToDelete => 'Žiadne spomienky na odstránenie';

  @override
  String get createMemoryTooltip => 'Vytvoriť novú spomienku';

  @override
  String get createActionItemTooltip => 'Vytvoriť novú úlohu';

  @override
  String get memoryManagement => 'Správa pamäte';

  @override
  String get filterMemories => 'Filtrovať spomienky';

  @override
  String totalMemoriesCount(int count) {
    return 'Máte $count spomienok celkom';
  }

  @override
  String get publicMemories => 'Verejné spomienky';

  @override
  String get privateMemories => 'Súkromné spomienky';

  @override
  String get makeAllPrivate => 'Urobiť všetky spomienky súkromnými';

  @override
  String get makeAllPublic => 'Urobiť všetky spomienky verejnými';

  @override
  String get deleteAllMemories => 'Odstrániť všetky spomienky';

  @override
  String get allMemoriesPrivateResult => 'Všetky spomienky sú teraz súkromné';

  @override
  String get allMemoriesPublicResult => 'Všetky spomienky sú teraz verejné';

  @override
  String get newMemory => 'Nová spomienka';

  @override
  String get editMemory => 'Upraviť spomienku';

  @override
  String get memoryContentHint => 'Rád jem zmrzlinu...';

  @override
  String get failedToSaveMemory => 'Nepodarilo sa uložiť. Skontrolujte prosím svoje pripojenie.';

  @override
  String get saveMemory => 'Uložiť spomienku';

  @override
  String get retry => 'Skúsiť znova';

  @override
  String get createActionItem => 'Vytvoriť úlohu';

  @override
  String get editActionItem => 'Upraviť úlohu';

  @override
  String get actionItemDescriptionHint => 'Čo je potrebné urobiť?';

  @override
  String get actionItemDescriptionEmpty => 'Popis úlohy nemôže byť prázdny.';

  @override
  String get actionItemUpdated => 'Úloha bola aktualizovaná';

  @override
  String get failedToUpdateActionItem => 'Nepodarilo sa aktualizovať úlohu';

  @override
  String get actionItemCreated => 'Úloha bola vytvorená';

  @override
  String get failedToCreateActionItem => 'Nepodarilo sa vytvoriť úlohu';

  @override
  String get dueDate => 'Termín dokončenia';

  @override
  String get time => 'Čas';

  @override
  String get addDueDate => 'Pridať termín dokončenia';

  @override
  String get pressDoneToSave => 'Stlačte hotovo pre uloženie';

  @override
  String get pressDoneToCreate => 'Stlačte hotovo pre vytvorenie';

  @override
  String get filterAll => 'Všetko';

  @override
  String get filterSystem => 'O vás';

  @override
  String get filterInteresting => 'Postrehy';

  @override
  String get filterManual => 'Manuálne';

  @override
  String get completed => 'Dokončené';

  @override
  String get markComplete => 'Označiť ako dokončené';

  @override
  String get actionItemDeleted => 'Úloha bola odstránená';

  @override
  String get failedToDeleteActionItem => 'Nepodarilo sa odstrániť úlohu';

  @override
  String get deleteActionItemConfirmTitle => 'Odstrániť úlohu';

  @override
  String get deleteActionItemConfirmMessage => 'Naozaj chcete odstrániť túto úlohu?';

  @override
  String get appLanguage => 'Jazyk aplikácie';

  @override
  String get appInterfaceSectionTitle => 'ROZHRANIE APLIKÁCIE';

  @override
  String get speechTranscriptionSectionTitle => 'REČ A PREPIS';

  @override
  String get languageSettingsHelperText =>
      'Jazyk aplikácie mení ponuky a tlačidlá. Jazyk reči ovplyvňuje spôsob prepisu vašich nahrávok.';
}
