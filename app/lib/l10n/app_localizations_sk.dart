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
  String get cancel => 'Cancel';

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
  String get copySummary => 'Kopírovať zhrnutie';

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
  String get clearChat => 'Vymazať chat';

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
  String get myApps => 'Moje aplikácie';

  @override
  String get installedApps => 'Nainštalované aplikácie';

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
  String get offlineSync => 'Offline Sync';

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
  String get off => 'Off';

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
  String get urlCopied => 'URL skopírovaná';

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
  String get editName => 'Edit Name';

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
  String get noUpcomingMeetings => 'Žiadne nadchádzajúce stretnutia';

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
  String deviceUsesCodec(String device, String reason) {
    return '$device používa $reason. Bude použité Omi.';
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
  String get speechProfileIntro => 'Omi potrebuje spoznať vaše ciele a váš hlas. Neskôr to budete môcť zmeniť.';

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
  String get retry => 'Retry';

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
  String get conversationUrlCouldNotBeShared => 'URL konverzácie sa nepodarilo zdieľať.';

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
  String get generateSummary => 'Vygenerovať súhrn';

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
  String get unknownDevice => 'Unknown';

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
    return '$label skopírované';
  }

  @override
  String get noApiKeysYet => 'Zatiaľ žiadne API kľúče. Vytvorte jeden pre integráciu s vašou aplikáciou.';

  @override
  String get createKeyToGetStarted => 'Vytvorte kľúč pre začatie';

  @override
  String get persona => 'Persona';

  @override
  String get configureYourAiPersona => 'Nakonfigurujte svoju AI osobnosť';

  @override
  String get configureSttProvider => 'Konfigurácia poskytovateľa STT';

  @override
  String get setWhenConversationsAutoEnd => 'Nastavte, kedy sa konverzácie automaticky ukončia';

  @override
  String get importDataFromOtherSources => 'Import údajov z iných zdrojov';

  @override
  String get debugAndDiagnostics => 'Ladenie a diagnostika';

  @override
  String get autoDeletesAfter3Days => 'Automatické vymazanie po 3 dňoch';

  @override
  String get helpsDiagnoseIssues => 'Pomáha diagnostikovať problémy';

  @override
  String get exportStartedMessage => 'Export sa začal. Môže to trvať niekoľko sekúnd...';

  @override
  String get exportConversationsToJson => 'Exportovať konverzácie do súboru JSON';

  @override
  String get knowledgeGraphDeletedSuccess => 'Graf znalostí bol úspešne odstránený';

  @override
  String failedToDeleteGraph(String error) {
    return 'Nepodarilo sa odstrániť graf: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'Vymazať všetky uzly a spojenia';

  @override
  String get addToClaudeDesktopConfig => 'Pridať do claude_desktop_config.json';

  @override
  String get connectAiAssistantsToData => 'Pripojte AI asistentov k vašim údajom';

  @override
  String get useYourMcpApiKey => 'Použite svoj MCP API kľúč';

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
  String get autoCreateWhenNameDetected => 'Automaticky vytvoriť pri zistení mena';

  @override
  String get followUpQuestions => 'Následné otázky';

  @override
  String get suggestQuestionsAfterConversations => 'Navrhovať otázky po konverzáciách';

  @override
  String get goalTracker => 'Sledovanie cieľov';

  @override
  String get trackPersonalGoalsOnHomepage => 'Sledujte svoje osobné ciele na domovskej stránke';

  @override
  String get dailyReflection => 'Denná reflexia';

  @override
  String get get9PmReminderToReflect => 'Dostávajte pripomienku o 21:00 na zamyslenie sa nad svojím dňom';

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
  String get current => 'Aktuálne';

  @override
  String get target => 'Cieľ';

  @override
  String get saveGoal => 'Uložiť';

  @override
  String get goals => 'Ciele';

  @override
  String get tapToAddGoal => 'Klepnutím pridajte cieľ';

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
  String get dailyScoreDescription => 'Skóre, ktoré vám pomôže lepšie\nsa sústrediť na plnenie.';

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
  String get all => 'All';

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
  String get installsCount => 'Inštalácie';

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
  String get getOmiDevice => 'Get Omi Device';

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
      'Pre túto aplikáciu nie je k dispozícii zhrnutie. Skúste inú aplikáciu pre lepšie výsledky.';

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
  String get dailySummary => 'Denný súhrn';

  @override
  String get developer => 'Vývojár';

  @override
  String get about => 'O aplikácii';

  @override
  String get selectTime => 'Vybrať čas';

  @override
  String get accountGroup => 'Účet';

  @override
  String get signOutQuestion => 'Odhlásiť sa?';

  @override
  String get signOutConfirmation => 'Are you sure you want to sign out?';

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
  String get dailySummaryDescription => 'Získajte personalizovaný súhrn konverzácií dňa ako upozornenie.';

  @override
  String get deliveryTime => 'Čas doručenia';

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
  String get upcomingMeetings => 'Nadchádzajúce stretnutia';

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
  String get dailyReflectionDescription =>
      'Získajte pripomienku o 21:00, aby ste sa zamysleli nad svojím dňom a zaznamenali myšlienky.';

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
  String get invalidIntegrationUrl => 'Neplatná URL integrácie';

  @override
  String get tapToComplete => 'Klepnite pre dokončenie';

  @override
  String get invalidSetupInstructionsUrl => 'Neplatná URL pokynov na nastavenie';

  @override
  String get pushToTalk => 'Stlačte pre hovor';

  @override
  String get summaryPrompt => 'Výzva na zhrnutie';

  @override
  String get pleaseSelectARating => 'Vyberte prosím hodnotenie';

  @override
  String get reviewAddedSuccessfully => 'Recenzia úspešne pridaná 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'Recenzia úspešne aktualizovaná 🚀';

  @override
  String get failedToSubmitReview => 'Nepodarilo sa odoslať recenziu. Skúste to znova.';

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

  @override
  String get whatWouldYouLikeToCreate => 'Čo by ste chceli vytvoriť?';

  @override
  String get createAnApp => 'Vytvoriť aplikáciu';

  @override
  String get createAndShareYourApp => 'Vytvorte a zdieľajte svoju aplikáciu';

  @override
  String get createMyClone => 'Vytvoriť môj klon';

  @override
  String get createYourDigitalClone => 'Vytvorte si digitálny klon';

  @override
  String get itemApp => 'Aplikácia';

  @override
  String get itemPersona => 'Persona';

  @override
  String keepItemPublic(String item) {
    return 'Ponechať $item verejnú';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return 'Zverejniť $item?';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return 'Zneverejniť $item?';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'Ak zverejníte $item, môže ju používať každý';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'Ak teraz zneverejníte $item, prestane fungovať pre všetkých a bude viditeľná len pre vás';
  }

  @override
  String get manageApp => 'Spravovať aplikáciu';

  @override
  String get updatePersonaDetails => 'Aktualizovať detaily persony';

  @override
  String deleteItemTitle(String item) {
    return 'Odstrániť $item';
  }

  @override
  String deleteItemQuestion(String item) {
    return 'Odstrániť $item?';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'Ste si istí, že chcete odstrániť túto $item? Túto akciu nie je možné vrátiť späť.';
  }

  @override
  String get revokeKeyQuestion => 'Odvolať kľúč?';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'Ste si istí, že chcete odvolať kľúč \"$keyName\"? Túto akciu nie je možné vrátiť späť.';
  }

  @override
  String get createNewKey => 'Vytvoriť nový kľúč';

  @override
  String get keyNameHint => 'napr. Claude Desktop';

  @override
  String get pleaseEnterAName => 'Prosím zadajte názov.';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'Nepodarilo sa vytvoriť kľúč: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'Nepodarilo sa vytvoriť kľúč. Skúste to prosím znova.';

  @override
  String get keyCreated => 'Kľúč vytvorený';

  @override
  String get keyCreatedMessage => 'Váš nový kľúč bol vytvorený. Prosím skopírujte si ho teraz. Už ho neuvidíte.';

  @override
  String get keyWord => 'Kľúč';

  @override
  String get externalAppAccess => 'Prístup externých aplikácií';

  @override
  String get externalAppAccessDescription =>
      'Nasledujúce nainštalované aplikácie majú externé integrácie a môžu pristupovať k vašim údajom, ako sú konverzácie a spomienky.';

  @override
  String get noExternalAppsHaveAccess => 'Žiadne externé aplikácie nemajú prístup k vašim údajom.';

  @override
  String get maximumSecurityE2ee => 'Maximálne zabezpečenie (E2EE)';

  @override
  String get e2eeDescription =>
      'End-to-end šifrovanie je zlatý štandard ochrany súkromia. Keď je povolené, vaše údaje sú šifrované na vašom zariadení pred odoslaním na naše servery. To znamená, že nikto, ani Omi, nemôže pristupovať k vášmu obsahu.';

  @override
  String get importantTradeoffs => 'Dôležité kompromisy:';

  @override
  String get e2eeTradeoff1 => '• Niektoré funkcie ako integrácie externých aplikácií môžu byť zakázané.';

  @override
  String get e2eeTradeoff2 => '• Ak stratíte heslo, vaše údaje nie je možné obnoviť.';

  @override
  String get featureComingSoon => 'Táto funkcia bude čoskoro k dispozícii!';

  @override
  String get migrationInProgressMessage => 'Migrácia prebieha. Úroveň ochrany nemôžete zmeniť, kým sa nedokončí.';

  @override
  String get migrationFailed => 'Migrácia zlyhala';

  @override
  String migratingFromTo(String source, String target) {
    return 'Migrácia z $source na $target';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total objektov';
  }

  @override
  String get secureEncryption => 'Bezpečné šifrovanie';

  @override
  String get secureEncryptionDescription =>
      'Vaše údaje sú šifrované kľúčom jedinečným pre vás na našich serveroch hostovaných v Google Cloud. To znamená, že váš surový obsah je neprístupný nikomu, vrátane zamestnancov Omi alebo Google, priamo z databázy.';

  @override
  String get endToEndEncryption => 'End-to-end šifrovanie';

  @override
  String get e2eeCardDescription =>
      'Povoľte pre maximálne zabezpečenie, kde iba vy máte prístup k vašim údajom. Klepnutím sa dozviete viac.';

  @override
  String get dataAlwaysEncrypted => 'Bez ohľadu na úroveň sú vaše údaje vždy šifrované v pokoji aj pri prenose.';

  @override
  String get readOnlyScope => 'Iba na čítanie';

  @override
  String get fullAccessScope => 'Plný prístup';

  @override
  String get readScope => 'Čítanie';

  @override
  String get writeScope => 'Zápis';

  @override
  String get apiKeyCreated => 'API kľúč vytvorený!';

  @override
  String get saveKeyWarning => 'Uložte si tento kľúč teraz! Znovu ho neuvidíte.';

  @override
  String get yourApiKey => 'VÁŠ API KĽÚČ';

  @override
  String get tapToCopy => 'Klepnutím skopírujete';

  @override
  String get copyKey => 'Kopírovať kľúč';

  @override
  String get createApiKey => 'Vytvoriť API kľúč';

  @override
  String get accessDataProgrammatically => 'Programovo pristupujte k svojim údajom';

  @override
  String get keyNameLabel => 'NÁZOV KĽÚČA';

  @override
  String get keyNamePlaceholder => 'napr., Moja integrácia aplikácie';

  @override
  String get permissionsLabel => 'OPRÁVNENIA';

  @override
  String get permissionsInfoNote => 'R = Čítanie, W = Zápis. Predvolené je iba na čítanie, ak nie je nič vybrané.';

  @override
  String get developerApi => 'Vývojárske API';

  @override
  String get createAKeyToGetStarted => 'Vytvorte kľúč pre začatie';

  @override
  String errorWithMessage(String error) {
    return 'Chyba: $error';
  }

  @override
  String get omiTraining => 'Tréning Omi';

  @override
  String get trainingDataProgram => 'Program tréningových dát';

  @override
  String get getOmiUnlimitedFree => 'Získajte Omi Unlimited zadarmo prispením vašich dát na trénovanie AI modelov.';

  @override
  String get trainingDataBullets =>
      '• Vaše dáta pomáhajú zlepšovať AI modely\n• Zdieľajú sa len necitlivé dáta\n• Úplne transparentný proces';

  @override
  String get learnMoreAtOmiTraining => 'Zistite viac na omi.me/training';

  @override
  String get agreeToContributeData => 'Rozumiem a súhlasím s prispením mojich dát na trénovanie AI';

  @override
  String get submitRequest => 'Odoslať žiadosť';

  @override
  String get thankYouRequestUnderReview => 'Ďakujeme! Vaša žiadosť sa posudzuje. Po schválení vás upozorníme.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'Váš plán zostane aktívny do $date. Potom stratíte prístup k neobmedzeným funkciám. Ste si istí?';
  }

  @override
  String get confirmCancellation => 'Potvrdiť zrušenie';

  @override
  String get keepMyPlan => 'Ponechať môj plán';

  @override
  String get subscriptionSetToCancel => 'Vaše predplatné je nastavené na zrušenie na konci obdobia.';

  @override
  String get switchedToOnDevice => 'Prepnuté na prepis na zariadení';

  @override
  String get couldNotSwitchToFreePlan => 'Nepodarilo sa prepnúť na bezplatný plán. Skúste to prosím znova.';

  @override
  String get couldNotLoadPlans => 'Nepodarilo sa načítať dostupné plány. Skúste to prosím znova.';

  @override
  String get selectedPlanNotAvailable => 'Vybraný plán nie je k dispozícii. Skúste to prosím znova.';

  @override
  String get upgradeToAnnualPlan => 'Upgradovať na ročný plán';

  @override
  String get importantBillingInfo => 'Dôležité informácie o fakturácii:';

  @override
  String get monthlyPlanContinues => 'Váš súčasný mesačný plán bude pokračovať do konca fakturačného obdobia';

  @override
  String get paymentMethodCharged =>
      'Váš existujúci spôsob platby bude automaticky účtovaný po skončení mesačného plánu';

  @override
  String get annualSubscriptionStarts => 'Vaše 12-mesačné ročné predplatné sa automaticky spustí po zaúčtovaní';

  @override
  String get thirteenMonthsCoverage => 'Získate celkom 13 mesiacov pokrytia (aktuálny mesiac + 12 mesiacov ročne)';

  @override
  String get confirmUpgrade => 'Potvrdiť upgrade';

  @override
  String get confirmPlanChange => 'Potvrdiť zmenu plánu';

  @override
  String get confirmAndProceed => 'Potvrdiť a pokračovať';

  @override
  String get upgradeScheduled => 'Upgrade naplánovaný';

  @override
  String get changePlan => 'Zmeniť plán';

  @override
  String get upgradeAlreadyScheduled => 'Váš upgrade na ročný plán je už naplánovaný';

  @override
  String get youAreOnUnlimitedPlan => 'Ste na pláne Unlimited.';

  @override
  String get yourOmiUnleashed => 'Váš Omi, uvoľnený. Prejdite na neobmedzený pre nekonečné možnosti.';

  @override
  String planEndedOn(String date) {
    return 'Váš plán skončil $date.\\nZnova sa prihláste teraz - budete okamžite účtovaní za nové fakturačné obdobie.';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'Váš plán je nastavený na zrušenie $date.\\nZnova sa prihláste teraz, aby ste si zachovali výhody - bez poplatku do $date.';
  }

  @override
  String get annualPlanStartsAutomatically => 'Váš ročný plán sa automaticky spustí po skončení mesačného plánu.';

  @override
  String planRenewsOn(String date) {
    return 'Váš plán sa obnovuje $date.';
  }

  @override
  String get unlimitedConversations => 'Neobmedzené konverzácie';

  @override
  String get askOmiAnything => 'Opýtajte sa Omi čokoľvek o svojom živote';

  @override
  String get unlockOmiInfiniteMemory => 'Odomknite nekonečnú pamäť Omi';

  @override
  String get youreOnAnnualPlan => 'Ste na ročnom pláne';

  @override
  String get alreadyBestValuePlan => 'Už máte plán s najlepšou hodnotou. Nie sú potrebné žiadne zmeny.';

  @override
  String get unableToLoadPlans => 'Nedá sa načítať plány';

  @override
  String get checkConnectionTryAgain => 'Skontrolujte pripojenie a skúste to znova';

  @override
  String get useFreePlan => 'Použiť bezplatný plán';

  @override
  String get continueText => 'Pokračovať';

  @override
  String get resubscribe => 'Znova sa prihlásiť';

  @override
  String get couldNotOpenPaymentSettings => 'Nepodarilo sa otvoriť nastavenia platby. Skúste to prosím znova.';

  @override
  String get managePaymentMethod => 'Spravovať spôsob platby';

  @override
  String get cancelSubscription => 'Zrušiť predplatné';

  @override
  String endsOnDate(String date) {
    return 'Končí $date';
  }

  @override
  String get active => 'Aktívny';

  @override
  String get freePlan => 'Bezplatný plán';

  @override
  String get configure => 'Konfigurovať';

  @override
  String get privacyInformation => 'Informácie o súkromí';

  @override
  String get yourPrivacyMattersToUs => 'Na vašom súkromí nám záleží';

  @override
  String get privacyIntroText =>
      'V Omi berieme vaše súkromie veľmi vážne. Chceme byť transparentní ohľadom údajov, ktoré zhromažďujeme a ako ich používame. Tu je to, čo potrebujete vedieť:';

  @override
  String get whatWeTrack => 'Čo sledujeme';

  @override
  String get anonymityAndPrivacy => 'Anonymita a súkromie';

  @override
  String get optInAndOptOutOptions => 'Možnosti prihlásenia a odhlásenia';

  @override
  String get ourCommitment => 'Náš záväzok';

  @override
  String get commitmentText =>
      'Zaväzujeme sa používať zhromaždené údaje len na to, aby sme z Omi urobili lepší produkt pre vás. Vaše súkromie a dôvera sú pre nás prvoradé.';

  @override
  String get thankYouText =>
      'Ďakujeme, že ste cenený používateľ Omi. Ak máte akékoľvek otázky alebo obavy, neváhajte nás kontaktovať na team@basedhardware.com.';

  @override
  String get wifiSyncSettings => 'Nastavenia synchronizácie WiFi';

  @override
  String get enterHotspotCredentials => 'Zadajte prihlasovacie údaje hotspotu telefónu';

  @override
  String get wifiSyncUsesHotspot =>
      'WiFi synchronizácia používa váš telefón ako hotspot. Nájdite názov a heslo v Nastavenia > Osobný hotspot.';

  @override
  String get hotspotNameSsid => 'Názov hotspotu (SSID)';

  @override
  String get exampleIphoneHotspot => 'napr. iPhone Hotspot';

  @override
  String get password => 'Heslo';

  @override
  String get enterHotspotPassword => 'Zadajte heslo hotspotu';

  @override
  String get saveCredentials => 'Uložiť prihlasovacie údaje';

  @override
  String get clearCredentials => 'Vymazať prihlasovacie údaje';

  @override
  String get pleaseEnterHotspotName => 'Prosím zadajte názov hotspotu';

  @override
  String get wifiCredentialsSaved => 'WiFi prihlasovacie údaje uložené';

  @override
  String get wifiCredentialsCleared => 'WiFi prihlasovacie údaje vymazané';

  @override
  String summaryGeneratedForDate(String date) {
    return 'Zhrnutie vytvorené pre $date';
  }

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'Nepodarilo sa vytvoriť zhrnutie. Uistite sa, že máte konverzácie pre daný deň.';

  @override
  String get summaryNotFound => 'Zhrnutie nenájdené';

  @override
  String get yourDaysJourney => 'Vaša denná cesta';

  @override
  String get highlights => 'Hlavné body';

  @override
  String get unresolvedQuestions => 'Nevyriešené otázky';

  @override
  String get decisions => 'Rozhodnutia';

  @override
  String get learnings => 'Ponaučenia';

  @override
  String get autoDeletesAfterThreeDays => 'Automaticky vymazané po 3 dňoch.';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'Graf znalostí úspešne vymazaný';

  @override
  String get exportStartedMayTakeFewSeconds => 'Export sa začal. Môže to trvať niekoľko sekúnd...';

  @override
  String get knowledgeGraphDeleteDescription =>
      'Toto vymaže všetky odvodené údaje grafu znalostí (uzly a spojenia). Vaše pôvodné spomienky zostanú v bezpečí. Graf sa obnoví časom alebo pri ďalšej požiadavke.';

  @override
  String get configureDailySummaryDigest => 'Nastavte si denný prehľad úloh';

  @override
  String accessesDataTypes(String dataTypes) {
    return 'Prístup k $dataTypes';
  }

  @override
  String triggeredByType(String triggerType) {
    return 'spustené $triggerType';
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
  String get noSpecificDataAccessConfigured => 'Nie je nakonfigurovaný žiadny konkrétny prístup k údajom.';

  @override
  String get basicPlanDescription => '1 200 prémiových minút + neobmedzené na zariadení';

  @override
  String get minutes => 'minút';

  @override
  String get omiHas => 'Omi má:';

  @override
  String get premiumMinutesUsed => 'Prémiové minúty vyčerpané.';

  @override
  String get setupOnDevice => 'Nastaviť na zariadení';

  @override
  String get forUnlimitedFreeTranscription => 'pre neobmedzenú bezplatnú transkripciu.';

  @override
  String premiumMinsLeft(int count) {
    return 'Zostáva $count prémiových minút.';
  }

  @override
  String get alwaysAvailable => 'vždy k dispozícii.';

  @override
  String get importHistory => 'História importu';

  @override
  String get noImportsYet => 'Zatiaľ žiadne importy';

  @override
  String get selectZipFileToImport => 'Vyberte súbor .zip na import!';

  @override
  String get otherDevicesComingSoon => 'Ďalšie zariadenia už čoskoro';

  @override
  String get deleteAllLimitlessConversations => 'Odstrániť všetky konverzácie Limitless?';

  @override
  String get deleteAllLimitlessWarning =>
      'Toto natrvalo odstráni všetky konverzácie importované z Limitless. Túto akciu nemožno vrátiť späť.';

  @override
  String deletedLimitlessConversations(int count) {
    return 'Odstránených $count konverzácií Limitless';
  }

  @override
  String get failedToDeleteConversations => 'Nepodarilo sa odstrániť konverzácie';

  @override
  String get deleteImportedData => 'Odstrániť importované údaje';

  @override
  String get statusPending => 'Čaká';

  @override
  String get statusProcessing => 'Spracováva sa';

  @override
  String get statusCompleted => 'Dokončené';

  @override
  String get statusFailed => 'Zlyhalo';

  @override
  String nConversations(int count) {
    return '$count konverzácií';
  }

  @override
  String get pleaseEnterName => 'Prosím zadajte meno';

  @override
  String get nameMustBeBetweenCharacters => 'Meno musí mať 2 až 40 znakov';

  @override
  String get deleteSampleQuestion => 'Odstrániť vzorku?';

  @override
  String deleteSampleConfirmation(String name) {
    return 'Ste si istí, že chcete odstrániť vzorku $name?';
  }

  @override
  String get confirmDeletion => 'Potvrdiť odstránenie';

  @override
  String deletePersonConfirmation(String name) {
    return 'Ste si istí, že chcete odstrániť $name? Tým sa odstránia aj všetky súvisiace hlasové vzorky.';
  }

  @override
  String get howItWorksTitle => 'Ako to funguje?';

  @override
  String get howPeopleWorks =>
      'Po vytvorení osoby môžete prejsť na prepis konverzácie a priradiť im zodpovedajúce segmenty, takto bude Omi schopné rozpoznať aj ich reč!';

  @override
  String get tapToDelete => 'Klepnite pre odstránenie';

  @override
  String get newTag => 'NOVÉ';

  @override
  String get needHelpChatWithUs => 'Potrebujete pomoc? Napíšte nám';

  @override
  String get localStorageEnabled => 'Lokálne úložisko povolené';

  @override
  String get localStorageDisabled => 'Lokálne úložisko zakázané';

  @override
  String failedToUpdateSettings(String error) {
    return 'Nepodarilo sa aktualizovať nastavenia: $error';
  }

  @override
  String get privacyNotice => 'Oznámenie o ochrane súkromia';

  @override
  String get recordingsMayCaptureOthers =>
      'Nahrávky môžu zachytiť hlasy ostatných. Pred povolením sa uistite, že máte súhlas všetkých účastníkov.';

  @override
  String get enable => 'Povoliť';

  @override
  String get storeAudioOnPhone => 'Store Audio on Phone';

  @override
  String get on => 'On';

  @override
  String get storeAudioDescription =>
      'Uchovávajte všetky zvukové nahrávky uložené lokálne v telefóne. Pri vypnutí sa ukladajú iba neúspešné nahrávania pre úsporu miesta.';

  @override
  String get enableLocalStorage => 'Povoliť lokálne úložisko';

  @override
  String get cloudStorageEnabled => 'Cloudové úložisko povolené';

  @override
  String get cloudStorageDisabled => 'Cloudové úložisko zakázané';

  @override
  String get enableCloudStorage => 'Povoliť cloudové úložisko';

  @override
  String get storeAudioOnCloud => 'Store Audio on Cloud';

  @override
  String get cloudStorageDialogMessage =>
      'Vaše nahrávky v reálnom čase budú uložené v súkromnom cloudovom úložisku počas rozprávania.';

  @override
  String get storeAudioCloudDescription =>
      'Ukladajte svoje nahrávky v reálnom čase do súkromného cloudového úložiska počas rozprávania. Zvuk sa zachytáva a bezpečne ukladá v reálnom čase.';

  @override
  String get downloadingFirmware => 'Sťahovanie firmvéru';

  @override
  String get installingFirmware => 'Inštalácia firmvéru';

  @override
  String get firmwareUpdateWarning =>
      'Nezatvárajte aplikáciu ani nevypínajte zariadenie. Mohlo by to poškodiť vaše zariadenie.';

  @override
  String get firmwareUpdated => 'Firmvér aktualizovaný';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'Pre dokončenie aktualizácie reštartujte $deviceName.';
  }

  @override
  String get yourDeviceIsUpToDate => 'Vaše zariadenie je aktuálne';

  @override
  String get currentVersion => 'Aktuálna verzia';

  @override
  String get latestVersion => 'Najnovšia verzia';

  @override
  String get whatsNew => 'Čo je nové';

  @override
  String get installUpdate => 'Nainštalovať aktualizáciu';

  @override
  String get updateNow => 'Aktualizovať teraz';

  @override
  String get updateGuide => 'Sprievodca aktualizáciou';

  @override
  String get checkingForUpdates => 'Kontrola aktualizácií';

  @override
  String get checkingFirmwareVersion => 'Kontrola verzie firmvéru...';

  @override
  String get firmwareUpdate => 'Aktualizácia firmvéru';

  @override
  String get payments => 'Platby';

  @override
  String get connectPaymentMethodInfo =>
      'Pripojte nižšie platobnú metódu a začnite prijímať platby za svoje aplikácie.';

  @override
  String get selectedPaymentMethod => 'Vybraná platobná metóda';

  @override
  String get availablePaymentMethods => 'Dostupné platobné metódy';

  @override
  String get activeStatus => 'Aktívny';

  @override
  String get connectedStatus => 'Pripojené';

  @override
  String get notConnectedStatus => 'Nepripojené';

  @override
  String get setActive => 'Nastaviť ako aktívne';

  @override
  String get getPaidThroughStripe => 'Získajte platby za predaj aplikácií cez Stripe';

  @override
  String get monthlyPayouts => 'Mesačné výplaty';

  @override
  String get monthlyPayoutsDescription => 'Dostávajte mesačné platby priamo na účet, keď dosiahnete zárobky 10 \$';

  @override
  String get secureAndReliable => 'Bezpečné a spoľahlivé';

  @override
  String get stripeSecureDescription => 'Stripe zabezpečuje bezpečné a včasné prevody príjmov z vašej aplikácie';

  @override
  String get selectYourCountry => 'Vyberte svoju krajinu';

  @override
  String get countrySelectionPermanent => 'Výber krajiny je trvalý a neskôr ho nemožno zmeniť.';

  @override
  String get byClickingConnectNow => 'Kliknutím na \"Pripojiť teraz\" súhlasíte s';

  @override
  String get stripeConnectedAccountAgreement => 'Zmluva o pripojenom účte Stripe';

  @override
  String get errorConnectingToStripe => 'Chyba pri pripájaní k Stripe! Skúste to prosím neskôr.';

  @override
  String get connectingYourStripeAccount => 'Pripájanie vášho účtu Stripe';

  @override
  String get stripeOnboardingInstructions =>
      'Dokončite prosím proces registrácie Stripe vo vašom prehliadači. Táto stránka sa automaticky aktualizuje po dokončení.';

  @override
  String get failedTryAgain => 'Zlyhalo? Skúsiť znova';

  @override
  String get illDoItLater => 'Urobím to neskôr';

  @override
  String get successfullyConnected => 'Úspešne pripojené!';

  @override
  String get stripeReadyForPayments =>
      'Váš účet Stripe je teraz pripravený prijímať platby. Môžete ihneď začať zarábať z predaja aplikácií.';

  @override
  String get updateStripeDetails => 'Aktualizovať údaje Stripe';

  @override
  String get errorUpdatingStripeDetails => 'Chyba pri aktualizácii údajov Stripe! Skúste to prosím neskôr.';

  @override
  String get updatePayPal => 'Aktualizovať PayPal';

  @override
  String get setUpPayPal => 'Nastaviť PayPal';

  @override
  String get updatePayPalAccountDetails => 'Aktualizujte údaje svojho účtu PayPal';

  @override
  String get connectPayPalToReceivePayments => 'Pripojte svoj účet PayPal a začnite prijímať platby za svoje aplikácie';

  @override
  String get paypalEmail => 'E-mail PayPal';

  @override
  String get paypalMeLink => 'Odkaz PayPal.me';

  @override
  String get stripeRecommendation =>
      'Ak je Stripe k dispozícii vo vašej krajine, dôrazne odporúčame jeho použitie pre rýchlejšie a jednoduchšie výplaty.';

  @override
  String get updatePayPalDetails => 'Aktualizovať údaje PayPal';

  @override
  String get savePayPalDetails => 'Uložiť údaje PayPal';

  @override
  String get pleaseEnterPayPalEmail => 'Zadajte svoj e-mail PayPal';

  @override
  String get pleaseEnterPayPalMeLink => 'Zadajte svoj odkaz PayPal.me';

  @override
  String get doNotIncludeHttpInLink => 'Nezahrňujte http alebo https alebo www do odkazu';

  @override
  String get pleaseEnterValidPayPalMeLink => 'Zadajte platný odkaz PayPal.me';

  @override
  String get pleaseEnterValidEmail => 'Zadajte platnú e-mailovú adresu';

  @override
  String get syncingYourRecordings => 'Synchronizácia vašich nahrávok';

  @override
  String get syncYourRecordings => 'Synchronizujte svoje nahrávky';

  @override
  String get syncNow => 'Synchronizovať teraz';

  @override
  String get error => 'Chyba';

  @override
  String get speechSamples => 'Hlasové vzorky';

  @override
  String additionalSampleIndex(String index) {
    return 'Ďalšia vzorka $index';
  }

  @override
  String durationSeconds(String seconds) {
    return 'Trvanie: $seconds sekúnd';
  }

  @override
  String get additionalSpeechSampleRemoved => 'Ďalšia hlasová vzorka odstránená';

  @override
  String get consentDataMessage =>
      'Pokračovaním budú všetky údaje, ktoré zdieľate s touto aplikáciou (vrátane vašich konverzácií, nahrávok a osobných informácií), bezpečne uložené na našich serveroch, aby sme vám mohli poskytovať poznatky založené na AI a umožniť všetky funkcie aplikácie.';

  @override
  String get tasksEmptyStateMessage =>
      'Úlohy z vašich konverzácií sa zobrazia tu.\nKlepnite na + pre manuálne vytvorenie.';

  @override
  String get clearChatAction => 'Vymazať chat';

  @override
  String get enableApps => 'Povoliť aplikácie';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => 'zobraziť viac ↓';

  @override
  String get showLess => 'zobraziť menej ↑';

  @override
  String get loadingYourRecording => 'Načítava sa nahrávka...';

  @override
  String get photoDiscardedMessage => 'Táto fotografia bola vyradená, pretože nebola významná.';

  @override
  String get analyzing => 'Analyzovanie...';

  @override
  String get searchCountries => 'Hľadať krajiny...';

  @override
  String get checkingAppleWatch => 'Kontrola Apple Watch...';

  @override
  String get installOmiOnAppleWatch => 'Nainštalujte Omi na\nApple Watch';

  @override
  String get installOmiOnAppleWatchDescription =>
      'Ak chcete používať Apple Watch s Omi, musíte najprv nainštalovať aplikáciu Omi na hodinky.';

  @override
  String get openOmiOnAppleWatch => 'Otvorte Omi na\nApple Watch';

  @override
  String get openOmiOnAppleWatchDescription =>
      'Aplikácia Omi je nainštalovaná na Apple Watch. Otvorte ju a klepnite na Štart.';

  @override
  String get openWatchApp => 'Otvoriť aplikáciu Watch';

  @override
  String get iveInstalledAndOpenedTheApp => 'Nainštaloval(a) som a otvoril(a) aplikáciu';

  @override
  String get unableToOpenWatchApp =>
      'Aplikáciu Apple Watch sa nepodarilo otvoriť. Manuálne otvorte aplikáciu Watch na Apple Watch a nainštalujte Omi zo sekcie \"Dostupné aplikácie\".';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch úspešne pripojené!';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch stále nie je dostupné. Uistite sa, že aplikácia Omi je na hodinkách otvorená.';

  @override
  String errorCheckingConnection(String error) {
    return 'Chyba pri kontrole pripojenia: $error';
  }

  @override
  String get muted => 'Stlmené';

  @override
  String get processNow => 'Spracovať teraz';

  @override
  String get finishedConversation => 'Konverzácia dokončená?';

  @override
  String get stopRecordingConfirmation => 'Ste si istí, že chcete zastaviť nahrávanie a zhrnúť konverzáciu teraz?';

  @override
  String get conversationEndsManually => 'Konverzácia sa ukončí iba ručne.';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'Konverzácia sa zhrnie po $minutes minút$suffix ticha.';
  }

  @override
  String get dontAskAgain => 'Nepýtaj sa znova';

  @override
  String get waitingForTranscriptOrPhotos => 'Čakanie na prepis alebo fotografie...';

  @override
  String get noSummaryYet => 'Zatiaľ žiadne zhrnutie';

  @override
  String hints(String text) {
    return 'Tipy: $text';
  }

  @override
  String get testConversationPrompt => 'Testovať výzvu konverzácie';

  @override
  String get prompt => 'Výzva';

  @override
  String get result => 'Výsledok:';

  @override
  String get compareTranscripts => 'Porovnať prepisy';

  @override
  String get notHelpful => 'Nebolo užitočné';

  @override
  String get exportTasksWithOneTap => 'Exportujte úlohy jedným ťuknutím!';

  @override
  String get inProgress => 'Prebieha';

  @override
  String get photos => 'Fotky';

  @override
  String get rawData => 'Nespracované dáta';

  @override
  String get content => 'Obsah';

  @override
  String get noContentToDisplay => 'Žiadny obsah na zobrazenie';

  @override
  String get noSummary => 'Žiadny súhrn';

  @override
  String get updateOmiFirmware => 'Aktualizovať firmvér omi';

  @override
  String get anErrorOccurredTryAgain => 'Vyskytla sa chyba. Skúste to znova.';

  @override
  String get welcomeBackSimple => 'Vitajte späť';

  @override
  String get addVocabularyDescription => 'Pridajte slová, ktoré má Omi rozpoznať počas prepisu.';

  @override
  String get enterWordsCommaSeparated => 'Zadajte slová (oddelené čiarkou)';

  @override
  String get whenToReceiveDailySummary => 'Kedy dostať denné zhrnutie';

  @override
  String get checkingNextSevenDays => 'Kontrola nasledujúcich 7 dní';

  @override
  String failedToDeleteError(String error) {
    return 'Odstránenie zlyhalo: $error';
  }

  @override
  String get developerApiKeys => 'API kľúče vývojára';

  @override
  String get noApiKeysCreateOne => 'Žiadne API kľúče. Vytvorte jeden na začiatok.';

  @override
  String get commandRequired => '⌘ je povinné';

  @override
  String get spaceKey => 'Medzerník';

  @override
  String loadMoreRemaining(String count) {
    return 'Načítať viac ($count zostáva)';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'Top $percentile% používateľ';
  }

  @override
  String get wrappedMinutes => 'minút';

  @override
  String get wrappedConversations => 'konverzácií';

  @override
  String get wrappedDaysActive => 'aktívnych dní';

  @override
  String get wrappedYouTalkedAbout => 'Hovorili ste o';

  @override
  String get wrappedActionItems => 'Úlohy';

  @override
  String get wrappedTasksCreated => 'vytvorených úloh';

  @override
  String get wrappedCompleted => 'dokončených';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% miera dokončenia';
  }

  @override
  String get wrappedYourTopDays => 'Vaše najlepšie dni';

  @override
  String get wrappedBestMoments => 'Najlepšie momenty';

  @override
  String get wrappedMyBuddies => 'Moji priatelia';

  @override
  String get wrappedCouldntStopTalkingAbout => 'Nemohol som prestať hovoriť o';

  @override
  String get wrappedShow => 'SERIÁL';

  @override
  String get wrappedMovie => 'FILM';

  @override
  String get wrappedBook => 'KNIHA';

  @override
  String get wrappedCelebrity => 'CELEBRITA';

  @override
  String get wrappedFood => 'JEDLO';

  @override
  String get wrappedMovieRecs => 'Odporúčania filmov pre priateľov';

  @override
  String get wrappedBiggest => 'Najväčšia';

  @override
  String get wrappedStruggle => 'Výzva';

  @override
  String get wrappedButYouPushedThrough => 'Ale zvládli ste to 💪';

  @override
  String get wrappedWin => 'Výhra';

  @override
  String get wrappedYouDidIt => 'Dokázali ste to! 🎉';

  @override
  String get wrappedTopPhrases => 'Top 5 fráz';

  @override
  String get wrappedMins => 'min';

  @override
  String get wrappedConvos => 'konverzácií';

  @override
  String get wrappedDays => 'dní';

  @override
  String get wrappedMyBuddiesLabel => 'MOJI PRIATELIA';

  @override
  String get wrappedObsessionsLabel => 'POSADNUTOSTI';

  @override
  String get wrappedStruggleLabel => 'VÝZVA';

  @override
  String get wrappedWinLabel => 'VÝHRA';

  @override
  String get wrappedTopPhrasesLabel => 'TOP FRÁZY';

  @override
  String get wrappedLetsHitRewind => 'Pretočme späť tvoj';

  @override
  String get wrappedGenerateMyWrapped => 'Vygenerovať môj Wrapped';

  @override
  String get wrappedProcessingDefault => 'Spracovanie...';

  @override
  String get wrappedCreatingYourStory => 'Vytvárame tvoj\npríbeh 2025...';

  @override
  String get wrappedSomethingWentWrong => 'Niečo sa\npokazilo';

  @override
  String get wrappedAnErrorOccurred => 'Vyskytla sa chyba';

  @override
  String get wrappedTryAgain => 'Skúsiť znova';

  @override
  String get wrappedNoDataAvailable => 'Žiadne údaje nie sú k dispozícii';

  @override
  String get wrappedOmiLifeRecap => 'Omi zhrnutie života';

  @override
  String get wrappedSwipeUpToBegin => 'Potiahni nahor pre začiatok';

  @override
  String get wrappedShareText => 'Môj 2025, zaznamenaný Omi ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare => 'Zdieľanie zlyhalo. Skúste to znova.';

  @override
  String get wrappedFailedToStartGeneration => 'Spustenie generovania zlyhalo. Skúste to znova.';

  @override
  String get wrappedStarting => 'Spúšťam...';

  @override
  String get wrappedShare => 'Zdieľať';

  @override
  String get wrappedShareYourWrapped => 'Zdieľaj svoj Wrapped';

  @override
  String get wrappedMy2025 => 'Môj 2025';

  @override
  String get wrappedRememberedByOmi => 'zaznamenaný Omi';

  @override
  String get wrappedMostFunDay => 'Najzábavnejší';

  @override
  String get wrappedMostProductiveDay => 'Najproduktívnejší';

  @override
  String get wrappedMostIntenseDay => 'Najintenzívnejší';

  @override
  String get wrappedFunniestMoment => 'Najvtipnejší';

  @override
  String get wrappedMostCringeMoment => 'Najtrápnejší';

  @override
  String get wrappedMinutesLabel => 'minút';

  @override
  String get wrappedConversationsLabel => 'konverzácií';

  @override
  String get wrappedDaysActiveLabel => 'aktívnych dní';

  @override
  String get wrappedTasksGenerated => 'vytvorených úloh';

  @override
  String get wrappedTasksCompleted => 'dokončených úloh';

  @override
  String get wrappedTopFivePhrases => 'Top 5 fráz';

  @override
  String get wrappedAGreatDay => 'Skvelý deň';

  @override
  String get wrappedGettingItDone => 'Zvládnuť to';

  @override
  String get wrappedAChallenge => 'Výzva';

  @override
  String get wrappedAHilariousMoment => 'Vtipný moment';

  @override
  String get wrappedThatAwkwardMoment => 'Ten trápny moment';

  @override
  String get wrappedYouHadFunnyMoments => 'Mal si vtipné chvíle tento rok!';

  @override
  String get wrappedWeveAllBeenThere => 'Všetci sme tam boli!';

  @override
  String get wrappedFriend => 'Priateľ';

  @override
  String get wrappedYourBuddy => 'Tvoj kamarát!';

  @override
  String get wrappedNotMentioned => 'Nespomenuté';

  @override
  String get wrappedTheHardPart => 'Ťažká časť';

  @override
  String get wrappedPersonalGrowth => 'Osobný rast';

  @override
  String get wrappedFunDay => 'Zábavný';

  @override
  String get wrappedProductiveDay => 'Produktívny';

  @override
  String get wrappedIntenseDay => 'Intenzívny';

  @override
  String get wrappedFunnyMomentTitle => 'Vtipný moment';

  @override
  String get wrappedCringeMomentTitle => 'Trápny moment';

  @override
  String get wrappedYouTalkedAboutBadge => 'Hovoril si o';

  @override
  String get wrappedCompletedLabel => 'Dokončené';

  @override
  String get wrappedMyBuddiesCard => 'Moji kamaráti';

  @override
  String get wrappedBuddiesLabel => 'KAMARÁTI';

  @override
  String get wrappedObsessionsLabelUpper => 'POSADNUTOSTI';

  @override
  String get wrappedStruggleLabelUpper => 'BOJ';

  @override
  String get wrappedWinLabelUpper => 'VÍŤAZSTVO';

  @override
  String get wrappedTopPhrasesLabelUpper => 'TOP FRÁZY';

  @override
  String get wrappedYourHeader => 'Tvoje';

  @override
  String get wrappedTopDaysHeader => 'Najlepšie dni';

  @override
  String get wrappedYourTopDaysBadge => 'Tvoje najlepšie dni';

  @override
  String get wrappedBestHeader => 'Najlepšie';

  @override
  String get wrappedMomentsHeader => 'Momenty';

  @override
  String get wrappedBestMomentsBadge => 'Najlepšie momenty';

  @override
  String get wrappedBiggestHeader => 'Najväčší';

  @override
  String get wrappedStruggleHeader => 'Boj';

  @override
  String get wrappedWinHeader => 'Víťazstvo';

  @override
  String get wrappedButYouPushedThroughEmoji => 'Ale zvládol si to 💪';

  @override
  String get wrappedYouDidItEmoji => 'Dokázal si to! 🎉';

  @override
  String get wrappedHours => 'hodín';

  @override
  String get wrappedActions => 'akcií';

  @override
  String get multipleSpeakersDetected => 'Zistených viacero rečníkov';

  @override
  String get multipleSpeakersDescription =>
      'Zdá sa, že v nahrávke je viacero rečníkov. Uistite sa, že ste na tichom mieste a skúste to znova.';

  @override
  String get invalidRecordingDetected => 'Zistená neplatná nahrávka';

  @override
  String get notEnoughSpeechDescription => 'Nebola zistená dostatočná reč. Prosím, hovorte viac a skúste to znova.';

  @override
  String get speechDurationDescription => 'Uistite sa, že hovoríte aspoň 5 sekúnd a nie viac ako 90.';

  @override
  String get connectionLostDescription =>
      'Spojenie bolo prerušené. Skontrolujte svoje internetové pripojenie a skúste to znova.';

  @override
  String get howToTakeGoodSample => 'Ako urobiť dobrú vzorku?';

  @override
  String get goodSampleInstructions =>
      '1. Uistite sa, že ste na tichom mieste.\n2. Hovorte jasne a prirodzene.\n3. Uistite sa, že vaše zariadenie je v prirodzenej polohe na krku.\n\nPo vytvorení ho môžete vždy vylepšiť alebo urobiť znova.';

  @override
  String get noDeviceConnectedUseMic => 'Žiadne pripojené zariadenie. Bude použitý mikrofón telefónu.';

  @override
  String get doItAgain => 'Urobiť znova';

  @override
  String get listenToSpeechProfile => 'Počúvať môj hlasový profil ➡️';

  @override
  String get recognizingOthers => 'Rozpoznávanie ostatných 👀';

  @override
  String get keepGoingGreat => 'Pokračuj, darí sa ti skvele';

  @override
  String get somethingWentWrongTryAgain => 'Niečo sa pokazilo! Skúste to prosím neskôr znova.';

  @override
  String get uploadingVoiceProfile => 'Nahrávanie vášho hlasového profilu....';

  @override
  String get memorizingYourVoice => 'Ukladanie vášho hlasu...';

  @override
  String get personalizingExperience => 'Prispôsobovanie vašej skúsenosti...';

  @override
  String get keepSpeakingUntil100 => 'Hovorte ďalej, kým nedosiahnete 100%.';

  @override
  String get greatJobAlmostThere => 'Skvelá práca, už ste skoro tam';

  @override
  String get soCloseJustLittleMore => 'Tak blízko, len ešte trochu';

  @override
  String get notificationFrequency => 'Frekvencia upozornení';

  @override
  String get controlNotificationFrequency => 'Ovládajte, ako často vám Omi posiela proaktívne oznámenia.';

  @override
  String get yourScore => 'Vaše skóre';

  @override
  String get dailyScoreBreakdown => 'Rozpis denného skóre';

  @override
  String get todaysScore => 'Dnešné skóre';

  @override
  String get tasksCompleted => 'Dokončené úlohy';

  @override
  String get completionRate => 'Miera dokončenia';

  @override
  String get howItWorks => 'Ako to funguje';

  @override
  String get dailyScoreExplanation =>
      'Vaše denné skóre je založené na plnení úloh. Dokončite svoje úlohy pre zlepšenie skóre!';

  @override
  String get notificationFrequencyDescription =>
      'Ovládajte, ako často vám Omi posiela proaktívne upozornenia a pripomienky.';

  @override
  String get sliderOff => 'Vyp.';

  @override
  String get sliderMax => 'Max.';

  @override
  String summaryGeneratedFor(String date) {
    return 'Súhrn vygenerovaný pre $date';
  }

  @override
  String get failedToGenerateSummary =>
      'Nepodarilo sa vygenerovať súhrn. Uistite sa, že máte konverzácie pre tento deň.';

  @override
  String get recap => 'Zhrnutie';

  @override
  String deleteQuoted(String name) {
    return 'Odstrániť \"$name\"';
  }

  @override
  String moveConversationsTo(int count) {
    return 'Presunúť $count konverzácií do:';
  }

  @override
  String get noFolder => 'Žiadny priečinok';

  @override
  String get removeFromAllFolders => 'Odstrániť zo všetkých priečinkov';

  @override
  String get buildAndShareYourCustomApp => 'Vytvorte a zdieľajte svoju vlastnú aplikáciu';

  @override
  String get searchAppsPlaceholder => 'Hľadať v 1500+ aplikáciách';

  @override
  String get filters => 'Filtre';

  @override
  String get frequencyOff => 'Vypnuté';

  @override
  String get frequencyMinimal => 'Minimálna';

  @override
  String get frequencyLow => 'Nízka';

  @override
  String get frequencyBalanced => 'Vyvážená';

  @override
  String get frequencyHigh => 'Vysoká';

  @override
  String get frequencyMaximum => 'Maximálna';

  @override
  String get frequencyDescOff => 'Žiadne proaktívne upozornenia';

  @override
  String get frequencyDescMinimal => 'Len kritické pripomienky';

  @override
  String get frequencyDescLow => 'Len dôležité aktualizácie';

  @override
  String get frequencyDescBalanced => 'Pravidelné užitočné pripomienky';

  @override
  String get frequencyDescHigh => 'Časté kontroly';

  @override
  String get frequencyDescMaximum => 'Zostaňte neustále zapojený';

  @override
  String get clearChatQuestion => 'Vymazať chat?';

  @override
  String get syncingMessages => 'Synchronizácia správ so serverom...';

  @override
  String get chatAppsTitle => 'Chatové aplikácie';

  @override
  String get selectApp => 'Vybrať aplikáciu';

  @override
  String get noChatAppsEnabled =>
      'Žiadne chatové aplikácie nie sú povolené.\nKlepnite na \"Povoliť aplikácie\" pre pridanie.';

  @override
  String get disable => 'Zakázať';

  @override
  String get photoLibrary => 'Knižnica fotografií';

  @override
  String get chooseFile => 'Vybrať súbor';

  @override
  String get configureAiPersona => 'Configure your AI persona';

  @override
  String get connectAiAssistantsToYourData => 'Connect AI assistants to your data';

  @override
  String get oAuth => 'OAuth';

  @override
  String get trackYourGoalsOnHomepage => 'Track your personal goals on homepage';

  @override
  String get deleteRecording => 'Delete Recording';

  @override
  String get thisCannotBeUndone => 'This cannot be undone.';

  @override
  String get sdCard => 'SD Card';

  @override
  String get fromSd => 'From SD';

  @override
  String get limitless => 'Limitless';

  @override
  String get fastTransfer => 'Rýchly prenos';

  @override
  String get syncingStatus => 'Syncing';

  @override
  String get failedStatus => 'Failed';

  @override
  String etaLabel(String time) {
    return 'ETA: $time';
  }

  @override
  String get transferMethod => 'Metóda prenosu';

  @override
  String get fast => 'Fast';

  @override
  String get ble => 'BLE';

  @override
  String get phone => 'Phone';

  @override
  String get cancelSync => 'Cancel Sync';

  @override
  String get cancelSyncMessage => 'Data already downloaded will be saved. You can resume later.';

  @override
  String get syncCancelled => 'Sync cancelled';

  @override
  String get deleteProcessedFiles => 'Delete Processed Files';

  @override
  String get processedFilesDeleted => 'Processed files deleted';

  @override
  String get wifiEnableFailed => 'Failed to enable WiFi on device. Please try again.';

  @override
  String get deviceNoFastTransfer => 'Your device does not support Fast Transfer. Use Bluetooth instead.';

  @override
  String get enableHotspotMessage => 'Please enable your phone\'s hotspot and try again.';

  @override
  String get transferStartFailed => 'Failed to start transfer. Please try again.';

  @override
  String get deviceNotResponding => 'Device did not respond. Please try again.';

  @override
  String get invalidWifiCredentials => 'Invalid WiFi credentials. Check your hotspot settings.';

  @override
  String get wifiConnectionFailed => 'WiFi connection failed. Please try again.';

  @override
  String get sdCardProcessing => 'SD Card Processing';

  @override
  String sdCardProcessingMessage(int count) {
    return 'Processing $count recording(s). Files will be removed from SD card after.';
  }

  @override
  String get process => 'Process';

  @override
  String get wifiSyncFailed => 'WiFi Sync Failed';

  @override
  String get processingFailed => 'Processing Failed';

  @override
  String get downloadingFromSdCard => 'Downloading from SD Card';

  @override
  String processingProgress(int current, int total) {
    return 'Processing $current/$total';
  }

  @override
  String conversationsCreated(int count) {
    return '$count conversations created';
  }

  @override
  String get internetRequired => 'Internet required';

  @override
  String get processAudio => 'Process Audio';

  @override
  String get start => 'Start';

  @override
  String get noRecordings => 'No Recordings';

  @override
  String get audioFromOmiWillAppearHere => 'Audio from your Omi device will appear here';

  @override
  String get deleteProcessed => 'Delete Processed';

  @override
  String get tryDifferentFilter => 'Try a different filter';

  @override
  String get recordings => 'Recordings';

  @override
  String get enableRemindersAccess => 'Povoľte prístup k Pripomienkam v Nastaveniach pre použitie Apple Pripomienok';

  @override
  String todayAtTime(String time) {
    return 'Dnes o $time';
  }

  @override
  String yesterdayAtTime(String time) {
    return 'Včera o $time';
  }

  @override
  String get lessThanAMinute => 'Menej ako minúta';

  @override
  String estimatedMinutes(int count) {
    return '~$count min.';
  }

  @override
  String estimatedHours(int count) {
    return '~$count hod.';
  }

  @override
  String estimatedTimeRemaining(String time) {
    return 'Odhad: zostáva $time';
  }

  @override
  String get summarizingConversation => 'Zhrnutie konverzácie...\nMôže to trvať niekoľko sekúnd';

  @override
  String get resummarizingConversation => 'Opätovné zhrnutie konverzácie...\nMôže to trvať niekoľko sekúnd';

  @override
  String get nothingInterestingRetry => 'Nič zaujímavé nenájdené,\nchcete to skúsiť znova?';

  @override
  String get noSummaryForConversation => 'Pre túto konverzáciu\nnie je k dispozícii zhrnutie.';

  @override
  String get unknownLocation => 'Neznáma poloha';

  @override
  String get couldNotLoadMap => 'Mapu sa nepodarilo načítať';

  @override
  String get triggerConversationIntegration => 'Spustiť integráciu vytvorenia konverzácie';

  @override
  String get webhookUrlNotSet => 'URL webhooku nie je nastavená';

  @override
  String get setWebhookUrlInSettings => 'Nastavte URL webhooku v nastaveniach vývojára pre použitie tejto funkcie.';

  @override
  String get sendWebUrl => 'Odoslať webovú URL';

  @override
  String get sendTranscript => 'Odoslať prepis';

  @override
  String get sendSummary => 'Odoslať zhrnutie';

  @override
  String get debugModeDetected => 'Zistený režim ladenia';

  @override
  String get performanceReduced => 'Výkon môže byť znížený';

  @override
  String autoClosingInSeconds(int seconds) {
    return 'Automatické zatvorenie o $seconds sekúnd';
  }

  @override
  String get modelRequired => 'Vyžaduje sa model';

  @override
  String get downloadWhisperModel => 'Stiahnite model whisper na použitie prepisu na zariadení';

  @override
  String get deviceNotCompatible => 'Vaše zariadenie nie je kompatibilné s prepisom na zariadení';

  @override
  String get deviceRequirements => 'Your device does not meet the requirements for On-Device transcription.';

  @override
  String get willLikelyCrash => 'Povolenie pravdepodobne spôsobí pád alebo zamrznutie aplikácie.';

  @override
  String get transcriptionSlowerLessAccurate => 'Prepis bude výrazne pomalší a menej presný.';

  @override
  String get proceedAnyway => 'Napriek tomu pokračovať';

  @override
  String get olderDeviceDetected => 'Zistené staršie zariadenie';

  @override
  String get onDeviceSlower => 'On-device transcription may be slower on this device.';

  @override
  String get batteryUsageHigher => 'Spotreba batérie bude vyššia ako pri cloudovom prepise.';

  @override
  String get considerOmiCloud => 'Zvážte použitie Omi Cloud pre lepší výkon.';

  @override
  String get highResourceUsage => 'Vysoká spotreba zdrojov';

  @override
  String get onDeviceIntensive => 'On-Device transcription is computationally intensive.';

  @override
  String get batteryDrainIncrease => 'Battery drain will increase significantly.';

  @override
  String get deviceMayWarmUp => 'Zariadenie sa môže pri dlhšom používaní zahriať.';

  @override
  String get speedAccuracyLower => 'Rýchlosť a presnosť môžu byť nižšie ako pri cloudových modeloch.';

  @override
  String get cloudProvider => 'Cloudový poskytovateľ';

  @override
  String get premiumMinutesInfo => '1,200 premium minutes/month. On-Device tab offers unlimited free transcription.';

  @override
  String get viewUsage => 'Zobraziť využitie';

  @override
  String get localProcessingInfo => 'Audio is processed locally. Works offline, more private, but uses more battery.';

  @override
  String get model => 'Model';

  @override
  String get performanceWarning => 'Varovanie o výkone';

  @override
  String get largeModelWarning =>
      'This model is large and may crash the app or run very slowly on mobile devices.\n\n\"small\" or \"base\" is recommended.';

  @override
  String get usingNativeIosSpeech => 'Používanie natívneho rozpoznávania reči iOS';

  @override
  String get noModelDownloadRequired => 'Your device\'s native speech engine will be used. No model download required.';

  @override
  String get modelReady => 'Model Ready';

  @override
  String get redownload => 'Re-download';

  @override
  String get doNotCloseApp => 'Prosím nezatvárajte aplikáciu.';

  @override
  String get downloading => 'Sťahovanie...';

  @override
  String get downloadModel => 'Stiahnuť model';

  @override
  String estimatedSize(String size) {
    return 'Estimated Size: ~$size MB';
  }

  @override
  String availableSpace(String space) {
    return 'Available Space: $space';
  }

  @override
  String get notEnoughSpace => 'Varovanie: Nedostatok miesta!';

  @override
  String get download => 'Stiahnuť';

  @override
  String downloadError(String error) {
    return 'Download error: $error';
  }

  @override
  String get cancelled => 'Zrušené';

  @override
  String get deviceNotCompatibleTitle => 'Zariadenie nie je kompatibilné';

  @override
  String get deviceNotMeetRequirements => 'Vaše zariadenie nespĺňa požiadavky pre prepis na zariadení.';

  @override
  String get transcriptionSlowerOnDevice => 'Prepis na zariadení môže byť na tomto zariadení pomalší.';

  @override
  String get computationallyIntensive => 'Prepis na zariadení je výpočtovo náročný.';

  @override
  String get batteryDrainSignificantly => 'Vybíjanie batérie sa výrazne zvýši.';

  @override
  String get premiumMinutesMonth =>
      '1 200 prémiových minút/mesiac. Karta Na zariadení ponúka neobmedzený bezplatný prepis. ';

  @override
  String get audioProcessedLocally =>
      'Zvuk sa spracováva lokálne. Funguje offline, je súkromnejší, ale spotrebováva viac batérie.';

  @override
  String get languageLabel => 'Jazyk';

  @override
  String get modelLabel => 'Model';

  @override
  String get modelTooLargeWarning =>
      'Tento model je veľký a môže spôsobiť pád aplikácie alebo veľmi pomalý beh na mobilných zariadeniach.\n\nOdporúča sa small alebo base.';

  @override
  String get nativeEngineNoDownload =>
      'Bude použitý natívny hlasový engine vášho zariadenia. Nie je potrebné sťahovať model.';

  @override
  String modelReadyWithName(String model) {
    return 'Model pripravený ($model)';
  }

  @override
  String get reDownload => 'Znova stiahnuť';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return 'Sťahovanie $model: $received / $total MB';
  }

  @override
  String preparingModel(String model) {
    return 'Príprava $model...';
  }

  @override
  String downloadErrorWithMessage(String error) {
    return 'Chyba sťahovania: $error';
  }

  @override
  String estimatedSizeWithValue(String size) {
    return 'Odhadovaná veľkosť: ~$size MB';
  }

  @override
  String availableSpaceWithValue(String space) {
    return 'Dostupné miesto: $space';
  }

  @override
  String get omiTranscriptionOptimized =>
      'Vstavaný živý prepis Omi je optimalizovaný pre konverzácie v reálnom čase s automatickou detekciou rečníkov a diarizáciou.';

  @override
  String get reset => 'Resetovať';

  @override
  String get useTemplateFrom => 'Použiť šablónu od';

  @override
  String get selectProviderTemplate => 'Vyberte šablónu poskytovateľa...';

  @override
  String get quicklyPopulateResponse => 'Rýchlo vyplniť známym formátom odpovede poskytovateľa';

  @override
  String get quicklyPopulateRequest => 'Rýchlo vyplniť známym formátom požiadavky poskytovateľa';

  @override
  String get invalidJsonError => 'Neplatný JSON';

  @override
  String downloadModelWithName(String model) {
    return 'Stiahnuť model ($model)';
  }

  @override
  String modelNameWithFile(String model) {
    return 'Model: $model';
  }

  @override
  String get device => 'Device';

  @override
  String get chatAssistantsTitle => 'Chat asistenti';

  @override
  String get permissionReadConversations => 'Čítať konverzácie';

  @override
  String get permissionReadMemories => 'Čítať spomienky';

  @override
  String get permissionReadTasks => 'Čítať úlohy';

  @override
  String get permissionCreateConversations => 'Vytvárať konverzácie';

  @override
  String get permissionCreateMemories => 'Vytvárať spomienky';

  @override
  String get permissionTypeAccess => 'Prístup';

  @override
  String get permissionTypeCreate => 'Vytvoriť';

  @override
  String get permissionTypeTrigger => 'Spúšťač';

  @override
  String get permissionDescReadConversations => 'Táto aplikácia môže pristupovať k vašim konverzáciám.';

  @override
  String get permissionDescReadMemories => 'Táto aplikácia môže pristupovať k vašim spomienkam.';

  @override
  String get permissionDescReadTasks => 'Táto aplikácia môže pristupovať k vašim úlohám.';

  @override
  String get permissionDescCreateConversations => 'Táto aplikácia môže vytvárať nové konverzácie.';

  @override
  String get permissionDescCreateMemories => 'Táto aplikácia môže vytvárať nové spomienky.';

  @override
  String get realtimeListening => 'Počúvanie v reálnom čase';

  @override
  String get setupCompleted => 'Dokončené';

  @override
  String get pleaseSelectRating => 'Prosím vyberte hodnotenie';

  @override
  String get writeReviewOptional => 'Napíšte recenziu (voliteľné)';

  @override
  String get setupQuestionsIntro => 'Help us improve Omi by answering a few questions.  🫶 💜';

  @override
  String get setupQuestionProfession => '1. What do you do?';

  @override
  String get setupQuestionUsage => '2. Where do you plan to use your Omi?';

  @override
  String get setupQuestionAge => '3. What\'s your age range?';

  @override
  String get setupAnswerAllQuestions => 'You haven\'t answered all the questions yet! 🥺';

  @override
  String get setupSkipHelp => 'Skip, I don\'t want to help :C';

  @override
  String get professionEntrepreneur => 'Entrepreneur';

  @override
  String get professionSoftwareEngineer => 'Software Engineer';

  @override
  String get professionProductManager => 'Product Manager';

  @override
  String get professionExecutive => 'Executive';

  @override
  String get professionSales => 'Sales';

  @override
  String get professionStudent => 'Student';

  @override
  String get usageAtWork => 'At work';

  @override
  String get usageIrlEvents => 'IRL Events';

  @override
  String get usageOnline => 'Online';

  @override
  String get usageSocialSettings => 'In Social Settings';

  @override
  String get usageEverywhere => 'Everywhere';

  @override
  String get customBackendUrlTitle => 'Vlastná URL servera';

  @override
  String get backendUrlLabel => 'URL servera';

  @override
  String get saveUrlButton => 'Uložiť URL';

  @override
  String get enterBackendUrlError => 'Zadajte URL servera';

  @override
  String get urlMustEndWithSlashError => 'URL musí končiť na \"/\"';

  @override
  String get invalidUrlError => 'Zadajte platnú URL';

  @override
  String get backendUrlSavedSuccess => 'URL servera bola úspešne uložená!';

  @override
  String get signInTitle => 'Prihlásiť sa';

  @override
  String get signInButton => 'Prihlásiť sa';

  @override
  String get enterEmailError => 'Zadajte svoj e-mail';

  @override
  String get invalidEmailError => 'Zadajte platný e-mail';

  @override
  String get enterPasswordError => 'Zadajte svoje heslo';

  @override
  String get passwordMinLengthError => 'Heslo musí mať aspoň 8 znakov';

  @override
  String get signInSuccess => 'Prihlásenie úspešné!';

  @override
  String get alreadyHaveAccountLogin => 'Máte už účet? Prihláste sa';

  @override
  String get emailLabel => 'E-mail';

  @override
  String get passwordLabel => 'Heslo';

  @override
  String get createAccountTitle => 'Vytvoriť účet';

  @override
  String get nameLabel => 'Meno';

  @override
  String get repeatPasswordLabel => 'Zopakujte heslo';

  @override
  String get signUpButton => 'Zaregistrovať sa';

  @override
  String get enterNameError => 'Zadajte svoje meno';

  @override
  String get passwordsDoNotMatch => 'Heslá sa nezhodujú';

  @override
  String get signUpSuccess => 'Registrácia úspešná!';

  @override
  String get loadingKnowledgeGraph => 'Načítava sa znalostný graf...';

  @override
  String get noKnowledgeGraphYet => 'Zatiaľ žiadny znalostný graf';

  @override
  String get buildingKnowledgeGraphFromMemories => 'Vytvára sa znalostný graf zo spomienok...';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'Váš znalostný graf sa vytvorí automaticky, keď vytvoríte nové spomienky.';

  @override
  String get buildGraphButton => 'Vytvoriť graf';

  @override
  String get checkOutMyMemoryGraph => 'Pozrite sa na môj graf pamäte!';

  @override
  String get getButton => 'Získať';

  @override
  String openingApp(String appName) {
    return 'Otvára sa $appName...';
  }

  @override
  String get writeSomething => 'Napíšte niečo';

  @override
  String get submitReply => 'Odoslať odpoveď';

  @override
  String get editYourReply => 'Upraviť odpoveď';

  @override
  String get replyToReview => 'Odpovedať na recenziu';

  @override
  String get rateAndReviewThisApp => 'Ohodnoťte a recenzujte túto aplikáciu';

  @override
  String get noChangesInReview => 'Žiadne zmeny v recenzii na aktualizáciu.';

  @override
  String get cantRateWithoutInternet => 'Nemožno hodnotiť aplikáciu bez pripojenia na internet.';

  @override
  String get appAnalytics => 'Analytika aplikácie';

  @override
  String get learnMoreLink => 'zistiť viac';

  @override
  String get moneyEarned => 'Zarobené peniaze';

  @override
  String get writeYourReply => 'Write your reply...';

  @override
  String get replySentSuccessfully => 'Reply sent successfully';

  @override
  String failedToSendReply(String error) {
    return 'Failed to send reply: $error';
  }

  @override
  String get send => 'Send';

  @override
  String starFilter(int count) {
    return '$count Star';
  }

  @override
  String get noReviewsFound => 'No Reviews Found';

  @override
  String get editReply => 'Edit Reply';

  @override
  String get reply => 'Reply';

  @override
  String starFilterLabel(int count) {
    return '$count hviezda';
  }

  @override
  String get sharePublicLink => 'Share Public Link';

  @override
  String get makePersonaPublic => 'Make Persona Public';

  @override
  String get connectedKnowledgeData => 'Connected Knowledge Data';

  @override
  String get enterName => 'Enter name';

  @override
  String get disconnectTwitter => 'Disconnect Twitter';

  @override
  String get disconnectTwitterConfirmation =>
      'Are you sure you want to disconnect your Twitter account? Your persona will no longer have access to your Twitter data.';

  @override
  String get getOmiDeviceDescription => 'Create a more accurate clone with your personal conversations';

  @override
  String get getOmi => 'Get Omi';

  @override
  String get iHaveOmiDevice => 'I have Omi device';

  @override
  String get goal => 'CIEĽ';

  @override
  String get tapToTrackThisGoal => 'Ťuknite pre sledovanie tohto cieľa';

  @override
  String get tapToSetAGoal => 'Ťuknite pre nastavenie cieľa';

  @override
  String get processedConversations => 'Spracované konverzácie';

  @override
  String get updatedConversations => 'Aktualizované konverzácie';

  @override
  String get newConversations => 'Nové konverzácie';

  @override
  String get summaryTemplate => 'Šablóna zhrnutia';

  @override
  String get suggestedTemplates => 'Navrhované šablóny';

  @override
  String get otherTemplates => 'Ostatné šablóny';

  @override
  String get availableTemplates => 'Dostupné šablóny';

  @override
  String get getCreative => 'Buďte kreatívni';

  @override
  String get defaultLabel => 'Predvolené';

  @override
  String get lastUsedLabel => 'Naposledy použité';

  @override
  String get setDefaultApp => 'Nastaviť predvolenú aplikáciu';

  @override
  String setDefaultAppContent(String appName) {
    return 'Nastaviť $appName ako predvolenú aplikáciu na zhrnutia?\\n\\nTáto aplikácia sa automaticky použije pre všetky budúce zhrnutia konverzácií.';
  }

  @override
  String get setDefaultButton => 'Nastaviť predvolenú';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName nastavená ako predvolená aplikácia na zhrnutia';
  }

  @override
  String get createCustomTemplate => 'Vytvoriť vlastnú šablónu';

  @override
  String get allTemplates => 'Všetky šablóny';

  @override
  String failedToInstallApp(String appName) {
    return 'Nepodarilo sa nainštalovať $appName. Skúste to znova.';
  }

  @override
  String errorInstallingApp(String appName, String error) {
    return 'Chyba pri inštalácii $appName: $error';
  }

  @override
  String tagSpeaker(int speakerId) {
    return 'Tag Speaker $speakerId';
  }

  @override
  String get personNameAlreadyExists => 'A person with this name already exists.';

  @override
  String get selectYouFromList => 'To tag yourself, please select \"You\" from the list.';

  @override
  String get enterPersonsName => 'Enter Person\'s Name';

  @override
  String get addPerson => 'Add Person';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'Tag other segments from this speaker ($selected/$total)';
  }

  @override
  String get tagOtherSegments => 'Tag other segments';

  @override
  String get managePeople => 'Manage People';

  @override
  String get shareViaSms => 'Zdieľať cez SMS';

  @override
  String get selectContactsToShareSummary => 'Vyberte kontakty na zdieľanie súhrnu konverzácie';

  @override
  String get searchContactsHint => 'Hľadať kontakty...';

  @override
  String contactsSelectedCount(int count) {
    return '$count vybraných';
  }

  @override
  String get clearAllSelection => 'Vymazať všetko';

  @override
  String get selectContactsToShare => 'Vyberte kontakty na zdieľanie';

  @override
  String shareWithContactCount(int count) {
    return 'Zdieľať s $count kontaktom';
  }

  @override
  String shareWithContactsCount(int count) {
    return 'Zdieľať s $count kontaktmi';
  }

  @override
  String get contactsPermissionRequired => 'Vyžaduje sa povolenie kontaktov';

  @override
  String get contactsPermissionRequiredForSms => 'Na zdieľanie cez SMS sa vyžaduje povolenie kontaktov';

  @override
  String get grantContactsPermissionForSms => 'Pre zdieľanie cez SMS prosím udeľte povolenie kontaktov';

  @override
  String get noContactsWithPhoneNumbers => 'Neboli nájdené kontakty s telefónnymi číslami';

  @override
  String get noContactsMatchSearch => 'Žiadne kontakty nezodpovedajú vášmu vyhľadávaniu';

  @override
  String get failedToLoadContacts => 'Nepodarilo sa načítať kontakty';

  @override
  String get failedToPrepareConversationForSharing =>
      'Nepodarilo sa pripraviť konverzáciu na zdieľanie. Skúste to znova.';

  @override
  String get couldNotOpenSmsApp => 'Nepodarilo sa otvoriť aplikáciu SMS. Skúste to znova.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'Tu je to, o čom sme práve hovorili: $link';
  }

  @override
  String get wifiSync => 'Synchronizácia WiFi';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item skopírované do schránky';
  }

  @override
  String get wifiConnectionFailedTitle => 'Connection Failed';

  @override
  String connectingToDeviceName(String deviceName) {
    return 'Connecting to $deviceName';
  }

  @override
  String enableDeviceWifi(String deviceName) {
    return 'Enable $deviceName\'s WiFi';
  }

  @override
  String connectToDeviceName(String deviceName) {
    return 'Connect to $deviceName';
  }

  @override
  String get recordingDetails => 'Recording Details';

  @override
  String get storageLocationSdCard => 'SD Card';

  @override
  String get storageLocationLimitlessPendant => 'Limitless Pendant';

  @override
  String get storageLocationPhone => 'Phone';

  @override
  String get storageLocationPhoneMemory => 'Phone (Memory)';

  @override
  String storedOnDevice(String deviceName) {
    return 'Stored on $deviceName';
  }

  @override
  String get transferring => 'Transferring...';

  @override
  String get transferRequired => 'Transfer Required';

  @override
  String get downloadingAudioFromSdCard => 'Downloading audio from your device\'s SD card';

  @override
  String get transferRequiredDescription =>
      'This recording is stored on your device\'s SD card. Transfer it to your phone to play or share.';

  @override
  String get cancelTransfer => 'Cancel Transfer';

  @override
  String get transferToPhone => 'Transfer to Phone';

  @override
  String get privateAndSecureOnDevice => 'Private & secure on your device';

  @override
  String get recordingInfo => 'Recording Info';

  @override
  String get transferInProgress => 'Transfer in progress...';

  @override
  String get shareRecording => 'Share Recording';

  @override
  String get deleteRecordingConfirmation =>
      'Are you sure you want to permanently delete this recording? This can\'t be undone.';

  @override
  String get recordingIdLabel => 'Recording ID';

  @override
  String get dateTimeLabel => 'Date & Time';

  @override
  String get durationLabel => 'Duration';

  @override
  String get audioFormatLabel => 'Audio Format';

  @override
  String get storageLocationLabel => 'Storage Location';

  @override
  String get estimatedSizeLabel => 'Estimated Size';

  @override
  String get deviceModelLabel => 'Device Model';

  @override
  String get deviceIdLabel => 'Device ID';

  @override
  String get statusLabel => 'Status';

  @override
  String get statusProcessed => 'Processed';

  @override
  String get statusUnprocessed => 'Unprocessed';

  @override
  String get switchedToFastTransfer => 'Switched to Fast Transfer';

  @override
  String get transferCompleteMessage => 'Transfer complete! You can now play this recording.';

  @override
  String transferFailedMessage(String error) {
    return 'Transfer failed: $error';
  }

  @override
  String get transferCancelled => 'Transfer cancelled';

  @override
  String get fastTransferEnabled => 'Rýchly prenos povolený';

  @override
  String get bluetoothSyncEnabled => 'Synchronizácia Bluetooth povolená';

  @override
  String get enableFastTransfer => 'Povoliť rýchly prenos';

  @override
  String get fastTransferDescription =>
      'Rýchly prenos používa WiFi pre ~5x rýchlejšie prenosy. Váš telefón sa dočasne pripojí k WiFi sieti zariadenia Omi počas prenosu.';

  @override
  String get internetAccessPausedDuringTransfer => 'Prístup na internet je počas prenosu pozastavený';

  @override
  String get chooseTransferMethodDescription => 'Zvoľte, ako sa nahrávky prenášajú zo zariadenia Omi do telefónu.';

  @override
  String get wifiSpeed => '~150 KB/s cez WiFi';

  @override
  String get fiveTimesFaster => '5X RÝCHLEJŠÍ';

  @override
  String get fastTransferMethodDescription =>
      'Vytvorí priame WiFi pripojenie k zariadeniu Omi. Telefón sa dočasne odpojí od bežnej WiFi počas prenosu.';

  @override
  String get bluetooth => 'Bluetooth';

  @override
  String get bleSpeed => '~30 KB/s cez BLE';

  @override
  String get bluetoothMethodDescription =>
      'Používa štandardné Bluetooth Low Energy pripojenie. Pomalšie, ale neovplyvňuje WiFi pripojenie.';

  @override
  String get selected => 'Vybrané';

  @override
  String get selectOption => 'Vybrať';

  @override
  String get lowBatteryAlertTitle => 'Upozornenie na nízku batériu';

  @override
  String get lowBatteryAlertBody => 'Batéria vášho zariadenia je vybitá. Je čas ju nabiť! 🔋';

  @override
  String get deviceDisconnectedNotificationTitle => 'Vaše zariadenie Omi bolo odpojené';

  @override
  String get deviceDisconnectedNotificationBody =>
      'Prosím, znova sa pripojte, aby ste mohli pokračovať v používaní Omi.';

  @override
  String get firmwareUpdateAvailable => 'K dispozícii je aktualizácia firmvéru';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'Pre vaše zariadenie Omi je k dispozícii nová aktualizácia firmvéru ($version). Chcete aktualizovať teraz?';
  }

  @override
  String get later => 'Neskôr';

  @override
  String get appDeletedSuccessfully => 'Aplikácia bola úspešne odstránená';

  @override
  String get appDeleteFailed => 'Nepodarilo sa odstrániť aplikáciu. Skúste to neskôr.';

  @override
  String get appVisibilityChangedSuccessfully =>
      'Viditeľnosť aplikácie bola úspešne zmenená. Môže to trvať niekoľko minút.';

  @override
  String get errorActivatingAppIntegration =>
      'Chyba pri aktivácii aplikácie. Ak ide o integračnú aplikáciu, uistite sa, že nastavenie je dokončené.';

  @override
  String get errorUpdatingAppStatus => 'Pri aktualizácii stavu aplikácie došlo k chybe.';

  @override
  String get calculatingETA => 'Calculating...';

  @override
  String aboutMinutesRemaining(int minutes) {
    return 'About $minutes minutes remaining';
  }

  @override
  String get aboutAMinuteRemaining => 'About a minute remaining';

  @override
  String get almostDone => 'Almost done...';

  @override
  String get omiSays => 'omi says';

  @override
  String get analyzingYourData => 'Analyzing your data...';

  @override
  String migratingToProtection(String level) {
    return 'Migrating to $level protection...';
  }

  @override
  String get noDataToMigrateFinalizing => 'No data to migrate. Finalizing...';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return 'Migrating $itemType... $percentage%';
  }

  @override
  String get allObjectsMigratedFinalizing => 'All objects migrated. Finalizing...';

  @override
  String get migrationErrorOccurred => 'An error occurred during migration. Please try again.';

  @override
  String get migrationComplete => 'Migration complete!';

  @override
  String dataProtectedWithSettings(String level) {
    return 'Your data is now protected with the new $level settings.';
  }

  @override
  String get chatsLowercase => 'chats';

  @override
  String get dataLowercase => 'data';

  @override
  String get fallNotificationTitle => 'Ouch';

  @override
  String get fallNotificationBody => 'Did you fall?';

  @override
  String get importantConversationTitle => 'Dôležitý rozhovor';

  @override
  String get importantConversationBody => 'Práve ste mali dôležitý rozhovor. Klepnutím zdieľajte zhrnutie.';

  @override
  String get templateName => 'Názov šablóny';

  @override
  String get templateNameHint => 'napr. Extraktor úloh zo stretnutí';

  @override
  String get nameMustBeAtLeast3Characters => 'Názov musí mať aspoň 3 znaky';

  @override
  String get conversationPromptHint => 'napr. Extrahujte úlohy, prijaté rozhodnutia a kľúčové poznatky z konverzácie.';

  @override
  String get pleaseEnterAppPrompt => 'Zadajte prosím výzvu pre aplikáciu';

  @override
  String get promptMustBeAtLeast10Characters => 'Výzva musí mať aspoň 10 znakov';

  @override
  String get anyoneCanDiscoverTemplate => 'Ktokoľvek môže objaviť vašu šablónu';

  @override
  String get onlyYouCanUseTemplate => 'Iba vy môžete používať túto šablónu';

  @override
  String get generatingDescription => 'Generovanie popisu...';

  @override
  String get creatingAppIcon => 'Vytváranie ikony aplikácie...';

  @override
  String get installingApp => 'Inštalácia aplikácie...';

  @override
  String get appCreatedAndInstalled => 'Aplikácia vytvorená a nainštalovaná!';

  @override
  String get appCreatedSuccessfully => 'Aplikácia úspešne vytvorená!';

  @override
  String get failedToCreateApp => 'Nepodarilo sa vytvoriť aplikáciu. Skúste to znova.';
}
