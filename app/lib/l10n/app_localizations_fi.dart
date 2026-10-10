// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Finnish (`fi`).
class AppLocalizationsFi extends AppLocalizations {
  AppLocalizationsFi([String locale = 'fi']) : super(locale);

  @override
  String get welcomeActionItemsDescription =>
      'Tekoälysi poimii automaattisesti tehtävät keskusteluistasi. Ne näkyvät täällä, kun ne on luotu.';

  @override
  String get chatAppsProblemFailed => 'Jokin meni pieleen. Yritä uudelleen.';

  @override
  String get deviceOnboardingStarConversation => 'Tähditä käynnissä olevaa keskustelua';

  @override
  String get deleteAll => 'Poista kaikki';

  @override
  String get copySummary => 'Kopioi tiivistelmä';

  @override
  String get locationAccessDesc => 'Jotta Omi voi merkitä, missä keskustelusi käytiin.';

  @override
  String get firmwareUpdate => 'Laiteohjelmistopäivitys';

  @override
  String get chatMessages => 'viestiä';

  @override
  String get showEventsNoParticipants => 'Näytä tapahtumat ilman osallistujia';

  @override
  String get sharePeriodYear => 'Tänä vuonna Omi on:';

  @override
  String get dreamReportRunFailed => 'Dreamin ajaminen ei onnistunut. Yritä uudelleen.';

  @override
  String get sttModelAccuracy => 'Tarkkuus';

  @override
  String get scopes => 'Käyttöalueet';

  @override
  String get deleteFlowFeedbackSubtitle => 'Mikä olisi saanut Omin toimimaan sinulle?';

  @override
  String appDataAccessTitle(String appName) {
    return 'Sallitaanko $appName-sovelluksen käyttöoikeus?';
  }

  @override
  String get pendantStorageAlmostFull =>
      'Riipuksen tallennustila on lähes täynnä — pidä sovellus auki synkronointia varten.';

  @override
  String get deviceOnboardingAllSetDoublePressBadge => '2×';

  @override
  String get copyErrorMessage => 'Kopioi virheilmoitus';

  @override
  String get filterMemories => 'Suodata muistoja';

  @override
  String get helpsDiagnoseIssuesAutoDeletes =>
      'Auttaa ongelmien diagnosoinnissa. Poistetaan automaattisesti 3 päivän kuluttua.';

  @override
  String get locationServiceDisabledDesc =>
      'Sijaintipalvelut ovat pois päältä tässä laitteessa. Ota ne käyttöön asetuksissa.';

  @override
  String chatAppsIsConnected(String app) {
    return '$app on yhdistetty';
  }

  @override
  String get paymentMethodStripe => 'Stripe';

  @override
  String get deleteReasonTechnicalIssues => 'Liian monta teknistä ongelmaa';

  @override
  String get payments => 'Maksut';

  @override
  String get verifiedFallback => 'Vahvistettu';

  @override
  String get pleaseWait => 'Odota…';

  @override
  String get appLanguage => 'Sovelluksen kieli';

  @override
  String get unknownApp => 'Tuntematon sovellus';

  @override
  String get appReEnableFailedBody => 'Tätä sovellusta ei voitu ottaa uudelleen käyttöön. Yritä uudelleen.';

  @override
  String get somethingWentWrongTryAgain => 'Jokin meni pieleen! Yritä myöhemmin uudelleen.';

  @override
  String get upgradeScheduled => 'Päivitys ajoitettu';

  @override
  String get wrappedBuddiesLabel => 'KAVERIT';

  @override
  String get chatBlockShowMore => 'Näytä lisää';

  @override
  String get subscriptionSuccessfulCharged => 'Tilaus onnistui! Sinut on veloitettu uudesta laskutusjaksosta.';

  @override
  String get phoneCall => 'Puhelu';

  @override
  String get chatAppsRefreshFailed => 'Päivitys epäonnistui. Näytetään viimeksi nähty tilanne.';

  @override
  String get noDesktopAccess => 'Ei toimi tietokoneella';

  @override
  String get areYouSure => 'Oletko varma?';

  @override
  String get resubscribe => 'Tilaa uudelleen';

  @override
  String voiceMatchMeterLabel(String level) {
    return 'Äänen osuma: $level';
  }

  @override
  String get syncingBackground => 'Jatkamme nauhoitusten synkronointia taustalla.';

  @override
  String get signOutQuestion => 'Kirjaudu ulos?';

  @override
  String chatAppsReadOnlyBanner(String app) {
    return 'Vain luku. Vastaa Omille sovelluksessa $app.';
  }

  @override
  String get connected => 'Yhdistetty';

  @override
  String get shareStatsMessage => 'Jaan Omi-tilastoni! (omi.me - aina päällä oleva tekoälyavustajasi)';

  @override
  String get frequencyMinimal => 'Minimaalinen';

  @override
  String get addAppSelectLogo => 'Valitse logo sovelluksellesi';

  @override
  String get integrationInstructions => 'Integrointiohjeet';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'Esteettömyysluvan tila: $status. Tarkista Järjestelmäasetukset.';
  }

  @override
  String get wrappedCompleted => 'valmista';

  @override
  String get remaining => 'Jäljellä';

  @override
  String get onDeviceIntensive => 'Laitteella tapahtuva puheentunnistus on laskennallisesti vaativaa.';

  @override
  String get diagnosticsVerdictTrouble => 'Yhdistämisessä on ongelmia';

  @override
  String deviceOnboardingVoiceReplyPreviewThroughDevice(String device) {
    return '$device kautta';
  }

  @override
  String get copyConfig => 'Kopioi kokoonpano';

  @override
  String accessesDataTypes(String dataTypes) {
    return 'Käyttää: $dataTypes';
  }

  @override
  String get chatAppsWaitlistConfirmed => 'Kiitos. WhatsApp ilmestyy tänne, kun se on valmis.';

  @override
  String get undo => 'Kumoa';

  @override
  String get phoneContactsAccessTitle => 'Salli yhteystietojen käyttö';

  @override
  String confidenceIsConfirmed(String name) {
    return '$name on tilassa Vahvistettu. Sinun ei tarvitse tehdä mitään muuta.';
  }

  @override
  String get wrappedMovie => 'ELOKUVA';

  @override
  String get wrappedStruggleLabelUpper => 'KAMPPAILU';

  @override
  String get appleHealthFeatureChatDesc => 'Kysy Omilta askelista, unesta, sykkeestä ja harjoituksista.';

  @override
  String get writeReviewOptional => 'Kirjoita arvostelu (valinnainen)';

  @override
  String get pairNewDevice => 'Yhdistä uusi laite';

  @override
  String chatUsedOfLimitCompute(String used, String limit) {
    return '$used / $limit laskentabudjetista käytetty';
  }

  @override
  String get dailySummary => 'Päivittäinen yhteenveto';

  @override
  String get pleaseEnterYourName => 'Syötä nimesi';

  @override
  String get continueWithoutDevice => 'Jatka ilman laitetta';

  @override
  String get configure => 'Määritä';

  @override
  String get createApp => 'Luo sovellus';

  @override
  String get invalidUrlError => 'Anna kelvollinen URL';

  @override
  String get appClosed => 'Sovellus suljettu';

  @override
  String get downgradeToFreemiumAction => 'Vaihda ilmaisversioon';

  @override
  String get chatAppsUseTelegramForNow => 'Käytä toistaiseksi Telegramia';

  @override
  String get wrappedBestMomentsBadge => 'Parhaat hetket';

  @override
  String get storageSection => 'Tallennustila';

  @override
  String get pauseResumeRecording => 'Keskeytä/Jatka nauhoitusta';

  @override
  String get phoneUnmute => 'Poista mykistys';

  @override
  String get youreAllSet => 'Olet valmis!';

  @override
  String get migrationComplete => 'Siirto valmis!';

  @override
  String get paymentAppCost => 'Sovelluksen hinta';

  @override
  String get deviceOnboardingFinish => 'Valmis';

  @override
  String get noVerifiedNumbers => 'Ei vahvistettuja numeroita';

  @override
  String get connectAiAssistantsToData => 'Yhdistä AI-avustajat tietoihisi';

  @override
  String get keyNameHint => 'esim. Claude Desktop';

  @override
  String get paymentMethods => 'Maksutavat';

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'Esteettömyysluvan tarkistus epäonnistui: $error';
  }

  @override
  String get confidenceReasonAutoOnly => 'Merkitty automaattisesti, ei vielä vahvistettu';

  @override
  String whatsNewInVersion(String version) {
    return 'Uutta versiossa $version';
  }

  @override
  String get selectYourLanguage => 'Valitse kielesi';

  @override
  String get memoryClearedSuccess => 'Omin muisti sinusta on tyhjennetty';

  @override
  String get memoryContentHint => 'Pidän mieluiten kokoukset aamulla.';

  @override
  String get dreamReportTitle => 'Dream-raportti';

  @override
  String importErrorGeneric(String error) {
    return 'Virhe: $error';
  }

  @override
  String get completionRate => 'Suoritusaste';

  @override
  String get trackPersonalGoals => 'Seuraa henkilökohtaisia tavoitteita etusivulla';

  @override
  String get wrappedTryAgain => 'Yritä uudelleen';

  @override
  String get dataProtection => 'Tietosuoja';

  @override
  String get yourConversations => 'Keskustelusi';

  @override
  String pdfTitleLabel(String title) {
    return 'Otsikko: $title';
  }

  @override
  String get sendRawAudioToOmiDescription =>
      'Poista käytöstä, jotta käsittelemätöntä ääntä ei lähetetä Omille. Litterointeja ja pilviominaisuuksien tarvitsemia tietoja voidaan silti lähettää Omille.';

  @override
  String get entityLoadFailed => 'Tätä sivua ei voitu ladata.';

  @override
  String get networkNameSsid => 'Verkon nimi (SSID)';

  @override
  String get discovery => 'Löydös';

  @override
  String get rayBanMetaMicPickerConnectError =>
      'Mikrofoniin ei voitu muodostaa yhteyttä. Varmista, että se on yhdistetty iPhonen asetuksissa.';

  @override
  String get fairUseAboutTitle => 'Tietoa kohtuullisesta käytöstä';

  @override
  String get wrappedYouTalkedAbout => 'Puhuit aiheesta';

  @override
  String get downgradeLimitQuality => '30 % heikompi litterointilaatu';

  @override
  String get sharedTasksUnknownSender => 'Joku';

  @override
  String get selectAReason => 'Valitse syy';

  @override
  String get wrappedWinLabel => 'VOITTO';

  @override
  String get configuration => 'Kokoonpano';

  @override
  String get noFolder => 'Ei kansiota';

  @override
  String get manifestRefreshedSuccess => 'Manifesti päivitetty onnistuneesti';

  @override
  String get paymentStatusActive => 'Aktiivinen';

  @override
  String get linkKeyMismatch => 'Yhteysavaimen ristiriita';

  @override
  String speakerTagPromptProgress(int current, int total) {
    return '$current/$total';
  }

  @override
  String get updateRequiredMessage =>
      'Tätä Omin versiota ei enää tueta. Päivitä, jotta voit jatkaa tallentamista ja synkronointia.';

  @override
  String get sharePeriodMonth => 'Tässä kuussa Omi on:';

  @override
  String get rollbackToStableFirmware => 'Palaa vakaaseen laiteohjelmistoon';

  @override
  String get paymentStatusConnected => 'Yhdistetty';

  @override
  String get findDeviceNoneTitle => 'Omia ei löytynyt';

  @override
  String get appIdCopiedToClipboard => 'Sovelluksen tunnus kopioitu leikepöydälle';

  @override
  String get bySubmittingYouAgreeToOmi => 'Lähettämällä hyväksyt Omin ';

  @override
  String get filterRating => 'Arvostelu';

  @override
  String get usageAtWork => 'Työssä';

  @override
  String get tasksCleanTodayMessage => 'Tämä poistaa vain määräajat';

  @override
  String get ignoredVoicesSubtitle => 'TV, podcastit ja muut äänet, jotka merkitsit kohtaan Ei ihminen';

  @override
  String get permissionEnable => 'Ota käyttöön';

  @override
  String integrationComingSoon(String appName) {
    return '$appName ei ole vielä tuettu.';
  }

  @override
  String get sttModelLower => 'Matalampi';

  @override
  String get loadingYourMemories => 'Ladataan muistojasi…';

  @override
  String get followUpQuestions => 'Jatkokysymykset';

  @override
  String get previousDay => 'Edellinen päivä';

  @override
  String fairUseCaseRefCopied(String caseRef) {
    return '$caseRef kopioitu';
  }

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get recordingPaused => 'Tallennus keskeytetty';

  @override
  String get cannotReportOwnMessages => 'Et voi raportoida omia viestejäsi';

  @override
  String get enterWordsHint => 'Syötä sanat (pilkulla eroteltuina)';

  @override
  String get audioDownloadFailed => 'Äänen lataus epäonnistui';

  @override
  String get clearMemoryMessage => 'Kaikki muistosi poistetaan. Tätä ei voi perua.';

  @override
  String get templateNameHint => 'esim. Kokouksen tehtävien poimija';

  @override
  String speakerLabelTalkTime(String duration) {
    return '$duration tästä äänestä';
  }

  @override
  String get recordingMode => 'Tallennustila';

  @override
  String get cancelReasonOther => 'Muu';

  @override
  String get sttModelHigher => 'Korkeampi';

  @override
  String get settingUpSystemAudioCapture => 'Järjestelmän äänitallennus asetuksissa';

  @override
  String memoriesCount(int count) {
    return '$count muistoa';
  }

  @override
  String get noSpecificDataAccessConfigured => 'Ei määritettyä tietojen käyttöoikeutta.';

  @override
  String get recordingIdLabel => 'Nauhoituksen tunnus';

  @override
  String get highlights => 'Kohokohdat';

  @override
  String get phoneTryAgain => 'Yrita uudelleen';

  @override
  String chatAppsCouldNotOpen(String app) {
    return 'Sovellusta $app ei voitu avata. Varmista, että se on asennettu, ja yritä uudelleen.';
  }

  @override
  String get onDeviceTranscriptionDesc => 'Transkriptio käsitellään paikallisesti laitteellasi';

  @override
  String get chatAppsTryPromise => 'Mitä lupasin Samille eilen?';

  @override
  String get paymentStatusNotConnected => 'Ei yhdistetty';

  @override
  String get intervalSeconds => 'Aikaväli (sekuntia)';

  @override
  String get authorize => 'Valtuuta';

  @override
  String get settingsHeader => 'ASETUKSET';

  @override
  String get personNameAlreadyExists => 'Tämä nimi on jo olemassa';

  @override
  String get deviceOnboardingVoiceReplyPreviewThroughCurrentOutput => 'Nykyisen äänilähdön kautta';

  @override
  String get monthJun => 'Kesä';

  @override
  String selectedCount(int count) {
    return '$count valittu';
  }

  @override
  String get batteryHistory => 'Akku';

  @override
  String get noPastChats => 'Keskustelusi Omin kanssa näkyvät täällä.';

  @override
  String get chatAppsDoesSave => 'Tallentaa muistoja ja hallitsee tehtäviäsi';

  @override
  String get apiKey => 'API-avain';

  @override
  String get authFailedToLinkGoogle => 'Googleen linkittäminen epäonnistui, yritä uudelleen.';

  @override
  String audioUploadFailedKeptLocal(String duration) {
    return 'Lähetys epäonnistui — $duration ääntä on tallessa puhelimessasi.';
  }

  @override
  String get free => 'Ilmainen';

  @override
  String get deselectAllTasksMenu => 'Poista kaikkien valinta';

  @override
  String get dreamReportLoadFailed => 'Dream-raportin lataaminen ei onnistunut.';

  @override
  String get entityRecentConversations => 'Viimeisimmät keskustelut';

  @override
  String get pendantRecordingNote =>
      'Riipuksesi tallentaa itsenäisesti. Tallenteet synkronoituvat puhelimeesi, kun sovellus on auki.';

  @override
  String get manageStorage => 'Hallitse tallennustilaa';

  @override
  String get filterSystem => 'Tietoja sinusta';

  @override
  String get deleteConsequenceSubscription => 'Mahdolliset aktiiviset tilaukset peruutetaan.';

  @override
  String get defaultList => 'Oletusluettelo';

  @override
  String get shared => 'Jaettu';

  @override
  String get customVocabulary => 'Mukautettu Sanasto';

  @override
  String get feedbackTitleAudioQuality => 'Mitä ongelmia koit?';

  @override
  String get thisActionCannotBeUndone => 'Tätä ei voi perua.';

  @override
  String errorRequestingPermission(String error) {
    return 'Virhe pyydettäessä käyttöoikeutta: $error';
  }

  @override
  String get recapRegenerateFailed => 'Yhteenvedon uudelleenluonti epäonnistui. Yritä myöhemmin uudelleen.';

  @override
  String get result => 'Tulos:';

  @override
  String get statusCallMissed => 'Vastaamaton puhelu';

  @override
  String get diagnosticsLongestGap => 'Pisin katko';

  @override
  String get noLogFilesFound => 'Lokitiedostoja ei löytynyt.';

  @override
  String get speechTranscriptionSectionTitle => 'Puhe ja litterointi';

  @override
  String get syncNow => 'Synkronoi nyt';

  @override
  String get sttUsePrimaryLanguage => 'Käytä ensisijaista kieltä';

  @override
  String get importUnsupportedFileType => 'Tämän tyyppistä tiedostoa ei voi tuoda.';

  @override
  String get chatSendMessage => 'Lähetä viesti';

  @override
  String get syncCardAllBackedUp => 'Kaikki tallenteet synkronoitu';

  @override
  String get settings => 'Asetukset';

  @override
  String get backgroundLocationDeniedDesc =>
      'Siirry laitteen asetuksiin ja aseta sijaintioikeus asentoon \"Salli aina\"';

  @override
  String get computationallyIntensive => 'Laitteella tapahtuva transkriptio on laskennallisesti intensiivistä.';

  @override
  String get and => ' ja ';

  @override
  String get yourVerifiedNumbers => 'Vahvistetut numerosi';

  @override
  String get tasksCleanTodayTitle => 'Siivota tämän päivän tehtävät?';

  @override
  String get microphonePermission => 'Mikrofonin käyttöoikeus';

  @override
  String get failedToUpdateConversationTitle => 'Keskustelun otsikon päivitys epäonnistui';

  @override
  String get appsDisconnected => 'Sovelluksesi ja integraatiosi irrotetaan.';

  @override
  String get live => 'Livenä';

  @override
  String get connectionFailed => 'Yhteys epäonnistui';

  @override
  String get selectImages => 'Valitse kuvia';

  @override
  String get playbackAudioNetworkFailed => 'Tarkista yhteys';

  @override
  String get paypalEmail => 'PayPal-sähköposti';

  @override
  String get chatAppsOnTheList => 'Listalla';

  @override
  String get generateSummary => 'Luo yhteenveto';

  @override
  String get categoryHealth => 'Terveys';

  @override
  String get transcribeLaterStorageFull =>
      'Puhelimesi tallennustila on vähissä, joten nauhoitus on keskeytetty. Vapauta tilaa tai lataa nauhoituksesi, niin se jatkuu automaattisesti.';

  @override
  String get chatAppsNoChatsTitle => 'Ei vielä keskusteluja';

  @override
  String get onboardingSetupStepPersonalize => 'Kokemustasi personoidaan';

  @override
  String get leaveUnselectedTasks => 'Jätä valitsematta luodaksesi tehtäviä ilman projektia';

  @override
  String get wrappedButYouPushedThroughEmoji => 'Mutta selvisit siitä 💪';

  @override
  String get needHelp => 'Tarvitsetko apua?';

  @override
  String get confirmAndCancel => 'Vahvista ja peruuta';

  @override
  String get frequencyDescHigh => 'Enemmän ehdotuksia, noin 6–9 päivässä';

  @override
  String get copyLink => 'Kopioi linkki';

  @override
  String get dreamReportLiveBanner => 'Dream tekee nämä muutokset itse. Peru ne kohdassa Viimeisimmät muutokset.';

  @override
  String get enterActionItemDescription => 'Anna tehtävän kuvaus';

  @override
  String chatAppsInChannel(String app) {
    return 'Sovelluksessa $app';
  }

  @override
  String get links => 'Linkit';

  @override
  String get dreamReportEmptyTitle => 'Ei vielä ajoja';

  @override
  String get monthJan => 'Tammi';

  @override
  String get wrappedMostProductiveDay => 'Tuottavin';

  @override
  String get productUpdate => 'Tuotepäivitys';

  @override
  String get addYourReview => 'Lisää arvostelusi';

  @override
  String get raybanMetaImageCaptureReady => 'Kuvan kaappaus valmis';

  @override
  String get displayUpcomingMeetingsDescription => 'Näytä tulevat kokoukset valikkorivissä';

  @override
  String get whatWeCollect => 'Mitä keräämme';

  @override
  String get connectPayPalToReceivePayments =>
      'Yhdistä PayPal-tilisi aloittaaksesi maksujen vastaanottamisen sovelluksistasi';

  @override
  String get justAMoment => 'Hetkinen';

  @override
  String get chatReplyServerError => 'Jotain meni pieleen meidän puolellamme. Yritä uudelleen.';

  @override
  String get transferInProgress => 'Siirto käynnissä…';

  @override
  String get usageAll => 'Kaikki aika';

  @override
  String get failedToLoadContacts => 'Yhteystietojen lataaminen epäonnistui';

  @override
  String appUsersCount(int count) {
    return '$count+ käyttäjää';
  }

  @override
  String get report => 'Raportoi';

  @override
  String get languageLabel => 'Kieli';

  @override
  String verifiedOnDate(String date) {
    return 'Vahvistettu $date';
  }

  @override
  String get customVocabularyHeader => 'MUKAUTETTU SANASTO';

  @override
  String otaRebooting(String deviceName) {
    return '$deviceName käynnistyy uudelleen uudella laiteohjelmistolla.';
  }

  @override
  String get mcpServer => 'MCP-palvelin';

  @override
  String get findDevice => 'Etsi';

  @override
  String get msgUploadAttachedFileFailed => 'Liitetiedoston lataus epäonnistui.';

  @override
  String get appName => 'App Name';

  @override
  String get pairingTitlePlaudNote => 'Aseta Plaud Note pariliitostilaan';

  @override
  String get moreOptions => 'Lisää vaihtoehtoja';

  @override
  String get noConversationsHeroMessage =>
      'Tallentamasi keskustelut näkyvät täällä. Tallenna ensimmäinen napauttamalla tallennuspainiketta Koti-välilehdellä.';

  @override
  String get finish => 'Lopeta';

  @override
  String get goBack => 'Palaa takaisin';

  @override
  String get apiKeysDescription =>
      'API-avaimia käytetään todentamiseen, kun sovelluksesi kommunikoi Omi-palvelimen kanssa. Ne mahdollistavat sovelluksesi luoda muistoja ja käyttää muita Omi-palveluita turvallisesti.';

  @override
  String get sttProviderSpeechmatics => 'Speechmatics';

  @override
  String get setWebhookUrlInSettings => 'Aseta webhook-URL kehittäjäasetuksissa käyttääksesi tätä ominaisuutta.';

  @override
  String get dailyScoreBreakdown => 'Päivittäisen pistemäärän erittely';

  @override
  String get showMeetingsMenuBarDesc => 'Näytä seuraava kokouksesi ja aika sen alkuun macOS-valikkorivissä';

  @override
  String get tapToTrackThisGoal => 'Napauta seurataksesi tätä tavoitetta';

  @override
  String get summarizingConversation => 'Tiivistetään keskustelua…\nTämä voi kestää muutaman sekunnin';

  @override
  String get noInternetConnection => 'Ei internet-yhteyttä';

  @override
  String diagnosticsCountSincePairing(int count) {
    return '$count parituksen jälkeen';
  }

  @override
  String get wrappedTasksCreated => 'luotua tehtävää';

  @override
  String get deleteConsequenceNoRecovery => 'Tiliäsi ei voi palauttaa — ei edes tuki voi tehdä sitä.';

  @override
  String get waitForReprocessing => 'Odota, kunnes uudelleenkäsittely on valmis.';

  @override
  String get needYourPermission => 'Tarvitsemme lupasi';

  @override
  String get downgradeLimitSpeakers => 'Puhujia ei voi tunnistaa';

  @override
  String conversationsTodayCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count keskustelua tänään.',
      one: '1 keskustelu tänään.',
      zero: 'Ei keskusteluja tänään.',
    );
    return '$_temp0';
  }

  @override
  String get dailyScore => 'PÄIVITTÄINEN PISTEMÄÄRÄ';

  @override
  String get reportAnIssue => 'Ilmoita ongelmasta';

  @override
  String get invalidKey => 'Virheellinen näppäin';

  @override
  String get preview => 'Esikatselu';

  @override
  String get nextWeek => 'Ensi viikolla';

  @override
  String get confidenceUnverified => 'Vahvistamaton';

  @override
  String get previewScreenshots => 'Kuvakaappausten esikatselu';

  @override
  String get ledBrightness => 'LED-kirkkaus';

  @override
  String get firmwareUpdateFailedMessage =>
      'Päivitys ei valmistunut. Laitteessasi on yhä nykyinen laiteohjelmisto, ja sitä on turvallista käyttää. Pidä se ladattuna ja lähellä puhelinta ja yritä uudelleen.';

  @override
  String get loadingProfile => 'Ladataan profiilia…';

  @override
  String get deleteRecapConfirmTitle => 'Poistetaanko tämä yhteenveto?';

  @override
  String get notificationFrequency => 'Ilmoitusten tiheys';

  @override
  String get captureSystemAudioFromMeetings => 'Tallenna järjestelmän ääntä kokouksista';

  @override
  String get storeAudioCloudDescription => 'Lataa tallenteesi puheen aikana, jotta voit toistaa ne myöhemmin.';

  @override
  String get color => 'Väri';

  @override
  String get open => 'Avaa';

  @override
  String get diagnosticsVerdictNoDrops => 'Ei katkoksia tällä viikolla';

  @override
  String get autoExtractionFeature => 'Poimittu automaattisesti keskusteluista';

  @override
  String get searchResults => 'Hakutulokset';

  @override
  String get v2UndetectedMessage =>
      'Sinulla näyttää olevan V1-laite tai laitteesi ei ole yhdistetty. SD-korttitoiminto on saatavilla vain V2-laitteille.';

  @override
  String get endAndProcess => 'Lopeta ja käsittele keskustelu';

  @override
  String get noSyncedRecordings => 'Ei synkronoituja nauhoituksia vielä';

  @override
  String get coworker => 'Työkaveri';

  @override
  String get setupQuestionUsage => '2. Missä aiot käyttää Omi-laitetta?';

  @override
  String get pinnedNotSelectable => 'Kiinnitetty, ei valittavissa';

  @override
  String get showMore => 'näytä lisää ↓';

  @override
  String get createYourFirstMemory => 'Luo ensimmäinen muistosi aloittaaksesi';

  @override
  String get discardedConversation => 'Hylätty keskustelu';

  @override
  String get enableApps => 'Ota sovellukset käyttöön';

  @override
  String get today => 'Tänään';

  @override
  String get showEventsNoParticipantsDesc =>
      'Kun käytössä, Tulossa näyttää tapahtumat ilman osallistujia tai videolinkkiä.';

  @override
  String get couldNotLoadPage => 'Sivua ei voitu ladata. Tarkista yhteys ja yritä uudelleen.';

  @override
  String actionItemDeletedResult(String description) {
    return 'Tehtävä \"$description\" poistettu';
  }

  @override
  String get deleteSampleQuestion => 'Poista näyte?';

  @override
  String get youAreOnAPaidPlan => 'Sinulla on maksullinen tilaus.';

  @override
  String get otaInstallFailed => 'Asennus epäonnistui. Laitteessasi on yhä nykyinen laiteohjelmisto.';

  @override
  String get addFirstMemory => 'Lisää ensimmäinen muistosi';

  @override
  String get appDeletedSuccessfully => 'Sovellus poistettu onnistuneesti';

  @override
  String get chatAppsConnectTelegramMessage =>
      'Omi avaa Telegramin yksityisellä linkillä, joka on tarkoitettu vain sinulle.';

  @override
  String get phoneSetupStep1Title => 'Vahvista puhelinnumerosi';

  @override
  String get deviceRequirements => 'Laitteesi ei täytä laitteella tapahtuvan puheentunnistuksen vaatimuksia.';

  @override
  String get confidenceEvidenceHeader => 'Perusteet';

  @override
  String get pleaseEnterAName => 'Anna nimi.';

  @override
  String get deleteConfirmationWord => 'DELETE';

  @override
  String get speakerTagPromptThatsMe => 'Se olen minä';

  @override
  String get ourCommitment => 'Sitoumuksemme';

  @override
  String get notificationScopes => 'Ilmoitusalueet';

  @override
  String get autoDeletesAfter3Days => 'Poistetaan automaattisesti 3 päivän kuluttua';

  @override
  String get initialisingRecorder => 'Alustetaan tallenninta';

  @override
  String get privateAndSecureOnDevice => 'Tallennettu tähän puhelimeen';

  @override
  String get allObjectsMigratedFinalizing => 'Kaikki kohteet siirretty. Viimeistellään…';

  @override
  String get chatAppsOpenMessages => 'Avaa Viestit';

  @override
  String get upgradeToPro => 'Päivitä Pro-versioon';

  @override
  String get clientId => 'Asiakas-ID';

  @override
  String get backgroundActivity => 'Taustatoiminta';

  @override
  String get noSummaryAvailable => 'Yhteenvetoa ei ole saatavilla';

  @override
  String get failedToUpdateStarred => 'Tähtimerkkauksen päivitys epäonnistui.';

  @override
  String get omiYourAiCompanion => 'Omi – tekoälykumppanisi';

  @override
  String get pleaseSelectReason => 'Valitse syy';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Kaikki muistot ($count) poistetaan. Tätä ei voi perua.';
  }

  @override
  String get connectNow => 'Yhdistä nyt';

  @override
  String chatAppsDisconnectTitle(String app) {
    return 'Katkaistaanko yhteys: $app?';
  }

  @override
  String get clearCredentials => 'Tyhjennä tunnukset';

  @override
  String get grantContactsPermissionForSms => 'Anna yhteystietolupa jakamiseen tekstiviestillä';

  @override
  String get cloudTranscription => 'Pilvitranskriptio';

  @override
  String get memoryHistory => 'Historia';

  @override
  String get speechSamples => 'Puhenäytteet';

  @override
  String get wrappedBiggest => 'Suurin';

  @override
  String get reviewShowMore => 'Näytä lisää';

  @override
  String get triggersWhenDaySummaryGenerated => 'Käynnistyy, kun päivän yhteenveto luodaan.';

  @override
  String get thankYouFeedback => 'Kiitos palautteestasi!';

  @override
  String get allow => 'Salli';

  @override
  String triggeredByType(String triggerType) {
    return 'laukaisee $triggerType';
  }

  @override
  String get howToPair => 'Näin muodostat pariliitoksen';

  @override
  String get conversationDeveloperTools => 'Kehittäjätyökalut keskusteluissa';

  @override
  String get memoryProvenanceIphone => 'iPhone';

  @override
  String get aboutYou => 'Sinusta';

  @override
  String get memoryProvenanceMac => 'Mac';

  @override
  String get effectCounts => 'Auttaa';

  @override
  String get tagSpeakerIncludingLaterSpeech => 'Merkitse myös tämän puhujan myöhempi puhe';

  @override
  String get storeAudioOnPhone => 'Tallenna ääni puhelimeen';

  @override
  String get developerApiKeys => 'Kehittäjän API-avaimet';

  @override
  String get wrappedMyBuddiesCard => 'Kaverini';

  @override
  String get bulkExportAlreadyExported => 'Kaikki valitut tehtävät on jo viety';

  @override
  String get popularBadge => 'SUOSITTU';

  @override
  String get enableLocationTitle => 'Ota sijainti käyttöön';

  @override
  String get feedbackBug => 'Palaute / Virhe';

  @override
  String get good => 'Hyvä';

  @override
  String get upgradeYourPlan => 'Päivitä tilauksesi';

  @override
  String get exportingAllData => 'Tietojasi viedään… Pidä Omi auki; suuret tilit voivat viedä useita minuutteja.';

  @override
  String get switchAndRestart => 'Vaihda';

  @override
  String get noReposFound => 'Repositorioita ei löytynyt';

  @override
  String get latest => 'Uusin';

  @override
  String get failedToRevoke => 'Valtuutuksen peruutus epäonnistui. Yritä uudelleen.';

  @override
  String get appleHealthDisconnectCta => 'Katkaise yhteys Apple Healthiin';

  @override
  String get chatAppsPrivateMemoriesSubtitle =>
      'Terveys, raha ja kaikki yksityiseksi merkitsemäsi pysyvät poissa chat-sovelluksista.';

  @override
  String get deleteFlowFeedbackTitle => 'Kerro lisää';

  @override
  String get failedToConnectTodoistRetry => 'Yhteyden muodostaminen Todoistiin epäonnistui. Yritä uudelleen.';

  @override
  String get capturePhoneStorageFull => 'Puhelimen tallennustila täynnä';

  @override
  String deletePeopleTitle(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Poistetaanko $count henkilöä?',
      one: 'Poistetaanko 1 henkilö?',
    );
    return '$_temp0';
  }

  @override
  String get cleanUpNothingMessage => 'Omi ei ole tällä hetkellä epävarma kenestäkään.';

  @override
  String get writeAReviewOptional => 'Kirjoita arvostelu (valinnainen)';

  @override
  String get syncFailed => 'Synkronointi epäonnistui';

  @override
  String get audioShareFailed => 'Jakaminen epäonnistui';

  @override
  String loadMoreRemaining(String count) {
    return 'Lataa lisää ($count jäljellä)';
  }

  @override
  String get phoneDeleteNumberFailed => 'Numeron poistaminen epäonnistui';

  @override
  String deviceUsesCodec(String device, String reason) {
    return '$device nauhoittaa muodossa, jota tämä palveluntarjoaja ei pysty lukemaan ($reason), joten sen sijaan käytetään Omin litterointia.';
  }

  @override
  String get chatAppsConnectIMessageMessage =>
      'Lähetä Omille yksi viesti numerosta, jota haluat käyttää. Viestin koodi liittää numeron tiliisi.';

  @override
  String get speechToTextUnavailableDesc =>
      'Puheen muuntaminen tekstiksi ei ole juuri nyt käytettävissä. Tarkista internetyhteytesi ja laitteesi puheentunnistusasetukset ja yritä uudelleen.';

  @override
  String get chatReplyTimeout => 'Vastaus kesti liian kauan. Yritä uudelleen.';

  @override
  String get passwordMinLengthError => 'Salasanan on oltava vähintään 8 merkkiä';

  @override
  String get chatAppsWhatsAppMessage => 'Työstämme Omin tuomista WhatsAppiin. Se ilmestyy tänne, kun se on valmis.';

  @override
  String get deleteAccountCheckbox =>
      'Ymmärrän, että tilini poistaminen on pysyvää ja kaikki tiedot, mukaan lukien muistot ja keskustelut, menetetään eikä niitä voi palauttaa.';

  @override
  String get firmwareConnectWifi => 'Yhdistä WiFi:iin tai mobiiliverkkoon.';

  @override
  String get forgetDeviceConfirmMessage => 'Omi lopettaa yhteyden muodostamisen tähän laitteeseen.';

  @override
  String get editSwipeFeature => 'Napauta muokataksesi, pyyhkäise suorittaaksesi tai poistaaksesi';

  @override
  String get memoryManagement => 'Muistinhallinta';

  @override
  String get transcriptLoadFailed => 'Litterointia ei voitu ladata.';

  @override
  String get diagnosticsExportTitle => 'Omi-laitediagnostiikka';

  @override
  String get updateOmiFirmware => 'Päivitä omin laiteohjelmisto';

  @override
  String get importTooManyAttempts => 'Liian monta tuontia juuri nyt. Yritä myöhemmin uudelleen.';

  @override
  String get noAppsFound => 'Sovelluksia ei löytynyt';

  @override
  String get phoneSetupStep1Subtitle => 'Soitamme sinulle vahvistusta varten';

  @override
  String get deleteSyncedFiles => 'Poista synkronoidut tallenteet';

  @override
  String speakerLabelVoiceStatus(String state) {
    String _temp0 = intl.Intl.selectLogic(
      state,
      {
        'learned': 'Ääni opittu',
        'pending': 'Opitaan ääntä…',
        'disabled': 'Äänen tallennus on pois päältä',
        'other': 'Ääntä ei ole vielä opittu',
      },
    );
    return '$_temp0';
  }

  @override
  String get recordingsMayCaptureOthers =>
      'Tallenteet voivat tallentaa muiden ääniä. Varmista, että sinulla on kaikkien osallistujien suostumus ennen käyttöönottoa.';

  @override
  String get helpful => 'Hyödyllinen';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return 'Ladataan $model: $received / $total MB';
  }

  @override
  String get permissions => 'Käyttöoikeudet';

  @override
  String get audioDownloadSuccess => 'Ääni ladattu onnistuneesti';

  @override
  String get confirmPlanChange => 'Vahvista tilauksen muutos';

  @override
  String get wrappedThatAwkwardMoment => 'Se kiusallinen hetki';

  @override
  String get calendarProviders => 'Kalenteripalvelut';

  @override
  String evidenceAutoUnconfirmed(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count automaattista merkintää ei vielä vahvistettu',
      one: '1 automaattinen merkintä ei vielä vahvistettu',
    );
    return '$_temp0';
  }

  @override
  String get importData => 'Tuo tietoja';

  @override
  String get weekdayMon => 'Ma';

  @override
  String get deviceStorageTitle => 'Laitteen tallennustila';

  @override
  String get externalAppAccess => 'Ulkoisten sovellusten käyttöoikeus';

  @override
  String get transcriptionUnavailable => 'Litterointi ei ole käytettävissä';

  @override
  String get termsAndPrivacyPolicy => 'Ehdot ja Tietosuojakäytäntö';

  @override
  String get noImportsYet => 'Ei tuonteja vielä';

  @override
  String get openOmiOnAppleWatchDescription =>
      'Omi-sovellus on asennettu Apple Watchiin. Avaa se ja napauta Aloita aloittaaksesi.';

  @override
  String dreamReportFailed(String error) {
    return 'Epäonnistui ($error)';
  }

  @override
  String get sendSummary => 'Lähetä tiivistelmä';

  @override
  String get filterAll => 'Kaikki';

  @override
  String get deleteChatMessage => 'Se poistuu aiemmista keskusteluista pysyvästi.';

  @override
  String get timeout10Minutes => '10 minuuttia';

  @override
  String get noCalendarEventsNearby => 'Tämän ajankohdan tienoilta ei löytynyt kalenteritapahtumia.';

  @override
  String get cancelSyncQuestion => 'Peruuta synkronointi?';

  @override
  String get whatShouldWeMake => 'Mitä meidän pitäisi tehdä?';

  @override
  String get usageListened => 'Listened';

  @override
  String get errorUpdatingStripeDetails => 'Virhe Stripe-tietojen päivityksessä! Yritä myöhemmin uudelleen.';

  @override
  String get conversationEndAfterHours => 'Keskustelut päättyvät nyt 4 tunnin hiljaisuuden jälkeen';

  @override
  String get issueActivatingApp => 'Sovelluksen aktivoinnissa ilmeni ongelma. Yritä uudelleen.';

  @override
  String get appCreatedSuccessfully => 'Sovellus luotu onnistuneesti!';

  @override
  String get categoryNews => 'Uutiset';

  @override
  String get phoneSearchHint => 'Hae';

  @override
  String peoplePinnedCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count kiinnitettyä',
      one: '1 kiinnitetty',
    );
    return '$_temp0';
  }

  @override
  String get wrappedHours => 'tuntia';

  @override
  String get phoneKeypad => 'Näppäimistö';

  @override
  String get peopleFilterLowConfidence => 'Matala varmuus';

  @override
  String get agreeToContributeData => 'Ymmärrän ja suostun antamaan tietoni AI:n kouluttamiseen';

  @override
  String get addGoal => 'Lisää tavoite';

  @override
  String get dreamReportRunInProgress => 'Ajo on jo käynnissä. Yritä uudelleen minuutin kuluttua.';

  @override
  String importedConfig(String providerName) {
    return 'Tuotu $providerName-kokoonpano';
  }

  @override
  String monthsAgo(int count) {
    return '$count kuukautta sitten';
  }

  @override
  String get downgradeLimitationsHeading => 'Kohtaat nämä rajoitukset:';

  @override
  String get chatRemoveSelectedText => 'Poista lainattu teksti';

  @override
  String get firmwareBatteryAbove15 => 'Akku yli 15%';

  @override
  String reviewQuestionSamePerson(String name) {
    return 'Sama henkilö kuin ”$name”?';
  }

  @override
  String get effectCountsALot => 'Auttaa paljon';

  @override
  String get sdCard => 'SD-kortti';

  @override
  String get openInGoogleCalendar => 'Avaa Google-kalenterissa';

  @override
  String get appleHealthFeatureSecureTitle => 'Turvallinen synkronointi';

  @override
  String get conversationDeveloperToolsDescription =>
      'Näytä Kopioi keskustelun tunnus ja Testaa kehote keskustelun valikossa';

  @override
  String get host => 'Isäntä';

  @override
  String get deleteReasonMissingFeatures => 'Tarvitsemiani ominaisuuksia puuttuu';

  @override
  String get syncingInProgress => 'Synkronointi käynnissä';

  @override
  String get tabDone => 'Tehty';

  @override
  String get revoke => 'Peruuta';

  @override
  String get mcp => 'MCP';

  @override
  String get anyoneCanDiscoverTemplate => 'Kuka tahansa voi löytää mallisi';

  @override
  String get mcpDescription =>
      'Yhdistääksesi Omin muihin sovelluksiin lukeaksesi, etsiäksesi ja hallitaksesi muistojasi ja keskustelujasi. Luo avain aloittaaksesi.';

  @override
  String get connectionLostDescription => 'Yhteys katkesi. Tarkista internet-yhteytesi ja yritä uudelleen.';

  @override
  String chatAppsNoChatsMessage(String app) {
    return 'Omin kanssa sovelluksessa $app käymäsi keskustelut näkyvät täällä.';
  }

  @override
  String get storedLocallyNeverShared =>
      'Tallennettu tähän puhelimeen. Lähetetään vain transkriptiopalvelun tarjoajalle.';

  @override
  String get morePaymentMethodsComingSoon => 'Lisää maksutapoja tulossa pian';

  @override
  String get allCaughtUp => 'Kaikki ajan tasalla';

  @override
  String previewImageLabel(int index, int total) {
    return 'Kuvakaappaus $index/$total';
  }

  @override
  String get disable => 'Poista käytöstä';

  @override
  String get recordings => 'Nauhoitukset';

  @override
  String get enterPersonsName => 'Syötä henkilön nimi';

  @override
  String get newConversationCreated => 'Uusi keskustelu luotu';

  @override
  String resetsInDays(int count) {
    return 'Nollautuu $count päivän kuluttua';
  }

  @override
  String get confidenceConfirmed => 'Vahvistettu';

  @override
  String get bulkExportInProgress => 'Viedään…';

  @override
  String get detectLanguages => 'Tunnista yli 10 kieltä';

  @override
  String get phoneSpeaker => 'Kaiutin';

  @override
  String get visitWebsite => 'Käy verkkosivustolla';

  @override
  String get howToTakeGoodSample => 'Miten ottaa hyvä näyte?';

  @override
  String get clearChat => 'Tyhjennä keskustelu';

  @override
  String languageSetTo(String language) {
    return 'Kieleksi asetettu $language';
  }

  @override
  String get deviceOnboardingVoiceReplyHeadphonesDescription =>
      'Yksityinen. Puhuu vain numeroiden AirPods, Bluetooth tai langallisten kuulokkeiden kautta.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'Tilauksesi pysyy aktiivisena $date asti. Sen jälkeen menetät pääsyn rajoittamattomiin ominaisuuksiin.';
  }

  @override
  String get clientSecret => 'Asiakassalaisuus';

  @override
  String get pairingTitleAppleWatch => 'Yhdistä Apple Watch';

  @override
  String get share => 'Jaa';

  @override
  String get yourPrivacyYourControl => 'Yksityisyytesi, sinun hallinnassasi';

  @override
  String get tapToCopy => 'Kopioi napauttamalla';

  @override
  String get feedbackTitleFoundAlternative => 'Mihin vaihdat?';

  @override
  String get all => 'All';

  @override
  String get filterCapabilities => 'Ominaisuudet';

  @override
  String get tagOtherSegments => 'Merkitse muut segmentit';

  @override
  String get entityDecisions => 'Päätökset';

  @override
  String get tasksCreatedInWorkspace => 'Tehtävät luodaan tähän työtilaan';

  @override
  String get fairUseDailyTranscription => 'Daily Transcription';

  @override
  String get pausePlayback => 'Tauko';

  @override
  String get sharedTasksLinkExpired => 'Näitä jaettuja tehtäviä ei löytynyt tai linkki on vanhentunut.';

  @override
  String get editConversationDialogTitle => 'Muokkaa keskustelua';

  @override
  String get deleteMemoryConfirmation => 'Poistetaanko tämä muisto? Tätä ei voi perua.';

  @override
  String get appUnderReviewMessage =>
      'Sovelluksesi on tarkistettavana ja näkyy vain sinulle. Se julkaistaan hyväksynnän jälkeen.';

  @override
  String get illDoItLater => 'Teen sen myöhemmin';

  @override
  String get captureStillRecording => 'Tallennus jatkuu';

  @override
  String confidenceNextLabels(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Nimeä heidät vielä $count keskustelussa.',
      one: 'Nimeä heidät vielä 1 keskustelussa.',
    );
    return '$_temp0';
  }

  @override
  String get speakerTagPromptAnswerFailed => 'Tallennus epäonnistui. Yritä uudelleen.';

  @override
  String get feedbackReasonSummaryIncomplete => 'Incomplete';

  @override
  String get errorActivatingApp => 'Virhe sovelluksen aktivoinnissa';

  @override
  String get tasksCompleted => 'Tehtäviä suoritettu';

  @override
  String onboardingStepOf(int current, int total) {
    return 'Vaihe $current/$total';
  }

  @override
  String get downgradeAnyway => 'Vaihda silti';

  @override
  String get leaveBlank => 'Jätä tyhjäksi';

  @override
  String get chatAppsViewChats => 'Näytä keskustelut';

  @override
  String get captureScreenRecordingPermissionRequired => 'Näytön tallennusoikeus vaaditaan';

  @override
  String get accountCutoverUpdateRequiredTitle => 'Päivitys vaaditaan';

  @override
  String weeksAgo(int count) {
    return '$count viikkoa sitten';
  }

  @override
  String get phoneEndCall => 'Lopeta';

  @override
  String get startupFailedMessage =>
      'Jokin meni pieleen Omin käynnistyessä. Tarkista yhteytesi ja yritä sitten uudelleen.';

  @override
  String get permissionRevokedTitle => 'Lupa peruttu';

  @override
  String get chatFeatures => 'Chat-ominaisuudet';

  @override
  String get couldNotLoadMap => 'Karttaa ei voitu ladata';

  @override
  String get selectContactsToShare => 'Valitse yhteystiedot jakamista varten';

  @override
  String get ok => 'OK';

  @override
  String get memoryReviewConfirmed => 'Vahvistettu.';

  @override
  String get deleteKnowledgeGraph => 'Poista tietograafi';

  @override
  String get reviewChangeFailed => 'Muutosta ei voitu päivittää. Yritä uudelleen.';

  @override
  String get limitless => 'Limitless';

  @override
  String uploadingToCloud(int current, int total) {
    return 'Ladataan $current/$total';
  }

  @override
  String get dontSeeYourDevice => 'Etkö näe laitettasi?';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Tehtäväsi synkronoidaan $appName-tilillesi';
  }

  @override
  String appSettingsLabel(String appName) {
    return '$appName-asetukset';
  }

  @override
  String get chatBlockShowLess => 'Näytä vähemmän';

  @override
  String get mindMap => 'Mind Map';

  @override
  String get authorizationBearer => 'Authorization: Bearer <avain>';

  @override
  String get dreamReportWouldSuggestTasks => 'Ehdottaisi tehtäviä';

  @override
  String get dreamReportWouldAsk => 'Kysyisi sinulta';

  @override
  String get getFreeUnlimitedAccess => 'Hanki ilmainen rajaton käyttöoikeus';

  @override
  String get yourDaysJourney => 'Päiväsi matka';

  @override
  String get transcriptReceived => 'Litterointi vastaanotettu';

  @override
  String get expand => 'Laajenna';

  @override
  String get onboardingCompleteMessage =>
      'Pidä Omi käynnissä pari päivää. Keskustelusi, muistosi ja tehtäväsi alkavat täyttyä.';

  @override
  String get trainFamilyProfiles => 'Kouluta profiileja ystäville ja perheelle';

  @override
  String get selectText => 'Valitse teksti';

  @override
  String get generatingDescription => 'Luodaan kuvausta…';

  @override
  String get deviceOnboardingStarConversationDesc => 'Merkitse keskustelu tärkeäksi';

  @override
  String disableAppNamed(String appName) {
    return 'Poista $appName käytöstä';
  }

  @override
  String get deleteConversationConfirmation => 'Poistetaanko tämä keskustelu? Tätä ei voi perua.';

  @override
  String get contentCopied => 'Sisältö kopioitu leikepöydälle';

  @override
  String get joinTheCommunity => 'Liity yhteisöön!';

  @override
  String get noContactsWithPhoneNumbers => 'Puhelinnumerollisia yhteystietoja ei löytynyt';

  @override
  String get removeAttachment => 'Poista liite';

  @override
  String get followTheVoiceInstructions => 'Seuraa aaniohjelta';

  @override
  String get createYourOwnApp => 'Luo oma sovellus';

  @override
  String get paymentDetails => 'Maksutiedot';

  @override
  String get tellOmiWhoSaidIt => 'Kerro Omi:lle, kuka sen sanoi 🗣️';

  @override
  String audioInputSetTo(String deviceName) {
    return 'Äänitulo asetettu: $deviceName';
  }

  @override
  String get pleaseEnterValidEmail => 'Anna kelvollinen sähköpostiosoite';

  @override
  String get thisYear => 'Tänä vuonna';

  @override
  String get noTranscriptMessage => 'Tällä keskustelulla ei ole litterointia.';

  @override
  String get appearanceDark => 'Tumma';

  @override
  String get createCustomTemplate => 'Luo mukautettu malli';

  @override
  String get monthMay => 'Touko';

  @override
  String get tasksAddedToList => 'Tehtävät lisätään tähän luetteloon';

  @override
  String isTriggeredBy(String triggerDescription) {
    return 'On $triggerDescription.';
  }

  @override
  String get deleteConversationTitle => 'Poista keskustelu?';

  @override
  String get accountCutoverUpdateRequiredMessage => 'Asenna uusin Omi-sovellus jatkaaksesi tilin siirron jälkeen.';

  @override
  String get txtFormat => 'TXT';

  @override
  String chatAppsDisconnectMessage(String app) {
    return 'Omi lakkaa vastaamasta sovelluksessa $app ja poistaa sille tallennetun keskusteluhistorian. Sovelluksessa $app jo olevat viestit säilyvät siellä.';
  }

  @override
  String get captureWithCamera => 'Ota kameralla';

  @override
  String get appIdLabel => 'Sovelluksen tunnus';

  @override
  String get endpointUrl => 'Päätepisteen URL';

  @override
  String get actionItemUpdated => 'Tehtävä päivitetty';

  @override
  String itemsSelected(int count) {
    return '$count valittu';
  }

  @override
  String get onboardingWhatIKnowAboutYouDescription => 'Tämä kartta päivittyy, kun Omi oppii keskusteluistasi.';

  @override
  String diagnosticsLastDuration(String duration) {
    return 'Viimeiset $duration';
  }

  @override
  String get pairingDescLimitless =>
      'Kun mikä tahansa valo on näkyvissä, paina kerran ja paina sitten pitkään, kunnes laite näyttää vaaleanpunaista valoa, vapauta sitten.';

  @override
  String get chatBlockOpenConversation => 'Avaa keskustelu';

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '$used/$limit näkemystä saavutettu tässä kuussa';
  }

  @override
  String get connectionErrorDesc => 'Yhteys palvelimeen epäonnistui. Tarkista internet-yhteytesi ja yritä uudelleen.';

  @override
  String get enterWordsCommaSeparated => 'Syötä sanat (pilkulla erotettuna)';

  @override
  String get otherDevicesComingSoon => 'Muut laitteet tulossa pian';

  @override
  String speakerSuggestionChip(String name) {
    return '$name?';
  }

  @override
  String get speakerTagPromptNotAPersonToast => 'Merkitty: ei ihminen';

  @override
  String get createKeyToGetStarted => 'Luo avain aloittaaksesi';

  @override
  String get captureRecordingSeparateConfirm => 'Erota';

  @override
  String get diagnosticsDrops => 'Katkokset';

  @override
  String lowBatteryAlertBody(int level) {
    return 'Akkusi on $level%. Aika ladata! 🔋';
  }

  @override
  String get deviceOnboardingTurnOffSubtitle => 'Pidä painiketta pohjassa 3 sekuntia';

  @override
  String get done => 'Valmis';

  @override
  String get wifiConfigurationSubtitle => 'Syötä WiFi-tunnuksesi, jotta laite voi ladata laiteohjelmiston.';

  @override
  String get permissionGrantedNow =>
      'Käyttöoikeus myönnetty! Nyt:\n\nAvaa Omi-sovellus kellossasi ja napauta \"Jatka\" alla';

  @override
  String get setUpPayPal => 'Määritä PayPal';

  @override
  String get statusProcessed => 'Käsitelty';

  @override
  String phoneFreeCallsRemaining(int remaining, int limit) {
    return '$remaining/$limit ilmaista puhelua jäljellä tässä kuussa';
  }

  @override
  String get event => 'Tapahtuma';

  @override
  String get conversationEvents => 'Keskustelutapahtumat';

  @override
  String get uninstall => 'Poista asennus';

  @override
  String get appCreators => 'Sovellusten tekijät';

  @override
  String get muted => 'Mykistetty';

  @override
  String get deleteRecapAction => 'Poista';

  @override
  String get addAppErrorSelectingThumbnailRetry => 'Virhe pikkukuvan valinnassa. Yritä uudelleen.';

  @override
  String get basicPlanDescription => '300 premium-minuuttia + rajoittamaton laitteella';

  @override
  String get countrySelectionPermanent => 'Maavalinasi on pysyvä eikä sitä voi muuttaa myöhemmin.';

  @override
  String get transcriptionConnecting => 'Yhdistetään litterointia…';

  @override
  String transcriptionsPendingFraction(int pending, int total) {
    return 'Jonossa olevat transkriptiot $pending/$total';
  }

  @override
  String get apiKeyAuth => 'API-avaimen todennus';

  @override
  String downloadModelWithName(String model) {
    return 'Lataa malli ($model)';
  }

  @override
  String get devModeInvalidDaySummaryWebhookUrl => 'Virheellinen päiväyhteenvedon webhook-URL';

  @override
  String get memoryReviewSaveFailed => 'Tallennus epäonnistui, yritä uudelleen';

  @override
  String get payYourSttProvider => 'Omi on ilmainen. Maksat transkriptiopalvelun tarjoajalle suoraan.';

  @override
  String get dailySummaryHeader => 'PÄIVITTÄINEN YHTEENVETO';

  @override
  String get fairUseStageWarning => 'Varoitus';

  @override
  String get multipleSpeakersDesc =>
      'Näyttää siltä, että nauhoituksessa on useita puhujia. Varmista, että olet hiljaisessa paikassa ja yritä uudelleen.';

  @override
  String get pastChats => 'Aiemmat keskustelut';

  @override
  String get listeningMins => 'Kuunteleminen (min)';

  @override
  String get pairingDescOmi => 'Pidä laitetta painettuna, kunnes se värisee, käynnistääksesi sen.';

  @override
  String get deviceOnboardingIntroSubtitle =>
      'Kokeile live-litterointia, kysymyksen esittämistä ja kaksoisnapautuksen pikanäppäintä.';

  @override
  String get autoRemoveSyncedCopiesTitle => 'Poista synkronoidut kopiot automaattisesti';

  @override
  String chatAppsReadOnlyFooter(String app) {
    return 'Nämä keskustelut ovat täällä vain luettavissa. Vastaa sovelluksessa $app.';
  }

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'Mikrofoni vaihdettu. Jatketaan ${countdown}s kuluttua';
  }

  @override
  String get takePhoto => 'Ota kuva';

  @override
  String get cancelSync => 'Peruuta synkronointi';

  @override
  String appSettings(String appName) {
    return '$appName-asetukset';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'Mikrofoniluvam tarkistus epäonnistui: $error';
  }

  @override
  String get micGain => 'Mikrofonin vahvistus';

  @override
  String get collectingData => 'Kerätään tietoja…';

  @override
  String get memoryReadOnlyHint => 'Tämä muisto säilytetään historiana, eikä sitä voi muokata.';

  @override
  String get appUnderReviewOwner =>
      'Sovelluksesi on tarkistettavana ja näkyvissä vain sinulle. Se tulee julkiseksi hyväksynnän jälkeen.';

  @override
  String get addNewPerson => 'Lisää uusi henkilö';

  @override
  String get nameSpeakerTitle => 'Nimeä puhuja';

  @override
  String get downloadingAudioFromSdCard => 'Ladataan ääntä laitteesi SD-kortilta';

  @override
  String get pendantSyncingRecordings => 'Synkronoidaan tallenteita riipuksestasi…';

  @override
  String get otaNotSupported => 'Tätä laiteohjelmistoa ei voi päivittää Wi-Fin kautta.';

  @override
  String get wrappedSomethingWentWrong => 'Jokin meni\npieleen';

  @override
  String get screenRecording => 'Näytön tallennus';

  @override
  String get audioProcessedLocally =>
      'Ääni käsitellään paikallisesti. Toimii offline, yksityisempi, mutta kuluttaa enemmän akkua.';

  @override
  String get onboardingSignIn => 'Kirjaudu sisään';

  @override
  String timeDaysPlural(int count) {
    return '$count päivää';
  }

  @override
  String get memoryReviewTitle => 'Mitä opin tänään';

  @override
  String get hidePassword => 'Piilota salasana';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get disconnected => 'Yhteys katkaistu';

  @override
  String get revokeApiKeyQuestion => 'Peruuta API-avain?';

  @override
  String get detectBrowserBasedMeetings => 'Tunnista selainpohjaiset kokoukset';

  @override
  String get failedToDeleteConversations => 'Keskustelujen poistaminen epäonnistui';

  @override
  String get raybanMetaCapturePhoto => 'Ota valokuva';

  @override
  String get bleSpeed => '~30 KB/s BLE:n kautta';

  @override
  String get conversationPromptPlaceholder => 'Olet mahtava sovellus, saat keskustelun litteroinnin ja yhteenvedon…';

  @override
  String get secureAuthViaGoogleAccount => 'Turvallinen todennus Google-tilin kautta';

  @override
  String get omiHas => 'Omilla on:';

  @override
  String get raybanMetaContinue => 'Jatka';

  @override
  String get pauseRecording => 'Keskeytä nauhoitus';

  @override
  String get evidenceNothing => 'Et ole vielä nimennyt tai vahvistanut häntä';

  @override
  String get noActivityYet => 'Ei vielä toimintaa';

  @override
  String get enterPasswordError => 'Anna salasanasi';

  @override
  String get forgetDeviceConfirmTitle => 'Unohdetaanko laite?';

  @override
  String get ratingsAndReviews => 'Arviot ja arvostelut';

  @override
  String get addApiKeyAfterImport => 'Sinun on lisättävä oma API-avaimesi tuonnin jälkeen';

  @override
  String get alreadyOnStableFirmware => 'Sinulla on jo uusin vakaa versio.';

  @override
  String get deleteAccountConfirm => 'Haluatko varmasti poistaa tilisi?';

  @override
  String get recordingInfo => 'Nauhoituksen tiedot';

  @override
  String get feedbackReasonSummaryInaccurate => 'Inaccurate';

  @override
  String get pendantRecordingTitle => 'Tallennus riipuksella';

  @override
  String get deleteWhileProcessingMessage =>
      'Tämä tallenne on ladattu, mutta Omi luo yhä keskustelua. Jos poistat sen nyt ja käsittely epäonnistuu, sitä ei voi palauttaa. Poistetaanko silti?';

  @override
  String get createNewKey => 'Luo uusi avain';

  @override
  String get firmwareDownloadFailedMessage =>
      'Päivitystä ei voitu ladata, eikä laitettasi muutettu. Tarkista internetyhteys ja yritä uudelleen.';

  @override
  String get loadingTasks => 'Ladataan tehtäviä…';

  @override
  String get previousResult => 'Edellinen tulos';

  @override
  String get reviewLoadFailed => 'Kysymyksiäsi ei voitu ladata.';

  @override
  String get onDevice => 'Laitteella';

  @override
  String get bluetoothSyncEnabled => 'Bluetooth-synkronointi käytössä';

  @override
  String get categorySafety => 'Turvallisuus';

  @override
  String get unknownLocation => 'Tuntematon sijainti';

  @override
  String get newMemoryTitle => 'Uusi muisto';

  @override
  String get conversationCannotBeMerged => 'Tätä keskustelua ei voi yhdistää (lukittu tai jo yhdistämässä)';

  @override
  String get summaryGenerated => 'Yhteenveto luotu';

  @override
  String get createKey => 'Luo Avain';

  @override
  String get letOmiChooseAutomatically => 'Anna Omin valita paras sovellus automaattisesti';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'Käynnistä $deviceName uudelleen päivityksen viimeistelemiseksi.';
  }

  @override
  String get goals => 'Tavoitteet';

  @override
  String get wrappedAnErrorOccurred => 'Tapahtui virhe';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'Mikrofonin luvan tarkistus epäonnistui: $error';
  }

  @override
  String get connectLater => 'Yhdistä myöhemmin';

  @override
  String get wrappedRememberedByOmi => 'tallentanut Omi';

  @override
  String get fairUseStatusNormal => 'Käyttösi on normaalien rajojen sisällä.';

  @override
  String get includePersonalEventsDescription => 'Sisällytä henkilökohtaiset tapahtumat ilman osallistujia';

  @override
  String get week => 'Viikko';

  @override
  String get willLikelyCrash => 'Tämän käyttöönotto aiheuttaa todennäköisesti sovelluksen kaatumisen tai jäätymisen.';

  @override
  String get selectPrimaryLanguage => 'Valitse ensisijainen kielesi';

  @override
  String get pilotFeaturesDescription => 'Nämä ominaisuudet ovat testejä, eikä tukea taata.';

  @override
  String get askOmi => 'Kysy Omilta';

  @override
  String get ifYouCancel => 'Jos peruutat:';

  @override
  String get audioOutput => 'Äänilähtö';

  @override
  String get memoryReviewWrong => 'Väärin';

  @override
  String get couldNotSchedulePlanChange => 'Paketin vaihtoa ei voitu ajoittaa. Yritä uudelleen.';

  @override
  String speakerLabelEarlierMatches(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Löytyi $count aiemmasta keskustelusta',
      one: 'Löytyi 1 aiemmasta keskustelusta',
    );
    return '$_temp0';
  }

  @override
  String get deviceOnboardingListening => 'Kuunnellaan…';

  @override
  String get speechProfileEnrollmentPrompt =>
      'Jotta Omi tietää, mikä ääni on sinun — puhu mistä tahansa noin 5 sekuntia.';

  @override
  String get mcpServerUrl => 'MCP Server URL';

  @override
  String get chatBlockMemory => 'Muisto';

  @override
  String get noStarredConversations => 'Ei tähdellä merkittyjä keskusteluja';

  @override
  String get syncStatusTooOld => 'Liian vanha synkronoitavaksi — Omi ei voi hyväksyä sitä';

  @override
  String connectedAsUser(String userId) {
    return 'Yhdistetty käyttäjänä: $userId';
  }

  @override
  String get phonePageTitle => 'Puhelin';

  @override
  String get buildGraphButton => 'Rakenna graafi';

  @override
  String get issuesCreatedInRepo => 'Ongelmat luodaan oletusrepositoriossasi';

  @override
  String get scopeUserFacts => 'Käyttäjän tiedot';

  @override
  String get unableToLoadPlans => 'Suunnitelmia ei voitu ladata';

  @override
  String get deleteRecording => 'Poista nauhoitus';

  @override
  String get appDeleteFailed => 'Sovelluksen poistaminen epäonnistui. Yritä myöhemmin uudelleen.';

  @override
  String get addAppUpdatedSuccess => 'Sovellus päivitetty onnistuneesti 🚀';

  @override
  String get reviewCaughtUpTitle => 'Ei vastattavaa';

  @override
  String get copyConversationId => 'Kopioi keskustelun tunnus';

  @override
  String get helpImproveOmiBySharing => 'Auta parantamaan Omi:ta jakamalla anonymisoituja analytiikkatietoja';

  @override
  String get dataEncryptedBanner =>
      'Tietosi on oletuksena suojattu vahvalla salauksella, ja sinä hallitset, miten niitä säilytetään ja käytetään.';

  @override
  String get redo => 'Tallenna uudelleen';

  @override
  String get updateOmiGlassFirmware => 'Päivitä OmiGlassin laiteohjelmisto';

  @override
  String get deviceUnpairedMessage =>
      'Laitteen pariliitos poistettu. Siirry Asetukset > Bluetooth ja unohda laite pariliitoksen poistamisen viimeistelemiseksi.';

  @override
  String speakerLabelText(String part, String name) {
    String _temp0 = intl.Intl.selectLogic(
      part,
      {
        'likely': 'Todennäköinen',
        'soundsLike': 'Kuulostaa henkilöltä $name',
        'notPerson': 'Ei $name',
        'carried': 'Edelleen $name. Siirretty edellisestä keskustelustasi.',
        'change': 'Vaihda',
        'alsoTitle': 'Onko tämä myös $name?',
        'alsoBody': 'Omi löysi saman äänen aiemmista keskusteluista.',
        'confirmed': 'Vahvistit tämän nimen',
        'other': 'Tarkista',
      },
    );
    return '$_temp0';
  }

  @override
  String get continueWithApple => 'Jatka Applella';

  @override
  String get iUnderstand => 'Ymmärrän';

  @override
  String get memoryProvenanceAndroid => 'Android';

  @override
  String get saving => 'Tallennetaan…';

  @override
  String get deviceOnboardingDoubleTapTitle => 'Mukauta kaksoisnapautus';

  @override
  String get allMemoriesPublicResult => 'Kaikki muistot ovat nyt julkisia';

  @override
  String get chatAppsAddToContacts => 'Lisää Omi yhteystietoihin';

  @override
  String get wrappedDays => 'päivää';

  @override
  String get invalidJsonError => 'Virheellinen JSON';

  @override
  String syncCardNeedsAttention(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count tallennetta vaatii huomiota',
      one: '1 tallenne vaatii huomiota',
    );
    return '$_temp0';
  }

  @override
  String get wrappedSwipeUpToBegin => 'Pyyhkäise ylös aloittaaksesi';

  @override
  String addedToService(String serviceName) {
    return 'Lisätty kohteeseen $serviceName';
  }

  @override
  String get advanced => 'Lisäasetukset';

  @override
  String get autoCreateAndTagNewSpeakers => 'Luo ja merkitse uudet puhujat automaattisesti';

  @override
  String get appCapabilities => 'Sovelluksen ominaisuudet';

  @override
  String get onboardingMicrophoneDenied =>
      'Mikrofonilupa evätty. Myönnä lupa kohdassa Järjestelmäasetukset > Tietosuoja ja turvallisuus > Mikrofoni.';

  @override
  String get pleaseEnterFolderName => 'Anna kansion nimi';

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'Bluetooth-luvan tarkistus epäonnistui: $error';
  }

  @override
  String get invalidRecordingDetected => 'Virheellinen nauhoitus havaittu';

  @override
  String get appAnalytics => 'Sovellusanalytiikka';

  @override
  String get captureRecordingsSheetTitle => 'Tämän keskustelun tallenteet';

  @override
  String deletedLimitlessConversations(int count) {
    return 'Poistettu $count Limitless-keskustelua';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'Virhe kuvan valinnassa: $error';
  }

  @override
  String get unnamedSpeakerLabel => 'Puhuja';

  @override
  String get failedToCreateApp => 'Sovelluksen luonti epäonnistui. Yritä uudelleen.';

  @override
  String get planUpdate => 'Tilauksen päivitys';

  @override
  String get timeout5Minutes => '5 minuuttia';

  @override
  String get deleteSample => 'Poista näyte';

  @override
  String get willNotSeeAgain => 'Et voi nähdä sitä uudelleen.';

  @override
  String get thisMonth => 'Tässä kuussa';

  @override
  String get enterName => 'Syötä nimi';

  @override
  String get memoryThisDevice => 'Tämä laite';

  @override
  String get verifiedNumbersDescription => 'Kun soitat jollekulle, he nakevat taman numeron';

  @override
  String get deviceOnboardingSingleTapHint => 'Tuo oli yksittäisnapautus – yritä napauttaa kahdesti nopeasti!';

  @override
  String autoClosingInSeconds(int seconds) {
    return 'Sulkeutuu automaattisesti $seconds sekunnissa';
  }

  @override
  String get chatAppsProPerkContext => 'Omi muistaa asiayhteyden kaikissa sovelluksissa';

  @override
  String get errorProcessingConversation => 'Virhe keskustelun käsittelyssä. Yritä myöhemmin uudelleen.';

  @override
  String get profileSettings => 'Profiilin asetukset';

  @override
  String get statusUnprocessed => 'Käsittelemätön';

  @override
  String get deleteConversationMessage => 'Tämä poistaa myös liittyvät muistot, tehtävät ja äänitiedostot.';

  @override
  String get cancelSubscriptionQuestion => 'Peruuta tilaus?';

  @override
  String get forUnlimitedFreeTranscription => 'rajattomaan ilmaiseen litterointiin.';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used/$limit min käytetty';
  }

  @override
  String get categoryPersonalWellness => 'Henkilökohtainen hyvinvointi';

  @override
  String get automaticTranslation => 'Automaattinen käännös';

  @override
  String get defaultAiAssistant => 'Oletus AI-assistentti';

  @override
  String get allDataErased => 'Muistosi ja keskustelusi poistetaan.';

  @override
  String entityDue(String date) {
    return 'Määräpäivä $date';
  }

  @override
  String get feedbackChatWithUs => 'More detail? Chat with us';

  @override
  String get speakerTagPromptSomeoneNew => 'Joku uusi';

  @override
  String get inProgress => 'Käynnissä';

  @override
  String get raybanMetaCheckAgain => 'Tarkista uudelleen';

  @override
  String get fairUseStageNormal => 'Normaali';

  @override
  String get pairingTitleLimitless => 'Aseta Limitless pariliitostilaan';

  @override
  String get usingNativeIosSpeech => 'Käytetään iOS:n natiivia puheentunnistusta';

  @override
  String get actionItemDeletedSuccessfully => 'Tehtävä poistettu onnistuneesti';

  @override
  String get failedToSetLanguage => 'Kielen asetus epäonnistui';

  @override
  String get appHomeUrl => 'Sovelluksen kotisivun URL';

  @override
  String get appNameLabel => 'Sovelluksen nimi';

  @override
  String get localStorageDisabled => 'Paikallinen tallennustila pois käytöstä';

  @override
  String get appReEnable => 'Ota uudelleen käyttöön';

  @override
  String get migrationFailed => 'Siirto epäonnistui';

  @override
  String get markComplete => 'Merkitse valmiiksi';

  @override
  String get lastUsedLabel => 'Viimeksi käytetty';

  @override
  String get chatCleared => 'Chat tyhjennetty';

  @override
  String get revokeApiKeyWarning =>
      'Tätä avainta käyttävät sovellukset menettävät API-käyttöoikeuden. Tätä ei voi perua.';

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return 'Näytönkaappausluvan tarkistus epäonnistui: $error';
  }

  @override
  String get troubleshootingSteps =>
      'Vianmääritys:\n\n1. Varmista, että Omi on asennettu kelloosi\n2. Avaa Omi-sovellus kellossasi\n3. Etsi käyttöoikeuspyyntö\n4. Napauta \"Salli\" kehotettaessa\n5. Kello-sovellus sulkeutuu - avaa se uudelleen\n6. Palaa ja napauta \"Jatka\" iPhonessasi';

  @override
  String get location => 'Sijainti';

  @override
  String get chatAppsWhatsAppMeantime => 'Telegram ja iMessage toimivat jo nyt samoilla muistoilla ja tehtävillä.';

  @override
  String get sliderOff => 'Pois';

  @override
  String get checkingFirmwareVersion => 'Tarkistetaan laiteohjelmiston versiota…';

  @override
  String get reviewUnknownSpeaker => 'Tuntematon puhuja';

  @override
  String get professionSales => 'Myynti';

  @override
  String get noRssiDataYet => 'Ei vielä RSSI-tietoja';

  @override
  String get emptyOldMessage => '✅ Ei vanhoja tehtäviä';

  @override
  String deleteSampleConfirmation(String name) {
    return 'Henkilön $name ääninäyte poistetaan. Tätä ei voi perua.';
  }

  @override
  String get saveUrlButton => 'Tallenna URL';

  @override
  String get onboardingNotificationDeniedSystemPrefs => 'Ilmoituslupa evätty. Myönnä lupa Järjestelmäasetuksissa.';

  @override
  String get languageForTranscription => 'Omi käyttää tätä kieltä litterointiin, yhteenvetoihin ja muistoihin.';

  @override
  String get updatedLabel => 'PÄIVITETTY';

  @override
  String get content => 'Sisältö';

  @override
  String get phoneCallButton => 'Soita';

  @override
  String get exportStartedMayTakeFewSeconds => 'Vienti aloitettu. Tämä voi kestää muutaman sekunnin…';

  @override
  String dreamReportPrivacyHeld(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count ilmoitusta pidätetty yksityisyyden vuoksi',
      one: '1 ilmoitus pidätetty yksityisyyden vuoksi',
    );
    return '$_temp0';
  }

  @override
  String firmwareBatteryTooLow(int level) {
    return 'Akun varaus on $level %. Lataa laite vähintään 15 %:iin ennen päivitystä.';
  }

  @override
  String get appearance => 'Ulkoasu';

  @override
  String noTasksOnDate(Object date) {
    return 'Ei tehtäviä $date';
  }

  @override
  String get deleteFlowFeedbackHint => 'Valinnainen — ajatuksesi auttavat meitä rakentamaan parempaa tuotetta.';

  @override
  String get bluetooth => 'Bluetooth';

  @override
  String get cancelUpdate => 'Peruuta päivitys';

  @override
  String get syncStatusConversationCreated => 'Keskustelu luotu';

  @override
  String get reconnecting => 'Yhdistetään uudelleen…';

  @override
  String get tasksToday => 'Tänään';

  @override
  String taskCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count tehtävää',
      one: '1 tehtävä',
    );
    return '$_temp0';
  }

  @override
  String get noUpcomingMeetings => 'Ei tulevia tapaamisia';

  @override
  String get invalidRecordingMultipleSpeakers => 'Virheellinen nauhoitus havaittu';

  @override
  String get startupFailedTitle => 'Omi ei voinut käynnistyä';

  @override
  String contactsSelectedCount(int count) {
    return '$count valittu';
  }

  @override
  String get skipForward10Seconds => '10 sekuntia eteenpäin';

  @override
  String get noItems => 'Ei kohteita';

  @override
  String get timeout30Minutes => '30 minuuttia';

  @override
  String get signInSuccess => 'Kirjautuminen onnistui!';

  @override
  String get syncStatusDownloadingFromDevice => 'Ladataan laitteeltasi';

  @override
  String get makePrivate => 'Tee yksityiseksi';

  @override
  String get update => 'Päivitä';

  @override
  String get aiGenCreatingAppIcon => 'Luodaan sovelluskuvaketta…';

  @override
  String get wrappedIntenseDay => 'Intensiivinen';

  @override
  String get raybanMetaSkipForNow => 'Ohita toistaiseksi';

  @override
  String diagnosticsReconnectedIn(String duration) {
    return 'yhdistetty uudelleen $duration kuluttua';
  }

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'Olet vaihtamassa Rajoittamaton-pakettisi pakettiin $title.';
  }

  @override
  String get appsAskWith => 'Kysy Omilta käyttäen';

  @override
  String get noMemoriesFound => 'Muistoja ei löytynyt';

  @override
  String get noMemoriesYet => 'Ei vielä muistoja';

  @override
  String get captureRecordingSeparateFailed => 'Erottaminen epäonnistui. Yritä uudelleen.';

  @override
  String get pinAsBaseline => 'Kiinnitä perustaksi';

  @override
  String get voiceRecognitionSettings => 'Äänentunnistus';

  @override
  String get chatAppsComingLater => 'Tulossa myöhemmin';

  @override
  String get sliderMax => 'Maks.';

  @override
  String get deleteWhileProcessingTitle => 'Käsitellään yhä';

  @override
  String get devModeSettingsSaved => 'Asetukset tallennettu!';

  @override
  String get fairUseToday => 'Tänään';

  @override
  String get exportDataDesc => 'Vie keskustelut JSON-tiedostoon';

  @override
  String get whatsYourName => 'Mikä on nimesi?';

  @override
  String get onDeviceSlower => 'Laitteella tapahtuva puheentunnistus voi olla hitaampaa tällä laitteella.';

  @override
  String get categoryProductivityLifestyle => 'Tuottavuus ja elämäntapa';

  @override
  String get addToYourTaskList => 'Lisätäänkö tehtävälistallesi?';

  @override
  String get meetingScreenshotFallbackCaption => 'Kuvakaappaus tästä kokouksesta';

  @override
  String get effectCountsALittle => 'Auttaa vähän';

  @override
  String get pairingTitleFriendPendant => 'Aseta Friend Pendant pariliitostilaan';

  @override
  String get peopleStatsIncomplete => 'Määrät voivat olla puutteellisia.';

  @override
  String get tapToAddGoal => 'Napauta lisätäksesi tavoitteen';

  @override
  String get payment => 'Maksu';

  @override
  String get omiDebugLog => 'Omin vianjäljitysloki';

  @override
  String get showMeetingsMenuBar => 'Näytä tulevat kokoukset valikkorivissä';

  @override
  String get mostInstalls => 'Eniten asennuksia';

  @override
  String chatUsageMessages(String used, String limit) {
    return 'Chat: $used / $limit viestiä tässä kuussa';
  }

  @override
  String get chat => 'Keskustelu';

  @override
  String get areYouThere => 'Oletko siellä?';

  @override
  String get highestRating => 'Korkein arvio';

  @override
  String get pleaseSpecify => 'Tarkenna';

  @override
  String get staging => 'Testiympäristö';

  @override
  String get cancelReasonBatteryDrain => 'Huoli akun kulumisesta';

  @override
  String get apiKeys => 'API-avaimet';

  @override
  String conversationsCreated(int count) {
    return '$count keskustelua luotu';
  }

  @override
  String get trainingDataProgram => 'Koulutustietojen ohjelma';

  @override
  String get customBackendUrlTitle => 'Mukautettu palvelimen URL';

  @override
  String get omiSyncsAudioFiles => 'Omi synkronoi sitten äänitiedostot palvelimen kanssa';

  @override
  String get reviewAnswerMe => 'Minä';

  @override
  String get debugDiagnostics => 'Vianjäljitys ja diagnostiikka';

  @override
  String get confidenceReasonNotHeard => 'ei vielä kuultu';

  @override
  String get doubleTapAction => 'Kaksoisnapaututstoiminto';

  @override
  String get showTasksOnHomepage => 'Näytä tehtävät etusivulla';

  @override
  String failedToStartUpdate(String error) {
    return 'Päivityksen aloitus epäonnistui: $error';
  }

  @override
  String get feedbackReasonSummaryWrongContext => 'Wrong context';

  @override
  String get pleaseProvideValidDescription => 'Anna kelvollinen kuvaus';

  @override
  String get appRejectedNotice =>
      'Sovelluksesi on hylätty. Päivitä sovelluksen tiedot ja lähetä se uudelleen tarkistettavaksi.';

  @override
  String get deleteOnDeviceModel => 'Poista malli';

  @override
  String get languageSettingsHelperText =>
      'Sovelluksen kieli muuttaa valikkoja ja painikkeita. Ensisijainen kieli vaikuttaa siihen, miten tallenteet litteroidaan.';

  @override
  String get deleteConversationsMessage => 'Tämä poistaa myös niiden muistot, tehtävät ja äänitiedostot.';

  @override
  String get usageBestMonth => 'Best month';

  @override
  String get creating => 'Luodaan…';

  @override
  String get microphoneAccessDescription =>
      'Omi tarvitsee mikrofonin käyttöoikeuden tallentaakseen keskustelusi ja tarjotakseen transkriptioita.';

  @override
  String get cancelReasonNotUsing => 'En käytä tarpeeksi';

  @override
  String get wrappedWeveAllBeenThere => 'Olemme kaikki olleet siellä!';

  @override
  String get chatAppsProblemRateLimited => 'Liian monta yritystä. Odota minuutti ja yritä uudelleen.';

  @override
  String get selectOption => 'Valitse';

  @override
  String get languageBenefits => 'Omi käyttää tätä kieltä litterointiin, yhteenvetoihin ja muistoihin.';

  @override
  String get triggerConversationIntegration => 'Käynnistä keskustelun luonti-integraatio';

  @override
  String get integrationSetupRequired => 'Jos tämä on integraatiosovellus, varmista että asennus on valmis.';

  @override
  String get clickPlayToResumeOrStop => 'Napsauta toista jatkaaksesi tai pysäytä lopettaaksesi';

  @override
  String disconnectedFrom(String appName) {
    return 'Yhteys katkaistu palveluun $appName';
  }

  @override
  String get subscribe => 'Tilaa';

  @override
  String get permissionsChangeAnytime => 'Voit muuttaa näitä milloin tahansa kohdassa Asetukset > Käyttöoikeudet';

  @override
  String get enableRemindersAccess =>
      'Ota käyttöön muistutusten käyttöoikeus asetuksissa käyttääksesi Apple Muistutuksia';

  @override
  String get selectProviderTemplate => 'Valitse palveluntarjoajan malli…';

  @override
  String get initialisingSystemAudio => 'Alustetaan järjestelmän ääntä';

  @override
  String get excellent => 'Erinomainen';

  @override
  String get chatBlockGoal => 'Tavoite';

  @override
  String get deleteFolder => 'Poista kansio';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'Avaimen luominen epäonnistui: $error';
  }

  @override
  String get whisperModelSizeSmall => 'Pieni';

  @override
  String get pleaseCopyKeyNow => 'Ole hyvä ja kopioi se nyt ja kirjoita se turvalliseen paikkaan. ';

  @override
  String get unresolvedSpeakersNotice => 'Puhujien merkinnät eivät ehkä täsmää tämän keskustelun äänitteiden välillä.';

  @override
  String get omisMemoryCleared => 'Omin muisti sinusta on tyhjennetty';

  @override
  String get manageApp => 'Hallitse sovellusta';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return 'Näytönkaappausluvan tila: $status. Tarkista Järjestelmäasetukset.';
  }

  @override
  String get edit => 'Muokkaa';

  @override
  String get redownload => 'Lataa uudelleen';

  @override
  String get chatBlockConversation => 'Keskustelu';

  @override
  String get loadingApps => 'Ladataan sovelluksia…';

  @override
  String get chatPromptPlaceholder =>
      'Olet mahtava sovellus, tehtäväsi on vastata käyttäjien kyselyihin ja saada heidät tuntemaan olonsa hyväksi…';

  @override
  String get stripeConnectedAccountAgreement => 'Stripe Connected Account -sopimus';

  @override
  String get autoSync => 'Automaattinen synkronointi';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'Tietograafi poistettu onnistuneesti';

  @override
  String get optInAndOptOutOptions => 'Suostumis- ja kieltäytymisvaihtoehdot';

  @override
  String get permissionReadMemories => 'Lue muistoja';

  @override
  String get noSpacesInWorkspace => 'Tiloja ei löytynyt tästä työtilasta';

  @override
  String get reviewYesMerge => 'Kyllä, yhdistä';

  @override
  String get voiceMode => 'Äänitila';

  @override
  String get fairUseStageThrottle => 'Rajoitettu';

  @override
  String get deleteChatQuestion => 'Poistetaanko tämä keskustelu?';

  @override
  String get failedToGetCallToken => 'Tokenin haku epaonnistui. Vahvista numerosi ensin.';

  @override
  String get selectTime => 'Valitse aika';

  @override
  String get sdCardProcessing => 'SD-kortin käsittely';

  @override
  String errorConnectingRayBanMeta(String error) {
    return 'Virhe yhdistettäessä Ray-Ban Metaan: $error';
  }

  @override
  String get couldNotLoadImportHistory => 'Tuontihistoriaa ei voitu ladata';

  @override
  String get noApiKeysFound => 'API-avaimia ei löytynyt. Luo yksi aloittaaksesi.';

  @override
  String get appDisabledTitle => 'Tämä sovellus on poistettu käytöstä eikä sitä voi asentaa.';

  @override
  String get syncStatusBackedUp => 'Varmuuskopioitu';

  @override
  String get speakerTagPromptThatsMeAction => 'Se olen minä';

  @override
  String timeCompactHoursAndMins(int hours, int mins) {
    return '${hours}t ${mins}m';
  }

  @override
  String get chatPrompt => 'Chat-kehote';

  @override
  String get voicePreviewSample => 'Hei, olen Omi. Tämä on ääneni.';

  @override
  String get saved => 'Tallennettu';

  @override
  String get grantPermissionButton => 'Myönnä käyttöoikeus';

  @override
  String get subscription => 'Tilaus';

  @override
  String get capabilityFeatured => 'Suositellut';

  @override
  String get pdfConversationExport => 'Keskustelun vienti';

  @override
  String get unknown => 'Tuntematon';

  @override
  String get yourMeetings => 'Kokouksesi';

  @override
  String get uploadingVoiceProfile => 'Ladataan ääniprofiiliasi….';

  @override
  String get apiUrl => 'API-URL';

  @override
  String get reportMessage => 'Raportoi viesti';

  @override
  String get passwordLabel => 'Salasana';

  @override
  String get permanentlyRemoveAllMemories => 'Poista pysyvästi kaikki muistot Omista';

  @override
  String get transcriptionSlowerLessAccurate => 'Transkriptio on huomattavasti hitaampi ja epätarkempi.';

  @override
  String get filterManual => 'Manuaalinen';

  @override
  String get keepMyPlan => 'Säilytä tilaukseni';

  @override
  String get setupQuestionAge => '3. Minkä ikäinen olet?';

  @override
  String get addAppSelectTriggerEvent => 'Valitse laukaisutapahtuma sovelluksellesi';

  @override
  String get defaultWorkspace => 'Oletustyötila';

  @override
  String get errorUpdatingAppStatus => 'Sovelluksen tilan päivittämisessä tapahtui virhe.';

  @override
  String get invalidJsonConfig => 'Virheellinen JSON-kokoonpano';

  @override
  String get detailedDiagnosticMessages => 'Yksityiskohtaiset diagnostiikkaviestit';

  @override
  String get mergingInBackground => 'Yhdistetään taustalla. Tämä voi kestää hetken.';

  @override
  String get setDefaultApp => 'Aseta oletussovellus';

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Sinun on valtuutettava Omi luomaan tehtäviä $appName-tilillesi. Tämä avaa selaimesi todennusta varten.';
  }

  @override
  String get cleanUpEllipsis => 'Siivoa…';

  @override
  String get addTask => 'Lisää tehtävä';

  @override
  String get getCreative => 'Ole luova';

  @override
  String get captureRecordingOpenFailed => 'Tallennetta ei voitu avata.';

  @override
  String get emptyTodoMessage => '🎉 Kaikki hoidettu!\nEi odottavia tehtäviä';

  @override
  String get onboardingSetupTitle => 'Omia otetaan käyttöön';

  @override
  String get sharePeriodAllTime => 'Tähän mennessä Omi on:';

  @override
  String get translationNotice => 'Käännösilmoitus';

  @override
  String captureRecordingError(String error) {
    return 'Tallennuksen aikana tapahtui virhe: $error';
  }

  @override
  String get downloadAudio => 'Lataa ääni';

  @override
  String get identifySpeaker => 'Tunnista puhuja';

  @override
  String get viewTranscript => 'Näytä litterointi';

  @override
  String get makeAllMemoriesPublic => 'Tee kaikki muistot julkisiksi';

  @override
  String get xTwitter => 'X (Twitter)';

  @override
  String get frequencyOff => 'Pois';

  @override
  String get apiEnvironment => 'API-ympäristö';

  @override
  String get processingTakingLonger => 'Vielä käynnissä — tämä kestää tavallista kauemmin.';

  @override
  String get firmwareUpdateFailedTitle => 'Päivitys epäonnistui';

  @override
  String get unresolvedQuestions => 'Ratkaisemattomat kysymykset';

  @override
  String get chatAppsMessage => 'Viesti';

  @override
  String get dreamReportManual => 'Manuaalinen';

  @override
  String get enterSttHttpEndpoint => 'Kirjoita STT HTTP -päätepisteesi';

  @override
  String get beforeUpdateMakeSure => 'Ennen päivitystä varmista:';

  @override
  String get transcriptionReconnecting => 'Yhdistetään litterointia uudelleen…';

  @override
  String get deviceName => 'Laitteen nimi';

  @override
  String neoSubtitle(int count) {
    return '$count kysymystä kuukaudessa';
  }

  @override
  String chatUsageProgress(String used, String limit) {
    return '$used / $limit käytetty';
  }

  @override
  String get noChangesInReview => 'Ei muutoksia arvostelussa päivitettäväksi.';

  @override
  String get allMemories => 'Kaikki muistot';

  @override
  String get needMicrophonePermission =>
      'Tarvitsemme mikrofonin käyttöoikeuden.\n\n1. Napauta \"Myönnä käyttöoikeus\"\n2. Salli iPhonessasi\n3. Kello-sovellus sulkeutuu\n4. Avaa uudelleen ja napauta \"Jatka\"';

  @override
  String get keepSpeakingUntil100 => 'Jatka puhumista kunnes saavutat 100%.';

  @override
  String get singleLanguageModeInfo =>
      'Yhden kielen tila on käytössä. Käännös on poistettu käytöstä paremman tarkkuuden vuoksi.';

  @override
  String get thisCannotBeUndone => 'Tätä ei voi perua.';

  @override
  String get setupSkipHelp => 'Ohita, en halua auttaa :C';

  @override
  String get speakerTagPromptNoAction => 'Ei…';

  @override
  String labelCopied(String label) {
    return '$label kopioitu';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'Virhe äänitulolaitteen vaihdossa: $error';
  }

  @override
  String get remembering => 'Muistaminen';

  @override
  String get externalAppAccessDescription =>
      'Seuraavilla asennetuilla sovelluksilla on ulkoisia integraatioita ja ne voivat käyttää tietojasi, kuten keskusteluja ja muistoja.';

  @override
  String get preferences => 'Asetukset';

  @override
  String get wrappedFunDay => 'Hauska';

  @override
  String get effectNeeded => 'Tarvitaan tilaan Vahvistettu';

  @override
  String get importantConversationBody => 'Sinulla oli juuri tärkeä keskustelu. Napauta jakaaksesi yhteenvedon muille.';

  @override
  String whyConfidenceMenu(String level) {
    return 'Miksi $level?';
  }

  @override
  String get cmdRequired => '⌘ vaaditaan';

  @override
  String get completed => 'Valmis';

  @override
  String get deviceOnboardingVoiceReplyStatusAlwaysSpeaker => 'Toistaa ääneen puhelimen kaiuttimesta.';

  @override
  String get effectCountsAgainst => 'Haittaa';

  @override
  String get recaps => 'Yhteenvedot';

  @override
  String get shareConversationQuestion => 'Jaetaanko keskustelu?';

  @override
  String get actionItemsCopiedToClipboard => 'Tehtävät kopioitu leikepöydälle';

  @override
  String get appleHealthManageNote =>
      'Omi käyttää Apple Healthia Applen HealthKit-kehyksen kautta. Voit perua käyttöoikeuden milloin tahansa iOS-asetuksista.';

  @override
  String addingToService(String serviceName) {
    return 'Lisätään kohteeseen $serviceName…';
  }

  @override
  String get needHelpGettingStarted => 'Tarvitsetko apua aloittamiseen?';

  @override
  String get thanksForAuthorizing => 'Kiitos valtuutuksesta!';

  @override
  String get assistantVoiceSettingsTitle => 'Ääni';

  @override
  String get cloudStorageDisabled => 'Pilvitallennustila pois käytöstä';

  @override
  String get reviewPlayClip => 'Toista klippi';

  @override
  String get storeAudioOnCloud => 'Tallenna ääni pilveen';

  @override
  String get syncStatusBackingUp => 'Synkronoidaan…';

  @override
  String get peopleFilterPinned => 'Kiinnitetyt';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName asetettu oletusyhteenvetosovellukseksi';
  }

  @override
  String get githubRepositoryUrlRequired => 'GitHub-tietovaraston URL vaaditaan';

  @override
  String get microphoneAccess => 'Mikrofonin käyttöoikeus';

  @override
  String get cancelSubscriptionButton => 'Peruuta tilaus';

  @override
  String get signal => 'Signaali';

  @override
  String get failedToConnectAsanaRetry => 'Yhteyden muodostaminen Asanaan epäonnistui. Yritä uudelleen.';

  @override
  String get keyCreatedMessage => 'Uusi avaimesi on luotu. Kopioi se nyt. Et näe sitä enää uudelleen.';

  @override
  String autoRemoveSyncedCopiesDays(int days) {
    return 'Synkronoidut kopiot poistetaan $days päivän jälkeen';
  }

  @override
  String get wrappedMostCringeMoment => 'Noloin';

  @override
  String get activity => 'Toiminta';

  @override
  String get calendarSettings => 'Kalenteriasetukset';

  @override
  String get additionalFeedbackOptional => 'Lisäpalaute (valinnainen)';

  @override
  String get phoneAllow => 'Salli';

  @override
  String get noDeviceConnectedUseMic => 'Laitetta ei ole yhdistetty. Käytetään puhelimen mikrofonia.';

  @override
  String get stripeOnboardingInstructions =>
      'Suorita Stripe-käyttöönottoprosessi selaimessasi. Tämä sivu päivittyy automaattisesti, kun prosessi on valmis.';

  @override
  String availableSpaceWithValue(String space) {
    return 'Käytettävissä oleva tila: $space';
  }

  @override
  String get conversationDetails => 'Keskustelun tiedot';

  @override
  String get wrappedYouHadFunnyMoments => 'Sinulla oli hauskoja hetkiä tänä vuonna!';

  @override
  String get actionReadConversations => 'Lue keskusteluja';

  @override
  String speakerTagPromptIsThisPerson(String name) {
    return 'Onko tämä $name?';
  }

  @override
  String get openSettings => 'Avaa asetukset';

  @override
  String get alwaysAvailable => 'aina käytettävissä.';

  @override
  String get rating1PlusStars => '1+ tähti';

  @override
  String get pauseResume => 'Keskeytä/Jatka';

  @override
  String get conversationDeleted => 'Keskustelu poistettu';

  @override
  String get memoryReviewRight => 'Oikein';

  @override
  String get deleteGoal => 'Poista tavoite';

  @override
  String get youtube => 'YouTube';

  @override
  String get untitledConversation => 'Nimetön keskustelu';

  @override
  String get yourOmiInsights => 'Omi-näkemyksesi';

  @override
  String get compareTranscripts => 'Vertaa litterointeja';

  @override
  String get pause => 'Tauko';

  @override
  String get successfullyConnectedGoogle => 'Yhdistetty onnistuneesti Googleen!';

  @override
  String planRenewsOn(String date) {
    return 'Tilauksesi uusitaan $date.';
  }

  @override
  String chatAppsOpenApp(String app) {
    return 'Avaa $app';
  }

  @override
  String get dailySummaryDescription => 'Saa henkilökohtainen yhteenveto päivän keskusteluista ilmoituksena.';

  @override
  String conversationPhotosCount(int count) {
    return '$count kuvaa';
  }

  @override
  String get errorLoadingAudio => 'Äänen lataaminen epäonnistui';

  @override
  String get couldNotAccessFile => 'Valittua tiedostoa ei voitu käyttää';

  @override
  String deleteGraphFailed(String error) {
    return 'Graafin poisto epäonnistui: $error';
  }

  @override
  String get reviewOpenDetailsHint => 'Avaa tiedot';

  @override
  String get conversationTimeoutDesc =>
      'Valitse kuinka kauan odotetaan hiljaisuutta ennen keskustelun automaattista päättämistä:';

  @override
  String get transcriptionJsonPlaceholder => 'Liitä JSON-asetukset tähän…';

  @override
  String get loadingCapabilities => 'Ladataan ominaisuuksia…';

  @override
  String get activeStatus => 'Aktiivinen';

  @override
  String get noDailyRecapsYet => 'Ei vielä päivittäisiä yhteenvetoja';

  @override
  String get wouldLikePermission => 'Haluaisimme lupasi tallentaa ääninauhoituksesi. Tässä syy:';

  @override
  String get chatBlockRecommendedNextSteps => 'Suositellut seuraavat vaiheet';

  @override
  String get tryAdjustingSearchTerms => 'Yritä muokata hakuehtojasi';

  @override
  String get connectOmiWithAI => 'Yhdistä Omi AI-avustajiin';

  @override
  String get whenToReceiveDailySummary => 'Milloin haluat päivittäisen yhteenvedon';

  @override
  String syncCardReadyCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count tallennetta valmiina synkronoitavaksi',
      one: '1 tallenne valmis synkronoitavaksi',
    );
    return '$_temp0';
  }

  @override
  String get yourApiKey => 'API-AVAIMESI';

  @override
  String failedToLoadRepos(String error) {
    return 'Repositorioiden lataaminen epäonnistui: $error';
  }

  @override
  String get syncingMessages => 'Synkronoidaan viestejä palvelimen kanssa…';

  @override
  String get pleaseSelectARating => 'Valitse arvosana';

  @override
  String get suggestedTemplates => 'Ehdotetut mallit';

  @override
  String get updateAppQuestion => 'Päivitä sovellus?';

  @override
  String get frequencyDescOff => 'Ei proaktiivisia ilmoituksia';

  @override
  String get triggerAudioBytes => 'Äänitavut';

  @override
  String get confirmClearChat => 'Tyhjennetäänkö tämä keskustelu? Tätä ei voi perua.';

  @override
  String get dataPrivacy => 'Tietosuoja';

  @override
  String get audioFromOmiWillAppearHere => 'Omi-laitteesi ääni näkyy täällä';

  @override
  String get durationLabel => 'Kesto';

  @override
  String get deviceOnboardingAllSetTitle => 'Kaikki on valmista';

  @override
  String msgSelectImagesError(String error) {
    return 'Virhe kuvien valinnassa: $error';
  }

  @override
  String evidenceCardPicks(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Valittu $count ehdotuksessa',
      one: 'Valittu 1 ehdotuksessa',
    );
    return '$_temp0';
  }

  @override
  String get connectionLostDesc => 'Yhteys keskeytyi. Tarkista internet-yhteytesi ja yritä uudelleen.';

  @override
  String get defaultLabel => 'Oletus';

  @override
  String get raybanMetaAllowCamera => 'Salli lasien kamera';

  @override
  String get addAppSelectCoreCapability => 'Valitse vielä yksi ydintoiminto sovelluksellesi';

  @override
  String get noManualMemories => 'Ei vielä manuaalisia muistoja';

  @override
  String get deliveryTime => 'Toimitusaika';

  @override
  String get defaultProjectOptional => 'Oletusprojekti (valinnainen)';

  @override
  String get devModeInvalidAudioBytesWebhookUrl => 'Virheellinen äänitavujen webhook-URL';

  @override
  String get ignoredVoicesTitle => 'Ohitetut äänet';

  @override
  String get refreshManifest => 'Päivitä manifesti';

  @override
  String get diagnosticsRightNow => 'Juuri nyt';

  @override
  String get reviewDue => 'Määräpäivä';

  @override
  String get unmute => 'Poista mykistys';

  @override
  String get recordingsDeleted => 'Nauhoitukset poistettu.';

  @override
  String get failedToDeleteFolder => 'Kansion poistaminen epäonnistui';

  @override
  String get reviewAnswerOther => 'Muu';

  @override
  String get exportedConversations => 'Viedyt keskustelut Omista';

  @override
  String get privacyPolicy => 'Tietosuojakäytäntö';

  @override
  String get editReply => 'Muokkaa vastausta';

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription ja on $triggerDescription.';
  }

  @override
  String errorSaving(String error) {
    return 'Virhe tallentaessa: $error';
  }

  @override
  String get diagnosticsConnectedFor => 'Yhdistettynä';

  @override
  String get callStateConnecting => 'Yhdistetaan…';

  @override
  String get conversationUrlNotShared => 'Keskustelun URL-osoitetta ei voitu jakaa.';

  @override
  String get tooShortDesc => 'Puhetta ei havaittu tarpeeksi. Puhu enemmän ja yritä uudelleen.';

  @override
  String get failedToShareRecap => 'Yhteenvetoa ei voitu jakaa';

  @override
  String get billingMonthly => 'Kuukausittain';

  @override
  String get developingLogic => 'Kehitetään logiikkaa';

  @override
  String get phoneContinue => 'Jatka';

  @override
  String get successfullyConnectedGitHub => 'Yhdistetty onnistuneesti GitHubiin!';

  @override
  String get failedToSubmitReview => 'Arvostelun lähettäminen epäonnistui. Yritä uudelleen.';

  @override
  String get anyoneCanDiscover => 'Kuka tahansa voi löytää sovelluksesi';

  @override
  String get v2Undetected => 'V2 ei havaittu';

  @override
  String get usageIrlEvents => 'Livetapahtumat';

  @override
  String get conversationPromptHint => 'esim. Poimi tehtävät, päätökset ja keskeiset havainnot keskustelusta.';

  @override
  String get openProviderDocs => 'Avaa dokumentaatio';

  @override
  String get showMeetingsInMenuBar => 'Näytä kokoukset valikkorivissä';

  @override
  String get viewPlansAndUsage => 'Näytä Suunnitelmat ja Käyttö';

  @override
  String get buildSubmitCustomOmiApp => 'Rakenna ja lähetä mukautettu Omi-sovelluksesi';

  @override
  String get failedToRefreshGoogleStatus => 'Google-yhteyden tilan päivitys epäonnistui.';

  @override
  String get feedbackSubtitleTooExpensive => 'Palautteesi auttaa meitä löytämään oikean tasapainon.';

  @override
  String get startUsingOmi => 'Aloita Omin käyttö';

  @override
  String get dreamReportLearnedWords => 'Opitut sanat';

  @override
  String get actionItemCreated => 'Tehtävä luotu';

  @override
  String get exportAllConversationsToJson => 'Vie kaikki keskustelusi JSON-tiedostoon.';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'Tarkista internet-yhteytesi ja yritä uudelleen';

  @override
  String get callStateEnded => 'Puhelu paattynyt';

  @override
  String get phoneNumberHint => 'Puhelinnumero';

  @override
  String get tasksGroupByProject => 'Ryhmittele projektin mukaan';

  @override
  String get phoneCallsUnlimitedOnly => 'Puhelut Omin kautta';

  @override
  String get frequencyDescMinimal => 'Vain kiireelliset asiat, noin 1–3 päivässä';

  @override
  String get changeYourName => 'Vaihda nimesi';

  @override
  String get editYourReply => 'Muokkaa vastaustasi';

  @override
  String get publicMemories => 'Julkiset muistot';

  @override
  String get monthDec => 'Joulu';

  @override
  String get reviewNewPersonName => 'Heidän nimensä';

  @override
  String get googleCalendarConnectPrompt =>
      'Yhdistä Google Kalenteri, niin voit linkittää keskusteluja kalenteritapahtumiin.';

  @override
  String get realtimeAudioBytes => 'Reaaliaikaiset äänitavut';

  @override
  String get trackYourGoalsOnHomepage => 'Seuraa henkilökohtaisia tavoitteitasi etusivulla';

  @override
  String get chatAddAttachment => 'Lisää liite';

  @override
  String get beta => 'BETA';

  @override
  String get createMemory => 'Luo muisti';

  @override
  String get permissionsRequiredDescription =>
      'Omi tarvitsee muutamia käyttöoikeuksia toimiakseen oikein. Myönnä ne jatkaaksesi.';

  @override
  String get dataCollectionMessage =>
      'Jatkamalla keskustelusi, tallenteet ja henkilötiedot tallennetaan turvallisesti palvelimillemme tarjotaksemme tekoälyavusteisia näkemyksiä ja mahdollistaaksemme kaikki sovelluksen ominaisuudet.';

  @override
  String get batteryLevel => 'Akun taso';

  @override
  String get searchCountries => 'Etsi maita...';

  @override
  String get confidenceSheetTitle => 'Varmuus';

  @override
  String get deviceModelLabel => 'Laitteen malli';

  @override
  String get noStableFirmwareFound => 'Laitteellesi ei löytynyt vakaata laiteohjelmistoversiota.';

  @override
  String get noResultsFound => 'Tuloksia ei löytynyt';

  @override
  String get wrappedMins => 'min';

  @override
  String get chatAppsTelegramSubtitle => 'Valmis kahdella napautuksella';

  @override
  String get categoryConversationAnalysis => 'Keskusteluanalyysi';

  @override
  String get target => 'Tavoite';

  @override
  String get apiKeyRequired => 'API-avain vaaditaan';

  @override
  String otaUpdatedMessage(String deviceName) {
    return '$deviceName on päivitetty ja käynnistyy uudelleen itsestään.';
  }

  @override
  String get reconnections => 'Uudelleenyhdistämiset';

  @override
  String errorCheckingConnection(String error) {
    return 'Virhe yhteyden tarkistuksessa: $error';
  }

  @override
  String get usageMonth => 'Tässä kuussa';

  @override
  String get additionalSpeechSampleRemoved => 'Lisäpuhenäyte poistettu';

  @override
  String get speakerTagPromptExcerptSaved => 'Vastaus tallennettu tälle katkelmalle.';

  @override
  String get omisStorage => 'Omin tallennustila';

  @override
  String get recordingAndTranscription => 'Tallennus ja litterointi';

  @override
  String get categoryCommunication => 'Viestintä';

  @override
  String get wrappedYouDidIt => 'Onnistuit! 🎉';

  @override
  String get failedToDeleteItems => 'Kohteiden poisto epäonnistui';

  @override
  String speakerLabelLinesLabeled(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Nimetty $count riviä',
      one: 'Nimetty 1 rivi',
    );
    return '$_temp0';
  }

  @override
  String get generatingLink => 'Luodaan linkkiä…';

  @override
  String get clickHereForAppBuildingGuides =>
      'Napsauta tästä sovelluksen rakentamisohjeiden ja dokumentaation saamiseksi';

  @override
  String get authUrl => 'Todennuksen URL';

  @override
  String get addAppCapabilityConflictWithPersona => 'Muita toimintoja ei voi valita Personan kanssa';

  @override
  String get deviceOnboardingVoiceReplyGenericHeadphones => 'Kuulokkeet';

  @override
  String get clearAll => 'Tyhjennä kaikki';

  @override
  String get noKnowledgeGraphYet => 'Ei vielä tietograafia';

  @override
  String get messageReportedSuccessfully => '✅ Viesti raportoitu onnistuneesti';

  @override
  String get paymentFailedToSetDefault => 'Oletusmaksutavan asettaminen epäonnistui. Yritä myöhemmin uudelleen.';

  @override
  String get memoryReviewUpdated => 'Päivitetty.';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'Pakettisi peruuntuu $date.';
  }

  @override
  String get welcomeToOmi => 'Tervetuloa Omi';

  @override
  String get phoneFreeCallLimitReached => 'Ilmaisten puheluiden kuukausiraja on täynnä. Se nollautuu ensi kuussa.';

  @override
  String get omiTranscriptionOptimized =>
      'Omin reaaliaikainen litterointi on tehty reaaliaikaisiin keskusteluihin ja merkitsee, kuka sanoi mitäkin.';

  @override
  String get chatAppsLoadFailedTitle => 'Chat-sovellusten lataus epäonnistui';

  @override
  String get continueWithGoogle => 'Jatka Googlella';

  @override
  String get setupSteps => 'Asennusvaiheet';

  @override
  String totalMemoriesCount(int count) {
    return 'Sinulla on $count muistoa yhteensä';
  }

  @override
  String get feedbackSubtitleBatteryDrain => 'Tämä auttaa laitteistotiimiämme parantamaan.';

  @override
  String get tryIt => 'Kokeile';

  @override
  String get chatAppsInsights => 'Omin oivallukset';

  @override
  String nFiles(int count) {
    return '$count tallennetta';
  }

  @override
  String get clearChatTitle => 'Tyhjennä chat?';

  @override
  String get onlyYouCanUseTemplate => 'Vain sinä voit käyttää tätä mallia';

  @override
  String get raybanMetaCameraExplanation =>
      'Omi käyttää lasiesi kameraa lisätäkseen valokuvia keskusteluihisi. Voit ohittaa tämän ja käyttää vain ääntä.';

  @override
  String get deviceDiagnosticsTicket => 'Support ticket code';

  @override
  String get capabilityTasks => 'Tehtävät';

  @override
  String get copyUrl => 'Kopioi URL';

  @override
  String keepItemPublic(String item) {
    return 'Pidä $item julkisena';
  }

  @override
  String get chatStarterTeachMe => 'Voitko opettaa minulle jotain uutta?';

  @override
  String get cancelReasonDetailHint => 'Arvostamme kaikkea palautetta…';

  @override
  String get checkConnectionTryAgain => 'Tarkista yhteys ja yritä uudelleen.';

  @override
  String get backToConversations => 'Takaisin keskusteluihin';

  @override
  String get merge => 'Yhdistä';

  @override
  String get couldNotLaunchUpgradePage => 'Päivityssivua ei voitu avata. Yritä uudelleen.';

  @override
  String get deviceOnboardingTranscriptionSubtitle => 'Sano muutama sana ja katso, miten ne ilmestyvät reaaliajassa';

  @override
  String get deleteOnDeviceModelConfirm => 'Poistetaanko tämä malli?';

  @override
  String get reviewQuestionSpeaker => 'Kuka sanoi tämän?';

  @override
  String updatedDate(String date) {
    return 'Päivitetty $date';
  }

  @override
  String get saveSettings => 'Tallenna Asetukset';

  @override
  String get alreadyGavePermission =>
      'Olet jo antanut meille luvan tallentaa nauhoituksiasi. Tässä muistutus siitä, miksi tarvitsemme sen:';

  @override
  String get appCreatedAndInstalled => 'Sovellus luotu ja asennettu!';

  @override
  String get failedToRefreshNotionStatus => 'Notion-yhteyden tilan päivitys epäonnistui.';

  @override
  String get deviceOnboardingProcessingQuestion => 'Käsitellään kysymystäsi…';

  @override
  String get chatBlockTask => 'Tehtävä';

  @override
  String get pendantNotConnected => 'Riipus ei ole yhdistetty. Yhdistä synkronoidaksesi.';

  @override
  String get createActionItem => 'Luo tehtävä';

  @override
  String get logsCopied => 'Lokit kopioitu';

  @override
  String get timeout5MinutesDesc => 'Lopeta keskustelu 5 minuutin hiljaisuuden jälkeen';

  @override
  String get msgUploadFileFailed => 'Tiedoston lataus epäonnistui, yritä myöhemmin uudelleen';

  @override
  String get reportMessageConfirm => 'Ilmoitetaanko tästä viestistä?';

  @override
  String deletePersonConfirmation(String name) {
    return 'Tämä poistaa henkilön $name ääninäytteet, eikä sitä voi perua. Hänen repliikkinsä aiemmissa keskusteluissa muuttuvat nimettömiksi puhujiksi.';
  }

  @override
  String get weekdayTue => 'Ti';

  @override
  String get liveTranscript => 'Live-transkriptio';

  @override
  String timeDaysAndHours(int days, int hours) {
    return '$days päivää $hours tuntia';
  }

  @override
  String versionLabel(String version) {
    return 'Versio $version';
  }

  @override
  String get cancelConsequenceDelay => '5-7 sekunnin käsittelyviive (laitteen mallit)';

  @override
  String captureRecordingSeparateMessage(String recording) {
    return '$recording näytetään omana keskustelunaan, eikä sitä enää ryhmitellä tähän tapahtumaan.';
  }

  @override
  String get updateAvailableTitle => 'Päivitys saatavilla';

  @override
  String get dreamReportShadowBanner =>
      'Esikatselutila: Dream näyttää, mitä se muuttaisi, mutta tilissäsi ei muutu vielä mitään.';

  @override
  String get sharedTasksAcceptFailed => 'Tehtäviä ei voitu hyväksyä. Olet ehkä jo hyväksynyt tämän jaon.';

  @override
  String get appPricingLabel => 'Sovelluksen hinnoittelu';

  @override
  String get reDownload => 'Lataa uudelleen';

  @override
  String get recordWithPhoneMic => 'Tallenna puhelimen mikrofonilla';

  @override
  String appDisabledOn(String date) {
    return 'Poistettu käytöstä $date.';
  }

  @override
  String get play => 'Toista';

  @override
  String get private => 'Yksityinen';

  @override
  String get speakerTagPromptNotSureAction => 'En ole varma';

  @override
  String get showDiscardedConversationsDesc => 'Sisällytä hylätyksi merkityt keskustelut';

  @override
  String get captureModeLiveDescription => 'Litteroi reaaliajassa puhuessasi.';

  @override
  String get subscriptionCancelledSuccessfully =>
      'Tilaus peruutettu onnistuneesti. Se pysyy aktiivisena nykyisen laskutuskauden loppuun.';

  @override
  String get tapToSetAGoal => 'Napauta asettaaksesi tavoitteen';

  @override
  String get tellUsMoreWhatWentWrong => 'Kerro meille lisää siitä, mikä meni pieleen…';

  @override
  String get downgradeToFreemiumTitle => 'Siirrytäänkö ilmaiseen tilaukseen?';

  @override
  String get usageTasks => 'Tehtävät';

  @override
  String get chatReplyOffline => 'Yhteyttä ei voitu muodostaa. Tarkista yhteys ja yritä uudelleen.';

  @override
  String get makePublic => 'Julkaise';

  @override
  String get authUnexpectedErrorFirebase => 'Odottamaton virhe kirjautuessa, Firebase-virhe, yritä uudelleen.';

  @override
  String get unlimitedConversations => 'Rajoittamattomat keskustelut';

  @override
  String get stagingDisclaimer =>
      'Testiympäristö voi olla epävakaa, suorituskyky voi vaihdella ja tietoja voi kadota. Vain testausta varten.';

  @override
  String get captureMicrophonePermissionRequired => 'Mikrofonin käyttöoikeus vaaditaan';

  @override
  String shareStatsInsights(String count) {
    return '✨ Tarjonnut $count näkemystä';
  }

  @override
  String get feedbackReasonSummaryIrrelevant => 'Not relevant';

  @override
  String get userIdCopiedToClipboard => 'Käyttäjätunnus kopioitu';

  @override
  String get urlCopiedToClipboard => 'URL kopioitu leikepöydälle';

  @override
  String annualBillingSummary(int months, String price) {
    return '$months kuukautta / $price';
  }

  @override
  String chatAppsShowInAppOff(String app) {
    return 'Pois: näet ne vain sovelluksessa $app.';
  }

  @override
  String get replySentSuccessfully => 'Vastaus lähetetty onnistuneesti';

  @override
  String get deviceOnboardingTurnOffTitle => 'Sammuta';

  @override
  String get phoneStorageDesc =>
      'Kun Omi yhdistyy uudelleen, nauhoitukset siirretään automaattisesti puhelimeesi ennen palvelimelle lataamista.';

  @override
  String get callRecordingConsentDisclaimer => 'Puheluiden nauhoittaminen voi vaatia suostumuksen lainkaytoalueellasi';

  @override
  String get showDiscardedConversations => 'Näytä hylätyt keskustelut';

  @override
  String get calendarIntegration => 'Kalenterin Integraatio';

  @override
  String get whisperModelSizeBase => 'Perus';

  @override
  String get shareViaSms => 'Jaa tekstiviestillä';

  @override
  String get nameMustBeAtLeast3Characters => 'Nimen on oltava vähintään 3 merkkiä';

  @override
  String get chatDiscardRecording => 'Hylkää';

  @override
  String get chatAppsProPerkText => 'Lähetä Omille viestejä Telegramista ja iMessagesta';

  @override
  String get readyToSync => 'Valmis synkronointiin';

  @override
  String get noAppsInCategoryYet => 'Tässä luokassa ei ole vielä sovelluksia';

  @override
  String get firmwareUpdateAvailable => 'Laiteohjelmistopäivitys saatavilla';

  @override
  String get modelNumber => 'Mallinumero';

  @override
  String get sortBy => 'Lajittele';

  @override
  String get slideToUpdate => 'Liu\'uta päivittääksesi';

  @override
  String get effectBarelyCounts => 'Tuskin auttaa';

  @override
  String get onlyYouCanUse => 'Vain sinä voit käyttää tätä sovellusta';

  @override
  String get triggersWhenNewConversationCreated => 'Käynnistyy, kun uusi keskustelu luodaan.';

  @override
  String get paymentPlan => 'Maksusuunnitelma';

  @override
  String get whisperModelDesc => 'Valitse malli laitteella tapahtuvaan transkriptioon';

  @override
  String get askSuggestOwe => 'Mitä olen vielä velkaa muille?';

  @override
  String get starConversation => 'Merkitse tähdellä';

  @override
  String get hardwareSection => 'Laitteisto';

  @override
  String get transcribing => 'Litteroidaan…';

  @override
  String get chatAppsVoiceNotesSubtitle => 'Lähetä ääniviesti, niin Omi vastaa siihen.';

  @override
  String confidenceNextVoice(String name) {
    return 'Omi tarvitsee myös henkilön $name ääninäytteen. Nimeä hänet, kun Muista äänet on päällä.';
  }

  @override
  String get rating3PlusStars => '3+ tähteä';

  @override
  String get recordingActive => 'Tallennus aktiivinen';

  @override
  String starFilter(int count) {
    return '$count tähteä';
  }

  @override
  String get storageLocationLabel => 'Tallennussijainti';

  @override
  String get reviewNoChangesBody => 'Kun Omi siistii muistiinpanojasi, muutokset näkyvät täällä.';

  @override
  String get testPrompt => 'Testaa kehotetta';

  @override
  String get otaUpdateUnavailable => 'Tämä päivitys ei ole juuri nyt saatavilla. Yritä myöhemmin uudelleen.';

  @override
  String get downloading => 'Ladataan…';

  @override
  String get welcomeBackSimple => 'Tervetuloa takaisin';

  @override
  String get sttProviderSoniox => 'Soniox';

  @override
  String get clearAllSelection => 'Tyhjennä kaikki';

  @override
  String get confidenceReasonNeverConfirmed => 'Ei koskaan vahvistettu';

  @override
  String get writeScope => 'Kirjoitus';

  @override
  String get evidenceVoiceReady => 'Ääninäyte valmis';

  @override
  String get updateApp => 'Päivitä sovellus';

  @override
  String get weekdayThu => 'To';

  @override
  String chatUsageCostNoLimit(String used) {
    return 'Chat: \$$used käytetty tässä kuussa';
  }

  @override
  String get configCopied => 'Kokoonpano kopioitu leikepöydälle';

  @override
  String get startupFailedConfigMessage =>
      'Tässä Omin versiossa on määritysongelma. Kyse ei ole laitteestasi. Ota yhteyttä tukeen ja liitä alla olevat tiedot mukaan.';

  @override
  String get getOmiForMac => 'Hanki Omi Macille';

  @override
  String get appleHealthConnectedBadge => 'Yhdistetty';

  @override
  String get msgCameraNotAvailable => 'Kameran tallennus ei ole käytettävissä tällä alustalla';

  @override
  String get actionItemsDescription => 'Napauta muokataksesi • Pidä painettuna valitaksesi • Pyyhkäise toiminnoille';

  @override
  String get notificationsDesc =>
      'Jotta Omi voi lähettää sinulle keskustelujen yhteenvedot, tehtävämuistutukset ja vastaukset sovelluksistasi.';

  @override
  String audioUploadRetrying(String duration) {
    return 'Yritetään lähetystä uudelleen… $duration ääntä on tallessa puhelimessasi';
  }

  @override
  String get importStarted => 'Tuonti aloitettu! Saat ilmoituksen, kun se on valmis.';

  @override
  String get onDeviceModelDownloadFailed => 'Mallin lataus epäonnistui';

  @override
  String get noProjectsInWorkspace => 'Projekteja ei löytynyt tästä työtilasta';

  @override
  String get helpCenter => 'Ohjekeskus';

  @override
  String get trainingDataBullets =>
      '• Tietosi auttavat parantamaan AI-malleja\n• Jaetaan vain ei-arkaluonteisia tietoja';

  @override
  String get invalidPromotionCode => 'Virheellinen tarjouskoodi.';

  @override
  String get battery => 'Akku';

  @override
  String get clearSelection => 'Tyhjennä valinta';

  @override
  String get phoneSetupStep2Subtitle => 'Lyhyt koodi, jonka syotat puhelun aikana';

  @override
  String get googleSearch => 'Google Search';

  @override
  String get charging => 'Lataa';

  @override
  String deleteNamedPerson(String name) {
    return 'Poista $name';
  }

  @override
  String get chatAppsPartOfPro => 'Chat-sovellukset kuuluvat Pro-tilaukseen';

  @override
  String get invalidWebhookUrlError => 'Anna kelvollinen webhookin URL';

  @override
  String get starConversationsToFindQuickly => 'Merkitse keskustelut tähdellä löytääksesi ne nopeasti täältä';

  @override
  String get permissionCreateMemories => 'Luo muistoja';

  @override
  String get conversationIdCopied => 'Keskustelun tunnus kopioitu leikepöydälle';

  @override
  String get chatAppsMessagesApp => 'Viestit';

  @override
  String get understandingWords => 'Ymmärtäminen (sanaa)';

  @override
  String diagnosticsVerdictTroubleDetail(int count) {
    return 'Epäonnistuneet yhteydet viimeisten 24 tunnin aikana: $count';
  }

  @override
  String get editName => 'Muokkaa nimeä';

  @override
  String get askAboutThisConversation => 'Kysy tästä';

  @override
  String get useTemplateFrom => 'Käytä mallia kohteesta';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'Mikrofoniluvam tila: $status. Tarkista Järjestelmäasetukset.';
  }

  @override
  String get markAsCompleted => 'Merkitse valmiiksi';

  @override
  String get urlMustEndWithSlashError => 'URL:n on päätyttävä \"/\"';

  @override
  String get deviceOnboardingIntroTitle => 'Tutustu Omiisi';

  @override
  String nPending(int count) {
    return '$count odottaa';
  }

  @override
  String get howShouldOmiCallYou => 'Miten Omin pitäisi kutsua sinua?';

  @override
  String get preparingFormForYou => 'Valmistellaan lomaketta sinulle…';

  @override
  String get deleteChat => 'Poista keskustelu';

  @override
  String get msgPhotosPermissionDenied => 'Kuvien käyttöoikeus evätty. Salli pääsy kuviin valitaksesi kuvia';

  @override
  String get moreWaysToRecord => 'Lisää tallennustapoja';

  @override
  String get creatingPlan => 'Luodaan suunnitelmaa';

  @override
  String get configCopiedToClipboard => 'Kokoonpano kopioitu leikepöydälle';

  @override
  String get transcribeLaterDescription =>
      'Nauhoita nyt ja litteroi, kun haluat. Siihen asti ääni pysyy puhelimessasi.';

  @override
  String get couldNotSwitchToFreePlan => 'Ilmaiseen tilaukseen vaihtaminen epäonnistui. Yritä uudelleen.';

  @override
  String get wrappedTasksCompleted => 'tehtävää suoritettu';

  @override
  String get deviceOnboardingTranscriptionTitle => 'Puhu Omi-laitteeseesi';

  @override
  String get thankYouRequestUnderReview =>
      'Kiitos! Pyyntösi on tarkistettavana. Ilmoitamme sinulle hyväksynnän jälkeen.';

  @override
  String get unpairAndForgetDevice => 'Poista pariliitos ja unohda laite';

  @override
  String get sendWebUrl => 'Lähetä web-URL';

  @override
  String get noTasksForToday => 'Ei tehtäviä tänään.\nKysy Omilta lisää tehtäviä tai luo ne manuaalisesti.';

  @override
  String get conversationSummaryFailed => 'Yhteenveto epäonnistui';

  @override
  String get realtimeTranscript => 'Reaaliaikainen litterointi';

  @override
  String nConversationsCreated(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count keskustelua luotu',
      one: '1 keskustelu luotu',
    );
    return '$_temp0';
  }

  @override
  String get noEmailSet => 'Sähköpostia ei ole asetettu';

  @override
  String get setDueDateAndTime => 'Aseta määräpäivä ja aika';

  @override
  String get pairingDescFieldy => 'Pidä laitetta painettuna, kunnes valo syttyy, käynnistääksesi sen.';

  @override
  String get maximumSecurityE2ee => 'Maksimaalinen turvallisuus (E2EE)';

  @override
  String get instantSpeakerLabels => 'Välittömät puhujatunnisteet';

  @override
  String get resetRequestConfig => 'Palauta pyyntökokoonpano oletuksiin';

  @override
  String get webhookUrlNotSet => 'Webhook-URL-osoitetta ei ole asetettu';

  @override
  String get feedbackReasonRecordingOther => 'Something else';

  @override
  String get accountCutoverMigrationRollbackMessage =>
      'Tilisi on huollossa siirron peruutuksen jälkeen. Uudempaa dataa voi olla eristettynä.';

  @override
  String get cancelConsequenceQuality => '30% heikompi transkriptiolaatu (laitteen mallit)';

  @override
  String get pairingDescPlaudNote =>
      'Pidä sivupainiketta painettuna 2 sekuntia. Punainen LED vilkkuu, kun se on valmis pariliitokseen.';

  @override
  String get plansAndBilling => 'Suunnitelmat ja Laskutus';

  @override
  String get deviceOnboardingVoiceReplyTitle => 'Kuuntele Omin vastaukset';

  @override
  String get generatingIcon => 'Luodaan kuvaketta…';

  @override
  String get cleanUpBannerBody =>
      'Enimmäkseen väärin kuultuja nimiä. Käy ne läpi ja poista ne, jotka eivät ole oikeita.';

  @override
  String get speakerTagPromptSavedAsYou => 'Tallennettu sinuksi';

  @override
  String get connectOmiOmiGlass => 'Yhdistä Omi / OmiGlass';

  @override
  String get capabilityConversations => 'Keskustelut';

  @override
  String get notificationFrequencyDescription =>
      'Hallitse kuinka usein Omi lähettää sinulle proaktiivisia ilmoituksia ja muistutuksia.';

  @override
  String chatScopeAbout(String title) {
    return 'Aihe: $title';
  }

  @override
  String get importHistory => 'Tuontihistoria';

  @override
  String get getApiKey => 'Hanki API-avain';

  @override
  String get nothingInterestingRetry => 'Mitään mielenkiintoista ei löytynyt,\nhaluatko yrittää uudelleen?';

  @override
  String get whatWouldYouLikeToCreate => 'Mitä haluaisit luoda?';

  @override
  String get pricingFree => 'Ilmainen';

  @override
  String get speakerTagPromptHintIdentify => 'Vastauksesi auttaa Omia tunnistamaan tämän äänen seuraavalla kerralla.';

  @override
  String get noConversationsYet => 'Ei vielä keskusteluja';

  @override
  String get deviceNotMeetRequirements => 'Laitteesi ei täytä laitteella tapahtuvan transkription vaatimuksia.';

  @override
  String get pressKeys => 'Paina näppäimiä…';

  @override
  String get downgradeLimitDelayNotRealTime => '5–7 sekunnin viive (ei reaaliaikainen)';

  @override
  String get conversationLinkCopiedToClipboard => 'Keskustelun linkki kopioitu leikepöydälle';

  @override
  String get onboardingSetupStepMemory => 'Muistiasi otetaan käyttöön';

  @override
  String get chatAppsTelegramOtherDevice => 'Telegram toisella laitteella?';

  @override
  String get appNotFoundOrRemoved => 'Tämä sovellus ei ole enää saatavilla';

  @override
  String appsCount(String count) {
    return 'Sovellukset ($count)';
  }

  @override
  String get endToEndEncryption => 'Päästä päähän -salaus';

  @override
  String otaConnectFailed(String deviceName) {
    return 'Laitteeseen $deviceName ei saatu yhteyttä. Pidä se päällä ja lähellä ja yritä uudelleen.';
  }

  @override
  String get continueButton => 'Jatka';

  @override
  String get failedToPrepareConversationForSharing =>
      'Keskustelun valmistelu jakamista varten epäonnistui. Yritä uudelleen.';

  @override
  String get showAll => 'Näytä kaikki →';

  @override
  String get speakerLabelYou => 'Sina';

  @override
  String get wrappedActionItems => 'Tehtävät';

  @override
  String failedToInstallApp(String appName) {
    return '$appName asennus epäonnistui. Yritä uudelleen.';
  }

  @override
  String get searching => 'Haetaan';

  @override
  String get deviceNotCompatibleTitle => 'Laite ei yhteensopiva';

  @override
  String get summarize => 'Tiivistä';

  @override
  String get exportConversationsToJson => 'Vie keskustelut JSON-tiedostoon';

  @override
  String makeItemPrivateExplanation(String item) {
    return 'Jos teet $item nyt yksityiseksi, se lakkaa toimimasta kaikille ja on näkyvissä vain sinulle';
  }

  @override
  String get wrappedFailedToShare => 'Jakaminen epäonnistui. Yritä uudelleen.';

  @override
  String get cancelSubscriptionConfirmation => 'Sinulla on edelleen pääsy nykyisen laskutuskauden loppuun.';

  @override
  String get phoneHideKeypad => 'Piilota näppäimistö';

  @override
  String get vadGate => 'VAD Gate';

  @override
  String get nameUpdatedSuccessfully => 'Nimi päivitetty onnistuneesti!';

  @override
  String get photoLibrary => 'Kuvakirjasto';

  @override
  String get chatAppsHeroMessage =>
      'Kysy päivästäsi, tallenna muistoja ja hallitse tehtäviä Telegramista tai iMessagesta. Keskustelusi pysyvät käyttämässäsi sovelluksessa, ja Omi muistaa kaiken, mistä olette puhuneet, kaikkialla.';

  @override
  String get upgradeToAnnualPlan => 'Päivitä vuositilaukseen';

  @override
  String get completeAuthInBrowser => 'Viimeistele todennus selaimessasi. Kun olet valmis, palaa sovellukseen.';

  @override
  String errorLabel(String error) {
    return 'Virhe: $error';
  }

  @override
  String get durationThresholdDesc => 'Piilota tätä lyhyemmät keskustelut';

  @override
  String transcriptionsPendingCount(int count) {
    return 'Jonossa olevat transkriptiot $count';
  }

  @override
  String get transcribeLaterNote =>
      'Toimii puhelimen mikrofonin sekä Omi- ja Limitless-laitteiden kanssa. Ääni säilyy puhelimessasi, kunnes päätät ladata sen.';

  @override
  String get device => 'Laite';

  @override
  String get signUpSuccess => 'Rekisteröityminen onnistui!';

  @override
  String get onboardingPermissions => 'Käyttöoikeudet';

  @override
  String get modelTooLargeWarning =>
      'Tämä malli on suuri ja voi aiheuttaa sovelluksen kaatumisen tai erittäin hitaan toiminnan mobiililaitteissa.\n\nSuositellaan small tai base.';

  @override
  String get showDailyScoreOnHomepage => 'Näytä päivittäinen pistemäärä etusivulla';

  @override
  String confidenceSummaryUnverified(String name) {
    return 'Et ole vielä merkinnyt tai vahvistanut henkilöä $name, joten Omi ei ole varma, tunteeko se hänen äänensä.';
  }

  @override
  String get endConversation => 'Lopeta keskustelu';

  @override
  String get unpinAsBaseline => 'Irrota perustasta';

  @override
  String audioSavedLocally(String duration) {
    return '$duration ääntä tallennettu paikallisesti';
  }

  @override
  String get editMemory => '✏️ Muokkaa muistia';

  @override
  String get speakerTagPromptThanks => 'Kiitos! Omi oppii tunnistamaan äänet paremmin.';

  @override
  String get actionItemDescriptionEmpty => 'Tehtävän kuvaus ei voi olla tyhjä.';

  @override
  String get maybeLater => 'Ehkä myöhemmin';

  @override
  String get daySummary => 'Päivän yhteenveto';

  @override
  String get confirmReportMessage => 'Ilmoitetaanko tästä viestistä?';

  @override
  String get deleteAllLimitlessConversations => 'Poista kaikki Limitless-keskustelut?';

  @override
  String get selectAllTasksMenu => 'Valitse kaikki';

  @override
  String get syncStatusRetrying => 'Käsittely epäonnistui — yritetään uudelleen';

  @override
  String get exportButton => 'Vie';

  @override
  String get wrappedYouTalkedAboutBadge => 'Puhuit aiheesta';

  @override
  String get firmwareWarningTitle => 'Tärkeää: Lue ennen päivitystä';

  @override
  String get permissionTypeCreate => 'Luo';

  @override
  String get viewUsage => 'Näytä käyttö';

  @override
  String get deviceOnboardingIntroDuration => 'Noin 1 minuutti';

  @override
  String get import => 'Tuo';

  @override
  String get conversationsExportStarted => 'Keskustelujen vienti aloitettu. Tämä voi kestää muutaman sekunnin, odota.';

  @override
  String get speechToTextProvider => 'Puheesta tekstiksi -palveluntarjoaja';

  @override
  String get languageTranslation => 'Yli 100 kielen käännös';

  @override
  String get primaryLanguage => 'Ensisijainen kieli';

  @override
  String durationSeconds(String seconds) {
    return 'Kesto: $seconds sekuntia';
  }

  @override
  String get autoSyncDescription => 'Synkronoi offline-tallenteet automaattisesti, kun laitteesi yhdistetään';

  @override
  String get debugLogs => 'Virheenkorjauslokit';

  @override
  String get authorizationRevoked => 'Valtuutus peruttu.';

  @override
  String get noTranscriptAvailable => 'Litterointia ei ole saatavilla';

  @override
  String get available => 'Saatavilla';

  @override
  String get wrappedObsessionsLabelUpper => 'PAKKOMIELTET';

  @override
  String get professionStudent => 'Opiskelija';

  @override
  String get chatAppsTryRemind => 'Muistuta minua soittamaan äidille sunnuntaina';

  @override
  String get failedToStartVerification => 'Vahvistuksen aloitus epaonnistui';

  @override
  String get failedToCreateFolder => 'Kansion luominen epäonnistui';

  @override
  String timeMinSingular(int count) {
    return '$count min';
  }

  @override
  String get insights => 'Oivallukset';

  @override
  String get privacyInformation => 'Tietosuojatiedot';

  @override
  String get finishedConversation => 'Keskustelu päättynyt?';

  @override
  String get syncGoogleAccount => 'Synkronoi Google-tilisi kanssa';

  @override
  String get pairingTitleNeoOne => 'Aseta Neo One pariliitostilaan';

  @override
  String get translatedByOmi => 'kääntänyt Omi';

  @override
  String get githubRepositoryUrl => 'GitHub-repositorion URL';

  @override
  String get readOnlyScope => 'Vain luku';

  @override
  String get chatAppsChannelsTitle => 'Chat-sovellukset';

  @override
  String get chatAppsDoesAnswer => 'Vastaa kysymyksiin keskusteluistasi ja muistoistasi';

  @override
  String get wrappedFailedToStartGeneration => 'Luonnin aloitus epäonnistui. Yritä uudelleen.';

  @override
  String get storageLocationSdCard => 'SD-kortti';

  @override
  String get askSuggestDecide => 'Mitä päätin tänään?';

  @override
  String get close => 'Sulje';

  @override
  String get paymentMethodPayPal => 'PayPal';

  @override
  String categoryAppCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count sovellusta',
      one: '1 sovellus',
    );
    return '$_temp0';
  }

  @override
  String get speakerTagPromptRecentPeople => 'Ihmiset, joiden kanssa puhuit äskettäin';

  @override
  String get actionCreateMemories => 'Luo muistoja';

  @override
  String get swipeTasksToIndent => 'Pyyhkäise tehtäviä sisennykseen, vedä kategorioiden välillä';

  @override
  String get createAccountTitle => 'Luo tili';

  @override
  String get modelRequired => 'Malli vaaditaan';

  @override
  String get saveMemory => 'Tallenna muisto';

  @override
  String get successfullyConnectedClickUp => 'Yhdistetty onnistuneesti ClickUpiin!';

  @override
  String get notYetSynced => 'Ei vielä synkronoitu puhelimeesi';

  @override
  String get pendantUpToDate => 'Riipus on ajan tasalla';

  @override
  String get categoryProductivityTools => 'Tuottavuustyökalut';

  @override
  String get refresh => 'Päivitä';

  @override
  String get cancelSyncMessage => 'Jo ladatut tiedot tallennetaan. Voit jatkaa myöhemmin.';

  @override
  String get selectImageFileTitle => 'Valitse kuvatiedosto';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'Virhe tiedostonvalitsimen avaamisessa: $message';
  }

  @override
  String get failedToGenerateConversationLink => 'Keskustelulinkin luominen epäonnistui';

  @override
  String get voiceFailedToTranscribe => 'Äänen litterointi epäonnistui';

  @override
  String get viewAll => 'Näytä kaikki';

  @override
  String get yourNewKey => 'Uusi avaimesi:';

  @override
  String get conversationMap => 'Keskustelukartta';

  @override
  String get contactSupportAction => 'Ota yhteyttä tukeen';

  @override
  String get weekdaySun => 'Su';

  @override
  String get summaryNotFound => 'Yhteenvetoa ei löytynyt';

  @override
  String get shortConversationThreshold => 'Lyhyen keskustelun kynnysarvo';

  @override
  String get dailyRecapsDescription => 'Päivittäiset yhteenvetosi näkyvät täällä, kun ne on luotu';

  @override
  String get phoneCallsWithOmi => 'Puhelut Omin kanssa';

  @override
  String get addAppSelectPaymentPlan => 'Valitse maksusuunnitelma ja syötä hinta sovelluksellesi';

  @override
  String get deleteAccountFinal =>
      'Tämä toiminto on peruuttamaton ja poistaa tilisi ja kaikki siihen liittyvät tiedot pysyvästi. Haluatko varmasti jatkaa?';

  @override
  String get gettingAudioFiles => 'Haetaan äänitiedostoja…';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String get port => 'Portti';

  @override
  String personPinnedToast(String name) {
    return '$name kiinnitetty';
  }

  @override
  String get wrappedConversations => 'keskustelua';

  @override
  String get availableOnMacMobileWeb => 'Saatavilla Macilla, mobiilissa ja verkossa';

  @override
  String get monthAug => 'Elo';

  @override
  String get failedToGenerateSummary =>
      'Yhteenvedon luominen epäonnistui. Varmista, että sinulla on keskusteluja kyseiseltä päivältä.';

  @override
  String planEndedOn(String date) {
    return 'Tilauksesi päättyi $date.\nTilaa uudelleen nyt - sinulta veloitetaan välittömästi uudesta laskutusjaksosta.';
  }

  @override
  String get createAnApp => 'Luo sovellus';

  @override
  String get cancelling => 'Peruutetaan…';

  @override
  String get wrappedTopDaysHeader => 'Parhaat päivät';

  @override
  String get keepEditing => 'Jatka muokkausta';

  @override
  String get ignoredVoicesEmpty => 'Ei ohitettuja ääniä';

  @override
  String get cannotBeUndone => 'Tätä ei voi perua.';

  @override
  String get usersPayToUse => 'Käyttäjät maksavat sovelluksesi käytöstä';

  @override
  String get maxFilesUploadError => 'Voit ladata vain 4 tiedostoa kerralla';

  @override
  String get yourDeviceIsUpToDate => 'Laitteesi on ajan tasalla';

  @override
  String get unableToFetchApps => 'Sovellusten haku epäonnistui :(\n\nTarkista internet-yhteytesi ja yritä uudelleen.';

  @override
  String get entityCorrectionFailed => 'Korjausta ei voitu lähettää. Yritä uudelleen.';

  @override
  String get alreadyAuthorized => 'Jo valtuutettu';

  @override
  String get speedAccuracyLower => 'Nopeus ja tarkkuus voivat olla alhaisempia kuin pilvimalleilla.';

  @override
  String siriShortcutsSearchHint(String searchPhrase) {
    return ' Voit myös sanoa “$searchPhrase for what I did today”.';
  }

  @override
  String get unlimitedPlan => 'Rajoittamaton paketti';

  @override
  String get contactSupport => 'Ota yhteyttä tukeen?';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Enintään $count tavoitetta sallittu';
  }

  @override
  String get deviceStorageNearlyFull => 'Laite on lähes täynnä — synkronoi vapauttaaksesi tilaa.';

  @override
  String get setDueDate => 'Aseta määräpäivä';

  @override
  String privateAppsCount(String count) {
    return 'Yksityiset sovellukset ($count)';
  }

  @override
  String get selectPeople => 'Valitse ihmisiä';

  @override
  String get capabilityChat => 'Keskustelu';

  @override
  String chatAppsChannelChats(String app) {
    return '$app-keskustelut';
  }

  @override
  String get transcribeLaterTitle => 'Litteroi myöhemmin';

  @override
  String get failedToConnectAsana => 'Yhteyden muodostaminen Asanaan epäonnistui';

  @override
  String get youAreOnUnlimitedPlan => 'Sinulla on Rajoittamaton tilaus.';

  @override
  String get chatAppsIncludedWithPro => 'SISÄLTYY OMI PRO -TILAUKSEEN';

  @override
  String get failedToCreateKeyTryAgain => 'Avaimen luominen epäonnistui. Yritä uudelleen.';

  @override
  String get backgroundModeTitle => 'Taustatila';

  @override
  String get discardChangesMessage => 'Tallentamattomat muutokset menetetään.';

  @override
  String get captureSourcePendant => 'Riipus';

  @override
  String get exportTasksWithOneTap => 'Vie tehtävät yhdellä napautuksella!';

  @override
  String get sundayAbbr => 'Su';

  @override
  String get pleaseEnterAppPrompt => 'Anna sovelluksellesi kehote';

  @override
  String deviceStoragePercentFull(int percent) {
    return '$percent % täynnä';
  }

  @override
  String get developerSettings => 'Kehittäjäasetukset';

  @override
  String get selectYouFromList => 'Merkitäksesi itsesi, valitse \"Sinä\" luettelosta.';

  @override
  String get deleteNow => 'Poista nyt';

  @override
  String get installUpdate => 'Asenna päivitys';

  @override
  String get unpairDevice => 'Poista laitteen pariliitos';

  @override
  String get assistantVoice => 'Avustajan ääni';

  @override
  String get installingApp => 'Asennetaan sovellusta…';

  @override
  String get wrappedFunnyMomentTitle => 'Hauska hetki';

  @override
  String onboardingFailedCheckNotification(String error) {
    return 'Ilmoitusluvan tarkistus epäonnistui: $error';
  }

  @override
  String get dreamReportRunNow => 'Suorita nyt';

  @override
  String get notSet => 'Ei asetettu';

  @override
  String get startVoiceRecording => 'Aloita ääninauhoitus';

  @override
  String get userInformation => 'Käyttäjätiedot';

  @override
  String get wrappedStruggleLabel => 'HAASTE';

  @override
  String get filterInteresting => 'Oivallukset';

  @override
  String captureRecordingsCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count tallennetta',
      one: '1 tallenne',
    );
    return '$_temp0';
  }

  @override
  String get addOrChangeYourPaymentMethod => 'Lisää tai vaihda maksutapa';

  @override
  String get unableToLoadApps => 'Sovellusten lataus epäonnistui';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'Uusi laiteohjelmistopäivitys ($version) on saatavilla Omi-laitteellesi. Haluatko päivittää nyt?';
  }

  @override
  String get cancelReasonTooExpensive => 'Liian kallis';

  @override
  String get firmwareUsbWarning => 'USB-yhteys päivitysten aikana voi vahingoittaa laitettasi.';

  @override
  String authAccessMessage(String appName) {
    return 'Sinun on valtuutettava Omi käyttämään $appName-tietojasi. Tämä avaa selaimesi todennusta varten.';
  }

  @override
  String get conversationEndsManually => 'Keskustelu päättyy vain manuaalisesti.';

  @override
  String get partialRecording => 'Osittainen tallenne';

  @override
  String get dreamReportFeedback => 'Ilmoitettu Omi-tiimille';

  @override
  String get shareAudio => 'Jaa ääni';

  @override
  String get importDataFromOtherSources => 'Tuo tietoja muista lähteistä';

  @override
  String get premiumMinutesUsed => 'Premium-minuutit käytetty.';

  @override
  String get phoneCallsUpgradeButton => 'Päivitä Rajattomaan';

  @override
  String get omiUnlimited => 'Omi Unlimited';

  @override
  String get unknownDevice => 'Tuntematon';

  @override
  String get failedToStartImport => 'Tuonnin aloitus epäonnistui. Yritä uudelleen.';

  @override
  String get searchActionItems => 'Hae tehtäviä';

  @override
  String get whisperModel => 'Whisper-malli';

  @override
  String get searchContacts => 'Hae yhteystietoja';

  @override
  String get selectAllSkipsPinned =>
      'Valitse kaikki ohittaa kiinnitetyt ihmiset. Poista heidät yksitellen heidän sivultaan.';

  @override
  String get speechProfileIntro => 'Omin täytyy oppia tavoitteesi ja äänesi. Voit muokata sitä myöhemmin.';

  @override
  String get realtimeListening => 'Reaaliaikainen kuuntelu';

  @override
  String get appNotAvailable => 'Hups! Etsimääsi sovellusta ei näytä olevan saatavilla.';

  @override
  String get enterYourName => 'Syötä nimesi';

  @override
  String get permissionTypeTrigger => 'Laukaisin';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'Tietograafisi rakennetaan automaattisesti, kun luot uusia muistoja.';

  @override
  String get chatAppsLink => 'Linkki';

  @override
  String get minutes => 'minuuttia';

  @override
  String get actions => 'Toiminnot';

  @override
  String get connectRayBanMeta => 'Yhdistä Ray-Ban Meta';

  @override
  String get monthSep => 'Syys';

  @override
  String get selectContactsToShareSummary => 'Valitse yhteystiedot keskustelun yhteenvedon jakamiseksi';

  @override
  String get paymentNoneSelected => 'Ei valittu';

  @override
  String get pinAction => 'Kiinnitä';

  @override
  String get monthOct => 'Loka';

  @override
  String get startRecording => 'Aloita tallennus';

  @override
  String get somethingWentWrong => 'Jokin meni pieleen! Yritä myöhemmin uudelleen.';

  @override
  String largeTimeGapsDetected(String gaps) {
    return 'Havaittu suuria aikavälejä ($gaps)';
  }

  @override
  String get phoneEnterNumber => 'Syota numero';

  @override
  String get cancelConsequenceNoAccess => 'Ei enää rajoittamatonta pääsyä laskutusjakson lopussa.';

  @override
  String get appleHealthDeniedTitle => 'Apple Health -käyttöoikeus evätty';

  @override
  String deleteItemTitle(String item) {
    return 'Poista $item';
  }

  @override
  String get invalidIntegrationUrl => 'Virheellinen integraatio-URL';

  @override
  String get welcomeActionItemsTitle => 'Valmis tehtäville';

  @override
  String get updateAppConfirmation => 'Muutokset näkyvät tiimimme tarkistuksen jälkeen.';

  @override
  String get corruptedStatus => 'Vioittunut';

  @override
  String get cantRateWithoutInternet => 'Sovellusta ei voi arvioida ilman internetyhteyttä.';

  @override
  String get dontShowAgain => 'Älä näytä uudelleen';

  @override
  String get hardwareRevision => 'Laitteistoversio';

  @override
  String get trySelectingDifferentDate => 'Yritä valita eri päivämäärä';

  @override
  String get learnings => 'Opit';

  @override
  String get failedToConnectTodoist => 'Yhteyden muodostaminen Todoistiin epäonnistui';

  @override
  String get accessDataProgrammatically => 'Käytä tietojasi ohjelmallisesti';

  @override
  String processingProgress(int current, int total) {
    return 'Käsitellään $current/$total';
  }

  @override
  String get apiEnvSavedRestartRequired =>
      'Tallennettu. Sulje ja avaa sovellus uudelleen, jotta muutokset tulevat voimaan.';

  @override
  String get syncCardWaitingInternet => 'Odottaa verkkoyhteyttä';

  @override
  String get accountCutoverOpenStore => 'Avaa kauppa';

  @override
  String get processedConversations => 'Käsitellyt keskustelut';

  @override
  String get holdOnPreparingForm => 'Odota hetki, valmistelemme lomaketta sinulle';

  @override
  String get waitingForDevice => 'Odotetaan laitetta…';

  @override
  String get learnMore => 'Lue lisää…';

  @override
  String get aiGenErrorWhileCreatingApp => 'Sovelluksen luomisessa tapahtui virhe';

  @override
  String get deleteAllFilesWarning =>
      'Tämä poistaa synkronoidut ja odottavat tallenteet. Odottavia tallenteita EI ole synkronoitu ja ne menetetään pysyvästi.';

  @override
  String get usageWordsHeard => 'Words heard';

  @override
  String get importDataDescription => 'Tuo tietoja muista lähteistä';

  @override
  String get raybanMetaImageCaptureUnavailable => 'Ei käytettävissä vain ääni -tilassa';

  @override
  String get appRejectedMessage => 'Sovelluksesi on hylätty. Päivitä tiedot ja lähetä uudelleen tarkistettavaksi.';

  @override
  String get capturePendantDisconnectedShort => 'Omi yhdistää itsestään uudelleen';

  @override
  String get improveSpeechProfileDesc =>
      'Käytämme nauhoituksia henkilökohtaisen puheprofiilisi kouluttamiseen ja parantamiseen.';

  @override
  String get voiceResponseModeTitle => 'Milloin vastaukset luetaan';

  @override
  String get failedToDeleteItem => 'Tehtävän poisto epäonnistui';

  @override
  String get firmware => 'Laiteohjelmisto';

  @override
  String failedToAddToService(String serviceName) {
    return 'Lisääminen kohteeseen $serviceName epäonnistui';
  }

  @override
  String get askOmiAnything => 'Kysy Omilta mitä tahansa elämästäsi';

  @override
  String get integrationsFooter => 'Yhdistä sovelluksesi nähdäksesi tiedot ja mittarit chatissa.';

  @override
  String get loading => 'Ladataan…';

  @override
  String get showLess => 'näytä vähemmän ↑';

  @override
  String get chatAppsNeverMessagesOthers => 'Ei koskaan viestitä muille puolestasi';

  @override
  String get scopeUserName => 'Käyttäjänimi';

  @override
  String get mute => 'Vaimenna';

  @override
  String get serverProcessesAudio => 'Palvelin käsittelee äänitiedostot ja luo muistoja';

  @override
  String mergeConversationsSuccessBody(int count) {
    return '$count keskustelua yhdistettiin onnistuneesti';
  }

  @override
  String get pairingSuccessful => 'PARILIITOS ONNISTUI';

  @override
  String get websocketUrl => 'WebSocket-URL';

  @override
  String get wrappedFriend => 'Ystävä';

  @override
  String get frequencyHigh => 'Korkea';

  @override
  String get processingFailed => 'Käsittely epäonnistui';

  @override
  String get dataLowercase => 'tiedot';

  @override
  String deviceOfflineWakeHint(String deviceName) {
    return '$deviceName on offline-tilassa. Herätä se painamalla sen painiketta ja yritä uudelleen.';
  }

  @override
  String get updatedConversations => 'Päivitetyt keskustelut';

  @override
  String get phoneGetStarted => 'Aloita';

  @override
  String get recordingDetails => 'Nauhoituksen tiedot';

  @override
  String get createApiKey => 'Luo API-avain';

  @override
  String get anyoneWithLinkCanView => 'Kuka tahansa linkin haltija voi katsella';

  @override
  String get noPendingTasks => 'Ei avoimia tehtäviä';

  @override
  String get featureComingSoon => 'Tämä ominaisuus on tulossa pian!';

  @override
  String get bluetoothMethodDescription =>
      'Käyttää tavallista Bluetooth Low Energy -yhteyttä. Hitaampi, mutta ei vaikuta WiFi-yhteyteen.';

  @override
  String get chatAppsNotConnectedTitle => 'Ei yhdistetty';

  @override
  String get wrappedMostIntenseDay => 'Intensiivisin';

  @override
  String get yesterday => 'Eilen';

  @override
  String get requestConfiguration => 'Pyyntökokoonpano';

  @override
  String get timeAM => 'AP';

  @override
  String autoRemoveSyncedCopiesDescription(int days) {
    return 'Poistaa paikalliset kopiot $days päivää synkronoinnin jälkeen. Pilvikopiot säilytetään.';
  }

  @override
  String get chatAppsTelegramPrivacyNote =>
      'Omin kanssa käymäsi keskustelut tallentaa myös Telegram. Omi vastaa vain sinulle, ei koskaan muille, ja voit katkaista yhteyden milloin tahansa.';

  @override
  String speakerWithId(String speakerId) {
    return 'Puhuja $speakerId';
  }

  @override
  String get reviewNoDate => 'Ei mitään';

  @override
  String get transcript => 'Litterointi';

  @override
  String get deviceDiagnosticsUploadFailed => 'Could not send diagnostics to support. Please try again.';

  @override
  String get noFoldersAvailable => 'Ei kansioita saatavilla';

  @override
  String get addAppSelectCategory => 'Valitse kategoria sovelluksellesi';

  @override
  String get conversations => 'Keskustelut';

  @override
  String get upgradeToUnlimited => 'Päivitä rajattomaksi';

  @override
  String get deleteFlowConfirmTitle => 'Poistetaanko tilisi?';

  @override
  String get accountCutoverMigrationInProgressMessage =>
      'Tiliäsi siirretään. Tuoteominaisuudet on keskeytetty, kunnes siirto valmistuu.';

  @override
  String get permissionAllowed => 'Sallittu';

  @override
  String get pressDoneToSave => 'Paina valmis tallentaaksesi';

  @override
  String get listening => 'Kuunteleminen';

  @override
  String get audioReady => 'Ääni valmis';

  @override
  String get freeForEveryone => 'Ilmainen kaikille';

  @override
  String get buildingKnowledgeGraphFromMemories => 'Rakennetaan tietograafia muistoista…';

  @override
  String get onDeviceTranscription => 'Laitteella tapahtuva transkriptio';

  @override
  String errorWithMessage(String error) {
    return 'Virhe: $error';
  }

  @override
  String get chatAppsProblemOffline => 'Olet offline-tilassa. Tarkista yhteytesi ja yritä uudelleen.';

  @override
  String get callAlreadyInProgress => 'Puhelu on jo kaynnissa';

  @override
  String get reviewQuestionSpelling => 'Miten tämä kirjoitetaan?';

  @override
  String get firmwareStableConnection => 'Vakaa yhteys';

  @override
  String get categoryOther => 'Muut';

  @override
  String get perMonthLabel => '/ kuukausi';

  @override
  String get onboardingYoureAllSet => 'Olet valmis';

  @override
  String get resumeRecording => 'Jatka nauhoitusta';

  @override
  String get feedbackSubtitleAudioQuality => 'Haluaisimme ymmärtää, mikä meni pieleen.';

  @override
  String get speakerTagPromptPlayClip => 'Toista leike';

  @override
  String get anonymityAndPrivacy => 'Nimettömyys ja yksityisyys';

  @override
  String get noMemoriesToDelete => 'Ei poistettavia muistoja';

  @override
  String get syncStepProcess => 'Litterointi';

  @override
  String get callStateRinging => 'Soi…';

  @override
  String get setupOnDevice => 'Määritä laitteella';

  @override
  String get creatorPayouts => 'Tekijöiden maksut';

  @override
  String get olderDeviceDetected => 'Vanhempi laite havaittu';

  @override
  String get deletePhoneNumberWarning => 'Sinun taytyy vahvistaa uudelleen soittaaksesi';

  @override
  String get appVisibilityChangedSuccessfully =>
      'Sovelluksen näkyvyys muutettu onnistuneesti. Muutos voi näkyä muutaman minuutin kuluttua.';

  @override
  String get failedToCreateActionItem => 'Tehtävän luonti epäonnistui';

  @override
  String get msgSelectFilesGenericError => 'Virhe tiedostojen valinnassa. Yritä uudelleen.';

  @override
  String get pendantRecordingSyncBlocked =>
      'Pendant tallentaa edelleen, joten tallennettua ääntä ei voi siirtää. Pysäytä tallennus painamalla Pendantin painiketta ja synkronoi sitten uudelleen.';

  @override
  String get failedToStartMerge => 'Yhdistämisen aloitus epäonnistui';

  @override
  String get shortcutChangeInstruction => 'Napsauta pikanäppäintä muuttaaksesi sitä. Peruuta painamalla Escape.';

  @override
  String get notificationsAndDisplay => 'Ilmoitukset ja näyttö';

  @override
  String get getPaidThroughStripe => 'Saa maksuja sovellustesi myynnistä Stripen kautta';

  @override
  String get weekdayWed => 'Ke';

  @override
  String get send => 'Lähetä';

  @override
  String get nativeEngineNoDownload => 'Käytetään laitteesi natiivia puhe-moottoria. Mallin latausta ei tarvita.';

  @override
  String get wrappedActions => 'toimintoa';

  @override
  String get conversationTimeoutConfig => 'Kuinka kauan Omi odottaa hiljaisuudessa ennen keskustelun päättämistä';

  @override
  String get mic => 'Mikrofoni';

  @override
  String deviceOnboardingVoiceReplyStatusAlwaysHeadphones(String device) {
    return 'Toistaa numeron $device kautta.';
  }

  @override
  String failedToSendReply(String error) {
    return 'Vastauksen lähettäminen epäonnistui: $error';
  }

  @override
  String get whisperModelSizeTiny => 'Pikkuruinen';

  @override
  String get speakerTagPromptNotMeAction => 'En ole minä';

  @override
  String get setupInstructions => 'Asetusohjeet';

  @override
  String get noLanguagesFound => 'Kieliä ei löytynyt';

  @override
  String get experimental => 'Kokeellinen';

  @override
  String get continueRecording => 'Jatka nauhoitusta';

  @override
  String get selectDefaultRepoDesc =>
      'Valitse oletusrepositorio ongelmien luomiseen. Voit silti määrittää eri repositorion ongelmia luodessa.';

  @override
  String sharedTasksTitle(String name, int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count tehtävää',
      one: '1 tehtävän',
    );
    return '$name jakoi $_temp0';
  }

  @override
  String get permissionsRequiredDesc =>
      'Tämä sovellus tarvitsee Bluetooth- ja sijaintioikeudet toimiakseen oikein. Ota ne käyttöön asetuksissa.';

  @override
  String diagnosticsVerdictReconnectsDetail(String duration) {
    return 'Lyhyitä katkoksia, palaa joka kerta noin $duration kuluttua';
  }

  @override
  String get transferring => 'Siirretään…';

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '$used/$limit sanaa käytetty tässä kuussa';
  }

  @override
  String get noChatAppsEnabled => 'Chat-sovelluksia ei ole käytössä.\nNapauta \"Ota käyttöön\" lisätäksesi.';

  @override
  String get tipKeepPhoneNearby => 'Pidä puhelin lähellä nopeampaa synkronointia varten';

  @override
  String get authFailedToSignInWithGoogle => 'Kirjautuminen Googlella epäonnistui, yritä uudelleen.';

  @override
  String get frequencyDescLow => 'Vain tärkeät asiat, noin 3–5 päivässä';

  @override
  String get availableTemplates => 'Saatavilla olevat mallit';

  @override
  String get captureEveryMoment => 'Omi nauhoittaa keskustelusi ja kirjoittaa\nsinulle yhteenvedon ja tehtävät.';

  @override
  String get migrationErrorOccurred => 'Siirron aikana tapahtui virhe. Yritä uudelleen.';

  @override
  String get wrappedCompletedLabel => 'Suoritettu';

  @override
  String speakerTagPromptLabeledToast(String name) {
    return 'Nimetty: $name';
  }

  @override
  String get docs => 'Dokumentaatio';

  @override
  String get dateTimeLabel => 'Päivämäärä ja aika';

  @override
  String get editFolder => 'Muokkaa kansiota';

  @override
  String get apps => 'Sovellukset';

  @override
  String segmentsSingular(String count) {
    return '$count segmentti';
  }

  @override
  String get deviceSettings => 'Laitteen asetukset';

  @override
  String get offline => 'Offline-tilassa';

  @override
  String get createActionItemTooltip => 'Luo uusi tehtävä';

  @override
  String get forgetDevice => 'Unohda laite';

  @override
  String get reviewEntryTitle => 'Kysymyksiä sinulle';

  @override
  String get enterEmailError => 'Anna sähköpostiosoitteesi';

  @override
  String get appDisabledOwnerHint =>
      'Korjaa ensin päätepiste — käyttöönotto tarkistaa jokaisen määritetyn URL-osoitteen uudelleen.';

  @override
  String get chatAppsIMessageSubtitle => 'Lähetä Omille viesti puhelinnumerostasi';

  @override
  String get tasksExportedOneApp => 'Tehtäviä voidaan viedä yhteen sovellukseen kerrallaan';

  @override
  String transcriptSpeakerCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count puhujaa',
      one: '1 puhuja',
    );
    return '$_temp0';
  }

  @override
  String get saveGoal => 'Tallenna';

  @override
  String get noBatteryDataYet => 'Ei vielä akkutietoja';

  @override
  String chatUsedOfLimitMessages(String used, String limit) {
    return '$used / $limit viestiä käytetty tässä kuussa';
  }

  @override
  String get backgroundActivityDesc =>
      'Jotta Omi jatkaa tallennusta, kun näyttö on pois päältä tai vaihdat sovellusta.';

  @override
  String get addAppUpdateFailed => 'Päivitys epäonnistui. Yritä myöhemmin uudelleen';

  @override
  String get noMatchingPeople => 'Ei vastaavia henkilöitä';

  @override
  String get unlinkCalendarEvent => 'Poista kalenteritapahtuman linkitys';

  @override
  String get regenerateRecap => 'Luo yhteenveto uudelleen';

  @override
  String get deleteSynced => 'Poista synkronoidut';

  @override
  String get speakerTagPromptNameHint => 'Nimi';

  @override
  String get freePlan => 'Ilmainen tilaus';

  @override
  String get installs => 'ASENNUKSET';

  @override
  String get publicLabel => 'Julkinen';

  @override
  String get deletingMessages => 'Poistetaan viestejäsi Omin muistista…';

  @override
  String get pendingFilesDeleted => 'Odottavat tallenteet poistettu';

  @override
  String get checkUsage => 'Tarkista käyttö';

  @override
  String get addWordsDesc => 'Nimiä, termejä tai harvinaisia sanoja';

  @override
  String get entityCorrectionSaved => 'Kiitos. Omi korjaa sen.';

  @override
  String get categoryEducation => 'Koulutus';

  @override
  String get planAndUsage => 'Paketti ja käyttö';

  @override
  String get deleteMemory => 'Poista muisti';

  @override
  String get dataProtectionLevel => 'Tietosuojataso';

  @override
  String timeDaySingular(int count) {
    return '$count päivä';
  }

  @override
  String get keyCreated => 'Avain luotu';

  @override
  String get date => 'Päivämäärä';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return 'Migrating $itemType… $percentage%';
  }

  @override
  String get enableLocalStorage => 'Ota paikallinen tallennustila käyttöön';

  @override
  String get omiSays => 'Omi says';

  @override
  String get appDetails => 'Sovelluksen tiedot';

  @override
  String get loadingYourRecording => 'Ladataan tallennetta…';

  @override
  String get deleteAllLimitlessWarning => 'Kaikki Limitlessistä tuodut keskustelut poistetaan. Tätä ei voi perua.';

  @override
  String get combiningAudioFiles => 'Yhdistetään äänitiedostoja…';

  @override
  String get suggestFollowUpQuestion => 'Ehdota jatkokysymystä';

  @override
  String chatStarterPrompt(String kind) {
    String _temp0 = intl.Intl.selectLogic(
      kind,
      {
        'capabilities': 'Mitä voit tehdä hyväkseni?',
        'goal': 'Auta minua asettamaan tavoite',
        'activity': 'Tee yhteenveto viimeaikaisista toimistani',
        'improve': 'Miten voin kehittyä?',
        'other': '',
      },
    );
    return '$_temp0';
  }

  @override
  String get speakerTagPromptIgnoredNote => 'Omi ei kysy tästä äänestä enää';

  @override
  String get recordWithPhoneInstead => 'Tallenna sen sijaan puhelimella';

  @override
  String get triggerEvent => 'Laukaisutapahtuma';

  @override
  String get waitingForTranscriptOrPhotos => 'Odotetaan litterointia tai kuvia…';

  @override
  String get omiApiKeys => 'Omi API-avaimet';

  @override
  String addNamedPersonAction(String name) {
    return 'Lisää “$name”';
  }

  @override
  String get enableDetailedDiagnosticMessages =>
      'Ota käyttöön yksityiskohtaiset diagnostiikkaviestit litterointipalvelusta';

  @override
  String get nameCannotBeEmpty => 'Nimi ei voi olla tyhjä';

  @override
  String get noTasksYet => 'Ei tehtäviä vielä';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'Kokeile hakuehtojen tai suodattimien muuttamista';

  @override
  String daySummaryForDate(String date) {
    return 'Päivän yhteenveto · $date';
  }

  @override
  String get statusTimedOut => 'Aikakatkaisu';

  @override
  String chatUsageDescription(String used, String limitDisplay, String plan) {
    return 'Olet käyttänyt $used / $limitDisplay $plan-suunnitelmassa.';
  }

  @override
  String get paypalMeLink => 'PayPal.me-linkki';

  @override
  String get allMemoriesPrivateResult => 'Kaikki muistot ovat nyt yksityisiä';

  @override
  String get scanAgain => 'Hae uudelleen';

  @override
  String get doItAgain => 'Tee uudelleen';

  @override
  String get reviewTitle => 'Tarkistus';

  @override
  String get photos => 'Kuvat';

  @override
  String get phoneNoVerifiedNumbersMessage => 'Vahvista numerosi soittaaksesi Omin kautta.';

  @override
  String get save => 'Tallenna';

  @override
  String get deleteAccount => 'Poista Tili';

  @override
  String get managePaymentMethod => 'Hallitse maksutapaa';

  @override
  String get selectThumbnailImageTitle => 'Valitse pikkukuva';

  @override
  String get pairingTitleOmi => 'Käynnistä Omi';

  @override
  String get whatsYourPrimaryLanguage => 'Mikä on ensisijainen kielesi?';

  @override
  String get replyToReview => 'Vastaa arvosteluun';

  @override
  String failedToDeleteError(String error) {
    return 'Poistaminen epäonnistui: $error';
  }

  @override
  String get newestFirst => 'Uusimmat ensin';

  @override
  String get wrappedCreatingYourStory => 'Luodaan\n2025 tarinaasi…';

  @override
  String get chatAppsPrivateMemories => 'Pidä yksityiset muistot sovelluksessa';

  @override
  String get pleaseEnterPayPalEmail => 'Syötä PayPal-sähköpostisi';

  @override
  String get transcription => 'Litterointi';

  @override
  String get yourReview => 'Arvostelusi';

  @override
  String get filesDownloadedUploadedNextTime => 'Jo ladatut tiedostot ladataan palvelimelle seuraavalla kerralla.';

  @override
  String get phoneSetupStep3Subtitle => 'Sisaanrakennetulla reaaliaikaisella litteroinnilla';

  @override
  String get mcpConnectionFailed => 'MCP-palvelimeen yhdistäminen epäonnistui';

  @override
  String get chatAppsConnectTelegramTitle => 'Yhdistä Telegram';

  @override
  String get createMemoryTooltip => 'Luo uusi muisto';

  @override
  String get connectDeviceMessage => 'Yhdistä Omi-laite käyttääksesi\nlaiteasetuksia ja mukautusta';

  @override
  String get authorizingMcpServer => 'Valtuutetaan…';

  @override
  String charactersCount(int count) {
    return '$count merkkiä';
  }

  @override
  String get syncStatusUploaded => 'Ladattu · käsitellään Omissa';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'Ole hyvä ja kirjaudu $serviceName palveluun kohdassa Asetukset > Tehtäväintegraatiot';
  }

  @override
  String get setDefaultButton => 'Aseta oletukseksi';

  @override
  String get resummarizingConversation => 'Tiivistetään keskustelua uudelleen…\nTämä voi kestää muutaman sekunnin';

  @override
  String estimatedHours(int count) {
    return '~$count tunti(a)';
  }

  @override
  String get chatAppsInsightsSubtitle => 'Anna Omin lähettää sinulle yhteenveto tai oivallus tänne.';

  @override
  String get memoryAllowUse => 'Salli käyttö';

  @override
  String get model => 'Malli';

  @override
  String get memoryGraphTitle => 'Muistikartta';

  @override
  String get endpointURL => 'Päätepisteen URL';

  @override
  String get wrappedShareYourWrapped => 'Jaa Wrapped';

  @override
  String get micGainDescBoosted => 'Vahvistettu - hiljaisiin ympäristöihin';

  @override
  String get wrappedMinutes => 'minuuttia';

  @override
  String get language => 'Kieli';

  @override
  String downloadErrorWithMessage(String error) {
    return 'Latausvirhe: $error';
  }

  @override
  String get onboardingRatingPromptNo => 'Ei';

  @override
  String get whatWouldYouLikeToRemember => 'Mitä haluaisit muistaa?';

  @override
  String get deviceOnboardingMuteUnmuteDesc => 'Kytke mikrofoni päälle tai pois';

  @override
  String secondsCount(int count) {
    return '$count sekuntia';
  }

  @override
  String get icon => 'Kuvake';

  @override
  String get realTimeTranscript => 'Reaaliaikainen litterointi';

  @override
  String get deviceOnboardingVoiceReplySample => 'Selvä. Seuraava kokouksesi alkaa kahdenkymmenen minuutin kuluttua.';

  @override
  String get noDisconnectsRecorded => 'Katkaisuja ei ole tallennettu';

  @override
  String get filterMyApps => 'Omat sovellukseni';

  @override
  String get recapRegenerateCooldown => 'Odota muutama sekunti ennen uudelleen luomista.';

  @override
  String get templateName => 'Mallin nimi';

  @override
  String get retry => 'Yritä uudelleen';

  @override
  String get sdCardSyncDescription => 'SD-kortin synkronointi tuo muistosi SD-kortilta sovellukseen';

  @override
  String get deviceTutorial => 'Näin käytät Omia';

  @override
  String get noApiKeysCreateOne => 'Ei API-avaimia. Luo yksi aloittaaksesi.';

  @override
  String siriShortcutsSetupHint(String askPhrase, String questionPhrase) {
    return 'Ota Omi käyttöön Pikakomennot → Siri -kohdasta. Sano “$askPhrase” tai “$questionPhrase” ja esitä sitten kysymyksesi.';
  }

  @override
  String get failedToDeleteSomeItems => 'Joidenkin kohteiden poisto epäonnistui';

  @override
  String get raybanMetaSetupDescription =>
      'Käytä Ray-Ban Meta -laseja Omi-tallennuslaitteena keskusteluihin ja visuaaliseen kontekstiin. Omi avaa Meta AI -sovelluksen lasien yhdistämistä varten.';

  @override
  String get tabToDo => 'Tekemättä';

  @override
  String get otaWifiFailed => 'Wi-Fiin ei voitu liittyä. Tarkista verkon nimi ja salasana.';

  @override
  String get changePlan => 'Vaihda tilausta';

  @override
  String copiedToClipboard(String title) {
    return '$title kopioitu leikepöydälle';
  }

  @override
  String get completeAuthBrowser => 'Viimeistele todennus selaimessasi. Kun olet valmis, palaa sovellukseen.';

  @override
  String get migrationInProgressMessage => 'Siirto käynnissä. Et voi muuttaa suojaustasoa ennen kuin se on valmis.';

  @override
  String get keepSubscription => 'Pidä tilaus';

  @override
  String get playbackPreparingAudio => 'Valmistellaan ääntä…';

  @override
  String get cloudStorageDialogMessage =>
      'Reaaliaikaiset tallenteet tallennetaan yksityiseen pilvitallennustilaan puhuessasi.';

  @override
  String get newChat => 'Uusi keskustelu';

  @override
  String get paymentEnterAmountGreaterThanZero => 'Syötä summa, joka on suurempi kuin 0';

  @override
  String showAllPeople(int count) {
    return 'Näytä kaikki ($count) henkilöä';
  }

  @override
  String deletePersonNamedTitle(String name) {
    return 'Poistetaanko $name?';
  }

  @override
  String get importTranscriptFiles => 'Litterointitiedostot';

  @override
  String get transcriptPlaceholder => 'Litterointi nakyy taalla…';

  @override
  String get logShared => 'Loki jaettu';

  @override
  String get deleteReasonNotUsing => 'En käytä sitä tarpeeksi';

  @override
  String diagnosticsDropsPerHour(int count) {
    return 'noin $count tunnissa';
  }

  @override
  String get wrappedProcessingDefault => 'Käsitellään…';

  @override
  String get failedToConnectGoogleTasksRetry => 'Yhteyden muodostaminen Google Tasksiin epäonnistui. Yritä uudelleen.';

  @override
  String get downloadingFromSdCard => 'Ladataan SD-kortilta';

  @override
  String get firmwareFormatWarning =>
      'Tämä laiteohjelmisto alustaa SD-kortin. Varmista, että kaikki offline-tiedot on synkronoitu ennen päivitystä.\n\nJos näet vilkkuvan punaisen valon tämän version asentamisen jälkeen, älä huoli. Yhdistä laite sovellukseen ja sen pitäisi muuttua siniseksi. Punainen valo tarkoittaa, että laitteen kelloa ei ole vielä synkronoitu.';

  @override
  String get pleaseProvidePrompt => 'Anna kehote';

  @override
  String get voiceResponseAlways => 'Aina';

  @override
  String get statusLabel => 'Tila';

  @override
  String get shareLogs => 'Jaa lokit';

  @override
  String get continueAnyway => 'Jatka';

  @override
  String get transferCompleteMessage => 'Siirto valmis! Voit nyt toistaa tämän nauhoituksen.';

  @override
  String get reviewCaughtUpBody => 'Omi kysyy täällä vain, kun se tarvitsee sinua.';

  @override
  String get calculatingETA => 'Lasketaan…';

  @override
  String get speechProfileTopicWork => 'Mitä teet työksesi?';

  @override
  String get considerOmiCloud => 'Harkitse Omi Cloudin käyttöä paremman suorituskyvyn saavuttamiseksi.';

  @override
  String get testConversationPrompt => 'Testaa keskustelukehotetta';

  @override
  String get deletePending => 'Poista odottavat';

  @override
  String get renameConversation => 'Nimeä uudelleen';

  @override
  String get batteryDrainSignificantly => 'Akun kulutus kasvaa merkittävästi.';

  @override
  String get clear => 'Tyhjennä';

  @override
  String get addAppEnterWebhookUrl => 'Syötä webhook-URL sovelluksellesi';

  @override
  String get active => 'Aktiivinen';

  @override
  String get exportStartedMessage => 'Vienti aloitettu. Tämä voi kestää muutaman sekunnin…';

  @override
  String get dataAccessNoticeDescription =>
      'Tämä sovellus käyttää tietojasi. Omi AI ei ole vastuussa siitä, miten tietojasi käytetään, muokataan tai poistetaan tässä sovelluksessa';

  @override
  String get yourRequestUnderReview => 'Pyyntösi on käsittelyssä';

  @override
  String get unresolvedSpeakersMessage =>
      'Omi ei pystynyt erottamaan muita ääniä äänitteiden välillä. Napauta puhujamerkintää nimetäksesi, kuka puhuu.';

  @override
  String downloadError(String error) {
    return 'Latausvirhe: $error';
  }

  @override
  String get offlineSync => 'Offline-synkronointi';

  @override
  String get cancelSubscription => 'Peruuta tilaus';

  @override
  String get claudeDesktopConnectorSetup =>
      'Lisää Claude Desktop → Settings → Connectors-palvelussa mukautettu liitin ja liitä palvelimen URL-osoite. Jos Claude pyytää edistynyttä OAuth Client ID:tä, käytä alla olevaa arvoa ja jätä salaisuus tyhjäksi — älä koskaan käytä MCP API -avaintasi OAuth-salaisuuksena.';

  @override
  String get chatAppsTelegramWaiting => 'Odotetaan, että napautat Aloita Telegramissa…';

  @override
  String get tryAgain => 'Yritä uudelleen';

  @override
  String get syncStatusOnDevice => 'Laitteellasi';

  @override
  String get entityCorrectionTitle => 'Mikä ei ole oikein?';

  @override
  String peopleDeletedToast(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count henkilöä poistettu',
      one: '1 henkilö poistettu',
    );
    return '$_temp0';
  }

  @override
  String get features => 'Ominaisuudet';

  @override
  String get startEarning => 'Aloita ansaitseminen! 💰';

  @override
  String get enterYourNumber => 'Syota numerosi';

  @override
  String get addToClaudeCodeConfig => 'Lisää ~/.claude.json-tiedostoon';

  @override
  String get cleanDisconnect => 'Puhdas katkaisu';

  @override
  String get grantContactsAccess => 'Anna paasy yhteystietoihisi';

  @override
  String get feedbackReasonIncorrect => 'Virheellinen tai keksitty';

  @override
  String get addAppErrorSelectingImageRetry => 'Virhe kuvan valinnassa. Yritä uudelleen.';

  @override
  String get feedbackTitleNotUsing => 'Mikä saisi sinut käyttämään Omia enemmän?';

  @override
  String get memories => 'Muistot';

  @override
  String get capturingPhotos => 'Otetaan kuvia';

  @override
  String get hideApiKey => 'Piilota API-avain';

  @override
  String get signUpButton => 'Rekisteröidy';

  @override
  String get tuesdayAbbr => 'Ti';

  @override
  String get noApiKeys => 'Ei vielä API-avaimia';

  @override
  String get keyWord => 'Avain';

  @override
  String reviewAnswersConversations(int count) {
    return 'Tämä vastaus nimeää $count keskustelua';
  }

  @override
  String get statusFailed => 'Epäonnistui';

  @override
  String get installedApps => 'Asennetut sovellukset';

  @override
  String get flashFirmware => 'Asenna laiteohjelmisto';

  @override
  String get conversationUrlCouldNotBeGenerated => 'Keskustelun URL-osoitetta ei voitu luoda.';

  @override
  String get reloadingApps => 'Ladataan sovelluksia uudelleen…';

  @override
  String get goalTitle => 'Tavoitteen otsikko';

  @override
  String get importantConversationTitle => 'Tärkeä keskustelu';

  @override
  String get byContinuingAgree => 'Jatkamalla hyväksyt ';

  @override
  String get saturdayAbbr => 'La';

  @override
  String get subscriptionReactivatedDefault =>
      'Tilauksesi on aktivoitu uudelleen! Ei veloitusta nyt - sinut laskutetaan nykyisen jakson lopussa.';

  @override
  String get tryLatestExperimentalFeatures => 'Kokeile Omi-tiimin uusimpia kokeellisia ominaisuuksia.';

  @override
  String get chatAppsEntrySubtitle => 'Keskustele Omin kanssa sovelluksissa, joita käytät joka päivä.';

  @override
  String get transcriptionPaused => 'Nauhoittaa, yhdistetään uudelleen';

  @override
  String get appleHealthFeatureReadOnlyTitle => 'Vain lukuoikeus';

  @override
  String get shareDataForTraining => 'Jaa dataa koulutukseen';

  @override
  String get noNotificationScopesAvailable => 'Ilmoitusalueita ei ole saatavilla';

  @override
  String disconnectFromApp(String appName) {
    return 'Katkaise yhteys palveluun $appName?';
  }

  @override
  String get failedToConnectGoogleTasks => 'Yhteyden muodostaminen Google Tasksiin epäonnistui';

  @override
  String get copyToClipboard => 'Kopioi leikepöydälle';

  @override
  String get stopRecordingConfirmation => 'Lopetetaanko tallennus ja tiivistetäänkö keskustelu nyt?';

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'Yhteenvedon luominen epäonnistui. Varmista, että sinulla on keskusteluja kyseiseltä päivältä.';

  @override
  String get monthlyLimitReached => 'Olet saavuttanut kuukausirajan.';

  @override
  String get permissionsPageDescription =>
      'Omi käyttää näitä yhdistääkseen laitteeseesi, nauhoittaakseen ääntä, toimiakseen taustalla, lähettääkseen muistutuksia ja merkitäkseen, missä keskustelut käytiin.';

  @override
  String get onboardingTellUsAboutYourself => 'Kerro meille itsestäsi';

  @override
  String get deviceOnboardingAskQuestionSubtitle =>
      'Paina painiketta kerran, esitä kysymyksesi ja paina uudelleen, kun olet valmis';

  @override
  String get filters => 'Suodattimet';

  @override
  String get firmwareUpdateWarning => 'Älä sulje sovellusta tai sammuta laitetta. Tämä voi vaurioittaa laitettasi.';

  @override
  String get oneSourceAtATime => 'Omi tallentaa vain yhdestä lähteestä kerrallaan.';

  @override
  String chatAppsConnectedAs(String handle) {
    return 'Yhdistetty: $handle';
  }

  @override
  String get pilotFeatures => 'Pilottiominaisuudet';

  @override
  String get selectFirmwareZip => 'Valitse laiteohjelmiston ZIP-tiedosto';

  @override
  String get feedbackReasonRecordingPoorTranscription => 'Poor transcription';

  @override
  String get deleteAccountFailed => 'Tiliäsi ei voitu poistaa. Yritä uudelleen.';

  @override
  String get searchConversations => 'Etsi keskusteluja';

  @override
  String get frequencyBalanced => 'Tasapainotettu';

  @override
  String get auto => 'Automaattinen';

  @override
  String get actionItemUpdatedSuccessfully => 'Tehtävä päivitetty onnistuneesti';

  @override
  String get entityProjects => 'Projektit';

  @override
  String get signInWithApple => 'Kirjaudu Applella';

  @override
  String get backendUrlLabel => 'Palvelimen URL';

  @override
  String confidenceSummaryLikely(String name) {
    return 'Omi tunnistaa yleensä henkilön $name äänen, mutta olet vahvistanut sen vasta muutaman kerran.';
  }

  @override
  String get entityOpenThreads => 'Avoimet asiat';

  @override
  String get deleteActionItemMessage => 'Poistetaanko tämä tehtävä?';

  @override
  String chatWithApp(String appName) {
    return 'Keskustele: $appName';
  }

  @override
  String get editActionItem => 'Muokkaa tehtävää';

  @override
  String get cloudStorageEnabled => 'Pilvitallennustila käytössä';

  @override
  String get wrappedPersonalGrowth => 'Henkilökohtainen kasvu';

  @override
  String get chatAppsProPerkSave => 'Tallenna muistoja ja hallitse tehtäviä suoraan chatista';

  @override
  String get alreadyHaveAccountLogin => 'Onko sinulla jo tili? Kirjaudu sisään';

  @override
  String makeItemPublicQuestion(String item) {
    return 'Tee $item julkiseksi?';
  }

  @override
  String get usagePeakHour => 'Peak hour';

  @override
  String get addWords => 'Lisää sanoja';

  @override
  String get usageNow => 'now';

  @override
  String get usageMinutes => 'minuuttia';

  @override
  String availableSpace(String space) {
    return 'Käytettävissä oleva tila: $space';
  }

  @override
  String get providingSubtitle => 'Tehtävät ja muistiinpanot automaattisesti tallennettu.';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% valmistumisaste';
  }

  @override
  String summaryGeneratedFor(String date) {
    return 'Yhteenveto luotu päivälle $date';
  }

  @override
  String get selectCategory => 'Valitse kategoria';

  @override
  String nProcessed(int count) {
    return '$count käsiteltyä';
  }

  @override
  String get privacyPolicyTitle => 'Tietosuojakäytäntö';

  @override
  String get deviceMayWarmUp => 'Laite voi lämmetä pitkäaikaisessa käytössä.';

  @override
  String get designingApp => 'Suunnitellaan sovellusta';

  @override
  String get couldNotLoadWhatsNew => 'Uutuuksia ei voitu ladata';

  @override
  String get doNotCloseApp => 'Älä sulje sovellusta.';

  @override
  String get voiceResponseAudio => 'Lue Omin vastaus ääneen';

  @override
  String get allTime => 'Kaikki aika';

  @override
  String get developerSettingsTitle => 'Kehittäjäasetukset';

  @override
  String get restoreAction => 'Palauta';

  @override
  String get phoneSetupStep3Title => 'Aloita soittaminen yhteystiedoillesi';

  @override
  String get anErrorOccurredTryAgain => 'Tapahtui virhe. Yritä uudelleen.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'Tässä mitä juuri keskustelimme: $link';
  }

  @override
  String get playbackAudioLoadFailed => 'Ääntä ei voitu ladata';

  @override
  String get phoneMute => 'Mykista';

  @override
  String get captureNotTranscribing => 'Ei litterointia';

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return 'Tallennus pysähtyi: $reason. Saatat joutua yhdistämään ulkoiset näytöt uudelleen tai käynnistämään tallennuksen uudelleen.';
  }

  @override
  String get sttProviderDeepgram => 'Deepgram';

  @override
  String get spaceKey => 'Välilyönti';

  @override
  String get raybanMetaOpenMetaAI => 'Yhdistä Meta AI:n kautta';

  @override
  String get linkEvent => 'Linkitä tapahtuma';

  @override
  String get fairUse3Day => '3 päivän jakso';

  @override
  String failedToStartAppAuth(String appName) {
    return '$appName-todennuksen aloitus epäonnistui';
  }

  @override
  String get processingOnServer => 'Käsitellään palvelimella…';

  @override
  String errorStartingRecording(String error) {
    return 'Virhe nauhoituksen aloittamisessa: $error';
  }

  @override
  String get quiet => 'Hiljainen';

  @override
  String get startConversationToSeeInsights => 'Aloita keskustelu Omin kanssa\nnähdäksesi käyttötietosi täällä.';

  @override
  String get processAudio => 'Käsittele ääni';

  @override
  String get chatAppsConnectIMessageTitle => 'Yhdistä lähettämällä Omille viesti';

  @override
  String get chatWithOmi => 'Keskustele Omin kanssa';

  @override
  String get clickToBeginRecording => 'Napsauta aloittaaksesi tallennuksen';

  @override
  String get confirmAndProceed => 'Vahvista ja jatka';

  @override
  String get mondayAbbr => 'Ma';

  @override
  String sdCardProcessingMessage(int count) {
    return 'Käsitellään $count nauhoitusta. Tiedostot poistetaan SD-kortilta jälkeen.';
  }

  @override
  String get chatReplyNotSignedIn => 'Et ole kirjautunut sisään. Kirjaudu sisään ja yritä uudelleen.';

  @override
  String deviceOnboardingVoiceReplySettingsHint(String settings, String voiceResponse) {
    return 'Voit muuttaa tätä milloin tahansa numerossa $settings › $voiceResponse';
  }

  @override
  String get wrappedGenerateMyWrapped => 'Luo Wrapped';

  @override
  String get reviewChangesIntro =>
      'Mitä Omi on muuttanut itse viimeisen 30 päivän aikana. Kumoa kaikki, mikä näyttää väärältä.';

  @override
  String get stripeReadyForPayments =>
      'Stripe-tilisi on nyt valmis vastaanottamaan maksuja. Voit alkaa ansaita sovellustesi myynnistä heti.';

  @override
  String get appleWatchSetup => 'Apple Watch -asennus';

  @override
  String get failedToDisconnect => 'Yhteyden katkaisu epäonnistui';

  @override
  String get localStorageEnabled => 'Paikallinen tallennustila käytössä';

  @override
  String get captureSourceDesktop => 'Tietokone';

  @override
  String get serialNumber => 'Sarjanumero';

  @override
  String get appleHealthFeatureSecureDesc => 'Apple Health -tietosi synkronoidaan yksityisesti Omi-tilillesi.';

  @override
  String get tryAdjustingSearch => 'Kokeile säätää hakua tai suodattimia';

  @override
  String connectTo(String appName) {
    return 'Yhdistä palveluun $appName';
  }

  @override
  String get exportConversationsDescription => 'Vie keskustelut JSON-muotoon';

  @override
  String get featuredLabel => 'ESITELTY';

  @override
  String get speechProfile => 'Ääniprofiili';

  @override
  String get integrations => 'Integraatiot';

  @override
  String get hideCompletedTasks => 'Piilota valmiit';

  @override
  String get sendRawAudioToOmi => 'Lähetä käsittelemätön ääni Omille';

  @override
  String ratingsCount(String count) {
    return '$count+ arvioita';
  }

  @override
  String get exportShared => 'Vienti jaettu';

  @override
  String get conversationTimeout => 'Keskustelun aikakatkaisu';

  @override
  String get installStableFirmware => 'Asenna vakaa laiteohjelmisto';

  @override
  String get secureAndReliable => 'Turvallinen ja luotettava';

  @override
  String get exportingConversations => 'Viedään keskusteluja…';

  @override
  String get feedbackReasonRecordingFragmentedOrDuplicated => 'Fragmented or duplicated';

  @override
  String get chatAppsWaitingMessage =>
      'Lähetä viesti Viestit-sovelluksessa. Tämä näkymä päivittyy heti, kun Omi saa sen.';

  @override
  String get onboardingSetupStepWorkspace => 'Työtilaasi valmistellaan';

  @override
  String get recap => 'Kertaus';

  @override
  String get lessThanAMinute => 'Alle minuutti';

  @override
  String get tasks => 'Tehtävät';

  @override
  String get onboardingSetupStepDevices => 'Laitteitasi yhdistetään';

  @override
  String pinPersonTitle(String name) {
    return 'Kiinnitä $name';
  }

  @override
  String get wrappedButYouPushedThrough => 'Mutta selvisit siitä 💪';

  @override
  String get fetchingYourAppDetails => 'Haetaan sovelluksen tietoja';

  @override
  String get timeout2MinutesDesc => 'Lopeta keskustelu 2 minuutin hiljaisuuden jälkeen';

  @override
  String get otaUpdateCancelled => 'Päivitys peruttiin';

  @override
  String get usageTasksNotes => 'Tasks & notes';

  @override
  String get deviceNotConnected => 'Laitetta ei ole yhdistetty';

  @override
  String get rayBanMetaMicPickerEmpty =>
      'Bluetooth-mikrofoneja ei löytynyt. Yhdistä lasit iPhonen asetuksissa ja yritä uudelleen.';

  @override
  String get actionItemCompleted => 'Tehtävä suoritettu';

  @override
  String get usageSocialSettings => 'Sosiaalisissa tilanteissa';

  @override
  String get from => 'alkaen';

  @override
  String get siriIndexSetting => 'Use Omi with Siri & Apple Intelligence';

  @override
  String get reviewReasonNotMine => 'Ei minun';

  @override
  String connectToDeviceName(String deviceName) {
    return 'Connect to $deviceName';
  }

  @override
  String get onboardingComplete => 'Valmis';

  @override
  String get chatAppsShowInApp => 'Näytä nämä keskustelut Omi-sovelluksessa';

  @override
  String nCompleted(int count) {
    return '$count valmiina';
  }

  @override
  String get feedbackAllGood => 'All good';

  @override
  String get syncCardUploadingTitle => 'Lähetetään Omiin';

  @override
  String get baselineMemory => 'Perusmuisti';

  @override
  String get trainFamilyProfilesDesc =>
      'Nauhoituksesi auttavat meitä tunnistamaan ja luomaan profiileja ystävillesi ja perheellesi.';

  @override
  String get failedToGenerateShareLink => 'Jakamislinkin luominen epäonnistui';

  @override
  String get onlyYouCanSeeConversation => 'Vain sinä voit nähdä tämän keskustelun';

  @override
  String get popular => 'Suosittu';

  @override
  String get captureRecordingSeparate => 'Erota…';

  @override
  String get allTemplates => 'Kaikki mallit';

  @override
  String devicesFoundNearby(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'LAITETTA',
      one: 'LAITE',
    );
    return '$count $_temp0 LÖYDETTY LÄHISTÖLTÄ';
  }

  @override
  String speakerTagPromptSavedAs(String name) {
    return 'Tallennettu nimellä $name';
  }

  @override
  String get configureSettings => 'Määritä asetukset';

  @override
  String get noRatings => 'ei arvioita';

  @override
  String resumingInCountdown(String countdown) {
    return 'Jatketaan ${countdown}s kuluttua…';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 Muistanut $count muistoa';
  }

  @override
  String get clearDueDate => 'Tyhjennä eräpäivä';

  @override
  String get copy => 'Kopioi';

  @override
  String get showPhoneCallButtonDesc => 'Näytä puhelupainike aloitusnäytöllä';

  @override
  String get appleHealthFeatureReadOnlyDesc => 'Omi ei koskaan kirjoita Apple Healthiin tai muuta tietojasi.';

  @override
  String get multipleSpeakersDescription =>
      'Näyttää siltä, että nauhoituksessa on useita puhujia. Varmista, että olet hiljaisessa paikassa ja yritä uudelleen.';

  @override
  String get failedToUpdateDueDate => 'Eräpäivän päivittäminen epäonnistui';

  @override
  String get successfullyConnectedWhoop => 'Yhdistetty onnistuneesti Whoopiin!';

  @override
  String get categories => 'Kategoriat';

  @override
  String get loadingTranscript => 'Ladataan litterointia…';

  @override
  String get syncCustomSttWarningMessage =>
      'Käytät omaa litterointipalveluasi. Näiden tallenteiden synkronointi litteroi ne Omin palvelimilla, ja ne lasketaan tilauksesi litterointirajaan.';

  @override
  String get newRecording => 'Uusi tallennus';

  @override
  String get transcriptionUnavailableRecordingSaved =>
      'Litterointi ei ole käytettävissä — tallennus jatkuu ja äänesi tallennetaan.';

  @override
  String get submittingYourApp => 'Lähetetään sovellustasi…';

  @override
  String get failedToLinkCalendarEvent => 'Kalenteritapahtuman linkittäminen epäonnistui';

  @override
  String get paypalMeLinkHint => 'paypal.me/nik';

  @override
  String get yourInformation => 'Sinun Tietosi';

  @override
  String get accountDeletionInProgressSignInAgain =>
      'Tätä tiliä poistetaan. Kirjaudu sisään toisella tilillä tai odota muutama minuutti ja yritä uudelleen.';

  @override
  String get on => 'On';

  @override
  String get diagnostics => 'Diagnostiikka';

  @override
  String get errorCopied => 'Virheilmoitus kopioitu leikepöydälle';

  @override
  String get lovingOmi => 'Pidätkö Omista?';

  @override
  String get permissionDescReadMemories => 'Tämä sovellus voi käyttää muistojasi.';

  @override
  String get doNotIncludeHttpInLink => 'Älä sisällytä http, https tai www linkkiin';

  @override
  String get shareRecording => 'Jaa nauhoitus';

  @override
  String get memoryReviewFix => 'Korjaa';

  @override
  String get selectedPlanNotAvailable => 'Valittu tilaus ei ole saatavilla. Yritä uudelleen.';

  @override
  String get autoCreateWhenDetected => 'Luo automaattisesti, kun nimi havaitaan';

  @override
  String get addAppSelectCapability => 'Valitse vähintään yksi toiminto sovelluksellesi';

  @override
  String get showPassword => 'Näytä salasana';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Keskustelut päättyvät nyt $minutes minuutin hiljaisuuden jälkeen';
  }

  @override
  String get updateAvailableMessage => 'Omin uusi versio on valmis, ja siinä on korjauksia ja parannuksia.';

  @override
  String get nameMustBeBetweenCharacters => 'Nimen on oltava 2-40 merkkiä';

  @override
  String operatorSubtitle(int count) {
    return '$count kysymystä kuukaudessa';
  }

  @override
  String conversationsDeletedCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count keskustelua poistettu',
      one: '1 keskustelu poistettu',
    );
    return '$_temp0';
  }

  @override
  String get monthlyPayoutsDescription => 'Saat kuukausittaiset maksut suoraan tilillesi, kun saavutat 10 \$ ansiot';

  @override
  String get dailyScoreExplanation =>
      'Päivittäinen pistemääräsi perustuu tehtävien suorittamiseen. Suorita tehtäväsi parantaaksesi pistemäärääsi!';

  @override
  String get improveConnectionContent =>
      'Olemme parantaneet Omin yhteydenpitoa laitteeseesi. Aktivoidaksesi tämän, siirry Laitteen tiedot -sivulle, napauta \"Katkaise laitteen yhteys\" ja yhdistä laitteesi uudelleen.';

  @override
  String get syncingRecordings => 'Synkronoidaan nauhoituksia';

  @override
  String get professionProductManager => 'Tuotepäällikkö';

  @override
  String get nameMustBeAtLeast2Characters => 'Nimen on oltava vähintään 2 merkkiä';

  @override
  String get conversationTitle => 'Keskustelun otsikko';

  @override
  String mcpServerConnected(int count) {
    return '$count työkalua yhdistetty onnistuneesti';
  }

  @override
  String get feedbackSubtitleNotUsing => 'Haluamme tehdä Omista hyödyllisemmän sinulle.';

  @override
  String get exportBeforeDelete =>
      'Voit viedä tietosi ennen tilin poistamista, mutta poiston jälkeen niitä ei voi palauttaa.';

  @override
  String deleteTasksTitle(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Poistetaanko $count tehtävää?',
      one: 'Poistetaanko 1 tehtävä?',
    );
    return '$_temp0';
  }

  @override
  String get frequencyMaximum => 'Maksimi';

  @override
  String get cancelReasonSubtitle => 'Voitko kertoa meille, miksi lähdet?';

  @override
  String get generatingIconStep => 'Luodaan kuvaketta';

  @override
  String get storeAudioDescription =>
      'Säilytä kaikki äänitallenteet paikallisesti puhelimessasi. Kun pois käytöstä, vain epäonnistuneet lataukset säilytetään tallennustilan säästämiseksi.';

  @override
  String get unpairDeviceConfirmTitle => 'Poistetaanko laitteen pariliitos?';

  @override
  String get phoneCallsMaybeLater => 'Ehkä myöhemmin';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'Tapahtui virhe: $message';
  }

  @override
  String get yourPrivacyMattersToUs => 'Yksityisyytesi on meille tärkeä';

  @override
  String get collapseAction => 'Tiivistä';

  @override
  String get friendWordOfMouth => 'Ystävä';

  @override
  String get deviceOnboardingVoiceReplyStatusHeadphonesDisconnected =>
      'Kuulokkeita ei ole kytketty. Omi pysyy äänettömänä, kunnes yhdistät osan.';

  @override
  String get connectDevice => 'Yhdistä laite';

  @override
  String get deviceId => 'Laitteen tunnus';

  @override
  String get addWordsDescription => 'Lisää sanoja, jotka Omin tulisi tunnistaa transkription aikana.';

  @override
  String get userId => 'Käyttäjätunnus';

  @override
  String evidenceCardConfirms(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Kyllä $count ehdotuksessa',
      one: 'Kyllä 1 ehdotuksessa',
    );
    return '$_temp0';
  }

  @override
  String segmentsCount(int count) {
    return '$count segmenttiä';
  }

  @override
  String get permissionsSetupTitle => 'Saat parhaan kokemuksen';

  @override
  String get permissionTypeAccess => 'Pääsy';

  @override
  String get speakerTagPromptSaveVoicesBody =>
      'Omi tallentaa lyhyen ääninäytteen tunnistaakseen heidät ensi kerralla. Voit muuttaa tätä milloin tahansa asetuksista.';

  @override
  String get developerApi => 'Kehittäjän API';

  @override
  String get chargingIssues => 'Latausongelmat';

  @override
  String get debugAndDiagnostics => 'Virheenkorjaus ja diagnostiikka';

  @override
  String get failedConnections => 'Epäonnistuneet yhteydet';

  @override
  String get userIdCopied => 'Käyttäjätunnus kopioitu leikepöydälle';

  @override
  String get cannotReportOwnMessage => 'Et voi ilmoittaa omista viesteistäsi.';

  @override
  String get latestVersion => 'Uusin versio';

  @override
  String get feedbackReasonNotHelpful => 'Ei hyödyllinen tai asiaankuulumaton';

  @override
  String get deletePeopleMessage =>
      'Tämä poistaa heidän ääninäytteensä, eikä sitä voi perua. Heidän repliikkinsä aiemmissa keskusteluissa muuttuvat nimettömiksi puhujiksi.';

  @override
  String get deviceOnboardingAllSetSubtitle => 'Tarkista tai muuta riviä napauttamalla sitä.';

  @override
  String get mergeConversations => 'Yhdistä keskustelut';

  @override
  String get paused => 'Keskeytetty';

  @override
  String get updateGuide => 'Päivitysopas';

  @override
  String cancelBillingPeriodInfo(String date) {
    return 'Tilauksesi pysyy aktiivisena $date asti. Sen jälkeen sinut siirretään ilmaisversioon rajoitetuilla ominaisuuksilla.';
  }

  @override
  String get reconnectingToInternet => 'Yhdistetään uudelleen internetiin…';

  @override
  String get allFilesDeleted => 'Kaikki tallenteet poistettu';

  @override
  String get paypalEmailHint => 'nik@example.com';

  @override
  String get oneWeekAgo => 'viikko sitten';

  @override
  String get deviceOnboardingAllSetSinglePressBadge => '1×';

  @override
  String get playbackAudioUnavailable => 'Ääni ei saatavilla';

  @override
  String get deviceOnboardingTryDoubleTap => 'Kokeile nyt! Kaksoisnapauta Omi-laitettasi';

  @override
  String get deleteReasonPrivacy => 'Yksityisyyteen liittyvät huolet';

  @override
  String get cleanUpPinnedNote => 'Kiinnitettyjä ihmisiä ei koskaan oteta mukaan siivoukseen.';

  @override
  String get wrappedProductiveDay => 'Tuottava';

  @override
  String get voiceSharedAcrossDevices => 'Äänivalintasi on yhteinen mobiilissa ja työpöydällä.';

  @override
  String get knowledgeGraphDeleted => 'Tietämysgraafi poistettu';

  @override
  String get pressDoneToCreate => 'Paina valmis luodaksesi';

  @override
  String get cloudStorage => 'Pilvitallennustila';

  @override
  String get howDoesItWork => 'Miten se toimii?';

  @override
  String get submitApp => 'Lähetä sovellus';

  @override
  String get searchMemories => 'Hae muistoja';

  @override
  String get fallNotificationTitle => 'Auts';

  @override
  String storedOnDevice(String deviceName) {
    return 'Tallennettu laitteelle $deviceName';
  }

  @override
  String get contactsPermissionRequired => 'Yhteystietolupa vaaditaan';

  @override
  String get reviewUpdatedSuccessfully => 'Arvostelu päivitetty onnistuneesti 🚀';

  @override
  String get pleaseEnterPayPalMeLink => 'Syötä PayPal.me-linkkisi';

  @override
  String get notHelpful => 'Ei hyödyllinen';

  @override
  String get recordingsToSync => 'Synkronoitavat nauhoitukset';

  @override
  String get categoryUtilities => 'Työkalut';

  @override
  String get exportStarted => 'Vienti aloitettu. Tämä voi kestää muutaman sekunnin…';

  @override
  String get deviceOnboardingVoiceReplyStatusOff => 'Omi pysyy hiljaa. Vastaukset näkyvät edelleen sovelluksessa.';

  @override
  String get myGoal => 'Tavoitteeni';

  @override
  String timeHourSingular(int count) {
    return '$count tunti';
  }

  @override
  String get chatToolsManifestUrl => 'Keskustelutyökalujen manifestin URL';

  @override
  String msgSelectFilesError(String error) {
    return 'Virhe tiedostojen valinnassa: $error';
  }

  @override
  String connectedToApp(String appName) {
    return 'Yhdistetty palveluun $appName';
  }

  @override
  String get entityCorrectionHint => 'Kerro Omille, mitä korjataan';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch yhdistetty!';

  @override
  String appIntegration(String appName) {
    return '$appName-integraatio';
  }

  @override
  String get cancelReasonAudioQuality => 'Äänen/transkription laatu';

  @override
  String get invalidProviderInConfig => 'Virheellinen palveluntarjoaja kokoonpanossa';

  @override
  String get deselectAll => 'Poista valinnat';

  @override
  String get chatAppsCodeExpiredMessage => 'Hae uusi koodi ja lähetä se Viestit-sovelluksesta.';

  @override
  String get reviewAnswerFailed => 'Vastausta ei voitu tallentaa. Yritä uudelleen.';

  @override
  String get categorySocial => 'Sosiaalinen';

  @override
  String get rating4PlusStars => '4+ tähteä';

  @override
  String get couldNotOpenSmsApp => 'SMS-sovellusta ei voitu avata. Yritä uudelleen.';

  @override
  String get chatAppsNoMessages => 'Ei viestejä';

  @override
  String get wrappedCelebrity => 'JULKKIS';

  @override
  String get revokeKeyQuestion => 'Peruuta avain?';

  @override
  String timeMinsAndSecs(int mins, int secs) {
    return '$mins min $secs sek';
  }

  @override
  String get searchContactsHint => 'Etsi yhteystietoja';

  @override
  String get showEventsWithoutParticipants => 'Näytä tapahtumat ilman osallistujia';

  @override
  String get fair => 'Kohtalainen';

  @override
  String get tipAutoSync => 'Nauhoitukset synkronoidaan automaattisesti';

  @override
  String get summaryCopiedToClipboard => 'Yhteenveto kopioitu leikepöydälle';

  @override
  String get clearSearch => 'Tyhjennä haku';

  @override
  String get speakerTagPromptNotAPerson => 'Ei ihminen';

  @override
  String get modelLabel => 'Malli';

  @override
  String deleteItemQuestion(String item) {
    return 'Poista $item?';
  }

  @override
  String get enterPromoCode => 'Syötä tarjouskoodi';

  @override
  String get phoneNoContactsFound => 'Yhteystietoja ei loydy';

  @override
  String countRemaining(String count) {
    return '$count jäljellä';
  }

  @override
  String get manageYourApp => 'Hallinnoi sovellustasi';

  @override
  String get willSyncAutomatically => 'synkronoidaan automaattisesti';

  @override
  String get promoCode => 'Tarjouskoodi';

  @override
  String get trackPersonalGoalsOnHomepage => 'Seuraa henkilökohtaisia tavoitteitasi etusivulla';

  @override
  String get memoryHistoryPartial =>
      'Osa muistojen historiasta ei ole saatavilla. Näytetään tähän mennessä saatu historia.';

  @override
  String get sharePublicLink => 'Jaa julkinen linkki';

  @override
  String get conversationTab => 'Keskustelu';

  @override
  String get backgroundModeDescription => 'Pidä Omi tallentamassa, vaikka sovellus olisi kokonaan suljettu.';

  @override
  String get pairingDescOmiDevkit =>
      'Paina painiketta kerran käynnistääksesi. LED vilkkuu violettina pariliitostilassa.';

  @override
  String get callStateFailed => 'Puhelu epaonnistui';

  @override
  String get githubRepositoryUrlHint => 'Linkki sovelluksesi lähdekoodin repositorioon';

  @override
  String get appIconLabel => 'App Icon';

  @override
  String get uninstallApp => 'Poista sovellus';

  @override
  String get confidenceReasonNeedsVoice => 'ei vielä ääninäytettä';

  @override
  String get couldNotLoadApiKeys => 'API-avaimia ei voitu ladata.';

  @override
  String get fetchingStableFirmware => 'Haetaan uusinta vakaata laiteohjelmistoa…';

  @override
  String get onDeviceModelDownloaded => 'Ladattu';

  @override
  String get noAPIKeys => 'Ei API-avaimia. Luo yksi aloittaaksesi.';

  @override
  String get phoneCallsUpsellFeature3 => 'Vastaanottajat näkevät oikean numerosi, eivät satunnaista';

  @override
  String get wrappedMovieRecs => 'Elokuvasuosituksia ystäville';

  @override
  String msgFilePickerError(String error) {
    return 'Virhe tiedostonvalitsimen avaamisessa: $error';
  }

  @override
  String get professionEntrepreneur => 'Yrittäjä';

  @override
  String get recent => 'Viimeisimmät';

  @override
  String get permissionDescCreateMemories => 'Tämä sovellus voi luoda uusia muistoja.';

  @override
  String get tapToComplete => 'Napauta viimeistelläksesi';

  @override
  String vocabularyWordCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count sanaa',
      one: '1 sana',
    );
    return '$_temp0';
  }

  @override
  String get deleteSyncedFilesMessage => 'Nämä tallenteet on jo synkronoitu puhelimeesi. Tätä ei voi kumota.';

  @override
  String get cancelConsequenceSpeakers => 'Ei voi tunnistaa puhujia.';

  @override
  String get aiGenFailedToGenerateApp => 'Sovelluksen luominen epäonnistui. Yritä uudelleen.';

  @override
  String get account => 'Tili';

  @override
  String get capabilityIntegrations => 'Integraatiot';

  @override
  String get voiceSettingsAskToTag => 'Pyydä minua merkitsemään äänet';

  @override
  String get chatAppsHeroTitle => 'Keskustele Omin kanssa siellä, missä muutenkin keskustelet';

  @override
  String get myApps => 'Minun luomani';

  @override
  String get deleteRecap => 'Poista yhteenveto';

  @override
  String get production => 'Tuotanto';

  @override
  String get phoneRecordingBlockedByPendantBatch =>
      'Lopeta Transcribe Later riipuksessa ennen kuin nauhoitat puhelimella.';

  @override
  String dataRateKbps(String rate) {
    return '$rate kbps';
  }

  @override
  String get createAKeyToGetStarted => 'Luo avain aloittaaksesi';

  @override
  String get pleaseSelectRating => 'Valitse arvio';

  @override
  String get pdfTranscriptExport => 'Litteraation vienti';

  @override
  String get newFolder => 'Uusi kansio';

  @override
  String get fallNotificationBody => 'Kaaduiitko?';

  @override
  String get scopeUserChat => 'Käyttäjän chat';

  @override
  String get tryDifferentSearchTerm => 'Kokeile eri hakusanaa';

  @override
  String get submit => 'Lähetä';

  @override
  String get deviceOnboardingVoiceReplySubtitle => 'Kun kysyt painikkeella, Omi voi lukea vastauksensa ääneen.';

  @override
  String get showOnLockScreen => 'Näytä lukitusnäytöllä';

  @override
  String get msgMaxImagesLimit => 'Voit valita enintään 4 kuvaa';

  @override
  String get wrappedOmiLifeRecap => 'Omi elämän yhteenveto';

  @override
  String get nextButton => 'Seuraava';

  @override
  String disconnectAppTitle(String appName) {
    return 'Katkaise yhteys palveluun $appName?';
  }

  @override
  String get updateReview => 'Päivitä arvostelu';

  @override
  String get noMemoriesInCategory => 'Tässä kategoriassa ei ole vielä muistoja';

  @override
  String get memoryDeleted => 'Muisto poistettu';

  @override
  String get connectOmiDevice => 'Yhdistä Omi-laite';

  @override
  String get professionSoftwareEngineer => 'Ohjelmistoinsinööri';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'Merkitse muut segmentit tältä puhujalta ($selected/$total)';
  }

  @override
  String get productName => 'Tuotteen nimi';

  @override
  String get permissionDeniedForAppleReminders => 'Käyttöoikeus Apple Muistutuksille evätty';

  @override
  String get allMemoriesAreNowPrivate => 'Kaikki muistot ovat nyt yksityisiä';

  @override
  String planSetToCancelOn(String date) {
    return 'Tilauksesi on asetettu peruuntumaan $date.\nTilaa uudelleen nyt säilyttääksesi edut - ei veloitusta ennen $date.';
  }

  @override
  String get deletePersonTitle => 'Poistetaanko henkilö?';

  @override
  String deleteItemConfirmation(String item) {
    return '$item poistetaan. Tätä ei voi perua.';
  }

  @override
  String get appleHealthConnectCta => 'Yhdistä Apple Healthiin';

  @override
  String segmentsPlural(String count) {
    return '$count segmenttiä';
  }

  @override
  String get syncCardDownloadingTitle => 'Ladataan laitteeltasi';

  @override
  String additionalSampleIndex(String index) {
    return 'Lisänäyte $index';
  }

  @override
  String get descriptionLabel => 'Kuvaus';

  @override
  String get failedToClearDueDate => 'Eräpäivän tyhjentäminen epäonnistui';

  @override
  String get timeout4HoursDesc => 'Lopeta keskustelu 4 tunnin hiljaisuuden jälkeen';

  @override
  String get noSyncedRecordingsYet => 'Ei vielä synkronoituja nauhoituksia';

  @override
  String dreamReportDropped(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count vanhempaa muutosta ohitettu',
      one: '1 vanhempi muutos ohitettu',
    );
    return '$_temp0';
  }

  @override
  String get claudeCode => 'Claude Code';

  @override
  String get noPendingRecordings => 'Ei odottavia tallenteita';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'Kerro meille, miten haluaisit, että sinut puhutellaan. Tämä auttaa personoimaan Omi-kokemuksesi.';

  @override
  String get updateSummaryWithNewNames => 'Päivitä yhteenveto uusilla nimillä';

  @override
  String get setWhenConversationsAutoEnd => 'Kuinka kauan Omi odottaa hiljaisuudessa ennen keskustelun päättämistä';

  @override
  String get successfullyConnectedGoogleTasks => 'Yhdistetty onnistuneesti Google Tasksiin!';

  @override
  String get confirmUpgrade => 'Vahvista päivitys';

  @override
  String get speechToTextProviderDesc => 'Valitse transkriptioon käytettävä palvelu';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Virhe yhdistettäessä Apple Watchiin: $error';
  }

  @override
  String get instagram => 'Instagram';

  @override
  String sampleNumber(int number) {
    return 'Näyte $number';
  }

  @override
  String get popularApps => 'Suositut sovellukset';

  @override
  String get micGainDescSlightlyBoosted => 'Hieman vahvistettu - normaalikäyttö';

  @override
  String get promptMustBeAtLeast10Characters => 'Kehotteen on oltava vähintään 10 merkkiä';

  @override
  String get chatAppsEntryRowSubtitle => 'Telegram, iMessage ja muut';

  @override
  String get estimatedSizeLabel => 'Arvioitu koko';

  @override
  String get mcpServerDesc => 'Yhdistä tekoälyavustajat tietoihisi';

  @override
  String get disconnectHistory => 'Katkaisuhistoria';

  @override
  String get downgradeLimitDelay => '5–7 sekunnin viive';

  @override
  String get msgSelectImagesGenericError => 'Virhe kuvien valinnassa. Yritä uudelleen.';

  @override
  String get audioPlaybackUnavailable => 'Äänitiedosto ei ole saatavilla toistettavaksi';

  @override
  String get byClickingConnectNow => 'Napsauttamalla \"Yhdistä nyt\" hyväksyt';

  @override
  String get signalStrength => 'Signaalin voimakkuus';

  @override
  String get tellUsPrimaryLanguage => 'Kerro meille ensisijainen kielesi';

  @override
  String get diagnosticsShareFailed => 'Diagnostiikan jakaminen epäonnistui. Yritä uudelleen.';

  @override
  String get createKeyToStart => 'Luo avain aloittaaksesi';

  @override
  String generatedBy(String appName) {
    return 'Luonut $appName';
  }

  @override
  String shareStatsListened(String minutes) {
    return '🎧 Kuunnellut $minutes minuuttia';
  }

  @override
  String get getOmiDevice => 'Hanki Omi-laite';

  @override
  String get newTask => 'Uusi tehtävä';

  @override
  String get conversationPrompt => 'Keskustelukehote';

  @override
  String get otaWifiConnected => 'Yhdistetty Wi-Fiin';

  @override
  String get dismiss => 'Hylkää';

  @override
  String get webhooks => 'Webhookit';

  @override
  String get raybanMetaCamera => 'Kamera';

  @override
  String get recapRegenerateNoConversations => 'Tänä päivänä ei ole keskusteluja yhteenvedettäväksi.';

  @override
  String pendantMinutesStored(int minutes) {
    return '~$minutes min tallennettu';
  }

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName yhteys katkaistu';
  }

  @override
  String get normal => 'Normaali';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch ei ole vielä tavoitettavissa. Varmista, että Omi-sovellus on auki kellossasi.';

  @override
  String get connectionGuide => 'Yhteysopas';

  @override
  String get syncStepProcessDesc => 'Omi muuttaa äänen keskusteluksi';

  @override
  String get couldNotLoadPlans => 'Saatavilla olevia tilauksia ei voitu ladata. Yritä uudelleen.';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '$used/$limit min käytetty tässä kuussa';
  }

  @override
  String get learnMoreLink => 'lue lisää';

  @override
  String get unpairDeviceDialogMessage =>
      'Tämä poistaa laitteen pariliitoksen, jotta se voidaan yhdistää toiseen puhelimeen. Sinun on siirryttävä Asetukset > Bluetooth ja unohdettava laite prosessin viimeistelemiseksi.';

  @override
  String get authFailedToRetrieveToken => 'Firebase-tunnuksen hakeminen epäonnistui, yritä uudelleen.';

  @override
  String get aiGenFailedToCreateApp => 'Sovelluksen luominen epäonnistui';

  @override
  String get appAndDeviceCopied => 'Sovelluksen ja laitteen tiedot kopioitu';

  @override
  String get noProcessedRecordings => 'Ei vielä käsiteltyjä tallenteita';

  @override
  String get transcriptTab => 'Litterointi';

  @override
  String get permissionDescReadConversations => 'Tämä sovellus voi käyttää keskustelujasi.';

  @override
  String get tryAnotherApp => 'Kokeile toista sovellusta';

  @override
  String get subscriptionSetToCancel => 'Tilauksesi on asetettu peruuntumaan jakson lopussa.';

  @override
  String chatAppsCodeExpiresIn(String time) {
    return 'Koodi vanhenee: $time';
  }

  @override
  String get authFailedToSignInWithApple => 'Kirjautuminen Applella epäonnistui, yritä uudelleen.';

  @override
  String get feedbackReasonIgnoredInstructions => 'Ei noudattanut ohjeita';

  @override
  String get startupFailedDetails => 'Tiedot';

  @override
  String get deleteMeetingScreenshotTitle => 'Poistetaanko kuvakaappaus?';

  @override
  String get chatAppsNotConnectedMessage => 'Tämän chat-sovelluksen yhteys katkaistiin.';

  @override
  String get aboutOmiApiKeys => 'Tietoja Omi API-avaimista';

  @override
  String get tiktok => 'TikTok';

  @override
  String get maxFilesLimit => 'Voit ladata vain 4 tiedostoa kerrallaan';

  @override
  String get legalNotice =>
      'Oikeudellinen huomautus: Äänidatan nauhoittamisen ja tallentamisen laillisuus voi vaihdella sijaintisi ja tämän ominaisuuden käyttötavan mukaan. Vastaat paikallisten lakien ja määräysten noudattamisesta.';

  @override
  String get wrappedYourTopDays => 'Parhaat päiväsi';

  @override
  String get addMcpServer => 'Lisää MCP-palvelin';

  @override
  String publicAppsCount(String count) {
    return 'Julkiset sovellukset ($count)';
  }

  @override
  String get noExternalAppsHaveAccess => 'Ulkoisilla sovelluksilla ei ole pääsyä tietoihisi.';

  @override
  String get captureStarting => 'Käynnistetään…';

  @override
  String get downloadingAudioProgress => 'Ladataan ääntä';

  @override
  String get audioBytes => 'Äänitavut';

  @override
  String batteryLevelSemantics(int level) {
    return 'Akku $level %';
  }

  @override
  String captureRecordedBy(String devices) {
    return 'Tallentanut $devices';
  }

  @override
  String get chatAppsRepliesOnlyNote => 'Omi vastaa vain sinulle. Se ei koskaan lähetä viestiä ensin.';

  @override
  String get hideTranscript => 'Piilota litterointi';

  @override
  String get permissionReadConversations => 'Lue keskusteluja';

  @override
  String get installed => 'Asennettu';

  @override
  String get paymentEnterValidAmount => 'Syötä kelvollinen summa';

  @override
  String get sttLanguageOverride => 'Ohita';

  @override
  String get appInterfaceSectionTitle => 'Sovelluksen käyttöliittymä';

  @override
  String get searchLanguages => 'Hae kieliä';

  @override
  String get otherSource => 'Muu';

  @override
  String get pairingDescOmiGlass => 'Pidä sivupainiketta painettuna 3 sekuntia käynnistääksesi.';

  @override
  String get signOut => 'Kirjaudu Ulos';

  @override
  String shareStatsWords(String words) {
    return '🧠 Ymmärtänyt $words sanaa';
  }

  @override
  String verifiedDaysAgo(int days) {
    return 'Vahvistettu ${days}pv sitten';
  }

  @override
  String get captureModeLater => 'Myöhemmin';

  @override
  String get enableMoreApps => 'Ota käyttöön lisää sovelluksia';

  @override
  String get frequencyDescBalanced => 'Hyödyllisiä ehdotuksia, noin 5–8 päivässä';

  @override
  String get startYourFirstRecording => 'Aloita ensimmäinen tallennus';

  @override
  String get transcriptionPausedReconnecting => 'Nauhoittaa yhä — yhdistetään uudelleen puheentunnistukseen…';

  @override
  String get basicPlan => 'Ilmaispaketti';

  @override
  String get user => 'Käyttäjä';

  @override
  String get pinPersonDescription =>
      'Kiinnitetyt ihmiset pysyvät Ihmiset-listasi yläosassa, eikä Siivous poista niitä.';

  @override
  String get reviewProject => 'Projekti';

  @override
  String get keyboardShortcuts => 'Pikanäppäimet';

  @override
  String get diagnosticsFailBadge => 'Epäonnistui';

  @override
  String get debugLogCleared => 'Vianjäljitysloki tyhjennetty';

  @override
  String get errorConnectingToStripe => 'Virhe yhdistettäessä Stripeen! Yritä myöhemmin uudelleen.';

  @override
  String get tapPlusToStartRecording => 'Aloita tallennus napauttamalla tallennuspainiketta';

  @override
  String get permissionBlockedHint => 'Poistettu käytöstä asetuksissa. Salli se siellä, jotta voit käyttää tätä.';

  @override
  String get downloadingAudio => 'Ladataan ääntä…';

  @override
  String failedToRevokeApiKey(String error) {
    return 'API-avaimen peruuttaminen epäonnistui: $error';
  }

  @override
  String largeTimeGapDetected(String gap) {
    return 'Havaittu suuri aikaväli ($gap)';
  }

  @override
  String get customFirmwareWarning =>
      'Mukautettu laiteohjelmisto voi rikkoa laitteesi. Varmista, että kyseessä on kelvollinen Omi-laiteohjelmistoversio, äläkä katkaise yhteyttä päivityksen aikana.';

  @override
  String get wrapped2025 => 'Katsaus 2025';

  @override
  String get showApiKey => 'Näytä API-avain';

  @override
  String get agreeAndContinue => 'Hyväksy ja jatka';

  @override
  String get connectExternalAiTools => 'Yhdistä ulkoiset tekoälytyökalut';

  @override
  String get batteryFullyChargedTitle => 'Omi on ladattu täyteen';

  @override
  String get appReEnableFailedTitle => 'Käyttöönotto epäonnistui';

  @override
  String get onboardingYourName => 'Nimesi';

  @override
  String get searchApps => 'Etsi sovelluksia';

  @override
  String get weak => 'Heikko';

  @override
  String get tellUsMore => 'Kerro meille lisää (valinnainen)';

  @override
  String confidenceReasonPicked(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Valittu $count ehdotuksessa',
      one: 'Valittu 1 ehdotuksessa',
    );
    return '$_temp0';
  }

  @override
  String chatAppsDisconnectFooter(String app) {
    return 'Yhteyden katkaisu poistaa historian, jonka Omi säilyttää sovellukselle $app.';
  }

  @override
  String get selectAll => 'Valitse kaikki';

  @override
  String get deleteActionItemConfirmation => 'Poistetaanko tämä tehtävä? Tätä ei voi perua.';

  @override
  String get categoryTravel => 'Matkailu';

  @override
  String get lowestRating => 'Matalin arvio';

  @override
  String get tasksEmptyStateMessage => 'Aloita keskustelu luodaksesi tehtävän.';

  @override
  String get unpairAndForget => 'Pura laitepari ja unohda laite';

  @override
  String get listeningForAudio => 'Kuunnellaan ääntä…';

  @override
  String get processedStatus => 'Käsitelty';

  @override
  String get wrappedTheHardPart => 'Vaikea osuus';

  @override
  String chatAppsReplyThereAnytime(String app) {
    return 'Voit lähettää Omille viestin sovelluksessa $app milloin tahansa.';
  }

  @override
  String get upgradePlan => 'Päivitä suunnitelma';

  @override
  String get onboardingRatingPromptYes => 'Kyllä';

  @override
  String timeCompactMins(int count) {
    return '${count}m';
  }

  @override
  String get changeTheConversationTitle => 'Muuta keskustelun otsikkoa';

  @override
  String get accountGroup => 'Tili';

  @override
  String get updatingYourApp => 'Päivitetään sovellustasi';

  @override
  String get microphone => 'Mikrofoni';

  @override
  String get suggestQuestionsAfterConversations => 'Ehdota kysymyksiä keskustelujen jälkeen';

  @override
  String get failedToTranscribeAudio => 'Äänen litterointi epäonnistui';

  @override
  String get unstarConversation => 'Poista keskustelun tähti';

  @override
  String get speakerTagPromptNotMe => 'En ole minä';

  @override
  String get confidenceReasonCorrected => 'Korjasit sen vastaavuuden';

  @override
  String get peopleSearchPlaceholder => 'Etsi henkilöitä';

  @override
  String get syncStatusUnsupportedAudio => 'Ääntä ei voitu lukea — ei voi synkronoida';

  @override
  String get indentTask => 'Sisennä';

  @override
  String get selectApp => 'Valitse sovellus';

  @override
  String get updatePayPal => 'Päivitä PayPal';

  @override
  String get enterNameError => 'Anna nimesi';

  @override
  String get exportAllData => 'Vie kaikki tiedot';

  @override
  String premiumMinsLeft(int count) {
    return '$count premium-minuuttia jäljellä.';
  }

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName asetettu oletusyhteenvetosovellukseksi';
  }

  @override
  String get recordingStartedSuccessfully => 'Nauhoitus aloitettu onnistuneesti!';

  @override
  String get trySomethingLike => 'Kokeile jotain tällaista…';

  @override
  String get chatAppsTryAsking => 'Kokeile kysyä';

  @override
  String get categoryEntertainment => 'Viihde';

  @override
  String get checksForAudioFiles => 'Tarkistaa äänitiedostot SD-kortilla';

  @override
  String get everyoneHeader => 'Kaikki';

  @override
  String get clearMemoryButton => 'Tyhjennä muisti';

  @override
  String confidenceReasonLabeled(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Nimesit $count kertaa',
      one: 'Nimesit kerran',
    );
    return '$_temp0';
  }

  @override
  String get selectLogFile => 'Valitse lokitiedosto';

  @override
  String get chatAppsTelegramStepReturn => 'Palaa tänne. Vahvistamme, että se onnistui.';

  @override
  String get discordMemberCount => 'Yli 8000 jäsentä Discordissa';

  @override
  String get public => 'Julkinen';

  @override
  String get outdentTask => 'Poista sisennys';

  @override
  String get statusProcessing => 'Käsitellään';

  @override
  String get useFreePlan => 'Käytä ilmaista tilausta';

  @override
  String get emailLabel => 'Sähköposti';

  @override
  String get statusCallInProgress => 'Puhelu kaynnissa';

  @override
  String get shortcuts => 'Pikanäppäimet';

  @override
  String get reviewRecentChanges => 'Viimeaikaiset muutokset';

  @override
  String get raybanMetaAudioOnlyExplanation =>
      'Tämä Omi-versio voi käyttää lasiesi mikrofonia Bluetoothin kautta. Valokuvien ottaminen vaatii Omin Meta-kehittäjäversion.';

  @override
  String get wrappedDaysActiveLabel => 'aktiivista päivää';

  @override
  String get installOmiOnAppleWatch => 'Asenna Omi\nApple Watchiin';

  @override
  String tasksCountLabel(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count tehtävää',
      one: '1 tehtävä',
    );
    return '$_temp0';
  }

  @override
  String get confidenceReasonVoiceReady => 'ääni tallennettu';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Poistetaanko $count valittua tehtävää$s?';
  }

  @override
  String get sdCardSync => 'SD-kortin synkronointi';

  @override
  String get timeout4Hours => '4 tuntia';

  @override
  String get chatAppsTitle => 'Chat-sovellukset';

  @override
  String get repeatPasswordLabel => 'Toista salasana';

  @override
  String get skip => 'Ohita';

  @override
  String get phoneNoVerifiedNumbersTitle => 'Ei vahvistettuja numeroita';

  @override
  String get connectionLost => 'Yhteys katkesi';

  @override
  String get photoDiscardedMessage => 'Tämä kuva hylättiin, koska se ei ollut merkittävä.';

  @override
  String get weekdayFri => 'Pe';

  @override
  String get moveToFolder => 'Siirrä kansioon';

  @override
  String get updateNow => 'Päivitä nyt';

  @override
  String get failedToUpdateActionItem => 'Tehtävän päivitys epäonnistui';

  @override
  String get transferRequiredDescription =>
      'Tämä nauhoitus on tallennettu laitteesi SD-kortille. Siirrä se puhelimeesi toistaaksesi tai jakaaksesi.';

  @override
  String get checkingForUpdates => 'Tarkistetaan päivityksiä';

  @override
  String get importTranscriptFilesDescription => 'Valitse SRT-, VTT- tai TXT-litteroinnit tai niitä sisältävä ZIP';

  @override
  String get listenToSpeechProfile => 'Kuuntele ääniprofiiliani ➡️';

  @override
  String get deleteRecapConfirmBody =>
      'Yhteenveto poistetaan pysyvästi. Tuon päivän alkuperäiset keskustelut säilyvät.';

  @override
  String get copyLogs => 'Kopioi lokit';

  @override
  String get wrappedFunniestMoment => 'Hauskin';

  @override
  String get onboardingMicrophoneRequired => 'Mikrofonilupa vaaditaan tallennukseen.';

  @override
  String get whoIsItTitle => 'Kuka se on?';

  @override
  String dreamReportRunsLeft(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count manuaalista ajoa jäljellä tänään',
      one: '1 manuaalinen ajo jäljellä tänään',
    );
    return '$_temp0';
  }

  @override
  String get modified => 'Muokattu';

  @override
  String get actionCreateConversations => 'Luo keskusteluja';

  @override
  String get chatAssistantsTitle => 'Chat-avustajat';

  @override
  String get connectionError => 'Yhteysvirhe';

  @override
  String get chooseFromGallery => 'Valitse galleriasta';

  @override
  String get summaryPrompt => 'Yhteenvetokehote';

  @override
  String get whatWentWrong => 'Mikä meni pieleen?';

  @override
  String get keepGoingGreat => 'Jatka, pärjäät loistavasti';

  @override
  String get deviceConnecting => 'Yhdistetään…';

  @override
  String get downgradeLimitBattery => '7-kertainen akunkulutus';

  @override
  String get privateMemories => 'Yksityiset muistot';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get aiGenPleaseEnterDescription => 'Anna sovelluksellesi kuvaus';

  @override
  String get enterLiveSttWebsocket => 'Kirjoita live-STT WebSocket -päätepisteesi';

  @override
  String processingOnServerProgress(int current, int total) {
    return 'Käsitellään… $current/$total segmenttiä';
  }

  @override
  String linkedToEvent(String title) {
    return 'Linkitetty tapahtumaan ”$title”';
  }

  @override
  String get failedToSaveCheckConnection => 'Tallennus epäonnistui. Tarkista yhteytesi.';

  @override
  String get deviceOnboardingContinue => 'Jatka';

  @override
  String get pairedToAnotherPhone => 'Yhdistetty toiseen puhelimeen';

  @override
  String get syncingYourRecordings => 'Synkronoidaan tallenteitasi';

  @override
  String get manual => 'Manuaalinen';

  @override
  String get oneMonthAgo => 'kuukausi sitten';

  @override
  String get clearChatConfirm => 'Kaikki tämän keskustelun viestit poistetaan. Tätä ei voi perua.';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'Kaikki avainta \"$keyName\" käyttävät menettävät pääsyn. Tätä ei voi perua.';
  }

  @override
  String get vadGateDescription => 'Ohittaa hiljaisen äänen ennen litterointia kustannusten vähentämiseksi.';

  @override
  String get dreamReportScheduled => 'Ajastettu';

  @override
  String get audioDataReceived => 'Ääniaineisto vastaanotettu';

  @override
  String get pro => 'Pro';

  @override
  String get micGainDescMuted => 'Mikrofoni on vaimennettu';

  @override
  String get enableLocationDescription => 'Sijaintilupa tarvitaan lähellä olevien Bluetooth-laitteiden löytämiseen.';

  @override
  String get conversationTitleUpdatedSuccessfully => 'Keskustelun otsikko päivitetty onnistuneesti';

  @override
  String get syncStepUpload => 'Synkronoi';

  @override
  String get removeScreenshot => 'Poista kuvakaappaus';

  @override
  String get failedToStartCall => 'Puhelun aloitus epaonnistui';

  @override
  String get deviceDiagnosticsUploadDescription =>
      'Review the diagnostics JSON below. It includes your device identifier, connection history, battery readings, firmware diagnostics, and BLE events. No audio or transcripts are included.';

  @override
  String get pairingTitleFieldy => 'Aseta Fieldy pariliitostilaan';

  @override
  String get autoDeletesAfterThreeDays => 'Poistetaan automaattisesti 3 päivän kuluttua.';

  @override
  String get wrappedDaysActive => 'aktiivista päivää';

  @override
  String get failedToDeleteActionItem => 'Tehtävän poisto epäonnistui';

  @override
  String get connect => 'Yhdistä';

  @override
  String get unableToDeleteConversation => 'Keskustelun poisto ei onnistu';

  @override
  String get clearChatAction => 'Tyhjennä keskustelu';

  @override
  String get memoryThisIphone => 'Tämä iPhone';

  @override
  String get captureCustomSttUnreachableDetail =>
      'Omaa puheentunnistuspalveluasi ei tavoiteta. Omi säilyttää äänen tässä puhelimessa ja lähettää sen, kun palvelu palaa. Mitään ei menetetä.';

  @override
  String get feedbackGiveFeedback => 'Give feedback';

  @override
  String failedToUpdateSettings(String error) {
    return 'Asetusten päivitys epäonnistui: $error';
  }

  @override
  String get deleteRecordingConfirmation => 'Tätä ei voi perua.';

  @override
  String get advancedSettings => 'Lisäasetukset';

  @override
  String get transcriptionNoAudio => 'Transkriptio ei vastaanota ääntä';

  @override
  String deletePeopleCountAction(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Poista $count henkilöä',
      one: 'Poista 1 henkilö',
    );
    return '$_temp0';
  }

  @override
  String get speakerSuggestionAppliesToSpeaker => 'Koskee kaikkia tämän puhujan rivejä';

  @override
  String get deviceNotResponding => 'Laite ei vastannut. Yritä uudelleen.';

  @override
  String get everythingSynced => 'Kaikki on jo synkronoitu.';

  @override
  String get onDeviceModelDownloadFailedDesc => 'Whisper-mallin lataaminen epäonnistui. Yritä uudelleen.';

  @override
  String fairUseBannerStatus(String status) {
    return 'Reilu käyttö: $status';
  }

  @override
  String tasksDeleteSelected(int count) {
    return 'Poista $count tehtävä(ä)';
  }

  @override
  String get connectPaymentMethodInfo =>
      'Yhdistä maksutapa alla aloittaaksesi maksujen vastaanottamisen sovelluksistasi.';

  @override
  String get conversationNotFoundOrDeleted => 'Keskustelua ei löytynyt tai se on poistettu';

  @override
  String leaveFlowStepOf(int current, int total) {
    return 'Vaihe $current/$total';
  }

  @override
  String get deleteTypeToConfirm => 'Kirjoita DELETE vahvistaaksesi';

  @override
  String get clearMemoryTitle => 'Tyhjennä Omin muisti';

  @override
  String get triggerConversationCreation => 'Keskustelun luominen';

  @override
  String get flashCustomFirmware => 'Asenna mukautettu laiteohjelmisto';

  @override
  String shareWithContactCount(int count) {
    return 'Jaa $count yhteystiedolle';
  }

  @override
  String get customChatbotPersonality => 'Mukautettu chatbot-persoonallisuus';

  @override
  String get betaTesterNotice =>
      'Olet tämän sovelluksen beta-testaaja. Se ei ole vielä julkinen. Se tulee julkiseksi hyväksynnän jälkeen.';

  @override
  String get tomorrow => 'Huomenna';

  @override
  String get createdLabel => 'LUOTU';

  @override
  String get searchPeople => 'Etsi ihmisiä';

  @override
  String get cancelled => 'Peruutettu';

  @override
  String basicPlanDesc(int limit) {
    return 'Pakettisi sisältää $limit ilmaisminuuttia kuukaudessa. Päivitä saadaksesi rajoittamattoman.';
  }

  @override
  String get editMemoryTitle => 'Muokkaa muistoa';

  @override
  String get whatDoYouWantToKnow => 'Mitä haluat tietää?';

  @override
  String get confidenceFootnote =>
      'Sinun tekemilläsi merkinnöillä ja vahvistuksilla on eniten painoa. Automaattisilla merkinnöillä on vähän painoa, kunnes vahvistat ne.';

  @override
  String get exportFailedTryAgain => 'Vienti epäonnistui. Yritä uudelleen.';

  @override
  String get addAppPhotosPermissionDenied => 'Valokuvalupa evätty. Salli pääsy valokuviin';

  @override
  String get filterByDate => 'Suodata päivämäärän mukaan';

  @override
  String get chatAppsDoesFiles => 'Lähettää ja vastaanottaa tiedostoja, kuvia ja ääniviestejä';

  @override
  String get deleteKnowledgeGraphTitle => 'Poista tietograafi?';

  @override
  String get reloadingConversations => 'Ladataan keskusteluja uudelleen…';

  @override
  String get aiGenPleaseGenerateAppFirst => 'Luo ensin sovellus';

  @override
  String get completeYourUpgrade => 'Viimeistele päivityksesi';

  @override
  String get capturePendantDisconnectedDetail =>
      'Riipus menetti yhteyden tähän puhelimeen. Omi yhdistää itsestään uudelleen, kun riipus on päällä ja lähellä. Kaikki tätä ennen tallennettu on tallessa.';

  @override
  String get greetingMorning => 'Hyvää huomenta';

  @override
  String get thanksForYourFeedback => 'Kiitos palautteestasi!';

  @override
  String get deleteActionItemConfirmMessage => 'Poistetaanko tämä tehtävä?';

  @override
  String get syncCardProcessing => 'Käsitellään Omissa…';

  @override
  String get chatAppsTryWeek => 'Tiivistä viikkoni kolmeen riviin';

  @override
  String get recordWithPhoneMicSubtitle => 'Nauhoita ja litteroi tämän puhelimen mikrofonilla';

  @override
  String get notifications => 'Ilmoitukset';

  @override
  String get annualPlanStartsAutomatically => 'Vuositilauksesi alkaa automaattisesti, kun kuukausitilauksesi päättyy.';

  @override
  String get unpairDialogMessage =>
      'Tämä purkaa laiteparin, jotta se voidaan yhdistää toiseen puhelimeen. Sinun on siirryttävä kohtaan Asetukset > Bluetooth ja unohdettava laite prosessin viimeistelemiseksi.';

  @override
  String get pairingTitleBee => 'Aseta Bee pariliitostilaan';

  @override
  String conversationCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count keskustelua',
      one: '1 keskustelu',
    );
    return '$_temp0';
  }

  @override
  String get syncStatusWaiting => 'Odottaa synkronointia';

  @override
  String get validWebsocketUrlRequired => 'Kelvollinen WebSocket-URL vaaditaan (wss://)';

  @override
  String get improveSpeechProfile => 'Paranna puheprofiiliasi';

  @override
  String entityWaitingOn(String name) {
    return 'Odotetaan: $name';
  }

  @override
  String get feedbackReasonTooVerbose => 'Liian monisanainen';

  @override
  String chatAppsChannelFooter(String app) {
    return '$app-keskustelusi pysyvät sovelluksessa $app. Omi tietää silti, mistä olette puhuneet sovelluksessa ja muissa chat-sovelluksissasi.';
  }

  @override
  String get wrappedNoDataAvailable => 'Ei tietoja saatavilla';

  @override
  String deviceOnboardingAllSetReplayHint(String settings, String deviceSettings, String deviceTutorial) {
    return 'Toista tämä kiertue milloin tahansa numerossa $settings › $deviceSettings › $deviceTutorial';
  }

  @override
  String get createAKey => 'Luo avain';

  @override
  String get successfullyConnectedNotion => 'Yhdistetty onnistuneesti Notioniin!';

  @override
  String get captureMicInterruptedDetail =>
      'Puhelu tai toinen sovellus otti mikrofonin, joten Omi ei kuule juuri nyt. Omi jatkaa itsestään, kun mikrofoni vapautuu. Kaikki tätä ennen tallennettu on tallessa.';

  @override
  String get onboardingScreenCaptureDenied =>
      'Näytönkaappauslupa evätty. Myönnä lupa kohdassa Järjestelmäasetukset > Tietosuoja ja turvallisuus > Näytön tallennus.';

  @override
  String get settingUp => 'Asetetaan…';

  @override
  String get frequencyLow => 'Matala';

  @override
  String get sttFilterAuto => 'Automaattinen';

  @override
  String get voiceQuestionNoSpeech => 'En saanut selvää — yritä uudelleen';

  @override
  String get stripeRecommendation =>
      'Jos Stripe on saatavilla maassasi, suosittelemme vahvasti sen käyttöä nopeampien ja helpompien maksujen saamiseksi.';

  @override
  String get confirmed => 'Vahvistettu!';

  @override
  String get deletePendingFilesWarning =>
      'Näitä tallenteita EI ole synkronoitu puhelimeesi ja ne menetetään pysyvästi. Tätä ei voi kumota.';

  @override
  String get removeFilter => 'Poista Suodatin';

  @override
  String get downloadModel => 'Lataa malli';

  @override
  String get performanceReduced => 'Suorituskyky voi olla alentunut';

  @override
  String get hostRequired => 'Isäntä vaaditaan';

  @override
  String get alreadyBestValuePlan => 'Sinulla on jo paras hinta-laatusuhteen tilaus. Muutoksia ei tarvita.';

  @override
  String preparingModel(String model) {
    return 'Valmistellaan $model…';
  }

  @override
  String get sendTranscript => 'Lähetä litterointi';

  @override
  String get howItWorksTitle => 'Miten se toimii?';

  @override
  String get filterBySpeaker => 'Suodata puhujan mukaan';

  @override
  String get addAppSubmittedSuccess => 'Sovellus lähetetty onnistuneesti 🚀';

  @override
  String olderIphoneModelDetected(String model) {
    return 'Havaittu malli: $model (vanhempi kuin iPhone XS). Laitteella tapahtuva tunnistus voi olla hitaampaa.';
  }

  @override
  String get chatAppsWhatsAppTitle => 'WhatsApp on tulossa';

  @override
  String get syncingDeveloperSettings => 'Synkronoidaan kehittäjäasetuksia…';

  @override
  String get enterWifiPassword => 'Syötä WiFi-salasana';

  @override
  String get failedToUpdateBaselineStatus => 'Tätä muistoa ei voitu päivittää. Yritä uudelleen.';

  @override
  String get joinCommunity => 'Liity yhteisöön!';

  @override
  String get helpOrInquiries => 'Apua tai kysymyksiä?';

  @override
  String get enable => 'Ota käyttöön';

  @override
  String get deviceForgottenMessage => 'Laite unohdettu';

  @override
  String diagnosticsSincePairingSummary(int drops, int failed) {
    return 'Parituksen jälkeen: katkoksia $drops, epäonnistuneita yhteyksiä $failed.';
  }

  @override
  String confidenceSummaryConfirmed(String name) {
    return 'Omi tunnistaa henkilön $name äänen, ja olet vahvistanut sen.';
  }

  @override
  String migratingToProtection(String level) {
    return 'Siirretään $level-suojaukseen…';
  }

  @override
  String get managePlan => 'Hallitse pakettia';

  @override
  String get synced => 'Synkronoitu';

  @override
  String get failedToMoveConversations => 'Keskusteluja ei voitu siirtää';

  @override
  String get monthMar => 'Maalis';

  @override
  String get timePM => 'IP';

  @override
  String get debugLogsAutoDelete => 'Poistetaan automaattisesti 3 päivän kuluttua.';

  @override
  String get linkedIn => 'LinkedIn';

  @override
  String speakerLabelVoiceDetail(String state, String name) {
    String _temp0 = intl.Intl.selectLogic(
      state,
      {
        'learned': 'Omi tunnistaa henkilön $name ensi kerralla.',
        'pending': 'Tämä kestää muutaman sekunnin.',
        'disabled': 'Ota äänten tallennus käyttöön asetuksissa, jotta Omi voi tunnistaa henkilön $name.',
        'other': 'Omi tarvitsee lisää selkeää puhetta henkilöltä $name ja yrittää edelleen.',
      },
    );
    return '$_temp0';
  }

  @override
  String get authUnexpectedError => 'Odottamaton virhe kirjautuessa, yritä uudelleen';

  @override
  String disconnectAppMessage(String appName) {
    return 'Voit yhdistää palvelun $appName uudelleen milloin tahansa.';
  }

  @override
  String get pendantPausedResumesWhenYouFinish => 'Riipus tauolla · jatkuu, kun lopetat';

  @override
  String get sendToSupport => 'Send to support';

  @override
  String get fairUseBudgetExhausted => 'Daily transcription limit reached';

  @override
  String evidenceAutoConfirmed(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Vahvistettu $count automaattista merkintää',
      one: 'Vahvistettu 1 automaattinen merkintä',
    );
    return '$_temp0';
  }

  @override
  String get otaWifiConnecting => 'Yhdistetään Wi-Fiin…';

  @override
  String starFilterLabel(int count) {
    return '$count tähti';
  }

  @override
  String get disconnectDevice => 'Katkaise laitteen yhteys';

  @override
  String get installsCount => 'Asennukset';

  @override
  String captureStatusWithSource(String status, String source) {
    return '$status · $source';
  }

  @override
  String get pairingTitleOmiGlass => 'Käynnistä Omi Glass';

  @override
  String get setActive => 'Aseta aktiiviseksi';

  @override
  String get showShortConversations => 'Näytä lyhyet keskustelut';

  @override
  String get reviewNotSure => 'En ole varma';

  @override
  String msgCameraAccessError(String error) {
    return 'Virhe kameraan pääsyssä: $error';
  }

  @override
  String get quickActionAskOmi => 'Kysy Omilta mitä tahansa';

  @override
  String get dreamReportTimedOut => 'Pysähtyi aikarajaan';

  @override
  String get chooseYourLanguage => 'Valitse kielesi';

  @override
  String get unableToDetermineFirmwareVersion => 'Nykyistä laiteohjelmistoversiota ei voida määrittää';

  @override
  String get addAppEnterConversationPrompt => 'Syötä keskustelukehote sovelluksellesi';

  @override
  String get readScope => 'Luku';

  @override
  String get selectALanguage => 'Valitse kieli';

  @override
  String get otherTemplates => 'Muut mallit';

  @override
  String get speechProfileTopicGoal => 'Mikä on pitkän aikavälin tavoitteesi?';

  @override
  String get rayBanMetaMicPickerTitle => 'Valitse Ray-Ban Meta -mikrofoni';

  @override
  String meetingNotesSubject(String title) {
    return 'Muistiinpanot: $title';
  }

  @override
  String get feedbackTitleMissingFeatures => 'Mitä ominaisuuksia kaipaat?';

  @override
  String get modelReady => 'Malli valmis';

  @override
  String todayAtTime(String time) {
    return 'Tänään klo $time';
  }

  @override
  String get deleteAccountPermanently => 'Poista tili pysyvästi';

  @override
  String get updateStripeDetails => 'Päivitä Stripe-tiedot';

  @override
  String get voiceResponseHeadphonesOnly => 'Vain kuulokkeet';

  @override
  String get deviceOnboardingEndConversation => 'Lopeta keskustelu';

  @override
  String openingApp(String appName) {
    return 'Avataan $appName…';
  }

  @override
  String get submitAppPublicDescription =>
      'Sovelluksesi tarkistetaan ja julkaistaan. Voit alkaa käyttää sitä heti, jopa tarkistuksen aikana!';

  @override
  String connectToAppTitle(String appName) {
    return 'Yhdistä palveluun $appName';
  }

  @override
  String get timeout10MinutesDesc => 'Lopeta keskustelu 10 minuutin hiljaisuuden jälkeen';

  @override
  String get googleCalendar => 'Google Kalenteri';

  @override
  String get initializing => 'Alustetaan…';

  @override
  String get noMessagesYet => 'Ei vielä viestejä!\nMikset aloittaisi keskustelua?';

  @override
  String get chatAppsLoadFailed => 'Chat-sovelluksia ei voitu ladata. Yritä uudelleen.';

  @override
  String get tasksLater => 'Myöhemmin';

  @override
  String get speakerLabelUnknown => 'Tuntematon';

  @override
  String get appTitle => 'Omi';

  @override
  String get noModelDownloadRequired =>
      'Laitteesi natiivi puheentunnistusmoottori on käytössä. Mallin lataus ei ole tarpeen.';

  @override
  String get authenticationFailed => 'Todennus epäonnistui. Yritä uudelleen.';

  @override
  String get defaultRepoSaved => 'Oletusrepositorio tallennettu';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'Virhe pikkukuvan valinnassa: $error';
  }

  @override
  String get captureRecordingSeparateTitle => 'Erotetaanko tämä tallenne?';

  @override
  String get back => 'Takaisin';

  @override
  String get preparingAudio => 'Valmistellaan ääntä';

  @override
  String get noAutoMemories => 'Ei vielä automaattisesti poimittuja muistoja';

  @override
  String get allDone => 'Kaikki valmista!';

  @override
  String get msgReadingMemories => 'Luetaan muistojasi…';

  @override
  String get worksOnDesktop => 'Toimii tietokoneella';

  @override
  String get displayOptions => 'Näyttövaihtoehdot';

  @override
  String get installApp => 'Asenna sovellus';

  @override
  String get stop => 'Pysäytä';

  @override
  String get grantPermissions => 'Myönnä luvat';

  @override
  String get at => 'klo';

  @override
  String get checkInternetConnection => 'Tarkista internetyhteytesi';

  @override
  String get actionItems => 'Tehtävät';

  @override
  String get nextDay => 'Seuraava päivä';

  @override
  String get syncStatusFailed => 'Epäonnistui — napauta Yritä uudelleen';

  @override
  String get saveCredentials => 'Tallenna tunnukset';

  @override
  String get peopleRecent => 'Viimeaikaiset';

  @override
  String get bringYourOwn => 'Tuo omasi';

  @override
  String get cancelConsequenceBattery => '7x enemmän akunkäyttöä (laitteella käsittely)';

  @override
  String get copyMessage => 'Kopioi viesti';

  @override
  String get annualSubscriptionStarts => '12 kuukauden vuositilauksesi alkaa automaattisesti veloituksen jälkeen';

  @override
  String get deleteImportedData => 'Poista tuodut tiedot';

  @override
  String get chatLimitReachedUpgrade => 'Chat-raja saavutettu. Päivitä saadaksesi lisää viestejä.';

  @override
  String get whatsNew => 'Uutta';

  @override
  String get omiTraining => 'Omi-koulutus';

  @override
  String get wrappedMyBuddies => 'Ystäväni';

  @override
  String get keepRecording => 'Jatka nauhoitusta';

  @override
  String get suggestedEvent => 'Ehdotettu';

  @override
  String get name => 'Nimi';

  @override
  String get screenRecordingDescription =>
      'Omi tarvitsee näytön tallennusluvan tallentaakseen järjestelmän ääntä selainpohjaisista kokouksistasi.';

  @override
  String get improveConnectionTitle => 'Paranna yhteyttä';

  @override
  String get syncProcessingBackgroundHint => 'Tämä jatkuu taustalla — voit poistua tästä näkymästä.';

  @override
  String get wrappedYourTopDaysBadge => 'Parhaat päiväsi';

  @override
  String get noPeopleYet => 'Ei vielä henkilöitä';

  @override
  String summaryGeneratedForDate(String date) {
    return 'Yhteenveto luotu päivälle $date';
  }

  @override
  String get searchTranscriptOrSummary => 'Hae transkriptiosta tai yhteenvedosta';

  @override
  String get memoryDetailsTitle => 'Muisto';

  @override
  String get chatPersonality => 'Chat-persoonallisuus';

  @override
  String get release => 'Vapauta';

  @override
  String removeVocabularyWord(String word) {
    return 'Poista $word';
  }

  @override
  String get onboardingLanguage => 'Kieli';

  @override
  String get wrappedYouDidItEmoji => 'Teit sen! 🎉';

  @override
  String get syncInProgress => 'Synkronointi käynnissä';

  @override
  String get wrappedCouldntStopTalkingAbout => 'En voinut lopettaa puhumista';

  @override
  String get chooseSummarizationApp => 'Valitse yhteenvetosovellus';

  @override
  String etaLabel(String time) {
    return 'ETA: $time';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'Jos teet $item julkiseksi, kaikki voivat käyttää sitä';
  }

  @override
  String get phoneCallsUpsellFeature2 => 'Automaattiset puheluyhteenvedot ja tehtävät';

  @override
  String get freemiumLimitsIntro =>
      'Omi on ilmainen, mutta ilmaisversiossa on rajoituksia, jotka vaikuttavat kokemukseesi:';

  @override
  String get nameLabel => 'Nimi';

  @override
  String get shortConversationThresholdSubtitle =>
      'Tätä lyhyemmät keskustelut piilotetaan, ellei niitä ole otettu käyttöön yllä';

  @override
  String get captureMicInUseElsewhere => 'Toinen sovellus käyttää mikrofonia';

  @override
  String get selectChatAssistant => 'Valitse chat-assistentti';

  @override
  String get transferRequired => 'Siirto vaaditaan';

  @override
  String get unlimitedChatThisMonth => 'Rajoittamattomasti chat-viestejä tässä kuussa';

  @override
  String get backgroundModeUnavailable =>
      'Taustatila ei ole käytettävissä, koska yhteensopivaa laitetta ei ole yhdistetty. Yhdistä Omi-, OpenGlass- tai Friend Pendant -laite käyttääksesi tätä ominaisuutta.';

  @override
  String get importConfiguration => 'Tuo kokoonpano';

  @override
  String get e2eeTradeoff1 =>
      '• Jotkin ominaisuudet, kuten ulkoisten sovellusten integraatiot, voivat olla pois käytöstä.';

  @override
  String get chatAppsCodeExpiredTitle => 'Tämä koodi vanheni';

  @override
  String get responseSchema => 'Vastauskaavio';

  @override
  String get wrappedBestMoments => 'Parhaat hetket';

  @override
  String get noAppsExternalAccess => 'Yhdelläkään asennetulla sovelluksella ei ole ulkoista pääsyä tietoihisi.';

  @override
  String modelReadyWithName(String model) {
    return 'Malli valmis ($model)';
  }

  @override
  String get appDisabledWebhookFailures =>
      'Sen päätepiste epäonnistui 72 tuntia peräkkäin, joten toimitukset pysäytettiin.';

  @override
  String reviewConversationCount(int count) {
    return 'Keskustelut: $count';
  }

  @override
  String get reviewChangesLoadFailed => 'Viimeaikaisia muutoksia ei voitu ladata.';

  @override
  String get reviewOpenConversation => 'Keskustelu';

  @override
  String get voiceRecordingFound => 'Tallenne löytyi';

  @override
  String durationAgo(String duration) {
    return '$duration sitten';
  }

  @override
  String get onboardingWelcomeToOmi => 'Tervetuloa Omiin';

  @override
  String get deleteActionItemConfirmTitle => 'Poista tehtävä';

  @override
  String get importantBillingInfo => 'Tärkeää laskutustietoa:';

  @override
  String get pending => 'Odottaa';

  @override
  String get onboardingRatingPromptTitle => 'Pidätkö Omista?';

  @override
  String get savePayPalDetails => 'Tallenna PayPal-tiedot';

  @override
  String appDisabledLastError(String error) {
    return 'Viimeisin virhe: $error.';
  }

  @override
  String get iveInstalledAndOpenedTheApp => 'Olen asentanut ja avannut sovelluksen';

  @override
  String get pricePlaceholder => '0.00';

  @override
  String get triggerTranscriptProcessed => 'Litterointi käsitelty';

  @override
  String get decisions => 'Päätökset';

  @override
  String get conversationProcessingFailedMessage => 'Tätä keskustelua ei voitu käsitellä.';

  @override
  String get continueText => 'Jatka';

  @override
  String get signInWithGoogle => 'Kirjaudu Googlella';

  @override
  String firmwareFlashTarget(String deviceName) {
    return 'Laite: $deviceName';
  }

  @override
  String get deleteYourAccountAndAllData => 'Poista tilisi ja kaikki tiedot';

  @override
  String get provider => 'Palveluntarjoaja';

  @override
  String get people => 'Ihmiset';

  @override
  String get perMonth => '/ kuukausi';

  @override
  String get monthFeb => 'Helmi';

  @override
  String get fridayAbbr => 'Pe';

  @override
  String get thankYouForFeedback => 'Kiitos palautteestasi!';

  @override
  String get usageBestYear => 'Best year';

  @override
  String get addAppFillRequiredFields => 'Täytä kaikki pakolliset kentät oikein';

  @override
  String get deviceOnboardingVoiceReplyOffDescription => 'Vastaukset pysyvät näytöllä. Mitään ei puhuta.';

  @override
  String get logs => 'Lokit';

  @override
  String get exportConversations => 'Vie keskustelut';

  @override
  String get memoryReviewDropped => 'Poistettu muistoistasi.';

  @override
  String get appearanceLight => 'Vaalea';

  @override
  String get moneyEarned => 'Ansaittu raha';

  @override
  String get permissionsAndTriggers => 'Käyttöoikeudet ja laukaisimet';

  @override
  String get discardRecordingTitle => 'Hylätäänkö nauhoitus?';

  @override
  String get wrappedMinutesLabel => 'minuuttia';

  @override
  String get voiceRestoredToast => 'Omi saattaa kysyä tästä äänestä uudelleen';

  @override
  String get locationAccess => 'Sijaintipääsy';

  @override
  String get deleteAllMemories => 'Poista kaikki muistot';

  @override
  String get deleteAccountTitle => 'Poista tili';

  @override
  String get selectFile => 'Valitse tiedosto';

  @override
  String get answerTheCallFrom => 'Vastaa puheluun numerosta';

  @override
  String get unpairDeviceDialogTitle => 'Poista laitteen pariliitos';

  @override
  String exportedToPlatform(String platform) {
    return 'Viety kohteeseen $platform';
  }

  @override
  String syncCardDownloadPercent(int percent) {
    return '$percent%';
  }

  @override
  String get deviceOnboardingVoiceReplyPreviewPlaying => 'Toistetaan viimeistä vastaustasi...';

  @override
  String get fromSd => 'SD:ltä';

  @override
  String get goodSampleInstructions =>
      '1. Varmista, että olet hiljaisessa paikassa.\n2. Puhu selkeästi ja luonnollisesti.\n3. Varmista, että laitteesi on luonnollisessa asennossaan kaulallasi.\n\nKun se on luotu, voit aina parantaa sitä tai tehdä sen uudelleen.';

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
  String get starConversationHint => 'Merkitäksesi keskustelun tähdellä, avaa se ja napauta tähti-kuvaketta otsikossa.';

  @override
  String get pairingTitleOmiDevkit => 'Aseta Omi DevKit pariliitostilaan';

  @override
  String sttPrimaryLanguageUnsupported(String language, String fallback) {
    return 'Tämä palveluntarjoaja ei tue kieltä $language, joten se käyttää kieltä $fallback.';
  }

  @override
  String get premiumMinutesMonth =>
      '300 premium-minuuttia kuukaudessa. Valitse ”Laitteella” rajattomaan ilmaiseen litterointiin. ';

  @override
  String get firmwareEnsureBattery => 'Varmista, että laitteessasi on 15% akkua.';

  @override
  String get actionItemDescriptionHint => 'Mitä pitää tehdä?';

  @override
  String get yourScore => 'Pistemääräsi';

  @override
  String failedToStartAuth(String appName) {
    return '$appName-todennuksen aloitus epäonnistui';
  }

  @override
  String get actionReadTasks => 'Lue tehtäviä';

  @override
  String get keepSyncing => 'Jatka synkronointia';

  @override
  String get overdue => 'Myöhässä';

  @override
  String get chatAppsProblemUnavailable => 'Chat-sovellukset eivät ole vielä käytettävissä tililläsi.';

  @override
  String get tapSyncToStart => 'Aloita napauttamalla Synkronoi';

  @override
  String get emptyDoneMessage => 'Ei vielä suoritettuja kohteita';

  @override
  String get recordOptionsTip => 'Vinkki: tallenna puhelu napauttamalla tallennuspainikkeen nuolta.';

  @override
  String get setupQuestionProfession => '1. Mikä on ammattisi?';

  @override
  String get deviceInfoSection => 'Laitteen tiedot';

  @override
  String get teachOmiYourVoice => 'Opeta Omi äänesi';

  @override
  String get addYourFirstMemory => 'Lisää ensimmäinen muistosi';

  @override
  String get priceLabel => 'HINTA';

  @override
  String get high => 'Korkea';

  @override
  String estimatedSizeWithValue(String size) {
    return 'Arvioitu koko: ~$size MB';
  }

  @override
  String cleanUpUnsureCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count henkilöä, joista Omi ei ole varma',
      one: '1 henkilö, josta Omi ei ole varma',
    );
    return '$_temp0';
  }

  @override
  String get makeAllMemoriesPrivate => 'Tee kaikki muistot yksityisiksi';

  @override
  String get raybanMetaWaitingForMetaAI => 'Viimeistele yhdistäminen Meta AI -sovelluksessa ja palaa sitten tänne.';

  @override
  String get revokeAuthorization => 'Peru valtuutus';

  @override
  String get confidenceToReachConfirmed => 'Vahvistetuksi pääsemiseksi';

  @override
  String get syncCardRateLimited => 'Kohtuullisen käytön raja saavutettu — synkronointi jatkuu automaattisesti';

  @override
  String get reviewStopClip => 'Pysäytä klippi';

  @override
  String get chatAppsWhatOmiDoes => 'Mitä Omi tekee chat-sovelluksissa';

  @override
  String get resume => 'Jatka';

  @override
  String get defaultSpace => 'Oletustila';

  @override
  String get multipleSpeakersDetected => 'Useita puhujia havaittu';

  @override
  String evidenceAutoCorrected(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Muutit $count automaattista merkintää toiselle henkilölle',
      one: 'Muutit 1 automaattisen merkinnän toiselle henkilölle',
    );
    return '$_temp0';
  }

  @override
  String get voiceMatchPossible => 'Mahdollinen osuma';

  @override
  String get checkBoxToConfirm =>
      'Valitse ruutu vahvistaaksesi, että ymmärrät tilin poistamisen olevan pysyvää ja peruuttamatonta.';

  @override
  String get quicklyPopulateResponse => 'Täytä nopeasti tunnetulla palveluntarjoajan vastausmuodolla';

  @override
  String get monthJul => 'Heinä';

  @override
  String get failedToInitializeCallService => 'Puhelupalvelun alustus epaonnistui';

  @override
  String get connectAction => 'Yhdistä';

  @override
  String get onDeviceModelDeleted => 'Malli poistettu';

  @override
  String get micGainDescNeutral => 'Neutraali - tasapainoinen nauhoitus';

  @override
  String get chatOfflineHint => 'Olet offline-tilassa. Muodosta yhteys lähettääksesi viestejä.';

  @override
  String get onboardingLocationGrantInSettings =>
      'Myönnä sijaintilupa kohdassa Asetukset > Tietosuoja ja turvallisuus > Sijaintipalvelut';

  @override
  String get invalidSetupInstructionsUrl => 'Virheellinen asetusohjeiden URL';

  @override
  String get msgCameraPermissionDenied => 'Kameran käyttöoikeus evätty. Salli pääsy kameraan';

  @override
  String get dataAndPrivacy => 'Tiedot ja tietosuoja';

  @override
  String get deviceNotCompatible => 'Laitteesi ei ole yhteensopiva laitteella tapahtuvan transkription kanssa';

  @override
  String get pairingDescAppleWatch =>
      'Asenna ja avaa Omi-sovellus Apple Watchissasi, napauta sitten Yhdistä sovelluksessa.';

  @override
  String get speechProfileTopicLocation => 'Missä asut?';

  @override
  String get makeAllPrivate => 'Tee kaikki muistot yksityisiksi';

  @override
  String get capabilityNotification => 'Ilmoitus';

  @override
  String get captureAudioSavedTranscribesLater => 'Ääni tallennettu, litteroidaan myöhemmin';

  @override
  String get wrappedTopPhrases => 'Top 5 lausetta';

  @override
  String get transcribeLaterPaused => 'Keskeytetty – ääntä ei tallenneta';

  @override
  String get deviceOnboardingTurnOnTitle => 'Käynnistä';

  @override
  String get keyNamePlaceholder => 'esim. Oma sovellus';

  @override
  String get languageTitle => 'Kieli';

  @override
  String get statusVerifiedLabel => 'Vahvistettu';

  @override
  String get storageLocationPhoneMemory => 'Puhelin (muisti)';

  @override
  String get you => 'Sinä';

  @override
  String get listeningTranscriptWillAppear => 'Kuunnellaan… litterointi näkyy tässä.';

  @override
  String get askSuggestNotice => 'Mitä Omi huomasi?';

  @override
  String get safelyBackedUp => 'Keskustelut luotu';

  @override
  String get folderName => 'Kansion nimi';

  @override
  String get categorySocialEntertainment => 'Sosiaalinen ja viihde';

  @override
  String speechProfileOwnerTitle(String name) {
    return 'Käyttäjän $name ääniprofiili';
  }

  @override
  String get reviewAddedSuccessfully => 'Arvostelu lisätty onnistuneesti 🚀';

  @override
  String get fairUseSpeechUsage => 'Puheen käyttö';

  @override
  String get visibilitySubtitle => 'Hallitse mitä keskusteluja näkyy luettelossasi';

  @override
  String get wrappedWinLabelUpper => 'VOITTO';

  @override
  String timeCompactMinsAndSecs(int mins, int secs) {
    return '${mins}m ${secs}s';
  }

  @override
  String get phoneCallsUpsellSubtitle =>
      'Soita puheluita Omin kautta ja saa reaaliaikainen litterointi, automaattiset yhteenvedot ja paljon muuta.';

  @override
  String get sessionExpiredSignInAgain => 'Istunto on vanhentunut — kirjaudu uudelleen.';

  @override
  String get newPersonEllipsis => 'Uusi henkilö…';

  @override
  String get sharePeriodToday => 'Tänään Omi on:';

  @override
  String get premiumMinutesInfo =>
      '300 premium-minuuttia kuukaudessa. Valitse ”Laitteella” rajattomaan ilmaiseen litterointiin.';

  @override
  String get notConnectedStatus => 'Ei yhdistetty';

  @override
  String get authorizeSavingRecordings => 'Valtuuta nauhoitusten tallentaminen';

  @override
  String get thinking => 'Mietitään';

  @override
  String get unpairDialogTitle => 'Pura laitepari';

  @override
  String get batteryFullyChargedBody => 'Omi-laitteesi on ladattu täyteen. Voit irrottaa sen nyt!';

  @override
  String get speakerTagPromptRejectedToast => 'Nimi poistettu';

  @override
  String get phone => 'Puhelin';

  @override
  String get chatAppsVoiceNotes => 'Ääniviestit';

  @override
  String get deviceOnboardingStatusDisconnected => 'Yhteys katkaistu';

  @override
  String get debugModeDetected => 'Virheenkorjaustila havaittu';

  @override
  String get failedToSaveDefaultRepo => 'Oletusrepositorion tallentaminen epäonnistui';

  @override
  String get showCompletedTasks => 'Näytä valmiit';

  @override
  String deviceStorageUsedOfTotal(String used, String total) {
    return '$used / $total käytössä';
  }

  @override
  String get recordingsNotSynced => 'Sinulla on nauhoituksia, joita ei ole vielä synkronoitu.';

  @override
  String get performanceWarning => 'Suorituskykyvaroitus';

  @override
  String get submitAppPrivateDescription =>
      'Sovelluksesi tarkistetaan ja asetetaan saatavillesi yksityisesti. Voit alkaa käyttää sitä heti, jopa tarkistuksen aikana!';

  @override
  String get copyTranscript => 'Kopioi litterointi';

  @override
  String get providing => 'Tarjoaminen';

  @override
  String get findDeviceNoneMessage => 'Kytke se päälle ja pidä sitä puhelimesi lähellä.';

  @override
  String get wrappedLetsHitRewind => 'Kelataan taaksepäin vuotesi';

  @override
  String deviceRamBelowMinimum(String ram) {
    return 'Havaittu RAM: $ram Gt. Suositeltu vähimmäismäärä: 4 Gt.';
  }

  @override
  String get addOrChangePaymentMethod => 'Lisää tai vaihda maksutapa';

  @override
  String get omiAppName => 'Omi';

  @override
  String get enableBluetooth => 'Ota Bluetooth käyttöön';

  @override
  String get privacyNotice => 'Tietosuojailmoitus';

  @override
  String get manufacturer => 'Valmistaja';

  @override
  String get byContinuingYouAgree => 'Jatkamalla hyväksyt ';

  @override
  String dataProtectedWithSettings(String level) {
    return 'Tietosi on nyt suojattu uusilla $level-asetuksilla.';
  }

  @override
  String get selectSpaceInWorkspace => 'Valitse tila työtilassasi';

  @override
  String get copyKey => 'Kopioi avain';

  @override
  String get password => 'Salasana';

  @override
  String estimatedSize(String size) {
    return 'Arvioitu koko: ~$size Mt';
  }

  @override
  String monthsFreeBadge(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count kuukautta ilmaiseksi',
      one: '1 kuukausi ilmaiseksi',
    );
    return '$_temp0';
  }

  @override
  String get chatAppsNotAvailableYet => 'Ei vielä saatavilla';

  @override
  String estimatedTimeRemaining(String time) {
    return 'Arvio: $time jäljellä';
  }

  @override
  String get syncCardBackendBusy =>
      'Omin palvelimet ovat ruuhkautuneet — tallenteesi synkronoidaan, kun kapasiteettia vapautuu';

  @override
  String get speakerTagPromptTitle => 'Auta Omia tunnistamaan äänet';

  @override
  String get playFromHere => 'Toista tästä';

  @override
  String get entityProject => 'Projekti';

  @override
  String get permissionNotGrantedYet =>
      'Käyttöoikeutta ei ole vielä myönnetty. Varmista, että salloit mikrofonin käytön ja avasit sovelluksen kellossasi uudelleen.';

  @override
  String get e2eeTradeoff2 => '• Jos kadotat salasanasi, tietojasi ei voi palauttaa.';

  @override
  String get exportConfiguration => 'Vie kokoonpano';

  @override
  String get recordWith => 'Tallennustapa';

  @override
  String get greetingEvening => 'Hyvää iltaa';

  @override
  String deletePhoneNumberConfirm(String phoneNumber) {
    return 'Poista $phoneNumber?';
  }

  @override
  String get deviceOnboardingAskQuestionTitle => 'Esitä Omille kysymys';

  @override
  String get appNamePlaceholder => 'Upea sovellukseni';

  @override
  String get tapPlayToResume => 'Napauta toista jatkaaksesi';

  @override
  String get dueDate => 'Määräpäivä';

  @override
  String get appearanceSystem => 'Järjestelmä';

  @override
  String get invalidEmailError => 'Anna kelvollinen sähköpostiosoite';

  @override
  String get highResourceUsage => 'Korkea resurssien käyttö';

  @override
  String get voiceAndPeople => 'Ääni ja Ihmiset';

  @override
  String get customizationSection => 'Mukautus';

  @override
  String get failedToCancelSubscription => 'Tilauksen peruuttaminen epäonnistui. Yritä uudelleen.';

  @override
  String get later => 'Myöhemmin';

  @override
  String get wrappedTasksGenerated => 'tehtävää luotu';

  @override
  String get personalizingExperience => 'Mukautetaan kokemustasi…';

  @override
  String get syncAvailable => 'Synkronointi saatavilla';

  @override
  String chatGreeting(String name) {
    return 'Hei $name, kysy mitä vain';
  }

  @override
  String get phoneCallSettingsTitle => 'Puheluasetukset';

  @override
  String get remoteDeviceTerminated => 'Etälaite katkaisi yhteyden';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'Virhe tiedostonvalitsimen avaamisessa: $message';
  }

  @override
  String get actionItemDeleted => 'Tehtävä poistettu';

  @override
  String get couldNotLoadMemories => 'Muistoja ei voitu ladata';

  @override
  String get generateDescription => 'Luo kuvaus';

  @override
  String get privateLabel => 'Yksityinen';

  @override
  String get deviceOnboardingMuteUnmute => 'Mykistä / poista mykistys';

  @override
  String get day => 'Päivä';

  @override
  String get submitAppQuestion => 'Lähetetäänkö sovellus?';

  @override
  String get usageWords => 'Words';

  @override
  String get failedToConnectClickUp => 'Yhteyden muodostaminen ClickUpiin epäonnistui';

  @override
  String get selectZipFileToImport => 'Valitse tuotava .zip-tiedosto!';

  @override
  String timeSecsPlural(int count) {
    return '$count sek';
  }

  @override
  String get wasThisHelpful => 'Oliko tästä apua?';

  @override
  String get msgLearningMemories => 'Opitaan muistoistasi…';

  @override
  String get onboardingScreenCaptureRequired => 'Näytönkaappauslupa vaaditaan järjestelmä-äänen tallennukseen.';

  @override
  String evidenceManualLabels(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Nimesit $count keskustelussa',
      one: 'Nimesit 1 keskustelussa',
    );
    return '$_temp0';
  }

  @override
  String get transferCancelled => 'Siirto peruutettu';

  @override
  String get sttModelSpeed => 'Nopeus';

  @override
  String get fairUsePolicy => 'Kohtuullinen käyttö';

  @override
  String get phoneStorage => 'Puhelimen tallennustila';

  @override
  String get deviceOnboardingEndConversationDesc => 'Tallenna ja lopeta nykyinen keskustelu';

  @override
  String get proceedAnyway => 'Jatka silti';

  @override
  String get overview => 'Yleiskatsaus';

  @override
  String get deviceOnboardingGoodJob => 'Hienosti!';

  @override
  String get delete => 'Poista';

  @override
  String get connectAiAssistantsToYourData => 'Yhdistä tekoälyavustajat tietoihisi';

  @override
  String get startFresh => 'Aloita alusta';

  @override
  String get deviceOnboardingStatusConnectedDone => 'Yhdistetty!';

  @override
  String get filterInstalled => 'Asennettu';

  @override
  String get mergingStatus => 'Yhdistetään…';

  @override
  String get successfullyConnected => 'Yhdistetty onnistuneesti!';

  @override
  String get permissionCreateConversations => 'Luo keskusteluja';

  @override
  String get cancelConsequencePhoneCalls => 'Ei reaaliaikaista puhelutranskripiota';

  @override
  String get feedbackReasonSummaryOther => 'Something else';

  @override
  String get oAuth => 'OAuth';

  @override
  String get notEnoughSpace => 'Varoitus: Ei tarpeeksi tilaa!';

  @override
  String get feedbackTitleTooExpensive => 'Mikä hinta sopisi sinulle?';

  @override
  String get secureEncryption => 'Turvallinen salaus';

  @override
  String get rating2PlusStars => '2+ tähteä';

  @override
  String get chatAppsOpenMessagesAgain => 'Avaa Viestit uudelleen';

  @override
  String fairUseBudgetResetsAt(String time) {
    return 'Resets $time';
  }

  @override
  String get addVocabularyDescription => 'Lisää sanoja, jotka Omin tulisi tunnistaa litteroinnin aikana.';

  @override
  String get whisperModelSizeMedium => 'Keskikokoinen';

  @override
  String get wrappedMyBuddiesLabel => 'YSTÄVÄNI';

  @override
  String get memoryGraph => 'Muistigraafi';

  @override
  String get paste => 'Liitä';

  @override
  String get failedToRefreshGitHubStatus => 'GitHub-yhteyden tilan päivitys epäonnistui.';

  @override
  String get feedbackSubtitleMissingFeatures => 'Rakennamme aina — tämä auttaa meitä priorisoimaan.';

  @override
  String get itemApp => 'Sovellus';

  @override
  String get pairingDescFriendPendant =>
      'Paina riipuksen painiketta käynnistääksesi sen. Se siirtyy automaattisesti pariliitostilaan.';

  @override
  String get appDisabledGeneric => 'Omi poisti sen käytöstä.';

  @override
  String get noSummaryForApp =>
      'Tälle sovellukselle ei ole tiivistelmää. Kokeile toista sovellusta parempien tulosten saamiseksi.';

  @override
  String get deleteProcessed => 'Poista käsitellyt';

  @override
  String get chatBlockOpenInGoals => 'Avaa Tavoitteissa';

  @override
  String get micGainDescModerate => 'Hiljainen - kohtalaiseen meluun';

  @override
  String get defaultRepository => 'Oletusrepositorio';

  @override
  String get statusPending => 'Odottaa';

  @override
  String get referralProgram => 'Suositteluohjelma';

  @override
  String get authFailedToLinkApple => 'Appleen linkittäminen epäonnistui, yritä uudelleen.';

  @override
  String modelNameWithFile(String model) {
    return 'Malli: $model';
  }

  @override
  String get deviceOnboardingTurnOnSubtitle => 'Käynnistä se uudelleen painamalla painiketta';

  @override
  String get previewAndScreenshots => 'Esikatselu ja kuvakaappaukset';

  @override
  String get recordingOfflineTranscriptWillCatchUp =>
      'Tallennetaan offline-tilassa — litterointi päivittyy, kun olet taas verkossa.';

  @override
  String get accessibilityDescription =>
      'Omi tarvitsee esteettömyysluvan tunnistaakseen, milloin liityt Zoom-, Meet- tai Teams-kokouksiin selaimessasi.';

  @override
  String setDefaultAppContent(String appName) {
    return 'Asetetaanko $appName oletusyhteenvetosovellukseksi?\n\nTätä sovellusta käytetään automaattisesti kaikkiin tuleviin keskusteluyhteenvetoihin.';
  }

  @override
  String get switchRequiresRestart => 'Vaihto vaatii sovelluksen uudelleenkäynnistyksen';

  @override
  String get wrappedWinHeader => 'Voitto';

  @override
  String get forYou => 'Sinulle';

  @override
  String get filterCategory => 'Kategoria';

  @override
  String get createPersonHint => 'Luo uusi henkilö ja opeta Omi tunnistamaan hänen puheensa!';

  @override
  String get loadingMemories => 'Ladataan muistoja…';

  @override
  String get selectedPaymentMethod => 'Valittu maksutapa';

  @override
  String get email => 'Sähköposti';

  @override
  String get transcriptionUnavailableRecordingContinues =>
      'Transkriptiot eivät ole käytettävissä, tallennus jatkuu laitteella ja käsitellään myöhemmin';

  @override
  String get noLogsYet =>
      'Lokeja ei vielä ole. Nauhoita jotain, niin näet transkriptiopalvelun tarjoajalle lähetetyt pyynnöt.';

  @override
  String get failedToStartAuthentication => 'Todennuksen aloitus epäonnistui';

  @override
  String peopleCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count henkilöä',
      one: '1 henkilö',
    );
    return '$_temp0';
  }

  @override
  String get enterBackendUrlError => 'Anna palvelimen URL';

  @override
  String get playbackBackToCurrent => 'Takaisin nykyiseen';

  @override
  String clockSkewWarning(int minutes) {
    return 'Laitteesi kello on ~$minutes min. väärässä. Tarkista päivämäärä- ja aika-asetukset.';
  }

  @override
  String get stopThese => 'Lopeta nämä';

  @override
  String get yes => 'Kyllä';

  @override
  String get recognizingOthers => 'Muiden tunnistaminen 👀';

  @override
  String get transcriptionLanguageDesc => 'Valitse puheen transkription kieli';

  @override
  String aboutMinutesRemaining(int minutes) {
    return 'Noin $minutes minuuttia jäljellä';
  }

  @override
  String get deleteFlowReasonSubtitle => 'Palautteesi auttaa meitä parantamaan Omia kaikille.';

  @override
  String get processedFilesDeleted => 'Käsitellyt tiedostot poistettu';

  @override
  String get autoLanguageDetection => 'Automaattinen kielentunnistus';

  @override
  String bulkExportPartial(int success, int total, String platform) {
    return 'Viety $success/$total kohteeseen $platform';
  }

  @override
  String get actionItemDescriptionCannotBeEmpty => 'Tehtävän kuvaus ei voi olla tyhjä';

  @override
  String get deleteReasonFoundAlternative => 'Käytän jotain muuta';

  @override
  String get noContentToDisplay => 'Ei sisältöä näytettäväksi';

  @override
  String get feedbackReasonRecordingWrongSpeaker => 'Wrong speaker';

  @override
  String get create => 'Luo';

  @override
  String get greatJobAlmostThere => 'Hienoa työtä, olet melkein valmis';

  @override
  String get captureStorageAlmostFull => 'Tallennustila melkein täynnä';

  @override
  String chatAppsConnectedOn(String date) {
    return 'Yhdistetty $date';
  }

  @override
  String get wrappedAGreatDay => 'Hieno päivä';

  @override
  String get backendUrlSavedSuccess => 'Palvelimen URL tallennettu!';

  @override
  String get speakerTagPromptIsThisYou => 'Olitko tämä sinä?';

  @override
  String get knowledgeGraphDeletedSuccess => 'Tietograafi poistettu onnistuneesti';

  @override
  String timeMinsPlural(int count) {
    return '$count min';
  }

  @override
  String get peopleNotHeardYet => 'Ei vielä kuultu';

  @override
  String get chatStarterDoDifferently => 'Mitä voisin tehdä tänään toisin?';

  @override
  String get fairUseAboutBody =>
      'Omi on suunniteltu henkilökohtaisiin keskusteluihin, kokouksiin ja live-vuorovaikutukseen. Käyttöä mitataan puhumiseen käytetyllä ajalla, ei yhteysajalla. Jos käyttösi on selvästi tavanomaisen henkilökohtaisen käytön yläpuolella, saat ensin varoituksen. Jatkuva raskas käyttö voi hidastaa litterointia tai rajoittaa sitä.';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'Valitse ensisijainen kielesi';

  @override
  String get manualDisconnect => 'Manuaalinen katkaisu';

  @override
  String get googleCalendarNotConnected => 'Google Kalenteria ei ole yhdistetty';

  @override
  String get soCloseJustLittleMore => 'Niin lähellä, vielä vähän';

  @override
  String appDataAccessMessage(String appName) {
    return '$appName vastaanottaa keskustelusi, muistosi ja tallenteesi kehittäjänsä palvelimelle. Omi ei vastaa siitä, miten tietoja siellä käytetään.';
  }

  @override
  String savePercent(int percent) {
    return 'Säästä ~$percent%';
  }

  @override
  String get deviceDisconnectedNotificationBody => 'Yhdistä uudelleen jatkaaksesi Omin käyttöä.';

  @override
  String get openConversation => 'Avaa keskustelu';

  @override
  String get frequencyDescMaximum => 'Jokainen hyödyllinen yhteys, enintään 9 päivässä';

  @override
  String get readChatRepliesAloud => 'Lue chat-vastaukset ääneen';

  @override
  String get microphonePermissionRequired => 'Mikrofonin lupa vaaditaan äänen tallennukseen.';

  @override
  String get updatePayPalAccountDetails => 'Päivitä PayPal-tilisi tiedot';

  @override
  String get connectionTimeout => 'Yhteyden aikakatkaisu';

  @override
  String get micGainDescHigh => 'Korkea - kaukaisille tai pehmeille äänille';

  @override
  String get permissionsInfoNote => 'R = Luku, W = Kirjoitus. Oletuksena vain luku, jos mitään ei ole valittu.';

  @override
  String timeHoursAndMins(int hours, int mins) {
    return '$hours tuntia $mins min';
  }

  @override
  String get keepMyAccount => 'Säilytä tilini';

  @override
  String get transcriptionLanguage => 'Transkription kieli';

  @override
  String dreamReportStats(int records, int tokens) {
    return 'Luettu $records kohdetta · $tokens tokenia';
  }

  @override
  String get editPerson => 'Muokkaa henkilöä';

  @override
  String get whatWeTrack => 'Mitä seuraamme';

  @override
  String get micGainDescVeryHigh => 'Erittäin korkea - erittäin hiljaisille lähteille';

  @override
  String timeCompactDays(int count) {
    return '${count}pv';
  }

  @override
  String get reviewTaskField => 'Tehtävä';

  @override
  String reviewConfirmPerson(String name) {
    return 'Vahvista $name';
  }

  @override
  String get downloadingFromDevice => 'Ladataan laitteesta';

  @override
  String get conversationTranscriptCopiedToClipboard => 'Keskustelun litterointi kopioitu leikepöydälle';

  @override
  String get continueAction => 'Jatka';

  @override
  String conversationsMovedCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count keskustelua siirretty',
      one: '1 keskustelu siirretty',
    );
    return '$_temp0';
  }

  @override
  String get signInButton => 'Kirjaudu sisään';

  @override
  String get startUpdate => 'Aloita päivitys';

  @override
  String get wrappedTopPhrasesLabelUpper => 'TOP LAUSEET';

  @override
  String get total => 'Yhteensä';

  @override
  String get deleting => 'Poistetaan…';

  @override
  String get skipBack10Seconds => '10 sekuntia taaksepäin';

  @override
  String get setupAnswerAllQuestions => 'Et ole vielä vastannut kaikkiin kysymyksiin! 🥺';

  @override
  String get planUpgradeScheduledMessage =>
      'Upgrade scheduled! Your monthly plan continues until the end of your billing period, then automatically switches to annual.';

  @override
  String get needHelpChatWithUs => 'Tarvitsetko apua? Keskustele kanssamme';

  @override
  String get chatBlockUnavailable => 'Ei ole enää saatavilla';

  @override
  String estimatedMinutes(int count) {
    return '~$count minuutti(a)';
  }

  @override
  String get failedToSaveMemory => 'Tallennus epäonnistui. Tarkista yhteytesi.';

  @override
  String get deleteReasonTakingBreak => 'Pidän vain tauon';

  @override
  String get reviewAndManageConversations => 'Tarkista ja hallitse tallennettuja keskustelujasi';

  @override
  String get actionReadMemories => 'Lue muistoja';

  @override
  String deletePinnedPersonMessage(String name) {
    return '$name on kiinnitetty. Hänen ääninäytteensä poistetaan, Omi ei enää tunnista häntä ja aiemmissa litteroinneissa hän näkyy nimettömänä puhujana. Tätä ei voi perua.';
  }

  @override
  String get speakerTagPromptHintOwner => 'Vastauksesi merkitsee vain toistetun katkelman.';

  @override
  String get onboardingNotificationDeniedNotifications =>
      'Ilmoituslupa evätty. Myönnä lupa kohdassa Järjestelmäasetukset > Ilmoitukset.';

  @override
  String appDisabledNamed(String appName) {
    return '$appName poistettu käytöstä';
  }

  @override
  String get tabOld => 'Vanhat';

  @override
  String deviceOnboardingVoiceReplyStatusHeadphonesConnected(String device) {
    return '$device yhdistetty. Omi puhuu täällä.';
  }

  @override
  String get deletePendingFiles => 'Poista odottavat tallenteet';

  @override
  String get wrappedWin => 'Voitto';

  @override
  String get removeFromAllFolders => 'Poista kaikista kansioista';

  @override
  String get deviceIdLabel => 'Laitteen tunnus';

  @override
  String get upgradeAlreadyScheduled => 'Päivityksesi vuositilaukseen on jo ajoitettu';

  @override
  String get openCall => 'Avaa puhelu';

  @override
  String get rateAndReviewThisApp => 'Arvioi ja arvostele tämä sovellus';

  @override
  String get getStarted => 'Aloita';

  @override
  String get deviceOnboardingVoiceReplyAlwaysDescription =>
      'Käyttää puhelimen kaiutinta, kun kuulokkeita ei ole kytketty.';

  @override
  String chooseExportDestination(int count) {
    return 'Vie $count kohde(tta) kohteeseen…';
  }

  @override
  String get onboardingSetupSubtitle => 'Anna Omille hetki mukautua';

  @override
  String welcomeBack(String name) {
    return 'Tervetuloa takaisin, $name';
  }

  @override
  String get dreamReportIdle => 'Ei vielä mitään uutta tarkistettavaa.';

  @override
  String get cleanUpTitle => 'Siivous';

  @override
  String get deleteProcessedFiles => 'Poista käsitellyt tiedostot';

  @override
  String get no => 'Ei';

  @override
  String get msgPhotoError => 'Virhe kuvan ottamisessa. Yritä uudelleen.';

  @override
  String get search => 'Etsi';

  @override
  String get downloadingFirmware => 'Ladataan laiteohjelmistoa';

  @override
  String get phoneKeypadTab => 'Nappaimisto';

  @override
  String get pendantFullSyncBlocked =>
      'Pendantin muisti on täynnä ja se on yhä äänitystilassa, joten tallennettua ääntä ei voi siirtää. Pysäytä äänitys painamalla Pendantin painiketta ja synkronoi sitten uudelleen.';

  @override
  String get deleteSelectedItemsTitle => 'Poista valitut kohteet';

  @override
  String get appPrivacyAndTerms => 'Sovelluksen tietosuoja ja ehdot';

  @override
  String get omiTranscription => 'Omi-litterointi';

  @override
  String get editConversation => 'Muokkaa keskustelua';

  @override
  String moveConversationsTo(int count) {
    return 'Siirrä $count keskustelua kansioon:';
  }

  @override
  String get signOutConfirmation =>
      'Sinun on kirjauduttava uudelleen nähdäksesi keskustelusi. Pariliitetty laite ja sovelluksen asetukset säilyvät tässä puhelimessa.';

  @override
  String get wrappedObsessionsLabel => 'PAKKOMIELTEENI';

  @override
  String get jumpToLatestMessage => 'Siirry uusimpaan viestiin';

  @override
  String get failedStatus => 'Epäonnistui';

  @override
  String get notNow => 'Ei nyt';

  @override
  String transferFailedMessage(String error) {
    return 'Siirto epäonnistui: $error';
  }

  @override
  String get customVocabularyTitle => 'Mukautettu sanasto';

  @override
  String get internetRequired => 'Internet vaaditaan';

  @override
  String get waitingForData => 'Odotetaan tietoja…';

  @override
  String get noRecordingsYet => 'Ei vielä tallenteita';

  @override
  String get answerWithYourVoice => 'Vastaa puhumalla:';

  @override
  String personUnpinnedToast(String name) {
    return '$name irrotettu';
  }

  @override
  String get stopRecording => 'Lopeta nauhoitus';

  @override
  String get off => 'Pois';

  @override
  String get memoryThisPhone => 'Tämä puhelin';

  @override
  String get thirteenMonthsCoverage =>
      'Saat yhteensä 13 kuukauden kattavuuden (nykyinen kuukausi + 12 kuukautta vuosittain)';

  @override
  String failedToCreateApiKey(String error) {
    return 'Palveluntarjoajan API-avaimen luominen epäonnistui: $error';
  }

  @override
  String get tipStableInternet => 'Vakaa internet nopeuttaa pilveen lataamista';

  @override
  String get tasksMarkComplete => 'Merkitty valmiiksi';

  @override
  String get reviewAddTask => 'Lisää tehtävä';

  @override
  String get submitReply => 'Lähetä vastaus';

  @override
  String get captureRecoveryBanner => 'Omi ei lähetä ääntä — yhdistä uudelleen napauttamalla';

  @override
  String get analyzing => 'Analysoidaan…';

  @override
  String get sttModelFaster => 'Nopeampi';

  @override
  String get fairUseLoadError => 'Kohtuullisen käytön tilaa ei voitu ladata. Yritä uudelleen.';

  @override
  String get places => 'Paikat';

  @override
  String get voiceMatchWeak => 'Heikko osuma';

  @override
  String captureOfflineBufferingFor(int minutes) {
    return 'Offline, puskuroidaan · $minutes min';
  }

  @override
  String get onboardingWhatIKnowAboutYouTitle => 'Tässä on mitä tiedän sinusta';

  @override
  String get raybanMetaPhotoRequested => 'Valokuvaa pyydetty — se näkyy keskustelussasi.';

  @override
  String get verifyYourNumber => 'Vahvista numerosi';

  @override
  String get deleteFlowConfirmSubtitle => 'Tätä ei voi perua, ei edes tuen avulla.';

  @override
  String get submitAppTermsAgreement =>
      'Lähettämällä tämän sovelluksen hyväksyn Omi AI:n käyttöehdot ja tietosuojakäytännön';

  @override
  String get stripeSecureDescription => 'Stripe varmistaa sovelluksesi tulojen turvalliset ja oikea-aikaiset siirrot';

  @override
  String get categoryProductivity => 'Tuottavuus';

  @override
  String chatWithAppName(String appName) {
    return 'Chat sovelluksen $appName kanssa';
  }

  @override
  String get enableCloudStorage => 'Ota pilvitallennustila käyttöön';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl => 'Virheellinen reaaliaikaisen transkription webhook-URL';

  @override
  String get wrappedShow => 'SARJA';

  @override
  String get speakTranscribeSummarize => 'Puhu. Litteroi. Tee yhteenveto.';

  @override
  String get pricingPaid => 'Maksullinen';

  @override
  String get successfullyConnectedAsana => 'Yhdistetty onnistuneesti Asanaan!';

  @override
  String get rating => 'Arvio';

  @override
  String get chatQuotaExceededReply =>
      'Olet saavuttanut kuukausittaisen rajasi. Päivitä jatkaaksesi keskustelua Omin kanssa ilman rajoituksia.';

  @override
  String get pendantIsListeningTitle => 'Riipuksesi kuuntelee';

  @override
  String get usageBestDay => 'Best day';

  @override
  String get personWhyConfidence => 'Miksi?';

  @override
  String get permissionDescCreateConversations => 'Tämä sovellus voi luoda uusia keskusteluja.';

  @override
  String get reviewSpellingCustom => 'Kirjoita itse';

  @override
  String resetsInHours(int count) {
    return 'Nollautuu $count tunnin kuluttua';
  }

  @override
  String get reviewAction => 'Tarkista';

  @override
  String get submitRequest => 'Lähetä pyyntö';

  @override
  String get phoneCalls => 'Puhelut';

  @override
  String get actionItemsTab => 'Tehtävät';

  @override
  String get record => 'Tallenna';

  @override
  String get noReviewsFound => 'Arvosteluja ei löytynyt';

  @override
  String get oauth => 'OAuth';

  @override
  String get urlCopied => 'URL kopioitu';

  @override
  String get actionItemReminderTitle => 'Omi-muistutus';

  @override
  String sharedTasksAdded(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Luetteloosi lisättiin $count tehtävää',
      one: 'Luetteloosi lisättiin 1 tehtävä',
    );
    return '$_temp0';
  }

  @override
  String get contactsPermissionRequiredForSms => 'Yhteystietolupa vaaditaan jakamiseen tekstiviestillä';

  @override
  String get apiKeyRevokedSuccessfully => 'API-avain peruutettu onnistuneesti';

  @override
  String get authorizationSuccessful => 'Valtuutus onnistui!';

  @override
  String get unpinAction => 'Irrota';

  @override
  String get syncingStatus => 'Synkronoidaan';

  @override
  String get audioFormatLabel => 'Äänimuoto';

  @override
  String get phoneSelectCountryTitle => 'Valitse maa';

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'Top $percentile% käyttäjä';
  }

  @override
  String get phoneContactsTab => 'Yhteystiedot';

  @override
  String get reply => 'Vastaa';

  @override
  String get openingShareSheet => 'Avataan jakamisnäyttöä…';

  @override
  String get creatingAppIcon => 'Luodaan sovelluskuvaketta…';

  @override
  String get deviceOnboardingStartSpeaking => 'Ala puhua…';

  @override
  String get wrappedAHilariousMoment => 'Hauska hetki';

  @override
  String get paidApp => 'Maksullinen sovellus';

  @override
  String get wrappedStruggleHeader => 'Kamppailu';

  @override
  String get speakerTagPromptDontKnow => 'Joku, jota en tunne';

  @override
  String get wrappedStarting => 'Aloitetaan…';

  @override
  String get getButton => 'Hae';

  @override
  String get syncCustomSttWarningTitle => 'Synkronointi käyttää Omin litterointia';

  @override
  String get download => 'Lataa';

  @override
  String get addScreenshot => 'Lisää kuvakaappaus';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return 'Yhteyden muodostaminen palveluun $serviceName epäonnistui: $error';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'Yhdistä uudelleen jatkaaksesi $deviceName käyttöä.';
  }

  @override
  String get configureDailySummaryDigest => 'Määritä päivittäinen tehtäväyhteenveto';

  @override
  String get showShortConversationsDesc => 'Näytä kynnysarvoa lyhyemmät keskustelut';

  @override
  String participantsSummaryUncounted(String name) {
    return '$name ja muut';
  }

  @override
  String fairUseBudgetUsed(String used, String limit) {
    return '${used}m / ${limit}m';
  }

  @override
  String get add => 'Lisää';

  @override
  String get disconnect => 'Katkaise yhteys';

  @override
  String get enterApiKey => 'Kirjoita API-avaimesi';

  @override
  String get msgMaxFilesLimit => 'Voit valita enintään 4 tiedostoa';

  @override
  String get space => 'Välilyönti';

  @override
  String get upgrade => 'Päivitä';

  @override
  String get tapToView => 'Napauta nähdäksesi';

  @override
  String get summaryTemplate => 'Yhteenvetomalli';

  @override
  String get chatAppsWaitingTitle => 'Odotetaan viestiäsi';

  @override
  String yesterdayAtTime(String time) {
    return 'Eilen klo $time';
  }

  @override
  String get cancel => 'Peruuta';

  @override
  String get checkingAppleWatch => 'Tarkistetaan Apple Watchia…';

  @override
  String syncCardDownloadPercentSpeed(int percent, String speed) {
    return '$percent% · $speed KB/s';
  }

  @override
  String get finalTouches => 'Viimeiset viimeistelyt';

  @override
  String get weekdaySat => 'La';

  @override
  String get fairUseWeekly => 'Viikkojakso';

  @override
  String get invalidPaymentUrl => 'Virheellinen maksu-URL';

  @override
  String get transcriptionSlowerOnDevice => 'Laitteella tapahtuva transkriptio voi olla hitaampaa tällä laitteella.';

  @override
  String get noListsInSpace => 'Luetteloita ei löytynyt tästä tilasta';

  @override
  String get deviceDiagnostics => 'Laitediagnostiikka';

  @override
  String get askAnything => 'Kysy mitä tahansa';

  @override
  String confidenceMeterLabel(String level) {
    return 'Varmuus: $level';
  }

  @override
  String get permissionReadTasks => 'Lue tehtäviä';

  @override
  String get skipForNow => 'Ohita toistaiseksi';

  @override
  String get setupCompletedUrl => 'Asennuksen valmistumisen URL';

  @override
  String get saySomething => 'Sano jotain…';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get chatAppsEntryTitle => 'Keskustele Omin kanssa';

  @override
  String get chatAppsTelegramStepOpen => 'Napauta alla Avaa Telegram';

  @override
  String get pleaseEnterValidPayPalMeLink => 'Syötä kelvollinen PayPal.me-linkki';

  @override
  String get syncFlowIntro =>
      'Tallenteet siirretään laitteeltasi tähän puhelimeen ja tallennetaan paikallisesti, minkä jälkeen ne ladataan Omin palvelimelle, jossa ne litteroidaan ja muunnetaan keskusteluiksi.';

  @override
  String get cantFindDeviceHint =>
      'Etkö löydä laitetta? Varmista, että se on päällä ja lähellä puhelinta, ja hae uudelleen.';

  @override
  String get tryAdjustingFilter => 'Yritä muokata hakuasi tai suodatinta';

  @override
  String get failedConnectionsRecent => 'Epäonnistuneet yhteydet (viimeiset 7 päivää)';

  @override
  String get captureSourceCall => 'Puhelu';

  @override
  String get storageLocationPhone => 'Puhelin';

  @override
  String get voiceMatchClose => 'Läheinen osuma';

  @override
  String get reviewChangeUndone => 'Kumottu. Omi ei toista tätä itse.';

  @override
  String get tasksNoProject => 'Ei projektia';

  @override
  String get dataAccessNotice => 'Tietojen käyttöilmoitus';

  @override
  String deviceStorageFree(String free) {
    return '$free vapaana';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'Jo viety kohteeseen $platform';
  }

  @override
  String get recapDeletedSnackbar => 'Yhteenveto poistettu';

  @override
  String get apiUrlRequired => 'API-URL vaaditaan';

  @override
  String get getOmiUnlimitedFree =>
      'Saat Omi Unlimited -tilauksen ilmaiseksi antamalla tietosi AI-mallien kouluttamiseen.';

  @override
  String get wrappedShare => 'Jaa';

  @override
  String get tasksTomorrow => 'Huomenna';

  @override
  String get chatAppsShowInAppOn => 'Päällä: ne näkyvät Omi-sovelluksessa vain luku -keskusteluina.';

  @override
  String get errorActivatingAppIntegration =>
      'Virhe sovelluksen aktivoinnissa. Jos kyseessä on integrointisovellus, varmista, että asennus on valmis.';

  @override
  String get readChatRepliesAloudDescription => 'Puhuu vain, kun Äänivastaus sen sallii.';

  @override
  String get addDueDate => 'Lisää eräpäivä';

  @override
  String get translated => 'käännetty';

  @override
  String get dontAskAgain => 'Älä kysy uudelleen';

  @override
  String get fullAccessScope => 'Täysi pääsy';

  @override
  String get firmwareUpdated => 'Laiteohjelmisto päivitetty';

  @override
  String get deviceOnboardingVoiceReplyPreviewThroughPhoneSpeaker => 'Puhelimen kaiuttimen kautta';

  @override
  String get prompt => 'Kehote';

  @override
  String get dreamReportDeletedItem => 'Poistettu kohde';

  @override
  String chatAppsDisconnectChannel(String app) {
    return 'Katkaise yhteys: $app';
  }

  @override
  String get appleHealthDeniedBody =>
      'Omilla ei ole oikeutta lukea Apple Health -tietojasi. Ota se käyttöön: iOS-asetukset → Yksityisyys ja turvallisuus → Health → Omi.';

  @override
  String endsOnDate(String date) {
    return 'Päättyy $date';
  }

  @override
  String get searchSettings => 'Etsi asetuksista';

  @override
  String get pairingDescNeoOne => 'Pidä virtapainiketta painettuna, kunnes LED vilkkuu. Laite on löydettävissä.';

  @override
  String get checkingNextSevenDays => 'Tarkistetaan seuraavat 7 päivää';

  @override
  String get confidenceLikely => 'Todennäköinen';

  @override
  String get appleHealthFeatureChatTitle => 'Keskustele terveydestäsi';

  @override
  String get loadingDevices => 'Ladataan laitteita…';

  @override
  String get writeSomething => 'Kirjoita jotain';

  @override
  String syncCardProgressOf(int current, int total) {
    return '$current / $total';
  }

  @override
  String get unableToOpenWatchApp =>
      'Apple Watch -sovellusta ei voi avata. Avaa Watch-sovellus manuaalisesti Apple Watchissa ja asenna Omi \"Saatavilla olevat sovellukset\" -osiosta.';

  @override
  String get dreamReportWouldFix => 'Korjaisi';

  @override
  String get doubleTap => 'Kaksoisnapautus';

  @override
  String get speakerTagPromptSomeoneElse => 'Joku muu…';

  @override
  String get cancelTransfer => 'Peruuta siirto';

  @override
  String get capabilityExternalIntegration => 'Ulkoinen integraatio';

  @override
  String get sttLanguageFollowsPrimary => 'Seuraa ensisijaista kieltäsi';

  @override
  String get wrappedCringeMomentTitle => 'Nolo hetki';

  @override
  String get allRecordingsSynced => 'Kaikki nauhoitukset synkronoitu';

  @override
  String get reviewConfirm => 'Vahvista';

  @override
  String get checkBackLaterForNewApps => 'Tarkista myöhemmin uudet sovellukset';

  @override
  String get referAFriend => 'Suosittele ystävälle';

  @override
  String cleanUpLead(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other:
          'Omi ei ole varma näistä $count henkilöstä. Useimmat ovat litteroinneista väärin kuultuja nimiä. Poista valinta niiltä, jotka haluat pitää.',
      one: 'Omi ei ole varma tästä henkilöstä. Poista valinta, jos haluat pitää hänet.',
    );
    return '$_temp0';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return 'Tee $item yksityiseksi?';
  }

  @override
  String get chatQuotaSubtitle => 'AI chat messages used with Omi this month.';

  @override
  String get failedTryAgain => 'Epäonnistui? Yritä uudelleen';

  @override
  String get deleteAllFiles => 'Poista kaikki tallenteet';

  @override
  String get onDeviceModelDownloadSuccess => 'Malli ladattu';

  @override
  String get reviewNoChangesTitle => 'Ei vielä muutoksia';

  @override
  String get useMobileAppToCapture => 'Käytä mobiilisovellusta äänen tallentamiseen';

  @override
  String get setYourName => 'Aseta nimesi';

  @override
  String get tasksGroupByDate => 'Ryhmittele päivämäärän mukaan';

  @override
  String get diagnosticsLast7Days => 'Viimeiset 7 päivää';

  @override
  String get deviceOnboardingStatusConnected => 'Yhdistetty';

  @override
  String get actionItemCreatedSuccessfully => 'Tehtävä luotu onnistuneesti';

  @override
  String get thursdayAbbr => 'To';

  @override
  String get wifiConfiguration => 'WiFi-asetukset';

  @override
  String get cancelReasonFoundAlternative => 'Löysin vaihtoehdon';

  @override
  String get process => 'Käsittele';

  @override
  String get help => 'Ohje';

  @override
  String get rollbackConfirmTitle => 'Palauta laiteohjelmisto?';

  @override
  String get visibility => 'Näkyvyys';

  @override
  String get evidenceNotHeard => 'Ei vielä kuultu keskustelussa';

  @override
  String get messageReported => 'Viesti ilmoitettu onnistuneesti.';

  @override
  String get readyToChat => '✨ Valmis chattailemaan!';

  @override
  String get tryDifferentFilter => 'Kokeile eri suodatinta';

  @override
  String get header => 'Otsikko';

  @override
  String get wrappedBestHeader => 'Parhaat';

  @override
  String get memoryDontUse => 'Älä käytä';

  @override
  String get appStore => 'App Store';

  @override
  String get deleteMeetingScreenshotMessage =>
      'Kuvakaappaus poistetaan tämän kokouksen muistiinpanosta. Toimintoa ei voi kumota.';

  @override
  String get categoryShopping => 'Ostokset';

  @override
  String get voiceResponseOff => 'Pois';

  @override
  String get bluetoothNeeded =>
      'Omi tarvitsee Bluetoothin yhdistääkseen puettavaan laitteeseesi. Ota Bluetooth käyttöön ja yritä uudelleen.';

  @override
  String get googleCalendarComingSoon => 'Google Kalenteri -integraatio tulossa pian!';

  @override
  String get max => 'Maks.';

  @override
  String get homeScreen => 'Aloitusnäyttö';

  @override
  String get chatAppsTelegramStepStart => 'Napauta Aloita keskustelussasi Omin kanssa';

  @override
  String get greetingAfternoon => 'Hyvää iltapäivää';

  @override
  String get unpair => 'Poista pariliitos';

  @override
  String get diagnosticsVerdictReconnects => 'Yhdistää itse uudelleen';

  @override
  String get macOsCalendar => 'macOS-kalenteri';

  @override
  String get onboardingSetupStepLanguage => 'Tekstitystä mukautetaan kielellesi';

  @override
  String get mcpOAuthSetup =>
      'Lisää claude.ai-palvelussa mukautettu liitin ja liitä palvelimen URL-osoite. Jos Claude pyytää edistynyttä OAuth Client ID:tä, käytä alla olevaa arvoa ja jätä salaisuus tyhjäksi — älä koskaan käytä MCP API -avaintasi OAuth-salaisuuksena.';

  @override
  String get wednesdayAbbr => 'Ke';

  @override
  String get selectAudioInput => 'Valitse äänitulo';

  @override
  String get deviceDisconnectedMessage => 'Omin yhteys on katkaistu 😔';

  @override
  String get reprocessConversation => 'Käsittele keskustelu uudelleen';

  @override
  String get goal => 'TAVOITE';

  @override
  String mergeConversationsMessage(int count) {
    return 'Tämä yhdistää $count keskustelua yhdeksi. Kaikki sisältö yhdistetään ja luodaan uudelleen.';
  }

  @override
  String get everyXSeconds => 'Joka x sekunti';

  @override
  String get chatAppsLocked => 'Vaatii Omi Pron';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl => 'Virheellinen luodun keskustelun webhook-URL';

  @override
  String get secureAuthViaAppleId => 'Turvallinen todennus Apple ID:n kautta';

  @override
  String connectingToDeviceName(String deviceName) {
    return 'Yhdistetään laitteeseen $deviceName';
  }

  @override
  String get listeningSubtitle => 'Kokonaisaika, jonka Omi on aktiivisesti kuunnellut.';

  @override
  String get capturing => 'Tallennetaan';

  @override
  String get enterWifiNetworkName => 'Syötä WiFi-verkon nimi';

  @override
  String get noAppsAvailable => 'Ei saatavilla olevia sovelluksia';

  @override
  String get installingFirmware => 'Asennetaan laiteohjelmistoa';

  @override
  String get transferToPhone => 'Siirrä puhelimeen';

  @override
  String get voiceResponseMode => 'Äänivastaus';

  @override
  String get messageCopied => '✨ Viesti kopioitu leikepöydälle';

  @override
  String get discardRecordingMessage => 'Ääninäytettäsi ei ole vielä tallennettu. Jos poistut nyt, se hylätään.';

  @override
  String chatAppsIMessageBody(String code) {
    return 'Hei Omi, linkityskoodi $code';
  }

  @override
  String get failedToRefreshWhoopStatus => 'Whoop-yhteyden tilan päivitys epäonnistui.';

  @override
  String get youreOnAnnualPlan => 'Sinulla on vuositilaus';

  @override
  String timeHoursPlural(int count) {
    return '$count tuntia';
  }

  @override
  String get usageOnline => 'Verkossa';

  @override
  String get validPortRequired => 'Kelvollinen portti vaaditaan';

  @override
  String get howItWorks => 'Miten se toimii';

  @override
  String get viewTemplate => 'Näytä malli';

  @override
  String get dreamReportNothingFound => 'Ei korjattavaa';

  @override
  String get personTalkTime => 'Puheaika';

  @override
  String get evidenceNoVoice => 'Ei vielä ääninäytettä';

  @override
  String get makeMyAppPublic => 'Tee sovelluksestani julkinen';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'Bluetooth-luvan tila: $status. Tarkista Järjestelmäasetukset.';
  }

  @override
  String get noRecordings => 'Ei nauhoituksia';

  @override
  String get usageChatThisMonth => 'Chat this month';

  @override
  String get addAppEnterChatPrompt => 'Syötä chat-kehote sovelluksellesi';

  @override
  String daysAgo(int count) {
    return '$count päivää sitten';
  }

  @override
  String get processing => 'Käsitellään';

  @override
  String get deviceOnboardingStatusTurningOff => 'Sammutetaan…';

  @override
  String get newTag => 'UUSI';

  @override
  String get permissionDescReadTasks => 'Tämä sovellus voi käyttää tehtäviäsi.';

  @override
  String get time => 'Aika';

  @override
  String get recording => 'Tallennetaan';

  @override
  String get speakerTagPromptWhoIsThis => 'Kuka tämä on?';

  @override
  String chatUsageMessagesNoLimit(String used) {
    return 'Chat: $used viestiä tässä kuussa';
  }

  @override
  String get importantTradeoffs => 'Tärkeät kompromissit:';

  @override
  String get makeAllPublic => 'Tee kaikki muistot julkisiksi';

  @override
  String get noSpeechDesc =>
      'Emme voineet havaita mitään puhetta. Varmista, että puhut vähintään 10 sekuntia ja korkeintaan 3 minuuttia.';

  @override
  String get searchPartialFailure => 'Joitakin tuloksia ei voitu ladata';

  @override
  String get prerecordedTranscript => 'Esitallenne';

  @override
  String get confirm => 'Vahvista';

  @override
  String get statusCalling => 'Soitetaan…';

  @override
  String get wrappedConvos => 'keskustelua';

  @override
  String get unresolvedSpeakersTitle => 'Tietoa puhujamerkinnöistä';

  @override
  String get writeYourReply => 'Kirjoita vastauksesi…';

  @override
  String get localCopiesSection => 'Paikalliset kopiot';

  @override
  String get noSummaryYet => 'Ei yhteenvetoa vielä';

  @override
  String get wrappedBiggestHeader => 'Suurin';

  @override
  String get error => 'Virhe';

  @override
  String get deviceWillRestart => 'Laite käynnistyy uudelleen.';

  @override
  String get consentDataMessage =>
      'Jatkamalla keskustelusi, tallenteet ja henkilötietosi tallennetaan turvallisesti palvelimillemme. Äänitallenteitasi ja transkriptioitasi käsittelevät kolmannen osapuolen tekoälypalvelut (mukaan lukien Deepgram transkriptiota ja OpenAI analyysiä varten) tarjotaksemme sinulle tekoälypohjaisia oivalluksia ja mahdollistaaksemme kaikki sovelluksen ominaisuudet.';

  @override
  String get connectMacOsCalendar => 'Yhdistä paikallinen macOS-kalenterisi';

  @override
  String get captureSourcePhoneMic => 'Puhelimen mikrofoni';

  @override
  String get setupCompleted => 'Valmis';

  @override
  String get installOmiOnAppleWatchDescription =>
      'Käyttääksesi Apple Watchia Omin kanssa, sinun on ensin asennettava Omi-sovellus kelloosi.';

  @override
  String get toggleControlBar => 'Vaihda ohjausp alkki';

  @override
  String get onboardingBluetoothDeniedSystemPrefs => 'Bluetooth-lupa evätty. Myönnä lupa Järjestelmäasetuksissa.';

  @override
  String get syncCancelled => 'Synkronointi peruutettu';

  @override
  String get firmwareDisconnectUsb => 'Irrota USB';

  @override
  String get processNow => 'Käsittele nyt';

  @override
  String get appIdNotFoundError => 'Sovelluksen tunnusta ei löytynyt';

  @override
  String get editDueDate => 'Muokkaa eräpäivää';

  @override
  String get home => 'Koti';

  @override
  String get tasksOverdue => 'Myöhässä';

  @override
  String get statusCompleted => 'Valmis';

  @override
  String get otaStarting => 'Aloitetaan päivitystä…';

  @override
  String get monthApr => 'Huhti';

  @override
  String get conversationTasksEmptyMessage => 'Tämän keskustelun tehtävät näkyvät täällä.';

  @override
  String get useDifferentAccount => 'Käytä toista tiliä';

  @override
  String get reviewReasonNotUseful => 'Ei hyödyllinen';

  @override
  String get anonymousUser => 'Anonyymi käyttäjä';

  @override
  String get viewPlansDescription => 'Hallitse tilaustasi ja katso käyttötilastoja';

  @override
  String invalidJson(String error) {
    return 'Virheellinen JSON: $error';
  }

  @override
  String get deleteActionItem => 'Poista tehtävä';

  @override
  String get confirmCancellation => 'Vahvista peruutus';

  @override
  String get tapToDelete => 'Napauta poistaaksesi';

  @override
  String get onTheCallEnterThisCode => 'Syota tama koodi puhelun aikana';

  @override
  String get stableFirmware => 'Vakaa laiteohjelmisto';

  @override
  String get triggerEvents => 'Käynnistävät tapahtumat';

  @override
  String get speakerTagPromptSaveVoicesTitle => 'Muista nimeämiesi ihmisten äänet';

  @override
  String get syncedFilesDeleted => 'Synkronoidut tallenteet poistettu';

  @override
  String get cloudStorageDesc =>
      'Lataamisen jälkeen nauhoituksesi käsitellään ja litteroidaan. Keskustelut ovat saatavilla minuutin kuluessa.';

  @override
  String get failedToUpdateFolder => 'Kansion päivittäminen epäonnistui';

  @override
  String dreamReportFound(int fixes, int asks) {
    String _temp0 = intl.Intl.pluralLogic(
      fixes,
      locale: localeName,
      other: '$fixes korjausta',
      one: '1 korjaus',
    );
    String _temp1 = intl.Intl.pluralLogic(
      asks,
      locale: localeName,
      other: '$asks ehdotusta',
      one: '1 ehdotus',
    );
    return '$_temp0 · $_temp1';
  }

  @override
  String get anotherPlatform => 'toiseen alustaan';

  @override
  String get wrappedTopPhrasesLabel => 'TOP LAUSEET';

  @override
  String get dataAccessWarning =>
      'Tämä sovellus käyttää tietojasi. Omi AI ei ole vastuussa siitä, miten tietojasi käytetään, muokataan tai poistetaan tällä sovelluksella';

  @override
  String get pleaseCompleteAuthentication => 'Viimeistele todennus selaimessasi. Kun olet valmis, palaa sovellukseen.';

  @override
  String get dailySummaryTitle => 'Päivittäinen Yhteenveto';

  @override
  String get managePeople => 'Hallitse henkilöitä';

  @override
  String get dreamReportEmptyBody => 'Dream tarkistaa tilisi muutokset noin kerran tunnissa.';

  @override
  String get couldNotOpenPaymentSettings => 'Maksuasetuksia ei voitu avata. Yritä uudelleen.';

  @override
  String get locationServiceDisabled => 'Sijaintipalvelu poistettu käytöstä';

  @override
  String get understanding => 'Ymmärtäminen';

  @override
  String get recapDeleteFailed => 'Yhteenvetoa ei voitu poistaa. Yritä myöhemmin uudelleen.';

  @override
  String get deleteKnowledgeGraphQuestion => 'Poistetaanko tietograafi?';

  @override
  String get wrappedYourBuddy => 'Kaverisi!';

  @override
  String chatAppsChatIn(String app) {
    return 'Keskustelu sovelluksessa $app';
  }

  @override
  String get speechDurationDescription => 'Varmista, että puhut vähintään 5 sekuntia ja enintään 90.';

  @override
  String get reviewReasonAlreadyDone => 'Jo tehty';

  @override
  String get phoneSetupStep2Title => 'Syota vahvistuskoodi';

  @override
  String get tasksClearCompleted => 'Tyhjennä valmiit';

  @override
  String get searchingForDevices => 'Etsitään laitteita';

  @override
  String get siriIndexSettingDescription =>
      'Allow Siri to find your conversations, memories, and tasks on this device. Turning this off removes them from Apple search.';

  @override
  String get markIncomplete => 'Merkitse keskeneräiseksi';

  @override
  String get onboardingBluetoothRequired => 'Bluetooth-lupa vaaditaan laitteeseen yhdistämiseen.';

  @override
  String get searchAppsPlaceholder => 'Hae yli 1500 sovelluksesta';

  @override
  String get pleaseEnterName => 'Anna nimi';

  @override
  String get paymentMethodCharged => 'Nykyinen maksutapasi veloitetaan automaattisesti kuukausitilauksesi päättyessä';

  @override
  String get allMemoriesAreNowPublic => 'Kaikki muistot ovat nyt julkisia';

  @override
  String taskDueDate(String date) {
    return 'Määräpäivä $date';
  }

  @override
  String get pendantPausesUntilYouFinish => 'Riipus on tauolla, kunnes lopetat';

  @override
  String get failedToAuthorize => 'Valtuutus epäonnistui. Yritä uudelleen.';

  @override
  String get mergeConversationsSuccessTitle => 'Keskustelut yhdistetty onnistuneesti';

  @override
  String get peopleFilterNeedsVoice => 'Ääni puuttuu';

  @override
  String get clickToBeginRecordingSystemAudio => 'Napsauta aloittaaksesi järjestelmän äänitallennus';

  @override
  String get fairUseStageRestrict => 'Estetty';

  @override
  String get nextResult => 'Seuraava tulos';

  @override
  String get chatAppsContactsApp => 'Yhteystiedot';

  @override
  String get categoryEmotionalSupport => 'Tunnetuki';

  @override
  String get wrappedYourHeader => 'Sinun';

  @override
  String get pendantPausesDuringCall => 'Riipus on tauolla puhelun ajan';

  @override
  String noConversationsOnDate(String date) {
    return 'Ei keskusteluja päivämäärällä $date';
  }

  @override
  String get chatStarterYesterday => 'Mitä tein eilen?';

  @override
  String get entityNotRight => 'Eikö oikein?';

  @override
  String get failedToCreateShareLink => 'Jakolinkin luominen epäonnistui';

  @override
  String get sync => 'Synkronoi';

  @override
  String get micGainDescMax => 'Maksimi - käytä varoen';

  @override
  String get sttNone => 'Ei mitään';

  @override
  String get chatAppsCodeNote => 'Koodi toimii vain kerran ja vanhenee 10 minuutissa.';

  @override
  String get aiGenAppCreatedSuccessfully => 'Sovellus luotu onnistuneesti!';

  @override
  String lastNEvents(int count) {
    return 'Viimeiset $count tapahtumaa';
  }

  @override
  String get phoneDeleteButton => 'Poista';

  @override
  String get systemAudio => 'Järjestelmä';

  @override
  String get checkOutMyMemoryGraph => 'Katso muistigraafikani!';

  @override
  String get feedbackTitleBatteryDrain => 'Kerro meille akkuongelmista';

  @override
  String get startCallRecording => 'Aloita puhelun nauhoitus';

  @override
  String get monthlyPlanContinues => 'Nykyinen kuukausitilauksesi jatkuu laskutusjakson loppuun asti';

  @override
  String get syncStepUploadDesc => 'Tallenteesi lähetetään Omin palvelimelle';

  @override
  String get otaKeepNearby => 'Pidä laite päivityksen ajan päällä ja lähellä, äläkä sulje sovellusta.';

  @override
  String get updatePayPalDetails => 'Päivitä PayPal-tiedot';

  @override
  String get termsOfUse => 'Käyttöehdot';

  @override
  String get apiKeyCreated => 'API-avain luotu!';

  @override
  String get deviceOnboardingVoiceReplyPreviewIdle => 'Kuuntele viimeinen vastauksesi';

  @override
  String get starOngoing => 'Merkitse käynnissä oleva keskustelu tähdellä';

  @override
  String get largeModelWarning =>
      'Tämä malli on suuri ja saattaa kaataa sovelluksen tai toimia erittäin hitaasti mobiililaitteilla.\n\n\"small\" tai \"base\" on suositeltu.';

  @override
  String get selectLanguage => 'Valitse kieli';

  @override
  String get professionExecutive => 'Johtaja';

  @override
  String get importFileTooLarge => 'Tämä tiedosto on liian suuri tuotavaksi.';

  @override
  String get updateRequiredTitle => 'Päivitys vaaditaan';

  @override
  String get syncStepBackedUp => 'Keskustelu valmis';

  @override
  String get openWatchApp => 'Avaa Watch-sovellus';

  @override
  String get keyNameLabel => 'AVAIMEN NIMI';

  @override
  String bulkExportSuccess(int count, String platform) {
    return 'Viety $count kohteeseen $platform';
  }

  @override
  String get couldNotProcessSubscription => 'Tilausta ei voitu käsitellä. Yritä uudelleen.';

  @override
  String get memorizingYourVoice => 'Tallennetaan ääntäsi…';

  @override
  String get processingAudio => 'Käsitellään ääntä';

  @override
  String get syncYourRecordings => 'Synkronoi tallenteet';

  @override
  String get resetToDefault => 'Palauta oletusarvoon';

  @override
  String get deleteConversation => 'Poista keskustelu';

  @override
  String get flashCustomFirmwareDescription => 'Asenna mukautettuja laiteohjelmistoversioita';

  @override
  String get deviceUpToDate => 'Laitteesi on ajan tasalla';

  @override
  String get raybanMetaMusicPauseNote => 'Puhelimesi musiikki keskeytyy, kun lasien mikrofoni on käytössä.';

  @override
  String get appleHealthNotAvailable => 'Apple Health ei ole käytettävissä tässä laitteessa';

  @override
  String hints(String text) {
    return 'Vihjeet: $text';
  }

  @override
  String get cloudProvider => 'Pilvipalveluntarjoaja';

  @override
  String get chooseAnyFileType => 'Valitse mikä tahansa tiedostotyyppi';

  @override
  String get reset => 'Nollaa';

  @override
  String get automaticallyCreateNewPerson => 'Luo automaattisesti uusi henkilö, kun litterointiin havaitaan nimi.';

  @override
  String get timeout2Minutes => '2 minuuttia';

  @override
  String get newMemory => '✨ Uusi muisti';

  @override
  String get chatAppsMoreComing => 'Lisää sovelluksia on tulossa.';

  @override
  String get couldNotLoadKnowledgeGraph => 'Tietograafia ei voitu ladata';

  @override
  String get voiceSettingsAskToTagSubtitle => 'Silloin tällöin Omi kysyy, kuka puhui viimeaikaisissa keskusteluissasi';

  @override
  String get developer => 'Kehittäjä';

  @override
  String get connectionNeeded => '🌐 Yhteys vaaditaan';

  @override
  String get helpAndAbout => 'Ohje ja tietoja';

  @override
  String get tasksNoDeadline => 'Ei määräaikaa';

  @override
  String get yourDataIsProtected => 'Tietosi ovat suojattuja ja niitä säätelee ';

  @override
  String get confirmDeletion => 'Vahvista poisto';

  @override
  String get speakerTagPromptClosestVoices => 'Lähimmät äänet';

  @override
  String get quicklyPopulateRequest => 'Täytä nopeasti tunnetulla palveluntarjoajan pyyntömuodolla';

  @override
  String get exportTranscript => 'Vie litterointi';

  @override
  String get resetsSoon => 'Nollautuu pian';

  @override
  String get showPhoneCallButtonTitle => 'Näytä puhelupainike';

  @override
  String get wrappedAChallenge => 'Haaste';

  @override
  String get revokeKey => 'Peruuta avain';

  @override
  String get dailyRecaps => 'Päivittäiset Yhteenvedot';

  @override
  String get processingConversationProgress => 'Keskustelua käsitellään…';

  @override
  String get freeMinutesMonth => '300 ilmaisminuuttia kuukaudessa mukana. Rajoittamaton ';

  @override
  String get downloadWhisperModel => 'Lataa whisper-malli käyttääksesi laitteella tapahtuvaa transkriptiota';

  @override
  String get noMemoriesInCategories => 'Ei muistoja näissä kategorioissa';

  @override
  String get checkingNextDays => 'Tarkistetaan seuraavat 30 päivää';

  @override
  String get createAndSubmitNewApp => 'Luo ja lähetä uusi sovellus';

  @override
  String get chatAppsInTheMeantime => 'Sillä välin';

  @override
  String get deleteFlowReasonTitle => 'Miksi lähdet?';

  @override
  String get tasksSelectAll => 'Valitse kaikki';

  @override
  String get webhookUrl => 'Webhookin URL';

  @override
  String get selected => 'Valittu';

  @override
  String get batteryDrainIncrease => 'Akun kulutus kasvaa merkittävästi.';

  @override
  String get dreamReportFixed => 'Korjattu';

  @override
  String get failedToConnectClickUpRetry => 'Yhteyden muodostaminen ClickUpiin epäonnistui. Yritä uudelleen.';

  @override
  String get serverUrl => 'Palvelimen URL';

  @override
  String get starred => 'Tähdellä merkitty';

  @override
  String get speakerTagPromptClipUnavailable => 'Leikettä ei voitu toistaa';

  @override
  String get feedbackSubtitleFoundAlternative => 'Haluaisimme tietää, mikä kiinnitti huomiosi.';

  @override
  String get omiButtonActions => 'Omi-painikkeen toiminnot';

  @override
  String get invalidRecordingDesc => 'Varmista, että puhut vähintään 5 sekuntia ja korkeintaan 90 sekuntia.';

  @override
  String get switchApiConfirmTitle => 'Vaihda API-ympäristö';

  @override
  String gattError(String code) {
    return 'GATT-virhe ($code)';
  }

  @override
  String get aiGenRegenerateIcon => 'Luo kuvake uudelleen';

  @override
  String get connectTaskAppToExport => 'Yhdistä tehtäväsovellus Asetuksissa vientiä varten';

  @override
  String get firmwareFlashed => 'Laiteohjelmisto asennettu';

  @override
  String get addPerson => 'Lisää henkilö';

  @override
  String get cancelConsequencesSubtitle =>
      'Suosittelemme vahvasti tutustumaan muihin vaihtoehtoihisi peruutuksen sijaan.';

  @override
  String get transcriptCopiedToClipboard => 'Litterointi kopioitu leikepöydälle';

  @override
  String get monthNov => 'Marras';

  @override
  String get switchedToOnDevice => 'Vaihdettu laitteen transkriptioon';

  @override
  String get phoneMicOfflineFallbackMessage =>
      'Ei yhteyttä – tallennetaan paikallisesti. Litterointi tehdään, kun olet taas verkossa.';

  @override
  String get scopeUserConversations => 'Käyttäjän keskustelut';

  @override
  String get otherAppResults => 'Muiden sovellusten tulokset';

  @override
  String get chatAppsGetNewCode => 'Hae uusi koodi';

  @override
  String get backgroundLocationDenied => 'Taustasijaintipääsy evätty';

  @override
  String get syncFailureFootnote =>
      'Jos käsittely epäonnistuu, tallenne yritetään automaattisesti uudelleen seuraavan synkronoinnin yhteydessä.';

  @override
  String get checkingNext7Days => 'Tarkistetaan seuraavat 7 päivää';

  @override
  String get monthlyPayouts => 'Kuukausittaiset maksut';

  @override
  String get searchLanguageHint => 'Etsi kieltä nimen tai koodin perusteella';

  @override
  String get gotIt => 'Selvä';

  @override
  String get pleaseEnterAppName => 'Anna sovelluksen nimi';

  @override
  String get newConversations => 'Uudet keskustelut';

  @override
  String get learnMoreAtOmiTraining => 'Lue lisää osoitteessa omi.me/training';

  @override
  String get entityOpenTasks => 'Avoimet tehtävät';

  @override
  String get summary => 'Yhteenveto';

  @override
  String get copied => 'Kopioitu';

  @override
  String get feedbackReasonRecordingDelayedOrStuck => 'Delayed or stuck';

  @override
  String get taskIntegrations => 'Tehtäväintegraatiot';

  @override
  String get tailoredConversationSummaries => 'Räätälöidyt keskusteluyhteenvedot';

  @override
  String get skipThisQuestion => 'Ohita tämä kysymys';

  @override
  String get descriptionOptional => 'Kuvaus (valinnainen)';

  @override
  String get about => 'Tietoja';

  @override
  String shareWithContactsCount(int count) {
    return 'Jaa $count yhteystiedolle';
  }

  @override
  String get discardChangesTitle => 'Hylätäänkö muutokset?';

  @override
  String get transcriptionDiagnostics => 'Litterointidiagnostiikka';

  @override
  String get syncStatusFileUnavailable => 'Tiedosto ei ole käytettävissä';

  @override
  String get createNewApp => 'Luo uusi sovellus';

  @override
  String verifiedHoursAgo(int hours) {
    return 'Vahvistettu ${hours}t sitten';
  }

  @override
  String get chatLimitReachedTitle => 'Chat-raja saavutettu';

  @override
  String get wrappedShareText => 'Vuoteni 2025, tallentanut Omi ✨ omi.me/wrapped';

  @override
  String get reconnectionsRecent => 'Uudelleenyhdistykset (viimeiset 7 päivää)';

  @override
  String get appAccess => 'Sovelluspääsy';

  @override
  String get description => 'Kuvaus';

  @override
  String phoneFreeCallsRemainingWithMax(int remaining, int limit, int minutes) {
    return '$remaining/$limit ilmaista puhelua jäljellä tässä kuussa · enintään $minutes min kukin';
  }

  @override
  String get clearOmisMemory => 'Tyhjennä Omin muisti';

  @override
  String get exportSummary => 'Vie yhteenveto';

  @override
  String get install => 'Asenna';

  @override
  String get syncStepBackedUpDesc => 'Löydät sen kohdasta Keskustelut';

  @override
  String get localProcessingInfo =>
      'Ääni käsitellään paikallisesti. Toimii offline-tilassa, yksityisempi, mutta kuluttaa enemmän akkua.';

  @override
  String get connectStripeOrPayPal => 'Yhdistä Stripe tai PayPal vastaanottaaksesi maksuja sovelluksestasi.';

  @override
  String get wrappedMomentsHeader => 'Hetket';

  @override
  String get systemDefault => 'Järjestelmän oletus';

  @override
  String get keepUsingPendant => 'Jatka riipuksella';

  @override
  String get paymentFailedToFetchCountries => 'Tuettujen maiden haku epäonnistui. Yritä myöhemmin uudelleen.';

  @override
  String get micGainDescLow => 'Erittäin hiljainen - meluisiin ympäristöihin';

  @override
  String get errorUpdatingConversationTitle => 'Virhe keskustelun otsikon päivityksessä';

  @override
  String timeSecsSingular(int count) {
    return '$count sek';
  }

  @override
  String timeCompactHours(int count) {
    return '${count}t';
  }

  @override
  String get browseInstallCreateApps => 'Selaa, asenna ja luo sovelluksia';

  @override
  String get reddit => 'Reddit';

  @override
  String get chooseFile => 'Valitse tiedosto';

  @override
  String participantsSummary(String name, int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count muuta',
      many: '$count muuta',
      few: '$count muuta',
      one: '1 muu',
    );
    return '$name + $_temp0';
  }

  @override
  String get connectingYourStripeAccount => 'Stripe-tilisi yhdistäminen';

  @override
  String get cancelReasonMissingFeatures => 'Puuttuvat ominaisuudet';

  @override
  String get chatTitle => 'Chat';

  @override
  String get chatAppsNotifyMe => 'Ilmoita minulle';

  @override
  String get appAccessDesc =>
      'Seuraavat sovellukset voivat käyttää tietojasi. Napauta sovellusta hallitaksesi sen käyttöoikeuksia.';

  @override
  String get captureDisplayDetectionFailed => 'Näytön tunnistus epäonnistui. Tallennus pysäytetty.';

  @override
  String get recapRegeneratedSnackbar => 'Yhteenveto luotu uudelleen';

  @override
  String get speakerTagPromptLabeledYouToast => 'Nimetty sinuksi';

  @override
  String get categoryFinancial => 'Talous';

  @override
  String get chatAppsPrefilled => 'Esitäytetty';

  @override
  String get noSummaryForConversation => 'Tälle keskustelulle\nei ole tiivistelmää.';

  @override
  String get aiPrompts => 'Tekoälykehotukset';

  @override
  String get view => 'Näytä';

  @override
  String get dataAlwaysEncrypted => 'Tasosta riippumatta tietosi ovat aina salattuja levossa ja siirrettäessä.';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item kopioitu leikepöydälle';
  }

  @override
  String get currentPlan => 'Nykyinen';

  @override
  String get phoneCallsUpsellFeature1 => 'Jokaisen puhelun reaaliaikainen litterointi';

  @override
  String get lowBatteryAlertTitle => 'Alhaisen akun varoitus';

  @override
  String get enterConversationTitle => 'Syötä keskustelun otsikko…';

  @override
  String get pasteJsonConfig => 'Liitä JSON-kokoonpanosi alle:';

  @override
  String get dreamReportRunLimit => 'Ei manuaalisia ajoja jäljellä tänään';

  @override
  String get translationNoticeMessage =>
      'Omi kääntää keskustelut ensisijaiselle kielellesi. Päivitä se milloin tahansa kohdassa Asetukset → Profiilit.';

  @override
  String get aiGenFailedToRegenerateIcon => 'Kuvakkeen uudelleenluominen epäonnistui';

  @override
  String get pairingDescBee => 'Paina painiketta 5 kertaa peräkkäin. Valo alkaa vilkkua sinisenä ja vihreänä.';

  @override
  String sharedTasksAddButton(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Lisää $count tehtävää',
      one: 'Lisää 1 tehtävä',
    );
    return '$_temp0';
  }

  @override
  String get paymentFailedToSavePaypal => 'PayPal-tietojen tallennus epäonnistui. Yritä myöhemmin uudelleen.';

  @override
  String get couldNotLoadCheckout => 'Maksusivua ei voitu ladata. Tarkista yhteys ja yritä uudelleen.';

  @override
  String get capabilitySummary => 'Yhteenveto';

  @override
  String get selectYourCountry => 'Valitse maasi';

  @override
  String uploadingAudioForTranscription(String duration) {
    return 'Lähetetään $duration ääntä litteroitavaksi…';
  }

  @override
  String get conversationUrlCouldNotBeShared => 'Keskustelun URL-osoitetta ei voitu jakaa.';

  @override
  String get otaStartFailed => 'Päivitystä ei voitu aloittaa. Tarkista Wi-Fin nimi ja salasana ja yritä uudelleen.';

  @override
  String get triggersWhenAudioBytesReceived => 'Käynnistyy, kun äänitavut vastaanotetaan.';

  @override
  String get wrappedMy2025 => 'Vuoteni 2025';

  @override
  String timeCompactSecs(int count) {
    return '${count}s';
  }

  @override
  String get shareWithAttendees => 'Jaa osallistujille';

  @override
  String get recordingsSyncAutomatically => 'Nauhoitukset synkronoidaan automaattisesti — toimenpiteitä ei tarvita.';

  @override
  String get whereDidYouHearAboutOmi => 'Miten löysit meidät?';

  @override
  String get captureMicrophonePermissionInSystemPreferences => 'Myönnä mikrofonin käyttöoikeus Järjestelmäasetuksissa';

  @override
  String audioUploadFailedTapRetry(String duration) {
    return 'Lähetys epäonnistui — $duration ääntä on tallessa puhelimessasi. Yritä uudelleen napauttamalla.';
  }

  @override
  String get captureModeLaterDescription => 'Tallenna ääni nyt ja litteroi milloin haluat.';

  @override
  String get cleanUpNothingTitle => 'Ei siivottavaa';

  @override
  String get deletePersonLabel => 'Poista henkilö';

  @override
  String get attachedFiles => '📎 Liitetyt tiedostot';

  @override
  String get editGoal => 'Muokkaa tavoitetta';

  @override
  String get helpsDiagnoseIssues => 'Auttaa ongelmien diagnosoinnissa';

  @override
  String get bulkDeleteFailed => 'Tehtävien poistaminen epäonnistui. Yritä uudelleen.';

  @override
  String get manifestRefreshFailed => 'Manifestin päivitys epäonnistui';

  @override
  String get searchPlaceholder => 'Etsi';

  @override
  String get appOptions => 'Sovelluksen valinnat';

  @override
  String get reprocessingConversationProgress => 'Keskustelua käsitellään uudelleen…';

  @override
  String get entityWhatOmiKnows => 'Mitä Omi tietää';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'Keskustelu tiivistetään $minutes minuuti$suffix hiljaisuuden jälkeen.';
  }

  @override
  String get permissionRevokedMessage => 'Haluatko meidän poistavan myös kaikki olemassa olevat nauhoituksesi?';

  @override
  String get phoneNumberCallerIdHint => 'Vahvistuksen jalkeen tasta tulee soittajatunnuksesi';

  @override
  String chatAppsTextThisTo(String address) {
    return 'Ei avautunut? Lähetä tämä numeroon $address';
  }

  @override
  String get upcomingMeetings => 'Tulevat tapaamiset';

  @override
  String get preparingSystemAudioCapture => 'Järjestelmän äänitallennus valmistellaan';

  @override
  String dreamReportQueued(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count muutosta odottaa',
      one: '1 muutos odottaa',
      zero: 'Ei odottavia muutoksia',
    );
    return '$_temp0';
  }

  @override
  String get chatReplyFailed => 'Omi ei voinut vastata. Tarkista yhteys ja yritä uudelleen.';

  @override
  String get noDataToMigrateFinalizing => 'Ei dataa siirrettäväksi. Viimeistellään…';

  @override
  String get accessibility => 'Esteettömyys';

  @override
  String get openOmiOnAppleWatch => 'Avaa Omi\nApple Watchissa';

  @override
  String get wrappedGettingItDone => 'Asian hoitaminen';

  @override
  String get rawData => 'Raakadata';

  @override
  String get passwordsDoNotMatch => 'Salasanat eivät täsmää';

  @override
  String errorInstallingApp(String appName, String error) {
    return 'Virhe asennettaessa $appName: $error';
  }

  @override
  String deleteQuoted(String name) {
    return 'Poista \"$name\"';
  }

  @override
  String get wrappedTopFivePhrases => 'Top 5 lausetta';

  @override
  String get deviceOnboardingHoldButtonHint => 'Pidä painiketta tiukasti pohjassa, kunnes valo sammuu';

  @override
  String get capabilities => 'Ominaisuudet';

  @override
  String get useMcpApiKey => 'Käytä MCP API-avainta';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return '$serviceName-integraatio tulossa pian';
  }

  @override
  String get wrappedStruggle => 'Haaste';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return 'Ilmoitusluvan tila: $status. Tarkista Järjestelmäasetukset.';
  }

  @override
  String get meetingScreenshotsTitle => 'Mitä näytöllä oli';

  @override
  String verifiedMinutesAgo(int minutes) {
    return 'Vahvistettu ${minutes}min sitten';
  }

  @override
  String get permissionsRequired => 'Käyttöoikeudet vaaditaan';

  @override
  String get speakerTagPromptNotSure => 'En ole varma';

  @override
  String get current => 'Nykyinen';

  @override
  String get improveConnectionAction => 'Selvä';

  @override
  String get profile => 'Profiili';

  @override
  String get audioPlaybackFailed => 'Ääntä ei voi toistaa. Tiedosto saattaa olla vioittunut tai puuttua.';

  @override
  String get billingYearly => 'Vuosittain';

  @override
  String get batteryUsageHigher => 'Akunkäyttö on korkeampi kuin pilvitranskriptiossa.';

  @override
  String get permissionsLabel => 'OIKEUDET';

  @override
  String get enhanceTranscriptAccuracy => 'Paranna litterointitarkkuutta';

  @override
  String get connectedStatus => 'Yhdistetty';

  @override
  String get microphonePermissionDenied =>
      'Mikrofonin lupa evätty. Anna lupa kohdassa Järjestelmäasetukset > Tietosuoja ja turvallisuus > Mikrofoni.';

  @override
  String get onDeviceModelDownloadSuccessDesc => 'Whisper-malli ladattiin onnistuneesti';

  @override
  String get storageLocationLimitlessPendant => 'Limitless Pendant';

  @override
  String get chatAppsLinkExpired => 'Linkki vanheni. Napauta Avaa Telegram saadaksesi uuden.';

  @override
  String get captureOfflineBuffering => 'Offline, puskuroidaan';

  @override
  String get pleaseCheckInternetConnection => 'Tarkista internet-yhteytesi ja yritä uudelleen';

  @override
  String get todaysScore => 'Tämän päivän pisteet';

  @override
  String get conversationReprocessed => 'Keskustelu päivitetty';

  @override
  String get loadingDuration => 'Ladataan kestoa…';

  @override
  String get noSummary => 'Ei yhteenvetoa';

  @override
  String get raybanMetaMicrophoneReady => 'Mikrofoni valmis';

  @override
  String get applyFilters => 'Käytä suodattimia';

  @override
  String get appDescriptionPlaceholder =>
      'Upea sovellukseni on loistava sovellus, joka tekee hämmästyttäviä asioita. Se on paras sovellus!';

  @override
  String get cancelSubscriptionKeepAccessMessage => 'Käyttöoikeus säilyy nykyisen laskutuskauden loppuun.';

  @override
  String get editYourReview => 'Muokkaa arvostelua';

  @override
  String get actionItemsTitle => 'Tehtävät';

  @override
  String get raybanMetaAudioOnlyTitle => 'Ray-Ban Metan vain ääni -tila';

  @override
  String get reviewSomeoneElse => 'Joku muu…';

  @override
  String get betaTesterMessage =>
      'Olet tämän sovelluksen beta-testaaja. Se ei ole vielä julkinen. Se julkaistaan hyväksynnän jälkeen.';

  @override
  String chatAppsIMessageTo(String address) {
    return 'Vastaanottaja: Omi · $address';
  }

  @override
  String get comingSoon => 'Tulossa pian';

  @override
  String rollbackConfirmMessage(String version) {
    return 'Tämä korvaa nykyisen laiteohjelmiston uusimmalla vakaalla versiolla ($version). Laitteesi käynnistyy uudelleen päivityksen jälkeen.';
  }

  @override
  String get termsOfService => 'Käyttöehdot';

  @override
  String get wrappedNotMentioned => 'Ei mainittu';

  @override
  String get deviceDisconnectedNotificationTitle => 'Omi-laitteesi yhteys katkesi';

  @override
  String get rayBanMetaMicPickerDescription =>
      'Valitse lasiesi Bluetooth-mikrofoni. Musiikki keskeytyy, kun Omi käyttää sitä.';

  @override
  String get chatBlockQuestion => 'Kysymys';

  @override
  String get successfullyConnectedTodoist => 'Yhdistetty onnistuneesti Todoistiin!';

  @override
  String voiceRecognitionStatus(String status) {
    String _temp0 = intl.Intl.selectLogic(
      status,
      {
        'ready': 'Ääni on valmis tunnistettavaksi',
        'saved_sample_awaiting_embedding': 'Näyte tallennettu, äänen käsittelyä tarvitaan vielä',
        'not_learned': 'Ääntä ei ole opittu',
        'other': 'Äänen tila tuntematon',
      },
    );
    return '$_temp0';
  }

  @override
  String addQueryAsNewPerson(String query) {
    return 'Lisää \"$query\" uutena henkilönä';
  }

  @override
  String confidenceReasonAutoConfirmed(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Vahvistit $count automaattista merkintää',
      one: 'Vahvistit 1 automaattisen merkinnän',
    );
    return '$_temp0';
  }

  @override
  String get recordAudioConversations => 'Tallenna äänikeskusteluja';

  @override
  String get saveKeyWarning => 'Tallenna tämä avain nyt! Et näe sitä enää uudelleen.';

  @override
  String get saveChanges => 'Tallenna muutokset';

  @override
  String get sttModelSlower => 'Hitaampi';

  @override
  String get otaDownloadFailed => 'Laiteohjelmiston lataus epäonnistui. Tarkista Wi-Fi-yhteys ja yritä uudelleen.';

  @override
  String get captureRecordingViewing => 'Katselet tätä tallennetta';

  @override
  String get resetFilters => 'Nollaa suodattimet';

  @override
  String get voiceSettingsSaveOthersSubtitle =>
      'Kun nimeät jonkun, Omi tallentaa lyhyen ääninäytteen tunnistaakseen hänet ensi kerralla';

  @override
  String get iveDoneThis => 'Olen tehnyt tämän';

  @override
  String get howSyncingWorks => 'Miten synkronointi toimii';

  @override
  String greetingWithName(String greeting, String name) {
    return '$greeting, $name';
  }

  @override
  String reviewRemaining(int count) {
    return '$count jäljellä';
  }

  @override
  String get feedbackReasonRecordingMissingAudio => 'Missing audio';

  @override
  String get appCategoryModalTitle => 'Sovelluksen kategoria';

  @override
  String get pushToTalk => 'Paina puhuaksesi';

  @override
  String get noApiKeysYet => 'Ei vielä API-avaimia. Luo yksi integroidaksesi sovelluksesi kanssa.';

  @override
  String minLabel(int count) {
    return '$count min';
  }

  @override
  String appRatingCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count arviota',
      one: '1 arvio',
    );
    return '$_temp0';
  }

  @override
  String get wrappedFood => 'RUOKA';

  @override
  String get aboutAMinuteRemaining => 'Noin minuutti jäljellä';

  @override
  String get clearLogs => 'Tyhjennä lokit';

  @override
  String get wrappedBook => 'KIRJA';

  @override
  String get phoneCallSubtitle => 'Tallenna puhelu reaaliaikaisella tekstityksellä';

  @override
  String deleteConversationsTitle(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Poistetaanko $count keskustelua?',
      one: 'Poistetaanko 1 keskustelu?',
    );
    return '$_temp0';
  }

  @override
  String get deleteSelected => 'Poista valitut';

  @override
  String failedToDeleteGraph(String error) {
    return 'Graafin poistaminen epäonnistui: $error';
  }

  @override
  String get setupQuestionsIntro => 'Auta meitä parantamaan Omia vastaamalla muutamaan kysymykseen. 🫶 💜';

  @override
  String get category => 'Kategoria';

  @override
  String get timeout30MinutesDesc => 'Lopeta keskustelu 30 minuutin hiljaisuuden jälkeen';

  @override
  String get goalDeleted => 'Tavoite poistettu';

  @override
  String get conversationDisplay => 'Keskustelujen Näyttö';

  @override
  String get conversationNoSummaryYet => 'Tällä keskustelulla ei ole vielä yhteenvetoa.';

  @override
  String get chatsLowercase => 'keskustelut';

  @override
  String get clearChatQuestion => 'Tyhjennä keskustelu?';

  @override
  String get signInTitle => 'Kirjaudu sisään';

  @override
  String get loadingKnowledgeGraph => 'Ladataan tietograafia…';

  @override
  String get goalTracker => 'Tavoitteiden seuranta';

  @override
  String get commandRequired => '⌘ vaaditaan';

  @override
  String get permissionEnabled => 'Käytössä';

  @override
  String get submitReview => 'Lähetä arvostelu';

  @override
  String chatUsageCost(String used, String limit) {
    return 'Chat: \$$used / \$$limit käytetty tässä kuussa';
  }

  @override
  String get discard => 'Hylkää';

  @override
  String dreamReportPasses(int count, int limit) {
    return '$count/$limit ajoa tänään';
  }

  @override
  String get unlockOmiInfiniteMemory => 'Rajattomasti muistoja';

  @override
  String get addAppPersonaConflictWithCapabilities => 'Personaa ei voi valita muiden toimintojen kanssa';

  @override
  String get whyAreYouCanceling => 'Miksi peruutat?';

  @override
  String get permissionRequestedExclaim => 'Käyttöoikeus pyydetty!';

  @override
  String get chatBlockOpenInMemories => 'Avaa Muistoissa';

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total objektia';
  }

  @override
  String get deleteActionItemTitle => 'Poista tehtävä';

  @override
  String get rollBack => 'Palauta';

  @override
  String get chatAppsOmiPro => 'OMI PRO';

  @override
  String disconnectFromAppDesc(String appName) {
    return 'Tämä poistaa $appName-todennuksesi. Sinun on yhdistettävä uudelleen käyttääksesi sitä uudelleen.';
  }

  @override
  String get onDeviceModelSize => 'Mallin koko';

  @override
  String tagSpeaker(int speakerId) {
    return 'Merkitse puhuja $speakerId';
  }

  @override
  String get couldNotOpenUrl => 'URL-osoitetta ei voitu avata. Yritä uudelleen.';

  @override
  String get conversationNewIndicator => 'Uusi';

  @override
  String get notEnoughSpeechDescription => 'Puhetta ei havaittu tarpeeksi. Puhu enemmän ja yritä uudelleen.';

  @override
  String get liveRssiOverTime => 'Reaaliaikainen RSSI ajan myötä';

  @override
  String get usageEverywhere => 'Kaikkialla';

  @override
  String nConversations(int count) {
    return '$count keskustelua';
  }

  @override
  String get wrappedConversationsLabel => 'keskustelua';

  @override
  String get usageYear => 'Tänä vuonna';

  @override
  String get noContactsMatchSearch => 'Yksikään yhteystieto ei vastaa hakuasi';

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count tehtävää$s poistettu';
  }

  @override
  String get actionItemMarkedIncomplete => 'Tehtävä merkitty keskeneräiseksi';

  @override
  String get start => 'Aloita';

  @override
  String discardedConversationTitle(String duration) {
    return 'Hylätty · $duration';
  }

  @override
  String get debugLogsCleared => 'Virheenkorjauslokit tyhjennetty';

  @override
  String get preparingAudioCapture => 'Äänitallennus valmistellaan';

  @override
  String get availablePaymentMethods => 'Käytettävissä olevat maksutavat';

  @override
  String get deleteReasonOther => 'Muu';

  @override
  String get accountCutoverMigrationInProgressTitle => 'Siirto käynnissä';

  @override
  String get connectedKnowledgeData => 'Yhdistetty tietolähteisiin';

  @override
  String get wrappedMostFunDay => 'Hauskin';

  @override
  String get onboardingAccessibilityRequired => 'Esteettömyyslupa vaaditaan selainkokouksten havaitsemiseen.';

  @override
  String get selectActionItems => 'Valitse useita';

  @override
  String switchApiConfirmBody(String environment) {
    return 'Vaihdetaanko ympäristöön $environment? Sinun on suljettava ja avattava sovellus uudelleen, jotta muutokset tulevat voimaan.';
  }

  @override
  String get whisperModelSizeLarge => 'Suuri';

  @override
  String get currentVersion => 'Nykyinen versio';

  @override
  String get aiAppGeneratorBannerTitle => 'Luo sovellus tekoälyllä yhdellä napautuksella';

  @override
  String get rayBanMetaMicPickerLoadError =>
      'Bluetooth-mikrofoneja ei voitu ladata. Tarkista, että Bluetooth on päällä, ja yritä uudelleen.';

  @override
  String get noneSelected => 'Ei valittu';

  @override
  String get entityKeptCurrent => 'Omin ajan tasalla pitämä';

  @override
  String migratingFromTo(String source, String target) {
    return 'Siirretään kohteesta $source kohteeseen $target';
  }

  @override
  String get controlNotificationFrequency => 'Hallitse kuinka usein Omi lähettää sinulle ennakoivia ilmoituksia.';

  @override
  String get connectionUptime => 'Käyttöaika';

  @override
  String get categoryLabel => 'Kategoria';

  @override
  String get aboutTheApp => 'Tietoja sovelluksesta';

  @override
  String get planSheetChooseYourPlan => 'Valitse sinulle sopiva tilaus.';

  @override
  String get almostDone => 'Melkein valmis…';

  @override
  String get tasksFromConversationsWillAppear =>
      'Keskusteluistasi tulevat tehtävät näkyvät tässä.\nNapsauta Luo lisätäksesi yhden manuaalisesti.';

  @override
  String get personLastHeard => 'Viimeksi kuultu';

  @override
  String get durationThreshold => 'Kestokynnys';

  @override
  String get transcriptionServiceDiagnosticStatus => 'Litterointipalvelun diagnostiikkatila';

  @override
  String get triggersWhenNewTranscriptReceived => 'Käynnistyy, kun uusi litterointi vastaanotetaan.';

  @override
  String get aboutOmi => 'Tietoja Omista';

  @override
  String get identifyingOthers => 'Muiden Tunnistaminen';

  @override
  String get phoneCallsSubtitle => 'Soita reaaliaikaisella litteroinnilla';

  @override
  String get creatingYourApp => 'Luodaan sovellustasi…';

  @override
  String get analyzingYourData => 'Analysoidaan tietojasi…';
}
