// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Dutch Flemish (`nl`).
class AppLocalizationsNl extends AppLocalizations {
  AppLocalizationsNl([String locale = 'nl']) : super(locale);

  @override
  String get welcomeActionItemsDescription =>
      'Je AI haalt automatisch taken uit je gesprekken. Ze verschijnen hier wanneer ze zijn aangemaakt.';

  @override
  String get chatAppsProblemFailed => 'Er ging iets mis. Probeer het opnieuw.';

  @override
  String get deviceOnboardingStarConversation => 'Lopend gesprek markeren';

  @override
  String get deleteAll => 'Alles verwijderen';

  @override
  String get copySummary => 'Kopieer samenvatting';

  @override
  String get locationAccessDesc => 'Zodat Omi kan vastleggen waar je gesprekken plaatsvonden.';

  @override
  String get firmwareUpdate => 'Firmware-update';

  @override
  String get chatMessages => 'berichten';

  @override
  String get showEventsNoParticipants => 'Evenementen zonder deelnemers tonen';

  @override
  String get sharePeriodYear => 'Dit jaar heeft Omi:';

  @override
  String get dreamReportRunFailed => 'Dream kon niet worden uitgevoerd. Probeer het opnieuw.';

  @override
  String get sttModelAccuracy => 'Nauwkeurigheid';

  @override
  String get scopes => 'Scopes';

  @override
  String get deleteFlowFeedbackSubtitle => 'Wat zou Omi voor jou hebben laten werken?';

  @override
  String appDataAccessTitle(String appName) {
    return '$appName toegang geven?';
  }

  @override
  String get pendantStorageAlmostFull =>
      'De opslag van de hanger is bijna vol — houd de app open om te synchroniseren.';

  @override
  String get deviceOnboardingAllSetDoublePressBadge => '2×';

  @override
  String get copyErrorMessage => 'Foutmelding kopiëren';

  @override
  String get filterMemories => 'Herinneringen filteren';

  @override
  String get helpsDiagnoseIssuesAutoDeletes =>
      'Helpt bij het diagnosticeren van problemen. Wordt na 3 dagen automatisch verwijderd.';

  @override
  String get locationServiceDisabledDesc =>
      'Locatievoorzieningen staan uit op dit apparaat. Zet ze aan in Instellingen.';

  @override
  String chatAppsIsConnected(String app) {
    return '$app is verbonden';
  }

  @override
  String get paymentMethodStripe => 'Stripe';

  @override
  String get deleteReasonTechnicalIssues => 'Te veel technische problemen';

  @override
  String get payments => 'Betalingen';

  @override
  String get verifiedFallback => 'Geverifieerd';

  @override
  String get pleaseWait => 'Even geduld…';

  @override
  String get appLanguage => 'App-taal';

  @override
  String get unknownApp => 'Onbekende app';

  @override
  String get appReEnableFailedBody => 'Deze app kon niet opnieuw worden ingeschakeld. Probeer het opnieuw.';

  @override
  String get somethingWentWrongTryAgain => 'Er is iets misgegaan! Probeer het later opnieuw.';

  @override
  String get upgradeScheduled => 'Upgrade gepland';

  @override
  String get wrappedBuddiesLabel => 'VRIENDEN';

  @override
  String get chatBlockShowMore => 'Meer tonen';

  @override
  String get subscriptionSuccessfulCharged =>
      'Abonnement succesvol! Je bent gefactureerd voor de nieuwe factureringsperiode.';

  @override
  String get phoneCall => 'Telefoongesprek';

  @override
  String get chatAppsRefreshFailed => 'Verversen mislukt. We tonen wat we het laatst zagen.';

  @override
  String get noDesktopAccess => 'Werkt niet op desktop';

  @override
  String get areYouSure => 'Weet je het zeker?';

  @override
  String get resubscribe => 'Opnieuw abonneren';

  @override
  String voiceMatchMeterLabel(String level) {
    return 'Stemmatch: $level';
  }

  @override
  String get syncingBackground => 'We blijven je opnames op de achtergrond synchroniseren.';

  @override
  String get signOutQuestion => 'Uitloggen?';

  @override
  String chatAppsReadOnlyBanner(String app) {
    return 'Alleen-lezen. Antwoord Omi in $app.';
  }

  @override
  String get connected => 'Verbonden';

  @override
  String get shareStatsMessage => 'Ik deel mijn Omi-statistieken! (omi.me - je altijd-aan AI-assistent)';

  @override
  String get frequencyMinimal => 'Minimaal';

  @override
  String get addAppSelectLogo => 'Selecteer een logo voor uw app';

  @override
  String get integrationInstructions => 'Integratie-instructies';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'Toegankelijkheidstoestemmingsstatus: $status. Controleer Systeemvoorkeuren.';
  }

  @override
  String get wrappedCompleted => 'voltooid';

  @override
  String get remaining => 'Resterend';

  @override
  String get onDeviceIntensive => 'On-device transcriptie is rekenintensief.';

  @override
  String get diagnosticsVerdictTrouble => 'Problemen met verbinden';

  @override
  String deviceOnboardingVoiceReplyPreviewThroughDevice(String device) {
    return 'Via $device';
  }

  @override
  String get copyConfig => 'Configuratie kopiëren';

  @override
  String accessesDataTypes(String dataTypes) {
    return 'Toegang tot $dataTypes';
  }

  @override
  String get chatAppsWaitlistConfirmed => 'Bedankt. WhatsApp verschijnt hier zodra het klaar is.';

  @override
  String get undo => 'Ongedaan maken';

  @override
  String get phoneContactsAccessTitle => 'Toegang tot contacten toestaan';

  @override
  String confidenceIsConfirmed(String name) {
    return '$name is bevestigd. Je hoeft verder niets te doen.';
  }

  @override
  String get wrappedMovie => 'FILM';

  @override
  String get wrappedStruggleLabelUpper => 'STRIJD';

  @override
  String get appleHealthFeatureChatDesc => 'Vraag Omi over je stappen, slaap, hartslag en workouts.';

  @override
  String get writeReviewOptional => 'Schrijf een recensie (optioneel)';

  @override
  String get pairNewDevice => 'Nieuw apparaat koppelen';

  @override
  String chatUsedOfLimitCompute(String used, String limit) {
    return '$used van $limit rekenbudget gebruikt';
  }

  @override
  String get dailySummary => 'Dagelijkse samenvatting';

  @override
  String get pleaseEnterYourName => 'Voer uw naam in';

  @override
  String get continueWithoutDevice => 'Doorgaan zonder apparaat';

  @override
  String get configure => 'Configureren';

  @override
  String get createApp => 'App maken';

  @override
  String get invalidUrlError => 'Voer een geldige URL in';

  @override
  String get appClosed => 'App gesloten';

  @override
  String get downgradeToFreemiumAction => 'Overstappen naar de gratis versie';

  @override
  String get chatAppsUseTelegramForNow => 'Gebruik voorlopig Telegram';

  @override
  String get wrappedBestMomentsBadge => 'Beste momenten';

  @override
  String get storageSection => 'Opslag';

  @override
  String get pauseResumeRecording => 'Opname pauzeren/hervatten';

  @override
  String get phoneUnmute => 'Demping opheffen';

  @override
  String get youreAllSet => 'Je bent klaar!';

  @override
  String get migrationComplete => 'Migratie voltooid!';

  @override
  String get paymentAppCost => 'App-kosten';

  @override
  String get deviceOnboardingFinish => 'Voltooien';

  @override
  String get noVerifiedNumbers => 'Geen geverifieerde nummers';

  @override
  String get connectAiAssistantsToData => 'Verbind AI-assistenten met je gegevens';

  @override
  String get keyNameHint => 'bijv. Claude Desktop';

  @override
  String get paymentMethods => 'Betaalmethoden';

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'Kan toegankelijkheidstoestemming niet controleren: $error';
  }

  @override
  String get confidenceReasonAutoOnly => 'Automatisch gelabeld, nog niet bevestigd';

  @override
  String whatsNewInVersion(String version) {
    return 'Nieuw in $version';
  }

  @override
  String get selectYourLanguage => 'Selecteer je taal';

  @override
  String get memoryClearedSuccess => 'Omi\'s geheugen over jou is gewist';

  @override
  String get memoryContentHint => 'Ik heb liever vergaderingen in de ochtend.';

  @override
  String get dreamReportTitle => 'Dream-rapport';

  @override
  String importErrorGeneric(String error) {
    return 'Fout: $error';
  }

  @override
  String get completionRate => 'Voltooiingspercentage';

  @override
  String get trackPersonalGoals => 'Persoonlijke doelen volgen op de homepage';

  @override
  String get wrappedTryAgain => 'Opnieuw proberen';

  @override
  String get dataProtection => 'Gegevensbescherming';

  @override
  String get yourConversations => 'Je gesprekken';

  @override
  String pdfTitleLabel(String title) {
    return 'Titel: $title';
  }

  @override
  String get sendRawAudioToOmiDescription =>
      'Schakel uit om te voorkomen dat onbewerkte audio naar Omi wordt gestuurd. Transcripties en gegevens die cloudfuncties nodig hebben, kunnen nog steeds naar Omi worden gestuurd.';

  @override
  String get entityLoadFailed => 'Deze pagina kon niet worden geladen.';

  @override
  String get networkNameSsid => 'Netwerknaam (SSID)';

  @override
  String get discovery => 'Ontdekking';

  @override
  String get rayBanMetaMicPickerConnectError =>
      'Kan geen verbinding maken met die microfoon. Controleer of deze verbonden is in de iPhone-instellingen.';

  @override
  String get fairUseAboutTitle => 'Over redelijk gebruik';

  @override
  String get wrappedYouTalkedAbout => 'Je sprak over';

  @override
  String get downgradeLimitQuality => '30% lagere transcriptiekwaliteit';

  @override
  String get sharedTasksUnknownSender => 'Iemand';

  @override
  String get selectAReason => 'Kies een reden';

  @override
  String get wrappedWinLabel => 'OVERWINNING';

  @override
  String get configuration => 'Configuratie';

  @override
  String get noFolder => 'Geen map';

  @override
  String get manifestRefreshedSuccess => 'Manifest succesvol vernieuwd';

  @override
  String get paymentStatusActive => 'Actief';

  @override
  String get linkKeyMismatch => 'Koppelingssleutel komt niet overeen';

  @override
  String speakerTagPromptProgress(int current, int total) {
    return '$current van $total';
  }

  @override
  String get updateRequiredMessage =>
      'Deze versie van Omi wordt niet meer ondersteund. Update om te blijven opnemen en synchroniseren.';

  @override
  String get sharePeriodMonth => 'Deze maand heeft Omi:';

  @override
  String get rollbackToStableFirmware => 'Terugkeren naar stabiele firmware';

  @override
  String get paymentStatusConnected => 'Verbonden';

  @override
  String get findDeviceNoneTitle => 'Geen Omi gevonden';

  @override
  String get appIdCopiedToClipboard => 'App-ID gekopieerd naar klembord';

  @override
  String get bySubmittingYouAgreeToOmi => 'Door in te dienen, gaat u akkoord met Omi ';

  @override
  String get filterRating => 'Beoordeling';

  @override
  String get usageAtWork => 'Op het werk';

  @override
  String get tasksCleanTodayMessage => 'Hiermee worden alleen deadlines verwijderd';

  @override
  String get ignoredVoicesSubtitle => 'Tv, podcasts en andere stemmen die je hebt gemarkeerd als “Geen persoon”';

  @override
  String get permissionEnable => 'Inschakelen';

  @override
  String integrationComingSoon(String appName) {
    return '$appName wordt nog niet ondersteund.';
  }

  @override
  String get sttModelLower => 'Lager';

  @override
  String get loadingYourMemories => 'Je herinneringen laden…';

  @override
  String get followUpQuestions => 'Vervolgvragen';

  @override
  String get previousDay => 'Vorige dag';

  @override
  String fairUseCaseRefCopied(String caseRef) {
    return '$caseRef gekopieerd';
  }

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get recordingPaused => 'Opname gepauzeerd';

  @override
  String get cannotReportOwnMessages => 'U kunt uw eigen berichten niet melden';

  @override
  String get enterWordsHint => 'Voer woorden in (kommagescheiden)';

  @override
  String get audioDownloadFailed => 'Audio downloaden mislukt';

  @override
  String get clearMemoryMessage => 'Al je herinneringen worden verwijderd. Dit kan niet ongedaan worden gemaakt.';

  @override
  String get templateNameHint => 'bijv. Vergadertaken-extractor';

  @override
  String speakerLabelTalkTime(String duration) {
    return '$duration van deze stem';
  }

  @override
  String get recordingMode => 'Opnamemodus';

  @override
  String get cancelReasonOther => 'Anders';

  @override
  String get sttModelHigher => 'Hoger';

  @override
  String get settingUpSystemAudioCapture => 'Systeemaudio-opname instellen';

  @override
  String memoriesCount(int count) {
    return '$count herinneringen';
  }

  @override
  String get noSpecificDataAccessConfigured => 'Geen specifieke gegevenstoegang geconfigureerd.';

  @override
  String get recordingIdLabel => 'Opname-ID';

  @override
  String get highlights => 'Hoogtepunten';

  @override
  String get phoneTryAgain => 'Opnieuw proberen';

  @override
  String chatAppsCouldNotOpen(String app) {
    return 'Kan $app niet openen. Controleer of de app is geïnstalleerd en probeer het opnieuw.';
  }

  @override
  String get onDeviceTranscriptionDesc => 'Transcriptie wordt lokaal op je apparaat verwerkt';

  @override
  String get chatAppsTryPromise => 'Wat heb ik gisteren aan Sam beloofd?';

  @override
  String get paymentStatusNotConnected => 'Niet verbonden';

  @override
  String get intervalSeconds => 'Interval (seconden)';

  @override
  String get authorize => 'Autoriseren';

  @override
  String get settingsHeader => 'INSTELLINGEN';

  @override
  String get personNameAlreadyExists => 'Er bestaat al een persoon met deze naam.';

  @override
  String get deviceOnboardingVoiceReplyPreviewThroughCurrentOutput => 'Via de huidige audio-uitvoer';

  @override
  String get monthJun => 'Jun';

  @override
  String selectedCount(int count) {
    return '$count geselecteerd';
  }

  @override
  String get batteryHistory => 'Batterij';

  @override
  String get noPastChats => 'Je chats met Omi verschijnen hier.';

  @override
  String get chatAppsDoesSave => 'Bewaart herinneringen en beheert je taken';

  @override
  String get apiKey => 'API-sleutel';

  @override
  String get authFailedToLinkGoogle => 'Koppelen met Google mislukt, probeer het opnieuw.';

  @override
  String audioUploadFailedKeptLocal(String duration) {
    return 'Uploaden mislukt — $duration audio bewaard op je telefoon.';
  }

  @override
  String get free => 'Gratis';

  @override
  String get deselectAllTasksMenu => 'Alles deselecteren';

  @override
  String get dreamReportLoadFailed => 'Het Dream-rapport kon niet worden geladen.';

  @override
  String get entityRecentConversations => 'Recente gesprekken';

  @override
  String get pendantRecordingNote =>
      'Je hanger neemt zelfstandig op. Opnames worden met je telefoon gesynchroniseerd zolang de app open staat.';

  @override
  String get manageStorage => 'Opslag beheren';

  @override
  String get filterSystem => 'Over jou';

  @override
  String get deleteConsequenceSubscription => 'Een actief abonnement wordt geannuleerd.';

  @override
  String get defaultList => 'Standaardlijst';

  @override
  String get shared => 'Gedeeld';

  @override
  String get customVocabulary => 'Aangepaste Woordenschat';

  @override
  String get feedbackTitleAudioQuality => 'Welke problemen heb je ervaren?';

  @override
  String get thisActionCannotBeUndone => 'Dit kan niet ongedaan worden gemaakt.';

  @override
  String errorRequestingPermission(String error) {
    return 'Fout bij het vragen van toestemming: $error';
  }

  @override
  String get recapRegenerateFailed => 'Kon de samenvatting niet opnieuw genereren. Probeer het later opnieuw.';

  @override
  String get result => 'Resultaat:';

  @override
  String get statusCallMissed => 'Gemist gesprek';

  @override
  String get diagnosticsLongestGap => 'Langste onderbreking';

  @override
  String get noLogFilesFound => 'Geen logbestanden gevonden.';

  @override
  String get speechTranscriptionSectionTitle => 'Spraak & transcriptie';

  @override
  String get syncNow => 'Nu synchroniseren';

  @override
  String get sttUsePrimaryLanguage => 'Primaire taal gebruiken';

  @override
  String get importUnsupportedFileType => 'Dit bestandstype kan niet worden geïmporteerd.';

  @override
  String get chatSendMessage => 'Bericht versturen';

  @override
  String get syncCardAllBackedUp => 'Alle opnames gesynchroniseerd';

  @override
  String get settings => 'Instellingen';

  @override
  String get backgroundLocationDeniedDesc =>
      'Ga naar apparaatinstellingen en stel locatiemachtiging in op \"Altijd toestaan\"';

  @override
  String get computationallyIntensive => 'On-device transcriptie is rekenintensief.';

  @override
  String get and => ' en ';

  @override
  String get yourVerifiedNumbers => 'Uw geverifieerde nummers';

  @override
  String get tasksCleanTodayTitle => 'Taken van vandaag opschonen?';

  @override
  String get microphonePermission => 'Microfoontoestemming';

  @override
  String get failedToUpdateConversationTitle => 'Kan gesprekstitel niet bijwerken';

  @override
  String get appsDisconnected => 'Je apps en integraties worden losgekoppeld.';

  @override
  String get live => 'Live';

  @override
  String get connectionFailed => 'Verbinding mislukt';

  @override
  String get selectImages => 'Selecteer afbeeldingen';

  @override
  String get playbackAudioNetworkFailed => 'Controleer verbinding';

  @override
  String get paypalEmail => 'PayPal-e-mail';

  @override
  String get chatAppsOnTheList => 'Op de lijst';

  @override
  String get generateSummary => 'Samenvatting genereren';

  @override
  String get categoryHealth => 'Gezondheid';

  @override
  String get transcribeLaterStorageFull =>
      'Je telefoon heeft weinig opslagruimte, dus de opname is gepauzeerd. Maak ruimte vrij of upload je opnames, dan gaat het automatisch verder.';

  @override
  String get chatAppsNoChatsTitle => 'Nog geen chats';

  @override
  String get onboardingSetupStepPersonalize => 'Je ervaring wordt gepersonaliseerd';

  @override
  String get leaveUnselectedTasks => 'Laat niet geselecteerd om taken zonder project aan te maken';

  @override
  String get wrappedButYouPushedThroughEmoji => 'Maar je hebt het gered 💪';

  @override
  String get needHelp => 'Hulp nodig?';

  @override
  String get confirmAndCancel => 'Bevestigen en annuleren';

  @override
  String get frequencyDescHigh => 'Meer suggesties, ongeveer 6–9 per dag';

  @override
  String get copyLink => 'Link kopiëren';

  @override
  String get dreamReportLiveBanner => 'Dream past deze wijzigingen zelf toe. Maak ze ongedaan in Recente wijzigingen.';

  @override
  String get enterActionItemDescription => 'Voer taakbeschrijving in';

  @override
  String chatAppsInChannel(String app) {
    return 'In $app';
  }

  @override
  String get links => 'Links';

  @override
  String get dreamReportEmptyTitle => 'Nog geen rondes';

  @override
  String get monthJan => 'Jan';

  @override
  String get wrappedMostProductiveDay => 'Meest productief';

  @override
  String get productUpdate => 'Productupdate';

  @override
  String get addYourReview => 'Voeg uw beoordeling toe';

  @override
  String get raybanMetaImageCaptureReady => 'Beeldopname gereed';

  @override
  String get displayUpcomingMeetingsDescription => 'Aankomende vergaderingen weergeven in menubalk';

  @override
  String get whatWeCollect => 'Wat we verzamelen';

  @override
  String get connectPayPalToReceivePayments => 'Verbind uw PayPal-account om betalingen voor uw apps te ontvangen';

  @override
  String get justAMoment => 'Een moment, alsjeblieft';

  @override
  String get chatReplyServerError => 'Er is iets misgegaan aan onze kant. Probeer het opnieuw.';

  @override
  String get transferInProgress => 'Overdracht bezig…';

  @override
  String get usageAll => 'Altijd';

  @override
  String get failedToLoadContacts => 'Kan contacten niet laden';

  @override
  String appUsersCount(int count) {
    return '$count+ gebruikers';
  }

  @override
  String get report => 'Melden';

  @override
  String get languageLabel => 'Taal';

  @override
  String verifiedOnDate(String date) {
    return 'Geverifieerd op $date';
  }

  @override
  String get customVocabularyHeader => 'AANGEPASTE WOORDENSCHAT';

  @override
  String otaRebooting(String deviceName) {
    return '$deviceName start opnieuw op met de nieuwe firmware.';
  }

  @override
  String get mcpServer => 'MCP-server';

  @override
  String get findDevice => 'Zoeken';

  @override
  String get msgUploadAttachedFileFailed => 'Uploaden van bijgevoegd bestand mislukt.';

  @override
  String get appName => 'App Name';

  @override
  String get pairingTitlePlaudNote => 'Zet Plaud Note in koppelingsmodus';

  @override
  String get moreOptions => 'Meer opties';

  @override
  String get noConversationsHeroMessage =>
      'Gesprekken die je opneemt verschijnen hier. Tik op Home op de opnameknop om je eerste op te nemen.';

  @override
  String get finish => 'Afronden';

  @override
  String get goBack => 'Terug';

  @override
  String get apiKeysDescription =>
      'API-sleutels worden gebruikt voor authenticatie wanneer uw app communiceert met de Omi-server. Ze stellen uw applicatie in staat om herinneringen te maken en veilig toegang te krijgen tot andere Omi-services.';

  @override
  String get sttProviderSpeechmatics => 'Speechmatics';

  @override
  String get setWebhookUrlInSettings =>
      'Stel de webhook URL in bij ontwikkelaarsinstellingen om deze functie te gebruiken.';

  @override
  String get dailyScoreBreakdown => 'Dagelijkse score overzicht';

  @override
  String get showMeetingsMenuBarDesc => 'Toon je volgende vergadering en tijd tot deze begint in de macOS-menubalk';

  @override
  String get tapToTrackThisGoal => 'Tik om dit doel te volgen';

  @override
  String get summarizingConversation => 'Gesprek samenvatten…\nDit kan enkele seconden duren';

  @override
  String get noInternetConnection => 'Geen internetverbinding';

  @override
  String diagnosticsCountSincePairing(int count) {
    return '$count sinds koppeling';
  }

  @override
  String get wrappedTasksCreated => 'aangemaakte taken';

  @override
  String get deleteConsequenceNoRecovery => 'Je account kan niet worden hersteld — zelfs niet door support.';

  @override
  String get waitForReprocessing => 'Wacht tot het opnieuw verwerken klaar is.';

  @override
  String get needYourPermission => 'We hebben je toestemming nodig';

  @override
  String get downgradeLimitSpeakers => 'Kan sprekers niet herkennen';

  @override
  String conversationsTodayCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count gesprekken vandaag.',
      one: '1 gesprek vandaag.',
      zero: 'Vandaag geen gesprekken.',
    );
    return '$_temp0';
  }

  @override
  String get dailyScore => 'DAGELIJKSE SCORE';

  @override
  String get reportAnIssue => 'Een probleem melden';

  @override
  String get invalidKey => 'Ongeldige toets';

  @override
  String get preview => 'Voorbeeld';

  @override
  String get nextWeek => 'Volgende week';

  @override
  String get confidenceUnverified => 'Niet geverifieerd';

  @override
  String get previewScreenshots => 'Voorbeeld schermafbeeldingen';

  @override
  String get ledBrightness => 'LED-helderheid';

  @override
  String get firmwareUpdateFailedMessage =>
      'De update is niet voltooid. Je apparaat draait nog op de huidige firmware en is veilig te gebruiken. Houd het opgeladen en dicht bij je telefoon en probeer het opnieuw.';

  @override
  String get loadingProfile => 'Profiel laden…';

  @override
  String get deleteRecapConfirmTitle => 'Deze samenvatting verwijderen?';

  @override
  String get notificationFrequency => 'Meldingsfrequentie';

  @override
  String get captureSystemAudioFromMeetings => 'Systeemaudio van vergaderingen vastleggen';

  @override
  String get storeAudioCloudDescription => 'Uploadt je opnames terwijl je spreekt, zodat je ze later kunt afspelen.';

  @override
  String get color => 'Kleur';

  @override
  String get open => 'Openen';

  @override
  String get diagnosticsVerdictNoDrops => 'Geen onderbrekingen deze week';

  @override
  String get autoExtractionFeature => 'Automatisch geëxtraheerd uit gesprekken';

  @override
  String get searchResults => 'Zoekresultaten';

  @override
  String get v2UndetectedMessage =>
      'We zien dat je een V1-apparaat hebt of je apparaat is niet verbonden. SD-kaartfunctionaliteit is alleen beschikbaar voor V2-apparaten.';

  @override
  String get endAndProcess => 'Gesprek beëindigen en verwerken';

  @override
  String get noSyncedRecordings => 'Nog geen gesynchroniseerde opnames';

  @override
  String get coworker => 'Collega';

  @override
  String get setupQuestionUsage => '2. Waar ben je van plan je Omi te gebruiken?';

  @override
  String get pinnedNotSelectable => 'Vastgezet, niet te selecteren';

  @override
  String get showMore => 'toon meer ↓';

  @override
  String get createYourFirstMemory => 'Maak je eerste herinnering om te beginnen';

  @override
  String get discardedConversation => 'Verwijderd gesprek';

  @override
  String get enableApps => 'Apps inschakelen';

  @override
  String get today => 'Vandaag';

  @override
  String get showEventsNoParticipantsDesc =>
      'Wanneer ingeschakeld, toont Binnenkort evenementen zonder deelnemers of videolink.';

  @override
  String get couldNotLoadPage =>
      'Deze pagina kon niet worden geladen. Controleer je verbinding en probeer het opnieuw.';

  @override
  String actionItemDeletedResult(String description) {
    return 'Taak \"$description\" verwijderd';
  }

  @override
  String get deleteSampleQuestion => 'Voorbeeld verwijderen?';

  @override
  String get youAreOnAPaidPlan => 'Je hebt een betaald abonnement.';

  @override
  String get otaInstallFailed => 'Installatie mislukt. Je apparaat draait nog op de huidige firmware.';

  @override
  String get addFirstMemory => 'Voeg je eerste herinnering toe';

  @override
  String get appDeletedSuccessfully => 'App succesvol verwijderd';

  @override
  String get chatAppsConnectTelegramMessage => 'Omi opent Telegram met een privélink die alleen voor jou is.';

  @override
  String get phoneSetupStep1Title => 'Verifieer uw telefoonnummer';

  @override
  String get deviceRequirements => 'Je apparaat voldoet niet aan de vereisten voor on-device transcriptie.';

  @override
  String get confidenceEvidenceHeader => 'Bewijs';

  @override
  String get pleaseEnterAName => 'Voer een naam in.';

  @override
  String get deleteConfirmationWord => 'DELETE';

  @override
  String get speakerTagPromptThatsMe => 'Dat ben ik';

  @override
  String get ourCommitment => 'Onze toezegging';

  @override
  String get notificationScopes => 'Meldingsbereiken';

  @override
  String get autoDeletesAfter3Days => 'Wordt automatisch verwijderd na 3 dagen';

  @override
  String get initialisingRecorder => 'Recorder initialiseren';

  @override
  String get privateAndSecureOnDevice => 'Opgeslagen op deze telefoon';

  @override
  String get allObjectsMigratedFinalizing => 'Alle objecten gemigreerd. Afronden…';

  @override
  String get chatAppsOpenMessages => 'Open Berichten';

  @override
  String get upgradeToPro => 'Upgraden naar Pro';

  @override
  String get clientId => 'Client-ID';

  @override
  String get backgroundActivity => 'Achtergrondactiviteit';

  @override
  String get noSummaryAvailable => 'Geen samenvatting beschikbaar';

  @override
  String get failedToUpdateStarred => 'Kan favorietenstatus niet bijwerken.';

  @override
  String get omiYourAiCompanion => 'Omi – Je AI-metgezel';

  @override
  String get pleaseSelectReason => 'Selecteer een reden';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Alle $count herinneringen worden verwijderd. Dit kan niet ongedaan worden gemaakt.';
  }

  @override
  String get connectNow => 'Nu verbinden';

  @override
  String chatAppsDisconnectTitle(String app) {
    return '$app ontkoppelen?';
  }

  @override
  String get clearCredentials => 'Inloggegevens wissen';

  @override
  String get grantContactsPermissionForSms => 'Geef contactentoestemming om via SMS te delen';

  @override
  String get cloudTranscription => 'Cloud transcriptie';

  @override
  String get memoryHistory => 'Geschiedenis';

  @override
  String get speechSamples => 'Spraakvoorbeelden';

  @override
  String get wrappedBiggest => 'Grootste';

  @override
  String get reviewShowMore => 'Meer tonen';

  @override
  String get triggersWhenDaySummaryGenerated => 'Wordt geactiveerd wanneer de dagsamenvatting wordt gegenereerd.';

  @override
  String get thankYouFeedback => 'Bedankt voor je feedback!';

  @override
  String get allow => 'Toestaan';

  @override
  String triggeredByType(String triggerType) {
    return 'getriggerd door $triggerType';
  }

  @override
  String get howToPair => 'Zo koppel je';

  @override
  String get conversationDeveloperTools => 'Ontwikkelaarstools in gesprekken';

  @override
  String get memoryProvenanceIphone => 'iPhone';

  @override
  String get aboutYou => 'Over jou';

  @override
  String get memoryProvenanceMac => 'Mac';

  @override
  String get effectCounts => 'Helpt';

  @override
  String get tagSpeakerIncludingLaterSpeech => 'Ook latere spraak van deze spreker taggen';

  @override
  String get storeAudioOnPhone => 'Audio opslaan op telefoon';

  @override
  String get developerApiKeys => 'Ontwikkelaar API-sleutels';

  @override
  String get wrappedMyBuddiesCard => 'Mijn vrienden';

  @override
  String get bulkExportAlreadyExported => 'Alle geselecteerde taken zijn al geëxporteerd';

  @override
  String get popularBadge => 'POPULAIR';

  @override
  String get enableLocationTitle => 'Locatie inschakelen';

  @override
  String get feedbackBug => 'Feedback / Fout';

  @override
  String get good => 'Goed';

  @override
  String get upgradeYourPlan => 'Upgrade je abonnement';

  @override
  String get exportingAllData =>
      'Je gegevens worden geëxporteerd… Houd Omi open; grote accounts kunnen enkele minuten duren.';

  @override
  String get switchAndRestart => 'Wisselen';

  @override
  String get noReposFound => 'Geen repositories gevonden';

  @override
  String get latest => 'Nieuwste';

  @override
  String get failedToRevoke => 'Autorisatie intrekken mislukt. Probeer het opnieuw.';

  @override
  String get appleHealthDisconnectCta => 'Apple Health loskoppelen';

  @override
  String get chatAppsPrivateMemoriesSubtitle =>
      'Gezondheid, geld en alles wat je als privé hebt gemarkeerd, blijft buiten chat-apps.';

  @override
  String get deleteFlowFeedbackTitle => 'Vertel ons meer';

  @override
  String get failedToConnectTodoistRetry => 'Verbinding met Todoist mislukt. Probeer het opnieuw.';

  @override
  String get capturePhoneStorageFull => 'Telefoonopslag vol';

  @override
  String deletePeopleTitle(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count personen verwijderen?',
      one: '1 persoon verwijderen?',
    );
    return '$_temp0';
  }

  @override
  String get cleanUpNothingMessage => 'Omi is op dit moment over niemand onzeker.';

  @override
  String get writeAReviewOptional => 'Schrijf een beoordeling (optioneel)';

  @override
  String get syncFailed => 'Synchronisatie mislukt';

  @override
  String get audioShareFailed => 'Delen mislukt';

  @override
  String loadMoreRemaining(String count) {
    return 'Meer laden ($count over)';
  }

  @override
  String get phoneDeleteNumberFailed => 'Dit nummer kon niet worden verwijderd';

  @override
  String deviceUsesCodec(String device, String reason) {
    return '$device neemt op in een formaat dat deze provider niet kan lezen ($reason), dus wordt in plaats daarvan de transcriptie van Omi gebruikt.';
  }

  @override
  String get chatAppsConnectIMessageMessage =>
      'Stuur Omi één bericht vanaf het nummer dat je wilt gebruiken. De code erin koppelt dat nummer aan je account.';

  @override
  String get speechToTextUnavailableDesc =>
      'Spraak naar tekst is momenteel niet beschikbaar. Controleer je internetverbinding en de instellingen voor spraakherkenning op je apparaat en probeer het opnieuw.';

  @override
  String get chatReplyTimeout => 'De reactie duurde te lang. Probeer het opnieuw.';

  @override
  String get passwordMinLengthError => 'Wachtwoord moet minimaal 8 tekens zijn';

  @override
  String get chatAppsWhatsAppMessage =>
      'We werken eraan om Omi naar WhatsApp te brengen. Het verschijnt hier zodra het klaar is.';

  @override
  String get deleteAccountCheckbox =>
      'Ik begrijp dat het verwijderen van mijn account permanent is en alle gegevens, inclusief herinneringen en gesprekken, verloren gaan en niet kunnen worden hersteld.';

  @override
  String get firmwareConnectWifi => 'Verbind met WiFi of mobiel netwerk.';

  @override
  String get forgetDeviceConfirmMessage => 'Omi maakt geen verbinding meer met dit apparaat.';

  @override
  String get editSwipeFeature => 'Tik om te bewerken, veeg om te voltooien of te verwijderen';

  @override
  String get memoryManagement => 'Geheugenbeheer';

  @override
  String get transcriptLoadFailed => 'Kan het transcript niet laden.';

  @override
  String get diagnosticsExportTitle => 'Omi-apparaatdiagnostiek';

  @override
  String get updateOmiFirmware => 'Omi-firmware bijwerken';

  @override
  String get importTooManyAttempts => 'Te veel imports op dit moment. Probeer het later opnieuw.';

  @override
  String get noAppsFound => 'Geen apps gevonden';

  @override
  String get phoneSetupStep1Subtitle => 'We bellen u ter bevestiging';

  @override
  String get deleteSyncedFiles => 'Gesynchroniseerde opnames verwijderen';

  @override
  String speakerLabelVoiceStatus(String state) {
    String _temp0 = intl.Intl.selectLogic(
      state,
      {
        'learned': 'Stem geleerd',
        'pending': 'Stem leren…',
        'disabled': 'Stem opslaan staat uit',
        'other': 'Stem nog niet geleerd',
      },
    );
    return '$_temp0';
  }

  @override
  String get recordingsMayCaptureOthers =>
      'Opnames kunnen de stemmen van anderen vastleggen. Zorg ervoor dat u toestemming hebt van alle deelnemers voordat u inschakelt.';

  @override
  String get helpful => 'Nuttig';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return '$model downloaden: $received / $total MB';
  }

  @override
  String get permissions => 'Machtigingen';

  @override
  String get audioDownloadSuccess => 'Audio succesvol gedownload';

  @override
  String get confirmPlanChange => 'Planwijziging bevestigen';

  @override
  String get wrappedThatAwkwardMoment => 'Dat ongemakkelijke moment';

  @override
  String get calendarProviders => 'Agenda-providers';

  @override
  String evidenceAutoUnconfirmed(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count automatische labels nog niet bevestigd',
      one: '1 automatisch label nog niet bevestigd',
    );
    return '$_temp0';
  }

  @override
  String get importData => 'Gegevens importeren';

  @override
  String get weekdayMon => 'Ma';

  @override
  String get deviceStorageTitle => 'Apparaatopslag';

  @override
  String get externalAppAccess => 'Externe app-toegang';

  @override
  String get transcriptionUnavailable => 'Transcriptie niet beschikbaar';

  @override
  String get termsAndPrivacyPolicy => 'Voorwaarden en Privacybeleid';

  @override
  String get noImportsYet => 'Nog geen imports';

  @override
  String get openOmiOnAppleWatchDescription =>
      'De Omi-app is geïnstalleerd op je Apple Watch. Open deze en tik op Start om te beginnen.';

  @override
  String dreamReportFailed(String error) {
    return 'Mislukt ($error)';
  }

  @override
  String get sendSummary => 'Verstuur samenvatting';

  @override
  String get filterAll => 'Alle';

  @override
  String get deleteChatMessage => 'Hij verdwijnt voorgoed uit eerdere chats.';

  @override
  String get timeout10Minutes => '10 minuten';

  @override
  String get noCalendarEventsNearby => 'Geen agenda-afspraken gevonden rond dit tijdstip.';

  @override
  String get cancelSyncQuestion => 'Synchronisatie annuleren?';

  @override
  String get whatShouldWeMake => 'Wat zullen we maken?';

  @override
  String get usageListened => 'Listened';

  @override
  String get errorUpdatingStripeDetails => 'Fout bij het bijwerken van Stripe-gegevens! Probeer het later opnieuw.';

  @override
  String get conversationEndAfterHours => 'Gesprekken eindigen nu na 4 uur stilte';

  @override
  String get issueActivatingApp => 'Er is een probleem opgetreden bij het activeren van deze app. Probeer het opnieuw.';

  @override
  String get appCreatedSuccessfully => 'App succesvol gemaakt!';

  @override
  String get categoryNews => 'Nieuws';

  @override
  String get phoneSearchHint => 'Zoeken';

  @override
  String peoplePinnedCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count vastgezet',
      one: '1 vastgezet',
    );
    return '$_temp0';
  }

  @override
  String get wrappedHours => 'uren';

  @override
  String get phoneKeypad => 'Toetsenbord';

  @override
  String get peopleFilterLowConfidence => 'Lage zekerheid';

  @override
  String get agreeToContributeData => 'Ik begrijp en ga akkoord met het bijdragen van mijn gegevens voor AI-training';

  @override
  String get addGoal => 'Doel toevoegen';

  @override
  String get dreamReportRunInProgress => 'Er loopt al een ronde. Probeer het over een minuut opnieuw.';

  @override
  String importedConfig(String providerName) {
    return '$providerName-configuratie geïmporteerd';
  }

  @override
  String monthsAgo(int count) {
    return '$count maanden geleden';
  }

  @override
  String get downgradeLimitationsHeading => 'Je krijgt te maken met deze beperkingen:';

  @override
  String get chatRemoveSelectedText => 'Geciteerde tekst verwijderen';

  @override
  String get firmwareBatteryAbove15 => 'Batterij boven 15%';

  @override
  String reviewQuestionSamePerson(String name) {
    return 'Dezelfde persoon als “$name”?';
  }

  @override
  String get effectCountsALot => 'Helpt veel';

  @override
  String get sdCard => 'SD-kaart';

  @override
  String get openInGoogleCalendar => 'Openen in Google Agenda';

  @override
  String get appleHealthFeatureSecureTitle => 'Veilige synchronisatie';

  @override
  String get conversationDeveloperToolsDescription =>
      'Toon Gesprek-ID kopiëren en Prompt testen in het menu van een gesprek';

  @override
  String get host => 'Host';

  @override
  String get deleteReasonMissingFeatures => 'Functies die ik nodig heb ontbreken';

  @override
  String get syncingInProgress => 'Synchronisatie bezig';

  @override
  String get tabDone => 'Klaar';

  @override
  String get revoke => 'Intrekken';

  @override
  String get mcp => 'MCP';

  @override
  String get anyoneCanDiscoverTemplate => 'Iedereen kan uw sjabloon ontdekken';

  @override
  String get mcpDescription =>
      'Om Omi te verbinden met andere applicaties om uw herinneringen en gesprekken te lezen, te zoeken en te beheren. Maak een sleutel om te beginnen.';

  @override
  String get connectionLostDescription =>
      'De verbinding werd onderbroken. Controleer je internetverbinding en probeer het opnieuw.';

  @override
  String chatAppsNoChatsMessage(String app) {
    return 'Chats die je met Omi hebt in $app verschijnen hier.';
  }

  @override
  String get storedLocallyNeverShared => 'Opgeslagen op deze telefoon. Alleen verzonden naar je transcriptieprovider.';

  @override
  String get morePaymentMethodsComingSoon => 'Meer betaalmethoden binnenkort';

  @override
  String get allCaughtUp => 'Alles is bijgewerkt';

  @override
  String previewImageLabel(int index, int total) {
    return 'Screenshot $index van $total';
  }

  @override
  String get disable => 'Uitschakelen';

  @override
  String get recordings => 'Opnames';

  @override
  String get enterPersonsName => 'Voer naam van persoon in';

  @override
  String get newConversationCreated => 'Nieuw gesprek aangemaakt';

  @override
  String resetsInDays(int count) {
    return 'Reset over $count dagen';
  }

  @override
  String get confidenceConfirmed => 'Bevestigd';

  @override
  String get bulkExportInProgress => 'Exporteren…';

  @override
  String get detectLanguages => 'Detecteer 10+ talen';

  @override
  String get phoneSpeaker => 'Luidspreker';

  @override
  String get visitWebsite => 'Bezoek website';

  @override
  String get howToTakeGoodSample => 'Hoe maak je een goed voorbeeld?';

  @override
  String get clearChat => 'Chat wissen';

  @override
  String languageSetTo(String language) {
    return 'Taal ingesteld op $language';
  }

  @override
  String get deviceOnboardingVoiceReplyHeadphonesDescription =>
      'Privé. Spreekt alleen via AirPods, Bluetooth of bedrade hoofdtelefoons.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'Uw plan blijft actief tot $date. Daarna verliest u de toegang tot uw onbeperkte functies.';
  }

  @override
  String get clientSecret => 'Client-geheim';

  @override
  String get pairingTitleAppleWatch => 'Verbind Apple Watch';

  @override
  String get share => 'Delen';

  @override
  String get yourPrivacyYourControl => 'Jouw privacy, jouw controle';

  @override
  String get tapToCopy => 'Tik om te kopiëren';

  @override
  String get feedbackTitleFoundAlternative => 'Waarnaar stap je over?';

  @override
  String get all => 'Alles';

  @override
  String get filterCapabilities => 'Functies';

  @override
  String get tagOtherSegments => 'Andere segmenten taggen';

  @override
  String get entityDecisions => 'Besluiten';

  @override
  String get tasksCreatedInWorkspace => 'Taken worden aangemaakt in deze werkruimte';

  @override
  String get fairUseDailyTranscription => 'Daily Transcription';

  @override
  String get pausePlayback => 'Pauzeren';

  @override
  String get sharedTasksLinkExpired => 'Deze gedeelde taken zijn niet gevonden of de link is verlopen.';

  @override
  String get editConversationDialogTitle => 'Gesprek bewerken';

  @override
  String get deleteMemoryConfirmation => 'Deze herinnering verwijderen? Dit kan niet ongedaan worden gemaakt.';

  @override
  String get appUnderReviewMessage =>
      'Uw app wordt beoordeeld en is alleen voor u zichtbaar. Deze wordt openbaar na goedkeuring.';

  @override
  String get illDoItLater => 'Ik doe het later';

  @override
  String get captureStillRecording => 'Neemt nog op';

  @override
  String confidenceNextLabels(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Label ze in nog $count gesprekken.',
      one: 'Label ze in nog 1 gesprek.',
    );
    return '$_temp0';
  }

  @override
  String get speakerTagPromptAnswerFailed => 'Opslaan mislukt. Probeer het opnieuw.';

  @override
  String get feedbackReasonSummaryIncomplete => 'Onvolledig';

  @override
  String get errorActivatingApp => 'Fout bij activeren van de app';

  @override
  String get tasksCompleted => 'Taken voltooid';

  @override
  String onboardingStepOf(int current, int total) {
    return 'Stap $current van $total';
  }

  @override
  String get downgradeAnyway => 'Toch downgraden';

  @override
  String get leaveBlank => 'Leeg laten';

  @override
  String get chatAppsViewChats => 'Bekijk chats';

  @override
  String get captureScreenRecordingPermissionRequired => 'Schermopnametoestemming vereist';

  @override
  String get accountCutoverUpdateRequiredTitle => 'Update vereist';

  @override
  String weeksAgo(int count) {
    return '$count weken geleden';
  }

  @override
  String get phoneEndCall => 'Einde';

  @override
  String get startupFailedMessage =>
      'Er is iets misgegaan tijdens het opstarten van Omi. Controleer je verbinding en probeer het opnieuw.';

  @override
  String get permissionRevokedTitle => 'Toestemming ingetrokken';

  @override
  String get chatFeatures => 'Chat-functies';

  @override
  String get couldNotLoadMap => 'Kaart kon niet worden geladen';

  @override
  String get selectContactsToShare => 'Selecteer contacten om te delen';

  @override
  String get ok => 'OK';

  @override
  String get memoryReviewConfirmed => 'Bevestigd.';

  @override
  String get deleteKnowledgeGraph => 'Kennisgraaf verwijderen';

  @override
  String get reviewChangeFailed => 'Deze wijziging kon niet worden bijgewerkt. Probeer het opnieuw.';

  @override
  String get limitless => 'Limitless';

  @override
  String uploadingToCloud(int current, int total) {
    return '$current van $total uploaden';
  }

  @override
  String get dontSeeYourDevice => 'Zie je je apparaat niet?';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Je taken worden gesynchroniseerd met je $appName-account';
  }

  @override
  String appSettingsLabel(String appName) {
    return 'Instellingen van $appName';
  }

  @override
  String get chatBlockShowLess => 'Minder tonen';

  @override
  String get mindMap => 'Mind Map';

  @override
  String get authorizationBearer => 'Authorization: Bearer <sleutel>';

  @override
  String get dreamReportWouldSuggestTasks => 'Zou taken voorstellen';

  @override
  String get dreamReportWouldAsk => 'Zou je vragen';

  @override
  String get getFreeUnlimitedAccess => 'Krijg gratis onbeperkte toegang';

  @override
  String get yourDaysJourney => 'Uw dagreis';

  @override
  String get transcriptReceived => 'Transcript ontvangen';

  @override
  String get expand => 'Uitvouwen';

  @override
  String get onboardingCompleteMessage =>
      'Laat Omi een paar dagen draaien. Je gesprekken, herinneringen en to-do\'s komen dan vanzelf binnen.';

  @override
  String get trainFamilyProfiles => 'Train profielen voor vrienden en familie';

  @override
  String get selectText => 'Tekst selecteren';

  @override
  String get generatingDescription => 'Beschrijving genereren…';

  @override
  String get deviceOnboardingStarConversationDesc => 'Gesprek als belangrijk markeren';

  @override
  String disableAppNamed(String appName) {
    return '$appName uitschakelen';
  }

  @override
  String get deleteConversationConfirmation => 'Dit gesprek verwijderen? Dit kan niet ongedaan worden gemaakt.';

  @override
  String get contentCopied => 'Inhoud gekopieerd naar klembord';

  @override
  String get joinTheCommunity => 'Word lid van de community!';

  @override
  String get noContactsWithPhoneNumbers => 'Geen contacten met telefoonnummers gevonden';

  @override
  String get removeAttachment => 'Bijlage verwijderen';

  @override
  String get followTheVoiceInstructions => 'Volg de spraakinstructies';

  @override
  String get createYourOwnApp => 'Maak je eigen app';

  @override
  String get paymentDetails => 'Betalingsgegevens';

  @override
  String get tellOmiWhoSaidIt => 'Vertel Omi wie het zei 🗣️';

  @override
  String audioInputSetTo(String deviceName) {
    return 'Audio-ingang ingesteld op $deviceName';
  }

  @override
  String get pleaseEnterValidEmail => 'Voer een geldig e-mailadres in';

  @override
  String get thisYear => 'Dit jaar';

  @override
  String get noTranscriptMessage => 'Dit gesprek heeft geen transcript.';

  @override
  String get appearanceDark => 'Donker';

  @override
  String get createCustomTemplate => 'Aangepast sjabloon maken';

  @override
  String get monthMay => 'Mei';

  @override
  String get tasksAddedToList => 'Taken worden toegevoegd aan deze lijst';

  @override
  String isTriggeredBy(String triggerDescription) {
    return 'Wordt $triggerDescription geactiveerd.';
  }

  @override
  String get deleteConversationTitle => 'Gesprek verwijderen?';

  @override
  String get accountCutoverUpdateRequiredMessage =>
      'Installeer de nieuwste Omi-app om door te gaan na de accountmigratie.';

  @override
  String get txtFormat => 'TXT';

  @override
  String chatAppsDisconnectMessage(String app) {
    return 'Omi stopt met antwoorden in $app en verwijdert de chatgeschiedenis die het ervoor bewaart. Berichten die al in $app staan, blijven daar.';
  }

  @override
  String get captureWithCamera => 'Opnemen met camera';

  @override
  String get appIdLabel => 'App-ID';

  @override
  String get endpointUrl => 'Eindpunt-URL';

  @override
  String get actionItemUpdated => 'Taak bijgewerkt';

  @override
  String itemsSelected(int count) {
    return '$count geselecteerd';
  }

  @override
  String get onboardingWhatIKnowAboutYouDescription =>
      'Deze kaart wordt bijgewerkt naarmate Omi leert van je gesprekken.';

  @override
  String diagnosticsLastDuration(String duration) {
    return 'Laatste $duration';
  }

  @override
  String get pairingDescLimitless =>
      'Wanneer een lampje brandt, druk eenmaal en houd dan ingedrukt totdat het apparaat een roze licht toont, laat dan los.';

  @override
  String get chatBlockOpenConversation => 'Gesprek openen';

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '$used van $limit inzichten verkregen deze maand';
  }

  @override
  String get connectionErrorDesc =>
      'Kan geen verbinding maken met de server. Controleer je internetverbinding en probeer het opnieuw.';

  @override
  String get enterWordsCommaSeparated => 'Voer woorden in (gescheiden door komma)';

  @override
  String get otherDevicesComingSoon => 'Andere apparaten binnenkort';

  @override
  String speakerSuggestionChip(String name) {
    return '$name?';
  }

  @override
  String get speakerTagPromptNotAPersonToast => 'Gemarkeerd als geen persoon';

  @override
  String get createKeyToGetStarted => 'Maak een sleutel aan om te beginnen';

  @override
  String get captureRecordingSeparateConfirm => 'Scheiden';

  @override
  String get diagnosticsDrops => 'Onderbrekingen';

  @override
  String lowBatteryAlertBody(int level) {
    return 'Je batterij staat op $level%. Tijd om op te laden! 🔋';
  }

  @override
  String get deviceOnboardingTurnOffSubtitle => 'Houd de knop 3 seconden ingedrukt';

  @override
  String get done => 'Klaar';

  @override
  String get wifiConfigurationSubtitle => 'Voer uw WiFi-gegevens in zodat het apparaat de firmware kan downloaden.';

  @override
  String get permissionGrantedNow =>
      'Toestemming verleend! Nu:\n\nOpen de Omi-app op je horloge en tik hieronder op \"Doorgaan\"';

  @override
  String get setUpPayPal => 'PayPal instellen';

  @override
  String get statusProcessed => 'Verwerkt';

  @override
  String phoneFreeCallsRemaining(int remaining, int limit) {
    return 'Nog $remaining van $limit gratis gesprekken deze maand';
  }

  @override
  String get event => 'Evenement';

  @override
  String get conversationEvents => 'Gespreksgebeurtenissen';

  @override
  String get uninstall => 'Verwijderen';

  @override
  String get appCreators => 'App-makers';

  @override
  String get muted => 'Gedempt';

  @override
  String get deleteRecapAction => 'Verwijderen';

  @override
  String get addAppErrorSelectingThumbnailRetry => 'Fout bij selecteren miniatuur. Probeer opnieuw.';

  @override
  String get basicPlanDescription => '300 premium minuten + onbeperkt op apparaat';

  @override
  String get countrySelectionPermanent => 'Uw landselectie is permanent en kan later niet worden gewijzigd.';

  @override
  String get transcriptionConnecting => 'Transcriptie verbinden…';

  @override
  String transcriptionsPendingFraction(int pending, int total) {
    return 'Transcripties in behandeling $pending/$total';
  }

  @override
  String get apiKeyAuth => 'API-sleutel authenticatie';

  @override
  String downloadModelWithName(String model) {
    return 'Model downloaden ($model)';
  }

  @override
  String get devModeInvalidDaySummaryWebhookUrl => 'Ongeldige webhook-URL voor dagsamenvatting';

  @override
  String get memoryReviewSaveFailed => 'Opslaan mislukt, probeer het opnieuw';

  @override
  String get payYourSttProvider => 'Gratis in Omi. Je betaalt je transcriptieprovider rechtstreeks.';

  @override
  String get dailySummaryHeader => 'DAGELIJKSE SAMENVATTING';

  @override
  String get fairUseStageWarning => 'Waarschuwing';

  @override
  String get multipleSpeakersDesc =>
      'Het lijkt erop dat er meerdere sprekers in de opname zijn. Zorg ervoor dat je op een rustige locatie bent en probeer het opnieuw.';

  @override
  String get pastChats => 'Eerdere chats';

  @override
  String get listeningMins => 'Luisteren (min)';

  @override
  String get pairingDescOmi => 'Houd het apparaat ingedrukt totdat het trilt om het in te schakelen.';

  @override
  String get deviceOnboardingIntroSubtitle =>
      'Probeer live transcriptie, een vraag stellen en de dubbeltik-snelkoppeling.';

  @override
  String get autoRemoveSyncedCopiesTitle => 'Gesynchroniseerde kopieën automatisch verwijderen';

  @override
  String chatAppsReadOnlyFooter(String app) {
    return 'Deze chats zijn hier alleen-lezen. Antwoord in $app.';
  }

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'Microfoon gewijzigd. Hervatten over ${countdown}s';
  }

  @override
  String get takePhoto => 'Foto maken';

  @override
  String get cancelSync => 'Synchronisatie annuleren';

  @override
  String appSettings(String appName) {
    return '$appName-instellingen';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'Kan microfoontoestemming niet controleren: $error';
  }

  @override
  String get micGain => 'Microfoonversterking';

  @override
  String get collectingData => 'Gegevens verzamelen…';

  @override
  String get memoryReadOnlyHint => 'Deze herinnering wordt bewaard als geschiedenis en kan niet worden bewerkt.';

  @override
  String get appUnderReviewOwner =>
      'Uw app wordt beoordeeld en is alleen zichtbaar voor u. Het wordt openbaar zodra het is goedgekeurd.';

  @override
  String get addNewPerson => 'Nieuwe persoon toevoegen';

  @override
  String get nameSpeakerTitle => 'Spreker benoemen';

  @override
  String get downloadingAudioFromSdCard => 'Audio downloaden van de SD-kaart van je apparaat';

  @override
  String get pendantSyncingRecordings => 'Opnames van je hanger synchroniseren…';

  @override
  String get otaNotSupported => 'Deze firmware kan niet via wifi worden bijgewerkt.';

  @override
  String get wrappedSomethingWentWrong => 'Er ging iets\nmis';

  @override
  String get screenRecording => 'Schermopname';

  @override
  String get audioProcessedLocally =>
      'Audio wordt lokaal verwerkt. Werkt offline, meer privacy, maar gebruikt meer batterij.';

  @override
  String get onboardingSignIn => 'Inloggen';

  @override
  String timeDaysPlural(int count) {
    return '$count dagen';
  }

  @override
  String get memoryReviewTitle => 'Wat ik vandaag heb geleerd';

  @override
  String get hidePassword => 'Wachtwoord verbergen';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get disconnected => 'Verbroken';

  @override
  String get revokeApiKeyQuestion => 'API-sleutel intrekken?';

  @override
  String get detectBrowserBasedMeetings => 'Browsergebaseerde vergaderingen detecteren';

  @override
  String get failedToDeleteConversations => 'Gesprekken verwijderen mislukt';

  @override
  String get raybanMetaCapturePhoto => 'Foto maken';

  @override
  String get bleSpeed => '~30 KB/s via BLE';

  @override
  String get conversationPromptPlaceholder =>
      'Je bent een geweldige app, je krijgt een transcriptie en samenvatting van een gesprek…';

  @override
  String get secureAuthViaGoogleAccount => 'Veilige authenticatie via Google-account';

  @override
  String get omiHas => 'Omi heeft:';

  @override
  String get raybanMetaContinue => 'Doorgaan';

  @override
  String get pauseRecording => 'Opname pauzeren';

  @override
  String get evidenceNothing => 'Je hebt deze persoon nog niet gelabeld of bevestigd';

  @override
  String get noActivityYet => 'Nog geen activiteit';

  @override
  String get enterPasswordError => 'Voer uw wachtwoord in';

  @override
  String get forgetDeviceConfirmTitle => 'Apparaat vergeten?';

  @override
  String get ratingsAndReviews => 'Beoordelingen en recensies';

  @override
  String get addApiKeyAfterImport => 'Je moet je eigen API-sleutel toevoegen na het importeren';

  @override
  String get alreadyOnStableFirmware => 'U gebruikt al de laatste stabiele versie.';

  @override
  String get deleteAccountConfirm => 'Weet je zeker dat je je account wilt verwijderen?';

  @override
  String get recordingInfo => 'Opname-informatie';

  @override
  String get feedbackReasonSummaryInaccurate => 'Niet nauwkeurig';

  @override
  String get pendantRecordingTitle => 'Opnemen op de hanger';

  @override
  String get deleteWhileProcessingMessage =>
      'Deze opname is geüpload maar Omi maakt het gesprek nog aan. Als je hem nu verwijdert en de verwerking mislukt, kan hij niet worden hersteld. Toch verwijderen?';

  @override
  String get createNewKey => 'Nieuwe sleutel maken';

  @override
  String get firmwareDownloadFailedMessage =>
      'De update kon niet worden gedownload en je apparaat is niet gewijzigd. Controleer je internetverbinding en probeer het opnieuw.';

  @override
  String get loadingTasks => 'Taken laden…';

  @override
  String get previousResult => 'Vorig resultaat';

  @override
  String get reviewLoadFailed => 'Je vragen konden niet worden geladen.';

  @override
  String get onDevice => 'Op apparaat';

  @override
  String get bluetoothSyncEnabled => 'Bluetooth-synchronisatie ingeschakeld';

  @override
  String get categorySafety => 'Veiligheid';

  @override
  String get unknownLocation => 'Onbekende locatie';

  @override
  String get newMemoryTitle => 'Nieuwe herinnering';

  @override
  String get conversationCannotBeMerged =>
      'Dit gesprek kan niet worden samengevoegd (vergrendeld of al aan het samenvoegen)';

  @override
  String get summaryGenerated => 'Samenvatting gegenereerd';

  @override
  String get createKey => 'Sleutel Maken';

  @override
  String get letOmiChooseAutomatically => 'Laat Omi automatisch de beste app kiezen';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'Start uw $deviceName opnieuw op om de update te voltooien.';
  }

  @override
  String get goals => 'Doelen';

  @override
  String get wrappedAnErrorOccurred => 'Er is een fout opgetreden';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'Controleren microfoontoegang mislukt: $error';
  }

  @override
  String get connectLater => 'Later verbinden';

  @override
  String get wrappedRememberedByOmi => 'onthouden door Omi';

  @override
  String get fairUseStatusNormal => 'Uw gebruik is binnen de normale grenzen.';

  @override
  String get includePersonalEventsDescription => 'Persoonlijke evenementen zonder deelnemers opnemen';

  @override
  String get week => 'Week';

  @override
  String get willLikelyCrash => 'Dit inschakelen zal waarschijnlijk de app laten crashen of vastlopen.';

  @override
  String get selectPrimaryLanguage => 'Selecteer je primaire taal';

  @override
  String get pilotFeaturesDescription => 'Deze functies zijn tests en er wordt geen ondersteuning gegarandeerd.';

  @override
  String get askOmi => 'Vraag Omi';

  @override
  String get ifYouCancel => 'Als je annuleert:';

  @override
  String get audioOutput => 'Audio-uitvoer';

  @override
  String get memoryReviewWrong => 'Klopt niet';

  @override
  String get couldNotSchedulePlanChange => 'Kon planwijziging niet plannen. Probeer opnieuw.';

  @override
  String speakerLabelEarlierMatches(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Gevonden in $count eerdere gesprekken',
      one: 'Gevonden in 1 eerder gesprek',
    );
    return '$_temp0';
  }

  @override
  String get deviceOnboardingListening => 'Aan het luisteren…';

  @override
  String get speechProfileEnrollmentPrompt =>
      'Zodat Omi weet welke stem van jou is — praat ongeveer 5 seconden over wat je maar wilt.';

  @override
  String get mcpServerUrl => 'MCP Server URL';

  @override
  String get chatBlockMemory => 'Herinnering';

  @override
  String get noStarredConversations => 'Geen gesprekken met ster';

  @override
  String get syncStatusTooOld => 'Te oud om te synchroniseren — Omi kan deze niet accepteren';

  @override
  String connectedAsUser(String userId) {
    return 'Verbonden als gebruiker: $userId';
  }

  @override
  String get phonePageTitle => 'Telefoon';

  @override
  String get buildGraphButton => 'Grafiek bouwen';

  @override
  String get issuesCreatedInRepo => 'Issues worden aangemaakt in je standaard repository';

  @override
  String get scopeUserFacts => 'Gebruikersgegevens';

  @override
  String get unableToLoadPlans => 'Kan plannen niet laden';

  @override
  String get deleteRecording => 'Opname verwijderen';

  @override
  String get appDeleteFailed => 'Kan app niet verwijderen. Probeer het later opnieuw.';

  @override
  String get addAppUpdatedSuccess => 'App succesvol bijgewerkt 🚀';

  @override
  String get reviewCaughtUpTitle => 'Niets om te beantwoorden';

  @override
  String get copyConversationId => 'Gesprek-ID kopiëren';

  @override
  String get helpImproveOmiBySharing => 'Help Omi te verbeteren door geanonimiseerde analysegegevens te delen';

  @override
  String get dataEncryptedBanner =>
      'Je gegevens zijn standaard beveiligd met sterke versleuteling, en jij bepaalt hoe ze worden opgeslagen en gebruikt.';

  @override
  String get redo => 'Opnieuw opnemen';

  @override
  String get updateOmiGlassFirmware => 'OmiGlass-firmware bijwerken';

  @override
  String get deviceUnpairedMessage =>
      'Apparaat ontkoppeld. Ga naar Instellingen > Bluetooth en vergeet het apparaat om het ontkoppelen te voltooien.';

  @override
  String speakerLabelText(String part, String name) {
    String _temp0 = intl.Intl.selectLogic(
      part,
      {
        'likely': 'Waarschijnlijk',
        'soundsLike': 'Klinkt als $name',
        'notPerson': 'Niet $name',
        'carried': 'Nog steeds $name. Overgenomen uit je laatste gesprek.',
        'change': 'Wijzigen',
        'alsoTitle': 'Is dit ook $name?',
        'alsoBody': 'Omi heeft dezelfde stem in eerdere gesprekken gevonden.',
        'confirmed': 'Je hebt dit label bevestigd',
        'other': 'Bekijken',
      },
    );
    return '$_temp0';
  }

  @override
  String get continueWithApple => 'Doorgaan met Apple';

  @override
  String get iUnderstand => 'Ik begrijp het';

  @override
  String get memoryProvenanceAndroid => 'Android';

  @override
  String get saving => 'Opslaan…';

  @override
  String get deviceOnboardingDoubleTapTitle => 'Dubbeltik aanpassen';

  @override
  String get allMemoriesPublicResult => 'Alle herinneringen zijn nu openbaar';

  @override
  String get chatAppsAddToContacts => 'Omi toevoegen aan Contacten';

  @override
  String get wrappedDays => 'dagen';

  @override
  String get invalidJsonError => 'Ongeldige JSON';

  @override
  String syncCardNeedsAttention(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count opnamen vragen aandacht',
      one: '1 opname vraagt aandacht',
    );
    return '$_temp0';
  }

  @override
  String get wrappedSwipeUpToBegin => 'Veeg omhoog om te beginnen';

  @override
  String addedToService(String serviceName) {
    return 'Toegevoegd aan $serviceName';
  }

  @override
  String get advanced => 'Geavanceerd';

  @override
  String get autoCreateAndTagNewSpeakers => 'Nieuwe sprekers automatisch aanmaken en taggen';

  @override
  String get appCapabilities => 'App-mogelijkheden';

  @override
  String get onboardingMicrophoneDenied =>
      'Microfoontoestemming geweigerd. Verleen toestemming in Systeemvoorkeuren > Privacy en beveiliging > Microfoon.';

  @override
  String get pleaseEnterFolderName => 'Voer een mapnaam in';

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'Kan Bluetooth-toestemming niet controleren: $error';
  }

  @override
  String get invalidRecordingDetected => 'Ongeldige opname gedetecteerd';

  @override
  String get appAnalytics => 'App-analyse';

  @override
  String get captureRecordingsSheetTitle => 'Opnamen van dit gesprek';

  @override
  String deletedLimitlessConversations(int count) {
    return '$count Limitless-gesprekken verwijderd';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'Fout bij selecteren afbeelding: $error';
  }

  @override
  String get unnamedSpeakerLabel => 'Spreker';

  @override
  String get failedToCreateApp => 'Kan app niet maken. Probeer het opnieuw.';

  @override
  String get planUpdate => 'Abonnement bijwerken';

  @override
  String get timeout5Minutes => '5 minuten';

  @override
  String get deleteSample => 'Sample verwijderen';

  @override
  String get willNotSeeAgain => 'U zult het niet meer kunnen zien.';

  @override
  String get thisMonth => 'Deze maand';

  @override
  String get enterName => 'Voer naam in';

  @override
  String get memoryThisDevice => 'Dit apparaat';

  @override
  String get verifiedNumbersDescription => 'Wanneer u iemand belt, zien zij dit nummer';

  @override
  String get deviceOnboardingSingleTapHint => 'Dat was één tik — probeer twee keer snel te tikken!';

  @override
  String autoClosingInSeconds(int seconds) {
    return 'Sluit automatisch over $seconds seconden';
  }

  @override
  String get chatAppsProPerkContext => 'Omi onthoudt de context in elke app';

  @override
  String get errorProcessingConversation => 'Fout bij het verwerken van gesprek. Probeer het later opnieuw.';

  @override
  String get profileSettings => 'Profielinstellingen';

  @override
  String get statusUnprocessed => 'Niet verwerkt';

  @override
  String get deleteConversationMessage =>
      'Dit zal ook de bijbehorende herinneringen, taken en audiobestanden verwijderen.';

  @override
  String get cancelSubscriptionQuestion => 'Abonnement annuleren?';

  @override
  String get forUnlimitedFreeTranscription => 'voor onbeperkte gratis transcriptie.';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used van $limit min gebruikt';
  }

  @override
  String get categoryPersonalWellness => 'Persoonlijk welzijn';

  @override
  String get automaticTranslation => 'Automatische vertaling';

  @override
  String get defaultAiAssistant => 'Standaard AI-assistent';

  @override
  String get allDataErased => 'Je herinneringen en gesprekken worden gewist.';

  @override
  String entityDue(String date) {
    return 'Deadline $date';
  }

  @override
  String get feedbackChatWithUs => 'Meer te melden? Chat met ons';

  @override
  String get speakerTagPromptSomeoneNew => 'Iemand nieuws';

  @override
  String get inProgress => 'Bezig';

  @override
  String get raybanMetaCheckAgain => 'Opnieuw controleren';

  @override
  String get fairUseStageNormal => 'Normaal';

  @override
  String get pairingTitleLimitless => 'Zet Limitless in koppelingsmodus';

  @override
  String get usingNativeIosSpeech => 'Gebruik van native iOS spraakherkenning';

  @override
  String get actionItemDeletedSuccessfully => 'Taak succesvol verwijderd';

  @override
  String get failedToSetLanguage => 'Kan taal niet instellen';

  @override
  String get appHomeUrl => 'Startpagina-URL van de app';

  @override
  String get appNameLabel => 'App-naam';

  @override
  String get localStorageDisabled => 'Lokale opslag uitgeschakeld';

  @override
  String get appReEnable => 'Opnieuw inschakelen';

  @override
  String get migrationFailed => 'Migratie mislukt';

  @override
  String get markComplete => 'Markeren als voltooid';

  @override
  String get lastUsedLabel => 'Laatst gebruikt';

  @override
  String get chatCleared => 'Chat gewist';

  @override
  String get revokeApiKeyWarning =>
      'Apps die deze sleutel gebruiken, verliezen toegang tot de API. Dit kan niet ongedaan worden gemaakt.';

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return 'Kan schermopnametoestemming niet controleren: $error';
  }

  @override
  String get troubleshootingSteps =>
      'Probleemoplossing:\n\n1. Zorg dat Omi op je horloge is geïnstalleerd\n2. Open de Omi-app op je horloge\n3. Zoek naar de toestemmingspopup\n4. Tik op \"Toestaan\" wanneer gevraagd\n5. App op je horloge sluit - heropen deze\n6. Kom terug en tik op \"Doorgaan\" op je iPhone';

  @override
  String get location => 'Locatie';

  @override
  String get chatAppsWhatsAppMeantime => 'Telegram en iMessage werken nu al, met dezelfde herinneringen en taken.';

  @override
  String get sliderOff => 'Uit';

  @override
  String get checkingFirmwareVersion => 'Firmware-versie controleren…';

  @override
  String get reviewUnknownSpeaker => 'Onbekende spreker';

  @override
  String get professionSales => 'Verkoop';

  @override
  String get noRssiDataYet => 'Nog geen RSSI-gegevens';

  @override
  String get emptyOldMessage => '✅ Geen oude taken';

  @override
  String deleteSampleConfirmation(String name) {
    return 'De stemsample van $name wordt verwijderd. Dit kan niet ongedaan worden gemaakt.';
  }

  @override
  String get saveUrlButton => 'URL opslaan';

  @override
  String get onboardingNotificationDeniedSystemPrefs =>
      'Meldingstoestemming geweigerd. Verleen toestemming in Systeemvoorkeuren.';

  @override
  String get languageForTranscription => 'Omi gebruikt deze taal voor transcripties, samenvattingen en herinneringen.';

  @override
  String get updatedLabel => 'BIJGEWERKT';

  @override
  String get content => 'Inhoud';

  @override
  String get phoneCallButton => 'Bellen';

  @override
  String get exportStartedMayTakeFewSeconds => 'Export gestart. Dit kan enkele seconden duren…';

  @override
  String dreamReportPrivacyHeld(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count meldingen achtergehouden vanwege privacy',
      one: '1 melding achtergehouden vanwege privacy',
    );
    return '$_temp0';
  }

  @override
  String firmwareBatteryTooLow(int level) {
    return 'De batterij staat op $level%. Laad je apparaat op tot minstens 15% voordat je bijwerkt.';
  }

  @override
  String get appearance => 'Uiterlijk';

  @override
  String noTasksOnDate(Object date) {
    return 'Geen taken op $date';
  }

  @override
  String get deleteFlowFeedbackHint => 'Optioneel — jouw inzichten helpen ons een beter product te bouwen.';

  @override
  String get bluetooth => 'Bluetooth';

  @override
  String get cancelUpdate => 'Update annuleren';

  @override
  String get syncStatusConversationCreated => 'Gesprek aangemaakt';

  @override
  String get reconnecting => 'Opnieuw verbinden…';

  @override
  String get tasksToday => 'Vandaag';

  @override
  String taskCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count taken',
      one: '1 taak',
    );
    return '$_temp0';
  }

  @override
  String get noUpcomingMeetings => 'Geen aankomende vergaderingen';

  @override
  String get invalidRecordingMultipleSpeakers => 'Ongeldige opname gedetecteerd';

  @override
  String get startupFailedTitle => 'Omi kon niet starten';

  @override
  String contactsSelectedCount(int count) {
    return '$count geselecteerd';
  }

  @override
  String get skipForward10Seconds => '10 seconden vooruit';

  @override
  String get noItems => 'Geen items';

  @override
  String get timeout30Minutes => '30 minuten';

  @override
  String get signInSuccess => 'Inloggen gelukt!';

  @override
  String get syncStatusDownloadingFromDevice => 'Downloaden van je apparaat';

  @override
  String get makePrivate => 'Privé maken';

  @override
  String get update => 'Bijwerken';

  @override
  String get aiGenCreatingAppIcon => 'App-pictogram maken…';

  @override
  String get wrappedIntenseDay => 'Intens';

  @override
  String get raybanMetaSkipForNow => 'Nu overslaan';

  @override
  String diagnosticsReconnectedIn(String duration) {
    return 'opnieuw verbonden na $duration';
  }

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'Je schakelt je Onbeperkt Plan over naar het $title.';
  }

  @override
  String get appsAskWith => 'Omi vragen met';

  @override
  String get noMemoriesFound => 'Geen herinneringen gevonden';

  @override
  String get noMemoriesYet => 'Nog geen herinneringen';

  @override
  String get captureRecordingSeparateFailed => 'Scheiden mislukt. Probeer het opnieuw.';

  @override
  String get pinAsBaseline => 'Vastzetten als basis';

  @override
  String get voiceRecognitionSettings => 'Stemherkenning';

  @override
  String get chatAppsComingLater => 'Komt later';

  @override
  String get sliderMax => 'Max.';

  @override
  String get deleteWhileProcessingTitle => 'Nog bezig met verwerken';

  @override
  String get devModeSettingsSaved => 'Instellingen opgeslagen!';

  @override
  String get fairUseToday => 'Vandaag';

  @override
  String get exportDataDesc => 'Gesprekken exporteren naar een JSON-bestand';

  @override
  String get whatsYourName => 'Wat is je naam?';

  @override
  String get onDeviceSlower => 'On-device transcriptie kan trager zijn op dit apparaat.';

  @override
  String get categoryProductivityLifestyle => 'Productiviteit & levensstijl';

  @override
  String get addToYourTaskList => 'Toevoegen aan je takenlijst?';

  @override
  String get meetingScreenshotFallbackCaption => 'Schermafbeelding van deze vergadering';

  @override
  String get effectCountsALittle => 'Helpt een beetje';

  @override
  String get pairingTitleFriendPendant => 'Zet Friend Pendant in koppelingsmodus';

  @override
  String get peopleStatsIncomplete => 'De aantallen zijn mogelijk onvolledig.';

  @override
  String get tapToAddGoal => 'Tik om een doel toe te voegen';

  @override
  String get payment => 'Betaling';

  @override
  String get omiDebugLog => 'Omi debug-log';

  @override
  String get showMeetingsMenuBar => 'Toon aankomende vergaderingen in menubalk';

  @override
  String get mostInstalls => 'Meeste installaties';

  @override
  String chatUsageMessages(String used, String limit) {
    return 'Chat: $used / $limit berichten deze maand';
  }

  @override
  String get chat => 'Chat';

  @override
  String get areYouThere => 'Ben je er nog?';

  @override
  String get highestRating => 'Hoogste beoordeling';

  @override
  String get pleaseSpecify => 'Geef aan';

  @override
  String get staging => 'Testomgeving';

  @override
  String get cancelReasonBatteryDrain => 'Zorgen over batterijverbruik';

  @override
  String get apiKeys => 'API-sleutels';

  @override
  String conversationsCreated(int count) {
    return '$count gesprekken aangemaakt';
  }

  @override
  String get trainingDataProgram => 'Trainingsdataprogramma';

  @override
  String get customBackendUrlTitle => 'Aangepaste backend-URL';

  @override
  String get omiSyncsAudioFiles => 'Omi synchroniseert vervolgens de audiobestanden met de server';

  @override
  String get reviewAnswerMe => 'Ik';

  @override
  String get debugDiagnostics => 'Debug en diagnostiek';

  @override
  String get confidenceReasonNotHeard => 'nog niet gehoord';

  @override
  String get doubleTapAction => 'Dubbel tikken actie';

  @override
  String get showTasksOnHomepage => 'Taken weergeven op startpagina';

  @override
  String failedToStartUpdate(String error) {
    return 'Kan update niet starten: $error';
  }

  @override
  String get feedbackReasonSummaryWrongContext => 'Verkeerde context';

  @override
  String get pleaseProvideValidDescription => 'Geef een geldige beschrijving op';

  @override
  String get appRejectedNotice =>
      'Uw app is afgewezen. Werk de app-details bij en dien deze opnieuw in ter beoordeling.';

  @override
  String get deleteOnDeviceModel => 'Model verwijderen';

  @override
  String get languageSettingsHelperText =>
      'App-taal verandert menu\'s en knoppen. Primaire taal bepaalt hoe je opnames worden getranscribeerd.';

  @override
  String get deleteConversationsMessage => 'Hiermee worden ook hun herinneringen, taken en audiobestanden verwijderd.';

  @override
  String get usageBestMonth => 'Best month';

  @override
  String get creating => 'Maken…';

  @override
  String get microphoneAccessDescription =>
      'Omi heeft microfoontoegang nodig om uw gesprekken op te nemen en transcripties te leveren.';

  @override
  String get cancelReasonNotUsing => 'Gebruik het niet genoeg';

  @override
  String get wrappedWeveAllBeenThere => 'We zijn er allemaal geweest!';

  @override
  String get chatAppsProblemRateLimited => 'Te veel pogingen. Wacht een minuut en probeer het opnieuw.';

  @override
  String get selectOption => 'Selecteren';

  @override
  String get languageBenefits => 'Omi gebruikt deze taal voor transcripties, samenvattingen en herinneringen.';

  @override
  String get triggerConversationIntegration => 'Gesprek aanmaak-integratie activeren';

  @override
  String get integrationSetupRequired =>
      'Als dit een integratie-app is, zorg er dan voor dat de installatie is voltooid.';

  @override
  String get clickPlayToResumeOrStop => 'Klik op afspelen om te hervatten of stop om te voltooien';

  @override
  String disconnectedFrom(String appName) {
    return 'Losgekoppeld van $appName';
  }

  @override
  String get subscribe => 'Abonneren';

  @override
  String get permissionsChangeAnytime => 'Je kunt deze op elk moment wijzigen in Instellingen > Machtigingen';

  @override
  String get enableRemindersAccess =>
      'Schakel toegang tot Herinneringen in via Instellingen om Apple Herinneringen te gebruiken';

  @override
  String get selectProviderTemplate => 'Selecteer een provider sjabloon…';

  @override
  String get initialisingSystemAudio => 'Systeemaudio initialiseren';

  @override
  String get excellent => 'Uitstekend';

  @override
  String get chatBlockGoal => 'Doel';

  @override
  String get deleteFolder => 'Map verwijderen';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'Sleutel maken mislukt: $error';
  }

  @override
  String get whisperModelSizeSmall => 'Klein';

  @override
  String get pleaseCopyKeyNow => 'Kopieer het nu en schrijf het ergens veilig op. ';

  @override
  String get unresolvedSpeakersNotice => 'Sprekerlabels komen mogelijk niet overeen tussen de opnames in dit gesprek.';

  @override
  String get omisMemoryCleared => 'Omi\'s geheugen over jou is gewist';

  @override
  String get manageApp => 'App beheren';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return 'Schermopnametoestemmingsstatus: $status. Controleer Systeemvoorkeuren.';
  }

  @override
  String get edit => 'Bewerken';

  @override
  String get redownload => 'Opnieuw downloaden';

  @override
  String get chatBlockConversation => 'Gesprek';

  @override
  String get loadingApps => 'Apps laden…';

  @override
  String get chatPromptPlaceholder =>
      'Je bent een geweldige app, je taak is om te reageren op gebruikersvragen en hen zich goed te laten voelen…';

  @override
  String get stripeConnectedAccountAgreement => 'Stripe Connected Account-overeenkomst';

  @override
  String get autoSync => 'Automatisch synchroniseren';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'Kennisgrafiek succesvol verwijderd';

  @override
  String get optInAndOptOutOptions => 'Opt-in en opt-out opties';

  @override
  String get permissionReadMemories => 'Herinneringen lezen';

  @override
  String get noSpacesInWorkspace => 'Geen ruimtes gevonden in deze werkruimte';

  @override
  String get reviewYesMerge => 'Ja, samenvoegen';

  @override
  String get voiceMode => 'Spraakmodus';

  @override
  String get fairUseStageThrottle => 'Beperkt';

  @override
  String get deleteChatQuestion => 'Deze chat verwijderen?';

  @override
  String get failedToGetCallToken => 'Kan token niet ophalen. Verifieer eerst uw nummer.';

  @override
  String get selectTime => 'Tijd selecteren';

  @override
  String get sdCardProcessing => 'SD-kaart verwerking';

  @override
  String errorConnectingRayBanMeta(String error) {
    return 'Fout bij verbinden met Ray-Ban Meta: $error';
  }

  @override
  String get couldNotLoadImportHistory => 'Importgeschiedenis kon niet worden geladen';

  @override
  String get noApiKeysFound => 'Geen API-sleutels gevonden. Maak er een om te beginnen.';

  @override
  String get appDisabledTitle => 'Deze app is uitgeschakeld en kan niet worden geïnstalleerd.';

  @override
  String get syncStatusBackedUp => 'Geback-upt';

  @override
  String get speakerTagPromptThatsMeAction => 'Dat ben ik';

  @override
  String timeCompactHoursAndMins(int hours, int mins) {
    return '${hours}u ${mins}m';
  }

  @override
  String get chatPrompt => 'Chat-prompt';

  @override
  String get voicePreviewSample => 'Hoi, ik ben Omi. Dit is mijn stem.';

  @override
  String get saved => 'Opgeslagen';

  @override
  String get grantPermissionButton => 'Toestemming verlenen';

  @override
  String get subscription => 'Abonnement';

  @override
  String get capabilityFeatured => 'Uitgelicht';

  @override
  String get pdfConversationExport => 'Gesprek exporteren';

  @override
  String get unknown => 'Onbekend';

  @override
  String get yourMeetings => 'Je vergaderingen';

  @override
  String get uploadingVoiceProfile => 'Je stemprofiel wordt geüpload….';

  @override
  String get apiUrl => 'API-URL';

  @override
  String get reportMessage => 'Bericht melden';

  @override
  String get passwordLabel => 'Wachtwoord';

  @override
  String get permanentlyRemoveAllMemories => 'Alle herinneringen permanent verwijderen uit Omi';

  @override
  String get transcriptionSlowerLessAccurate => 'Transcriptie zal aanzienlijk langzamer en minder nauwkeurig zijn.';

  @override
  String get filterManual => 'Handmatig';

  @override
  String get keepMyPlan => 'Mijn plan behouden';

  @override
  String get setupQuestionAge => '3. Wat is je leeftijdscategorie?';

  @override
  String get addAppSelectTriggerEvent => 'Selecteer een triggergebeurtenis voor uw app';

  @override
  String get defaultWorkspace => 'Standaard werkruimte';

  @override
  String get errorUpdatingAppStatus => 'Er is een fout opgetreden bij het bijwerken van de app-status.';

  @override
  String get invalidJsonConfig => 'Ongeldige JSON-configuratie';

  @override
  String get detailedDiagnosticMessages => 'Gedetailleerde diagnostische berichten';

  @override
  String get mergingInBackground => 'Samenvoegen op de achtergrond. Dit kan even duren.';

  @override
  String get setDefaultApp => 'Standaardapp instellen';

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Je moet Omi autoriseren om taken aan te maken in je $appName-account. Dit opent je browser voor authenticatie.';
  }

  @override
  String get cleanUpEllipsis => 'Opruimen…';

  @override
  String get addTask => 'Taak toevoegen';

  @override
  String get getCreative => 'Wees creatief';

  @override
  String get captureRecordingOpenFailed => 'Kan deze opname niet openen.';

  @override
  String get emptyTodoMessage => '🎉 Alles bijgewerkt!\nGeen openstaande taken';

  @override
  String get onboardingSetupTitle => 'Je Omi wordt ingesteld';

  @override
  String get sharePeriodAllTime => 'Tot nu toe heeft Omi:';

  @override
  String get translationNotice => 'Vertaalbericht';

  @override
  String captureRecordingError(String error) {
    return 'Er is een fout opgetreden tijdens de opname: $error';
  }

  @override
  String get downloadAudio => 'Audio downloaden';

  @override
  String get identifySpeaker => 'Spreker toewijzen';

  @override
  String get viewTranscript => 'Transcript bekijken';

  @override
  String get makeAllMemoriesPublic => 'Alle herinneringen openbaar maken';

  @override
  String get xTwitter => 'X (Twitter)';

  @override
  String get frequencyOff => 'Uit';

  @override
  String get apiEnvironment => 'API-omgeving';

  @override
  String get processingTakingLonger => 'Nog bezig — dit duurt langer dan normaal.';

  @override
  String get firmwareUpdateFailedTitle => 'Update mislukt';

  @override
  String get unresolvedQuestions => 'Onopgeloste vragen';

  @override
  String get chatAppsMessage => 'Bericht';

  @override
  String get dreamReportManual => 'Handmatig';

  @override
  String get enterSttHttpEndpoint => 'Voer je STT HTTP-endpoint in';

  @override
  String get beforeUpdateMakeSure => 'Voordat u update, zorg ervoor:';

  @override
  String get transcriptionReconnecting => 'Transcriptie opnieuw verbinden…';

  @override
  String get deviceName => 'Apparaatnaam';

  @override
  String neoSubtitle(int count) {
    return '$count vragen per maand';
  }

  @override
  String chatUsageProgress(String used, String limit) {
    return '$used / $limit gebruikt';
  }

  @override
  String get noChangesInReview => 'Geen wijzigingen in de recensie om bij te werken.';

  @override
  String get allMemories => 'Alle herinneringen';

  @override
  String get needMicrophonePermission =>
      'We hebben microfoontoestemming nodig.\n\n1. Tik op \"Toestemming verlenen\"\n2. Sta toe op je iPhone\n3. Horloge-app sluit\n4. Heropen en tik op \"Doorgaan\"';

  @override
  String get keepSpeakingUntil100 => 'Blijf praten tot je 100% bereikt.';

  @override
  String get singleLanguageModeInfo =>
      'Enkeltaalmodus is ingeschakeld. Vertaling is uitgeschakeld voor hogere nauwkeurigheid.';

  @override
  String get thisCannotBeUndone => 'Dit kan niet ongedaan worden gemaakt.';

  @override
  String get setupSkipHelp => 'Overslaan, ik wil niet helpen :C';

  @override
  String get speakerTagPromptNoAction => 'Nee…';

  @override
  String labelCopied(String label) {
    return '$label gekopieerd';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'Fout bij wisselen van audio-apparaat: $error';
  }

  @override
  String get remembering => 'Onthouden';

  @override
  String get externalAppAccessDescription =>
      'De volgende geïnstalleerde apps hebben externe integraties en kunnen toegang krijgen tot uw gegevens, zoals gesprekken en herinneringen.';

  @override
  String get preferences => 'Voorkeuren';

  @override
  String get wrappedFunDay => 'Leuk';

  @override
  String get effectNeeded => 'Nodig voor Bevestigd';

  @override
  String get importantConversationBody => 'Je hebt net een belangrijk gesprek gehad. Tik om de samenvatting te delen.';

  @override
  String whyConfidenceMenu(String level) {
    return 'Waarom $level?';
  }

  @override
  String get cmdRequired => '⌘ vereist';

  @override
  String get completed => 'Voltooid';

  @override
  String get deviceOnboardingVoiceReplyStatusAlwaysSpeaker =>
      'Wordt hardop afgespeeld via de luidspreker van de telefoon.';

  @override
  String get effectCountsAgainst => 'Schaadt';

  @override
  String get recaps => 'Samenvattingen';

  @override
  String get shareConversationQuestion => 'Gesprek delen?';

  @override
  String get actionItemsCopiedToClipboard => 'Taken gekopieerd naar klembord';

  @override
  String get appleHealthManageNote =>
      'Omi heeft toegang tot Apple Health via Apple\'s HealthKit-framework. Je kunt de toegang op elk moment intrekken in de iOS-instellingen.';

  @override
  String addingToService(String serviceName) {
    return 'Toevoegen aan $serviceName…';
  }

  @override
  String get needHelpGettingStarted => 'Hulp nodig om te beginnen?';

  @override
  String get thanksForAuthorizing => 'Bedankt voor het autoriseren!';

  @override
  String get assistantVoiceSettingsTitle => 'Stem';

  @override
  String get cloudStorageDisabled => 'Cloudopslag uitgeschakeld';

  @override
  String get reviewPlayClip => 'Fragment afspelen';

  @override
  String get storeAudioOnCloud => 'Audio opslaan in de cloud';

  @override
  String get syncStatusBackingUp => 'Synchroniseren…';

  @override
  String get peopleFilterPinned => 'Vastgezet';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName ingesteld als standaard samenvattingsapp';
  }

  @override
  String get githubRepositoryUrlRequired => 'GitHub-repository-URL is verplicht';

  @override
  String get microphoneAccess => 'Microfoontoegang';

  @override
  String get cancelSubscriptionButton => 'Abonnement annuleren';

  @override
  String get signal => 'Signaal';

  @override
  String get failedToConnectAsanaRetry => 'Verbinding met Asana mislukt. Probeer het opnieuw.';

  @override
  String get keyCreatedMessage => 'Uw nieuwe sleutel is aangemaakt. Kopieer deze nu. U kunt deze niet meer zien.';

  @override
  String autoRemoveSyncedCopiesDays(int days) {
    return 'Gesynchroniseerde kopieën worden na $days dagen verwijderd';
  }

  @override
  String get wrappedMostCringeMoment => 'Meest gênant';

  @override
  String get activity => 'Activiteit';

  @override
  String get calendarSettings => 'Agenda-instellingen';

  @override
  String get additionalFeedbackOptional => 'Aanvullende feedback (optioneel)';

  @override
  String get phoneAllow => 'Toestaan';

  @override
  String get noDeviceConnectedUseMic => 'Geen apparaat verbonden. De telefoonmicrofoon wordt gebruikt.';

  @override
  String get stripeOnboardingInstructions =>
      'Voltooi het Stripe-onboardingproces in uw browser. Deze pagina wordt automatisch bijgewerkt zodra het proces is voltooid.';

  @override
  String availableSpaceWithValue(String space) {
    return 'Beschikbare ruimte: $space';
  }

  @override
  String get conversationDetails => 'Gespreksdetails';

  @override
  String get wrappedYouHadFunnyMoments => 'Je had grappige momenten dit jaar!';

  @override
  String get actionReadConversations => 'Gesprekken lezen';

  @override
  String speakerTagPromptIsThisPerson(String name) {
    return 'Is dit $name?';
  }

  @override
  String get openSettings => 'Instellingen openen';

  @override
  String get alwaysAvailable => 'altijd beschikbaar.';

  @override
  String get rating1PlusStars => '1+ ster';

  @override
  String get pauseResume => 'Pauzeren/Hervatten';

  @override
  String get conversationDeleted => 'Gesprek verwijderd';

  @override
  String get memoryReviewRight => 'Klopt';

  @override
  String get deleteGoal => 'Doel verwijderen';

  @override
  String get youtube => 'YouTube';

  @override
  String get untitledConversation => 'Naamloos gesprek';

  @override
  String get yourOmiInsights => 'Je Omi-inzichten';

  @override
  String get compareTranscripts => 'Transcripties vergelijken';

  @override
  String get pause => 'Pauzeren';

  @override
  String get successfullyConnectedGoogle => 'Succesvol verbonden met Google!';

  @override
  String planRenewsOn(String date) {
    return 'Uw plan wordt verlengd op $date.';
  }

  @override
  String chatAppsOpenApp(String app) {
    return 'Open $app';
  }

  @override
  String get dailySummaryDescription =>
      'Ontvang een gepersonaliseerde samenvatting van je dagelijkse gesprekken als melding.';

  @override
  String conversationPhotosCount(int count) {
    return '$count foto\'s';
  }

  @override
  String get errorLoadingAudio => 'Fout bij laden van audio';

  @override
  String get couldNotAccessFile => 'Kan het geselecteerde bestand niet openen';

  @override
  String deleteGraphFailed(String error) {
    return 'Verwijderen graaf mislukt: $error';
  }

  @override
  String get reviewOpenDetailsHint => 'Opent details';

  @override
  String get conversationTimeoutDesc =>
      'Kies hoe lang te wachten in stilte voordat een gesprek automatisch wordt beëindigd:';

  @override
  String get transcriptionJsonPlaceholder => 'Plak hier je JSON-configuratie…';

  @override
  String get loadingCapabilities => 'Functies laden…';

  @override
  String get activeStatus => 'Actief';

  @override
  String get noDailyRecapsYet => 'Nog geen dagelijkse samenvattingen';

  @override
  String get wouldLikePermission => 'We willen graag je toestemming om je spraakopnames op te slaan. Dit is waarom:';

  @override
  String get chatBlockRecommendedNextSteps => 'Aanbevolen volgende stappen';

  @override
  String get tryAdjustingSearchTerms => 'Probeer je zoektermen aan te passen';

  @override
  String get connectOmiWithAI => 'Verbind Omi met AI-assistenten';

  @override
  String get whenToReceiveDailySummary => 'Wanneer je dagelijkse samenvatting ontvangen';

  @override
  String syncCardReadyCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count opnames klaar om te synchroniseren',
      one: '1 opname klaar om te synchroniseren',
    );
    return '$_temp0';
  }

  @override
  String get yourApiKey => 'UW API-SLEUTEL';

  @override
  String failedToLoadRepos(String error) {
    return 'Laden van repositories mislukt: $error';
  }

  @override
  String get syncingMessages => 'Berichten synchroniseren met de server…';

  @override
  String get pleaseSelectARating => 'Selecteer een beoordeling';

  @override
  String get suggestedTemplates => 'Voorgestelde sjablonen';

  @override
  String get updateAppQuestion => 'App bijwerken?';

  @override
  String get frequencyDescOff => 'Geen proactieve meldingen';

  @override
  String get triggerAudioBytes => 'Audiobytes';

  @override
  String get confirmClearChat => 'Deze chat wissen? Dit kan niet ongedaan worden gemaakt.';

  @override
  String get dataPrivacy => 'Gegevensprivacy';

  @override
  String get audioFromOmiWillAppearHere => 'Audio van je Omi-apparaat verschijnt hier';

  @override
  String get durationLabel => 'Duur';

  @override
  String get deviceOnboardingAllSetTitle => 'Alles is ingesteld';

  @override
  String msgSelectImagesError(String error) {
    return 'Fout bij selecteren van afbeeldingen: $error';
  }

  @override
  String evidenceCardPicks(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Gekozen in $count suggesties',
      one: 'Gekozen in 1 suggestie',
    );
    return '$_temp0';
  }

  @override
  String get connectionLostDesc =>
      'De verbinding is onderbroken. Controleer je internetverbinding en probeer het opnieuw.';

  @override
  String get defaultLabel => 'Standaard';

  @override
  String get raybanMetaAllowCamera => 'Camera op bril toestaan';

  @override
  String get addAppSelectCoreCapability => 'Selecteer nog een kernfunctie voor uw app';

  @override
  String get noManualMemories => 'Nog geen handmatige herinneringen';

  @override
  String get deliveryTime => 'Bezorgtijd';

  @override
  String get defaultProjectOptional => 'Standaardproject (optioneel)';

  @override
  String get devModeInvalidAudioBytesWebhookUrl => 'Ongeldige webhook-URL voor audiobytes';

  @override
  String get ignoredVoicesTitle => 'Genegeerde stemmen';

  @override
  String get refreshManifest => 'Manifest vernieuwen';

  @override
  String get diagnosticsRightNow => 'Op dit moment';

  @override
  String get reviewDue => 'Deadline';

  @override
  String get unmute => 'Dempen opheffen';

  @override
  String get recordingsDeleted => 'Opnames verwijderd.';

  @override
  String get failedToDeleteFolder => 'Kan map niet verwijderen';

  @override
  String get reviewAnswerOther => 'Anders';

  @override
  String get exportedConversations => 'Geëxporteerde gesprekken van Omi';

  @override
  String get privacyPolicy => 'Privacybeleid';

  @override
  String get editReply => 'Reactie bewerken';

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription en is $triggerDescription.';
  }

  @override
  String errorSaving(String error) {
    return 'Fout bij opslaan: $error';
  }

  @override
  String get diagnosticsConnectedFor => 'Verbonden sinds';

  @override
  String get callStateConnecting => 'Verbinden…';

  @override
  String get conversationUrlNotShared => 'Gesprek-URL kon niet worden gedeeld.';

  @override
  String get tooShortDesc => 'Er is niet genoeg spraak gedetecteerd. Spreek meer en probeer het opnieuw.';

  @override
  String get failedToShareRecap => 'Kan de samenvatting niet delen';

  @override
  String get billingMonthly => 'Maandelijks';

  @override
  String get developingLogic => 'Logica ontwikkelen';

  @override
  String get phoneContinue => 'Doorgaan';

  @override
  String get successfullyConnectedGitHub => 'Succesvol verbonden met GitHub!';

  @override
  String get failedToSubmitReview => 'Verzenden van recensie mislukt. Probeer het opnieuw.';

  @override
  String get anyoneCanDiscover => 'Iedereen kan je app ontdekken';

  @override
  String get v2Undetected => 'V2 niet gedetecteerd';

  @override
  String get usageIrlEvents => 'Bij evenementen';

  @override
  String get conversationPromptHint => 'bijv., Haal taken, genomen beslissingen en belangrijke punten uit het gesprek.';

  @override
  String get openProviderDocs => 'Documentatie openen';

  @override
  String get showMeetingsInMenuBar => 'Vergaderingen weergeven in menubalk';

  @override
  String get viewPlansAndUsage => 'Bekijk Plannen & Gebruik';

  @override
  String get buildSubmitCustomOmiApp => 'Bouw en dien je aangepaste Omi-app in';

  @override
  String get failedToRefreshGoogleStatus => 'Kan de Google-verbindingsstatus niet vernieuwen.';

  @override
  String get feedbackSubtitleTooExpensive => 'Je feedback helpt ons de juiste balans te vinden.';

  @override
  String get startUsingOmi => 'Begin met Omi';

  @override
  String get dreamReportLearnedWords => 'Geleerde woorden';

  @override
  String get actionItemCreated => 'Taak aangemaakt';

  @override
  String get exportAllConversationsToJson => 'Exporteer al uw gesprekken naar een JSON-bestand.';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'Controleer je internetverbinding en probeer opnieuw';

  @override
  String get callStateEnded => 'Gesprek beeindigd';

  @override
  String get phoneNumberHint => 'Telefoonnummer';

  @override
  String get tasksGroupByProject => 'Groeperen op project';

  @override
  String get phoneCallsUnlimitedOnly => 'Telefoongesprekken via Omi';

  @override
  String get frequencyDescMinimal => 'Alleen dringende zaken, ongeveer 1–3 per dag';

  @override
  String get changeYourName => 'Wijzig uw naam';

  @override
  String get editYourReply => 'Antwoord bewerken';

  @override
  String get publicMemories => 'Openbare herinneringen';

  @override
  String get monthDec => 'Dec';

  @override
  String get reviewNewPersonName => 'Hun naam';

  @override
  String get googleCalendarConnectPrompt => 'Verbind je Google Agenda om gesprekken aan agenda-items te koppelen.';

  @override
  String get realtimeAudioBytes => 'Realtime audiobytes';

  @override
  String get trackYourGoalsOnHomepage => 'Volg je persoonlijke doelen op de startpagina';

  @override
  String get chatAddAttachment => 'Bijlage toevoegen';

  @override
  String get beta => 'BETA';

  @override
  String get createMemory => 'Geheugen maken';

  @override
  String get permissionsRequiredDescription =>
      'Omi heeft een aantal machtigingen nodig om goed te werken. Verleen ze alsjeblieft om door te gaan.';

  @override
  String get dataCollectionMessage =>
      'Door door te gaan, worden je gesprekken, opnames en persoonlijke informatie veilig opgeslagen op onze servers om AI-gedreven inzichten te bieden en alle app-functies mogelijk te maken.';

  @override
  String get batteryLevel => 'Batterijniveau';

  @override
  String get searchCountries => 'Landen zoeken...';

  @override
  String get confidenceSheetTitle => 'Zekerheid';

  @override
  String get deviceModelLabel => 'Apparaatmodel';

  @override
  String get noStableFirmwareFound => 'Kan geen stabiele firmwareversie vinden voor uw apparaat.';

  @override
  String get noResultsFound => 'Geen resultaten gevonden';

  @override
  String get wrappedMins => 'min';

  @override
  String get chatAppsTelegramSubtitle => 'In twee tikken ingesteld';

  @override
  String get categoryConversationAnalysis => 'Gesprekanalyse';

  @override
  String get target => 'Doel';

  @override
  String get apiKeyRequired => 'API-sleutel is vereist';

  @override
  String otaUpdatedMessage(String deviceName) {
    return '$deviceName is bijgewerkt en start vanzelf opnieuw op.';
  }

  @override
  String get reconnections => 'Herverbindingen';

  @override
  String errorCheckingConnection(String error) {
    return 'Fout bij controleren verbinding: $error';
  }

  @override
  String get usageMonth => 'Deze maand';

  @override
  String get additionalSpeechSampleRemoved => 'Extra spraakvoorbeeld verwijderd';

  @override
  String get speakerTagPromptExcerptSaved => 'Antwoord opgeslagen voor dit fragment.';

  @override
  String get omisStorage => 'Omi\'s opslag';

  @override
  String get recordingAndTranscription => 'Opname en transcriptie';

  @override
  String get categoryCommunication => 'Communicatie';

  @override
  String get wrappedYouDidIt => 'Je hebt het gedaan! 🎉';

  @override
  String get failedToDeleteItems => 'Kan items niet verwijderen';

  @override
  String speakerLabelLinesLabeled(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count regels gelabeld',
      one: '1 regel gelabeld',
    );
    return '$_temp0';
  }

  @override
  String get generatingLink => 'Link wordt gegenereerd…';

  @override
  String get clickHereForAppBuildingGuides => 'Klik hier voor app-bouwgidsen en documentatie';

  @override
  String get authUrl => 'Authenticatie-URL';

  @override
  String get addAppCapabilityConflictWithPersona => 'Andere functies kunnen niet worden geselecteerd met Persona';

  @override
  String get deviceOnboardingVoiceReplyGenericHeadphones => 'Koptelefoon';

  @override
  String get clearAll => 'Alles wissen';

  @override
  String get noKnowledgeGraphYet => 'Nog geen kennisgrafiek';

  @override
  String get messageReportedSuccessfully => '✅ Bericht succesvol gemeld';

  @override
  String get paymentFailedToSetDefault => 'Instellen standaard betaalmethode mislukt. Probeer het later opnieuw.';

  @override
  String get memoryReviewUpdated => 'Bijgewerkt.';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'Je abonnement wordt geannuleerd op $date.';
  }

  @override
  String get welcomeToOmi => 'Welkom bij Omi';

  @override
  String get phoneFreeCallLimitReached =>
      'Maandelijkse limiet voor gratis gesprekken bereikt. Deze wordt volgende maand gereset.';

  @override
  String get omiTranscriptionOptimized =>
      'De live transcriptie van Omi is gemaakt voor realtime gesprekken en laat zien wie wat zei.';

  @override
  String get chatAppsLoadFailedTitle => 'Kan chat-apps niet laden';

  @override
  String get continueWithGoogle => 'Doorgaan met Google';

  @override
  String get setupSteps => 'Installatiestappen';

  @override
  String totalMemoriesCount(int count) {
    return 'Je hebt $count herinneringen in totaal';
  }

  @override
  String get feedbackSubtitleBatteryDrain => 'Dit helpt ons hardwareteam verbeteren.';

  @override
  String get tryIt => 'Probeer het';

  @override
  String get chatAppsInsights => 'Inzichten van Omi';

  @override
  String nFiles(int count) {
    return '$count opnames';
  }

  @override
  String get clearChatTitle => 'Chat wissen?';

  @override
  String get onlyYouCanUseTemplate => 'Alleen u kunt deze sjabloon gebruiken';

  @override
  String get raybanMetaCameraExplanation =>
      'Omi gebruikt de camera van je bril om foto\'s aan je gesprekken toe te voegen. Je kunt dit overslaan en alleen audio gebruiken.';

  @override
  String get deviceDiagnosticsTicket => 'Support ticket code';

  @override
  String get capabilityTasks => 'Taken';

  @override
  String get copyUrl => 'URL kopiëren';

  @override
  String keepItemPublic(String item) {
    return '$item openbaar houden';
  }

  @override
  String get chatStarterTeachMe => 'Kun je me iets nieuws leren?';

  @override
  String get cancelReasonDetailHint => 'We waarderen alle feedback…';

  @override
  String get checkConnectionTryAgain => 'Controleer je verbinding en probeer het opnieuw.';

  @override
  String get backToConversations => 'Terug naar gesprekken';

  @override
  String get merge => 'Samenvoegen';

  @override
  String get couldNotLaunchUpgradePage => 'Kon upgradepagina niet openen. Probeer opnieuw.';

  @override
  String get deviceOnboardingTranscriptionSubtitle => 'Zeg een paar woorden en zie ze in realtime verschijnen';

  @override
  String get deleteOnDeviceModelConfirm => 'Dit model verwijderen?';

  @override
  String get reviewQuestionSpeaker => 'Wie zei dit?';

  @override
  String updatedDate(String date) {
    return 'Bijgewerkt $date';
  }

  @override
  String get saveSettings => 'Instellingen Opslaan';

  @override
  String get alreadyGavePermission =>
      'Je hebt ons al toestemming gegeven om je opnames op te slaan. Hier is een herinnering waarom we het nodig hebben:';

  @override
  String get appCreatedAndInstalled => 'App gemaakt en geïnstalleerd!';

  @override
  String get failedToRefreshNotionStatus => 'Kan de Notion-verbindingsstatus niet vernieuwen.';

  @override
  String get deviceOnboardingProcessingQuestion => 'Je vraag wordt verwerkt…';

  @override
  String get chatBlockTask => 'Taak';

  @override
  String get pendantNotConnected => 'Hanger niet verbonden. Verbind om te synchroniseren.';

  @override
  String get createActionItem => 'Taak aanmaken';

  @override
  String get logsCopied => 'Logboeken gekopieerd';

  @override
  String get timeout5MinutesDesc => 'Gesprek beëindigen na 5 minuten stilte';

  @override
  String get msgUploadFileFailed => 'Bestand uploaden mislukt, probeer het later opnieuw';

  @override
  String get reportMessageConfirm => 'Dit bericht melden?';

  @override
  String deletePersonConfirmation(String name) {
    return 'Hiermee worden de stemsamples van $name verwijderd. Dit kan niet ongedaan worden gemaakt. De uitspraken in eerdere gesprekken worden naamloze sprekers.';
  }

  @override
  String get weekdayTue => 'Di';

  @override
  String get liveTranscript => 'Live transcriptie';

  @override
  String timeDaysAndHours(int days, int hours) {
    return '$days dagen $hours uur';
  }

  @override
  String versionLabel(String version) {
    return 'Versie $version';
  }

  @override
  String get cancelConsequenceDelay => '5-7 seconden verwerkingsvertraging (modellen op het apparaat)';

  @override
  String captureRecordingSeparateMessage(String recording) {
    return '$recording wordt als apart gesprek getoond en niet opnieuw met deze gebeurtenis gegroepeerd.';
  }

  @override
  String get updateAvailableTitle => 'Update beschikbaar';

  @override
  String get dreamReportShadowBanner =>
      'Voorbeeldmodus: Dream laat zien wat het zou wijzigen, maar er verandert nog niets in je account.';

  @override
  String get sharedTasksAcceptFailed =>
      'Deze taken konden niet worden geaccepteerd. Misschien heb je deze deling al geaccepteerd.';

  @override
  String get appPricingLabel => 'App-prijzen';

  @override
  String get reDownload => 'Opnieuw downloaden';

  @override
  String get recordWithPhoneMic => 'Opnemen met telefoonmicrofoon';

  @override
  String appDisabledOn(String date) {
    return 'Uitgeschakeld op $date.';
  }

  @override
  String get play => 'Afspelen';

  @override
  String get private => 'Privé';

  @override
  String get speakerTagPromptNotSureAction => 'Weet ik niet';

  @override
  String get showDiscardedConversationsDesc => 'Gesprekken gemarkeerd als verwijderd opnemen';

  @override
  String get captureModeLiveDescription => 'Transcribeer in realtime terwijl je praat.';

  @override
  String get subscriptionCancelledSuccessfully =>
      'Abonnement succesvol geannuleerd. Het blijft actief tot het einde van de huidige factureringsperiode.';

  @override
  String get tapToSetAGoal => 'Tik om een doel in te stellen';

  @override
  String get tellUsMoreWhatWentWrong => 'Vertel ons meer over wat er fout ging…';

  @override
  String get downgradeToFreemiumTitle => 'Downgraden naar Freemium?';

  @override
  String get usageTasks => 'Taken';

  @override
  String get chatReplyOffline => 'Kan geen verbinding maken. Controleer je verbinding en probeer het opnieuw.';

  @override
  String get makePublic => 'Openbaar maken';

  @override
  String get authUnexpectedErrorFirebase => 'Onverwachte fout bij aanmelden, Firebase-fout, probeer het opnieuw.';

  @override
  String get unlimitedConversations => 'Onbeperkte gesprekken';

  @override
  String get stagingDisclaimer =>
      'De testomgeving kan onstabiel zijn, inconsistente prestaties hebben en gegevens kunnen verloren gaan. Alleen voor testen.';

  @override
  String get captureMicrophonePermissionRequired => 'Microfoontoestemming vereist';

  @override
  String shareStatsInsights(String count) {
    return '✨ $count inzichten gegeven';
  }

  @override
  String get feedbackReasonSummaryIrrelevant => 'Niet relevant';

  @override
  String get userIdCopiedToClipboard => 'Gebruikers-ID gekopieerd';

  @override
  String get urlCopiedToClipboard => 'URL gekopieerd naar klembord';

  @override
  String annualBillingSummary(int months, String price) {
    return '$months maanden / $price';
  }

  @override
  String chatAppsShowInAppOff(String app) {
    return 'Uit: je ziet ze alleen in $app.';
  }

  @override
  String get replySentSuccessfully => 'Reactie succesvol verzonden';

  @override
  String get deviceOnboardingTurnOffTitle => 'Uitzetten';

  @override
  String get phoneStorageDesc =>
      'Wanneer Omi opnieuw verbinding maakt, worden opnames automatisch naar uw telefoon overgebracht voor het uploaden.';

  @override
  String get callRecordingConsentDisclaimer => 'Gespreksopname kan toestemming vereisen in uw rechtsgebied';

  @override
  String get showDiscardedConversations => 'Verwijderde gesprekken tonen';

  @override
  String get calendarIntegration => 'Agenda-integratie';

  @override
  String get whisperModelSizeBase => 'Basis';

  @override
  String get shareViaSms => 'Delen via SMS';

  @override
  String get nameMustBeAtLeast3Characters => 'Naam moet minimaal 3 tekens zijn';

  @override
  String get chatDiscardRecording => 'Verwerpen';

  @override
  String get chatAppsProPerkText => 'Stuur Omi een bericht via Telegram en iMessage';

  @override
  String get readyToSync => 'Klaar om te synchroniseren';

  @override
  String get noAppsInCategoryYet => 'Nog geen apps in deze categorie';

  @override
  String get firmwareUpdateAvailable => 'Firmware-update beschikbaar';

  @override
  String get modelNumber => 'Modelnummer';

  @override
  String get sortBy => 'Sorteren';

  @override
  String get slideToUpdate => 'Schuif om bij te werken';

  @override
  String get effectBarelyCounts => 'Helpt nauwelijks';

  @override
  String get onlyYouCanUse => 'Alleen jij kunt deze app gebruiken';

  @override
  String get triggersWhenNewConversationCreated => 'Wordt geactiveerd wanneer een nieuw gesprek wordt aangemaakt.';

  @override
  String get paymentPlan => 'Betalingsplan';

  @override
  String get whisperModelDesc => 'Selecteer het model voor on-device transcriptie';

  @override
  String get askSuggestOwe => 'Wat ben ik mensen nog verschuldigd?';

  @override
  String get starConversation => 'Gesprek als favoriet markeren';

  @override
  String get hardwareSection => 'Hardware';

  @override
  String get transcribing => 'Transcriberen…';

  @override
  String get chatAppsVoiceNotesSubtitle => 'Stuur een spraakbericht en Omi antwoordt erop.';

  @override
  String confidenceNextVoice(String name) {
    return 'Omi heeft ook een stemvoorbeeld van $name nodig. Label deze persoon met “Stemmen onthouden” aan.';
  }

  @override
  String get rating3PlusStars => '3+ sterren';

  @override
  String get recordingActive => 'Opname actief';

  @override
  String starFilter(int count) {
    return '$count ster';
  }

  @override
  String get storageLocationLabel => 'Opslaglocatie';

  @override
  String get reviewNoChangesBody => 'Als Omi je notities opruimt, verschijnen de wijzigingen hier.';

  @override
  String get testPrompt => 'Prompt testen';

  @override
  String get otaUpdateUnavailable => 'Deze update is nu niet beschikbaar. Probeer het later opnieuw.';

  @override
  String get downloading => 'Downloaden…';

  @override
  String get welcomeBackSimple => 'Welkom terug';

  @override
  String get sttProviderSoniox => 'Soniox';

  @override
  String get clearAllSelection => 'Alles wissen';

  @override
  String get confidenceReasonNeverConfirmed => 'Nooit bevestigd';

  @override
  String get writeScope => 'Schrijven';

  @override
  String get evidenceVoiceReady => 'Stemvoorbeeld klaar';

  @override
  String get updateApp => 'App bijwerken';

  @override
  String get weekdayThu => 'Do';

  @override
  String chatUsageCostNoLimit(String used) {
    return 'Chat: \$$used gebruikt deze maand';
  }

  @override
  String get configCopied => 'Configuratie gekopieerd naar klembord';

  @override
  String get startupFailedConfigMessage =>
      'Deze build van Omi heeft een configuratieprobleem. Het ligt niet aan je apparaat. Neem contact op met support en voeg de onderstaande details toe.';

  @override
  String get getOmiForMac => 'Omi voor Mac downloaden';

  @override
  String get appleHealthConnectedBadge => 'Verbonden';

  @override
  String get msgCameraNotAvailable => 'Camera-opname is niet beschikbaar op dit platform';

  @override
  String get actionItemsDescription => 'Tik om te bewerken • Lang indrukken om te selecteren • Veeg voor acties';

  @override
  String get notificationsDesc =>
      'Zodat Omi je gespreksamenvattingen, taakherinneringen en antwoorden van je apps kan sturen.';

  @override
  String audioUploadRetrying(String duration) {
    return 'Upload opnieuw proberen… $duration audio bewaard op je telefoon';
  }

  @override
  String get importStarted => 'Import gestart! Je krijgt een melding wanneer het klaar is.';

  @override
  String get onDeviceModelDownloadFailed => 'Downloaden van model mislukt';

  @override
  String get noProjectsInWorkspace => 'Geen projecten gevonden in deze werkruimte';

  @override
  String get helpCenter => 'Helpcentrum';

  @override
  String get trainingDataBullets =>
      '• Je gegevens helpen AI-modellen verbeteren\n• Alleen niet-gevoelige gegevens worden gedeeld';

  @override
  String get invalidPromotionCode => 'Ongeldige promotiecode.';

  @override
  String get battery => 'Batterij';

  @override
  String get clearSelection => 'Selectie wissen';

  @override
  String get phoneSetupStep2Subtitle => 'Een korte code die u invoert tijdens het gesprek';

  @override
  String get googleSearch => 'Google Search';

  @override
  String get charging => 'Opladen';

  @override
  String deleteNamedPerson(String name) {
    return '$name verwijderen';
  }

  @override
  String get chatAppsPartOfPro => 'Chat-apps zijn onderdeel van Pro';

  @override
  String get invalidWebhookUrlError => 'Voer een geldige webhook-URL in';

  @override
  String get starConversationsToFindQuickly => 'Geef gesprekken een ster om ze hier snel te vinden';

  @override
  String get permissionCreateMemories => 'Herinneringen maken';

  @override
  String get conversationIdCopied => 'Gesprek-ID gekopieerd naar klembord';

  @override
  String get chatAppsMessagesApp => 'Berichten';

  @override
  String get understandingWords => 'Begrijpen (woorden)';

  @override
  String diagnosticsVerdictTroubleDetail(int count) {
    return 'Mislukte verbindingen in de afgelopen 24 uur: $count';
  }

  @override
  String get editName => 'Naam bewerken';

  @override
  String get askAboutThisConversation => 'Hiernaar vragen';

  @override
  String get useTemplateFrom => 'Gebruik sjabloon van';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'Microfoontoestemmingsstatus: $status. Controleer Systeemvoorkeuren.';
  }

  @override
  String get markAsCompleted => 'Markeren als voltooid';

  @override
  String get urlMustEndWithSlashError => 'URL moet eindigen met \"/\"';

  @override
  String get deviceOnboardingIntroTitle => 'Maak kennis met je Omi';

  @override
  String nPending(int count) {
    return '$count in afwachting';
  }

  @override
  String get howShouldOmiCallYou => 'Hoe moet Omi je noemen?';

  @override
  String get preparingFormForYou => 'Het formulier wordt voor je voorbereid…';

  @override
  String get deleteChat => 'Chat verwijderen';

  @override
  String get msgPhotosPermissionDenied =>
      'Fototoestemming geweigerd. Geef alstublieft toegang tot foto\'s om afbeeldingen te selecteren';

  @override
  String get moreWaysToRecord => 'Meer manieren om op te nemen';

  @override
  String get creatingPlan => 'Plan maken';

  @override
  String get configCopiedToClipboard => 'Configuratie gekopieerd naar klembord';

  @override
  String get transcribeLaterDescription =>
      'Neem nu op en transcribeer wanneer je wilt. Tot dan blijft de audio op je telefoon.';

  @override
  String get couldNotSwitchToFreePlan => 'Kon niet overschakelen naar gratis abonnement. Probeer het opnieuw.';

  @override
  String get wrappedTasksCompleted => 'taken voltooid';

  @override
  String get deviceOnboardingTranscriptionTitle => 'Spreek in je Omi';

  @override
  String get thankYouRequestUnderReview =>
      'Bedankt! Uw verzoek wordt beoordeeld. We laten u weten wanneer het is goedgekeurd.';

  @override
  String get unpairAndForgetDevice => 'Ontkoppelen en apparaat vergeten';

  @override
  String get sendWebUrl => 'Verstuur web-URL';

  @override
  String get noTasksForToday => 'Geen taken voor vandaag.\nVraag Omi om meer taken of maak ze handmatig aan.';

  @override
  String get conversationSummaryFailed => 'Samenvatting mislukt';

  @override
  String get realtimeTranscript => 'Realtime transcriptie';

  @override
  String nConversationsCreated(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count gesprekken aangemaakt',
      one: '1 gesprek aangemaakt',
    );
    return '$_temp0';
  }

  @override
  String get noEmailSet => 'Geen e-mail ingesteld';

  @override
  String get setDueDateAndTime => 'Vervaldatum en tijd instellen';

  @override
  String get pairingDescFieldy => 'Houd het apparaat ingedrukt totdat het lampje verschijnt om het in te schakelen.';

  @override
  String get maximumSecurityE2ee => 'Maximale beveiliging (E2EE)';

  @override
  String get instantSpeakerLabels => 'Directe sprekerslabels';

  @override
  String get resetRequestConfig => 'Verzoekconfiguratie resetten naar standaard';

  @override
  String get webhookUrlNotSet => 'Webhook URL niet ingesteld';

  @override
  String get feedbackReasonRecordingOther => 'Iets anders';

  @override
  String get accountCutoverMigrationRollbackMessage =>
      'Je account is in onderhoud na een migratie-rollback. Nieuwere data kan geïsoleerd zijn.';

  @override
  String get cancelConsequenceQuality => '30% lagere transcriptiekwaliteit (modellen op het apparaat)';

  @override
  String get pairingDescPlaudNote =>
      'Houd de zijknop 2 seconden ingedrukt. De rode LED knippert wanneer het klaar is om te koppelen.';

  @override
  String get plansAndBilling => 'Plannen & Facturering';

  @override
  String get deviceOnboardingVoiceReplyTitle => 'Luister naar Omi\'s antwoorden';

  @override
  String get generatingIcon => 'Icoon genereren…';

  @override
  String get cleanUpBannerBody =>
      'Meestal verkeerd verstane namen. Bekijk ze en verwijder de namen die niet echt zijn.';

  @override
  String get speakerTagPromptSavedAsYou => 'Opgeslagen als jij';

  @override
  String get connectOmiOmiGlass => 'Omi / OmiGlass verbinden';

  @override
  String get capabilityConversations => 'Gesprekken';

  @override
  String get notificationFrequencyDescription => 'Bepaal hoe vaak Omi je proactieve meldingen en herinneringen stuurt.';

  @override
  String chatScopeAbout(String title) {
    return 'Over: $title';
  }

  @override
  String get importHistory => 'Importgeschiedenis';

  @override
  String get getApiKey => 'API-sleutel ophalen';

  @override
  String get nothingInterestingRetry => 'Niets interessants gevonden,\nwil je het opnieuw proberen?';

  @override
  String get whatWouldYouLikeToCreate => 'Wat wilt u maken?';

  @override
  String get pricingFree => 'Gratis';

  @override
  String get speakerTagPromptHintIdentify => 'Je antwoord helpt Omi deze stem de volgende keer te herkennen.';

  @override
  String get noConversationsYet => 'Nog geen gesprekken';

  @override
  String get deviceNotMeetRequirements => 'Je apparaat voldoet niet aan de vereisten voor on-device transcriptie.';

  @override
  String get pressKeys => 'Druk op toetsen…';

  @override
  String get downgradeLimitDelayNotRealTime => '5-7 seconden vertraging (niet realtime)';

  @override
  String get conversationLinkCopiedToClipboard => 'Gesprekslink gekopieerd naar klembord';

  @override
  String get onboardingSetupStepMemory => 'Je geheugen wordt ingesteld';

  @override
  String get chatAppsTelegramOtherDevice => 'Telegram op een ander apparaat?';

  @override
  String get appNotFoundOrRemoved => 'Deze app is niet meer beschikbaar';

  @override
  String appsCount(String count) {
    return 'Apps ($count)';
  }

  @override
  String get endToEndEncryption => 'End-to-end-encryptie';

  @override
  String otaConnectFailed(String deviceName) {
    return 'Kan geen verbinding maken met $deviceName. Houd het aan en in de buurt en probeer het opnieuw.';
  }

  @override
  String get continueButton => 'Doorgaan';

  @override
  String get failedToPrepareConversationForSharing => 'Kan gesprek niet voorbereiden om te delen. Probeer het opnieuw.';

  @override
  String get showAll => 'Alles tonen →';

  @override
  String get speakerLabelYou => 'U';

  @override
  String get wrappedActionItems => 'Taken';

  @override
  String failedToInstallApp(String appName) {
    return 'Installatie van $appName mislukt. Probeer het opnieuw.';
  }

  @override
  String get searching => 'Zoeken';

  @override
  String get deviceNotCompatibleTitle => 'Apparaat niet compatibel';

  @override
  String get summarize => 'Samenvatten';

  @override
  String get exportConversationsToJson => 'Gesprekken exporteren naar een JSON-bestand';

  @override
  String makeItemPrivateExplanation(String item) {
    return 'Als u $item nu privé maakt, werkt het voor niemand meer en is het alleen voor u zichtbaar';
  }

  @override
  String get wrappedFailedToShare => 'Delen mislukt. Probeer het opnieuw.';

  @override
  String get cancelSubscriptionConfirmation => 'U behoudt toegang tot het einde van uw huidige factureringsperiode.';

  @override
  String get phoneHideKeypad => 'Toetsenbord verbergen';

  @override
  String get vadGate => 'VAD Gate';

  @override
  String get nameUpdatedSuccessfully => 'Naam succesvol bijgewerkt!';

  @override
  String get photoLibrary => 'Fotobibliotheek';

  @override
  String get chatAppsHeroMessage =>
      'Vraag naar je dag, bewaar herinneringen en beheer taken vanuit Telegram of iMessage. Je chats blijven in de app die je gebruikt, en Omi onthoudt overal waar je het over had.';

  @override
  String get upgradeToAnnualPlan => 'Upgraden naar jaarabonnement';

  @override
  String get completeAuthInBrowser => 'Voltooi de authenticatie in je browser. Keer daarna terug naar de app.';

  @override
  String errorLabel(String error) {
    return 'Fout: $error';
  }

  @override
  String get durationThresholdDesc => 'Gesprekken korter dan dit verbergen';

  @override
  String transcriptionsPendingCount(int count) {
    return 'Transcripties in behandeling $count';
  }

  @override
  String get transcribeLaterNote =>
      'Werkt met de telefoonmicrofoon en met Omi- en Limitless-apparaten. Je audio blijft op je telefoon totdat je hem zelf uploadt.';

  @override
  String get device => 'Apparaat';

  @override
  String get signUpSuccess => 'Registratie gelukt!';

  @override
  String get onboardingPermissions => 'Machtigingen';

  @override
  String get modelTooLargeWarning =>
      'Dit model is groot en kan de app laten crashen of zeer langzaam werken op mobiele apparaten.\n\nsmall of base wordt aanbevolen.';

  @override
  String get showDailyScoreOnHomepage => 'Dagelijkse score weergeven op startpagina';

  @override
  String confidenceSummaryUnverified(String name) {
    return 'Je hebt $name nog niet gelabeld of bevestigd, dus Omi weet niet zeker of het hun stem kent.';
  }

  @override
  String get endConversation => 'Gesprek beëindigen';

  @override
  String get unpinAsBaseline => 'Losmaken van basis';

  @override
  String audioSavedLocally(String duration) {
    return '$duration audio lokaal opgeslagen';
  }

  @override
  String get editMemory => '✏️ Geheugen bewerken';

  @override
  String get speakerTagPromptThanks => 'Bedankt! Omi wordt beter in het herkennen van stemmen.';

  @override
  String get actionItemDescriptionEmpty => 'Taakbeschrijving mag niet leeg zijn.';

  @override
  String get maybeLater => 'Misschien later';

  @override
  String get daySummary => 'Dagsamenvatting';

  @override
  String get confirmReportMessage => 'Dit bericht melden?';

  @override
  String get deleteAllLimitlessConversations => 'Alle Limitless-gesprekken verwijderen?';

  @override
  String get selectAllTasksMenu => 'Alles selecteren';

  @override
  String get syncStatusRetrying => 'Verwerken mislukt — opnieuw proberen';

  @override
  String get exportButton => 'Exporteren';

  @override
  String get wrappedYouTalkedAboutBadge => 'Je praatte over';

  @override
  String get firmwareWarningTitle => 'Belangrijk: Lees voor het updaten';

  @override
  String get permissionTypeCreate => 'Maken';

  @override
  String get viewUsage => 'Bekijk gebruik';

  @override
  String get deviceOnboardingIntroDuration => 'Ongeveer 1 minuut';

  @override
  String get import => 'Importeren';

  @override
  String get conversationsExportStarted => 'Export van gesprekken gestart. Dit kan enkele seconden duren, even geduld.';

  @override
  String get speechToTextProvider => 'Spraak-naar-tekst provider';

  @override
  String get languageTranslation => '100+ taalvertaling';

  @override
  String get primaryLanguage => 'Primaire taal';

  @override
  String durationSeconds(String seconds) {
    return 'Duur: $seconds seconden';
  }

  @override
  String get autoSyncDescription => 'Synchroniseer offline-opnamen automatisch wanneer je apparaat verbinding maakt';

  @override
  String get debugLogs => 'Debuglogboeken';

  @override
  String get authorizationRevoked => 'Autorisatie ingetrokken.';

  @override
  String get noTranscriptAvailable => 'Geen transcript beschikbaar';

  @override
  String get available => 'Beschikbaar';

  @override
  String get wrappedObsessionsLabelUpper => 'OBSESSIES';

  @override
  String get professionStudent => 'Student';

  @override
  String get chatAppsTryRemind => 'Herinner me eraan om zondag mama te bellen';

  @override
  String get failedToStartVerification => 'Kan verificatie niet starten';

  @override
  String get failedToCreateFolder => 'Kan map niet aanmaken';

  @override
  String timeMinSingular(int count) {
    return '$count min';
  }

  @override
  String get insights => 'Inzichten';

  @override
  String get privacyInformation => 'Privacyinformatie';

  @override
  String get finishedConversation => 'Gesprek beëindigd?';

  @override
  String get syncGoogleAccount => 'Synchroniseer met je Google-account';

  @override
  String get pairingTitleNeoOne => 'Zet Neo One in koppelingsmodus';

  @override
  String get translatedByOmi => 'vertaald door Omi';

  @override
  String get githubRepositoryUrl => 'URL van GitHub-repository';

  @override
  String get readOnlyScope => 'Alleen lezen';

  @override
  String get chatAppsChannelsTitle => 'Chat-apps';

  @override
  String get chatAppsDoesAnswer => 'Beantwoordt vragen over je gesprekken en herinneringen';

  @override
  String get wrappedFailedToStartGeneration => 'Starten van generatie mislukt. Probeer het opnieuw.';

  @override
  String get storageLocationSdCard => 'SD-kaart';

  @override
  String get askSuggestDecide => 'Wat heb ik vandaag besloten?';

  @override
  String get close => 'Sluiten';

  @override
  String get paymentMethodPayPal => 'PayPal';

  @override
  String categoryAppCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count apps',
      one: '1 app',
    );
    return '$_temp0';
  }

  @override
  String get speakerTagPromptRecentPeople => 'Mensen met wie je recent hebt gepraat';

  @override
  String get actionCreateMemories => 'Herinneringen aanmaken';

  @override
  String get swipeTasksToIndent => 'Veeg taken om in te springen, sleep tussen categorieën';

  @override
  String get createAccountTitle => 'Account aanmaken';

  @override
  String get modelRequired => 'Model vereist';

  @override
  String get saveMemory => 'Herinnering opslaan';

  @override
  String get successfullyConnectedClickUp => 'Succesvol verbonden met ClickUp!';

  @override
  String get notYetSynced => 'Nog niet gesynchroniseerd met uw telefoon';

  @override
  String get pendantUpToDate => 'Hanger is up-to-date';

  @override
  String get categoryProductivityTools => 'Productiviteitstools';

  @override
  String get refresh => 'Vernieuwen';

  @override
  String get cancelSyncMessage => 'Reeds gedownloade gegevens worden opgeslagen. Je kunt later hervatten.';

  @override
  String get selectImageFileTitle => 'Selecteer een afbeeldingsbestand';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'Fout bij openen bestandskiezer: $message';
  }

  @override
  String get failedToGenerateConversationLink => 'Kan geen gesprekslink genereren';

  @override
  String get voiceFailedToTranscribe => 'Audiotranscriptie mislukt';

  @override
  String get viewAll => 'Alles bekijken';

  @override
  String get yourNewKey => 'Uw nieuwe sleutel:';

  @override
  String get conversationMap => 'Gesprekskaart';

  @override
  String get contactSupportAction => 'Contact opnemen met support';

  @override
  String get weekdaySun => 'Zo';

  @override
  String get summaryNotFound => 'Samenvatting niet gevonden';

  @override
  String get shortConversationThreshold => 'Drempel voor korte gesprekken';

  @override
  String get dailyRecapsDescription => 'Uw dagelijkse samenvattingen verschijnen hier zodra ze zijn gegenereerd';

  @override
  String get phoneCallsWithOmi => 'Bellen met Omi';

  @override
  String get addAppSelectPaymentPlan => 'Selecteer een betalingsplan en voer een prijs in voor uw app';

  @override
  String get deleteAccountFinal =>
      'Deze actie is onomkeerbaar en verwijdert permanent je account en alle bijbehorende gegevens. Weet je zeker dat je wilt doorgaan?';

  @override
  String get gettingAudioFiles => 'Audiobestanden ophalen…';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String get port => 'Poort';

  @override
  String personPinnedToast(String name) {
    return '$name vastgezet';
  }

  @override
  String get wrappedConversations => 'gesprekken';

  @override
  String get availableOnMacMobileWeb => 'Beschikbaar op Mac, mobiel en web';

  @override
  String get monthAug => 'Aug';

  @override
  String get failedToGenerateSummary =>
      'Kon samenvatting niet genereren. Zorg ervoor dat je gesprekken hebt voor die dag.';

  @override
  String planEndedOn(String date) {
    return 'Uw plan eindigde op $date.\nAbonneer nu opnieuw - u wordt direct belast voor een nieuwe factureringsperiode.';
  }

  @override
  String get createAnApp => 'Een app maken';

  @override
  String get cancelling => 'Annuleren…';

  @override
  String get wrappedTopDaysHeader => 'Beste dagen';

  @override
  String get keepEditing => 'Verder bewerken';

  @override
  String get ignoredVoicesEmpty => 'Geen genegeerde stemmen';

  @override
  String get cannotBeUndone => 'Dit kan niet ongedaan worden gemaakt.';

  @override
  String get usersPayToUse => 'Gebruikers betalen om je app te gebruiken';

  @override
  String get maxFilesUploadError => 'U kunt slechts 4 bestanden tegelijk uploaden';

  @override
  String get yourDeviceIsUpToDate => 'Uw apparaat is up-to-date';

  @override
  String get unableToFetchApps =>
      'Kan apps niet ophalen :(\n\nControleer je internetverbinding en probeer het opnieuw.';

  @override
  String get entityCorrectionFailed => 'Je correctie kon niet worden verzonden. Probeer het opnieuw.';

  @override
  String get alreadyAuthorized => 'Al geautoriseerd';

  @override
  String get speedAccuracyLower => 'Snelheid en nauwkeurigheid kunnen lager zijn dan Cloud-modellen.';

  @override
  String siriShortcutsSearchHint(String searchPhrase) {
    return ' Je kunt ook “$searchPhrase for what I did today” zeggen.';
  }

  @override
  String get unlimitedPlan => 'Onbeperkt abonnement';

  @override
  String get contactSupport => 'Contact opnemen met support?';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Maximaal $count doelen toegestaan';
  }

  @override
  String get deviceStorageNearlyFull => 'Apparaat bijna vol — synchroniseer om ruimte vrij te maken.';

  @override
  String get setDueDate => 'Vervaldatum instellen';

  @override
  String privateAppsCount(String count) {
    return 'Privé-apps ($count)';
  }

  @override
  String get selectPeople => 'Mensen selecteren';

  @override
  String get capabilityChat => 'Chat';

  @override
  String chatAppsChannelChats(String app) {
    return '$app-chats';
  }

  @override
  String get transcribeLaterTitle => 'Later transcriberen';

  @override
  String get failedToConnectAsana => 'Verbinding met Asana mislukt';

  @override
  String get youAreOnUnlimitedPlan => 'U bent op het Unlimited-abonnement.';

  @override
  String get chatAppsIncludedWithPro => 'INBEGREPEN BIJ OMI PRO';

  @override
  String get failedToCreateKeyTryAgain => 'Sleutel maken mislukt. Probeer het opnieuw.';

  @override
  String get backgroundModeTitle => 'Achtergrondmodus';

  @override
  String get discardChangesMessage => 'Je niet-opgeslagen wijzigingen gaan verloren.';

  @override
  String get captureSourcePendant => 'Hanger';

  @override
  String get exportTasksWithOneTap => 'Exporteer taken met één tik!';

  @override
  String get sundayAbbr => 'Zo';

  @override
  String get pleaseEnterAppPrompt => 'Voer een prompt in voor uw app';

  @override
  String deviceStoragePercentFull(int percent) {
    return '$percent% vol';
  }

  @override
  String get developerSettings => 'Ontwikkelaarsinstellingen';

  @override
  String get selectYouFromList => 'Om jezelf te taggen, selecteer \"Jij\" uit de lijst.';

  @override
  String get deleteNow => 'Nu verwijderen';

  @override
  String get installUpdate => 'Update installeren';

  @override
  String get unpairDevice => 'Apparaat ontkoppelen';

  @override
  String get assistantVoice => 'Stem van assistent';

  @override
  String get installingApp => 'App installeren…';

  @override
  String get wrappedFunnyMomentTitle => 'Grappig moment';

  @override
  String onboardingFailedCheckNotification(String error) {
    return 'Kan meldingstoestemming niet controleren: $error';
  }

  @override
  String get dreamReportRunNow => 'Nu uitvoeren';

  @override
  String get notSet => 'Niet ingesteld';

  @override
  String get startVoiceRecording => 'Spraakopname starten';

  @override
  String get userInformation => 'Gebruikersinformatie';

  @override
  String get wrappedStruggleLabel => 'UITDAGING';

  @override
  String get filterInteresting => 'Inzichten';

  @override
  String captureRecordingsCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count opnamen',
      one: '1 opname',
    );
    return '$_temp0';
  }

  @override
  String get addOrChangeYourPaymentMethod => 'Betalingsmethode toevoegen of wijzigen';

  @override
  String get unableToLoadApps => 'Kan apps niet laden';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'Er is een nieuwe firmware-update ($version) beschikbaar voor uw Omi-apparaat. Wilt u nu bijwerken?';
  }

  @override
  String get cancelReasonTooExpensive => 'Te duur';

  @override
  String get firmwareUsbWarning => 'USB-verbinding tijdens updates kan uw apparaat beschadigen.';

  @override
  String authAccessMessage(String appName) {
    return 'Je moet Omi autoriseren om toegang te krijgen tot je $appName-gegevens. Dit opent je browser voor authenticatie.';
  }

  @override
  String get conversationEndsManually => 'Het gesprek eindigt alleen handmatig.';

  @override
  String get partialRecording => 'Gedeeltelijke opname';

  @override
  String get dreamReportFeedback => 'Gemeld aan het Omi-team';

  @override
  String get shareAudio => 'Audio delen';

  @override
  String get importDataFromOtherSources => 'Gegevens importeren uit andere bronnen';

  @override
  String get premiumMinutesUsed => 'Premium minuten gebruikt.';

  @override
  String get phoneCallsUpgradeButton => 'Upgraden naar Onbeperkt';

  @override
  String get omiUnlimited => 'Omi Onbeperkt';

  @override
  String get unknownDevice => 'Onbekend';

  @override
  String get failedToStartImport => 'Kan import niet starten. Probeer het opnieuw.';

  @override
  String get searchActionItems => 'Taken zoeken';

  @override
  String get whisperModel => 'Whisper-model';

  @override
  String get searchContacts => 'Contacten zoeken';

  @override
  String get selectAllSkipsPinned =>
      'Alles selecteren slaat vastgezette mensen over. Verwijder ze één voor één vanaf hun pagina.';

  @override
  String get speechProfileIntro => 'Omi moet je doelen en je stem leren. Je kunt het later aanpassen.';

  @override
  String get realtimeListening => 'Realtime luisteren';

  @override
  String get appNotAvailable => 'Oeps! Het lijkt erop dat de app die je zoekt niet beschikbaar is.';

  @override
  String get enterYourName => 'Voer uw naam in';

  @override
  String get permissionTypeTrigger => 'Trigger';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'Uw kennisgrafiek wordt automatisch opgebouwd wanneer u nieuwe herinneringen maakt.';

  @override
  String get chatAppsLink => 'Link';

  @override
  String get minutes => 'minuten';

  @override
  String get actions => 'Acties';

  @override
  String get connectRayBanMeta => 'Ray-Ban Meta verbinden';

  @override
  String get monthSep => 'Sep';

  @override
  String get selectContactsToShareSummary => 'Selecteer contacten om je gesprekssamenvatting te delen';

  @override
  String get paymentNoneSelected => 'Geen geselecteerd';

  @override
  String get pinAction => 'Vastzetten';

  @override
  String get monthOct => 'Okt';

  @override
  String get startRecording => 'Opname starten';

  @override
  String get somethingWentWrong => 'Er is iets misgegaan! Probeer het later opnieuw.';

  @override
  String largeTimeGapsDetected(String gaps) {
    return 'Grote tijdsverschillen gedetecteerd ($gaps)';
  }

  @override
  String get phoneEnterNumber => 'Voer nummer in';

  @override
  String get cancelConsequenceNoAccess => 'Geen onbeperkte toegang meer aan het einde van je factureringsperiode.';

  @override
  String get appleHealthDeniedTitle => 'Apple Health-toegang geweigerd';

  @override
  String deleteItemTitle(String item) {
    return '$item verwijderen';
  }

  @override
  String get invalidIntegrationUrl => 'Ongeldige integratie-URL';

  @override
  String get welcomeActionItemsTitle => 'Klaar voor taken';

  @override
  String get updateAppConfirmation => 'De wijzigingen worden doorgevoerd na beoordeling door ons team.';

  @override
  String get corruptedStatus => 'Beschadigd';

  @override
  String get cantRateWithoutInternet => 'Kan app niet beoordelen zonder internetverbinding.';

  @override
  String get dontShowAgain => 'Niet meer weergeven';

  @override
  String get hardwareRevision => 'Hardwarerevisie';

  @override
  String get trySelectingDifferentDate => 'Probeer een andere datum te selecteren';

  @override
  String get learnings => 'Inzichten';

  @override
  String get failedToConnectTodoist => 'Verbinding met Todoist mislukt';

  @override
  String get accessDataProgrammatically => 'Toegang tot uw gegevens via programmering';

  @override
  String processingProgress(int current, int total) {
    return 'Verwerken $current/$total';
  }

  @override
  String get apiEnvSavedRestartRequired =>
      'Opgeslagen. Sluit de app en open deze opnieuw om de wijzigingen toe te passen.';

  @override
  String get syncCardWaitingInternet => 'Wachten op internet';

  @override
  String get accountCutoverOpenStore => 'Store openen';

  @override
  String get processedConversations => 'Verwerkte gesprekken';

  @override
  String get holdOnPreparingForm => 'Even geduld, we bereiden het formulier voor u voor';

  @override
  String get waitingForDevice => 'Wachten op apparaat…';

  @override
  String get learnMore => 'Meer informatie…';

  @override
  String get aiGenErrorWhileCreatingApp => 'Er is een fout opgetreden bij het aanmaken van de app';

  @override
  String get deleteAllFilesWarning =>
      'Dit verwijdert gesynchroniseerde en wachtende opnames. Wachtende opnames zijn NIET gesynchroniseerd en gaan permanent verloren.';

  @override
  String get usageWordsHeard => 'Words heard';

  @override
  String get importDataDescription => 'Gegevens importeren uit andere bronnen';

  @override
  String get raybanMetaImageCaptureUnavailable => 'Niet beschikbaar in alleen-audiomodus';

  @override
  String get appRejectedMessage => 'Uw app is afgewezen. Werk de gegevens bij en dien opnieuw in ter beoordeling.';

  @override
  String get capturePendantDisconnectedShort => 'Omi maakt vanzelf opnieuw verbinding';

  @override
  String get improveSpeechProfileDesc =>
      'We gebruiken opnames om je persoonlijke spraakprofiel verder te trainen en te verbeteren.';

  @override
  String get voiceResponseModeTitle => 'Wanneer antwoorden worden voorgelezen';

  @override
  String get failedToDeleteItem => 'Kan taak niet verwijderen';

  @override
  String get firmware => 'Firmware';

  @override
  String failedToAddToService(String serviceName) {
    return 'Toevoegen aan $serviceName mislukt';
  }

  @override
  String get askOmiAnything => 'Vraag Omi alles over uw leven';

  @override
  String get integrationsFooter => 'Verbind je apps om gegevens en statistieken in de chat te bekijken.';

  @override
  String get loading => 'Laden…';

  @override
  String get showLess => 'toon minder ↑';

  @override
  String get chatAppsNeverMessagesOthers => 'Stuurt nooit namens jou berichten naar anderen';

  @override
  String get scopeUserName => 'Gebruikersnaam';

  @override
  String get mute => 'Dempen';

  @override
  String get serverProcessesAudio => 'De server verwerkt de audiobestanden en creëert herinneringen';

  @override
  String mergeConversationsSuccessBody(int count) {
    return '$count gesprekken zijn succesvol samengevoegd';
  }

  @override
  String get pairingSuccessful => 'KOPPELEN SUCCESVOL';

  @override
  String get websocketUrl => 'WebSocket-URL';

  @override
  String get wrappedFriend => 'Vriend';

  @override
  String get frequencyHigh => 'Hoog';

  @override
  String get processingFailed => 'Verwerking mislukt';

  @override
  String get dataLowercase => 'gegevens';

  @override
  String deviceOfflineWakeHint(String deviceName) {
    return '$deviceName is offline. Druk op de knop om het te activeren en probeer het opnieuw.';
  }

  @override
  String get updatedConversations => 'Bijgewerkte gesprekken';

  @override
  String get phoneGetStarted => 'Aan de slag';

  @override
  String get recordingDetails => 'Opnamegegevens';

  @override
  String get createApiKey => 'API-sleutel maken';

  @override
  String get anyoneWithLinkCanView => 'Iedereen met de link kan bekijken';

  @override
  String get noPendingTasks => 'Geen openstaande taken';

  @override
  String get featureComingSoon => 'Deze functie komt binnenkort!';

  @override
  String get bluetoothMethodDescription =>
      'Gebruikt standaard Bluetooth Low Energy-verbinding. Langzamer maar beïnvloedt je WiFi-verbinding niet.';

  @override
  String get chatAppsNotConnectedTitle => 'Niet verbonden';

  @override
  String get wrappedMostIntenseDay => 'Meest intens';

  @override
  String get yesterday => 'Gisteren';

  @override
  String get requestConfiguration => 'Verzoek configuratie';

  @override
  String get timeAM => 'AM';

  @override
  String autoRemoveSyncedCopiesDescription(int days) {
    return 'Verwijdert lokale kopieën $days dagen na synchronisatie. Cloudkopieën blijven bewaard.';
  }

  @override
  String get chatAppsTelegramPrivacyNote =>
      'Je chats met Omi worden ook door Telegram opgeslagen. Omi antwoordt alleen jou, nooit andere mensen, en je kunt de verbinding op elk moment verbreken.';

  @override
  String speakerWithId(String speakerId) {
    return 'Spreker $speakerId';
  }

  @override
  String get reviewNoDate => 'Geen';

  @override
  String get transcript => 'Transcriptie';

  @override
  String get deviceDiagnosticsUploadFailed => 'Could not send diagnostics to support. Please try again.';

  @override
  String get noFoldersAvailable => 'Geen mappen beschikbaar';

  @override
  String get addAppSelectCategory => 'Selecteer een categorie voor uw app';

  @override
  String get conversations => 'Gesprekken';

  @override
  String get upgradeToUnlimited => 'Upgraden naar onbeperkt';

  @override
  String get deleteFlowConfirmTitle => 'Je account verwijderen?';

  @override
  String get accountCutoverMigrationInProgressMessage =>
      'Je account wordt gemigreerd. Productfuncties zijn gepauzeerd tot de migratie klaar is.';

  @override
  String get permissionAllowed => 'Toegestaan';

  @override
  String get pressDoneToSave => 'Druk op Klaar om op te slaan';

  @override
  String get listening => 'Luisteren';

  @override
  String get audioReady => 'Audio klaar';

  @override
  String get freeForEveryone => 'Gratis voor iedereen';

  @override
  String get buildingKnowledgeGraphFromMemories => 'Kennisgrafiek opbouwen vanuit herinneringen…';

  @override
  String get onDeviceTranscription => 'On-device transcriptie';

  @override
  String errorWithMessage(String error) {
    return 'Fout: $error';
  }

  @override
  String get chatAppsProblemOffline => 'Je bent offline. Controleer je verbinding en probeer het opnieuw.';

  @override
  String get callAlreadyInProgress => 'Er is al een gesprek gaande';

  @override
  String get reviewQuestionSpelling => 'Hoe schrijf je dit?';

  @override
  String get firmwareStableConnection => 'Stabiele verbinding';

  @override
  String get categoryOther => 'Overig';

  @override
  String get perMonthLabel => '/ maand';

  @override
  String get onboardingYoureAllSet => 'Je bent klaar';

  @override
  String get resumeRecording => 'Opname hervatten';

  @override
  String get feedbackSubtitleAudioQuality => 'We willen graag begrijpen wat er mis ging.';

  @override
  String get speakerTagPromptPlayClip => 'Fragment afspelen';

  @override
  String get anonymityAndPrivacy => 'Anonimiteit en privacy';

  @override
  String get noMemoriesToDelete => 'Geen herinneringen om te verwijderen';

  @override
  String get syncStepProcess => 'Transcriberen';

  @override
  String get callStateRinging => 'Gaat over…';

  @override
  String get setupOnDevice => 'Instellen op apparaat';

  @override
  String get creatorPayouts => 'Uitbetalingen voor makers';

  @override
  String get olderDeviceDetected => 'Ouder apparaat gedetecteerd';

  @override
  String get deletePhoneNumberWarning => 'U moet opnieuw verifieren om te bellen';

  @override
  String get appVisibilityChangedSuccessfully =>
      'Zichtbaarheid van app succesvol gewijzigd. Het kan enkele minuten duren voordat dit zichtbaar is.';

  @override
  String get failedToCreateActionItem => 'Taak aanmaken mislukt';

  @override
  String get msgSelectFilesGenericError => 'Fout bij selecteren van bestanden. Probeer het opnieuw.';

  @override
  String get pendantRecordingSyncBlocked =>
      'Je Pendant is nog aan het opnemen, dus de opgeslagen audio kan niet worden overgezet. Druk op de knop van de Pendant om de opname te stoppen en synchroniseer opnieuw.';

  @override
  String get failedToStartMerge => 'Kan samenvoegen niet starten';

  @override
  String get shortcutChangeInstruction => 'Klik op een sneltoets om deze te wijzigen. Druk op Escape om te annuleren.';

  @override
  String get notificationsAndDisplay => 'Meldingen en weergave';

  @override
  String get getPaidThroughStripe => 'Ontvang betalingen voor uw app-verkopen via Stripe';

  @override
  String get weekdayWed => 'Wo';

  @override
  String get send => 'Verzenden';

  @override
  String get nativeEngineNoDownload =>
      'De native spraakengine van je apparaat wordt gebruikt. Geen model download nodig.';

  @override
  String get wrappedActions => 'acties';

  @override
  String get conversationTimeoutConfig => 'Hoelang Omi in stilte wacht voordat een gesprek eindigt';

  @override
  String get mic => 'Microfoon';

  @override
  String deviceOnboardingVoiceReplyStatusAlwaysHeadphones(String device) {
    return 'Speelt via $device.';
  }

  @override
  String failedToSendReply(String error) {
    return 'Reactie verzenden mislukt: $error';
  }

  @override
  String get whisperModelSizeTiny => 'Heel klein';

  @override
  String get speakerTagPromptNotMeAction => 'Niet ik';

  @override
  String get setupInstructions => 'Installatie-instructies';

  @override
  String get noLanguagesFound => 'Geen talen gevonden';

  @override
  String get experimental => 'Experimenteel';

  @override
  String get continueRecording => 'Opname voortzetten';

  @override
  String get selectDefaultRepoDesc =>
      'Selecteer een standaard repository voor het aanmaken van issues. Je kunt nog steeds een andere repository opgeven bij het aanmaken van issues.';

  @override
  String sharedTasksTitle(String name, int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count taken gedeeld',
      one: '1 taak gedeeld',
    );
    return '$name heeft $_temp0';
  }

  @override
  String get permissionsRequiredDesc =>
      'Deze app heeft Bluetooth- en locatiemachtigingen nodig om correct te functioneren. Schakel deze in via de instellingen.';

  @override
  String diagnosticsVerdictReconnectsDetail(String duration) {
    return 'Korte onderbrekingen, elke keer na ongeveer $duration terug';
  }

  @override
  String get transferring => 'Bezig met overdragen…';

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '$used van $limit woorden gebruikt deze maand';
  }

  @override
  String get noChatAppsEnabled => 'Geen chat-apps ingeschakeld.\nTik op \"Apps inschakelen\" om toe te voegen.';

  @override
  String get tipKeepPhoneNearby => 'Houd uw telefoon dichtbij voor snellere synchronisatie';

  @override
  String get authFailedToSignInWithGoogle => 'Aanmelden met Google mislukt, probeer het opnieuw.';

  @override
  String get frequencyDescLow => 'Alleen belangrijke zaken, ongeveer 3–5 per dag';

  @override
  String get availableTemplates => 'Beschikbare sjablonen';

  @override
  String get captureEveryMoment => 'Omi neemt je gesprekken op en schrijft\nvoor jou de samenvatting en to-do\'s.';

  @override
  String get migrationErrorOccurred => 'Er is een fout opgetreden tijdens de migratie. Probeer opnieuw.';

  @override
  String get wrappedCompletedLabel => 'Voltooid';

  @override
  String speakerTagPromptLabeledToast(String name) {
    return 'Gelabeld als $name';
  }

  @override
  String get docs => 'Documentatie';

  @override
  String get dateTimeLabel => 'Datum & Tijd';

  @override
  String get editFolder => 'Map bewerken';

  @override
  String get apps => 'Apps';

  @override
  String segmentsSingular(String count) {
    return '$count segment';
  }

  @override
  String get deviceSettings => 'Apparaatinstellingen';

  @override
  String get offline => 'Offline';

  @override
  String get createActionItemTooltip => 'Nieuwe taak maken';

  @override
  String get forgetDevice => 'Apparaat vergeten';

  @override
  String get reviewEntryTitle => 'Vragen voor jou';

  @override
  String get enterEmailError => 'Voer uw e-mailadres in';

  @override
  String get appDisabledOwnerHint =>
      'Repareer eerst het endpoint — bij het opnieuw inschakelen wordt elke ingestelde URL opnieuw gecontroleerd.';

  @override
  String get chatAppsIMessageSubtitle => 'Stuur Omi een bericht vanaf je telefoonnummer';

  @override
  String get tasksExportedOneApp => 'Taken kunnen naar één app tegelijk worden geëxporteerd.';

  @override
  String transcriptSpeakerCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count sprekers',
      one: '1 spreker',
    );
    return '$_temp0';
  }

  @override
  String get saveGoal => 'Opslaan';

  @override
  String get noBatteryDataYet => 'Nog geen batterijgegevens';

  @override
  String chatUsedOfLimitMessages(String used, String limit) {
    return '$used van $limit berichten gebruikt deze maand';
  }

  @override
  String get backgroundActivityDesc => 'Zodat Omi blijft opnemen als het scherm uit is of je van app wisselt.';

  @override
  String get addAppUpdateFailed => 'Bijwerken mislukt. Probeer het later opnieuw';

  @override
  String get noMatchingPeople => 'Geen Overeenkomende Personen';

  @override
  String get unlinkCalendarEvent => 'Afspraak ontkoppelen';

  @override
  String get regenerateRecap => 'Samenvatting opnieuw genereren';

  @override
  String get deleteSynced => 'Gesynchroniseerde verwijderen';

  @override
  String get speakerTagPromptNameHint => 'Naam';

  @override
  String get freePlan => 'Gratis abonnement';

  @override
  String get installs => 'INSTALLATIES';

  @override
  String get publicLabel => 'Openbaar';

  @override
  String get deletingMessages => 'Uw berichten verwijderen uit het geheugen van Omi…';

  @override
  String get pendingFilesDeleted => 'Wachtende opnames verwijderd';

  @override
  String get checkUsage => 'Verbruik controleren';

  @override
  String get addWordsDesc => 'Namen, termen of ongewone woorden';

  @override
  String get entityCorrectionSaved => 'Bedankt. Omi past het aan.';

  @override
  String get categoryEducation => 'Onderwijs';

  @override
  String get planAndUsage => 'Abonnement en gebruik';

  @override
  String get deleteMemory => 'Geheugen verwijderen';

  @override
  String get dataProtectionLevel => 'Gegevensbeschermingsniveau';

  @override
  String timeDaySingular(int count) {
    return '$count dag';
  }

  @override
  String get keyCreated => 'Sleutel aangemaakt';

  @override
  String get date => 'Datum';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return '$itemType migreren… $percentage%';
  }

  @override
  String get enableLocalStorage => 'Lokale opslag inschakelen';

  @override
  String get omiSays => 'Omi zegt';

  @override
  String get appDetails => 'App-gegevens';

  @override
  String get loadingYourRecording => 'Uw opname laden…';

  @override
  String get deleteAllLimitlessWarning =>
      'Alle gesprekken die uit Limitless zijn geïmporteerd, worden verwijderd. Dit kan niet ongedaan worden gemaakt.';

  @override
  String get combiningAudioFiles => 'Audiobestanden combineren…';

  @override
  String get suggestFollowUpQuestion => 'Vervolgvraag voorstellen';

  @override
  String chatStarterPrompt(String kind) {
    String _temp0 = intl.Intl.selectLogic(
      kind,
      {
        'capabilities': 'Wat kun je voor me doen?',
        'goal': 'Help me een doel te stellen',
        'activity': 'Vat mijn recente activiteiten samen',
        'improve': 'Hoe kan ik me verbeteren?',
        'other': '',
      },
    );
    return '$_temp0';
  }

  @override
  String get speakerTagPromptIgnoredNote => 'Omi vraagt niet meer naar deze stem';

  @override
  String get recordWithPhoneInstead => 'In plaats daarvan met telefoon opnemen';

  @override
  String get triggerEvent => 'Triggergebeurtenis';

  @override
  String get waitingForTranscriptOrPhotos => 'Wachten op transcriptie of foto\'s…';

  @override
  String get omiApiKeys => 'Omi API-sleutels';

  @override
  String addNamedPersonAction(String name) {
    return 'Voeg “$name” toe';
  }

  @override
  String get enableDetailedDiagnosticMessages =>
      'Gedetailleerde diagnostische berichten van de transcriptieservice inschakelen';

  @override
  String get nameCannotBeEmpty => 'Naam mag niet leeg zijn';

  @override
  String get noTasksYet => 'Nog geen taken';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'Probeer je zoektermen of filters aan te passen';

  @override
  String daySummaryForDate(String date) {
    return 'Dagoverzicht · $date';
  }

  @override
  String get statusTimedOut => 'Tijd verstreken';

  @override
  String chatUsageDescription(String used, String limitDisplay, String plan) {
    return 'Je hebt $used van je $limitDisplay op het $plan-plan gebruikt.';
  }

  @override
  String get paypalMeLink => 'PayPal.me-link';

  @override
  String get allMemoriesPrivateResult => 'Alle herinneringen zijn nu privé';

  @override
  String get scanAgain => 'Opnieuw zoeken';

  @override
  String get doItAgain => 'Opnieuw doen';

  @override
  String get reviewTitle => 'Beoordeling';

  @override
  String get photos => 'Foto\'s';

  @override
  String get phoneNoVerifiedNumbersMessage => 'Verifieer je nummer om via Omi te bellen.';

  @override
  String get save => 'Opslaan';

  @override
  String get deleteAccount => 'Account Verwijderen';

  @override
  String get managePaymentMethod => 'Betalingsmethode beheren';

  @override
  String get selectThumbnailImageTitle => 'Selecteer een miniatuurafbeelding';

  @override
  String get pairingTitleOmi => 'Zet Omi aan';

  @override
  String get whatsYourPrimaryLanguage => 'Wat is je primaire taal?';

  @override
  String get replyToReview => 'Reageer op review';

  @override
  String failedToDeleteError(String error) {
    return 'Verwijderen mislukt: $error';
  }

  @override
  String get newestFirst => 'Nieuwste eerst';

  @override
  String get wrappedCreatingYourStory => 'Je 2025\nverhaal maken…';

  @override
  String get chatAppsPrivateMemories => 'Houd privéherinneringen in de app';

  @override
  String get pleaseEnterPayPalEmail => 'Voer uw PayPal-e-mailadres in';

  @override
  String get transcription => 'Transcriptie';

  @override
  String get yourReview => 'Uw beoordeling';

  @override
  String get filesDownloadedUploadedNextTime => 'Reeds gedownloade bestanden worden de volgende keer geüpload.';

  @override
  String get phoneSetupStep3Subtitle => 'Met ingebouwde live transcriptie';

  @override
  String get mcpConnectionFailed => 'Kan geen verbinding maken met MCP-server';

  @override
  String get chatAppsConnectTelegramTitle => 'Telegram verbinden';

  @override
  String get createMemoryTooltip => 'Nieuwe herinnering maken';

  @override
  String get connectDeviceMessage =>
      'Verbind je Omi-apparaat om toegang te krijgen tot\napparaatinstellingen en aanpassingen';

  @override
  String get authorizingMcpServer => 'Autoriseren…';

  @override
  String charactersCount(int count) {
    return '$count tekens';
  }

  @override
  String get syncStatusUploaded => 'Geüpload · wordt verwerkt op Omi';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'Authenticeer a.u.b. met $serviceName in Instellingen > Taakintegraties';
  }

  @override
  String get setDefaultButton => 'Als standaard instellen';

  @override
  String get resummarizingConversation => 'Gesprek opnieuw samenvatten…\nDit kan enkele seconden duren';

  @override
  String estimatedHours(int count) {
    return '~$count uur';
  }

  @override
  String get chatAppsInsightsSubtitle => 'Laat Omi je hier een samenvatting of inzicht sturen.';

  @override
  String get memoryAllowUse => 'Gebruik toestaan';

  @override
  String get model => 'Model';

  @override
  String get memoryGraphTitle => 'Herinneringsgrafiek';

  @override
  String get endpointURL => 'Eindpunt-URL';

  @override
  String get wrappedShareYourWrapped => 'Deel je Wrapped';

  @override
  String get micGainDescBoosted => 'Versterkt - voor stille omgevingen';

  @override
  String get wrappedMinutes => 'minuten';

  @override
  String get language => 'Taal';

  @override
  String downloadErrorWithMessage(String error) {
    return 'Downloadfout: $error';
  }

  @override
  String get onboardingRatingPromptNo => 'Nee';

  @override
  String get whatWouldYouLikeToRemember => 'Wat wil je onthouden?';

  @override
  String get deviceOnboardingMuteUnmuteDesc => 'Microfoon aan- of uitzetten';

  @override
  String secondsCount(int count) {
    return '$count seconden';
  }

  @override
  String get icon => 'Pictogram';

  @override
  String get realTimeTranscript => 'Realtime transcriptie';

  @override
  String get deviceOnboardingVoiceReplySample => 'Begrepen. Je volgende vergadering begint over twintig minuten.';

  @override
  String get noDisconnectsRecorded => 'Geen ontkoppelingen geregistreerd';

  @override
  String get filterMyApps => 'Mijn apps';

  @override
  String get recapRegenerateCooldown => 'Wacht een paar seconden voordat je opnieuw genereert.';

  @override
  String get templateName => 'Sjabloonnaam';

  @override
  String get retry => 'Opnieuw proberen';

  @override
  String get sdCardSyncDescription => 'SD-kaartsynchronisatie importeert je herinneringen van de SD-kaart naar de app';

  @override
  String get deviceTutorial => 'Hoe je Omi gebruikt';

  @override
  String get noApiKeysCreateOne => 'Geen API-sleutels. Maak er een aan om te beginnen.';

  @override
  String siriShortcutsSetupHint(String askPhrase, String questionPhrase) {
    return 'Zet Omi aan in Sneltoetsen → Siri. Zeg “$askPhrase” of “$questionPhrase” en stel daarna je vraag.';
  }

  @override
  String get failedToDeleteSomeItems => 'Kan sommige items niet verwijderen';

  @override
  String get raybanMetaSetupDescription =>
      'Gebruik je Ray-Ban Meta-bril als je Omi-opnameapparaat voor gesprekken en visuele context. Omi opent de Meta AI-app om je bril te koppelen.';

  @override
  String get tabToDo => 'Te doen';

  @override
  String get otaWifiFailed => 'Kan geen verbinding maken met wifi. Controleer de netwerknaam en het wachtwoord.';

  @override
  String get changePlan => 'Plan wijzigen';

  @override
  String copiedToClipboard(String title) {
    return '$title gekopieerd naar klembord';
  }

  @override
  String get completeAuthBrowser => 'Voltooi de authenticatie in je browser. Keer daarna terug naar de app.';

  @override
  String get migrationInProgressMessage =>
      'Migratie bezig. U kunt het beveiligingsniveau niet wijzigen totdat deze is voltooid.';

  @override
  String get keepSubscription => 'Abonnement behouden';

  @override
  String get playbackPreparingAudio => 'Audio wordt voorbereid…';

  @override
  String get cloudStorageDialogMessage =>
      'Uw realtime opnames worden opgeslagen in privé cloudopslag terwijl u spreekt.';

  @override
  String get newChat => 'Nieuwe chat';

  @override
  String get paymentEnterAmountGreaterThanZero => 'Voer een bedrag groter dan 0 in';

  @override
  String showAllPeople(int count) {
    return 'Alle $count personen weergeven';
  }

  @override
  String deletePersonNamedTitle(String name) {
    return '$name verwijderen?';
  }

  @override
  String get importTranscriptFiles => 'Transcriptiebestanden';

  @override
  String get transcriptPlaceholder => 'Transcriptie verschijnt hier…';

  @override
  String get logShared => 'Log gedeeld';

  @override
  String get deleteReasonNotUsing => 'Ik gebruik het niet genoeg';

  @override
  String diagnosticsDropsPerHour(int count) {
    return 'ongeveer $count per uur';
  }

  @override
  String get wrappedProcessingDefault => 'Verwerken…';

  @override
  String get failedToConnectGoogleTasksRetry => 'Verbinding met Google Tasks mislukt. Probeer het opnieuw.';

  @override
  String get downloadingFromSdCard => 'Downloaden van SD-kaart';

  @override
  String get firmwareFormatWarning =>
      'Deze firmware zal de SD-kaart formatteren. Zorg ervoor dat alle offline gegevens gesynchroniseerd zijn voor de upgrade.\n\nAls u na het installeren van deze versie een knipperend rood lampje ziet, maak u geen zorgen. Verbind het apparaat gewoon met de app en het zou blauw moeten worden. Het rode lampje betekent dat de klok van het apparaat nog niet is gesynchroniseerd.';

  @override
  String get pleaseProvidePrompt => 'Geef een prompt op';

  @override
  String get voiceResponseAlways => 'Altijd';

  @override
  String get statusLabel => 'Status';

  @override
  String get shareLogs => 'Logboeken delen';

  @override
  String get continueAnyway => 'Doorgaan';

  @override
  String get transferCompleteMessage => 'Overdracht voltooid! Je kunt deze opname nu afspelen.';

  @override
  String get reviewCaughtUpBody => 'Omi vraagt hier alleen iets als het je nodig heeft.';

  @override
  String get calculatingETA => 'Berekenen…';

  @override
  String get speechProfileTopicWork => 'Wat doe je voor werk?';

  @override
  String get considerOmiCloud => 'Overweeg Omi Cloud te gebruiken voor betere prestaties.';

  @override
  String get testConversationPrompt => 'Test een gespreks-prompt';

  @override
  String get deletePending => 'Wachtende verwijderen';

  @override
  String get renameConversation => 'Naam wijzigen';

  @override
  String get batteryDrainSignificantly => 'Batterijverbruik zal aanzienlijk toenemen.';

  @override
  String get clear => 'Wissen';

  @override
  String get addAppEnterWebhookUrl => 'Voer een webhook-URL in voor uw app';

  @override
  String get active => 'Actief';

  @override
  String get exportStartedMessage => 'Export gestart. Dit kan enkele seconden duren…';

  @override
  String get dataAccessNoticeDescription =>
      'Deze app krijgt toegang tot je gegevens. Omi AI is niet verantwoordelijk voor hoe je gegevens worden gebruikt, gewijzigd of verwijderd door deze app';

  @override
  String get yourRequestUnderReview => 'Je aanvraag wordt beoordeeld';

  @override
  String get unresolvedSpeakersMessage =>
      'Omi kon de andere stemmen niet uit elkaar houden over opnames heen. Tik op een sprekerlabel om te benoemen wie er spreekt.';

  @override
  String downloadError(String error) {
    return 'Downloadfout: $error';
  }

  @override
  String get offlineSync => 'Offline synchronisatie';

  @override
  String get cancelSubscription => 'Abonnement opzeggen';

  @override
  String get claudeDesktopConnectorSetup =>
      'Voeg op Claude Desktop → Settings → Connectors een aangepaste connector toe en plak de server-URL. Als Claude om een geavanceerde OAuth Client ID vraagt, gebruik dan de waarde hieronder en laat het geheim leeg — gebruik je MCP API-sleutel nooit als OAuth-geheim.';

  @override
  String get chatAppsTelegramWaiting => 'Wachten tot je in Telegram op Start tikt…';

  @override
  String get tryAgain => 'Opnieuw proberen';

  @override
  String get syncStatusOnDevice => 'Op je apparaat';

  @override
  String get entityCorrectionTitle => 'Wat klopt er niet?';

  @override
  String peopleDeletedToast(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count mensen verwijderd',
      one: '1 persoon verwijderd',
    );
    return '$_temp0';
  }

  @override
  String get features => 'Functies';

  @override
  String get startEarning => 'Begin met verdienen! 💰';

  @override
  String get enterYourNumber => 'Voer uw nummer in';

  @override
  String get addToClaudeCodeConfig => 'Toevoegen aan ~/.claude.json';

  @override
  String get cleanDisconnect => 'Schone ontkoppeling';

  @override
  String get grantContactsAccess => 'Geef toegang tot uw contacten';

  @override
  String get feedbackReasonIncorrect => 'Onjuist of verzonnen';

  @override
  String get addAppErrorSelectingImageRetry => 'Fout bij selecteren afbeelding. Probeer opnieuw.';

  @override
  String get feedbackTitleNotUsing => 'Wat zou je Omi meer laten gebruiken?';

  @override
  String get memories => 'Herinneringen';

  @override
  String get capturingPhotos => 'Foto\'s vastleggen';

  @override
  String get hideApiKey => 'API-sleutel verbergen';

  @override
  String get signUpButton => 'Registreren';

  @override
  String get tuesdayAbbr => 'Di';

  @override
  String get noApiKeys => 'Nog geen API-sleutels';

  @override
  String get keyWord => 'Sleutel';

  @override
  String reviewAnswersConversations(int count) {
    return 'Dit antwoord labelt $count gesprekken';
  }

  @override
  String get statusFailed => 'Mislukt';

  @override
  String get installedApps => 'Geïnstalleerde apps';

  @override
  String get flashFirmware => 'Firmware flashen';

  @override
  String get conversationUrlCouldNotBeGenerated => 'Gesprek-URL kon niet worden gegenereerd.';

  @override
  String get reloadingApps => 'Apps opnieuw laden…';

  @override
  String get goalTitle => 'Doeltitel';

  @override
  String get importantConversationTitle => 'Belangrijk gesprek';

  @override
  String get byContinuingAgree => 'Door verder te gaan, ga je akkoord met ons ';

  @override
  String get saturdayAbbr => 'Za';

  @override
  String get subscriptionReactivatedDefault =>
      'Je abonnement is opnieuw geactiveerd! Geen kosten nu - je wordt gefactureerd aan het einde van je huidige periode.';

  @override
  String get tryLatestExperimentalFeatures => 'Probeer de nieuwste experimentele functies van het Omi-team.';

  @override
  String get chatAppsEntrySubtitle => 'Praat met Omi in de apps die je elke dag al gebruikt.';

  @override
  String get transcriptionPaused => 'Opname, opnieuw verbinden';

  @override
  String get appleHealthFeatureReadOnlyTitle => 'Alleen-lezen toegang';

  @override
  String get shareDataForTraining => 'Gegevens delen voor training';

  @override
  String get noNotificationScopesAvailable => 'Geen meldingsbereiken beschikbaar';

  @override
  String disconnectFromApp(String appName) {
    return 'Loskoppelen van $appName?';
  }

  @override
  String get failedToConnectGoogleTasks => 'Verbinding met Google Tasks mislukt';

  @override
  String get copyToClipboard => 'Kopiëren naar klembord';

  @override
  String get stopRecordingConfirmation => 'Opname stoppen en het gesprek nu samenvatten?';

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'Kon samenvatting niet genereren. Zorg ervoor dat u gesprekken heeft voor die dag.';

  @override
  String get monthlyLimitReached => 'Je hebt je maandelijkse limiet bereikt.';

  @override
  String get permissionsPageDescription =>
      'Omi gebruikt deze om verbinding te maken met je apparaat, audio op te nemen, op de achtergrond te blijven werken, herinneringen te sturen en bij te houden waar gesprekken plaatsvonden.';

  @override
  String get onboardingTellUsAboutYourself => 'Vertel ons over jezelf';

  @override
  String get deviceOnboardingAskQuestionSubtitle =>
      'Druk eenmaal op de knop, stel je vraag en druk nogmaals als je klaar bent';

  @override
  String get filters => 'Filters';

  @override
  String get firmwareUpdateWarning =>
      'Sluit de app niet en schakel het apparaat niet uit. Dit kan uw apparaat beschadigen.';

  @override
  String get oneSourceAtATime => 'Omi neemt steeds van één bron tegelijk op.';

  @override
  String chatAppsConnectedAs(String handle) {
    return 'Verbonden als $handle';
  }

  @override
  String get pilotFeatures => 'Pilotfuncties';

  @override
  String get selectFirmwareZip => 'Selecteer het firmware-ZIP-bestand';

  @override
  String get feedbackReasonRecordingPoorTranscription => 'Slechte transcriptie';

  @override
  String get deleteAccountFailed => 'Je account kon niet worden verwijderd. Probeer het opnieuw.';

  @override
  String get searchConversations => 'Zoek gesprekken';

  @override
  String get frequencyBalanced => 'Gebalanceerd';

  @override
  String get auto => 'Automatisch';

  @override
  String get actionItemUpdatedSuccessfully => 'Taak succesvol bijgewerkt';

  @override
  String get entityProjects => 'Projecten';

  @override
  String get signInWithApple => 'Inloggen met Apple';

  @override
  String get backendUrlLabel => 'Backend-URL';

  @override
  String confidenceSummaryLikely(String name) {
    return 'Omi herkent de stem van $name meestal, maar je hebt het maar een paar keer bevestigd.';
  }

  @override
  String get entityOpenThreads => 'Open onderwerpen';

  @override
  String get deleteActionItemMessage => 'Deze taak verwijderen?';

  @override
  String chatWithApp(String appName) {
    return 'Chatten met $appName';
  }

  @override
  String get editActionItem => 'Taak bewerken';

  @override
  String get cloudStorageEnabled => 'Cloudopslag ingeschakeld';

  @override
  String get wrappedPersonalGrowth => 'Persoonlijke groei';

  @override
  String get chatAppsProPerkSave => 'Bewaar herinneringen en beheer taken direct vanuit de chat';

  @override
  String get alreadyHaveAccountLogin => 'Heeft u al een account? Log in';

  @override
  String makeItemPublicQuestion(String item) {
    return '$item openbaar maken?';
  }

  @override
  String get usagePeakHour => 'Peak hour';

  @override
  String get addWords => 'Woorden toevoegen';

  @override
  String get usageNow => 'now';

  @override
  String get usageMinutes => 'minuten';

  @override
  String availableSpace(String space) {
    return 'Beschikbare ruimte: $space';
  }

  @override
  String get providingSubtitle => 'Taken en notities, automatisch vastgelegd.';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% voltooiingspercentage';
  }

  @override
  String summaryGeneratedFor(String date) {
    return 'Samenvatting gegenereerd voor $date';
  }

  @override
  String get selectCategory => 'Selecteer categorie';

  @override
  String nProcessed(int count) {
    return '$count verwerkt';
  }

  @override
  String get privacyPolicyTitle => 'Privacybeleid';

  @override
  String get deviceMayWarmUp => 'Apparaat kan warm worden tijdens langdurig gebruik.';

  @override
  String get designingApp => 'App ontwerpen';

  @override
  String get couldNotLoadWhatsNew => 'Kan de nieuwe functies niet laden';

  @override
  String get doNotCloseApp => 'Sluit de app niet.';

  @override
  String get voiceResponseAudio => 'Lees Omi\'s antwoord voor';

  @override
  String get allTime => 'Altijd';

  @override
  String get developerSettingsTitle => 'Ontwikkelaarsinstellingen';

  @override
  String get restoreAction => 'Herstellen';

  @override
  String get phoneSetupStep3Title => 'Begin uw contacten te bellen';

  @override
  String get anErrorOccurredTryAgain => 'Er is een fout opgetreden. Probeer het opnieuw.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'Hier is waar we net over spraken: $link';
  }

  @override
  String get playbackAudioLoadFailed => 'Audio kon niet worden geladen';

  @override
  String get phoneMute => 'Dempen';

  @override
  String get captureNotTranscribing => 'Geen transcriptie';

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return 'Opname gestopt: $reason. Mogelijk moet u externe beeldschermen opnieuw aansluiten of de opname opnieuw starten.';
  }

  @override
  String get sttProviderDeepgram => 'Deepgram';

  @override
  String get spaceKey => 'Spatie';

  @override
  String get raybanMetaOpenMetaAI => 'Verbinden via Meta AI';

  @override
  String get linkEvent => 'Afspraak koppelen';

  @override
  String get fairUse3Day => '3-daags voortschrijdend';

  @override
  String failedToStartAppAuth(String appName) {
    return 'Kan $appName-authenticatie niet starten';
  }

  @override
  String get processingOnServer => 'Verwerken op de server…';

  @override
  String errorStartingRecording(String error) {
    return 'Fout bij het starten van opname: $error';
  }

  @override
  String get quiet => 'Stil';

  @override
  String get startConversationToSeeInsights => 'Start een gesprek met Omi\nom je gebruiksinzichten hier te zien.';

  @override
  String get processAudio => 'Audio verwerken';

  @override
  String get chatAppsConnectIMessageTitle => 'Stuur Omi een bericht om te verbinden';

  @override
  String get chatWithOmi => 'Chat met Omi';

  @override
  String get clickToBeginRecording => 'Klik om opname te starten';

  @override
  String get confirmAndProceed => 'Bevestigen en doorgaan';

  @override
  String get mondayAbbr => 'Ma';

  @override
  String sdCardProcessingMessage(int count) {
    return '$count opname(s) verwerken. Bestanden worden na verwerking van de SD-kaart verwijderd.';
  }

  @override
  String get chatReplyNotSignedIn => 'Je bent niet ingelogd. Log in en probeer het opnieuw.';

  @override
  String deviceOnboardingVoiceReplySettingsHint(String settings, String voiceResponse) {
    return 'Je kunt dit op elk moment wijzigen via $settings ›$voiceResponse';
  }

  @override
  String get wrappedGenerateMyWrapped => 'Genereer mijn Wrapped';

  @override
  String get reviewChangesIntro =>
      'Wat Omi de afgelopen 30 dagen zelf heeft gewijzigd. Maak alles ongedaan wat niet klopt.';

  @override
  String get stripeReadyForPayments =>
      'Uw Stripe-account is nu klaar om betalingen te ontvangen. U kunt direct beginnen met verdienen aan uw app-verkopen.';

  @override
  String get appleWatchSetup => 'Apple Watch instellen';

  @override
  String get failedToDisconnect => 'Loskoppelen mislukt';

  @override
  String get localStorageEnabled => 'Lokale opslag ingeschakeld';

  @override
  String get captureSourceDesktop => 'Computer';

  @override
  String get serialNumber => 'Serienummer';

  @override
  String get appleHealthFeatureSecureDesc => 'Je Apple Health-gegevens synchroniseren privé naar je Omi-account.';

  @override
  String get tryAdjustingSearch => 'Probeer je zoekopdracht of filters aan te passen';

  @override
  String connectTo(String appName) {
    return 'Verbinden met $appName';
  }

  @override
  String get exportConversationsDescription => 'Gesprekken exporteren naar JSON';

  @override
  String get featuredLabel => 'UITGELICHT';

  @override
  String get speechProfile => 'Stemprofiel';

  @override
  String get integrations => 'Integraties';

  @override
  String get hideCompletedTasks => 'Voltooide verbergen';

  @override
  String get sendRawAudioToOmi => 'Onbewerkte audio naar Omi sturen';

  @override
  String ratingsCount(String count) {
    return '$count+ beoordelingen';
  }

  @override
  String get exportShared => 'Export gedeeld';

  @override
  String get conversationTimeout => 'Gesprekstime-out';

  @override
  String get installStableFirmware => 'Stabiele firmware installeren';

  @override
  String get secureAndReliable => 'Veilig en betrouwbaar';

  @override
  String get exportingConversations => 'Gesprekken exporteren…';

  @override
  String get feedbackReasonRecordingFragmentedOrDuplicated => 'Gefragmenteerd of gedupliceerd';

  @override
  String get chatAppsWaitingMessage =>
      'Stuur het bericht in Berichten. Dit scherm wordt bijgewerkt zodra Omi het ontvangt.';

  @override
  String get onboardingSetupStepWorkspace => 'Je werkruimte wordt voorbereid';

  @override
  String get recap => 'Samenvatting';

  @override
  String get lessThanAMinute => 'Minder dan een minuut';

  @override
  String get tasks => 'Taken';

  @override
  String get onboardingSetupStepDevices => 'Je apparaten worden verbonden';

  @override
  String pinPersonTitle(String name) {
    return '$name vastzetten';
  }

  @override
  String get wrappedButYouPushedThrough => 'Maar je hebt het gehaald 💪';

  @override
  String get fetchingYourAppDetails => 'App-details ophalen';

  @override
  String get timeout2MinutesDesc => 'Gesprek beëindigen na 2 minuten stilte';

  @override
  String get otaUpdateCancelled => 'Update geannuleerd';

  @override
  String get usageTasksNotes => 'Tasks & notes';

  @override
  String get deviceNotConnected => 'Apparaat niet verbonden';

  @override
  String get rayBanMetaMicPickerEmpty =>
      'Geen Bluetooth-microfoons gevonden. Verbind je bril in de iPhone-instellingen en probeer het opnieuw.';

  @override
  String get actionItemCompleted => 'Taak voltooid';

  @override
  String get usageSocialSettings => 'In sociale omgevingen';

  @override
  String get from => 'van';

  @override
  String get siriIndexSetting => 'Use Omi with Siri & Apple Intelligence';

  @override
  String get reviewReasonNotMine => 'Niet van mij';

  @override
  String connectToDeviceName(String deviceName) {
    return 'Verbinden met $deviceName';
  }

  @override
  String get onboardingComplete => 'Voltooid';

  @override
  String get chatAppsShowInApp => 'Toon deze chats in de Omi-app';

  @override
  String nCompleted(int count) {
    return '$count voltooid';
  }

  @override
  String get feedbackAllGood => 'Alles goed';

  @override
  String get syncCardUploadingTitle => 'Uploaden naar Omi';

  @override
  String get baselineMemory => 'Basisherinnering';

  @override
  String get trainFamilyProfilesDesc =>
      'Je opnames helpen ons om profielen voor je vrienden en familie te herkennen en aan te maken.';

  @override
  String get failedToGenerateShareLink => 'Kan geen deellink genereren';

  @override
  String get onlyYouCanSeeConversation => 'Alleen jij kunt dit gesprek zien';

  @override
  String get popular => 'Populair';

  @override
  String get captureRecordingSeparate => 'Scheiden…';

  @override
  String get allTemplates => 'Alle sjablonen';

  @override
  String devicesFoundNearby(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'APPARATEN',
      one: 'APPARAAT',
    );
    return '$count $_temp0 GEVONDEN IN DE BUURT';
  }

  @override
  String speakerTagPromptSavedAs(String name) {
    return 'Opgeslagen als $name';
  }

  @override
  String get configureSettings => 'Instellingen configureren';

  @override
  String get noRatings => 'geen beoordelingen';

  @override
  String resumingInCountdown(String countdown) {
    return 'Hervatten over ${countdown}s…';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 $count herinneringen onthouden';
  }

  @override
  String get clearDueDate => 'Vervaldatum wissen';

  @override
  String get copy => 'Kopiëren';

  @override
  String get showPhoneCallButtonDesc => 'Toon de telefoonbelknop op het startscherm';

  @override
  String get appleHealthFeatureReadOnlyDesc => 'Omi schrijft nooit naar Apple Health en wijzigt je gegevens niet.';

  @override
  String get multipleSpeakersDescription =>
      'Het lijkt erop dat er meerdere sprekers in de opname zijn. Zorg ervoor dat je op een rustige plek bent en probeer het opnieuw.';

  @override
  String get failedToUpdateDueDate => 'Kan vervaldatum niet bijwerken';

  @override
  String get successfullyConnectedWhoop => 'Succesvol verbonden met Whoop!';

  @override
  String get categories => 'Categorieën';

  @override
  String get loadingTranscript => 'Transcript laden…';

  @override
  String get syncCustomSttWarningMessage =>
      'Je gebruikt je eigen transcriptieprovider. Door deze opnames te synchroniseren worden ze op de servers van Omi getranscribeerd en tellen ze mee voor de transcriptielimiet van je abonnement.';

  @override
  String get newRecording => 'Nieuwe opname';

  @override
  String get transcriptionUnavailableRecordingSaved =>
      'Transcriptie is niet beschikbaar — de opname gaat door en je audio wordt bewaard.';

  @override
  String get submittingYourApp => 'Je app wordt ingediend…';

  @override
  String get failedToLinkCalendarEvent => 'Koppelen van agenda-item mislukt';

  @override
  String get paypalMeLinkHint => 'paypal.me/nik';

  @override
  String get yourInformation => 'Uw Informatie';

  @override
  String get accountDeletionInProgressSignInAgain =>
      'Dit account wordt verwijderd. Log in met een ander account, of wacht een paar minuten en probeer het opnieuw.';

  @override
  String get on => 'Aan';

  @override
  String get diagnostics => 'Diagnostiek';

  @override
  String get errorCopied => 'Foutmelding gekopieerd naar klembord';

  @override
  String get lovingOmi => 'Ben je blij met Omi?';

  @override
  String get permissionDescReadMemories => 'Deze app heeft toegang tot je herinneringen.';

  @override
  String get doNotIncludeHttpInLink => 'Neem geen http, https of www op in de link';

  @override
  String get shareRecording => 'Opname delen';

  @override
  String get memoryReviewFix => 'Corrigeren';

  @override
  String get selectedPlanNotAvailable => 'Geselecteerd abonnement is niet beschikbaar. Probeer het opnieuw.';

  @override
  String get autoCreateWhenDetected => 'Automatisch aanmaken wanneer naam wordt gedetecteerd';

  @override
  String get addAppSelectCapability => 'Selecteer minstens één functie voor uw app';

  @override
  String get showPassword => 'Wachtwoord tonen';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Gesprekken eindigen nu na $minutes minuut/minuten stilte';
  }

  @override
  String get updateAvailableMessage => 'Er staat een nieuwe versie van Omi klaar, met oplossingen en verbeteringen.';

  @override
  String get nameMustBeBetweenCharacters => 'Naam moet tussen 2 en 40 tekens zijn';

  @override
  String operatorSubtitle(int count) {
    return '$count vragen per maand';
  }

  @override
  String conversationsDeletedCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count gesprekken verwijderd',
      one: '1 gesprek verwijderd',
    );
    return '$_temp0';
  }

  @override
  String get monthlyPayoutsDescription =>
      'Ontvang maandelijkse betalingen rechtstreeks op uw rekening wanneer u \$10 aan inkomsten bereikt';

  @override
  String get dailyScoreExplanation =>
      'Je dagelijkse score is gebaseerd op taakvoltooiing. Voltooi je taken om je score te verbeteren!';

  @override
  String get improveConnectionContent =>
      'We hebben verbeterd hoe Omi verbonden blijft met je apparaat. Om dit te activeren, ga naar de Apparaatinfo-pagina, tik op \"Apparaat loskoppelen\" en koppel je apparaat opnieuw.';

  @override
  String get syncingRecordings => 'Opnames synchroniseren';

  @override
  String get professionProductManager => 'Productmanager';

  @override
  String get nameMustBeAtLeast2Characters => 'Naam moet minstens 2 tekens bevatten';

  @override
  String get conversationTitle => 'Gesprekstitel';

  @override
  String mcpServerConnected(int count) {
    return '$count tools succesvol verbonden';
  }

  @override
  String get feedbackSubtitleNotUsing => 'We willen Omi nuttiger maken voor je.';

  @override
  String get exportBeforeDelete =>
      'Je kunt je gegevens exporteren voordat je je account verwijdert, maar eenmaal verwijderd kan het niet worden hersteld.';

  @override
  String deleteTasksTitle(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count taken verwijderen?',
      one: '1 taak verwijderen?',
    );
    return '$_temp0';
  }

  @override
  String get frequencyMaximum => 'Maximum';

  @override
  String get cancelReasonSubtitle => 'Kun je ons vertellen waarom je vertrekt?';

  @override
  String get generatingIconStep => 'Icoon genereren';

  @override
  String get storeAudioDescription =>
      'Bewaar alle audio-opnames lokaal op uw telefoon. Wanneer uitgeschakeld, worden alleen mislukte uploads bewaard om opslagruimte te besparen.';

  @override
  String get unpairDeviceConfirmTitle => 'Apparaat ontkoppelen?';

  @override
  String get phoneCallsMaybeLater => 'Misschien later';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'Er is een fout opgetreden: $message';
  }

  @override
  String get yourPrivacyMattersToUs => 'Uw privacy is belangrijk voor ons';

  @override
  String get collapseAction => 'Samenvouwen';

  @override
  String get friendWordOfMouth => 'Vriend';

  @override
  String get deviceOnboardingVoiceReplyStatusHeadphonesDisconnected =>
      'Geen hoofdtelefoon aangesloten. Omi blijft stil totdat u er een paar aansluit.';

  @override
  String get connectDevice => 'Apparaat verbinden';

  @override
  String get deviceId => 'Apparaat-ID';

  @override
  String get addWordsDescription => 'Voeg woorden toe die Omi moet herkennen tijdens transcriptie.';

  @override
  String get userId => 'Gebruikers-ID';

  @override
  String evidenceCardConfirms(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Ja op $count suggesties',
      one: 'Ja op 1 suggestie',
    );
    return '$_temp0';
  }

  @override
  String segmentsCount(int count) {
    return '$count segmenten';
  }

  @override
  String get permissionsSetupTitle => 'Krijg de beste ervaring';

  @override
  String get permissionTypeAccess => 'Toegang';

  @override
  String get speakerTagPromptSaveVoicesBody =>
      'Omi bewaart een kort stemfragment om ze de volgende keer te herkennen. Je kunt dit altijd wijzigen in Instellingen.';

  @override
  String get developerApi => 'Ontwikkelaar-API';

  @override
  String get chargingIssues => 'Oplaadproblemen';

  @override
  String get debugAndDiagnostics => 'Debug & Diagnostiek';

  @override
  String get failedConnections => 'Mislukte verbindingen';

  @override
  String get userIdCopied => 'Gebruikers-ID gekopieerd naar klembord';

  @override
  String get cannotReportOwnMessage => 'Je kunt je eigen berichten niet rapporteren.';

  @override
  String get latestVersion => 'Nieuwste versie';

  @override
  String get feedbackReasonNotHelpful => 'Niet nuttig of niet relevant';

  @override
  String get deletePeopleMessage =>
      'Hiermee worden hun stemsamples verwijderd. Dit kan niet ongedaan worden gemaakt. Hun uitspraken in eerdere gesprekken worden naamloze sprekers.';

  @override
  String get deviceOnboardingAllSetSubtitle => 'Tik op een rij om deze te bekijken of te wijzigen.';

  @override
  String get mergeConversations => 'Gesprekken samenvoegen';

  @override
  String get paused => 'Gepauzeerd';

  @override
  String get updateGuide => 'Update-handleiding';

  @override
  String cancelBillingPeriodInfo(String date) {
    return 'Je abonnement blijft actief tot $date. Daarna word je overgezet naar de gratis versie met beperkte functies.';
  }

  @override
  String get reconnectingToInternet => 'Opnieuw verbinden met internet…';

  @override
  String get allFilesDeleted => 'Alle opnames verwijderd';

  @override
  String get paypalEmailHint => 'nik@example.com';

  @override
  String get oneWeekAgo => '1 week geleden';

  @override
  String get deviceOnboardingAllSetSinglePressBadge => '1×';

  @override
  String get playbackAudioUnavailable => 'Audio niet beschikbaar';

  @override
  String get deviceOnboardingTryDoubleTap => 'Probeer het nu! Dubbeltik op je Omi';

  @override
  String get deleteReasonPrivacy => 'Privacyzorgen';

  @override
  String get cleanUpPinnedNote => 'Vastgezette mensen worden nooit meegenomen bij Opruimen.';

  @override
  String get wrappedProductiveDay => 'Productief';

  @override
  String get voiceSharedAcrossDevices => 'Je stemkeuze wordt gedeeld tussen mobiel en desktop.';

  @override
  String get knowledgeGraphDeleted => 'Kennisgraaf verwijderd';

  @override
  String get pressDoneToCreate => 'Druk op Klaar om aan te maken';

  @override
  String get cloudStorage => 'Cloudopslag';

  @override
  String get howDoesItWork => 'Hoe werkt het?';

  @override
  String get submitApp => 'App indienen';

  @override
  String get searchMemories => 'Herinneringen zoeken';

  @override
  String get fallNotificationTitle => 'Au';

  @override
  String storedOnDevice(String deviceName) {
    return 'Opgeslagen op $deviceName';
  }

  @override
  String get contactsPermissionRequired => 'Contactentoestemming vereist';

  @override
  String get reviewUpdatedSuccessfully => 'Recensie succesvol bijgewerkt 🚀';

  @override
  String get pleaseEnterPayPalMeLink => 'Voer uw PayPal.me-link in';

  @override
  String get notHelpful => 'Niet nuttig';

  @override
  String get recordingsToSync => 'Opnames om te synchroniseren';

  @override
  String get categoryUtilities => 'Hulpmiddelen';

  @override
  String get exportStarted => 'Export gestart. Dit kan enkele seconden duren…';

  @override
  String get deviceOnboardingVoiceReplyStatusOff => 'Omi blijft stil. Antwoorden verschijnen nog steeds in de app.';

  @override
  String get myGoal => 'Mijn doel';

  @override
  String timeHourSingular(int count) {
    return '$count uur';
  }

  @override
  String get chatToolsManifestUrl => 'URL van chattoolsmanifest';

  @override
  String msgSelectFilesError(String error) {
    return 'Fout bij selecteren van bestanden: $error';
  }

  @override
  String connectedToApp(String appName) {
    return 'Verbonden met $appName';
  }

  @override
  String get entityCorrectionHint => 'Vertel Omi wat er moet worden aangepast';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch succesvol verbonden!';

  @override
  String appIntegration(String appName) {
    return '$appName-integratie';
  }

  @override
  String get cancelReasonAudioQuality => 'Audio-/transcriptiekwaliteit';

  @override
  String get invalidProviderInConfig => 'Ongeldige provider in configuratie';

  @override
  String get deselectAll => 'Alles Deselecteren';

  @override
  String get chatAppsCodeExpiredMessage => 'Vraag een nieuwe code aan en stuur die vanuit Berichten.';

  @override
  String get reviewAnswerFailed => 'Je antwoord kon niet worden opgeslagen. Probeer het opnieuw.';

  @override
  String get categorySocial => 'Sociaal';

  @override
  String get rating4PlusStars => '4+ sterren';

  @override
  String get couldNotOpenSmsApp => 'Kan SMS-app niet openen. Probeer het opnieuw.';

  @override
  String get chatAppsNoMessages => 'Geen berichten';

  @override
  String get wrappedCelebrity => 'BEROEMDHEID';

  @override
  String get revokeKeyQuestion => 'Sleutel intrekken?';

  @override
  String timeMinsAndSecs(int mins, int secs) {
    return '$mins min $secs sec';
  }

  @override
  String get searchContactsHint => 'Contacten zoeken';

  @override
  String get showEventsWithoutParticipants => 'Evenementen zonder deelnemers weergeven';

  @override
  String get fair => 'Redelijk';

  @override
  String get tipAutoSync => 'Opnames worden automatisch gesynchroniseerd';

  @override
  String get summaryCopiedToClipboard => 'Samenvatting gekopieerd naar klembord';

  @override
  String get clearSearch => 'Zoekopdracht wissen';

  @override
  String get speakerTagPromptNotAPerson => 'Geen persoon';

  @override
  String get modelLabel => 'Model';

  @override
  String deleteItemQuestion(String item) {
    return '$item verwijderen?';
  }

  @override
  String get enterPromoCode => 'Voer promotiecode in';

  @override
  String get phoneNoContactsFound => 'Geen contacten gevonden';

  @override
  String countRemaining(String count) {
    return '$count resterend';
  }

  @override
  String get manageYourApp => 'Beheer uw app';

  @override
  String get willSyncAutomatically => 'wordt automatisch gesynchroniseerd';

  @override
  String get promoCode => 'Promotiecode';

  @override
  String get trackPersonalGoalsOnHomepage => 'Volg je persoonlijke doelen op de startpagina';

  @override
  String get memoryHistoryPartial =>
      'Een deel van de herinneringsgeschiedenis is niet beschikbaar. De tot nu toe ontvangen geschiedenis wordt getoond.';

  @override
  String get sharePublicLink => 'Openbare link delen';

  @override
  String get conversationTab => 'Gesprek';

  @override
  String get backgroundModeDescription => 'Houd je Omi aan het opnemen, zelfs wanneer de app volledig gesloten is.';

  @override
  String get pairingDescOmiDevkit =>
      'Druk eenmaal op de knop om in te schakelen. De LED knippert paars in koppelingsmodus.';

  @override
  String get callStateFailed => 'Gesprek mislukt';

  @override
  String get githubRepositoryUrlHint => 'Link naar de broncode-repository van je app';

  @override
  String get appIconLabel => 'App Icon';

  @override
  String get uninstallApp => 'App verwijderen';

  @override
  String get confidenceReasonNeedsVoice => 'nog geen stemvoorbeeld';

  @override
  String get couldNotLoadApiKeys => 'API-sleutels konden niet worden geladen.';

  @override
  String get fetchingStableFirmware => 'Laatste stabiele firmware ophalen…';

  @override
  String get onDeviceModelDownloaded => 'Gedownload';

  @override
  String get noAPIKeys => 'Geen API-sleutels. Maak er een aan om te beginnen.';

  @override
  String get phoneCallsUpsellFeature3 => 'Ontvangers zien je echte nummer, niet een willekeurig';

  @override
  String get wrappedMovieRecs => 'Filmaanbevelingen voor vrienden';

  @override
  String msgFilePickerError(String error) {
    return 'Fout bij openen bestandskiezer: $error';
  }

  @override
  String get professionEntrepreneur => 'Ondernemer';

  @override
  String get recent => 'Recent';

  @override
  String get permissionDescCreateMemories => 'Deze app kan nieuwe herinneringen maken.';

  @override
  String get tapToComplete => 'Tik om te voltooien';

  @override
  String vocabularyWordCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count woorden',
      one: '1 woord',
    );
    return '$_temp0';
  }

  @override
  String get deleteSyncedFilesMessage =>
      'Deze opnames zijn al gesynchroniseerd met uw telefoon. Dit kan niet ongedaan worden gemaakt.';

  @override
  String get cancelConsequenceSpeakers => 'Kan sprekers niet identificeren.';

  @override
  String get aiGenFailedToGenerateApp => 'Kan app niet genereren. Probeer het opnieuw.';

  @override
  String get account => 'Account';

  @override
  String get capabilityIntegrations => 'Integraties';

  @override
  String get voiceSettingsAskToTag => 'Vraag me stemmen te taggen';

  @override
  String get chatAppsHeroTitle => 'Chat met Omi waar je al chat';

  @override
  String get myApps => 'Door mij gemaakt';

  @override
  String get deleteRecap => 'Samenvatting verwijderen';

  @override
  String get production => 'Productie';

  @override
  String get phoneRecordingBlockedByPendantBatch =>
      'Stop Transcribe Later op je hanger voordat je met je telefoon opneemt.';

  @override
  String dataRateKbps(String rate) {
    return '$rate kbps';
  }

  @override
  String get createAKeyToGetStarted => 'Maak een sleutel om te beginnen';

  @override
  String get pleaseSelectRating => 'Selecteer een beoordeling';

  @override
  String get pdfTranscriptExport => 'Transcript exporteren';

  @override
  String get newFolder => 'Nieuwe map';

  @override
  String get fallNotificationBody => 'Ben je gevallen?';

  @override
  String get scopeUserChat => 'Gebruikerschat';

  @override
  String get tryDifferentSearchTerm => 'Probeer een andere zoekterm';

  @override
  String get submit => 'Versturen';

  @override
  String get deviceOnboardingVoiceReplySubtitle =>
      'Wanneer u met de knop vraagt, kan Omi het antwoord hardop voorlezen.';

  @override
  String get showOnLockScreen => 'Toon op vergrendelscherm';

  @override
  String get msgMaxImagesLimit => 'U kunt maximaal 4 afbeeldingen selecteren';

  @override
  String get wrappedOmiLifeRecap => 'Omi levenssamenvatting';

  @override
  String get nextButton => 'Volgende';

  @override
  String disconnectAppTitle(String appName) {
    return '$appName loskoppelen?';
  }

  @override
  String get updateReview => 'Beoordeling bijwerken';

  @override
  String get noMemoriesInCategory => 'Nog geen herinneringen in deze categorie';

  @override
  String get memoryDeleted => 'Herinnering verwijderd';

  @override
  String get connectOmiDevice => 'Omi-apparaat verbinden';

  @override
  String get professionSoftwareEngineer => 'Software-ontwikkelaar';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'Andere segmenten van deze spreker taggen ($selected/$total)';
  }

  @override
  String get productName => 'Productnaam';

  @override
  String get permissionDeniedForAppleReminders => 'Toestemming geweigerd voor Apple Herinneringen';

  @override
  String get allMemoriesAreNowPrivate => 'Alle herinneringen zijn nu privé';

  @override
  String planSetToCancelOn(String date) {
    return 'Uw plan wordt geannuleerd op $date.\nAbonneer nu opnieuw om uw voordelen te behouden - geen kosten tot $date.';
  }

  @override
  String get deletePersonTitle => 'Persoon verwijderen?';

  @override
  String deleteItemConfirmation(String item) {
    return '$item wordt verwijderd. Dit kan niet ongedaan worden gemaakt.';
  }

  @override
  String get appleHealthConnectCta => 'Verbinden met Apple Health';

  @override
  String segmentsPlural(String count) {
    return '$count segmenten';
  }

  @override
  String get syncCardDownloadingTitle => 'Downloaden van je apparaat';

  @override
  String additionalSampleIndex(String index) {
    return 'Extra voorbeeld $index';
  }

  @override
  String get descriptionLabel => 'Beschrijving';

  @override
  String get failedToClearDueDate => 'Kan vervaldatum niet wissen';

  @override
  String get timeout4HoursDesc => 'Gesprek beëindigen na 4 uur stilte';

  @override
  String get noSyncedRecordingsYet => 'Nog geen gesynchroniseerde opnames';

  @override
  String dreamReportDropped(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count oudere wijzigingen overgeslagen',
      one: '1 oudere wijziging overgeslagen',
    );
    return '$_temp0';
  }

  @override
  String get claudeCode => 'Claude Code';

  @override
  String get noPendingRecordings => 'Geen wachtende opnames';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'Vertel ons hoe u aangesproken wilt worden. Dit helpt uw Omi-ervaring te personaliseren.';

  @override
  String get updateSummaryWithNewNames => 'Samenvatting bijwerken met nieuwe namen';

  @override
  String get setWhenConversationsAutoEnd => 'Hoelang Omi in stilte wacht voordat een gesprek eindigt';

  @override
  String get successfullyConnectedGoogleTasks => 'Succesvol verbonden met Google Tasks!';

  @override
  String get confirmUpgrade => 'Upgrade bevestigen';

  @override
  String get speechToTextProviderDesc => 'Selecteer de dienst voor transcriptie';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Fout bij verbinden met Apple Watch: $error';
  }

  @override
  String get instagram => 'Instagram';

  @override
  String sampleNumber(int number) {
    return 'Monster $number';
  }

  @override
  String get popularApps => 'Populaire apps';

  @override
  String get micGainDescSlightlyBoosted => 'Licht versterkt - normaal gebruik';

  @override
  String get promptMustBeAtLeast10Characters => 'Prompt moet minimaal 10 tekens zijn';

  @override
  String get chatAppsEntryRowSubtitle => 'Telegram, iMessage en meer';

  @override
  String get estimatedSizeLabel => 'Geschatte grootte';

  @override
  String get mcpServerDesc => 'AI-assistenten verbinden met je gegevens';

  @override
  String get disconnectHistory => 'Ontkoppelingsgeschiedenis';

  @override
  String get downgradeLimitDelay => '5-7 seconden vertraging';

  @override
  String get msgSelectImagesGenericError => 'Fout bij selecteren van afbeeldingen. Probeer het opnieuw.';

  @override
  String get audioPlaybackUnavailable => 'Audiobestand is niet beschikbaar voor afspelen';

  @override
  String get byClickingConnectNow => 'Door op \"Nu verbinden\" te klikken gaat u akkoord met';

  @override
  String get signalStrength => 'Signaalsterkte';

  @override
  String get tellUsPrimaryLanguage => 'Vertel ons je primaire taal';

  @override
  String get diagnosticsShareFailed => 'Kon de diagnostiek niet delen. Probeer het opnieuw.';

  @override
  String get createKeyToStart => 'Maak een sleutel aan om te beginnen';

  @override
  String generatedBy(String appName) {
    return 'Gegenereerd door $appName';
  }

  @override
  String shareStatsListened(String minutes) {
    return '🎧 $minutes minuten geluisterd';
  }

  @override
  String get getOmiDevice => 'Omi apparaat aanschaffen';

  @override
  String get newTask => 'Nieuwe taak';

  @override
  String get conversationPrompt => 'Gespreksprompt';

  @override
  String get otaWifiConnected => 'Verbonden met wifi';

  @override
  String get dismiss => 'Verbergen';

  @override
  String get webhooks => 'Webhooks';

  @override
  String get raybanMetaCamera => 'Camera';

  @override
  String get recapRegenerateNoConversations => 'Geen gesprekken om voor deze dag samen te vatten.';

  @override
  String pendantMinutesStored(int minutes) {
    return '~$minutes min opgeslagen';
  }

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName losgekoppeld';
  }

  @override
  String get normal => 'Normaal';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch nog steeds niet bereikbaar. Zorg ervoor dat de Omi-app geopend is op je horloge.';

  @override
  String get connectionGuide => 'Verbindingshandleiding';

  @override
  String get syncStepProcessDesc => 'Omi maakt van de audio een gesprek';

  @override
  String get couldNotLoadPlans => 'Kon beschikbare abonnementen niet laden. Probeer het opnieuw.';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '$used van $limit min gebruikt deze maand';
  }

  @override
  String get learnMoreLink => 'meer informatie';

  @override
  String get unpairDeviceDialogMessage =>
      'Dit zal het apparaat ontkoppelen zodat het kan worden verbonden met een andere telefoon. U moet naar Instellingen > Bluetooth gaan en het apparaat vergeten om het proces te voltooien.';

  @override
  String get authFailedToRetrieveToken => 'Kon Firebase-token niet ophalen, probeer het opnieuw.';

  @override
  String get aiGenFailedToCreateApp => 'Kan app niet aanmaken';

  @override
  String get appAndDeviceCopied => 'App- en apparaatgegevens gekopieerd';

  @override
  String get noProcessedRecordings => 'Nog geen verwerkte opnames';

  @override
  String get transcriptTab => 'Transcriptie';

  @override
  String get permissionDescReadConversations => 'Deze app heeft toegang tot je gesprekken.';

  @override
  String get tryAnotherApp => 'Probeer een andere app';

  @override
  String get subscriptionSetToCancel => 'Uw abonnement wordt aan het einde van de periode geannuleerd.';

  @override
  String chatAppsCodeExpiresIn(String time) {
    return 'Code verloopt over $time';
  }

  @override
  String get authFailedToSignInWithApple => 'Aanmelden met Apple mislukt, probeer het opnieuw.';

  @override
  String get feedbackReasonIgnoredInstructions => 'Volgde de instructies niet';

  @override
  String get startupFailedDetails => 'Details';

  @override
  String get deleteMeetingScreenshotTitle => 'Schermafbeelding verwijderen?';

  @override
  String get chatAppsNotConnectedMessage => 'Deze chat-app is ontkoppeld.';

  @override
  String get aboutOmiApiKeys => 'Over Omi API-sleutels';

  @override
  String get tiktok => 'TikTok';

  @override
  String get maxFilesLimit => 'Je kunt maximaal 4 bestanden tegelijk uploaden';

  @override
  String get legalNotice =>
      'Juridische kennisgeving: De legaliteit van het opnemen en opslaan van spraakgegevens kan variëren afhankelijk van je locatie en hoe je deze functie gebruikt. Het is jouw verantwoordelijkheid om naleving van lokale wet- en regelgeving te waarborgen.';

  @override
  String get wrappedYourTopDays => 'Je beste dagen';

  @override
  String get addMcpServer => 'MCP-server toevoegen';

  @override
  String publicAppsCount(String count) {
    return 'Openbare apps ($count)';
  }

  @override
  String get noExternalAppsHaveAccess => 'Geen externe apps hebben toegang tot uw gegevens.';

  @override
  String get captureStarting => 'Starten…';

  @override
  String get downloadingAudioProgress => 'Audio downloaden';

  @override
  String get audioBytes => 'Audiobytes';

  @override
  String batteryLevelSemantics(int level) {
    return 'Batterij $level%';
  }

  @override
  String captureRecordedBy(String devices) {
    return 'Opgenomen door $devices';
  }

  @override
  String get chatAppsRepliesOnlyNote => 'Omi antwoordt alleen jou. Omi stuurt nooit als eerste een bericht.';

  @override
  String get hideTranscript => 'Transcript verbergen';

  @override
  String get permissionReadConversations => 'Gesprekken lezen';

  @override
  String get installed => 'Geïnstalleerd';

  @override
  String get paymentEnterValidAmount => 'Voer een geldig bedrag in';

  @override
  String get sttLanguageOverride => 'Overschrijven';

  @override
  String get appInterfaceSectionTitle => 'App-interface';

  @override
  String get searchLanguages => 'Zoek talen';

  @override
  String get otherSource => 'Anders';

  @override
  String get pairingDescOmiGlass => 'Houd de zijknop 3 seconden ingedrukt om in te schakelen.';

  @override
  String get signOut => 'Uitloggen';

  @override
  String shareStatsWords(String words) {
    return '🧠 $words woorden begrepen';
  }

  @override
  String verifiedDaysAgo(int days) {
    return '${days}d geleden geverifieerd';
  }

  @override
  String get captureModeLater => 'Later';

  @override
  String get enableMoreApps => 'Meer apps inschakelen';

  @override
  String get frequencyDescBalanced => 'Nuttige suggesties, ongeveer 5–8 per dag';

  @override
  String get startYourFirstRecording => 'Start uw eerste opname';

  @override
  String get transcriptionPausedReconnecting => 'Neemt nog steeds op — opnieuw verbinden met transcriptie…';

  @override
  String get basicPlan => 'Gratis abonnement';

  @override
  String get user => 'Gebruiker';

  @override
  String get pinPersonDescription =>
      'Vastgezette mensen blijven bovenaan je lijst met mensen staan en worden niet verwijderd door Opruimen.';

  @override
  String get reviewProject => 'Project';

  @override
  String get keyboardShortcuts => 'Sneltoetsen';

  @override
  String get diagnosticsFailBadge => 'Mislukt';

  @override
  String get debugLogCleared => 'Debug-log gewist';

  @override
  String get errorConnectingToStripe => 'Fout bij verbinden met Stripe! Probeer het later opnieuw.';

  @override
  String get tapPlusToStartRecording => 'Tik op de opnameknop om de opname te starten';

  @override
  String get permissionBlockedHint => 'Uitgeschakeld in Instellingen. Sta het daar toe om dit te gebruiken.';

  @override
  String get downloadingAudio => 'Audio downloaden…';

  @override
  String failedToRevokeApiKey(String error) {
    return 'Kan API-sleutel niet intrekken: $error';
  }

  @override
  String largeTimeGapDetected(String gap) {
    return 'Groot tijdsverschil gedetecteerd ($gap)';
  }

  @override
  String get customFirmwareWarning =>
      'Aangepaste firmware kan je apparaat onbruikbaar maken. Controleer of dit een geldige Omi-firmwarebuild is en verbreek de verbinding niet tijdens de update.';

  @override
  String get wrapped2025 => 'Terugblik 2025';

  @override
  String get showApiKey => 'API-sleutel tonen';

  @override
  String get agreeAndContinue => 'Akkoord en doorgaan';

  @override
  String get connectExternalAiTools => 'Externe AI-tools verbinden';

  @override
  String get batteryFullyChargedTitle => 'Omi is volledig opgeladen';

  @override
  String get appReEnableFailedTitle => 'Opnieuw inschakelen mislukt';

  @override
  String get onboardingYourName => 'Je naam';

  @override
  String get searchApps => 'Apps zoeken';

  @override
  String get weak => 'Zwak';

  @override
  String get tellUsMore => 'Vertel ons meer (optioneel)';

  @override
  String confidenceReasonPicked(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Gekozen in $count suggesties',
      one: 'Gekozen in 1 suggestie',
    );
    return '$_temp0';
  }

  @override
  String chatAppsDisconnectFooter(String app) {
    return 'Bij ontkoppelen wordt de geschiedenis verwijderd die Omi voor $app bewaart.';
  }

  @override
  String get selectAll => 'Alles selecteren';

  @override
  String get deleteActionItemConfirmation => 'Deze taak verwijderen? Dit kan niet ongedaan worden gemaakt.';

  @override
  String get categoryTravel => 'Reizen';

  @override
  String get lowestRating => 'Laagste beoordeling';

  @override
  String get tasksEmptyStateMessage => 'Begin een gesprek om een taak aan te maken.';

  @override
  String get unpairAndForget => 'Apparaat ontkoppelen en vergeten';

  @override
  String get listeningForAudio => 'Luisteren naar audio…';

  @override
  String get processedStatus => 'Verwerkt';

  @override
  String get wrappedTheHardPart => 'Het moeilijke deel';

  @override
  String chatAppsReplyThereAnytime(String app) {
    return 'Stuur Omi op elk moment een bericht in $app.';
  }

  @override
  String get upgradePlan => 'Plan upgraden';

  @override
  String get onboardingRatingPromptYes => 'Ja';

  @override
  String timeCompactMins(int count) {
    return '${count}m';
  }

  @override
  String get changeTheConversationTitle => 'Gesprekstitel wijzigen';

  @override
  String get accountGroup => 'Account';

  @override
  String get updatingYourApp => 'Uw app bijwerken';

  @override
  String get microphone => 'Microfoon';

  @override
  String get suggestQuestionsAfterConversations => 'Vragen voorstellen na gesprekken';

  @override
  String get failedToTranscribeAudio => 'Audio transcriberen mislukt';

  @override
  String get unstarConversation => 'Ster van gesprek verwijderen';

  @override
  String get speakerTagPromptNotMe => 'Niet ik';

  @override
  String get confidenceReasonCorrected => 'Je hebt de match gecorrigeerd';

  @override
  String get peopleSearchPlaceholder => 'Zoek mensen';

  @override
  String get syncStatusUnsupportedAudio => 'Audio niet leesbaar — kan niet worden gesynchroniseerd';

  @override
  String get indentTask => 'Inspringen';

  @override
  String get selectApp => 'App selecteren';

  @override
  String get updatePayPal => 'PayPal bijwerken';

  @override
  String get enterNameError => 'Voer uw naam in';

  @override
  String get exportAllData => 'Alle gegevens exporteren';

  @override
  String premiumMinsLeft(int count) {
    return '$count premium minuten over.';
  }

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName ingesteld als standaard samenvattingsapp';
  }

  @override
  String get recordingStartedSuccessfully => 'Opname succesvol gestart!';

  @override
  String get trySomethingLike => 'Probeer iets als…';

  @override
  String get chatAppsTryAsking => 'Probeer te vragen';

  @override
  String get categoryEntertainment => 'Entertainment';

  @override
  String get checksForAudioFiles => 'Controleert op audiobestanden op de SD-kaart';

  @override
  String get everyoneHeader => 'Iedereen';

  @override
  String get clearMemoryButton => 'Geheugen wissen';

  @override
  String confidenceReasonLabeled(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Je hebt $count keer gelabeld',
      one: 'Je hebt één keer gelabeld',
    );
    return '$_temp0';
  }

  @override
  String get selectLogFile => 'Logbestand selecteren';

  @override
  String get chatAppsTelegramStepReturn => 'Kom hier terug. We bevestigen dat het gelukt is.';

  @override
  String get discordMemberCount => 'Meer dan 8000 leden op Discord';

  @override
  String get public => 'Openbaar';

  @override
  String get outdentTask => 'Uitspringen';

  @override
  String get statusProcessing => 'Verwerken';

  @override
  String get useFreePlan => 'Gratis abonnement gebruiken';

  @override
  String get emailLabel => 'E-mail';

  @override
  String get statusCallInProgress => 'Gesprek gaande';

  @override
  String get shortcuts => 'Sneltoetsen';

  @override
  String get reviewRecentChanges => 'Recente wijzigingen';

  @override
  String get raybanMetaAudioOnlyExplanation =>
      'Deze versie van Omi kan de microfoon van je bril gebruiken via Bluetooth. Voor het maken van foto\'s is de Meta-ontwikkelaarsversie van Omi nodig.';

  @override
  String get wrappedDaysActiveLabel => 'actieve dagen';

  @override
  String get installOmiOnAppleWatch => 'Installeer Omi op je\nApple Watch';

  @override
  String tasksCountLabel(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count taken',
      one: '1 taak',
    );
    return '$_temp0';
  }

  @override
  String get confidenceReasonVoiceReady => 'stem opgeslagen';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return '$count geselecteerde ta(a)k(en)$s verwijderen?';
  }

  @override
  String get sdCardSync => 'SD-kaart synchronisatie';

  @override
  String get timeout4Hours => '4 uur';

  @override
  String get chatAppsTitle => 'Chat-apps';

  @override
  String get repeatPasswordLabel => 'Wachtwoord herhalen';

  @override
  String get skip => 'Overslaan';

  @override
  String get phoneNoVerifiedNumbersTitle => 'Geen geverifieerde nummers';

  @override
  String get connectionLost => 'Verbinding verbroken';

  @override
  String get photoDiscardedMessage => 'Deze foto is verwijderd omdat deze niet significant was.';

  @override
  String get weekdayFri => 'Vr';

  @override
  String get moveToFolder => 'Verplaatsen naar map';

  @override
  String get updateNow => 'Nu bijwerken';

  @override
  String get failedToUpdateActionItem => 'Taak bijwerken mislukt';

  @override
  String get transferRequiredDescription =>
      'Deze opname staat op de SD-kaart van je apparaat. Zet deze over naar je telefoon om af te spelen of te delen.';

  @override
  String get checkingForUpdates => 'Controleren op updates';

  @override
  String get importTranscriptFilesDescription =>
      'Selecteer SRT-, VTT- of TXT-transcripties, of een ZIP met deze bestanden';

  @override
  String get listenToSpeechProfile => 'Luister naar mijn stemprofiel ➡️';

  @override
  String get deleteRecapConfirmBody =>
      'Deze samenvatting wordt permanent verwijderd. De oorspronkelijke gesprekken van die dag blijven behouden.';

  @override
  String get copyLogs => 'Logs kopiëren';

  @override
  String get wrappedFunniestMoment => 'Grappigste';

  @override
  String get onboardingMicrophoneRequired => 'Microfoontoestemming is vereist voor opname.';

  @override
  String get whoIsItTitle => 'Wie is het?';

  @override
  String dreamReportRunsLeft(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Nog $count handmatige runs vandaag',
      one: 'Nog 1 handmatige run vandaag',
    );
    return '$_temp0';
  }

  @override
  String get modified => 'Aangepast';

  @override
  String get actionCreateConversations => 'Gesprekken aanmaken';

  @override
  String get chatAssistantsTitle => 'Chat-assistenten';

  @override
  String get connectionError => 'Verbindingsfout';

  @override
  String get chooseFromGallery => 'Kies uit galerij';

  @override
  String get summaryPrompt => 'Samenvattingsprompt';

  @override
  String get whatWentWrong => 'Wat ging er mis?';

  @override
  String get keepGoingGreat => 'Ga zo door, je doet het geweldig';

  @override
  String get deviceConnecting => 'Verbinden…';

  @override
  String get downgradeLimitBattery => '7x meer batterijverbruik';

  @override
  String get privateMemories => 'Privé herinneringen';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get aiGenPleaseEnterDescription => 'Voer een beschrijving in voor je app';

  @override
  String get enterLiveSttWebsocket => 'Voer je live STT WebSocket-endpoint in';

  @override
  String processingOnServerProgress(int current, int total) {
    return 'Verwerken… $current/$total segmenten';
  }

  @override
  String linkedToEvent(String title) {
    return 'Gekoppeld aan “$title”';
  }

  @override
  String get failedToSaveCheckConnection => 'Opslaan mislukt. Controleer je verbinding.';

  @override
  String get deviceOnboardingContinue => 'Doorgaan';

  @override
  String get pairedToAnotherPhone => 'Gekoppeld aan een andere telefoon';

  @override
  String get syncingYourRecordings => 'Je opnames synchroniseren';

  @override
  String get manual => 'Handmatig';

  @override
  String get oneMonthAgo => '1 maand geleden';

  @override
  String get clearChatConfirm => 'Alle berichten in deze chat worden verwijderd. Dit kan niet ongedaan worden gemaakt.';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'Alles wat \"$keyName\" gebruikt, verliest toegang. Dit kan niet ongedaan worden gemaakt.';
  }

  @override
  String get vadGateDescription => 'Slaat stille audio over voordat er wordt getranscribeerd, om kosten te besparen.';

  @override
  String get dreamReportScheduled => 'Gepland';

  @override
  String get audioDataReceived => 'Audiogegevens ontvangen';

  @override
  String get pro => 'Pro';

  @override
  String get micGainDescMuted => 'Microfoon is gedempt';

  @override
  String get enableLocationDescription => 'Locatietoestemming is nodig om Bluetooth-apparaten in de buurt te vinden.';

  @override
  String get conversationTitleUpdatedSuccessfully => 'Gesprekstitel succesvol bijgewerkt';

  @override
  String get syncStepUpload => 'Synchroniseren';

  @override
  String get removeScreenshot => 'Screenshot verwijderen';

  @override
  String get failedToStartCall => 'Kan gesprek niet starten';

  @override
  String get deviceDiagnosticsUploadDescription =>
      'Review the diagnostics JSON below. It includes your device identifier, connection history, battery readings, firmware diagnostics, and BLE events. No audio or transcripts are included.';

  @override
  String get pairingTitleFieldy => 'Zet Fieldy in koppelingsmodus';

  @override
  String get autoDeletesAfterThreeDays => 'Automatisch verwijderd na 3 dagen.';

  @override
  String get wrappedDaysActive => 'actieve dagen';

  @override
  String get failedToDeleteActionItem => 'Taak verwijderen mislukt';

  @override
  String get connect => 'Verbinden';

  @override
  String get unableToDeleteConversation => 'Kan gesprek niet verwijderen';

  @override
  String get clearChatAction => 'Chat wissen';

  @override
  String get memoryThisIphone => 'Deze iPhone';

  @override
  String get captureCustomSttUnreachableDetail =>
      'Je eigen spraak-naar-tekstdienst is niet bereikbaar. Omi bewaart de audio op deze telefoon en verstuurt die zodra de dienst terug is. Er gaat niets verloren.';

  @override
  String get feedbackGiveFeedback => 'Feedback geven';

  @override
  String failedToUpdateSettings(String error) {
    return 'Instellingen bijwerken mislukt: $error';
  }

  @override
  String get deleteRecordingConfirmation => 'Dit kan niet ongedaan worden gemaakt.';

  @override
  String get advancedSettings => 'Geavanceerde instellingen';

  @override
  String get transcriptionNoAudio => 'Transcriptie ontvangt geen audio';

  @override
  String deletePeopleCountAction(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count mensen verwijderen',
      one: '1 persoon verwijderen',
    );
    return '$_temp0';
  }

  @override
  String get speakerSuggestionAppliesToSpeaker => 'Geldt voor elke regel van deze spreker';

  @override
  String get deviceNotResponding => 'Apparaat reageerde niet. Probeer opnieuw.';

  @override
  String get everythingSynced => 'Alles is al gesynchroniseerd.';

  @override
  String get onDeviceModelDownloadFailedDesc => 'Het Whisper-model kon niet worden gedownload. Probeer het opnieuw.';

  @override
  String fairUseBannerStatus(String status) {
    return 'Eerlijk gebruik: $status';
  }

  @override
  String tasksDeleteSelected(int count) {
    return '$count taak/taken verwijderen';
  }

  @override
  String get connectPaymentMethodInfo =>
      'Verbind hieronder een betaalmethode om uitbetalingen voor uw apps te ontvangen.';

  @override
  String get conversationNotFoundOrDeleted => 'Gesprek niet gevonden of is verwijderd';

  @override
  String leaveFlowStepOf(int current, int total) {
    return 'Stap $current van $total';
  }

  @override
  String get deleteTypeToConfirm => 'Typ DELETE om te bevestigen';

  @override
  String get clearMemoryTitle => 'Omi\'s geheugen wissen';

  @override
  String get triggerConversationCreation => 'Gesprek aanmaken';

  @override
  String get flashCustomFirmware => 'Aangepaste firmware flashen';

  @override
  String shareWithContactCount(int count) {
    return 'Delen met $count contact';
  }

  @override
  String get customChatbotPersonality => 'Aangepaste chatbot-persoonlijkheid';

  @override
  String get betaTesterNotice =>
      'U bent een bètatester voor deze app. Het is nog niet openbaar. Het wordt openbaar zodra het is goedgekeurd.';

  @override
  String get tomorrow => 'Morgen';

  @override
  String get createdLabel => 'AANGEMAAKT';

  @override
  String get searchPeople => 'Personen zoeken';

  @override
  String get cancelled => 'Geannuleerd';

  @override
  String basicPlanDesc(int limit) {
    return 'Je abonnement bevat $limit gratis minuten per maand. Upgrade naar onbeperkt.';
  }

  @override
  String get editMemoryTitle => 'Herinnering bewerken';

  @override
  String get whatDoYouWantToKnow => 'Wat wil je weten?';

  @override
  String get confidenceFootnote =>
      'Labels en bevestigingen van jou tellen het zwaarst. Automatische labels tellen weinig tot je ze bevestigt.';

  @override
  String get exportFailedTryAgain => 'Exporteren mislukt. Probeer het opnieuw.';

  @override
  String get addAppPhotosPermissionDenied => 'Fototoegang geweigerd. Geef toegang tot foto\'s';

  @override
  String get filterByDate => 'Filteren op datum';

  @override
  String get chatAppsDoesFiles => 'Verstuurt en ontvangt bestanden, foto\'s en spraakberichten';

  @override
  String get deleteKnowledgeGraphTitle => 'Kennisgraaf verwijderen?';

  @override
  String get reloadingConversations => 'Gesprekken opnieuw laden…';

  @override
  String get aiGenPleaseGenerateAppFirst => 'Genereer eerst een app';

  @override
  String get completeYourUpgrade => 'Voltooi je upgrade';

  @override
  String get capturePendantDisconnectedDetail =>
      'Je hanger heeft de verbinding met deze telefoon verloren. Omi maakt vanzelf opnieuw verbinding zodra de hanger aan staat en in de buurt is. Alles wat eerder is opgenomen, is veilig.';

  @override
  String get greetingMorning => 'Goedemorgen';

  @override
  String get thanksForYourFeedback => 'Bedankt voor je feedback!';

  @override
  String get deleteActionItemConfirmMessage => 'Deze taak verwijderen?';

  @override
  String get syncCardProcessing => 'Verwerken bij Omi…';

  @override
  String get chatAppsTryWeek => 'Vat mijn week samen in drie regels';

  @override
  String get recordWithPhoneMicSubtitle => 'Opnemen en transcriberen met de microfoon van deze telefoon';

  @override
  String get notifications => 'Meldingen';

  @override
  String get annualPlanStartsAutomatically => 'Uw jaarabonnement start automatisch wanneer uw maandabonnement eindigt.';

  @override
  String get unpairDialogMessage =>
      'Dit ontkoppelt het apparaat zodat het met een andere telefoon kan worden verbonden. Je moet naar Instellingen > Bluetooth gaan en het apparaat vergeten om het proces te voltooien.';

  @override
  String get pairingTitleBee => 'Zet Bee in koppelingsmodus';

  @override
  String conversationCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count gesprekken',
      one: '1 gesprek',
    );
    return '$_temp0';
  }

  @override
  String get syncStatusWaiting => 'Wacht op synchronisatie';

  @override
  String get validWebsocketUrlRequired => 'Geldige WebSocket-URL is vereist (wss://)';

  @override
  String get improveSpeechProfile => 'Verbeter je spraakprofiel';

  @override
  String entityWaitingOn(String name) {
    return 'Wachten op $name';
  }

  @override
  String get feedbackReasonTooVerbose => 'Te langdradig';

  @override
  String chatAppsChannelFooter(String app) {
    return 'Je $app-chats blijven in $app. Omi weet nog steeds waar je het over had in de app en in je andere chat-apps.';
  }

  @override
  String get wrappedNoDataAvailable => 'Geen gegevens beschikbaar';

  @override
  String deviceOnboardingAllSetReplayHint(String settings, String deviceSettings, String deviceTutorial) {
    return 'Speel deze tour op elk gewenst moment opnieuw af in $settings › $deviceSettings › $deviceTutorial';
  }

  @override
  String get createAKey => 'Sleutel maken';

  @override
  String get successfullyConnectedNotion => 'Succesvol verbonden met Notion!';

  @override
  String get captureMicInterruptedDetail =>
      'Een gesprek of andere app gebruikt de microfoon, dus Omi kan nu niet luisteren. Omi gaat vanzelf verder zodra de microfoon vrij is. Alles wat eerder is opgenomen, is veilig.';

  @override
  String get onboardingScreenCaptureDenied =>
      'Schermopnametoestemming geweigerd. Verleen toestemming in Systeemvoorkeuren > Privacy en beveiliging > Schermopname.';

  @override
  String get settingUp => 'Instellen…';

  @override
  String get frequencyLow => 'Laag';

  @override
  String get sttFilterAuto => 'Automatisch';

  @override
  String get voiceQuestionNoSpeech => 'Dat heb ik niet verstaan — probeer het opnieuw';

  @override
  String get stripeRecommendation =>
      'Als Stripe beschikbaar is in uw land, raden we het ten zeerste aan voor snellere en gemakkelijkere uitbetalingen.';

  @override
  String get confirmed => 'Bevestigd!';

  @override
  String get deletePendingFilesWarning =>
      'Deze opnames zijn NIET gesynchroniseerd met uw telefoon en gaan permanent verloren. Dit kan niet ongedaan worden gemaakt.';

  @override
  String get removeFilter => 'Filter Verwijderen';

  @override
  String get downloadModel => 'Model downloaden';

  @override
  String get performanceReduced => 'Prestaties kunnen verminderd zijn';

  @override
  String get hostRequired => 'Host is vereist';

  @override
  String get alreadyBestValuePlan => 'U heeft al het beste abonnement qua waarde. Geen wijzigingen nodig.';

  @override
  String preparingModel(String model) {
    return '$model voorbereiden…';
  }

  @override
  String get sendTranscript => 'Verstuur transcript';

  @override
  String get howItWorksTitle => 'Hoe werkt het?';

  @override
  String get filterBySpeaker => 'Filteren op spreker';

  @override
  String get addAppSubmittedSuccess => 'App succesvol ingediend 🚀';

  @override
  String olderIphoneModelDetected(String model) {
    return 'Gedetecteerd model: $model (ouder dan iPhone XS). Herkenning op het apparaat kan trager zijn.';
  }

  @override
  String get chatAppsWhatsAppTitle => 'WhatsApp komt eraan';

  @override
  String get syncingDeveloperSettings => 'Ontwikkelaarsinstellingen synchroniseren…';

  @override
  String get enterWifiPassword => 'Voer het WiFi-wachtwoord in';

  @override
  String get failedToUpdateBaselineStatus => 'Kan deze herinnering niet bijwerken. Probeer het opnieuw.';

  @override
  String get joinCommunity => 'Word lid van de community!';

  @override
  String get helpOrInquiries => 'Hulp of vragen?';

  @override
  String get enable => 'Inschakelen';

  @override
  String get deviceForgottenMessage => 'Apparaat vergeten';

  @override
  String diagnosticsSincePairingSummary(int drops, int failed) {
    return 'Sinds koppeling: $drops onderbrekingen, $failed mislukte verbindingen.';
  }

  @override
  String confidenceSummaryConfirmed(String name) {
    return 'Omi herkent de stem van $name, en je hebt dat bevestigd.';
  }

  @override
  String migratingToProtection(String level) {
    return 'Migreren naar $level beveiliging…';
  }

  @override
  String get managePlan => 'Abonnement beheren';

  @override
  String get synced => 'Gesynchroniseerd';

  @override
  String get failedToMoveConversations => 'Kan de gesprekken niet verplaatsen';

  @override
  String get monthMar => 'Mrt';

  @override
  String get timePM => 'PM';

  @override
  String get debugLogsAutoDelete => 'Automatisch verwijderd na 3 dagen.';

  @override
  String get linkedIn => 'LinkedIn';

  @override
  String speakerLabelVoiceDetail(String state, String name) {
    String _temp0 = intl.Intl.selectLogic(
      state,
      {
        'learned': 'Omi herkent $name de volgende keer.',
        'pending': 'Dit duurt een paar seconden.',
        'disabled': 'Zet stemmen opslaan aan in Instellingen zodat Omi $name kan herkennen.',
        'other': 'Omi heeft meer duidelijke spraak van $name nodig en blijft het proberen.',
      },
    );
    return '$_temp0';
  }

  @override
  String get authUnexpectedError => 'Onverwachte fout bij aanmelden, probeer het opnieuw';

  @override
  String disconnectAppMessage(String appName) {
    return 'Je kunt $appName altijd opnieuw verbinden.';
  }

  @override
  String get pendantPausedResumesWhenYouFinish => 'Hanger gepauzeerd · gaat verder als je klaar bent';

  @override
  String get sendToSupport => 'Send to support';

  @override
  String get fairUseBudgetExhausted => 'Daily transcription limit reached';

  @override
  String evidenceAutoConfirmed(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Je hebt $count automatische labels bevestigd',
      one: 'Je hebt 1 automatisch label bevestigd',
    );
    return '$_temp0';
  }

  @override
  String get otaWifiConnecting => 'Verbinden met wifi…';

  @override
  String starFilterLabel(int count) {
    return '$count ster';
  }

  @override
  String get disconnectDevice => 'Apparaat loskoppelen';

  @override
  String get installsCount => 'Installaties';

  @override
  String captureStatusWithSource(String status, String source) {
    return '$status · $source';
  }

  @override
  String get pairingTitleOmiGlass => 'Zet Omi Glass aan';

  @override
  String get setActive => 'Instellen als actief';

  @override
  String get showShortConversations => 'Korte gesprekken tonen';

  @override
  String get reviewNotSure => 'Weet ik niet';

  @override
  String msgCameraAccessError(String error) {
    return 'Fout bij toegang tot camera: $error';
  }

  @override
  String get quickActionAskOmi => 'Vraag Omi van alles';

  @override
  String get dreamReportTimedOut => 'Gestopt bij de tijdslimiet';

  @override
  String get chooseYourLanguage => 'Kies uw taal';

  @override
  String get unableToDetermineFirmwareVersion => 'Kan de huidige firmwareversie niet bepalen';

  @override
  String get addAppEnterConversationPrompt => 'Voer een gespreksprompt in voor uw app';

  @override
  String get readScope => 'Lezen';

  @override
  String get selectALanguage => 'Selecteer een taal';

  @override
  String get otherTemplates => 'Andere sjablonen';

  @override
  String get speechProfileTopicGoal => 'Wat is je langetermijndoel?';

  @override
  String get rayBanMetaMicPickerTitle => 'Kies je Ray-Ban Meta-microfoon';

  @override
  String meetingNotesSubject(String title) {
    return 'Notities: $title';
  }

  @override
  String get feedbackTitleMissingFeatures => 'Welke functies mis je?';

  @override
  String get modelReady => 'Model gereed';

  @override
  String todayAtTime(String time) {
    return 'Vandaag om $time';
  }

  @override
  String get deleteAccountPermanently => 'Account definitief verwijderen';

  @override
  String get updateStripeDetails => 'Stripe-gegevens bijwerken';

  @override
  String get voiceResponseHeadphonesOnly => 'Alleen koptelefoon';

  @override
  String get deviceOnboardingEndConversation => 'Gesprek beëindigen';

  @override
  String openingApp(String appName) {
    return '$appName openen…';
  }

  @override
  String get submitAppPublicDescription =>
      'Je app wordt beoordeeld en openbaar gemaakt. Je kunt het onmiddellijk gebruiken, zelfs tijdens de beoordeling!';

  @override
  String connectToAppTitle(String appName) {
    return 'Verbinden met $appName';
  }

  @override
  String get timeout10MinutesDesc => 'Gesprek beëindigen na 10 minuten stilte';

  @override
  String get googleCalendar => 'Google Agenda';

  @override
  String get initializing => 'Initialiseren…';

  @override
  String get noMessagesYet => 'Nog geen berichten!\nWaarom begin je geen gesprek?';

  @override
  String get chatAppsLoadFailed => 'Chat-apps konden niet worden geladen. Probeer het opnieuw.';

  @override
  String get tasksLater => 'Later';

  @override
  String get speakerLabelUnknown => 'Onbekend';

  @override
  String get appTitle => 'Omi';

  @override
  String get noModelDownloadRequired =>
      'De native spraakengine van je apparaat wordt gebruikt. Geen modeldownload vereist.';

  @override
  String get authenticationFailed => 'Authenticatie mislukt. Probeer het opnieuw.';

  @override
  String get defaultRepoSaved => 'Standaard repository opgeslagen';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'Fout bij selecteren miniatuur: $error';
  }

  @override
  String get captureRecordingSeparateTitle => 'Deze opname scheiden?';

  @override
  String get back => 'Terug';

  @override
  String get preparingAudio => 'Audio voorbereiden';

  @override
  String get noAutoMemories => 'Nog geen automatisch geëxtraheerde herinneringen';

  @override
  String get allDone => 'Helemaal klaar!';

  @override
  String get msgReadingMemories => 'Je herinneringen lezen…';

  @override
  String get worksOnDesktop => 'Werkt op desktop';

  @override
  String get displayOptions => 'Weergaveopties';

  @override
  String get installApp => 'App installeren';

  @override
  String get stop => 'Stop';

  @override
  String get grantPermissions => 'Machtigingen verlenen';

  @override
  String get at => 'om';

  @override
  String get checkInternetConnection => 'Controleer uw internetverbinding';

  @override
  String get actionItems => 'Taken';

  @override
  String get nextDay => 'Volgende dag';

  @override
  String get syncStatusFailed => 'Mislukt — tik op Opnieuw';

  @override
  String get saveCredentials => 'Inloggegevens opslaan';

  @override
  String get peopleRecent => 'Recent';

  @override
  String get bringYourOwn => 'Breng je eigen mee';

  @override
  String get cancelConsequenceBattery => '7x meer batterijverbruik (verwerking op het apparaat)';

  @override
  String get copyMessage => 'Bericht kopiëren';

  @override
  String get annualSubscriptionStarts => 'Uw 12-maanden jaarabonnement start automatisch na de betaling';

  @override
  String get deleteImportedData => 'Geïmporteerde gegevens verwijderen';

  @override
  String get chatLimitReachedUpgrade => 'Chatlimiet bereikt. Upgrade voor meer berichten.';

  @override
  String get whatsNew => 'Wat is nieuw';

  @override
  String get omiTraining => 'Omi Training';

  @override
  String get wrappedMyBuddies => 'Mijn vrienden';

  @override
  String get keepRecording => 'Verder opnemen';

  @override
  String get suggestedEvent => 'Voorgesteld';

  @override
  String get name => 'Naam';

  @override
  String get screenRecordingDescription =>
      'Omi heeft toestemming voor schermopname nodig om systeemaudio van uw browsergebaseerde vergaderingen vast te leggen.';

  @override
  String get improveConnectionTitle => 'Verbinding verbeteren';

  @override
  String get syncProcessingBackgroundHint => 'Dit gaat op de achtergrond door — je kunt dit scherm verlaten.';

  @override
  String get wrappedYourTopDaysBadge => 'Je beste dagen';

  @override
  String get noPeopleYet => 'Nog geen personen';

  @override
  String summaryGeneratedForDate(String date) {
    return 'Samenvatting gegenereerd voor $date';
  }

  @override
  String get searchTranscriptOrSummary => 'Zoeken in transcript of samenvatting';

  @override
  String get memoryDetailsTitle => 'Herinnering';

  @override
  String get chatPersonality => 'Chatpersoonlijkheid';

  @override
  String get release => 'Loslaten';

  @override
  String removeVocabularyWord(String word) {
    return '$word verwijderen';
  }

  @override
  String get onboardingLanguage => 'Taal';

  @override
  String get wrappedYouDidItEmoji => 'Je hebt het gedaan! 🎉';

  @override
  String get syncInProgress => 'Synchronisatie bezig';

  @override
  String get wrappedCouldntStopTalkingAbout => 'Kon niet stoppen met praten over';

  @override
  String get chooseSummarizationApp => 'Kies samenvattingsapp';

  @override
  String etaLabel(String time) {
    return 'ETA: $time';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'Als u $item openbaar maakt, kan het door iedereen worden gebruikt';
  }

  @override
  String get phoneCallsUpsellFeature2 => 'Automatische gesprekssamenvattingen en taken';

  @override
  String get freemiumLimitsIntro =>
      'Omi is gratis, maar de gratis versie heeft beperkingen die je ervaring beïnvloeden:';

  @override
  String get nameLabel => 'Naam';

  @override
  String get shortConversationThresholdSubtitle =>
      'Gesprekken korter dan dit worden verborgen tenzij hierboven ingeschakeld';

  @override
  String get captureMicInUseElsewhere => 'Microfoon in gebruik door andere app';

  @override
  String get selectChatAssistant => 'Selecteer chat-assistent';

  @override
  String get transferRequired => 'Overdracht vereist';

  @override
  String get unlimitedChatThisMonth => 'Onbeperkte chatberichten deze maand';

  @override
  String get backgroundModeUnavailable =>
      'Achtergrondmodus is niet beschikbaar omdat er geen compatibel apparaat is verbonden. Verbind een Omi-, OpenGlass- of Friend Pendant-apparaat om deze functie te gebruiken.';

  @override
  String get importConfiguration => 'Configuratie importeren';

  @override
  String get e2eeTradeoff1 => '• Sommige functies zoals externe app-integraties kunnen worden uitgeschakeld.';

  @override
  String get chatAppsCodeExpiredTitle => 'Deze code is verlopen';

  @override
  String get responseSchema => 'Response schema';

  @override
  String get wrappedBestMoments => 'Beste momenten';

  @override
  String get noAppsExternalAccess => 'Geen geïnstalleerde apps hebben externe toegang tot je gegevens.';

  @override
  String modelReadyWithName(String model) {
    return 'Model gereed ($model)';
  }

  @override
  String get appDisabledWebhookFailures => 'Het endpoint faalde 72 uur achter elkaar, daarom is de bezorging gestopt.';

  @override
  String reviewConversationCount(int count) {
    return 'Gesprekken: $count';
  }

  @override
  String get reviewChangesLoadFailed => 'Recente wijzigingen konden niet worden geladen.';

  @override
  String get reviewOpenConversation => 'Gesprek';

  @override
  String get voiceRecordingFound => 'Opname gevonden';

  @override
  String durationAgo(String duration) {
    return '$duration geleden';
  }

  @override
  String get onboardingWelcomeToOmi => 'Welkom bij Omi';

  @override
  String get deleteActionItemConfirmTitle => 'Taak verwijderen';

  @override
  String get importantBillingInfo => 'Belangrijke factureringsinformatie:';

  @override
  String get pending => 'In afwachting';

  @override
  String get onboardingRatingPromptTitle => 'Bevalt Omi je?';

  @override
  String get savePayPalDetails => 'PayPal-gegevens opslaan';

  @override
  String appDisabledLastError(String error) {
    return 'Laatste fout: $error.';
  }

  @override
  String get iveInstalledAndOpenedTheApp => 'Ik heb de app geïnstalleerd en geopend';

  @override
  String get pricePlaceholder => '0,00';

  @override
  String get triggerTranscriptProcessed => 'Transcript verwerkt';

  @override
  String get decisions => 'Beslissingen';

  @override
  String get conversationProcessingFailedMessage => 'Dit gesprek kon niet worden verwerkt.';

  @override
  String get continueText => 'Doorgaan';

  @override
  String get signInWithGoogle => 'Inloggen met Google';

  @override
  String firmwareFlashTarget(String deviceName) {
    return 'Apparaat: $deviceName';
  }

  @override
  String get deleteYourAccountAndAllData => 'Verwijder uw account en alle gegevens';

  @override
  String get provider => 'Provider';

  @override
  String get people => 'Mensen';

  @override
  String get perMonth => '/ Maand';

  @override
  String get monthFeb => 'Feb';

  @override
  String get fridayAbbr => 'Vr';

  @override
  String get thankYouForFeedback => 'Bedankt voor uw feedback!';

  @override
  String get usageBestYear => 'Best year';

  @override
  String get addAppFillRequiredFields => 'Vul alle verplichte velden correct in';

  @override
  String get deviceOnboardingVoiceReplyOffDescription => 'Antwoorden blijven op het scherm. Er wordt niets gesproken.';

  @override
  String get logs => 'Logboeken';

  @override
  String get exportConversations => 'Gesprekken exporteren';

  @override
  String get memoryReviewDropped => 'Verwijderd uit je herinneringen.';

  @override
  String get appearanceLight => 'Licht';

  @override
  String get moneyEarned => 'Verdiend geld';

  @override
  String get permissionsAndTriggers => 'Machtigingen & triggers';

  @override
  String get discardRecordingTitle => 'Opname verwerpen?';

  @override
  String get wrappedMinutesLabel => 'minuten';

  @override
  String get voiceRestoredToast => 'Omi kan opnieuw naar deze stem vragen';

  @override
  String get locationAccess => 'Locatietoegang';

  @override
  String get deleteAllMemories => 'Alle herinneringen verwijderen';

  @override
  String get deleteAccountTitle => 'Account verwijderen';

  @override
  String get selectFile => 'Selecteer een bestand';

  @override
  String get answerTheCallFrom => 'Beantwoord het gesprek van';

  @override
  String get unpairDeviceDialogTitle => 'Apparaat ontkoppelen';

  @override
  String exportedToPlatform(String platform) {
    return 'Geëxporteerd naar $platform';
  }

  @override
  String syncCardDownloadPercent(int percent) {
    return '$percent%';
  }

  @override
  String get deviceOnboardingVoiceReplyPreviewPlaying => 'Je laatste antwoord afspelen...';

  @override
  String get fromSd => 'Van SD';

  @override
  String get goodSampleInstructions =>
      '1. Zorg ervoor dat je op een rustige plek bent.\n2. Spreek duidelijk en natuurlijk.\n3. Zorg ervoor dat je apparaat in zijn natuurlijke positie op je nek zit.\n\nNa het maken kun je het altijd verbeteren of opnieuw doen.';

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
  String get starConversationHint =>
      'Om een gesprek als favoriet te markeren, open het en tik op het stericoon in de header.';

  @override
  String get pairingTitleOmiDevkit => 'Zet Omi DevKit in koppelingsmodus';

  @override
  String sttPrimaryLanguageUnsupported(String language, String fallback) {
    return 'Deze provider ondersteunt $language niet en gebruikt daarom $fallback.';
  }

  @override
  String get premiumMinutesMonth =>
      '300 premium minuten per maand. Kies Op apparaat voor onbeperkte gratis transcriptie. ';

  @override
  String get firmwareEnsureBattery => 'Zorg ervoor dat uw apparaat 15% batterij heeft.';

  @override
  String get actionItemDescriptionHint => 'Wat moet er gedaan worden?';

  @override
  String get yourScore => 'Jouw score';

  @override
  String failedToStartAuth(String appName) {
    return 'Kan $appName-authenticatie niet starten';
  }

  @override
  String get actionReadTasks => 'Taken lezen';

  @override
  String get keepSyncing => 'Doorgaan met synchroniseren';

  @override
  String get overdue => 'Achterstallig';

  @override
  String get chatAppsProblemUnavailable => 'Chat-apps zijn nog niet beschikbaar voor je account.';

  @override
  String get tapSyncToStart => 'Tik op Synchroniseren om te starten';

  @override
  String get emptyDoneMessage => 'Nog geen voltooide items';

  @override
  String get recordOptionsTip => 'Tip: tik op de pijl op de opnameknop om een telefoongesprek op te nemen.';

  @override
  String get setupQuestionProfession => '1. Wat doe je voor werk?';

  @override
  String get deviceInfoSection => 'Apparaatinformatie';

  @override
  String get teachOmiYourVoice => 'Leer Omi uw stem';

  @override
  String get addYourFirstMemory => 'Voeg je eerste herinnering toe';

  @override
  String get priceLabel => 'PRIJS';

  @override
  String get high => 'Hoog';

  @override
  String estimatedSizeWithValue(String size) {
    return 'Geschatte grootte: ~$size MB';
  }

  @override
  String cleanUpUnsureCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count mensen waarvan Omi het niet zeker weet',
      one: '1 persoon waarvan Omi het niet zeker weet',
    );
    return '$_temp0';
  }

  @override
  String get makeAllMemoriesPrivate => 'Alle herinneringen privé maken';

  @override
  String get raybanMetaWaitingForMetaAI => 'Voltooi het verbinden in de Meta AI-app en kom daarna terug.';

  @override
  String get revokeAuthorization => 'Autorisatie intrekken';

  @override
  String get confidenceToReachConfirmed => 'Om Bevestigd te bereiken';

  @override
  String get syncCardRateLimited => 'Gebruikslimiet bereikt — synchronisatie wordt automatisch hervat';

  @override
  String get reviewStopClip => 'Fragment stoppen';

  @override
  String get chatAppsWhatOmiDoes => 'Wat Omi doet in chat-apps';

  @override
  String get resume => 'Hervatten';

  @override
  String get defaultSpace => 'Standaardruimte';

  @override
  String get multipleSpeakersDetected => 'Meerdere sprekers gedetecteerd';

  @override
  String evidenceAutoCorrected(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Je hebt $count automatische labels naar iemand anders veranderd',
      one: 'Je hebt 1 automatisch label naar iemand anders veranderd',
    );
    return '$_temp0';
  }

  @override
  String get voiceMatchPossible => 'Mogelijke match';

  @override
  String get checkBoxToConfirm =>
      'Vink het vakje aan om te bevestigen dat je begrijpt dat het verwijderen van je account permanent en onomkeerbaar is.';

  @override
  String get quicklyPopulateResponse => 'Snel invullen met bekend provider antwoordformaat';

  @override
  String get monthJul => 'Jul';

  @override
  String get failedToInitializeCallService => 'Kan belservice niet initialiseren';

  @override
  String get connectAction => 'Verbinden';

  @override
  String get onDeviceModelDeleted => 'Model verwijderd';

  @override
  String get micGainDescNeutral => 'Neutraal - gebalanceerde opname';

  @override
  String get chatOfflineHint => 'Je bent offline. Maak opnieuw verbinding om berichten te versturen.';

  @override
  String get onboardingLocationGrantInSettings =>
      'Verleen locatietoestemming in Instellingen > Privacy en beveiliging > Locatievoorzieningen';

  @override
  String get invalidSetupInstructionsUrl => 'Ongeldige URL voor installatie-instructies';

  @override
  String get msgCameraPermissionDenied => 'Cameratoestemming geweigerd. Geef alstublieft toegang tot de camera';

  @override
  String get dataAndPrivacy => 'Data en privacy';

  @override
  String get deviceNotCompatible => 'Je apparaat is niet compatibel met on-device transcriptie';

  @override
  String get pairingDescAppleWatch =>
      'Installeer en open de Omi-app op je Apple Watch en tik vervolgens op Verbinden in de app.';

  @override
  String get speechProfileTopicLocation => 'Waar woon je?';

  @override
  String get makeAllPrivate => 'Alle herinneringen privé maken';

  @override
  String get capabilityNotification => 'Melding';

  @override
  String get captureAudioSavedTranscribesLater => 'Audio opgeslagen, later getranscribeerd';

  @override
  String get wrappedTopPhrases => 'Top 5 zinnen';

  @override
  String get transcribeLaterPaused => 'Gepauzeerd — audio wordt niet opgenomen';

  @override
  String get deviceOnboardingTurnOnTitle => 'Aanzetten';

  @override
  String get keyNamePlaceholder => 'bijv., Mijn app-integratie';

  @override
  String get languageTitle => 'Taal';

  @override
  String get statusVerifiedLabel => 'Geverifieerd';

  @override
  String get storageLocationPhoneMemory => 'Telefoon (Geheugen)';

  @override
  String get you => 'Jij';

  @override
  String get listeningTranscriptWillAppear => 'Luisteren… hier verschijnt een transcript.';

  @override
  String get askSuggestNotice => 'Wat viel Omi op?';

  @override
  String get safelyBackedUp => 'Aangemaakte gesprekken';

  @override
  String get folderName => 'Mapnaam';

  @override
  String get categorySocialEntertainment => 'Sociaal & entertainment';

  @override
  String speechProfileOwnerTitle(String name) {
    return 'Stemprofiel van $name';
  }

  @override
  String get reviewAddedSuccessfully => 'Recensie succesvol toegevoegd 🚀';

  @override
  String get fairUseSpeechUsage => 'Spraakgebruik';

  @override
  String get visibilitySubtitle => 'Bepaal welke gesprekken in je lijst verschijnen';

  @override
  String get wrappedWinLabelUpper => 'OVERWINNING';

  @override
  String timeCompactMinsAndSecs(int mins, int secs) {
    return '${mins}m ${secs}s';
  }

  @override
  String get phoneCallsUpsellSubtitle =>
      'Bel via Omi en krijg realtime transcriptie, automatische samenvattingen en meer.';

  @override
  String get sessionExpiredSignInAgain => 'De sessie is verlopen — log opnieuw in.';

  @override
  String get newPersonEllipsis => 'Nieuwe persoon…';

  @override
  String get sharePeriodToday => 'Vandaag heeft Omi:';

  @override
  String get premiumMinutesInfo =>
      '300 premium minuten per maand. Kies Op apparaat voor onbeperkte gratis transcriptie.';

  @override
  String get notConnectedStatus => 'Niet verbonden';

  @override
  String get authorizeSavingRecordings => 'Opnames opslaan autoriseren';

  @override
  String get thinking => 'Aan het nadenken';

  @override
  String get unpairDialogTitle => 'Apparaat ontkoppelen';

  @override
  String get batteryFullyChargedBody => 'Uw Omi-apparaat is volledig opgeladen. U kunt het loskoppelen!';

  @override
  String get speakerTagPromptRejectedToast => 'Label verwijderd';

  @override
  String get phone => 'Telefoon';

  @override
  String get chatAppsVoiceNotes => 'Spraakberichten';

  @override
  String get deviceOnboardingStatusDisconnected => 'Niet verbonden';

  @override
  String get debugModeDetected => 'Debug-modus gedetecteerd';

  @override
  String get failedToSaveDefaultRepo => 'Opslaan van standaard repository mislukt';

  @override
  String get showCompletedTasks => 'Voltooide tonen';

  @override
  String deviceStorageUsedOfTotal(String used, String total) {
    return '$used van $total gebruikt';
  }

  @override
  String get recordingsNotSynced => 'Je hebt opnames die nog niet zijn gesynchroniseerd.';

  @override
  String get performanceWarning => 'Prestatiewaarschuwing';

  @override
  String get submitAppPrivateDescription =>
      'Je app wordt beoordeeld en privé beschikbaar gemaakt voor jou. Je kunt het onmiddellijk gebruiken, zelfs tijdens de beoordeling!';

  @override
  String get copyTranscript => 'Kopieer transcript';

  @override
  String get providing => 'Leveren';

  @override
  String get findDeviceNoneMessage => 'Zet hem aan en houd hem bij je telefoon.';

  @override
  String get wrappedLetsHitRewind => 'Laten we terugspoelen naar je';

  @override
  String deviceRamBelowMinimum(String ram) {
    return 'Gedetecteerd RAM: $ram GB. Aanbevolen minimum: 4 GB.';
  }

  @override
  String get addOrChangePaymentMethod => 'Voeg toe of wijzig je betaalmethode';

  @override
  String get omiAppName => 'Omi';

  @override
  String get enableBluetooth => 'Bluetooth inschakelen';

  @override
  String get privacyNotice => 'Privacyverklaring';

  @override
  String get manufacturer => 'Fabrikant';

  @override
  String get byContinuingYouAgree => 'Door door te gaan, ga je akkoord met onze ';

  @override
  String dataProtectedWithSettings(String level) {
    return 'Je gegevens zijn nu beschermd met de nieuwe $level instellingen.';
  }

  @override
  String get selectSpaceInWorkspace => 'Selecteer een ruimte in je werkruimte';

  @override
  String get copyKey => 'Sleutel kopiëren';

  @override
  String get password => 'Wachtwoord';

  @override
  String estimatedSize(String size) {
    return 'Geschatte grootte: ~$size MB';
  }

  @override
  String monthsFreeBadge(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count maanden gratis',
      one: '1 maand gratis',
    );
    return '$_temp0';
  }

  @override
  String get chatAppsNotAvailableYet => 'Nog niet beschikbaar';

  @override
  String estimatedTimeRemaining(String time) {
    return 'Geschat: $time resterend';
  }

  @override
  String get syncCardBackendBusy =>
      'De servers van Omi zijn druk — je opnames worden gesynchroniseerd zodra er weer capaciteit is';

  @override
  String get speakerTagPromptTitle => 'Help Omi stemmen te herkennen';

  @override
  String get playFromHere => 'Hier afspelen';

  @override
  String get entityProject => 'Project';

  @override
  String get permissionNotGrantedYet =>
      'Toestemming nog niet verleend. Zorg dat je microfoontoestemming hebt gegeven en de app op je horloge hebt heropend.';

  @override
  String get e2eeTradeoff2 => '• Als u uw wachtwoord verliest, kunnen uw gegevens niet worden hersteld.';

  @override
  String get exportConfiguration => 'Configuratie exporteren';

  @override
  String get recordWith => 'Opnemen met';

  @override
  String get greetingEvening => 'Goedenavond';

  @override
  String deletePhoneNumberConfirm(String phoneNumber) {
    return '$phoneNumber verwijderen?';
  }

  @override
  String get deviceOnboardingAskQuestionTitle => 'Stel Omi een vraag';

  @override
  String get appNamePlaceholder => 'Mijn geweldige app';

  @override
  String get tapPlayToResume => 'Tik op afspelen om te hervatten';

  @override
  String get dueDate => 'Vervaldatum';

  @override
  String get appearanceSystem => 'Systeem';

  @override
  String get invalidEmailError => 'Voer een geldig e-mailadres in';

  @override
  String get highResourceUsage => 'Hoog bronnengebruik';

  @override
  String get voiceAndPeople => 'Stem & Mensen';

  @override
  String get customizationSection => 'Aanpassingen';

  @override
  String get failedToCancelSubscription => 'Annuleren van abonnement mislukt. Probeer het opnieuw.';

  @override
  String get later => 'Later';

  @override
  String get wrappedTasksGenerated => 'taken gegenereerd';

  @override
  String get personalizingExperience => 'Je ervaring wordt gepersonaliseerd…';

  @override
  String get syncAvailable => 'Synchronisatie beschikbaar';

  @override
  String chatGreeting(String name) {
    return 'Hoi $name, vraag maar raak';
  }

  @override
  String get phoneCallSettingsTitle => 'Gespreksinstellingen';

  @override
  String get remoteDeviceTerminated => 'Extern apparaat heeft de verbinding verbroken';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'Fout bij openen bestandskiezer: $message';
  }

  @override
  String get actionItemDeleted => 'Taak verwijderd';

  @override
  String get couldNotLoadMemories => 'Herinneringen konden niet worden geladen';

  @override
  String get generateDescription => 'Beschrijving genereren';

  @override
  String get privateLabel => 'Privé';

  @override
  String get deviceOnboardingMuteUnmute => 'Dempen / Dempen opheffen';

  @override
  String get day => 'Dag';

  @override
  String get submitAppQuestion => 'App indienen?';

  @override
  String get usageWords => 'Words';

  @override
  String get failedToConnectClickUp => 'Verbinding met ClickUp mislukt';

  @override
  String get selectZipFileToImport => 'Selecteer het .zip-bestand om te importeren!';

  @override
  String timeSecsPlural(int count) {
    return '$count sec';
  }

  @override
  String get wasThisHelpful => 'Was dit nuttig?';

  @override
  String get msgLearningMemories => 'Leren van je herinneringen…';

  @override
  String get onboardingScreenCaptureRequired => 'Schermopnametoestemming is vereist voor systeemaudio-opname.';

  @override
  String evidenceManualLabels(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Door jou gelabeld in $count gesprekken',
      one: 'Door jou gelabeld in 1 gesprek',
    );
    return '$_temp0';
  }

  @override
  String get transferCancelled => 'Overdracht geannuleerd';

  @override
  String get sttModelSpeed => 'Snelheid';

  @override
  String get fairUsePolicy => 'Redelijk gebruik';

  @override
  String get phoneStorage => 'Telefoonopslag';

  @override
  String get deviceOnboardingEndConversationDesc => 'Huidig gesprek opslaan en beëindigen';

  @override
  String get proceedAnyway => 'Toch doorgaan';

  @override
  String get overview => 'Overzicht';

  @override
  String get deviceOnboardingGoodJob => 'Goed gedaan!';

  @override
  String get delete => 'Verwijderen';

  @override
  String get connectAiAssistantsToYourData => 'Verbind AI-assistenten met je gegevens';

  @override
  String get startFresh => 'Opnieuw beginnen';

  @override
  String get deviceOnboardingStatusConnectedDone => 'Verbonden!';

  @override
  String get filterInstalled => 'Geïnstalleerd';

  @override
  String get mergingStatus => 'Samenvoegen…';

  @override
  String get successfullyConnected => 'Succesvol verbonden!';

  @override
  String get permissionCreateConversations => 'Gesprekken maken';

  @override
  String get cancelConsequencePhoneCalls => 'Geen realtime telefoongesprek transcriptie';

  @override
  String get feedbackReasonSummaryOther => 'Iets anders';

  @override
  String get oAuth => 'OAuth';

  @override
  String get notEnoughSpace => 'Waarschuwing: Niet genoeg ruimte!';

  @override
  String get feedbackTitleTooExpensive => 'Welke prijs zou voor jou werken?';

  @override
  String get secureEncryption => 'Veilige versleuteling';

  @override
  String get rating2PlusStars => '2+ sterren';

  @override
  String get chatAppsOpenMessagesAgain => 'Open Berichten opnieuw';

  @override
  String fairUseBudgetResetsAt(String time) {
    return 'Resets $time';
  }

  @override
  String get addVocabularyDescription => 'Voeg woorden toe die Omi moet herkennen tijdens transcriptie.';

  @override
  String get whisperModelSizeMedium => 'Gemiddeld';

  @override
  String get wrappedMyBuddiesLabel => 'MIJN VRIENDEN';

  @override
  String get memoryGraph => 'Herinneringengrafiek';

  @override
  String get paste => 'Plakken';

  @override
  String get failedToRefreshGitHubStatus => 'Kan de GitHub-verbindingsstatus niet vernieuwen.';

  @override
  String get feedbackSubtitleMissingFeatures => 'We bouwen altijd — dit helpt ons prioriteiten te stellen.';

  @override
  String get itemApp => 'App';

  @override
  String get pairingDescFriendPendant =>
      'Druk op de knop op de hanger om deze in te schakelen. Het gaat automatisch naar de koppelingsmodus.';

  @override
  String get appDisabledGeneric => 'De app is door Omi uitgeschakeld.';

  @override
  String get noSummaryForApp =>
      'Geen samenvatting beschikbaar voor deze app. Probeer een andere app voor betere resultaten.';

  @override
  String get deleteProcessed => 'Verwerkte verwijderen';

  @override
  String get chatBlockOpenInGoals => 'Openen in Doelen';

  @override
  String get micGainDescModerate => 'Stil - voor matig geluid';

  @override
  String get defaultRepository => 'Standaard repository';

  @override
  String get statusPending => 'In behandeling';

  @override
  String get referralProgram => 'Doorverwijsprogramma';

  @override
  String get authFailedToLinkApple => 'Koppelen met Apple mislukt, probeer het opnieuw.';

  @override
  String modelNameWithFile(String model) {
    return 'Model: $model';
  }

  @override
  String get deviceOnboardingTurnOnSubtitle => 'Druk op de knop om hem weer aan te zetten';

  @override
  String get previewAndScreenshots => 'Voorbeeld en schermafbeeldingen';

  @override
  String get recordingOfflineTranscriptWillCatchUp =>
      'Offline opnemen — het transcript haalt de achterstand in zodra je weer online bent.';

  @override
  String get accessibilityDescription =>
      'Omi heeft toegankelijkheidstoestemming nodig om te detecteren wanneer u deelneemt aan Zoom-, Meet- of Teams-vergaderingen in uw browser.';

  @override
  String setDefaultAppContent(String appName) {
    return '$appName instellen als je standaard samenvattingsapp?\n\nDeze app wordt automatisch gebruikt voor alle toekomstige gesprekssamenvattingen.';
  }

  @override
  String get switchRequiresRestart => 'Wisselen vereist herstart van de app';

  @override
  String get wrappedWinHeader => 'Overwinning';

  @override
  String get forYou => 'Voor jou';

  @override
  String get filterCategory => 'Categorie';

  @override
  String get createPersonHint => 'Maak een nieuwe persoon aan en train Omi om hun stem te herkennen!';

  @override
  String get loadingMemories => 'Herinneringen laden…';

  @override
  String get selectedPaymentMethod => 'Geselecteerde betaalmethode';

  @override
  String get email => 'E-mail';

  @override
  String get transcriptionUnavailableRecordingContinues =>
      'Transcripties zijn niet beschikbaar, de opname gaat door op het apparaat en wordt later verwerkt';

  @override
  String get noLogsYet => 'Nog geen logs. Neem iets op om verzoeken naar je transcriptieprovider te zien.';

  @override
  String get failedToStartAuthentication => 'Kan authenticatie niet starten';

  @override
  String peopleCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count personen',
      one: '1 persoon',
    );
    return '$_temp0';
  }

  @override
  String get enterBackendUrlError => 'Voer de backend-URL in';

  @override
  String get playbackBackToCurrent => 'Terug naar huidige';

  @override
  String clockSkewWarning(int minutes) {
    return 'De klok van je apparaat wijkt ~$minutes min. af. Controleer je datum- en tijdinstellingen.';
  }

  @override
  String get stopThese => 'Deze stoppen';

  @override
  String get yes => 'Ja';

  @override
  String get recognizingOthers => 'Anderen herkennen 👀';

  @override
  String get transcriptionLanguageDesc => 'Selecteer de taal voor spraaktranscriptie';

  @override
  String aboutMinutesRemaining(int minutes) {
    return 'Ongeveer $minutes minuten resterend';
  }

  @override
  String get deleteFlowReasonSubtitle => 'Jouw feedback helpt ons Omi voor iedereen te verbeteren.';

  @override
  String get processedFilesDeleted => 'Verwerkte bestanden verwijderd';

  @override
  String get autoLanguageDetection => 'Automatische taaldetectie';

  @override
  String bulkExportPartial(int success, int total, String platform) {
    return '$success van $total geëxporteerd naar $platform';
  }

  @override
  String get actionItemDescriptionCannotBeEmpty => 'Taakomschrijving mag niet leeg zijn';

  @override
  String get deleteReasonFoundAlternative => 'Ik gebruik iets anders';

  @override
  String get noContentToDisplay => 'Geen inhoud om weer te geven';

  @override
  String get feedbackReasonRecordingWrongSpeaker => 'Verkeerde spreker';

  @override
  String get create => 'Aanmaken';

  @override
  String get greatJobAlmostThere => 'Goed bezig, je bent er bijna';

  @override
  String get captureStorageAlmostFull => 'Opslag bijna vol';

  @override
  String chatAppsConnectedOn(String date) {
    return 'Verbonden op $date';
  }

  @override
  String get wrappedAGreatDay => 'Een geweldige dag';

  @override
  String get backendUrlSavedSuccess => 'Backend-URL succesvol opgeslagen!';

  @override
  String get speakerTagPromptIsThisYou => 'Was jij dit?';

  @override
  String get knowledgeGraphDeletedSuccess => 'Kennisgraaf succesvol verwijderd';

  @override
  String timeMinsPlural(int count) {
    return '$count min';
  }

  @override
  String get peopleNotHeardYet => 'Nog niet gehoord';

  @override
  String get chatStarterDoDifferently => 'Wat kan ik vandaag anders doen?';

  @override
  String get fairUseAboutBody =>
      'Omi is ontworpen voor persoonlijke gesprekken, vergaderingen en live interacties. Het gebruik wordt gemeten aan de hand van de tijd dat er gesproken wordt, niet aan de hand van de verbindingstijd. Als je gebruik ver boven normaal persoonlijk gebruik ligt, krijg je eerst een waarschuwing. Aanhoudend zwaar gebruik kan de transcriptie vertragen of beperken.';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'Selecteer uw primaire taal';

  @override
  String get manualDisconnect => 'Handmatige ontkoppeling';

  @override
  String get googleCalendarNotConnected => 'Google Agenda niet verbonden';

  @override
  String get soCloseJustLittleMore => 'Zo dichtbij, nog even';

  @override
  String appDataAccessMessage(String appName) {
    return '$appName ontvangt je gesprekken, herinneringen en opnames op de server van de ontwikkelaar. Omi is niet verantwoordelijk voor hoe die gegevens daar worden gebruikt.';
  }

  @override
  String savePercent(int percent) {
    return 'Bespaar ~$percent%';
  }

  @override
  String get deviceDisconnectedNotificationBody => 'Verbind opnieuw om Omi te blijven gebruiken.';

  @override
  String get openConversation => 'Gesprek openen';

  @override
  String get frequencyDescMaximum => 'Elk nuttig verband, tot 9 per dag';

  @override
  String get readChatRepliesAloud => 'Chatantwoorden hardop voorlezen';

  @override
  String get microphonePermissionRequired => 'Microfoontoegang is vereist voor spraakopname.';

  @override
  String get updatePayPalAccountDetails => 'Werk uw PayPal-accountgegevens bij';

  @override
  String get connectionTimeout => 'Verbindingstime-out';

  @override
  String get micGainDescHigh => 'Hoog - voor verre of zachte stemmen';

  @override
  String get permissionsInfoNote => 'R = Lezen, W = Schrijven. Standaard alleen lezen als niets is geselecteerd.';

  @override
  String timeHoursAndMins(int hours, int mins) {
    return '$hours uur $mins min';
  }

  @override
  String get keepMyAccount => 'Mijn account behouden';

  @override
  String get transcriptionLanguage => 'Transcriptietaal';

  @override
  String dreamReportStats(int records, int tokens) {
    return '$records items gelezen · $tokens tokens';
  }

  @override
  String get editPerson => 'Persoon bewerken';

  @override
  String get whatWeTrack => 'Wat we bijhouden';

  @override
  String get micGainDescVeryHigh => 'Zeer hoog - voor zeer stille bronnen';

  @override
  String timeCompactDays(int count) {
    return '${count}d';
  }

  @override
  String get reviewTaskField => 'Taak';

  @override
  String reviewConfirmPerson(String name) {
    return '$name bevestigen';
  }

  @override
  String get downloadingFromDevice => 'Downloaden van apparaat';

  @override
  String get conversationTranscriptCopiedToClipboard => 'Gesprekstranscript gekopieerd naar klembord';

  @override
  String get continueAction => 'Doorgaan';

  @override
  String conversationsMovedCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count gesprekken verplaatst',
      one: '1 gesprek verplaatst',
    );
    return '$_temp0';
  }

  @override
  String get signInButton => 'Inloggen';

  @override
  String get startUpdate => 'Update starten';

  @override
  String get wrappedTopPhrasesLabelUpper => 'TOP ZINNEN';

  @override
  String get total => 'Totaal';

  @override
  String get deleting => 'Verwijderen…';

  @override
  String get skipBack10Seconds => '10 seconden terug';

  @override
  String get setupAnswerAllQuestions => 'Je hebt nog niet alle vragen beantwoord! 🥺';

  @override
  String get planUpgradeScheduledMessage =>
      'Upgrade gepland! Je maandelijkse abonnement loopt door tot het einde van je factureringsperiode en schakelt dan automatisch over naar jaarlijks.';

  @override
  String get needHelpChatWithUs => 'Hulp nodig? Chat met ons';

  @override
  String get chatBlockUnavailable => 'Niet langer beschikbaar';

  @override
  String estimatedMinutes(int count) {
    return '~$count minuut/minuten';
  }

  @override
  String get failedToSaveMemory => 'Opslaan mislukt. Controleer je verbinding.';

  @override
  String get deleteReasonTakingBreak => 'Ik neem gewoon een pauze';

  @override
  String get reviewAndManageConversations => 'Bekijk en beheer je opgenomen gesprekken';

  @override
  String get actionReadMemories => 'Herinneringen lezen';

  @override
  String deletePinnedPersonMessage(String name) {
    return '$name is vastgezet. De stemvoorbeelden worden verwijderd, Omi herkent deze persoon niet meer en in eerdere transcripties verschijnt die als een naamloze spreker. Dit kan niet ongedaan worden gemaakt.';
  }

  @override
  String get speakerTagPromptHintOwner => 'Je antwoord labelt alleen het afgespeelde fragment.';

  @override
  String get onboardingNotificationDeniedNotifications =>
      'Meldingstoestemming geweigerd. Verleen toestemming in Systeemvoorkeuren > Meldingen.';

  @override
  String appDisabledNamed(String appName) {
    return '$appName uitgeschakeld';
  }

  @override
  String get tabOld => 'Oud';

  @override
  String deviceOnboardingVoiceReplyStatusHeadphonesConnected(String device) {
    return '$device aangesloten. Omi zal hier spreken.';
  }

  @override
  String get deletePendingFiles => 'Wachtende opnames verwijderen';

  @override
  String get wrappedWin => 'Overwinning';

  @override
  String get removeFromAllFolders => 'Uit alle mappen verwijderen';

  @override
  String get deviceIdLabel => 'Apparaat-ID';

  @override
  String get upgradeAlreadyScheduled => 'Uw upgrade naar het jaarabonnement is al gepland';

  @override
  String get openCall => 'Gesprek openen';

  @override
  String get rateAndReviewThisApp => 'Beoordeel en recenseer deze app';

  @override
  String get getStarted => 'Aan de slag';

  @override
  String get deviceOnboardingVoiceReplyAlwaysDescription =>
      'Gebruikt de telefoonluidspreker als er geen hoofdtelefoon is aangesloten.';

  @override
  String chooseExportDestination(int count) {
    return '$count item(s) exporteren naar…';
  }

  @override
  String get onboardingSetupSubtitle => 'Geef Omi even de tijd om te personaliseren';

  @override
  String welcomeBack(String name) {
    return 'Welkom terug, $name';
  }

  @override
  String get dreamReportIdle => 'Nog niets nieuws om te bekijken.';

  @override
  String get cleanUpTitle => 'Opruimen';

  @override
  String get deleteProcessedFiles => 'Verwerkte bestanden verwijderen';

  @override
  String get no => 'Nee';

  @override
  String get msgPhotoError => 'Fout bij het maken van foto. Probeer het opnieuw.';

  @override
  String get search => 'Zoeken';

  @override
  String get downloadingFirmware => 'Firmware downloaden';

  @override
  String get phoneKeypadTab => 'Toetsenbord';

  @override
  String get pendantFullSyncBlocked =>
      'De opslag van je Pendant is vol en hij staat nog in de opnamemodus, dus de opgeslagen audio kan niet worden overgedragen. Druk op de knop van de Pendant om de opname te stoppen en synchroniseer daarna opnieuw.';

  @override
  String get deleteSelectedItemsTitle => 'Geselecteerde items verwijderen';

  @override
  String get appPrivacyAndTerms => 'App-privacy en -voorwaarden';

  @override
  String get omiTranscription => 'Omi-transcriptie';

  @override
  String get editConversation => 'Gesprek bewerken';

  @override
  String moveConversationsTo(int count) {
    return '$count gesprekken verplaatsen naar:';
  }

  @override
  String get signOutConfirmation =>
      'Je moet opnieuw inloggen om je gesprekken te zien. Je gekoppelde apparaat en app-voorkeuren blijven op deze telefoon.';

  @override
  String get wrappedObsessionsLabel => 'OBSESSIES';

  @override
  String get jumpToLatestMessage => 'Naar nieuwste bericht springen';

  @override
  String get failedStatus => 'Mislukt';

  @override
  String get notNow => 'Niet nu';

  @override
  String transferFailedMessage(String error) {
    return 'Overdracht mislukt: $error';
  }

  @override
  String get customVocabularyTitle => 'Aangepaste woordenlijst';

  @override
  String get internetRequired => 'Internet vereist';

  @override
  String get waitingForData => 'Wachten op gegevens…';

  @override
  String get noRecordingsYet => 'Nog geen opnames';

  @override
  String get answerWithYourVoice => 'Antwoord met je stem:';

  @override
  String personUnpinnedToast(String name) {
    return '$name losgemaakt';
  }

  @override
  String get stopRecording => 'Opname stoppen';

  @override
  String get off => 'Uit';

  @override
  String get memoryThisPhone => 'Deze telefoon';

  @override
  String get thirteenMonthsCoverage => 'U krijgt in totaal 13 maanden dekking (huidige maand + 12 maanden jaarlijks)';

  @override
  String failedToCreateApiKey(String error) {
    return 'Kan provider API-sleutel niet maken: $error';
  }

  @override
  String get tipStableInternet => 'Stabiel internet versnelt cloud-uploads';

  @override
  String get tasksMarkComplete => 'Gemarkeerd als voltooid';

  @override
  String get reviewAddTask => 'Taak toevoegen';

  @override
  String get submitReply => 'Antwoord verzenden';

  @override
  String get captureRecoveryBanner => 'Omi verzendt geen audio — tik om opnieuw verbinding te maken';

  @override
  String get analyzing => 'Analyseren…';

  @override
  String get sttModelFaster => 'Sneller';

  @override
  String get fairUseLoadError => 'Kan de status van redelijk gebruik niet laden. Probeer het opnieuw.';

  @override
  String get places => 'Plaatsen';

  @override
  String get voiceMatchWeak => 'Zwakke match';

  @override
  String captureOfflineBufferingFor(int minutes) {
    return 'Offline, bufferen · $minutes min';
  }

  @override
  String get onboardingWhatIKnowAboutYouTitle => 'Dit weet ik over jou';

  @override
  String get raybanMetaPhotoRequested => 'Foto aangevraagd — deze verschijnt in je gesprek.';

  @override
  String get verifyYourNumber => 'Verifieer uw nummer';

  @override
  String get deleteFlowConfirmSubtitle => 'Dit kan niet ongedaan worden gemaakt, ook niet door support.';

  @override
  String get submitAppTermsAgreement =>
      'Door deze app in te dienen, ga ik akkoord met de Servicevoorwaarden en het Privacybeleid van Omi AI';

  @override
  String get stripeSecureDescription => 'Stripe zorgt voor veilige en tijdige overdrachten van uw app-inkomsten';

  @override
  String get categoryProductivity => 'Productiviteit';

  @override
  String chatWithAppName(String appName) {
    return 'Chat met $appName';
  }

  @override
  String get enableCloudStorage => 'Cloudopslag inschakelen';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl => 'Ongeldige webhook-URL voor realtime-transcriptie';

  @override
  String get wrappedShow => 'SERIE';

  @override
  String get speakTranscribeSummarize => 'Spreek. Transcribeer. Vat samen.';

  @override
  String get pricingPaid => 'Betaald';

  @override
  String get successfullyConnectedAsana => 'Succesvol verbonden met Asana!';

  @override
  String get rating => 'Beoordeling';

  @override
  String get chatQuotaExceededReply =>
      'Je hebt je maandelijkse limiet bereikt. Upgrade om zonder beperkingen met Omi te blijven chatten.';

  @override
  String get pendantIsListeningTitle => 'Je hanger luistert';

  @override
  String get usageBestDay => 'Best day';

  @override
  String get personWhyConfidence => 'Waarom?';

  @override
  String get permissionDescCreateConversations => 'Deze app kan nieuwe gesprekken maken.';

  @override
  String get reviewSpellingCustom => 'Typ het';

  @override
  String resetsInHours(int count) {
    return 'Reset over $count uur';
  }

  @override
  String get reviewAction => 'Bekijken';

  @override
  String get submitRequest => 'Verzoek indienen';

  @override
  String get phoneCalls => 'Telefoongesprekken';

  @override
  String get actionItemsTab => 'Taken';

  @override
  String get record => 'Opnemen';

  @override
  String get noReviewsFound => 'Geen recensies gevonden';

  @override
  String get oauth => 'OAuth';

  @override
  String get urlCopied => 'URL gekopieerd';

  @override
  String get actionItemReminderTitle => 'Omi-herinnering';

  @override
  String sharedTasksAdded(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count taken aan je lijst toegevoegd',
      one: '1 taak aan je lijst toegevoegd',
    );
    return '$_temp0';
  }

  @override
  String get contactsPermissionRequiredForSms => 'Contactentoestemming is vereist om via SMS te delen';

  @override
  String get apiKeyRevokedSuccessfully => 'API-sleutel succesvol ingetrokken';

  @override
  String get authorizationSuccessful => 'Autorisatie succesvol!';

  @override
  String get unpinAction => 'Losmaken';

  @override
  String get syncingStatus => 'Synchroniseren';

  @override
  String get audioFormatLabel => 'Audioformaat';

  @override
  String get phoneSelectCountryTitle => 'Land kiezen';

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'Top $percentile% gebruiker';
  }

  @override
  String get phoneContactsTab => 'Contacten';

  @override
  String get reply => 'Reageren';

  @override
  String get openingShareSheet => 'Deelvenster openen…';

  @override
  String get creatingAppIcon => 'App-pictogram maken…';

  @override
  String get deviceOnboardingStartSpeaking => 'Begin met praten…';

  @override
  String get wrappedAHilariousMoment => 'Een hilarisch moment';

  @override
  String get paidApp => 'Betaalde app';

  @override
  String get wrappedStruggleHeader => 'Strijd';

  @override
  String get speakerTagPromptDontKnow => 'Iemand die ik niet ken';

  @override
  String get wrappedStarting => 'Starten…';

  @override
  String get getButton => 'Download';

  @override
  String get syncCustomSttWarningTitle => 'Synchroniseren gebruikt Omi-transcriptie';

  @override
  String get download => 'Downloaden';

  @override
  String get addScreenshot => 'Screenshot toevoegen';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return 'Verbinding met $serviceName mislukt: $error';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'Maak opnieuw verbinding om uw $deviceName te blijven gebruiken.';
  }

  @override
  String get configureDailySummaryDigest => 'Configureer je dagelijkse takenoverzicht';

  @override
  String get showShortConversationsDesc => 'Gesprekken korter dan de drempel weergeven';

  @override
  String participantsSummaryUncounted(String name) {
    return '$name en anderen';
  }

  @override
  String fairUseBudgetUsed(String used, String limit) {
    return '${used}m / ${limit}m';
  }

  @override
  String get add => 'Toevoegen';

  @override
  String get disconnect => 'Loskoppelen';

  @override
  String get enterApiKey => 'Voer je API-sleutel in';

  @override
  String get msgMaxFilesLimit => 'U kunt maximaal 4 bestanden selecteren';

  @override
  String get space => 'Spatie';

  @override
  String get upgrade => 'Upgraden';

  @override
  String get tapToView => 'Tik om te bekijken';

  @override
  String get summaryTemplate => 'Samenvattingssjabloon';

  @override
  String get chatAppsWaitingTitle => 'Wachten op je bericht';

  @override
  String yesterdayAtTime(String time) {
    return 'Gisteren om $time';
  }

  @override
  String get cancel => 'Annuleren';

  @override
  String get checkingAppleWatch => 'Apple Watch controleren…';

  @override
  String syncCardDownloadPercentSpeed(int percent, String speed) {
    return '$percent% · $speed KB/s';
  }

  @override
  String get finalTouches => 'Laatste aanpassingen';

  @override
  String get weekdaySat => 'Za';

  @override
  String get fairUseWeekly => 'Wekelijks voortschrijdend';

  @override
  String get invalidPaymentUrl => 'Ongeldige betalings-URL';

  @override
  String get transcriptionSlowerOnDevice => 'On-device transcriptie kan langzamer zijn op dit apparaat.';

  @override
  String get noListsInSpace => 'Geen lijsten gevonden in deze ruimte';

  @override
  String get deviceDiagnostics => 'Apparaatdiagnostiek';

  @override
  String get askAnything => 'Vraag wat je wilt';

  @override
  String confidenceMeterLabel(String level) {
    return 'Zekerheid: $level';
  }

  @override
  String get permissionReadTasks => 'Taken lezen';

  @override
  String get skipForNow => 'Nu overslaan';

  @override
  String get setupCompletedUrl => 'URL voor voltooide installatie';

  @override
  String get saySomething => 'Zeg iets…';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get chatAppsEntryTitle => 'Chat met Omi';

  @override
  String get chatAppsTelegramStepOpen => 'Tik hieronder op Open Telegram';

  @override
  String get pleaseEnterValidPayPalMeLink => 'Voer een geldige PayPal.me-link in';

  @override
  String get syncFlowIntro =>
      'Opnamen worden van je apparaat naar deze telefoon overgezet en lokaal opgeslagen en vervolgens geüpload naar de server van Omi, waar ze worden getranscribeerd en omgezet in gesprekken.';

  @override
  String get cantFindDeviceHint =>
      'Kun je je apparaat niet vinden? Zorg dat het aan staat en dicht bij je telefoon is en zoek opnieuw.';

  @override
  String get tryAdjustingFilter => 'Probeer je zoekopdracht of filter aan te passen';

  @override
  String get failedConnectionsRecent => 'Mislukte verbindingen (laatste 7 dagen)';

  @override
  String get captureSourceCall => 'Gesprek';

  @override
  String get storageLocationPhone => 'Telefoon';

  @override
  String get voiceMatchClose => 'Sterke match';

  @override
  String get reviewChangeUndone => 'Ongedaan gemaakt. Omi doet dit niet uit zichzelf opnieuw.';

  @override
  String get tasksNoProject => 'Geen project';

  @override
  String get dataAccessNotice => 'Melding gegevenstoegang';

  @override
  String deviceStorageFree(String free) {
    return '$free vrij';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'Al geëxporteerd naar $platform';
  }

  @override
  String get recapDeletedSnackbar => 'Samenvatting verwijderd';

  @override
  String get apiUrlRequired => 'API-URL is vereist';

  @override
  String get getOmiUnlimitedFree =>
      'Krijg Omi Unlimited gratis door uw gegevens bij te dragen voor het trainen van AI-modellen.';

  @override
  String get wrappedShare => 'Delen';

  @override
  String get tasksTomorrow => 'Morgen';

  @override
  String get chatAppsShowInAppOn => 'Aan: ze verschijnen in de Omi-app als chats die je alleen kunt lezen.';

  @override
  String get errorActivatingAppIntegration =>
      'Fout bij het activeren van de app. Als het een integratie-app is, zorg ervoor dat de installatie is voltooid.';

  @override
  String get readChatRepliesAloudDescription => 'Spreekt alleen als Spraakantwoord dit toestaat.';

  @override
  String get addDueDate => 'Vervaldatum toevoegen';

  @override
  String get translated => 'vertaald';

  @override
  String get dontAskAgain => 'Niet opnieuw vragen';

  @override
  String get fullAccessScope => 'Volledige toegang';

  @override
  String get firmwareUpdated => 'Firmware bijgewerkt';

  @override
  String get deviceOnboardingVoiceReplyPreviewThroughPhoneSpeaker => 'Via de telefoonluidspreker';

  @override
  String get prompt => 'Prompt';

  @override
  String get dreamReportDeletedItem => 'Verwijderd item';

  @override
  String chatAppsDisconnectChannel(String app) {
    return '$app ontkoppelen';
  }

  @override
  String get appleHealthDeniedBody =>
      'Omi heeft geen toestemming om je Apple Health-gegevens te lezen. Schakel het in via iOS-instellingen → Privacy en beveiliging → Gezondheid → Omi.';

  @override
  String endsOnDate(String date) {
    return 'Eindigt op $date';
  }

  @override
  String get searchSettings => 'Instellingen zoeken';

  @override
  String get pairingDescNeoOne =>
      'Houd de aan-/uitknop ingedrukt totdat de LED knippert. Het apparaat is dan vindbaar.';

  @override
  String get checkingNextSevenDays => 'De komende 7 dagen controleren';

  @override
  String get confidenceLikely => 'Waarschijnlijk';

  @override
  String get appleHealthFeatureChatTitle => 'Chat over je gezondheid';

  @override
  String get loadingDevices => 'Apparaten laden…';

  @override
  String get writeSomething => 'Schrijf iets';

  @override
  String syncCardProgressOf(int current, int total) {
    return '$current van $total';
  }

  @override
  String get unableToOpenWatchApp =>
      'Kan Apple Watch-app niet openen. Open handmatig de Watch-app op je Apple Watch en installeer Omi vanuit het gedeelte \"Beschikbare apps\".';

  @override
  String get dreamReportWouldFix => 'Zou herstellen';

  @override
  String get doubleTap => 'Dubbel tikken';

  @override
  String get speakerTagPromptSomeoneElse => 'Iemand anders…';

  @override
  String get cancelTransfer => 'Overdracht annuleren';

  @override
  String get capabilityExternalIntegration => 'Externe integratie';

  @override
  String get sttLanguageFollowsPrimary => 'Volgt je primaire taal';

  @override
  String get wrappedCringeMomentTitle => 'Gênant moment';

  @override
  String get allRecordingsSynced => 'Alle opnames zijn gesynchroniseerd';

  @override
  String get reviewConfirm => 'Bevestigen';

  @override
  String get checkBackLaterForNewApps => 'Kom later terug voor nieuwe apps';

  @override
  String get referAFriend => 'Verwijs een vriend';

  @override
  String cleanUpLead(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other:
          'Omi weet het niet zeker bij deze $count mensen. De meeste zijn namen die verkeerd zijn verstaan in transcripties. Vink uit wie je wilt behouden.',
      one: 'Omi weet het niet zeker bij deze persoon. Vink uit om te behouden.',
    );
    return '$_temp0';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return '$item privé maken?';
  }

  @override
  String get chatQuotaSubtitle => 'AI chat messages used with Omi this month.';

  @override
  String get failedTryAgain => 'Mislukt? Probeer opnieuw';

  @override
  String get deleteAllFiles => 'Alle opnames verwijderen';

  @override
  String get onDeviceModelDownloadSuccess => 'Model gedownload';

  @override
  String get reviewNoChangesTitle => 'Nog geen wijzigingen';

  @override
  String get useMobileAppToCapture => 'Gebruik je mobiele app om audio vast te leggen';

  @override
  String get setYourName => 'Stel uw naam in';

  @override
  String get tasksGroupByDate => 'Groeperen op datum';

  @override
  String get diagnosticsLast7Days => 'Laatste 7 dagen';

  @override
  String get deviceOnboardingStatusConnected => 'Verbonden';

  @override
  String get actionItemCreatedSuccessfully => 'Taak succesvol aangemaakt';

  @override
  String get thursdayAbbr => 'Do';

  @override
  String get wifiConfiguration => 'WiFi-configuratie';

  @override
  String get cancelReasonFoundAlternative => 'Een alternatief gevonden';

  @override
  String get process => 'Verwerken';

  @override
  String get help => 'Hulp';

  @override
  String get rollbackConfirmTitle => 'Firmware terugzetten?';

  @override
  String get visibility => 'Zichtbaarheid';

  @override
  String get evidenceNotHeard => 'Nog niet gehoord in een gesprek';

  @override
  String get messageReported => 'Bericht succesvol gerapporteerd.';

  @override
  String get readyToChat => '✨ Klaar om te chatten!';

  @override
  String get tryDifferentFilter => 'Probeer een ander filter';

  @override
  String get header => 'Koptekst';

  @override
  String get wrappedBestHeader => 'Beste';

  @override
  String get memoryDontUse => 'Niet gebruiken';

  @override
  String get appStore => 'App Store';

  @override
  String get deleteMeetingScreenshotMessage =>
      'Hiermee wordt de schermafbeelding uit de notitie van deze vergadering verwijderd. Dit kan niet ongedaan worden gemaakt.';

  @override
  String get categoryShopping => 'Winkelen';

  @override
  String get voiceResponseOff => 'Uit';

  @override
  String get bluetoothNeeded =>
      'Omi heeft Bluetooth nodig om verbinding te maken met je wearable. Schakel Bluetooth in en probeer het opnieuw.';

  @override
  String get googleCalendarComingSoon => 'Google Agenda-integratie komt binnenkort!';

  @override
  String get max => 'Max';

  @override
  String get homeScreen => 'Startscherm';

  @override
  String get chatAppsTelegramStepStart => 'Tik op Start in je chat met Omi';

  @override
  String get greetingAfternoon => 'Goedemiddag';

  @override
  String get unpair => 'Ontkoppelen';

  @override
  String get diagnosticsVerdictReconnects => 'Maakt zelf opnieuw verbinding';

  @override
  String get macOsCalendar => 'macOS-agenda';

  @override
  String get onboardingSetupStepLanguage => 'Transcriptie wordt afgestemd op jouw taal';

  @override
  String get mcpOAuthSetup =>
      'Voeg op claude.ai een aangepaste connector toe en plak de server-URL. Als Claude om een geavanceerde OAuth Client ID vraagt, gebruik dan de waarde hieronder en laat het geheim leeg — gebruik je MCP API-sleutel nooit als OAuth-geheim.';

  @override
  String get wednesdayAbbr => 'Wo';

  @override
  String get selectAudioInput => 'Selecteer audio-ingang';

  @override
  String get deviceDisconnectedMessage => 'Je Omi is losgekoppeld 😔';

  @override
  String get reprocessConversation => 'Gesprek opnieuw verwerken';

  @override
  String get goal => 'DOEL';

  @override
  String mergeConversationsMessage(int count) {
    return 'Dit combineert $count gesprekken tot één. Alle inhoud wordt samengevoegd en opnieuw gegenereerd.';
  }

  @override
  String get everyXSeconds => 'Elke x seconden';

  @override
  String get chatAppsLocked => 'Vereist Omi Pro';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl => 'Ongeldige webhook-URL voor aangemaakte conversatie';

  @override
  String get secureAuthViaAppleId => 'Veilige authenticatie via Apple ID';

  @override
  String connectingToDeviceName(String deviceName) {
    return 'Verbinden met $deviceName';
  }

  @override
  String get listeningSubtitle => 'Totale tijd dat Omi actief heeft geluisterd.';

  @override
  String get capturing => 'Bezig met vastleggen';

  @override
  String get enterWifiNetworkName => 'Voer de WiFi-netwerknaam in';

  @override
  String get noAppsAvailable => 'Geen apps beschikbaar';

  @override
  String get installingFirmware => 'Firmware installeren';

  @override
  String get transferToPhone => 'Overdragen naar telefoon';

  @override
  String get voiceResponseMode => 'Spraakantwoord';

  @override
  String get messageCopied => '✨ Bericht gekopieerd naar klembord';

  @override
  String get discardRecordingMessage =>
      'Je spraakmonster is nog niet opgeslagen. Als je nu weggaat, wordt het verwijderd.';

  @override
  String chatAppsIMessageBody(String code) {
    return 'Hoi Omi, koppelcode $code';
  }

  @override
  String get failedToRefreshWhoopStatus => 'Kan de Whoop-verbindingsstatus niet vernieuwen.';

  @override
  String get youreOnAnnualPlan => 'U bent op het jaarabonnement';

  @override
  String timeHoursPlural(int count) {
    return '$count uur';
  }

  @override
  String get usageOnline => 'Online';

  @override
  String get validPortRequired => 'Geldige poort is vereist';

  @override
  String get howItWorks => 'Hoe het werkt';

  @override
  String get viewTemplate => 'Template bekijken';

  @override
  String get dreamReportNothingFound => 'Niets te herstellen';

  @override
  String get personTalkTime => 'Spreektijd';

  @override
  String get evidenceNoVoice => 'Nog geen stemvoorbeeld';

  @override
  String get makeMyAppPublic => 'Mijn app openbaar maken';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'Bluetooth-toestemmingsstatus: $status. Controleer Systeemvoorkeuren.';
  }

  @override
  String get noRecordings => 'Geen opnames';

  @override
  String get usageChatThisMonth => 'Chat this month';

  @override
  String get addAppEnterChatPrompt => 'Voer een chatprompt in voor uw app';

  @override
  String daysAgo(int count) {
    return '$count dagen geleden';
  }

  @override
  String get processing => 'Verwerken';

  @override
  String get deviceOnboardingStatusTurningOff => 'Aan het uitzetten…';

  @override
  String get newTag => 'NIEUW';

  @override
  String get permissionDescReadTasks => 'Deze app heeft toegang tot je taken.';

  @override
  String get time => 'Tijd';

  @override
  String get recording => 'Opnemen';

  @override
  String get speakerTagPromptWhoIsThis => 'Wie is dit?';

  @override
  String chatUsageMessagesNoLimit(String used) {
    return 'Chat: $used berichten deze maand';
  }

  @override
  String get importantTradeoffs => 'Belangrijke afwegingen:';

  @override
  String get makeAllPublic => 'Alle herinneringen openbaar maken';

  @override
  String get noSpeechDesc =>
      'We konden geen spraak detecteren. Zorg ervoor dat je minimaal 10 seconden en niet meer dan 3 minuten spreekt.';

  @override
  String get searchPartialFailure => 'Sommige resultaten konden niet worden geladen';

  @override
  String get prerecordedTranscript => 'Vooraf opgenomen';

  @override
  String get confirm => 'Bevestigen';

  @override
  String get statusCalling => 'Bellen…';

  @override
  String get wrappedConvos => 'gesprekken';

  @override
  String get unresolvedSpeakersTitle => 'Over sprekerlabels';

  @override
  String get writeYourReply => 'Schrijf je reactie…';

  @override
  String get localCopiesSection => 'Lokale kopieën';

  @override
  String get noSummaryYet => 'Nog geen samenvatting';

  @override
  String get wrappedBiggestHeader => 'Grootste';

  @override
  String get error => 'Fout';

  @override
  String get deviceWillRestart => 'Je apparaat wordt opnieuw opgestart.';

  @override
  String get consentDataMessage =>
      'Door verder te gaan worden uw gesprekken, opnames en persoonlijke informatie veilig opgeslagen op onze servers. Uw audio-opnames en transcripties worden verwerkt door AI-diensten van derden (waaronder Deepgram voor transcriptie en OpenAI voor analyse) om u AI-gestuurde inzichten te bieden en alle app-functies mogelijk te maken.';

  @override
  String get connectMacOsCalendar => 'Verbind je lokale macOS-agenda';

  @override
  String get captureSourcePhoneMic => 'Telefoonmicrofoon';

  @override
  String get setupCompleted => 'Voltooid';

  @override
  String get installOmiOnAppleWatchDescription =>
      'Om je Apple Watch met Omi te gebruiken, moet je eerst de Omi-app op je horloge installeren.';

  @override
  String get toggleControlBar => 'Schakel bedieningsbalk';

  @override
  String get onboardingBluetoothDeniedSystemPrefs =>
      'Bluetooth-toestemming geweigerd. Verleen toestemming in Systeemvoorkeuren.';

  @override
  String get syncCancelled => 'Synchronisatie geannuleerd';

  @override
  String get firmwareDisconnectUsb => 'USB ontkoppelen';

  @override
  String get processNow => 'Nu verwerken';

  @override
  String get appIdNotFoundError => 'App-ID niet gevonden';

  @override
  String get editDueDate => 'Vervaldatum bewerken';

  @override
  String get home => 'Home';

  @override
  String get tasksOverdue => 'Achterstallig';

  @override
  String get statusCompleted => 'Voltooid';

  @override
  String get otaStarting => 'Update wordt gestart…';

  @override
  String get monthApr => 'Apr';

  @override
  String get conversationTasksEmptyMessage => 'Taken uit dit gesprek verschijnen hier.';

  @override
  String get useDifferentAccount => 'Ander account gebruiken';

  @override
  String get reviewReasonNotUseful => 'Niet nuttig';

  @override
  String get anonymousUser => 'Anonieme gebruiker';

  @override
  String get viewPlansDescription => 'Beheer je abonnement en bekijk gebruiksstatistieken';

  @override
  String invalidJson(String error) {
    return 'Ongeldige JSON: $error';
  }

  @override
  String get deleteActionItem => 'Taak verwijderen';

  @override
  String get confirmCancellation => 'Annulering bevestigen';

  @override
  String get tapToDelete => 'Tik om te verwijderen';

  @override
  String get onTheCallEnterThisCode => 'Voer tijdens het gesprek deze code in';

  @override
  String get stableFirmware => 'Stabiele firmware';

  @override
  String get triggerEvents => 'Triggergebeurtenissen';

  @override
  String get speakerTagPromptSaveVoicesTitle => 'Stemmen onthouden van mensen die je een naam geeft';

  @override
  String get syncedFilesDeleted => 'Gesynchroniseerde opnames verwijderd';

  @override
  String get cloudStorageDesc =>
      'Na het uploaden worden uw opnames verwerkt en getranscribeerd. Gesprekken zijn binnen een minuut beschikbaar.';

  @override
  String get failedToUpdateFolder => 'Kan map niet bijwerken';

  @override
  String dreamReportFound(int fixes, int asks) {
    String _temp0 = intl.Intl.pluralLogic(
      fixes,
      locale: localeName,
      other: '$fixes oplossingen',
      one: '1 oplossing',
    );
    String _temp1 = intl.Intl.pluralLogic(
      asks,
      locale: localeName,
      other: '$asks suggesties',
      one: '1 suggestie',
    );
    return '$_temp0 · $_temp1';
  }

  @override
  String get anotherPlatform => 'een ander platform';

  @override
  String get wrappedTopPhrasesLabel => 'TOP ZINNEN';

  @override
  String get dataAccessWarning =>
      'Deze app heeft toegang tot uw gegevens. Omi AI is niet verantwoordelijk voor hoe uw gegevens worden gebruikt, gewijzigd of verwijderd door deze app';

  @override
  String get pleaseCompleteAuthentication => 'Voltooi de authenticatie in je browser. Keer daarna terug naar de app.';

  @override
  String get dailySummaryTitle => 'Dagelijkse Samenvatting';

  @override
  String get managePeople => 'Personen beheren';

  @override
  String get dreamReportEmptyBody => 'Dream bekijkt ongeveer elk uur wat er in je account is veranderd.';

  @override
  String get couldNotOpenPaymentSettings => 'Kon betalingsinstellingen niet openen. Probeer het opnieuw.';

  @override
  String get locationServiceDisabled => 'Locatieservice uitgeschakeld';

  @override
  String get understanding => 'Begrijpen';

  @override
  String get recapDeleteFailed => 'Kan de samenvatting niet verwijderen. Probeer het later opnieuw.';

  @override
  String get deleteKnowledgeGraphQuestion => 'Kennisgrafiek verwijderen?';

  @override
  String get wrappedYourBuddy => 'Je maat!';

  @override
  String chatAppsChatIn(String app) {
    return 'Chat in $app';
  }

  @override
  String get speechDurationDescription => 'Zorg ervoor dat je minimaal 5 seconden en maximaal 90 seconden spreekt.';

  @override
  String get reviewReasonAlreadyDone => 'Al gedaan';

  @override
  String get phoneSetupStep2Title => 'Voer een verificatiecode in';

  @override
  String get tasksClearCompleted => 'Verwijder voltooide';

  @override
  String get searchingForDevices => 'Zoeken naar apparaten';

  @override
  String get siriIndexSettingDescription =>
      'Allow Siri to find your conversations, memories, and tasks on this device. Turning this off removes them from Apple search.';

  @override
  String get markIncomplete => 'Markeren als onvolledig';

  @override
  String get onboardingBluetoothRequired => 'Bluetooth-toestemming is vereist om verbinding te maken met uw apparaat.';

  @override
  String get searchAppsPlaceholder => 'Zoek in 1500+ apps';

  @override
  String get pleaseEnterName => 'Voer een naam in';

  @override
  String get paymentMethodCharged =>
      'Uw bestaande betaalmethode wordt automatisch belast wanneer uw maandabonnement eindigt';

  @override
  String get allMemoriesAreNowPublic => 'Alle herinneringen zijn nu openbaar';

  @override
  String taskDueDate(String date) {
    return 'Deadline $date';
  }

  @override
  String get pendantPausesUntilYouFinish => 'Hanger pauzeert tot je klaar bent';

  @override
  String get failedToAuthorize => 'Autorisatie mislukt. Probeer het opnieuw.';

  @override
  String get mergeConversationsSuccessTitle => 'Gesprekken succesvol samengevoegd';

  @override
  String get peopleFilterNeedsVoice => 'Stem nodig';

  @override
  String get clickToBeginRecordingSystemAudio => 'Klik om systeemaudio-opname te starten';

  @override
  String get fairUseStageRestrict => 'Geblokkeerd';

  @override
  String get nextResult => 'Volgend resultaat';

  @override
  String get chatAppsContactsApp => 'Contacten';

  @override
  String get categoryEmotionalSupport => 'Emotionele ondersteuning';

  @override
  String get wrappedYourHeader => 'Je';

  @override
  String get pendantPausesDuringCall => 'Hanger pauzeert tijdens het gesprek';

  @override
  String noConversationsOnDate(String date) {
    return 'Geen gesprekken op $date';
  }

  @override
  String get chatStarterYesterday => 'Wat heb ik gisteren gedaan?';

  @override
  String get entityNotRight => 'Klopt dit niet?';

  @override
  String get failedToCreateShareLink => 'Kan deellink niet aanmaken';

  @override
  String get sync => 'Synchroniseren';

  @override
  String get micGainDescMax => 'Maximum - gebruik met voorzichtigheid';

  @override
  String get sttNone => 'Geen';

  @override
  String get chatAppsCodeNote => 'De code werkt één keer en verloopt na 10 minuten.';

  @override
  String get aiGenAppCreatedSuccessfully => 'App succesvol aangemaakt!';

  @override
  String lastNEvents(int count) {
    return 'Laatste $count gebeurtenissen';
  }

  @override
  String get phoneDeleteButton => 'Verwijderen';

  @override
  String get systemAudio => 'Systeem';

  @override
  String get checkOutMyMemoryGraph => 'Bekijk mijn geheugengrafiek!';

  @override
  String get feedbackTitleBatteryDrain => 'Vertel ons over de batterijproblemen';

  @override
  String get startCallRecording => 'Gespreksopname starten';

  @override
  String get monthlyPlanContinues => 'Uw huidige maandabonnement loopt door tot het einde van uw factureringsperiode';

  @override
  String get syncStepUploadDesc => 'Je opname wordt naar Omi\'s server gestuurd';

  @override
  String get otaKeepNearby => 'Houd je apparaat tijdens de update aan en in de buurt, en sluit de app niet.';

  @override
  String get updatePayPalDetails => 'PayPal-gegevens bijwerken';

  @override
  String get termsOfUse => 'Gebruiksvoorwaarden';

  @override
  String get apiKeyCreated => 'API-sleutel aangemaakt!';

  @override
  String get deviceOnboardingVoiceReplyPreviewIdle => 'Luister naar je laatste antwoord';

  @override
  String get starOngoing => 'Lopend gesprek als favoriet markeren';

  @override
  String get largeModelWarning =>
      'Dit model is groot en kan de app laten crashen of zeer traag draaien op mobiele apparaten.\n\n\"small\" of \"base\" wordt aanbevolen.';

  @override
  String get selectLanguage => 'Selecteer taal';

  @override
  String get professionExecutive => 'Directeur';

  @override
  String get importFileTooLarge => 'Dit bestand is te groot om te importeren.';

  @override
  String get updateRequiredTitle => 'Update vereist';

  @override
  String get syncStepBackedUp => 'Gesprek klaar';

  @override
  String get openWatchApp => 'Watch-app openen';

  @override
  String get keyNameLabel => 'SLEUTELNAAM';

  @override
  String bulkExportSuccess(int count, String platform) {
    return '$count geëxporteerd naar $platform';
  }

  @override
  String get couldNotProcessSubscription => 'Kon abonnement niet verwerken. Probeer opnieuw.';

  @override
  String get memorizingYourVoice => 'Je stem wordt onthouden…';

  @override
  String get processingAudio => 'Audio verwerken';

  @override
  String get syncYourRecordings => 'Synchroniseer je opnames';

  @override
  String get resetToDefault => 'Terugzetten naar standaard';

  @override
  String get deleteConversation => 'Gesprek verwijderen';

  @override
  String get flashCustomFirmwareDescription => 'Aangepaste firmwarebuilds flashen';

  @override
  String get deviceUpToDate => 'Uw apparaat is up-to-date';

  @override
  String get raybanMetaMusicPauseNote =>
      'Muziek op je telefoon wordt gepauzeerd terwijl de microfoon van de bril in gebruik is.';

  @override
  String get appleHealthNotAvailable => 'Apple Health is niet beschikbaar op dit apparaat';

  @override
  String hints(String text) {
    return 'Tips: $text';
  }

  @override
  String get cloudProvider => 'Cloud-provider';

  @override
  String get chooseAnyFileType => 'Kies elk bestandstype';

  @override
  String get reset => 'Resetten';

  @override
  String get automaticallyCreateNewPerson =>
      'Maak automatisch een nieuwe persoon aan wanneer een naam wordt gedetecteerd in de transcriptie.';

  @override
  String get timeout2Minutes => '2 minuten';

  @override
  String get newMemory => '✨ Nieuw geheugen';

  @override
  String get chatAppsMoreComing => 'Er komen meer apps.';

  @override
  String get couldNotLoadKnowledgeGraph => 'Kennisgrafiek kon niet worden geladen';

  @override
  String get voiceSettingsAskToTagSubtitle => 'Af en toe vraagt Omi wie er sprak in je recente gesprekken';

  @override
  String get developer => 'Ontwikkelaar';

  @override
  String get connectionNeeded => '🌐 Verbinding nodig';

  @override
  String get helpAndAbout => 'Help en over';

  @override
  String get tasksNoDeadline => 'Geen deadline';

  @override
  String get yourDataIsProtected => 'Je gegevens zijn beschermd en worden beheerst door ons ';

  @override
  String get confirmDeletion => 'Verwijdering bevestigen';

  @override
  String get speakerTagPromptClosestVoices => 'Dichtstbijzijnde stemmen';

  @override
  String get quicklyPopulateRequest => 'Snel invullen met bekend provider verzoekformaat';

  @override
  String get exportTranscript => 'Transcriptie exporteren';

  @override
  String get resetsSoon => 'Reset binnenkort';

  @override
  String get showPhoneCallButtonTitle => 'Toon belknop';

  @override
  String get wrappedAChallenge => 'Een uitdaging';

  @override
  String get revokeKey => 'Sleutel intrekken';

  @override
  String get dailyRecaps => 'Dagelijkse Samenvattingen';

  @override
  String get processingConversationProgress => 'Gesprek wordt verwerkt…';

  @override
  String get freeMinutesMonth => '300 gratis minuten/maand inbegrepen. Onbeperkt met ';

  @override
  String get downloadWhisperModel => 'Download een whisper-model om on-device transcriptie te gebruiken';

  @override
  String get noMemoriesInCategories => 'Geen herinneringen in deze categorieën';

  @override
  String get checkingNextDays => 'Volgende 30 dagen controleren';

  @override
  String get createAndSubmitNewApp => 'Maak en dien een nieuwe app in';

  @override
  String get chatAppsInTheMeantime => 'Intussen';

  @override
  String get deleteFlowReasonTitle => 'Waarom vertrek je?';

  @override
  String get tasksSelectAll => 'Alles selecteren';

  @override
  String get webhookUrl => 'Webhook-URL';

  @override
  String get selected => 'Geselecteerd';

  @override
  String get batteryDrainIncrease => 'Het batterijverbruik zal aanzienlijk toenemen.';

  @override
  String get dreamReportFixed => 'Hersteld';

  @override
  String get failedToConnectClickUpRetry => 'Verbinding met ClickUp mislukt. Probeer het opnieuw.';

  @override
  String get serverUrl => 'Server-URL';

  @override
  String get starred => 'Met ster';

  @override
  String get speakerTagPromptClipUnavailable => 'Kan dit fragment niet afspelen';

  @override
  String get feedbackSubtitleFoundAlternative => 'We horen graag wat je aandacht trok.';

  @override
  String get omiButtonActions => 'Omi-knopacties';

  @override
  String get invalidRecordingDesc => 'Zorg ervoor dat je minimaal 5 seconden en niet meer dan 90 seconden spreekt.';

  @override
  String get switchApiConfirmTitle => 'API-omgeving wisselen';

  @override
  String gattError(String code) {
    return 'GATT-fout ($code)';
  }

  @override
  String get aiGenRegenerateIcon => 'Pictogram opnieuw genereren';

  @override
  String get connectTaskAppToExport => 'Verbind een taken-app in Instellingen om te exporteren';

  @override
  String get firmwareFlashed => 'Firmware geflasht';

  @override
  String get addPerson => 'Persoon toevoegen';

  @override
  String get cancelConsequencesSubtitle =>
      'We raden je sterk aan om je andere opties te verkennen in plaats van te annuleren.';

  @override
  String get transcriptCopiedToClipboard => 'Transcriptie gekopieerd naar klembord';

  @override
  String get monthNov => 'Nov';

  @override
  String get switchedToOnDevice => 'Overgeschakeld naar transcriptie op apparaat';

  @override
  String get phoneMicOfflineFallbackMessage =>
      'Geen verbinding — er wordt lokaal opgenomen. Het wordt getranscribeerd zodra je weer online bent.';

  @override
  String get scopeUserConversations => 'Gebruikersgesprekken';

  @override
  String get otherAppResults => 'Resultaten van andere apps';

  @override
  String get chatAppsGetNewCode => 'Nieuwe code aanvragen';

  @override
  String get backgroundLocationDenied => 'Achtergrondlocatietoegang geweigerd';

  @override
  String get syncFailureFootnote =>
      'Als de verwerking mislukt, wordt de opname automatisch opnieuw geprobeerd bij de volgende synchronisatie.';

  @override
  String get checkingNext7Days => 'Controleren van de komende 7 dagen';

  @override
  String get monthlyPayouts => 'Maandelijkse uitbetalingen';

  @override
  String get searchLanguageHint => 'Zoek taal op naam of code';

  @override
  String get gotIt => 'Begrepen';

  @override
  String get pleaseEnterAppName => 'Voer de app-naam in';

  @override
  String get newConversations => 'Nieuwe gesprekken';

  @override
  String get learnMoreAtOmiTraining => 'Meer informatie op omi.me/training';

  @override
  String get entityOpenTasks => 'Open taken';

  @override
  String get summary => 'Samenvatting';

  @override
  String get copied => 'Gekopieerd';

  @override
  String get feedbackReasonRecordingDelayedOrStuck => 'Vertraagd of vastgelopen';

  @override
  String get taskIntegrations => 'Taakintegraties';

  @override
  String get tailoredConversationSummaries => 'Op maat gemaakte gesprekssamenvattingen';

  @override
  String get skipThisQuestion => 'Sla deze vraag over';

  @override
  String get descriptionOptional => 'Beschrijving (optioneel)';

  @override
  String get about => 'Over';

  @override
  String shareWithContactsCount(int count) {
    return 'Delen met $count contacten';
  }

  @override
  String get discardChangesTitle => 'Wijzigingen verwerpen?';

  @override
  String get transcriptionDiagnostics => 'Transcriptie-diagnostics';

  @override
  String get syncStatusFileUnavailable => 'Bestand niet beschikbaar';

  @override
  String get createNewApp => 'Nieuwe app maken';

  @override
  String verifiedHoursAgo(int hours) {
    return '${hours}u geleden geverifieerd';
  }

  @override
  String get chatLimitReachedTitle => 'Chatlimiet bereikt';

  @override
  String get wrappedShareText => 'Mijn 2025, onthouden door Omi ✨ omi.me/wrapped';

  @override
  String get reconnectionsRecent => 'Herverbindingen (laatste 7 dagen)';

  @override
  String get appAccess => 'App-toegang';

  @override
  String get description => 'Beschrijving';

  @override
  String phoneFreeCallsRemainingWithMax(int remaining, int limit, int minutes) {
    return 'Nog $remaining van $limit gratis gesprekken deze maand · tot $minutes min per gesprek';
  }

  @override
  String get clearOmisMemory => 'Omi\'s geheugen wissen';

  @override
  String get exportSummary => 'Samenvatting exporteren';

  @override
  String get install => 'Installeren';

  @override
  String get syncStepBackedUpDesc => 'Te vinden onder Gesprekken';

  @override
  String get localProcessingInfo =>
      'Audio wordt lokaal verwerkt. Werkt offline, meer privacy, maar gebruikt meer batterij.';

  @override
  String get connectStripeOrPayPal => 'Verbind Stripe of PayPal om betalingen voor je app te ontvangen.';

  @override
  String get wrappedMomentsHeader => 'Momenten';

  @override
  String get systemDefault => 'Systeemstandaard';

  @override
  String get keepUsingPendant => 'Hanger blijven gebruiken';

  @override
  String get paymentFailedToFetchCountries => 'Ophalen van ondersteunde landen mislukt. Probeer het later opnieuw.';

  @override
  String get micGainDescLow => 'Zeer stil - voor luidruchtige omgevingen';

  @override
  String get errorUpdatingConversationTitle => 'Fout bij bijwerken van gesprekstitel';

  @override
  String timeSecsSingular(int count) {
    return '$count sec';
  }

  @override
  String timeCompactHours(int count) {
    return '${count}u';
  }

  @override
  String get browseInstallCreateApps => 'Blader, installeer en maak apps';

  @override
  String get reddit => 'Reddit';

  @override
  String get chooseFile => 'Bestand kiezen';

  @override
  String participantsSummary(String name, int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count anderen',
      many: '$count anderen',
      few: '$count anderen',
      one: '1 ander',
    );
    return '$name + $_temp0';
  }

  @override
  String get connectingYourStripeAccount => 'Uw Stripe-account verbinden';

  @override
  String get cancelReasonMissingFeatures => 'Ontbrekende functies';

  @override
  String get chatTitle => 'Chat';

  @override
  String get chatAppsNotifyMe => 'Houd me op de hoogte';

  @override
  String get appAccessDesc =>
      'De volgende apps hebben toegang tot je gegevens. Tik op een app om de machtigingen te beheren.';

  @override
  String get captureDisplayDetectionFailed => 'Schermdetectie mislukt. Opname gestopt.';

  @override
  String get recapRegeneratedSnackbar => 'Samenvatting opnieuw gegenereerd';

  @override
  String get speakerTagPromptLabeledYouToast => 'Gelabeld als jij';

  @override
  String get categoryFinancial => 'Financiën';

  @override
  String get chatAppsPrefilled => 'Vooraf ingevuld';

  @override
  String get noSummaryForConversation => 'Geen samenvatting beschikbaar\nvoor dit gesprek.';

  @override
  String get aiPrompts => 'AI-prompts';

  @override
  String get view => 'Bekijken';

  @override
  String get dataAlwaysEncrypted =>
      'Ongeacht het niveau zijn uw gegevens altijd versleuteld in rust en tijdens overdracht.';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item gekopieerd naar klembord';
  }

  @override
  String get currentPlan => 'Huidig';

  @override
  String get phoneCallsUpsellFeature1 => 'Realtime transcriptie van elk gesprek';

  @override
  String get lowBatteryAlertTitle => 'Waarschuwing lage batterij';

  @override
  String get enterConversationTitle => 'Voer gesprekstitel in…';

  @override
  String get pasteJsonConfig => 'Plak je JSON-configuratie hieronder:';

  @override
  String get dreamReportRunLimit => 'Geen handmatige runs meer vandaag';

  @override
  String get translationNoticeMessage =>
      'Omi vertaalt gesprekken naar uw primaire taal. Update deze op elk moment in Instellingen → Profielen.';

  @override
  String get aiGenFailedToRegenerateIcon => 'Kan pictogram niet opnieuw genereren';

  @override
  String get pairingDescBee => 'Druk 5 keer achter elkaar op de knop. Het lampje gaat blauw en groen knipperen.';

  @override
  String sharedTasksAddButton(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count taken toevoegen',
      one: '1 taak toevoegen',
    );
    return '$_temp0';
  }

  @override
  String get paymentFailedToSavePaypal => 'Opslaan PayPal-gegevens mislukt. Probeer het later opnieuw.';

  @override
  String get couldNotLoadCheckout =>
      'De betaalpagina kon niet worden geladen. Controleer je verbinding en probeer het opnieuw.';

  @override
  String get capabilitySummary => 'Samenvatting';

  @override
  String get selectYourCountry => 'Selecteer uw land';

  @override
  String uploadingAudioForTranscription(String duration) {
    return '$duration audio uploaden voor transcriptie…';
  }

  @override
  String get conversationUrlCouldNotBeShared => 'Gesprek-URL kon niet worden gedeeld.';

  @override
  String get otaStartFailed =>
      'Kan de update niet starten. Controleer de wifinaam en het wachtwoord en probeer het opnieuw.';

  @override
  String get triggersWhenAudioBytesReceived => 'Wordt geactiveerd wanneer audiobytes worden ontvangen.';

  @override
  String get wrappedMy2025 => 'Mijn 2025';

  @override
  String timeCompactSecs(int count) {
    return '${count}s';
  }

  @override
  String get shareWithAttendees => 'Delen met deelnemers';

  @override
  String get recordingsSyncAutomatically => 'Opnames worden automatisch gesynchroniseerd — geen actie nodig.';

  @override
  String get whereDidYouHearAboutOmi => 'Hoe heb je ons gevonden?';

  @override
  String get captureMicrophonePermissionInSystemPreferences => 'Geef microfoontoestemming in Systeemvoorkeuren';

  @override
  String audioUploadFailedTapRetry(String duration) {
    return 'Uploaden mislukt — $duration audio bewaard op je telefoon. Tik om het opnieuw te proberen.';
  }

  @override
  String get captureModeLaterDescription => 'Sla audio nu op en transcribeer wanneer je wilt.';

  @override
  String get cleanUpNothingTitle => 'Niets om op te ruimen';

  @override
  String get deletePersonLabel => 'Persoon verwijderen';

  @override
  String get attachedFiles => '📎 Bijgevoegde bestanden';

  @override
  String get editGoal => 'Doel bewerken';

  @override
  String get helpsDiagnoseIssues => 'Helpt problemen diagnosticeren';

  @override
  String get bulkDeleteFailed => 'Taken konden niet worden verwijderd. Probeer het opnieuw.';

  @override
  String get manifestRefreshFailed => 'Manifest vernieuwen mislukt';

  @override
  String get searchPlaceholder => 'Zoeken';

  @override
  String get appOptions => 'App-opties';

  @override
  String get reprocessingConversationProgress => 'Gesprek wordt opnieuw verwerkt…';

  @override
  String get entityWhatOmiKnows => 'Wat Omi weet';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'Het gesprek wordt samengevat na $minutes minuut$suffix stilte.';
  }

  @override
  String get permissionRevokedMessage => 'Wil je dat we ook al je bestaande opnames verwijderen?';

  @override
  String get phoneNumberCallerIdHint => 'Na verificatie wordt dit uw beller-ID';

  @override
  String chatAppsTextThisTo(String address) {
    return 'Niet geopend? Stuur dit naar $address';
  }

  @override
  String get upcomingMeetings => 'Aankomende vergaderingen';

  @override
  String get preparingSystemAudioCapture => 'Systeemaudio-opname voorbereiden';

  @override
  String dreamReportQueued(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count wijzigingen in de wachtrij',
      one: '1 wijziging in de wachtrij',
      zero: 'Geen wijzigingen in de wachtrij',
    );
    return '$_temp0';
  }

  @override
  String get chatReplyFailed => 'Omi kon niet antwoorden. Controleer je verbinding en probeer het opnieuw.';

  @override
  String get noDataToMigrateFinalizing => 'Geen gegevens om te migreren. Afronden…';

  @override
  String get accessibility => 'Toegankelijkheid';

  @override
  String get openOmiOnAppleWatch => 'Open Omi op je\nApple Watch';

  @override
  String get wrappedGettingItDone => 'Het gedaan krijgen';

  @override
  String get rawData => 'Ruwe gegevens';

  @override
  String get passwordsDoNotMatch => 'Wachtwoorden komen niet overeen';

  @override
  String errorInstallingApp(String appName, String error) {
    return 'Fout bij installeren van $appName: $error';
  }

  @override
  String deleteQuoted(String name) {
    return '\"$name\" verwijderen';
  }

  @override
  String get wrappedTopFivePhrases => 'Top 5 zinnen';

  @override
  String get deviceOnboardingHoldButtonHint => 'Houd de knop stevig ingedrukt tot het lampje uitgaat';

  @override
  String get capabilities => 'Mogelijkheden';

  @override
  String get useMcpApiKey => 'Gebruik je MCP API-sleutel';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return '$serviceName-integratie binnenkort beschikbaar';
  }

  @override
  String get wrappedStruggle => 'Uitdaging';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return 'Meldingstoestemmingsstatus: $status. Controleer Systeemvoorkeuren.';
  }

  @override
  String get meetingScreenshotsTitle => 'Wat er op het scherm stond';

  @override
  String verifiedMinutesAgo(int minutes) {
    return '${minutes}min geleden geverifieerd';
  }

  @override
  String get permissionsRequired => 'Machtigingen vereist';

  @override
  String get speakerTagPromptNotSure => 'Weet ik niet';

  @override
  String get current => 'Huidig';

  @override
  String get improveConnectionAction => 'Begrepen';

  @override
  String get profile => 'Profiel';

  @override
  String get audioPlaybackFailed => 'Kan audio niet afspelen. Het bestand is mogelijk beschadigd of ontbreekt.';

  @override
  String get billingYearly => 'Jaarlijks';

  @override
  String get batteryUsageHigher => 'Batterijverbruik zal hoger zijn dan cloud transcriptie.';

  @override
  String get permissionsLabel => 'MACHTIGINGEN';

  @override
  String get enhanceTranscriptAccuracy => 'Verbeter transcriptnauwkeurigheid';

  @override
  String get connectedStatus => 'Verbonden';

  @override
  String get microphonePermissionDenied =>
      'Microfoontoegang geweigerd. Verleen toestemming in Systeemvoorkeuren > Privacy & beveiliging > Microfoon.';

  @override
  String get onDeviceModelDownloadSuccessDesc => 'Whisper-model succesvol gedownload';

  @override
  String get storageLocationLimitlessPendant => 'Limitless Pendant';

  @override
  String get chatAppsLinkExpired => 'Die link is verlopen. Tik op Open Telegram voor een nieuwe.';

  @override
  String get captureOfflineBuffering => 'Offline, bufferen';

  @override
  String get pleaseCheckInternetConnection => 'Controleer uw internetverbinding en probeer het opnieuw';

  @override
  String get todaysScore => 'Score van vandaag';

  @override
  String get conversationReprocessed => 'Gesprek bijgewerkt';

  @override
  String get loadingDuration => 'Duur laden…';

  @override
  String get noSummary => 'Geen samenvatting';

  @override
  String get raybanMetaMicrophoneReady => 'Microfoon gereed';

  @override
  String get applyFilters => 'Filters toepassen';

  @override
  String get appDescriptionPlaceholder =>
      'Mijn geweldige app is een geweldige app die geweldige dingen doet. Het is de beste app ooit!';

  @override
  String get cancelSubscriptionKeepAccessMessage => 'Je houdt toegang tot het einde van de huidige factuurperiode.';

  @override
  String get editYourReview => 'Bewerk uw beoordeling';

  @override
  String get actionItemsTitle => 'Taken';

  @override
  String get raybanMetaAudioOnlyTitle => 'Ray-Ban Meta alleen-audiomodus';

  @override
  String get reviewSomeoneElse => 'Iemand anders…';

  @override
  String get betaTesterMessage =>
      'U bent een bètatester voor deze app. Deze is nog niet openbaar. Deze wordt openbaar na goedkeuring.';

  @override
  String chatAppsIMessageTo(String address) {
    return 'Aan: Omi · $address';
  }

  @override
  String get comingSoon => 'Binnenkort beschikbaar';

  @override
  String rollbackConfirmMessage(String version) {
    return 'Dit vervangt uw huidige firmware door de laatste stabiele versie ($version). Uw apparaat wordt opnieuw opgestart na de update.';
  }

  @override
  String get termsOfService => 'Servicevoorwaarden';

  @override
  String get wrappedNotMentioned => 'Niet genoemd';

  @override
  String get deviceDisconnectedNotificationTitle => 'Uw Omi-apparaat is losgekoppeld';

  @override
  String get rayBanMetaMicPickerDescription =>
      'Selecteer de Bluetooth-microfoon van je bril. Muziek wordt gepauzeerd terwijl Omi deze gebruikt.';

  @override
  String get chatBlockQuestion => 'Vraag';

  @override
  String get successfullyConnectedTodoist => 'Succesvol verbonden met Todoist!';

  @override
  String voiceRecognitionStatus(String status) {
    String _temp0 = intl.Intl.selectLogic(
      status,
      {
        'ready': 'Stem klaar voor herkenning',
        'saved_sample_awaiting_embedding': 'Fragment opgeslagen; stemverwerking nog nodig',
        'not_learned': 'Stem niet geleerd',
        'other': 'Stemstatus onbekend',
      },
    );
    return '$_temp0';
  }

  @override
  String addQueryAsNewPerson(String query) {
    return '\"$query\" toevoegen als nieuwe persoon';
  }

  @override
  String confidenceReasonAutoConfirmed(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Je hebt $count automatische labels bevestigd',
      one: 'Je hebt 1 automatisch label bevestigd',
    );
    return '$_temp0';
  }

  @override
  String get recordAudioConversations => 'Audiogesprekken opnemen';

  @override
  String get saveKeyWarning => 'Sla deze sleutel nu op! U kunt hem niet meer zien.';

  @override
  String get saveChanges => 'Wijzigingen opslaan';

  @override
  String get sttModelSlower => 'Langzamer';

  @override
  String get otaDownloadFailed =>
      'Het downloaden van de firmware is mislukt. Controleer de wifiverbinding en probeer het opnieuw.';

  @override
  String get captureRecordingViewing => 'Je bekijkt deze opname';

  @override
  String get resetFilters => 'Filters resetten';

  @override
  String get voiceSettingsSaveOthersSubtitle =>
      'Als je iemand een naam geeft, bewaart Omi een kort stemfragment om diegene de volgende keer te herkennen';

  @override
  String get iveDoneThis => 'Dit heb ik gedaan';

  @override
  String get howSyncingWorks => 'Hoe synchronisatie werkt';

  @override
  String greetingWithName(String greeting, String name) {
    return '$greeting, $name';
  }

  @override
  String reviewRemaining(int count) {
    return 'Nog $count';
  }

  @override
  String get feedbackReasonRecordingMissingAudio => 'Audio ontbreekt';

  @override
  String get appCategoryModalTitle => 'App-categorie';

  @override
  String get pushToTalk => 'Druk om te praten';

  @override
  String get noApiKeysYet => 'Nog geen API-sleutels. Maak er een aan om te integreren met uw app.';

  @override
  String minLabel(int count) {
    return '$count min';
  }

  @override
  String appRatingCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count beoordelingen',
      one: '1 beoordeling',
    );
    return '$_temp0';
  }

  @override
  String get wrappedFood => 'ETEN';

  @override
  String get aboutAMinuteRemaining => 'Ongeveer een minuut resterend';

  @override
  String get clearLogs => 'Logboeken wissen';

  @override
  String get wrappedBook => 'BOEK';

  @override
  String get phoneCallSubtitle => 'Neem een gesprek op met live transcriptie';

  @override
  String deleteConversationsTitle(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count gesprekken verwijderen?',
      one: '1 gesprek verwijderen?',
    );
    return '$_temp0';
  }

  @override
  String get deleteSelected => 'Geselecteerde verwijderen';

  @override
  String failedToDeleteGraph(String error) {
    return 'Kon graaf niet verwijderen: $error';
  }

  @override
  String get setupQuestionsIntro => 'Help ons Omi te verbeteren door een paar vragen te beantwoorden. 🫶 💜';

  @override
  String get category => 'Categorie';

  @override
  String get timeout30MinutesDesc => 'Gesprek beëindigen na 30 minuten stilte';

  @override
  String get goalDeleted => 'Doel verwijderd';

  @override
  String get conversationDisplay => 'Gespreksweergave';

  @override
  String get conversationNoSummaryYet => 'Dit gesprek heeft nog geen samenvatting.';

  @override
  String get chatsLowercase => 'chats';

  @override
  String get clearChatQuestion => 'Chat wissen?';

  @override
  String get signInTitle => 'Inloggen';

  @override
  String get loadingKnowledgeGraph => 'Kennisgrafiek laden…';

  @override
  String get goalTracker => 'Doel-tracker';

  @override
  String get commandRequired => '⌘ vereist';

  @override
  String get permissionEnabled => 'Ingeschakeld';

  @override
  String get submitReview => 'Beoordeling verzenden';

  @override
  String chatUsageCost(String used, String limit) {
    return 'Chat: \$$used / \$$limit gebruikt deze maand';
  }

  @override
  String get discard => 'Verwerpen';

  @override
  String dreamReportPasses(int count, int limit) {
    return '$count van $limit rondes vandaag';
  }

  @override
  String get unlockOmiInfiniteMemory => 'Onbeperkte herinneringen';

  @override
  String get addAppPersonaConflictWithCapabilities => 'Persona kan niet worden geselecteerd met andere functies';

  @override
  String get whyAreYouCanceling => 'Waarom annuleer je?';

  @override
  String get permissionRequestedExclaim => 'Toestemming gevraagd!';

  @override
  String get chatBlockOpenInMemories => 'Openen in Herinneringen';

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total objecten';
  }

  @override
  String get deleteActionItemTitle => 'Taak verwijderen';

  @override
  String get rollBack => 'Terugzetten';

  @override
  String get chatAppsOmiPro => 'OMI PRO';

  @override
  String disconnectFromAppDesc(String appName) {
    return 'Dit verwijdert je $appName-authenticatie. Je moet opnieuw verbinden om het weer te gebruiken.';
  }

  @override
  String get onDeviceModelSize => 'Modelgrootte';

  @override
  String tagSpeaker(int speakerId) {
    return 'Spreker $speakerId taggen';
  }

  @override
  String get couldNotOpenUrl => 'Kan de URL niet openen. Probeer het opnieuw.';

  @override
  String get conversationNewIndicator => 'Nieuw';

  @override
  String get notEnoughSpeechDescription =>
      'Er is niet genoeg spraak gedetecteerd. Spreek alsjeblieft meer en probeer het opnieuw.';

  @override
  String get liveRssiOverTime => 'Live RSSI in de tijd';

  @override
  String get usageEverywhere => 'Overal';

  @override
  String nConversations(int count) {
    return '$count gesprekken';
  }

  @override
  String get wrappedConversationsLabel => 'gesprekken';

  @override
  String get usageYear => 'Dit jaar';

  @override
  String get noContactsMatchSearch => 'Geen contacten komen overeen met uw zoekopdracht';

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count ta(a)k(en)$s verwijderd';
  }

  @override
  String get actionItemMarkedIncomplete => 'Taak gemarkeerd als niet voltooid';

  @override
  String get start => 'Starten';

  @override
  String discardedConversationTitle(String duration) {
    return 'Verworpen · $duration';
  }

  @override
  String get debugLogsCleared => 'Debuglogboeken gewist';

  @override
  String get preparingAudioCapture => 'Audio-opname voorbereiden';

  @override
  String get availablePaymentMethods => 'Beschikbare betaalmethoden';

  @override
  String get deleteReasonOther => 'Anders';

  @override
  String get accountCutoverMigrationInProgressTitle => 'Migratie bezig';

  @override
  String get connectedKnowledgeData => 'Verbonden kennisgegevens';

  @override
  String get wrappedMostFunDay => 'Leukste';

  @override
  String get onboardingAccessibilityRequired =>
      'Toegankelijkheidstoestemming is vereist voor het detecteren van browservergaderingen.';

  @override
  String get selectActionItems => 'Meerdere selecteren';

  @override
  String switchApiConfirmBody(String environment) {
    return 'Overschakelen naar $environment? Je moet de app sluiten en opnieuw openen om de wijzigingen door te voeren.';
  }

  @override
  String get whisperModelSizeLarge => 'Groot';

  @override
  String get currentVersion => 'Huidige versie';

  @override
  String get aiAppGeneratorBannerTitle => 'Maak met één tik een app met AI';

  @override
  String get rayBanMetaMicPickerLoadError =>
      'Bluetooth-microfoons konden niet worden geladen. Controleer of Bluetooth aanstaat en probeer het opnieuw.';

  @override
  String get noneSelected => 'Geen geselecteerd';

  @override
  String get entityKeptCurrent => 'Actueel gehouden door Omi';

  @override
  String migratingFromTo(String source, String target) {
    return 'Migreren van $source naar $target';
  }

  @override
  String get controlNotificationFrequency => 'Bepaal hoe vaak Omi u proactieve meldingen stuurt.';

  @override
  String get connectionUptime => 'Uptime';

  @override
  String get categoryLabel => 'Categorie';

  @override
  String get aboutTheApp => 'Over de app';

  @override
  String get planSheetChooseYourPlan => 'Kies het abonnement dat bij je past.';

  @override
  String get almostDone => 'Bijna klaar…';

  @override
  String get tasksFromConversationsWillAppear =>
      'Taken uit je gesprekken verschijnen hier.\nKlik op Aanmaken om er handmatig een toe te voegen.';

  @override
  String get personLastHeard => 'Laatst gehoord';

  @override
  String get durationThreshold => 'Duurdrempel';

  @override
  String get transcriptionServiceDiagnosticStatus => 'Diagnostische status van transcriptieservice';

  @override
  String get triggersWhenNewTranscriptReceived => 'Wordt geactiveerd wanneer een nieuwe transcriptie wordt ontvangen.';

  @override
  String get aboutOmi => 'Over Omi';

  @override
  String get identifyingOthers => 'Identificatie van Anderen';

  @override
  String get phoneCallsSubtitle => 'Bel met realtime transcriptie';

  @override
  String get creatingYourApp => 'Je app maken…';

  @override
  String get analyzingYourData => 'Je gegevens analyseren…';
}
