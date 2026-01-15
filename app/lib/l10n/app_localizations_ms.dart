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
  String get update => 'Kemas Kini';

  @override
  String get save => 'Simpan';

  @override
  String get edit => 'Edit';

  @override
  String get close => 'Tutup';

  @override
  String get clear => 'Kosongkan';

  @override
  String get copyTranscript => 'Salin Transkrip';

  @override
  String get copySummary => 'Salin Ringkasan';

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
  String get noInternetConnection => 'Sila semak sambungan internet anda dan cuba lagi.';

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
  String get disconnected => 'Terputus Sambungan';

  @override
  String get searching => 'Mencari';

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
  String get noConversationsYet => 'Tiada perbualan lagi.';

  @override
  String get noStarredConversations => 'Tiada perbualan berbintang lagi.';

  @override
  String get starConversationHint => 'Untuk membintangkan perbualan, buka dan ketik ikon bintang di pengepala.';

  @override
  String get searchConversations => 'Cari Perbualan';

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
  String get deletingMessages => 'Memadam mesej anda daripada ingatan Omi...';

  @override
  String get messageCopied => 'Mesej disalin ke papan keratan.';

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
  String get clearChat => 'Kosongkan Sembang?';

  @override
  String get clearChatConfirm => 'Adakah anda pasti mahu mengosongkan sembang? Tindakan ini tidak boleh dibatalkan.';

  @override
  String get maxFilesLimit => 'Anda hanya boleh memuat naik 4 fail pada satu masa';

  @override
  String get chatWithOmi => 'Sembang dengan Omi';

  @override
  String get apps => 'Aplikasi';

  @override
  String get noAppsFound => 'Tiada aplikasi dijumpai';

  @override
  String get tryAdjustingSearch => 'Cuba laraskan carian atau penapis anda';

  @override
  String get createYourOwnApp => 'Cipta Aplikasi Anda Sendiri';

  @override
  String get buildAndShareApp => 'Bina dan kongsi aplikasi tersuai anda';

  @override
  String get searchApps => 'Cari 1500+ Aplikasi';

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
  String get membersAndCounting => '8000+ ahli dan semakin bertambah.';

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
  String get identifyingOthers => 'Mengenal Pasti Orang Lain';

  @override
  String get paymentMethods => 'Kaedah Pembayaran';

  @override
  String get conversationDisplay => 'Paparan Perbualan';

  @override
  String get dataPrivacy => 'Data & Privasi';

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
  String get chatTools => 'Alat Sembang';

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
  String get wrapped2025 => 'Wrapped 2025';

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
  String get sdCardSync => 'Segerak Kad SD';

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
  String get unpairDevice => 'Nyahpasang Peranti';

  @override
  String get unpairAndForget => 'Nyahpasang dan Lupakan Peranti';

  @override
  String get deviceDisconnectedMessage => 'Omi anda telah diputuskan sambungan 😔';

  @override
  String get deviceUnpairedMessage =>
      'Peranti dinyahpasangkan. Pergi ke Tetapan > Bluetooth dan lupakan peranti untuk melengkapkan nyahpasangan.';

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
  String get docs => 'Dokumen';

  @override
  String get yourOmiInsights => 'Wawasan Omi Anda';

  @override
  String get today => 'Hari Ini';

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
  String get upgradeToUnlimited => 'Naik Taraf ke Tanpa Had';

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
  String get noLogFilesFound => 'Tiada fail log dijumpai.';

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
  String get knowledgeGraphDeleted => 'Graf Pengetahuan berjaya dipadam';

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
  String get authorizationBearer => 'Authorization: Bearer <key>';

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
  String get memories => 'Ingatan';

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
  String get connect => 'Sambung';

  @override
  String get comingSoon => 'Akan Datang';

  @override
  String get chatToolsFooter => 'Sambungkan aplikasi anda untuk melihat data dan metrik dalam sembang.';

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
  String get editName => 'Edit Nama';

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
  String get googleCalendar => 'Google Calendar';

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
  String get noUpcomingMeetings => 'Tiada mesyuarat akan datang dijumpai';

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
  String get noLanguagesFound => 'Tiada bahasa dijumpai';

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
  String get yesterday => 'semalam';

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
  String deviceUsesCodec(String deviceName, String codecReason) {
    return '$deviceName menggunakan $codecReason. Omi akan digunakan.';
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
  String get resetToDefault => 'Tetapkan Semula ke Lalai';

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
  String get appName => 'Nama Aplikasi';

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
  String get makePublic => 'Jadikan awam';

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
  String get createApp => 'Cipta Aplikasi';

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
  String get maybeLater => 'Mungkin kemudian';

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
  String get deleteActionItemTitle => 'Padam Item Tindakan';

  @override
  String get deleteActionItemMessage => 'Adakah anda pasti mahu memadam item tindakan ini?';

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
  String searchMemories(int count) {
    return 'Cari $count Ingatan';
  }

  @override
  String get memoryDeleted => 'Ingatan Dipadam.';

  @override
  String get undo => 'Buat Asal';

  @override
  String get noMemoriesYet => 'Tiada ingatan lagi';

  @override
  String get noAutoMemories => 'Tiada ingatan auto-ekstrak lagi';

  @override
  String get noManualMemories => 'Tiada ingatan manual lagi';

  @override
  String get noMemoriesInCategories => 'Tiada ingatan dalam kategori ini';

  @override
  String get noMemoriesFound => 'Tiada ingatan dijumpai';

  @override
  String get addFirstMemory => 'Tambah ingatan pertama anda';

  @override
  String get clearMemoryTitle => 'Kosongkan Ingatan Omi';

  @override
  String get clearMemoryMessage =>
      'Adakah anda pasti mahu mengosongkan ingatan Omi? Tindakan ini tidak boleh dibatalkan.';

  @override
  String get clearMemoryButton => 'Kosongkan Ingatan';

  @override
  String get memoryClearedSuccess => 'Ingatan Omi tentang anda telah dikosongkan';

  @override
  String get noMemoriesToDelete => 'Tiada ingatan untuk dipadam';

  @override
  String get createMemoryTooltip => 'Cipta ingatan baharu';

  @override
  String get createActionItemTooltip => 'Cipta item tindakan baharu';

  @override
  String get memoryManagement => 'Pengurusan Ingatan';

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
  String get deleteAllMemories => 'Padam Semua Ingatan';

  @override
  String get allMemoriesPrivateResult => 'Semua ingatan kini peribadi';

  @override
  String get allMemoriesPublicResult => 'Semua ingatan kini awam';

  @override
  String get newMemory => 'Ingatan Baharu';

  @override
  String get editMemory => 'Edit Ingatan';

  @override
  String get memoryContentHint => 'Saya suka makan ais krim...';

  @override
  String get failedToSaveMemory => 'Gagal menyimpan. Sila semak sambungan anda.';

  @override
  String get saveMemory => 'Simpan Ingatan';

  @override
  String get retry => 'Cuba Semula';

  @override
  String get createActionItem => 'Cipta Item Tindakan';

  @override
  String get editActionItem => 'Edit Item Tindakan';

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
  String get failedToCreateActionItem => 'Gagal mencipta item tindakan';

  @override
  String get dueDate => 'Tarikh Akhir';

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
  String get markComplete => 'Tandakan selesai';

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
}
