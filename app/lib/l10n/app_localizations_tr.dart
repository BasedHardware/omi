// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Turkish (`tr`).
class AppLocalizationsTr extends AppLocalizations {
  AppLocalizationsTr([String locale = 'tr']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'Konuşma';

  @override
  String get transcriptTab => 'Transkript';

  @override
  String get actionItemsTab => 'Eylem Öğeleri';

  @override
  String get deleteConversationTitle => 'Konuşma Silinsin mi?';

  @override
  String get deleteConversationMessage => 'Bu konuşmayı silmek istediğinizden emin misiniz? Bu işlem geri alınamaz.';

  @override
  String get confirm => 'Onayla';

  @override
  String get cancel => 'İptal';

  @override
  String get ok => 'Tamam';

  @override
  String get delete => 'Sil';

  @override
  String get add => 'Ekle';

  @override
  String get update => 'Güncelle';

  @override
  String get save => 'Kaydet';

  @override
  String get edit => 'Düzenle';

  @override
  String get close => 'Kapat';

  @override
  String get clear => 'Temizle';

  @override
  String get copyTranscript => 'Transkripti kopyala';

  @override
  String get copySummary => 'Özeti kopyala';

  @override
  String get testPrompt => 'İstemi Test Et';

  @override
  String get reprocessConversation => 'Konuşmayı Yeniden İşle';

  @override
  String get deleteConversation => 'Sohbeti Sil';

  @override
  String get contentCopied => 'İçerik panoya kopyalandı';

  @override
  String get failedToUpdateStarred => 'Favorilere ekleme durumu güncellenemedi.';

  @override
  String get conversationUrlNotShared => 'Konuşma URL\'si paylaşılamadı.';

  @override
  String get errorProcessingConversation => 'Konuşma işlenirken hata oluştu. Lütfen daha sonra tekrar deneyin.';

  @override
  String get noInternetConnection => 'İnternet bağlantısı yok';

  @override
  String get unableToDeleteConversation => 'Konuşma Silinemiyor';

  @override
  String get somethingWentWrong => 'Bir şeyler ters gitti! Lütfen daha sonra tekrar deneyin.';

  @override
  String get copyErrorMessage => 'Hata mesajını kopyala';

  @override
  String get errorCopied => 'Hata mesajı panoya kopyalandı';

  @override
  String get remaining => 'Kalan';

  @override
  String get loading => 'Yükleniyor...';

  @override
  String get loadingDuration => 'Süre yükleniyor...';

  @override
  String secondsCount(int count) {
    return '$count saniye';
  }

  @override
  String get people => 'Kişiler';

  @override
  String get addNewPerson => 'Yeni Kişi Ekle';

  @override
  String get editPerson => 'Kişiyi Düzenle';

  @override
  String get createPersonHint => 'Yeni bir kişi oluşturun ve Omi\'yi onların konuşmasını da tanımaya eğitin!';

  @override
  String get speechProfile => 'Konuşma Profili';

  @override
  String sampleNumber(int number) {
    return 'Örnek $number';
  }

  @override
  String get settings => 'Ayarlar';

  @override
  String get language => 'Dil';

  @override
  String get selectLanguage => 'Dil Seç';

  @override
  String get deleting => 'Siliniyor...';

  @override
  String get pleaseCompleteAuthentication =>
      'Lütfen tarayıcınızda kimlik doğrulamayı tamamlayın. Tamamlandığında uygulamaya geri dönün.';

  @override
  String get failedToStartAuthentication => 'Kimlik doğrulama başlatılamadı';

  @override
  String get importStarted => 'İçe aktarma başladı! Tamamlandığında bildirim alacaksınız.';

  @override
  String get failedToStartImport => 'İçe aktarma başlatılamadı. Lütfen tekrar deneyin.';

  @override
  String get couldNotAccessFile => 'Seçilen dosyaya erişilemedi';

  @override
  String get askOmi => 'Omi\'ye Sor';

  @override
  String get done => 'Tamamlandı';

  @override
  String get disconnected => 'Bağlantı kesildi';

  @override
  String get searching => 'Aranıyor...';

  @override
  String get connectDevice => 'Cihazı Bağla';

  @override
  String get monthlyLimitReached => 'Aylık limitinize ulaştınız.';

  @override
  String get checkUsage => 'Kullanımı Kontrol Et';

  @override
  String get syncingRecordings => 'Kayıtlar senkronize ediliyor';

  @override
  String get recordingsToSync => 'Senkronize edilecek kayıtlar';

  @override
  String get allCaughtUp => 'Her şey güncel';

  @override
  String get sync => 'Senkronize Et';

  @override
  String get pendantUpToDate => 'Kolye güncel';

  @override
  String get allRecordingsSynced => 'Tüm kayıtlar senkronize edildi';

  @override
  String get syncingInProgress => 'Senkronizasyon devam ediyor';

  @override
  String get readyToSync => 'Senkronize etmeye hazır';

  @override
  String get tapSyncToStart => 'Başlatmak için Senkronize Et\'e dokunun';

  @override
  String get pendantNotConnected => 'Kolye bağlı değil. Senkronize etmek için bağlayın.';

  @override
  String get everythingSynced => 'Her şey zaten senkronize edilmiş.';

  @override
  String get recordingsNotSynced => 'Henüz senkronize edilmemiş kayıtlarınız var.';

  @override
  String get syncingBackground => 'Kayıtlarınızı arka planda senkronize etmeye devam edeceğiz.';

  @override
  String get noConversationsYet => 'Henüz görüşme yok';

  @override
  String get noStarredConversations => 'Yıldızlı konuşma yok';

  @override
  String get starConversationHint =>
      'Bir konuşmayı favorilere eklemek için açın ve üst kısımdaki yıldız simgesine dokunun.';

  @override
  String get searchConversations => 'Konuşmaları ara...';

  @override
  String selectedCount(int count, Object s) {
    return '$count seçildi';
  }

  @override
  String get merge => 'Birleştir';

  @override
  String get mergeConversations => 'Konuşmaları Birleştir';

  @override
  String mergeConversationsMessage(int count) {
    return 'Bu işlem $count konuşmayı birleştirecek. Tüm içerik birleştirilecek ve yeniden oluşturulacak.';
  }

  @override
  String get mergingInBackground => 'Arka planda birleştiriliyor. Bu biraz zaman alabilir.';

  @override
  String get failedToStartMerge => 'Birleştirme başlatılamadı';

  @override
  String get askAnything => 'Her şeyi sor';

  @override
  String get noMessagesYet => 'Henüz mesaj yok!\nNeden bir konuşma başlatmıyorsunuz?';

  @override
  String get deletingMessages => 'Mesajlarınız Omi\'nin hafızasından siliniyor...';

  @override
  String get messageCopied => '✨ Mesaj panoya kopyalandı';

  @override
  String get cannotReportOwnMessage => 'Kendi mesajlarınızı bildiremezsiniz.';

  @override
  String get reportMessage => 'Mesajı Bildir';

  @override
  String get reportMessageConfirm => 'Bu mesajı bildirmek istediğinizden emin misiniz?';

  @override
  String get messageReported => 'Mesaj başarıyla bildirildi.';

  @override
  String get thankYouFeedback => 'Geri bildiriminiz için teşekkürler!';

  @override
  String get clearChat => 'Sohbeti Temizle';

  @override
  String get clearChatConfirm => 'Sohbeti temizlemek istediğinizden emin misiniz? Bu işlem geri alınamaz.';

  @override
  String get maxFilesLimit => 'Aynı anda en fazla 4 dosya yükleyebilirsiniz';

  @override
  String get chatWithOmi => 'Omi ile Sohbet';

  @override
  String get apps => 'Uygulamalar';

  @override
  String get noAppsFound => 'Uygulama bulunamadı';

  @override
  String get tryAdjustingSearch => 'Arama veya filtreleri ayarlamayı deneyin';

  @override
  String get createYourOwnApp => 'Kendi Uygulamanızı Oluşturun';

  @override
  String get buildAndShareApp => 'Özel uygulamanızı oluşturun ve paylaşın';

  @override
  String get searchApps => 'Uygulama ara...';

  @override
  String get myApps => 'Uygulamalarım';

  @override
  String get installedApps => 'Yüklü Uygulamalar';

  @override
  String get unableToFetchApps =>
      'Uygulamalar alınamadı :(\n\nLütfen internet bağlantınızı kontrol edin ve tekrar deneyin.';

  @override
  String get aboutOmi => 'Omi Hakkında';

  @override
  String get privacyPolicy => 'Gizlilik Politikası';

  @override
  String get visitWebsite => 'Web sitesini ziyaret edin';

  @override
  String get helpOrInquiries => 'Yardım veya sorularınız mı var?';

  @override
  String get joinCommunity => 'Topluluğa katılın!';

  @override
  String get membersAndCounting => '8000+ üye ve sayı artıyor.';

  @override
  String get deleteAccountTitle => 'Hesabı Sil';

  @override
  String get deleteAccountConfirm => 'Hesabınızı silmek istediğinizden emin misiniz?';

  @override
  String get cannotBeUndone => 'Bu işlem geri alınamaz.';

  @override
  String get allDataErased => 'Tüm anılarınız ve konuşmalarınız kalıcı olarak silinecek.';

  @override
  String get appsDisconnected => 'Uygulamalarınız ve Entegrasyonlarınızın bağlantısı derhal kesilecek.';

  @override
  String get exportBeforeDelete =>
      'Hesabınızı silmeden önce verilerinizi dışa aktarabilirsiniz, ancak silindikten sonra kurtarılamaz.';

  @override
  String get deleteAccountCheckbox =>
      'Hesabımı silmenin kalıcı olduğunu ve anılar ve konuşmalar dahil tüm verilerin kaybolacağını ve kurtarılamayacağını anlıyorum.';

  @override
  String get areYouSure => 'Emin misiniz?';

  @override
  String get deleteAccountFinal =>
      'Bu işlem geri alınamaz ve hesabınızı ve tüm ilgili verileri kalıcı olarak silecektir. Devam etmek istediğinizden emin misiniz?';

  @override
  String get deleteNow => 'Şimdi Sil';

  @override
  String get goBack => 'Geri Dön';

  @override
  String get checkBoxToConfirm =>
      'Hesabınızı silmenin kalıcı ve geri alınamaz olduğunu anladığınızı onaylamak için kutucuğu işaretleyin.';

  @override
  String get profile => 'Profil';

  @override
  String get name => 'Ad';

  @override
  String get email => 'E-posta';

  @override
  String get customVocabulary => 'Özel Kelime Dağarcığı';

  @override
  String get identifyingOthers => 'Diğerlerini Tanımlama';

  @override
  String get paymentMethods => 'Ödeme Yöntemleri';

  @override
  String get conversationDisplay => 'Konuşma Görüntüleme';

  @override
  String get dataPrivacy => 'Veri Gizliliği';

  @override
  String get userId => 'Kullanıcı Kimliği';

  @override
  String get notSet => 'Ayarlanmamış';

  @override
  String get userIdCopied => 'Kullanıcı kimliği panoya kopyalandı';

  @override
  String get systemDefault => 'Sistem Varsayılanı';

  @override
  String get planAndUsage => 'Plan ve Kullanım';

  @override
  String get offlineSync => 'Çevrimdışı Senkronizasyon';

  @override
  String get deviceSettings => 'Cihaz Ayarları';

  @override
  String get integrations => 'Entegrasyonlar';

  @override
  String get feedbackBug => 'Geri Bildirim / Hata';

  @override
  String get helpCenter => 'Yardım Merkezi';

  @override
  String get developerSettings => 'Geliştirici Ayarları';

  @override
  String get getOmiForMac => 'Mac için Omi\'yi Edinin';

  @override
  String get referralProgram => 'Yönlendirme Programı';

  @override
  String get signOut => 'Çıkış Yap';

  @override
  String get appAndDeviceCopied => 'Uygulama ve cihaz detayları kopyalandı';

  @override
  String get wrapped2025 => '2025 Özeti';

  @override
  String get yourPrivacyYourControl => 'Gizliliğiniz, Kontrolünüz';

  @override
  String get privacyIntro =>
      'Omi\'de gizliliğinizi korumaya kararlıyız. Bu sayfa verilerinizin nasıl saklandığını ve kullanıldığını kontrol etmenizi sağlar.';

  @override
  String get learnMore => 'Daha fazla bilgi...';

  @override
  String get dataProtectionLevel => 'Veri Koruma Seviyesi';

  @override
  String get dataProtectionDesc =>
      'Verileriniz varsayılan olarak güçlü şifreleme ile korunmaktadır. Ayarlarınızı ve gelecekteki gizlilik seçeneklerini aşağıda inceleyin.';

  @override
  String get appAccess => 'Uygulama Erişimi';

  @override
  String get appAccessDesc =>
      'Aşağıdaki uygulamalar verilerinize erişebilir. İzinlerini yönetmek için bir uygulamaya dokunun.';

  @override
  String get noAppsExternalAccess => 'Yüklü hiçbir uygulama verilerinize harici erişime sahip değil.';

  @override
  String get deviceName => 'Cihaz Adı';

  @override
  String get deviceId => 'Cihaz Kimliği';

  @override
  String get firmware => 'Ürün Yazılımı';

  @override
  String get sdCardSync => 'SD Kart Senkronizasyonu';

  @override
  String get hardwareRevision => 'Donanım Revizyonu';

  @override
  String get modelNumber => 'Model Numarası';

  @override
  String get manufacturer => 'Üretici';

  @override
  String get doubleTap => 'Çift Dokunma';

  @override
  String get ledBrightness => 'LED Parlaklığı';

  @override
  String get micGain => 'Mikrofon Kazancı';

  @override
  String get disconnect => 'Bağlantıyı Kes';

  @override
  String get forgetDevice => 'Cihazı Unut';

  @override
  String get chargingIssues => 'Şarj Sorunları';

  @override
  String get disconnectDevice => 'Cihaz Bağlantısını Kes';

  @override
  String get unpairDevice => 'Cihaz Eşleştirmesini Kaldır';

  @override
  String get unpairAndForget => 'Eşleştirmeyi Kaldır ve Cihazı Unut';

  @override
  String get deviceDisconnectedMessage => 'Omi\'nizin bağlantısı kesildi 😔';

  @override
  String get deviceUnpairedMessage =>
      'Cihaz eşleştirmesi kaldırıldı. Eşleştirme kaldırmayı tamamlamak için Ayarlar > Bluetooth\'a gidin ve cihazı unutun.';

  @override
  String get unpairDialogTitle => 'Cihazı Eşleştirmeyi Kaldır';

  @override
  String get unpairDialogMessage =>
      'Bu, cihazın eşleştirilmesini kaldıracak ve başka bir telefona bağlanabilecek. İşlemi tamamlamak için Ayarlar > Bluetooth\'a gidip cihazı unutmanız gerekecek.';

  @override
  String get deviceNotConnected => 'Cihaz Bağlı Değil';

  @override
  String get connectDeviceMessage => 'Cihaz ayarlarına ve özelleştirmeye erişmek için\nOmi cihazınızı bağlayın';

  @override
  String get deviceInfoSection => 'Cihaz Bilgileri';

  @override
  String get customizationSection => 'Özelleştirme';

  @override
  String get hardwareSection => 'Donanım';

  @override
  String get v2Undetected => 'V2 algılanamadı';

  @override
  String get v2UndetectedMessage =>
      'V1 cihazınız olduğunu veya cihazınızın bağlı olmadığını görüyoruz. SD Kart işlevi yalnızca V2 cihazlar için mevcuttur.';

  @override
  String get endConversation => 'Konuşmayı Sonlandır';

  @override
  String get pauseResume => 'Duraklat/Devam Et';

  @override
  String get starConversation => 'Konuşmayı Favorilere Ekle';

  @override
  String get doubleTapAction => 'Çift Dokunma İşlemi';

  @override
  String get endAndProcess => 'Konuşmayı Sonlandır ve İşle';

  @override
  String get pauseResumeRecording => 'Kaydı Duraklat/Devam Ettir';

  @override
  String get starOngoing => 'Devam Eden Konuşmayı Favorilere Ekle';

  @override
  String get off => 'Kapalı';

  @override
  String get max => 'Maksimum';

  @override
  String get mute => 'Sessiz';

  @override
  String get quiet => 'Sessiz';

  @override
  String get normal => 'Normal';

  @override
  String get high => 'Yüksek';

  @override
  String get micGainDescMuted => 'Mikrofon sessize alındı';

  @override
  String get micGainDescLow => 'Çok sessiz - gürültülü ortamlar için';

  @override
  String get micGainDescModerate => 'Sessiz - orta düzey gürültü için';

  @override
  String get micGainDescNeutral => 'Nötr - dengeli kayıt';

  @override
  String get micGainDescSlightlyBoosted => 'Hafif artırılmış - normal kullanım';

  @override
  String get micGainDescBoosted => 'Artırılmış - sessiz ortamlar için';

  @override
  String get micGainDescHigh => 'Yüksek - uzak veya yumuşak sesler için';

  @override
  String get micGainDescVeryHigh => 'Çok yüksek - çok sessiz kaynaklar için';

  @override
  String get micGainDescMax => 'Maksimum - dikkatli kullanın';

  @override
  String get developerSettingsTitle => 'Geliştirici Ayarları';

  @override
  String get saving => 'Kaydediliyor...';

  @override
  String get personaConfig => 'Yapay zeka kişiliğinizi yapılandırın';

  @override
  String get beta => 'BETA';

  @override
  String get transcription => 'Transkripsiyon';

  @override
  String get transcriptionConfig => 'STT sağlayıcısını yapılandırın';

  @override
  String get conversationTimeout => 'Konuşma Zaman Aşımı';

  @override
  String get conversationTimeoutConfig => 'Konuşmaların ne zaman otomatik sonlandırılacağını ayarlayın';

  @override
  String get importData => 'Veri İçe Aktar';

  @override
  String get importDataConfig => 'Diğer kaynaklardan veri içe aktarın';

  @override
  String get debugDiagnostics => 'Hata Ayıklama ve Teşhis';

  @override
  String get endpointUrl => 'Uç Nokta URL\'si';

  @override
  String get noApiKeys => 'Henüz API anahtarı yok';

  @override
  String get createKeyToStart => 'Başlamak için bir anahtar oluşturun';

  @override
  String get createKey => 'Anahtar Oluştur';

  @override
  String get docs => 'Dokümantasyon';

  @override
  String get yourOmiInsights => 'Omi İçgörüleriniz';

  @override
  String get today => 'Bugün';

  @override
  String get thisMonth => 'Bu Ay';

  @override
  String get thisYear => 'Bu Yıl';

  @override
  String get allTime => 'Tüm Zamanlar';

  @override
  String get noActivityYet => 'Henüz Aktivite Yok';

  @override
  String get startConversationToSeeInsights =>
      'Kullanım içgörülerinizi burada görmek için\nOmi ile bir konuşma başlatın.';

  @override
  String get listening => 'Dinleme';

  @override
  String get listeningSubtitle => 'Omi\'nin aktif olarak dinlediği toplam süre.';

  @override
  String get understanding => 'Anlama';

  @override
  String get understandingSubtitle => 'Konuşmalarınızdan anlaşılan kelimeler.';

  @override
  String get providing => 'Sağlama';

  @override
  String get providingSubtitle => 'Otomatik olarak yakalanan eylem öğeleri ve notlar.';

  @override
  String get remembering => 'Hatırlama';

  @override
  String get rememberingSubtitle => 'Sizin için hatırlanan gerçekler ve detaylar.';

  @override
  String get unlimitedPlan => 'Sınırsız Plan';

  @override
  String get managePlan => 'Planı Yönet';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'Planınız $date tarihinde iptal edilecek.';
  }

  @override
  String renewsOn(String date) {
    return 'Planınız $date tarihinde yenilenecek.';
  }

  @override
  String get basicPlan => 'Ücretsiz Plan';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$limit dakikadan $used kullanıldı';
  }

  @override
  String get upgrade => 'Yükselt';

  @override
  String get upgradeToUnlimited => 'Sınırsıza yükselt';

  @override
  String basicPlanDesc(int limit) {
    return 'Planınız ayda $limit ücretsiz dakika içerir. Sınırsız kullanım için yükseltin.';
  }

  @override
  String get shareStatsMessage => 'Omi istatistiklerimi paylaşıyorum! (omi.me - her zaman açık yapay zeka asistanınız)';

  @override
  String get sharePeriodToday => 'Bugün, omi:';

  @override
  String get sharePeriodMonth => 'Bu ay, omi:';

  @override
  String get sharePeriodYear => 'Bu yıl, omi:';

  @override
  String get sharePeriodAllTime => 'Şimdiye kadar, omi:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 $minutes dakika dinledi';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 $words kelime anladı';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ $count içgörü sağladı';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 $count anı hatırladı';
  }

  @override
  String get debugLogs => 'Hata ayıklama günlükleri';

  @override
  String get debugLogsAutoDelete => '3 gün sonra otomatik olarak silinir.';

  @override
  String get debugLogsDesc => 'Sorunların teşhisine yardımcı olur';

  @override
  String get noLogFilesFound => 'Günlük dosyası bulunamadı.';

  @override
  String get omiDebugLog => 'Omi hata ayıklama günlüğü';

  @override
  String get logShared => 'Günlük paylaşıldı';

  @override
  String get selectLogFile => 'Günlük Dosyası Seç';

  @override
  String get shareLogs => 'Günlükleri paylaş';

  @override
  String get debugLogCleared => 'Hata ayıklama günlüğü temizlendi';

  @override
  String get exportStarted => 'Dışa aktarma başladı. Bu birkaç saniye sürebilir...';

  @override
  String get exportAllData => 'Tüm Verileri Dışa Aktar';

  @override
  String get exportDataDesc => 'Konuşmaları JSON dosyasına aktar';

  @override
  String get exportedConversations => 'Omi\'den Dışa Aktarılan Konuşmalar';

  @override
  String get exportShared => 'Dışa aktarma paylaşıldı';

  @override
  String get deleteKnowledgeGraphTitle => 'Bilgi Grafiği Silinsin mi?';

  @override
  String get deleteKnowledgeGraphMessage =>
      'Bu, tüm türetilmiş bilgi grafiği verilerini (düğümler ve bağlantılar) silecektir. Orijinal anılarınız güvende kalacaktır. Grafik zamanla veya bir sonraki istekte yeniden oluşturulacaktır.';

  @override
  String get knowledgeGraphDeleted => 'Bilgi grafiği silindi';

  @override
  String deleteGraphFailed(String error) {
    return 'Grafik silinemedi: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'Bilgi Grafiğini Sil';

  @override
  String get deleteKnowledgeGraphDesc => 'Tüm düğümleri ve bağlantıları temizle';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'MCP Sunucusu';

  @override
  String get mcpServerDesc => 'Yapay zeka asistanlarını verilerinize bağlayın';

  @override
  String get serverUrl => 'Sunucu URL\'si';

  @override
  String get urlCopied => 'URL kopyalandı';

  @override
  String get apiKeyAuth => 'API Anahtar Kimlik Doğrulaması';

  @override
  String get header => 'Başlık';

  @override
  String get authorizationBearer => 'Authorization: Bearer <key>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'İstemci Kimliği';

  @override
  String get clientSecret => 'İstemci Gizli Anahtarı';

  @override
  String get useMcpApiKey => 'MCP API anahtarınızı kullanın';

  @override
  String get webhooks => 'Webhook\'lar';

  @override
  String get conversationEvents => 'Konuşma Olayları';

  @override
  String get newConversationCreated => 'Yeni konuşma oluşturuldu';

  @override
  String get realtimeTranscript => 'Gerçek zamanlı transkript';

  @override
  String get transcriptReceived => 'Transkript alındı';

  @override
  String get audioBytes => 'Ses Baytları';

  @override
  String get audioDataReceived => 'Ses verisi alındı';

  @override
  String get intervalSeconds => 'Aralık (saniye)';

  @override
  String get daySummary => 'Günlük Özet';

  @override
  String get summaryGenerated => 'Özet oluşturuldu';

  @override
  String get claudeDesktop => 'Claude Masaüstü';

  @override
  String get addToClaudeConfig => 'claude_desktop_config.json\'a ekle';

  @override
  String get copyConfig => 'Yapılandırmayı Kopyala';

  @override
  String get configCopied => 'Yapılandırma panoya kopyalandı';

  @override
  String get listeningMins => 'Dinleme (dk)';

  @override
  String get understandingWords => 'Anlama (kelime)';

  @override
  String get insights => 'İçgörüler';

  @override
  String get memories => 'Anılar';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return 'Bu ay $limit dakikadan $used kullanıldı';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return 'Bu ay $limit kelimeden $used kullanıldı';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return 'Bu ay $limit içgörüden $used elde edildi';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return 'Bu ay $limit anıdan $used oluşturuldu';
  }

  @override
  String get visibility => 'Görünürlük';

  @override
  String get visibilitySubtitle => 'Listenizde hangi konuşmaların görüneceğini kontrol edin';

  @override
  String get showShortConversations => 'Kısa Konuşmaları Göster';

  @override
  String get showShortConversationsDesc => 'Eşik değerinden kısa konuşmaları göster';

  @override
  String get showDiscardedConversations => 'Atılan Konuşmaları Göster';

  @override
  String get showDiscardedConversationsDesc => 'Atılanmış olarak işaretlenmiş konuşmaları dahil et';

  @override
  String get shortConversationThreshold => 'Kısa Konuşma Eşiği';

  @override
  String get shortConversationThresholdSubtitle => 'Bundan kısa konuşmalar yukarıda etkinleştirilmedikçe gizlenecek';

  @override
  String get durationThreshold => 'Süre Eşiği';

  @override
  String get durationThresholdDesc => 'Bundan kısa konuşmaları gizle';

  @override
  String minLabel(int count) {
    return '$count dk';
  }

  @override
  String get customVocabularyTitle => 'Özel Kelime Hazinesi';

  @override
  String get addWords => 'Kelime Ekle';

  @override
  String get addWordsDesc => 'İsimler, terimler veya yaygın olmayan kelimeler';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'Connect';

  @override
  String get comingSoon => 'Yakında';

  @override
  String get integrationsFooter => 'Sohbette veri ve metrikleri görmek için uygulamalarınızı bağlayın.';

  @override
  String get completeAuthInBrowser =>
      'Lütfen tarayıcınızda kimlik doğrulamayı tamamlayın. Tamamlandığında uygulamaya geri dönün.';

  @override
  String failedToStartAuth(String appName) {
    return '$appName kimlik doğrulaması başlatılamadı';
  }

  @override
  String disconnectAppTitle(String appName) {
    return '$appName Bağlantısı Kesilsin mi?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return '$appName bağlantısını kesmek istediğinizden emin misiniz? İstediğiniz zaman tekrar bağlanabilirsiniz.';
  }

  @override
  String disconnectedFrom(String appName) {
    return '$appName bağlantısı kesildi';
  }

  @override
  String get failedToDisconnect => 'Bağlantı kesilemedi';

  @override
  String connectTo(String appName) {
    return '$appName\'e Bağlan';
  }

  @override
  String authAccessMessage(String appName) {
    return 'Omi\'nin $appName verilerinize erişmesine yetki vermeniz gerekecek. Bu, kimlik doğrulama için tarayıcınızı açacaktır.';
  }

  @override
  String get continueAction => 'Devam Et';

  @override
  String get languageTitle => 'Dil';

  @override
  String get primaryLanguage => 'Birincil Dil';

  @override
  String get automaticTranslation => 'Otomatik Çeviri';

  @override
  String get detectLanguages => '10+ dil algıla';

  @override
  String get authorizeSavingRecordings => 'Kayıtların Kaydedilmesine İzin Ver';

  @override
  String get thanksForAuthorizing => 'İzin verdiğiniz için teşekkürler!';

  @override
  String get needYourPermission => 'İzninize ihtiyacımız var';

  @override
  String get alreadyGavePermission =>
      'Kayıtlarınızı kaydetmemiz için bize zaten izin verdiniz. İşte neden buna ihtiyacımız olduğunun bir hatırlatması:';

  @override
  String get wouldLikePermission => 'Ses kayıtlarınızı kaydetmek için izninizi istiyoruz. İşte nedeni:';

  @override
  String get improveSpeechProfile => 'Konuşma Profilinizi Geliştirin';

  @override
  String get improveSpeechProfileDesc =>
      'Kişisel konuşma profilinizi eğitmek ve geliştirmek için kayıtları kullanıyoruz.';

  @override
  String get trainFamilyProfiles => 'Arkadaşlar ve Aile için Profil Eğitin';

  @override
  String get trainFamilyProfilesDesc =>
      'Kayıtlarınız arkadaşlarınızı ve ailenizi tanımamıza ve profil oluşturmamıza yardımcı olur.';

  @override
  String get enhanceTranscriptAccuracy => 'Transkript Doğruluğunu Artırın';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'Modelimiz geliştikçe, kayıtlarınız için daha iyi transkripsiyon sonuçları sağlayabiliriz.';

  @override
  String get legalNotice =>
      'Yasal Uyarı: Ses verilerini kaydetme ve saklama yasallığı bulunduğunuz yere ve bu özelliği nasıl kullandığınıza bağlı olarak değişebilir. Yerel yasalara ve düzenlemelere uyumu sağlamak sizin sorumluluğunuzdur.';

  @override
  String get alreadyAuthorized => 'Zaten İzin Verildi';

  @override
  String get authorize => 'İzin Ver';

  @override
  String get revokeAuthorization => 'İzni Geri Al';

  @override
  String get authorizationSuccessful => 'İzin verme başarılı!';

  @override
  String get failedToAuthorize => 'İzin verilemedi. Lütfen tekrar deneyin.';

  @override
  String get authorizationRevoked => 'İzin geri alındı.';

  @override
  String get recordingsDeleted => 'Kayıtlar silindi.';

  @override
  String get failedToRevoke => 'İzin geri alınamadı. Lütfen tekrar deneyin.';

  @override
  String get permissionRevokedTitle => 'İzin Geri Alındı';

  @override
  String get permissionRevokedMessage => 'Mevcut tüm kayıtlarınızı da kaldırmamızı ister misiniz?';

  @override
  String get yes => 'Evet';

  @override
  String get editName => 'Adı Düzenle';

  @override
  String get howShouldOmiCallYou => 'Omi size nasıl hitap etmeli?';

  @override
  String get enterYourName => 'Adınızı girin';

  @override
  String get nameCannotBeEmpty => 'İsim boş olamaz';

  @override
  String get nameUpdatedSuccessfully => 'İsim başarıyla güncellendi!';

  @override
  String get calendarSettings => 'Takvim ayarları';

  @override
  String get calendarProviders => 'Takvim Sağlayıcıları';

  @override
  String get macOsCalendar => 'macOS Takvimi';

  @override
  String get connectMacOsCalendar => 'Yerel macOS takviminizi bağlayın';

  @override
  String get googleCalendar => 'Google Takvim';

  @override
  String get syncGoogleAccount => 'Google hesabınızla senkronize edin';

  @override
  String get showMeetingsMenuBar => 'Yaklaşan toplantıları menü çubuğunda göster';

  @override
  String get showMeetingsMenuBarDesc =>
      'Bir sonraki toplantınızı ve başlamasına kalan süreyi macOS menü çubuğunda gösterin';

  @override
  String get showEventsNoParticipants => 'Katılımcısı olmayan etkinlikleri göster';

  @override
  String get showEventsNoParticipantsDesc =>
      'Etkinleştirildiğinde, Yaklaşanlar katılımcısı veya video bağlantısı olmayan etkinlikleri gösterir.';

  @override
  String get yourMeetings => 'Toplantılarınız';

  @override
  String get refresh => 'Yenile';

  @override
  String get noUpcomingMeetings => 'Yaklaşan toplantı yok';

  @override
  String get checkingNextDays => 'Sonraki 30 gün kontrol ediliyor';

  @override
  String get tomorrow => 'Yarın';

  @override
  String get googleCalendarComingSoon => 'Google Takvim entegrasyonu yakında!';

  @override
  String connectedAsUser(String userId) {
    return 'Kullanıcı olarak bağlandı: $userId';
  }

  @override
  String get defaultWorkspace => 'Varsayılan Çalışma Alanı';

  @override
  String get tasksCreatedInWorkspace => 'Görevler bu çalışma alanında oluşturulacak';

  @override
  String get defaultProjectOptional => 'Varsayılan Proje (İsteğe Bağlı)';

  @override
  String get leaveUnselectedTasks => 'Görevleri proje olmadan oluşturmak için seçilmemiş bırakın';

  @override
  String get noProjectsInWorkspace => 'Bu çalışma alanında proje bulunamadı';

  @override
  String get conversationTimeoutDesc =>
      'Sessizlikte ne kadar bekledikten sonra konuşmanın otomatik olarak sonlandırılacağını seçin:';

  @override
  String get timeout2Minutes => '2 dakika';

  @override
  String get timeout2MinutesDesc => '2 dakika sessizlikten sonra konuşmayı sonlandır';

  @override
  String get timeout5Minutes => '5 dakika';

  @override
  String get timeout5MinutesDesc => '5 dakika sessizlikten sonra konuşmayı sonlandır';

  @override
  String get timeout10Minutes => '10 dakika';

  @override
  String get timeout10MinutesDesc => '10 dakika sessizlikten sonra konuşmayı sonlandır';

  @override
  String get timeout30Minutes => '30 dakika';

  @override
  String get timeout30MinutesDesc => '30 dakika sessizlikten sonra konuşmayı sonlandır';

  @override
  String get timeout4Hours => '4 saat';

  @override
  String get timeout4HoursDesc => '4 saat sessizlikten sonra konuşmayı sonlandır';

  @override
  String get conversationEndAfterHours => 'Konuşmalar artık 4 saat sessizlikten sonra sonlanacak';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Konuşmalar artık $minutes dakika sessizlikten sonra sonlanacak';
  }

  @override
  String get tellUsPrimaryLanguage => 'Bize ana dilinizi söyleyin';

  @override
  String get languageForTranscription =>
      'Daha keskin transkripsiyonlar ve kişiselleştirilmiş bir deneyim için dilinizi ayarlayın.';

  @override
  String get singleLanguageModeInfo => 'Tek Dil Modu etkin. Daha yüksek doğruluk için çeviri devre dışı.';

  @override
  String get searchLanguageHint => 'Dili isim veya koda göre arayın';

  @override
  String get noLanguagesFound => 'Dil bulunamadı';

  @override
  String get skip => 'Atla';

  @override
  String languageSetTo(String language) {
    return 'Dil $language olarak ayarlandı';
  }

  @override
  String get failedToSetLanguage => 'Dil ayarlanamadı';

  @override
  String appSettings(String appName) {
    return '$appName Ayarları';
  }

  @override
  String disconnectFromApp(String appName) {
    return '$appName Bağlantısı Kesilsin mi?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'Bu, $appName kimlik doğrulamanızı kaldıracaktır. Tekrar kullanmak için yeniden bağlanmanız gerekecek.';
  }

  @override
  String connectedToApp(String appName) {
    return '$appName\'e bağlandı';
  }

  @override
  String get account => 'Hesap';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Eylem öğeleriniz $appName hesabınıza senkronize edilecek';
  }

  @override
  String get defaultSpace => 'Varsayılan Alan';

  @override
  String get selectSpaceInWorkspace => 'Çalışma alanınızda bir alan seçin';

  @override
  String get noSpacesInWorkspace => 'Bu çalışma alanında alan bulunamadı';

  @override
  String get defaultList => 'Varsayılan Liste';

  @override
  String get tasksAddedToList => 'Görevler bu listeye eklenecek';

  @override
  String get noListsInSpace => 'Bu alanda liste bulunamadı';

  @override
  String failedToLoadRepos(String error) {
    return 'Depolar yüklenemedi: $error';
  }

  @override
  String get defaultRepoSaved => 'Varsayılan depo kaydedildi';

  @override
  String get failedToSaveDefaultRepo => 'Varsayılan depo kaydedilemedi';

  @override
  String get defaultRepository => 'Varsayılan Depo';

  @override
  String get selectDefaultRepoDesc =>
      'Sorun oluşturmak için varsayılan bir depo seçin. Sorun oluştururken farklı bir depo belirtebilirsiniz.';

  @override
  String get noReposFound => 'Depo bulunamadı';

  @override
  String get private => 'Özel';

  @override
  String updatedDate(String date) {
    return '$date güncellendi';
  }

  @override
  String get yesterday => 'Dün';

  @override
  String daysAgo(int count) {
    return '$count gün önce';
  }

  @override
  String get oneWeekAgo => '1 hafta önce';

  @override
  String weeksAgo(int count) {
    return '$count hafta önce';
  }

  @override
  String get oneMonthAgo => '1 ay önce';

  @override
  String monthsAgo(int count) {
    return '$count ay önce';
  }

  @override
  String get issuesCreatedInRepo => 'Sorunlar varsayılan deponuzda oluşturulacak';

  @override
  String get taskIntegrations => 'Görev Entegrasyonları';

  @override
  String get configureSettings => 'Ayarları Yapılandır';

  @override
  String get completeAuthBrowser =>
      'Lütfen tarayıcınızda kimlik doğrulamayı tamamlayın. Tamamlandığında uygulamaya geri dönün.';

  @override
  String failedToStartAppAuth(String appName) {
    return '$appName kimlik doğrulaması başlatılamadı';
  }

  @override
  String connectToAppTitle(String appName) {
    return '$appName\'e Bağlan';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Omi\'nin $appName hesabınızda görev oluşturmasına yetki vermeniz gerekecek. Bu, kimlik doğrulama için tarayıcınızı açacaktır.';
  }

  @override
  String get continueButton => 'Devam et';

  @override
  String appIntegration(String appName) {
    return '$appName Entegrasyonu';
  }

  @override
  String integrationComingSoon(String appName) {
    return '$appName ile entegrasyon yakında! Size daha fazla görev yönetimi seçeneği sunmak için çok çalışıyoruz.';
  }

  @override
  String get gotIt => 'Anladım';

  @override
  String get tasksExportedOneApp => 'Görevler aynı anda bir uygulamaya aktarılabilir.';

  @override
  String get completeYourUpgrade => 'Yükseltmenizi Tamamlayın';

  @override
  String get importConfiguration => 'Yapılandırma İçe Aktar';

  @override
  String get exportConfiguration => 'Yapılandırmayı dışa aktar';

  @override
  String get bringYourOwn => 'Kendininkini getir';

  @override
  String get payYourSttProvider => 'Omi\'yi özgürce kullanın. Sadece STT sağlayıcınıza doğrudan ödeme yaparsınız.';

  @override
  String get freeMinutesMonth => 'Ayda 1.200 ücretsiz dakika dahildir. ';

  @override
  String get omiUnlimited => 'Omi Sınırsız';

  @override
  String get hostRequired => 'Host gereklidir';

  @override
  String get validPortRequired => 'Geçerli port gereklidir';

  @override
  String get validWebsocketUrlRequired => 'Geçerli WebSocket URL\'si gereklidir (wss://)';

  @override
  String get apiUrlRequired => 'API URL\'si gereklidir';

  @override
  String get apiKeyRequired => 'API anahtarı gereklidir';

  @override
  String get invalidJsonConfig => 'Geçersiz JSON yapılandırması';

  @override
  String errorSaving(String error) {
    return 'Kaydetme hatası: $error';
  }

  @override
  String get configCopiedToClipboard => 'Yapılandırma panoya kopyalandı';

  @override
  String get pasteJsonConfig => 'JSON yapılandırmanızı aşağıya yapıştırın:';

  @override
  String get addApiKeyAfterImport => 'İçe aktardıktan sonra kendi API anahtarınızı eklemeniz gerekecek';

  @override
  String get paste => 'Yapıştır';

  @override
  String get import => 'İçe Aktar';

  @override
  String get invalidProviderInConfig => 'Yapılandırmada geçersiz sağlayıcı';

  @override
  String importedConfig(String providerName) {
    return '$providerName yapılandırması içe aktarıldı';
  }

  @override
  String invalidJson(String error) {
    return 'Geçersiz JSON: $error';
  }

  @override
  String get provider => 'Sağlayıcı';

  @override
  String get live => 'Canlı';

  @override
  String get onDevice => 'Cihazda';

  @override
  String get apiUrl => 'API URL\'si';

  @override
  String get enterSttHttpEndpoint => 'STT HTTP uç noktanızı girin';

  @override
  String get websocketUrl => 'WebSocket URL\'si';

  @override
  String get enterLiveSttWebsocket => 'Canlı STT WebSocket uç noktanızı girin';

  @override
  String get apiKey => 'API Anahtarı';

  @override
  String get enterApiKey => 'API anahtarınızı girin';

  @override
  String get storedLocallyNeverShared => 'Yerel olarak saklanır, asla paylaşılmaz';

  @override
  String get host => 'Sunucu';

  @override
  String get port => 'Port';

  @override
  String get advanced => 'Gelişmiş';

  @override
  String get configuration => 'Yapılandırma';

  @override
  String get requestConfiguration => 'İstek Yapılandırması';

  @override
  String get responseSchema => 'Yanıt Şeması';

  @override
  String get modified => 'Değiştirildi';

  @override
  String get resetRequestConfig => 'İstek yapılandırmasını varsayılana sıfırla';

  @override
  String get logs => 'Günlükler';

  @override
  String get logsCopied => 'Günlükler kopyalandı';

  @override
  String get noLogsYet => 'Henüz günlük yok. Özel STT etkinliğini görmek için kayda başlayın.';

  @override
  String deviceUsesCodec(String device, String reason) {
    return '$device $reason kullanıyor. Omi kullanılacak.';
  }

  @override
  String get omiTranscription => 'Omi Transkripsiyonu';

  @override
  String get bestInClassTranscription => 'Sıfır kurulum ile sınıfının en iyisi transkripsiyon';

  @override
  String get instantSpeakerLabels => 'Anında konuşmacı etiketleri';

  @override
  String get languageTranslation => '100+ dil çevirisi';

  @override
  String get optimizedForConversation => 'Konuşma için optimize edilmiş';

  @override
  String get autoLanguageDetection => 'Otomatik dil algılama';

  @override
  String get highAccuracy => 'Yüksek doğruluk';

  @override
  String get privacyFirst => 'Önce gizlilik';

  @override
  String get saveChanges => 'Değişiklikleri kaydet';

  @override
  String get resetToDefault => 'Varsayılana sıfırla';

  @override
  String get viewTemplate => 'Şablonu Görüntüle';

  @override
  String get trySomethingLike => 'Şöyle bir şey deneyin...';

  @override
  String get tryIt => 'Dene';

  @override
  String get creatingPlan => 'Plan oluşturuluyor';

  @override
  String get developingLogic => 'Mantık geliştiriliyor';

  @override
  String get designingApp => 'Uygulama tasarlanıyor';

  @override
  String get generatingIconStep => 'İkon oluşturuluyor';

  @override
  String get finalTouches => 'Son dokunuşlar';

  @override
  String get processing => 'İşleniyor...';

  @override
  String get features => 'Özellikler';

  @override
  String get creatingYourApp => 'Uygulamanız oluşturuluyor...';

  @override
  String get generatingIcon => 'İkon oluşturuluyor...';

  @override
  String get whatShouldWeMake => 'Ne yapalım?';

  @override
  String get appName => 'App Name';

  @override
  String get description => 'Açıklama';

  @override
  String get publicLabel => 'Genel';

  @override
  String get privateLabel => 'Özel';

  @override
  String get free => 'Ücretsiz';

  @override
  String get perMonth => '/ Ay';

  @override
  String get tailoredConversationSummaries => 'Özelleştirilmiş Konuşma Özetleri';

  @override
  String get customChatbotPersonality => 'Özel Chatbot Kişiliği';

  @override
  String get makePublic => 'Herkese açık yap';

  @override
  String get anyoneCanDiscover => 'Herkes uygulamanızı keşfedebilir';

  @override
  String get onlyYouCanUse => 'Yalnızca siz bu uygulamayı kullanabilirsiniz';

  @override
  String get paidApp => 'Ücretli uygulama';

  @override
  String get usersPayToUse => 'Kullanıcılar uygulamanızı kullanmak için ödeme yapar';

  @override
  String get freeForEveryone => 'Herkes için ücretsiz';

  @override
  String get perMonthLabel => '/ ay';

  @override
  String get creating => 'Oluşturuluyor...';

  @override
  String get createApp => 'Uygulama Oluştur';

  @override
  String get searchingForDevices => 'Cihazlar aranıyor...';

  @override
  String devicesFoundNearby(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'CİHAZ',
      one: 'CİHAZ',
    );
    return '$count $_temp0 YAKINLARDA BULUNDU';
  }

  @override
  String get pairingSuccessful => 'EŞLEŞTIRME BAŞARILI';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Apple Watch\'a bağlanırken hata: $error';
  }

  @override
  String get dontShowAgain => 'Bir daha gösterme';

  @override
  String get iUnderstand => 'Anlıyorum';

  @override
  String get enableBluetooth => 'Bluetooth\'u Etkinleştir';

  @override
  String get bluetoothNeeded =>
      'Omi\'nin giyilebilir cihazınıza bağlanması için Bluetooth gereklidir. Lütfen Bluetooth\'u etkinleştirin ve tekrar deneyin.';

  @override
  String get contactSupport => 'Desteğe Başvur?';

  @override
  String get connectLater => 'Sonra Bağlan';

  @override
  String get grantPermissions => 'İzinleri ver';

  @override
  String get backgroundActivity => 'Arka plan etkinliği';

  @override
  String get backgroundActivityDesc => 'Daha iyi stabilite için Omi\'nin arka planda çalışmasına izin verin';

  @override
  String get locationAccess => 'Konum erişimi';

  @override
  String get locationAccessDesc => 'Tam deneyim için arka plan konumunu etkinleştirin';

  @override
  String get notifications => 'Bildirimler';

  @override
  String get notificationsDesc => 'Bilgilendirilmek için bildirimleri etkinleştirin';

  @override
  String get locationServiceDisabled => 'Konum Servisi Devre Dışı';

  @override
  String get locationServiceDisabledDesc =>
      'Konum Servisi Devre Dışı. Lütfen Ayarlar > Gizlilik ve Güvenlik > Konum Servisleri\'ne gidin ve etkinleştirin';

  @override
  String get backgroundLocationDenied => 'Arka Plan Konum Erişimi Reddedildi';

  @override
  String get backgroundLocationDeniedDesc =>
      'Lütfen cihaz ayarlarına gidin ve konum iznini \"Her Zaman İzin Ver\" olarak ayarlayın';

  @override
  String get lovingOmi => 'Omi\'yi Beğeniyor musunuz?';

  @override
  String get leaveReviewIos =>
      'App Store\'da bir yorum bırakarak daha fazla insana ulaşmamıza yardımcı olun. Geri bildiriminiz bizim için çok değerli!';

  @override
  String get leaveReviewAndroid =>
      'Google Play Store\'da bir yorum bırakarak daha fazla insana ulaşmamıza yardımcı olun. Geri bildiriminiz bizim için çok değerli!';

  @override
  String get rateOnAppStore => 'App Store\'da Değerlendir';

  @override
  String get rateOnGooglePlay => 'Google Play\'de Değerlendir';

  @override
  String get maybeLater => 'Belki Sonra';

  @override
  String get speechProfileIntro => 'Omi hedeflerinizi ve sesinizi öğrenmeli. Daha sonra değiştirebilirsiniz.';

  @override
  String get getStarted => 'Başlayın';

  @override
  String get allDone => 'Hepsi tamam!';

  @override
  String get keepGoing => 'Devam et, harika gidiyorsun';

  @override
  String get skipThisQuestion => 'Bu soruyu atla';

  @override
  String get skipForNow => 'Şimdilik atla';

  @override
  String get connectionError => 'Bağlantı Hatası';

  @override
  String get connectionErrorDesc =>
      'Sunucuya bağlanılamadı. Lütfen internet bağlantınızı kontrol edin ve tekrar deneyin.';

  @override
  String get invalidRecordingMultipleSpeakers => 'Geçersiz kayıt algılandı';

  @override
  String get multipleSpeakersDesc =>
      'Kayıtta birden fazla konuşmacı var gibi görünüyor. Lütfen sessiz bir yerde olduğunuzdan emin olun ve tekrar deneyin.';

  @override
  String get tooShortDesc => 'Yeterli konuşma algılanamadı. Lütfen daha fazla konuşun ve tekrar deneyin.';

  @override
  String get invalidRecordingDesc => 'Lütfen en az 5 saniye, en fazla 90 saniye konuştuğunuzdan emin olun.';

  @override
  String get areYouThere => 'Orada mısınız?';

  @override
  String get noSpeechDesc =>
      'Herhangi bir konuşma algılayamadık. Lütfen en az 10 saniye, en fazla 3 dakika konuştuğunuzdan emin olun.';

  @override
  String get connectionLost => 'Bağlantı Kesildi';

  @override
  String get connectionLostDesc => 'Bağlantı kesildi. Lütfen internet bağlantınızı kontrol edin ve tekrar deneyin.';

  @override
  String get tryAgain => 'Tekrar Dene';

  @override
  String get connectOmiOmiGlass => 'Omi / OmiGlass Bağla';

  @override
  String get continueWithoutDevice => 'Cihaz Olmadan Devam Et';

  @override
  String get permissionsRequired => 'İzinler Gerekli';

  @override
  String get permissionsRequiredDesc =>
      'Bu uygulamanın düzgün çalışması için Bluetooth ve Konum izinlerine ihtiyacı var. Lütfen ayarlardan bunları etkinleştirin.';

  @override
  String get openSettings => 'Ayarları Aç';

  @override
  String get wantDifferentName => 'Farklı bir isimle mi anılmak istiyorsunuz?';

  @override
  String get whatsYourName => 'Adın ne?';

  @override
  String get speakTranscribeSummarize => 'Konuş. Transkripsiyonu Oluştur. Özetle.';

  @override
  String get signInWithApple => 'Apple ile Giriş Yap';

  @override
  String get signInWithGoogle => 'Google ile Giriş Yap';

  @override
  String get byContinuingAgree => 'Devam ederek ';

  @override
  String get termsOfUse => 'Kullanım Koşulları';

  @override
  String get omiYourAiCompanion => 'Omi – Yapay Zeka Yardımcınız';

  @override
  String get captureEveryMoment => 'Her anı yakalayın. Yapay zeka destekli\nözetler alın. Artık not almayın.';

  @override
  String get appleWatchSetup => 'Apple Watch Kurulumu';

  @override
  String get permissionRequestedExclaim => 'İzin İstendi!';

  @override
  String get microphonePermission => 'Mikrofon İzni';

  @override
  String get permissionGrantedNow =>
      'İzin verildi! Şimdi:\n\nSaatinizdeki Omi uygulamasını açın ve aşağıda \"Devam Et\"e dokunun';

  @override
  String get needMicrophonePermission =>
      'Mikrofon iznine ihtiyacımız var.\n\n1. \"İzin Ver\"e dokunun\n2. iPhone\'unuzda izin verin\n3. Saat uygulaması kapanacak\n4. Yeniden açın ve \"Devam Et\"e dokunun';

  @override
  String get grantPermissionButton => 'İzin Ver';

  @override
  String get needHelp => 'Yardıma mı İhtiyacınız Var?';

  @override
  String get troubleshootingSteps =>
      'Sorun giderme:\n\n1. Omi\'nin saatinizde yüklü olduğundan emin olun\n2. Saatinizdeki Omi uygulamasını açın\n3. İzin açılır penceresini arayın\n4. İstendiğinde \"İzin Ver\"e dokunun\n5. Saatinizdeki uygulama kapanacak - yeniden açın\n6. Geri gelin ve iPhone\'unuzda \"Devam Et\"e dokunun';

  @override
  String get recordingStartedSuccessfully => 'Kayıt başarıyla başladı!';

  @override
  String get permissionNotGrantedYet =>
      'Henüz izin verilmedi. Lütfen mikrofon erişimine izin verdiğinizden ve saatinizdeki uygulamayı yeniden açtığınızdan emin olun.';

  @override
  String errorRequestingPermission(String error) {
    return 'İzin isteği hatası: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'Kayıt başlatma hatası: $error';
  }

  @override
  String get selectPrimaryLanguage => 'Ana dilinizi seçin';

  @override
  String get languageBenefits =>
      'Daha keskin transkripsiyonlar ve kişiselleştirilmiş bir deneyim için dilinizi ayarlayın';

  @override
  String get whatsYourPrimaryLanguage => 'Ana diliniz nedir?';

  @override
  String get selectYourLanguage => 'Dilinizi seçin';

  @override
  String get personalGrowthJourney => 'Her kelimenizi dinleyen yapay zeka ile kişisel gelişim yolculuğunuz.';

  @override
  String get actionItemsTitle => 'Yapılacaklar';

  @override
  String get actionItemsDescription => 'Düzenlemek için dokunun • Seçmek için uzun basın • Eylemler için kaydırın';

  @override
  String get tabToDo => 'Yapılacak';

  @override
  String get tabDone => 'Bitti';

  @override
  String get tabOld => 'Eski';

  @override
  String get emptyTodoMessage => '🎉 Her şey güncel!\nBekleyen eylem öğesi yok';

  @override
  String get emptyDoneMessage => 'Henüz tamamlanmış öğe yok';

  @override
  String get emptyOldMessage => '✅ Eski görev yok';

  @override
  String get noItems => 'Öğe yok';

  @override
  String get actionItemMarkedIncomplete => 'Eylem öğesi tamamlanmamış olarak işaretlendi';

  @override
  String get actionItemCompleted => 'Eylem öğesi tamamlandı';

  @override
  String get deleteActionItemTitle => 'Eylem öğesini sil';

  @override
  String get deleteActionItemMessage => 'Bu eylem öğesini silmek istediğinizden emin misiniz?';

  @override
  String get deleteSelectedItemsTitle => 'Seçili Öğeleri Sil';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return '$count seçili eylem öğesini silmek istediğinizden emin misiniz?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'Eylem öğesi \"$description\" silindi';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count eylem öğesi silindi';
  }

  @override
  String get failedToDeleteItem => 'Eylem öğesi silinemedi';

  @override
  String get failedToDeleteItems => 'Öğeler silinemedi';

  @override
  String get failedToDeleteSomeItems => 'Bazı öğeler silinemedi';

  @override
  String get welcomeActionItemsTitle => 'Eylem Öğeleri için Hazır';

  @override
  String get welcomeActionItemsDescription =>
      'Yapay zekanız konuşmalarınızdan otomatik olarak görevleri ve yapılacakları çıkaracaktır. Oluşturulduklarında burada görünecekler.';

  @override
  String get autoExtractionFeature => 'Konuşmalardan otomatik olarak çıkarıldı';

  @override
  String get editSwipeFeature => 'Düzenlemek için dokunun, tamamlamak veya silmek için kaydırın';

  @override
  String itemsSelected(int count) {
    return '$count seçildi';
  }

  @override
  String get selectAll => 'Tümünü seç';

  @override
  String get deleteSelected => 'Seçilenleri sil';

  @override
  String get searchMemories => 'Anı ara...';

  @override
  String get memoryDeleted => 'Anı Silindi.';

  @override
  String get undo => 'Geri Al';

  @override
  String get noMemoriesYet => '🧠 Henüz anı yok';

  @override
  String get noAutoMemories => 'Henüz otomatik çıkarılan anı yok';

  @override
  String get noManualMemories => 'Henüz manuel anı yok';

  @override
  String get noMemoriesInCategories => 'Bu kategorilerde anı yok';

  @override
  String get noMemoriesFound => '🔍 Anı bulunamadı';

  @override
  String get addFirstMemory => 'İlk anınızı ekleyin';

  @override
  String get clearMemoryTitle => 'Omi\'nin Hafızasını Temizle';

  @override
  String get clearMemoryMessage =>
      'Omi\'nin hafızasını temizlemek istediğinizden emin misiniz? Bu işlem geri alınamaz.';

  @override
  String get clearMemoryButton => 'Belleği Temizle';

  @override
  String get memoryClearedSuccess => 'Omi\'nin sizinle ilgili hafızası temizlendi';

  @override
  String get noMemoriesToDelete => 'Silinecek anı yok';

  @override
  String get createMemoryTooltip => 'Yeni anı oluştur';

  @override
  String get createActionItemTooltip => 'Yeni eylem öğesi oluştur';

  @override
  String get memoryManagement => 'Bellek Yönetimi';

  @override
  String get filterMemories => 'Anıları Filtrele';

  @override
  String totalMemoriesCount(int count) {
    return 'Toplam $count anınız var';
  }

  @override
  String get publicMemories => 'Genel anılar';

  @override
  String get privateMemories => 'Özel anılar';

  @override
  String get makeAllPrivate => 'Tüm Anıları Özel Yap';

  @override
  String get makeAllPublic => 'Tüm Anıları Genel Yap';

  @override
  String get deleteAllMemories => 'Tüm Anıları Sil';

  @override
  String get allMemoriesPrivateResult => 'Tüm anılar artık özel';

  @override
  String get allMemoriesPublicResult => 'Tüm anılar artık genel';

  @override
  String get newMemory => '✨ Yeni hafıza';

  @override
  String get editMemory => '✏️ Hafızayı düzenle';

  @override
  String get memoryContentHint => 'Dondurma yemeyi severim...';

  @override
  String get failedToSaveMemory => 'Kaydedilemedi. Lütfen bağlantınızı kontrol edin.';

  @override
  String get saveMemory => 'Anıyı Kaydet';

  @override
  String get retry => 'Tekrar Dene';

  @override
  String get createActionItem => 'Eylem öğesi oluştur';

  @override
  String get editActionItem => 'Eylem öğesini düzenle';

  @override
  String get actionItemDescriptionHint => 'Ne yapılması gerekiyor?';

  @override
  String get actionItemDescriptionEmpty => 'Eylem öğesi açıklaması boş olamaz.';

  @override
  String get actionItemUpdated => 'Eylem öğesi güncellendi';

  @override
  String get failedToUpdateActionItem => 'Eylem öğesi güncellenemedi';

  @override
  String get actionItemCreated => 'Eylem öğesi oluşturuldu';

  @override
  String get failedToCreateActionItem => 'Eylem öğesi oluşturulamadı';

  @override
  String get dueDate => 'Bitiş tarihi';

  @override
  String get time => 'Saat';

  @override
  String get addDueDate => 'Teslim tarihi ekle';

  @override
  String get pressDoneToSave => 'Kaydetmek için bitti\'ye basın';

  @override
  String get pressDoneToCreate => 'Oluşturmak için bitti\'ye basın';

  @override
  String get filterAll => 'Tümü';

  @override
  String get filterSystem => 'Hakkınızda';

  @override
  String get filterInteresting => 'İçgörüler';

  @override
  String get filterManual => 'Manuel';

  @override
  String get completed => 'Tamamlandı';

  @override
  String get markComplete => 'Tamamlandı olarak işaretle';

  @override
  String get actionItemDeleted => 'Eylem öğesi silindi';

  @override
  String get failedToDeleteActionItem => 'Eylem öğesi silinemedi';

  @override
  String get deleteActionItemConfirmTitle => 'Eylem Öğesini Sil';

  @override
  String get deleteActionItemConfirmMessage => 'Bu eylem öğesini silmek istediğinizden emin misiniz?';

  @override
  String get appLanguage => 'Uygulama Dili';

  @override
  String get appInterfaceSectionTitle => 'UYGULAMA ARAYÜZÜ';

  @override
  String get speechTranscriptionSectionTitle => 'KONUŞMA VE TRANSKRİPSİYON';

  @override
  String get languageSettingsHelperText =>
      'Uygulama Dili menüleri ve düğmeleri değiştirir. Konuşma Dili, kayıtlarınızın nasıl transkribe edildiğini etkiler.';

  @override
  String get translationNotice => 'Çeviri Bildirimi';

  @override
  String get translationNoticeMessage =>
      'Omi konuşmaları birincil dilinize çevirir. İstediğiniz zaman Ayarlar → Profiller\'de güncelleyin.';

  @override
  String get pleaseCheckInternetConnection => 'Lütfen internet bağlantınızı kontrol edin ve tekrar deneyin';

  @override
  String get pleaseSelectReason => 'Lütfen bir neden seçin';

  @override
  String get tellUsMoreWhatWentWrong => 'Neyin yanlış gittiğini bize daha fazla anlatın...';

  @override
  String get selectText => 'Metin Seç';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Maksimum $count hedef izin verildi';
  }

  @override
  String get conversationCannotBeMerged => 'Bu konuşma birleştirilemez (kilitli veya zaten birleştiriliyor)';

  @override
  String get pleaseEnterFolderName => 'Lütfen bir klasör adı girin';

  @override
  String get failedToCreateFolder => 'Klasör oluşturulamadı';

  @override
  String get failedToUpdateFolder => 'Klasör güncellenemedi';

  @override
  String get folderName => 'Klasör adı';

  @override
  String get descriptionOptional => 'Description (optional)';

  @override
  String get failedToDeleteFolder => 'Klasör silinemedi';

  @override
  String get editFolder => 'Klasörü düzenle';

  @override
  String get deleteFolder => 'Klasörü sil';

  @override
  String get transcriptCopiedToClipboard => 'Transkript panoya kopyalandı';

  @override
  String get summaryCopiedToClipboard => 'Özet panoya kopyalandı';

  @override
  String get conversationUrlCouldNotBeShared => 'Konuşma URL\'si paylaşılamadı.';

  @override
  String get urlCopiedToClipboard => 'URL panoya kopyalandı';

  @override
  String get exportTranscript => 'Transkripti dışa aktar';

  @override
  String get exportSummary => 'Özeti dışa aktar';

  @override
  String get exportButton => 'Dışa aktar';

  @override
  String get actionItemsCopiedToClipboard => 'Eylem öğeleri panoya kopyalandı';

  @override
  String get summarize => 'Özetle';

  @override
  String get generateSummary => 'Özet Oluştur';

  @override
  String get conversationNotFoundOrDeleted => 'Konuşma bulunamadı veya silindi';

  @override
  String get deleteMemory => 'Hafızayı sil';

  @override
  String get thisActionCannotBeUndone => 'Bu işlem geri alınamaz.';

  @override
  String memoriesCount(int count) {
    return '$count anı';
  }

  @override
  String get noMemoriesInCategory => 'Bu kategoride henüz anı yok';

  @override
  String get addYourFirstMemory => 'İlk anınızı ekleyin';

  @override
  String get firmwareDisconnectUsb => 'USB\'yi çıkarın';

  @override
  String get firmwareUsbWarning => 'Güncellemeler sırasında USB bağlantısı cihazınıza zarar verebilir.';

  @override
  String get firmwareBatteryAbove15 => 'Pil %15\'in üzerinde';

  @override
  String get firmwareEnsureBattery => 'Cihazınızın %15 pili olduğundan emin olun.';

  @override
  String get firmwareStableConnection => 'Kararlı bağlantı';

  @override
  String get firmwareConnectWifi => 'WiFi veya hücresel veriye bağlanın.';

  @override
  String failedToStartUpdate(String error) {
    return 'Güncelleme başlatılamadı: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'Güncellemeden önce emin olun:';

  @override
  String get confirmed => 'Onaylandı!';

  @override
  String get release => 'Bırak';

  @override
  String get slideToUpdate => 'Güncellemek için kaydırın';

  @override
  String copiedToClipboard(String title) {
    return '$title panoya kopyalandı';
  }

  @override
  String get batteryLevel => 'Pil Seviyesi';

  @override
  String get productUpdate => 'Ürün Güncellemesi';

  @override
  String get offline => 'Çevrimdışı';

  @override
  String get available => 'Mevcut';

  @override
  String get unpairDeviceDialogTitle => 'Cihaz Eşleştirmesini Kaldır';

  @override
  String get unpairDeviceDialogMessage =>
      'Bu, cihazın başka bir telefona bağlanabilmesi için eşleştirmesini kaldıracaktır. İşlemi tamamlamak için Ayarlar > Bluetooth\'a gitmeniz ve cihazı unutmanız gerekecek.';

  @override
  String get unpair => 'Eşleştirmeyi Kaldır';

  @override
  String get unpairAndForgetDevice => 'Eşleştirmeyi Kaldır ve Cihazı Unut';

  @override
  String get unknownDevice => 'Bilinmeyen';

  @override
  String get unknown => 'Bilinmeyen';

  @override
  String get productName => 'Ürün Adı';

  @override
  String get serialNumber => 'Seri Numarası';

  @override
  String get connected => 'Bağlı';

  @override
  String get privacyPolicyTitle => 'Gizlilik Politikası';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label kopyalandı';
  }

  @override
  String get noApiKeysYet => 'Henüz API anahtarı yok. Uygulamanızla entegre etmek için bir tane oluşturun.';

  @override
  String get createKeyToGetStarted => 'Başlamak için bir anahtar oluşturun';

  @override
  String get persona => 'Kişilik';

  @override
  String get configureYourAiPersona => 'AI kişiliğinizi yapılandırın';

  @override
  String get configureSttProvider => 'STT sağlayıcısını yapılandır';

  @override
  String get setWhenConversationsAutoEnd => 'Konuşmaların ne zaman otomatik biteceğini ayarlayın';

  @override
  String get importDataFromOtherSources => 'Diğer kaynaklardan veri içe aktar';

  @override
  String get debugAndDiagnostics => 'Hata Ayıklama ve Tanılama';

  @override
  String get autoDeletesAfter3Days => '3 gün sonra otomatik olarak silinir';

  @override
  String get helpsDiagnoseIssues => 'Sorunları teşhis etmeye yardımcı olur';

  @override
  String get exportStartedMessage => 'Dışa aktarma başladı. Bu birkaç saniye sürebilir...';

  @override
  String get exportConversationsToJson => 'Konuşmaları JSON dosyasına aktar';

  @override
  String get knowledgeGraphDeletedSuccess => 'Bilgi grafiği başarıyla silindi';

  @override
  String failedToDeleteGraph(String error) {
    return 'Grafik silinemedi: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'Tüm düğümleri ve bağlantıları temizle';

  @override
  String get addToClaudeDesktopConfig => 'claude_desktop_config.json dosyasına ekle';

  @override
  String get connectAiAssistantsToData => 'AI asistanlarını verilerinize bağlayın';

  @override
  String get useYourMcpApiKey => 'MCP API anahtarınızı kullanın';

  @override
  String get realTimeTranscript => 'Gerçek Zamanlı Transkript';

  @override
  String get experimental => 'Deneysel';

  @override
  String get transcriptionDiagnostics => 'Transkripsiyon Tanılaması';

  @override
  String get detailedDiagnosticMessages => 'Ayrıntılı tanılama mesajları';

  @override
  String get autoCreateSpeakers => 'Konuşmacıları Otomatik Oluştur';

  @override
  String get autoCreateWhenNameDetected => 'İsim algılandığında otomatik oluştur';

  @override
  String get followUpQuestions => 'Takip Soruları';

  @override
  String get suggestQuestionsAfterConversations => 'Konuşmalardan sonra sorular önerin';

  @override
  String get goalTracker => 'Hedef İzleyici';

  @override
  String get trackPersonalGoalsOnHomepage => 'Ana sayfada kişisel hedeflerinizi takip edin';

  @override
  String get dailyReflection => 'Günlük Düşünce';

  @override
  String get get9PmReminderToReflect => 'Gününüzü değerlendirmek için saat 21:00 hatırlatıcısı alın';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'Eylem öğesi açıklaması boş olamaz';

  @override
  String get saved => 'Kaydedildi';

  @override
  String get overdue => 'Gecikmiş';

  @override
  String get failedToUpdateDueDate => 'Son tarih güncellenemedi';

  @override
  String get markIncomplete => 'Tamamlanmadı olarak işaretle';

  @override
  String get editDueDate => 'Son tarihi düzenle';

  @override
  String get setDueDate => 'Bitiş tarihini ayarla';

  @override
  String get clearDueDate => 'Son tarihi temizle';

  @override
  String get failedToClearDueDate => 'Son tarih temizlenemedi';

  @override
  String get mondayAbbr => 'Pzt';

  @override
  String get tuesdayAbbr => 'Sal';

  @override
  String get wednesdayAbbr => 'Çar';

  @override
  String get thursdayAbbr => 'Per';

  @override
  String get fridayAbbr => 'Cum';

  @override
  String get saturdayAbbr => 'Cmt';

  @override
  String get sundayAbbr => 'Paz';

  @override
  String get howDoesItWork => 'Nasıl çalışır?';

  @override
  String get sdCardSyncDescription => 'SD Kart Senkronizasyonu, anılarınızı SD Karttan uygulamaya aktaracak';

  @override
  String get checksForAudioFiles => 'SD Karttaki ses dosyalarını kontrol eder';

  @override
  String get omiSyncsAudioFiles => 'Omi daha sonra ses dosyalarını sunucu ile senkronize eder';

  @override
  String get serverProcessesAudio => 'Sunucu ses dosyalarını işler ve anılar oluşturur';

  @override
  String get youreAllSet => 'Hazırsınız!';

  @override
  String get welcomeToOmiDescription =>
      'Omi\'ye hoş geldiniz! AI yardımcınız konuşmalar, görevler ve daha fazlasında size yardımcı olmaya hazır.';

  @override
  String get startUsingOmi => 'Omi\'yi Kullanmaya Başla';

  @override
  String get back => 'Geri';

  @override
  String get keyboardShortcuts => 'Klavye Kısayolları';

  @override
  String get toggleControlBar => 'Kontrol Çubuğunu Değiştir';

  @override
  String get pressKeys => 'Tuşlara basın...';

  @override
  String get cmdRequired => '⌘ gerekli';

  @override
  String get invalidKey => 'Geçersiz tuş';

  @override
  String get space => 'Boşluk';

  @override
  String get search => 'Ara';

  @override
  String get searchPlaceholder => 'Ara...';

  @override
  String get untitledConversation => 'Başlıksız Sohbet';

  @override
  String countRemaining(String count) {
    return '$count kalan';
  }

  @override
  String get addGoal => 'Hedef Ekle';

  @override
  String get editGoal => 'Hedefi Düzenle';

  @override
  String get icon => 'Simge';

  @override
  String get goalTitle => 'Hedef başlığı';

  @override
  String get current => 'Mevcut';

  @override
  String get target => 'Hedef';

  @override
  String get saveGoal => 'Kaydet';

  @override
  String get goals => 'Hedefler';

  @override
  String get tapToAddGoal => 'Hedef eklemek için dokunun';

  @override
  String welcomeBack(String name) {
    return 'Tekrar hoş geldiniz, $name';
  }

  @override
  String get yourConversations => 'Görüşmeleriniz';

  @override
  String get reviewAndManageConversations => 'Kaydedilen görüşmelerinizi inceleyin ve yönetin';

  @override
  String get startCapturingConversations => 'Görüşmeleri burada görmek için Omi cihazınızla yakalamaya başlayın.';

  @override
  String get useMobileAppToCapture => 'Ses kaydetmek için mobil uygulamanızı kullanın';

  @override
  String get conversationsProcessedAutomatically => 'Görüşmeler otomatik olarak işlenir';

  @override
  String get getInsightsInstantly => 'Anında içgörüler ve özetler alın';

  @override
  String get showAll => 'Hepsini göster →';

  @override
  String get noTasksForToday => 'Bugün için görev yok.\\nDaha fazla görev için Omi\'ye sorun veya manuel oluşturun.';

  @override
  String get dailyScore => 'GÜNLÜK SKOR';

  @override
  String get dailyScoreDescription => 'Yürütmeye daha iyi odaklanmanıza\nyardımcı olacak bir skor.';

  @override
  String get searchResults => 'Arama sonuçları';

  @override
  String get actionItems => 'Eylem öğeleri';

  @override
  String get tasksToday => 'Bugün';

  @override
  String get tasksTomorrow => 'Yarın';

  @override
  String get tasksNoDeadline => 'Son tarih yok';

  @override
  String get tasksLater => 'Daha sonra';

  @override
  String get loadingTasks => 'Görevler yükleniyor...';

  @override
  String get tasks => 'Görevler';

  @override
  String get swipeTasksToIndent => 'Görevleri girintili hale getirmek için kaydırın, kategoriler arasında sürükleyin';

  @override
  String get create => 'Oluştur';

  @override
  String get noTasksYet => 'Henüz görev yok';

  @override
  String get tasksFromConversationsWillAppear =>
      'Konuşmalarınızdaki görevler burada görünecek.\nManuel olarak eklemek için Oluştur\'a tıklayın.';

  @override
  String get monthJan => 'Oca';

  @override
  String get monthFeb => 'Şub';

  @override
  String get monthMar => 'Mar';

  @override
  String get monthApr => 'Nis';

  @override
  String get monthMay => 'May';

  @override
  String get monthJun => 'Haz';

  @override
  String get monthJul => 'Tem';

  @override
  String get monthAug => 'Ağu';

  @override
  String get monthSep => 'Eyl';

  @override
  String get monthOct => 'Eki';

  @override
  String get monthNov => 'Kas';

  @override
  String get monthDec => 'Ara';

  @override
  String get timePM => 'ÖS';

  @override
  String get timeAM => 'ÖÖ';

  @override
  String get actionItemUpdatedSuccessfully => 'Eylem öğesi başarıyla güncellendi';

  @override
  String get actionItemCreatedSuccessfully => 'Eylem öğesi başarıyla oluşturuldu';

  @override
  String get actionItemDeletedSuccessfully => 'Eylem öğesi başarıyla silindi';

  @override
  String get deleteActionItem => 'Eylem öğesini sil';

  @override
  String get deleteActionItemConfirmation =>
      'Bu eylem öğesini silmek istediğinizden emin misiniz? Bu işlem geri alınamaz.';

  @override
  String get enterActionItemDescription => 'Eylem öğesi açıklamasını girin...';

  @override
  String get markAsCompleted => 'Tamamlandı olarak işaretle';

  @override
  String get setDueDateAndTime => 'Bitiş tarihini ve saatini ayarla';

  @override
  String get reloadingApps => 'Uygulamalar yeniden yükleniyor...';

  @override
  String get loadingApps => 'Uygulamalar yükleniyor...';

  @override
  String get browseInstallCreateApps => 'Uygulamalara göz atın, yükleyin ve oluşturun';

  @override
  String get all => 'Tümü';

  @override
  String get open => 'Aç';

  @override
  String get install => 'Yükle';

  @override
  String get noAppsAvailable => 'Kullanılabilir uygulama yok';

  @override
  String get unableToLoadApps => 'Uygulamalar yüklenemiyor';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'Arama terimlerinizi veya filtrelerinizi ayarlamayı deneyin';

  @override
  String get checkBackLaterForNewApps => 'Yeni uygulamalar için daha sonra tekrar kontrol edin';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'Lütfen internet bağlantınızı kontrol edin ve tekrar deneyin';

  @override
  String get createNewApp => 'Yeni Uygulama Oluştur';

  @override
  String get buildSubmitCustomOmiApp => 'Özel Omi uygulamanızı oluşturun ve gönderin';

  @override
  String get submittingYourApp => 'Uygulamanız gönderiliyor...';

  @override
  String get preparingFormForYou => 'Form sizin için hazırlanıyor...';

  @override
  String get appDetails => 'Uygulama Detayları';

  @override
  String get paymentDetails => 'Ödeme Detayları';

  @override
  String get previewAndScreenshots => 'Önizleme ve Ekran Görüntüleri';

  @override
  String get appCapabilities => 'Uygulama Yetenekleri';

  @override
  String get aiPrompts => 'Yapay Zeka Yönlendirmeleri';

  @override
  String get chatPrompt => 'Sohbet Yönlendirmesi';

  @override
  String get chatPromptPlaceholder =>
      'Harika bir uygulamasınız, işiniz kullanıcı sorgularına yanıt vermek ve onları iyi hissettirmek...';

  @override
  String get conversationPrompt => 'Konuşma İstemi';

  @override
  String get conversationPromptPlaceholder =>
      'Harika bir uygulamasınız, size bir konuşmanın transkripti ve özeti verilecek...';

  @override
  String get notificationScopes => 'Bildirim Kapsamları';

  @override
  String get appPrivacyAndTerms => 'Uygulama Gizliliği ve Şartları';

  @override
  String get makeMyAppPublic => 'Uygulamamı herkese açık yap';

  @override
  String get submitAppTermsAgreement =>
      'Bu uygulamayı göndererek, Omi AI Hizmet Koşullarını ve Gizlilik Politikasını kabul ediyorum';

  @override
  String get submitApp => 'Uygulamayı Gönder';

  @override
  String get needHelpGettingStarted => 'Başlamak için yardıma mı ihtiyacınız var?';

  @override
  String get clickHereForAppBuildingGuides => 'Uygulama oluşturma kılavuzları ve belgeleri için buraya tıklayın';

  @override
  String get submitAppQuestion => 'Uygulama Gönderilsin mi?';

  @override
  String get submitAppPublicDescription =>
      'Uygulamanız incelenecek ve herkese açık hale getirilecek. İnceleme sırasında bile hemen kullanmaya başlayabilirsiniz!';

  @override
  String get submitAppPrivateDescription =>
      'Uygulamanız incelenecek ve size özel olarak sunulacak. İnceleme sırasında bile hemen kullanmaya başlayabilirsiniz!';

  @override
  String get startEarning => 'Kazanmaya Başlayın! 💰';

  @override
  String get connectStripeOrPayPal => 'Uygulamanız için ödeme almak üzere Stripe veya PayPal\'ı bağlayın.';

  @override
  String get connectNow => 'Şimdi Bağlan';

  @override
  String get installsCount => 'Yüklemeler';

  @override
  String get uninstallApp => 'Uygulamayı kaldır';

  @override
  String get subscribe => 'Abone ol';

  @override
  String get dataAccessNotice => 'Veri Erişim Bildirimi';

  @override
  String get dataAccessWarning =>
      'Bu uygulama verilerinize erişecek. Omi AI, bu uygulama tarafından verilerinizin nasıl kullanıldığı, değiştirildiği veya silindiğinden sorumlu değildir';

  @override
  String get installApp => 'Uygulamayı yükle';

  @override
  String get betaTesterNotice =>
      'Bu uygulamanın beta test kullanıcısısınız. Henüz herkese açık değil. Onaylandıktan sonra herkese açık olacak.';

  @override
  String get appUnderReviewOwner =>
      'Uygulamanız inceleniyor ve yalnızca size görünür. Onaylandıktan sonra herkese açık olacak.';

  @override
  String get appRejectedNotice =>
      'Uygulamanız reddedildi. Lütfen uygulama ayrıntılarını güncelleyin ve inceleme için yeniden gönderin.';

  @override
  String get setupSteps => 'Kurulum Adımları';

  @override
  String get setupInstructions => 'Kurulum Talimatları';

  @override
  String get integrationInstructions => 'Entegrasyon Talimatları';

  @override
  String get preview => 'Önizleme';

  @override
  String get aboutTheApp => 'Uygulama Hakkında';

  @override
  String get aboutThePersona => 'Persona Hakkında';

  @override
  String get chatPersonality => 'Sohbet Kişiliği';

  @override
  String get ratingsAndReviews => 'Puanlar ve Yorumlar';

  @override
  String get noRatings => 'puan yok';

  @override
  String ratingsCount(String count) {
    return '$count+ puan';
  }

  @override
  String get errorActivatingApp => 'Uygulamayı etkinleştirme hatası';

  @override
  String get integrationSetupRequired => 'Bu bir entegrasyon uygulamasıysa, kurulumun tamamlandığından emin olun.';

  @override
  String get installed => 'Yüklendi';

  @override
  String get appIdLabel => 'Uygulama Kimliği';

  @override
  String get appNameLabel => 'Uygulama Adı';

  @override
  String get appNamePlaceholder => 'Harika Uygulamam';

  @override
  String get pleaseEnterAppName => 'Lütfen uygulama adını girin';

  @override
  String get categoryLabel => 'Kategori';

  @override
  String get selectCategory => 'Kategori Seçin';

  @override
  String get descriptionLabel => 'Açıklama';

  @override
  String get appDescriptionPlaceholder =>
      'Harika Uygulamam harika şeyler yapan harika bir uygulamadır. En iyi uygulama!';

  @override
  String get pleaseProvideValidDescription => 'Lütfen geçerli bir açıklama sağlayın';

  @override
  String get appPricingLabel => 'Uygulama Fiyatlandırması';

  @override
  String get noneSelected => 'Seçilmedi';

  @override
  String get appIdCopiedToClipboard => 'Uygulama Kimliği panoya kopyalandı';

  @override
  String get appCategoryModalTitle => 'Uygulama Kategorisi';

  @override
  String get pricingFree => 'Ücretsiz';

  @override
  String get pricingPaid => 'Ücretli';

  @override
  String get loadingCapabilities => 'Yetenekler yükleniyor...';

  @override
  String get filterInstalled => 'Yüklü';

  @override
  String get filterMyApps => 'Uygulamalarım';

  @override
  String get clearSelection => 'Seçimi temizle';

  @override
  String get filterCategory => 'Kategori';

  @override
  String get rating4PlusStars => '4+ yıldız';

  @override
  String get rating3PlusStars => '3+ yıldız';

  @override
  String get rating2PlusStars => '2+ yıldız';

  @override
  String get rating1PlusStars => '1+ yıldız';

  @override
  String get filterRating => 'Değerlendirme';

  @override
  String get filterCapabilities => 'Yetenekler';

  @override
  String get noNotificationScopesAvailable => 'Kullanılabilir bildirim kapsamı yok';

  @override
  String get popularApps => 'Popüler Uygulamalar';

  @override
  String get pleaseProvidePrompt => 'Lütfen bir istem sağlayın';

  @override
  String chatWithAppName(String appName) {
    return '$appName ile sohbet';
  }

  @override
  String get defaultAiAssistant => 'Varsayılan AI Asistanı';

  @override
  String get readyToChat => '✨ Sohbete hazır!';

  @override
  String get connectionNeeded => '🌐 Bağlantı gerekli';

  @override
  String get startConversation => 'Bir sohbet başlatın ve büyünün başlamasına izin verin';

  @override
  String get checkInternetConnection => 'Lütfen internet bağlantınızı kontrol edin';

  @override
  String get wasThisHelpful => 'Bu yardımcı oldu mu?';

  @override
  String get thankYouForFeedback => 'Geri bildiriminiz için teşekkürler!';

  @override
  String get maxFilesUploadError => 'Aynı anda yalnızca 4 dosya yükleyebilirsiniz';

  @override
  String get attachedFiles => '📎 Ekli Dosyalar';

  @override
  String get takePhoto => 'Fotoğraf Çek';

  @override
  String get captureWithCamera => 'Kamera ile yakala';

  @override
  String get selectImages => 'Görsel Seç';

  @override
  String get chooseFromGallery => 'Galeriden seç';

  @override
  String get selectFile => 'Dosya Seç';

  @override
  String get chooseAnyFileType => 'Herhangi bir dosya türü seçin';

  @override
  String get cannotReportOwnMessages => 'Kendi mesajlarınızı bildiremezsiniz';

  @override
  String get messageReportedSuccessfully => '✅ Mesaj başarıyla bildirildi';

  @override
  String get confirmReportMessage => 'Bu mesajı bildirmek istediğinizden emin misiniz?';

  @override
  String get selectChatAssistant => 'Sohbet Asistanı Seç';

  @override
  String get enableMoreApps => 'Daha Fazla Uygulama Etkinleştir';

  @override
  String get chatCleared => 'Sohbet temizlendi';

  @override
  String get clearChatTitle => 'Sohbeti Temizle?';

  @override
  String get confirmClearChat => 'Sohbeti temizlemek istediğinizden emin misiniz? Bu işlem geri alınamaz.';

  @override
  String get copy => 'Kopyala';

  @override
  String get share => 'Paylaş';

  @override
  String get report => 'Bildir';

  @override
  String get microphonePermissionRequired => 'Ses kaydı için mikrofon izni gereklidir.';

  @override
  String get microphonePermissionDenied =>
      'Mikrofon izni reddedildi. Lütfen Sistem Tercihleri > Gizlilik ve Güvenlik > Mikrofon\'da izin verin.';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'Mikrofon izni kontrol edilemedi: $error';
  }

  @override
  String get failedToTranscribeAudio => 'Ses transkribe edilemedi';

  @override
  String get transcribing => 'Transkribe ediliyor...';

  @override
  String get transcriptionFailed => 'Transkripsiyon başarısız';

  @override
  String get discardedConversation => 'Atılan konuşma';

  @override
  String get at => 'saat';

  @override
  String get from => 'itibaren';

  @override
  String get copied => 'Kopyalandı!';

  @override
  String get copyLink => 'Bağlantıyı kopyala';

  @override
  String get hideTranscript => 'Transkripti Gizle';

  @override
  String get viewTranscript => 'Transkripti Görüntüle';

  @override
  String get conversationDetails => 'Sohbet Detayları';

  @override
  String get transcript => 'Transkript';

  @override
  String segmentsCount(int count) {
    return '$count segment';
  }

  @override
  String get noTranscriptAvailable => 'Transkript Mevcut Değil';

  @override
  String get noTranscriptMessage => 'Bu sohbetin transkripti yok.';

  @override
  String get conversationUrlCouldNotBeGenerated => 'Sohbet URL\'si oluşturulamadı.';

  @override
  String get failedToGenerateConversationLink => 'Sohbet bağlantısı oluşturulamadı';

  @override
  String get failedToGenerateShareLink => 'Paylaşım bağlantısı oluşturulamadı';

  @override
  String get reloadingConversations => 'Konuşmalar yeniden yükleniyor...';

  @override
  String get user => 'Kullanıcı';

  @override
  String get starred => 'Yıldızlı';

  @override
  String get date => 'Tarih';

  @override
  String get noResultsFound => 'Sonuç bulunamadı';

  @override
  String get tryAdjustingSearchTerms => 'Arama terimlerinizi ayarlamayı deneyin';

  @override
  String get starConversationsToFindQuickly => 'Konuşmaları burada hızlıca bulmak için yıldızlayın';

  @override
  String noConversationsOnDate(String date) {
    return '$date tarihinde konuşma yok';
  }

  @override
  String get trySelectingDifferentDate => 'Farklı bir tarih seçmeyi deneyin';

  @override
  String get conversations => 'Konuşmalar';

  @override
  String get chat => 'Sohbet';

  @override
  String get actions => 'Eylemler';

  @override
  String get syncAvailable => 'Senkronizasyon Mevcut';

  @override
  String get referAFriend => 'Arkadaş Öner';

  @override
  String get help => 'Yardım';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'Pro\'ya Yükselt';

  @override
  String get getOmiDevice => 'Omi Cihazı Edinin';

  @override
  String get wearableAiCompanion => 'Giyilebilir AI arkadaşı';

  @override
  String get loadingMemories => 'Anılar yükleniyor...';

  @override
  String get allMemories => 'Tüm anılar';

  @override
  String get aboutYou => 'Hakkınızda';

  @override
  String get manual => 'Manuel';

  @override
  String get loadingYourMemories => 'Anılarınız yükleniyor...';

  @override
  String get createYourFirstMemory => 'Başlamak için ilk anınızı oluşturun';

  @override
  String get tryAdjustingFilter => 'Aramanızı veya filtrenizi ayarlamayı deneyin';

  @override
  String get whatWouldYouLikeToRemember => 'Ne hatırlamak istersiniz?';

  @override
  String get category => 'Kategori';

  @override
  String get public => 'Herkese açık';

  @override
  String get failedToSaveCheckConnection => 'Kaydetme başarısız. Lütfen bağlantınızı kontrol edin.';

  @override
  String get createMemory => 'Hafıza oluştur';

  @override
  String get deleteMemoryConfirmation => 'Bu hafızayı silmek istediğinizden emin misiniz? Bu işlem geri alınamaz.';

  @override
  String get makePrivate => 'Özel yap';

  @override
  String get organizeAndControlMemories => 'Anılarınızı düzenleyin ve kontrol edin';

  @override
  String get total => 'Toplam';

  @override
  String get makeAllMemoriesPrivate => 'Tüm Anıları Özel Yap';

  @override
  String get setAllMemoriesToPrivate => 'Tüm anıları özel görünürlüğe ayarla';

  @override
  String get makeAllMemoriesPublic => 'Tüm Anıları Herkese Açık Yap';

  @override
  String get setAllMemoriesToPublic => 'Tüm anıları herkese açık görünürlüğe ayarla';

  @override
  String get permanentlyRemoveAllMemories => 'Omi\'den tüm anıları kalıcı olarak kaldır';

  @override
  String get allMemoriesAreNowPrivate => 'Tüm anılar artık özel';

  @override
  String get allMemoriesAreNowPublic => 'Tüm anılar artık herkese açık';

  @override
  String get clearOmisMemory => 'Omi\'nin Belleğini Temizle';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Omi\'nin belleğini temizlemek istediğinizden emin misiniz? Bu işlem geri alınamaz ve tüm $count anıyı kalıcı olarak siler.';
  }

  @override
  String get omisMemoryCleared => 'Omi\'nin senin hakkındaki belleği temizlendi';

  @override
  String get welcomeToOmi => 'Omi\'ye hoş geldiniz';

  @override
  String get continueWithApple => 'Apple ile devam et';

  @override
  String get continueWithGoogle => 'Google ile devam et';

  @override
  String get byContinuingYouAgree => 'Devam ederek ';

  @override
  String get termsOfService => 'Hizmet Koşullarını';

  @override
  String get and => ' ve ';

  @override
  String get dataAndPrivacy => 'Veri ve Gizlilik';

  @override
  String get secureAuthViaAppleId => 'Apple ID üzerinden güvenli kimlik doğrulama';

  @override
  String get secureAuthViaGoogleAccount => 'Google Hesabı üzerinden güvenli kimlik doğrulama';

  @override
  String get whatWeCollect => 'Topladıklarımız';

  @override
  String get dataCollectionMessage =>
      'Devam ederek, konuşmalarınız, kayıtlarınız ve kişisel bilgileriniz AI destekli içgörüler sağlamak ve tüm uygulama özelliklerini etkinleştirmek için sunucularımızda güvenli bir şekilde saklanacaktır.';

  @override
  String get dataProtection => 'Veri Koruması';

  @override
  String get yourDataIsProtected => 'Verileriniz korunmaktadır ve ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'Lütfen birincil dilinizi seçin';

  @override
  String get chooseYourLanguage => 'Dilinizi seçin';

  @override
  String get selectPreferredLanguageForBestExperience => 'En iyi Omi deneyimi için tercih ettiğiniz dili seçin';

  @override
  String get searchLanguages => 'Dil ara...';

  @override
  String get selectALanguage => 'Bir dil seçin';

  @override
  String get tryDifferentSearchTerm => 'Farklı bir arama terimi deneyin';

  @override
  String get pleaseEnterYourName => 'Lütfen adınızı girin';

  @override
  String get nameMustBeAtLeast2Characters => 'İsim en az 2 karakter olmalıdır';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'Nasıl hitap edilmesini istediğinizi bize söyleyin. Bu, Omi deneyiminizi kişiselleştirmeye yardımcı olur.';

  @override
  String charactersCount(int count) {
    return '$count karakter';
  }

  @override
  String get enableFeaturesForBestExperience => 'Cihazınızda en iyi Omi deneyimi için özellikleri etkinleştirin.';

  @override
  String get microphoneAccess => 'Mikrofon Erişimi';

  @override
  String get recordAudioConversations => 'Sesli konuşmaları kaydet';

  @override
  String get microphoneAccessDescription =>
      'Omi, konuşmalarınızı kaydetmek ve transkript sağlamak için mikrofon erişimine ihtiyaç duyar.';

  @override
  String get screenRecording => 'Ekran Kaydı';

  @override
  String get captureSystemAudioFromMeetings => 'Toplantılardan sistem sesini yakala';

  @override
  String get screenRecordingDescription =>
      'Omi, tarayıcı tabanlı toplantılarınızdan sistem sesini yakalamak için ekran kaydı izni gerektirir.';

  @override
  String get accessibility => 'Erişilebilirlik';

  @override
  String get detectBrowserBasedMeetings => 'Tarayıcı tabanlı toplantıları algıla';

  @override
  String get accessibilityDescription =>
      'Omi, tarayıcınızda Zoom, Meet veya Teams toplantılarına katıldığınızı algılamak için erişilebilirlik izni gerektirir.';

  @override
  String get pleaseWait => 'Lütfen bekleyin...';

  @override
  String get joinTheCommunity => 'Topluluğa katılın!';

  @override
  String get loadingProfile => 'Profil yükleniyor...';

  @override
  String get profileSettings => 'Profil Ayarları';

  @override
  String get noEmailSet => 'E-posta ayarlanmadı';

  @override
  String get userIdCopiedToClipboard => 'Kullanıcı kimliği kopyalandı';

  @override
  String get yourInformation => 'Bilgileriniz';

  @override
  String get setYourName => 'Adınızı belirleyin';

  @override
  String get changeYourName => 'Adınızı değiştirin';

  @override
  String get manageYourOmiPersona => 'Omi personanızı yönetin';

  @override
  String get voiceAndPeople => 'Ses ve İnsanlar';

  @override
  String get teachOmiYourVoice => 'Omi\'ye sesinizi öğretin';

  @override
  String get tellOmiWhoSaidIt => 'Omi\'ye kimin söylediğini söyleyin 🗣️';

  @override
  String get payment => 'Ödeme';

  @override
  String get addOrChangeYourPaymentMethod => 'Ödeme yöntemi ekleyin veya değiştirin';

  @override
  String get preferences => 'Tercihler';

  @override
  String get helpImproveOmiBySharing =>
      'Anonimleştirilmiş analitik verileri paylaşarak Omi\'yi geliştirmeye yardımcı olun';

  @override
  String get deleteAccount => 'Hesabı Sil';

  @override
  String get deleteYourAccountAndAllData => 'Hesabınızı ve tüm verilerinizi silin';

  @override
  String get clearLogs => 'Günlükleri temizle';

  @override
  String get debugLogsCleared => 'Hata ayıklama günlükleri temizlendi';

  @override
  String get exportConversations => 'Konuşmaları dışa aktar';

  @override
  String get exportAllConversationsToJson => 'Tüm konuşmalarınızı bir JSON dosyasına aktarın.';

  @override
  String get conversationsExportStarted =>
      'Konuşma dışa aktarımı başlatıldı. Bu birkaç saniye sürebilir, lütfen bekleyin.';

  @override
  String get mcpDescription =>
      'Anılarınızı ve konuşmalarınızı okumak, aramak ve yönetmek için Omi\'yi diğer uygulamalarla bağlamak için. Başlamak için bir anahtar oluşturun.';

  @override
  String get apiKeys => 'API Anahtarları';

  @override
  String errorLabel(String error) {
    return 'Hata: $error';
  }

  @override
  String get noApiKeysFound => 'API anahtarı bulunamadı. Başlamak için bir tane oluşturun.';

  @override
  String get advancedSettings => 'Gelişmiş Ayarlar';

  @override
  String get triggersWhenNewConversationCreated => 'Yeni bir konuşma oluşturulduğunda tetiklenir.';

  @override
  String get triggersWhenNewTranscriptReceived => 'Yeni bir transkript alındığında tetiklenir.';

  @override
  String get realtimeAudioBytes => 'Gerçek zamanlı ses baytları';

  @override
  String get triggersWhenAudioBytesReceived => 'Ses baytları alındığında tetiklenir.';

  @override
  String get everyXSeconds => 'Her x saniyede';

  @override
  String get triggersWhenDaySummaryGenerated => 'Günlük özet oluşturulduğunda tetiklenir.';

  @override
  String get tryLatestExperimentalFeatures => 'Omi Ekibinin en son deneysel özelliklerini deneyin.';

  @override
  String get transcriptionServiceDiagnosticStatus => 'Transkripsiyon hizmeti tanı durumu';

  @override
  String get enableDetailedDiagnosticMessages => 'Transkripsiyon hizmetinden ayrıntılı tanı mesajlarını etkinleştir';

  @override
  String get autoCreateAndTagNewSpeakers => 'Yeni konuşmacıları otomatik olarak oluştur ve etiketle';

  @override
  String get automaticallyCreateNewPerson =>
      'Transkriptte bir ad algılandığında otomatik olarak yeni bir kişi oluştur.';

  @override
  String get pilotFeatures => 'Pilot Özellikler';

  @override
  String get pilotFeaturesDescription => 'Bu özellikler testlerdir ve destek garanti edilmez.';

  @override
  String get suggestFollowUpQuestion => 'Takip sorusu öner';

  @override
  String get saveSettings => 'Ayarları Kaydet';

  @override
  String get syncingDeveloperSettings => 'Geliştirici ayarları senkronize ediliyor...';

  @override
  String get summary => 'Özet';

  @override
  String get auto => 'Otomatik';

  @override
  String get noSummaryForApp =>
      'Bu uygulama için özet mevcut değil. Daha iyi sonuçlar için başka bir uygulama deneyin.';

  @override
  String get tryAnotherApp => 'Başka Bir Uygulama Deneyin';

  @override
  String generatedBy(String appName) {
    return '$appName tarafından oluşturuldu';
  }

  @override
  String get overview => 'Genel Bakış';

  @override
  String get otherAppResults => 'Diğer Uygulama Sonuçları';

  @override
  String get unknownApp => 'Bilinmeyen uygulama';

  @override
  String get noSummaryAvailable => 'Özet Mevcut Değil';

  @override
  String get conversationNoSummaryYet => 'Bu konuşmanın henüz bir özeti yok.';

  @override
  String get chooseSummarizationApp => 'Özet Uygulaması Seçin';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName varsayılan özet uygulaması olarak ayarlandı';
  }

  @override
  String get letOmiChooseAutomatically => 'Omi\'nin en iyi uygulamayı otomatik olarak seçmesine izin verin';

  @override
  String get deleteConversationConfirmation => 'Bu sohbeti silmek istediğinizden emin misiniz? Bu işlem geri alınamaz.';

  @override
  String get conversationDeleted => 'Sohbet silindi';

  @override
  String get generatingLink => 'Bağlantı oluşturuluyor...';

  @override
  String get editConversation => 'Sohbeti düzenle';

  @override
  String get conversationLinkCopiedToClipboard => 'Sohbet bağlantısı panoya kopyalandı';

  @override
  String get conversationTranscriptCopiedToClipboard => 'Sohbet transkripti panoya kopyalandı';

  @override
  String get editConversationDialogTitle => 'Sohbeti Düzenle';

  @override
  String get changeTheConversationTitle => 'Sohbet başlığını değiştir';

  @override
  String get conversationTitle => 'Sohbet Başlığı';

  @override
  String get enterConversationTitle => 'Sohbet başlığı girin...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'Sohbet başlığı başarıyla güncellendi';

  @override
  String get failedToUpdateConversationTitle => 'Sohbet başlığı güncellenemedi';

  @override
  String get errorUpdatingConversationTitle => 'Sohbet başlığı güncellenirken hata oluştu';

  @override
  String get settingUp => 'Kuruluyor...';

  @override
  String get startYourFirstRecording => 'İlk kaydınızı başlatın';

  @override
  String get preparingSystemAudioCapture => 'Sistem ses kaydı hazırlanıyor';

  @override
  String get clickTheButtonToCaptureAudio =>
      'Canlı transkriptler, AI içgörüleri ve otomatik kaydetme için ses kaydetmek üzere düğmeye tıklayın.';

  @override
  String get reconnecting => 'Yeniden bağlanıyor...';

  @override
  String get recordingPaused => 'Kayıt duraklatıldı';

  @override
  String get recordingActive => 'Kayıt aktif';

  @override
  String get startRecording => 'Kaydı başlat';

  @override
  String resumingInCountdown(String countdown) {
    return '$countdown saniye içinde devam ediliyor...';
  }

  @override
  String get tapPlayToResume => 'Devam etmek için oynat\'a dokunun';

  @override
  String get listeningForAudio => 'Ses dinleniyor...';

  @override
  String get preparingAudioCapture => 'Ses kaydı hazırlanıyor';

  @override
  String get clickToBeginRecording => 'Kaydı başlatmak için tıklayın';

  @override
  String get translated => 'çevrildi';

  @override
  String get liveTranscript => 'Canlı Transkript';

  @override
  String segmentsSingular(String count) {
    return '$count bölüm';
  }

  @override
  String segmentsPlural(String count) {
    return '$count segment';
  }

  @override
  String get startRecordingToSeeTranscript => 'Canlı transkripti görmek için kaydı başlatın';

  @override
  String get paused => 'Duraklatıldı';

  @override
  String get initializing => 'Başlatılıyor...';

  @override
  String get recording => 'Kaydediliyor';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'Mikrofon değiştirildi. $countdown saniye içinde devam ediliyor';
  }

  @override
  String get clickPlayToResumeOrStop => 'Devam etmek için oynat\'a veya bitirmek için durdur\'a tıklayın';

  @override
  String get settingUpSystemAudioCapture => 'Sistem ses kaydı kuruluyor';

  @override
  String get capturingAudioAndGeneratingTranscript => 'Ses kaydediliyor ve transkript oluşturuluyor';

  @override
  String get clickToBeginRecordingSystemAudio => 'Sistem ses kaydını başlatmak için tıklayın';

  @override
  String get you => 'Siz';

  @override
  String speakerWithId(String speakerId) {
    return 'Konuşmacı $speakerId';
  }

  @override
  String get translatedByOmi => 'omi tarafından çevrildi';

  @override
  String get backToConversations => 'Konuşmalara dön';

  @override
  String get systemAudio => 'Sistem';

  @override
  String get mic => 'Mikrofon';

  @override
  String audioInputSetTo(String deviceName) {
    return 'Ses girişi $deviceName olarak ayarlandı';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'Ses cihazı değiştirilirken hata: $error';
  }

  @override
  String get selectAudioInput => 'Ses girişini seç';

  @override
  String get loadingDevices => 'Cihazlar yükleniyor...';

  @override
  String get settingsHeader => 'AYARLAR';

  @override
  String get plansAndBilling => 'Planlar ve Faturalama';

  @override
  String get calendarIntegration => 'Takvim Entegrasyonu';

  @override
  String get dailySummary => 'Günlük Özet';

  @override
  String get developer => 'Geliştirici';

  @override
  String get about => 'Hakkında';

  @override
  String get selectTime => 'Saat Seç';

  @override
  String get accountGroup => 'Hesap';

  @override
  String get signOutQuestion => 'Çıkış yap?';

  @override
  String get signOutConfirmation => 'Çıkış yapmak istediğinizden emin misiniz?';

  @override
  String get customVocabularyHeader => 'ÖZEL KELIME DAĞARCIĞI';

  @override
  String get addWordsDescription => 'Omin transkripsiyon sırasında tanıması gereken kelimeleri ekleyin.';

  @override
  String get enterWordsHint => 'Kelimeleri girin (virgülle ayrılmış)';

  @override
  String get dailySummaryHeader => 'GÜNLÜK ÖZET';

  @override
  String get dailySummaryTitle => 'Günlük Özet';

  @override
  String get dailySummaryDescription => 'Günün konuşmalarının kişiselleştirilmiş özetini bildirim olarak alın.';

  @override
  String get deliveryTime => 'Gönderim Saati';

  @override
  String get deliveryTimeDescription => 'Günlük özetinizi ne zaman alacağınız';

  @override
  String get subscription => 'Abonelik';

  @override
  String get viewPlansAndUsage => 'Planları ve Kullanımı Görüntüle';

  @override
  String get viewPlansDescription => 'Aboneliğinizi yönetin ve kullanım istatistiklerini görün';

  @override
  String get addOrChangePaymentMethod => 'Ödeme yönteminizi ekleyin veya değiştirin';

  @override
  String get displayOptions => 'Görüntüleme Seçenekleri';

  @override
  String get showMeetingsInMenuBar => 'Menü Çubuğunda Toplantıları Göster';

  @override
  String get displayUpcomingMeetingsDescription => 'Yaklaşan toplantıları menü çubuğunda göster';

  @override
  String get showEventsWithoutParticipants => 'Katılımcısız Etkinlikleri Göster';

  @override
  String get includePersonalEventsDescription => 'Katılımcı olmayan kişisel etkinlikleri dahil et';

  @override
  String get upcomingMeetings => 'Yaklaşan Toplantılar';

  @override
  String get checkingNext7Days => 'Sonraki 7 gün kontrol ediliyor';

  @override
  String get shortcuts => 'Kısayollar';

  @override
  String get shortcutChangeInstruction => 'Değiştirmek için bir kısayola tıklayın. İptal etmek için Escape\'e basın.';

  @override
  String get configurePersonaDescription => 'Yapay zeka kişiliğinizi yapılandırın';

  @override
  String get configureSTTProvider => 'STT sağlayıcısını yapılandır';

  @override
  String get setConversationEndDescription => 'Konuşmaların otomatik olarak ne zaman sona ereceğini ayarlayın';

  @override
  String get importDataDescription => 'Diğer kaynaklardan veri içe aktar';

  @override
  String get exportConversationsDescription => 'Konuşmaları JSON\'a aktar';

  @override
  String get exportingConversations => 'Konuşmalar dışa aktarılıyor...';

  @override
  String get clearNodesDescription => 'Tüm düğümleri ve bağlantıları temizle';

  @override
  String get deleteKnowledgeGraphQuestion => 'Bilgi Grafiği Silinsin mi?';

  @override
  String get deleteKnowledgeGraphWarning =>
      'Bu, türetilmiş tüm bilgi grafiği verilerini silecektir. Orijinal anılarınız güvende kalır.';

  @override
  String get connectOmiWithAI => 'Omi\'yi yapay zeka asistanlarıyla bağlayın';

  @override
  String get noAPIKeys => 'API anahtarı yok. Başlamak için bir tane oluşturun.';

  @override
  String get autoCreateWhenDetected => 'İsim algılandığında otomatik oluştur';

  @override
  String get trackPersonalGoals => 'Ana sayfada kişisel hedefleri izleyin';

  @override
  String get dailyReflectionDescription =>
      'Gününüzü değerlendirmek ve düşüncelerinizi kaydetmek için saat 21:00\'da hatırlatıcı alın.';

  @override
  String get endpointURL => 'Uç Nokta URL\'si';

  @override
  String get links => 'Bağlantılar';

  @override
  String get discordMemberCount => 'Discord\'da 8000\'den fazla üye';

  @override
  String get userInformation => 'Kullanıcı Bilgileri';

  @override
  String get capabilities => 'Yetenekler';

  @override
  String get previewScreenshots => 'Ekran görüntüsü önizlemesi';

  @override
  String get holdOnPreparingForm => 'Bekleyin, formu sizin için hazırlıyoruz';

  @override
  String get bySubmittingYouAgreeToOmi => 'Göndererek, Omi ';

  @override
  String get termsAndPrivacyPolicy => 'Şartlar ve Gizlilik Politikası';

  @override
  String get helpsDiagnoseIssuesAutoDeletes =>
      'Sorunların teşhisine yardımcı olur. 3 gün sonra otomatik olarak silinir.';

  @override
  String get manageYourApp => 'Uygulamanızı Yönetin';

  @override
  String get updatingYourApp => 'Uygulamanız güncelleniyor';

  @override
  String get fetchingYourAppDetails => 'Uygulama bilgileri alınıyor';

  @override
  String get updateAppQuestion => 'Uygulama güncellensin mi?';

  @override
  String get updateAppConfirmation =>
      'Uygulamanızı güncellemek istediğinizden emin misiniz? Değişiklikler ekibimiz tarafından incelendikten sonra yansıtılacaktır.';

  @override
  String get updateApp => 'Uygulamayı Güncelle';

  @override
  String get createAndSubmitNewApp => 'Yeni bir uygulama oluştur ve gönder';

  @override
  String appsCount(String count) {
    return 'Uygulamalar ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'Özel Uygulamalar ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'Herkese Açık Uygulamalar ($count)';
  }

  @override
  String get newVersionAvailable => 'Yeni Sürüm Mevcut  🎉';

  @override
  String get no => 'Hayır';

  @override
  String get subscriptionCancelledSuccessfully =>
      'Abonelik başarıyla iptal edildi. Mevcut fatura döneminin sonuna kadar aktif kalacaktır.';

  @override
  String get failedToCancelSubscription => 'Abonelik iptal edilemedi. Lütfen tekrar deneyin.';

  @override
  String get invalidPaymentUrl => 'Geçersiz ödeme URL\'si';

  @override
  String get permissionsAndTriggers => 'İzinler ve Tetikleyiciler';

  @override
  String get chatFeatures => 'Sohbet Özellikleri';

  @override
  String get uninstall => 'Kaldır';

  @override
  String get installs => 'YÜKLEMELER';

  @override
  String get priceLabel => 'FİYAT';

  @override
  String get updatedLabel => 'GÜNCELLENDİ';

  @override
  String get createdLabel => 'OLUŞTURULDU';

  @override
  String get featuredLabel => 'ÖNE ÇIKAN';

  @override
  String get cancelSubscriptionQuestion => 'Aboneliği iptal et?';

  @override
  String get cancelSubscriptionConfirmation =>
      'Aboneliğinizi iptal etmek istediğinizden emin misiniz? Mevcut fatura döneminin sonuna kadar erişiminiz devam edecektir.';

  @override
  String get cancelSubscriptionButton => 'Aboneliği İptal Et';

  @override
  String get cancelling => 'İptal ediliyor...';

  @override
  String get betaTesterMessage =>
      'Bu uygulamanın beta test kullanıcısısınız. Henüz herkese açık değil. Onaylandıktan sonra herkese açık olacak.';

  @override
  String get appUnderReviewMessage =>
      'Uygulamanız inceleniyor ve yalnızca size görünür. Onaylandıktan sonra herkese açık olacak.';

  @override
  String get appRejectedMessage => 'Uygulamanız reddedildi. Lütfen detayları güncelleyip tekrar gönderin.';

  @override
  String get invalidIntegrationUrl => 'Geçersiz entegrasyon URL';

  @override
  String get tapToComplete => 'Tamamlamak için dokun';

  @override
  String get invalidSetupInstructionsUrl => 'Geçersiz kurulum talimatları URL';

  @override
  String get pushToTalk => 'Konuşmak için Bas';

  @override
  String get summaryPrompt => 'Özet Promptu';

  @override
  String get pleaseSelectARating => 'Lütfen bir puan seçin';

  @override
  String get reviewAddedSuccessfully => 'Yorum başarıyla eklendi 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'Yorum başarıyla güncellendi 🚀';

  @override
  String get failedToSubmitReview => 'Yorum gönderilemedi. Lütfen tekrar deneyin.';

  @override
  String get addYourReview => 'Değerlendirmenizi Ekleyin';

  @override
  String get editYourReview => 'Değerlendirmenizi Düzenleyin';

  @override
  String get writeAReviewOptional => 'Bir değerlendirme yazın (isteğe bağlı)';

  @override
  String get submitReview => 'Değerlendirmeyi Gönder';

  @override
  String get updateReview => 'Değerlendirmeyi Güncelle';

  @override
  String get yourReview => 'Değerlendirmeniz';

  @override
  String get anonymousUser => 'Anonim Kullanıcı';

  @override
  String get issueActivatingApp => 'Bu uygulamayı etkinleştirirken bir sorun oluştu. Lütfen tekrar deneyin.';

  @override
  String get dataAccessNoticeDescription =>
      'Bu uygulama verilerinize erişecektir. Omi AI, verilerinizin bu uygulama tarafından nasıl kullanıldığından, değiştirildiğinden veya silindiğinden sorumlu değildir';

  @override
  String get copyUrl => 'URL\'yi Kopyala';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => 'Pzt';

  @override
  String get weekdayTue => 'Sal';

  @override
  String get weekdayWed => 'Çar';

  @override
  String get weekdayThu => 'Per';

  @override
  String get weekdayFri => 'Cum';

  @override
  String get weekdaySat => 'Cmt';

  @override
  String get weekdaySun => 'Paz';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return '$serviceName entegrasyonu yakında';
  }

  @override
  String alreadyExportedTo(String platform) {
    return '$platform platformuna zaten aktarıldı';
  }

  @override
  String get anotherPlatform => 'başka bir platform';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'Lütfen Ayarlar > Görev Entegrasyonları bölümünden $serviceName ile kimlik doğrulaması yapın';
  }

  @override
  String addingToService(String serviceName) {
    return '$serviceName platformuna ekleniyor...';
  }

  @override
  String addedToService(String serviceName) {
    return '$serviceName platformuna eklendi';
  }

  @override
  String failedToAddToService(String serviceName) {
    return '$serviceName platformuna eklenemedi';
  }

  @override
  String get permissionDeniedForAppleReminders => 'Apple Hatırlatıcılar için izin reddedildi';

  @override
  String failedToCreateApiKey(String error) {
    return 'Sağlayıcı API anahtarı oluşturulamadı: $error';
  }

  @override
  String get createAKey => 'Anahtar Oluştur';

  @override
  String get apiKeyRevokedSuccessfully => 'API anahtarı başarıyla iptal edildi';

  @override
  String failedToRevokeApiKey(String error) {
    return 'API anahtarı iptal edilemedi: $error';
  }

  @override
  String get omiApiKeys => 'Omi API Anahtarları';

  @override
  String get apiKeysDescription =>
      'API anahtarları, uygulamanız OMI sunucusuyla iletişim kurarken kimlik doğrulama için kullanılır. Uygulamanızın anılar oluşturmasına ve diğer OMI hizmetlerine güvenli bir şekilde erişmesine olanak tanır.';

  @override
  String get aboutOmiApiKeys => 'Omi API Anahtarları Hakkında';

  @override
  String get yourNewKey => 'Yeni anahtarınız:';

  @override
  String get copyToClipboard => 'Panoya kopyala';

  @override
  String get pleaseCopyKeyNow => 'Lütfen şimdi kopyalayın ve güvenli bir yere yazın. ';

  @override
  String get willNotSeeAgain => 'Tekrar göremeyeceksiniz.';

  @override
  String get revokeKey => 'Anahtarı iptal et';

  @override
  String get revokeApiKeyQuestion => 'API Anahtarını İptal Et?';

  @override
  String get revokeApiKeyWarning =>
      'Bu işlem geri alınamaz. Bu anahtarı kullanan uygulamalar artık API\'ye erişemeyecektir.';

  @override
  String get revoke => 'İptal Et';

  @override
  String get whatWouldYouLikeToCreate => 'Ne oluşturmak istersiniz?';

  @override
  String get createAnApp => 'Uygulama Oluştur';

  @override
  String get createAndShareYourApp => 'Uygulamanızı oluşturun ve paylaşın';

  @override
  String get createMyClone => 'Klonumu Oluştur';

  @override
  String get createYourDigitalClone => 'Dijital klonunuzu oluşturun';

  @override
  String get itemApp => 'Uygulama';

  @override
  String get itemPersona => 'Kişilik';

  @override
  String keepItemPublic(String item) {
    return '$item Herkese Açık Tut';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return '$item Herkese Açık Yap?';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return '$item Özel Yap?';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return '$item herkese açık yaparsanız, herkes kullanabilir';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return '$item şimdi özel yaparsanız, herkes için çalışmayı durduracak ve yalnızca size görünür olacak';
  }

  @override
  String get manageApp => 'Uygulamayı Yönet';

  @override
  String get updatePersonaDetails => 'Persona Ayrıntılarını Güncelle';

  @override
  String deleteItemTitle(String item) {
    return '$item Sil';
  }

  @override
  String deleteItemQuestion(String item) {
    return '$item Silinsin mi?';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'Bu $item silmek istediğinizden emin misiniz? Bu işlem geri alınamaz.';
  }

  @override
  String get revokeKeyQuestion => 'Anahtar İptal Edilsin mi?';

  @override
  String revokeKeyConfirmation(String keyName) {
    return '\"$keyName\" anahtarını iptal etmek istediğinizden emin misiniz? Bu işlem geri alınamaz.';
  }

  @override
  String get createNewKey => 'Yeni Anahtar Oluştur';

  @override
  String get keyNameHint => 'örn. Claude Desktop';

  @override
  String get pleaseEnterAName => 'Lütfen bir ad girin.';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'Anahtar oluşturulamadı: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'Anahtar oluşturulamadı. Lütfen tekrar deneyin.';

  @override
  String get keyCreated => 'Anahtar Oluşturuldu';

  @override
  String get keyCreatedMessage => 'Yeni anahtarınız oluşturuldu. Lütfen şimdi kopyalayın. Tekrar göremeyeceksiniz.';

  @override
  String get keyWord => 'Anahtar';

  @override
  String get externalAppAccess => 'Harici Uygulama Erişimi';

  @override
  String get externalAppAccessDescription =>
      'Aşağıdaki yüklü uygulamalar harici entegrasyonlara sahiptir ve sohbetler ve anılar gibi verilerinize erişebilir.';

  @override
  String get noExternalAppsHaveAccess => 'Hiçbir harici uygulama verilerinize erişemiyor.';

  @override
  String get maximumSecurityE2ee => 'Maksimum Güvenlik (E2EE)';

  @override
  String get e2eeDescription =>
      'Uçtan uca şifreleme, gizlilik için altın standarttır. Etkinleştirildiğinde, verileriniz sunucularımıza gönderilmeden önce cihazınızda şifrelenir. Bu, Omi dahil hiç kimsenin içeriğinize erişemeyeceği anlamına gelir.';

  @override
  String get importantTradeoffs => 'Önemli Ödünler:';

  @override
  String get e2eeTradeoff1 => '• Harici uygulama entegrasyonları gibi bazı özellikler devre dışı bırakılabilir.';

  @override
  String get e2eeTradeoff2 => '• Parolanızı kaybederseniz, verileriniz kurtarılamaz.';

  @override
  String get featureComingSoon => 'Bu özellik yakında geliyor!';

  @override
  String get migrationInProgressMessage => 'Geçiş devam ediyor. Tamamlanana kadar koruma seviyesini değiştiremezsiniz.';

  @override
  String get migrationFailed => 'Geçiş Başarısız';

  @override
  String migratingFromTo(String source, String target) {
    return '$source konumundan $target konumuna geçiş yapılıyor';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total nesne';
  }

  @override
  String get secureEncryption => 'Güvenli Şifreleme';

  @override
  String get secureEncryptionDescription =>
      'Verileriniz, Google Cloud\'da barındırılan sunucularımızda size özgü bir anahtarla şifrelenir. Bu, ham içeriğinizin Omi personeli veya Google dahil hiç kimse tarafından doğrudan veritabanından erişilemez olduğu anlamına gelir.';

  @override
  String get endToEndEncryption => 'Uçtan Uca Şifreleme';

  @override
  String get e2eeCardDescription =>
      'Yalnızca sizin verilerinize erişebildiğiniz maksimum güvenlik için etkinleştirin. Daha fazla bilgi için dokunun.';

  @override
  String get dataAlwaysEncrypted =>
      'Seviyeden bağımsız olarak, verileriniz her zaman dinlenme halinde ve aktarım sırasında şifrelenir.';

  @override
  String get readOnlyScope => 'Yalnızca Okuma';

  @override
  String get fullAccessScope => 'Tam Erişim';

  @override
  String get readScope => 'Okuma';

  @override
  String get writeScope => 'Yazma';

  @override
  String get apiKeyCreated => 'API Anahtarı Oluşturuldu!';

  @override
  String get saveKeyWarning => 'Bu anahtarı şimdi kaydedin! Tekrar göremeyeceksiniz.';

  @override
  String get yourApiKey => 'API ANAHTARINIZ';

  @override
  String get tapToCopy => 'Kopyalamak için dokunun';

  @override
  String get copyKey => 'Anahtarı Kopyala';

  @override
  String get createApiKey => 'API Anahtarı Oluştur';

  @override
  String get accessDataProgrammatically => 'Verilerinize programatik olarak erişin';

  @override
  String get keyNameLabel => 'ANAHTAR ADI';

  @override
  String get keyNamePlaceholder => 'ör., Uygulama Entegrasyonum';

  @override
  String get permissionsLabel => 'İZİNLER';

  @override
  String get permissionsInfoNote => 'R = Okuma, W = Yazma. Hiçbir şey seçilmezse varsayılan salt okunur.';

  @override
  String get developerApi => 'Geliştirici API\'si';

  @override
  String get createAKeyToGetStarted => 'Başlamak için bir anahtar oluşturun';

  @override
  String errorWithMessage(String error) {
    return 'Hata: $error';
  }

  @override
  String get omiTraining => 'Omi Eğitimi';

  @override
  String get trainingDataProgram => 'Eğitim Verisi Programı';

  @override
  String get getOmiUnlimitedFree =>
      'Verilerinizi AI modellerini eğitmek için katkıda bulunarak Omi Unlimited\'ı ücretsiz alın.';

  @override
  String get trainingDataBullets =>
      '• Verileriniz AI modellerini geliştirmeye yardımcı olur\n• Yalnızca hassas olmayan veriler paylaşılır\n• Tamamen şeffaf süreç';

  @override
  String get learnMoreAtOmiTraining => 'omi.me/training adresinde daha fazla bilgi edinin';

  @override
  String get agreeToContributeData => 'AI eğitimi için verilerimi katkıda bulunmayı anlıyorum ve kabul ediyorum';

  @override
  String get submitRequest => 'İstek Gönder';

  @override
  String get thankYouRequestUnderReview =>
      'Teşekkürler! İsteğiniz inceleniyor. Onaylandıktan sonra sizi bilgilendireceğiz.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'Planınız $date tarihine kadar aktif kalacak. Bundan sonra sınırsız özelliklerinize erişiminizi kaybedeceksiniz. Emin misiniz?';
  }

  @override
  String get confirmCancellation => 'İptali Onayla';

  @override
  String get keepMyPlan => 'Planımı Koru';

  @override
  String get subscriptionSetToCancel => 'Aboneliğiniz dönem sonunda iptal edilecek şekilde ayarlandı.';

  @override
  String get switchedToOnDevice => 'Cihaz üzerinde transkripsiyona geçildi';

  @override
  String get couldNotSwitchToFreePlan => 'Ücretsiz plana geçilemedi. Lütfen tekrar deneyin.';

  @override
  String get couldNotLoadPlans => 'Mevcut planlar yüklenemedi. Lütfen tekrar deneyin.';

  @override
  String get selectedPlanNotAvailable => 'Seçilen plan mevcut değil. Lütfen tekrar deneyin.';

  @override
  String get upgradeToAnnualPlan => 'Yıllık Plana Yükseltin';

  @override
  String get importantBillingInfo => 'Önemli Fatura Bilgileri:';

  @override
  String get monthlyPlanContinues => 'Mevcut aylık planınız fatura döneminizin sonuna kadar devam edecek';

  @override
  String get paymentMethodCharged =>
      'Aylık planınız sona erdiğinde mevcut ödeme yönteminiz otomatik olarak tahsil edilecek';

  @override
  String get annualSubscriptionStarts => '12 aylık yıllık aboneliğiniz ödeme sonrasında otomatik olarak başlayacak';

  @override
  String get thirteenMonthsCoverage => 'Toplamda 13 aylık kapsam alacaksınız (mevcut ay + 12 ay yıllık)';

  @override
  String get confirmUpgrade => 'Yükseltmeyi Onayla';

  @override
  String get confirmPlanChange => 'Plan Değişikliğini Onayla';

  @override
  String get confirmAndProceed => 'Onayla ve Devam Et';

  @override
  String get upgradeScheduled => 'Yükseltme Planlandı';

  @override
  String get changePlan => 'Planı Değiştir';

  @override
  String get upgradeAlreadyScheduled => 'Yıllık plana yükseltmeniz zaten planlandı';

  @override
  String get youAreOnUnlimitedPlan => 'Sınırsız Plan\'dasınız.';

  @override
  String get yourOmiUnleashed => 'Omi\'niz, serbest bırakıldı. Sonsuz olasılıklar için sınırsız olun.';

  @override
  String planEndedOn(String date) {
    return 'Planınız $date tarihinde sona erdi.\\nŞimdi yeniden abone olun - yeni fatura dönemi için hemen ücretlendirileceksiniz.';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'Planınız $date tarihinde iptal edilecek şekilde ayarlandı.\\nAvantajlarınızı korumak için şimdi yeniden abone olun - $date tarihine kadar ücret yok.';
  }

  @override
  String get annualPlanStartsAutomatically =>
      'Aylık planınız sona erdiğinde yıllık planınız otomatik olarak başlayacak.';

  @override
  String planRenewsOn(String date) {
    return 'Planınız $date tarihinde yenilenir.';
  }

  @override
  String get unlimitedConversations => 'Sınırsız konuşmalar';

  @override
  String get askOmiAnything => 'Hayatınız hakkında Omi\'ye her şeyi sorun';

  @override
  String get unlockOmiInfiniteMemory => 'Omi\'nin sonsuz hafızasını açın';

  @override
  String get youreOnAnnualPlan => 'Yıllık Plan\'dasınız';

  @override
  String get alreadyBestValuePlan => 'Zaten en iyi değerli plana sahipsiniz. Değişiklik gerekmiyor.';

  @override
  String get unableToLoadPlans => 'Planlar yüklenemiyor';

  @override
  String get checkConnectionTryAgain => 'Lütfen bağlantınızı kontrol edin ve tekrar deneyin';

  @override
  String get useFreePlan => 'Ücretsiz Planı Kullan';

  @override
  String get continueText => 'Devam Et';

  @override
  String get resubscribe => 'Yeniden Abone Ol';

  @override
  String get couldNotOpenPaymentSettings => 'Ödeme ayarları açılamadı. Lütfen tekrar deneyin.';

  @override
  String get managePaymentMethod => 'Ödeme Yöntemini Yönet';

  @override
  String get cancelSubscription => 'Aboneliği İptal Et';

  @override
  String endsOnDate(String date) {
    return '$date tarihinde sona erer';
  }

  @override
  String get active => 'Aktif';

  @override
  String get freePlan => 'Ücretsiz Plan';

  @override
  String get configure => 'Yapılandır';

  @override
  String get privacyInformation => 'Gizlilik Bilgileri';

  @override
  String get yourPrivacyMattersToUs => 'Gizliliğiniz Bizim İçin Önemli';

  @override
  String get privacyIntroText =>
      'Omi\'de gizliliğinizi çok ciddiye alıyoruz. Topladığımız veriler ve bunları nasıl kullandığımız konusunda şeffaf olmak istiyoruz. İşte bilmeniz gerekenler:';

  @override
  String get whatWeTrack => 'Ne Takip Ediyoruz';

  @override
  String get anonymityAndPrivacy => 'Anonimlik ve Gizlilik';

  @override
  String get optInAndOptOutOptions => 'Katılma ve Ayrılma Seçenekleri';

  @override
  String get ourCommitment => 'Taahhüdümüz';

  @override
  String get commitmentText =>
      'Topladığımız verileri yalnızca Omi\'yi sizin için daha iyi bir ürün haline getirmek için kullanmayı taahhüt ediyoruz. Gizliliğiniz ve güveniniz bizim için çok önemlidir.';

  @override
  String get thankYouText =>
      'Omi\'nin değerli bir kullanıcısı olduğunuz için teşekkür ederiz. Herhangi bir sorunuz veya endişeniz varsa, team@basedhardware.com adresinden bize ulaşmaktan çekinmeyin.';

  @override
  String get wifiSyncSettings => 'WiFi Senkronizasyon Ayarları';

  @override
  String get enterHotspotCredentials => 'Telefonunuzun hotspot kimlik bilgilerini girin';

  @override
  String get wifiSyncUsesHotspot =>
      'WiFi senkronizasyonu telefonunuzu hotspot olarak kullanır. Adı ve şifreyi Ayarlar > Kişisel Erişim Noktası\'nda bulun.';

  @override
  String get hotspotNameSsid => 'Hotspot Adı (SSID)';

  @override
  String get exampleIphoneHotspot => 'örn. iPhone Hotspot';

  @override
  String get password => 'Şifre';

  @override
  String get enterHotspotPassword => 'Hotspot şifresini girin';

  @override
  String get saveCredentials => 'Kimlik Bilgilerini Kaydet';

  @override
  String get clearCredentials => 'Kimlik Bilgilerini Temizle';

  @override
  String get pleaseEnterHotspotName => 'Lütfen bir hotspot adı girin';

  @override
  String get wifiCredentialsSaved => 'WiFi kimlik bilgileri kaydedildi';

  @override
  String get wifiCredentialsCleared => 'WiFi kimlik bilgileri temizlendi';

  @override
  String summaryGeneratedForDate(String date) {
    return '$date için özet oluşturuldu';
  }

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'Özet oluşturulamadı. O gün için konuşmalarınız olduğundan emin olun.';

  @override
  String get summaryNotFound => 'Özet bulunamadı';

  @override
  String get yourDaysJourney => 'Günün Yolculuğu';

  @override
  String get highlights => 'Öne Çıkanlar';

  @override
  String get unresolvedQuestions => 'Çözülmemiş Sorular';

  @override
  String get decisions => 'Kararlar';

  @override
  String get learnings => 'Öğrenilenler';

  @override
  String get autoDeletesAfterThreeDays => '3 gün sonra otomatik silinir.';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'Bilgi Grafiği başarıyla silindi';

  @override
  String get exportStartedMayTakeFewSeconds => 'Dışa aktarma başladı. Bu birkaç saniye sürebilir...';

  @override
  String get knowledgeGraphDeleteDescription =>
      'Bu, tüm türetilmiş bilgi grafiği verilerini (düğümler ve bağlantılar) silecektir. Orijinal anılarınız güvende kalacaktır. Grafik zamanla veya bir sonraki istekte yeniden oluşturulacaktır.';

  @override
  String get configureDailySummaryDigest => 'Günlük görev özetinizi yapılandırın';

  @override
  String accessesDataTypes(String dataTypes) {
    return '$dataTypes erişimi';
  }

  @override
  String triggeredByType(String triggerType) {
    return '$triggerType tarafından tetiklendi';
  }

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription ve $triggerDescription.';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return '$triggerDescription.';
  }

  @override
  String get noSpecificDataAccessConfigured => 'Belirli veri erişimi yapılandırılmamış.';

  @override
  String get basicPlanDescription => '1.200 premium dakika + cihazda sınırsız';

  @override
  String get minutes => 'dakika';

  @override
  String get omiHas => 'Omi:';

  @override
  String get premiumMinutesUsed => 'Premium dakikalar kullanıldı.';

  @override
  String get setupOnDevice => 'Cihazda ayarla';

  @override
  String get forUnlimitedFreeTranscription => 'sınırsız ücretsiz transkripsiyon için.';

  @override
  String premiumMinsLeft(int count) {
    return '$count premium dakika kaldı.';
  }

  @override
  String get alwaysAvailable => 'her zaman mevcut.';

  @override
  String get importHistory => 'İçe Aktarma Geçmişi';

  @override
  String get noImportsYet => 'Henüz içe aktarma yok';

  @override
  String get selectZipFileToImport => '.zip dosyasını içe aktarmak için seçin!';

  @override
  String get otherDevicesComingSoon => 'Diğer cihazlar yakında';

  @override
  String get deleteAllLimitlessConversations => 'Tüm Limitless konuşmaları silinsin mi?';

  @override
  String get deleteAllLimitlessWarning =>
      'Bu, Limitless\'tan içe aktarılan tüm konuşmaları kalıcı olarak silecektir. Bu işlem geri alınamaz.';

  @override
  String deletedLimitlessConversations(int count) {
    return '$count Limitless konuşması silindi';
  }

  @override
  String get failedToDeleteConversations => 'Konuşmalar silinemedi';

  @override
  String get deleteImportedData => 'İçe Aktarılan Verileri Sil';

  @override
  String get statusPending => 'Bekliyor';

  @override
  String get statusProcessing => 'İşleniyor';

  @override
  String get statusCompleted => 'Tamamlandı';

  @override
  String get statusFailed => 'Başarısız';

  @override
  String nConversations(int count) {
    return '$count konuşma';
  }

  @override
  String get pleaseEnterName => 'Lütfen bir ad girin';

  @override
  String get nameMustBeBetweenCharacters => 'Ad 2 ile 40 karakter arasında olmalıdır';

  @override
  String get deleteSampleQuestion => 'Örnek silinsin mi?';

  @override
  String deleteSampleConfirmation(String name) {
    return '$name örneğini silmek istediğinizden emin misiniz?';
  }

  @override
  String get confirmDeletion => 'Silmeyi Onayla';

  @override
  String deletePersonConfirmation(String name) {
    return '$name kişisini silmek istediğinizden emin misiniz? Bu aynı zamanda tüm ilişkili konuşma örneklerini de kaldıracaktır.';
  }

  @override
  String get howItWorksTitle => 'Nasıl çalışır?';

  @override
  String get howPeopleWorks =>
      'Bir kişi oluşturulduktan sonra, bir konuşma transkriptine gidebilir ve ilgili bölümleri atayabilirsiniz, böylece Omi onların konuşmasını da tanıyabilir!';

  @override
  String get tapToDelete => 'Silmek için dokunun';

  @override
  String get newTag => 'YENİ';

  @override
  String get needHelpChatWithUs => 'Yardıma mı ihtiyacınız var? Bizimle sohbet edin';

  @override
  String get localStorageEnabled => 'Yerel depolama etkinleştirildi';

  @override
  String get localStorageDisabled => 'Yerel depolama devre dışı bırakıldı';

  @override
  String failedToUpdateSettings(String error) {
    return 'Ayarlar güncellenemedi: $error';
  }

  @override
  String get privacyNotice => 'Gizlilik Bildirimi';

  @override
  String get recordingsMayCaptureOthers =>
      'Kayıtlar başkalarının seslerini yakalayabilir. Etkinleştirmeden önce tüm katılımcıların onayını aldığınızdan emin olun.';

  @override
  String get enable => 'Etkinleştir';

  @override
  String get storeAudioOnPhone => 'Sesi Telefonda Depola';

  @override
  String get on => 'On';

  @override
  String get storeAudioDescription =>
      'Tüm ses kayıtlarını telefonunuzda yerel olarak saklayın. Devre dışı bırakıldığında, depolama alanından tasarruf etmek için yalnızca başarısız yüklemeler saklanır.';

  @override
  String get enableLocalStorage => 'Yerel Depolamayı Etkinleştir';

  @override
  String get cloudStorageEnabled => 'Bulut depolama etkinleştirildi';

  @override
  String get cloudStorageDisabled => 'Bulut depolama devre dışı bırakıldı';

  @override
  String get enableCloudStorage => 'Bulut Depolamayı Etkinleştir';

  @override
  String get storeAudioOnCloud => 'Sesi Bulutta Depola';

  @override
  String get cloudStorageDialogMessage =>
      'Gerçek zamanlı kayıtlarınız konuşurken özel bulut depolamasında saklanacaktır.';

  @override
  String get storeAudioCloudDescription =>
      'Konuşurken gerçek zamanlı kayıtlarınızı özel bulut depolamasında saklayın. Ses gerçek zamanlı olarak güvenli bir şekilde yakalanır ve kaydedilir.';

  @override
  String get downloadingFirmware => 'Aygıt yazılımı indiriliyor';

  @override
  String get installingFirmware => 'Aygıt yazılımı yükleniyor';

  @override
  String get firmwareUpdateWarning => 'Uygulamayı kapatmayın veya cihazı kapatmayın. Bu, cihazınıza zarar verebilir.';

  @override
  String get firmwareUpdated => 'Aygıt yazılımı güncellendi';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'Güncellemeyi tamamlamak için lütfen $deviceName cihazınızı yeniden başlatın.';
  }

  @override
  String get yourDeviceIsUpToDate => 'Cihazınız güncel';

  @override
  String get currentVersion => 'Mevcut Sürüm';

  @override
  String get latestVersion => 'En Son Sürüm';

  @override
  String get whatsNew => 'Yenilikler';

  @override
  String get installUpdate => 'Güncellemeyi Yükle';

  @override
  String get updateNow => 'Şimdi Güncelle';

  @override
  String get updateGuide => 'Güncelleme Kılavuzu';

  @override
  String get checkingForUpdates => 'Güncellemeler kontrol ediliyor';

  @override
  String get checkingFirmwareVersion => 'Aygıt yazılımı sürümü kontrol ediliyor...';

  @override
  String get firmwareUpdate => 'Aygıt Yazılımı Güncellemesi';

  @override
  String get payments => 'Ödemeler';

  @override
  String get connectPaymentMethodInfo =>
      'Uygulamalarınız için ödeme almaya başlamak için aşağıdan bir ödeme yöntemi bağlayın.';

  @override
  String get selectedPaymentMethod => 'Seçilen Ödeme Yöntemi';

  @override
  String get availablePaymentMethods => 'Mevcut Ödeme Yöntemleri';

  @override
  String get activeStatus => 'Aktif';

  @override
  String get connectedStatus => 'Bağlandı';

  @override
  String get notConnectedStatus => 'Bağlı Değil';

  @override
  String get setActive => 'Aktif Olarak Ayarla';

  @override
  String get getPaidThroughStripe => 'Stripe üzerinden uygulama satışlarınız için ödeme alın';

  @override
  String get monthlyPayouts => 'Aylık ödemeler';

  @override
  String get monthlyPayoutsDescription => '10 \$ kazanca ulaştığınızda aylık ödemeleri doğrudan hesabınıza alın';

  @override
  String get secureAndReliable => 'Güvenli ve güvenilir';

  @override
  String get stripeSecureDescription => 'Stripe, uygulama gelirinizin güvenli ve zamanında transferini sağlar';

  @override
  String get selectYourCountry => 'Ülkenizi seçin';

  @override
  String get countrySelectionPermanent => 'Ülke seçiminiz kalıcıdır ve daha sonra değiştirilemez.';

  @override
  String get byClickingConnectNow => '\"Şimdi Bağlan\"a tıklayarak kabul etmiş olursunuz';

  @override
  String get stripeConnectedAccountAgreement => 'Stripe Bağlı Hesap Sözleşmesi';

  @override
  String get errorConnectingToStripe => 'Stripe\'a bağlanırken hata! Lütfen daha sonra tekrar deneyin.';

  @override
  String get connectingYourStripeAccount => 'Stripe hesabınız bağlanıyor';

  @override
  String get stripeOnboardingInstructions =>
      'Lütfen tarayıcınızda Stripe kayıt sürecini tamamlayın. Bu sayfa tamamlandıktan sonra otomatik olarak güncellenecektir.';

  @override
  String get failedTryAgain => 'Başarısız mı? Tekrar Dene';

  @override
  String get illDoItLater => 'Daha sonra yapacağım';

  @override
  String get successfullyConnected => 'Başarıyla Bağlandı!';

  @override
  String get stripeReadyForPayments =>
      'Stripe hesabınız artık ödeme almaya hazır. Uygulama satışlarınızdan hemen kazanmaya başlayabilirsiniz.';

  @override
  String get updateStripeDetails => 'Stripe Bilgilerini Güncelle';

  @override
  String get errorUpdatingStripeDetails => 'Stripe bilgilerini güncellerken hata! Lütfen daha sonra tekrar deneyin.';

  @override
  String get updatePayPal => 'PayPal\'ı Güncelle';

  @override
  String get setUpPayPal => 'PayPal\'ı Ayarla';

  @override
  String get updatePayPalAccountDetails => 'PayPal hesap bilgilerinizi güncelleyin';

  @override
  String get connectPayPalToReceivePayments =>
      'Uygulamalarınız için ödeme almaya başlamak için PayPal hesabınızı bağlayın';

  @override
  String get paypalEmail => 'PayPal E-postası';

  @override
  String get paypalMeLink => 'PayPal.me Bağlantısı';

  @override
  String get stripeRecommendation =>
      'Stripe ülkenizde mevcutsa, daha hızlı ve kolay ödemeler için kullanmanızı şiddetle tavsiye ederiz.';

  @override
  String get updatePayPalDetails => 'PayPal Bilgilerini Güncelle';

  @override
  String get savePayPalDetails => 'PayPal Bilgilerini Kaydet';

  @override
  String get pleaseEnterPayPalEmail => 'Lütfen PayPal e-postanızı girin';

  @override
  String get pleaseEnterPayPalMeLink => 'Lütfen PayPal.me bağlantınızı girin';

  @override
  String get doNotIncludeHttpInLink => 'Bağlantıya http veya https veya www eklemeyin';

  @override
  String get pleaseEnterValidPayPalMeLink => 'Lütfen geçerli bir PayPal.me bağlantısı girin';

  @override
  String get pleaseEnterValidEmail => 'Lütfen geçerli bir e-posta adresi girin';

  @override
  String get syncingYourRecordings => 'Kayıtlarınız senkronize ediliyor';

  @override
  String get syncYourRecordings => 'Kayıtlarınızı senkronize edin';

  @override
  String get syncNow => 'Şimdi senkronize et';

  @override
  String get error => 'Hata';

  @override
  String get speechSamples => 'Ses örnekleri';

  @override
  String additionalSampleIndex(String index) {
    return 'Ek örnek $index';
  }

  @override
  String durationSeconds(String seconds) {
    return 'Süre: $seconds saniye';
  }

  @override
  String get additionalSpeechSampleRemoved => 'Ek ses örneği kaldırıldı';

  @override
  String get consentDataMessage =>
      'Devam ederek, bu uygulamayla paylaştığınız tüm veriler (konuşmalarınız, kayıtlarınız ve kişisel bilgileriniz dahil) size yapay zeka destekli içgörüler sağlamak ve tüm uygulama özelliklerini etkinleştirmek için sunucularımızda güvenli bir şekilde saklanacaktır.';

  @override
  String get tasksEmptyStateMessage =>
      'Konuşmalarınızdaki görevler burada görünecek.\nManuel olarak oluşturmak için + simgesine dokunun.';

  @override
  String get clearChatAction => 'Sohbeti temizle';

  @override
  String get enableApps => 'Uygulamaları etkinleştir';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => 'daha fazla göster ↓';

  @override
  String get showLess => 'daha az göster ↑';

  @override
  String get loadingYourRecording => 'Kaydınız yükleniyor...';

  @override
  String get photoDiscardedMessage => 'Bu fotoğraf önemli olmadığı için silindi.';

  @override
  String get analyzing => 'Analiz ediliyor...';

  @override
  String get searchCountries => 'Ülke ara...';

  @override
  String get checkingAppleWatch => 'Apple Watch kontrol ediliyor...';

  @override
  String get installOmiOnAppleWatch => 'Apple Watch\'unuza\nOmi yükleyin';

  @override
  String get installOmiOnAppleWatchDescription =>
      'Apple Watch\'unuzu Omi ile kullanmak için önce saatinize Omi uygulamasını yüklemeniz gerekir.';

  @override
  String get openOmiOnAppleWatch => 'Apple Watch\'unuzda\nOmi\'yi açın';

  @override
  String get openOmiOnAppleWatchDescription =>
      'Omi uygulaması Apple Watch\'unuza yüklü. Açın ve başlamak için Başlat\'a dokunun.';

  @override
  String get openWatchApp => 'Watch Uygulamasını Aç';

  @override
  String get iveInstalledAndOpenedTheApp => 'Uygulamayı Yükledim ve Açtım';

  @override
  String get unableToOpenWatchApp =>
      'Apple Watch uygulaması açılamadı. Lütfen Apple Watch\'unuzda Watch uygulamasını manuel olarak açın ve \"Mevcut Uygulamalar\" bölümünden Omi\'yi yükleyin.';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch başarıyla bağlandı!';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch hala erişilebilir değil. Lütfen Omi uygulamasının saatinizde açık olduğundan emin olun.';

  @override
  String errorCheckingConnection(String error) {
    return 'Bağlantı kontrol hatası: $error';
  }

  @override
  String get muted => 'Sessiz';

  @override
  String get processNow => 'Şimdi işle';

  @override
  String get finishedConversation => 'Konuşma bitti mi?';

  @override
  String get stopRecordingConfirmation => 'Kaydı durdurmak ve konuşmayı şimdi özetlemek istediğinizden emin misiniz?';

  @override
  String get conversationEndsManually => 'Konuşma yalnızca manuel olarak sona erecektir.';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'Konuşma $minutes dakika$suffix sessizlik sonrası özetlenir.';
  }

  @override
  String get dontAskAgain => 'Bir daha sorma';

  @override
  String get waitingForTranscriptOrPhotos => 'Transkript veya fotoğraflar bekleniyor...';

  @override
  String get noSummaryYet => 'Henüz özet yok';

  @override
  String hints(String text) {
    return 'İpuçları: $text';
  }

  @override
  String get testConversationPrompt => 'Konuşma istemini test et';

  @override
  String get prompt => 'İstem';

  @override
  String get result => 'Sonuç:';

  @override
  String get compareTranscripts => 'Transkriptleri karşılaştır';

  @override
  String get notHelpful => 'Yardımcı olmadı';

  @override
  String get exportTasksWithOneTap => 'Görevleri tek dokunuşla dışa aktarın!';

  @override
  String get inProgress => 'Devam ediyor';

  @override
  String get photos => 'Fotoğraflar';

  @override
  String get rawData => 'Ham Veri';

  @override
  String get content => 'İçerik';

  @override
  String get noContentToDisplay => 'Gösterilecek içerik yok';

  @override
  String get noSummary => 'Özet yok';

  @override
  String get updateOmiFirmware => 'omi yazılımını güncelle';

  @override
  String get anErrorOccurredTryAgain => 'Bir hata oluştu. Lütfen tekrar deneyin.';

  @override
  String get welcomeBackSimple => 'Tekrar hoş geldiniz';

  @override
  String get addVocabularyDescription => 'Transkripsiyon sırasında Omi\'nin tanıması gereken kelimeleri ekleyin.';

  @override
  String get enterWordsCommaSeparated => 'Kelimeleri girin (virgülle ayırın)';

  @override
  String get whenToReceiveDailySummary => 'Günlük özetinizi ne zaman alacağınız';

  @override
  String get checkingNextSevenDays => 'Sonraki 7 gün kontrol ediliyor';

  @override
  String failedToDeleteError(String error) {
    return 'Silme başarısız: $error';
  }

  @override
  String get developerApiKeys => 'Geliştirici API Anahtarları';

  @override
  String get noApiKeysCreateOne => 'API anahtarı yok. Başlamak için bir tane oluşturun.';

  @override
  String get commandRequired => '⌘ gerekli';

  @override
  String get spaceKey => 'Boşluk';

  @override
  String loadMoreRemaining(String count) {
    return 'Daha fazla yükle ($count kaldı)';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'En iyi $percentile% kullanıcı';
  }

  @override
  String get wrappedMinutes => 'dakika';

  @override
  String get wrappedConversations => 'konuşma';

  @override
  String get wrappedDaysActive => 'aktif gün';

  @override
  String get wrappedYouTalkedAbout => 'Hakkında konuştunuz';

  @override
  String get wrappedActionItems => 'Görevler';

  @override
  String get wrappedTasksCreated => 'oluşturulan görev';

  @override
  String get wrappedCompleted => 'tamamlandı';

  @override
  String wrappedCompletionRate(String rate) {
    return '%$rate tamamlanma oranı';
  }

  @override
  String get wrappedYourTopDays => 'En iyi günleriniz';

  @override
  String get wrappedBestMoments => 'En iyi anlar';

  @override
  String get wrappedMyBuddies => 'Arkadaşlarım';

  @override
  String get wrappedCouldntStopTalkingAbout => 'Hakkında konuşmayı bırakamadım';

  @override
  String get wrappedShow => 'DİZİ';

  @override
  String get wrappedMovie => 'FİLM';

  @override
  String get wrappedBook => 'KİTAP';

  @override
  String get wrappedCelebrity => 'ÜNLÜ';

  @override
  String get wrappedFood => 'YİYECEK';

  @override
  String get wrappedMovieRecs => 'Arkadaşlar için film önerileri';

  @override
  String get wrappedBiggest => 'En büyük';

  @override
  String get wrappedStruggle => 'Zorluk';

  @override
  String get wrappedButYouPushedThrough => 'Ama başardınız 💪';

  @override
  String get wrappedWin => 'Zafer';

  @override
  String get wrappedYouDidIt => 'Başardınız! 🎉';

  @override
  String get wrappedTopPhrases => 'En çok kullanılan 5 ifade';

  @override
  String get wrappedMins => 'dk';

  @override
  String get wrappedConvos => 'sohbet';

  @override
  String get wrappedDays => 'gün';

  @override
  String get wrappedMyBuddiesLabel => 'ARKADAŞLARIM';

  @override
  String get wrappedObsessionsLabel => 'TAKINTILARI';

  @override
  String get wrappedStruggleLabel => 'ZORLUK';

  @override
  String get wrappedWinLabel => 'ZAFER';

  @override
  String get wrappedTopPhrasesLabel => 'TOP İFADELER';

  @override
  String get wrappedLetsHitRewind => 'Yılını geri saralım';

  @override
  String get wrappedGenerateMyWrapped => 'Wrapped\'ımı Oluştur';

  @override
  String get wrappedProcessingDefault => 'İşleniyor...';

  @override
  String get wrappedCreatingYourStory => '2025 hikayenizi\noluşturuyoruz...';

  @override
  String get wrappedSomethingWentWrong => 'Bir şeyler\nyanlış gitti';

  @override
  String get wrappedAnErrorOccurred => 'Bir hata oluştu';

  @override
  String get wrappedTryAgain => 'Tekrar Dene';

  @override
  String get wrappedNoDataAvailable => 'Veri mevcut değil';

  @override
  String get wrappedOmiLifeRecap => 'Omi Yaşam Özeti';

  @override
  String get wrappedSwipeUpToBegin => 'Başlamak için yukarı kaydır';

  @override
  String get wrappedShareText => '2025\'im, Omi tarafından hatırlandı ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare => 'Paylaşım başarısız. Lütfen tekrar deneyin.';

  @override
  String get wrappedFailedToStartGeneration => 'Oluşturma başlatılamadı. Lütfen tekrar deneyin.';

  @override
  String get wrappedStarting => 'Başlatılıyor...';

  @override
  String get wrappedShare => 'Paylaş';

  @override
  String get wrappedShareYourWrapped => 'Wrapped\'ını Paylaş';

  @override
  String get wrappedMy2025 => '2025\'im';

  @override
  String get wrappedRememberedByOmi => 'Omi tarafından hatırlandı';

  @override
  String get wrappedMostFunDay => 'En Eğlenceli';

  @override
  String get wrappedMostProductiveDay => 'En Verimli';

  @override
  String get wrappedMostIntenseDay => 'En Yoğun';

  @override
  String get wrappedFunniestMoment => 'En Komik';

  @override
  String get wrappedMostCringeMoment => 'En Utanç Verici';

  @override
  String get wrappedMinutesLabel => 'dakika';

  @override
  String get wrappedConversationsLabel => 'sohbet';

  @override
  String get wrappedDaysActiveLabel => 'aktif gün';

  @override
  String get wrappedTasksGenerated => 'görev oluşturuldu';

  @override
  String get wrappedTasksCompleted => 'görev tamamlandı';

  @override
  String get wrappedTopFivePhrases => 'En İyi 5 İfade';

  @override
  String get wrappedAGreatDay => 'Harika Bir Gün';

  @override
  String get wrappedGettingItDone => 'Başarmak';

  @override
  String get wrappedAChallenge => 'Bir Zorluk';

  @override
  String get wrappedAHilariousMoment => 'Komik Bir An';

  @override
  String get wrappedThatAwkwardMoment => 'O Garip An';

  @override
  String get wrappedYouHadFunnyMoments => 'Bu yıl komik anların oldu!';

  @override
  String get wrappedWeveAllBeenThere => 'Hepimiz orada bulunduk!';

  @override
  String get wrappedFriend => 'Arkadaş';

  @override
  String get wrappedYourBuddy => 'Senin dostun!';

  @override
  String get wrappedNotMentioned => 'Bahsedilmedi';

  @override
  String get wrappedTheHardPart => 'Zor Kısım';

  @override
  String get wrappedPersonalGrowth => 'Kişisel Gelişim';

  @override
  String get wrappedFunDay => 'Eğlenceli';

  @override
  String get wrappedProductiveDay => 'Verimli';

  @override
  String get wrappedIntenseDay => 'Yoğun';

  @override
  String get wrappedFunnyMomentTitle => 'Komik an';

  @override
  String get wrappedCringeMomentTitle => 'Utanç verici an';

  @override
  String get wrappedYouTalkedAboutBadge => 'Hakkında Konuştun';

  @override
  String get wrappedCompletedLabel => 'Tamamlandı';

  @override
  String get wrappedMyBuddiesCard => 'Arkadaşlarım';

  @override
  String get wrappedBuddiesLabel => 'ARKADAŞLAR';

  @override
  String get wrappedObsessionsLabelUpper => 'TAKINTILER';

  @override
  String get wrappedStruggleLabelUpper => 'MÜCADELE';

  @override
  String get wrappedWinLabelUpper => 'ZAFER';

  @override
  String get wrappedTopPhrasesLabelUpper => 'EN İYİ İFADELER';

  @override
  String get wrappedYourHeader => 'Senin';

  @override
  String get wrappedTopDaysHeader => 'En İyi Günlerin';

  @override
  String get wrappedYourTopDaysBadge => 'En iyi günlerin';

  @override
  String get wrappedBestHeader => 'En İyi';

  @override
  String get wrappedMomentsHeader => 'Anlar';

  @override
  String get wrappedBestMomentsBadge => 'En iyi anlar';

  @override
  String get wrappedBiggestHeader => 'En Büyük';

  @override
  String get wrappedStruggleHeader => 'Mücadele';

  @override
  String get wrappedWinHeader => 'Zafer';

  @override
  String get wrappedButYouPushedThroughEmoji => 'Ama başardın 💪';

  @override
  String get wrappedYouDidItEmoji => 'Başardın! 🎉';

  @override
  String get wrappedHours => 'saat';

  @override
  String get wrappedActions => 'eylem';

  @override
  String get multipleSpeakersDetected => 'Birden fazla konuşmacı tespit edildi';

  @override
  String get multipleSpeakersDescription =>
      'Kayıtta birden fazla konuşmacı var gibi görünüyor. Sessiz bir yerde olduğunuzdan emin olun ve tekrar deneyin.';

  @override
  String get invalidRecordingDetected => 'Geçersiz kayıt tespit edildi';

  @override
  String get notEnoughSpeechDescription =>
      'Yeterli konuşma tespit edilmedi. Lütfen daha fazla konuşun ve tekrar deneyin.';

  @override
  String get speechDurationDescription => 'En az 5 saniye ve en fazla 90 saniye konuştuğunuzdan emin olun.';

  @override
  String get connectionLostDescription => 'Bağlantı kesildi. İnternet bağlantınızı kontrol edin ve tekrar deneyin.';

  @override
  String get howToTakeGoodSample => 'İyi bir örnek nasıl alınır?';

  @override
  String get goodSampleInstructions =>
      '1. Sessiz bir yerde olduğunuzdan emin olun.\n2. Net ve doğal bir şekilde konuşun.\n3. Cihazınızın boynunuzda doğal konumunda olduğundan emin olun.\n\nOluşturulduktan sonra her zaman geliştirebilir veya yeniden yapabilirsiniz.';

  @override
  String get noDeviceConnectedUseMic => 'Bağlı cihaz yok. Telefon mikrofonu kullanılacak.';

  @override
  String get doItAgain => 'Tekrar yap';

  @override
  String get listenToSpeechProfile => 'Ses profilimi dinle ➡️';

  @override
  String get recognizingOthers => 'Diğerlerini tanıma 👀';

  @override
  String get keepGoingGreat => 'Devam et, harika gidiyorsun';

  @override
  String get somethingWentWrongTryAgain => 'Bir şeyler yanlış gitti! Lütfen daha sonra tekrar deneyin.';

  @override
  String get uploadingVoiceProfile => 'Ses profiliniz yükleniyor....';

  @override
  String get memorizingYourVoice => 'Sesiniz hatırlanıyor...';

  @override
  String get personalizingExperience => 'Deneyiminiz kişiselleştiriliyor...';

  @override
  String get keepSpeakingUntil100 => '%100\'e ulaşana kadar konuşmaya devam edin.';

  @override
  String get greatJobAlmostThere => 'Harika iş, neredeyse bitti';

  @override
  String get soCloseJustLittleMore => 'Çok yakın, biraz daha';

  @override
  String get notificationFrequency => 'Bildirim Sıklığı';

  @override
  String get controlNotificationFrequency =>
      'Omi\'nin size ne sıklıkta proaktif bildirimler göndereceğini kontrol edin.';

  @override
  String get yourScore => 'Skorunuz';

  @override
  String get dailyScoreBreakdown => 'Günlük Skor Detayı';

  @override
  String get todaysScore => 'Bugünün Skoru';

  @override
  String get tasksCompleted => 'Tamamlanan Görevler';

  @override
  String get completionRate => 'Tamamlanma Oranı';

  @override
  String get howItWorks => 'Nasıl çalışır';

  @override
  String get dailyScoreExplanation =>
      'Günlük skorunuz görev tamamlamaya dayanır. Skorunuzu artırmak için görevlerinizi tamamlayın!';

  @override
  String get notificationFrequencyDescription =>
      'Omi\'nin size ne sıklıkla proaktif bildirimler ve hatırlatıcılar gönderdiğini kontrol edin.';

  @override
  String get sliderOff => 'Kapalı';

  @override
  String get sliderMax => 'Maks.';

  @override
  String summaryGeneratedFor(String date) {
    return '$date için özet oluşturuldu';
  }

  @override
  String get failedToGenerateSummary => 'Özet oluşturulamadı. O gün için konuşmalarınız olduğundan emin olun.';

  @override
  String get recap => 'Özet';

  @override
  String deleteQuoted(String name) {
    return '\"$name\" öğesini sil';
  }

  @override
  String moveConversationsTo(int count) {
    return '$count konuşmayı taşı:';
  }

  @override
  String get noFolder => 'Klasör yok';

  @override
  String get removeFromAllFolders => 'Tüm klasörlerden kaldır';

  @override
  String get buildAndShareYourCustomApp => 'Özel uygulamanızı oluşturun ve paylaşın';

  @override
  String get searchAppsPlaceholder => '1500+ Uygulamada Ara';

  @override
  String get filters => 'Filtreler';

  @override
  String get frequencyOff => 'Kapalı';

  @override
  String get frequencyMinimal => 'Minimum';

  @override
  String get frequencyLow => 'Düşük';

  @override
  String get frequencyBalanced => 'Dengeli';

  @override
  String get frequencyHigh => 'Yüksek';

  @override
  String get frequencyMaximum => 'Maksimum';

  @override
  String get frequencyDescOff => 'Proaktif bildirim yok';

  @override
  String get frequencyDescMinimal => 'Sadece kritik hatırlatıcılar';

  @override
  String get frequencyDescLow => 'Sadece önemli güncellemeler';

  @override
  String get frequencyDescBalanced => 'Düzenli yararlı hatırlatıcılar';

  @override
  String get frequencyDescHigh => 'Sık kontroller';

  @override
  String get frequencyDescMaximum => 'Sürekli bağlı kalın';

  @override
  String get clearChatQuestion => 'Sohbeti temizle?';

  @override
  String get syncingMessages => 'Mesajlar sunucuyla senkronize ediliyor...';

  @override
  String get chatAppsTitle => 'Sohbet Uygulamaları';

  @override
  String get selectApp => 'Uygulama Seç';

  @override
  String get noChatAppsEnabled => 'Etkin sohbet uygulaması yok.\nEklemek için \"Uygulamaları Etkinleştir\"e dokunun.';

  @override
  String get disable => 'Devre Dışı Bırak';

  @override
  String get photoLibrary => 'Fotoğraf Kütüphanesi';

  @override
  String get chooseFile => 'Dosya Seç';

  @override
  String get configureAiPersona => 'AI kişiliğinizi yapılandırın';

  @override
  String get connectAiAssistantsToYourData => 'AI asistanlarını verilerinize bağlayın';

  @override
  String get oAuth => 'OAuth';

  @override
  String get trackYourGoalsOnHomepage => 'Ana sayfada kişisel hedeflerinizi takip edin';

  @override
  String get deleteRecording => 'Kaydı Sil';

  @override
  String get thisCannotBeUndone => 'Bu işlem geri alınamaz.';

  @override
  String get sdCard => 'SD Kart';

  @override
  String get fromSd => 'SD\'den';

  @override
  String get limitless => 'Limitless';

  @override
  String get fastTransfer => 'Hızlı aktarım';

  @override
  String get syncingStatus => 'Senkronize ediliyor';

  @override
  String get failedStatus => 'Başarısız';

  @override
  String etaLabel(String time) {
    return 'Tahmini süre: $time';
  }

  @override
  String get transferMethod => 'Aktarım yöntemi';

  @override
  String get fast => 'Hızlı';

  @override
  String get ble => 'BLE';

  @override
  String get phone => 'Telefon';

  @override
  String get cancelSync => 'Senkronizasyonu İptal Et';

  @override
  String get cancelSyncMessage => 'İndirilen veriler kaydedilecek. Daha sonra devam edebilirsiniz.';

  @override
  String get syncCancelled => 'Senkronizasyon iptal edildi';

  @override
  String get deleteProcessedFiles => 'İşlenmiş Dosyaları Sil';

  @override
  String get processedFilesDeleted => 'İşlenmiş dosyalar silindi';

  @override
  String get wifiEnableFailed => 'Cihazda WiFi etkinleştirilemedi. Lütfen tekrar deneyin.';

  @override
  String get deviceNoFastTransfer => 'Cihazınız Hızlı Aktarımı desteklemiyor. Bunun yerine Bluetooth kullanın.';

  @override
  String get enableHotspotMessage => 'Lütfen telefonunuzun erişim noktasını etkinleştirin ve tekrar deneyin.';

  @override
  String get transferStartFailed => 'Aktarım başlatılamadı. Lütfen tekrar deneyin.';

  @override
  String get deviceNotResponding => 'Cihaz yanıt vermedi. Lütfen tekrar deneyin.';

  @override
  String get invalidWifiCredentials => 'Geçersiz WiFi kimlik bilgileri. Erişim noktası ayarlarınızı kontrol edin.';

  @override
  String get wifiConnectionFailed => 'WiFi bağlantısı başarısız oldu. Lütfen tekrar deneyin.';

  @override
  String get sdCardProcessing => 'SD Kart İşleniyor';

  @override
  String sdCardProcessingMessage(int count) {
    return '$count kayıt işleniyor. Dosyalar işlendikten sonra SD karttan silinecek.';
  }

  @override
  String get process => 'İşle';

  @override
  String get wifiSyncFailed => 'WiFi Senkronizasyonu Başarısız';

  @override
  String get processingFailed => 'İşleme Başarısız';

  @override
  String get downloadingFromSdCard => 'SD Karttan İndiriliyor';

  @override
  String processingProgress(int current, int total) {
    return 'İşleniyor $current/$total';
  }

  @override
  String conversationsCreated(int count) {
    return '$count konuşma oluşturuldu';
  }

  @override
  String get internetRequired => 'İnternet gerekli';

  @override
  String get processAudio => 'Sesi İşle';

  @override
  String get start => 'Başlat';

  @override
  String get noRecordings => 'Kayıt Yok';

  @override
  String get audioFromOmiWillAppearHere => 'Omi cihazınızdan gelen ses burada görünecek';

  @override
  String get deleteProcessed => 'İşlenmişleri Sil';

  @override
  String get tryDifferentFilter => 'Farklı bir filtre deneyin';

  @override
  String get recordings => 'Kayıtlar';

  @override
  String get enableRemindersAccess =>
      'Apple Hatırlatıcılar\'ı kullanmak için lütfen Ayarlar\'da Hatırlatıcılar erişimini etkinleştirin';

  @override
  String todayAtTime(String time) {
    return 'Bugün saat $time';
  }

  @override
  String yesterdayAtTime(String time) {
    return 'Dün saat $time';
  }

  @override
  String get lessThanAMinute => 'Bir dakikadan az';

  @override
  String estimatedMinutes(int count) {
    return '~$count dakika';
  }

  @override
  String estimatedHours(int count) {
    return '~$count saat';
  }

  @override
  String estimatedTimeRemaining(String time) {
    return 'Tahmini: $time kaldı';
  }

  @override
  String get summarizingConversation => 'Konuşma özetleniyor...\nBu birkaç saniye sürebilir';

  @override
  String get resummarizingConversation => 'Konuşma yeniden özetleniyor...\nBu birkaç saniye sürebilir';

  @override
  String get nothingInterestingRetry => 'İlginç bir şey bulunamadı,\ntekrar denemek ister misiniz?';

  @override
  String get noSummaryForConversation => 'Bu konuşma için\nözet mevcut değil.';

  @override
  String get unknownLocation => 'Bilinmeyen konum';

  @override
  String get couldNotLoadMap => 'Harita yüklenemedi';

  @override
  String get triggerConversationIntegration => 'Konuşma oluşturma entegrasyonunu tetikle';

  @override
  String get webhookUrlNotSet => 'Webhook URL ayarlanmadı';

  @override
  String get setWebhookUrlInSettings => 'Bu özelliği kullanmak için geliştirici ayarlarında webhook URL\'yi ayarlayın.';

  @override
  String get sendWebUrl => 'Web URL gönder';

  @override
  String get sendTranscript => 'Transkript gönder';

  @override
  String get sendSummary => 'Özet gönder';

  @override
  String get debugModeDetected => 'Hata ayıklama modu algılandı';

  @override
  String get performanceReduced => 'Performans düşük olabilir';

  @override
  String autoClosingInSeconds(int seconds) {
    return '$seconds saniye içinde otomatik kapanıyor';
  }

  @override
  String get modelRequired => 'Model gerekli';

  @override
  String get downloadWhisperModel => 'Cihaz üzerinde transkripsiyonu kullanmak için bir whisper modeli indirin';

  @override
  String get deviceNotCompatible => 'Cihazınız cihaz üzerinde transkripsiyon ile uyumlu değil';

  @override
  String get deviceRequirements => 'Cihazınız Cihaz Üzerinde transkripsiyon gereksinimlerini karşılamıyor.';

  @override
  String get willLikelyCrash =>
      'Bu özelliği etkinleştirmek muhtemelen uygulamanın çökmesine veya donmasına neden olacaktır.';

  @override
  String get transcriptionSlowerLessAccurate => 'Transkripsiyon önemli ölçüde daha yavaş ve daha az doğru olacaktır.';

  @override
  String get proceedAnyway => 'Yine de devam et';

  @override
  String get olderDeviceDetected => 'Eski Cihaz Algılandı';

  @override
  String get onDeviceSlower => 'Bu cihazda cihaz üzerinde transkripsiyon daha yavaş olabilir.';

  @override
  String get batteryUsageHigher => 'Pil kullanımı bulut transkripsiyonundan daha yüksek olacaktır.';

  @override
  String get considerOmiCloud => 'Daha iyi performans için Omi Cloud kullanmayı düşünün.';

  @override
  String get highResourceUsage => 'Yüksek Kaynak Kullanımı';

  @override
  String get onDeviceIntensive => 'Cihaz Üzerinde transkripsiyon yoğun hesaplama gerektirir.';

  @override
  String get batteryDrainIncrease => 'Pil tüketimi önemli ölçüde artacaktır.';

  @override
  String get deviceMayWarmUp => 'Cihaz uzun süreli kullanımda ısınabilir.';

  @override
  String get speedAccuracyLower => 'Hız ve doğruluk Bulut modellerinden daha düşük olabilir.';

  @override
  String get cloudProvider => 'Bulut Sağlayıcı';

  @override
  String get premiumMinutesInfo =>
      'Ayda 1.200 premium dakika. Cihaz Üzerinde sekmesi sınırsız ücretsiz transkripsiyon sunar.';

  @override
  String get viewUsage => 'Kullanımı görüntüle';

  @override
  String get localProcessingInfo =>
      'Ses yerel olarak işlenir. Çevrimdışı çalışır, daha güvenlidir, ancak daha fazla pil kullanır.';

  @override
  String get model => 'Model';

  @override
  String get performanceWarning => 'Performans Uyarısı';

  @override
  String get largeModelWarning =>
      'Bu model büyük ve uygulamanın çökmesine veya mobil cihazlarda çok yavaş çalışmasına neden olabilir.\n\n\"small\" veya \"base\" önerilir.';

  @override
  String get usingNativeIosSpeech => 'Yerel iOS Konuşma Tanıma Kullanılıyor';

  @override
  String get noModelDownloadRequired => 'Cihazınızın yerel konuşma motoru kullanılacak. Model indirmesi gerekmiyor.';

  @override
  String get modelReady => 'Model Hazır';

  @override
  String get redownload => 'Yeniden İndir';

  @override
  String get doNotCloseApp => 'Lütfen uygulamayı kapatmayın.';

  @override
  String get downloading => 'İndiriliyor...';

  @override
  String get downloadModel => 'Modeli indir';

  @override
  String estimatedSize(String size) {
    return 'Tahmini Boyut: ~$size MB';
  }

  @override
  String availableSpace(String space) {
    return 'Kullanılabilir Alan: $space';
  }

  @override
  String get notEnoughSpace => 'Uyarı: Yeterli alan yok!';

  @override
  String get download => 'İndir';

  @override
  String downloadError(String error) {
    return 'İndirme hatası: $error';
  }

  @override
  String get cancelled => 'İptal edildi';

  @override
  String get deviceNotCompatibleTitle => 'Cihaz Uyumlu Değil';

  @override
  String get deviceNotMeetRequirements => 'Cihazınız cihaz üzerinde transkripsiyon gereksinimlerini karşılamıyor.';

  @override
  String get transcriptionSlowerOnDevice => 'Bu cihazda cihaz üzerinde transkripsiyon daha yavaş olabilir.';

  @override
  String get computationallyIntensive => 'Cihaz üzerinde transkripsiyon hesaplama açısından yoğundur.';

  @override
  String get batteryDrainSignificantly => 'Pil tüketimi önemli ölçüde artacaktır.';

  @override
  String get premiumMinutesMonth =>
      'Ayda 1.200 premium dakika. Cihaz Üzerinde sekmesi sınırsız ücretsiz transkripsiyon sunar. ';

  @override
  String get audioProcessedLocally =>
      'Ses yerel olarak işlenir. Çevrimdışı çalışır, daha özel, ancak daha fazla pil kullanır.';

  @override
  String get languageLabel => 'Dil';

  @override
  String get modelLabel => 'Model';

  @override
  String get modelTooLargeWarning =>
      'Bu model büyük ve mobil cihazlarda uygulamanın çökmesine veya çok yavaş çalışmasına neden olabilir.\n\nsmall veya base önerilir.';

  @override
  String get nativeEngineNoDownload => 'Cihazınızın yerel konuşma motoru kullanılacak. Model indirmesi gerekli değil.';

  @override
  String modelReadyWithName(String model) {
    return 'Model Hazır ($model)';
  }

  @override
  String get reDownload => 'Yeniden indir';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return '$model indiriliyor: $received / $total MB';
  }

  @override
  String preparingModel(String model) {
    return '$model hazırlanıyor...';
  }

  @override
  String downloadErrorWithMessage(String error) {
    return 'İndirme hatası: $error';
  }

  @override
  String estimatedSizeWithValue(String size) {
    return 'Tahmini Boyut: ~$size MB';
  }

  @override
  String availableSpaceWithValue(String space) {
    return 'Kullanılabilir Alan: $space';
  }

  @override
  String get omiTranscriptionOptimized =>
      'Ominin yerleşik canlı transkripsiyonu, otomatik konuşmacı algılama ve diarizasyon ile gerçek zamanlı konuşmalar için optimize edilmiştir.';

  @override
  String get reset => 'Sıfırla';

  @override
  String get useTemplateFrom => 'Şablonu kullan';

  @override
  String get selectProviderTemplate => 'Bir sağlayıcı şablonu seçin...';

  @override
  String get quicklyPopulateResponse => 'Bilinen sağlayıcı yanıt formatıyla hızlıca doldur';

  @override
  String get quicklyPopulateRequest => 'Bilinen sağlayıcı istek formatıyla hızlıca doldur';

  @override
  String get invalidJsonError => 'Geçersiz JSON';

  @override
  String downloadModelWithName(String model) {
    return 'Model İndir ($model)';
  }

  @override
  String modelNameWithFile(String model) {
    return 'Model: $model';
  }

  @override
  String get device => 'Cihaz';

  @override
  String get chatAssistantsTitle => 'Sohbet Asistanları';

  @override
  String get permissionReadConversations => 'Konuşmaları Oku';

  @override
  String get permissionReadMemories => 'Anıları Oku';

  @override
  String get permissionReadTasks => 'Görevleri Oku';

  @override
  String get permissionCreateConversations => 'Konuşma Oluştur';

  @override
  String get permissionCreateMemories => 'Anı Oluştur';

  @override
  String get permissionTypeAccess => 'Erişim';

  @override
  String get permissionTypeCreate => 'Oluştur';

  @override
  String get permissionTypeTrigger => 'Tetikleyici';

  @override
  String get permissionDescReadConversations => 'Bu uygulama konuşmalarınıza erişebilir.';

  @override
  String get permissionDescReadMemories => 'Bu uygulama anılarınıza erişebilir.';

  @override
  String get permissionDescReadTasks => 'Bu uygulama görevlerinize erişebilir.';

  @override
  String get permissionDescCreateConversations => 'Bu uygulama yeni konuşmalar oluşturabilir.';

  @override
  String get permissionDescCreateMemories => 'Bu uygulama yeni anılar oluşturabilir.';

  @override
  String get realtimeListening => 'Gerçek Zamanlı Dinleme';

  @override
  String get setupCompleted => 'Tamamlandı';

  @override
  String get pleaseSelectRating => 'Lütfen bir puan seçin';

  @override
  String get writeReviewOptional => 'Yorum yaz (isteğe bağlı)';

  @override
  String get setupQuestionsIntro => 'Birkaç soruyu yanıtlayarak Omi\'yi geliştirmemize yardımcı olun.  🫶 💜';

  @override
  String get setupQuestionProfession => '1. Ne iş yapıyorsunuz?';

  @override
  String get setupQuestionUsage => '2. Omi\'yi nerede kullanmayı planlıyorsunuz?';

  @override
  String get setupQuestionAge => '3. Yaş aralığınız nedir?';

  @override
  String get setupAnswerAllQuestions => 'Henüz tüm soruları yanıtlamadınız! 🥺';

  @override
  String get setupSkipHelp => 'Atla, yardım etmek istemiyorum :C';

  @override
  String get professionEntrepreneur => 'Girişimci';

  @override
  String get professionSoftwareEngineer => 'Yazılım Mühendisi';

  @override
  String get professionProductManager => 'Ürün Yöneticisi';

  @override
  String get professionExecutive => 'Yönetici';

  @override
  String get professionSales => 'Satış';

  @override
  String get professionStudent => 'Öğrenci';

  @override
  String get usageAtWork => 'İşte';

  @override
  String get usageIrlEvents => 'Gerçek Hayat Etkinliklerinde';

  @override
  String get usageOnline => 'Çevrimiçi';

  @override
  String get usageSocialSettings => 'Sosyal Ortamlarda';

  @override
  String get usageEverywhere => 'Her Yerde';

  @override
  String get customBackendUrlTitle => 'Özel Sunucu URL';

  @override
  String get backendUrlLabel => 'Sunucu URL';

  @override
  String get saveUrlButton => 'URL\'yi Kaydet';

  @override
  String get enterBackendUrlError => 'Lütfen sunucu URL\'sini girin';

  @override
  String get urlMustEndWithSlashError => 'URL \"/\" ile bitmelidir';

  @override
  String get invalidUrlError => 'Lütfen geçerli bir URL girin';

  @override
  String get backendUrlSavedSuccess => 'Sunucu URL başarıyla kaydedildi!';

  @override
  String get signInTitle => 'Giriş Yap';

  @override
  String get signInButton => 'Giriş Yap';

  @override
  String get enterEmailError => 'Lütfen e-postanızı girin';

  @override
  String get invalidEmailError => 'Lütfen geçerli bir e-posta girin';

  @override
  String get enterPasswordError => 'Lütfen şifrenizi girin';

  @override
  String get passwordMinLengthError => 'Şifre en az 8 karakter olmalıdır';

  @override
  String get signInSuccess => 'Giriş başarılı!';

  @override
  String get alreadyHaveAccountLogin => 'Zaten hesabınız var mı? Giriş yapın';

  @override
  String get emailLabel => 'E-posta';

  @override
  String get passwordLabel => 'Şifre';

  @override
  String get createAccountTitle => 'Hesap Oluştur';

  @override
  String get nameLabel => 'Ad';

  @override
  String get repeatPasswordLabel => 'Şifreyi Tekrarla';

  @override
  String get signUpButton => 'Kaydol';

  @override
  String get enterNameError => 'Lütfen adınızı girin';

  @override
  String get passwordsDoNotMatch => 'Şifreler eşleşmiyor';

  @override
  String get signUpSuccess => 'Kayıt başarılı!';

  @override
  String get loadingKnowledgeGraph => 'Bilgi grafiği yükleniyor...';

  @override
  String get noKnowledgeGraphYet => 'Henüz bilgi grafiği yok';

  @override
  String get buildingKnowledgeGraphFromMemories => 'Anılardan bilgi grafiği oluşturuluyor...';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'Yeni anılar oluşturdukça bilgi grafiğiniz otomatik olarak oluşturulacak.';

  @override
  String get buildGraphButton => 'Grafik Oluştur';

  @override
  String get checkOutMyMemoryGraph => 'Hafıza grafiğime göz atın!';

  @override
  String get getButton => 'Al';

  @override
  String openingApp(String appName) {
    return '$appName açılıyor...';
  }

  @override
  String get writeSomething => 'Bir şeyler yazın';

  @override
  String get submitReply => 'Yanıt Gönder';

  @override
  String get editYourReply => 'Yanıtını Düzenle';

  @override
  String get replyToReview => 'Yoruma Yanıt Ver';

  @override
  String get rateAndReviewThisApp => 'Bu uygulamayı değerlendirin ve yorum yazın';

  @override
  String get noChangesInReview => 'Güncellenecek yorum değişikliği yok.';

  @override
  String get cantRateWithoutInternet => 'İnternet bağlantısı olmadan uygulama değerlendirilemez.';

  @override
  String get appAnalytics => 'Uygulama Analitiği';

  @override
  String get learnMoreLink => 'daha fazla bilgi';

  @override
  String get moneyEarned => 'Kazanılan para';

  @override
  String get writeYourReply => 'Yanıtınızı yazın...';

  @override
  String get replySentSuccessfully => 'Yanıt başarıyla gönderildi';

  @override
  String failedToSendReply(String error) {
    return 'Yanıt gönderilemedi: $error';
  }

  @override
  String get send => 'Gönder';

  @override
  String starFilter(int count) {
    return '$count Yıldız';
  }

  @override
  String get noReviewsFound => 'Yorum Bulunamadı';

  @override
  String get editReply => 'Yanıtı Düzenle';

  @override
  String get reply => 'Yanıtla';

  @override
  String starFilterLabel(int count) {
    return '$count yıldız';
  }

  @override
  String get sharePublicLink => 'Herkese Açık Bağlantıyı Paylaş';

  @override
  String get makePersonaPublic => 'Kişiliği Herkese Açık Yap';

  @override
  String get connectedKnowledgeData => 'Bağlı Bilgi Verisi';

  @override
  String get enterName => 'Ad girin';

  @override
  String get disconnectTwitter => 'Twitter\'ı Bağlantıdan Kes';

  @override
  String get disconnectTwitterConfirmation =>
      'Twitter hesabınızı bağlantıdan kesmek istediğinizden emin misiniz? Kişiliğiniz artık Twitter verilerinize erişemeyecek.';

  @override
  String get getOmiDeviceDescription => 'Kişisel konuşmalarınızla daha doğru bir klon oluşturun';

  @override
  String get getOmi => 'Omi Edinin';

  @override
  String get iHaveOmiDevice => 'Omi cihazım var';

  @override
  String get goal => 'HEDEF';

  @override
  String get tapToTrackThisGoal => 'Bu hedefi takip etmek için dokun';

  @override
  String get tapToSetAGoal => 'Bir hedef belirlemek için dokun';

  @override
  String get processedConversations => 'İşlenmiş Konuşmalar';

  @override
  String get updatedConversations => 'Güncellenen Konuşmalar';

  @override
  String get newConversations => 'Yeni Konuşmalar';

  @override
  String get summaryTemplate => 'Özet Şablonu';

  @override
  String get suggestedTemplates => 'Önerilen Şablonlar';

  @override
  String get otherTemplates => 'Diğer Şablonlar';

  @override
  String get availableTemplates => 'Mevcut Şablonlar';

  @override
  String get getCreative => 'Yaratıcı Ol';

  @override
  String get defaultLabel => 'Varsayılan';

  @override
  String get lastUsedLabel => 'Son Kullanılan';

  @override
  String get setDefaultApp => 'Varsayılan Uygulamayı Ayarla';

  @override
  String setDefaultAppContent(String appName) {
    return '$appName varsayılan özet uygulamanız olarak ayarlansın mı?\\n\\nBu uygulama gelecekteki tüm konuşma özetleri için otomatik olarak kullanılacaktır.';
  }

  @override
  String get setDefaultButton => 'Varsayılan Olarak Ayarla';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName varsayılan özet uygulaması olarak ayarlandı';
  }

  @override
  String get createCustomTemplate => 'Özel Şablon Oluştur';

  @override
  String get allTemplates => 'Tüm Şablonlar';

  @override
  String failedToInstallApp(String appName) {
    return '$appName yüklenemedi. Lütfen tekrar deneyin.';
  }

  @override
  String errorInstallingApp(String appName, String error) {
    return '$appName yüklenirken hata oluştu: $error';
  }

  @override
  String tagSpeaker(int speakerId) {
    return 'Konuşmacıyı Etiketle $speakerId';
  }

  @override
  String get personNameAlreadyExists => 'Bu isimde bir kişi zaten mevcut.';

  @override
  String get selectYouFromList => 'Kendinizi etiketlemek için lütfen listeden \"Sen\" seçeneğini seçin.';

  @override
  String get enterPersonsName => 'Kişinin Adını Girin';

  @override
  String get addPerson => 'Kişi Ekle';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'Bu konuşmacıdan diğer bölümleri etiketle ($selected/$total)';
  }

  @override
  String get tagOtherSegments => 'Diğer bölümleri etiketle';

  @override
  String get managePeople => 'Kişileri Yönet';

  @override
  String get shareViaSms => 'SMS ile paylaş';

  @override
  String get selectContactsToShareSummary => 'Konuşma özetinizi paylaşmak için kişileri seçin';

  @override
  String get searchContactsHint => 'Kişileri ara...';

  @override
  String contactsSelectedCount(int count) {
    return '$count seçildi';
  }

  @override
  String get clearAllSelection => 'Tümünü temizle';

  @override
  String get selectContactsToShare => 'Paylaşılacak kişileri seçin';

  @override
  String shareWithContactCount(int count) {
    return '$count kişiyle paylaş';
  }

  @override
  String shareWithContactsCount(int count) {
    return '$count kişiyle paylaş';
  }

  @override
  String get contactsPermissionRequired => 'Kişi izni gerekli';

  @override
  String get contactsPermissionRequiredForSms => 'SMS ile paylaşmak için kişi izni gereklidir';

  @override
  String get grantContactsPermissionForSms => 'SMS ile paylaşmak için lütfen kişi izni verin';

  @override
  String get noContactsWithPhoneNumbers => 'Telefon numarası olan kişi bulunamadı';

  @override
  String get noContactsMatchSearch => 'Aramanızla eşleşen kişi yok';

  @override
  String get failedToLoadContacts => 'Kişiler yüklenemedi';

  @override
  String get failedToPrepareConversationForSharing => 'Konuşma paylaşım için hazırlanamadı. Lütfen tekrar deneyin.';

  @override
  String get couldNotOpenSmsApp => 'SMS uygulaması açılamadı. Lütfen tekrar deneyin.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'Az önce konuştuklarımız: $link';
  }

  @override
  String get wifiSync => 'WiFi Senkronizasyonu';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item panoya kopyalandı';
  }

  @override
  String get wifiConnectionFailedTitle => 'Bağlantı Başarısız';

  @override
  String connectingToDeviceName(String deviceName) {
    return '$deviceName cihazına bağlanılıyor';
  }

  @override
  String enableDeviceWifi(String deviceName) {
    return '$deviceName WiFi\'sini etkinleştir';
  }

  @override
  String connectToDeviceName(String deviceName) {
    return '$deviceName cihazına bağlan';
  }

  @override
  String get recordingDetails => 'Kayıt Detayları';

  @override
  String get storageLocationSdCard => 'SD Kart';

  @override
  String get storageLocationLimitlessPendant => 'Limitless Kolye';

  @override
  String get storageLocationPhone => 'Telefon';

  @override
  String get storageLocationPhoneMemory => 'Telefon (Bellek)';

  @override
  String storedOnDevice(String deviceName) {
    return '$deviceName üzerinde depolandı';
  }

  @override
  String get transferring => 'Aktarılıyor...';

  @override
  String get transferRequired => 'Aktarım Gerekli';

  @override
  String get downloadingAudioFromSdCard => 'Cihazınızın SD kartından ses indiriliyor';

  @override
  String get transferRequiredDescription =>
      'Bu kayıt cihazınızın SD kartında depolanıyor. Çalmak veya paylaşmak için telefonunuza aktarın.';

  @override
  String get cancelTransfer => 'Aktarımı İptal Et';

  @override
  String get transferToPhone => 'Telefona Aktar';

  @override
  String get privateAndSecureOnDevice => 'Cihazınızda gizli ve güvenli';

  @override
  String get recordingInfo => 'Kayıt Bilgisi';

  @override
  String get transferInProgress => 'Aktarım devam ediyor...';

  @override
  String get shareRecording => 'Kaydı Paylaş';

  @override
  String get deleteRecordingConfirmation =>
      'Bu kaydı kalıcı olarak silmek istediğinizden emin misiniz? Bu işlem geri alınamaz.';

  @override
  String get recordingIdLabel => 'Kayıt Kimliği';

  @override
  String get dateTimeLabel => 'Tarih ve Saat';

  @override
  String get durationLabel => 'Süre';

  @override
  String get audioFormatLabel => 'Ses Formatı';

  @override
  String get storageLocationLabel => 'Depolama Konumu';

  @override
  String get estimatedSizeLabel => 'Tahmini Boyut';

  @override
  String get deviceModelLabel => 'Cihaz Modeli';

  @override
  String get deviceIdLabel => 'Cihaz Kimliği';

  @override
  String get statusLabel => 'Durum';

  @override
  String get statusProcessed => 'İşlendi';

  @override
  String get statusUnprocessed => 'İşlenmedi';

  @override
  String get switchedToFastTransfer => 'Hızlı Aktarıma geçildi';

  @override
  String get transferCompleteMessage => 'Aktarım tamamlandı! Bu kaydı artık çalabilirsiniz.';

  @override
  String transferFailedMessage(String error) {
    return 'Aktarım başarısız: $error';
  }

  @override
  String get transferCancelled => 'Aktarım iptal edildi';

  @override
  String get fastTransferEnabled => 'Hızlı aktarım etkinleştirildi';

  @override
  String get bluetoothSyncEnabled => 'Bluetooth senkronizasyonu etkinleştirildi';

  @override
  String get enableFastTransfer => 'Hızlı aktarımı etkinleştir';

  @override
  String get fastTransferDescription =>
      'Hızlı aktarım, ~5 kat daha hızlı hızlar için WiFi kullanır. Telefonunuz aktarım sırasında geçici olarak Omi cihazınızın WiFi ağına bağlanacaktır.';

  @override
  String get internetAccessPausedDuringTransfer => 'Aktarım sırasında internet erişimi duraklatıldı';

  @override
  String get chooseTransferMethodDescription => 'Kayıtların Omi cihazından telefonunuza nasıl aktarılacağını seçin.';

  @override
  String get wifiSpeed => 'WiFi ile ~150 KB/s';

  @override
  String get fiveTimesFaster => '5 KAT DAHA HIZLI';

  @override
  String get fastTransferMethodDescription =>
      'Omi cihazınıza doğrudan WiFi bağlantısı oluşturur. Telefonunuz aktarım sırasında geçici olarak normal WiFi bağlantısını keser.';

  @override
  String get bluetooth => 'Bluetooth';

  @override
  String get bleSpeed => 'BLE ile ~30 KB/s';

  @override
  String get bluetoothMethodDescription =>
      'Standart Bluetooth Low Energy bağlantısı kullanır. Daha yavaş ama WiFi bağlantınızı etkilemez.';

  @override
  String get selected => 'Seçildi';

  @override
  String get selectOption => 'Seç';

  @override
  String get lowBatteryAlertTitle => 'Düşük Pil Uyarısı';

  @override
  String get lowBatteryAlertBody => 'Cihazınızın pili azaldı. Şarj etme zamanı! 🔋';

  @override
  String get deviceDisconnectedNotificationTitle => 'Omi Cihazınız Bağlantı Kesildi';

  @override
  String get deviceDisconnectedNotificationBody => 'Omi\'yi kullanmaya devam etmek için lütfen yeniden bağlanın.';

  @override
  String get firmwareUpdateAvailable => 'Yazılım Güncellemesi Mevcut';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'Omi cihazınız için yeni bir yazılım güncellemesi ($version) mevcut. Şimdi güncellemek ister misiniz?';
  }

  @override
  String get later => 'Daha sonra';

  @override
  String get appDeletedSuccessfully => 'Uygulama başarıyla silindi';

  @override
  String get appDeleteFailed => 'Uygulama silinemedi. Lütfen daha sonra tekrar deneyin.';

  @override
  String get appVisibilityChangedSuccessfully =>
      'Uygulama görünürlüğü başarıyla değiştirildi. Yansıması birkaç dakika sürebilir.';

  @override
  String get errorActivatingAppIntegration =>
      'Uygulama etkinleştirilirken hata oluştu. Bu bir entegrasyon uygulamasıysa, kurulumun tamamlandığından emin olun.';

  @override
  String get errorUpdatingAppStatus => 'Uygulama durumu güncellenirken bir hata oluştu.';

  @override
  String get calculatingETA => 'Hesaplanıyor...';

  @override
  String aboutMinutesRemaining(int minutes) {
    return 'Yaklaşık $minutes dakika kaldı';
  }

  @override
  String get aboutAMinuteRemaining => 'Yaklaşık bir dakika kaldı';

  @override
  String get almostDone => 'Neredeyse tamamlandı...';

  @override
  String get omiSays => 'omi diyor ki';

  @override
  String get analyzingYourData => 'Verileriniz analiz ediliyor...';

  @override
  String migratingToProtection(String level) {
    return '$level korumaya geçiliyor...';
  }

  @override
  String get noDataToMigrateFinalizing => 'Taşınacak veri yok. Tamamlanıyor...';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return '$itemType taşınıyor... %$percentage';
  }

  @override
  String get allObjectsMigratedFinalizing => 'Tüm nesneler taşındı. Tamamlanıyor...';

  @override
  String get migrationErrorOccurred => 'Taşıma sırasında bir hata oluştu. Lütfen tekrar deneyin.';

  @override
  String get migrationComplete => 'Taşıma tamamlandı!';

  @override
  String dataProtectedWithSettings(String level) {
    return 'Verileriniz artık yeni $level ayarlarıyla korunuyor.';
  }

  @override
  String get chatsLowercase => 'sohbetler';

  @override
  String get dataLowercase => 'veriler';

  @override
  String get fallNotificationTitle => 'Ayy';

  @override
  String get fallNotificationBody => 'Düştünüz mü?';

  @override
  String get importantConversationTitle => 'Önemli Konuşma';

  @override
  String get importantConversationBody => 'Az önce önemli bir konuşma yaptınız. Özeti paylaşmak için dokunun.';

  @override
  String get templateName => 'Şablon Adı';

  @override
  String get templateNameHint => 'örn. Toplantı Eylem Maddeleri Çıkarıcı';

  @override
  String get nameMustBeAtLeast3Characters => 'Ad en az 3 karakter olmalıdır';

  @override
  String get conversationPromptHint =>
      'örn., Verilen konuşmadan eylem maddeleri, alınan kararlar ve önemli çıkarımları çıkarın.';

  @override
  String get pleaseEnterAppPrompt => 'Lütfen uygulamanız için bir istem girin';

  @override
  String get promptMustBeAtLeast10Characters => 'İstem en az 10 karakter olmalıdır';

  @override
  String get anyoneCanDiscoverTemplate => 'Herkes şablonunuzu keşfedebilir';

  @override
  String get onlyYouCanUseTemplate => 'Bu şablonu yalnızca siz kullanabilirsiniz';

  @override
  String get generatingDescription => 'Açıklama oluşturuluyor...';

  @override
  String get creatingAppIcon => 'Uygulama simgesi oluşturuluyor...';

  @override
  String get installingApp => 'Uygulama yükleniyor...';

  @override
  String get appCreatedAndInstalled => 'Uygulama oluşturuldu ve yüklendi!';

  @override
  String get appCreatedSuccessfully => 'Uygulama başarıyla oluşturuldu!';

  @override
  String get failedToCreateApp => 'Uygulama oluşturulamadı. Lütfen tekrar deneyin.';

  @override
  String get addAppSelectCoreCapability => 'Uygulamanız için bir temel yetenek daha seçin';

  @override
  String get addAppSelectPaymentPlan => 'Bir ödeme planı seçin ve uygulamanız için fiyat girin';

  @override
  String get addAppSelectCapability => 'Uygulamanız için en az bir yetenek seçin';

  @override
  String get addAppSelectLogo => 'Uygulamanız için bir logo seçin';

  @override
  String get addAppEnterChatPrompt => 'Uygulamanız için bir sohbet istemi girin';

  @override
  String get addAppEnterConversationPrompt => 'Uygulamanız için bir konuşma istemi girin';

  @override
  String get addAppSelectTriggerEvent => 'Uygulamanız için bir tetikleyici olay seçin';

  @override
  String get addAppEnterWebhookUrl => 'Uygulamanız için bir webhook URL\'si girin';

  @override
  String get addAppSelectCategory => 'Uygulamanız için bir kategori seçin';

  @override
  String get addAppFillRequiredFields => 'Tüm gerekli alanları doğru şekilde doldurun';

  @override
  String get addAppUpdatedSuccess => 'Uygulama başarıyla güncellendi 🚀';

  @override
  String get addAppUpdateFailed => 'Güncelleme başarısız. Daha sonra tekrar deneyin';

  @override
  String get addAppSubmittedSuccess => 'Uygulama başarıyla gönderildi 🚀';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'Dosya seçici açılırken hata: $message';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'Görsel seçilirken hata: $error';
  }

  @override
  String get addAppPhotosPermissionDenied => 'Fotoğraf izni reddedildi. Fotoğraflara erişime izin verin';

  @override
  String get addAppErrorSelectingImageRetry => 'Görsel seçilirken hata. Tekrar deneyin.';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'Küçük resim seçilirken hata: $error';
  }

  @override
  String get addAppErrorSelectingThumbnailRetry => 'Küçük resim seçilirken hata. Tekrar deneyin.';

  @override
  String get addAppCapabilityConflictWithPersona => 'Diğer yetenekler Persona ile birlikte seçilemez';

  @override
  String get addAppPersonaConflictWithCapabilities => 'Persona diğer yeteneklerle birlikte seçilemez';

  @override
  String get personaTwitterHandleNotFound => 'Twitter hesabı bulunamadı';

  @override
  String get personaTwitterHandleSuspended => 'Twitter hesabı askıya alındı';

  @override
  String get personaFailedToVerifyTwitter => 'Twitter hesabı doğrulanamadı';

  @override
  String get personaFailedToFetch => 'Persona alınamadı';

  @override
  String get personaFailedToCreate => 'Persona oluşturulamadı';

  @override
  String get personaConnectKnowledgeSource => 'En az bir veri kaynağı bağlayın (Omi veya Twitter)';

  @override
  String get personaUpdatedSuccessfully => 'Persona başarıyla güncellendi';

  @override
  String get personaFailedToUpdate => 'Persona güncellenemedi';

  @override
  String get personaPleaseSelectImage => 'Bir görsel seçin';

  @override
  String get personaFailedToCreateTryLater => 'Persona oluşturulamadı. Daha sonra tekrar deneyin.';

  @override
  String personaFailedToCreateWithError(String error) {
    return 'Persona oluşturulamadı: $error';
  }

  @override
  String get personaFailedToEnable => 'Persona etkinleştirilemedi';

  @override
  String personaErrorEnablingWithError(String error) {
    return 'Persona etkinleştirilirken hata: $error';
  }

  @override
  String get paymentFailedToFetchCountries => 'Desteklenen ülkeler alınamadı. Daha sonra tekrar deneyin.';

  @override
  String get paymentFailedToSetDefault => 'Varsayılan ödeme yöntemi ayarlanamadı. Daha sonra tekrar deneyin.';

  @override
  String get paymentFailedToSavePaypal => 'PayPal bilgileri kaydedilemedi. Daha sonra tekrar deneyin.';

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
  String get paymentStatusConnected => 'Bağlı';

  @override
  String get paymentStatusNotConnected => 'Bağlı Değil';

  @override
  String get paymentAppCost => 'Uygulama Maliyeti';

  @override
  String get paymentEnterValidAmount => 'Geçerli bir tutar girin';

  @override
  String get paymentEnterAmountGreaterThanZero => '0\'dan büyük bir tutar girin';

  @override
  String get paymentPlan => 'Ödeme Planı';

  @override
  String get paymentNoneSelected => 'Seçilmedi';

  @override
  String get aiGenPleaseEnterDescription => 'Lütfen uygulamanız için bir açıklama girin';

  @override
  String get aiGenCreatingAppIcon => 'Uygulama simgesi oluşturuluyor...';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'Bir hata oluştu: $message';
  }

  @override
  String get aiGenAppCreatedSuccessfully => 'Uygulama başarıyla oluşturuldu!';

  @override
  String get aiGenFailedToCreateApp => 'Uygulama oluşturulamadı';

  @override
  String get aiGenErrorWhileCreatingApp => 'Uygulama oluşturulurken bir hata oluştu';

  @override
  String get aiGenFailedToGenerateApp => 'Uygulama oluşturulamadı. Lütfen tekrar deneyin.';

  @override
  String get aiGenFailedToRegenerateIcon => 'Simge yeniden oluşturulamadı';

  @override
  String get aiGenPleaseGenerateAppFirst => 'Lütfen önce bir uygulama oluşturun';

  @override
  String get xHandleTitle => 'X kullanıcı adınız nedir?';

  @override
  String get xHandleDescription => 'Omi klonunuzu hesabınızın\netkinliğine göre önceden eğiteceğiz';

  @override
  String get xHandleHint => '@nikshevchenko';

  @override
  String get xHandlePleaseEnter => 'Lütfen X kullanıcı adınızı girin';

  @override
  String get xHandlePleaseEnterValid => 'Lütfen geçerli bir X kullanıcı adı girin';

  @override
  String get nextButton => 'İleri';

  @override
  String get connectOmiDevice => 'Omi Cihazını Bağla';

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'Sınırsız Planınızı $title planına değiştiriyorsunuz. Devam etmek istediğinizden emin misiniz?';
  }

  @override
  String get planUpgradeScheduledMessage =>
      'Yükseltme planlandı! Aylık planınız fatura döneminizin sonuna kadar devam eder, ardından otomatik olarak yıllık plana geçer.';

  @override
  String get couldNotSchedulePlanChange => 'Plan değişikliği planlanamadı. Lütfen tekrar deneyin.';

  @override
  String get subscriptionReactivatedDefault =>
      'Aboneliğiniz yeniden etkinleştirildi! Şimdi ücret alınmayacak - mevcut dönem sonunda faturalandırılacaksınız.';

  @override
  String get subscriptionSuccessfulCharged => 'Abonelik başarılı! Yeni fatura dönemi için ücret alındı.';

  @override
  String get couldNotProcessSubscription => 'Abonelik işlenemedi. Lütfen tekrar deneyin.';

  @override
  String get couldNotLaunchUpgradePage => 'Yükseltme sayfası açılamadı. Lütfen tekrar deneyin.';

  @override
  String get transcriptionJsonPlaceholder => 'JSON yapılandırmanızı buraya yapıştırın...';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get pricePlaceholder => '0,00';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'Dosya seçici açılırken hata: $message';
  }

  @override
  String importErrorGeneric(String error) {
    return 'Hata: $error';
  }

  @override
  String get mergeConversationsSuccessTitle => 'Konuşmalar başarıyla birleştirildi';

  @override
  String mergeConversationsSuccessBody(int count) {
    return '$count konuşma başarıyla birleştirildi';
  }

  @override
  String get dailyReflectionNotificationTitle => 'Günlük düşünce zamanı';

  @override
  String get dailyReflectionNotificationBody => 'Bana gününü anlat';

  @override
  String get actionItemReminderTitle => 'Omi Hatırlatıcı';

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName bağlantısı kesildi';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'Lütfen $deviceName cihazınızı kullanmaya devam etmek için yeniden bağlanın.';
  }

  @override
  String get onboardingSignIn => 'Giriş Yap';

  @override
  String get onboardingYourName => 'Adınız';

  @override
  String get onboardingLanguage => 'Dil';

  @override
  String get onboardingPermissions => 'İzinler';

  @override
  String get onboardingComplete => 'Tamamlandı';

  @override
  String get onboardingWelcomeToOmi => 'Omi\'ye Hoş Geldiniz';

  @override
  String get onboardingTellUsAboutYourself => 'Bize kendinizden bahsedin';

  @override
  String get onboardingChooseYourPreference => 'Tercihinizi seçin';

  @override
  String get onboardingGrantRequiredAccess => 'Gerekli erişimi verin';

  @override
  String get onboardingYoureAllSet => 'Hazırsınız';

  @override
  String get searchTranscriptOrSummary => 'Transkript veya özette ara...';

  @override
  String get myGoal => 'Hedefim';

  @override
  String get appNotAvailable => 'Hay aksi! Aradığınız uygulama mevcut değil görünüyor.';

  @override
  String get failedToConnectTodoist => 'Todoist\'a bağlanılamadı';

  @override
  String get failedToConnectAsana => 'Asana\'ya bağlanılamadı';

  @override
  String get failedToConnectGoogleTasks => 'Google Tasks\'a bağlanılamadı';

  @override
  String get failedToConnectClickUp => 'ClickUp\'a bağlanılamadı';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return '$serviceName hizmetine bağlanılamadı: $error';
  }

  @override
  String get successfullyConnectedTodoist => 'Todoist\'a başarıyla bağlanıldı!';

  @override
  String get failedToConnectTodoistRetry => 'Todoist\'a bağlanılamadı. Lütfen tekrar deneyin.';

  @override
  String get successfullyConnectedAsana => 'Asana\'ya başarıyla bağlanıldı!';

  @override
  String get failedToConnectAsanaRetry => 'Asana\'ya bağlanılamadı. Lütfen tekrar deneyin.';

  @override
  String get successfullyConnectedGoogleTasks => 'Google Tasks\'a başarıyla bağlanıldı!';

  @override
  String get failedToConnectGoogleTasksRetry => 'Google Tasks\'a bağlanılamadı. Lütfen tekrar deneyin.';

  @override
  String get successfullyConnectedClickUp => 'ClickUp\'a başarıyla bağlanıldı!';

  @override
  String get failedToConnectClickUpRetry => 'ClickUp\'a bağlanılamadı. Lütfen tekrar deneyin.';

  @override
  String get successfullyConnectedNotion => 'Notion\'a başarıyla bağlanıldı!';

  @override
  String get failedToRefreshNotionStatus => 'Notion bağlantı durumu yenilenemedi.';

  @override
  String get successfullyConnectedGoogle => 'Google\'a başarıyla bağlanıldı!';

  @override
  String get failedToRefreshGoogleStatus => 'Google bağlantı durumu yenilenemedi.';

  @override
  String get successfullyConnectedWhoop => 'Whoop\'a başarıyla bağlanıldı!';

  @override
  String get failedToRefreshWhoopStatus => 'Whoop bağlantı durumu yenilenemedi.';

  @override
  String get successfullyConnectedGitHub => 'GitHub\'a başarıyla bağlanıldı!';

  @override
  String get failedToRefreshGitHubStatus => 'GitHub bağlantı durumu yenilenemedi.';

  @override
  String get authFailedToSignInWithGoogle => 'Google ile giriş yapılamadı, lütfen tekrar deneyin.';

  @override
  String get authenticationFailed => 'Kimlik doğrulama başarısız. Lütfen tekrar deneyin.';

  @override
  String get authFailedToSignInWithApple => 'Apple ile giriş yapılamadı, lütfen tekrar deneyin.';

  @override
  String get authFailedToRetrieveToken => 'Firebase jetonu alınamadı, lütfen tekrar deneyin.';

  @override
  String get authUnexpectedErrorFirebase => 'Giriş yaparken beklenmeyen hata, Firebase hatası, lütfen tekrar deneyin.';

  @override
  String get authUnexpectedError => 'Giriş yaparken beklenmeyen hata, lütfen tekrar deneyin';

  @override
  String get authFailedToLinkGoogle => 'Google ile bağlantı kurulamadı, lütfen tekrar deneyin.';

  @override
  String get authFailedToLinkApple => 'Apple ile bağlantı kurulamadı, lütfen tekrar deneyin.';

  @override
  String get onboardingBluetoothRequired => 'Cihazınıza bağlanmak için Bluetooth izni gereklidir.';

  @override
  String get onboardingBluetoothDeniedSystemPrefs =>
      'Bluetooth izni reddedildi. Lütfen Sistem Tercihleri\'nde izin verin.';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'Bluetooth izin durumu: $status. Lütfen Sistem Tercihleri\'ni kontrol edin.';
  }

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'Bluetooth izni kontrol edilemedi: $error';
  }

  @override
  String get onboardingNotificationDeniedSystemPrefs =>
      'Bildirim izni reddedildi. Lütfen Sistem Tercihleri\'nde izin verin.';

  @override
  String get onboardingNotificationDeniedNotifications =>
      'Bildirim izni reddedildi. Lütfen Sistem Tercihleri > Bildirimler\'de izin verin.';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return 'Bildirim izin durumu: $status. Lütfen Sistem Tercihleri\'ni kontrol edin.';
  }

  @override
  String onboardingFailedCheckNotification(String error) {
    return 'Bildirim izni kontrol edilemedi: $error';
  }

  @override
  String get onboardingLocationGrantInSettings =>
      'Lütfen Ayarlar > Gizlilik ve Güvenlik > Konum Servisleri\'nde konum izni verin';

  @override
  String get onboardingMicrophoneRequired => 'Kayıt için mikrofon izni gereklidir.';

  @override
  String get onboardingMicrophoneDenied =>
      'Mikrofon izni reddedildi. Lütfen Sistem Tercihleri > Gizlilik ve Güvenlik > Mikrofon\'da izin verin.';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'Mikrofon izin durumu: $status. Lütfen Sistem Tercihleri\'ni kontrol edin.';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'Mikrofon izni kontrol edilemedi: $error';
  }

  @override
  String get onboardingScreenCaptureRequired => 'Sistem ses kaydı için ekran yakalama izni gereklidir.';

  @override
  String get onboardingScreenCaptureDenied =>
      'Ekran yakalama izni reddedildi. Lütfen Sistem Tercihleri > Gizlilik ve Güvenlik > Ekran Kaydı\'nda izin verin.';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return 'Ekran yakalama izin durumu: $status. Lütfen Sistem Tercihleri\'ni kontrol edin.';
  }

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return 'Ekran yakalama izni kontrol edilemedi: $error';
  }

  @override
  String get onboardingAccessibilityRequired =>
      'Tarayıcı toplantılarını algılamak için erişilebilirlik izni gereklidir.';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'Erişilebilirlik izin durumu: $status. Lütfen Sistem Tercihleri\'ni kontrol edin.';
  }

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'Erişilebilirlik izni kontrol edilemedi: $error';
  }

  @override
  String get msgCameraNotAvailable => 'Bu platformda kamera çekimi kullanılamıyor';

  @override
  String get msgCameraPermissionDenied => 'Kamera izni reddedildi. Lütfen kameraya erişime izin verin';

  @override
  String msgCameraAccessError(String error) {
    return 'Kameraya erişim hatası: $error';
  }

  @override
  String get msgPhotoError => 'Fotoğraf çekerken hata oluştu. Lütfen tekrar deneyin.';

  @override
  String get msgMaxImagesLimit => 'En fazla 4 resim seçebilirsiniz';

  @override
  String msgFilePickerError(String error) {
    return 'Dosya seçici açılırken hata: $error';
  }

  @override
  String msgSelectImagesError(String error) {
    return 'Resim seçerken hata: $error';
  }

  @override
  String get msgPhotosPermissionDenied =>
      'Fotoğraf izni reddedildi. Resim seçmek için lütfen fotoğraflara erişime izin verin';

  @override
  String get msgSelectImagesGenericError => 'Resim seçerken hata oluştu. Lütfen tekrar deneyin.';

  @override
  String get msgMaxFilesLimit => 'En fazla 4 dosya seçebilirsiniz';

  @override
  String msgSelectFilesError(String error) {
    return 'Dosya seçerken hata: $error';
  }

  @override
  String get msgSelectFilesGenericError => 'Dosya seçerken hata oluştu. Lütfen tekrar deneyin.';

  @override
  String get msgUploadFileFailed => 'Dosya yüklenemedi, lütfen daha sonra tekrar deneyin';

  @override
  String get msgReadingMemories => 'Anılarınız okunuyor...';

  @override
  String get msgLearningMemories => 'Anılarınızdan öğreniliyor...';

  @override
  String get msgUploadAttachedFileFailed => 'Ekli dosya yüklenemedi.';

  @override
  String captureRecordingError(String error) {
    return 'Kayıt sırasında bir hata oluştu: $error';
  }

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return 'Kayıt durduruldu: $reason. Harici ekranları yeniden bağlamanız veya kaydı yeniden başlatmanız gerekebilir.';
  }

  @override
  String get captureMicrophonePermissionRequired => 'Mikrofon izni gerekli';

  @override
  String get captureMicrophonePermissionInSystemPreferences => 'Sistem Tercihleri\'nde mikrofon izni verin';

  @override
  String get captureScreenRecordingPermissionRequired => 'Ekran kaydı izni gerekli';

  @override
  String get captureDisplayDetectionFailed => 'Ekran algılama başarısız. Kayıt durduruldu.';

  @override
  String get devModeInvalidAudioBytesWebhookUrl => 'Geçersiz ses baytları webhook URL\'si';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl => 'Geçersiz gerçek zamanlı transkript webhook URL\'si';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl => 'Geçersiz oluşturulan konuşma webhook URL\'si';

  @override
  String get devModeInvalidDaySummaryWebhookUrl => 'Geçersiz günlük özet webhook URL\'si';

  @override
  String get devModeSettingsSaved => 'Ayarlar kaydedildi!';

  @override
  String get voiceFailedToTranscribe => 'Ses metne dönüştürülemedi';

  @override
  String get locationPermissionRequired => 'Konum izni gerekli';

  @override
  String get locationPermissionContent =>
      'Hızlı Transfer, WiFi bağlantısını doğrulamak için konum izni gerektirir. Devam etmek için lütfen konum izni verin.';

  @override
  String get pdfTranscriptExport => 'Döküm Dışa Aktar';

  @override
  String get pdfConversationExport => 'Sohbet Dışa Aktar';

  @override
  String pdfTitleLabel(String title) {
    return 'Başlık: $title';
  }

  @override
  String get conversationNewIndicator => 'Yeni 🚀';

  @override
  String conversationPhotosCount(int count) {
    return '$count fotoğraf';
  }

  @override
  String get mergingStatus => 'Birleştiriliyor...';

  @override
  String timeSecsSingular(int count) {
    return '$count sn';
  }

  @override
  String timeSecsPlural(int count) {
    return '$count sn';
  }

  @override
  String timeMinSingular(int count) {
    return '$count dk';
  }

  @override
  String timeMinsPlural(int count) {
    return '$count dk';
  }

  @override
  String timeMinsAndSecs(int mins, int secs) {
    return '$mins dk $secs sn';
  }

  @override
  String timeHourSingular(int count) {
    return '$count saat';
  }

  @override
  String timeHoursPlural(int count) {
    return '$count saat';
  }

  @override
  String timeHoursAndMins(int hours, int mins) {
    return '$hours saat $mins dk';
  }

  @override
  String timeDaySingular(int count) {
    return '$count gün';
  }

  @override
  String timeDaysPlural(int count) {
    return '$count gün';
  }

  @override
  String timeDaysAndHours(int days, int hours) {
    return '$days gün $hours saat';
  }

  @override
  String timeCompactSecs(int count) {
    return '${count}sn';
  }

  @override
  String timeCompactMins(int count) {
    return '${count}dk';
  }

  @override
  String timeCompactMinsAndSecs(int mins, int secs) {
    return '${mins}dk ${secs}sn';
  }

  @override
  String timeCompactHours(int count) {
    return '${count}sa';
  }

  @override
  String timeCompactHoursAndMins(int hours, int mins) {
    return '${hours}sa ${mins}dk';
  }

  @override
  String get moveToFolder => 'Klasöre Taşı';

  @override
  String get noFoldersAvailable => 'Kullanılabilir klasör yok';

  @override
  String get newFolder => 'Yeni Klasör';

  @override
  String get color => 'Renk';

  @override
  String get waitingForDevice => 'Cihaz bekleniyor...';

  @override
  String get saySomething => 'Bir şey söyle...';

  @override
  String get initialisingSystemAudio => 'Sistem Sesi Başlatılıyor';

  @override
  String get stopRecording => 'Kaydı Durdur';

  @override
  String get continueRecording => 'Kayda Devam Et';

  @override
  String get initialisingRecorder => 'Kayıt Cihazı Başlatılıyor';

  @override
  String get pauseRecording => 'Kaydı Duraklat';

  @override
  String get resumeRecording => 'Kaydı Sürdür';

  @override
  String get noDailyRecapsYet => 'Henüz günlük özet yok';

  @override
  String get dailyRecapsDescription => 'Günlük özetleriniz oluşturulduktan sonra burada görünecek';

  @override
  String get chooseTransferMethod => 'Aktarım yöntemi seçin';

  @override
  String get fastTransferSpeed => 'WiFi ile ~150 KB/s';

  @override
  String largeTimeGapDetected(String gap) {
    return 'Büyük zaman farkı tespit edildi ($gap)';
  }

  @override
  String largeTimeGapsDetected(String gaps) {
    return 'Büyük zaman farkları tespit edildi ($gaps)';
  }

  @override
  String get deviceDoesNotSupportWifiSwitchingToBle =>
      'Cihaz WiFi senkronizasyonunu desteklemiyor, Bluetooth\'a geçiliyor';

  @override
  String get appleHealthNotAvailable => 'Apple Health bu cihazda kullanılamıyor';

  @override
  String get downloadAudio => 'Ses İndir';

  @override
  String get audioDownloadSuccess => 'Ses başarıyla indirildi';

  @override
  String get audioDownloadFailed => 'Ses indirme başarısız';

  @override
  String get downloadingAudio => 'Ses indiriliyor...';

  @override
  String get shareAudio => 'Sesi Paylaş';

  @override
  String get preparingAudio => 'Ses Hazırlanıyor';

  @override
  String get gettingAudioFiles => 'Ses dosyaları alınıyor...';

  @override
  String get downloadingAudioProgress => 'Ses İndiriliyor';

  @override
  String get processingAudio => 'Ses İşleniyor';

  @override
  String get combiningAudioFiles => 'Ses dosyaları birleştiriliyor...';

  @override
  String get audioReady => 'Ses Hazır';

  @override
  String get openingShareSheet => 'Paylaşım sayfası açılıyor...';

  @override
  String get audioShareFailed => 'Paylaşım Başarısız';

  @override
  String get dailyRecaps => 'Günlük Özetler';

  @override
  String get removeFilter => 'Filtreyi Kaldır';

  @override
  String get categoryConversationAnalysis => 'Konuşma Analizi';

  @override
  String get categoryPersonalityClone => 'Kişilik Klonu';

  @override
  String get categoryHealth => 'Sağlık';

  @override
  String get categoryEducation => 'Eğitim';

  @override
  String get categoryCommunication => 'İletişim';

  @override
  String get categoryEmotionalSupport => 'Duygusal Destek';

  @override
  String get categoryProductivity => 'Verimlilik';

  @override
  String get categoryEntertainment => 'Eğlence';

  @override
  String get categoryFinancial => 'Finans';

  @override
  String get categoryTravel => 'Seyahat';

  @override
  String get categorySafety => 'Güvenlik';

  @override
  String get categoryShopping => 'Alışveriş';

  @override
  String get categorySocial => 'Sosyal';

  @override
  String get categoryNews => 'Haberler';

  @override
  String get categoryUtilities => 'Araçlar';

  @override
  String get categoryOther => 'Diğer';

  @override
  String get capabilityChat => 'Sohbet';

  @override
  String get capabilityConversations => 'Konuşmalar';

  @override
  String get capabilityExternalIntegration => 'Harici Entegrasyon';

  @override
  String get capabilityNotification => 'Bildirim';

  @override
  String get triggerAudioBytes => 'Ses Baytları';

  @override
  String get triggerConversationCreation => 'Konuşma Oluşturma';

  @override
  String get triggerTranscriptProcessed => 'Transkript İşlendi';

  @override
  String get actionCreateConversations => 'Konuşma oluştur';

  @override
  String get actionCreateMemories => 'Anı oluştur';

  @override
  String get actionReadConversations => 'Konuşmaları oku';

  @override
  String get actionReadMemories => 'Anıları oku';

  @override
  String get actionReadTasks => 'Görevleri oku';

  @override
  String get scopeUserName => 'Kullanıcı Adı';

  @override
  String get scopeUserFacts => 'Kullanıcı Bilgileri';

  @override
  String get scopeUserConversations => 'Kullanıcı Konuşmaları';

  @override
  String get scopeUserChat => 'Kullanıcı Sohbeti';

  @override
  String get capabilitySummary => 'Özet';

  @override
  String get capabilityFeatured => 'Öne Çıkanlar';

  @override
  String get capabilityTasks => 'Görevler';

  @override
  String get capabilityIntegrations => 'Entegrasyonlar';

  @override
  String get categoryPersonalityClones => 'Kişilik Klonları';

  @override
  String get categoryProductivityLifestyle => 'Verimlilik ve Yaşam Tarzı';

  @override
  String get categorySocialEntertainment => 'Sosyal ve Eğlence';

  @override
  String get categoryProductivityTools => 'Verimlilik Araçları';

  @override
  String get categoryPersonalWellness => 'Kişisel Sağlık';

  @override
  String get rating => 'Puan';

  @override
  String get categories => 'Kategoriler';

  @override
  String get sortBy => 'Sırala';

  @override
  String get highestRating => 'En yüksek puan';

  @override
  String get lowestRating => 'En düşük puan';

  @override
  String get resetFilters => 'Filtreleri sıfırla';

  @override
  String get applyFilters => 'Filtreleri uygula';

  @override
  String get mostInstalls => 'En çok yükleme';

  @override
  String get couldNotOpenUrl => 'URL açılamadı. Lütfen tekrar deneyin.';

  @override
  String get newTask => 'Yeni görev';

  @override
  String get viewAll => 'Tümünü gör';

  @override
  String get addTask => 'Görev ekle';

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
  String get audioPlaybackUnavailable => 'Ses dosyası oynatma için mevcut değil';

  @override
  String get audioPlaybackFailed => 'Ses oynatılamıyor. Dosya bozuk veya eksik olabilir.';

  @override
  String get connectionGuide => 'Bağlantı Rehberi';

  @override
  String get iveDoneThis => 'Bunu yaptım';

  @override
  String get pairNewDevice => 'Yeni cihaz eşleştir';

  @override
  String get dontSeeYourDevice => 'Cihazınızı görmüyor musunuz?';

  @override
  String get reportAnIssue => 'Sorun bildirin';

  @override
  String get pairingTitleOmi => 'Omi\'yi Açın';

  @override
  String get pairingDescOmi => 'Cihazı açmak için titreşene kadar basılı tutun.';

  @override
  String get pairingTitleOmiDevkit => 'Omi DevKit\'i Eşleştirme Moduna Alın';

  @override
  String get pairingDescOmiDevkit => 'Açmak için düğmeye bir kez basın. Eşleştirme modunda LED mor renkte yanıp söner.';

  @override
  String get pairingTitleOmiGlass => 'Omi Glass\'ı Açın';

  @override
  String get pairingDescOmiGlass => 'Açmak için yan düğmeyi 3 saniye basılı tutun.';

  @override
  String get pairingTitlePlaudNote => 'Plaud Note\'u Eşleştirme Moduna Alın';

  @override
  String get pairingDescPlaudNote =>
      'Yan düğmeyi 2 saniye basılı tutun. Eşleştirmeye hazır olduğunda kırmızı LED yanıp söner.';

  @override
  String get pairingTitleBee => 'Bee\'yi Eşleştirme Moduna Alın';

  @override
  String get pairingDescBee => 'Düğmeye art arda 5 kez basın. Işık mavi ve yeşil yanıp sönmeye başlayacaktır.';

  @override
  String get pairingTitleLimitless => 'Limitless\'ı Eşleştirme Moduna Alın';

  @override
  String get pairingDescLimitless =>
      'Herhangi bir ışık görünürken, bir kez basın, ardından cihaz pembe ışık gösterene kadar basılı tutun, sonra bırakın.';

  @override
  String get pairingTitleFriendPendant => 'Friend Pendant\'ı Eşleştirme Moduna Alın';

  @override
  String get pairingDescFriendPendant =>
      'Açmak için kolye üzerindeki düğmeye basın. Otomatik olarak eşleştirme moduna geçecektir.';

  @override
  String get pairingTitleFieldy => 'Fieldy\'yi Eşleştirme Moduna Alın';

  @override
  String get pairingDescFieldy => 'Cihazı açmak için ışık görünene kadar basılı tutun.';

  @override
  String get pairingTitleAppleWatch => 'Apple Watch Bağlayın';

  @override
  String get pairingDescAppleWatch =>
      'Apple Watch\'unuza Omi uygulamasını yükleyin ve açın, ardından uygulamada Bağlan\'a dokunun.';

  @override
  String get pairingTitleNeoOne => 'Neo One\'ı Eşleştirme Moduna Alın';

  @override
  String get pairingDescNeoOne => 'LED yanıp sönene kadar güç düğmesini basılı tutun. Cihaz keşfedilebilir olacaktır.';
}
