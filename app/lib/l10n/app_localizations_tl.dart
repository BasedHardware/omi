// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Tagalog (`tl`).
class AppLocalizationsTl extends AppLocalizations {
  AppLocalizationsTl([String locale = 'tl']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'Pag-uusap';

  @override
  String get transcriptTab => 'Transcript';

  @override
  String get actionItemsTab => 'Mga Aksyon';

  @override
  String get deleteConversationTitle => 'Tanggalin ang Pag-uusap?';

  @override
  String get deleteConversationMessage =>
      'Tatanggalin din nito ang mga nauugnay na alaala, gawain, at audio file. Hindi maaaring bawiin ang aksyong ito.';

  @override
  String get confirm => 'Kumpirma';

  @override
  String get cancel => 'Kanselahin';

  @override
  String get ok => 'OK';

  @override
  String get delete => 'Tanggalin';

  @override
  String get add => 'Magdagdag';

  @override
  String get update => 'I-update';

  @override
  String get save => 'I-save';

  @override
  String get edit => 'I-edit';

  @override
  String get close => 'Isara';

  @override
  String get clear => 'Burahin';

  @override
  String get copyTranscript => 'Kopyahin ang Transcript';

  @override
  String get copySummary => 'Kopyahin ang Buod';

  @override
  String get testPrompt => 'Subukan ang Prompt';

  @override
  String get reprocessConversation => 'Muling Proseso ang Pag-uusap';

  @override
  String get deleteConversation => 'Tanggalin ang Pag-uusap';

  @override
  String get contentCopied => 'Ang nilalaman ay kinopya sa clipboard';

  @override
  String get failedToUpdateStarred => 'Hindi na-update ang status na may bituin.';

  @override
  String get conversationUrlNotShared => 'Ang URL ng pag-uusap ay hindi na-share.';

  @override
  String get errorProcessingConversation => 'May kamalian sa pagpoproseso ng pag-uusap. Subukan ulit mamaya.';

  @override
  String get noInternetConnection => 'Walang koneksyon sa internet';

  @override
  String get unableToDeleteConversation => 'Hindi Maipaghanap Tanggalin ang Pag-uusap';

  @override
  String get somethingWentWrong => 'May nangyari na hindi tama! Subukan ulit mamaya.';

  @override
  String get copyErrorMessage => 'Kopyahin ang mensahe ng kamalian';

  @override
  String get errorCopied => 'Ang mensahe ng kamalian ay kinopya sa clipboard';

  @override
  String get remaining => 'Natitirang';

  @override
  String get loading => 'Naglo-load...';

  @override
  String get loadingDuration => 'Naglo-load ng tagal...';

  @override
  String secondsCount(int count) {
    return '$count segundo';
  }

  @override
  String get people => 'Mga Tao';

  @override
  String get addNewPerson => 'Magdagdag ng Bagong Tao';

  @override
  String get editPerson => 'I-edit ang Tao';

  @override
  String get createPersonHint => 'Lumikha ng bagong tao at turuan ang Omi na kilalanin ang kanilang pagsasalita!';

  @override
  String get speechProfile => 'Profil ng Boses';

  @override
  String sampleNumber(int number) {
    return 'Sample $number';
  }

  @override
  String get settings => 'Mga Setting';

  @override
  String get language => 'Wika';

  @override
  String get selectLanguage => 'Piliin ang Wika';

  @override
  String get deleting => 'Inaalis...';

  @override
  String get pleaseCompleteAuthentication =>
      'Kumpleto ang pag-authenticate sa iyong browser. Kapag tapos na, bumalik sa app.';

  @override
  String get failedToStartAuthentication => 'Nabigo ang pagsisimula ng pag-authenticate';

  @override
  String get importStarted => 'Nagsimula ang pag-import! Makakatanggap ka ng pabatid kapag tapos na.';

  @override
  String get failedToStartImport => 'Nabigo ang pagsisimula ng pag-import. Subukan ulit.';

  @override
  String get couldNotAccessFile => 'Hindi ma-access ang napiling file';

  @override
  String get askOmi => 'Tanungin ang Omi';

  @override
  String get done => 'Tapos na';

  @override
  String get disconnected => 'Nawawalan ng koneksyon';

  @override
  String get searching => 'Naghahanap...';

  @override
  String get connectDevice => 'Ikonekta ang Device';

  @override
  String get monthlyLimitReached => 'Umbot ka na sa iyong monthly limit.';

  @override
  String get checkUsage => 'Tingnan ang Paggamit';

  @override
  String get syncingRecordings => 'Nag-sync ng mga recording';

  @override
  String get recordingsToSync => 'Mga recording na dapat i-sync';

  @override
  String get allCaughtUp => 'Lahat ay na-update na';

  @override
  String get sync => 'I-sync';

  @override
  String get pendantUpToDate => 'Ang pendant ay updated na';

  @override
  String get allRecordingsSynced => 'Lahat ng recording ay na-sync na';

  @override
  String get syncingInProgress => 'Nag-sync sa ngayon';

  @override
  String get readyToSync => 'Handa nang mag-sync';

  @override
  String get tapSyncToStart => 'I-tap ang Sync para magsimula';

  @override
  String get pendantNotConnected => 'Pendant ay hindi konektado. Ikonekta para mag-sync.';

  @override
  String get everythingSynced => 'Lahat ay na-sync na.';

  @override
  String get recordingsNotSynced => 'Mayroon kang mga recording na hindi pa na-sync.';

  @override
  String get syncingBackground => 'Magpapatuloy kaming mag-sync ng iyong mga recording sa background.';

  @override
  String get noConversationsYet => 'Walang pag-uusap pa';

  @override
  String get noStarredConversations => 'Walang may-bituing pag-uusap';

  @override
  String get starConversationHint =>
      'Para maglagay ng bituin sa isang pag-uusap, buksan ito at i-tap ang bituin icon sa header.';

  @override
  String get searchConversations => 'Maghanap ng pag-uusap...';

  @override
  String selectedCount(int count, Object s) {
    return '$count napili';
  }

  @override
  String get merge => 'Pagsama';

  @override
  String get mergeConversations => 'Pagsama ng Mga Pag-uusap';

  @override
  String mergeConversationsMessage(int count) {
    return 'Ito ay pagsasama ng $count pag-uusap sa isa. Lahat ng nilalaman ay pagsasama at muling bubuo.';
  }

  @override
  String get mergingInBackground => 'Pinagsasama sa background. Maaaring tumagal ng ilang sandali.';

  @override
  String get failedToStartMerge => 'Nabigo ang pagsisimula ng pagsama';

  @override
  String get askAnything => 'Tanungin ang kahit ano';

  @override
  String get noMessagesYet => 'Walang mensahe pa!\nBakit hindi ka magsimula ng pag-uusap?';

  @override
  String get deletingMessages => 'Inaalis ang iyong mga mensahe mula sa memorya ni Omi...';

  @override
  String get messageCopied => '✨ Ang mensahe ay kinopya sa clipboard';

  @override
  String get cannotReportOwnMessage => 'Hindi mo maaaring i-report ang iyong sariling mga mensahe.';

  @override
  String get reportMessage => 'I-report ang Mensahe';

  @override
  String get reportMessageConfirm => 'Sigurado ka na bang gustong i-report ang mensaheng ito?';

  @override
  String get messageReported => 'Ang mensahe ay na-report na.';

  @override
  String get thankYouFeedback => 'Salamat sa iyong feedback!';

  @override
  String get clearChat => 'Burahin ang Chat';

  @override
  String get clearChatConfirm => 'Sigurado ka na bang gustong burahin ang chat? Hindi maaaring bawiin ang aksyong ito.';

  @override
  String get maxFilesLimit => 'Maaari lang kang mag-upload ng 4 files nang sabay-sabay';

  @override
  String get chatWithOmi => 'Makipag-chat sa Omi';

  @override
  String get apps => 'Mga App';

  @override
  String get noAppsFound => 'Walang app na nahanap';

  @override
  String get tryAdjustingSearch => 'Subukan ang pag-adjust ng iyong paghahanap o filters';

  @override
  String get createYourOwnApp => 'Lumikha ng Iyong Sariling App';

  @override
  String get buildAndShareApp => 'Bumuo at ibahagi ang iyong custom app';

  @override
  String get searchApps => 'Maghanap ng mga app...';

  @override
  String get myApps => 'Aking Mga App';

  @override
  String get installedApps => 'Naka-install na Mga App';

  @override
  String get unableToFetchApps =>
      'Hindi makuha ang mga app :(\n\nMangyaring suriin ang iyong koneksyon sa internet at subukan ulit.';

  @override
  String get aboutOmi => 'Tungkol sa Omi';

  @override
  String get privacyPolicy => 'Patakaran sa Privacy';

  @override
  String get visitWebsite => 'Bisitahin ang Website';

  @override
  String get helpOrInquiries => 'Tulong o Mga Katanungan?';

  @override
  String get joinCommunity => 'Sumali sa komunidad!';

  @override
  String get membersAndCounting => '8000+ miyembro at patuloy na dumarami.';

  @override
  String get deleteAccountTitle => 'Tanggalin ang Account';

  @override
  String get deleteAccountConfirm => 'Sigurado ka na bang gustong tanggalin ang iyong account?';

  @override
  String get cannotBeUndone => 'Hindi ito maaaring bawiin.';

  @override
  String get allDataErased => 'Lahat ng iyong mga alaala at pag-uusap ay permanenteng buburahin.';

  @override
  String get appsDisconnected => 'Ang iyong Mga App at Integrations ay mawawalan ng koneksyon kaagad.';

  @override
  String get exportBeforeDelete =>
      'Maaari mong i-export ang iyong data bago tanggalin ang iyong account, ngunit kapag tanggal na, hindi na ito mababawi.';

  @override
  String get deleteAccountCheckbox =>
      'Nauunawaan ko na ang pagtanggal ng iyong account ay permanente at lahat ng data, kasama ang mga alaala at pag-uusap, ay mawawalan at hindi mababawi.';

  @override
  String get areYouSure => 'Sigurado ka ba?';

  @override
  String get deleteAccountFinal =>
      'Ang aksyong ito ay hindi na mababawi at magtatanggal ng permanente sa iyong account at lahat ng nauugnay na data. Sigurado ka na bang nais magpatuloy?';

  @override
  String get deleteNow => 'Tanggalin Na';

  @override
  String get goBack => 'Bumalik';

  @override
  String get checkBoxToConfirm =>
      'Suriin ang kahon upang kumpirmahin na nauunawaan mo na ang pagtanggal ng iyong account ay permanente at hindi na mababawi.';

  @override
  String get profile => 'Profile';

  @override
  String get name => 'Pangalan';

  @override
  String get email => 'Email';

  @override
  String get customVocabulary => 'Custom na Bokabularyo';

  @override
  String get identifyingOthers => 'Pagkilala sa Iba';

  @override
  String get paymentMethods => 'Mga Paraan ng Pagbabayad';

  @override
  String get conversationDisplay => 'Pagpapakita ng Pag-uusap';

  @override
  String get dataPrivacy => 'Privacy ng Data';

  @override
  String get userId => 'User ID';

  @override
  String get notSet => 'Hindi nakatakda';

  @override
  String get userIdCopied => 'User ID ay kinopya sa clipboard';

  @override
  String get systemDefault => 'System Default';

  @override
  String get planAndUsage => 'Plan & Paggamit';

  @override
  String get offlineSync => 'Offline Sync';

  @override
  String get deviceSettings => 'Mga Device Setting';

  @override
  String get integrations => 'Mga Integration';

  @override
  String get feedbackBug => 'Feedback / Bug';

  @override
  String get helpCenter => 'Help Center';

  @override
  String get developerSettings => 'Developer Settings';

  @override
  String get getOmiForMac => 'Kunin ang Omi para sa Mac';

  @override
  String get referralProgram => 'Referral Program';

  @override
  String get signOut => 'Mag-sign Out';

  @override
  String get appAndDeviceCopied => 'Ang app at device details ay kinopya';

  @override
  String get wrapped2025 => 'Wrapped 2025';

  @override
  String get yourPrivacyYourControl => 'Ang Iyong Privacy, Ang Iyong Kontrol';

  @override
  String get privacyIntro =>
      'Sa Omi, kami ay nakatuon sa pagprotekta ng iyong privacy. Ang pahina na ito ay nagbibigay-daan sa iyo na kontrolin kung paano ginagamit at iniimbak ang iyong data.';

  @override
  String get learnMore => 'Matutunan ang higit pa...';

  @override
  String get dataProtectionLevel => 'Antas ng Proteksyon ng Data';

  @override
  String get dataProtectionDesc =>
      'Ang iyong data ay protektado ng default gamit ang mataas na encryption. Suriin ang iyong mga setting at hinaharap na privacy options sa ibaba.';

  @override
  String get appAccess => 'Pag-access ng App';

  @override
  String get appAccessDesc =>
      'Ang mga sumusunod na apps ay maaaring mag-access sa iyong data. I-tap ang isang app upang pamahalaan ang mga pahintulot nito.';

  @override
  String get noAppsExternalAccess => 'Walang naka-install na apps na may external access sa iyong data.';

  @override
  String get deviceName => 'Pangalan ng Device';

  @override
  String get deviceId => 'Device ID';

  @override
  String get firmware => 'Firmware';

  @override
  String get sdCardSync => 'SD Card Sync';

  @override
  String get hardwareRevision => 'Hardware Revision';

  @override
  String get modelNumber => 'Model Number';

  @override
  String get manufacturer => 'Manufacturer';

  @override
  String get doubleTap => 'Double Tap';

  @override
  String get ledBrightness => 'LED Brightness';

  @override
  String get micGain => 'Mic Gain';

  @override
  String get disconnect => 'Putol ang Koneksyon';

  @override
  String get forgetDevice => 'Kalimutan ang Device';

  @override
  String get chargingIssues => 'Mga Problema sa Pag-charge';

  @override
  String get disconnectDevice => 'Putol ang Koneksyon sa Device';

  @override
  String get unpairDevice => 'I-unpair ang Device';

  @override
  String get unpairAndForget => 'I-unpair at Kalimutan ang Device';

  @override
  String get deviceDisconnectedMessage => 'Ang iyong Omi ay nawawalan ng koneksyon 😔';

  @override
  String get deviceUnpairedMessage =>
      'Device ay nai-unpair na. Pumunta sa Settings > Bluetooth at kalimutan ang device upang makumpleto ang pag-unpair.';

  @override
  String get unpairDialogTitle => 'I-unpair ang Device';

  @override
  String get unpairDialogMessage =>
      'Ito ay ire-unpair ang device upang maaaring ikonekta sa iba pang telepono. Kailangan mong pumunta sa Settings > Bluetooth at kalimutan ang device upang makumpleto ang proseso.';

  @override
  String get deviceNotConnected => 'Device ay Hindi Konektado';

  @override
  String get connectDeviceMessage =>
      'Ikonekta ang iyong Omi device upang ma-access\nang device settings at pag-customize';

  @override
  String get deviceInfoSection => 'Impormasyon ng Device';

  @override
  String get customizationSection => 'Pag-customize';

  @override
  String get hardwareSection => 'Hardware';

  @override
  String get v2Undetected => 'V2 ay hindi na-detect';

  @override
  String get v2UndetectedMessage =>
      'Nakita namin na mayroon kang V1 device o ang iyong device ay hindi konektado. Ang SD Card functionality ay available lamang para sa V2 devices.';

  @override
  String get endConversation => 'Tapusin ang Pag-uusap';

  @override
  String get pauseResume => 'I-pause/Magpatuloy';

  @override
  String get starConversation => 'Bituin ang Pag-uusap';

  @override
  String get doubleTapAction => 'Double Tap Action';

  @override
  String get endAndProcess => 'Tapusin & Proseso ang Pag-uusap';

  @override
  String get pauseResumeRecording => 'I-pause/Magpatuloy ang Recording';

  @override
  String get starOngoing => 'Bituin ang Patuloy na Pag-uusap';

  @override
  String get off => 'Pataas';

  @override
  String get max => 'Max';

  @override
  String get mute => 'I-mute';

  @override
  String get quiet => 'Tahimik';

  @override
  String get normal => 'Normal';

  @override
  String get high => 'Mataas';

  @override
  String get micGainDescMuted => 'Ang microphone ay naka-mute';

  @override
  String get micGainDescLow => 'Napakahina - para sa malakas na kapaligiran';

  @override
  String get micGainDescModerate => 'Tahimik - para sa moderate na ingay';

  @override
  String get micGainDescNeutral => 'Neutral - balanced na recording';

  @override
  String get micGainDescSlightlyBoosted => 'Bahagyang pinataas - normal na paggamit';

  @override
  String get micGainDescBoosted => 'Pinataas - para sa tahimik na kapaligiran';

  @override
  String get micGainDescHigh => 'Mataas - para sa malayo o malambot na mga boses';

  @override
  String get micGainDescVeryHigh => 'Napakataas - para sa napakahina na mga pinagkukunan';

  @override
  String get micGainDescMax => 'Maximum - gamitin nang may pag-iingat';

  @override
  String get developerSettingsTitle => 'Developer Settings';

  @override
  String get saving => 'Nase-save...';

  @override
  String get beta => 'BETA';

  @override
  String get transcription => 'Transcription';

  @override
  String get transcriptionConfig => 'I-configure ang STT provider';

  @override
  String get conversationTimeout => 'Conversation Timeout';

  @override
  String get conversationTimeoutConfig => 'Itakda kung kailan auto-end ang mga pag-uusap';

  @override
  String get importData => 'I-import ang Data';

  @override
  String get importDataConfig => 'I-import ang data mula sa ibang pinagkukunan';

  @override
  String get debugDiagnostics => 'Debug & Diagnostics';

  @override
  String get endpointUrl => 'Endpoint URL';

  @override
  String get noApiKeys => 'Walang API keys pa';

  @override
  String get createKeyToStart => 'Lumikha ng key upang magsimula';

  @override
  String get createKey => 'Lumikha ng Key';

  @override
  String get docs => 'Docs';

  @override
  String get yourOmiInsights => 'Ang Iyong Omi Insights';

  @override
  String get today => 'Ngayon';

  @override
  String get thisMonth => 'Sa Buwan Na Ito';

  @override
  String get thisYear => 'Sa Taong Ito';

  @override
  String get allTime => 'Lahat ng Panahon';

  @override
  String get noActivityYet => 'Walang Aktibidad Pa';

  @override
  String get startConversationToSeeInsights =>
      'Magsimula ng pag-uusap sa Omi\nupang makita ang iyong usage insights dito.';

  @override
  String get listening => 'Nakikinig';

  @override
  String get listeningSubtitle => 'Kabuuang oras na aktibong nakinig ang Omi.';

  @override
  String get understanding => 'Nauunawaan';

  @override
  String get understandingSubtitle => 'Mga salitang nauunawaan mula sa iyong mga pag-uusap.';

  @override
  String get providing => 'Nagbibigay';

  @override
  String get providingSubtitle => 'Mga aksyon, at mga tala na awtomatikong na-capture.';

  @override
  String get remembering => 'Naaalala';

  @override
  String get rememberingSubtitle => 'Mga katotohanan at detalye na naaalala para sa iyo.';

  @override
  String get unlimitedPlan => 'Unlimited Plan';

  @override
  String get managePlan => 'Pamahalaan ang Plan';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'Ang iyong plan ay macancel sa $date.';
  }

  @override
  String renewsOn(String date) {
    return 'Ang iyong plan ay magre-renew sa $date.';
  }

  @override
  String get basicPlan => 'Free Plan';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used ng $limit mins na ginamit';
  }

  @override
  String get upgrade => 'I-upgrade';

  @override
  String get upgradeToUnlimited => 'I-upgrade sa unlimited';

  @override
  String basicPlanDesc(int limit) {
    return 'Ang iyong plan ay may kasamang $limit libreng minuto bawat buwan. I-upgrade para maging unlimited.';
  }

  @override
  String get shareStatsMessage => 'Nagbabahagi ng aking Omi stats! (omi.me - ang iyong palaging-bukas na AI assistant)';

  @override
  String get sharePeriodToday => 'Ngayon, omi ay:';

  @override
  String get sharePeriodMonth => 'Sa buwan na ito, omi ay:';

  @override
  String get sharePeriodYear => 'Sa taon na ito, omi ay:';

  @override
  String get sharePeriodAllTime => 'Sa ngayon, omi ay:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 Nakinig ng $minutes minuto';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 Nauunawaan ang $words salita';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ Nagbigay ng $count insights';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 Naaalala ang $count memories';
  }

  @override
  String get debugLogs => 'Debug Logs';

  @override
  String get debugLogsAutoDelete => 'Awtomatikong buburahin pagkatapos ng 3 araw.';

  @override
  String get debugLogsDesc => 'Tumutulong sa pag-diagnose ng mga isyu';

  @override
  String get noLogFilesFound => 'Walang log files na nahanap.';

  @override
  String get omiDebugLog => 'Omi debug log';

  @override
  String get logShared => 'Log ay na-share';

  @override
  String get selectLogFile => 'Piliin ang Log File';

  @override
  String get shareLogs => 'Ibahagi ang Logs';

  @override
  String get debugLogCleared => 'Debug log ay naburahin';

  @override
  String get exportStarted => 'Nagsimula ang pag-export. Maaaring tumagal ng ilang segundo...';

  @override
  String get exportAllData => 'I-export ang Lahat ng Data';

  @override
  String get exportDataDesc => 'I-export ang mga pag-uusap sa isang JSON file';

  @override
  String get exportedConversations => 'Mga Exported Conversations mula sa Omi';

  @override
  String get exportShared => 'Export ay na-share';

  @override
  String get deleteKnowledgeGraphTitle => 'Tanggalin ang Knowledge Graph?';

  @override
  String get deleteKnowledgeGraphMessage =>
      'Ito ay tatanggal ang lahat ng derived knowledge graph data (nodes at connections). Ang iyong orihinal na mga alaala ay manatiling ligtas. Ang graph ay muling bubuo sa paglipas ng panahon o sa susunod na request.';

  @override
  String get knowledgeGraphDeleted => 'Knowledge Graph ay natanggal';

  @override
  String deleteGraphFailed(String error) {
    return 'Nabigo ang pagtanggal ng graph: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'Tanggalin ang Knowledge Graph';

  @override
  String get deleteKnowledgeGraphDesc => 'Burahin ang lahat ng nodes at connections';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'MCP Server';

  @override
  String get mcpServerDesc => 'Ikonekta ang AI assistants sa iyong data';

  @override
  String get serverUrl => 'Server URL';

  @override
  String get urlCopied => 'URL ay kinopya';

  @override
  String get apiKeyAuth => 'API Key Auth';

  @override
  String get header => 'Header';

  @override
  String get authorizationBearer => 'Authorization: Bearer <key>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'Client ID';

  @override
  String get clientSecret => 'Client Secret';

  @override
  String get useMcpApiKey => 'Gamitin ang iyong MCP API key';

  @override
  String get webhooks => 'Webhooks';

  @override
  String get conversationEvents => 'Conversation Events';

  @override
  String get newConversationCreated => 'Bagong pag-uusap na nilikha';

  @override
  String get realtimeTranscript => 'Real-time Transcript';

  @override
  String get transcriptReceived => 'Transcript ay natanggap';

  @override
  String get audioBytes => 'Audio Bytes';

  @override
  String get audioDataReceived => 'Audio data ay natanggap';

  @override
  String get intervalSeconds => 'Interval (segundo)';

  @override
  String get daySummary => 'Day Summary';

  @override
  String get summaryGenerated => 'Summary ay nabuo';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'Idagdag sa claude_desktop_config.json';

  @override
  String get copyConfig => 'Kopyahin ang Config';

  @override
  String get configCopied => 'Config ay kinopya sa clipboard';

  @override
  String get listeningMins => 'Nakikinig (mins)';

  @override
  String get understandingWords => 'Nauunawaan (words)';

  @override
  String get insights => 'Insights';

  @override
  String get memories => 'Alaala';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '$used ng $limit min na ginamit sa buwan na ito';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '$used ng $limit salita na ginamit sa buwan na ito';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '$used ng $limit insights na nakuha sa buwan na ito';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return '$used ng $limit alaala na nabuo sa buwan na ito';
  }

  @override
  String get visibility => 'Visibility';

  @override
  String get visibilitySubtitle => 'Kontrolin kung aling mga pag-uusap ang lilitaw sa iyong lista';

  @override
  String get showShortConversations => 'Ipakita ang Short Conversations';

  @override
  String get showShortConversationsDesc => 'Ipakita ang mga pag-uusap na mas maikli kaysa threshold';

  @override
  String get showDiscardedConversations => 'Ipakita ang Discarded Conversations';

  @override
  String get showDiscardedConversationsDesc => 'Isama ang mga pag-uusap na markadong discarded';

  @override
  String get shortConversationThreshold => 'Short Conversation Threshold';

  @override
  String get shortConversationThresholdSubtitle =>
      'Ang mga pag-uusap na mas maikli kaysa dito ay nakatagong maliban kung na-enable ang nasa itaas';

  @override
  String get durationThreshold => 'Duration Threshold';

  @override
  String get durationThresholdDesc => 'Itago ang mga pag-uusap na mas maikli kaysa dito';

  @override
  String minLabel(int count) {
    return '$count min';
  }

  @override
  String get customVocabularyTitle => 'Custom na Bokabularyo';

  @override
  String get addWords => 'Magdagdag ng Mga Salita';

  @override
  String get addWordsDesc => 'Mga pangalan, termino, o hindi karaniwang mga salita';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'Ikonekta';

  @override
  String get comingSoon => 'Paparating Na';

  @override
  String get integrationsFooter => 'Ikonekta ang iyong mga app upang makita ang data at metrics sa chat.';

  @override
  String get completeAuthInBrowser => 'Kumpleto ang pag-authenticate sa iyong browser. Kapag tapos na, bumalik sa app.';

  @override
  String failedToStartAuth(String appName) {
    return 'Nabigo ang pagsisimula ng $appName authentication';
  }

  @override
  String disconnectAppTitle(String appName) {
    return 'I-disconnect ang $appName?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'Sigurado ka na bang gustong mag-disconnect mula sa $appName? Maaari kang muling kumonekta anumang oras.';
  }

  @override
  String disconnectedFrom(String appName) {
    return 'Nag-disconnect mula sa $appName';
  }

  @override
  String get failedToDisconnect => 'Nabigo ang pag-disconnect';

  @override
  String connectTo(String appName) {
    return 'Ikonekta sa $appName';
  }

  @override
  String authAccessMessage(String appName) {
    return 'Kailangan mong i-authorize ang Omi upang ma-access ang iyong $appName data. Ito ay magbubukas ng iyong browser para sa pag-authenticate.';
  }

  @override
  String get continueAction => 'Magpatuloy';

  @override
  String get languageTitle => 'Wika';

  @override
  String get primaryLanguage => 'Primary Language';

  @override
  String get automaticTranslation => 'Awtomatikong Pagsasalin';

  @override
  String get detectLanguages => 'Tukuyin ang 10+ wikang';

  @override
  String get authorizeSavingRecordings => 'I-authorize ang Pag-save ng mga Recording';

  @override
  String get thanksForAuthorizing => 'Salamat sa pag-authorize!';

  @override
  String get needYourPermission => 'Kailangan namin ng iyong pahintulot';

  @override
  String get alreadyGavePermission =>
      'Nagbigay ka na sa amin ng pahintulot na i-save ang iyong mga recording. Narito ang isang reminder kung bakit namin kailangan:';

  @override
  String get wouldLikePermission =>
      'Nais naming makakuha ng iyong pahintulot upang i-save ang iyong mga voice recording. Narito kung bakit:';

  @override
  String get improveSpeechProfile => 'Mapabuti ang Iyong Profil ng Boses';

  @override
  String get improveSpeechProfileDesc =>
      'Gumagamit kami ng mga recording upang higit na pagsanayin at pahusayin ang iyong personal na profil ng boses.';

  @override
  String get trainFamilyProfiles => 'Tukuyin ang Mga Profil para sa Mga Kaibigan at Pamilya';

  @override
  String get trainFamilyProfilesDesc =>
      'Ang iyong mga recording ay tumutulong sa amin na kilalanin at lumikha ng mga profil para sa iyong mga kaibigan at pamilya.';

  @override
  String get enhanceTranscriptAccuracy => 'Pahusayin ang Accuracy ng Transcript';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'Habang umuunlad ang aming modelo, maaari kaming magbigay ng mas mahusay na resulta ng transkeribsyon para sa iyong mga recording.';

  @override
  String get legalNotice =>
      'Legal Notice: Ang legality ng pag-record at pag-store ng voice data ay maaaring magkakaiba depende sa iyong lokasyon at paano mo ginagamit ang feature na ito. Ang iyong responsibilidad na matiyak ang compliance sa local laws at regulations.';

  @override
  String get alreadyAuthorized => 'Naauthorize Na';

  @override
  String get authorize => 'I-authorize';

  @override
  String get revokeAuthorization => 'Bawiin ang Authorization';

  @override
  String get authorizationSuccessful => 'Ang pag-authorize ay matagumpay!';

  @override
  String get failedToAuthorize => 'Nabigo ang pahintulot. Pakitry muli.';

  @override
  String get authorizationRevoked => 'Ang pahintulot ay inaalis na.';

  @override
  String get recordingsDeleted => 'Ang mga recording ay inalis na.';

  @override
  String get failedToRevoke => 'Nabigo ang pagtanggal ng pahintulot. Pakitry muli.';

  @override
  String get permissionRevokedTitle => 'Ang Pahintulot ay Inaalis na';

  @override
  String get permissionRevokedMessage => 'Gusto mo ba na i-remove namin ang lahat ng iyong mga recordings?';

  @override
  String get yes => 'Oo';

  @override
  String get editName => 'I-edit ang Pangalan';

  @override
  String get howShouldOmiCallYou => 'Paano ka dapat tawagan ng Omi?';

  @override
  String get enterYourName => 'Ilagay ang iyong pangalan';

  @override
  String get nameCannotBeEmpty => 'Ang pangalan ay hindi maaaring walang laman';

  @override
  String get nameUpdatedSuccessfully => 'Ang pangalan ay na-update na!';

  @override
  String get calendarSettings => 'Mga setting ng Calendar';

  @override
  String get calendarProviders => 'Mga Calendar Provider';

  @override
  String get macOsCalendar => 'macOS Calendar';

  @override
  String get connectMacOsCalendar => 'Ikonekta ang iyong lokal na macOS calendar';

  @override
  String get googleCalendar => 'Google Calendar';

  @override
  String get syncGoogleAccount => 'I-sync sa iyong Google account';

  @override
  String get showMeetingsMenuBar => 'Ipakita ang mga darating na pulong sa menu bar';

  @override
  String get showMeetingsMenuBarDesc => 'Ipakita ang iyong susunod na pulong at oras sa macOS menu bar';

  @override
  String get showEventsNoParticipants => 'Ipakita ang mga kaganapan na walang participants';

  @override
  String get showEventsNoParticipantsDesc =>
      'Kapag pinagana, ang Coming Up ay magpapakita ng mga kaganapan na walang participants o video link.';

  @override
  String get yourMeetings => 'Ang Iyong Mga Pulong';

  @override
  String get refresh => 'I-refresh';

  @override
  String get noUpcomingMeetings => 'Walang darating na mga pulong';

  @override
  String get checkingNextDays => 'Sinusuri ang susunod na 30 araw';

  @override
  String get tomorrow => 'Bukas';

  @override
  String get googleCalendarComingSoon => 'Ang Google Calendar integration ay paparating na!';

  @override
  String connectedAsUser(String userId) {
    return 'Konektado bilang user: $userId';
  }

  @override
  String get defaultWorkspace => 'Default Workspace';

  @override
  String get tasksCreatedInWorkspace => 'Ang mga task ay lilikha sa workspace na ito';

  @override
  String get defaultProjectOptional => 'Default Project (Opsyonal)';

  @override
  String get leaveUnselectedTasks => 'Iwanan na walang pipili upang lumikha ng mga task nang walang proyekto';

  @override
  String get noProjectsInWorkspace => 'Walang mga proyekto na nahanap sa workspace na ito';

  @override
  String get conversationTimeoutDesc =>
      'Pumili kung gaano katagal ang maghintay sa kalmado bago awtomatikong pagtatapos ng pag-usap:';

  @override
  String get timeout2Minutes => '2 minuto';

  @override
  String get timeout2MinutesDesc => 'Pagtatapos ng pag-usap pagkatapos ng 2 minuto ng kalmado';

  @override
  String get timeout5Minutes => '5 minuto';

  @override
  String get timeout5MinutesDesc => 'Pagtatapos ng pag-usap pagkatapos ng 5 minuto ng kalmado';

  @override
  String get timeout10Minutes => '10 minuto';

  @override
  String get timeout10MinutesDesc => 'Pagtatapos ng pag-usap pagkatapos ng 10 minuto ng kalmado';

  @override
  String get timeout30Minutes => '30 minuto';

  @override
  String get timeout30MinutesDesc => 'Pagtatapos ng pag-usap pagkatapos ng 30 minuto ng kalmado';

  @override
  String get timeout4Hours => '4 na oras';

  @override
  String get timeout4HoursDesc => 'Pagtatapos ng pag-usap pagkatapos ng 4 na oras ng kalmado';

  @override
  String get conversationEndAfterHours => 'Ang mga pag-usap ay magtatapos na pagkatapos ng 4 na oras ng kalmado';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Ang mga pag-usap ay magtatapos na pagkatapos ng $minutes minuto ng kalmado';
  }

  @override
  String get tellUsPrimaryLanguage => 'Sabihin sa amin ang iyong pangunahing wika';

  @override
  String get languageForTranscription =>
      'Itakda ang iyong wika para sa mas matalinong transcriptions at personalized na karanasan.';

  @override
  String get singleLanguageModeInfo =>
      'Ang Single Language Mode ay pinagana na. Ang pagsasalin ay hindi pinagana para sa mas mataas na accuracy.';

  @override
  String get searchLanguageHint => 'Maghanap ng wika ayon sa pangalan o code';

  @override
  String get noLanguagesFound => 'Walang mga wikang nahanap';

  @override
  String get skip => 'Laktawan';

  @override
  String languageSetTo(String language) {
    return 'Ang wika ay itinakda sa $language';
  }

  @override
  String get failedToSetLanguage => 'Nabigo ang pagtatakda ng wika';

  @override
  String appSettings(String appName) {
    return 'Mga Setting ng $appName';
  }

  @override
  String disconnectFromApp(String appName) {
    return 'Humiwalay mula sa $appName?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'Ito ay aalisin ang iyong $appName authentication. Kakailanganin mong muling kumonekta upang gamitin ito.';
  }

  @override
  String connectedToApp(String appName) {
    return 'Konektado sa $appName';
  }

  @override
  String get account => 'Account';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Ang iyong mga action item ay i-sync sa iyong $appName account';
  }

  @override
  String get defaultSpace => 'Default Space';

  @override
  String get selectSpaceInWorkspace => 'Pumili ng isang space sa iyong workspace';

  @override
  String get noSpacesInWorkspace => 'Walang mga space na nahanap sa workspace na ito';

  @override
  String get defaultList => 'Default List';

  @override
  String get tasksAddedToList => 'Ang mga task ay idaragdag sa listang ito';

  @override
  String get noListsInSpace => 'Walang mga listang nahanap sa space na ito';

  @override
  String failedToLoadRepos(String error) {
    return 'Nabigo ang pagkarga ng mga repositoryo: $error';
  }

  @override
  String get defaultRepoSaved => 'Ang default na repositoryo ay nakatipid na';

  @override
  String get failedToSaveDefaultRepo => 'Nabigo ang pagsave ng default na repositoryo';

  @override
  String get defaultRepository => 'Default Repository';

  @override
  String get selectDefaultRepoDesc =>
      'Pumili ng default na repositoryo para sa paglikha ng mga isyu. Maaari pa ring tukuyin ang ibang repositoryo kapag lumilikha ng mga isyu.';

  @override
  String get noReposFound => 'Walang mga repositoryo na nahanap';

  @override
  String get private => 'Pribado';

  @override
  String updatedDate(String date) {
    return 'Na-update $date';
  }

  @override
  String get yesterday => 'Kahapon';

  @override
  String daysAgo(int count) {
    return '$count araw na ang nakakaraan';
  }

  @override
  String get oneWeekAgo => '1 linggo na ang nakakaraan';

  @override
  String weeksAgo(int count) {
    return '$count linggo na ang nakakaraan';
  }

  @override
  String get oneMonthAgo => '1 buwan na ang nakakaraan';

  @override
  String monthsAgo(int count) {
    return '$count buwan na ang nakakaraan';
  }

  @override
  String get issuesCreatedInRepo => 'Ang mga isyu ay lilikha sa iyong default na repositoryo';

  @override
  String get taskIntegrations => 'Mga Task Integration';

  @override
  String get configureSettings => 'I-configure ang Mga Setting';

  @override
  String get completeAuthBrowser =>
      'Mangyaring kumpletuhin ang authentication sa iyong browser. Kapag tapos na, bumalik sa app.';

  @override
  String failedToStartAppAuth(String appName) {
    return 'Nabigo ang pagsisimula ng $appName authentication';
  }

  @override
  String connectToAppTitle(String appName) {
    return 'Kumonekta sa $appName';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Kakailanganin mong pahintulutan ang Omi na lumikha ng mga task sa iyong $appName account. Ito ay magbubukas ng iyong browser para sa authentication.';
  }

  @override
  String get continueButton => 'Magpatuloy';

  @override
  String appIntegration(String appName) {
    return '$appName Integration';
  }

  @override
  String integrationComingSoon(String appName) {
    return 'Ang integration sa $appName ay paparating na! Nagsusumikap kami na magdala ng mas maraming opsyon sa pamamahala ng gawain.';
  }

  @override
  String get gotIt => 'Nakuha ko';

  @override
  String get tasksExportedOneApp => 'Ang mga task ay maaaring i-export sa isang app sa isang pagkakataon.';

  @override
  String get completeYourUpgrade => 'Kumpletuhin ang Iyong Upgrade';

  @override
  String get importConfiguration => 'I-import ang Configuration';

  @override
  String get exportConfiguration => 'I-export ang configuration';

  @override
  String get bringYourOwn => 'Dalhin ang iyong sarili';

  @override
  String get payYourSttProvider => 'Gamitin ang omi nang libre. Direkta lang sa iyong STT provider ang babayaran mo.';

  @override
  String get freeMinutesMonth => '1,200 libreng minuto/buwan kasama. Unlimited sa ';

  @override
  String get omiUnlimited => 'Omi Unlimited';

  @override
  String get hostRequired => 'Ang Host ay kinakailangan';

  @override
  String get validPortRequired => 'Ang Valid port ay kinakailangan';

  @override
  String get validWebsocketUrlRequired => 'Ang Valid WebSocket URL ay kinakailangan (wss://)';

  @override
  String get apiUrlRequired => 'Ang API URL ay kinakailangan';

  @override
  String get apiKeyRequired => 'Ang API key ay kinakailangan';

  @override
  String get invalidJsonConfig => 'Ang Invalid JSON configuration';

  @override
  String errorSaving(String error) {
    return 'Error sa pagsave: $error';
  }

  @override
  String get configCopiedToClipboard => 'Ang config ay nakopya sa clipboard';

  @override
  String get pasteJsonConfig => 'I-paste ang iyong JSON configuration sa ibaba:';

  @override
  String get addApiKeyAfterImport => 'Kailangan mong magdagdag ng iyong sariling API key pagkatapos mag-import';

  @override
  String get paste => 'I-paste';

  @override
  String get import => 'I-import';

  @override
  String get invalidProviderInConfig => 'Ang Invalid provider sa configuration';

  @override
  String importedConfig(String providerName) {
    return 'Ang na-import na $providerName configuration';
  }

  @override
  String invalidJson(String error) {
    return 'Ang Invalid JSON: $error';
  }

  @override
  String get provider => 'Provider';

  @override
  String get live => 'Live';

  @override
  String get onDevice => 'On Device';

  @override
  String get apiUrl => 'API URL';

  @override
  String get enterSttHttpEndpoint => 'Ilagay ang iyong STT HTTP endpoint';

  @override
  String get websocketUrl => 'WebSocket URL';

  @override
  String get enterLiveSttWebsocket => 'Ilagay ang iyong live STT WebSocket endpoint';

  @override
  String get apiKey => 'API key';

  @override
  String get enterApiKey => 'Ilagay ang iyong API key';

  @override
  String get storedLocallyNeverShared => 'Nakatipid sa lokal, hindi kailanman ibinabahagi';

  @override
  String get host => 'Host';

  @override
  String get port => 'Port';

  @override
  String get advanced => 'Advanced';

  @override
  String get configuration => 'Configuration';

  @override
  String get requestConfiguration => 'Request Configuration';

  @override
  String get responseSchema => 'Response Schema';

  @override
  String get modified => 'Na-modify';

  @override
  String get resetRequestConfig => 'I-reset ang request config sa default';

  @override
  String get logs => 'Mga Log';

  @override
  String get logsCopied => 'Ang mga log ay nakopya';

  @override
  String get noLogsYet => 'Walang mga log pa. Magsimula ng recording para makita ang custom STT activity.';

  @override
  String deviceUsesCodec(String device, String reason) {
    return 'Ang $device ay gumagamit ng $reason. Ang Omi ay gagamitin.';
  }

  @override
  String get omiTranscription => 'Omi Transcription';

  @override
  String get bestInClassTranscription => 'Best in class transcription na walang setup';

  @override
  String get instantSpeakerLabels => 'Instant speaker labels';

  @override
  String get languageTranslation => '100+ language translation';

  @override
  String get optimizedForConversation => 'Naka-optimize para sa pag-usap';

  @override
  String get autoLanguageDetection => 'Auto language detection';

  @override
  String get highAccuracy => 'High accuracy';

  @override
  String get privacyFirst => 'Privacy first';

  @override
  String get saveChanges => 'I-save ang Mga Pagbabago';

  @override
  String get resetToDefault => 'I-reset sa default';

  @override
  String get viewTemplate => 'Tingnan ang Template';

  @override
  String get trySomethingLike => 'Subukan ang isang bagay tulad ng...';

  @override
  String get tryIt => 'Subukan ito';

  @override
  String get creatingPlan => 'Lumilikha ng plano';

  @override
  String get developingLogic => 'Bumubuo ng logic';

  @override
  String get designingApp => 'Dinadala ang app';

  @override
  String get generatingIconStep => 'Bumubuo ng icon';

  @override
  String get finalTouches => 'Huling touchup';

  @override
  String get processing => 'Nagpoproseso...';

  @override
  String get features => 'Mga Features';

  @override
  String get creatingYourApp => 'Lumilikha ng iyong app...';

  @override
  String get generatingIcon => 'Bumubuo ng icon...';

  @override
  String get whatShouldWeMake => 'Ano ang dapat tayong gawing?';

  @override
  String get appName => 'App Name';

  @override
  String get description => 'Description';

  @override
  String get publicLabel => 'Public';

  @override
  String get privateLabel => 'Private';

  @override
  String get free => 'Libre';

  @override
  String get perMonth => '/ Buwan';

  @override
  String get tailoredConversationSummaries => 'Tailored Conversation Summaries';

  @override
  String get customChatbotPersonality => 'Custom Chatbot Personality';

  @override
  String get makePublic => 'Gawing Public';

  @override
  String get anyoneCanDiscover => 'Sinuman ay maaaring tuklasin ang iyong app';

  @override
  String get onlyYouCanUse => 'Ikaw lang ang maaaring gumamit ng app na ito';

  @override
  String get paidApp => 'Paid app';

  @override
  String get usersPayToUse => 'Ang mga users ay nagbabayad upang gumamit ng iyong app';

  @override
  String get freeForEveryone => 'Libre para sa lahat';

  @override
  String get perMonthLabel => '/ buwan';

  @override
  String get creating => 'Lumilikha...';

  @override
  String get createApp => 'Lumikha ng App';

  @override
  String get searchingForDevices => 'Naghahanap ng mga device...';

  @override
  String devicesFoundNearby(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'DEVICES',
      one: 'DEVICE',
    );
    return '$count $_temp0 NAHANAP SA MALAPIT';
  }

  @override
  String get pairingSuccessful => 'SUCCESSFUL NA PAIRING';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Error sa pag-konekta sa Apple Watch: $error';
  }

  @override
  String get dontShowAgain => 'Huwag ipakita ulit';

  @override
  String get iUnderstand => 'Nakakaintindi ako';

  @override
  String get enableBluetooth => 'Paganahin ang Bluetooth';

  @override
  String get bluetoothNeeded =>
      'Ang Omi ay kailangan ng Bluetooth upang kumonekta sa iyong wearable. Mangyaring paganahin ang Bluetooth at subukan muli.';

  @override
  String get contactSupport => 'Makipag-ugnayan sa Support?';

  @override
  String get connectLater => 'Kumonekta Sa Ibang Pagkakataon';

  @override
  String get grantPermissions => 'Bigyan ng mga pahintulot';

  @override
  String get backgroundActivity => 'Background activity';

  @override
  String get backgroundActivityDesc => 'Hayaang tumakbo ang Omi sa background para sa mas magandang stability';

  @override
  String get locationAccess => 'Location access';

  @override
  String get locationAccessDesc => 'Paganahin ang background location para sa buong karanasan';

  @override
  String get notifications => 'Mga Notipikasyon';

  @override
  String get notificationsDesc => 'Paganahin ang mga notipikasyon upang manatiling informed';

  @override
  String get locationServiceDisabled => 'Ang Location Service ay Disabled';

  @override
  String get locationServiceDisabledDesc =>
      'Ang Location Service ay Disabled. Mangyaring pumunta sa Settings > Privacy & Security > Location Services at paganahin ito';

  @override
  String get backgroundLocationDenied => 'Ang Background Location Access ay Dineny';

  @override
  String get backgroundLocationDeniedDesc =>
      'Mangyaring pumunta sa device settings at itakda ang location permission sa \"Always Allow\"';

  @override
  String get lovingOmi => 'Gusto mo ba ang Omi?';

  @override
  String get leaveReviewIos =>
      'Tumulong sa amin na maabot ang mas maraming tao sa pamamagitan ng pag-iwan ng review sa App Store. Ang iyong feedback ay napakahalagang para sa amin!';

  @override
  String get leaveReviewAndroid =>
      'Tumulong sa amin na maabot ang mas maraming tao sa pamamagitan ng pag-iwan ng review sa Google Play Store. Ang iyong feedback ay napakahalagang para sa amin!';

  @override
  String get rateOnAppStore => 'Mag-rate sa App Store';

  @override
  String get rateOnGooglePlay => 'Mag-rate sa Google Play';

  @override
  String get maybeLater => 'Siguro mamaya';

  @override
  String get speechProfileIntro =>
      'Ang Omi ay kailangan matuto ng iyong mga layunin at iyong boses. Makakabago ka nito mamaya.';

  @override
  String get getStarted => 'Magsimula';

  @override
  String get allDone => 'Tapos na!';

  @override
  String get keepGoing => 'Patuloy, ang iyong ginagawa ay napakaganda';

  @override
  String get skipThisQuestion => 'I-skip ang tanong na ito';

  @override
  String get skipForNow => 'I-skip para sa ngayon';

  @override
  String get connectionError => 'Connection Error';

  @override
  String get connectionErrorDesc =>
      'Nabigo ang koneksyon sa server. Mangyaring suriin ang iyong internet connection at subukan muli.';

  @override
  String get invalidRecordingMultipleSpeakers => 'Ang invalid recording ay nadetect';

  @override
  String get multipleSpeakersDesc =>
      'Mukhang may maraming speakers sa recording. Mangyaring masiguro na ikaw ay nasa tahimik na lugar at subukan muli.';

  @override
  String get tooShortDesc => 'Walang sapat na speech na nadetect. Mangyaring magsalita nang higit pa at subukan muli.';

  @override
  String get invalidRecordingDesc =>
      'Mangyaring masiguro na ikaw ay nagsasalita ng hindi bababa sa 5 segundo at hindi higit sa 90.';

  @override
  String get areYouThere => 'Nandito ka ba?';

  @override
  String get noSpeechDesc =>
      'Hindi namin nadetect ang anumang speech. Mangyaring masiguro na nagsasalita ka ng hindi bababa sa 10 segundo at hindi higit sa 3 minuto.';

  @override
  String get connectionLost => 'Ang Koneksyon ay Nawala';

  @override
  String get connectionLostDesc =>
      'Ang koneksyon ay naintriga. Mangyaring suriin ang iyong internet connection at subukan muli.';

  @override
  String get tryAgain => 'Subukan Muli';

  @override
  String get connectOmiOmiGlass => 'Kumonekta sa Omi / OmiGlass';

  @override
  String get continueWithoutDevice => 'Magpatuloy Nang Walang Device';

  @override
  String get permissionsRequired => 'Mga Pahintulot na Kinakailangan';

  @override
  String get permissionsRequiredDesc =>
      'Ang app na ito ay kailangan ng Bluetooth at Location permissions upang gumana nang maayos. Mangyaring paganahin ang mga ito sa settings.';

  @override
  String get openSettings => 'Buksan ang Settings';

  @override
  String get wantDifferentName => 'Gusto mo bang gamitin ang ibang pangalan?';

  @override
  String get whatsYourName => 'Ano ang iyong pangalan?';

  @override
  String get speakTranscribeSummarize => 'Magsalita. Mag-transcribe. Bumuod.';

  @override
  String get signInWithApple => 'Mag-sign in gamit ang Apple';

  @override
  String get signInWithGoogle => 'Mag-sign in gamit ang Google';

  @override
  String get byContinuingAgree => 'Sa pagpapatuloy, sumasang-ayon ka sa aming ';

  @override
  String get termsOfUse => 'Terms of Use';

  @override
  String get omiYourAiCompanion => 'Omi – Ang Iyong AI Companion';

  @override
  String get captureEveryMoment =>
      'Kunan ang bawat sandali. Makakuha ng AI-powered\nsummaries. Hindi na kailangan mag-notes.';

  @override
  String get appleWatchSetup => 'Apple Watch Setup';

  @override
  String get permissionRequestedExclaim => 'Ang Pahintulot ay Hiniling!';

  @override
  String get microphonePermission => 'Microphone Permission';

  @override
  String get permissionGrantedNow =>
      'Ang pahintulot ay nabigyan na! Ngayon:\n\nBuksan ang Omi app sa iyong watch at tapin ang \"Continue\" sa ibaba';

  @override
  String get needMicrophonePermission =>
      'Kailangan namin ng microphone permission.\n\n1. Tapin ang \"Grant Permission\"\n2. Payagan sa iyong iPhone\n3. Ang watch app ay magsasara\n4. Muling buksan at tapin ang \"Continue\"';

  @override
  String get grantPermissionButton => 'Bigyan ng Permission';

  @override
  String get needHelp => 'Kailangan ng Tulong?';

  @override
  String get troubleshootingSteps =>
      'Troubleshooting:\n\n1. Masiguro na ang Omi ay naka-install sa iyong watch\n2. Buksan ang Omi app sa iyong watch\n3. Hanapin ang permission popup\n4. Tapin ang \"Allow\" kapag hiniling\n5. Ang app sa iyong watch ay magsasara - buksan ito muli\n6. Bumalik at tapin ang \"Continue\" sa iyong iPhone';

  @override
  String get recordingStartedSuccessfully => 'Ang recording ay nagsimula na!';

  @override
  String get permissionNotGrantedYet =>
      'Ang pahintulot ay hindi pa nabigyan. Mangyaring masiguro na pinahintulutan mo ang microphone access at muling binuksan ang app sa iyong watch.';

  @override
  String errorRequestingPermission(String error) {
    return 'Error sa hinihiling ng pahintulot: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'Error sa pagsisimula ng recording: $error';
  }

  @override
  String get selectPrimaryLanguage => 'Pumili ng iyong pangunahing wika';

  @override
  String get languageBenefits =>
      'Itakda ang iyong wika para sa mas matalinong transcriptions at personalized na karanasan';

  @override
  String get whatsYourPrimaryLanguage => 'Ano ang iyong pangunahing wika?';

  @override
  String get selectYourLanguage => 'Pumili ng iyong wika';

  @override
  String get personalGrowthJourney => 'Ang iyong personal growth journey gamit ang AI na nakikinig sa bawat salita mo.';

  @override
  String get actionItemsTitle => 'Mga To-Do';

  @override
  String get actionItemsDescription => 'Tapin upang i-edit • Long press upang pumili • Mag-swipe para sa aksyon';

  @override
  String get tabToDo => 'To Do';

  @override
  String get tabDone => 'Tapos na';

  @override
  String get tabOld => 'Matanda';

  @override
  String get emptyTodoMessage => '🎉 Tapos na!\nWalang pending action items';

  @override
  String get emptyDoneMessage => 'Walang kumpleting items pa';

  @override
  String get emptyOldMessage => '✅ Walang matandang tasks';

  @override
  String get noItems => 'Walang items';

  @override
  String get actionItemMarkedIncomplete => 'Ang action item ay minarkahan bilang incomplete';

  @override
  String get actionItemCompleted => 'Ang action item ay kumpleto na';

  @override
  String get deleteActionItemTitle => 'I-delete ang Action Item';

  @override
  String get deleteActionItemMessage => 'Sigurado ka ba na gusto mong i-delete ang action item na ito?';

  @override
  String get deleteSelectedItemsTitle => 'I-delete ang Mga Piniling Items';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Sigurado ka ba na gusto mong i-delete ang $count piniling action item$s?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'Ang action item \"$description\" ay natanggal na';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count action item$s ay natanggal na';
  }

  @override
  String get failedToDeleteItem => 'Nabigo ang pagtanggal ng action item';

  @override
  String get failedToDeleteItems => 'Nabigo ang pagtanggal ng mga items';

  @override
  String get failedToDeleteSomeItems => 'Nabigo ang pagtanggal ng ilang items';

  @override
  String get welcomeActionItemsTitle => 'Handa para sa Action Items';

  @override
  String get welcomeActionItemsDescription =>
      'Ang iyong AI ay awtomatikong makakakuha ng mga tasks at to-dos mula sa iyong mga pag-usap. Makikita nila dito kapag ginawa.';

  @override
  String get autoExtractionFeature => 'Awtomatikong na-extract mula sa mga pag-usap';

  @override
  String get editSwipeFeature => 'Tapin upang i-edit, mag-swipe upang makumpleto o tanggalin';

  @override
  String itemsSelected(int count) {
    return '$count napili';
  }

  @override
  String get selectAll => 'Piliin lahat';

  @override
  String get deleteSelected => 'I-delete ang pinili';

  @override
  String get searchMemories => 'Maghanap ng mga alaala...';

  @override
  String get memoryDeleted => 'Ang Alaala ay Natanggal.';

  @override
  String get undo => 'Undo';

  @override
  String get noMemoriesYet => '🧠 Walang mga alaala pa';

  @override
  String get noAutoMemories => 'Walang awtomatikong na-extract na mga alaala pa';

  @override
  String get noManualMemories => 'Walang manual na mga alaala pa';

  @override
  String get noMemoriesInCategories => 'Walang mga alaala sa mga kategoryang ito';

  @override
  String get noMemoriesFound => '🔍 Walang mga alaala na nahanap';

  @override
  String get addFirstMemory => 'Magdagdag ng iyong unang alaala';

  @override
  String get clearMemoryTitle => 'I-clear ang Alaala ng Omi';

  @override
  String get clearMemoryMessage =>
      'Sigurado ka ba na gusto mong i-clear ang alaala ng Omi? Ang aksyon na ito ay hindi mababawi.';

  @override
  String get clearMemoryButton => 'I-clear ang Alaala';

  @override
  String get memoryClearedSuccess => 'Ang alaala ng Omi tungkol sa iyo ay na-clear na';

  @override
  String get noMemoriesToDelete => 'Walang mga alaala na i-delete';

  @override
  String get createMemoryTooltip => 'Lumikha ng bagong alaala';

  @override
  String get createActionItemTooltip => 'Lumikha ng bagong action item';

  @override
  String get memoryManagement => 'Memory Management';

  @override
  String get filterMemories => 'I-filter ang Mga Alaala';

  @override
  String totalMemoriesCount(int count) {
    return 'Mayroon kang $count total memories';
  }

  @override
  String get publicMemories => 'Mga public na alaala';

  @override
  String get privateMemories => 'Mga private na alaala';

  @override
  String get makeAllPrivate => 'Gawin Lahat ng Mga Alaala na Private';

  @override
  String get makeAllPublic => 'Gawin Lahat ng Mga Alaala na Public';

  @override
  String get deleteAllMemories => 'I-delete Lahat ng Mga Alaala';

  @override
  String get allMemoriesPrivateResult => 'Lahat ng mga alaala ay private na';

  @override
  String get allMemoriesPublicResult => 'Lahat ng mga alaala ay public na';

  @override
  String get newMemory => '✨ Bagong Alaala';

  @override
  String get editMemory => '✏️ I-edit ang Alaala';

  @override
  String get memoryContentHint => 'Gusto ko na kumain ng ice cream...';

  @override
  String get failedToSaveMemory => 'Nabigo ang pagsave. Mangyaring suriin ang iyong koneksyon.';

  @override
  String get saveMemory => 'I-save ang Alaala';

  @override
  String get retry => 'Subukan muli';

  @override
  String get createActionItem => 'Lumikha ng Action Item';

  @override
  String get editActionItem => 'I-edit ang Action Item';

  @override
  String get actionItemDescriptionHint => 'Ano ang kailangan gawin?';

  @override
  String get actionItemDescriptionEmpty => 'Ang action item description ay hindi maaaring walang laman.';

  @override
  String get actionItemUpdated => 'Ang action item ay na-update na';

  @override
  String get failedToUpdateActionItem => 'Nabigo ang pag-update ng action item';

  @override
  String get actionItemCreated => 'Ang action item ay nilikha na';

  @override
  String get failedToCreateActionItem => 'Nabigo ang paglikha ng action item';

  @override
  String get dueDate => 'Due Date';

  @override
  String get time => 'Oras';

  @override
  String get addDueDate => 'Magdagdag ng due date';

  @override
  String get pressDoneToSave => 'Pindutin ang done upang i-save';

  @override
  String get pressDoneToCreate => 'Pindutin ang done upang lumikha';

  @override
  String get filterAll => 'Lahat';

  @override
  String get filterSystem => 'Tungkol sa Iyo';

  @override
  String get filterInteresting => 'Insights';

  @override
  String get filterManual => 'Manual';

  @override
  String get completed => 'Kumpleto';

  @override
  String get markComplete => 'Markahan Bilang Kumpleto';

  @override
  String get actionItemDeleted => 'Ang action item ay natanggal na';

  @override
  String get failedToDeleteActionItem => 'Nabigo ang pagtanggal ng action item';

  @override
  String get deleteActionItemConfirmTitle => 'I-delete ang Action Item';

  @override
  String get deleteActionItemConfirmMessage => 'Sigurado ka ba na gusto mong i-delete ang action item na ito?';

  @override
  String get appLanguage => 'App Language';

  @override
  String get appInterfaceSectionTitle => 'APP INTERFACE';

  @override
  String get speechTranscriptionSectionTitle => 'SPEECH & TRANSCRIPTION';

  @override
  String get languageSettingsHelperText =>
      'Ang App Language ay nagbabago ng mga menu at button. Ang Speech Language ay nakakaapekto sa kung paano na-transcribe ang iyong mga recording.';

  @override
  String get translationNotice => 'Translation Notice';

  @override
  String get translationNoticeMessage =>
      'Ang Omi ay nagsasalin ng mga pag-usap sa iyong pangunahing wika. I-update ito anumang oras sa Settings → Profiles.';

  @override
  String get pleaseCheckInternetConnection => 'Mangyaring suriin ang iyong internet connection at subukan muli';

  @override
  String get pleaseSelectReason => 'Mangyaring pumili ng dahilan';

  @override
  String get tellUsMoreWhatWentWrong => 'Sabihin sa amin nang higit pa ang nangyari...';

  @override
  String get selectText => 'Pumili ng Text';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Maximum $count goals allowed';
  }

  @override
  String get conversationCannotBeMerged => 'Ang pag-usap na ito ay hindi maaaring isama (locked o nag-merge na)';

  @override
  String get pleaseEnterFolderName => 'Mangyaring ilagay ang folder name';

  @override
  String get failedToCreateFolder => 'Nabigo ang paglikha ng folder';

  @override
  String get failedToUpdateFolder => 'Nabigo ang pag-update ng folder';

  @override
  String get folderName => 'Folder name';

  @override
  String get descriptionOptional => 'Paglalarawan (opsyonal)';

  @override
  String get failedToDeleteFolder => 'Nabigong burahin ang folder';

  @override
  String get editFolder => 'I-edit ang Folder';

  @override
  String get deleteFolder => 'Burahin ang Folder';

  @override
  String get transcriptCopiedToClipboard => 'Transcript ay nai-copy sa clipboard';

  @override
  String get summaryCopiedToClipboard => 'Summary ay nai-copy sa clipboard';

  @override
  String get conversationUrlCouldNotBeShared => 'Ang URL ng conversation ay hindi maaaring ibahagi.';

  @override
  String get urlCopiedToClipboard => 'URL ay Nai-copy sa Clipboard';

  @override
  String get exportTranscript => 'I-export ang Transcript';

  @override
  String get exportSummary => 'I-export ang Summary';

  @override
  String get exportButton => 'I-export';

  @override
  String get actionItemsCopiedToClipboard => 'Action items ay nai-copy sa clipboard';

  @override
  String get summarize => 'Bumuod';

  @override
  String get generateSummary => 'Lumikha ng Summary';

  @override
  String get conversationNotFoundOrDeleted => 'Ang conversation ay hindi nahanap o na-delete na';

  @override
  String get deleteMemory => 'Burahin ang Memory';

  @override
  String get thisActionCannotBeUndone => 'Ang aksyong ito ay hindi maaaring bawiin.';

  @override
  String memoriesCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count memories',
      one: '1 memory',
      zero: '0 memories',
    );
    return '$_temp0';
  }

  @override
  String get noMemoriesInCategory => 'Walang memories sa kategoryang ito pa';

  @override
  String get addYourFirstMemory => 'Magdagdag ng iyong unang memory';

  @override
  String get firmwareDisconnectUsb => 'Ikabit ang USB';

  @override
  String get firmwareUsbWarning =>
      'Ang koneksyon ng USB sa panahon ng mga update ay maaaring makasama sa iyong device.';

  @override
  String get firmwareBatteryAbove15 => 'Baterya sa Itaas ng 15%';

  @override
  String get firmwareEnsureBattery => 'Siguraduhin na ang iyong device ay may 15% na baterya.';

  @override
  String get firmwareStableConnection => 'Matatag na Koneksyon';

  @override
  String get firmwareConnectWifi => 'Kumonekta sa WiFi o cellular.';

  @override
  String failedToStartUpdate(String error) {
    return 'Nabigong magsimula ng update: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'Bago ang Update, Siguraduhin:';

  @override
  String get confirmed => 'Kumpirmado!';

  @override
  String get release => 'Ilabas';

  @override
  String get slideToUpdate => 'Mag-slide upang I-update';

  @override
  String copiedToClipboard(String title) {
    return '$title ay nai-copy sa clipboard';
  }

  @override
  String get batteryLevel => 'Antas ng Baterya';

  @override
  String get charging => 'Nagcha-charge';

  @override
  String get productUpdate => 'Product Update';

  @override
  String get offline => 'Offline';

  @override
  String get available => 'Available';

  @override
  String get unpairDeviceDialogTitle => 'I-unpair ang Device';

  @override
  String get unpairDeviceDialogMessage =>
      'Ito ay mag-unpair ng device upang maaari itong ikonekta sa iba pang telepono. Kailangan mong pumunta sa Settings > Bluetooth at kalimutan ang device upang makumpleto ang proseso.';

  @override
  String get unpair => 'I-unpair';

  @override
  String get unpairAndForgetDevice => 'I-unpair at Kalimutan ang Device';

  @override
  String get unknownDevice => 'Hindi Kilala';

  @override
  String get unknown => 'Hindi Kilala';

  @override
  String get productName => 'Pangalan ng Produkto';

  @override
  String get serialNumber => 'Serial Number';

  @override
  String get connected => 'Konektado';

  @override
  String get privacyPolicyTitle => 'Privacy Policy';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label ay nai-copy';
  }

  @override
  String get noApiKeysYet => 'Walang API keys pa';

  @override
  String get createKeyToGetStarted => 'Lumikha ng key upang magsimula';

  @override
  String get configureSttProvider => 'I-configure ang STT provider';

  @override
  String get setWhenConversationsAutoEnd => 'Itakda kung kailan ang mga conversation ay awtomatikong magtatapos';

  @override
  String get importDataFromOtherSources => 'Mag-import ng data mula sa ibang mga pinagkukunan';

  @override
  String get debugAndDiagnostics => 'Debug & Diagnostics';

  @override
  String get autoDeletesAfter3Days => 'Awtomatikong nababura pagkatapos ng 3 araw.';

  @override
  String get helpsDiagnoseIssues => 'Tumutulong na tukuyin ang mga isyu';

  @override
  String get exportStartedMessage => 'Nagsimula na ang export. Ito ay maaaring tumagal ng ilang segundo...';

  @override
  String get exportConversationsToJson => 'I-export ang mga conversation sa isang JSON file';

  @override
  String get knowledgeGraphDeletedSuccess => 'Knowledge Graph ay matagumpay na nabura';

  @override
  String failedToDeleteGraph(String error) {
    return 'Nabigong burahin ang graph: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'Burahin ang lahat ng nodes at connections';

  @override
  String get addToClaudeDesktopConfig => 'Idagdag sa claude_desktop_config.json';

  @override
  String get connectAiAssistantsToData => 'Ikonekta ang mga AI assistant sa iyong data';

  @override
  String get useYourMcpApiKey => 'Gamitin ang iyong MCP API key';

  @override
  String get realTimeTranscript => 'Real-time Transcript';

  @override
  String get experimental => 'Experimental';

  @override
  String get transcriptionDiagnostics => 'Transcription Diagnostics';

  @override
  String get detailedDiagnosticMessages => 'Detailed na mga diagnostic messages';

  @override
  String get autoCreateSpeakers => 'Awtomatikong Lumikha ng Speakers';

  @override
  String get autoCreateWhenNameDetected => 'Awtomatikong lumikha kapag ang pangalan ay natuklasan';

  @override
  String get followUpQuestions => 'Follow-up Questions';

  @override
  String get suggestQuestionsAfterConversations => 'Magmungkahi ng mga tanong pagkatapos ng mga conversation';

  @override
  String get goalTracker => 'Goal Tracker';

  @override
  String get trackPersonalGoalsOnHomepage => 'Subaybayan ang iyong personal na mga layunin sa homepage';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'Ang paglalarawan ng action item ay hindi maaaring walang laman';

  @override
  String get saved => 'Nai-save';

  @override
  String get overdue => 'Lampas sa target na petsa';

  @override
  String get failedToUpdateDueDate => 'Nabigong i-update ang due date';

  @override
  String get markIncomplete => 'Markahan bilang Hindi Kumpleto';

  @override
  String get editDueDate => 'I-edit ang Due Date';

  @override
  String get setDueDate => 'Itakda ang Due Date';

  @override
  String get clearDueDate => 'Burahin ang Due Date';

  @override
  String get failedToClearDueDate => 'Nabigong burahin ang due date';

  @override
  String get mondayAbbr => 'Lun';

  @override
  String get tuesdayAbbr => 'Mar';

  @override
  String get wednesdayAbbr => 'Miy';

  @override
  String get thursdayAbbr => 'Huy';

  @override
  String get fridayAbbr => 'Biy';

  @override
  String get saturdayAbbr => 'Sab';

  @override
  String get sundayAbbr => 'Lin';

  @override
  String get howDoesItWork => 'Paano ito gumagana?';

  @override
  String get sdCardSyncDescription =>
      'Ang SD Card Sync ay mag-import ng iyong mga memories mula sa SD Card patungo sa app';

  @override
  String get checksForAudioFiles => 'Sinusuri ang mga audio file sa SD Card';

  @override
  String get omiSyncsAudioFiles => 'Ang Omi ay nag-sync pagkatapos ng mga audio file sa server';

  @override
  String get serverProcessesAudio => 'Ang server ay nagpoproseso ng mga audio file at lumilikha ng mga memories';

  @override
  String get youreAllSet => 'Lahat ay handa na!';

  @override
  String get welcomeToOmiDescription =>
      'Maligayang pagdating sa Omi! Ang iyong AI companion ay handa nang tulungan ka sa mga conversation, gawain, at marami pa.';

  @override
  String get startUsingOmi => 'Magsimulang Gumamit ng Omi';

  @override
  String get back => 'Bumalik';

  @override
  String get keyboardShortcuts => 'Keyboard Shortcuts';

  @override
  String get toggleControlBar => 'I-toggle ang Control Bar';

  @override
  String get pressKeys => 'Pindutin ang mga susi...';

  @override
  String get cmdRequired => '⌘ kinakailangan';

  @override
  String get invalidKey => 'Invalid na susi';

  @override
  String get space => 'Space';

  @override
  String get search => 'Maghanap';

  @override
  String get searchPlaceholder => 'Maghanap...';

  @override
  String get untitledConversation => 'Walang Panandaliang Conversation';

  @override
  String countRemaining(String count) {
    return '$count nananatili';
  }

  @override
  String get addGoal => 'Magdagdag ng Layunin';

  @override
  String get editGoal => 'I-edit ang Layunin';

  @override
  String get icon => 'Icon';

  @override
  String get goalTitle => 'Pamagat ng layunin';

  @override
  String get current => 'Kasalukuyan';

  @override
  String get target => 'Target';

  @override
  String get saveGoal => 'I-save';

  @override
  String get goals => 'Mga Layunin';

  @override
  String get tapToAddGoal => 'Mag-tap upang magdagdag ng layunin';

  @override
  String welcomeBack(String name) {
    return 'Maligayang pagbabalik, $name';
  }

  @override
  String get yourConversations => 'Ang Iyong Mga Conversation';

  @override
  String get reviewAndManageConversations => 'Suriin at pamahalaan ang iyong mga captured na conversation';

  @override
  String get startCapturingConversations =>
      'Magsimulang kumuha ng mga conversation gamit ang iyong Omi device upang makita ang mga ito dito.';

  @override
  String get useMobileAppToCapture => 'Gamitin ang iyong mobile app upang kumuha ng audio';

  @override
  String get conversationsProcessedAutomatically => 'Ang mga conversation ay awtomatikong napoproseso';

  @override
  String get getInsightsInstantly => 'Makakuha ng mga insight at summary kaagad';

  @override
  String get showAll => 'Ipakita ang Lahat';

  @override
  String get noTasksForToday =>
      'Walang mga gawain para sa araw na ito.\nTanungin ang Omi para sa higit pang mga gawain o lumikha nang manu-mano.';

  @override
  String get dailyScore => 'PANG-ARAW-ARAW NA PUNTUASYON';

  @override
  String get dailyScoreDescription => 'Isang puntuasyon upang tulungan kang mas mahusay\ntumuon sa pagpapatupad.';

  @override
  String get searchResults => 'Mga resulta ng paghahanap';

  @override
  String get actionItems => 'Action Items';

  @override
  String get tasksToday => 'Ngayong Araw';

  @override
  String get tasksTomorrow => 'Bukas';

  @override
  String get tasksNoDeadline => 'Walang Deadline';

  @override
  String get tasksLater => 'Mamaya';

  @override
  String get loadingTasks => 'Kumakarga ng mga gawain...';

  @override
  String get tasks => 'Mga Gawain';

  @override
  String get swipeTasksToIndent => 'I-swipe ang mga gawain upang mag-indent, i-drag sa pagitan ng mga kategorya';

  @override
  String get create => 'Lumikha';

  @override
  String get noTasksYet => 'Walang Mga Gawain Pa';

  @override
  String get tasksFromConversationsWillAppear =>
      'Ang mga gawain mula sa iyong mga conversation ay lilitaw dito.\nI-click ang Create upang magdagdag ng isa nang manu-mano.';

  @override
  String get monthJan => 'Ene';

  @override
  String get monthFeb => 'Peb';

  @override
  String get monthMar => 'Mar';

  @override
  String get monthApr => 'Abr';

  @override
  String get monthMay => 'May';

  @override
  String get monthJun => 'Hun';

  @override
  String get monthJul => 'Hul';

  @override
  String get monthAug => 'Ago';

  @override
  String get monthSep => 'Set';

  @override
  String get monthOct => 'Okt';

  @override
  String get monthNov => 'Nob';

  @override
  String get monthDec => 'Des';

  @override
  String get timePM => 'PM';

  @override
  String get timeAM => 'AM';

  @override
  String get actionItemUpdatedSuccessfully => 'Ang action item ay matagumpay na na-update';

  @override
  String get actionItemCreatedSuccessfully => 'Ang action item ay matagumpay na nalikha';

  @override
  String get actionItemDeletedSuccessfully => 'Ang action item ay matagumpay na nabura';

  @override
  String get deleteActionItem => 'Burahin ang Action Item';

  @override
  String get deleteActionItemConfirmation =>
      'Sigurado ka na ba na nais mong burahin ang action item na ito? Ang aksyong ito ay hindi maaaring bawiin.';

  @override
  String get enterActionItemDescription => 'Magpasok ng paglalarawan ng action item...';

  @override
  String get markAsCompleted => 'Markahan bilang Kumpleto';

  @override
  String get setDueDateAndTime => 'Itakda ang due date at oras';

  @override
  String get reloadingApps => 'Nag-reload ng mga app...';

  @override
  String get loadingApps => 'Kumakarga ng mga app...';

  @override
  String get browseInstallCreateApps => 'Mag-browse, mag-install, at lumikha ng mga app';

  @override
  String get all => 'Lahat';

  @override
  String get open => 'Buksan';

  @override
  String get install => 'I-install';

  @override
  String get noAppsAvailable => 'Walang mga app na available';

  @override
  String get unableToLoadApps => 'Hindi kayang i-load ang mga app';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'Subukan ang pag-adjust ng iyong mga search terms o filters';

  @override
  String get checkBackLaterForNewApps => 'Bumalik mamaya upang makita ang mga bagong app';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'Pakisuri ang iyong koneksyon sa internet at subukan muli';

  @override
  String get createNewApp => 'Lumikha ng Bagong App';

  @override
  String get buildSubmitCustomOmiApp => 'Bumuo at magpadala ng iyong custom na Omi app';

  @override
  String get submittingYourApp => 'Nag-submit ng iyong app...';

  @override
  String get preparingFormForYou => 'Naghahanda ng form para sa iyo...';

  @override
  String get appDetails => 'App Details';

  @override
  String get paymentDetails => 'Payment Details';

  @override
  String get previewAndScreenshots => 'Preview at Screenshots';

  @override
  String get appCapabilities => 'App Capabilities';

  @override
  String get aiPrompts => 'AI Prompts';

  @override
  String get chatPrompt => 'Chat Prompt';

  @override
  String get chatPromptPlaceholder =>
      'Ikaw ay isang kahanga-hangang app, ang iyong trabaho ay tumugon sa mga query ng user at gawing masaya sila...';

  @override
  String get conversationPrompt => 'Conversation Prompt';

  @override
  String get conversationPromptPlaceholder =>
      'Ikaw ay isang kahanga-hangang app, bibigyan ka ng transcript at summary ng isang conversation...';

  @override
  String get notificationScopes => 'Notification Scopes';

  @override
  String get appPrivacyAndTerms => 'App Privacy & Terms';

  @override
  String get makeMyAppPublic => 'Gawing public ang aking app';

  @override
  String get submitAppTermsAgreement =>
      'Sa pag-submit ng app na ito, sumasang-ayon ako sa Omi AI Terms of Service at Privacy Policy';

  @override
  String get submitApp => 'Magpadala ng App';

  @override
  String get needHelpGettingStarted => 'Kailangan mo ng tulong upang magsimula?';

  @override
  String get clickHereForAppBuildingGuides => 'I-click dito para sa mga app building guides at documentation';

  @override
  String get submitAppQuestion => 'Magpadala ng App?';

  @override
  String get submitAppPublicDescription =>
      'Ang iyong app ay ire-review at ginagawang public. Maaari kang magsimulang gamitin ito kaagad, kahit sa panahon ng review!';

  @override
  String get submitAppPrivateDescription =>
      'Ang iyong app ay ire-review at gagawin itong available sa iyo nang pribado. Maaari kang magsimulang gamitin ito kaagad, kahit sa panahon ng review!';

  @override
  String get startEarning => 'Magsimulang Kumita! 💰';

  @override
  String get connectStripeOrPayPal => 'Kumonekta sa Stripe o PayPal upang makatanggap ng mga bayad para sa iyong app.';

  @override
  String get connectNow => 'Kumonekta Ngayon';

  @override
  String get installsCount => 'Mga Installs';

  @override
  String get uninstallApp => 'I-uninstall ang App';

  @override
  String get subscribe => 'Sumali';

  @override
  String get dataAccessNotice => 'Data Access Notice';

  @override
  String get dataAccessWarning =>
      'Ang app na ito ay makakapag-access sa iyong data. Ang Omi AI ay hindi responsable sa kung paano ang iyong data ay ginagamit, binabago, o bina-delete ng app na ito';

  @override
  String get installApp => 'I-install ang App';

  @override
  String get betaTesterNotice =>
      'Ikaw ay isang beta tester para sa app na ito. Ito ay hindi pa public. Magiging public ito kapag naunang aprubahan.';

  @override
  String get appUnderReviewOwner =>
      'Ang iyong app ay nasa ilalim ng review at makikita lamang ng iyo. Magiging public ito kapag naunang aprubahan.';

  @override
  String get appRejectedNotice =>
      'Ang iyong app ay nireject. Pakibago ang mga detalye ng app at muling ipadala para sa review.';

  @override
  String get setupSteps => 'Setup Steps';

  @override
  String get setupInstructions => 'Setup Instructions';

  @override
  String get integrationInstructions => 'Integration Instructions';

  @override
  String get preview => 'Preview';

  @override
  String get aboutTheApp => 'Tungkol sa App';

  @override
  String get chatPersonality => 'Chat Personality';

  @override
  String get ratingsAndReviews => 'Ratings & Reviews';

  @override
  String get noRatings => 'walang ratings';

  @override
  String ratingsCount(String count) {
    return '$count+ ratings';
  }

  @override
  String get errorActivatingApp => 'Error sa pag-activate ng app';

  @override
  String get integrationSetupRequired => 'Kung ito ay isang integration app, siguraduhin na ang setup ay nakumpleto.';

  @override
  String get installed => 'Nai-install';

  @override
  String get appIdLabel => 'App ID';

  @override
  String get appNameLabel => 'App Name';

  @override
  String get appNamePlaceholder => 'My Awesome App';

  @override
  String get pleaseEnterAppName => 'Pakipasok ang pangalan ng app';

  @override
  String get categoryLabel => 'Category';

  @override
  String get selectCategory => 'Pumili ng Category';

  @override
  String get descriptionLabel => 'Description';

  @override
  String get appDescriptionPlaceholder =>
      'My Awesome App ay isang mahusay na app na gumagawa ng mga kahanga-hangang bagay. Ito ang pinakamagandang app!';

  @override
  String get pleaseProvideValidDescription => 'Pakibigay ng isang wastong paglalarawan';

  @override
  String get appPricingLabel => 'App Pricing';

  @override
  String get noneSelected => 'Walang Napili';

  @override
  String get appIdCopiedToClipboard => 'App ID ay nai-copy sa clipboard';

  @override
  String get appCategoryModalTitle => 'App Category';

  @override
  String get pricingFree => 'Libre';

  @override
  String get pricingPaid => 'Bayad';

  @override
  String get loadingCapabilities => 'Kumakarga ng capabilities...';

  @override
  String get filterInstalled => 'Nai-install';

  @override
  String get filterMyApps => 'Ang Aking Mga App';

  @override
  String get clearSelection => 'Burahin ang seleksyon';

  @override
  String get filterCategory => 'Category';

  @override
  String get rating4PlusStars => '4+ Stars';

  @override
  String get rating3PlusStars => '3+ Stars';

  @override
  String get rating2PlusStars => '2+ Stars';

  @override
  String get rating1PlusStars => '1+ Stars';

  @override
  String get filterRating => 'Rating';

  @override
  String get filterCapabilities => 'Capabilities';

  @override
  String get noNotificationScopesAvailable => 'Walang mga notification scopes na available';

  @override
  String get popularApps => 'Popular Apps';

  @override
  String get pleaseProvidePrompt => 'Pakibigay ng prompt';

  @override
  String chatWithAppName(String appName) {
    return 'Makipag-chat sa $appName';
  }

  @override
  String get defaultAiAssistant => 'Default AI Assistant';

  @override
  String get readyToChat => '✨ Handa nang makipag-chat!';

  @override
  String get connectionNeeded => '🌐 Kailangan ng koneksyon';

  @override
  String get startConversation => 'Magsimula ng isang conversation at hayaan ang magic na magsimula';

  @override
  String get checkInternetConnection => 'Pakisuri ang iyong koneksyon sa internet';

  @override
  String get wasThisHelpful => 'Nakatulong ba ito?';

  @override
  String get thankYouForFeedback => 'Salamat sa iyong feedback!';

  @override
  String get maxFilesUploadError => 'Maaari lamang kang mag-upload ng 4 file nang sabay-sabay';

  @override
  String get attachedFiles => '📎 Attached Files';

  @override
  String get takePhoto => 'Kumuha ng Photo';

  @override
  String get captureWithCamera => 'Kumuha gamit ang camera';

  @override
  String get selectImages => 'Pumili ng Mga Larawan';

  @override
  String get chooseFromGallery => 'Pumili mula sa gallery';

  @override
  String get selectFile => 'Pumili ng File';

  @override
  String get chooseAnyFileType => 'Pumili ng anumang uri ng file';

  @override
  String get cannotReportOwnMessages => 'Hindi mo maaaring i-report ang iyong sariling mga mensahe';

  @override
  String get messageReportedSuccessfully => '✅ Ang mensahe ay matagumpay na nai-report';

  @override
  String get confirmReportMessage => 'Sigurado ka na ba na nais mong i-report ang mensaheng ito?';

  @override
  String get selectChatAssistant => 'Pumili ng Chat Assistant';

  @override
  String get enableMoreApps => 'Paganahin ang Higit Pang Mga App';

  @override
  String get chatCleared => 'Chat ay na-clear';

  @override
  String get clearChatTitle => 'I-clear ang Chat?';

  @override
  String get confirmClearChat =>
      'Sigurado ka na ba na nais mong i-clear ang chat? Ang aksyong ito ay hindi maaaring bawiin.';

  @override
  String get copy => 'Kopyahin';

  @override
  String get share => 'Ibahagi';

  @override
  String get report => 'I-report';

  @override
  String get microphonePermissionRequired => 'Kailangan ng microphone permission upang gumawa ng mga tawag';

  @override
  String get microphonePermissionDenied =>
      'Microphone permission ay natatanggihan. Pakigive ng pahintulot sa System Preferences > Privacy & Security > Microphone.';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'Nabigong suriin ang Microphone permission: $error';
  }

  @override
  String get failedToTranscribeAudio => 'Nabigong mag-transcribe ng audio';

  @override
  String get transcribing => 'Nag-transcribe...';

  @override
  String get transcriptionFailed => 'Ang transcription ay nabigo';

  @override
  String get discardedConversation => 'Itinakda ang Conversation';

  @override
  String get at => 'sa';

  @override
  String get from => 'mula sa';

  @override
  String get copied => 'Nakopyahin!';

  @override
  String get copyLink => 'Kopyahin ang link';

  @override
  String get hideTranscript => 'Itago ang Transcript';

  @override
  String get viewTranscript => 'Tingnan ang Transcript';

  @override
  String get conversationDetails => 'Conversation Details';

  @override
  String get transcript => 'Transcript';

  @override
  String segmentsCount(int count) {
    return '$count segments';
  }

  @override
  String get noTranscriptAvailable => 'Walang Transcript Available';

  @override
  String get noTranscriptMessage => 'Ang conversation na ito ay walang transcript.';

  @override
  String get conversationUrlCouldNotBeGenerated => 'Ang URL ng conversation ay hindi maaaring mailikha.';

  @override
  String get failedToGenerateConversationLink => 'Nabigong lumikha ng conversation link';

  @override
  String get failedToGenerateShareLink => 'Nabigong lumikha ng share link';

  @override
  String get reloadingConversations => 'Nag-reload ng mga conversation...';

  @override
  String get user => 'User';

  @override
  String get starred => 'Naka-star';

  @override
  String get date => 'Petsa';

  @override
  String get noResultsFound => 'Walang resulta na nahanap';

  @override
  String get tryAdjustingSearchTerms => 'Subukan ang pag-adjust ng iyong mga search terms';

  @override
  String get starConversationsToFindQuickly => 'I-star ang mga conversation upang makita ang mga ito nang mabilis dito';

  @override
  String noConversationsOnDate(String date) {
    return 'Walang mga conversation sa $date';
  }

  @override
  String get trySelectingDifferentDate => 'Subukan ang pagpili ng ibang petsa';

  @override
  String get conversations => 'Mga Conversation';

  @override
  String get chat => 'Chat';

  @override
  String get actions => 'Mga Aksyon';

  @override
  String get syncAvailable => 'Sync Available';

  @override
  String get referAFriend => 'Mag-refer ng Kaibigan';

  @override
  String get help => 'Tulong';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'Mag-upgrade sa Pro';

  @override
  String get getOmiDevice => 'Kumuha ng Omi Device';

  @override
  String get wearableAiCompanion => 'Wearable AI companion';

  @override
  String get loadingMemories => 'Kumakarga ng mga memories...';

  @override
  String get allMemories => 'Lahat ng Memories';

  @override
  String get aboutYou => 'Tungkol sa Iyo';

  @override
  String get manual => 'Manual';

  @override
  String get loadingYourMemories => 'Kumakarga ng iyong mga memories...';

  @override
  String get createYourFirstMemory => 'Lumikha ng iyong unang memory upang magsimula';

  @override
  String get tryAdjustingFilter => 'Subukan ang pag-adjust ng iyong paghahanap o filter';

  @override
  String get whatWouldYouLikeToRemember => 'Ano ang nais mong matandaan?';

  @override
  String get category => 'Category';

  @override
  String get public => 'Public';

  @override
  String get failedToSaveCheckConnection => 'Nabigong mag-save. Pakisuri ang iyong koneksyon.';

  @override
  String get createMemory => 'Lumikha ng Memory';

  @override
  String get deleteMemoryConfirmation =>
      'Sigurado ka na ba na nais mong burahin ang memory na ito? Ang aksyong ito ay hindi maaaring bawiin.';

  @override
  String get makePrivate => 'Gawing Private';

  @override
  String get organizeAndControlMemories => 'Mag-organize at kontrol ang iyong mga memories';

  @override
  String get total => 'Total';

  @override
  String get makeAllMemoriesPrivate => 'Gawing Private ang Lahat ng Memories';

  @override
  String get setAllMemoriesToPrivate => 'Itakda ang lahat ng memories sa private visibility';

  @override
  String get makeAllMemoriesPublic => 'Gawing Public ang Lahat ng Memories';

  @override
  String get setAllMemoriesToPublic => 'Itakda ang lahat ng memories sa public visibility';

  @override
  String get permanentlyRemoveAllMemories => 'Permanenteng alisin ang lahat ng memories mula sa Omi';

  @override
  String get allMemoriesAreNowPrivate => 'Ang lahat ng memories ay ngayon private';

  @override
  String get allMemoriesAreNowPublic => 'Ang lahat ng memories ay ngayon public';

  @override
  String get clearOmisMemory => 'Burahin ang Memory ng Omi';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Sigurado ka na ba na nais mong burahin ang memory ng Omi? Ang aksyong ito ay hindi maaaring bawiin at permanenteng magsasabing lahat ng $count memories.';
  }

  @override
  String get omisMemoryCleared => 'Ang memory ng Omi tungkol sa iyo ay nabura na';

  @override
  String get welcomeToOmi => 'Maligayang pagdating sa Omi';

  @override
  String get continueWithApple => 'Magpatuloy sa Apple';

  @override
  String get continueWithGoogle => 'Magpatuloy sa Google';

  @override
  String get byContinuingYouAgree => 'Sa pamamagitan ng pagpatuloy, sumasang-ayon ka sa aming ';

  @override
  String get termsOfService => 'Mga Kondisyon ng Serbisyo';

  @override
  String get and => ' at ';

  @override
  String get dataAndPrivacy => 'Data & Privacy';

  @override
  String get secureAuthViaAppleId => 'Secure na pagpapatunay sa pamamagitan ng Apple ID';

  @override
  String get secureAuthViaGoogleAccount => 'Secure na pagpapatunay sa pamamagitan ng Google Account';

  @override
  String get whatWeCollect => 'Kung ano ang aming kinokolekta';

  @override
  String get dataCollectionMessage =>
      'Sa pamamagitan ng pagpatuloy, ang iyong mga conversation, recording, at personal na impormasyon ay ligtas na maiipon sa aming mga server upang magbigay ng AI-powered insights at paganahin ang lahat ng features ng app.';

  @override
  String get dataProtection => 'Proteksyon ng Data';

  @override
  String get yourDataIsProtected => 'Ang iyong data ay protektado at pinamamahalaan ng aming ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'Piliin ang iyong pangunahing wika';

  @override
  String get chooseYourLanguage => 'Piliin ang iyong wika';

  @override
  String get selectPreferredLanguageForBestExperience =>
      'Piliin ang iyong preferred na wika para sa pinakamahusay na Omi experience';

  @override
  String get searchLanguages => 'Maghanap ng mga wika...';

  @override
  String get selectALanguage => 'Pumili ng isang wika';

  @override
  String get tryDifferentSearchTerm => 'Subukan ang ibang search term';

  @override
  String get pleaseEnterYourName => 'Mangyaring ilagay ang iyong pangalan';

  @override
  String get nameMustBeAtLeast2Characters => 'Ang pangalan ay dapat na hindi bababa sa 2 characters';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'Sabihin sa amin kung paano ka nais tawagan. Ito ay tumutulong na i-personalize ang iyong Omi experience.';

  @override
  String charactersCount(int count) {
    return '$count characters';
  }

  @override
  String get enableFeaturesForBestExperience =>
      'Paganahin ang mga features para sa pinakamahusay na Omi experience sa iyong device.';

  @override
  String get microphoneAccess => 'Microphone Access';

  @override
  String get recordAudioConversations => 'I-record ang audio conversations';

  @override
  String get microphoneAccessDescription =>
      'Kailangan ng Omi ang microphone access upang i-record ang iyong mga conversation at magbigay ng mga transcription.';

  @override
  String get screenRecording => 'Screen Recording';

  @override
  String get captureSystemAudioFromMeetings => 'Kunin ang system audio mula sa mga meeting';

  @override
  String get screenRecordingDescription =>
      'Kailangan ng Omi ng screen recording permission upang kunin ang system audio mula sa iyong browser-based na mga meeting.';

  @override
  String get accessibility => 'Accessibility';

  @override
  String get detectBrowserBasedMeetings => 'Tukuyin ang browser-based na mga meeting';

  @override
  String get accessibilityDescription =>
      'Kailangan ng Omi ng accessibility permission upang matukoy kung kailan ka sumali sa Zoom, Meet, o Teams meetings sa iyong browser.';

  @override
  String get pleaseWait => 'Mangyaring maghintay...';

  @override
  String get joinTheCommunity => 'Sumali sa komunidad!';

  @override
  String get loadingProfile => 'Nag-load ng profile...';

  @override
  String get profileSettings => 'Profile Settings';

  @override
  String get noEmailSet => 'Walang email na itinakda';

  @override
  String get userIdCopiedToClipboard => 'User ID na kinopya sa clipboard';

  @override
  String get yourInformation => 'Ang Iyong Impormasyon';

  @override
  String get setYourName => 'Itakda ang Iyong Pangalan';

  @override
  String get changeYourName => 'Baguhin ang Iyong Pangalan';

  @override
  String get voiceAndPeople => 'Boses & Tao';

  @override
  String get teachOmiYourVoice => 'Turuan ang Omi ng iyong boses';

  @override
  String get tellOmiWhoSaidIt => 'Sabihin sa Omi kung sino ang nagsabi nito 🗣️';

  @override
  String get payment => 'Pagbabayad';

  @override
  String get addOrChangeYourPaymentMethod => 'Magdagdag o baguhin ang iyong payment method';

  @override
  String get preferences => 'Mga Kagustuhan';

  @override
  String get helpImproveOmiBySharing =>
      'Tumulong na mapabuti ang Omi sa pamamagitan ng pagbabahagi ng anonymized analytics data';

  @override
  String get deleteAccount => 'Burahin ang Account';

  @override
  String get deleteYourAccountAndAllData => 'Burahin ang iyong account at lahat ng data';

  @override
  String get clearLogs => 'I-clear ang logs';

  @override
  String get debugLogsCleared => 'Debug logs na nai-clear';

  @override
  String get exportConversations => 'I-export ang Mga Conversation';

  @override
  String get exportAllConversationsToJson => 'I-export ang lahat ng iyong mga conversation sa isang JSON file.';

  @override
  String get conversationsExportStarted =>
      'Nagsimula na ang Conversations Export. Ito ay maaaring tumagal ng ilang segundo, mangyaring maghintay.';

  @override
  String get mcpDescription =>
      'Upang ikonekta ang Omi sa ibang mga aplikasyon upang basahin, maghanap, at pamahalaan ang iyong mga memory at conversation. Lumikha ng isang key upang magsimula.';

  @override
  String get apiKeys => 'API Keys';

  @override
  String errorLabel(String error) {
    return 'Error: $error';
  }

  @override
  String get noApiKeysFound => 'Walang API keys na nahanap. Lumikha ng isa upang magsimula.';

  @override
  String get advancedSettings => 'Advanced Settings';

  @override
  String get triggersWhenNewConversationCreated => 'Nag-trigger kapag ang isang bagong conversation ay nilikha.';

  @override
  String get triggersWhenNewTranscriptReceived => 'Nag-trigger kapag ang isang bagong transcript ay natanggap.';

  @override
  String get realtimeAudioBytes => 'Realtime Audio Bytes';

  @override
  String get triggersWhenAudioBytesReceived => 'Nag-trigger kapag ang audio bytes ay natanggap.';

  @override
  String get everyXSeconds => 'Bawat x segundo';

  @override
  String get triggersWhenDaySummaryGenerated => 'Nag-trigger kapag ang day summary ay nabuo.';

  @override
  String get tryLatestExperimentalFeatures => 'Subukan ang pinakabagong experimental features mula sa Omi Team.';

  @override
  String get transcriptionServiceDiagnosticStatus => 'Transcription service diagnostic status';

  @override
  String get enableDetailedDiagnosticMessages =>
      'Paganahin ang detailed diagnostic messages mula sa transcription service';

  @override
  String get autoCreateAndTagNewSpeakers => 'Auto-create at mag-tag ng bagong mga speaker';

  @override
  String get automaticallyCreateNewPerson =>
      'Awtomatikong lumikha ng isang bagong tao kapag ang isang pangalan ay na-detect sa transcript.';

  @override
  String get pilotFeatures => 'Pilot Features';

  @override
  String get pilotFeaturesDescription => 'Ang mga features na ito ay mga pagsubok at walang guaranteed na suporta.';

  @override
  String get suggestFollowUpQuestion => 'Mag-suggest ng follow up question';

  @override
  String get saveSettings => 'I-save ang Mga Setting';

  @override
  String get syncingDeveloperSettings => 'Nag-sync ng Developer Settings...';

  @override
  String get summary => 'Buod';

  @override
  String get auto => 'Awtomatiko';

  @override
  String get noSummaryForApp =>
      'Walang buod na available para sa app na ito. Subukan ang ibang app para sa mas mahusay na resulta.';

  @override
  String get tryAnotherApp => 'Subukan ang Ibang App';

  @override
  String generatedBy(String appName) {
    return 'Nabuo ng $appName';
  }

  @override
  String get overview => 'Pangkalahatang Pananaw';

  @override
  String get otherAppResults => 'Ibang App Results';

  @override
  String get unknownApp => 'Unknownong App';

  @override
  String get noSummaryAvailable => 'Walang Buod na Available';

  @override
  String get conversationNoSummaryYet => 'Ang conversation na ito ay wala pang buod.';

  @override
  String get chooseSummarizationApp => 'Pumili ng Summarization App';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return 'Ang $appName ay itinakda bilang default summarization app';
  }

  @override
  String get letOmiChooseAutomatically => 'Hayaan ang Omi na pumili ng pinakamahusay na app nang awtomatiko';

  @override
  String get deleteConversationConfirmation =>
      'Sigurado ka na ba na gusto mong burahin ang conversation na ito? Ang aksyong ito ay hindi mababawi.';

  @override
  String get conversationDeleted => 'Conversation na nabura';

  @override
  String get generatingLink => 'Gumagawa ng link...';

  @override
  String get editConversation => 'I-edit ang conversation';

  @override
  String get conversationLinkCopiedToClipboard => 'Conversation link na kinopya sa clipboard';

  @override
  String get conversationTranscriptCopiedToClipboard => 'Conversation transcript na kinopya sa clipboard';

  @override
  String get editConversationDialogTitle => 'I-edit ang Conversation';

  @override
  String get changeTheConversationTitle => 'Baguhin ang pamagat ng conversation';

  @override
  String get conversationTitle => 'Conversation Title';

  @override
  String get enterConversationTitle => 'Ilagay ang pamagat ng conversation...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'Conversation title na successfully na-update';

  @override
  String get failedToUpdateConversationTitle => 'Failed na i-update ang conversation title';

  @override
  String get errorUpdatingConversationTitle => 'Error sa pag-update ng conversation title';

  @override
  String get settingUp => 'Nag-setup...';

  @override
  String get startYourFirstRecording => 'Magsimula ng Iyong Unang Recording';

  @override
  String get preparingSystemAudioCapture => 'Nag-prepare ng system audio capture';

  @override
  String get clickTheButtonToCaptureAudio =>
      'I-click ang button upang kunin ang audio para sa live transcripts, AI insights, at automatic saving.';

  @override
  String get reconnecting => 'Nag-reconnect...';

  @override
  String get recordingPaused => 'Recording na Iniwas';

  @override
  String get recordingActive => 'Recording na Aktibo';

  @override
  String get startRecording => 'Magsimula ng Recording';

  @override
  String resumingInCountdown(String countdown) {
    return 'Magsisimula ulit sa ${countdown}s...';
  }

  @override
  String get tapPlayToResume => 'Itap ang play upang magpatuloy';

  @override
  String get listeningForAudio => 'Nakinig para sa audio...';

  @override
  String get preparingAudioCapture => 'Nag-prepare ng audio capture';

  @override
  String get clickToBeginRecording => 'I-click upang magsimula ng recording';

  @override
  String get translated => 'isinalin';

  @override
  String get liveTranscript => 'Live Transcript';

  @override
  String segmentsSingular(String count) {
    return '$count segment';
  }

  @override
  String segmentsPlural(String count) {
    return '$count segments';
  }

  @override
  String get startRecordingToSeeTranscript => 'Magsimula ng recording upang makita ang live transcript';

  @override
  String get paused => 'Iniwas';

  @override
  String get initializing => 'Nag-initialize...';

  @override
  String get recording => 'Nag-record';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'Microphone na nagbago. Magsisimula ulit sa ${countdown}s';
  }

  @override
  String get clickPlayToResumeOrStop => 'I-click ang play upang magpatuloy o stop upang tapusin';

  @override
  String get settingUpSystemAudioCapture => 'Nag-setup ng system audio capture';

  @override
  String get capturingAudioAndGeneratingTranscript => 'Kumukuha ng audio at gumagawa ng transcript';

  @override
  String get clickToBeginRecordingSystemAudio => 'I-click upang magsimula ng pag-record ng system audio';

  @override
  String get you => 'Ikaw';

  @override
  String speakerWithId(String speakerId) {
    return 'Speaker $speakerId';
  }

  @override
  String get translatedByOmi => 'isinalin ng omi';

  @override
  String get backToConversations => 'Bumalik sa Mga Conversation';

  @override
  String get systemAudio => 'System';

  @override
  String get mic => 'Mic';

  @override
  String audioInputSetTo(String deviceName) {
    return 'Audio input na itinakda sa $deviceName';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'Error sa pag-switch ng audio device: $error';
  }

  @override
  String get selectAudioInput => 'Pumili ng Audio Input';

  @override
  String get loadingDevices => 'Nag-load ng mga device...';

  @override
  String get settingsHeader => 'SETTINGS';

  @override
  String get plansAndBilling => 'Mga Plano & Pagbabayad';

  @override
  String get calendarIntegration => 'Calendar Integration';

  @override
  String get dailySummary => 'Daily Summary';

  @override
  String get developer => 'Developer';

  @override
  String get about => 'Tungkol';

  @override
  String get selectTime => 'Pumili ng Oras';

  @override
  String get accountGroup => 'Account';

  @override
  String get signOutQuestion => 'Mag-sign Out?';

  @override
  String get signOutConfirmation => 'Sigurado ka na ba na gusto mong mag-sign out?';

  @override
  String get customVocabularyHeader => 'CUSTOM VOCABULARY';

  @override
  String get addWordsDescription => 'Magdagdag ng mga salita na dapat kilalanin ng Omi sa panahon ng transcription.';

  @override
  String get enterWordsHint => 'Ilagay ang mga salita (comma separated)';

  @override
  String get dailySummaryHeader => 'DAILY SUMMARY';

  @override
  String get dailySummaryTitle => 'Daily Summary';

  @override
  String get dailySummaryDescription =>
      'Makatanggap ng personalized na buod ng iyong mga conversation sa araw na ipadala bilang notipikasyon.';

  @override
  String get deliveryTime => 'Oras ng Paghahatid';

  @override
  String get deliveryTimeDescription => 'Kailan makakatanggap ng iyong daily summary';

  @override
  String get subscription => 'Subscription';

  @override
  String get viewPlansAndUsage => 'Tingnan ang Mga Plano & Paggamit';

  @override
  String get viewPlansDescription => 'Pamahalaan ang iyong subscription at makita ang usage stats';

  @override
  String get addOrChangePaymentMethod => 'Magdagdag o baguhin ang iyong payment method';

  @override
  String get displayOptions => 'Display Options';

  @override
  String get showMeetingsInMenuBar => 'Ipakita ang Mga Meeting sa Menu Bar';

  @override
  String get displayUpcomingMeetingsDescription => 'Ipakita ang paparating na mga meeting sa menu bar';

  @override
  String get showEventsWithoutParticipants => 'Ipakita ang Mga Event na Walang Participants';

  @override
  String get includePersonalEventsDescription => 'Isama ang personal na mga event na walang attendee';

  @override
  String get upcomingMeetings => 'Paparating na Mga Meeting';

  @override
  String get checkingNext7Days => 'Sinusuri ang susunod na 7 araw';

  @override
  String get shortcuts => 'Mga Shortcut';

  @override
  String get shortcutChangeInstruction =>
      'I-click sa isang shortcut upang baguhin ito. Pindutin ang Escape upang kanselahin.';

  @override
  String get configureSTTProvider => 'I-configure ang STT provider';

  @override
  String get setConversationEndDescription => 'Itakda kung kailan mag-auto-end ang mga conversation';

  @override
  String get importDataDescription => 'Mag-import ng data mula sa ibang mga source';

  @override
  String get exportConversationsDescription => 'I-export ang mga conversation sa JSON';

  @override
  String get exportingConversations => 'Nag-export ng mga conversation...';

  @override
  String get clearNodesDescription => 'I-clear ang lahat ng nodes at connections';

  @override
  String get deleteKnowledgeGraphQuestion => 'Burahin ang Knowledge Graph?';

  @override
  String get deleteKnowledgeGraphWarning =>
      'Ito ay buburahin ang lahat ng derived knowledge graph data. Ang iyong original na mga memory ay manatiling ligtas.';

  @override
  String get connectOmiWithAI => 'Ikonekta ang Omi sa AI assistants';

  @override
  String get noAPIKeys => 'Walang API keys. Lumikha ng isa upang magsimula.';

  @override
  String get autoCreateWhenDetected => 'Auto-create kapag na-detect ang pangalan';

  @override
  String get trackPersonalGoals => 'Subaybayan ang personal na mga layunin sa homepage';

  @override
  String get endpointURL => 'Endpoint URL';

  @override
  String get links => 'Mga Link';

  @override
  String get discordMemberCount => '8000+ members sa Discord';

  @override
  String get userInformation => 'Impormasyon ng User';

  @override
  String get capabilities => 'Mga Kakayahan';

  @override
  String get previewScreenshots => 'Tingnan ang Preview ng Screenshots';

  @override
  String get holdOnPreparingForm => 'Maghintay, kami ay nag-prepare ng form para sa iyo';

  @override
  String get bySubmittingYouAgreeToOmi => 'Sa pamamagitan ng pagpapadala, sumasang-ayon ka sa Omi ';

  @override
  String get termsAndPrivacyPolicy => 'Mga Kondisyon & Privacy Policy';

  @override
  String get helpsDiagnoseIssuesAutoDeletes => 'Tumutulong na tukuyin ang mga isyu. Auto-deletes pagkatapos ng 3 araw.';

  @override
  String get manageYourApp => 'Pamahalaan ang Iyong App';

  @override
  String get updatingYourApp => 'Nag-update ng iyong app';

  @override
  String get fetchingYourAppDetails => 'Nag-fetch ng iyong app details';

  @override
  String get updateAppQuestion => 'I-update ang App?';

  @override
  String get updateAppConfirmation =>
      'Sigurado ka na ba na gusto mong i-update ang iyong app? Ang mga pagbabago ay makikita kapag na-review na ng aming team.';

  @override
  String get updateApp => 'I-update ang App';

  @override
  String get createAndSubmitNewApp => 'Lumikha at mag-submit ng bagong app';

  @override
  String appsCount(String count) {
    return 'Mga App ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'Private Mga App ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'Public Mga App ($count)';
  }

  @override
  String get newVersionAvailable => 'Ang Bagong Bersyon ay Available 🎉';

  @override
  String get no => 'Hindi';

  @override
  String get subscriptionCancelledSuccessfully =>
      'Subscription na successfully na-cancel. Ito ay manatiling aktibo hanggang sa katapusan ng current billing period.';

  @override
  String get failedToCancelSubscription => 'Failed na i-cancel ang subscription. Mangyaring subukan ulit.';

  @override
  String get invalidPaymentUrl => 'Invalid payment URL';

  @override
  String get permissionsAndTriggers => 'Mga Pahintulot & Triggers';

  @override
  String get chatFeatures => 'Chat Features';

  @override
  String get uninstall => 'I-uninstall';

  @override
  String get installs => 'INSTALLS';

  @override
  String get priceLabel => 'PRESYO';

  @override
  String get updatedLabel => 'NA-UPDATE';

  @override
  String get createdLabel => 'NILIKHA';

  @override
  String get featuredLabel => 'FEATURED';

  @override
  String get cancelSubscriptionQuestion => 'I-cancel ang Subscription?';

  @override
  String get cancelSubscriptionConfirmation =>
      'Sigurado ka na ba na gusto mong i-cancel ang iyong subscription? Magpapatuloy kang may access hanggang sa katapusan ng iyong current billing period.';

  @override
  String get cancelSubscriptionButton => 'I-cancel ang Subscription';

  @override
  String get cancelling => 'Nag-cancel...';

  @override
  String get betaTesterMessage =>
      'Ikaw ay isang beta tester para sa app na ito. Hindi pa ito pampubliko. Ito ay magiging pampubliko kapag na-approve na.';

  @override
  String get appUnderReviewMessage =>
      'Ang iyong app ay nasa review at makikita lamang ng iyo. Ito ay magiging pampubliko kapag na-approve na.';

  @override
  String get appRejectedMessage =>
      'Ang iyong app ay naging reject. Mangyaring i-update ang app details at mag-resubmit para sa review.';

  @override
  String get invalidIntegrationUrl => 'Invalid integration URL';

  @override
  String get tapToComplete => 'Itap upang makumpleto';

  @override
  String get invalidSetupInstructionsUrl => 'Invalid setup instructions URL';

  @override
  String get pushToTalk => 'Push to Talk';

  @override
  String get summaryPrompt => 'Summary Prompt';

  @override
  String get pleaseSelectARating => 'Mangyaring pumili ng rating';

  @override
  String get reviewAddedSuccessfully => 'Review na successfully na-add 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'Review na successfully na-update 🚀';

  @override
  String get failedToSubmitReview => 'Failed na mag-submit ng review. Mangyaring subukan ulit.';

  @override
  String get addYourReview => 'Magdagdag ng Iyong Review';

  @override
  String get editYourReview => 'I-edit ang Iyong Review';

  @override
  String get writeAReviewOptional => 'Magsulat ng review (optional)';

  @override
  String get submitReview => 'Mag-submit ng Review';

  @override
  String get updateReview => 'I-update ang Review';

  @override
  String get yourReview => 'Ang Iyong Review';

  @override
  String get anonymousUser => 'Anonymous na User';

  @override
  String get issueActivatingApp => 'Mayroong isyu sa pag-activate ng app na ito. Mangyaring subukan ulit.';

  @override
  String get dataAccessNoticeDescription =>
      'Ang app na ito ay mag-access sa iyong data. Ang Omi AI ay hindi responsable kung paano ginagamit, binabago, o binubura ang iyong data ng app na ito';

  @override
  String get copyUrl => 'Kopyahin ang URL';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => 'Lun';

  @override
  String get weekdayTue => 'Mar';

  @override
  String get weekdayWed => 'Miy';

  @override
  String get weekdayThu => 'Huw';

  @override
  String get weekdayFri => 'Biy';

  @override
  String get weekdaySat => 'Sab';

  @override
  String get weekdaySun => 'Lin';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return 'Ang $serviceName integration ay paparating na';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'Na-export na sa $platform';
  }

  @override
  String get anotherPlatform => 'iba pang platform';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'Mangyaring mag-authenticate sa $serviceName sa Settings > Task Integrations';
  }

  @override
  String addingToService(String serviceName) {
    return 'Nagdadagdag sa $serviceName...';
  }

  @override
  String addedToService(String serviceName) {
    return 'Naidagdag sa $serviceName';
  }

  @override
  String failedToAddToService(String serviceName) {
    return 'Failed na magdagdag sa $serviceName';
  }

  @override
  String get permissionDeniedForAppleReminders => 'Permission denied para sa Apple Reminders';

  @override
  String failedToCreateApiKey(String error) {
    return 'Failed na lumikha ng provider API key: $error';
  }

  @override
  String get createAKey => 'Lumikha ng Key';

  @override
  String get apiKeyRevokedSuccessfully => 'API key na successfully na-revoke';

  @override
  String failedToRevokeApiKey(String error) {
    return 'Failed na mag-revoke ng API key: $error';
  }

  @override
  String get omiApiKeys => 'Omi API Keys';

  @override
  String get apiKeysDescription =>
      'Ang API Keys ay ginagamit para sa authentication kapag ang iyong app ay nakikipag-ugnayan sa OMI server. Pinapayagan nila ang iyong application na lumikha ng mga memory at mag-access ng ibang OMI services nang secure.';

  @override
  String get aboutOmiApiKeys => 'Tungkol sa Omi API Keys';

  @override
  String get yourNewKey => 'Ang iyong bagong key:';

  @override
  String get copyToClipboard => 'Kopyahin sa clipboard';

  @override
  String get pleaseCopyKeyNow => 'Mangyaring kopyahin ito ngayon at isulat ito sa isang ligtas na lugar. ';

  @override
  String get willNotSeeAgain => 'Hindi mo na makikita ito ulit.';

  @override
  String get revokeKey => 'Mag-revoke ng key';

  @override
  String get revokeApiKeyQuestion => 'Mag-revoke ng API Key?';

  @override
  String get revokeApiKeyWarning =>
      'Ang aksyong ito ay hindi mababawi. Ang anumang aplikasyon na gumagamit ng key na ito ay hindi na makakapag-access sa API.';

  @override
  String get revoke => 'Mag-revoke';

  @override
  String get whatWouldYouLikeToCreate => 'Ano ang gusto mong likhain?';

  @override
  String get createAnApp => 'Lumikha ng App';

  @override
  String get createAndShareYourApp => 'Lumikha at ibahagi ang iyong app';

  @override
  String get itemApp => 'App';

  @override
  String keepItemPublic(String item) {
    return 'Panatilihing Pampubliko ang $item';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return 'Gawing Pampubliko ang $item?';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return 'Gawing Pribado ang $item?';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'Kung gagawin mong pampubliko ang $item, maaari itong gamitin ng lahat';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'Kung gagawin mong pribado ang $item ngayon, ito ay titigil na gumana para sa lahat at makikita lamang ng iyo';
  }

  @override
  String get manageApp => 'Pamahalaan ang App';

  @override
  String deleteItemTitle(String item) {
    return 'Burahin ang $item';
  }

  @override
  String deleteItemQuestion(String item) {
    return 'Burahin ang $item?';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'Sigurado ka na ba na gusto mong burahin ang $item? Ang aksyong ito ay hindi mababawi.';
  }

  @override
  String get revokeKeyQuestion => 'Mag-revoke ng Key?';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'Sigurado ka na ba na gusto mong mag-revoke ng key na \"$keyName\"? Ang aksyong ito ay hindi mababawi.';
  }

  @override
  String get createNewKey => 'Lumikha ng Bagong Key';

  @override
  String get keyNameHint => 'e.g., Claude Desktop';

  @override
  String get pleaseEnterAName => 'Mangyaring ilagay ang isang pangalan.';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'Failed na lumikha ng key: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'Failed na lumikha ng key. Mangyaring subukan ulit.';

  @override
  String get keyCreated => 'Key na Nilikha';

  @override
  String get keyCreatedMessage =>
      'Ang iyong bagong key ay na-create na. Mangyaring kopyahin ito ngayon. Hindi mo na makikita ito ulit.';

  @override
  String get keyWord => 'Key';

  @override
  String get externalAppAccess => 'External App Access';

  @override
  String get externalAppAccessDescription =>
      'Ang sumusunod na installed apps ay may external integrations at maaaring mag-access sa iyong data, tulad ng mga conversation at memory.';

  @override
  String get noExternalAppsHaveAccess => 'Walang external apps na may access sa iyong data.';

  @override
  String get maximumSecurityE2ee => 'Maximum Security (E2EE)';

  @override
  String get e2eeDescription =>
      'Ang end-to-end encryption ay ang gold standard para sa privacy. Kapag na-enable ito, ang iyong data ay naka-encrypt sa iyong device bago ipadala sa aming mga server. Ito ay nangangahulugang walang isa, hindi pa naman ang Omi, ay makaka-access sa iyong content.';

  @override
  String get importantTradeoffs => 'Mga Mahalagang Trade-offs:';

  @override
  String get e2eeTradeoff1 => '• Ang ilang features tulad ng external app integrations ay maaaring maging disabled.';

  @override
  String get e2eeTradeoff2 => '• Kung mawawalan ka ng iyong password, ang iyong data ay hindi mababawi.';

  @override
  String get featureComingSoon => 'Ang feature na ito ay paparating na!';

  @override
  String get migrationInProgressMessage =>
      'Migration na nag-iingay. Hindi mo mababago ang protection level hanggang sa ito ay nakumpleto.';

  @override
  String get migrationFailed => 'Migration na Failed';

  @override
  String migratingFromTo(String source, String target) {
    return 'Nag-migrate mula sa $source papunta sa $target';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total objects';
  }

  @override
  String get secureEncryption => 'Secure Encryption';

  @override
  String get secureEncryptionDescription =>
      'Ang iyong data ay naka-encrypt gamit ang isang key na natatangi sa iyo sa aming mga server, hosted sa Google Cloud. Ito ay nangangahulugang ang iyong raw na content ay hindi accessible sa sinuman, kabilang ang Omi staff o Google, direkta mula sa database.';

  @override
  String get endToEndEncryption => 'End-to-End Encryption';

  @override
  String get e2eeCardDescription =>
      'Paganahin para sa maximum security kung saan lamang ikaw ay maka-access sa iyong data. Itap upang matuto pa.';

  @override
  String get dataAlwaysEncrypted => 'Anuman ang level, ang iyong data ay laging encrypted sa rest at in transit.';

  @override
  String get readOnlyScope => 'Read Only';

  @override
  String get fullAccessScope => 'Full Access';

  @override
  String get readScope => 'Read';

  @override
  String get writeScope => 'Write';

  @override
  String get apiKeyCreated => 'API Key na Nilikha!';

  @override
  String get saveKeyWarning => 'I-save ang key na ito ngayon! Hindi mo na makikita ito ulit.';

  @override
  String get yourApiKey => 'ANG IYONG API KEY';

  @override
  String get tapToCopy => 'Itap upang kopyahin';

  @override
  String get copyKey => 'Kopyahin ang Key';

  @override
  String get createApiKey => 'Lumikha ng API Key';

  @override
  String get accessDataProgrammatically => 'I-access ang iyong data nang programmatically';

  @override
  String get keyNameLabel => 'KEY NAME';

  @override
  String get keyNamePlaceholder => 'e.g., My App Integration';

  @override
  String get permissionsLabel => 'PERMISSIONS';

  @override
  String get permissionsInfoNote => 'R = Read, W = Write. Defaults sa read-only kung walang napiling selection.';

  @override
  String get developerApi => 'Developer API';

  @override
  String get createAKeyToGetStarted => 'Lumikha ng key upang magsimula';

  @override
  String errorWithMessage(String error) {
    return 'Error: $error';
  }

  @override
  String get omiTraining => 'Omi Training';

  @override
  String get trainingDataProgram => 'Training Data Program';

  @override
  String get getOmiUnlimitedFree =>
      'Makakuha ng Omi Unlimited nang libre sa pamamagitan ng pagbibigay ng iyong data upang magsanay sa AI models.';

  @override
  String get trainingDataBullets =>
      '• Ang iyong data ay tumutulong na mapabuti ang AI models\n• Lamang ang non-sensitive data ang ibabahagi\n• Fully transparent na proseso';

  @override
  String get learnMoreAtOmiTraining => 'Matuto pa sa omi.me/training';

  @override
  String get agreeToContributeData => 'Nauunawaan at sumasang-ayon ako na magbigay ng iyong data para sa AI training';

  @override
  String get submitRequest => 'Mag-submit ng Request';

  @override
  String get thankYouRequestUnderReview =>
      'Salamat! Ang iyong request ay nasa review. Kami ay mag-notify sa iyo kapag na-approve na.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'Ang iyong plan ay manatiling aktibo hanggang sa $date. Pagkatapos, mawawalan ka ng access sa iyong unlimited features. Sigurado ka na ba?';
  }

  @override
  String get confirmCancellation => 'Kumpirmahin ang Cancellation';

  @override
  String get keepMyPlan => 'Panatilihin ang Aking Plan';

  @override
  String get subscriptionSetToCancel => 'Ang iyong subscription ay itinakda na mag-cancel sa katapusan ng period.';

  @override
  String get switchedToOnDevice => 'Lumipat sa on-device transcription';

  @override
  String get couldNotSwitchToFreePlan => 'Hindi maaaring lumipat sa libreng plano. Mangyaring subukan ulit.';

  @override
  String get couldNotLoadPlans => 'Hindi maaaring i-load ang mga available na plano. Mangyaring subukan ulit.';

  @override
  String get selectedPlanNotAvailable => 'Ang napiling plano ay hindi available. Mangyaring subukan ulit.';

  @override
  String get upgradeToAnnualPlan => 'Mag-upgrade sa Annual Plan';

  @override
  String get importantBillingInfo => 'Mahalagang Impormasyon sa Pagbabayad:';

  @override
  String get monthlyPlanContinues =>
      'Ang iyong kasalukuyang monthly plan ay magpapatuloy hanggang sa katapusan ng iyong billing period';

  @override
  String get paymentMethodCharged =>
      'Ang iyong existing payment method ay awtomatikong babayaran kapag nagtatapos ang iyong monthly plan';

  @override
  String get annualSubscriptionStarts =>
      'Ang iyong 12-buwan na annual subscription ay awtomatikong magsisimula pagkatapos ng bayad';

  @override
  String get thirteenMonthsCoverage =>
      'Makakakuha ka ng kabuuang 13 buwan ng coverage (kasalukuyang buwan + 12 buwan annual)';

  @override
  String get confirmUpgrade => 'Kumpirmahin ang Upgrade';

  @override
  String get confirmPlanChange => 'Kumpirmahin ang Pagbabago ng Plano';

  @override
  String get confirmAndProceed => 'Kumpirmahin & Magpatuloy';

  @override
  String get upgradeScheduled => 'Upgrade na Naka-schedule';

  @override
  String get changePlan => 'Baguhin ang Plano';

  @override
  String get upgradeAlreadyScheduled => 'Ang iyong upgrade sa annual plan ay naka-schedule na';

  @override
  String get youAreOnUnlimitedPlan => 'Ikaw ay nasa Unlimited Plan.';

  @override
  String get yourOmiUnleashed =>
      'Ang iyong Omi, na walang hanggan. Maging unlimited para sa walang hanggang posibilidad.';

  @override
  String planEndedOn(String date) {
    return 'Ang iyong plano ay nagtapos noong $date.\\nMag-subscribe muli ngayon - ikaw ay agad na babayaran para sa bagong billing period.';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'Ang iyong plano ay nakatakda na kanselahin sa $date.\\nMag-subscribe muli upang mapanatili ang iyong mga benepisyo - walang bayad hanggang $date.';
  }

  @override
  String get annualPlanStartsAutomatically =>
      'Ang iyong annual plan ay awtomatikong magsisimula kapag nagtatapos ang iyong monthly plan.';

  @override
  String planRenewsOn(String date) {
    return 'Ang iyong plano ay nag-renew sa $date.';
  }

  @override
  String get unlimitedConversations => 'Walang hanggang mga pag-uusap';

  @override
  String get askOmiAnything => 'Tanungin ang Omi tungkol sa kahit ano sa iyong buhay';

  @override
  String get unlockOmiInfiniteMemory => 'I-unlock ang walang hanggang memorya ng Omi';

  @override
  String get youreOnAnnualPlan => 'Ikaw ay nasa Annual Plan';

  @override
  String get alreadyBestValuePlan => 'Mayroon ka na ng pinakamahusay na value plan. Walang pagbabago na kailangan.';

  @override
  String get unableToLoadPlans => 'Hindi ma-load ang mga plan';

  @override
  String get checkConnectionTryAgain => 'Suriin ang koneksyon at subukan ulit';

  @override
  String get useFreePlan => 'Gamitin ang Free Plan';

  @override
  String get continueText => 'Magpatuloy';

  @override
  String get resubscribe => 'Mag-subscribe Muli';

  @override
  String get couldNotOpenPaymentSettings => 'Hindi maaaring buksan ang payment settings. Mangyaring subukan ulit.';

  @override
  String get managePaymentMethod => 'Pamahalaan ang Payment Method';

  @override
  String get cancelSubscription => 'Kanselahin ang Subscription';

  @override
  String endsOnDate(String date) {
    return 'Nagtatapos sa $date';
  }

  @override
  String get active => 'Aktibo';

  @override
  String get freePlan => 'Free Plan';

  @override
  String get configure => 'I-configure';

  @override
  String get privacyInformation => 'Impormasyon sa Privacy';

  @override
  String get yourPrivacyMattersToUs => 'Mahalaga sa Amin ang Iyong Privacy';

  @override
  String get privacyIntroText =>
      'Sa Omi, seryoso kami ang kinuha ang iyong privacy. Nais naming maging transparent tungkol sa data na aming kinukuha at kung paano namin ito ginagamit upang mapabuti ang aming produkto para sa iyo. Narito kung ano ang kailangan mong malaman:';

  @override
  String get whatWeTrack => 'Ano ang Aming Sinusubaybayan';

  @override
  String get anonymityAndPrivacy => 'Anonymity at Privacy';

  @override
  String get optInAndOptOutOptions => 'Mga Opsyon sa Opt-In at Opt-Out';

  @override
  String get ourCommitment => 'Ang Aming Pangako';

  @override
  String get commitmentText =>
      'Kami ay nakatuon sa paggamit ng data na aming kinukuha lamang upang gawing mas mahusay na produkto ang Omi para sa iyo. Ang iyong privacy at tiwala ay pangunahin para sa amin.';

  @override
  String get thankYouText =>
      'Salamat sa pagiging valued user ng Omi. Kung mayroon kang anumang mga katanungan o alalahanin, huwag mag-atubiling makipag-ugnayan sa amin sa team@basedhardware.com.';

  @override
  String get wifiSyncSettings => 'WiFi Sync Settings';

  @override
  String get enterHotspotCredentials => 'Ipasok ang iyong phone hotspot credentials';

  @override
  String get wifiSyncUsesHotspot =>
      'Ang WiFi sync ay gumagamit ng iyong phone bilang hotspot. Hanapin ang iyong hotspot name at password sa Settings > Personal Hotspot.';

  @override
  String get hotspotNameSsid => 'Hotspot Name (SSID)';

  @override
  String get exampleIphoneHotspot => 'halimbawa iPhone Hotspot';

  @override
  String get password => 'Password';

  @override
  String get enterHotspotPassword => 'Ipasok ang hotspot password';

  @override
  String get saveCredentials => 'I-save ang Credentials';

  @override
  String get clearCredentials => 'I-clear ang Credentials';

  @override
  String get pleaseEnterHotspotName => 'Mangyaring ipasok ang isang hotspot name';

  @override
  String get wifiCredentialsSaved => 'WiFi credentials na na-save';

  @override
  String get wifiCredentialsCleared => 'WiFi credentials na na-clear';

  @override
  String summaryGeneratedForDate(String date) {
    return 'Summary na nabuo para sa $date';
  }

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'Nabigong lumikha ng summary. Tiyakin na mayroon kang mga pag-uusap para sa araw na iyon.';

  @override
  String get summaryNotFound => 'Summary ay hindi nahanap';

  @override
  String get yourDaysJourney => 'Ang Iyong Araw na Paglalakbay';

  @override
  String get highlights => 'Highlights';

  @override
  String get unresolvedQuestions => 'Mga Walang Solusyong Tanong';

  @override
  String get decisions => 'Mga Desisyon';

  @override
  String get learnings => 'Mga Natutunan';

  @override
  String get autoDeletesAfterThreeDays => 'Awtomatikong nababura pagkatapos ng 3 araw.';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'Knowledge Graph ay matagumpay na nabura';

  @override
  String get exportStartedMayTakeFewSeconds => 'Export ay nagsimula. Maaaring ito ay aabot ng ilang segundo...';

  @override
  String get knowledgeGraphDeleteDescription =>
      'Ito ay magbabura ng lahat ng derived knowledge graph data (nodes at connections). Ang iyong mga orihinal na memories ay magiging ligtas. Ang graph ay muling mabubuo sa paglipas ng panahon o sa susunod na request.';

  @override
  String get configureDailySummaryDigest => 'I-configure ang iyong daily action items digest';

  @override
  String accessesDataTypes(String dataTypes) {
    return 'Nag-access ng $dataTypes';
  }

  @override
  String triggeredByType(String triggerType) {
    return 'na-trigger ng $triggerType';
  }

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription at ay $triggerDescription.';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return 'Ay $triggerDescription.';
  }

  @override
  String get noSpecificDataAccessConfigured => 'Walang specific data access na na-configure.';

  @override
  String get basicPlanDescription => '1,200 premium mins + unlimited on-device';

  @override
  String get minutes => 'minutes';

  @override
  String get omiHas => 'Mayroon ang Omi:';

  @override
  String get premiumMinutesUsed => 'Premium minutes na ginamit.';

  @override
  String get setupOnDevice => 'I-setup ang on-device';

  @override
  String get forUnlimitedFreeTranscription => 'para sa unlimited free transcription.';

  @override
  String premiumMinsLeft(int count) {
    return '$count premium mins na natitira.';
  }

  @override
  String get alwaysAvailable => 'laging available.';

  @override
  String get importHistory => 'Import History';

  @override
  String get noImportsYet => 'Walang imports pa';

  @override
  String get selectZipFileToImport => 'Piliin ang .zip file na i-import!';

  @override
  String get otherDevicesComingSoon => 'Iba pang devices ay paparating na';

  @override
  String get deleteAllLimitlessConversations => 'Burahin ang Lahat ng Limitless Conversations?';

  @override
  String get deleteAllLimitlessWarning =>
      'Ito ay permanenteng magbabura ng lahat ng mga pag-uusap na na-import mula sa Limitless. Ang aksyon na ito ay hindi maaaring i-undo.';

  @override
  String deletedLimitlessConversations(int count) {
    return 'Nabura ang $count Limitless conversations';
  }

  @override
  String get failedToDeleteConversations => 'Nabigong burahin ang mga pag-uusap';

  @override
  String get deleteImportedData => 'Burahin ang Imported Data';

  @override
  String get statusPending => 'Pending';

  @override
  String get statusProcessing => 'Processing';

  @override
  String get statusCompleted => 'Completed';

  @override
  String get statusFailed => 'Failed';

  @override
  String nConversations(int count) {
    return '$count conversations';
  }

  @override
  String get pleaseEnterName => 'Mangyaring ipasok ang isang pangalan';

  @override
  String get nameMustBeBetweenCharacters => 'Ang pangalan ay dapat na sa pagitan ng 2 at 40 na characters';

  @override
  String get deleteSampleQuestion => 'Burahin ang Sample?';

  @override
  String deleteSampleConfirmation(String name) {
    return 'Sigurado ka ba na gusto mong burahin ang $name\'s sample?';
  }

  @override
  String get confirmDeletion => 'Kumpirmahin ang Pagbabura';

  @override
  String deletePersonConfirmation(String name) {
    return 'Sigurado ka ba na gusto mong burahin ang $name? Ito rin ay magtatanggal ng lahat ng associated speech samples.';
  }

  @override
  String get howItWorksTitle => 'Paano ito gumagana?';

  @override
  String get howPeopleWorks =>
      'Kapag lumikha ng isang tao, maaari kang pumunta sa isang conversation transcript, at italaan sa kanila ang kanilang corresponding segments, sa ganitong paraan ang Omi ay makakapag-recognize ng kanilang speech din!';

  @override
  String get tapToDelete => 'I-tap upang burahin';

  @override
  String get newTag => 'BAGO';

  @override
  String get needHelpChatWithUs => 'Kailangan ng Tulong? Chat sa amin';

  @override
  String get localStorageEnabled => 'Local storage enabled';

  @override
  String get localStorageDisabled => 'Local storage disabled';

  @override
  String failedToUpdateSettings(String error) {
    return 'Nabigong i-update ang settings: $error';
  }

  @override
  String get privacyNotice => 'Privacy Notice';

  @override
  String get recordingsMayCaptureOthers =>
      'Ang mga recordings ay maaaring kumuha ng ibang mga boses. Tiyakin na mayroon kang pahintulot mula sa lahat ng participants bago paganahin.';

  @override
  String get enable => 'I-enable';

  @override
  String get storeAudioOnPhone => 'Mag-store ng Audio sa Phone';

  @override
  String get on => 'On';

  @override
  String get storeAudioDescription =>
      'Panatilihin ang lahat ng audio recordings na naka-store nang lokal sa iyong phone. Kapag naka-disable, ang mga nabigong uploads lamang ang iniingatan upang makatipid ng storage space.';

  @override
  String get enableLocalStorage => 'I-enable ang Local Storage';

  @override
  String get cloudStorageEnabled => 'Cloud storage enabled';

  @override
  String get cloudStorageDisabled => 'Cloud storage disabled';

  @override
  String get enableCloudStorage => 'I-enable ang Cloud Storage';

  @override
  String get storeAudioOnCloud => 'Mag-store ng Audio sa Cloud';

  @override
  String get cloudStorageDialogMessage =>
      'Ang iyong real-time recordings ay ise-store sa private cloud storage habang nagsasalita ka.';

  @override
  String get storeAudioCloudDescription =>
      'I-store ang iyong real-time recordings sa private cloud storage habang nagsasalita ka. Ang audio ay kina-capture at ina-save nang secure sa real-time.';

  @override
  String get downloadingFirmware => 'Nagda-download ng Firmware';

  @override
  String get installingFirmware => 'Nag-install ng Firmware';

  @override
  String get firmwareUpdateWarning =>
      'Huwag itigil ang app o i-off ang device. Ito ay maaaring magdulot ng damage sa iyong device.';

  @override
  String get firmwareUpdated => 'Firmware Updated';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'Mangyaring i-restart ang iyong $deviceName upang makumpleto ang update.';
  }

  @override
  String get yourDeviceIsUpToDate => 'Ang iyong device ay updated na';

  @override
  String get currentVersion => 'Current Version';

  @override
  String get latestVersion => 'Latest Version';

  @override
  String get whatsNew => 'Ano ang Bago';

  @override
  String get installUpdate => 'I-install ang Update';

  @override
  String get updateNow => 'I-update Ngayon';

  @override
  String get updateGuide => 'Update Guide';

  @override
  String get checkingForUpdates => 'Kumikita para sa Updates';

  @override
  String get checkingFirmwareVersion => 'Kumikita ng firmware version...';

  @override
  String get firmwareUpdate => 'Firmware Update';

  @override
  String get payments => 'Mga Pagbabayad';

  @override
  String get connectPaymentMethodInfo =>
      'Kumonekta sa isang payment method sa ibaba upang magsimulang tumanggap ng payouts para sa iyong apps.';

  @override
  String get selectedPaymentMethod => 'Selected Payment Method';

  @override
  String get availablePaymentMethods => 'Available Payment Methods';

  @override
  String get activeStatus => 'Aktibo';

  @override
  String get connectedStatus => 'Konektado';

  @override
  String get notConnectedStatus => 'Hindi Konektado';

  @override
  String get setActive => 'Itakda bilang Aktibo';

  @override
  String get getPaidThroughStripe => 'Makatanggap ng bayad para sa iyong app sales sa pamamagitan ng Stripe';

  @override
  String get monthlyPayouts => 'Monthly payouts';

  @override
  String get monthlyPayoutsDescription =>
      'Makatanggap ng monthly payments direkta sa iyong account kapag umabot ka na sa \$10 sa earnings';

  @override
  String get secureAndReliable => 'Secure at reliable';

  @override
  String get stripeSecureDescription => 'Sinisiguro ng Stripe ang ligtas at on-time na paglipat ng iyong app revenue';

  @override
  String get selectYourCountry => 'Piliin ang iyong bansa';

  @override
  String get countrySelectionPermanent =>
      'Ang iyong country selection ay permanent at hindi maaaring baguhin sa hinaharap.';

  @override
  String get byClickingConnectNow => 'Sa pamamagitan ng pag-click sa \"Connect Now\" sumasang-ayon ka sa';

  @override
  String get stripeConnectedAccountAgreement => 'Stripe Connected Account Agreement';

  @override
  String get errorConnectingToStripe => 'Error sa pagkonekta sa Stripe! Mangyaring subukan muli nang huli.';

  @override
  String get connectingYourStripeAccount => 'Konektado ang iyong Stripe account';

  @override
  String get stripeOnboardingInstructions =>
      'Mangyaring tapusin ang Stripe onboarding process sa iyong browser. Ang pahina na ito ay awtomatikong mag-update kapag tapos na.';

  @override
  String get failedTryAgain => 'Nabigo? Subukan Muli';

  @override
  String get illDoItLater => 'Gagawin ko ito nang huli';

  @override
  String get successfullyConnected => 'Successfully Connected!';

  @override
  String get stripeReadyForPayments =>
      'Ang iyong Stripe account ay handa na na makatanggap ng payments. Maaari na kang magsimulang kumita mula sa iyong app sales kaagad.';

  @override
  String get updateStripeDetails => 'I-update ang Stripe Details';

  @override
  String get errorUpdatingStripeDetails => 'Error sa pag-update ng Stripe details! Mangyaring subukan muli nang huli.';

  @override
  String get updatePayPal => 'I-update ang PayPal';

  @override
  String get setUpPayPal => 'I-set Up ang PayPal';

  @override
  String get updatePayPalAccountDetails => 'I-update ang iyong PayPal account details';

  @override
  String get connectPayPalToReceivePayments =>
      'Kumonekta sa iyong PayPal account upang magsimulang tumanggap ng payments para sa iyong apps';

  @override
  String get paypalEmail => 'PayPal Email';

  @override
  String get paypalMeLink => 'PayPal.me Link';

  @override
  String get stripeRecommendation =>
      'Kung ang Stripe ay available sa iyong bansa, lubos naming inirekomenda ang paggamit nito para sa mas mabilis at mas madaling payouts.';

  @override
  String get updatePayPalDetails => 'I-update ang PayPal Details';

  @override
  String get savePayPalDetails => 'I-save ang PayPal Details';

  @override
  String get pleaseEnterPayPalEmail => 'Mangyaring ipasok ang iyong PayPal email';

  @override
  String get pleaseEnterPayPalMeLink => 'Mangyaring ipasok ang iyong PayPal.me link';

  @override
  String get doNotIncludeHttpInLink => 'Huwag isama ang http o https o www sa link';

  @override
  String get pleaseEnterValidPayPalMeLink => 'Mangyaring ipasok ang isang valid PayPal.me link';

  @override
  String get pleaseEnterValidEmail => 'Mangyaring ipasok ang isang valid email address';

  @override
  String get syncingYourRecordings => 'Nagsi-sync ng iyong mga recordings';

  @override
  String get syncYourRecordings => 'I-sync ang iyong mga recordings';

  @override
  String get syncNow => 'I-sync Ngayon';

  @override
  String get error => 'Error';

  @override
  String get speechSamples => 'Speech Samples';

  @override
  String additionalSampleIndex(String index) {
    return 'Additional Sample $index';
  }

  @override
  String durationSeconds(String seconds) {
    return 'Duration: $seconds seconds';
  }

  @override
  String get additionalSpeechSampleRemoved => 'Additional Speech Sample Removed';

  @override
  String get consentDataMessage =>
      'Sa pagpapatuloy, ang iyong mga pag-uusap, recording, at personal na impormasyon ay ligtas na maiimbak sa aming mga server. Ang iyong mga audio recording at transcript ay pinoproseso ng third-party na mga serbisyo ng AI (kabilang ang Deepgram para sa transcription at OpenAI para sa analysis) upang mabigyan ka ng AI-powered na mga insight at ma-enable ang lahat ng feature ng app.';

  @override
  String get tasksEmptyStateMessage =>
      'Ang mga tasks mula sa iyong mga pag-uusap ay lilitaw dito.\\nI-tap ang + upang lumikha ng isa nang manual.';

  @override
  String get clearChatAction => 'Burahin ang Chat';

  @override
  String get enableApps => 'I-enable ang Apps';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => 'magpakita ng higit pa ↓';

  @override
  String get showLess => 'magpakita ng mas kaunti ↑';

  @override
  String get loadingYourRecording => 'Nag-load ng iyong recording...';

  @override
  String get photoDiscardedMessage => 'Ang photo na ito ay iniwan dahil hindi ito significant.';

  @override
  String get analyzing => 'Nag-analyze...';

  @override
  String get searchCountries => 'Maghanap ng mga bansa';

  @override
  String get checkingAppleWatch => 'Kumikita ng Apple Watch...';

  @override
  String get installOmiOnAppleWatch => 'I-install ang Omi sa iyong\\nApple Watch';

  @override
  String get installOmiOnAppleWatchDescription =>
      'Upang gamitin ang iyong Apple Watch kasama ang Omi, kailangan mo munang i-install ang Omi app sa iyong watch.';

  @override
  String get openOmiOnAppleWatch => 'Buksan ang Omi sa iyong\\nApple Watch';

  @override
  String get openOmiOnAppleWatchDescription =>
      'Ang Omi app ay naka-install na sa iyong Apple Watch. Buksan ito at i-tap ang Start upang magsimula.';

  @override
  String get openWatchApp => 'Buksan ang Watch App';

  @override
  String get iveInstalledAndOpenedTheApp => 'Nag-install na ako at Binuksan ang App';

  @override
  String get unableToOpenWatchApp =>
      'Hindi maaaring buksan ang Apple Watch app. Mangyaring manu-manong buksan ang Watch app sa iyong Apple Watch at i-install ang Omi mula sa \"Available Apps\" section.';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch ay matagumpay na konektado!';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch ay hindi pa rin reachable. Mangyaring tiyakin na ang Omi app ay bukas sa iyong watch.';

  @override
  String errorCheckingConnection(String error) {
    return 'Error sa pagsusuri ng koneksyon: $error';
  }

  @override
  String get muted => 'Muted';

  @override
  String get processNow => 'I-process Ngayon';

  @override
  String get finishedConversation => 'Natapos ang Conversation?';

  @override
  String get stopRecordingConfirmation =>
      'Sigurado ka ba na gusto mong ihinto ang pag-record at i-summarize ang pag-uusap ngayon?';

  @override
  String get conversationEndsManually => 'Ang pag-uusap ay magtatapos lamang nang manual.';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'Ang pag-uusap ay na-summarize pagkatapos ng $minutes minute$suffix na walang pagsasalita.';
  }

  @override
  String get dontAskAgain => 'Huwag na itanong muli';

  @override
  String get waitingForTranscriptOrPhotos => 'Naghihintay para sa transcript o mga photo...';

  @override
  String get noSummaryYet => 'Walang summary pa';

  @override
  String hints(String text) {
    return 'Hints: $text';
  }

  @override
  String get testConversationPrompt => 'Subukin ang Conversation Prompt';

  @override
  String get prompt => 'Prompt';

  @override
  String get result => 'Result:';

  @override
  String get compareTranscripts => 'Ihambing ang Mga Transcript';

  @override
  String get notHelpful => 'Hindi Nakatulong';

  @override
  String get exportTasksWithOneTap => 'I-export ang mga tasks sa isang tap!';

  @override
  String get inProgress => 'Sa progreso';

  @override
  String get photos => 'Mga Photos';

  @override
  String get rawData => 'Raw Data';

  @override
  String get content => 'Content';

  @override
  String get noContentToDisplay => 'Walang content na ipapakita';

  @override
  String get noSummary => 'Walang summary';

  @override
  String get updateOmiFirmware => 'I-update ang omi firmware';

  @override
  String get anErrorOccurredTryAgain => 'Isang error ang nangyari. Mangyaring subukan ulit.';

  @override
  String get welcomeBackSimple => 'Maligayang pabalik';

  @override
  String get addVocabularyDescription =>
      'Magdagdag ng mga salita na dapat tanggapin ng Omi sa panahon ng transcription.';

  @override
  String get enterWordsCommaSeparated => 'Ipasok ang mga salita (comma separated)';

  @override
  String get whenToReceiveDailySummary => 'Kailan makakatanggap ng iyong daily summary';

  @override
  String get checkingNextSevenDays => 'Kumikita ng susunod na 7 araw';

  @override
  String failedToDeleteError(String error) {
    return 'Nabigong burahin: $error';
  }

  @override
  String get developerApiKeys => 'Developer API Keys';

  @override
  String get noApiKeysCreateOne => 'Walang API keys. Lumikha ng isa upang magsimula.';

  @override
  String get commandRequired => '⌘ required';

  @override
  String get spaceKey => 'Space';

  @override
  String loadMoreRemaining(String count) {
    return 'Mag-load ng Higit Pa ($count remaining)';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'Top $percentile% User';
  }

  @override
  String get wrappedMinutes => 'minutes';

  @override
  String get wrappedConversations => 'conversations';

  @override
  String get wrappedDaysActive => 'days active';

  @override
  String get wrappedYouTalkedAbout => 'Nagsalita Ka Tungkol sa';

  @override
  String get wrappedActionItems => 'Action Items';

  @override
  String get wrappedTasksCreated => 'tasks created';

  @override
  String get wrappedCompleted => 'completed';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% completion rate';
  }

  @override
  String get wrappedYourTopDays => 'Ang Iyong Top Days';

  @override
  String get wrappedBestMoments => 'Best Moments';

  @override
  String get wrappedMyBuddies => 'Ang Aking mga Kaibigan';

  @override
  String get wrappedCouldntStopTalkingAbout => 'Hindi Maaaring Tumigil na Nagsasalita Tungkol sa';

  @override
  String get wrappedShow => 'SHOW';

  @override
  String get wrappedMovie => 'MOVIE';

  @override
  String get wrappedBook => 'BOOK';

  @override
  String get wrappedCelebrity => 'CELEBRITY';

  @override
  String get wrappedFood => 'FOOD';

  @override
  String get wrappedMovieRecs => 'Movie Recs Para sa mga Kaibigan';

  @override
  String get wrappedBiggest => 'Pinakamalaki';

  @override
  String get wrappedStruggle => 'Pagsubok';

  @override
  String get wrappedButYouPushedThrough => 'Pero ikaw ay nag-push through 💪';

  @override
  String get wrappedWin => 'Tagumpay';

  @override
  String get wrappedYouDidIt => 'Ginawa mo ito! 🎉';

  @override
  String get wrappedTopPhrases => 'Top 5 Phrases';

  @override
  String get wrappedMins => 'mins';

  @override
  String get wrappedConvos => 'convos';

  @override
  String get wrappedDays => 'days';

  @override
  String get wrappedMyBuddiesLabel => 'ANG AKING MGA KAIBIGAN';

  @override
  String get wrappedObsessionsLabel => 'OBSESSIONS';

  @override
  String get wrappedStruggleLabel => 'PAGSUBOK';

  @override
  String get wrappedWinLabel => 'TAGUMPAY';

  @override
  String get wrappedTopPhrasesLabel => 'TOP PHRASES';

  @override
  String get wrappedLetsHitRewind => 'Bumalik tayo sa iyong';

  @override
  String get wrappedGenerateMyWrapped => 'Lumikha ng Aking Wrapped';

  @override
  String get wrappedProcessingDefault => 'Processing...';

  @override
  String get wrappedCreatingYourStory => 'Lumilikha ng iyong\\n2025 story...';

  @override
  String get wrappedSomethingWentWrong => 'Isang bagay\\nay nagkamali';

  @override
  String get wrappedAnErrorOccurred => 'Isang error ang nangyari';

  @override
  String get wrappedTryAgain => 'Subukan Muli';

  @override
  String get wrappedNoDataAvailable => 'Walang data available';

  @override
  String get wrappedOmiLifeRecap => 'Omi Life Recap';

  @override
  String get wrappedSwipeUpToBegin => 'Mag-swipe up upang magsimula';

  @override
  String get wrappedShareText => 'Ang aking 2025, naalaala ng Omi ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare => 'Nabigong ibahagi. Mangyaring subukan ulit.';

  @override
  String get wrappedFailedToStartGeneration => 'Nabigong magsimula ng generation. Mangyaring subukan ulit.';

  @override
  String get wrappedStarting => 'Nagsisimula...';

  @override
  String get wrappedShare => 'Ibahagi';

  @override
  String get wrappedShareYourWrapped => 'Ibahagi ang Iyong Wrapped';

  @override
  String get wrappedMy2025 => 'Ang Aking 2025';

  @override
  String get wrappedRememberedByOmi => 'naalaala ng Omi';

  @override
  String get wrappedMostFunDay => 'Pinakamasaya';

  @override
  String get wrappedMostProductiveDay => 'Pinakaproductive';

  @override
  String get wrappedMostIntenseDay => 'Pinakapalakas';

  @override
  String get wrappedFunniestMoment => 'Pinakamasaya';

  @override
  String get wrappedMostCringeMoment => 'Pinakacringe';

  @override
  String get wrappedMinutesLabel => 'minutes';

  @override
  String get wrappedConversationsLabel => 'conversations';

  @override
  String get wrappedDaysActiveLabel => 'days active';

  @override
  String get wrappedTasksGenerated => 'tasks generated';

  @override
  String get wrappedTasksCompleted => 'tasks completed';

  @override
  String get wrappedTopFivePhrases => 'Top 5 Phrases';

  @override
  String get wrappedAGreatDay => 'Isang Magandang Araw';

  @override
  String get wrappedGettingItDone => 'Nakakagawa ng Trabaho';

  @override
  String get wrappedAChallenge => 'Isang Hamon';

  @override
  String get wrappedAHilariousMoment => 'Isang Masayang Sandali';

  @override
  String get wrappedThatAwkwardMoment => 'Ang Awkward na Sandaling Iyon';

  @override
  String get wrappedYouHadFunnyMoments => 'Mayroon kang ilang nakakatuwa na sandali ngayong taon!';

  @override
  String get wrappedWeveAllBeenThere => 'Lahat tayo ay nandoon!';

  @override
  String get wrappedFriend => 'Kaibigan';

  @override
  String get wrappedYourBuddy => 'Ang iyong kaibigan!';

  @override
  String get wrappedNotMentioned => 'Hindi nabanggit';

  @override
  String get wrappedTheHardPart => 'Ang Mahirap na Bahagi';

  @override
  String get wrappedPersonalGrowth => 'Personal Growth';

  @override
  String get wrappedFunDay => 'Masaya';

  @override
  String get wrappedProductiveDay => 'Produktibo';

  @override
  String get wrappedIntenseDay => 'Malakas';

  @override
  String get wrappedFunnyMomentTitle => 'Masayang Sandali';

  @override
  String get wrappedCringeMomentTitle => 'Cringe Moment';

  @override
  String get wrappedYouTalkedAboutBadge => 'Nagsalita Ka Tungkol sa';

  @override
  String get wrappedCompletedLabel => 'Tapusin';

  @override
  String get wrappedMyBuddiesCard => 'Ang Aking mga Kaibigan';

  @override
  String get wrappedBuddiesLabel => 'MGA KAIBIGAN';

  @override
  String get wrappedObsessionsLabelUpper => 'OBSESSIONS';

  @override
  String get wrappedStruggleLabelUpper => 'PAGSUBOK';

  @override
  String get wrappedWinLabelUpper => 'TAGUMPAY';

  @override
  String get wrappedTopPhrasesLabelUpper => 'TOP PHRASES';

  @override
  String get wrappedYourHeader => 'Ang Iyong';

  @override
  String get wrappedTopDaysHeader => 'Top Days';

  @override
  String get wrappedYourTopDaysBadge => 'Ang Iyong Top Days';

  @override
  String get wrappedBestHeader => 'Pinakamahusay';

  @override
  String get wrappedMomentsHeader => 'Sandali';

  @override
  String get wrappedBestMomentsBadge => 'Best Moments';

  @override
  String get wrappedBiggestHeader => 'Pinakamalaki';

  @override
  String get wrappedStruggleHeader => 'Pagsubok';

  @override
  String get wrappedWinHeader => 'Tagumpay';

  @override
  String get wrappedButYouPushedThroughEmoji => 'Pero ikaw ay nag-push through 💪';

  @override
  String get wrappedYouDidItEmoji => 'Ginawa mo ito! 🎉';

  @override
  String get wrappedHours => 'hours';

  @override
  String get wrappedActions => 'actions';

  @override
  String get multipleSpeakersDetected => 'Ang maraming mga nagsasalita ay nahanap';

  @override
  String get multipleSpeakersDescription =>
      'Mukhang mayroon kang maraming mga nagsasalita sa recording. Mangyaring tiyakin na nasa quiet location ka at subukan ulit.';

  @override
  String get invalidRecordingDetected => 'Ang invalid recording ay nahanap';

  @override
  String get notEnoughSpeechDescription =>
      'Walang sapat na pagsasalita na nahanap. Mangyaring magsalita ng higit pa at subukan ulit.';

  @override
  String get speechDurationDescription =>
      'Siguraduhin na nagsasalita ka ng hindi bababa sa 5 segundo at hindi higit sa 90.';

  @override
  String get connectionLostDescription =>
      'Ang koneksyon ay nawasak. Pakisuri ang iyong internet na koneksyon at subukan ulit.';

  @override
  String get howToTakeGoodSample => 'Paano gumawa ng magandang sample?';

  @override
  String get goodSampleInstructions =>
      '1. Siguraduhin na nasa matuling lugar ka.\n2. Magsalita ng malinaw at natural.\n3. Siguraduhin na ang iyong device ay nasa natural na posisyon, sa iyong leeg.\n\nKapag nagawa na, maaari mong palaging mapabuti ito o gawin itong muli.';

  @override
  String get noDeviceConnectedUseMic => 'Walang konektadong device. Gagamitin ang mikropono ng telepono.';

  @override
  String get doItAgain => 'Gawin itong muli';

  @override
  String get listenToSpeechProfile => 'Pakinggan ang aking speech profile ➡️';

  @override
  String get recognizingOthers => 'Kinikilala ang iba 👀';

  @override
  String get keepGoingGreat => 'Magpatuloy, maganda ang iyong ginagawa';

  @override
  String get somethingWentWrongTryAgain => 'May problema! Subukan ulit mamaya.';

  @override
  String get uploadingVoiceProfile => 'Ina-upload ang iyong voice profile....';

  @override
  String get memorizingYourVoice => 'Natatandaan ang iyong boses...';

  @override
  String get personalizingExperience => 'Personalisasyon ng iyong karanasan...';

  @override
  String get keepSpeakingUntil100 => 'Magpatuloy na magsalita hanggang 100%.';

  @override
  String get greatJobAlmostThere => 'Napakaganda, malapit ka na';

  @override
  String get soCloseJustLittleMore => 'Napakalapit, kailangan lang ng konti pa';

  @override
  String get notificationFrequency => 'Dalas ng Mga Notipikasyon';

  @override
  String get controlNotificationFrequency =>
      'Kontrolin kung gaano kadalas ang Omi na magpadala sa iyo ng proactive na mga notipikasyon.';

  @override
  String get yourScore => 'Iyong marka';

  @override
  String get dailyScoreBreakdown => 'Araw-araw na Breakdown ng Marka';

  @override
  String get todaysScore => 'Ang Marka ng Ngayon';

  @override
  String get tasksCompleted => 'Tapos na Mga Gawain';

  @override
  String get completionRate => 'Completion Rate';

  @override
  String get howItWorks => 'Paano ito gumagana';

  @override
  String get dailyScoreExplanation =>
      'Ang iyong pang-araw-araw na marka ay batay sa pagkakatapos ng gawain. Tapusin ang iyong mga gawain upang mapabuti ang iyong marka!';

  @override
  String get notificationFrequencyDescription =>
      'Kontrolin kung gaano kadalas ang Omi na magpadala sa iyo ng proactive na mga notipikasyon at mga reminder.';

  @override
  String get sliderOff => 'I-off';

  @override
  String get sliderMax => 'Max';

  @override
  String summaryGeneratedFor(String date) {
    return 'Summary na nabuo para sa $date';
  }

  @override
  String get failedToGenerateSummary =>
      'Hindi na-generate ang summary. Siguraduhin na mayroon kang mga pag-usap para sa araw na iyon.';

  @override
  String get recap => 'Recap';

  @override
  String deleteQuoted(String name) {
    return 'Tanggalin ang \"$name\"';
  }

  @override
  String moveConversationsTo(int count) {
    return 'Ilipat ang $count mga pag-usap sa:';
  }

  @override
  String get noFolder => 'Walang Folder';

  @override
  String get removeFromAllFolders => 'Alisin mula sa lahat ng mga folder';

  @override
  String get buildAndShareYourCustomApp => 'Bumuo at ibahagi ang iyong custom na app';

  @override
  String get searchAppsPlaceholder => 'Maghanap ng 1500+ Apps';

  @override
  String get filters => 'Mga Filter';

  @override
  String get frequencyOff => 'I-off';

  @override
  String get frequencyMinimal => 'Minimal';

  @override
  String get frequencyLow => 'Mababa';

  @override
  String get frequencyBalanced => 'Balansado';

  @override
  String get frequencyHigh => 'Mataas';

  @override
  String get frequencyMaximum => 'Maximum';

  @override
  String get frequencyDescOff => 'Walang proactive na mga notipikasyon';

  @override
  String get frequencyDescMinimal => 'Kritikal lamang na mga reminder';

  @override
  String get frequencyDescLow => 'Mahalagang update lamang';

  @override
  String get frequencyDescBalanced => 'Regular na nakakatulong na empuye';

  @override
  String get frequencyDescHigh => 'Madalas na check-in';

  @override
  String get frequencyDescMaximum => 'Manatiling patuloy na engaged';

  @override
  String get clearChatQuestion => 'Linasin ang Chat?';

  @override
  String get syncingMessages => 'Sine-sync ang mga mensahe sa server...';

  @override
  String get chatAppsTitle => 'Chat Apps';

  @override
  String get selectApp => 'Pumili ng App';

  @override
  String get noChatAppsEnabled =>
      'Walang naka-enable na chat apps.\nI-tap ang \"Enable Apps\" upang magdagdag ng ilan.';

  @override
  String get disable => 'I-disable';

  @override
  String get photoLibrary => 'Photo Library';

  @override
  String get chooseFile => 'Pumili ng File';

  @override
  String get connectAiAssistantsToYourData => 'Ikonekta ang AI assistants sa iyong data';

  @override
  String get oAuth => 'OAuth';

  @override
  String get trackYourGoalsOnHomepage => 'Subaybayan ang iyong personal na mga layunin sa homepage';

  @override
  String get deleteRecording => 'Tanggalin ang Recording';

  @override
  String get thisCannotBeUndone => 'Hindi ito maaaring bawiin.';

  @override
  String get sdCard => 'SD Card';

  @override
  String get fromSd => 'Mula sa SD';

  @override
  String get limitless => 'Limitless';

  @override
  String get fastTransfer => 'Fast Transfer';

  @override
  String get syncingStatus => 'Sine-sync';

  @override
  String get failedStatus => 'Nabigo';

  @override
  String etaLabel(String time) {
    return 'ETA: $time';
  }

  @override
  String get transferMethod => 'Transfer Method';

  @override
  String get fast => 'Mabilis';

  @override
  String get ble => 'BLE';

  @override
  String get phone => 'Telepono';

  @override
  String get cancelSync => 'Kanselahin ang Sync';

  @override
  String get cancelSyncMessage => 'Ang data na nai-download na ay ise-save. Maaari mong muling simulan mamaya.';

  @override
  String get syncCancelled => 'Ang sync ay kinansela';

  @override
  String get deleteProcessedFiles => 'Tanggalin ang Naprosesong Mga File';

  @override
  String get processedFilesDeleted => 'Naprosesong mga file ay natanggal';

  @override
  String get wifiEnableFailed => 'Nabigo ang pagpapagana ng WiFi sa device. Subukan ulit.';

  @override
  String get deviceNoFastTransfer =>
      'Ang iyong device ay hindi sumusuporta sa Fast Transfer. Gumamit ng Bluetooth sa halip.';

  @override
  String get enableHotspotMessage => 'Pakipagana ang hotspot ng iyong telepono at subukan ulit.';

  @override
  String get transferStartFailed => 'Nabigo ang pagsisimula ng transfer. Subukan ulit.';

  @override
  String get deviceNotResponding => 'Ang device ay hindi tumugon. Subukan ulit.';

  @override
  String get invalidWifiCredentials => 'Invalid na WiFi credentials. Suriin ang iyong hotspot settings.';

  @override
  String get wifiConnectionFailed => 'Nabigo ang WiFi connection. Subukan ulit.';

  @override
  String get sdCardProcessing => 'SD Card Processing';

  @override
  String sdCardProcessingMessage(int count) {
    return 'Pinoproseso ang $count recording(s). Ang mga file ay mawawalan mula sa SD card pagkatapos.';
  }

  @override
  String get process => 'Proseso';

  @override
  String get wifiSyncFailed => 'Nabigo ang WiFi Sync';

  @override
  String get processingFailed => 'Nabigo ang Pagpoproseso';

  @override
  String get downloadingFromSdCard => 'Dine-download mula sa SD Card';

  @override
  String processingProgress(int current, int total) {
    return 'Pinoproseso ang $current/$total';
  }

  @override
  String conversationsCreated(int count) {
    return '$count mga pag-usap na nabuo';
  }

  @override
  String get internetRequired => 'Internet na kailangan';

  @override
  String get processAudio => 'Proseso ang Audio';

  @override
  String get start => 'Magsimula';

  @override
  String get noRecordings => 'Walang Mga Recording';

  @override
  String get audioFromOmiWillAppearHere => 'Ang tunog mula sa iyong Omi device ay lilitaw dito';

  @override
  String get deleteProcessed => 'Tanggalin ang Naproseso';

  @override
  String get tryDifferentFilter => 'Subukan ang ibang filter';

  @override
  String get recordings => 'Mga Recording';

  @override
  String get enableRemindersAccess => 'Pakipagana ang Reminders access sa Settings upang gamitin ang Apple Reminders';

  @override
  String todayAtTime(String time) {
    return 'Ngayong araw sa $time';
  }

  @override
  String yesterdayAtTime(String time) {
    return 'Kahapon sa $time';
  }

  @override
  String get lessThanAMinute => 'Mas mababa sa isang minuto';

  @override
  String estimatedMinutes(int count) {
    return '~$count minuto(s)';
  }

  @override
  String estimatedHours(int count) {
    return '~$count oras(oras)';
  }

  @override
  String estimatedTimeRemaining(String time) {
    return 'Estimated: $time na nananatili';
  }

  @override
  String get summarizingConversation => 'Sine-summarize ang pag-usap...\nIto ay maaaring tumagal ng ilang segundo';

  @override
  String get resummarizingConversation => 'Re-summarizing ang pag-usap...\nIto ay maaaring tumagal ng ilang segundo';

  @override
  String get nothingInterestingRetry => 'Walang nahanap na interesante,\ngusto mo bang subukan ulit?';

  @override
  String get noSummaryForConversation => 'Walang available na summary\npara sa pag-usapang ito.';

  @override
  String get unknownLocation => 'Hindi kilalang lokasyon';

  @override
  String get couldNotLoadMap => 'Hindi ma-load ang mapa';

  @override
  String get triggerConversationIntegration => 'I-trigger ang Conversation Created Integration';

  @override
  String get webhookUrlNotSet => 'Webhook URL ay hindi nakatakda';

  @override
  String get setWebhookUrlInSettings =>
      'Pakisiguro ang webhook URL sa developer settings upang gamitin ang feature na ito.';

  @override
  String get sendWebUrl => 'Magpadala ng web url';

  @override
  String get sendTranscript => 'Magpadala ng Transcript';

  @override
  String get sendSummary => 'Magpadala ng Summary';

  @override
  String get debugModeDetected => 'Debug Mode Detected';

  @override
  String get performanceReduced => 'Nabawasan ang performance ng 5-10x. Gamitin ang Release mode.';

  @override
  String autoClosingInSeconds(int seconds) {
    return 'Awtomatikong pagsasara sa ${seconds}s';
  }

  @override
  String get modelRequired => 'Model na Kailangan';

  @override
  String get downloadWhisperModel => 'Pakidownload ang Whisper model bago i-save.';

  @override
  String get deviceNotCompatible => 'Device Not Compatible';

  @override
  String get deviceRequirements =>
      'Ang iyong device ay hindi nakakatugon sa mga kinakailangan para sa On-Device transcription.';

  @override
  String get willLikelyCrash => 'Ang pagpapagana nito ay malamang na magdudulot ng pag-crash o pag-freeze sa app.';

  @override
  String get transcriptionSlowerLessAccurate => 'Ang transcription ay magiging mas mabagal at mas hindi tumpak.';

  @override
  String get proceedAnyway => 'Magpatuloy pa rin';

  @override
  String get olderDeviceDetected => 'Matandang Device Detected';

  @override
  String get onDeviceSlower => 'Ang on-device transcription ay maaaring mas mabagal sa device na ito.';

  @override
  String get batteryUsageHigher => 'Ang battery usage ay mas mataas kaysa cloud transcription.';

  @override
  String get considerOmiCloud => 'Isaalang-alang ang paggamit ng Omi Cloud para sa mas magandang performance.';

  @override
  String get highResourceUsage => 'Mataas na Paggamit ng Resource';

  @override
  String get onDeviceIntensive => 'Ang On-Device transcription ay computationally intensive.';

  @override
  String get batteryDrainIncrease => 'Ang battery drain ay tataas ng malaki.';

  @override
  String get deviceMayWarmUp => 'Ang device ay maaaring mag-init sa mahabang paggamit.';

  @override
  String get speedAccuracyLower => 'Ang bilis at katumpakan ay maaaring mas mababa kaysa Cloud models.';

  @override
  String get cloudProvider => 'Cloud Provider';

  @override
  String get premiumMinutesInfo =>
      '1,200 premium na minuto/buwan. Ang On-Device tab ay nag-aalok ng unlimited na libreng transcription.';

  @override
  String get viewUsage => 'Tingnan ang paggamit';

  @override
  String get localProcessingInfo =>
      'Ang audio ay napoproseso nang lokal. Gumagana nang offline, mas pribado, ngunit gumagamit ng mas maraming battery.';

  @override
  String get model => 'Model';

  @override
  String get performanceWarning => 'Performance Warning';

  @override
  String get largeModelWarning =>
      'Ang model na ito ay malaki at maaaring mag-crash sa app o tumatakbo ng napakabagal sa mobile devices.\n\n\"small\" o \"base\" ang inirerekomenda.';

  @override
  String get usingNativeIosSpeech => 'Gumagamit ng Native iOS Speech Recognition';

  @override
  String get noModelDownloadRequired =>
      'Ang native speech engine ng iyong device ay gagamitin. Walang model download na kailangan.';

  @override
  String get modelReady => 'Model Ready';

  @override
  String get redownload => 'I-download ulit';

  @override
  String get doNotCloseApp => 'Pakihuwag isara ang app.';

  @override
  String get downloading => 'Dine-download...';

  @override
  String get downloadModel => 'Download Model';

  @override
  String estimatedSize(String size) {
    return 'Estimated Size: ~$size MB';
  }

  @override
  String availableSpace(String space) {
    return 'Available Space: $space';
  }

  @override
  String get notEnoughSpace => 'Warning: Walang sapat na space!';

  @override
  String get download => 'I-download';

  @override
  String downloadError(String error) {
    return 'Download error: $error';
  }

  @override
  String get cancelled => 'Kinansela';

  @override
  String get deviceNotCompatibleTitle => 'Device Not Compatible';

  @override
  String get deviceNotMeetRequirements =>
      'Ang iyong device ay hindi nakakatugon sa mga kinakailangan para sa On-Device transcription.';

  @override
  String get transcriptionSlowerOnDevice => 'Ang on-device transcription ay maaaring mas mabagal sa device na ito.';

  @override
  String get computationallyIntensive => 'Ang On-Device transcription ay computationally intensive.';

  @override
  String get batteryDrainSignificantly => 'Ang battery drain ay tataas ng malaki.';

  @override
  String get premiumMinutesMonth =>
      '1,200 premium na minuto/buwan. Ang On-Device tab ay nag-aalok ng unlimited na libreng transcription. ';

  @override
  String get audioProcessedLocally =>
      'Ang audio ay napoproseso nang lokal. Gumagana nang offline, mas pribado, ngunit gumagamit ng mas maraming battery.';

  @override
  String get languageLabel => 'Wika';

  @override
  String get modelLabel => 'Model';

  @override
  String get modelTooLargeWarning =>
      'Ang model na ito ay malaki at maaaring mag-crash sa app o tumatakbo ng napakabagal sa mobile devices.\n\n\"small\" o \"base\" ang inirerekomenda.';

  @override
  String get nativeEngineNoDownload =>
      'Ang native speech engine ng iyong device ay gagamitin. Walang model download na kailangan.';

  @override
  String modelReadyWithName(String model) {
    return 'Model Ready ($model)';
  }

  @override
  String get reDownload => 'I-download ulit';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return 'Dine-download ang $model: $received / $total MB';
  }

  @override
  String preparingModel(String model) {
    return 'Hinihanda ang $model...';
  }

  @override
  String downloadErrorWithMessage(String error) {
    return 'Download error: $error';
  }

  @override
  String estimatedSizeWithValue(String size) {
    return 'Estimated Size: ~$size MB';
  }

  @override
  String availableSpaceWithValue(String space) {
    return 'Available Space: $space';
  }

  @override
  String get omiTranscriptionOptimized =>
      'Ang built-in live transcription ng Omi ay na-optimize para sa real-time na pag-usap na may automatic speaker detection at diarization.';

  @override
  String get reset => 'I-reset';

  @override
  String get useTemplateFrom => 'Gamitin ang template mula sa';

  @override
  String get selectProviderTemplate => 'Pumili ng provider template...';

  @override
  String get quicklyPopulateResponse => 'Mabilis na puno ang kilalang response format ng provider';

  @override
  String get quicklyPopulateRequest => 'Mabilis na puno ang kilalang request format ng provider';

  @override
  String get invalidJsonError => 'Invalid JSON';

  @override
  String downloadModelWithName(String model) {
    return 'Download Model ($model)';
  }

  @override
  String modelNameWithFile(String model) {
    return 'Model: $model';
  }

  @override
  String get device => 'Device';

  @override
  String get chatAssistantsTitle => 'Chat Assistants';

  @override
  String get permissionReadConversations => 'Basahin ang Mga Pag-usap';

  @override
  String get permissionReadMemories => 'Basahin ang Mga Alaala';

  @override
  String get permissionReadTasks => 'Basahin ang Mga Gawain';

  @override
  String get permissionCreateConversations => 'Lumikha ng Mga Pag-usap';

  @override
  String get permissionCreateMemories => 'Lumikha ng Mga Alaala';

  @override
  String get permissionTypeAccess => 'Access';

  @override
  String get permissionTypeCreate => 'Lumikha';

  @override
  String get permissionTypeTrigger => 'Trigger';

  @override
  String get permissionDescReadConversations => 'Ang app na ito ay maaaring mag-access sa iyong mga pag-usap.';

  @override
  String get permissionDescReadMemories => 'Ang app na ito ay maaaring mag-access sa iyong mga alaala.';

  @override
  String get permissionDescReadTasks => 'Ang app na ito ay maaaring mag-access sa iyong mga gawain.';

  @override
  String get permissionDescCreateConversations => 'Ang app na ito ay maaaring lumikha ng mga bagong pag-usap.';

  @override
  String get permissionDescCreateMemories => 'Ang app na ito ay maaaring lumikha ng mga bagong alaala.';

  @override
  String get realtimeListening => 'Realtime Listening';

  @override
  String get setupCompleted => 'Nakumpleto';

  @override
  String get pleaseSelectRating => 'Piliin ang rating';

  @override
  String get writeReviewOptional => 'Magsulat ng review (opsyonal)';

  @override
  String get setupQuestionsIntro =>
      'Tulungan kaming mapabuti ang Omi sa pamamagitan ng pagsagot sa ilang mga tanong.  🫶 💜';

  @override
  String get setupQuestionProfession => '1. Ano ang iyong ginagawa?';

  @override
  String get setupQuestionUsage => '2. Saan mo plano na gamitin ang iyong Omi?';

  @override
  String get setupQuestionAge => '3. Ano ang iyong age range?';

  @override
  String get setupAnswerAllQuestions => 'Hindi mo pa sinasagot ang lahat ng mga tanong! 🥺';

  @override
  String get setupSkipHelp => 'Skip, ayaw kong tumulong :C';

  @override
  String get professionEntrepreneur => 'Entrepreneur';

  @override
  String get professionSoftwareEngineer => 'Software Engineer';

  @override
  String get professionProductManager => 'Product Manager';

  @override
  String get professionExecutive => 'Executive';

  @override
  String get professionSales => 'Sales';

  @override
  String get professionStudent => 'Student';

  @override
  String get usageAtWork => 'Sa trabaho';

  @override
  String get usageIrlEvents => 'IRL Events';

  @override
  String get usageOnline => 'Online';

  @override
  String get usageSocialSettings => 'Sa Social Settings';

  @override
  String get usageEverywhere => 'Kahit saan';

  @override
  String get customBackendUrlTitle => 'Custom Backend URL';

  @override
  String get backendUrlLabel => 'Backend URL';

  @override
  String get saveUrlButton => 'I-save ang URL';

  @override
  String get enterBackendUrlError => 'Pakilagay ang backend URL';

  @override
  String get urlMustEndWithSlashError => 'Ang URL ay dapat magtapos ng \"/\"';

  @override
  String get invalidUrlError => 'Pakilagay ang valid URL';

  @override
  String get backendUrlSavedSuccess => 'Ang backend URL ay successfully na na-save!';

  @override
  String get signInTitle => 'Sign In';

  @override
  String get signInButton => 'Sign In';

  @override
  String get enterEmailError => 'Pakilagay ang iyong email';

  @override
  String get invalidEmailError => 'Pakilagay ang valid email';

  @override
  String get enterPasswordError => 'Pakilagay ang iyong password';

  @override
  String get passwordMinLengthError => 'Ang password ay dapat na hindi bababa sa 8 na character';

  @override
  String get signInSuccess => 'Successful na Sign In!';

  @override
  String get alreadyHaveAccountLogin => 'Mayroon na bang account? Log In';

  @override
  String get emailLabel => 'Email';

  @override
  String get passwordLabel => 'Password';

  @override
  String get createAccountTitle => 'Lumikha ng Account';

  @override
  String get nameLabel => 'Pangalan';

  @override
  String get repeatPasswordLabel => 'Ulitin ang Password';

  @override
  String get signUpButton => 'Sign Up';

  @override
  String get enterNameError => 'Pakilagay ang iyong pangalan';

  @override
  String get passwordsDoNotMatch => 'Ang mga password ay hindi tugma';

  @override
  String get signUpSuccess => 'Successful na Signup!';

  @override
  String get loadingKnowledgeGraph => 'Kina-load ang Knowledge Graph...';

  @override
  String get noKnowledgeGraphYet => 'Walang knowledge graph pa';

  @override
  String get buildingKnowledgeGraphFromMemories => 'Binubuo ang iyong knowledge graph mula sa mga alaala...';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'Ang iyong knowledge graph ay awtomatikong bubuo habang lumilikha ka ng mga bagong alaala.';

  @override
  String get buildGraphButton => 'Bumuo ng Graph';

  @override
  String get checkOutMyMemoryGraph => 'Tingnan ang aking memory graph!';

  @override
  String get getButton => 'Kunin';

  @override
  String openingApp(String appName) {
    return 'Binubuksan ang $appName...';
  }

  @override
  String get writeSomething => 'Magsulat ng isang bagay';

  @override
  String get submitReply => 'Ipadala ang Reply';

  @override
  String get editYourReply => 'I-edit ang Iyong Reply';

  @override
  String get replyToReview => 'Sumagot sa Review';

  @override
  String get rateAndReviewThisApp => 'I-rate at Bisitahin ang App na Ito';

  @override
  String get noChangesInReview => 'Walang pagbabago sa review upang i-update.';

  @override
  String get cantRateWithoutInternet => 'Hindi maaaring i-rate ang app nang walang internet connection.';

  @override
  String get appAnalytics => 'App Analytics';

  @override
  String get learnMoreLink => 'matuto ng higit pa';

  @override
  String get moneyEarned => 'Pera na Kinita';

  @override
  String get writeYourReply => 'Isulat ang iyong reply...';

  @override
  String get replySentSuccessfully => 'Ang reply ay successfully na ipinadala';

  @override
  String failedToSendReply(String error) {
    return 'Nabigo ang pagpapadala ng reply: $error';
  }

  @override
  String get send => 'Ipadala';

  @override
  String starFilter(int count) {
    return '$count Star';
  }

  @override
  String get noReviewsFound => 'Walang Mga Review na Nahanap';

  @override
  String get editReply => 'I-edit ang Reply';

  @override
  String get reply => 'Sumagot';

  @override
  String starFilterLabel(int count) {
    return '$count Star';
  }

  @override
  String get sharePublicLink => 'Ibahagi ang Public Link';

  @override
  String get connectedKnowledgeData => 'Connected Knowledge Data';

  @override
  String get enterName => 'Lagyan ng pangalan';

  @override
  String get goal => 'LAYUNIN';

  @override
  String get tapToTrackThisGoal => 'I-tap upang subaybayan ang layuning ito';

  @override
  String get tapToSetAGoal => 'I-tap upang magtakda ng layunin';

  @override
  String get processedConversations => 'Naprosesong Mga Pag-usap';

  @override
  String get updatedConversations => 'Na-update na Mga Pag-usap';

  @override
  String get newConversations => 'Mga Bagong Pag-usap';

  @override
  String get summaryTemplate => 'Summary Template';

  @override
  String get suggestedTemplates => 'Inaasahang Mga Template';

  @override
  String get otherTemplates => 'Ibang Mga Template';

  @override
  String get availableTemplates => 'Available na Mga Template';

  @override
  String get getCreative => 'Maging Creative';

  @override
  String get defaultLabel => 'Default';

  @override
  String get lastUsedLabel => 'Huling Ginamit';

  @override
  String get setDefaultApp => 'Itakda ang Default App';

  @override
  String setDefaultAppContent(String appName) {
    return 'Itakda ang $appName bilang iyong default na summarization app?\\n\\nAng app na ito ay awtomatikong gagamitin para sa lahat ng susunod na conversation summaries.';
  }

  @override
  String get setDefaultButton => 'Itakda ang Default';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName ay itinakda bilang default na summarization app';
  }

  @override
  String get createCustomTemplate => 'Lumikha ng Custom Template';

  @override
  String get allTemplates => 'Lahat ng Templates';

  @override
  String failedToInstallApp(String appName) {
    return 'Nabigo ang pag-install ng $appName. Subukan ulit.';
  }

  @override
  String errorInstallingApp(String appName, String error) {
    return 'Error sa pag-install ng $appName: $error';
  }

  @override
  String tagSpeaker(int speakerId) {
    return 'I-tag ang Speaker $speakerId';
  }

  @override
  String get personNameAlreadyExists => 'Ang taong may ganitong pangalan ay mayroon na.';

  @override
  String get selectYouFromList => 'Upang i-tag ang iyong sarili, pakipili ang \"You\" mula sa listahan.';

  @override
  String get enterPersonsName => 'Lagyan ng Pangalan ng Tao';

  @override
  String get addPerson => 'Magdagdag ng Tao';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'I-tag ang ibang mga segment mula sa speaker na ito ($selected/$total)';
  }

  @override
  String get tagOtherSegments => 'I-tag ang ibang mga segment';

  @override
  String get managePeople => 'Pamahalaan ang Mga Tao';

  @override
  String get shareViaSms => 'Ibahagi sa pamamagitan ng SMS';

  @override
  String get selectContactsToShareSummary => 'Piliin ang mga contact upang ibahagi ang iyong conversation summary';

  @override
  String get searchContactsHint => 'Maghanap ng mga contact...';

  @override
  String contactsSelectedCount(int count) {
    return '$count napili';
  }

  @override
  String get clearAllSelection => 'Burahin ang lahat';

  @override
  String get selectContactsToShare => 'Pumili ng mga contact upang ibahagi';

  @override
  String shareWithContactCount(int count) {
    return 'Ibahagi sa $count contact';
  }

  @override
  String shareWithContactsCount(int count) {
    return 'Ibahagi sa $count mga contact';
  }

  @override
  String get contactsPermissionRequired => 'Mga permission sa contact na kailangan';

  @override
  String get contactsPermissionRequiredForSms =>
      'Ang mga permission sa contact ay kinakailangan upang ibahagi sa pamamagitan ng SMS';

  @override
  String get grantContactsPermissionForSms => 'Pakigrant ang contacts permission upang ibahagi sa pamamagitan ng SMS';

  @override
  String get noContactsWithPhoneNumbers => 'Walang mga contact na may phone numbers na nahanap';

  @override
  String get noContactsMatchSearch => 'Walang mga contact na tumugma sa iyong search';

  @override
  String get failedToLoadContacts => 'Nabigo ang pag-load ng mga contact';

  @override
  String get failedToPrepareConversationForSharing =>
      'Nabigo ang paghahanda ng pag-usap para sa pagbabahagi. Subukan ulit.';

  @override
  String get couldNotOpenSmsApp => 'Hindi makuha ang SMS app. Subukan ulit.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'Narito ang aming inabot: $link';
  }

  @override
  String get wifiSync => 'WiFi Sync';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item ay kinopya sa clipboard';
  }

  @override
  String get wifiConnectionFailedTitle => 'Connection Failed';

  @override
  String connectingToDeviceName(String deviceName) {
    return 'Kumokonekta sa $deviceName';
  }

  @override
  String enableDeviceWifi(String deviceName) {
    return 'Paganahin ang $deviceName\'s WiFi';
  }

  @override
  String connectToDeviceName(String deviceName) {
    return 'Kumonekta sa $deviceName';
  }

  @override
  String get recordingDetails => 'Recording Details';

  @override
  String get storageLocationSdCard => 'SD Card';

  @override
  String get storageLocationLimitlessPendant => 'Limitless Pendant';

  @override
  String get storageLocationPhone => 'Telepono';

  @override
  String get storageLocationPhoneMemory => 'Telepono (Memory)';

  @override
  String storedOnDevice(String deviceName) {
    return 'Nakaimbak sa $deviceName';
  }

  @override
  String get transferring => 'Naglilipat...';

  @override
  String get transferRequired => 'Transfer Required';

  @override
  String get downloadingAudioFromSdCard => 'Dine-download ang audio mula sa SD card ng iyong device';

  @override
  String get transferRequiredDescription =>
      'Ang recording na ito ay nakaimbak sa SD card ng iyong device. Ilipat ito sa iyong telepono upang maglaro o magbahagi.';

  @override
  String get cancelTransfer => 'Kanselahin ang Transfer';

  @override
  String get transferToPhone => 'Ilipat sa Telepono';

  @override
  String get privateAndSecureOnDevice => 'Pribado at secure sa iyong device';

  @override
  String get recordingInfo => 'Recording Info';

  @override
  String get transferInProgress => 'Nagsisimula ang paglipat...';

  @override
  String get shareRecording => 'Ibahagi ang Recording';

  @override
  String get deleteRecordingConfirmation =>
      'Sigurado ka na gusto mong permanenteng tanggalin ang recording na ito? Hindi na ito mababawi.';

  @override
  String get recordingIdLabel => 'Recording ID';

  @override
  String get dateTimeLabel => 'Petsa at Oras';

  @override
  String get durationLabel => 'Tagal';

  @override
  String get audioFormatLabel => 'Audio Format';

  @override
  String get storageLocationLabel => 'Lokasyon ng Imbak';

  @override
  String get estimatedSizeLabel => 'Inaasahang Laki';

  @override
  String get deviceModelLabel => 'Device Model';

  @override
  String get deviceIdLabel => 'Device ID';

  @override
  String get statusLabel => 'Status';

  @override
  String get statusProcessed => 'Naproseso';

  @override
  String get statusUnprocessed => 'Hindi Naproseso';

  @override
  String get switchedToFastTransfer => 'Lumipat sa Fast Transfer';

  @override
  String get transferCompleteMessage => 'Tapos na ang paglipat! Maaari mo na ngayong i-play ang recording na ito.';

  @override
  String transferFailedMessage(String error) {
    return 'Nabigo ang paglipat: $error';
  }

  @override
  String get transferCancelled => 'Kinansela ang paglipat';

  @override
  String get fastTransferEnabled => 'Fast Transfer ay naka-enable';

  @override
  String get bluetoothSyncEnabled => 'Bluetooth sync ay naka-enable';

  @override
  String get enableFastTransfer => 'I-enable ang Fast Transfer';

  @override
  String get fastTransferDescription =>
      'Gumagamit ang Fast Transfer ng WiFi para sa humigit-kumulang na 5x na mas mabilis na bilis. Ang iyong telepono ay pansamantalang magkonekta sa WiFi network ng iyong Omi device sa panahon ng paglipat.';

  @override
  String get internetAccessPausedDuringTransfer => 'Ang internet access ay napigil sa panahon ng paglipat';

  @override
  String get chooseTransferMethodDescription =>
      'Pumili kung paano ang mga recording ay ilipat mula sa iyong Omi device patungo sa iyong telepono.';

  @override
  String get wifiSpeed => '~150 KB/s sa pamamagitan ng WiFi';

  @override
  String get fiveTimesFaster => '5X MAS MABILIS';

  @override
  String get fastTransferMethodDescription =>
      'Lumilikha ng direktang WiFi connection sa iyong Omi device. Ang iyong telepono ay pansamantalang nadadiskonekta mula sa iyong regular na WiFi sa panahon ng paglipat.';

  @override
  String get bluetooth => 'Bluetooth';

  @override
  String get bleSpeed => '~30 KB/s sa pamamagitan ng BLE';

  @override
  String get bluetoothMethodDescription =>
      'Gumagamit ng standard Bluetooth Low Energy connection. Mas mabagal ngunit hindi nakakaapekto sa iyong WiFi connection.';

  @override
  String get selected => 'Napili';

  @override
  String get selectOption => 'Piliin';

  @override
  String get lowBatteryAlertTitle => 'Low Battery Alert';

  @override
  String get lowBatteryAlertBody => 'Ang iyong device ay mababa na sa baterya. Panahon na para mag-recharge! 🔋';

  @override
  String get deviceDisconnectedNotificationTitle => 'Ang Iyong Omi Device ay Nadiskonekta';

  @override
  String get deviceDisconnectedNotificationBody =>
      'Mangyaring mag-reconnect upang magpatuloy ng paggamit ng iyong Omi.';

  @override
  String get firmwareUpdateAvailable => 'Available ang Firmware Update';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'Ang bagong firmware update ($version) ay available para sa iyong Omi device. Gusto mo na bang mag-update ngayon?';
  }

  @override
  String get later => 'Mamaya';

  @override
  String get appDeletedSuccessfully => 'Matagumpay na nabura ang app';

  @override
  String get appDeleteFailed => 'Nabigo ang pagsisikap na burahin ang app. Mangyaring subukan ulit mamaya.';

  @override
  String get appVisibilityChangedSuccessfully =>
      'Matagumpay na binago ang visibility ng app. Maaaring tumagal ng ilang minuto upang makita ang pagbabago.';

  @override
  String get errorActivatingAppIntegration =>
      'Nagkamalian sa pag-activate ng app. Kung ito ay isang integration app, siguraduhin na tapos na ang setup.';

  @override
  String get errorUpdatingAppStatus => 'Nagkaroon ng error sa pag-update ng app status.';

  @override
  String get calculatingETA => 'Kinakalkula...';

  @override
  String aboutMinutesRemaining(int minutes) {
    return 'Humigit-kumulang $minutes minuto na lang';
  }

  @override
  String get aboutAMinuteRemaining => 'Humigit-kumulang isang minuto na lang';

  @override
  String get almostDone => 'Halos tapos na...';

  @override
  String get omiSays => 'sinabi ni omi';

  @override
  String get analyzingYourData => 'Sinusuri ang iyong data...';

  @override
  String migratingToProtection(String level) {
    return 'Minomuber sa $level protection...';
  }

  @override
  String get noDataToMigrateFinalizing => 'Walang data na ilipat. Fininalizing...';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return 'Minomuber ang $itemType... $percentage%';
  }

  @override
  String get allObjectsMigratedFinalizing => 'Lahat ng objects ay nalipat. Fininalizing...';

  @override
  String get migrationErrorOccurred => 'Nagkamalian sa panahon ng migration. Mangyaring subukan ulit.';

  @override
  String get migrationComplete => 'Tapos na ang migration!';

  @override
  String dataProtectedWithSettings(String level) {
    return 'Ang iyong data ay protektado na ngayon gamit ang bagong $level settings.';
  }

  @override
  String get chatsLowercase => 'chats';

  @override
  String get dataLowercase => 'data';

  @override
  String get fallNotificationTitle => 'Ay nako';

  @override
  String get fallNotificationBody => 'Nahulog ka ba?';

  @override
  String get importantConversationTitle => 'Important Conversation';

  @override
  String get importantConversationBody => 'Mayroon kang important na usapan. I-tap upang ibahagi ang summary sa iba.';

  @override
  String get templateName => 'Template Name';

  @override
  String get templateNameHint => 'e.g., Meeting Action Items Extractor';

  @override
  String get nameMustBeAtLeast3Characters => 'Dapat ang pangalan ay hindi bababa sa 3 character';

  @override
  String get conversationPromptHint =>
      'e.g., I-extract ang action items, decisions na ginawa, at key takeaways mula sa ibinigay na conversation.';

  @override
  String get pleaseEnterAppPrompt => 'Mangyaring magpasok ng prompt para sa iyong app';

  @override
  String get promptMustBeAtLeast10Characters => 'Dapat ang prompt ay hindi bababa sa 10 character';

  @override
  String get anyoneCanDiscoverTemplate => 'Kahit sino ay maaaring matuklasan ang iyong template';

  @override
  String get onlyYouCanUseTemplate => 'Ikaw lang ang maaaring gumagamit ng template na ito';

  @override
  String get generatingDescription => 'Lumilikha ng description...';

  @override
  String get creatingAppIcon => 'Lumilikha ng app icon...';

  @override
  String get installingApp => 'Nag-i-install ng app...';

  @override
  String get appCreatedAndInstalled => 'Nilikha at na-install ang app!';

  @override
  String get appCreatedSuccessfully => 'Matagumpay na nilikha ang app!';

  @override
  String get failedToCreateApp => 'Nabigo ang paglalakbay na lumikha ng app. Mangyaring subukan ulit.';

  @override
  String get addAppSelectCoreCapability =>
      'Mangyaring pumili ng isa pang core capability para sa iyong app upang magpatuloy';

  @override
  String get addAppSelectPaymentPlan => 'Mangyaring pumili ng payment plan at magpasok ng presyo para sa iyong app';

  @override
  String get addAppSelectCapability => 'Mangyaring pumili ng hindi bababa sa isang capability para sa iyong app';

  @override
  String get addAppSelectLogo => 'Mangyaring pumili ng logo para sa iyong app';

  @override
  String get addAppEnterChatPrompt => 'Mangyaring magpasok ng chat prompt para sa iyong app';

  @override
  String get addAppEnterConversationPrompt => 'Mangyaring magpasok ng conversation prompt para sa iyong app';

  @override
  String get addAppSelectTriggerEvent => 'Mangyaring pumili ng trigger event para sa iyong app';

  @override
  String get addAppEnterWebhookUrl => 'Mangyaring magpasok ng webhook URL para sa iyong app';

  @override
  String get addAppSelectCategory => 'Mangyaring pumili ng category para sa iyong app';

  @override
  String get addAppFillRequiredFields => 'Mangyaring punan ang lahat ng required fields ng tama';

  @override
  String get addAppUpdatedSuccess => 'Matagumpay na na-update ang app 🚀';

  @override
  String get addAppUpdateFailed => 'Nabigo ang pag-update ng app. Mangyaring subukan ulit mamaya';

  @override
  String get addAppSubmittedSuccess => 'Matagumpay na napadala ang app 🚀';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'Nagkamalian sa pagbukas ng file picker: $message';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'Nagkamalian sa pagpili ng imahe: $error';
  }

  @override
  String get addAppPhotosPermissionDenied =>
      'Ang Photos permission ay tinanggihan. Mangyaring payagan ang access sa mga photo upang pumili ng imahe';

  @override
  String get addAppErrorSelectingImageRetry => 'Nagkamalian sa pagpili ng imahe. Mangyaring subukan ulit.';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'Nagkamalian sa pagpili ng thumbnail: $error';
  }

  @override
  String get addAppErrorSelectingThumbnailRetry => 'Nagkamalian sa pagpili ng thumbnail. Mangyaring subukan ulit.';

  @override
  String get addAppCapabilityConflictWithPersona =>
      'Hindi maaaring piliin ang iba pang capabilities kasama ang Persona';

  @override
  String get addAppPersonaConflictWithCapabilities =>
      'Hindi maaaring piliin ang Persona kasama ang iba pang capabilities';

  @override
  String get paymentFailedToFetchCountries =>
      'Nabigo ang pagkuha ng mga supported countries. Mangyaring subukan ulit mamaya.';

  @override
  String get paymentFailedToSetDefault =>
      'Nabigo ang pagseset ng default payment method. Mangyaring subukan ulit mamaya.';

  @override
  String get paymentFailedToSavePaypal => 'Nabigo ang pagsave ng PayPal details. Mangyaring subukan ulit mamaya.';

  @override
  String get paypalEmailHint => 'nik@example.com';

  @override
  String get paypalMeLinkHint => 'paypal.me/nik';

  @override
  String get paymentMethodStripe => 'Stripe';

  @override
  String get paymentMethodPayPal => 'PayPal';

  @override
  String get paymentStatusActive => 'Active';

  @override
  String get paymentStatusConnected => 'Connected';

  @override
  String get paymentStatusNotConnected => 'Not Connected';

  @override
  String get paymentAppCost => 'App Cost';

  @override
  String get paymentEnterValidAmount => 'Mangyaring magpasok ng valid na halaga';

  @override
  String get paymentEnterAmountGreaterThanZero => 'Mangyaring magpasok ng halaga na higit sa 0';

  @override
  String get paymentPlan => 'Payment Plan';

  @override
  String get paymentNoneSelected => 'Walang Napili';

  @override
  String get aiGenPleaseEnterDescription => 'Mangyaring magpasok ng description para sa iyong app';

  @override
  String get aiGenCreatingAppIcon => 'Lumilikha ng app icon...';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'Nagkamalian: $message';
  }

  @override
  String get aiGenAppCreatedSuccessfully => 'Matagumpay na nilikha ang app!';

  @override
  String get aiGenFailedToCreateApp => 'Nabigo ang paglikha ng app';

  @override
  String get aiGenErrorWhileCreatingApp => 'Nagkamalian sa panahon ng paglikha ng app';

  @override
  String get aiGenFailedToGenerateApp => 'Nabigo ang paggenerate ng app. Mangyaring subukan ulit.';

  @override
  String get aiGenFailedToRegenerateIcon => 'Nabigo ang pag-regenerate ng icon';

  @override
  String get aiGenPleaseGenerateAppFirst => 'Mangyaring maggenerate ng app muna';

  @override
  String get nextButton => 'Susunod';

  @override
  String get connectOmiDevice => 'I-connect ang Omi Device';

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'Ikaw ay gumagalit ng iyong Unlimited Plan sa $title. Sigurado ka na bang gusto mong magpatuloy?';
  }

  @override
  String get planUpgradeScheduledMessage =>
      'Upgrade ay naka-schedule na! Ang iyong monthly plan ay patuloy hanggang sa dulo ng iyong billing period, pagkatapos ay awtomatikong magsasalit sa annual.';

  @override
  String get couldNotSchedulePlanChange => 'Hindi makasagawa ang pag-schedule ng plan change. Mangyaring subukan ulit.';

  @override
  String get subscriptionReactivatedDefault =>
      'Ang iyong subscription ay naka-reactivate na! Walang charge ngayon - ikaw ay ma-bill sa dulo ng iyong current period.';

  @override
  String get subscriptionSuccessfulCharged =>
      'Matagumpay na subscription! Ikaw ay na-charge para sa bagong billing period.';

  @override
  String get couldNotProcessSubscription => 'Hindi makasagawa ang proseso ng subscription. Mangyaring subukan ulit.';

  @override
  String get couldNotLaunchUpgradePage => 'Hindi makabuksan ang upgrade page. Mangyaring subukan ulit.';

  @override
  String get transcriptionJsonPlaceholder => 'I-paste ang iyong JSON configuration dito...';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get pricePlaceholder => '0.00';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'Nagkamalian sa pagbukas ng file picker: $message';
  }

  @override
  String importErrorGeneric(String error) {
    return 'Nagkamalian: $error';
  }

  @override
  String get mergeConversationsSuccessTitle => 'Matagumpay na Pinagsama ang Conversations';

  @override
  String mergeConversationsSuccessBody(int count) {
    return '$count conversations ay matagumpay na pinagsama';
  }

  @override
  String get actionItemReminderTitle => 'Omi Reminder';

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName Nadiskonekta';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'Mangyaring mag-reconnect upang magpatuloy ng paggamit ng iyong $deviceName.';
  }

  @override
  String get onboardingSignIn => 'Mag-sign In';

  @override
  String get onboardingYourName => 'Ang Iyong Pangalan';

  @override
  String get onboardingLanguage => 'Wika';

  @override
  String get onboardingPermissions => 'Mga Permission';

  @override
  String get onboardingComplete => 'Kumpleto';

  @override
  String get onboardingWelcomeToOmi => 'Maligayang Pagdating sa Omi';

  @override
  String get onboardingTellUsAboutYourself => 'Sabihin sa amin tungkol sa iyo';

  @override
  String get onboardingChooseYourPreference => 'Piliin ang iyong kagustuhan';

  @override
  String get onboardingGrantRequiredAccess => 'Bigyan ng kinakailangang access';

  @override
  String get onboardingYoureAllSet => 'Handa ka na';

  @override
  String get searchTranscriptOrSummary => 'Maghanap ng transcript o summary...';

  @override
  String get myGoal => 'Ang Aking Layunin';

  @override
  String get appNotAvailable => 'Oops! Mukhang ang app na hinahanap mo ay hindi available.';

  @override
  String get failedToConnectTodoist => 'Nabigo ang pagkonekta sa Todoist';

  @override
  String get failedToConnectAsana => 'Nabigo ang pagkonekta sa Asana';

  @override
  String get failedToConnectGoogleTasks => 'Nabigo ang pagkonekta sa Google Tasks';

  @override
  String get failedToConnectClickUp => 'Nabigo ang pagkonekta sa ClickUp';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return 'Nabigo ang pagkonekta sa $serviceName: $error';
  }

  @override
  String get successfullyConnectedTodoist => 'Matagumpay na kumonekta sa Todoist!';

  @override
  String get failedToConnectTodoistRetry => 'Nabigo ang pagkonekta sa Todoist. Mangyaring subukan ulit.';

  @override
  String get successfullyConnectedAsana => 'Matagumpay na kumonekta sa Asana!';

  @override
  String get failedToConnectAsanaRetry => 'Nabigo ang pagkonekta sa Asana. Mangyaring subukan ulit.';

  @override
  String get successfullyConnectedGoogleTasks => 'Matagumpay na kumonekta sa Google Tasks!';

  @override
  String get failedToConnectGoogleTasksRetry => 'Nabigo ang pagkonekta sa Google Tasks. Mangyaring subukan ulit.';

  @override
  String get successfullyConnectedClickUp => 'Matagumpay na kumonekta sa ClickUp!';

  @override
  String get failedToConnectClickUpRetry => 'Nabigo ang pagkonekta sa ClickUp. Mangyaring subukan ulit.';

  @override
  String get successfullyConnectedNotion => 'Matagumpay na kumonekta sa Notion!';

  @override
  String get failedToRefreshNotionStatus => 'Nabigo ang pag-refresh ng Notion connection status.';

  @override
  String get successfullyConnectedGoogle => 'Matagumpay na kumonekta sa Google!';

  @override
  String get failedToRefreshGoogleStatus => 'Nabigo ang pag-refresh ng Google connection status.';

  @override
  String get successfullyConnectedWhoop => 'Matagumpay na kumonekta sa Whoop!';

  @override
  String get failedToRefreshWhoopStatus => 'Nabigo ang pag-refresh ng Whoop connection status.';

  @override
  String get successfullyConnectedGitHub => 'Matagumpay na kumonekta sa GitHub!';

  @override
  String get failedToRefreshGitHubStatus => 'Nabigo ang pag-refresh ng GitHub connection status.';

  @override
  String get authFailedToSignInWithGoogle => 'Nabigo ang pag-sign in gamit ang Google, mangyaring subukan ulit.';

  @override
  String get authenticationFailed => 'Nabigo ang authentication. Mangyaring subukan ulit.';

  @override
  String get authFailedToSignInWithApple => 'Nabigo ang pag-sign in gamit ang Apple, mangyaring subukan ulit.';

  @override
  String get authFailedToRetrieveToken => 'Nabigo ang pagkuha ng firebase token, mangyaring subukan ulit.';

  @override
  String get authUnexpectedErrorFirebase => 'Unexpected error sa pag-sign in, Firebase error, mangyaring subukan ulit.';

  @override
  String get authUnexpectedError => 'Unexpected error sa pag-sign in, mangyaring subukan ulit';

  @override
  String get authFailedToLinkGoogle => 'Nabigo ang pag-link gamit ang Google, mangyaring subukan ulit.';

  @override
  String get authFailedToLinkApple => 'Nabigo ang pag-link gamit ang Apple, mangyaring subukan ulit.';

  @override
  String get onboardingBluetoothRequired =>
      'Ang Bluetooth permission ay kinakailangan upang kumonekta sa iyong device.';

  @override
  String get onboardingBluetoothDeniedSystemPrefs =>
      'Ang Bluetooth permission ay tinanggihan. Mangyaring bigyan ng permission sa System Preferences.';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'Bluetooth permission status: $status. Mangyaring tignan ang System Preferences.';
  }

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'Nabigo ang pagcheck ng Bluetooth permission: $error';
  }

  @override
  String get onboardingNotificationDeniedSystemPrefs =>
      'Ang Notification permission ay tinanggihan. Mangyaring bigyan ng permission sa System Preferences.';

  @override
  String get onboardingNotificationDeniedNotifications =>
      'Ang Notification permission ay tinanggihan. Mangyaring bigyan ng permission sa System Preferences > Notifications.';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return 'Notification permission status: $status. Mangyaring tignan ang System Preferences.';
  }

  @override
  String onboardingFailedCheckNotification(String error) {
    return 'Nabigo ang pagcheck ng Notification permission: $error';
  }

  @override
  String get onboardingLocationGrantInSettings =>
      'Mangyaring bigyan ng location permission sa Settings > Privacy & Security > Location Services';

  @override
  String get onboardingMicrophoneRequired => 'Ang Microphone permission ay kinakailangan para sa pag-record.';

  @override
  String get onboardingMicrophoneDenied =>
      'Ang Microphone permission ay tinanggihan. Mangyaring bigyan ng permission sa System Preferences > Privacy & Security > Microphone.';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'Microphone permission status: $status. Mangyaring tignan ang System Preferences.';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'Nabigo ang pagcheck ng Microphone permission: $error';
  }

  @override
  String get onboardingScreenCaptureRequired =>
      'Ang Screen capture permission ay kinakailangan para sa system audio recording.';

  @override
  String get onboardingScreenCaptureDenied =>
      'Ang Screen capture permission ay tinanggihan. Mangyaring bigyan ng permission sa System Preferences > Privacy & Security > Screen Recording.';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return 'Screen capture permission status: $status. Mangyaring tignan ang System Preferences.';
  }

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return 'Nabigo ang pagcheck ng Screen Capture permission: $error';
  }

  @override
  String get onboardingAccessibilityRequired =>
      'Ang Accessibility permission ay kinakailangan para sa pag-detect ng browser meetings.';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'Accessibility permission status: $status. Mangyaring tignan ang System Preferences.';
  }

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'Nabigo ang pagcheck ng Accessibility permission: $error';
  }

  @override
  String get msgCameraNotAvailable => 'Ang Camera capture ay hindi available sa platform na ito';

  @override
  String get msgCameraPermissionDenied =>
      'Ang Camera permission ay tinanggihan. Mangyaring payagan ang access sa camera';

  @override
  String msgCameraAccessError(String error) {
    return 'Nagkamalian sa pag-access ng camera: $error';
  }

  @override
  String get msgPhotoError => 'Nagkamalian sa pagkuha ng photo. Mangyaring subukan ulit.';

  @override
  String get msgMaxImagesLimit => 'Maaari kang pumili ng hanggang 4 na mga imahe lamang';

  @override
  String msgFilePickerError(String error) {
    return 'Nagkamalian sa pagbukas ng file picker: $error';
  }

  @override
  String msgSelectImagesError(String error) {
    return 'Nagkamalian sa pagpili ng mga imahe: $error';
  }

  @override
  String get msgPhotosPermissionDenied =>
      'Ang Photos permission ay tinanggihan. Mangyaring payagan ang access sa mga photo upang pumili ng mga imahe';

  @override
  String get msgSelectImagesGenericError => 'Nagkamalian sa pagpili ng mga imahe. Mangyaring subukan ulit.';

  @override
  String get msgMaxFilesLimit => 'Maaari kang pumili ng hanggang 4 na mga file lamang';

  @override
  String msgSelectFilesError(String error) {
    return 'Nagkamalian sa pagpili ng mga file: $error';
  }

  @override
  String get msgSelectFilesGenericError => 'Nagkamalian sa pagpili ng mga file. Mangyaring subukan ulit.';

  @override
  String get msgUploadFileFailed => 'Nabigo ang pag-upload ng file, mangyaring subukan ulit mamaya';

  @override
  String get msgReadingMemories => 'Binabasa ang iyong mga memories...';

  @override
  String get msgLearningMemories => 'Natututo mula sa iyong mga memories...';

  @override
  String get msgUploadAttachedFileFailed => 'Nabigo ang pag-upload ng attached file.';

  @override
  String captureRecordingError(String error) {
    return 'Nagkamalian sa panahon ng pag-record: $error';
  }

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return 'Huminto ang pag-record: $reason. Maaaring kailanganin mong mag-reconnect ng external displays o magsimula ulit ng pag-record.';
  }

  @override
  String get captureMicrophonePermissionRequired => 'Ang Microphone permission ay kinakailangan';

  @override
  String get captureMicrophonePermissionInSystemPreferences => 'Bigyan ng microphone permission sa System Preferences';

  @override
  String get captureScreenRecordingPermissionRequired => 'Ang Screen recording permission ay kinakailangan';

  @override
  String get captureDisplayDetectionFailed => 'Nabigo ang display detection. Huminto ang pag-record.';

  @override
  String get devModeInvalidAudioBytesWebhookUrl => 'Invalid audio bytes webhook URL';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl => 'Invalid realtime transcript webhook URL';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl => 'Invalid conversation created webhook URL';

  @override
  String get devModeInvalidDaySummaryWebhookUrl => 'Invalid day summary webhook URL';

  @override
  String get devModeSettingsSaved => 'Na-save ang settings!';

  @override
  String get voiceFailedToTranscribe => 'Nabigo ang pag-transcribe ng audio';

  @override
  String get locationPermissionRequired => 'Ang Location Permission ay Kinakailangan';

  @override
  String get locationPermissionContent =>
      'Ang Fast Transfer ay nangangailangan ng location permission upang ma-verify ang WiFi connection. Mangyaring bigyan ng location permission upang magpatuloy.';

  @override
  String get pdfTranscriptExport => 'Transcript Export';

  @override
  String get pdfConversationExport => 'Conversation Export';

  @override
  String pdfTitleLabel(String title) {
    return 'Title: $title';
  }

  @override
  String get conversationNewIndicator => 'Bago 🚀';

  @override
  String conversationPhotosCount(int count) {
    return '$count mga photo';
  }

  @override
  String get mergingStatus => 'Nagsasama...';

  @override
  String timeSecsSingular(int count) {
    return '$count sec';
  }

  @override
  String timeSecsPlural(int count) {
    return '$count secs';
  }

  @override
  String timeMinSingular(int count) {
    return '$count min';
  }

  @override
  String timeMinsPlural(int count) {
    return '$count mins';
  }

  @override
  String timeMinsAndSecs(int mins, int secs) {
    return '$mins mins $secs secs';
  }

  @override
  String timeHourSingular(int count) {
    return '$count oras';
  }

  @override
  String timeHoursPlural(int count) {
    return '$count oras';
  }

  @override
  String timeHoursAndMins(int hours, int mins) {
    return '$hours oras $mins mins';
  }

  @override
  String timeDaySingular(int count) {
    return '$count araw';
  }

  @override
  String timeDaysPlural(int count) {
    return '$count araw';
  }

  @override
  String timeDaysAndHours(int days, int hours) {
    return '$days araw $hours oras';
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
    return '${count}h';
  }

  @override
  String timeCompactHoursAndMins(int hours, int mins) {
    return '${hours}h ${mins}m';
  }

  @override
  String get moveToFolder => 'Ilipat sa Folder';

  @override
  String get noFoldersAvailable => 'Walang available na mga folder';

  @override
  String get newFolder => 'Bagong Folder';

  @override
  String get color => 'Kulay';

  @override
  String get waitingForDevice => 'Naghihintay para sa device...';

  @override
  String get saySomething => 'Sabihin ang kahit ano...';

  @override
  String get initialisingSystemAudio => 'Nag-i-initialize ng System Audio';

  @override
  String get stopRecording => 'Ihinto ang Pag-record';

  @override
  String get continueRecording => 'Magpatuloy sa Pag-record';

  @override
  String get initialisingRecorder => 'Nag-i-initialize ng Recorder';

  @override
  String get pauseRecording => 'I-pause ang Pag-record';

  @override
  String get resumeRecording => 'Ipagpatuloy ang Pag-record';

  @override
  String get noDailyRecapsYet => 'Walang daily recaps pa';

  @override
  String get dailyRecapsDescription => 'Ang iyong daily recaps ay lilitaw dito kapag na-generate na';

  @override
  String get chooseTransferMethod => 'Pumili ng Transfer Method';

  @override
  String get fastTransferSpeed => '~150 KB/s sa pamamagitan ng WiFi';

  @override
  String largeTimeGapDetected(String gap) {
    return 'Malaking time gap na natuklasan ($gap)';
  }

  @override
  String largeTimeGapsDetected(String gaps) {
    return 'Malaking time gaps na natuklasan ($gaps)';
  }

  @override
  String get deviceDoesNotSupportWifiSwitchingToBle =>
      'Ang device ay hindi sumusuporta sa WiFi sync, lumipat sa Bluetooth';

  @override
  String get appleHealthNotAvailable => 'Ang Apple Health ay hindi available sa device na ito';

  @override
  String get downloadAudio => 'I-download ang Audio';

  @override
  String get audioDownloadSuccess => 'Matagumpay na na-download ang audio';

  @override
  String get audioDownloadFailed => 'Nabigo ang pag-download ng audio';

  @override
  String get downloadingAudio => 'Nag-download ng audio...';

  @override
  String get shareAudio => 'Ibahagi ang Audio';

  @override
  String get preparingAudio => 'Naghahanda ng Audio';

  @override
  String get gettingAudioFiles => 'Nakakakuha ng audio files...';

  @override
  String get downloadingAudioProgress => 'Nag-download ng Audio';

  @override
  String get processingAudio => 'Nagpoproseso ng Audio';

  @override
  String get combiningAudioFiles => 'Pinagsasama ang audio files...';

  @override
  String get audioReady => 'Handa na ang Audio';

  @override
  String get openingShareSheet => 'Binubuksan ang share sheet...';

  @override
  String get audioShareFailed => 'Nabigo ang Share';

  @override
  String get dailyRecaps => 'Daily Recaps';

  @override
  String get removeFilter => 'Alisin ang Filter';

  @override
  String get categoryConversationAnalysis => 'Conversation Analysis';

  @override
  String get categoryHealth => 'Kalusugan';

  @override
  String get categoryEducation => 'Edukasyon';

  @override
  String get categoryCommunication => 'Komunikasyon';

  @override
  String get categoryEmotionalSupport => 'Emotional Support';

  @override
  String get categoryProductivity => 'Produktibidad';

  @override
  String get categoryEntertainment => 'Entertainment';

  @override
  String get categoryFinancial => 'Financial';

  @override
  String get categoryTravel => 'Travel';

  @override
  String get categorySafety => 'Seguridad';

  @override
  String get categoryShopping => 'Shopping';

  @override
  String get categorySocial => 'Social';

  @override
  String get categoryNews => 'Balita';

  @override
  String get categoryUtilities => 'Utilities';

  @override
  String get categoryOther => 'Iba';

  @override
  String get capabilityChat => 'Chat';

  @override
  String get capabilityConversations => 'Conversations';

  @override
  String get capabilityExternalIntegration => 'External Integration';

  @override
  String get capabilityNotification => 'Notification';

  @override
  String get triggerAudioBytes => 'Audio Bytes';

  @override
  String get triggerConversationCreation => 'Conversation Creation';

  @override
  String get triggerTranscriptProcessed => 'Transcript Processed';

  @override
  String get actionCreateConversations => 'Lumikha ng conversations';

  @override
  String get actionCreateMemories => 'Lumikha ng memories';

  @override
  String get actionReadConversations => 'Basahin ang conversations';

  @override
  String get actionReadMemories => 'Basahin ang memories';

  @override
  String get actionReadTasks => 'Basahin ang tasks';

  @override
  String get scopeUserName => 'User Name';

  @override
  String get scopeUserFacts => 'User Facts';

  @override
  String get scopeUserConversations => 'User Conversations';

  @override
  String get scopeUserChat => 'User Chat';

  @override
  String get capabilitySummary => 'Summary';

  @override
  String get capabilityFeatured => 'Featured';

  @override
  String get capabilityTasks => 'Tasks';

  @override
  String get capabilityIntegrations => 'Integrations';

  @override
  String get categoryProductivityLifestyle => 'Productivity & Lifestyle';

  @override
  String get categorySocialEntertainment => 'Social & Entertainment';

  @override
  String get categoryProductivityTools => 'Productivity & Tools';

  @override
  String get categoryPersonalWellness => 'Personal & Lifestyle';

  @override
  String get rating => 'Rating';

  @override
  String get categories => 'Mga Kategorya';

  @override
  String get sortBy => 'I-sort';

  @override
  String get highestRating => 'Pinakamataas na Rating';

  @override
  String get lowestRating => 'Pinakamababa na Rating';

  @override
  String get resetFilters => 'I-reset ang mga filter';

  @override
  String get applyFilters => 'Ilapat ang mga filter';

  @override
  String get mostInstalls => 'Pinakamaraming I-install';

  @override
  String get couldNotOpenUrl => 'Hindi ma-bukas ang URL. Mangyaring subukan ulit.';

  @override
  String get newTask => 'Bagong Task';

  @override
  String get viewAll => 'Tingnan Lahat';

  @override
  String get addTask => 'Magdagdag ng Task';

  @override
  String get addMcpServer => 'Magdagdag ng MCP Server';

  @override
  String get connectExternalAiTools => 'Kumonekta sa external AI tools';

  @override
  String get mcpServerUrl => 'MCP Server URL';

  @override
  String mcpServerConnected(int count) {
    return '$count tools na nag-connect nang matagumpay';
  }

  @override
  String get mcpConnectionFailed => 'Nabigo ang pagkonekta sa MCP server';

  @override
  String get authorizingMcpServer => 'Nag-authorize...';

  @override
  String get whereDidYouHearAboutOmi => 'Paano ka nakahanap sa amin?';

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
  String get friendWordOfMouth => 'Kaibigan';

  @override
  String get otherSource => 'Iba';

  @override
  String get pleaseSpecify => 'Mangyaring tukuyin';

  @override
  String get event => 'Event';

  @override
  String get coworker => 'Kasamahan sa trabaho';

  @override
  String get linkedIn => 'LinkedIn';

  @override
  String get appStore => 'App Store';

  @override
  String get googleSearch => 'Google Search';

  @override
  String get audioPlaybackUnavailable => 'Ang audio file ay hindi available para sa playback';

  @override
  String get audioPlaybackFailed => 'Hindi ma-play ang audio. Ang file ay maaaring na-corrupt o nawawala.';

  @override
  String get connectionGuide => 'Connection Guide';

  @override
  String get iveDoneThis => 'Tapos ko na ito';

  @override
  String get pairNewDevice => 'I-pair ang bagong device';

  @override
  String get dontSeeYourDevice => 'Hindi mo makikita ang iyong device?';

  @override
  String get reportAnIssue => 'Mag-ulat ng isang isyu';

  @override
  String get pairingTitleOmi => 'I-on ang Omi';

  @override
  String get pairingDescOmi => 'Pindutin at panatilihin ang device hanggang sa mag-vibrate upang i-on ito.';

  @override
  String get pairingTitleOmiDevkit => 'Ilagay ang Omi DevKit sa Pairing Mode';

  @override
  String get pairingDescOmiDevkit =>
      'Pindutin ang button nang isang beses upang i-on. Ang LED ay mag-blink ng purple kapag nasa pairing mode.';

  @override
  String get pairingTitleOmiGlass => 'I-on ang Omi Glass';

  @override
  String get pairingDescOmiGlass => 'I-power on sa pamamagitan ng pagpipigil sa side button sa loob ng 3 segundo.';

  @override
  String get pairingTitlePlaudNote => 'Ilagay ang Plaud Note sa Pairing Mode';

  @override
  String get pairingDescPlaudNote =>
      'Pindutin at panatilihin ang side button sa loob ng 2 segundo. Ang red LED ay mag-blink kapag handa nang mag-pair.';

  @override
  String get pairingTitleBee => 'Ilagay ang Bee sa Pairing Mode';

  @override
  String get pairingDescBee =>
      'Pindutin ang button nang 5 beses nang tuluy-tuloy. Ang liwanag ay magsisimulang mag-blink ng asul at luntian.';

  @override
  String get pairingTitleLimitless => 'Ilagay ang Limitless sa Pairing Mode';

  @override
  String get pairingDescLimitless =>
      'Kapag may nakikitang liwanag, pindutin nang isang beses at pagkatapos ay pindutin at panatilihin hanggang sa ipakita ng device ang pink light, pagkatapos ay palayain.';

  @override
  String get pairingTitleFriendPendant => 'Ilagay ang Friend Pendant sa Pairing Mode';

  @override
  String get pairingDescFriendPendant =>
      'Pindutin ang button sa pendant upang i-on ito. Automatic na papasok ito sa pairing mode.';

  @override
  String get pairingTitleFieldy => 'Ilagay ang Fieldy sa Pairing Mode';

  @override
  String get pairingDescFieldy => 'Pindutin at panatilihin ang device hanggang sa lumitaw ang liwanag upang i-on ito.';

  @override
  String get pairingTitleAppleWatch => 'Kumonekta sa Apple Watch';

  @override
  String get pairingDescAppleWatch =>
      'I-install at buksan ang Omi app sa iyong Apple Watch, pagkatapos ay i-tap ang Connect sa app.';

  @override
  String get pairingTitleNeoOne => 'Ilagay ang Neo One sa Pairing Mode';

  @override
  String get pairingDescNeoOne =>
      'Pindutin at panatilihin ang power button hanggang sa mag-blink ang LED. Ang device ay magiging discoverable.';

  @override
  String get downloadingFromDevice => 'Nag-download mula sa device';

  @override
  String get reconnectingToInternet => 'Muling kumokonekta sa internet...';

  @override
  String uploadingToCloud(int current, int total) {
    return 'Nag-upload $current ng $total';
  }

  @override
  String get processingOnServer => 'Pinoproseso sa server...';

  @override
  String processingOnServerProgress(int current, int total) {
    return 'Pinoproseso... $current/$total segments';
  }

  @override
  String get processedStatus => 'Naproseso';

  @override
  String get corruptedStatus => 'Nakasira';

  @override
  String nPending(int count) {
    return '$count naghihintay';
  }

  @override
  String nProcessed(int count) {
    return '$count naproseso';
  }

  @override
  String get synced => 'Nag-sync';

  @override
  String get noPendingRecordings => 'Walang naghihintay na recordings';

  @override
  String get noProcessedRecordings => 'Walang naprosesong recordings pa';

  @override
  String get pending => 'Naghihintay';

  @override
  String whatsNewInVersion(String version) {
    return 'Ano ang Bago sa $version';
  }

  @override
  String get addToYourTaskList => 'Idagdag sa iyong task list?';

  @override
  String get failedToCreateShareLink => 'Nabigo ang paglikha ng share link';

  @override
  String get deleteGoal => 'Tanggalin ang Goal';

  @override
  String get deviceUpToDate => 'Ang iyong device ay up to date';

  @override
  String get wifiConfiguration => 'WiFi Configuration';

  @override
  String get wifiConfigurationSubtitle =>
      'Ipasok ang iyong WiFi credentials upang payagan ang device na mag-download ng firmware.';

  @override
  String get networkNameSsid => 'Network Name (SSID)';

  @override
  String get enterWifiNetworkName => 'Ipasok ang WiFi network name';

  @override
  String get enterWifiPassword => 'Ipasok ang WiFi password';

  @override
  String get appIconLabel => 'App Icon';

  @override
  String get onboardingWhatIKnowAboutYouTitle => 'Ito ang alam ko tungkol sa iyo';

  @override
  String get onboardingWhatIKnowAboutYouDescription =>
      'Ang map na ito ay nag-update habang natututo ang Omi mula sa iyong mga conversation.';

  @override
  String get apiEnvironment => 'API Environment';

  @override
  String get apiEnvironmentDescription => 'Pumili kung aling backend ang kukonektahan';

  @override
  String get production => 'Production';

  @override
  String get staging => 'Staging';

  @override
  String get switchRequiresRestart => 'Ang paglipat ay nangangailangan ng app restart';

  @override
  String get switchApiConfirmTitle => 'Baguhin ang API Environment';

  @override
  String switchApiConfirmBody(String environment) {
    return 'Lumipat sa $environment? Kailangan mong isara at muling buksan ang app para mag-apply ang mga pagbabago.';
  }

  @override
  String get switchAndRestart => 'Lumipat';

  @override
  String get stagingDisclaimer =>
      'Ang Staging ay maaaring may bugs, hindi consistent na performance, at maaaring mawala ang data. Gamitin lamang para sa testing.';

  @override
  String get apiEnvSavedRestartRequired => 'Nakatipid. Isara at muling buksan ang app upang mag-apply.';

  @override
  String get shared => 'Shared';

  @override
  String get onlyYouCanSeeConversation => 'Ikaw lamang ang makakakita ng conversation na ito';

  @override
  String get anyoneWithLinkCanView => 'Ang sinumang may link ay maaaring manood';

  @override
  String get tasksCleanTodayTitle => 'Linisin ang tasks ngayong araw?';

  @override
  String get tasksCleanTodayMessage => 'Ito ay mag-aalis lamang ng deadlines';

  @override
  String get tasksOverdue => 'Overdue';

  @override
  String get phoneCallsWithOmi => 'Phone Calls with Omi';

  @override
  String get phoneCallsSubtitle => 'Gumawa ng mga call na may real-time transcription';

  @override
  String get phoneSetupStep1Title => 'I-verify ang iyong phone number';

  @override
  String get phoneSetupStep1Subtitle => 'Tatawagin ka namin upang kumpirmahin na iyo ito';

  @override
  String get phoneSetupStep2Title => 'Magpasok ng verification code';

  @override
  String get phoneSetupStep2Subtitle => 'Isang maikling code na ia-type mo sa call';

  @override
  String get phoneSetupStep3Title => 'Simulan ang pagtawag sa iyong mga contacts';

  @override
  String get phoneSetupStep3Subtitle => 'Na may live transcription na built in';

  @override
  String get phoneGetStarted => 'Magsimula';

  @override
  String get callRecordingConsentDisclaimer =>
      'Ang call recording ay maaaring na kailangan ng consent sa iyong jurisdiction';

  @override
  String get enterYourNumber => 'Ipasok ang iyong number';

  @override
  String get phoneNumberCallerIdHint => 'Kapag na-verify, ito ay magiging iyong caller ID';

  @override
  String get phoneNumberHint => 'Phone number';

  @override
  String get failedToStartVerification => 'Nabigo ang pagpagsimula ng verification';

  @override
  String get phoneContinue => 'Magpatuloy';

  @override
  String get verifyYourNumber => 'I-verify ang iyong number';

  @override
  String get answerTheCallFrom => 'Sagutin ang call mula sa';

  @override
  String get onTheCallEnterThisCode => 'Sa call, ipasok ang code na ito';

  @override
  String get followTheVoiceInstructions => 'Sundin ang voice instructions';

  @override
  String get statusCalling => 'Tumatawag...';

  @override
  String get statusCallInProgress => 'Call in progress';

  @override
  String get statusVerifiedLabel => 'Na-verify';

  @override
  String get statusCallMissed => 'Call missed';

  @override
  String get statusTimedOut => 'Timed out';

  @override
  String get phoneTryAgain => 'Subukan Ulit';

  @override
  String get phonePageTitle => 'Phone';

  @override
  String get phoneContactsTab => 'Contacts';

  @override
  String get phoneKeypadTab => 'Keypad';

  @override
  String get grantContactsAccess => 'Magbigay ng access sa iyong mga contacts';

  @override
  String get phoneAllow => 'Payagan';

  @override
  String get phoneSearchHint => 'Maghanap';

  @override
  String get phoneNoContactsFound => 'Walang contacts na nahanap';

  @override
  String get phoneEnterNumber => 'Ipasok ang number';

  @override
  String get failedToStartCall => 'Nabigo ang pagpagsimula ng call';

  @override
  String get callStateConnecting => 'Kumokonekta...';

  @override
  String get callStateRinging => 'Tumutunog...';

  @override
  String get callStateEnded => 'Call Ended';

  @override
  String get callStateFailed => 'Call Failed';

  @override
  String get transcriptPlaceholder => 'Ang transcript ay magpapakita dito...';

  @override
  String get phoneUnmute => 'I-unmute';

  @override
  String get phoneMute => 'I-mute';

  @override
  String get phoneSpeaker => 'Speaker';

  @override
  String get phoneEndCall => 'Tapos';

  @override
  String get phoneCallSettingsTitle => 'Phone Call Settings';

  @override
  String get showPhoneCallButtonTitle => 'Ipakita ang button ng tawag';

  @override
  String get showPhoneCallButtonDesc => 'Ipakita ang button ng tawag sa home screen';

  @override
  String get yourVerifiedNumbers => 'Ang Iyong Na-verify na Mga Numero';

  @override
  String get verifiedNumbersDescription =>
      'Kapag tumatawag ka sa isang tao, makikita nila ang numerong ito sa kanilang phone';

  @override
  String get noVerifiedNumbers => 'Walang na-verify na mga numero';

  @override
  String deletePhoneNumberConfirm(String phoneNumber) {
    return 'Tanggalin ang $phoneNumber?';
  }

  @override
  String get deletePhoneNumberWarning => 'Kailangan mong i-verify ulit upang gumawa ng mga call';

  @override
  String get phoneDeleteButton => 'Tanggalin';

  @override
  String verifiedMinutesAgo(int minutes) {
    return 'Na-verify ${minutes}m na ang nakakaraan';
  }

  @override
  String verifiedHoursAgo(int hours) {
    return 'Na-verify ${hours}h na ang nakakaraan';
  }

  @override
  String verifiedDaysAgo(int days) {
    return 'Na-verify ${days}d na ang nakakaraan';
  }

  @override
  String verifiedOnDate(String date) {
    return 'Na-verify noong $date';
  }

  @override
  String get verifiedFallback => 'Na-verify';

  @override
  String get callAlreadyInProgress => 'May call na naka-progress na';

  @override
  String get failedToGetCallToken => 'Nabigo ang pagkuha ng call token. I-verify ang iyong phone number una.';

  @override
  String get failedToInitializeCallService => 'Nabigo ang pag-initialize ng call service';

  @override
  String get speakerLabelYou => 'Ikaw';

  @override
  String get speakerLabelUnknown => 'Hindi alam';

  @override
  String get showDailyScoreOnHomepage => 'Ipakita ang Daily Score sa homepage';

  @override
  String get showTasksOnHomepage => 'Ipakita ang Tasks sa homepage';

  @override
  String get phoneCallsUnlimitedOnly => 'Phone Calls via Omi';

  @override
  String get phoneCallsUpsellSubtitle =>
      'Gumawa ng mga call sa pamamagitan ng Omi at makakuha ng real-time transcription, automatic summaries, at marami pang iba. Available exclusively para sa Unlimited plan subscribers.';

  @override
  String get phoneCallsUpsellFeature1 => 'Real-time transcription ng bawat call';

  @override
  String get phoneCallsUpsellFeature2 => 'Automatic call summaries at action items';

  @override
  String get phoneCallsUpsellFeature3 =>
      'Ang mga recipient ay makikita ang iyong tunay na numero, hindi ang random na numero';

  @override
  String get phoneCallsUpsellFeature4 => 'Ang iyong mga call ay nananatiling private at secure';

  @override
  String get phoneCallsUpgradeButton => 'I-upgrade sa Unlimited';

  @override
  String get phoneCallsMaybeLater => 'Siguro sa ibang pagkakataon';

  @override
  String get deleteSynced => 'Tanggalin ang Synced';

  @override
  String get deleteSyncedFiles => 'Tanggalin ang Synced Recordings';

  @override
  String get deleteSyncedFilesMessage => 'Ang mga recording na ito ay nag-sync na sa iyong phone. Hindi ito mababawi.';

  @override
  String get syncedFilesDeleted => 'Ang synced recordings ay nakatanggal';

  @override
  String get deletePending => 'Tanggalin ang Pending';

  @override
  String get deletePendingFiles => 'Tanggalin ang Pending Recordings';

  @override
  String get deletePendingFilesWarning =>
      'Ang mga recording na ito ay HINDI nag-sync sa iyong phone at permanent na mawawala. Hindi ito mababawi.';

  @override
  String get pendingFilesDeleted => 'Ang pending recordings ay nakatanggal';

  @override
  String get deleteAllFiles => 'Tanggalin ang Lahat ng Recordings';

  @override
  String get deleteAll => 'Tanggalin Ang Lahat';

  @override
  String get deleteAllFilesWarning =>
      'Ito ay magtanggal ng parehong synced at pending recordings. Ang pending recordings ay HINDI nag-sync at permanent na mawawala. Hindi ito mababawi.';

  @override
  String get allFilesDeleted => 'Ang lahat ng recordings ay nakatanggal';

  @override
  String nFiles(int count) {
    return '$count recordings';
  }

  @override
  String get manageStorage => 'Pamahalaan ang Storage';

  @override
  String get safelyBackedUp => 'Safely backed up sa iyong phone';

  @override
  String get notYetSynced => 'Hindi pa nag-sync sa iyong phone';

  @override
  String get clearAll => 'Burahin Ang Lahat';

  @override
  String get phoneKeypad => 'Keypad';

  @override
  String get phoneHideKeypad => 'Itago ang Keypad';

  @override
  String get fairUsePolicy => 'Fair Use';

  @override
  String get fairUseLoadError => 'Hindi ma-load ang fair use status. Mangyaring subukan ulit.';

  @override
  String get fairUseStatusNormal => 'Ang iyong usage ay nasa loob ng normal limits.';

  @override
  String get fairUseStageNormal => 'Normal';

  @override
  String get fairUseStageWarning => 'Warning';

  @override
  String get fairUseStageThrottle => 'Throttled';

  @override
  String get fairUseStageRestrict => 'Restricted';

  @override
  String get fairUseSpeechUsage => 'Speech Usage';

  @override
  String get fairUseToday => 'Ngayong araw';

  @override
  String get fairUse3Day => '3-Day Rolling';

  @override
  String get fairUseWeekly => 'Weekly Rolling';

  @override
  String get fairUseAboutTitle => 'Tungkol sa Fair Use';

  @override
  String get fairUseAboutBody =>
      'Ang Omi ay dinisenyo para sa personal conversations, meetings, at live interactions. Ang usage ay sinusukat ng real speech time detected, hindi ang connection time. Kung ang usage ay significantly lumalampas sa normal patterns para sa non-personal content, ang mga adjustments ay maaaring mag-apply.';

  @override
  String fairUseCaseRefCopied(String caseRef) {
    return '$caseRef copied';
  }

  @override
  String get fairUseDailyTranscription => 'Daily Transcription';

  @override
  String fairUseBudgetUsed(String used, String limit) {
    return '${used}m / ${limit}m';
  }

  @override
  String get fairUseBudgetExhausted => 'Ang daily transcription limit ay naabot';

  @override
  String fairUseBudgetResetsAt(String time) {
    return 'Resets $time';
  }

  @override
  String get transcriptionPaused => 'Recording, muling kumokonekta';

  @override
  String get transcriptionPausedReconnecting => 'Patuloy na nag-record — muling kumokonekta sa transcription...';

  @override
  String fairUseBannerStatus(String status) {
    return 'Fair Use: $status';
  }

  @override
  String get improveConnectionTitle => 'Pagbutihin ang Connection';

  @override
  String get improveConnectionContent =>
      'Nag-improve kami ng kung paano ang Omi ay manatiling connected sa iyong device. Upang i-activate ito, mangyaring magpunta sa Device Info page, i-tap ang \"Disconnect Device\", at pagkatapos ay i-pair ang iyong device ulit.';

  @override
  String get improveConnectionAction => 'Nakaintindi';

  @override
  String clockSkewWarning(int minutes) {
    return 'Ang iyong device clock ay off ng ~$minutes min. Tingnan ang iyong date & time settings.';
  }

  @override
  String get omisStorage => 'Omi\'s Storage';

  @override
  String get phoneStorage => 'Phone Storage';

  @override
  String get cloudStorage => 'Cloud Storage';

  @override
  String get howSyncingWorks => 'Kung paano gumagana ang syncing';

  @override
  String get noSyncedRecordings => 'Walang synced recordings pa';

  @override
  String get recordingsSyncAutomatically => 'Ang recordings ay nag-sync automatically — walang kailangang aksyon.';

  @override
  String get filesDownloadedUploadedNextTime =>
      'Ang mga file na na-download na ay iu-upload sa susunod na pagkakataon.';

  @override
  String nConversationsCreated(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 's',
      one: '',
    );
    return '$count conversation$_temp0 na ginawa';
  }

  @override
  String get tapToView => 'I-tap upang tingnan';

  @override
  String get syncFailed => 'Ang sync ay nabigo';

  @override
  String get keepSyncing => 'Magpatuloy ng syncing';

  @override
  String get cancelSyncQuestion => 'Kanselahin ang sync?';

  @override
  String get omisStorageDesc =>
      'Kapag ang iyong Omi ay hindi konektado sa iyong phone, ito ay nag-store ng audio locally sa built-in memory nito. Hindi mo kailanman mawawalan ng recording.';

  @override
  String get phoneStorageDesc =>
      'Kapag muling kumokonekta ang Omi, ang mga recording ay automatic na inilipat sa iyong phone bilang isang temporary holding area bago i-upload.';

  @override
  String get cloudStorageDesc =>
      'Pagkatapos ng pag-upload, ang iyong mga recording ay pinoproseso at naitranscribe. Ang mga conversation ay magiging available sa loob ng isang minuto.';

  @override
  String get tipKeepPhoneNearby => 'Panatilihing malapit ang iyong phone para sa mas mabilis na syncing';

  @override
  String get tipStableInternet => 'Ang stable internet ay nagpapabilis ng cloud uploads';

  @override
  String get tipAutoSync => 'Ang mga recordings ay nag-sync automatically';

  @override
  String get storageSection => 'STORAGE';

  @override
  String get permissions => 'Permissions';

  @override
  String get permissionEnabled => 'Enabled';

  @override
  String get permissionEnable => 'I-enable';

  @override
  String get permissionsPageDescription =>
      'Ang mga permissions na ito ay core sa kung paano gumagana ang Omi. Pinapahintulutan nila ang mga key features tulad ng notifications, location-based experiences, at audio capture.';

  @override
  String get permissionsRequiredDescription =>
      'Ang Omi ay nangangailangan ng ilang permissions upang gumana nang maayos. Mangyaring bigyan ang mga ito upang magpatuloy.';

  @override
  String get permissionsSetupTitle => 'Makakuha ng pinakamahusay na experience';

  @override
  String get permissionsSetupDescription => 'I-enable ang ilang permissions upang ang Omi ay gumawa ng mahika.';

  @override
  String get permissionsChangeAnytime => 'Maaari mong baguhin ang mga ito anumang oras sa Settings > Permissions';

  @override
  String get location => 'Location';

  @override
  String get microphone => 'Microphone';

  @override
  String get whyAreYouCanceling => 'Bakit ka nagcancel?';

  @override
  String get cancelReasonSubtitle => 'Maaari mo ba kaming sabihin kung bakit ka umalis?';

  @override
  String get cancelReasonTooExpensive => 'Masyadong mahal';

  @override
  String get cancelReasonNotUsing => 'Hindi ko gamitin ang sapat';

  @override
  String get cancelReasonMissingFeatures => 'Nawawalang features';

  @override
  String get cancelReasonAudioQuality => 'Audio/transcription quality';

  @override
  String get cancelReasonBatteryDrain => 'Battery drain concerns';

  @override
  String get cancelReasonFoundAlternative => 'Nahanap ko ang isang alternatibo';

  @override
  String get cancelReasonOther => 'Iba';

  @override
  String get tellUsMore => 'Sabihin sa amin ng higit pa (optional)';

  @override
  String get cancelReasonDetailHint => 'Pinapahalagahan namin ang anumang feedback...';

  @override
  String get justAMoment => 'Isang sandali lamang';

  @override
  String get cancelConsequencesSubtitle =>
      'Lubos naming nirerekomenda na tuklasin ang iyong iba pang mga pagpipilian sa halip na magcancel.';

  @override
  String cancelBillingPeriodInfo(String date) {
    return 'Ang iyong plan ay manatiling active hanggang $date. Pagkatapos nito, ililitaw ka sa free version na may limited features.';
  }

  @override
  String get ifYouCancel => 'Kung magcancel ka:';

  @override
  String get cancelConsequenceNoAccess => 'Hindi na may unlimited access sa pagtatapos ng iyong billing period.';

  @override
  String get cancelConsequenceBattery => '7x higit pang battery usage (on-device processing)';

  @override
  String get cancelConsequenceQuality => '30% mas mababang transcription quality (on-device models)';

  @override
  String get cancelConsequenceDelay => '5-7 segundo processing delay (on-device models)';

  @override
  String get cancelConsequenceSpeakers => 'Hindi makakagawa ng identify sa mga speakers.';

  @override
  String get confirmAndCancel => 'Kumpirmahin & Magcancel';

  @override
  String get cancelConsequencePhoneCalls => 'Walang real-time phone call transcription';

  @override
  String get feedbackTitleTooExpensive => 'Anong presyo ang magiging okay sa iyo?';

  @override
  String get feedbackTitleMissingFeatures => 'Anong mga features ang nawawala mo?';

  @override
  String get feedbackTitleAudioQuality => 'Anong mga isyu ang naranasan mo?';

  @override
  String get feedbackTitleBatteryDrain => 'Sabihin sa amin tungkol sa battery issues';

  @override
  String get feedbackTitleFoundAlternative => 'Ano ang pinalipatan mo?';

  @override
  String get feedbackTitleNotUsing => 'Ano ang gagawing mas maraming gamit ang Omi?';

  @override
  String get feedbackSubtitleTooExpensive => 'Ang iyong feedback ay tumutulong sa amin na mahanap ang tamang balanse.';

  @override
  String get feedbackSubtitleMissingFeatures => 'Palagi kaming nagbubuo — ito ay tumutulong sa amin na mag-prioritize.';

  @override
  String get feedbackSubtitleAudioQuality => 'Gusto naming maintindihan kung ano ang napunta sa inaasahan.';

  @override
  String get feedbackSubtitleBatteryDrain => 'Ito ay tumutulong sa aming hardware team na mapabuti.';

  @override
  String get feedbackSubtitleFoundAlternative => 'Gusto naming malaman kung ano ang nakuha ng iyong atensyon.';

  @override
  String get feedbackSubtitleNotUsing => 'Gusto naming gawing mas kapaki-pakinabang ang Omi para sa iyo.';

  @override
  String get deviceDiagnostics => 'Device Diagnostics';

  @override
  String get signalStrength => 'Signal Strength';

  @override
  String get connectionUptime => 'Uptime';

  @override
  String get reconnections => 'Reconnections';

  @override
  String get disconnectHistory => 'Disconnect History';

  @override
  String get noDisconnectsRecorded => 'Walang disconnects na naitala';

  @override
  String get diagnostics => 'Diagnostics';

  @override
  String get waitingForData => 'Naghihintay ng data...';

  @override
  String get liveRssiOverTime => 'Live RSSI over time';

  @override
  String get noRssiDataYet => 'Walang RSSI data pa';

  @override
  String get collectingData => 'Nagkololekta ng data...';

  @override
  String get cleanDisconnect => 'Clean disconnect';

  @override
  String get connectionTimeout => 'Connection timeout';

  @override
  String get remoteDeviceTerminated => 'Remote device terminated';

  @override
  String get pairedToAnotherPhone => 'Paired sa ibang phone';

  @override
  String get linkKeyMismatch => 'Link key mismatch';

  @override
  String get connectionFailed => 'Connection failed';

  @override
  String get appClosed => 'App closed';

  @override
  String get manualDisconnect => 'Manual disconnect';

  @override
  String lastNEvents(int count) {
    return 'Huling $count events';
  }

  @override
  String get signal => 'Signal';

  @override
  String get battery => 'Battery';

  @override
  String get excellent => 'Excellent';

  @override
  String get good => 'Good';

  @override
  String get fair => 'Fair';

  @override
  String get weak => 'Weak';

  @override
  String gattError(String code) {
    return 'GATT error ($code)';
  }

  @override
  String get batteryHistory => 'Baterya';

  @override
  String get noBatteryDataYet => 'Wala pang datos ng baterya';

  @override
  String get day => 'Araw';

  @override
  String get week => 'Linggo';

  @override
  String get rollbackToStableFirmware => 'Bumalik sa Stable Firmware';

  @override
  String get rollbackConfirmTitle => 'Bumalik sa Firmware?';

  @override
  String rollbackConfirmMessage(String version) {
    return 'Ito ay papalitan ang iyong kasalukuyang firmware ng pinakabagong stable version ($version). Ang iyong device ay mag-restart pagkatapos ng update.';
  }

  @override
  String get stableFirmware => 'Stable Firmware';

  @override
  String get fetchingStableFirmware => 'Kukunin ang pinakabagong stable firmware...';

  @override
  String get noStableFirmwareFound => 'Hindi makaghanap ng stable firmware version para sa iyong device.';

  @override
  String get installStableFirmware => 'I-install ang Stable Firmware';

  @override
  String get alreadyOnStableFirmware => 'Ikaw ay nasa pinakabagong stable version na.';

  @override
  String audioSavedLocally(String duration) {
    return '$duration audio na nakatipid locally';
  }

  @override
  String get willSyncAutomatically => 'mag-sync automatically';

  @override
  String get enableLocationTitle => 'I-enable ang Location';

  @override
  String get enableLocationDescription =>
      'Ang location permission ay kailangan upang mahanap ang nearby Bluetooth devices.';

  @override
  String get voiceRecordingFound => 'Recording na nahanap';

  @override
  String get transcriptionConnecting => 'Kumokonekta sa transcription...';

  @override
  String get transcriptionReconnecting => 'Muling kumokonekta sa transcription...';

  @override
  String get transcriptionUnavailable => 'Transcription unavailable';

  @override
  String get audioOutput => 'Audio Output';

  @override
  String get firmwareWarningTitle => 'Mahalaga: Basahin Bago Mag-update';

  @override
  String get firmwareFormatWarning =>
      'Ang firmware na ito ay magfo-format ng SD card. Pakitiyak na ang lahat ng offline na data ay naka-sync bago mag-upgrade.\n\nKung makakita ka ng kumukurap na pulang ilaw pagkatapos i-install ang bersyong ito, huwag mag-alala. Ikonekta lang ang device sa app at dapat itong maging asul. Ang pulang ilaw ay nangangahulugang hindi pa na-sync ang orasan ng device.';

  @override
  String get continueAnyway => 'Magpatuloy';

  @override
  String get tasksClearCompleted => 'Linisin ang natapos';

  @override
  String get tasksSelectAll => 'Piliin lahat';

  @override
  String tasksDeleteSelected(int count) {
    return 'Burahin ang $count gawain';
  }

  @override
  String get tasksMarkComplete => 'Minarkahan bilang kumpleto';

  @override
  String get appleHealthManageNote =>
      'Ina-access ng Omi ang Apple Health sa pamamagitan ng HealthKit framework ng Apple. Maaari mong bawiin ang access anumang oras sa iOS Settings.';

  @override
  String get appleHealthConnectCta => 'Ikonekta sa Apple Health';

  @override
  String get appleHealthDisconnectCta => 'Idiskonekta ang Apple Health';

  @override
  String get appleHealthConnectedBadge => 'Nakakonekta';

  @override
  String get appleHealthFeatureChatTitle => 'Kumustahin ang iyong kalusugan';

  @override
  String get appleHealthFeatureChatDesc =>
      'Tanungin ang Omi tungkol sa iyong hakbang, tulog, tibok ng puso, at mga ehersisyo.';

  @override
  String get appleHealthFeatureReadOnlyTitle => 'Access na pambasa lamang';

  @override
  String get appleHealthFeatureReadOnlyDesc =>
      'Hindi kailanman nagsusulat ang Omi sa Apple Health o nagbabago ng iyong datos.';

  @override
  String get appleHealthFeatureSecureTitle => 'Ligtas na sync';

  @override
  String get appleHealthFeatureSecureDesc =>
      'Ang iyong datos sa Apple Health ay pribadong sinisync sa iyong Omi account.';

  @override
  String get appleHealthDeniedTitle => 'Tinanggihan ang access sa Apple Health';

  @override
  String get appleHealthDeniedBody =>
      'Walang pahintulot ang Omi na basahin ang iyong Apple Health data. I-enable ito sa iOS Settings → Privacy & Security → Health → Omi.';

  @override
  String get deleteFlowReasonTitle => 'Bakit ka aalis?';

  @override
  String get deleteFlowReasonSubtitle =>
      'Ang iyong feedback ay tumutulong sa amin na pagbutihin ang Omi para sa lahat.';

  @override
  String get deleteReasonPrivacy => 'Mga alalahanin sa privacy';

  @override
  String get deleteReasonNotUsing => 'Hindi sapat ang paggamit';

  @override
  String get deleteReasonMissingFeatures => 'Kulang sa mga feature na kailangan ko';

  @override
  String get deleteReasonTechnicalIssues => 'Masyadong maraming teknikal na problema';

  @override
  String get deleteReasonFoundAlternative => 'Gumagamit ng iba';

  @override
  String get deleteReasonTakingBreak => 'Nagpapahinga lang';

  @override
  String get deleteReasonOther => 'Iba pa';

  @override
  String get deleteFlowFeedbackTitle => 'Sabihin mo sa amin ang higit pa';

  @override
  String get deleteFlowFeedbackSubtitle => 'Ano ang magiging dahilan para gumana ang Omi para sa iyo?';

  @override
  String get deleteFlowFeedbackHint =>
      'Opsyonal — ang mga isip mo ay tumutulong sa amin na makabuo ng mas mahusay na produkto.';

  @override
  String get deleteFlowConfirmTitle => 'Ito ay permanente';

  @override
  String get deleteFlowConfirmSubtitle => 'Kapag na-delete mo na ang account mo, wala nang paraan para mabawi ito.';

  @override
  String get deleteConsequenceSubscription => 'Ang anumang aktibong subscription ay ikakansela.';

  @override
  String get deleteConsequenceNoRecovery => 'Hindi maibabalik ang iyong account — kahit ng support team.';

  @override
  String get deleteTypeToConfirm => 'I-type ang DELETE para kumpirmahin';

  @override
  String get deleteConfirmationWord => 'DELETE';

  @override
  String get deleteAccountPermanently => 'Tanggalin nang permanente ang account';

  @override
  String get keepMyAccount => 'Panatilihin ang aking account';

  @override
  String get deleteAccountFailed => 'Hindi ma-delete ang iyong account. Pakisubukan muli.';

  @override
  String get planUpdate => 'Update ng Plano';

  @override
  String get planDeprecationMessage =>
      'Ang iyong Unlimited na plano ay inihihinto na. Lumipat sa Operator na plano — parehong magagandang feature sa \$49/buwan. Ang kasalukuyan mong plano ay patuloy na gagana samantala.';

  @override
  String get upgradeYourPlan => 'I-upgrade ang Iyong Plano';

  @override
  String get youAreOnAPaidPlan => 'Ikaw ay nasa bayad na plano.';

  @override
  String get chatTitle => 'Chat';

  @override
  String get chatMessages => 'mensahe';

  @override
  String get unlimitedChatThisMonth => 'Walang limitasyon sa mensahe ngayong buwan';

  @override
  String chatUsedOfLimitCompute(String used, String limit) {
    return '$used sa $limit compute budget nagamit';
  }

  @override
  String chatUsedOfLimitMessages(String used, String limit) {
    return '$used sa $limit mensahe nagamit ngayong buwan';
  }

  @override
  String chatUsageProgress(String used, String limit) {
    return '$used / $limit nagamit';
  }

  @override
  String get chatLimitReachedUpgrade => 'Naabot na ang limitasyon ng chat. Mag-upgrade para sa mas maraming mensahe.';

  @override
  String get chatLimitReachedTitle => 'Naabot na ang limitasyon ng chat';

  @override
  String chatUsageDescription(String used, String limitDisplay, String plan) {
    return 'Ginamit mo na ang $used sa $limitDisplay sa $plan plan.';
  }

  @override
  String resetsInDays(int count) {
    return 'Magre-reset sa $count araw';
  }

  @override
  String resetsInHours(int count) {
    return 'Magre-reset sa $count oras';
  }

  @override
  String get resetsSoon => 'Magre-reset na';

  @override
  String get upgradePlan => 'I-upgrade ang plan';

  @override
  String get billingMonthly => 'Buwanan';

  @override
  String get billingYearly => 'Taunan';

  @override
  String get savePercent => 'Makatipid ~17%';

  @override
  String get popular => 'Sikat';

  @override
  String get currentPlan => 'Kasalukuyan';

  @override
  String neoSubtitle(int count) {
    return '$count tanong bawat buwan';
  }

  @override
  String operatorSubtitle(int count) {
    return '$count tanong bawat buwan';
  }

  @override
  String get architectSubtitle => 'Power-user AI — libu-libong chat + agentic automation';

  @override
  String chatUsageCost(String used, String limit) {
    return 'Chat: \$$used / \$$limit nagamit ngayong buwan';
  }

  @override
  String chatUsageCostNoLimit(String used) {
    return 'Chat: \$$used nagamit ngayong buwan';
  }

  @override
  String chatUsageMessages(String used, String limit) {
    return 'Chat: $used / $limit mensahe ngayong buwan';
  }

  @override
  String chatUsageMessagesNoLimit(String used) {
    return 'Chat: $used mensahe ngayong buwan';
  }

  @override
  String get chatQuotaSubtitle => 'AI chat messages used with Omi this month.';

  @override
  String get chatQuotaExceededReply =>
      'Naabot mo na ang iyong buwanang limitasyon. Mag-upgrade para magpatuloy ng chat sa Omi nang walang limitasyon.';

  @override
  String get voiceResponseAudio => 'Basahin nang malakas ang sagot ng Omi';

  @override
  String get voiceResponseMode => 'Tugon sa boses';

  @override
  String get voiceResponseModeTitle => 'Kailan bibigkasin ang tugon';

  @override
  String get voiceResponseOff => 'Naka-off';

  @override
  String get voiceResponseHeadphonesOnly => 'Headphones lang';

  @override
  String get voiceResponseAlways => 'Palagi';

  @override
  String get agreeAndContinue => 'Sumasang-ayon at Magpatuloy';

  @override
  String get startVoiceRecording => 'Simulan ang voice recording';

  @override
  String get startCallRecording => 'Simulan ang pag-record ng tawag';

  @override
  String get mindMap => 'Mind Map';

  @override
  String get voiceMode => 'Voice Mode';

  @override
  String get quickActionAskOmi => 'Tanungin si Omi ng kahit ano';

  @override
  String get record => 'Mag-record';

  @override
  String get stop => 'Itigil';

  @override
  String get recordWithPhoneMic => 'Mag-record gamit ang mikropono ng telepono';

  @override
  String get recordWithPhoneMicSubtitle => 'Kunan ang audio sa paligid mo';

  @override
  String get phoneCall => 'Tawag sa telepono';

  @override
  String get phoneCallSubtitle => 'Mag-record ng tawag na may live na transkripsyon';

  @override
  String get searchActionItems => 'Maghanap ng mga action item';

  @override
  String get selectActionItems => 'Pumili ng marami';

  @override
  String chooseExportDestination(int count) {
    return 'I-export ang $count item sa…';
  }

  @override
  String get bulkExportInProgress => 'Nag-e-export…';

  @override
  String bulkExportSuccess(int count, String platform) {
    return 'Na-export ang $count sa $platform';
  }

  @override
  String bulkExportPartial(int success, int total, String platform) {
    return 'Na-export ang $success sa $total sa $platform';
  }

  @override
  String get showCompletedTasks => 'Ipakita ang tapos na';

  @override
  String get hideCompletedTasks => 'Itago ang tapos na';

  @override
  String get selectAllTasksMenu => 'Piliin lahat';

  @override
  String get connectTaskAppToExport => 'Ikonekta ang isang task app sa Settings para mag-export';

  @override
  String get connectAction => 'Ikonekta';

  @override
  String get deselectAllTasksMenu => 'I-deselect lahat';
}
