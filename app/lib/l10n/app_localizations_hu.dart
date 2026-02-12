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
  String get noInternetConnection => 'Nincs internetkapcsolat';

  @override
  String get unableToDeleteConversation => 'Nem lehet törölni a beszélgetést';

  @override
  String get somethingWentWrong => 'Valami hiba történt! Kérlek, próbáld újra később.';

  @override
  String get copyErrorMessage => 'Hibaüzenet másolása';

  @override
  String get errorCopied => 'Hibaüzenet vágólapra másolva';

  @override
  String get remaining => 'Hátralevő';

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
  String get askOmi => 'Kérdezd meg Omit';

  @override
  String get done => 'Kész';

  @override
  String get disconnected => 'Megszakítva';

  @override
  String get searching => 'Keresés...';

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
  String get noConversationsYet => 'Még nincsenek beszélgetések';

  @override
  String get noStarredConversations => 'Nincsenek csillagozott beszélgetések';

  @override
  String get starConversationHint =>
      'Beszélgetés csillagozásához nyisd meg, és érintsd meg a csillag ikont a fejlécben.';

  @override
  String get searchConversations => 'Beszélgetések keresése...';

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
  String get messageCopied => '✨ Üzenet vágólapra másolva';

  @override
  String get cannotReportOwnMessage => 'Nem jelentheted be a saját üzeneteidet.';

  @override
  String get reportMessage => 'Üzenet jelentése';

  @override
  String get reportMessageConfirm => 'Biztosan be szeretnéd jelenteni ezt az üzenetet?';

  @override
  String get messageReported => 'Üzenet sikeresen bejelentve.';

  @override
  String get thankYouFeedback => 'Köszönjük a visszajelzést!';

  @override
  String get clearChat => 'Csevegés törlése';

  @override
  String get clearChatConfirm => 'Biztosan törölni szeretnéd a csevegést? Ez a művelet nem vonható vissza.';

  @override
  String get maxFilesLimit => 'Egyszerre csak 4 fájlt tölthetsz fel';

  @override
  String get chatWithOmi => 'Csevegés Omi-val';

  @override
  String get apps => 'Alkalmazások';

  @override
  String get noAppsFound => 'Nem található alkalmazás';

  @override
  String get tryAdjustingSearch => 'Próbáld módosítani a keresést vagy a szűrőket';

  @override
  String get createYourOwnApp => 'Hozd létre saját alkalmazásod';

  @override
  String get buildAndShareApp => 'Építsd meg és oszd meg egyedi alkalmazásodat';

  @override
  String get searchApps => 'Alkalmazások keresése...';

  @override
  String get myApps => 'Alkalmazásaim';

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
  String get visitWebsite => 'Weboldal megtekintése';

  @override
  String get helpOrInquiries => 'Segítség vagy kérdések?';

  @override
  String get joinCommunity => 'Csatlakozz a közösséghez!';

  @override
  String get membersAndCounting => '8000+ tag és számuk folyamatosan nő.';

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
  String get customVocabulary => 'Egyéni Szókincs';

  @override
  String get identifyingOthers => 'Mások Azonosítása';

  @override
  String get paymentMethods => 'Fizetési Módok';

  @override
  String get conversationDisplay => 'Beszélgetések Megjelenítése';

  @override
  String get dataPrivacy => 'Adatvédelem';

  @override
  String get userId => 'Felhasználói Azonosító';

  @override
  String get notSet => 'Nincs beállítva';

  @override
  String get userIdCopied => 'Felhasználói azonosító vágólapra másolva';

  @override
  String get systemDefault => 'Rendszer alapértelmezett';

  @override
  String get planAndUsage => 'Előfizetés és használat';

  @override
  String get offlineSync => 'Offline Sync';

  @override
  String get deviceSettings => 'Eszköz beállításai';

  @override
  String get integrations => 'Integrációk';

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
  String get wrapped2025 => '2025 összefoglaló';

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
  String get unpairDevice => 'Eszköz párosítás megszüntetése';

  @override
  String get unpairAndForget => 'Párosítás megszüntetése és elfelejtés';

  @override
  String get deviceDisconnectedMessage => 'Az Omi leválasztásra került 😔';

  @override
  String get deviceUnpairedMessage =>
      'Eszköz párosítása megszüntetve. Menjen a Beállítások > Bluetooth menüpontba, és felejtse el az eszközt a párosítás megszüntetésének befejezéséhez.';

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
  String get createKey => 'Kulcs Létrehozása';

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
  String get knowledgeGraphDeleted => 'Tudásgráf törölve';

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
  String get intervalSeconds => 'Intervallum (másodperc)';

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
  String get connect => 'Connect';

  @override
  String get comingSoon => 'Hamarosan';

  @override
  String get integrationsFooter =>
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
  String get editName => 'Edit Name';

  @override
  String get howShouldOmiCallYou => 'Hogyan szólítson az Omi?';

  @override
  String get enterYourName => 'Adja meg a nevét';

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
  String get noUpcomingMeetings => 'Nincs közelgő találkozó';

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
  String get noLanguagesFound => 'Nem található nyelv';

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
  String get yesterday => 'Tegnap';

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
  String deviceUsesCodec(String device, String reason) {
    return '$device $reason-t használ. Omi lesz használva.';
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
  String get resetToDefault => 'Visszaállítás alapértelmezettre';

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
  String get appName => 'App Name';

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
  String get dontShowAgain => 'Ne jelenjen meg újra';

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
  String get speechProfileIntro => 'Az Ominak meg kell tanulnia a céljait és a hangját. Később módosíthatja.';

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
  String get personalGrowthJourney => 'Személyes növekedési utazásod AI-val, amely minden szavadra figyel.';

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
  String get deleteActionItemTitle => 'Műveleti elem törlése';

  @override
  String get deleteActionItemMessage => 'Biztosan törölni szeretné ezt a műveleti elemet?';

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
  String get searchMemories => 'Emlékek keresése...';

  @override
  String get memoryDeleted => 'Emlék törölve.';

  @override
  String get undo => 'Visszavonás';

  @override
  String get noMemoriesYet => '🧠 Még nincsenek emlékek';

  @override
  String get noAutoMemories => 'Még nincsenek automatikusan kinyert emlékek';

  @override
  String get noManualMemories => 'Még nincsenek manuális emlékek';

  @override
  String get noMemoriesInCategories => 'Nincsenek emlékek ezekben a kategóriákban';

  @override
  String get noMemoriesFound => '🔍 Nem találhatók emlékek';

  @override
  String get addFirstMemory => 'Add hozzá az első emlékedet';

  @override
  String get clearMemoryTitle => 'Omi emlékének törlése';

  @override
  String get clearMemoryMessage => 'Biztosan törölni szeretnéd az Omi emlékét? Ez a művelet nem vonható vissza.';

  @override
  String get clearMemoryButton => 'Memória törlése';

  @override
  String get memoryClearedSuccess => 'Az Omi rólad szóló emléke törölve lett';

  @override
  String get noMemoriesToDelete => 'Nincs törlendő emlékezet';

  @override
  String get createMemoryTooltip => 'Új emlék létrehozása';

  @override
  String get createActionItemTooltip => 'Új teendő létrehozása';

  @override
  String get memoryManagement => 'Memória kezelés';

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
  String get deleteAllMemories => 'Minden emlékezet törlése';

  @override
  String get allMemoriesPrivateResult => 'Minden emlék most privát';

  @override
  String get allMemoriesPublicResult => 'Minden emlék most nyilvános';

  @override
  String get newMemory => '✨ Új emlékezet';

  @override
  String get editMemory => '✏️ Emlékezet szerkesztése';

  @override
  String get memoryContentHint => 'Szeretek fagyit enni...';

  @override
  String get failedToSaveMemory => 'Mentés sikertelen. Kérlek, ellenőrizd a kapcsolatot.';

  @override
  String get saveMemory => 'Emlék mentése';

  @override
  String get retry => 'Retry';

  @override
  String get createActionItem => 'Feladat létrehozása';

  @override
  String get editActionItem => 'Feladat szerkesztése';

  @override
  String get actionItemDescriptionHint => 'Mit kell elvégezni?';

  @override
  String get actionItemDescriptionEmpty => 'A teendő leírása nem lehet üres.';

  @override
  String get actionItemUpdated => 'Teendő frissítve';

  @override
  String get failedToUpdateActionItem => 'A feladat frissítése sikertelen';

  @override
  String get actionItemCreated => 'Teendő létrehozva';

  @override
  String get failedToCreateActionItem => 'A feladat létrehozása sikertelen';

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
  String get markComplete => 'Megjelölés befejezettként';

  @override
  String get actionItemDeleted => 'Műveleti elem törölve';

  @override
  String get failedToDeleteActionItem => 'A feladat törlése sikertelen';

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

  @override
  String get translationNotice => 'Fordítási értesítés';

  @override
  String get translationNoticeMessage =>
      'Az Omi az elsődleges nyelvedre fordítja a beszélgetéseket. Bármikor frissítheted a Beállítások → Profilok menüpontban.';

  @override
  String get pleaseCheckInternetConnection => 'Kérjük, ellenőrizd az internetkapcsolatot, és próbáld újra';

  @override
  String get pleaseSelectReason => 'Kérjük, válassz egy okot';

  @override
  String get tellUsMoreWhatWentWrong => 'Mondj el többet arról, mi ment rosszul...';

  @override
  String get selectText => 'Szöveg kijelölése';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Maximum $count cél engedélyezett';
  }

  @override
  String get conversationCannotBeMerged => 'Ez a beszélgetés nem egyesíthető (zárolva vagy már egyesítés alatt)';

  @override
  String get pleaseEnterFolderName => 'Kérjük, adj meg egy mappanevet';

  @override
  String get failedToCreateFolder => 'A mappa létrehozása sikertelen';

  @override
  String get failedToUpdateFolder => 'A mappa frissítése sikertelen';

  @override
  String get folderName => 'Mappa neve';

  @override
  String get descriptionOptional => 'Description (optional)';

  @override
  String get failedToDeleteFolder => 'A mappa törlése sikertelen';

  @override
  String get editFolder => 'Mappa szerkesztése';

  @override
  String get deleteFolder => 'Mappa törlése';

  @override
  String get transcriptCopiedToClipboard => 'Átirat vágólapra másolva';

  @override
  String get summaryCopiedToClipboard => 'Összefoglaló vágólapra másolva';

  @override
  String get conversationUrlCouldNotBeShared => 'A beszélgetés URL-je nem osztható meg.';

  @override
  String get urlCopiedToClipboard => 'URL vágólapra másolva';

  @override
  String get exportTranscript => 'Átirat exportálása';

  @override
  String get exportSummary => 'Összefoglaló exportálása';

  @override
  String get exportButton => 'Exportálás';

  @override
  String get actionItemsCopiedToClipboard => 'Műveletpontok vágólapra másolva';

  @override
  String get summarize => 'Összefoglalás';

  @override
  String get generateSummary => 'Összefoglaló generálása';

  @override
  String get conversationNotFoundOrDeleted => 'A beszélgetés nem található vagy törölve lett';

  @override
  String get deleteMemory => 'Emlékezet törlése';

  @override
  String get thisActionCannotBeUndone => 'Ez a művelet nem vonható vissza.';

  @override
  String memoriesCount(int count) {
    return '$count emlék';
  }

  @override
  String get noMemoriesInCategory => 'Ebben a kategóriában még nincsenek emlékek';

  @override
  String get addYourFirstMemory => 'Add hozzá az első emlékedet';

  @override
  String get firmwareDisconnectUsb => 'USB leválasztása';

  @override
  String get firmwareUsbWarning => 'Az USB-kapcsolat a frissítések során károsíthatja az eszközt.';

  @override
  String get firmwareBatteryAbove15 => 'Akkumulátor 15% felett';

  @override
  String get firmwareEnsureBattery => 'Győződjön meg róla, hogy az eszköz akkumulátora 15%.';

  @override
  String get firmwareStableConnection => 'Stabil kapcsolat';

  @override
  String get firmwareConnectWifi => 'Csatlakozzon WiFi-hez vagy mobilhálózathoz.';

  @override
  String failedToStartUpdate(String error) {
    return 'Nem sikerült elindítani a frissítést: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'Frissítés előtt győződjön meg:';

  @override
  String get confirmed => 'Megerősítve!';

  @override
  String get release => 'Elenged';

  @override
  String get slideToUpdate => 'Csúsztassa a frissítéshez';

  @override
  String copiedToClipboard(String title) {
    return '$title a vágólapra másolva';
  }

  @override
  String get batteryLevel => 'Akkumulátor szint';

  @override
  String get productUpdate => 'Termékfrissítés';

  @override
  String get offline => 'Offline';

  @override
  String get available => 'Elérhető';

  @override
  String get unpairDeviceDialogTitle => 'Eszköz párosítás megszüntetése';

  @override
  String get unpairDeviceDialogMessage =>
      'Ez megszünteti az eszköz párosítását, hogy egy másik telefonhoz csatlakozhasson. A Beállítások > Bluetooth menüpontba kell mennie, és el kell felejtenie az eszközt a folyamat befejezéséhez.';

  @override
  String get unpair => 'Párosítás megszüntetése';

  @override
  String get unpairAndForgetDevice => 'Párosítás megszüntetése és eszköz elfelejtése';

  @override
  String get unknownDevice => 'Unknown';

  @override
  String get unknown => 'Ismeretlen';

  @override
  String get productName => 'Termék neve';

  @override
  String get serialNumber => 'Sorozatszám';

  @override
  String get connected => 'Csatlakoztatva';

  @override
  String get privacyPolicyTitle => 'Adatvédelmi irányelvek';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label másolva';
  }

  @override
  String get noApiKeysYet => 'Még nincsenek API-kulcsok. Hozzon létre egyet az alkalmazásával való integrációhoz.';

  @override
  String get createKeyToGetStarted => 'Hozzon létre egy kulcsot a kezdéshez';

  @override
  String get persona => 'Persona';

  @override
  String get configureYourAiPersona => 'Konfigurálja AI személyiségét';

  @override
  String get configureSttProvider => 'STT szolgáltató konfigurálása';

  @override
  String get setWhenConversationsAutoEnd => 'Állítsa be, mikor fejeződjenek be automatikusan a beszélgetések';

  @override
  String get importDataFromOtherSources => 'Adatok importálása más forrásokból';

  @override
  String get debugAndDiagnostics => 'Hibakeresés és diagnosztika';

  @override
  String get autoDeletesAfter3Days => 'Automatikus törlés 3 nap után';

  @override
  String get helpsDiagnoseIssues => 'Segít a problémák diagnosztizálásában';

  @override
  String get exportStartedMessage => 'Exportálás elindult. Ez néhány másodpercig tarthat...';

  @override
  String get exportConversationsToJson => 'Beszélgetések exportálása JSON fájlba';

  @override
  String get knowledgeGraphDeletedSuccess => 'Tudásgráf sikeresen törölve';

  @override
  String failedToDeleteGraph(String error) {
    return 'Nem sikerült törölni a gráfot: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'Összes csomópont és kapcsolat törlése';

  @override
  String get addToClaudeDesktopConfig => 'Hozzáadás a claude_desktop_config.json fájlhoz';

  @override
  String get connectAiAssistantsToData => 'Csatlakoztassa AI asszisztenseit az adataihoz';

  @override
  String get useYourMcpApiKey => 'Használja MCP API kulcsát';

  @override
  String get realTimeTranscript => 'Valós idejű átirat';

  @override
  String get experimental => 'Kísérleti';

  @override
  String get transcriptionDiagnostics => 'Átírási diagnosztika';

  @override
  String get detailedDiagnosticMessages => 'Részletes diagnosztikai üzenetek';

  @override
  String get autoCreateSpeakers => 'Beszélők automatikus létrehozása';

  @override
  String get autoCreateWhenNameDetected => 'Automatikus létrehozás név észlelésekor';

  @override
  String get followUpQuestions => 'Követő kérdések';

  @override
  String get suggestQuestionsAfterConversations => 'Kérdések javaslása beszélgetések után';

  @override
  String get goalTracker => 'Célkövetés';

  @override
  String get trackPersonalGoalsOnHomepage => 'Kövesse személyes céljait a kezdőlapon';

  @override
  String get dailyReflection => 'Napi reflexió';

  @override
  String get get9PmReminderToReflect => 'Kapjon emlékeztetőt este 9-kor, hogy elgondolkodjon a napján';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'A műveleti elem leírása nem lehet üres';

  @override
  String get saved => 'Mentve';

  @override
  String get overdue => 'Lejárt határidejű';

  @override
  String get failedToUpdateDueDate => 'Nem sikerült frissíteni a határidőt';

  @override
  String get markIncomplete => 'Megjelölés befejezetlen ként';

  @override
  String get editDueDate => 'Határidő szerkesztése';

  @override
  String get setDueDate => 'Határidő beállítása';

  @override
  String get clearDueDate => 'Határidő törlése';

  @override
  String get failedToClearDueDate => 'Nem sikerült törölni a határidőt';

  @override
  String get mondayAbbr => 'H';

  @override
  String get tuesdayAbbr => 'K';

  @override
  String get wednesdayAbbr => 'Sze';

  @override
  String get thursdayAbbr => 'Cs';

  @override
  String get fridayAbbr => 'P';

  @override
  String get saturdayAbbr => 'Szo';

  @override
  String get sundayAbbr => 'V';

  @override
  String get howDoesItWork => 'Hogyan működik?';

  @override
  String get sdCardSyncDescription =>
      'Az SD kártya szinkronizálás importálja az emlékeidet az SD kártyáról az alkalmazásba';

  @override
  String get checksForAudioFiles => 'Ellenőrzi a hangfájlokat az SD kártyán';

  @override
  String get omiSyncsAudioFiles => 'Az Omi ezután szinkronizálja a hangfájlokat a szerverrel';

  @override
  String get serverProcessesAudio => 'A szerver feldolgozza a hangfájlokat és emlékeket hoz létre';

  @override
  String get youreAllSet => 'Készen állsz!';

  @override
  String get welcomeToOmiDescription =>
      'Üdvözöljük az Omi-ban! Az AI társad készen áll, hogy segítsen a beszélgetésekben, feladatokban és még sok másban.';

  @override
  String get startUsingOmi => 'Omi használatának megkezdése';

  @override
  String get back => 'Vissza';

  @override
  String get keyboardShortcuts => 'Billentyűparancsok';

  @override
  String get toggleControlBar => 'Vezérlősáv váltása';

  @override
  String get pressKeys => 'Nyomja meg a billentyűket...';

  @override
  String get cmdRequired => '⌘ szükséges';

  @override
  String get invalidKey => 'Érvénytelen billentyű';

  @override
  String get space => 'Szóköz';

  @override
  String get search => 'Keresés';

  @override
  String get searchPlaceholder => 'Keresés...';

  @override
  String get untitledConversation => 'Névtelen beszélgetés';

  @override
  String countRemaining(String count) {
    return '$count hátra';
  }

  @override
  String get addGoal => 'Cél hozzáadása';

  @override
  String get editGoal => 'Cél szerkesztése';

  @override
  String get icon => 'Ikon';

  @override
  String get goalTitle => 'Cél címe';

  @override
  String get current => 'Jelenlegi';

  @override
  String get target => 'Cél';

  @override
  String get saveGoal => 'Mentés';

  @override
  String get goals => 'Célok';

  @override
  String get tapToAddGoal => 'Koppints cél hozzáadásához';

  @override
  String welcomeBack(String name) {
    return 'Üdvözöljük vissza, $name';
  }

  @override
  String get yourConversations => 'A beszélgetéseid';

  @override
  String get reviewAndManageConversations => 'Tekintse át és kezelje rögzített beszélgetéseit';

  @override
  String get startCapturingConversations =>
      'Kezdje el rögzíteni a beszélgetéseket Omi eszközével, hogy itt láthassa őket.';

  @override
  String get useMobileAppToCapture => 'Használja mobilalkalmazását hang rögzítéséhez';

  @override
  String get conversationsProcessedAutomatically => 'A beszélgetések automatikusan feldolgozásra kerülnek';

  @override
  String get getInsightsInstantly => 'Szerezzen betekintéseket és összefoglalókat azonnal';

  @override
  String get showAll => 'Összes megjelenítése →';

  @override
  String get noTasksForToday => 'Nincs feladat mára.\\nKérdezzen Omit több feladatért, vagy hozzon létre manuálisan.';

  @override
  String get dailyScore => 'NAPI PONTSZÁM';

  @override
  String get dailyScoreDescription => 'Egy pontszám, amely segít jobban\na végrehajtásra összpontosítani.';

  @override
  String get searchResults => 'Keresési eredmények';

  @override
  String get actionItems => 'Teendők';

  @override
  String get tasksToday => 'Ma';

  @override
  String get tasksTomorrow => 'Holnap';

  @override
  String get tasksNoDeadline => 'Nincs határidő';

  @override
  String get tasksLater => 'Később';

  @override
  String get loadingTasks => 'Feladatok betöltése...';

  @override
  String get tasks => 'Feladatok';

  @override
  String get swipeTasksToIndent => 'Húzza el a feladatokat a behúzáshoz, húzza a kategóriák között';

  @override
  String get create => 'Létrehozás';

  @override
  String get noTasksYet => 'Még nincsenek feladatok';

  @override
  String get tasksFromConversationsWillAppear =>
      'A beszélgetésekből származó feladatok itt jelennek meg.\nKattintson a Létrehozás gombra egy manuális hozzáadásához.';

  @override
  String get monthJan => 'Jan';

  @override
  String get monthFeb => 'Feb';

  @override
  String get monthMar => 'Már';

  @override
  String get monthApr => 'Ápr';

  @override
  String get monthMay => 'Máj';

  @override
  String get monthJun => 'Jún';

  @override
  String get monthJul => 'Júl';

  @override
  String get monthAug => 'Aug';

  @override
  String get monthSep => 'Szep';

  @override
  String get monthOct => 'Okt';

  @override
  String get monthNov => 'Nov';

  @override
  String get monthDec => 'Dec';

  @override
  String get timePM => 'DU';

  @override
  String get timeAM => 'DE';

  @override
  String get actionItemUpdatedSuccessfully => 'Feladat sikeresen frissítve';

  @override
  String get actionItemCreatedSuccessfully => 'Feladat sikeresen létrehozva';

  @override
  String get actionItemDeletedSuccessfully => 'Feladat sikeresen törölve';

  @override
  String get deleteActionItem => 'Feladat törlése';

  @override
  String get deleteActionItemConfirmation =>
      'Biztosan törölni szeretné ezt a feladatot? Ez a művelet nem vonható vissza.';

  @override
  String get enterActionItemDescription => 'Adja meg a feladat leírását...';

  @override
  String get markAsCompleted => 'Megjelölés befejezettként';

  @override
  String get setDueDateAndTime => 'Határidő és időpont beállítása';

  @override
  String get reloadingApps => 'Alkalmazások újratöltése...';

  @override
  String get loadingApps => 'Alkalmazások betöltése...';

  @override
  String get browseInstallCreateApps => 'Böngésszen, telepítsen és hozzon létre alkalmazásokat';

  @override
  String get all => 'All';

  @override
  String get open => 'Megnyitás';

  @override
  String get install => 'Telepítés';

  @override
  String get noAppsAvailable => 'Nincsenek elérhető alkalmazások';

  @override
  String get unableToLoadApps => 'Nem sikerült betölteni az alkalmazásokat';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'Próbálja meg módosítani a keresési kifejezéseket vagy szűrőket';

  @override
  String get checkBackLaterForNewApps => 'Nézzen vissza később új alkalmazásokért';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'Kérjük, ellenőrizze az internetkapcsolatát és próbálja újra';

  @override
  String get createNewApp => 'Új alkalmazás létrehozása';

  @override
  String get buildSubmitCustomOmiApp => 'Készítsd el és nyújtsd be egyedi Omi alkalmazásodat';

  @override
  String get submittingYourApp => 'Alkalmazásod beküldése...';

  @override
  String get preparingFormForYou => 'Az űrlap előkészítése számodra...';

  @override
  String get appDetails => 'Alkalmazás részletei';

  @override
  String get paymentDetails => 'Fizetési részletek';

  @override
  String get previewAndScreenshots => 'Előnézet és képernyőképek';

  @override
  String get appCapabilities => 'Alkalmazás képességei';

  @override
  String get aiPrompts => 'MI utasítások';

  @override
  String get chatPrompt => 'Chat utasítás';

  @override
  String get chatPromptPlaceholder =>
      'Egy fantasztikus alkalmazás vagy, a feladatod, hogy válaszolj a felhasználói kérdésekre és jól éreztess velük...';

  @override
  String get conversationPrompt => 'Beszélgetési felszólítás';

  @override
  String get conversationPromptPlaceholder =>
      'Egy fantasztikus alkalmazás vagy, kapsz egy beszélgetés átírását és összefoglalóját...';

  @override
  String get notificationScopes => 'Értesítési körök';

  @override
  String get appPrivacyAndTerms => 'Alkalmazás adatvédelem és feltételek';

  @override
  String get makeMyAppPublic => 'Tedd nyilvánossá az alkalmazásomat';

  @override
  String get submitAppTermsAgreement =>
      'Az alkalmazás beküldésével elfogadom az Omi AI Szolgáltatási Feltételeit és Adatvédelmi Irányelveit';

  @override
  String get submitApp => 'Alkalmazás beküldése';

  @override
  String get needHelpGettingStarted => 'Segítségre van szükséged az induláshoz?';

  @override
  String get clickHereForAppBuildingGuides => 'Kattints ide az alkalmazáskészítési útmutatókért és dokumentációért';

  @override
  String get submitAppQuestion => 'Alkalmazás beküldése?';

  @override
  String get submitAppPublicDescription =>
      'Alkalmazásod felülvizsgálásra kerül és nyilvánossá válik. Azonnal elkezdheted használni, még a felülvizsgálat alatt is!';

  @override
  String get submitAppPrivateDescription =>
      'Alkalmazásod felülvizsgálásra kerül és privát módon elérhetővé válik számodra. Azonnal elkezdheted használni, még a felülvizsgálat alatt is!';

  @override
  String get startEarning => 'Kezdj el keresni! 💰';

  @override
  String get connectStripeOrPayPal =>
      'Csatlakoztasd a Stripe-ot vagy PayPalt, hogy fizetéseket fogadhass az alkalmazásodért.';

  @override
  String get connectNow => 'Csatlakoztatás most';

  @override
  String get installsCount => 'Telepítések';

  @override
  String get uninstallApp => 'Alkalmazás eltávolítása';

  @override
  String get subscribe => 'Feliratkozás';

  @override
  String get dataAccessNotice => 'Adathozzáférési értesítés';

  @override
  String get dataAccessWarning =>
      'Ez az alkalmazás hozzáfér az adataihoz. Az Omi AI nem felelős azért, hogy ez az alkalmazás hogyan használja, módosítja vagy törli az adatait';

  @override
  String get installApp => 'Alkalmazás telepítése';

  @override
  String get betaTesterNotice =>
      'Ön ennek az alkalmazásnak a béta tesztelője. Még nem nyilvános. Jóváhagyás után nyilvános lesz.';

  @override
  String get appUnderReviewOwner =>
      'Az alkalmazása felülvizsgálat alatt áll, és csak Ön számára látható. Jóváhagyás után nyilvános lesz.';

  @override
  String get appRejectedNotice =>
      'Az alkalmazását elutasították. Kérjük, frissítse az alkalmazás adatait, és küldje be újra felülvizsgálatra.';

  @override
  String get setupSteps => 'Beállítási lépések';

  @override
  String get setupInstructions => 'Beállítási útmutató';

  @override
  String get integrationInstructions => 'Integrációs utasítások';

  @override
  String get preview => 'Előnézet';

  @override
  String get aboutTheApp => 'Az alkalmazásról';

  @override
  String get aboutThePersona => 'A personáról';

  @override
  String get chatPersonality => 'Chat személyiség';

  @override
  String get ratingsAndReviews => 'Értékelések és vélemények';

  @override
  String get noRatings => 'nincs értékelés';

  @override
  String ratingsCount(String count) {
    return '$count+ értékelés';
  }

  @override
  String get errorActivatingApp => 'Hiba az alkalmazás aktiválása során';

  @override
  String get integrationSetupRequired =>
      'Ha ez egy integrációs alkalmazás, győződjön meg róla, hogy a beállítás befejeződött.';

  @override
  String get installed => 'Telepítve';

  @override
  String get appIdLabel => 'Alkalmazás azonosító';

  @override
  String get appNameLabel => 'Alkalmazás neve';

  @override
  String get appNamePlaceholder => 'Nagyszerű alkalmazásom';

  @override
  String get pleaseEnterAppName => 'Kérjük, adja meg az alkalmazás nevét';

  @override
  String get categoryLabel => 'Kategória';

  @override
  String get selectCategory => 'Kategória kiválasztása';

  @override
  String get descriptionLabel => 'Leírás';

  @override
  String get appDescriptionPlaceholder =>
      'Nagyszerű alkalmazásom egy remek alkalmazás, amely csodálatos dolgokat tesz. Ez a legjobb alkalmazás!';

  @override
  String get pleaseProvideValidDescription => 'Kérjük, adjon meg érvényes leírást';

  @override
  String get appPricingLabel => 'Alkalmazás árazása';

  @override
  String get noneSelected => 'Nincs kiválasztva';

  @override
  String get appIdCopiedToClipboard => 'Alkalmazás azonosító vágólapra másolva';

  @override
  String get appCategoryModalTitle => 'Alkalmazás kategória';

  @override
  String get pricingFree => 'Ingyenes';

  @override
  String get pricingPaid => 'Fizetős';

  @override
  String get loadingCapabilities => 'Képességek betöltése...';

  @override
  String get filterInstalled => 'Telepítve';

  @override
  String get filterMyApps => 'Saját alkalmazásaim';

  @override
  String get clearSelection => 'Kijelölés törlése';

  @override
  String get filterCategory => 'Kategória';

  @override
  String get rating4PlusStars => '4+ csillag';

  @override
  String get rating3PlusStars => '3+ csillag';

  @override
  String get rating2PlusStars => '2+ csillag';

  @override
  String get rating1PlusStars => '1+ csillag';

  @override
  String get filterRating => 'Értékelés';

  @override
  String get filterCapabilities => 'Képességek';

  @override
  String get noNotificationScopesAvailable => 'Nincsenek elérhető értesítési hatókörök';

  @override
  String get popularApps => 'Népszerű alkalmazások';

  @override
  String get pleaseProvidePrompt => 'Kérjük, adjon meg egy promptot';

  @override
  String chatWithAppName(String appName) {
    return 'Chat $appName alkalmazással';
  }

  @override
  String get defaultAiAssistant => 'Alapértelmezett AI asszisztens';

  @override
  String get readyToChat => '✨ Készen áll a csevegésre!';

  @override
  String get connectionNeeded => '🌐 Kapcsolat szükséges';

  @override
  String get startConversation => 'Kezdjen el beszélgetni, és hagyja, hogy a varázslat kezdetét vegye';

  @override
  String get checkInternetConnection => 'Kérjük, ellenőrizze az internetkapcsolatot';

  @override
  String get wasThisHelpful => 'Hasznos volt ez?';

  @override
  String get thankYouForFeedback => 'Köszönjük a visszajelzést!';

  @override
  String get maxFilesUploadError => 'Egyszerre csak 4 fájlt tölthet fel';

  @override
  String get attachedFiles => '📎 Csatolt fájlok';

  @override
  String get takePhoto => 'Fénykép készítése';

  @override
  String get captureWithCamera => 'Felvétel kamerával';

  @override
  String get selectImages => 'Képek kiválasztása';

  @override
  String get chooseFromGallery => 'Válasszon a galériából';

  @override
  String get selectFile => 'Fájl kiválasztása';

  @override
  String get chooseAnyFileType => 'Bármilyen fájltípus választása';

  @override
  String get cannotReportOwnMessages => 'Nem jelentheti saját üzeneteit';

  @override
  String get messageReportedSuccessfully => '✅ Üzenet sikeresen jelentve';

  @override
  String get confirmReportMessage => 'Biztosan jelenteni szeretné ezt az üzenetet?';

  @override
  String get selectChatAssistant => 'Chat asszisztens kiválasztása';

  @override
  String get enableMoreApps => 'További alkalmazások engedélyezése';

  @override
  String get chatCleared => 'Chat törölve';

  @override
  String get clearChatTitle => 'Chat törlése?';

  @override
  String get confirmClearChat => 'Biztosan törölni szeretné a chatet? Ez a művelet nem vonható vissza.';

  @override
  String get copy => 'Másolás';

  @override
  String get share => 'Megosztás';

  @override
  String get report => 'Jelentés';

  @override
  String get microphonePermissionRequired => 'Mikrofon engedély szükséges a hangfelvételhez.';

  @override
  String get microphonePermissionDenied =>
      'Mikrofon engedély megtagadva. Kérjük, adjon engedélyt a Rendszerbeállítások > Adatvédelem és biztonság > Mikrofon alatt.';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'Nem sikerült ellenőrizni a mikrofon engedélyt: $error';
  }

  @override
  String get failedToTranscribeAudio => 'Nem sikerült átírni a hangot';

  @override
  String get transcribing => 'Átírás...';

  @override
  String get transcriptionFailed => 'Átírás sikertelen';

  @override
  String get discardedConversation => 'Elvetett beszélgetés';

  @override
  String get at => 'ekkor:';

  @override
  String get from => 'ettől:';

  @override
  String get copied => 'Másolva!';

  @override
  String get copyLink => 'Link másolása';

  @override
  String get hideTranscript => 'Átirat elrejtése';

  @override
  String get viewTranscript => 'Átirat megtekintése';

  @override
  String get conversationDetails => 'Beszélgetés részletei';

  @override
  String get transcript => 'Átirat';

  @override
  String segmentsCount(int count) {
    return '$count szegmens';
  }

  @override
  String get noTranscriptAvailable => 'Nincs elérhető átirat';

  @override
  String get noTranscriptMessage => 'Ehhez a beszélgetéshez nincs átirat.';

  @override
  String get conversationUrlCouldNotBeGenerated => 'A beszélgetés URL-je nem generálható.';

  @override
  String get failedToGenerateConversationLink => 'Beszélgetés link generálása sikertelen';

  @override
  String get failedToGenerateShareLink => 'Megosztási link generálása sikertelen';

  @override
  String get reloadingConversations => 'Beszélgetések újratöltése...';

  @override
  String get user => 'Felhasználó';

  @override
  String get starred => 'Csillagozott';

  @override
  String get date => 'Dátum';

  @override
  String get noResultsFound => 'Nem található eredmény';

  @override
  String get tryAdjustingSearchTerms => 'Próbálja meg módosítani a keresési kifejezéseket';

  @override
  String get starConversationsToFindQuickly => 'Csillagozza meg a beszélgetéseket, hogy gyorsan megtalálja őket itt';

  @override
  String noConversationsOnDate(String date) {
    return 'Nincsenek beszélgetések $date-kor';
  }

  @override
  String get trySelectingDifferentDate => 'Próbáljon meg egy másik dátumot kiválasztani';

  @override
  String get conversations => 'Beszélgetések';

  @override
  String get chat => 'Csevegés';

  @override
  String get actions => 'Műveletek';

  @override
  String get syncAvailable => 'Szinkronizálás elérhető';

  @override
  String get referAFriend => 'Ajánljon egy barátnak';

  @override
  String get help => 'Súgó';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'Frissítés Pro-ra';

  @override
  String get getOmiDevice => 'Omi eszköz beszerzése';

  @override
  String get wearableAiCompanion => 'Hordható AI társ';

  @override
  String get loadingMemories => 'Emlékek betöltése...';

  @override
  String get allMemories => 'Összes emlék';

  @override
  String get aboutYou => 'Rólad';

  @override
  String get manual => 'Kézi';

  @override
  String get loadingYourMemories => 'Emlékeid betöltése...';

  @override
  String get createYourFirstMemory => 'Hozd létre az első emlékedet a kezdéshez';

  @override
  String get tryAdjustingFilter => 'Próbáld meg módosítani a keresést vagy a szűrőt';

  @override
  String get whatWouldYouLikeToRemember => 'Mire szeretnél emlékezni?';

  @override
  String get category => 'Kategória';

  @override
  String get public => 'Nyilvános';

  @override
  String get failedToSaveCheckConnection => 'Sikertelen mentés. Ellenőrizd a kapcsolatot.';

  @override
  String get createMemory => 'Emlékezet létrehozása';

  @override
  String get deleteMemoryConfirmation =>
      'Biztosan törölni szeretnéd ezt az emlékezetet? Ez a művelet nem vonható vissza.';

  @override
  String get makePrivate => 'Priváttá tétel';

  @override
  String get organizeAndControlMemories => 'Szervezd és irányítsd az emlékezetedet';

  @override
  String get total => 'Összesen';

  @override
  String get makeAllMemoriesPrivate => 'Minden emlékezet priváttá tétele';

  @override
  String get setAllMemoriesToPrivate => 'Minden emlékezet beállítása privát láthatóságra';

  @override
  String get makeAllMemoriesPublic => 'Minden emlékezet nyilvánossá tétele';

  @override
  String get setAllMemoriesToPublic => 'Minden emlékezet beállítása nyilvános láthatóságra';

  @override
  String get permanentlyRemoveAllMemories => 'Minden emlékezet végleges eltávolítása az Omiból';

  @override
  String get allMemoriesAreNowPrivate => 'Minden emlékezet most privát';

  @override
  String get allMemoriesAreNowPublic => 'Minden emlékezet most nyilvános';

  @override
  String get clearOmisMemory => 'Omi memóriájának törlése';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Biztosan törölni szeretnéd az Omi memóriáját? Ez a művelet nem vonható vissza és véglegesen törli mind a(z) $count emlékezetet.';
  }

  @override
  String get omisMemoryCleared => 'Az Omi rólad szóló memóriája törölve lett';

  @override
  String get welcomeToOmi => 'Üdvözöljük az Omiban';

  @override
  String get continueWithApple => 'Folytatás Apple-lel';

  @override
  String get continueWithGoogle => 'Folytatás Google-lel';

  @override
  String get byContinuingYouAgree => 'A folytatással elfogadod ';

  @override
  String get termsOfService => 'Szolgáltatási feltételeinket';

  @override
  String get and => ' és ';

  @override
  String get dataAndPrivacy => 'Adatok és adatvédelem';

  @override
  String get secureAuthViaAppleId => 'Biztonságos hitelesítés Apple ID-n keresztül';

  @override
  String get secureAuthViaGoogleAccount => 'Biztonságos hitelesítés Google fiókon keresztül';

  @override
  String get whatWeCollect => 'Mit gyűjtünk';

  @override
  String get dataCollectionMessage =>
      'A folytatással beszélgetéseid, felvételeid és személyes adataid biztonságosan tárolódnak szervereiken, hogy AI-alapú betekintéseket nyújtsunk és engedélyezzük az összes app funkciót.';

  @override
  String get dataProtection => 'Adatvédelem';

  @override
  String get yourDataIsProtected => 'Adataid védettek és ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'Kérjük, válassza ki az elsődleges nyelvét';

  @override
  String get chooseYourLanguage => 'Válassza ki a nyelvét';

  @override
  String get selectPreferredLanguageForBestExperience => 'Válassza ki a preferált nyelvét a legjobb Omi élményért';

  @override
  String get searchLanguages => 'Nyelvek keresése...';

  @override
  String get selectALanguage => 'Válasszon egy nyelvet';

  @override
  String get tryDifferentSearchTerm => 'Próbáljon ki egy másik keresési kifejezést';

  @override
  String get pleaseEnterYourName => 'Kérjük, adja meg a nevét';

  @override
  String get nameMustBeAtLeast2Characters => 'A névnek legalább 2 karakterből kell állnia';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'Mondja el nekünk, hogyan szeretné, ha megszólítanánk. Ez segít személyre szabni az Omi élményt.';

  @override
  String charactersCount(int count) {
    return '$count karakter';
  }

  @override
  String get enableFeaturesForBestExperience => 'Engedélyezze a funkciókat a legjobb Omi élményért az eszközén.';

  @override
  String get microphoneAccess => 'Mikrofon hozzáférés';

  @override
  String get recordAudioConversations => 'Hangbeszélgetések rögzítése';

  @override
  String get microphoneAccessDescription =>
      'Az Omi-nak mikrofon hozzáférésre van szüksége a beszélgetések rögzítéséhez és átirat készítéséhez.';

  @override
  String get screenRecording => 'Képernyőrögzítés';

  @override
  String get captureSystemAudioFromMeetings => 'Rendszerhang rögzítése találkozókból';

  @override
  String get screenRecordingDescription =>
      'Az Omi-nak képernyőrögzítési engedélyre van szüksége a rendszerhang rögzítéséhez a böngésző alapú találkozókból.';

  @override
  String get accessibility => 'Akadálymentesség';

  @override
  String get detectBrowserBasedMeetings => 'Böngésző alapú találkozók észlelése';

  @override
  String get accessibilityDescription =>
      'Az Omi-nak akadálymentesítési engedélyre van szüksége annak észleléséhez, amikor csatlakozik Zoom, Meet vagy Teams találkozókhoz a böngészőjében.';

  @override
  String get pleaseWait => 'Kérem várjon...';

  @override
  String get joinTheCommunity => 'Csatlakozz a közösséghez!';

  @override
  String get loadingProfile => 'Profil betöltése...';

  @override
  String get profileSettings => 'Profil beállításai';

  @override
  String get noEmailSet => 'Nincs beállított e-mail';

  @override
  String get userIdCopiedToClipboard => 'Felhasználói azonosító másolva';

  @override
  String get yourInformation => 'Az Ön Adatai';

  @override
  String get setYourName => 'Név beállítása';

  @override
  String get changeYourName => 'Név módosítása';

  @override
  String get manageYourOmiPersona => 'Az Omi persona kezelése';

  @override
  String get voiceAndPeople => 'Hang és Emberek';

  @override
  String get teachOmiYourVoice => 'Tanítsa meg az Omi-nak a hangját';

  @override
  String get tellOmiWhoSaidIt => 'Mondja meg az Omi-nak, ki mondta 🗣️';

  @override
  String get payment => 'Fizetés';

  @override
  String get addOrChangeYourPaymentMethod => 'Fizetési mód hozzáadása vagy módosítása';

  @override
  String get preferences => 'Beállítások';

  @override
  String get helpImproveOmiBySharing => 'Segítsen az Omi fejlesztésében anonim elemzési adatok megosztásával';

  @override
  String get deleteAccount => 'Fiók Törlése';

  @override
  String get deleteYourAccountAndAllData => 'Fiók és minden adat törlése';

  @override
  String get clearLogs => 'Naplók törlése';

  @override
  String get debugLogsCleared => 'Hibakeresési naplók törölve';

  @override
  String get exportConversations => 'Beszélgetések exportálása';

  @override
  String get exportAllConversationsToJson => 'Exportálja az összes beszélgetését JSON fájlba.';

  @override
  String get conversationsExportStarted =>
      'Beszélgetések exportálása elindult. Ez eltarthat néhány másodpercig, kérem várjon.';

  @override
  String get mcpDescription =>
      'Az Omi más alkalmazásokhoz való csatlakoztatásához, hogy olvassa, keresse és kezelje az emlékeit és beszélgetéseit. Hozzon létre egy kulcsot az induláshoz.';

  @override
  String get apiKeys => 'API kulcsok';

  @override
  String errorLabel(String error) {
    return 'Hiba: $error';
  }

  @override
  String get noApiKeysFound => 'Nem találhatók API kulcsok. Hozzon létre egyet az induláshoz.';

  @override
  String get advancedSettings => 'Speciális beállítások';

  @override
  String get triggersWhenNewConversationCreated => 'Aktiválódik, amikor új beszélgetés jön létre.';

  @override
  String get triggersWhenNewTranscriptReceived => 'Aktiválódik, amikor új átirat érkezik.';

  @override
  String get realtimeAudioBytes => 'Valós idejű audio bájtok';

  @override
  String get triggersWhenAudioBytesReceived => 'Aktiválódik, amikor audio bájtok érkeznek.';

  @override
  String get everyXSeconds => 'Minden x másodperc';

  @override
  String get triggersWhenDaySummaryGenerated => 'Aktiválódik, amikor a napi összefoglaló generálódik.';

  @override
  String get tryLatestExperimentalFeatures => 'Próbálja ki az Omi csapat legújabb kísérleti funkcióit.';

  @override
  String get transcriptionServiceDiagnosticStatus => 'Átírási szolgáltatás diagnosztikai állapota';

  @override
  String get enableDetailedDiagnosticMessages =>
      'Részletes diagnosztikai üzenetek engedélyezése az átírási szolgáltatástól';

  @override
  String get autoCreateAndTagNewSpeakers => 'Új beszélők automatikus létrehozása és címkézése';

  @override
  String get automaticallyCreateNewPerson => 'Új személy automatikus létrehozása, amikor nevet észlel az átiratban.';

  @override
  String get pilotFeatures => 'Pilot funkciók';

  @override
  String get pilotFeaturesDescription => 'Ezek a funkciók tesztek, és nem garantált a támogatás.';

  @override
  String get suggestFollowUpQuestion => 'Utánkövetési kérdés javaslása';

  @override
  String get saveSettings => 'Beállítások Mentése';

  @override
  String get syncingDeveloperSettings => 'Fejlesztői beállítások szinkronizálása...';

  @override
  String get summary => 'Összefoglaló';

  @override
  String get auto => 'Automatikus';

  @override
  String get noSummaryForApp =>
      'Nincs elérhető összefoglaló ehhez az alkalmazáshoz. Próbálj ki egy másik alkalmazást a jobb eredmények érdekében.';

  @override
  String get tryAnotherApp => 'Próbáljon ki egy másik alkalmazást';

  @override
  String generatedBy(String appName) {
    return 'Létrehozta: $appName';
  }

  @override
  String get overview => 'Áttekintés';

  @override
  String get otherAppResults => 'Más alkalmazások eredményei';

  @override
  String get unknownApp => 'Ismeretlen alkalmazás';

  @override
  String get noSummaryAvailable => 'Nincs elérhető összefoglaló';

  @override
  String get conversationNoSummaryYet => 'Ennek a beszélgetésnek még nincs összefoglalója.';

  @override
  String get chooseSummarizationApp => 'Összefoglaló alkalmazás kiválasztása';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName beállítva alapértelmezett összefoglaló alkalmazásként';
  }

  @override
  String get letOmiChooseAutomatically => 'Hagyja, hogy az Omi automatikusan válassza ki a legjobb alkalmazást';

  @override
  String get deleteConversationConfirmation => 'Biztosan törli ezt a beszélgetést? Ez a művelet nem vonható vissza.';

  @override
  String get conversationDeleted => 'Beszélgetés törölve';

  @override
  String get generatingLink => 'Link generálása...';

  @override
  String get editConversation => 'Beszélgetés szerkesztése';

  @override
  String get conversationLinkCopiedToClipboard => 'Beszélgetés link vágólapra másolva';

  @override
  String get conversationTranscriptCopiedToClipboard => 'Beszélgetés átírása vágólapra másolva';

  @override
  String get editConversationDialogTitle => 'Beszélgetés szerkesztése';

  @override
  String get changeTheConversationTitle => 'Beszélgetés címének módosítása';

  @override
  String get conversationTitle => 'Beszélgetés címe';

  @override
  String get enterConversationTitle => 'Adja meg a beszélgetés címét...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'Beszélgetés címe sikeresen frissítve';

  @override
  String get failedToUpdateConversationTitle => 'Beszélgetés címének frissítése sikertelen';

  @override
  String get errorUpdatingConversationTitle => 'Hiba a beszélgetés címének frissítése során';

  @override
  String get settingUp => 'Beállítás...';

  @override
  String get startYourFirstRecording => 'Indítsa el első felvételét';

  @override
  String get preparingSystemAudioCapture => 'Rendszer hangfelvétel előkészítése';

  @override
  String get clickTheButtonToCaptureAudio =>
      'Kattintson a gombra hangfelvétel készítéséhez élő átiratok, AI betekintések és automatikus mentés céljából.';

  @override
  String get reconnecting => 'Újracsatlakozás...';

  @override
  String get recordingPaused => 'Felvétel szüneteltetve';

  @override
  String get recordingActive => 'Felvétel aktív';

  @override
  String get startRecording => 'Felvétel indítása';

  @override
  String resumingInCountdown(String countdown) {
    return 'Folytatás ${countdown}mp múlva...';
  }

  @override
  String get tapPlayToResume => 'Koppintson a lejátszásra a folytatáshoz';

  @override
  String get listeningForAudio => 'Hang figyelése...';

  @override
  String get preparingAudioCapture => 'Hangfelvétel előkészítése';

  @override
  String get clickToBeginRecording => 'Kattintson a felvétel indításához';

  @override
  String get translated => 'lefordítva';

  @override
  String get liveTranscript => 'Élő átirat';

  @override
  String segmentsSingular(String count) {
    return '$count szegmens';
  }

  @override
  String segmentsPlural(String count) {
    return '$count szegmens';
  }

  @override
  String get startRecordingToSeeTranscript => 'Indítsa el a felvételt az élő átirat megtekintéséhez';

  @override
  String get paused => 'Szüneteltetve';

  @override
  String get initializing => 'Inicializálás...';

  @override
  String get recording => 'Felvétel';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'Mikrofon megváltoztatva. Folytatás ${countdown}mp múlva';
  }

  @override
  String get clickPlayToResumeOrStop => 'Kattintson a lejátszásra a folytatáshoz vagy a megállításra a befejezéshez';

  @override
  String get settingUpSystemAudioCapture => 'Rendszer hangfelvétel beállítása';

  @override
  String get capturingAudioAndGeneratingTranscript => 'Hangfelvétel és átirat generálása';

  @override
  String get clickToBeginRecordingSystemAudio => 'Kattintson a rendszer hangfelvétel indításához';

  @override
  String get you => 'Ön';

  @override
  String speakerWithId(String speakerId) {
    return 'Beszélő $speakerId';
  }

  @override
  String get translatedByOmi => 'fordította az omi';

  @override
  String get backToConversations => 'Vissza a beszélgetésekhez';

  @override
  String get systemAudio => 'Rendszer';

  @override
  String get mic => 'Mikrofon';

  @override
  String audioInputSetTo(String deviceName) {
    return 'Hangbemenet beállítva: $deviceName';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'Hiba a hangeszköz váltásakor: $error';
  }

  @override
  String get selectAudioInput => 'Válasszon hangbemenetet';

  @override
  String get loadingDevices => 'Eszközök betöltése...';

  @override
  String get settingsHeader => 'BEÁLLÍTÁSOK';

  @override
  String get plansAndBilling => 'Csomagok és Számlázás';

  @override
  String get calendarIntegration => 'Naptár Integráció';

  @override
  String get dailySummary => 'Napi összefoglaló';

  @override
  String get developer => 'Fejlesztő';

  @override
  String get about => 'Névjegy';

  @override
  String get selectTime => 'Időpont választása';

  @override
  String get accountGroup => 'Fiók';

  @override
  String get signOutQuestion => 'Kijelentkezik?';

  @override
  String get signOutConfirmation => 'Biztosan ki szeretnél jelentkezni?';

  @override
  String get customVocabularyHeader => 'EGYÉNI SZÓKINCS';

  @override
  String get addWordsDescription => 'Adjon hozzá szavakat, amelyeket az Ominek fel kell ismernie az átírás során.';

  @override
  String get enterWordsHint => 'Adjon meg szavakat (vesszővel elválasztva)';

  @override
  String get dailySummaryHeader => 'NAPI ÖSSZEFOGLALÓ';

  @override
  String get dailySummaryTitle => 'Napi Összefoglaló';

  @override
  String get dailySummaryDescription => 'Kapj személyre szabott összefoglalót a nap beszélgetéseiről értesítésként.';

  @override
  String get deliveryTime => 'Kézbesítési idő';

  @override
  String get deliveryTimeDescription => 'Mikor kapja meg a napi összefoglalót';

  @override
  String get subscription => 'Előfizetés';

  @override
  String get viewPlansAndUsage => 'Csomagok és Használat Megtekintése';

  @override
  String get viewPlansDescription => 'Kezelje előfizetését és tekintse meg a használati statisztikákat';

  @override
  String get addOrChangePaymentMethod => 'Adjon hozzá vagy módosítsa fizetési módját';

  @override
  String get displayOptions => 'Megjelenítési beállítások';

  @override
  String get showMeetingsInMenuBar => 'Találkozók megjelenítése a menüsorban';

  @override
  String get displayUpcomingMeetingsDescription => 'Közelgő találkozók megjelenítése a menüsorban';

  @override
  String get showEventsWithoutParticipants => 'Résztvevők nélküli események megjelenítése';

  @override
  String get includePersonalEventsDescription => 'Résztvevők nélküli személyes események befoglalása';

  @override
  String get upcomingMeetings => 'Közelgő találkozók';

  @override
  String get checkingNext7Days => 'A következő 7 nap ellenőrzése';

  @override
  String get shortcuts => 'Gyorsbillentyűk';

  @override
  String get shortcutChangeInstruction =>
      'Kattintson egy gyorsbillentyűre a módosításához. Nyomja meg az Escape gombot a megszakításhoz.';

  @override
  String get configurePersonaDescription => 'Konfigurálja AI personáját';

  @override
  String get configureSTTProvider => 'STT szolgáltató konfigurálása';

  @override
  String get setConversationEndDescription => 'Állítsa be, mikor érjenek véget automatikusan a beszélgetések';

  @override
  String get importDataDescription => 'Adatok importálása más forrásokból';

  @override
  String get exportConversationsDescription => 'Beszélgetések exportálása JSON-ba';

  @override
  String get exportingConversations => 'Beszélgetések exportálása...';

  @override
  String get clearNodesDescription => 'Összes csomópont és kapcsolat törlése';

  @override
  String get deleteKnowledgeGraphQuestion => 'Törölni a tudásgráfot?';

  @override
  String get deleteKnowledgeGraphWarning =>
      'Ez törli az összes származtatott tudásgráf adatot. Az eredeti emlékei biztonságban maradnak.';

  @override
  String get connectOmiWithAI => 'Csatlakoztassa az Omi-t AI asszisztensekhez';

  @override
  String get noAPIKeys => 'Nincsenek API kulcsok. Hozzon létre egyet a kezdéshez.';

  @override
  String get autoCreateWhenDetected => 'Automatikus létrehozás név észlelésekor';

  @override
  String get trackPersonalGoals => 'Személyes célok követése a főoldalon';

  @override
  String get dailyReflectionDescription =>
      'Kapj emlékeztetőt este 9-kor, hogy elgondolkodj a napodról és rögzítsd gondolataidat.';

  @override
  String get endpointURL => 'Végpont URL';

  @override
  String get links => 'Linkek';

  @override
  String get discordMemberCount => 'Több mint 8000 tag a Discordon';

  @override
  String get userInformation => 'Felhasználói információk';

  @override
  String get capabilities => 'Képességek';

  @override
  String get previewScreenshots => 'Képernyőkép előnézet';

  @override
  String get holdOnPreparingForm => 'Várjon, előkészítjük az űrlapot';

  @override
  String get bySubmittingYouAgreeToOmi => 'Beküldéssel elfogadja az Omi ';

  @override
  String get termsAndPrivacyPolicy => 'Feltételek és Adatvédelmi Irányelvek';

  @override
  String get helpsDiagnoseIssuesAutoDeletes =>
      'Segít a problémák diagnosztizálásában. 3 nap után automatikusan törlődik.';

  @override
  String get manageYourApp => 'Alkalmazás kezelése';

  @override
  String get updatingYourApp => 'Alkalmazás frissítése';

  @override
  String get fetchingYourAppDetails => 'Alkalmazás részleteinek lekérése';

  @override
  String get updateAppQuestion => 'Alkalmazás frissítése?';

  @override
  String get updateAppConfirmation =>
      'Biztosan frissíteni szeretné az alkalmazást? A változtatások a csapatunk általi felülvizsgálat után lépnek érvénybe.';

  @override
  String get updateApp => 'Alkalmazás frissítése';

  @override
  String get createAndSubmitNewApp => 'Új alkalmazás létrehozása és beküldése';

  @override
  String appsCount(String count) {
    return 'Alkalmazások ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'Privát alkalmazások ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'Nyilvános alkalmazások ($count)';
  }

  @override
  String get newVersionAvailable => 'Új verzió elérhető  🎉';

  @override
  String get no => 'Nem';

  @override
  String get subscriptionCancelledSuccessfully =>
      'Előfizetés sikeresen lemondva. Az aktuális számlázási időszak végéig aktív marad.';

  @override
  String get failedToCancelSubscription => 'Az előfizetés lemondása sikertelen. Kérjük, próbálja újra.';

  @override
  String get invalidPaymentUrl => 'Érvénytelen fizetési URL';

  @override
  String get permissionsAndTriggers => 'Engedélyek és triggerek';

  @override
  String get chatFeatures => 'Chat funkciók';

  @override
  String get uninstall => 'Eltávolítás';

  @override
  String get installs => 'TELEPÍTÉSEK';

  @override
  String get priceLabel => 'ÁR';

  @override
  String get updatedLabel => 'FRISSÍTVE';

  @override
  String get createdLabel => 'LÉTREHOZVA';

  @override
  String get featuredLabel => 'KIEMELT';

  @override
  String get cancelSubscriptionQuestion => 'Előfizetés lemondása?';

  @override
  String get cancelSubscriptionConfirmation =>
      'Biztosan le szeretné mondani az előfizetését? Az aktuális számlázási időszak végéig továbbra is hozzáférhet.';

  @override
  String get cancelSubscriptionButton => 'Előfizetés lemondása';

  @override
  String get cancelling => 'Lemondás...';

  @override
  String get betaTesterMessage =>
      'Ön ennek az alkalmazásnak a béta tesztelője. Még nem nyilvános. A jóváhagyás után lesz nyilvános.';

  @override
  String get appUnderReviewMessage =>
      'Az alkalmazása felülvizsgálat alatt áll és csak Ön láthatja. A jóváhagyás után lesz nyilvános.';

  @override
  String get appRejectedMessage => 'Az alkalmazása el lett utasítva. Kérjük, frissítse az adatokat és küldje el újra.';

  @override
  String get invalidIntegrationUrl => 'Érvénytelen integrációs URL';

  @override
  String get tapToComplete => 'Koppints a befejezéshez';

  @override
  String get invalidSetupInstructionsUrl => 'Érvénytelen beállítási útmutató URL';

  @override
  String get pushToTalk => 'Nyomd meg a beszédhez';

  @override
  String get summaryPrompt => 'Összefoglaló prompt';

  @override
  String get pleaseSelectARating => 'Kérjük, válasszon értékelést';

  @override
  String get reviewAddedSuccessfully => 'Vélemény sikeresen hozzáadva 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'Vélemény sikeresen frissítve 🚀';

  @override
  String get failedToSubmitReview => 'Nem sikerült elküldeni a véleményt. Kérlek próbáld újra.';

  @override
  String get addYourReview => 'Értékelés hozzáadása';

  @override
  String get editYourReview => 'Értékelés szerkesztése';

  @override
  String get writeAReviewOptional => 'Írjon értékelést (opcionális)';

  @override
  String get submitReview => 'Értékelés küldése';

  @override
  String get updateReview => 'Értékelés frissítése';

  @override
  String get yourReview => 'Az Ön értékelése';

  @override
  String get anonymousUser => 'Névtelen felhasználó';

  @override
  String get issueActivatingApp => 'Probléma merült fel az alkalmazás aktiválásakor. Kérjük, próbálja újra.';

  @override
  String get dataAccessNoticeDescription =>
      'Ez az alkalmazás hozzá fog férni az adataidhoz. Az Omi AI nem felelős azért, hogy ez az alkalmazás hogyan használja, módosítja vagy törli az adataidat';

  @override
  String get copyUrl => 'URL másolása';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => 'Hét';

  @override
  String get weekdayTue => 'Kedd';

  @override
  String get weekdayWed => 'Szer';

  @override
  String get weekdayThu => 'Csüt';

  @override
  String get weekdayFri => 'Pén';

  @override
  String get weekdaySat => 'Szo';

  @override
  String get weekdaySun => 'Vas';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return '$serviceName integráció hamarosan';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'Már exportálva ide: $platform';
  }

  @override
  String get anotherPlatform => 'másik platform';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'Kérjük, jelentkezzen be a $serviceName szolgáltatásba a Beállítások > Feladatintegrációk menüben';
  }

  @override
  String addingToService(String serviceName) {
    return 'Hozzáadás a $serviceName szolgáltatáshoz...';
  }

  @override
  String addedToService(String serviceName) {
    return 'Hozzáadva a $serviceName szolgáltatáshoz';
  }

  @override
  String failedToAddToService(String serviceName) {
    return 'Nem sikerült hozzáadni a $serviceName szolgáltatáshoz';
  }

  @override
  String get permissionDeniedForAppleReminders => 'Engedély megtagadva az Apple Emlékeztetők számára';

  @override
  String failedToCreateApiKey(String error) {
    return 'Nem sikerült létrehozni a szolgáltató API-kulcsát: $error';
  }

  @override
  String get createAKey => 'Kulcs létrehozása';

  @override
  String get apiKeyRevokedSuccessfully => 'API-kulcs sikeresen visszavonva';

  @override
  String failedToRevokeApiKey(String error) {
    return 'Nem sikerült visszavonni az API-kulcsot: $error';
  }

  @override
  String get omiApiKeys => 'Omi API-kulcsok';

  @override
  String get apiKeysDescription =>
      'Az API-kulcsokat hitelesítésre használják, amikor az alkalmazásod kommunikál az OMI szerverrel. Lehetővé teszik az alkalmazásod számára, hogy emlékeket hozzon létre és biztonságosan hozzáférjen más OMI szolgáltatásokhoz.';

  @override
  String get aboutOmiApiKeys => 'Az Omi API-kulcsokról';

  @override
  String get yourNewKey => 'Az új kulcsod:';

  @override
  String get copyToClipboard => 'Másolás a vágólapra';

  @override
  String get pleaseCopyKeyNow => 'Kérjük, másold le most és írd le valahova biztonságos helyre. ';

  @override
  String get willNotSeeAgain => 'Nem fogod tudni újra látni.';

  @override
  String get revokeKey => 'Kulcs visszavonása';

  @override
  String get revokeApiKeyQuestion => 'API-kulcs visszavonása?';

  @override
  String get revokeApiKeyWarning =>
      'Ez a művelet nem vonható vissza. Az ezt a kulcsot használó alkalmazások többé nem férhetnek hozzá az API-hoz.';

  @override
  String get revoke => 'Visszavonás';

  @override
  String get whatWouldYouLikeToCreate => 'Mit szeretne létrehozni?';

  @override
  String get createAnApp => 'Alkalmazás létrehozása';

  @override
  String get createAndShareYourApp => 'Hozza létre és ossza meg alkalmazását';

  @override
  String get createMyClone => 'Klónom létrehozása';

  @override
  String get createYourDigitalClone => 'Hozza létre digitális klónját';

  @override
  String get itemApp => 'Alkalmazás';

  @override
  String get itemPersona => 'Persona';

  @override
  String keepItemPublic(String item) {
    return '$item nyilvános tartása';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return '$item nyilvánossá tétele?';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return '$item priváttá tétele?';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'Ha nyilvánossá teszi a(z) $item-t, mindenki használhatja';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'Ha most priváttá teszi a(z) $item-t, az mindenki számára leáll és csak ön láthatja';
  }

  @override
  String get manageApp => 'Alkalmazás kezelése';

  @override
  String get updatePersonaDetails => 'Persona részleteinek frissítése';

  @override
  String deleteItemTitle(String item) {
    return '$item törlése';
  }

  @override
  String deleteItemQuestion(String item) {
    return '$item törlése?';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'Biztosan törölni szeretné ezt a(z) $item-t? Ez a művelet nem vonható vissza.';
  }

  @override
  String get revokeKeyQuestion => 'Kulcs visszavonása?';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'Biztosan vissza szeretné vonni a(z) \"$keyName\" kulcsot? Ez a művelet nem vonható vissza.';
  }

  @override
  String get createNewKey => 'Új kulcs létrehozása';

  @override
  String get keyNameHint => 'pl. Claude Desktop';

  @override
  String get pleaseEnterAName => 'Kérjük, adjon meg egy nevet.';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'Nem sikerült létrehozni a kulcsot: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'Nem sikerült létrehozni a kulcsot. Kérjük, próbálja újra.';

  @override
  String get keyCreated => 'Kulcs létrehozva';

  @override
  String get keyCreatedMessage => 'Az új kulcsa létrejött. Kérjük, másolja most. Nem fogja tudni újra megtekinteni.';

  @override
  String get keyWord => 'Kulcs';

  @override
  String get externalAppAccess => 'Külső alkalmazás hozzáférés';

  @override
  String get externalAppAccessDescription =>
      'A következő telepített alkalmazásoknak külső integrációi vannak, és hozzáférhetnek az adataihoz, például beszélgetésekhez és emlékekhez.';

  @override
  String get noExternalAppsHaveAccess => 'Egyetlen külső alkalmazásnak sincs hozzáférése az adataihoz.';

  @override
  String get maximumSecurityE2ee => 'Maximális biztonság (E2EE)';

  @override
  String get e2eeDescription =>
      'A végpontok közötti titkosítás a magánélet aranystandardja. Ha engedélyezve van, az adatait az eszközén titkosítjuk, mielőtt elküldenénk a szervereinkre. Ez azt jelenti, hogy senki, még az Omi sem férhet hozzá a tartalmához.';

  @override
  String get importantTradeoffs => 'Fontos kompromisszumok:';

  @override
  String get e2eeTradeoff1 => '• Egyes funkciók, mint például a külső alkalmazás-integrációk, letilthatók.';

  @override
  String get e2eeTradeoff2 => '• Ha elveszíti jelszavát, az adatai nem állíthatók helyre.';

  @override
  String get featureComingSoon => 'Ez a funkció hamarosan érkezik!';

  @override
  String get migrationInProgressMessage =>
      'Migráció folyamatban. A védelmi szintet nem módosíthatja, amíg be nem fejeződik.';

  @override
  String get migrationFailed => 'A migráció sikertelen';

  @override
  String migratingFromTo(String source, String target) {
    return 'Migráció $source típusról $target típusra';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total objektum';
  }

  @override
  String get secureEncryption => 'Biztonságos titkosítás';

  @override
  String get secureEncryptionDescription =>
      'Az adatait egy Önnek egyedi kulccsal titkosítjuk a szervereink, amelyek a Google Cloudon vannak. Ez azt jelenti, hogy a nyers tartalma senkinek sem hozzáférhető, beleértve az Omi személyzetét vagy a Google-t, közvetlenül az adatbázisból.';

  @override
  String get endToEndEncryption => 'Végpontok közötti titkosítás';

  @override
  String get e2eeCardDescription =>
      'Engedélyezze a maximális biztonságot, ahol csak ön férhet hozzá adataihoz. Érintse meg a további információkért.';

  @override
  String get dataAlwaysEncrypted =>
      'A szinttől függetlenül az adatai mindig titkosítva vannak nyugalmi állapotban és átvitel közben.';

  @override
  String get readOnlyScope => 'Csak olvasható';

  @override
  String get fullAccessScope => 'Teljes hozzáférés';

  @override
  String get readScope => 'Olvasás';

  @override
  String get writeScope => 'Írás';

  @override
  String get apiKeyCreated => 'API kulcs létrehozva!';

  @override
  String get saveKeyWarning => 'Mentse el ezt a kulcsot most! Nem fogja tudni újra megtekinteni.';

  @override
  String get yourApiKey => 'AZ ÖN API KULCSA';

  @override
  String get tapToCopy => 'Másoláshoz érintse meg';

  @override
  String get copyKey => 'Kulcs másolása';

  @override
  String get createApiKey => 'API kulcs létrehozása';

  @override
  String get accessDataProgrammatically => 'Programozott hozzáférés az adataihoz';

  @override
  String get keyNameLabel => 'KULCS NEVE';

  @override
  String get keyNamePlaceholder => 'pl. Az én integrációm';

  @override
  String get permissionsLabel => 'ENGEDÉLYEK';

  @override
  String get permissionsInfoNote =>
      'R = Olvasás, W = Írás. Alapértelmezés szerint csak olvasható, ha nincs semmi kiválasztva.';

  @override
  String get developerApi => 'Fejlesztői API';

  @override
  String get createAKeyToGetStarted => 'Hozzon létre egy kulcsot a kezdéshez';

  @override
  String errorWithMessage(String error) {
    return 'Hiba: $error';
  }

  @override
  String get omiTraining => 'Omi Képzés';

  @override
  String get trainingDataProgram => 'Képzési adatprogram';

  @override
  String get getOmiUnlimitedFree =>
      'Szerezze meg az Omi Unlimited-et ingyen, ha hozzájárul adataival az AI modellek képzéséhez.';

  @override
  String get trainingDataBullets =>
      '• Az adatai segítenek az AI modellek fejlesztésében\n• Csak nem érzékeny adatok kerülnek megosztásra\n• Teljesen átlátható folyamat';

  @override
  String get learnMoreAtOmiTraining => 'További információ: omi.me/training';

  @override
  String get agreeToContributeData => 'Megértem és beleegyezem, hogy hozzájáruljak adataimmal az AI képzéséhez';

  @override
  String get submitRequest => 'Kérelem beküldése';

  @override
  String get thankYouRequestUnderReview => 'Köszönjük! Kérelme felülvizsgálat alatt áll. Értesítjük a jóváhagyás után.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'A csomagja $date-ig aktív marad. Ezután elveszíti a korlátlan funkciókhoz való hozzáférést. Biztos benne?';
  }

  @override
  String get confirmCancellation => 'Lemondás megerősítése';

  @override
  String get keepMyPlan => 'Csomagom megtartása';

  @override
  String get subscriptionSetToCancel => 'Az előfizetése az időszak végén törlésre van beállítva.';

  @override
  String get switchedToOnDevice => 'Eszközön történő átírásra váltva';

  @override
  String get couldNotSwitchToFreePlan => 'Nem sikerült váltani az ingyenes csomagra. Kérjük, próbálja újra.';

  @override
  String get couldNotLoadPlans => 'Nem sikerült betölteni az elérhető csomagokat. Kérjük, próbálja újra.';

  @override
  String get selectedPlanNotAvailable => 'A kiválasztott csomag nem érhető el. Kérjük, próbálja újra.';

  @override
  String get upgradeToAnnualPlan => 'Frissítés éves csomagra';

  @override
  String get importantBillingInfo => 'Fontos számlázási információk:';

  @override
  String get monthlyPlanContinues => 'Jelenlegi havi csomagja a számlázási időszak végéig folytatódik';

  @override
  String get paymentMethodCharged =>
      'A meglévő fizetési módja automatikusan terhelésre kerül, amikor a havi csomagja lejár';

  @override
  String get annualSubscriptionStarts => '12 hónapos éves előfizetése automatikusan elindul a terhelés után';

  @override
  String get thirteenMonthsCoverage => 'Összesen 13 hónap lefedettséget kap (jelenlegi hónap + 12 hónap éves)';

  @override
  String get confirmUpgrade => 'Frissítés megerősítése';

  @override
  String get confirmPlanChange => 'Csomagváltás megerősítése';

  @override
  String get confirmAndProceed => 'Megerősítés és folytatás';

  @override
  String get upgradeScheduled => 'Frissítés ütemezve';

  @override
  String get changePlan => 'Csomag váltás';

  @override
  String get upgradeAlreadyScheduled => 'Az éves csomagra való frissítése már ütemezve van';

  @override
  String get youAreOnUnlimitedPlan => 'Ön a Korlátlan csomagban van.';

  @override
  String get yourOmiUnleashed => 'Az Omi-ja, szabadjára engedve. Váljon korlátlanná a végtelen lehetőségekért.';

  @override
  String planEndedOn(String date) {
    return 'A csomagja $date-án lejárt.\\nIratkozzon fel újra most - azonnal felszámítjuk az új számlázási időszakot.';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'A csomagja $date-án törlésre van beállítva.\\nIratkozzon fel újra most, hogy megtartsa előnyeit - nincs díj $date-ig.';
  }

  @override
  String get annualPlanStartsAutomatically => 'Az éves csomagja automatikusan elindul, amikor a havi csomagja lejár.';

  @override
  String planRenewsOn(String date) {
    return 'A csomagja $date-án megújul.';
  }

  @override
  String get unlimitedConversations => 'Korlátlan beszélgetések';

  @override
  String get askOmiAnything => 'Kérdezzen Omi-tól bármit az életéről';

  @override
  String get unlockOmiInfiniteMemory => 'Oldja fel Omi végtelen memóriáját';

  @override
  String get youreOnAnnualPlan => 'Ön az éves csomagon van';

  @override
  String get alreadyBestValuePlan => 'Már a legjobb értékű csomagja van. Nincs szükség változtatásra.';

  @override
  String get unableToLoadPlans => 'Nem sikerült betölteni a csomagokat';

  @override
  String get checkConnectionTryAgain => 'Ellenőrizze a kapcsolatot és próbálja újra';

  @override
  String get useFreePlan => 'Ingyenes csomag használata';

  @override
  String get continueText => 'Folytatás';

  @override
  String get resubscribe => 'Újra feliratkozás';

  @override
  String get couldNotOpenPaymentSettings => 'Nem sikerült megnyitni a fizetési beállításokat. Kérjük, próbálja újra.';

  @override
  String get managePaymentMethod => 'Fizetési mód kezelése';

  @override
  String get cancelSubscription => 'Előfizetés lemondása';

  @override
  String endsOnDate(String date) {
    return 'Lejár: $date';
  }

  @override
  String get active => 'Aktív';

  @override
  String get freePlan => 'Ingyenes csomag';

  @override
  String get configure => 'Beállítás';

  @override
  String get privacyInformation => 'Adatvédelmi információk';

  @override
  String get yourPrivacyMattersToUs => 'Adatai védelme fontos számunkra';

  @override
  String get privacyIntroText =>
      'Az Ominál nagyon komolyan vesszük az adatvédelmet. Átláthatóak szeretnénk lenni az általunk gyűjtött adatokról és azok felhasználásáról. Íme, amit tudnia kell:';

  @override
  String get whatWeTrack => 'Mit követünk nyomon';

  @override
  String get anonymityAndPrivacy => 'Anonimitás és adatvédelem';

  @override
  String get optInAndOptOutOptions => 'Feliratkozási és leiratkozási lehetőségek';

  @override
  String get ourCommitment => 'Elkötelezettségünk';

  @override
  String get commitmentText =>
      'Elkötelezettek vagyunk amellett, hogy az általunk gyűjtött adatokat csak arra használjuk, hogy az Omi jobb termék legyen az Ön számára. Adatainak védelme és bizalma kiemelten fontos számunkra.';

  @override
  String get thankYouText =>
      'Köszönjük, hogy az Omi értékes felhasználója. Ha kérdése vagy aggálya van, forduljon hozzánk a team@basedhardware.com címen.';

  @override
  String get wifiSyncSettings => 'WiFi szinkronizálás beállításai';

  @override
  String get enterHotspotCredentials => 'Adja meg telefonja hotspot hitelesítő adatait';

  @override
  String get wifiSyncUsesHotspot =>
      'A WiFi szinkronizálás a telefont hotspotként használja. A nevet és jelszót a Beállítások > Személyes hotspot menüben találja.';

  @override
  String get hotspotNameSsid => 'Hotspot neve (SSID)';

  @override
  String get exampleIphoneHotspot => 'pl. iPhone Hotspot';

  @override
  String get password => 'Jelszó';

  @override
  String get enterHotspotPassword => 'Adja meg a hotspot jelszavát';

  @override
  String get saveCredentials => 'Hitelesítő adatok mentése';

  @override
  String get clearCredentials => 'Hitelesítő adatok törlése';

  @override
  String get pleaseEnterHotspotName => 'Kérjük, adjon meg egy hotspot nevet';

  @override
  String get wifiCredentialsSaved => 'WiFi hitelesítő adatok mentve';

  @override
  String get wifiCredentialsCleared => 'WiFi hitelesítő adatok törölve';

  @override
  String summaryGeneratedForDate(String date) {
    return 'Összefoglaló létrehozva: $date';
  }

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'Nem sikerült létrehozni az összefoglalót. Győződjön meg róla, hogy vannak beszélgetései aznap.';

  @override
  String get summaryNotFound => 'Összefoglaló nem található';

  @override
  String get yourDaysJourney => 'A napod útja';

  @override
  String get highlights => 'Kiemelések';

  @override
  String get unresolvedQuestions => 'Megoldatlan kérdések';

  @override
  String get decisions => 'Döntések';

  @override
  String get learnings => 'Tanulságok';

  @override
  String get autoDeletesAfterThreeDays => 'Automatikusan törlődik 3 nap után.';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'Tudásgráf sikeresen törölve';

  @override
  String get exportStartedMayTakeFewSeconds => 'Exportálás elindítva. Ez eltarthat néhány másodpercig...';

  @override
  String get knowledgeGraphDeleteDescription =>
      'Ez törli az összes származtatott tudásgráf adatot (csomópontokat és kapcsolatokat). Az eredeti emlékei biztonságban maradnak. A gráf idővel vagy a következő kérésnél újraépül.';

  @override
  String get configureDailySummaryDigest => 'Állítsa be a napi feladatösszesítőt';

  @override
  String accessesDataTypes(String dataTypes) {
    return 'Hozzáfér: $dataTypes';
  }

  @override
  String triggeredByType(String triggerType) {
    return '$triggerType által kiváltva';
  }

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription és $triggerDescription.';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return '$triggerDescription.';
  }

  @override
  String get noSpecificDataAccessConfigured => 'Nincs beállítva specifikus adathozzáférés.';

  @override
  String get basicPlanDescription => '1200 prémium perc + korlátlan eszközön';

  @override
  String get minutes => 'perc';

  @override
  String get omiHas => 'Omi:';

  @override
  String get premiumMinutesUsed => 'Prémium percek elhasználva.';

  @override
  String get setupOnDevice => 'Eszközön beállítás';

  @override
  String get forUnlimitedFreeTranscription => 'korlátlan ingyenes átíráshoz.';

  @override
  String premiumMinsLeft(int count) {
    return '$count prémium perc maradt.';
  }

  @override
  String get alwaysAvailable => 'mindig elérhető.';

  @override
  String get importHistory => 'Importálási előzmények';

  @override
  String get noImportsYet => 'Még nincs importálás';

  @override
  String get selectZipFileToImport => 'Válassza ki az importálandó .zip fájlt!';

  @override
  String get otherDevicesComingSoon => 'Más eszközök hamarosan';

  @override
  String get deleteAllLimitlessConversations => 'Törli az összes Limitless beszélgetést?';

  @override
  String get deleteAllLimitlessWarning =>
      'Ez véglegesen törli a Limitlessből importált összes beszélgetést. Ez a művelet nem vonható vissza.';

  @override
  String deletedLimitlessConversations(int count) {
    return '$count Limitless beszélgetés törölve';
  }

  @override
  String get failedToDeleteConversations => 'A beszélgetések törlése sikertelen';

  @override
  String get deleteImportedData => 'Importált adatok törlése';

  @override
  String get statusPending => 'Függőben';

  @override
  String get statusProcessing => 'Feldolgozás';

  @override
  String get statusCompleted => 'Befejezve';

  @override
  String get statusFailed => 'Sikertelen';

  @override
  String nConversations(int count) {
    return '$count beszélgetés';
  }

  @override
  String get pleaseEnterName => 'Kérjük, adjon meg egy nevet';

  @override
  String get nameMustBeBetweenCharacters => 'A névnek 2 és 40 karakter között kell lennie';

  @override
  String get deleteSampleQuestion => 'Minta törlése?';

  @override
  String deleteSampleConfirmation(String name) {
    return 'Biztosan törölni szeretné $name mintáját?';
  }

  @override
  String get confirmDeletion => 'Törlés megerősítése';

  @override
  String deletePersonConfirmation(String name) {
    return 'Biztosan törölni szeretné $name személyt? Ez eltávolítja az összes kapcsolódó hangmintát is.';
  }

  @override
  String get howItWorksTitle => 'Hogyan működik?';

  @override
  String get howPeopleWorks =>
      'Ha létrehoz egy személyt, elmehet egy beszélgetés átiratához, és hozzárendelheti a megfelelő szegmenseket, így az Omi képes lesz felismerni az ő beszédét is!';

  @override
  String get tapToDelete => 'Koppintson a törléshez';

  @override
  String get newTag => 'ÚJ';

  @override
  String get needHelpChatWithUs => 'Segítségre van szüksége? Csevegjen velünk';

  @override
  String get localStorageEnabled => 'Helyi tárolás engedélyezve';

  @override
  String get localStorageDisabled => 'Helyi tárolás letiltva';

  @override
  String failedToUpdateSettings(String error) {
    return 'A beállítások frissítése sikertelen: $error';
  }

  @override
  String get privacyNotice => 'Adatvédelmi figyelmeztetés';

  @override
  String get recordingsMayCaptureOthers =>
      'A felvételek rögzíthetik mások hangját. A bekapcsolás előtt győződjön meg arról, hogy minden résztvevő beleegyezését megkapta.';

  @override
  String get enable => 'Engedélyezés';

  @override
  String get storeAudioOnPhone => 'Hanganyag tárolása telefonon';

  @override
  String get on => 'Be';

  @override
  String get storeAudioDescription =>
      'Tartsa az összes hangfelvételt helyileg tárolva a telefonján. Letiltva csak a sikertelen feltöltések maradnak meg a tárhely megtakarítása érdekében.';

  @override
  String get enableLocalStorage => 'Helyi tárolás engedélyezése';

  @override
  String get cloudStorageEnabled => 'Felhőtárhely engedélyezve';

  @override
  String get cloudStorageDisabled => 'Felhőtárhely letiltva';

  @override
  String get enableCloudStorage => 'Felhőtárhely engedélyezése';

  @override
  String get storeAudioOnCloud => 'Hanganyag tárolása felhőben';

  @override
  String get cloudStorageDialogMessage =>
      'Valós idejű felvételei a beszéd közben privát felhőtárhelyen kerülnek tárolásra.';

  @override
  String get storeAudioCloudDescription =>
      'Tárolja valós idejű felvételeit privát felhőtárhelyen beszéd közben. A hang valós időben, biztonságosan rögzítésre és mentésre kerül.';

  @override
  String get downloadingFirmware => 'Firmware letöltése';

  @override
  String get installingFirmware => 'Firmware telepítése';

  @override
  String get firmwareUpdateWarning =>
      'Ne zárja be az alkalmazást és ne kapcsolja ki az eszközt. Ez károsíthatja az eszközét.';

  @override
  String get firmwareUpdated => 'Firmware frissítve';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'Kérjük, indítsa újra a(z) $deviceName eszközét a frissítés befejezéséhez.';
  }

  @override
  String get yourDeviceIsUpToDate => 'Az eszköze naprakész';

  @override
  String get currentVersion => 'Jelenlegi verzió';

  @override
  String get latestVersion => 'Legújabb verzió';

  @override
  String get whatsNew => 'Újdonságok';

  @override
  String get installUpdate => 'Frissítés telepítése';

  @override
  String get updateNow => 'Frissítés most';

  @override
  String get updateGuide => 'Frissítési útmutató';

  @override
  String get checkingForUpdates => 'Frissítések keresése';

  @override
  String get checkingFirmwareVersion => 'Firmware verzió ellenőrzése...';

  @override
  String get firmwareUpdate => 'Firmware frissítés';

  @override
  String get payments => 'Fizetések';

  @override
  String get connectPaymentMethodInfo =>
      'Csatlakoztasson alább egy fizetési módot, hogy elkezdhesse fogadni a kifizetéseket az alkalmazásaiért.';

  @override
  String get selectedPaymentMethod => 'Kiválasztott fizetési mód';

  @override
  String get availablePaymentMethods => 'Elérhető fizetési módok';

  @override
  String get activeStatus => 'Aktív';

  @override
  String get connectedStatus => 'Csatlakoztatva';

  @override
  String get notConnectedStatus => 'Nincs csatlakoztatva';

  @override
  String get setActive => 'Beállítás aktívként';

  @override
  String get getPaidThroughStripe => 'Kapjon fizetést az alkalmazás-eladásaiért a Stripe-on keresztül';

  @override
  String get monthlyPayouts => 'Havi kifizetések';

  @override
  String get monthlyPayoutsDescription =>
      'Kapjon havi kifizetéseket közvetlenül a számlájára, amikor eléri a 10 \$ bevételt';

  @override
  String get secureAndReliable => 'Biztonságos és megbízható';

  @override
  String get stripeSecureDescription =>
      'A Stripe biztonságos és időben történő átutalásokat biztosít az alkalmazás bevételeihez';

  @override
  String get selectYourCountry => 'Válassza ki az országát';

  @override
  String get countrySelectionPermanent => 'Az országválasztás végleges és később nem módosítható.';

  @override
  String get byClickingConnectNow => 'A \"Csatlakozás most\" gombra kattintva elfogadja';

  @override
  String get stripeConnectedAccountAgreement => 'Stripe Connected Account megállapodás';

  @override
  String get errorConnectingToStripe => 'Hiba a Stripe-hoz való csatlakozáskor! Kérjük, próbálja újra később.';

  @override
  String get connectingYourStripeAccount => 'Stripe fiókjának csatlakoztatása';

  @override
  String get stripeOnboardingInstructions =>
      'Kérjük, fejezze be a Stripe bevezetési folyamatot a böngészőjében. Ez az oldal automatikusan frissül a befejezés után.';

  @override
  String get failedTryAgain => 'Sikertelen? Próbálja újra';

  @override
  String get illDoItLater => 'Később megcsinálom';

  @override
  String get successfullyConnected => 'Sikeresen csatlakoztatva!';

  @override
  String get stripeReadyForPayments =>
      'Stripe-fiókja készen áll a kifizetések fogadására. Azonnal elkezdheti a keresést az alkalmazás-eladásaiból.';

  @override
  String get updateStripeDetails => 'Stripe adatok frissítése';

  @override
  String get errorUpdatingStripeDetails => 'Hiba a Stripe adatok frissítésekor! Kérjük, próbálja újra később.';

  @override
  String get updatePayPal => 'PayPal frissítése';

  @override
  String get setUpPayPal => 'PayPal beállítása';

  @override
  String get updatePayPalAccountDetails => 'Frissítse PayPal-fiókja adatait';

  @override
  String get connectPayPalToReceivePayments =>
      'Csatlakoztassa PayPal-fiókját, hogy elkezdhesse fogadni a kifizetéseket az alkalmazásaiért';

  @override
  String get paypalEmail => 'PayPal e-mail';

  @override
  String get paypalMeLink => 'PayPal.me link';

  @override
  String get stripeRecommendation =>
      'Ha a Stripe elérhető az Ön országában, erősen javasoljuk, hogy használja a gyorsabb és egyszerűbb kifizetésekhez.';

  @override
  String get updatePayPalDetails => 'PayPal adatok frissítése';

  @override
  String get savePayPalDetails => 'PayPal adatok mentése';

  @override
  String get pleaseEnterPayPalEmail => 'Kérjük, adja meg PayPal e-mail címét';

  @override
  String get pleaseEnterPayPalMeLink => 'Kérjük, adja meg PayPal.me linkjét';

  @override
  String get doNotIncludeHttpInLink => 'Ne adjon meg http, https vagy www előtagot a linkben';

  @override
  String get pleaseEnterValidPayPalMeLink => 'Kérjük, adjon meg egy érvényes PayPal.me linket';

  @override
  String get pleaseEnterValidEmail => 'Kérjük, adjon meg egy érvényes e-mail címet';

  @override
  String get syncingYourRecordings => 'Felvételek szinkronizálása';

  @override
  String get syncYourRecordings => 'Szinkronizáld a felvételeidet';

  @override
  String get syncNow => 'Szinkronizálás most';

  @override
  String get error => 'Hiba';

  @override
  String get speechSamples => 'Hangminták';

  @override
  String additionalSampleIndex(String index) {
    return 'További minta $index';
  }

  @override
  String durationSeconds(String seconds) {
    return 'Időtartam: $seconds másodperc';
  }

  @override
  String get additionalSpeechSampleRemoved => 'További hangminta eltávolítva';

  @override
  String get consentDataMessage =>
      'A folytatással az alkalmazással megosztott összes adat (beleértve a beszélgetéseket, felvételeket és személyes adatokat) biztonságosan tárolódik a szervereinkei, hogy AI-alapú betekintéseket nyújthassunk és engedélyezhessük az összes alkalmazásfunkciót.';

  @override
  String get tasksEmptyStateMessage =>
      'A beszélgetéseidből származó feladatok itt jelennek meg.\nKoppints a + gombra manuális létrehozáshoz.';

  @override
  String get clearChatAction => 'Chat törlése';

  @override
  String get enableApps => 'Alkalmazások engedélyezése';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => 'mutass többet ↓';

  @override
  String get showLess => 'mutass kevesebbet ↑';

  @override
  String get loadingYourRecording => 'Felvétel betöltése...';

  @override
  String get photoDiscardedMessage => 'Ez a fotó el lett vetve, mert nem volt jelentős.';

  @override
  String get analyzing => 'Elemzés...';

  @override
  String get searchCountries => 'Országok keresése...';

  @override
  String get checkingAppleWatch => 'Apple Watch ellenőrzése...';

  @override
  String get installOmiOnAppleWatch => 'Telepítse az Omit az\nApple Watch-ra';

  @override
  String get installOmiOnAppleWatchDescription =>
      'Az Apple Watch Omival való használatához először telepítenie kell az Omi alkalmazást az órájára.';

  @override
  String get openOmiOnAppleWatch => 'Nyissa meg az Omit az\nApple Watch-on';

  @override
  String get openOmiOnAppleWatchDescription =>
      'Az Omi alkalmazás telepítve van az Apple Watch-ra. Nyissa meg és érintse meg a Start gombot.';

  @override
  String get openWatchApp => 'Watch alkalmazás megnyitása';

  @override
  String get iveInstalledAndOpenedTheApp => 'Telepítettem és megnyitottam az alkalmazást';

  @override
  String get unableToOpenWatchApp =>
      'Nem sikerült megnyitni az Apple Watch alkalmazást. Nyissa meg manuálisan a Watch alkalmazást az Apple Watch-on, és telepítse az Omit az \"Elérhető alkalmazások\" részből.';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch sikeresen csatlakoztatva!';

  @override
  String get appleWatchNotReachable =>
      'Az Apple Watch még nem érhető el. Győződjön meg róla, hogy az Omi alkalmazás nyitva van az óráján.';

  @override
  String errorCheckingConnection(String error) {
    return 'Hiba a kapcsolat ellenőrzésekor: $error';
  }

  @override
  String get muted => 'Némítva';

  @override
  String get processNow => 'Feldolgozás most';

  @override
  String get finishedConversation => 'Beszélgetés befejezve?';

  @override
  String get stopRecordingConfirmation =>
      'Biztosan le szeretné állítani a felvételt és most összefoglalni a beszélgetést?';

  @override
  String get conversationEndsManually => 'A beszélgetés csak manuálisan fejeződik be.';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'A beszélgetés $minutes perc$suffix csend után összegződik.';
  }

  @override
  String get dontAskAgain => 'Ne kérdezd újra';

  @override
  String get waitingForTranscriptOrPhotos => 'Várakozás átiratra vagy fotókra...';

  @override
  String get noSummaryYet => 'Még nincs összefoglaló';

  @override
  String hints(String text) {
    return 'Tippek: $text';
  }

  @override
  String get testConversationPrompt => 'Beszélgetési prompt tesztelése';

  @override
  String get prompt => 'Prompt';

  @override
  String get result => 'Eredmény:';

  @override
  String get compareTranscripts => 'Átiratok összehasonlítása';

  @override
  String get notHelpful => 'Nem hasznos';

  @override
  String get exportTasksWithOneTap => 'Feladatok exportálása egy érintéssel!';

  @override
  String get inProgress => 'Folyamatban';

  @override
  String get photos => 'Fényképek';

  @override
  String get rawData => 'Nyers adatok';

  @override
  String get content => 'Tartalom';

  @override
  String get noContentToDisplay => 'Nincs megjeleníthető tartalom';

  @override
  String get noSummary => 'Nincs összefoglaló';

  @override
  String get updateOmiFirmware => 'Omi firmware frissítése';

  @override
  String get anErrorOccurredTryAgain => 'Hiba történt. Kérjük, próbálja újra.';

  @override
  String get welcomeBackSimple => 'Üdv újra';

  @override
  String get addVocabularyDescription =>
      'Adjon hozzá szavakat, amelyeket az Omi-nak fel kell ismernie az átírás során.';

  @override
  String get enterWordsCommaSeparated => 'Adja meg a szavakat (vesszővel elválasztva)';

  @override
  String get whenToReceiveDailySummary => 'Mikor kapja meg a napi összefoglalót';

  @override
  String get checkingNextSevenDays => 'A következő 7 nap ellenőrzése';

  @override
  String failedToDeleteError(String error) {
    return 'A törlés sikertelen: $error';
  }

  @override
  String get developerApiKeys => 'Fejlesztői API kulcsok';

  @override
  String get noApiKeysCreateOne => 'Nincsenek API kulcsok. Hozzon létre egyet a kezdéshez.';

  @override
  String get commandRequired => '⌘ szükséges';

  @override
  String get spaceKey => 'Szóköz';

  @override
  String loadMoreRemaining(String count) {
    return 'Továbbiak betöltése ($count maradt)';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'Top $percentile% felhasználó';
  }

  @override
  String get wrappedMinutes => 'perc';

  @override
  String get wrappedConversations => 'beszélgetés';

  @override
  String get wrappedDaysActive => 'aktív nap';

  @override
  String get wrappedYouTalkedAbout => 'Erről beszéltél';

  @override
  String get wrappedActionItems => 'Feladatok';

  @override
  String get wrappedTasksCreated => 'létrehozott feladat';

  @override
  String get wrappedCompleted => 'befejezett';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% teljesítési arány';
  }

  @override
  String get wrappedYourTopDays => 'Legjobb napjaid';

  @override
  String get wrappedBestMoments => 'Legjobb pillanatok';

  @override
  String get wrappedMyBuddies => 'Barátaim';

  @override
  String get wrappedCouldntStopTalkingAbout => 'Nem tudtam abbahagyni a beszélést';

  @override
  String get wrappedShow => 'SOROZAT';

  @override
  String get wrappedMovie => 'FILM';

  @override
  String get wrappedBook => 'KÖNYV';

  @override
  String get wrappedCelebrity => 'HÍRESSÉG';

  @override
  String get wrappedFood => 'ÉTEL';

  @override
  String get wrappedMovieRecs => 'Filmajánlók barátoknak';

  @override
  String get wrappedBiggest => 'Legnagyobb';

  @override
  String get wrappedStruggle => 'Kihívás';

  @override
  String get wrappedButYouPushedThrough => 'De sikerült 💪';

  @override
  String get wrappedWin => 'Győzelem';

  @override
  String get wrappedYouDidIt => 'Sikerült! 🎉';

  @override
  String get wrappedTopPhrases => 'Top 5 mondat';

  @override
  String get wrappedMins => 'perc';

  @override
  String get wrappedConvos => 'beszélgetés';

  @override
  String get wrappedDays => 'nap';

  @override
  String get wrappedMyBuddiesLabel => 'BARÁTAIM';

  @override
  String get wrappedObsessionsLabel => 'MEGSZÁLLOTTSÁGAIM';

  @override
  String get wrappedStruggleLabel => 'KIHÍVÁS';

  @override
  String get wrappedWinLabel => 'GYŐZELEM';

  @override
  String get wrappedTopPhrasesLabel => 'TOP MONDATOK';

  @override
  String get wrappedLetsHitRewind => 'Tekerjük vissza a';

  @override
  String get wrappedGenerateMyWrapped => 'Wrapped generálása';

  @override
  String get wrappedProcessingDefault => 'Feldolgozás...';

  @override
  String get wrappedCreatingYourStory => 'A 2025-ös\ntörténeted készül...';

  @override
  String get wrappedSomethingWentWrong => 'Valami\nhiba történt';

  @override
  String get wrappedAnErrorOccurred => 'Hiba történt';

  @override
  String get wrappedTryAgain => 'Próbáld újra';

  @override
  String get wrappedNoDataAvailable => 'Nincs elérhető adat';

  @override
  String get wrappedOmiLifeRecap => 'Omi élet összefoglaló';

  @override
  String get wrappedSwipeUpToBegin => 'Húzd felfelé a kezdéshez';

  @override
  String get wrappedShareText => '2025-öm, az Omi által megőrizve ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare => 'Megosztás sikertelen. Kérjük, próbáld újra.';

  @override
  String get wrappedFailedToStartGeneration => 'A generálás indítása sikertelen. Kérjük, próbáld újra.';

  @override
  String get wrappedStarting => 'Indítás...';

  @override
  String get wrappedShare => 'Megosztás';

  @override
  String get wrappedShareYourWrapped => 'Oszd meg a Wrapped-ed';

  @override
  String get wrappedMy2025 => '2025-öm';

  @override
  String get wrappedRememberedByOmi => 'az Omi által megőrizve';

  @override
  String get wrappedMostFunDay => 'Legszórakoztatóbb';

  @override
  String get wrappedMostProductiveDay => 'Legproduktívabb';

  @override
  String get wrappedMostIntenseDay => 'Legintenzívebb';

  @override
  String get wrappedFunniestMoment => 'Legviccesebb';

  @override
  String get wrappedMostCringeMoment => 'Legkínosabb';

  @override
  String get wrappedMinutesLabel => 'perc';

  @override
  String get wrappedConversationsLabel => 'beszélgetés';

  @override
  String get wrappedDaysActiveLabel => 'aktív nap';

  @override
  String get wrappedTasksGenerated => 'létrehozott feladat';

  @override
  String get wrappedTasksCompleted => 'befejezett feladat';

  @override
  String get wrappedTopFivePhrases => 'Top 5 kifejezés';

  @override
  String get wrappedAGreatDay => 'Egy nagyszerű nap';

  @override
  String get wrappedGettingItDone => 'Megcsinálni';

  @override
  String get wrappedAChallenge => 'Egy kihívás';

  @override
  String get wrappedAHilariousMoment => 'Egy vicces pillanat';

  @override
  String get wrappedThatAwkwardMoment => 'Az a kínos pillanat';

  @override
  String get wrappedYouHadFunnyMoments => 'Idén vicces pillanataid voltak!';

  @override
  String get wrappedWeveAllBeenThere => 'Mindannyian voltunk már ott!';

  @override
  String get wrappedFriend => 'Barát';

  @override
  String get wrappedYourBuddy => 'A haverod!';

  @override
  String get wrappedNotMentioned => 'Nem említve';

  @override
  String get wrappedTheHardPart => 'A nehéz rész';

  @override
  String get wrappedPersonalGrowth => 'Személyes fejlődés';

  @override
  String get wrappedFunDay => 'Szórakoztató';

  @override
  String get wrappedProductiveDay => 'Produktív';

  @override
  String get wrappedIntenseDay => 'Intenzív';

  @override
  String get wrappedFunnyMomentTitle => 'Vicces pillanat';

  @override
  String get wrappedCringeMomentTitle => 'Kínos pillanat';

  @override
  String get wrappedYouTalkedAboutBadge => 'Erről beszéltél';

  @override
  String get wrappedCompletedLabel => 'Befejezve';

  @override
  String get wrappedMyBuddiesCard => 'Barátaim';

  @override
  String get wrappedBuddiesLabel => 'BARÁTOK';

  @override
  String get wrappedObsessionsLabelUpper => 'MEGSZÁLLOTTSÁGOK';

  @override
  String get wrappedStruggleLabelUpper => 'KÜZDELEM';

  @override
  String get wrappedWinLabelUpper => 'GYŐZELEM';

  @override
  String get wrappedTopPhrasesLabelUpper => 'TOP KIFEJEZÉSEK';

  @override
  String get wrappedYourHeader => 'A te';

  @override
  String get wrappedTopDaysHeader => 'Legjobb napjaid';

  @override
  String get wrappedYourTopDaysBadge => 'A legjobb napjaid';

  @override
  String get wrappedBestHeader => 'Legjobb';

  @override
  String get wrappedMomentsHeader => 'Pillanatok';

  @override
  String get wrappedBestMomentsBadge => 'Legjobb pillanatok';

  @override
  String get wrappedBiggestHeader => 'Legnagyobb';

  @override
  String get wrappedStruggleHeader => 'Küzdelem';

  @override
  String get wrappedWinHeader => 'Győzelem';

  @override
  String get wrappedButYouPushedThroughEmoji => 'De sikerült 💪';

  @override
  String get wrappedYouDidItEmoji => 'Megcsináltad! 🎉';

  @override
  String get wrappedHours => 'óra';

  @override
  String get wrappedActions => 'művelet';

  @override
  String get multipleSpeakersDetected => 'Több beszélő észlelve';

  @override
  String get multipleSpeakersDescription =>
      'Úgy tűnik, hogy több beszélő van a felvételen. Győződjön meg róla, hogy csendes helyen van, és próbálja újra.';

  @override
  String get invalidRecordingDetected => 'Érvénytelen felvétel észlelve';

  @override
  String get notEnoughSpeechDescription => 'Nem észleltünk elég beszédet. Kérjük, beszéljen többet és próbálja újra.';

  @override
  String get speechDurationDescription =>
      'Győződjön meg róla, hogy legalább 5 másodpercig és legfeljebb 90 másodpercig beszél.';

  @override
  String get connectionLostDescription =>
      'A kapcsolat megszakadt. Kérjük, ellenőrizze az internetkapcsolatát és próbálja újra.';

  @override
  String get howToTakeGoodSample => 'Hogyan készítsünk jó mintát?';

  @override
  String get goodSampleInstructions =>
      '1. Győződjön meg róla, hogy csendes helyen van.\n2. Beszéljen tisztán és természetesen.\n3. Győződjön meg róla, hogy készüléke természetes helyzetben van a nyakán.\n\nHa elkészült, mindig javíthatja vagy újra elkészítheti.';

  @override
  String get noDeviceConnectedUseMic => 'Nincs csatlakoztatott eszköz. A telefon mikrofonját használjuk.';

  @override
  String get doItAgain => 'Csináld újra';

  @override
  String get listenToSpeechProfile => 'Hallgasd meg a hangprofilomat ➡️';

  @override
  String get recognizingOthers => 'Mások felismerése 👀';

  @override
  String get keepGoingGreat => 'Csak így tovább, remekül megy';

  @override
  String get somethingWentWrongTryAgain => 'Valami hiba történt! Kérjük, próbálja újra később.';

  @override
  String get uploadingVoiceProfile => 'Hangprofil feltöltése....';

  @override
  String get memorizingYourVoice => 'Hangja megjegyzése...';

  @override
  String get personalizingExperience => 'Élményének személyre szabása...';

  @override
  String get keepSpeakingUntil100 => 'Beszéljen tovább, amíg el nem éri a 100%-ot.';

  @override
  String get greatJobAlmostThere => 'Remek munka, már majdnem kész';

  @override
  String get soCloseJustLittleMore => 'Olyan közel, már csak egy kicsit';

  @override
  String get notificationFrequency => 'Értesítések gyakorisága';

  @override
  String get controlNotificationFrequency => 'Szabályozza, milyen gyakran küld Önnek proaktív értesítéseket az Omi.';

  @override
  String get yourScore => 'Az Ön pontszáma';

  @override
  String get dailyScoreBreakdown => 'Napi pontszám részletei';

  @override
  String get todaysScore => 'Mai pontszám';

  @override
  String get tasksCompleted => 'Befejezett feladatok';

  @override
  String get completionRate => 'Befejezési arány';

  @override
  String get howItWorks => 'Hogyan működik';

  @override
  String get dailyScoreExplanation =>
      'A napi pontszáma a feladatok befejezésén alapul. Fejezze be feladatait a pontszám javításához!';

  @override
  String get notificationFrequencyDescription =>
      'Szabályozd, milyen gyakran küld az Omi proaktív értesítéseket és emlékeztetőket.';

  @override
  String get sliderOff => 'Ki';

  @override
  String get sliderMax => 'Max.';

  @override
  String summaryGeneratedFor(String date) {
    return 'Összefoglaló elkészült: $date';
  }

  @override
  String get failedToGenerateSummary =>
      'Nem sikerült összefoglalót generálni. Győződj meg róla, hogy vannak beszélgetések arra a napra.';

  @override
  String get recap => 'Összefoglaló';

  @override
  String deleteQuoted(String name) {
    return '\"$name\" törlése';
  }

  @override
  String moveConversationsTo(int count) {
    return '$count beszélgetés áthelyezése ide:';
  }

  @override
  String get noFolder => 'Nincs mappa';

  @override
  String get removeFromAllFolders => 'Eltávolítás az összes mappából';

  @override
  String get buildAndShareYourCustomApp => 'Építsd és oszd meg egyedi alkalmazásod';

  @override
  String get searchAppsPlaceholder => 'Keresés 1500+ alkalmazásban';

  @override
  String get filters => 'Szűrők';

  @override
  String get frequencyOff => 'Ki';

  @override
  String get frequencyMinimal => 'Minimális';

  @override
  String get frequencyLow => 'Alacsony';

  @override
  String get frequencyBalanced => 'Kiegyensúlyozott';

  @override
  String get frequencyHigh => 'Magas';

  @override
  String get frequencyMaximum => 'Maximális';

  @override
  String get frequencyDescOff => 'Nincsenek proaktív értesítések';

  @override
  String get frequencyDescMinimal => 'Csak kritikus emlékeztetők';

  @override
  String get frequencyDescLow => 'Csak fontos frissítések';

  @override
  String get frequencyDescBalanced => 'Rendszeres hasznos emlékeztetők';

  @override
  String get frequencyDescHigh => 'Gyakori ellenőrzések';

  @override
  String get frequencyDescMaximum => 'Maradjon folyamatosan elkötelezett';

  @override
  String get clearChatQuestion => 'Csevegés törlése?';

  @override
  String get syncingMessages => 'Üzenetek szinkronizálása a szerverrel...';

  @override
  String get chatAppsTitle => 'Chat alkalmazások';

  @override
  String get selectApp => 'Alkalmazás kiválasztása';

  @override
  String get noChatAppsEnabled =>
      'Nincs engedélyezett chat alkalmazás.\nKoppintson az \"Alkalmazások engedélyezése\" gombra a hozzáadáshoz.';

  @override
  String get disable => 'Letiltás';

  @override
  String get photoLibrary => 'Fotótár';

  @override
  String get chooseFile => 'Fájl kiválasztása';

  @override
  String get configureAiPersona => 'AI személyiséged konfigurálása';

  @override
  String get connectAiAssistantsToYourData => 'AI asszisztensek csatlakoztatása az adataidhoz';

  @override
  String get oAuth => 'OAuth';

  @override
  String get trackYourGoalsOnHomepage => 'Személyes célok követése a kezdőlapon';

  @override
  String get deleteRecording => 'Felvétel törlése';

  @override
  String get thisCannotBeUndone => 'Ez nem vonható vissza.';

  @override
  String get sdCard => 'SD Card';

  @override
  String get fromSd => 'From SD';

  @override
  String get limitless => 'Limitless';

  @override
  String get fastTransfer => 'Gyors átvitel';

  @override
  String get syncingStatus => 'Szinkronizálás';

  @override
  String get failedStatus => 'Sikertelen';

  @override
  String etaLabel(String time) {
    return 'ETA: $time';
  }

  @override
  String get transferMethod => 'Átviteli módszer';

  @override
  String get fast => 'Fast';

  @override
  String get ble => 'BLE';

  @override
  String get phone => 'Phone';

  @override
  String get cancelSync => 'Szinkronizálás megszakítása';

  @override
  String get cancelSyncMessage => 'A már letöltött adatok mentésre kerülnek. Később folytathatod.';

  @override
  String get syncCancelled => 'Szinkronizálás megszakítva';

  @override
  String get deleteProcessedFiles => 'Feldolgozott fájlok törlése';

  @override
  String get processedFilesDeleted => 'Processed files deleted';

  @override
  String get wifiEnableFailed => 'A WiFi engedélyezése sikertelen az eszközön. Kérlek, próbáld újra.';

  @override
  String get deviceNoFastTransfer => 'Az eszközöd nem támogatja a gyors átvitelt. Használd inkább a Bluetooth-t.';

  @override
  String get enableHotspotMessage => 'Kérlek, engedélyezd a telefonod hotspotját, és próbáld újra.';

  @override
  String get transferStartFailed => 'Az átvitel indítása sikertelen. Kérlek, próbáld újra.';

  @override
  String get deviceNotResponding => 'Az eszköz nem válaszol. Kérlek, próbáld újra.';

  @override
  String get invalidWifiCredentials => 'Érvénytelen WiFi hitelesítő adatok. Ellenőrizd a hotspot beállításokat.';

  @override
  String get wifiConnectionFailed => 'WiFi kapcsolódás sikertelen. Kérlek, próbáld újra.';

  @override
  String get sdCardProcessing => 'SD Card Processing';

  @override
  String sdCardProcessingMessage(int count) {
    return '$count felvétel feldolgozása. A fájlok törlésre kerülnek az SD kártyáról utána.';
  }

  @override
  String get process => 'Process';

  @override
  String get wifiSyncFailed => 'WiFi szinkronizálás sikertelen';

  @override
  String get processingFailed => 'Feldolgozás sikertelen';

  @override
  String get downloadingFromSdCard => 'Letöltés az SD kártyáról';

  @override
  String processingProgress(int current, int total) {
    return 'Feldolgozás $current/$total';
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
  String get noRecordings => 'Nincsenek felvételek';

  @override
  String get audioFromOmiWillAppearHere => 'Az Omi eszközödről származó hanganyag itt fog megjelenni';

  @override
  String get deleteProcessed => 'Feldolgozottak törlése';

  @override
  String get tryDifferentFilter => 'Try a different filter';

  @override
  String get recordings => 'Felvételek';

  @override
  String get enableRemindersAccess =>
      'Kérjük, engedélyezze az Emlékeztetők hozzáférést a Beállításokban az Apple Emlékeztetők használatához';

  @override
  String todayAtTime(String time) {
    return 'Ma $time-kor';
  }

  @override
  String yesterdayAtTime(String time) {
    return 'Tegnap $time-kor';
  }

  @override
  String get lessThanAMinute => 'Kevesebb mint egy perc';

  @override
  String estimatedMinutes(int count) {
    return '~$count perc';
  }

  @override
  String estimatedHours(int count) {
    return '~$count óra';
  }

  @override
  String estimatedTimeRemaining(String time) {
    return 'Becsült: $time hátralévő';
  }

  @override
  String get summarizingConversation => 'Beszélgetés összefoglalása...\nEz néhány másodpercig tarthat';

  @override
  String get resummarizingConversation => 'Beszélgetés újraösszefoglalása...\nEz néhány másodpercig tarthat';

  @override
  String get nothingInterestingRetry => 'Nem találtunk semmi érdekeset,\nszeretnéd újra próbálni?';

  @override
  String get noSummaryForConversation => 'Nincs elérhető összefoglaló\nehhez a beszélgetéshez.';

  @override
  String get unknownLocation => 'Ismeretlen hely';

  @override
  String get couldNotLoadMap => 'A térkép nem tölthető be';

  @override
  String get triggerConversationIntegration => 'Beszélgetés-létrehozási integráció indítása';

  @override
  String get webhookUrlNotSet => 'Webhook URL nincs beállítva';

  @override
  String get setWebhookUrlInSettings => 'Kérjük, állítsd be a webhook URL-t a fejlesztői beállításokban.';

  @override
  String get sendWebUrl => 'Web URL küldése';

  @override
  String get sendTranscript => 'Átirat küldése';

  @override
  String get sendSummary => 'Összefoglaló küldése';

  @override
  String get debugModeDetected => 'Hibakeresési mód észlelve';

  @override
  String get performanceReduced => 'A teljesítmény csökkenhet';

  @override
  String autoClosingInSeconds(int seconds) {
    return 'Automatikus bezárás $seconds másodperc múlva';
  }

  @override
  String get modelRequired => 'Modell szükséges';

  @override
  String get downloadWhisperModel => 'Tölts le egy whisper modellt az eszközön történő átírás használatához';

  @override
  String get deviceNotCompatible => 'Az eszközöd nem kompatibilis az eszközön történő átírással';

  @override
  String get deviceRequirements => 'Készüléke nem felel meg az eszközön történő átírás követelményeinek.';

  @override
  String get willLikelyCrash => 'Az engedélyezés valószínűleg az alkalmazás összeomlását vagy lefagyását okozza.';

  @override
  String get transcriptionSlowerLessAccurate => 'Az átírás jelentősen lassabb és kevésbé pontos lesz.';

  @override
  String get proceedAnyway => 'Folytatás mindenképp';

  @override
  String get olderDeviceDetected => 'Régebbi eszköz észlelve';

  @override
  String get onDeviceSlower => 'Az eszközön történő átírás lassabb lehet ezen a készüléken.';

  @override
  String get batteryUsageHigher => 'Az akkumulátorhasználat magasabb lesz, mint a felhő átírás esetén.';

  @override
  String get considerOmiCloud => 'Fontold meg az Omi Cloud használatát a jobb teljesítmény érdekében.';

  @override
  String get highResourceUsage => 'Magas erőforrás-használat';

  @override
  String get onDeviceIntensive => 'Az eszközön történő átírás nagy számítási kapacitást igényel.';

  @override
  String get batteryDrainIncrease => 'Az akkumulátor-fogyasztás jelentősen megnő.';

  @override
  String get deviceMayWarmUp => 'Az eszköz felmelegedhet hosszabb használat során.';

  @override
  String get speedAccuracyLower => 'A sebesség és pontosság alacsonyabb lehet, mint a felhőmodellekkel.';

  @override
  String get cloudProvider => 'Felhő szolgáltató';

  @override
  String get premiumMinutesInfo => '1200 prémium perc/hónap. Az Eszközön fül korlátlan ingyenes átírást kínál.';

  @override
  String get viewUsage => 'Használat megtekintése';

  @override
  String get localProcessingInfo =>
      'A hang helyben kerül feldolgozásra. Offline működik, több adatvédelmet biztosít, de több akkumulátort fogyaszt.';

  @override
  String get model => 'Modell';

  @override
  String get performanceWarning => 'Teljesítmény figyelmeztetés';

  @override
  String get largeModelWarning =>
      'Ez a modell nagy méretű, és mobileszközökön összeomolhat az alkalmazás, vagy nagyon lassan futhat.\n\nA \"small\" vagy \"base\" ajánlott.';

  @override
  String get usingNativeIosSpeech => 'Natív iOS beszédfelismerés használata';

  @override
  String get noModelDownloadRequired =>
      'Készüléke natív beszédfelismerő motorja lesz használva. Nincs szükség modell letöltésére.';

  @override
  String get modelReady => 'Modell kész';

  @override
  String get redownload => 'Újratöltés';

  @override
  String get doNotCloseApp => 'Kérjük, ne zárd be az alkalmazást.';

  @override
  String get downloading => 'Letöltés...';

  @override
  String get downloadModel => 'Modell letöltése';

  @override
  String estimatedSize(String size) {
    return 'Becsült méret: ~$size MB';
  }

  @override
  String availableSpace(String space) {
    return 'Szabad hely: $space';
  }

  @override
  String get notEnoughSpace => 'Figyelmeztetés: Nincs elég hely!';

  @override
  String get download => 'Letöltés';

  @override
  String downloadError(String error) {
    return 'Letöltési hiba: $error';
  }

  @override
  String get cancelled => 'Megszakítva';

  @override
  String get deviceNotCompatibleTitle => 'Eszköz nem kompatibilis';

  @override
  String get deviceNotMeetRequirements => 'Az eszközöd nem felel meg az eszközön történő átírás követelményeinek.';

  @override
  String get transcriptionSlowerOnDevice => 'Az eszközön történő átírás lassabb lehet ezen az eszközön.';

  @override
  String get computationallyIntensive => 'Az eszközön történő átírás számításigényes.';

  @override
  String get batteryDrainSignificantly => 'Az akkumulátor-lemerülés jelentősen növekedni fog.';

  @override
  String get premiumMinutesMonth => '1200 prémium perc/hónap. Az Eszközön fül korlátlan ingyenes átírást kínál. ';

  @override
  String get audioProcessedLocally =>
      'A hang helyileg kerül feldolgozásra. Offline működik, privátabb, de több akkumulátort használ.';

  @override
  String get languageLabel => 'Nyelv';

  @override
  String get modelLabel => 'Modell';

  @override
  String get modelTooLargeWarning =>
      'Ez a modell nagy, és az alkalmazás összeomlását vagy nagyon lassú működését okozhatja mobileszközökön.\n\nA small vagy base ajánlott.';

  @override
  String get nativeEngineNoDownload =>
      'Az eszközöd natív beszédmotorja lesz használva. Nem szükséges modell letöltése.';

  @override
  String modelReadyWithName(String model) {
    return 'Modell kész ($model)';
  }

  @override
  String get reDownload => 'Újra letöltés';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return '$model letöltése: $received / $total MB';
  }

  @override
  String preparingModel(String model) {
    return '$model előkészítése...';
  }

  @override
  String downloadErrorWithMessage(String error) {
    return 'Letöltési hiba: $error';
  }

  @override
  String estimatedSizeWithValue(String size) {
    return 'Becsült méret: ~$size MB';
  }

  @override
  String availableSpaceWithValue(String space) {
    return 'Elérhető hely: $space';
  }

  @override
  String get omiTranscriptionOptimized =>
      'Az Omi beépített élő átírása valós idejű beszélgetésekre van optimalizálva automatikus beszélő-felismeréssel és diarizációval.';

  @override
  String get reset => 'Visszaállítás';

  @override
  String get useTemplateFrom => 'Sablon használata innen';

  @override
  String get selectProviderTemplate => 'Szolgáltató sablon kiválasztása...';

  @override
  String get quicklyPopulateResponse => 'Gyors kitöltés ismert szolgáltató válaszformátummal';

  @override
  String get quicklyPopulateRequest => 'Gyors kitöltés ismert szolgáltató kérésformátummal';

  @override
  String get invalidJsonError => 'Érvénytelen JSON';

  @override
  String downloadModelWithName(String model) {
    return 'Modell letöltése ($model)';
  }

  @override
  String modelNameWithFile(String model) {
    return 'Modell: $model';
  }

  @override
  String get device => 'Eszköz';

  @override
  String get chatAssistantsTitle => 'Chat asszisztensek';

  @override
  String get permissionReadConversations => 'Beszélgetések olvasása';

  @override
  String get permissionReadMemories => 'Emlékek olvasása';

  @override
  String get permissionReadTasks => 'Feladatok olvasása';

  @override
  String get permissionCreateConversations => 'Beszélgetések létrehozása';

  @override
  String get permissionCreateMemories => 'Emlékek létrehozása';

  @override
  String get permissionTypeAccess => 'Hozzáférés';

  @override
  String get permissionTypeCreate => 'Létrehozás';

  @override
  String get permissionTypeTrigger => 'Indító';

  @override
  String get permissionDescReadConversations => 'Ez az alkalmazás hozzáférhet a beszélgetéseidhez.';

  @override
  String get permissionDescReadMemories => 'Ez az alkalmazás hozzáférhet az emlékeidhez.';

  @override
  String get permissionDescReadTasks => 'Ez az alkalmazás hozzáférhet a feladataidhoz.';

  @override
  String get permissionDescCreateConversations => 'Ez az alkalmazás új beszélgetéseket hozhat létre.';

  @override
  String get permissionDescCreateMemories => 'Ez az alkalmazás új emlékeket hozhat létre.';

  @override
  String get realtimeListening => 'Valós idejű hallgatás';

  @override
  String get setupCompleted => 'Befejezve';

  @override
  String get pleaseSelectRating => 'Kérlek válassz értékelést';

  @override
  String get writeReviewOptional => 'Írj véleményt (opcionális)';

  @override
  String get setupQuestionsIntro => 'Segíts nekünk fejleszteni az Omit néhány kérdés megválaszolásával.  🫶 💜';

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
  String get professionEntrepreneur => 'Vállalkozó';

  @override
  String get professionSoftwareEngineer => 'Szoftverfejlesztő';

  @override
  String get professionProductManager => 'Termékmenedzser';

  @override
  String get professionExecutive => 'Vezető';

  @override
  String get professionSales => 'Értékesítő';

  @override
  String get professionStudent => 'Diák';

  @override
  String get usageAtWork => 'Munkahelyen';

  @override
  String get usageIrlEvents => 'IRL Events';

  @override
  String get usageOnline => 'Online';

  @override
  String get usageSocialSettings => 'In Social Settings';

  @override
  String get usageEverywhere => 'Everywhere';

  @override
  String get customBackendUrlTitle => 'Egyéni háttérszerver URL';

  @override
  String get backendUrlLabel => 'Háttérszerver URL';

  @override
  String get saveUrlButton => 'URL mentése';

  @override
  String get enterBackendUrlError => 'Kérjük, adja meg a háttérszerver URL-jét';

  @override
  String get urlMustEndWithSlashError => 'Az URL-nek \"/\" karakterrel kell végződnie';

  @override
  String get invalidUrlError => 'Kérjük, adjon meg érvényes URL-t';

  @override
  String get backendUrlSavedSuccess => 'Háttérszerver URL sikeresen mentve!';

  @override
  String get signInTitle => 'Bejelentkezés';

  @override
  String get signInButton => 'Bejelentkezés';

  @override
  String get enterEmailError => 'Kérjük, adja meg e-mail címét';

  @override
  String get invalidEmailError => 'Kérjük, adjon meg érvényes e-mail címet';

  @override
  String get enterPasswordError => 'Kérjük, adja meg jelszavát';

  @override
  String get passwordMinLengthError => 'A jelszónak legalább 8 karakternek kell lennie';

  @override
  String get signInSuccess => 'Sikeres bejelentkezés!';

  @override
  String get alreadyHaveAccountLogin => 'Már van fiókja? Jelentkezzen be';

  @override
  String get emailLabel => 'E-mail';

  @override
  String get passwordLabel => 'Jelszó';

  @override
  String get createAccountTitle => 'Fiók létrehozása';

  @override
  String get nameLabel => 'Név';

  @override
  String get repeatPasswordLabel => 'Jelszó ismétlése';

  @override
  String get signUpButton => 'Regisztráció';

  @override
  String get enterNameError => 'Kérjük, adja meg nevét';

  @override
  String get passwordsDoNotMatch => 'A jelszavak nem egyeznek';

  @override
  String get signUpSuccess => 'Sikeres regisztráció!';

  @override
  String get loadingKnowledgeGraph => 'Tudásgráf betöltése...';

  @override
  String get noKnowledgeGraphYet => 'Még nincs tudásgráf';

  @override
  String get buildingKnowledgeGraphFromMemories => 'Tudásgráf építése az emlékekből...';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'A tudásgráfja automatikusan felépül, amikor új emlékeket hoz létre.';

  @override
  String get buildGraphButton => 'Gráf építése';

  @override
  String get checkOutMyMemoryGraph => 'Nézd meg a memória gráfomat!';

  @override
  String get getButton => 'Letöltés';

  @override
  String openingApp(String appName) {
    return '$appName megnyitása...';
  }

  @override
  String get writeSomething => 'Írjon valamit';

  @override
  String get submitReply => 'Válasz küldése';

  @override
  String get editYourReply => 'Válasz szerkesztése';

  @override
  String get replyToReview => 'Válasz az értékelésre';

  @override
  String get rateAndReviewThisApp => 'Értékeld és írd meg véleményed erről az alkalmazásról';

  @override
  String get noChangesInReview => 'Nincs változás az értékelésben a frissítéshez.';

  @override
  String get cantRateWithoutInternet => 'Nem lehet értékelni internetkapcsolat nélkül.';

  @override
  String get appAnalytics => 'Alkalmazás elemzés';

  @override
  String get learnMoreLink => 'tudj meg többet';

  @override
  String get moneyEarned => 'Keresett pénz';

  @override
  String get writeYourReply => 'Írja meg válaszát...';

  @override
  String get replySentSuccessfully => 'Válasz sikeresen elküldve';

  @override
  String failedToSendReply(String error) {
    return 'Nem sikerült elküldeni a választ: $error';
  }

  @override
  String get send => 'Küldés';

  @override
  String starFilter(int count) {
    return '$count csillag';
  }

  @override
  String get noReviewsFound => 'Nem találhatók értékelések';

  @override
  String get editReply => 'Válasz szerkesztése';

  @override
  String get reply => 'Válasz';

  @override
  String starFilterLabel(int count) {
    return '$count csillag';
  }

  @override
  String get sharePublicLink => 'Share Public Link';

  @override
  String get makePersonaPublic => 'Make Persona Public';

  @override
  String get connectedKnowledgeData => 'Csatlakoztatott tudásadatok';

  @override
  String get enterName => 'Név megadása';

  @override
  String get disconnectTwitter => 'Twitter leválasztása';

  @override
  String get disconnectTwitterConfirmation =>
      'Biztosan le szeretnéd választani a Twitter fiókodat? A személyiséged többé nem fér hozzá a Twitter adataidhoz.';

  @override
  String get getOmiDeviceDescription => 'Hozz létre pontosabb klónt a személyes beszélgetéseiddel';

  @override
  String get getOmi => 'Omi beszerzése';

  @override
  String get iHaveOmiDevice => 'I have Omi device';

  @override
  String get goal => 'CÉL';

  @override
  String get tapToTrackThisGoal => 'Érintse meg a cél követéséhez';

  @override
  String get tapToSetAGoal => 'Érintse meg egy cél beállításához';

  @override
  String get processedConversations => 'Feldolgozott beszélgetések';

  @override
  String get updatedConversations => 'Frissített beszélgetések';

  @override
  String get newConversations => 'Új beszélgetések';

  @override
  String get summaryTemplate => 'Összefoglaló sablon';

  @override
  String get suggestedTemplates => 'Javasolt sablonok';

  @override
  String get otherTemplates => 'Egyéb sablonok';

  @override
  String get availableTemplates => 'Elérhető sablonok';

  @override
  String get getCreative => 'Légy kreatív';

  @override
  String get defaultLabel => 'Alapértelmezett';

  @override
  String get lastUsedLabel => 'Utoljára használt';

  @override
  String get setDefaultApp => 'Alapértelmezett alkalmazás beállítása';

  @override
  String setDefaultAppContent(String appName) {
    return 'Beállítja a(z) $appName alkalmazást alapértelmezett összefoglaló alkalmazásként?\\n\\nEz az alkalmazás automatikusan használva lesz minden jövőbeli beszélgetés összefoglalásához.';
  }

  @override
  String get setDefaultButton => 'Beállítás alapértelmezettként';

  @override
  String setAsDefaultSuccess(String appName) {
    return 'A(z) $appName beállítva alapértelmezett összefoglaló alkalmazásként';
  }

  @override
  String get createCustomTemplate => 'Egyéni sablon létrehozása';

  @override
  String get allTemplates => 'Összes sablon';

  @override
  String failedToInstallApp(String appName) {
    return 'A(z) $appName telepítése sikertelen. Kérjük, próbálja újra.';
  }

  @override
  String errorInstallingApp(String appName, String error) {
    return 'Hiba a(z) $appName telepítésekor: $error';
  }

  @override
  String tagSpeaker(int speakerId) {
    return 'Beszélő címkézése $speakerId';
  }

  @override
  String get personNameAlreadyExists => 'A person with this name already exists.';

  @override
  String get selectYouFromList => 'To tag yourself, please select \"You\" from the list.';

  @override
  String get enterPersonsName => 'Személy nevének megadása';

  @override
  String get addPerson => 'Add Person';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'Más szegmensek címkézése ettől a beszélőtől ($selected/$total)';
  }

  @override
  String get tagOtherSegments => 'Más szegmensek címkézése';

  @override
  String get managePeople => 'Személyek kezelése';

  @override
  String get shareViaSms => 'Megosztás SMS-ben';

  @override
  String get selectContactsToShareSummary => 'Válasszon névjegyeket a beszélgetés összefoglalójának megosztásához';

  @override
  String get searchContactsHint => 'Névjegyek keresése...';

  @override
  String contactsSelectedCount(int count) {
    return '$count kiválasztva';
  }

  @override
  String get clearAllSelection => 'Összes törlése';

  @override
  String get selectContactsToShare => 'Válasszon névjegyeket a megosztáshoz';

  @override
  String shareWithContactCount(int count) {
    return 'Megosztás $count névjeggyel';
  }

  @override
  String shareWithContactsCount(int count) {
    return 'Megosztás $count névjeggyel';
  }

  @override
  String get contactsPermissionRequired => 'Névjegyengedély szükséges';

  @override
  String get contactsPermissionRequiredForSms => 'Az SMS-ben való megosztáshoz névjegyengedély szükséges';

  @override
  String get grantContactsPermissionForSms => 'Kérjük, adja meg a névjegyengedélyt az SMS-ben való megosztáshoz';

  @override
  String get noContactsWithPhoneNumbers => 'Nem találhatók telefonszámmal rendelkező névjegyek';

  @override
  String get noContactsMatchSearch => 'Nincs a keresésnek megfelelő névjegy';

  @override
  String get failedToLoadContacts => 'A névjegyek betöltése sikertelen';

  @override
  String get failedToPrepareConversationForSharing =>
      'A beszélgetés előkészítése a megosztáshoz sikertelen. Kérjük, próbálja újra.';

  @override
  String get couldNotOpenSmsApp => 'Az SMS alkalmazás nem nyitható meg. Kérjük, próbálja újra.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'Íme, amiről épp beszéltünk: $link';
  }

  @override
  String get wifiSync => 'WiFi szinkronizálás';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item másolva a vágólapra';
  }

  @override
  String get wifiConnectionFailedTitle => 'Kapcsolódás sikertelen';

  @override
  String connectingToDeviceName(String deviceName) {
    return 'Csatlakozás a következőhöz: $deviceName';
  }

  @override
  String enableDeviceWifi(String deviceName) {
    return '$deviceName WiFi engedélyezése';
  }

  @override
  String connectToDeviceName(String deviceName) {
    return 'Csatlakozás a következőhöz: $deviceName';
  }

  @override
  String get recordingDetails => 'Felvétel részletei';

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
    return 'Tárolva: $deviceName';
  }

  @override
  String get transferring => 'Átvitel folyamatban...';

  @override
  String get transferRequired => 'Átvitel szükséges';

  @override
  String get downloadingAudioFromSdCard => 'Hanganyag letöltése az eszközöd SD kártyájáról';

  @override
  String get transferRequiredDescription =>
      'Ez a felvétel az eszközöd SD kártyáján van tárolva. Vidd át a telefonodra a lejátszáshoz vagy megosztáshoz.';

  @override
  String get cancelTransfer => 'Átvitel megszakítása';

  @override
  String get transferToPhone => 'Átvitel telefonra';

  @override
  String get privateAndSecureOnDevice => 'Privát és biztonságos az eszközödön';

  @override
  String get recordingInfo => 'Felvétel információ';

  @override
  String get transferInProgress => 'Átvitel folyamatban...';

  @override
  String get shareRecording => 'Share Recording';

  @override
  String get deleteRecordingConfirmation =>
      'Biztosan véglegesen törölni szeretnéd ezt a felvételt? Ez nem vonható vissza.';

  @override
  String get recordingIdLabel => 'Felvétel azonosító';

  @override
  String get dateTimeLabel => 'Date & Time';

  @override
  String get durationLabel => 'Duration';

  @override
  String get audioFormatLabel => 'Hangformátum';

  @override
  String get storageLocationLabel => 'Tárolási hely';

  @override
  String get estimatedSizeLabel => 'Estimated Size';

  @override
  String get deviceModelLabel => 'Eszköz modell';

  @override
  String get deviceIdLabel => 'Eszköz azonosító';

  @override
  String get statusLabel => 'Állapot';

  @override
  String get statusProcessed => 'Processed';

  @override
  String get statusUnprocessed => 'Unprocessed';

  @override
  String get switchedToFastTransfer => 'Átváltás gyors átvitelre';

  @override
  String get transferCompleteMessage => 'Átvitel befejezve! Most már lejátszhatod ezt a felvételt.';

  @override
  String transferFailedMessage(String error) {
    return 'Átvitel sikertelen: $error';
  }

  @override
  String get transferCancelled => 'Átvitel megszakítva';

  @override
  String get fastTransferEnabled => 'Gyors átvitel engedélyezve';

  @override
  String get bluetoothSyncEnabled => 'Bluetooth szinkronizálás engedélyezve';

  @override
  String get enableFastTransfer => 'Gyors átvitel engedélyezése';

  @override
  String get fastTransferDescription =>
      'A gyors átvitel WiFi-t használ ~5x gyorsabb sebességekhez. A telefonja ideiglenesen csatlakozik az Omi eszköz WiFi hálózatához az átvitel során.';

  @override
  String get internetAccessPausedDuringTransfer => 'Az internetelérés szünetel az átvitel alatt';

  @override
  String get chooseTransferMethodDescription =>
      'Válassza ki, hogyan kerüljenek át a felvételek az Omi eszközről a telefonjára.';

  @override
  String get wifiSpeed => '~150 KB/s WiFi-n keresztül';

  @override
  String get fiveTimesFaster => '5X GYORSABB';

  @override
  String get fastTransferMethodDescription =>
      'Közvetlen WiFi kapcsolatot hoz létre az Omi eszközével. A telefonja ideiglenesen lecsatlakozik a szokásos WiFi-ről az átvitel alatt.';

  @override
  String get bluetooth => 'Bluetooth';

  @override
  String get bleSpeed => '~30 KB/s BLE-n keresztül';

  @override
  String get bluetoothMethodDescription =>
      'Szabványos Bluetooth Low Energy kapcsolatot használ. Lassabb, de nem befolyásolja a WiFi kapcsolatot.';

  @override
  String get selected => 'Kiválasztva';

  @override
  String get selectOption => 'Kiválasztás';

  @override
  String get lowBatteryAlertTitle => 'Alacsony akkumulátor figyelmeztetés';

  @override
  String get lowBatteryAlertBody => 'Az eszköz akkumulátora alacsony. Ideje feltölteni! 🔋';

  @override
  String get deviceDisconnectedNotificationTitle => 'Az Omi eszköz lecsatlakozott';

  @override
  String get deviceDisconnectedNotificationBody => 'Kérjük, csatlakozzon újra az Omi használatának folytatásához.';

  @override
  String get firmwareUpdateAvailable => 'Firmware frissítés elérhető';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'Új firmware frissítés ($version) érhető el az Omi eszközéhez. Szeretné most frissíteni?';
  }

  @override
  String get later => 'Később';

  @override
  String get appDeletedSuccessfully => 'Az alkalmazás sikeresen törölve';

  @override
  String get appDeleteFailed => 'Nem sikerült törölni az alkalmazást. Kérjük, próbáld újra később.';

  @override
  String get appVisibilityChangedSuccessfully =>
      'Az alkalmazás láthatósága sikeresen megváltozott. Néhány percig eltarthat, amíg érvénybe lép.';

  @override
  String get errorActivatingAppIntegration =>
      'Hiba az alkalmazás aktiválásakor. Ha integrációs alkalmazásról van szó, győződj meg róla, hogy a beállítás befejeződött.';

  @override
  String get errorUpdatingAppStatus => 'Hiba történt az alkalmazás állapotának frissítése közben.';

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
  String get analyzingYourData => 'Adataid elemzése...';

  @override
  String migratingToProtection(String level) {
    return 'Migrating to $level protection...';
  }

  @override
  String get noDataToMigrateFinalizing => 'Nincs áttelepítendő adat. Befejezés...';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return 'Migrating $itemType... $percentage%';
  }

  @override
  String get allObjectsMigratedFinalizing => 'All objects migrated. Finalizing...';

  @override
  String get migrationErrorOccurred => 'Hiba történt az áttelepítés során. Kérlek, próbáld újra.';

  @override
  String get migrationComplete => 'Áttelepítés befejezve!';

  @override
  String dataProtectedWithSettings(String level) {
    return 'Az adataid mostantól védettek az új $level beállításokkal.';
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
  String get importantConversationTitle => 'Fontos beszélgetés';

  @override
  String get importantConversationBody =>
      'Most volt egy fontos beszélgetésed. Érintsd meg az összefoglaló megosztásához.';

  @override
  String get templateName => 'Sablon neve';

  @override
  String get templateNameHint => 'pl. Értekezlet tennivalók kinyerő';

  @override
  String get nameMustBeAtLeast3Characters => 'A névnek legalább 3 karakterből kell állnia';

  @override
  String get conversationPromptHint =>
      'pl. Nyerje ki a feladatpontokat, döntéseket és fő tanulságokat a beszélgetésből.';

  @override
  String get pleaseEnterAppPrompt => 'Kérjük, adjon meg egy promptot az alkalmazásához';

  @override
  String get promptMustBeAtLeast10Characters => 'A promptnak legalább 10 karakterből kell állnia';

  @override
  String get anyoneCanDiscoverTemplate => 'Bárki felfedezheti a sablonját';

  @override
  String get onlyYouCanUseTemplate => 'Csak Ön használhatja ezt a sablont';

  @override
  String get generatingDescription => 'Leírás generálása...';

  @override
  String get creatingAppIcon => 'Alkalmazás ikon létrehozása...';

  @override
  String get installingApp => 'Alkalmazás telepítése...';

  @override
  String get appCreatedAndInstalled => 'Alkalmazás létrehozva és telepítve!';

  @override
  String get appCreatedSuccessfully => 'Alkalmazás sikeresen létrehozva!';

  @override
  String get failedToCreateApp => 'Nem sikerült létrehozni az alkalmazást. Kérjük, próbálja újra.';

  @override
  String get addAppSelectCoreCapability => 'Válasszon még egy alapvető képességet az alkalmazásához';

  @override
  String get addAppSelectPaymentPlan => 'Válasszon fizetési tervet és adjon meg árat az alkalmazáshoz';

  @override
  String get addAppSelectCapability => 'Válasszon legalább egy képességet az alkalmazásához';

  @override
  String get addAppSelectLogo => 'Válasszon logót az alkalmazásához';

  @override
  String get addAppEnterChatPrompt => 'Adjon meg chat promptot az alkalmazásához';

  @override
  String get addAppEnterConversationPrompt => 'Adjon meg beszélgetés promptot az alkalmazásához';

  @override
  String get addAppSelectTriggerEvent => 'Válasszon kiváltó eseményt az alkalmazásához';

  @override
  String get addAppEnterWebhookUrl => 'Adjon meg webhook URL-t az alkalmazásához';

  @override
  String get addAppSelectCategory => 'Válasszon kategóriát az alkalmazásához';

  @override
  String get addAppFillRequiredFields => 'Töltse ki helyesen az összes kötelező mezőt';

  @override
  String get addAppUpdatedSuccess => 'Alkalmazás sikeresen frissítve 🚀';

  @override
  String get addAppUpdateFailed => 'Frissítés sikertelen. Próbálja később';

  @override
  String get addAppSubmittedSuccess => 'Alkalmazás sikeresen elküldve 🚀';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'Hiba a fájlválasztó megnyitásakor: $message';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'Hiba a kép kiválasztásakor: $error';
  }

  @override
  String get addAppPhotosPermissionDenied => 'Fotó engedély megtagadva. Engedélyezze a fotó hozzáférést';

  @override
  String get addAppErrorSelectingImageRetry => 'Hiba a kép kiválasztásakor. Próbálja újra.';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'Hiba a miniatűr kiválasztásakor: $error';
  }

  @override
  String get addAppErrorSelectingThumbnailRetry => 'Hiba a miniatűr kiválasztásakor. Próbálja újra.';

  @override
  String get addAppCapabilityConflictWithPersona => 'Más képességek nem választhatók a Persona mellett';

  @override
  String get addAppPersonaConflictWithCapabilities => 'A Persona nem választható más képességekkel együtt';

  @override
  String get personaTwitterHandleNotFound => 'Twitter fiók nem található';

  @override
  String get personaTwitterHandleSuspended => 'Twitter fiók felfüggesztve';

  @override
  String get personaFailedToVerifyTwitter => 'Twitter fiók ellenőrzése sikertelen';

  @override
  String get personaFailedToFetch => 'Nem sikerült lekérni a personáját';

  @override
  String get personaFailedToCreate => 'Nem sikerült létrehozni a personát';

  @override
  String get personaConnectKnowledgeSource => 'Csatlakoztasson legalább egy adatforrást (Omi vagy Twitter)';

  @override
  String get personaUpdatedSuccessfully => 'Persona sikeresen frissítve';

  @override
  String get personaFailedToUpdate => 'Persona frissítése sikertelen';

  @override
  String get personaPleaseSelectImage => 'Válasszon képet';

  @override
  String get personaFailedToCreateTryLater => 'Persona létrehozása sikertelen. Próbálja később.';

  @override
  String personaFailedToCreateWithError(String error) {
    return 'Persona létrehozása sikertelen: $error';
  }

  @override
  String get personaFailedToEnable => 'Persona engedélyezése sikertelen';

  @override
  String personaErrorEnablingWithError(String error) {
    return 'Hiba a persona engedélyezésekor: $error';
  }

  @override
  String get paymentFailedToFetchCountries => 'Nem sikerült lekérni a támogatott országokat. Próbálja később.';

  @override
  String get paymentFailedToSetDefault => 'Nem sikerült beállítani az alapértelmezett fizetési módot. Próbálja később.';

  @override
  String get paymentFailedToSavePaypal => 'Nem sikerült menteni a PayPal adatokat. Próbálja később.';

  @override
  String get paypalEmailHint => 'nik@example.com';

  @override
  String get paypalMeLinkHint => 'paypal.me/nik';

  @override
  String get paymentMethodStripe => 'Stripe';

  @override
  String get paymentMethodPayPal => 'PayPal';

  @override
  String get paymentStatusActive => 'Aktív';

  @override
  String get paymentStatusConnected => 'Csatlakoztatva';

  @override
  String get paymentStatusNotConnected => 'Nincs csatlakoztatva';

  @override
  String get paymentAppCost => 'Alkalmazás ára';

  @override
  String get paymentEnterValidAmount => 'Adjon meg érvényes összeget';

  @override
  String get paymentEnterAmountGreaterThanZero => 'Adjon meg 0-nál nagyobb összeget';

  @override
  String get paymentPlan => 'Fizetési terv';

  @override
  String get paymentNoneSelected => 'Nincs kiválasztva';

  @override
  String get aiGenPleaseEnterDescription => 'Kérjük, adj meg egy leírást az alkalmazásodhoz';

  @override
  String get aiGenCreatingAppIcon => 'Alkalmazás ikon létrehozása...';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'Hiba történt: $message';
  }

  @override
  String get aiGenAppCreatedSuccessfully => 'Alkalmazás sikeresen létrehozva!';

  @override
  String get aiGenFailedToCreateApp => 'Nem sikerült létrehozni az alkalmazást';

  @override
  String get aiGenErrorWhileCreatingApp => 'Hiba történt az alkalmazás létrehozása közben';

  @override
  String get aiGenFailedToGenerateApp => 'Nem sikerült generálni az alkalmazást. Kérjük, próbáld újra.';

  @override
  String get aiGenFailedToRegenerateIcon => 'Nem sikerült újragenerálni az ikont';

  @override
  String get aiGenPleaseGenerateAppFirst => 'Kérjük, először generálj egy alkalmazást';

  @override
  String get xHandleTitle => 'Mi az X felhasználóneved?';

  @override
  String get xHandleDescription => 'Előzetesen betanítjuk az Omi klónodat\na fiókod tevékenysége alapján';

  @override
  String get xHandleHint => '@nikshevchenko';

  @override
  String get xHandlePleaseEnter => 'Kérlek, add meg az X felhasználóneved';

  @override
  String get xHandlePleaseEnterValid => 'Kérlek, adj meg érvényes X felhasználónevet';

  @override
  String get nextButton => 'Next';

  @override
  String get connectOmiDevice => 'Omi eszköz csatlakoztatása';

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'You\'re switching your Unlimited Plan to the $title. Are you sure you want to proceed?';
  }

  @override
  String get planUpgradeScheduledMessage =>
      'Frissítés ütemezve! A havi csomagod a számlázási időszak végéig folytatódik, majd automatikusan átvált évesre.';

  @override
  String get couldNotSchedulePlanChange => 'A csomagváltás ütemezése sikertelen. Kérlek, próbáld újra.';

  @override
  String get subscriptionReactivatedDefault =>
      'Az előfizetésed újra aktiválva! Most nincs díj - a jelenlegi időszak végén leszel számlázva.';

  @override
  String get subscriptionSuccessfulCharged => 'Sikeres előfizetés! A számlázás megtörtént az új számlázási időszakra.';

  @override
  String get couldNotProcessSubscription => 'Az előfizetés feldolgozása sikertelen. Kérlek, próbáld újra.';

  @override
  String get couldNotLaunchUpgradePage => 'A frissítési oldal megnyitása sikertelen. Kérlek, próbáld újra.';

  @override
  String get transcriptionJsonPlaceholder => 'Illeszd be a JSON konfigurációdat ide...';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get pricePlaceholder => '0.00';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'Hiba a fájlválasztó megnyitásakor: $message';
  }

  @override
  String importErrorGeneric(String error) {
    return 'Hiba: $error';
  }

  @override
  String get mergeConversationsSuccessTitle => 'Beszélgetések sikeresen összevonva';

  @override
  String mergeConversationsSuccessBody(int count) {
    return '$count beszélgetés sikeresen összevonva';
  }

  @override
  String get dailyReflectionNotificationTitle => 'Ideje a napi reflexiónak';

  @override
  String get dailyReflectionNotificationBody => 'Mesélj a napodról';

  @override
  String get actionItemReminderTitle => 'Omi emlékeztető';

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName lecsatlakoztatva';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'Kérjük, csatlakozzon újra a $deviceName további használatához.';
  }

  @override
  String get onboardingSignIn => 'Bejelentkezés';

  @override
  String get onboardingYourName => 'A neved';

  @override
  String get onboardingLanguage => 'Nyelv';

  @override
  String get onboardingPermissions => 'Engedélyek';

  @override
  String get onboardingComplete => 'Kész';

  @override
  String get onboardingWelcomeToOmi => 'Üdvözöl az Omi';

  @override
  String get onboardingTellUsAboutYourself => 'Mesélj magadról';

  @override
  String get onboardingChooseYourPreference => 'Válaszd ki a preferenciádat';

  @override
  String get onboardingGrantRequiredAccess => 'Szükséges hozzáférés megadása';

  @override
  String get onboardingYoureAllSet => 'Készen állsz';

  @override
  String get searchTranscriptOrSummary => 'Keresés az átiratban vagy összefoglalóban...';

  @override
  String get myGoal => 'Célom';

  @override
  String get appNotAvailable => 'Hoppá! Úgy tűnik, a keresett alkalmazás nem érhető el.';

  @override
  String get failedToConnectTodoist => 'Nem sikerült csatlakozni a Todoisthoz';

  @override
  String get failedToConnectAsana => 'Nem sikerült csatlakozni az Asanához';

  @override
  String get failedToConnectGoogleTasks => 'Nem sikerült csatlakozni a Google Taskshoz';

  @override
  String get failedToConnectClickUp => 'Nem sikerült csatlakozni a ClickUphoz';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return 'Nem sikerült csatlakozni a(z) $serviceName szolgáltatáshoz: $error';
  }

  @override
  String get successfullyConnectedTodoist => 'Sikeresen csatlakozva a Todoisthoz!';

  @override
  String get failedToConnectTodoistRetry => 'Nem sikerült csatlakozni a Todoisthoz. Kérjük, próbálja újra.';

  @override
  String get successfullyConnectedAsana => 'Sikeresen csatlakozva az Asanához!';

  @override
  String get failedToConnectAsanaRetry => 'Nem sikerült csatlakozni az Asanához. Kérjük, próbálja újra.';

  @override
  String get successfullyConnectedGoogleTasks => 'Sikeresen csatlakozva a Google Taskshoz!';

  @override
  String get failedToConnectGoogleTasksRetry => 'Nem sikerült csatlakozni a Google Taskshoz. Kérjük, próbálja újra.';

  @override
  String get successfullyConnectedClickUp => 'Sikeresen csatlakozva a ClickUphoz!';

  @override
  String get failedToConnectClickUpRetry => 'Nem sikerült csatlakozni a ClickUphoz. Kérjük, próbálja újra.';

  @override
  String get successfullyConnectedNotion => 'Sikeresen csatlakozva a Notionhöz!';

  @override
  String get failedToRefreshNotionStatus => 'Nem sikerült frissíteni a Notion kapcsolat állapotát.';

  @override
  String get successfullyConnectedGoogle => 'Sikeresen csatlakozva a Google-höz!';

  @override
  String get failedToRefreshGoogleStatus => 'Nem sikerült frissíteni a Google kapcsolat állapotát.';

  @override
  String get successfullyConnectedWhoop => 'Sikeresen csatlakozva a Whoophoz!';

  @override
  String get failedToRefreshWhoopStatus => 'Nem sikerült frissíteni a Whoop kapcsolat állapotát.';

  @override
  String get successfullyConnectedGitHub => 'Sikeresen csatlakozva a GitHubhoz!';

  @override
  String get failedToRefreshGitHubStatus => 'Nem sikerült frissíteni a GitHub kapcsolat állapotát.';

  @override
  String get authFailedToSignInWithGoogle => 'Nem sikerült bejelentkezni a Google-lel, kérjük próbálja újra.';

  @override
  String get authenticationFailed => 'A hitelesítés sikertelen. Kérjük, próbálja újra.';

  @override
  String get authFailedToSignInWithApple => 'Nem sikerült bejelentkezni az Apple-lel, kérjük próbálja újra.';

  @override
  String get authFailedToRetrieveToken => 'Nem sikerült lekérni a Firebase tokent, kérjük próbálja újra.';

  @override
  String get authUnexpectedErrorFirebase => 'Váratlan hiba a bejelentkezés során, Firebase hiba, kérjük próbálja újra.';

  @override
  String get authUnexpectedError => 'Váratlan hiba a bejelentkezés során, kérjük próbálja újra';

  @override
  String get authFailedToLinkGoogle => 'Nem sikerült a Google-lel összekapcsolni, kérjük próbálja újra.';

  @override
  String get authFailedToLinkApple => 'Nem sikerült az Apple-lel összekapcsolni, kérjük próbálja újra.';

  @override
  String get onboardingBluetoothRequired => 'Bluetooth-engedély szükséges az eszközhöz való csatlakozáshoz.';

  @override
  String get onboardingBluetoothDeniedSystemPrefs =>
      'Bluetooth-engedély megtagadva. Kérjük, adja meg az engedélyt a Rendszerbeállításokban.';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'Bluetooth-engedély állapota: $status. Kérjük, ellenőrizze a Rendszerbeállításokat.';
  }

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'Bluetooth-engedély ellenőrzése sikertelen: $error';
  }

  @override
  String get onboardingNotificationDeniedSystemPrefs =>
      'Értesítési engedély megtagadva. Kérjük, adja meg az engedélyt a Rendszerbeállításokban.';

  @override
  String get onboardingNotificationDeniedNotifications =>
      'Értesítési engedély megtagadva. Kérjük, adja meg az engedélyt a Rendszerbeállítások > Értesítések menüpontban.';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return 'Értesítési engedély állapota: $status. Kérjük, ellenőrizze a Rendszerbeállításokat.';
  }

  @override
  String onboardingFailedCheckNotification(String error) {
    return 'Értesítési engedély ellenőrzése sikertelen: $error';
  }

  @override
  String get onboardingLocationGrantInSettings =>
      'Kérjük, adja meg a helymeghatározási engedélyt a Beállítások > Adatvédelem és biztonság > Helyszolgáltatások menüpontban';

  @override
  String get onboardingMicrophoneRequired => 'Mikrofon-engedély szükséges a felvételhez.';

  @override
  String get onboardingMicrophoneDenied =>
      'Mikrofon-engedély megtagadva. Kérjük, adja meg az engedélyt a Rendszerbeállítások > Adatvédelem és biztonság > Mikrofon menüpontban.';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'Mikrofon-engedély állapota: $status. Kérjük, ellenőrizze a Rendszerbeállításokat.';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'Mikrofon-engedély ellenőrzése sikertelen: $error';
  }

  @override
  String get onboardingScreenCaptureRequired => 'Képernyőrögzítési engedély szükséges a rendszerhang rögzítéséhez.';

  @override
  String get onboardingScreenCaptureDenied =>
      'Képernyőrögzítési engedély megtagadva. Kérjük, adja meg az engedélyt a Rendszerbeállítások > Adatvédelem és biztonság > Képernyőfelvétel menüpontban.';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return 'Képernyőrögzítési engedély állapota: $status. Kérjük, ellenőrizze a Rendszerbeállításokat.';
  }

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return 'Képernyőrögzítési engedély ellenőrzése sikertelen: $error';
  }

  @override
  String get onboardingAccessibilityRequired =>
      'Akadálymentesítési engedély szükséges a böngészőtalálkozók észleléséhez.';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'Akadálymentesítési engedély állapota: $status. Kérjük, ellenőrizze a Rendszerbeállításokat.';
  }

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'Akadálymentesítési engedély ellenőrzése sikertelen: $error';
  }

  @override
  String get msgCameraNotAvailable => 'A kamerarögzítés nem érhető el ezen a platformon';

  @override
  String get msgCameraPermissionDenied =>
      'Kamera engedély megtagadva. Kérjük, engedélyezze a kamerához való hozzáférést';

  @override
  String msgCameraAccessError(String error) {
    return 'Hiba a kamera elérésekor: $error';
  }

  @override
  String get msgPhotoError => 'Hiba a fénykép készítésekor. Kérjük, próbálja újra.';

  @override
  String get msgMaxImagesLimit => 'Legfeljebb 4 képet választhat ki';

  @override
  String msgFilePickerError(String error) {
    return 'Hiba a fájlválasztó megnyitásakor: $error';
  }

  @override
  String msgSelectImagesError(String error) {
    return 'Hiba a képek kiválasztásakor: $error';
  }

  @override
  String get msgPhotosPermissionDenied =>
      'Fényképek engedély megtagadva. Kérjük, engedélyezze a fényképekhez való hozzáférést a képek kiválasztásához';

  @override
  String get msgSelectImagesGenericError => 'Hiba a képek kiválasztásakor. Kérjük, próbálja újra.';

  @override
  String get msgMaxFilesLimit => 'Legfeljebb 4 fájlt választhat ki';

  @override
  String msgSelectFilesError(String error) {
    return 'Hiba a fájlok kiválasztásakor: $error';
  }

  @override
  String get msgSelectFilesGenericError => 'Hiba a fájlok kiválasztásakor. Kérjük, próbálja újra.';

  @override
  String get msgUploadFileFailed => 'A fájl feltöltése sikertelen, kérjük próbálja újra később';

  @override
  String get msgReadingMemories => 'Emlékeid olvasása...';

  @override
  String get msgLearningMemories => 'Tanulás az emlékeidből...';

  @override
  String get msgUploadAttachedFileFailed => 'A csatolt fájl feltöltése sikertelen.';

  @override
  String captureRecordingError(String error) {
    return 'Hiba történt a felvétel során: $error';
  }

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return 'A felvétel leállt: $reason. Lehet, hogy újra kell csatlakoztatnia a külső kijelzőket vagy újra kell indítania a felvételt.';
  }

  @override
  String get captureMicrophonePermissionRequired => 'Mikrofon engedély szükséges';

  @override
  String get captureMicrophonePermissionInSystemPreferences => 'Adja meg a mikrofon engedélyt a Rendszerbeállításokban';

  @override
  String get captureScreenRecordingPermissionRequired => 'Képernyőfelvétel engedély szükséges';

  @override
  String get captureDisplayDetectionFailed => 'A kijelző észlelése sikertelen. A felvétel leállt.';

  @override
  String get devModeInvalidAudioBytesWebhookUrl => 'Érvénytelen hangbájtok webhook URL';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl => 'Érvénytelen valós idejű átírat webhook URL';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl => 'Érvénytelen létrehozott beszélgetés webhook URL';

  @override
  String get devModeInvalidDaySummaryWebhookUrl => 'Érvénytelen napi összefoglaló webhook URL';

  @override
  String get devModeSettingsSaved => 'Beállítások mentve!';

  @override
  String get voiceFailedToTranscribe => 'Nem sikerült átírni a hangot';

  @override
  String get locationPermissionRequired => 'Helymeghatározási engedély szükséges';

  @override
  String get locationPermissionContent =>
      'A gyors átvitelhez helymeghatározási engedély szükséges a WiFi-kapcsolat ellenőrzéséhez. Kérjük, adja meg a helymeghatározási engedélyt a folytatáshoz.';

  @override
  String get pdfTranscriptExport => 'Átirat exportálása';

  @override
  String get pdfConversationExport => 'Beszélgetés exportálása';

  @override
  String pdfTitleLabel(String title) {
    return 'Cím: $title';
  }

  @override
  String get conversationNewIndicator => 'Új 🚀';

  @override
  String conversationPhotosCount(int count) {
    return '$count fotó';
  }

  @override
  String get mergingStatus => 'Egyesítés...';

  @override
  String timeSecsSingular(int count) {
    return '$count mp';
  }

  @override
  String timeSecsPlural(int count) {
    return '$count mp';
  }

  @override
  String timeMinSingular(int count) {
    return '$count perc';
  }

  @override
  String timeMinsPlural(int count) {
    return '$count perc';
  }

  @override
  String timeMinsAndSecs(int mins, int secs) {
    return '$mins perc $secs mp';
  }

  @override
  String timeHourSingular(int count) {
    return '$count óra';
  }

  @override
  String timeHoursPlural(int count) {
    return '$count óra';
  }

  @override
  String timeHoursAndMins(int hours, int mins) {
    return '$hours óra $mins perc';
  }

  @override
  String timeDaySingular(int count) {
    return '$count nap';
  }

  @override
  String timeDaysPlural(int count) {
    return '$count nap';
  }

  @override
  String timeDaysAndHours(int days, int hours) {
    return '$days nap $hours óra';
  }

  @override
  String timeCompactSecs(int count) {
    return '${count}mp';
  }

  @override
  String timeCompactMins(int count) {
    return '${count}p';
  }

  @override
  String timeCompactMinsAndSecs(int mins, int secs) {
    return '${mins}p ${secs}mp';
  }

  @override
  String timeCompactHours(int count) {
    return '$countó';
  }

  @override
  String timeCompactHoursAndMins(int hours, int mins) {
    return '$hoursó ${mins}p';
  }

  @override
  String get moveToFolder => 'Áthelyezés mappába';

  @override
  String get noFoldersAvailable => 'Nincsenek elérhető mappák';

  @override
  String get newFolder => 'Új mappa';

  @override
  String get color => 'Szín';

  @override
  String get waitingForDevice => 'Várakozás az eszközre...';

  @override
  String get saySomething => 'Mondj valamit...';

  @override
  String get initialisingSystemAudio => 'Rendszerhang inicializálása';

  @override
  String get stopRecording => 'Felvétel leállítása';

  @override
  String get continueRecording => 'Felvétel folytatása';

  @override
  String get initialisingRecorder => 'Felvevő inicializálása';

  @override
  String get pauseRecording => 'Felvétel szüneteltetése';

  @override
  String get resumeRecording => 'Felvétel folytatása';

  @override
  String get noDailyRecapsYet => 'Még nincsenek napi összefoglalók';

  @override
  String get dailyRecapsDescription => 'A napi összefoglalói itt jelennek meg, amint elkészülnek';

  @override
  String get chooseTransferMethod => 'Válasszon átviteli módot';

  @override
  String get fastTransferSpeed => '~150 KB/s WiFi-n keresztül';

  @override
  String largeTimeGapDetected(String gap) {
    return 'Nagy időeltérés észlelve ($gap)';
  }

  @override
  String largeTimeGapsDetected(String gaps) {
    return 'Nagy időeltérések észlelve ($gaps)';
  }

  @override
  String get deviceDoesNotSupportWifiSwitchingToBle =>
      'Az eszköz nem támogatja a WiFi szinkronizálást, váltás Bluetooth-ra';

  @override
  String get appleHealthNotAvailable => 'Az Apple Health nem érhető el ezen az eszközön';

  @override
  String get downloadAudio => 'Hang letöltése';

  @override
  String get audioDownloadSuccess => 'Hang sikeresen letöltve';

  @override
  String get audioDownloadFailed => 'Hang letöltése sikertelen';

  @override
  String get downloadingAudio => 'Hang letöltése...';

  @override
  String get shareAudio => 'Hang megosztása';

  @override
  String get preparingAudio => 'Hang előkészítése';

  @override
  String get gettingAudioFiles => 'Hangfájlok lekérése...';

  @override
  String get downloadingAudioProgress => 'Hang letöltése';

  @override
  String get processingAudio => 'Hang feldolgozása';

  @override
  String get combiningAudioFiles => 'Hangfájlok egyesítése...';

  @override
  String get audioReady => 'Hang kész';

  @override
  String get openingShareSheet => 'Megosztási lap megnyitása...';

  @override
  String get audioShareFailed => 'Megosztás sikertelen';

  @override
  String get dailyRecaps => 'Napi Összefoglalók';

  @override
  String get removeFilter => 'Szűrő Eltávolítása';

  @override
  String get categoryConversationAnalysis => 'Beszélgetéselemzés';

  @override
  String get categoryPersonalityClone => 'Személyiségklón';

  @override
  String get categoryHealth => 'Egészség';

  @override
  String get categoryEducation => 'Oktatás';

  @override
  String get categoryCommunication => 'Kommunikáció';

  @override
  String get categoryEmotionalSupport => 'Érzelmi támogatás';

  @override
  String get categoryProductivity => 'Termelékenység';

  @override
  String get categoryEntertainment => 'Szórakozás';

  @override
  String get categoryFinancial => 'Pénzügyek';

  @override
  String get categoryTravel => 'Utazás';

  @override
  String get categorySafety => 'Biztonság';

  @override
  String get categoryShopping => 'Vásárlás';

  @override
  String get categorySocial => 'Közösségi';

  @override
  String get categoryNews => 'Hírek';

  @override
  String get categoryUtilities => 'Eszközök';

  @override
  String get categoryOther => 'Egyéb';

  @override
  String get capabilityChat => 'Chat';

  @override
  String get capabilityConversations => 'Beszélgetések';

  @override
  String get capabilityExternalIntegration => 'Külső integráció';

  @override
  String get capabilityNotification => 'Értesítés';

  @override
  String get triggerAudioBytes => 'Hang bájtok';

  @override
  String get triggerConversationCreation => 'Beszélgetés létrehozása';

  @override
  String get triggerTranscriptProcessed => 'Átirat feldolgozva';

  @override
  String get actionCreateConversations => 'Beszélgetések létrehozása';

  @override
  String get actionCreateMemories => 'Emlékek létrehozása';

  @override
  String get actionReadConversations => 'Beszélgetések olvasása';

  @override
  String get actionReadMemories => 'Emlékek olvasása';

  @override
  String get actionReadTasks => 'Feladatok olvasása';

  @override
  String get scopeUserName => 'Felhasználónév';

  @override
  String get scopeUserFacts => 'Felhasználói adatok';

  @override
  String get scopeUserConversations => 'Felhasználói beszélgetések';

  @override
  String get scopeUserChat => 'Felhasználói chat';

  @override
  String get capabilitySummary => 'Összefoglaló';

  @override
  String get capabilityFeatured => 'Kiemelt';

  @override
  String get capabilityTasks => 'Feladatok';

  @override
  String get capabilityIntegrations => 'Integrációk';

  @override
  String get categoryPersonalityClones => 'Személyiségklónok';

  @override
  String get categoryProductivityLifestyle => 'Termelékenység és életmód';

  @override
  String get categorySocialEntertainment => 'Közösségi és szórakozás';

  @override
  String get categoryProductivityTools => 'Termelékenységi eszközök';

  @override
  String get categoryPersonalWellness => 'Személyes jólét';

  @override
  String get rating => 'Értékelés';

  @override
  String get categories => 'Kategóriák';

  @override
  String get sortBy => 'Rendezés';

  @override
  String get highestRating => 'Legmagasabb értékelés';

  @override
  String get lowestRating => 'Legalacsonyabb értékelés';

  @override
  String get resetFilters => 'Szűrők visszaállítása';

  @override
  String get applyFilters => 'Szűrők alkalmazása';

  @override
  String get mostInstalls => 'Legtöbb telepítés';

  @override
  String get couldNotOpenUrl => 'Az URL nem nyitható meg. Kérjük, próbálja újra.';

  @override
  String get newTask => 'Új feladat';

  @override
  String get viewAll => 'Összes megtekintése';

  @override
  String get addTask => 'Feladat hozzáadása';

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
  String get audioPlaybackUnavailable => 'A hangfájl nem érhető el lejátszásra';

  @override
  String get audioPlaybackFailed => 'Nem sikerült lejátszani a hangot. A fájl sérült vagy hiányzik.';

  @override
  String get connectionGuide => 'Csatlakozási útmutató';

  @override
  String get iveDoneThis => 'Megcsináltam';

  @override
  String get pairNewDevice => 'Új eszköz párosítása';

  @override
  String get dontSeeYourDevice => 'Nem látja az eszközét?';

  @override
  String get reportAnIssue => 'Probléma jelentése';

  @override
  String get pairingTitleOmi => 'Kapcsolja be az Omi-t';

  @override
  String get pairingDescOmi => 'Tartsa nyomva az eszközt, amíg rezeg, a bekapcsoláshoz.';

  @override
  String get pairingTitleOmiDevkit => 'Állítsa Omi DevKit-et párosítási módba';

  @override
  String get pairingDescOmiDevkit =>
      'Nyomja meg a gombot egyszer a bekapcsoláshoz. A LED lilán villog párosítási módban.';

  @override
  String get pairingTitleOmiGlass => 'Kapcsolja be az Omi Glass-t';

  @override
  String get pairingDescOmiGlass => 'Tartsa nyomva az oldalgombot 3 másodpercig a bekapcsoláshoz.';

  @override
  String get pairingTitlePlaudNote => 'Állítsa Plaud Note-ot párosítási módba';

  @override
  String get pairingDescPlaudNote =>
      'Tartsa nyomva az oldalgombot 2 másodpercig. A piros LED villogni kezd, amikor párosításra kész.';

  @override
  String get pairingTitleBee => 'Állítsa Bee-t párosítási módba';

  @override
  String get pairingDescBee => 'Nyomja meg a gombot 5-ször egymás után. A fény kéken és zölden villogni kezd.';

  @override
  String get pairingTitleLimitless => 'Állítsa Limitless-t párosítási módba';

  @override
  String get pairingDescLimitless =>
      'Amikor bármilyen fény látható, nyomja meg egyszer, majd tartsa nyomva, amíg az eszköz rózsaszín fényt nem mutat, majd engedje el.';

  @override
  String get pairingTitleFriendPendant => 'Állítsa Friend Pendant-et párosítási módba';

  @override
  String get pairingDescFriendPendant =>
      'Nyomja meg a gombot a medálon a bekapcsoláshoz. Automatikusan párosítási módba lép.';

  @override
  String get pairingTitleFieldy => 'Állítsa Fieldy-t párosítási módba';

  @override
  String get pairingDescFieldy => 'Tartsa nyomva az eszközt, amíg a fény meg nem jelenik a bekapcsoláshoz.';

  @override
  String get pairingTitleAppleWatch => 'Apple Watch csatlakoztatása';

  @override
  String get pairingDescAppleWatch =>
      'Telepítse és nyissa meg az Omi alkalmazást Apple Watch-ján, majd koppintson a Csatlakozás gombra az alkalmazásban.';

  @override
  String get pairingTitleNeoOne => 'Állítsa Neo One-t párosítási módba';

  @override
  String get pairingDescNeoOne =>
      'Tartsa nyomva a bekapcsoló gombot, amíg a LED villogni nem kezd. Az eszköz felfedezhető lesz.';
}
