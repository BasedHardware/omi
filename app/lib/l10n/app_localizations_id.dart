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
  String get ok => 'Ok';

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
  String get copyTranscript => 'Salin Transkrip';

  @override
  String get copySummary => 'Salin Ringkasan';

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
  String get noInternetConnection => 'Silakan periksa koneksi internet Anda dan coba lagi.';

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
  String get searching => 'Mencari';

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
  String get noConversationsYet => 'Belum ada percakapan.';

  @override
  String get noStarredConversations => 'Belum ada percakapan berbintang.';

  @override
  String get starConversationHint => 'Untuk memberi bintang pada percakapan, buka dan ketuk ikon bintang di header.';

  @override
  String get searchConversations => 'Cari Percakapan';

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
  String get messageCopied => 'Pesan disalin ke clipboard.';

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
  String get clearChat => 'Bersihkan Obrolan?';

  @override
  String get clearChatConfirm => 'Apakah Anda yakin ingin menghapus obrolan? Tindakan ini tidak dapat dibatalkan.';

  @override
  String get maxFilesLimit => 'Anda hanya dapat mengunggah 4 file sekaligus';

  @override
  String get chatWithOmi => 'Obrolan dengan Omi';

  @override
  String get apps => 'Aplikasi';

  @override
  String get noAppsFound => 'Tidak ada aplikasi ditemukan';

  @override
  String get tryAdjustingSearch => 'Coba sesuaikan pencarian atau filter Anda';

  @override
  String get createYourOwnApp => 'Buat Aplikasi Anda Sendiri';

  @override
  String get buildAndShareApp => 'Bangun dan bagikan aplikasi kustom Anda';

  @override
  String get searchApps => 'Cari 1500+ Aplikasi';

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
  String get visitWebsite => 'Kunjungi Website';

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
  String get identifyingOthers => 'Identifikasi Orang Lain';

  @override
  String get paymentMethods => 'Metode Pembayaran';

  @override
  String get conversationDisplay => 'Tampilan Percakapan';

  @override
  String get dataPrivacy => 'Data & Privasi';

  @override
  String get userId => 'ID Pengguna';

  @override
  String get notSet => 'Belum diatur';

  @override
  String get userIdCopied => 'ID Pengguna disalin ke clipboard';

  @override
  String get systemDefault => 'Bawaan Sistem';

  @override
  String get planAndUsage => 'Paket & Penggunaan';

  @override
  String get offlineSync => 'Sinkronisasi Offline';

  @override
  String get deviceSettings => 'Pengaturan Perangkat';

  @override
  String get chatTools => 'Alat Obrolan';

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
  String get wrapped2025 => 'Wrapped 2025';

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
  String get disconnectDevice => 'Putuskan Perangkat';

  @override
  String get unpairDevice => 'Batalkan Pasangan Perangkat';

  @override
  String get unpairAndForget => 'Batalkan Pasangan dan Lupakan Perangkat';

  @override
  String get deviceDisconnectedMessage => 'Omi Anda telah terputus 😔';

  @override
  String get deviceUnpairedMessage =>
      'Perangkat tidak terpasang. Buka Pengaturan > Bluetooth dan lupakan perangkat untuk menyelesaikan pembatalan pasangan.';

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
  String get off => 'Mati';

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
  String get today => 'Hari Ini';

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
  String get upgradeToUnlimited => 'Tingkatkan ke Tanpa Batas';

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
  String get noLogFilesFound => 'Tidak ada file log ditemukan.';

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
  String get knowledgeGraphDeleted => 'Grafik Pengetahuan berhasil dihapus';

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
  String get webhooks => 'Webhooks';

  @override
  String get conversationEvents => 'Peristiwa Percakapan';

  @override
  String get newConversationCreated => 'Percakapan baru dibuat';

  @override
  String get realtimeTranscript => 'Transkrip Real-time';

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
  String get memories => 'Memori';

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
  String get connect => 'Hubungkan';

  @override
  String get comingSoon => 'Segera Hadir';

  @override
  String get chatToolsFooter => 'Hubungkan aplikasi Anda untuk melihat data dan metrik dalam obrolan.';

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
  String get editName => 'Edit Nama';

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
  String get noUpcomingMeetings => 'Tidak ada rapat mendatang ditemukan';

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
  String get noLanguagesFound => 'Tidak ada bahasa ditemukan';

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
  String get private => 'Pribadi';

  @override
  String updatedDate(String date) {
    return 'Diperbarui $date';
  }

  @override
  String get yesterday => 'kemarin';

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
  String deviceUsesCodec(String deviceName, String codecReason) {
    return '$deviceName menggunakan $codecReason. Omi akan digunakan.';
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
  String get resetToDefault => 'Setel Ulang ke Default';

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
  String get appName => 'Nama Aplikasi';

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
  String get makePublic => 'Buat publik';

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
  String get maybeLater => 'Mungkin nanti';

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
  String get deleteActionItemTitle => 'Hapus Item Tindakan';

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
  String searchMemories(int count) {
    return 'Cari $count Memori';
  }

  @override
  String get memoryDeleted => 'Memori Dihapus.';

  @override
  String get undo => 'Batalkan';

  @override
  String get noMemoriesYet => 'Belum ada memori';

  @override
  String get noAutoMemories => 'Belum ada memori yang diekstrak otomatis';

  @override
  String get noManualMemories => 'Belum ada memori manual';

  @override
  String get noMemoriesInCategories => 'Tidak ada memori dalam kategori ini';

  @override
  String get noMemoriesFound => 'Tidak ada memori ditemukan';

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
  String get newMemory => 'Memori Baru';

  @override
  String get editMemory => 'Edit Memori';

  @override
  String get memoryContentHint => 'Saya suka makan es krim...';

  @override
  String get failedToSaveMemory => 'Gagal menyimpan. Silakan periksa koneksi Anda.';

  @override
  String get saveMemory => 'Simpan Memori';

  @override
  String get retry => 'Coba Lagi';

  @override
  String get createActionItem => 'Buat Item Tindakan';

  @override
  String get editActionItem => 'Edit Item Tindakan';

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
  String get dueDate => 'Tenggat Waktu';

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
}
