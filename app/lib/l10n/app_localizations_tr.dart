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
  String get copySummary => 'Özeti Kopyala';

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
  String get pleaseCompleteAuthentication => 'Lütfen tarayıcınızda kimlik doğrulamayı tamamlayın. Tamamlandığında uygulamaya geri dönün.';

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
  String get noStarredConversations => 'Yıldızlı konuşma yok';

  @override
  String get starConversationHint => 'Bir konuşmayı favorilere eklemek için açın ve üst kısımdaki yıldız simgesine dokunun.';

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
  String get unableToFetchApps => 'Uygulamalar alınamadı :(\n\nLütfen internet bağlantınızı kontrol edin ve tekrar deneyin.';

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
  String get exportBeforeDelete => 'Hesabınızı silmeden önce verilerinizi dışa aktarabilirsiniz, ancak silindikten sonra kurtarılamaz.';

  @override
  String get deleteAccountCheckbox => 'Hesabımı silmenin kalıcı olduğunu ve anılar ve konuşmalar dahil tüm verilerin kaybolacağını ve kurtarılamayacağını anlıyorum.';

  @override
  String get areYouSure => 'Emin misiniz?';

  @override
  String get deleteAccountFinal => 'Bu işlem geri alınamaz ve hesabınızı ve tüm ilgili verileri kalıcı olarak silecektir. Devam etmek istediğinizden emin misiniz?';

  @override
  String get deleteNow => 'Şimdi Sil';

  @override
  String get goBack => 'Geri Dön';

  @override
  String get checkBoxToConfirm => 'Hesabınızı silmenin kalıcı ve geri alınamaz olduğunu anladığınızı onaylamak için kutucuğu işaretleyin.';

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
  String get privacyIntro => 'Omi\'de gizliliğinizi korumaya kararlıyız. Bu sayfa verilerinizin nasıl saklandığını ve kullanıldığını kontrol etmenizi sağlar.';

  @override
  String get learnMore => 'Daha fazla bilgi...';

  @override
  String get dataProtectionLevel => 'Veri Koruma Seviyesi';

  @override
  String get dataProtectionDesc => 'Verileriniz varsayılan olarak güçlü şifreleme ile korunmaktadır. Ayarlarınızı ve gelecekteki gizlilik seçeneklerini aşağıda inceleyin.';

  @override
  String get appAccess => 'Uygulama Erişimi';

  @override
  String get appAccessDesc => 'Aşağıdaki uygulamalar verilerinize erişebilir. İzinlerini yönetmek için bir uygulamaya dokunun.';

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
  String get deviceUnpairedMessage => 'Cihaz eşleştirmesi kaldırıldı. Eşleştirme kaldırmayı tamamlamak için Ayarlar > Bluetooth\'a gidin ve cihazı unutun.';

  @override
  String get unpairDialogTitle => 'Cihazı Eşleştirmeyi Kaldır';

  @override
  String get unpairDialogMessage => 'Bu, cihazın eşleştirilmesini kaldıracak ve başka bir telefona bağlanabilecek. İşlemi tamamlamak için Ayarlar > Bluetooth\'a gidip cihazı unutmanız gerekecek.';

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
  String get v2UndetectedMessage => 'V1 cihazınız olduğunu veya cihazınızın bağlı olmadığını görüyoruz. SD Kart işlevi yalnızca V2 cihazlar için mevcuttur.';

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
  String get endpointUrl => 'Uç nokta URL\'si';

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
  String get startConversationToSeeInsights => 'Kullanım içgörülerinizi burada görmek için\nOmi ile bir konuşma başlatın.';

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
  String get deleteKnowledgeGraphMessage => 'Bu, tüm türetilmiş bilgi grafiği verilerini (düğümler ve bağlantılar) silecektir. Orijinal anılarınız güvende kalacaktır. Grafik zamanla veya bir sonraki istekte yeniden oluşturulacaktır.';

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
  String get connect => 'Bağlan';

  @override
  String get comingSoon => 'Yakında';

  @override
  String get chatToolsFooter => 'Sohbette veri ve metrikleri görmek için uygulamalarınızı bağlayın.';

  @override
  String get completeAuthInBrowser => 'Lütfen tarayıcınızda kimlik doğrulamayı tamamlayın. Tamamlandığında uygulamaya geri dönün.';

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
  String get alreadyGavePermission => 'Kayıtlarınızı kaydetmemiz için bize zaten izin verdiniz. İşte neden buna ihtiyacımız olduğunun bir hatırlatması:';

  @override
  String get wouldLikePermission => 'Ses kayıtlarınızı kaydetmek için izninizi istiyoruz. İşte nedeni:';

  @override
  String get improveSpeechProfile => 'Konuşma Profilinizi Geliştirin';

  @override
  String get improveSpeechProfileDesc => 'Kişisel konuşma profilinizi eğitmek ve geliştirmek için kayıtları kullanıyoruz.';

  @override
  String get trainFamilyProfiles => 'Arkadaşlar ve Aile için Profil Eğitin';

  @override
  String get trainFamilyProfilesDesc => 'Kayıtlarınız arkadaşlarınızı ve ailenizi tanımamıza ve profil oluşturmamıza yardımcı olur.';

  @override
  String get enhanceTranscriptAccuracy => 'Transkript Doğruluğunu Artırın';

  @override
  String get enhanceTranscriptAccuracyDesc => 'Modelimiz geliştikçe, kayıtlarınız için daha iyi transkripsiyon sonuçları sağlayabiliriz.';

  @override
  String get legalNotice => 'Yasal Uyarı: Ses verilerini kaydetme ve saklama yasallığı bulunduğunuz yere ve bu özelliği nasıl kullandığınıza bağlı olarak değişebilir. Yerel yasalara ve düzenlemelere uyumu sağlamak sizin sorumluluğunuzdur.';

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
  String get showMeetingsMenuBarDesc => 'Bir sonraki toplantınızı ve başlamasına kalan süreyi macOS menü çubuğunda gösterin';

  @override
  String get showEventsNoParticipants => 'Katılımcısı olmayan etkinlikleri göster';

  @override
  String get showEventsNoParticipantsDesc => 'Etkinleştirildiğinde, Yaklaşanlar katılımcısı veya video bağlantısı olmayan etkinlikleri gösterir.';

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
  String get conversationTimeoutDesc => 'Sessizlikte ne kadar bekledikten sonra konuşmanın otomatik olarak sonlandırılacağını seçin:';

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
  String get languageForTranscription => 'Daha keskin transkripsiyonlar ve kişiselleştirilmiş bir deneyim için dilinizi ayarlayın.';

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
  String get selectDefaultRepoDesc => 'Sorun oluşturmak için varsayılan bir depo seçin. Sorun oluştururken farklı bir depo belirtebilirsiniz.';

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
  String get completeAuthBrowser => 'Lütfen tarayıcınızda kimlik doğrulamayı tamamlayın. Tamamlandığında uygulamaya geri dönün.';

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
  String get bluetoothNeeded => 'Omi\'nin giyilebilir cihazınıza bağlanması için Bluetooth gereklidir. Lütfen Bluetooth\'u etkinleştirin ve tekrar deneyin.';

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
  String get locationServiceDisabledDesc => 'Konum Servisi Devre Dışı. Lütfen Ayarlar > Gizlilik ve Güvenlik > Konum Servisleri\'ne gidin ve etkinleştirin';

  @override
  String get backgroundLocationDenied => 'Arka Plan Konum Erişimi Reddedildi';

  @override
  String get backgroundLocationDeniedDesc => 'Lütfen cihaz ayarlarına gidin ve konum iznini \"Her Zaman İzin Ver\" olarak ayarlayın';

  @override
  String get lovingOmi => 'Omi\'yi Beğeniyor musunuz?';

  @override
  String get leaveReviewIos => 'App Store\'da bir yorum bırakarak daha fazla insana ulaşmamıza yardımcı olun. Geri bildiriminiz bizim için çok değerli!';

  @override
  String get leaveReviewAndroid => 'Google Play Store\'da bir yorum bırakarak daha fazla insana ulaşmamıza yardımcı olun. Geri bildiriminiz bizim için çok değerli!';

  @override
  String get rateOnAppStore => 'App Store\'da Değerlendir';

  @override
  String get rateOnGooglePlay => 'Google Play\'de Değerlendir';

  @override
  String get maybeLater => 'Belki Sonra';

  @override
  String get speechProfileIntro => 'Omi\'nin hedeflerinizi ve sesinizi öğrenmesi gerekiyor. Daha sonra değiştirebilirsiniz.';

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
  String get connectionErrorDesc => 'Sunucuya bağlanılamadı. Lütfen internet bağlantınızı kontrol edin ve tekrar deneyin.';

  @override
  String get invalidRecordingMultipleSpeakers => 'Geçersiz kayıt algılandı';

  @override
  String get multipleSpeakersDesc => 'Kayıtta birden fazla konuşmacı var gibi görünüyor. Lütfen sessiz bir yerde olduğunuzdan emin olun ve tekrar deneyin.';

  @override
  String get tooShortDesc => 'Yeterli konuşma algılanamadı. Lütfen daha fazla konuşun ve tekrar deneyin.';

  @override
  String get invalidRecordingDesc => 'Lütfen en az 5 saniye, en fazla 90 saniye konuştuğunuzdan emin olun.';

  @override
  String get areYouThere => 'Orada mısınız?';

  @override
  String get noSpeechDesc => 'Herhangi bir konuşma algılayamadık. Lütfen en az 10 saniye, en fazla 3 dakika konuştuğunuzdan emin olun.';

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
  String get permissionsRequiredDesc => 'Bu uygulamanın düzgün çalışması için Bluetooth ve Konum izinlerine ihtiyacı var. Lütfen ayarlardan bunları etkinleştirin.';

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
  String get permissionGrantedNow => 'İzin verildi! Şimdi:\n\nSaatinizdeki Omi uygulamasını açın ve aşağıda \"Devam Et\"e dokunun';

  @override
  String get needMicrophonePermission => 'Mikrofon iznine ihtiyacımız var.\n\n1. \"İzin Ver\"e dokunun\n2. iPhone\'unuzda izin verin\n3. Saat uygulaması kapanacak\n4. Yeniden açın ve \"Devam Et\"e dokunun';

  @override
  String get grantPermissionButton => 'İzin Ver';

  @override
  String get needHelp => 'Yardıma mı İhtiyacınız Var?';

  @override
  String get troubleshootingSteps => 'Sorun giderme:\n\n1. Omi\'nin saatinizde yüklü olduğundan emin olun\n2. Saatinizdeki Omi uygulamasını açın\n3. İzin açılır penceresini arayın\n4. İstendiğinde \"İzin Ver\"e dokunun\n5. Saatinizdeki uygulama kapanacak - yeniden açın\n6. Geri gelin ve iPhone\'unuzda \"Devam Et\"e dokunun';

  @override
  String get recordingStartedSuccessfully => 'Kayıt başarıyla başladı!';

  @override
  String get permissionNotGrantedYet => 'Henüz izin verilmedi. Lütfen mikrofon erişimine izin verdiğinizden ve saatinizdeki uygulamayı yeniden açtığınızdan emin olun.';

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
  String get languageBenefits => 'Daha keskin transkripsiyonlar ve kişiselleştirilmiş bir deneyim için dilinizi ayarlayın';

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
  String get welcomeActionItemsDescription => 'Yapay zekanız konuşmalarınızdan otomatik olarak görevleri ve yapılacakları çıkaracaktır. Oluşturulduklarında burada görünecekler.';

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
  String get clearMemoryMessage => 'Omi\'nin hafızasını temizlemek istediğinizden emin misiniz? Bu işlem geri alınamaz.';

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
  String get retry => 'Tekrar dene';

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
  String get languageSettingsHelperText => 'Uygulama Dili menüleri ve düğmeleri değiştirir. Konuşma Dili, kayıtlarınızın nasıl transkribe edildiğini etkiler.';

  @override
  String get translationNotice => 'Çeviri Bildirimi';

  @override
  String get translationNoticeMessage => 'Omi konuşmaları birincil dilinize çevirir. İstediğiniz zaman Ayarlar → Profiller\'de güncelleyin.';

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
  String get conversationUrlCouldNotBeShared => 'Sohbet URL\'si paylaşılamadı.';

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
  String get unpairDeviceDialogMessage => 'Bu, cihazın başka bir telefona bağlanabilmesi için eşleştirmesini kaldıracaktır. İşlemi tamamlamak için Ayarlar > Bluetooth\'a gitmeniz ve cihazı unutmanız gerekecek.';

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
  String get noApiKeysYet => 'Henüz API anahtarı yok. Uygulamanızla entegre etmek için bir tane oluşturun.';

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
  String get debugAndDiagnostics => 'Hata Ayıklama ve Tanılama';

  @override
  String get autoDeletesAfter3Days => '3 gün sonra otomatik olarak silinir';

  @override
  String get helpsDiagnoseIssues => 'Sorunları teşhis etmeye yardımcı olur';

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
  String get autoCreateWhenNameDetected => 'Auto-create when name detected';

  @override
  String get followUpQuestions => 'Takip Soruları';

  @override
  String get suggestQuestionsAfterConversations => 'Konuşmalardan sonra sorular önerin';

  @override
  String get goalTracker => 'Hedef İzleyici';

  @override
  String get trackPersonalGoalsOnHomepage => 'Track your personal goals on homepage';

  @override
  String get dailyReflection => 'Günlük Yansıma';

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
  String get welcomeToOmiDescription => 'Omi\'ye hoş geldiniz! AI yardımcınız konuşmalar, görevler ve daha fazlasında size yardımcı olmaya hazır.';

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
  String get tasksFromConversationsWillAppear => 'Konuşmalarınızdaki görevler burada görünecek.\nManuel olarak eklemek için Oluştur\'a tıklayın.';

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
  String get deleteActionItemConfirmation => 'Bu eylem öğesini silmek istediğinizden emin misiniz? Bu işlem geri alınamaz.';

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
  String get chatPromptPlaceholder => 'Harika bir uygulamasınız, işiniz kullanıcı sorgularına yanıt vermek ve onları iyi hissettirmek...';

  @override
  String get conversationPrompt => 'Konuşma İstemi';

  @override
  String get conversationPromptPlaceholder => 'Harika bir uygulamasınız, size bir konuşmanın transkripti ve özeti verilecek...';

  @override
  String get notificationScopes => 'Bildirim Kapsamları';

  @override
  String get appPrivacyAndTerms => 'Uygulama Gizliliği ve Şartları';

  @override
  String get makeMyAppPublic => 'Uygulamamı herkese açık yap';

  @override
  String get submitAppTermsAgreement => 'Bu uygulamayı göndererek, Omi AI Hizmet Koşullarını ve Gizlilik Politikasını kabul ediyorum';

  @override
  String get submitApp => 'Uygulamayı Gönder';

  @override
  String get needHelpGettingStarted => 'Başlamak için yardıma mı ihtiyacınız var?';

  @override
  String get clickHereForAppBuildingGuides => 'Uygulama oluşturma kılavuzları ve belgeleri için buraya tıklayın';

  @override
  String get submitAppQuestion => 'Uygulama Gönderilsin mi?';

  @override
  String get submitAppPublicDescription => 'Uygulamanız incelenecek ve herkese açık hale getirilecek. İnceleme sırasında bile hemen kullanmaya başlayabilirsiniz!';

  @override
  String get submitAppPrivateDescription => 'Uygulamanız incelenecek ve size özel olarak sunulacak. İnceleme sırasında bile hemen kullanmaya başlayabilirsiniz!';

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
  String get dataAccessWarning => 'Bu uygulama verilerinize erişecek. Omi AI, bu uygulama tarafından verilerinizin nasıl kullanıldığı, değiştirildiği veya silindiğinden sorumlu değildir';

  @override
  String get installApp => 'Uygulamayı yükle';

  @override
  String get betaTesterNotice => 'Bu uygulamanın beta test kullanıcısısınız. Henüz herkese açık değil. Onaylandıktan sonra herkese açık olacak.';

  @override
  String get appUnderReviewOwner => 'Uygulamanız inceleniyor ve yalnızca size görünür. Onaylandıktan sonra herkese açık olacak.';

  @override
  String get appRejectedNotice => 'Uygulamanız reddedildi. Lütfen uygulama ayrıntılarını güncelleyin ve inceleme için yeniden gönderin.';

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
  String get appDescriptionPlaceholder => 'Harika Uygulamam harika şeyler yapan harika bir uygulamadır. En iyi uygulama!';

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
  String get microphonePermissionDenied => 'Mikrofon izni reddedildi. Lütfen Sistem Tercihleri > Gizlilik ve Güvenlik > Mikrofon\'da izin verin.';

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
  String get discardedConversation => 'İptal Edilen Sohbet';

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
  String get getOmiDevice => 'Omi Cihazı Al';

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
  String get dataCollectionMessage => 'Devam ederek, konuşmalarınız, kayıtlarınız ve kişisel bilgileriniz AI destekli içgörüler sağlamak ve tüm uygulama özelliklerini etkinleştirmek için sunucularımızda güvenli bir şekilde saklanacaktır.';

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
  String get tellUsHowYouWouldLikeToBeAddressed => 'Nasıl hitap edilmesini istediğinizi bize söyleyin. Bu, Omi deneyiminizi kişiselleştirmeye yardımcı olur.';

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
  String get microphoneAccessDescription => 'Omi, konuşmalarınızı kaydetmek ve transkript sağlamak için mikrofon erişimine ihtiyaç duyar.';

  @override
  String get screenRecording => 'Ekran Kaydı';

  @override
  String get captureSystemAudioFromMeetings => 'Toplantılardan sistem sesini yakala';

  @override
  String get screenRecordingDescription => 'Omi, tarayıcı tabanlı toplantılarınızdan sistem sesini yakalamak için ekran kaydı izni gerektirir.';

  @override
  String get accessibility => 'Erişilebilirlik';

  @override
  String get detectBrowserBasedMeetings => 'Tarayıcı tabanlı toplantıları algıla';

  @override
  String get accessibilityDescription => 'Omi, tarayıcınızda Zoom, Meet veya Teams toplantılarına katıldığınızı algılamak için erişilebilirlik izni gerektirir.';

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
  String get helpImproveOmiBySharing => 'Anonimleştirilmiş analitik verileri paylaşarak Omi\'yi geliştirmeye yardımcı olun';

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
  String get conversationsExportStarted => 'Konuşma dışa aktarımı başlatıldı. Bu birkaç saniye sürebilir, lütfen bekleyin.';

  @override
  String get mcpDescription => 'Anılarınızı ve konuşmalarınızı okumak, aramak ve yönetmek için Omi\'yi diğer uygulamalarla bağlamak için. Başlamak için bir anahtar oluşturun.';

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
  String get automaticallyCreateNewPerson => 'Transkriptte bir ad algılandığında otomatik olarak yeni bir kişi oluştur.';

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
  String get noSummaryForApp => 'Bu uygulama için özet mevcut değil. Daha iyi sonuçlar için başka bir uygulama deneyin.';

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
  String get unknownApp => 'Bilinmeyen Uygulama';

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
  String get clickTheButtonToCaptureAudio => 'Canlı transkriptler, AI içgörüleri ve otomatik kaydetme için ses kaydetmek üzere düğmeye tıklayın.';

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
    return '$count segment';
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
  String get selectTime => 'Zaman Seç';

  @override
  String get accountGroup => 'Hesap';

  @override
  String get signOutQuestion => 'Çıkış Yapılsın mı?';

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
  String get dailySummaryDescription => 'Konuşmalarınızın kişiselleştirilmiş özetini alın';

  @override
  String get deliveryTime => 'Teslimat Zamanı';

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
  String get upcomingMeetings => 'YAKLAŞAN TOPLANTILAR';

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
  String get exportingConversations => 'Konuşmalar aktarılıyor...';

  @override
  String get clearNodesDescription => 'Tüm düğümleri ve bağlantıları temizle';

  @override
  String get deleteKnowledgeGraphQuestion => 'Bilgi Grafiği Silinsin mi?';

  @override
  String get deleteKnowledgeGraphWarning => 'Bu, türetilmiş tüm bilgi grafiği verilerini silecektir. Orijinal anılarınız güvende kalır.';

  @override
  String get connectOmiWithAI => 'Omi\'yi yapay zeka asistanlarıyla bağlayın';

  @override
  String get noAPIKeys => 'API anahtarı yok. Başlamak için bir tane oluşturun.';

  @override
  String get autoCreateWhenDetected => 'İsim algılandığında otomatik oluştur';

  @override
  String get trackPersonalGoals => 'Ana sayfada kişisel hedefleri izleyin';

  @override
  String get dailyReflectionDescription => 'Gününüzü yansıtmak için 21:00 hatırlatıcısı';

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
  String get helpsDiagnoseIssuesAutoDeletes => 'Sorunların teşhisine yardımcı olur. 3 gün sonra otomatik olarak silinir.';

  @override
  String get manageYourApp => 'Uygulamanızı Yönetin';

  @override
  String get updatingYourApp => 'Uygulamanız güncelleniyor';

  @override
  String get fetchingYourAppDetails => 'Uygulama bilgileri alınıyor';

  @override
  String get updateAppQuestion => 'Uygulama güncellensin mi?';

  @override
  String get updateAppConfirmation => 'Uygulamanızı güncellemek istediğinizden emin misiniz? Değişiklikler ekibimiz tarafından incelendikten sonra yansıtılacaktır.';

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
  String get subscriptionCancelledSuccessfully => 'Abonelik başarıyla iptal edildi. Mevcut fatura döneminin sonuna kadar aktif kalacaktır.';

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
  String get cancelSubscriptionConfirmation => 'Aboneliğinizi iptal etmek istediğinizden emin misiniz? Mevcut fatura döneminin sonuna kadar erişiminiz devam edecektir.';

  @override
  String get cancelSubscriptionButton => 'Aboneliği İptal Et';

  @override
  String get cancelling => 'İptal ediliyor...';

  @override
  String get betaTesterMessage => 'Bu uygulamanın beta test kullanıcısısınız. Henüz herkese açık değil. Onaylandıktan sonra herkese açık olacak.';

  @override
  String get appUnderReviewMessage => 'Uygulamanız inceleniyor ve yalnızca size görünür. Onaylandıktan sonra herkese açık olacak.';

  @override
  String get appRejectedMessage => 'Uygulamanız reddedildi. Lütfen detayları güncelleyip tekrar gönderin.';

  @override
  String get invalidIntegrationUrl => 'Geçersiz entegrasyon URL\'si';

  @override
  String get tapToComplete => 'Tamamlamak için dokunun';

  @override
  String get invalidSetupInstructionsUrl => 'Geçersiz kurulum talimatları URL\'si';

  @override
  String get pushToTalk => 'Konuşmak için Basın';

  @override
  String get summaryPrompt => 'Özet İstemi';

  @override
  String get pleaseSelectARating => 'Lütfen bir puan seçin';

  @override
  String get reviewAddedSuccessfully => 'Değerlendirme başarıyla eklendi 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'Değerlendirme başarıyla güncellendi 🚀';

  @override
  String get failedToSubmitReview => 'Değerlendirme gönderilemedi. Lütfen tekrar deneyin.';

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
  String get dataAccessNoticeDescription => 'This app will access your data. Omi AI is not responsible for how your data is used, modified, or deleted by this app';

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
  String get apiKeysDescription => 'API anahtarları, uygulamanız OMI sunucusuyla iletişim kurarken kimlik doğrulama için kullanılır. Uygulamanızın anılar oluşturmasına ve diğer OMI hizmetlerine güvenli bir şekilde erişmesine olanak tanır.';

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
  String get revokeApiKeyWarning => 'Bu işlem geri alınamaz. Bu anahtarı kullanan uygulamalar artık API\'ye erişemeyecektir.';

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
  String get itemPersona => 'Persona';

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
  String get externalAppAccessDescription => 'Aşağıdaki yüklü uygulamalar harici entegrasyonlara sahiptir ve sohbetler ve anılar gibi verilerinize erişebilir.';

  @override
  String get noExternalAppsHaveAccess => 'Hiçbir harici uygulama verilerinize erişemiyor.';

  @override
  String get maximumSecurityE2ee => 'Maksimum Güvenlik (E2EE)';

  @override
  String get e2eeDescription => 'Uçtan uca şifreleme, gizlilik için altın standarttır. Etkinleştirildiğinde, verileriniz sunucularımıza gönderilmeden önce cihazınızda şifrelenir. Bu, Omi dahil hiç kimsenin içeriğinize erişemeyeceği anlamına gelir.';

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
  String get secureEncryptionDescription => 'Verileriniz, Google Cloud\'da barındırılan sunucularımızda size özgü bir anahtarla şifrelenir. Bu, ham içeriğinizin Omi personeli veya Google dahil hiç kimse tarafından doğrudan veritabanından erişilemez olduğu anlamına gelir.';

  @override
  String get endToEndEncryption => 'Uçtan Uca Şifreleme';

  @override
  String get e2eeCardDescription => 'Yalnızca sizin verilerinize erişebildiğiniz maksimum güvenlik için etkinleştirin. Daha fazla bilgi için dokunun.';

  @override
  String get dataAlwaysEncrypted => 'Seviyeden bağımsız olarak, verileriniz her zaman dinlenme halinde ve aktarım sırasında şifrelenir.';

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
  String get getOmiUnlimitedFree => 'Verilerinizi AI modellerini eğitmek için katkıda bulunarak Omi Unlimited\'ı ücretsiz alın.';

  @override
  String get trainingDataBullets => '• Verileriniz AI modellerini geliştirmeye yardımcı olur\n• Yalnızca hassas olmayan veriler paylaşılır\n• Tamamen şeffaf süreç';

  @override
  String get learnMoreAtOmiTraining => 'omi.me/training adresinde daha fazla bilgi edinin';

  @override
  String get agreeToContributeData => 'AI eğitimi için verilerimi katkıda bulunmayı anlıyorum ve kabul ediyorum';

  @override
  String get submitRequest => 'İstek Gönder';

  @override
  String get thankYouRequestUnderReview => 'Teşekkürler! İsteğiniz inceleniyor. Onaylandıktan sonra sizi bilgilendireceğiz.';

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
  String get paymentMethodCharged => 'Aylık planınız sona erdiğinde mevcut ödeme yönteminiz otomatik olarak tahsil edilecek';

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
  String get annualPlanStartsAutomatically => 'Aylık planınız sona erdiğinde yıllık planınız otomatik olarak başlayacak.';

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
  String get privacyIntroText => 'Omi\'de gizliliğinizi çok ciddiye alıyoruz. Topladığımız veriler ve bunları nasıl kullandığımız konusunda şeffaf olmak istiyoruz. İşte bilmeniz gerekenler:';

  @override
  String get whatWeTrack => 'Ne Takip Ediyoruz';

  @override
  String get anonymityAndPrivacy => 'Anonimlik ve Gizlilik';

  @override
  String get optInAndOptOutOptions => 'Katılma ve Ayrılma Seçenekleri';

  @override
  String get ourCommitment => 'Taahhüdümüz';

  @override
  String get commitmentText => 'Topladığımız verileri yalnızca Omi\'yi sizin için daha iyi bir ürün haline getirmek için kullanmayı taahhüt ediyoruz. Gizliliğiniz ve güveniniz bizim için çok önemlidir.';

  @override
  String get thankYouText => 'Omi\'nin değerli bir kullanıcısı olduğunuz için teşekkür ederiz. Herhangi bir sorunuz veya endişeniz varsa, team@basedhardware.com adresinden bize ulaşmaktan çekinmeyin.';

  @override
  String get wifiSyncSettings => 'WiFi Senkronizasyon Ayarları';

  @override
  String get enterHotspotCredentials => 'Telefonunuzun hotspot kimlik bilgilerini girin';

  @override
  String get wifiSyncUsesHotspot => 'WiFi senkronizasyonu telefonunuzu hotspot olarak kullanır. Adı ve şifreyi Ayarlar > Kişisel Erişim Noktası\'nda bulun.';

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
}
