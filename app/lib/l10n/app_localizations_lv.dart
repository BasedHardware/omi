// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Latvian (`lv`).
class AppLocalizationsLv extends AppLocalizations {
  AppLocalizationsLv([String locale = 'lv']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'Saruna';

  @override
  String get transcriptTab => 'Transkripcija';

  @override
  String get actionItemsTab => 'Uzdevumi';

  @override
  String get deleteConversationTitle => 'Dzēst sarunu?';

  @override
  String get deleteConversationMessage => 'Vai tiešām vēlaties dzēst šo sarunu? Šo darbību nevar atsaukt.';

  @override
  String get confirm => 'Apstiprināt';

  @override
  String get cancel => 'Atcelt';

  @override
  String get ok => 'Labi';

  @override
  String get delete => 'Dzēst';

  @override
  String get add => 'Pievienot';

  @override
  String get update => 'Atjaunināt';

  @override
  String get save => 'Saglabāt';

  @override
  String get edit => 'Rediģēt';

  @override
  String get close => 'Aizvērt';

  @override
  String get clear => 'Notīrīt';

  @override
  String get copyTranscript => 'Kopēt transkripciju';

  @override
  String get copySummary => 'Kopēt kopsavilkumu';

  @override
  String get testPrompt => 'Testēt uzvedni';

  @override
  String get reprocessConversation => 'Pārstrādāt sarunu';

  @override
  String get deleteConversation => 'Dzēst sarunu';

  @override
  String get contentCopied => 'Saturs nokopēts starpliktuvē';

  @override
  String get failedToUpdateStarred => 'Neizdevās atjaunināt zvaigznītes statusu.';

  @override
  String get conversationUrlNotShared => 'Sarunas URL nevarēja kopīgot.';

  @override
  String get errorProcessingConversation => 'Kļūda, apstrādājot sarunu. Lūdzu, mēģiniet vēlreiz vēlāk.';

  @override
  String get noInternetConnection => 'Nav interneta savienojuma';

  @override
  String get unableToDeleteConversation => 'Nevar dzēst sarunu';

  @override
  String get somethingWentWrong => 'Kaut kas nogāja greizi! Lūdzu, mēģiniet vēlreiz vēlāk.';

  @override
  String get copyErrorMessage => 'Kopēt kļūdas ziņojumu';

  @override
  String get errorCopied => 'Kļūdas ziņojums nokopēts starpliktuvē';

  @override
  String get remaining => 'Atlikušais';

  @override
  String get loading => 'Ielādē...';

  @override
  String get loadingDuration => 'Ielādē ilgumu...';

  @override
  String secondsCount(int count) {
    return '$count sekundes';
  }

  @override
  String get people => 'Cilvēki';

  @override
  String get addNewPerson => 'Pievienot jaunu personu';

  @override
  String get editPerson => 'Rediģēt personu';

  @override
  String get createPersonHint => 'Izveidojiet jaunu personu un apmāciet Omi atpazīt arī viņu runu!';

  @override
  String get speechProfile => 'Runas profils';

  @override
  String sampleNumber(int number) {
    return 'Paraugs $number';
  }

  @override
  String get settings => 'Iestatījumi';

  @override
  String get language => 'Valoda';

  @override
  String get selectLanguage => 'Izvēlēties valodu';

  @override
  String get deleting => 'Dzēš...';

  @override
  String get pleaseCompleteAuthentication =>
      'Lūdzu, pabeidziet autentifikāciju savā pārlūkprogrammā. Kad esat pabeidzis, atgriezieties lietotnē.';

  @override
  String get failedToStartAuthentication => 'Neizdevās sākt autentifikāciju';

  @override
  String get importStarted => 'Importēšana sākta! Jūs saņemsiet paziņojumu, kad tā būs pabeigta.';

  @override
  String get failedToStartImport => 'Neizdevās sākt importēšanu. Lūdzu, mēģiniet vēlreiz.';

  @override
  String get couldNotAccessFile => 'Nevarēja piekļūt atlasītajam failam';

  @override
  String get askOmi => 'Jautāt Omi';

  @override
  String get done => 'Gatavs';

  @override
  String get disconnected => 'Atvienots';

  @override
  String get searching => 'Meklē...';

  @override
  String get connectDevice => 'Savienot ierīci';

  @override
  String get monthlyLimitReached => 'Jūs esat sasniedzis mēneša limitu.';

  @override
  String get checkUsage => 'Pārbaudīt lietojumu';

  @override
  String get syncingRecordings => 'Sinhronizē ierakstus';

  @override
  String get recordingsToSync => 'Ieraksti, kas jāsinhronizē';

  @override
  String get allCaughtUp => 'Viss ir sinhronizēts';

  @override
  String get sync => 'Sinhronizēt';

  @override
  String get pendantUpToDate => 'Kulons ir atjaunināts';

  @override
  String get allRecordingsSynced => 'Visi ieraksti ir sinhronizēti';

  @override
  String get syncingInProgress => 'Notiek sinhronizācija';

  @override
  String get readyToSync => 'Gatavs sinhronizācijai';

  @override
  String get tapSyncToStart => 'Piespiediet Sinhronizēt, lai sāktu';

  @override
  String get pendantNotConnected => 'Kulons nav savienots. Savienojiet, lai sinhronizētu.';

  @override
  String get everythingSynced => 'Viss jau ir sinhronizēts.';

  @override
  String get recordingsNotSynced => 'Jums ir ieraksti, kas vēl nav sinhronizēti.';

  @override
  String get syncingBackground => 'Mēs turpināsim sinhronizēt jūsu ierakstus fonā.';

  @override
  String get noConversationsYet => 'Pagaidām nav sarunu';

  @override
  String get noStarredConversations => 'Vēl nav atzīmētu sarunu.';

  @override
  String get starConversationHint =>
      'Lai atzīmētu sarunu ar zvaigznīti, atveriet to un piespiediet zvaigznītes ikonu galvenē.';

  @override
  String get searchConversations => 'Meklēt sarunas...';

  @override
  String selectedCount(int count, Object s) {
    return '$count atlasīts';
  }

  @override
  String get merge => 'Apvienot';

  @override
  String get mergeConversations => 'Apvienot sarunas';

  @override
  String mergeConversationsMessage(int count) {
    return 'Tas apvienos $count sarunas vienā. Viss saturs tiks apvienots un ģenerēts no jauna.';
  }

  @override
  String get mergingInBackground => 'Apvieno fonā. Tas var aizņemt brīdi.';

  @override
  String get failedToStartMerge => 'Neizdevās sākt apvienošanu';

  @override
  String get askAnything => 'Jautājiet jebko';

  @override
  String get noMessagesYet => 'Vēl nav ziņojumu!\nKāpēc nesākt sarunu?';

  @override
  String get deletingMessages => 'Dzēš jūsu ziņojumus no Omi atmiņas...';

  @override
  String get messageCopied => 'Ziņojums nokopēts starpliktuvē.';

  @override
  String get cannotReportOwnMessage => 'Jūs nevarat ziņot par saviem ziņojumiem.';

  @override
  String get reportMessage => 'Ziņot par ziņojumu';

  @override
  String get reportMessageConfirm => 'Vai tiešām vēlaties ziņot par šo ziņojumu?';

  @override
  String get messageReported => 'Ziņojums veiksmīgi ziņots.';

  @override
  String get thankYouFeedback => 'Paldies par jūsu atsauksmēm!';

  @override
  String get clearChat => 'Notīrīt tērzēšanu?';

  @override
  String get clearChatConfirm => 'Vai tiešām vēlaties notīrīt tērzēšanu? Šo darbību nevar atsaukt.';

  @override
  String get maxFilesLimit => 'Vienlaikus var augšupielādēt tikai 4 failus';

  @override
  String get chatWithOmi => 'Tērzēt ar Omi';

  @override
  String get apps => 'Lietotnes';

  @override
  String get noAppsFound => 'Lietotnes nav atrastas';

  @override
  String get tryAdjustingSearch => 'Mēģiniet pielāgot meklēšanu vai filtrus';

  @override
  String get createYourOwnApp => 'Izveidojiet savu lietotni';

  @override
  String get buildAndShareApp => 'Izveidojiet un kopīgojiet savu pielāgoto lietotni';

  @override
  String get searchApps => 'Meklēt lietotnes...';

  @override
  String get myApps => 'Manas lietotnes';

  @override
  String get installedApps => 'Instalētās lietotnes';

  @override
  String get unableToFetchApps =>
      'Nevar ielādēt lietotnes :(\n\nLūdzu, pārbaudiet interneta savienojumu un mēģiniet vēlreiz.';

  @override
  String get aboutOmi => 'Par Omi';

  @override
  String get privacyPolicy => 'Privātuma politika';

  @override
  String get visitWebsite => 'Apmeklēt vietni';

  @override
  String get helpOrInquiries => 'Palīdzība vai jautājumi?';

  @override
  String get joinCommunity => 'Pievienojieties kopienai!';

  @override
  String get membersAndCounting => '8000+ biedri un turpina pieaugt.';

  @override
  String get deleteAccountTitle => 'Dzēst kontu';

  @override
  String get deleteAccountConfirm => 'Vai tiešām vēlaties dzēst savu kontu?';

  @override
  String get cannotBeUndone => 'To nevar atsaukt.';

  @override
  String get allDataErased => 'Visas jūsu atmiņas un sarunas tiks neatgriezeniski dzēstas.';

  @override
  String get appsDisconnected => 'Jūsu lietotnes un integrācijas tiks atsavi notas nekavējoties.';

  @override
  String get exportBeforeDelete =>
      'Jūs varat eksportēt savus datus pirms konta dzēšanas, bet pēc dzēšanas tos vairs nevarēs atjaunot.';

  @override
  String get deleteAccountCheckbox =>
      'Es saprotu, ka konta dzēšana ir neatgriezeniska un visi dati, tostarp atmiņas un sarunas, tiks zaudēti un tos nevarēs atgūt.';

  @override
  String get areYouSure => 'Vai esat pārliecināts?';

  @override
  String get deleteAccountFinal =>
      'Šī darbība ir neatgriezeniska un neatgriezeniski izdzēsīs jūsu kontu un visus saistītos datus. Vai tiešām vēlaties turpināt?';

  @override
  String get deleteNow => 'Dzēst tagad';

  @override
  String get goBack => 'Atgriezties';

  @override
  String get checkBoxToConfirm =>
      'Atzīmējiet izvēles rūtiņu, lai apstiprinātu, ka saprotat, ka konta dzēšana ir neatgriezeniska un neatceļama.';

  @override
  String get profile => 'Profils';

  @override
  String get name => 'Vārds';

  @override
  String get email => 'E-pasts';

  @override
  String get customVocabulary => 'Pielāgota vārdnīca';

  @override
  String get identifyingOthers => 'Citu identificēšana';

  @override
  String get paymentMethods => 'Maksājumu metodes';

  @override
  String get conversationDisplay => 'Sarunas attēlojums';

  @override
  String get dataPrivacy => 'Dati un privātums';

  @override
  String get userId => 'Lietotāja ID';

  @override
  String get notSet => 'Nav iestatīts';

  @override
  String get userIdCopied => 'Lietotāja ID nokopēts starpliktuvē';

  @override
  String get systemDefault => 'Sistēmas noklusējuma';

  @override
  String get planAndUsage => 'Plāns un lietojums';

  @override
  String get offlineSync => 'Bezsaistes sinhronizācija';

  @override
  String get deviceSettings => 'Ierīces iestatījumi';

  @override
  String get chatTools => 'Tērzēšanas rīki';

  @override
  String get feedbackBug => 'Atsauksmes / Kļūda';

  @override
  String get helpCenter => 'Palīdzības centrs';

  @override
  String get developerSettings => 'Izstrādātāja iestatījumi';

  @override
  String get getOmiForMac => 'Iegūt Omi priekš Mac';

  @override
  String get referralProgram => 'Ieteikšanas programma';

  @override
  String get signOut => 'Izrakstīties';

  @override
  String get appAndDeviceCopied => 'Lietotnes un ierīces informācija nokopēta';

  @override
  String get wrapped2025 => '2025. gada apskats';

  @override
  String get yourPrivacyYourControl => 'Jūsu privātums, jūsu kontrole';

  @override
  String get privacyIntro =>
      'Omi mēs esam apņēmušies aizsargāt jūsu privātumu. Šī lapa ļauj jums kontrolēt, kā jūsu dati tiek uzglabāti un izmantoti.';

  @override
  String get learnMore => 'Uzzināt vairāk...';

  @override
  String get dataProtectionLevel => 'Datu aizsardzības līmenis';

  @override
  String get dataProtectionDesc =>
      'Jūsu dati pēc noklusējuma ir aizsargāti ar spēcīgu šifrēšanu. Pārskatiet savus iestatījumus un turpmākās privātuma opcijas zemāk.';

  @override
  String get appAccess => 'Lietotņu piekļuve';

  @override
  String get appAccessDesc =>
      'Šādas lietotnes var piekļūt jūsu datiem. Piespiediet uz lietotnes, lai pārvaldītu tās atļaujas.';

  @override
  String get noAppsExternalAccess => 'Nevienai instalētajai lietotnei nav ārējas piekļuves jūsu datiem.';

  @override
  String get deviceName => 'Ierīces nosaukums';

  @override
  String get deviceId => 'Ierīces ID';

  @override
  String get firmware => 'Programmaparatūra';

  @override
  String get sdCardSync => 'SD kartes sinhronizācija';

  @override
  String get hardwareRevision => 'Aparatūras versija';

  @override
  String get modelNumber => 'Modeļa numurs';

  @override
  String get manufacturer => 'Ražotājs';

  @override
  String get doubleTap => 'Dubultklikšķis';

  @override
  String get ledBrightness => 'LED spilgtums';

  @override
  String get micGain => 'Mikrofona pastiprinājums';

  @override
  String get disconnect => 'Atvienot';

  @override
  String get forgetDevice => 'Aizmirst ierīci';

  @override
  String get chargingIssues => 'Uzlādes problēmas';

  @override
  String get disconnectDevice => 'Atvienot ierīci';

  @override
  String get unpairDevice => 'Atvienot ierīces sapārošanu';

  @override
  String get unpairAndForget => 'Atpārošana un aizmirst ierīci';

  @override
  String get deviceDisconnectedMessage => 'Jūsu Omi ir atvienots 😔';

  @override
  String get deviceUnpairedMessage =>
      'Ierīce atvienota. Dodieties uz Iestatījumi > Bluetooth un aizmirstiet ierīci, lai pabeigtu sapārošanas atcelšanu.';

  @override
  String get unpairDialogTitle => 'Atpārošana ierīci';

  @override
  String get unpairDialogMessage =>
      'Tas atpāros ierīci, lai to varētu savienot ar citu tālruni. Jums būs jādodas uz Iestatījumi > Bluetooth un jāaizmirst ierīce, lai pabeigtu procesu.';

  @override
  String get deviceNotConnected => 'Ierīce nav savienota';

  @override
  String get connectDeviceMessage => 'Savienojiet savu Omi ierīci, lai piekļūtu\nierīces iestatījumiem un pielāgošanai';

  @override
  String get deviceInfoSection => 'Ierīces informācija';

  @override
  String get customizationSection => 'Pielāgošana';

  @override
  String get hardwareSection => 'Aparatūra';

  @override
  String get v2Undetected => 'V2 nav atklāts';

  @override
  String get v2UndetectedMessage =>
      'Redzam, ka jums ir V1 ierīce vai jūsu ierīce nav savienota. SD kartes funkcionalitāte ir pieejama tikai V2 ierīcēm.';

  @override
  String get endConversation => 'Beigt sarunu';

  @override
  String get pauseResume => 'Pauze/Atsākt';

  @override
  String get starConversation => 'Atzīmēt sarunu ar zvaigznīti';

  @override
  String get doubleTapAction => 'Dubultklikšķa darbība';

  @override
  String get endAndProcess => 'Beigt un apstrādāt sarunu';

  @override
  String get pauseResumeRecording => 'Apturēt/atsākt ierakstīšanu';

  @override
  String get starOngoing => 'Atzīmēt notiekošo sarunu ar zvaigznīti';

  @override
  String get off => 'Izslēgts';

  @override
  String get max => 'Maks.';

  @override
  String get mute => 'Apklusināt';

  @override
  String get quiet => 'Kluss';

  @override
  String get normal => 'Normāls';

  @override
  String get high => 'Augsts';

  @override
  String get micGainDescMuted => 'Mikrofons ir apklusināts';

  @override
  String get micGainDescLow => 'Ļoti kluss - skaļām vidēm';

  @override
  String get micGainDescModerate => 'Kluss - mērenai trokšņu videi';

  @override
  String get micGainDescNeutral => 'Neitrāls - līdzsvarots ieraksts';

  @override
  String get micGainDescSlightlyBoosted => 'Nedaudz pastiprināts - parastas izmantošanas';

  @override
  String get micGainDescBoosted => 'Pastiprināts - klusām vidēm';

  @override
  String get micGainDescHigh => 'Augsts - tālām vai klus ām balsīm';

  @override
  String get micGainDescVeryHigh => 'Ļoti augsts - ļoti klusiem avotiem';

  @override
  String get micGainDescMax => 'Maksimālais - lietot piesardzīgi';

  @override
  String get developerSettingsTitle => 'Izstrādātāja iestatījumi';

  @override
  String get saving => 'Saglabā...';

  @override
  String get personaConfig => 'Konfigurēt savu AI personību';

  @override
  String get beta => 'BETA';

  @override
  String get transcription => 'Transkripcija';

  @override
  String get transcriptionConfig => 'Konfigurēt STT pakalpojumu sniedzēju';

  @override
  String get conversationTimeout => 'Sarunas taimauts';

  @override
  String get conversationTimeoutConfig => 'Iestatīt, kad sarunas automātiski beidzas';

  @override
  String get importData => 'Importēt datus';

  @override
  String get importDataConfig => 'Importēt datus no citiem avotiem';

  @override
  String get debugDiagnostics => 'Atkļūdošana un diagnostika';

  @override
  String get endpointUrl => 'Galapunkta URL';

  @override
  String get noApiKeys => 'Vēl nav API atslēgu';

  @override
  String get createKeyToStart => 'Izveidojiet atslēgu, lai sāktu';

  @override
  String get createKey => 'Izveidot atslēgu';

  @override
  String get docs => 'Dokumentācija';

  @override
  String get yourOmiInsights => 'Jūsu Omi ieskati';

  @override
  String get today => 'Šodien';

  @override
  String get thisMonth => 'Šomēnes';

  @override
  String get thisYear => 'Šogad';

  @override
  String get allTime => 'Visu laiku';

  @override
  String get noActivityYet => 'Vēl nav aktivitātes';

  @override
  String get startConversationToSeeInsights => 'Sāciet sarunu ar Omi,\nlai šeit redzētu lietošanas statistiku.';

  @override
  String get listening => 'Klausās';

  @override
  String get listeningSubtitle => 'Kopējais laiks, ko Omi aktīvi klausījies.';

  @override
  String get understanding => 'Saprot';

  @override
  String get understandingSubtitle => 'Vārdi, kas saprasti no jūsu sarunām.';

  @override
  String get providing => 'Sniedz';

  @override
  String get providingSubtitle => 'Uzdevumi un piezīmes, kas automātiski fiksēti.';

  @override
  String get remembering => 'Atceras';

  @override
  String get rememberingSubtitle => 'Fakti un detaļas, kas atcerētas jums.';

  @override
  String get unlimitedPlan => 'Neierobežots plāns';

  @override
  String get managePlan => 'Pārvaldīt plānu';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'Jūsu plāns tiks atcelts $date.';
  }

  @override
  String renewsOn(String date) {
    return 'Jūsu plāns atjaunojas $date.';
  }

  @override
  String get basicPlan => 'Bezmaksas plāns';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used no $limit min izmantots';
  }

  @override
  String get upgrade => 'Jaunināt';

  @override
  String get upgradeToUnlimited => 'Jauniniet uz neierobežotu';

  @override
  String basicPlanDesc(int limit) {
    return 'Jūsu plāns ietver $limit bezmaksas minūtes mēnesī. Jauniniet, lai iegūtu neierobežotu.';
  }

  @override
  String get shareStatsMessage => 'Dalījums ar manu Omi statistiku! (omi.me - jūsu vienmēr ieslēgtais AI asistents)';

  @override
  String get sharePeriodToday => 'Šodien omi ir:';

  @override
  String get sharePeriodMonth => 'Šomēnes omi ir:';

  @override
  String get sharePeriodYear => 'Šogad omi ir:';

  @override
  String get sharePeriodAllTime => 'Līdz šim omi ir:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 Klausījies $minutes minūtes';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 Sapratis $words vārdus';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ Sniedzis $count ieskatus';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 Atcerējies $count atmiņas';
  }

  @override
  String get debugLogs => 'Atkļūdošanas žurnāli';

  @override
  String get debugLogsAutoDelete => 'Automātiski izdzēš pēc 3 dienām.';

  @override
  String get debugLogsDesc => 'Palīdz diagnosticēt problēmas';

  @override
  String get noLogFilesFound => 'Žurnāla faili nav atrasti.';

  @override
  String get omiDebugLog => 'Omi atkļūdošanas žurnāls';

  @override
  String get logShared => 'Žurnāls kopīgots';

  @override
  String get selectLogFile => 'Izvēlēties žurnāla failu';

  @override
  String get shareLogs => 'Kopīgot žurnālus';

  @override
  String get debugLogCleared => 'Atkļūdošanas žurnāls notīrīts';

  @override
  String get exportStarted => 'Eksports sākts. Tas var aizņemt dažas sekundes...';

  @override
  String get exportAllData => 'Eksportēt visus datus';

  @override
  String get exportDataDesc => 'Eksportēt sarunas uz JSON failu';

  @override
  String get exportedConversations => 'Eksportētās sarunas no Omi';

  @override
  String get exportShared => 'Eksports kopīgots';

  @override
  String get deleteKnowledgeGraphTitle => 'Dzēst zināšanu grafu?';

  @override
  String get deleteKnowledgeGraphMessage =>
      'Tas izdzēsīs visus atvasinātos zināšanu grafa datus (mezglus un savienojumus). Jūsu oriģinālās atmiņas paliks drošībā. Grafs tiks atjaunots ar laiku vai pēc nākamā pieprasījuma.';

  @override
  String get knowledgeGraphDeleted => 'Zināšanu grafs veiksmīgi izdzēsts';

  @override
  String deleteGraphFailed(String error) {
    return 'Neizdevās dzēst grafu: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'Dzēst zināšanu grafu';

  @override
  String get deleteKnowledgeGraphDesc => 'Notīrīt visus mezglus un savienojumus';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'MCP serveris';

  @override
  String get mcpServerDesc => 'Savienojiet AI asistentus ar jūsu datiem';

  @override
  String get serverUrl => 'Servera URL';

  @override
  String get urlCopied => 'URL nokopēts';

  @override
  String get apiKeyAuth => 'API atslēgas autentifikācija';

  @override
  String get header => 'Galvene';

  @override
  String get authorizationBearer => 'Autorizācija: Bearer <atslēga>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'Klienta ID';

  @override
  String get clientSecret => 'Klienta noslēpums';

  @override
  String get useMcpApiKey => 'Izmantojiet savu MCP API atslēgu';

  @override
  String get webhooks => 'Tīmekļa āķi';

  @override
  String get conversationEvents => 'Sarunas notikumi';

  @override
  String get newConversationCreated => 'Jauna saruna izveidota';

  @override
  String get realtimeTranscript => 'Reāllaika transkripcija';

  @override
  String get transcriptReceived => 'Transkripcija saņemta';

  @override
  String get audioBytes => 'Audio baiti';

  @override
  String get audioDataReceived => 'Audio dati saņemti';

  @override
  String get intervalSeconds => 'Intervāls (sekundes)';

  @override
  String get daySummary => 'Dienas kopsavilkums';

  @override
  String get summaryGenerated => 'Kopsavilkums izveidots';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'Pievienot claude_desktop_config.json';

  @override
  String get copyConfig => 'Kopēt konfigurāciju';

  @override
  String get configCopied => 'Konfigurācija nokopēta starpliktuvē';

  @override
  String get listeningMins => 'Klausās (min)';

  @override
  String get understandingWords => 'Saprot (vārdi)';

  @override
  String get insights => 'Ieskati';

  @override
  String get memories => 'Atmiņas';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '$used no $limit min izmantots šomēnes';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '$used no $limit vārdiem izmantots šomēnes';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '$used no $limit ieskatiem iegūts šomēnes';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return '$used no $limit atmiņām izveidots šomēnes';
  }

  @override
  String get visibility => 'Redzamība';

  @override
  String get visibilitySubtitle => 'Kontrolējiet, kuras sarunas parādās jūsu sarakstā';

  @override
  String get showShortConversations => 'Rādīt īsas sarunas';

  @override
  String get showShortConversationsDesc => 'Attēlot sarunas, kas ir īsākas par slieksni';

  @override
  String get showDiscardedConversations => 'Rādīt atmestas sarunas';

  @override
  String get showDiscardedConversationsDesc => 'Iekļaut sarunas, kas atzīmētas kā atmestas';

  @override
  String get shortConversationThreshold => 'Īsās sarunas slieksnis';

  @override
  String get shortConversationThresholdSubtitle =>
      'Sarunas, kas ir īsākas par šo, tiks slēptas, ja vien nav iespējotas iepriekš';

  @override
  String get durationThreshold => 'Ilguma slieksnis';

  @override
  String get durationThresholdDesc => 'Slēpt sarunas, kas ir īsākas par šo';

  @override
  String minLabel(int count) {
    return '$count min';
  }

  @override
  String get customVocabularyTitle => 'Pielāgota vārdnīca';

  @override
  String get addWords => 'Pievienot vārdus';

  @override
  String get addWordsDesc => 'Vārdi, termini vai netipiski vārdi';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'Savienot';

  @override
  String get comingSoon => 'Drīzumā';

  @override
  String get chatToolsFooter => 'Savienojiet savas lietotnes, lai skatītu datus un metriku tērzēšanā.';

  @override
  String get completeAuthInBrowser =>
      'Lūdzu, pabeidziet autentifikāciju savā pārlūkprogrammā. Kad esat pabeidzis, atgriezieties lietotnē.';

  @override
  String failedToStartAuth(String appName) {
    return 'Neizdevās sākt $appName autentifikāciju';
  }

  @override
  String disconnectAppTitle(String appName) {
    return 'Atvienot $appName?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'Vai tiešām vēlaties atvienot no $appName? Jūs varat atkārtoti izveidot savienojumu jebkurā laikā.';
  }

  @override
  String disconnectedFrom(String appName) {
    return 'Atvienots no $appName';
  }

  @override
  String get failedToDisconnect => 'Neizdevās atvienot';

  @override
  String connectTo(String appName) {
    return 'Savienoties ar $appName';
  }

  @override
  String authAccessMessage(String appName) {
    return 'Jums būs jāautorizē Omi piekļuvei jūsu $appName datiem. Tas atvērs jūsu pārlūkprogrammu autentifikācijai.';
  }

  @override
  String get continueAction => 'Turpināt';

  @override
  String get languageTitle => 'Valoda';

  @override
  String get primaryLanguage => 'Primārā valoda';

  @override
  String get automaticTranslation => 'Automātiskais tulkojums';

  @override
  String get detectLanguages => 'Atklāt 10+ valodas';

  @override
  String get authorizeSavingRecordings => 'Autorizēt ierakstu saglabāšanu';

  @override
  String get thanksForAuthorizing => 'Paldies par autorizāciju!';

  @override
  String get needYourPermission => 'Mums nepieciešama jūsu atļauja';

  @override
  String get alreadyGavePermission =>
      'Jūs jau esat devis mums atļauju saglabāt jūsu ierakstus. Šeit ir atgādinājums, kāpēc mums tas ir nepieciešams:';

  @override
  String get wouldLikePermission => 'Mēs vēlētos jūsu atļauju saglabāt jūsu balss ierakstus. Šeit ir iemesls:';

  @override
  String get improveSpeechProfile => 'Uzlabot jūsu runas profilu';

  @override
  String get improveSpeechProfileDesc =>
      'Mēs izmantojam ierakstus, lai turpinātu apmācīt un uzlabotu jūsu personīgo runas profilu.';

  @override
  String get trainFamilyProfiles => 'Apmācīt profilus draugiem un ģimenei';

  @override
  String get trainFamilyProfilesDesc =>
      'Jūsu ieraksti palīdz mums atpazīt un izveidot profilus jūsu draugiem un ģimenei.';

  @override
  String get enhanceTranscriptAccuracy => 'Uzlabot transkripcijas precizitāti';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'Uzlabojoties mūsu modelim, mēs varam sniegt labākus transkripcijas rezultātus jūsu ierakstiem.';

  @override
  String get legalNotice =>
      'Juridisks paziņojums: Balss datu ierakstīšanas un uzglabāšanas likumība var atšķirties atkarībā no jūsu atrašanās vietas un tā, kā izmantojat šo funkciju. Ir jūsu atbildība nodrošināt atbilstību vietējiem likumiem un noteikumiem.';

  @override
  String get alreadyAuthorized => 'Jau autorizēts';

  @override
  String get authorize => 'Autorizēt';

  @override
  String get revokeAuthorization => 'Atsaukt autorizāciju';

  @override
  String get authorizationSuccessful => 'Autorizācija veiksmīga!';

  @override
  String get failedToAuthorize => 'Neizdevās autorizēt. Lūdzu, mēģiniet vēlreiz.';

  @override
  String get authorizationRevoked => 'Autorizācija atsaukta.';

  @override
  String get recordingsDeleted => 'Ieraksti izdzēsti.';

  @override
  String get failedToRevoke => 'Neizdevās atsaukt autorizāciju. Lūdzu, mēģiniet vēlreiz.';

  @override
  String get permissionRevokedTitle => 'Atļauja atsaukta';

  @override
  String get permissionRevokedMessage => 'Vai vēlaties, lai mēs noņemtu arī visus jūsu esošos ierakstus?';

  @override
  String get yes => 'Jā';

  @override
  String get editName => 'Rediģēt vārdu';

  @override
  String get howShouldOmiCallYou => 'Kā Omi jums vajadzētu uzrunāt?';

  @override
  String get enterYourName => 'Ievadiet savu vārdu';

  @override
  String get nameCannotBeEmpty => 'Vārds nevar būt tukšs';

  @override
  String get nameUpdatedSuccessfully => 'Vārds veiksmīgi atjaunināts!';

  @override
  String get calendarSettings => 'Kalendāra iestatījumi';

  @override
  String get calendarProviders => 'Kalendāra pakalpojumu sniedzēji';

  @override
  String get macOsCalendar => 'macOS kalendārs';

  @override
  String get connectMacOsCalendar => 'Savienojiet savu vietējo macOS kalendāru';

  @override
  String get googleCalendar => 'Google kalendārs';

  @override
  String get syncGoogleAccount => 'Sinhronizēt ar savu Google kontu';

  @override
  String get showMeetingsMenuBar => 'Rādīt tuvākās sanāksmes izvēlnes joslā';

  @override
  String get showMeetingsMenuBarDesc => 'Attēlot jūsu nākamo sanāksmi un laiku līdz tās sākumam macOS izvēlnes joslā';

  @override
  String get showEventsNoParticipants => 'Rādīt notikumus bez dalībniekiem';

  @override
  String get showEventsNoParticipantsDesc =>
      'Ja iespējots, Coming Up rāda notikumus bez dalībniekiem vai video saites.';

  @override
  String get yourMeetings => 'Jūsu sanāksmes';

  @override
  String get refresh => 'Atsvaidzināt';

  @override
  String get noUpcomingMeetings => 'Nav atrastas tuvākās sanāksmes';

  @override
  String get checkingNextDays => 'Pārbauda nākamās 30 dienas';

  @override
  String get tomorrow => 'Rīt';

  @override
  String get googleCalendarComingSoon => 'Google Calendar integrācija drīzumā!';

  @override
  String connectedAsUser(String userId) {
    return 'Savienots kā lietotājs: $userId';
  }

  @override
  String get defaultWorkspace => 'Noklusējuma darba vieta';

  @override
  String get tasksCreatedInWorkspace => 'Uzdevumi tiks izveidoti šajā darba vietā';

  @override
  String get defaultProjectOptional => 'Noklusējuma projekts (neobligāts)';

  @override
  String get leaveUnselectedTasks => 'Atstājiet neizvēlētu, lai izveidotu uzdevumus bez projekta';

  @override
  String get noProjectsInWorkspace => 'Šajā darba vietā nav atrasti projekti';

  @override
  String get conversationTimeoutDesc => 'Izvēlieties, cik ilgi gaidīt klusumu, pirms automātiski beidzat sarunu:';

  @override
  String get timeout2Minutes => '2 minūtes';

  @override
  String get timeout2MinutesDesc => 'Beigt sarunu pēc 2 minūšu klusuma';

  @override
  String get timeout5Minutes => '5 minūtes';

  @override
  String get timeout5MinutesDesc => 'Beigt sarunu pēc 5 minūšu klusuma';

  @override
  String get timeout10Minutes => '10 minūtes';

  @override
  String get timeout10MinutesDesc => 'Beigt sarunu pēc 10 minūšu klusuma';

  @override
  String get timeout30Minutes => '30 minūtes';

  @override
  String get timeout30MinutesDesc => 'Beigt sarunu pēc 30 minūšu klusuma';

  @override
  String get timeout4Hours => '4 stundas';

  @override
  String get timeout4HoursDesc => 'Beigt sarunu pēc 4 stundu klusuma';

  @override
  String get conversationEndAfterHours => 'Sarunas tagad beigsies pēc 4 stundu klusuma';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Sarunas tagad beigsies pēc $minutes minūtes(-ēm) klusuma';
  }

  @override
  String get tellUsPrimaryLanguage => 'Pastāstiet mums savu primāro valodu';

  @override
  String get languageForTranscription => 'Iestatiet savu valodu precīzākai transkripcijai un personalizētai pieredzei.';

  @override
  String get singleLanguageModeInfo =>
      'Vienas valodas režīms ir iespējots. Tulkošana ir atspējota lielākai precizitātei.';

  @override
  String get searchLanguageHint => 'Meklēt valodu pēc nosaukuma vai koda';

  @override
  String get noLanguagesFound => 'Valodas nav atrastas';

  @override
  String get skip => 'Izlaist';

  @override
  String languageSetTo(String language) {
    return 'Valoda iestatīta uz $language';
  }

  @override
  String get failedToSetLanguage => 'Neizdevās iestatīt valodu';

  @override
  String appSettings(String appName) {
    return '$appName iestatījumi';
  }

  @override
  String disconnectFromApp(String appName) {
    return 'Atvienot no $appName?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'Tas noņems jūsu $appName autentifikāciju. Jums būs atkārtoti jāizveido savienojums, lai to izmantotu vēlreiz.';
  }

  @override
  String connectedToApp(String appName) {
    return 'Savienots ar $appName';
  }

  @override
  String get account => 'Konts';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Jūsu uzdevumi tiks sinhronizēti ar jūsu $appName kontu';
  }

  @override
  String get defaultSpace => 'Noklusējuma vieta';

  @override
  String get selectSpaceInWorkspace => 'Izvēlēties vietu savā darba vietā';

  @override
  String get noSpacesInWorkspace => 'Šajā darba vietā nav atrastas vietas';

  @override
  String get defaultList => 'Noklusējuma saraksts';

  @override
  String get tasksAddedToList => 'Uzdevumi tiks pievienoti šim sarakstam';

  @override
  String get noListsInSpace => 'Šajā vietā nav atrasti saraksti';

  @override
  String failedToLoadRepos(String error) {
    return 'Neizdevās ielādēt repozitorijus: $error';
  }

  @override
  String get defaultRepoSaved => 'Noklusējuma repozitorijs saglabāts';

  @override
  String get failedToSaveDefaultRepo => 'Neizdevās saglabāt noklusējuma repozitoriju';

  @override
  String get defaultRepository => 'Noklusējuma repozitorijs';

  @override
  String get selectDefaultRepoDesc =>
      'Izvēlieties noklusējuma repozitoriju problēmu izveidošanai. Jūs joprojām varat norādīt citu repozitoriju, veidojot problēmas.';

  @override
  String get noReposFound => 'Repozitoriji nav atrasti';

  @override
  String get private => 'Privāts';

  @override
  String updatedDate(String date) {
    return 'Atjaunināts $date';
  }

  @override
  String get yesterday => 'Vakar';

  @override
  String daysAgo(int count) {
    return 'pirms $count dienām';
  }

  @override
  String get oneWeekAgo => 'pirms 1 nedēļas';

  @override
  String weeksAgo(int count) {
    return 'pirms $count nedēļām';
  }

  @override
  String get oneMonthAgo => 'pirms 1 mēneša';

  @override
  String monthsAgo(int count) {
    return 'pirms $count mēnešiem';
  }

  @override
  String get issuesCreatedInRepo => 'Problēmas tiks izveidotas jūsu noklusējuma repozitorijā';

  @override
  String get taskIntegrations => 'Uzdevumu integrācijas';

  @override
  String get configureSettings => 'Konfigurēt iestatījumus';

  @override
  String get completeAuthBrowser =>
      'Lūdzu, pabeidziet autentifikāciju savā pārlūkprogrammā. Kad esat pabeidzis, atgriezieties lietotnē.';

  @override
  String failedToStartAppAuth(String appName) {
    return 'Neizdevās sākt $appName autentifikāciju';
  }

  @override
  String connectToAppTitle(String appName) {
    return 'Savienoties ar $appName';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Jums būs jāautorizē Omi, lai izveidotu uzdevumus jūsu $appName kontā. Tas atvērs jūsu pārlūkprogrammu autentifikācijai.';
  }

  @override
  String get continueButton => 'Turpināt';

  @override
  String appIntegration(String appName) {
    return '$appName integrācija';
  }

  @override
  String integrationComingSoon(String appName) {
    return 'Integrācija ar $appName drīzumā! Mēs cītīgi strādājam, lai jums piedāvātu vairāk uzdevumu pārvaldības iespēju.';
  }

  @override
  String get gotIt => 'Sapratu';

  @override
  String get tasksExportedOneApp => 'Uzdevumus var eksportēt uz vienu lietotni vienlaikus.';

  @override
  String get completeYourUpgrade => 'Pabeidziet savu jaunināšanu';

  @override
  String get importConfiguration => 'Importēt konfigurāciju';

  @override
  String get exportConfiguration => 'Eksportēt konfigurāciju';

  @override
  String get bringYourOwn => 'Atnesiet savu';

  @override
  String get payYourSttProvider => 'Brīvi izmantojiet omi. Jūs maksājat tikai savam STT pakalpojumu sniedzējam tieši.';

  @override
  String get freeMinutesMonth => '1200 bezmaksas minūtes/mēnesī iekļautas. Neierobežots ar ';

  @override
  String get omiUnlimited => 'Omi Neierobežots';

  @override
  String get hostRequired => 'Resursdators ir nepieciešams';

  @override
  String get validPortRequired => 'Ir nepieciešams derīgs ports';

  @override
  String get validWebsocketUrlRequired => 'Ir nepieciešams derīgs WebSocket URL (wss://)';

  @override
  String get apiUrlRequired => 'API URL ir nepieciešams';

  @override
  String get apiKeyRequired => 'API atslēga ir nepieciešama';

  @override
  String get invalidJsonConfig => 'Nederīga JSON konfigurācija';

  @override
  String errorSaving(String error) {
    return 'Kļūda, saglabājot: $error';
  }

  @override
  String get configCopiedToClipboard => 'Konfigurācija nokopēta starpliktuvē';

  @override
  String get pasteJsonConfig => 'Ielīmējiet savu JSON konfigurāciju zemāk:';

  @override
  String get addApiKeyAfterImport => 'Jums būs jāpievieno sava API atslēga pēc importēšanas';

  @override
  String get paste => 'Ielīmēt';

  @override
  String get import => 'Importēt';

  @override
  String get invalidProviderInConfig => 'Nederīgs pakalpojumu sniedzējs konfigurācijā';

  @override
  String importedConfig(String providerName) {
    return 'Importēta $providerName konfigurācija';
  }

  @override
  String invalidJson(String error) {
    return 'Nederīgs JSON: $error';
  }

  @override
  String get provider => 'Pakalpojumu sniedzējs';

  @override
  String get live => 'Tiešraide';

  @override
  String get onDevice => 'Ierīcē';

  @override
  String get apiUrl => 'API URL';

  @override
  String get enterSttHttpEndpoint => 'Ievadiet savu STT HTTP galapunktu';

  @override
  String get websocketUrl => 'WebSocket URL';

  @override
  String get enterLiveSttWebsocket => 'Ievadiet savu tiešraides STT WebSocket galapunktu';

  @override
  String get apiKey => 'API atslēga';

  @override
  String get enterApiKey => 'Ievadiet savu API atslēgu';

  @override
  String get storedLocallyNeverShared => 'Saglabāts vietēji, nekad nekopīgots';

  @override
  String get host => 'Resursdators';

  @override
  String get port => 'Ports';

  @override
  String get advanced => 'Papildu';

  @override
  String get configuration => 'Konfigurācija';

  @override
  String get requestConfiguration => 'Pieprasījuma konfigurācija';

  @override
  String get responseSchema => 'Atbildes shēma';

  @override
  String get modified => 'Modificēts';

  @override
  String get resetRequestConfig => 'Atiestatīt pieprasījuma konfigurāciju uz noklusējumu';

  @override
  String get logs => 'Žurnāli';

  @override
  String get logsCopied => 'Žurnāli nokopēti';

  @override
  String get noLogsYet => 'Vēl nav žurnālu. Sāciet ierakstīšanu, lai redzētu pielāgoto STT aktivitāti.';

  @override
  String deviceUsesCodec(String deviceName, String codecReason) {
    return '$deviceName izmanto $codecReason. Tiks izmantots Omi.';
  }

  @override
  String get omiTranscription => 'Omi transkripcija';

  @override
  String get bestInClassTranscription => 'Labākā klases transkripcija ar nulli iestatījumiem';

  @override
  String get instantSpeakerLabels => 'Tūlītējas runātāja etiķetes';

  @override
  String get languageTranslation => '100+ valodu tulkošana';

  @override
  String get optimizedForConversation => 'Optimizēts sarunām';

  @override
  String get autoLanguageDetection => 'Automātiska valodas noteikšana';

  @override
  String get highAccuracy => 'Augsta precizitāte';

  @override
  String get privacyFirst => 'Privātums pirmajā vietā';

  @override
  String get saveChanges => 'Saglabāt izmaiņas';

  @override
  String get resetToDefault => 'Atiestatīt uz noklusējumu';

  @override
  String get viewTemplate => 'Skatīt veidni';

  @override
  String get trySomethingLike => 'Mēģiniet kaut ko līdzīgu...';

  @override
  String get tryIt => 'Izmēģināt';

  @override
  String get creatingPlan => 'Izveido plānu';

  @override
  String get developingLogic => 'Izstrādā loģiku';

  @override
  String get designingApp => 'Projektē lietotni';

  @override
  String get generatingIconStep => 'Ģenerē ikonu';

  @override
  String get finalTouches => 'Pēdējie pieskārieni';

  @override
  String get processing => 'Apstrādā...';

  @override
  String get features => 'Funkcijas';

  @override
  String get creatingYourApp => 'Izveido jūsu lietotni...';

  @override
  String get generatingIcon => 'Ģenerē ikonu...';

  @override
  String get whatShouldWeMake => 'Ko mums vajadzētu izveidot?';

  @override
  String get appName => 'Lietotnes nosaukums';

  @override
  String get description => 'Apraksts';

  @override
  String get publicLabel => 'Publisks';

  @override
  String get privateLabel => 'Privāts';

  @override
  String get free => 'Bezmaksas';

  @override
  String get perMonth => '/ Mēnesī';

  @override
  String get tailoredConversationSummaries => 'Pielāgoti sarunas kopsavilkumi';

  @override
  String get customChatbotPersonality => 'Pielāgota tērzēšanas robota personība';

  @override
  String get makePublic => 'Padarīt publisku';

  @override
  String get anyoneCanDiscover => 'Ikviens var atklāt jūsu lietotni';

  @override
  String get onlyYouCanUse => 'Tikai jūs varat izmantot šo lietotni';

  @override
  String get paidApp => 'Maksas lietotne';

  @override
  String get usersPayToUse => 'Lietotāji maksā, lai izmantotu jūsu lietotni';

  @override
  String get freeForEveryone => 'Bezmaksas visiem';

  @override
  String get perMonthLabel => '/ mēnesī';

  @override
  String get creating => 'Izveido...';

  @override
  String get createApp => 'Izveidot lietotni';

  @override
  String get searchingForDevices => 'Meklē ierīces...';

  @override
  String devicesFoundNearby(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'IERĪCES',
      one: 'IERĪCE',
    );
    return '$count $_temp0 ATRASTAS TUVUMĀ';
  }

  @override
  String get pairingSuccessful => 'PĀROŠANA VEIKSMĪGA';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Kļūda, savienojoties ar Apple Watch: $error';
  }

  @override
  String get dontShowAgain => 'Vairs nerādīt';

  @override
  String get iUnderstand => 'Es saprotu';

  @override
  String get enableBluetooth => 'Iespējot Bluetooth';

  @override
  String get bluetoothNeeded =>
      'Omi nepieciešams Bluetooth, lai savienotos ar jūsu valkājamo ierīci. Lūdzu, iespējojiet Bluetooth un mēģiniet vēlreiz.';

  @override
  String get contactSupport => 'Sazināties ar atbalstu?';

  @override
  String get connectLater => 'Savienot vēlāk';

  @override
  String get grantPermissions => 'Piešķirt atļaujas';

  @override
  String get backgroundActivity => 'Fona aktivitāte';

  @override
  String get backgroundActivityDesc => 'Ļaujiet Omi darboties fonā labākai stabilitātei';

  @override
  String get locationAccess => 'Atrašanās vietas piekļuve';

  @override
  String get locationAccessDesc => 'Iespējojiet fona atrašanās vietu pilnai pieredzei';

  @override
  String get notifications => 'Paziņojumi';

  @override
  String get notificationsDesc => 'Iespējojiet paziņojumus, lai būtu informēti';

  @override
  String get locationServiceDisabled => 'Atrašanās vietas pakalpojums atspējots';

  @override
  String get locationServiceDisabledDesc =>
      'Atrašanās vietas pakalpojums ir atspējots. Lūdzu, dodieties uz Iestatījumi > Privātums un drošība > Atrašanās vietas pakalpojumi un iespējojiet to';

  @override
  String get backgroundLocationDenied => 'Fona atrašanās vietas piekļuve liegta';

  @override
  String get backgroundLocationDeniedDesc =>
      'Lūdzu, dodieties uz ierīces iestatījumiem un iestatiet atrašanās vietas atļauju uz \"Vienmēr atļaut\"';

  @override
  String get lovingOmi => 'Patīk Omi?';

  @override
  String get leaveReviewIos =>
      'Palīdziet mums sasniegt vairāk cilvēku, atstājot atsauksmi App Store. Jūsu atsauksmes mums nozīmē visu!';

  @override
  String get leaveReviewAndroid =>
      'Palīdziet mums sasniegt vairāk cilvēku, atstājot atsauksmi Google Play Store. Jūsu atsauksmes mums nozīmē visu!';

  @override
  String get rateOnAppStore => 'Novērtēt App Store';

  @override
  String get rateOnGooglePlay => 'Novērtēt Google Play';

  @override
  String get maybeLater => 'Varbūt vēlāk';

  @override
  String get speechProfileIntro => 'Omi ir jāiemācās jūsu mērķi un jūsu balss. Jūs varēsiet to modificēt vēlāk.';

  @override
  String get getStarted => 'Sākt';

  @override
  String get allDone => 'Viss padarīts!';

  @override
  String get keepGoing => 'Turpiniet, jūs darāt lieliski';

  @override
  String get skipThisQuestion => 'Izlaist šo jautājumu';

  @override
  String get skipForNow => 'Izlaist pagaidām';

  @override
  String get connectionError => 'Savienojuma kļūda';

  @override
  String get connectionErrorDesc =>
      'Neizdevās izveidot savienojumu ar serveri. Lūdzu, pārbaudiet interneta savienojumu un mēģiniet vēlreiz.';

  @override
  String get invalidRecordingMultipleSpeakers => 'Atklāts nederīgs ieraksts';

  @override
  String get multipleSpeakersDesc =>
      'Šķiet, ka ierakstā ir vairāki runātāji. Lūdzu, pārliecinieties, ka atrodaties klusā vietā, un mēģiniet vēlreiz.';

  @override
  String get tooShortDesc => 'Nav atklāts pietiekami daudz runas. Lūdzu, runājiet vairāk un mēģiniet vēlreiz.';

  @override
  String get invalidRecordingDesc => 'Lūdzu, pārliecinieties, ka runājat vismaz 5 sekundes un ne vairāk kā 90.';

  @override
  String get areYouThere => 'Vai jūs esat tur?';

  @override
  String get noSpeechDesc =>
      'Mēs nevarējām atklāt nevienu runu. Lūdzu, pārliecinieties, ka runājat vismaz 10 sekundes un ne vairāk kā 3 minūtes.';

  @override
  String get connectionLost => 'Savienojums zaudēts';

  @override
  String get connectionLostDesc =>
      'Savienojums tika pārtraukts. Lūdzu, pārbaudiet interneta savienojumu un mēģiniet vēlreiz.';

  @override
  String get tryAgain => 'Mēģināt vēlreiz';

  @override
  String get connectOmiOmiGlass => 'Savienot Omi / OmiGlass';

  @override
  String get continueWithoutDevice => 'Turpināt bez ierīces';

  @override
  String get permissionsRequired => 'Nepieciešamas atļaujas';

  @override
  String get permissionsRequiredDesc =>
      'Šai lietotnei ir nepieciešamas Bluetooth un Atrašanās vietas atļaujas, lai darbotos pareizi. Lūdzu, iespējojiet tās iestatījumos.';

  @override
  String get openSettings => 'Atvērt iestatījumus';

  @override
  String get wantDifferentName => 'Vēlaties, lai jūs uzrunā citādi?';

  @override
  String get whatsYourName => 'Kāds ir jūsu vārds?';

  @override
  String get speakTranscribeSummarize => 'Runāt. Transkribēt. Apkopot.';

  @override
  String get signInWithApple => 'Pierakstīties ar Apple';

  @override
  String get signInWithGoogle => 'Pierakstīties ar Google';

  @override
  String get byContinuingAgree => 'Turpinot, jūs piekrītat mūsu ';

  @override
  String get termsOfUse => 'Lietošanas noteikumi';

  @override
  String get omiYourAiCompanion => 'Omi – jūsu AI pavadonis';

  @override
  String get captureEveryMoment =>
      'Fiksējiet katru brīdi. Iegūstiet AI\nkopsavilkumus. Nekad vairs nerakstiet piezīmes.';

  @override
  String get appleWatchSetup => 'Apple Watch iestatīšana';

  @override
  String get permissionRequestedExclaim => 'Atļauja pieprasīta!';

  @override
  String get microphonePermission => 'Mikrofona atļauja';

  @override
  String get permissionGrantedNow =>
      'Atļauja piešķirta! Tagad:\n\nAtveriet Omi lietotni savā pulkstenī un piespiediet \"Turpināt\" zemāk';

  @override
  String get needMicrophonePermission =>
      'Mums nepieciešama mikrofona atļauja.\n\n1. Piespiediet \"Piešķirt atļauju\"\n2. Atļaut iPhone\n3. Pulksteņa lietotne aizvērsies\n4. Atkārtoti atveriet un piespiediet \"Turpināt\"';

  @override
  String get grantPermissionButton => 'Piešķirt atļauju';

  @override
  String get needHelp => 'Nepieciešama palīdzība?';

  @override
  String get troubleshootingSteps =>
      'Problēmu novēršana:\n\n1. Pārliecinieties, ka Omi ir instalēts jūsu pulkstenī\n2. Atveriet Omi lietotni savā pulkstenī\n3. Meklējiet atļaujas uznirstošo logu\n4. Piespiediet \"Atļaut\", kad tiek piedāvāts\n5. Lietotne jūsu pulkstenī aizvērsies - atkārtoti atveriet to\n6. Atgriezieties un piespiediet \"Turpināt\" savā iPhone';

  @override
  String get recordingStartedSuccessfully => 'Ierakstīšana veiksmīgi sākta!';

  @override
  String get permissionNotGrantedYet =>
      'Atļauja vēl nav piešķirta. Lūdzu, pārliecinieties, ka atļāvāt mikrofona piekļuvi un atkārtoti atvērāt lietotni savā pulkstenī.';

  @override
  String errorRequestingPermission(String error) {
    return 'Kļūda, pieprasot atļauju: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'Kļūda, sākot ierakstīšanu: $error';
  }

  @override
  String get selectPrimaryLanguage => 'Izvēlieties savu primāro valodu';

  @override
  String get languageBenefits => 'Iestatiet savu valodu precīzākai transkripcijai un personalizētai pieredzei';

  @override
  String get whatsYourPrimaryLanguage => 'Kāda ir jūsu primārā valoda?';

  @override
  String get selectYourLanguage => 'Izvēlieties savu valodu';

  @override
  String get personalGrowthJourney => 'Jūsu personīgās izaugsmes ceļojums ar AI, kas klausās katru jūsu vārdu.';

  @override
  String get actionItemsTitle => 'Darāmie darbi';

  @override
  String get actionItemsDescription =>
      'Piespiediet, lai rediģētu • Ilgi turiet, lai atlasītu • Velciet, lai veiktu darbības';

  @override
  String get tabToDo => 'Darāms';

  @override
  String get tabDone => 'Padarīts';

  @override
  String get tabOld => 'Vecs';

  @override
  String get emptyTodoMessage => '🎉 Viss padarīts!\nNav gaidošu uzdevumu';

  @override
  String get emptyDoneMessage => 'Vēl nav pabeigtu vienību';

  @override
  String get emptyOldMessage => '✅ Nav vecu uzdevumu';

  @override
  String get noItems => 'Nav vienību';

  @override
  String get actionItemMarkedIncomplete => 'Uzdevums atzīmēts kā nepabeigts';

  @override
  String get actionItemCompleted => 'Uzdevums pabeigts';

  @override
  String get deleteActionItemTitle => 'Dzēst darbības vienumu';

  @override
  String get deleteActionItemMessage => 'Vai tiešām vēlaties dzēst šo darbības vienumu?';

  @override
  String get deleteSelectedItemsTitle => 'Dzēst atlasītos vienumus';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Vai tiešām vēlaties dzēst $count atlasītos uzdevumus?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'Uzdevums \"$description\" izdzēsts';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count uzdevumi izdzēsti';
  }

  @override
  String get failedToDeleteItem => 'Neizdevās dzēst uzdevumu';

  @override
  String get failedToDeleteItems => 'Neizdevās dzēst vienumus';

  @override
  String get failedToDeleteSomeItems => 'Neizdevās dzēst dažus vienumus';

  @override
  String get welcomeActionItemsTitle => 'Gatavs uzdevumiem';

  @override
  String get welcomeActionItemsDescription =>
      'Jūsu AI automātiski izvilks uzdevumus no jūsu sarunām. Tie parādīsies šeit, kad tiks izveidoti.';

  @override
  String get autoExtractionFeature => 'Automātiski izvilkts no sarunām';

  @override
  String get editSwipeFeature => 'Piespiediet, lai rediģētu, velciet, lai pabeigtu vai dzēstu';

  @override
  String itemsSelected(int count) {
    return '$count atlasīts';
  }

  @override
  String get selectAll => 'Atlasīt visu';

  @override
  String get deleteSelected => 'Dzēst atlasītos';

  @override
  String searchMemories(int count) {
    return 'Meklēt $count atmiņas';
  }

  @override
  String get memoryDeleted => 'Atmiņa izdzēsta.';

  @override
  String get undo => 'Atsaukt';

  @override
  String get noMemoriesYet => 'Vēl nav atmiņu';

  @override
  String get noAutoMemories => 'Vēl nav automātiski izvilktu atmiņu';

  @override
  String get noManualMemories => 'Vēl nav manuālu atmiņu';

  @override
  String get noMemoriesInCategories => 'Šajās kategorijās nav atmiņu';

  @override
  String get noMemoriesFound => 'Atmiņas nav atrastas';

  @override
  String get addFirstMemory => 'Pievienot savu pirmo atmiņu';

  @override
  String get clearMemoryTitle => 'Notīrīt Omi atmiņu';

  @override
  String get clearMemoryMessage => 'Vai tiešām vēlaties notīrīt Omi atmiņu? Šo darbību nevar atsaukt.';

  @override
  String get clearMemoryButton => 'Notīrīt atmiņu';

  @override
  String get memoryClearedSuccess => 'Omi atmiņa par jums ir notīrīta';

  @override
  String get noMemoriesToDelete => 'Nav atmiņu, ko dzēst';

  @override
  String get createMemoryTooltip => 'Izveidot jaunu atmiņu';

  @override
  String get createActionItemTooltip => 'Izveidot jaunu uzdevumu';

  @override
  String get memoryManagement => 'Atmiņas pārvaldība';

  @override
  String get filterMemories => 'Filtrēt atmiņas';

  @override
  String totalMemoriesCount(int count) {
    return 'Jums ir $count kopējās atmiņas';
  }

  @override
  String get publicMemories => 'Publiskas atmiņas';

  @override
  String get privateMemories => 'Privātas atmiņas';

  @override
  String get makeAllPrivate => 'Padarīt visas atmiņas privātas';

  @override
  String get makeAllPublic => 'Padarīt visas atmiņas publiskas';

  @override
  String get deleteAllMemories => 'Dzēst visas atmiņas';

  @override
  String get allMemoriesPrivateResult => 'Visas atmiņas tagad ir privātas';

  @override
  String get allMemoriesPublicResult => 'Visas atmiņas tagad ir publiskas';

  @override
  String get newMemory => 'Jauna atmiņa';

  @override
  String get editMemory => 'Rediģēt atmiņu';

  @override
  String get memoryContentHint => 'Man patīk ēst saldējumu...';

  @override
  String get failedToSaveMemory => 'Neizdevās saglabāt. Lūdzu, pārbaudiet savienojumu.';

  @override
  String get saveMemory => 'Saglabāt atmiņu';

  @override
  String get retry => 'Mēģināt vēlreiz';

  @override
  String get createActionItem => 'Izveidot darbības vienumu';

  @override
  String get editActionItem => 'Rediģēt darbības vienumu';

  @override
  String get actionItemDescriptionHint => 'Kas ir jādara?';

  @override
  String get actionItemDescriptionEmpty => 'Uzdevuma apraksts nevar būt tukšs.';

  @override
  String get actionItemUpdated => 'Uzdevums atjaunināts';

  @override
  String get failedToUpdateActionItem => 'Neizdevās atjaunināt darbības vienumu';

  @override
  String get actionItemCreated => 'Uzdevums izveidots';

  @override
  String get failedToCreateActionItem => 'Neizdevās izveidot darbības vienumu';

  @override
  String get dueDate => 'Termiņš';

  @override
  String get time => 'Laiks';

  @override
  String get addDueDate => 'Pievienot termiņu';

  @override
  String get pressDoneToSave => 'Piespiediet gatavs, lai saglabātu';

  @override
  String get pressDoneToCreate => 'Piespiediet gatavs, lai izveidotu';

  @override
  String get filterAll => 'Visi';

  @override
  String get filterSystem => 'Par jums';

  @override
  String get filterInteresting => 'Ieskati';

  @override
  String get filterManual => 'Manuāli';

  @override
  String get completed => 'Pabeigts';

  @override
  String get markComplete => 'Atzīmēt kā pabeigtu';

  @override
  String get actionItemDeleted => 'Darbības vienums dzēsts';

  @override
  String get failedToDeleteActionItem => 'Neizdevās izdzēst darbības vienumu';

  @override
  String get deleteActionItemConfirmTitle => 'Dzēst uzdevumu';

  @override
  String get deleteActionItemConfirmMessage => 'Vai tiešām vēlaties dzēst šo uzdevumu?';

  @override
  String get appLanguage => 'Lietotnes valoda';

  @override
  String get appInterfaceSectionTitle => 'LIETOJUMPROGRAMMAS INTERFEISS';

  @override
  String get speechTranscriptionSectionTitle => 'RUNA UN TRANSKRIPCIJA';

  @override
  String get languageSettingsHelperText =>
      'Lietojumprogrammas valoda maina izvēlnes un pogas. Runas valoda ietekmē to, kā tiek transkribēti jūsu ieraksti.';

  @override
  String get translationNotice => 'Tulkošanas paziņojums';

  @override
  String get translationNoticeMessage =>
      'Omi tulko sarunas jūsu galvenajā valodā. Atjauniniet to jebkurā laikā sadaļā Iestatījumi → Profili.';

  @override
  String get pleaseCheckInternetConnection => 'Lūdzu, pārbaudiet interneta savienojumu un mēģiniet vēlreiz';

  @override
  String get pleaseSelectReason => 'Lūdzu, izvēlieties iemeslu';

  @override
  String get tellUsMoreWhatWentWrong => 'Pastāstiet mums vairāk par to, kas nogāja greizi...';

  @override
  String get selectText => 'Atlasīt tekstu';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Maksimums $count mērķi atļauti';
  }

  @override
  String get conversationCannotBeMerged => 'Šo sarunu nevar apvienot (bloķēta vai jau tiek apvienota)';

  @override
  String get pleaseEnterFolderName => 'Lūdzu, ievadiet mapes nosaukumu';

  @override
  String get failedToCreateFolder => 'Neizdevās izveidot mapi';

  @override
  String get failedToUpdateFolder => 'Neizdevās atjaunināt mapi';

  @override
  String get folderName => 'Mapes nosaukums';

  @override
  String get descriptionOptional => 'Apraksts (pēc izvēles)';

  @override
  String get failedToDeleteFolder => 'Neizdevās dzēst mapi';

  @override
  String get editFolder => 'Rediģēt mapi';

  @override
  String get deleteFolder => 'Dzēst mapi';

  @override
  String get transcriptCopiedToClipboard => 'Transkripts nokopēts starpliktuvē';

  @override
  String get summaryCopiedToClipboard => 'Kopsavilkums nokopēts starpliktuvē';

  @override
  String get conversationUrlCouldNotBeShared => 'Sarunas URL nevarēja kopīgot.';

  @override
  String get urlCopiedToClipboard => 'URL nokopēts starpliktuvē';

  @override
  String get exportTranscript => 'Eksportēt transkriptu';

  @override
  String get exportSummary => 'Eksportēt kopsavilkumu';

  @override
  String get exportButton => 'Eksportēt';

  @override
  String get actionItemsCopiedToClipboard => 'Darbības vienumi nokopēti starpliktuvē';

  @override
  String get summarize => 'Apkopot';

  @override
  String get generateSummary => 'Ģenerēt kopsavilkumu';

  @override
  String get conversationNotFoundOrDeleted => 'Saruna nav atrasta vai ir dzēsta';

  @override
  String get deleteMemory => 'Dzēst atmiņu?';

  @override
  String get thisActionCannotBeUndone => 'Šo darbību nevar atsaukt.';

  @override
  String memoriesCount(int count) {
    return '$count atmiņas';
  }

  @override
  String get noMemoriesInCategory => 'Šajā kategorijā vēl nav atmiņu';

  @override
  String get addYourFirstMemory => 'Pievienojiet savu pirmo atmiņu';

  @override
  String get firmwareDisconnectUsb => 'Atvienojiet USB';

  @override
  String get firmwareUsbWarning => 'USB savienojums atjaunināšanas laikā var sabojāt jūsu ierīci.';

  @override
  String get firmwareBatteryAbove15 => 'Akumulators virs 15%';

  @override
  String get firmwareEnsureBattery => 'Pārliecinieties, ka jūsu ierīcē ir 15% akumulators.';

  @override
  String get firmwareStableConnection => 'Stabils savienojums';

  @override
  String get firmwareConnectWifi => 'Izveidojiet savienojumu ar WiFi vai mobilo tīklu.';

  @override
  String failedToStartUpdate(String error) {
    return 'Neizdevās sākt atjaunināšanu: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'Pirms atjaunināšanas pārliecinieties:';

  @override
  String get confirmed => 'Apstiprināts!';

  @override
  String get release => 'Atlaidiet';

  @override
  String get slideToUpdate => 'Bīdiet, lai atjauninātu';

  @override
  String copiedToClipboard(String title) {
    return '$title nokopēts starpliktuvē';
  }

  @override
  String get batteryLevel => 'Akumulatora līmenis';

  @override
  String get productUpdate => 'Produkta atjauninājums';

  @override
  String get offline => 'Bezsaistē';

  @override
  String get available => 'Pieejams';

  @override
  String get unpairDeviceDialogTitle => 'Atvienot ierīces sapārošanu';

  @override
  String get unpairDeviceDialogMessage =>
      'Tas atvienos ierīces sapārošanu, lai to varētu savienot ar citu tālruni. Jums būs jādodas uz Iestatījumi > Bluetooth un jāaizmirst ierīce, lai pabeigtu procesu.';

  @override
  String get unpair => 'Atvienot sapārošanu';

  @override
  String get unpairAndForgetDevice => 'Atvienot sapārošanu un aizmirst ierīci';

  @override
  String get unknownDevice => 'Nezināma ierīce';

  @override
  String get unknown => 'Nezināms';

  @override
  String get productName => 'Produkta nosaukums';

  @override
  String get serialNumber => 'Sērijas numurs';

  @override
  String get connected => 'Savienots';

  @override
  String get privacyPolicyTitle => 'Privātuma politika';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label copied';
  }

  @override
  String get noApiKeysYet => 'No API keys yet';

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
  String get debugAndDiagnostics => 'Debug & Diagnostics';

  @override
  String get autoDeletesAfter3Days => 'Auto-deletes after 3 days.';

  @override
  String get helpsDiagnoseIssues => 'Helps diagnose issues';

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
  String get realTimeTranscript => 'Real-time Transcript';

  @override
  String get experimental => 'Experimental';

  @override
  String get transcriptionDiagnostics => 'Transcription Diagnostics';

  @override
  String get detailedDiagnosticMessages => 'Detailed diagnostic messages';

  @override
  String get autoCreateSpeakers => 'Auto-create Speakers';

  @override
  String get autoCreateWhenNameDetected => 'Auto-create when name detected';

  @override
  String get followUpQuestions => 'Follow-up Questions';

  @override
  String get suggestQuestionsAfterConversations => 'Suggest questions after conversations';

  @override
  String get goalTracker => 'Goal Tracker';

  @override
  String get trackPersonalGoalsOnHomepage => 'Track your personal goals on homepage';

  @override
  String get dailyReflection => 'Daily Reflection';

  @override
  String get get9PmReminderToReflect => 'Get a 9 PM reminder to reflect on your day';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'Darbības vienuma apraksts nevar būt tukšs';

  @override
  String get saved => 'Saglabāts';

  @override
  String get overdue => 'Nokavēts';

  @override
  String get failedToUpdateDueDate => 'Neizdevās atjaunināt izpildes termiņu';

  @override
  String get markIncomplete => 'Atzīmēt kā nepabeigtu';

  @override
  String get editDueDate => 'Rediģēt izpildes termiņu';

  @override
  String get setDueDate => 'Iestatīt termiņu';

  @override
  String get clearDueDate => 'Notīrīt izpildes termiņu';

  @override
  String get failedToClearDueDate => 'Neizdevās notīrīt izpildes termiņu';

  @override
  String get mondayAbbr => 'Pr';

  @override
  String get tuesdayAbbr => 'Ot';

  @override
  String get wednesdayAbbr => 'Tr';

  @override
  String get thursdayAbbr => 'Ce';

  @override
  String get fridayAbbr => 'Pk';

  @override
  String get saturdayAbbr => 'Se';

  @override
  String get sundayAbbr => 'Sv';

  @override
  String get howDoesItWork => 'Kā tas darbojas?';

  @override
  String get sdCardSyncDescription => 'SD kartes sinhronizācija importēs jūsu atmiņas no SD kartes lietotnē';

  @override
  String get checksForAudioFiles => 'Pārbauda audio failus SD kartē';

  @override
  String get omiSyncsAudioFiles => 'Omi pēc tam sinhronizē audio failus ar serveri';

  @override
  String get serverProcessesAudio => 'Serveris apstrādā audio failus un izveido atmiņas';

  @override
  String get youreAllSet => 'Viss ir gatavs!';

  @override
  String get welcomeToOmiDescription =>
      'Laipni lūdzam Omi! Jūsu AI kompanjons ir gatavs palīdzēt jums sarunās, uzdevumos un vēl daudz ko.';

  @override
  String get startUsingOmi => 'Sākt izmantot Omi';

  @override
  String get back => 'Atpakaļ';

  @override
  String get keyboardShortcuts => 'Tastatūras īsceļi';

  @override
  String get toggleControlBar => 'Pārslēgt vadības joslu';

  @override
  String get pressKeys => 'Nospiediet taustiņus...';

  @override
  String get cmdRequired => '⌘ nepieciešams';

  @override
  String get invalidKey => 'Nederīgs taustiņš';

  @override
  String get space => 'Atstarpe';

  @override
  String get search => 'Meklēt';

  @override
  String get searchPlaceholder => 'Meklēt...';

  @override
  String get untitledConversation => 'Nosaukuma nav sarunai';

  @override
  String countRemaining(String count) {
    return '$count atlikušais';
  }

  @override
  String get addGoal => 'Pievienot mērķi';

  @override
  String get editGoal => 'Rediģēt mērķi';

  @override
  String get icon => 'Ikona';

  @override
  String get goalTitle => 'Mērķa nosaukums';

  @override
  String get current => 'Pašreizējais';

  @override
  String get target => 'Mērķis';

  @override
  String get saveGoal => 'Saglabāt';

  @override
  String get goals => 'Mērķi';

  @override
  String get tapToAddGoal => 'Pieskarieties, lai pievienotu mērķi';

  @override
  String get welcomeBack => 'Laipni lūdzam atpakaļ';

  @override
  String get yourConversations => 'Jūsu sarunas';

  @override
  String get reviewAndManageConversations => 'Pārskatiet un pārvaldiet ierakstītās sarunas';

  @override
  String get startCapturingConversations => 'Sāciet iegūt sarunas ar savu Omi ierīci, lai tās redzētu šeit.';

  @override
  String get useMobileAppToCapture => 'Izmantojiet mobilo lietotni, lai ierakstītu audio';

  @override
  String get conversationsProcessedAutomatically => 'Sarunas tiek apstrādātas automātiski';

  @override
  String get getInsightsInstantly => 'Iegūstiet ieskatus un kopsavilkumus nekavējoties';

  @override
  String get showAll => 'Rādīt visu →';

  @override
  String get noTasksForToday =>
      'Šodien nav uzdevumu.\\nJautājiet Omi par vairāk uzdevumiem vai izveidojiet tos manuāli.';

  @override
  String get dailyScore => 'DIENAS VĒRTĒJUMS';

  @override
  String get dailyScoreDescription => 'Vērtējums, kas palīdz labāk koncentrēties uz izpildi.';

  @override
  String get searchResults => 'Meklēšanas rezultāti';

  @override
  String get actionItems => 'Darbības punkti';

  @override
  String get tasksToday => 'Šodien';

  @override
  String get tasksTomorrow => 'Rīt';

  @override
  String get tasksNoDeadline => 'Nav termiņa';

  @override
  String get tasksLater => 'Vēlāk';

  @override
  String get loadingTasks => 'Ielādē uzdevumus...';

  @override
  String get tasks => 'Uzdevumi';

  @override
  String get swipeTasksToIndent => 'Velciet uzdevumus, lai atkāptu, velciet starp kategorijām';

  @override
  String get create => 'Izveidot';

  @override
  String get noTasksYet => 'Vēl nav uzdevumu';

  @override
  String get tasksFromConversationsWillAppear =>
      'Šeit parādīsies uzdevumi no jūsu sarunām.\nNoklikšķiniet uz Izveidot, lai pievienotu vienu manuāli.';

  @override
  String get monthJan => 'Jan';

  @override
  String get monthFeb => 'Feb';

  @override
  String get monthMar => 'Mar';

  @override
  String get monthApr => 'Apr';

  @override
  String get monthMay => 'Maijs';

  @override
  String get monthJun => 'Jūn';

  @override
  String get monthJul => 'Jūl';

  @override
  String get monthAug => 'Aug';

  @override
  String get monthSep => 'Sept';

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
  String get actionItemUpdatedSuccessfully => 'Darbības vienums veiksmīgi atjaunināts';

  @override
  String get actionItemCreatedSuccessfully => 'Darbības vienums veiksmīgi izveidots';

  @override
  String get actionItemDeletedSuccessfully => 'Darbības vienums veiksmīgi izdzēsts';

  @override
  String get deleteActionItem => 'Dzēst darbības vienumu';

  @override
  String get deleteActionItemConfirmation => 'Vai tiešām vēlaties dzēst šo darbības vienumu? Šo darbību nevar atsaukt.';

  @override
  String get enterActionItemDescription => 'Ievadiet darbības vienuma aprakstu...';

  @override
  String get markAsCompleted => 'Atzīmēt kā pabeigtu';

  @override
  String get setDueDateAndTime => 'Iestatīt termiņu un laiku';

  @override
  String get reloadingApps => 'Lietotņu pārlāde...';

  @override
  String get loadingApps => 'Lietotņu ielāde...';

  @override
  String get browseInstallCreateApps => 'Pārlūkojiet, instalējiet un izveidojiet lietotnes';

  @override
  String get all => 'Visi';

  @override
  String get open => 'Atvērt';

  @override
  String get install => 'Instalēt';

  @override
  String get noAppsAvailable => 'Nav pieejamu lietotņu';

  @override
  String get unableToLoadApps => 'Neizdevās ielādēt lietotnes';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'Mēģiniet pielāgot meklēšanas terminus vai filtrus';

  @override
  String get checkBackLaterForNewApps => 'Pārbaudiet vēlāk jaunas lietotnes';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'Lūdzu, pārbaudiet interneta savienojumu un mēģiniet vēlreiz';

  @override
  String get createNewApp => 'Izveidot jaunu lietotni';

  @override
  String get buildSubmitCustomOmiApp => 'Izveidojiet un iesniedziet savu pielāgoto Omi lietotni';

  @override
  String get submittingYourApp => 'Jūsu lietotne tiek iesniegta...';

  @override
  String get preparingFormForYou => 'Veidlapa tiek sagatavota jums...';

  @override
  String get appDetails => 'Lietotnes informācija';

  @override
  String get paymentDetails => 'Maksājuma informācija';

  @override
  String get previewAndScreenshots => 'Priekšskatījums un ekrānuzņēmumi';

  @override
  String get appCapabilities => 'Lietotnes iespējas';

  @override
  String get aiPrompts => 'MI norādījumi';

  @override
  String get chatPrompt => 'Tērzēšanas norādījums';

  @override
  String get chatPromptPlaceholder =>
      'Jūs esat lieliska lietotne, jūsu darbs ir atbildēt uz lietotāju jautājumiem un likt viņiem justies labi...';

  @override
  String get conversationPrompt => 'Sarunas uzvedne';

  @override
  String get conversationPromptPlaceholder =>
      'Jūs esat lieliska lietotne, jums tiks sniegta sarunas transkripcija un kopsavilkums...';

  @override
  String get notificationScopes => 'Paziņojumu jomas';

  @override
  String get appPrivacyAndTerms => 'Lietotnes privātums un noteikumi';

  @override
  String get makeMyAppPublic => 'Padarīt manu lietotni publisku';

  @override
  String get submitAppTermsAgreement =>
      'Iesniedzot šo lietotni, es piekrītu Omi AI pakalpojumu sniegšanas noteikumiem un privātuma politikai';

  @override
  String get submitApp => 'Iesniegt lietotni';

  @override
  String get needHelpGettingStarted => 'Vajadzīga palīdzība, lai sāktu?';

  @override
  String get clickHereForAppBuildingGuides => 'Noklikšķiniet šeit lietotņu veidošanas rokasgrāmatām un dokumentācijai';

  @override
  String get submitAppQuestion => 'Iesniegt lietotni?';

  @override
  String get submitAppPublicDescription =>
      'Jūsu lietotne tiks pārskatīta un padarīta publiska. Varat sākt to izmantot uzreiz, pat pārskatīšanas laikā!';

  @override
  String get submitAppPrivateDescription =>
      'Jūsu lietotne tiks pārskatīta un padarīta jums pieejama privāti. Varat sākt to izmantot uzreiz, pat pārskatīšanas laikā!';

  @override
  String get startEarning => 'Sāciet pelnīt! 💰';

  @override
  String get connectStripeOrPayPal => 'Savienojiet Stripe vai PayPal, lai saņemtu maksājumus par savu lietotni.';

  @override
  String get connectNow => 'Savienot tagad';

  @override
  String installsCount(String count) {
    return '$count+ instalācijas';
  }

  @override
  String get uninstallApp => 'Atinstalēt lietotni';

  @override
  String get subscribe => 'Abonēt';

  @override
  String get dataAccessNotice => 'Datu piekļuves paziņojums';

  @override
  String get dataAccessWarning =>
      'Šī lietotne piekļūs jūsu datiem. Omi AI nav atbildīgs par to, kā šī lietotne izmanto, modificē vai dzēš jūsu datus';

  @override
  String get installApp => 'Instalēt lietotni';

  @override
  String get betaTesterNotice =>
      'Jūs esat šīs lietotnes beta testētājs. Tā vēl nav publiska. Tā kļūs publiska pēc apstiprināšanas.';

  @override
  String get appUnderReviewOwner =>
      'Jūsu lietotne tiek pārskatīta un ir redzama tikai jums. Tā kļūs publiska pēc apstiprināšanas.';

  @override
  String get appRejectedNotice =>
      'Jūsu lietotne tika noraidīta. Lūdzu, atjauniniet lietotnes informāciju un atkārtoti iesniedziet to pārskatīšanai.';

  @override
  String get setupSteps => 'Iestatīšanas soļi';

  @override
  String get setupInstructions => 'Iestatīšanas instrukcijas';

  @override
  String get integrationInstructions => 'Integrācijas instrukcijas';

  @override
  String get preview => 'Priekšskatījums';

  @override
  String get aboutTheApp => 'Par lietotni';

  @override
  String get aboutThePersona => 'Par personu';

  @override
  String get chatPersonality => 'Tērzēšanas personība';

  @override
  String get ratingsAndReviews => 'Vērtējumi un atsauksmes';

  @override
  String get noRatings => 'nav vērtējumu';

  @override
  String ratingsCount(String count) {
    return '$count+ vērtējumi';
  }

  @override
  String get errorActivatingApp => 'Kļūda, aktivizējot lietotni';

  @override
  String get integrationSetupRequired => 'Ja šī ir integrācijas lietotne, pārliecinieties, ka iestatīšana ir pabeigta.';

  @override
  String get installed => 'Instalēts';
}
