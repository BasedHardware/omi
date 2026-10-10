// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Estonian (`et`).
class AppLocalizationsEt extends AppLocalizations {
  AppLocalizationsEt([String locale = 'et']) : super(locale);

  @override
  String get welcomeActionItemsDescription =>
      'Teie AI eraldab teie vestlustest automaatselt ülesanded. Need ilmuvad siia, kui need luuakse.';

  @override
  String get chatAppsProblemFailed => 'Midagi läks valesti. Proovi uuesti.';

  @override
  String get deviceOnboardingStarConversation => 'Märgi käimasolev vestlus tähega';

  @override
  String get deleteAll => 'Kustuta kõik';

  @override
  String get copySummary => 'Kopeeri kokkuvõte';

  @override
  String get locationAccessDesc => 'Et Omi saaks märkida, kus sinu vestlused toimusid.';

  @override
  String get firmwareUpdate => 'Püsivara värskendus';

  @override
  String get chatMessages => 'sõnumit';

  @override
  String get showEventsNoParticipants => 'Kuva ilma osalejateta sündmusi';

  @override
  String get sharePeriodYear => 'Sel aastal on Omi:';

  @override
  String get dreamReportRunFailed => 'Dreami käivitamine ebaõnnestus. Proovi uuesti.';

  @override
  String get sttModelAccuracy => 'Täpsus';

  @override
  String get scopes => 'Ulatused';

  @override
  String get deleteFlowFeedbackSubtitle => 'Mis oleks pannud Omi sinu jaoks toimima?';

  @override
  String appDataAccessTitle(String appName) {
    return 'Kas lubada rakendusele $appName juurdepääs?';
  }

  @override
  String get pendantStorageAlmostFull => 'Ripatsi mälu on peaaegu täis — hoia rakendus avatud, et sünkroonida.';

  @override
  String get deviceOnboardingAllSetDoublePressBadge => '2×';

  @override
  String get copyErrorMessage => 'Kopeeri veateade';

  @override
  String get filterMemories => 'Filtreeri mälestusi';

  @override
  String get helpsDiagnoseIssuesAutoDeletes => 'Aitab diagnoosida probleeme. Kustutatakse automaatselt 3 päeva pärast.';

  @override
  String get locationServiceDisabledDesc =>
      'Asukohateenused on selles seadmes välja lülitatud. Lülita need seadetes sisse.';

  @override
  String chatAppsIsConnected(String app) {
    return '$app on ühendatud';
  }

  @override
  String get paymentMethodStripe => 'Stripe';

  @override
  String get deleteReasonTechnicalIssues => 'Liiga palju tehnilisi probleeme';

  @override
  String get payments => 'Maksed';

  @override
  String get verifiedFallback => 'Kinnitatud';

  @override
  String get pleaseWait => 'Palun oodake…';

  @override
  String get appLanguage => 'Rakenduse keel';

  @override
  String get unknownApp => 'Tundmatu rakendus';

  @override
  String get appReEnableFailedBody => 'Seda rakendust ei õnnestunud uuesti sisse lülitada. Proovi uuesti.';

  @override
  String get somethingWentWrongTryAgain => 'Midagi läks valesti! Palun proovi hiljem uuesti.';

  @override
  String get upgradeScheduled => 'Täiendus planeeritud';

  @override
  String get wrappedBuddiesLabel => 'SÕBRAD';

  @override
  String get chatBlockShowMore => 'Näita rohkem';

  @override
  String get subscriptionSuccessfulCharged => 'Tellimus õnnestus! Teilt on uue arveldusperioodi eest tasu võetud.';

  @override
  String get phoneCall => 'Telefonikõne';

  @override
  String get chatAppsRefreshFailed => 'Värskendamine ebaõnnestus. Näitame viimast teadaolevat seisu.';

  @override
  String get noDesktopAccess => 'Ei tööta arvutis';

  @override
  String get areYouSure => 'Kas olete kindel?';

  @override
  String get resubscribe => 'Telli uuesti';

  @override
  String voiceMatchMeterLabel(String level) {
    return 'Hääle vaste: $level';
  }

  @override
  String get syncingBackground => 'Jätkame teie salvestiste sünkroonimist taustal.';

  @override
  String get signOutQuestion => 'Logi välja?';

  @override
  String chatAppsReadOnlyBanner(String app) {
    return 'Kirjutuskaitstud. Vasta Omile rakenduses $app.';
  }

  @override
  String get connected => 'Ühendatud';

  @override
  String get shareStatsMessage => 'Jagan oma Omi statistikat! (omi.me - teie alati sees AI assistent)';

  @override
  String get frequencyMinimal => 'Minimaalne';

  @override
  String get addAppSelectLogo => 'Valige oma rakenduse jaoks logo';

  @override
  String get integrationInstructions => 'Integratsiooni juhised';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'Ligipääsetavuse loa olek: $status. Palun kontrollige Süsteemieelistusi.';
  }

  @override
  String get wrappedCompleted => 'lõpetatud';

  @override
  String get remaining => 'Jäänud';

  @override
  String get onDeviceIntensive => 'Seadmesisene transkriptsioon on arvutuslikult intensiivne.';

  @override
  String get diagnosticsVerdictTrouble => 'Ühendamisega on probleeme';

  @override
  String deviceOnboardingVoiceReplyPreviewThroughDevice(String device) {
    return '$device kaudu';
  }

  @override
  String get copyConfig => 'Kopeeri konfiguratsioon';

  @override
  String accessesDataTypes(String dataTypes) {
    return 'Juurdepääs: $dataTypes';
  }

  @override
  String get chatAppsWaitlistConfirmed => 'Aitäh. WhatsApp ilmub siia, kui on valmis.';

  @override
  String get undo => 'Tühista';

  @override
  String get phoneContactsAccessTitle => 'Luba juurdepääs kontaktidele';

  @override
  String confidenceIsConfirmed(String name) {
    return '$name on staatuses Kinnitatud. Muid samme pole vaja teha.';
  }

  @override
  String get wrappedMovie => 'FILM';

  @override
  String get wrappedStruggleLabelUpper => 'VÕITLUS';

  @override
  String get appleHealthFeatureChatDesc => 'Küsi Omilt oma sammude, une, pulsi ja treeningute kohta.';

  @override
  String get writeReviewOptional => 'Kirjuta arvustus (valikuline)';

  @override
  String get pairNewDevice => 'Sidu uus seade';

  @override
  String chatUsedOfLimitCompute(String used, String limit) {
    return '$used / $limit arvutuseelarvet kasutatud';
  }

  @override
  String get dailySummary => 'Päeva kokkuvõte';

  @override
  String get pleaseEnterYourName => 'Palun sisestage oma nimi';

  @override
  String get continueWithoutDevice => 'Jätka ilma seadmeta';

  @override
  String get configure => 'Seadista';

  @override
  String get createApp => 'Loo rakendus';

  @override
  String get invalidUrlError => 'Palun sisestage kehtiv URL';

  @override
  String get appClosed => 'Rakendus suletud';

  @override
  String get downgradeToFreemiumAction => 'Mine üle tasuta versioonile';

  @override
  String get chatAppsUseTelegramForNow => 'Kasuta praegu Telegrami';

  @override
  String get wrappedBestMomentsBadge => 'Parimad hetked';

  @override
  String get storageSection => 'Salvestusruum';

  @override
  String get pauseResumeRecording => 'Peata/jätka salvestamine';

  @override
  String get phoneUnmute => 'Eemalda vaigistus';

  @override
  String get youreAllSet => 'Oled valmis!';

  @override
  String get migrationComplete => 'Migratsioon lõpetatud!';

  @override
  String get paymentAppCost => 'Rakenduse hind';

  @override
  String get deviceOnboardingFinish => 'Lõpeta';

  @override
  String get noVerifiedNumbers => 'Kinnitatud numbreid pole';

  @override
  String get connectAiAssistantsToData => 'Ühenda AI-assistendid oma andmetega';

  @override
  String get keyNameHint => 'nt Claude Desktop';

  @override
  String get paymentMethods => 'Makseviisid';

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'Ligipääsetavuse loa kontrollimine ebaõnnestus: $error';
  }

  @override
  String get confidenceReasonAutoOnly => 'Automaatselt märgistatud, pole veel kinnitatud';

  @override
  String whatsNewInVersion(String version) {
    return 'Mis on uut versioonis $version';
  }

  @override
  String get selectYourLanguage => 'Valige oma keel';

  @override
  String get memoryClearedSuccess => 'Omi mälu teie kohta on tühjendatud';

  @override
  String get memoryContentHint => 'Eelistan hommikusi koosolekuid.';

  @override
  String get dreamReportTitle => 'Dreami aruanne';

  @override
  String importErrorGeneric(String error) {
    return 'Viga: $error';
  }

  @override
  String get completionRate => 'Täitmise määr';

  @override
  String get trackPersonalGoals => 'Jälgi isiklikke eesmärke avalehel';

  @override
  String get wrappedTryAgain => 'Proovi uuesti';

  @override
  String get dataProtection => 'Andmekaitse';

  @override
  String get yourConversations => 'Teie vestlused';

  @override
  String pdfTitleLabel(String title) {
    return 'Pealkiri: $title';
  }

  @override
  String get sendRawAudioToOmiDescription =>
      'Lülita välja, et töötlemata heli Omisse ei saadetaks. Transkriptsioone ja pilvefunktsioonide jaoks vajalikke andmeid võidakse endiselt Omisse saata.';

  @override
  String get entityLoadFailed => 'Seda lehte ei õnnestunud laadida.';

  @override
  String get networkNameSsid => 'Võrgu nimi (SSID)';

  @override
  String get discovery => 'Avastus';

  @override
  String get rayBanMetaMicPickerConnectError =>
      'Selle mikrofoniga ei saanud ühendust luua. Veenduge, et see oleks iPhone\'i seadetes ühendatud.';

  @override
  String get fairUseAboutTitle => 'Õiglase kasutuse kohta';

  @override
  String get wrappedYouTalkedAbout => 'Sa rääkisid';

  @override
  String get downgradeLimitQuality => '30% madalam transkriptsiooni kvaliteet';

  @override
  String get sharedTasksUnknownSender => 'Keegi';

  @override
  String get selectAReason => 'Vali põhjus';

  @override
  String get wrappedWinLabel => 'VÕIT';

  @override
  String get configuration => 'Konfiguratsioon';

  @override
  String get noFolder => 'Kausta pole';

  @override
  String get manifestRefreshedSuccess => 'Manifest värskendati edukalt';

  @override
  String get paymentStatusActive => 'Aktiivne';

  @override
  String get linkKeyMismatch => 'Lingivõtme mittevastavus';

  @override
  String speakerTagPromptProgress(int current, int total) {
    return '$current/$total';
  }

  @override
  String get updateRequiredMessage =>
      'Seda Omi versiooni enam ei toetata. Värskenda, et jätkata salvestamist ja sünkroonimist.';

  @override
  String get sharePeriodMonth => 'Sel kuul on Omi:';

  @override
  String get rollbackToStableFirmware => 'Tagasi stabiilsele püsivarale';

  @override
  String get paymentStatusConnected => 'Ühendatud';

  @override
  String get findDeviceNoneTitle => 'Omi-d ei leitud';

  @override
  String get appIdCopiedToClipboard => 'Rakenduse ID kopeeritud lõikelauale';

  @override
  String get bySubmittingYouAgreeToOmi => 'Esitades nõustute Omi ';

  @override
  String get filterRating => 'Hinnang';

  @override
  String get usageAtWork => 'Tööl';

  @override
  String get tasksCleanTodayMessage => 'See eemaldab ainult tähtajad';

  @override
  String get ignoredVoicesSubtitle => 'Telekas, taskuhäälingud ja muud hääled, mille märkisid kui „Pole inimene“';

  @override
  String get permissionEnable => 'Luba';

  @override
  String integrationComingSoon(String appName) {
    return '$appName ei ole veel toetatud.';
  }

  @override
  String get sttModelLower => 'Madalam';

  @override
  String get loadingYourMemories => 'Teie mälestuste laadimine…';

  @override
  String get followUpQuestions => 'Järgmised küsimused';

  @override
  String get previousDay => 'Eelmine päev';

  @override
  String fairUseCaseRefCopied(String caseRef) {
    return '$caseRef kopeeritud';
  }

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get recordingPaused => 'Salvestamine peatatud';

  @override
  String get cannotReportOwnMessages => 'Te ei saa oma sõnumeid teatada';

  @override
  String get enterWordsHint => 'Sisestage sõnad (komaga eraldatud)';

  @override
  String get audioDownloadFailed => 'Heli allalaadimine ebaõnnestus';

  @override
  String get clearMemoryMessage => 'Kõik teie mälestused kustutatakse. Seda ei saa tagasi võtta.';

  @override
  String get templateNameHint => 'nt. Koosoleku ülesannete ekstraktor';

  @override
  String speakerLabelTalkTime(String duration) {
    return '$duration sellest häälest';
  }

  @override
  String get recordingMode => 'Salvestusrežiim';

  @override
  String get cancelReasonOther => 'Muu';

  @override
  String get sttModelHigher => 'Kõrgem';

  @override
  String get settingUpSystemAudioCapture => 'Süsteemiheli salvestamise seadistamine';

  @override
  String memoriesCount(int count) {
    return '$count mälu';
  }

  @override
  String get noSpecificDataAccessConfigured => 'Konkreetset andmetele juurdepääsu pole seadistatud.';

  @override
  String get recordingIdLabel => 'Salvestise ID';

  @override
  String get highlights => 'Esiletõstetud';

  @override
  String get phoneTryAgain => 'Proovi uuesti';

  @override
  String chatAppsCouldNotOpen(String app) {
    return 'Rakendust $app ei saanud avada. Veendu, et see on installitud, ja proovi uuesti.';
  }

  @override
  String get onDeviceTranscriptionDesc => 'Transkriptsioon töödeldakse kohapeal sinu seadmes';

  @override
  String get chatAppsTryPromise => 'Mida ma eile Samile lubasin?';

  @override
  String get paymentStatusNotConnected => 'Pole ühendatud';

  @override
  String get intervalSeconds => 'Intervall (sekundid)';

  @override
  String get authorize => 'Autoriseeri';

  @override
  String get settingsHeader => 'SEADED';

  @override
  String get personNameAlreadyExists => 'Selle nimega isik on juba olemas.';

  @override
  String get deviceOnboardingVoiceReplyPreviewThroughCurrentOutput => 'Läbi praeguse heliväljundi';

  @override
  String get monthJun => 'Juuni';

  @override
  String selectedCount(int count) {
    return '$count valitud';
  }

  @override
  String get batteryHistory => 'Aku';

  @override
  String get noPastChats => 'Sinu vestlused Omiga ilmuvad siia.';

  @override
  String get chatAppsDoesSave => 'Salvestab mälestusi ja haldab sinu ülesandeid';

  @override
  String get apiKey => 'API võti';

  @override
  String get authFailedToLinkGoogle => 'Google\'iga sidumine ebaõnnestus, palun proovige uuesti.';

  @override
  String audioUploadFailedKeptLocal(String duration) {
    return 'Üleslaadimine ebaõnnestus — $duration heli on sinu telefonis alles.';
  }

  @override
  String get free => 'Tasuta';

  @override
  String get deselectAllTasksMenu => 'Tühista kõigi valik';

  @override
  String get dreamReportLoadFailed => 'Dreami aruande laadimine ebaõnnestus.';

  @override
  String get entityRecentConversations => 'Hiljutised vestlused';

  @override
  String get pendantRecordingNote =>
      'Sinu ripats salvestab iseseisvalt. Salvestised sünkroonitakse telefoniga, kui rakendus on avatud.';

  @override
  String get manageStorage => 'Halda salvestusruumi';

  @override
  String get filterSystem => 'Teie kohta';

  @override
  String get deleteConsequenceSubscription => 'Kõik aktiivsed tellimused tühistatakse.';

  @override
  String get defaultList => 'Vaikimisi loend';

  @override
  String get shared => 'Jagatud';

  @override
  String get customVocabulary => 'Kohandatud Sõnavara';

  @override
  String get feedbackTitleAudioQuality => 'Milliseid probleeme kogesite?';

  @override
  String get thisActionCannotBeUndone => 'Seda ei saa tagasi võtta.';

  @override
  String errorRequestingPermission(String error) {
    return 'Viga loa taotlemisel: $error';
  }

  @override
  String get recapRegenerateFailed => 'Kokkuvõtet ei õnnestunud uuesti luua. Proovi hiljem uuesti.';

  @override
  String get result => 'Tulemus:';

  @override
  String get statusCallMissed => 'Vastamata kone';

  @override
  String get diagnosticsLongestGap => 'Pikim paus';

  @override
  String get noLogFilesFound => 'Logifaile ei leitud.';

  @override
  String get speechTranscriptionSectionTitle => 'Kõne ja transkriptsioon';

  @override
  String get syncNow => 'Sünkrooni kohe';

  @override
  String get sttUsePrimaryLanguage => 'Kasuta põhikeelt';

  @override
  String get importUnsupportedFileType => 'Seda failitüüpi ei saa importida.';

  @override
  String get chatSendMessage => 'Saada sõnum';

  @override
  String get syncCardAllBackedUp => 'Kõik salvestused sünkroonitud';

  @override
  String get settings => 'Seaded';

  @override
  String get backgroundLocationDeniedDesc =>
      'Palun minge seadme seadetesse ja määrake asukoha luba väärtusele \"Luba alati\"';

  @override
  String get computationallyIntensive => 'Seadmes transkriptsioon on arvutuslikult intensiivne.';

  @override
  String get and => ' ja ';

  @override
  String get yourVerifiedNumbers => 'Teie kinnitatud numbrid';

  @override
  String get tasksCleanTodayTitle => 'Puhastada tänased ülesanded?';

  @override
  String get microphonePermission => 'Mikrofoni luba';

  @override
  String get failedToUpdateConversationTitle => 'Vestluse pealkirja uuendamine ebaõnnestus';

  @override
  String get appsDisconnected => 'Sinu rakendused ja integratsioonid ühendatakse lahti.';

  @override
  String get live => 'Otse';

  @override
  String get connectionFailed => 'Ühendamine ebaõnnestus';

  @override
  String get selectImages => 'Vali pildid';

  @override
  String get playbackAudioNetworkFailed => 'Kontrollige ühendust';

  @override
  String get paypalEmail => 'PayPali e-post';

  @override
  String get chatAppsOnTheList => 'Nimekirjas';

  @override
  String get generateSummary => 'Genereeri kokkuvõte';

  @override
  String get categoryHealth => 'Tervis';

  @override
  String get transcribeLaterStorageFull =>
      'Sinu telefonis on vähe mäluruumi, seega salvestamine on peatatud. Vabasta ruumi või laadi salvestised üles, siis jätkub salvestamine automaatselt.';

  @override
  String get chatAppsNoChatsTitle => 'Vestlusi pole veel';

  @override
  String get onboardingSetupStepPersonalize => 'Sinu kogemuse isikupärastamine';

  @override
  String get leaveUnselectedTasks => 'Jätke valimata, et luua ülesanded ilma projektita';

  @override
  String get wrappedButYouPushedThroughEmoji => 'Aga sa said hakkama 💪';

  @override
  String get needHelp => 'Vajate abi?';

  @override
  String get confirmAndCancel => 'Kinnita ja tühista';

  @override
  String get frequencyDescHigh => 'Rohkem soovitusi, umbes 6–9 päevas';

  @override
  String get copyLink => 'Kopeeri link';

  @override
  String get dreamReportLiveBanner =>
      'Dream rakendab need muudatused ise. Võta need tagasi jaotises Hiljutised muudatused.';

  @override
  String get enterActionItemDescription => 'Sisesta ülesande kirjeldus';

  @override
  String chatAppsInChannel(String app) {
    return 'Rakenduses $app';
  }

  @override
  String get links => 'Lingid';

  @override
  String get dreamReportEmptyTitle => 'Käivitusi pole veel';

  @override
  String get monthJan => 'Jaan';

  @override
  String get wrappedMostProductiveDay => 'Kõige produktiivsem';

  @override
  String get productUpdate => 'Toote värskendus';

  @override
  String get addYourReview => 'Lisa oma arvustus';

  @override
  String get raybanMetaImageCaptureReady => 'Pildistamine on valmis';

  @override
  String get displayUpcomingMeetingsDescription => 'Kuva tulevasi kohtumisi menüüribal';

  @override
  String get whatWeCollect => 'Mida me kogume';

  @override
  String get connectPayPalToReceivePayments =>
      'Ühendage oma PayPali konto, et alustada oma rakenduste eest maksete saamist';

  @override
  String get justAMoment => 'Üks hetk, palun';

  @override
  String get chatReplyServerError => 'Meie poolel läks midagi valesti. Palun proovi uuesti.';

  @override
  String get transferInProgress => 'Ülekanne käib…';

  @override
  String get usageAll => 'Kogu aeg';

  @override
  String get failedToLoadContacts => 'Kontaktide laadimine ebaõnnestus';

  @override
  String appUsersCount(int count) {
    return '$count+ kasutajat';
  }

  @override
  String get report => 'Teata';

  @override
  String get languageLabel => 'Keel';

  @override
  String verifiedOnDate(String date) {
    return 'Kinnitatud $date';
  }

  @override
  String get customVocabularyHeader => 'KOHANDATUD SÕNAVARA';

  @override
  String otaRebooting(String deviceName) {
    return '$deviceName taaskäivitub uue püsivaraga.';
  }

  @override
  String get mcpServer => 'MCP server';

  @override
  String get findDevice => 'Leia';

  @override
  String get msgUploadAttachedFileFailed => 'Manustatud faili üleslaadimine ebaõnnestus.';

  @override
  String get appName => 'App Name';

  @override
  String get pairingTitlePlaudNote => 'Lülitage Plaud Note sidumisrežiimi';

  @override
  String get moreOptions => 'Rohkem valikuid';

  @override
  String get noConversationsHeroMessage =>
      'Siin kuvatakse salvestatud vestlused. Esimese salvestamiseks puuduta avalehel salvestusnuppu.';

  @override
  String get finish => 'Lõpeta';

  @override
  String get goBack => 'Mine tagasi';

  @override
  String get apiKeysDescription =>
      'API võtmeid kasutatakse autentimiseks, kui teie rakendus suhtleb Omi serveriga. Need võimaldavad teie rakendusel luua mälestusi ja turvaliselt juurde pääseda teistele Omi teenustele.';

  @override
  String get sttProviderSpeechmatics => 'Speechmatics';

  @override
  String get setWebhookUrlInSettings => 'Selle funktsiooni kasutamiseks määra webhooki URL arendaja seadetes.';

  @override
  String get dailyScoreBreakdown => 'Päeva skoori ülevaade';

  @override
  String get showMeetingsMenuBarDesc => 'Kuva oma järgmine koosolek ja aeg selle alguseni macOS-i menüüribal';

  @override
  String get tapToTrackThisGoal => 'Puudutage selle eesmärgi jälgimiseks';

  @override
  String get summarizingConversation => 'Vestluse kokkuvõtte tegemine…\nSee võib võtta mõne sekundi';

  @override
  String get noInternetConnection => 'Internetiühendus puudub';

  @override
  String diagnosticsCountSincePairing(int count) {
    return '$count pärast sidumist';
  }

  @override
  String get wrappedTasksCreated => 'loodud ülesannet';

  @override
  String get deleteConsequenceNoRecovery => 'Sinu kontot ei saa taastada — isegi mitte tugi.';

  @override
  String get waitForReprocessing => 'Oota, kuni uuesti töötlemine lõpeb.';

  @override
  String get needYourPermission => 'Vajame teie luba';

  @override
  String get downgradeLimitSpeakers => 'Kõnelejaid ei saa tuvastada';

  @override
  String conversationsTodayCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count vestlust täna.',
      one: '1 vestlus täna.',
      zero: 'Täna vestlusi pole.',
    );
    return '$_temp0';
  }

  @override
  String get dailyScore => 'PÄEVA SKOOR';

  @override
  String get reportAnIssue => 'Teata probleemist';

  @override
  String get invalidKey => 'Kehtetu klahv';

  @override
  String get preview => 'Eelvaade';

  @override
  String get nextWeek => 'Järgmisel nädalal';

  @override
  String get confidenceUnverified => 'Kinnitamata';

  @override
  String get previewScreenshots => 'Ekraanipiltide eelvaade';

  @override
  String get ledBrightness => 'LED heledus';

  @override
  String get firmwareUpdateFailedMessage =>
      'Värskendus ei lõppenud. Seadmel on endiselt praegune püsivara ja seda on ohutu kasutada. Hoia see laetuna ja telefoni lähedal ning proovi uuesti.';

  @override
  String get loadingProfile => 'Profiili laadimine…';

  @override
  String get deleteRecapConfirmTitle => 'Kustutada see kokkuvõte?';

  @override
  String get notificationFrequency => 'Teavituste sagedus';

  @override
  String get captureSystemAudioFromMeetings => 'Süsteemiheli jäädvustamine koosolekutest';

  @override
  String get storeAudioCloudDescription => 'Laeb salvestised üles, kui räägid, et saaksid neid hiljem taasesitada.';

  @override
  String get color => 'Värv';

  @override
  String get open => 'Ava';

  @override
  String get diagnosticsVerdictNoDrops => 'Sel nädalal katkestusi pole';

  @override
  String get autoExtractionFeature => 'Automaatselt vestlustest eraldatud';

  @override
  String get searchResults => 'Otsingutulemused';

  @override
  String get v2UndetectedMessage =>
      'Näeme, et teil on kas V1 seade või teie seade pole ühendatud. SD-kaardi funktsioon on saadaval ainult V2 seadmetele.';

  @override
  String get endAndProcess => 'Lõpeta ja töötle vestlus';

  @override
  String get noSyncedRecordings => 'Sünkroonitud salvestusi veel pole';

  @override
  String get coworker => 'Kolleeg';

  @override
  String get setupQuestionUsage => '2. Kus plaanite oma Omit kasutada?';

  @override
  String get pinnedNotSelectable => 'Esile tõstetud, ei saa valida';

  @override
  String get showMore => 'näita rohkem ↓';

  @override
  String get createYourFirstMemory => 'Loo alustamiseks oma esimene mälestus';

  @override
  String get discardedConversation => 'Kustutatud vestlus';

  @override
  String get enableApps => 'Luba rakendused';

  @override
  String get today => 'Täna';

  @override
  String get showEventsNoParticipantsDesc => 'Kui lubatud, näitab Coming Up sündmusi ilma osalejate või videolingita.';

  @override
  String get couldNotLoadPage => 'Lehte ei õnnestunud laadida. Kontrolli ühendust ja proovi uuesti.';

  @override
  String actionItemDeletedResult(String description) {
    return 'Ülesanne \"$description\" kustutatud';
  }

  @override
  String get deleteSampleQuestion => 'Kustuta näidis?';

  @override
  String get youAreOnAPaidPlan => 'Oled tasulisel plaanil.';

  @override
  String get otaInstallFailed => 'Installimine ebaõnnestus. Seadmel on endiselt praegune püsivara.';

  @override
  String get addFirstMemory => 'Lisa oma esimene mälestus';

  @override
  String get appDeletedSuccessfully => 'Rakendus kustutati edukalt';

  @override
  String get chatAppsConnectTelegramMessage => 'Omi avab Telegrami privaatse lingiga, mis on ainult sinu jaoks.';

  @override
  String get phoneSetupStep1Title => 'Kinnitage oma telefoninumber';

  @override
  String get deviceRequirements => 'Teie seade ei vasta seadmesisese transkriptsiooni nõuetele.';

  @override
  String get confidenceEvidenceHeader => 'Alus';

  @override
  String get pleaseEnterAName => 'Palun sisestage nimi.';

  @override
  String get deleteConfirmationWord => 'DELETE';

  @override
  String get speakerTagPromptThatsMe => 'See olen mina';

  @override
  String get ourCommitment => 'Meie kohustus';

  @override
  String get notificationScopes => 'Teavituste ulatused';

  @override
  String get autoDeletesAfter3Days => 'Automaatne kustutamine 3 päeva pärast';

  @override
  String get initialisingRecorder => 'Salvestaja initsialiseerimine';

  @override
  String get privateAndSecureOnDevice => 'Salvestatud sellesse telefoni';

  @override
  String get allObjectsMigratedFinalizing => 'Kõik objektid migreeritud. Lõpetamine…';

  @override
  String get chatAppsOpenMessages => 'Ava Sõnumid';

  @override
  String get upgradeToPro => 'Uuenda Pro-le';

  @override
  String get clientId => 'Kliendi ID';

  @override
  String get backgroundActivity => 'Taustegevus';

  @override
  String get noSummaryAvailable => 'Kokkuvõte pole saadaval';

  @override
  String get failedToUpdateStarred => 'Tärni lisamine ebaõnnestus.';

  @override
  String get omiYourAiCompanion => 'Omi – teie AI kaaslane';

  @override
  String get pleaseSelectReason => 'Palun valige põhjus';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Kõik mälestused ($count) kustutatakse. Seda ei saa tagasi võtta.';
  }

  @override
  String get connectNow => 'Ühenda kohe';

  @override
  String chatAppsDisconnectTitle(String app) {
    return 'Kas katkestada $app ühendus?';
  }

  @override
  String get clearCredentials => 'Kustuta mandaadid';

  @override
  String get grantContactsPermissionForSms => 'SMS-i kaudu jagamiseks andke palun kontaktide luba';

  @override
  String get cloudTranscription => 'Pilves transkriptsioon';

  @override
  String get memoryHistory => 'Ajalugu';

  @override
  String get speechSamples => 'Kõnenäidised';

  @override
  String get wrappedBiggest => 'Suurim';

  @override
  String get reviewShowMore => 'Näita rohkem';

  @override
  String get triggersWhenDaySummaryGenerated => 'Käivitatakse, kui luuakse päeva kokkuvõte.';

  @override
  String get thankYouFeedback => 'Täname tagasiside eest!';

  @override
  String get allow => 'Luba';

  @override
  String triggeredByType(String triggerType) {
    return 'käivitab $triggerType';
  }

  @override
  String get howToPair => 'Kuidas siduda';

  @override
  String get conversationDeveloperTools => 'Arendaja tööriistad vestlustes';

  @override
  String get memoryProvenanceIphone => 'iPhone';

  @override
  String get aboutYou => 'Sinu kohta';

  @override
  String get memoryProvenanceMac => 'Mac';

  @override
  String get effectCounts => 'Aitab';

  @override
  String get tagSpeakerIncludingLaterSpeech => 'Märgi ka selle kõneleja hilisem kõne';

  @override
  String get storeAudioOnPhone => 'Salvesta heli telefoni';

  @override
  String get developerApiKeys => 'Arendaja API võtmed';

  @override
  String get wrappedMyBuddiesCard => 'Minu sõbrad';

  @override
  String get bulkExportAlreadyExported => 'Kõik valitud ülesanded on juba eksporditud';

  @override
  String get popularBadge => 'POPULAARNE';

  @override
  String get enableLocationTitle => 'Luba asukoht';

  @override
  String get feedbackBug => 'Tagasiside / viga';

  @override
  String get good => 'Hea';

  @override
  String get upgradeYourPlan => 'Uuenda oma plaani';

  @override
  String get exportingAllData =>
      'Teie andmete eksportimine… Hoidke Omi avatud; suurte kontode puhul võib see võtta mitu minutit.';

  @override
  String get switchAndRestart => 'Lülita';

  @override
  String get noReposFound => 'Hoidlaid ei leitud';

  @override
  String get latest => 'Uusim';

  @override
  String get failedToRevoke => 'Autoriseerimise tühistamine ebaõnnestus. Palun proovige uuesti.';

  @override
  String get appleHealthDisconnectCta => 'Katkesta ühendus Apple Health\'iga';

  @override
  String get chatAppsPrivateMemoriesSubtitle =>
      'Tervis, raha ja kõik, mille oled privaatseks märkinud, jääb vestlusrakendustest välja.';

  @override
  String get deleteFlowFeedbackTitle => 'Räägi rohkem';

  @override
  String get failedToConnectTodoistRetry => 'Todoistiga ühendamine ebaõnnestus. Palun proovi uuesti.';

  @override
  String get capturePhoneStorageFull => 'Telefoni mälu on täis';

  @override
  String deletePeopleTitle(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Kustuta $count inimest?',
      one: 'Kustuta 1 inimene?',
    );
    return '$_temp0';
  }

  @override
  String get cleanUpNothingMessage => 'Omi ei ole praegu kellegi suhtes kahtlev.';

  @override
  String get writeAReviewOptional => 'Kirjuta arvustus (valikuline)';

  @override
  String get syncFailed => 'Sünkroonimine ebaõnnestus';

  @override
  String get audioShareFailed => 'Jagamine ebaõnnestus';

  @override
  String loadMoreRemaining(String count) {
    return 'Laadi rohkem ($count järel)';
  }

  @override
  String get phoneDeleteNumberFailed => 'Seda numbrit ei õnnestunud kustutada';

  @override
  String deviceUsesCodec(String device, String reason) {
    return '$device salvestab vormingus, mida see pakkuja ei oska lugeda ($reason), seega kasutatakse selle asemel Omi transkriptsiooni.';
  }

  @override
  String get chatAppsConnectIMessageMessage =>
      'Saada Omile üks sõnum numbrilt, mida soovid kasutada. Selles olev kood seob selle numbri sinu kontoga.';

  @override
  String get speechToTextUnavailableDesc =>
      'Kõne tekstiks teisendamine pole praegu saadaval. Kontrolli internetiühendust ja seadme kõnetuvastuse seadeid ning proovi uuesti.';

  @override
  String get chatReplyTimeout => 'Vastus võttis liiga kaua aega. Palun proovi uuesti.';

  @override
  String get passwordMinLengthError => 'Parool peab olema vähemalt 8 tähemärki';

  @override
  String get chatAppsWhatsAppMessage => 'Töötame selle nimel, et Omi jõuaks WhatsAppi. See ilmub siia, kui on valmis.';

  @override
  String get deleteAccountCheckbox =>
      'Mõistan, et minu konto kustutamine on püsiv ja kõik andmed, sealhulgas mälestused ja vestlused, lähevad kaotsi ega ole taastatavad.';

  @override
  String get firmwareConnectWifi => 'Ühendage WiFi-ga või mobiilsidevõrguga.';

  @override
  String get forgetDeviceConfirmMessage => 'Omi lõpetab selle seadmega ühendumise.';

  @override
  String get editSwipeFeature => 'Puudutage muutmiseks, libistage lõpetamiseks või kustutamiseks';

  @override
  String get memoryManagement => 'Mäluhaldus';

  @override
  String get transcriptLoadFailed => 'Transkriptsiooni ei õnnestunud laadida.';

  @override
  String get diagnosticsExportTitle => 'Omi seadme diagnostika';

  @override
  String get updateOmiFirmware => 'Värskenda Omi püsivara';

  @override
  String get importTooManyAttempts => 'Praegu on liiga palju importimisi. Proovi hiljem uuesti.';

  @override
  String get noAppsFound => 'Rakendusi ei leitud';

  @override
  String get phoneSetupStep1Subtitle => 'Helistame teile kinnitamiseks';

  @override
  String get deleteSyncedFiles => 'Kustuta sünkroniseeritud salvestised';

  @override
  String speakerLabelVoiceStatus(String state) {
    String _temp0 = intl.Intl.selectLogic(
      state,
      {
        'learned': 'Hääl õpitud',
        'pending': 'Häält õpitakse…',
        'disabled': 'Hääle salvestamine on välja lülitatud',
        'other': 'Häält pole veel õpitud',
      },
    );
    return '$_temp0';
  }

  @override
  String get recordingsMayCaptureOthers =>
      'Salvestised võivad jäädvustada teiste inimeste hääli. Enne lubamist veenduge, et teil on kõigi osalejate nõusolek.';

  @override
  String get helpful => 'Kasulik';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return 'Laadin alla $model: $received / $total MB';
  }

  @override
  String get permissions => 'Õigused';

  @override
  String get audioDownloadSuccess => 'Heli on edukalt alla laaditud';

  @override
  String get confirmPlanChange => 'Kinnita plaani muutmine';

  @override
  String get wrappedThatAwkwardMoment => 'See piinlik hetk';

  @override
  String get calendarProviders => 'Kalendri pakkujad';

  @override
  String evidenceAutoUnconfirmed(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count automaatset märgistust pole veel kinnitatud',
      one: '1 automaatne märgistus pole veel kinnitatud',
    );
    return '$_temp0';
  }

  @override
  String get importData => 'Impordi andmed';

  @override
  String get weekdayMon => 'Esm';

  @override
  String get deviceStorageTitle => 'Seadme salvestusruum';

  @override
  String get externalAppAccess => 'Väliste rakenduste juurdepääs';

  @override
  String get transcriptionUnavailable => 'Transkriptsioon pole saadaval';

  @override
  String get termsAndPrivacyPolicy => 'Tingimused ja Privaatsuspoliitika';

  @override
  String get noImportsYet => 'Importe pole veel';

  @override
  String get openOmiOnAppleWatchDescription =>
      'Omi rakendus on teie Apple Watchile installitud. Avage see ja puudutage käivitamiseks Start.';

  @override
  String dreamReportFailed(String error) {
    return 'Ebaõnnestus ($error)';
  }

  @override
  String get sendSummary => 'Saada kokkuvõte';

  @override
  String get filterAll => 'Kõik';

  @override
  String get deleteChatMessage => 'See kaob varasematest vestlustest jäädavalt.';

  @override
  String get timeout10Minutes => '10 minutit';

  @override
  String get noCalendarEventsNearby => 'Selle aja ümbruses ei leitud kalendrisündmusi.';

  @override
  String get cancelSyncQuestion => 'Tühista sünkroonimine?';

  @override
  String get whatShouldWeMake => 'Mida me peaksime tegema?';

  @override
  String get usageListened => 'Listened';

  @override
  String get errorUpdatingStripeDetails => 'Viga Stripe andmete värskendamisel! Palun proovige hiljem uuesti.';

  @override
  String get conversationEndAfterHours => 'Vestlused lõpevad nüüd pärast 4-tunnist vaikust';

  @override
  String get issueActivatingApp => 'Selle rakenduse aktiveerimisel tekkis probleem. Palun proovi uuesti.';

  @override
  String get appCreatedSuccessfully => 'Rakendus edukalt loodud!';

  @override
  String get categoryNews => 'Uudised';

  @override
  String get phoneSearchHint => 'Otsi';

  @override
  String peoplePinnedCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count esile tõstetud',
      one: '1 esile tõstetud',
    );
    return '$_temp0';
  }

  @override
  String get wrappedHours => 'tundi';

  @override
  String get phoneKeypad => 'Klahvistik';

  @override
  String get peopleFilterLowConfidence => 'Väike kindlus';

  @override
  String get agreeToContributeData => 'Ma mõistan ja nõustun panustama oma andmetega AI treenimisse';

  @override
  String get addGoal => 'Lisa eesmärk';

  @override
  String get dreamReportRunInProgress => 'Käivitus juba töötab. Proovi minuti pärast uuesti.';

  @override
  String importedConfig(String providerName) {
    return 'Imporditud $providerName konfiguratsioon';
  }

  @override
  String monthsAgo(int count) {
    return '$count kuud tagasi';
  }

  @override
  String get downgradeLimitationsHeading => 'Sind ootavad ees järgmised piirangud:';

  @override
  String get chatRemoveSelectedText => 'Eemalda tsiteeritud tekst';

  @override
  String get firmwareBatteryAbove15 => 'Aku üle 15%';

  @override
  String reviewQuestionSamePerson(String name) {
    return 'Sama inimene mis „$name“?';
  }

  @override
  String get effectCountsALot => 'Aitab palju';

  @override
  String get sdCard => 'SD-kaart';

  @override
  String get openInGoogleCalendar => 'Ava Google\'i kalendris';

  @override
  String get appleHealthFeatureSecureTitle => 'Turvaline sünkroonimine';

  @override
  String get conversationDeveloperToolsDescription =>
      'Näita vestluse menüüs valikuid Kopeeri vestluse ID ja Testi viipa';

  @override
  String get host => 'Host';

  @override
  String get deleteReasonMissingFeatures => 'Puuduvad funktsioonid, mida vajan';

  @override
  String get syncingInProgress => 'Sünkroonimine käib';

  @override
  String get tabDone => 'Tehtud';

  @override
  String get revoke => 'Tühista';

  @override
  String get mcp => 'MCP';

  @override
  String get anyoneCanDiscoverTemplate => 'Igaüks saab teie malli avastada';

  @override
  String get mcpDescription =>
      'Omi ühendamiseks teiste rakendustega, et lugeda, otsida ja hallata oma mälestusi ja vestlusi. Alustamiseks looge võti.';

  @override
  String get connectionLostDescription => 'Ühendus katkes. Kontrollige oma internetiühendust ja proovige uuesti.';

  @override
  String chatAppsNoChatsMessage(String app) {
    return 'Vestlused, mida pead Omiga rakenduses $app, ilmuvad siia.';
  }

  @override
  String get storedLocallyNeverShared =>
      'Salvestatud sellesse telefoni. Saadetakse ainult sinu transkriptsiooniteenuse pakkujale.';

  @override
  String get morePaymentMethodsComingSoon => 'Peagi rohkem makseviise';

  @override
  String get allCaughtUp => 'Kõik on sünkroonitud';

  @override
  String previewImageLabel(int index, int total) {
    return 'Ekraanipilt $index/$total';
  }

  @override
  String get disable => 'Keela';

  @override
  String get recordings => 'Salvestised';

  @override
  String get enterPersonsName => 'Sisesta isiku nimi';

  @override
  String get newConversationCreated => 'Uus vestlus loodud';

  @override
  String resetsInDays(int count) {
    return 'Lähtestub $count päeva pärast';
  }

  @override
  String get confidenceConfirmed => 'Kinnitatud';

  @override
  String get bulkExportInProgress => 'Eksportimine…';

  @override
  String get detectLanguages => 'Tuvasta 10+ keelt';

  @override
  String get phoneSpeaker => 'Kolar';

  @override
  String get visitWebsite => 'Külasta veebisaiti';

  @override
  String get howToTakeGoodSample => 'Kuidas teha head proovi?';

  @override
  String get clearChat => 'Kustuta vestlus';

  @override
  String languageSetTo(String language) {
    return 'Keeleks määratud $language';
  }

  @override
  String get deviceOnboardingVoiceReplyHeadphonesDescription =>
      'Privaatne. Räägib ainult AirPods, Bluetooth või juhtmega kõrvaklappide kaudu.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'Teie plaan jääb aktiivseks kuni $date. Pärast seda kaotate juurdepääsu piiramatutele funktsioonidele.';
  }

  @override
  String get clientSecret => 'Kliendi saladus';

  @override
  String get pairingTitleAppleWatch => 'Ühendage Apple Watch';

  @override
  String get share => 'Jaga';

  @override
  String get yourPrivacyYourControl => 'Teie privaatsus, teie kontroll';

  @override
  String get tapToCopy => 'Puudutage kopeerimiseks';

  @override
  String get feedbackTitleFoundAlternative => 'Millele lähete üle?';

  @override
  String get all => 'Kõik';

  @override
  String get filterCapabilities => 'Võimed';

  @override
  String get tagOtherSegments => 'Märgi teised segmendid';

  @override
  String get entityDecisions => 'Otsused';

  @override
  String get tasksCreatedInWorkspace => 'Ülesanded luuakse sellesse tööalasse';

  @override
  String get fairUseDailyTranscription => 'Daily Transcription';

  @override
  String get pausePlayback => 'Paus';

  @override
  String get sharedTasksLinkExpired => 'Neid jagatud ülesandeid ei leitud või link on aegunud.';

  @override
  String get editConversationDialogTitle => 'Muuda vestlust';

  @override
  String get deleteMemoryConfirmation => 'Kas kustutada see mälestus? Seda ei saa tagasi võtta.';

  @override
  String get appUnderReviewMessage =>
      'Teie rakendus on läbivaatamisel ja nähtav ainult teile. See muutub avalikuks pärast heakskiitu.';

  @override
  String get illDoItLater => 'Teen seda hiljem';

  @override
  String get captureStillRecording => 'Salvestamine jätkub';

  @override
  String confidenceNextLabels(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Märgi nad veel $count vestluses.',
      one: 'Märgi nad veel 1 vestluses.',
    );
    return '$_temp0';
  }

  @override
  String get speakerTagPromptAnswerFailed => 'Salvestamine ebaõnnestus. Proovi uuesti.';

  @override
  String get feedbackReasonSummaryIncomplete => 'Incomplete';

  @override
  String get errorActivatingApp => 'Viga rakenduse aktiveerimisel';

  @override
  String get tasksCompleted => 'Ülesanded täidetud';

  @override
  String onboardingStepOf(int current, int total) {
    return 'Samm $current/$total';
  }

  @override
  String get downgradeAnyway => 'Alanda siiski';

  @override
  String get leaveBlank => 'Jäta tühjaks';

  @override
  String get chatAppsViewChats => 'Vaata vestlusi';

  @override
  String get captureScreenRecordingPermissionRequired => 'Ekraani salvestamise luba on vajalik';

  @override
  String get accountCutoverUpdateRequiredTitle => 'Päivitys vaaditaan';

  @override
  String weeksAgo(int count) {
    return '$count nädalat tagasi';
  }

  @override
  String get phoneEndCall => 'Lopeta';

  @override
  String get startupFailedMessage =>
      'Omi käivitamisel läks midagi valesti. Kontrolli oma ühendust ja proovi seejärel uuesti.';

  @override
  String get permissionRevokedTitle => 'Luba tühistatud';

  @override
  String get chatFeatures => 'Vestluse funktsioonid';

  @override
  String get couldNotLoadMap => 'Kaarti ei õnnestunud laadida';

  @override
  String get selectContactsToShare => 'Vali kontaktid jagamiseks';

  @override
  String get ok => 'OK';

  @override
  String get memoryReviewConfirmed => 'Kinnitatud.';

  @override
  String get deleteKnowledgeGraph => 'Kustuta teadmiste graaf';

  @override
  String get reviewChangeFailed => 'Muudatust ei õnnestunud värskendada. Proovi uuesti.';

  @override
  String get limitless => 'Limitless';

  @override
  String uploadingToCloud(int current, int total) {
    return '$current/$total üleslaadimine';
  }

  @override
  String get dontSeeYourDevice => 'Ei näe oma seadet?';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Teie ülesanded sünkroonitakse teie $appName kontoga';
  }

  @override
  String appSettingsLabel(String appName) {
    return 'Rakenduse $appName seaded';
  }

  @override
  String get chatBlockShowLess => 'Näita vähem';

  @override
  String get mindMap => 'Mind Map';

  @override
  String get authorizationBearer => 'Authorization: Bearer <võti>';

  @override
  String get dreamReportWouldSuggestTasks => 'Soovitaks ülesandeid';

  @override
  String get dreamReportWouldAsk => 'Küsiks sinult';

  @override
  String get getFreeUnlimitedAccess => 'Saa tasuta piiramatu juurdepääs';

  @override
  String get yourDaysJourney => 'Teie päeva teekond';

  @override
  String get transcriptReceived => 'Transkriptsioon vastu võetud';

  @override
  String get expand => 'Laienda';

  @override
  String get onboardingCompleteMessage =>
      'Lase Omil mõned päevad töötada. Sinu vestlused, mälestused ja ülesanded hakkavad täienema.';

  @override
  String get trainFamilyProfiles => 'Treenige profiile sõprade ja pere jaoks';

  @override
  String get selectText => 'Vali tekst';

  @override
  String get generatingDescription => 'Kirjelduse genereerimine…';

  @override
  String get deviceOnboardingStarConversationDesc => 'Märgi vestlus oluliseks';

  @override
  String disableAppNamed(String appName) {
    return 'Keela $appName';
  }

  @override
  String get deleteConversationConfirmation => 'Kas kustutada see vestlus? Seda ei saa tagasi võtta.';

  @override
  String get contentCopied => 'Sisu kopeeritud lõikelauale';

  @override
  String get joinTheCommunity => 'Liitu kogukonnaga!';

  @override
  String get noContactsWithPhoneNumbers => 'Telefoninumbritega kontakte ei leitud';

  @override
  String get removeAttachment => 'Eemalda manus';

  @override
  String get followTheVoiceInstructions => 'Jargige haaljuhiseid';

  @override
  String get createYourOwnApp => 'Loo oma rakendus';

  @override
  String get paymentDetails => 'Makse üksikasjad';

  @override
  String get tellOmiWhoSaidIt => 'Ütle Omi-le, kes seda ütles 🗣️';

  @override
  String audioInputSetTo(String deviceName) {
    return 'Helisisend määratud: $deviceName';
  }

  @override
  String get pleaseEnterValidEmail => 'Palun sisestage kehtiv e-posti aadress';

  @override
  String get thisYear => 'See aasta';

  @override
  String get noTranscriptMessage => 'Sellel vestlusel pole transkriptsiooni.';

  @override
  String get appearanceDark => 'Tume';

  @override
  String get createCustomTemplate => 'Loo kohandatud mall';

  @override
  String get monthMay => 'Mai';

  @override
  String get tasksAddedToList => 'Ülesanded lisatakse sellesse loendisse';

  @override
  String isTriggeredBy(String triggerDescription) {
    return 'On $triggerDescription.';
  }

  @override
  String get deleteConversationTitle => 'Kustuta vestlus?';

  @override
  String get accountCutoverUpdateRequiredMessage => 'Asenna uusin Omi-sovellus jatkaaksesi tilin siirron jälkeen.';

  @override
  String get txtFormat => 'TXT';

  @override
  String chatAppsDisconnectMessage(String app) {
    return 'Omi lõpetab vastamise rakenduses $app ja kustutab selle jaoks hoitava vestlusajaloo. Rakenduses $app juba olevad sõnumid jäävad sinna.';
  }

  @override
  String get captureWithCamera => 'Jäädvusta kaameraga';

  @override
  String get appIdLabel => 'Rakenduse ID';

  @override
  String get endpointUrl => 'Lõpp-punkti URL';

  @override
  String get actionItemUpdated => 'Ülesanne uuendatud';

  @override
  String itemsSelected(int count) {
    return '$count valitud';
  }

  @override
  String get onboardingWhatIKnowAboutYouDescription => 'See kaart uueneb, kui Omi õpib teie vestlustest.';

  @override
  String diagnosticsLastDuration(String duration) {
    return 'Viimased $duration';
  }

  @override
  String get pairingDescLimitless =>
      'Kui mõni tuli põleb, vajutage üks kord ja seejärel vajutage ja hoidke all, kuni seade näitab roosat valgust, seejärel vabastage.';

  @override
  String get chatBlockOpenConversation => 'Ava vestlus';

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '$used/$limit ülevaadet saadud sel kuul';
  }

  @override
  String get connectionErrorDesc =>
      'Serveriga ühendamine ebaõnnestus. Palun kontrollige oma internetiühendust ja proovige uuesti.';

  @override
  String get enterWordsCommaSeparated => 'Sisestage sõnad (komadega eraldatud)';

  @override
  String get otherDevicesComingSoon => 'Teised seadmed tulekul';

  @override
  String speakerSuggestionChip(String name) {
    return '$name?';
  }

  @override
  String get speakerTagPromptNotAPersonToast => 'Märgitud kui mitte inimene';

  @override
  String get createKeyToGetStarted => 'Loo võti alustamiseks';

  @override
  String get captureRecordingSeparateConfirm => 'Eralda';

  @override
  String get diagnosticsDrops => 'Katkestused';

  @override
  String lowBatteryAlertBody(int level) {
    return 'Sinu aku on $level%. Aeg laadida! 🔋';
  }

  @override
  String get deviceOnboardingTurnOffSubtitle => 'Hoia nuppu 3 sekundit all';

  @override
  String get done => 'Valmis';

  @override
  String get wifiConfigurationSubtitle => 'Sisestage WiFi andmed, et seade saaks püsivara alla laadida.';

  @override
  String get permissionGrantedNow =>
      'Luba antud! Nüüd:\n\nAvage Omi rakendus oma kellal ja puudutage allpool \"Jätka\"';

  @override
  String get setUpPayPal => 'Seadista PayPal';

  @override
  String get statusProcessed => 'Töödeldud';

  @override
  String phoneFreeCallsRemaining(int remaining, int limit) {
    return 'Sel kuul on jäänud $remaining tasuta kõnet $limit-st';
  }

  @override
  String get event => 'Sündmus';

  @override
  String get conversationEvents => 'Vestlussündmused';

  @override
  String get uninstall => 'Desinstalli';

  @override
  String get appCreators => 'Rakenduste loojad';

  @override
  String get muted => 'Vaigistatud';

  @override
  String get deleteRecapAction => 'Kustuta';

  @override
  String get addAppErrorSelectingThumbnailRetry => 'Viga pisipildi valimisel. Proovige uuesti.';

  @override
  String get basicPlanDescription => '300 premium minutit + piiramatu seadmes';

  @override
  String get countrySelectionPermanent => 'Teie riigivalik on püsiv ja seda ei saa hiljem muuta.';

  @override
  String get transcriptionConnecting => 'Transkriptsiooni ühendamine…';

  @override
  String transcriptionsPendingFraction(int pending, int total) {
    return 'Ootel transkriptsioonid $pending/$total';
  }

  @override
  String get apiKeyAuth => 'API võtme autentimine';

  @override
  String downloadModelWithName(String model) {
    return 'Laadi mudel alla ($model)';
  }

  @override
  String get devModeInvalidDaySummaryWebhookUrl => 'Kehtetu päeva kokkuvõtte veebihaagi URL';

  @override
  String get memoryReviewSaveFailed => 'Salvestamine ebaõnnestus, proovi uuesti';

  @override
  String get payYourSttProvider => 'Omis on tasuta. Transkriptsiooni pakkujale maksad otse.';

  @override
  String get dailySummaryHeader => 'PÄEVANE KOKKUVÕTE';

  @override
  String get fairUseStageWarning => 'Hoiatus';

  @override
  String get multipleSpeakersDesc =>
      'Tundub, et salvestises on mitu kõnelejat. Palun veenduge, et olete vaikses kohas ja proovige uuesti.';

  @override
  String get pastChats => 'Varasemad vestlused';

  @override
  String get listeningMins => 'Kuulamine (min)';

  @override
  String get pairingDescOmi => 'Vajutage ja hoidke seadet all, kuni see vibreerib, et seda sisse lülitada.';

  @override
  String get deviceOnboardingIntroSubtitle =>
      'Proovi reaalajas transkriptsiooni, küsimuse esitamist ja topeltpuudutuse otseteed.';

  @override
  String get autoRemoveSyncedCopiesTitle => 'Sünkroonitud koopiate automaatne eemaldamine';

  @override
  String chatAppsReadOnlyFooter(String app) {
    return 'Need vestlused on siin kirjutuskaitstud. Vasta rakenduses $app.';
  }

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'Mikrofon on vahetatud. Jätkamine ${countdown}s pärast';
  }

  @override
  String get takePhoto => 'Tee foto';

  @override
  String get cancelSync => 'Tühista sünkroonimine';

  @override
  String appSettings(String appName) {
    return '$appName seaded';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'Mikrofoni loa kontrollimine ebaõnnestus: $error';
  }

  @override
  String get micGain => 'Mikrofoni võimendus';

  @override
  String get collectingData => 'Andmete kogumine…';

  @override
  String get memoryReadOnlyHint => 'Seda mälestust hoitakse ajaloona ja seda ei saa muuta.';

  @override
  String get appUnderReviewOwner =>
      'Teie rakendus on ülevaatamisel ja nähtav ainult teile. See muutub avalikuks pärast kinnitamist.';

  @override
  String get addNewPerson => 'Lisa uus isik';

  @override
  String get nameSpeakerTitle => 'Nimeta kõneleja';

  @override
  String get downloadingAudioFromSdCard => 'Heli allalaadimine seadme SD-kaardilt';

  @override
  String get pendantSyncingRecordings => 'Ripatsi salvestiste sünkroonimine…';

  @override
  String get otaNotSupported => 'Seda püsivara ei saa Wi-Fi kaudu värskendada.';

  @override
  String get wrappedSomethingWentWrong => 'Midagi läks\nvalesti';

  @override
  String get screenRecording => 'Ekraanisalvestus';

  @override
  String get audioProcessedLocally =>
      'Heli töödeldakse kohapeal. Töötab võrguühenduseta, privaatsem, kuid kasutab rohkem akut.';

  @override
  String get onboardingSignIn => 'Logi sisse';

  @override
  String timeDaysPlural(int count) {
    return '$count päeva';
  }

  @override
  String get memoryReviewTitle => 'Mida ma täna õppisin';

  @override
  String get hidePassword => 'Peida parool';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get disconnected => 'Ühendus puudub';

  @override
  String get revokeApiKeyQuestion => 'Tühistada API võti?';

  @override
  String get detectBrowserBasedMeetings => 'Tuvastage brauseripõhised koosolekud';

  @override
  String get failedToDeleteConversations => 'Vestluste kustutamine ebaõnnestus';

  @override
  String get raybanMetaCapturePhoto => 'Jäädvusta foto';

  @override
  String get bleSpeed => '~30 KB/s BLE kaudu';

  @override
  String get conversationPromptPlaceholder =>
      'Sa oled suurepärane rakendus, sulle antakse vestluse transkriptsioon ja kokkuvõte…';

  @override
  String get secureAuthViaGoogleAccount => 'Turvaline autentimine Google\'i konto kaudu';

  @override
  String get omiHas => 'Omil on:';

  @override
  String get raybanMetaContinue => 'Jätka';

  @override
  String get pauseRecording => 'Peata salvestus';

  @override
  String get evidenceNothing => 'Sa pole teda veel märgistanud ega kinnitanud';

  @override
  String get noActivityYet => 'Tegevust pole veel';

  @override
  String get enterPasswordError => 'Palun sisestage oma parool';

  @override
  String get forgetDeviceConfirmTitle => 'Kas unustada seade?';

  @override
  String get ratingsAndReviews => 'Hinnangud ja arvustused';

  @override
  String get addApiKeyAfterImport => 'Peate pärast importimist lisama oma API võtme';

  @override
  String get alreadyOnStableFirmware => 'Teil on juba uusim stabiilne versioon.';

  @override
  String get deleteAccountConfirm => 'Kas olete kindel, et soovite oma konto kustutada?';

  @override
  String get recordingInfo => 'Salvestise teave';

  @override
  String get feedbackReasonSummaryInaccurate => 'Inaccurate';

  @override
  String get pendantRecordingTitle => 'Salvestamine ripatsil';

  @override
  String get deleteWhileProcessingMessage =>
      'See salvestis on üles laaditud, kuid Omi loob veel vestlust. Kui kustutad selle nüüd ja töötlemine ebaõnnestub, ei saa seda taastada. Kas kustutada ikkagi?';

  @override
  String get createNewKey => 'Loo uus võti';

  @override
  String get firmwareDownloadFailedMessage =>
      'Värskendust ei õnnestunud alla laadida ja seadet ei muudetud. Kontrolli internetiühendust ja proovi uuesti.';

  @override
  String get loadingTasks => 'Ülesannete laadimine…';

  @override
  String get previousResult => 'Eelmine tulemus';

  @override
  String get reviewLoadFailed => 'Sinu küsimusi ei õnnestunud laadida.';

  @override
  String get onDevice => 'Seadmel';

  @override
  String get bluetoothSyncEnabled => 'Bluetoothi sünkroonimine lubatud';

  @override
  String get categorySafety => 'Turvalisus';

  @override
  String get unknownLocation => 'Tundmatu asukoht';

  @override
  String get newMemoryTitle => 'Uus mälestus';

  @override
  String get conversationCannotBeMerged => 'Seda vestlust ei saa ühendada (lukustatud või juba ühendamisel)';

  @override
  String get summaryGenerated => 'Kokkuvõte loodud';

  @override
  String get createKey => 'Loo Võti';

  @override
  String get letOmiChooseAutomatically => 'Lase Omil automaatselt parim rakendus valida';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'Palun taaskäivitage $deviceName värskenduse lõpuleviimiseks.';
  }

  @override
  String get goals => 'Eesmärgid';

  @override
  String get wrappedAnErrorOccurred => 'Tekkis viga';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'Mikrofoni loa kontrollimine ebaõnnestus: $error';
  }

  @override
  String get connectLater => 'Ühenda hiljem';

  @override
  String get wrappedRememberedByOmi => 'jäädvustatud Omi poolt';

  @override
  String get fairUseStatusNormal => 'Teie kasutus on tavapiirides.';

  @override
  String get includePersonalEventsDescription => 'Kaasa isiklikud sündmused ilma osalejateta';

  @override
  String get week => 'Nädal';

  @override
  String get willLikelyCrash => 'Selle lubamine põhjustab tõenäoliselt rakenduse krahhi või hangumise.';

  @override
  String get selectPrimaryLanguage => 'Valige oma põhikeel';

  @override
  String get pilotFeaturesDescription => 'Need funktsioonid on testid ja toe pakkumist ei garanteerita.';

  @override
  String get askOmi => 'Küsi Omilt';

  @override
  String get ifYouCancel => 'Kui tühistate:';

  @override
  String get audioOutput => 'Heliväljund';

  @override
  String get memoryReviewWrong => 'Vale';

  @override
  String get couldNotSchedulePlanChange => 'Paketi muutmist ei õnnestunud ajastada. Palun proovige uuesti.';

  @override
  String speakerLabelEarlierMatches(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Leitud $count varasemast vestlusest',
      one: 'Leitud 1 varasemast vestlusest',
    );
    return '$_temp0';
  }

  @override
  String get deviceOnboardingListening => 'Kuulan…';

  @override
  String get speechProfileEnrollmentPrompt =>
      'Et Omi teaks, milline hääl on sinu oma — räägi ükskõik millest umbes 5 sekundit.';

  @override
  String get mcpServerUrl => 'MCP Server URL';

  @override
  String get chatBlockMemory => 'Mälestus';

  @override
  String get noStarredConversations => 'Tärniga vestlusi pole';

  @override
  String get syncStatusTooOld => 'Sünkroonimiseks liiga vana — Omi ei saa seda vastu võtta';

  @override
  String connectedAsUser(String userId) {
    return 'Ühendatud kasutajana: $userId';
  }

  @override
  String get phonePageTitle => 'Telefon';

  @override
  String get buildGraphButton => 'Loo graafik';

  @override
  String get issuesCreatedInRepo => 'Probleemid luuakse teie vaikimisi hoidlasse';

  @override
  String get scopeUserFacts => 'Kasutaja faktid';

  @override
  String get unableToLoadPlans => 'Plaanide laadimine ebaõnnestus';

  @override
  String get deleteRecording => 'Kustuta salvestis';

  @override
  String get appDeleteFailed => 'Rakenduse kustutamine ebaõnnestus. Palun proovi hiljem uuesti.';

  @override
  String get addAppUpdatedSuccess => 'Rakendus edukalt värskendatud 🚀';

  @override
  String get reviewCaughtUpTitle => 'Pole midagi vastata';

  @override
  String get copyConversationId => 'Kopeeri vestluse ID';

  @override
  String get helpImproveOmiBySharing => 'Aita Omi-d parandada, jagades anonümiseeritud analüüsandmeid';

  @override
  String get dataEncryptedBanner =>
      'Sinu andmed on vaikimisi kaitstud tugeva krüptimisega ja sina kontrollid, kuidas neid salvestatakse ja kasutatakse.';

  @override
  String get redo => 'Salvesta uuesti';

  @override
  String get updateOmiGlassFirmware => 'Värskenda OmiGlassi püsivara';

  @override
  String get deviceUnpairedMessage =>
      'Seadme sidumine tühistatud. Minge Seaded > Bluetooth ja unustage seade sidumise tühistamise lõpetamiseks.';

  @override
  String speakerLabelText(String part, String name) {
    String _temp0 = intl.Intl.selectLogic(
      part,
      {
        'likely': 'Tõenäoline',
        'soundsLike': 'Kõlab nagu $name',
        'notPerson': 'Pole $name',
        'carried': 'Endiselt $name. Üle võetud sinu viimasest vestlusest.',
        'change': 'Muuda',
        'alsoTitle': 'Kas see on ka $name?',
        'alsoBody': 'Omi leidis sama hääle varasematest vestlustest.',
        'confirmed': 'Kinnitasid selle sildi',
        'other': 'Vaata üle',
      },
    );
    return '$_temp0';
  }

  @override
  String get continueWithApple => 'Jätka Apple\'iga';

  @override
  String get iUnderstand => 'Ma mõistan';

  @override
  String get memoryProvenanceAndroid => 'Android';

  @override
  String get saving => 'Salvestamine…';

  @override
  String get deviceOnboardingDoubleTapTitle => 'Kohanda topeltkoputust';

  @override
  String get allMemoriesPublicResult => 'Kõik mälestused on nüüd avalikud';

  @override
  String get chatAppsAddToContacts => 'Lisa Omi kontaktidesse';

  @override
  String get wrappedDays => 'päeva';

  @override
  String get invalidJsonError => 'Vigane JSON';

  @override
  String syncCardNeedsAttention(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count salvestist vajab tähelepanu',
      one: '1 salvestis vajab tähelepanu',
    );
    return '$_temp0';
  }

  @override
  String get wrappedSwipeUpToBegin => 'Pühkige üles alustamiseks';

  @override
  String addedToService(String serviceName) {
    return 'Lisatud $serviceName';
  }

  @override
  String get advanced => 'Täpsem';

  @override
  String get autoCreateAndTagNewSpeakers => 'Loo ja märgista uued kõnelejad automaatselt';

  @override
  String get appCapabilities => 'Rakenduse võimalused';

  @override
  String get onboardingMicrophoneDenied =>
      'Mikrofoni luba keelatud. Palun andke luba Süsteemieelistused > Privaatsus ja turvalisus > Mikrofon.';

  @override
  String get pleaseEnterFolderName => 'Palun sisestage kausta nimi';

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'Bluetoothi loa kontrollimine ebaõnnestus: $error';
  }

  @override
  String get invalidRecordingDetected => 'Tuvastati kehtetu salvestis';

  @override
  String get appAnalytics => 'Rakenduse analüütika';

  @override
  String get captureRecordingsSheetTitle => 'Selle vestluse salvestised';

  @override
  String deletedLimitlessConversations(int count) {
    return 'Kustutatud $count Limitless vestlust';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'Viga pildi valimisel: $error';
  }

  @override
  String get unnamedSpeakerLabel => 'Kõneleja';

  @override
  String get failedToCreateApp => 'Rakenduse loomine ebaõnnestus. Palun proovige uuesti.';

  @override
  String get planUpdate => 'Plaani uuendus';

  @override
  String get timeout5Minutes => '5 minutit';

  @override
  String get deleteSample => 'Kustuta näidis';

  @override
  String get willNotSeeAgain => 'Te ei saa seda enam näha.';

  @override
  String get thisMonth => 'See kuu';

  @override
  String get enterName => 'Sisesta nimi';

  @override
  String get memoryThisDevice => 'See seade';

  @override
  String get verifiedNumbersDescription => 'Kui helistate kellelegi, naevad nad seda numbrit';

  @override
  String get deviceOnboardingSingleTapHint => 'See oli üks koputus — proovi koputada kaks korda kiiresti!';

  @override
  String autoClosingInSeconds(int seconds) {
    return 'Automaatne sulgemine $seconds sekundi pärast';
  }

  @override
  String get chatAppsProPerkContext => 'Omi mäletab konteksti igas rakenduses';

  @override
  String get errorProcessingConversation => 'Viga vestluse töötlemisel. Palun proovige hiljem uuesti.';

  @override
  String get profileSettings => 'Profiili seaded';

  @override
  String get statusUnprocessed => 'Töötlemata';

  @override
  String get deleteConversationMessage => 'See kustutab ka seotud mälestused, ülesanded ja helifailid.';

  @override
  String get cancelSubscriptionQuestion => 'Tühista tellimus?';

  @override
  String get forUnlimitedFreeTranscription => 'piiramatuks tasuta transkriptsiooniks.';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used/$limit min kasutatud';
  }

  @override
  String get categoryPersonalWellness => 'Isiklik heaolu';

  @override
  String get automaticTranslation => 'Automaatne tõlge';

  @override
  String get defaultAiAssistant => 'Vaikimisi AI abiline';

  @override
  String get allDataErased => 'Sinu mälestused ja vestlused kustutatakse.';

  @override
  String entityDue(String date) {
    return 'Tähtaeg $date';
  }

  @override
  String get feedbackChatWithUs => 'More detail? Chat with us';

  @override
  String get speakerTagPromptSomeoneNew => 'Keegi uus';

  @override
  String get inProgress => 'Töötlemisel';

  @override
  String get raybanMetaCheckAgain => 'Kontrolli uuesti';

  @override
  String get fairUseStageNormal => 'Tavaline';

  @override
  String get pairingTitleLimitless => 'Lülitage Limitless sidumisrežiimi';

  @override
  String get usingNativeIosSpeech => 'Kasutatakse iOS-i natiivset kõnetuvastust';

  @override
  String get actionItemDeletedSuccessfully => 'Ülesanne edukalt kustutatud';

  @override
  String get failedToSetLanguage => 'Keele määramine ebaõnnestus';

  @override
  String get appHomeUrl => 'Rakenduse avalehe URL';

  @override
  String get appNameLabel => 'Rakenduse nimi';

  @override
  String get localStorageDisabled => 'Kohalik salvestus keelatud';

  @override
  String get appReEnable => 'Lülita uuesti sisse';

  @override
  String get migrationFailed => 'Migreerimine ebaõnnestus';

  @override
  String get markComplete => 'Märgi lõpetatuks';

  @override
  String get lastUsedLabel => 'Viimati kasutatud';

  @override
  String get chatCleared => 'Vestlus kustutatud';

  @override
  String get revokeApiKeyWarning =>
      'Seda võtit kasutavad rakendused kaotavad API-juurdepääsu. Seda ei saa tagasi võtta.';

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return 'Ekraanipildi loa kontrollimine ebaõnnestus: $error';
  }

  @override
  String get troubleshootingSteps =>
      'Tõrkeotsing:\n\n1. Veenduge, et Omi on teie kellale installitud\n2. Avage Omi rakendus oma kellal\n3. Otsige loa hüpikakent\n4. Puudutage \"Luba\", kui küsitakse\n5. Rakendus teie kellal sulgub - avage see uuesti\n6. Tulge tagasi ja puudutage \"Jätka\" oma iPhone\'is';

  @override
  String get location => 'Asukoht';

  @override
  String get chatAppsWhatsAppMeantime => 'Telegram ja iMessage töötavad juba täna, samade mälestuste ja ülesannetega.';

  @override
  String get sliderOff => 'Väljas';

  @override
  String get checkingFirmwareVersion => 'Püsivara versiooni kontrollimine…';

  @override
  String get reviewUnknownSpeaker => 'Tundmatu kõneleja';

  @override
  String get professionSales => 'Müük';

  @override
  String get noRssiDataYet => 'RSSI andmeid veel pole';

  @override
  String get emptyOldMessage => '✅ Vanu ülesandeid pole';

  @override
  String deleteSampleConfirmation(String name) {
    return 'Isiku $name häälenäidis eemaldatakse. Seda ei saa tagasi võtta.';
  }

  @override
  String get saveUrlButton => 'Salvesta URL';

  @override
  String get onboardingNotificationDeniedSystemPrefs =>
      'Teavituste luba keelatud. Palun andke luba Süsteemieelistustes.';

  @override
  String get languageForTranscription => 'Omi kasutab seda keelt transkriptsiooni, kokkuvõtete ja mälestuste jaoks.';

  @override
  String get updatedLabel => 'UUENDATUD';

  @override
  String get content => 'Sisu';

  @override
  String get phoneCallButton => 'Helista';

  @override
  String get exportStartedMayTakeFewSeconds => 'Eksport alustatud. See võib võtta mõne sekundi…';

  @override
  String dreamReportPrivacyHeld(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count aruannet hoiti privaatsuse tõttu tagasi',
      one: '1 aruanne hoiti privaatsuse tõttu tagasi',
    );
    return '$_temp0';
  }

  @override
  String firmwareBatteryTooLow(int level) {
    return 'Aku on $level%. Lae seade enne värskendamist vähemalt 15%-ni.';
  }

  @override
  String get appearance => 'Välimus';

  @override
  String noTasksOnDate(Object date) {
    return '$date pole ülesandeid';
  }

  @override
  String get deleteFlowFeedbackHint => 'Valikuline — sinu mõtted aitavad meil paremat toodet ehitada.';

  @override
  String get bluetooth => 'Bluetooth';

  @override
  String get cancelUpdate => 'Tühista värskendus';

  @override
  String get syncStatusConversationCreated => 'Vestlus loodud';

  @override
  String get reconnecting => 'Taasühendamine…';

  @override
  String get tasksToday => 'Täna';

  @override
  String taskCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count ülesannet',
      one: '1 ülesanne',
    );
    return '$_temp0';
  }

  @override
  String get noUpcomingMeetings => 'Tulevaid kohtumisi pole';

  @override
  String get invalidRecordingMultipleSpeakers => 'Vigane salvestis tuvastatud';

  @override
  String get startupFailedTitle => 'Omi käivitamine ebaõnnestus';

  @override
  String contactsSelectedCount(int count) {
    return '$count valitud';
  }

  @override
  String get skipForward10Seconds => '10 sekundit edasi';

  @override
  String get noItems => 'Punkte pole';

  @override
  String get timeout30Minutes => '30 minutit';

  @override
  String get signInSuccess => 'Sisselogimine õnnestus!';

  @override
  String get syncStatusDownloadingFromDevice => 'Allalaadimine sinu seadmest';

  @override
  String get makePrivate => 'Tee privaatseks';

  @override
  String get update => 'Uuenda';

  @override
  String get aiGenCreatingAppIcon => 'Rakenduse ikooni loomine…';

  @override
  String get wrappedIntenseDay => 'Intensiivne';

  @override
  String get raybanMetaSkipForNow => 'Jäta praegu vahele';

  @override
  String diagnosticsReconnectedIn(String duration) {
    return 'taasühendatud $duration pärast';
  }

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'Te lähete oma Unlimited paketilt üle $title paketile.';
  }

  @override
  String get appsAskWith => 'Küsi Omilt koos';

  @override
  String get noMemoriesFound => 'Mälestusi ei leitud';

  @override
  String get noMemoriesYet => 'Mälestusi pole veel';

  @override
  String get captureRecordingSeparateFailed => 'Eraldamine ebaõnnestus. Proovi uuesti.';

  @override
  String get pinAsBaseline => 'Kinnita alusena';

  @override
  String get voiceRecognitionSettings => 'Häältuvastus';

  @override
  String get chatAppsComingLater => 'Tulekul hiljem';

  @override
  String get sliderMax => 'Maks.';

  @override
  String get deleteWhileProcessingTitle => 'Töötlemine veel käib';

  @override
  String get devModeSettingsSaved => 'Seaded salvestatud!';

  @override
  String get fairUseToday => 'Täna';

  @override
  String get exportDataDesc => 'Ekspordi vestlused JSON-failina';

  @override
  String get whatsYourName => 'Mis on teie nimi?';

  @override
  String get onDeviceSlower => 'Seadmesisene transkriptsioon võib sellel seadmel olla aeglasem.';

  @override
  String get categoryProductivityLifestyle => 'Tootlikkus ja elustiil';

  @override
  String get addToYourTaskList => 'Lisada oma ülesannete loendisse?';

  @override
  String get meetingScreenshotFallbackCaption => 'Ekraanipilt sellelt koosolekult';

  @override
  String get effectCountsALittle => 'Aitab veidi';

  @override
  String get pairingTitleFriendPendant => 'Lülitage Friend Pendant sidumisrežiimi';

  @override
  String get peopleStatsIncomplete => 'Arvud võivad olla puudulikud.';

  @override
  String get tapToAddGoal => 'Puuduta eesmärgi lisamiseks';

  @override
  String get payment => 'Makse';

  @override
  String get omiDebugLog => 'Omi silumislogi';

  @override
  String get showMeetingsMenuBar => 'Kuva tulevased koosolekud menüüribal';

  @override
  String get mostInstalls => 'Enim paigaldusi';

  @override
  String chatUsageMessages(String used, String limit) {
    return 'Vestlus: $used / $limit sõnumit sel kuul';
  }

  @override
  String get chat => 'Vestlus';

  @override
  String get areYouThere => 'Kas olete seal?';

  @override
  String get highestRating => 'Kõrgeim hinnang';

  @override
  String get pleaseSpecify => 'Palun täpsusta';

  @override
  String get staging => 'Testkeskkond';

  @override
  String get cancelReasonBatteryDrain => 'Aku tühjenemise mured';

  @override
  String get apiKeys => 'API võtmed';

  @override
  String conversationsCreated(int count) {
    return '$count vestlust loodud';
  }

  @override
  String get trainingDataProgram => 'Treeningandmete programm';

  @override
  String get customBackendUrlTitle => 'Kohandatud serveri URL';

  @override
  String get omiSyncsAudioFiles => 'Omi sünkroonib seejärel helifailid serveriga';

  @override
  String get reviewAnswerMe => 'Mina';

  @override
  String get debugDiagnostics => 'Silumis- ja diagnostika';

  @override
  String get confidenceReasonNotHeard => 'veel kuulmata';

  @override
  String get doubleTapAction => 'Topeltpuudutuse tegevus';

  @override
  String get showTasksOnHomepage => 'Kuva ülesanded avalehel';

  @override
  String failedToStartUpdate(String error) {
    return 'Värskenduse alustamine ebaõnnestus: $error';
  }

  @override
  String get feedbackReasonSummaryWrongContext => 'Wrong context';

  @override
  String get pleaseProvideValidDescription => 'Palun esitage kehtiv kirjeldus';

  @override
  String get appRejectedNotice =>
      'Teie rakendus on tagasi lükatud. Palun värskendage rakenduse üksikasju ja esitage see uuesti ülevaatamiseks.';

  @override
  String get deleteOnDeviceModel => 'Kustuta mudel';

  @override
  String get languageSettingsHelperText =>
      'Rakenduse keel muudab menüüsid ja nuppe. Põhikeel mõjutab, kuidas teie salvestisi transkribeeritakse.';

  @override
  String get deleteConversationsMessage => 'See kustutab ka nende mälestused, ülesanded ja helifailid.';

  @override
  String get usageBestMonth => 'Best month';

  @override
  String get creating => 'Loomine…';

  @override
  String get microphoneAccessDescription =>
      'Omi vajab mikrofoni juurdepääsu, et salvestada teie vestlusi ja pakkuda transkriptsioone.';

  @override
  String get cancelReasonNotUsing => 'Ei kasuta piisavalt';

  @override
  String get wrappedWeveAllBeenThere => 'Me kõik oleme seal olnud!';

  @override
  String get chatAppsProblemRateLimited => 'Liiga palju katseid. Oota minut ja proovi uuesti.';

  @override
  String get selectOption => 'Vali';

  @override
  String get languageBenefits => 'Omi kasutab seda keelt transkriptsiooni, kokkuvõtete ja mälestuste jaoks.';

  @override
  String get triggerConversationIntegration => 'Käivita vestluse loomise integratsioon';

  @override
  String get integrationSetupRequired => 'Kui see on integratsioonirakendus, veenduge, et seadistamine on lõpetatud.';

  @override
  String get clickPlayToResumeOrStop => 'Klõpsake esitamisel jätkamiseks või stopp lõpetamiseks';

  @override
  String disconnectedFrom(String appName) {
    return 'Ühendus rakendusega $appName katkestatud';
  }

  @override
  String get subscribe => 'Telli';

  @override
  String get permissionsChangeAnytime => 'Saate neid igal ajal muuta jaotises Seaded > Õigused';

  @override
  String get enableRemindersAccess => 'Apple meeldetuletuste kasutamiseks lubage meeldetuletuste juurdepääs seadetes';

  @override
  String get selectProviderTemplate => 'Valige teenusepakkuja mall…';

  @override
  String get initialisingSystemAudio => 'Süsteemiheli initsialiseerimine';

  @override
  String get excellent => 'Suurepärane';

  @override
  String get chatBlockGoal => 'Eesmärk';

  @override
  String get deleteFolder => 'Kustuta kaust';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'Võtme loomine ebaõnnestus: $error';
  }

  @override
  String get whisperModelSizeSmall => 'Väike';

  @override
  String get pleaseCopyKeyNow => 'Palun kopeerige see nüüd ja kirjutage kuhugi turvalisesse kohta. ';

  @override
  String get unresolvedSpeakersNotice =>
      'Kõnelejate märgised ei pruugi selles vestluses olevate salvestiste vahel kokku sobida.';

  @override
  String get omisMemoryCleared => 'Omi mälu sinu kohta on tühjendatud';

  @override
  String get manageApp => 'Halda rakendust';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return 'Ekraanipildi loa olek: $status. Palun kontrollige Süsteemieelistusi.';
  }

  @override
  String get edit => 'Muuda';

  @override
  String get redownload => 'Laadi uuesti alla';

  @override
  String get chatBlockConversation => 'Vestlus';

  @override
  String get loadingApps => 'Rakenduste laadimine…';

  @override
  String get chatPromptPlaceholder =>
      'Sa oled suurepärane rakendus, sinu töö on vastata kasutajate küsimustele ja panna nad end hästi tundma…';

  @override
  String get stripeConnectedAccountAgreement => 'Stripe ühendatud konto leping';

  @override
  String get autoSync => 'Automaatne sünkroonimine';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'Teadmusgraaf edukalt kustutatud';

  @override
  String get optInAndOptOutOptions => 'Nõustumise ja keeldumise valikud';

  @override
  String get permissionReadMemories => 'Loe mälestusi';

  @override
  String get noSpacesInWorkspace => 'Selles tööalas ruume ei leitud';

  @override
  String get reviewYesMerge => 'Jah, ühenda';

  @override
  String get voiceMode => 'Häälrežiim';

  @override
  String get fairUseStageThrottle => 'Piiratud';

  @override
  String get deleteChatQuestion => 'Kas kustutada see vestlus?';

  @override
  String get failedToGetCallToken => 'Tokeni hankimine ebaonnestus. Kinnitage esmalt oma number.';

  @override
  String get selectTime => 'Vali aeg';

  @override
  String get sdCardProcessing => 'SD-kaardi töötlemine';

  @override
  String errorConnectingRayBanMeta(String error) {
    return 'Viga Ray-Ban Metaga ühendamisel: $error';
  }

  @override
  String get couldNotLoadImportHistory => 'Impordiajalugu ei õnnestunud laadida';

  @override
  String get noApiKeysFound => 'API võtmeid ei leitud. Alustamiseks looge üks.';

  @override
  String get appDisabledTitle => 'See rakendus on välja lülitatud ja seda ei saa paigaldada.';

  @override
  String get syncStatusBackedUp => 'Varundatud';

  @override
  String get speakerTagPromptThatsMeAction => 'See olen mina';

  @override
  String timeCompactHoursAndMins(int hours, int mins) {
    return '${hours}t ${mins}m';
  }

  @override
  String get chatPrompt => 'Vestluse viip';

  @override
  String get voicePreviewSample => 'Tere, mina olen Omi. See on minu hääl.';

  @override
  String get saved => 'Salvestatud';

  @override
  String get grantPermissionButton => 'Anna luba';

  @override
  String get subscription => 'Tellimus';

  @override
  String get capabilityFeatured => 'Esiletõstetud';

  @override
  String get pdfConversationExport => 'Vestluse eksport';

  @override
  String get unknown => 'Tundmatu';

  @override
  String get yourMeetings => 'Teie koosolekud';

  @override
  String get uploadingVoiceProfile => 'Teie hääleprofiili üleslaadimine….';

  @override
  String get apiUrl => 'API URL';

  @override
  String get reportMessage => 'Teata sõnumist';

  @override
  String get passwordLabel => 'Parool';

  @override
  String get permanentlyRemoveAllMemories => 'Eemalda püsivalt kõik mälestused Omist';

  @override
  String get transcriptionSlowerLessAccurate => 'Transkriptsioon on oluliselt aeglasem ja vähem täpne.';

  @override
  String get filterManual => 'Käsitsi';

  @override
  String get keepMyPlan => 'Säilita minu plaan';

  @override
  String get setupQuestionAge => '3. Mis on teie vanuserühm?';

  @override
  String get addAppSelectTriggerEvent => 'Valige oma rakenduse jaoks käivitussündmus';

  @override
  String get defaultWorkspace => 'Vaikimisi tööala';

  @override
  String get errorUpdatingAppStatus => 'Rakenduse oleku uuendamisel ilmnes viga.';

  @override
  String get invalidJsonConfig => 'Vigane JSON-konfiguratsioon';

  @override
  String get detailedDiagnosticMessages => 'Üksikasjalikud diagnostikasõnumid';

  @override
  String get mergingInBackground => 'Ühendamine käib taustal. See võib võtta hetke aega.';

  @override
  String get setDefaultApp => 'Määra vaikerakendus';

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Peate andma Omi-le loa ülesannete loomiseks teie $appName kontol. See avab teie brauseri autentimiseks.';
  }

  @override
  String get cleanUpEllipsis => 'Puhasta…';

  @override
  String get addTask => 'Lisa ülesanne';

  @override
  String get getCreative => 'Ole loov';

  @override
  String get captureRecordingOpenFailed => 'Seda salvestist ei saanud avada.';

  @override
  String get emptyTodoMessage => '🎉 Kõik tehtud!\nOotel ülesandeid pole';

  @override
  String get onboardingSetupTitle => 'Sinu Omi seadistamine';

  @override
  String get sharePeriodAllTime => 'Seni on Omi:';

  @override
  String get translationNotice => 'Tõlke teatis';

  @override
  String captureRecordingError(String error) {
    return 'Salvestamisel ilmnes viga: $error';
  }

  @override
  String get downloadAudio => 'Laadi heli alla';

  @override
  String get identifySpeaker => 'Tuvasta kõneleja';

  @override
  String get viewTranscript => 'Vaata transkriptsiooni';

  @override
  String get makeAllMemoriesPublic => 'Tee kõik mälestused avalikuks';

  @override
  String get xTwitter => 'X (Twitter)';

  @override
  String get frequencyOff => 'Väljas';

  @override
  String get apiEnvironment => 'API keskkond';

  @override
  String get processingTakingLonger => 'Ikka käimas — see võtab kauem aega kui tavaliselt.';

  @override
  String get firmwareUpdateFailedTitle => 'Värskendamine ebaõnnestus';

  @override
  String get unresolvedQuestions => 'Lahendamata küsimused';

  @override
  String get chatAppsMessage => 'Sõnum';

  @override
  String get dreamReportManual => 'Käsitsi';

  @override
  String get enterSttHttpEndpoint => 'Sisestage oma STT HTTP otspunkt';

  @override
  String get beforeUpdateMakeSure => 'Enne värskendamist veenduge:';

  @override
  String get transcriptionReconnecting => 'Transkriptsiooni uuesti ühendamine…';

  @override
  String get deviceName => 'Seadme nimi';

  @override
  String neoSubtitle(int count) {
    return '$count küsimust kuus';
  }

  @override
  String chatUsageProgress(String used, String limit) {
    return '$used / $limit kasutatud';
  }

  @override
  String get noChangesInReview => 'Arvustuses pole muudatusi uuendamiseks.';

  @override
  String get allMemories => 'Kõik mälestused';

  @override
  String get needMicrophonePermission =>
      'Vajame mikrofoni luba.\n\n1. Puudutage \"Anna luba\"\n2. Lubage oma iPhone\'is\n3. Kella rakendus sulgub\n4. Avage uuesti ja puudutage \"Jätka\"';

  @override
  String get keepSpeakingUntil100 => 'Rääkige edasi, kuni jõuate 100%-ni.';

  @override
  String get singleLanguageModeInfo => 'Ühe keele režiim on lubatud. Tõlge on keelatud suurema täpsuse jaoks.';

  @override
  String get thisCannotBeUndone => 'Seda ei saa tagasi võtta.';

  @override
  String get setupSkipHelp => 'Jäta vahele, ma ei soovi aidata :C';

  @override
  String get speakerTagPromptNoAction => 'Ei…';

  @override
  String labelCopied(String label) {
    return '$label kopeeritud';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'Viga heliseadme vahetamisel: $error';
  }

  @override
  String get remembering => 'Meelde jätmine';

  @override
  String get externalAppAccessDescription =>
      'Järgmistel installitud rakendustel on välised integratsioonid ja need saavad juurdepääsu teie andmetele, nagu vestlused ja mälestused.';

  @override
  String get preferences => 'Eelistused';

  @override
  String get wrappedFunDay => 'Lõbus';

  @override
  String get effectNeeded => 'Vajalik tasemeks „Kinnitatud“';

  @override
  String get importantConversationBody => 'Teil oli just oluline vestlus. Puudutage kokkuvõtte jagamiseks.';

  @override
  String whyConfidenceMenu(String level) {
    return 'Miks $level?';
  }

  @override
  String get cmdRequired => '⌘ on nõutud';

  @override
  String get completed => 'Lõpetatud';

  @override
  String get deviceOnboardingVoiceReplyStatusAlwaysSpeaker => 'Mängib valjult läbi telefoni kõlari.';

  @override
  String get effectCountsAgainst => 'Kahjustab';

  @override
  String get recaps => 'Kokkuvõtted';

  @override
  String get shareConversationQuestion => 'Kas jagada vestlust?';

  @override
  String get actionItemsCopiedToClipboard => 'Ülesanded kopeeritud lõikelauale';

  @override
  String get appleHealthManageNote =>
      'Omi kasutab Apple Health\'i juurdepääsuks Apple\'i HealthKit\'i raamistikku. Juurdepääsu saate igal ajal tühistada iOS\'i seadetes.';

  @override
  String addingToService(String serviceName) {
    return 'Lisamine $serviceName…';
  }

  @override
  String get needHelpGettingStarted => 'Vajad abi alustamiseks?';

  @override
  String get thanksForAuthorizing => 'Täname loa andmise eest!';

  @override
  String get assistantVoiceSettingsTitle => 'Hääl';

  @override
  String get cloudStorageDisabled => 'Pilvesalvestus keelatud';

  @override
  String get reviewPlayClip => 'Esita klipp';

  @override
  String get storeAudioOnCloud => 'Salvesta heli pilve';

  @override
  String get syncStatusBackingUp => 'Sünkroonimine…';

  @override
  String get peopleFilterPinned => 'Esile tõstetud';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName määratud vaikimisi kokkuvõtte rakenduseks';
  }

  @override
  String get githubRepositoryUrlRequired => 'GitHubi hoidla URL on kohustuslik';

  @override
  String get microphoneAccess => 'Mikrofoni juurdepääs';

  @override
  String get cancelSubscriptionButton => 'Tühista tellimus';

  @override
  String get signal => 'Signaal';

  @override
  String get failedToConnectAsanaRetry => 'Asanaga ühendamine ebaõnnestus. Palun proovi uuesti.';

  @override
  String get keyCreatedMessage => 'Teie uus võti on loodud. Palun kopeerige see nüüd. Te ei näe seda enam.';

  @override
  String autoRemoveSyncedCopiesDays(int days) {
    return 'Sünkroonitud koopiad kustutatakse pärast $days päeva';
  }

  @override
  String get wrappedMostCringeMoment => 'Piinlikum';

  @override
  String get activity => 'Tegevus';

  @override
  String get calendarSettings => 'Kalendri seaded';

  @override
  String get additionalFeedbackOptional => 'Lisatagasiside (valikuline)';

  @override
  String get phoneAllow => 'Luba';

  @override
  String get noDeviceConnectedUseMic => 'Ühendatud seadet pole. Kasutatakse telefoni mikrofoni.';

  @override
  String get stripeOnboardingInstructions =>
      'Palun viige Stripe\'i registreerimisprotsess lõpule oma brauseris. See leht värskendatakse automaatselt pärast lõpetamist.';

  @override
  String availableSpaceWithValue(String space) {
    return 'Saadaolev ruum: $space';
  }

  @override
  String get conversationDetails => 'Vestluse üksikasjad';

  @override
  String get wrappedYouHadFunnyMoments => 'Sul oli sel aastal naljakaid hetki!';

  @override
  String get actionReadConversations => 'Loe vestlusi';

  @override
  String speakerTagPromptIsThisPerson(String name) {
    return 'Kas see on $name?';
  }

  @override
  String get openSettings => 'Ava seaded';

  @override
  String get alwaysAvailable => 'alati saadaval.';

  @override
  String get rating1PlusStars => '1+ täht';

  @override
  String get pauseResume => 'Peata/jätka';

  @override
  String get conversationDeleted => 'Vestlus kustutatud';

  @override
  String get memoryReviewRight => 'Õige';

  @override
  String get deleteGoal => 'Kustuta eesmärk';

  @override
  String get youtube => 'YouTube';

  @override
  String get untitledConversation => 'Pealkirjata vestlus';

  @override
  String get yourOmiInsights => 'Teie Omi ülevaated';

  @override
  String get compareTranscripts => 'Võrdle transkriptsioone';

  @override
  String get pause => 'Paus';

  @override
  String get successfullyConnectedGoogle => 'Edukalt ühendatud Google\'iga!';

  @override
  String planRenewsOn(String date) {
    return 'Teie plaan uueneb $date.';
  }

  @override
  String chatAppsOpenApp(String app) {
    return 'Ava $app';
  }

  @override
  String get dailySummaryDescription => 'Saa isikupärastatud kokkuvõte päeva vestlustest teavitusena.';

  @override
  String conversationPhotosCount(int count) {
    return '$count fotot';
  }

  @override
  String get errorLoadingAudio => 'Heli laadimine ebaõnnestus';

  @override
  String get couldNotAccessFile => 'Valitud failile ei pääsenud ligi';

  @override
  String deleteGraphFailed(String error) {
    return 'Graafi kustutamine ebaõnnestus: $error';
  }

  @override
  String get reviewOpenDetailsHint => 'Avab üksikasjad';

  @override
  String get conversationTimeoutDesc => 'Valige, kui kaua vaikuses oodatakse enne vestluse automaatset lõpetamist:';

  @override
  String get transcriptionJsonPlaceholder => 'Kleepige oma JSON konfiguratsioon siia…';

  @override
  String get loadingCapabilities => 'Võimete laadimine…';

  @override
  String get activeStatus => 'Aktiivne';

  @override
  String get noDailyRecapsYet => 'Päevaseid kokkuvõtteid veel pole';

  @override
  String get wouldLikePermission => 'Sooviksime teie luba teie helisalvestiste salvestamiseks. Siin on põhjus:';

  @override
  String get chatBlockRecommendedNextSteps => 'Soovitatud järgmised sammud';

  @override
  String get tryAdjustingSearchTerms => 'Proovige kohandada otsingusõnu';

  @override
  String get connectOmiWithAI => 'Ühenda Omi AI-assistentidega';

  @override
  String get whenToReceiveDailySummary => 'Millal saada oma igapäevane kokkuvõte';

  @override
  String syncCardReadyCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count salvestust on sünkroonimiseks valmis',
      one: '1 salvestus on sünkroonimiseks valmis',
    );
    return '$_temp0';
  }

  @override
  String get yourApiKey => 'TEIE API VÕTI';

  @override
  String failedToLoadRepos(String error) {
    return 'Hoidlate laadimine ebaõnnestus: $error';
  }

  @override
  String get syncingMessages => 'Sõnumite sünkroonimine serveriga…';

  @override
  String get pleaseSelectARating => 'Palun valige hinnang';

  @override
  String get suggestedTemplates => 'Soovitatud mallid';

  @override
  String get updateAppQuestion => 'Värskenda rakendust?';

  @override
  String get frequencyDescOff => 'Pole proaktiivseid teateid';

  @override
  String get triggerAudioBytes => 'Heli baidid';

  @override
  String get confirmClearChat => 'Kas tühjendada see vestlus? Seda ei saa tagasi võtta.';

  @override
  String get dataPrivacy => 'Andmete Privaatsus';

  @override
  String get audioFromOmiWillAppearHere => 'Teie Omi seadmest pärinev heli ilmub siia';

  @override
  String get durationLabel => 'Kestus';

  @override
  String get deviceOnboardingAllSetTitle => 'Kõik on valmis';

  @override
  String msgSelectImagesError(String error) {
    return 'Viga piltide valimisel: $error';
  }

  @override
  String evidenceCardPicks(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Valitud $count soovituses',
      one: 'Valitud 1 soovituses',
    );
    return '$_temp0';
  }

  @override
  String get connectionLostDesc => 'Ühendus katkestati. Palun kontrollige oma internetiühendust ja proovige uuesti.';

  @override
  String get defaultLabel => 'Vaikimisi';

  @override
  String get raybanMetaAllowCamera => 'Luba prillide kaamera';

  @override
  String get addAppSelectCoreCapability => 'Valige veel üks põhivõime oma rakenduse jaoks';

  @override
  String get noManualMemories => 'Käsitsi lisatud mälestusi pole veel';

  @override
  String get deliveryTime => 'Edastamise aeg';

  @override
  String get defaultProjectOptional => 'Vaikimisi projekt (valikuline)';

  @override
  String get devModeInvalidAudioBytesWebhookUrl => 'Kehtetu helibaitide veebihaagi URL';

  @override
  String get ignoredVoicesTitle => 'Ignoreeritud hääled';

  @override
  String get refreshManifest => 'Värskenda manifesti';

  @override
  String get diagnosticsRightNow => 'Praegu';

  @override
  String get reviewDue => 'Tähtaeg';

  @override
  String get unmute => 'Tühista vaigistus';

  @override
  String get recordingsDeleted => 'Salvestised kustutatud.';

  @override
  String get failedToDeleteFolder => 'Kausta kustutamine ebaõnnestus';

  @override
  String get reviewAnswerOther => 'Muu';

  @override
  String get exportedConversations => 'Omi-st eksporditud vestlused';

  @override
  String get privacyPolicy => 'Privaatsuspoliitikaga';

  @override
  String get editReply => 'Muuda vastust';

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription ja on $triggerDescription.';
  }

  @override
  String errorSaving(String error) {
    return 'Salvestamise viga: $error';
  }

  @override
  String get diagnosticsConnectedFor => 'Ühendatud';

  @override
  String get callStateConnecting => 'Uhendamine…';

  @override
  String get conversationUrlNotShared => 'Vestluse URL-i ei saanud jagada.';

  @override
  String get tooShortDesc => 'Kõnet ei tuvastatud piisavalt. Palun rääkige rohkem ja proovige uuesti.';

  @override
  String get failedToShareRecap => 'Kokkuvõtet ei saanud jagada';

  @override
  String get billingMonthly => 'Kuine';

  @override
  String get developingLogic => 'Loogika arendamine';

  @override
  String get phoneContinue => 'Jatka';

  @override
  String get successfullyConnectedGitHub => 'Edukalt ühendatud GitHubiga!';

  @override
  String get failedToSubmitReview => 'Arvustuse esitamine ebaõnnestus. Palun proovi uuesti.';

  @override
  String get anyoneCanDiscover => 'Igaüks saab teie rakendust avastada';

  @override
  String get v2Undetected => 'V2 tuvastamata';

  @override
  String get usageIrlEvents => 'Päriselus üritustel';

  @override
  String get conversationPromptHint => 'nt Eraldage vestlusest ülesanded, tehtud otsused ja põhipunktid.';

  @override
  String get openProviderDocs => 'Ava dokumentatsioon';

  @override
  String get showMeetingsInMenuBar => 'Näita kohtumisi menüüribal';

  @override
  String get viewPlansAndUsage => 'Vaata Plaane ja Kasutust';

  @override
  String get buildSubmitCustomOmiApp => 'Ehita ja esita oma kohandatud Omi rakendus';

  @override
  String get failedToRefreshGoogleStatus => 'Google\'i ühenduse oleku värskendamine ebaõnnestus.';

  @override
  String get feedbackSubtitleTooExpensive => 'Teie tagasiside aitab meil leida õige tasakaalu.';

  @override
  String get startUsingOmi => 'Alusta Omi kasutamist';

  @override
  String get dreamReportLearnedWords => 'Õpitud sõnad';

  @override
  String get actionItemCreated => 'Ülesanne loodud';

  @override
  String get exportAllConversationsToJson => 'Eksportige kõik oma vestlused JSON-faili.';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'Palun kontrolli oma internetiühendust ja proovi uuesti';

  @override
  String get callStateEnded => 'Kone loppenud';

  @override
  String get phoneNumberHint => 'Telefoninumber';

  @override
  String get tasksGroupByProject => 'Rühmita projekti järgi';

  @override
  String get phoneCallsUnlimitedOnly => 'Telefonikõned Omi kaudu';

  @override
  String get frequencyDescMinimal => 'Ainult kiireloomulised asjad, umbes 1–3 päevas';

  @override
  String get changeYourName => 'Muuda oma nime';

  @override
  String get editYourReply => 'Muuda vastust';

  @override
  String get publicMemories => 'Avalikud mälestused';

  @override
  String get monthDec => 'Dets';

  @override
  String get reviewNewPersonName => 'Nende nimi';

  @override
  String get googleCalendarConnectPrompt => 'Ühenda oma Google Kalender, et siduda vestlusi kalendrisündmustega.';

  @override
  String get realtimeAudioBytes => 'Reaalajas helibaidid';

  @override
  String get trackYourGoalsOnHomepage => 'Jälgi oma isiklikke eesmärke avalehel';

  @override
  String get chatAddAttachment => 'Lisa manus';

  @override
  String get beta => 'BEETA';

  @override
  String get createMemory => 'Loo mälestus';

  @override
  String get permissionsRequiredDescription =>
      'Omi vajab mõningaid õigusi, et korralikult töötada. Palun anna need jätkamiseks.';

  @override
  String get dataCollectionMessage =>
      'Jätkates salvestatakse teie vestlused, salvestused ja isikuandmed turvaliselt meie serveritesse, et pakkuda AI-põhiseid ülevaateid ja võimaldada kõiki rakenduse funktsioone.';

  @override
  String get batteryLevel => 'Aku tase';

  @override
  String get searchCountries => 'Otsi riike...';

  @override
  String get confidenceSheetTitle => 'Kindlus';

  @override
  String get deviceModelLabel => 'Seadme mudel';

  @override
  String get noStableFirmwareFound => 'Teie seadmele ei leitud stabiilset püsivara versiooni.';

  @override
  String get noResultsFound => 'Tulemusi ei leitud';

  @override
  String get wrappedMins => 'min';

  @override
  String get chatAppsTelegramSubtitle => 'Seadistub kahe puudutusega';

  @override
  String get categoryConversationAnalysis => 'Vestluste analüüs';

  @override
  String get target => 'Sihtmärk';

  @override
  String get apiKeyRequired => 'API võti on nõutud';

  @override
  String otaUpdatedMessage(String deviceName) {
    return '$deviceName on värskendatud ja taaskäivitub ise.';
  }

  @override
  String get reconnections => 'Taasühendused';

  @override
  String errorCheckingConnection(String error) {
    return 'Ühenduse kontrollimisel ilmnes viga: $error';
  }

  @override
  String get usageMonth => 'See kuu';

  @override
  String get additionalSpeechSampleRemoved => 'Lisakõnenäidis eemaldatud';

  @override
  String get speakerTagPromptExcerptSaved => 'Vastus on selle lõigu jaoks salvestatud.';

  @override
  String get omisStorage => 'Omi salvestusruum';

  @override
  String get recordingAndTranscription => 'Salvestamine ja transkriptsioon';

  @override
  String get categoryCommunication => 'Suhtlus';

  @override
  String get wrappedYouDidIt => 'Sa tegid seda! 🎉';

  @override
  String get failedToDeleteItems => 'Punktide kustutamine ebaõnnestus';

  @override
  String speakerLabelLinesLabeled(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Märgitud $count rida',
      one: 'Märgitud 1 rida',
    );
    return '$_temp0';
  }

  @override
  String get generatingLink => 'Lingi genereerimine…';

  @override
  String get clickHereForAppBuildingGuides => 'Klõpsa siia rakenduste loomise juhiste ja dokumentatsiooni jaoks';

  @override
  String get authUrl => 'Autentimise URL';

  @override
  String get addAppCapabilityConflictWithPersona => 'Teisi võimeid ei saa Personaga valida';

  @override
  String get deviceOnboardingVoiceReplyGenericHeadphones => 'Kõrvaklapid';

  @override
  String get clearAll => 'Tühjenda kõik';

  @override
  String get noKnowledgeGraphYet => 'Teadmisgraafikut pole veel';

  @override
  String get messageReportedSuccessfully => '✅ Sõnum edukalt teatatud';

  @override
  String get paymentFailedToSetDefault => 'Vaikimisi makseviisi määramine ebaõnnestus. Proovige hiljem uuesti.';

  @override
  String get memoryReviewUpdated => 'Uuendatud.';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'Teie plaan tühistatakse $date.';
  }

  @override
  String get welcomeToOmi => 'Tere tulemast Omi';

  @override
  String get phoneFreeCallLimitReached => 'Tasuta kõnede kuulimiit on täis. See lähtestub järgmisel kuul.';

  @override
  String get omiTranscriptionOptimized =>
      'Omi reaalajas transkriptsioon on loodud reaalajas vestlusteks ja märgib, kes mida ütles.';

  @override
  String get chatAppsLoadFailedTitle => 'Vestlusrakendusi ei saanud laadida';

  @override
  String get continueWithGoogle => 'Jätka Google\'iga';

  @override
  String get setupSteps => 'Seadistamise sammud';

  @override
  String totalMemoriesCount(int count) {
    return 'Teil on kokku $count mälestust';
  }

  @override
  String get feedbackSubtitleBatteryDrain => 'See aitab meie riistvarameeskonnal paraneda.';

  @override
  String get tryIt => 'Proovi seda';

  @override
  String get chatAppsInsights => 'Omi ülevaated';

  @override
  String nFiles(int count) {
    return '$count salvestist';
  }

  @override
  String get clearChatTitle => 'Kustuta vestlus?';

  @override
  String get onlyYouCanUseTemplate => 'Ainult teie saate seda malli kasutada';

  @override
  String get raybanMetaCameraExplanation =>
      'Omi kasutab sinu prillide kaamerat, et lisada vestlustele fotosid. Võid selle vahele jätta ja kasutada ainult heli.';

  @override
  String get deviceDiagnosticsTicket => 'Support ticket code';

  @override
  String get capabilityTasks => 'Ülesanded';

  @override
  String get copyUrl => 'Kopeeri URL';

  @override
  String keepItemPublic(String item) {
    return 'Hoia $item avalik';
  }

  @override
  String get chatStarterTeachMe => 'Kas saad mulle midagi uut õpetada?';

  @override
  String get cancelReasonDetailHint => 'Hindame igasugust tagasisidet…';

  @override
  String get checkConnectionTryAgain => 'Kontrolli ühendust ja proovi uuesti.';

  @override
  String get backToConversations => 'Tagasi vestluste juurde';

  @override
  String get merge => 'Ühenda';

  @override
  String get couldNotLaunchUpgradePage => 'Uuenduse lehte ei õnnestunud avada. Palun proovige uuesti.';

  @override
  String get deviceOnboardingTranscriptionSubtitle => 'Ütle paar sõna ja vaata, kuidas need reaalajas ilmuvad';

  @override
  String get deleteOnDeviceModelConfirm => 'Kas kustutada see mudel?';

  @override
  String get reviewQuestionSpeaker => 'Kes seda ütles?';

  @override
  String updatedDate(String date) {
    return 'Uuendatud $date';
  }

  @override
  String get saveSettings => 'Salvesta Seaded';

  @override
  String get alreadyGavePermission =>
      'Olete juba andnud meile loa teie salvestiste salvestamiseks. Siin on meeldetuletus, miks me seda vajame:';

  @override
  String get appCreatedAndInstalled => 'Rakendus loodud ja installitud!';

  @override
  String get failedToRefreshNotionStatus => 'Notioni ühenduse oleku värskendamine ebaõnnestus.';

  @override
  String get deviceOnboardingProcessingQuestion => 'Töötlen sinu küsimust…';

  @override
  String get chatBlockTask => 'Ülesanne';

  @override
  String get pendantNotConnected => 'Ripats pole ühendatud. Sünkroonimiseks ühendage see.';

  @override
  String get createActionItem => 'Loo ülesanne';

  @override
  String get logsCopied => 'Logid kopeeritud';

  @override
  String get timeout5MinutesDesc => 'Lõpeta vestlus pärast 5-minutilist vaikust';

  @override
  String get msgUploadFileFailed => 'Faili üleslaadimine ebaõnnestus, palun proovige hiljem uuesti';

  @override
  String get reportMessageConfirm => 'Kas teatada sellest sõnumist?';

  @override
  String deletePersonConfirmation(String name) {
    return 'See eemaldab isiku $name häälenäidised ja seda ei saa tagasi võtta. Tema read varasemates vestlustes muutuvad nimetuteks kõnelejateks.';
  }

  @override
  String get weekdayTue => 'Tei';

  @override
  String get liveTranscript => 'Reaalajas transkriptsioon';

  @override
  String timeDaysAndHours(int days, int hours) {
    return '$days päeva $hours tundi';
  }

  @override
  String versionLabel(String version) {
    return 'Versioon $version';
  }

  @override
  String get cancelConsequenceDelay => '5-7 sekundit töötlemisviivitust (seadme mudelid)';

  @override
  String captureRecordingSeparateMessage(String recording) {
    return '$recording kuvatakse eraldi vestlusena ja seda ei rühmitata enam selle sündmusega.';
  }

  @override
  String get updateAvailableTitle => 'Värskendus on saadaval';

  @override
  String get dreamReportShadowBanner =>
      'Eelvaate režiim: Dream näitab, mida see muudaks, kuid sinu kontol ei muutu veel midagi.';

  @override
  String get sharedTasksAcceptFailed =>
      'Neid ülesandeid ei saanud vastu võtta. Võib-olla oled selle jagamise juba vastu võtnud.';

  @override
  String get appPricingLabel => 'Rakenduse hinnakujundus';

  @override
  String get reDownload => 'Laadi uuesti alla';

  @override
  String get recordWithPhoneMic => 'Salvesta telefoni mikrofoniga';

  @override
  String appDisabledOn(String date) {
    return 'Välja lülitatud $date.';
  }

  @override
  String get play => 'Esita';

  @override
  String get private => 'Privaatne';

  @override
  String get speakerTagPromptNotSureAction => 'Ei tea';

  @override
  String get showDiscardedConversationsDesc => 'Kaasa hüljatuna märgitud vestlused';

  @override
  String get captureModeLiveDescription => 'Transkribeeri reaalajas, kui räägid.';

  @override
  String get subscriptionCancelledSuccessfully =>
      'Tellimus tühistatud edukalt. See jääb aktiivseks kuni praeguse arveldusperioodi lõpuni.';

  @override
  String get tapToSetAGoal => 'Puudutage eesmärgi seadmiseks';

  @override
  String get tellUsMoreWhatWentWrong => 'Rääkige meile rohkem sellest, mis valesti läks…';

  @override
  String get downgradeToFreemiumTitle => 'Kas minna üle tasuta plaanile?';

  @override
  String get usageTasks => 'Ülesanded';

  @override
  String get chatReplyOffline => 'Ühendust ei saa luua. Kontrolli ühendust ja proovi uuesti.';

  @override
  String get makePublic => 'Tee avalikuks';

  @override
  String get authUnexpectedErrorFirebase => 'Ootamatu viga sisselogimisel, Firebase viga, palun proovige uuesti.';

  @override
  String get unlimitedConversations => 'Piiramatult vestlusi';

  @override
  String get stagingDisclaimer =>
      'Testkeskkond võib olla ebastabiilne, ebaühtlase jõudlusega ja andmed võivad kaduda. Ainult testimiseks.';

  @override
  String get captureMicrophonePermissionRequired => 'Mikrofoni luba on vajalik';

  @override
  String shareStatsInsights(String count) {
    return '✨ Pakkunud $count ülevaadet';
  }

  @override
  String get feedbackReasonSummaryIrrelevant => 'Not relevant';

  @override
  String get userIdCopiedToClipboard => 'Kasutaja ID kopeeritud';

  @override
  String get urlCopiedToClipboard => 'URL kopeeritud lõikelauale';

  @override
  String annualBillingSummary(int months, String price) {
    return '$months kuud / $price';
  }

  @override
  String chatAppsShowInAppOff(String app) {
    return 'Väljas: näed neid ainult rakenduses $app.';
  }

  @override
  String get replySentSuccessfully => 'Vastus saadeti edukalt';

  @override
  String get deviceOnboardingTurnOffTitle => 'Lülita välja';

  @override
  String get phoneStorageDesc =>
      'Kui Omi uuesti ühendub, kantakse salvestised automaatselt teie telefoni enne üleslaadimist.';

  @override
  String get callRecordingConsentDisclaimer => 'Kone salvestamine voib teie jurisdiktsioonis nousoleku nousolekut';

  @override
  String get showDiscardedConversations => 'Kuva hüljatud vestlused';

  @override
  String get calendarIntegration => 'Kalendri Integratsioon';

  @override
  String get whisperModelSizeBase => 'Baas';

  @override
  String get shareViaSms => 'Jaga SMS-i kaudu';

  @override
  String get nameMustBeAtLeast3Characters => 'Nimi peab olema vähemalt 3 tähemärki';

  @override
  String get chatDiscardRecording => 'Loobu';

  @override
  String get chatAppsProPerkText => 'Kirjuta Omile Telegramist ja iMessage\'ist';

  @override
  String get readyToSync => 'Valmis sünkroonimiseks';

  @override
  String get noAppsInCategoryYet => 'Selles kategoorias pole veel rakendusi';

  @override
  String get firmwareUpdateAvailable => 'Püsivara värskendus saadaval';

  @override
  String get modelNumber => 'Mudeli number';

  @override
  String get sortBy => 'Sorteeri';

  @override
  String get slideToUpdate => 'Värskendamiseks libistage';

  @override
  String get effectBarelyCounts => 'Aitab vaevu';

  @override
  String get onlyYouCanUse => 'Ainult teie saate seda rakendust kasutada';

  @override
  String get triggersWhenNewConversationCreated => 'Käivitatakse, kui luuakse uus vestlus.';

  @override
  String get paymentPlan => 'Maksepakett';

  @override
  String get whisperModelDesc => 'Vali seadmes transkriptsiooni mudel';

  @override
  String get askSuggestOwe => 'Mida ma inimestele veel võlgnen?';

  @override
  String get starConversation => 'Märgi vestlus tärniga';

  @override
  String get hardwareSection => 'Riistvara';

  @override
  String get transcribing => 'Transkribeerimine…';

  @override
  String get chatAppsVoiceNotesSubtitle => 'Saada häälsõnum ja Omi vastab sellele.';

  @override
  String confidenceNextVoice(String name) {
    return 'Omi vajab ka inimese $name hääleproovi. Märgista ta, kui „Jäta hääled meelde“ on sisse lülitatud.';
  }

  @override
  String get rating3PlusStars => '3+ tärni';

  @override
  String get recordingActive => 'Salvestamine aktiivne';

  @override
  String starFilter(int count) {
    return '$count tärni';
  }

  @override
  String get storageLocationLabel => 'Salvestuskoht';

  @override
  String get reviewNoChangesBody => 'Kui Omi su märkmeid korrastab, ilmuvad muudatused siia.';

  @override
  String get testPrompt => 'Testi käsku';

  @override
  String get otaUpdateUnavailable => 'See värskendus pole praegu saadaval. Proovi hiljem uuesti.';

  @override
  String get downloading => 'Allalaadimine…';

  @override
  String get welcomeBackSimple => 'Tere tulemast tagasi';

  @override
  String get sttProviderSoniox => 'Soniox';

  @override
  String get clearAllSelection => 'Tühista kõik';

  @override
  String get confidenceReasonNeverConfirmed => 'Pole kunagi kinnitatud';

  @override
  String get writeScope => 'Kirjutamine';

  @override
  String get evidenceVoiceReady => 'Hääleproov valmis';

  @override
  String get updateApp => 'Värskenda rakendust';

  @override
  String get weekdayThu => 'Nel';

  @override
  String chatUsageCostNoLimit(String used) {
    return 'Vestlus: \$$used kasutatud sel kuul';
  }

  @override
  String get configCopied => 'Konfiguratsioon kopeeritud lõikelauale';

  @override
  String get startupFailedConfigMessage =>
      'Selles Omi versioonis on seadistusprobleem. See ei ole sinu seadme viga. Võta ühendust toega ja lisa allolevad üksikasjad.';

  @override
  String get getOmiForMac => 'Hangi Omi Mac-ile';

  @override
  String get appleHealthConnectedBadge => 'Ühendatud';

  @override
  String get msgCameraNotAvailable => 'Kaamera jäädvustamine pole sellel platvormil saadaval';

  @override
  String get actionItemsDescription => 'Puudutage muutmiseks • Vajutage pikalt valimiseks • Libistage toimingute jaoks';

  @override
  String get notificationsDesc =>
      'Et Omi saaks saata sulle vestluste kokkuvõtteid, ülesannete meeldetuletusi ja vastuseid sinu rakendustest.';

  @override
  String audioUploadRetrying(String duration) {
    return 'Üleslaadimist proovitakse uuesti… $duration heli on sinu telefonis alles';
  }

  @override
  String get importStarted => 'Import algas! Saate teate, kui see on lõpetatud.';

  @override
  String get onDeviceModelDownloadFailed => 'Mudeli allalaadimine ebaõnnestus';

  @override
  String get noProjectsInWorkspace => 'Selles tööalas projekte ei leitud';

  @override
  String get helpCenter => 'Abikeskus';

  @override
  String get trainingDataBullets =>
      '• Sinu andmed aitavad parandada AI mudeleid\n• Jagatakse ainult mittetundlikke andmeid';

  @override
  String get invalidPromotionCode => 'Kehtetu sooduskood.';

  @override
  String get battery => 'Aku';

  @override
  String get clearSelection => 'Tühista valik';

  @override
  String get phoneSetupStep2Subtitle => 'Luhike kood, mille sisestate kone ajal';

  @override
  String get googleSearch => 'Google Search';

  @override
  String get charging => 'Laadimine';

  @override
  String deleteNamedPerson(String name) {
    return 'Kustuta $name';
  }

  @override
  String get chatAppsPartOfPro => 'Vestlusrakendused kuuluvad Pro juurde';

  @override
  String get invalidWebhookUrlError => 'Sisesta kehtiv webhooki URL';

  @override
  String get starConversationsToFindQuickly => 'Märkige vestlused tärniga, et neid siit kiiresti leida';

  @override
  String get permissionCreateMemories => 'Loo mälestusi';

  @override
  String get conversationIdCopied => 'Vestluse ID kopeeriti lõikelauale';

  @override
  String get chatAppsMessagesApp => 'Sõnumid';

  @override
  String get understandingWords => 'Mõistmine (sõnad)';

  @override
  String diagnosticsVerdictTroubleDetail(int count) {
    return 'Ebaõnnestunud ühendused viimase 24 tunni jooksul: $count';
  }

  @override
  String get editName => 'Muuda nime';

  @override
  String get askAboutThisConversation => 'Küsi selle kohta';

  @override
  String get useTemplateFrom => 'Kasuta malli allikast';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'Mikrofoni loa olek: $status. Palun kontrollige Süsteemieelistusi.';
  }

  @override
  String get markAsCompleted => 'Märgi lõpetatuks';

  @override
  String get urlMustEndWithSlashError => 'URL peab lõppema \"/\"';

  @override
  String get deviceOnboardingIntroTitle => 'Tutvu oma Omiga';

  @override
  String nPending(int count) {
    return '$count ootel';
  }

  @override
  String get howShouldOmiCallYou => 'Kuidas peaks Omi teid kutsuma?';

  @override
  String get preparingFormForYou => 'Vormi ettevalmistamine sinu jaoks…';

  @override
  String get deleteChat => 'Kustuta vestlus';

  @override
  String get msgPhotosPermissionDenied => 'Fotode luba keelatud. Palun lubage juurdepääs fotodele piltide valimiseks';

  @override
  String get moreWaysToRecord => 'Rohkem salvestusviise';

  @override
  String get creatingPlan => 'Plaani loomine';

  @override
  String get configCopiedToClipboard => 'Konfiguratsioon kopeeritud lõikelauale';

  @override
  String get transcribeLaterDescription =>
      'Salvesta kohe, transkribeeri siis, kui soovid. Seni jääb heli sinu telefoni.';

  @override
  String get couldNotSwitchToFreePlan => 'Tasuta plaanile lülitumine ebaõnnestus. Palun proovi uuesti.';

  @override
  String get wrappedTasksCompleted => 'ülesannet lõpetatud';

  @override
  String get deviceOnboardingTranscriptionTitle => 'Räägi oma Omisse';

  @override
  String get thankYouRequestUnderReview => 'Aitäh! Teie taotlus on läbivaatamisel. Teavitame teid pärast kinnitamist.';

  @override
  String get unpairAndForgetDevice => 'Tühista sidumine ja unusta seade';

  @override
  String get sendWebUrl => 'Saada veebi URL';

  @override
  String get noTasksForToday => 'Täna pole ülesandeid.\nKüsi Omi käest rohkem ülesandeid või loo need käsitsi.';

  @override
  String get conversationSummaryFailed => 'Kokkuvõtte loomine ebaõnnestus';

  @override
  String get realtimeTranscript => 'Reaalajas transkriptsioon';

  @override
  String nConversationsCreated(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count vestlust loodud',
      one: '1 vestlus loodud',
    );
    return '$_temp0';
  }

  @override
  String get noEmailSet => 'E-posti ei ole seatud';

  @override
  String get setDueDateAndTime => 'Määra tähtaeg ja kellaaeg';

  @override
  String get pairingDescFieldy => 'Vajutage ja hoidke seadet all, kuni ilmub valgus, et seda sisse lülitada.';

  @override
  String get maximumSecurityE2ee => 'Maksimaalne turvalisus (E2EE)';

  @override
  String get instantSpeakerLabels => 'Kohesed kõneleja sildid';

  @override
  String get resetRequestConfig => 'Lähtesta päringu konfiguratsioon vaikimisi';

  @override
  String get webhookUrlNotSet => 'Webhooki URL pole määratud';

  @override
  String get feedbackReasonRecordingOther => 'Something else';

  @override
  String get accountCutoverMigrationRollbackMessage =>
      'Tilisi on huollossa siirron peruutuksen jälkeen. Uudempaa dataa voi olla eristettynä.';

  @override
  String get cancelConsequenceQuality => '30% madalam transkriptsiooni kvaliteet (seadme mudelid)';

  @override
  String get pairingDescPlaudNote =>
      'Vajutage ja hoidke külgnuppu 2 sekundit. Punane LED vilgub, kui seade on sidumiseks valmis.';

  @override
  String get plansAndBilling => 'Plaanid ja Arveldus';

  @override
  String get deviceOnboardingVoiceReplyTitle => 'Kuula Omi vastuseid';

  @override
  String get generatingIcon => 'Ikooni genereerimine…';

  @override
  String get cleanUpBannerBody => 'Enamasti valesti kuuldud nimed. Vaata need üle ja eemalda need, mis pole päris.';

  @override
  String get speakerTagPromptSavedAsYou => 'Salvestatud sinuna';

  @override
  String get connectOmiOmiGlass => 'Ühenda Omi / OmiGlass';

  @override
  String get capabilityConversations => 'Vestlused';

  @override
  String get notificationFrequencyDescription =>
      'Kontrolli, kui sageli Omi saadab sulle proaktiivseid teavitusi ja meeldetuletusi.';

  @override
  String chatScopeAbout(String title) {
    return 'Teave: $title';
  }

  @override
  String get importHistory => 'Importimise ajalugu';

  @override
  String get getApiKey => 'Hangi API-võti';

  @override
  String get nothingInterestingRetry => 'Midagi huvitavat ei leitud,\nkas soovid uuesti proovida?';

  @override
  String get whatWouldYouLikeToCreate => 'Mida soovite luua?';

  @override
  String get pricingFree => 'Tasuta';

  @override
  String get speakerTagPromptHintIdentify => 'Sinu vastus aitab Omil selle hääle järgmine kord ära tunda.';

  @override
  String get noConversationsYet => 'Vestlusi pole veel';

  @override
  String get deviceNotMeetRequirements => 'Teie seade ei vasta seadmes transkriptsiooni nõuetele.';

  @override
  String get pressKeys => 'Vajutage klahve…';

  @override
  String get downgradeLimitDelayNotRealTime => '5–7 sekundi viivitus (mitte reaalajas)';

  @override
  String get conversationLinkCopiedToClipboard => 'Vestluse link kopeeritud lõikelauale';

  @override
  String get onboardingSetupStepMemory => 'Sinu mälu seadistamine';

  @override
  String get chatAppsTelegramOtherDevice => 'Telegram teises seadmes?';

  @override
  String get appNotFoundOrRemoved => 'See rakendus ei ole enam saadaval';

  @override
  String appsCount(String count) {
    return 'Rakendused ($count)';
  }

  @override
  String get endToEndEncryption => 'Otsast otsani krüpteerimine';

  @override
  String otaConnectFailed(String deviceName) {
    return 'Seadmega $deviceName ei saanud ühendust. Hoia see sisse lülitatuna ja lähedal ning proovi uuesti.';
  }

  @override
  String get continueButton => 'Jätka';

  @override
  String get failedToPrepareConversationForSharing =>
      'Vestluse jagamiseks ettevalmistamine ebaõnnestus. Palun proovige uuesti.';

  @override
  String get showAll => 'Kuva kõik →';

  @override
  String get speakerLabelYou => 'Teie';

  @override
  String get wrappedActionItems => 'Ülesanded';

  @override
  String failedToInstallApp(String appName) {
    return '$appName installimine ebaõnnestus. Palun proovi uuesti.';
  }

  @override
  String get searching => 'Otsimine';

  @override
  String get deviceNotCompatibleTitle => 'Seade ei ühildu';

  @override
  String get summarize => 'Kokkuvõte';

  @override
  String get exportConversationsToJson => 'Ekspordi vestlused JSON-faili';

  @override
  String makeItemPrivateExplanation(String item) {
    return 'Kui muudate $item nüüd privaatseks, lakkab see töötamast kõigil ja on nähtav ainult teile';
  }

  @override
  String get wrappedFailedToShare => 'Jagamine ebaõnnestus. Palun proovige uuesti.';

  @override
  String get cancelSubscriptionConfirmation => 'Teil on juurdepääs praeguse arveldusperioodi lõpuni.';

  @override
  String get phoneHideKeypad => 'Peida klahvistik';

  @override
  String get vadGate => 'VAD Gate';

  @override
  String get nameUpdatedSuccessfully => 'Nimi edukalt uuendatud!';

  @override
  String get photoLibrary => 'Fotokogu';

  @override
  String get chatAppsHeroMessage =>
      'Küsi oma päeva kohta, salvesta mälestusi ja halda ülesandeid Telegramist või iMessage\'ist. Sinu vestlused jäävad rakendusse, mida kasutad, ja Omi mäletab kõikjal, millest te rääkisite.';

  @override
  String get upgradeToAnnualPlan => 'Täienda aastasele plaanile';

  @override
  String get completeAuthInBrowser => 'Palun lõpetage autentimine oma brauseris. Kui olete valmis, naasake rakendusse.';

  @override
  String errorLabel(String error) {
    return 'Viga: $error';
  }

  @override
  String get durationThresholdDesc => 'Peida sellest lühemad vestlused';

  @override
  String transcriptionsPendingCount(int count) {
    return 'Ootel transkriptsioonid $count';
  }

  @override
  String get transcribeLaterNote =>
      'Töötab telefoni mikrofoni ning Omi ja Limitless seadmetega. Heli jääb sinu telefoni seni, kuni otsustad selle üles laadida.';

  @override
  String get device => 'Seade';

  @override
  String get signUpSuccess => 'Registreerimine õnnestus!';

  @override
  String get onboardingPermissions => 'Õigused';

  @override
  String get modelTooLargeWarning =>
      'See mudel on suur ja võib põhjustada rakenduse krahhi või väga aeglase töö mobiilseadmetes.\n\nSoovitatav on small või base.';

  @override
  String get showDailyScoreOnHomepage => 'Kuva päevapunktid avalehel';

  @override
  String confidenceSummaryUnverified(String name) {
    return 'Sa pole $name veel märgistanud ega kinnitanud, seega Omi pole kindel, kas ta tunneb tema häält.';
  }

  @override
  String get endConversation => 'Lõpeta vestlus';

  @override
  String get unpinAsBaseline => 'Eemalda aluselt';

  @override
  String audioSavedLocally(String duration) {
    return '$duration heli salvestatud kohapeal';
  }

  @override
  String get editMemory => '✏️ Muuda mälestust';

  @override
  String get speakerTagPromptThanks => 'Aitäh! Omi tunneb hääli nüüd paremini ära.';

  @override
  String get actionItemDescriptionEmpty => 'Ülesande kirjeldus ei saa olla tühi.';

  @override
  String get maybeLater => 'Võib-olla hiljem';

  @override
  String get daySummary => 'Päeva kokkuvõte';

  @override
  String get confirmReportMessage => 'Kas teatada sellest sõnumist?';

  @override
  String get deleteAllLimitlessConversations => 'Kustuta kõik Limitless vestlused?';

  @override
  String get selectAllTasksMenu => 'Vali kõik';

  @override
  String get syncStatusRetrying => 'Töötlemine ebaõnnestus — proovin uuesti';

  @override
  String get exportButton => 'Ekspordi';

  @override
  String get wrappedYouTalkedAboutBadge => 'Rääkisid';

  @override
  String get firmwareWarningTitle => 'Oluline: Lugege enne uuendamist';

  @override
  String get permissionTypeCreate => 'Loo';

  @override
  String get viewUsage => 'Vaata kasutust';

  @override
  String get deviceOnboardingIntroDuration => 'Umbes 1 minut';

  @override
  String get import => 'Impordi';

  @override
  String get conversationsExportStarted => 'Vestluste eksport algas. See võib võtta mõned sekundid, palun oodake.';

  @override
  String get speechToTextProvider => 'Kõne tekstiks teisendaja';

  @override
  String get languageTranslation => '100+ keele tõlge';

  @override
  String get primaryLanguage => 'Põhikeel';

  @override
  String durationSeconds(String seconds) {
    return 'Kestus: $seconds sekundit';
  }

  @override
  String get autoSyncDescription => 'Sünkrooni võrguühenduseta salvestised automaatselt, kui seade ühendatakse';

  @override
  String get debugLogs => 'Silumislogid';

  @override
  String get authorizationRevoked => 'Autoriseerimine tühistatud.';

  @override
  String get noTranscriptAvailable => 'Transkriptsioon pole saadaval';

  @override
  String get available => 'Saadaval';

  @override
  String get wrappedObsessionsLabelUpper => 'KINNISMÕTTED';

  @override
  String get professionStudent => 'Tudeng';

  @override
  String get chatAppsTryRemind => 'Tuleta mulle pühapäeval meelde emale helistada';

  @override
  String get failedToStartVerification => 'Kinnitamise alustamine ebaonnestus';

  @override
  String get failedToCreateFolder => 'Kausta loomine ebaõnnestus';

  @override
  String timeMinSingular(int count) {
    return '$count min';
  }

  @override
  String get insights => 'Ülevaated';

  @override
  String get privacyInformation => 'Privaatsusinfo';

  @override
  String get finishedConversation => 'Vestlus lõppenud?';

  @override
  String get syncGoogleAccount => 'Sünkroonige oma Google\'i kontoga';

  @override
  String get pairingTitleNeoOne => 'Lülitage Neo One sidumisrežiimi';

  @override
  String get translatedByOmi => 'tõlgitud Omi poolt';

  @override
  String get githubRepositoryUrl => 'GitHubi hoidla URL';

  @override
  String get readOnlyScope => 'Ainult lugemine';

  @override
  String get chatAppsChannelsTitle => 'Vestlusrakendused';

  @override
  String get chatAppsDoesAnswer => 'Vastab küsimustele sinu vestluste ja mälestuste kohta';

  @override
  String get wrappedFailedToStartGeneration => 'Genereerimise alustamine ebaõnnestus. Palun proovige uuesti.';

  @override
  String get storageLocationSdCard => 'SD-kaart';

  @override
  String get askSuggestDecide => 'Mida ma täna otsustasin?';

  @override
  String get close => 'Sulge';

  @override
  String get paymentMethodPayPal => 'PayPal';

  @override
  String categoryAppCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count rakendust',
      one: '1 rakendus',
    );
    return '$_temp0';
  }

  @override
  String get speakerTagPromptRecentPeople => 'Inimesed, kellega hiljuti rääkisid';

  @override
  String get actionCreateMemories => 'Loo mälestused';

  @override
  String get swipeTasksToIndent => 'Libista ülesandeid taande jaoks, lohista kategooriate vahel';

  @override
  String get createAccountTitle => 'Loo konto';

  @override
  String get modelRequired => 'Mudel nõutav';

  @override
  String get saveMemory => 'Salvesta mälestus';

  @override
  String get successfullyConnectedClickUp => 'Edukalt ühendatud ClickUpiga!';

  @override
  String get notYetSynced => 'Pole veel teie telefoniga sünkroniseeritud';

  @override
  String get pendantUpToDate => 'Ripats on ajakohane';

  @override
  String get categoryProductivityTools => 'Tootlikkuse tööriistad';

  @override
  String get refresh => 'Värskenda';

  @override
  String get cancelSyncMessage => 'Juba allalaaditud andmed salvestatakse. Võite hiljem jätkata.';

  @override
  String get selectImageFileTitle => 'Vali pildifail';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'Viga failivalija avamisel: $message';
  }

  @override
  String get failedToGenerateConversationLink => 'Vestluse lingi genereerimine ebaõnnestus';

  @override
  String get voiceFailedToTranscribe => 'Heli transkribeerimine ebaõnnestus';

  @override
  String get viewAll => 'Vaata kõiki';

  @override
  String get yourNewKey => 'Teie uus võti:';

  @override
  String get conversationMap => 'Vestluste kaart';

  @override
  String get contactSupportAction => 'Võta toega ühendust';

  @override
  String get weekdaySun => 'Püh';

  @override
  String get summaryNotFound => 'Kokkuvõtet ei leitud';

  @override
  String get shortConversationThreshold => 'Lühikese vestluse künnis';

  @override
  String get dailyRecapsDescription => 'Teie päevased kokkuvõtted ilmuvad siia pärast nende loomist';

  @override
  String get phoneCallsWithOmi => 'Koned Omiga';

  @override
  String get addAppSelectPaymentPlan => 'Valige maksepakett ja sisestage oma rakenduse hind';

  @override
  String get deleteAccountFinal =>
      'See toiming on pöördumatu ja kustutab jäädavalt teie konto ja kõik sellega seotud andmed. Kas olete kindel, et soovite jätkata?';

  @override
  String get gettingAudioFiles => 'Helifailide hankimine…';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String get port => 'Port';

  @override
  String personPinnedToast(String name) {
    return '$name tõsteti esile';
  }

  @override
  String get wrappedConversations => 'vestlust';

  @override
  String get availableOnMacMobileWeb => 'Saadaval Macis, mobiilis ja veebis';

  @override
  String get monthAug => 'aug';

  @override
  String get failedToGenerateSummary =>
      'Kokkuvõtte genereerimine ebaõnnestus. Veendu, et sul on vestlusi sellel päeval.';

  @override
  String planEndedOn(String date) {
    return 'Teie plaan lõppes $date.\nTellige uuesti kohe - teilt võetakse kohe tasu uue arveldusperioodi eest.';
  }

  @override
  String get createAnApp => 'Loo rakendus';

  @override
  String get cancelling => 'Tühistamine…';

  @override
  String get wrappedTopDaysHeader => 'Parimad päevad';

  @override
  String get keepEditing => 'Jätka muutmist';

  @override
  String get ignoredVoicesEmpty => 'Ignoreeritud hääli pole';

  @override
  String get cannotBeUndone => 'Seda ei saa tagasi võtta.';

  @override
  String get usersPayToUse => 'Kasutajad maksavad teie rakenduse kasutamise eest';

  @override
  String get maxFilesUploadError => 'Saate üles laadida ainult 4 faili korraga';

  @override
  String get yourDeviceIsUpToDate => 'Teie seade on ajakohane';

  @override
  String get unableToFetchApps =>
      'Rakenduste laadimine ebaõnnestus :(\n\nPalun kontrollige oma internetiühendust ja proovige uuesti.';

  @override
  String get entityCorrectionFailed => 'Parandust ei õnnestunud saata. Proovi uuesti.';

  @override
  String get alreadyAuthorized => 'Juba autoriseeritud';

  @override
  String get speedAccuracyLower => 'Kiirus ja täpsus võivad olla pilvemudeli omadest madalamad.';

  @override
  String siriShortcutsSearchHint(String searchPhrase) {
    return ' Saate öelda ka „$searchPhrase for what I did today“.';
  }

  @override
  String get unlimitedPlan => 'Piiramatu plaan';

  @override
  String get contactSupport => 'Võta ühendust toega?';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Maksimaalselt $count eesmärki lubatud';
  }

  @override
  String get deviceStorageNearlyFull => 'Seade on peaaegu täis — sünkroonige ruumi vabastamiseks.';

  @override
  String get setDueDate => 'Määra tähtaeg';

  @override
  String privateAppsCount(String count) {
    return 'Privaatsed rakendused ($count)';
  }

  @override
  String get selectPeople => 'Vali inimesed';

  @override
  String get capabilityChat => 'Vestlus';

  @override
  String chatAppsChannelChats(String app) {
    return '$app-i vestlused';
  }

  @override
  String get transcribeLaterTitle => 'Transkribeeri hiljem';

  @override
  String get failedToConnectAsana => 'Asanaga ühendamine ebaõnnestus';

  @override
  String get youAreOnUnlimitedPlan => 'Olete Piiramatul plaanil.';

  @override
  String get chatAppsIncludedWithPro => 'KUULUB OMI PRO JUURDE';

  @override
  String get failedToCreateKeyTryAgain => 'Võtme loomine ebaõnnestus. Palun proovige uuesti.';

  @override
  String get backgroundModeTitle => 'Taustarežiim';

  @override
  String get discardChangesMessage => 'Salvestamata muudatused lähevad kaotsi.';

  @override
  String get captureSourcePendant => 'Ripats';

  @override
  String get exportTasksWithOneTap => 'Ekspordi ülesanded ühe puudutusega!';

  @override
  String get sundayAbbr => 'P';

  @override
  String get pleaseEnterAppPrompt => 'Palun sisestage oma rakenduse viip';

  @override
  String deviceStoragePercentFull(int percent) {
    return '$percent% täis';
  }

  @override
  String get developerSettings => 'Arendaja seaded';

  @override
  String get selectYouFromList => 'Enda märkimiseks valige nimekirjast \"Sina\".';

  @override
  String get deleteNow => 'Kustuta kohe';

  @override
  String get installUpdate => 'Installi värskendus';

  @override
  String get unpairDevice => 'Tühista seadme sidumine';

  @override
  String get assistantVoice => 'Assistendi hääl';

  @override
  String get installingApp => 'Rakenduse installimine…';

  @override
  String get wrappedFunnyMomentTitle => 'Naljakas hetk';

  @override
  String onboardingFailedCheckNotification(String error) {
    return 'Teavituste loa kontrollimine ebaõnnestus: $error';
  }

  @override
  String get dreamReportRunNow => 'Käivita kohe';

  @override
  String get notSet => 'Määramata';

  @override
  String get startVoiceRecording => 'Alusta häälsalvestust';

  @override
  String get userInformation => 'Kasutajateave';

  @override
  String get wrappedStruggleLabel => 'VÄLJAKUTSE';

  @override
  String get filterInteresting => 'Ülevaated';

  @override
  String captureRecordingsCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count salvestist',
      one: '1 salvestis',
    );
    return '$_temp0';
  }

  @override
  String get addOrChangeYourPaymentMethod => 'Lisa või muuda makseviisi';

  @override
  String get unableToLoadApps => 'Rakenduste laadimine ebaõnnestus';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'Teie Omi seadme jaoks on saadaval uus püsivara värskendus ($version). Kas soovite kohe värskendada?';
  }

  @override
  String get cancelReasonTooExpensive => 'Liiga kallis';

  @override
  String get firmwareUsbWarning => 'USB-ühendus värskenduste ajal võib teie seadet kahjustada.';

  @override
  String authAccessMessage(String appName) {
    return 'Peate andma Omi-le loa juurdepääsuks teie $appName andmetele. See avab teie brauseri autentimiseks.';
  }

  @override
  String get conversationEndsManually => 'Vestlus lõpeb ainult käsitsi.';

  @override
  String get partialRecording => 'Osaline salvestus';

  @override
  String get dreamReportFeedback => 'Teatatud Omi tiimile';

  @override
  String get shareAudio => 'Jaga heli';

  @override
  String get importDataFromOtherSources => 'Impordi andmeid teistest allikatest';

  @override
  String get premiumMinutesUsed => 'Premium minutid kasutatud.';

  @override
  String get phoneCallsUpgradeButton => 'Uuenda Piiramatuks';

  @override
  String get omiUnlimited => 'Omi Unlimited';

  @override
  String get unknownDevice => 'Tundmatu';

  @override
  String get failedToStartImport => 'Impordi alustamine ebaõnnestus. Palun proovige uuesti.';

  @override
  String get searchActionItems => 'Otsi ülesandeid';

  @override
  String get whisperModel => 'Whisper mudel';

  @override
  String get searchContacts => 'Otsi kontakte';

  @override
  String get selectAllSkipsPinned =>
      '„Vali kõik“ jätab esile tõstetud inimesed vahele. Kustuta nad ükshaaval nende lehelt.';

  @override
  String get speechProfileIntro => 'Omi peab õppima teie eesmärke ja häält. Saate seda hiljem muuta.';

  @override
  String get realtimeListening => 'Reaalajas kuulamine';

  @override
  String get appNotAvailable => 'Oih! Tundub, et otsitav rakendus pole saadaval.';

  @override
  String get enterYourName => 'Sisestage oma nimi';

  @override
  String get permissionTypeTrigger => 'Päästik';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'Teie teadmisgraafik luuakse automaatselt, kui loote uusi mälestusi.';

  @override
  String get chatAppsLink => 'Link';

  @override
  String get minutes => 'minutit';

  @override
  String get actions => 'Toimingud';

  @override
  String get connectRayBanMeta => 'Ühenda Ray-Ban Meta';

  @override
  String get monthSep => 'Sept';

  @override
  String get selectContactsToShareSummary => 'Vali kontaktid vestluse kokkuvõtte jagamiseks';

  @override
  String get paymentNoneSelected => 'Midagi pole valitud';

  @override
  String get pinAction => 'Tõsta esile';

  @override
  String get monthOct => 'Okt';

  @override
  String get startRecording => 'Alusta salvestamist';

  @override
  String get somethingWentWrong => 'Midagi läks valesti! Palun proovige hiljem uuesti.';

  @override
  String largeTimeGapsDetected(String gaps) {
    return 'Tuvastati suured ajavahed ($gaps)';
  }

  @override
  String get phoneEnterNumber => 'Sisestage number';

  @override
  String get cancelConsequenceNoAccess => 'Arveldusperioodi lõpus ei ole teil enam piiramatut juurdepääsu.';

  @override
  String get appleHealthDeniedTitle => 'Apple Health\'i juurdepääs keelatud';

  @override
  String deleteItemTitle(String item) {
    return 'Kustuta $item';
  }

  @override
  String get invalidIntegrationUrl => 'Vigane integratsiooni URL';

  @override
  String get welcomeActionItemsTitle => 'Valmis ülesanneteks';

  @override
  String get updateAppConfirmation => 'Muudatused jõustuvad pärast meie meeskonna ülevaatust.';

  @override
  String get corruptedStatus => 'Rikutud';

  @override
  String get cantRateWithoutInternet => 'Ei saa rakendust hinnata ilma internetiühenduseta.';

  @override
  String get dontShowAgain => 'Ära näita uuesti';

  @override
  String get hardwareRevision => 'Riistvara versioon';

  @override
  String get trySelectingDifferentDate => 'Proovige valida teine kuupäev';

  @override
  String get learnings => 'Õpitu';

  @override
  String get failedToConnectTodoist => 'Todoistiga ühendamine ebaõnnestus';

  @override
  String get accessDataProgrammatically => 'Pääsete oma andmetele programmiliselt juurde';

  @override
  String processingProgress(int current, int total) {
    return 'Töötlemine $current/$total';
  }

  @override
  String get apiEnvSavedRestartRequired => 'Salvestatud. Sulgege ja avage rakendus uuesti, et muudatused rakenduks.';

  @override
  String get syncCardWaitingInternet => 'Ootan internetiühendust';

  @override
  String get accountCutoverOpenStore => 'Avaa kauppa';

  @override
  String get processedConversations => 'Töödeldud vestlused';

  @override
  String get holdOnPreparingForm => 'Oota, valmistame vormi teile ette';

  @override
  String get waitingForDevice => 'Ootan seadet…';

  @override
  String get learnMore => 'Loe lähemalt…';

  @override
  String get aiGenErrorWhileCreatingApp => 'Rakenduse loomisel tekkis viga';

  @override
  String get deleteAllFilesWarning =>
      'See kustutab sünkroniseeritud ja ootel salvestised. Ootel salvestisi EI ole sünkroniseeritud ja need lähevad jäädavalt kaotsi.';

  @override
  String get usageWordsHeard => 'Words heard';

  @override
  String get importDataDescription => 'Impordi andmed teistest allikatest';

  @override
  String get raybanMetaImageCaptureUnavailable => 'Pole saadaval ainult heli režiimis';

  @override
  String get appRejectedMessage =>
      'Teie rakendus lükati tagasi. Palun uuendage andmeid ja esitage uuesti läbivaatamiseks.';

  @override
  String get capturePendantDisconnectedShort => 'Omi loob ühenduse ise uuesti';

  @override
  String get improveSpeechProfileDesc =>
      'Kasutame salvestisi, et edasi treenida ja parandada teie isiklikku kõneprofiili.';

  @override
  String get voiceResponseModeTitle => 'Millal vastuseid ette lugeda';

  @override
  String get failedToDeleteItem => 'Ülesande kustutamine ebaõnnestus';

  @override
  String get firmware => 'Püsivara';

  @override
  String failedToAddToService(String serviceName) {
    return 'Lisamine $serviceName ebaõnnestus';
  }

  @override
  String get askOmiAnything => 'Küsige Omilt kõike oma elu kohta';

  @override
  String get integrationsFooter => 'Ühendage oma rakendused, et vestluses andmeid ja mõõdikuid vaadata.';

  @override
  String get loading => 'Laadimine…';

  @override
  String get showLess => 'näita vähem ↑';

  @override
  String get chatAppsNeverMessagesOthers => 'Ei kirjuta kunagi sinu eest teistele inimestele';

  @override
  String get scopeUserName => 'Kasutajanimi';

  @override
  String get mute => 'Vaigista';

  @override
  String get serverProcessesAudio => 'Server töötleb helifaile ja loob mälestusi';

  @override
  String mergeConversationsSuccessBody(int count) {
    return '$count vestlust ühendati edukalt';
  }

  @override
  String get pairingSuccessful => 'ÜHENDAMINE ÕNNESTUS';

  @override
  String get websocketUrl => 'WebSocket URL';

  @override
  String get wrappedFriend => 'Sõber';

  @override
  String get frequencyHigh => 'Kõrge';

  @override
  String get processingFailed => 'Töötlemine ebaõnnestus';

  @override
  String get dataLowercase => 'andmed';

  @override
  String deviceOfflineWakeHint(String deviceName) {
    return '$deviceName on võrguühenduseta. Vajuta selle nuppu äratamiseks ja proovi uuesti.';
  }

  @override
  String get updatedConversations => 'Uuendatud vestlused';

  @override
  String get phoneGetStarted => 'Alusta';

  @override
  String get recordingDetails => 'Salvestise üksikasjad';

  @override
  String get createApiKey => 'Loo API võti';

  @override
  String get anyoneWithLinkCanView => 'Igaüks, kellel on link, saab vaadata';

  @override
  String get noPendingTasks => 'Ootel ülesandeid pole';

  @override
  String get featureComingSoon => 'See funktsioon on peagi tulemas!';

  @override
  String get bluetoothMethodDescription =>
      'Kasutab standardset Bluetooth Low Energy ühendust. Aeglasem, kuid ei mõjuta WiFi-ühendust.';

  @override
  String get chatAppsNotConnectedTitle => 'Pole ühendatud';

  @override
  String get wrappedMostIntenseDay => 'Kõige intensiivsem';

  @override
  String get yesterday => 'Eile';

  @override
  String get requestConfiguration => 'Päringu konfiguratsioon';

  @override
  String get timeAM => 'AM';

  @override
  String autoRemoveSyncedCopiesDescription(int days) {
    return 'Kustutab kohalikud koopiad $days päeva pärast sünkroonimist. Pilvekoopiad jäävad alles.';
  }

  @override
  String get chatAppsTelegramPrivacyNote =>
      'Telegram salvestab ka sinu vestlused Omiga. Omi vastab ainult sulle, mitte kunagi teistele, ja saad ühenduse igal ajal katkestada.';

  @override
  String speakerWithId(String speakerId) {
    return 'Kõneleja $speakerId';
  }

  @override
  String get reviewNoDate => 'Puudub';

  @override
  String get transcript => 'Transkriptsioon';

  @override
  String get deviceDiagnosticsUploadFailed => 'Could not send diagnostics to support. Please try again.';

  @override
  String get noFoldersAvailable => 'Kaustad pole saadaval';

  @override
  String get addAppSelectCategory => 'Valige oma rakenduse jaoks kategooria';

  @override
  String get conversations => 'Vestlused';

  @override
  String get upgradeToUnlimited => 'Uuenda piiramatuks';

  @override
  String get deleteFlowConfirmTitle => 'Kas kustutada oma konto?';

  @override
  String get accountCutoverMigrationInProgressMessage =>
      'Tiliäsi siirretään. Tuoteominaisuudet on keskeytetty, kunnes siirto valmistuu.';

  @override
  String get permissionAllowed => 'Lubatud';

  @override
  String get pressDoneToSave => 'Vajutage valmis salvestamiseks';

  @override
  String get listening => 'Kuulamine';

  @override
  String get audioReady => 'Heli on valmis';

  @override
  String get freeForEveryone => 'Tasuta kõigile';

  @override
  String get buildingKnowledgeGraphFromMemories => 'Teadmisgraafiku loomine mälestustest…';

  @override
  String get onDeviceTranscription => 'Seadmes transkriptsioon';

  @override
  String errorWithMessage(String error) {
    return 'Viga: $error';
  }

  @override
  String get chatAppsProblemOffline => 'Oled võrguühenduseta. Kontrolli ühendust ja proovi uuesti.';

  @override
  String get callAlreadyInProgress => 'Kone on juba pooleli';

  @override
  String get reviewQuestionSpelling => 'Kuidas seda kirjutatakse?';

  @override
  String get firmwareStableConnection => 'Stabiilne ühendus';

  @override
  String get categoryOther => 'Muu';

  @override
  String get perMonthLabel => '/ kuu';

  @override
  String get onboardingYoureAllSet => 'Kõik on valmis';

  @override
  String get resumeRecording => 'Jätka salvestamist';

  @override
  String get feedbackSubtitleAudioQuality => 'Tahaksime mõista, mis läks valesti.';

  @override
  String get speakerTagPromptPlayClip => 'Esita klipp';

  @override
  String get anonymityAndPrivacy => 'Anonüümsus ja privaatsus';

  @override
  String get noMemoriesToDelete => 'Pole mälestusi kustutamiseks';

  @override
  String get syncStepProcess => 'Transkribeerimine';

  @override
  String get callStateRinging => 'Heliseb…';

  @override
  String get setupOnDevice => 'Seadista seadmes';

  @override
  String get creatorPayouts => 'Loojate väljamaksed';

  @override
  String get olderDeviceDetected => 'Tuvastati vanem seade';

  @override
  String get deletePhoneNumberWarning => 'Helistamiseks peate uuesti kinnitama';

  @override
  String get appVisibilityChangedSuccessfully =>
      'Rakenduse nähtavus muudeti edukalt. Muudatuse kajastumine võib võtta mõne minuti.';

  @override
  String get failedToCreateActionItem => 'Ülesande loomine ebaõnnestus';

  @override
  String get msgSelectFilesGenericError => 'Viga failide valimisel. Palun proovige uuesti.';

  @override
  String get pendantRecordingSyncBlocked =>
      'Pendant salvestab endiselt, seega salvestatud heli ei saa üle kanda. Salvestamise peatamiseks vajuta Pendanti nuppu ja sünkrooni uuesti.';

  @override
  String get failedToStartMerge => 'Ühendamise alustamine ebaõnnestus';

  @override
  String get shortcutChangeInstruction => 'Klõpsake kiirklahvil, et seda muuta. Tühistamiseks vajutage Escape.';

  @override
  String get notificationsAndDisplay => 'Teavitused ja kuva';

  @override
  String get getPaidThroughStripe => 'Saate oma rakenduste müügi eest tasu Stripe\'i kaudu';

  @override
  String get weekdayWed => 'Kol';

  @override
  String get send => 'Saada';

  @override
  String get nativeEngineNoDownload =>
      'Kasutatakse teie seadme natiivset kõnemootorit. Mudeli allalaadimine pole vajalik.';

  @override
  String get wrappedActions => 'tegevust';

  @override
  String get conversationTimeoutConfig => 'Kui kaua Omi ootab vaikust enne vestluse lõpetamist';

  @override
  String get mic => 'Mikrofon';

  @override
  String deviceOnboardingVoiceReplyStatusAlwaysHeadphones(String device) {
    return 'Mängib läbi numbri $device.';
  }

  @override
  String failedToSendReply(String error) {
    return 'Vastuse saatmine ebaõnnestus: $error';
  }

  @override
  String get whisperModelSizeTiny => 'Pisike';

  @override
  String get speakerTagPromptNotMeAction => 'Pole mina';

  @override
  String get setupInstructions => 'Seadistusjuhised';

  @override
  String get noLanguagesFound => 'Keeli ei leitud';

  @override
  String get experimental => 'Eksperimentaalne';

  @override
  String get continueRecording => 'Jätka salvestamist';

  @override
  String get selectDefaultRepoDesc =>
      'Valige vaikimisi hoidla probleemide loomiseks. Probleemide loomisel saate siiski määrata teise hoidla.';

  @override
  String sharedTasksTitle(String name, int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count ülesannet',
      one: '1 ülesannet',
    );
    return '$name jagas $_temp0';
  }

  @override
  String get permissionsRequiredDesc =>
      'See rakendus vajab nõuetekohaseks toimimiseks Bluetoothi ja asukoha lube. Palun lubage need seadetes.';

  @override
  String diagnosticsVerdictReconnectsDetail(String duration) {
    return 'Lühikesed katkestused, iga kord tagasi umbes $duration pärast';
  }

  @override
  String get transferring => 'Ülekandmine…';

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '$used/$limit sõna kasutatud sel kuul';
  }

  @override
  String get noChatAppsEnabled =>
      'Vestlusrakendusi pole lubatud.\nPuudutage rakenduste lisamiseks \"Luba rakendused\".';

  @override
  String get tipKeepPhoneNearby => 'Hoidke telefon lähedal kiiremaks sünkroonimiseks';

  @override
  String get authFailedToSignInWithGoogle => 'Google\'iga sisselogimine ebaõnnestus, palun proovige uuesti.';

  @override
  String get frequencyDescLow => 'Ainult olulised asjad, umbes 3–5 päevas';

  @override
  String get availableTemplates => 'Saadaolevad mallid';

  @override
  String get captureEveryMoment => 'Omi salvestab su vestlused ja kirjutab sinu eest\nkokkuvõtte ja ülesanded.';

  @override
  String get migrationErrorOccurred => 'Migreerimise ajal tekkis viga. Palun proovige uuesti.';

  @override
  String get wrappedCompletedLabel => 'Lõpetatud';

  @override
  String speakerTagPromptLabeledToast(String name) {
    return 'Märgistatud kui $name';
  }

  @override
  String get docs => 'Dokumentatsioon';

  @override
  String get dateTimeLabel => 'Kuupäev ja kellaaeg';

  @override
  String get editFolder => 'Muuda kausta';

  @override
  String get apps => 'Rakendused';

  @override
  String segmentsSingular(String count) {
    return '$count segment';
  }

  @override
  String get deviceSettings => 'Seadme seaded';

  @override
  String get offline => 'Ühenduseta';

  @override
  String get createActionItemTooltip => 'Loo uus ülesanne';

  @override
  String get forgetDevice => 'Unusta seade';

  @override
  String get reviewEntryTitle => 'Küsimused sulle';

  @override
  String get enterEmailError => 'Palun sisestage oma e-post';

  @override
  String get appDisabledOwnerHint =>
      'Paranda kõigepealt lõpp-punkt — uuesti sisselülitamisel kontrollitakse iga seadistatud URL uuesti.';

  @override
  String get chatAppsIMessageSubtitle => 'Kirjuta Omile oma telefoninumbrilt';

  @override
  String get tasksExportedOneApp => 'Ülesandeid saab eksportida korraga ühte rakendusse.';

  @override
  String transcriptSpeakerCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count kõnelejat',
      one: '1 kõneleja',
    );
    return '$_temp0';
  }

  @override
  String get saveGoal => 'Salvesta';

  @override
  String get noBatteryDataYet => 'Aku andmed puuduvad';

  @override
  String chatUsedOfLimitMessages(String used, String limit) {
    return '$used / $limit sõnumit kasutatud sel kuul';
  }

  @override
  String get backgroundActivityDesc =>
      'Et Omi jätkaks salvestamist ka siis, kui ekraan on väljas või vahetad rakendust.';

  @override
  String get addAppUpdateFailed => 'Värskendamine ebaõnnestus. Proovige hiljem uuesti';

  @override
  String get noMatchingPeople => 'Sobivaid inimesi pole';

  @override
  String get unlinkCalendarEvent => 'Eemalda kalendrisündmuse seos';

  @override
  String get regenerateRecap => 'Loo kokkuvõte uuesti';

  @override
  String get deleteSynced => 'Kustuta sünkroniseeritud';

  @override
  String get speakerTagPromptNameHint => 'Nimi';

  @override
  String get freePlan => 'Tasuta plaan';

  @override
  String get installs => 'PAIGALDUSED';

  @override
  String get publicLabel => 'Avalik';

  @override
  String get deletingMessages => 'Teie sõnumite kustutamine Omi mälust…';

  @override
  String get pendingFilesDeleted => 'Ootel salvestised kustutatud';

  @override
  String get checkUsage => 'Kontrolli kasutust';

  @override
  String get addWordsDesc => 'Nimed, terminid või ebatavalised sõnad';

  @override
  String get entityCorrectionSaved => 'Aitäh. Omi parandab selle.';

  @override
  String get categoryEducation => 'Haridus';

  @override
  String get planAndUsage => 'Plaan ja kasutus';

  @override
  String get deleteMemory => 'Kustuta mälestus';

  @override
  String get dataProtectionLevel => 'Andmekaitse tase';

  @override
  String timeDaySingular(int count) {
    return '$count päev';
  }

  @override
  String get keyCreated => 'Võti loodud';

  @override
  String get date => 'Kuupäev';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return '$itemType migreerimine… $percentage%';
  }

  @override
  String get enableLocalStorage => 'Luba kohalik salvestus';

  @override
  String get omiSays => 'Omi ütleb';

  @override
  String get appDetails => 'Rakenduse üksikasjad';

  @override
  String get loadingYourRecording => 'Salvestuse laadimine…';

  @override
  String get deleteAllLimitlessWarning =>
      'Kõik Limitlessist imporditud vestlused kustutatakse. Seda ei saa tagasi võtta.';

  @override
  String get combiningAudioFiles => 'Helifailide ühendamine…';

  @override
  String get suggestFollowUpQuestion => 'Soovita jätkuküsimust';

  @override
  String chatStarterPrompt(String kind) {
    String _temp0 = intl.Intl.selectLogic(
      kind,
      {
        'capabilities': 'Mida sa minu heaks teha saad?',
        'goal': 'Aita mul eesmärk seada',
        'activity': 'Tee kokkuvõte minu hiljutisest tegevusest',
        'improve': 'Kuidas saan end parandada?',
        'other': '',
      },
    );
    return '$_temp0';
  }

  @override
  String get speakerTagPromptIgnoredNote => 'Omi ei küsi selle hääle kohta enam';

  @override
  String get recordWithPhoneInstead => 'Salvesta hoopis telefoniga';

  @override
  String get triggerEvent => 'Käivitussündmus';

  @override
  String get waitingForTranscriptOrPhotos => 'Ootan transkriptsiooni või fotosid…';

  @override
  String get omiApiKeys => 'Omi API võtmed';

  @override
  String addNamedPersonAction(String name) {
    return 'Lisa „$name“';
  }

  @override
  String get enableDetailedDiagnosticMessages => 'Luba üksikasjalikud diagnostikateated transkriptsiooni teenusest';

  @override
  String get nameCannotBeEmpty => 'Nimi ei saa olla tühi';

  @override
  String get noTasksYet => 'Ülesandeid pole veel';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'Proovi otsingumõisteid või filtreid kohandada';

  @override
  String daySummaryForDate(String date) {
    return 'Päeva kokkuvõte · $date';
  }

  @override
  String get statusTimedOut => 'Aeg otsas';

  @override
  String chatUsageDescription(String used, String limitDisplay, String plan) {
    return 'Oled kasutanud $used oma $limitDisplay plaanist $plan.';
  }

  @override
  String get paypalMeLink => 'PayPal.me link';

  @override
  String get allMemoriesPrivateResult => 'Kõik mälestused on nüüd privaatsed';

  @override
  String get scanAgain => 'Otsi uuesti';

  @override
  String get doItAgain => 'Tee uuesti';

  @override
  String get reviewTitle => 'Ülevaatus';

  @override
  String get photos => 'Fotod';

  @override
  String get phoneNoVerifiedNumbersMessage => 'Kinnita oma number, et Omi kaudu helistada.';

  @override
  String get save => 'Salvesta';

  @override
  String get deleteAccount => 'Kustuta Konto';

  @override
  String get managePaymentMethod => 'Halda makseviisi';

  @override
  String get selectThumbnailImageTitle => 'Vali pisipilt';

  @override
  String get pairingTitleOmi => 'Lülitage Omi sisse';

  @override
  String get whatsYourPrimaryLanguage => 'Mis on teie põhikeel?';

  @override
  String get replyToReview => 'Vasta arvustusele';

  @override
  String failedToDeleteError(String error) {
    return 'Kustutamine ebaõnnestus: $error';
  }

  @override
  String get newestFirst => 'Uusimad esmalt';

  @override
  String get wrappedCreatingYourStory => 'Loome sinu\n2025 aasta lugu…';

  @override
  String get chatAppsPrivateMemories => 'Hoia privaatsed mälestused rakenduses';

  @override
  String get pleaseEnterPayPalEmail => 'Palun sisestage oma PayPali e-post';

  @override
  String get transcription => 'Transkriptsioon';

  @override
  String get yourReview => 'Teie arvustus';

  @override
  String get filesDownloadedUploadedNextTime => 'Juba allalaaditud failid laaditakse üles järgmisel korral.';

  @override
  String get phoneSetupStep3Subtitle => 'Sisseehitatud otsetranskriptsiooniga';

  @override
  String get mcpConnectionFailed => 'MCP serveriga ühendamine ebaõnnestus';

  @override
  String get chatAppsConnectTelegramTitle => 'Ühenda Telegram';

  @override
  String get createMemoryTooltip => 'Loo uus mälestus';

  @override
  String get connectDeviceMessage => 'Ühendage oma Omi seade, et pääseda juurde\nseadme seadetele ja kohandamisele';

  @override
  String get authorizingMcpServer => 'Autoriseerimine…';

  @override
  String charactersCount(int count) {
    return '$count tähemärki';
  }

  @override
  String get syncStatusUploaded => 'Üles laaditud · töödeldakse Omis';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'Palun autentimige $serviceName kaudu Seaded > Ülesannete integratsioonid';
  }

  @override
  String get setDefaultButton => 'Määra vaikimisi';

  @override
  String get resummarizingConversation => 'Vestluse uuesti kokkuvõtte tegemine…\nSee võib võtta mõne sekundi';

  @override
  String estimatedHours(int count) {
    return '~$count tund(i)';
  }

  @override
  String get chatAppsInsightsSubtitle => 'Luba Omil saata sulle siia kokkuvõte või ülevaade.';

  @override
  String get memoryAllowUse => 'Luba kasutamine';

  @override
  String get model => 'Mudel';

  @override
  String get memoryGraphTitle => 'Mälestuste graaf';

  @override
  String get endpointURL => 'Lõpp-punkti URL';

  @override
  String get wrappedShareYourWrapped => 'Jaga oma Wrapped';

  @override
  String get micGainDescBoosted => 'Võimendatud - vaiksetele keskkondadele';

  @override
  String get wrappedMinutes => 'minutit';

  @override
  String get language => 'Keel';

  @override
  String downloadErrorWithMessage(String error) {
    return 'Allalaadimise viga: $error';
  }

  @override
  String get onboardingRatingPromptNo => 'Ei';

  @override
  String get whatWouldYouLikeToRemember => 'Mida soovid meeles pidada?';

  @override
  String get deviceOnboardingMuteUnmuteDesc => 'Lülita mikrofon sisse või välja';

  @override
  String secondsCount(int count) {
    return '$count sekundit';
  }

  @override
  String get icon => 'Ikoon';

  @override
  String get realTimeTranscript => 'Reaalajas transkriptsioon';

  @override
  String get deviceOnboardingVoiceReplySample => 'Selge. Sinu järgmine kohtumine algab kahekümne minuti pärast.';

  @override
  String get noDisconnectsRecorded => 'Katkestusi pole registreeritud';

  @override
  String get filterMyApps => 'Minu rakendused';

  @override
  String get recapRegenerateCooldown => 'Palun oota mõni sekund enne uuesti loomist.';

  @override
  String get templateName => 'Malli nimi';

  @override
  String get retry => 'Proovi uuesti';

  @override
  String get sdCardSyncDescription => 'SD-kaardi sünkroonimine impordib teie mälestused SD-kaardilt rakendusse';

  @override
  String get deviceTutorial => 'Kuidas Omi\'t kasutada';

  @override
  String get noApiKeysCreateOne => 'API võtmeid pole. Looge üks alustamiseks.';

  @override
  String siriShortcutsSetupHint(String askPhrase, String questionPhrase) {
    return 'Lülitage Omi sisse jaotises Otseteed → Siri. Ütlege „$askPhrase“ või „$questionPhrase“ ja seejärel esitage oma küsimus.';
  }

  @override
  String get failedToDeleteSomeItems => 'Mõne punkti kustutamine ebaõnnestus';

  @override
  String get raybanMetaSetupDescription =>
      'Kasuta oma Ray-Ban Meta prille Omi jäädvustusseadmena vestluste ja visuaalse konteksti jaoks. Omi avab Meta AI rakenduse, et sinu prillid siduda.';

  @override
  String get tabToDo => 'Teha';

  @override
  String get otaWifiFailed => 'Wi-Fi-ga ei õnnestunud liituda. Kontrolli võrgu nime ja parooli.';

  @override
  String get changePlan => 'Muuda plaani';

  @override
  String copiedToClipboard(String title) {
    return '$title kopeeritud lõikelauale';
  }

  @override
  String get completeAuthBrowser => 'Palun lõpetage autentimine oma brauseris. Kui olete valmis, naasake rakendusse.';

  @override
  String get migrationInProgressMessage => 'Migreerimine käimas. Te ei saa kaitsetaset muuta enne selle lõpetamist.';

  @override
  String get keepSubscription => 'Jäta tellimus alles';

  @override
  String get playbackPreparingAudio => 'Heli ettevalmistamine…';

  @override
  String get cloudStorageDialogMessage =>
      'Teie reaalajas salvestised salvestatakse privaatsesse pilvesalvestusse, kui räägite.';

  @override
  String get newChat => 'Uus vestlus';

  @override
  String get paymentEnterAmountGreaterThanZero => 'Sisestage summa, mis on suurem kui 0';

  @override
  String showAllPeople(int count) {
    return 'Kuva kõik inimesed ($count)';
  }

  @override
  String deletePersonNamedTitle(String name) {
    return 'Kustuta $name?';
  }

  @override
  String get importTranscriptFiles => 'Transkriptsioonifailid';

  @override
  String get transcriptPlaceholder => 'Transkriptsioon ilmub siia…';

  @override
  String get logShared => 'Logi jagatud';

  @override
  String get deleteReasonNotUsing => 'Ei kasuta seda piisavalt';

  @override
  String diagnosticsDropsPerHour(int count) {
    return 'umbes $count tunnis';
  }

  @override
  String get wrappedProcessingDefault => 'Töötlemine…';

  @override
  String get failedToConnectGoogleTasksRetry => 'Google Tasksiga ühendamine ebaõnnestus. Palun proovi uuesti.';

  @override
  String get downloadingFromSdCard => 'Allalaadimine SD-kaardilt';

  @override
  String get firmwareFormatWarning =>
      'See püsivara vormindab SD-kaardi. Palun veenduge, et kõik võrguühenduseta andmed on enne uuendamist sünkroniseeritud.\n\nKui näete pärast selle versiooni installimist vilkuvat punast tuld, ärge muretsege. Ühendage seade lihtsalt rakendusega ja see peaks muutuma siniseks. Punane tuli tähendab, et seadme kell pole veel sünkroniseeritud.';

  @override
  String get pleaseProvidePrompt => 'Palun esitage viip';

  @override
  String get voiceResponseAlways => 'Alati';

  @override
  String get statusLabel => 'Olek';

  @override
  String get shareLogs => 'Jaga logisid';

  @override
  String get continueAnyway => 'Jätka';

  @override
  String get transferCompleteMessage => 'Ülekanne lõpetatud! Nüüd saate seda salvestist esitada.';

  @override
  String get reviewCaughtUpBody => 'Omi küsib siin ainult siis, kui tal on sind vaja.';

  @override
  String get calculatingETA => 'Arvutamine…';

  @override
  String get speechProfileTopicWork => 'Mis tööd sa teed?';

  @override
  String get considerOmiCloud => 'Kaaluge parema jõudluse saavutamiseks Omi Cloudi kasutamist.';

  @override
  String get testConversationPrompt => 'Testi vestluse viipa';

  @override
  String get deletePending => 'Kustuta ootel olevad';

  @override
  String get renameConversation => 'Nimeta ümber';

  @override
  String get batteryDrainSignificantly => 'Aku tühjenemine suureneb märkimisväärselt.';

  @override
  String get clear => 'Tühjenda';

  @override
  String get addAppEnterWebhookUrl => 'Sisestage webhook URL oma rakenduse jaoks';

  @override
  String get active => 'Aktiivne';

  @override
  String get exportStartedMessage => 'Eksport alustatud. See võib võtta mõne sekundi…';

  @override
  String get dataAccessNoticeDescription =>
      'See rakendus pääseb ligi teie andmetele. Omi AI ei vastuta selle eest, kuidas teie andmeid kasutatakse.';

  @override
  String get yourRequestUnderReview => 'Sinu taotlus on läbivaatamisel';

  @override
  String get unresolvedSpeakersMessage =>
      'Omi ei suutnud teisi hääli salvestuste vahel eristada. Puudutage kõneleja silti, et nimetada, kes räägib.';

  @override
  String downloadError(String error) {
    return 'Allalaadimise viga: $error';
  }

  @override
  String get offlineSync => 'Võrguühenduseta sünkroonimine';

  @override
  String get cancelSubscription => 'Tühista tellimus';

  @override
  String get claudeDesktopConnectorSetup =>
      'Lehel Claude Desktop → Settings → Connectors lisa kohandatud konnektor ja kleebi serveri URL. Kui Claude küsib täiustatud OAuth Client ID-d, kasuta allolevat väärtust ja jäta saladus tühjaks — ära kunagi kasuta oma MCP API võtit OAuth saladusena.';

  @override
  String get chatAppsTelegramWaiting => 'Ootan, et puudutaksid Telegramis nuppu Alusta…';

  @override
  String get tryAgain => 'Proovi uuesti';

  @override
  String get syncStatusOnDevice => 'Sinu seadmes';

  @override
  String get entityCorrectionTitle => 'Mis pole õige?';

  @override
  String peopleDeletedToast(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count inimest kustutatud',
      one: '1 inimene kustutatud',
    );
    return '$_temp0';
  }

  @override
  String get features => 'Funktsioonid';

  @override
  String get startEarning => 'Alusta teenimist! 💰';

  @override
  String get enterYourNumber => 'Sisestage oma number';

  @override
  String get addToClaudeCodeConfig => 'Lisa faili ~/.claude.json';

  @override
  String get cleanDisconnect => 'Puhas katkestus';

  @override
  String get grantContactsAccess => 'Andke juurdepaus oma kontaktidele';

  @override
  String get feedbackReasonIncorrect => 'Vale või välja mõeldud';

  @override
  String get addAppErrorSelectingImageRetry => 'Viga pildi valimisel. Proovige uuesti.';

  @override
  String get feedbackTitleNotUsing => 'Mis paneks teid Omi rohkem kasutama?';

  @override
  String get memories => 'Mälestused';

  @override
  String get capturingPhotos => 'Fotode jäädvustamine';

  @override
  String get hideApiKey => 'Peida API-võti';

  @override
  String get signUpButton => 'Registreeru';

  @override
  String get tuesdayAbbr => 'T';

  @override
  String get noApiKeys => 'API võtmeid pole veel';

  @override
  String get keyWord => 'Võti';

  @override
  String reviewAnswersConversations(int count) {
    return 'See vastus märgistab vestlusi: $count';
  }

  @override
  String get statusFailed => 'Ebaõnnestunud';

  @override
  String get installedApps => 'Paigaldatud rakendused';

  @override
  String get flashFirmware => 'Installi püsivara';

  @override
  String get conversationUrlCouldNotBeGenerated => 'Vestluse URL-i ei saanud genereerida.';

  @override
  String get reloadingApps => 'Rakenduste uuesti laadimine…';

  @override
  String get goalTitle => 'Eesmärgi pealkiri';

  @override
  String get importantConversationTitle => 'Oluline vestlus';

  @override
  String get byContinuingAgree => 'Jätkates nõustute meie ';

  @override
  String get saturdayAbbr => 'L';

  @override
  String get subscriptionReactivatedDefault =>
      'Teie tellimus on taastatud! Praegu tasu ei võeta - arve esitatakse järgmisel arveldusperioodil.';

  @override
  String get tryLatestExperimentalFeatures => 'Proovige Omi meeskonna uusimaid eksperimentaalseid funktsioone.';

  @override
  String get chatAppsEntrySubtitle => 'Räägi Omiga rakendustest, mida kasutad iga päev.';

  @override
  String get transcriptionPaused => 'Salvestamine, taasühendamine';

  @override
  String get appleHealthFeatureReadOnlyTitle => 'Ainult lugemisõigus';

  @override
  String get shareDataForTraining => 'Jaga andmeid treenimiseks';

  @override
  String get noNotificationScopesAvailable => 'Teatiste ulatusi pole saadaval';

  @override
  String disconnectFromApp(String appName) {
    return 'Katkesta ühendus rakendusega $appName?';
  }

  @override
  String get failedToConnectGoogleTasks => 'Google Tasksiga ühendamine ebaõnnestus';

  @override
  String get copyToClipboard => 'Kopeeri lõikelauale';

  @override
  String get stopRecordingConfirmation => 'Kas lõpetada salvestamine ja teha vestlusest kohe kokkuvõte?';

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'Kokkuvõtte loomine ebaõnnestus. Veenduge, et teil on selle päeva vestlusi.';

  @override
  String get monthlyLimitReached => 'Olete jõudnud oma kuulimiidini.';

  @override
  String get permissionsPageDescription =>
      'Omi kasutab neid, et ühenduda sinu seadmega, salvestada heli, töötada taustal, saata meeldetuletusi ja märkida, kus vestlused toimusid.';

  @override
  String get onboardingTellUsAboutYourself => 'Räägi meile endast';

  @override
  String get deviceOnboardingAskQuestionSubtitle =>
      'Vajuta nuppu üks kord, esita küsimus ja vajuta lõpetamiseks uuesti';

  @override
  String get filters => 'Filtrid';

  @override
  String get firmwareUpdateWarning =>
      'Ärge sulgege rakendust ega lülitage seadet välja. See võib teie seadet kahjustada.';

  @override
  String get oneSourceAtATime => 'Omi salvestab korraga ainult ühest allikast.';

  @override
  String chatAppsConnectedAs(String handle) {
    return 'Ühendatud kasutajana $handle';
  }

  @override
  String get pilotFeatures => 'Pilootfunktsioonid';

  @override
  String get selectFirmwareZip => 'Vali püsivara ZIP-fail';

  @override
  String get feedbackReasonRecordingPoorTranscription => 'Poor transcription';

  @override
  String get deleteAccountFailed => 'Sinu kontot ei õnnestunud kustutada. Palun proovi uuesti.';

  @override
  String get searchConversations => 'Otsi vestluseid';

  @override
  String get frequencyBalanced => 'Tasakaalustatud';

  @override
  String get auto => 'Automaatne';

  @override
  String get actionItemUpdatedSuccessfully => 'Ülesanne edukalt uuendatud';

  @override
  String get entityProjects => 'Projektid';

  @override
  String get signInWithApple => 'Logi sisse Apple\'iga';

  @override
  String get backendUrlLabel => 'Serveri URL';

  @override
  String confidenceSummaryLikely(String name) {
    return 'Omi tunneb inimese $name häält tavaliselt ära, kuid oled seda kinnitanud vaid paar korda.';
  }

  @override
  String get entityOpenThreads => 'Avatud teemad';

  @override
  String get deleteActionItemMessage => 'Kas kustutada see ülesanne?';

  @override
  String chatWithApp(String appName) {
    return 'Vestle rakendusega $appName';
  }

  @override
  String get editActionItem => 'Muuda ülesannet';

  @override
  String get cloudStorageEnabled => 'Pilvesalvestus lubatud';

  @override
  String get wrappedPersonalGrowth => 'Isiklik areng';

  @override
  String get chatAppsProPerkSave => 'Salvesta mälestusi ja halda ülesandeid otse vestlusest';

  @override
  String get alreadyHaveAccountLogin => 'Kas teil on juba konto? Logige sisse';

  @override
  String makeItemPublicQuestion(String item) {
    return 'Muuta $item avalikuks?';
  }

  @override
  String get usagePeakHour => 'Peak hour';

  @override
  String get addWords => 'Lisa sõnad';

  @override
  String get usageNow => 'now';

  @override
  String get usageMinutes => 'minutit';

  @override
  String availableSpace(String space) {
    return 'Saadaval ruumi: $space';
  }

  @override
  String get providingSubtitle => 'Ülesanded ja märkmed, automaatselt salvestatud.';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% lõpetamismäär';
  }

  @override
  String summaryGeneratedFor(String date) {
    return 'Kokkuvõte genereeritud kuupäevale $date';
  }

  @override
  String get selectCategory => 'Valige kategooria';

  @override
  String nProcessed(int count) {
    return '$count töödeldud';
  }

  @override
  String get privacyPolicyTitle => 'Privaatsuspoliitika';

  @override
  String get deviceMayWarmUp => 'Seade võib pikaajalisel kasutamisel soojeneda.';

  @override
  String get designingApp => 'Rakenduse kujundamine';

  @override
  String get couldNotLoadWhatsNew => 'Uudiseid ei õnnestunud laadida';

  @override
  String get doNotCloseApp => 'Palun ärge sulgege rakendust.';

  @override
  String get voiceResponseAudio => 'Loe Omi vastus ette';

  @override
  String get allTime => 'Kogu aeg';

  @override
  String get developerSettingsTitle => 'Arendaja seaded';

  @override
  String get restoreAction => 'Taasta';

  @override
  String get phoneSetupStep3Title => 'Hakake oma kontaktidele helistama';

  @override
  String get anErrorOccurredTryAgain => 'Tekkis viga. Palun proovige uuesti.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'Siin on see, millest me just rääkisime: $link';
  }

  @override
  String get playbackAudioLoadFailed => 'Heli ei õnnestunud laadida';

  @override
  String get phoneMute => 'Vaigista';

  @override
  String get captureNotTranscribing => 'Transkriptsioon puudub';

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return 'Salvestamine peatatud: $reason. Võimalik, et peate välised ekraanid uuesti ühendama või salvestamise taaskäivitama.';
  }

  @override
  String get sttProviderDeepgram => 'Deepgram';

  @override
  String get spaceKey => 'Tühik';

  @override
  String get raybanMetaOpenMetaAI => 'Ühenda Meta AI kaudu';

  @override
  String get linkEvent => 'Seo sündmus';

  @override
  String get fairUse3Day => '3-päevane periood';

  @override
  String failedToStartAppAuth(String appName) {
    return '$appName autentimise alustamine ebaõnnestus';
  }

  @override
  String get processingOnServer => 'Töötlemine serveris…';

  @override
  String errorStartingRecording(String error) {
    return 'Viga salvestamise alustamisel: $error';
  }

  @override
  String get quiet => 'Vaikne';

  @override
  String get startConversationToSeeInsights => 'Alustage Omi-ga vestlust,\net näha siinkohal oma kasutuse ülevaadet.';

  @override
  String get processAudio => 'Töötle heli';

  @override
  String get chatAppsConnectIMessageTitle => 'Kirjuta Omile ühendamiseks';

  @override
  String get chatWithOmi => 'Vestlus Omi-ga';

  @override
  String get clickToBeginRecording => 'Klõpsake salvestamise alustamiseks';

  @override
  String get confirmAndProceed => 'Kinnita ja jätka';

  @override
  String get mondayAbbr => 'E';

  @override
  String sdCardProcessingMessage(int count) {
    return 'Töödeldakse $count salvestis(t). Failid eemaldatakse SD-kaardilt pärast töötlemist.';
  }

  @override
  String get chatReplyNotSignedIn => 'Sa pole sisse logitud. Logi sisse ja proovi uuesti.';

  @override
  String deviceOnboardingVoiceReplySettingsHint(String settings, String voiceResponse) {
    return 'Saate seda igal ajal muuta numbril $settings › $voiceResponse';
  }

  @override
  String get wrappedGenerateMyWrapped => 'Genereeri minu Wrapped';

  @override
  String get reviewChangesIntro =>
      'Mida Omi on viimase 30 päeva jooksul ise muutnud. Võta tagasi kõik, mis tundub vale.';

  @override
  String get stripeReadyForPayments =>
      'Teie Stripe konto on nüüd valmis makseid vastu võtma. Saate kohe alustada oma rakenduste müügist teenimist.';

  @override
  String get appleWatchSetup => 'Apple Watch\'i seadistamine';

  @override
  String get failedToDisconnect => 'Ühenduse katkestamine ebaõnnestus';

  @override
  String get localStorageEnabled => 'Kohalik salvestus lubatud';

  @override
  String get captureSourceDesktop => 'Arvuti';

  @override
  String get serialNumber => 'Seerianumber';

  @override
  String get appleHealthFeatureSecureDesc => 'Teie Apple Health\'i andmed sünkroonitakse privaatselt teie Omi kontoga.';

  @override
  String get tryAdjustingSearch => 'Proovige otsingu või filtrite muutmist';

  @override
  String connectTo(String appName) {
    return 'Ühenda rakendusega $appName';
  }

  @override
  String get exportConversationsDescription => 'Ekspordi vestlused JSON-vormingus';

  @override
  String get featuredLabel => 'ESILETÕSTETUD';

  @override
  String get speechProfile => 'Hääleprofiil';

  @override
  String get integrations => 'Integratsioonid';

  @override
  String get hideCompletedTasks => 'Peida lõpetatud';

  @override
  String get sendRawAudioToOmi => 'Saada töötlemata heli Omisse';

  @override
  String ratingsCount(String count) {
    return '$count+ hinnangut';
  }

  @override
  String get exportShared => 'Eksport jagatud';

  @override
  String get conversationTimeout => 'Vestluse aegumine';

  @override
  String get installStableFirmware => 'Paigalda stabiilne püsivara';

  @override
  String get secureAndReliable => 'Turvaline ja usaldusväärne';

  @override
  String get exportingConversations => 'Vestluste eksportimine…';

  @override
  String get feedbackReasonRecordingFragmentedOrDuplicated => 'Fragmented or duplicated';

  @override
  String get chatAppsWaitingMessage => 'Saada sõnum rakenduses Sõnumid. See ekraan uueneb, kui Omi selle kätte saab.';

  @override
  String get onboardingSetupStepWorkspace => 'Sinu tööruumi ettevalmistamine';

  @override
  String get recap => 'Kokkuvõte';

  @override
  String get lessThanAMinute => 'Vähem kui minut';

  @override
  String get tasks => 'Ülesanded';

  @override
  String get onboardingSetupStepDevices => 'Sinu seadmete ühendamine';

  @override
  String pinPersonTitle(String name) {
    return 'Tõsta $name esile';
  }

  @override
  String get wrappedButYouPushedThrough => 'Aga sa said hakkama 💪';

  @override
  String get fetchingYourAppDetails => 'Rakenduse üksikasjade hankimine';

  @override
  String get timeout2MinutesDesc => 'Lõpeta vestlus pärast 2-minutilist vaikust';

  @override
  String get otaUpdateCancelled => 'Värskendus tühistati';

  @override
  String get usageTasksNotes => 'Tasks & notes';

  @override
  String get deviceNotConnected => 'Seade pole ühendatud';

  @override
  String get rayBanMetaMicPickerEmpty =>
      'Bluetooth-mikrofone ei leitud. Ühendage prillid iPhone\'i seadetes ja proovige uuesti.';

  @override
  String get actionItemCompleted => 'Ülesanne lõpetatud';

  @override
  String get usageSocialSettings => 'Sotsiaalsetes olukordades';

  @override
  String get from => 'alates';

  @override
  String get siriIndexSetting => 'Use Omi with Siri & Apple Intelligence';

  @override
  String get reviewReasonNotMine => 'Pole minu oma';

  @override
  String connectToDeviceName(String deviceName) {
    return 'Ühenda seadmega $deviceName';
  }

  @override
  String get onboardingComplete => 'Valmis';

  @override
  String get chatAppsShowInApp => 'Näita neid vestlusi Omi rakenduses';

  @override
  String nCompleted(int count) {
    return '$count tehtud';
  }

  @override
  String get feedbackAllGood => 'All good';

  @override
  String get syncCardUploadingTitle => 'Üleslaadimine Omisse';

  @override
  String get baselineMemory => 'Alusmälu';

  @override
  String get trainFamilyProfilesDesc =>
      'Teie salvestised aitavad meil ära tunda ja luua profiile teie sõprade ja pere jaoks.';

  @override
  String get failedToGenerateShareLink => 'Jagamislingi genereerimine ebaõnnestus';

  @override
  String get onlyYouCanSeeConversation => 'Ainult teie saate seda vestlust näha';

  @override
  String get popular => 'Populaarne';

  @override
  String get captureRecordingSeparate => 'Eralda…';

  @override
  String get allTemplates => 'Kõik mallid';

  @override
  String devicesFoundNearby(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'SEADET',
      one: 'SEADE',
    );
    return '$count $_temp0 LEITUD LÄHEDALT';
  }

  @override
  String speakerTagPromptSavedAs(String name) {
    return 'Salvestatud kui $name';
  }

  @override
  String get configureSettings => 'Seadista seaded';

  @override
  String get noRatings => 'hinnanguid pole';

  @override
  String resumingInCountdown(String countdown) {
    return 'Jätkamine ${countdown}s pärast…';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 Meelde jätnud $count mälestust';
  }

  @override
  String get clearDueDate => 'Kustuta tähtaeg';

  @override
  String get copy => 'Kopeeri';

  @override
  String get showPhoneCallButtonDesc => 'Kuva telefonikõne nupp avakuval';

  @override
  String get appleHealthFeatureReadOnlyDesc => 'Omi ei kirjuta kunagi Apple Health\'i ega muuda teie andmeid.';

  @override
  String get multipleSpeakersDescription =>
      'Tundub, et salvestises on mitu kõnelejat. Veenduge, et olete vaikses kohas ja proovige uuesti.';

  @override
  String get failedToUpdateDueDate => 'Tähtaja värskendamine ebaõnnestus';

  @override
  String get successfullyConnectedWhoop => 'Edukalt ühendatud Whoopiga!';

  @override
  String get categories => 'Kategooriad';

  @override
  String get loadingTranscript => 'Transkriptsiooni laadimine…';

  @override
  String get syncCustomSttWarningMessage =>
      'Kasutate oma transkriptsiooniteenust. Nende salvestiste sünkroonimine transkribeerib need Omi serverites ja need arvestatakse teie paketi transkriptsioonilimiidi sisse.';

  @override
  String get newRecording => 'Uus salvestus';

  @override
  String get transcriptionUnavailableRecordingSaved =>
      'Transkribeerimine pole saadaval — salvestamine jätkub ja sinu heli salvestatakse.';

  @override
  String get submittingYourApp => 'Sinu rakenduse esitamine…';

  @override
  String get failedToLinkCalendarEvent => 'Kalendrisündmuse sidumine ebaõnnestus';

  @override
  String get paypalMeLinkHint => 'paypal.me/nik';

  @override
  String get yourInformation => 'Teie Andmed';

  @override
  String get accountDeletionInProgressSignInAgain =>
      'Seda kontot kustutatakse. Logi sisse teise kontoga või oota paar minutit ja proovi uuesti.';

  @override
  String get on => 'On';

  @override
  String get diagnostics => 'Diagnostika';

  @override
  String get errorCopied => 'Veateade kopeeritud lõikelauale';

  @override
  String get lovingOmi => 'Meeldib Omi?';

  @override
  String get permissionDescReadMemories => 'See rakendus pääseb ligi sinu mälestustele.';

  @override
  String get doNotIncludeHttpInLink => 'Ärge lisage lingile http, https ega www';

  @override
  String get shareRecording => 'Jaga salvestist';

  @override
  String get memoryReviewFix => 'Paranda';

  @override
  String get selectedPlanNotAvailable => 'Valitud plaan pole saadaval. Palun proovi uuesti.';

  @override
  String get autoCreateWhenDetected => 'Loo automaatselt, kui nimi tuvastatakse';

  @override
  String get addAppSelectCapability => 'Valige oma rakenduse jaoks vähemalt üks võime';

  @override
  String get showPassword => 'Näita parooli';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Vestlused lõpevad nüüd pärast $minutes minuti pikkust vaikust';
  }

  @override
  String get updateAvailableMessage => 'Omi uus versioon on valmis – parandused ja täiustused.';

  @override
  String get nameMustBeBetweenCharacters => 'Nimi peab olema 2 kuni 40 tähemärki';

  @override
  String operatorSubtitle(int count) {
    return '$count küsimust kuus';
  }

  @override
  String conversationsDeletedCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count vestlust kustutatud',
      one: '1 vestlus kustutatud',
    );
    return '$_temp0';
  }

  @override
  String get monthlyPayoutsDescription => 'Saate igakuiseid makseid otse oma kontole, kui jõuate 10 \$ teenimiseni';

  @override
  String get dailyScoreExplanation =>
      'Teie päeva skoor põhineb ülesannete täitmisel. Täitke oma ülesanded skoori parandamiseks!';

  @override
  String get improveConnectionContent =>
      'Oleme parandanud, kuidas Omi jääb teie seadmega ühendusse. Selle aktiveerimiseks minge seadme teabe lehele, puudutage \"Katkesta seadme ühendus\" ja ühendage seade uuesti.';

  @override
  String get syncingRecordings => 'Salvestiste sünkroonimine';

  @override
  String get professionProductManager => 'Tootejuht';

  @override
  String get nameMustBeAtLeast2Characters => 'Nimi peab olema vähemalt 2 tähemärki';

  @override
  String get conversationTitle => 'Vestluse pealkiri';

  @override
  String mcpServerConnected(int count) {
    return '$count tööriista edukalt ühendatud';
  }

  @override
  String get feedbackSubtitleNotUsing => 'Tahame muuta Omi teile kasulikumaks.';

  @override
  String get exportBeforeDelete =>
      'Saate oma andmed enne konto kustutamist eksportida, kuid pärast kustutamist ei saa neid taastada.';

  @override
  String deleteTasksTitle(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Kas kustutada $count ülesannet?',
      one: 'Kas kustutada 1 ülesanne?',
    );
    return '$_temp0';
  }

  @override
  String get frequencyMaximum => 'Maksimaalne';

  @override
  String get cancelReasonSubtitle => 'Kas saate meile öelda, miks lahkute?';

  @override
  String get generatingIconStep => 'Ikooni genereerimine';

  @override
  String get storeAudioDescription =>
      'Hoidke kõik helisalvestised telefonis lokaalselt. Kui on keelatud, salvestatakse ainult ebaõnnestunud üleslaadimised ruumi säästmiseks.';

  @override
  String get unpairDeviceConfirmTitle => 'Kas tühistada seadme sidumine?';

  @override
  String get phoneCallsMaybeLater => 'Võib-olla hiljem';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'Tekkis viga: $message';
  }

  @override
  String get yourPrivacyMattersToUs => 'Teie privaatsus on meile oluline';

  @override
  String get collapseAction => 'Ahenda';

  @override
  String get friendWordOfMouth => 'Sõber';

  @override
  String get deviceOnboardingVoiceReplyStatusHeadphonesDisconnected =>
      'Kõrvaklappe pole ühendatud. Omi vaikib, kuni ühendate mõne.';

  @override
  String get connectDevice => 'Ühenda seade';

  @override
  String get deviceId => 'Seadme ID';

  @override
  String get addWordsDescription => 'Lisage sõnad, mida Omi peaks transkribeerimisel ära tundma.';

  @override
  String get userId => 'Kasutaja ID';

  @override
  String evidenceCardConfirms(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Jah $count soovitusele',
      one: 'Jah 1 soovitusele',
    );
    return '$_temp0';
  }

  @override
  String segmentsCount(int count) {
    return '$count segmenti';
  }

  @override
  String get permissionsSetupTitle => 'Saage parim kogemus';

  @override
  String get permissionTypeAccess => 'Juurdepääs';

  @override
  String get speakerTagPromptSaveVoicesBody =>
      'Omi hoiab alles lühikese häälenäidise, et neid järgmine kord ära tunda. Saad seda igal ajal seadetes muuta.';

  @override
  String get developerApi => 'Arendaja API';

  @override
  String get chargingIssues => 'Laadimisprobleemid';

  @override
  String get debugAndDiagnostics => 'Silumine ja diagnostika';

  @override
  String get failedConnections => 'Ebaõnnestunud ühendused';

  @override
  String get userIdCopied => 'Kasutaja ID kopeeritud lõikelauale';

  @override
  String get cannotReportOwnMessage => 'Te ei saa oma sõnumitest teatada.';

  @override
  String get latestVersion => 'Uusim versioon';

  @override
  String get feedbackReasonNotHelpful => 'Ei aidanud või pole asjakohane';

  @override
  String get deletePeopleMessage =>
      'See eemaldab nende häälenäidised ja seda ei saa tagasi võtta. Nende read varasemates vestlustes muutuvad nimetuteks kõnelejateks.';

  @override
  String get deviceOnboardingAllSetSubtitle => 'Puuduta rida, et seda üle vaadata või muuta.';

  @override
  String get mergeConversations => 'Ühenda vestlused';

  @override
  String get paused => 'Peatatud';

  @override
  String get updateGuide => 'Värskendamise juhend';

  @override
  String cancelBillingPeriodInfo(String date) {
    return 'Teie plaan jääb aktiivseks kuni $date. Pärast seda viiakse teid üle tasuta versioonile piiratud funktsioonidega.';
  }

  @override
  String get reconnectingToInternet => 'Internetiga uuesti ühendamine…';

  @override
  String get allFilesDeleted => 'Kõik salvestised kustutatud';

  @override
  String get paypalEmailHint => 'nik@example.com';

  @override
  String get oneWeekAgo => '1 nädal tagasi';

  @override
  String get deviceOnboardingAllSetSinglePressBadge => '1×';

  @override
  String get playbackAudioUnavailable => 'Heli pole saadaval';

  @override
  String get deviceOnboardingTryDoubleTap => 'Proovi kohe! Koputa oma Omile kaks korda';

  @override
  String get deleteReasonPrivacy => 'Privaatsusprobleemid';

  @override
  String get cleanUpPinnedNote => 'Esile tõstetud inimesi ei kaasata kunagi puhastamisse.';

  @override
  String get wrappedProductiveDay => 'Produktiivne';

  @override
  String get voiceSharedAcrossDevices => 'Sinu häälevalik on ühine mobiilis ja töölaual.';

  @override
  String get knowledgeGraphDeleted => 'Teadmiste graaf kustutatud';

  @override
  String get pressDoneToCreate => 'Vajutage valmis loomiseks';

  @override
  String get cloudStorage => 'Pilvsalvestus';

  @override
  String get howDoesItWork => 'Kuidas see töötab?';

  @override
  String get submitApp => 'Esita rakendus';

  @override
  String get searchMemories => 'Otsi mälestusi';

  @override
  String get fallNotificationTitle => 'Oih';

  @override
  String storedOnDevice(String deviceName) {
    return 'Salvestatud seadmesse $deviceName';
  }

  @override
  String get contactsPermissionRequired => 'Nõutav kontaktide luba';

  @override
  String get reviewUpdatedSuccessfully => 'Arvustus edukalt uuendatud 🚀';

  @override
  String get pleaseEnterPayPalMeLink => 'Palun sisestage oma PayPal.me link';

  @override
  String get notHelpful => 'Ei olnud kasulik';

  @override
  String get recordingsToSync => 'Sünkroonimist vajavad salvestised';

  @override
  String get categoryUtilities => 'Tööriistad';

  @override
  String get exportStarted => 'Eksport algas. See võib võtta mõne sekundi…';

  @override
  String get deviceOnboardingVoiceReplyStatusOff => 'Omi vaikib. Vastused kuvatakse endiselt rakenduses.';

  @override
  String get myGoal => 'Minu eesmärk';

  @override
  String timeHourSingular(int count) {
    return '$count tund';
  }

  @override
  String get chatToolsManifestUrl => 'Vestlustööriistade manifesti URL';

  @override
  String msgSelectFilesError(String error) {
    return 'Viga failide valimisel: $error';
  }

  @override
  String connectedToApp(String appName) {
    return 'Ühendatud rakendusega $appName';
  }

  @override
  String get entityCorrectionHint => 'Ütle Omile, mida parandada';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch ühendatud!';

  @override
  String appIntegration(String appName) {
    return '$appName integratsioon';
  }

  @override
  String get cancelReasonAudioQuality => 'Heli/transkriptsiooni kvaliteet';

  @override
  String get invalidProviderInConfig => 'Vigane pakkuja konfiguratsioonis';

  @override
  String get deselectAll => 'Tühista kõik valikud';

  @override
  String get chatAppsCodeExpiredMessage => 'Hangi uus kood ja saada see rakendusest Sõnumid.';

  @override
  String get reviewAnswerFailed => 'Vastust ei õnnestunud salvestada. Proovi uuesti.';

  @override
  String get categorySocial => 'Sotsiaalne';

  @override
  String get rating4PlusStars => '4+ tärni';

  @override
  String get couldNotOpenSmsApp => 'SMS-i rakendust ei saanud avada. Palun proovige uuesti.';

  @override
  String get chatAppsNoMessages => 'Sõnumeid pole';

  @override
  String get wrappedCelebrity => 'KUULSUS';

  @override
  String get revokeKeyQuestion => 'Tühista võti?';

  @override
  String timeMinsAndSecs(int mins, int secs) {
    return '$mins min $secs sek';
  }

  @override
  String get searchContactsHint => 'Otsi kontakte';

  @override
  String get showEventsWithoutParticipants => 'Näita sündmusi ilma osalejateta';

  @override
  String get fair => 'Rahuldav';

  @override
  String get tipAutoSync => 'Salvestised sünkroonitakse automaatselt';

  @override
  String get summaryCopiedToClipboard => 'Kokkuvõte kopeeritud lõikelauale';

  @override
  String get clearSearch => 'Tühjenda otsing';

  @override
  String get speakerTagPromptNotAPerson => 'Pole inimene';

  @override
  String get modelLabel => 'Mudel';

  @override
  String deleteItemQuestion(String item) {
    return 'Kustuta $item?';
  }

  @override
  String get enterPromoCode => 'Sisestage sooduskood';

  @override
  String get phoneNoContactsFound => 'Kontakte ei leitud';

  @override
  String countRemaining(String count) {
    return '$count järel';
  }

  @override
  String get manageYourApp => 'Halda oma rakendust';

  @override
  String get willSyncAutomatically => 'sünkroniseeritakse automaatselt';

  @override
  String get promoCode => 'Sooduskood';

  @override
  String get trackPersonalGoalsOnHomepage => 'Jälgi oma isiklikke eesmärke avalehel';

  @override
  String get memoryHistoryPartial => 'Osa mälestuste ajaloost pole saadaval. Kuvatakse seni saadud ajalugu.';

  @override
  String get sharePublicLink => 'Jaga avalikku linki';

  @override
  String get conversationTab => 'Vestlus';

  @override
  String get backgroundModeDescription => 'Hoia oma Omi salvestamas ka siis, kui rakendus on täielikult suletud.';

  @override
  String get pairingDescOmiDevkit => 'Vajutage nuppu üks kord sisselülitamiseks. LED vilgub sidumisrežiimis lillana.';

  @override
  String get callStateFailed => 'Kone ebaonnestus';

  @override
  String get githubRepositoryUrlHint => 'Link rakenduse lähtekoodi hoidlale';

  @override
  String get appIconLabel => 'App Icon';

  @override
  String get uninstallApp => 'Desinstalli rakendus';

  @override
  String get confidenceReasonNeedsVoice => 'häälenäidist veel pole';

  @override
  String get couldNotLoadApiKeys => 'API-võtmeid ei õnnestunud laadida.';

  @override
  String get fetchingStableFirmware => 'Uusima stabiilse püsivara toomine…';

  @override
  String get onDeviceModelDownloaded => 'Alla laaditud';

  @override
  String get noAPIKeys => 'API võtmed puuduvad. Looge üks alustamiseks.';

  @override
  String get phoneCallsUpsellFeature3 => 'Saajad näevad teie pärisnumbrit, mitte juhuslikku';

  @override
  String get wrappedMovieRecs => 'Filmisoovitused sõpradele';

  @override
  String msgFilePickerError(String error) {
    return 'Viga failivalija avamisel: $error';
  }

  @override
  String get professionEntrepreneur => 'Ettevõtja';

  @override
  String get recent => 'Hiljutised';

  @override
  String get permissionDescCreateMemories => 'See rakendus saab luua uusi mälestusi.';

  @override
  String get tapToComplete => 'Puuduta lõpetamiseks';

  @override
  String vocabularyWordCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count sõna',
      one: '1 sõna',
    );
    return '$_temp0';
  }

  @override
  String get deleteSyncedFilesMessage =>
      'Need salvestised on juba teie telefoniga sünkroniseeritud. Seda ei saa tagasi võtta.';

  @override
  String get cancelConsequenceSpeakers => 'Ei suuda kõnelejaid tuvastada.';

  @override
  String get aiGenFailedToGenerateApp => 'Rakenduse genereerimine ebaõnnestus. Palun proovi uuesti.';

  @override
  String get account => 'Konto';

  @override
  String get capabilityIntegrations => 'Integratsioonid';

  @override
  String get voiceSettingsAskToTag => 'Palu mul hääli märgistada';

  @override
  String get chatAppsHeroTitle => 'Vestle Omiga seal, kus sa juba vestled';

  @override
  String get myApps => 'Minu loodud';

  @override
  String get deleteRecap => 'Kustuta kokkuvõte';

  @override
  String get production => 'Tootmine';

  @override
  String get phoneRecordingBlockedByPendantBatch =>
      'Peata ripatsi režiim Transcribe Later enne telefoniga salvestamist.';

  @override
  String dataRateKbps(String rate) {
    return '$rate kbps';
  }

  @override
  String get createAKeyToGetStarted => 'Alustamiseks loo võti';

  @override
  String get pleaseSelectRating => 'Palun vali hinnang';

  @override
  String get pdfTranscriptExport => 'Transkriptsiooni eksport';

  @override
  String get newFolder => 'Uus kaust';

  @override
  String get fallNotificationBody => 'Kas te kukkusite?';

  @override
  String get scopeUserChat => 'Kasutaja vestlus';

  @override
  String get tryDifferentSearchTerm => 'Proovige teist otsingusõna';

  @override
  String get submit => 'Saada';

  @override
  String get deviceOnboardingVoiceReplySubtitle => 'Kui küsite nupuga, saab Omi oma vastuse valjusti lugeda.';

  @override
  String get showOnLockScreen => 'Kuva lukustuskuval';

  @override
  String get msgMaxImagesLimit => 'Saate valida kuni 4 pilti';

  @override
  String get wrappedOmiLifeRecap => 'Omi elu kokkuvõte';

  @override
  String get nextButton => 'Järgmine';

  @override
  String disconnectAppTitle(String appName) {
    return 'Katkesta ühendus rakendusega $appName?';
  }

  @override
  String get updateReview => 'Uuenda arvustust';

  @override
  String get noMemoriesInCategory => 'Selles kategoorias pole veel mälestusi';

  @override
  String get memoryDeleted => 'Mälestus kustutatud';

  @override
  String get connectOmiDevice => 'Ühenda Omi seade';

  @override
  String get professionSoftwareEngineer => 'Tarkvaraarendaja';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'Märgi teised segmendid sellelt kõnelejalt ($selected/$total)';
  }

  @override
  String get productName => 'Toote nimi';

  @override
  String get permissionDeniedForAppleReminders => 'Apple Reminders luba keelatud';

  @override
  String get allMemoriesAreNowPrivate => 'Kõik mälestused on nüüd privaatsed';

  @override
  String planSetToCancelOn(String date) {
    return 'Teie plaan on seatud tühistuma $date.\nTellige uuesti kohe, et säilitada oma eelised - tasu ei võeta kuni $date.';
  }

  @override
  String get deletePersonTitle => 'Kas kustutada isik?';

  @override
  String deleteItemConfirmation(String item) {
    return '$item kustutatakse. Seda ei saa tagasi võtta.';
  }

  @override
  String get appleHealthConnectCta => 'Ühenda Apple Health\'iga';

  @override
  String segmentsPlural(String count) {
    return '$count segmenti';
  }

  @override
  String get syncCardDownloadingTitle => 'Allalaadimine sinu seadmest';

  @override
  String additionalSampleIndex(String index) {
    return 'Lisanäidis $index';
  }

  @override
  String get descriptionLabel => 'Kirjeldus';

  @override
  String get failedToClearDueDate => 'Tähtaja kustutamine ebaõnnestus';

  @override
  String get timeout4HoursDesc => 'Lõpeta vestlus pärast 4-tunnist vaikust';

  @override
  String get noSyncedRecordingsYet => 'Sünkroonitud salvestisi pole veel';

  @override
  String dreamReportDropped(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count vanemat muudatust vahele jäetud',
      one: '1 vanem muudatus vahele jäetud',
    );
    return '$_temp0';
  }

  @override
  String get claudeCode => 'Claude Code';

  @override
  String get noPendingRecordings => 'Ootel salvestisi pole';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'Öelge meile, kuidas te soovite, et teid pöördutaks. See aitab isikupärastada teie Omi kogemust.';

  @override
  String get updateSummaryWithNewNames => 'Uuenda kokkuvõtet uute nimedega';

  @override
  String get setWhenConversationsAutoEnd => 'Kui kaua Omi ootab vaikust enne vestluse lõpetamist';

  @override
  String get successfullyConnectedGoogleTasks => 'Edukalt ühendatud Google Tasksiga!';

  @override
  String get confirmUpgrade => 'Kinnita täiendus';

  @override
  String get speechToTextProviderDesc => 'Vali transkriptsiooniks kasutatav teenus';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Viga Apple Watch\'iga ühendamisel: $error';
  }

  @override
  String get instagram => 'Instagram';

  @override
  String sampleNumber(int number) {
    return 'Näidis $number';
  }

  @override
  String get popularApps => 'Populaarsed rakendused';

  @override
  String get micGainDescSlightlyBoosted => 'Veidi võimendatud - tavakasutus';

  @override
  String get promptMustBeAtLeast10Characters => 'Viip peab olema vähemalt 10 tähemärki';

  @override
  String get chatAppsEntryRowSubtitle => 'Telegram, iMessage ja palju muud';

  @override
  String get estimatedSizeLabel => 'Eeldatav suurus';

  @override
  String get mcpServerDesc => 'Ühendage AI assistendid oma andmetega';

  @override
  String get disconnectHistory => 'Katkestuste ajalugu';

  @override
  String get downgradeLimitDelay => '5–7 sekundi pikkune viivitus';

  @override
  String get msgSelectImagesGenericError => 'Viga piltide valimisel. Palun proovige uuesti.';

  @override
  String get audioPlaybackUnavailable => 'Helifail ei ole esitamiseks saadaval';

  @override
  String get byClickingConnectNow => 'Klõpsates \"Ühenda kohe\" nõustute';

  @override
  String get signalStrength => 'Signaali tugevus';

  @override
  String get tellUsPrimaryLanguage => 'Öelge meile oma põhikeel';

  @override
  String get diagnosticsShareFailed => 'Diagnostikat ei õnnestunud jagada. Proovi uuesti.';

  @override
  String get createKeyToStart => 'Alustamiseks looge võti';

  @override
  String generatedBy(String appName) {
    return 'Loonud $appName';
  }

  @override
  String shareStatsListened(String minutes) {
    return '🎧 Kuulanud $minutes minutit';
  }

  @override
  String get getOmiDevice => 'Hangi Omi seade';

  @override
  String get newTask => 'Uus ülesanne';

  @override
  String get conversationPrompt => 'Vestluse viip';

  @override
  String get otaWifiConnected => 'Wi-Fi-ga ühendatud';

  @override
  String get dismiss => 'Peida';

  @override
  String get webhooks => 'Veebikongid';

  @override
  String get raybanMetaCamera => 'Kaamera';

  @override
  String get recapRegenerateNoConversations => 'Selle päeva jaoks pole vestlusi, mida kokku võtta.';

  @override
  String pendantMinutesStored(int minutes) {
    return '~$minutes min salvestatud';
  }

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName ühendus katkestatud';
  }

  @override
  String get normal => 'Tavaline';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch pole veel kättesaadav. Veenduge, et Omi rakendus oleks teie kellas avatud.';

  @override
  String get connectionGuide => 'Ühendamisjuhend';

  @override
  String get syncStepProcessDesc => 'Omi muudab heli vestluseks';

  @override
  String get couldNotLoadPlans => 'Saadaolevaid plaane ei õnnestunud laadida. Palun proovi uuesti.';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '$used/$limit min kasutatud sel kuul';
  }

  @override
  String get learnMoreLink => 'lisateave';

  @override
  String get unpairDeviceDialogMessage =>
      'See tühistab seadme sidumise, et seda saaks ühendada teise telefoniga. Peate minema Seaded > Bluetooth ja unustama seadme protsessi lõpetamiseks.';

  @override
  String get authFailedToRetrieveToken => 'Firebase tokeni hankimine ebaõnnestus, palun proovige uuesti.';

  @override
  String get aiGenFailedToCreateApp => 'Rakenduse loomine ebaõnnestus';

  @override
  String get appAndDeviceCopied => 'Rakenduse ja seadme üksikasjad kopeeritud';

  @override
  String get noProcessedRecordings => 'Töödeldud salvestisi pole veel';

  @override
  String get transcriptTab => 'Transkriptsioon';

  @override
  String get permissionDescReadConversations => 'See rakendus pääseb ligi sinu vestlustele.';

  @override
  String get tryAnotherApp => 'Proovi teist rakendust';

  @override
  String get subscriptionSetToCancel => 'Teie tellimus on seatud tühistuma perioodi lõpus.';

  @override
  String chatAppsCodeExpiresIn(String time) {
    return 'Kood aegub $time pärast';
  }

  @override
  String get authFailedToSignInWithApple => 'Apple\'iga sisselogimine ebaõnnestus, palun proovige uuesti.';

  @override
  String get feedbackReasonIgnoredInstructions => 'Ei järginud juhiseid';

  @override
  String get startupFailedDetails => 'Üksikasjad';

  @override
  String get deleteMeetingScreenshotTitle => 'Kas kustutada ekraanipilt?';

  @override
  String get chatAppsNotConnectedMessage => 'See vestlusrakendus on lahti ühendatud.';

  @override
  String get aboutOmiApiKeys => 'Omi API võtmete kohta';

  @override
  String get tiktok => 'TikTok';

  @override
  String get maxFilesLimit => 'Korraga saate üles laadida ainult 4 faili';

  @override
  String get legalNotice =>
      'Õiguslik teade: Häälsalvestuste salvestamise ja salvestamise seaduslikkus võib sõltuvalt teie asukohast ja selle funktsiooni kasutamisest erineda. Teie kohustus on tagada kohalike seaduste ja määruste järgimine.';

  @override
  String get wrappedYourTopDays => 'Sinu parimad päevad';

  @override
  String get addMcpServer => 'Lisa MCP server';

  @override
  String publicAppsCount(String count) {
    return 'Avalikud rakendused ($count)';
  }

  @override
  String get noExternalAppsHaveAccess => 'Ühelgi välisel rakendusel pole juurdepääsu teie andmetele.';

  @override
  String get captureStarting => 'Käivitamine…';

  @override
  String get downloadingAudioProgress => 'Heli allalaadimine';

  @override
  String get audioBytes => 'Helibaite';

  @override
  String batteryLevelSemantics(int level) {
    return 'Aku $level%';
  }

  @override
  String captureRecordedBy(String devices) {
    return 'Salvestas $devices';
  }

  @override
  String get chatAppsRepliesOnlyNote => 'Omi vastab ainult sulle. Ta ei kirjuta kunagi esimesena.';

  @override
  String get hideTranscript => 'Peida transkriptsioon';

  @override
  String get permissionReadConversations => 'Loe vestlusi';

  @override
  String get installed => 'Paigaldatud';

  @override
  String get paymentEnterValidAmount => 'Sisestage kehtiv summa';

  @override
  String get sttLanguageOverride => 'Muuda';

  @override
  String get appInterfaceSectionTitle => 'Rakenduse liides';

  @override
  String get searchLanguages => 'Otsi keeli';

  @override
  String get otherSource => 'Muu';

  @override
  String get pairingDescOmiGlass => 'Vajutage ja hoidke külgnuppu 3 sekundit sisselülitamiseks.';

  @override
  String get signOut => 'Logi Välja';

  @override
  String shareStatsWords(String words) {
    return '🧠 Mõistnud $words sõna';
  }

  @override
  String verifiedDaysAgo(int days) {
    return 'Kinnitatud ${days}p tagasi';
  }

  @override
  String get captureModeLater => 'Hiljem';

  @override
  String get enableMoreApps => 'Luba rohkem rakendusi';

  @override
  String get frequencyDescBalanced => 'Kasulikud soovitused, umbes 5–8 päevas';

  @override
  String get startYourFirstRecording => 'Alustage oma esimest salvestust';

  @override
  String get transcriptionPausedReconnecting => 'Salvestamine jätkub — ühenduse taastamine transkriptsiooniga…';

  @override
  String get basicPlan => 'Tasuta plaan';

  @override
  String get user => 'Kasutaja';

  @override
  String get pinPersonDescription =>
      'Esile tõstetud inimesed jäävad sinu Inimeste loendi ülaossa ega ole Puhastamisega eemaldatavad.';

  @override
  String get reviewProject => 'Projekt';

  @override
  String get keyboardShortcuts => 'Kiirklahvid';

  @override
  String get diagnosticsFailBadge => 'Ebaõnnestus';

  @override
  String get debugLogCleared => 'Silumislogi tühjendatud';

  @override
  String get errorConnectingToStripe => 'Viga Stripe\'iga ühendamisel! Palun proovige hiljem uuesti.';

  @override
  String get tapPlusToStartRecording => 'Salvestamise alustamiseks puuduta salvestusnuppu';

  @override
  String get permissionBlockedHint => 'Seadetes välja lülitatud. Selle kasutamiseks luba see seal.';

  @override
  String get downloadingAudio => 'Heli allalaadimine…';

  @override
  String failedToRevokeApiKey(String error) {
    return 'API võtme tühistamine ebaõnnestus: $error';
  }

  @override
  String largeTimeGapDetected(String gap) {
    return 'Tuvastati suur ajavahe ($gap)';
  }

  @override
  String get customFirmwareWarning =>
      'Kohandatud püsivara võib seadme kasutuskõlbmatuks muuta. Veendu, et see on kehtiv Omi püsivara järk, ja ära katkesta ühendust uuendamise ajal.';

  @override
  String get wrapped2025 => 'Kokkuvõte 2025';

  @override
  String get showApiKey => 'Näita API-võtit';

  @override
  String get agreeAndContinue => 'Nõustun ja jätka';

  @override
  String get connectExternalAiTools => 'Ühenda välised AI tööriistad';

  @override
  String get batteryFullyChargedTitle => 'Omi on täielikult laetud';

  @override
  String get appReEnableFailedTitle => 'Uuesti sisselülitamine ebaõnnestus';

  @override
  String get onboardingYourName => 'Sinu nimi';

  @override
  String get searchApps => 'Otsi rakendusi';

  @override
  String get weak => 'Nõrk';

  @override
  String get tellUsMore => 'Rääkige meile rohkem (valikuline)';

  @override
  String confidenceReasonPicked(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Valitud $count soovituses',
      one: 'Valitud 1 soovituses',
    );
    return '$_temp0';
  }

  @override
  String chatAppsDisconnectFooter(String app) {
    return 'Ühenduse katkestamine kustutab ajaloo, mida Omi $app jaoks hoiab.';
  }

  @override
  String get selectAll => 'Vali kõik';

  @override
  String get deleteActionItemConfirmation => 'Kas kustutada see ülesanne? Seda ei saa tagasi võtta.';

  @override
  String get categoryTravel => 'Reisimine';

  @override
  String get lowestRating => 'Madalaim hinnang';

  @override
  String get tasksEmptyStateMessage => 'Ülesande loomiseks alusta vestlust.';

  @override
  String get unpairAndForget => 'Tühista sidumine ja unusta seade';

  @override
  String get listeningForAudio => 'Heli kuulamine…';

  @override
  String get processedStatus => 'Töödeldud';

  @override
  String get wrappedTheHardPart => 'Raske osa';

  @override
  String chatAppsReplyThereAnytime(String app) {
    return 'Kirjuta Omile rakenduses $app millal tahes.';
  }

  @override
  String get upgradePlan => 'Uuenda plaani';

  @override
  String get onboardingRatingPromptYes => 'Jah';

  @override
  String timeCompactMins(int count) {
    return '${count}m';
  }

  @override
  String get changeTheConversationTitle => 'Muuda vestluse pealkirja';

  @override
  String get accountGroup => 'Konto';

  @override
  String get updatingYourApp => 'Rakenduse värskendamine';

  @override
  String get microphone => 'Mikrofon';

  @override
  String get suggestQuestionsAfterConversations => 'Soovita küsimusi pärast vestlusi';

  @override
  String get failedToTranscribeAudio => 'Heli transkribeerimine ebaõnnestus';

  @override
  String get unstarConversation => 'Eemalda vestluselt tärn';

  @override
  String get speakerTagPromptNotMe => 'Pole mina';

  @override
  String get confidenceReasonCorrected => 'Parandasid selle vaste';

  @override
  String get peopleSearchPlaceholder => 'Otsi inimesi';

  @override
  String get syncStatusUnsupportedAudio => 'Heli ei õnnestunud lugeda — sünkroonimine pole võimalik';

  @override
  String get indentTask => 'Taanda';

  @override
  String get selectApp => 'Vali rakendus';

  @override
  String get updatePayPal => 'Värskenda PayPal';

  @override
  String get enterNameError => 'Palun sisestage oma nimi';

  @override
  String get exportAllData => 'Ekspordi kõik andmed';

  @override
  String premiumMinsLeft(int count) {
    return '$count premium minutit jäänud.';
  }

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName määratud vaikerakenduseks kokkuvõtte jaoks';
  }

  @override
  String get recordingStartedSuccessfully => 'Salvestamine algas edukalt!';

  @override
  String get trySomethingLike => 'Proovige midagi sellist nagu…';

  @override
  String get chatAppsTryAsking => 'Proovi küsida';

  @override
  String get categoryEntertainment => 'Meelelahutus';

  @override
  String get checksForAudioFiles => 'Kontrollib helifaile SD-kaardil';

  @override
  String get everyoneHeader => 'Kõik';

  @override
  String get clearMemoryButton => 'Tühjenda mälu';

  @override
  String confidenceReasonLabeled(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Märgistasid $count korda',
      one: 'Märgistasid ühe korra',
    );
    return '$_temp0';
  }

  @override
  String get selectLogFile => 'Vali logifail';

  @override
  String get chatAppsTelegramStepReturn => 'Tule siia tagasi. Kinnitame, et see õnnestus.';

  @override
  String get discordMemberCount => 'Üle 8000 liikme Discordis';

  @override
  String get public => 'Avalik';

  @override
  String get outdentTask => 'Vähenda taanet';

  @override
  String get statusProcessing => 'Töötlemine';

  @override
  String get useFreePlan => 'Kasuta tasuta plaani';

  @override
  String get emailLabel => 'E-post';

  @override
  String get statusCallInProgress => 'Kone pooleli';

  @override
  String get shortcuts => 'Kiirklahvid';

  @override
  String get reviewRecentChanges => 'Hiljutised muudatused';

  @override
  String get raybanMetaAudioOnlyExplanation =>
      'See Omi versioon saab kasutada sinu prillide mikrofoni Bluetoothi kaudu. Fotode jäädvustamiseks on vaja Omi Meta arendajaversiooni.';

  @override
  String get wrappedDaysActiveLabel => 'aktiivset päeva';

  @override
  String get installOmiOnAppleWatch => 'Installige Omi oma\nApple Watchi';

  @override
  String tasksCountLabel(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count ülesannet',
      one: '1 ülesanne',
    );
    return '$_temp0';
  }

  @override
  String get confidenceReasonVoiceReady => 'hääl salvestatud';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Kas kustutada $count valitud ülesannet$s?';
  }

  @override
  String get sdCardSync => 'SD-kaardi sünkroonimine';

  @override
  String get timeout4Hours => '4 tundi';

  @override
  String get chatAppsTitle => 'Vestlusrakendused';

  @override
  String get repeatPasswordLabel => 'Korda parooli';

  @override
  String get skip => 'Jäta vahele';

  @override
  String get phoneNoVerifiedNumbersTitle => 'Kinnitatud numbreid pole';

  @override
  String get connectionLost => 'Ühendus kadus';

  @override
  String get photoDiscardedMessage => 'See foto kõrvaldati, kuna see polnud oluline.';

  @override
  String get weekdayFri => 'Ree';

  @override
  String get moveToFolder => 'Teisalda kausta';

  @override
  String get updateNow => 'Värskenda kohe';

  @override
  String get failedToUpdateActionItem => 'Ülesande uuendamine ebaõnnestus';

  @override
  String get transferRequiredDescription =>
      'See salvestis on salvestatud teie seadme SD-kaardile. Kandke see oma telefoni, et seda esitada.';

  @override
  String get checkingForUpdates => 'Värskenduste otsimine';

  @override
  String get importTranscriptFilesDescription => 'Vali SRT-, VTT- või TXT-transkriptsioonid või neid sisaldav ZIP';

  @override
  String get listenToSpeechProfile => 'Kuula minu häälprofiili ➡️';

  @override
  String get deleteRecapConfirmBody =>
      'Kokkuvõte eemaldatakse jäädavalt. Selle päeva algsed vestlused jäävad puutumata.';

  @override
  String get copyLogs => 'Kopeeri logid';

  @override
  String get wrappedFunniestMoment => 'Naljavam';

  @override
  String get onboardingMicrophoneRequired => 'Salvestamiseks on vajalik mikrofoni luba.';

  @override
  String get whoIsItTitle => 'Kes see on?';

  @override
  String dreamReportRunsLeft(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Täna jäi $count käsitsi käivitust',
      one: 'Täna jäi 1 käsitsi käivitus',
    );
    return '$_temp0';
  }

  @override
  String get modified => 'Muudetud';

  @override
  String get actionCreateConversations => 'Loo vestlused';

  @override
  String get chatAssistantsTitle => 'Vestlusassistendid';

  @override
  String get connectionError => 'Ühenduse viga';

  @override
  String get chooseFromGallery => 'Vali galeriist';

  @override
  String get summaryPrompt => 'Kokkuvõtte viip';

  @override
  String get whatWentWrong => 'Mis läks valesti?';

  @override
  String get keepGoingGreat => 'Jätka, sul läheb suurepäraselt';

  @override
  String get deviceConnecting => 'Ühendamine…';

  @override
  String get downgradeLimitBattery => '7x suurem akukulu';

  @override
  String get privateMemories => 'Privaatsed mälestused';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get aiGenPleaseEnterDescription => 'Palun sisesta oma rakenduse kirjeldus';

  @override
  String get enterLiveSttWebsocket => 'Sisestage oma reaalajas STT WebSocket otspunkt';

  @override
  String processingOnServerProgress(int current, int total) {
    return 'Töötlemine… $current/$total segmenti';
  }

  @override
  String linkedToEvent(String title) {
    return 'Seotud sündmusega „$title“';
  }

  @override
  String get failedToSaveCheckConnection => 'Salvestamine ebaõnnestus. Kontrolli ühendust.';

  @override
  String get deviceOnboardingContinue => 'Jätka';

  @override
  String get pairedToAnotherPhone => 'Seotud teise telefoniga';

  @override
  String get syncingYourRecordings => 'Sinu salvestuste sünkroonimine';

  @override
  String get manual => 'Käsitsi';

  @override
  String get oneMonthAgo => '1 kuu tagasi';

  @override
  String get clearChatConfirm => 'Kõik selle vestluse sõnumid kustutatakse. Seda ei saa tagasi võtta.';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'Kõik, mis kasutab võtit \"$keyName\", kaotab juurdepääsu. Seda ei saa tagasi võtta.';
  }

  @override
  String get vadGateDescription => 'Jätab enne transkriptsiooni vaikse heli vahele, et kulusid vähendada.';

  @override
  String get dreamReportScheduled => 'Ajastatud';

  @override
  String get audioDataReceived => 'Heliandmed vastu võetud';

  @override
  String get pro => 'Pro';

  @override
  String get micGainDescMuted => 'Mikrofon on vaigistatud';

  @override
  String get enableLocationDescription => 'Asukoha luba on vajalik läheduses olevate Bluetooth-seadmete leidmiseks.';

  @override
  String get conversationTitleUpdatedSuccessfully => 'Vestluse pealkiri edukalt uuendatud';

  @override
  String get syncStepUpload => 'Sünkrooni';

  @override
  String get removeScreenshot => 'Eemalda ekraanipilt';

  @override
  String get failedToStartCall => 'Kone alustamine ebaonnestus';

  @override
  String get deviceDiagnosticsUploadDescription =>
      'Review the diagnostics JSON below. It includes your device identifier, connection history, battery readings, firmware diagnostics, and BLE events. No audio or transcripts are included.';

  @override
  String get pairingTitleFieldy => 'Lülitage Fieldy sidumisrežiimi';

  @override
  String get autoDeletesAfterThreeDays => 'Kustutatakse automaatselt 3 päeva pärast.';

  @override
  String get wrappedDaysActive => 'aktiivset päeva';

  @override
  String get failedToDeleteActionItem => 'Ülesande kustutamine ebaõnnestus';

  @override
  String get connect => 'Ühenda';

  @override
  String get unableToDeleteConversation => 'Vestlust ei õnnestunud kustutada';

  @override
  String get clearChatAction => 'Tühjenda vestlus';

  @override
  String get memoryThisIphone => 'See iPhone';

  @override
  String get captureCustomSttUnreachableDetail =>
      'Sinu kohandatud kõnetuvastusteenus pole kättesaadav. Omi hoiab heli selles telefonis ja saadab selle, kui teenus taastub. Midagi ei lähe kaduma.';

  @override
  String get feedbackGiveFeedback => 'Give feedback';

  @override
  String failedToUpdateSettings(String error) {
    return 'Seadete värskendamine ebaõnnestus: $error';
  }

  @override
  String get deleteRecordingConfirmation => 'Seda ei saa tagasi võtta.';

  @override
  String get advancedSettings => 'Täpsemad seaded';

  @override
  String get transcriptionNoAudio => 'Transkriptsioon ei saa heli';

  @override
  String deletePeopleCountAction(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Kustuta $count inimest',
      one: 'Kustuta 1 inimene',
    );
    return '$_temp0';
  }

  @override
  String get speakerSuggestionAppliesToSpeaker => 'Kehtib kõigile selle kõneleja ridadele';

  @override
  String get deviceNotResponding => 'Seade ei vastanud. Palun proovige uuesti.';

  @override
  String get everythingSynced => 'Kõik on juba sünkroonitud.';

  @override
  String get onDeviceModelDownloadFailedDesc => 'Whisperi mudeli allalaadimine ebaõnnestus. Palun proovi uuesti.';

  @override
  String fairUseBannerStatus(String status) {
    return 'Õiglane kasutus: $status';
  }

  @override
  String tasksDeleteSelected(int count) {
    return 'Kustuta $count ülesanne(t)';
  }

  @override
  String get connectPaymentMethodInfo =>
      'Ühendage allpool maksemeetod, et alustada oma rakenduste eest maksete saamist.';

  @override
  String get conversationNotFoundOrDeleted => 'Vestlust ei leitud või see on kustutatud';

  @override
  String leaveFlowStepOf(int current, int total) {
    return 'Samm $current/$total';
  }

  @override
  String get deleteTypeToConfirm => 'Kinnitamiseks tipi DELETE';

  @override
  String get clearMemoryTitle => 'Tühjenda Omi mälu';

  @override
  String get triggerConversationCreation => 'Vestluse loomine';

  @override
  String get flashCustomFirmware => 'Paigalda kohandatud püsivara';

  @override
  String shareWithContactCount(int count) {
    return 'Jaga $count kontaktiga';
  }

  @override
  String get customChatbotPersonality => 'Kohandatud vestlusroboti isiksus';

  @override
  String get betaTesterNotice =>
      'Olete selle rakenduse beeta-testija. See ei ole veel avalik. See muutub avalikuks pärast kinnitamist.';

  @override
  String get tomorrow => 'Homme';

  @override
  String get createdLabel => 'LOODUD';

  @override
  String get searchPeople => 'Otsi inimesi';

  @override
  String get cancelled => 'Tühistatud';

  @override
  String basicPlanDesc(int limit) {
    return 'Teie plaan sisaldab $limit tasuta minutit kuus. Uuendage piiramatuks.';
  }

  @override
  String get editMemoryTitle => 'Muuda mälestust';

  @override
  String get whatDoYouWantToKnow => 'Mida sa tahad teada?';

  @override
  String get confidenceFootnote =>
      'Kõige rohkem loevad sinu märgistused ja kinnitused. Automaatsed märgistused loevad vähe, kuni sa need kinnitad.';

  @override
  String get exportFailedTryAgain => 'Eksport ebaõnnestus. Proovi uuesti.';

  @override
  String get addAppPhotosPermissionDenied => 'Fotode luba keelatud. Lubage juurdepääs fotodele';

  @override
  String get filterByDate => 'Filtreeri kuupäeva järgi';

  @override
  String get chatAppsDoesFiles => 'Saadab ja võtab vastu faile, fotosid ja häälsõnumeid';

  @override
  String get deleteKnowledgeGraphTitle => 'Kustuta teadmiste graaf?';

  @override
  String get reloadingConversations => 'Vestluste ümberlaadimine…';

  @override
  String get aiGenPleaseGenerateAppFirst => 'Palun genereeri kõigepealt rakendus';

  @override
  String get completeYourUpgrade => 'Viige oma uuendamine lõpule';

  @override
  String get capturePendantDisconnectedDetail =>
      'Ripats kaotas ühenduse selle telefoniga. Omi loob ühenduse ise uuesti, kui ripats on sisse lülitatud ja lähedal. Kõik varem salvestatu on alles.';

  @override
  String get greetingMorning => 'Tere hommikust';

  @override
  String get thanksForYourFeedback => 'Täname tagasiside eest!';

  @override
  String get deleteActionItemConfirmMessage => 'Kas kustutada see ülesanne?';

  @override
  String get syncCardProcessing => 'Töötlemine Omis…';

  @override
  String get chatAppsTryWeek => 'Võta mu nädal kokku kolme reaga';

  @override
  String get recordWithPhoneMicSubtitle => 'Salvesta ja transkribeeri selle telefoni mikrofoniga';

  @override
  String get notifications => 'Teavitused';

  @override
  String get annualPlanStartsAutomatically => 'Teie aastane plaan algab automaatselt, kui teie kuuplaan lõpeb.';

  @override
  String get unpairDialogMessage =>
      'See tühistab seadme sidumise, et seda saaks ühendada teise telefoniga. Protsessi lõpetamiseks peate minema Seaded > Bluetooth ja unustama seadme.';

  @override
  String get pairingTitleBee => 'Lülitage Bee sidumisrežiimi';

  @override
  String conversationCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count vestlust',
      one: '1 vestlus',
    );
    return '$_temp0';
  }

  @override
  String get syncStatusWaiting => 'Ootab sünkroonimist';

  @override
  String get validWebsocketUrlRequired => 'Kehtiv WebSocket URL on nõutud (wss://)';

  @override
  String get improveSpeechProfile => 'Parandage oma kõneprofiili';

  @override
  String entityWaitingOn(String name) {
    return 'Ootab: $name';
  }

  @override
  String get feedbackReasonTooVerbose => 'Liiga sõnaohter';

  @override
  String chatAppsChannelFooter(String app) {
    return 'Sinu $app-i vestlused jäävad rakendusse $app. Omi teab siiski, millest te rääkisite rakenduses ja sinu teistes vestlusrakendustes.';
  }

  @override
  String get wrappedNoDataAvailable => 'Andmed pole saadaval';

  @override
  String deviceOnboardingAllSetReplayHint(String settings, String deviceSettings, String deviceTutorial) {
    return 'Esitage seda ringkäiku igal ajal uuesti numbril $settings › $deviceSettings › $deviceTutorial';
  }

  @override
  String get createAKey => 'Loo võti';

  @override
  String get successfullyConnectedNotion => 'Edukalt ühendatud Notioniga!';

  @override
  String get captureMicInterruptedDetail =>
      'Kõne või mõni teine rakendus võttis mikrofoni, seega Omi praegu ei kuule. Omi jätkab ise, kui mikrofon vabaneb. Kõik varem salvestatu on alles.';

  @override
  String get onboardingScreenCaptureDenied =>
      'Ekraanipildi luba keelatud. Palun andke luba Süsteemieelistused > Privaatsus ja turvalisus > Ekraani salvestamine.';

  @override
  String get settingUp => 'Seadistamine…';

  @override
  String get frequencyLow => 'Madal';

  @override
  String get sttFilterAuto => 'Automaatne';

  @override
  String get voiceQuestionNoSpeech => 'Ma ei saanud aru — proovige uuesti';

  @override
  String get stripeRecommendation =>
      'Kui Stripe on teie riigis saadaval, soovitame tungivalt seda kasutada kiiremate ja lihtsamate väljamaksete jaoks.';

  @override
  String get confirmed => 'Kinnitatud!';

  @override
  String get deletePendingFilesWarning =>
      'Neid salvestisi EI ole teie telefoniga sünkroniseeritud ja need lähevad jäädavalt kaotsi. Seda ei saa tagasi võtta.';

  @override
  String get removeFilter => 'Eemalda Filter';

  @override
  String get downloadModel => 'Laadi mudel alla';

  @override
  String get performanceReduced => 'Jõudlus võib olla vähenenud';

  @override
  String get hostRequired => 'Host on nõutud';

  @override
  String get alreadyBestValuePlan => 'Teil on juba parima väärtusega plaan. Muudatusi pole vaja.';

  @override
  String preparingModel(String model) {
    return 'Valmistan ette $model…';
  }

  @override
  String get sendTranscript => 'Saada transkriptsioon';

  @override
  String get howItWorksTitle => 'Kuidas see töötab?';

  @override
  String get filterBySpeaker => 'Filtreeri kõneleja järgi';

  @override
  String get addAppSubmittedSuccess => 'Rakendus edukalt esitatud 🚀';

  @override
  String olderIphoneModelDetected(String model) {
    return 'Tuvastatud mudel: $model (vanem kui iPhone XS). Seadmesisene tuvastus võib olla aeglasem.';
  }

  @override
  String get chatAppsWhatsAppTitle => 'WhatsApp on tulemas';

  @override
  String get syncingDeveloperSettings => 'Arendaja seadete sünkroonimine…';

  @override
  String get enterWifiPassword => 'Sisestage WiFi parool';

  @override
  String get failedToUpdateBaselineStatus => 'Seda mälestust ei õnnestunud uuendada. Proovi uuesti.';

  @override
  String get joinCommunity => 'Liitu kogukonnaga!';

  @override
  String get helpOrInquiries => 'Abi või päringud?';

  @override
  String get enable => 'Luba';

  @override
  String get deviceForgottenMessage => 'Seade unustatud';

  @override
  String diagnosticsSincePairingSummary(int drops, int failed) {
    return 'Pärast sidumist: katkestusi $drops, ebaõnnestunud ühendusi $failed.';
  }

  @override
  String confidenceSummaryConfirmed(String name) {
    return 'Omi tunneb inimese $name häält ja sa oled seda kinnitanud.';
  }

  @override
  String migratingToProtection(String level) {
    return '$level kaitsele migreerimine…';
  }

  @override
  String get managePlan => 'Halda plaani';

  @override
  String get synced => 'Sünkroonitud';

  @override
  String get failedToMoveConversations => 'Vestlusi ei saanud teisaldada';

  @override
  String get monthMar => 'Märts';

  @override
  String get timePM => 'PM';

  @override
  String get debugLogsAutoDelete => 'Kustutatakse automaatselt 3 päeva pärast.';

  @override
  String get linkedIn => 'LinkedIn';

  @override
  String speakerLabelVoiceDetail(String state, String name) {
    String _temp0 = intl.Intl.selectLogic(
      state,
      {
        'learned': 'Omi tunneb $name järgmisel korral ära.',
        'pending': 'See võtab mõne sekundi.',
        'disabled': 'Lülita seadetes sisse häälte salvestamine, et Omi saaks $name ära tunda.',
        'other': 'Omi vajab inimeselt $name rohkem selget kõnet ja proovib edasi.',
      },
    );
    return '$_temp0';
  }

  @override
  String get authUnexpectedError => 'Ootamatu viga sisselogimisel, palun proovige uuesti';

  @override
  String disconnectAppMessage(String appName) {
    return 'Saate $appName igal ajal uuesti ühendada.';
  }

  @override
  String get pendantPausedResumesWhenYouFinish => 'Ripats peatatud · jätkab, kui lõpetad';

  @override
  String get sendToSupport => 'Send to support';

  @override
  String get fairUseBudgetExhausted => 'Daily transcription limit reached';

  @override
  String evidenceAutoConfirmed(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Kinnitatud $count automaatset märgistust',
      one: 'Kinnitatud 1 automaatne märgistus',
    );
    return '$_temp0';
  }

  @override
  String get otaWifiConnecting => 'Wi-Fi-ga ühendamine…';

  @override
  String starFilterLabel(int count) {
    return '$count tärn';
  }

  @override
  String get disconnectDevice => 'Katkesta seadme ühendus';

  @override
  String get installsCount => 'Paigaldused';

  @override
  String captureStatusWithSource(String status, String source) {
    return '$status · $source';
  }

  @override
  String get pairingTitleOmiGlass => 'Lülitage Omi Glass sisse';

  @override
  String get setActive => 'Määra aktiivseks';

  @override
  String get showShortConversations => 'Kuva lühikesed vestlused';

  @override
  String get reviewNotSure => 'Pole kindel';

  @override
  String msgCameraAccessError(String error) {
    return 'Viga kaamerale juurdepääsul: $error';
  }

  @override
  String get quickActionAskOmi => 'Küsi Omilt midagi';

  @override
  String get dreamReportTimedOut => 'Peatus ajapiiri tõttu';

  @override
  String get chooseYourLanguage => 'Valige oma keel';

  @override
  String get unableToDetermineFirmwareVersion => 'Praeguse püsivara versiooni ei õnnestunud tuvastada';

  @override
  String get addAppEnterConversationPrompt => 'Sisestage vestluse viip oma rakenduse jaoks';

  @override
  String get readScope => 'Lugemine';

  @override
  String get selectALanguage => 'Valige keel';

  @override
  String get otherTemplates => 'Muud mallid';

  @override
  String get speechProfileTopicGoal => 'Mis on sinu pikaajaline eesmärk?';

  @override
  String get rayBanMetaMicPickerTitle => 'Valige Ray-Ban Meta mikrofon';

  @override
  String meetingNotesSubject(String title) {
    return 'Märkmed: $title';
  }

  @override
  String get feedbackTitleMissingFeatures => 'Milliseid funktsioone teil puudu on?';

  @override
  String get modelReady => 'Mudel on valmis';

  @override
  String todayAtTime(String time) {
    return 'Täna kell $time';
  }

  @override
  String get deleteAccountPermanently => 'Kustuta konto jäädavalt';

  @override
  String get updateStripeDetails => 'Värskenda Stripe andmeid';

  @override
  String get voiceResponseHeadphonesOnly => 'Ainult kõrvaklapid';

  @override
  String get deviceOnboardingEndConversation => 'Lõpeta vestlus';

  @override
  String openingApp(String appName) {
    return 'Avan $appName…';
  }

  @override
  String get submitAppPublicDescription =>
      'Sinu rakendust vaadatakse üle ja tehakse avalikuks. Võid seda kohe kasutada, isegi ülevaatuse ajal!';

  @override
  String connectToAppTitle(String appName) {
    return 'Ühenda rakendusega $appName';
  }

  @override
  String get timeout10MinutesDesc => 'Lõpeta vestlus pärast 10-minutilist vaikust';

  @override
  String get googleCalendar => 'Google Kalender';

  @override
  String get initializing => 'Algseadistamine…';

  @override
  String get noMessagesYet => 'Sõnumeid pole veel!\nMiks te ei alusta vestlust?';

  @override
  String get chatAppsLoadFailed => 'Vestlusrakendusi ei õnnestunud laadida. Palun proovi uuesti.';

  @override
  String get tasksLater => 'Hiljem';

  @override
  String get speakerLabelUnknown => 'Tundmatu';

  @override
  String get appTitle => 'Omi';

  @override
  String get noModelDownloadRequired =>
      'Kasutatakse teie seadme algset kõnemootorit. Mudeli allalaadimine pole vajalik.';

  @override
  String get authenticationFailed => 'Autentimine ebaõnnestus. Palun proovige uuesti.';

  @override
  String get defaultRepoSaved => 'Vaikimisi hoidla salvestatud';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'Viga pisipildi valimisel: $error';
  }

  @override
  String get captureRecordingSeparateTitle => 'Kas eraldada see salvestis?';

  @override
  String get back => 'Tagasi';

  @override
  String get preparingAudio => 'Heli ettevalmistamine';

  @override
  String get noAutoMemories => 'Automaatselt eraldatud mälestusi pole veel';

  @override
  String get allDone => 'Kõik tehtud!';

  @override
  String get msgReadingMemories => 'Loen sinu mälestusi…';

  @override
  String get worksOnDesktop => 'Töötab arvutis';

  @override
  String get displayOptions => 'Kuvamisvalikud';

  @override
  String get installApp => 'Installi rakendus';

  @override
  String get stop => 'Peata';

  @override
  String get grantPermissions => 'Anna load';

  @override
  String get at => 'kell';

  @override
  String get checkInternetConnection => 'Palun kontrollige oma internetiühendust';

  @override
  String get actionItems => 'Ülesanded';

  @override
  String get nextDay => 'Järgmine päev';

  @override
  String get syncStatusFailed => 'Ebaõnnestus — puuduta Proovi uuesti';

  @override
  String get saveCredentials => 'Salvesta mandaadid';

  @override
  String get peopleRecent => 'Hiljutised';

  @override
  String get bringYourOwn => 'Tooge oma oma';

  @override
  String get cancelConsequenceBattery => '7x suurem akukasutus (seadmes töötlemine)';

  @override
  String get copyMessage => 'Kopeeri sõnum';

  @override
  String get annualSubscriptionStarts => 'Teie 12-kuuline aastatellimus algab automaatselt pärast makse tegemist';

  @override
  String get deleteImportedData => 'Kustuta imporditud andmed';

  @override
  String get chatLimitReachedUpgrade => 'Vestluse limiit täis. Uuenda rohkemate sõnumite jaoks.';

  @override
  String get whatsNew => 'Mis on uut';

  @override
  String get omiTraining => 'Omi Koolitus';

  @override
  String get wrappedMyBuddies => 'Minu sõbrad';

  @override
  String get keepRecording => 'Jätka salvestamist';

  @override
  String get suggestedEvent => 'Soovitatud';

  @override
  String get name => 'Nimi';

  @override
  String get screenRecordingDescription =>
      'Omi vajab ekraanisalvestuse luba, et jäädvustada süsteemiheli teie brauseripõhistest koosolekutest.';

  @override
  String get improveConnectionTitle => 'Ühenduse parandamine';

  @override
  String get syncProcessingBackgroundHint => 'See jätkub taustal — võite sellelt ekraanilt lahkuda.';

  @override
  String get wrappedYourTopDaysBadge => 'Sinu parimad päevad';

  @override
  String get noPeopleYet => 'Isikuid veel pole';

  @override
  String summaryGeneratedForDate(String date) {
    return 'Kokkuvõte loodud kuupäevaks $date';
  }

  @override
  String get searchTranscriptOrSummary => 'Otsi transkriptsioonist või kokkuvõttest';

  @override
  String get memoryDetailsTitle => 'Mälestus';

  @override
  String get chatPersonality => 'Vestluse isiksus';

  @override
  String get release => 'Vabastage';

  @override
  String removeVocabularyWord(String word) {
    return 'Eemalda $word';
  }

  @override
  String get onboardingLanguage => 'Keel';

  @override
  String get wrappedYouDidItEmoji => 'Sa tegid seda! 🎉';

  @override
  String get syncInProgress => 'Sünkroonimine käib';

  @override
  String get wrappedCouldntStopTalkingAbout => 'Ei suutnud lõpetada rääkimist';

  @override
  String get chooseSummarizationApp => 'Vali kokkuvõtte rakendus';

  @override
  String etaLabel(String time) {
    return 'Hinnanguline aeg: $time';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'Kui muudate $item avalikuks, saavad kõik seda kasutada';
  }

  @override
  String get phoneCallsUpsellFeature2 => 'Automaatsed kõnekokkuvõtted ja ülesanded';

  @override
  String get freemiumLimitsIntro => 'Omi on tasuta, kuid tasuta versioonil on piirangud, mis mõjutavad sinu kogemust:';

  @override
  String get nameLabel => 'Nimi';

  @override
  String get shortConversationThresholdSubtitle => 'Sellest lühemad vestlused peidetakse, kui pole ülalpool lubatud';

  @override
  String get captureMicInUseElsewhere => 'Mikrofoni kasutab teine rakendus';

  @override
  String get selectChatAssistant => 'Vali vestlusabiline';

  @override
  String get transferRequired => 'Ülekanne vajalik';

  @override
  String get unlimitedChatThisMonth => 'Piiramatu arv vestlussõnumeid sel kuul';

  @override
  String get backgroundModeUnavailable =>
      'Taustarežiim pole saadaval, sest ühtegi ühilduvat seadet pole ühendatud. Selle funktsiooni kasutamiseks ühenda Omi, OpenGlass või Friend Pendant seade.';

  @override
  String get importConfiguration => 'Impordi konfiguratsioon';

  @override
  String get e2eeTradeoff1 => '• Mõned funktsioonid, nagu väliste rakenduste integratsioonid, võivad olla keelatud.';

  @override
  String get chatAppsCodeExpiredTitle => 'See kood aegus';

  @override
  String get responseSchema => 'Vastuse skeem';

  @override
  String get wrappedBestMoments => 'Parimad hetked';

  @override
  String get noAppsExternalAccess => 'Ühelgi paigaldatud rakendusel pole välise juurdepääsu teie andmetele.';

  @override
  String modelReadyWithName(String model) {
    return 'Mudel valmis ($model)';
  }

  @override
  String get appDisabledWebhookFailures => 'Selle lõpp-punkt ebaõnnestus 72 tundi järjest, seega saatmine peatati.';

  @override
  String reviewConversationCount(int count) {
    return 'Vestlusi: $count';
  }

  @override
  String get reviewChangesLoadFailed => 'Hiljutisi muudatusi ei õnnestunud laadida.';

  @override
  String get reviewOpenConversation => 'Vestlus';

  @override
  String get voiceRecordingFound => 'Salvestis leitud';

  @override
  String durationAgo(String duration) {
    return '$duration tagasi';
  }

  @override
  String get onboardingWelcomeToOmi => 'Tere tulemast Omi-sse';

  @override
  String get deleteActionItemConfirmTitle => 'Kustuta ülesanne';

  @override
  String get importantBillingInfo => 'Oluline arvelduse teave:';

  @override
  String get pending => 'Ootel';

  @override
  String get onboardingRatingPromptTitle => 'Kas Omi meeldib sulle?';

  @override
  String get savePayPalDetails => 'Salvesta PayPali andmed';

  @override
  String appDisabledLastError(String error) {
    return 'Viimane viga: $error.';
  }

  @override
  String get iveInstalledAndOpenedTheApp => 'Olen rakenduse installinud ja avanud';

  @override
  String get pricePlaceholder => '0.00';

  @override
  String get triggerTranscriptProcessed => 'Transkriptsioon töödeldud';

  @override
  String get decisions => 'Otsused';

  @override
  String get conversationProcessingFailedMessage => 'Seda vestlust ei õnnestunud töödelda.';

  @override
  String get continueText => 'Jätka';

  @override
  String get signInWithGoogle => 'Logi sisse Google\'iga';

  @override
  String firmwareFlashTarget(String deviceName) {
    return 'Seade: $deviceName';
  }

  @override
  String get deleteYourAccountAndAllData => 'Kustuta oma konto ja kõik andmed';

  @override
  String get provider => 'Pakkuja';

  @override
  String get people => 'Inimesed';

  @override
  String get perMonth => '/ kuu';

  @override
  String get monthFeb => 'Veebr';

  @override
  String get fridayAbbr => 'R';

  @override
  String get thankYouForFeedback => 'Täname tagasiside eest!';

  @override
  String get usageBestYear => 'Best year';

  @override
  String get addAppFillRequiredFields => 'Täitke kõik kohustuslikud väljad õigesti';

  @override
  String get deviceOnboardingVoiceReplyOffDescription => 'Vastused jäävad ekraanile. Midagi ei räägita.';

  @override
  String get logs => 'Logid';

  @override
  String get exportConversations => 'Ekspordi vestlused';

  @override
  String get memoryReviewDropped => 'Eemaldatud sinu mälestustest.';

  @override
  String get appearanceLight => 'Hele';

  @override
  String get moneyEarned => 'Teenitud raha';

  @override
  String get permissionsAndTriggers => 'Load ja päästikud';

  @override
  String get discardRecordingTitle => 'Kas loobuda salvestusest?';

  @override
  String get wrappedMinutesLabel => 'minutit';

  @override
  String get voiceRestoredToast => 'Omi võib selle hääle kohta uuesti küsida';

  @override
  String get locationAccess => 'Asukoha juurdepääs';

  @override
  String get deleteAllMemories => 'Kustuta kõik mälestused';

  @override
  String get deleteAccountTitle => 'Kustuta konto';

  @override
  String get selectFile => 'Vali fail';

  @override
  String get answerTheCallFrom => 'Vasta konesle numbrilt';

  @override
  String get unpairDeviceDialogTitle => 'Tühista seadme sidumine';

  @override
  String exportedToPlatform(String platform) {
    return 'Eksporditud rakendusse $platform';
  }

  @override
  String syncCardDownloadPercent(int percent) {
    return '$percent%';
  }

  @override
  String get deviceOnboardingVoiceReplyPreviewPlaying => 'Teie viimase vastuse esitamine...';

  @override
  String get fromSd => 'SD-lt';

  @override
  String get goodSampleInstructions =>
      '1. Veenduge, et olete vaikses kohas.\n2. Rääkige selgelt ja loomulikult.\n3. Veenduge, et teie seade on oma loomulikus asendis kaelal.\n\nKui see on loodud, saate seda alati parandada või uuesti teha.';

  @override
  String voiceIntroduction(String part) {
    String _temp0 = intl.Intl.selectLogic(
      part,
      {
        'title': 'Let Omi get to know you',
        'intro':
            'Finish four short sentences out loud. This helps Omi recognize your voice and remember what matters to you. Share only what you want.',
        'hint': 'Say the whole sentence and finish it in your own words.',
        'name': 'My name is ___, and I spend most of my time ___.',
        'work': 'Right now, I am working on ___.',
        'enjoy': 'Outside of that, I really enjoy ___.',
        'food': 'My favorite food is ___.',
        'remember': 'Something I would like help remembering is ___.',
        'day': 'A good day for me includes ___.',
        'another': 'Try Another Prompt',
        'start': 'Start Speaking',
        'skipPrompt': 'Skip Question',
        'captured': 'Voice sample captured',
        'silence': 'Take your time. Speak toward your phone microphone.',
        'audio': 'Audio detected',
        'review': 'Here is what I heard',
        'reviewHint': 'Uncheck anything you don\'t want saved.',
        'saveVoice': 'Save Voice Profile',
        'savingVoice': 'Saving your voice profile…',
        'savedVoice': 'Voice profile saved',
        'voiceLater': 'Set Up My Voice Later',
        'keep': 'Save Selected Answers',
        'without': 'Continue Without Saving Answers',
        'savedMemories': 'Your memories are saved',
        'short': 'We need a little more audio. Add one more sentence; your earlier answers are safe.',
        'addSample': 'Add Another Sentence',
        'uploadError': 'Your voice profile could not be saved. Retry with the same recording, or set it up later.',
        'memoryError': 'Some answers could not be saved. Saved items are safe; retry to save the rest.',
        'transcriptionError': 'We could not transcribe that answer. Try again, keep speaking, or skip this question.',
        'noMemories': 'You can tell Omi more about yourself whenever you like.',
        'voiceOnlyHint': 'You can skip any personal prompt and talk about something else.',
        'goalPrompt': 'Right now my number one goal is to ___.',
        'savedGoal': 'Your goal is saved',
        'goalError':
            'Your goal could not be saved. Retry to save the same goal without duplicating it. Any memories already saved are safe.',
        'goalLong': 'Shorten your goal to 500 characters or fewer, then try again.',
        'voiceUnavailable':
            'Voice setup is temporarily unavailable. Saved answers are safe. Retry, or continue and set up your voice later.',
        'saveFinish': 'Save and Finish',
        'retryRemaining': 'Retry Remaining',
        'saveHint': 'Saves your voice profile and checked answers.',
        'savedAll': 'Your introduction is saved.',
        'continueSaved': 'Continue With What Is Saved',
        'reviewAnswers': 'Review Answers',
        'originalGoal': 'Use Original Wording',
        'savingAnswers': 'Saving your answers…',
        'other': '',
      },
    );
    return '$_temp0';
  }

  @override
  String get starConversationHint => 'Vestluse tärniga märkimiseks avage see ja puudutage päises tärni ikooni.';

  @override
  String get pairingTitleOmiDevkit => 'Lülitage Omi DevKit sidumisrežiimi';

  @override
  String sttPrimaryLanguageUnsupported(String language, String fallback) {
    return 'See teenusepakkuja ei toeta keelt $language, seega kasutatakse keelt $fallback.';
  }

  @override
  String get premiumMinutesMonth =>
      '300 premium-minutit kuus. Piiramatu tasuta transkriptsiooni jaoks vali „Seadmel“. ';

  @override
  String get firmwareEnsureBattery => 'Veenduge, et teie seadmel on 15% akut.';

  @override
  String get actionItemDescriptionHint => 'Mida on vaja teha?';

  @override
  String get yourScore => 'Teie skoor';

  @override
  String failedToStartAuth(String appName) {
    return '$appName autentimise alustamine ebaõnnestus';
  }

  @override
  String get actionReadTasks => 'Loe ülesandeid';

  @override
  String get keepSyncing => 'Jätka sünkroonimist';

  @override
  String get overdue => 'Tähtaja ületanud';

  @override
  String get chatAppsProblemUnavailable => 'Vestlusrakendused pole sinu kontol veel saadaval.';

  @override
  String get tapSyncToStart => 'Alustamiseks vajutage Sünkrooni';

  @override
  String get emptyDoneMessage => 'Lõpetatud punkte pole veel';

  @override
  String get recordOptionsTip => 'Nõuanne: telefonikõne salvestamiseks puuduta salvestusnupul olevat noolt.';

  @override
  String get setupQuestionProfession => '1. Mis on teie amet?';

  @override
  String get deviceInfoSection => 'Seadme teave';

  @override
  String get teachOmiYourVoice => 'Õpeta Omi-le oma häält';

  @override
  String get addYourFirstMemory => 'Lisa oma esimene mälestus';

  @override
  String get priceLabel => 'HIND';

  @override
  String get high => 'Kõrge';

  @override
  String estimatedSizeWithValue(String size) {
    return 'Eeldatav suurus: ~$size MB';
  }

  @override
  String cleanUpUnsureCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count inimest, kelles Omi ei ole kindel',
      one: '1 inimene, kelles Omi ei ole kindel',
    );
    return '$_temp0';
  }

  @override
  String get makeAllMemoriesPrivate => 'Tee kõik mälestused privaatseks';

  @override
  String get raybanMetaWaitingForMetaAI => 'Lõpeta ühendamine Meta AI rakenduses ja tule siis siia tagasi.';

  @override
  String get revokeAuthorization => 'Tühista autoriseerimine';

  @override
  String get confidenceToReachConfirmed => 'Kinnitatud tasemeni jõudmiseks';

  @override
  String get syncCardRateLimited => 'Õiglase kasutuse piir on saavutatud — sünkroonimine jätkub automaatselt';

  @override
  String get reviewStopClip => 'Peata klipp';

  @override
  String get chatAppsWhatOmiDoes => 'Mida Omi vestlusrakendustes teeb';

  @override
  String get resume => 'Jätka';

  @override
  String get defaultSpace => 'Vaikimisi ruum';

  @override
  String get multipleSpeakersDetected => 'Tuvastati mitu kõnelejat';

  @override
  String evidenceAutoCorrected(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Muutsid $count automaatset märgistust kellegi teise kasuks',
      one: 'Muutsid 1 automaatse märgistuse kellegi teise kasuks',
    );
    return '$_temp0';
  }

  @override
  String get voiceMatchPossible => 'Võimalik vaste';

  @override
  String get checkBoxToConfirm =>
      'Märkige ruut, et kinnitada, et mõistate, et teie konto kustutamine on püsiv ja pöördumatu.';

  @override
  String get quicklyPopulateResponse => 'Täida kiiresti tuntud teenusepakkuja vastuse vorminguga';

  @override
  String get monthJul => 'Juuli';

  @override
  String get failedToInitializeCallService => 'Koneteenuse kaivitamine ebaonnestus';

  @override
  String get connectAction => 'Ühenda';

  @override
  String get onDeviceModelDeleted => 'Mudel kustutatud';

  @override
  String get micGainDescNeutral => 'Neutraalne - tasakaalustatud salvestamine';

  @override
  String get chatOfflineHint => 'Oled võrguühenduseta. Sõnumite saatmiseks loo uuesti ühendus.';

  @override
  String get onboardingLocationGrantInSettings =>
      'Palun andke asukohaluba Seaded > Privaatsus ja turvalisus > Asukohateenused';

  @override
  String get invalidSetupInstructionsUrl => 'Vigane seadistusjuhiste URL';

  @override
  String get msgCameraPermissionDenied => 'Kaamera luba keelatud. Palun lubage juurdepääs kaamerale';

  @override
  String get dataAndPrivacy => 'Andmed ja privaatsus';

  @override
  String get deviceNotCompatible => 'Sinu seade ei ühildu seadmes transkriptsiooniga';

  @override
  String get pairingDescAppleWatch =>
      'Installige ja avage Omi rakendus oma Apple Watchis, seejärel puudutage rakenduses Ühenda.';

  @override
  String get speechProfileTopicLocation => 'Kus sa elad?';

  @override
  String get makeAllPrivate => 'Muuda kõik mälestused privaatseks';

  @override
  String get capabilityNotification => 'Teavitus';

  @override
  String get captureAudioSavedTranscribesLater => 'Heli salvestatud, transkribeeritakse hiljem';

  @override
  String get wrappedTopPhrases => 'Top 5 fraasi';

  @override
  String get transcribeLaterPaused => 'Peatatud — heli ei salvestata';

  @override
  String get deviceOnboardingTurnOnTitle => 'Lülita sisse';

  @override
  String get keyNamePlaceholder => 'nt. Minu rakenduse integratsioon';

  @override
  String get languageTitle => 'Keel';

  @override
  String get statusVerifiedLabel => 'Kinnitatud';

  @override
  String get storageLocationPhoneMemory => 'Telefon (mälu)';

  @override
  String get you => 'Sina';

  @override
  String get listeningTranscriptWillAppear => 'Kuulan… siia ilmub transkriptsioon.';

  @override
  String get askSuggestNotice => 'Mida Omi märkas?';

  @override
  String get safelyBackedUp => 'Loodud vestlused';

  @override
  String get folderName => 'Kausta nimi';

  @override
  String get categorySocialEntertainment => 'Sotsiaalne ja meelelahutus';

  @override
  String speechProfileOwnerTitle(String name) {
    return '$name: hääleprofiil';
  }

  @override
  String get reviewAddedSuccessfully => 'Arvustus edukalt lisatud 🚀';

  @override
  String get fairUseSpeechUsage => 'Kõne kasutus';

  @override
  String get visibilitySubtitle => 'Kontrollige, millised vestlused teie loendis kuvatakse';

  @override
  String get wrappedWinLabelUpper => 'VÕIT';

  @override
  String timeCompactMinsAndSecs(int mins, int secs) {
    return '${mins}m ${secs}s';
  }

  @override
  String get phoneCallsUpsellSubtitle =>
      'Tehke kõnesid Omi kaudu ja saage reaalajas transkriptsioon, automaatsed kokkuvõtted ja palju muud.';

  @override
  String get sessionExpiredSignInAgain => 'Seanss aegus — logige uuesti sisse.';

  @override
  String get newPersonEllipsis => 'Uus inimene…';

  @override
  String get sharePeriodToday => 'Täna on Omi:';

  @override
  String get premiumMinutesInfo => '300 premium-minutit kuus. Piiramatu tasuta transkriptsiooni jaoks vali „Seadmel“.';

  @override
  String get notConnectedStatus => 'Pole ühendatud';

  @override
  String get authorizeSavingRecordings => 'Luba salvestiste salvestamine';

  @override
  String get thinking => 'Mõtlen';

  @override
  String get unpairDialogTitle => 'Tühista seadme sidumine';

  @override
  String get batteryFullyChargedBody => 'Teie Omi seade on täielikult laetud. Võite selle lahti ühendada!';

  @override
  String get speakerTagPromptRejectedToast => 'Märgistus eemaldatud';

  @override
  String get phone => 'Telefon';

  @override
  String get chatAppsVoiceNotes => 'Häälsõnumid';

  @override
  String get deviceOnboardingStatusDisconnected => 'Ühendus katkenud';

  @override
  String get debugModeDetected => 'Silumisrežiim tuvastatud';

  @override
  String get failedToSaveDefaultRepo => 'Vaikimisi hoidla salvestamine ebaõnnestus';

  @override
  String get showCompletedTasks => 'Kuva lõpetatud';

  @override
  String deviceStorageUsedOfTotal(String used, String total) {
    return '$used / $total kasutatud';
  }

  @override
  String get recordingsNotSynced => 'Teil on salvestisi, mis pole veel sünkroonitud.';

  @override
  String get performanceWarning => 'Jõudluse hoiatus';

  @override
  String get submitAppPrivateDescription =>
      'Sinu rakendust vaadatakse üle ja tehakse sulle privaatselt kättesaadavaks. Võid seda kohe kasutada, isegi ülevaatuse ajal!';

  @override
  String get copyTranscript => 'Kopeeri transkriptsioon';

  @override
  String get providing => 'Pakkumine';

  @override
  String get findDeviceNoneMessage => 'Lülita see sisse ja hoia telefoni lähedal.';

  @override
  String get wrappedLetsHitRewind => 'Kerime tagasi sinu';

  @override
  String deviceRamBelowMinimum(String ram) {
    return 'Tuvastatud RAM: $ram GB. Soovitatav miinimum: 4 GB.';
  }

  @override
  String get addOrChangePaymentMethod => 'Lisa või muuda oma makseviisi';

  @override
  String get omiAppName => 'Omi';

  @override
  String get enableBluetooth => 'Luba Bluetooth';

  @override
  String get privacyNotice => 'Privaatsusteade';

  @override
  String get manufacturer => 'Tootja';

  @override
  String get byContinuingYouAgree => 'Jätkates nõustute meie ';

  @override
  String dataProtectedWithSettings(String level) {
    return 'Teie andmed on nüüd kaitstud uute $level seadistustega.';
  }

  @override
  String get selectSpaceInWorkspace => 'Valige ruum oma tööalast';

  @override
  String get copyKey => 'Kopeeri võti';

  @override
  String get password => 'Parool';

  @override
  String estimatedSize(String size) {
    return 'Hinnanguline suurus: ~$size MB';
  }

  @override
  String monthsFreeBadge(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count kuud tasuta',
      one: '1 kuu tasuta',
    );
    return '$_temp0';
  }

  @override
  String get chatAppsNotAvailableYet => 'Pole veel saadaval';

  @override
  String estimatedTimeRemaining(String time) {
    return 'Hinnanguline: $time jäänud';
  }

  @override
  String get syncCardBackendBusy => 'Omi serverid on hõivatud — sinu salvestised sünkroonitakse, kui maht vabaneb';

  @override
  String get speakerTagPromptTitle => 'Aita Omil hääli ära tunda';

  @override
  String get playFromHere => 'Esita siit';

  @override
  String get entityProject => 'Projekt';

  @override
  String get permissionNotGrantedYet =>
      'Luba pole veel antud. Palun veenduge, et lubate mikrofoni juurdepääsu ja avasid rakenduse oma kellal uuesti.';

  @override
  String get e2eeTradeoff2 => '• Kui kaotate oma parooli, ei saa teie andmeid taastada.';

  @override
  String get exportConfiguration => 'Ekspordi konfiguratsioon';

  @override
  String get recordWith => 'Salvestusviis';

  @override
  String get greetingEvening => 'Tere õhtust';

  @override
  String deletePhoneNumberConfirm(String phoneNumber) {
    return 'Kustuta $phoneNumber?';
  }

  @override
  String get deviceOnboardingAskQuestionTitle => 'Esita Omile küsimus';

  @override
  String get appNamePlaceholder => 'Minu suurepärane rakendus';

  @override
  String get tapPlayToResume => 'Puudutage esitamist jätkamiseks';

  @override
  String get dueDate => 'Tähtaeg';

  @override
  String get appearanceSystem => 'Süsteem';

  @override
  String get invalidEmailError => 'Palun sisestage kehtiv e-post';

  @override
  String get highResourceUsage => 'Suur ressursikasutus';

  @override
  String get voiceAndPeople => 'Hääl ja Inimesed';

  @override
  String get customizationSection => 'Kohandamine';

  @override
  String get failedToCancelSubscription => 'Tellimuse tühistamine ebaõnnestus. Palun proovi uuesti.';

  @override
  String get later => 'Hiljem';

  @override
  String get wrappedTasksGenerated => 'ülesannet loodud';

  @override
  String get personalizingExperience => 'Teie kogemuse isikupärastamine…';

  @override
  String get syncAvailable => 'Sünkroonimine saadaval';

  @override
  String chatGreeting(String name) {
    return 'Tere, $name, küsi mida tahes';
  }

  @override
  String get phoneCallSettingsTitle => 'Kone seaded';

  @override
  String get remoteDeviceTerminated => 'Kaugseade katkestas ühenduse';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'Viga failivalija avamisel: $message';
  }

  @override
  String get actionItemDeleted => 'Ülesanne kustutatud';

  @override
  String get couldNotLoadMemories => 'Mälestusi ei õnnestunud laadida';

  @override
  String get generateDescription => 'Genereeri kirjeldus';

  @override
  String get privateLabel => 'Privaatne';

  @override
  String get deviceOnboardingMuteUnmute => 'Vaigista / Taasta heli';

  @override
  String get day => 'Päev';

  @override
  String get submitAppQuestion => 'Esita rakendus?';

  @override
  String get usageWords => 'Words';

  @override
  String get failedToConnectClickUp => 'ClickUpiga ühendamine ebaõnnestus';

  @override
  String get selectZipFileToImport => 'Vali importimiseks .zip fail!';

  @override
  String timeSecsPlural(int count) {
    return '$count sek';
  }

  @override
  String get wasThisHelpful => 'Kas see oli kasulik?';

  @override
  String get msgLearningMemories => 'Õpin sinu mälestustest…';

  @override
  String get onboardingScreenCaptureRequired => 'Süsteemiheli salvestamiseks on vajalik ekraanipildi luba.';

  @override
  String evidenceManualLabels(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Märgistatud sinu poolt $count vestluses',
      one: 'Märgistatud sinu poolt 1 vestluses',
    );
    return '$_temp0';
  }

  @override
  String get transferCancelled => 'Ülekanne tühistatud';

  @override
  String get sttModelSpeed => 'Kiirus';

  @override
  String get fairUsePolicy => 'Õiglane kasutus';

  @override
  String get phoneStorage => 'Telefoni salvestusruum';

  @override
  String get deviceOnboardingEndConversationDesc => 'Salvesta ja lõpeta praegune vestlus';

  @override
  String get proceedAnyway => 'Jätka siiski';

  @override
  String get overview => 'Ülevaade';

  @override
  String get deviceOnboardingGoodJob => 'Tubli!';

  @override
  String get delete => 'Kustuta';

  @override
  String get connectAiAssistantsToYourData => 'Ühendage AI-assistendid oma andmetega';

  @override
  String get startFresh => 'Alusta otsast';

  @override
  String get deviceOnboardingStatusConnectedDone => 'Ühendatud!';

  @override
  String get filterInstalled => 'Paigaldatud';

  @override
  String get mergingStatus => 'Ühendamine…';

  @override
  String get successfullyConnected => 'Edukalt ühendatud!';

  @override
  String get permissionCreateConversations => 'Loo vestlusi';

  @override
  String get cancelConsequencePhoneCalls => 'Puudub reaalajas telefonikõnede transkriptsioon';

  @override
  String get feedbackReasonSummaryOther => 'Something else';

  @override
  String get oAuth => 'OAuth';

  @override
  String get notEnoughSpace => 'Hoiatus: Pole piisavalt ruumi!';

  @override
  String get feedbackTitleTooExpensive => 'Milline hind sobiks teile?';

  @override
  String get secureEncryption => 'Turvaline krüpteerimine';

  @override
  String get rating2PlusStars => '2+ tärni';

  @override
  String get chatAppsOpenMessagesAgain => 'Ava Sõnumid uuesti';

  @override
  String fairUseBudgetResetsAt(String time) {
    return 'Resets $time';
  }

  @override
  String get addVocabularyDescription => 'Lisage sõnad, mida Omi peaks transkriptsiooni ajal ära tundma.';

  @override
  String get whisperModelSizeMedium => 'Keskmine';

  @override
  String get wrappedMyBuddiesLabel => 'MINU SÕBRAD';

  @override
  String get memoryGraph => 'Mälude graaf';

  @override
  String get paste => 'Kleebi';

  @override
  String get failedToRefreshGitHubStatus => 'GitHubi ühenduse oleku värskendamine ebaõnnestus.';

  @override
  String get feedbackSubtitleMissingFeatures => 'Ehitame alati — see aitab meil prioriteete seada.';

  @override
  String get itemApp => 'Rakendus';

  @override
  String get pairingDescFriendPendant =>
      'Vajutage ripatsil olevat nuppu selle sisselülitamiseks. See lülitub automaatselt sidumisrežiimi.';

  @override
  String get appDisabledGeneric => 'Omi lülitas selle välja.';

  @override
  String get noSummaryForApp =>
      'Selle rakenduse jaoks pole kokkuvõtet saadaval. Proovi teist rakendust paremate tulemuste saamiseks.';

  @override
  String get deleteProcessed => 'Kustuta töödeldud';

  @override
  String get chatBlockOpenInGoals => 'Ava eesmärkides';

  @override
  String get micGainDescModerate => 'Vaikne - mõõduka müra jaoks';

  @override
  String get defaultRepository => 'Vaikimisi hoidla';

  @override
  String get statusPending => 'Ootel';

  @override
  String get referralProgram => 'Viiteprogramm';

  @override
  String get authFailedToLinkApple => 'Apple\'iga sidumine ebaõnnestus, palun proovige uuesti.';

  @override
  String modelNameWithFile(String model) {
    return 'Mudel: $model';
  }

  @override
  String get deviceOnboardingTurnOnSubtitle => 'Vajuta nuppu, et see uuesti sisse lülitada';

  @override
  String get previewAndScreenshots => 'Eelvaade ja ekraanipildid';

  @override
  String get recordingOfflineTranscriptWillCatchUp =>
      'Salvestamine võrguühenduseta — transkriptsioon jõuab järele, kui oled taas võrgus.';

  @override
  String get accessibilityDescription =>
      'Omi vajab juurdepääsetavuse luba, et tuvastada, millal te liitute Zoom, Meet või Teams koosolekutega oma brauseris.';

  @override
  String setDefaultAppContent(String appName) {
    return 'Kas määrata $appName vaikimisi kokkuvõtte rakenduseks?\n\nSeda rakendust kasutatakse automaatselt kõigi tulevaste vestluste kokkuvõtete jaoks.';
  }

  @override
  String get switchRequiresRestart => 'Vahetamine nõuab rakenduse taaskäivitamist';

  @override
  String get wrappedWinHeader => 'Võit';

  @override
  String get forYou => 'Sulle';

  @override
  String get filterCategory => 'Kategooria';

  @override
  String get createPersonHint => 'Looge uus isik ja õpetage Omi-le ära tundma ka tema kõnet!';

  @override
  String get loadingMemories => 'Mälestuste laadimine…';

  @override
  String get selectedPaymentMethod => 'Valitud maksemeetod';

  @override
  String get email => 'E-post';

  @override
  String get transcriptionUnavailableRecordingContinues =>
      'Transkriptsioonid pole saadaval, salvestamine jätkub seadmel ja töödeldakse hiljem';

  @override
  String get noLogsYet => 'Logisid pole veel. Salvesta midagi, et näha päringuid transkriptsiooniteenuse pakkujale.';

  @override
  String get failedToStartAuthentication => 'Autentimise alustamine ebaõnnestus';

  @override
  String peopleCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count inimest',
      one: '1 inimene',
    );
    return '$_temp0';
  }

  @override
  String get enterBackendUrlError => 'Palun sisestage serveri URL';

  @override
  String get playbackBackToCurrent => 'Tagasi praeguse juurde';

  @override
  String clockSkewWarning(int minutes) {
    return 'Teie seadme kell erineb ~$minutes min. Kontrollige kuupäeva ja kellaaja seadeid.';
  }

  @override
  String get stopThese => 'Peata need';

  @override
  String get yes => 'Jah';

  @override
  String get recognizingOthers => 'Teiste tuvastamine 👀';

  @override
  String get transcriptionLanguageDesc => 'Vali kõne transkriptsiooni keel';

  @override
  String aboutMinutesRemaining(int minutes) {
    return 'Umbes $minutes minutit jäänud';
  }

  @override
  String get deleteFlowReasonSubtitle => 'Sinu tagasiside aitab meil Omi kõigi jaoks paremaks muuta.';

  @override
  String get processedFilesDeleted => 'Töödeldud failid kustutatud';

  @override
  String get autoLanguageDetection => 'Automaatne keele tuvastamine';

  @override
  String bulkExportPartial(int success, int total, String platform) {
    return 'Eksporditi $success/$total asukohta $platform';
  }

  @override
  String get actionItemDescriptionCannotBeEmpty => 'Ülesande kirjeldus ei tohi olla tühi';

  @override
  String get deleteReasonFoundAlternative => 'Kasutan midagi muud';

  @override
  String get noContentToDisplay => 'Sisu pole kuvamiseks';

  @override
  String get feedbackReasonRecordingWrongSpeaker => 'Wrong speaker';

  @override
  String get create => 'Loo';

  @override
  String get greatJobAlmostThere => 'Suurepärane töö, olete peaaegu kohal';

  @override
  String get captureStorageAlmostFull => 'Mälu on peaaegu täis';

  @override
  String chatAppsConnectedOn(String date) {
    return 'Ühendatud $date';
  }

  @override
  String get wrappedAGreatDay => 'Suurepärane päev';

  @override
  String get backendUrlSavedSuccess => 'Serveri URL salvestatud!';

  @override
  String get speakerTagPromptIsThisYou => 'Kas see olid sina?';

  @override
  String get knowledgeGraphDeletedSuccess => 'Teadmiste graaf edukalt kustutatud';

  @override
  String timeMinsPlural(int count) {
    return '$count min';
  }

  @override
  String get peopleNotHeardYet => 'Pole veel kuulnud';

  @override
  String get chatStarterDoDifferently => 'Mida saaksin täna teisiti teha?';

  @override
  String get fairUseAboutBody =>
      'Omi on mõeldud isiklikeks vestlusteks, koosolekuteks ja reaalajas suhtluseks. Kasutust mõõdetakse kõnelemisele kulutatud ajaga, mitte ühendatud ajaga. Kui su kasutus on tavapärasest isiklikust kasutusest oluliselt suurem, saad enne hoiatuse. Pideva tõsise kasutamise korral võib transkriptsioon aeglustuda või piirduda.';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'Palun valige oma põhikeel';

  @override
  String get manualDisconnect => 'Käsitsi katkestus';

  @override
  String get googleCalendarNotConnected => 'Google Kalender pole ühendatud';

  @override
  String get soCloseJustLittleMore => 'Nii lähedal, veel natuke';

  @override
  String appDataAccessMessage(String appName) {
    return '$appName saab sinu vestlused, mälestused ja salvestised oma arendaja serverisse. Omi ei vastuta selle eest, kuidas neid andmeid seal kasutatakse.';
  }

  @override
  String savePercent(int percent) {
    return 'Säästa ~$percent%';
  }

  @override
  String get deviceDisconnectedNotificationBody => 'Palun ühendage uuesti, et jätkata Omi kasutamist.';

  @override
  String get openConversation => 'Ava vestlus';

  @override
  String get frequencyDescMaximum => 'Iga kasulik seos, kuni 9 päevas';

  @override
  String get readChatRepliesAloud => 'Loe vestluse vastused ette';

  @override
  String get microphonePermissionRequired => 'Helisalvestuse jaoks on vajalik mikrofoni luba.';

  @override
  String get updatePayPalAccountDetails => 'Värskendage oma PayPali konto andmeid';

  @override
  String get connectionTimeout => 'Ühenduse ajalõpp';

  @override
  String get micGainDescHigh => 'Kõrge - kaugete või vaikste häälte jaoks';

  @override
  String get permissionsInfoNote =>
      'R = Lugemine, W = Kirjutamine. Vaikimisi ainult lugemine, kui midagi pole valitud.';

  @override
  String timeHoursAndMins(int hours, int mins) {
    return '$hours tundi $mins min';
  }

  @override
  String get keepMyAccount => 'Säilita minu konto';

  @override
  String get transcriptionLanguage => 'Transkriptsiooni keel';

  @override
  String dreamReportStats(int records, int tokens) {
    return 'Loetud $records üksust · $tokens tokenit';
  }

  @override
  String get editPerson => 'Muuda isikut';

  @override
  String get whatWeTrack => 'Mida jälgime';

  @override
  String get micGainDescVeryHigh => 'Väga kõrge - väga vaiksetele allikatele';

  @override
  String timeCompactDays(int count) {
    return '${count}p';
  }

  @override
  String get reviewTaskField => 'Ülesanne';

  @override
  String reviewConfirmPerson(String name) {
    return 'Kinnita: $name';
  }

  @override
  String get downloadingFromDevice => 'Seadmest allalaadimine';

  @override
  String get conversationTranscriptCopiedToClipboard => 'Vestluse transkriptsioon kopeeritud lõikelauale';

  @override
  String get continueAction => 'Jätka';

  @override
  String conversationsMovedCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count vestlust teisaldatud',
      one: '1 vestlus teisaldatud',
    );
    return '$_temp0';
  }

  @override
  String get signInButton => 'Logi sisse';

  @override
  String get startUpdate => 'Alusta värskendamist';

  @override
  String get wrappedTopPhrasesLabelUpper => 'TOP FRAASID';

  @override
  String get total => 'Kokku';

  @override
  String get deleting => 'Kustutamine…';

  @override
  String get skipBack10Seconds => '10 sekundit tagasi';

  @override
  String get setupAnswerAllQuestions => 'Te pole veel kõikidele küsimustele vastanud! 🥺';

  @override
  String get planUpgradeScheduledMessage => 'Uuendamine on ajastatud! Teie kuupakett jätkub arveldusperioodi lõpuni.';

  @override
  String get needHelpChatWithUs => 'Vajad abi? Vestle meiega';

  @override
  String get chatBlockUnavailable => 'Pole enam saadaval';

  @override
  String estimatedMinutes(int count) {
    return '~$count minut(it)';
  }

  @override
  String get failedToSaveMemory => 'Salvestamine ebaõnnestus. Palun kontrollige oma ühendust.';

  @override
  String get deleteReasonTakingBreak => 'Teen lihtsalt pausi';

  @override
  String get reviewAndManageConversations => 'Vaadake üle ja hallake oma salvestatud vestlusi';

  @override
  String get actionReadMemories => 'Loe mälestusi';

  @override
  String deletePinnedPersonMessage(String name) {
    return '$name on esile tõstetud. Tema hääleproovid eemaldatakse, Omi lõpetab tema tuvastamise ja varasemates ärakirjades kuvatakse ta nimetu kõnelejana. Seda ei saa tagasi võtta.';
  }

  @override
  String get speakerTagPromptHintOwner => 'Sinu vastus märgistab ainult esitatud lõigu.';

  @override
  String get onboardingNotificationDeniedNotifications =>
      'Teavituste luba keelatud. Palun andke luba Süsteemieelistused > Teavitused.';

  @override
  String appDisabledNamed(String appName) {
    return '$appName on keelatud';
  }

  @override
  String get tabOld => 'Vanad';

  @override
  String deviceOnboardingVoiceReplyStatusHeadphonesConnected(String device) {
    return '$device ühendatud. Siin räägib Omi.';
  }

  @override
  String get deletePendingFiles => 'Kustuta ootel salvestised';

  @override
  String get wrappedWin => 'Võit';

  @override
  String get removeFromAllFolders => 'Eemalda kõigist kaustadest';

  @override
  String get deviceIdLabel => 'Seadme ID';

  @override
  String get upgradeAlreadyScheduled => 'Teie täiendus aastasele plaanile on juba planeeritud';

  @override
  String get openCall => 'Ava kõne';

  @override
  String get rateAndReviewThisApp => 'Hinda ja arvusta seda rakendust';

  @override
  String get getStarted => 'Alusta';

  @override
  String get deviceOnboardingVoiceReplyAlwaysDescription => 'Kasutab telefoni kõlarit, kui kõrvaklappe pole ühendatud.';

  @override
  String chooseExportDestination(int count) {
    return 'Ekspordi $count üksus(t) asukohta…';
  }

  @override
  String get onboardingSetupSubtitle => 'Anna Omile hetk kohandamiseks';

  @override
  String welcomeBack(String name) {
    return 'Tere tulemast tagasi, $name';
  }

  @override
  String get dreamReportIdle => 'Pole veel midagi uut vaadata.';

  @override
  String get cleanUpTitle => 'Puhastamine';

  @override
  String get deleteProcessedFiles => 'Kustuta töödeldud failid';

  @override
  String get no => 'Ei';

  @override
  String get msgPhotoError => 'Viga foto tegemisel. Palun proovige uuesti.';

  @override
  String get search => 'Otsi';

  @override
  String get downloadingFirmware => 'Püsivara allalaadimine';

  @override
  String get phoneKeypadTab => 'Klaviatuur';

  @override
  String get pendantFullSyncBlocked =>
      'Pendanti mälu on täis ja see on endiselt salvestusrežiimis, seega salvestatud heli ei saa üle kanda. Salvestamise peatamiseks vajuta Pendanti nuppu ja seejärel sünkrooni uuesti.';

  @override
  String get deleteSelectedItemsTitle => 'Kustuta valitud punktid';

  @override
  String get appPrivacyAndTerms => 'Rakenduse privaatsus ja tingimused';

  @override
  String get omiTranscription => 'Omi transkriptsioon';

  @override
  String get editConversation => 'Muuda vestlust';

  @override
  String moveConversationsTo(int count) {
    return 'Teisalda $count vestlust kausta:';
  }

  @override
  String get signOutConfirmation =>
      'Vestluste nägemiseks pead uuesti sisse logima. Seotud seade ja rakenduse eelistused jäävad sellesse telefoni.';

  @override
  String get wrappedObsessionsLabel => 'KINNISIDEED';

  @override
  String get jumpToLatestMessage => 'Hüppa uusima sõnumi juurde';

  @override
  String get failedStatus => 'Ebaõnnestunud';

  @override
  String get notNow => 'Mitte praegu';

  @override
  String transferFailedMessage(String error) {
    return 'Ülekanne ebaõnnestus: $error';
  }

  @override
  String get customVocabularyTitle => 'Kohandatud sõnavara';

  @override
  String get internetRequired => 'Internet on vajalik';

  @override
  String get waitingForData => 'Andmete ootel…';

  @override
  String get noRecordingsYet => 'Salvestisi veel pole';

  @override
  String get answerWithYourVoice => 'Vasta oma häälega:';

  @override
  String personUnpinnedToast(String name) {
    return '$name esiletõstmine eemaldati';
  }

  @override
  String get stopRecording => 'Peata salvestus';

  @override
  String get off => 'Väljas';

  @override
  String get memoryThisPhone => 'See telefon';

  @override
  String get thirteenMonthsCoverage => 'Saate kokku 13 kuud katvust (praegune kuu + 12 kuud aastas)';

  @override
  String failedToCreateApiKey(String error) {
    return 'Teenusepakkuja API võtme loomine ebaõnnestus: $error';
  }

  @override
  String get tipStableInternet => 'Stabiilne internet kiirendab pilveüleslaadimist';

  @override
  String get tasksMarkComplete => 'Märgitud lõpetatuks';

  @override
  String get reviewAddTask => 'Lisa ülesanne';

  @override
  String get submitReply => 'Saada vastus';

  @override
  String get captureRecoveryBanner => 'Omi ei saada heli — puudutage uuesti ühendamiseks';

  @override
  String get analyzing => 'Analüüsimine…';

  @override
  String get sttModelFaster => 'Kiirem';

  @override
  String get fairUseLoadError => 'Õiglase kasutuse olekut ei õnnestunud laadida. Palun proovige uuesti.';

  @override
  String get places => 'Kohad';

  @override
  String get voiceMatchWeak => 'Nõrk vaste';

  @override
  String captureOfflineBufferingFor(int minutes) {
    return 'Võrguühenduseta, puhverdamine · $minutes min';
  }

  @override
  String get onboardingWhatIKnowAboutYouTitle => 'Siin on, mida ma sinust tean';

  @override
  String get raybanMetaPhotoRequested => 'Foto taotletud — see ilmub sinu vestlusesse.';

  @override
  String get verifyYourNumber => 'Kinnitage oma number';

  @override
  String get deleteFlowConfirmSubtitle => 'Seda ei saa tagasi võtta, isegi mitte kasutajatoe abil.';

  @override
  String get submitAppTermsAgreement =>
      'Selle rakenduse esitamisega nõustun Omi AI teenuse tingimuste ja privaatsuspoliitikaga';

  @override
  String get stripeSecureDescription => 'Stripe tagab teie rakenduse tulude turvalised ja õigeaegsed ülekanded';

  @override
  String get categoryProductivity => 'Tootlikkus';

  @override
  String chatWithAppName(String appName) {
    return 'Vestle rakendusega $appName';
  }

  @override
  String get enableCloudStorage => 'Luba pilvesalvestus';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl => 'Kehtetu reaalajas transkriptsiooni veebihaagi URL';

  @override
  String get wrappedShow => 'SARI';

  @override
  String get speakTranscribeSummarize => 'Räägi. Transkribeeri. Võta kokku.';

  @override
  String get pricingPaid => 'Tasuline';

  @override
  String get successfullyConnectedAsana => 'Edukalt ühendatud Asanaga!';

  @override
  String get rating => 'Hinnang';

  @override
  String get chatQuotaExceededReply =>
      'Olete saavutanud oma igakuise limiidi. Uuendage, et jätkata Omiga piiranguteta vestlemist.';

  @override
  String get pendantIsListeningTitle => 'Sinu ripats kuulab';

  @override
  String get usageBestDay => 'Best day';

  @override
  String get personWhyConfidence => 'Miks?';

  @override
  String get permissionDescCreateConversations => 'See rakendus saab luua uusi vestlusi.';

  @override
  String get reviewSpellingCustom => 'Sisesta ise';

  @override
  String resetsInHours(int count) {
    return 'Lähtestub $count tunni pärast';
  }

  @override
  String get reviewAction => 'Vaata üle';

  @override
  String get submitRequest => 'Esita taotlus';

  @override
  String get phoneCalls => 'Telefonikõned';

  @override
  String get actionItemsTab => 'Ülesanded';

  @override
  String get record => 'Salvesta';

  @override
  String get noReviewsFound => 'Arvustusi ei leitud';

  @override
  String get oauth => 'OAuth';

  @override
  String get urlCopied => 'URL kopeeritud';

  @override
  String get actionItemReminderTitle => 'Omi meeldetuletus';

  @override
  String sharedTasksAdded(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Sinu loendisse lisati $count ülesannet',
      one: 'Sinu loendisse lisati 1 ülesanne',
    );
    return '$_temp0';
  }

  @override
  String get contactsPermissionRequiredForSms => 'SMS-i kaudu jagamiseks on vajalik kontaktide luba';

  @override
  String get apiKeyRevokedSuccessfully => 'API võti tühistatud edukalt';

  @override
  String get authorizationSuccessful => 'Autoriseerimine õnnestus!';

  @override
  String get unpinAction => 'Eemalda esiletõstmine';

  @override
  String get syncingStatus => 'Sünkroonimine';

  @override
  String get audioFormatLabel => 'Helivorming';

  @override
  String get phoneSelectCountryTitle => 'Vali riik';

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'Top $percentile% kasutaja';
  }

  @override
  String get phoneContactsTab => 'Kontaktid';

  @override
  String get reply => 'Vasta';

  @override
  String get openingShareSheet => 'Jagamislehe avamine…';

  @override
  String get creatingAppIcon => 'Rakenduse ikooni loomine…';

  @override
  String get deviceOnboardingStartSpeaking => 'Hakka rääkima…';

  @override
  String get wrappedAHilariousMoment => 'Naljakas hetk';

  @override
  String get paidApp => 'Tasuline rakendus';

  @override
  String get wrappedStruggleHeader => 'Võitlus';

  @override
  String get speakerTagPromptDontKnow => 'Keegi, keda ma ei tunne';

  @override
  String get wrappedStarting => 'Alustamine…';

  @override
  String get getButton => 'Hangi';

  @override
  String get syncCustomSttWarningTitle => 'Sünkroonimine kasutab Omi transkriptsiooni';

  @override
  String get download => 'Laadi alla';

  @override
  String get addScreenshot => 'Lisa ekraanipilt';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return '$serviceName ühendamine ebaõnnestus: $error';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'Palun ühenda uuesti, et jätkata oma $deviceName kasutamist.';
  }

  @override
  String get configureDailySummaryDigest => 'Seadista oma igapäevane ülesannete kokkuvõte';

  @override
  String get showShortConversationsDesc => 'Kuva künnisest lühemaid vestlusi';

  @override
  String participantsSummaryUncounted(String name) {
    return '$name ja teised';
  }

  @override
  String fairUseBudgetUsed(String used, String limit) {
    return '${used}m / ${limit}m';
  }

  @override
  String get add => 'Lisa';

  @override
  String get disconnect => 'Katkesta ühendus';

  @override
  String get enterApiKey => 'Sisestage oma API võti';

  @override
  String get msgMaxFilesLimit => 'Saate valida kuni 4 faili';

  @override
  String get space => 'Tühik';

  @override
  String get upgrade => 'Uuenda';

  @override
  String get tapToView => 'Puudutage vaatamiseks';

  @override
  String get summaryTemplate => 'Kokkuvõtte mall';

  @override
  String get chatAppsWaitingTitle => 'Ootan sinu sõnumit';

  @override
  String yesterdayAtTime(String time) {
    return 'Eile kell $time';
  }

  @override
  String get cancel => 'Tühista';

  @override
  String get checkingAppleWatch => 'Apple Watchi kontrollimine…';

  @override
  String syncCardDownloadPercentSpeed(int percent, String speed) {
    return '$percent% · $speed KB/s';
  }

  @override
  String get finalTouches => 'Viimased lihvid';

  @override
  String get weekdaySat => 'Lau';

  @override
  String get fairUseWeekly => 'Nädalane periood';

  @override
  String get invalidPaymentUrl => 'Vigane makse URL';

  @override
  String get transcriptionSlowerOnDevice => 'Seadmes transkriptsioon võib sellel seadmel olla aeglasem.';

  @override
  String get noListsInSpace => 'Selles ruumis loendeid ei leitud';

  @override
  String get deviceDiagnostics => 'Seadme diagnostika';

  @override
  String get askAnything => 'Küsi mida tahes';

  @override
  String confidenceMeterLabel(String level) {
    return 'Kindlus: $level';
  }

  @override
  String get permissionReadTasks => 'Loe ülesandeid';

  @override
  String get skipForNow => 'Jäta praegu vahele';

  @override
  String get setupCompletedUrl => 'Seadistuse lõpetamise URL';

  @override
  String get saySomething => 'Ütle midagi…';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get chatAppsEntryTitle => 'Vestle Omiga';

  @override
  String get chatAppsTelegramStepOpen => 'Puuduta all nuppu Ava Telegram';

  @override
  String get pleaseEnterValidPayPalMeLink => 'Palun sisestage kehtiv PayPal.me link';

  @override
  String get syncFlowIntro =>
      'Salvestised kantakse sinu seadmest sellesse telefoni ja salvestatakse kohapeal ning seejärel laaditakse üles Omi serverisse, kus need transkribeeritakse ja muudetakse vestlusteks.';

  @override
  String get cantFindDeviceHint =>
      'Ei leia seadet? Veendu, et see on sisse lülitatud ja telefoni lähedal, ning otsi uuesti.';

  @override
  String get tryAdjustingFilter => 'Proovige kohandada otsingut või filtrit';

  @override
  String get failedConnectionsRecent => 'Ebaõnnestunud ühendused (viimased 7 päeva)';

  @override
  String get captureSourceCall => 'Kõne';

  @override
  String get storageLocationPhone => 'Telefon';

  @override
  String get voiceMatchClose => 'Lähedane vaste';

  @override
  String get reviewChangeUndone => 'Tagasi võetud. Omi ei tee seda ise uuesti.';

  @override
  String get tasksNoProject => 'Projekti pole';

  @override
  String get dataAccessNotice => 'Andmetele juurdepääsu teatis';

  @override
  String deviceStorageFree(String free) {
    return '$free vaba';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'Juba eksporditud $platform';
  }

  @override
  String get recapDeletedSnackbar => 'Kokkuvõte kustutatud';

  @override
  String get apiUrlRequired => 'API URL on nõutud';

  @override
  String get getOmiUnlimitedFree => 'Saage Omi Unlimited tasuta, panustades oma andmetega AI mudelite treenimisse.';

  @override
  String get wrappedShare => 'Jaga';

  @override
  String get tasksTomorrow => 'Homme';

  @override
  String get chatAppsShowInAppOn => 'Sees: need ilmuvad Omi rakenduses kirjutuskaitstud vestlustena.';

  @override
  String get errorActivatingAppIntegration =>
      'Viga rakenduse aktiveerimisel. Kui see on integratsioonirakendus, veendu, et seadistus on lõpule viidud.';

  @override
  String get readChatRepliesAloudDescription => 'Räägib ainult siis, kui \"Häälvastus\" seda lubab.';

  @override
  String get addDueDate => 'Lisa tähtaeg';

  @override
  String get translated => 'tõlgitud';

  @override
  String get dontAskAgain => 'Ära küsi uuesti';

  @override
  String get fullAccessScope => 'Täielik juurdepääs';

  @override
  String get firmwareUpdated => 'Püsivara uuendatud';

  @override
  String get deviceOnboardingVoiceReplyPreviewThroughPhoneSpeaker => 'Läbi telefoni kõlari';

  @override
  String get prompt => 'Viip';

  @override
  String get dreamReportDeletedItem => 'Kustutatud üksus';

  @override
  String chatAppsDisconnectChannel(String app) {
    return 'Katkesta $app ühendus';
  }

  @override
  String get appleHealthDeniedBody =>
      'Omil pole luba teie Apple Health\'i andmete lugemiseks. Lubage see: iOS Seaded → Privaatsus ja turvalisus → Health → Omi.';

  @override
  String endsOnDate(String date) {
    return 'Lõpeb $date';
  }

  @override
  String get searchSettings => 'Otsi seadetest';

  @override
  String get pairingDescNeoOne => 'Vajutage ja hoidke toitenuppu, kuni LED vilgub. Seade on leitav.';

  @override
  String get checkingNextSevenDays => 'Kontrollitakse järgmist 7 päeva';

  @override
  String get confidenceLikely => 'Tõenäoline';

  @override
  String get appleHealthFeatureChatTitle => 'Vestle oma tervisest';

  @override
  String get loadingDevices => 'Seadmete laadimine…';

  @override
  String get writeSomething => 'Kirjuta midagi';

  @override
  String syncCardProgressOf(int current, int total) {
    return '$current / $total';
  }

  @override
  String get unableToOpenWatchApp =>
      'Apple Watchi rakendust ei saa avada. Avage Watchi rakendus käsitsi oma Apple Watchis ja installige Omi jaotisest \"Saadaolevad rakendused\".';

  @override
  String get dreamReportWouldFix => 'Parandaks';

  @override
  String get doubleTap => 'Topeltpuudutus';

  @override
  String get speakerTagPromptSomeoneElse => 'Keegi teine…';

  @override
  String get cancelTransfer => 'Tühista ülekanne';

  @override
  String get capabilityExternalIntegration => 'Väline integratsioon';

  @override
  String get sttLanguageFollowsPrimary => 'Järgib sinu põhikeelt';

  @override
  String get wrappedCringeMomentTitle => 'Piinlik hetk';

  @override
  String get allRecordingsSynced => 'Kõik salvestised on sünkroonitud';

  @override
  String get reviewConfirm => 'Kinnita';

  @override
  String get checkBackLaterForNewApps => 'Kontrolli hiljem uusi rakendusi';

  @override
  String get referAFriend => 'Soovita sõbrale';

  @override
  String cleanUpLead(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other:
          'Omi ei ole nende $count inimese suhtes kindel. Enamik on ärakirjadest valesti kuuldud nimed. Eemalda märge nendelt, keda soovid alles hoida.',
      one: 'Omi ei ole selle inimese suhtes kindel. Eemalda märge, et ta alles hoida.',
    );
    return '$_temp0';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return 'Muuta $item privaatseks?';
  }

  @override
  String get chatQuotaSubtitle => 'AI chat messages used with Omi this month.';

  @override
  String get failedTryAgain => 'Ebaõnnestus? Proovi uuesti';

  @override
  String get deleteAllFiles => 'Kustuta kõik salvestised';

  @override
  String get onDeviceModelDownloadSuccess => 'Mudel alla laaditud';

  @override
  String get reviewNoChangesTitle => 'Muudatusi pole veel';

  @override
  String get useMobileAppToCapture => 'Kasutage heeli salvestamiseks mobiilirakendust';

  @override
  String get setYourName => 'Määra oma nimi';

  @override
  String get tasksGroupByDate => 'Rühmita kuupäeva järgi';

  @override
  String get diagnosticsLast7Days => 'Viimased 7 päeva';

  @override
  String get deviceOnboardingStatusConnected => 'Ühendatud';

  @override
  String get actionItemCreatedSuccessfully => 'Ülesanne edukalt loodud';

  @override
  String get thursdayAbbr => 'N';

  @override
  String get wifiConfiguration => 'WiFi seadistamine';

  @override
  String get cancelReasonFoundAlternative => 'Leidsin alternatiivi';

  @override
  String get process => 'Töötle';

  @override
  String get help => 'Abi';

  @override
  String get rollbackConfirmTitle => 'Taastada püsivara?';

  @override
  String get visibility => 'Nähtavus';

  @override
  String get evidenceNotHeard => 'Pole veel vestluses kuuldud';

  @override
  String get messageReported => 'Sõnumist teatati edukalt.';

  @override
  String get readyToChat => '✨ Valmis vestluseks!';

  @override
  String get tryDifferentFilter => 'Proovige teist filtrit';

  @override
  String get header => 'Päis';

  @override
  String get wrappedBestHeader => 'Parimad';

  @override
  String get memoryDontUse => 'Ära kasuta';

  @override
  String get appStore => 'App Store';

  @override
  String get deleteMeetingScreenshotMessage =>
      'See eemaldab ekraanipildi selle koosoleku märkmest. Seda ei saa tagasi võtta.';

  @override
  String get categoryShopping => 'Ostlemine';

  @override
  String get voiceResponseOff => 'Väljas';

  @override
  String get bluetoothNeeded =>
      'Omi vajab Bluetoothi, et ühenduda teie kantava seadmega. Palun lubage Bluetooth ja proovige uuesti.';

  @override
  String get googleCalendarComingSoon => 'Google Calendar integratsioon tuleb varsti!';

  @override
  String get max => 'Maks';

  @override
  String get homeScreen => 'Avakuva';

  @override
  String get chatAppsTelegramStepStart => 'Puuduta oma vestluses Omiga nuppu Alusta';

  @override
  String get greetingAfternoon => 'Tere päevast';

  @override
  String get unpair => 'Tühista sidumine';

  @override
  String get diagnosticsVerdictReconnects => 'Taasühendub ise';

  @override
  String get macOsCalendar => 'macOS kalender';

  @override
  String get onboardingSetupStepLanguage => 'Transkriptsiooni häälestamine sinu keelele';

  @override
  String get mcpOAuthSetup =>
      'Lehel claude.ai lisa kohandatud konnektor ja kleebi serveri URL. Kui Claude küsib täiustatud OAuth Client ID-d, kasuta allolevat väärtust ja jäta saladus tühjaks — ära kunagi kasuta oma MCP API võtit OAuth saladusena.';

  @override
  String get wednesdayAbbr => 'K';

  @override
  String get selectAudioInput => 'Valige helisisend';

  @override
  String get deviceDisconnectedMessage => 'Teie Omi on ühendus katkestatud 😔';

  @override
  String get reprocessConversation => 'Töötle vestlust uuesti';

  @override
  String get goal => 'EESMÄRK';

  @override
  String mergeConversationsMessage(int count) {
    return 'See ühendab $count vestlust üheks. Kogu sisu ühendatakse ja luuakse uuesti.';
  }

  @override
  String get everyXSeconds => 'Iga x sekundi järel';

  @override
  String get chatAppsLocked => 'Nõuab Omi Pro';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl => 'Kehtetu loodud vestluse veebihaagi URL';

  @override
  String get secureAuthViaAppleId => 'Turvaline autentimine Apple ID kaudu';

  @override
  String connectingToDeviceName(String deviceName) {
    return 'Ühendamine seadmega $deviceName';
  }

  @override
  String get listeningSubtitle => 'Aeg, mil Omi on aktiivselt kuulanud.';

  @override
  String get capturing => 'Salvestamine';

  @override
  String get enterWifiNetworkName => 'Sisestage WiFi võrgu nimi';

  @override
  String get noAppsAvailable => 'Rakendusi pole saadaval';

  @override
  String get installingFirmware => 'Püsivara paigaldamine';

  @override
  String get transferToPhone => 'Kanna telefoni';

  @override
  String get voiceResponseMode => 'Hääleline vastus';

  @override
  String get messageCopied => '✨ Sõnum kopeeritud lõikelauale';

  @override
  String get discardRecordingMessage => 'Sinu häälenäidist pole veel salvestatud. Kui lahkud nüüd, see kustutatakse.';

  @override
  String chatAppsIMessageBody(String code) {
    return 'Tere Omi, sidumiskood $code';
  }

  @override
  String get failedToRefreshWhoopStatus => 'Whoopi ühenduse oleku värskendamine ebaõnnestus.';

  @override
  String get youreOnAnnualPlan => 'Olete aastasel plaanil';

  @override
  String timeHoursPlural(int count) {
    return '$count tundi';
  }

  @override
  String get usageOnline => 'Internetis';

  @override
  String get validPortRequired => 'Kehtiv port on nõutud';

  @override
  String get howItWorks => 'Kuidas see töötab';

  @override
  String get viewTemplate => 'Vaata malli';

  @override
  String get dreamReportNothingFound => 'Pole midagi parandada';

  @override
  String get personTalkTime => 'Rääkimisaeg';

  @override
  String get evidenceNoVoice => 'Hääleproovi veel pole';

  @override
  String get makeMyAppPublic => 'Tee minu rakendus avalikuks';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'Bluetoothi loa olek: $status. Palun kontrollige Süsteemieelistusi.';
  }

  @override
  String get noRecordings => 'Salvestisi pole';

  @override
  String get usageChatThisMonth => 'Chat this month';

  @override
  String get addAppEnterChatPrompt => 'Sisestage vestluse viip oma rakenduse jaoks';

  @override
  String daysAgo(int count) {
    return '$count päeva tagasi';
  }

  @override
  String get processing => 'Töötlemine';

  @override
  String get deviceOnboardingStatusTurningOff => 'Lülitan välja…';

  @override
  String get newTag => 'UUS';

  @override
  String get permissionDescReadTasks => 'See rakendus pääseb ligi sinu ülesannetele.';

  @override
  String get time => 'Aeg';

  @override
  String get recording => 'Salvestamine';

  @override
  String get speakerTagPromptWhoIsThis => 'Kes see on?';

  @override
  String chatUsageMessagesNoLimit(String used) {
    return 'Vestlus: $used sõnumit sel kuul';
  }

  @override
  String get importantTradeoffs => 'Olulised kompromissid:';

  @override
  String get makeAllPublic => 'Muuda kõik mälestused avalikuks';

  @override
  String get noSpeechDesc =>
      'Me ei suutnud kõnet tuvastada. Palun veenduge, et räägite vähemalt 10 sekundit ja mitte rohkem kui 3 minutit.';

  @override
  String get searchPartialFailure => 'Mõnda tulemust ei õnnestunud laadida';

  @override
  String get prerecordedTranscript => 'Eelsalvestatud';

  @override
  String get confirm => 'Kinnita';

  @override
  String get statusCalling => 'Helistamine…';

  @override
  String get wrappedConvos => 'vestlust';

  @override
  String get unresolvedSpeakersTitle => 'Kõnelejate siltidest';

  @override
  String get writeYourReply => 'Kirjuta oma vastus…';

  @override
  String get localCopiesSection => 'Kohalikud koopiad';

  @override
  String get noSummaryYet => 'Kokkuvõtet veel pole';

  @override
  String get wrappedBiggestHeader => 'Suurim';

  @override
  String get error => 'Viga';

  @override
  String get deviceWillRestart => 'Seade taaskäivitub.';

  @override
  String get consentDataMessage =>
      'Jätkates salvestatakse teie vestlused, salvestised ja isikuandmed turvaliselt meie serverites. Teie helisalvestisi ja transkriptsioone töötlevad kolmandate osapoolte AI-teenused (sealhulgas Deepgram transkriptsiooni ja OpenAI analüüsi jaoks), et pakkuda teile AI-põhiseid ülevaateid ja võimaldada kõiki rakenduse funktsioone.';

  @override
  String get connectMacOsCalendar => 'Ühendage oma kohalik macOS kalender';

  @override
  String get captureSourcePhoneMic => 'Telefoni mikrofon';

  @override
  String get setupCompleted => 'Lõpetatud';

  @override
  String get installOmiOnAppleWatchDescription =>
      'Apple Watchi kasutamiseks Omiga peate esmalt installima Omi rakenduse oma kellale.';

  @override
  String get toggleControlBar => 'Lülita juhtpaneeli';

  @override
  String get onboardingBluetoothDeniedSystemPrefs => 'Bluetoothi luba keelatud. Palun andke luba Süsteemieelistustes.';

  @override
  String get syncCancelled => 'Sünkroonimine tühistatud';

  @override
  String get firmwareDisconnectUsb => 'Eemaldage USB';

  @override
  String get processNow => 'Töötle kohe';

  @override
  String get appIdNotFoundError => 'Rakenduse ID-d ei leitud';

  @override
  String get editDueDate => 'Muuda tähtaega';

  @override
  String get home => 'Avaleht';

  @override
  String get tasksOverdue => 'Tähtaja ületanud';

  @override
  String get statusCompleted => 'Lõpetatud';

  @override
  String get otaStarting => 'Värskenduse alustamine…';

  @override
  String get monthApr => 'apr';

  @override
  String get conversationTasksEmptyMessage => 'Selle vestluse ülesanded ilmuvad siia.';

  @override
  String get useDifferentAccount => 'Kasuta teist kontot';

  @override
  String get reviewReasonNotUseful => 'Pole kasulik';

  @override
  String get anonymousUser => 'Anonüümne kasutaja';

  @override
  String get viewPlansDescription => 'Halda oma tellimust ja vaata kasutusstatistikat';

  @override
  String invalidJson(String error) {
    return 'Vigane JSON: $error';
  }

  @override
  String get deleteActionItem => 'Kustuta ülesanne';

  @override
  String get confirmCancellation => 'Kinnita tühistamine';

  @override
  String get tapToDelete => 'Puuduta kustutamiseks';

  @override
  String get onTheCallEnterThisCode => 'Kone ajal sisestage see kood';

  @override
  String get stableFirmware => 'Stabiilne püsivara';

  @override
  String get triggerEvents => 'Käivitavad sündmused';

  @override
  String get speakerTagPromptSaveVoicesTitle => 'Jäta meelde nende inimeste hääled, kellele nime annad';

  @override
  String get syncedFilesDeleted => 'Sünkroniseeritud salvestised kustutatud';

  @override
  String get cloudStorageDesc =>
      'Pärast üleslaadimist töödeldakse ja transkribeeritakse teie salvestised. Vestlused on saadaval minuti jooksul.';

  @override
  String get failedToUpdateFolder => 'Kausta värskendamine ebaõnnestus';

  @override
  String dreamReportFound(int fixes, int asks) {
    String _temp0 = intl.Intl.pluralLogic(
      fixes,
      locale: localeName,
      other: '$fixes parandust',
      one: '1 parandus',
    );
    String _temp1 = intl.Intl.pluralLogic(
      asks,
      locale: localeName,
      other: '$asks soovitust',
      one: '1 soovitus',
    );
    return '$_temp0 · $_temp1';
  }

  @override
  String get anotherPlatform => 'teise platvormiga';

  @override
  String get wrappedTopPhrasesLabel => 'TOP FRAASID';

  @override
  String get dataAccessWarning =>
      'See rakendus pääseb ligi teie andmetele. Omi AI ei vastuta selle eest, kuidas see rakendus teie andmeid kasutab, muudab või kustutab';

  @override
  String get pleaseCompleteAuthentication =>
      'Palun lõpetage autentimine oma brauseris. Kui olete valmis, naasake rakendusse.';

  @override
  String get dailySummaryTitle => 'Päevane Kokkuvõte';

  @override
  String get managePeople => 'Halda inimesi';

  @override
  String get dreamReportEmptyBody => 'Dream vaatab umbes kord tunnis üle, mis su kontol muutus.';

  @override
  String get couldNotOpenPaymentSettings => 'Makseseadeid ei saanud avada. Palun proovi uuesti.';

  @override
  String get locationServiceDisabled => 'Asukohateenused keelatud';

  @override
  String get understanding => 'Mõistmine';

  @override
  String get recapDeleteFailed => 'Kokkuvõtet ei saanud kustutada. Proovi hiljem uuesti.';

  @override
  String get deleteKnowledgeGraphQuestion => 'Kustutada teadmiste graafik?';

  @override
  String get wrappedYourBuddy => 'Sinu sõber!';

  @override
  String chatAppsChatIn(String app) {
    return 'Vestlus rakenduses $app';
  }

  @override
  String get speechDurationDescription => 'Veenduge, et räägite vähemalt 5 sekundit ja mitte rohkem kui 90.';

  @override
  String get reviewReasonAlreadyDone => 'Juba tehtud';

  @override
  String get phoneSetupStep2Title => 'Sisestage kinnituskood';

  @override
  String get tasksClearCompleted => 'Kustuta lõpetatud';

  @override
  String get searchingForDevices => 'Seadmete otsimine';

  @override
  String get siriIndexSettingDescription =>
      'Allow Siri to find your conversations, memories, and tasks on this device. Turning this off removes them from Apple search.';

  @override
  String get markIncomplete => 'Märgi lõpetamatuks';

  @override
  String get onboardingBluetoothRequired => 'Seadmega ühenduse loomiseks on vajalik Bluetoothi luba.';

  @override
  String get searchAppsPlaceholder => 'Otsi 1500+ rakendust';

  @override
  String get pleaseEnterName => 'Palun sisesta nimi';

  @override
  String get paymentMethodCharged => 'Teie olemasolev makseviis debiteeritakse automaatselt, kui teie kuuplaan lõpeb';

  @override
  String get allMemoriesAreNowPublic => 'Kõik mälestused on nüüd avalikud';

  @override
  String taskDueDate(String date) {
    return 'Tähtaeg $date';
  }

  @override
  String get pendantPausesUntilYouFinish => 'Ripats on peatatud, kuni lõpetad';

  @override
  String get failedToAuthorize => 'Autoriseerimine ebaõnnestus. Palun proovige uuesti.';

  @override
  String get mergeConversationsSuccessTitle => 'Vestlused ühendati edukalt';

  @override
  String get peopleFilterNeedsVoice => 'Hääl puudub';

  @override
  String get clickToBeginRecordingSystemAudio => 'Klõpsake süsteemiheli salvestamise alustamiseks';

  @override
  String get fairUseStageRestrict => 'Keelatud';

  @override
  String get nextResult => 'Järgmine tulemus';

  @override
  String get chatAppsContactsApp => 'Kontaktid';

  @override
  String get categoryEmotionalSupport => 'Emotsionaalne tugi';

  @override
  String get wrappedYourHeader => 'Sinu';

  @override
  String get pendantPausesDuringCall => 'Ripats on kõne ajal peatatud';

  @override
  String noConversationsOnDate(String date) {
    return 'Vestlusi pole kuupäeval $date';
  }

  @override
  String get chatStarterYesterday => 'Mida ma eile tegin?';

  @override
  String get entityNotRight => 'Pole õige?';

  @override
  String get failedToCreateShareLink => 'Jagamislingi loomine ebaõnnestus';

  @override
  String get sync => 'Sünkrooni';

  @override
  String get micGainDescMax => 'Maksimum - kasutage ettevaatusega';

  @override
  String get sttNone => 'Puudub';

  @override
  String get chatAppsCodeNote => 'Kood töötab ainult ühe korra ja aegub 10 minuti pärast.';

  @override
  String get aiGenAppCreatedSuccessfully => 'Rakendus edukalt loodud!';

  @override
  String lastNEvents(int count) {
    return 'Viimased $count sündmust';
  }

  @override
  String get phoneDeleteButton => 'Kustuta';

  @override
  String get systemAudio => 'Süsteem';

  @override
  String get checkOutMyMemoryGraph => 'Vaata minu mälugraafikut!';

  @override
  String get feedbackTitleBatteryDrain => 'Rääkige meile akuprobleemidest';

  @override
  String get startCallRecording => 'Alusta kõne salvestamist';

  @override
  String get monthlyPlanContinues => 'Teie praegune kuuplaan jätkub kuni arveldusperioodi lõpuni';

  @override
  String get syncStepUploadDesc => 'Sinu salvestis saadetakse Omi serverisse';

  @override
  String get otaKeepNearby => 'Hoia seade värskenduse ajal sisse lülitatuna ja lähedal ning ära sulge rakendust.';

  @override
  String get updatePayPalDetails => 'Värskenda PayPali andmeid';

  @override
  String get termsOfUse => 'Kasutustingimustega';

  @override
  String get apiKeyCreated => 'API võti loodud!';

  @override
  String get deviceOnboardingVoiceReplyPreviewIdle => 'Kuulake oma viimast vastust';

  @override
  String get starOngoing => 'Märgi käimasolev vestlus tärniga';

  @override
  String get largeModelWarning =>
      'See mudel on suur ja võib põhjustada rakenduse krahhi või väga aeglase töö mobiilseadmetes.\n\nSoovitatav on kasutada \"small\" või \"base\" mudelit.';

  @override
  String get selectLanguage => 'Vali keel';

  @override
  String get professionExecutive => 'Juht';

  @override
  String get importFileTooLarge => 'See fail on importimiseks liiga suur.';

  @override
  String get updateRequiredTitle => 'Värskendus on vajalik';

  @override
  String get syncStepBackedUp => 'Vestlus on valmis';

  @override
  String get openWatchApp => 'Ava Watchi rakendus';

  @override
  String get keyNameLabel => 'VÕTME NIMI';

  @override
  String bulkExportSuccess(int count, String platform) {
    return 'Eksporditi $count asukohta $platform';
  }

  @override
  String get couldNotProcessSubscription => 'Tellimust ei õnnestunud töödelda. Palun proovige uuesti.';

  @override
  String get memorizingYourVoice => 'Teie hääle meeldejätmine…';

  @override
  String get processingAudio => 'Heli töötlemine';

  @override
  String get syncYourRecordings => 'Sünkrooni oma salvestused';

  @override
  String get resetToDefault => 'Lähtesta vaikeväärtusele';

  @override
  String get deleteConversation => 'Kustuta vestlus';

  @override
  String get flashCustomFirmwareDescription => 'Paigalda kohandatud püsivara järke';

  @override
  String get deviceUpToDate => 'Teie seade on ajakohane';

  @override
  String get raybanMetaMusicPauseNote => 'Sinu telefoni muusika peatub, kui prillide mikrofon on kasutusel.';

  @override
  String get appleHealthNotAvailable => 'Apple Health pole selles seadmes saadaval';

  @override
  String hints(String text) {
    return 'Vihjed: $text';
  }

  @override
  String get cloudProvider => 'Pilveteenuse pakkuja';

  @override
  String get chooseAnyFileType => 'Vali mis tahes failitüüp';

  @override
  String get reset => 'Lähtesta';

  @override
  String get automaticallyCreateNewPerson => 'Loo automaatselt uus inimene, kui transkriptsioonis tuvastatakse nimi.';

  @override
  String get timeout2Minutes => '2 minutit';

  @override
  String get newMemory => '✨ Uus mälestus';

  @override
  String get chatAppsMoreComing => 'Rohkem rakendusi on tulemas.';

  @override
  String get couldNotLoadKnowledgeGraph => 'Teadmiste graafi ei õnnestunud laadida';

  @override
  String get voiceSettingsAskToTagSubtitle => 'Aeg-ajalt küsib Omi, kes sinu hiljutistes vestlustes rääkis';

  @override
  String get developer => 'Arendaja';

  @override
  String get connectionNeeded => '🌐 Vajalik ühendus';

  @override
  String get helpAndAbout => 'Abi ja teave';

  @override
  String get tasksNoDeadline => 'Tähtajata';

  @override
  String get yourDataIsProtected => 'Teie andmed on kaitstud ja neid reguleerib meie ';

  @override
  String get confirmDeletion => 'Kinnita kustutamine';

  @override
  String get speakerTagPromptClosestVoices => 'Lähimad hääled';

  @override
  String get quicklyPopulateRequest => 'Täida kiiresti tuntud teenusepakkuja päringu vorminguga';

  @override
  String get exportTranscript => 'Ekspordi transkriptsioon';

  @override
  String get resetsSoon => 'Lähtestub peagi';

  @override
  String get showPhoneCallButtonTitle => 'Kuva kõnenuppu';

  @override
  String get wrappedAChallenge => 'Väljakutse';

  @override
  String get revokeKey => 'Tühista võti';

  @override
  String get dailyRecaps => 'Päevased Kokkuvõtted';

  @override
  String get processingConversationProgress => 'Vestlust töödeldakse…';

  @override
  String get freeMinutesMonth => '300 tasuta minutit kuus kaasa arvatud. Piiramatu koos ';

  @override
  String get downloadWhisperModel => 'Laadi alla whisper mudel, et kasutada seadmes transkriptsiooni';

  @override
  String get noMemoriesInCategories => 'Neis kategooriates pole mälestusi';

  @override
  String get checkingNextDays => 'Kontrolli järgmist 30 päeva';

  @override
  String get createAndSubmitNewApp => 'Loo ja esita uus rakendus';

  @override
  String get chatAppsInTheMeantime => 'Vahepeal';

  @override
  String get deleteFlowReasonTitle => 'Miks sa lahkud?';

  @override
  String get tasksSelectAll => 'Vali kõik';

  @override
  String get webhookUrl => 'Webhooki URL';

  @override
  String get selected => 'Valitud';

  @override
  String get batteryDrainIncrease => 'Aku tarbimine suureneb märkimisväärselt.';

  @override
  String get dreamReportFixed => 'Parandatud';

  @override
  String get failedToConnectClickUpRetry => 'ClickUpiga ühendamine ebaõnnestus. Palun proovi uuesti.';

  @override
  String get serverUrl => 'Serveri URL';

  @override
  String get starred => 'Tärniga';

  @override
  String get speakerTagPromptClipUnavailable => 'Seda klippi ei õnnestunud esitada';

  @override
  String get feedbackSubtitleFoundAlternative => 'Tahaksime teada, mis teie tähelepanu köitis.';

  @override
  String get omiButtonActions => 'Omi nupu toimingud';

  @override
  String get invalidRecordingDesc => 'Palun veenduge, et räägite vähemalt 5 sekundit ja mitte rohkem kui 90.';

  @override
  String get switchApiConfirmTitle => 'Vaheta API keskkonda';

  @override
  String gattError(String code) {
    return 'GATT viga ($code)';
  }

  @override
  String get aiGenRegenerateIcon => 'Loo ikoon uuesti';

  @override
  String get connectTaskAppToExport => 'Eksportimiseks ühendage Seadetes ülesannete rakendus';

  @override
  String get firmwareFlashed => 'Püsivara paigaldatud';

  @override
  String get addPerson => 'Lisa isik';

  @override
  String get cancelConsequencesSubtitle => 'Soovitame tungivalt uurida oma teisi võimalusi tühistamise asemel.';

  @override
  String get transcriptCopiedToClipboard => 'Transkriptsioon kopeeritud lõikelauale';

  @override
  String get monthNov => 'nov';

  @override
  String get switchedToOnDevice => 'Lülitatud seadme transkriptsioonile';

  @override
  String get phoneMicOfflineFallbackMessage =>
      'Ühendus puudub – salvestatakse lokaalselt. See transkribeeritakse, kui oled taas võrgus.';

  @override
  String get scopeUserConversations => 'Kasutaja vestlused';

  @override
  String get otherAppResults => 'Teiste rakenduste tulemused';

  @override
  String get chatAppsGetNewCode => 'Hangi uus kood';

  @override
  String get backgroundLocationDenied => 'Tausta asukoha juurdepääs keelatud';

  @override
  String get syncFailureFootnote =>
      'Kui töötlemine ebaõnnestub, proovitakse salvestist järgmise sünkroonimise käigus automaatselt uuesti.';

  @override
  String get checkingNext7Days => 'Järgmise 7 päeva kontrollimine';

  @override
  String get monthlyPayouts => 'Igakuised väljamaksed';

  @override
  String get searchLanguageHint => 'Otsige keelt nime või koodi järgi';

  @override
  String get gotIt => 'Selge';

  @override
  String get pleaseEnterAppName => 'Palun sisestage rakenduse nimi';

  @override
  String get newConversations => 'Uued vestlused';

  @override
  String get learnMoreAtOmiTraining => 'Lisateave omi.me/training';

  @override
  String get entityOpenTasks => 'Avatud ülesanded';

  @override
  String get summary => 'Kokkuvõte';

  @override
  String get copied => 'Kopeeritud';

  @override
  String get feedbackReasonRecordingDelayedOrStuck => 'Delayed or stuck';

  @override
  String get taskIntegrations => 'Ülesannete integratsioonid';

  @override
  String get tailoredConversationSummaries => 'Kohandatud vestluste kokkuvõtted';

  @override
  String get skipThisQuestion => 'Jäta see küsimus vahele';

  @override
  String get descriptionOptional => 'Kirjeldus (valikuline)';

  @override
  String get about => 'Teave';

  @override
  String shareWithContactsCount(int count) {
    return 'Jaga $count kontaktiga';
  }

  @override
  String get discardChangesTitle => 'Kas loobuda muudatustest?';

  @override
  String get transcriptionDiagnostics => 'Transkriptsiooni diagnostika';

  @override
  String get syncStatusFileUnavailable => 'Fail pole saadaval';

  @override
  String get createNewApp => 'Loo uus rakendus';

  @override
  String verifiedHoursAgo(int hours) {
    return 'Kinnitatud ${hours}t tagasi';
  }

  @override
  String get chatLimitReachedTitle => 'Vestluse limiit täis';

  @override
  String get wrappedShareText => 'Minu 2025, jäädvustatud Omi poolt ✨ omi.me/wrapped';

  @override
  String get reconnectionsRecent => 'Taasühendused (viimased 7 päeva)';

  @override
  String get appAccess => 'Rakenduse juurdepääs';

  @override
  String get description => 'Kirjeldus';

  @override
  String phoneFreeCallsRemainingWithMax(int remaining, int limit, int minutes) {
    return 'Sel kuul on jäänud $remaining tasuta kõnet $limit-st · kuni $minutes min igaüks';
  }

  @override
  String get clearOmisMemory => 'Tühjenda Omi mälu';

  @override
  String get exportSummary => 'Ekspordi kokkuvõte';

  @override
  String get install => 'Paigalda';

  @override
  String get syncStepBackedUpDesc => 'Leiad selle jaotisest Vestlused';

  @override
  String get localProcessingInfo =>
      'Heli töödeldakse kohapeal. Töötab võrguühenduseta, on privaatsem, kuid kasutab rohkem akut.';

  @override
  String get connectStripeOrPayPal => 'Ühenda Stripe või PayPal, et saada rakenduse eest makseid.';

  @override
  String get wrappedMomentsHeader => 'Hetked';

  @override
  String get systemDefault => 'Süsteemi vaikimisi';

  @override
  String get keepUsingPendant => 'Jätka ripatsiga';

  @override
  String get paymentFailedToFetchCountries => 'Toetatud riikide toomine ebaõnnestus. Proovige hiljem uuesti.';

  @override
  String get micGainDescLow => 'Väga vaikne - valjude keskkondade jaoks';

  @override
  String get errorUpdatingConversationTitle => 'Viga vestluse pealkirja uuendamisel';

  @override
  String timeSecsSingular(int count) {
    return '$count sek';
  }

  @override
  String timeCompactHours(int count) {
    return '${count}t';
  }

  @override
  String get browseInstallCreateApps => 'Sirvi, installi ja loo rakendusi';

  @override
  String get reddit => 'Reddit';

  @override
  String get chooseFile => 'Vali fail';

  @override
  String participantsSummary(String name, int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count teist',
      many: '$count teist',
      few: '$count teist',
      one: '1 teine',
    );
    return '$name + $_temp0';
  }

  @override
  String get connectingYourStripeAccount => 'Teie Stripe konto ühendamine';

  @override
  String get cancelReasonMissingFeatures => 'Puuduvad funktsioonid';

  @override
  String get chatTitle => 'Vestlus';

  @override
  String get chatAppsNotifyMe => 'Anna mulle teada';

  @override
  String get appAccessDesc =>
      'Järgmised rakendused pääsevad juurde teie andmetele. Puudutage rakendust selle õiguste haldamiseks.';

  @override
  String get captureDisplayDetectionFailed => 'Ekraani tuvastamine ebaõnnestus. Salvestamine peatatud.';

  @override
  String get recapRegeneratedSnackbar => 'Kokkuvõte loodi uuesti';

  @override
  String get speakerTagPromptLabeledYouToast => 'Märgistatud sinuna';

  @override
  String get categoryFinancial => 'Rahandus';

  @override
  String get chatAppsPrefilled => 'Eeltäidetud';

  @override
  String get noSummaryForConversation => 'Selle vestluse jaoks\npole kokkuvõtet saadaval.';

  @override
  String get aiPrompts => 'AI vihjed';

  @override
  String get view => 'Vaata';

  @override
  String get dataAlwaysEncrypted => 'Olenemata tasemest on teie andmed alati krüpteeritud puhkeolekus ja edastamisel.';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item kopeeritud lõikelauale';
  }

  @override
  String get currentPlan => 'Praegune';

  @override
  String get phoneCallsUpsellFeature1 => 'Iga kõne reaalajas transkriptsioon';

  @override
  String get lowBatteryAlertTitle => 'Tühja aku hoiatus';

  @override
  String get enterConversationTitle => 'Sisesta vestluse pealkiri…';

  @override
  String get pasteJsonConfig => 'Kleepige oma JSON-konfiguratsioon allpool:';

  @override
  String get dreamReportRunLimit => 'Täna pole käsitsi käivitusi enam järel';

  @override
  String get translationNoticeMessage =>
      'Omi tõlgib vestlused teie põhikeelde. Värskendage seda igal ajal jaotises Seaded → Profiilid.';

  @override
  String get aiGenFailedToRegenerateIcon => 'Ikooni uuesti genereerimine ebaõnnestus';

  @override
  String get pairingDescBee => 'Vajutage nuppu 5 korda järjest. Tuli hakkab vilkuma siniselt ja roheliselt.';

  @override
  String sharedTasksAddButton(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Lisa $count ülesannet',
      one: 'Lisa 1 ülesanne',
    );
    return '$_temp0';
  }

  @override
  String get paymentFailedToSavePaypal => 'PayPali andmete salvestamine ebaõnnestus. Proovige hiljem uuesti.';

  @override
  String get couldNotLoadCheckout => 'Makselehte ei õnnestunud laadida. Kontrolli ühendust ja proovi uuesti.';

  @override
  String get capabilitySummary => 'Kokkuvõte';

  @override
  String get selectYourCountry => 'Valige oma riik';

  @override
  String uploadingAudioForTranscription(String duration) {
    return 'Laadin üles $duration heli transkribeerimiseks…';
  }

  @override
  String get conversationUrlCouldNotBeShared => 'Vestluse URL-i ei saanud jagada.';

  @override
  String get otaStartFailed =>
      'Värskendust ei õnnestunud alustada. Kontrolli Wi-Fi nime ja parooli ning proovi uuesti.';

  @override
  String get triggersWhenAudioBytesReceived => 'Käivitatakse, kui saadakse helibaidid.';

  @override
  String get wrappedMy2025 => 'Minu 2025';

  @override
  String timeCompactSecs(int count) {
    return '${count}s';
  }

  @override
  String get shareWithAttendees => 'Jaga osalejatega';

  @override
  String get recordingsSyncAutomatically => 'Salvestised sünkroonitakse automaatselt — tegevust pole vaja.';

  @override
  String get whereDidYouHearAboutOmi => 'Kuidas sa meid leidsid?';

  @override
  String get captureMicrophonePermissionInSystemPreferences => 'Andke mikrofoni luba Süsteemieelistustes';

  @override
  String audioUploadFailedTapRetry(String duration) {
    return 'Üleslaadimine ebaõnnestus — $duration heli on sinu telefonis alles. Uuesti proovimiseks puuduta.';
  }

  @override
  String get captureModeLaterDescription => 'Salvesta heli kohe ja transkribeeri, millal soovid.';

  @override
  String get cleanUpNothingTitle => 'Pole midagi puhastada';

  @override
  String get deletePersonLabel => 'Kustuta isik';

  @override
  String get attachedFiles => '📎 Lisatud failid';

  @override
  String get editGoal => 'Muuda eesmärki';

  @override
  String get helpsDiagnoseIssues => 'Aitab probleeme diagnoosida';

  @override
  String get bulkDeleteFailed => 'Ülesandeid ei õnnestunud kustutada. Palun proovi uuesti.';

  @override
  String get manifestRefreshFailed => 'Manifesti värskendamine ebaõnnestus';

  @override
  String get searchPlaceholder => 'Otsi';

  @override
  String get appOptions => 'Rakenduse valikud';

  @override
  String get reprocessingConversationProgress => 'Vestlust töödeldakse uuesti…';

  @override
  String get entityWhatOmiKnows => 'Mida Omi teab';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'Vestlus võetakse kokku pärast $minutes minut$suffix vaikust.';
  }

  @override
  String get permissionRevokedMessage => 'Kas soovite, et me eemaldaksime ka kõik teie olemasolevad salvestised?';

  @override
  String get phoneNumberCallerIdHint => 'Parast kinnitamist saab see teie helistaja ID-ks';

  @override
  String chatAppsTextThisTo(String address) {
    return 'Ei avanenud? Saada see numbrile $address';
  }

  @override
  String get upcomingMeetings => 'Tulevased kohtumised';

  @override
  String get preparingSystemAudioCapture => 'Süsteemiheli salvestamise ettevalmistamine';

  @override
  String dreamReportQueued(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count muudatust ootel',
      one: '1 muudatus ootel',
      zero: 'Ootel muudatusi pole',
    );
    return '$_temp0';
  }

  @override
  String get chatReplyFailed => 'Omi ei saanud vastata. Kontrolli ühendust ja proovi uuesti.';

  @override
  String get noDataToMigrateFinalizing => 'Andmeid migreerida pole. Lõpetamine…';

  @override
  String get accessibility => 'Juurdepääsetavus';

  @override
  String get openOmiOnAppleWatch => 'Avage Omi oma\nApple Watchis';

  @override
  String get wrappedGettingItDone => 'Asjade ärategemine';

  @override
  String get rawData => 'Töötlemata andmed';

  @override
  String get passwordsDoNotMatch => 'Paroolid ei kattu';

  @override
  String errorInstallingApp(String appName, String error) {
    return 'Viga $appName installimisel: $error';
  }

  @override
  String deleteQuoted(String name) {
    return 'Kustuta \"$name\"';
  }

  @override
  String get wrappedTopFivePhrases => 'Top 5 fraasi';

  @override
  String get deviceOnboardingHoldButtonHint => 'Hoia nuppu kindlalt all, kuni tuli kustub';

  @override
  String get capabilities => 'Võimalused';

  @override
  String get useMcpApiKey => 'Kasutage oma MCP API võtit';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return '$serviceName integratsioon tuleb peagi';
  }

  @override
  String get wrappedStruggle => 'Väljakutse';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return 'Teavituste loa olek: $status. Palun kontrollige Süsteemieelistusi.';
  }

  @override
  String get meetingScreenshotsTitle => 'Mis oli ekraanil';

  @override
  String verifiedMinutesAgo(int minutes) {
    return 'Kinnitatud ${minutes}m tagasi';
  }

  @override
  String get permissionsRequired => 'Õigused nõutavad';

  @override
  String get speakerTagPromptNotSure => 'Pole kindel';

  @override
  String get current => 'Praegune';

  @override
  String get improveConnectionAction => 'Selge';

  @override
  String get profile => 'Profiil';

  @override
  String get audioPlaybackFailed => 'Heli esitamine ebaõnnestus. Fail võib olla rikutud või puududa.';

  @override
  String get billingYearly => 'Aastane';

  @override
  String get batteryUsageHigher => 'Akukasutus on suurem kui pilves transkriptsiooni puhul.';

  @override
  String get permissionsLabel => 'ÕIGUSED';

  @override
  String get enhanceTranscriptAccuracy => 'Parandage transkriptsiooni täpsust';

  @override
  String get connectedStatus => 'Ühendatud';

  @override
  String get microphonePermissionDenied =>
      'Mikrofoni luba keelatud. Palun andke luba Süsteemieelistused > Privaatsus ja turvalisus > Mikrofon.';

  @override
  String get onDeviceModelDownloadSuccessDesc => 'Whisperi mudel laaditi edukalt alla';

  @override
  String get storageLocationLimitlessPendant => 'Limitless ripats';

  @override
  String get chatAppsLinkExpired => 'See link aegus. Uue saamiseks puuduta nuppu Ava Telegram.';

  @override
  String get captureOfflineBuffering => 'Võrguühenduseta, puhverdamine';

  @override
  String get pleaseCheckInternetConnection => 'Palun kontrollige oma internetiühendust ja proovige uuesti';

  @override
  String get todaysScore => 'Tänane skoor';

  @override
  String get conversationReprocessed => 'Vestlus on uuendatud';

  @override
  String get loadingDuration => 'Kestuse laadimine…';

  @override
  String get noSummary => 'Kokkuvõte puudub';

  @override
  String get raybanMetaMicrophoneReady => 'Mikrofon on valmis';

  @override
  String get applyFilters => 'Rakenda filtrid';

  @override
  String get appDescriptionPlaceholder =>
      'Minu suurepärane rakendus on suurepärane rakendus, mis teeb hämmastav asju. See on parim rakendus!';

  @override
  String get cancelSubscriptionKeepAccessMessage => 'Juurdepääs jääb alles kuni praeguse arveldusperioodi lõpuni.';

  @override
  String get editYourReview => 'Muuda oma arvustust';

  @override
  String get actionItemsTitle => 'Ülesanded';

  @override
  String get raybanMetaAudioOnlyTitle => 'Ray-Ban Meta ainult heli režiim';

  @override
  String get reviewSomeoneElse => 'Keegi teine…';

  @override
  String get betaTesterMessage =>
      'Olete selle rakenduse beetatestija. See ei ole veel avalik. See muutub avalikuks pärast heakskiitu.';

  @override
  String chatAppsIMessageTo(String address) {
    return 'Kellele: Omi · $address';
  }

  @override
  String get comingSoon => 'Tulekul';

  @override
  String rollbackConfirmMessage(String version) {
    return 'See asendab teie praeguse püsivara uusima stabiilse versiooniga ($version). Teie seade taaskäivitub pärast värskendust.';
  }

  @override
  String get termsOfService => 'Teenusetingimustega';

  @override
  String get wrappedNotMentioned => 'Pole mainitud';

  @override
  String get deviceDisconnectedNotificationTitle => 'Teie Omi seade on lahti ühendatud';

  @override
  String get rayBanMetaMicPickerDescription =>
      'Valige prillide Bluetooth-mikrofon. Muusika peatub, kui Omi seda kasutab.';

  @override
  String get chatBlockQuestion => 'Küsimus';

  @override
  String get successfullyConnectedTodoist => 'Edukalt ühendatud Todoistiga!';

  @override
  String voiceRecognitionStatus(String status) {
    String _temp0 = intl.Intl.selectLogic(
      status,
      {
        'ready': 'Hääl on tuvastamiseks valmis',
        'saved_sample_awaiting_embedding': 'Näidis salvestatud, hääle töötlemine on ootel',
        'not_learned': 'Hääl pole õpitud',
        'other': 'Hääle olek teadmata',
      },
    );
    return '$_temp0';
  }

  @override
  String addQueryAsNewPerson(String query) {
    return 'Lisa \"$query\" uue inimesena';
  }

  @override
  String confidenceReasonAutoConfirmed(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Kinnitasid $count automaatset märgistust',
      one: 'Kinnitasid 1 automaatse märgistuse',
    );
    return '$_temp0';
  }

  @override
  String get recordAudioConversations => 'Helisalvestiste salvestamine';

  @override
  String get saveKeyWarning => 'Salvesta see võti kohe! Sa ei näe seda enam kunagi.';

  @override
  String get saveChanges => 'Salvesta muudatused';

  @override
  String get sttModelSlower => 'Aeglasem';

  @override
  String get otaDownloadFailed => 'Püsivara allalaadimine ebaõnnestus. Kontrolli Wi-Fi-ühendust ja proovi uuesti.';

  @override
  String get captureRecordingViewing => 'Vaatad seda salvestist';

  @override
  String get resetFilters => 'Lähtesta filtrid';

  @override
  String get voiceSettingsSaveOthersSubtitle =>
      'Kui annad kellelegi nime, hoiab Omi alles lühikese häälenäidise, et teda järgmine kord ära tunda';

  @override
  String get iveDoneThis => 'Olen seda teinud';

  @override
  String get howSyncingWorks => 'Kuidas sünkroonimine töötab';

  @override
  String greetingWithName(String greeting, String name) {
    return '$greeting, $name';
  }

  @override
  String reviewRemaining(int count) {
    return 'Jäänud $count';
  }

  @override
  String get feedbackReasonRecordingMissingAudio => 'Missing audio';

  @override
  String get appCategoryModalTitle => 'Rakenduse kategooria';

  @override
  String get pushToTalk => 'Vajuta rääkimiseks';

  @override
  String get noApiKeysYet => 'API võtmeid pole veel. Looge üks oma rakendusega integreerimiseks.';

  @override
  String minLabel(int count) {
    return '$count min';
  }

  @override
  String appRatingCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count hinnangut',
      one: '1 hinnang',
    );
    return '$_temp0';
  }

  @override
  String get wrappedFood => 'TOIT';

  @override
  String get aboutAMinuteRemaining => 'Umbes minut jäänud';

  @override
  String get clearLogs => 'Kustuta logid';

  @override
  String get wrappedBook => 'RAAMAT';

  @override
  String get phoneCallSubtitle => 'Salvesta kõne reaalajas transkriptsiooniga';

  @override
  String deleteConversationsTitle(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Kas kustutada $count vestlust?',
      one: 'Kas kustutada 1 vestlus?',
    );
    return '$_temp0';
  }

  @override
  String get deleteSelected => 'Kustuta valitud';

  @override
  String failedToDeleteGraph(String error) {
    return 'Graafi kustutamine ebaõnnestus: $error';
  }

  @override
  String get setupQuestionsIntro => 'Aidake meil Omit paremaks muuta, vastates mõnele küsimusele. 🫶 💜';

  @override
  String get category => 'Kategooria';

  @override
  String get timeout30MinutesDesc => 'Lõpeta vestlus pärast 30-minutilist vaikust';

  @override
  String get goalDeleted => 'Eesmärk kustutatud';

  @override
  String get conversationDisplay => 'Vestluste Kuvamine';

  @override
  String get conversationNoSummaryYet => 'Sellel vestlusel pole veel kokkuvõtet.';

  @override
  String get chatsLowercase => 'vestlused';

  @override
  String get clearChatQuestion => 'Kustuta vestlus?';

  @override
  String get signInTitle => 'Logi sisse';

  @override
  String get loadingKnowledgeGraph => 'Teadmisgraafiku laadimine…';

  @override
  String get goalTracker => 'Eesmärkide jälgija';

  @override
  String get commandRequired => '⌘ on nõutav';

  @override
  String get permissionEnabled => 'Lubatud';

  @override
  String get submitReview => 'Esita arvustus';

  @override
  String chatUsageCost(String used, String limit) {
    return 'Vestlus: \$$used / \$$limit kasutatud sel kuul';
  }

  @override
  String get discard => 'Loobu';

  @override
  String dreamReportPasses(int count, int limit) {
    return '$count/$limit käivitust täna';
  }

  @override
  String get unlockOmiInfiniteMemory => 'Piiramatult mälestusi';

  @override
  String get addAppPersonaConflictWithCapabilities => 'Personat ei saa teiste võimetega valida';

  @override
  String get whyAreYouCanceling => 'Miks tühistate?';

  @override
  String get permissionRequestedExclaim => 'Luba taotletud!';

  @override
  String get chatBlockOpenInMemories => 'Ava mälestustes';

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total objekti';
  }

  @override
  String get deleteActionItemTitle => 'Kustuta ülesanne';

  @override
  String get rollBack => 'Taasta';

  @override
  String get chatAppsOmiPro => 'OMI PRO';

  @override
  String disconnectFromAppDesc(String appName) {
    return 'See eemaldab teie $appName autentimise. Peate uuesti ühendama, et seda uuesti kasutada.';
  }

  @override
  String get onDeviceModelSize => 'Mudeli suurus';

  @override
  String tagSpeaker(int speakerId) {
    return 'Märgi kõneleja $speakerId';
  }

  @override
  String get couldNotOpenUrl => 'URL-i avamine ebaõnnestus. Palun proovige uuesti.';

  @override
  String get conversationNewIndicator => 'Uus';

  @override
  String get notEnoughSpeechDescription => 'Ei tuvastatud piisavalt kõnet. Palun rääkige rohkem ja proovige uuesti.';

  @override
  String get liveRssiOverTime => 'Reaalajas RSSI ajas';

  @override
  String get usageEverywhere => 'Kõikjal';

  @override
  String nConversations(int count) {
    return '$count vestlust';
  }

  @override
  String get wrappedConversationsLabel => 'vestlust';

  @override
  String get usageYear => 'See aasta';

  @override
  String get noContactsMatchSearch => 'Ükski kontakt ei vasta teie otsingule';

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count ülesanne$s kustutatud';
  }

  @override
  String get actionItemMarkedIncomplete => 'Ülesanne märgitud mittelõpetatuks';

  @override
  String get start => 'Alusta';

  @override
  String discardedConversationTitle(String duration) {
    return 'Loobutud · $duration';
  }

  @override
  String get debugLogsCleared => 'Silumislogid kustutatud';

  @override
  String get preparingAudioCapture => 'Helisalvestuse ettevalmistamine';

  @override
  String get availablePaymentMethods => 'Saadaolevad maksemeetodid';

  @override
  String get deleteReasonOther => 'Muu';

  @override
  String get accountCutoverMigrationInProgressTitle => 'Siirto käynnissä';

  @override
  String get connectedKnowledgeData => 'Ühendatud teadmiste andmed';

  @override
  String get wrappedMostFunDay => 'Kõige lõbusam';

  @override
  String get onboardingAccessibilityRequired => 'Brauseri koosolekute tuvastamiseks on vajalik ligipääsetavuse luba.';

  @override
  String get selectActionItems => 'Vali mitu';

  @override
  String switchApiConfirmBody(String environment) {
    return 'Lülituda keskkonnale $environment? Peate rakenduse sulgema ja uuesti avama, et muudatused jõustuksid.';
  }

  @override
  String get whisperModelSizeLarge => 'Suur';

  @override
  String get currentVersion => 'Praegune versioon';

  @override
  String get aiAppGeneratorBannerTitle => 'Loo tehisintellektiga rakendus ühe puudutusega';

  @override
  String get rayBanMetaMicPickerLoadError =>
      'Bluetooth-mikrofone ei saanud laadida. Kontrollige, kas Bluetooth on sisse lülitatud, ja proovige uuesti.';

  @override
  String get noneSelected => 'Valimata';

  @override
  String get entityKeptCurrent => 'Omi hoiab ajakohasena';

  @override
  String migratingFromTo(String source, String target) {
    return 'Migreerimine $source kaudu $target';
  }

  @override
  String get controlNotificationFrequency => 'Määrake, kui sageli Omi saadab teile ennetavaid teavitusi.';

  @override
  String get connectionUptime => 'Tööaeg';

  @override
  String get categoryLabel => 'Kategooria';

  @override
  String get aboutTheApp => 'Rakendusest';

  @override
  String get planSheetChooseYourPlan => 'Vali endale sobiv pakett.';

  @override
  String get almostDone => 'Peaaegu valmis…';

  @override
  String get tasksFromConversationsWillAppear =>
      'Teie vestlustest pärit ülesanded ilmuvad siia.\nKlõpsake ülesande käsitsi lisamiseks nuppu Loo.';

  @override
  String get personLastHeard => 'Viimati kuuldud';

  @override
  String get durationThreshold => 'Kestuse künnis';

  @override
  String get transcriptionServiceDiagnosticStatus => 'Transkriptsiooni teenuse diagnostika olek';

  @override
  String get triggersWhenNewTranscriptReceived => 'Käivitatakse, kui saadakse uus transkriptsioon.';

  @override
  String get aboutOmi => 'Omi kohta';

  @override
  String get identifyingOthers => 'Teiste Tuvastamine';

  @override
  String get phoneCallsSubtitle => 'Helistage reaalajas transkriptsiooniga';

  @override
  String get creatingYourApp => 'Teie rakenduse loomine…';

  @override
  String get analyzingYourData => 'Teie andmete analüüsimine…';
}
