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
  String get cancel => 'Cancel';

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
  String get speechProfile => 'Runas Profils';

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
  String get noStarredConversations => 'Nav sarunu ar zvaigzni';

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
  String get messageCopied => '✨ Ziņojums nokopēts starpliktuvē';

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
  String get clearChat => 'Notīrīt sarunu';

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
  String get membersAndCounting => '8000+ dalībnieki un turpina pieaugt.';

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
  String get customVocabulary => 'Pielāgots Vārdnīca';

  @override
  String get identifyingOthers => 'Citu Identificēšana';

  @override
  String get paymentMethods => 'Maksājumu Metodes';

  @override
  String get conversationDisplay => 'Sarunu Attēlošana';

  @override
  String get dataPrivacy => 'Datu Privātums';

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
  String get offlineSync => 'Offline Sync';

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
  String get signOut => 'Iziet';

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
  String get off => 'Off';

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
  String get createKey => 'Izveidot Atslēgu';

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
  String get noLogFilesFound => 'Nav atrasts neviens žurnāla fails.';

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
  String get knowledgeGraphDeleted => 'Zināšanu grafs izdzēsts';

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
  String get realtimeTranscript => 'Reāllaika transkripts';

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
  String get noUpcomingMeetings => 'Nav gaidāmu tikšanos';

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
  String get private => 'Privāta';

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
  String get speechProfileIntro => 'Omi ir jāapgūst jūsu mērķi un balss. Vēlāk varēsiet to mainīt.';

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
  String get whatsYourName => 'Kā tevi sauc?';

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
  String get searchMemories => 'Meklēt atmiņas...';

  @override
  String get memoryDeleted => 'Atmiņa izdzēsta.';

  @override
  String get undo => 'Atsaukt';

  @override
  String get noMemoriesYet => '🧠 Vēl nav atmiņu';

  @override
  String get noAutoMemories => 'Vēl nav automātiski izvilktu atmiņu';

  @override
  String get noManualMemories => 'Vēl nav manuālu atmiņu';

  @override
  String get noMemoriesInCategories => 'Šajās kategorijās nav atmiņu';

  @override
  String get noMemoriesFound => '🔍 Atmiņas nav atrastas';

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
  String get noMemoriesToDelete => 'Nav atmiņu dzēšanai';

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
  String get newMemory => '✨ Jauna atmiņa';

  @override
  String get editMemory => '✏️ Rediģēt atmiņu';

  @override
  String get memoryContentHint => 'Man patīk ēst saldējumu...';

  @override
  String get failedToSaveMemory => 'Neizdevās saglabāt. Lūdzu, pārbaudiet savienojumu.';

  @override
  String get saveMemory => 'Saglabāt atmiņu';

  @override
  String get retry => 'Retry';

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
  String get deleteMemory => 'Dzēst atmiņu';

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
    return '$label nokopēts';
  }

  @override
  String get noApiKeysYet => 'Vēl nav API atslēgu. Izveidojiet vienu integrācijai ar savu lietotni.';

  @override
  String get createKeyToGetStarted => 'Izveidojiet atslēgu, lai sāktu';

  @override
  String get persona => 'Persona';

  @override
  String get configureYourAiPersona => 'Konfigurējiet savu AI personu';

  @override
  String get configureSttProvider => 'Konfigurēt STT pakalpojumu sniedzēju';

  @override
  String get setWhenConversationsAutoEnd => 'Iestatiet, kad sarunas automātiski beidzas';

  @override
  String get importDataFromOtherSources => 'Importēt datus no citiem avotiem';

  @override
  String get debugAndDiagnostics => 'Atkļūdošana un diagnostika';

  @override
  String get autoDeletesAfter3Days => 'Automātiska dzēšana pēc 3 dienām';

  @override
  String get helpsDiagnoseIssues => 'Palīdz diagnosticēt problēmas';

  @override
  String get exportStartedMessage => 'Eksports sākts. Tas var aizņemt dažas sekundes...';

  @override
  String get exportConversationsToJson => 'Eksportēt sarunas uz JSON failu';

  @override
  String get knowledgeGraphDeletedSuccess => 'Zināšanu grafs veiksmīgi dzēsts';

  @override
  String failedToDeleteGraph(String error) {
    return 'Neizdevās dzēst grafu: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'Notīrīt visus mezglus un savienojumus';

  @override
  String get addToClaudeDesktopConfig => 'Pievienot claude_desktop_config.json';

  @override
  String get connectAiAssistantsToData => 'Savienojiet AI asistentus ar saviem datiem';

  @override
  String get useYourMcpApiKey => 'Izmantojiet savu MCP API atslēgu';

  @override
  String get realTimeTranscript => 'Reāllaika transkripcija';

  @override
  String get experimental => 'Eksperimentāls';

  @override
  String get transcriptionDiagnostics => 'Transkripcijas diagnostika';

  @override
  String get detailedDiagnosticMessages => 'Detalizēti diagnostikas ziņojumi';

  @override
  String get autoCreateSpeakers => 'Automātiski izveidot runātājus';

  @override
  String get autoCreateWhenNameDetected => 'Automātiski izveidot, kad konstatēts vārds';

  @override
  String get followUpQuestions => 'Turpinājuma jautājumi';

  @override
  String get suggestQuestionsAfterConversations => 'Ieteikt jautājumus pēc sarunām';

  @override
  String get goalTracker => 'Mērķu izsekotājs';

  @override
  String get trackPersonalGoalsOnHomepage => 'Izsekojiet savus personīgos mērķus sākumlapā';

  @override
  String get dailyReflection => 'Ikdienas pārdomu';

  @override
  String get get9PmReminderToReflect => 'Saņemiet atgādinājumu plkst. 21, lai pārdomātu savu dienu';

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
  String get keyboardShortcuts => 'Tastatūras Īsceļi';

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
  String get untitledConversation => 'Saruna bez nosaukuma';

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
  String welcomeBack(String name) {
    return 'Laipni lūdzam atpakaļ, $name';
  }

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
  String get dailyScore => 'DIENAS REZULTĀTS';

  @override
  String get dailyScoreDescription => 'Rezultāts, kas palīdz labāk\nkoncentrēties uz izpildi.';

  @override
  String get searchResults => 'Meklēšanas rezultāti';

  @override
  String get actionItems => 'Darbības elementi';

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
  String get all => 'All';

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
  String get installed => 'Instalēta';

  @override
  String get appIdLabel => 'Lietotnes ID';

  @override
  String get appNameLabel => 'Lietotnes nosaukums';

  @override
  String get appNamePlaceholder => 'Mana brīnišķīgā lietotne';

  @override
  String get pleaseEnterAppName => 'Lūdzu, ievadiet lietotnes nosaukumu';

  @override
  String get categoryLabel => 'Kategorija';

  @override
  String get selectCategory => 'Atlasiet kategoriju';

  @override
  String get descriptionLabel => 'Apraksts';

  @override
  String get appDescriptionPlaceholder =>
      'Mana brīnišķīgā lietotne ir lieliska lietotne, kas dara pārsteidzošas lietas. Tā ir labākā lietotne!';

  @override
  String get pleaseProvideValidDescription => 'Lūdzu, norādiet derīgu aprakstu';

  @override
  String get appPricingLabel => 'Lietotnes cenu noteikšana';

  @override
  String get noneSelected => 'Nav atlasīts';

  @override
  String get appIdCopiedToClipboard => 'Lietotnes ID nokopēts starpliktuvē';

  @override
  String get appCategoryModalTitle => 'Lietotnes kategorija';

  @override
  String get pricingFree => 'Bezmaksas';

  @override
  String get pricingPaid => 'Maksas';

  @override
  String get loadingCapabilities => 'Ielādē iespējas...';

  @override
  String get filterInstalled => 'Instalēts';

  @override
  String get filterMyApps => 'Manas lietotnes';

  @override
  String get clearSelection => 'Notīrīt atlasi';

  @override
  String get filterCategory => 'Kategorija';

  @override
  String get rating4PlusStars => '4+ zvaigznes';

  @override
  String get rating3PlusStars => '3+ zvaigznes';

  @override
  String get rating2PlusStars => '2+ zvaigznes';

  @override
  String get rating1PlusStars => '1+ zvaigzne';

  @override
  String get filterRating => 'Vērtējums';

  @override
  String get filterCapabilities => 'Iespējas';

  @override
  String get noNotificationScopesAvailable => 'Paziņojumu tvērumi nav pieejami';

  @override
  String get popularApps => 'Populārākās lietotnes';

  @override
  String get pleaseProvidePrompt => 'Lūdzu, norādiet uzvedni';

  @override
  String chatWithAppName(String appName) {
    return 'Tērzēšana ar $appName';
  }

  @override
  String get defaultAiAssistant => 'Noklusējuma AI asistents';

  @override
  String get readyToChat => '✨ Gatavs tērzēt!';

  @override
  String get connectionNeeded => '🌐 Nepieciešams savienojums';

  @override
  String get startConversation => 'Sāciet sarunu un ļaujiet būt brīnumiem';

  @override
  String get checkInternetConnection => 'Lūdzu, pārbaudiet interneta savienojumu';

  @override
  String get wasThisHelpful => 'Vai tas bija noderīgi?';

  @override
  String get thankYouForFeedback => 'Paldies par atsauksmēm!';

  @override
  String get maxFilesUploadError => 'Vienlaikus var augšupielādēt tikai 4 failus';

  @override
  String get attachedFiles => '📎 Pievienotie faili';

  @override
  String get takePhoto => 'Uzņemt fotoattēlu';

  @override
  String get captureWithCamera => 'Uzņemt ar kameru';

  @override
  String get selectImages => 'Atlasīt attēlus';

  @override
  String get chooseFromGallery => 'Izvēlieties no galerijas';

  @override
  String get selectFile => 'Atlasīt failu';

  @override
  String get chooseAnyFileType => 'Izvēlieties jebkuru faila tipu';

  @override
  String get cannotReportOwnMessages => 'Jūs nevarat ziņot par saviem ziņojumiem';

  @override
  String get messageReportedSuccessfully => '✅ Ziņojums veiksmīgi ziņots';

  @override
  String get confirmReportMessage => 'Vai tiešām vēlaties ziņot par šo ziņojumu?';

  @override
  String get selectChatAssistant => 'Izvēlēties tērzēšanas asistentu';

  @override
  String get enableMoreApps => 'Iespējot vairāk lietotņu';

  @override
  String get chatCleared => 'Tērzēšana notīrīta';

  @override
  String get clearChatTitle => 'Notīrīt tērzēšanu?';

  @override
  String get confirmClearChat => 'Vai tiešām vēlaties notīrīt tērzēšanu? Šo darbību nevar atsaukt.';

  @override
  String get copy => 'Kopēt';

  @override
  String get share => 'Dalīties';

  @override
  String get report => 'Ziņot';

  @override
  String get microphonePermissionRequired => 'Balss ierakstam nepieciešama mikrofona atļauja.';

  @override
  String get microphonePermissionDenied =>
      'Mikrofona atļauja liegta. Lūdzu, dodiet atļauju Sistēmas iestatījumi > Privātums un drošība > Mikrofons.';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'Neizdevās pārbaudīt mikrofona atļauju: $error';
  }

  @override
  String get failedToTranscribeAudio => 'Neizdevās transkribēt audio';

  @override
  String get transcribing => 'Transkribē...';

  @override
  String get transcriptionFailed => 'Transkripcija neizdevās';

  @override
  String get discardedConversation => 'Atmesta saruna';

  @override
  String get at => 'plkst.';

  @override
  String get from => 'no';

  @override
  String get copied => 'Nokopēts!';

  @override
  String get copyLink => 'Kopēt saiti';

  @override
  String get hideTranscript => 'Paslēpt transkripciju';

  @override
  String get viewTranscript => 'Skatīt transkripciju';

  @override
  String get conversationDetails => 'Sarunas detaļas';

  @override
  String get transcript => 'Transkripcija';

  @override
  String segmentsCount(int count) {
    return '$count segmenti';
  }

  @override
  String get noTranscriptAvailable => 'Nav pieejama transkripcija';

  @override
  String get noTranscriptMessage => 'Šai sarunai nav transkripcijas.';

  @override
  String get conversationUrlCouldNotBeGenerated => 'Sarunas URL nevarēja izveidot.';

  @override
  String get failedToGenerateConversationLink => 'Neizdevās izveidot sarunas saiti';

  @override
  String get failedToGenerateShareLink => 'Neizdevās izveidot kopīgošanas saiti';

  @override
  String get reloadingConversations => 'Sarunu atkārtota ielāde...';

  @override
  String get user => 'Lietotājs';

  @override
  String get starred => 'Ar zvaigznīti';

  @override
  String get date => 'Datums';

  @override
  String get noResultsFound => 'Rezultāti nav atrasti';

  @override
  String get tryAdjustingSearchTerms => 'Mēģiniet pielāgot meklēšanas nosacījumus';

  @override
  String get starConversationsToFindQuickly => 'Atzīmējiet sarunas ar zvaigzni, lai tās ātri atrastu šeit';

  @override
  String noConversationsOnDate(String date) {
    return 'Nav sarunu datumā $date';
  }

  @override
  String get trySelectingDifferentDate => 'Mēģiniet izvēlēties citu datumu';

  @override
  String get conversations => 'Sarunas';

  @override
  String get chat => 'Tērzēšana';

  @override
  String get actions => 'Darbības';

  @override
  String get syncAvailable => 'Sinhronizācija pieejama';

  @override
  String get referAFriend => 'Ieteikt draugam';

  @override
  String get help => 'Palīdzība';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'Jaunināt uz Pro';

  @override
  String get getOmiDevice => 'Iegūt Omi ierīci';

  @override
  String get wearableAiCompanion => 'Valkājams AI palīgs';

  @override
  String get loadingMemories => 'Ielādē atmiņas...';

  @override
  String get allMemories => 'Visas atmiņas';

  @override
  String get aboutYou => 'Par jums';

  @override
  String get manual => 'Manuāls';

  @override
  String get loadingYourMemories => 'Ielādē jūsu atmiņas...';

  @override
  String get createYourFirstMemory => 'Izveidojiet savu pirmo atmiņu, lai sāktu';

  @override
  String get tryAdjustingFilter => 'Mēģiniet pielāgot meklēšanu vai filtru';

  @override
  String get whatWouldYouLikeToRemember => 'Ko jūs vēlētos atcerēties?';

  @override
  String get category => 'Kategorija';

  @override
  String get public => 'Publiska';

  @override
  String get failedToSaveCheckConnection => 'Neizdevās saglabāt. Lūdzu, pārbaudiet savienojumu.';

  @override
  String get createMemory => 'Izveidot atmiņu';

  @override
  String get deleteMemoryConfirmation => 'Vai tiešām vēlaties dzēst šo atmiņu? Šo darbību nevar atsaukt.';

  @override
  String get makePrivate => 'Padarīt privātu';

  @override
  String get organizeAndControlMemories => 'Organizējiet un kontrolējiet savas atmiņas';

  @override
  String get total => 'Kopā';

  @override
  String get makeAllMemoriesPrivate => 'Padarīt visas atmiņas privātas';

  @override
  String get setAllMemoriesToPrivate => 'Iestatīt visas atmiņas kā privātas';

  @override
  String get makeAllMemoriesPublic => 'Padarīt visas atmiņas publiskas';

  @override
  String get setAllMemoriesToPublic => 'Iestatīt visas atmiņas kā publiskas';

  @override
  String get permanentlyRemoveAllMemories => 'Neatgriezeniski noņemt visas atmiņas no Omi';

  @override
  String get allMemoriesAreNowPrivate => 'Visas atmiņas tagad ir privātas';

  @override
  String get allMemoriesAreNowPublic => 'Visas atmiņas tagad ir publiskas';

  @override
  String get clearOmisMemory => 'Notīrīt Omi atmiņu';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Vai tiešām vēlaties notīrīt Omi atmiņu? Šo darbību nevar atsaukt un tā neatgriezeniski dzēsīs visas $count atmiņas.';
  }

  @override
  String get omisMemoryCleared => 'Omi atmiņa par jums ir notīrīta';

  @override
  String get welcomeToOmi => 'Laipni lūdzam Omi';

  @override
  String get continueWithApple => 'Turpināt ar Apple';

  @override
  String get continueWithGoogle => 'Turpināt ar Google';

  @override
  String get byContinuingYouAgree => 'Turpinot, jūs piekrītat mūsu ';

  @override
  String get termsOfService => 'Pakalpojuma noteikumiem';

  @override
  String get and => ' un ';

  @override
  String get dataAndPrivacy => 'Dati un privātums';

  @override
  String get secureAuthViaAppleId => 'Droša autentifikācija caur Apple ID';

  @override
  String get secureAuthViaGoogleAccount => 'Droša autentifikācija caur Google kontu';

  @override
  String get whatWeCollect => 'Ko mēs vācam';

  @override
  String get dataCollectionMessage =>
      'Turpinot, jūsu sarunas, ieraksti un personiskā informācija tiks droši glabāta mūsu serveros, lai sniegtu AI vadītu ieskatu un iespējotu visas lietotnes funkcijas.';

  @override
  String get dataProtection => 'Datu aizsardzība';

  @override
  String get yourDataIsProtected => 'Jūsu dati ir aizsargāti un regulēti ar mūsu ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'Lūdzu, izvēlieties savu primāro valodu';

  @override
  String get chooseYourLanguage => 'Izvēlieties savu valodu';

  @override
  String get selectPreferredLanguageForBestExperience => 'Izvēlieties vēlamo valodu labākajai Omi pieredzei';

  @override
  String get searchLanguages => 'Meklēt valodas...';

  @override
  String get selectALanguage => 'Izvēlieties valodu';

  @override
  String get tryDifferentSearchTerm => 'Mēģiniet citu meklēšanas terminu';

  @override
  String get pleaseEnterYourName => 'Lūdzu, ievadiet savu vārdu';

  @override
  String get nameMustBeAtLeast2Characters => 'Vārdam jābūt vismaz 2 rakstzīmes garam';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'Pastāstiet mums, kā jūs vēlētos, lai jūs uzrunātu. Tas palīdz personalizēt jūsu Omi pieredzi.';

  @override
  String charactersCount(int count) {
    return '$count rakstzīmes';
  }

  @override
  String get enableFeaturesForBestExperience => 'Iespējojiet funkcijas labākajai Omi pieredzei jūsu ierīcē.';

  @override
  String get microphoneAccess => 'Mikrofona piekļuve';

  @override
  String get recordAudioConversations => 'Ierakstīt audio sarunas';

  @override
  String get microphoneAccessDescription =>
      'Omi nepieciešama mikrofona piekļuve, lai ierakstītu jūsu sarunas un nodrošinātu transkripcijas.';

  @override
  String get screenRecording => 'Ekrāna ierakstīšana';

  @override
  String get captureSystemAudioFromMeetings => 'Uzņemt sistēmas audio no sapulcēm';

  @override
  String get screenRecordingDescription =>
      'Omi nepieciešama ekrāna ierakstīšanas atļauja, lai uzņemtu sistēmas audio no jūsu pārlūkprogrammā balstītajām sapulcēm.';

  @override
  String get accessibility => 'Pieejamība';

  @override
  String get detectBrowserBasedMeetings => 'Noteikt pārlūkprogrammā balstītas sapulces';

  @override
  String get accessibilityDescription =>
      'Omi nepieciešama pieejamības atļauja, lai noteiktu, kad pievienojaties Zoom, Meet vai Teams sapulcēm savā pārlūkprogrammā.';

  @override
  String get pleaseWait => 'Lūdzu, uzgaidiet...';

  @override
  String get joinTheCommunity => 'Pievienojieties kopienai!';

  @override
  String get loadingProfile => 'Ielādē profilu...';

  @override
  String get profileSettings => 'Profila iestatījumi';

  @override
  String get noEmailSet => 'E-pasts nav iestatīts';

  @override
  String get userIdCopiedToClipboard => 'Lietotāja ID nokopēts';

  @override
  String get yourInformation => 'Jūsu Informācija';

  @override
  String get setYourName => 'Iestatīt savu vārdu';

  @override
  String get changeYourName => 'Mainīt savu vārdu';

  @override
  String get manageYourOmiPersona => 'Pārvaldīt savu Omi personu';

  @override
  String get voiceAndPeople => 'Balss un Cilvēki';

  @override
  String get teachOmiYourVoice => 'Iemāciet Omi savu balsi';

  @override
  String get tellOmiWhoSaidIt => 'Pastāstiet Omi, kas to teica 🗣️';

  @override
  String get payment => 'Maksājums';

  @override
  String get addOrChangeYourPaymentMethod => 'Pievienot vai mainīt maksājuma metodi';

  @override
  String get preferences => 'Preferences';

  @override
  String get helpImproveOmiBySharing => 'Palīdziet uzlabot Omi, daloties ar anonimizētiem analīzes datiem';

  @override
  String get deleteAccount => 'Dzēst Kontu';

  @override
  String get deleteYourAccountAndAllData => 'Dzēst savu kontu un visus datus';

  @override
  String get clearLogs => 'Notīrīt žurnālus';

  @override
  String get debugLogsCleared => 'Atkļūdošanas žurnāli notīrīti';

  @override
  String get exportConversations => 'Eksportēt sarunas';

  @override
  String get exportAllConversationsToJson => 'Eksportējiet visas savas sarunas uz JSON failu.';

  @override
  String get conversationsExportStarted =>
      'Sarunu eksportēšana sākta. Tas var aizņemt dažas sekundes, lūdzu, uzgaidiet.';

  @override
  String get mcpDescription =>
      'Lai savienotu Omi ar citām lietojumprogrammām, lai lasītu, meklētu un pārvaldītu savas atmiņas un sarunas. Izveidojiet atslēgu, lai sāktu.';

  @override
  String get apiKeys => 'API atslēgas';

  @override
  String errorLabel(String error) {
    return 'Kļūda: $error';
  }

  @override
  String get noApiKeysFound => 'Nav atrastas API atslēgas. Izveidojiet vienu, lai sāktu.';

  @override
  String get advancedSettings => 'Papildu iestatījumi';

  @override
  String get triggersWhenNewConversationCreated => 'Tiek aktivizēts, kad tiek izveidota jauna saruna.';

  @override
  String get triggersWhenNewTranscriptReceived => 'Tiek aktivizēts, kad tiek saņemts jauns transkripts.';

  @override
  String get realtimeAudioBytes => 'Reāllaika audio baiti';

  @override
  String get triggersWhenAudioBytesReceived => 'Tiek aktivizēts, kad tiek saņemti audio baiti.';

  @override
  String get everyXSeconds => 'Katras x sekundes';

  @override
  String get triggersWhenDaySummaryGenerated => 'Tiek aktivizēts, kad tiek ģenerēts dienas kopsavilkums.';

  @override
  String get tryLatestExperimentalFeatures => 'Izmēģiniet jaunākās Omi komandas eksperimentālās funkcijas.';

  @override
  String get transcriptionServiceDiagnosticStatus => 'Transkribēšanas pakalpojuma diagnostikas statuss';

  @override
  String get enableDetailedDiagnosticMessages =>
      'Iespējot detalizētus diagnostikas ziņojumus no transkribēšanas pakalpojuma';

  @override
  String get autoCreateAndTagNewSpeakers => 'Automātiski izveidot un atzīmēt jaunus runātājus';

  @override
  String get automaticallyCreateNewPerson => 'Automātiski izveidot jaunu personu, kad transkriptā tiek atklāts vārds.';

  @override
  String get pilotFeatures => 'Pilotfunkcijas';

  @override
  String get pilotFeaturesDescription => 'Šīs funkcijas ir testi, un atbalsts nav garantēts.';

  @override
  String get suggestFollowUpQuestion => 'Ieteikt turpinājuma jautājumu';

  @override
  String get saveSettings => 'Saglabāt Iestatījumus';

  @override
  String get syncingDeveloperSettings => 'Sinhronizē izstrādātāja iestatījumus...';

  @override
  String get summary => 'Kopsavilkums';

  @override
  String get auto => 'Automātisks';

  @override
  String get noSummaryForApp =>
      'Šai lietotnei kopsavilkums nav pieejams. Izmēģiniet citu lietotni labākiem rezultātiem.';

  @override
  String get tryAnotherApp => 'Izmēģiniet citu lietotni';

  @override
  String generatedBy(String appName) {
    return 'Izveidoja $appName';
  }

  @override
  String get overview => 'Pārskats';

  @override
  String get otherAppResults => 'Citu lietotņu rezultāti';

  @override
  String get unknownApp => 'Nezināma lietotne';

  @override
  String get noSummaryAvailable => 'Nav pieejams kopsavilkums';

  @override
  String get conversationNoSummaryYet => 'Šai sarunai vēl nav kopsavilkuma.';

  @override
  String get chooseSummarizationApp => 'Izvēlieties kopsavilkuma lietotni';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName iestatīta kā noklusējuma kopsavilkuma lietotne';
  }

  @override
  String get letOmiChooseAutomatically => 'Ļaujiet Omi automātiski izvēlēties labāko lietotni';

  @override
  String get deleteConversationConfirmation => 'Vai tiešām vēlaties dzēst šo sarunu? Šo darbību nevar atsaukt.';

  @override
  String get conversationDeleted => 'Saruna dzēsta';

  @override
  String get generatingLink => 'Ģenerē saiti...';

  @override
  String get editConversation => 'Rediģēt sarunu';

  @override
  String get conversationLinkCopiedToClipboard => 'Sarunas saite nokopēta starpliktuvē';

  @override
  String get conversationTranscriptCopiedToClipboard => 'Sarunas transkripts nokopēts starpliktuvē';

  @override
  String get editConversationDialogTitle => 'Rediģēt sarunu';

  @override
  String get changeTheConversationTitle => 'Mainīt sarunas nosaukumu';

  @override
  String get conversationTitle => 'Sarunas nosaukums';

  @override
  String get enterConversationTitle => 'Ievadiet sarunas nosaukumu...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'Sarunas nosaukums veiksmīgi atjaunināts';

  @override
  String get failedToUpdateConversationTitle => 'Neizdevās atjaunināt sarunas nosaukumu';

  @override
  String get errorUpdatingConversationTitle => 'Kļūda, atjauninot sarunas nosaukumu';

  @override
  String get settingUp => 'Iestatīšana...';

  @override
  String get startYourFirstRecording => 'Sāciet savu pirmo ierakstu';

  @override
  String get preparingSystemAudioCapture => 'Notiek sistēmas audio ierakstīšanas sagatavošana';

  @override
  String get clickTheButtonToCaptureAudio =>
      'Noklikšķiniet uz pogas, lai ierakstītu audio tiešraides transkripcijām, AI ieskaitiem un automātiskai saglabāšanai.';

  @override
  String get reconnecting => 'Notiek atkārtota savienošana...';

  @override
  String get recordingPaused => 'Ieraksts apturēts';

  @override
  String get recordingActive => 'Ieraksts aktīvs';

  @override
  String get startRecording => 'Sākt ierakstu';

  @override
  String resumingInCountdown(String countdown) {
    return 'Atsākšana pēc ${countdown}s...';
  }

  @override
  String get tapPlayToResume => 'Pieskarieties atskaņot, lai atsāktu';

  @override
  String get listeningForAudio => 'Klausās audio...';

  @override
  String get preparingAudioCapture => 'Notiek audio ierakstīšanas sagatavošana';

  @override
  String get clickToBeginRecording => 'Noklikšķiniet, lai sāktu ierakstu';

  @override
  String get translated => 'tulkots';

  @override
  String get liveTranscript => 'Tiešraides transkripcija';

  @override
  String segmentsSingular(String count) {
    return '$count segments';
  }

  @override
  String segmentsPlural(String count) {
    return '$count segmenti';
  }

  @override
  String get startRecordingToSeeTranscript => 'Sāciet ierakstu, lai redzētu tiešraides transkripciju';

  @override
  String get paused => 'Apturēts';

  @override
  String get initializing => 'Inicializēšana...';

  @override
  String get recording => 'Ierakstīšana';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'Mikrofons mainīts. Atsākšana pēc ${countdown}s';
  }

  @override
  String get clickPlayToResumeOrStop => 'Noklikšķiniet uz atskaņot, lai atsāktu, vai apturēt, lai pabeigtu';

  @override
  String get settingUpSystemAudioCapture => 'Notiek sistēmas audio ierakstīšanas iestatīšana';

  @override
  String get capturingAudioAndGeneratingTranscript => 'Ieraksta audio un ģenerē transkripciju';

  @override
  String get clickToBeginRecordingSystemAudio => 'Noklikšķiniet, lai sāktu sistēmas audio ierakstu';

  @override
  String get you => 'Jūs';

  @override
  String speakerWithId(String speakerId) {
    return 'Runātājs $speakerId';
  }

  @override
  String get translatedByOmi => 'tulkojis omi';

  @override
  String get backToConversations => 'Atpakaļ uz sarunām';

  @override
  String get systemAudio => 'Sistēma';

  @override
  String get mic => 'Mikrofons';

  @override
  String audioInputSetTo(String deviceName) {
    return 'Audio ievade iestatīta uz $deviceName';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'Kļūda, mainoties audio ierīcei: $error';
  }

  @override
  String get selectAudioInput => 'Atlasiet audio ievadi';

  @override
  String get loadingDevices => 'Ielādē ierīces...';

  @override
  String get settingsHeader => 'IESTATĪJUMI';

  @override
  String get plansAndBilling => 'Plāni un Norēķini';

  @override
  String get calendarIntegration => 'Kalendāra Integrācija';

  @override
  String get dailySummary => 'Dienas kopsavilkums';

  @override
  String get developer => 'Izstrādātājs';

  @override
  String get about => 'Par';

  @override
  String get selectTime => 'Izvēlēties laiku';

  @override
  String get accountGroup => 'Konts';

  @override
  String get signOutQuestion => 'Izrakstīties?';

  @override
  String get signOutConfirmation => 'Vai tiešām vēlaties izrakstīties?';

  @override
  String get customVocabularyHeader => 'PIELĀGOTS VĀRDNĪCA';

  @override
  String get addWordsDescription => 'Pievienojiet vārdus, kurus Omi vajadzētu atpazīt transkripcijas laikā.';

  @override
  String get enterWordsHint => 'Ievadiet vārdus (atdalīti ar komatu)';

  @override
  String get dailySummaryHeader => 'DIENAS KOPSAVILKUMS';

  @override
  String get dailySummaryTitle => 'Dienas Kopsavilkums';

  @override
  String get dailySummaryDescription => 'Saņemiet personalizētu dienas sarunu kopsavilkumu kā paziņojumu.';

  @override
  String get deliveryTime => 'Piegādes laiks';

  @override
  String get deliveryTimeDescription => 'Kad saņemt dienas kopsavilkumu';

  @override
  String get subscription => 'Abonements';

  @override
  String get viewPlansAndUsage => 'Skatīt Plānus un Lietošanu';

  @override
  String get viewPlansDescription => 'Pārvaldiet abonementa un skatiet lietošanas statistiku';

  @override
  String get addOrChangePaymentMethod => 'Pievienojiet vai mainiet maksājuma metodi';

  @override
  String get displayOptions => 'Attēlošanas opcijas';

  @override
  String get showMeetingsInMenuBar => 'Rādīt sapulces izvēlnes joslā';

  @override
  String get displayUpcomingMeetingsDescription => 'Rādīt gaidāmās sapulces izvēlnes joslā';

  @override
  String get showEventsWithoutParticipants => 'Rādīt notikumus bez dalībniekiem';

  @override
  String get includePersonalEventsDescription => 'Iekļaut personīgos notikumus bez dalībniekiem';

  @override
  String get upcomingMeetings => 'Gaidāmās tikšanās';

  @override
  String get checkingNext7Days => 'Pārbaudām nākamās 7 dienas';

  @override
  String get shortcuts => 'Saīsnes';

  @override
  String get shortcutChangeInstruction => 'Noklikšķiniet uz saīsnes, lai to mainītu. Nospiediet Escape, lai atceltu.';

  @override
  String get configurePersonaDescription => 'Konfigurējiet savu AI personu';

  @override
  String get configureSTTProvider => 'Konfigurēt STT nodrošinātāju';

  @override
  String get setConversationEndDescription => 'Iestatiet, kad sarunas automātiski beidzas';

  @override
  String get importDataDescription => 'Importēt datus no citiem avotiem';

  @override
  String get exportConversationsDescription => 'Eksportēt sarunas uz JSON';

  @override
  String get exportingConversations => 'Eksportē sarunas...';

  @override
  String get clearNodesDescription => 'Notīrīt visus mezglus un savienojumus';

  @override
  String get deleteKnowledgeGraphQuestion => 'Dzēst zināšanu grafu?';

  @override
  String get deleteKnowledgeGraphWarning =>
      'Tas izdzēsīs visus atvasinātos zināšanu grafa datus. Jūsu sākotnējās atmiņas paliks drošībā.';

  @override
  String get connectOmiWithAI => 'Savienojiet Omi ar AI asistentiem';

  @override
  String get noAPIKeys => 'Nav API atslēgu. Izveidojiet vienu, lai sāktu.';

  @override
  String get autoCreateWhenDetected => 'Automātiski izveidot, kad tiek konstatēts vārds';

  @override
  String get trackPersonalGoals => 'Izsekot personīgos mērķus sākumlapā';

  @override
  String get dailyReflectionDescription =>
      'Saņemiet atgādinājumu plkst. 21, lai pārdomātu savu dienu un piefiksētu domas.';

  @override
  String get endpointURL => 'Galapunkta URL';

  @override
  String get links => 'Saites';

  @override
  String get discordMemberCount => 'Vairāk nekā 8000 dalībnieku Discord';

  @override
  String get userInformation => 'Lietotāja informācija';

  @override
  String get capabilities => 'Iespējas';

  @override
  String get previewScreenshots => 'Ekrānuzņēmumu priekšskatījums';

  @override
  String get holdOnPreparingForm => 'Uzgaidiet, mēs sagatavojam veidlapu jums';

  @override
  String get bySubmittingYouAgreeToOmi => 'Iesniedzot, jūs piekrītat Omi ';

  @override
  String get termsAndPrivacyPolicy => 'Noteikumi un Privātuma Politika';

  @override
  String get helpsDiagnoseIssuesAutoDeletes => 'Palīdz diagnosticēt problēmas. Automātiski izdzēsts pēc 3 dienām.';

  @override
  String get manageYourApp => 'Pārvaldīt jūsu lietotni';

  @override
  String get updatingYourApp => 'Atjaunina jūsu lietotni';

  @override
  String get fetchingYourAppDetails => 'Iegūst lietotnes informāciju';

  @override
  String get updateAppQuestion => 'Atjaunināt lietotni?';

  @override
  String get updateAppConfirmation =>
      'Vai tiešām vēlaties atjaunināt savu lietotni? Izmaiņas būs redzamas pēc mūsu komandas pārskatīšanas.';

  @override
  String get updateApp => 'Atjaunināt lietotni';

  @override
  String get createAndSubmitNewApp => 'Izveidojiet un iesniedziet jaunu lietotni';

  @override
  String appsCount(String count) {
    return 'Lietotnes ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'Privātās lietotnes ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'Publiskās lietotnes ($count)';
  }

  @override
  String get newVersionAvailable => 'Pieejama jauna versija  🎉';

  @override
  String get no => 'Nē';

  @override
  String get subscriptionCancelledSuccessfully =>
      'Abonements veiksmīgi atcelts. Tas paliks aktīvs līdz pašreizējā norēķinu perioda beigām.';

  @override
  String get failedToCancelSubscription => 'Neizdevās atcelt abonementu. Lūdzu, mēģiniet vēlreiz.';

  @override
  String get invalidPaymentUrl => 'Nederīgs maksājuma URL';

  @override
  String get permissionsAndTriggers => 'Atļaujas un aktivizētāji';

  @override
  String get chatFeatures => 'Tērzēšanas funkcijas';

  @override
  String get uninstall => 'Atinstalēt';

  @override
  String get installs => 'INSTALĀCIJAS';

  @override
  String get priceLabel => 'CENA';

  @override
  String get updatedLabel => 'ATJAUNINĀTS';

  @override
  String get createdLabel => 'IZVEIDOTS';

  @override
  String get featuredLabel => 'IETEIKTS';

  @override
  String get cancelSubscriptionQuestion => 'Atcelt abonementu?';

  @override
  String get cancelSubscriptionConfirmation =>
      'Vai tiešām vēlaties atcelt abonementu? Jums būs piekļuve līdz pašreizējā norēķinu perioda beigām.';

  @override
  String get cancelSubscriptionButton => 'Atcelt abonementu';

  @override
  String get cancelling => 'Atceļ...';

  @override
  String get betaTesterMessage =>
      'Jūs esat šīs lietotnes beta testētājs. Tā vēl nav publiska. Tā kļūs publiska pēc apstiprināšanas.';

  @override
  String get appUnderReviewMessage =>
      'Jūsu lietotne tiek pārskatīta un ir redzama tikai jums. Tā kļūs publiska pēc apstiprināšanas.';

  @override
  String get appRejectedMessage =>
      'Jūsu lietotne tika noraidīta. Lūdzu, atjauniniet informāciju un iesniedziet atkārtoti.';

  @override
  String get invalidIntegrationUrl => 'Nederīgs integrācijas URL';

  @override
  String get tapToComplete => 'Pieskarieties, lai pabeigtu';

  @override
  String get invalidSetupInstructionsUrl => 'Nederīgs iestatīšanas instrukciju URL';

  @override
  String get pushToTalk => 'Spiediet, lai runātu';

  @override
  String get summaryPrompt => 'Kopsavilkuma uzvedne';

  @override
  String get pleaseSelectARating => 'Lūdzu, izvēlieties vērtējumu';

  @override
  String get reviewAddedSuccessfully => 'Atsauksme veiksmīgi pievienota 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'Atsauksme veiksmīgi atjaunināta 🚀';

  @override
  String get failedToSubmitReview => 'Neizdevās iesniegt atsauksmi. Lūdzu, mēģiniet vēlreiz.';

  @override
  String get addYourReview => 'Pievienojiet savu atsauksmi';

  @override
  String get editYourReview => 'Rediģēt savu atsauksmi';

  @override
  String get writeAReviewOptional => 'Uzrakstiet atsauksmi (neobligāti)';

  @override
  String get submitReview => 'Iesniegt atsauksmi';

  @override
  String get updateReview => 'Atjaunināt atsauksmi';

  @override
  String get yourReview => 'Jūsu atsauksme';

  @override
  String get anonymousUser => 'Anonīms lietotājs';

  @override
  String get issueActivatingApp => 'Aktivizējot šo lietotni, radās problēma. Lūdzu, mēģiniet vēlreiz.';

  @override
  String get dataAccessNoticeDescription =>
      'This app will access your data. Omi AI is not responsible for how your data is used, modified, or deleted by this app';

  @override
  String get copyUrl => 'Kopēt URL';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => 'Pr';

  @override
  String get weekdayTue => 'Ot';

  @override
  String get weekdayWed => 'Tr';

  @override
  String get weekdayThu => 'Ce';

  @override
  String get weekdayFri => 'Pk';

  @override
  String get weekdaySat => 'Se';

  @override
  String get weekdaySun => 'Sv';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return '$serviceName integrācija drīzumā';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'Jau eksportēts uz $platform';
  }

  @override
  String get anotherPlatform => 'citu platformu';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'Lūdzu, autentificējieties ar $serviceName Iestatījumi > Uzdevumu integrācijas';
  }

  @override
  String addingToService(String serviceName) {
    return 'Pievieno $serviceName...';
  }

  @override
  String addedToService(String serviceName) {
    return 'Pievienots $serviceName';
  }

  @override
  String failedToAddToService(String serviceName) {
    return 'Neizdevās pievienot $serviceName';
  }

  @override
  String get permissionDeniedForAppleReminders => 'Apple Reminders atļauja liegta';

  @override
  String failedToCreateApiKey(String error) {
    return 'Neizdevās izveidot pakalpojumu sniedzēja API atslēgu: $error';
  }

  @override
  String get createAKey => 'Izveidot atslēgu';

  @override
  String get apiKeyRevokedSuccessfully => 'API atslēga veiksmīgi atsaukta';

  @override
  String failedToRevokeApiKey(String error) {
    return 'Neizdevās atsaukt API atslēgu: $error';
  }

  @override
  String get omiApiKeys => 'Omi API atslēgas';

  @override
  String get apiKeysDescription =>
      'API atslēgas izmanto autentifikācijai, kad jūsu lietotne sazinās ar OMI serveri. Tās ļauj jūsu lietojumprogrammai droši izveidot atmiņas un piekļūt citiem OMI pakalpojumiem.';

  @override
  String get aboutOmiApiKeys => 'Par Omi API atslēgām';

  @override
  String get yourNewKey => 'Jūsu jaunā atslēga:';

  @override
  String get copyToClipboard => 'Kopēt starpliktuvē';

  @override
  String get pleaseCopyKeyNow => 'Lūdzu, nokopējiet to tagad un pierakstiet drošā vietā. ';

  @override
  String get willNotSeeAgain => 'Jūs to vairs nevarēsiet redzēt.';

  @override
  String get revokeKey => 'Atsaukt atslēgu';

  @override
  String get revokeApiKeyQuestion => 'Atsaukt API atslēgu?';

  @override
  String get revokeApiKeyWarning =>
      'Šo darbību nevar atsaukt. Lietojumprogrammas, kas izmanto šo atslēgu, vairs nevarēs piekļūt API.';

  @override
  String get revoke => 'Atsaukt';

  @override
  String get whatWouldYouLikeToCreate => 'Ko vēlaties izveidot?';

  @override
  String get createAnApp => 'Izveidot lietotni';

  @override
  String get createAndShareYourApp => 'Izveidojiet un dalieties ar savu lietotni';

  @override
  String get createMyClone => 'Izveidot manu klonu';

  @override
  String get createYourDigitalClone => 'Izveidojiet savu digitālo klonu';

  @override
  String get itemApp => 'Lietotne';

  @override
  String get itemPersona => 'Persona';

  @override
  String keepItemPublic(String item) {
    return 'Saglabāt $item publisku';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return 'Padarīt $item publisku?';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return 'Padarīt $item privātu?';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'Ja padarīsiet $item publisku, to varēs izmantot visi';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'Ja tagad padarīsiet $item privātu, tā pārtrauks darboties visiem un būs redzama tikai jums';
  }

  @override
  String get manageApp => 'Pārvaldīt lietotni';

  @override
  String get updatePersonaDetails => 'Atjaunināt personas datus';

  @override
  String deleteItemTitle(String item) {
    return 'Dzēst $item';
  }

  @override
  String deleteItemQuestion(String item) {
    return 'Dzēst $item?';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'Vai tiešām vēlaties dzēst šo $item? Šo darbību nevar atsaukt.';
  }

  @override
  String get revokeKeyQuestion => 'Atsaukt atslēgu?';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'Vai tiešām vēlaties atsaukt atslēgu \"$keyName\"? Šo darbību nevar atsaukt.';
  }

  @override
  String get createNewKey => 'Izveidot jaunu atslēgu';

  @override
  String get keyNameHint => 'piem., Claude Desktop';

  @override
  String get pleaseEnterAName => 'Lūdzu, ievadiet nosaukumu.';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'Neizdevās izveidot atslēgu: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'Neizdevās izveidot atslēgu. Lūdzu, mēģiniet vēlreiz.';

  @override
  String get keyCreated => 'Atslēga izveidota';

  @override
  String get keyCreatedMessage =>
      'Jūsu jaunā atslēga ir izveidota. Lūdzu, nokopējiet to tagad. Jūs to vairs neredzēsiet.';

  @override
  String get keyWord => 'Atslēga';

  @override
  String get externalAppAccess => 'Ārējo lietotņu piekļuve';

  @override
  String get externalAppAccessDescription =>
      'Šīm instalētajām lietotnēm ir ārējās integrācijas, un tās var piekļūt jūsu datiem, piemēram, sarunām un atmiņām.';

  @override
  String get noExternalAppsHaveAccess => 'Nevienai ārējai lietotnei nav piekļuves jūsu datiem.';

  @override
  String get maximumSecurityE2ee => 'Maksimāla drošība (E2EE)';

  @override
  String get e2eeDescription =>
      'Pilnīga šifrēšana ir privātuma zelta standarts. Kad tā ir iespējota, jūsu dati tiek šifrēti jūsu ierīcē pirms nosūtīšanas uz mūsu serveriem. Tas nozīmē, ka neviens, pat ne Omi, nevar piekļūt jūsu saturam.';

  @override
  String get importantTradeoffs => 'Svarīgi kompromisi:';

  @override
  String get e2eeTradeoff1 => '• Dažas funkcijas, piemēram, ārējo lietotņu integrācijas, var tikt atspējotas.';

  @override
  String get e2eeTradeoff2 => '• Ja zaudējat paroli, jūsu datus nevar atgūt.';

  @override
  String get featureComingSoon => 'Šī funkcija drīzumā būs pieejama!';

  @override
  String get migrationInProgressMessage =>
      'Migrācija notiek. Jūs nevarat mainīt aizsardzības līmeni, kamēr tā nav pabeigta.';

  @override
  String get migrationFailed => 'Migrācija neizdevās';

  @override
  String migratingFromTo(String source, String target) {
    return 'Migrācija no $source uz $target';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total objekti';
  }

  @override
  String get secureEncryption => 'Droša šifrēšana';

  @override
  String get secureEncryptionDescription =>
      'Jūsu dati tiek šifrēti ar jums unikālu atslēgu mūsu serveros, kas mitināti Google Cloud. Tas nozīmē, ka jūsu neapstrādātais saturs nav pieejams nevienam, ieskaitot Omi darbiniekus vai Google, tieši no datu bāzes.';

  @override
  String get endToEndEncryption => 'Pilnīga šifrēšana';

  @override
  String get e2eeCardDescription =>
      'Iespējojiet maksimālu drošību, kur tikai jūs varat piekļūt saviem datiem. Pieskarieties, lai uzzinātu vairāk.';

  @override
  String get dataAlwaysEncrypted =>
      'Neatkarīgi no līmeņa, jūsu dati vienmēr ir šifrēti miera stāvoklī un pārsūtīšanas laikā.';

  @override
  String get readOnlyScope => 'Tikai lasīšana';

  @override
  String get fullAccessScope => 'Pilna piekļuve';

  @override
  String get readScope => 'Lasīt';

  @override
  String get writeScope => 'Rakstīt';

  @override
  String get apiKeyCreated => 'API atslēga izveidota!';

  @override
  String get saveKeyWarning => 'Saglabājiet šo atslēgu tagad! Jūs to vairs nevarēsiet redzēt.';

  @override
  String get yourApiKey => 'JŪSU API ATSLĒGA';

  @override
  String get tapToCopy => 'Pieskarieties, lai kopētu';

  @override
  String get copyKey => 'Kopēt atslēgu';

  @override
  String get createApiKey => 'Izveidot API atslēgu';

  @override
  String get accessDataProgrammatically => 'Piekļūstiet saviem datiem programmatiski';

  @override
  String get keyNameLabel => 'ATSLĒGAS NOSAUKUMS';

  @override
  String get keyNamePlaceholder => 'piem., Manas lietotnes integrācija';

  @override
  String get permissionsLabel => 'ATĻAUJAS';

  @override
  String get permissionsInfoNote => 'R = Lasīt, W = Rakstīt. Noklusējums tikai lasīšana, ja nekas nav atlasīts.';

  @override
  String get developerApi => 'Izstrādātāja API';

  @override
  String get createAKeyToGetStarted => 'Izveidojiet atslēgu, lai sāktu';

  @override
  String errorWithMessage(String error) {
    return 'Kļūda: $error';
  }

  @override
  String get omiTraining => 'Omi apmācība';

  @override
  String get trainingDataProgram => 'Apmācības datu programma';

  @override
  String get getOmiUnlimitedFree => 'Iegūstiet Omi Unlimited bez maksas, sniedzot savus datus AI modeļu apmācībai.';

  @override
  String get trainingDataBullets =>
      '• Jūsu dati palīdz uzlabot AI modeļus\n• Tiek kopīgoti tikai nejutīgi dati\n• Pilnībā pārredzams process';

  @override
  String get learnMoreAtOmiTraining => 'Uzziniet vairāk vietnē omi.me/training';

  @override
  String get agreeToContributeData => 'Es saprotu un piekrītu sniegt savus datus AI apmācībai';

  @override
  String get submitRequest => 'Iesniegt pieprasījumu';

  @override
  String get thankYouRequestUnderReview =>
      'Paldies! Jūsu pieprasījums tiek izskatīts. Mēs jūs informēsim pēc apstiprināšanas.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'Jūsu plāns paliks aktīvs līdz $date. Pēc tam jūs zaudēsiet piekļuvi neierobežotajām funkcijām. Vai esat pārliecināts?';
  }

  @override
  String get confirmCancellation => 'Apstiprināt atcelšanu';

  @override
  String get keepMyPlan => 'Paturēt manu plānu';

  @override
  String get subscriptionSetToCancel => 'Jūsu abonements ir iestatīts atcelšanai perioda beigās.';

  @override
  String get switchedToOnDevice => 'Pārslēgts uz ierīces transkripciju';

  @override
  String get couldNotSwitchToFreePlan => 'Nevarēja pārslēgties uz bezmaksas plānu. Lūdzu, mēģiniet vēlreiz.';

  @override
  String get couldNotLoadPlans => 'Nevarēja ielādēt pieejamos plānus. Lūdzu, mēģiniet vēlreiz.';

  @override
  String get selectedPlanNotAvailable => 'Izvēlētais plāns nav pieejams. Lūdzu, mēģiniet vēlreiz.';

  @override
  String get upgradeToAnnualPlan => 'Jaunināt uz gada plānu';

  @override
  String get importantBillingInfo => 'Svarīga norēķinu informācija:';

  @override
  String get monthlyPlanContinues => 'Jūsu pašreizējais mēneša plāns turpināsies līdz norēķinu perioda beigām';

  @override
  String get paymentMethodCharged =>
      'Jūsu esošais maksājuma veids tiks automātiski iekasēts, kad beigsies jūsu mēneša plāns';

  @override
  String get annualSubscriptionStarts => 'Jūsu 12 mēnešu gada abonements automātiski sāksies pēc maksājuma';

  @override
  String get thirteenMonthsCoverage => 'Jūs saņemsiet kopumā 13 mēnešu segumu (pašreizējais mēnesis + 12 mēneši gadā)';

  @override
  String get confirmUpgrade => 'Apstiprināt jaunināšanu';

  @override
  String get confirmPlanChange => 'Apstiprināt plāna maiņu';

  @override
  String get confirmAndProceed => 'Apstiprināt un turpināt';

  @override
  String get upgradeScheduled => 'Jaunināšana ieplānota';

  @override
  String get changePlan => 'Mainīt plānu';

  @override
  String get upgradeAlreadyScheduled => 'Jūsu jaunināšana uz gada plānu jau ir ieplānota';

  @override
  String get youAreOnUnlimitedPlan => 'Jūs esat Neierobežotajā plānā.';

  @override
  String get yourOmiUnleashed => 'Jūsu Omi, atbrīvots. Kļūstiet neierobežots bezgalīgām iespējām.';

  @override
  String planEndedOn(String date) {
    return 'Jūsu plāns beidzās $date.\\nAbonejiet atkārtoti tagad - jums nekavējoties tiks iekasēta maksa par jauno norēķinu periodu.';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'Jūsu plāns ir iestatīts atcelšanai $date.\\nAbonejiet atkārtoti tagad, lai saglabātu savus ieguvumus - bez maksas līdz $date.';
  }

  @override
  String get annualPlanStartsAutomatically => 'Jūsu gada plāns automātiski sāksies, kad beigsies jūsu mēneša plāns.';

  @override
  String planRenewsOn(String date) {
    return 'Jūsu plāns tiek atjaunots $date.';
  }

  @override
  String get unlimitedConversations => 'Neierobežotas sarunas';

  @override
  String get askOmiAnything => 'Jautājiet Omi jebko par savu dzīvi';

  @override
  String get unlockOmiInfiniteMemory => 'Atbloķējiet Omi bezgalīgo atmiņu';

  @override
  String get youreOnAnnualPlan => 'Jūs esat gada plānā';

  @override
  String get alreadyBestValuePlan => 'Jums jau ir vislabākās vērtības plāns. Nav nepieciešamas izmaiņas.';

  @override
  String get unableToLoadPlans => 'Nevar ielādēt plānus';

  @override
  String get checkConnectionTryAgain => 'Lūdzu, pārbaudiet savienojumu un mēģiniet vēlreiz';

  @override
  String get useFreePlan => 'Izmantot bezmaksas plānu';

  @override
  String get continueText => 'Turpināt';

  @override
  String get resubscribe => 'Atkārtoti abonēt';

  @override
  String get couldNotOpenPaymentSettings => 'Nevarēja atvērt maksājumu iestatījumus. Lūdzu, mēģiniet vēlreiz.';

  @override
  String get managePaymentMethod => 'Pārvaldīt maksājuma veidu';

  @override
  String get cancelSubscription => 'Atcelt abonementu';

  @override
  String endsOnDate(String date) {
    return 'Beidzas $date';
  }

  @override
  String get active => 'Aktīvs';

  @override
  String get freePlan => 'Bezmaksas plāns';

  @override
  String get configure => 'Konfigurēt';

  @override
  String get privacyInformation => 'Privātuma informācija';

  @override
  String get yourPrivacyMattersToUs => 'Jūsu privātums mums ir svarīgs';

  @override
  String get privacyIntroText =>
      'Omi mēs ļoti nopietni uztveram jūsu privātumu. Mēs vēlamies būt caurspīdīgi par datiem, ko apkopojam un kā tos izmantojam. Lūk, kas jums jāzina:';

  @override
  String get whatWeTrack => 'Ko mēs izsekojam';

  @override
  String get anonymityAndPrivacy => 'Anonimitāte un privātums';

  @override
  String get optInAndOptOutOptions => 'Piekrišanas un atteikšanās iespējas';

  @override
  String get ourCommitment => 'Mūsu apņemšanās';

  @override
  String get commitmentText =>
      'Mēs esam apņēmušies izmantot apkopotos datus tikai, lai padarītu Omi par labāku produktu jums. Jūsu privātums un uzticība mums ir vissvarīgākā.';

  @override
  String get thankYouText =>
      'Paldies, ka esat vērtīgs Omi lietotājs. Ja jums ir kādi jautājumi vai bažas, sazinieties ar mums pa team@basedhardware.com.';

  @override
  String get wifiSyncSettings => 'WiFi sinhronizācijas iestatījumi';

  @override
  String get enterHotspotCredentials => 'Ievadiet tālruņa tīklāja akreditācijas datus';

  @override
  String get wifiSyncUsesHotspot =>
      'WiFi sinhronizācija izmanto jūsu tālruni kā tīklāju. Atrodiet nosaukumu un paroli sadaļā Iestatījumi > Personālais tīklājs.';

  @override
  String get hotspotNameSsid => 'Tīklāja nosaukums (SSID)';

  @override
  String get exampleIphoneHotspot => 'piem. iPhone Hotspot';

  @override
  String get password => 'Parole';

  @override
  String get enterHotspotPassword => 'Ievadiet tīklāja paroli';

  @override
  String get saveCredentials => 'Saglabāt akreditācijas datus';

  @override
  String get clearCredentials => 'Notīrīt akreditācijas datus';

  @override
  String get pleaseEnterHotspotName => 'Lūdzu, ievadiet tīklāja nosaukumu';

  @override
  String get wifiCredentialsSaved => 'WiFi akreditācijas dati saglabāti';

  @override
  String get wifiCredentialsCleared => 'WiFi akreditācijas dati notīrīti';

  @override
  String summaryGeneratedForDate(String date) {
    return 'Kopsavilkums izveidots $date';
  }

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'Neizdevās izveidot kopsavilkumu. Pārliecinieties, ka jums ir sarunas par šo dienu.';

  @override
  String get summaryNotFound => 'Kopsavilkums nav atrasts';

  @override
  String get yourDaysJourney => 'Jūsu dienas ceļojums';

  @override
  String get highlights => 'Galvenie punkti';

  @override
  String get unresolvedQuestions => 'Neatrisināti jautājumi';

  @override
  String get decisions => 'Lēmumi';

  @override
  String get learnings => 'Mācības';

  @override
  String get autoDeletesAfterThreeDays => 'Automātiski dzēš pēc 3 dienām.';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'Zināšanu grafs veiksmīgi izdzēsts';

  @override
  String get exportStartedMayTakeFewSeconds => 'Eksports sākts. Tas var aizņemt dažas sekundes...';

  @override
  String get knowledgeGraphDeleteDescription =>
      'Tas dzēsīs visus atvasinātos zināšanu grafa datus (mezglus un savienojumus). Jūsu sākotnējās atmiņas paliks drošībā. Grafs tiks atjaunots laika gaitā vai nākamajā pieprasījumā.';

  @override
  String get configureDailySummaryDigest => 'Konfigurējiet savu ikdienas uzdevumu kopsavilkumu';

  @override
  String accessesDataTypes(String dataTypes) {
    return 'Piekļūst $dataTypes';
  }

  @override
  String triggeredByType(String triggerType) {
    return 'aktivizē $triggerType';
  }

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription un ir $triggerDescription.';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return 'Ir $triggerDescription.';
  }

  @override
  String get noSpecificDataAccessConfigured => 'Nav konfigurēta specifiska datu piekļuve.';

  @override
  String get basicPlanDescription => '1200 premium minūtes + neierobežots ierīcē';

  @override
  String get minutes => 'minūtes';

  @override
  String get omiHas => 'Omi ir:';

  @override
  String get premiumMinutesUsed => 'Premium minūtes izmantotas.';

  @override
  String get setupOnDevice => 'Iestatīt ierīcē';

  @override
  String get forUnlimitedFreeTranscription => 'neierobežotai bezmaksas transkripcijai.';

  @override
  String premiumMinsLeft(int count) {
    return 'Atlikušas $count premium minūtes.';
  }

  @override
  String get alwaysAvailable => 'vienmēr pieejams.';

  @override
  String get importHistory => 'Importēšanas vēsture';

  @override
  String get noImportsYet => 'Vēl nav importu';

  @override
  String get selectZipFileToImport => 'Izvēlieties importēšanai .zip failu!';

  @override
  String get otherDevicesComingSoon => 'Citas ierīces drīzumā';

  @override
  String get deleteAllLimitlessConversations => 'Dzēst visas Limitless sarunas?';

  @override
  String get deleteAllLimitlessWarning =>
      'Tas neatgriezeniski izdzēsīs visas no Limitless importētās sarunas. Šo darbību nevar atsaukt.';

  @override
  String deletedLimitlessConversations(int count) {
    return 'Dzēstas $count Limitless sarunas';
  }

  @override
  String get failedToDeleteConversations => 'Neizdevās dzēst sarunas';

  @override
  String get deleteImportedData => 'Dzēst importētos datus';

  @override
  String get statusPending => 'Gaida';

  @override
  String get statusProcessing => 'Apstrādā';

  @override
  String get statusCompleted => 'Pabeigts';

  @override
  String get statusFailed => 'Neizdevās';

  @override
  String nConversations(int count) {
    return '$count sarunas';
  }

  @override
  String get pleaseEnterName => 'Lūdzu, ievadiet vārdu';

  @override
  String get nameMustBeBetweenCharacters => 'Vārdam jābūt no 2 līdz 40 rakstzīmēm';

  @override
  String get deleteSampleQuestion => 'Dzēst paraugu?';

  @override
  String deleteSampleConfirmation(String name) {
    return 'Vai tiešām vēlaties dzēst $name paraugu?';
  }

  @override
  String get confirmDeletion => 'Apstiprināt dzēšanu';

  @override
  String deletePersonConfirmation(String name) {
    return 'Vai tiešām vēlaties dzēst $name? Tas arī noņems visus saistītos runas paraugus.';
  }

  @override
  String get howItWorksTitle => 'Kā tas darbojas?';

  @override
  String get howPeopleWorks =>
      'Kad persona ir izveidota, varat doties uz sarunas transkripciju un piešķirt viņiem atbilstošos segmentus, tādā veidā Omi varēs atpazīt arī viņu runu!';

  @override
  String get tapToDelete => 'Pieskarieties, lai dzēstu';

  @override
  String get newTag => 'JAUNS';

  @override
  String get needHelpChatWithUs => 'Nepieciešama palīdzība? Sazinies ar mums';

  @override
  String get localStorageEnabled => 'Lokālā krātuve iespējota';

  @override
  String get localStorageDisabled => 'Lokālā krātuve atspējota';

  @override
  String failedToUpdateSettings(String error) {
    return 'Neizdevās atjaunināt iestatījumus: $error';
  }

  @override
  String get privacyNotice => 'Privātuma paziņojums';

  @override
  String get recordingsMayCaptureOthers =>
      'Ieraksti var ierakstīt citu cilvēku balsis. Pirms iespējošanas pārliecinieties, ka esat saņēmis visu dalībnieku piekrišanu.';

  @override
  String get enable => 'Iespējot';

  @override
  String get storeAudioOnPhone => 'Store Audio on Phone';

  @override
  String get on => 'On';

  @override
  String get storeAudioDescription =>
      'Saglabājiet visus audio ierakstus lokāli savā tālrunī. Kad ir atspējots, tiek saglabāti tikai neveiksmīgie augšupielādēšanas gadījumi, lai ietaupītu vietu.';

  @override
  String get enableLocalStorage => 'Iespējot lokālo krātuvi';

  @override
  String get cloudStorageEnabled => 'Mākoņkrātuve iespējota';

  @override
  String get cloudStorageDisabled => 'Mākoņkrātuve atspējota';

  @override
  String get enableCloudStorage => 'Iespējot mākoņkrātuvi';

  @override
  String get storeAudioOnCloud => 'Store Audio on Cloud';

  @override
  String get cloudStorageDialogMessage => 'Jūsu reāllaika ieraksti tiks glabāti privātā mākoņkrātuvē, kamēr runājat.';

  @override
  String get storeAudioCloudDescription =>
      'Saglabājiet savus reāllaika ierakstus privātā mākoņkrātuvē, kamēr runājat. Audio tiek tverts un droši saglabāts reāllaikā.';

  @override
  String get downloadingFirmware => 'Lejupielādē programmaparatūru';

  @override
  String get installingFirmware => 'Instalē programmaparatūru';

  @override
  String get firmwareUpdateWarning => 'Neaizveriet lietotni un neizslēdziet ierīci. Tas var sabojāt jūsu ierīci.';

  @override
  String get firmwareUpdated => 'Programmaparatūra atjaunināta';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'Lūdzu, restartējiet $deviceName, lai pabeigtu atjauninājumu.';
  }

  @override
  String get yourDeviceIsUpToDate => 'Jūsu ierīce ir atjaunināta';

  @override
  String get currentVersion => 'Pašreizējā versija';

  @override
  String get latestVersion => 'Jaunākā versija';

  @override
  String get whatsNew => 'Kas jauns';

  @override
  String get installUpdate => 'Instalēt atjauninājumu';

  @override
  String get updateNow => 'Atjaunināt tagad';

  @override
  String get updateGuide => 'Atjaunināšanas ceļvedis';

  @override
  String get checkingForUpdates => 'Pārbauda atjauninājumus';

  @override
  String get checkingFirmwareVersion => 'Pārbauda programmaparatūras versiju...';

  @override
  String get firmwareUpdate => 'Programmaparatūras atjauninājums';

  @override
  String get payments => 'Maksājumi';

  @override
  String get connectPaymentMethodInfo =>
      'Pievienojiet maksājuma metodi zemāk, lai sāktu saņemt maksājumus par savām lietotnēm.';

  @override
  String get selectedPaymentMethod => 'Izvēlētā maksājuma metode';

  @override
  String get availablePaymentMethods => 'Pieejamās maksājuma metodes';

  @override
  String get activeStatus => 'Aktīvs';

  @override
  String get connectedStatus => 'Savienots';

  @override
  String get notConnectedStatus => 'Nav savienots';

  @override
  String get setActive => 'Iestatīt kā aktīvu';

  @override
  String get getPaidThroughStripe => 'Saņemiet maksājumus par lietotņu pārdošanu caur Stripe';

  @override
  String get monthlyPayouts => 'Ikmēneša maksājumi';

  @override
  String get monthlyPayoutsDescription =>
      'Saņemiet ikmēneša maksājumus tieši savā kontā, kad sasniedzat \$10 ieņēmumus';

  @override
  String get secureAndReliable => 'Drošs un uzticams';

  @override
  String get stripeSecureDescription => 'Stripe nodrošina drošus un savlaicīgus jūsu lietotnes ieņēmumu pārskaitījumus';

  @override
  String get selectYourCountry => 'Izvēlieties savu valsti';

  @override
  String get countrySelectionPermanent => 'Jūsu valsts izvēle ir pastāvīga un to nevar mainīt vēlāk.';

  @override
  String get byClickingConnectNow => 'Noklikšķinot uz \"Savienot tagad\" jūs piekrītat';

  @override
  String get stripeConnectedAccountAgreement => 'Stripe savienotā konta līgums';

  @override
  String get errorConnectingToStripe => 'Kļūda savienojot ar Stripe! Lūdzu, mēģiniet vēlāk.';

  @override
  String get connectingYourStripeAccount => 'Jūsu Stripe konta savienošana';

  @override
  String get stripeOnboardingInstructions =>
      'Lūdzu, pabeidziet Stripe reģistrācijas procesu savā pārlūkprogrammā. Šī lapa tiks automātiski atjaunināta pēc pabeigšanas.';

  @override
  String get failedTryAgain => 'Neizdevās? Mēģināt vēlreiz';

  @override
  String get illDoItLater => 'Es to izdarīšu vēlāk';

  @override
  String get successfullyConnected => 'Veiksmīgi savienots!';

  @override
  String get stripeReadyForPayments =>
      'Jūsu Stripe konts tagad ir gatavs saņemt maksājumus. Jūs varat nekavējoties sākt pelnīt no savu lietotņu pārdošanas.';

  @override
  String get updateStripeDetails => 'Atjaunināt Stripe informāciju';

  @override
  String get errorUpdatingStripeDetails => 'Kļūda atjauninot Stripe informāciju! Lūdzu, mēģiniet vēlāk.';

  @override
  String get updatePayPal => 'Atjaunināt PayPal';

  @override
  String get setUpPayPal => 'Iestatīt PayPal';

  @override
  String get updatePayPalAccountDetails => 'Atjauniniet sava PayPal konta informāciju';

  @override
  String get connectPayPalToReceivePayments =>
      'Pievienojiet savu PayPal kontu, lai sāktu saņemt maksājumus par savām lietotnēm';

  @override
  String get paypalEmail => 'PayPal e-pasts';

  @override
  String get paypalMeLink => 'PayPal.me saite';

  @override
  String get stripeRecommendation =>
      'Ja Stripe ir pieejams jūsu valstī, mēs ļoti iesakām to izmantot ātrākiem un vienkāršākiem maksājumiem.';

  @override
  String get updatePayPalDetails => 'Atjaunināt PayPal informāciju';

  @override
  String get savePayPalDetails => 'Saglabāt PayPal informāciju';

  @override
  String get pleaseEnterPayPalEmail => 'Lūdzu, ievadiet savu PayPal e-pastu';

  @override
  String get pleaseEnterPayPalMeLink => 'Lūdzu, ievadiet savu PayPal.me saiti';

  @override
  String get doNotIncludeHttpInLink => 'Neiekļaujiet saitē http, https vai www';

  @override
  String get pleaseEnterValidPayPalMeLink => 'Lūdzu, ievadiet derīgu PayPal.me saiti';

  @override
  String get pleaseEnterValidEmail => 'Lūdzu, ievadiet derīgu e-pasta adresi';

  @override
  String get syncingYourRecordings => 'Sinhronizē jūsu ierakstus';

  @override
  String get syncYourRecordings => 'Sinhronizējiet savus ierakstus';

  @override
  String get syncNow => 'Sinhronizēt tagad';

  @override
  String get error => 'Kļūda';

  @override
  String get speechSamples => 'Balss paraugi';

  @override
  String additionalSampleIndex(String index) {
    return 'Papildu paraugs $index';
  }

  @override
  String durationSeconds(String seconds) {
    return 'Ilgums: $seconds sekundes';
  }

  @override
  String get additionalSpeechSampleRemoved => 'Papildu balss paraugs noņemts';

  @override
  String get consentDataMessage =>
      'Turpinot, visi dati, ko kopīgojat ar šo lietotni (tostarp jūsu sarunas, ierakstus un personisko informāciju), tiks droši glabāti mūsu serveros, lai sniegtu jums AI balstītas atziņas un iespējotu visas lietotnes funkcijas.';

  @override
  String get tasksEmptyStateMessage =>
      'Uzdevumi no jūsu sarunām parādīsies šeit.\nPieskarieties +, lai izveidotu manuāli.';

  @override
  String get clearChatAction => 'Notīrīt tērzēšanu';

  @override
  String get enableApps => 'Iespējot lietotnes';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => 'rādīt vairāk ↓';

  @override
  String get showLess => 'rādīt mazāk ↑';

  @override
  String get loadingYourRecording => 'Ielādē ierakstu...';

  @override
  String get photoDiscardedMessage => 'Šī fotogrāfija tika atmesta, jo tā nebija nozīmīga.';

  @override
  String get analyzing => 'Analizē...';

  @override
  String get searchCountries => 'Meklēt valstis...';

  @override
  String get checkingAppleWatch => 'Pārbauda Apple Watch...';

  @override
  String get installOmiOnAppleWatch => 'Instalējiet Omi savā\nApple Watch';

  @override
  String get installOmiOnAppleWatchDescription =>
      'Lai izmantotu Apple Watch ar Omi, vispirms jāinstalē Omi lietotne pulkstenī.';

  @override
  String get openOmiOnAppleWatch => 'Atveriet Omi savā\nApple Watch';

  @override
  String get openOmiOnAppleWatchDescription =>
      'Omi lietotne ir instalēta jūsu Apple Watch. Atveriet to un pieskarieties Sākt.';

  @override
  String get openWatchApp => 'Atvērt Watch lietotni';

  @override
  String get iveInstalledAndOpenedTheApp => 'Esmu instalējis un atvēris lietotni';

  @override
  String get unableToOpenWatchApp =>
      'Nevar atvērt Apple Watch lietotni. Lūdzu, manuāli atveriet Watch lietotni savā Apple Watch un instalējiet Omi no sadaļas \"Pieejamās lietotnes\".';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch veiksmīgi savienots!';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch joprojām nav sasniedzams. Lūdzu, pārliecinieties, ka Omi lietotne ir atvērta jūsu pulkstenī.';

  @override
  String errorCheckingConnection(String error) {
    return 'Savienojuma pārbaudes kļūda: $error';
  }

  @override
  String get muted => 'Izslēgts skaņa';

  @override
  String get processNow => 'Apstrādāt tagad';

  @override
  String get finishedConversation => 'Saruna pabeigta?';

  @override
  String get stopRecordingConfirmation => 'Vai tiešām vēlaties apturēt ierakstīšanu un apkopot sarunu tagad?';

  @override
  String get conversationEndsManually => 'Saruna beigsies tikai manuāli.';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'Saruna tiek apkopota pēc $minutes minūt$suffix klusuma.';
  }

  @override
  String get dontAskAgain => 'Vairs nejautāt';

  @override
  String get waitingForTranscriptOrPhotos => 'Gaida transkripciju vai fotoattēlus...';

  @override
  String get noSummaryYet => 'Vēl nav kopsavilkuma';

  @override
  String hints(String text) {
    return 'Padomi: $text';
  }

  @override
  String get testConversationPrompt => 'Testēt sarunas uzvedni';

  @override
  String get prompt => 'Uzvedne';

  @override
  String get result => 'Rezultāts:';

  @override
  String get compareTranscripts => 'Salīdzināt transkripcijas';

  @override
  String get notHelpful => 'Nav noderīgs';

  @override
  String get exportTasksWithOneTap => 'Eksportējiet uzdevumus ar vienu pieskārienu!';

  @override
  String get inProgress => 'Notiek';

  @override
  String get photos => 'Fotoattēli';

  @override
  String get rawData => 'Neapstrādāti dati';

  @override
  String get content => 'Saturs';

  @override
  String get noContentToDisplay => 'Nav satura, ko parādīt';

  @override
  String get noSummary => 'Nav kopsavilkuma';

  @override
  String get updateOmiFirmware => 'Atjaunināt omi programmaparatūru';

  @override
  String get anErrorOccurredTryAgain => 'Radās kļūda. Lūdzu, mēģiniet vēlreiz.';

  @override
  String get welcomeBackSimple => 'Laipni lūdzam atpakaļ';

  @override
  String get addVocabularyDescription => 'Pievienojiet vārdus, ko Omi vajadzētu atpazīt transkripcijas laikā.';

  @override
  String get enterWordsCommaSeparated => 'Ievadiet vārdus (atdalītus ar komatiem)';

  @override
  String get whenToReceiveDailySummary => 'Kad saņemt ikdienas kopsavilkumu';

  @override
  String get checkingNextSevenDays => 'Pārbaudot nākamās 7 dienas';

  @override
  String failedToDeleteError(String error) {
    return 'Neizdevās dzēst: $error';
  }

  @override
  String get developerApiKeys => 'Izstrādātāja API atslēgas';

  @override
  String get noApiKeysCreateOne => 'Nav API atslēgu. Izveidojiet vienu, lai sāktu.';

  @override
  String get commandRequired => '⌘ ir nepieciešams';

  @override
  String get spaceKey => 'Atstarpe';

  @override
  String loadMoreRemaining(String count) {
    return 'Ielādēt vairāk ($count atlikuši)';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'Top $percentile% lietotājs';
  }

  @override
  String get wrappedMinutes => 'minūtes';

  @override
  String get wrappedConversations => 'sarunas';

  @override
  String get wrappedDaysActive => 'aktīvas dienas';

  @override
  String get wrappedYouTalkedAbout => 'Jūs runājāt par';

  @override
  String get wrappedActionItems => 'Uzdevumi';

  @override
  String get wrappedTasksCreated => 'izveidotie uzdevumi';

  @override
  String get wrappedCompleted => 'pabeigti';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% pabeigšanas rādītājs';
  }

  @override
  String get wrappedYourTopDays => 'Jūsu labākās dienas';

  @override
  String get wrappedBestMoments => 'Labākie mirkļi';

  @override
  String get wrappedMyBuddies => 'Mani draugi';

  @override
  String get wrappedCouldntStopTalkingAbout => 'Nevarēju pārstāt runāt par';

  @override
  String get wrappedShow => 'SERIĀLS';

  @override
  String get wrappedMovie => 'FILMA';

  @override
  String get wrappedBook => 'GRĀMATA';

  @override
  String get wrappedCelebrity => 'SLAVENĪBA';

  @override
  String get wrappedFood => 'ĒDIENS';

  @override
  String get wrappedMovieRecs => 'Filmu ieteikumi draugiem';

  @override
  String get wrappedBiggest => 'Lielākais';

  @override
  String get wrappedStruggle => 'Izaicinājums';

  @override
  String get wrappedButYouPushedThrough => 'Bet jūs tikāt galā 💪';

  @override
  String get wrappedWin => 'Uzvara';

  @override
  String get wrappedYouDidIt => 'Jūs to izdarījāt! 🎉';

  @override
  String get wrappedTopPhrases => 'Top 5 frāzes';

  @override
  String get wrappedMins => 'min';

  @override
  String get wrappedConvos => 'sarunas';

  @override
  String get wrappedDays => 'dienas';

  @override
  String get wrappedMyBuddiesLabel => 'MANI DRAUGI';

  @override
  String get wrappedObsessionsLabel => 'OBSESIJAS';

  @override
  String get wrappedStruggleLabel => 'IZAICINĀJUMS';

  @override
  String get wrappedWinLabel => 'UZVARA';

  @override
  String get wrappedTopPhrasesLabel => 'TOP FRĀZES';

  @override
  String get wrappedLetsHitRewind => 'Attīsim atpakaļ tavu';

  @override
  String get wrappedGenerateMyWrapped => 'Ģenerēt manu Wrapped';

  @override
  String get wrappedProcessingDefault => 'Apstrādā...';

  @override
  String get wrappedCreatingYourStory => 'Veidojam tavu\n2025 stāstu...';

  @override
  String get wrappedSomethingWentWrong => 'Kaut kas\nnogāja greizi';

  @override
  String get wrappedAnErrorOccurred => 'Radās kļūda';

  @override
  String get wrappedTryAgain => 'Mēģināt vēlreiz';

  @override
  String get wrappedNoDataAvailable => 'Nav pieejamu datu';

  @override
  String get wrappedOmiLifeRecap => 'Omi dzīves kopsavilkums';

  @override
  String get wrappedSwipeUpToBegin => 'Velciet uz augšu, lai sāktu';

  @override
  String get wrappedShareText => 'Mans 2025, atcerējies Omi ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare => 'Kopīgošana neizdevās. Lūdzu, mēģiniet vēlreiz.';

  @override
  String get wrappedFailedToStartGeneration => 'Ģenerēšanas sākšana neizdevās. Lūdzu, mēģiniet vēlreiz.';

  @override
  String get wrappedStarting => 'Sāk...';

  @override
  String get wrappedShare => 'Kopīgot';

  @override
  String get wrappedShareYourWrapped => 'Kopīgo savu Wrapped';

  @override
  String get wrappedMy2025 => 'Mans 2025';

  @override
  String get wrappedRememberedByOmi => 'atcerējies Omi';

  @override
  String get wrappedMostFunDay => 'Jautrākā';

  @override
  String get wrappedMostProductiveDay => 'Produktīvākā';

  @override
  String get wrappedMostIntenseDay => 'Intensīvākā';

  @override
  String get wrappedFunniestMoment => 'Jautrākais';

  @override
  String get wrappedMostCringeMoment => 'Neērtākais';

  @override
  String get wrappedMinutesLabel => 'minūtes';

  @override
  String get wrappedConversationsLabel => 'sarunas';

  @override
  String get wrappedDaysActiveLabel => 'aktīvas dienas';

  @override
  String get wrappedTasksGenerated => 'izveidoti uzdevumi';

  @override
  String get wrappedTasksCompleted => 'pabeigti uzdevumi';

  @override
  String get wrappedTopFivePhrases => 'Top 5 frāzes';

  @override
  String get wrappedAGreatDay => 'Lieliska diena';

  @override
  String get wrappedGettingItDone => 'Paveikt to';

  @override
  String get wrappedAChallenge => 'Izaicinājums';

  @override
  String get wrappedAHilariousMoment => 'Jautrs brīdis';

  @override
  String get wrappedThatAwkwardMoment => 'Tas neērtais brīdis';

  @override
  String get wrappedYouHadFunnyMoments => 'Tev bija jautri brīži šogad!';

  @override
  String get wrappedWeveAllBeenThere => 'Mēs visi esam tur bijuši!';

  @override
  String get wrappedFriend => 'Draugs';

  @override
  String get wrappedYourBuddy => 'Tavs draugs!';

  @override
  String get wrappedNotMentioned => 'Nav minēts';

  @override
  String get wrappedTheHardPart => 'Grūtā daļa';

  @override
  String get wrappedPersonalGrowth => 'Personīgā izaugsme';

  @override
  String get wrappedFunDay => 'Jautra';

  @override
  String get wrappedProductiveDay => 'Produktīva';

  @override
  String get wrappedIntenseDay => 'Intensīva';

  @override
  String get wrappedFunnyMomentTitle => 'Jautrs brīdis';

  @override
  String get wrappedCringeMomentTitle => 'Neērts brīdis';

  @override
  String get wrappedYouTalkedAboutBadge => 'Tu runāji par';

  @override
  String get wrappedCompletedLabel => 'Pabeigts';

  @override
  String get wrappedMyBuddiesCard => 'Mani draugi';

  @override
  String get wrappedBuddiesLabel => 'DRAUGI';

  @override
  String get wrappedObsessionsLabelUpper => 'AIZRAUŠANĀS';

  @override
  String get wrappedStruggleLabelUpper => 'CĪŅA';

  @override
  String get wrappedWinLabelUpper => 'UZVARA';

  @override
  String get wrappedTopPhrasesLabelUpper => 'TOP FRĀZES';

  @override
  String get wrappedYourHeader => 'Tavas';

  @override
  String get wrappedTopDaysHeader => 'Labākās dienas';

  @override
  String get wrappedYourTopDaysBadge => 'Tavas labākās dienas';

  @override
  String get wrappedBestHeader => 'Labākās';

  @override
  String get wrappedMomentsHeader => 'Mirkļi';

  @override
  String get wrappedBestMomentsBadge => 'Labākie mirkļi';

  @override
  String get wrappedBiggestHeader => 'Lielākā';

  @override
  String get wrappedStruggleHeader => 'Cīņa';

  @override
  String get wrappedWinHeader => 'Uzvara';

  @override
  String get wrappedButYouPushedThroughEmoji => 'Bet tu to pārvarēji 💪';

  @override
  String get wrappedYouDidItEmoji => 'Tu to izdarīji! 🎉';

  @override
  String get wrappedHours => 'stundas';

  @override
  String get wrappedActions => 'darbības';

  @override
  String get multipleSpeakersDetected => 'Konstatēti vairāki runātāji';

  @override
  String get multipleSpeakersDescription =>
      'Izskatās, ka ierakstā ir vairāki runātāji. Pārliecinieties, ka atrodaties klusā vietā, un mēģiniet vēlreiz.';

  @override
  String get invalidRecordingDetected => 'Konstatēts nederīgs ieraksts';

  @override
  String get notEnoughSpeechDescription =>
      'Netika konstatēta pietiekama runa. Lūdzu, runājiet vairāk un mēģiniet vēlreiz.';

  @override
  String get speechDurationDescription => 'Pārliecinieties, ka runājat vismaz 5 sekundes un ne vairāk kā 90.';

  @override
  String get connectionLostDescription =>
      'Savienojums tika pārtraukts. Lūdzu, pārbaudiet interneta savienojumu un mēģiniet vēlreiz.';

  @override
  String get howToTakeGoodSample => 'Kā iegūt labu paraugu?';

  @override
  String get goodSampleInstructions =>
      '1. Pārliecinieties, ka atrodaties klusā vietā.\n2. Runājiet skaidri un dabiski.\n3. Pārliecinieties, ka ierīce atrodas dabiskā stāvoklī uz kakla.\n\nPēc izveides vienmēr varat to uzlabot vai izveidot no jauna.';

  @override
  String get noDeviceConnectedUseMic => 'Nav pievienota neviena ierīce. Tiks izmantots tālruņa mikrofons.';

  @override
  String get doItAgain => 'Darīt vēlreiz';

  @override
  String get listenToSpeechProfile => 'Klausīties manu balss profilu ➡️';

  @override
  String get recognizingOthers => 'Citu atpazīšana 👀';

  @override
  String get keepGoingGreat => 'Turpini, tev lieliski padodas';

  @override
  String get somethingWentWrongTryAgain => 'Kaut kas nogāja greizi! Lūdzu, mēģiniet vēlāk vēlreiz.';

  @override
  String get uploadingVoiceProfile => 'Augšupielādē jūsu balss profilu....';

  @override
  String get memorizingYourVoice => 'Iegaumē jūsu balsi...';

  @override
  String get personalizingExperience => 'Personalizē jūsu pieredzi...';

  @override
  String get keepSpeakingUntil100 => 'Turpiniet runāt, līdz sasniedzat 100%.';

  @override
  String get greatJobAlmostThere => 'Lielisks darbs, gandrīz pabeigts';

  @override
  String get soCloseJustLittleMore => 'Tik tuvu, vēl nedaudz';

  @override
  String get notificationFrequency => 'Paziņojumu biežums';

  @override
  String get controlNotificationFrequency => 'Kontrolējiet, cik bieži Omi sūta jums proaktīvus paziņojumus.';

  @override
  String get yourScore => 'Jūsu rezultāts';

  @override
  String get dailyScoreBreakdown => 'Dienas rezultāta sadalījums';

  @override
  String get todaysScore => 'Šodienas rezultāts';

  @override
  String get tasksCompleted => 'Uzdevumi pabeigti';

  @override
  String get completionRate => 'Izpildes rādītājs';

  @override
  String get howItWorks => 'Kā tas darbojas';

  @override
  String get dailyScoreExplanation =>
      'Jūsu dienas rezultāts balstās uz uzdevumu izpildi. Pabeidziet uzdevumus, lai uzlabotu rezultātu!';

  @override
  String get notificationFrequencyDescription =>
      'Kontrolējiet, cik bieži Omi sūta jums proaktīvus paziņojumus un atgādinājumus.';

  @override
  String get sliderOff => 'Izslēgts';

  @override
  String get sliderMax => 'Maks.';

  @override
  String summaryGeneratedFor(String date) {
    return 'Kopsavilkums izveidots datumam $date';
  }

  @override
  String get failedToGenerateSummary =>
      'Neizdevās izveidot kopsavilkumu. Pārliecinieties, ka jums ir sarunas par šo dienu.';

  @override
  String get recap => 'Kopsavilkums';

  @override
  String deleteQuoted(String name) {
    return 'Dzēst \"$name\"';
  }

  @override
  String moveConversationsTo(int count) {
    return 'Pārvietot $count sarunas uz:';
  }

  @override
  String get noFolder => 'Nav mapes';

  @override
  String get removeFromAllFolders => 'Noņemt no visām mapēm';

  @override
  String get buildAndShareYourCustomApp => 'Izveidojiet un kopīgojiet savu pielāgoto lietotni';

  @override
  String get searchAppsPlaceholder => 'Meklēt 1500+ lietotnēs';

  @override
  String get filters => 'Filtri';

  @override
  String get frequencyOff => 'Izslēgts';

  @override
  String get frequencyMinimal => 'Minimāls';

  @override
  String get frequencyLow => 'Zems';

  @override
  String get frequencyBalanced => 'Līdzsvarots';

  @override
  String get frequencyHigh => 'Augsts';

  @override
  String get frequencyMaximum => 'Maksimāls';

  @override
  String get frequencyDescOff => 'Nav proaktīvu paziņojumu';

  @override
  String get frequencyDescMinimal => 'Tikai kritiski atgādinājumi';

  @override
  String get frequencyDescLow => 'Tikai svarīgi atjauninājumi';

  @override
  String get frequencyDescBalanced => 'Regulāri noderīgi atgādinājumi';

  @override
  String get frequencyDescHigh => 'Bieži pārbaudes';

  @override
  String get frequencyDescMaximum => 'Palieciet pastāvīgi iesaistīts';

  @override
  String get clearChatQuestion => 'Notīrīt sarunu?';

  @override
  String get syncingMessages => 'Sinhronizē ziņojumus ar serveri...';

  @override
  String get chatAppsTitle => 'Tērzēšanas lietotnes';

  @override
  String get selectApp => 'Izvēlēties lietotni';

  @override
  String get noChatAppsEnabled =>
      'Nav iespējotas tērzēšanas lietotnes.\nPieskarieties \"Iespējot lietotnes\", lai pievienotu.';

  @override
  String get disable => 'Atspējot';

  @override
  String get photoLibrary => 'Fotoattēlu bibliotēka';

  @override
  String get chooseFile => 'Izvēlēties failu';

  @override
  String get configureAiPersona => 'Configure your AI persona';

  @override
  String get connectAiAssistantsToYourData => 'Connect AI assistants to your data';

  @override
  String get oAuth => 'OAuth';

  @override
  String get trackYourGoalsOnHomepage => 'Track your personal goals on homepage';

  @override
  String get deleteRecording => 'Delete Recording';

  @override
  String get thisCannotBeUndone => 'This cannot be undone.';

  @override
  String get sdCard => 'SD Card';

  @override
  String get fromSd => 'From SD';

  @override
  String get limitless => 'Limitless';

  @override
  String get fastTransfer => 'Fast Transfer';

  @override
  String get syncingStatus => 'Syncing';

  @override
  String get failedStatus => 'Failed';

  @override
  String etaLabel(String time) {
    return 'ETA: $time';
  }

  @override
  String get transferMethod => 'Transfer Method';

  @override
  String get fast => 'Fast';

  @override
  String get ble => 'BLE';

  @override
  String get phone => 'Phone';

  @override
  String get cancelSync => 'Cancel Sync';

  @override
  String get cancelSyncMessage => 'Data already downloaded will be saved. You can resume later.';

  @override
  String get syncCancelled => 'Sync cancelled';

  @override
  String get deleteProcessedFiles => 'Delete Processed Files';

  @override
  String get processedFilesDeleted => 'Processed files deleted';

  @override
  String get wifiEnableFailed => 'Failed to enable WiFi on device. Please try again.';

  @override
  String get deviceNoFastTransfer => 'Your device does not support Fast Transfer. Use Bluetooth instead.';

  @override
  String get enableHotspotMessage => 'Please enable your phone\'s hotspot and try again.';

  @override
  String get transferStartFailed => 'Failed to start transfer. Please try again.';

  @override
  String get deviceNotResponding => 'Device did not respond. Please try again.';

  @override
  String get invalidWifiCredentials => 'Invalid WiFi credentials. Check your hotspot settings.';

  @override
  String get wifiConnectionFailed => 'WiFi connection failed. Please try again.';

  @override
  String get sdCardProcessing => 'SD Card Processing';

  @override
  String sdCardProcessingMessage(int count) {
    return 'Processing $count recording(s). Files will be removed from SD card after.';
  }

  @override
  String get process => 'Process';

  @override
  String get wifiSyncFailed => 'WiFi Sync Failed';

  @override
  String get processingFailed => 'Processing Failed';

  @override
  String get downloadingFromSdCard => 'Downloading from SD Card';

  @override
  String processingProgress(int current, int total) {
    return 'Processing $current/$total';
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
  String get noRecordings => 'No Recordings';

  @override
  String get audioFromOmiWillAppearHere => 'Audio from your Omi device will appear here';

  @override
  String get deleteProcessed => 'Delete Processed';

  @override
  String get tryDifferentFilter => 'Try a different filter';

  @override
  String get recordings => 'Recordings';

  @override
  String get enableRemindersAccess =>
      'Lūdzu, iespējojiet piekļuvi atgādinājumiem Iestatījumos, lai izmantotu Apple Atgādinājumus';

  @override
  String todayAtTime(String time) {
    return 'Šodien $time';
  }

  @override
  String yesterdayAtTime(String time) {
    return 'Vakar $time';
  }

  @override
  String get lessThanAMinute => 'Mazāk par minūti';

  @override
  String estimatedMinutes(int count) {
    return '~$count min.';
  }

  @override
  String estimatedHours(int count) {
    return '~$count st.';
  }

  @override
  String estimatedTimeRemaining(String time) {
    return 'Aplēsts: atlikušais laiks $time';
  }

  @override
  String get summarizingConversation => 'Apkopo sarunu...\nTas var aizņemt dažas sekundes';

  @override
  String get resummarizingConversation => 'Atkārtoti apkopo sarunu...\nTas var aizņemt dažas sekundes';

  @override
  String get nothingInterestingRetry => 'Nekas interesants netika atrasts,\nvai vēlaties mēģināt vēlreiz?';

  @override
  String get noSummaryForConversation => 'Šai sarunai\nkopsavilkums nav pieejams.';

  @override
  String get unknownLocation => 'Nezināma atrašanās vieta';

  @override
  String get couldNotLoadMap => 'Nevarēja ielādēt karti';

  @override
  String get triggerConversationIntegration => 'Aktivizēt sarunas izveides integrāciju';

  @override
  String get webhookUrlNotSet => 'Webhook URL nav iestatīts';

  @override
  String get setWebhookUrlInSettings =>
      'Lūdzu, iestatiet webhook URL izstrādātāja iestatījumos, lai izmantotu šo funkciju.';

  @override
  String get sendWebUrl => 'Sūtīt tīmekļa URL';

  @override
  String get sendTranscript => 'Sūtīt transkripciju';

  @override
  String get sendSummary => 'Sūtīt kopsavilkumu';
}
