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
  String get copyTranscript => 'Transkripti Kopyala';

  @override
  String get copySummary => 'Özeti Kopyala';

  @override
  String get testPrompt => 'İstemi Test Et';

  @override
  String get reprocessConversation => 'Konuşmayı Yeniden İşle';

  @override
  String get deleteConversation => 'Konuşmayı Sil';

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
  String get done => 'Tamam';

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
  String get noStarredConversations => 'Henüz favorilere eklenmiş konuşma yok.';

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
  String get messageCopied => 'Mesaj panoya kopyalandı.';

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
  String get clearChat => 'Sohbet Temizlensin mi?';

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
  String get visitWebsite => 'Web Sitesini Ziyaret Et';

  @override
  String get helpOrInquiries => 'Yardım veya Sorular?';

  @override
  String get joinCommunity => 'Topluluğa katılın!';

  @override
  String get membersAndCounting => '8000+ üye ve artıyor.';

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
  String get name => 'İsim';

  @override
  String get email => 'E-posta';

  @override
  String get customVocabulary => 'Özel Kelime Hazinesi';

  @override
  String get identifyingOthers => 'Diğerlerini Tanımlama';

  @override
  String get paymentMethods => 'Ödeme Yöntemleri';

  @override
  String get conversationDisplay => 'Konuşma Görünümü';

  @override
  String get dataPrivacy => 'Veri ve Gizlilik';

  @override
  String get userId => 'Kullanıcı Kimliği';

  @override
  String get notSet => 'Ayarlanmadı';

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
  String get chatTools => 'Sohbet Araçları';

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
  String get docs => 'Dokümanlar';

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
  String get debugLogs => 'Hata Ayıklama Günlükleri';

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
  String get shareLogs => 'Günlükleri Paylaş';

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
  String get knowledgeGraphDeleted => 'Bilgi Grafiği başarıyla silindi';

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
  String get webhooks => 'Web Hook\'ları';

  @override
  String get conversationEvents => 'Konuşma Olayları';

  @override
  String get newConversationCreated => 'Yeni konuşma oluşturuldu';

  @override
  String get realtimeTranscript => 'Gerçek Zamanlı Transkript';

  @override
  String get transcriptReceived => 'Transkript alındı';

  @override
  String get audioBytes => 'Ses Baytları';

  @override
  String get audioDataReceived => 'Ses verisi alındı';

  @override
  String get intervalSeconds => 'Aralık (saniye)';

  @override
  String get daySummary => 'Gün Özeti';

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
  String get connect => 'Bağlan';

  @override
  String get comingSoon => 'Yakında';

  @override
  String get chatToolsFooter => 'Sohbette veri ve metrikleri görmek için uygulamalarınızı bağlayın.';

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
  String get primaryLanguage => 'Ana Dil';

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
  String get editName => 'İsmi Düzenle';

  @override
  String get howShouldOmiCallYou => 'Omi size nasıl hitap etmeli?';

  @override
  String get enterYourName => 'İsminizi girin';

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
  String get noUpcomingMeetings => 'Yaklaşan toplantı bulunamadı';

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
  String get continueButton => 'Devam Et';

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
  String get omiUnlimited => 'Omi Unlimited';

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
  String get host => 'Host';

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
  String deviceUsesCodec(String deviceName, String codecReason) {
    return '$deviceName $codecReason kullanıyor. Omi kullanılacak.';
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
  String get saveChanges => 'Değişiklikleri Kaydet';

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
  String get appName => 'Uygulama Adı';

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
  String get iUnderstand => 'Anladım';

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
  String get speechProfileIntro =>
      'Omi\'nin hedeflerinizi ve sesinizi öğrenmesi gerekiyor. Daha sonra değiştirebilirsiniz.';

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
  String get whatsYourName => 'Adınız nedir?';

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
  String searchMemories(int count) {
    return '$count Anıda Ara';
  }

  @override
  String get memoryDeleted => 'Anı Silindi.';

  @override
  String get undo => 'Geri Al';

  @override
  String get noMemoriesYet => 'Henüz anı yok';

  @override
  String get noAutoMemories => 'Henüz otomatik çıkarılan anı yok';

  @override
  String get noManualMemories => 'Henüz manuel anı yok';

  @override
  String get noMemoriesInCategories => 'Bu kategorilerde anı yok';

  @override
  String get noMemoriesFound => 'Anı bulunamadı';

  @override
  String get addFirstMemory => 'İlk anınızı ekleyin';

  @override
  String get clearMemoryTitle => 'Omi\'nin Hafızasını Temizle';

  @override
  String get clearMemoryMessage =>
      'Omi\'nin hafızasını temizlemek istediğinizden emin misiniz? Bu işlem geri alınamaz.';

  @override
  String get clearMemoryButton => 'Hafızayı Temizle';

  @override
  String get memoryClearedSuccess => 'Omi\'nin sizinle ilgili hafızası temizlendi';

  @override
  String get noMemoriesToDelete => 'Silinecek anı yok';

  @override
  String get createMemoryTooltip => 'Yeni anı oluştur';

  @override
  String get createActionItemTooltip => 'Yeni eylem öğesi oluştur';

  @override
  String get memoryManagement => 'Anı Yönetimi';

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
  String get newMemory => 'Yeni Anı';

  @override
  String get editMemory => 'Anıyı Düzenle';

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
  String get selectText => 'Metni seç';

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
  String get descriptionOptional => 'Açıklama (isteğe bağlı)';

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
  String get generateSummary => 'Özet oluştur';

  @override
  String get conversationNotFoundOrDeleted => 'Konuşma bulunamadı veya silindi';

  @override
  String get deleteMemory => 'Bellek silinsin mi?';

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
  String get unknownDevice => 'Bilinmeyen Cihaz';

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
  String get untitledConversation => 'Başlıksız konuşma';

  @override
  String countRemaining(String count) {
    return '$count kalan';
  }

  @override
  String get addGoal => 'Hedef ekle';

  @override
  String get editGoal => 'Hedefi düzenle';

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
  String get welcomeBack => 'Tekrar hoş geldiniz';

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
  String get dailyScore => 'GÜNLÜK PUAN';

  @override
  String get dailyScoreDescription => 'Uygulamaya daha iyi odaklanmanıza yardımcı olan bir puan.';

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
  String installsCount(String count) {
    return '$count+ yükleme';
  }

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
  String get aboutThePersona => 'Kişilik Hakkında';

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
}
