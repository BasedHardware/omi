// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Malay (`ms`).
class AppLocalizationsMs extends AppLocalizations {
  AppLocalizationsMs([String locale = 'ms']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'Perbualan';

  @override
  String get transcriptTab => 'Transkrip';

  @override
  String get actionItemsTab => 'Item Tindakan';

  @override
  String get deleteConversationTitle => 'Padam Perbualan?';

  @override
  String get deleteConversationMessage =>
      'Adakah anda pasti mahu memadam perbualan ini? Tindakan ini tidak boleh dibatalkan.';

  @override
  String get confirm => 'Sahkan';

  @override
  String get cancel => 'Batal';

  @override
  String get ok => 'Ok';

  @override
  String get delete => 'Padam';

  @override
  String get add => 'Tambah';

  @override
  String get update => 'Kemas kini';

  @override
  String get save => 'Simpan';

  @override
  String get edit => 'Sunting';

  @override
  String get close => 'Tutup';

  @override
  String get clear => 'Kosongkan';

  @override
  String get copyTranscript => 'Salin transkrip';

  @override
  String get copySummary => 'Salin ringkasan';

  @override
  String get testPrompt => 'Uji Gesaan';

  @override
  String get reprocessConversation => 'Proses Semula Perbualan';

  @override
  String get deleteConversation => 'Padam Perbualan';

  @override
  String get contentCopied => 'Kandungan disalin ke papan keratan';

  @override
  String get failedToUpdateStarred => 'Gagal mengemas kini status bintang.';

  @override
  String get conversationUrlNotShared => 'URL perbualan tidak dapat dikongsi.';

  @override
  String get errorProcessingConversation => 'Ralat semasa memproses perbualan. Sila cuba lagi kemudian.';

  @override
  String get noInternetConnection => 'Tiada sambungan internet';

  @override
  String get unableToDeleteConversation => 'Tidak Dapat Memadam Perbualan';

  @override
  String get somethingWentWrong => 'Ada yang tidak kena! Sila cuba lagi kemudian.';

  @override
  String get copyErrorMessage => 'Salin mesej ralat';

  @override
  String get errorCopied => 'Mesej ralat disalin ke papan keratan';

  @override
  String get remaining => 'Berbaki';

  @override
  String get loading => 'Memuatkan...';

  @override
  String get loadingDuration => 'Memuatkan tempoh...';

  @override
  String secondsCount(int count) {
    return '$count saat';
  }

  @override
  String get people => 'Orang';

  @override
  String get addNewPerson => 'Tambah Orang Baharu';

  @override
  String get editPerson => 'Edit Orang';

  @override
  String get createPersonHint => 'Cipta orang baharu dan latih Omi untuk mengenali pertuturan mereka juga!';

  @override
  String get speechProfile => 'Profil Pertuturan';

  @override
  String sampleNumber(int number) {
    return 'Sampel $number';
  }

  @override
  String get settings => 'Tetapan';

  @override
  String get language => 'Bahasa';

  @override
  String get selectLanguage => 'Pilih Bahasa';

  @override
  String get deleting => 'Memadam...';

  @override
  String get pleaseCompleteAuthentication =>
      'Sila lengkapkan pengesahan dalam pelayar anda. Selepas selesai, kembali ke aplikasi.';

  @override
  String get failedToStartAuthentication => 'Gagal memulakan pengesahan';

  @override
  String get importStarted => 'Import bermula! Anda akan dimaklumkan apabila selesai.';

  @override
  String get failedToStartImport => 'Gagal memulakan import. Sila cuba lagi.';

  @override
  String get couldNotAccessFile => 'Tidak dapat mengakses fail yang dipilih';

  @override
  String get askOmi => 'Tanya Omi';

  @override
  String get done => 'Selesai';

  @override
  String get disconnected => 'Terputus sambungan';

  @override
  String get searching => 'Mencari...';

  @override
  String get connectDevice => 'Sambung Peranti';

  @override
  String get monthlyLimitReached => 'Anda telah mencapai had bulanan anda.';

  @override
  String get checkUsage => 'Semak Penggunaan';

  @override
  String get syncingRecordings => 'Menyegerakkan rakaman';

  @override
  String get recordingsToSync => 'Rakaman untuk disegerakkan';

  @override
  String get allCaughtUp => 'Semua telah dikemas kini';

  @override
  String get sync => 'Segerak';

  @override
  String get pendantUpToDate => 'Pendant adalah terkini';

  @override
  String get allRecordingsSynced => 'Semua rakaman telah disegerakkan';

  @override
  String get syncingInProgress => 'Penyegerakan sedang berlangsung';

  @override
  String get readyToSync => 'Sedia untuk disegerakkan';

  @override
  String get tapSyncToStart => 'Ketik Segerak untuk mula';

  @override
  String get pendantNotConnected => 'Pendant tidak disambungkan. Sambung untuk menyegerakkan.';

  @override
  String get everythingSynced => 'Semua telah disegerakkan.';

  @override
  String get recordingsNotSynced => 'Anda mempunyai rakaman yang belum disegerakkan lagi.';

  @override
  String get syncingBackground => 'Kami akan terus menyegerakkan rakaman anda di latar belakang.';

  @override
  String get noConversationsYet => 'Belum ada perbualan lagi';

  @override
  String get noStarredConversations => 'Tiada perbualan berbintang';

  @override
  String get starConversationHint => 'Untuk membintangkan perbualan, buka dan ketik ikon bintang di pengepala.';

  @override
  String get searchConversations => 'Cari perbualan...';

  @override
  String selectedCount(int count, Object s) {
    return '$count dipilih';
  }

  @override
  String get merge => 'Gabung';

  @override
  String get mergeConversations => 'Gabungkan Perbualan';

  @override
  String mergeConversationsMessage(int count) {
    return 'Ini akan menggabungkan $count perbualan menjadi satu. Semua kandungan akan digabungkan dan dijana semula.';
  }

  @override
  String get mergingInBackground => 'Menggabungkan di latar belakang. Ini mungkin mengambil sedikit masa.';

  @override
  String get failedToStartMerge => 'Gagal memulakan penggabungan';

  @override
  String get askAnything => 'Tanya apa sahaja';

  @override
  String get noMessagesYet => 'Tiada mesej lagi!\nMengapa tidak mulakan perbualan?';

  @override
  String get deletingMessages => 'Memadam mesej anda dari ingatan Omi...';

  @override
  String get messageCopied => '✨ Mesej disalin ke papan keratan';

  @override
  String get cannotReportOwnMessage => 'Anda tidak boleh melaporkan mesej anda sendiri.';

  @override
  String get reportMessage => 'Laporkan Mesej';

  @override
  String get reportMessageConfirm => 'Adakah anda pasti mahu melaporkan mesej ini?';

  @override
  String get messageReported => 'Mesej berjaya dilaporkan.';

  @override
  String get thankYouFeedback => 'Terima kasih atas maklum balas anda!';

  @override
  String get clearChat => 'Padam Sembang';

  @override
  String get clearChatConfirm => 'Adakah anda pasti mahu mengosongkan sembang? Tindakan ini tidak boleh dibatalkan.';

  @override
  String get maxFilesLimit => 'Anda hanya boleh memuat naik 4 fail pada satu masa';

  @override
  String get chatWithOmi => 'Sembang dengan Omi';

  @override
  String get apps => 'Aplikasi';

  @override
  String get noAppsFound => 'Tiada apl ditemui';

  @override
  String get tryAdjustingSearch => 'Cuba laraskan carian atau penapis anda';

  @override
  String get createYourOwnApp => 'Cipta Aplikasi Anda Sendiri';

  @override
  String get buildAndShareApp => 'Bina dan kongsi aplikasi tersuai anda';

  @override
  String get searchApps => 'Cari apl...';

  @override
  String get myApps => 'Aplikasi Saya';

  @override
  String get installedApps => 'Aplikasi Dipasang';

  @override
  String get unableToFetchApps =>
      'Tidak dapat mendapatkan aplikasi :(\n\nSila semak sambungan internet anda dan cuba lagi.';

  @override
  String get aboutOmi => 'Tentang Omi';

  @override
  String get privacyPolicy => 'Dasar Privasi';

  @override
  String get visitWebsite => 'Lawati Laman Web';

  @override
  String get helpOrInquiries => 'Bantuan atau Pertanyaan?';

  @override
  String get joinCommunity => 'Sertai komuniti!';

  @override
  String get membersAndCounting => '8000+ ahli dan terus bertambah.';

  @override
  String get deleteAccountTitle => 'Padam Akaun';

  @override
  String get deleteAccountConfirm => 'Adakah anda pasti mahu memadam akaun anda?';

  @override
  String get cannotBeUndone => 'Ini tidak boleh dibatalkan.';

  @override
  String get allDataErased => 'Semua ingatan dan perbualan anda akan dipadam secara kekal.';

  @override
  String get appsDisconnected => 'Aplikasi dan Integrasi anda akan diputuskan sambungan dengan serta-merta.';

  @override
  String get exportBeforeDelete =>
      'Anda boleh mengeksport data anda sebelum memadam akaun anda, tetapi setelah dipadam, ia tidak boleh dipulihkan.';

  @override
  String get deleteAccountCheckbox =>
      'Saya faham bahawa memadam akaun saya adalah kekal dan semua data, termasuk ingatan dan perbualan, akan hilang dan tidak boleh dipulihkan.';

  @override
  String get areYouSure => 'Adakah anda pasti?';

  @override
  String get deleteAccountFinal =>
      'Tindakan ini tidak boleh diterbalikkan dan akan memadam akaun anda dan semua data berkaitan secara kekal. Adakah anda pasti mahu meneruskan?';

  @override
  String get deleteNow => 'Padam Sekarang';

  @override
  String get goBack => 'Kembali';

  @override
  String get checkBoxToConfirm =>
      'Tandakan kotak untuk mengesahkan anda faham bahawa memadam akaun anda adalah kekal dan tidak boleh diterbalikkan.';

  @override
  String get profile => 'Profil';

  @override
  String get name => 'Nama';

  @override
  String get email => 'E-mel';

  @override
  String get customVocabulary => 'Perbendaharaan Kata Tersuai';

  @override
  String get identifyingOthers => 'Mengenalpasti Orang Lain';

  @override
  String get paymentMethods => 'Kaedah Pembayaran';

  @override
  String get conversationDisplay => 'Paparan Perbualan';

  @override
  String get dataPrivacy => 'Privasi Data';

  @override
  String get userId => 'ID Pengguna';

  @override
  String get notSet => 'Tidak ditetapkan';

  @override
  String get userIdCopied => 'ID Pengguna disalin ke papan keratan';

  @override
  String get systemDefault => 'Lalai Sistem';

  @override
  String get planAndUsage => 'Pelan & Penggunaan';

  @override
  String get offlineSync => 'Segerak Luar Talian';

  @override
  String get deviceSettings => 'Tetapan Peranti';

  @override
  String get integrations => 'Integrasi';

  @override
  String get feedbackBug => 'Maklum Balas / Pepijat';

  @override
  String get helpCenter => 'Pusat Bantuan';

  @override
  String get developerSettings => 'Tetapan Pembangun';

  @override
  String get getOmiForMac => 'Dapatkan Omi untuk Mac';

  @override
  String get referralProgram => 'Program Rujukan';

  @override
  String get signOut => 'Log Keluar';

  @override
  String get appAndDeviceCopied => 'Butiran aplikasi dan peranti disalin';

  @override
  String get wrapped2025 => 'Rumusan 2025';

  @override
  String get yourPrivacyYourControl => 'Privasi Anda, Kawalan Anda';

  @override
  String get privacyIntro =>
      'Di Omi, kami komited untuk melindungi privasi anda. Halaman ini membolehkan anda mengawal cara data anda disimpan dan digunakan.';

  @override
  String get learnMore => 'Ketahui lebih lanjut...';

  @override
  String get dataProtectionLevel => 'Tahap Perlindungan Data';

  @override
  String get dataProtectionDesc =>
      'Data anda dijamin secara lalai dengan penyulitan yang kukuh. Semak tetapan dan pilihan privasi masa depan anda di bawah.';

  @override
  String get appAccess => 'Akses Aplikasi';

  @override
  String get appAccessDesc =>
      'Aplikasi berikut boleh mengakses data anda. Ketik pada aplikasi untuk mengurus keizinannya.';

  @override
  String get noAppsExternalAccess => 'Tiada aplikasi yang dipasang mempunyai akses luaran ke data anda.';

  @override
  String get deviceName => 'Nama Peranti';

  @override
  String get deviceId => 'ID Peranti';

  @override
  String get firmware => 'Perisian Tegar';

  @override
  String get sdCardSync => 'Sinkronisasi Kad SD';

  @override
  String get hardwareRevision => 'Semakan Perkakasan';

  @override
  String get modelNumber => 'Nombor Model';

  @override
  String get manufacturer => 'Pengeluar';

  @override
  String get doubleTap => 'Ketik Dua Kali';

  @override
  String get ledBrightness => 'Kecerahan LED';

  @override
  String get micGain => 'Gandaan Mikrofon';

  @override
  String get disconnect => 'Putuskan Sambungan';

  @override
  String get forgetDevice => 'Lupakan Peranti';

  @override
  String get chargingIssues => 'Masalah Pengecasan';

  @override
  String get disconnectDevice => 'Putuskan Sambungan Peranti';

  @override
  String get unpairDevice => 'Nyahpasangkan Peranti';

  @override
  String get unpairAndForget => 'Nyahpasang dan Lupakan Peranti';

  @override
  String get deviceDisconnectedMessage => 'Omi anda telah diputuskan sambungan 😔';

  @override
  String get deviceUnpairedMessage =>
      'Peranti dinyahpasangkan. Pergi ke Tetapan > Bluetooth dan lupakan peranti untuk melengkapkan penyahpasangan.';

  @override
  String get unpairDialogTitle => 'Nyahpasang Peranti';

  @override
  String get unpairDialogMessage =>
      'Ini akan menyahpasangkan peranti supaya ia boleh disambungkan ke telefon lain. Anda perlu pergi ke Tetapan > Bluetooth dan lupakan peranti untuk melengkapkan proses.';

  @override
  String get deviceNotConnected => 'Peranti Tidak Disambungkan';

  @override
  String get connectDeviceMessage => 'Sambungkan peranti Omi anda untuk mengakses\ntetapan peranti dan penyesuaian';

  @override
  String get deviceInfoSection => 'Maklumat Peranti';

  @override
  String get customizationSection => 'Penyesuaian';

  @override
  String get hardwareSection => 'Perkakasan';

  @override
  String get v2Undetected => 'V2 tidak dikesan';

  @override
  String get v2UndetectedMessage =>
      'Kami lihat anda sama ada mempunyai peranti V1 atau peranti anda tidak disambungkan. Fungsi Kad SD hanya tersedia untuk peranti V2.';

  @override
  String get endConversation => 'Tamatkan Perbualan';

  @override
  String get pauseResume => 'Jeda/Sambung Semula';

  @override
  String get starConversation => 'Bintangkan Perbualan';

  @override
  String get doubleTapAction => 'Tindakan Ketik Dua Kali';

  @override
  String get endAndProcess => 'Tamatkan & Proses Perbualan';

  @override
  String get pauseResumeRecording => 'Jeda/Sambung Semula Rakaman';

  @override
  String get starOngoing => 'Bintangkan Perbualan Berterusan';

  @override
  String get off => 'Mati';

  @override
  String get max => 'Maksimum';

  @override
  String get mute => 'Bisukan';

  @override
  String get quiet => 'Senyap';

  @override
  String get normal => 'Biasa';

  @override
  String get high => 'Tinggi';

  @override
  String get micGainDescMuted => 'Mikrofon dibisukan';

  @override
  String get micGainDescLow => 'Sangat senyap - untuk persekitaran bising';

  @override
  String get micGainDescModerate => 'Senyap - untuk bunyi sederhana';

  @override
  String get micGainDescNeutral => 'Neutral - rakaman seimbang';

  @override
  String get micGainDescSlightlyBoosted => 'Dipertingkat sedikit - penggunaan biasa';

  @override
  String get micGainDescBoosted => 'Dipertingkat - untuk persekitaran senyap';

  @override
  String get micGainDescHigh => 'Tinggi - untuk suara jauh atau lembut';

  @override
  String get micGainDescVeryHigh => 'Sangat tinggi - untuk sumber sangat senyap';

  @override
  String get micGainDescMax => 'Maksimum - gunakan dengan berhati-hati';

  @override
  String get developerSettingsTitle => 'Tetapan Pembangun';

  @override
  String get saving => 'Menyimpan...';

  @override
  String get personaConfig => 'Konfigurasikan persona AI anda';

  @override
  String get beta => 'BETA';

  @override
  String get transcription => 'Transkripsi';

  @override
  String get transcriptionConfig => 'Konfigurasikan penyedia STT';

  @override
  String get conversationTimeout => 'Tamat Masa Perbualan';

  @override
  String get conversationTimeoutConfig => 'Tetapkan bila perbualan tamat secara automatik';

  @override
  String get importData => 'Import Data';

  @override
  String get importDataConfig => 'Import data dari sumber lain';

  @override
  String get debugDiagnostics => 'Nyahpepijat & Diagnostik';

  @override
  String get endpointUrl => 'URL Titik Akhir';

  @override
  String get noApiKeys => 'Tiada kunci API lagi';

  @override
  String get createKeyToStart => 'Cipta kunci untuk bermula';

  @override
  String get createKey => 'Cipta Kunci';

  @override
  String get docs => 'Dokumentasi';

  @override
  String get yourOmiInsights => 'Wawasan Omi Anda';

  @override
  String get today => 'Hari ini';

  @override
  String get thisMonth => 'Bulan Ini';

  @override
  String get thisYear => 'Tahun Ini';

  @override
  String get allTime => 'Sepanjang Masa';

  @override
  String get noActivityYet => 'Tiada Aktiviti Lagi';

  @override
  String get startConversationToSeeInsights =>
      'Mulakan perbualan dengan Omi\nuntuk melihat wawasan penggunaan anda di sini.';

  @override
  String get listening => 'Mendengar';

  @override
  String get listeningSubtitle => 'Jumlah masa Omi telah mendengar secara aktif.';

  @override
  String get understanding => 'Memahami';

  @override
  String get understandingSubtitle => 'Perkataan yang difahami daripada perbualan anda.';

  @override
  String get providing => 'Menyediakan';

  @override
  String get providingSubtitle => 'Item tindakan dan nota ditangkap secara automatik.';

  @override
  String get remembering => 'Mengingati';

  @override
  String get rememberingSubtitle => 'Fakta dan butiran diingati untuk anda.';

  @override
  String get unlimitedPlan => 'Pelan Tanpa Had';

  @override
  String get managePlan => 'Urus Pelan';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'Pelan anda akan dibatalkan pada $date.';
  }

  @override
  String renewsOn(String date) {
    return 'Pelan anda diperbaharui pada $date.';
  }

  @override
  String get basicPlan => 'Pelan Percuma';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used daripada $limit minit digunakan';
  }

  @override
  String get upgrade => 'Naik Taraf';

  @override
  String get upgradeToUnlimited => 'Naik taraf kepada tanpa had';

  @override
  String basicPlanDesc(int limit) {
    return 'Pelan anda termasuk $limit minit percuma sebulan. Naik taraf untuk tanpa had.';
  }

  @override
  String get shareStatsMessage => 'Berkongsi statistik Omi saya! (omi.me - pembantu AI anda yang sentiasa aktif)';

  @override
  String get sharePeriodToday => 'Hari ini, omi telah:';

  @override
  String get sharePeriodMonth => 'Bulan ini, omi telah:';

  @override
  String get sharePeriodYear => 'Tahun ini, omi telah:';

  @override
  String get sharePeriodAllTime => 'Setakat ini, omi telah:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 Mendengar selama $minutes minit';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 Memahami $words perkataan';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ Menyediakan $count wawasan';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 Mengingati $count ingatan';
  }

  @override
  String get debugLogs => 'Log Nyahpepijat';

  @override
  String get debugLogsAutoDelete => 'Auto-padam selepas 3 hari.';

  @override
  String get debugLogsDesc => 'Membantu mendiagnosis masalah';

  @override
  String get noLogFilesFound => 'Tiada fail log ditemui.';

  @override
  String get omiDebugLog => 'Log nyahpepijat Omi';

  @override
  String get logShared => 'Log dikongsi';

  @override
  String get selectLogFile => 'Pilih Fail Log';

  @override
  String get shareLogs => 'Kongsi Log';

  @override
  String get debugLogCleared => 'Log nyahpepijat dikosongkan';

  @override
  String get exportStarted => 'Eksport bermula. Ini mungkin mengambil beberapa saat...';

  @override
  String get exportAllData => 'Eksport Semua Data';

  @override
  String get exportDataDesc => 'Eksport perbualan ke fail JSON';

  @override
  String get exportedConversations => 'Perbualan Dieksport daripada Omi';

  @override
  String get exportShared => 'Eksport dikongsi';

  @override
  String get deleteKnowledgeGraphTitle => 'Padam Graf Pengetahuan?';

  @override
  String get deleteKnowledgeGraphMessage =>
      'Ini akan memadam semua data graf pengetahuan terbitan (nod dan sambungan). Ingatan asal anda akan kekal selamat. Graf akan dibina semula dari semasa ke semasa atau atas permintaan seterusnya.';

  @override
  String get knowledgeGraphDeleted => 'Graf pengetahuan dipadamkan';

  @override
  String deleteGraphFailed(String error) {
    return 'Gagal memadam graf: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'Padam Graf Pengetahuan';

  @override
  String get deleteKnowledgeGraphDesc => 'Kosongkan semua nod dan sambungan';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'Pelayan MCP';

  @override
  String get mcpServerDesc => 'Sambungkan pembantu AI ke data anda';

  @override
  String get serverUrl => 'URL Pelayan';

  @override
  String get urlCopied => 'URL disalin';

  @override
  String get apiKeyAuth => 'Pengesahan Kunci API';

  @override
  String get header => 'Pengepala';

  @override
  String get authorizationBearer => 'Kebenaran: Bearer <kunci>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'ID Klien';

  @override
  String get clientSecret => 'Rahsia Klien';

  @override
  String get useMcpApiKey => 'Gunakan kunci API MCP anda';

  @override
  String get webhooks => 'Webhooks';

  @override
  String get conversationEvents => 'Acara Perbualan';

  @override
  String get newConversationCreated => 'Perbualan baharu dicipta';

  @override
  String get realtimeTranscript => 'Transkrip Masa Nyata';

  @override
  String get transcriptReceived => 'Transkrip diterima';

  @override
  String get audioBytes => 'Bait Audio';

  @override
  String get audioDataReceived => 'Data audio diterima';

  @override
  String get intervalSeconds => 'Selang (saat)';

  @override
  String get daySummary => 'Ringkasan Hari';

  @override
  String get summaryGenerated => 'Ringkasan dijana';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'Tambah ke claude_desktop_config.json';

  @override
  String get copyConfig => 'Salin Konfigurasi';

  @override
  String get configCopied => 'Konfigurasi disalin ke papan keratan';

  @override
  String get listeningMins => 'Mendengar (minit)';

  @override
  String get understandingWords => 'Memahami (perkataan)';

  @override
  String get insights => 'Wawasan';

  @override
  String get memories => 'Kenangan';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '$used daripada $limit minit digunakan bulan ini';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '$used daripada $limit perkataan digunakan bulan ini';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '$used daripada $limit wawasan diperoleh bulan ini';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return '$used daripada $limit ingatan dicipta bulan ini';
  }

  @override
  String get visibility => 'Keterlihatan';

  @override
  String get visibilitySubtitle => 'Kawal perbualan mana yang muncul dalam senarai anda';

  @override
  String get showShortConversations => 'Tunjukkan Perbualan Pendek';

  @override
  String get showShortConversationsDesc => 'Paparkan perbualan yang lebih pendek daripada ambang';

  @override
  String get showDiscardedConversations => 'Tunjukkan Perbualan Dibuang';

  @override
  String get showDiscardedConversationsDesc => 'Sertakan perbualan yang ditandakan sebagai dibuang';

  @override
  String get shortConversationThreshold => 'Ambang Perbualan Pendek';

  @override
  String get shortConversationThresholdSubtitle =>
      'Perbualan yang lebih pendek daripada ini akan disembunyikan melainkan didayakan di atas';

  @override
  String get durationThreshold => 'Ambang Tempoh';

  @override
  String get durationThresholdDesc => 'Sembunyikan perbualan yang lebih pendek daripada ini';

  @override
  String minLabel(int count) {
    return '$count min';
  }

  @override
  String get customVocabularyTitle => 'Perbendaharaan Kata Tersuai';

  @override
  String get addWords => 'Tambah Perkataan';

  @override
  String get addWordsDesc => 'Nama, istilah, atau perkataan luar biasa';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'Connect';

  @override
  String get comingSoon => 'Akan Datang';

  @override
  String get integrationsFooter => 'Sambungkan aplikasi anda untuk melihat data dan metrik dalam sembang.';

  @override
  String get completeAuthInBrowser =>
      'Sila lengkapkan pengesahan dalam pelayar anda. Selepas selesai, kembali ke aplikasi.';

  @override
  String failedToStartAuth(String appName) {
    return 'Gagal memulakan pengesahan $appName';
  }

  @override
  String disconnectAppTitle(String appName) {
    return 'Putuskan sambungan $appName?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'Adakah anda pasti mahu memutuskan sambungan dari $appName? Anda boleh menyambung semula bila-bila masa.';
  }

  @override
  String disconnectedFrom(String appName) {
    return 'Terputus sambungan dari $appName';
  }

  @override
  String get failedToDisconnect => 'Gagal memutuskan sambungan';

  @override
  String connectTo(String appName) {
    return 'Sambung ke $appName';
  }

  @override
  String authAccessMessage(String appName) {
    return 'Anda perlu memberi kebenaran kepada Omi untuk mengakses data $appName anda. Ini akan membuka pelayar anda untuk pengesahan.';
  }

  @override
  String get continueAction => 'Teruskan';

  @override
  String get languageTitle => 'Bahasa';

  @override
  String get primaryLanguage => 'Bahasa Utama';

  @override
  String get automaticTranslation => 'Terjemahan Automatik';

  @override
  String get detectLanguages => 'Kesan 10+ bahasa';

  @override
  String get authorizeSavingRecordings => 'Benarkan Menyimpan Rakaman';

  @override
  String get thanksForAuthorizing => 'Terima kasih kerana memberi kebenaran!';

  @override
  String get needYourPermission => 'Kami memerlukan kebenaran anda';

  @override
  String get alreadyGavePermission =>
      'Anda telah memberi kami kebenaran untuk menyimpan rakaman anda. Berikut adalah peringatan mengapa kami memerlukannya:';

  @override
  String get wouldLikePermission => 'Kami ingin kebenaran anda untuk menyimpan rakaman suara anda. Sebabnya:';

  @override
  String get improveSpeechProfile => 'Tingkatkan Profil Pertuturan Anda';

  @override
  String get improveSpeechProfileDesc =>
      'Kami menggunakan rakaman untuk melatih dan meningkatkan profil pertuturan peribadi anda.';

  @override
  String get trainFamilyProfiles => 'Latih Profil untuk Rakan dan Keluarga';

  @override
  String get trainFamilyProfilesDesc =>
      'Rakaman anda membantu kami mengenali dan mencipta profil untuk rakan dan keluarga anda.';

  @override
  String get enhanceTranscriptAccuracy => 'Tingkatkan Ketepatan Transkrip';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'Apabila model kami bertambah baik, kami boleh memberikan hasil transkripsi yang lebih baik untuk rakaman anda.';

  @override
  String get legalNotice =>
      'Notis Undang-undang: Kesahihan merakam dan menyimpan data suara mungkin berbeza bergantung pada lokasi anda dan cara anda menggunakan ciri ini. Adalah tanggungjawab anda untuk memastikan pematuhan undang-undang dan peraturan tempatan.';

  @override
  String get alreadyAuthorized => 'Sudah Dibenarkan';

  @override
  String get authorize => 'Benarkan';

  @override
  String get revokeAuthorization => 'Batalkan Kebenaran';

  @override
  String get authorizationSuccessful => 'Kebenaran berjaya!';

  @override
  String get failedToAuthorize => 'Gagal memberi kebenaran. Sila cuba lagi.';

  @override
  String get authorizationRevoked => 'Kebenaran dibatalkan.';

  @override
  String get recordingsDeleted => 'Rakaman dipadam.';

  @override
  String get failedToRevoke => 'Gagal membatalkan kebenaran. Sila cuba lagi.';

  @override
  String get permissionRevokedTitle => 'Kebenaran Dibatalkan';

  @override
  String get permissionRevokedMessage => 'Adakah anda mahu kami membuang semua rakaman sedia ada anda juga?';

  @override
  String get yes => 'Ya';

  @override
  String get editName => 'Sunting Nama';

  @override
  String get howShouldOmiCallYou => 'Apa yang Omi patut panggil anda?';

  @override
  String get enterYourName => 'Masukkan nama anda';

  @override
  String get nameCannotBeEmpty => 'Nama tidak boleh kosong';

  @override
  String get nameUpdatedSuccessfully => 'Nama berjaya dikemas kini!';

  @override
  String get calendarSettings => 'Tetapan kalendar';

  @override
  String get calendarProviders => 'Penyedia Kalendar';

  @override
  String get macOsCalendar => 'Kalendar macOS';

  @override
  String get connectMacOsCalendar => 'Sambungkan kalendar macOS tempatan anda';

  @override
  String get googleCalendar => 'Kalendar Google';

  @override
  String get syncGoogleAccount => 'Segerakkan dengan akaun Google anda';

  @override
  String get showMeetingsMenuBar => 'Tunjukkan mesyuarat akan datang di bar menu';

  @override
  String get showMeetingsMenuBarDesc =>
      'Paparkan mesyuarat seterusnya anda dan masa sehingga ia bermula di bar menu macOS';

  @override
  String get showEventsNoParticipants => 'Tunjukkan acara tanpa peserta';

  @override
  String get showEventsNoParticipantsDesc =>
      'Apabila didayakan, Coming Up menunjukkan acara tanpa peserta atau pautan video.';

  @override
  String get yourMeetings => 'Mesyuarat Anda';

  @override
  String get refresh => 'Muat Semula';

  @override
  String get noUpcomingMeetings => 'Tiada mesyuarat akan datang';

  @override
  String get checkingNextDays => 'Menyemak 30 hari akan datang';

  @override
  String get tomorrow => 'Esok';

  @override
  String get googleCalendarComingSoon => 'Integrasi Google Calendar akan datang!';

  @override
  String connectedAsUser(String userId) {
    return 'Disambungkan sebagai pengguna: $userId';
  }

  @override
  String get defaultWorkspace => 'Ruang Kerja Lalai';

  @override
  String get tasksCreatedInWorkspace => 'Tugasan akan dicipta dalam ruang kerja ini';

  @override
  String get defaultProjectOptional => 'Projek Lalai (Pilihan)';

  @override
  String get leaveUnselectedTasks => 'Biarkan tidak dipilih untuk mencipta tugasan tanpa projek';

  @override
  String get noProjectsInWorkspace => 'Tiada projek dijumpai dalam ruang kerja ini';

  @override
  String get conversationTimeoutDesc =>
      'Pilih berapa lama untuk menunggu dalam senyap sebelum menamatkan perbualan secara automatik:';

  @override
  String get timeout2Minutes => '2 minit';

  @override
  String get timeout2MinutesDesc => 'Tamatkan perbualan selepas 2 minit senyap';

  @override
  String get timeout5Minutes => '5 minit';

  @override
  String get timeout5MinutesDesc => 'Tamatkan perbualan selepas 5 minit senyap';

  @override
  String get timeout10Minutes => '10 minit';

  @override
  String get timeout10MinutesDesc => 'Tamatkan perbualan selepas 10 minit senyap';

  @override
  String get timeout30Minutes => '30 minit';

  @override
  String get timeout30MinutesDesc => 'Tamatkan perbualan selepas 30 minit senyap';

  @override
  String get timeout4Hours => '4 jam';

  @override
  String get timeout4HoursDesc => 'Tamatkan perbualan selepas 4 jam senyap';

  @override
  String get conversationEndAfterHours => 'Perbualan akan tamat selepas 4 jam senyap';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Perbualan akan tamat selepas $minutes minit senyap';
  }

  @override
  String get tellUsPrimaryLanguage => 'Beritahu kami bahasa utama anda';

  @override
  String get languageForTranscription =>
      'Tetapkan bahasa anda untuk transkripsi yang lebih tajam dan pengalaman yang diperibadikan.';

  @override
  String get singleLanguageModeInfo =>
      'Mod Bahasa Tunggal didayakan. Terjemahan dilumpuhkan untuk ketepatan yang lebih tinggi.';

  @override
  String get searchLanguageHint => 'Cari bahasa mengikut nama atau kod';

  @override
  String get noLanguagesFound => 'Tiada bahasa ditemui';

  @override
  String get skip => 'Langkau';

  @override
  String languageSetTo(String language) {
    return 'Bahasa ditetapkan kepada $language';
  }

  @override
  String get failedToSetLanguage => 'Gagal menetapkan bahasa';

  @override
  String appSettings(String appName) {
    return 'Tetapan $appName';
  }

  @override
  String disconnectFromApp(String appName) {
    return 'Putuskan sambungan dari $appName?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'Ini akan membuang pengesahan $appName anda. Anda perlu menyambung semula untuk menggunakannya lagi.';
  }

  @override
  String connectedToApp(String appName) {
    return 'Disambungkan ke $appName';
  }

  @override
  String get account => 'Akaun';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Item tindakan anda akan disegerakkan ke akaun $appName anda';
  }

  @override
  String get defaultSpace => 'Ruang Lalai';

  @override
  String get selectSpaceInWorkspace => 'Pilih ruang dalam ruang kerja anda';

  @override
  String get noSpacesInWorkspace => 'Tiada ruang dijumpai dalam ruang kerja ini';

  @override
  String get defaultList => 'Senarai Lalai';

  @override
  String get tasksAddedToList => 'Tugasan akan ditambah ke senarai ini';

  @override
  String get noListsInSpace => 'Tiada senarai dijumpai dalam ruang ini';

  @override
  String failedToLoadRepos(String error) {
    return 'Gagal memuatkan repositori: $error';
  }

  @override
  String get defaultRepoSaved => 'Repositori lalai disimpan';

  @override
  String get failedToSaveDefaultRepo => 'Gagal menyimpan repositori lalai';

  @override
  String get defaultRepository => 'Repositori Lalai';

  @override
  String get selectDefaultRepoDesc =>
      'Pilih repositori lalai untuk mencipta isu. Anda masih boleh menyatakan repositori yang berbeza semasa mencipta isu.';

  @override
  String get noReposFound => 'Tiada repositori dijumpai';

  @override
  String get private => 'Peribadi';

  @override
  String updatedDate(String date) {
    return 'Dikemas kini $date';
  }

  @override
  String get yesterday => 'Semalam';

  @override
  String daysAgo(int count) {
    return '$count hari yang lalu';
  }

  @override
  String get oneWeekAgo => '1 minggu yang lalu';

  @override
  String weeksAgo(int count) {
    return '$count minggu yang lalu';
  }

  @override
  String get oneMonthAgo => '1 bulan yang lalu';

  @override
  String monthsAgo(int count) {
    return '$count bulan yang lalu';
  }

  @override
  String get issuesCreatedInRepo => 'Isu akan dicipta dalam repositori lalai anda';

  @override
  String get taskIntegrations => 'Integrasi Tugasan';

  @override
  String get configureSettings => 'Konfigurasikan Tetapan';

  @override
  String get completeAuthBrowser =>
      'Sila lengkapkan pengesahan dalam pelayar anda. Selepas selesai, kembali ke aplikasi.';

  @override
  String failedToStartAppAuth(String appName) {
    return 'Gagal memulakan pengesahan $appName';
  }

  @override
  String connectToAppTitle(String appName) {
    return 'Sambung ke $appName';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Anda perlu memberi kebenaran kepada Omi untuk mencipta tugasan dalam akaun $appName anda. Ini akan membuka pelayar anda untuk pengesahan.';
  }

  @override
  String get continueButton => 'Teruskan';

  @override
  String appIntegration(String appName) {
    return 'Integrasi $appName';
  }

  @override
  String integrationComingSoon(String appName) {
    return 'Integrasi dengan $appName akan datang! Kami bekerja keras untuk membawa anda lebih banyak pilihan pengurusan tugasan.';
  }

  @override
  String get gotIt => 'Faham';

  @override
  String get tasksExportedOneApp => 'Tugasan boleh dieksport ke satu aplikasi pada satu masa.';

  @override
  String get completeYourUpgrade => 'Lengkapkan Naik Taraf Anda';

  @override
  String get importConfiguration => 'Import Konfigurasi';

  @override
  String get exportConfiguration => 'Eksport konfigurasi';

  @override
  String get bringYourOwn => 'Bawa milik anda sendiri';

  @override
  String get payYourSttProvider => 'Gunakan omi secara bebas. Anda hanya membayar penyedia STT anda secara langsung.';

  @override
  String get freeMinutesMonth => '1,200 minit percuma/bulan disertakan. Tanpa had dengan ';

  @override
  String get omiUnlimited => 'Omi Tanpa Had';

  @override
  String get hostRequired => 'Hos diperlukan';

  @override
  String get validPortRequired => 'Port yang sah diperlukan';

  @override
  String get validWebsocketUrlRequired => 'URL WebSocket yang sah diperlukan (wss://)';

  @override
  String get apiUrlRequired => 'URL API diperlukan';

  @override
  String get apiKeyRequired => 'Kunci API diperlukan';

  @override
  String get invalidJsonConfig => 'Konfigurasi JSON tidak sah';

  @override
  String errorSaving(String error) {
    return 'Ralat menyimpan: $error';
  }

  @override
  String get configCopiedToClipboard => 'Konfigurasi disalin ke papan keratan';

  @override
  String get pasteJsonConfig => 'Tampal konfigurasi JSON anda di bawah:';

  @override
  String get addApiKeyAfterImport => 'Anda perlu menambah kunci API anda sendiri selepas mengimport';

  @override
  String get paste => 'Tampal';

  @override
  String get import => 'Import';

  @override
  String get invalidProviderInConfig => 'Penyedia tidak sah dalam konfigurasi';

  @override
  String importedConfig(String providerName) {
    return 'Konfigurasi $providerName diimport';
  }

  @override
  String invalidJson(String error) {
    return 'JSON tidak sah: $error';
  }

  @override
  String get provider => 'Penyedia';

  @override
  String get live => 'Langsung';

  @override
  String get onDevice => 'Pada Peranti';

  @override
  String get apiUrl => 'URL API';

  @override
  String get enterSttHttpEndpoint => 'Masukkan titik akhir HTTP STT anda';

  @override
  String get websocketUrl => 'URL WebSocket';

  @override
  String get enterLiveSttWebsocket => 'Masukkan titik akhir WebSocket STT langsung anda';

  @override
  String get apiKey => 'Kunci API';

  @override
  String get enterApiKey => 'Masukkan kunci API anda';

  @override
  String get storedLocallyNeverShared => 'Disimpan secara tempatan, tidak pernah dikongsi';

  @override
  String get host => 'Hos';

  @override
  String get port => 'Port';

  @override
  String get advanced => 'Lanjutan';

  @override
  String get configuration => 'Konfigurasi';

  @override
  String get requestConfiguration => 'Konfigurasi Permintaan';

  @override
  String get responseSchema => 'Skema Respons';

  @override
  String get modified => 'Diubah Suai';

  @override
  String get resetRequestConfig => 'Tetapkan semula konfigurasi permintaan ke lalai';

  @override
  String get logs => 'Log';

  @override
  String get logsCopied => 'Log disalin';

  @override
  String get noLogsYet => 'Tiada log lagi. Mulakan rakaman untuk melihat aktiviti STT tersuai.';

  @override
  String deviceUsesCodec(String device, String reason) {
    return '$device menggunakan $reason. Omi akan digunakan.';
  }

  @override
  String get omiTranscription => 'Transkripsi Omi';

  @override
  String get bestInClassTranscription => 'Transkripsi terbaik dalam kelasnya tanpa persediaan';

  @override
  String get instantSpeakerLabels => 'Label penutur segera';

  @override
  String get languageTranslation => 'Terjemahan 100+ bahasa';

  @override
  String get optimizedForConversation => 'Dioptimumkan untuk perbualan';

  @override
  String get autoLanguageDetection => 'Pengesanan bahasa automatik';

  @override
  String get highAccuracy => 'Ketepatan tinggi';

  @override
  String get privacyFirst => 'Privasi utama';

  @override
  String get saveChanges => 'Simpan Perubahan';

  @override
  String get resetToDefault => 'Tetapkan semula ke lalai';

  @override
  String get viewTemplate => 'Lihat Templat';

  @override
  String get trySomethingLike => 'Cuba sesuatu seperti...';

  @override
  String get tryIt => 'Cuba';

  @override
  String get creatingPlan => 'Mencipta pelan';

  @override
  String get developingLogic => 'Membangunkan logik';

  @override
  String get designingApp => 'Mereka aplikasi';

  @override
  String get generatingIconStep => 'Menjana ikon';

  @override
  String get finalTouches => 'Sentuhan akhir';

  @override
  String get processing => 'Memproses...';

  @override
  String get features => 'Ciri-ciri';

  @override
  String get creatingYourApp => 'Mencipta aplikasi anda...';

  @override
  String get generatingIcon => 'Menjana ikon...';

  @override
  String get whatShouldWeMake => 'Apa yang patut kita buat?';

  @override
  String get appName => 'App Name';

  @override
  String get description => 'Penerangan';

  @override
  String get publicLabel => 'Awam';

  @override
  String get privateLabel => 'Peribadi';

  @override
  String get free => 'Percuma';

  @override
  String get perMonth => '/ Bulan';

  @override
  String get tailoredConversationSummaries => 'Ringkasan Perbualan Tersuai';

  @override
  String get customChatbotPersonality => 'Personaliti Chatbot Tersuai';

  @override
  String get makePublic => 'Jadikan Awam';

  @override
  String get anyoneCanDiscover => 'Sesiapa sahaja boleh menemui aplikasi anda';

  @override
  String get onlyYouCanUse => 'Hanya anda boleh menggunakan aplikasi ini';

  @override
  String get paidApp => 'Aplikasi berbayar';

  @override
  String get usersPayToUse => 'Pengguna membayar untuk menggunakan aplikasi anda';

  @override
  String get freeForEveryone => 'Percuma untuk semua';

  @override
  String get perMonthLabel => '/ bulan';

  @override
  String get creating => 'Mencipta...';

  @override
  String get createApp => 'Cipta Apl';

  @override
  String get searchingForDevices => 'Mencari peranti...';

  @override
  String devicesFoundNearby(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'PERANTI',
      one: 'PERANTI',
    );
    return '$count $_temp0 DIJUMPAI BERDEKATAN';
  }

  @override
  String get pairingSuccessful => 'PERPASANGAN BERJAYA';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Ralat menyambung ke Apple Watch: $error';
  }

  @override
  String get dontShowAgain => 'Jangan tunjukkan lagi';

  @override
  String get iUnderstand => 'Saya Faham';

  @override
  String get enableBluetooth => 'Dayakan Bluetooth';

  @override
  String get bluetoothNeeded =>
      'Omi memerlukan Bluetooth untuk menyambung ke peranti boleh pakai anda. Sila dayakan Bluetooth dan cuba lagi.';

  @override
  String get contactSupport => 'Hubungi Sokongan?';

  @override
  String get connectLater => 'Sambung Kemudian';

  @override
  String get grantPermissions => 'Berikan kebenaran';

  @override
  String get backgroundActivity => 'Aktiviti latar belakang';

  @override
  String get backgroundActivityDesc => 'Biarkan Omi berjalan di latar belakang untuk kestabilan yang lebih baik';

  @override
  String get locationAccess => 'Akses lokasi';

  @override
  String get locationAccessDesc => 'Dayakan lokasi latar belakang untuk pengalaman penuh';

  @override
  String get notifications => 'Pemberitahuan';

  @override
  String get notificationsDesc => 'Dayakan pemberitahuan untuk terus dimaklumkan';

  @override
  String get locationServiceDisabled => 'Perkhidmatan Lokasi Dilumpuhkan';

  @override
  String get locationServiceDisabledDesc =>
      'Perkhidmatan Lokasi dilumpuhkan. Sila pergi ke Tetapan > Privasi & Keselamatan > Perkhidmatan Lokasi dan dayakannya';

  @override
  String get backgroundLocationDenied => 'Akses Lokasi Latar Belakang Ditolak';

  @override
  String get backgroundLocationDeniedDesc =>
      'Sila pergi ke tetapan peranti dan tetapkan kebenaran lokasi kepada \"Sentiasa Benarkan\"';

  @override
  String get lovingOmi => 'Suka Omi?';

  @override
  String get leaveReviewIos =>
      'Bantu kami menjangkau lebih ramai orang dengan meninggalkan ulasan di App Store. Maklum balas anda sangat bermakna bagi kami!';

  @override
  String get leaveReviewAndroid =>
      'Bantu kami menjangkau lebih ramai orang dengan meninggalkan ulasan di Google Play Store. Maklum balas anda sangat bermakna bagi kami!';

  @override
  String get rateOnAppStore => 'Nilai di App Store';

  @override
  String get rateOnGooglePlay => 'Nilai di Google Play';

  @override
  String get maybeLater => 'Mungkin Kemudian';

  @override
  String get speechProfileIntro => 'Omi perlu mempelajari matlamat dan suara anda. Anda boleh mengubahnya kemudian.';

  @override
  String get getStarted => 'Mulakan';

  @override
  String get allDone => 'Semua selesai!';

  @override
  String get keepGoing => 'Teruskan, anda buat dengan baik';

  @override
  String get skipThisQuestion => 'Langkau soalan ini';

  @override
  String get skipForNow => 'Langkau buat masa ini';

  @override
  String get connectionError => 'Ralat Sambungan';

  @override
  String get connectionErrorDesc => 'Gagal menyambung ke pelayan. Sila semak sambungan internet anda dan cuba lagi.';

  @override
  String get invalidRecordingMultipleSpeakers => 'Rakaman tidak sah dikesan';

  @override
  String get multipleSpeakersDesc =>
      'Nampaknya terdapat beberapa penutur dalam rakaman. Sila pastikan anda berada di lokasi yang senyap dan cuba lagi.';

  @override
  String get tooShortDesc => 'Tidak cukup pertuturan dikesan. Sila bercakap lebih banyak dan cuba lagi.';

  @override
  String get invalidRecordingDesc =>
      'Sila pastikan anda bercakap sekurang-kurangnya 5 saat dan tidak lebih daripada 90.';

  @override
  String get areYouThere => 'Adakah anda di sana?';

  @override
  String get noSpeechDesc =>
      'Kami tidak dapat mengesan sebarang pertuturan. Sila pastikan untuk bercakap sekurang-kurangnya 10 saat dan tidak lebih daripada 3 minit.';

  @override
  String get connectionLost => 'Sambungan Terputus';

  @override
  String get connectionLostDesc => 'Sambungan terganggu. Sila semak sambungan internet anda dan cuba lagi.';

  @override
  String get tryAgain => 'Cuba Lagi';

  @override
  String get connectOmiOmiGlass => 'Sambung Omi / OmiGlass';

  @override
  String get continueWithoutDevice => 'Teruskan Tanpa Peranti';

  @override
  String get permissionsRequired => 'Kebenaran Diperlukan';

  @override
  String get permissionsRequiredDesc =>
      'Aplikasi ini memerlukan kebenaran Bluetooth dan Lokasi untuk berfungsi dengan betul. Sila dayakannya dalam tetapan.';

  @override
  String get openSettings => 'Buka Tetapan';

  @override
  String get wantDifferentName => 'Mahu dipanggil dengan nama lain?';

  @override
  String get whatsYourName => 'Siapa nama anda?';

  @override
  String get speakTranscribeSummarize => 'Bercakap. Transkrip. Ringkaskan.';

  @override
  String get signInWithApple => 'Log masuk dengan Apple';

  @override
  String get signInWithGoogle => 'Log masuk dengan Google';

  @override
  String get byContinuingAgree => 'Dengan meneruskan, anda bersetuju dengan ';

  @override
  String get termsOfUse => 'Terma Penggunaan';

  @override
  String get omiYourAiCompanion => 'Omi – Sahabat AI Anda';

  @override
  String get captureEveryMoment => 'Tangkap setiap detik. Dapatkan ringkasan dikuasakan AI.\nJangan ambil nota lagi.';

  @override
  String get appleWatchSetup => 'Persediaan Apple Watch';

  @override
  String get permissionRequestedExclaim => 'Kebenaran Diminta!';

  @override
  String get microphonePermission => 'Kebenaran Mikrofon';

  @override
  String get permissionGrantedNow =>
      'Kebenaran diberikan! Sekarang:\n\nBuka aplikasi Omi pada jam tangan anda dan ketik \"Teruskan\" di bawah';

  @override
  String get needMicrophonePermission =>
      'Kami memerlukan kebenaran mikrofon.\n\n1. Ketik \"Berikan Kebenaran\"\n2. Benarkan pada iPhone anda\n3. Aplikasi jam tangan akan ditutup\n4. Buka semula dan ketik \"Teruskan\"';

  @override
  String get grantPermissionButton => 'Berikan Kebenaran';

  @override
  String get needHelp => 'Perlukan Bantuan?';

  @override
  String get troubleshootingSteps =>
      'Penyelesaian Masalah:\n\n1. Pastikan Omi dipasang pada jam tangan anda\n2. Buka aplikasi Omi pada jam tangan anda\n3. Cari popup kebenaran\n4. Ketik \"Benarkan\" apabila diminta\n5. Aplikasi pada jam tangan anda akan ditutup - buka semula\n6. Kembali dan ketik \"Teruskan\" pada iPhone anda';

  @override
  String get recordingStartedSuccessfully => 'Rakaman bermula dengan jayanya!';

  @override
  String get permissionNotGrantedYet =>
      'Kebenaran belum diberikan. Sila pastikan anda membenarkan akses mikrofon dan membuka semula aplikasi pada jam tangan anda.';

  @override
  String errorRequestingPermission(String error) {
    return 'Ralat meminta kebenaran: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'Ralat memulakan rakaman: $error';
  }

  @override
  String get selectPrimaryLanguage => 'Pilih bahasa utama anda';

  @override
  String get languageBenefits =>
      'Tetapkan bahasa anda untuk transkripsi yang lebih tajam dan pengalaman yang diperibadikan';

  @override
  String get whatsYourPrimaryLanguage => 'Apakah bahasa utama anda?';

  @override
  String get selectYourLanguage => 'Pilih bahasa anda';

  @override
  String get personalGrowthJourney =>
      'Perjalanan pertumbuhan peribadi anda dengan AI yang mendengar setiap perkataan anda.';

  @override
  String get actionItemsTitle => 'Tugasan';

  @override
  String get actionItemsDescription => 'Ketik untuk edit • Tekan lama untuk pilih • Leret untuk tindakan';

  @override
  String get tabToDo => 'Tugasan';

  @override
  String get tabDone => 'Selesai';

  @override
  String get tabOld => 'Lama';

  @override
  String get emptyTodoMessage => '🎉 Semua telah selesai!\nTiada item tindakan tertunda';

  @override
  String get emptyDoneMessage => 'Tiada item selesai lagi';

  @override
  String get emptyOldMessage => '✅ Tiada tugasan lama';

  @override
  String get noItems => 'Tiada item';

  @override
  String get actionItemMarkedIncomplete => 'Item tindakan ditandakan sebagai tidak lengkap';

  @override
  String get actionItemCompleted => 'Item tindakan selesai';

  @override
  String get deleteActionItemTitle => 'Padam item tindakan';

  @override
  String get deleteActionItemMessage => 'Adakah anda pasti mahu memadamkan item tindakan ini?';

  @override
  String get deleteSelectedItemsTitle => 'Padam Item Terpilih';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Adakah anda pasti mahu memadam $count item tindakan terpilih$s?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'Item tindakan \"$description\" dipadam';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count item tindakan$s dipadam';
  }

  @override
  String get failedToDeleteItem => 'Gagal memadam item tindakan';

  @override
  String get failedToDeleteItems => 'Gagal memadam item';

  @override
  String get failedToDeleteSomeItems => 'Gagal memadam beberapa item';

  @override
  String get welcomeActionItemsTitle => 'Sedia untuk Item Tindakan';

  @override
  String get welcomeActionItemsDescription =>
      'AI anda akan secara automatik mengekstrak tugasan dan perkara-yang-perlu-dilakukan daripada perbualan anda. Ia akan muncul di sini apabila dicipta.';

  @override
  String get autoExtractionFeature => 'Diekstrak secara automatik daripada perbualan';

  @override
  String get editSwipeFeature => 'Ketik untuk edit, leret untuk lengkapkan atau padam';

  @override
  String itemsSelected(int count) {
    return '$count dipilih';
  }

  @override
  String get selectAll => 'Pilih semua';

  @override
  String get deleteSelected => 'Padam terpilih';

  @override
  String get searchMemories => 'Cari kenangan...';

  @override
  String get memoryDeleted => 'Ingatan Dipadam.';

  @override
  String get undo => 'Buat Asal';

  @override
  String get noMemoriesYet => '🧠 Belum ada kenangan';

  @override
  String get noAutoMemories => 'Tiada ingatan auto-ekstrak lagi';

  @override
  String get noManualMemories => 'Tiada ingatan manual lagi';

  @override
  String get noMemoriesInCategories => 'Tiada ingatan dalam kategori ini';

  @override
  String get noMemoriesFound => '🔍 Tiada kenangan ditemui';

  @override
  String get addFirstMemory => 'Tambah ingatan pertama anda';

  @override
  String get clearMemoryTitle => 'Kosongkan Ingatan Omi';

  @override
  String get clearMemoryMessage =>
      'Adakah anda pasti mahu mengosongkan ingatan Omi? Tindakan ini tidak boleh dibatalkan.';

  @override
  String get clearMemoryButton => 'Kosongkan Memori';

  @override
  String get memoryClearedSuccess => 'Ingatan Omi tentang anda telah dikosongkan';

  @override
  String get noMemoriesToDelete => 'Tiada memori untuk dipadam';

  @override
  String get createMemoryTooltip => 'Cipta ingatan baharu';

  @override
  String get createActionItemTooltip => 'Cipta item tindakan baharu';

  @override
  String get memoryManagement => 'Pengurusan Memori';

  @override
  String get filterMemories => 'Tapis Ingatan';

  @override
  String totalMemoriesCount(int count) {
    return 'Anda mempunyai $count jumlah ingatan';
  }

  @override
  String get publicMemories => 'Ingatan awam';

  @override
  String get privateMemories => 'Ingatan peribadi';

  @override
  String get makeAllPrivate => 'Jadikan Semua Ingatan Peribadi';

  @override
  String get makeAllPublic => 'Jadikan Semua Ingatan Awam';

  @override
  String get deleteAllMemories => 'Padam Semua Memori';

  @override
  String get allMemoriesPrivateResult => 'Semua ingatan kini peribadi';

  @override
  String get allMemoriesPublicResult => 'Semua ingatan kini awam';

  @override
  String get newMemory => '✨ Memori Baru';

  @override
  String get editMemory => '✏️ Edit Memori';

  @override
  String get memoryContentHint => 'Saya suka makan ais krim...';

  @override
  String get failedToSaveMemory => 'Gagal menyimpan. Sila semak sambungan anda.';

  @override
  String get saveMemory => 'Simpan Ingatan';

  @override
  String get retry => 'Cuba Lagi';

  @override
  String get createActionItem => 'Buat item tindakan';

  @override
  String get editActionItem => 'Edit item tindakan';

  @override
  String get actionItemDescriptionHint => 'Apa yang perlu dilakukan?';

  @override
  String get actionItemDescriptionEmpty => 'Penerangan item tindakan tidak boleh kosong.';

  @override
  String get actionItemUpdated => 'Item tindakan dikemas kini';

  @override
  String get failedToUpdateActionItem => 'Gagal mengemas kini item tindakan';

  @override
  String get actionItemCreated => 'Item tindakan dicipta';

  @override
  String get failedToCreateActionItem => 'Gagal membuat item tindakan';

  @override
  String get dueDate => 'Tarikh akhir';

  @override
  String get time => 'Masa';

  @override
  String get addDueDate => 'Tambah tarikh akhir';

  @override
  String get pressDoneToSave => 'Tekan selesai untuk simpan';

  @override
  String get pressDoneToCreate => 'Tekan selesai untuk cipta';

  @override
  String get filterAll => 'Semua';

  @override
  String get filterSystem => 'Tentang Anda';

  @override
  String get filterInteresting => 'Wawasan';

  @override
  String get filterManual => 'Manual';

  @override
  String get completed => 'Selesai';

  @override
  String get markComplete => 'Tandai selesai';

  @override
  String get actionItemDeleted => 'Item tindakan dipadam';

  @override
  String get failedToDeleteActionItem => 'Gagal memadam item tindakan';

  @override
  String get deleteActionItemConfirmTitle => 'Padam Item Tindakan';

  @override
  String get deleteActionItemConfirmMessage => 'Adakah anda pasti mahu memadam item tindakan ini?';

  @override
  String get appLanguage => 'Bahasa Aplikasi';

  @override
  String get appInterfaceSectionTitle => 'ANTARA MUKA APLIKASI';

  @override
  String get speechTranscriptionSectionTitle => 'PERTUTURAN & TRANSKRIPSI';

  @override
  String get languageSettingsHelperText =>
      'Bahasa Aplikasi menukar menu dan butang. Bahasa Pertuturan mempengaruhi cara rakaman anda ditranskripsi.';

  @override
  String get translationNotice => 'Notis Terjemahan';

  @override
  String get translationNoticeMessage =>
      'Omi menterjemah perbualan ke bahasa utama anda. Kemas kini pada bila-bila masa di Tetapan → Profil.';

  @override
  String get pleaseCheckInternetConnection => 'Sila semak sambungan internet anda dan cuba lagi';

  @override
  String get pleaseSelectReason => 'Sila pilih sebab';

  @override
  String get tellUsMoreWhatWentWrong => 'Beritahu kami lebih lanjut tentang apa yang salah...';

  @override
  String get selectText => 'Pilih Teks';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Maksimum $count matlamat dibenarkan';
  }

  @override
  String get conversationCannotBeMerged => 'Perbualan ini tidak boleh digabungkan (dikunci atau sudah digabungkan)';

  @override
  String get pleaseEnterFolderName => 'Sila masukkan nama folder';

  @override
  String get failedToCreateFolder => 'Gagal mencipta folder';

  @override
  String get failedToUpdateFolder => 'Gagal mengemas kini folder';

  @override
  String get folderName => 'Nama folder';

  @override
  String get descriptionOptional => 'Description (optional)';

  @override
  String get failedToDeleteFolder => 'Gagal memadam folder';

  @override
  String get editFolder => 'Edit folder';

  @override
  String get deleteFolder => 'Padam folder';

  @override
  String get transcriptCopiedToClipboard => 'Transkrip disalin ke papan keratan';

  @override
  String get summaryCopiedToClipboard => 'Ringkasan disalin ke papan keratan';

  @override
  String get conversationUrlCouldNotBeShared => 'URL perbualan tidak dapat dikongsi.';

  @override
  String get urlCopiedToClipboard => 'URL disalin ke papan keratan';

  @override
  String get exportTranscript => 'Eksport transkrip';

  @override
  String get exportSummary => 'Eksport ringkasan';

  @override
  String get exportButton => 'Eksport';

  @override
  String get actionItemsCopiedToClipboard => 'Item tindakan disalin ke papan keratan';

  @override
  String get summarize => 'Ringkaskan';

  @override
  String get generateSummary => 'Jana Ringkasan';

  @override
  String get conversationNotFoundOrDeleted => 'Perbualan tidak ditemui atau telah dipadam';

  @override
  String get deleteMemory => 'Padam Memori';

  @override
  String get thisActionCannotBeUndone => 'Tindakan ini tidak boleh dibuat asal.';

  @override
  String memoriesCount(int count) {
    return '$count kenangan';
  }

  @override
  String get noMemoriesInCategory => 'Tiada kenangan dalam kategori ini lagi';

  @override
  String get addYourFirstMemory => 'Tambah kenangan pertama anda';

  @override
  String get firmwareDisconnectUsb => 'Putuskan USB';

  @override
  String get firmwareUsbWarning => 'Sambungan USB semasa kemas kini boleh merosakkan peranti anda.';

  @override
  String get firmwareBatteryAbove15 => 'Bateri melebihi 15%';

  @override
  String get firmwareEnsureBattery => 'Pastikan peranti anda mempunyai 15% bateri.';

  @override
  String get firmwareStableConnection => 'Sambungan stabil';

  @override
  String get firmwareConnectWifi => 'Sambung ke WiFi atau data selular.';

  @override
  String failedToStartUpdate(String error) {
    return 'Gagal memulakan kemas kini: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'Sebelum kemas kini, pastikan:';

  @override
  String get confirmed => 'Disahkan!';

  @override
  String get release => 'Lepaskan';

  @override
  String get slideToUpdate => 'Luncurkan untuk kemas kini';

  @override
  String copiedToClipboard(String title) {
    return '$title disalin ke papan keratan';
  }

  @override
  String get batteryLevel => 'Tahap Bateri';

  @override
  String get productUpdate => 'Kemas Kini Produk';

  @override
  String get offline => 'Luar Talian';

  @override
  String get available => 'Tersedia';

  @override
  String get unpairDeviceDialogTitle => 'Nyahpasangkan Peranti';

  @override
  String get unpairDeviceDialogMessage =>
      'Ini akan menyahpasangkan peranti supaya ia boleh disambungkan ke telefon lain. Anda perlu pergi ke Tetapan > Bluetooth dan melupakan peranti untuk melengkapkan prosesnya.';

  @override
  String get unpair => 'Nyahpasangkan';

  @override
  String get unpairAndForgetDevice => 'Nyahpasangkan dan Lupakan Peranti';

  @override
  String get unknownDevice => 'Tidak Diketahui';

  @override
  String get unknown => 'Tidak Dikenali';

  @override
  String get productName => 'Nama Produk';

  @override
  String get serialNumber => 'Nombor Siri';

  @override
  String get connected => 'Disambungkan';

  @override
  String get privacyPolicyTitle => 'Dasar Privasi';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label disalin';
  }

  @override
  String get noApiKeysYet => 'Belum ada kunci API. Cipta satu untuk mengintegrasikan dengan aplikasi anda.';

  @override
  String get createKeyToGetStarted => 'Cipta kunci untuk bermula';

  @override
  String get persona => 'Persona';

  @override
  String get configureYourAiPersona => 'Konfigurasikan persona AI anda';

  @override
  String get configureSttProvider => 'Konfigurasikan pembekal STT';

  @override
  String get setWhenConversationsAutoEnd => 'Tetapkan bila perbualan tamat secara automatik';

  @override
  String get importDataFromOtherSources => 'Import data daripada sumber lain';

  @override
  String get debugAndDiagnostics => 'Nyahpepijat & Diagnostik';

  @override
  String get autoDeletesAfter3Days => 'Padam automatik selepas 3 hari';

  @override
  String get helpsDiagnoseIssues => 'Membantu mendiagnosis isu';

  @override
  String get exportStartedMessage => 'Eksport dimulakan. Ini mungkin mengambil masa beberapa saat...';

  @override
  String get exportConversationsToJson => 'Eksport perbualan ke fail JSON';

  @override
  String get knowledgeGraphDeletedSuccess => 'Graf pengetahuan berjaya dipadam';

  @override
  String failedToDeleteGraph(String error) {
    return 'Gagal memadam graf: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'Kosongkan semua nod dan sambungan';

  @override
  String get addToClaudeDesktopConfig => 'Tambah ke claude_desktop_config.json';

  @override
  String get connectAiAssistantsToData => 'Sambungkan pembantu AI ke data anda';

  @override
  String get useYourMcpApiKey => 'Gunakan kunci API MCP anda';

  @override
  String get realTimeTranscript => 'Transkrip Masa Nyata';

  @override
  String get experimental => 'Eksperimental';

  @override
  String get transcriptionDiagnostics => 'Diagnostik Transkripsi';

  @override
  String get detailedDiagnosticMessages => 'Mesej diagnostik terperinci';

  @override
  String get autoCreateSpeakers => 'Cipta Penceramah Secara Automatik';

  @override
  String get autoCreateWhenNameDetected => 'Cipta automatik apabila nama dikesan';

  @override
  String get followUpQuestions => 'Soalan Susulan';

  @override
  String get suggestQuestionsAfterConversations => 'Cadangkan soalan selepas perbualan';

  @override
  String get goalTracker => 'Penjejak Matlamat';

  @override
  String get trackPersonalGoalsOnHomepage => 'Jejaki matlamat peribadi anda di laman utama';

  @override
  String get dailyReflection => 'Refleksi Harian';

  @override
  String get get9PmReminderToReflect => 'Dapatkan peringatan jam 9 malam untuk merenung hari anda';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'Penerangan item tindakan tidak boleh kosong';

  @override
  String get saved => 'Disimpan';

  @override
  String get overdue => 'Lewat';

  @override
  String get failedToUpdateDueDate => 'Gagal mengemas kini tarikh akhir';

  @override
  String get markIncomplete => 'Tandai belum selesai';

  @override
  String get editDueDate => 'Edit tarikh akhir';

  @override
  String get setDueDate => 'Tetapkan tarikh akhir';

  @override
  String get clearDueDate => 'Kosongkan tarikh akhir';

  @override
  String get failedToClearDueDate => 'Gagal mengosongkan tarikh akhir';

  @override
  String get mondayAbbr => 'Isn';

  @override
  String get tuesdayAbbr => 'Sel';

  @override
  String get wednesdayAbbr => 'Rab';

  @override
  String get thursdayAbbr => 'Kha';

  @override
  String get fridayAbbr => 'Jum';

  @override
  String get saturdayAbbr => 'Sab';

  @override
  String get sundayAbbr => 'Ahd';

  @override
  String get howDoesItWork => 'Bagaimana ia berfungsi?';

  @override
  String get sdCardSyncDescription => 'Penyegerakan Kad SD akan mengimport kenangan anda dari Kad SD ke aplikasi';

  @override
  String get checksForAudioFiles => 'Memeriksa fail audio pada Kad SD';

  @override
  String get omiSyncsAudioFiles => 'Omi kemudian menyegerakkan fail audio dengan pelayan';

  @override
  String get serverProcessesAudio => 'Pelayan memproses fail audio dan mencipta kenangan';

  @override
  String get youreAllSet => 'Anda sudah bersedia!';

  @override
  String get welcomeToOmiDescription =>
      'Selamat datang ke Omi! Pendamping AI anda bersedia membantu anda dengan perbualan, tugasan, dan banyak lagi.';

  @override
  String get startUsingOmi => 'Mula Menggunakan Omi';

  @override
  String get back => 'Kembali';

  @override
  String get keyboardShortcuts => 'Pintasan Papan Kekunci';

  @override
  String get toggleControlBar => 'Togol Bar Kawalan';

  @override
  String get pressKeys => 'Tekan kekunci...';

  @override
  String get cmdRequired => '⌘ diperlukan';

  @override
  String get invalidKey => 'Kekunci tidak sah';

  @override
  String get space => 'Ruang';

  @override
  String get search => 'Cari';

  @override
  String get searchPlaceholder => 'Cari...';

  @override
  String get untitledConversation => 'Perbualan Tanpa Tajuk';

  @override
  String countRemaining(String count) {
    return '$count baki';
  }

  @override
  String get addGoal => 'Tambah Matlamat';

  @override
  String get editGoal => 'Edit Matlamat';

  @override
  String get icon => 'Ikon';

  @override
  String get goalTitle => 'Tajuk matlamat';

  @override
  String get current => 'Semasa';

  @override
  String get target => 'Sasaran';

  @override
  String get saveGoal => 'Simpan';

  @override
  String get goals => 'Matlamat';

  @override
  String get tapToAddGoal => 'Ketik untuk menambah matlamat';

  @override
  String welcomeBack(String name) {
    return 'Selamat kembali, $name';
  }

  @override
  String get yourConversations => 'Perbualan Anda';

  @override
  String get reviewAndManageConversations => 'Semak dan urus perbualan yang dirakam';

  @override
  String get startCapturingConversations => 'Mula tangkap perbualan dengan peranti Omi anda untuk melihatnya di sini.';

  @override
  String get useMobileAppToCapture => 'Gunakan aplikasi mudah alih anda untuk merakam audio';

  @override
  String get conversationsProcessedAutomatically => 'Perbualan diproses secara automatik';

  @override
  String get getInsightsInstantly => 'Dapatkan pandangan dan ringkasan dengan segera';

  @override
  String get showAll => 'Tunjukkan semua →';

  @override
  String get noTasksForToday =>
      'Tiada tugasan untuk hari ini.\\nTanya Omi untuk lebih banyak tugasan atau cipta secara manual.';

  @override
  String get dailyScore => 'SKOR HARIAN';

  @override
  String get dailyScoreDescription => 'Skor untuk membantu anda\nfokus pada pelaksanaan.';

  @override
  String get searchResults => 'Hasil carian';

  @override
  String get actionItems => 'Item tindakan';

  @override
  String get tasksToday => 'Hari ini';

  @override
  String get tasksTomorrow => 'Esok';

  @override
  String get tasksNoDeadline => 'Tiada tarikh akhir';

  @override
  String get tasksLater => 'Kemudian';

  @override
  String get loadingTasks => 'Memuatkan tugas...';

  @override
  String get tasks => 'Tugas';

  @override
  String get swipeTasksToIndent => 'Leret tugas untuk indent, seret antara kategori';

  @override
  String get create => 'Cipta';

  @override
  String get noTasksYet => 'Belum ada tugas';

  @override
  String get tasksFromConversationsWillAppear =>
      'Tugas daripada perbualan anda akan muncul di sini.\nKlik Cipta untuk menambah satu secara manual.';

  @override
  String get monthJan => 'Jan';

  @override
  String get monthFeb => 'Feb';

  @override
  String get monthMar => 'Mac';

  @override
  String get monthApr => 'Apr';

  @override
  String get monthMay => 'Mei';

  @override
  String get monthJun => 'Jun';

  @override
  String get monthJul => 'Jul';

  @override
  String get monthAug => 'Ogos';

  @override
  String get monthSep => 'Sept';

  @override
  String get monthOct => 'Okt';

  @override
  String get monthNov => 'Nov';

  @override
  String get monthDec => 'Dis';

  @override
  String get timePM => 'PTG';

  @override
  String get timeAM => 'PG';

  @override
  String get actionItemUpdatedSuccessfully => 'Item tindakan berjaya dikemas kini';

  @override
  String get actionItemCreatedSuccessfully => 'Item tindakan berjaya dibuat';

  @override
  String get actionItemDeletedSuccessfully => 'Item tindakan berjaya dipadamkan';

  @override
  String get deleteActionItem => 'Padam item tindakan';

  @override
  String get deleteActionItemConfirmation =>
      'Adakah anda pasti mahu memadam item tindakan ini? Tindakan ini tidak boleh dibatalkan.';

  @override
  String get enterActionItemDescription => 'Masukkan penerangan item tindakan...';

  @override
  String get markAsCompleted => 'Tandakan sebagai selesai';

  @override
  String get setDueDateAndTime => 'Tetapkan tarikh dan masa akhir';

  @override
  String get reloadingApps => 'Memuatkan semula apl...';

  @override
  String get loadingApps => 'Memuatkan apl...';

  @override
  String get browseInstallCreateApps => 'Layari, pasang dan cipta apl';

  @override
  String get all => 'Semua';

  @override
  String get open => 'Buka';

  @override
  String get install => 'Pasang';

  @override
  String get noAppsAvailable => 'Tiada apl tersedia';

  @override
  String get unableToLoadApps => 'Tidak dapat memuatkan apl';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'Cuba laraskan istilah carian atau penapis anda';

  @override
  String get checkBackLaterForNewApps => 'Semak kemudian untuk apl baharu';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'Sila semak sambungan internet anda dan cuba lagi';

  @override
  String get createNewApp => 'Cipta Aplikasi Baharu';

  @override
  String get buildSubmitCustomOmiApp => 'Bina dan hantar aplikasi Omi tersuai anda';

  @override
  String get submittingYourApp => 'Menghantar aplikasi anda...';

  @override
  String get preparingFormForYou => 'Menyediakan borang untuk anda...';

  @override
  String get appDetails => 'Butiran Aplikasi';

  @override
  String get paymentDetails => 'Butiran Pembayaran';

  @override
  String get previewAndScreenshots => 'Pratonton dan Tangkapan Skrin';

  @override
  String get appCapabilities => 'Keupayaan Aplikasi';

  @override
  String get aiPrompts => 'Gesaan AI';

  @override
  String get chatPrompt => 'Gesaan Sembang';

  @override
  String get chatPromptPlaceholder =>
      'Anda adalah aplikasi yang hebat, tugas anda adalah untuk menjawab pertanyaan pengguna dan membuat mereka berasa baik...';

  @override
  String get conversationPrompt => 'Gesaan Perbualan';

  @override
  String get conversationPromptPlaceholder =>
      'Anda adalah aplikasi yang hebat, anda akan diberikan transkrip dan ringkasan perbualan...';

  @override
  String get notificationScopes => 'Skop Pemberitahuan';

  @override
  String get appPrivacyAndTerms => 'Privasi & Terma Aplikasi';

  @override
  String get makeMyAppPublic => 'Jadikan aplikasi saya awam';

  @override
  String get submitAppTermsAgreement =>
      'Dengan menghantar aplikasi ini, saya bersetuju dengan Terma Perkhidmatan dan Dasar Privasi Omi AI';

  @override
  String get submitApp => 'Hantar Aplikasi';

  @override
  String get needHelpGettingStarted => 'Perlukan bantuan untuk bermula?';

  @override
  String get clickHereForAppBuildingGuides => 'Klik di sini untuk panduan pembinaan aplikasi dan dokumentasi';

  @override
  String get submitAppQuestion => 'Hantar Aplikasi?';

  @override
  String get submitAppPublicDescription =>
      'Aplikasi anda akan disemak dan dijadikan awam. Anda boleh mula menggunakannya dengan serta-merta, walaupun semasa semakan!';

  @override
  String get submitAppPrivateDescription =>
      'Aplikasi anda akan disemak dan disediakan untuk anda secara peribadi. Anda boleh mula menggunakannya dengan serta-merta, walaupun semasa semakan!';

  @override
  String get startEarning => 'Mula Memperoleh! 💰';

  @override
  String get connectStripeOrPayPal => 'Sambungkan Stripe atau PayPal untuk menerima pembayaran untuk aplikasi anda.';

  @override
  String get connectNow => 'Sambung Sekarang';

  @override
  String get installsCount => 'Pemasangan';

  @override
  String get uninstallApp => 'Nyahpasang Apl';

  @override
  String get subscribe => 'Langgan';

  @override
  String get dataAccessNotice => 'Notis Akses Data';

  @override
  String get dataAccessWarning =>
      'Apl ini akan mengakses data anda. Omi AI tidak bertanggungjawab terhadap bagaimana data anda digunakan, diubah suai, atau dipadamkan oleh apl ini';

  @override
  String get installApp => 'Pasang Apl';

  @override
  String get betaTesterNotice =>
      'Anda adalah penguji beta untuk apl ini. Ia belum lagi awam. Ia akan menjadi awam setelah diluluskan.';

  @override
  String get appUnderReviewOwner =>
      'Apl anda sedang dalam semakan dan hanya kelihatan kepada anda. Ia akan menjadi awam setelah diluluskan.';

  @override
  String get appRejectedNotice =>
      'Apl anda telah ditolak. Sila kemas kini butiran apl dan hantar semula untuk semakan.';

  @override
  String get setupSteps => 'Langkah Persediaan';

  @override
  String get setupInstructions => 'Arahan Persediaan';

  @override
  String get integrationInstructions => 'Arahan Integrasi';

  @override
  String get preview => 'Pratonton';

  @override
  String get aboutTheApp => 'Tentang Aplikasi';

  @override
  String get aboutThePersona => 'Tentang Persona';

  @override
  String get chatPersonality => 'Personaliti Sembang';

  @override
  String get ratingsAndReviews => 'Penilaian & Ulasan';

  @override
  String get noRatings => 'tiada penilaian';

  @override
  String ratingsCount(String count) {
    return '$count+ penilaian';
  }

  @override
  String get errorActivatingApp => 'Ralat mengaktifkan apl';

  @override
  String get integrationSetupRequired => 'Jika ini adalah apl integrasi, pastikan persediaan telah selesai.';

  @override
  String get installed => 'Dipasang';

  @override
  String get appIdLabel => 'ID Aplikasi';

  @override
  String get appNameLabel => 'Nama Aplikasi';

  @override
  String get appNamePlaceholder => 'Aplikasi Hebat Saya';

  @override
  String get pleaseEnterAppName => 'Sila masukkan nama aplikasi';

  @override
  String get categoryLabel => 'Kategori';

  @override
  String get selectCategory => 'Pilih Kategori';

  @override
  String get descriptionLabel => 'Keterangan';

  @override
  String get appDescriptionPlaceholder =>
      'Aplikasi Hebat Saya adalah aplikasi yang hebat yang melakukan perkara yang menakjubkan. Ia adalah aplikasi terbaik!';

  @override
  String get pleaseProvideValidDescription => 'Sila berikan keterangan yang sah';

  @override
  String get appPricingLabel => 'Harga Aplikasi';

  @override
  String get noneSelected => 'Tiada Yang Dipilih';

  @override
  String get appIdCopiedToClipboard => 'ID Aplikasi disalin ke papan klip';

  @override
  String get appCategoryModalTitle => 'Kategori Aplikasi';

  @override
  String get pricingFree => 'Percuma';

  @override
  String get pricingPaid => 'Berbayar';

  @override
  String get loadingCapabilities => 'Memuatkan keupayaan...';

  @override
  String get filterInstalled => 'Dipasang';

  @override
  String get filterMyApps => 'Aplikasi Saya';

  @override
  String get clearSelection => 'Kosongkan pilihan';

  @override
  String get filterCategory => 'Kategori';

  @override
  String get rating4PlusStars => '4+ Bintang';

  @override
  String get rating3PlusStars => '3+ Bintang';

  @override
  String get rating2PlusStars => '2+ Bintang';

  @override
  String get rating1PlusStars => '1+ Bintang';

  @override
  String get filterRating => 'Penilaian';

  @override
  String get filterCapabilities => 'Keupayaan';

  @override
  String get noNotificationScopesAvailable => 'Tiada skop pemberitahuan tersedia';

  @override
  String get popularApps => 'Aplikasi Popular';

  @override
  String get pleaseProvidePrompt => 'Sila berikan prompt';

  @override
  String chatWithAppName(String appName) {
    return 'Sembang dengan $appName';
  }

  @override
  String get defaultAiAssistant => 'Pembantu AI Lalai';

  @override
  String get readyToChat => '✨ Bersedia untuk sembang!';

  @override
  String get connectionNeeded => '🌐 Sambungan diperlukan';

  @override
  String get startConversation => 'Mulakan perbualan dan biarkan keajaiban bermula';

  @override
  String get checkInternetConnection => 'Sila periksa sambungan internet anda';

  @override
  String get wasThisHelpful => 'Adakah ini membantu?';

  @override
  String get thankYouForFeedback => 'Terima kasih atas maklum balas anda!';

  @override
  String get maxFilesUploadError => 'Anda hanya boleh memuat naik 4 fail pada satu masa';

  @override
  String get attachedFiles => '📎 Fail Dilampirkan';

  @override
  String get takePhoto => 'Ambil Gambar';

  @override
  String get captureWithCamera => 'Tangkap dengan kamera';

  @override
  String get selectImages => 'Pilih Imej';

  @override
  String get chooseFromGallery => 'Pilih dari galeri';

  @override
  String get selectFile => 'Pilih Fail';

  @override
  String get chooseAnyFileType => 'Pilih sebarang jenis fail';

  @override
  String get cannotReportOwnMessages => 'Anda tidak boleh melaporkan mesej anda sendiri';

  @override
  String get messageReportedSuccessfully => '✅ Mesej berjaya dilaporkan';

  @override
  String get confirmReportMessage => 'Adakah anda pasti mahu melaporkan mesej ini?';

  @override
  String get selectChatAssistant => 'Pilih Pembantu Sembang';

  @override
  String get enableMoreApps => 'Dayakan Lebih Banyak Aplikasi';

  @override
  String get chatCleared => 'Sembang dibersihkan';

  @override
  String get clearChatTitle => 'Kosongkan Sembang?';

  @override
  String get confirmClearChat => 'Adakah anda pasti mahu mengosongkan sembang? Tindakan ini tidak boleh dibatalkan.';

  @override
  String get copy => 'Salin';

  @override
  String get share => 'Kongsi';

  @override
  String get report => 'Laporkan';

  @override
  String get microphonePermissionRequired => 'Kebenaran mikrofon diperlukan untuk rakaman suara.';

  @override
  String get microphonePermissionDenied =>
      'Kebenaran mikrofon ditolak. Sila berikan kebenaran dalam Keutamaan Sistem > Privasi & Keselamatan > Mikrofon.';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'Gagal menyemak kebenaran mikrofon: $error';
  }

  @override
  String get failedToTranscribeAudio => 'Gagal menyalin audio';

  @override
  String get transcribing => 'Menyalin...';

  @override
  String get transcriptionFailed => 'Penyalinan gagal';

  @override
  String get discardedConversation => 'Perbualan dibuang';

  @override
  String get at => 'pada';

  @override
  String get from => 'dari';

  @override
  String get copied => 'Disalin!';

  @override
  String get copyLink => 'Salin pautan';

  @override
  String get hideTranscript => 'Sembunyikan Transkrip';

  @override
  String get viewTranscript => 'Lihat Transkrip';

  @override
  String get conversationDetails => 'Butiran Perbualan';

  @override
  String get transcript => 'Transkrip';

  @override
  String segmentsCount(int count) {
    return '$count segmen';
  }

  @override
  String get noTranscriptAvailable => 'Tiada Transkrip Tersedia';

  @override
  String get noTranscriptMessage => 'Perbualan ini tidak mempunyai transkrip.';

  @override
  String get conversationUrlCouldNotBeGenerated => 'URL perbualan tidak dapat dijana.';

  @override
  String get failedToGenerateConversationLink => 'Gagal menjana pautan perbualan';

  @override
  String get failedToGenerateShareLink => 'Gagal menjana pautan perkongsian';

  @override
  String get reloadingConversations => 'Memuatkan semula perbualan...';

  @override
  String get user => 'Pengguna';

  @override
  String get starred => 'Berbintang';

  @override
  String get date => 'Tarikh';

  @override
  String get noResultsFound => 'Tiada hasil ditemui';

  @override
  String get tryAdjustingSearchTerms => 'Cuba laraskan istilah carian anda';

  @override
  String get starConversationsToFindQuickly => 'Beri bintang pada perbualan untuk mencarinya dengan cepat di sini';

  @override
  String noConversationsOnDate(String date) {
    return 'Tiada perbualan pada $date';
  }

  @override
  String get trySelectingDifferentDate => 'Cuba pilih tarikh yang berbeza';

  @override
  String get conversations => 'Perbualan';

  @override
  String get chat => 'Sembang';

  @override
  String get actions => 'Tindakan';

  @override
  String get syncAvailable => 'Penyegerakan Tersedia';

  @override
  String get referAFriend => 'Rujuk Rakan';

  @override
  String get help => 'Bantuan';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'Naik taraf ke Pro';

  @override
  String get getOmiDevice => 'Dapatkan Peranti Omi';

  @override
  String get wearableAiCompanion => 'Teman AI boleh pakai';

  @override
  String get loadingMemories => 'Memuatkan kenangan...';

  @override
  String get allMemories => 'Semua kenangan';

  @override
  String get aboutYou => 'Tentang anda';

  @override
  String get manual => 'Manual';

  @override
  String get loadingYourMemories => 'Memuatkan kenangan anda...';

  @override
  String get createYourFirstMemory => 'Cipta kenangan pertama anda untuk bermula';

  @override
  String get tryAdjustingFilter => 'Cuba laraskan carian atau penapis anda';

  @override
  String get whatWouldYouLikeToRemember => 'Apa yang anda ingin ingat?';

  @override
  String get category => 'Kategori';

  @override
  String get public => 'Awam';

  @override
  String get failedToSaveCheckConnection => 'Gagal menyimpan. Sila periksa sambungan anda.';

  @override
  String get createMemory => 'Cipta Memori';

  @override
  String get deleteMemoryConfirmation =>
      'Adakah anda pasti mahu memadam memori ini? Tindakan ini tidak boleh dibatalkan.';

  @override
  String get makePrivate => 'Jadikan Peribadi';

  @override
  String get organizeAndControlMemories => 'Atur dan kawal memori anda';

  @override
  String get total => 'Jumlah';

  @override
  String get makeAllMemoriesPrivate => 'Jadikan Semua Memori Peribadi';

  @override
  String get setAllMemoriesToPrivate => 'Tetapkan semua memori kepada keterlihatan peribadi';

  @override
  String get makeAllMemoriesPublic => 'Jadikan Semua Memori Awam';

  @override
  String get setAllMemoriesToPublic => 'Tetapkan semua memori kepada keterlihatan awam';

  @override
  String get permanentlyRemoveAllMemories => 'Buang semua memori dari Omi secara kekal';

  @override
  String get allMemoriesAreNowPrivate => 'Semua memori kini peribadi';

  @override
  String get allMemoriesAreNowPublic => 'Semua memori kini awam';

  @override
  String get clearOmisMemory => 'Kosongkan Memori Omi';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Adakah anda pasti mahu mengosongkan memori Omi? Tindakan ini tidak boleh dibatalkan dan akan memadam semua $count memori secara kekal.';
  }

  @override
  String get omisMemoryCleared => 'Memori Omi tentang anda telah dikosongkan';

  @override
  String get welcomeToOmi => 'Selamat datang ke Omi';

  @override
  String get continueWithApple => 'Teruskan dengan Apple';

  @override
  String get continueWithGoogle => 'Teruskan dengan Google';

  @override
  String get byContinuingYouAgree => 'Dengan meneruskan, anda bersetuju dengan ';

  @override
  String get termsOfService => 'Terma Perkhidmatan';

  @override
  String get and => ' dan ';

  @override
  String get dataAndPrivacy => 'Data & Privasi';

  @override
  String get secureAuthViaAppleId => 'Pengesahan selamat melalui Apple ID';

  @override
  String get secureAuthViaGoogleAccount => 'Pengesahan selamat melalui Akaun Google';

  @override
  String get whatWeCollect => 'Apa yang kami kumpulkan';

  @override
  String get dataCollectionMessage =>
      'Dengan meneruskan, perbualan, rakaman dan maklumat peribadi anda akan disimpan dengan selamat di pelayan kami untuk memberikan wawasan dikuasakan AI dan membolehkan semua ciri aplikasi.';

  @override
  String get dataProtection => 'Perlindungan Data';

  @override
  String get yourDataIsProtected => 'Data anda dilindungi dan dikawal oleh ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'Sila pilih bahasa utama anda';

  @override
  String get chooseYourLanguage => 'Pilih bahasa anda';

  @override
  String get selectPreferredLanguageForBestExperience => 'Pilih bahasa pilihan anda untuk pengalaman Omi terbaik';

  @override
  String get searchLanguages => 'Cari bahasa...';

  @override
  String get selectALanguage => 'Pilih bahasa';

  @override
  String get tryDifferentSearchTerm => 'Cuba istilah carian yang berbeza';

  @override
  String get pleaseEnterYourName => 'Sila masukkan nama anda';

  @override
  String get nameMustBeAtLeast2Characters => 'Nama mesti sekurang-kurangnya 2 aksara';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'Beritahu kami bagaimana anda ingin dipanggil. Ini membantu memperibadikan pengalaman Omi anda.';

  @override
  String charactersCount(int count) {
    return '$count aksara';
  }

  @override
  String get enableFeaturesForBestExperience => 'Dayakan ciri untuk pengalaman Omi terbaik pada peranti anda.';

  @override
  String get microphoneAccess => 'Akses Mikrofon';

  @override
  String get recordAudioConversations => 'Rakam perbualan audio';

  @override
  String get microphoneAccessDescription =>
      'Omi memerlukan akses mikrofon untuk merakam perbualan anda dan menyediakan transkripsi.';

  @override
  String get screenRecording => 'Rakaman Skrin';

  @override
  String get captureSystemAudioFromMeetings => 'Tangkap audio sistem dari mesyuarat';

  @override
  String get screenRecordingDescription =>
      'Omi memerlukan kebenaran rakaman skrin untuk menangkap audio sistem dari mesyuarat berasaskan pelayar anda.';

  @override
  String get accessibility => 'Kebolehcapaian';

  @override
  String get detectBrowserBasedMeetings => 'Kesan mesyuarat berasaskan pelayar';

  @override
  String get accessibilityDescription =>
      'Omi memerlukan kebenaran kebolehcapaian untuk mengesan apabila anda menyertai mesyuarat Zoom, Meet, atau Teams dalam pelayar anda.';

  @override
  String get pleaseWait => 'Sila tunggu...';

  @override
  String get joinTheCommunity => 'Sertai komuniti!';

  @override
  String get loadingProfile => 'Memuatkan profil...';

  @override
  String get profileSettings => 'Tetapan Profil';

  @override
  String get noEmailSet => 'Tiada e-mel ditetapkan';

  @override
  String get userIdCopiedToClipboard => 'ID pengguna disalin';

  @override
  String get yourInformation => 'Maklumat Anda';

  @override
  String get setYourName => 'Tetapkan Nama Anda';

  @override
  String get changeYourName => 'Tukar Nama Anda';

  @override
  String get manageYourOmiPersona => 'Urus persona Omi anda';

  @override
  String get voiceAndPeople => 'Suara & Orang';

  @override
  String get teachOmiYourVoice => 'Ajar Omi suara anda';

  @override
  String get tellOmiWhoSaidIt => 'Beritahu Omi siapa yang mengatakannya 🗣️';

  @override
  String get payment => 'Pembayaran';

  @override
  String get addOrChangeYourPaymentMethod => 'Tambah atau tukar kaedah pembayaran';

  @override
  String get preferences => 'Keutamaan';

  @override
  String get helpImproveOmiBySharing => 'Bantu tingkatkan Omi dengan berkongsi data analitik tanpa nama';

  @override
  String get deleteAccount => 'Padam Akaun';

  @override
  String get deleteYourAccountAndAllData => 'Padam akaun dan semua data anda';

  @override
  String get clearLogs => 'Kosongkan log';

  @override
  String get debugLogsCleared => 'Log nyahpepijat dikosongkan';

  @override
  String get exportConversations => 'Eksport Perbualan';

  @override
  String get exportAllConversationsToJson => 'Eksport semua perbualan anda ke fail JSON.';

  @override
  String get conversationsExportStarted =>
      'Eksport Perbualan Dimulakan. Ini mungkin mengambil masa beberapa saat, sila tunggu.';

  @override
  String get mcpDescription =>
      'Untuk menyambungkan Omi dengan aplikasi lain untuk membaca, mencari, dan mengurus kenangan dan perbualan anda. Cipta kunci untuk bermula.';

  @override
  String get apiKeys => 'Kunci API';

  @override
  String errorLabel(String error) {
    return 'Ralat: $error';
  }

  @override
  String get noApiKeysFound => 'Tiada kunci API dijumpai. Cipta satu untuk bermula.';

  @override
  String get advancedSettings => 'Tetapan Lanjutan';

  @override
  String get triggersWhenNewConversationCreated => 'Dicetuskan apabila perbualan baharu dicipta.';

  @override
  String get triggersWhenNewTranscriptReceived => 'Dicetuskan apabila transkrip baharu diterima.';

  @override
  String get realtimeAudioBytes => 'Bait Audio Masa Nyata';

  @override
  String get triggersWhenAudioBytesReceived => 'Dicetuskan apabila bait audio diterima.';

  @override
  String get everyXSeconds => 'Setiap x saat';

  @override
  String get triggersWhenDaySummaryGenerated => 'Dicetuskan apabila ringkasan hari dijana.';

  @override
  String get tryLatestExperimentalFeatures => 'Cuba ciri eksperimental terkini daripada Pasukan Omi.';

  @override
  String get transcriptionServiceDiagnosticStatus => 'Status diagnostik perkhidmatan transkripsi';

  @override
  String get enableDetailedDiagnosticMessages =>
      'Dayakan mesej diagnostik terperinci daripada perkhidmatan transkripsi';

  @override
  String get autoCreateAndTagNewSpeakers => 'Cipta dan tag penceramah baharu secara automatik';

  @override
  String get automaticallyCreateNewPerson =>
      'Cipta orang baharu secara automatik apabila nama dikesan dalam transkrip.';

  @override
  String get pilotFeatures => 'Ciri Perintis';

  @override
  String get pilotFeaturesDescription => 'Ciri ini adalah ujian dan tiada jaminan sokongan.';

  @override
  String get suggestFollowUpQuestion => 'Cadangkan soalan susulan';

  @override
  String get saveSettings => 'Simpan Tetapan';

  @override
  String get syncingDeveloperSettings => 'Menyegerakkan Tetapan Pembangun...';

  @override
  String get summary => 'Ringkasan';

  @override
  String get auto => 'Auto';

  @override
  String get noSummaryForApp => 'Tiada ringkasan untuk aplikasi ini. Cuba aplikasi lain untuk hasil yang lebih baik.';

  @override
  String get tryAnotherApp => 'Cuba Aplikasi Lain';

  @override
  String generatedBy(String appName) {
    return 'Dijana oleh $appName';
  }

  @override
  String get overview => 'Gambaran Keseluruhan';

  @override
  String get otherAppResults => 'Hasil Aplikasi Lain';

  @override
  String get unknownApp => 'Aplikasi tidak diketahui';

  @override
  String get noSummaryAvailable => 'Tiada Ringkasan Tersedia';

  @override
  String get conversationNoSummaryYet => 'Perbualan ini belum mempunyai ringkasan.';

  @override
  String get chooseSummarizationApp => 'Pilih Aplikasi Ringkasan';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName ditetapkan sebagai aplikasi ringkasan lalai';
  }

  @override
  String get letOmiChooseAutomatically => 'Biarkan Omi memilih aplikasi terbaik secara automatik';

  @override
  String get deleteConversationConfirmation =>
      'Adakah anda pasti mahu memadam perbualan ini? Tindakan ini tidak boleh dibatalkan.';

  @override
  String get conversationDeleted => 'Perbualan dipadam';

  @override
  String get generatingLink => 'Menjana pautan...';

  @override
  String get editConversation => 'Edit perbualan';

  @override
  String get conversationLinkCopiedToClipboard => 'Pautan perbualan disalin ke papan keratan';

  @override
  String get conversationTranscriptCopiedToClipboard => 'Transkrip perbualan disalin ke papan keratan';

  @override
  String get editConversationDialogTitle => 'Edit Perbualan';

  @override
  String get changeTheConversationTitle => 'Tukar tajuk perbualan';

  @override
  String get conversationTitle => 'Tajuk Perbualan';

  @override
  String get enterConversationTitle => 'Masukkan tajuk perbualan...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'Tajuk perbualan berjaya dikemas kini';

  @override
  String get failedToUpdateConversationTitle => 'Gagal mengemas kini tajuk perbualan';

  @override
  String get errorUpdatingConversationTitle => 'Ralat mengemas kini tajuk perbualan';

  @override
  String get settingUp => 'Menyediakan...';

  @override
  String get startYourFirstRecording => 'Mulakan rakaman pertama anda';

  @override
  String get preparingSystemAudioCapture => 'Menyediakan tangkapan audio sistem';

  @override
  String get clickTheButtonToCaptureAudio =>
      'Klik butang untuk menangkap audio untuk transkripsi langsung, cerapan AI dan penyimpanan automatik.';

  @override
  String get reconnecting => 'Menyambung semula...';

  @override
  String get recordingPaused => 'Rakaman dijeda';

  @override
  String get recordingActive => 'Rakaman aktif';

  @override
  String get startRecording => 'Mula merakam';

  @override
  String resumingInCountdown(String countdown) {
    return 'Menyambung dalam ${countdown}s...';
  }

  @override
  String get tapPlayToResume => 'Ketik main untuk meneruskan';

  @override
  String get listeningForAudio => 'Mendengar audio...';

  @override
  String get preparingAudioCapture => 'Menyediakan tangkapan audio';

  @override
  String get clickToBeginRecording => 'Klik untuk memulakan rakaman';

  @override
  String get translated => 'diterjemahkan';

  @override
  String get liveTranscript => 'Transkripsi Langsung';

  @override
  String segmentsSingular(String count) {
    return '$count segmen';
  }

  @override
  String segmentsPlural(String count) {
    return '$count segmen';
  }

  @override
  String get startRecordingToSeeTranscript => 'Mula rakaman untuk melihat transkripsi langsung';

  @override
  String get paused => 'Dijeda';

  @override
  String get initializing => 'Memulakan...';

  @override
  String get recording => 'Merakam';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'Mikrofon ditukar. Menyambung dalam ${countdown}s';
  }

  @override
  String get clickPlayToResumeOrStop => 'Klik main untuk meneruskan atau berhenti untuk tamat';

  @override
  String get settingUpSystemAudioCapture => 'Menyediakan tangkapan audio sistem';

  @override
  String get capturingAudioAndGeneratingTranscript => 'Menangkap audio dan menjana transkripsi';

  @override
  String get clickToBeginRecordingSystemAudio => 'Klik untuk memulakan rakaman audio sistem';

  @override
  String get you => 'Anda';

  @override
  String speakerWithId(String speakerId) {
    return 'Penceramah $speakerId';
  }

  @override
  String get translatedByOmi => 'diterjemahkan oleh omi';

  @override
  String get backToConversations => 'Kembali ke Perbualan';

  @override
  String get systemAudio => 'Sistem';

  @override
  String get mic => 'Mikrofon';

  @override
  String audioInputSetTo(String deviceName) {
    return 'Input audio ditetapkan kepada $deviceName';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'Ralat menukar peranti audio: $error';
  }

  @override
  String get selectAudioInput => 'Pilih Input Audio';

  @override
  String get loadingDevices => 'Memuatkan peranti...';

  @override
  String get settingsHeader => 'TETAPAN';

  @override
  String get plansAndBilling => 'Pelan & Pengebilan';

  @override
  String get calendarIntegration => 'Integrasi Kalendar';

  @override
  String get dailySummary => 'Ringkasan Harian';

  @override
  String get developer => 'Pembangun';

  @override
  String get about => 'Perihal';

  @override
  String get selectTime => 'Pilih Masa';

  @override
  String get accountGroup => 'Akaun';

  @override
  String get signOutQuestion => 'Log keluar?';

  @override
  String get signOutConfirmation => 'Adakah anda pasti mahu log keluar?';

  @override
  String get customVocabularyHeader => 'PERBENDAHARAAN KATA TERSUAI';

  @override
  String get addWordsDescription => 'Tambah perkataan yang Omi harus kenali semasa transkripsi.';

  @override
  String get enterWordsHint => 'Masukkan perkataan (dipisahkan koma)';

  @override
  String get dailySummaryHeader => 'RINGKASAN HARIAN';

  @override
  String get dailySummaryTitle => 'Ringkasan Harian';

  @override
  String get dailySummaryDescription => 'Terima ringkasan diperibadikan perbualan hari anda sebagai pemberitahuan.';

  @override
  String get deliveryTime => 'Masa Penghantaran';

  @override
  String get deliveryTimeDescription => 'Bila menerima ringkasan harian anda';

  @override
  String get subscription => 'Langganan';

  @override
  String get viewPlansAndUsage => 'Lihat Pelan & Penggunaan';

  @override
  String get viewPlansDescription => 'Urus langganan anda dan lihat statistik penggunaan';

  @override
  String get addOrChangePaymentMethod => 'Tambah atau tukar kaedah pembayaran anda';

  @override
  String get displayOptions => 'Pilihan Paparan';

  @override
  String get showMeetingsInMenuBar => 'Tunjukkan Mesyuarat dalam Bar Menu';

  @override
  String get displayUpcomingMeetingsDescription => 'Paparkan mesyuarat akan datang dalam bar menu';

  @override
  String get showEventsWithoutParticipants => 'Tunjukkan Acara Tanpa Peserta';

  @override
  String get includePersonalEventsDescription => 'Sertakan acara peribadi tanpa kehadiran';

  @override
  String get upcomingMeetings => 'Mesyuarat Akan Datang';

  @override
  String get checkingNext7Days => 'Memeriksa 7 hari akan datang';

  @override
  String get shortcuts => 'Pintasan';

  @override
  String get shortcutChangeInstruction => 'Klik pada pintasan untuk mengubahnya. Tekan Escape untuk membatalkan.';

  @override
  String get configurePersonaDescription => 'Konfigurasikan persona AI anda';

  @override
  String get configureSTTProvider => 'Konfigurasikan pembekal STT';

  @override
  String get setConversationEndDescription => 'Tetapkan bila perbualan tamat secara automatik';

  @override
  String get importDataDescription => 'Import data dari sumber lain';

  @override
  String get exportConversationsDescription => 'Eksport perbualan ke JSON';

  @override
  String get exportingConversations => 'Mengeksport perbualan...';

  @override
  String get clearNodesDescription => 'Kosongkan semua nod dan sambungan';

  @override
  String get deleteKnowledgeGraphQuestion => 'Padam Graf Pengetahuan?';

  @override
  String get deleteKnowledgeGraphWarning =>
      'Ini akan memadam semua data graf pengetahuan yang diperoleh. Ingatan asal anda kekal selamat.';

  @override
  String get connectOmiWithAI => 'Sambungkan Omi dengan pembantu AI';

  @override
  String get noAPIKeys => 'Tiada kunci API. Cipta satu untuk bermula.';

  @override
  String get autoCreateWhenDetected => 'Cipta automatik apabila nama dikesan';

  @override
  String get trackPersonalGoals => 'Jejaki matlamat peribadi pada laman utama';

  @override
  String get dailyReflectionDescription =>
      'Terima peringatan pada jam 9 malam untuk merenung hari anda dan mencatat fikiran anda.';

  @override
  String get endpointURL => 'URL Titik Akhir';

  @override
  String get links => 'Pautan';

  @override
  String get discordMemberCount => '8000+ ahli di Discord';

  @override
  String get userInformation => 'Maklumat Pengguna';

  @override
  String get capabilities => 'Keupayaan';

  @override
  String get previewScreenshots => 'Pratonton tangkapan skrin';

  @override
  String get holdOnPreparingForm => 'Sila tunggu, kami sedang menyediakan borang untuk anda';

  @override
  String get bySubmittingYouAgreeToOmi => 'Dengan menghantar, anda bersetuju dengan ';

  @override
  String get termsAndPrivacyPolicy => 'Terma & Dasar Privasi';

  @override
  String get helpsDiagnoseIssuesAutoDeletes => 'Membantu mendiagnosis isu. Dipadam secara automatik selepas 3 hari.';

  @override
  String get manageYourApp => 'Urus Aplikasi Anda';

  @override
  String get updatingYourApp => 'Mengemas kini aplikasi anda';

  @override
  String get fetchingYourAppDetails => 'Mendapatkan butiran aplikasi anda';

  @override
  String get updateAppQuestion => 'Kemas kini Aplikasi?';

  @override
  String get updateAppConfirmation =>
      'Adakah anda pasti mahu mengemas kini aplikasi anda? Perubahan akan dipaparkan selepas disemak oleh pasukan kami.';

  @override
  String get updateApp => 'Kemas kini Aplikasi';

  @override
  String get createAndSubmitNewApp => 'Cipta dan hantar aplikasi baharu';

  @override
  String appsCount(String count) {
    return 'Aplikasi ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'Aplikasi Peribadi ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'Aplikasi Awam ($count)';
  }

  @override
  String get newVersionAvailable => 'Versi Baharu Tersedia  🎉';

  @override
  String get no => 'Tidak';

  @override
  String get subscriptionCancelledSuccessfully =>
      'Langganan berjaya dibatalkan. Ia akan kekal aktif sehingga akhir tempoh pengebilan semasa.';

  @override
  String get failedToCancelSubscription => 'Gagal membatalkan langganan. Sila cuba lagi.';

  @override
  String get invalidPaymentUrl => 'URL pembayaran tidak sah';

  @override
  String get permissionsAndTriggers => 'Kebenaran & Pencetus';

  @override
  String get chatFeatures => 'Ciri Sembang';

  @override
  String get uninstall => 'Nyahpasang';

  @override
  String get installs => 'PEMASANGAN';

  @override
  String get priceLabel => 'HARGA';

  @override
  String get updatedLabel => 'DIKEMAS KINI';

  @override
  String get createdLabel => 'DICIPTA';

  @override
  String get featuredLabel => 'PILIHAN';

  @override
  String get cancelSubscriptionQuestion => 'Batalkan Langganan?';

  @override
  String get cancelSubscriptionConfirmation =>
      'Adakah anda pasti mahu membatalkan langganan anda? Anda akan terus mempunyai akses sehingga akhir tempoh pengebilan semasa.';

  @override
  String get cancelSubscriptionButton => 'Batalkan Langganan';

  @override
  String get cancelling => 'Membatalkan...';

  @override
  String get betaTesterMessage =>
      'Anda adalah penguji beta untuk aplikasi ini. Ia belum dipublikasikan. Ia akan dipublikasikan setelah diluluskan.';

  @override
  String get appUnderReviewMessage =>
      'Aplikasi anda sedang disemak dan hanya kelihatan kepada anda. Ia akan dipublikasikan setelah diluluskan.';

  @override
  String get appRejectedMessage =>
      'Aplikasi anda telah ditolak. Sila kemas kini butiran dan hantar semula untuk semakan.';

  @override
  String get invalidIntegrationUrl => 'URL integrasi tidak sah';

  @override
  String get tapToComplete => 'Ketik untuk selesaikan';

  @override
  String get invalidSetupInstructionsUrl => 'URL arahan persediaan tidak sah';

  @override
  String get pushToTalk => 'Tekan untuk Bercakap';

  @override
  String get summaryPrompt => 'Prompt Ringkasan';

  @override
  String get pleaseSelectARating => 'Sila pilih penilaian';

  @override
  String get reviewAddedSuccessfully => 'Ulasan berjaya ditambah 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'Ulasan berjaya dikemas kini 🚀';

  @override
  String get failedToSubmitReview => 'Gagal menghantar ulasan. Sila cuba lagi.';

  @override
  String get addYourReview => 'Tambah Ulasan Anda';

  @override
  String get editYourReview => 'Edit Ulasan Anda';

  @override
  String get writeAReviewOptional => 'Tulis ulasan (pilihan)';

  @override
  String get submitReview => 'Hantar Ulasan';

  @override
  String get updateReview => 'Kemas kini Ulasan';

  @override
  String get yourReview => 'Ulasan Anda';

  @override
  String get anonymousUser => 'Pengguna Tanpa Nama';

  @override
  String get issueActivatingApp => 'Terdapat masalah mengaktifkan aplikasi ini. Sila cuba lagi.';

  @override
  String get dataAccessNoticeDescription =>
      'Aplikasi ini akan mengakses data anda. Omi AI tidak bertanggungjawab atas cara data anda digunakan oleh aplikasi ini.';

  @override
  String get copyUrl => 'Salin URL';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => 'Isn';

  @override
  String get weekdayTue => 'Sel';

  @override
  String get weekdayWed => 'Rab';

  @override
  String get weekdayThu => 'Kha';

  @override
  String get weekdayFri => 'Jum';

  @override
  String get weekdaySat => 'Sab';

  @override
  String get weekdaySun => 'Ahd';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return 'Integrasi $serviceName akan datang';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'Sudah dieksport ke $platform';
  }

  @override
  String get anotherPlatform => 'platform lain';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'Sila sahkan dengan $serviceName dalam Tetapan > Integrasi Tugas';
  }

  @override
  String addingToService(String serviceName) {
    return 'Menambah ke $serviceName...';
  }

  @override
  String addedToService(String serviceName) {
    return 'Ditambah ke $serviceName';
  }

  @override
  String failedToAddToService(String serviceName) {
    return 'Gagal menambah ke $serviceName';
  }

  @override
  String get permissionDeniedForAppleReminders => 'Kebenaran ditolak untuk Apple Reminders';

  @override
  String failedToCreateApiKey(String error) {
    return 'Gagal mencipta kunci API pembekal: $error';
  }

  @override
  String get createAKey => 'Cipta Kunci';

  @override
  String get apiKeyRevokedSuccessfully => 'Kunci API berjaya dibatalkan';

  @override
  String failedToRevokeApiKey(String error) {
    return 'Gagal membatalkan kunci API: $error';
  }

  @override
  String get omiApiKeys => 'Kunci API Omi';

  @override
  String get apiKeysDescription =>
      'Kunci API digunakan untuk pengesahan apabila aplikasi anda berkomunikasi dengan pelayan OMI. Ia membenarkan aplikasi anda mencipta memori dan mengakses perkhidmatan OMI lain dengan selamat.';

  @override
  String get aboutOmiApiKeys => 'Tentang Kunci API Omi';

  @override
  String get yourNewKey => 'Kunci baharu anda:';

  @override
  String get copyToClipboard => 'Salin ke papan keratan';

  @override
  String get pleaseCopyKeyNow => 'Sila salin sekarang dan simpan di tempat yang selamat. ';

  @override
  String get willNotSeeAgain => 'Anda tidak akan dapat melihatnya lagi.';

  @override
  String get revokeKey => 'Batalkan kunci';

  @override
  String get revokeApiKeyQuestion => 'Batalkan Kunci API?';

  @override
  String get revokeApiKeyWarning =>
      'Tindakan ini tidak boleh dibuat asal. Sebarang aplikasi yang menggunakan kunci ini tidak akan dapat mengakses API lagi.';

  @override
  String get revoke => 'Batalkan';

  @override
  String get whatWouldYouLikeToCreate => 'Apa yang anda ingin cipta?';

  @override
  String get createAnApp => 'Cipta Aplikasi';

  @override
  String get createAndShareYourApp => 'Cipta dan kongsi aplikasi anda';

  @override
  String get createMyClone => 'Cipta Klon Saya';

  @override
  String get createYourDigitalClone => 'Cipta klon digital anda';

  @override
  String get itemApp => 'Aplikasi';

  @override
  String get itemPersona => 'Persona';

  @override
  String keepItemPublic(String item) {
    return 'Kekalkan $item Awam';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return 'Jadikan $item Awam?';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return 'Jadikan $item Peribadi?';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'Jika anda menjadikan $item awam, ia boleh digunakan oleh semua orang';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'Jika anda menjadikan $item peribadi sekarang, ia akan berhenti berfungsi untuk semua orang dan hanya akan kelihatan kepada anda';
  }

  @override
  String get manageApp => 'Urus Aplikasi';

  @override
  String get updatePersonaDetails => 'Kemas Kini Butiran Persona';

  @override
  String deleteItemTitle(String item) {
    return 'Padam $item';
  }

  @override
  String deleteItemQuestion(String item) {
    return 'Padam $item?';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'Adakah anda pasti mahu memadamkan $item ini? Tindakan ini tidak boleh dibuat asal.';
  }

  @override
  String get revokeKeyQuestion => 'Batalkan Kunci?';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'Adakah anda pasti mahu membatalkan kunci \"$keyName\"? Tindakan ini tidak boleh dibuat asal.';
  }

  @override
  String get createNewKey => 'Cipta Kunci Baharu';

  @override
  String get keyNameHint => 'cth., Claude Desktop';

  @override
  String get pleaseEnterAName => 'Sila masukkan nama.';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'Gagal mencipta kunci: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'Gagal mencipta kunci. Sila cuba lagi.';

  @override
  String get keyCreated => 'Kunci Dicipta';

  @override
  String get keyCreatedMessage =>
      'Kunci baharu anda telah dicipta. Sila salin sekarang. Anda tidak akan dapat melihatnya lagi.';

  @override
  String get keyWord => 'Kunci';

  @override
  String get externalAppAccess => 'Akses Aplikasi Luaran';

  @override
  String get externalAppAccessDescription =>
      'Aplikasi yang dipasang berikut mempunyai integrasi luaran dan boleh mengakses data anda, seperti perbualan dan kenangan.';

  @override
  String get noExternalAppsHaveAccess => 'Tiada aplikasi luaran yang mempunyai akses kepada data anda.';

  @override
  String get maximumSecurityE2ee => 'Keselamatan Maksimum (E2EE)';

  @override
  String get e2eeDescription =>
      'Penyulitan hujung ke hujung adalah standard emas untuk privasi. Apabila diaktifkan, data anda disulitkan pada peranti anda sebelum dihantar ke pelayan kami. Ini bermakna tiada sesiapa, malah Omi, boleh mengakses kandungan anda.';

  @override
  String get importantTradeoffs => 'Pertimbangan Penting:';

  @override
  String get e2eeTradeoff1 => '• Beberapa ciri seperti integrasi aplikasi luaran mungkin dilumpuhkan.';

  @override
  String get e2eeTradeoff2 => '• Jika anda kehilangan kata laluan, data anda tidak boleh dipulihkan.';

  @override
  String get featureComingSoon => 'Ciri ini akan datang tidak lama lagi!';

  @override
  String get migrationInProgressMessage =>
      'Migrasi sedang berjalan. Anda tidak boleh menukar tahap perlindungan sehingga selesai.';

  @override
  String get migrationFailed => 'Migrasi Gagal';

  @override
  String migratingFromTo(String source, String target) {
    return 'Memindahkan dari $source ke $target';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total objek';
  }

  @override
  String get secureEncryption => 'Penyulitan Selamat';

  @override
  String get secureEncryptionDescription =>
      'Data anda disulitkan dengan kunci yang unik untuk anda di pelayan kami, yang dihoskan di Google Cloud. Ini bermakna kandungan mentah anda tidak boleh diakses oleh sesiapa, termasuk kakitangan Omi atau Google, terus dari pangkalan data.';

  @override
  String get endToEndEncryption => 'Penyulitan Hujung ke Hujung';

  @override
  String get e2eeCardDescription =>
      'Aktifkan untuk keselamatan maksimum di mana hanya anda boleh mengakses data anda. Ketik untuk mengetahui lebih lanjut.';

  @override
  String get dataAlwaysEncrypted =>
      'Tanpa mengira tahap, data anda sentiasa disulitkan semasa berehat dan dalam transit.';

  @override
  String get readOnlyScope => 'Baca Sahaja';

  @override
  String get fullAccessScope => 'Akses Penuh';

  @override
  String get readScope => 'Baca';

  @override
  String get writeScope => 'Tulis';

  @override
  String get apiKeyCreated => 'Kunci API Dicipta!';

  @override
  String get saveKeyWarning => 'Simpan kunci ini sekarang! Anda tidak akan dapat melihatnya lagi.';

  @override
  String get yourApiKey => 'KUNCI API ANDA';

  @override
  String get tapToCopy => 'Ketik untuk menyalin';

  @override
  String get copyKey => 'Salin Kunci';

  @override
  String get createApiKey => 'Cipta Kunci API';

  @override
  String get accessDataProgrammatically => 'Akses data anda secara programatik';

  @override
  String get keyNameLabel => 'NAMA KUNCI';

  @override
  String get keyNamePlaceholder => 'cth., Integrasi Apl Saya';

  @override
  String get permissionsLabel => 'KEBENARAN';

  @override
  String get permissionsInfoNote => 'R = Baca, W = Tulis. Lalai baca sahaja jika tiada yang dipilih.';

  @override
  String get developerApi => 'API Pembangun';

  @override
  String get createAKeyToGetStarted => 'Cipta kunci untuk bermula';

  @override
  String errorWithMessage(String error) {
    return 'Ralat: $error';
  }

  @override
  String get omiTraining => 'Latihan Omi';

  @override
  String get trainingDataProgram => 'Program Data Latihan';

  @override
  String get getOmiUnlimitedFree =>
      'Dapatkan Omi Unlimited percuma dengan menyumbang data anda untuk melatih model AI.';

  @override
  String get trainingDataBullets =>
      '• Data anda membantu meningkatkan model AI\n• Hanya data tidak sensitif yang dikongsi\n• Proses sepenuhnya telus';

  @override
  String get learnMoreAtOmiTraining => 'Ketahui lebih lanjut di omi.me/training';

  @override
  String get agreeToContributeData => 'Saya memahami dan bersetuju untuk menyumbang data saya untuk latihan AI';

  @override
  String get submitRequest => 'Hantar Permintaan';

  @override
  String get thankYouRequestUnderReview =>
      'Terima kasih! Permintaan anda sedang disemak. Kami akan memberitahu anda setelah diluluskan.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'Pelan anda akan kekal aktif sehingga $date. Selepas itu, anda akan kehilangan akses kepada ciri tanpa had. Adakah anda pasti?';
  }

  @override
  String get confirmCancellation => 'Sahkan Pembatalan';

  @override
  String get keepMyPlan => 'Kekalkan Pelan Saya';

  @override
  String get subscriptionSetToCancel => 'Langganan anda ditetapkan untuk dibatalkan pada akhir tempoh.';

  @override
  String get switchedToOnDevice => 'Bertukar kepada transkripsi pada peranti';

  @override
  String get couldNotSwitchToFreePlan => 'Tidak dapat beralih ke pelan percuma. Sila cuba lagi.';

  @override
  String get couldNotLoadPlans => 'Tidak dapat memuatkan pelan yang tersedia. Sila cuba lagi.';

  @override
  String get selectedPlanNotAvailable => 'Pelan yang dipilih tidak tersedia. Sila cuba lagi.';

  @override
  String get upgradeToAnnualPlan => 'Naik taraf ke Pelan Tahunan';

  @override
  String get importantBillingInfo => 'Maklumat Pengebilan Penting:';

  @override
  String get monthlyPlanContinues => 'Pelan bulanan semasa anda akan diteruskan sehingga akhir tempoh pengebilan';

  @override
  String get paymentMethodCharged =>
      'Kaedah pembayaran sedia ada anda akan dicaj secara automatik apabila pelan bulanan anda tamat';

  @override
  String get annualSubscriptionStarts => 'Langganan tahunan 12 bulan anda akan bermula secara automatik selepas caj';

  @override
  String get thirteenMonthsCoverage =>
      'Anda akan mendapat liputan 13 bulan secara keseluruhan (bulan semasa + 12 bulan tahunan)';

  @override
  String get confirmUpgrade => 'Sahkan Naik Taraf';

  @override
  String get confirmPlanChange => 'Sahkan Perubahan Pelan';

  @override
  String get confirmAndProceed => 'Sahkan & Teruskan';

  @override
  String get upgradeScheduled => 'Naik Taraf Dijadualkan';

  @override
  String get changePlan => 'Tukar Pelan';

  @override
  String get upgradeAlreadyScheduled => 'Naik taraf anda ke pelan tahunan sudah dijadualkan';

  @override
  String get youAreOnUnlimitedPlan => 'Anda berada di Pelan Tanpa Had.';

  @override
  String get yourOmiUnleashed => 'Omi anda, dibebaskan. Pilih tanpa had untuk kemungkinan tanpa batas.';

  @override
  String planEndedOn(String date) {
    return 'Pelan anda tamat pada $date.\\nLanggan semula sekarang - anda akan dicaj serta-merta untuk tempoh pengebilan baharu.';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'Pelan anda ditetapkan untuk dibatalkan pada $date.\\nLanggan semula sekarang untuk mengekalkan manfaat anda - tiada caj sehingga $date.';
  }

  @override
  String get annualPlanStartsAutomatically =>
      'Pelan tahunan anda akan bermula secara automatik apabila pelan bulanan anda tamat.';

  @override
  String planRenewsOn(String date) {
    return 'Pelan anda diperbaharui pada $date.';
  }

  @override
  String get unlimitedConversations => 'Perbualan tanpa had';

  @override
  String get askOmiAnything => 'Tanya Omi apa sahaja tentang hidup anda';

  @override
  String get unlockOmiInfiniteMemory => 'Buka kunci memori tak terhingga Omi';

  @override
  String get youreOnAnnualPlan => 'Anda berada di Pelan Tahunan';

  @override
  String get alreadyBestValuePlan => 'Anda sudah mempunyai pelan nilai terbaik. Tiada perubahan diperlukan.';

  @override
  String get unableToLoadPlans => 'Tidak dapat memuatkan pelan';

  @override
  String get checkConnectionTryAgain => 'Sila semak sambungan anda dan cuba lagi';

  @override
  String get useFreePlan => 'Gunakan Pelan Percuma';

  @override
  String get continueText => 'Teruskan';

  @override
  String get resubscribe => 'Langgan semula';

  @override
  String get couldNotOpenPaymentSettings => 'Tidak dapat membuka tetapan pembayaran. Sila cuba lagi.';

  @override
  String get managePaymentMethod => 'Urus Kaedah Pembayaran';

  @override
  String get cancelSubscription => 'Batalkan Langganan';

  @override
  String endsOnDate(String date) {
    return 'Tamat pada $date';
  }

  @override
  String get active => 'Aktif';

  @override
  String get freePlan => 'Pelan Percuma';

  @override
  String get configure => 'Konfigurasi';

  @override
  String get privacyInformation => 'Maklumat Privasi';

  @override
  String get yourPrivacyMattersToUs => 'Privasi Anda Penting bagi Kami';

  @override
  String get privacyIntroText =>
      'Di Omi, kami mengambil privasi anda dengan sangat serius. Kami ingin telus tentang data yang kami kumpul dan cara kami menggunakannya. Inilah yang perlu anda ketahui:';

  @override
  String get whatWeTrack => 'Apa yang Kami Jejaki';

  @override
  String get anonymityAndPrivacy => 'Anonimiti dan Privasi';

  @override
  String get optInAndOptOutOptions => 'Pilihan Ikut Serta dan Tidak Ikut Serta';

  @override
  String get ourCommitment => 'Komitmen Kami';

  @override
  String get commitmentText =>
      'Kami komited untuk menggunakan data yang kami kumpul hanya untuk menjadikan Omi produk yang lebih baik untuk anda. Privasi dan kepercayaan anda adalah yang paling penting bagi kami.';

  @override
  String get thankYouText =>
      'Terima kasih kerana menjadi pengguna Omi yang dihargai. Jika anda mempunyai sebarang soalan atau kebimbangan, sila hubungi kami di team@basedhardware.com.';

  @override
  String get wifiSyncSettings => 'Tetapan Segerak WiFi';

  @override
  String get enterHotspotCredentials => 'Masukkan kelayakan hotspot telefon anda';

  @override
  String get wifiSyncUsesHotspot =>
      'Segerak WiFi menggunakan telefon anda sebagai hotspot. Cari nama dan kata laluan di Tetapan > Hotspot Peribadi.';

  @override
  String get hotspotNameSsid => 'Nama Hotspot (SSID)';

  @override
  String get exampleIphoneHotspot => 'cth. iPhone Hotspot';

  @override
  String get password => 'Kata Laluan';

  @override
  String get enterHotspotPassword => 'Masukkan kata laluan hotspot';

  @override
  String get saveCredentials => 'Simpan Kelayakan';

  @override
  String get clearCredentials => 'Kosongkan Kelayakan';

  @override
  String get pleaseEnterHotspotName => 'Sila masukkan nama hotspot';

  @override
  String get wifiCredentialsSaved => 'Kelayakan WiFi disimpan';

  @override
  String get wifiCredentialsCleared => 'Kelayakan WiFi dikosongkan';

  @override
  String summaryGeneratedForDate(String date) {
    return 'Ringkasan dijana untuk $date';
  }

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'Gagal menjana ringkasan. Pastikan anda mempunyai perbualan untuk hari itu.';

  @override
  String get summaryNotFound => 'Ringkasan tidak ditemui';

  @override
  String get yourDaysJourney => 'Perjalanan Hari Anda';

  @override
  String get highlights => 'Sorotan';

  @override
  String get unresolvedQuestions => 'Soalan Tidak Selesai';

  @override
  String get decisions => 'Keputusan';

  @override
  String get learnings => 'Pembelajaran';

  @override
  String get autoDeletesAfterThreeDays => 'Padam automatik selepas 3 hari.';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'Graf Pengetahuan berjaya dipadamkan';

  @override
  String get exportStartedMayTakeFewSeconds => 'Eksport dimulakan. Ini mungkin mengambil beberapa saat...';

  @override
  String get knowledgeGraphDeleteDescription =>
      'Ini akan memadamkan semua data graf pengetahuan terbitan (nod dan sambungan). Memori asal anda akan kekal selamat. Graf akan dibina semula dari semasa ke semasa atau atas permintaan seterusnya.';

  @override
  String get configureDailySummaryDigest => 'Konfigurasikan ringkasan tugas harian anda';

  @override
  String accessesDataTypes(String dataTypes) {
    return 'Mengakses $dataTypes';
  }

  @override
  String triggeredByType(String triggerType) {
    return 'dicetuskan oleh $triggerType';
  }

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription dan $triggerDescription.';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return '$triggerDescription.';
  }

  @override
  String get noSpecificDataAccessConfigured => 'Tiada akses data khusus dikonfigurasi.';

  @override
  String get basicPlanDescription => '1,200 minit premium + tanpa had pada peranti';

  @override
  String get minutes => 'minit';

  @override
  String get omiHas => 'Omi mempunyai:';

  @override
  String get premiumMinutesUsed => 'Minit premium digunakan.';

  @override
  String get setupOnDevice => 'Sediakan pada peranti';

  @override
  String get forUnlimitedFreeTranscription => 'untuk transkripsi percuma tanpa had.';

  @override
  String premiumMinsLeft(int count) {
    return '$count minit premium berbaki.';
  }

  @override
  String get alwaysAvailable => 'sentiasa tersedia.';

  @override
  String get importHistory => 'Sejarah Import';

  @override
  String get noImportsYet => 'Tiada import lagi';

  @override
  String get selectZipFileToImport => 'Pilih fail .zip untuk diimport!';

  @override
  String get otherDevicesComingSoon => 'Peranti lain akan datang';

  @override
  String get deleteAllLimitlessConversations => 'Padam Semua Perbualan Limitless?';

  @override
  String get deleteAllLimitlessWarning =>
      'Ini akan memadam secara kekal semua perbualan yang diimport dari Limitless. Tindakan ini tidak boleh dibuat asal.';

  @override
  String deletedLimitlessConversations(int count) {
    return 'Dipadam $count perbualan Limitless';
  }

  @override
  String get failedToDeleteConversations => 'Gagal memadam perbualan';

  @override
  String get deleteImportedData => 'Padam Data yang Diimport';

  @override
  String get statusPending => 'Menunggu';

  @override
  String get statusProcessing => 'Memproses';

  @override
  String get statusCompleted => 'Selesai';

  @override
  String get statusFailed => 'Gagal';

  @override
  String nConversations(int count) {
    return '$count perbualan';
  }

  @override
  String get pleaseEnterName => 'Sila masukkan nama';

  @override
  String get nameMustBeBetweenCharacters => 'Nama mestilah antara 2 dan 40 aksara';

  @override
  String get deleteSampleQuestion => 'Padam Sampel?';

  @override
  String deleteSampleConfirmation(String name) {
    return 'Adakah anda pasti mahu memadam sampel $name?';
  }

  @override
  String get confirmDeletion => 'Sahkan Pemadaman';

  @override
  String deletePersonConfirmation(String name) {
    return 'Adakah anda pasti mahu memadam $name? Ini juga akan membuang semua sampel pertuturan yang berkaitan.';
  }

  @override
  String get howItWorksTitle => 'Bagaimana ia berfungsi?';

  @override
  String get howPeopleWorks =>
      'Sebaik sahaja seseorang dicipta, anda boleh pergi ke transkrip perbualan dan menetapkan segmen yang sepadan kepada mereka, dengan cara itu Omi akan dapat mengenali pertuturan mereka juga!';

  @override
  String get tapToDelete => 'Ketik untuk memadam';

  @override
  String get newTag => 'BAHARU';

  @override
  String get needHelpChatWithUs => 'Perlukan bantuan? Berbual dengan kami';

  @override
  String get localStorageEnabled => 'Storan tempatan diaktifkan';

  @override
  String get localStorageDisabled => 'Storan tempatan dinyahaktifkan';

  @override
  String failedToUpdateSettings(String error) {
    return 'Gagal mengemas kini tetapan: $error';
  }

  @override
  String get privacyNotice => 'Notis Privasi';

  @override
  String get recordingsMayCaptureOthers =>
      'Rakaman mungkin menangkap suara orang lain. Pastikan anda mendapat persetujuan daripada semua peserta sebelum mengaktifkan.';

  @override
  String get enable => 'Aktifkan';

  @override
  String get storeAudioOnPhone => 'Simpan Audio di Telefon';

  @override
  String get on => 'On';

  @override
  String get storeAudioDescription =>
      'Simpan semua rakaman audio secara tempatan di telefon anda. Apabila dilumpuhkan, hanya muat naik yang gagal disimpan untuk menjimatkan ruang storan.';

  @override
  String get enableLocalStorage => 'Aktifkan Storan Tempatan';

  @override
  String get cloudStorageEnabled => 'Storan awan diaktifkan';

  @override
  String get cloudStorageDisabled => 'Storan awan dinyahaktifkan';

  @override
  String get enableCloudStorage => 'Aktifkan Storan Awan';

  @override
  String get storeAudioOnCloud => 'Simpan Audio di Awan';

  @override
  String get cloudStorageDialogMessage =>
      'Rakaman masa nyata anda akan disimpan dalam storan awan peribadi semasa anda bercakap.';

  @override
  String get storeAudioCloudDescription =>
      'Simpan rakaman masa nyata anda dalam storan awan peribadi semasa anda bercakap. Audio ditangkap dan disimpan dengan selamat dalam masa nyata.';

  @override
  String get downloadingFirmware => 'Memuat turun Perisian Tegar';

  @override
  String get installingFirmware => 'Memasang Perisian Tegar';

  @override
  String get firmwareUpdateWarning => 'Jangan tutup aplikasi atau matikan peranti. Ini boleh merosakkan peranti anda.';

  @override
  String get firmwareUpdated => 'Perisian Tegar Dikemas Kini';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'Sila mulakan semula $deviceName anda untuk melengkapkan kemas kini.';
  }

  @override
  String get yourDeviceIsUpToDate => 'Peranti anda adalah terkini';

  @override
  String get currentVersion => 'Versi Semasa';

  @override
  String get latestVersion => 'Versi Terkini';

  @override
  String get whatsNew => 'Apa yang Baharu';

  @override
  String get installUpdate => 'Pasang Kemas Kini';

  @override
  String get updateNow => 'Kemas Kini Sekarang';

  @override
  String get updateGuide => 'Panduan Kemas Kini';

  @override
  String get checkingForUpdates => 'Menyemak Kemas Kini';

  @override
  String get checkingFirmwareVersion => 'Menyemak versi perisian tegar...';

  @override
  String get firmwareUpdate => 'Kemas Kini Perisian Tegar';

  @override
  String get payments => 'Pembayaran';

  @override
  String get connectPaymentMethodInfo =>
      'Sambungkan kaedah pembayaran di bawah untuk mula menerima pembayaran untuk aplikasi anda.';

  @override
  String get selectedPaymentMethod => 'Kaedah Pembayaran Dipilih';

  @override
  String get availablePaymentMethods => 'Kaedah Pembayaran Tersedia';

  @override
  String get activeStatus => 'Aktif';

  @override
  String get connectedStatus => 'Disambungkan';

  @override
  String get notConnectedStatus => 'Tidak Disambungkan';

  @override
  String get setActive => 'Tetapkan Aktif';

  @override
  String get getPaidThroughStripe => 'Dapatkan bayaran untuk jualan aplikasi anda melalui Stripe';

  @override
  String get monthlyPayouts => 'Pembayaran bulanan';

  @override
  String get monthlyPayoutsDescription =>
      'Terima bayaran bulanan terus ke akaun anda apabila mencapai \$10 dalam pendapatan';

  @override
  String get secureAndReliable => 'Selamat dan boleh dipercayai';

  @override
  String get stripeSecureDescription =>
      'Stripe memastikan pemindahan hasil aplikasi anda yang selamat dan tepat pada masanya';

  @override
  String get selectYourCountry => 'Pilih negara anda';

  @override
  String get countrySelectionPermanent => 'Pilihan negara anda adalah kekal dan tidak boleh ditukar kemudian.';

  @override
  String get byClickingConnectNow => 'Dengan mengklik \"Sambung Sekarang\" anda bersetuju dengan';

  @override
  String get stripeConnectedAccountAgreement => 'Perjanjian Akaun Bersambung Stripe';

  @override
  String get errorConnectingToStripe => 'Ralat menyambung ke Stripe! Sila cuba lagi kemudian.';

  @override
  String get connectingYourStripeAccount => 'Menyambungkan akaun Stripe anda';

  @override
  String get stripeOnboardingInstructions =>
      'Sila lengkapkan proses penerimaan Stripe dalam pelayar anda. Halaman ini akan dikemas kini secara automatik setelah selesai.';

  @override
  String get failedTryAgain => 'Gagal? Cuba Lagi';

  @override
  String get illDoItLater => 'Saya akan lakukannya nanti';

  @override
  String get successfullyConnected => 'Berjaya Disambungkan!';

  @override
  String get stripeReadyForPayments =>
      'Akaun Stripe anda kini sedia menerima pembayaran. Anda boleh mula menjana pendapatan daripada jualan aplikasi anda dengan segera.';

  @override
  String get updateStripeDetails => 'Kemas Kini Butiran Stripe';

  @override
  String get errorUpdatingStripeDetails => 'Ralat mengemas kini butiran Stripe! Sila cuba lagi kemudian.';

  @override
  String get updatePayPal => 'Kemas Kini PayPal';

  @override
  String get setUpPayPal => 'Sediakan PayPal';

  @override
  String get updatePayPalAccountDetails => 'Kemas kini butiran akaun PayPal anda';

  @override
  String get connectPayPalToReceivePayments =>
      'Sambungkan akaun PayPal anda untuk mula menerima pembayaran untuk aplikasi anda';

  @override
  String get paypalEmail => 'E-mel PayPal';

  @override
  String get paypalMeLink => 'Pautan PayPal.me';

  @override
  String get stripeRecommendation =>
      'Jika Stripe tersedia di negara anda, kami sangat mengesyorkan menggunakannya untuk pembayaran yang lebih cepat dan mudah.';

  @override
  String get updatePayPalDetails => 'Kemas Kini Butiran PayPal';

  @override
  String get savePayPalDetails => 'Simpan Butiran PayPal';

  @override
  String get pleaseEnterPayPalEmail => 'Sila masukkan e-mel PayPal anda';

  @override
  String get pleaseEnterPayPalMeLink => 'Sila masukkan pautan PayPal.me anda';

  @override
  String get doNotIncludeHttpInLink => 'Jangan sertakan http atau https atau www dalam pautan';

  @override
  String get pleaseEnterValidPayPalMeLink => 'Sila masukkan pautan PayPal.me yang sah';

  @override
  String get pleaseEnterValidEmail => 'Sila masukkan alamat e-mel yang sah';

  @override
  String get syncingYourRecordings => 'Menyegerakkan rakaman anda';

  @override
  String get syncYourRecordings => 'Segerakkan rakaman anda';

  @override
  String get syncNow => 'Segerak sekarang';

  @override
  String get error => 'Ralat';

  @override
  String get speechSamples => 'Sampel suara';

  @override
  String additionalSampleIndex(String index) {
    return 'Sampel tambahan $index';
  }

  @override
  String durationSeconds(String seconds) {
    return 'Tempoh: $seconds saat';
  }

  @override
  String get additionalSpeechSampleRemoved => 'Sampel suara tambahan dibuang';

  @override
  String get consentDataMessage =>
      'Dengan meneruskan, semua data yang anda kongsi dengan aplikasi ini (termasuk perbualan, rakaman dan maklumat peribadi anda) akan disimpan dengan selamat di pelayan kami untuk memberikan anda cerapan berkuasa AI dan membolehkan semua ciri aplikasi.';

  @override
  String get tasksEmptyStateMessage =>
      'Tugasan daripada perbualan anda akan muncul di sini.\nKetik + untuk mencipta secara manual.';

  @override
  String get clearChatAction => 'Kosongkan sembang';

  @override
  String get enableApps => 'Dayakan aplikasi';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => 'tunjukkan lagi ↓';

  @override
  String get showLess => 'tunjukkan kurang ↑';

  @override
  String get loadingYourRecording => 'Memuatkan rakaman anda...';

  @override
  String get photoDiscardedMessage => 'Foto ini telah dibuang kerana tidak penting.';

  @override
  String get analyzing => 'Menganalisis...';

  @override
  String get searchCountries => 'Cari negara...';

  @override
  String get checkingAppleWatch => 'Menyemak Apple Watch...';

  @override
  String get installOmiOnAppleWatch => 'Pasang Omi pada\nApple Watch anda';

  @override
  String get installOmiOnAppleWatchDescription =>
      'Untuk menggunakan Apple Watch dengan Omi, anda perlu memasang aplikasi Omi pada jam tangan anda terlebih dahulu.';

  @override
  String get openOmiOnAppleWatch => 'Buka Omi pada\nApple Watch anda';

  @override
  String get openOmiOnAppleWatchDescription =>
      'Aplikasi Omi dipasang pada Apple Watch anda. Buka dan ketik Mula untuk bermula.';

  @override
  String get openWatchApp => 'Buka Aplikasi Watch';

  @override
  String get iveInstalledAndOpenedTheApp => 'Saya Telah Memasang & Membuka Aplikasi';

  @override
  String get unableToOpenWatchApp =>
      'Tidak dapat membuka aplikasi Apple Watch. Sila buka aplikasi Watch secara manual pada Apple Watch anda dan pasang Omi dari bahagian \"Aplikasi Tersedia\".';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch berjaya disambungkan!';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch masih tidak dapat dicapai. Pastikan aplikasi Omi dibuka pada jam tangan anda.';

  @override
  String errorCheckingConnection(String error) {
    return 'Ralat menyemak sambungan: $error';
  }

  @override
  String get muted => 'Dibisukan';

  @override
  String get processNow => 'Proses sekarang';

  @override
  String get finishedConversation => 'Perbualan selesai?';

  @override
  String get stopRecordingConfirmation =>
      'Adakah anda pasti mahu menghentikan rakaman dan meringkaskan perbualan sekarang?';

  @override
  String get conversationEndsManually => 'Perbualan hanya akan tamat secara manual.';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'Perbualan diringkaskan selepas $minutes minit$suffix tanpa pertuturan.';
  }

  @override
  String get dontAskAgain => 'Jangan tanya lagi';

  @override
  String get waitingForTranscriptOrPhotos => 'Menunggu transkrip atau foto...';

  @override
  String get noSummaryYet => 'Belum ada ringkasan';

  @override
  String hints(String text) {
    return 'Petunjuk: $text';
  }

  @override
  String get testConversationPrompt => 'Uji prompt perbualan';

  @override
  String get prompt => 'Gesaan';

  @override
  String get result => 'Hasil:';

  @override
  String get compareTranscripts => 'Bandingkan transkrip';

  @override
  String get notHelpful => 'Tidak membantu';

  @override
  String get exportTasksWithOneTap => 'Eksport tugas dengan satu ketukan!';

  @override
  String get inProgress => 'Sedang diproses';

  @override
  String get photos => 'Foto';

  @override
  String get rawData => 'Data Mentah';

  @override
  String get content => 'Kandungan';

  @override
  String get noContentToDisplay => 'Tiada kandungan untuk dipaparkan';

  @override
  String get noSummary => 'Tiada ringkasan';

  @override
  String get updateOmiFirmware => 'Kemas kini perisian tegar omi';

  @override
  String get anErrorOccurredTryAgain => 'Ralat berlaku. Sila cuba lagi.';

  @override
  String get welcomeBackSimple => 'Selamat kembali';

  @override
  String get addVocabularyDescription => 'Tambah perkataan yang Omi perlu kenali semasa transkripsi.';

  @override
  String get enterWordsCommaSeparated => 'Masukkan perkataan (dipisahkan koma)';

  @override
  String get whenToReceiveDailySummary => 'Bila untuk menerima ringkasan harian anda';

  @override
  String get checkingNextSevenDays => 'Menyemak 7 hari akan datang';

  @override
  String failedToDeleteError(String error) {
    return 'Gagal memadam: $error';
  }

  @override
  String get developerApiKeys => 'Kunci API Pembangun';

  @override
  String get noApiKeysCreateOne => 'Tiada kunci API. Cipta satu untuk bermula.';

  @override
  String get commandRequired => '⌘ diperlukan';

  @override
  String get spaceKey => 'Ruang';

  @override
  String loadMoreRemaining(String count) {
    return 'Muat lagi ($count lagi)';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'Top $percentile% Pengguna';
  }

  @override
  String get wrappedMinutes => 'minit';

  @override
  String get wrappedConversations => 'perbualan';

  @override
  String get wrappedDaysActive => 'hari aktif';

  @override
  String get wrappedYouTalkedAbout => 'Anda berbual tentang';

  @override
  String get wrappedActionItems => 'Tugasan';

  @override
  String get wrappedTasksCreated => 'tugasan dicipta';

  @override
  String get wrappedCompleted => 'selesai';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% kadar penyelesaian';
  }

  @override
  String get wrappedYourTopDays => 'Hari terbaik anda';

  @override
  String get wrappedBestMoments => 'Detik terbaik';

  @override
  String get wrappedMyBuddies => 'Rakan-rakan saya';

  @override
  String get wrappedCouldntStopTalkingAbout => 'Tidak dapat berhenti bercakap tentang';

  @override
  String get wrappedShow => 'RANCANGAN';

  @override
  String get wrappedMovie => 'FILEM';

  @override
  String get wrappedBook => 'BUKU';

  @override
  String get wrappedCelebrity => 'SELEBRITI';

  @override
  String get wrappedFood => 'MAKANAN';

  @override
  String get wrappedMovieRecs => 'Cadangan filem untuk rakan';

  @override
  String get wrappedBiggest => 'Terbesar';

  @override
  String get wrappedStruggle => 'Cabaran';

  @override
  String get wrappedButYouPushedThrough => 'Tetapi anda berjaya 💪';

  @override
  String get wrappedWin => 'Kemenangan';

  @override
  String get wrappedYouDidIt => 'Anda berjaya! 🎉';

  @override
  String get wrappedTopPhrases => 'Top 5 frasa';

  @override
  String get wrappedMins => 'min';

  @override
  String get wrappedConvos => 'perbualan';

  @override
  String get wrappedDays => 'hari';

  @override
  String get wrappedMyBuddiesLabel => 'RAKAN-RAKAN SAYA';

  @override
  String get wrappedObsessionsLabel => 'OBSESI';

  @override
  String get wrappedStruggleLabel => 'CABARAN';

  @override
  String get wrappedWinLabel => 'KEMENANGAN';

  @override
  String get wrappedTopPhrasesLabel => 'TOP FRASA';

  @override
  String get wrappedLetsHitRewind => 'Mari kita putar semula';

  @override
  String get wrappedGenerateMyWrapped => 'Jana Wrapped Saya';

  @override
  String get wrappedProcessingDefault => 'Memproses...';

  @override
  String get wrappedCreatingYourStory => 'Mencipta\ncerita 2025 anda...';

  @override
  String get wrappedSomethingWentWrong => 'Sesuatu telah\nberlaku';

  @override
  String get wrappedAnErrorOccurred => 'Ralat berlaku';

  @override
  String get wrappedTryAgain => 'Cuba Lagi';

  @override
  String get wrappedNoDataAvailable => 'Tiada data tersedia';

  @override
  String get wrappedOmiLifeRecap => 'Rumusan Hidup Omi';

  @override
  String get wrappedSwipeUpToBegin => 'Leret ke atas untuk mula';

  @override
  String get wrappedShareText => '2025 saya, diingati oleh Omi ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare => 'Gagal berkongsi. Sila cuba lagi.';

  @override
  String get wrappedFailedToStartGeneration => 'Gagal memulakan penjanaan. Sila cuba lagi.';

  @override
  String get wrappedStarting => 'Memulakan...';

  @override
  String get wrappedShare => 'Kongsi';

  @override
  String get wrappedShareYourWrapped => 'Kongsi Wrapped Anda';

  @override
  String get wrappedMy2025 => '2025 Saya';

  @override
  String get wrappedRememberedByOmi => 'diingati oleh Omi';

  @override
  String get wrappedMostFunDay => 'Paling Seronok';

  @override
  String get wrappedMostProductiveDay => 'Paling Produktif';

  @override
  String get wrappedMostIntenseDay => 'Paling Sengit';

  @override
  String get wrappedFunniestMoment => 'Paling Lucu';

  @override
  String get wrappedMostCringeMoment => 'Paling Memalukan';

  @override
  String get wrappedMinutesLabel => 'minit';

  @override
  String get wrappedConversationsLabel => 'perbualan';

  @override
  String get wrappedDaysActiveLabel => 'hari aktif';

  @override
  String get wrappedTasksGenerated => 'tugasan dijana';

  @override
  String get wrappedTasksCompleted => 'tugasan selesai';

  @override
  String get wrappedTopFivePhrases => 'Top 5 Frasa';

  @override
  String get wrappedAGreatDay => 'Hari Yang Hebat';

  @override
  String get wrappedGettingItDone => 'Menyiapkannya';

  @override
  String get wrappedAChallenge => 'Satu Cabaran';

  @override
  String get wrappedAHilariousMoment => 'Detik Lucu';

  @override
  String get wrappedThatAwkwardMoment => 'Detik Janggal Itu';

  @override
  String get wrappedYouHadFunnyMoments => 'Anda ada detik lucu tahun ini!';

  @override
  String get wrappedWeveAllBeenThere => 'Kita semua pernah alaminya!';

  @override
  String get wrappedFriend => 'Rakan';

  @override
  String get wrappedYourBuddy => 'Kawan anda!';

  @override
  String get wrappedNotMentioned => 'Tidak disebut';

  @override
  String get wrappedTheHardPart => 'Bahagian Sukar';

  @override
  String get wrappedPersonalGrowth => 'Pertumbuhan Peribadi';

  @override
  String get wrappedFunDay => 'Seronok';

  @override
  String get wrappedProductiveDay => 'Produktif';

  @override
  String get wrappedIntenseDay => 'Sengit';

  @override
  String get wrappedFunnyMomentTitle => 'Detik Lucu';

  @override
  String get wrappedCringeMomentTitle => 'Detik Memalukan';

  @override
  String get wrappedYouTalkedAboutBadge => 'Anda Bercakap Tentang';

  @override
  String get wrappedCompletedLabel => 'Selesai';

  @override
  String get wrappedMyBuddiesCard => 'Kawan-kawan Saya';

  @override
  String get wrappedBuddiesLabel => 'KAWAN';

  @override
  String get wrappedObsessionsLabelUpper => 'OBSESI';

  @override
  String get wrappedStruggleLabelUpper => 'CABARAN';

  @override
  String get wrappedWinLabelUpper => 'KEMENANGAN';

  @override
  String get wrappedTopPhrasesLabelUpper => 'TOP FRASA';

  @override
  String get wrappedYourHeader => 'Hari';

  @override
  String get wrappedTopDaysHeader => 'Terbaik Anda';

  @override
  String get wrappedYourTopDaysBadge => 'Hari Terbaik Anda';

  @override
  String get wrappedBestHeader => 'Terbaik';

  @override
  String get wrappedMomentsHeader => 'Detik';

  @override
  String get wrappedBestMomentsBadge => 'Detik Terbaik';

  @override
  String get wrappedBiggestHeader => 'Terbesar';

  @override
  String get wrappedStruggleHeader => 'Cabaran';

  @override
  String get wrappedWinHeader => 'Kemenangan';

  @override
  String get wrappedButYouPushedThroughEmoji => 'Tetapi anda berjaya 💪';

  @override
  String get wrappedYouDidItEmoji => 'Anda berjaya! 🎉';

  @override
  String get wrappedHours => 'jam';

  @override
  String get wrappedActions => 'tindakan';

  @override
  String get multipleSpeakersDetected => 'Berbilang penutur dikesan';

  @override
  String get multipleSpeakersDescription =>
      'Nampaknya terdapat berbilang penutur dalam rakaman. Sila pastikan anda berada di tempat yang tenang dan cuba lagi.';

  @override
  String get invalidRecordingDetected => 'Rakaman tidak sah dikesan';

  @override
  String get notEnoughSpeechDescription => 'Tidak cukup pertuturan dikesan. Sila bercakap lebih banyak dan cuba lagi.';

  @override
  String get speechDurationDescription =>
      'Sila pastikan anda bercakap sekurang-kurangnya 5 saat dan tidak lebih dari 90.';

  @override
  String get connectionLostDescription => 'Sambungan terputus. Sila semak sambungan internet anda dan cuba lagi.';

  @override
  String get howToTakeGoodSample => 'Bagaimana untuk membuat sampel yang baik?';

  @override
  String get goodSampleInstructions =>
      '1. Pastikan anda berada di tempat yang tenang.\n2. Bercakap dengan jelas dan semula jadi.\n3. Pastikan peranti anda berada dalam kedudukan semula jadi di leher anda.\n\nSetelah dicipta, anda sentiasa boleh memperbaikinya atau membuatnya semula.';

  @override
  String get noDeviceConnectedUseMic => 'Tiada peranti disambungkan. Mikrofon telefon akan digunakan.';

  @override
  String get doItAgain => 'Buat lagi';

  @override
  String get listenToSpeechProfile => 'Dengar profil suara saya ➡️';

  @override
  String get recognizingOthers => 'Mengenali orang lain 👀';

  @override
  String get keepGoingGreat => 'Teruskan, anda melakukannya dengan baik';

  @override
  String get somethingWentWrongTryAgain => 'Sesuatu telah berlaku! Sila cuba lagi kemudian.';

  @override
  String get uploadingVoiceProfile => 'Memuat naik profil suara anda....';

  @override
  String get memorizingYourVoice => 'Mengingati suara anda...';

  @override
  String get personalizingExperience => 'Memperibadikan pengalaman anda...';

  @override
  String get keepSpeakingUntil100 => 'Teruskan bercakap sehingga mencapai 100%.';

  @override
  String get greatJobAlmostThere => 'Kerja yang baik, hampir siap';

  @override
  String get soCloseJustLittleMore => 'Sangat hampir, sedikit lagi';

  @override
  String get notificationFrequency => 'Kekerapan Pemberitahuan';

  @override
  String get controlNotificationFrequency => 'Kawal kekerapan Omi menghantar pemberitahuan proaktif kepada anda.';

  @override
  String get yourScore => 'Skor anda';

  @override
  String get dailyScoreBreakdown => 'Pecahan Skor Harian';

  @override
  String get todaysScore => 'Skor Hari Ini';

  @override
  String get tasksCompleted => 'Tugasan Selesai';

  @override
  String get completionRate => 'Kadar Penyelesaian';

  @override
  String get howItWorks => 'Bagaimana ia berfungsi';

  @override
  String get dailyScoreExplanation =>
      'Skor harian anda berdasarkan penyelesaian tugasan. Selesaikan tugasan anda untuk meningkatkan skor!';

  @override
  String get notificationFrequencyDescription =>
      'Kawal kekerapan Omi menghantar pemberitahuan dan peringatan proaktif kepada anda.';

  @override
  String get sliderOff => 'Mati';

  @override
  String get sliderMax => 'Maks.';

  @override
  String summaryGeneratedFor(String date) {
    return 'Ringkasan dijana untuk $date';
  }

  @override
  String get failedToGenerateSummary =>
      'Gagal menjana ringkasan. Pastikan anda mempunyai perbualan untuk hari tersebut.';

  @override
  String get recap => 'Ringkasan';

  @override
  String deleteQuoted(String name) {
    return 'Padam \"$name\"';
  }

  @override
  String moveConversationsTo(int count) {
    return 'Pindahkan $count perbualan ke:';
  }

  @override
  String get noFolder => 'Tiada folder';

  @override
  String get removeFromAllFolders => 'Alih keluar dari semua folder';

  @override
  String get buildAndShareYourCustomApp => 'Bina dan kongsi aplikasi tersuai anda';

  @override
  String get searchAppsPlaceholder => 'Cari 1500+ Aplikasi';

  @override
  String get filters => 'Penapis';

  @override
  String get frequencyOff => 'Mati';

  @override
  String get frequencyMinimal => 'Minimum';

  @override
  String get frequencyLow => 'Rendah';

  @override
  String get frequencyBalanced => 'Seimbang';

  @override
  String get frequencyHigh => 'Tinggi';

  @override
  String get frequencyMaximum => 'Maksimum';

  @override
  String get frequencyDescOff => 'Tiada pemberitahuan proaktif';

  @override
  String get frequencyDescMinimal => 'Hanya peringatan kritikal';

  @override
  String get frequencyDescLow => 'Hanya kemas kini penting';

  @override
  String get frequencyDescBalanced => 'Peringatan berguna biasa';

  @override
  String get frequencyDescHigh => 'Pemeriksaan kerap';

  @override
  String get frequencyDescMaximum => 'Kekal sentiasa terlibat';

  @override
  String get clearChatQuestion => 'Padam sembang?';

  @override
  String get syncingMessages => 'Menyegerakkan mesej dengan pelayan...';

  @override
  String get chatAppsTitle => 'Aplikasi Sembang';

  @override
  String get selectApp => 'Pilih Aplikasi';

  @override
  String get noChatAppsEnabled => 'Tiada aplikasi sembang diaktifkan.\nKetik \"Aktifkan Aplikasi\" untuk menambah.';

  @override
  String get disable => 'Nyahaktif';

  @override
  String get photoLibrary => 'Pustaka Foto';

  @override
  String get chooseFile => 'Pilih Fail';

  @override
  String get configureAiPersona => 'Konfigurasikan persona AI anda';

  @override
  String get connectAiAssistantsToYourData => 'Sambungkan pembantu AI ke data anda';

  @override
  String get oAuth => 'OAuth';

  @override
  String get trackYourGoalsOnHomepage => 'Jejaki matlamat peribadi anda di halaman utama';

  @override
  String get deleteRecording => 'Padam Rakaman';

  @override
  String get thisCannotBeUndone => 'Tindakan ini tidak boleh dibatalkan.';

  @override
  String get sdCard => 'Kad SD';

  @override
  String get fromSd => 'Dari SD';

  @override
  String get limitless => 'Limitless';

  @override
  String get fastTransfer => 'Pemindahan Pantas';

  @override
  String get syncingStatus => 'Menyegerakkan';

  @override
  String get failedStatus => 'Gagal';

  @override
  String etaLabel(String time) {
    return 'Anggaran: $time';
  }

  @override
  String get transferMethod => 'Kaedah Pemindahan';

  @override
  String get fast => 'Pantas';

  @override
  String get ble => 'BLE';

  @override
  String get phone => 'Telefon';

  @override
  String get cancelSync => 'Batal Segerak';

  @override
  String get cancelSyncMessage => 'Data yang sudah dimuat turun akan disimpan. Anda boleh sambung semula kemudian.';

  @override
  String get syncCancelled => 'Penyegerakan dibatalkan';

  @override
  String get deleteProcessedFiles => 'Padam Fail yang Diproses';

  @override
  String get processedFilesDeleted => 'Fail yang diproses telah dipadam';

  @override
  String get wifiEnableFailed => 'Gagal mengaktifkan WiFi pada peranti. Sila cuba lagi.';

  @override
  String get deviceNoFastTransfer => 'Peranti anda tidak menyokong Pemindahan Pantas. Gunakan Bluetooth sebaliknya.';

  @override
  String get enableHotspotMessage => 'Sila aktifkan hotspot telefon anda dan cuba lagi.';

  @override
  String get transferStartFailed => 'Gagal memulakan pemindahan. Sila cuba lagi.';

  @override
  String get deviceNotResponding => 'Peranti tidak bertindak balas. Sila cuba lagi.';

  @override
  String get invalidWifiCredentials => 'Kelayakan WiFi tidak sah. Semak tetapan hotspot anda.';

  @override
  String get wifiConnectionFailed => 'Sambungan WiFi gagal. Sila cuba lagi.';

  @override
  String get sdCardProcessing => 'Memproses Kad SD';

  @override
  String sdCardProcessingMessage(int count) {
    return 'Memproses $count rakaman. Fail akan dipadam dari kad SD selepas itu.';
  }

  @override
  String get process => 'Proses';

  @override
  String get wifiSyncFailed => 'Segerak WiFi Gagal';

  @override
  String get processingFailed => 'Pemprosesan Gagal';

  @override
  String get downloadingFromSdCard => 'Memuat turun dari Kad SD';

  @override
  String processingProgress(int current, int total) {
    return 'Memproses $current/$total';
  }

  @override
  String conversationsCreated(int count) {
    return '$count perbualan dicipta';
  }

  @override
  String get internetRequired => 'Internet diperlukan';

  @override
  String get processAudio => 'Proses Audio';

  @override
  String get start => 'Mula';

  @override
  String get noRecordings => 'Tiada Rakaman';

  @override
  String get audioFromOmiWillAppearHere => 'Audio dari peranti Omi anda akan muncul di sini';

  @override
  String get deleteProcessed => 'Padam yang Diproses';

  @override
  String get tryDifferentFilter => 'Cuba penapis yang berbeza';

  @override
  String get recordings => 'Rakaman';

  @override
  String get enableRemindersAccess => 'Sila aktifkan akses Peringatan dalam Tetapan untuk menggunakan Peringatan Apple';

  @override
  String todayAtTime(String time) {
    return 'Hari ini pada $time';
  }

  @override
  String yesterdayAtTime(String time) {
    return 'Semalam pada $time';
  }

  @override
  String get lessThanAMinute => 'Kurang dari seminit';

  @override
  String estimatedMinutes(int count) {
    return '~$count minit';
  }

  @override
  String estimatedHours(int count) {
    return '~$count jam';
  }

  @override
  String estimatedTimeRemaining(String time) {
    return 'Anggaran: $time berbaki';
  }

  @override
  String get summarizingConversation => 'Meringkaskan perbualan...\nIni mungkin mengambil beberapa saat';

  @override
  String get resummarizingConversation => 'Meringkaskan semula perbualan...\nIni mungkin mengambil beberapa saat';

  @override
  String get nothingInterestingRetry => 'Tiada yang menarik ditemui,\nmahu cuba lagi?';

  @override
  String get noSummaryForConversation => 'Tiada ringkasan\nuntuk perbualan ini.';

  @override
  String get unknownLocation => 'Lokasi tidak diketahui';

  @override
  String get couldNotLoadMap => 'Tidak dapat memuatkan peta';

  @override
  String get triggerConversationIntegration => 'Cetuskan integrasi penciptaan perbualan';

  @override
  String get webhookUrlNotSet => 'URL Webhook tidak ditetapkan';

  @override
  String get setWebhookUrlInSettings => 'Sila tetapkan URL webhook dalam tetapan pembangun untuk menggunakan ciri ini.';

  @override
  String get sendWebUrl => 'Hantar URL web';

  @override
  String get sendTranscript => 'Hantar transkrip';

  @override
  String get sendSummary => 'Hantar ringkasan';

  @override
  String get debugModeDetected => 'Mod nyahpepijat dikesan';

  @override
  String get performanceReduced => 'Prestasi mungkin berkurang';

  @override
  String autoClosingInSeconds(int seconds) {
    return 'Menutup secara automatik dalam $seconds saat';
  }

  @override
  String get modelRequired => 'Model diperlukan';

  @override
  String get downloadWhisperModel => 'Muat turun model whisper untuk menggunakan transkripsi pada peranti';

  @override
  String get deviceNotCompatible => 'Peranti anda tidak serasi dengan transkripsi pada peranti';

  @override
  String get deviceRequirements => 'Peranti anda tidak memenuhi keperluan untuk transkripsi Pada-Peranti.';

  @override
  String get willLikelyCrash => 'Mengaktifkan ini kemungkinan akan menyebabkan aplikasi ranap atau beku.';

  @override
  String get transcriptionSlowerLessAccurate => 'Transkripsi akan menjadi lebih perlahan dan kurang tepat.';

  @override
  String get proceedAnyway => 'Teruskan juga';

  @override
  String get olderDeviceDetected => 'Peranti Lama Dikesan';

  @override
  String get onDeviceSlower => 'Transkripsi pada-peranti mungkin lebih perlahan pada peranti ini.';

  @override
  String get batteryUsageHigher => 'Penggunaan bateri akan lebih tinggi daripada transkripsi awan.';

  @override
  String get considerOmiCloud => 'Pertimbangkan menggunakan Omi Cloud untuk prestasi yang lebih baik.';

  @override
  String get highResourceUsage => 'Penggunaan Sumber Tinggi';

  @override
  String get onDeviceIntensive => 'Transkripsi Pada-Peranti memerlukan pengiraan intensif.';

  @override
  String get batteryDrainIncrease => 'Penggunaan bateri akan meningkat dengan ketara.';

  @override
  String get deviceMayWarmUp => 'Peranti mungkin menjadi panas semasa penggunaan berpanjangan.';

  @override
  String get speedAccuracyLower => 'Kelajuan dan ketepatan mungkin lebih rendah daripada model Awan.';

  @override
  String get cloudProvider => 'Pembekal Awan';

  @override
  String get premiumMinutesInfo =>
      '1,200 minit premium/bulan. Tab Pada-Peranti menawarkan transkripsi percuma tanpa had.';

  @override
  String get viewUsage => 'Lihat penggunaan';

  @override
  String get localProcessingInfo =>
      'Audio diproses secara tempatan. Berfungsi luar talian, lebih peribadi, tetapi menggunakan lebih banyak bateri.';

  @override
  String get model => 'Model';

  @override
  String get performanceWarning => 'Amaran Prestasi';

  @override
  String get largeModelWarning =>
      'Model ini besar dan mungkin menyebabkan aplikasi ranap atau berjalan sangat perlahan pada peranti mudah alih.\n\n\"small\" atau \"base\" disyorkan.';

  @override
  String get usingNativeIosSpeech => 'Menggunakan Pengecaman Pertuturan iOS Asli';

  @override
  String get noModelDownloadRequired =>
      'Enjin pertuturan asli peranti anda akan digunakan. Tiada muat turun model diperlukan.';

  @override
  String get modelReady => 'Model Sedia';

  @override
  String get redownload => 'Muat Turun Semula';

  @override
  String get doNotCloseApp => 'Sila jangan tutup aplikasi.';

  @override
  String get downloading => 'Memuat turun...';

  @override
  String get downloadModel => 'Muat turun model';

  @override
  String estimatedSize(String size) {
    return 'Anggaran Saiz: ~$size MB';
  }

  @override
  String availableSpace(String space) {
    return 'Ruang Tersedia: $space';
  }

  @override
  String get notEnoughSpace => 'Amaran: Ruang tidak mencukupi!';

  @override
  String get download => 'Muat turun';

  @override
  String downloadError(String error) {
    return 'Ralat muat turun: $error';
  }

  @override
  String get cancelled => 'Dibatalkan';

  @override
  String get deviceNotCompatibleTitle => 'Peranti Tidak Serasi';

  @override
  String get deviceNotMeetRequirements => 'Peranti anda tidak memenuhi keperluan untuk transkripsi pada peranti.';

  @override
  String get transcriptionSlowerOnDevice => 'Transkripsi pada peranti mungkin lebih perlahan pada peranti ini.';

  @override
  String get computationallyIntensive => 'Transkripsi pada peranti adalah intensif dari segi pengiraan.';

  @override
  String get batteryDrainSignificantly => 'Pengurasan bateri akan meningkat dengan ketara.';

  @override
  String get premiumMinutesMonth =>
      '1,200 minit premium/bulan. Tab Pada Peranti menawarkan transkripsi percuma tanpa had. ';

  @override
  String get audioProcessedLocally =>
      'Audio diproses secara tempatan. Berfungsi luar talian, lebih peribadi, tetapi menggunakan lebih banyak bateri.';

  @override
  String get languageLabel => 'Bahasa';

  @override
  String get modelLabel => 'Model';

  @override
  String get modelTooLargeWarning =>
      'Model ini besar dan mungkin menyebabkan aplikasi ranap atau berjalan sangat perlahan pada peranti mudah alih.\n\nsmall atau base disyorkan.';

  @override
  String get nativeEngineNoDownload =>
      'Enjin pertuturan asli peranti anda akan digunakan. Tiada muat turun model diperlukan.';

  @override
  String modelReadyWithName(String model) {
    return 'Model Sedia ($model)';
  }

  @override
  String get reDownload => 'Muat turun semula';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return 'Memuat turun $model: $received / $total MB';
  }

  @override
  String preparingModel(String model) {
    return 'Menyediakan $model...';
  }

  @override
  String downloadErrorWithMessage(String error) {
    return 'Ralat muat turun: $error';
  }

  @override
  String estimatedSizeWithValue(String size) {
    return 'Anggaran Saiz: ~$size MB';
  }

  @override
  String availableSpaceWithValue(String space) {
    return 'Ruang Tersedia: $space';
  }

  @override
  String get omiTranscriptionOptimized =>
      'Transkripsi langsung terbina dalam Omi dioptimumkan untuk perbualan masa nyata dengan pengesanan penutur automatik dan diarisasi.';

  @override
  String get reset => 'Set semula';

  @override
  String get useTemplateFrom => 'Gunakan templat dari';

  @override
  String get selectProviderTemplate => 'Pilih templat pembekal...';

  @override
  String get quicklyPopulateResponse => 'Isi dengan cepat dengan format respons pembekal yang diketahui';

  @override
  String get quicklyPopulateRequest => 'Isi dengan cepat dengan format permintaan pembekal yang diketahui';

  @override
  String get invalidJsonError => 'JSON Tidak Sah';

  @override
  String downloadModelWithName(String model) {
    return 'Muat turun Model ($model)';
  }

  @override
  String modelNameWithFile(String model) {
    return 'Model: $model';
  }

  @override
  String get device => 'Peranti';

  @override
  String get chatAssistantsTitle => 'Pembantu Sembang';

  @override
  String get permissionReadConversations => 'Baca Perbualan';

  @override
  String get permissionReadMemories => 'Baca Kenangan';

  @override
  String get permissionReadTasks => 'Baca Tugas';

  @override
  String get permissionCreateConversations => 'Cipta Perbualan';

  @override
  String get permissionCreateMemories => 'Cipta Kenangan';

  @override
  String get permissionTypeAccess => 'Akses';

  @override
  String get permissionTypeCreate => 'Cipta';

  @override
  String get permissionTypeTrigger => 'Pencetus';

  @override
  String get permissionDescReadConversations => 'Aplikasi ini boleh mengakses perbualan anda.';

  @override
  String get permissionDescReadMemories => 'Aplikasi ini boleh mengakses kenangan anda.';

  @override
  String get permissionDescReadTasks => 'Aplikasi ini boleh mengakses tugas anda.';

  @override
  String get permissionDescCreateConversations => 'Aplikasi ini boleh mencipta perbualan baharu.';

  @override
  String get permissionDescCreateMemories => 'Aplikasi ini boleh mencipta kenangan baharu.';

  @override
  String get realtimeListening => 'Pendengaran Masa Nyata';

  @override
  String get setupCompleted => 'Selesai';

  @override
  String get pleaseSelectRating => 'Sila pilih penilaian';

  @override
  String get writeReviewOptional => 'Tulis ulasan (pilihan)';

  @override
  String get setupQuestionsIntro => 'Bantu kami memperbaiki Omi dengan menjawab beberapa soalan.  🫶 💜';

  @override
  String get setupQuestionProfession => '1. Apakah pekerjaan anda?';

  @override
  String get setupQuestionUsage => '2. Di mana anda bercadang menggunakan Omi anda?';

  @override
  String get setupQuestionAge => '3. Berapakah julat umur anda?';

  @override
  String get setupAnswerAllQuestions => 'Anda belum menjawab semua soalan lagi! 🥺';

  @override
  String get setupSkipHelp => 'Langkau, saya tidak mahu membantu :C';

  @override
  String get professionEntrepreneur => 'Usahawan';

  @override
  String get professionSoftwareEngineer => 'Jurutera Perisian';

  @override
  String get professionProductManager => 'Pengurus Produk';

  @override
  String get professionExecutive => 'Eksekutif';

  @override
  String get professionSales => 'Jualan';

  @override
  String get professionStudent => 'Pelajar';

  @override
  String get usageAtWork => 'Di tempat kerja';

  @override
  String get usageIrlEvents => 'Acara IRL';

  @override
  String get usageOnline => 'Dalam Talian';

  @override
  String get usageSocialSettings => 'Dalam Suasana Sosial';

  @override
  String get usageEverywhere => 'Di Mana-mana';

  @override
  String get customBackendUrlTitle => 'URL Backend Tersuai';

  @override
  String get backendUrlLabel => 'URL Backend';

  @override
  String get saveUrlButton => 'Simpan URL';

  @override
  String get enterBackendUrlError => 'Sila masukkan URL backend';

  @override
  String get urlMustEndWithSlashError => 'URL mesti berakhir dengan \"/\"';

  @override
  String get invalidUrlError => 'Sila masukkan URL yang sah';

  @override
  String get backendUrlSavedSuccess => 'URL backend berjaya disimpan!';

  @override
  String get signInTitle => 'Log Masuk';

  @override
  String get signInButton => 'Log Masuk';

  @override
  String get enterEmailError => 'Sila masukkan e-mel anda';

  @override
  String get invalidEmailError => 'Sila masukkan e-mel yang sah';

  @override
  String get enterPasswordError => 'Sila masukkan kata laluan anda';

  @override
  String get passwordMinLengthError => 'Kata laluan mestilah sekurang-kurangnya 8 aksara';

  @override
  String get signInSuccess => 'Log masuk berjaya!';

  @override
  String get alreadyHaveAccountLogin => 'Sudah mempunyai akaun? Log masuk';

  @override
  String get emailLabel => 'E-mel';

  @override
  String get passwordLabel => 'Kata laluan';

  @override
  String get createAccountTitle => 'Buat Akaun';

  @override
  String get nameLabel => 'Nama';

  @override
  String get repeatPasswordLabel => 'Ulang Kata Laluan';

  @override
  String get signUpButton => 'Daftar';

  @override
  String get enterNameError => 'Sila masukkan nama anda';

  @override
  String get passwordsDoNotMatch => 'Kata laluan tidak sepadan';

  @override
  String get signUpSuccess => 'Pendaftaran berjaya!';

  @override
  String get loadingKnowledgeGraph => 'Memuatkan Graf Pengetahuan...';

  @override
  String get noKnowledgeGraphYet => 'Tiada graf pengetahuan lagi';

  @override
  String get buildingKnowledgeGraphFromMemories => 'Membina graf pengetahuan daripada kenangan...';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'Graf pengetahuan anda akan dibina secara automatik apabila anda mencipta kenangan baharu.';

  @override
  String get buildGraphButton => 'Bina Graf';

  @override
  String get checkOutMyMemoryGraph => 'Lihat graf memori saya!';

  @override
  String get getButton => 'Dapatkan';

  @override
  String openingApp(String appName) {
    return 'Membuka $appName...';
  }

  @override
  String get writeSomething => 'Tulis sesuatu';

  @override
  String get submitReply => 'Hantar Balasan';

  @override
  String get editYourReply => 'Edit Balasan Anda';

  @override
  String get replyToReview => 'Balas Ulasan';

  @override
  String get rateAndReviewThisApp => 'Nilai dan ulas aplikasi ini';

  @override
  String get noChangesInReview => 'Tiada perubahan dalam ulasan untuk dikemas kini.';

  @override
  String get cantRateWithoutInternet => 'Tidak boleh menilai aplikasi tanpa sambungan internet.';

  @override
  String get appAnalytics => 'Analitik Aplikasi';

  @override
  String get learnMoreLink => 'ketahui lebih lanjut';

  @override
  String get moneyEarned => 'Wang yang diperoleh';

  @override
  String get writeYourReply => 'Tulis balasan anda...';

  @override
  String get replySentSuccessfully => 'Balasan berjaya dihantar';

  @override
  String failedToSendReply(String error) {
    return 'Gagal menghantar balasan: $error';
  }

  @override
  String get send => 'Hantar';

  @override
  String starFilter(int count) {
    return '$count Bintang';
  }

  @override
  String get noReviewsFound => 'Tiada Ulasan Ditemui';

  @override
  String get editReply => 'Edit Balasan';

  @override
  String get reply => 'Balas';

  @override
  String starFilterLabel(int count) {
    return '$count bintang';
  }

  @override
  String get sharePublicLink => 'Kongsi Pautan Awam';

  @override
  String get makePersonaPublic => 'Jadikan Persona Awam';

  @override
  String get connectedKnowledgeData => 'Data Pengetahuan Tersambung';

  @override
  String get enterName => 'Masukkan nama';

  @override
  String get disconnectTwitter => 'Putuskan Sambungan Twitter';

  @override
  String get disconnectTwitterConfirmation =>
      'Adakah anda pasti mahu memutuskan sambungan akaun Twitter anda? Persona anda tidak lagi dikemas kini berdasarkan aktiviti anda.';

  @override
  String get getOmiDeviceDescription => 'Cipta klon yang lebih tepat dengan perbualan peribadi anda';

  @override
  String get getOmi => 'Dapatkan Omi';

  @override
  String get iHaveOmiDevice => 'Saya mempunyai peranti Omi';

  @override
  String get goal => 'MATLAMAT';

  @override
  String get tapToTrackThisGoal => 'Ketik untuk menjejaki matlamat ini';

  @override
  String get tapToSetAGoal => 'Ketik untuk menetapkan matlamat';

  @override
  String get processedConversations => 'Perbualan yang Diproses';

  @override
  String get updatedConversations => 'Perbualan yang Dikemas Kini';

  @override
  String get newConversations => 'Perbualan Baharu';

  @override
  String get summaryTemplate => 'Templat Ringkasan';

  @override
  String get suggestedTemplates => 'Templat Dicadangkan';

  @override
  String get otherTemplates => 'Templat Lain';

  @override
  String get availableTemplates => 'Templat Tersedia';

  @override
  String get getCreative => 'Jadilah Kreatif';

  @override
  String get defaultLabel => 'Lalai';

  @override
  String get lastUsedLabel => 'Terakhir Digunakan';

  @override
  String get setDefaultApp => 'Tetapkan Aplikasi Lalai';

  @override
  String setDefaultAppContent(String appName) {
    return 'Tetapkan $appName sebagai aplikasi ringkasan lalai anda?\\n\\nAplikasi ini akan digunakan secara automatik untuk semua ringkasan perbualan pada masa hadapan.';
  }

  @override
  String get setDefaultButton => 'Tetapkan Lalai';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName ditetapkan sebagai aplikasi ringkasan lalai';
  }

  @override
  String get createCustomTemplate => 'Cipta Templat Tersuai';

  @override
  String get allTemplates => 'Semua Templat';

  @override
  String failedToInstallApp(String appName) {
    return 'Gagal memasang $appName. Sila cuba lagi.';
  }

  @override
  String errorInstallingApp(String appName, String error) {
    return 'Ralat memasang $appName: $error';
  }

  @override
  String tagSpeaker(int speakerId) {
    return 'Tag Pembicara $speakerId';
  }

  @override
  String get personNameAlreadyExists => 'Orang dengan nama ini sudah wujud.';

  @override
  String get selectYouFromList => 'Untuk menandai diri sendiri, sila pilih \"Anda\" dari senarai.';

  @override
  String get enterPersonsName => 'Masukkan Nama Orang';

  @override
  String get addPerson => 'Tambah Orang';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'Tag segmen lain dari pembicara ini ($selected/$total)';
  }

  @override
  String get tagOtherSegments => 'Tag segmen lain';

  @override
  String get managePeople => 'Urus Orang';

  @override
  String get shareViaSms => 'Kongsi melalui SMS';

  @override
  String get selectContactsToShareSummary => 'Pilih kenalan untuk berkongsi ringkasan perbualan anda';

  @override
  String get searchContactsHint => 'Cari kenalan...';

  @override
  String contactsSelectedCount(int count) {
    return '$count dipilih';
  }

  @override
  String get clearAllSelection => 'Kosongkan semua';

  @override
  String get selectContactsToShare => 'Pilih kenalan untuk dikongsi';

  @override
  String shareWithContactCount(int count) {
    return 'Kongsi dengan $count kenalan';
  }

  @override
  String shareWithContactsCount(int count) {
    return 'Kongsi dengan $count kenalan';
  }

  @override
  String get contactsPermissionRequired => 'Kebenaran kenalan diperlukan';

  @override
  String get contactsPermissionRequiredForSms => 'Kebenaran kenalan diperlukan untuk berkongsi melalui SMS';

  @override
  String get grantContactsPermissionForSms => 'Sila berikan kebenaran kenalan untuk berkongsi melalui SMS';

  @override
  String get noContactsWithPhoneNumbers => 'Tiada kenalan dengan nombor telefon ditemui';

  @override
  String get noContactsMatchSearch => 'Tiada kenalan yang sepadan dengan carian anda';

  @override
  String get failedToLoadContacts => 'Gagal memuatkan kenalan';

  @override
  String get failedToPrepareConversationForSharing => 'Gagal menyediakan perbualan untuk dikongsi. Sila cuba lagi.';

  @override
  String get couldNotOpenSmsApp => 'Tidak dapat membuka aplikasi SMS. Sila cuba lagi.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'Inilah yang baru kita bincangkan: $link';
  }

  @override
  String get wifiSync => 'Penyegerakan WiFi';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item disalin ke papan keratan';
  }

  @override
  String get wifiConnectionFailedTitle => 'Sambungan Gagal';

  @override
  String connectingToDeviceName(String deviceName) {
    return 'Menyambung ke $deviceName';
  }

  @override
  String enableDeviceWifi(String deviceName) {
    return 'Aktifkan WiFi $deviceName';
  }

  @override
  String connectToDeviceName(String deviceName) {
    return 'Sambung ke $deviceName';
  }

  @override
  String get recordingDetails => 'Butiran Rakaman';

  @override
  String get storageLocationSdCard => 'Kad SD';

  @override
  String get storageLocationLimitlessPendant => 'Limitless Pendant';

  @override
  String get storageLocationPhone => 'Telefon';

  @override
  String get storageLocationPhoneMemory => 'Telefon (Memori)';

  @override
  String storedOnDevice(String deviceName) {
    return 'Disimpan di $deviceName';
  }

  @override
  String get transferring => 'Memindahkan...';

  @override
  String get transferRequired => 'Pemindahan Diperlukan';

  @override
  String get downloadingAudioFromSdCard => 'Memuat turun audio dari kad SD peranti anda';

  @override
  String get transferRequiredDescription =>
      'Rakaman ini disimpan di kad SD peranti anda. Pindahkan ke telefon anda untuk memainkan semula.';

  @override
  String get cancelTransfer => 'Batal Pemindahan';

  @override
  String get transferToPhone => 'Pindah ke Telefon';

  @override
  String get privateAndSecureOnDevice => 'Peribadi & selamat di peranti anda';

  @override
  String get recordingInfo => 'Maklumat Rakaman';

  @override
  String get transferInProgress => 'Pemindahan sedang berjalan...';

  @override
  String get shareRecording => 'Kongsi Rakaman';

  @override
  String get deleteRecordingConfirmation =>
      'Adakah anda pasti mahu memadam rakaman ini secara kekal? Tindakan ini tidak boleh dibatalkan.';

  @override
  String get recordingIdLabel => 'ID Rakaman';

  @override
  String get dateTimeLabel => 'Tarikh & Masa';

  @override
  String get durationLabel => 'Tempoh';

  @override
  String get audioFormatLabel => 'Format Audio';

  @override
  String get storageLocationLabel => 'Lokasi Penyimpanan';

  @override
  String get estimatedSizeLabel => 'Anggaran Saiz';

  @override
  String get deviceModelLabel => 'Model Peranti';

  @override
  String get deviceIdLabel => 'ID Peranti';

  @override
  String get statusLabel => 'Status';

  @override
  String get statusProcessed => 'Diproses';

  @override
  String get statusUnprocessed => 'Belum Diproses';

  @override
  String get switchedToFastTransfer => 'Bertukar ke Pemindahan Pantas';

  @override
  String get transferCompleteMessage => 'Pemindahan selesai! Anda kini boleh memainkan rakaman ini.';

  @override
  String transferFailedMessage(String error) {
    return 'Pemindahan gagal: $error';
  }

  @override
  String get transferCancelled => 'Pemindahan dibatalkan';

  @override
  String get fastTransferEnabled => 'Pemindahan Pantas diaktifkan';

  @override
  String get bluetoothSyncEnabled => 'Penyegerakan Bluetooth diaktifkan';

  @override
  String get enableFastTransfer => 'Aktifkan Pemindahan Pantas';

  @override
  String get fastTransferDescription =>
      'Pemindahan Pantas menggunakan WiFi untuk kelajuan ~5x lebih pantas. Telefon anda akan bersambung sementara ke rangkaian WiFi peranti Omi semasa pemindahan.';

  @override
  String get internetAccessPausedDuringTransfer => 'Akses internet dijeda semasa pemindahan';

  @override
  String get chooseTransferMethodDescription => 'Pilih cara rakaman dipindahkan dari peranti Omi ke telefon anda.';

  @override
  String get wifiSpeed => '~150 KB/s melalui WiFi';

  @override
  String get fiveTimesFaster => '5X LEBIH PANTAS';

  @override
  String get fastTransferMethodDescription =>
      'Mencipta sambungan WiFi terus ke peranti Omi anda. Telefon anda terputus sementara dari WiFi biasa semasa pemindahan.';

  @override
  String get bluetooth => 'Bluetooth';

  @override
  String get bleSpeed => '~30 KB/s melalui BLE';

  @override
  String get bluetoothMethodDescription =>
      'Menggunakan sambungan Bluetooth Low Energy standard. Lebih perlahan tetapi tidak menjejaskan sambungan WiFi anda.';

  @override
  String get selected => 'Dipilih';

  @override
  String get selectOption => 'Pilih';

  @override
  String get lowBatteryAlertTitle => 'Amaran Bateri Lemah';

  @override
  String get lowBatteryAlertBody => 'Bateri peranti anda lemah. Masa untuk mengecas semula! 🔋';

  @override
  String get deviceDisconnectedNotificationTitle => 'Peranti Omi Anda Terputus';

  @override
  String get deviceDisconnectedNotificationBody => 'Sila sambung semula untuk terus menggunakan Omi.';

  @override
  String get firmwareUpdateAvailable => 'Kemas Kini Firmware Tersedia';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'Kemas kini firmware baharu ($version) tersedia untuk peranti Omi anda. Adakah anda mahu mengemas kini sekarang?';
  }

  @override
  String get later => 'Nanti';

  @override
  String get appDeletedSuccessfully => 'Apl berjaya dipadam';

  @override
  String get appDeleteFailed => 'Gagal memadam apl. Sila cuba lagi kemudian.';

  @override
  String get appVisibilityChangedSuccessfully =>
      'Keterlihatan apl berjaya ditukar. Ia mungkin mengambil masa beberapa minit untuk dikemas kini.';

  @override
  String get errorActivatingAppIntegration =>
      'Ralat mengaktifkan apl. Jika ini adalah apl integrasi, pastikan persediaan telah selesai.';

  @override
  String get errorUpdatingAppStatus => 'Ralat berlaku semasa mengemas kini status apl.';

  @override
  String get calculatingETA => 'Mengira...';

  @override
  String aboutMinutesRemaining(int minutes) {
    return 'Kira-kira $minutes minit lagi';
  }

  @override
  String get aboutAMinuteRemaining => 'Kira-kira satu minit lagi';

  @override
  String get almostDone => 'Hampir selesai...';

  @override
  String get omiSays => 'omi berkata';

  @override
  String get analyzingYourData => 'Menganalisis data anda...';

  @override
  String migratingToProtection(String level) {
    return 'Berpindah ke perlindungan $level...';
  }

  @override
  String get noDataToMigrateFinalizing => 'Tiada data untuk dipindahkan. Memmuktamadkan...';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return 'Memindahkan $itemType... $percentage%';
  }

  @override
  String get allObjectsMigratedFinalizing => 'Semua objek telah dipindahkan. Memmuktamadkan...';

  @override
  String get migrationErrorOccurred => 'Ralat berlaku semasa pemindahan. Sila cuba lagi.';

  @override
  String get migrationComplete => 'Pemindahan selesai!';

  @override
  String dataProtectedWithSettings(String level) {
    return 'Data anda kini dilindungi dengan tetapan $level yang baharu.';
  }

  @override
  String get chatsLowercase => 'sembang';

  @override
  String get dataLowercase => 'data';

  @override
  String get fallNotificationTitle => 'Aduh';

  @override
  String get fallNotificationBody => 'Adakah anda jatuh?';

  @override
  String get importantConversationTitle => 'Perbualan Penting';

  @override
  String get importantConversationBody =>
      'Anda baru sahaja melakukan perbualan penting. Ketik untuk berkongsi ringkasan.';

  @override
  String get templateName => 'Nama Templat';

  @override
  String get templateNameHint => 'cth. Pengekstrak Item Tindakan Mesyuarat';

  @override
  String get nameMustBeAtLeast3Characters => 'Nama mesti sekurang-kurangnya 3 aksara';

  @override
  String get conversationPromptHint =>
      'cth., Ekstrak item tindakan, keputusan yang dibuat, dan perkara utama dari perbualan yang diberikan.';

  @override
  String get pleaseEnterAppPrompt => 'Sila masukkan prompt untuk aplikasi anda';

  @override
  String get promptMustBeAtLeast10Characters => 'Prompt mesti sekurang-kurangnya 10 aksara';

  @override
  String get anyoneCanDiscoverTemplate => 'Sesiapa sahaja boleh menemui templat anda';

  @override
  String get onlyYouCanUseTemplate => 'Hanya anda boleh menggunakan templat ini';

  @override
  String get generatingDescription => 'Menjana penerangan...';

  @override
  String get creatingAppIcon => 'Mencipta ikon aplikasi...';

  @override
  String get installingApp => 'Memasang aplikasi...';

  @override
  String get appCreatedAndInstalled => 'Aplikasi dicipta dan dipasang!';

  @override
  String get appCreatedSuccessfully => 'Aplikasi berjaya dicipta!';

  @override
  String get failedToCreateApp => 'Gagal mencipta aplikasi. Sila cuba lagi.';

  @override
  String get addAppSelectCoreCapability => 'Sila pilih satu lagi keupayaan teras untuk aplikasi anda';

  @override
  String get addAppSelectPaymentPlan => 'Sila pilih pelan pembayaran dan masukkan harga untuk aplikasi anda';

  @override
  String get addAppSelectCapability => 'Sila pilih sekurang-kurangnya satu keupayaan untuk aplikasi anda';

  @override
  String get addAppSelectLogo => 'Sila pilih logo untuk aplikasi anda';

  @override
  String get addAppEnterChatPrompt => 'Sila masukkan prompt sembang untuk aplikasi anda';

  @override
  String get addAppEnterConversationPrompt => 'Sila masukkan prompt perbualan untuk aplikasi anda';

  @override
  String get addAppSelectTriggerEvent => 'Sila pilih peristiwa pencetus untuk aplikasi anda';

  @override
  String get addAppEnterWebhookUrl => 'Sila masukkan URL webhook untuk aplikasi anda';

  @override
  String get addAppSelectCategory => 'Sila pilih kategori untuk aplikasi anda';

  @override
  String get addAppFillRequiredFields => 'Sila isi semua medan yang diperlukan dengan betul';

  @override
  String get addAppUpdatedSuccess => 'Aplikasi berjaya dikemas kini 🚀';

  @override
  String get addAppUpdateFailed => 'Kemas kini gagal. Sila cuba lagi nanti';

  @override
  String get addAppSubmittedSuccess => 'Aplikasi berjaya dihantar 🚀';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'Ralat membuka pemilih fail: $message';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'Ralat memilih imej: $error';
  }

  @override
  String get addAppPhotosPermissionDenied => 'Kebenaran foto ditolak. Sila benarkan akses kepada foto';

  @override
  String get addAppErrorSelectingImageRetry => 'Ralat memilih imej. Sila cuba lagi.';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'Ralat memilih lakaran kecil: $error';
  }

  @override
  String get addAppErrorSelectingThumbnailRetry => 'Ralat memilih lakaran kecil. Sila cuba lagi.';

  @override
  String get addAppCapabilityConflictWithPersona => 'Keupayaan lain tidak boleh dipilih dengan Persona';

  @override
  String get addAppPersonaConflictWithCapabilities => 'Persona tidak boleh dipilih dengan keupayaan lain';

  @override
  String get personaTwitterHandleNotFound => 'Akaun Twitter tidak dijumpai';

  @override
  String get personaTwitterHandleSuspended => 'Akaun Twitter digantung';

  @override
  String get personaFailedToVerifyTwitter => 'Gagal mengesahkan akaun Twitter';

  @override
  String get personaFailedToFetch => 'Gagal mendapatkan persona anda';

  @override
  String get personaFailedToCreate => 'Gagal mencipta persona';

  @override
  String get personaConnectKnowledgeSource => 'Sila sambungkan sekurang-kurangnya satu sumber data (Omi atau Twitter)';

  @override
  String get personaUpdatedSuccessfully => 'Persona berjaya dikemas kini';

  @override
  String get personaFailedToUpdate => 'Gagal mengemas kini persona';

  @override
  String get personaPleaseSelectImage => 'Sila pilih imej';

  @override
  String get personaFailedToCreateTryLater => 'Gagal mencipta persona. Sila cuba lagi nanti.';

  @override
  String personaFailedToCreateWithError(String error) {
    return 'Gagal mencipta persona: $error';
  }

  @override
  String get personaFailedToEnable => 'Gagal mengaktifkan persona';

  @override
  String personaErrorEnablingWithError(String error) {
    return 'Ralat mengaktifkan persona: $error';
  }

  @override
  String get paymentFailedToFetchCountries => 'Gagal mendapatkan negara yang disokong. Sila cuba lagi nanti.';

  @override
  String get paymentFailedToSetDefault => 'Gagal menetapkan kaedah pembayaran lalai. Sila cuba lagi nanti.';

  @override
  String get paymentFailedToSavePaypal => 'Gagal menyimpan butiran PayPal. Sila cuba lagi nanti.';

  @override
  String get paypalEmailHint => 'nik@example.com';

  @override
  String get paypalMeLinkHint => 'paypal.me/nik';

  @override
  String get paymentMethodStripe => 'Stripe';

  @override
  String get paymentMethodPayPal => 'PayPal';

  @override
  String get paymentStatusActive => 'Aktif';

  @override
  String get paymentStatusConnected => 'Disambungkan';

  @override
  String get paymentStatusNotConnected => 'Tidak Disambungkan';

  @override
  String get paymentAppCost => 'Kos Aplikasi';

  @override
  String get paymentEnterValidAmount => 'Sila masukkan jumlah yang sah';

  @override
  String get paymentEnterAmountGreaterThanZero => 'Sila masukkan jumlah lebih daripada 0';

  @override
  String get paymentPlan => 'Pelan Pembayaran';

  @override
  String get paymentNoneSelected => 'Tiada Dipilih';

  @override
  String get aiGenPleaseEnterDescription => 'Sila masukkan penerangan untuk aplikasi anda';

  @override
  String get aiGenCreatingAppIcon => 'Mencipta ikon aplikasi...';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'Ralat berlaku: $message';
  }

  @override
  String get aiGenAppCreatedSuccessfully => 'Aplikasi berjaya dicipta!';

  @override
  String get aiGenFailedToCreateApp => 'Gagal mencipta aplikasi';

  @override
  String get aiGenErrorWhileCreatingApp => 'Ralat berlaku semasa mencipta aplikasi';

  @override
  String get aiGenFailedToGenerateApp => 'Gagal menjana aplikasi. Sila cuba lagi.';

  @override
  String get aiGenFailedToRegenerateIcon => 'Gagal menjana semula ikon';

  @override
  String get aiGenPleaseGenerateAppFirst => 'Sila jana aplikasi terlebih dahulu';

  @override
  String get xHandleTitle => 'Apakah nama pengguna X anda?';

  @override
  String get xHandleDescription => 'Kami akan melatih klon Omi anda terlebih dahulu\nberdasarkan aktiviti akaun anda';

  @override
  String get xHandleHint => '@nikshevchenko';

  @override
  String get xHandlePleaseEnter => 'Sila masukkan nama pengguna X anda';

  @override
  String get xHandlePleaseEnterValid => 'Sila masukkan nama pengguna X yang sah';

  @override
  String get nextButton => 'Seterusnya';

  @override
  String get connectOmiDevice => 'Sambung Peranti Omi';

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'Anda sedang menukar Pelan Tanpa Had anda ke $title. Adakah anda pasti mahu meneruskan?';
  }

  @override
  String get planUpgradeScheduledMessage =>
      'Naik taraf dijadualkan! Pelan bulanan anda diteruskan sehingga akhir tempoh bil anda.';

  @override
  String get couldNotSchedulePlanChange => 'Tidak dapat menjadualkan perubahan pelan. Sila cuba lagi.';

  @override
  String get subscriptionReactivatedDefault =>
      'Langganan anda telah diaktifkan semula! Tiada caj sekarang - anda akan dibilkan pada kadar baharu pada tempoh pengebilan seterusnya.';

  @override
  String get subscriptionSuccessfulCharged => 'Langganan berjaya! Anda telah dicaj untuk tempoh pengebilan baharu.';

  @override
  String get couldNotProcessSubscription => 'Tidak dapat memproses langganan. Sila cuba lagi.';

  @override
  String get couldNotLaunchUpgradePage => 'Tidak dapat membuka halaman naik taraf. Sila cuba lagi.';

  @override
  String get transcriptionJsonPlaceholder => 'Tampal konfigurasi JSON anda di sini...';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get pricePlaceholder => '0.00';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'Ralat membuka pemilih fail: $message';
  }

  @override
  String importErrorGeneric(String error) {
    return 'Ralat: $error';
  }

  @override
  String get mergeConversationsSuccessTitle => 'Perbualan berjaya digabungkan';

  @override
  String mergeConversationsSuccessBody(int count) {
    return '$count perbualan berjaya digabungkan';
  }

  @override
  String get dailyReflectionNotificationTitle => 'Masa untuk Refleksi Harian';

  @override
  String get dailyReflectionNotificationBody => 'Ceritakan tentang hari anda';

  @override
  String get actionItemReminderTitle => 'Peringatan Omi';

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName terputus';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'Sila sambung semula untuk terus menggunakan $deviceName anda.';
  }

  @override
  String get onboardingSignIn => 'Log masuk';

  @override
  String get onboardingYourName => 'Nama anda';

  @override
  String get onboardingLanguage => 'Bahasa';

  @override
  String get onboardingPermissions => 'Kebenaran';

  @override
  String get onboardingComplete => 'Selesai';

  @override
  String get onboardingWelcomeToOmi => 'Selamat datang ke Omi';

  @override
  String get onboardingTellUsAboutYourself => 'Ceritakan tentang diri anda';

  @override
  String get onboardingChooseYourPreference => 'Pilih keutamaan anda';

  @override
  String get onboardingGrantRequiredAccess => 'Berikan akses yang diperlukan';

  @override
  String get onboardingYoureAllSet => 'Anda sudah sedia';

  @override
  String get searchTranscriptOrSummary => 'Cari dalam transkrip atau ringkasan...';

  @override
  String get myGoal => 'Matlamat saya';

  @override
  String get appNotAvailable => 'Oops! Nampaknya aplikasi yang anda cari tidak tersedia.';

  @override
  String get failedToConnectTodoist => 'Gagal menyambung ke Todoist';

  @override
  String get failedToConnectAsana => 'Gagal menyambung ke Asana';

  @override
  String get failedToConnectGoogleTasks => 'Gagal menyambung ke Google Tasks';

  @override
  String get failedToConnectClickUp => 'Gagal menyambung ke ClickUp';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return 'Gagal menyambung ke $serviceName: $error';
  }

  @override
  String get successfullyConnectedTodoist => 'Berjaya disambungkan ke Todoist!';

  @override
  String get failedToConnectTodoistRetry => 'Gagal menyambung ke Todoist. Sila cuba lagi.';

  @override
  String get successfullyConnectedAsana => 'Berjaya disambungkan ke Asana!';

  @override
  String get failedToConnectAsanaRetry => 'Gagal menyambung ke Asana. Sila cuba lagi.';

  @override
  String get successfullyConnectedGoogleTasks => 'Berjaya disambungkan ke Google Tasks!';

  @override
  String get failedToConnectGoogleTasksRetry => 'Gagal menyambung ke Google Tasks. Sila cuba lagi.';

  @override
  String get successfullyConnectedClickUp => 'Berjaya disambungkan ke ClickUp!';

  @override
  String get failedToConnectClickUpRetry => 'Gagal menyambung ke ClickUp. Sila cuba lagi.';

  @override
  String get successfullyConnectedNotion => 'Berjaya disambungkan ke Notion!';

  @override
  String get failedToRefreshNotionStatus => 'Gagal memuat semula status sambungan Notion.';

  @override
  String get successfullyConnectedGoogle => 'Berjaya disambungkan ke Google!';

  @override
  String get failedToRefreshGoogleStatus => 'Gagal memuat semula status sambungan Google.';

  @override
  String get successfullyConnectedWhoop => 'Berjaya disambungkan ke Whoop!';

  @override
  String get failedToRefreshWhoopStatus => 'Gagal memuat semula status sambungan Whoop.';

  @override
  String get successfullyConnectedGitHub => 'Berjaya disambungkan ke GitHub!';

  @override
  String get failedToRefreshGitHubStatus => 'Gagal memuat semula status sambungan GitHub.';

  @override
  String get authFailedToSignInWithGoogle => 'Gagal log masuk dengan Google, sila cuba lagi.';

  @override
  String get authenticationFailed => 'Pengesahan gagal. Sila cuba lagi.';

  @override
  String get authFailedToSignInWithApple => 'Gagal log masuk dengan Apple, sila cuba lagi.';

  @override
  String get authFailedToRetrieveToken => 'Gagal mendapatkan token Firebase, sila cuba lagi.';

  @override
  String get authUnexpectedErrorFirebase => 'Ralat tidak dijangka semasa log masuk, ralat Firebase, sila cuba lagi.';

  @override
  String get authUnexpectedError => 'Ralat tidak dijangka semasa log masuk, sila cuba lagi';

  @override
  String get authFailedToLinkGoogle => 'Gagal memautkan dengan Google, sila cuba lagi.';

  @override
  String get authFailedToLinkApple => 'Gagal memautkan dengan Apple, sila cuba lagi.';

  @override
  String get onboardingBluetoothRequired => 'Kebenaran Bluetooth diperlukan untuk menyambung ke peranti anda.';

  @override
  String get onboardingBluetoothDeniedSystemPrefs =>
      'Kebenaran Bluetooth ditolak. Sila berikan kebenaran dalam Keutamaan Sistem.';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'Status kebenaran Bluetooth: $status. Sila semak Keutamaan Sistem.';
  }

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'Gagal menyemak kebenaran Bluetooth: $error';
  }

  @override
  String get onboardingNotificationDeniedSystemPrefs =>
      'Kebenaran pemberitahuan ditolak. Sila berikan kebenaran dalam Keutamaan Sistem.';

  @override
  String get onboardingNotificationDeniedNotifications =>
      'Kebenaran pemberitahuan ditolak. Sila berikan kebenaran dalam Keutamaan Sistem > Pemberitahuan.';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return 'Status kebenaran pemberitahuan: $status. Sila semak Keutamaan Sistem.';
  }

  @override
  String onboardingFailedCheckNotification(String error) {
    return 'Gagal menyemak kebenaran pemberitahuan: $error';
  }

  @override
  String get onboardingLocationGrantInSettings =>
      'Sila berikan kebenaran lokasi dalam Tetapan > Privasi & Keselamatan > Perkhidmatan Lokasi';

  @override
  String get onboardingMicrophoneRequired => 'Kebenaran mikrofon diperlukan untuk merakam.';

  @override
  String get onboardingMicrophoneDenied =>
      'Kebenaran mikrofon ditolak. Sila berikan kebenaran dalam Keutamaan Sistem > Privasi & Keselamatan > Mikrofon.';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'Status kebenaran mikrofon: $status. Sila semak Keutamaan Sistem.';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'Gagal menyemak kebenaran mikrofon: $error';
  }

  @override
  String get onboardingScreenCaptureRequired => 'Kebenaran tangkapan skrin diperlukan untuk merakam audio sistem.';

  @override
  String get onboardingScreenCaptureDenied =>
      'Kebenaran tangkapan skrin ditolak. Sila berikan kebenaran dalam Keutamaan Sistem > Privasi & Keselamatan > Rakaman Skrin.';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return 'Status kebenaran tangkapan skrin: $status. Sila semak Keutamaan Sistem.';
  }

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return 'Gagal menyemak kebenaran tangkapan skrin: $error';
  }

  @override
  String get onboardingAccessibilityRequired => 'Kebenaran kebolehcapaian diperlukan untuk mengesan mesyuarat pelayar.';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'Status kebenaran kebolehcapaian: $status. Sila semak Keutamaan Sistem.';
  }

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'Gagal menyemak kebenaran kebolehcapaian: $error';
  }

  @override
  String get msgCameraNotAvailable => 'Tangkapan kamera tidak tersedia di platform ini';

  @override
  String get msgCameraPermissionDenied => 'Kebenaran kamera ditolak. Sila benarkan akses kepada kamera';

  @override
  String msgCameraAccessError(String error) {
    return 'Ralat mengakses kamera: $error';
  }

  @override
  String get msgPhotoError => 'Ralat mengambil gambar. Sila cuba lagi.';

  @override
  String get msgMaxImagesLimit => 'Anda hanya boleh memilih sehingga 4 imej';

  @override
  String msgFilePickerError(String error) {
    return 'Ralat membuka pemilih fail: $error';
  }

  @override
  String msgSelectImagesError(String error) {
    return 'Ralat memilih imej: $error';
  }

  @override
  String get msgPhotosPermissionDenied => 'Kebenaran foto ditolak. Sila benarkan akses kepada foto untuk memilih imej';

  @override
  String get msgSelectImagesGenericError => 'Ralat memilih imej. Sila cuba lagi.';

  @override
  String get msgMaxFilesLimit => 'Anda hanya boleh memilih sehingga 4 fail';

  @override
  String msgSelectFilesError(String error) {
    return 'Ralat memilih fail: $error';
  }

  @override
  String get msgSelectFilesGenericError => 'Ralat memilih fail. Sila cuba lagi.';

  @override
  String get msgUploadFileFailed => 'Gagal memuat naik fail, sila cuba lagi kemudian';

  @override
  String get msgReadingMemories => 'Membaca kenangan anda...';

  @override
  String get msgLearningMemories => 'Belajar dari kenangan anda...';

  @override
  String get msgUploadAttachedFileFailed => 'Gagal memuat naik fail yang dilampirkan.';

  @override
  String captureRecordingError(String error) {
    return 'Ralat berlaku semasa rakaman: $error';
  }

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return 'Rakaman dihentikan: $reason. Anda mungkin perlu menyambung semula paparan luaran atau mulakan semula rakaman.';
  }

  @override
  String get captureMicrophonePermissionRequired => 'Kebenaran mikrofon diperlukan';

  @override
  String get captureMicrophonePermissionInSystemPreferences => 'Berikan kebenaran mikrofon dalam Keutamaan Sistem';

  @override
  String get captureScreenRecordingPermissionRequired => 'Kebenaran rakaman skrin diperlukan';

  @override
  String get captureDisplayDetectionFailed => 'Pengesanan paparan gagal. Rakaman dihentikan.';

  @override
  String get devModeInvalidAudioBytesWebhookUrl => 'URL webhook bait audio tidak sah';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl => 'URL webhook transkripsi masa nyata tidak sah';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl => 'URL webhook perbualan dicipta tidak sah';

  @override
  String get devModeInvalidDaySummaryWebhookUrl => 'URL webhook ringkasan harian tidak sah';

  @override
  String get devModeSettingsSaved => 'Tetapan disimpan!';

  @override
  String get voiceFailedToTranscribe => 'Gagal mentranskrip audio';

  @override
  String get locationPermissionRequired => 'Kebenaran lokasi diperlukan';

  @override
  String get locationPermissionContent =>
      'Pemindahan Pantas memerlukan kebenaran lokasi untuk mengesahkan sambungan WiFi. Sila berikan kebenaran lokasi untuk meneruskan.';

  @override
  String get pdfTranscriptExport => 'Eksport Transkrip';

  @override
  String get pdfConversationExport => 'Eksport Perbualan';

  @override
  String pdfTitleLabel(String title) {
    return 'Tajuk: $title';
  }

  @override
  String get conversationNewIndicator => 'Baharu 🚀';

  @override
  String conversationPhotosCount(int count) {
    return '$count foto';
  }

  @override
  String get mergingStatus => 'Menggabungkan...';

  @override
  String timeSecsSingular(int count) {
    return '$count saat';
  }

  @override
  String timeSecsPlural(int count) {
    return '$count saat';
  }

  @override
  String timeMinSingular(int count) {
    return '$count minit';
  }

  @override
  String timeMinsPlural(int count) {
    return '$count minit';
  }

  @override
  String timeMinsAndSecs(int mins, int secs) {
    return '$mins minit $secs saat';
  }

  @override
  String timeHourSingular(int count) {
    return '$count jam';
  }

  @override
  String timeHoursPlural(int count) {
    return '$count jam';
  }

  @override
  String timeHoursAndMins(int hours, int mins) {
    return '$hours jam $mins minit';
  }

  @override
  String timeDaySingular(int count) {
    return '$count hari';
  }

  @override
  String timeDaysPlural(int count) {
    return '$count hari';
  }

  @override
  String timeDaysAndHours(int days, int hours) {
    return '$days hari $hours jam';
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
    return '${count}j';
  }

  @override
  String timeCompactHoursAndMins(int hours, int mins) {
    return '${hours}j ${mins}m';
  }

  @override
  String get moveToFolder => 'Pindah ke Folder';

  @override
  String get noFoldersAvailable => 'Tiada folder tersedia';

  @override
  String get newFolder => 'Folder Baharu';

  @override
  String get color => 'Warna';

  @override
  String get waitingForDevice => 'Menunggu peranti...';

  @override
  String get saySomething => 'Katakan sesuatu...';

  @override
  String get initialisingSystemAudio => 'Memulakan Audio Sistem';

  @override
  String get stopRecording => 'Hentikan Rakaman';

  @override
  String get continueRecording => 'Teruskan Rakaman';

  @override
  String get initialisingRecorder => 'Memulakan Perakam';

  @override
  String get pauseRecording => 'Jeda Rakaman';

  @override
  String get resumeRecording => 'Sambung Rakaman';

  @override
  String get noDailyRecapsYet => 'Belum ada ringkasan harian';

  @override
  String get dailyRecapsDescription => 'Ringkasan harian anda akan muncul di sini setelah dijana';

  @override
  String get chooseTransferMethod => 'Pilih kaedah pemindahan';

  @override
  String get fastTransferSpeed => '~150 KB/s melalui WiFi';

  @override
  String largeTimeGapDetected(String gap) {
    return 'Jurang masa besar dikesan ($gap)';
  }

  @override
  String largeTimeGapsDetected(String gaps) {
    return 'Jurang masa besar dikesan ($gaps)';
  }

  @override
  String get deviceDoesNotSupportWifiSwitchingToBle =>
      'Peranti tidak menyokong penyegerakan WiFi, bertukar kepada Bluetooth';

  @override
  String get appleHealthNotAvailable => 'Apple Health tidak tersedia pada peranti ini';

  @override
  String get downloadAudio => 'Muat turun Audio';

  @override
  String get audioDownloadSuccess => 'Audio berjaya dimuat turun';

  @override
  String get audioDownloadFailed => 'Gagal memuat turun audio';

  @override
  String get downloadingAudio => 'Memuat turun audio...';

  @override
  String get shareAudio => 'Kongsi Audio';

  @override
  String get preparingAudio => 'Menyediakan Audio';

  @override
  String get gettingAudioFiles => 'Mendapatkan fail audio...';

  @override
  String get downloadingAudioProgress => 'Memuat turun Audio';

  @override
  String get processingAudio => 'Memproses Audio';

  @override
  String get combiningAudioFiles => 'Menggabungkan fail audio...';

  @override
  String get audioReady => 'Audio Sedia';

  @override
  String get openingShareSheet => 'Membuka helaian perkongsian...';

  @override
  String get audioShareFailed => 'Perkongsian Gagal';

  @override
  String get dailyRecaps => 'Ringkasan Harian';

  @override
  String get removeFilter => 'Alih Keluar Penapis';

  @override
  String get categoryConversationAnalysis => 'Analisis Perbualan';

  @override
  String get categoryPersonalityClone => 'Klon Personaliti';

  @override
  String get categoryHealth => 'Kesihatan';

  @override
  String get categoryEducation => 'Pendidikan';

  @override
  String get categoryCommunication => 'Komunikasi';

  @override
  String get categoryEmotionalSupport => 'Sokongan Emosi';

  @override
  String get categoryProductivity => 'Produktiviti';

  @override
  String get categoryEntertainment => 'Hiburan';

  @override
  String get categoryFinancial => 'Kewangan';

  @override
  String get categoryTravel => 'Perjalanan';

  @override
  String get categorySafety => 'Keselamatan';

  @override
  String get categoryShopping => 'Membeli-belah';

  @override
  String get categorySocial => 'Sosial';

  @override
  String get categoryNews => 'Berita';

  @override
  String get categoryUtilities => 'Utiliti';

  @override
  String get categoryOther => 'Lain-lain';

  @override
  String get capabilityChat => 'Sembang';

  @override
  String get capabilityConversations => 'Perbualan';

  @override
  String get capabilityExternalIntegration => 'Integrasi Luaran';

  @override
  String get capabilityNotification => 'Pemberitahuan';

  @override
  String get triggerAudioBytes => 'Bait Audio';

  @override
  String get triggerConversationCreation => 'Penciptaan Perbualan';

  @override
  String get triggerTranscriptProcessed => 'Transkrip Diproses';

  @override
  String get actionCreateConversations => 'Cipta perbualan';

  @override
  String get actionCreateMemories => 'Cipta kenangan';

  @override
  String get actionReadConversations => 'Baca perbualan';

  @override
  String get actionReadMemories => 'Baca kenangan';

  @override
  String get actionReadTasks => 'Baca tugas';

  @override
  String get scopeUserName => 'Nama Pengguna';

  @override
  String get scopeUserFacts => 'Fakta Pengguna';

  @override
  String get scopeUserConversations => 'Perbualan Pengguna';

  @override
  String get scopeUserChat => 'Sembang Pengguna';

  @override
  String get capabilitySummary => 'Ringkasan';

  @override
  String get capabilityFeatured => 'Pilihan';

  @override
  String get capabilityTasks => 'Tugas';

  @override
  String get capabilityIntegrations => 'Integrasi';

  @override
  String get categoryPersonalityClones => 'Klon Personaliti';

  @override
  String get categoryProductivityLifestyle => 'Produktiviti & Gaya Hidup';

  @override
  String get categorySocialEntertainment => 'Sosial & Hiburan';

  @override
  String get categoryProductivityTools => 'Alat Produktiviti';

  @override
  String get categoryPersonalWellness => 'Kesejahteraan Peribadi';

  @override
  String get rating => 'Penilaian';

  @override
  String get categories => 'Kategori';

  @override
  String get sortBy => 'Isih';

  @override
  String get highestRating => 'Penilaian tertinggi';

  @override
  String get lowestRating => 'Penilaian terendah';

  @override
  String get resetFilters => 'Set semula penapis';

  @override
  String get applyFilters => 'Guna penapis';

  @override
  String get mostInstalls => 'Paling banyak dipasang';

  @override
  String get couldNotOpenUrl => 'Tidak dapat membuka URL. Sila cuba lagi.';

  @override
  String get newTask => 'Tugas baru';

  @override
  String get viewAll => 'Lihat semua';

  @override
  String get addTask => 'Tambah tugas';

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
  String get audioPlaybackUnavailable => 'Fail audio tidak tersedia untuk dimainkan';

  @override
  String get audioPlaybackFailed => 'Tidak dapat memainkan audio. Fail mungkin rosak atau hilang.';

  @override
  String get connectionGuide => 'Panduan Sambungan';

  @override
  String get iveDoneThis => 'Saya sudah buat ini';

  @override
  String get pairNewDevice => 'Pasangkan peranti baru';

  @override
  String get dontSeeYourDevice => 'Tidak nampak peranti anda?';

  @override
  String get reportAnIssue => 'Laporkan masalah';

  @override
  String get pairingTitleOmi => 'Hidupkan Omi';

  @override
  String get pairingDescOmi => 'Tekan dan tahan peranti sehingga ia bergetar untuk menghidupkannya.';

  @override
  String get pairingTitleOmiDevkit => 'Letakkan Omi DevKit dalam Mod Berpasangan';

  @override
  String get pairingDescOmiDevkit =>
      'Tekan butang sekali untuk menghidupkan. LED akan berkelip ungu dalam mod berpasangan.';

  @override
  String get pairingTitleOmiGlass => 'Hidupkan Omi Glass';

  @override
  String get pairingDescOmiGlass => 'Tekan dan tahan butang sisi selama 3 saat untuk menghidupkan.';

  @override
  String get pairingTitlePlaudNote => 'Letakkan Plaud Note dalam Mod Berpasangan';

  @override
  String get pairingDescPlaudNote =>
      'Tekan dan tahan butang sisi selama 2 saat. LED merah akan berkelip apabila sedia untuk berpasangan.';

  @override
  String get pairingTitleBee => 'Letakkan Bee dalam Mod Berpasangan';

  @override
  String get pairingDescBee => 'Tekan butang 5 kali berturut-turut. Lampu akan mula berkelip biru dan hijau.';

  @override
  String get pairingTitleLimitless => 'Letakkan Limitless dalam Mod Berpasangan';

  @override
  String get pairingDescLimitless =>
      'Apabila sebarang lampu kelihatan, tekan sekali kemudian tekan dan tahan sehingga peranti menunjukkan lampu merah jambu, kemudian lepaskan.';

  @override
  String get pairingTitleFriendPendant => 'Letakkan Friend Pendant dalam Mod Berpasangan';

  @override
  String get pairingDescFriendPendant =>
      'Tekan butang pada loket untuk menghidupkannya. Ia akan memasuki mod berpasangan secara automatik.';

  @override
  String get pairingTitleFieldy => 'Letakkan Fieldy dalam Mod Berpasangan';

  @override
  String get pairingDescFieldy => 'Tekan dan tahan peranti sehingga lampu muncul untuk menghidupkannya.';

  @override
  String get pairingTitleAppleWatch => 'Sambungkan Apple Watch';

  @override
  String get pairingDescAppleWatch =>
      'Pasang dan buka aplikasi Omi pada Apple Watch anda, kemudian ketik Sambung dalam aplikasi.';

  @override
  String get pairingTitleNeoOne => 'Letakkan Neo One dalam Mod Berpasangan';

  @override
  String get pairingDescNeoOne => 'Tekan dan tahan butang kuasa sehingga LED berkelip. Peranti akan boleh ditemui.';
}
