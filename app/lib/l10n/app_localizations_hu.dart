// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Hungarian (`hu`).
class AppLocalizationsHu extends AppLocalizations {
  AppLocalizationsHu([String locale = 'hu']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'Beszélgetés';

  @override
  String get transcriptTab => 'Átirat';

  @override
  String get actionItemsTab => 'Teendők';

  @override
  String get deleteConversationTitle => 'Beszélgetés törlése?';

  @override
  String get deleteConversationMessage =>
      'Biztosan törölni szeretnéd ezt a beszélgetést? Ez a művelet nem vonható vissza.';

  @override
  String get confirm => 'Megerősítés';

  @override
  String get cancel => 'Mégse';

  @override
  String get ok => 'OK';

  @override
  String get delete => 'Törlés';

  @override
  String get add => 'Hozzáadás';

  @override
  String get update => 'Frissítés';

  @override
  String get save => 'Mentés';

  @override
  String get edit => 'Szerkesztés';

  @override
  String get close => 'Bezárás';

  @override
  String get clear => 'Törlés';

  @override
  String get copyTranscript => 'Átirat másolása';

  @override
  String get copySummary => 'Összefoglaló másolása';

  @override
  String get testPrompt => 'Prompt tesztelése';

  @override
  String get reprocessConversation => 'Beszélgetés újrafeldolgozása';

  @override
  String get deleteConversation => 'Beszélgetés törlése';

  @override
  String get contentCopied => 'Tartalom vágólapra másolva';

  @override
  String get failedToUpdateStarred => 'A csillagozás frissítése sikertelen.';

  @override
  String get conversationUrlNotShared => 'A beszélgetés URL-je nem volt megosztható.';

  @override
  String get errorProcessingConversation =>
      'Hiba történt a beszélgetés feldolgozása során. Kérlek, próbáld újra később.';

  @override
  String get noInternetConnection => 'Kérlek, ellenőrizd az internetkapcsolatot, és próbáld újra.';

  @override
  String get unableToDeleteConversation => 'Nem lehet törölni a beszélgetést';

  @override
  String get somethingWentWrong => 'Valami hiba történt! Kérlek, próbáld újra később.';

  @override
  String get copyErrorMessage => 'Hibaüzenet másolása';

  @override
  String get errorCopied => 'Hibaüzenet vágólapra másolva';

  @override
  String get remaining => 'Hátralévő';

  @override
  String get loading => 'Betöltés...';

  @override
  String get loadingDuration => 'Időtartam betöltése...';

  @override
  String secondsCount(int count) {
    return '$count másodperc';
  }

  @override
  String get people => 'Személyek';

  @override
  String get addNewPerson => 'Új személy hozzáadása';

  @override
  String get editPerson => 'Személy szerkesztése';

  @override
  String get createPersonHint => 'Hozz létre egy új személyt, és tanítsd meg az Omi-t, hogy felismerje a beszédét is!';

  @override
  String get speechProfile => 'Beszédprofil';

  @override
  String sampleNumber(int number) {
    return '$number. minta';
  }

  @override
  String get settings => 'Beállítások';

  @override
  String get language => 'Nyelv';

  @override
  String get selectLanguage => 'Nyelv kiválasztása';

  @override
  String get deleting => 'Törlés...';

  @override
  String get pleaseCompleteAuthentication =>
      'Kérlek, fejezd be a hitelesítést a böngésződben. Ha kész, térj vissza az alkalmazásba.';

  @override
  String get failedToStartAuthentication => 'A hitelesítés indítása sikertelen';

  @override
  String get importStarted => 'Az importálás elkezdődött! Értesítünk, amikor befejeződik.';

  @override
  String get failedToStartImport => 'Az importálás indítása sikertelen. Kérlek, próbáld újra.';

  @override
  String get couldNotAccessFile => 'Nem sikerült hozzáférni a kiválasztott fájlhoz';

  @override
  String get askOmi => 'Kérdezd Omi-t';

  @override
  String get done => 'Kész';

  @override
  String get disconnected => 'Leválasztva';

  @override
  String get searching => 'Keresés';

  @override
  String get connectDevice => 'Eszköz csatlakoztatása';

  @override
  String get monthlyLimitReached => 'Elérted a havi keretet.';

  @override
  String get checkUsage => 'Használat ellenőrzése';

  @override
  String get syncingRecordings => 'Felvételek szinkronizálása';

  @override
  String get recordingsToSync => 'Szinkronizálandó felvételek';

  @override
  String get allCaughtUp => 'Minden naprakész';

  @override
  String get sync => 'Szinkronizálás';

  @override
  String get pendantUpToDate => 'A medál naprakész';

  @override
  String get allRecordingsSynced => 'Minden felvétel szinkronizálva';

  @override
  String get syncingInProgress => 'Szinkronizálás folyamatban';

  @override
  String get readyToSync => 'Készen áll a szinkronizálásra';

  @override
  String get tapSyncToStart => 'Érintsd meg a Szinkronizálást az indításhoz';

  @override
  String get pendantNotConnected => 'A medál nincs csatlakoztatva. Csatlakoztasd a szinkronizáláshoz.';

  @override
  String get everythingSynced => 'Minden már szinkronizálva van.';

  @override
  String get recordingsNotSynced => 'Vannak még szinkronizálatlan felvételeid.';

  @override
  String get syncingBackground => 'Folytatjuk a felvételek szinkronizálását a háttérben.';

  @override
  String get noConversationsYet => 'Még nincsenek beszélgetések.';

  @override
  String get noStarredConversations => 'Még nincsenek csillagozott beszélgetések.';

  @override
  String get starConversationHint =>
      'Beszélgetés csillagozásához nyisd meg, és érintsd meg a csillag ikont a fejlécben.';

  @override
  String get searchConversations => 'Beszélgetések keresése';

  @override
  String selectedCount(int count, Object s) {
    return '$count kiválasztva';
  }

  @override
  String get merge => 'Összevonás';

  @override
  String get mergeConversations => 'Beszélgetések összevonása';

  @override
  String mergeConversationsMessage(int count) {
    return 'Ez $count beszélgetést egyesít egybe. Minden tartalom összevonásra és újragenerálásra kerül.';
  }

  @override
  String get mergingInBackground => 'Összevonás a háttérben. Ez eltarthat egy pillanatig.';

  @override
  String get failedToStartMerge => 'Az összevonás indítása sikertelen';

  @override
  String get askAnything => 'Kérdezz bármit';

  @override
  String get noMessagesYet => 'Még nincsenek üzenetek!\nMiért nem kezdesz egy beszélgetést?';

  @override
  String get deletingMessages => 'Üzenetek törlése az Omi memóriájából...';

  @override
  String get messageCopied => 'Üzenet vágólapra másolva.';

  @override
  String get cannotReportOwnMessage => 'Nem jelentheted be a saját üzeneteidet.';

  @override
  String get reportMessage => 'Üzenet bejelentése';

  @override
  String get reportMessageConfirm => 'Biztosan be szeretnéd jelenteni ezt az üzenetet?';

  @override
  String get messageReported => 'Üzenet sikeresen bejelentve.';

  @override
  String get thankYouFeedback => 'Köszönjük a visszajelzést!';

  @override
  String get clearChat => 'Csevegés törlése?';

  @override
  String get clearChatConfirm => 'Biztosan törölni szeretnéd a csevegést? Ez a művelet nem vonható vissza.';

  @override
  String get maxFilesLimit => 'Egyszerre csak 4 fájlt tölthetsz fel';

  @override
  String get chatWithOmi => 'Csevegés Omi-val';

  @override
  String get apps => 'Alkalmazások';

  @override
  String get noAppsFound => 'Nem találhatók alkalmazások';

  @override
  String get tryAdjustingSearch => 'Próbáld módosítani a keresést vagy a szűrőket';

  @override
  String get createYourOwnApp => 'Saját alkalmazás létrehozása';

  @override
  String get buildAndShareApp => 'Építsd meg és oszd meg egyedi alkalmazásodat';

  @override
  String get searchApps => 'Keresés 1500+ alkalmazás között';

  @override
  String get myApps => 'Saját alkalmazások';

  @override
  String get installedApps => 'Telepített alkalmazások';

  @override
  String get unableToFetchApps =>
      'Nem sikerült betölteni az alkalmazásokat :(\n\nKérlek, ellenőrizd az internetkapcsolatot, és próbáld újra.';

  @override
  String get aboutOmi => 'Az Omi-ról';

  @override
  String get privacyPolicy => 'Adatvédelmi szabályzatot';

  @override
  String get visitWebsite => 'Weboldal meglátogatása';

  @override
  String get helpOrInquiries => 'Segítség vagy kérdések?';

  @override
  String get joinCommunity => 'Csatlakozz a közösséghez!';

  @override
  String get membersAndCounting => '8000+ tag és még mindig nő.';

  @override
  String get deleteAccountTitle => 'Fiók törlése';

  @override
  String get deleteAccountConfirm => 'Biztosan törölni szeretnéd a fiókodat?';

  @override
  String get cannotBeUndone => 'Ez nem vonható vissza.';

  @override
  String get allDataErased => 'Minden emléked és beszélgetésed véglegesen törlésre kerül.';

  @override
  String get appsDisconnected => 'Alkalmazásaid és integrációid azonnal leválasztásra kerülnek.';

  @override
  String get exportBeforeDelete =>
      'Exportálhatod az adataidat a fiók törlése előtt, de törlés után nem állítható vissza.';

  @override
  String get deleteAccountCheckbox =>
      'Megértettem, hogy a fiókom törlése végleges, és minden adat, beleértve az emlékeket és beszélgetéseket, elvész és nem állítható vissza.';

  @override
  String get areYouSure => 'Biztos vagy benne?';

  @override
  String get deleteAccountFinal =>
      'Ez a művelet visszafordíthatatlan, és véglegesen törli a fiókodat és minden kapcsolódó adatot. Biztosan folytatni szeretnéd?';

  @override
  String get deleteNow => 'Törlés most';

  @override
  String get goBack => 'Vissza';

  @override
  String get checkBoxToConfirm =>
      'Jelöld be a négyzetet, hogy megerősítsd, megértetted, hogy a fiókod törlése végleges és visszafordíthatatlan.';

  @override
  String get profile => 'Profil';

  @override
  String get name => 'Név';

  @override
  String get email => 'E-mail';

  @override
  String get customVocabulary => 'Egyedi szókincs';

  @override
  String get identifyingOthers => 'Mások azonosítása';

  @override
  String get paymentMethods => 'Fizetési módok';

  @override
  String get conversationDisplay => 'Beszélgetés megjelenítése';

  @override
  String get dataPrivacy => 'Adatok és adatvédelem';

  @override
  String get userId => 'Felhasználói azonosító';

  @override
  String get notSet => 'Nincs beállítva';

  @override
  String get userIdCopied => 'Felhasználói azonosító vágólapra másolva';

  @override
  String get systemDefault => 'Rendszer alapértelmezett';

  @override
  String get planAndUsage => 'Előfizetés és használat';

  @override
  String get offlineSync => 'Offline szinkronizálás';

  @override
  String get deviceSettings => 'Eszköz beállításai';

  @override
  String get chatTools => 'Csevegés eszközök';

  @override
  String get feedbackBug => 'Visszajelzés / hiba';

  @override
  String get helpCenter => 'Súgó központ';

  @override
  String get developerSettings => 'Fejlesztői beállítások';

  @override
  String get getOmiForMac => 'Szerezd be az Omi-t Mac-re';

  @override
  String get referralProgram => 'Ajánlói program';

  @override
  String get signOut => 'Kijelentkezés';

  @override
  String get appAndDeviceCopied => 'Alkalmazás és eszköz részletei másolva';

  @override
  String get wrapped2025 => 'Wrapped 2025';

  @override
  String get yourPrivacyYourControl => 'Adatvédelem, saját ellenőrzésed alatt';

  @override
  String get privacyIntro =>
      'Az Omi-nál elkötelezettek vagyunk az adatvédelem iránt. Ez az oldal lehetővé teszi az adataid tárolásának és felhasználásának szabályozását.';

  @override
  String get learnMore => 'További információ...';

  @override
  String get dataProtectionLevel => 'Adatvédelmi szint';

  @override
  String get dataProtectionDesc =>
      'Az adataid alapértelmezetten erős titkosítással védettek. Tekintsd át a beállításaidat és a jövőbeli adatvédelmi lehetőségeket alább.';

  @override
  String get appAccess => 'Alkalmazás hozzáférés';

  @override
  String get appAccessDesc =>
      'A következő alkalmazások férhetnek hozzá az adataidhoz. Érintsd meg az alkalmazást az engedélyek kezeléséhez.';

  @override
  String get noAppsExternalAccess => 'Egyik telepített alkalmazás sem rendelkezik külső hozzáféréssel az adataidhoz.';

  @override
  String get deviceName => 'Eszköz neve';

  @override
  String get deviceId => 'Eszköz azonosító';

  @override
  String get firmware => 'Firmware';

  @override
  String get sdCardSync => 'SD kártya szinkronizálás';

  @override
  String get hardwareRevision => 'Hardver verzió';

  @override
  String get modelNumber => 'Modellszám';

  @override
  String get manufacturer => 'Gyártó';

  @override
  String get doubleTap => 'Dupla érintés';

  @override
  String get ledBrightness => 'LED fényerő';

  @override
  String get micGain => 'Mikrofon erősítés';

  @override
  String get disconnect => 'Leválasztás';

  @override
  String get forgetDevice => 'Eszköz elfelejtése';

  @override
  String get chargingIssues => 'Töltési problémák';

  @override
  String get disconnectDevice => 'Eszköz leválasztása';

  @override
  String get unpairDevice => 'Eszköz párosításának megszüntetése';

  @override
  String get unpairAndForget => 'Párosítás megszüntetése és elfelejtés';

  @override
  String get deviceDisconnectedMessage => 'Az Omi leválasztásra került 😔';

  @override
  String get deviceUnpairedMessage =>
      'Eszköz párosítása megszüntetve. Menj a Beállítások > Bluetooth menübe, és felejtsd el az eszközt a folyamat befejezéséhez.';

  @override
  String get unpairDialogTitle => 'Eszköz párosításának megszüntetése';

  @override
  String get unpairDialogMessage =>
      'Ez megszünteti az eszköz párosítását, így másik telefonhoz csatlakoztatható. Menned kell a Beállítások > Bluetooth menübe, és el kell felejtened az eszközt a folyamat befejezéséhez.';

  @override
  String get deviceNotConnected => 'Eszköz nincs csatlakoztatva';

  @override
  String get connectDeviceMessage =>
      'Csatlakoztasd az Omi eszközödet az eszköz\nbeállítások és testreszabás eléréséhez';

  @override
  String get deviceInfoSection => 'Eszköz információk';

  @override
  String get customizationSection => 'Testreszabás';

  @override
  String get hardwareSection => 'Hardver';

  @override
  String get v2Undetected => 'V2 nem észlelhető';

  @override
  String get v2UndetectedMessage =>
      'Úgy látjuk, hogy vagy V1 eszközöd van, vagy az eszközöd nincs csatlakoztatva. Az SD kártya funkció csak V2 eszközökön érhető el.';

  @override
  String get endConversation => 'Beszélgetés befejezése';

  @override
  String get pauseResume => 'Szünet/folytatás';

  @override
  String get starConversation => 'Beszélgetés csillagozása';

  @override
  String get doubleTapAction => 'Dupla érintés művelet';

  @override
  String get endAndProcess => 'Beszélgetés befejezése és feldolgozása';

  @override
  String get pauseResumeRecording => 'Felvétel szüneteltetése/folytatása';

  @override
  String get starOngoing => 'Folyamatban lévő beszélgetés csillagozása';

  @override
  String get off => 'Ki';

  @override
  String get max => 'Maximum';

  @override
  String get mute => 'Némítás';

  @override
  String get quiet => 'Halk';

  @override
  String get normal => 'Normál';

  @override
  String get high => 'Magas';

  @override
  String get micGainDescMuted => 'Mikrofon némítva';

  @override
  String get micGainDescLow => 'Nagyon halk - zajos környezethez';

  @override
  String get micGainDescModerate => 'Halk - közepes zajhoz';

  @override
  String get micGainDescNeutral => 'Semleges - kiegyensúlyozott felvétel';

  @override
  String get micGainDescSlightlyBoosted => 'Enyhén felerősített - normál használat';

  @override
  String get micGainDescBoosted => 'Felerősített - csendes környezethez';

  @override
  String get micGainDescHigh => 'Magas - távoli vagy halk hangokhoz';

  @override
  String get micGainDescVeryHigh => 'Nagyon magas - nagyon csendes forrásokhoz';

  @override
  String get micGainDescMax => 'Maximum - óvatosan használd';

  @override
  String get developerSettingsTitle => 'Fejlesztői beállítások';

  @override
  String get saving => 'Mentés...';

  @override
  String get personaConfig => 'AI személyiség beállítása';

  @override
  String get beta => 'BÉTA';

  @override
  String get transcription => 'Átírás';

  @override
  String get transcriptionConfig => 'STT szolgáltató beállítása';

  @override
  String get conversationTimeout => 'Beszélgetés időkorlátja';

  @override
  String get conversationTimeoutConfig => 'Beszélgetések automatikus befejezésének beállítása';

  @override
  String get importData => 'Adatok importálása';

  @override
  String get importDataConfig => 'Adatok importálása más forrásokból';

  @override
  String get debugDiagnostics => 'Hibakeresés és diagnosztika';

  @override
  String get endpointUrl => 'Végpont URL';

  @override
  String get noApiKeys => 'Még nincsenek API kulcsok';

  @override
  String get createKeyToStart => 'Hozz létre egy kulcsot a kezdéshez';

  @override
  String get createKey => 'Kulcs létrehozása';

  @override
  String get docs => 'Dokumentáció';

  @override
  String get yourOmiInsights => 'Omi statisztikáid';

  @override
  String get today => 'Ma';

  @override
  String get thisMonth => 'Ez a hónap';

  @override
  String get thisYear => 'Ez az év';

  @override
  String get allTime => 'Minden idők';

  @override
  String get noActivityYet => 'Még nincs aktivitás';

  @override
  String get startConversationToSeeInsights =>
      'Kezdj egy beszélgetést Omi-val,\nhogy itt lásd a használati statisztikáidat.';

  @override
  String get listening => 'Figyelés';

  @override
  String get listeningSubtitle => 'Az összes idő, amit az Omi aktívan figyelt.';

  @override
  String get understanding => 'Megértés';

  @override
  String get understandingSubtitle => 'A beszélgetéseidből megértett szavak.';

  @override
  String get providing => 'Nyújtás';

  @override
  String get providingSubtitle => 'Automatikusan rögzített teendők és jegyzetek.';

  @override
  String get remembering => 'Emlékezés';

  @override
  String get rememberingSubtitle => 'Számodra megjegyzett tények és részletek.';

  @override
  String get unlimitedPlan => 'Korlátlan csomag';

  @override
  String get managePlan => 'Csomag kezelése';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'Előfizetésed $date-án megszűnik.';
  }

  @override
  String renewsOn(String date) {
    return 'Előfizetésed $date-án megújul.';
  }

  @override
  String get basicPlan => 'Ingyenes csomag';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used / $limit perc felhasználva';
  }

  @override
  String get upgrade => 'Frissítés';

  @override
  String get upgradeToUnlimited => 'Frissítés korlátlanra';

  @override
  String basicPlanDesc(int limit) {
    return 'Csomagod $limit ingyenes percet tartalmaz havonta. Frissíts a korlátlan használathoz.';
  }

  @override
  String get shareStatsMessage =>
      'Megosztom az Omi statisztikáimat! (omi.me - mindig rendelkezésre álló AI asszisztensed)';

  @override
  String get sharePeriodToday => 'Ma az omi:';

  @override
  String get sharePeriodMonth => 'Ebben a hónapban az omi:';

  @override
  String get sharePeriodYear => 'Ebben az évben az omi:';

  @override
  String get sharePeriodAllTime => 'Eddig az omi:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 $minutes percet figyelt';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 $words szót megértett';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ $count betekintést nyújtott';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 $count emléket jegyzett meg';
  }

  @override
  String get debugLogs => 'Hibakeresési naplók';

  @override
  String get debugLogsAutoDelete => 'Automatikus törlés 3 nap után.';

  @override
  String get debugLogsDesc => 'Segít a problémák diagnosztizálásában';

  @override
  String get noLogFilesFound => 'Nem találhatók naplófájlok.';

  @override
  String get omiDebugLog => 'Omi hibakeresési napló';

  @override
  String get logShared => 'Napló megosztva';

  @override
  String get selectLogFile => 'Naplófájl kiválasztása';

  @override
  String get shareLogs => 'Naplók megosztása';

  @override
  String get debugLogCleared => 'Hibakeresési napló törölve';

  @override
  String get exportStarted => 'Exportálás elkezdődött. Ez eltarthat néhány másodpercig...';

  @override
  String get exportAllData => 'Minden adat exportálása';

  @override
  String get exportDataDesc => 'Beszélgetések exportálása JSON fájlba';

  @override
  String get exportedConversations => 'Exportált beszélgetések az Omi-ból';

  @override
  String get exportShared => 'Exportálás megosztva';

  @override
  String get deleteKnowledgeGraphTitle => 'Tudásgráf törlése?';

  @override
  String get deleteKnowledgeGraphMessage =>
      'Ez törli az összes származtatott tudásgráf adatot (csomópontok és kapcsolatok). Az eredeti emlékeid biztonságban maradnak. A gráf idővel vagy a következő kérésre újjáépül.';

  @override
  String get knowledgeGraphDeleted => 'Tudásgráf sikeresen törölve';

  @override
  String deleteGraphFailed(String error) {
    return 'Gráf törlése sikertelen: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'Tudásgráf törlése';

  @override
  String get deleteKnowledgeGraphDesc => 'Összes csomópont és kapcsolat törlése';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'MCP szerver';

  @override
  String get mcpServerDesc => 'AI asszisztensek csatlakoztatása az adataidhoz';

  @override
  String get serverUrl => 'Szerver URL';

  @override
  String get urlCopied => 'URL másolva';

  @override
  String get apiKeyAuth => 'API kulcs hitelesítés';

  @override
  String get header => 'Fejléc';

  @override
  String get authorizationBearer => 'Engedélyezés: Bearer <kulcs>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'Kliens azonosító';

  @override
  String get clientSecret => 'Kliens titok';

  @override
  String get useMcpApiKey => 'Használd az MCP API kulcsodat';

  @override
  String get webhooks => 'Webhookok';

  @override
  String get conversationEvents => 'Beszélgetés események';

  @override
  String get newConversationCreated => 'Új beszélgetés létrehozva';

  @override
  String get realtimeTranscript => 'Valós idejű átirat';

  @override
  String get transcriptReceived => 'Átirat fogadva';

  @override
  String get audioBytes => 'Hang byte-ok';

  @override
  String get audioDataReceived => 'Hangadatok fogadva';

  @override
  String get intervalSeconds => 'Időköz (másodperc)';

  @override
  String get daySummary => 'Napi összefoglaló';

  @override
  String get summaryGenerated => 'Összefoglaló generálva';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'Hozzáadás claude_desktop_config.json-hoz';

  @override
  String get copyConfig => 'Konfiguráció másolása';

  @override
  String get configCopied => 'Konfiguráció vágólapra másolva';

  @override
  String get listeningMins => 'Figyelés (perc)';

  @override
  String get understandingWords => 'Megértés (szavak)';

  @override
  String get insights => 'Betekintések';

  @override
  String get memories => 'Emlékek';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '$used / $limit perc felhasználva ebben a hónapban';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '$used / $limit szó felhasználva ebben a hónapban';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '$used / $limit betekintés nyerve ebben a hónapban';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return '$used / $limit emlék létrehozva ebben a hónapban';
  }

  @override
  String get visibility => 'Láthatóság';

  @override
  String get visibilitySubtitle => 'Szabályozd, mely beszélgetések jelenjenek meg a listában';

  @override
  String get showShortConversations => 'Rövid beszélgetések megjelenítése';

  @override
  String get showShortConversationsDesc => 'Küszöbértéknél rövidebb beszélgetések megjelenítése';

  @override
  String get showDiscardedConversations => 'Elvetett beszélgetések megjelenítése';

  @override
  String get showDiscardedConversationsDesc => 'Elvetettként megjelölt beszélgetések hozzáadása';

  @override
  String get shortConversationThreshold => 'Rövid beszélgetés küszöbérték';

  @override
  String get shortConversationThresholdSubtitle =>
      'Ennél rövidebb beszélgetések el lesznek rejtve, ha fent nincs engedélyezve';

  @override
  String get durationThreshold => 'Időtartam küszöbérték';

  @override
  String get durationThresholdDesc => 'Ennél rövidebb beszélgetések elrejtése';

  @override
  String minLabel(int count) {
    return '$count perc';
  }

  @override
  String get customVocabularyTitle => 'Egyedi szókincs';

  @override
  String get addWords => 'Szavak hozzáadása';

  @override
  String get addWordsDesc => 'Nevek, kifejezések vagy ritka szavak';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'Csatlakozás';

  @override
  String get comingSoon => 'Hamarosan';

  @override
  String get chatToolsFooter =>
      'Csatlakoztasd az alkalmazásaidat az adatok és metrikák megjelenítéséhez a csevegésben.';

  @override
  String get completeAuthInBrowser =>
      'Kérlek, fejezd be a hitelesítést a böngésződben. Ha kész, térj vissza az alkalmazásba.';

  @override
  String failedToStartAuth(String appName) {
    return '$appName hitelesítés indítása sikertelen';
  }

  @override
  String disconnectAppTitle(String appName) {
    return '$appName leválasztása?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'Biztosan leválasztod a(z) $appName-t? Bármikor újracsatlakozthatsz.';
  }

  @override
  String disconnectedFrom(String appName) {
    return '$appName-től leválasztva';
  }

  @override
  String get failedToDisconnect => 'Leválasztás sikertelen';

  @override
  String connectTo(String appName) {
    return 'Csatlakozás: $appName';
  }

  @override
  String authAccessMessage(String appName) {
    return 'Engedélyezned kell az Omi-nak, hogy hozzáférjen a(z) $appName adataidhoz. Ez megnyitja a böngésződ a hitelesítéshez.';
  }

  @override
  String get continueAction => 'Folytatás';

  @override
  String get languageTitle => 'Nyelv';

  @override
  String get primaryLanguage => 'Elsődleges nyelv';

  @override
  String get automaticTranslation => 'Automatikus fordítás';

  @override
  String get detectLanguages => '10+ nyelv érzékelése';

  @override
  String get authorizeSavingRecordings => 'Felvételek mentésének engedélyezése';

  @override
  String get thanksForAuthorizing => 'Köszönjük az engedélyezést!';

  @override
  String get needYourPermission => 'Szükségünk van az engedélyedre';

  @override
  String get alreadyGavePermission =>
      'Már engedélyezted a felvételeid mentését. Itt egy emlékeztető, hogy miért van erre szükségünk:';

  @override
  String get wouldLikePermission =>
      'Szeretnénk az engedélyedet kérni a hangfelvételeid mentéséhez. Itt van, hogy miért:';

  @override
  String get improveSpeechProfile => 'Beszédprofil fejlesztése';

  @override
  String get improveSpeechProfileDesc =>
      'A felvételeket használjuk a személyes beszédprofilod további tanítására és fejlesztésére.';

  @override
  String get trainFamilyProfiles => 'Profilok tanítása barátoknak és családtagoknak';

  @override
  String get trainFamilyProfilesDesc =>
      'A felvételeid segítenek felismerni és profilokat létrehozni a barátaidnak és családtagjaidnak.';

  @override
  String get enhanceTranscriptAccuracy => 'Átirat pontosságának növelése';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'Ahogy a modellünk fejlődik, jobb átírási eredményeket tudunk biztosítani a felvételeidhez.';

  @override
  String get legalNotice =>
      'Jogi közlemény: A hangadatok rögzítésének és tárolásának jogszerűsége a tartózkodási helyedtől és a funkció használatától függően változhat. A helyi törvényeknek és szabályozásoknak való megfelelés a te felelősséged.';

  @override
  String get alreadyAuthorized => 'Már engedélyezve';

  @override
  String get authorize => 'Engedélyezés';

  @override
  String get revokeAuthorization => 'Engedély visszavonása';

  @override
  String get authorizationSuccessful => 'Engedélyezés sikeres!';

  @override
  String get failedToAuthorize => 'Engedélyezés sikertelen. Kérlek, próbáld újra.';

  @override
  String get authorizationRevoked => 'Engedély visszavonva.';

  @override
  String get recordingsDeleted => 'Felvételek törölve.';

  @override
  String get failedToRevoke => 'Engedély visszavonása sikertelen. Kérlek, próbáld újra.';

  @override
  String get permissionRevokedTitle => 'Engedély visszavonva';

  @override
  String get permissionRevokedMessage => 'Szeretnéd, hogy az összes meglévő felvételedet is töröljük?';

  @override
  String get yes => 'Igen';

  @override
  String get editName => 'Név szerkesztése';

  @override
  String get howShouldOmiCallYou => 'Hogyan szólítson az Omi?';

  @override
  String get enterYourName => 'Add meg a neved';

  @override
  String get nameCannotBeEmpty => 'A név nem lehet üres';

  @override
  String get nameUpdatedSuccessfully => 'Név sikeresen frissítve!';

  @override
  String get calendarSettings => 'Naptár beállítások';

  @override
  String get calendarProviders => 'Naptár szolgáltatók';

  @override
  String get macOsCalendar => 'macOS naptár';

  @override
  String get connectMacOsCalendar => 'Helyi macOS naptár csatlakoztatása';

  @override
  String get googleCalendar => 'Google naptár';

  @override
  String get syncGoogleAccount => 'Szinkronizálás Google fiókoddal';

  @override
  String get showMeetingsMenuBar => 'Közelgő találkozók megjelenítése a menüsorban';

  @override
  String get showMeetingsMenuBarDesc =>
      'A következő találkozód és a kezdésig hátralévő idő megjelenítése a macOS menüsorban';

  @override
  String get showEventsNoParticipants => 'Résztvevők nélküli események megjelenítése';

  @override
  String get showEventsNoParticipantsDesc =>
      'Ha engedélyezve van, a Közelgő események résztvevők vagy videó link nélküli eseményeket is mutat.';

  @override
  String get yourMeetings => 'Találkozóid';

  @override
  String get refresh => 'Frissítés';

  @override
  String get noUpcomingMeetings => 'Nem találhatók közelgő találkozók';

  @override
  String get checkingNextDays => 'Következő 30 nap ellenőrzése';

  @override
  String get tomorrow => 'Holnap';

  @override
  String get googleCalendarComingSoon => 'Google naptár integráció hamarosan!';

  @override
  String connectedAsUser(String userId) {
    return 'Csatlakozva mint felhasználó: $userId';
  }

  @override
  String get defaultWorkspace => 'Alapértelmezett munkaterület';

  @override
  String get tasksCreatedInWorkspace => 'A feladatok ebben a munkaterületen lesznek létrehozva';

  @override
  String get defaultProjectOptional => 'Alapértelmezett projekt (opcionális)';

  @override
  String get leaveUnselectedTasks => 'Hagyd kiválasztatlanul projekt nélküli feladatok létrehozásához';

  @override
  String get noProjectsInWorkspace => 'Nem találhatók projektek ebben a munkaterületen';

  @override
  String get conversationTimeoutDesc =>
      'Válaszd ki, mennyi ideig várjon csendben a beszélgetés automatikus befejezése előtt:';

  @override
  String get timeout2Minutes => '2 perc';

  @override
  String get timeout2MinutesDesc => 'Beszélgetés befejezése 2 perc csend után';

  @override
  String get timeout5Minutes => '5 perc';

  @override
  String get timeout5MinutesDesc => 'Beszélgetés befejezése 5 perc csend után';

  @override
  String get timeout10Minutes => '10 perc';

  @override
  String get timeout10MinutesDesc => 'Beszélgetés befejezése 10 perc csend után';

  @override
  String get timeout30Minutes => '30 perc';

  @override
  String get timeout30MinutesDesc => 'Beszélgetés befejezése 30 perc csend után';

  @override
  String get timeout4Hours => '4 óra';

  @override
  String get timeout4HoursDesc => 'Beszélgetés befejezése 4 óra csend után';

  @override
  String get conversationEndAfterHours => 'A beszélgetések mostantól 4 óra csend után végződnek';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'A beszélgetések mostantól $minutes perc csend után végződnek';
  }

  @override
  String get tellUsPrimaryLanguage => 'Add meg az elsődleges nyelvedet';

  @override
  String get languageForTranscription => 'Állítsd be a nyelvedet a pontosabb átíráshoz és személyre szabott élményhez.';

  @override
  String get singleLanguageModeInfo =>
      'Egynyelvű mód engedélyezve. A fordítás ki van kapcsolva a nagyobb pontosság érdekében.';

  @override
  String get searchLanguageHint => 'Keress nyelvet név vagy kód alapján';

  @override
  String get noLanguagesFound => 'Nem találhatók nyelvek';

  @override
  String get skip => 'Kihagyás';

  @override
  String languageSetTo(String language) {
    return 'Nyelv beállítva: $language';
  }

  @override
  String get failedToSetLanguage => 'Nyelv beállítása sikertelen';

  @override
  String appSettings(String appName) {
    return '$appName beállítások';
  }

  @override
  String disconnectFromApp(String appName) {
    return '$appName leválasztása?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'Ez eltávolítja a(z) $appName hitelesítésedet. Újra kell csatlakoznod a használathoz.';
  }

  @override
  String connectedToApp(String appName) {
    return 'Csatlakozva: $appName';
  }

  @override
  String get account => 'Fiók';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'A teendőid szinkronizálva lesznek a(z) $appName fiókodhoz';
  }

  @override
  String get defaultSpace => 'Alapértelmezett terület';

  @override
  String get selectSpaceInWorkspace => 'Válassz egy területet a munkaterületen';

  @override
  String get noSpacesInWorkspace => 'Nem találhatók területek ebben a munkaterületen';

  @override
  String get defaultList => 'Alapértelmezett lista';

  @override
  String get tasksAddedToList => 'A feladatok ehhez a listához lesznek hozzáadva';

  @override
  String get noListsInSpace => 'Nem találhatók listák ezen a területen';

  @override
  String failedToLoadRepos(String error) {
    return 'Tárolók betöltése sikertelen: $error';
  }

  @override
  String get defaultRepoSaved => 'Alapértelmezett tároló mentve';

  @override
  String get failedToSaveDefaultRepo => 'Alapértelmezett tároló mentése sikertelen';

  @override
  String get defaultRepository => 'Alapértelmezett tároló';

  @override
  String get selectDefaultRepoDesc =>
      'Válassz egy alapértelmezett tárolót a problémák létrehozásához. Problémák létrehozásakor továbbra is megadhatsz másik tárolót.';

  @override
  String get noReposFound => 'Nem találhatók tárolók';

  @override
  String get private => 'Privát';

  @override
  String updatedDate(String date) {
    return 'Frissítve: $date';
  }

  @override
  String get yesterday => 'tegnap';

  @override
  String daysAgo(int count) {
    return '$count napja';
  }

  @override
  String get oneWeekAgo => '1 hete';

  @override
  String weeksAgo(int count) {
    return '$count hete';
  }

  @override
  String get oneMonthAgo => '1 hónapja';

  @override
  String monthsAgo(int count) {
    return '$count hónapja';
  }

  @override
  String get issuesCreatedInRepo => 'A problémák az alapértelmezett tárolódban lesznek létrehozva';

  @override
  String get taskIntegrations => 'Feladat integrációk';

  @override
  String get configureSettings => 'Beállítások konfigurálása';

  @override
  String get completeAuthBrowser =>
      'Kérlek, fejezd be a hitelesítést a böngésződben. Ha kész, térj vissza az alkalmazásba.';

  @override
  String failedToStartAppAuth(String appName) {
    return '$appName hitelesítés indítása sikertelen';
  }

  @override
  String connectToAppTitle(String appName) {
    return 'Csatlakozás: $appName';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Engedélyezned kell az Omi-nak, hogy feladatokat hozzon létre a(z) $appName fiókodban. Ez megnyitja a böngésződ a hitelesítéshez.';
  }

  @override
  String get continueButton => 'Folytatás';

  @override
  String appIntegration(String appName) {
    return '$appName integráció';
  }

  @override
  String integrationComingSoon(String appName) {
    return 'A(z) $appName integrációja hamarosan! Keményen dolgozunk, hogy több feladatkezelési lehetőséget hozzunk.';
  }

  @override
  String get gotIt => 'Értem';

  @override
  String get tasksExportedOneApp => 'A feladatok egyszerre csak egy alkalmazásba exportálhatók.';

  @override
  String get completeYourUpgrade => 'Fejezd be a frissítést';

  @override
  String get importConfiguration => 'Konfiguráció importálása';

  @override
  String get exportConfiguration => 'Konfiguráció exportálása';

  @override
  String get bringYourOwn => 'Hozd a sajátod';

  @override
  String get payYourSttProvider => 'Szabadon használd az omi-t. Csak az STT szolgáltatódnak fizetsz közvetlenül.';

  @override
  String get freeMinutesMonth => '1200 ingyenes perc/hónap tartalmazza. Korlátlan a következővel: ';

  @override
  String get omiUnlimited => 'Omi Unlimited';

  @override
  String get hostRequired => 'Host szükséges';

  @override
  String get validPortRequired => 'Érvényes port szükséges';

  @override
  String get validWebsocketUrlRequired => 'Érvényes WebSocket URL szükséges (wss://)';

  @override
  String get apiUrlRequired => 'API URL szükséges';

  @override
  String get apiKeyRequired => 'API kulcs szükséges';

  @override
  String get invalidJsonConfig => 'Érvénytelen JSON konfiguráció';

  @override
  String errorSaving(String error) {
    return 'Mentési hiba: $error';
  }

  @override
  String get configCopiedToClipboard => 'Konfiguráció vágólapra másolva';

  @override
  String get pasteJsonConfig => 'Illeszd be a JSON konfigurációdat alább:';

  @override
  String get addApiKeyAfterImport => 'Importálás után hozzá kell adnod a saját API kulcsodat';

  @override
  String get paste => 'Beillesztés';

  @override
  String get import => 'Importálás';

  @override
  String get invalidProviderInConfig => 'Érvénytelen szolgáltató a konfigurációban';

  @override
  String importedConfig(String providerName) {
    return '$providerName konfiguráció importálva';
  }

  @override
  String invalidJson(String error) {
    return 'Érvénytelen JSON: $error';
  }

  @override
  String get provider => 'Szolgáltató';

  @override
  String get live => 'Élő';

  @override
  String get onDevice => 'Eszközön';

  @override
  String get apiUrl => 'API URL';

  @override
  String get enterSttHttpEndpoint => 'Add meg az STT HTTP végpontodat';

  @override
  String get websocketUrl => 'WebSocket URL';

  @override
  String get enterLiveSttWebsocket => 'Add meg az élő STT WebSocket végpontodat';

  @override
  String get apiKey => 'API kulcs';

  @override
  String get enterApiKey => 'Add meg az API kulcsodat';

  @override
  String get storedLocallyNeverShared => 'Helyileg tárolva, soha nem megosztott';

  @override
  String get host => 'Host';

  @override
  String get port => 'Port';

  @override
  String get advanced => 'Speciális';

  @override
  String get configuration => 'Konfiguráció';

  @override
  String get requestConfiguration => 'Kérés konfiguráció';

  @override
  String get responseSchema => 'Válasz séma';

  @override
  String get modified => 'Módosítva';

  @override
  String get resetRequestConfig => 'Kérés konfiguráció alaphelyzetbe állítása';

  @override
  String get logs => 'Naplók';

  @override
  String get logsCopied => 'Naplók másolva';

  @override
  String get noLogsYet => 'Még nincsenek naplók. Kezdj el rögzíteni az egyéni STT aktivitás megtekintéséhez.';

  @override
  String deviceUsesCodec(String deviceName, String codecReason) {
    return '$deviceName használja: $codecReason. Az Omi-t fogjuk használni.';
  }

  @override
  String get omiTranscription => 'Omi átírás';

  @override
  String get bestInClassTranscription => 'Legjobb átírás a kategóriában, zéró beállítással';

  @override
  String get instantSpeakerLabels => 'Azonnali beszélő címkék';

  @override
  String get languageTranslation => '100+ nyelv fordítása';

  @override
  String get optimizedForConversation => 'Beszélgetésre optimalizált';

  @override
  String get autoLanguageDetection => 'Automatikus nyelvfelismerés';

  @override
  String get highAccuracy => 'Nagy pontosság';

  @override
  String get privacyFirst => 'Adatvédelem az első';

  @override
  String get saveChanges => 'Változtatások mentése';

  @override
  String get resetToDefault => 'Alaphelyzetbe állítás';

  @override
  String get viewTemplate => 'Sablon megtekintése';

  @override
  String get trySomethingLike => 'Próbálj valami ilyesmit...';

  @override
  String get tryIt => 'Próbáld ki';

  @override
  String get creatingPlan => 'Terv készítése';

  @override
  String get developingLogic => 'Logika fejlesztése';

  @override
  String get designingApp => 'Alkalmazás tervezése';

  @override
  String get generatingIconStep => 'Ikon generálása';

  @override
  String get finalTouches => 'Utolsó simítások';

  @override
  String get processing => 'Feldolgozás...';

  @override
  String get features => 'Funkciók';

  @override
  String get creatingYourApp => 'Alkalmazásod létrehozása...';

  @override
  String get generatingIcon => 'Ikon generálása...';

  @override
  String get whatShouldWeMake => 'Mit készítsünk?';

  @override
  String get appName => 'Alkalmazás neve';

  @override
  String get description => 'Leírás';

  @override
  String get publicLabel => 'Nyilvános';

  @override
  String get privateLabel => 'Privát';

  @override
  String get free => 'Ingyenes';

  @override
  String get perMonth => '/ hónap';

  @override
  String get tailoredConversationSummaries => 'Személyre szabott beszélgetés összefoglalók';

  @override
  String get customChatbotPersonality => 'Egyéni chatbot személyiség';

  @override
  String get makePublic => 'Nyilvánossá tétel';

  @override
  String get anyoneCanDiscover => 'Bárki felfedezheti az alkalmazásodat';

  @override
  String get onlyYouCanUse => 'Csak te használhatod ezt az alkalmazást';

  @override
  String get paidApp => 'Fizetős alkalmazás';

  @override
  String get usersPayToUse => 'A felhasználók fizetnek az alkalmazásod használatáért';

  @override
  String get freeForEveryone => 'Ingyenes mindenki számára';

  @override
  String get perMonthLabel => '/ hónap';

  @override
  String get creating => 'Létrehozás...';

  @override
  String get createApp => 'Alkalmazás létrehozása';

  @override
  String get searchingForDevices => 'Eszközök keresése...';

  @override
  String devicesFoundNearby(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'ESZKÖZ',
      one: 'ESZKÖZ',
    );
    return '$count $_temp0 TALÁLHATÓ A KÖZELBEN';
  }

  @override
  String get pairingSuccessful => 'PÁROSÍTÁS SIKERES';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Hiba az Apple Watch csatlakoztatása során: $error';
  }

  @override
  String get dontShowAgain => 'Ne mutasd újra';

  @override
  String get iUnderstand => 'Megértettem';

  @override
  String get enableBluetooth => 'Bluetooth engedélyezése';

  @override
  String get bluetoothNeeded =>
      'Az Omi-nak Bluetoothra van szüksége a viselhető eszközhöz való csatlakozáshoz. Kérlek, engedélyezd a Bluetooth-t, és próbáld újra.';

  @override
  String get contactSupport => 'Ügyfélszolgálat elérése?';

  @override
  String get connectLater => 'Csatlakozás később';

  @override
  String get grantPermissions => 'Engedélyek megadása';

  @override
  String get backgroundActivity => 'Háttérműködés';

  @override
  String get backgroundActivityDesc => 'Engedd, hogy az Omi a háttérben fusson a jobb stabilitás érdekében';

  @override
  String get locationAccess => 'Helymeghatározás';

  @override
  String get locationAccessDesc => 'Háttérhelymeghatározás engedélyezése a teljes élményhez';

  @override
  String get notifications => 'Értesítések';

  @override
  String get notificationsDesc => 'Értesítések engedélyezése tájékozott maradáshoz';

  @override
  String get locationServiceDisabled => 'Helymeghatározási szolgáltatás letiltva';

  @override
  String get locationServiceDisabledDesc =>
      'A helymeghatározási szolgáltatás le van tiltva. Kérlek, menj a Beállítások > Adatvédelem és biztonság > Helyszolgáltatások menübe, és engedélyezd';

  @override
  String get backgroundLocationDenied => 'Háttérhelymeghatározás megtagadva';

  @override
  String get backgroundLocationDeniedDesc =>
      'Kérlek, menj az eszköz beállításaihoz, és állítsd a helymeghatározási engedélyt \"Mindig engedélyezés\"-re';

  @override
  String get lovingOmi => 'Tetszik az Omi?';

  @override
  String get leaveReviewIos =>
      'Segíts elérni több embert azzal, hogy értékelést hagysz az App Store-ban. A visszajelzésed sokat jelent nekünk!';

  @override
  String get leaveReviewAndroid =>
      'Segíts elérni több embert azzal, hogy értékelést hagysz a Google Play Áruházban. A visszajelzésed sokat jelent nekünk!';

  @override
  String get rateOnAppStore => 'Értékelés az App Store-ban';

  @override
  String get rateOnGooglePlay => 'Értékelés a Google Play-en';

  @override
  String get maybeLater => 'Talán később';

  @override
  String get speechProfileIntro => 'Az Omi-nak meg kell tanulnia a céljaidat és a hangodat. Később módosíthatod.';

  @override
  String get getStarted => 'Kezdés';

  @override
  String get allDone => 'Kész!';

  @override
  String get keepGoing => 'Csak így tovább, nagyszerűen csinálod';

  @override
  String get skipThisQuestion => 'Kérdés kihagyása';

  @override
  String get skipForNow => 'Egyelőre kihagyom';

  @override
  String get connectionError => 'Kapcsolódási hiba';

  @override
  String get connectionErrorDesc =>
      'Nem sikerült csatlakozni a szerverhez. Kérlek, ellenőrizd az internetkapcsolatot, és próbáld újra.';

  @override
  String get invalidRecordingMultipleSpeakers => 'Érvénytelen felvétel észlelve';

  @override
  String get multipleSpeakersDesc =>
      'Úgy tűnik, több beszélő van a felvételen. Kérlek, győződj meg róla, hogy csendes helyen vagy, és próbáld újra.';

  @override
  String get tooShortDesc => 'Nem észlelhető elegendő beszéd. Kérlek, beszélj többet, és próbáld újra.';

  @override
  String get invalidRecordingDesc =>
      'Kérlek, győződj meg róla, hogy legalább 5 másodpercig, de legfeljebb 90 másodpercig beszélsz.';

  @override
  String get areYouThere => 'Ott vagy?';

  @override
  String get noSpeechDesc =>
      'Nem tudtunk beszédet észlelni. Kérlek, győződj meg róla, hogy legalább 10 másodpercig, de legfeljebb 3 percig beszélsz.';

  @override
  String get connectionLost => 'Kapcsolat megszakadt';

  @override
  String get connectionLostDesc =>
      'A kapcsolat megszakadt. Kérlek, ellenőrizd az internetkapcsolatot, és próbáld újra.';

  @override
  String get tryAgain => 'Próbáld újra';

  @override
  String get connectOmiOmiGlass => 'Omi / OmiGlass csatlakoztatása';

  @override
  String get continueWithoutDevice => 'Folytatás eszköz nélkül';

  @override
  String get permissionsRequired => 'Engedélyek szükségesek';

  @override
  String get permissionsRequiredDesc =>
      'Ez az alkalmazás Bluetooth és helymeghatározási engedélyekre van szüksége a megfelelő működéshez. Kérlek, engedélyezd őket a beállításokban.';

  @override
  String get openSettings => 'Beállítások megnyitása';

  @override
  String get wantDifferentName => 'Máshogy szeretnéd, hogy hívjanak?';

  @override
  String get whatsYourName => 'Mi a neved?';

  @override
  String get speakTranscribeSummarize => 'Beszélj. Átírás. Összefoglalás.';

  @override
  String get signInWithApple => 'Bejelentkezés Apple-lel';

  @override
  String get signInWithGoogle => 'Bejelentkezés Google-lel';

  @override
  String get byContinuingAgree => 'A folytatással elfogadod az ';

  @override
  String get termsOfUse => 'Felhasználási feltételeket';

  @override
  String get omiYourAiCompanion => 'Omi – AI társad';

  @override
  String get captureEveryMoment =>
      'Rögzítsd minden pillanatot. Kapj AI-alapú\nösszefoglalókat. Soha többé ne kelljen jegyzetet készítened.';

  @override
  String get appleWatchSetup => 'Apple Watch beállítása';

  @override
  String get permissionRequestedExclaim => 'Engedély kérve!';

  @override
  String get microphonePermission => 'Mikrofon engedély';

  @override
  String get permissionGrantedNow =>
      'Engedély megadva! Most:\n\nNyisd meg az Omi alkalmazást az órádon, és érintsd meg a \"Folytatás\" gombot alább';

  @override
  String get needMicrophonePermission =>
      'Mikrofon engedélyre van szükségünk.\n\n1. Érintsd meg az \"Engedély megadása\" gombot\n2. Engedélyezd az iPhone-odon\n3. Az óra alkalmazás bezárul\n4. Nyisd meg újra, és érintsd meg a \"Folytatás\" gombot';

  @override
  String get grantPermissionButton => 'Engedély megadása';

  @override
  String get needHelp => 'Segítség kell?';

  @override
  String get troubleshootingSteps =>
      'Hibaelhárítás:\n\n1. Győződj meg róla, hogy az Omi telepítve van az órádon\n2. Nyisd meg az Omi alkalmazást az órádon\n3. Keresd az engedély felugró ablakot\n4. Érintsd meg az \"Engedélyezés\" gombot, amikor megjelenik\n5. Az óra alkalmazás bezárul - nyisd meg újra\n6. Térj vissza, és érintsd meg a \"Folytatás\" gombot az iPhone-odon';

  @override
  String get recordingStartedSuccessfully => 'Felvétel sikeresen elindult!';

  @override
  String get permissionNotGrantedYet =>
      'Az engedély még nincs megadva. Kérlek, győződj meg róla, hogy engedélyezted a mikrofon hozzáférést, és újra megnyitottad az alkalmazást az órádon.';

  @override
  String errorRequestingPermission(String error) {
    return 'Hiba az engedély kérésekor: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'Hiba a felvétel indításakor: $error';
  }

  @override
  String get selectPrimaryLanguage => 'Válaszd ki az elsődleges nyelvedet';

  @override
  String get languageBenefits => 'Állítsd be a nyelvedet a pontosabb átíráshoz és személyre szabott élményhez';

  @override
  String get whatsYourPrimaryLanguage => 'Mi az elsődleges nyelved?';

  @override
  String get selectYourLanguage => 'Válaszd ki a nyelvedet';

  @override
  String get personalGrowthJourney => 'Személyes fejlődési utad egy AI-val, amely minden szavadat figyeli.';

  @override
  String get actionItemsTitle => 'Teendők';

  @override
  String get actionItemsDescription =>
      'Érintsd meg a szerkesztéshez • Hosszan nyomd a kiválasztáshoz • Húzd a műveletekhez';

  @override
  String get tabToDo => 'Tennivaló';

  @override
  String get tabDone => 'Kész';

  @override
  String get tabOld => 'Régi';

  @override
  String get emptyTodoMessage => '🎉 Minden naprakész!\nNincsenek függőben lévő teendők';

  @override
  String get emptyDoneMessage => 'Még nincsenek befejezett elemek';

  @override
  String get emptyOldMessage => '✅ Nincsenek régi feladatok';

  @override
  String get noItems => 'Nincsenek elemek';

  @override
  String get actionItemMarkedIncomplete => 'Teendő befejezetlenként megjelölve';

  @override
  String get actionItemCompleted => 'Teendő befejezve';

  @override
  String get deleteActionItemTitle => 'Teendő törlése';

  @override
  String get deleteActionItemMessage => 'Biztosan törölni szeretnéd ezt a teendőt?';

  @override
  String get deleteSelectedItemsTitle => 'Kiválasztott elemek törlése';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Biztosan törölni szeretnéd a(z) $count kiválasztott teendő${s}t?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return '\"$description\" teendő törölve';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count teendő$s törölve';
  }

  @override
  String get failedToDeleteItem => 'Teendő törlése sikertelen';

  @override
  String get failedToDeleteItems => 'Elemek törlése sikertelen';

  @override
  String get failedToDeleteSomeItems => 'Néhány elem törlése sikertelen';

  @override
  String get welcomeActionItemsTitle => 'Készen állsz a teendőkre';

  @override
  String get welcomeActionItemsDescription =>
      'Az AI automatikusan kinyeri a feladatokat és teendőket a beszélgetéseidből. Itt jelennek meg, amikor létrejönnek.';

  @override
  String get autoExtractionFeature => 'Automatikusan kinyerve a beszélgetésekből';

  @override
  String get editSwipeFeature => 'Érintsd meg a szerkesztéshez, húzd a befejezéshez vagy törléshez';

  @override
  String itemsSelected(int count) {
    return '$count kiválasztva';
  }

  @override
  String get selectAll => 'Összes kiválasztása';

  @override
  String get deleteSelected => 'Kiválasztottak törlése';

  @override
  String searchMemories(int count) {
    return '$count emlék keresése';
  }

  @override
  String get memoryDeleted => 'Emlék törölve.';

  @override
  String get undo => 'Visszavonás';

  @override
  String get noMemoriesYet => 'Még nincsenek emlékek';

  @override
  String get noAutoMemories => 'Még nincsenek automatikusan kinyert emlékek';

  @override
  String get noManualMemories => 'Még nincsenek manuális emlékek';

  @override
  String get noMemoriesInCategories => 'Nincsenek emlékek ezekben a kategóriákban';

  @override
  String get noMemoriesFound => 'Nem találhatók emlékek';

  @override
  String get addFirstMemory => 'Add hozzá az első emlékedet';

  @override
  String get clearMemoryTitle => 'Omi emlékének törlése';

  @override
  String get clearMemoryMessage => 'Biztosan törölni szeretnéd az Omi emlékét? Ez a művelet nem vonható vissza.';

  @override
  String get clearMemoryButton => 'Emlék törlése';

  @override
  String get memoryClearedSuccess => 'Az Omi rólad szóló emléke törölve lett';

  @override
  String get noMemoriesToDelete => 'Nincsenek törlendő emlékek';

  @override
  String get createMemoryTooltip => 'Új emlék létrehozása';

  @override
  String get createActionItemTooltip => 'Új teendő létrehozása';

  @override
  String get memoryManagement => 'Emlékkezelés';

  @override
  String get filterMemories => 'Emlékek szűrése';

  @override
  String totalMemoriesCount(int count) {
    return 'Összesen $count emléked van';
  }

  @override
  String get publicMemories => 'Nyilvános emlékek';

  @override
  String get privateMemories => 'Privát emlékek';

  @override
  String get makeAllPrivate => 'Minden emlék priváttá tétele';

  @override
  String get makeAllPublic => 'Minden emlék nyilvánossá tétele';

  @override
  String get deleteAllMemories => 'Minden emlék törlése';

  @override
  String get allMemoriesPrivateResult => 'Minden emlék most privát';

  @override
  String get allMemoriesPublicResult => 'Minden emlék most nyilvános';

  @override
  String get newMemory => 'Új emlék';

  @override
  String get editMemory => 'Emlék szerkesztése';

  @override
  String get memoryContentHint => 'Szeretek fagyit enni...';

  @override
  String get failedToSaveMemory => 'Mentés sikertelen. Kérlek, ellenőrizd a kapcsolatot.';

  @override
  String get saveMemory => 'Emlék mentése';

  @override
  String get retry => 'Újrapróbálkozás';

  @override
  String get createActionItem => 'Teendő létrehozása';

  @override
  String get editActionItem => 'Teendő szerkesztése';

  @override
  String get actionItemDescriptionHint => 'Mit kell elvégezni?';

  @override
  String get actionItemDescriptionEmpty => 'A teendő leírása nem lehet üres.';

  @override
  String get actionItemUpdated => 'Teendő frissítve';

  @override
  String get failedToUpdateActionItem => 'Teendő frissítése sikertelen';

  @override
  String get actionItemCreated => 'Teendő létrehozva';

  @override
  String get failedToCreateActionItem => 'Teendő létrehozása sikertelen';

  @override
  String get dueDate => 'Határidő';

  @override
  String get time => 'Idő';

  @override
  String get addDueDate => 'Határidő hozzáadása';

  @override
  String get pressDoneToSave => 'Nyomd meg a kész gombot a mentéshez';

  @override
  String get pressDoneToCreate => 'Nyomd meg a kész gombot a létrehozáshoz';

  @override
  String get filterAll => 'Összes';

  @override
  String get filterSystem => 'Rólad';

  @override
  String get filterInteresting => 'Betekintések';

  @override
  String get filterManual => 'Manuális';

  @override
  String get completed => 'Befejezve';

  @override
  String get markComplete => 'Befejezettként megjelölés';

  @override
  String get actionItemDeleted => 'Teendő törölve';

  @override
  String get failedToDeleteActionItem => 'Teendő törlése sikertelen';

  @override
  String get deleteActionItemConfirmTitle => 'Teendő törlése';

  @override
  String get deleteActionItemConfirmMessage => 'Biztosan törölni szeretnéd ezt a teendőt?';

  @override
  String get appLanguage => 'Alkalmazás nyelve';

  @override
  String get appInterfaceSectionTitle => 'ALKALMAZÁS FELÜLET';

  @override
  String get speechTranscriptionSectionTitle => 'BESZÉD ÉS ÁTÍRÁS';

  @override
  String get languageSettingsHelperText =>
      'Az alkalmazás nyelve megváltoztatja a menüket és gombokat. A beszéd nyelve befolyásolja, hogyan íródnak át a felvételei.';
}
