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
  String get copySummary => 'Kopioi tiivistelmä';

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
  String get clearChat => 'Tyhjennä keskustelu';

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
  String get offlineSync => 'Offline Sync';

  @override
  String get deviceSettings => 'Laitteen asetukset';

  @override
  String get integrations => 'Integraatiot';

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
  String get wrapped2025 => 'Katsaus 2025';

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
  String get intervalSeconds => 'Aikaväli (sekuntia)';

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
  String get connect => 'Connect';

  @override
  String get comingSoon => 'Tulossa pian';

  @override
  String get integrationsFooter => 'Yhdistä sovelluksesi nähdäksesi tiedot ja mittarit chatissa.';

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
  String get noUpcomingMeetings => 'Ei tulevia tapaamisia';

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
  String deviceUsesCodec(String device, String reason) {
    return '$device käyttää $reason. Käytetään Omi.';
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
  String get appName => 'App Name';

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
  String get speechProfileIntro => 'Omin täytyy oppia tavoitteesi ja äänesi. Voit muokata sitä myöhemmin.';

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
  String get retry => 'Retry';

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
  String get descriptionOptional => 'Description (optional)';

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
  String get unknownDevice => 'Unknown';

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
    return '$label kopioitu';
  }

  @override
  String get noApiKeysYet => 'Ei vielä API-avaimia. Luo yksi integroidaksesi sovelluksesi kanssa.';

  @override
  String get createKeyToGetStarted => 'Luo avain aloittaaksesi';

  @override
  String get persona => 'Persona';

  @override
  String get configureYourAiPersona => 'Määritä AI-persoonasi';

  @override
  String get configureSttProvider => 'Määritä STT-palveluntarjoaja';

  @override
  String get setWhenConversationsAutoEnd => 'Aseta milloin keskustelut päättyvät automaattisesti';

  @override
  String get importDataFromOtherSources => 'Tuo tietoja muista lähteistä';

  @override
  String get debugAndDiagnostics => 'Virheenkorjaus ja diagnostiikka';

  @override
  String get autoDeletesAfter3Days => 'Poistetaan automaattisesti 3 päivän kuluttua';

  @override
  String get helpsDiagnoseIssues => 'Auttaa ongelmien diagnosoinnissa';

  @override
  String get exportStartedMessage => 'Vienti aloitettu. Tämä voi kestää muutaman sekunnin...';

  @override
  String get exportConversationsToJson => 'Vie keskustelut JSON-tiedostoon';

  @override
  String get knowledgeGraphDeletedSuccess => 'Tietograafi poistettu onnistuneesti';

  @override
  String failedToDeleteGraph(String error) {
    return 'Graafin poistaminen epäonnistui: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'Tyhjennä kaikki solmut ja yhteydet';

  @override
  String get addToClaudeDesktopConfig => 'Lisää claude_desktop_config.json-tiedostoon';

  @override
  String get connectAiAssistantsToData => 'Yhdistä AI-avustajat tietoihisi';

  @override
  String get useYourMcpApiKey => 'Käytä MCP API -avaintasi';

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
  String get autoCreateWhenNameDetected => 'Luo automaattisesti kun nimi havaitaan';

  @override
  String get followUpQuestions => 'Jatkokysymykset';

  @override
  String get suggestQuestionsAfterConversations => 'Ehdota kysymyksiä keskustelujen jälkeen';

  @override
  String get goalTracker => 'Tavoitteiden seuranta';

  @override
  String get trackPersonalGoalsOnHomepage => 'Seuraa henkilökohtaisia tavoitteitasi etusivulla';

  @override
  String get dailyReflection => 'Päivittäinen reflektio';

  @override
  String get get9PmReminderToReflect => 'Saa muistutus klo 21 päiväsi pohtimiseen';

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
  String get dailyScore => 'PÄIVITTÄINEN PISTEMÄÄRÄ';

  @override
  String get dailyScoreDescription => 'Pistemäärä, joka auttaa sinua\nkeskittymään paremmin suorittamiseen.';

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
  String get all => 'All';

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
  String get installsCount => 'Asennukset';

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
  String get setupInstructions => 'Asetusohjeet';

  @override
  String get integrationInstructions => 'Integrointiohjeet';

  @override
  String get preview => 'Esikatselu';

  @override
  String get aboutTheApp => 'Tietoja sovelluksesta';

  @override
  String get aboutThePersona => 'Tietoja persoonasta';

  @override
  String get chatPersonality => 'Chat-persoonallisuus';

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
  String get takePhoto => 'Ota kuva';

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
      'Tälle sovellukselle ei ole tiivistelmää. Kokeile toista sovellusta parempien tulosten saamiseksi.';

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
  String get dailySummary => 'Päivittäinen yhteenveto';

  @override
  String get developer => 'Kehittäjä';

  @override
  String get about => 'Tietoja';

  @override
  String get selectTime => 'Valitse aika';

  @override
  String get accountGroup => 'Tili';

  @override
  String get signOutQuestion => 'Kirjaudu ulos?';

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
  String get dailySummaryDescription => 'Saa henkilökohtainen yhteenveto päivän keskusteluista ilmoituksena.';

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
  String get upcomingMeetings => 'Tulevat tapaamiset';

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
  String get dailyReflectionDescription =>
      'Saa muistutus klo 21 reflektoidaksesi päivääsi ja tallentaaksesi ajatuksesi.';

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
  String get invalidSetupInstructionsUrl => 'Virheellinen asetusohjeiden URL';

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
      'Tämä sovellus käyttää tietojasi. Omi AI ei ole vastuussa siitä, miten tietojasi käytetään, muokataan tai poistetaan tässä sovelluksessa';

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

  @override
  String accessesDataTypes(String dataTypes) {
    return 'Käyttää: $dataTypes';
  }

  @override
  String triggeredByType(String triggerType) {
    return 'laukaisee $triggerType';
  }

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription ja on $triggerDescription.';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return 'On $triggerDescription.';
  }

  @override
  String get noSpecificDataAccessConfigured => 'Ei määritettyä tietojen käyttöoikeutta.';

  @override
  String get basicPlanDescription => '1 200 premium-minuuttia + rajoittamaton laitteella';

  @override
  String get minutes => 'minuuttia';

  @override
  String get omiHas => 'Omilla on:';

  @override
  String get premiumMinutesUsed => 'Premium-minuutit käytetty.';

  @override
  String get setupOnDevice => 'Määritä laitteella';

  @override
  String get forUnlimitedFreeTranscription => 'rajattomaan ilmaiseen litterointiin.';

  @override
  String premiumMinsLeft(int count) {
    return '$count premium-minuuttia jäljellä.';
  }

  @override
  String get alwaysAvailable => 'aina käytettävissä.';

  @override
  String get importHistory => 'Tuontihistoria';

  @override
  String get noImportsYet => 'Ei tuonteja vielä';

  @override
  String get selectZipFileToImport => 'Valitse tuotava .zip-tiedosto!';

  @override
  String get otherDevicesComingSoon => 'Muut laitteet tulossa pian';

  @override
  String get deleteAllLimitlessConversations => 'Poista kaikki Limitless-keskustelut?';

  @override
  String get deleteAllLimitlessWarning =>
      'Tämä poistaa pysyvästi kaikki Limitlessistä tuodut keskustelut. Tätä toimintoa ei voi kumota.';

  @override
  String deletedLimitlessConversations(int count) {
    return 'Poistettu $count Limitless-keskustelua';
  }

  @override
  String get failedToDeleteConversations => 'Keskustelujen poistaminen epäonnistui';

  @override
  String get deleteImportedData => 'Poista tuodut tiedot';

  @override
  String get statusPending => 'Odottaa';

  @override
  String get statusProcessing => 'Käsitellään';

  @override
  String get statusCompleted => 'Valmis';

  @override
  String get statusFailed => 'Epäonnistui';

  @override
  String nConversations(int count) {
    return '$count keskustelua';
  }

  @override
  String get pleaseEnterName => 'Anna nimi';

  @override
  String get nameMustBeBetweenCharacters => 'Nimen on oltava 2-40 merkkiä';

  @override
  String get deleteSampleQuestion => 'Poista näyte?';

  @override
  String deleteSampleConfirmation(String name) {
    return 'Haluatko varmasti poistaa käyttäjän $name näytteen?';
  }

  @override
  String get confirmDeletion => 'Vahvista poisto';

  @override
  String deletePersonConfirmation(String name) {
    return 'Haluatko varmasti poistaa käyttäjän $name? Tämä poistaa myös kaikki liittyvät puhenäytteet.';
  }

  @override
  String get howItWorksTitle => 'Miten se toimii?';

  @override
  String get howPeopleWorks =>
      'Kun henkilö on luotu, voit mennä keskustelun transkriptioon ja määrittää heille vastaavat segmentit, näin Omi voi tunnistaa myös heidän puheensa!';

  @override
  String get tapToDelete => 'Napauta poistaaksesi';

  @override
  String get newTag => 'UUSI';

  @override
  String get needHelpChatWithUs => 'Tarvitsetko apua? Keskustele kanssamme';

  @override
  String get localStorageEnabled => 'Paikallinen tallennustila käytössä';

  @override
  String get localStorageDisabled => 'Paikallinen tallennustila pois käytöstä';

  @override
  String failedToUpdateSettings(String error) {
    return 'Asetusten päivitys epäonnistui: $error';
  }

  @override
  String get privacyNotice => 'Tietosuojailmoitus';

  @override
  String get recordingsMayCaptureOthers =>
      'Tallenteet voivat tallentaa muiden ääniä. Varmista, että sinulla on kaikkien osallistujien suostumus ennen käyttöönottoa.';

  @override
  String get enable => 'Ota käyttöön';

  @override
  String get storeAudioOnPhone => 'Tallenna ääni puhelimeen';

  @override
  String get on => 'On';

  @override
  String get storeAudioDescription =>
      'Säilytä kaikki äänitallenteet paikallisesti puhelimessasi. Kun pois käytöstä, vain epäonnistuneet lataukset säilytetään tallennustilan säästämiseksi.';

  @override
  String get enableLocalStorage => 'Ota paikallinen tallennustila käyttöön';

  @override
  String get cloudStorageEnabled => 'Pilvitallennustila käytössä';

  @override
  String get cloudStorageDisabled => 'Pilvitallennustila pois käytöstä';

  @override
  String get enableCloudStorage => 'Ota pilvitallennustila käyttöön';

  @override
  String get storeAudioOnCloud => 'Tallenna ääni pilveen';

  @override
  String get cloudStorageDialogMessage =>
      'Reaaliaikaiset tallenteet tallennetaan yksityiseen pilvitallennustilaan puhuessasi.';

  @override
  String get storeAudioCloudDescription =>
      'Tallenna reaaliaikaiset tallenteet yksityiseen pilvitallennustilaan puhuessasi. Ääni tallennetaan turvallisesti reaaliajassa.';

  @override
  String get downloadingFirmware => 'Ladataan laiteohjelmistoa';

  @override
  String get installingFirmware => 'Asennetaan laiteohjelmistoa';

  @override
  String get firmwareUpdateWarning => 'Älä sulje sovellusta tai sammuta laitetta. Tämä voi vaurioittaa laitettasi.';

  @override
  String get firmwareUpdated => 'Laiteohjelmisto päivitetty';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'Käynnistä $deviceName uudelleen päivityksen viimeistelemiseksi.';
  }

  @override
  String get yourDeviceIsUpToDate => 'Laitteesi on ajan tasalla';

  @override
  String get currentVersion => 'Nykyinen versio';

  @override
  String get latestVersion => 'Uusin versio';

  @override
  String get whatsNew => 'Uutta';

  @override
  String get installUpdate => 'Asenna päivitys';

  @override
  String get updateNow => 'Päivitä nyt';

  @override
  String get updateGuide => 'Päivitysopas';

  @override
  String get checkingForUpdates => 'Tarkistetaan päivityksiä';

  @override
  String get checkingFirmwareVersion => 'Tarkistetaan laiteohjelmiston versiota...';

  @override
  String get firmwareUpdate => 'Laiteohjelmistopäivitys';

  @override
  String get payments => 'Maksut';

  @override
  String get connectPaymentMethodInfo =>
      'Yhdistä maksutapa alla aloittaaksesi maksujen vastaanottamisen sovelluksistasi.';

  @override
  String get selectedPaymentMethod => 'Valittu maksutapa';

  @override
  String get availablePaymentMethods => 'Käytettävissä olevat maksutavat';

  @override
  String get activeStatus => 'Aktiivinen';

  @override
  String get connectedStatus => 'Yhdistetty';

  @override
  String get notConnectedStatus => 'Ei yhdistetty';

  @override
  String get setActive => 'Aseta aktiiviseksi';

  @override
  String get getPaidThroughStripe => 'Saa maksuja sovellustesi myynnistä Stripen kautta';

  @override
  String get monthlyPayouts => 'Kuukausittaiset maksut';

  @override
  String get monthlyPayoutsDescription => 'Saat kuukausittaiset maksut suoraan tilillesi, kun saavutat 10 \$ ansiot';

  @override
  String get secureAndReliable => 'Turvallinen ja luotettava';

  @override
  String get stripeSecureDescription => 'Stripe varmistaa sovelluksesi tulojen turvalliset ja oikea-aikaiset siirrot';

  @override
  String get selectYourCountry => 'Valitse maasi';

  @override
  String get countrySelectionPermanent => 'Maavalinasi on pysyvä eikä sitä voi muuttaa myöhemmin.';

  @override
  String get byClickingConnectNow => 'Napsauttamalla \"Yhdistä nyt\" hyväksyt';

  @override
  String get stripeConnectedAccountAgreement => 'Stripe Connected Account -sopimus';

  @override
  String get errorConnectingToStripe => 'Virhe yhdistettäessä Stripeen! Yritä myöhemmin uudelleen.';

  @override
  String get connectingYourStripeAccount => 'Stripe-tilisi yhdistäminen';

  @override
  String get stripeOnboardingInstructions =>
      'Suorita Stripe-käyttöönottoprosessi selaimessasi. Tämä sivu päivittyy automaattisesti, kun prosessi on valmis.';

  @override
  String get failedTryAgain => 'Epäonnistui? Yritä uudelleen';

  @override
  String get illDoItLater => 'Teen sen myöhemmin';

  @override
  String get successfullyConnected => 'Yhdistetty onnistuneesti!';

  @override
  String get stripeReadyForPayments =>
      'Stripe-tilisi on nyt valmis vastaanottamaan maksuja. Voit alkaa ansaita sovellustesi myynnistä heti.';

  @override
  String get updateStripeDetails => 'Päivitä Stripe-tiedot';

  @override
  String get errorUpdatingStripeDetails => 'Virhe Stripe-tietojen päivityksessä! Yritä myöhemmin uudelleen.';

  @override
  String get updatePayPal => 'Päivitä PayPal';

  @override
  String get setUpPayPal => 'Määritä PayPal';

  @override
  String get updatePayPalAccountDetails => 'Päivitä PayPal-tilisi tiedot';

  @override
  String get connectPayPalToReceivePayments =>
      'Yhdistä PayPal-tilisi aloittaaksesi maksujen vastaanottamisen sovelluksistasi';

  @override
  String get paypalEmail => 'PayPal-sähköposti';

  @override
  String get paypalMeLink => 'PayPal.me-linkki';

  @override
  String get stripeRecommendation =>
      'Jos Stripe on saatavilla maassasi, suosittelemme vahvasti sen käyttöä nopeampien ja helpompien maksujen saamiseksi.';

  @override
  String get updatePayPalDetails => 'Päivitä PayPal-tiedot';

  @override
  String get savePayPalDetails => 'Tallenna PayPal-tiedot';

  @override
  String get pleaseEnterPayPalEmail => 'Syötä PayPal-sähköpostisi';

  @override
  String get pleaseEnterPayPalMeLink => 'Syötä PayPal.me-linkkisi';

  @override
  String get doNotIncludeHttpInLink => 'Älä sisällytä http, https tai www linkkiin';

  @override
  String get pleaseEnterValidPayPalMeLink => 'Syötä kelvollinen PayPal.me-linkki';

  @override
  String get pleaseEnterValidEmail => 'Anna kelvollinen sähköpostiosoite';

  @override
  String get syncingYourRecordings => 'Synkronoidaan tallenteitasi';

  @override
  String get syncYourRecordings => 'Synkronoi tallenteet';

  @override
  String get syncNow => 'Synkronoi nyt';

  @override
  String get error => 'Virhe';

  @override
  String get speechSamples => 'Puhenäytteet';

  @override
  String additionalSampleIndex(String index) {
    return 'Lisänäyte $index';
  }

  @override
  String durationSeconds(String seconds) {
    return 'Kesto: $seconds sekuntia';
  }

  @override
  String get additionalSpeechSampleRemoved => 'Lisäpuhenäyte poistettu';

  @override
  String get consentDataMessage =>
      'Jatkamalla kaikki tämän sovelluksen kanssa jakamasi tiedot (mukaan lukien keskustelusi, tallenteet ja henkilökohtaiset tietosi) tallennetaan turvallisesti palvelimillemme tarjotaksemme sinulle tekoälypohjaisia oivalluksia ja mahdollistaaksemme kaikki sovelluksen ominaisuudet.';

  @override
  String get tasksEmptyStateMessage =>
      'Keskusteluistasi saadut tehtävät näkyvät täällä.\nNapauta + luodaksesi manuaalisesti.';

  @override
  String get clearChatAction => 'Tyhjennä keskustelu';

  @override
  String get enableApps => 'Ota sovellukset käyttöön';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => 'näytä lisää ↓';

  @override
  String get showLess => 'näytä vähemmän ↑';

  @override
  String get loadingYourRecording => 'Ladataan tallennetta...';

  @override
  String get photoDiscardedMessage => 'Tämä kuva hylättiin, koska se ei ollut merkittävä.';

  @override
  String get analyzing => 'Analysoidaan...';

  @override
  String get searchCountries => 'Etsi maita...';

  @override
  String get checkingAppleWatch => 'Tarkistetaan Apple Watchia...';

  @override
  String get installOmiOnAppleWatch => 'Asenna Omi\nApple Watchiin';

  @override
  String get installOmiOnAppleWatchDescription =>
      'Käyttääksesi Apple Watchia Omin kanssa, sinun on ensin asennettava Omi-sovellus kelloosi.';

  @override
  String get openOmiOnAppleWatch => 'Avaa Omi\nApple Watchissa';

  @override
  String get openOmiOnAppleWatchDescription =>
      'Omi-sovellus on asennettu Apple Watchiin. Avaa se ja napauta Aloita aloittaaksesi.';

  @override
  String get openWatchApp => 'Avaa Watch-sovellus';

  @override
  String get iveInstalledAndOpenedTheApp => 'Olen asentanut ja avannut sovelluksen';

  @override
  String get unableToOpenWatchApp =>
      'Apple Watch -sovellusta ei voi avata. Avaa Watch-sovellus manuaalisesti Apple Watchissa ja asenna Omi \"Saatavilla olevat sovellukset\" -osiosta.';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch yhdistetty!';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch ei ole vielä tavoitettavissa. Varmista, että Omi-sovellus on auki kellossasi.';

  @override
  String errorCheckingConnection(String error) {
    return 'Virhe yhteyden tarkistuksessa: $error';
  }

  @override
  String get muted => 'Mykistetty';

  @override
  String get processNow => 'Käsittele nyt';

  @override
  String get finishedConversation => 'Keskustelu päättynyt?';

  @override
  String get stopRecordingConfirmation =>
      'Haluatko varmasti lopettaa nauhoituksen ja tehdä yhteenvedon keskustelusta nyt?';

  @override
  String get conversationEndsManually => 'Keskustelu päättyy vain manuaalisesti.';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'Keskustelu tiivistetään $minutes minuuti$suffix hiljaisuuden jälkeen.';
  }

  @override
  String get dontAskAgain => 'Älä kysy uudelleen';

  @override
  String get waitingForTranscriptOrPhotos => 'Odotetaan litterointia tai kuvia...';

  @override
  String get noSummaryYet => 'Ei yhteenvetoa vielä';

  @override
  String hints(String text) {
    return 'Vihjeet: $text';
  }

  @override
  String get testConversationPrompt => 'Testaa keskustelukehotetta';

  @override
  String get prompt => 'Kehote';

  @override
  String get result => 'Tulos:';

  @override
  String get compareTranscripts => 'Vertaa litterointeja';

  @override
  String get notHelpful => 'Ei hyödyllinen';

  @override
  String get exportTasksWithOneTap => 'Vie tehtävät yhdellä napautuksella!';

  @override
  String get inProgress => 'Käynnissä';

  @override
  String get photos => 'Kuvat';

  @override
  String get rawData => 'Raakadata';

  @override
  String get content => 'Sisältö';

  @override
  String get noContentToDisplay => 'Ei sisältöä näytettäväksi';

  @override
  String get noSummary => 'Ei yhteenvetoa';

  @override
  String get updateOmiFirmware => 'Päivitä omin laiteohjelmisto';

  @override
  String get anErrorOccurredTryAgain => 'Tapahtui virhe. Yritä uudelleen.';

  @override
  String get welcomeBackSimple => 'Tervetuloa takaisin';

  @override
  String get addVocabularyDescription => 'Lisää sanoja, jotka Omin tulisi tunnistaa litteroinnin aikana.';

  @override
  String get enterWordsCommaSeparated => 'Syötä sanat (pilkulla erotettuna)';

  @override
  String get whenToReceiveDailySummary => 'Milloin haluat päivittäisen yhteenvedon';

  @override
  String get checkingNextSevenDays => 'Tarkistetaan seuraavat 7 päivää';

  @override
  String failedToDeleteError(String error) {
    return 'Poistaminen epäonnistui: $error';
  }

  @override
  String get developerApiKeys => 'Kehittäjän API-avaimet';

  @override
  String get noApiKeysCreateOne => 'Ei API-avaimia. Luo yksi aloittaaksesi.';

  @override
  String get commandRequired => '⌘ vaaditaan';

  @override
  String get spaceKey => 'Välilyönti';

  @override
  String loadMoreRemaining(String count) {
    return 'Lataa lisää ($count jäljellä)';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'Top $percentile% käyttäjä';
  }

  @override
  String get wrappedMinutes => 'minuuttia';

  @override
  String get wrappedConversations => 'keskustelua';

  @override
  String get wrappedDaysActive => 'aktiivista päivää';

  @override
  String get wrappedYouTalkedAbout => 'Puhuit aiheesta';

  @override
  String get wrappedActionItems => 'Tehtävät';

  @override
  String get wrappedTasksCreated => 'luotua tehtävää';

  @override
  String get wrappedCompleted => 'valmista';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% valmistumisaste';
  }

  @override
  String get wrappedYourTopDays => 'Parhaat päiväsi';

  @override
  String get wrappedBestMoments => 'Parhaat hetket';

  @override
  String get wrappedMyBuddies => 'Ystäväni';

  @override
  String get wrappedCouldntStopTalkingAbout => 'En voinut lopettaa puhumista';

  @override
  String get wrappedShow => 'SARJA';

  @override
  String get wrappedMovie => 'ELOKUVA';

  @override
  String get wrappedBook => 'KIRJA';

  @override
  String get wrappedCelebrity => 'JULKKIS';

  @override
  String get wrappedFood => 'RUOKA';

  @override
  String get wrappedMovieRecs => 'Elokuvasuosituksia ystäville';

  @override
  String get wrappedBiggest => 'Suurin';

  @override
  String get wrappedStruggle => 'Haaste';

  @override
  String get wrappedButYouPushedThrough => 'Mutta selvisit siitä 💪';

  @override
  String get wrappedWin => 'Voitto';

  @override
  String get wrappedYouDidIt => 'Onnistuit! 🎉';

  @override
  String get wrappedTopPhrases => 'Top 5 lausetta';

  @override
  String get wrappedMins => 'min';

  @override
  String get wrappedConvos => 'keskustelua';

  @override
  String get wrappedDays => 'päivää';

  @override
  String get wrappedMyBuddiesLabel => 'YSTÄVÄNI';

  @override
  String get wrappedObsessionsLabel => 'PAKKOMIELTEENI';

  @override
  String get wrappedStruggleLabel => 'HAASTE';

  @override
  String get wrappedWinLabel => 'VOITTO';

  @override
  String get wrappedTopPhrasesLabel => 'TOP LAUSEET';

  @override
  String get wrappedLetsHitRewind => 'Kelataan taaksepäin vuotesi';

  @override
  String get wrappedGenerateMyWrapped => 'Luo Wrapped';

  @override
  String get wrappedProcessingDefault => 'Käsitellään...';

  @override
  String get wrappedCreatingYourStory => 'Luodaan\n2025 tarinaasi...';

  @override
  String get wrappedSomethingWentWrong => 'Jokin meni\npieleen';

  @override
  String get wrappedAnErrorOccurred => 'Tapahtui virhe';

  @override
  String get wrappedTryAgain => 'Yritä uudelleen';

  @override
  String get wrappedNoDataAvailable => 'Ei tietoja saatavilla';

  @override
  String get wrappedOmiLifeRecap => 'Omi elämän yhteenveto';

  @override
  String get wrappedSwipeUpToBegin => 'Pyyhkäise ylös aloittaaksesi';

  @override
  String get wrappedShareText => 'Vuoteni 2025, tallentanut Omi ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare => 'Jakaminen epäonnistui. Yritä uudelleen.';

  @override
  String get wrappedFailedToStartGeneration => 'Luonnin aloitus epäonnistui. Yritä uudelleen.';

  @override
  String get wrappedStarting => 'Aloitetaan...';

  @override
  String get wrappedShare => 'Jaa';

  @override
  String get wrappedShareYourWrapped => 'Jaa Wrapped';

  @override
  String get wrappedMy2025 => 'Vuoteni 2025';

  @override
  String get wrappedRememberedByOmi => 'tallentanut Omi';

  @override
  String get wrappedMostFunDay => 'Hauskin';

  @override
  String get wrappedMostProductiveDay => 'Tuottavin';

  @override
  String get wrappedMostIntenseDay => 'Intensiivisin';

  @override
  String get wrappedFunniestMoment => 'Hauskin';

  @override
  String get wrappedMostCringeMoment => 'Noloin';

  @override
  String get wrappedMinutesLabel => 'minuuttia';

  @override
  String get wrappedConversationsLabel => 'keskustelua';

  @override
  String get wrappedDaysActiveLabel => 'aktiivista päivää';

  @override
  String get wrappedTasksGenerated => 'tehtävää luotu';

  @override
  String get wrappedTasksCompleted => 'tehtävää suoritettu';

  @override
  String get wrappedTopFivePhrases => 'Top 5 lausetta';

  @override
  String get wrappedAGreatDay => 'Hieno päivä';

  @override
  String get wrappedGettingItDone => 'Asian hoitaminen';

  @override
  String get wrappedAChallenge => 'Haaste';

  @override
  String get wrappedAHilariousMoment => 'Hauska hetki';

  @override
  String get wrappedThatAwkwardMoment => 'Se kiusallinen hetki';

  @override
  String get wrappedYouHadFunnyMoments => 'Sinulla oli hauskoja hetkiä tänä vuonna!';

  @override
  String get wrappedWeveAllBeenThere => 'Olemme kaikki olleet siellä!';

  @override
  String get wrappedFriend => 'Ystävä';

  @override
  String get wrappedYourBuddy => 'Kaverisi!';

  @override
  String get wrappedNotMentioned => 'Ei mainittu';

  @override
  String get wrappedTheHardPart => 'Vaikea osuus';

  @override
  String get wrappedPersonalGrowth => 'Henkilökohtainen kasvu';

  @override
  String get wrappedFunDay => 'Hauska';

  @override
  String get wrappedProductiveDay => 'Tuottava';

  @override
  String get wrappedIntenseDay => 'Intensiivinen';

  @override
  String get wrappedFunnyMomentTitle => 'Hauska hetki';

  @override
  String get wrappedCringeMomentTitle => 'Nolo hetki';

  @override
  String get wrappedYouTalkedAboutBadge => 'Puhuit aiheesta';

  @override
  String get wrappedCompletedLabel => 'Suoritettu';

  @override
  String get wrappedMyBuddiesCard => 'Kaverini';

  @override
  String get wrappedBuddiesLabel => 'KAVERIT';

  @override
  String get wrappedObsessionsLabelUpper => 'PAKKOMIELTET';

  @override
  String get wrappedStruggleLabelUpper => 'KAMPPAILU';

  @override
  String get wrappedWinLabelUpper => 'VOITTO';

  @override
  String get wrappedTopPhrasesLabelUpper => 'TOP LAUSEET';

  @override
  String get wrappedYourHeader => 'Sinun';

  @override
  String get wrappedTopDaysHeader => 'Parhaat päivät';

  @override
  String get wrappedYourTopDaysBadge => 'Parhaat päiväsi';

  @override
  String get wrappedBestHeader => 'Parhaat';

  @override
  String get wrappedMomentsHeader => 'Hetket';

  @override
  String get wrappedBestMomentsBadge => 'Parhaat hetket';

  @override
  String get wrappedBiggestHeader => 'Suurin';

  @override
  String get wrappedStruggleHeader => 'Kamppailu';

  @override
  String get wrappedWinHeader => 'Voitto';

  @override
  String get wrappedButYouPushedThroughEmoji => 'Mutta selvisit siitä 💪';

  @override
  String get wrappedYouDidItEmoji => 'Teit sen! 🎉';

  @override
  String get wrappedHours => 'tuntia';

  @override
  String get wrappedActions => 'toimintoa';

  @override
  String get multipleSpeakersDetected => 'Useita puhujia havaittu';

  @override
  String get multipleSpeakersDescription =>
      'Näyttää siltä, että nauhoituksessa on useita puhujia. Varmista, että olet hiljaisessa paikassa ja yritä uudelleen.';

  @override
  String get invalidRecordingDetected => 'Virheellinen nauhoitus havaittu';

  @override
  String get notEnoughSpeechDescription => 'Puhetta ei havaittu tarpeeksi. Puhu enemmän ja yritä uudelleen.';

  @override
  String get speechDurationDescription => 'Varmista, että puhut vähintään 5 sekuntia ja enintään 90.';

  @override
  String get connectionLostDescription => 'Yhteys katkesi. Tarkista internet-yhteytesi ja yritä uudelleen.';

  @override
  String get howToTakeGoodSample => 'Miten ottaa hyvä näyte?';

  @override
  String get goodSampleInstructions =>
      '1. Varmista, että olet hiljaisessa paikassa.\n2. Puhu selkeästi ja luonnollisesti.\n3. Varmista, että laitteesi on luonnollisessa asennossaan kaulallasi.\n\nKun se on luotu, voit aina parantaa sitä tai tehdä sen uudelleen.';

  @override
  String get noDeviceConnectedUseMic => 'Laitetta ei ole yhdistetty. Käytetään puhelimen mikrofonia.';

  @override
  String get doItAgain => 'Tee uudelleen';

  @override
  String get listenToSpeechProfile => 'Kuuntele ääniprofiiliani ➡️';

  @override
  String get recognizingOthers => 'Muiden tunnistaminen 👀';

  @override
  String get keepGoingGreat => 'Jatka, pärjäät loistavasti';

  @override
  String get somethingWentWrongTryAgain => 'Jokin meni pieleen! Yritä myöhemmin uudelleen.';

  @override
  String get uploadingVoiceProfile => 'Ladataan ääniprofiiliasi....';

  @override
  String get memorizingYourVoice => 'Tallennetaan ääntäsi...';

  @override
  String get personalizingExperience => 'Mukautetaan kokemustasi...';

  @override
  String get keepSpeakingUntil100 => 'Jatka puhumista kunnes saavutat 100%.';

  @override
  String get greatJobAlmostThere => 'Hienoa työtä, olet melkein valmis';

  @override
  String get soCloseJustLittleMore => 'Niin lähellä, vielä vähän';

  @override
  String get notificationFrequency => 'Ilmoitusten tiheys';

  @override
  String get controlNotificationFrequency => 'Hallitse kuinka usein Omi lähettää sinulle ennakoivia ilmoituksia.';

  @override
  String get yourScore => 'Pistemääräsi';

  @override
  String get dailyScoreBreakdown => 'Päivittäisen pistemäärän erittely';

  @override
  String get todaysScore => 'Tämän päivän pisteet';

  @override
  String get tasksCompleted => 'Tehtäviä suoritettu';

  @override
  String get completionRate => 'Suoritusaste';

  @override
  String get howItWorks => 'Miten se toimii';

  @override
  String get dailyScoreExplanation =>
      'Päivittäinen pistemääräsi perustuu tehtävien suorittamiseen. Suorita tehtäväsi parantaaksesi pistemäärääsi!';

  @override
  String get notificationFrequencyDescription =>
      'Hallitse kuinka usein Omi lähettää sinulle proaktiivisia ilmoituksia ja muistutuksia.';

  @override
  String get sliderOff => 'Pois';

  @override
  String get sliderMax => 'Maks.';

  @override
  String summaryGeneratedFor(String date) {
    return 'Yhteenveto luotu päivälle $date';
  }

  @override
  String get failedToGenerateSummary =>
      'Yhteenvedon luominen epäonnistui. Varmista, että sinulla on keskusteluja kyseiseltä päivältä.';

  @override
  String get recap => 'Kertaus';

  @override
  String deleteQuoted(String name) {
    return 'Poista \"$name\"';
  }

  @override
  String moveConversationsTo(int count) {
    return 'Siirrä $count keskustelua kansioon:';
  }

  @override
  String get noFolder => 'Ei kansiota';

  @override
  String get removeFromAllFolders => 'Poista kaikista kansioista';

  @override
  String get buildAndShareYourCustomApp => 'Rakenna ja jaa mukautettu sovelluksesi';

  @override
  String get searchAppsPlaceholder => 'Hae yli 1500 sovelluksesta';

  @override
  String get filters => 'Suodattimet';

  @override
  String get frequencyOff => 'Pois';

  @override
  String get frequencyMinimal => 'Minimaalinen';

  @override
  String get frequencyLow => 'Matala';

  @override
  String get frequencyBalanced => 'Tasapainotettu';

  @override
  String get frequencyHigh => 'Korkea';

  @override
  String get frequencyMaximum => 'Maksimi';

  @override
  String get frequencyDescOff => 'Ei proaktiivisia ilmoituksia';

  @override
  String get frequencyDescMinimal => 'Vain kriittiset muistutukset';

  @override
  String get frequencyDescLow => 'Vain tärkeät päivitykset';

  @override
  String get frequencyDescBalanced => 'Säännölliset hyödylliset muistutukset';

  @override
  String get frequencyDescHigh => 'Usein tarkistukset';

  @override
  String get frequencyDescMaximum => 'Pysy jatkuvasti mukana';

  @override
  String get clearChatQuestion => 'Tyhjennä keskustelu?';

  @override
  String get syncingMessages => 'Synkronoidaan viestejä palvelimen kanssa...';

  @override
  String get chatAppsTitle => 'Chat-sovellukset';

  @override
  String get selectApp => 'Valitse sovellus';

  @override
  String get noChatAppsEnabled => 'Chat-sovelluksia ei ole käytössä.\nNapauta \"Ota käyttöön\" lisätäksesi.';

  @override
  String get disable => 'Poista käytöstä';

  @override
  String get photoLibrary => 'Kuvakirjasto';

  @override
  String get chooseFile => 'Valitse tiedosto';

  @override
  String get configureAiPersona => 'Määritä tekoälypersoona';

  @override
  String get connectAiAssistantsToYourData => 'Yhdistä tekoälyavustajat tietoihisi';

  @override
  String get oAuth => 'OAuth';

  @override
  String get trackYourGoalsOnHomepage => 'Seuraa henkilökohtaisia tavoitteitasi etusivulla';

  @override
  String get deleteRecording => 'Poista nauhoitus';

  @override
  String get thisCannotBeUndone => 'Tätä ei voi perua.';

  @override
  String get sdCard => 'SD-kortti';

  @override
  String get fromSd => 'SD:ltä';

  @override
  String get limitless => 'Limitless';

  @override
  String get fastTransfer => 'Nopea siirto';

  @override
  String get syncingStatus => 'Synkronoidaan';

  @override
  String get failedStatus => 'Failed';

  @override
  String etaLabel(String time) {
    return 'ETA: $time';
  }

  @override
  String get transferMethod => 'Siirtotapa';

  @override
  String get fast => 'Fast';

  @override
  String get ble => 'BLE';

  @override
  String get phone => 'Phone';

  @override
  String get cancelSync => 'Peruuta synkronointi';

  @override
  String get cancelSyncMessage => 'Jo ladatut tiedot tallennetaan. Voit jatkaa myöhemmin.';

  @override
  String get syncCancelled => 'Synkronointi peruutettu';

  @override
  String get deleteProcessedFiles => 'Poista käsitellyt tiedostot';

  @override
  String get processedFilesDeleted => 'Käsitellyt tiedostot poistettu';

  @override
  String get wifiEnableFailed => 'WiFin käyttöönotto laitteessa epäonnistui. Yritä uudelleen.';

  @override
  String get deviceNoFastTransfer => 'Laitteesi ei tue nopeaa siirtoa. Käytä Bluetoothia sen sijaan.';

  @override
  String get enableHotspotMessage => 'Ota puhelimesi hotspot käyttöön ja yritä uudelleen.';

  @override
  String get transferStartFailed => 'Siirron aloitus epäonnistui. Yritä uudelleen.';

  @override
  String get deviceNotResponding => 'Laite ei vastannut. Yritä uudelleen.';

  @override
  String get invalidWifiCredentials => 'Virheelliset WiFi-tunnukset. Tarkista hotspot-asetuksesi.';

  @override
  String get wifiConnectionFailed => 'WiFi-yhteys epäonnistui. Yritä uudelleen.';

  @override
  String get sdCardProcessing => 'SD-kortin käsittely';

  @override
  String sdCardProcessingMessage(int count) {
    return 'Käsitellään $count nauhoitusta. Tiedostot poistetaan SD-kortilta jälkeen.';
  }

  @override
  String get process => 'Käsittele';

  @override
  String get wifiSyncFailed => 'WiFi-synkronointi epäonnistui';

  @override
  String get processingFailed => 'Käsittely epäonnistui';

  @override
  String get downloadingFromSdCard => 'Ladataan SD-kortilta';

  @override
  String processingProgress(int current, int total) {
    return 'Käsitellään $current/$total';
  }

  @override
  String conversationsCreated(int count) {
    return '$count conversations created';
  }

  @override
  String get internetRequired => 'Internet vaaditaan';

  @override
  String get processAudio => 'Käsittele ääni';

  @override
  String get start => 'Start';

  @override
  String get noRecordings => 'Ei nauhoituksia';

  @override
  String get audioFromOmiWillAppearHere => 'Omi-laitteesi ääni näkyy täällä';

  @override
  String get deleteProcessed => 'Poista käsitellyt';

  @override
  String get tryDifferentFilter => 'Kokeile eri suodatinta';

  @override
  String get recordings => 'Nauhoitukset';

  @override
  String get enableRemindersAccess =>
      'Ota käyttöön muistutusten käyttöoikeus asetuksissa käyttääksesi Apple Muistutuksia';

  @override
  String todayAtTime(String time) {
    return 'Tänään klo $time';
  }

  @override
  String yesterdayAtTime(String time) {
    return 'Eilen klo $time';
  }

  @override
  String get lessThanAMinute => 'Alle minuutti';

  @override
  String estimatedMinutes(int count) {
    return '~$count minuutti(a)';
  }

  @override
  String estimatedHours(int count) {
    return '~$count tunti(a)';
  }

  @override
  String estimatedTimeRemaining(String time) {
    return 'Arvio: $time jäljellä';
  }

  @override
  String get summarizingConversation => 'Tiivistetään keskustelua...\nTämä voi kestää muutaman sekunnin';

  @override
  String get resummarizingConversation => 'Tiivistetään keskustelua uudelleen...\nTämä voi kestää muutaman sekunnin';

  @override
  String get nothingInterestingRetry => 'Mitään mielenkiintoista ei löytynyt,\nhaluatko yrittää uudelleen?';

  @override
  String get noSummaryForConversation => 'Tälle keskustelulle\nei ole tiivistelmää.';

  @override
  String get unknownLocation => 'Tuntematon sijainti';

  @override
  String get couldNotLoadMap => 'Karttaa ei voitu ladata';

  @override
  String get triggerConversationIntegration => 'Käynnistä keskustelun luonti-integraatio';

  @override
  String get webhookUrlNotSet => 'Webhook-URL-osoitetta ei ole asetettu';

  @override
  String get setWebhookUrlInSettings => 'Aseta webhook-URL kehittäjäasetuksissa käyttääksesi tätä ominaisuutta.';

  @override
  String get sendWebUrl => 'Lähetä web-URL';

  @override
  String get sendTranscript => 'Lähetä litterointi';

  @override
  String get sendSummary => 'Lähetä tiivistelmä';

  @override
  String get debugModeDetected => 'Virheenkorjaustila havaittu';

  @override
  String get performanceReduced => 'Suorituskyky voi olla alentunut';

  @override
  String autoClosingInSeconds(int seconds) {
    return 'Sulkeutuu automaattisesti $seconds sekunnissa';
  }

  @override
  String get modelRequired => 'Malli vaaditaan';

  @override
  String get downloadWhisperModel => 'Lataa whisper-malli käyttääksesi laitteella tapahtuvaa transkriptiota';

  @override
  String get deviceNotCompatible => 'Laitteesi ei ole yhteensopiva laitteella tapahtuvan transkription kanssa';

  @override
  String get deviceRequirements => 'Laitteesi ei täytä laitteella tapahtuvan puheentunnistuksen vaatimuksia.';

  @override
  String get willLikelyCrash => 'Tämän käyttöönotto aiheuttaa todennäköisesti sovelluksen kaatumisen tai jäätymisen.';

  @override
  String get transcriptionSlowerLessAccurate => 'Transkriptio on huomattavasti hitaampi ja epätarkempi.';

  @override
  String get proceedAnyway => 'Jatka silti';

  @override
  String get olderDeviceDetected => 'Vanhempi laite havaittu';

  @override
  String get onDeviceSlower => 'Laitteella tapahtuva puheentunnistus voi olla hitaampaa tällä laitteella.';

  @override
  String get batteryUsageHigher => 'Akunkäyttö on korkeampi kuin pilvitranskriptiossa.';

  @override
  String get considerOmiCloud => 'Harkitse Omi Cloudin käyttöä paremman suorituskyvyn saavuttamiseksi.';

  @override
  String get highResourceUsage => 'Korkea resurssien käyttö';

  @override
  String get onDeviceIntensive => 'Laitteella tapahtuva puheentunnistus on laskennallisesti vaativaa.';

  @override
  String get batteryDrainIncrease => 'Akun kulutus kasvaa merkittävästi.';

  @override
  String get deviceMayWarmUp => 'Laite voi lämmetä pitkäaikaisessa käytössä.';

  @override
  String get speedAccuracyLower => 'Nopeus ja tarkkuus voivat olla alhaisempia kuin pilvimalleilla.';

  @override
  String get cloudProvider => 'Pilvipalveluntarjoaja';

  @override
  String get premiumMinutesInfo =>
      '1 200 premium-minuuttia/kk. Laitteella-välilehti tarjoaa rajattoman ilmaisen puheentunnistuksen.';

  @override
  String get viewUsage => 'Näytä käyttö';

  @override
  String get localProcessingInfo =>
      'Ääni käsitellään paikallisesti. Toimii offline-tilassa, yksityisempi, mutta kuluttaa enemmän akkua.';

  @override
  String get model => 'Malli';

  @override
  String get performanceWarning => 'Suorituskykyvaroitus';

  @override
  String get largeModelWarning =>
      'Tämä malli on suuri ja saattaa kaataa sovelluksen tai toimia erittäin hitaasti mobiililaitteilla.\n\n\"small\" tai \"base\" on suositeltu.';

  @override
  String get usingNativeIosSpeech => 'Käytetään iOS:n natiivia puheentunnistusta';

  @override
  String get noModelDownloadRequired =>
      'Laitteesi natiivi puheentunnistusmoottori on käytössä. Mallin lataus ei ole tarpeen.';

  @override
  String get modelReady => 'Malli valmis';

  @override
  String get redownload => 'Lataa uudelleen';

  @override
  String get doNotCloseApp => 'Älä sulje sovellusta.';

  @override
  String get downloading => 'Ladataan...';

  @override
  String get downloadModel => 'Lataa malli';

  @override
  String estimatedSize(String size) {
    return 'Arvioitu koko: ~$size Mt';
  }

  @override
  String availableSpace(String space) {
    return 'Käytettävissä oleva tila: $space';
  }

  @override
  String get notEnoughSpace => 'Varoitus: Ei tarpeeksi tilaa!';

  @override
  String get download => 'Lataa';

  @override
  String downloadError(String error) {
    return 'Latausvirhe: $error';
  }

  @override
  String get cancelled => 'Peruutettu';

  @override
  String get deviceNotCompatibleTitle => 'Laite ei yhteensopiva';

  @override
  String get deviceNotMeetRequirements => 'Laitteesi ei täytä laitteella tapahtuvan transkription vaatimuksia.';

  @override
  String get transcriptionSlowerOnDevice => 'Laitteella tapahtuva transkriptio voi olla hitaampaa tällä laitteella.';

  @override
  String get computationallyIntensive => 'Laitteella tapahtuva transkriptio on laskennallisesti intensiivistä.';

  @override
  String get batteryDrainSignificantly => 'Akun kulutus kasvaa merkittävästi.';

  @override
  String get premiumMinutesMonth =>
      '1 200 premium-minuuttia/kk. Laitteella-välilehti tarjoaa rajoittamattoman ilmaisen transkription. ';

  @override
  String get audioProcessedLocally =>
      'Ääni käsitellään paikallisesti. Toimii offline, yksityisempi, mutta kuluttaa enemmän akkua.';

  @override
  String get languageLabel => 'Kieli';

  @override
  String get modelLabel => 'Malli';

  @override
  String get modelTooLargeWarning =>
      'Tämä malli on suuri ja voi aiheuttaa sovelluksen kaatumisen tai erittäin hitaan toiminnan mobiililaitteissa.\n\nSuositellaan small tai base.';

  @override
  String get nativeEngineNoDownload => 'Käytetään laitteesi natiivia puhe-moottoria. Mallin latausta ei tarvita.';

  @override
  String modelReadyWithName(String model) {
    return 'Malli valmis ($model)';
  }

  @override
  String get reDownload => 'Lataa uudelleen';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return 'Ladataan $model: $received / $total MB';
  }

  @override
  String preparingModel(String model) {
    return 'Valmistellaan $model...';
  }

  @override
  String downloadErrorWithMessage(String error) {
    return 'Latausvirhe: $error';
  }

  @override
  String estimatedSizeWithValue(String size) {
    return 'Arvioitu koko: ~$size MB';
  }

  @override
  String availableSpaceWithValue(String space) {
    return 'Käytettävissä oleva tila: $space';
  }

  @override
  String get omiTranscriptionOptimized =>
      'Omin sisäänrakennettu live-transkriptio on optimoitu reaaliaikaisiin keskusteluihin automaattisella puhujan tunnistuksella ja diarisaatiolla.';

  @override
  String get reset => 'Nollaa';

  @override
  String get useTemplateFrom => 'Käytä mallia kohteesta';

  @override
  String get selectProviderTemplate => 'Valitse palveluntarjoajan malli...';

  @override
  String get quicklyPopulateResponse => 'Täytä nopeasti tunnetulla palveluntarjoajan vastausmuodolla';

  @override
  String get quicklyPopulateRequest => 'Täytä nopeasti tunnetulla palveluntarjoajan pyyntömuodolla';

  @override
  String get invalidJsonError => 'Virheellinen JSON';

  @override
  String downloadModelWithName(String model) {
    return 'Lataa malli ($model)';
  }

  @override
  String modelNameWithFile(String model) {
    return 'Malli: $model';
  }

  @override
  String get device => 'Laite';

  @override
  String get chatAssistantsTitle => 'Chat-avustajat';

  @override
  String get permissionReadConversations => 'Lue keskusteluja';

  @override
  String get permissionReadMemories => 'Lue muistoja';

  @override
  String get permissionReadTasks => 'Lue tehtäviä';

  @override
  String get permissionCreateConversations => 'Luo keskusteluja';

  @override
  String get permissionCreateMemories => 'Luo muistoja';

  @override
  String get permissionTypeAccess => 'Pääsy';

  @override
  String get permissionTypeCreate => 'Luo';

  @override
  String get permissionTypeTrigger => 'Laukaisin';

  @override
  String get permissionDescReadConversations => 'Tämä sovellus voi käyttää keskustelujasi.';

  @override
  String get permissionDescReadMemories => 'Tämä sovellus voi käyttää muistojasi.';

  @override
  String get permissionDescReadTasks => 'Tämä sovellus voi käyttää tehtäviäsi.';

  @override
  String get permissionDescCreateConversations => 'Tämä sovellus voi luoda uusia keskusteluja.';

  @override
  String get permissionDescCreateMemories => 'Tämä sovellus voi luoda uusia muistoja.';

  @override
  String get realtimeListening => 'Reaaliaikainen kuuntelu';

  @override
  String get setupCompleted => 'Valmis';

  @override
  String get pleaseSelectRating => 'Valitse arvio';

  @override
  String get writeReviewOptional => 'Kirjoita arvostelu (valinnainen)';

  @override
  String get setupQuestionsIntro => 'Auta meitä parantamaan Omia vastaamalla muutamaan kysymykseen. 🫶 💜';

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
  String get professionEntrepreneur => 'Yrittäjä';

  @override
  String get professionSoftwareEngineer => 'Software Engineer';

  @override
  String get professionProductManager => 'Product Manager';

  @override
  String get professionExecutive => 'Executive';

  @override
  String get professionSales => 'Myynti';

  @override
  String get professionStudent => 'Opiskelija';

  @override
  String get usageAtWork => 'Työssä';

  @override
  String get usageIrlEvents => 'IRL Events';

  @override
  String get usageOnline => 'Online';

  @override
  String get usageSocialSettings => 'In Social Settings';

  @override
  String get usageEverywhere => 'Kaikkialla';

  @override
  String get customBackendUrlTitle => 'Mukautettu palvelimen URL';

  @override
  String get backendUrlLabel => 'Palvelimen URL';

  @override
  String get saveUrlButton => 'Tallenna URL';

  @override
  String get enterBackendUrlError => 'Anna palvelimen URL';

  @override
  String get urlMustEndWithSlashError => 'URL:n on päätyttävä \"/\"';

  @override
  String get invalidUrlError => 'Anna kelvollinen URL';

  @override
  String get backendUrlSavedSuccess => 'Palvelimen URL tallennettu!';

  @override
  String get signInTitle => 'Kirjaudu sisään';

  @override
  String get signInButton => 'Kirjaudu sisään';

  @override
  String get enterEmailError => 'Anna sähköpostiosoitteesi';

  @override
  String get invalidEmailError => 'Anna kelvollinen sähköpostiosoite';

  @override
  String get enterPasswordError => 'Anna salasanasi';

  @override
  String get passwordMinLengthError => 'Salasanan on oltava vähintään 8 merkkiä';

  @override
  String get signInSuccess => 'Kirjautuminen onnistui!';

  @override
  String get alreadyHaveAccountLogin => 'Onko sinulla jo tili? Kirjaudu sisään';

  @override
  String get emailLabel => 'Sähköposti';

  @override
  String get passwordLabel => 'Salasana';

  @override
  String get createAccountTitle => 'Luo tili';

  @override
  String get nameLabel => 'Nimi';

  @override
  String get repeatPasswordLabel => 'Toista salasana';

  @override
  String get signUpButton => 'Rekisteröidy';

  @override
  String get enterNameError => 'Anna nimesi';

  @override
  String get passwordsDoNotMatch => 'Salasanat eivät täsmää';

  @override
  String get signUpSuccess => 'Rekisteröityminen onnistui!';

  @override
  String get loadingKnowledgeGraph => 'Ladataan tietograafia...';

  @override
  String get noKnowledgeGraphYet => 'Ei vielä tietograafia';

  @override
  String get buildingKnowledgeGraphFromMemories => 'Rakennetaan tietograafia muistoista...';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'Tietograafisi rakennetaan automaattisesti, kun luot uusia muistoja.';

  @override
  String get buildGraphButton => 'Rakenna graafi';

  @override
  String get checkOutMyMemoryGraph => 'Katso muistigraafikani!';

  @override
  String get getButton => 'Hae';

  @override
  String openingApp(String appName) {
    return 'Avataan $appName...';
  }

  @override
  String get writeSomething => 'Kirjoita jotain';

  @override
  String get submitReply => 'Lähetä vastaus';

  @override
  String get editYourReply => 'Muokkaa vastaustasi';

  @override
  String get replyToReview => 'Vastaa arvosteluun';

  @override
  String get rateAndReviewThisApp => 'Arvioi ja arvostele tämä sovellus';

  @override
  String get noChangesInReview => 'Ei muutoksia arvostelussa päivitettäväksi.';

  @override
  String get cantRateWithoutInternet => 'Sovellusta ei voi arvioida ilman internetyhteyttä.';

  @override
  String get appAnalytics => 'Sovellusanalytiikka';

  @override
  String get learnMoreLink => 'lue lisää';

  @override
  String get moneyEarned => 'Ansaittu raha';

  @override
  String get writeYourReply => 'Kirjoita vastauksesi...';

  @override
  String get replySentSuccessfully => 'Vastaus lähetetty onnistuneesti';

  @override
  String failedToSendReply(String error) {
    return 'Vastauksen lähettäminen epäonnistui: $error';
  }

  @override
  String get send => 'Lähetä';

  @override
  String starFilter(int count) {
    return '$count tähteä';
  }

  @override
  String get noReviewsFound => 'Arvosteluja ei löytynyt';

  @override
  String get editReply => 'Muokkaa vastausta';

  @override
  String get reply => 'Vastaa';

  @override
  String starFilterLabel(int count) {
    return '$count tähti';
  }

  @override
  String get sharePublicLink => 'Jaa julkinen linkki';

  @override
  String get makePersonaPublic => 'Make Persona Public';

  @override
  String get connectedKnowledgeData => 'Yhdistetty tietolähteisiin';

  @override
  String get enterName => 'Syötä nimi';

  @override
  String get disconnectTwitter => 'Katkaise Twitter-yhteys';

  @override
  String get disconnectTwitterConfirmation =>
      'Haluatko varmasti katkaista Twitter-tilisi yhteyden? Persoonallasi ei ole enää pääsyä Twitter-tietoihisi.';

  @override
  String get getOmiDeviceDescription => 'Luo tarkempi klooni henkilökohtaisilla keskusteluillasi';

  @override
  String get getOmi => 'Hanki Omi';

  @override
  String get iHaveOmiDevice => 'I have Omi device';

  @override
  String get goal => 'TAVOITE';

  @override
  String get tapToTrackThisGoal => 'Napauta seurataksesi tätä tavoitetta';

  @override
  String get tapToSetAGoal => 'Napauta asettaaksesi tavoitteen';

  @override
  String get processedConversations => 'Käsitellyt keskustelut';

  @override
  String get updatedConversations => 'Päivitetyt keskustelut';

  @override
  String get newConversations => 'Uudet keskustelut';

  @override
  String get summaryTemplate => 'Yhteenvetomalli';

  @override
  String get suggestedTemplates => 'Ehdotetut mallit';

  @override
  String get otherTemplates => 'Muut mallit';

  @override
  String get availableTemplates => 'Saatavilla olevat mallit';

  @override
  String get getCreative => 'Ole luova';

  @override
  String get defaultLabel => 'Oletus';

  @override
  String get lastUsedLabel => 'Viimeksi käytetty';

  @override
  String get setDefaultApp => 'Aseta oletussovellus';

  @override
  String setDefaultAppContent(String appName) {
    return 'Asetetaanko $appName oletusyhteenvetosovellukseksi?\\n\\nTätä sovellusta käytetään automaattisesti kaikkiin tuleviin keskusteluyhteenvetoihin.';
  }

  @override
  String get setDefaultButton => 'Aseta oletukseksi';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName asetettu oletusyhteenvetosovellukseksi';
  }

  @override
  String get createCustomTemplate => 'Luo mukautettu malli';

  @override
  String get allTemplates => 'Kaikki mallit';

  @override
  String failedToInstallApp(String appName) {
    return '$appName asennus epäonnistui. Yritä uudelleen.';
  }

  @override
  String errorInstallingApp(String appName, String error) {
    return 'Virhe asennettaessa $appName: $error';
  }

  @override
  String tagSpeaker(int speakerId) {
    return 'Merkitse puhuja $speakerId';
  }

  @override
  String get personNameAlreadyExists => 'A person with this name already exists.';

  @override
  String get selectYouFromList => 'Merkitäksesi itsesi, valitse \"Sinä\" luettelosta.';

  @override
  String get enterPersonsName => 'Syötä henkilön nimi';

  @override
  String get addPerson => 'Add Person';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'Merkitse muut segmentit tältä puhujalta ($selected/$total)';
  }

  @override
  String get tagOtherSegments => 'Merkitse muut segmentit';

  @override
  String get managePeople => 'Hallitse henkilöitä';

  @override
  String get shareViaSms => 'Jaa tekstiviestillä';

  @override
  String get selectContactsToShareSummary => 'Valitse yhteystiedot keskustelun yhteenvedon jakamiseksi';

  @override
  String get searchContactsHint => 'Etsi yhteystietoja...';

  @override
  String contactsSelectedCount(int count) {
    return '$count valittu';
  }

  @override
  String get clearAllSelection => 'Tyhjennä kaikki';

  @override
  String get selectContactsToShare => 'Valitse yhteystiedot jakamista varten';

  @override
  String shareWithContactCount(int count) {
    return 'Jaa $count yhteystiedolle';
  }

  @override
  String shareWithContactsCount(int count) {
    return 'Jaa $count yhteystiedolle';
  }

  @override
  String get contactsPermissionRequired => 'Yhteystietolupa vaaditaan';

  @override
  String get contactsPermissionRequiredForSms => 'Yhteystietolupa vaaditaan jakamiseen tekstiviestillä';

  @override
  String get grantContactsPermissionForSms => 'Anna yhteystietolupa jakamiseen tekstiviestillä';

  @override
  String get noContactsWithPhoneNumbers => 'Puhelinnumerollisia yhteystietoja ei löytynyt';

  @override
  String get noContactsMatchSearch => 'Yksikään yhteystieto ei vastaa hakuasi';

  @override
  String get failedToLoadContacts => 'Yhteystietojen lataaminen epäonnistui';

  @override
  String get failedToPrepareConversationForSharing =>
      'Keskustelun valmistelu jakamista varten epäonnistui. Yritä uudelleen.';

  @override
  String get couldNotOpenSmsApp => 'SMS-sovellusta ei voitu avata. Yritä uudelleen.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'Tässä mitä juuri keskustelimme: $link';
  }

  @override
  String get wifiSync => 'WiFi-synkronointi';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item kopioitu leikepöydälle';
  }

  @override
  String get wifiConnectionFailedTitle => 'WiFi-yhteys epäonnistui';

  @override
  String connectingToDeviceName(String deviceName) {
    return 'Yhdistetään laitteeseen $deviceName';
  }

  @override
  String enableDeviceWifi(String deviceName) {
    return 'Ota käyttöön $deviceName-laitteen WiFi';
  }

  @override
  String connectToDeviceName(String deviceName) {
    return 'Connect to $deviceName';
  }

  @override
  String get recordingDetails => 'Nauhoituksen tiedot';

  @override
  String get storageLocationSdCard => 'SD-kortti';

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
  String get transferring => 'Siirretään...';

  @override
  String get transferRequired => 'Siirto vaaditaan';

  @override
  String get downloadingAudioFromSdCard => 'Ladataan ääntä laitteesi SD-kortilta';

  @override
  String get transferRequiredDescription =>
      'Tämä nauhoitus on tallennettu laitteesi SD-kortille. Siirrä se puhelimeesi toistaaksesi tai jakaaksesi.';

  @override
  String get cancelTransfer => 'Peruuta siirto';

  @override
  String get transferToPhone => 'Siirrä puhelimeen';

  @override
  String get privateAndSecureOnDevice => 'Private & secure on your device';

  @override
  String get recordingInfo => 'Nauhoituksen tiedot';

  @override
  String get transferInProgress => 'Siirto käynnissä...';

  @override
  String get shareRecording => 'Jaa nauhoitus';

  @override
  String get deleteRecordingConfirmation =>
      'Haluatko varmasti poistaa tämän nauhoituksen pysyvästi? Tätä ei voi perua.';

  @override
  String get recordingIdLabel => 'Nauhoituksen tunnus';

  @override
  String get dateTimeLabel => 'Date & Time';

  @override
  String get durationLabel => 'Duration';

  @override
  String get audioFormatLabel => 'Äänimuoto';

  @override
  String get storageLocationLabel => 'Tallennussijainti';

  @override
  String get estimatedSizeLabel => 'Estimated Size';

  @override
  String get deviceModelLabel => 'Laitteen malli';

  @override
  String get deviceIdLabel => 'Laitteen tunnus';

  @override
  String get statusLabel => 'Tila';

  @override
  String get statusProcessed => 'Käsitelty';

  @override
  String get statusUnprocessed => 'Unprocessed';

  @override
  String get switchedToFastTransfer => 'Vaihdettu nopeaan siirtoon';

  @override
  String get transferCompleteMessage => 'Siirto valmis! Voit nyt toistaa tämän nauhoituksen.';

  @override
  String transferFailedMessage(String error) {
    return 'Siirto epäonnistui: $error';
  }

  @override
  String get transferCancelled => 'Siirto peruutettu';

  @override
  String get fastTransferEnabled => 'Nopea siirto käytössä';

  @override
  String get bluetoothSyncEnabled => 'Bluetooth-synkronointi käytössä';

  @override
  String get enableFastTransfer => 'Ota nopea siirto käyttöön';

  @override
  String get fastTransferDescription =>
      'Nopea siirto käyttää WiFiä ~5x nopeampiin nopeuksiin. Puhelimesi yhdistää tilapäisesti Omi-laitteesi WiFi-verkkoon siirron aikana.';

  @override
  String get internetAccessPausedDuringTransfer => 'Internet-yhteys keskeytetään siirron ajaksi';

  @override
  String get chooseTransferMethodDescription => 'Valitse, miten tallenteet siirretään Omi-laitteesta puhelimeesi.';

  @override
  String get wifiSpeed => '~150 KB/s WiFin kautta';

  @override
  String get fiveTimesFaster => '5X NOPEAMPI';

  @override
  String get fastTransferMethodDescription =>
      'Luo suoran WiFi-yhteyden Omi-laitteeseesi. Puhelimesi katkeaa tilapäisesti tavallisesta WiFistä siirron aikana.';

  @override
  String get bluetooth => 'Bluetooth';

  @override
  String get bleSpeed => '~30 KB/s BLE:n kautta';

  @override
  String get bluetoothMethodDescription =>
      'Käyttää tavallista Bluetooth Low Energy -yhteyttä. Hitaampi, mutta ei vaikuta WiFi-yhteyteen.';

  @override
  String get selected => 'Valittu';

  @override
  String get selectOption => 'Valitse';

  @override
  String get lowBatteryAlertTitle => 'Alhaisen akun varoitus';

  @override
  String get lowBatteryAlertBody => 'Laitteesi akku on alhainen. Aika ladata! 🔋';

  @override
  String get deviceDisconnectedNotificationTitle => 'Omi-laitteesi yhteys katkesi';

  @override
  String get deviceDisconnectedNotificationBody => 'Yhdistä uudelleen jatkaaksesi Omin käyttöä.';

  @override
  String get firmwareUpdateAvailable => 'Laiteohjelmistopäivitys saatavilla';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'Uusi laiteohjelmistopäivitys ($version) on saatavilla Omi-laitteellesi. Haluatko päivittää nyt?';
  }

  @override
  String get later => 'Myöhemmin';

  @override
  String get appDeletedSuccessfully => 'Sovellus poistettu onnistuneesti';

  @override
  String get appDeleteFailed => 'Sovelluksen poistaminen epäonnistui. Yritä myöhemmin uudelleen.';

  @override
  String get appVisibilityChangedSuccessfully =>
      'Sovelluksen näkyvyys muutettu onnistuneesti. Muutos voi näkyä muutaman minuutin kuluttua.';

  @override
  String get errorActivatingAppIntegration =>
      'Virhe sovelluksen aktivoinnissa. Jos kyseessä on integrointisovellus, varmista, että asennus on valmis.';

  @override
  String get errorUpdatingAppStatus => 'Sovelluksen tilan päivittämisessä tapahtui virhe.';

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
  String get migrationErrorOccurred => 'Siirron aikana tapahtui virhe. Yritä uudelleen.';

  @override
  String get migrationComplete => 'Siirto valmis!';

  @override
  String dataProtectedWithSettings(String level) {
    return 'Tietosi on suojattu asetuksillasi';
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
  String get importantConversationTitle => 'Tärkeä keskustelu';

  @override
  String get importantConversationBody => 'Sinulla oli juuri tärkeä keskustelu. Napauta jakaaksesi yhteenvedon muille.';

  @override
  String get templateName => 'Mallin nimi';

  @override
  String get templateNameHint => 'esim. Kokouksen toimenpiteiden poimija';

  @override
  String get nameMustBeAtLeast3Characters => 'Nimen on oltava vähintään 3 merkkiä';

  @override
  String get conversationPromptHint => 'esim. Poimi toimenpiteet, päätökset ja keskeiset havainnot keskustelusta.';

  @override
  String get pleaseEnterAppPrompt => 'Anna sovelluksellesi kehote';

  @override
  String get promptMustBeAtLeast10Characters => 'Kehotteen on oltava vähintään 10 merkkiä';

  @override
  String get anyoneCanDiscoverTemplate => 'Kuka tahansa voi löytää mallisi';

  @override
  String get onlyYouCanUseTemplate => 'Vain sinä voit käyttää tätä mallia';

  @override
  String get generatingDescription => 'Luodaan kuvausta...';

  @override
  String get creatingAppIcon => 'Luodaan sovelluskuvaketta...';

  @override
  String get installingApp => 'Asennetaan sovellusta...';

  @override
  String get appCreatedAndInstalled => 'Sovellus luotu ja asennettu!';

  @override
  String get appCreatedSuccessfully => 'Sovellus luotu onnistuneesti!';

  @override
  String get failedToCreateApp => 'Sovelluksen luonti epäonnistui. Yritä uudelleen.';

  @override
  String get addAppSelectCoreCapability => 'Valitse vielä yksi ydintoiminto sovelluksellesi';

  @override
  String get addAppSelectPaymentPlan => 'Valitse maksusuunnitelma ja syötä hinta sovelluksellesi';

  @override
  String get addAppSelectCapability => 'Valitse vähintään yksi toiminto sovelluksellesi';

  @override
  String get addAppSelectLogo => 'Valitse logo sovelluksellesi';

  @override
  String get addAppEnterChatPrompt => 'Syötä chat-kehote sovelluksellesi';

  @override
  String get addAppEnterConversationPrompt => 'Syötä keskustelukehote sovelluksellesi';

  @override
  String get addAppSelectTriggerEvent => 'Valitse laukaisutapahtuma sovelluksellesi';

  @override
  String get addAppEnterWebhookUrl => 'Syötä webhook-URL sovelluksellesi';

  @override
  String get addAppSelectCategory => 'Valitse kategoria sovelluksellesi';

  @override
  String get addAppFillRequiredFields => 'Täytä kaikki pakolliset kentät oikein';

  @override
  String get addAppUpdatedSuccess => 'Sovellus päivitetty onnistuneesti 🚀';

  @override
  String get addAppUpdateFailed => 'Päivitys epäonnistui. Yritä myöhemmin uudelleen';

  @override
  String get addAppSubmittedSuccess => 'Sovellus lähetetty onnistuneesti 🚀';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'Virhe tiedostonvalitsimen avaamisessa: $message';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'Virhe kuvan valinnassa: $error';
  }

  @override
  String get addAppPhotosPermissionDenied => 'Valokuvalupa evätty. Salli pääsy valokuviin';

  @override
  String get addAppErrorSelectingImageRetry => 'Virhe kuvan valinnassa. Yritä uudelleen.';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'Virhe pikkukuvan valinnassa: $error';
  }

  @override
  String get addAppErrorSelectingThumbnailRetry => 'Virhe pikkukuvan valinnassa. Yritä uudelleen.';

  @override
  String get addAppCapabilityConflictWithPersona => 'Muita toimintoja ei voi valita Personan kanssa';

  @override
  String get addAppPersonaConflictWithCapabilities => 'Personaa ei voi valita muiden toimintojen kanssa';

  @override
  String get personaTwitterHandleNotFound => 'Twitter-tiliä ei löytynyt';

  @override
  String get personaTwitterHandleSuspended => 'Twitter-tili on jäädytetty';

  @override
  String get personaFailedToVerifyTwitter => 'Twitter-tilin vahvistus epäonnistui';

  @override
  String get personaFailedToFetch => 'Personan haku epäonnistui';

  @override
  String get personaFailedToCreate => 'Personan luonti epäonnistui';

  @override
  String get personaConnectKnowledgeSource => 'Yhdistä vähintään yksi tietolähde (Omi tai Twitter)';

  @override
  String get personaUpdatedSuccessfully => 'Persona päivitetty onnistuneesti';

  @override
  String get personaFailedToUpdate => 'Personan päivitys epäonnistui';

  @override
  String get personaPleaseSelectImage => 'Valitse kuva';

  @override
  String get personaFailedToCreateTryLater => 'Personan luonti epäonnistui. Yritä myöhemmin uudelleen.';

  @override
  String personaFailedToCreateWithError(String error) {
    return 'Personan luonti epäonnistui: $error';
  }

  @override
  String get personaFailedToEnable => 'Personan käyttöönotto epäonnistui';

  @override
  String personaErrorEnablingWithError(String error) {
    return 'Virhe personan käyttöönotossa: $error';
  }

  @override
  String get paymentFailedToFetchCountries => 'Tuettujen maiden haku epäonnistui. Yritä myöhemmin uudelleen.';

  @override
  String get paymentFailedToSetDefault => 'Oletusmaksutavan asettaminen epäonnistui. Yritä myöhemmin uudelleen.';

  @override
  String get paymentFailedToSavePaypal => 'PayPal-tietojen tallennus epäonnistui. Yritä myöhemmin uudelleen.';

  @override
  String get paypalEmailHint => 'nik@example.com';

  @override
  String get paypalMeLinkHint => 'paypal.me/nik';

  @override
  String get paymentMethodStripe => 'Stripe';

  @override
  String get paymentMethodPayPal => 'PayPal';

  @override
  String get paymentStatusActive => 'Aktiivinen';

  @override
  String get paymentStatusConnected => 'Yhdistetty';

  @override
  String get paymentStatusNotConnected => 'Ei yhdistetty';

  @override
  String get paymentAppCost => 'Sovelluksen hinta';

  @override
  String get paymentEnterValidAmount => 'Syötä kelvollinen summa';

  @override
  String get paymentEnterAmountGreaterThanZero => 'Syötä summa, joka on suurempi kuin 0';

  @override
  String get paymentPlan => 'Maksusuunnitelma';

  @override
  String get paymentNoneSelected => 'Ei valittu';

  @override
  String get aiGenPleaseEnterDescription => 'Anna sovelluksellesi kuvaus';

  @override
  String get aiGenCreatingAppIcon => 'Luodaan sovelluskuvaketta...';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'Tapahtui virhe: $message';
  }

  @override
  String get aiGenAppCreatedSuccessfully => 'Sovellus luotu onnistuneesti!';

  @override
  String get aiGenFailedToCreateApp => 'Sovelluksen luominen epäonnistui';

  @override
  String get aiGenErrorWhileCreatingApp => 'Sovelluksen luomisessa tapahtui virhe';

  @override
  String get aiGenFailedToGenerateApp => 'Sovelluksen luominen epäonnistui. Yritä uudelleen.';

  @override
  String get aiGenFailedToRegenerateIcon => 'Kuvakkeen uudelleenluominen epäonnistui';

  @override
  String get aiGenPleaseGenerateAppFirst => 'Luo ensin sovellus';

  @override
  String get xHandleTitle => 'Mikä on X-käyttäjätunnuksesi?';

  @override
  String get xHandleDescription => 'We will pre-train your Omi clone\nbased on your account\'s activity';

  @override
  String get xHandleHint => '@nikshevchenko';

  @override
  String get xHandlePleaseEnter => 'Syötä X-käyttäjätunnuksesi';

  @override
  String get xHandlePleaseEnterValid => 'Syötä kelvollinen X-käyttäjätunnus';

  @override
  String get nextButton => 'Next';

  @override
  String get connectOmiDevice => 'Yhdistä Omi-laite';

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'Olet vaihtamassa Rajoittamaton-pakettisi pakettiin $title. Haluatko varmasti jatkaa?';
  }

  @override
  String get planUpgradeScheduledMessage =>
      'Upgrade scheduled! Your monthly plan continues until the end of your billing period, then automatically switches to annual.';

  @override
  String get couldNotSchedulePlanChange => 'Paketin vaihtoa ei voitu ajoittaa. Yritä uudelleen.';

  @override
  String get subscriptionReactivatedDefault =>
      'Tilauksesi on aktivoitu uudelleen! Ei veloitusta nyt - sinut laskutetaan nykyisen jakson lopussa.';

  @override
  String get subscriptionSuccessfulCharged => 'Tilaus onnistui! Sinut on veloitettu uudesta laskutusjaksosta.';

  @override
  String get couldNotProcessSubscription => 'Tilausta ei voitu käsitellä. Yritä uudelleen.';

  @override
  String get couldNotLaunchUpgradePage => 'Päivityssivua ei voitu avata. Yritä uudelleen.';

  @override
  String get transcriptionJsonPlaceholder => 'Paste your JSON configuration here...';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get pricePlaceholder => '0.00';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'Virhe tiedostonvalitsimen avaamisessa: $message';
  }

  @override
  String importErrorGeneric(String error) {
    return 'Virhe: $error';
  }

  @override
  String get mergeConversationsSuccessTitle => 'Keskustelut yhdistetty onnistuneesti';

  @override
  String mergeConversationsSuccessBody(int count) {
    return '$count keskustelua yhdistettiin onnistuneesti';
  }

  @override
  String get dailyReflectionNotificationTitle => 'Aika päivittäiselle reflektiolle';

  @override
  String get dailyReflectionNotificationBody => 'Kerro minulle päivästäsi';

  @override
  String get actionItemReminderTitle => 'Omi-muistutus';

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName yhteys katkaistu';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'Yhdistä uudelleen jatkaaksesi $deviceName käyttöä.';
  }

  @override
  String get onboardingSignIn => 'Kirjaudu sisään';

  @override
  String get onboardingYourName => 'Nimesi';

  @override
  String get onboardingLanguage => 'Kieli';

  @override
  String get onboardingPermissions => 'Käyttöoikeudet';

  @override
  String get onboardingComplete => 'Valmis';

  @override
  String get onboardingWelcomeToOmi => 'Tervetuloa Omiin';

  @override
  String get onboardingTellUsAboutYourself => 'Kerro meille itsestäsi';

  @override
  String get onboardingChooseYourPreference => 'Valitse asetuksesi';

  @override
  String get onboardingGrantRequiredAccess => 'Myönnä tarvittava käyttöoikeus';

  @override
  String get onboardingYoureAllSet => 'Olet valmis';

  @override
  String get searchTranscriptOrSummary => 'Hae transkriptiosta tai yhteenvedosta...';

  @override
  String get myGoal => 'Tavoitteeni';

  @override
  String get appNotAvailable => 'Hups! Etsimääsi sovellusta ei näytä olevan saatavilla.';

  @override
  String get failedToConnectTodoist => 'Yhteyden muodostaminen Todoistiin epäonnistui';

  @override
  String get failedToConnectAsana => 'Yhteyden muodostaminen Asanaan epäonnistui';

  @override
  String get failedToConnectGoogleTasks => 'Yhteyden muodostaminen Google Tasksiin epäonnistui';

  @override
  String get failedToConnectClickUp => 'Yhteyden muodostaminen ClickUpiin epäonnistui';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return 'Yhteyden muodostaminen palveluun $serviceName epäonnistui: $error';
  }

  @override
  String get successfullyConnectedTodoist => 'Yhdistetty onnistuneesti Todoistiin!';

  @override
  String get failedToConnectTodoistRetry => 'Yhteyden muodostaminen Todoistiin epäonnistui. Yritä uudelleen.';

  @override
  String get successfullyConnectedAsana => 'Yhdistetty onnistuneesti Asanaan!';

  @override
  String get failedToConnectAsanaRetry => 'Yhteyden muodostaminen Asanaan epäonnistui. Yritä uudelleen.';

  @override
  String get successfullyConnectedGoogleTasks => 'Yhdistetty onnistuneesti Google Tasksiin!';

  @override
  String get failedToConnectGoogleTasksRetry => 'Yhteyden muodostaminen Google Tasksiin epäonnistui. Yritä uudelleen.';

  @override
  String get successfullyConnectedClickUp => 'Yhdistetty onnistuneesti ClickUpiin!';

  @override
  String get failedToConnectClickUpRetry => 'Yhteyden muodostaminen ClickUpiin epäonnistui. Yritä uudelleen.';

  @override
  String get successfullyConnectedNotion => 'Yhdistetty onnistuneesti Notioniin!';

  @override
  String get failedToRefreshNotionStatus => 'Notion-yhteyden tilan päivitys epäonnistui.';

  @override
  String get successfullyConnectedGoogle => 'Yhdistetty onnistuneesti Googleen!';

  @override
  String get failedToRefreshGoogleStatus => 'Google-yhteyden tilan päivitys epäonnistui.';

  @override
  String get successfullyConnectedWhoop => 'Yhdistetty onnistuneesti Whoopiin!';

  @override
  String get failedToRefreshWhoopStatus => 'Whoop-yhteyden tilan päivitys epäonnistui.';

  @override
  String get successfullyConnectedGitHub => 'Yhdistetty onnistuneesti GitHubiin!';

  @override
  String get failedToRefreshGitHubStatus => 'GitHub-yhteyden tilan päivitys epäonnistui.';

  @override
  String get authFailedToSignInWithGoogle => 'Kirjautuminen Googlella epäonnistui, yritä uudelleen.';

  @override
  String get authenticationFailed => 'Todennus epäonnistui. Yritä uudelleen.';

  @override
  String get authFailedToSignInWithApple => 'Kirjautuminen Applella epäonnistui, yritä uudelleen.';

  @override
  String get authFailedToRetrieveToken => 'Firebase-tunnuksen hakeminen epäonnistui, yritä uudelleen.';

  @override
  String get authUnexpectedErrorFirebase => 'Odottamaton virhe kirjautuessa, Firebase-virhe, yritä uudelleen.';

  @override
  String get authUnexpectedError => 'Odottamaton virhe kirjautuessa, yritä uudelleen';

  @override
  String get authFailedToLinkGoogle => 'Googleen linkittäminen epäonnistui, yritä uudelleen.';

  @override
  String get authFailedToLinkApple => 'Appleen linkittäminen epäonnistui, yritä uudelleen.';

  @override
  String get onboardingBluetoothRequired => 'Bluetooth-lupa vaaditaan laitteeseen yhdistämiseen.';

  @override
  String get onboardingBluetoothDeniedSystemPrefs => 'Bluetooth-lupa evätty. Myönnä lupa Järjestelmäasetuksissa.';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'Bluetooth-luvan tila: $status. Tarkista Järjestelmäasetukset.';
  }

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'Bluetooth-luvan tarkistus epäonnistui: $error';
  }

  @override
  String get onboardingNotificationDeniedSystemPrefs => 'Ilmoituslupa evätty. Myönnä lupa Järjestelmäasetuksissa.';

  @override
  String get onboardingNotificationDeniedNotifications =>
      'Ilmoituslupa evätty. Myönnä lupa kohdassa Järjestelmäasetukset > Ilmoitukset.';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return 'Ilmoitusluvan tila: $status. Tarkista Järjestelmäasetukset.';
  }

  @override
  String onboardingFailedCheckNotification(String error) {
    return 'Ilmoitusluvan tarkistus epäonnistui: $error';
  }

  @override
  String get onboardingLocationGrantInSettings =>
      'Myönnä sijaintilupa kohdassa Asetukset > Tietosuoja ja turvallisuus > Sijaintipalvelut';

  @override
  String get onboardingMicrophoneRequired => 'Mikrofonilupa vaaditaan tallennukseen.';

  @override
  String get onboardingMicrophoneDenied =>
      'Mikrofonilupa evätty. Myönnä lupa kohdassa Järjestelmäasetukset > Tietosuoja ja turvallisuus > Mikrofoni.';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'Mikrofoniluvam tila: $status. Tarkista Järjestelmäasetukset.';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'Mikrofoniluvam tarkistus epäonnistui: $error';
  }

  @override
  String get onboardingScreenCaptureRequired => 'Näytönkaappauslupa vaaditaan järjestelmä-äänen tallennukseen.';

  @override
  String get onboardingScreenCaptureDenied =>
      'Näytönkaappauslupa evätty. Myönnä lupa kohdassa Järjestelmäasetukset > Tietosuoja ja turvallisuus > Näytön tallennus.';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return 'Näytönkaappausluvan tila: $status. Tarkista Järjestelmäasetukset.';
  }

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return 'Näytönkaappausluvan tarkistus epäonnistui: $error';
  }

  @override
  String get onboardingAccessibilityRequired => 'Esteettömyyslupa vaaditaan selainkokouksten havaitsemiseen.';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'Esteettömyysluvan tila: $status. Tarkista Järjestelmäasetukset.';
  }

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'Esteettömyysluvan tarkistus epäonnistui: $error';
  }

  @override
  String get msgCameraNotAvailable => 'Kameran tallennus ei ole käytettävissä tällä alustalla';

  @override
  String get msgCameraPermissionDenied => 'Kameran käyttöoikeus evätty. Salli pääsy kameraan';

  @override
  String msgCameraAccessError(String error) {
    return 'Virhe kameraan pääsyssä: $error';
  }

  @override
  String get msgPhotoError => 'Virhe kuvan ottamisessa. Yritä uudelleen.';

  @override
  String get msgMaxImagesLimit => 'Voit valita enintään 4 kuvaa';

  @override
  String msgFilePickerError(String error) {
    return 'Virhe tiedostonvalitsimen avaamisessa: $error';
  }

  @override
  String msgSelectImagesError(String error) {
    return 'Virhe kuvien valinnassa: $error';
  }

  @override
  String get msgPhotosPermissionDenied => 'Kuvien käyttöoikeus evätty. Salli pääsy kuviin valitaksesi kuvia';

  @override
  String get msgSelectImagesGenericError => 'Virhe kuvien valinnassa. Yritä uudelleen.';

  @override
  String get msgMaxFilesLimit => 'Voit valita enintään 4 tiedostoa';

  @override
  String msgSelectFilesError(String error) {
    return 'Virhe tiedostojen valinnassa: $error';
  }

  @override
  String get msgSelectFilesGenericError => 'Virhe tiedostojen valinnassa. Yritä uudelleen.';

  @override
  String get msgUploadFileFailed => 'Tiedoston lataus epäonnistui, yritä myöhemmin uudelleen';

  @override
  String get msgReadingMemories => 'Luetaan muistojasi...';

  @override
  String get msgLearningMemories => 'Opitaan muistoistasi...';

  @override
  String get msgUploadAttachedFileFailed => 'Liitetiedoston lataus epäonnistui.';

  @override
  String captureRecordingError(String error) {
    return 'Tallennuksen aikana tapahtui virhe: $error';
  }

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return 'Tallennus pysähtyi: $reason. Saatat joutua yhdistämään ulkoiset näytöt uudelleen tai käynnistämään tallennuksen uudelleen.';
  }

  @override
  String get captureMicrophonePermissionRequired => 'Mikrofonin käyttöoikeus vaaditaan';

  @override
  String get captureMicrophonePermissionInSystemPreferences => 'Myönnä mikrofonin käyttöoikeus Järjestelmäasetuksissa';

  @override
  String get captureScreenRecordingPermissionRequired => 'Näytön tallennusoikeus vaaditaan';

  @override
  String get captureDisplayDetectionFailed => 'Näytön tunnistus epäonnistui. Tallennus pysäytetty.';

  @override
  String get devModeInvalidAudioBytesWebhookUrl => 'Virheellinen äänitavujen webhook-URL';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl => 'Virheellinen reaaliaikaisen transkription webhook-URL';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl => 'Virheellinen luodun keskustelun webhook-URL';

  @override
  String get devModeInvalidDaySummaryWebhookUrl => 'Virheellinen päiväyhteenvedon webhook-URL';

  @override
  String get devModeSettingsSaved => 'Asetukset tallennettu!';

  @override
  String get voiceFailedToTranscribe => 'Äänen litterointi epäonnistui';

  @override
  String get locationPermissionRequired => 'Sijaintilupa vaaditaan';

  @override
  String get locationPermissionContent =>
      'Nopea siirto vaatii sijaintiluvan WiFi-yhteyden tarkistamiseksi. Myönnä sijaintilupa jatkaaksesi.';

  @override
  String get pdfTranscriptExport => 'Litteraation vienti';

  @override
  String get pdfConversationExport => 'Keskustelun vienti';

  @override
  String pdfTitleLabel(String title) {
    return 'Otsikko: $title';
  }

  @override
  String get conversationNewIndicator => 'Uusi 🚀';

  @override
  String conversationPhotosCount(int count) {
    return '$count kuvaa';
  }

  @override
  String get mergingStatus => 'Yhdistetään...';

  @override
  String timeSecsSingular(int count) {
    return '$count sek';
  }

  @override
  String timeSecsPlural(int count) {
    return '$count sek';
  }

  @override
  String timeMinSingular(int count) {
    return '$count min';
  }

  @override
  String timeMinsPlural(int count) {
    return '$count min';
  }

  @override
  String timeMinsAndSecs(int mins, int secs) {
    return '$mins min $secs sek';
  }

  @override
  String timeHourSingular(int count) {
    return '$count tunti';
  }

  @override
  String timeHoursPlural(int count) {
    return '$count tuntia';
  }

  @override
  String timeHoursAndMins(int hours, int mins) {
    return '$hours tuntia $mins min';
  }

  @override
  String timeDaySingular(int count) {
    return '$count päivä';
  }

  @override
  String timeDaysPlural(int count) {
    return '$count päivää';
  }

  @override
  String timeDaysAndHours(int days, int hours) {
    return '$days päivää $hours tuntia';
  }

  @override
  String timeCompactSecs(int count) {
    return '${count}s';
  }

  @override
  String timeCompactMins(int count) {
    return '${count}m';
  }

  @override
  String timeCompactMinsAndSecs(int mins, int secs) {
    return '${mins}m ${secs}s';
  }

  @override
  String timeCompactHours(int count) {
    return '${count}t';
  }

  @override
  String timeCompactHoursAndMins(int hours, int mins) {
    return '${hours}t ${mins}m';
  }

  @override
  String get moveToFolder => 'Siirrä kansioon';

  @override
  String get noFoldersAvailable => 'Ei kansioita saatavilla';

  @override
  String get newFolder => 'Uusi kansio';

  @override
  String get color => 'Väri';

  @override
  String get waitingForDevice => 'Odotetaan laitetta...';

  @override
  String get saySomething => 'Sano jotain...';

  @override
  String get initialisingSystemAudio => 'Alustetaan järjestelmän ääntä';

  @override
  String get stopRecording => 'Lopeta nauhoitus';

  @override
  String get continueRecording => 'Jatka nauhoitusta';

  @override
  String get initialisingRecorder => 'Alustetaan tallenninta';

  @override
  String get pauseRecording => 'Keskeytä nauhoitus';

  @override
  String get resumeRecording => 'Jatka nauhoitusta';

  @override
  String get noDailyRecapsYet => 'Ei vielä päivittäisiä yhteenvetoja';

  @override
  String get dailyRecapsDescription => 'Päivittäiset yhteenvetosi näkyvät täällä, kun ne on luotu';

  @override
  String get chooseTransferMethod => 'Valitse siirtotapa';

  @override
  String get fastTransferSpeed => '~150 KB/s WiFin kautta';

  @override
  String largeTimeGapDetected(String gap) {
    return 'Havaittu suuri aikaväli ($gap)';
  }

  @override
  String largeTimeGapsDetected(String gaps) {
    return 'Havaittu suuria aikavälejä ($gaps)';
  }

  @override
  String get deviceDoesNotSupportWifiSwitchingToBle => 'Laite ei tue WiFi-synkronointia, vaihdetaan Bluetoothiin';

  @override
  String get appleHealthNotAvailable => 'Apple Health ei ole käytettävissä tässä laitteessa';

  @override
  String get downloadAudio => 'Lataa ääni';

  @override
  String get audioDownloadSuccess => 'Ääni ladattu onnistuneesti';

  @override
  String get audioDownloadFailed => 'Äänen lataus epäonnistui';

  @override
  String get downloadingAudio => 'Ladataan ääntä...';

  @override
  String get shareAudio => 'Jaa ääni';

  @override
  String get preparingAudio => 'Valmistellaan ääntä';

  @override
  String get gettingAudioFiles => 'Haetaan äänitiedostoja...';

  @override
  String get downloadingAudioProgress => 'Ladataan ääntä';

  @override
  String get processingAudio => 'Käsitellään ääntä';

  @override
  String get combiningAudioFiles => 'Yhdistetään äänitiedostoja...';

  @override
  String get audioReady => 'Ääni valmis';

  @override
  String get openingShareSheet => 'Avataan jakamisnäyttöä...';

  @override
  String get audioShareFailed => 'Jakaminen epäonnistui';

  @override
  String get dailyRecaps => 'Päivittäiset Yhteenvedot';

  @override
  String get removeFilter => 'Poista Suodatin';

  @override
  String get categoryConversationAnalysis => 'Keskusteluanalyysi';

  @override
  String get categoryPersonalityClone => 'Persoonallisuusklooni';

  @override
  String get categoryHealth => 'Terveys';

  @override
  String get categoryEducation => 'Koulutus';

  @override
  String get categoryCommunication => 'Viestintä';

  @override
  String get categoryEmotionalSupport => 'Tunnetuki';

  @override
  String get categoryProductivity => 'Tuottavuus';

  @override
  String get categoryEntertainment => 'Viihde';

  @override
  String get categoryFinancial => 'Talous';

  @override
  String get categoryTravel => 'Matkailu';

  @override
  String get categorySafety => 'Turvallisuus';

  @override
  String get categoryShopping => 'Ostokset';

  @override
  String get categorySocial => 'Sosiaalinen';

  @override
  String get categoryNews => 'Uutiset';

  @override
  String get categoryUtilities => 'Työkalut';

  @override
  String get categoryOther => 'Muut';

  @override
  String get capabilityChat => 'Chat';

  @override
  String get capabilityConversations => 'Keskustelut';

  @override
  String get capabilityExternalIntegration => 'Ulkoinen integraatio';

  @override
  String get capabilityNotification => 'Ilmoitus';

  @override
  String get triggerAudioBytes => 'Äänitavut';

  @override
  String get triggerConversationCreation => 'Keskustelun luominen';

  @override
  String get triggerTranscriptProcessed => 'Litterointi käsitelty';

  @override
  String get actionCreateConversations => 'Luo keskusteluja';

  @override
  String get actionCreateMemories => 'Luo muistoja';

  @override
  String get actionReadConversations => 'Lue keskusteluja';

  @override
  String get actionReadMemories => 'Lue muistoja';

  @override
  String get actionReadTasks => 'Lue tehtäviä';

  @override
  String get scopeUserName => 'Käyttäjänimi';

  @override
  String get scopeUserFacts => 'Käyttäjän tiedot';

  @override
  String get scopeUserConversations => 'Käyttäjän keskustelut';

  @override
  String get scopeUserChat => 'Käyttäjän chat';

  @override
  String get capabilitySummary => 'Yhteenveto';

  @override
  String get capabilityFeatured => 'Suositellut';

  @override
  String get capabilityTasks => 'Tehtävät';

  @override
  String get capabilityIntegrations => 'Integraatiot';

  @override
  String get categoryPersonalityClones => 'Persoonallisuuskloonit';

  @override
  String get categoryProductivityLifestyle => 'Tuottavuus ja elämäntapa';

  @override
  String get categorySocialEntertainment => 'Sosiaalinen ja viihde';

  @override
  String get categoryProductivityTools => 'Tuottavuustyökalut';

  @override
  String get categoryPersonalWellness => 'Henkilökohtainen hyvinvointi';

  @override
  String get rating => 'Arvio';

  @override
  String get categories => 'Kategoriat';

  @override
  String get sortBy => 'Lajittele';

  @override
  String get highestRating => 'Korkein arvio';

  @override
  String get lowestRating => 'Matalin arvio';

  @override
  String get resetFilters => 'Nollaa suodattimet';

  @override
  String get applyFilters => 'Käytä suodattimia';

  @override
  String get mostInstalls => 'Eniten asennuksia';

  @override
  String get couldNotOpenUrl => 'URL-osoitetta ei voitu avata. Yritä uudelleen.';

  @override
  String get newTask => 'Uusi tehtävä';

  @override
  String get viewAll => 'Näytä kaikki';

  @override
  String get addTask => 'Lisää tehtävä';

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
  String get audioPlaybackUnavailable => 'Äänitiedosto ei ole saatavilla toistettavaksi';

  @override
  String get audioPlaybackFailed => 'Ääntä ei voi toistaa. Tiedosto saattaa olla vioittunut tai puuttua.';

  @override
  String get connectionGuide => 'Yhteysopas';

  @override
  String get iveDoneThis => 'Olen tehnyt tämän';

  @override
  String get pairNewDevice => 'Yhdistä uusi laite';

  @override
  String get dontSeeYourDevice => 'Etkö näe laitettasi?';

  @override
  String get reportAnIssue => 'Ilmoita ongelmasta';

  @override
  String get pairingTitleOmi => 'Käynnistä Omi';

  @override
  String get pairingDescOmi => 'Pidä laitetta painettuna, kunnes se värisee, käynnistääksesi sen.';

  @override
  String get pairingTitleOmiDevkit => 'Aseta Omi DevKit pariliitostilaan';

  @override
  String get pairingDescOmiDevkit =>
      'Paina painiketta kerran käynnistääksesi. LED vilkkuu violettina pariliitostilassa.';

  @override
  String get pairingTitleOmiGlass => 'Käynnistä Omi Glass';

  @override
  String get pairingDescOmiGlass => 'Pidä sivupainiketta painettuna 3 sekuntia käynnistääksesi.';

  @override
  String get pairingTitlePlaudNote => 'Aseta Plaud Note pariliitostilaan';

  @override
  String get pairingDescPlaudNote =>
      'Pidä sivupainiketta painettuna 2 sekuntia. Punainen LED vilkkuu, kun se on valmis pariliitokseen.';

  @override
  String get pairingTitleBee => 'Aseta Bee pariliitostilaan';

  @override
  String get pairingDescBee => 'Paina painiketta 5 kertaa peräkkäin. Valo alkaa vilkkua sinisenä ja vihreänä.';

  @override
  String get pairingTitleLimitless => 'Aseta Limitless pariliitostilaan';

  @override
  String get pairingDescLimitless =>
      'Kun mikä tahansa valo on näkyvissä, paina kerran ja paina sitten pitkään, kunnes laite näyttää vaaleanpunaista valoa, vapauta sitten.';

  @override
  String get pairingTitleFriendPendant => 'Aseta Friend Pendant pariliitostilaan';

  @override
  String get pairingDescFriendPendant =>
      'Paina riipuksen painiketta käynnistääksesi sen. Se siirtyy automaattisesti pariliitostilaan.';

  @override
  String get pairingTitleFieldy => 'Aseta Fieldy pariliitostilaan';

  @override
  String get pairingDescFieldy => 'Pidä laitetta painettuna, kunnes valo syttyy, käynnistääksesi sen.';

  @override
  String get pairingTitleAppleWatch => 'Yhdistä Apple Watch';

  @override
  String get pairingDescAppleWatch =>
      'Asenna ja avaa Omi-sovellus Apple Watchissasi, napauta sitten Yhdistä sovelluksessa.';

  @override
  String get pairingTitleNeoOne => 'Aseta Neo One pariliitostilaan';

  @override
  String get pairingDescNeoOne => 'Pidä virtapainiketta painettuna, kunnes LED vilkkuu. Laite on löydettävissä.';
}
