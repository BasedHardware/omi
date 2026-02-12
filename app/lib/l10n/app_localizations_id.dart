// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Indonesian (`id`).
class AppLocalizationsId extends AppLocalizations {
  AppLocalizationsId([String locale = 'id']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'Percakapan';

  @override
  String get transcriptTab => 'Transkrip';

  @override
  String get actionItemsTab => 'Item Tindakan';

  @override
  String get deleteConversationTitle => 'Hapus Percakapan?';

  @override
  String get deleteConversationMessage =>
      'Apakah Anda yakin ingin menghapus percakapan ini? Tindakan ini tidak dapat dibatalkan.';

  @override
  String get confirm => 'Konfirmasi';

  @override
  String get cancel => 'Batal';

  @override
  String get ok => 'Oke';

  @override
  String get delete => 'Hapus';

  @override
  String get add => 'Tambah';

  @override
  String get update => 'Perbarui';

  @override
  String get save => 'Simpan';

  @override
  String get edit => 'Edit';

  @override
  String get close => 'Tutup';

  @override
  String get clear => 'Bersihkan';

  @override
  String get copyTranscript => 'Salin transkrip';

  @override
  String get copySummary => 'Salin ringkasan';

  @override
  String get testPrompt => 'Uji Prompt';

  @override
  String get reprocessConversation => 'Proses Ulang Percakapan';

  @override
  String get deleteConversation => 'Hapus Percakapan';

  @override
  String get contentCopied => 'Konten disalin ke clipboard';

  @override
  String get failedToUpdateStarred => 'Gagal memperbarui status bintang.';

  @override
  String get conversationUrlNotShared => 'URL percakapan tidak dapat dibagikan.';

  @override
  String get errorProcessingConversation => 'Terjadi kesalahan saat memproses percakapan. Silakan coba lagi nanti.';

  @override
  String get noInternetConnection => 'Tidak ada koneksi internet';

  @override
  String get unableToDeleteConversation => 'Tidak Dapat Menghapus Percakapan';

  @override
  String get somethingWentWrong => 'Terjadi kesalahan! Silakan coba lagi nanti.';

  @override
  String get copyErrorMessage => 'Salin pesan kesalahan';

  @override
  String get errorCopied => 'Pesan kesalahan disalin ke clipboard';

  @override
  String get remaining => 'Tersisa';

  @override
  String get loading => 'Memuat...';

  @override
  String get loadingDuration => 'Memuat durasi...';

  @override
  String secondsCount(int count) {
    return '$count detik';
  }

  @override
  String get people => 'Orang';

  @override
  String get addNewPerson => 'Tambah Orang Baru';

  @override
  String get editPerson => 'Edit Orang';

  @override
  String get createPersonHint => 'Buat orang baru dan latih Omi untuk mengenali suara mereka juga!';

  @override
  String get speechProfile => 'Profil Suara';

  @override
  String sampleNumber(int number) {
    return 'Sampel $number';
  }

  @override
  String get settings => 'Pengaturan';

  @override
  String get language => 'Bahasa';

  @override
  String get selectLanguage => 'Pilih Bahasa';

  @override
  String get deleting => 'Menghapus...';

  @override
  String get pleaseCompleteAuthentication =>
      'Silakan selesaikan autentikasi di browser Anda. Setelah selesai, kembali ke aplikasi.';

  @override
  String get failedToStartAuthentication => 'Gagal memulai autentikasi';

  @override
  String get importStarted => 'Impor dimulai! Anda akan diberi tahu saat selesai.';

  @override
  String get failedToStartImport => 'Gagal memulai impor. Silakan coba lagi.';

  @override
  String get couldNotAccessFile => 'Tidak dapat mengakses file yang dipilih';

  @override
  String get askOmi => 'Tanya Omi';

  @override
  String get done => 'Selesai';

  @override
  String get disconnected => 'Terputus';

  @override
  String get searching => 'Mencari...';

  @override
  String get connectDevice => 'Hubungkan Perangkat';

  @override
  String get monthlyLimitReached => 'Anda telah mencapai batas bulanan.';

  @override
  String get checkUsage => 'Periksa Penggunaan';

  @override
  String get syncingRecordings => 'Menyinkronkan rekaman';

  @override
  String get recordingsToSync => 'Rekaman untuk disinkronkan';

  @override
  String get allCaughtUp => 'Semua sudah tersinkronisasi';

  @override
  String get sync => 'Sinkronkan';

  @override
  String get pendantUpToDate => 'Pendant sudah terbaru';

  @override
  String get allRecordingsSynced => 'Semua rekaman sudah tersinkronisasi';

  @override
  String get syncingInProgress => 'Sinkronisasi sedang berlangsung';

  @override
  String get readyToSync => 'Siap untuk disinkronkan';

  @override
  String get tapSyncToStart => 'Ketuk Sinkronkan untuk memulai';

  @override
  String get pendantNotConnected => 'Pendant tidak terhubung. Hubungkan untuk menyinkronkan.';

  @override
  String get everythingSynced => 'Semuanya sudah tersinkronisasi.';

  @override
  String get recordingsNotSynced => 'Anda memiliki rekaman yang belum disinkronkan.';

  @override
  String get syncingBackground => 'Kami akan terus menyinkronkan rekaman Anda di latar belakang.';

  @override
  String get noConversationsYet => 'Belum ada percakapan';

  @override
  String get noStarredConversations => 'Tidak ada percakapan berbintang';

  @override
  String get starConversationHint => 'Untuk memberi bintang pada percakapan, buka dan ketuk ikon bintang di header.';

  @override
  String get searchConversations => 'Cari percakapan...';

  @override
  String selectedCount(int count, Object s) {
    return '$count dipilih';
  }

  @override
  String get merge => 'Gabungkan';

  @override
  String get mergeConversations => 'Gabungkan Percakapan';

  @override
  String mergeConversationsMessage(int count) {
    return 'Ini akan menggabungkan $count percakapan menjadi satu. Semua konten akan digabungkan dan dibuat ulang.';
  }

  @override
  String get mergingInBackground => 'Menggabungkan di latar belakang. Ini mungkin memakan waktu sebentar.';

  @override
  String get failedToStartMerge => 'Gagal memulai penggabungan';

  @override
  String get askAnything => 'Tanyakan apa saja';

  @override
  String get noMessagesYet => 'Belum ada pesan!\nMengapa tidak memulai percakapan?';

  @override
  String get deletingMessages => 'Menghapus pesan Anda dari memori Omi...';

  @override
  String get messageCopied => '✨ Pesan disalin ke clipboard';

  @override
  String get cannotReportOwnMessage => 'Anda tidak dapat melaporkan pesan Anda sendiri.';

  @override
  String get reportMessage => 'Laporkan Pesan';

  @override
  String get reportMessageConfirm => 'Apakah Anda yakin ingin melaporkan pesan ini?';

  @override
  String get messageReported => 'Pesan berhasil dilaporkan.';

  @override
  String get thankYouFeedback => 'Terima kasih atas masukan Anda!';

  @override
  String get clearChat => 'Hapus Obrolan';

  @override
  String get clearChatConfirm => 'Apakah Anda yakin ingin menghapus obrolan? Tindakan ini tidak dapat dibatalkan.';

  @override
  String get maxFilesLimit => 'Anda hanya dapat mengunggah 4 file sekaligus';

  @override
  String get chatWithOmi => 'Obrolan dengan Omi';

  @override
  String get apps => 'Aplikasi';

  @override
  String get noAppsFound => 'Tidak ada aplikasi yang ditemukan';

  @override
  String get tryAdjustingSearch => 'Coba sesuaikan pencarian atau filter Anda';

  @override
  String get createYourOwnApp => 'Buat Aplikasi Anda Sendiri';

  @override
  String get buildAndShareApp => 'Bangun dan bagikan aplikasi kustom Anda';

  @override
  String get searchApps => 'Cari aplikasi...';

  @override
  String get myApps => 'Aplikasi Saya';

  @override
  String get installedApps => 'Aplikasi Terinstal';

  @override
  String get unableToFetchApps =>
      'Tidak dapat mengambil aplikasi :(\n\nSilakan periksa koneksi internet Anda dan coba lagi.';

  @override
  String get aboutOmi => 'Tentang Omi';

  @override
  String get privacyPolicy => 'Kebijakan Privasi';

  @override
  String get visitWebsite => 'Kunjungi Situs Web';

  @override
  String get helpOrInquiries => 'Bantuan atau Pertanyaan?';

  @override
  String get joinCommunity => 'Bergabung dengan komunitas!';

  @override
  String get membersAndCounting => '8000+ anggota dan terus bertambah.';

  @override
  String get deleteAccountTitle => 'Hapus Akun';

  @override
  String get deleteAccountConfirm => 'Apakah Anda yakin ingin menghapus akun Anda?';

  @override
  String get cannotBeUndone => 'Ini tidak dapat dibatalkan.';

  @override
  String get allDataErased => 'Semua memori dan percakapan Anda akan dihapus secara permanen.';

  @override
  String get appsDisconnected => 'Aplikasi dan Integrasi Anda akan segera diputuskan.';

  @override
  String get exportBeforeDelete =>
      'Anda dapat mengekspor data Anda sebelum menghapus akun, tetapi setelah dihapus, tidak dapat dipulihkan.';

  @override
  String get deleteAccountCheckbox =>
      'Saya memahami bahwa menghapus akun saya bersifat permanen dan semua data, termasuk memori dan percakapan, akan hilang dan tidak dapat dipulihkan.';

  @override
  String get areYouSure => 'Apakah Anda yakin?';

  @override
  String get deleteAccountFinal =>
      'Tindakan ini tidak dapat dibatalkan dan akan menghapus akun dan semua data terkait secara permanen. Apakah Anda yakin ingin melanjutkan?';

  @override
  String get deleteNow => 'Hapus Sekarang';

  @override
  String get goBack => 'Kembali';

  @override
  String get checkBoxToConfirm =>
      'Centang kotak untuk mengonfirmasi bahwa Anda memahami penghapusan akun bersifat permanen dan tidak dapat dibatalkan.';

  @override
  String get profile => 'Profil';

  @override
  String get name => 'Nama';

  @override
  String get email => 'Email';

  @override
  String get customVocabulary => 'Kosakata Kustom';

  @override
  String get identifyingOthers => 'Mengidentifikasi Orang Lain';

  @override
  String get paymentMethods => 'Metode Pembayaran';

  @override
  String get conversationDisplay => 'Tampilan Percakapan';

  @override
  String get dataPrivacy => 'Privasi Data';

  @override
  String get userId => 'ID Pengguna';

  @override
  String get notSet => 'Tidak diatur';

  @override
  String get userIdCopied => 'ID Pengguna disalin ke clipboard';

  @override
  String get systemDefault => 'Bawaan Sistem';

  @override
  String get planAndUsage => 'Paket & Penggunaan';

  @override
  String get offlineSync => 'Offline Sync';

  @override
  String get deviceSettings => 'Pengaturan Perangkat';

  @override
  String get integrations => 'Integrasi';

  @override
  String get feedbackBug => 'Masukan / Bug';

  @override
  String get helpCenter => 'Pusat Bantuan';

  @override
  String get developerSettings => 'Pengaturan Pengembang';

  @override
  String get getOmiForMac => 'Dapatkan Omi untuk Mac';

  @override
  String get referralProgram => 'Program Rujukan';

  @override
  String get signOut => 'Keluar';

  @override
  String get appAndDeviceCopied => 'Detail aplikasi dan perangkat disalin';

  @override
  String get wrapped2025 => 'Rangkuman 2025';

  @override
  String get yourPrivacyYourControl => 'Privasi Anda, Kontrol Anda';

  @override
  String get privacyIntro =>
      'Di Omi, kami berkomitmen untuk melindungi privasi Anda. Halaman ini memungkinkan Anda mengontrol bagaimana data Anda disimpan dan digunakan.';

  @override
  String get learnMore => 'Pelajari lebih lanjut...';

  @override
  String get dataProtectionLevel => 'Tingkat Perlindungan Data';

  @override
  String get dataProtectionDesc =>
      'Data Anda diamankan secara default dengan enkripsi yang kuat. Tinjau pengaturan dan opsi privasi Anda di bawah ini.';

  @override
  String get appAccess => 'Akses Aplikasi';

  @override
  String get appAccessDesc => 'Aplikasi berikut dapat mengakses data Anda. Ketuk aplikasi untuk mengelola izinnya.';

  @override
  String get noAppsExternalAccess => 'Tidak ada aplikasi terinstal yang memiliki akses eksternal ke data Anda.';

  @override
  String get deviceName => 'Nama Perangkat';

  @override
  String get deviceId => 'ID Perangkat';

  @override
  String get firmware => 'Firmware';

  @override
  String get sdCardSync => 'Sinkronisasi Kartu SD';

  @override
  String get hardwareRevision => 'Revisi Perangkat Keras';

  @override
  String get modelNumber => 'Nomor Model';

  @override
  String get manufacturer => 'Produsen';

  @override
  String get doubleTap => 'Ketuk Ganda';

  @override
  String get ledBrightness => 'Kecerahan LED';

  @override
  String get micGain => 'Penguatan Mikrofon';

  @override
  String get disconnect => 'Putuskan';

  @override
  String get forgetDevice => 'Lupakan Perangkat';

  @override
  String get chargingIssues => 'Masalah Pengisian Daya';

  @override
  String get disconnectDevice => 'Putuskan Koneksi Perangkat';

  @override
  String get unpairDevice => 'Putuskan Pemasangan Perangkat';

  @override
  String get unpairAndForget => 'Batalkan Pasangan dan Lupakan Perangkat';

  @override
  String get deviceDisconnectedMessage => 'Omi Anda telah terputus 😔';

  @override
  String get deviceUnpairedMessage =>
      'Perangkat diputuskan pemasangannya. Buka Pengaturan > Bluetooth dan lupakan perangkat untuk menyelesaikan pemutusan pemasangan.';

  @override
  String get unpairDialogTitle => 'Batalkan Pasangan Perangkat';

  @override
  String get unpairDialogMessage =>
      'Ini akan membatalkan pasangan perangkat sehingga dapat dihubungkan ke ponsel lain. Anda perlu pergi ke Pengaturan > Bluetooth dan melupakan perangkat untuk menyelesaikan proses.';

  @override
  String get deviceNotConnected => 'Perangkat Tidak Terhubung';

  @override
  String get connectDeviceMessage =>
      'Hubungkan perangkat Omi Anda untuk mengakses\npengaturan dan kustomisasi perangkat';

  @override
  String get deviceInfoSection => 'Informasi Perangkat';

  @override
  String get customizationSection => 'Kustomisasi';

  @override
  String get hardwareSection => 'Perangkat Keras';

  @override
  String get v2Undetected => 'V2 tidak terdeteksi';

  @override
  String get v2UndetectedMessage =>
      'Kami melihat bahwa Anda memiliki perangkat V1 atau perangkat Anda tidak terhubung. Fungsi Kartu SD hanya tersedia untuk perangkat V2.';

  @override
  String get endConversation => 'Akhiri Percakapan';

  @override
  String get pauseResume => 'Jeda/Lanjutkan';

  @override
  String get starConversation => 'Beri Bintang Percakapan';

  @override
  String get doubleTapAction => 'Aksi Ketuk Ganda';

  @override
  String get endAndProcess => 'Akhiri & Proses Percakapan';

  @override
  String get pauseResumeRecording => 'Jeda/Lanjutkan Perekaman';

  @override
  String get starOngoing => 'Beri Bintang Percakapan yang Sedang Berlangsung';

  @override
  String get off => 'Nonaktif';

  @override
  String get max => 'Maksimal';

  @override
  String get mute => 'Bisukan';

  @override
  String get quiet => 'Pelan';

  @override
  String get normal => 'Normal';

  @override
  String get high => 'Tinggi';

  @override
  String get micGainDescMuted => 'Mikrofon dibisukan';

  @override
  String get micGainDescLow => 'Sangat pelan - untuk lingkungan bising';

  @override
  String get micGainDescModerate => 'Pelan - untuk kebisingan sedang';

  @override
  String get micGainDescNeutral => 'Netral - perekaman seimbang';

  @override
  String get micGainDescSlightlyBoosted => 'Sedikit ditingkatkan - penggunaan normal';

  @override
  String get micGainDescBoosted => 'Ditingkatkan - untuk lingkungan sunyi';

  @override
  String get micGainDescHigh => 'Tinggi - untuk suara jauh atau lembut';

  @override
  String get micGainDescVeryHigh => 'Sangat tinggi - untuk sumber sangat sunyi';

  @override
  String get micGainDescMax => 'Maksimum - gunakan dengan hati-hati';

  @override
  String get developerSettingsTitle => 'Pengaturan Pengembang';

  @override
  String get saving => 'Menyimpan...';

  @override
  String get personaConfig => 'Konfigurasi persona AI Anda';

  @override
  String get beta => 'BETA';

  @override
  String get transcription => 'Transkripsi';

  @override
  String get transcriptionConfig => 'Konfigurasi penyedia STT';

  @override
  String get conversationTimeout => 'Waktu Tunggu Percakapan';

  @override
  String get conversationTimeoutConfig => 'Atur kapan percakapan berakhir otomatis';

  @override
  String get importData => 'Impor Data';

  @override
  String get importDataConfig => 'Impor data dari sumber lain';

  @override
  String get debugDiagnostics => 'Debug & Diagnostik';

  @override
  String get endpointUrl => 'URL Endpoint';

  @override
  String get noApiKeys => 'Belum ada kunci API';

  @override
  String get createKeyToStart => 'Buat kunci untuk memulai';

  @override
  String get createKey => 'Buat Kunci';

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
  String get allTime => 'Sepanjang Waktu';

  @override
  String get noActivityYet => 'Belum Ada Aktivitas';

  @override
  String get startConversationToSeeInsights =>
      'Mulai percakapan dengan Omi\nuntuk melihat wawasan penggunaan Anda di sini.';

  @override
  String get listening => 'Mendengarkan';

  @override
  String get listeningSubtitle => 'Total waktu Omi mendengarkan secara aktif.';

  @override
  String get understanding => 'Memahami';

  @override
  String get understandingSubtitle => 'Kata-kata yang dipahami dari percakapan Anda.';

  @override
  String get providing => 'Memberikan';

  @override
  String get providingSubtitle => 'Item tindakan dan catatan yang secara otomatis ditangkap.';

  @override
  String get remembering => 'Mengingat';

  @override
  String get rememberingSubtitle => 'Fakta dan detail yang diingat untuk Anda.';

  @override
  String get unlimitedPlan => 'Paket Tanpa Batas';

  @override
  String get managePlan => 'Kelola Paket';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'Paket Anda akan dibatalkan pada $date.';
  }

  @override
  String renewsOn(String date) {
    return 'Paket Anda diperbarui pada $date.';
  }

  @override
  String get basicPlan => 'Paket Gratis';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used dari $limit menit terpakai';
  }

  @override
  String get upgrade => 'Tingkatkan';

  @override
  String get upgradeToUnlimited => 'Tingkatkan ke tanpa batas';

  @override
  String basicPlanDesc(int limit) {
    return 'Paket Anda mencakup $limit menit gratis per bulan. Tingkatkan untuk tanpa batas.';
  }

  @override
  String get shareStatsMessage => 'Membagikan statistik Omi saya! (omi.me - asisten AI yang selalu aktif)';

  @override
  String get sharePeriodToday => 'Hari ini, omi telah:';

  @override
  String get sharePeriodMonth => 'Bulan ini, omi telah:';

  @override
  String get sharePeriodYear => 'Tahun ini, omi telah:';

  @override
  String get sharePeriodAllTime => 'Sejauh ini, omi telah:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 Mendengarkan selama $minutes menit';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 Memahami $words kata';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ Memberikan $count wawasan';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 Mengingat $count memori';
  }

  @override
  String get debugLogs => 'Log Debug';

  @override
  String get debugLogsAutoDelete => 'Otomatis dihapus setelah 3 hari.';

  @override
  String get debugLogsDesc => 'Membantu mendiagnosis masalah';

  @override
  String get noLogFilesFound => 'File log tidak ditemukan.';

  @override
  String get omiDebugLog => 'Log debug Omi';

  @override
  String get logShared => 'Log dibagikan';

  @override
  String get selectLogFile => 'Pilih File Log';

  @override
  String get shareLogs => 'Bagikan Log';

  @override
  String get debugLogCleared => 'Log debug dibersihkan';

  @override
  String get exportStarted => 'Ekspor dimulai. Ini mungkin memakan waktu beberapa detik...';

  @override
  String get exportAllData => 'Ekspor Semua Data';

  @override
  String get exportDataDesc => 'Ekspor percakapan ke file JSON';

  @override
  String get exportedConversations => 'Percakapan yang Diekspor dari Omi';

  @override
  String get exportShared => 'Ekspor dibagikan';

  @override
  String get deleteKnowledgeGraphTitle => 'Hapus Grafik Pengetahuan?';

  @override
  String get deleteKnowledgeGraphMessage =>
      'Ini akan menghapus semua data grafik pengetahuan turunan (simpul dan koneksi). Memori asli Anda akan tetap aman. Grafik akan dibangun kembali seiring waktu atau pada permintaan berikutnya.';

  @override
  String get knowledgeGraphDeleted => 'Grafik pengetahuan dihapus';

  @override
  String deleteGraphFailed(String error) {
    return 'Gagal menghapus grafik: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'Hapus Grafik Pengetahuan';

  @override
  String get deleteKnowledgeGraphDesc => 'Bersihkan semua simpul dan koneksi';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'Server MCP';

  @override
  String get mcpServerDesc => 'Hubungkan asisten AI ke data Anda';

  @override
  String get serverUrl => 'URL Server';

  @override
  String get urlCopied => 'URL disalin';

  @override
  String get apiKeyAuth => 'Autentikasi Kunci API';

  @override
  String get header => 'Header';

  @override
  String get authorizationBearer => 'Authorization: Bearer <key>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'ID Klien';

  @override
  String get clientSecret => 'Rahasia Klien';

  @override
  String get useMcpApiKey => 'Gunakan kunci API MCP Anda';

  @override
  String get webhooks => 'Webhook';

  @override
  String get conversationEvents => 'Acara Percakapan';

  @override
  String get newConversationCreated => 'Percakapan baru dibuat';

  @override
  String get realtimeTranscript => 'Transkrip Waktu Nyata';

  @override
  String get transcriptReceived => 'Transkrip diterima';

  @override
  String get audioBytes => 'Byte Audio';

  @override
  String get audioDataReceived => 'Data audio diterima';

  @override
  String get intervalSeconds => 'Interval (detik)';

  @override
  String get daySummary => 'Ringkasan Hari';

  @override
  String get summaryGenerated => 'Ringkasan dibuat';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'Tambahkan ke claude_desktop_config.json';

  @override
  String get copyConfig => 'Salin Konfigurasi';

  @override
  String get configCopied => 'Konfigurasi disalin ke clipboard';

  @override
  String get listeningMins => 'Mendengarkan (menit)';

  @override
  String get understandingWords => 'Memahami (kata)';

  @override
  String get insights => 'Wawasan';

  @override
  String get memories => 'Kenangan';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '$used dari $limit menit terpakai bulan ini';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '$used dari $limit kata terpakai bulan ini';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '$used dari $limit wawasan diperoleh bulan ini';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return '$used dari $limit memori dibuat bulan ini';
  }

  @override
  String get visibility => 'Visibilitas';

  @override
  String get visibilitySubtitle => 'Kontrol percakapan mana yang muncul di daftar Anda';

  @override
  String get showShortConversations => 'Tampilkan Percakapan Pendek';

  @override
  String get showShortConversationsDesc => 'Tampilkan percakapan yang lebih pendek dari ambang batas';

  @override
  String get showDiscardedConversations => 'Tampilkan Percakapan yang Dibuang';

  @override
  String get showDiscardedConversationsDesc => 'Sertakan percakapan yang ditandai sebagai dibuang';

  @override
  String get shortConversationThreshold => 'Ambang Percakapan Pendek';

  @override
  String get shortConversationThresholdSubtitle =>
      'Percakapan yang lebih pendek dari ini akan disembunyikan kecuali diaktifkan di atas';

  @override
  String get durationThreshold => 'Ambang Durasi';

  @override
  String get durationThresholdDesc => 'Sembunyikan percakapan yang lebih pendek dari ini';

  @override
  String minLabel(int count) {
    return '$count menit';
  }

  @override
  String get customVocabularyTitle => 'Kosakata Kustom';

  @override
  String get addWords => 'Tambah Kata';

  @override
  String get addWordsDesc => 'Nama, istilah, atau kata yang tidak umum';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'Connect';

  @override
  String get comingSoon => 'Segera Hadir';

  @override
  String get integrationsFooter => 'Hubungkan aplikasi Anda untuk melihat data dan metrik dalam obrolan.';

  @override
  String get completeAuthInBrowser =>
      'Silakan selesaikan autentikasi di browser Anda. Setelah selesai, kembali ke aplikasi.';

  @override
  String failedToStartAuth(String appName) {
    return 'Gagal memulai autentikasi $appName';
  }

  @override
  String disconnectAppTitle(String appName) {
    return 'Putuskan $appName?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'Apakah Anda yakin ingin memutuskan dari $appName? Anda dapat menyambung kembali kapan saja.';
  }

  @override
  String disconnectedFrom(String appName) {
    return 'Terputus dari $appName';
  }

  @override
  String get failedToDisconnect => 'Gagal memutuskan';

  @override
  String connectTo(String appName) {
    return 'Hubungkan ke $appName';
  }

  @override
  String authAccessMessage(String appName) {
    return 'Anda perlu mengizinkan Omi untuk mengakses data $appName Anda. Ini akan membuka browser Anda untuk autentikasi.';
  }

  @override
  String get continueAction => 'Lanjutkan';

  @override
  String get languageTitle => 'Bahasa';

  @override
  String get primaryLanguage => 'Bahasa Utama';

  @override
  String get automaticTranslation => 'Terjemahan Otomatis';

  @override
  String get detectLanguages => 'Deteksi 10+ bahasa';

  @override
  String get authorizeSavingRecordings => 'Izinkan Menyimpan Rekaman';

  @override
  String get thanksForAuthorizing => 'Terima kasih telah mengizinkan!';

  @override
  String get needYourPermission => 'Kami memerlukan izin Anda';

  @override
  String get alreadyGavePermission =>
      'Anda sudah memberi kami izin untuk menyimpan rekaman Anda. Berikut pengingat mengapa kami membutuhkannya:';

  @override
  String get wouldLikePermission => 'Kami ingin izin Anda untuk menyimpan rekaman suara Anda. Berikut alasannya:';

  @override
  String get improveSpeechProfile => 'Tingkatkan Profil Suara Anda';

  @override
  String get improveSpeechProfileDesc =>
      'Kami menggunakan rekaman untuk melatih dan meningkatkan profil suara pribadi Anda lebih lanjut.';

  @override
  String get trainFamilyProfiles => 'Latih Profil untuk Teman dan Keluarga';

  @override
  String get trainFamilyProfilesDesc =>
      'Rekaman Anda membantu kami mengenali dan membuat profil untuk teman dan keluarga Anda.';

  @override
  String get enhanceTranscriptAccuracy => 'Tingkatkan Akurasi Transkrip';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'Seiring model kami meningkat, kami dapat memberikan hasil transkripsi yang lebih baik untuk rekaman Anda.';

  @override
  String get legalNotice =>
      'Pemberitahuan Hukum: Legalitas merekam dan menyimpan data suara dapat bervariasi tergantung pada lokasi Anda dan bagaimana Anda menggunakan fitur ini. Ini adalah tanggung jawab Anda untuk memastikan kepatuhan terhadap hukum dan peraturan lokal.';

  @override
  String get alreadyAuthorized => 'Sudah Diizinkan';

  @override
  String get authorize => 'Izinkan';

  @override
  String get revokeAuthorization => 'Cabut Izin';

  @override
  String get authorizationSuccessful => 'Otorisasi berhasil!';

  @override
  String get failedToAuthorize => 'Gagal mengotorisasi. Silakan coba lagi.';

  @override
  String get authorizationRevoked => 'Otorisasi dicabut.';

  @override
  String get recordingsDeleted => 'Rekaman dihapus.';

  @override
  String get failedToRevoke => 'Gagal mencabut otorisasi. Silakan coba lagi.';

  @override
  String get permissionRevokedTitle => 'Izin Dicabut';

  @override
  String get permissionRevokedMessage => 'Apakah Anda ingin kami menghapus semua rekaman Anda yang ada juga?';

  @override
  String get yes => 'Ya';

  @override
  String get editName => 'Edit Name';

  @override
  String get howShouldOmiCallYou => 'Bagaimana Omi harus memanggil Anda?';

  @override
  String get enterYourName => 'Masukkan nama Anda';

  @override
  String get nameCannotBeEmpty => 'Nama tidak boleh kosong';

  @override
  String get nameUpdatedSuccessfully => 'Nama berhasil diperbarui!';

  @override
  String get calendarSettings => 'Pengaturan kalender';

  @override
  String get calendarProviders => 'Penyedia Kalender';

  @override
  String get macOsCalendar => 'Kalender macOS';

  @override
  String get connectMacOsCalendar => 'Hubungkan kalender macOS lokal Anda';

  @override
  String get googleCalendar => 'Google Calendar';

  @override
  String get syncGoogleAccount => 'Sinkronkan dengan akun Google Anda';

  @override
  String get showMeetingsMenuBar => 'Tampilkan rapat mendatang di bilah menu';

  @override
  String get showMeetingsMenuBarDesc => 'Tampilkan rapat berikutnya dan waktu hingga dimulai di bilah menu macOS';

  @override
  String get showEventsNoParticipants => 'Tampilkan acara tanpa peserta';

  @override
  String get showEventsNoParticipantsDesc =>
      'Saat diaktifkan, Coming Up menampilkan acara tanpa peserta atau tautan video.';

  @override
  String get yourMeetings => 'Rapat Anda';

  @override
  String get refresh => 'Segarkan';

  @override
  String get noUpcomingMeetings => 'Tidak ada pertemuan mendatang';

  @override
  String get checkingNextDays => 'Memeriksa 30 hari ke depan';

  @override
  String get tomorrow => 'Besok';

  @override
  String get googleCalendarComingSoon => 'Integrasi Google Calendar segera hadir!';

  @override
  String connectedAsUser(String userId) {
    return 'Terhubung sebagai pengguna: $userId';
  }

  @override
  String get defaultWorkspace => 'Ruang Kerja Default';

  @override
  String get tasksCreatedInWorkspace => 'Tugas akan dibuat di ruang kerja ini';

  @override
  String get defaultProjectOptional => 'Proyek Default (Opsional)';

  @override
  String get leaveUnselectedTasks => 'Biarkan tidak dipilih untuk membuat tugas tanpa proyek';

  @override
  String get noProjectsInWorkspace => 'Tidak ada proyek ditemukan di ruang kerja ini';

  @override
  String get conversationTimeoutDesc =>
      'Pilih berapa lama menunggu dalam keheningan sebelum otomatis mengakhiri percakapan:';

  @override
  String get timeout2Minutes => '2 menit';

  @override
  String get timeout2MinutesDesc => 'Akhiri percakapan setelah 2 menit keheningan';

  @override
  String get timeout5Minutes => '5 menit';

  @override
  String get timeout5MinutesDesc => 'Akhiri percakapan setelah 5 menit keheningan';

  @override
  String get timeout10Minutes => '10 menit';

  @override
  String get timeout10MinutesDesc => 'Akhiri percakapan setelah 10 menit keheningan';

  @override
  String get timeout30Minutes => '30 menit';

  @override
  String get timeout30MinutesDesc => 'Akhiri percakapan setelah 30 menit keheningan';

  @override
  String get timeout4Hours => '4 jam';

  @override
  String get timeout4HoursDesc => 'Akhiri percakapan setelah 4 jam keheningan';

  @override
  String get conversationEndAfterHours => 'Percakapan sekarang akan berakhir setelah 4 jam keheningan';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Percakapan sekarang akan berakhir setelah $minutes menit keheningan';
  }

  @override
  String get tellUsPrimaryLanguage => 'Beri tahu kami bahasa utama Anda';

  @override
  String get languageForTranscription =>
      'Atur bahasa Anda untuk transkripsi yang lebih tajam dan pengalaman yang dipersonalisasi.';

  @override
  String get singleLanguageModeInfo =>
      'Mode Bahasa Tunggal diaktifkan. Terjemahan dinonaktifkan untuk akurasi yang lebih tinggi.';

  @override
  String get searchLanguageHint => 'Cari bahasa berdasarkan nama atau kode';

  @override
  String get noLanguagesFound => 'Tidak ada bahasa yang ditemukan';

  @override
  String get skip => 'Lewati';

  @override
  String languageSetTo(String language) {
    return 'Bahasa diatur ke $language';
  }

  @override
  String get failedToSetLanguage => 'Gagal mengatur bahasa';

  @override
  String appSettings(String appName) {
    return 'Pengaturan $appName';
  }

  @override
  String disconnectFromApp(String appName) {
    return 'Putuskan dari $appName?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'Ini akan menghapus autentikasi $appName Anda. Anda perlu menyambung kembali untuk menggunakannya lagi.';
  }

  @override
  String connectedToApp(String appName) {
    return 'Terhubung ke $appName';
  }

  @override
  String get account => 'Akun';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Item tindakan Anda akan disinkronkan ke akun $appName Anda';
  }

  @override
  String get defaultSpace => 'Ruang Default';

  @override
  String get selectSpaceInWorkspace => 'Pilih ruang di ruang kerja Anda';

  @override
  String get noSpacesInWorkspace => 'Tidak ada ruang ditemukan di ruang kerja ini';

  @override
  String get defaultList => 'Daftar Default';

  @override
  String get tasksAddedToList => 'Tugas akan ditambahkan ke daftar ini';

  @override
  String get noListsInSpace => 'Tidak ada daftar ditemukan di ruang ini';

  @override
  String failedToLoadRepos(String error) {
    return 'Gagal memuat repositori: $error';
  }

  @override
  String get defaultRepoSaved => 'Repositori default disimpan';

  @override
  String get failedToSaveDefaultRepo => 'Gagal menyimpan repositori default';

  @override
  String get defaultRepository => 'Repositori Default';

  @override
  String get selectDefaultRepoDesc =>
      'Pilih repositori default untuk membuat issue. Anda masih dapat menentukan repositori yang berbeda saat membuat issue.';

  @override
  String get noReposFound => 'Tidak ada repositori ditemukan';

  @override
  String get private => 'Privat';

  @override
  String updatedDate(String date) {
    return 'Diperbarui $date';
  }

  @override
  String get yesterday => 'Kemarin';

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
  String get issuesCreatedInRepo => 'Issue akan dibuat di repositori default Anda';

  @override
  String get taskIntegrations => 'Integrasi Tugas';

  @override
  String get configureSettings => 'Konfigurasi Pengaturan';

  @override
  String get completeAuthBrowser =>
      'Silakan selesaikan autentikasi di browser Anda. Setelah selesai, kembali ke aplikasi.';

  @override
  String failedToStartAppAuth(String appName) {
    return 'Gagal memulai autentikasi $appName';
  }

  @override
  String connectToAppTitle(String appName) {
    return 'Hubungkan ke $appName';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Anda perlu mengizinkan Omi untuk membuat tugas di akun $appName Anda. Ini akan membuka browser Anda untuk autentikasi.';
  }

  @override
  String get continueButton => 'Lanjutkan';

  @override
  String appIntegration(String appName) {
    return 'Integrasi $appName';
  }

  @override
  String integrationComingSoon(String appName) {
    return 'Integrasi dengan $appName segera hadir! Kami bekerja keras untuk memberikan Anda lebih banyak opsi manajemen tugas.';
  }

  @override
  String get gotIt => 'Mengerti';

  @override
  String get tasksExportedOneApp => 'Tugas dapat diekspor ke satu aplikasi pada satu waktu.';

  @override
  String get completeYourUpgrade => 'Selesaikan Peningkatan Anda';

  @override
  String get importConfiguration => 'Impor Konfigurasi';

  @override
  String get exportConfiguration => 'Ekspor konfigurasi';

  @override
  String get bringYourOwn => 'Bawa sendiri';

  @override
  String get payYourSttProvider => 'Gunakan omi secara bebas. Anda hanya membayar penyedia STT Anda secara langsung.';

  @override
  String get freeMinutesMonth => '1.200 menit gratis/bulan termasuk. Tanpa batas dengan ';

  @override
  String get omiUnlimited => 'Omi Unlimited';

  @override
  String get hostRequired => 'Host diperlukan';

  @override
  String get validPortRequired => 'Port yang valid diperlukan';

  @override
  String get validWebsocketUrlRequired => 'URL WebSocket yang valid diperlukan (wss://)';

  @override
  String get apiUrlRequired => 'URL API diperlukan';

  @override
  String get apiKeyRequired => 'Kunci API diperlukan';

  @override
  String get invalidJsonConfig => 'Konfigurasi JSON tidak valid';

  @override
  String errorSaving(String error) {
    return 'Kesalahan menyimpan: $error';
  }

  @override
  String get configCopiedToClipboard => 'Konfigurasi disalin ke clipboard';

  @override
  String get pasteJsonConfig => 'Tempel konfigurasi JSON Anda di bawah ini:';

  @override
  String get addApiKeyAfterImport => 'Anda perlu menambahkan kunci API Anda sendiri setelah mengimpor';

  @override
  String get paste => 'Tempel';

  @override
  String get import => 'Impor';

  @override
  String get invalidProviderInConfig => 'Penyedia tidak valid dalam konfigurasi';

  @override
  String importedConfig(String providerName) {
    return 'Konfigurasi $providerName diimpor';
  }

  @override
  String invalidJson(String error) {
    return 'JSON tidak valid: $error';
  }

  @override
  String get provider => 'Penyedia';

  @override
  String get live => 'Langsung';

  @override
  String get onDevice => 'Di Perangkat';

  @override
  String get apiUrl => 'URL API';

  @override
  String get enterSttHttpEndpoint => 'Masukkan endpoint HTTP STT Anda';

  @override
  String get websocketUrl => 'URL WebSocket';

  @override
  String get enterLiveSttWebsocket => 'Masukkan endpoint WebSocket STT langsung Anda';

  @override
  String get apiKey => 'Kunci API';

  @override
  String get enterApiKey => 'Masukkan kunci API Anda';

  @override
  String get storedLocallyNeverShared => 'Disimpan secara lokal, tidak pernah dibagikan';

  @override
  String get host => 'Host';

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
  String get modified => 'Dimodifikasi';

  @override
  String get resetRequestConfig => 'Setel ulang konfigurasi permintaan ke default';

  @override
  String get logs => 'Log';

  @override
  String get logsCopied => 'Log disalin';

  @override
  String get noLogsYet => 'Belum ada log. Mulai merekam untuk melihat aktivitas STT kustom.';

  @override
  String deviceUsesCodec(String device, String reason) {
    return '$device menggunakan $reason. Omi akan digunakan.';
  }

  @override
  String get omiTranscription => 'Transkripsi Omi';

  @override
  String get bestInClassTranscription => 'Transkripsi terbaik di kelasnya tanpa pengaturan';

  @override
  String get instantSpeakerLabels => 'Label pembicara instan';

  @override
  String get languageTranslation => 'Terjemahan 100+ bahasa';

  @override
  String get optimizedForConversation => 'Dioptimalkan untuk percakapan';

  @override
  String get autoLanguageDetection => 'Deteksi bahasa otomatis';

  @override
  String get highAccuracy => 'Akurasi tinggi';

  @override
  String get privacyFirst => 'Privasi utama';

  @override
  String get saveChanges => 'Simpan Perubahan';

  @override
  String get resetToDefault => 'Atur ulang ke default';

  @override
  String get viewTemplate => 'Lihat Template';

  @override
  String get trySomethingLike => 'Coba sesuatu seperti...';

  @override
  String get tryIt => 'Coba';

  @override
  String get creatingPlan => 'Membuat rencana';

  @override
  String get developingLogic => 'Mengembangkan logika';

  @override
  String get designingApp => 'Mendesain aplikasi';

  @override
  String get generatingIconStep => 'Menghasilkan ikon';

  @override
  String get finalTouches => 'Sentuhan akhir';

  @override
  String get processing => 'Memproses...';

  @override
  String get features => 'Fitur';

  @override
  String get creatingYourApp => 'Membuat aplikasi Anda...';

  @override
  String get generatingIcon => 'Menghasilkan ikon...';

  @override
  String get whatShouldWeMake => 'Apa yang harus kita buat?';

  @override
  String get appName => 'App Name';

  @override
  String get description => 'Deskripsi';

  @override
  String get publicLabel => 'Publik';

  @override
  String get privateLabel => 'Pribadi';

  @override
  String get free => 'Gratis';

  @override
  String get perMonth => '/ Bulan';

  @override
  String get tailoredConversationSummaries => 'Ringkasan Percakapan yang Disesuaikan';

  @override
  String get customChatbotPersonality => 'Kepribadian Chatbot Kustom';

  @override
  String get makePublic => 'Jadikan Publik';

  @override
  String get anyoneCanDiscover => 'Siapa saja dapat menemukan aplikasi Anda';

  @override
  String get onlyYouCanUse => 'Hanya Anda yang dapat menggunakan aplikasi ini';

  @override
  String get paidApp => 'Aplikasi berbayar';

  @override
  String get usersPayToUse => 'Pengguna membayar untuk menggunakan aplikasi Anda';

  @override
  String get freeForEveryone => 'Gratis untuk semua orang';

  @override
  String get perMonthLabel => '/ bulan';

  @override
  String get creating => 'Membuat...';

  @override
  String get createApp => 'Buat Aplikasi';

  @override
  String get searchingForDevices => 'Mencari perangkat...';

  @override
  String devicesFoundNearby(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'PERANGKAT',
      one: 'PERANGKAT',
    );
    return '$count $_temp0 DITEMUKAN DI SEKITAR';
  }

  @override
  String get pairingSuccessful => 'PASANGAN BERHASIL';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Kesalahan menghubungkan ke Apple Watch: $error';
  }

  @override
  String get dontShowAgain => 'Jangan tampilkan lagi';

  @override
  String get iUnderstand => 'Saya Mengerti';

  @override
  String get enableBluetooth => 'Aktifkan Bluetooth';

  @override
  String get bluetoothNeeded =>
      'Omi membutuhkan Bluetooth untuk terhubung ke perangkat yang dapat dipakai Anda. Silakan aktifkan Bluetooth dan coba lagi.';

  @override
  String get contactSupport => 'Hubungi Dukungan?';

  @override
  String get connectLater => 'Hubungkan Nanti';

  @override
  String get grantPermissions => 'Berikan izin';

  @override
  String get backgroundActivity => 'Aktivitas latar belakang';

  @override
  String get backgroundActivityDesc => 'Biarkan Omi berjalan di latar belakang untuk stabilitas yang lebih baik';

  @override
  String get locationAccess => 'Akses lokasi';

  @override
  String get locationAccessDesc => 'Aktifkan lokasi latar belakang untuk pengalaman penuh';

  @override
  String get notifications => 'Notifikasi';

  @override
  String get notificationsDesc => 'Aktifkan notifikasi agar tetap mendapat informasi';

  @override
  String get locationServiceDisabled => 'Layanan Lokasi Dinonaktifkan';

  @override
  String get locationServiceDisabledDesc =>
      'Layanan Lokasi Dinonaktifkan. Silakan buka Pengaturan > Privasi & Keamanan > Layanan Lokasi dan aktifkan';

  @override
  String get backgroundLocationDenied => 'Akses Lokasi Latar Belakang Ditolak';

  @override
  String get backgroundLocationDeniedDesc =>
      'Silakan buka pengaturan perangkat dan atur izin lokasi ke \"Selalu Izinkan\"';

  @override
  String get lovingOmi => 'Menyukai Omi?';

  @override
  String get leaveReviewIos =>
      'Bantu kami menjangkau lebih banyak orang dengan meninggalkan ulasan di App Store. Masukan Anda sangat berarti bagi kami!';

  @override
  String get leaveReviewAndroid =>
      'Bantu kami menjangkau lebih banyak orang dengan meninggalkan ulasan di Google Play Store. Masukan Anda sangat berarti bagi kami!';

  @override
  String get rateOnAppStore => 'Beri Nilai di App Store';

  @override
  String get rateOnGooglePlay => 'Beri Nilai di Google Play';

  @override
  String get maybeLater => 'Mungkin Nanti';

  @override
  String get speechProfileIntro => 'Omi perlu mempelajari tujuan dan suara Anda. Anda dapat memodifikasinya nanti.';

  @override
  String get getStarted => 'Mulai';

  @override
  String get allDone => 'Semua selesai!';

  @override
  String get keepGoing => 'Terus lanjutkan, Anda melakukannya dengan baik';

  @override
  String get skipThisQuestion => 'Lewati pertanyaan ini';

  @override
  String get skipForNow => 'Lewati untuk sekarang';

  @override
  String get connectionError => 'Kesalahan Koneksi';

  @override
  String get connectionErrorDesc => 'Gagal terhubung ke server. Silakan periksa koneksi internet Anda dan coba lagi.';

  @override
  String get invalidRecordingMultipleSpeakers => 'Rekaman tidak valid terdeteksi';

  @override
  String get multipleSpeakersDesc =>
      'Sepertinya ada beberapa pembicara dalam rekaman. Pastikan Anda berada di lokasi yang sunyi dan coba lagi.';

  @override
  String get tooShortDesc => 'Tidak cukup ucapan terdeteksi. Silakan berbicara lebih banyak dan coba lagi.';

  @override
  String get invalidRecordingDesc => 'Pastikan Anda berbicara setidaknya selama 5 detik dan tidak lebih dari 90.';

  @override
  String get areYouThere => 'Apakah Anda di sana?';

  @override
  String get noSpeechDesc =>
      'Kami tidak dapat mendeteksi ucapan apa pun. Pastikan untuk berbicara setidaknya selama 10 detik dan tidak lebih dari 3 menit.';

  @override
  String get connectionLost => 'Koneksi Terputus';

  @override
  String get connectionLostDesc => 'Koneksi terputus. Silakan periksa koneksi internet Anda dan coba lagi.';

  @override
  String get tryAgain => 'Coba Lagi';

  @override
  String get connectOmiOmiGlass => 'Hubungkan Omi / OmiGlass';

  @override
  String get continueWithoutDevice => 'Lanjutkan Tanpa Perangkat';

  @override
  String get permissionsRequired => 'Izin Diperlukan';

  @override
  String get permissionsRequiredDesc =>
      'Aplikasi ini memerlukan izin Bluetooth dan Lokasi agar berfungsi dengan baik. Silakan aktifkan di pengaturan.';

  @override
  String get openSettings => 'Buka Pengaturan';

  @override
  String get wantDifferentName => 'Ingin menggunakan nama lain?';

  @override
  String get whatsYourName => 'Siapa nama Anda?';

  @override
  String get speakTranscribeSummarize => 'Bicara. Transkripsi. Ringkas.';

  @override
  String get signInWithApple => 'Masuk dengan Apple';

  @override
  String get signInWithGoogle => 'Masuk dengan Google';

  @override
  String get byContinuingAgree => 'Dengan melanjutkan, Anda menyetujui ';

  @override
  String get termsOfUse => 'Ketentuan Penggunaan';

  @override
  String get omiYourAiCompanion => 'Omi – Pendamping AI Anda';

  @override
  String get captureEveryMoment =>
      'Tangkap setiap momen. Dapatkan ringkasan\nbertenaga AI. Jangan pernah mencatat lagi.';

  @override
  String get appleWatchSetup => 'Pengaturan Apple Watch';

  @override
  String get permissionRequestedExclaim => 'Izin Diminta!';

  @override
  String get microphonePermission => 'Izin Mikrofon';

  @override
  String get permissionGrantedNow =>
      'Izin diberikan! Sekarang:\n\nBuka aplikasi Omi di jam tangan Anda dan ketuk \"Lanjutkan\" di bawah ini';

  @override
  String get needMicrophonePermission =>
      'Kami memerlukan izin mikrofon.\n\n1. Ketuk \"Berikan Izin\"\n2. Izinkan di iPhone Anda\n3. Aplikasi jam tangan akan tertutup\n4. Buka kembali dan ketuk \"Lanjutkan\"';

  @override
  String get grantPermissionButton => 'Berikan Izin';

  @override
  String get needHelp => 'Butuh Bantuan?';

  @override
  String get troubleshootingSteps =>
      'Pemecahan Masalah:\n\n1. Pastikan Omi terinstal di jam tangan Anda\n2. Buka aplikasi Omi di jam tangan Anda\n3. Cari popup izin\n4. Ketuk \"Izinkan\" saat diminta\n5. Aplikasi di jam tangan Anda akan tertutup - buka kembali\n6. Kembali dan ketuk \"Lanjutkan\" di iPhone Anda';

  @override
  String get recordingStartedSuccessfully => 'Rekaman berhasil dimulai!';

  @override
  String get permissionNotGrantedYet =>
      'Izin belum diberikan. Pastikan Anda telah mengizinkan akses mikrofon dan membuka kembali aplikasi di jam tangan Anda.';

  @override
  String errorRequestingPermission(String error) {
    return 'Kesalahan meminta izin: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'Kesalahan memulai rekaman: $error';
  }

  @override
  String get selectPrimaryLanguage => 'Pilih bahasa utama Anda';

  @override
  String get languageBenefits =>
      'Atur bahasa Anda untuk transkripsi yang lebih tajam dan pengalaman yang dipersonalisasi';

  @override
  String get whatsYourPrimaryLanguage => 'Apa bahasa utama Anda?';

  @override
  String get selectYourLanguage => 'Pilih bahasa Anda';

  @override
  String get personalGrowthJourney =>
      'Perjalanan pertumbuhan pribadi Anda dengan AI yang mendengarkan setiap kata Anda.';

  @override
  String get actionItemsTitle => 'Daftar Tugas';

  @override
  String get actionItemsDescription => 'Ketuk untuk edit • Tekan lama untuk pilih • Geser untuk aksi';

  @override
  String get tabToDo => 'Harus Dilakukan';

  @override
  String get tabDone => 'Selesai';

  @override
  String get tabOld => 'Lama';

  @override
  String get emptyTodoMessage => '🎉 Semua selesai!\nTidak ada item tindakan tertunda';

  @override
  String get emptyDoneMessage => 'Belum ada item yang diselesaikan';

  @override
  String get emptyOldMessage => '✅ Tidak ada tugas lama';

  @override
  String get noItems => 'Tidak ada item';

  @override
  String get actionItemMarkedIncomplete => 'Item tindakan ditandai sebagai belum selesai';

  @override
  String get actionItemCompleted => 'Item tindakan selesai';

  @override
  String get deleteActionItemTitle => 'Hapus item tindakan';

  @override
  String get deleteActionItemMessage => 'Apakah Anda yakin ingin menghapus item tindakan ini?';

  @override
  String get deleteSelectedItemsTitle => 'Hapus Item yang Dipilih';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Apakah Anda yakin ingin menghapus $count item tindakan$s yang dipilih?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'Item tindakan \"$description\" dihapus';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count item tindakan$s dihapus';
  }

  @override
  String get failedToDeleteItem => 'Gagal menghapus item tindakan';

  @override
  String get failedToDeleteItems => 'Gagal menghapus item';

  @override
  String get failedToDeleteSomeItems => 'Gagal menghapus beberapa item';

  @override
  String get welcomeActionItemsTitle => 'Siap untuk Item Tindakan';

  @override
  String get welcomeActionItemsDescription =>
      'AI Anda akan secara otomatis mengekstrak tugas dan hal-hal yang harus dilakukan dari percakapan Anda. Mereka akan muncul di sini saat dibuat.';

  @override
  String get autoExtractionFeature => 'Secara otomatis diekstrak dari percakapan';

  @override
  String get editSwipeFeature => 'Ketuk untuk edit, geser untuk selesaikan atau hapus';

  @override
  String itemsSelected(int count) {
    return '$count dipilih';
  }

  @override
  String get selectAll => 'Pilih semua';

  @override
  String get deleteSelected => 'Hapus yang dipilih';

  @override
  String get searchMemories => 'Cari kenangan...';

  @override
  String get memoryDeleted => 'Memori Dihapus.';

  @override
  String get undo => 'Batalkan';

  @override
  String get noMemoriesYet => '🧠 Belum ada kenangan';

  @override
  String get noAutoMemories => 'Belum ada memori yang diekstrak otomatis';

  @override
  String get noManualMemories => 'Belum ada memori manual';

  @override
  String get noMemoriesInCategories => 'Tidak ada memori dalam kategori ini';

  @override
  String get noMemoriesFound => '🔍 Tidak ditemukan kenangan';

  @override
  String get addFirstMemory => 'Tambahkan memori pertama Anda';

  @override
  String get clearMemoryTitle => 'Hapus Memori Omi';

  @override
  String get clearMemoryMessage => 'Apakah Anda yakin ingin menghapus memori Omi? Tindakan ini tidak dapat dibatalkan.';

  @override
  String get clearMemoryButton => 'Hapus Memori';

  @override
  String get memoryClearedSuccess => 'Memori Omi tentang Anda telah dihapus';

  @override
  String get noMemoriesToDelete => 'Tidak ada memori untuk dihapus';

  @override
  String get createMemoryTooltip => 'Buat memori baru';

  @override
  String get createActionItemTooltip => 'Buat item tindakan baru';

  @override
  String get memoryManagement => 'Manajemen Memori';

  @override
  String get filterMemories => 'Filter Memori';

  @override
  String totalMemoriesCount(int count) {
    return 'Anda memiliki $count total memori';
  }

  @override
  String get publicMemories => 'Memori publik';

  @override
  String get privateMemories => 'Memori pribadi';

  @override
  String get makeAllPrivate => 'Jadikan Semua Memori Pribadi';

  @override
  String get makeAllPublic => 'Jadikan Semua Memori Publik';

  @override
  String get deleteAllMemories => 'Hapus Semua Memori';

  @override
  String get allMemoriesPrivateResult => 'Semua memori sekarang pribadi';

  @override
  String get allMemoriesPublicResult => 'Semua memori sekarang publik';

  @override
  String get newMemory => '✨ Memori Baru';

  @override
  String get editMemory => '✏️ Edit Memori';

  @override
  String get memoryContentHint => 'Saya suka makan es krim...';

  @override
  String get failedToSaveMemory => 'Gagal menyimpan. Silakan periksa koneksi Anda.';

  @override
  String get saveMemory => 'Simpan Memori';

  @override
  String get retry => 'Retry';

  @override
  String get createActionItem => 'Buat item tindakan';

  @override
  String get editActionItem => 'Edit item tindakan';

  @override
  String get actionItemDescriptionHint => 'Apa yang perlu dilakukan?';

  @override
  String get actionItemDescriptionEmpty => 'Deskripsi item tindakan tidak boleh kosong.';

  @override
  String get actionItemUpdated => 'Item tindakan diperbarui';

  @override
  String get failedToUpdateActionItem => 'Gagal memperbarui item tindakan';

  @override
  String get actionItemCreated => 'Item tindakan dibuat';

  @override
  String get failedToCreateActionItem => 'Gagal membuat item tindakan';

  @override
  String get dueDate => 'Tanggal jatuh tempo';

  @override
  String get time => 'Waktu';

  @override
  String get addDueDate => 'Tambahkan tenggat waktu';

  @override
  String get pressDoneToSave => 'Tekan selesai untuk menyimpan';

  @override
  String get pressDoneToCreate => 'Tekan selesai untuk membuat';

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
  String get actionItemDeleted => 'Item tindakan dihapus';

  @override
  String get failedToDeleteActionItem => 'Gagal menghapus item tindakan';

  @override
  String get deleteActionItemConfirmTitle => 'Hapus Item Tindakan';

  @override
  String get deleteActionItemConfirmMessage => 'Apakah Anda yakin ingin menghapus item tindakan ini?';

  @override
  String get appLanguage => 'Bahasa Aplikasi';

  @override
  String get appInterfaceSectionTitle => 'ANTARMUKA APLIKASI';

  @override
  String get speechTranscriptionSectionTitle => 'UCAPAN & TRANSKRIPSI';

  @override
  String get languageSettingsHelperText =>
      'Bahasa Aplikasi mengubah menu dan tombol. Bahasa Ucapan mempengaruhi cara rekaman Anda ditranskripsi.';

  @override
  String get translationNotice => 'Pemberitahuan Terjemahan';

  @override
  String get translationNoticeMessage =>
      'Omi menerjemahkan percakapan ke bahasa utama Anda. Perbarui kapan saja di Pengaturan → Profil.';

  @override
  String get pleaseCheckInternetConnection => 'Harap periksa koneksi internet Anda dan coba lagi';

  @override
  String get pleaseSelectReason => 'Harap pilih alasan';

  @override
  String get tellUsMoreWhatWentWrong => 'Beri tahu kami lebih lanjut tentang apa yang salah...';

  @override
  String get selectText => 'Pilih Teks';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Maksimal $count tujuan diizinkan';
  }

  @override
  String get conversationCannotBeMerged => 'Percakapan ini tidak dapat digabung (terkunci atau sudah digabungkan)';

  @override
  String get pleaseEnterFolderName => 'Harap masukkan nama folder';

  @override
  String get failedToCreateFolder => 'Gagal membuat folder';

  @override
  String get failedToUpdateFolder => 'Gagal memperbarui folder';

  @override
  String get folderName => 'Nama folder';

  @override
  String get descriptionOptional => 'Description (optional)';

  @override
  String get failedToDeleteFolder => 'Gagal menghapus folder';

  @override
  String get editFolder => 'Edit folder';

  @override
  String get deleteFolder => 'Hapus folder';

  @override
  String get transcriptCopiedToClipboard => 'Transkrip disalin ke papan klip';

  @override
  String get summaryCopiedToClipboard => 'Ringkasan disalin ke clipboard';

  @override
  String get conversationUrlCouldNotBeShared => 'URL percakapan tidak dapat dibagikan.';

  @override
  String get urlCopiedToClipboard => 'URL disalin ke papan klip';

  @override
  String get exportTranscript => 'Ekspor transkrip';

  @override
  String get exportSummary => 'Ekspor ringkasan';

  @override
  String get exportButton => 'Ekspor';

  @override
  String get actionItemsCopiedToClipboard => 'Item tindakan disalin ke papan klip';

  @override
  String get summarize => 'Ringkas';

  @override
  String get generateSummary => 'Buat Ringkasan';

  @override
  String get conversationNotFoundOrDeleted => 'Percakapan tidak ditemukan atau telah dihapus';

  @override
  String get deleteMemory => 'Hapus Memori';

  @override
  String get thisActionCannotBeUndone => 'Tindakan ini tidak dapat dibatalkan.';

  @override
  String memoriesCount(int count) {
    return '$count memori';
  }

  @override
  String get noMemoriesInCategory => 'Belum ada memori dalam kategori ini';

  @override
  String get addYourFirstMemory => 'Tambahkan kenangan pertama Anda';

  @override
  String get firmwareDisconnectUsb => 'Putuskan USB';

  @override
  String get firmwareUsbWarning => 'Koneksi USB selama pembaruan dapat merusak perangkat Anda.';

  @override
  String get firmwareBatteryAbove15 => 'Baterai di atas 15%';

  @override
  String get firmwareEnsureBattery => 'Pastikan perangkat Anda memiliki baterai 15%.';

  @override
  String get firmwareStableConnection => 'Koneksi stabil';

  @override
  String get firmwareConnectWifi => 'Hubungkan ke WiFi atau seluler.';

  @override
  String failedToStartUpdate(String error) {
    return 'Gagal memulai pembaruan: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'Sebelum memperbarui, pastikan:';

  @override
  String get confirmed => 'Dikonfirmasi!';

  @override
  String get release => 'Lepaskan';

  @override
  String get slideToUpdate => 'Geser untuk memperbarui';

  @override
  String copiedToClipboard(String title) {
    return '$title disalin ke papan klip';
  }

  @override
  String get batteryLevel => 'Level Baterai';

  @override
  String get productUpdate => 'Pembaruan Produk';

  @override
  String get offline => 'Offline';

  @override
  String get available => 'Tersedia';

  @override
  String get unpairDeviceDialogTitle => 'Putuskan Pemasangan Perangkat';

  @override
  String get unpairDeviceDialogMessage =>
      'Ini akan memutuskan pemasangan perangkat agar dapat terhubung ke ponsel lain. Anda perlu membuka Pengaturan > Bluetooth dan melupakan perangkat untuk menyelesaikan prosesnya.';

  @override
  String get unpair => 'Putuskan Pemasangan';

  @override
  String get unpairAndForgetDevice => 'Putuskan Pemasangan dan Lupakan Perangkat';

  @override
  String get unknownDevice => 'Unknown';

  @override
  String get unknown => 'Tidak Dikenal';

  @override
  String get productName => 'Nama Produk';

  @override
  String get serialNumber => 'Nomor Seri';

  @override
  String get connected => 'Terhubung';

  @override
  String get privacyPolicyTitle => 'Kebijakan Privasi';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label disalin';
  }

  @override
  String get noApiKeysYet => 'Belum ada kunci API. Buat satu untuk mengintegrasikan dengan aplikasi Anda.';

  @override
  String get createKeyToGetStarted => 'Buat kunci untuk memulai';

  @override
  String get persona => 'Persona';

  @override
  String get configureYourAiPersona => 'Konfigurasikan persona AI Anda';

  @override
  String get configureSttProvider => 'Konfigurasikan penyedia STT';

  @override
  String get setWhenConversationsAutoEnd => 'Atur kapan percakapan berakhir otomatis';

  @override
  String get importDataFromOtherSources => 'Impor data dari sumber lain';

  @override
  String get debugAndDiagnostics => 'Debug & Diagnostik';

  @override
  String get autoDeletesAfter3Days => 'Otomatis dihapus setelah 3 hari';

  @override
  String get helpsDiagnoseIssues => 'Membantu mendiagnosis masalah';

  @override
  String get exportStartedMessage => 'Ekspor dimulai. Ini mungkin memakan waktu beberapa detik...';

  @override
  String get exportConversationsToJson => 'Ekspor percakapan ke file JSON';

  @override
  String get knowledgeGraphDeletedSuccess => 'Graf pengetahuan berhasil dihapus';

  @override
  String failedToDeleteGraph(String error) {
    return 'Gagal menghapus graf: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'Hapus semua node dan koneksi';

  @override
  String get addToClaudeDesktopConfig => 'Tambahkan ke claude_desktop_config.json';

  @override
  String get connectAiAssistantsToData => 'Hubungkan asisten AI ke data Anda';

  @override
  String get useYourMcpApiKey => 'Gunakan kunci API MCP Anda';

  @override
  String get realTimeTranscript => 'Transkrip Real-time';

  @override
  String get experimental => 'Eksperimental';

  @override
  String get transcriptionDiagnostics => 'Diagnostik Transkripsi';

  @override
  String get detailedDiagnosticMessages => 'Pesan diagnostik terperinci';

  @override
  String get autoCreateSpeakers => 'Buat Pembicara Otomatis';

  @override
  String get autoCreateWhenNameDetected => 'Buat otomatis saat nama terdeteksi';

  @override
  String get followUpQuestions => 'Pertanyaan Lanjutan';

  @override
  String get suggestQuestionsAfterConversations => 'Sarankan pertanyaan setelah percakapan';

  @override
  String get goalTracker => 'Pelacak Tujuan';

  @override
  String get trackPersonalGoalsOnHomepage => 'Lacak tujuan pribadi Anda di beranda';

  @override
  String get dailyReflection => 'Refleksi Harian';

  @override
  String get get9PmReminderToReflect => 'Dapatkan pengingat jam 9 malam untuk merenungkan hari Anda';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'Deskripsi item tindakan tidak boleh kosong';

  @override
  String get saved => 'Disimpan';

  @override
  String get overdue => 'Terlambat';

  @override
  String get failedToUpdateDueDate => 'Gagal memperbarui tanggal jatuh tempo';

  @override
  String get markIncomplete => 'Tandai belum selesai';

  @override
  String get editDueDate => 'Edit tanggal jatuh tempo';

  @override
  String get setDueDate => 'Tetapkan tanggal jatuh tempo';

  @override
  String get clearDueDate => 'Hapus tanggal jatuh tempo';

  @override
  String get failedToClearDueDate => 'Gagal menghapus tanggal jatuh tempo';

  @override
  String get mondayAbbr => 'Sen';

  @override
  String get tuesdayAbbr => 'Sel';

  @override
  String get wednesdayAbbr => 'Rab';

  @override
  String get thursdayAbbr => 'Kam';

  @override
  String get fridayAbbr => 'Jum';

  @override
  String get saturdayAbbr => 'Sab';

  @override
  String get sundayAbbr => 'Min';

  @override
  String get howDoesItWork => 'Bagaimana cara kerjanya?';

  @override
  String get sdCardSyncDescription => 'Sinkronisasi Kartu SD akan mengimpor kenangan Anda dari Kartu SD ke aplikasi';

  @override
  String get checksForAudioFiles => 'Memeriksa file audio di Kartu SD';

  @override
  String get omiSyncsAudioFiles => 'Omi kemudian menyinkronkan file audio dengan server';

  @override
  String get serverProcessesAudio => 'Server memproses file audio dan membuat kenangan';

  @override
  String get youreAllSet => 'Anda siap!';

  @override
  String get welcomeToOmiDescription =>
      'Selamat datang di Omi! Pendamping AI Anda siap membantu Anda dengan percakapan, tugas, dan banyak lagi.';

  @override
  String get startUsingOmi => 'Mulai Menggunakan Omi';

  @override
  String get back => 'Kembali';

  @override
  String get keyboardShortcuts => 'Pintasan Keyboard';

  @override
  String get toggleControlBar => 'Alihkan Bilah Kontrol';

  @override
  String get pressKeys => 'Tekan tombol...';

  @override
  String get cmdRequired => '⌘ diperlukan';

  @override
  String get invalidKey => 'Tombol tidak valid';

  @override
  String get space => 'Spasi';

  @override
  String get search => 'Cari';

  @override
  String get searchPlaceholder => 'Cari...';

  @override
  String get untitledConversation => 'Percakapan Tanpa Judul';

  @override
  String countRemaining(String count) {
    return '$count tersisa';
  }

  @override
  String get addGoal => 'Tambah Sasaran';

  @override
  String get editGoal => 'Edit Sasaran';

  @override
  String get icon => 'Ikon';

  @override
  String get goalTitle => 'Judul sasaran';

  @override
  String get current => 'Saat ini';

  @override
  String get target => 'Target';

  @override
  String get saveGoal => 'Simpan';

  @override
  String get goals => 'Sasaran';

  @override
  String get tapToAddGoal => 'Ketuk untuk menambahkan sasaran';

  @override
  String welcomeBack(String name) {
    return 'Selamat datang kembali, $name';
  }

  @override
  String get yourConversations => 'Percakapan Anda';

  @override
  String get reviewAndManageConversations => 'Tinjau dan kelola percakapan yang telah direkam';

  @override
  String get startCapturingConversations =>
      'Mulai merekam percakapan dengan perangkat Omi Anda untuk melihatnya di sini.';

  @override
  String get useMobileAppToCapture => 'Gunakan aplikasi seluler Anda untuk merekam audio';

  @override
  String get conversationsProcessedAutomatically => 'Percakapan diproses secara otomatis';

  @override
  String get getInsightsInstantly => 'Dapatkan wawasan dan ringkasan secara instan';

  @override
  String get showAll => 'Tampilkan semua →';

  @override
  String get noTasksForToday =>
      'Tidak ada tugas untuk hari ini.\\nTanyakan Omi untuk lebih banyak tugas atau buat secara manual.';

  @override
  String get dailyScore => 'SKOR HARIAN';

  @override
  String get dailyScoreDescription => 'Skor untuk membantu Anda\nlebih fokus pada eksekusi.';

  @override
  String get searchResults => 'Hasil pencarian';

  @override
  String get actionItems => 'Item tindakan';

  @override
  String get tasksToday => 'Hari ini';

  @override
  String get tasksTomorrow => 'Besok';

  @override
  String get tasksNoDeadline => 'Tanpa tenggat';

  @override
  String get tasksLater => 'Nanti';

  @override
  String get loadingTasks => 'Memuat tugas...';

  @override
  String get tasks => 'Tugas';

  @override
  String get swipeTasksToIndent => 'Geser tugas untuk indentasi, seret antar kategori';

  @override
  String get create => 'Buat';

  @override
  String get noTasksYet => 'Belum ada tugas';

  @override
  String get tasksFromConversationsWillAppear =>
      'Tugas dari percakapan Anda akan muncul di sini.\nKlik Buat untuk menambahkan satu secara manual.';

  @override
  String get monthJan => 'Jan';

  @override
  String get monthFeb => 'Feb';

  @override
  String get monthMar => 'Mar';

  @override
  String get monthApr => 'Apr';

  @override
  String get monthMay => 'Mei';

  @override
  String get monthJun => 'Jun';

  @override
  String get monthJul => 'Jul';

  @override
  String get monthAug => 'Agu';

  @override
  String get monthSep => 'Sep';

  @override
  String get monthOct => 'Okt';

  @override
  String get monthNov => 'Nov';

  @override
  String get monthDec => 'Des';

  @override
  String get timePM => 'PM';

  @override
  String get timeAM => 'AM';

  @override
  String get actionItemUpdatedSuccessfully => 'Item tindakan berhasil diperbarui';

  @override
  String get actionItemCreatedSuccessfully => 'Item tindakan berhasil dibuat';

  @override
  String get actionItemDeletedSuccessfully => 'Item tindakan berhasil dihapus';

  @override
  String get deleteActionItem => 'Hapus item tindakan';

  @override
  String get deleteActionItemConfirmation =>
      'Apakah Anda yakin ingin menghapus item tindakan ini? Tindakan ini tidak dapat dibatalkan.';

  @override
  String get enterActionItemDescription => 'Masukkan deskripsi item tindakan...';

  @override
  String get markAsCompleted => 'Tandai sebagai selesai';

  @override
  String get setDueDateAndTime => 'Tetapkan tanggal dan waktu jatuh tempo';

  @override
  String get reloadingApps => 'Memuat ulang aplikasi...';

  @override
  String get loadingApps => 'Memuat aplikasi...';

  @override
  String get browseInstallCreateApps => 'Jelajahi, instal, dan buat aplikasi';

  @override
  String get all => 'All';

  @override
  String get open => 'Buka';

  @override
  String get install => 'Instal';

  @override
  String get noAppsAvailable => 'Tidak ada aplikasi tersedia';

  @override
  String get unableToLoadApps => 'Tidak dapat memuat aplikasi';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'Coba sesuaikan kata kunci pencarian atau filter Anda';

  @override
  String get checkBackLaterForNewApps => 'Periksa kembali nanti untuk aplikasi baru';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'Silakan periksa koneksi internet Anda dan coba lagi';

  @override
  String get createNewApp => 'Buat Aplikasi Baru';

  @override
  String get buildSubmitCustomOmiApp => 'Bangun dan kirim aplikasi Omi kustom Anda';

  @override
  String get submittingYourApp => 'Mengirimkan aplikasi Anda...';

  @override
  String get preparingFormForYou => 'Menyiapkan formulir untuk Anda...';

  @override
  String get appDetails => 'Detail Aplikasi';

  @override
  String get paymentDetails => 'Detail Pembayaran';

  @override
  String get previewAndScreenshots => 'Pratinjau dan Tangkapan Layar';

  @override
  String get appCapabilities => 'Kemampuan Aplikasi';

  @override
  String get aiPrompts => 'Petunjuk AI';

  @override
  String get chatPrompt => 'Petunjuk Chat';

  @override
  String get chatPromptPlaceholder =>
      'Anda adalah aplikasi yang luar biasa, tugas Anda adalah merespons pertanyaan pengguna dan membuat mereka merasa baik...';

  @override
  String get conversationPrompt => 'Prompt Percakapan';

  @override
  String get conversationPromptPlaceholder =>
      'Anda adalah aplikasi yang luar biasa, Anda akan diberikan transkrip dan ringkasan percakapan...';

  @override
  String get notificationScopes => 'Cakupan Notifikasi';

  @override
  String get appPrivacyAndTerms => 'Privasi & Ketentuan Aplikasi';

  @override
  String get makeMyAppPublic => 'Buat aplikasi saya publik';

  @override
  String get submitAppTermsAgreement =>
      'Dengan mengirimkan aplikasi ini, saya menyetujui Ketentuan Layanan dan Kebijakan Privasi Omi AI';

  @override
  String get submitApp => 'Kirim Aplikasi';

  @override
  String get needHelpGettingStarted => 'Butuh bantuan untuk memulai?';

  @override
  String get clickHereForAppBuildingGuides => 'Klik di sini untuk panduan pembuatan aplikasi dan dokumentasi';

  @override
  String get submitAppQuestion => 'Kirim Aplikasi?';

  @override
  String get submitAppPublicDescription =>
      'Aplikasi Anda akan ditinjau dan dipublikasikan. Anda dapat mulai menggunakannya segera, bahkan selama peninjauan!';

  @override
  String get submitAppPrivateDescription =>
      'Aplikasi Anda akan ditinjau dan tersedia untuk Anda secara pribadi. Anda dapat mulai menggunakannya segera, bahkan selama peninjauan!';

  @override
  String get startEarning => 'Mulai Menghasilkan! 💰';

  @override
  String get connectStripeOrPayPal => 'Hubungkan Stripe atau PayPal untuk menerima pembayaran untuk aplikasi Anda.';

  @override
  String get connectNow => 'Hubungkan Sekarang';

  @override
  String get installsCount => 'Instalasi';

  @override
  String get uninstallApp => 'Copot Aplikasi';

  @override
  String get subscribe => 'Berlangganan';

  @override
  String get dataAccessNotice => 'Pemberitahuan Akses Data';

  @override
  String get dataAccessWarning =>
      'Aplikasi ini akan mengakses data Anda. Omi AI tidak bertanggung jawab atas bagaimana data Anda digunakan, dimodifikasi, atau dihapus oleh aplikasi ini';

  @override
  String get installApp => 'Instal Aplikasi';

  @override
  String get betaTesterNotice =>
      'Anda adalah penguji beta untuk aplikasi ini. Ini belum publik. Ini akan menjadi publik setelah disetujui.';

  @override
  String get appUnderReviewOwner =>
      'Aplikasi Anda sedang dalam peninjauan dan hanya terlihat oleh Anda. Ini akan menjadi publik setelah disetujui.';

  @override
  String get appRejectedNotice =>
      'Aplikasi Anda telah ditolak. Harap perbarui detail aplikasi dan kirim ulang untuk ditinjau.';

  @override
  String get setupSteps => 'Langkah Pengaturan';

  @override
  String get setupInstructions => 'Instruksi Pengaturan';

  @override
  String get integrationInstructions => 'Instruksi Integrasi';

  @override
  String get preview => 'Pratinjau';

  @override
  String get aboutTheApp => 'Tentang Aplikasi';

  @override
  String get aboutThePersona => 'Tentang Persona';

  @override
  String get chatPersonality => 'Kepribadian Chat';

  @override
  String get ratingsAndReviews => 'Peringkat & Ulasan';

  @override
  String get noRatings => 'tidak ada peringkat';

  @override
  String ratingsCount(String count) {
    return '$count+ peringkat';
  }

  @override
  String get errorActivatingApp => 'Kesalahan mengaktifkan aplikasi';

  @override
  String get integrationSetupRequired => 'Jika ini adalah aplikasi integrasi, pastikan pengaturan telah selesai.';

  @override
  String get installed => 'Terinstal';

  @override
  String get appIdLabel => 'ID Aplikasi';

  @override
  String get appNameLabel => 'Nama Aplikasi';

  @override
  String get appNamePlaceholder => 'Aplikasi Hebat Saya';

  @override
  String get pleaseEnterAppName => 'Harap masukkan nama aplikasi';

  @override
  String get categoryLabel => 'Kategori';

  @override
  String get selectCategory => 'Pilih Kategori';

  @override
  String get descriptionLabel => 'Deskripsi';

  @override
  String get appDescriptionPlaceholder =>
      'Aplikasi Hebat Saya adalah aplikasi luar biasa yang melakukan hal-hal menakjubkan. Ini adalah aplikasi terbaik!';

  @override
  String get pleaseProvideValidDescription => 'Harap berikan deskripsi yang valid';

  @override
  String get appPricingLabel => 'Harga Aplikasi';

  @override
  String get noneSelected => 'Tidak Ada yang Dipilih';

  @override
  String get appIdCopiedToClipboard => 'ID Aplikasi disalin ke clipboard';

  @override
  String get appCategoryModalTitle => 'Kategori Aplikasi';

  @override
  String get pricingFree => 'Gratis';

  @override
  String get pricingPaid => 'Berbayar';

  @override
  String get loadingCapabilities => 'Memuat kemampuan...';

  @override
  String get filterInstalled => 'Terpasang';

  @override
  String get filterMyApps => 'Aplikasi Saya';

  @override
  String get clearSelection => 'Hapus pilihan';

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
  String get filterCapabilities => 'Kemampuan';

  @override
  String get noNotificationScopesAvailable => 'Tidak ada cakupan notifikasi yang tersedia';

  @override
  String get popularApps => 'Aplikasi Populer';

  @override
  String get pleaseProvidePrompt => 'Harap berikan prompt';

  @override
  String chatWithAppName(String appName) {
    return 'Obrolan dengan $appName';
  }

  @override
  String get defaultAiAssistant => 'Asisten AI Default';

  @override
  String get readyToChat => '✨ Siap mengobrol!';

  @override
  String get connectionNeeded => '🌐 Koneksi diperlukan';

  @override
  String get startConversation => 'Mulai percakapan dan biarkan keajaiban dimulai';

  @override
  String get checkInternetConnection => 'Silakan periksa koneksi internet Anda';

  @override
  String get wasThisHelpful => 'Apakah ini membantu?';

  @override
  String get thankYouForFeedback => 'Terima kasih atas tanggapan Anda!';

  @override
  String get maxFilesUploadError => 'Anda hanya dapat mengunggah 4 file sekaligus';

  @override
  String get attachedFiles => '📎 File Terlampir';

  @override
  String get takePhoto => 'Ambil Foto';

  @override
  String get captureWithCamera => 'Tangkap dengan kamera';

  @override
  String get selectImages => 'Pilih Gambar';

  @override
  String get chooseFromGallery => 'Pilih dari galeri';

  @override
  String get selectFile => 'Pilih File';

  @override
  String get chooseAnyFileType => 'Pilih jenis file apa saja';

  @override
  String get cannotReportOwnMessages => 'Anda tidak dapat melaporkan pesan Anda sendiri';

  @override
  String get messageReportedSuccessfully => '✅ Pesan berhasil dilaporkan';

  @override
  String get confirmReportMessage => 'Apakah Anda yakin ingin melaporkan pesan ini?';

  @override
  String get selectChatAssistant => 'Pilih Asisten Obrolan';

  @override
  String get enableMoreApps => 'Aktifkan Lebih Banyak Aplikasi';

  @override
  String get chatCleared => 'Obrolan dibersihkan';

  @override
  String get clearChatTitle => 'Hapus Obrolan?';

  @override
  String get confirmClearChat => 'Apakah Anda yakin ingin menghapus obrolan? Tindakan ini tidak dapat dibatalkan.';

  @override
  String get copy => 'Salin';

  @override
  String get share => 'Bagikan';

  @override
  String get report => 'Laporkan';

  @override
  String get microphonePermissionRequired => 'Izin mikrofon diperlukan untuk perekaman suara.';

  @override
  String get microphonePermissionDenied =>
      'Izin mikrofon ditolak. Harap berikan izin di Preferensi Sistem > Privasi & Keamanan > Mikrofon.';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'Gagal memeriksa izin mikrofon: $error';
  }

  @override
  String get failedToTranscribeAudio => 'Gagal menyalin audio';

  @override
  String get transcribing => 'Menyalin...';

  @override
  String get transcriptionFailed => 'Transkripsi gagal';

  @override
  String get discardedConversation => 'Percakapan dibuang';

  @override
  String get at => 'pada';

  @override
  String get from => 'dari';

  @override
  String get copied => 'Disalin!';

  @override
  String get copyLink => 'Salin tautan';

  @override
  String get hideTranscript => 'Sembunyikan Transkrip';

  @override
  String get viewTranscript => 'Lihat Transkrip';

  @override
  String get conversationDetails => 'Detail Percakapan';

  @override
  String get transcript => 'Transkrip';

  @override
  String segmentsCount(int count) {
    return '$count segmen';
  }

  @override
  String get noTranscriptAvailable => 'Tidak Ada Transkrip Tersedia';

  @override
  String get noTranscriptMessage => 'Percakapan ini tidak memiliki transkrip.';

  @override
  String get conversationUrlCouldNotBeGenerated => 'URL percakapan tidak dapat dibuat.';

  @override
  String get failedToGenerateConversationLink => 'Gagal membuat tautan percakapan';

  @override
  String get failedToGenerateShareLink => 'Gagal membuat tautan berbagi';

  @override
  String get reloadingConversations => 'Memuat ulang percakapan...';

  @override
  String get user => 'Pengguna';

  @override
  String get starred => 'Berbintang';

  @override
  String get date => 'Tanggal';

  @override
  String get noResultsFound => 'Tidak ada hasil yang ditemukan';

  @override
  String get tryAdjustingSearchTerms => 'Coba sesuaikan istilah pencarian Anda';

  @override
  String get starConversationsToFindQuickly => 'Beri bintang pada percakapan untuk menemukannya dengan cepat di sini';

  @override
  String noConversationsOnDate(String date) {
    return 'Tidak ada percakapan pada $date';
  }

  @override
  String get trySelectingDifferentDate => 'Coba pilih tanggal yang berbeda';

  @override
  String get conversations => 'Percakapan';

  @override
  String get chat => 'Obrolan';

  @override
  String get actions => 'Tindakan';

  @override
  String get syncAvailable => 'Sinkronisasi Tersedia';

  @override
  String get referAFriend => 'Referensikan Teman';

  @override
  String get help => 'Bantuan';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'Tingkatkan ke Pro';

  @override
  String get getOmiDevice => 'Dapatkan Perangkat Omi';

  @override
  String get wearableAiCompanion => 'Pendamping AI yang dapat dikenakan';

  @override
  String get loadingMemories => 'Memuat kenangan...';

  @override
  String get allMemories => 'Semua kenangan';

  @override
  String get aboutYou => 'Tentang Anda';

  @override
  String get manual => 'Manual';

  @override
  String get loadingYourMemories => 'Memuat kenangan Anda...';

  @override
  String get createYourFirstMemory => 'Buat kenangan pertama Anda untuk memulai';

  @override
  String get tryAdjustingFilter => 'Coba sesuaikan pencarian atau filter Anda';

  @override
  String get whatWouldYouLikeToRemember => 'Apa yang ingin Anda ingat?';

  @override
  String get category => 'Kategori';

  @override
  String get public => 'Publik';

  @override
  String get failedToSaveCheckConnection => 'Gagal menyimpan. Silakan periksa koneksi Anda.';

  @override
  String get createMemory => 'Buat Memori';

  @override
  String get deleteMemoryConfirmation =>
      'Apakah Anda yakin ingin menghapus memori ini? Tindakan ini tidak dapat dibatalkan.';

  @override
  String get makePrivate => 'Jadikan Privat';

  @override
  String get organizeAndControlMemories => 'Atur dan kontrol memori Anda';

  @override
  String get total => 'Total';

  @override
  String get makeAllMemoriesPrivate => 'Jadikan Semua Memori Privat';

  @override
  String get setAllMemoriesToPrivate => 'Atur semua memori ke visibilitas privat';

  @override
  String get makeAllMemoriesPublic => 'Jadikan Semua Memori Publik';

  @override
  String get setAllMemoriesToPublic => 'Atur semua memori ke visibilitas publik';

  @override
  String get permanentlyRemoveAllMemories => 'Hapus permanen semua memori dari Omi';

  @override
  String get allMemoriesAreNowPrivate => 'Semua memori sekarang privat';

  @override
  String get allMemoriesAreNowPublic => 'Semua memori sekarang publik';

  @override
  String get clearOmisMemory => 'Hapus Memori Omi';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Apakah Anda yakin ingin menghapus memori Omi? Tindakan ini tidak dapat dibatalkan dan akan menghapus permanen semua $count memori.';
  }

  @override
  String get omisMemoryCleared => 'Memori Omi tentang Anda telah dihapus';

  @override
  String get welcomeToOmi => 'Selamat datang di Omi';

  @override
  String get continueWithApple => 'Lanjutkan dengan Apple';

  @override
  String get continueWithGoogle => 'Lanjutkan dengan Google';

  @override
  String get byContinuingYouAgree => 'Dengan melanjutkan, Anda menyetujui ';

  @override
  String get termsOfService => 'Ketentuan Layanan';

  @override
  String get and => ' dan ';

  @override
  String get dataAndPrivacy => 'Data & Privasi';

  @override
  String get secureAuthViaAppleId => 'Autentikasi aman melalui Apple ID';

  @override
  String get secureAuthViaGoogleAccount => 'Autentikasi aman melalui Akun Google';

  @override
  String get whatWeCollect => 'Apa yang kami kumpulkan';

  @override
  String get dataCollectionMessage =>
      'Dengan melanjutkan, percakapan, rekaman, dan informasi pribadi Anda akan disimpan dengan aman di server kami untuk memberikan wawasan berbasis AI dan mengaktifkan semua fitur aplikasi.';

  @override
  String get dataProtection => 'Perlindungan Data';

  @override
  String get yourDataIsProtected => 'Data Anda dilindungi dan diatur oleh ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'Silakan pilih bahasa utama Anda';

  @override
  String get chooseYourLanguage => 'Pilih bahasa Anda';

  @override
  String get selectPreferredLanguageForBestExperience => 'Pilih bahasa pilihan Anda untuk pengalaman Omi terbaik';

  @override
  String get searchLanguages => 'Cari bahasa...';

  @override
  String get selectALanguage => 'Pilih bahasa';

  @override
  String get tryDifferentSearchTerm => 'Coba istilah pencarian yang berbeda';

  @override
  String get pleaseEnterYourName => 'Silakan masukkan nama Anda';

  @override
  String get nameMustBeAtLeast2Characters => 'Nama harus minimal 2 karakter';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'Beri tahu kami bagaimana Anda ingin disapa. Ini membantu mempersonalisasi pengalaman Omi Anda.';

  @override
  String charactersCount(int count) {
    return '$count karakter';
  }

  @override
  String get enableFeaturesForBestExperience => 'Aktifkan fitur untuk pengalaman Omi terbaik di perangkat Anda.';

  @override
  String get microphoneAccess => 'Akses Mikrofon';

  @override
  String get recordAudioConversations => 'Rekam percakapan audio';

  @override
  String get microphoneAccessDescription =>
      'Omi memerlukan akses mikrofon untuk merekam percakapan Anda dan memberikan transkripsi.';

  @override
  String get screenRecording => 'Perekaman Layar';

  @override
  String get captureSystemAudioFromMeetings => 'Tangkap audio sistem dari rapat';

  @override
  String get screenRecordingDescription =>
      'Omi memerlukan izin perekaman layar untuk menangkap audio sistem dari rapat berbasis browser Anda.';

  @override
  String get accessibility => 'Aksesibilitas';

  @override
  String get detectBrowserBasedMeetings => 'Deteksi rapat berbasis browser';

  @override
  String get accessibilityDescription =>
      'Omi memerlukan izin aksesibilitas untuk mendeteksi saat Anda bergabung dengan rapat Zoom, Meet, atau Teams di browser Anda.';

  @override
  String get pleaseWait => 'Harap tunggu...';

  @override
  String get joinTheCommunity => 'Bergabunglah dengan komunitas!';

  @override
  String get loadingProfile => 'Memuat profil...';

  @override
  String get profileSettings => 'Pengaturan Profil';

  @override
  String get noEmailSet => 'Tidak ada email yang diatur';

  @override
  String get userIdCopiedToClipboard => 'ID pengguna disalin';

  @override
  String get yourInformation => 'Informasi Anda';

  @override
  String get setYourName => 'Atur Nama Anda';

  @override
  String get changeYourName => 'Ubah Nama Anda';

  @override
  String get manageYourOmiPersona => 'Kelola persona Omi Anda';

  @override
  String get voiceAndPeople => 'Suara & Orang';

  @override
  String get teachOmiYourVoice => 'Ajari Omi suara Anda';

  @override
  String get tellOmiWhoSaidIt => 'Beri tahu Omi siapa yang mengatakannya 🗣️';

  @override
  String get payment => 'Pembayaran';

  @override
  String get addOrChangeYourPaymentMethod => 'Tambah atau ubah metode pembayaran';

  @override
  String get preferences => 'Preferensi';

  @override
  String get helpImproveOmiBySharing => 'Bantu tingkatkan Omi dengan berbagi data analitik anonim';

  @override
  String get deleteAccount => 'Hapus Akun';

  @override
  String get deleteYourAccountAndAllData => 'Hapus akun dan semua data Anda';

  @override
  String get clearLogs => 'Hapus log';

  @override
  String get debugLogsCleared => 'Log debug dibersihkan';

  @override
  String get exportConversations => 'Ekspor Percakapan';

  @override
  String get exportAllConversationsToJson => 'Ekspor semua percakapan Anda ke file JSON.';

  @override
  String get conversationsExportStarted =>
      'Ekspor Percakapan Dimulai. Ini mungkin memakan waktu beberapa detik, harap tunggu.';

  @override
  String get mcpDescription =>
      'Untuk menghubungkan Omi dengan aplikasi lain untuk membaca, mencari, dan mengelola kenangan dan percakapan Anda. Buat kunci untuk memulai.';

  @override
  String get apiKeys => 'Kunci API';

  @override
  String errorLabel(String error) {
    return 'Kesalahan: $error';
  }

  @override
  String get noApiKeysFound => 'Tidak ada kunci API yang ditemukan. Buat satu untuk memulai.';

  @override
  String get advancedSettings => 'Pengaturan Lanjutan';

  @override
  String get triggersWhenNewConversationCreated => 'Dipicu ketika percakapan baru dibuat.';

  @override
  String get triggersWhenNewTranscriptReceived => 'Dipicu ketika transkrip baru diterima.';

  @override
  String get realtimeAudioBytes => 'Byte Audio Waktu Nyata';

  @override
  String get triggersWhenAudioBytesReceived => 'Dipicu ketika byte audio diterima.';

  @override
  String get everyXSeconds => 'Setiap x detik';

  @override
  String get triggersWhenDaySummaryGenerated => 'Dipicu ketika ringkasan hari dibuat.';

  @override
  String get tryLatestExperimentalFeatures => 'Coba fitur eksperimental terbaru dari Tim Omi.';

  @override
  String get transcriptionServiceDiagnosticStatus => 'Status diagnostik layanan transkripsi';

  @override
  String get enableDetailedDiagnosticMessages => 'Aktifkan pesan diagnostik terperinci dari layanan transkripsi';

  @override
  String get autoCreateAndTagNewSpeakers => 'Buat dan tandai pembicara baru secara otomatis';

  @override
  String get automaticallyCreateNewPerson => 'Secara otomatis buat orang baru ketika nama terdeteksi dalam transkrip.';

  @override
  String get pilotFeatures => 'Fitur Pilot';

  @override
  String get pilotFeaturesDescription => 'Fitur ini adalah tes dan tidak ada jaminan dukungan.';

  @override
  String get suggestFollowUpQuestion => 'Sarankan pertanyaan lanjutan';

  @override
  String get saveSettings => 'Simpan Pengaturan';

  @override
  String get syncingDeveloperSettings => 'Menyinkronkan Pengaturan Pengembang...';

  @override
  String get summary => 'Ringkasan';

  @override
  String get auto => 'Otomatis';

  @override
  String get noSummaryForApp =>
      'Tidak ada ringkasan yang tersedia untuk aplikasi ini. Coba aplikasi lain untuk hasil yang lebih baik.';

  @override
  String get tryAnotherApp => 'Coba Aplikasi Lain';

  @override
  String generatedBy(String appName) {
    return 'Dibuat oleh $appName';
  }

  @override
  String get overview => 'Ikhtisar';

  @override
  String get otherAppResults => 'Hasil Aplikasi Lain';

  @override
  String get unknownApp => 'Aplikasi tidak dikenal';

  @override
  String get noSummaryAvailable => 'Tidak Ada Ringkasan Tersedia';

  @override
  String get conversationNoSummaryYet => 'Percakapan ini belum memiliki ringkasan.';

  @override
  String get chooseSummarizationApp => 'Pilih Aplikasi Ringkasan';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName ditetapkan sebagai aplikasi ringkasan default';
  }

  @override
  String get letOmiChooseAutomatically => 'Biarkan Omi memilih aplikasi terbaik secara otomatis';

  @override
  String get deleteConversationConfirmation =>
      'Apakah Anda yakin ingin menghapus percakapan ini? Tindakan ini tidak dapat dibatalkan.';

  @override
  String get conversationDeleted => 'Percakapan dihapus';

  @override
  String get generatingLink => 'Membuat tautan...';

  @override
  String get editConversation => 'Edit percakapan';

  @override
  String get conversationLinkCopiedToClipboard => 'Tautan percakapan disalin ke clipboard';

  @override
  String get conversationTranscriptCopiedToClipboard => 'Transkrip percakapan disalin ke clipboard';

  @override
  String get editConversationDialogTitle => 'Edit Percakapan';

  @override
  String get changeTheConversationTitle => 'Ubah judul percakapan';

  @override
  String get conversationTitle => 'Judul Percakapan';

  @override
  String get enterConversationTitle => 'Masukkan judul percakapan...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'Judul percakapan berhasil diperbarui';

  @override
  String get failedToUpdateConversationTitle => 'Gagal memperbarui judul percakapan';

  @override
  String get errorUpdatingConversationTitle => 'Kesalahan memperbarui judul percakapan';

  @override
  String get settingUp => 'Mengatur...';

  @override
  String get startYourFirstRecording => 'Mulai rekaman pertama Anda';

  @override
  String get preparingSystemAudioCapture => 'Menyiapkan tangkapan audio sistem';

  @override
  String get clickTheButtonToCaptureAudio =>
      'Klik tombol untuk menangkap audio untuk transkripsi langsung, wawasan AI, dan penyimpanan otomatis.';

  @override
  String get reconnecting => 'Menyambung kembali...';

  @override
  String get recordingPaused => 'Perekaman dijeda';

  @override
  String get recordingActive => 'Perekaman aktif';

  @override
  String get startRecording => 'Mulai merekam';

  @override
  String resumingInCountdown(String countdown) {
    return 'Melanjutkan dalam ${countdown}d...';
  }

  @override
  String get tapPlayToResume => 'Ketuk putar untuk melanjutkan';

  @override
  String get listeningForAudio => 'Mendengarkan audio...';

  @override
  String get preparingAudioCapture => 'Menyiapkan tangkapan audio';

  @override
  String get clickToBeginRecording => 'Klik untuk mulai merekam';

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
  String get startRecordingToSeeTranscript => 'Mulai merekam untuk melihat transkripsi langsung';

  @override
  String get paused => 'Dijeda';

  @override
  String get initializing => 'Menginisialisasi...';

  @override
  String get recording => 'Merekam';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'Mikrofon diubah. Melanjutkan dalam ${countdown}d';
  }

  @override
  String get clickPlayToResumeOrStop => 'Klik putar untuk melanjutkan atau berhenti untuk menyelesaikan';

  @override
  String get settingUpSystemAudioCapture => 'Mengatur tangkapan audio sistem';

  @override
  String get capturingAudioAndGeneratingTranscript => 'Menangkap audio dan menghasilkan transkripsi';

  @override
  String get clickToBeginRecordingSystemAudio => 'Klik untuk mulai merekam audio sistem';

  @override
  String get you => 'Anda';

  @override
  String speakerWithId(String speakerId) {
    return 'Pembicara $speakerId';
  }

  @override
  String get translatedByOmi => 'diterjemahkan oleh omi';

  @override
  String get backToConversations => 'Kembali ke Percakapan';

  @override
  String get systemAudio => 'Sistem';

  @override
  String get mic => 'Mikrofon';

  @override
  String audioInputSetTo(String deviceName) {
    return 'Input audio diatur ke $deviceName';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'Kesalahan saat mengganti perangkat audio: $error';
  }

  @override
  String get selectAudioInput => 'Pilih Input Audio';

  @override
  String get loadingDevices => 'Memuat perangkat...';

  @override
  String get settingsHeader => 'PENGATURAN';

  @override
  String get plansAndBilling => 'Paket & Penagihan';

  @override
  String get calendarIntegration => 'Integrasi Kalender';

  @override
  String get dailySummary => 'Ringkasan Harian';

  @override
  String get developer => 'Pengembang';

  @override
  String get about => 'Tentang';

  @override
  String get selectTime => 'Pilih Waktu';

  @override
  String get accountGroup => 'Akun';

  @override
  String get signOutQuestion => 'Keluar?';

  @override
  String get signOutConfirmation => 'Apakah Anda yakin ingin keluar?';

  @override
  String get customVocabularyHeader => 'KOSAKATA KUSTOM';

  @override
  String get addWordsDescription => 'Tambahkan kata-kata yang harus dikenali Omi selama transkripsi.';

  @override
  String get enterWordsHint => 'Masukkan kata (dipisahkan koma)';

  @override
  String get dailySummaryHeader => 'RINGKASAN HARIAN';

  @override
  String get dailySummaryTitle => 'Ringkasan Harian';

  @override
  String get dailySummaryDescription => 'Dapatkan ringkasan percakapan harian yang dipersonalisasi sebagai notifikasi.';

  @override
  String get deliveryTime => 'Waktu Pengiriman';

  @override
  String get deliveryTimeDescription => 'Kapan menerima ringkasan harian Anda';

  @override
  String get subscription => 'Langganan';

  @override
  String get viewPlansAndUsage => 'Lihat Paket & Penggunaan';

  @override
  String get viewPlansDescription => 'Kelola langganan Anda dan lihat statistik penggunaan';

  @override
  String get addOrChangePaymentMethod => 'Tambahkan atau ubah metode pembayaran Anda';

  @override
  String get displayOptions => 'Opsi Tampilan';

  @override
  String get showMeetingsInMenuBar => 'Tampilkan Rapat di Bilah Menu';

  @override
  String get displayUpcomingMeetingsDescription => 'Tampilkan rapat mendatang di bilah menu';

  @override
  String get showEventsWithoutParticipants => 'Tampilkan Acara Tanpa Peserta';

  @override
  String get includePersonalEventsDescription => 'Sertakan acara pribadi tanpa peserta';

  @override
  String get upcomingMeetings => 'Pertemuan Mendatang';

  @override
  String get checkingNext7Days => 'Memeriksa 7 hari ke depan';

  @override
  String get shortcuts => 'Pintasan';

  @override
  String get shortcutChangeInstruction => 'Klik pintasan untuk mengubahnya. Tekan Escape untuk membatalkan.';

  @override
  String get configurePersonaDescription => 'Konfigurasi persona AI Anda';

  @override
  String get configureSTTProvider => 'Konfigurasi penyedia STT';

  @override
  String get setConversationEndDescription => 'Atur kapan percakapan berakhir otomatis';

  @override
  String get importDataDescription => 'Impor data dari sumber lain';

  @override
  String get exportConversationsDescription => 'Ekspor percakapan ke JSON';

  @override
  String get exportingConversations => 'Mengekspor percakapan...';

  @override
  String get clearNodesDescription => 'Hapus semua node dan koneksi';

  @override
  String get deleteKnowledgeGraphQuestion => 'Hapus Grafik Pengetahuan?';

  @override
  String get deleteKnowledgeGraphWarning =>
      'Ini akan menghapus semua data grafik pengetahuan turunan. Kenangan asli Anda tetap aman.';

  @override
  String get connectOmiWithAI => 'Hubungkan Omi dengan asisten AI';

  @override
  String get noAPIKeys => 'Tidak ada kunci API. Buat satu untuk memulai.';

  @override
  String get autoCreateWhenDetected => 'Buat otomatis saat nama terdeteksi';

  @override
  String get trackPersonalGoals => 'Lacak tujuan pribadi di halaman utama';

  @override
  String get dailyReflectionDescription =>
      'Dapatkan pengingat pukul 21.00 untuk merefleksikan hari Anda dan mencatat pikiran Anda.';

  @override
  String get endpointURL => 'URL Endpoint';

  @override
  String get links => 'Tautan';

  @override
  String get discordMemberCount => '8000+ anggota di Discord';

  @override
  String get userInformation => 'Informasi Pengguna';

  @override
  String get capabilities => 'Kemampuan';

  @override
  String get previewScreenshots => 'Pratinjau tangkapan layar';

  @override
  String get holdOnPreparingForm => 'Tunggu sebentar, kami sedang menyiapkan formulir untuk Anda';

  @override
  String get bySubmittingYouAgreeToOmi => 'Dengan mengirimkan, Anda menyetujui ';

  @override
  String get termsAndPrivacyPolicy => 'Syarat & Kebijakan Privasi';

  @override
  String get helpsDiagnoseIssuesAutoDeletes => 'Membantu mendiagnosis masalah. Otomatis dihapus setelah 3 hari.';

  @override
  String get manageYourApp => 'Kelola Aplikasi Anda';

  @override
  String get updatingYourApp => 'Memperbarui aplikasi Anda';

  @override
  String get fetchingYourAppDetails => 'Mengambil detail aplikasi Anda';

  @override
  String get updateAppQuestion => 'Perbarui Aplikasi?';

  @override
  String get updateAppConfirmation =>
      'Apakah Anda yakin ingin memperbarui aplikasi? Perubahan akan terlihat setelah ditinjau oleh tim kami.';

  @override
  String get updateApp => 'Perbarui Aplikasi';

  @override
  String get createAndSubmitNewApp => 'Buat dan kirim aplikasi baru';

  @override
  String appsCount(String count) {
    return 'Aplikasi ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'Aplikasi Pribadi ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'Aplikasi Publik ($count)';
  }

  @override
  String get newVersionAvailable => 'Versi Baru Tersedia  🎉';

  @override
  String get no => 'Tidak';

  @override
  String get subscriptionCancelledSuccessfully =>
      'Langganan berhasil dibatalkan. Akan tetap aktif hingga akhir periode penagihan saat ini.';

  @override
  String get failedToCancelSubscription => 'Gagal membatalkan langganan. Silakan coba lagi.';

  @override
  String get invalidPaymentUrl => 'URL pembayaran tidak valid';

  @override
  String get permissionsAndTriggers => 'Izin & Pemicu';

  @override
  String get chatFeatures => 'Fitur Obrolan';

  @override
  String get uninstall => 'Copot pemasangan';

  @override
  String get installs => 'PEMASANGAN';

  @override
  String get priceLabel => 'HARGA';

  @override
  String get updatedLabel => 'DIPERBARUI';

  @override
  String get createdLabel => 'DIBUAT';

  @override
  String get featuredLabel => 'UNGGULAN';

  @override
  String get cancelSubscriptionQuestion => 'Batalkan Langganan?';

  @override
  String get cancelSubscriptionConfirmation =>
      'Apakah Anda yakin ingin membatalkan langganan? Anda akan tetap memiliki akses hingga akhir periode penagihan saat ini.';

  @override
  String get cancelSubscriptionButton => 'Batalkan Langganan';

  @override
  String get cancelling => 'Membatalkan...';

  @override
  String get betaTesterMessage =>
      'Anda adalah penguji beta untuk aplikasi ini. Belum dipublikasikan. Akan dipublikasikan setelah disetujui.';

  @override
  String get appUnderReviewMessage =>
      'Aplikasi Anda sedang ditinjau dan hanya terlihat oleh Anda. Akan dipublikasikan setelah disetujui.';

  @override
  String get appRejectedMessage => 'Aplikasi Anda ditolak. Perbarui detail dan kirim ulang untuk ditinjau.';

  @override
  String get invalidIntegrationUrl => 'URL integrasi tidak valid';

  @override
  String get tapToComplete => 'Ketuk untuk menyelesaikan';

  @override
  String get invalidSetupInstructionsUrl => 'URL instruksi pengaturan tidak valid';

  @override
  String get pushToTalk => 'Tekan untuk Bicara';

  @override
  String get summaryPrompt => 'Prompt Ringkasan';

  @override
  String get pleaseSelectARating => 'Silakan pilih penilaian';

  @override
  String get reviewAddedSuccessfully => 'Ulasan berhasil ditambahkan 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'Ulasan berhasil diperbarui 🚀';

  @override
  String get failedToSubmitReview => 'Gagal mengirim ulasan. Silakan coba lagi.';

  @override
  String get addYourReview => 'Tambahkan Ulasan Anda';

  @override
  String get editYourReview => 'Edit Ulasan Anda';

  @override
  String get writeAReviewOptional => 'Tulis ulasan (opsional)';

  @override
  String get submitReview => 'Kirim Ulasan';

  @override
  String get updateReview => 'Perbarui Ulasan';

  @override
  String get yourReview => 'Ulasan Anda';

  @override
  String get anonymousUser => 'Pengguna Anonim';

  @override
  String get issueActivatingApp => 'Terjadi masalah saat mengaktifkan aplikasi ini. Silakan coba lagi.';

  @override
  String get dataAccessNoticeDescription =>
      'This app will access your data. Omi AI is not responsible for how your data is used, modified, or deleted by this app';

  @override
  String get copyUrl => 'Salin URL';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => 'Sen';

  @override
  String get weekdayTue => 'Sel';

  @override
  String get weekdayWed => 'Rab';

  @override
  String get weekdayThu => 'Kam';

  @override
  String get weekdayFri => 'Jum';

  @override
  String get weekdaySat => 'Sab';

  @override
  String get weekdaySun => 'Min';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return 'Integrasi $serviceName segera hadir';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'Sudah diekspor ke $platform';
  }

  @override
  String get anotherPlatform => 'platform lain';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'Silakan autentikasi dengan $serviceName di Pengaturan > Integrasi Tugas';
  }

  @override
  String addingToService(String serviceName) {
    return 'Menambahkan ke $serviceName...';
  }

  @override
  String addedToService(String serviceName) {
    return 'Ditambahkan ke $serviceName';
  }

  @override
  String failedToAddToService(String serviceName) {
    return 'Gagal menambahkan ke $serviceName';
  }

  @override
  String get permissionDeniedForAppleReminders => 'Izin ditolak untuk Apple Reminders';

  @override
  String failedToCreateApiKey(String error) {
    return 'Gagal membuat kunci API penyedia: $error';
  }

  @override
  String get createAKey => 'Buat Kunci';

  @override
  String get apiKeyRevokedSuccessfully => 'Kunci API berhasil dicabut';

  @override
  String failedToRevokeApiKey(String error) {
    return 'Gagal mencabut kunci API: $error';
  }

  @override
  String get omiApiKeys => 'Kunci API Omi';

  @override
  String get apiKeysDescription =>
      'Kunci API digunakan untuk autentikasi saat aplikasi Anda berkomunikasi dengan server OMI. Kunci ini memungkinkan aplikasi Anda membuat memori dan mengakses layanan OMI lainnya dengan aman.';

  @override
  String get aboutOmiApiKeys => 'Tentang Kunci API Omi';

  @override
  String get yourNewKey => 'Kunci baru Anda:';

  @override
  String get copyToClipboard => 'Salin ke papan klip';

  @override
  String get pleaseCopyKeyNow => 'Silakan salin sekarang dan simpan di tempat yang aman. ';

  @override
  String get willNotSeeAgain => 'Anda tidak akan dapat melihatnya lagi.';

  @override
  String get revokeKey => 'Cabut kunci';

  @override
  String get revokeApiKeyQuestion => 'Cabut Kunci API?';

  @override
  String get revokeApiKeyWarning =>
      'Tindakan ini tidak dapat dibatalkan. Aplikasi apa pun yang menggunakan kunci ini tidak akan dapat mengakses API lagi.';

  @override
  String get revoke => 'Cabut';

  @override
  String get whatWouldYouLikeToCreate => 'Apa yang ingin Anda buat?';

  @override
  String get createAnApp => 'Buat Aplikasi';

  @override
  String get createAndShareYourApp => 'Buat dan bagikan aplikasi Anda';

  @override
  String get createMyClone => 'Buat Klon Saya';

  @override
  String get createYourDigitalClone => 'Buat klon digital Anda';

  @override
  String get itemApp => 'Aplikasi';

  @override
  String get itemPersona => 'Persona';

  @override
  String keepItemPublic(String item) {
    return 'Pertahankan $item Publik';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return 'Jadikan $item Publik?';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return 'Jadikan $item Pribadi?';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'Jika Anda menjadikan $item publik, dapat digunakan oleh semua orang';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'Jika Anda menjadikan $item pribadi sekarang, itu akan berhenti bekerja untuk semua orang dan hanya akan terlihat oleh Anda';
  }

  @override
  String get manageApp => 'Kelola Aplikasi';

  @override
  String get updatePersonaDetails => 'Perbarui Detail Persona';

  @override
  String deleteItemTitle(String item) {
    return 'Hapus $item';
  }

  @override
  String deleteItemQuestion(String item) {
    return 'Hapus $item?';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'Apakah Anda yakin ingin menghapus $item ini? Tindakan ini tidak dapat dibatalkan.';
  }

  @override
  String get revokeKeyQuestion => 'Cabut Kunci?';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'Apakah Anda yakin ingin mencabut kunci \"$keyName\"? Tindakan ini tidak dapat dibatalkan.';
  }

  @override
  String get createNewKey => 'Buat Kunci Baru';

  @override
  String get keyNameHint => 'mis., Claude Desktop';

  @override
  String get pleaseEnterAName => 'Silakan masukkan nama.';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'Gagal membuat kunci: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'Gagal membuat kunci. Silakan coba lagi.';

  @override
  String get keyCreated => 'Kunci Dibuat';

  @override
  String get keyCreatedMessage =>
      'Kunci baru Anda telah dibuat. Silakan salin sekarang. Anda tidak akan dapat melihatnya lagi.';

  @override
  String get keyWord => 'Kunci';

  @override
  String get externalAppAccess => 'Akses Aplikasi Eksternal';

  @override
  String get externalAppAccessDescription =>
      'Aplikasi terinstal berikut memiliki integrasi eksternal dan dapat mengakses data Anda, seperti percakapan dan kenangan.';

  @override
  String get noExternalAppsHaveAccess => 'Tidak ada aplikasi eksternal yang memiliki akses ke data Anda.';

  @override
  String get maximumSecurityE2ee => 'Keamanan Maksimum (E2EE)';

  @override
  String get e2eeDescription =>
      'Enkripsi end-to-end adalah standar emas untuk privasi. Saat diaktifkan, data Anda dienkripsi di perangkat Anda sebelum dikirim ke server kami. Ini berarti tidak ada seorang pun, bahkan Omi, yang dapat mengakses konten Anda.';

  @override
  String get importantTradeoffs => 'Pertimbangan Penting:';

  @override
  String get e2eeTradeoff1 => '• Beberapa fitur seperti integrasi aplikasi eksternal mungkin dinonaktifkan.';

  @override
  String get e2eeTradeoff2 => '• Jika Anda kehilangan kata sandi, data Anda tidak dapat dipulihkan.';

  @override
  String get featureComingSoon => 'Fitur ini akan segera hadir!';

  @override
  String get migrationInProgressMessage =>
      'Migrasi sedang berlangsung. Anda tidak dapat mengubah tingkat perlindungan sampai selesai.';

  @override
  String get migrationFailed => 'Migrasi Gagal';

  @override
  String migratingFromTo(String source, String target) {
    return 'Memigrasikan dari $source ke $target';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total objek';
  }

  @override
  String get secureEncryption => 'Enkripsi Aman';

  @override
  String get secureEncryptionDescription =>
      'Data Anda dienkripsi dengan kunci yang unik untuk Anda di server kami, yang dihosting di Google Cloud. Ini berarti konten mentah Anda tidak dapat diakses oleh siapa pun, termasuk staf Omi atau Google, langsung dari database.';

  @override
  String get endToEndEncryption => 'Enkripsi End-to-End';

  @override
  String get e2eeCardDescription =>
      'Aktifkan untuk keamanan maksimum di mana hanya Anda yang dapat mengakses data Anda. Ketuk untuk mempelajari lebih lanjut.';

  @override
  String get dataAlwaysEncrypted =>
      'Terlepas dari levelnya, data Anda selalu dienkripsi saat diam dan dalam perjalanan.';

  @override
  String get readOnlyScope => 'Hanya Baca';

  @override
  String get fullAccessScope => 'Akses Penuh';

  @override
  String get readScope => 'Baca';

  @override
  String get writeScope => 'Tulis';

  @override
  String get apiKeyCreated => 'Kunci API Dibuat!';

  @override
  String get saveKeyWarning => 'Simpan kunci ini sekarang! Anda tidak akan bisa melihatnya lagi.';

  @override
  String get yourApiKey => 'KUNCI API ANDA';

  @override
  String get tapToCopy => 'Ketuk untuk menyalin';

  @override
  String get copyKey => 'Salin Kunci';

  @override
  String get createApiKey => 'Buat Kunci API';

  @override
  String get accessDataProgrammatically => 'Akses data Anda secara terprogram';

  @override
  String get keyNameLabel => 'NAMA KUNCI';

  @override
  String get keyNamePlaceholder => 'mis., Integrasi Aplikasi Saya';

  @override
  String get permissionsLabel => 'IZIN';

  @override
  String get permissionsInfoNote => 'R = Baca, W = Tulis. Default hanya baca jika tidak ada yang dipilih.';

  @override
  String get developerApi => 'API Pengembang';

  @override
  String get createAKeyToGetStarted => 'Buat kunci untuk memulai';

  @override
  String errorWithMessage(String error) {
    return 'Kesalahan: $error';
  }

  @override
  String get omiTraining => 'Pelatihan Omi';

  @override
  String get trainingDataProgram => 'Program Data Pelatihan';

  @override
  String get getOmiUnlimitedFree =>
      'Dapatkan Omi Unlimited gratis dengan menyumbangkan data Anda untuk melatih model AI.';

  @override
  String get trainingDataBullets =>
      '• Data Anda membantu meningkatkan model AI\n• Hanya data non-sensitif yang dibagikan\n• Proses sepenuhnya transparan';

  @override
  String get learnMoreAtOmiTraining => 'Pelajari lebih lanjut di omi.me/training';

  @override
  String get agreeToContributeData => 'Saya memahami dan setuju untuk menyumbangkan data saya untuk pelatihan AI';

  @override
  String get submitRequest => 'Kirim Permintaan';

  @override
  String get thankYouRequestUnderReview =>
      'Terima kasih! Permintaan Anda sedang ditinjau. Kami akan memberi tahu Anda setelah disetujui.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'Paket Anda akan tetap aktif hingga $date. Setelah itu, Anda akan kehilangan akses ke fitur tak terbatas. Apakah Anda yakin?';
  }

  @override
  String get confirmCancellation => 'Konfirmasi Pembatalan';

  @override
  String get keepMyPlan => 'Pertahankan Paket Saya';

  @override
  String get subscriptionSetToCancel => 'Langganan Anda diatur untuk dibatalkan di akhir periode.';

  @override
  String get switchedToOnDevice => 'Beralih ke transkripsi di perangkat';

  @override
  String get couldNotSwitchToFreePlan => 'Tidak dapat beralih ke paket gratis. Silakan coba lagi.';

  @override
  String get couldNotLoadPlans => 'Tidak dapat memuat paket yang tersedia. Silakan coba lagi.';

  @override
  String get selectedPlanNotAvailable => 'Paket yang dipilih tidak tersedia. Silakan coba lagi.';

  @override
  String get upgradeToAnnualPlan => 'Tingkatkan ke Paket Tahunan';

  @override
  String get importantBillingInfo => 'Informasi Penagihan Penting:';

  @override
  String get monthlyPlanContinues => 'Paket bulanan Anda saat ini akan berlanjut hingga akhir periode penagihan';

  @override
  String get paymentMethodCharged =>
      'Metode pembayaran Anda yang ada akan dikenakan biaya secara otomatis saat paket bulanan Anda berakhir';

  @override
  String get annualSubscriptionStarts =>
      'Langganan tahunan 12 bulan Anda akan dimulai secara otomatis setelah pembayaran';

  @override
  String get thirteenMonthsCoverage => 'Anda akan mendapatkan total 13 bulan cakupan (bulan ini + 12 bulan tahunan)';

  @override
  String get confirmUpgrade => 'Konfirmasi Peningkatan';

  @override
  String get confirmPlanChange => 'Konfirmasi Perubahan Paket';

  @override
  String get confirmAndProceed => 'Konfirmasi & Lanjutkan';

  @override
  String get upgradeScheduled => 'Peningkatan Dijadwalkan';

  @override
  String get changePlan => 'Ubah Paket';

  @override
  String get upgradeAlreadyScheduled => 'Peningkatan Anda ke paket tahunan sudah dijadwalkan';

  @override
  String get youAreOnUnlimitedPlan => 'Anda berada di Paket Tak Terbatas.';

  @override
  String get yourOmiUnleashed => 'Omi Anda, dibebaskan. Pilih tak terbatas untuk kemungkinan tanpa akhir.';

  @override
  String planEndedOn(String date) {
    return 'Paket Anda berakhir pada $date.\\nBerlangganan lagi sekarang - Anda akan dikenakan biaya segera untuk periode penagihan baru.';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'Paket Anda diatur untuk dibatalkan pada $date.\\nBerlangganan lagi sekarang untuk mempertahankan manfaat Anda - tidak ada biaya hingga $date.';
  }

  @override
  String get annualPlanStartsAutomatically =>
      'Paket tahunan Anda akan dimulai secara otomatis saat paket bulanan Anda berakhir.';

  @override
  String planRenewsOn(String date) {
    return 'Paket Anda diperbarui pada $date.';
  }

  @override
  String get unlimitedConversations => 'Percakapan tak terbatas';

  @override
  String get askOmiAnything => 'Tanya Omi apa saja tentang hidup Anda';

  @override
  String get unlockOmiInfiniteMemory => 'Buka kunci memori tak terbatas Omi';

  @override
  String get youreOnAnnualPlan => 'Anda berada di Paket Tahunan';

  @override
  String get alreadyBestValuePlan => 'Anda sudah memiliki paket dengan nilai terbaik. Tidak perlu perubahan.';

  @override
  String get unableToLoadPlans => 'Tidak dapat memuat paket';

  @override
  String get checkConnectionTryAgain => 'Silakan periksa koneksi Anda dan coba lagi';

  @override
  String get useFreePlan => 'Gunakan Paket Gratis';

  @override
  String get continueText => 'Lanjutkan';

  @override
  String get resubscribe => 'Berlangganan lagi';

  @override
  String get couldNotOpenPaymentSettings => 'Tidak dapat membuka pengaturan pembayaran. Silakan coba lagi.';

  @override
  String get managePaymentMethod => 'Kelola Metode Pembayaran';

  @override
  String get cancelSubscription => 'Batalkan Langganan';

  @override
  String endsOnDate(String date) {
    return 'Berakhir pada $date';
  }

  @override
  String get active => 'Aktif';

  @override
  String get freePlan => 'Paket Gratis';

  @override
  String get configure => 'Konfigurasi';

  @override
  String get privacyInformation => 'Informasi Privasi';

  @override
  String get yourPrivacyMattersToUs => 'Privasi Anda Penting bagi Kami';

  @override
  String get privacyIntroText =>
      'Di Omi, kami menganggap privasi Anda dengan sangat serius. Kami ingin transparan tentang data yang kami kumpulkan dan bagaimana kami menggunakannya. Inilah yang perlu Anda ketahui:';

  @override
  String get whatWeTrack => 'Apa yang Kami Lacak';

  @override
  String get anonymityAndPrivacy => 'Anonimitas dan Privasi';

  @override
  String get optInAndOptOutOptions => 'Opsi Ikut Serta dan Tidak Ikut Serta';

  @override
  String get ourCommitment => 'Komitmen Kami';

  @override
  String get commitmentText =>
      'Kami berkomitmen untuk menggunakan data yang kami kumpulkan hanya untuk membuat Omi menjadi produk yang lebih baik untuk Anda. Privasi dan kepercayaan Anda sangat penting bagi kami.';

  @override
  String get thankYouText =>
      'Terima kasih telah menjadi pengguna Omi yang berharga. Jika Anda memiliki pertanyaan atau kekhawatiran, jangan ragu untuk menghubungi kami di team@basedhardware.com.';

  @override
  String get wifiSyncSettings => 'Pengaturan Sinkronisasi WiFi';

  @override
  String get enterHotspotCredentials => 'Masukkan kredensial hotspot ponsel Anda';

  @override
  String get wifiSyncUsesHotspot =>
      'Sinkronisasi WiFi menggunakan ponsel Anda sebagai hotspot. Temukan nama dan kata sandi di Pengaturan > Hotspot Pribadi.';

  @override
  String get hotspotNameSsid => 'Nama Hotspot (SSID)';

  @override
  String get exampleIphoneHotspot => 'mis. iPhone Hotspot';

  @override
  String get password => 'Kata Sandi';

  @override
  String get enterHotspotPassword => 'Masukkan kata sandi hotspot';

  @override
  String get saveCredentials => 'Simpan Kredensial';

  @override
  String get clearCredentials => 'Hapus Kredensial';

  @override
  String get pleaseEnterHotspotName => 'Silakan masukkan nama hotspot';

  @override
  String get wifiCredentialsSaved => 'Kredensial WiFi disimpan';

  @override
  String get wifiCredentialsCleared => 'Kredensial WiFi dihapus';

  @override
  String summaryGeneratedForDate(String date) {
    return 'Ringkasan dibuat untuk $date';
  }

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'Gagal membuat ringkasan. Pastikan Anda memiliki percakapan untuk hari itu.';

  @override
  String get summaryNotFound => 'Ringkasan tidak ditemukan';

  @override
  String get yourDaysJourney => 'Perjalanan Hari Anda';

  @override
  String get highlights => 'Sorotan';

  @override
  String get unresolvedQuestions => 'Pertanyaan Belum Terjawab';

  @override
  String get decisions => 'Keputusan';

  @override
  String get learnings => 'Pembelajaran';

  @override
  String get autoDeletesAfterThreeDays => 'Hapus otomatis setelah 3 hari.';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'Grafik Pengetahuan berhasil dihapus';

  @override
  String get exportStartedMayTakeFewSeconds => 'Ekspor dimulai. Ini mungkin memerlukan beberapa detik...';

  @override
  String get knowledgeGraphDeleteDescription =>
      'Ini akan menghapus semua data grafik pengetahuan turunan (node dan koneksi). Memori asli Anda akan tetap aman. Grafik akan dibangun kembali seiring waktu atau pada permintaan berikutnya.';

  @override
  String get configureDailySummaryDigest => 'Konfigurasikan ringkasan tugas harian Anda';

  @override
  String accessesDataTypes(String dataTypes) {
    return 'Mengakses $dataTypes';
  }

  @override
  String triggeredByType(String triggerType) {
    return 'dipicu oleh $triggerType';
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
  String get noSpecificDataAccessConfigured => 'Tidak ada akses data spesifik yang dikonfigurasi.';

  @override
  String get basicPlanDescription => '1.200 menit premium + tak terbatas di perangkat';

  @override
  String get minutes => 'menit';

  @override
  String get omiHas => 'Omi memiliki:';

  @override
  String get premiumMinutesUsed => 'Menit premium digunakan.';

  @override
  String get setupOnDevice => 'Atur di perangkat';

  @override
  String get forUnlimitedFreeTranscription => 'untuk transkripsi gratis tanpa batas.';

  @override
  String premiumMinsLeft(int count) {
    return '$count menit premium tersisa.';
  }

  @override
  String get alwaysAvailable => 'selalu tersedia.';

  @override
  String get importHistory => 'Riwayat Impor';

  @override
  String get noImportsYet => 'Belum ada impor';

  @override
  String get selectZipFileToImport => 'Pilih file .zip untuk diimpor!';

  @override
  String get otherDevicesComingSoon => 'Perangkat lain segera hadir';

  @override
  String get deleteAllLimitlessConversations => 'Hapus Semua Percakapan Limitless?';

  @override
  String get deleteAllLimitlessWarning =>
      'Ini akan menghapus secara permanen semua percakapan yang diimpor dari Limitless. Tindakan ini tidak dapat dibatalkan.';

  @override
  String deletedLimitlessConversations(int count) {
    return 'Menghapus $count percakapan Limitless';
  }

  @override
  String get failedToDeleteConversations => 'Gagal menghapus percakapan';

  @override
  String get deleteImportedData => 'Hapus Data yang Diimpor';

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
    return '$count percakapan';
  }

  @override
  String get pleaseEnterName => 'Silakan masukkan nama';

  @override
  String get nameMustBeBetweenCharacters => 'Nama harus antara 2 dan 40 karakter';

  @override
  String get deleteSampleQuestion => 'Hapus Sampel?';

  @override
  String deleteSampleConfirmation(String name) {
    return 'Apakah Anda yakin ingin menghapus sampel $name?';
  }

  @override
  String get confirmDeletion => 'Konfirmasi Penghapusan';

  @override
  String deletePersonConfirmation(String name) {
    return 'Apakah Anda yakin ingin menghapus $name? Ini juga akan menghapus semua sampel suara terkait.';
  }

  @override
  String get howItWorksTitle => 'Bagaimana cara kerjanya?';

  @override
  String get howPeopleWorks =>
      'Setelah seseorang dibuat, Anda dapat pergi ke transkrip percakapan dan menetapkan segmen yang sesuai, dengan cara itu Omi akan dapat mengenali ucapan mereka juga!';

  @override
  String get tapToDelete => 'Ketuk untuk menghapus';

  @override
  String get newTag => 'BARU';

  @override
  String get needHelpChatWithUs => 'Butuh bantuan? Hubungi kami';

  @override
  String get localStorageEnabled => 'Penyimpanan lokal diaktifkan';

  @override
  String get localStorageDisabled => 'Penyimpanan lokal dinonaktifkan';

  @override
  String failedToUpdateSettings(String error) {
    return 'Gagal memperbarui pengaturan: $error';
  }

  @override
  String get privacyNotice => 'Pemberitahuan Privasi';

  @override
  String get recordingsMayCaptureOthers =>
      'Rekaman dapat menangkap suara orang lain. Pastikan Anda memiliki persetujuan dari semua peserta sebelum mengaktifkan.';

  @override
  String get enable => 'Aktifkan';

  @override
  String get storeAudioOnPhone => 'Simpan Audio di Ponsel';

  @override
  String get on => 'Aktif';

  @override
  String get storeAudioDescription =>
      'Simpan semua rekaman audio secara lokal di ponsel Anda. Saat dinonaktifkan, hanya unggahan yang gagal yang disimpan untuk menghemat ruang penyimpanan.';

  @override
  String get enableLocalStorage => 'Aktifkan Penyimpanan Lokal';

  @override
  String get cloudStorageEnabled => 'Penyimpanan cloud diaktifkan';

  @override
  String get cloudStorageDisabled => 'Penyimpanan cloud dinonaktifkan';

  @override
  String get enableCloudStorage => 'Aktifkan Penyimpanan Cloud';

  @override
  String get storeAudioOnCloud => 'Simpan Audio di Cloud';

  @override
  String get cloudStorageDialogMessage =>
      'Rekaman real-time Anda akan disimpan di penyimpanan cloud pribadi saat Anda berbicara.';

  @override
  String get storeAudioCloudDescription =>
      'Simpan rekaman real-time Anda di penyimpanan cloud pribadi saat Anda berbicara. Audio ditangkap dan disimpan dengan aman secara real-time.';

  @override
  String get downloadingFirmware => 'Mengunduh Firmware';

  @override
  String get installingFirmware => 'Memasang Firmware';

  @override
  String get firmwareUpdateWarning => 'Jangan tutup aplikasi atau matikan perangkat. Ini dapat merusak perangkat Anda.';

  @override
  String get firmwareUpdated => 'Firmware Diperbarui';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'Silakan mulai ulang $deviceName Anda untuk menyelesaikan pembaruan.';
  }

  @override
  String get yourDeviceIsUpToDate => 'Perangkat Anda sudah diperbarui';

  @override
  String get currentVersion => 'Versi Saat Ini';

  @override
  String get latestVersion => 'Versi Terbaru';

  @override
  String get whatsNew => 'Yang Baru';

  @override
  String get installUpdate => 'Pasang Pembaruan';

  @override
  String get updateNow => 'Perbarui Sekarang';

  @override
  String get updateGuide => 'Panduan Pembaruan';

  @override
  String get checkingForUpdates => 'Memeriksa Pembaruan';

  @override
  String get checkingFirmwareVersion => 'Memeriksa versi firmware...';

  @override
  String get firmwareUpdate => 'Pembaruan Firmware';

  @override
  String get payments => 'Pembayaran';

  @override
  String get connectPaymentMethodInfo =>
      'Hubungkan metode pembayaran di bawah untuk mulai menerima pembayaran untuk aplikasi Anda.';

  @override
  String get selectedPaymentMethod => 'Metode Pembayaran Terpilih';

  @override
  String get availablePaymentMethods => 'Metode Pembayaran Tersedia';

  @override
  String get activeStatus => 'Aktif';

  @override
  String get connectedStatus => 'Terhubung';

  @override
  String get notConnectedStatus => 'Tidak Terhubung';

  @override
  String get setActive => 'Tetapkan Aktif';

  @override
  String get getPaidThroughStripe => 'Dapatkan bayaran untuk penjualan aplikasi Anda melalui Stripe';

  @override
  String get monthlyPayouts => 'Pembayaran bulanan';

  @override
  String get monthlyPayoutsDescription =>
      'Terima pembayaran bulanan langsung ke akun Anda saat mencapai \$10 dalam penghasilan';

  @override
  String get secureAndReliable => 'Aman dan andal';

  @override
  String get stripeSecureDescription => 'Stripe memastikan transfer pendapatan aplikasi Anda yang aman dan tepat waktu';

  @override
  String get selectYourCountry => 'Pilih negara Anda';

  @override
  String get countrySelectionPermanent => 'Pilihan negara Anda bersifat permanen dan tidak dapat diubah nanti.';

  @override
  String get byClickingConnectNow => 'Dengan mengklik \"Hubungkan Sekarang\" Anda menyetujui';

  @override
  String get stripeConnectedAccountAgreement => 'Perjanjian Akun Terhubung Stripe';

  @override
  String get errorConnectingToStripe => 'Kesalahan menghubungkan ke Stripe! Silakan coba lagi nanti.';

  @override
  String get connectingYourStripeAccount => 'Menghubungkan akun Stripe Anda';

  @override
  String get stripeOnboardingInstructions =>
      'Silakan selesaikan proses orientasi Stripe di browser Anda. Halaman ini akan diperbarui secara otomatis setelah selesai.';

  @override
  String get failedTryAgain => 'Gagal? Coba Lagi';

  @override
  String get illDoItLater => 'Saya akan melakukannya nanti';

  @override
  String get successfullyConnected => 'Berhasil Terhubung!';

  @override
  String get stripeReadyForPayments =>
      'Akun Stripe Anda sekarang siap menerima pembayaran. Anda dapat mulai menghasilkan dari penjualan aplikasi segera.';

  @override
  String get updateStripeDetails => 'Perbarui Detail Stripe';

  @override
  String get errorUpdatingStripeDetails => 'Kesalahan memperbarui detail Stripe! Silakan coba lagi nanti.';

  @override
  String get updatePayPal => 'Perbarui PayPal';

  @override
  String get setUpPayPal => 'Siapkan PayPal';

  @override
  String get updatePayPalAccountDetails => 'Perbarui detail akun PayPal Anda';

  @override
  String get connectPayPalToReceivePayments =>
      'Hubungkan akun PayPal Anda untuk mulai menerima pembayaran untuk aplikasi Anda';

  @override
  String get paypalEmail => 'Email PayPal';

  @override
  String get paypalMeLink => 'Tautan PayPal.me';

  @override
  String get stripeRecommendation =>
      'Jika Stripe tersedia di negara Anda, kami sangat menyarankan untuk menggunakannya untuk pembayaran yang lebih cepat dan mudah.';

  @override
  String get updatePayPalDetails => 'Perbarui Detail PayPal';

  @override
  String get savePayPalDetails => 'Simpan Detail PayPal';

  @override
  String get pleaseEnterPayPalEmail => 'Silakan masukkan email PayPal Anda';

  @override
  String get pleaseEnterPayPalMeLink => 'Silakan masukkan tautan PayPal.me Anda';

  @override
  String get doNotIncludeHttpInLink => 'Jangan sertakan http atau https atau www dalam tautan';

  @override
  String get pleaseEnterValidPayPalMeLink => 'Silakan masukkan tautan PayPal.me yang valid';

  @override
  String get pleaseEnterValidEmail => 'Silakan masukkan alamat email yang valid';

  @override
  String get syncingYourRecordings => 'Menyinkronkan rekaman Anda';

  @override
  String get syncYourRecordings => 'Sinkronkan rekaman Anda';

  @override
  String get syncNow => 'Sinkronkan sekarang';

  @override
  String get error => 'Kesalahan';

  @override
  String get speechSamples => 'Sampel suara';

  @override
  String additionalSampleIndex(String index) {
    return 'Sampel tambahan $index';
  }

  @override
  String durationSeconds(String seconds) {
    return 'Durasi: $seconds detik';
  }

  @override
  String get additionalSpeechSampleRemoved => 'Sampel suara tambahan dihapus';

  @override
  String get consentDataMessage =>
      'Dengan melanjutkan, semua data yang Anda bagikan dengan aplikasi ini (termasuk percakapan, rekaman, dan informasi pribadi Anda) akan disimpan dengan aman di server kami untuk memberikan wawasan berbasis AI dan mengaktifkan semua fitur aplikasi.';

  @override
  String get tasksEmptyStateMessage =>
      'Tugas dari percakapan Anda akan muncul di sini.\nKetuk + untuk membuat secara manual.';

  @override
  String get clearChatAction => 'Hapus obrolan';

  @override
  String get enableApps => 'Aktifkan aplikasi';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => 'tampilkan lebih ↓';

  @override
  String get showLess => 'tampilkan lebih sedikit ↑';

  @override
  String get loadingYourRecording => 'Memuat rekaman Anda...';

  @override
  String get photoDiscardedMessage => 'Foto ini dibuang karena tidak signifikan.';

  @override
  String get analyzing => 'Menganalisis...';

  @override
  String get searchCountries => 'Cari negara...';

  @override
  String get checkingAppleWatch => 'Memeriksa Apple Watch...';

  @override
  String get installOmiOnAppleWatch => 'Instal Omi di\nApple Watch Anda';

  @override
  String get installOmiOnAppleWatchDescription =>
      'Untuk menggunakan Apple Watch dengan Omi, Anda perlu menginstal aplikasi Omi di jam tangan Anda terlebih dahulu.';

  @override
  String get openOmiOnAppleWatch => 'Buka Omi di\nApple Watch Anda';

  @override
  String get openOmiOnAppleWatchDescription =>
      'Aplikasi Omi sudah terinstal di Apple Watch Anda. Buka dan ketuk Mulai untuk memulai.';

  @override
  String get openWatchApp => 'Buka Aplikasi Watch';

  @override
  String get iveInstalledAndOpenedTheApp => 'Saya Sudah Menginstal & Membuka Aplikasi';

  @override
  String get unableToOpenWatchApp =>
      'Tidak dapat membuka aplikasi Apple Watch. Silakan buka aplikasi Watch secara manual di Apple Watch Anda dan instal Omi dari bagian \"Aplikasi Tersedia\".';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch berhasil terhubung!';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch masih tidak dapat dijangkau. Pastikan aplikasi Omi terbuka di jam tangan Anda.';

  @override
  String errorCheckingConnection(String error) {
    return 'Kesalahan memeriksa koneksi: $error';
  }

  @override
  String get muted => 'Dibisukan';

  @override
  String get processNow => 'Proses sekarang';

  @override
  String get finishedConversation => 'Percakapan selesai?';

  @override
  String get stopRecordingConfirmation =>
      'Apakah Anda yakin ingin menghentikan rekaman dan merangkum percakapan sekarang?';

  @override
  String get conversationEndsManually => 'Percakapan hanya akan berakhir secara manual.';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'Percakapan dirangkum setelah $minutes menit$suffix tanpa bicara.';
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
  String get testConversationPrompt => 'Uji prompt percakapan';

  @override
  String get prompt => 'Prompt';

  @override
  String get result => 'Hasil:';

  @override
  String get compareTranscripts => 'Bandingkan transkrip';

  @override
  String get notHelpful => 'Tidak membantu';

  @override
  String get exportTasksWithOneTap => 'Ekspor tugas dengan satu ketukan!';

  @override
  String get inProgress => 'Sedang diproses';

  @override
  String get photos => 'Foto';

  @override
  String get rawData => 'Data Mentah';

  @override
  String get content => 'Konten';

  @override
  String get noContentToDisplay => 'Tidak ada konten untuk ditampilkan';

  @override
  String get noSummary => 'Tidak ada ringkasan';

  @override
  String get updateOmiFirmware => 'Perbarui firmware omi';

  @override
  String get anErrorOccurredTryAgain => 'Terjadi kesalahan. Silakan coba lagi.';

  @override
  String get welcomeBackSimple => 'Selamat datang kembali';

  @override
  String get addVocabularyDescription => 'Tambahkan kata-kata yang harus dikenali Omi selama transkripsi.';

  @override
  String get enterWordsCommaSeparated => 'Masukkan kata-kata (dipisahkan koma)';

  @override
  String get whenToReceiveDailySummary => 'Kapan menerima ringkasan harian Anda';

  @override
  String get checkingNextSevenDays => 'Memeriksa 7 hari ke depan';

  @override
  String failedToDeleteError(String error) {
    return 'Gagal menghapus: $error';
  }

  @override
  String get developerApiKeys => 'Kunci API Pengembang';

  @override
  String get noApiKeysCreateOne => 'Tidak ada kunci API. Buat satu untuk memulai.';

  @override
  String get commandRequired => '⌘ diperlukan';

  @override
  String get spaceKey => 'Spasi';

  @override
  String loadMoreRemaining(String count) {
    return 'Muat lebih banyak ($count tersisa)';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'Top $percentile% Pengguna';
  }

  @override
  String get wrappedMinutes => 'menit';

  @override
  String get wrappedConversations => 'percakapan';

  @override
  String get wrappedDaysActive => 'hari aktif';

  @override
  String get wrappedYouTalkedAbout => 'Kamu membicarakan';

  @override
  String get wrappedActionItems => 'Tugas';

  @override
  String get wrappedTasksCreated => 'tugas dibuat';

  @override
  String get wrappedCompleted => 'selesai';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% tingkat penyelesaian';
  }

  @override
  String get wrappedYourTopDays => 'Hari terbaikmu';

  @override
  String get wrappedBestMoments => 'Momen terbaik';

  @override
  String get wrappedMyBuddies => 'Teman-temanku';

  @override
  String get wrappedCouldntStopTalkingAbout => 'Tidak bisa berhenti membicarakan';

  @override
  String get wrappedShow => 'ACARA';

  @override
  String get wrappedMovie => 'FILM';

  @override
  String get wrappedBook => 'BUKU';

  @override
  String get wrappedCelebrity => 'SELEBRITI';

  @override
  String get wrappedFood => 'MAKANAN';

  @override
  String get wrappedMovieRecs => 'Rekomendasi film untuk teman';

  @override
  String get wrappedBiggest => 'Terbesar';

  @override
  String get wrappedStruggle => 'Tantangan';

  @override
  String get wrappedButYouPushedThrough => 'Tapi kamu berhasil 💪';

  @override
  String get wrappedWin => 'Kemenangan';

  @override
  String get wrappedYouDidIt => 'Kamu berhasil! 🎉';

  @override
  String get wrappedTopPhrases => 'Top 5 frasa';

  @override
  String get wrappedMins => 'mnt';

  @override
  String get wrappedConvos => 'percakapan';

  @override
  String get wrappedDays => 'hari';

  @override
  String get wrappedMyBuddiesLabel => 'TEMAN-TEMANKU';

  @override
  String get wrappedObsessionsLabel => 'OBSESI';

  @override
  String get wrappedStruggleLabel => 'TANTANGAN';

  @override
  String get wrappedWinLabel => 'KEMENANGAN';

  @override
  String get wrappedTopPhrasesLabel => 'TOP FRASA';

  @override
  String get wrappedLetsHitRewind => 'Mari kita putar balik';

  @override
  String get wrappedGenerateMyWrapped => 'Buat Wrapped Saya';

  @override
  String get wrappedProcessingDefault => 'Memproses...';

  @override
  String get wrappedCreatingYourStory => 'Membuat\ncerita 2025 kamu...';

  @override
  String get wrappedSomethingWentWrong => 'Terjadi\nkesalahan';

  @override
  String get wrappedAnErrorOccurred => 'Terjadi kesalahan';

  @override
  String get wrappedTryAgain => 'Coba Lagi';

  @override
  String get wrappedNoDataAvailable => 'Tidak ada data tersedia';

  @override
  String get wrappedOmiLifeRecap => 'Rekap Hidup Omi';

  @override
  String get wrappedSwipeUpToBegin => 'Geser ke atas untuk mulai';

  @override
  String get wrappedShareText => '2025 saya, diingat oleh Omi ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare => 'Gagal membagikan. Silakan coba lagi.';

  @override
  String get wrappedFailedToStartGeneration => 'Gagal memulai pembuatan. Silakan coba lagi.';

  @override
  String get wrappedStarting => 'Memulai...';

  @override
  String get wrappedShare => 'Bagikan';

  @override
  String get wrappedShareYourWrapped => 'Bagikan Wrapped Kamu';

  @override
  String get wrappedMy2025 => '2025 Saya';

  @override
  String get wrappedRememberedByOmi => 'diingat oleh Omi';

  @override
  String get wrappedMostFunDay => 'Paling Seru';

  @override
  String get wrappedMostProductiveDay => 'Paling Produktif';

  @override
  String get wrappedMostIntenseDay => 'Paling Intens';

  @override
  String get wrappedFunniestMoment => 'Paling Lucu';

  @override
  String get wrappedMostCringeMoment => 'Paling Cringe';

  @override
  String get wrappedMinutesLabel => 'menit';

  @override
  String get wrappedConversationsLabel => 'percakapan';

  @override
  String get wrappedDaysActiveLabel => 'hari aktif';

  @override
  String get wrappedTasksGenerated => 'tugas dibuat';

  @override
  String get wrappedTasksCompleted => 'tugas selesai';

  @override
  String get wrappedTopFivePhrases => 'Top 5 Frasa';

  @override
  String get wrappedAGreatDay => 'Hari yang Hebat';

  @override
  String get wrappedGettingItDone => 'Menyelesaikannya';

  @override
  String get wrappedAChallenge => 'Sebuah Tantangan';

  @override
  String get wrappedAHilariousMoment => 'Momen Lucu';

  @override
  String get wrappedThatAwkwardMoment => 'Momen Canggung Itu';

  @override
  String get wrappedYouHadFunnyMoments => 'Kamu punya momen lucu tahun ini!';

  @override
  String get wrappedWeveAllBeenThere => 'Kita semua pernah di sana!';

  @override
  String get wrappedFriend => 'Teman';

  @override
  String get wrappedYourBuddy => 'Temanmu!';

  @override
  String get wrappedNotMentioned => 'Tidak disebutkan';

  @override
  String get wrappedTheHardPart => 'Bagian Sulit';

  @override
  String get wrappedPersonalGrowth => 'Pertumbuhan Pribadi';

  @override
  String get wrappedFunDay => 'Seru';

  @override
  String get wrappedProductiveDay => 'Produktif';

  @override
  String get wrappedIntenseDay => 'Intens';

  @override
  String get wrappedFunnyMomentTitle => 'Momen Lucu';

  @override
  String get wrappedCringeMomentTitle => 'Momen Cringe';

  @override
  String get wrappedYouTalkedAboutBadge => 'Kamu Berbicara Tentang';

  @override
  String get wrappedCompletedLabel => 'Selesai';

  @override
  String get wrappedMyBuddiesCard => 'Teman-temanku';

  @override
  String get wrappedBuddiesLabel => 'TEMAN';

  @override
  String get wrappedObsessionsLabelUpper => 'OBSESI';

  @override
  String get wrappedStruggleLabelUpper => 'PERJUANGAN';

  @override
  String get wrappedWinLabelUpper => 'KEMENANGAN';

  @override
  String get wrappedTopPhrasesLabelUpper => 'TOP FRASA';

  @override
  String get wrappedYourHeader => 'Harimu';

  @override
  String get wrappedTopDaysHeader => 'Terbaik';

  @override
  String get wrappedYourTopDaysBadge => 'Hari Terbaikmu';

  @override
  String get wrappedBestHeader => 'Terbaik';

  @override
  String get wrappedMomentsHeader => 'Momen';

  @override
  String get wrappedBestMomentsBadge => 'Momen Terbaik';

  @override
  String get wrappedBiggestHeader => 'Terbesar';

  @override
  String get wrappedStruggleHeader => 'Perjuangan';

  @override
  String get wrappedWinHeader => 'Kemenangan';

  @override
  String get wrappedButYouPushedThroughEmoji => 'Tapi kamu berhasil melewatinya 💪';

  @override
  String get wrappedYouDidItEmoji => 'Kamu berhasil! 🎉';

  @override
  String get wrappedHours => 'jam';

  @override
  String get wrappedActions => 'aksi';

  @override
  String get multipleSpeakersDetected => 'Beberapa pembicara terdeteksi';

  @override
  String get multipleSpeakersDescription =>
      'Sepertinya ada beberapa pembicara dalam rekaman. Pastikan Anda berada di tempat yang tenang dan coba lagi.';

  @override
  String get invalidRecordingDetected => 'Rekaman tidak valid terdeteksi';

  @override
  String get notEnoughSpeechDescription =>
      'Tidak cukup ucapan terdeteksi. Silakan berbicara lebih banyak dan coba lagi.';

  @override
  String get speechDurationDescription => 'Pastikan Anda berbicara setidaknya 5 detik dan tidak lebih dari 90.';

  @override
  String get connectionLostDescription => 'Koneksi terputus. Silakan periksa koneksi internet Anda dan coba lagi.';

  @override
  String get howToTakeGoodSample => 'Bagaimana cara membuat sampel yang baik?';

  @override
  String get goodSampleInstructions =>
      '1. Pastikan Anda berada di tempat yang tenang.\n2. Berbicara dengan jelas dan alami.\n3. Pastikan perangkat Anda dalam posisi alaminya di leher Anda.\n\nSetelah dibuat, Anda selalu dapat memperbaikinya atau membuatnya lagi.';

  @override
  String get noDeviceConnectedUseMic => 'Tidak ada perangkat yang terhubung. Mikrofon telepon akan digunakan.';

  @override
  String get doItAgain => 'Lakukan lagi';

  @override
  String get listenToSpeechProfile => 'Dengarkan profil suara saya ➡️';

  @override
  String get recognizingOthers => 'Mengenali orang lain 👀';

  @override
  String get keepGoingGreat => 'Terus lanjutkan, Anda melakukannya dengan baik';

  @override
  String get somethingWentWrongTryAgain => 'Terjadi kesalahan! Silakan coba lagi nanti.';

  @override
  String get uploadingVoiceProfile => 'Mengunggah profil suara Anda....';

  @override
  String get memorizingYourVoice => 'Mengingat suara Anda...';

  @override
  String get personalizingExperience => 'Mempersonalisasi pengalaman Anda...';

  @override
  String get keepSpeakingUntil100 => 'Terus berbicara sampai mencapai 100%.';

  @override
  String get greatJobAlmostThere => 'Kerja bagus, hampir selesai';

  @override
  String get soCloseJustLittleMore => 'Sangat dekat, sedikit lagi';

  @override
  String get notificationFrequency => 'Frekuensi Notifikasi';

  @override
  String get controlNotificationFrequency => 'Kontrol seberapa sering Omi mengirimkan notifikasi proaktif kepada Anda.';

  @override
  String get yourScore => 'Skor Anda';

  @override
  String get dailyScoreBreakdown => 'Rincian Skor Harian';

  @override
  String get todaysScore => 'Skor Hari Ini';

  @override
  String get tasksCompleted => 'Tugas Selesai';

  @override
  String get completionRate => 'Tingkat Penyelesaian';

  @override
  String get howItWorks => 'Cara kerjanya';

  @override
  String get dailyScoreExplanation =>
      'Skor harian Anda berdasarkan penyelesaian tugas. Selesaikan tugas Anda untuk meningkatkan skor!';

  @override
  String get notificationFrequencyDescription =>
      'Kontrol seberapa sering Omi mengirimkan notifikasi dan pengingat proaktif.';

  @override
  String get sliderOff => 'Mati';

  @override
  String get sliderMax => 'Maks.';

  @override
  String summaryGeneratedFor(String date) {
    return 'Ringkasan dibuat untuk $date';
  }

  @override
  String get failedToGenerateSummary => 'Gagal membuat ringkasan. Pastikan Anda memiliki percakapan untuk hari itu.';

  @override
  String get recap => 'Rekap';

  @override
  String deleteQuoted(String name) {
    return 'Hapus \"$name\"';
  }

  @override
  String moveConversationsTo(int count) {
    return 'Pindahkan $count percakapan ke:';
  }

  @override
  String get noFolder => 'Tanpa folder';

  @override
  String get removeFromAllFolders => 'Hapus dari semua folder';

  @override
  String get buildAndShareYourCustomApp => 'Buat dan bagikan aplikasi kustom Anda';

  @override
  String get searchAppsPlaceholder => 'Cari 1500+ Aplikasi';

  @override
  String get filters => 'Filter';

  @override
  String get frequencyOff => 'Mati';

  @override
  String get frequencyMinimal => 'Minimal';

  @override
  String get frequencyLow => 'Rendah';

  @override
  String get frequencyBalanced => 'Seimbang';

  @override
  String get frequencyHigh => 'Tinggi';

  @override
  String get frequencyMaximum => 'Maksimal';

  @override
  String get frequencyDescOff => 'Tidak ada notifikasi proaktif';

  @override
  String get frequencyDescMinimal => 'Hanya pengingat penting';

  @override
  String get frequencyDescLow => 'Hanya pembaruan penting';

  @override
  String get frequencyDescBalanced => 'Pengingat reguler yang bermanfaat';

  @override
  String get frequencyDescHigh => 'Pengecekan sering';

  @override
  String get frequencyDescMaximum => 'Tetap terus terlibat';

  @override
  String get clearChatQuestion => 'Hapus obrolan?';

  @override
  String get syncingMessages => 'Menyinkronkan pesan dengan server...';

  @override
  String get chatAppsTitle => 'Aplikasi Obrolan';

  @override
  String get selectApp => 'Pilih Aplikasi';

  @override
  String get noChatAppsEnabled =>
      'Tidak ada aplikasi obrolan yang diaktifkan.\nKetuk \"Aktifkan Aplikasi\" untuk menambahkan.';

  @override
  String get disable => 'Nonaktifkan';

  @override
  String get photoLibrary => 'Galeri Foto';

  @override
  String get chooseFile => 'Pilih File';

  @override
  String get configureAiPersona => 'Konfigurasikan persona AI Anda';

  @override
  String get connectAiAssistantsToYourData => 'Hubungkan asisten AI ke data Anda';

  @override
  String get oAuth => 'OAuth';

  @override
  String get trackYourGoalsOnHomepage => 'Lacak tujuan pribadi Anda di beranda';

  @override
  String get deleteRecording => 'Hapus Rekaman';

  @override
  String get thisCannotBeUndone => 'Tindakan ini tidak dapat dibatalkan.';

  @override
  String get sdCard => 'Kartu SD';

  @override
  String get fromSd => 'From SD';

  @override
  String get limitless => 'Limitless';

  @override
  String get fastTransfer => 'Transfer Cepat';

  @override
  String get syncingStatus => 'Menyinkronkan';

  @override
  String get failedStatus => 'Gagal';

  @override
  String etaLabel(String time) {
    return 'ETA: $time';
  }

  @override
  String get transferMethod => 'Metode Transfer';

  @override
  String get fast => 'Fast';

  @override
  String get ble => 'BLE';

  @override
  String get phone => 'Phone';

  @override
  String get cancelSync => 'Batalkan Sinkronisasi';

  @override
  String get cancelSyncMessage =>
      'Apakah Anda yakin ingin membatalkan sinkronisasi? Ini akan menghentikan transfer data yang sedang berlangsung.';

  @override
  String get syncCancelled => 'Sync cancelled';

  @override
  String get deleteProcessedFiles => 'Hapus File yang Diproses';

  @override
  String get processedFilesDeleted => 'Processed files deleted';

  @override
  String get wifiEnableFailed => 'Gagal mengaktifkan WiFi pada perangkat. Silakan coba lagi.';

  @override
  String get deviceNoFastTransfer => 'Perangkat tidak mendukung Transfer Cepat';

  @override
  String get enableHotspotMessage => 'Silakan aktifkan hotspot ponsel Anda dan coba lagi.';

  @override
  String get transferStartFailed => 'Gagal memulai transfer. Silakan coba lagi.';

  @override
  String get deviceNotResponding => 'Perangkat tidak merespons. Silakan coba lagi.';

  @override
  String get invalidWifiCredentials => 'Kredensial WiFi tidak valid. Periksa pengaturan hotspot Anda.';

  @override
  String get wifiConnectionFailed => 'Koneksi WiFi gagal. Silakan coba lagi.';

  @override
  String get sdCardProcessing => 'Memproses Kartu SD';

  @override
  String sdCardProcessingMessage(int count) {
    return 'Memproses $count rekaman. File akan dihapus dari kartu SD setelahnya.';
  }

  @override
  String get process => 'Process';

  @override
  String get wifiSyncFailed => 'Sinkronisasi WiFi Gagal';

  @override
  String get processingFailed => 'Pemrosesan Gagal';

  @override
  String get downloadingFromSdCard => 'Mengunduh dari Kartu SD';

  @override
  String processingProgress(int current, int total) {
    return 'Memproses $current/$total';
  }

  @override
  String conversationsCreated(int count) {
    return '$count conversations created';
  }

  @override
  String get internetRequired => 'Diperlukan internet';

  @override
  String get processAudio => 'Process Audio';

  @override
  String get start => 'Start';

  @override
  String get noRecordings => 'No Recordings';

  @override
  String get audioFromOmiWillAppearHere => 'Audio dari perangkat Omi Anda akan muncul di sini';

  @override
  String get deleteProcessed => 'Hapus yang Diproses';

  @override
  String get tryDifferentFilter => 'Try a different filter';

  @override
  String get recordings => 'Rekaman';

  @override
  String get enableRemindersAccess => 'Aktifkan akses Pengingat di Pengaturan untuk menggunakan Pengingat Apple';

  @override
  String todayAtTime(String time) {
    return 'Hari ini pukul $time';
  }

  @override
  String yesterdayAtTime(String time) {
    return 'Kemarin pukul $time';
  }

  @override
  String get lessThanAMinute => 'Kurang dari satu menit';

  @override
  String estimatedMinutes(int count) {
    return '~$count menit';
  }

  @override
  String estimatedHours(int count) {
    return '~$count jam';
  }

  @override
  String estimatedTimeRemaining(String time) {
    return 'Perkiraan: $time tersisa';
  }

  @override
  String get summarizingConversation => 'Meringkas percakapan...\nIni mungkin memerlukan beberapa detik';

  @override
  String get resummarizingConversation => 'Meringkas ulang percakapan...\nIni mungkin memerlukan beberapa detik';

  @override
  String get nothingInterestingRetry => 'Tidak ada yang menarik ditemukan,\ningin mencoba lagi?';

  @override
  String get noSummaryForConversation => 'Tidak ada ringkasan tersedia\nuntuk percakapan ini.';

  @override
  String get unknownLocation => 'Lokasi tidak dikenal';

  @override
  String get couldNotLoadMap => 'Tidak dapat memuat peta';

  @override
  String get triggerConversationIntegration => 'Picu integrasi pembuatan percakapan';

  @override
  String get webhookUrlNotSet => 'URL Webhook belum diatur';

  @override
  String get setWebhookUrlInSettings =>
      'Silakan atur URL webhook di pengaturan pengembang untuk menggunakan fitur ini.';

  @override
  String get sendWebUrl => 'Kirim URL web';

  @override
  String get sendTranscript => 'Kirim transkrip';

  @override
  String get sendSummary => 'Kirim ringkasan';

  @override
  String get debugModeDetected => 'Mode debug terdeteksi';

  @override
  String get performanceReduced => 'Kinerja mungkin berkurang';

  @override
  String autoClosingInSeconds(int seconds) {
    return 'Menutup otomatis dalam $seconds detik';
  }

  @override
  String get modelRequired => 'Model diperlukan';

  @override
  String get downloadWhisperModel => 'Unduh model whisper untuk menggunakan transkripsi di perangkat';

  @override
  String get deviceNotCompatible => 'Perangkat Anda tidak kompatibel dengan transkripsi di perangkat';

  @override
  String get deviceRequirements => 'Perangkat Anda tidak memenuhi persyaratan untuk transkripsi di perangkat.';

  @override
  String get willLikelyCrash => 'Mengaktifkan ini kemungkinan akan menyebabkan aplikasi crash atau freeze.';

  @override
  String get transcriptionSlowerLessAccurate => 'Transkripsi akan jauh lebih lambat dan kurang akurat.';

  @override
  String get proceedAnyway => 'Lanjutkan saja';

  @override
  String get olderDeviceDetected => 'Perangkat Lama Terdeteksi';

  @override
  String get onDeviceSlower => 'Transkripsi di perangkat mungkin lebih lambat di perangkat ini.';

  @override
  String get batteryUsageHigher => 'Penggunaan baterai akan lebih tinggi daripada transkripsi cloud.';

  @override
  String get considerOmiCloud => 'Pertimbangkan untuk menggunakan Omi Cloud untuk kinerja yang lebih baik.';

  @override
  String get highResourceUsage => 'Penggunaan Sumber Daya Tinggi';

  @override
  String get onDeviceIntensive => 'Transkripsi di perangkat membutuhkan komputasi intensif.';

  @override
  String get batteryDrainIncrease => 'Penggunaan baterai akan meningkat secara signifikan.';

  @override
  String get deviceMayWarmUp => 'Perangkat mungkin menjadi panas selama penggunaan yang lama.';

  @override
  String get speedAccuracyLower => 'Kecepatan dan akurasi mungkin lebih rendah daripada model Cloud.';

  @override
  String get cloudProvider => 'Penyedia Cloud';

  @override
  String get premiumMinutesInfo =>
      '1.200 menit premium/bulan. Tab Di Perangkat menawarkan transkripsi gratis tanpa batas.';

  @override
  String get viewUsage => 'Lihat penggunaan';

  @override
  String get localProcessingInfo =>
      'Audio diproses secara lokal. Bekerja offline, lebih privat, tetapi menggunakan lebih banyak baterai.';

  @override
  String get model => 'Model';

  @override
  String get performanceWarning => 'Peringatan Kinerja';

  @override
  String get largeModelWarning =>
      'Model ini besar dan mungkin menyebabkan aplikasi crash atau berjalan sangat lambat di perangkat seluler.\n\n\"small\" atau \"base\" disarankan.';

  @override
  String get usingNativeIosSpeech => 'Menggunakan Pengenalan Suara iOS Asli';

  @override
  String get noModelDownloadRequired =>
      'Mesin ucapan bawaan perangkat Anda akan digunakan. Tidak perlu mengunduh model.';

  @override
  String get modelReady => 'Model Siap';

  @override
  String get redownload => 'Unduh Ulang';

  @override
  String get doNotCloseApp => 'Jangan tutup aplikasi.';

  @override
  String get downloading => 'Mengunduh...';

  @override
  String get downloadModel => 'Unduh model';

  @override
  String estimatedSize(String size) {
    return 'Perkiraan Ukuran: ~$size MB';
  }

  @override
  String availableSpace(String space) {
    return 'Ruang Tersedia: $space';
  }

  @override
  String get notEnoughSpace => 'Peringatan: Ruang tidak cukup!';

  @override
  String get download => 'Unduh';

  @override
  String downloadError(String error) {
    return 'Error unduhan: $error';
  }

  @override
  String get cancelled => 'Dibatalkan';

  @override
  String get deviceNotCompatibleTitle => 'Perangkat Tidak Kompatibel';

  @override
  String get deviceNotMeetRequirements => 'Perangkat Anda tidak memenuhi persyaratan untuk transkripsi di perangkat.';

  @override
  String get transcriptionSlowerOnDevice => 'Transkripsi di perangkat mungkin lebih lambat di perangkat ini.';

  @override
  String get computationallyIntensive => 'Transkripsi di perangkat memerlukan komputasi intensif.';

  @override
  String get batteryDrainSignificantly => 'Pengurasan baterai akan meningkat secara signifikan.';

  @override
  String get premiumMinutesMonth =>
      '1.200 menit premium/bulan. Tab Di Perangkat menawarkan transkripsi gratis tanpa batas. ';

  @override
  String get audioProcessedLocally =>
      'Audio diproses secara lokal. Bekerja offline, lebih privat, tetapi menggunakan lebih banyak baterai.';

  @override
  String get languageLabel => 'Bahasa';

  @override
  String get modelLabel => 'Model';

  @override
  String get modelTooLargeWarning =>
      'Model ini besar dan dapat menyebabkan aplikasi crash atau berjalan sangat lambat di perangkat seluler.\n\nsmall atau base disarankan.';

  @override
  String get nativeEngineNoDownload => 'Mesin suara asli perangkat Anda akan digunakan. Tidak perlu mengunduh model.';

  @override
  String modelReadyWithName(String model) {
    return 'Model Siap ($model)';
  }

  @override
  String get reDownload => 'Unduh ulang';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return 'Mengunduh $model: $received / $total MB';
  }

  @override
  String preparingModel(String model) {
    return 'Menyiapkan $model...';
  }

  @override
  String downloadErrorWithMessage(String error) {
    return 'Error unduhan: $error';
  }

  @override
  String estimatedSizeWithValue(String size) {
    return 'Perkiraan Ukuran: ~$size MB';
  }

  @override
  String availableSpaceWithValue(String space) {
    return 'Ruang Tersedia: $space';
  }

  @override
  String get omiTranscriptionOptimized =>
      'Transkripsi langsung bawaan Omi dioptimalkan untuk percakapan real-time dengan deteksi pembicara otomatis dan diarisasi.';

  @override
  String get reset => 'Reset';

  @override
  String get useTemplateFrom => 'Gunakan template dari';

  @override
  String get selectProviderTemplate => 'Pilih template penyedia...';

  @override
  String get quicklyPopulateResponse => 'Isi cepat dengan format respons penyedia yang dikenal';

  @override
  String get quicklyPopulateRequest => 'Isi cepat dengan format permintaan penyedia yang dikenal';

  @override
  String get invalidJsonError => 'JSON Tidak Valid';

  @override
  String downloadModelWithName(String model) {
    return 'Unduh Model ($model)';
  }

  @override
  String modelNameWithFile(String model) {
    return 'Model: $model';
  }

  @override
  String get device => 'Perangkat';

  @override
  String get chatAssistantsTitle => 'Asisten Obrolan';

  @override
  String get permissionReadConversations => 'Baca Percakapan';

  @override
  String get permissionReadMemories => 'Baca Kenangan';

  @override
  String get permissionReadTasks => 'Baca Tugas';

  @override
  String get permissionCreateConversations => 'Buat Percakapan';

  @override
  String get permissionCreateMemories => 'Buat Kenangan';

  @override
  String get permissionTypeAccess => 'Akses';

  @override
  String get permissionTypeCreate => 'Buat';

  @override
  String get permissionTypeTrigger => 'Pemicu';

  @override
  String get permissionDescReadConversations => 'Aplikasi ini dapat mengakses percakapan Anda.';

  @override
  String get permissionDescReadMemories => 'Aplikasi ini dapat mengakses kenangan Anda.';

  @override
  String get permissionDescReadTasks => 'Aplikasi ini dapat mengakses tugas Anda.';

  @override
  String get permissionDescCreateConversations => 'Aplikasi ini dapat membuat percakapan baru.';

  @override
  String get permissionDescCreateMemories => 'Aplikasi ini dapat membuat kenangan baru.';

  @override
  String get realtimeListening => 'Mendengarkan Realtime';

  @override
  String get setupCompleted => 'Selesai';

  @override
  String get pleaseSelectRating => 'Silakan pilih peringkat';

  @override
  String get writeReviewOptional => 'Tulis ulasan (opsional)';

  @override
  String get setupQuestionsIntro => 'Beberapa pertanyaan singkat untuk membantu kami mempersonalisasi pengalaman Anda';

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
  String get professionEntrepreneur => 'Pengusaha';

  @override
  String get professionSoftwareEngineer => 'Insinyur Perangkat Lunak';

  @override
  String get professionProductManager => 'Manajer Produk';

  @override
  String get professionExecutive => 'Executive';

  @override
  String get professionSales => 'Sales';

  @override
  String get professionStudent => 'Student';

  @override
  String get usageAtWork => 'Di tempat kerja';

  @override
  String get usageIrlEvents => 'Acara IRL';

  @override
  String get usageOnline => 'Online';

  @override
  String get usageSocialSettings => 'In Social Settings';

  @override
  String get usageEverywhere => 'Everywhere';

  @override
  String get customBackendUrlTitle => 'URL Backend Kustom';

  @override
  String get backendUrlLabel => 'URL Backend';

  @override
  String get saveUrlButton => 'Simpan URL';

  @override
  String get enterBackendUrlError => 'Masukkan URL backend';

  @override
  String get urlMustEndWithSlashError => 'URL harus diakhiri dengan \"/\"';

  @override
  String get invalidUrlError => 'Masukkan URL yang valid';

  @override
  String get backendUrlSavedSuccess => 'URL backend berhasil disimpan!';

  @override
  String get signInTitle => 'Masuk';

  @override
  String get signInButton => 'Masuk';

  @override
  String get enterEmailError => 'Masukkan email Anda';

  @override
  String get invalidEmailError => 'Masukkan email yang valid';

  @override
  String get enterPasswordError => 'Masukkan kata sandi Anda';

  @override
  String get passwordMinLengthError => 'Kata sandi harus minimal 8 karakter';

  @override
  String get signInSuccess => 'Berhasil masuk!';

  @override
  String get alreadyHaveAccountLogin => 'Sudah punya akun? Masuk';

  @override
  String get emailLabel => 'Email';

  @override
  String get passwordLabel => 'Kata sandi';

  @override
  String get createAccountTitle => 'Buat Akun';

  @override
  String get nameLabel => 'Nama';

  @override
  String get repeatPasswordLabel => 'Ulangi Kata Sandi';

  @override
  String get signUpButton => 'Daftar';

  @override
  String get enterNameError => 'Masukkan nama Anda';

  @override
  String get passwordsDoNotMatch => 'Kata sandi tidak cocok';

  @override
  String get signUpSuccess => 'Pendaftaran berhasil!';

  @override
  String get loadingKnowledgeGraph => 'Memuat Graf Pengetahuan...';

  @override
  String get noKnowledgeGraphYet => 'Belum ada graf pengetahuan';

  @override
  String get buildingKnowledgeGraphFromMemories => 'Membangun graf pengetahuan dari kenangan...';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'Graf pengetahuan Anda akan dibangun secara otomatis saat Anda membuat kenangan baru.';

  @override
  String get buildGraphButton => 'Bangun Graf';

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
  String get submitReply => 'Kirim Balasan';

  @override
  String get editYourReply => 'Edit Balasan Anda';

  @override
  String get replyToReview => 'Balas Ulasan';

  @override
  String get rateAndReviewThisApp => 'Beri peringkat dan ulasan aplikasi ini';

  @override
  String get noChangesInReview => 'Tidak ada perubahan pada ulasan untuk diperbarui.';

  @override
  String get cantRateWithoutInternet => 'Tidak dapat menilai aplikasi tanpa koneksi internet.';

  @override
  String get appAnalytics => 'Analitik Aplikasi';

  @override
  String get learnMoreLink => 'pelajari lebih lanjut';

  @override
  String get moneyEarned => 'Uang yang diperoleh';

  @override
  String get writeYourReply => 'Tulis balasan Anda...';

  @override
  String get replySentSuccessfully => 'Balasan berhasil dikirim';

  @override
  String failedToSendReply(String error) {
    return 'Gagal mengirim balasan: $error';
  }

  @override
  String get send => 'Kirim';

  @override
  String starFilter(int count) {
    return '$count Bintang';
  }

  @override
  String get noReviewsFound => 'Tidak Ada Ulasan Ditemukan';

  @override
  String get editReply => 'Edit Balasan';

  @override
  String get reply => 'Balas';

  @override
  String starFilterLabel(int count) {
    return '$count bintang';
  }

  @override
  String get sharePublicLink => 'Share Public Link';

  @override
  String get makePersonaPublic => 'Make Persona Public';

  @override
  String get connectedKnowledgeData => 'Connected Knowledge Data';

  @override
  String get enterName => 'Masukkan nama';

  @override
  String get disconnectTwitter => 'Disconnect Twitter';

  @override
  String get disconnectTwitterConfirmation =>
      'Apakah Anda yakin ingin memutuskan akun Twitter Anda? Persona Anda tidak akan lagi memiliki akses ke data Twitter Anda.';

  @override
  String get getOmiDeviceDescription => 'Create a more accurate clone with your personal conversations';

  @override
  String get getOmi => 'Dapatkan Omi';

  @override
  String get iHaveOmiDevice => 'I have Omi device';

  @override
  String get goal => 'TUJUAN';

  @override
  String get tapToTrackThisGoal => 'Ketuk untuk melacak tujuan ini';

  @override
  String get tapToSetAGoal => 'Ketuk untuk menetapkan tujuan';

  @override
  String get processedConversations => 'Percakapan yang Diproses';

  @override
  String get updatedConversations => 'Percakapan yang Diperbarui';

  @override
  String get newConversations => 'Percakapan Baru';

  @override
  String get summaryTemplate => 'Template Ringkasan';

  @override
  String get suggestedTemplates => 'Template yang Disarankan';

  @override
  String get otherTemplates => 'Template Lainnya';

  @override
  String get availableTemplates => 'Template yang Tersedia';

  @override
  String get getCreative => 'Jadilah Kreatif';

  @override
  String get defaultLabel => 'Default';

  @override
  String get lastUsedLabel => 'Terakhir Digunakan';

  @override
  String get setDefaultApp => 'Atur Aplikasi Default';

  @override
  String setDefaultAppContent(String appName) {
    return 'Atur $appName sebagai aplikasi ringkasan default Anda?\\n\\nAplikasi ini akan otomatis digunakan untuk semua ringkasan percakapan di masa depan.';
  }

  @override
  String get setDefaultButton => 'Atur Default';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName diatur sebagai aplikasi ringkasan default';
  }

  @override
  String get createCustomTemplate => 'Buat Template Kustom';

  @override
  String get allTemplates => 'Semua Template';

  @override
  String failedToInstallApp(String appName) {
    return 'Gagal menginstal $appName. Silakan coba lagi.';
  }

  @override
  String errorInstallingApp(String appName, String error) {
    return 'Error menginstal $appName: $error';
  }

  @override
  String tagSpeaker(int speakerId) {
    return 'Tandai Pembicara $speakerId';
  }

  @override
  String get personNameAlreadyExists => 'A person with this name already exists.';

  @override
  String get selectYouFromList => 'Pilih Anda dari daftar';

  @override
  String get enterPersonsName => 'Masukkan Nama Orang';

  @override
  String get addPerson => 'Tambah Orang';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'Tandai segmen lain dari pembicara ini ($selected/$total)';
  }

  @override
  String get tagOtherSegments => 'Tandai segmen lain';

  @override
  String get managePeople => 'Kelola Orang';

  @override
  String get shareViaSms => 'Bagikan via SMS';

  @override
  String get selectContactsToShareSummary => 'Pilih kontak untuk membagikan ringkasan percakapan Anda';

  @override
  String get searchContactsHint => 'Cari kontak...';

  @override
  String contactsSelectedCount(int count) {
    return '$count dipilih';
  }

  @override
  String get clearAllSelection => 'Hapus semua';

  @override
  String get selectContactsToShare => 'Pilih kontak untuk dibagikan';

  @override
  String shareWithContactCount(int count) {
    return 'Bagikan dengan $count kontak';
  }

  @override
  String shareWithContactsCount(int count) {
    return 'Bagikan dengan $count kontak';
  }

  @override
  String get contactsPermissionRequired => 'Izin kontak diperlukan';

  @override
  String get contactsPermissionRequiredForSms => 'Izin kontak diperlukan untuk berbagi melalui SMS';

  @override
  String get grantContactsPermissionForSms => 'Harap berikan izin kontak untuk berbagi melalui SMS';

  @override
  String get noContactsWithPhoneNumbers => 'Tidak ditemukan kontak dengan nomor telepon';

  @override
  String get noContactsMatchSearch => 'Tidak ada kontak yang cocok dengan pencarian Anda';

  @override
  String get failedToLoadContacts => 'Gagal memuat kontak';

  @override
  String get failedToPrepareConversationForSharing => 'Gagal menyiapkan percakapan untuk dibagikan. Silakan coba lagi.';

  @override
  String get couldNotOpenSmsApp => 'Tidak dapat membuka aplikasi SMS. Silakan coba lagi.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'Ini yang baru saja kita bahas: $link';
  }

  @override
  String get wifiSync => 'Sinkronisasi WiFi';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item disalin ke papan klip';
  }

  @override
  String get wifiConnectionFailedTitle => 'Connection Failed';

  @override
  String connectingToDeviceName(String deviceName) {
    return 'Connecting to $deviceName';
  }

  @override
  String enableDeviceWifi(String deviceName) {
    return 'Aktifkan WiFi $deviceName';
  }

  @override
  String connectToDeviceName(String deviceName) {
    return 'Hubungkan ke $deviceName';
  }

  @override
  String get recordingDetails => 'Detail Rekaman';

  @override
  String get storageLocationSdCard => 'Kartu SD';

  @override
  String get storageLocationLimitlessPendant => 'Limitless Pendant';

  @override
  String get storageLocationPhone => 'Ponsel';

  @override
  String get storageLocationPhoneMemory => 'Phone (Memory)';

  @override
  String storedOnDevice(String deviceName) {
    return 'Stored on $deviceName';
  }

  @override
  String get transferring => 'Mentransfer...';

  @override
  String get transferRequired => 'Transfer Diperlukan';

  @override
  String get downloadingAudioFromSdCard => 'Mengunduh audio dari kartu SD perangkat Anda';

  @override
  String get transferRequiredDescription => 'Rekaman ini perlu ditransfer ke ponsel Anda sebelum dapat diputar.';

  @override
  String get cancelTransfer => 'Batalkan Transfer';

  @override
  String get transferToPhone => 'Transfer ke Ponsel';

  @override
  String get privateAndSecureOnDevice => 'Private & secure on your device';

  @override
  String get recordingInfo => 'Info Rekaman';

  @override
  String get transferInProgress => 'Transfer sedang berlangsung...';

  @override
  String get shareRecording => 'Share Recording';

  @override
  String get deleteRecordingConfirmation =>
      'Apakah Anda yakin ingin menghapus rekaman ini secara permanen? Tindakan ini tidak dapat dibatalkan.';

  @override
  String get recordingIdLabel => 'ID Rekaman';

  @override
  String get dateTimeLabel => 'Date & Time';

  @override
  String get durationLabel => 'Duration';

  @override
  String get audioFormatLabel => 'Format Audio';

  @override
  String get storageLocationLabel => 'Lokasi Penyimpanan';

  @override
  String get estimatedSizeLabel => 'Estimated Size';

  @override
  String get deviceModelLabel => 'Model Perangkat';

  @override
  String get deviceIdLabel => 'ID Perangkat';

  @override
  String get statusLabel => 'Status';

  @override
  String get statusProcessed => 'Processed';

  @override
  String get statusUnprocessed => 'Unprocessed';

  @override
  String get switchedToFastTransfer => 'Beralih ke Transfer Cepat';

  @override
  String get transferCompleteMessage => 'Transfer selesai. Anda sekarang dapat memutar rekaman ini.';

  @override
  String transferFailedMessage(String error) {
    return 'Transfer gagal: $error';
  }

  @override
  String get transferCancelled => 'Transfer dibatalkan';

  @override
  String get fastTransferEnabled => 'Transfer Cepat diaktifkan';

  @override
  String get bluetoothSyncEnabled => 'Sinkronisasi Bluetooth diaktifkan';

  @override
  String get enableFastTransfer => 'Aktifkan Transfer Cepat';

  @override
  String get fastTransferDescription =>
      'Transfer Cepat menggunakan WiFi untuk kecepatan ~5x lebih cepat. Ponsel Anda akan terhubung sementara ke jaringan WiFi perangkat Omi selama transfer.';

  @override
  String get internetAccessPausedDuringTransfer => 'Akses internet dijeda selama transfer';

  @override
  String get chooseTransferMethodDescription => 'Pilih cara rekaman ditransfer dari perangkat Omi ke ponsel Anda.';

  @override
  String get wifiSpeed => '~150 KB/s via WiFi';

  @override
  String get fiveTimesFaster => '5X LEBIH CEPAT';

  @override
  String get fastTransferMethodDescription =>
      'Membuat koneksi WiFi langsung ke perangkat Omi Anda. Ponsel Anda sementara terputus dari WiFi biasa selama transfer.';

  @override
  String get bluetooth => 'Bluetooth';

  @override
  String get bleSpeed => '~30 KB/s via BLE';

  @override
  String get bluetoothMethodDescription =>
      'Menggunakan koneksi Bluetooth Low Energy standar. Lebih lambat tetapi tidak mempengaruhi koneksi WiFi Anda.';

  @override
  String get selected => 'Dipilih';

  @override
  String get selectOption => 'Pilih';

  @override
  String get lowBatteryAlertTitle => 'Peringatan Baterai Lemah';

  @override
  String get lowBatteryAlertBody => 'Baterai perangkat Anda lemah. Saatnya mengisi ulang! 🔋';

  @override
  String get deviceDisconnectedNotificationTitle => 'Perangkat Omi Anda Terputus';

  @override
  String get deviceDisconnectedNotificationBody => 'Silakan sambungkan kembali untuk terus menggunakan Omi.';

  @override
  String get firmwareUpdateAvailable => 'Pembaruan Firmware Tersedia';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'Pembaruan firmware baru ($version) tersedia untuk perangkat Omi Anda. Apakah Anda ingin memperbarui sekarang?';
  }

  @override
  String get later => 'Nanti';

  @override
  String get appDeletedSuccessfully => 'Aplikasi berhasil dihapus';

  @override
  String get appDeleteFailed => 'Gagal menghapus aplikasi. Silakan coba lagi nanti.';

  @override
  String get appVisibilityChangedSuccessfully =>
      'Visibilitas aplikasi berhasil diubah. Mungkin memerlukan beberapa menit untuk diterapkan.';

  @override
  String get errorActivatingAppIntegration =>
      'Kesalahan saat mengaktifkan aplikasi. Jika ini adalah aplikasi integrasi, pastikan pengaturan sudah selesai.';

  @override
  String get errorUpdatingAppStatus => 'Terjadi kesalahan saat memperbarui status aplikasi.';

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
  String get migrationErrorOccurred => 'Terjadi kesalahan selama migrasi. Silakan coba lagi.';

  @override
  String get migrationComplete => 'Migrasi selesai.';

  @override
  String dataProtectedWithSettings(String level) {
    return 'Your data is now protected with the new $level settings.';
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
  String get importantConversationTitle => 'Percakapan Penting';

  @override
  String get importantConversationBody =>
      'Anda baru saja melakukan percakapan penting. Ketuk untuk membagikan ringkasan.';

  @override
  String get templateName => 'Nama Template';

  @override
  String get templateNameHint => 'Masukkan nama untuk template Anda';

  @override
  String get nameMustBeAtLeast3Characters => 'Nama harus minimal 3 karakter';

  @override
  String get conversationPromptHint => 'Masukkan prompt percakapan';

  @override
  String get pleaseEnterAppPrompt => 'Silakan masukkan prompt aplikasi';

  @override
  String get promptMustBeAtLeast10Characters => 'Prompt harus minimal 10 karakter';

  @override
  String get anyoneCanDiscoverTemplate => 'Siapa saja dapat menemukan template';

  @override
  String get onlyYouCanUseTemplate => 'Hanya Anda yang dapat menggunakan template';

  @override
  String get generatingDescription => 'Menghasilkan deskripsi...';

  @override
  String get creatingAppIcon => 'Membuat ikon aplikasi...';

  @override
  String get installingApp => 'Menginstal aplikasi...';

  @override
  String get appCreatedAndInstalled => 'Aplikasi dibuat dan diinstal';

  @override
  String get appCreatedSuccessfully => 'Aplikasi berhasil dibuat';

  @override
  String get failedToCreateApp => 'Gagal membuat aplikasi';

  @override
  String get addAppSelectCoreCapability => 'Pilih kemampuan inti';

  @override
  String get addAppSelectPaymentPlan => 'Pilih paket pembayaran';

  @override
  String get addAppSelectCapability => 'Pilih kemampuan';

  @override
  String get addAppSelectLogo => 'Pilih logo';

  @override
  String get addAppEnterChatPrompt => 'Masukkan prompt chat';

  @override
  String get addAppEnterConversationPrompt => 'Masukkan prompt percakapan';

  @override
  String get addAppSelectTriggerEvent => 'Pilih event pemicu';

  @override
  String get addAppEnterWebhookUrl => 'Masukkan URL webhook';

  @override
  String get addAppSelectCategory => 'Pilih kategori';

  @override
  String get addAppFillRequiredFields => 'Harap isi semua bidang yang diperlukan';

  @override
  String get addAppUpdatedSuccess => 'Aplikasi berhasil diperbarui';

  @override
  String get addAppUpdateFailed => 'Gagal memperbarui aplikasi';

  @override
  String get addAppSubmittedSuccess => 'Aplikasi berhasil dikirim';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'Kesalahan membuka pemilih file';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'Kesalahan memilih gambar';
  }

  @override
  String get addAppPhotosPermissionDenied => 'Izin foto ditolak';

  @override
  String get addAppErrorSelectingImageRetry => 'Kesalahan memilih gambar. Silakan coba lagi.';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'Kesalahan memilih thumbnail';
  }

  @override
  String get addAppErrorSelectingThumbnailRetry => 'Kesalahan memilih thumbnail. Silakan coba lagi.';

  @override
  String get addAppCapabilityConflictWithPersona => 'Kemampuan ini berkonflik dengan persona';

  @override
  String get addAppPersonaConflictWithCapabilities => 'Persona berkonflik dengan kemampuan yang dipilih';

  @override
  String get personaTwitterHandleNotFound => 'Username Twitter tidak ditemukan';

  @override
  String get personaTwitterHandleSuspended => 'Username Twitter ditangguhkan';

  @override
  String get personaFailedToVerifyTwitter => 'Gagal memverifikasi Twitter';

  @override
  String get personaFailedToFetch => 'Gagal mengambil persona';

  @override
  String get personaFailedToCreate => 'Gagal membuat persona';

  @override
  String get personaConnectKnowledgeSource => 'Hubungkan sumber pengetahuan';

  @override
  String get personaUpdatedSuccessfully => 'Persona berhasil diperbarui';

  @override
  String get personaFailedToUpdate => 'Gagal memperbarui persona';

  @override
  String get personaPleaseSelectImage => 'Silakan pilih gambar';

  @override
  String get personaFailedToCreateTryLater => 'Gagal membuat persona. Silakan coba lagi nanti.';

  @override
  String personaFailedToCreateWithError(String error) {
    return 'Gagal membuat persona: $error';
  }

  @override
  String get personaFailedToEnable => 'Gagal mengaktifkan persona';

  @override
  String personaErrorEnablingWithError(String error) {
    return 'Kesalahan mengaktifkan persona: $error';
  }

  @override
  String get paymentFailedToFetchCountries => 'Gagal mengambil daftar negara';

  @override
  String get paymentFailedToSetDefault => 'Gagal mengatur metode pembayaran default';

  @override
  String get paymentFailedToSavePaypal => 'Gagal menyimpan PayPal';

  @override
  String get paypalEmailHint => 'Email PayPal';

  @override
  String get paypalMeLinkHint => 'Link PayPal.me';

  @override
  String get paymentMethodStripe => 'Stripe';

  @override
  String get paymentMethodPayPal => 'PayPal';

  @override
  String get paymentStatusActive => 'Aktif';

  @override
  String get paymentStatusConnected => 'Terhubung';

  @override
  String get paymentStatusNotConnected => 'Tidak Terhubung';

  @override
  String get paymentAppCost => 'Biaya Aplikasi';

  @override
  String get paymentEnterValidAmount => 'Masukkan jumlah yang valid';

  @override
  String get paymentEnterAmountGreaterThanZero => 'Masukkan jumlah lebih dari nol';

  @override
  String get paymentPlan => 'Paket Pembayaran';

  @override
  String get paymentNoneSelected => 'Tidak ada yang dipilih';

  @override
  String get aiGenPleaseEnterDescription => 'Silakan masukkan deskripsi';

  @override
  String get aiGenCreatingAppIcon => 'Membuat ikon aplikasi...';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'Terjadi kesalahan: $message';
  }

  @override
  String get aiGenAppCreatedSuccessfully => 'Aplikasi berhasil dibuat';

  @override
  String get aiGenFailedToCreateApp => 'Gagal membuat aplikasi';

  @override
  String get aiGenErrorWhileCreatingApp => 'Kesalahan saat membuat aplikasi';

  @override
  String get aiGenFailedToGenerateApp => 'Gagal menghasilkan aplikasi';

  @override
  String get aiGenFailedToRegenerateIcon => 'Gagal menghasilkan ulang ikon';

  @override
  String get aiGenPleaseGenerateAppFirst => 'Silakan buat aplikasi terlebih dahulu';

  @override
  String get xHandleTitle => 'Apa username X Anda?';

  @override
  String get xHandleDescription => 'Masukkan username X (Twitter) Anda untuk menghubungkan profil sosial Anda';

  @override
  String get xHandleHint => '@nikshevchenko';

  @override
  String get xHandlePleaseEnter => 'Silakan masukkan username X Anda';

  @override
  String get xHandlePleaseEnterValid => 'Silakan masukkan username X yang valid';

  @override
  String get nextButton => 'Selanjutnya';

  @override
  String get connectOmiDevice => 'Hubungkan Perangkat Omi';

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'Anda dijadwalkan untuk beralih ke paket $title pada periode penagihan berikutnya.';
  }

  @override
  String get planUpgradeScheduledMessage => 'Upgrade paket Anda dijadwalkan untuk periode penagihan berikutnya.';

  @override
  String get couldNotSchedulePlanChange => 'Tidak dapat menjadwalkan perubahan paket. Silakan coba lagi.';

  @override
  String get subscriptionReactivatedDefault => 'Langganan Anda telah diaktifkan kembali.';

  @override
  String get subscriptionSuccessfulCharged => 'Langganan berhasil diproses.';

  @override
  String get couldNotProcessSubscription => 'Tidak dapat memproses langganan. Silakan coba lagi.';

  @override
  String get couldNotLaunchUpgradePage => 'Tidak dapat membuka halaman upgrade. Silakan coba lagi.';

  @override
  String get transcriptionJsonPlaceholder => 'Placeholder JSON transkripsi';

  @override
  String get transcriptionSourceOmi => 'Sumber Transkripsi: Omi';

  @override
  String get pricePlaceholder => 'Harga';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'Kesalahan membuka pemilih file';
  }

  @override
  String importErrorGeneric(String error) {
    return 'Kesalahan mengimpor file';
  }

  @override
  String get mergeConversationsSuccessTitle => 'Percakapan Digabungkan';

  @override
  String mergeConversationsSuccessBody(int count) {
    return 'Percakapan Anda telah berhasil digabungkan';
  }

  @override
  String get dailyReflectionNotificationTitle => 'Refleksi Harian';

  @override
  String get dailyReflectionNotificationBody => 'Saatnya untuk refleksi harian Anda';

  @override
  String get actionItemReminderTitle => 'Pengingat Item Tindakan';

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return 'Perangkat Terputus';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'Perangkat Omi Anda telah terputus';
  }

  @override
  String get onboardingSignIn => 'Masuk';

  @override
  String get onboardingYourName => 'Nama Anda';

  @override
  String get onboardingLanguage => 'Bahasa';

  @override
  String get onboardingPermissions => 'Izin';

  @override
  String get onboardingComplete => 'Selesai';

  @override
  String get onboardingWelcomeToOmi => 'Selamat datang di Omi';

  @override
  String get onboardingTellUsAboutYourself => 'Ceritakan tentang diri Anda';

  @override
  String get onboardingChooseYourPreference => 'Pilih preferensi Anda';

  @override
  String get onboardingGrantRequiredAccess => 'Berikan akses yang diperlukan';

  @override
  String get onboardingYoureAllSet => 'Anda siap';

  @override
  String get searchTranscriptOrSummary => 'Cari transkrip atau ringkasan...';

  @override
  String get myGoal => 'Tujuan Saya';

  @override
  String get appNotAvailable => 'Aplikasi tidak tersedia';

  @override
  String get failedToConnectTodoist => 'Gagal terhubung ke Todoist';

  @override
  String get failedToConnectAsana => 'Gagal terhubung ke Asana';

  @override
  String get failedToConnectGoogleTasks => 'Gagal terhubung ke Google Tasks';

  @override
  String get failedToConnectClickUp => 'Gagal terhubung ke ClickUp';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return 'Gagal terhubung ke layanan: $error';
  }

  @override
  String get successfullyConnectedTodoist => 'Berhasil terhubung ke Todoist';

  @override
  String get failedToConnectTodoistRetry => 'Gagal terhubung ke Todoist. Silakan coba lagi.';

  @override
  String get successfullyConnectedAsana => 'Berhasil terhubung ke Asana';

  @override
  String get failedToConnectAsanaRetry => 'Gagal terhubung ke Asana. Silakan coba lagi.';

  @override
  String get successfullyConnectedGoogleTasks => 'Berhasil terhubung ke Google Tasks';

  @override
  String get failedToConnectGoogleTasksRetry => 'Gagal terhubung ke Google Tasks. Silakan coba lagi.';

  @override
  String get successfullyConnectedClickUp => 'Berhasil terhubung ke ClickUp';

  @override
  String get failedToConnectClickUpRetry => 'Gagal terhubung ke ClickUp. Silakan coba lagi.';

  @override
  String get successfullyConnectedNotion => 'Berhasil terhubung ke Notion';

  @override
  String get failedToRefreshNotionStatus => 'Gagal memperbarui status Notion';

  @override
  String get successfullyConnectedGoogle => 'Berhasil terhubung ke Google';

  @override
  String get failedToRefreshGoogleStatus => 'Gagal memperbarui status Google';

  @override
  String get successfullyConnectedWhoop => 'Berhasil terhubung ke Whoop';

  @override
  String get failedToRefreshWhoopStatus => 'Gagal memperbarui status Whoop';

  @override
  String get successfullyConnectedGitHub => 'Berhasil terhubung ke GitHub';

  @override
  String get failedToRefreshGitHubStatus => 'Gagal memperbarui status GitHub';

  @override
  String get authFailedToSignInWithGoogle => 'Gagal masuk dengan Google. Silakan coba lagi.';

  @override
  String get authenticationFailed => 'Autentikasi gagal. Silakan coba lagi.';

  @override
  String get authFailedToSignInWithApple => 'Gagal masuk dengan Apple. Silakan coba lagi.';

  @override
  String get authFailedToRetrieveToken => 'Gagal mengambil token. Silakan coba lagi.';

  @override
  String get authUnexpectedErrorFirebase =>
      'Terjadi kesalahan tak terduga saat masuk dengan Firebase. Silakan coba lagi.';

  @override
  String get authUnexpectedError => 'Terjadi kesalahan tak terduga saat masuk. Silakan coba lagi.';

  @override
  String get authFailedToLinkGoogle => 'Gagal menautkan akun Google. Silakan coba lagi.';

  @override
  String get authFailedToLinkApple => 'Gagal menautkan akun Apple. Silakan coba lagi.';

  @override
  String get onboardingBluetoothRequired => 'Bluetooth diperlukan untuk menghubungkan perangkat Omi Anda';

  @override
  String get onboardingBluetoothDeniedSystemPrefs => 'Izin Bluetooth ditolak. Harap aktifkan di Preferensi Sistem.';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'Status Bluetooth: $status. Harap periksa Preferensi Sistem.';
  }

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'Gagal memeriksa status Bluetooth: $error';
  }

  @override
  String get onboardingNotificationDeniedSystemPrefs => 'Izin notifikasi ditolak. Harap aktifkan di Preferensi Sistem.';

  @override
  String get onboardingNotificationDeniedNotifications =>
      'Izin notifikasi ditolak. Harap aktifkan di pengaturan Notifikasi.';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return 'Status notifikasi: $status. Harap periksa Preferensi Sistem.';
  }

  @override
  String onboardingFailedCheckNotification(String error) {
    return 'Gagal memeriksa status notifikasi: $error';
  }

  @override
  String get onboardingLocationGrantInSettings => 'Harap berikan izin lokasi di pengaturan untuk melanjutkan.';

  @override
  String get onboardingMicrophoneRequired => 'Mikrofon diperlukan untuk merekam audio';

  @override
  String get onboardingMicrophoneDenied => 'Izin mikrofon ditolak. Harap aktifkan di Preferensi Sistem.';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'Status mikrofon: $status. Harap periksa Preferensi Sistem.';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'Gagal memeriksa status mikrofon: $error';
  }

  @override
  String get onboardingScreenCaptureRequired => 'Perekaman layar diperlukan untuk merekam layar';

  @override
  String get onboardingScreenCaptureDenied => 'Izin perekaman layar ditolak. Harap aktifkan di Preferensi Sistem.';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return 'Status perekaman layar: $status. Harap periksa Preferensi Sistem.';
  }

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return 'Gagal memeriksa status perekaman layar: $error';
  }

  @override
  String get onboardingAccessibilityRequired => 'Aksesibilitas diperlukan untuk fitur lanjutan';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'Status aksesibilitas: $status. Harap periksa Preferensi Sistem.';
  }

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'Gagal memeriksa status aksesibilitas: $error';
  }

  @override
  String get msgCameraNotAvailable => 'Kamera tidak tersedia';

  @override
  String get msgCameraPermissionDenied => 'Izin kamera ditolak';

  @override
  String msgCameraAccessError(String error) {
    return 'Kesalahan akses kamera: $error';
  }

  @override
  String get msgPhotoError => 'Kesalahan mengambil foto';

  @override
  String get msgMaxImagesLimit => 'Maksimal 4 gambar dapat dipilih';

  @override
  String msgFilePickerError(String error) {
    return 'Kesalahan pemilih file: $error';
  }

  @override
  String msgSelectImagesError(String error) {
    return 'Kesalahan memilih gambar: $error';
  }

  @override
  String get msgPhotosPermissionDenied => 'Izin foto ditolak';

  @override
  String get msgSelectImagesGenericError => 'Kesalahan memilih gambar';

  @override
  String get msgMaxFilesLimit => 'Maksimal 4 file dapat dipilih';

  @override
  String msgSelectFilesError(String error) {
    return 'Kesalahan memilih file: $error';
  }

  @override
  String get msgSelectFilesGenericError => 'Kesalahan memilih file';

  @override
  String get msgUploadFileFailed => 'Gagal mengunggah file';

  @override
  String get msgReadingMemories => 'Membaca memori...';

  @override
  String get msgLearningMemories => 'Mempelajari memori...';

  @override
  String get msgUploadAttachedFileFailed => 'Gagal mengunggah file terlampir';

  @override
  String captureRecordingError(String error) {
    return 'Kesalahan perekaman: $error';
  }

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return 'Perekaman dihentikan: $reason. Anda mungkin perlu menghubungkan ulang layar eksternal atau memulai ulang perekaman.';
  }

  @override
  String get captureMicrophonePermissionRequired => 'Izin mikrofon diperlukan untuk merekam';

  @override
  String get captureMicrophonePermissionInSystemPreferences => 'Izin mikrofon dapat diatur di Preferensi Sistem';

  @override
  String get captureScreenRecordingPermissionRequired => 'Izin perekaman layar diperlukan';

  @override
  String get captureDisplayDetectionFailed => 'Deteksi tampilan gagal';

  @override
  String get devModeInvalidAudioBytesWebhookUrl => 'URL webhook audio bytes tidak valid';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl => 'URL webhook transkrip realtime tidak valid';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl => 'URL webhook percakapan dibuat tidak valid';

  @override
  String get devModeInvalidDaySummaryWebhookUrl => 'URL webhook ringkasan harian tidak valid';

  @override
  String get devModeSettingsSaved => 'Pengaturan disimpan';

  @override
  String get voiceFailedToTranscribe => 'Gagal mentranskripsi audio';

  @override
  String get locationPermissionRequired => 'Izin Lokasi Diperlukan';

  @override
  String get locationPermissionContent =>
      'Transfer Cepat memerlukan izin lokasi untuk memverifikasi koneksi WiFi. Harap berikan izin lokasi untuk melanjutkan.';

  @override
  String get pdfTranscriptExport => 'Ekspor Transkrip';

  @override
  String get pdfConversationExport => 'Ekspor Percakapan';

  @override
  String pdfTitleLabel(String title) {
    return 'Judul: $title';
  }

  @override
  String get conversationNewIndicator => 'Baru';

  @override
  String conversationPhotosCount(int count) {
    return '$count foto';
  }

  @override
  String get mergingStatus => 'Menggabungkan...';

  @override
  String timeSecsSingular(int count) {
    return '$count detik';
  }

  @override
  String timeSecsPlural(int count) {
    return '$count detik';
  }

  @override
  String timeMinSingular(int count) {
    return '$count menit';
  }

  @override
  String timeMinsPlural(int count) {
    return '$count menit';
  }

  @override
  String timeMinsAndSecs(int mins, int secs) {
    return '$mins menit $secs detik';
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
    return '$hours jam $mins menit';
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
    return '${count}d';
  }

  @override
  String timeCompactMins(int count) {
    return '${count}m';
  }

  @override
  String timeCompactMinsAndSecs(int mins, int secs) {
    return '${mins}m ${secs}d';
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
  String get moveToFolder => 'Pindahkan ke Folder';

  @override
  String get noFoldersAvailable => 'Tidak ada folder tersedia';

  @override
  String get newFolder => 'Folder Baru';

  @override
  String get color => 'Warna';

  @override
  String get waitingForDevice => 'Menunggu perangkat...';

  @override
  String get saySomething => 'Katakan sesuatu...';

  @override
  String get initialisingSystemAudio => 'Menginisialisasi Audio Sistem';

  @override
  String get stopRecording => 'Hentikan Perekaman';

  @override
  String get continueRecording => 'Lanjutkan Perekaman';

  @override
  String get initialisingRecorder => 'Menginisialisasi Perekam';

  @override
  String get pauseRecording => 'Jeda Perekaman';

  @override
  String get resumeRecording => 'Lanjutkan Perekaman';

  @override
  String get noDailyRecapsYet => 'Belum ada ringkasan harian';

  @override
  String get dailyRecapsDescription => 'Ringkasan harian Anda akan muncul di sini setelah dibuat';

  @override
  String get chooseTransferMethod => 'Pilih metode transfer';

  @override
  String get fastTransferSpeed => '~150 KB/s melalui WiFi';

  @override
  String largeTimeGapDetected(String gap) {
    return 'Terdeteksi jeda waktu besar ($gap)';
  }

  @override
  String largeTimeGapsDetected(String gaps) {
    return 'Terdeteksi jeda waktu besar ($gaps)';
  }

  @override
  String get deviceDoesNotSupportWifiSwitchingToBle =>
      'Perangkat tidak mendukung sinkronisasi WiFi, beralih ke Bluetooth';

  @override
  String get appleHealthNotAvailable => 'Apple Health tidak tersedia di perangkat ini';

  @override
  String get downloadAudio => 'Unduh Audio';

  @override
  String get audioDownloadSuccess => 'Audio berhasil diunduh';

  @override
  String get audioDownloadFailed => 'Gagal mengunduh audio';

  @override
  String get downloadingAudio => 'Mengunduh audio...';

  @override
  String get shareAudio => 'Bagikan Audio';

  @override
  String get preparingAudio => 'Menyiapkan Audio';

  @override
  String get gettingAudioFiles => 'Mendapatkan file audio...';

  @override
  String get downloadingAudioProgress => 'Mengunduh Audio';

  @override
  String get processingAudio => 'Memproses Audio';

  @override
  String get combiningAudioFiles => 'Menggabungkan file audio...';

  @override
  String get audioReady => 'Audio Siap';

  @override
  String get openingShareSheet => 'Membuka lembar berbagi...';

  @override
  String get audioShareFailed => 'Gagal Berbagi';

  @override
  String get dailyRecaps => 'Ringkasan Harian';

  @override
  String get removeFilter => 'Hapus Filter';

  @override
  String get categoryConversationAnalysis => 'Analisis Percakapan';

  @override
  String get categoryPersonalityClone => 'Klon Kepribadian';

  @override
  String get categoryHealth => 'Kesehatan';

  @override
  String get categoryEducation => 'Pendidikan';

  @override
  String get categoryCommunication => 'Komunikasi';

  @override
  String get categoryEmotionalSupport => 'Dukungan Emosional';

  @override
  String get categoryProductivity => 'Produktivitas';

  @override
  String get categoryEntertainment => 'Hiburan';

  @override
  String get categoryFinancial => 'Keuangan';

  @override
  String get categoryTravel => 'Perjalanan';

  @override
  String get categorySafety => 'Keamanan';

  @override
  String get categoryShopping => 'Belanja';

  @override
  String get categorySocial => 'Sosial';

  @override
  String get categoryNews => 'Berita';

  @override
  String get categoryUtilities => 'Utilitas';

  @override
  String get categoryOther => 'Lainnya';

  @override
  String get capabilityChat => 'Obrolan';

  @override
  String get capabilityConversations => 'Percakapan';

  @override
  String get capabilityExternalIntegration => 'Integrasi Eksternal';

  @override
  String get capabilityNotification => 'Notifikasi';

  @override
  String get triggerAudioBytes => 'Byte Audio';

  @override
  String get triggerConversationCreation => 'Pembuatan Percakapan';

  @override
  String get triggerTranscriptProcessed => 'Transkrip Diproses';

  @override
  String get actionCreateConversations => 'Buat percakapan';

  @override
  String get actionCreateMemories => 'Buat kenangan';

  @override
  String get actionReadConversations => 'Baca percakapan';

  @override
  String get actionReadMemories => 'Baca kenangan';

  @override
  String get actionReadTasks => 'Baca tugas';

  @override
  String get scopeUserName => 'Nama Pengguna';

  @override
  String get scopeUserFacts => 'Fakta Pengguna';

  @override
  String get scopeUserConversations => 'Percakapan Pengguna';

  @override
  String get scopeUserChat => 'Obrolan Pengguna';

  @override
  String get capabilitySummary => 'Ringkasan';

  @override
  String get capabilityFeatured => 'Unggulan';

  @override
  String get capabilityTasks => 'Tugas';

  @override
  String get capabilityIntegrations => 'Integrasi';

  @override
  String get categoryPersonalityClones => 'Klon Kepribadian';

  @override
  String get categoryProductivityLifestyle => 'Produktivitas & Gaya Hidup';

  @override
  String get categorySocialEntertainment => 'Sosial & Hiburan';

  @override
  String get categoryProductivityTools => 'Alat Produktivitas';

  @override
  String get categoryPersonalWellness => 'Kesejahteraan Pribadi';

  @override
  String get rating => 'Peringkat';

  @override
  String get categories => 'Kategori';

  @override
  String get sortBy => 'Urutkan';

  @override
  String get highestRating => 'Peringkat tertinggi';

  @override
  String get lowestRating => 'Peringkat terendah';

  @override
  String get resetFilters => 'Reset filter';

  @override
  String get applyFilters => 'Terapkan filter';

  @override
  String get mostInstalls => 'Paling banyak diinstal';

  @override
  String get couldNotOpenUrl => 'Tidak dapat membuka URL. Silakan coba lagi.';

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
  String get audioPlaybackUnavailable => 'File audio tidak tersedia untuk diputar';

  @override
  String get audioPlaybackFailed => 'Tidak dapat memutar audio. File mungkin rusak atau hilang.';

  @override
  String get connectionGuide => 'Panduan Koneksi';

  @override
  String get iveDoneThis => 'Saya sudah melakukannya';

  @override
  String get pairNewDevice => 'Pasangkan perangkat baru';

  @override
  String get dontSeeYourDevice => 'Tidak melihat perangkat Anda?';

  @override
  String get reportAnIssue => 'Laporkan masalah';

  @override
  String get pairingTitleOmi => 'Nyalakan Omi';

  @override
  String get pairingDescOmi => 'Tekan dan tahan perangkat hingga bergetar untuk menyalakannya.';

  @override
  String get pairingTitleOmiDevkit => 'Masukkan Omi DevKit ke Mode Pemasangan';

  @override
  String get pairingDescOmiDevkit =>
      'Tekan tombol sekali untuk menyalakan. LED akan berkedip ungu saat dalam mode pemasangan.';

  @override
  String get pairingTitleOmiGlass => 'Nyalakan Omi Glass';

  @override
  String get pairingDescOmiGlass => 'Tekan dan tahan tombol samping selama 3 detik untuk menyalakan.';

  @override
  String get pairingTitlePlaudNote => 'Masukkan Plaud Note ke Mode Pemasangan';

  @override
  String get pairingDescPlaudNote =>
      'Tekan dan tahan tombol samping selama 2 detik. LED merah akan berkedip saat siap dipasangkan.';

  @override
  String get pairingTitleBee => 'Masukkan Bee ke Mode Pemasangan';

  @override
  String get pairingDescBee => 'Tekan tombol 5 kali berturut-turut. Lampu akan mulai berkedip biru dan hijau.';

  @override
  String get pairingTitleLimitless => 'Masukkan Limitless ke Mode Pemasangan';

  @override
  String get pairingDescLimitless =>
      'Saat lampu menyala, tekan sekali lalu tekan dan tahan hingga perangkat menunjukkan lampu merah muda, lalu lepaskan.';

  @override
  String get pairingTitleFriendPendant => 'Masukkan Friend Pendant ke Mode Pemasangan';

  @override
  String get pairingDescFriendPendant =>
      'Tekan tombol pada liontin untuk menyalakannya. Perangkat akan masuk mode pemasangan secara otomatis.';

  @override
  String get pairingTitleFieldy => 'Masukkan Fieldy ke Mode Pemasangan';

  @override
  String get pairingDescFieldy => 'Tekan dan tahan perangkat hingga lampu muncul untuk menyalakannya.';

  @override
  String get pairingTitleAppleWatch => 'Hubungkan Apple Watch';

  @override
  String get pairingDescAppleWatch =>
      'Instal dan buka aplikasi Omi di Apple Watch Anda, lalu ketuk Hubungkan di aplikasi.';

  @override
  String get pairingTitleNeoOne => 'Masukkan Neo One ke Mode Pemasangan';

  @override
  String get pairingDescNeoOne => 'Tekan dan tahan tombol daya hingga LED berkedip. Perangkat akan dapat ditemukan.';
}
