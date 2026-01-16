// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Finnish (`fi`).
class AppLocalizationsFi extends AppLocalizations {
  AppLocalizationsFi([String locale = 'fi']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'Keskustelu';

  @override
  String get transcriptTab => 'Litterointi';

  @override
  String get actionItemsTab => 'Tehtävät';

  @override
  String get deleteConversationTitle => 'Poista keskustelu?';

  @override
  String get deleteConversationMessage => 'Haluatko varmasti poistaa tämän keskustelun? Tätä toimintoa ei voi perua.';

  @override
  String get confirm => 'Vahvista';

  @override
  String get cancel => 'Peruuta';

  @override
  String get ok => 'OK';

  @override
  String get delete => 'Poista';

  @override
  String get add => 'Lisää';

  @override
  String get update => 'Päivitä';

  @override
  String get save => 'Tallenna';

  @override
  String get edit => 'Muokkaa';

  @override
  String get close => 'Sulje';

  @override
  String get clear => 'Tyhjennä';

  @override
  String get copyTranscript => 'Kopioi litterointi';

  @override
  String get copySummary => 'Kopioi yhteenveto';

  @override
  String get testPrompt => 'Testaa kehotetta';

  @override
  String get reprocessConversation => 'Käsittele keskustelu uudelleen';

  @override
  String get deleteConversation => 'Poista keskustelu';

  @override
  String get contentCopied => 'Sisältö kopioitu leikepöydälle';

  @override
  String get failedToUpdateStarred => 'Tähtimerkkauksen päivitys epäonnistui.';

  @override
  String get conversationUrlNotShared => 'Keskustelun URL-osoitetta ei voitu jakaa.';

  @override
  String get errorProcessingConversation => 'Virhe keskustelun käsittelyssä. Yritä myöhemmin uudelleen.';

  @override
  String get noInternetConnection => 'Ei internet-yhteyttä';

  @override
  String get unableToDeleteConversation => 'Keskustelun poisto ei onnistu';

  @override
  String get somethingWentWrong => 'Jokin meni pieleen! Yritä myöhemmin uudelleen.';

  @override
  String get copyErrorMessage => 'Kopioi virheilmoitus';

  @override
  String get errorCopied => 'Virheilmoitus kopioitu leikepöydälle';

  @override
  String get remaining => 'Jäljellä';

  @override
  String get loading => 'Ladataan...';

  @override
  String get loadingDuration => 'Ladataan kestoa...';

  @override
  String secondsCount(int count) {
    return '$count sekuntia';
  }

  @override
  String get people => 'Ihmiset';

  @override
  String get addNewPerson => 'Lisää uusi henkilö';

  @override
  String get editPerson => 'Muokkaa henkilöä';

  @override
  String get createPersonHint => 'Luo uusi henkilö ja opeta Omi tunnistamaan hänen puheensa!';

  @override
  String get speechProfile => 'Puheprofiili';

  @override
  String sampleNumber(int number) {
    return 'Näyte $number';
  }

  @override
  String get settings => 'Asetukset';

  @override
  String get language => 'Kieli';

  @override
  String get selectLanguage => 'Valitse kieli';

  @override
  String get deleting => 'Poistetaan...';

  @override
  String get pleaseCompleteAuthentication => 'Viimeistele todennus selaimessasi. Kun olet valmis, palaa sovellukseen.';

  @override
  String get failedToStartAuthentication => 'Todennuksen aloitus epäonnistui';

  @override
  String get importStarted => 'Tuonti aloitettu! Saat ilmoituksen, kun se on valmis.';

  @override
  String get failedToStartImport => 'Tuonnin aloitus epäonnistui. Yritä uudelleen.';

  @override
  String get couldNotAccessFile => 'Valittua tiedostoa ei voitu käyttää';

  @override
  String get askOmi => 'Kysy Omilta';

  @override
  String get done => 'Valmis';

  @override
  String get disconnected => 'Yhteys katkaistu';

  @override
  String get searching => 'Haetaan...';

  @override
  String get connectDevice => 'Yhdistä laite';

  @override
  String get monthlyLimitReached => 'Olet saavuttanut kuukausirajan.';

  @override
  String get checkUsage => 'Tarkista käyttö';

  @override
  String get syncingRecordings => 'Synkronoidaan nauhoituksia';

  @override
  String get recordingsToSync => 'Synkronoitavat nauhoitukset';

  @override
  String get allCaughtUp => 'Kaikki ajan tasalla';

  @override
  String get sync => 'Synkronoi';

  @override
  String get pendantUpToDate => 'Riipus on ajan tasalla';

  @override
  String get allRecordingsSynced => 'Kaikki nauhoitukset synkronoitu';

  @override
  String get syncingInProgress => 'Synkronointi käynnissä';

  @override
  String get readyToSync => 'Valmis synkronointiin';

  @override
  String get tapSyncToStart => 'Aloita napauttamalla Synkronoi';

  @override
  String get pendantNotConnected => 'Riipus ei ole yhdistetty. Yhdistä synkronoidaksesi.';

  @override
  String get everythingSynced => 'Kaikki on jo synkronoitu.';

  @override
  String get recordingsNotSynced => 'Sinulla on nauhoituksia, joita ei ole vielä synkronoitu.';

  @override
  String get syncingBackground => 'Jatkamme nauhoitusten synkronointia taustalla.';

  @override
  String get noConversationsYet => 'Ei vielä keskusteluja';

  @override
  String get noStarredConversations => 'Ei tähdellä merkittyjä keskusteluja';

  @override
  String get starConversationHint => 'Merkitäksesi keskustelun tähdellä, avaa se ja napauta tähti-kuvaketta otsikossa.';

  @override
  String get searchConversations => 'Etsi keskusteluja...';

  @override
  String selectedCount(int count, Object s) {
    return '$count valittu';
  }

  @override
  String get merge => 'Yhdistä';

  @override
  String get mergeConversations => 'Yhdistä keskustelut';

  @override
  String mergeConversationsMessage(int count) {
    return 'Tämä yhdistää $count keskustelua yhdeksi. Kaikki sisältö yhdistetään ja luodaan uudelleen.';
  }

  @override
  String get mergingInBackground => 'Yhdistetään taustalla. Tämä voi kestää hetken.';

  @override
  String get failedToStartMerge => 'Yhdistämisen aloitus epäonnistui';

  @override
  String get askAnything => 'Kysy mitä tahansa';

  @override
  String get noMessagesYet => 'Ei vielä viestejä!\nMikset aloittaisi keskustelua?';

  @override
  String get deletingMessages => 'Poistetaan viestejäsi Omin muistista...';

  @override
  String get messageCopied => '✨ Viesti kopioitu leikepöydälle';

  @override
  String get cannotReportOwnMessage => 'Et voi ilmoittaa omista viesteistäsi.';

  @override
  String get reportMessage => 'Raportoi viesti';

  @override
  String get reportMessageConfirm => 'Haluatko varmasti ilmoittaa tästä viestistä?';

  @override
  String get messageReported => 'Viesti ilmoitettu onnistuneesti.';

  @override
  String get thankYouFeedback => 'Kiitos palautteestasi!';

  @override
  String get clearChat => 'Tyhjennä keskustelu?';

  @override
  String get clearChatConfirm => 'Haluatko varmasti tyhjentää keskustelun? Tätä toimintoa ei voi perua.';

  @override
  String get maxFilesLimit => 'Voit ladata vain 4 tiedostoa kerrallaan';

  @override
  String get chatWithOmi => 'Keskustele Omin kanssa';

  @override
  String get apps => 'Sovellukset';

  @override
  String get noAppsFound => 'Sovelluksia ei löytynyt';

  @override
  String get tryAdjustingSearch => 'Kokeile säätää hakua tai suodattimia';

  @override
  String get createYourOwnApp => 'Luo oma sovellus';

  @override
  String get buildAndShareApp => 'Rakenna ja jaa oma sovelluksesi';

  @override
  String get searchApps => 'Etsi sovelluksia...';

  @override
  String get myApps => 'Omat sovellukset';

  @override
  String get installedApps => 'Asennetut sovellukset';

  @override
  String get unableToFetchApps => 'Sovellusten haku epäonnistui :(\n\nTarkista internet-yhteytesi ja yritä uudelleen.';

  @override
  String get aboutOmi => 'Tietoja Omista';

  @override
  String get privacyPolicy => 'Tietosuojakäytäntö';

  @override
  String get visitWebsite => 'Käy verkkosivustolla';

  @override
  String get helpOrInquiries => 'Apua tai kysymyksiä?';

  @override
  String get joinCommunity => 'Liity yhteisöön!';

  @override
  String get membersAndCounting => '8000+ jäsentä ja kasvaa.';

  @override
  String get deleteAccountTitle => 'Poista tili';

  @override
  String get deleteAccountConfirm => 'Haluatko varmasti poistaa tilisi?';

  @override
  String get cannotBeUndone => 'Tätä ei voi perua.';

  @override
  String get allDataErased => 'Kaikki muistosi ja keskustelusi poistetaan pysyvästi.';

  @override
  String get appsDisconnected => 'Sovelluksesi ja integraatiot katkaistaan välittömästi.';

  @override
  String get exportBeforeDelete =>
      'Voit viedä tietosi ennen tilin poistamista, mutta poiston jälkeen niitä ei voi palauttaa.';

  @override
  String get deleteAccountCheckbox =>
      'Ymmärrän, että tilini poistaminen on pysyvää ja kaikki tiedot, mukaan lukien muistot ja keskustelut, menetetään eikä niitä voi palauttaa.';

  @override
  String get areYouSure => 'Oletko varma?';

  @override
  String get deleteAccountFinal =>
      'Tämä toiminto on peruuttamaton ja poistaa tilisi ja kaikki siihen liittyvät tiedot pysyvästi. Haluatko varmasti jatkaa?';

  @override
  String get deleteNow => 'Poista nyt';

  @override
  String get goBack => 'Palaa takaisin';

  @override
  String get checkBoxToConfirm =>
      'Valitse ruutu vahvistaaksesi, että ymmärrät tilin poistamisen olevan pysyvää ja peruuttamatonta.';

  @override
  String get profile => 'Profiili';

  @override
  String get name => 'Nimi';

  @override
  String get email => 'Sähköposti';

  @override
  String get customVocabulary => 'Mukautettu Sanasto';

  @override
  String get identifyingOthers => 'Muiden Tunnistaminen';

  @override
  String get paymentMethods => 'Maksutavat';

  @override
  String get conversationDisplay => 'Keskustelujen Näyttö';

  @override
  String get dataPrivacy => 'Tietosuoja';

  @override
  String get userId => 'Käyttäjätunnus';

  @override
  String get notSet => 'Ei asetettu';

  @override
  String get userIdCopied => 'Käyttäjätunnus kopioitu leikepöydälle';

  @override
  String get systemDefault => 'Järjestelmän oletus';

  @override
  String get planAndUsage => 'Paketti ja käyttö';

  @override
  String get offlineSync => 'Offline-synkronointi';

  @override
  String get deviceSettings => 'Laitteen asetukset';

  @override
  String get chatTools => 'Chat-työkalut';

  @override
  String get feedbackBug => 'Palaute / Virhe';

  @override
  String get helpCenter => 'Ohjekeskus';

  @override
  String get developerSettings => 'Kehittäjäasetukset';

  @override
  String get getOmiForMac => 'Hanki Omi Macille';

  @override
  String get referralProgram => 'Suositteluohjelma';

  @override
  String get signOut => 'Kirjaudu Ulos';

  @override
  String get appAndDeviceCopied => 'Sovelluksen ja laitteen tiedot kopioitu';

  @override
  String get wrapped2025 => 'Wrapped 2025';

  @override
  String get yourPrivacyYourControl => 'Yksityisyytesi, sinun hallinnassasi';

  @override
  String get privacyIntro =>
      'Omissa olemme sitoutuneet suojaamaan yksityisyyttäsi. Tämä sivu antaa sinulle mahdollisuuden hallita, miten tietojasi tallennetaan ja käytetään.';

  @override
  String get learnMore => 'Lue lisää...';

  @override
  String get dataProtectionLevel => 'Tietosuojataso';

  @override
  String get dataProtectionDesc =>
      'Tietosi on oletuksena suojattu vahvalla salauksella. Tarkista asetuksesi ja tulevat yksityisyysvaihtoehdot alla.';

  @override
  String get appAccess => 'Sovelluspääsy';

  @override
  String get appAccessDesc =>
      'Seuraavat sovellukset voivat käyttää tietojasi. Napauta sovellusta hallitaksesi sen käyttöoikeuksia.';

  @override
  String get noAppsExternalAccess => 'Yhdelläkään asennetulla sovelluksella ei ole ulkoista pääsyä tietoihisi.';

  @override
  String get deviceName => 'Laitteen nimi';

  @override
  String get deviceId => 'Laitteen tunnus';

  @override
  String get firmware => 'Laiteohjelmisto';

  @override
  String get sdCardSync => 'SD-kortin synkronointi';

  @override
  String get hardwareRevision => 'Laitteistoversio';

  @override
  String get modelNumber => 'Mallinumero';

  @override
  String get manufacturer => 'Valmistaja';

  @override
  String get doubleTap => 'Kaksoisnapautus';

  @override
  String get ledBrightness => 'LED-kirkkaus';

  @override
  String get micGain => 'Mikrofonin vahvistus';

  @override
  String get disconnect => 'Katkaise yhteys';

  @override
  String get forgetDevice => 'Unohda laite';

  @override
  String get chargingIssues => 'Latausongelmat';

  @override
  String get disconnectDevice => 'Katkaise laitteen yhteys';

  @override
  String get unpairDevice => 'Poista laitteen pariliitos';

  @override
  String get unpairAndForget => 'Pura laitepari ja unohda laite';

  @override
  String get deviceDisconnectedMessage => 'Omin yhteys on katkaistu 😔';

  @override
  String get deviceUnpairedMessage =>
      'Laitteen pariliitos poistettu. Siirry Asetukset > Bluetooth ja unohda laite pariliitoksen poistamisen viimeistelemiseksi.';

  @override
  String get unpairDialogTitle => 'Pura laitepari';

  @override
  String get unpairDialogMessage =>
      'Tämä purkaa laiteparin, jotta se voidaan yhdistää toiseen puhelimeen. Sinun on siirryttävä kohtaan Asetukset > Bluetooth ja unohdettava laite prosessin viimeistelemiseksi.';

  @override
  String get deviceNotConnected => 'Laitetta ei ole yhdistetty';

  @override
  String get connectDeviceMessage => 'Yhdistä Omi-laite käyttääksesi\nlaiteasetuksia ja mukautusta';

  @override
  String get deviceInfoSection => 'Laitteen tiedot';

  @override
  String get customizationSection => 'Mukautus';

  @override
  String get hardwareSection => 'Laitteisto';

  @override
  String get v2Undetected => 'V2 ei havaittu';

  @override
  String get v2UndetectedMessage =>
      'Sinulla näyttää olevan V1-laite tai laitteesi ei ole yhdistetty. SD-korttitoiminto on saatavilla vain V2-laitteille.';

  @override
  String get endConversation => 'Lopeta keskustelu';

  @override
  String get pauseResume => 'Keskeytä/Jatka';

  @override
  String get starConversation => 'Merkitse tähdellä';

  @override
  String get doubleTapAction => 'Kaksoisnapaututstoiminto';

  @override
  String get endAndProcess => 'Lopeta ja käsittele keskustelu';

  @override
  String get pauseResumeRecording => 'Keskeytä/Jatka nauhoitusta';

  @override
  String get starOngoing => 'Merkitse käynnissä oleva keskustelu tähdellä';

  @override
  String get off => 'Pois';

  @override
  String get max => 'Maks.';

  @override
  String get mute => 'Vaimenna';

  @override
  String get quiet => 'Hiljainen';

  @override
  String get normal => 'Normaali';

  @override
  String get high => 'Korkea';

  @override
  String get micGainDescMuted => 'Mikrofoni on vaimennettu';

  @override
  String get micGainDescLow => 'Erittäin hiljainen - meluisiin ympäristöihin';

  @override
  String get micGainDescModerate => 'Hiljainen - kohtalaiseen meluun';

  @override
  String get micGainDescNeutral => 'Neutraali - tasapainoinen nauhoitus';

  @override
  String get micGainDescSlightlyBoosted => 'Hieman vahvistettu - normaalikäyttö';

  @override
  String get micGainDescBoosted => 'Vahvistettu - hiljaisiin ympäristöihin';

  @override
  String get micGainDescHigh => 'Korkea - kaukaisille tai pehmeille äänille';

  @override
  String get micGainDescVeryHigh => 'Erittäin korkea - erittäin hiljaisille lähteille';

  @override
  String get micGainDescMax => 'Maksimi - käytä varoen';

  @override
  String get developerSettingsTitle => 'Kehittäjäasetukset';

  @override
  String get saving => 'Tallennetaan...';

  @override
  String get personaConfig => 'Määritä AI-persoonasi';

  @override
  String get beta => 'BETA';

  @override
  String get transcription => 'Litterointi';

  @override
  String get transcriptionConfig => 'Määritä STT-palveluntarjoaja';

  @override
  String get conversationTimeout => 'Keskustelun aikakatkaisu';

  @override
  String get conversationTimeoutConfig => 'Aseta milloin keskustelut päättyvät automaattisesti';

  @override
  String get importData => 'Tuo tietoja';

  @override
  String get importDataConfig => 'Tuo tietoja muista lähteistä';

  @override
  String get debugDiagnostics => 'Vianjäljitys ja diagnostiikka';

  @override
  String get endpointUrl => 'Päätepisteen URL';

  @override
  String get noApiKeys => 'Ei vielä API-avaimia';

  @override
  String get createKeyToStart => 'Luo avain aloittaaksesi';

  @override
  String get createKey => 'Luo Avain';

  @override
  String get docs => 'Dokumentaatio';

  @override
  String get yourOmiInsights => 'Omi-näkemyksesi';

  @override
  String get today => 'Tänään';

  @override
  String get thisMonth => 'Tässä kuussa';

  @override
  String get thisYear => 'Tänä vuonna';

  @override
  String get allTime => 'Kaikki aika';

  @override
  String get noActivityYet => 'Ei vielä toimintaa';

  @override
  String get startConversationToSeeInsights => 'Aloita keskustelu Omin kanssa\nnähdäksesi käyttötietosi täällä.';

  @override
  String get listening => 'Kuunteleminen';

  @override
  String get listeningSubtitle => 'Kokonaisaika, jonka Omi on aktiivisesti kuunnellut.';

  @override
  String get understanding => 'Ymmärtäminen';

  @override
  String get understandingSubtitle => 'Keskusteluistasi ymmärretyt sanat.';

  @override
  String get providing => 'Tarjoaminen';

  @override
  String get providingSubtitle => 'Tehtävät ja muistiinpanot automaattisesti tallennettu.';

  @override
  String get remembering => 'Muistaminen';

  @override
  String get rememberingSubtitle => 'Sinulle muistetut faktat ja yksityiskohdat.';

  @override
  String get unlimitedPlan => 'Rajoittamaton paketti';

  @override
  String get managePlan => 'Hallitse pakettia';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'Pakettisi peruuntuu $date.';
  }

  @override
  String renewsOn(String date) {
    return 'Pakettisi uusiutuu $date.';
  }

  @override
  String get basicPlan => 'Ilmaispaketti';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used/$limit min käytetty';
  }

  @override
  String get upgrade => 'Päivitä';

  @override
  String get upgradeToUnlimited => 'Päivitä rajattomaksi';

  @override
  String basicPlanDesc(int limit) {
    return 'Pakettisi sisältää $limit ilmaisminuuttia kuukaudessa. Päivitä saadaksesi rajoittamattoman.';
  }

  @override
  String get shareStatsMessage => 'Jaan Omi-tilastoni! (omi.me - aina päällä oleva tekoälyavustajasi)';

  @override
  String get sharePeriodToday => 'Tänään omi on:';

  @override
  String get sharePeriodMonth => 'Tässä kuussa omi on:';

  @override
  String get sharePeriodYear => 'Tänä vuonna omi on:';

  @override
  String get sharePeriodAllTime => 'Tähän mennessä omi on:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 Kuunnellut $minutes minuuttia';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 Ymmärtänyt $words sanaa';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ Tarjonnut $count näkemystä';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 Muistanut $count muistoa';
  }

  @override
  String get debugLogs => 'Virheenkorjauslokit';

  @override
  String get debugLogsAutoDelete => 'Poistetaan automaattisesti 3 päivän kuluttua.';

  @override
  String get debugLogsDesc => 'Auttaa ongelmien diagnosoinnissa';

  @override
  String get noLogFilesFound => 'Lokitiedostoja ei löytynyt.';

  @override
  String get omiDebugLog => 'Omin vianjäljitysloki';

  @override
  String get logShared => 'Loki jaettu';

  @override
  String get selectLogFile => 'Valitse lokitiedosto';

  @override
  String get shareLogs => 'Jaa lokit';

  @override
  String get debugLogCleared => 'Vianjäljitysloki tyhjennetty';

  @override
  String get exportStarted => 'Vienti aloitettu. Tämä voi kestää muutaman sekunnin...';

  @override
  String get exportAllData => 'Vie kaikki tiedot';

  @override
  String get exportDataDesc => 'Vie keskustelut JSON-tiedostoon';

  @override
  String get exportedConversations => 'Viedyt keskustelut Omista';

  @override
  String get exportShared => 'Vienti jaettu';

  @override
  String get deleteKnowledgeGraphTitle => 'Poista tietograafi?';

  @override
  String get deleteKnowledgeGraphMessage =>
      'Tämä poistaa kaikki johdetut tietograafitiedot (solmut ja yhteydet). Alkuperäiset muistosi pysyvät turvassa. Graafi rakennetaan uudelleen ajan myötä tai seuraavan pyynnön yhteydessä.';

  @override
  String get knowledgeGraphDeleted => 'Tietämysgraafi poistettu';

  @override
  String deleteGraphFailed(String error) {
    return 'Graafin poisto epäonnistui: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'Poista tietograafi';

  @override
  String get deleteKnowledgeGraphDesc => 'Tyhjennä kaikki solmut ja yhteydet';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'MCP-palvelin';

  @override
  String get mcpServerDesc => 'Yhdistä tekoälyavustajat tietoihisi';

  @override
  String get serverUrl => 'Palvelimen URL';

  @override
  String get urlCopied => 'URL kopioitu';

  @override
  String get apiKeyAuth => 'API-avaimen todennus';

  @override
  String get header => 'Otsikko';

  @override
  String get authorizationBearer => 'Authorization: Bearer <avain>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'Asiakas-ID';

  @override
  String get clientSecret => 'Asiakassalaisuus';

  @override
  String get useMcpApiKey => 'Käytä MCP API-avainta';

  @override
  String get webhooks => 'Webhookit';

  @override
  String get conversationEvents => 'Keskustelutapahtumat';

  @override
  String get newConversationCreated => 'Uusi keskustelu luotu';

  @override
  String get realtimeTranscript => 'Reaaliaikainen litterointi';

  @override
  String get transcriptReceived => 'Litterointi vastaanotettu';

  @override
  String get audioBytes => 'Äänitavut';

  @override
  String get audioDataReceived => 'Ääniaineisto vastaanotettu';

  @override
  String get intervalSeconds => 'Aikaväli (sekunteina)';

  @override
  String get daySummary => 'Päivän yhteenveto';

  @override
  String get summaryGenerated => 'Yhteenveto luotu';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'Lisää claude_desktop_config.json-tiedostoon';

  @override
  String get copyConfig => 'Kopioi kokoonpano';

  @override
  String get configCopied => 'Kokoonpano kopioitu leikepöydälle';

  @override
  String get listeningMins => 'Kuunteleminen (min)';

  @override
  String get understandingWords => 'Ymmärtäminen (sanaa)';

  @override
  String get insights => 'Oivallukset';

  @override
  String get memories => 'Muistot';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '$used/$limit min käytetty tässä kuussa';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '$used/$limit sanaa käytetty tässä kuussa';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '$used/$limit näkemystä saavutettu tässä kuussa';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return '$used/$limit muistoa luotu tässä kuussa';
  }

  @override
  String get visibility => 'Näkyvyys';

  @override
  String get visibilitySubtitle => 'Hallitse mitä keskusteluja näkyy luettelossasi';

  @override
  String get showShortConversations => 'Näytä lyhyet keskustelut';

  @override
  String get showShortConversationsDesc => 'Näytä kynnysarvoa lyhyemmät keskustelut';

  @override
  String get showDiscardedConversations => 'Näytä hylätyt keskustelut';

  @override
  String get showDiscardedConversationsDesc => 'Sisällytä hylätyksi merkityt keskustelut';

  @override
  String get shortConversationThreshold => 'Lyhyen keskustelun kynnysarvo';

  @override
  String get shortConversationThresholdSubtitle =>
      'Tätä lyhyemmät keskustelut piilotetaan, ellei niitä ole otettu käyttöön yllä';

  @override
  String get durationThreshold => 'Kestokynnys';

  @override
  String get durationThresholdDesc => 'Piilota tätä lyhyemmät keskustelut';

  @override
  String minLabel(int count) {
    return '$count min';
  }

  @override
  String get customVocabularyTitle => 'Mukautettu sanasto';

  @override
  String get addWords => 'Lisää sanoja';

  @override
  String get addWordsDesc => 'Nimiä, termejä tai harvinaisia sanoja';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'Yhdistä';

  @override
  String get comingSoon => 'Tulossa pian';

  @override
  String get chatToolsFooter => 'Yhdistä sovelluksesi nähdäksesi tiedot ja mittarit chatissa.';

  @override
  String get completeAuthInBrowser => 'Viimeistele todennus selaimessasi. Kun olet valmis, palaa sovellukseen.';

  @override
  String failedToStartAuth(String appName) {
    return '$appName-todennuksen aloitus epäonnistui';
  }

  @override
  String disconnectAppTitle(String appName) {
    return 'Katkaise yhteys palveluun $appName?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'Haluatko varmasti katkaista yhteyden palveluun $appName? Voit yhdistää uudelleen milloin tahansa.';
  }

  @override
  String disconnectedFrom(String appName) {
    return 'Yhteys katkaistu palveluun $appName';
  }

  @override
  String get failedToDisconnect => 'Yhteyden katkaisu epäonnistui';

  @override
  String connectTo(String appName) {
    return 'Yhdistä palveluun $appName';
  }

  @override
  String authAccessMessage(String appName) {
    return 'Sinun on valtuutettava Omi käyttämään $appName-tietojasi. Tämä avaa selaimesi todennusta varten.';
  }

  @override
  String get continueAction => 'Jatka';

  @override
  String get languageTitle => 'Kieli';

  @override
  String get primaryLanguage => 'Ensisijainen kieli';

  @override
  String get automaticTranslation => 'Automaattinen käännös';

  @override
  String get detectLanguages => 'Tunnista yli 10 kieltä';

  @override
  String get authorizeSavingRecordings => 'Valtuuta nauhoitusten tallentaminen';

  @override
  String get thanksForAuthorizing => 'Kiitos valtuutuksesta!';

  @override
  String get needYourPermission => 'Tarvitsemme lupasi';

  @override
  String get alreadyGavePermission =>
      'Olet jo antanut meille luvan tallentaa nauhoituksiasi. Tässä muistutus siitä, miksi tarvitsemme sen:';

  @override
  String get wouldLikePermission => 'Haluaisimme lupasi tallentaa ääninauhoituksesi. Tässä syy:';

  @override
  String get improveSpeechProfile => 'Paranna puheprofiiliasi';

  @override
  String get improveSpeechProfileDesc =>
      'Käytämme nauhoituksia henkilökohtaisen puheprofiilisi kouluttamiseen ja parantamiseen.';

  @override
  String get trainFamilyProfiles => 'Kouluta profiileja ystäville ja perheelle';

  @override
  String get trainFamilyProfilesDesc =>
      'Nauhoituksesi auttavat meitä tunnistamaan ja luomaan profiileja ystävillesi ja perheellesi.';

  @override
  String get enhanceTranscriptAccuracy => 'Paranna litterointitarkkuutta';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'Kun mallimme paranee, voimme tarjota parempia litterointituloksia nauhoituksillesi.';

  @override
  String get legalNotice =>
      'Oikeudellinen huomautus: Äänidatan nauhoittamisen ja tallentamisen laillisuus voi vaihdella sijaintisi ja tämän ominaisuuden käyttötavan mukaan. Vastaat paikallisten lakien ja määräysten noudattamisesta.';

  @override
  String get alreadyAuthorized => 'Jo valtuutettu';

  @override
  String get authorize => 'Valtuuta';

  @override
  String get revokeAuthorization => 'Peru valtuutus';

  @override
  String get authorizationSuccessful => 'Valtuutus onnistui!';

  @override
  String get failedToAuthorize => 'Valtuutus epäonnistui. Yritä uudelleen.';

  @override
  String get authorizationRevoked => 'Valtuutus peruttu.';

  @override
  String get recordingsDeleted => 'Nauhoitukset poistettu.';

  @override
  String get failedToRevoke => 'Valtuutuksen peruutus epäonnistui. Yritä uudelleen.';

  @override
  String get permissionRevokedTitle => 'Lupa peruttu';

  @override
  String get permissionRevokedMessage => 'Haluatko meidän poistavan myös kaikki olemassa olevat nauhoituksesi?';

  @override
  String get yes => 'Kyllä';

  @override
  String get editName => 'Muokkaa nimeä';

  @override
  String get howShouldOmiCallYou => 'Miten Omin pitäisi kutsua sinua?';

  @override
  String get enterYourName => 'Syötä nimesi';

  @override
  String get nameCannotBeEmpty => 'Nimi ei voi olla tyhjä';

  @override
  String get nameUpdatedSuccessfully => 'Nimi päivitetty onnistuneesti!';

  @override
  String get calendarSettings => 'Kalenteriasetukset';

  @override
  String get calendarProviders => 'Kalenteripalvelut';

  @override
  String get macOsCalendar => 'macOS-kalenteri';

  @override
  String get connectMacOsCalendar => 'Yhdistä paikallinen macOS-kalenterisi';

  @override
  String get googleCalendar => 'Google Kalenteri';

  @override
  String get syncGoogleAccount => 'Synkronoi Google-tilisi kanssa';

  @override
  String get showMeetingsMenuBar => 'Näytä tulevat kokoukset valikkorivissä';

  @override
  String get showMeetingsMenuBarDesc => 'Näytä seuraava kokouksesi ja aika sen alkuun macOS-valikkorivissä';

  @override
  String get showEventsNoParticipants => 'Näytä tapahtumat ilman osallistujia';

  @override
  String get showEventsNoParticipantsDesc =>
      'Kun käytössä, Tulossa näyttää tapahtumat ilman osallistujia tai videolinkkiä.';

  @override
  String get yourMeetings => 'Kokouksesi';

  @override
  String get refresh => 'Päivitä';

  @override
  String get noUpcomingMeetings => 'Tulevia kokouksia ei löytynyt';

  @override
  String get checkingNextDays => 'Tarkistetaan seuraavat 30 päivää';

  @override
  String get tomorrow => 'Huomenna';

  @override
  String get googleCalendarComingSoon => 'Google Kalenteri -integraatio tulossa pian!';

  @override
  String connectedAsUser(String userId) {
    return 'Yhdistetty käyttäjänä: $userId';
  }

  @override
  String get defaultWorkspace => 'Oletustyötila';

  @override
  String get tasksCreatedInWorkspace => 'Tehtävät luodaan tähän työtilaan';

  @override
  String get defaultProjectOptional => 'Oletusprojekti (valinnainen)';

  @override
  String get leaveUnselectedTasks => 'Jätä valitsematta luodaksesi tehtäviä ilman projektia';

  @override
  String get noProjectsInWorkspace => 'Projekteja ei löytynyt tästä työtilasta';

  @override
  String get conversationTimeoutDesc =>
      'Valitse kuinka kauan odotetaan hiljaisuutta ennen keskustelun automaattista päättämistä:';

  @override
  String get timeout2Minutes => '2 minuuttia';

  @override
  String get timeout2MinutesDesc => 'Lopeta keskustelu 2 minuutin hiljaisuuden jälkeen';

  @override
  String get timeout5Minutes => '5 minuuttia';

  @override
  String get timeout5MinutesDesc => 'Lopeta keskustelu 5 minuutin hiljaisuuden jälkeen';

  @override
  String get timeout10Minutes => '10 minuuttia';

  @override
  String get timeout10MinutesDesc => 'Lopeta keskustelu 10 minuutin hiljaisuuden jälkeen';

  @override
  String get timeout30Minutes => '30 minuuttia';

  @override
  String get timeout30MinutesDesc => 'Lopeta keskustelu 30 minuutin hiljaisuuden jälkeen';

  @override
  String get timeout4Hours => '4 tuntia';

  @override
  String get timeout4HoursDesc => 'Lopeta keskustelu 4 tunnin hiljaisuuden jälkeen';

  @override
  String get conversationEndAfterHours => 'Keskustelut päättyvät nyt 4 tunnin hiljaisuuden jälkeen';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Keskustelut päättyvät nyt $minutes minuutin hiljaisuuden jälkeen';
  }

  @override
  String get tellUsPrimaryLanguage => 'Kerro meille ensisijainen kielesi';

  @override
  String get languageForTranscription => 'Aseta kielesi tarkempaa litterointia ja henkilökohtaista kokemusta varten.';

  @override
  String get singleLanguageModeInfo =>
      'Yhden kielen tila on käytössä. Käännös on poistettu käytöstä paremman tarkkuuden vuoksi.';

  @override
  String get searchLanguageHint => 'Etsi kieltä nimen tai koodin perusteella';

  @override
  String get noLanguagesFound => 'Kieliä ei löytynyt';

  @override
  String get skip => 'Ohita';

  @override
  String languageSetTo(String language) {
    return 'Kieleksi asetettu $language';
  }

  @override
  String get failedToSetLanguage => 'Kielen asetus epäonnistui';

  @override
  String appSettings(String appName) {
    return '$appName-asetukset';
  }

  @override
  String disconnectFromApp(String appName) {
    return 'Katkaise yhteys palveluun $appName?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'Tämä poistaa $appName-todennuksesi. Sinun on yhdistettävä uudelleen käyttääksesi sitä uudelleen.';
  }

  @override
  String connectedToApp(String appName) {
    return 'Yhdistetty palveluun $appName';
  }

  @override
  String get account => 'Tili';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Tehtäväsi synkronoidaan $appName-tilillesi';
  }

  @override
  String get defaultSpace => 'Oletustila';

  @override
  String get selectSpaceInWorkspace => 'Valitse tila työtilassasi';

  @override
  String get noSpacesInWorkspace => 'Tiloja ei löytynyt tästä työtilasta';

  @override
  String get defaultList => 'Oletusluettelo';

  @override
  String get tasksAddedToList => 'Tehtävät lisätään tähän luetteloon';

  @override
  String get noListsInSpace => 'Luetteloita ei löytynyt tästä tilasta';

  @override
  String failedToLoadRepos(String error) {
    return 'Repositorioiden lataaminen epäonnistui: $error';
  }

  @override
  String get defaultRepoSaved => 'Oletusrepositorio tallennettu';

  @override
  String get failedToSaveDefaultRepo => 'Oletusrepositorion tallentaminen epäonnistui';

  @override
  String get defaultRepository => 'Oletusrepositorio';

  @override
  String get selectDefaultRepoDesc =>
      'Valitse oletusrepositorio ongelmien luomiseen. Voit silti määrittää eri repositorion ongelmia luodessa.';

  @override
  String get noReposFound => 'Repositorioita ei löytynyt';

  @override
  String get private => 'Yksityinen';

  @override
  String updatedDate(String date) {
    return 'Päivitetty $date';
  }

  @override
  String get yesterday => 'Eilen';

  @override
  String daysAgo(int count) {
    return '$count päivää sitten';
  }

  @override
  String get oneWeekAgo => 'viikko sitten';

  @override
  String weeksAgo(int count) {
    return '$count viikkoa sitten';
  }

  @override
  String get oneMonthAgo => 'kuukausi sitten';

  @override
  String monthsAgo(int count) {
    return '$count kuukautta sitten';
  }

  @override
  String get issuesCreatedInRepo => 'Ongelmat luodaan oletusrepositoriossasi';

  @override
  String get taskIntegrations => 'Tehtäväintegraatiot';

  @override
  String get configureSettings => 'Määritä asetukset';

  @override
  String get completeAuthBrowser => 'Viimeistele todennus selaimessasi. Kun olet valmis, palaa sovellukseen.';

  @override
  String failedToStartAppAuth(String appName) {
    return '$appName-todennuksen aloitus epäonnistui';
  }

  @override
  String connectToAppTitle(String appName) {
    return 'Yhdistä palveluun $appName';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Sinun on valtuutettava Omi luomaan tehtäviä $appName-tilillesi. Tämä avaa selaimesi todennusta varten.';
  }

  @override
  String get continueButton => 'Jatka';

  @override
  String appIntegration(String appName) {
    return '$appName-integraatio';
  }

  @override
  String integrationComingSoon(String appName) {
    return 'Integraatio palvelun $appName kanssa tulossa pian! Työskentelemme ahkerasti tuodaksemme sinulle lisää tehtävänhallinnan vaihtoehtoja.';
  }

  @override
  String get gotIt => 'Selvä';

  @override
  String get tasksExportedOneApp => 'Tehtäviä voidaan viedä yhteen sovellukseen kerrallaan';

  @override
  String get completeYourUpgrade => 'Viimeistele päivityksesi';

  @override
  String get importConfiguration => 'Tuo kokoonpano';

  @override
  String get exportConfiguration => 'Vie kokoonpano';

  @override
  String get bringYourOwn => 'Tuo omasi';

  @override
  String get payYourSttProvider => 'Käytä omia vapaasti. Maksat vain STT-palveluntarjoajallesi suoraan.';

  @override
  String get freeMinutesMonth => '1 200 ilmaisminuuttia kuukaudessa mukana. Rajoittamaton ';

  @override
  String get omiUnlimited => 'Omi Unlimited';

  @override
  String get hostRequired => 'Isäntä vaaditaan';

  @override
  String get validPortRequired => 'Kelvollinen portti vaaditaan';

  @override
  String get validWebsocketUrlRequired => 'Kelvollinen WebSocket-URL vaaditaan (wss://)';

  @override
  String get apiUrlRequired => 'API-URL vaaditaan';

  @override
  String get apiKeyRequired => 'API-avain vaaditaan';

  @override
  String get invalidJsonConfig => 'Virheellinen JSON-kokoonpano';

  @override
  String errorSaving(String error) {
    return 'Virhe tallentaessa: $error';
  }

  @override
  String get configCopiedToClipboard => 'Kokoonpano kopioitu leikepöydälle';

  @override
  String get pasteJsonConfig => 'Liitä JSON-kokoonpanosi alle:';

  @override
  String get addApiKeyAfterImport => 'Sinun on lisättävä oma API-avaimesi tuonnin jälkeen';

  @override
  String get paste => 'Liitä';

  @override
  String get import => 'Tuo';

  @override
  String get invalidProviderInConfig => 'Virheellinen palveluntarjoaja kokoonpanossa';

  @override
  String importedConfig(String providerName) {
    return 'Tuotu $providerName-kokoonpano';
  }

  @override
  String invalidJson(String error) {
    return 'Virheellinen JSON: $error';
  }

  @override
  String get provider => 'Palveluntarjoaja';

  @override
  String get live => 'Live';

  @override
  String get onDevice => 'Laitteella';

  @override
  String get apiUrl => 'API-URL';

  @override
  String get enterSttHttpEndpoint => 'Kirjoita STT HTTP -päätepisteesi';

  @override
  String get websocketUrl => 'WebSocket-URL';

  @override
  String get enterLiveSttWebsocket => 'Kirjoita live-STT WebSocket -päätepisteesi';

  @override
  String get apiKey => 'API-avain';

  @override
  String get enterApiKey => 'Kirjoita API-avaimesi';

  @override
  String get storedLocallyNeverShared => 'Tallennettu paikallisesti, ei koskaan jaettu';

  @override
  String get host => 'Isäntä';

  @override
  String get port => 'Portti';

  @override
  String get advanced => 'Lisäasetukset';

  @override
  String get configuration => 'Kokoonpano';

  @override
  String get requestConfiguration => 'Pyyntökokoonpano';

  @override
  String get responseSchema => 'Vastauskaavio';

  @override
  String get modified => 'Muokattu';

  @override
  String get resetRequestConfig => 'Palauta pyyntökokoonpano oletuksiin';

  @override
  String get logs => 'Lokit';

  @override
  String get logsCopied => 'Lokit kopioitu';

  @override
  String get noLogsYet => 'Ei vielä lokeja. Aloita nauhoitus nähdäksesi mukautetun STT-toiminnan.';

  @override
  String deviceUsesCodec(String deviceName, String codecReason) {
    return '$deviceName käyttää $codecReason. Omia käytetään.';
  }

  @override
  String get omiTranscription => 'Omi-litterointi';

  @override
  String get bestInClassTranscription => 'Paras litterointi ilman asennusta';

  @override
  String get instantSpeakerLabels => 'Välittömät puhujatunnisteet';

  @override
  String get languageTranslation => 'Yli 100 kielen käännös';

  @override
  String get optimizedForConversation => 'Optimoitu keskusteluille';

  @override
  String get autoLanguageDetection => 'Automaattinen kielentunnistus';

  @override
  String get highAccuracy => 'Korkea tarkkuus';

  @override
  String get privacyFirst => 'Yksityisyys ensin';

  @override
  String get saveChanges => 'Tallenna muutokset';

  @override
  String get resetToDefault => 'Palauta oletusarvoon';

  @override
  String get viewTemplate => 'Näytä malli';

  @override
  String get trySomethingLike => 'Kokeile jotain tällaista...';

  @override
  String get tryIt => 'Kokeile';

  @override
  String get creatingPlan => 'Luodaan suunnitelmaa';

  @override
  String get developingLogic => 'Kehitetään logiikkaa';

  @override
  String get designingApp => 'Suunnitellaan sovellusta';

  @override
  String get generatingIconStep => 'Luodaan kuvaketta';

  @override
  String get finalTouches => 'Viimeiset viimeistelyt';

  @override
  String get processing => 'Käsitellään...';

  @override
  String get features => 'Ominaisuudet';

  @override
  String get creatingYourApp => 'Luodaan sovellustasi...';

  @override
  String get generatingIcon => 'Luodaan kuvaketta...';

  @override
  String get whatShouldWeMake => 'Mitä meidän pitäisi tehdä?';

  @override
  String get appName => 'Sovelluksen nimi';

  @override
  String get description => 'Kuvaus';

  @override
  String get publicLabel => 'Julkinen';

  @override
  String get privateLabel => 'Yksityinen';

  @override
  String get free => 'Ilmainen';

  @override
  String get perMonth => '/ kuukausi';

  @override
  String get tailoredConversationSummaries => 'Räätälöidyt keskusteluyhteenvedot';

  @override
  String get customChatbotPersonality => 'Mukautettu chatbot-persoonallisuus';

  @override
  String get makePublic => 'Julkaise';

  @override
  String get anyoneCanDiscover => 'Kuka tahansa voi löytää sovelluksesi';

  @override
  String get onlyYouCanUse => 'Vain sinä voit käyttää tätä sovellusta';

  @override
  String get paidApp => 'Maksullinen sovellus';

  @override
  String get usersPayToUse => 'Käyttäjät maksavat sovelluksesi käytöstä';

  @override
  String get freeForEveryone => 'Ilmainen kaikille';

  @override
  String get perMonthLabel => '/ kuukausi';

  @override
  String get creating => 'Luodaan...';

  @override
  String get createApp => 'Luo sovellus';

  @override
  String get searchingForDevices => 'Etsitään laitteita...';

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
  String get pairingSuccessful => 'PARILIITOS ONNISTUI';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Virhe yhdistettäessä Apple Watchiin: $error';
  }

  @override
  String get dontShowAgain => 'Älä näytä uudelleen';

  @override
  String get iUnderstand => 'Ymmärrän';

  @override
  String get enableBluetooth => 'Ota Bluetooth käyttöön';

  @override
  String get bluetoothNeeded =>
      'Omi tarvitsee Bluetoothin yhdistääkseen puettavaan laitteeseesi. Ota Bluetooth käyttöön ja yritä uudelleen.';

  @override
  String get contactSupport => 'Ota yhteyttä tukeen?';

  @override
  String get connectLater => 'Yhdistä myöhemmin';

  @override
  String get grantPermissions => 'Myönnä luvat';

  @override
  String get backgroundActivity => 'Taustatoiminta';

  @override
  String get backgroundActivityDesc => 'Anna Omin toimia taustalla parempaa vakautta varten';

  @override
  String get locationAccess => 'Sijaintipääsy';

  @override
  String get locationAccessDesc => 'Ota taustasijaintisi käyttöön täydelliseen kokemukseen';

  @override
  String get notifications => 'Ilmoitukset';

  @override
  String get notificationsDesc => 'Ota ilmoitukset käyttöön pysyäksesi ajan tasalla';

  @override
  String get locationServiceDisabled => 'Sijaintipalvelu poistettu käytöstä';

  @override
  String get locationServiceDisabledDesc =>
      'Sijaintipalvelu on poistettu käytöstä. Siirry kohtaan Asetukset > Tietosuoja ja turvallisuus > Sijaintipalvelut ja ota se käyttöön';

  @override
  String get backgroundLocationDenied => 'Taustasijaintipääsy evätty';

  @override
  String get backgroundLocationDeniedDesc =>
      'Siirry laitteen asetuksiin ja aseta sijaintioikeus asentoon \"Salli aina\"';

  @override
  String get lovingOmi => 'Pidätkö Omista?';

  @override
  String get leaveReviewIos =>
      'Auta meitä tavoittamaan lisää ihmisiä jättämällä arvostelu App Storeen. Palautteesi on meille tärkeää!';

  @override
  String get leaveReviewAndroid =>
      'Auta meitä tavoittamaan lisää ihmisiä jättämällä arvostelu Google Play -kauppaan. Palautteesi on meille tärkeää!';

  @override
  String get rateOnAppStore => 'Arvostele App Storessa';

  @override
  String get rateOnGooglePlay => 'Arvostele Google Playssa';

  @override
  String get maybeLater => 'Ehkä myöhemmin';

  @override
  String get speechProfileIntro => 'Omin on opittava tavoitteesi ja äänesi. Voit muokata sitä myöhemmin.';

  @override
  String get getStarted => 'Aloita';

  @override
  String get allDone => 'Kaikki valmista!';

  @override
  String get keepGoing => 'Jatka, teet loistavasti';

  @override
  String get skipThisQuestion => 'Ohita tämä kysymys';

  @override
  String get skipForNow => 'Ohita toistaiseksi';

  @override
  String get connectionError => 'Yhteysvirhe';

  @override
  String get connectionErrorDesc => 'Yhteys palvelimeen epäonnistui. Tarkista internet-yhteytesi ja yritä uudelleen.';

  @override
  String get invalidRecordingMultipleSpeakers => 'Virheellinen nauhoitus havaittu';

  @override
  String get multipleSpeakersDesc =>
      'Näyttää siltä, että nauhoituksessa on useita puhujia. Varmista, että olet hiljaisessa paikassa ja yritä uudelleen.';

  @override
  String get tooShortDesc => 'Puhetta ei havaittu tarpeeksi. Puhu enemmän ja yritä uudelleen.';

  @override
  String get invalidRecordingDesc => 'Varmista, että puhut vähintään 5 sekuntia ja korkeintaan 90 sekuntia.';

  @override
  String get areYouThere => 'Oletko siellä?';

  @override
  String get noSpeechDesc =>
      'Emme voineet havaita mitään puhetta. Varmista, että puhut vähintään 10 sekuntia ja korkeintaan 3 minuuttia.';

  @override
  String get connectionLost => 'Yhteys katkesi';

  @override
  String get connectionLostDesc => 'Yhteys keskeytyi. Tarkista internet-yhteytesi ja yritä uudelleen.';

  @override
  String get tryAgain => 'Yritä uudelleen';

  @override
  String get connectOmiOmiGlass => 'Yhdistä Omi / OmiGlass';

  @override
  String get continueWithoutDevice => 'Jatka ilman laitetta';

  @override
  String get permissionsRequired => 'Käyttöoikeudet vaaditaan';

  @override
  String get permissionsRequiredDesc =>
      'Tämä sovellus tarvitsee Bluetooth- ja sijaintioikeudet toimiakseen oikein. Ota ne käyttöön asetuksissa.';

  @override
  String get openSettings => 'Avaa asetukset';

  @override
  String get wantDifferentName => 'Haluatko käyttää eri nimeä?';

  @override
  String get whatsYourName => 'Mikä on nimesi?';

  @override
  String get speakTranscribeSummarize => 'Puhu. Litteroi. Tee yhteenveto.';

  @override
  String get signInWithApple => 'Kirjaudu Applella';

  @override
  String get signInWithGoogle => 'Kirjaudu Googlella';

  @override
  String get byContinuingAgree => 'Jatkamalla hyväksyt ';

  @override
  String get termsOfUse => 'Käyttöehdot';

  @override
  String get omiYourAiCompanion => 'Omi – tekoälykumppanisi';

  @override
  String get captureEveryMoment =>
      'Tallenna jokainen hetki. Saat tekoälyn\nluomat yhteenvedot. Älä enää tee muistiinpanoja.';

  @override
  String get appleWatchSetup => 'Apple Watch -asennus';

  @override
  String get permissionRequestedExclaim => 'Käyttöoikeus pyydetty!';

  @override
  String get microphonePermission => 'Mikrofonin käyttöoikeus';

  @override
  String get permissionGrantedNow =>
      'Käyttöoikeus myönnetty! Nyt:\n\nAvaa Omi-sovellus kellossasi ja napauta \"Jatka\" alla';

  @override
  String get needMicrophonePermission =>
      'Tarvitsemme mikrofonin käyttöoikeuden.\n\n1. Napauta \"Myönnä käyttöoikeus\"\n2. Salli iPhonessasi\n3. Kello-sovellus sulkeutuu\n4. Avaa uudelleen ja napauta \"Jatka\"';

  @override
  String get grantPermissionButton => 'Myönnä käyttöoikeus';

  @override
  String get needHelp => 'Tarvitsetko apua?';

  @override
  String get troubleshootingSteps =>
      'Vianmääritys:\n\n1. Varmista, että Omi on asennettu kelloosi\n2. Avaa Omi-sovellus kellossasi\n3. Etsi käyttöoikeuspyyntö\n4. Napauta \"Salli\" kehotettaessa\n5. Kello-sovellus sulkeutuu - avaa se uudelleen\n6. Palaa ja napauta \"Jatka\" iPhonessasi';

  @override
  String get recordingStartedSuccessfully => 'Nauhoitus aloitettu onnistuneesti!';

  @override
  String get permissionNotGrantedYet =>
      'Käyttöoikeutta ei ole vielä myönnetty. Varmista, että salloit mikrofonin käytön ja avasit sovelluksen kellossasi uudelleen.';

  @override
  String errorRequestingPermission(String error) {
    return 'Virhe pyydettäessä käyttöoikeutta: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'Virhe nauhoituksen aloittamisessa: $error';
  }

  @override
  String get selectPrimaryLanguage => 'Valitse ensisijainen kielesi';

  @override
  String get languageBenefits => 'Aseta kielesi tarkempaa litterointia ja henkilökohtaista kokemusta varten';

  @override
  String get whatsYourPrimaryLanguage => 'Mikä on ensisijainen kielesi?';

  @override
  String get selectYourLanguage => 'Valitse kielesi';

  @override
  String get personalGrowthJourney => 'Henkilökohtainen kasvumatkasi tekoälyn kanssa, joka kuuntelee jokaista sanaasi.';

  @override
  String get actionItemsTitle => 'Tehtävät';

  @override
  String get actionItemsDescription => 'Napauta muokataksesi • Pidä painettuna valitaksesi • Pyyhkäise toiminnoille';

  @override
  String get tabToDo => 'Tekemättä';

  @override
  String get tabDone => 'Tehty';

  @override
  String get tabOld => 'Vanhat';

  @override
  String get emptyTodoMessage => '🎉 Kaikki hoidettu!\nEi odottavia tehtäviä';

  @override
  String get emptyDoneMessage => 'Ei vielä suoritettuja kohteita';

  @override
  String get emptyOldMessage => '✅ Ei vanhoja tehtäviä';

  @override
  String get noItems => 'Ei kohteita';

  @override
  String get actionItemMarkedIncomplete => 'Tehtävä merkitty keskeneräiseksi';

  @override
  String get actionItemCompleted => 'Tehtävä suoritettu';

  @override
  String get deleteActionItemTitle => 'Poista toimintokohde';

  @override
  String get deleteActionItemMessage => 'Haluatko varmasti poistaa tämän toimintokohteen?';

  @override
  String get deleteSelectedItemsTitle => 'Poista valitut kohteet';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Haluatko varmasti poistaa $count valittua tehtävää?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'Tehtävä \"$description\" poistettu';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count tehtävää poistettu';
  }

  @override
  String get failedToDeleteItem => 'Tehtävän poisto epäonnistui';

  @override
  String get failedToDeleteItems => 'Kohteiden poisto epäonnistui';

  @override
  String get failedToDeleteSomeItems => 'Joidenkin kohteiden poisto epäonnistui';

  @override
  String get welcomeActionItemsTitle => 'Valmis tehtäville';

  @override
  String get welcomeActionItemsDescription =>
      'Tekoälysi poimii automaattisesti tehtävät ja to-do-listat keskusteluistasi. Ne näkyvät täällä, kun ne on luotu.';

  @override
  String get autoExtractionFeature => 'Poimittu automaattisesti keskusteluista';

  @override
  String get editSwipeFeature => 'Napauta muokataksesi, pyyhkäise suorittaaksesi tai poistaaksesi';

  @override
  String itemsSelected(int count) {
    return '$count valittu';
  }

  @override
  String get selectAll => 'Valitse kaikki';

  @override
  String get deleteSelected => 'Poista valitut';

  @override
  String get searchMemories => 'Hae muistoja...';

  @override
  String get memoryDeleted => 'Muisto poistettu.';

  @override
  String get undo => 'Kumoa';

  @override
  String get noMemoriesYet => '🧠 Ei vielä muistoja';

  @override
  String get noAutoMemories => 'Ei vielä automaattisesti poimittuja muistoja';

  @override
  String get noManualMemories => 'Ei vielä manuaalisia muistoja';

  @override
  String get noMemoriesInCategories => 'Ei muistoja näissä kategorioissa';

  @override
  String get noMemoriesFound => '🔍 Muistoja ei löytynyt';

  @override
  String get addFirstMemory => 'Lisää ensimmäinen muistosi';

  @override
  String get clearMemoryTitle => 'Tyhjennä Omin muisti';

  @override
  String get clearMemoryMessage => 'Haluatko varmasti tyhjentää Omin muistin? Tätä toimintoa ei voi perua.';

  @override
  String get clearMemoryButton => 'Tyhjennä muisti';

  @override
  String get memoryClearedSuccess => 'Omin muisti sinusta on tyhjennetty';

  @override
  String get noMemoriesToDelete => 'Ei poistettavia muistoja';

  @override
  String get createMemoryTooltip => 'Luo uusi muisto';

  @override
  String get createActionItemTooltip => 'Luo uusi tehtävä';

  @override
  String get memoryManagement => 'Muistinhallinta';

  @override
  String get filterMemories => 'Suodata muistoja';

  @override
  String totalMemoriesCount(int count) {
    return 'Sinulla on $count muistoa yhteensä';
  }

  @override
  String get publicMemories => 'Julkiset muistot';

  @override
  String get privateMemories => 'Yksityiset muistot';

  @override
  String get makeAllPrivate => 'Tee kaikki muistot yksityisiksi';

  @override
  String get makeAllPublic => 'Tee kaikki muistot julkisiksi';

  @override
  String get deleteAllMemories => 'Poista kaikki muistot';

  @override
  String get allMemoriesPrivateResult => 'Kaikki muistot ovat nyt yksityisiä';

  @override
  String get allMemoriesPublicResult => 'Kaikki muistot ovat nyt julkisia';

  @override
  String get newMemory => '✨ Uusi muisti';

  @override
  String get editMemory => '✏️ Muokkaa muistia';

  @override
  String get memoryContentHint => 'Pidän jäätelön syömisestä...';

  @override
  String get failedToSaveMemory => 'Tallennus epäonnistui. Tarkista yhteytesi.';

  @override
  String get saveMemory => 'Tallenna muisto';

  @override
  String get retry => 'Yritä uudelleen';

  @override
  String get createActionItem => 'Luo tehtävä';

  @override
  String get editActionItem => 'Muokkaa tehtävää';

  @override
  String get actionItemDescriptionHint => 'Mitä pitää tehdä?';

  @override
  String get actionItemDescriptionEmpty => 'Tehtävän kuvaus ei voi olla tyhjä.';

  @override
  String get actionItemUpdated => 'Tehtävä päivitetty';

  @override
  String get failedToUpdateActionItem => 'Tehtävän päivitys epäonnistui';

  @override
  String get actionItemCreated => 'Tehtävä luotu';

  @override
  String get failedToCreateActionItem => 'Tehtävän luonti epäonnistui';

  @override
  String get dueDate => 'Määräpäivä';

  @override
  String get time => 'Aika';

  @override
  String get addDueDate => 'Lisää eräpäivä';

  @override
  String get pressDoneToSave => 'Paina valmis tallentaaksesi';

  @override
  String get pressDoneToCreate => 'Paina valmis luodaksesi';

  @override
  String get filterAll => 'Kaikki';

  @override
  String get filterSystem => 'Tietoja sinusta';

  @override
  String get filterInteresting => 'Oivallukset';

  @override
  String get filterManual => 'Manuaalinen';

  @override
  String get completed => 'Valmis';

  @override
  String get markComplete => 'Merkitse valmiiksi';

  @override
  String get actionItemDeleted => 'Toimintokohde poistettu';

  @override
  String get failedToDeleteActionItem => 'Tehtävän poisto epäonnistui';

  @override
  String get deleteActionItemConfirmTitle => 'Poista tehtävä';

  @override
  String get deleteActionItemConfirmMessage => 'Haluatko varmasti poistaa tämän tehtävän?';

  @override
  String get appLanguage => 'Sovelluksen kieli';

  @override
  String get appInterfaceSectionTitle => 'SOVELLUKSEN KÄYTTÖLIITTYMÄ';

  @override
  String get speechTranscriptionSectionTitle => 'PUHE JA LITTEROINTI';

  @override
  String get languageSettingsHelperText =>
      'Sovelluksen kieli muuttaa valikkoja ja painikkeita. Puheen kieli vaikuttaa siihen, miten tallenteet litteroidaan.';

  @override
  String get translationNotice => 'Käännösilmoitus';

  @override
  String get translationNoticeMessage =>
      'Omi kääntää keskustelut ensisijaiselle kielellesi. Päivitä se milloin tahansa kohdassa Asetukset → Profiilit.';

  @override
  String get pleaseCheckInternetConnection => 'Tarkista internet-yhteytesi ja yritä uudelleen';

  @override
  String get pleaseSelectReason => 'Valitse syy';

  @override
  String get tellUsMoreWhatWentWrong => 'Kerro meille lisää siitä, mikä meni pieleen...';

  @override
  String get selectText => 'Valitse teksti';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Enintään $count tavoitetta sallittu';
  }

  @override
  String get conversationCannotBeMerged => 'Tätä keskustelua ei voi yhdistää (lukittu tai jo yhdistämässä)';

  @override
  String get pleaseEnterFolderName => 'Anna kansion nimi';

  @override
  String get failedToCreateFolder => 'Kansion luominen epäonnistui';

  @override
  String get failedToUpdateFolder => 'Kansion päivittäminen epäonnistui';

  @override
  String get folderName => 'Kansion nimi';

  @override
  String get descriptionOptional => 'Kuvaus (valinnainen)';

  @override
  String get failedToDeleteFolder => 'Kansion poistaminen epäonnistui';

  @override
  String get editFolder => 'Muokkaa kansiota';

  @override
  String get deleteFolder => 'Poista kansio';

  @override
  String get transcriptCopiedToClipboard => 'Litterointi kopioitu leikepöydälle';

  @override
  String get summaryCopiedToClipboard => 'Yhteenveto kopioitu leikepöydälle';

  @override
  String get conversationUrlCouldNotBeShared => 'Keskustelun URL-osoitetta ei voitu jakaa.';

  @override
  String get urlCopiedToClipboard => 'URL kopioitu leikepöydälle';

  @override
  String get exportTranscript => 'Vie litterointi';

  @override
  String get exportSummary => 'Vie yhteenveto';

  @override
  String get exportButton => 'Vie';

  @override
  String get actionItemsCopiedToClipboard => 'Toimintakohteet kopioitu leikepöydälle';

  @override
  String get summarize => 'Tiivistä';

  @override
  String get generateSummary => 'Luo yhteenveto';

  @override
  String get conversationNotFoundOrDeleted => 'Keskustelua ei löytynyt tai se on poistettu';

  @override
  String get deleteMemory => 'Poista muisti';

  @override
  String get thisActionCannotBeUndone => 'Tätä toimintoa ei voi peruuttaa.';

  @override
  String memoriesCount(int count) {
    return '$count muistoa';
  }

  @override
  String get noMemoriesInCategory => 'Tässä kategoriassa ei ole vielä muistoja';

  @override
  String get addYourFirstMemory => 'Lisää ensimmäinen muistosi';

  @override
  String get firmwareDisconnectUsb => 'Irrota USB';

  @override
  String get firmwareUsbWarning => 'USB-yhteys päivitysten aikana voi vahingoittaa laitettasi.';

  @override
  String get firmwareBatteryAbove15 => 'Akku yli 15%';

  @override
  String get firmwareEnsureBattery => 'Varmista, että laitteessasi on 15% akkua.';

  @override
  String get firmwareStableConnection => 'Vakaa yhteys';

  @override
  String get firmwareConnectWifi => 'Yhdistä WiFi:iin tai mobiiliverkkoon.';

  @override
  String failedToStartUpdate(String error) {
    return 'Päivityksen aloitus epäonnistui: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'Ennen päivitystä varmista:';

  @override
  String get confirmed => 'Vahvistettu!';

  @override
  String get release => 'Vapauta';

  @override
  String get slideToUpdate => 'Liu\'uta päivittääksesi';

  @override
  String copiedToClipboard(String title) {
    return '$title kopioitu leikepöydälle';
  }

  @override
  String get batteryLevel => 'Akun taso';

  @override
  String get productUpdate => 'Tuotepäivitys';

  @override
  String get offline => 'Offline-tilassa';

  @override
  String get available => 'Saatavilla';

  @override
  String get unpairDeviceDialogTitle => 'Poista laitteen pariliitos';

  @override
  String get unpairDeviceDialogMessage =>
      'Tämä poistaa laitteen pariliitoksen, jotta se voidaan yhdistää toiseen puhelimeen. Sinun on siirryttävä Asetukset > Bluetooth ja unohdettava laite prosessin viimeistelemiseksi.';

  @override
  String get unpair => 'Poista pariliitos';

  @override
  String get unpairAndForgetDevice => 'Poista pariliitos ja unohda laite';

  @override
  String get unknownDevice => 'Tuntematon laite';

  @override
  String get unknown => 'Tuntematon';

  @override
  String get productName => 'Tuotteen nimi';

  @override
  String get serialNumber => 'Sarjanumero';

  @override
  String get connected => 'Yhdistetty';

  @override
  String get privacyPolicyTitle => 'Tietosuojakäytäntö';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label copied';
  }

  @override
  String get noApiKeysYet => 'Ei vielä API-avaimia. Luo yksi integroidaksesi sovelluksesi kanssa.';

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
  String get debugAndDiagnostics => 'Virheenkorjaus ja diagnostiikka';

  @override
  String get autoDeletesAfter3Days => 'Poistetaan automaattisesti 3 päivän kuluttua';

  @override
  String get helpsDiagnoseIssues => 'Auttaa ongelmien diagnosoinnissa';

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
  String get realTimeTranscript => 'Reaaliaikainen litterointi';

  @override
  String get experimental => 'Kokeellinen';

  @override
  String get transcriptionDiagnostics => 'Litterointidiagnostiikka';

  @override
  String get detailedDiagnosticMessages => 'Yksityiskohtaiset diagnostiikkaviestit';

  @override
  String get autoCreateSpeakers => 'Luo puhujat automaattisesti';

  @override
  String get autoCreateWhenNameDetected => 'Auto-create when name detected';

  @override
  String get followUpQuestions => 'Jatkokysymykset';

  @override
  String get suggestQuestionsAfterConversations => 'Ehdota kysymyksiä keskustelujen jälkeen';

  @override
  String get goalTracker => 'Tavoitteiden seuranta';

  @override
  String get trackPersonalGoalsOnHomepage => 'Track your personal goals on homepage';

  @override
  String get dailyReflection => 'Päivittäinen pohdinta';

  @override
  String get get9PmReminderToReflect => 'Get a 9 PM reminder to reflect on your day';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'Toimintokohteen kuvaus ei voi olla tyhjä';

  @override
  String get saved => 'Tallennettu';

  @override
  String get overdue => 'Myöhässä';

  @override
  String get failedToUpdateDueDate => 'Eräpäivän päivittäminen epäonnistui';

  @override
  String get markIncomplete => 'Merkitse keskeneräiseksi';

  @override
  String get editDueDate => 'Muokkaa eräpäivää';

  @override
  String get setDueDate => 'Aseta määräpäivä';

  @override
  String get clearDueDate => 'Tyhjennä eräpäivä';

  @override
  String get failedToClearDueDate => 'Eräpäivän tyhjentäminen epäonnistui';

  @override
  String get mondayAbbr => 'Ma';

  @override
  String get tuesdayAbbr => 'Ti';

  @override
  String get wednesdayAbbr => 'Ke';

  @override
  String get thursdayAbbr => 'To';

  @override
  String get fridayAbbr => 'Pe';

  @override
  String get saturdayAbbr => 'La';

  @override
  String get sundayAbbr => 'Su';

  @override
  String get howDoesItWork => 'Miten se toimii?';

  @override
  String get sdCardSyncDescription => 'SD-kortin synkronointi tuo muistosi SD-kortilta sovellukseen';

  @override
  String get checksForAudioFiles => 'Tarkistaa äänitiedostot SD-kortilla';

  @override
  String get omiSyncsAudioFiles => 'Omi synkronoi sitten äänitiedostot palvelimen kanssa';

  @override
  String get serverProcessesAudio => 'Palvelin käsittelee äänitiedostot ja luo muistoja';

  @override
  String get youreAllSet => 'Olet valmis!';

  @override
  String get welcomeToOmiDescription =>
      'Tervetuloa Omiin! AI-kumppanisi on valmis auttamaan sinua keskusteluissa, tehtävissä ja muussa.';

  @override
  String get startUsingOmi => 'Aloita Omin käyttö';

  @override
  String get back => 'Takaisin';

  @override
  String get keyboardShortcuts => 'Pikanäppäimet';

  @override
  String get toggleControlBar => 'Vaihda ohjausp alkki';

  @override
  String get pressKeys => 'Paina näppäimiä...';

  @override
  String get cmdRequired => '⌘ vaaditaan';

  @override
  String get invalidKey => 'Virheellinen näppäin';

  @override
  String get space => 'Välilyönti';

  @override
  String get search => 'Etsi';

  @override
  String get searchPlaceholder => 'Etsi...';

  @override
  String get untitledConversation => 'Nimetön keskustelu';

  @override
  String countRemaining(String count) {
    return '$count jäljellä';
  }

  @override
  String get addGoal => 'Lisää tavoite';

  @override
  String get editGoal => 'Muokkaa tavoitetta';

  @override
  String get icon => 'Kuvake';

  @override
  String get goalTitle => 'Tavoitteen otsikko';

  @override
  String get current => 'Nykyinen';

  @override
  String get target => 'Tavoite';

  @override
  String get saveGoal => 'Tallenna';

  @override
  String get goals => 'Tavoitteet';

  @override
  String get tapToAddGoal => 'Napauta lisätäksesi tavoitteen';

  @override
  String welcomeBack(String name) {
    return 'Tervetuloa takaisin, $name';
  }

  @override
  String get yourConversations => 'Keskustelusi';

  @override
  String get reviewAndManageConversations => 'Tarkista ja hallitse tallennettuja keskustelujasi';

  @override
  String get startCapturingConversations => 'Aloita keskustelujen tallentaminen Omi-laitteellasi nähdäksesi ne täällä.';

  @override
  String get useMobileAppToCapture => 'Käytä mobiilisovellusta äänen tallentamiseen';

  @override
  String get conversationsProcessedAutomatically => 'Keskustelut käsitellään automaattisesti';

  @override
  String get getInsightsInstantly => 'Saat oivalluksia ja yhteenvetoja välittömästi';

  @override
  String get showAll => 'Näytä kaikki →';

  @override
  String get noTasksForToday => 'Ei tehtäviä tänään.\\nKysy Omilta lisää tehtäviä tai luo ne manuaalisesti.';

  @override
  String get dailyScore => 'PÄIVITTÄINEN PISTEET';

  @override
  String get dailyScoreDescription => 'Pisteet, jotka auttavat keskittymään paremmin toteutukseen.';

  @override
  String get searchResults => 'Hakutulokset';

  @override
  String get actionItems => 'Toimintakohdat';

  @override
  String get tasksToday => 'Tänään';

  @override
  String get tasksTomorrow => 'Huomenna';

  @override
  String get tasksNoDeadline => 'Ei määräaikaa';

  @override
  String get tasksLater => 'Myöhemmin';

  @override
  String get loadingTasks => 'Ladataan tehtäviä...';

  @override
  String get tasks => 'Tehtävät';

  @override
  String get swipeTasksToIndent => 'Pyyhkäise tehtäviä sisennykseen, vedä kategorioiden välillä';

  @override
  String get create => 'Luo';

  @override
  String get noTasksYet => 'Ei tehtäviä vielä';

  @override
  String get tasksFromConversationsWillAppear =>
      'Keskusteluistasi tulevat tehtävät näkyvät tässä.\nNapsauta Luo lisätäksesi yhden manuaalisesti.';

  @override
  String get monthJan => 'Tammi';

  @override
  String get monthFeb => 'Helmi';

  @override
  String get monthMar => 'Maalis';

  @override
  String get monthApr => 'Huhti';

  @override
  String get monthMay => 'Touko';

  @override
  String get monthJun => 'Kesä';

  @override
  String get monthJul => 'Heinä';

  @override
  String get monthAug => 'Elo';

  @override
  String get monthSep => 'Syys';

  @override
  String get monthOct => 'Loka';

  @override
  String get monthNov => 'Marras';

  @override
  String get monthDec => 'Joulu';

  @override
  String get timePM => 'IP';

  @override
  String get timeAM => 'AP';

  @override
  String get actionItemUpdatedSuccessfully => 'Tehtävä päivitetty onnistuneesti';

  @override
  String get actionItemCreatedSuccessfully => 'Tehtävä luotu onnistuneesti';

  @override
  String get actionItemDeletedSuccessfully => 'Tehtävä poistettu onnistuneesti';

  @override
  String get deleteActionItem => 'Poista tehtävä';

  @override
  String get deleteActionItemConfirmation => 'Haluatko varmasti poistaa tämän tehtävän? Tätä toimintoa ei voi perua.';

  @override
  String get enterActionItemDescription => 'Anna tehtävän kuvaus...';

  @override
  String get markAsCompleted => 'Merkitse valmiiksi';

  @override
  String get setDueDateAndTime => 'Aseta määräpäivä ja aika';

  @override
  String get reloadingApps => 'Ladataan sovelluksia uudelleen...';

  @override
  String get loadingApps => 'Ladataan sovelluksia...';

  @override
  String get browseInstallCreateApps => 'Selaa, asenna ja luo sovelluksia';

  @override
  String get all => 'Kaikki';

  @override
  String get open => 'Avaa';

  @override
  String get install => 'Asenna';

  @override
  String get noAppsAvailable => 'Ei saatavilla olevia sovelluksia';

  @override
  String get unableToLoadApps => 'Sovellusten lataus epäonnistui';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'Kokeile hakuehtojen tai suodattimien muuttamista';

  @override
  String get checkBackLaterForNewApps => 'Tarkista myöhemmin uudet sovellukset';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'Tarkista internet-yhteytesi ja yritä uudelleen';

  @override
  String get createNewApp => 'Luo uusi sovellus';

  @override
  String get buildSubmitCustomOmiApp => 'Rakenna ja lähetä mukautettu Omi-sovelluksesi';

  @override
  String get submittingYourApp => 'Lähetetään sovellustasi...';

  @override
  String get preparingFormForYou => 'Valmistellaan lomaketta sinulle...';

  @override
  String get appDetails => 'Sovelluksen tiedot';

  @override
  String get paymentDetails => 'Maksutiedot';

  @override
  String get previewAndScreenshots => 'Esikatselu ja kuvakaappaukset';

  @override
  String get appCapabilities => 'Sovelluksen ominaisuudet';

  @override
  String get aiPrompts => 'Tekoälykehotukset';

  @override
  String get chatPrompt => 'Chat-kehote';

  @override
  String get chatPromptPlaceholder =>
      'Olet mahtava sovellus, tehtäväsi on vastata käyttäjien kyselyihin ja saada heidät tuntemaan olonsa hyväksi...';

  @override
  String get conversationPrompt => 'Keskustelukehote';

  @override
  String get conversationPromptPlaceholder => 'Olet mahtava sovellus, saat keskustelun litteroinnin ja yhteenvedon...';

  @override
  String get notificationScopes => 'Ilmoitusalueet';

  @override
  String get appPrivacyAndTerms => 'Sovelluksen tietosuoja ja ehdot';

  @override
  String get makeMyAppPublic => 'Tee sovelluksestani julkinen';

  @override
  String get submitAppTermsAgreement =>
      'Lähettämällä tämän sovelluksen hyväksyn Omi AI:n käyttöehdot ja tietosuojakäytännön';

  @override
  String get submitApp => 'Lähetä sovellus';

  @override
  String get needHelpGettingStarted => 'Tarvitsetko apua aloittamiseen?';

  @override
  String get clickHereForAppBuildingGuides =>
      'Napsauta tästä sovelluksen rakentamisohjeiden ja dokumentaation saamiseksi';

  @override
  String get submitAppQuestion => 'Lähetetäänkö sovellus?';

  @override
  String get submitAppPublicDescription =>
      'Sovelluksesi tarkistetaan ja julkaistaan. Voit alkaa käyttää sitä heti, jopa tarkistuksen aikana!';

  @override
  String get submitAppPrivateDescription =>
      'Sovelluksesi tarkistetaan ja asetetaan saatavillesi yksityisesti. Voit alkaa käyttää sitä heti, jopa tarkistuksen aikana!';

  @override
  String get startEarning => 'Aloita ansaitseminen! 💰';

  @override
  String get connectStripeOrPayPal => 'Yhdistä Stripe tai PayPal vastaanottaaksesi maksuja sovelluksestasi.';

  @override
  String get connectNow => 'Yhdistä nyt';

  @override
  String installsCount(String count) {
    return '$count+ asennusta';
  }

  @override
  String get uninstallApp => 'Poista sovellus';

  @override
  String get subscribe => 'Tilaa';

  @override
  String get dataAccessNotice => 'Tietojen käyttöilmoitus';

  @override
  String get dataAccessWarning =>
      'Tämä sovellus käyttää tietojasi. Omi AI ei ole vastuussa siitä, miten tietojasi käytetään, muokataan tai poistetaan tällä sovelluksella';

  @override
  String get installApp => 'Asenna sovellus';

  @override
  String get betaTesterNotice =>
      'Olet tämän sovelluksen beta-testaaja. Se ei ole vielä julkinen. Se tulee julkiseksi hyväksynnän jälkeen.';

  @override
  String get appUnderReviewOwner =>
      'Sovelluksesi on tarkistettavana ja näkyvissä vain sinulle. Se tulee julkiseksi hyväksynnän jälkeen.';

  @override
  String get appRejectedNotice =>
      'Sovelluksesi on hylätty. Päivitä sovelluksen tiedot ja lähetä se uudelleen tarkistettavaksi.';

  @override
  String get setupSteps => 'Asennusvaiheet';

  @override
  String get setupInstructions => 'Asennusohjeet';

  @override
  String get integrationInstructions => 'Integrointiohjeet';

  @override
  String get preview => 'Esikatselu';

  @override
  String get aboutTheApp => 'Tietoja sovelluksesta';

  @override
  String get aboutThePersona => 'Tietoja persoonasta';

  @override
  String get chatPersonality => 'Chatin persoonallisuus';

  @override
  String get ratingsAndReviews => 'Arviot ja arvostelut';

  @override
  String get noRatings => 'ei arvioita';

  @override
  String ratingsCount(String count) {
    return '$count+ arvioita';
  }

  @override
  String get errorActivatingApp => 'Virhe sovelluksen aktivoinnissa';

  @override
  String get integrationSetupRequired => 'Jos tämä on integraatiosovellus, varmista että asennus on valmis.';

  @override
  String get installed => 'Asennettu';

  @override
  String get appIdLabel => 'Sovelluksen tunnus';

  @override
  String get appNameLabel => 'Sovelluksen nimi';

  @override
  String get appNamePlaceholder => 'Upea sovellukseni';

  @override
  String get pleaseEnterAppName => 'Anna sovelluksen nimi';

  @override
  String get categoryLabel => 'Kategoria';

  @override
  String get selectCategory => 'Valitse kategoria';

  @override
  String get descriptionLabel => 'Kuvaus';

  @override
  String get appDescriptionPlaceholder =>
      'Upea sovellukseni on loistava sovellus, joka tekee hämmästyttäviä asioita. Se on paras sovellus!';

  @override
  String get pleaseProvideValidDescription => 'Anna kelvollinen kuvaus';

  @override
  String get appPricingLabel => 'Sovelluksen hinnoittelu';

  @override
  String get noneSelected => 'Ei valittu';

  @override
  String get appIdCopiedToClipboard => 'Sovelluksen tunnus kopioitu leikepöydälle';

  @override
  String get appCategoryModalTitle => 'Sovelluksen kategoria';

  @override
  String get pricingFree => 'Ilmainen';

  @override
  String get pricingPaid => 'Maksullinen';

  @override
  String get loadingCapabilities => 'Ladataan ominaisuuksia...';

  @override
  String get filterInstalled => 'Asennettu';

  @override
  String get filterMyApps => 'Omat sovellukseni';

  @override
  String get clearSelection => 'Tyhjennä valinta';

  @override
  String get filterCategory => 'Kategoria';

  @override
  String get rating4PlusStars => '4+ tähteä';

  @override
  String get rating3PlusStars => '3+ tähteä';

  @override
  String get rating2PlusStars => '2+ tähteä';

  @override
  String get rating1PlusStars => '1+ tähti';

  @override
  String get filterRating => 'Arvostelu';

  @override
  String get filterCapabilities => 'Ominaisuudet';

  @override
  String get noNotificationScopesAvailable => 'Ilmoitusalueita ei ole saatavilla';

  @override
  String get popularApps => 'Suositut sovellukset';

  @override
  String get pleaseProvidePrompt => 'Anna kehote';

  @override
  String chatWithAppName(String appName) {
    return 'Chat sovelluksen $appName kanssa';
  }

  @override
  String get defaultAiAssistant => 'Oletus AI-assistentti';

  @override
  String get readyToChat => '✨ Valmis chattailemaan!';

  @override
  String get connectionNeeded => '🌐 Yhteys vaaditaan';

  @override
  String get startConversation => 'Aloita keskustelu ja anna taikuuden alkaa';

  @override
  String get checkInternetConnection => 'Tarkista internetyhteytesi';

  @override
  String get wasThisHelpful => 'Oliko tästä apua?';

  @override
  String get thankYouForFeedback => 'Kiitos palautteestasi!';

  @override
  String get maxFilesUploadError => 'Voit ladata vain 4 tiedostoa kerralla';

  @override
  String get attachedFiles => '📎 Liitetyt tiedostot';

  @override
  String get takePhoto => 'Ota valokuva';

  @override
  String get captureWithCamera => 'Ota kameralla';

  @override
  String get selectImages => 'Valitse kuvia';

  @override
  String get chooseFromGallery => 'Valitse galleriasta';

  @override
  String get selectFile => 'Valitse tiedosto';

  @override
  String get chooseAnyFileType => 'Valitse mikä tahansa tiedostotyyppi';

  @override
  String get cannotReportOwnMessages => 'Et voi raportoida omia viestejäsi';

  @override
  String get messageReportedSuccessfully => '✅ Viesti raportoitu onnistuneesti';

  @override
  String get confirmReportMessage => 'Haluatko varmasti raportoida tämän viestin?';

  @override
  String get selectChatAssistant => 'Valitse chat-assistentti';

  @override
  String get enableMoreApps => 'Ota käyttöön lisää sovelluksia';

  @override
  String get chatCleared => 'Chat tyhjennetty';

  @override
  String get clearChatTitle => 'Tyhjennä chat?';

  @override
  String get confirmClearChat => 'Haluatko varmasti tyhjentää chatin? Tätä toimintoa ei voi peruuttaa.';

  @override
  String get copy => 'Kopioi';

  @override
  String get share => 'Jaa';

  @override
  String get report => 'Raportoi';

  @override
  String get microphonePermissionRequired => 'Mikrofonin lupa vaaditaan äänen tallennukseen.';

  @override
  String get microphonePermissionDenied =>
      'Mikrofonin lupa evätty. Anna lupa kohdassa Järjestelmäasetukset > Tietosuoja ja turvallisuus > Mikrofoni.';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'Mikrofonin luvan tarkistus epäonnistui: $error';
  }

  @override
  String get failedToTranscribeAudio => 'Äänen litterointi epäonnistui';

  @override
  String get transcribing => 'Litteroidaan...';

  @override
  String get transcriptionFailed => 'Litterointi epäonnistui';

  @override
  String get discardedConversation => 'Hylätty keskustelu';

  @override
  String get at => 'klo';

  @override
  String get from => 'alkaen';

  @override
  String get copied => 'Kopioitu!';

  @override
  String get copyLink => 'Kopioi linkki';

  @override
  String get hideTranscript => 'Piilota litterointi';

  @override
  String get viewTranscript => 'Näytä litterointi';

  @override
  String get conversationDetails => 'Keskustelun tiedot';

  @override
  String get transcript => 'Litterointi';

  @override
  String segmentsCount(int count) {
    return '$count segmenttiä';
  }

  @override
  String get noTranscriptAvailable => 'Litterointia ei ole saatavilla';

  @override
  String get noTranscriptMessage => 'Tällä keskustelulla ei ole litterointia.';

  @override
  String get conversationUrlCouldNotBeGenerated => 'Keskustelun URL-osoitetta ei voitu luoda.';

  @override
  String get failedToGenerateConversationLink => 'Keskustelulinkin luominen epäonnistui';

  @override
  String get failedToGenerateShareLink => 'Jakamislinkin luominen epäonnistui';

  @override
  String get reloadingConversations => 'Ladataan keskusteluja uudelleen...';

  @override
  String get user => 'Käyttäjä';

  @override
  String get starred => 'Tähdellä merkitty';

  @override
  String get date => 'Päivämäärä';

  @override
  String get noResultsFound => 'Tuloksia ei löytynyt';

  @override
  String get tryAdjustingSearchTerms => 'Yritä muokata hakuehtojasi';

  @override
  String get starConversationsToFindQuickly => 'Merkitse keskustelut tähdellä löytääksesi ne nopeasti täältä';

  @override
  String noConversationsOnDate(String date) {
    return 'Ei keskusteluja päivämäärällä $date';
  }

  @override
  String get trySelectingDifferentDate => 'Yritä valita eri päivämäärä';

  @override
  String get conversations => 'Keskustelut';

  @override
  String get chat => 'Keskustelu';

  @override
  String get actions => 'Toiminnot';

  @override
  String get syncAvailable => 'Synkronointi saatavilla';

  @override
  String get referAFriend => 'Suosittele ystävälle';

  @override
  String get help => 'Ohje';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'Päivitä Pro-versioon';

  @override
  String get getOmiDevice => 'Hanki Omi-laite';

  @override
  String get wearableAiCompanion => 'Puettava AI-kumppani';

  @override
  String get loadingMemories => 'Ladataan muistoja...';

  @override
  String get allMemories => 'Kaikki muistot';

  @override
  String get aboutYou => 'Sinusta';

  @override
  String get manual => 'Manuaalinen';

  @override
  String get loadingYourMemories => 'Ladataan muistojasi...';

  @override
  String get createYourFirstMemory => 'Luo ensimmäinen muistosi aloittaaksesi';

  @override
  String get tryAdjustingFilter => 'Yritä muokata hakuasi tai suodatinta';

  @override
  String get whatWouldYouLikeToRemember => 'Mitä haluaisit muistaa?';

  @override
  String get category => 'Kategoria';

  @override
  String get public => 'Julkinen';

  @override
  String get failedToSaveCheckConnection => 'Tallennus epäonnistui. Tarkista yhteytesi.';

  @override
  String get createMemory => 'Luo muisti';

  @override
  String get deleteMemoryConfirmation => 'Haluatko varmasti poistaa tämän muistin? Tätä toimintoa ei voi perua.';

  @override
  String get makePrivate => 'Tee yksityiseksi';

  @override
  String get organizeAndControlMemories => 'Järjestä ja hallitse muistojasi';

  @override
  String get total => 'Yhteensä';

  @override
  String get makeAllMemoriesPrivate => 'Tee kaikki muistot yksityisiksi';

  @override
  String get setAllMemoriesToPrivate => 'Aseta kaikki muistot yksityisiksi';

  @override
  String get makeAllMemoriesPublic => 'Tee kaikki muistot julkisiksi';

  @override
  String get setAllMemoriesToPublic => 'Aseta kaikki muistot julkisiksi';

  @override
  String get permanentlyRemoveAllMemories => 'Poista pysyvästi kaikki muistot Omista';

  @override
  String get allMemoriesAreNowPrivate => 'Kaikki muistot ovat nyt yksityisiä';

  @override
  String get allMemoriesAreNowPublic => 'Kaikki muistot ovat nyt julkisia';

  @override
  String get clearOmisMemory => 'Tyhjennä Omin muisti';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Haluatko varmasti tyhjentää Omin muistin? Tätä toimintoa ei voi perua ja se poistaa pysyvästi kaikki $count muistoa.';
  }

  @override
  String get omisMemoryCleared => 'Omin muisti sinusta on tyhjennetty';

  @override
  String get welcomeToOmi => 'Tervetuloa Omi';

  @override
  String get continueWithApple => 'Jatka Applella';

  @override
  String get continueWithGoogle => 'Jatka Googlella';

  @override
  String get byContinuingYouAgree => 'Jatkamalla hyväksyt ';

  @override
  String get termsOfService => 'Käyttöehdot';

  @override
  String get and => ' ja ';

  @override
  String get dataAndPrivacy => 'Tiedot ja tietosuoja';

  @override
  String get secureAuthViaAppleId => 'Turvallinen todennus Apple ID:n kautta';

  @override
  String get secureAuthViaGoogleAccount => 'Turvallinen todennus Google-tilin kautta';

  @override
  String get whatWeCollect => 'Mitä keräämme';

  @override
  String get dataCollectionMessage =>
      'Jatkamalla keskustelusi, tallenteet ja henkilötiedot tallennetaan turvallisesti palvelimillemme tarjotaksemme tekoälyavusteisia näkemyksiä ja mahdollistaaksemme kaikki sovelluksen ominaisuudet.';

  @override
  String get dataProtection => 'Tietosuoja';

  @override
  String get yourDataIsProtected => 'Tietosi ovat suojattuja ja niitä säätelee ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'Valitse ensisijainen kielesi';

  @override
  String get chooseYourLanguage => 'Valitse kielesi';

  @override
  String get selectPreferredLanguageForBestExperience => 'Valitse suosikkikielesi parhaan Omi-kokemuksen saamiseksi';

  @override
  String get searchLanguages => 'Hae kieliä...';

  @override
  String get selectALanguage => 'Valitse kieli';

  @override
  String get tryDifferentSearchTerm => 'Kokeile eri hakusanaa';

  @override
  String get pleaseEnterYourName => 'Syötä nimesi';

  @override
  String get nameMustBeAtLeast2Characters => 'Nimen on oltava vähintään 2 merkkiä';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'Kerro meille, miten haluaisit, että sinut puhutellaan. Tämä auttaa personoimaan Omi-kokemuksesi.';

  @override
  String charactersCount(int count) {
    return '$count merkkiä';
  }

  @override
  String get enableFeaturesForBestExperience =>
      'Ota käyttöön ominaisuudet parhaan Omi-kokemuksen saamiseksi laitteellasi.';

  @override
  String get microphoneAccess => 'Mikrofonin käyttöoikeus';

  @override
  String get recordAudioConversations => 'Tallenna äänikeskusteluja';

  @override
  String get microphoneAccessDescription =>
      'Omi tarvitsee mikrofonin käyttöoikeuden tallentaakseen keskustelusi ja tarjotakseen transkriptioita.';

  @override
  String get screenRecording => 'Näytön tallennus';

  @override
  String get captureSystemAudioFromMeetings => 'Tallenna järjestelmän ääntä kokouksista';

  @override
  String get screenRecordingDescription =>
      'Omi tarvitsee näytön tallennusluvan tallentaakseen järjestelmän ääntä selainpohjaisista kokouksistasi.';

  @override
  String get accessibility => 'Esteettömyys';

  @override
  String get detectBrowserBasedMeetings => 'Tunnista selainpohjaiset kokoukset';

  @override
  String get accessibilityDescription =>
      'Omi tarvitsee esteettömyysluvan tunnistaakseen, milloin liityt Zoom-, Meet- tai Teams-kokouksiin selaimessasi.';

  @override
  String get pleaseWait => 'Odota...';

  @override
  String get joinTheCommunity => 'Liity yhteisöön!';

  @override
  String get loadingProfile => 'Ladataan profiilia...';

  @override
  String get profileSettings => 'Profiilin asetukset';

  @override
  String get noEmailSet => 'Sähköpostia ei ole asetettu';

  @override
  String get userIdCopiedToClipboard => 'Käyttäjätunnus kopioitu';

  @override
  String get yourInformation => 'Sinun Tietosi';

  @override
  String get setYourName => 'Aseta nimesi';

  @override
  String get changeYourName => 'Vaihda nimesi';

  @override
  String get manageYourOmiPersona => 'Hallinnoi Omi-personaasi';

  @override
  String get voiceAndPeople => 'Ääni ja Ihmiset';

  @override
  String get teachOmiYourVoice => 'Opeta Omi äänesi';

  @override
  String get tellOmiWhoSaidIt => 'Kerro Omi:lle, kuka sen sanoi 🗣️';

  @override
  String get payment => 'Maksu';

  @override
  String get addOrChangeYourPaymentMethod => 'Lisää tai vaihda maksutapa';

  @override
  String get preferences => 'Asetukset';

  @override
  String get helpImproveOmiBySharing => 'Auta parantamaan Omi:ta jakamalla anonymisoituja analytiikkatietoja';

  @override
  String get deleteAccount => 'Poista Tili';

  @override
  String get deleteYourAccountAndAllData => 'Poista tilisi ja kaikki tiedot';

  @override
  String get clearLogs => 'Tyhjennä lokit';

  @override
  String get debugLogsCleared => 'Virheenkorjauslokit tyhjennetty';

  @override
  String get exportConversations => 'Vie keskustelut';

  @override
  String get exportAllConversationsToJson => 'Vie kaikki keskustelusi JSON-tiedostoon.';

  @override
  String get conversationsExportStarted => 'Keskustelujen vienti aloitettu. Tämä voi kestää muutaman sekunnin, odota.';

  @override
  String get mcpDescription =>
      'Yhdistääksesi Omin muihin sovelluksiin lukeaksesi, etsiäksesi ja hallitaksesi muistojasi ja keskustelujasi. Luo avain aloittaaksesi.';

  @override
  String get apiKeys => 'API-avaimet';

  @override
  String errorLabel(String error) {
    return 'Virhe: $error';
  }

  @override
  String get noApiKeysFound => 'API-avaimia ei löytynyt. Luo yksi aloittaaksesi.';

  @override
  String get advancedSettings => 'Lisäasetukset';

  @override
  String get triggersWhenNewConversationCreated => 'Käynnistyy, kun uusi keskustelu luodaan.';

  @override
  String get triggersWhenNewTranscriptReceived => 'Käynnistyy, kun uusi litterointi vastaanotetaan.';

  @override
  String get realtimeAudioBytes => 'Reaaliaikaiset äänitavut';

  @override
  String get triggersWhenAudioBytesReceived => 'Käynnistyy, kun äänitavut vastaanotetaan.';

  @override
  String get everyXSeconds => 'Joka x sekunti';

  @override
  String get triggersWhenDaySummaryGenerated => 'Käynnistyy, kun päivän yhteenveto luodaan.';

  @override
  String get tryLatestExperimentalFeatures => 'Kokeile Omi-tiimin uusimpia kokeellisia ominaisuuksia.';

  @override
  String get transcriptionServiceDiagnosticStatus => 'Litterointipalvelun diagnostiikkatila';

  @override
  String get enableDetailedDiagnosticMessages =>
      'Ota käyttöön yksityiskohtaiset diagnostiikkaviestit litterointipalvelusta';

  @override
  String get autoCreateAndTagNewSpeakers => 'Luo ja merkitse uudet puhujat automaattisesti';

  @override
  String get automaticallyCreateNewPerson => 'Luo automaattisesti uusi henkilö, kun litterointiin havaitaan nimi.';

  @override
  String get pilotFeatures => 'Pilottiominaisuudet';

  @override
  String get pilotFeaturesDescription => 'Nämä ominaisuudet ovat testejä, eikä tukea taata.';

  @override
  String get suggestFollowUpQuestion => 'Ehdota jatkokysymystä';

  @override
  String get saveSettings => 'Tallenna Asetukset';

  @override
  String get syncingDeveloperSettings => 'Synkronoidaan kehittäjäasetuksia...';

  @override
  String get summary => 'Yhteenveto';

  @override
  String get auto => 'Automaattinen';

  @override
  String get noSummaryForApp =>
      'Tälle sovellukselle ei ole saatavilla yhteenvetoa. Kokeile toista sovellusta parempien tulosten saamiseksi.';

  @override
  String get tryAnotherApp => 'Kokeile toista sovellusta';

  @override
  String generatedBy(String appName) {
    return 'Luonut $appName';
  }

  @override
  String get overview => 'Yleiskatsaus';

  @override
  String get otherAppResults => 'Muiden sovellusten tulokset';

  @override
  String get unknownApp => 'Tuntematon sovellus';

  @override
  String get noSummaryAvailable => 'Yhteenvetoa ei ole saatavilla';

  @override
  String get conversationNoSummaryYet => 'Tällä keskustelulla ei ole vielä yhteenvetoa.';

  @override
  String get chooseSummarizationApp => 'Valitse yhteenvetosovellus';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName asetettu oletusyhteenvetosovellukseksi';
  }

  @override
  String get letOmiChooseAutomatically => 'Anna Omin valita paras sovellus automaattisesti';

  @override
  String get deleteConversationConfirmation =>
      'Haluatko varmasti poistaa tämän keskustelun? Tätä toimintoa ei voi kumota.';

  @override
  String get conversationDeleted => 'Keskustelu poistettu';

  @override
  String get generatingLink => 'Luodaan linkkiä...';

  @override
  String get editConversation => 'Muokkaa keskustelua';

  @override
  String get conversationLinkCopiedToClipboard => 'Keskustelun linkki kopioitu leikepöydälle';

  @override
  String get conversationTranscriptCopiedToClipboard => 'Keskustelun litterointi kopioitu leikepöydälle';

  @override
  String get editConversationDialogTitle => 'Muokkaa keskustelua';

  @override
  String get changeTheConversationTitle => 'Muuta keskustelun otsikkoa';

  @override
  String get conversationTitle => 'Keskustelun otsikko';

  @override
  String get enterConversationTitle => 'Syötä keskustelun otsikko...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'Keskustelun otsikko päivitetty onnistuneesti';

  @override
  String get failedToUpdateConversationTitle => 'Keskustelun otsikon päivitys epäonnistui';

  @override
  String get errorUpdatingConversationTitle => 'Virhe keskustelun otsikon päivityksessä';

  @override
  String get settingUp => 'Asetetaan...';

  @override
  String get startYourFirstRecording => 'Aloita ensimmäinen tallennus';

  @override
  String get preparingSystemAudioCapture => 'Järjestelmän äänitallennus valmistellaan';

  @override
  String get clickTheButtonToCaptureAudio =>
      'Napsauta painiketta tallentaaksesi ääntä live-transkriptioita, AI-oivalluksia ja automaattista tallennusta varten.';

  @override
  String get reconnecting => 'Yhdistetään uudelleen...';

  @override
  String get recordingPaused => 'Tallennus keskeytetty';

  @override
  String get recordingActive => 'Tallennus aktiivinen';

  @override
  String get startRecording => 'Aloita tallennus';

  @override
  String resumingInCountdown(String countdown) {
    return 'Jatketaan ${countdown}s kuluttua...';
  }

  @override
  String get tapPlayToResume => 'Napauta toista jatkaaksesi';

  @override
  String get listeningForAudio => 'Kuunnellaan ääntä...';

  @override
  String get preparingAudioCapture => 'Äänitallennus valmistellaan';

  @override
  String get clickToBeginRecording => 'Napsauta aloittaaksesi tallennuksen';

  @override
  String get translated => 'käännetty';

  @override
  String get liveTranscript => 'Live-transkriptio';

  @override
  String segmentsSingular(String count) {
    return '$count segmentti';
  }

  @override
  String segmentsPlural(String count) {
    return '$count segmenttiä';
  }

  @override
  String get startRecordingToSeeTranscript => 'Aloita tallennus nähdäksesi live-transkription';

  @override
  String get paused => 'Keskeytetty';

  @override
  String get initializing => 'Alustetaan...';

  @override
  String get recording => 'Tallennetaan';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'Mikrofoni vaihdettu. Jatketaan ${countdown}s kuluttua';
  }

  @override
  String get clickPlayToResumeOrStop => 'Napsauta toista jatkaaksesi tai pysäytä lopettaaksesi';

  @override
  String get settingUpSystemAudioCapture => 'Järjestelmän äänitallennus asetuksissa';

  @override
  String get capturingAudioAndGeneratingTranscript => 'Tallennetaan ääntä ja luodaan transkriptiota';

  @override
  String get clickToBeginRecordingSystemAudio => 'Napsauta aloittaaksesi järjestelmän äänitallennus';

  @override
  String get you => 'Sinä';

  @override
  String speakerWithId(String speakerId) {
    return 'Puhuja $speakerId';
  }

  @override
  String get translatedByOmi => 'kääntänyt omi';

  @override
  String get backToConversations => 'Takaisin keskusteluihin';

  @override
  String get systemAudio => 'Järjestelmä';

  @override
  String get mic => 'Mikrofoni';

  @override
  String audioInputSetTo(String deviceName) {
    return 'Äänitulo asetettu: $deviceName';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'Virhe äänitulolaitteen vaihdossa: $error';
  }

  @override
  String get selectAudioInput => 'Valitse äänitulo';

  @override
  String get loadingDevices => 'Ladataan laitteita...';

  @override
  String get settingsHeader => 'ASETUKSET';

  @override
  String get plansAndBilling => 'Suunnitelmat ja Laskutus';

  @override
  String get calendarIntegration => 'Kalenterin Integraatio';

  @override
  String get dailySummary => 'Päivittäinen Yhteenveto';

  @override
  String get developer => 'Kehittäjä';

  @override
  String get about => 'Tietoja';

  @override
  String get selectTime => 'Valitse Aika';

  @override
  String get accountGroup => 'Tili';

  @override
  String get signOutQuestion => 'Kirjaudu Ulos?';

  @override
  String get signOutConfirmation => 'Haluatko varmasti kirjautua ulos?';

  @override
  String get customVocabularyHeader => 'MUKAUTETTU SANASTO';

  @override
  String get addWordsDescription => 'Lisää sanoja, jotka Omin tulisi tunnistaa transkription aikana.';

  @override
  String get enterWordsHint => 'Syötä sanat (pilkulla eroteltuina)';

  @override
  String get dailySummaryHeader => 'PÄIVITTÄINEN YHTEENVETO';

  @override
  String get dailySummaryTitle => 'Päivittäinen Yhteenveto';

  @override
  String get dailySummaryDescription => 'Saa henkilökohtainen yhteenveto keskusteluistasi';

  @override
  String get deliveryTime => 'Toimitusaika';

  @override
  String get deliveryTimeDescription => 'Milloin vastaanottaa päivittäinen yhteenveto';

  @override
  String get subscription => 'Tilaus';

  @override
  String get viewPlansAndUsage => 'Näytä Suunnitelmat ja Käyttö';

  @override
  String get viewPlansDescription => 'Hallitse tilaustasi ja katso käyttötilastoja';

  @override
  String get addOrChangePaymentMethod => 'Lisää tai vaihda maksutapa';

  @override
  String get displayOptions => 'Näyttövaihtoehdot';

  @override
  String get showMeetingsInMenuBar => 'Näytä kokoukset valikkorivissä';

  @override
  String get displayUpcomingMeetingsDescription => 'Näytä tulevat kokoukset valikkorivissä';

  @override
  String get showEventsWithoutParticipants => 'Näytä tapahtumat ilman osallistujia';

  @override
  String get includePersonalEventsDescription => 'Sisällytä henkilökohtaiset tapahtumat ilman osallistujia';

  @override
  String get upcomingMeetings => 'TULEVAT KOKOUKSET';

  @override
  String get checkingNext7Days => 'Tarkistetaan seuraavat 7 päivää';

  @override
  String get shortcuts => 'Pikanäppäimet';

  @override
  String get shortcutChangeInstruction => 'Napsauta pikanäppäintä muuttaaksesi sitä. Peruuta painamalla Escape.';

  @override
  String get configurePersonaDescription => 'Määritä AI-persoonasi';

  @override
  String get configureSTTProvider => 'Määritä STT-palveluntarjoaja';

  @override
  String get setConversationEndDescription => 'Aseta, milloin keskustelut päättyvät automaattisesti';

  @override
  String get importDataDescription => 'Tuo tietoja muista lähteistä';

  @override
  String get exportConversationsDescription => 'Vie keskustelut JSON-muotoon';

  @override
  String get exportingConversations => 'Viedään keskusteluja...';

  @override
  String get clearNodesDescription => 'Tyhjennä kaikki solmut ja yhteydet';

  @override
  String get deleteKnowledgeGraphQuestion => 'Poistetaanko tietograafi?';

  @override
  String get deleteKnowledgeGraphWarning =>
      'Tämä poistaa kaikki johdetut tietograafitiedot. Alkuperäiset muistosi pysyvät turvassa.';

  @override
  String get connectOmiWithAI => 'Yhdistä Omi AI-avustajiin';

  @override
  String get noAPIKeys => 'Ei API-avaimia. Luo yksi aloittaaksesi.';

  @override
  String get autoCreateWhenDetected => 'Luo automaattisesti, kun nimi havaitaan';

  @override
  String get trackPersonalGoals => 'Seuraa henkilökohtaisia tavoitteita etusivulla';

  @override
  String get dailyReflectionDescription => 'Klo 21 muistutus päivän pohdintaan';

  @override
  String get endpointURL => 'Päätepisteen URL';

  @override
  String get links => 'Linkit';

  @override
  String get discordMemberCount => 'Yli 8000 jäsentä Discordissa';

  @override
  String get userInformation => 'Käyttäjätiedot';

  @override
  String get capabilities => 'Ominaisuudet';

  @override
  String get previewScreenshots => 'Kuvakaappausten esikatselu';

  @override
  String get holdOnPreparingForm => 'Odota hetki, valmistelemme lomaketta sinulle';

  @override
  String get bySubmittingYouAgreeToOmi => 'Lähettämällä hyväksyt Omin ';

  @override
  String get termsAndPrivacyPolicy => 'Ehdot ja Tietosuojakäytäntö';

  @override
  String get helpsDiagnoseIssuesAutoDeletes =>
      'Auttaa ongelmien diagnosoinnissa. Poistetaan automaattisesti 3 päivän kuluttua.';

  @override
  String get manageYourApp => 'Hallinnoi sovellustasi';

  @override
  String get updatingYourApp => 'Päivitetään sovellustasi';

  @override
  String get fetchingYourAppDetails => 'Haetaan sovelluksen tietoja';

  @override
  String get updateAppQuestion => 'Päivitä sovellus?';

  @override
  String get updateAppConfirmation =>
      'Haluatko varmasti päivittää sovelluksesi? Muutokset näkyvät tiimimme tarkistuksen jälkeen.';

  @override
  String get updateApp => 'Päivitä sovellus';

  @override
  String get createAndSubmitNewApp => 'Luo ja lähetä uusi sovellus';

  @override
  String appsCount(String count) {
    return 'Sovellukset ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'Yksityiset sovellukset ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'Julkiset sovellukset ($count)';
  }

  @override
  String get newVersionAvailable => 'Uusi versio saatavilla  🎉';

  @override
  String get no => 'Ei';

  @override
  String get subscriptionCancelledSuccessfully =>
      'Tilaus peruutettu onnistuneesti. Se pysyy aktiivisena nykyisen laskutuskauden loppuun.';

  @override
  String get failedToCancelSubscription => 'Tilauksen peruuttaminen epäonnistui. Yritä uudelleen.';

  @override
  String get invalidPaymentUrl => 'Virheellinen maksu-URL';

  @override
  String get permissionsAndTriggers => 'Käyttöoikeudet ja laukaisimet';

  @override
  String get chatFeatures => 'Chat-ominaisuudet';

  @override
  String get uninstall => 'Poista asennus';

  @override
  String get installs => 'ASENNUKSET';

  @override
  String get priceLabel => 'HINTA';

  @override
  String get updatedLabel => 'PÄIVITETTY';

  @override
  String get createdLabel => 'LUOTU';

  @override
  String get featuredLabel => 'ESITELTY';

  @override
  String get cancelSubscriptionQuestion => 'Peruuta tilaus?';

  @override
  String get cancelSubscriptionConfirmation =>
      'Haluatko varmasti peruuttaa tilauksesi? Sinulla on edelleen pääsy nykyisen laskutuskauden loppuun.';

  @override
  String get cancelSubscriptionButton => 'Peruuta tilaus';

  @override
  String get cancelling => 'Peruutetaan...';

  @override
  String get betaTesterMessage =>
      'Olet tämän sovelluksen beta-testaaja. Se ei ole vielä julkinen. Se julkaistaan hyväksynnän jälkeen.';

  @override
  String get appUnderReviewMessage =>
      'Sovelluksesi on tarkistettavana ja näkyy vain sinulle. Se julkaistaan hyväksynnän jälkeen.';

  @override
  String get appRejectedMessage => 'Sovelluksesi on hylätty. Päivitä tiedot ja lähetä uudelleen tarkistettavaksi.';

  @override
  String get invalidIntegrationUrl => 'Virheellinen integraatio-URL';

  @override
  String get tapToComplete => 'Napauta viimeistelläksesi';

  @override
  String get invalidSetupInstructionsUrl => 'Virheellinen asennusohjeiden URL';

  @override
  String get pushToTalk => 'Paina puhuaksesi';

  @override
  String get summaryPrompt => 'Yhteenvetokehote';

  @override
  String get pleaseSelectARating => 'Valitse arvosana';

  @override
  String get reviewAddedSuccessfully => 'Arvostelu lisätty onnistuneesti 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'Arvostelu päivitetty onnistuneesti 🚀';

  @override
  String get failedToSubmitReview => 'Arvostelun lähettäminen epäonnistui. Yritä uudelleen.';

  @override
  String get addYourReview => 'Lisää arvostelusi';

  @override
  String get editYourReview => 'Muokkaa arvostelua';

  @override
  String get writeAReviewOptional => 'Kirjoita arvostelu (valinnainen)';

  @override
  String get submitReview => 'Lähetä arvostelu';

  @override
  String get updateReview => 'Päivitä arvostelu';

  @override
  String get yourReview => 'Arvostelusi';

  @override
  String get anonymousUser => 'Anonyymi käyttäjä';

  @override
  String get issueActivatingApp => 'Sovelluksen aktivoinnissa ilmeni ongelma. Yritä uudelleen.';

  @override
  String get dataAccessNoticeDescription =>
      'This app will access your data. Omi AI is not responsible for how your data is used, modified, or deleted by this app';

  @override
  String get copyUrl => 'Kopioi URL';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => 'Ma';

  @override
  String get weekdayTue => 'Ti';

  @override
  String get weekdayWed => 'Ke';

  @override
  String get weekdayThu => 'To';

  @override
  String get weekdayFri => 'Pe';

  @override
  String get weekdaySat => 'La';

  @override
  String get weekdaySun => 'Su';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return '$serviceName-integraatio tulossa pian';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'Jo viety kohteeseen $platform';
  }

  @override
  String get anotherPlatform => 'toiseen alustaan';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'Ole hyvä ja kirjaudu $serviceName palveluun kohdassa Asetukset > Tehtäväintegraatiot';
  }

  @override
  String addingToService(String serviceName) {
    return 'Lisätään kohteeseen $serviceName...';
  }

  @override
  String addedToService(String serviceName) {
    return 'Lisätty kohteeseen $serviceName';
  }

  @override
  String failedToAddToService(String serviceName) {
    return 'Lisääminen kohteeseen $serviceName epäonnistui';
  }

  @override
  String get permissionDeniedForAppleReminders => 'Käyttöoikeus Apple Muistutuksille evätty';

  @override
  String failedToCreateApiKey(String error) {
    return 'Palveluntarjoajan API-avaimen luominen epäonnistui: $error';
  }

  @override
  String get createAKey => 'Luo avain';

  @override
  String get apiKeyRevokedSuccessfully => 'API-avain peruutettu onnistuneesti';

  @override
  String failedToRevokeApiKey(String error) {
    return 'API-avaimen peruuttaminen epäonnistui: $error';
  }

  @override
  String get omiApiKeys => 'Omi API-avaimet';

  @override
  String get apiKeysDescription =>
      'API-avaimia käytetään todentamiseen, kun sovelluksesi kommunikoi OMI-palvelimen kanssa. Ne mahdollistavat sovelluksesi luoda muistoja ja käyttää muita OMI-palveluita turvallisesti.';

  @override
  String get aboutOmiApiKeys => 'Tietoja Omi API-avaimista';

  @override
  String get yourNewKey => 'Uusi avaimesi:';

  @override
  String get copyToClipboard => 'Kopioi leikepöydälle';

  @override
  String get pleaseCopyKeyNow => 'Ole hyvä ja kopioi se nyt ja kirjoita se turvalliseen paikkaan. ';

  @override
  String get willNotSeeAgain => 'Et voi nähdä sitä uudelleen.';

  @override
  String get revokeKey => 'Peruuta avain';

  @override
  String get revokeApiKeyQuestion => 'Peruuta API-avain?';

  @override
  String get revokeApiKeyWarning =>
      'Tätä toimintoa ei voi kumota. Tätä avainta käyttävät sovellukset eivät enää pääse API:in.';

  @override
  String get revoke => 'Peruuta';

  @override
  String get whatWouldYouLikeToCreate => 'Mitä haluaisit luoda?';

  @override
  String get createAnApp => 'Luo sovellus';

  @override
  String get createAndShareYourApp => 'Luo ja jaa sovelluksesi';

  @override
  String get createMyClone => 'Luo kloonini';

  @override
  String get createYourDigitalClone => 'Luo digitaalinen kloonisi';

  @override
  String get itemApp => 'Sovellus';

  @override
  String get itemPersona => 'Persona';

  @override
  String keepItemPublic(String item) {
    return 'Pidä $item julkisena';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return 'Tee $item julkiseksi?';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return 'Tee $item yksityiseksi?';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'Jos teet $item julkiseksi, kaikki voivat käyttää sitä';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'Jos teet $item nyt yksityiseksi, se lakkaa toimimasta kaikille ja on näkyvissä vain sinulle';
  }

  @override
  String get manageApp => 'Hallitse sovellusta';

  @override
  String get updatePersonaDetails => 'Päivitä persona-tiedot';

  @override
  String deleteItemTitle(String item) {
    return 'Poista $item';
  }

  @override
  String deleteItemQuestion(String item) {
    return 'Poista $item?';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'Haluatko varmasti poistaa tämän $item? Tätä toimintoa ei voi kumota.';
  }

  @override
  String get revokeKeyQuestion => 'Peruuta avain?';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'Haluatko varmasti peruuttaa avaimen \"$keyName\"? Tätä toimintoa ei voi kumota.';
  }

  @override
  String get createNewKey => 'Luo uusi avain';

  @override
  String get keyNameHint => 'esim. Claude Desktop';

  @override
  String get pleaseEnterAName => 'Anna nimi.';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'Avaimen luominen epäonnistui: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'Avaimen luominen epäonnistui. Yritä uudelleen.';

  @override
  String get keyCreated => 'Avain luotu';

  @override
  String get keyCreatedMessage => 'Uusi avaimesi on luotu. Kopioi se nyt. Et näe sitä enää uudelleen.';

  @override
  String get keyWord => 'Avain';

  @override
  String get externalAppAccess => 'Ulkoisten sovellusten käyttöoikeus';

  @override
  String get externalAppAccessDescription =>
      'Seuraavilla asennetuilla sovelluksilla on ulkoisia integraatioita ja ne voivat käyttää tietojasi, kuten keskusteluja ja muistoja.';

  @override
  String get noExternalAppsHaveAccess => 'Ulkoisilla sovelluksilla ei ole pääsyä tietoihisi.';

  @override
  String get maximumSecurityE2ee => 'Maksimaalinen turvallisuus (E2EE)';

  @override
  String get e2eeDescription =>
      'Päästä päähän -salaus on yksityisyyden kultastandardi. Kun se on käytössä, tietosi salataan laitteellasi ennen kuin ne lähetetään palvelimillemme. Tämä tarkoittaa, että kukaan, ei edes Omi, pääse käsiksi sisältöösi.';

  @override
  String get importantTradeoffs => 'Tärkeät kompromissit:';

  @override
  String get e2eeTradeoff1 =>
      '• Jotkin ominaisuudet, kuten ulkoisten sovellusten integraatiot, voivat olla pois käytöstä.';

  @override
  String get e2eeTradeoff2 => '• Jos kadotat salasanasi, tietojasi ei voi palauttaa.';

  @override
  String get featureComingSoon => 'Tämä ominaisuus on tulossa pian!';

  @override
  String get migrationInProgressMessage => 'Siirto käynnissä. Et voi muuttaa suojaustasoa ennen kuin se on valmis.';

  @override
  String get migrationFailed => 'Siirto epäonnistui';

  @override
  String migratingFromTo(String source, String target) {
    return 'Siirretään kohteesta $source kohteeseen $target';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total objektia';
  }

  @override
  String get secureEncryption => 'Turvallinen salaus';

  @override
  String get secureEncryptionDescription =>
      'Tietosi salataan sinulle yksilöllisellä avaimella palvelimillamme, jotka ovat Google Cloudissa. Tämä tarkoittaa, että raakatietosi eivät ole kenenkään, mukaan lukien Omin henkilöstön tai Googlen, saatavilla suoraan tietokannasta.';

  @override
  String get endToEndEncryption => 'Päästä päähän -salaus';

  @override
  String get e2eeCardDescription =>
      'Ota käyttöön maksimaalinen turvallisuus, jossa vain sinä pääset käsiksi tietoihisi. Napauta saadaksesi lisätietoja.';

  @override
  String get dataAlwaysEncrypted => 'Tasosta riippumatta tietosi ovat aina salattuja levossa ja siirrettäessä.';

  @override
  String get readOnlyScope => 'Vain luku';

  @override
  String get fullAccessScope => 'Täysi pääsy';

  @override
  String get readScope => 'Luku';

  @override
  String get writeScope => 'Kirjoitus';

  @override
  String get apiKeyCreated => 'API-avain luotu!';

  @override
  String get saveKeyWarning => 'Tallenna tämä avain nyt! Et näe sitä enää uudelleen.';

  @override
  String get yourApiKey => 'API-AVAIMESI';

  @override
  String get tapToCopy => 'Kopioi napauttamalla';

  @override
  String get copyKey => 'Kopioi avain';

  @override
  String get createApiKey => 'Luo API-avain';

  @override
  String get accessDataProgrammatically => 'Käytä tietojasi ohjelmallisesti';

  @override
  String get keyNameLabel => 'AVAIMEN NIMI';

  @override
  String get keyNamePlaceholder => 'esim. Oma sovellus';

  @override
  String get permissionsLabel => 'OIKEUDET';

  @override
  String get permissionsInfoNote => 'R = Luku, W = Kirjoitus. Oletuksena vain luku, jos mitään ei ole valittu.';

  @override
  String get developerApi => 'Kehittäjän API';

  @override
  String get createAKeyToGetStarted => 'Luo avain aloittaaksesi';

  @override
  String errorWithMessage(String error) {
    return 'Virhe: $error';
  }

  @override
  String get omiTraining => 'Omi-koulutus';

  @override
  String get trainingDataProgram => 'Koulutustietojen ohjelma';

  @override
  String get getOmiUnlimitedFree =>
      'Saat Omi Unlimited -tilauksen ilmaiseksi antamalla tietosi AI-mallien kouluttamiseen.';

  @override
  String get trainingDataBullets =>
      '• Tietosi auttavat parantamaan AI-malleja\n• Vain ei-arkaluonteiset tiedot jaetaan\n• Täysin läpinäkyvä prosessi';

  @override
  String get learnMoreAtOmiTraining => 'Lue lisää osoitteessa omi.me/training';

  @override
  String get agreeToContributeData => 'Ymmärrän ja suostun antamaan tietoni AI:n kouluttamiseen';

  @override
  String get submitRequest => 'Lähetä pyyntö';

  @override
  String get thankYouRequestUnderReview =>
      'Kiitos! Pyyntösi on tarkistettavana. Ilmoitamme sinulle hyväksynnän jälkeen.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'Tilauksesi pysyy aktiivisena $date asti. Sen jälkeen menetät pääsyn rajoittamattomiin ominaisuuksiin. Oletko varma?';
  }

  @override
  String get confirmCancellation => 'Vahvista peruutus';

  @override
  String get keepMyPlan => 'Säilytä tilaukseni';

  @override
  String get subscriptionSetToCancel => 'Tilauksesi on asetettu peruuntumaan jakson lopussa.';

  @override
  String get switchedToOnDevice => 'Vaihdettu laitteen transkriptioon';

  @override
  String get couldNotSwitchToFreePlan => 'Ilmaiseen tilaukseen vaihtaminen epäonnistui. Yritä uudelleen.';

  @override
  String get couldNotLoadPlans => 'Saatavilla olevia tilauksia ei voitu ladata. Yritä uudelleen.';

  @override
  String get selectedPlanNotAvailable => 'Valittu tilaus ei ole saatavilla. Yritä uudelleen.';

  @override
  String get upgradeToAnnualPlan => 'Päivitä vuositilaukseen';

  @override
  String get importantBillingInfo => 'Tärkeää laskutustietoa:';

  @override
  String get monthlyPlanContinues => 'Nykyinen kuukausitilauksesi jatkuu laskutusjakson loppuun asti';

  @override
  String get paymentMethodCharged => 'Nykyinen maksutapasi veloitetaan automaattisesti kuukausitilauksesi päättyessä';

  @override
  String get annualSubscriptionStarts => '12 kuukauden vuositilauksesi alkaa automaattisesti veloituksen jälkeen';

  @override
  String get thirteenMonthsCoverage =>
      'Saat yhteensä 13 kuukauden kattavuuden (nykyinen kuukausi + 12 kuukautta vuosittain)';

  @override
  String get confirmUpgrade => 'Vahvista päivitys';

  @override
  String get confirmPlanChange => 'Vahvista tilauksen muutos';

  @override
  String get confirmAndProceed => 'Vahvista ja jatka';

  @override
  String get upgradeScheduled => 'Päivitys ajoitettu';

  @override
  String get changePlan => 'Vaihda tilausta';

  @override
  String get upgradeAlreadyScheduled => 'Päivityksesi vuositilaukseen on jo ajoitettu';

  @override
  String get youAreOnUnlimitedPlan => 'Sinulla on Rajoittamaton tilaus.';

  @override
  String get yourOmiUnleashed => 'Omi vapaana. Siirry rajoittamattomaan loputtomien mahdollisuuksien saavuttamiseksi.';

  @override
  String planEndedOn(String date) {
    return 'Tilauksesi päättyi $date.\\nTilaa uudelleen nyt - sinulta veloitetaan välittömästi uudesta laskutusjaksosta.';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'Tilauksesi on asetettu peruuntumaan $date.\\nTilaa uudelleen nyt säilyttääksesi edut - ei veloitusta ennen $date.';
  }

  @override
  String get annualPlanStartsAutomatically => 'Vuositilauksesi alkaa automaattisesti, kun kuukausitilauksesi päättyy.';

  @override
  String planRenewsOn(String date) {
    return 'Tilauksesi uusitaan $date.';
  }

  @override
  String get unlimitedConversations => 'Rajoittamattomat keskustelut';

  @override
  String get askOmiAnything => 'Kysy Omilta mitä tahansa elämästäsi';

  @override
  String get unlockOmiInfiniteMemory => 'Avaa Omin rajaton muisti';

  @override
  String get youreOnAnnualPlan => 'Sinulla on vuositilaus';

  @override
  String get alreadyBestValuePlan => 'Sinulla on jo paras hinta-laatusuhteen tilaus. Muutoksia ei tarvita.';

  @override
  String get unableToLoadPlans => 'Tilauksia ei voida ladata';

  @override
  String get checkConnectionTryAgain => 'Tarkista yhteytesi ja yritä uudelleen';

  @override
  String get useFreePlan => 'Käytä ilmaista tilausta';

  @override
  String get continueText => 'Jatka';

  @override
  String get resubscribe => 'Tilaa uudelleen';

  @override
  String get couldNotOpenPaymentSettings => 'Maksuasetuksia ei voitu avata. Yritä uudelleen.';

  @override
  String get managePaymentMethod => 'Hallitse maksutapaa';

  @override
  String get cancelSubscription => 'Peruuta tilaus';

  @override
  String endsOnDate(String date) {
    return 'Päättyy $date';
  }

  @override
  String get active => 'Aktiivinen';

  @override
  String get freePlan => 'Ilmainen tilaus';

  @override
  String get configure => 'Määritä';

  @override
  String get privacyInformation => 'Tietosuojatiedot';

  @override
  String get yourPrivacyMattersToUs => 'Yksityisyytesi on meille tärkeä';

  @override
  String get privacyIntroText =>
      'Omissa otamme yksityisyytesi erittäin vakavasti. Haluamme olla läpinäkyviä keräämistämme tiedoista ja niiden käytöstä. Tässä on mitä sinun tulee tietää:';

  @override
  String get whatWeTrack => 'Mitä seuraamme';

  @override
  String get anonymityAndPrivacy => 'Nimettömyys ja yksityisyys';

  @override
  String get optInAndOptOutOptions => 'Suostumis- ja kieltäytymisvaihtoehdot';

  @override
  String get ourCommitment => 'Sitoumuksemme';

  @override
  String get commitmentText =>
      'Olemme sitoutuneet käyttämään keräämiämme tietoja vain Omin parantamiseen sinulle. Yksityisyytesi ja luottamuksesi ovat meille ensiarvoisen tärkeitä.';

  @override
  String get thankYouText =>
      'Kiitos, että olet arvokas Omin käyttäjä. Jos sinulla on kysyttävää tai huolenaiheita, ota rohkeasti yhteyttä osoitteeseen team@basedhardware.com.';

  @override
  String get wifiSyncSettings => 'WiFi-synkronointiasetukset';

  @override
  String get enterHotspotCredentials => 'Syötä puhelimesi hotspot-tunnukset';

  @override
  String get wifiSyncUsesHotspot =>
      'WiFi-synkronointi käyttää puhelintasi hotspotina. Löydä nimi ja salasana kohdasta Asetukset > Oma hotspot.';

  @override
  String get hotspotNameSsid => 'Hotspotin nimi (SSID)';

  @override
  String get exampleIphoneHotspot => 'esim. iPhone Hotspot';

  @override
  String get password => 'Salasana';

  @override
  String get enterHotspotPassword => 'Syötä hotspotin salasana';

  @override
  String get saveCredentials => 'Tallenna tunnukset';

  @override
  String get clearCredentials => 'Tyhjennä tunnukset';

  @override
  String get pleaseEnterHotspotName => 'Syötä hotspotin nimi';

  @override
  String get wifiCredentialsSaved => 'WiFi-tunnukset tallennettu';

  @override
  String get wifiCredentialsCleared => 'WiFi-tunnukset tyhjennetty';

  @override
  String summaryGeneratedForDate(String date) {
    return 'Yhteenveto luotu päivälle $date';
  }

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'Yhteenvedon luominen epäonnistui. Varmista, että sinulla on keskusteluja kyseiseltä päivältä.';

  @override
  String get summaryNotFound => 'Yhteenvetoa ei löytynyt';

  @override
  String get yourDaysJourney => 'Päiväsi matka';

  @override
  String get highlights => 'Kohokohdat';

  @override
  String get unresolvedQuestions => 'Ratkaisemattomat kysymykset';

  @override
  String get decisions => 'Päätökset';

  @override
  String get learnings => 'Opit';

  @override
  String get autoDeletesAfterThreeDays => 'Poistetaan automaattisesti 3 päivän kuluttua.';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'Tietograafi poistettu onnistuneesti';

  @override
  String get exportStartedMayTakeFewSeconds => 'Vienti aloitettu. Tämä voi kestää muutaman sekunnin...';

  @override
  String get knowledgeGraphDeleteDescription =>
      'Tämä poistaa kaikki johdetut tietograafin tiedot (solmut ja yhteydet). Alkuperäiset muistosi säilyvät turvassa. Graafi rakennetaan uudelleen ajan myötä tai seuraavan pyynnön yhteydessä.';

  @override
  String get configureDailySummaryDigest => 'Määritä päivittäinen tehtäväyhteenveto';
}
