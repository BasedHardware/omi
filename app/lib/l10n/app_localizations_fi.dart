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
  String get noInternetConnection => 'Tarkista internet-yhteytesi ja yritä uudelleen.';

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
  String get searching => 'Etsitään';

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
  String get noConversationsYet => 'Ei vielä keskusteluja.';

  @override
  String get noStarredConversations => 'Ei vielä tähdellä merkittyjä keskusteluja.';

  @override
  String get starConversationHint => 'Merkitäksesi keskustelun tähdellä, avaa se ja napauta tähti-kuvaketta otsikossa.';

  @override
  String get searchConversations => 'Etsi keskusteluja';

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
  String get messageCopied => 'Viesti kopioitu leikepöydälle.';

  @override
  String get cannotReportOwnMessage => 'Et voi ilmoittaa omista viesteistäsi.';

  @override
  String get reportMessage => 'Ilmoita viestistä';

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
  String get searchApps => 'Etsi yli 1500 sovelluksesta';

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
  String get visitWebsite => 'Käy verkkosivulla';

  @override
  String get helpOrInquiries => 'Apua tai kysymyksiä?';

  @override
  String get joinCommunity => 'Liity yhteisöön!';

  @override
  String get membersAndCounting => 'Yli 8000 jäsentä ja kasvaa.';

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
  String get customVocabulary => 'Mukautettu sanasto';

  @override
  String get identifyingOthers => 'Muiden tunnistaminen';

  @override
  String get paymentMethods => 'Maksutavat';

  @override
  String get conversationDisplay => 'Keskustelunäkymä';

  @override
  String get dataPrivacy => 'Tiedot ja yksityisyys';

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
  String get signOut => 'Kirjaudu ulos';

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
  String get deviceId => 'Laitetunnus';

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
  String get unpairDevice => 'Pura laitepari';

  @override
  String get unpairAndForget => 'Pura laitepari ja unohda laite';

  @override
  String get deviceDisconnectedMessage => 'Omin yhteys on katkaistu 😔';

  @override
  String get deviceUnpairedMessage =>
      'Laitepari purettu. Siirry kohtaan Asetukset > Bluetooth ja unohda laite viimeistelläksesi purkamisen.';

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
  String get createKey => 'Luo avain';

  @override
  String get docs => 'Dokumentit';

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
  String get upgradeToUnlimited => 'Päivitä rajoittamattomaan';

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
  String get debugLogs => 'Vianjäljityslokit';

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
  String get knowledgeGraphDeleted => 'Tietograafi poistettu onnistuneesti';

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
  String get insights => 'Näkemykset';

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
  String get enterYourName => 'Kirjoita nimesi';

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
  String get yesterday => 'eilen';

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
  String get resetToDefault => 'Palauta oletuksiin';

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
  String get makePublic => 'Tee julkiseksi';

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
  String get grantPermissions => 'Myönnä käyttöoikeudet';

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
  String get whatsYourName => 'Mikä nimesi on?';

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
  String get deleteActionItemTitle => 'Poista tehtävä';

  @override
  String get deleteActionItemMessage => 'Haluatko varmasti poistaa tämän tehtävän?';

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
  String searchMemories(int count) {
    return 'Etsi $count muistoa';
  }

  @override
  String get memoryDeleted => 'Muisto poistettu.';

  @override
  String get undo => 'Kumoa';

  @override
  String get noMemoriesYet => 'Ei vielä muistoja';

  @override
  String get noAutoMemories => 'Ei vielä automaattisesti poimittuja muistoja';

  @override
  String get noManualMemories => 'Ei vielä manuaalisia muistoja';

  @override
  String get noMemoriesInCategories => 'Ei muistoja näissä kategorioissa';

  @override
  String get noMemoriesFound => 'Muistoja ei löytynyt';

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
  String get newMemory => 'Uusi muisto';

  @override
  String get editMemory => 'Muokkaa muistoa';

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
  String get dueDate => 'Eräpäivä';

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
  String get completed => 'Suoritettu';

  @override
  String get markComplete => 'Merkitse suoritetuksi';

  @override
  String get actionItemDeleted => 'Tehtävä poistettu';

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
}
