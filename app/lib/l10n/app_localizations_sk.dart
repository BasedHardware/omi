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
  String get delete => 'Zmazať';

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
  String get copyTranscript => 'Kopírovať prepis';

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
  String get noInternetConnection => 'Žiadne internetové pripojenie';

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
  String get speechProfile => 'Rečový Profil';

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
  String get askOmi => 'Opýtať sa Omi';

  @override
  String get done => 'Hotovo';

  @override
  String get disconnected => 'Odpojené';

  @override
  String get searching => 'Vyhľadávanie...';

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
  String get noConversationsYet => 'Zatiaľ žiadne konverzácie';

  @override
  String get noStarredConversations => 'Žiadne konverzácie s hviezdičkou';

  @override
  String get starConversationHint =>
      'Ak chcete označiť konverzáciu hviezdičkou, otvorte ju a ťuknite na ikonu hviezdy v hlavičke.';

  @override
  String get searchConversations => 'Hľadať konverzácie...';

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
  String get deletingMessages => 'Odstraňovanie vašich správ z pamäte Omi...';

  @override
  String get messageCopied => '✨ Správa skopírovaná do schránky';

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
  String get noAppsFound => 'Nenašli sa žiadne aplikácie';

  @override
  String get tryAdjustingSearch => 'Skúste upraviť vyhľadávanie alebo filtre';

  @override
  String get createYourOwnApp => 'Vytvorte si vlastnú aplikáciu';

  @override
  String get buildAndShareApp => 'Vytvorte a zdieľajte vlastnú aplikáciu';

  @override
  String get searchApps => 'Hľadať aplikácie...';

  @override
  String get myApps => 'Moje Aplikácie';

  @override
  String get installedApps => 'Nainštalované Aplikácie';

  @override
  String get unableToFetchApps =>
      'Nepodarilo sa načítať aplikácie :(\n\nSkontrolujte prosím svoje internetové pripojenie a skúste to znova.';

  @override
  String get aboutOmi => 'O Omi';

  @override
  String get privacyPolicy => 'Zásady ochrany osobných údajov';

  @override
  String get visitWebsite => 'Navštíviť webovú stránku';

  @override
  String get helpOrInquiries => 'Pomoc alebo otázky?';

  @override
  String get joinCommunity => 'Pridajte sa ku komunite!';

  @override
  String get membersAndCounting => '8000+ členov a ich počet rastie.';

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
  String get customVocabulary => 'Vlastný Slovník';

  @override
  String get identifyingOthers => 'Identifikácia Ostatných';

  @override
  String get paymentMethods => 'Platobné Metódy';

  @override
  String get conversationDisplay => 'Zobrazenie Konverzácií';

  @override
  String get dataPrivacy => 'Ochrana Údajov';

  @override
  String get userId => 'ID Používateľa';

  @override
  String get notSet => 'Nenastavené';

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
  String get developerSettings => 'Nastavenia vývojára';

  @override
  String get getOmiForMac => 'Získať Omi pre Mac';

  @override
  String get referralProgram => 'Odporúčací program';

  @override
  String get signOut => 'Odhlásiť Sa';

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
      'Zariadenie odpárované. Prejdite do Nastavenia > Bluetooth a zabudnite zariadenie na dokončenie odpárovania.';

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
  String get saving => 'Ukladanie...';

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
  String get createKey => 'Vytvoriť Kľúč';

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
  String get upgradeToUnlimited => 'Upgradovať na neobmedzené';

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
  String get debugLogs => 'Denníky ladenia';

  @override
  String get debugLogsAutoDelete => 'Automaticky sa odstránia po 3 dňoch.';

  @override
  String get debugLogsDesc => 'Pomáha diagnostikovať problémy';

  @override
  String get noLogFilesFound => 'Nenašli sa žiadne súbory denníka.';

  @override
  String get omiDebugLog => 'Omi debug log';

  @override
  String get logShared => 'Log bol zdieľaný';

  @override
  String get selectLogFile => 'Vyberte súbor logu';

  @override
  String get shareLogs => 'Zdieľať denníky';

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
  String get knowledgeGraphDeleted => 'Graf znalostí zmazaný';

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
  String get urlCopied => 'URL skopírované';

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
  String get conversationEvents => 'Udalosti konverzácie';

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
  String get daySummary => 'Denný súhrn';

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
  String get insights => 'Poznatky';

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
  String get noLanguagesFound => 'Nenašli sa žiadne jazyky';

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
  String get private => 'Súkromná';

  @override
  String updatedDate(String date) {
    return 'Aktualizované $date';
  }

  @override
  String get yesterday => 'Včera';

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
  String get resetToDefault => 'Obnoviť predvolené';

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
  String get dontShowAgain => 'Nezobrazovať znova';

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
  String get whatsYourName => 'Ako sa voláš?';

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
  String get deleteActionItemTitle => 'Odstrániť akčnú položku';

  @override
  String get deleteActionItemMessage => 'Naozaj chcete odstrániť túto akčnú položku?';

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
  String get searchMemories => 'Hľadať spomienky...';

  @override
  String get memoryDeleted => 'Spomienka bola odstránená.';

  @override
  String get undo => 'Vrátiť späť';

  @override
  String get noMemoriesYet => '🧠 Zatiaľ žiadne spomienky';

  @override
  String get noAutoMemories => 'Zatiaľ žiadne automaticky extrahované spomienky';

  @override
  String get noManualMemories => 'Zatiaľ žiadne manuálne spomienky';

  @override
  String get noMemoriesInCategories => 'Žiadne spomienky v týchto kategóriách';

  @override
  String get noMemoriesFound => '🔍 Nenašli sa žiadne spomienky';

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
  String get newMemory => '✨ Nová pamäť';

  @override
  String get editMemory => '✏️ Upraviť pamäť';

  @override
  String get memoryContentHint => 'Rád jem zmrzlinu...';

  @override
  String get failedToSaveMemory => 'Nepodarilo sa uložiť. Skontrolujte prosím svoje pripojenie.';

  @override
  String get saveMemory => 'Uložiť spomienku';

  @override
  String get retry => 'Skúsiť znova';

  @override
  String get createActionItem => 'Vytvoriť položku úlohy';

  @override
  String get editActionItem => 'Upraviť položku úlohy';

  @override
  String get actionItemDescriptionHint => 'Čo je potrebné urobiť?';

  @override
  String get actionItemDescriptionEmpty => 'Popis úlohy nemôže byť prázdny.';

  @override
  String get actionItemUpdated => 'Úloha bola aktualizovaná';

  @override
  String get failedToUpdateActionItem => 'Nepodarilo sa aktualizovať položku úlohy';

  @override
  String get actionItemCreated => 'Úloha bola vytvorená';

  @override
  String get failedToCreateActionItem => 'Nepodarilo sa vytvoriť položku úlohy';

  @override
  String get dueDate => 'Termín';

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
  String get actionItemDeleted => 'Akčná položka odstránená';

  @override
  String get failedToDeleteActionItem => 'Nepodarilo sa odstrániť položku úlohy';

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

  @override
  String get translationNotice => 'Oznámenie o preklade';

  @override
  String get translationNoticeMessage =>
      'Omi prekladá konverzácie do vášho hlavného jazyka. Aktualizujte to kedykoľvek v Nastavenia → Profily.';

  @override
  String get pleaseCheckInternetConnection => 'Skontrolujte prosím pripojenie k internetu a skúste to znova';

  @override
  String get pleaseSelectReason => 'Vyberte prosím dôvod';

  @override
  String get tellUsMoreWhatWentWrong => 'Povedzte nám viac o tom, čo sa pokazilo...';

  @override
  String get selectText => 'Vybrať text';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Maximum $count cieľov povolených';
  }

  @override
  String get conversationCannotBeMerged => 'Túto konverzáciu nie je možné zlúčiť (zamknutá alebo sa už zlučuje)';

  @override
  String get pleaseEnterFolderName => 'Zadajte prosím názov priečinka';

  @override
  String get failedToCreateFolder => 'Vytvorenie priečinka zlyhalo';

  @override
  String get failedToUpdateFolder => 'Aktualizácia priečinka zlyhala';

  @override
  String get folderName => 'Názov priečinka';

  @override
  String get descriptionOptional => 'Popis (voliteľné)';

  @override
  String get failedToDeleteFolder => 'Odstránenie priečinka zlyhalo';

  @override
  String get editFolder => 'Upraviť priečinok';

  @override
  String get deleteFolder => 'Odstrániť priečinok';

  @override
  String get transcriptCopiedToClipboard => 'Prepis skopírovaný do schránky';

  @override
  String get summaryCopiedToClipboard => 'Zhrnutie skopírované do schránky';

  @override
  String get conversationUrlCouldNotBeShared => 'URL konverzácie sa nedá zdieľať.';

  @override
  String get urlCopiedToClipboard => 'URL skopírovaná do schránky';

  @override
  String get exportTranscript => 'Exportovať prepis';

  @override
  String get exportSummary => 'Exportovať zhrnutie';

  @override
  String get exportButton => 'Exportovať';

  @override
  String get actionItemsCopiedToClipboard => 'Položky akcií skopírované do schránky';

  @override
  String get summarize => 'Zhrnúť';

  @override
  String get generateSummary => 'Vygenerovať zhrnutie';

  @override
  String get conversationNotFoundOrDeleted => 'Konverzácia nebola nájdená alebo bola odstránená';

  @override
  String get deleteMemory => 'Odstrániť pamäť';

  @override
  String get thisActionCannotBeUndone => 'Túto akciu nie je možné vrátiť späť.';

  @override
  String memoriesCount(int count) {
    return '$count spomienok';
  }

  @override
  String get noMemoriesInCategory => 'V tejto kategórii zatiaľ nie sú žiadne spomienky';

  @override
  String get addYourFirstMemory => 'Pridajte svoju prvú spomienku';

  @override
  String get firmwareDisconnectUsb => 'Odpojte USB';

  @override
  String get firmwareUsbWarning => 'Pripojenie USB počas aktualizácií môže poškodiť vaše zariadenie.';

  @override
  String get firmwareBatteryAbove15 => 'Batéria nad 15%';

  @override
  String get firmwareEnsureBattery => 'Uistite sa, že vaše zariadenie má 15% batérie.';

  @override
  String get firmwareStableConnection => 'Stabilné pripojenie';

  @override
  String get firmwareConnectWifi => 'Pripojte sa k WiFi alebo mobilným dátam.';

  @override
  String failedToStartUpdate(String error) {
    return 'Nepodarilo sa spustiť aktualizáciu: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'Pred aktualizáciou sa uistite:';

  @override
  String get confirmed => 'Potvrdené!';

  @override
  String get release => 'Uvoľniť';

  @override
  String get slideToUpdate => 'Posuňte pre aktualizáciu';

  @override
  String copiedToClipboard(String title) {
    return '$title skopírované do schránky';
  }

  @override
  String get batteryLevel => 'Úroveň batérie';

  @override
  String get productUpdate => 'Aktualizácia produktu';

  @override
  String get offline => 'Offline';

  @override
  String get available => 'Dostupné';

  @override
  String get unpairDeviceDialogTitle => 'Zrušiť párovanie zariadenia';

  @override
  String get unpairDeviceDialogMessage =>
      'Tým sa zruší párovanie zariadenia, aby sa mohlo pripojiť k inému telefónu. Budete musieť prejsť do Nastavenia > Bluetooth a zabudnúť zariadenie na dokončenie procesu.';

  @override
  String get unpair => 'Zrušiť párovanie';

  @override
  String get unpairAndForgetDevice => 'Zrušiť párovanie a zabudnúť zariadenie';

  @override
  String get unknownDevice => 'Neznáme zariadenie';

  @override
  String get unknown => 'Neznáme';

  @override
  String get productName => 'Názov produktu';

  @override
  String get serialNumber => 'Sériové číslo';

  @override
  String get connected => 'Pripojené';

  @override
  String get privacyPolicyTitle => 'Zásady ochrany osobných údajov';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label copied';
  }

  @override
  String get noApiKeysYet => 'Zatiaľ žiadne API kľúče. Vytvorte jeden pre integráciu s vašou aplikáciou.';

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
  String get debugAndDiagnostics => 'Ladenie a diagnostika';

  @override
  String get autoDeletesAfter3Days => 'Automatické vymazanie po 3 dňoch';

  @override
  String get helpsDiagnoseIssues => 'Pomáha diagnostikovať problémy';

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
  String get realTimeTranscript => 'Prepis v reálnom čase';

  @override
  String get experimental => 'Experimentálne';

  @override
  String get transcriptionDiagnostics => 'Diagnostika prepisu';

  @override
  String get detailedDiagnosticMessages => 'Podrobné diagnostické správy';

  @override
  String get autoCreateSpeakers => 'Automaticky vytvoriť rečníkov';

  @override
  String get autoCreateWhenNameDetected => 'Auto-create when name detected';

  @override
  String get followUpQuestions => 'Následné otázky';

  @override
  String get suggestQuestionsAfterConversations => 'Navrhovať otázky po konverzáciách';

  @override
  String get goalTracker => 'Sledovanie cieľov';

  @override
  String get trackPersonalGoalsOnHomepage => 'Track your personal goals on homepage';

  @override
  String get dailyReflection => 'Denná reflexia';

  @override
  String get get9PmReminderToReflect => 'Get a 9 PM reminder to reflect on your day';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'Popis akčnej položky nesmie byť prázdny';

  @override
  String get saved => 'Uložené';

  @override
  String get overdue => 'Po termíne';

  @override
  String get failedToUpdateDueDate => 'Nepodarilo sa aktualizovať termín';

  @override
  String get markIncomplete => 'Označiť ako nedokončené';

  @override
  String get editDueDate => 'Upraviť termín';

  @override
  String get setDueDate => 'Nastaviť termín';

  @override
  String get clearDueDate => 'Vymazať termín';

  @override
  String get failedToClearDueDate => 'Nepodarilo sa vymazať termín';

  @override
  String get mondayAbbr => 'Po';

  @override
  String get tuesdayAbbr => 'Ut';

  @override
  String get wednesdayAbbr => 'St';

  @override
  String get thursdayAbbr => 'Št';

  @override
  String get fridayAbbr => 'Pi';

  @override
  String get saturdayAbbr => 'So';

  @override
  String get sundayAbbr => 'Ne';

  @override
  String get howDoesItWork => 'Ako to funguje?';

  @override
  String get sdCardSyncDescription => 'Synchronizácia SD karty importuje vaše spomienky z SD karty do aplikácie';

  @override
  String get checksForAudioFiles => 'Kontroluje zvukové súbory na SD karte';

  @override
  String get omiSyncsAudioFiles => 'Omi potom synchronizuje zvukové súbory so serverom';

  @override
  String get serverProcessesAudio => 'Server spracováva zvukové súbory a vytvára spomienky';

  @override
  String get youreAllSet => 'Všetko je pripravené!';

  @override
  String get welcomeToOmiDescription =>
      'Vitajte v Omi! Váš AI spoločník je pripravený pomôcť vám s rozhovormi, úlohami a oveľa viac.';

  @override
  String get startUsingOmi => 'Začať používať Omi';

  @override
  String get back => 'Späť';

  @override
  String get keyboardShortcuts => 'Klávesové Skratky';

  @override
  String get toggleControlBar => 'Prepnúť ovládací panel';

  @override
  String get pressKeys => 'Stlačte klávesy...';

  @override
  String get cmdRequired => '⌘ vyžadované';

  @override
  String get invalidKey => 'Neplatný kláves';

  @override
  String get space => 'Medzera';

  @override
  String get search => 'Hľadať';

  @override
  String get searchPlaceholder => 'Hľadať...';

  @override
  String get untitledConversation => 'Konverzácia bez názvu';

  @override
  String countRemaining(String count) {
    return '$count zostáva';
  }

  @override
  String get addGoal => 'Pridať cieľ';

  @override
  String get editGoal => 'Upraviť cieľ';

  @override
  String get icon => 'Ikona';

  @override
  String get goalTitle => 'Názov cieľa';

  @override
  String get current => 'Aktuálny';

  @override
  String get target => 'Cieľ';

  @override
  String get saveGoal => 'Uložiť';

  @override
  String get goals => 'Ciele';

  @override
  String get tapToAddGoal => 'Ťuknite na pridanie cieľa';

  @override
  String welcomeBack(String name) {
    return 'Vitajte späť, $name';
  }

  @override
  String get yourConversations => 'Vaše konverzácie';

  @override
  String get reviewAndManageConversations => 'Prezrite si a spravujte svoje zaznamenané konverzácie';

  @override
  String get startCapturingConversations => 'Začnite zachytávať konverzácie pomocou zariadenia Omi a uvidíte ich tu.';

  @override
  String get useMobileAppToCapture => 'Použite mobilnú aplikáciu na zachytenie zvuku';

  @override
  String get conversationsProcessedAutomatically => 'Konverzácie sa spracovávajú automaticky';

  @override
  String get getInsightsInstantly => 'Získajte poznatky a zhrnutia okamžite';

  @override
  String get showAll => 'Zobraziť všetko →';

  @override
  String get noTasksForToday => 'Žiadne úlohy na dnes.\\nSpýtajte sa Omi na ďalšie úlohy alebo ich vytvorte manuálne.';

  @override
  String get dailyScore => 'DENNÉ SKÓRE';

  @override
  String get dailyScoreDescription => 'Skóre, ktoré vám pomôže lepšie sa sústrediť na plnenie.';

  @override
  String get searchResults => 'Výsledky vyhľadávania';

  @override
  String get actionItems => 'Úlohy';

  @override
  String get tasksToday => 'Dnes';

  @override
  String get tasksTomorrow => 'Zajtra';

  @override
  String get tasksNoDeadline => 'Bez termínu';

  @override
  String get tasksLater => 'Neskôr';

  @override
  String get loadingTasks => 'Načítanie úloh...';

  @override
  String get tasks => 'Úlohy';

  @override
  String get swipeTasksToIndent => 'Potiahnutím úloh odsaďte, presuňte medzi kategóriami';

  @override
  String get create => 'Vytvoriť';

  @override
  String get noTasksYet => 'Zatiaľ žiadne úlohy';

  @override
  String get tasksFromConversationsWillAppear =>
      'Úlohy z vašich konverzácií sa tu zobrazia.\nKliknite na Vytvoriť a pridajte jednu ručne.';

  @override
  String get monthJan => 'Jan';

  @override
  String get monthFeb => 'Feb';

  @override
  String get monthMar => 'Mar';

  @override
  String get monthApr => 'Apr';

  @override
  String get monthMay => 'Máj';

  @override
  String get monthJun => 'Jún';

  @override
  String get monthJul => 'Júl';

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
  String get actionItemUpdatedSuccessfully => 'Položka úlohy úspešne aktualizovaná';

  @override
  String get actionItemCreatedSuccessfully => 'Položka úlohy úspešne vytvorená';

  @override
  String get actionItemDeletedSuccessfully => 'Položka úlohy úspešne odstránená';

  @override
  String get deleteActionItem => 'Odstrániť položku úlohy';

  @override
  String get deleteActionItemConfirmation =>
      'Naozaj chcete odstrániť túto položku úlohy? Túto akciu nemožno vrátiť späť.';

  @override
  String get enterActionItemDescription => 'Zadajte popis položky úlohy...';

  @override
  String get markAsCompleted => 'Označiť ako dokončené';

  @override
  String get setDueDateAndTime => 'Nastaviť termín a čas';

  @override
  String get reloadingApps => 'Opätovné načítanie aplikácií...';

  @override
  String get loadingApps => 'Načítanie aplikácií...';

  @override
  String get browseInstallCreateApps => 'Prechádzajte, inštalujte a vytvárajte aplikácie';

  @override
  String get all => 'Všetky';

  @override
  String get open => 'Otvoriť';

  @override
  String get install => 'Inštalovať';

  @override
  String get noAppsAvailable => 'Nie sú k dispozícii žiadne aplikácie';

  @override
  String get unableToLoadApps => 'Nepodarilo sa načítať aplikácie';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'Skúste upraviť vyhľadávacie výrazy alebo filtre';

  @override
  String get checkBackLaterForNewApps => 'Vráťte sa neskôr pre nové aplikácie';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'Skontrolujte prosím internetové pripojenie a skúste to znova';

  @override
  String get createNewApp => 'Vytvoriť novú aplikáciu';

  @override
  String get buildSubmitCustomOmiApp => 'Vytvorte a odošlite svoju vlastnú Omi aplikáciu';

  @override
  String get submittingYourApp => 'Odosielanie vašej aplikácie...';

  @override
  String get preparingFormForYou => 'Príprava formulára pre vás...';

  @override
  String get appDetails => 'Podrobnosti aplikácie';

  @override
  String get paymentDetails => 'Platobné údaje';

  @override
  String get previewAndScreenshots => 'Náhľad a snímky obrazovky';

  @override
  String get appCapabilities => 'Možnosti aplikácie';

  @override
  String get aiPrompts => 'AI výzvy';

  @override
  String get chatPrompt => 'Výzva chatu';

  @override
  String get chatPromptPlaceholder =>
      'Ste skvelá aplikácia, vašou úlohou je reagovať na otázky používateľov a dať im dobrý pocit...';

  @override
  String get conversationPrompt => 'Výzva konverzácie';

  @override
  String get conversationPromptPlaceholder => 'Ste skvelá aplikácia, dostanete prepis a zhrnutie konverzácie...';

  @override
  String get notificationScopes => 'Rozsahy oznámení';

  @override
  String get appPrivacyAndTerms => 'Ochrana súkromia a podmienky aplikácie';

  @override
  String get makeMyAppPublic => 'Zverejniť moju aplikáciu';

  @override
  String get submitAppTermsAgreement =>
      'Odoslaním tejto aplikácie súhlasím so Zmluvnými podmienkami a Zásadami ochrany osobných údajov Omi AI';

  @override
  String get submitApp => 'Odoslať aplikáciu';

  @override
  String get needHelpGettingStarted => 'Potrebujete pomoc so začatím?';

  @override
  String get clickHereForAppBuildingGuides => 'Kliknite sem pre návody na vytváranie aplikácií a dokumentáciu';

  @override
  String get submitAppQuestion => 'Odoslať aplikáciu?';

  @override
  String get submitAppPublicDescription =>
      'Vaša aplikácia bude skontrolovaná a zverejnená. Môžete ju začať používať okamžite, aj počas kontroly!';

  @override
  String get submitAppPrivateDescription =>
      'Vaša aplikácia bude skontrolovaná a sprístupnená vám súkromne. Môžete ju začať používať okamžite, aj počas kontroly!';

  @override
  String get startEarning => 'Začnite zarábať! 💰';

  @override
  String get connectStripeOrPayPal => 'Pripojte Stripe alebo PayPal, aby ste mohli prijímať platby za svoju aplikáciu.';

  @override
  String get connectNow => 'Pripojiť teraz';

  @override
  String installsCount(String count) {
    return '$count+ inštalácií';
  }

  @override
  String get uninstallApp => 'Odinštalovať aplikáciu';

  @override
  String get subscribe => 'Prihlásiť sa na odber';

  @override
  String get dataAccessNotice => 'Upozornenie na prístup k údajom';

  @override
  String get dataAccessWarning =>
      'Táto aplikácia bude mať prístup k vašim údajom. Omi AI nie je zodpovedný za to, ako táto aplikácia používa, upravuje alebo maže vaše údaje';

  @override
  String get installApp => 'Inštalovať aplikáciu';

  @override
  String get betaTesterNotice => 'Ste beta tester tejto aplikácie. Ešte nie je verejná. Bude verejná po schválení.';

  @override
  String get appUnderReviewOwner => 'Vaša aplikácia je v recenzii a viditeľná len pre vás. Bude verejná po schválení.';

  @override
  String get appRejectedNotice =>
      'Vaša aplikácia bola zamietnutá. Aktualizujte prosím podrobnosti aplikácie a odošlite ju znova na recenziu.';

  @override
  String get setupSteps => 'Kroky nastavenia';

  @override
  String get setupInstructions => 'Pokyny na nastavenie';

  @override
  String get integrationInstructions => 'Pokyny na integráciu';

  @override
  String get preview => 'Náhľad';

  @override
  String get aboutTheApp => 'O aplikácii';

  @override
  String get aboutThePersona => 'O persóne';

  @override
  String get chatPersonality => 'Osobnosť chatu';

  @override
  String get ratingsAndReviews => 'Hodnotenia a recenzie';

  @override
  String get noRatings => 'žiadne hodnotenia';

  @override
  String ratingsCount(String count) {
    return '$count+ hodnotení';
  }

  @override
  String get errorActivatingApp => 'Chyba pri aktivácii aplikácie';

  @override
  String get integrationSetupRequired => 'Ak sa jedná o integračnú aplikáciu, uistite sa, že je nastavenie dokončené.';

  @override
  String get installed => 'Nainštalované';

  @override
  String get appIdLabel => 'ID aplikácie';

  @override
  String get appNameLabel => 'Názov aplikácie';

  @override
  String get appNamePlaceholder => 'Moja úžasná aplikácia';

  @override
  String get pleaseEnterAppName => 'Zadajte prosím názov aplikácie';

  @override
  String get categoryLabel => 'Kategória';

  @override
  String get selectCategory => 'Vyberte kategóriu';

  @override
  String get descriptionLabel => 'Popis';

  @override
  String get appDescriptionPlaceholder =>
      'Moja úžasná aplikácia je skvelá aplikácia, ktorá robí úžasné veci. Je to najlepšia aplikácia!';

  @override
  String get pleaseProvideValidDescription => 'Zadajte prosím platný popis';

  @override
  String get appPricingLabel => 'Cena aplikácie';

  @override
  String get noneSelected => 'Nič nevybrané';

  @override
  String get appIdCopiedToClipboard => 'ID aplikácie skopírované do schránky';

  @override
  String get appCategoryModalTitle => 'Kategória aplikácie';

  @override
  String get pricingFree => 'Zadarmo';

  @override
  String get pricingPaid => 'Platené';

  @override
  String get loadingCapabilities => 'Načítavajú sa funkcie...';

  @override
  String get filterInstalled => 'Nainštalované';

  @override
  String get filterMyApps => 'Moje aplikácie';

  @override
  String get clearSelection => 'Vymazať výber';

  @override
  String get filterCategory => 'Kategória';

  @override
  String get rating4PlusStars => '4+ hviezdičiek';

  @override
  String get rating3PlusStars => '3+ hviezdičiek';

  @override
  String get rating2PlusStars => '2+ hviezdičiek';

  @override
  String get rating1PlusStars => '1+ hviezdička';

  @override
  String get filterRating => 'Hodnotenie';

  @override
  String get filterCapabilities => 'Funkcie';

  @override
  String get noNotificationScopesAvailable => 'Nie sú k dispozícii žiadne rozsahy oznámení';

  @override
  String get popularApps => 'Obľúbené aplikácie';

  @override
  String get pleaseProvidePrompt => 'Zadajte prosím výzvu';

  @override
  String chatWithAppName(String appName) {
    return 'Chat s $appName';
  }

  @override
  String get defaultAiAssistant => 'Predvolený AI asistent';

  @override
  String get readyToChat => '✨ Pripravený na chat!';

  @override
  String get connectionNeeded => '🌐 Vyžaduje sa pripojenie';

  @override
  String get startConversation => 'Začnite konverzáciu a nechajte kúzlo začať';

  @override
  String get checkInternetConnection => 'Skontrolujte prosím internetové pripojenie';

  @override
  String get wasThisHelpful => 'Bolo to užitočné?';

  @override
  String get thankYouForFeedback => 'Ďakujeme za spätnú väzbu!';

  @override
  String get maxFilesUploadError => 'Naraz môžete nahrať iba 4 súbory';

  @override
  String get attachedFiles => '📎 Priložené súbory';

  @override
  String get takePhoto => 'Odfotiť';

  @override
  String get captureWithCamera => 'Zachytiť kamerou';

  @override
  String get selectImages => 'Vybrať obrázky';

  @override
  String get chooseFromGallery => 'Vybrať z galérie';

  @override
  String get selectFile => 'Vybrať súbor';

  @override
  String get chooseAnyFileType => 'Vybrať akýkoľvek typ súboru';

  @override
  String get cannotReportOwnMessages => 'Nemôžete nahlásiť vlastné správy';

  @override
  String get messageReportedSuccessfully => '✅ Správa úspešne nahlásená';

  @override
  String get confirmReportMessage => 'Naozaj chcete nahlásiť túto správu?';

  @override
  String get selectChatAssistant => 'Vybrať chatovacieho asistenta';

  @override
  String get enableMoreApps => 'Povoliť viac aplikácií';

  @override
  String get chatCleared => 'Chat vymazaný';

  @override
  String get clearChatTitle => 'Vymazať chat?';

  @override
  String get confirmClearChat => 'Naozaj chcete vymazať chat? Túto akciu nemožno vrátiť späť.';

  @override
  String get copy => 'Kopírovať';

  @override
  String get share => 'Zdieľať';

  @override
  String get report => 'Nahlásiť';

  @override
  String get microphonePermissionRequired => 'Na hlasový záznam je potrebné povolenie mikrofónu.';

  @override
  String get microphonePermissionDenied =>
      'Povolenie mikrofónu zamietnuté. Udeľte prosím povolenie v Predvoľby systému > Súkromie a bezpečnosť > Mikrofón.';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'Nepodarilo sa skontrolovať povolenie mikrofónu: $error';
  }

  @override
  String get failedToTranscribeAudio => 'Nepodarilo sa prepísať zvuk';

  @override
  String get transcribing => 'Prepisovanie...';

  @override
  String get transcriptionFailed => 'Prepis zlyhal';

  @override
  String get discardedConversation => 'Zahodená konverzácia';

  @override
  String get at => 'o';

  @override
  String get from => 'od';

  @override
  String get copied => 'Skopírované!';

  @override
  String get copyLink => 'Kopírovať odkaz';

  @override
  String get hideTranscript => 'Skryť prepis';

  @override
  String get viewTranscript => 'Zobraziť prepis';

  @override
  String get conversationDetails => 'Detaily konverzácie';

  @override
  String get transcript => 'Prepis';

  @override
  String segmentsCount(int count) {
    return '$count segmentov';
  }

  @override
  String get noTranscriptAvailable => 'Prepis nie je k dispozícii';

  @override
  String get noTranscriptMessage => 'Táto konverzácia nemá prepis.';

  @override
  String get conversationUrlCouldNotBeGenerated => 'URL konverzácie sa nedá vygenerovať.';

  @override
  String get failedToGenerateConversationLink => 'Nepodarilo sa vygenerovať odkaz na konverzáciu';

  @override
  String get failedToGenerateShareLink => 'Nepodarilo sa vygenerovať odkaz na zdieľanie';

  @override
  String get reloadingConversations => 'Opätovné načítanie konverzácií...';

  @override
  String get user => 'Používateľ';

  @override
  String get starred => 'S hviezdičkou';

  @override
  String get date => 'Dátum';

  @override
  String get noResultsFound => 'Nenašli sa žiadne výsledky';

  @override
  String get tryAdjustingSearchTerms => 'Skúste upraviť hľadané výrazy';

  @override
  String get starConversationsToFindQuickly => 'Označte konverzácie hviezdičkou, aby ste ich tu rýchlo našli';

  @override
  String noConversationsOnDate(String date) {
    return 'Žiadne konverzácie dňa $date';
  }

  @override
  String get trySelectingDifferentDate => 'Skúste vybrať iný dátum';

  @override
  String get conversations => 'Konverzácie';

  @override
  String get chat => 'Chat';

  @override
  String get actions => 'Akcie';

  @override
  String get syncAvailable => 'Synchronizácia k dispozícii';

  @override
  String get referAFriend => 'Odporučiť priateľovi';

  @override
  String get help => 'Pomoc';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'Upgrade na Pro';

  @override
  String get getOmiDevice => 'Získať zariadenie Omi';

  @override
  String get wearableAiCompanion => 'Nositeľný AI spoločník';

  @override
  String get loadingMemories => 'Načítavanie spomienok...';

  @override
  String get allMemories => 'Všetky spomienky';

  @override
  String get aboutYou => 'O vás';

  @override
  String get manual => 'Manuálne';

  @override
  String get loadingYourMemories => 'Načítavanie vašich spomienok...';

  @override
  String get createYourFirstMemory => 'Vytvorte svoju prvú spomienku a začnite';

  @override
  String get tryAdjustingFilter => 'Skúste upraviť vyhľadávanie alebo filter';

  @override
  String get whatWouldYouLikeToRemember => 'Čo by ste si chceli zapamätať?';

  @override
  String get category => 'Kategória';

  @override
  String get public => 'Verejná';

  @override
  String get failedToSaveCheckConnection => 'Uloženie zlyhalo. Skontrolujte pripojenie.';

  @override
  String get createMemory => 'Vytvoriť pamäť';

  @override
  String get deleteMemoryConfirmation => 'Naozaj chcete odstrániť túto pamäť? Túto akciu nie je možné vrátiť späť.';

  @override
  String get makePrivate => 'Nastaviť ako súkromné';

  @override
  String get organizeAndControlMemories => 'Organizujte a ovládajte svoje spomienky';

  @override
  String get total => 'Celkom';

  @override
  String get makeAllMemoriesPrivate => 'Nastaviť všetky spomienky ako súkromné';

  @override
  String get setAllMemoriesToPrivate => 'Nastaviť všetky spomienky na súkromnú viditeľnosť';

  @override
  String get makeAllMemoriesPublic => 'Nastaviť všetky spomienky ako verejné';

  @override
  String get setAllMemoriesToPublic => 'Nastaviť všetky spomienky na verejnú viditeľnosť';

  @override
  String get permanentlyRemoveAllMemories => 'Trvalo odstrániť všetky spomienky z Omi';

  @override
  String get allMemoriesAreNowPrivate => 'Všetky spomienky sú teraz súkromné';

  @override
  String get allMemoriesAreNowPublic => 'Všetky spomienky sú teraz verejné';

  @override
  String get clearOmisMemory => 'Vymazať pamäť Omi';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Naozaj chcete vymazať pamäť Omi? Túto akciu nie je možné vrátiť späť a trvalo odstráni všetkých $count spomienok.';
  }

  @override
  String get omisMemoryCleared => 'Pamäť Omi o vás bola vymazaná';

  @override
  String get welcomeToOmi => 'Vitajte v Omi';

  @override
  String get continueWithApple => 'Pokračovať s Apple';

  @override
  String get continueWithGoogle => 'Pokračovať s Google';

  @override
  String get byContinuingYouAgree => 'Pokračovaním súhlasíte s našimi ';

  @override
  String get termsOfService => 'Podmienkami služby';

  @override
  String get and => ' a ';

  @override
  String get dataAndPrivacy => 'Dáta a súkromie';

  @override
  String get secureAuthViaAppleId => 'Bezpečné overenie cez Apple ID';

  @override
  String get secureAuthViaGoogleAccount => 'Bezpečné overenie cez účet Google';

  @override
  String get whatWeCollect => 'Čo zbierame';

  @override
  String get dataCollectionMessage =>
      'Pokračovaním budú vaše konverzácie, nahrávky a osobné údaje bezpečne uložené na našich serveroch, aby poskytli prehľady založené na AI a umožnili všetky funkcie aplikácie.';

  @override
  String get dataProtection => 'Ochrana dát';

  @override
  String get yourDataIsProtected => 'Vaše dáta sú chránené a riadia sa našimi ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'Prosím vyberte svoj primárny jazyk';

  @override
  String get chooseYourLanguage => 'Vyberte si svoj jazyk';

  @override
  String get selectPreferredLanguageForBestExperience => 'Vyberte si preferovaný jazyk pre najlepší Omi zážitok';

  @override
  String get searchLanguages => 'Hľadať jazyky...';

  @override
  String get selectALanguage => 'Vyberte jazyk';

  @override
  String get tryDifferentSearchTerm => 'Skúste iný vyhľadávací výraz';

  @override
  String get pleaseEnterYourName => 'Prosím zadajte svoje meno';

  @override
  String get nameMustBeAtLeast2Characters => 'Meno musí mať aspoň 2 znaky';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'Povedzte nám, ako by ste chceli byť oslovovaní. To pomáha prispôsobiť váš Omi zážitok.';

  @override
  String charactersCount(int count) {
    return '$count znakov';
  }

  @override
  String get enableFeaturesForBestExperience => 'Povoľte funkcie pre najlepší Omi zážitok na vašom zariadení.';

  @override
  String get microphoneAccess => 'Prístup k mikrofónu';

  @override
  String get recordAudioConversations => 'Nahrávať audio konverzácie';

  @override
  String get microphoneAccessDescription =>
      'Omi potrebuje prístup k mikrofónu na nahrávanie vašich konverzácií a poskytovanie prepisov.';

  @override
  String get screenRecording => 'Záznam obrazovky';

  @override
  String get captureSystemAudioFromMeetings => 'Zachytiť systémový zvuk zo schôdzok';

  @override
  String get screenRecordingDescription =>
      'Omi potrebuje povolenie na záznam obrazovky na zachytenie systémového zvuku z vašich schôdzok v prehliadači.';

  @override
  String get accessibility => 'Prístupnosť';

  @override
  String get detectBrowserBasedMeetings => 'Detekovať schôdzky v prehliadači';

  @override
  String get accessibilityDescription =>
      'Omi potrebuje povolenie prístupnosti na detekciu, kedy sa pripájate k schôdzkam Zoom, Meet alebo Teams vo vašom prehliadači.';

  @override
  String get pleaseWait => 'Prosím čakajte...';

  @override
  String get joinTheCommunity => 'Pripojte sa ku komunite!';

  @override
  String get loadingProfile => 'Načítavanie profilu...';

  @override
  String get profileSettings => 'Nastavenia profilu';

  @override
  String get noEmailSet => 'Email nie je nastavený';

  @override
  String get userIdCopiedToClipboard => 'ID používateľa skopírované';

  @override
  String get yourInformation => 'Vaše Informácie';

  @override
  String get setYourName => 'Nastaviť svoje meno';

  @override
  String get changeYourName => 'Zmeniť svoje meno';

  @override
  String get manageYourOmiPersona => 'Spravovať svoju Omi personu';

  @override
  String get voiceAndPeople => 'Hlas a Ľudia';

  @override
  String get teachOmiYourVoice => 'Naučiť Omi svoj hlas';

  @override
  String get tellOmiWhoSaidIt => 'Povedzte Omi, kto to povedal 🗣️';

  @override
  String get payment => 'Platba';

  @override
  String get addOrChangeYourPaymentMethod => 'Pridať alebo zmeniť platobnú metódu';

  @override
  String get preferences => 'Predvoľby';

  @override
  String get helpImproveOmiBySharing => 'Pomôžte vylepšiť Omi zdieľaním anonymizovaných analytických dát';

  @override
  String get deleteAccount => 'Zmazať Účet';

  @override
  String get deleteYourAccountAndAllData => 'Vymazať účet a všetky údaje';

  @override
  String get clearLogs => 'Vymazať denníky';

  @override
  String get debugLogsCleared => 'Protokoly ladenia vymazané';

  @override
  String get exportConversations => 'Exportovať konverzácie';

  @override
  String get exportAllConversationsToJson => 'Exportujte všetky svoje konverzácie do súboru JSON.';

  @override
  String get conversationsExportStarted => 'Export konverzácií začal. Môže to trvať niekoľko sekúnd, prosím čakajte.';

  @override
  String get mcpDescription =>
      'Na pripojenie Omi k iným aplikáciám na čítanie, vyhľadávanie a správu vašich spomienok a konverzácií. Vytvorte kľúč na začatie.';

  @override
  String get apiKeys => 'API kľúče';

  @override
  String errorLabel(String error) {
    return 'Chyba: $error';
  }

  @override
  String get noApiKeysFound => 'Nenašli sa žiadne API kľúče. Vytvorte jeden na začatie.';

  @override
  String get advancedSettings => 'Pokročilé nastavenia';

  @override
  String get triggersWhenNewConversationCreated => 'Spustí sa pri vytvorení novej konverzácie.';

  @override
  String get triggersWhenNewTranscriptReceived => 'Spustí sa pri prijatí nového prepisu.';

  @override
  String get realtimeAudioBytes => 'Zvukové bajty v reálnom čase';

  @override
  String get triggersWhenAudioBytesReceived => 'Spustí sa pri prijatí zvukových bajtov.';

  @override
  String get everyXSeconds => 'Každých x sekúnd';

  @override
  String get triggersWhenDaySummaryGenerated => 'Spustí sa pri vytvorení denného súhrnu.';

  @override
  String get tryLatestExperimentalFeatures => 'Vyskúšajte najnovšie experimentálne funkcie od tímu Omi.';

  @override
  String get transcriptionServiceDiagnosticStatus => 'Diagnostický stav služby prepisu';

  @override
  String get enableDetailedDiagnosticMessages => 'Povoliť podrobné diagnostické správy zo služby prepisu';

  @override
  String get autoCreateAndTagNewSpeakers => 'Automaticky vytvárať a označovať nových rečníkov';

  @override
  String get automaticallyCreateNewPerson => 'Automaticky vytvoriť novú osobu, keď je v prepise zistené meno.';

  @override
  String get pilotFeatures => 'Pilotné funkcie';

  @override
  String get pilotFeaturesDescription => 'Tieto funkcie sú testy a podpora nie je zaručená.';

  @override
  String get suggestFollowUpQuestion => 'Navrhnúť následnú otázku';

  @override
  String get saveSettings => 'Uložiť Nastavenia';

  @override
  String get syncingDeveloperSettings => 'Synchronizácia nastavení vývojára...';

  @override
  String get summary => 'Zhrnutie';

  @override
  String get auto => 'Automaticky';

  @override
  String get noSummaryForApp =>
      'Pre túto aplikáciu nie je k dispozícii žiadne zhrnutie. Skúste inú aplikáciu pre lepšie výsledky.';

  @override
  String get tryAnotherApp => 'Vyskúšať inú aplikáciu';

  @override
  String generatedBy(String appName) {
    return 'Vygenerované aplikáciou $appName';
  }

  @override
  String get overview => 'Prehľad';

  @override
  String get otherAppResults => 'Výsledky z iných aplikácií';

  @override
  String get unknownApp => 'Neznáma aplikácia';

  @override
  String get noSummaryAvailable => 'Nie je k dispozícii žiadne zhrnutie';

  @override
  String get conversationNoSummaryYet => 'Táto konverzácia ešte nemá zhrnutie.';

  @override
  String get chooseSummarizationApp => 'Vybrať aplikáciu na zhrnutie';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return 'Aplikácia $appName nastavená ako predvolená aplikácia na zhrnutie';
  }

  @override
  String get letOmiChooseAutomatically => 'Nechajte Omi automaticky vybrať najlepšiu aplikáciu';

  @override
  String get deleteConversationConfirmation =>
      'Naozaj chcete odstrániť túto konverzáciu? Túto akciu nemožno vrátiť späť.';

  @override
  String get conversationDeleted => 'Konverzácia odstránená';

  @override
  String get generatingLink => 'Generovanie odkazu...';

  @override
  String get editConversation => 'Upraviť konverzáciu';

  @override
  String get conversationLinkCopiedToClipboard => 'Odkaz na konverzáciu skopírovaný do schránky';

  @override
  String get conversationTranscriptCopiedToClipboard => 'Prepis konverzácie skopírovaný do schránky';

  @override
  String get editConversationDialogTitle => 'Upraviť konverzáciu';

  @override
  String get changeTheConversationTitle => 'Zmeniť názov konverzácie';

  @override
  String get conversationTitle => 'Názov konverzácie';

  @override
  String get enterConversationTitle => 'Zadajte názov konverzácie...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'Názov konverzácie úspešne aktualizovaný';

  @override
  String get failedToUpdateConversationTitle => 'Nepodarilo sa aktualizovať názov konverzácie';

  @override
  String get errorUpdatingConversationTitle => 'Chyba pri aktualizácii názvu konverzácie';

  @override
  String get settingUp => 'Nastavovanie...';

  @override
  String get startYourFirstRecording => 'Začnite svoj prvý záznam';

  @override
  String get preparingSystemAudioCapture => 'Príprava záznamu systémového zvuku';

  @override
  String get clickTheButtonToCaptureAudio =>
      'Kliknite na tlačidlo na záznam zvuku pre živé prepisy, AI poznatky a automatické ukladanie.';

  @override
  String get reconnecting => 'Opätovné pripájanie...';

  @override
  String get recordingPaused => 'Záznam pozastavený';

  @override
  String get recordingActive => 'Záznam aktívny';

  @override
  String get startRecording => 'Spustiť záznam';

  @override
  String resumingInCountdown(String countdown) {
    return 'Pokračovanie za ${countdown}s...';
  }

  @override
  String get tapPlayToResume => 'Klepnite na prehrať pre pokračovanie';

  @override
  String get listeningForAudio => 'Počúvanie zvuku...';

  @override
  String get preparingAudioCapture => 'Príprava záznamu zvuku';

  @override
  String get clickToBeginRecording => 'Kliknite pre začatie záznamu';

  @override
  String get translated => 'preložené';

  @override
  String get liveTranscript => 'Živý prepis';

  @override
  String segmentsSingular(String count) {
    return '$count segment';
  }

  @override
  String segmentsPlural(String count) {
    return '$count segmentov';
  }

  @override
  String get startRecordingToSeeTranscript => 'Spustite záznam pre zobrazenie živého prepisu';

  @override
  String get paused => 'Pozastavené';

  @override
  String get initializing => 'Inicializácia...';

  @override
  String get recording => 'Nahrávanie';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'Mikrofón zmenený. Pokračovanie za ${countdown}s';
  }

  @override
  String get clickPlayToResumeOrStop => 'Kliknite na prehrať pre pokračovanie alebo zastaviť pre dokončenie';

  @override
  String get settingUpSystemAudioCapture => 'Nastavenie záznamu systémového zvuku';

  @override
  String get capturingAudioAndGeneratingTranscript => 'Záznam zvuku a generovanie prepisu';

  @override
  String get clickToBeginRecordingSystemAudio => 'Kliknite pre začatie záznamu systémového zvuku';

  @override
  String get you => 'Vy';

  @override
  String speakerWithId(String speakerId) {
    return 'Hovorca $speakerId';
  }

  @override
  String get translatedByOmi => 'preložené pomocou omi';

  @override
  String get backToConversations => 'Späť na konverzácie';

  @override
  String get systemAudio => 'Systém';

  @override
  String get mic => 'Mikrofón';

  @override
  String audioInputSetTo(String deviceName) {
    return 'Vstup zvuku nastavený na $deviceName';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'Chyba pri prepínaní zvukového zariadenia: $error';
  }

  @override
  String get selectAudioInput => 'Vyberte vstup zvuku';

  @override
  String get loadingDevices => 'Načítavanie zariadení...';

  @override
  String get settingsHeader => 'NASTAVENIA';

  @override
  String get plansAndBilling => 'Plány a Fakturácia';

  @override
  String get calendarIntegration => 'Integrácia Kalendára';

  @override
  String get dailySummary => 'Denný Súhrn';

  @override
  String get developer => 'Vývojár';

  @override
  String get about => 'O aplikácii';

  @override
  String get selectTime => 'Vybrať Čas';

  @override
  String get accountGroup => 'Účet';

  @override
  String get signOutQuestion => 'Odhlásiť Sa?';

  @override
  String get signOutConfirmation => 'Naozaj sa chcete odhlásiť?';

  @override
  String get customVocabularyHeader => 'VLASTNÝ SLOVNÍK';

  @override
  String get addWordsDescription => 'Pridajte slová, ktoré má Omi rozpoznávať počas prepisu.';

  @override
  String get enterWordsHint => 'Zadajte slová (oddelené čiarkami)';

  @override
  String get dailySummaryHeader => 'DENNÝ SÚHRN';

  @override
  String get dailySummaryTitle => 'Denný Súhrn';

  @override
  String get dailySummaryDescription => 'Získajte personalizovaný súhrn vašich konverzácií';

  @override
  String get deliveryTime => 'Čas Doručenia';

  @override
  String get deliveryTimeDescription => 'Kedy prijímať denný súhrn';

  @override
  String get subscription => 'Predplatné';

  @override
  String get viewPlansAndUsage => 'Zobraziť Plány a Využitie';

  @override
  String get viewPlansDescription => 'Spravujte svoje predplatné a pozrite si štatistiky využitia';

  @override
  String get addOrChangePaymentMethod => 'Pridajte alebo zmeňte svoju platobnú metódu';

  @override
  String get displayOptions => 'Možnosti zobrazenia';

  @override
  String get showMeetingsInMenuBar => 'Zobraziť stretnutia v paneli ponúk';

  @override
  String get displayUpcomingMeetingsDescription => 'Zobraziť nadchádzajúce stretnutia v paneli ponúk';

  @override
  String get showEventsWithoutParticipants => 'Zobraziť udalosti bez účastníkov';

  @override
  String get includePersonalEventsDescription => 'Zahrnúť osobné udalosti bez účastníkov';

  @override
  String get upcomingMeetings => 'NADCHÁDZAJÚCE STRETNUTIA';

  @override
  String get checkingNext7Days => 'Kontrola nasledujúcich 7 dní';

  @override
  String get shortcuts => 'Klávesové skratky';

  @override
  String get shortcutChangeInstruction => 'Kliknite na skratku a zmeňte ju. Stlačením Escape zrušíte.';

  @override
  String get configurePersonaDescription => 'Nakonfigurujte svoju AI personu';

  @override
  String get configureSTTProvider => 'Nakonfigurujte poskytovateľa STT';

  @override
  String get setConversationEndDescription => 'Nastavte, kedy sa konverzácie automaticky ukončia';

  @override
  String get importDataDescription => 'Importovať dáta z iných zdrojov';

  @override
  String get exportConversationsDescription => 'Exportovať konverzácie do JSON';

  @override
  String get exportingConversations => 'Exportovanie konverzácií...';

  @override
  String get clearNodesDescription => 'Vymazať všetky uzly a pripojenia';

  @override
  String get deleteKnowledgeGraphQuestion => 'Vymazať graf znalostí?';

  @override
  String get deleteKnowledgeGraphWarning =>
      'Tým sa vymažú všetky odvodené údaje grafu znalostí. Vaše pôvodné spomienky zostanú v bezpečí.';

  @override
  String get connectOmiWithAI => 'Pripojte Omi k AI asistentom';

  @override
  String get noAPIKeys => 'Žiadne kľúče API. Vytvorte jeden na začatie.';

  @override
  String get autoCreateWhenDetected => 'Automaticky vytvoriť pri detekcii mena';

  @override
  String get trackPersonalGoals => 'Sledovať osobné ciele na domovskej stránke';

  @override
  String get dailyReflectionDescription => 'Pripomienka o 21:00 na zamyslenie sa nad vaším dňom';

  @override
  String get endpointURL => 'URL koncového bodu';

  @override
  String get links => 'Odkazy';

  @override
  String get discordMemberCount => 'Viac ako 8000 členov na Discorde';

  @override
  String get userInformation => 'Informácie o používateľovi';

  @override
  String get capabilities => 'Schopnosti';

  @override
  String get previewScreenshots => 'Náhľad snímok obrazovky';

  @override
  String get holdOnPreparingForm => 'Počkajte, pripravujeme pre vás formulár';

  @override
  String get bySubmittingYouAgreeToOmi => 'Odoslaním súhlasíte s Omi ';

  @override
  String get termsAndPrivacyPolicy => 'Podmienky a Zásady ochrany osobných údajov';

  @override
  String get helpsDiagnoseIssuesAutoDeletes => 'Pomáha diagnostikovať problémy. Automaticky sa vymaže po 3 dňoch.';

  @override
  String get manageYourApp => 'Spravujte svoju aplikáciu';

  @override
  String get updatingYourApp => 'Aktualizácia vašej aplikácie';

  @override
  String get fetchingYourAppDetails => 'Načítanie podrobností aplikácie';

  @override
  String get updateAppQuestion => 'Aktualizovať aplikáciu?';

  @override
  String get updateAppConfirmation =>
      'Ste si istý, že chcete aktualizovať svoju aplikáciu? Zmeny sa prejavia po kontrole naším tímom.';

  @override
  String get updateApp => 'Aktualizovať aplikáciu';

  @override
  String get createAndSubmitNewApp => 'Vytvorte a odošlite novú aplikáciu';

  @override
  String appsCount(String count) {
    return 'Aplikácie ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'Súkromné aplikácie ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'Verejné aplikácie ($count)';
  }

  @override
  String get newVersionAvailable => 'K dispozícii je nová verzia  🎉';

  @override
  String get no => 'Nie';

  @override
  String get subscriptionCancelledSuccessfully =>
      'Predplatné bolo úspešne zrušené. Zostane aktívne do konca aktuálneho fakturačného obdobia.';

  @override
  String get failedToCancelSubscription => 'Zrušenie predplatného zlyhalo. Skúste to prosím znova.';

  @override
  String get invalidPaymentUrl => 'Neplatná adresa URL platby';

  @override
  String get permissionsAndTriggers => 'Povolenia a spúšťače';

  @override
  String get chatFeatures => 'Funkcie chatu';

  @override
  String get uninstall => 'Odinštalovať';

  @override
  String get installs => 'INŠTALÁCIE';

  @override
  String get priceLabel => 'CENA';

  @override
  String get updatedLabel => 'AKTUALIZOVANÉ';

  @override
  String get createdLabel => 'VYTVORENÉ';

  @override
  String get featuredLabel => 'ODPORÚČANÉ';

  @override
  String get cancelSubscriptionQuestion => 'Zrušiť predplatné?';

  @override
  String get cancelSubscriptionConfirmation =>
      'Ste si istý, že chcete zrušiť predplatné? Budete mať prístup do konca aktuálneho fakturačného obdobia.';

  @override
  String get cancelSubscriptionButton => 'Zrušiť predplatné';

  @override
  String get cancelling => 'Rušenie...';

  @override
  String get betaTesterMessage => 'Ste beta tester tejto aplikácie. Zatiaľ nie je verejná. Bude verejná po schválení.';

  @override
  String get appUnderReviewMessage =>
      'Vaša aplikácia je v procese kontroly a viditeľná len pre vás. Bude verejná po schválení.';

  @override
  String get appRejectedMessage => 'Vaša aplikácia bola zamietnutá. Aktualizujte údaje a znova odošlite na kontrolu.';

  @override
  String get invalidIntegrationUrl => 'Neplatná adresa URL integrácie';

  @override
  String get tapToComplete => 'Klepnite pre dokončenie';

  @override
  String get invalidSetupInstructionsUrl => 'Neplatná adresa URL pokynov na nastavenie';

  @override
  String get pushToTalk => 'Stlačte pre hovorenie';

  @override
  String get summaryPrompt => 'Výzva na zhrnutie';

  @override
  String get pleaseSelectARating => 'Vyberte prosím hodnotenie';

  @override
  String get reviewAddedSuccessfully => 'Recenzia úspešne pridaná 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'Recenzia úspešne aktualizovaná 🚀';

  @override
  String get failedToSubmitReview => 'Odoslanie recenzie zlyhalo. Skúste to prosím znova.';

  @override
  String get addYourReview => 'Pridajte svoju recenziu';

  @override
  String get editYourReview => 'Upravte svoju recenziu';

  @override
  String get writeAReviewOptional => 'Napíšte recenziu (voliteľné)';

  @override
  String get submitReview => 'Odoslať recenziu';

  @override
  String get updateReview => 'Aktualizovať recenziu';

  @override
  String get yourReview => 'Vaša recenzia';

  @override
  String get anonymousUser => 'Anonymný používateľ';

  @override
  String get issueActivatingApp => 'Pri aktivácii tejto aplikácie došlo k problému. Skúste to prosím znova.';

  @override
  String get dataAccessNoticeDescription =>
      'This app will access your data. Omi AI is not responsible for how your data is used, modified, or deleted by this app';

  @override
  String get copyUrl => 'Kopírovať URL';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => 'Po';

  @override
  String get weekdayTue => 'Ut';

  @override
  String get weekdayWed => 'St';

  @override
  String get weekdayThu => 'Št';

  @override
  String get weekdayFri => 'Pi';

  @override
  String get weekdaySat => 'So';

  @override
  String get weekdaySun => 'Ne';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return 'Integrácia s $serviceName čoskoro';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'Už exportované do $platform';
  }

  @override
  String get anotherPlatform => 'inú platformu';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'Prosím overte sa pomocou $serviceName v Nastavenia > Integrácie úloh';
  }

  @override
  String addingToService(String serviceName) {
    return 'Pridávanie do $serviceName...';
  }

  @override
  String addedToService(String serviceName) {
    return 'Pridané do $serviceName';
  }

  @override
  String failedToAddToService(String serviceName) {
    return 'Nepodarilo sa pridať do $serviceName';
  }

  @override
  String get permissionDeniedForAppleReminders => 'Povolenie pre Apple Reminders zamietnuté';

  @override
  String failedToCreateApiKey(String error) {
    return 'Nepodarilo sa vytvoriť API kľúč poskytovateľa: $error';
  }

  @override
  String get createAKey => 'Vytvoriť kľúč';

  @override
  String get apiKeyRevokedSuccessfully => 'API kľúč bol úspešne odvolaný';

  @override
  String failedToRevokeApiKey(String error) {
    return 'Nepodarilo sa odvolať API kľúč: $error';
  }

  @override
  String get omiApiKeys => 'Omi API kľúče';

  @override
  String get apiKeysDescription =>
      'API kľúče sa používajú na overenie, keď vaša aplikácia komunikuje so serverom OMI. Umožňujú vašej aplikácii vytvárať spomienky a bezpečne pristupovať k ďalším službám OMI.';

  @override
  String get aboutOmiApiKeys => 'O Omi API kľúčoch';

  @override
  String get yourNewKey => 'Váš nový kľúč:';

  @override
  String get copyToClipboard => 'Kopírovať do schránky';

  @override
  String get pleaseCopyKeyNow => 'Prosím skopírujte si ho teraz a zapíšte si ho na bezpečné miesto. ';

  @override
  String get willNotSeeAgain => 'Nebudete ho môcť znova zobraziť.';

  @override
  String get revokeKey => 'Odvolať kľúč';

  @override
  String get revokeApiKeyQuestion => 'Odvolať API kľúč?';

  @override
  String get revokeApiKeyWarning =>
      'Túto akciu nie je možné vrátiť späť. Aplikácie používajúce tento kľúč už nebudú mať prístup k API.';

  @override
  String get revoke => 'Odvolať';
}
