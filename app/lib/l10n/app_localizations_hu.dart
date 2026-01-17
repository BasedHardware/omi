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
  String get copyTranscript => 'Átírás másolása';

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
  String get noAppsFound => 'Nem található alkalmazás';

  @override
  String get tryAdjustingSearch => 'Próbáld módosítani a keresést vagy a szűrőket';

  @override
  String get createYourOwnApp => 'Saját alkalmazás létrehozása';

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
  String get retry => 'Újrapróbálás';

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
  String get descriptionOptional => 'Leírás (opcionális)';

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
  String get generateSummary => 'Összefoglaló létrehozása';

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
  String get unknownDevice => 'Ismeretlen eszköz';

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
    return '$label copied';
  }

  @override
  String get noApiKeysYet => 'Még nincsenek API-kulcsok. Hozzon létre egyet az alkalmazásával való integrációhoz.';

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
  String get debugAndDiagnostics => 'Hibakeresés és diagnosztika';

  @override
  String get autoDeletesAfter3Days => 'Automatikus törlés 3 nap után';

  @override
  String get helpsDiagnoseIssues => 'Segít a problémák diagnosztizálásában';

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
  String get autoCreateWhenNameDetected => 'Auto-create when name detected';

  @override
  String get followUpQuestions => 'Követő kérdések';

  @override
  String get suggestQuestionsAfterConversations => 'Kérdések javaslása beszélgetések után';

  @override
  String get goalTracker => 'Célkövetés';

  @override
  String get trackPersonalGoalsOnHomepage => 'Track your personal goals on homepage';

  @override
  String get dailyReflection => 'Napi elmélkedés';

  @override
  String get get9PmReminderToReflect => 'Get a 9 PM reminder to reflect on your day';

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
  String get pressKeys => 'Nyomj meg billentyűket...';

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
  String get tapToAddGoal => 'Érintse meg cél hozzáadásához';

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
  String get dailyScoreDescription => 'Egy pontszám, amely segít jobban összpontosítani a végrehajtásra.';

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
  String get all => 'Összes';

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
  String installsCount(String count) {
    return '$count+ telepítés';
  }

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
  String get setupInstructions => 'Beállítási utasítások';

  @override
  String get integrationInstructions => 'Integrációs utasítások';

  @override
  String get preview => 'Előnézet';

  @override
  String get aboutTheApp => 'Az alkalmazásról';

  @override
  String get aboutThePersona => 'A személyről';

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
  String get getOmiDevice => 'Szerezzen be Omi eszközt';

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
      'Ehhez az alkalmazáshoz nincs elérhető összefoglaló. Jobb eredményekért próbáljon ki egy másik alkalmazást.';

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
  String get dailySummary => 'Napi Összefoglaló';

  @override
  String get developer => 'Fejlesztő';

  @override
  String get about => 'Névjegy';

  @override
  String get selectTime => 'Idő Kiválasztása';

  @override
  String get accountGroup => 'Fiók';

  @override
  String get signOutQuestion => 'Kijelentkezés?';

  @override
  String get signOutConfirmation => 'Biztosan ki szeretne jelentkezni?';

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
  String get dailySummaryDescription => 'Kapjon személyre szabott összefoglalót a beszélgetéseiről';

  @override
  String get deliveryTime => 'Kézbesítési Idő';

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
  String get upcomingMeetings => 'KÖZELGŐ TALÁLKOZÓK';

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
  String get dailyReflectionDescription => '21:00 emlékeztető a napod átgondolására';

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
  String get tapToComplete => 'Koppintson a befejezéshez';

  @override
  String get invalidSetupInstructionsUrl => 'Érvénytelen beállítási útmutató URL';

  @override
  String get pushToTalk => 'Nyomja meg a beszédhez';

  @override
  String get summaryPrompt => 'Összefoglaló prompt';

  @override
  String get pleaseSelectARating => 'Kérjük, válasszon értékelést';

  @override
  String get reviewAddedSuccessfully => 'Értékelés sikeresen hozzáadva 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'Értékelés sikeresen frissítve 🚀';

  @override
  String get failedToSubmitReview => 'Az értékelés elküldése sikertelen. Kérjük, próbálja újra.';

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
      'This app will access your data. Omi AI is not responsible for how your data is used, modified, or deleted by this app';

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
  String get omiTraining => 'Omi képzés';

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
}
