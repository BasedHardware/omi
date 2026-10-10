// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Turkish (`tr`).
class AppLocalizationsTr extends AppLocalizations {
  AppLocalizationsTr([String locale = 'tr']) : super(locale);

  @override
  String get welcomeActionItemsDescription =>
      'Yapay zekanız konuşmalarınızdaki görevleri otomatik olarak çıkaracaktır. Oluşturulduklarında burada görünecekler.';

  @override
  String get chatAppsProblemFailed => 'Bir şeyler ters gitti. Tekrar dene.';

  @override
  String get deviceOnboardingStarConversation => 'Devam Eden Konuşmayı Yıldızla';

  @override
  String get deleteAll => 'Tümünü sil';

  @override
  String get copySummary => 'Özeti kopyala';

  @override
  String get locationAccessDesc => 'Omi\'nin konuşmalarınızın nerede geçtiğini not edebilmesi için.';

  @override
  String get firmwareUpdate => 'Aygıt Yazılımı Güncellemesi';

  @override
  String get chatMessages => 'mesaj';

  @override
  String get showEventsNoParticipants => 'Katılımcısı olmayan etkinlikleri göster';

  @override
  String get sharePeriodYear => 'Bu yıl, Omi:';

  @override
  String get dreamReportRunFailed => 'Dream çalıştırılamadı. Tekrar dene.';

  @override
  String get sttModelAccuracy => 'Doğruluk';

  @override
  String get scopes => 'Kapsamlar';

  @override
  String get deleteFlowFeedbackSubtitle => 'Omi\'nin senin için işe yaramasını ne sağlardı?';

  @override
  String appDataAccessTitle(String appName) {
    return '$appName erişimine izin verilsin mi?';
  }

  @override
  String get pendantStorageAlmostFull =>
      'Pendant\'ın depolama alanı neredeyse dolu — eşitleme için uygulamayı açık tut.';

  @override
  String get deviceOnboardingAllSetDoublePressBadge => '2×';

  @override
  String get copyErrorMessage => 'Hata mesajını kopyala';

  @override
  String get filterMemories => 'Anıları Filtrele';

  @override
  String get helpsDiagnoseIssuesAutoDeletes =>
      'Sorunların teşhisine yardımcı olur. 3 gün sonra otomatik olarak silinir.';

  @override
  String get locationServiceDisabledDesc => 'Bu cihazda Konum Servisleri kapalı. Ayarlar\'dan açın.';

  @override
  String chatAppsIsConnected(String app) {
    return '$app bağlandı';
  }

  @override
  String get paymentMethodStripe => 'Stripe';

  @override
  String get deleteReasonTechnicalIssues => 'Çok fazla teknik sorun';

  @override
  String get payments => 'Ödemeler';

  @override
  String get verifiedFallback => 'Dogrulandi';

  @override
  String get pleaseWait => 'Lütfen bekleyin…';

  @override
  String get appLanguage => 'Uygulama Dili';

  @override
  String get unknownApp => 'Bilinmeyen uygulama';

  @override
  String get appReEnableFailedBody => 'Bu uygulama yeniden etkinleştirilemedi. Lütfen tekrar deneyin.';

  @override
  String get somethingWentWrongTryAgain => 'Bir şeyler yanlış gitti! Lütfen daha sonra tekrar deneyin.';

  @override
  String get upgradeScheduled => 'Yükseltme Planlandı';

  @override
  String get wrappedBuddiesLabel => 'ARKADAŞLAR';

  @override
  String get chatBlockShowMore => 'Daha Fazla Göster';

  @override
  String get subscriptionSuccessfulCharged => 'Abonelik başarılı! Yeni fatura dönemi için ücret alındı.';

  @override
  String get phoneCall => 'Telefon araması';

  @override
  String get chatAppsRefreshFailed => 'Yenilenemedi. Son görülenler gösteriliyor.';

  @override
  String get noDesktopAccess => 'Masaüstünde çalışmaz';

  @override
  String get areYouSure => 'Emin misiniz?';

  @override
  String get resubscribe => 'Yeniden Abone Ol';

  @override
  String voiceMatchMeterLabel(String level) {
    return 'Ses eşleşmesi: $level';
  }

  @override
  String get syncingBackground => 'Kayıtlarınızı arka planda senkronize etmeye devam edeceğiz.';

  @override
  String get signOutQuestion => 'Çıkış yap?';

  @override
  String chatAppsReadOnlyBanner(String app) {
    return 'Salt okunur. Omi\'ye $app içinde yanıt ver.';
  }

  @override
  String get connected => 'Bağlı';

  @override
  String get shareStatsMessage => 'Omi istatistiklerimi paylaşıyorum! (omi.me - her zaman açık yapay zeka asistanınız)';

  @override
  String get frequencyMinimal => 'Minimum';

  @override
  String get addAppSelectLogo => 'Uygulamanız için bir logo seçin';

  @override
  String get integrationInstructions => 'Entegrasyon Talimatları';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'Erişilebilirlik izin durumu: $status. Lütfen Sistem Tercihleri\'ni kontrol edin.';
  }

  @override
  String get wrappedCompleted => 'tamamlandı';

  @override
  String get remaining => 'Kalan';

  @override
  String get onDeviceIntensive => 'Cihaz Üzerinde transkripsiyon yoğun hesaplama gerektirir.';

  @override
  String get diagnosticsVerdictTrouble => 'Bağlanmada sorun var';

  @override
  String deviceOnboardingVoiceReplyPreviewThroughDevice(String device) {
    return '$device aracılığıyla';
  }

  @override
  String get copyConfig => 'Yapılandırmayı Kopyala';

  @override
  String accessesDataTypes(String dataTypes) {
    return '$dataTypes erişimi';
  }

  @override
  String get chatAppsWaitlistConfirmed => 'Teşekkürler. WhatsApp hazır olduğunda burada görünecek.';

  @override
  String get undo => 'Geri Al';

  @override
  String get phoneContactsAccessTitle => 'Kişilere Erişime İzin Ver';

  @override
  String confidenceIsConfirmed(String name) {
    return '$name Onaylandı durumunda. Başka yapmanız gereken bir şey yok.';
  }

  @override
  String get wrappedMovie => 'FİLM';

  @override
  String get wrappedStruggleLabelUpper => 'MÜCADELE';

  @override
  String get appleHealthFeatureChatDesc => 'Adımların, uykun, kalp atışın ve antrenmanların hakkında Omi\'ye sor.';

  @override
  String get writeReviewOptional => 'Yorum yaz (isteğe bağlı)';

  @override
  String get pairNewDevice => 'Yeni cihaz eşleştir';

  @override
  String chatUsedOfLimitCompute(String used, String limit) {
    return '$used / $limit hesaplama bütçesi kullanıldı';
  }

  @override
  String get dailySummary => 'Günlük Özet';

  @override
  String get pleaseEnterYourName => 'Lütfen adınızı girin';

  @override
  String get continueWithoutDevice => 'Cihaz Olmadan Devam Et';

  @override
  String get configure => 'Yapılandır';

  @override
  String get createApp => 'Uygulama Oluştur';

  @override
  String get invalidUrlError => 'Lütfen geçerli bir URL girin';

  @override
  String get appClosed => 'Uygulama kapatıldı';

  @override
  String get downgradeToFreemiumAction => 'Ücretsiz sürüme geç';

  @override
  String get chatAppsUseTelegramForNow => 'Şimdilik Telegram\'ı Kullan';

  @override
  String get wrappedBestMomentsBadge => 'En iyi anlar';

  @override
  String get storageSection => 'Depolama';

  @override
  String get pauseResumeRecording => 'Kaydı Duraklat/Devam Ettir';

  @override
  String get phoneUnmute => 'Sesi ac';

  @override
  String get youreAllSet => 'Hazırsınız!';

  @override
  String get migrationComplete => 'Taşıma tamamlandı!';

  @override
  String get paymentAppCost => 'Uygulama Maliyeti';

  @override
  String get deviceOnboardingFinish => 'Bitir';

  @override
  String get noVerifiedNumbers => 'Dogrulanmis numara yok';

  @override
  String get connectAiAssistantsToData => 'AI asistanlarını verilerinize bağlayın';

  @override
  String get keyNameHint => 'örn. Claude Desktop';

  @override
  String get paymentMethods => 'Ödeme Yöntemleri';

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'Erişilebilirlik izni kontrol edilemedi: $error';
  }

  @override
  String get confidenceReasonAutoOnly => 'Otomatik etiketlendi, henüz onaylanmadı';

  @override
  String whatsNewInVersion(String version) {
    return '$version sürümündeki yenilikler';
  }

  @override
  String get selectYourLanguage => 'Dilinizi seçin';

  @override
  String get memoryClearedSuccess => 'Omi\'nin sizinle ilgili hafızası temizlendi';

  @override
  String get memoryContentHint => 'Sabah toplantılarını tercih ederim.';

  @override
  String get dreamReportTitle => 'Dream Raporu';

  @override
  String importErrorGeneric(String error) {
    return 'Hata: $error';
  }

  @override
  String get completionRate => 'Tamamlanma Oranı';

  @override
  String get trackPersonalGoals => 'Ana sayfada kişisel hedefleri izleyin';

  @override
  String get wrappedTryAgain => 'Tekrar Dene';

  @override
  String get dataProtection => 'Veri Koruması';

  @override
  String get yourConversations => 'Görüşmeleriniz';

  @override
  String pdfTitleLabel(String title) {
    return 'Başlık: $title';
  }

  @override
  String get sendRawAudioToOmiDescription =>
      'Ham sesin Omi\'ye gönderilmesini önlemek için kapatın. Transkriptler ve bulut özelliklerinin gerektirdiği veriler yine de Omi\'ye gönderilebilir.';

  @override
  String get entityLoadFailed => 'Bu sayfa yüklenemedi.';

  @override
  String get networkNameSsid => 'Ağ Adı (SSID)';

  @override
  String get discovery => 'Keşif';

  @override
  String get rayBanMetaMicPickerConnectError =>
      'Bu mikrofona bağlanılamadı. iPhone Ayarları\'nda bağlı olduğundan emin olun.';

  @override
  String get fairUseAboutTitle => 'Adil Kullanım Hakkında';

  @override
  String get wrappedYouTalkedAbout => 'Hakkında konuştunuz';

  @override
  String get downgradeLimitQuality => '%30 daha düşük transkripsiyon kalitesi';

  @override
  String get sharedTasksUnknownSender => 'Birisi';

  @override
  String get selectAReason => 'Bir neden seç';

  @override
  String get wrappedWinLabel => 'ZAFER';

  @override
  String get configuration => 'Yapılandırma';

  @override
  String get noFolder => 'Klasör yok';

  @override
  String get manifestRefreshedSuccess => 'Manifest başarıyla yenilendi';

  @override
  String get paymentStatusActive => 'Aktif';

  @override
  String get linkKeyMismatch => 'Bağlantı anahtarı uyuşmazlığı';

  @override
  String speakerTagPromptProgress(int current, int total) {
    return '$current/$total';
  }

  @override
  String get updateRequiredMessage =>
      'Omi\'nin bu sürümü artık desteklenmiyor. Kayda ve eşitlemeye devam etmek için güncelleyin.';

  @override
  String get sharePeriodMonth => 'Bu ay, Omi:';

  @override
  String get rollbackToStableFirmware => 'Kararlı yazılıma geri dön';

  @override
  String get paymentStatusConnected => 'Bağlı';

  @override
  String get findDeviceNoneTitle => 'Omi Bulunamadı';

  @override
  String get appIdCopiedToClipboard => 'Uygulama Kimliği panoya kopyalandı';

  @override
  String get bySubmittingYouAgreeToOmi => 'Göndererek, Omi ';

  @override
  String get filterRating => 'Değerlendirme';

  @override
  String get usageAtWork => 'İşte';

  @override
  String get tasksCleanTodayMessage => 'Bu işlem yalnızca son tarihleri kaldırır';

  @override
  String get ignoredVoicesSubtitle => 'TV, podcast ve “Kişi Değil” olarak işaretlediğiniz diğer sesler';

  @override
  String get permissionEnable => 'Etkinleştir';

  @override
  String integrationComingSoon(String appName) {
    return '$appName henüz desteklenmiyor.';
  }

  @override
  String get sttModelLower => 'Daha düşük';

  @override
  String get loadingYourMemories => 'Anılarınız yükleniyor…';

  @override
  String get followUpQuestions => 'Takip Soruları';

  @override
  String get previousDay => 'Önceki gün';

  @override
  String fairUseCaseRefCopied(String caseRef) {
    return '$caseRef kopyalandı';
  }

  @override
  String get claudeDesktop => 'Claude Masaüstü';

  @override
  String get recordingPaused => 'Kayıt duraklatıldı';

  @override
  String get cannotReportOwnMessages => 'Kendi mesajlarınızı bildiremezsiniz';

  @override
  String get enterWordsHint => 'Kelimeleri girin (virgülle ayrılmış)';

  @override
  String get audioDownloadFailed => 'Ses indirme başarısız';

  @override
  String get clearMemoryMessage => 'Tüm anılarınız silinir. Bu işlem geri alınamaz.';

  @override
  String get templateNameHint => 'örn. Toplantı Görev Çıkarıcı';

  @override
  String speakerLabelTalkTime(String duration) {
    return 'Bu sesten $duration';
  }

  @override
  String get recordingMode => 'Kayıt modu';

  @override
  String get cancelReasonOther => 'Diğer';

  @override
  String get sttModelHigher => 'Daha yüksek';

  @override
  String get settingUpSystemAudioCapture => 'Sistem ses kaydı kuruluyor';

  @override
  String memoriesCount(int count) {
    return '$count anı';
  }

  @override
  String get noSpecificDataAccessConfigured => 'Belirli veri erişimi yapılandırılmamış.';

  @override
  String get recordingIdLabel => 'Kayıt Kimliği';

  @override
  String get highlights => 'Öne Çıkanlar';

  @override
  String get phoneTryAgain => 'Tekrar dene';

  @override
  String chatAppsCouldNotOpen(String app) {
    return '$app açılamadı. Yüklü olduğundan emin ol ve tekrar dene.';
  }

  @override
  String get onDeviceTranscriptionDesc => 'Transkripsiyon cihazınızda yerel olarak işlenir';

  @override
  String get chatAppsTryPromise => 'Dün Sam\'e ne söz verdim?';

  @override
  String get paymentStatusNotConnected => 'Bağlı Değil';

  @override
  String get intervalSeconds => 'Aralık (saniye)';

  @override
  String get authorize => 'İzin Ver';

  @override
  String get settingsHeader => 'AYARLAR';

  @override
  String get personNameAlreadyExists => 'Bu isimde bir kişi zaten mevcut.';

  @override
  String get deviceOnboardingVoiceReplyPreviewThroughCurrentOutput => 'Geçerli ses çıkışı aracılığıyla';

  @override
  String get monthJun => 'Haz';

  @override
  String selectedCount(int count) {
    return '$count seçildi';
  }

  @override
  String get batteryHistory => 'Pil';

  @override
  String get noPastChats => 'Omi ile sohbetleriniz burada görünür.';

  @override
  String get chatAppsDoesSave => 'Anıları kaydeder ve görevlerini yönetir';

  @override
  String get apiKey => 'API Anahtarı';

  @override
  String get authFailedToLinkGoogle => 'Google ile bağlantı kurulamadı, lütfen tekrar deneyin.';

  @override
  String audioUploadFailedKeptLocal(String duration) {
    return 'Yükleme başarısız — $duration ses telefonunuzda saklanıyor.';
  }

  @override
  String get free => 'Ücretsiz';

  @override
  String get deselectAllTasksMenu => 'Tümünün seçimini kaldır';

  @override
  String get dreamReportLoadFailed => 'Dream raporu yüklenemedi.';

  @override
  String get entityRecentConversations => 'Son konuşmalar';

  @override
  String get pendantRecordingNote =>
      'Pendant\'ın kendi kendine kayıt yapıyor. Uygulama açıkken kayıtlar telefonuna eşitlenir.';

  @override
  String get manageStorage => 'Depolamayı yönet';

  @override
  String get filterSystem => 'Hakkınızda';

  @override
  String get deleteConsequenceSubscription => 'Etkin abonelik iptal edilecektir.';

  @override
  String get defaultList => 'Varsayılan Liste';

  @override
  String get shared => 'Paylaşıldı';

  @override
  String get customVocabulary => 'Özel Kelime Dağarcığı';

  @override
  String get feedbackTitleAudioQuality => 'Ne tür sorunlar yaşadınız?';

  @override
  String get thisActionCannotBeUndone => 'Bu işlem geri alınamaz.';

  @override
  String errorRequestingPermission(String error) {
    return 'İzin isteği hatası: $error';
  }

  @override
  String get recapRegenerateFailed => 'Özet yeniden oluşturulamadı. Lütfen daha sonra tekrar deneyin.';

  @override
  String get result => 'Sonuç:';

  @override
  String get statusCallMissed => 'Cevapsiz arama';

  @override
  String get diagnosticsLongestGap => 'En uzun kesinti';

  @override
  String get noLogFilesFound => 'Günlük dosyası bulunamadı.';

  @override
  String get speechTranscriptionSectionTitle => 'Konuşma ve transkripsiyon';

  @override
  String get syncNow => 'Şimdi senkronize et';

  @override
  String get sttUsePrimaryLanguage => 'Birincil Dili Kullan';

  @override
  String get importUnsupportedFileType => 'Bu dosya türü içe aktarılamaz.';

  @override
  String get chatSendMessage => 'Mesajı gönder';

  @override
  String get syncCardAllBackedUp => 'Tüm kayıtlar eşitlendi';

  @override
  String get settings => 'Ayarlar';

  @override
  String get backgroundLocationDeniedDesc =>
      'Lütfen cihaz ayarlarına gidin ve konum iznini \"Her Zaman İzin Ver\" olarak ayarlayın';

  @override
  String get computationallyIntensive => 'Cihaz üzerinde transkripsiyon hesaplama açısından yoğundur.';

  @override
  String get and => ' ve ';

  @override
  String get yourVerifiedNumbers => 'Dogrulanmis numaralariniz';

  @override
  String get tasksCleanTodayTitle => 'Bugünün görevleri temizlensin mi?';

  @override
  String get microphonePermission => 'Mikrofon İzni';

  @override
  String get failedToUpdateConversationTitle => 'Sohbet başlığı güncellenemedi';

  @override
  String get appsDisconnected => 'Uygulamalarının ve entegrasyonlarının bağlantısı kesilecek.';

  @override
  String get live => 'Canlı';

  @override
  String get connectionFailed => 'Bağlantı başarısız';

  @override
  String get selectImages => 'Görsel Seç';

  @override
  String get playbackAudioNetworkFailed => 'Bağlantıyı Kontrol Edin';

  @override
  String get paypalEmail => 'PayPal E-postası';

  @override
  String get chatAppsOnTheList => 'Listedesin';

  @override
  String get generateSummary => 'Özet Oluştur';

  @override
  String get categoryHealth => 'Sağlık';

  @override
  String get transcribeLaterStorageFull =>
      'Telefonunda yer azaldığı için kayıt duraklatıldı. Yer aç ya da kayıtlarını yükle; ardından otomatik olarak devam eder.';

  @override
  String get chatAppsNoChatsTitle => 'Henüz sohbet yok';

  @override
  String get onboardingSetupStepPersonalize => 'Deneyiminiz kişiselleştiriliyor';

  @override
  String get leaveUnselectedTasks => 'Görevleri proje olmadan oluşturmak için seçilmemiş bırakın';

  @override
  String get wrappedButYouPushedThroughEmoji => 'Ama başardın 💪';

  @override
  String get needHelp => 'Yardıma mı İhtiyacınız Var?';

  @override
  String get confirmAndCancel => 'Onayla ve iptal et';

  @override
  String get frequencyDescHigh => 'Daha fazla öneri, günde yaklaşık 6–9';

  @override
  String get copyLink => 'Bağlantıyı kopyala';

  @override
  String get dreamReportLiveBanner =>
      'Dream bu değişiklikleri kendisi uygular. Hepsini Son Değişiklikler\'den geri alabilirsin.';

  @override
  String get enterActionItemDescription => 'Görev açıklamasını girin';

  @override
  String chatAppsInChannel(String app) {
    return '$app içinde';
  }

  @override
  String get links => 'Bağlantılar';

  @override
  String get dreamReportEmptyTitle => 'Henüz tur yok';

  @override
  String get monthJan => 'Oca';

  @override
  String get wrappedMostProductiveDay => 'En Verimli';

  @override
  String get productUpdate => 'Ürün Güncellemesi';

  @override
  String get addYourReview => 'Değerlendirmenizi Ekleyin';

  @override
  String get raybanMetaImageCaptureReady => 'Görüntü yakalama hazır';

  @override
  String get displayUpcomingMeetingsDescription => 'Yaklaşan toplantıları menü çubuğunda göster';

  @override
  String get whatWeCollect => 'Topladıklarımız';

  @override
  String get connectPayPalToReceivePayments =>
      'Uygulamalarınız için ödeme almaya başlamak için PayPal hesabınızı bağlayın';

  @override
  String get justAMoment => 'Bir dakika, lütfen';

  @override
  String get chatReplyServerError => 'Bizim tarafta bir sorun oluştu. Lütfen tekrar deneyin.';

  @override
  String get transferInProgress => 'Aktarım devam ediyor…';

  @override
  String get usageAll => 'Tüm Zamanlar';

  @override
  String get failedToLoadContacts => 'Kişiler yüklenemedi';

  @override
  String appUsersCount(int count) {
    return '$count+ kullanıcı';
  }

  @override
  String get report => 'Bildir';

  @override
  String get languageLabel => 'Dil';

  @override
  String verifiedOnDate(String date) {
    return '$date tarihinde dogrulandi';
  }

  @override
  String get customVocabularyHeader => 'ÖZEL KELIME DAĞARCIĞI';

  @override
  String otaRebooting(String deviceName) {
    return '$deviceName yeni yazılımla yeniden başlatılıyor.';
  }

  @override
  String get mcpServer => 'MCP Sunucusu';

  @override
  String get findDevice => 'Bul';

  @override
  String get msgUploadAttachedFileFailed => 'Ekli dosya yüklenemedi.';

  @override
  String get appName => 'App Name';

  @override
  String get pairingTitlePlaudNote => 'Plaud Note\'u Eşleştirme Moduna Alın';

  @override
  String get moreOptions => 'Diğer seçenekler';

  @override
  String get noConversationsHeroMessage =>
      'Kaydettiğin konuşmalar burada görünür. İlkini kaydetmek için Ana Sayfa\'da kayıt düğmesine dokun.';

  @override
  String get finish => 'Bitir';

  @override
  String get goBack => 'Geri Dön';

  @override
  String get apiKeysDescription =>
      'API anahtarları, uygulamanız Omi sunucusuyla iletişim kurarken kimlik doğrulama için kullanılır. Uygulamanızın anılar oluşturmasına ve diğer Omi hizmetlerine güvenli bir şekilde erişmesine olanak tanır.';

  @override
  String get sttProviderSpeechmatics => 'Speechmatics';

  @override
  String get setWebhookUrlInSettings => 'Bu özelliği kullanmak için geliştirici ayarlarında webhook URL\'yi ayarlayın.';

  @override
  String get dailyScoreBreakdown => 'Günlük Skor Detayı';

  @override
  String get showMeetingsMenuBarDesc =>
      'Bir sonraki toplantınızı ve başlamasına kalan süreyi macOS menü çubuğunda gösterin';

  @override
  String get tapToTrackThisGoal => 'Bu hedefi takip etmek için dokun';

  @override
  String get summarizingConversation => 'Konuşma özetleniyor…\nBu birkaç saniye sürebilir';

  @override
  String get noInternetConnection => 'İnternet bağlantısı yok';

  @override
  String diagnosticsCountSincePairing(int count) {
    return '$count eşleştirmeden beri';
  }

  @override
  String get wrappedTasksCreated => 'oluşturulan görev';

  @override
  String get deleteConsequenceNoRecovery => 'Hesabınız geri yüklenemez — destek ekibi bile yapamaz.';

  @override
  String get waitForReprocessing => 'Yeniden işlemenin bitmesini bekleyin.';

  @override
  String get needYourPermission => 'İzninize ihtiyacımız var';

  @override
  String get downgradeLimitSpeakers => 'Konuşmacılar tanımlanamaz';

  @override
  String conversationsTodayCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Bugün $count konuşma.',
      one: 'Bugün 1 konuşma.',
      zero: 'Bugün konuşma yok.',
    );
    return '$_temp0';
  }

  @override
  String get dailyScore => 'GÜNLÜK SKOR';

  @override
  String get reportAnIssue => 'Sorun bildirin';

  @override
  String get invalidKey => 'Geçersiz tuş';

  @override
  String get preview => 'Önizleme';

  @override
  String get nextWeek => 'Gelecek hafta';

  @override
  String get confidenceUnverified => 'Doğrulanmadı';

  @override
  String get previewScreenshots => 'Ekran görüntüsü önizlemesi';

  @override
  String get ledBrightness => 'LED Parlaklığı';

  @override
  String get firmwareUpdateFailedMessage =>
      'Güncelleme tamamlanmadı. Cihazınız hâlâ mevcut yazılımda ve güvenle kullanılabilir. Şarjlı ve telefonunuza yakın tutun, sonra tekrar deneyin.';

  @override
  String get loadingProfile => 'Profil yükleniyor…';

  @override
  String get deleteRecapConfirmTitle => 'Bu özet silinsin mi?';

  @override
  String get notificationFrequency => 'Bildirim Sıklığı';

  @override
  String get captureSystemAudioFromMeetings => 'Toplantılardan sistem sesini yakala';

  @override
  String get storeAudioCloudDescription => 'Konuşurken kayıtlarınızı yükler, böylece daha sonra geri oynatabilirsiniz.';

  @override
  String get color => 'Renk';

  @override
  String get open => 'Aç';

  @override
  String get diagnosticsVerdictNoDrops => 'Bu hafta kopma yok';

  @override
  String get autoExtractionFeature => 'Konuşmalardan otomatik olarak çıkarıldı';

  @override
  String get searchResults => 'Arama sonuçları';

  @override
  String get v2UndetectedMessage =>
      'V1 cihazınız olduğunu veya cihazınızın bağlı olmadığını görüyoruz. SD Kart işlevi yalnızca V2 cihazlar için mevcuttur.';

  @override
  String get endAndProcess => 'Konuşmayı Sonlandır ve İşle';

  @override
  String get noSyncedRecordings => 'Henüz senkronize kayıt yok';

  @override
  String get coworker => 'İş arkadaşı';

  @override
  String get setupQuestionUsage => '2. Omi\'yi nerede kullanmayı planlıyorsunuz?';

  @override
  String get pinnedNotSelectable => 'Sabitli, seçilemez';

  @override
  String get showMore => 'daha fazla göster ↓';

  @override
  String get createYourFirstMemory => 'Başlamak için ilk anınızı oluşturun';

  @override
  String get discardedConversation => 'Atılan konuşma';

  @override
  String get enableApps => 'Uygulamaları etkinleştir';

  @override
  String get today => 'Bugün';

  @override
  String get showEventsNoParticipantsDesc =>
      'Etkinleştirildiğinde, Yaklaşanlar katılımcısı veya video bağlantısı olmayan etkinlikleri gösterir.';

  @override
  String get couldNotLoadPage => 'Bu sayfa yüklenemedi. Bağlantınızı kontrol edip tekrar deneyin.';

  @override
  String actionItemDeletedResult(String description) {
    return 'Görev \"$description\" silindi';
  }

  @override
  String get deleteSampleQuestion => 'Örnek silinsin mi?';

  @override
  String get youAreOnAPaidPlan => 'Ücretli bir plandasınız.';

  @override
  String get otaInstallFailed => 'Yükleme başarısız. Cihazınız hâlâ mevcut yazılımda.';

  @override
  String get addFirstMemory => 'İlk anınızı ekleyin';

  @override
  String get appDeletedSuccessfully => 'Uygulama başarıyla silindi';

  @override
  String get chatAppsConnectTelegramMessage => 'Omi, yalnızca sana özel bir bağlantıyla Telegram\'ı açacak.';

  @override
  String get phoneSetupStep1Title => 'Telefon numaranizi dogrulayin';

  @override
  String get deviceRequirements => 'Cihazınız Cihaz Üzerinde transkripsiyon gereksinimlerini karşılamıyor.';

  @override
  String get confidenceEvidenceHeader => 'Kanıtlar';

  @override
  String get pleaseEnterAName => 'Lütfen bir ad girin.';

  @override
  String get deleteConfirmationWord => 'DELETE';

  @override
  String get speakerTagPromptThatsMe => 'Bu benim';

  @override
  String get ourCommitment => 'Taahhüdümüz';

  @override
  String get notificationScopes => 'Bildirim Kapsamları';

  @override
  String get autoDeletesAfter3Days => '3 gün sonra otomatik olarak silinir';

  @override
  String get initialisingRecorder => 'Kayıt Cihazı Başlatılıyor';

  @override
  String get privateAndSecureOnDevice => 'Bu telefonda kaydedildi';

  @override
  String get allObjectsMigratedFinalizing => 'Tüm nesneler taşındı. Tamamlanıyor…';

  @override
  String get chatAppsOpenMessages => 'Mesajlar\'ı aç';

  @override
  String get upgradeToPro => 'Pro\'ya Yükselt';

  @override
  String get clientId => 'İstemci Kimliği';

  @override
  String get backgroundActivity => 'Arka plan etkinliği';

  @override
  String get noSummaryAvailable => 'Özet Mevcut Değil';

  @override
  String get failedToUpdateStarred => 'Favorilere ekleme durumu güncellenemedi.';

  @override
  String get omiYourAiCompanion => 'Omi – Yapay Zeka Yardımcınız';

  @override
  String get pleaseSelectReason => 'Lütfen bir neden seçin';

  @override
  String clearMemoryConfirmation(int count) {
    return '$count anının tamamı silinir. Bu işlem geri alınamaz.';
  }

  @override
  String get connectNow => 'Şimdi Bağlan';

  @override
  String chatAppsDisconnectTitle(String app) {
    return '$app bağlantısı kesilsin mi?';
  }

  @override
  String get clearCredentials => 'Kimlik Bilgilerini Temizle';

  @override
  String get grantContactsPermissionForSms => 'SMS ile paylaşmak için lütfen kişi izni verin';

  @override
  String get cloudTranscription => 'Bulut transkripsiyonu';

  @override
  String get memoryHistory => 'Geçmiş';

  @override
  String get speechSamples => 'Ses örnekleri';

  @override
  String get wrappedBiggest => 'En büyük';

  @override
  String get reviewShowMore => 'Daha fazla göster';

  @override
  String get triggersWhenDaySummaryGenerated => 'Günlük özet oluşturulduğunda tetiklenir.';

  @override
  String get thankYouFeedback => 'Geri bildiriminiz için teşekkürler!';

  @override
  String get allow => 'İzin Ver';

  @override
  String triggeredByType(String triggerType) {
    return '$triggerType tarafından tetiklendi';
  }

  @override
  String get howToPair => 'Nasıl Eşleştirilir';

  @override
  String get conversationDeveloperTools => 'Konuşmalarda geliştirici araçları';

  @override
  String get memoryProvenanceIphone => 'iPhone';

  @override
  String get aboutYou => 'Hakkınızda';

  @override
  String get memoryProvenanceMac => 'Mac';

  @override
  String get effectCounts => 'Yardımcı olur';

  @override
  String get tagSpeakerIncludingLaterSpeech => 'Bu konuşmacının sonraki konuşmasını da etiketle';

  @override
  String get storeAudioOnPhone => 'Sesi Telefonda Depola';

  @override
  String get developerApiKeys => 'Geliştirici API Anahtarları';

  @override
  String get wrappedMyBuddiesCard => 'Arkadaşlarım';

  @override
  String get bulkExportAlreadyExported => 'Seçilen tüm görevler zaten dışa aktarıldı';

  @override
  String get popularBadge => 'POPÜLER';

  @override
  String get enableLocationTitle => 'Konumu Etkinleştir';

  @override
  String get feedbackBug => 'Geri Bildirim / Hata';

  @override
  String get good => 'İyi';

  @override
  String get upgradeYourPlan => 'Planınızı Yükseltin';

  @override
  String get exportingAllData =>
      'Verileriniz dışa aktarılıyor… Omi\'yi açık tutun; büyük hesaplar birkaç dakika sürebilir.';

  @override
  String get switchAndRestart => 'Değiştir';

  @override
  String get noReposFound => 'Depo bulunamadı';

  @override
  String get latest => 'En son';

  @override
  String get failedToRevoke => 'İzin geri alınamadı. Lütfen tekrar deneyin.';

  @override
  String get appleHealthDisconnectCta => 'Apple Health Bağlantısını Kes';

  @override
  String get chatAppsPrivateMemoriesSubtitle =>
      'Sağlık, para ve özel olarak işaretlediğin her şey sohbet uygulamalarının dışında kalır.';

  @override
  String get deleteFlowFeedbackTitle => 'Daha fazlasını anlat';

  @override
  String get failedToConnectTodoistRetry => 'Todoist\'a bağlanılamadı. Lütfen tekrar deneyin.';

  @override
  String get capturePhoneStorageFull => 'Telefon depolama alanı dolu';

  @override
  String deletePeopleTitle(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count kişi silinsin mi?',
      one: '1 kişi silinsin mi?',
    );
    return '$_temp0';
  }

  @override
  String get cleanUpNothingMessage => 'Omi şu anda hiç kimse konusunda kararsız değil.';

  @override
  String get writeAReviewOptional => 'Bir değerlendirme yazın (isteğe bağlı)';

  @override
  String get syncFailed => 'Senkronizasyon başarısız';

  @override
  String get audioShareFailed => 'Paylaşım Başarısız';

  @override
  String loadMoreRemaining(String count) {
    return 'Daha fazla yükle ($count kaldı)';
  }

  @override
  String get phoneDeleteNumberFailed => 'Bu numara silinemedi';

  @override
  String deviceUsesCodec(String device, String reason) {
    return '$device bu sağlayıcının okuyamayacağı bir biçimde kaydediyor ($reason), bu yüzden bunun yerine Omi\'nin transkripsiyonu kullanılacak.';
  }

  @override
  String get chatAppsConnectIMessageMessage =>
      'Kullanmak istediğin numaradan Omi\'ye bir mesaj gönder. İçindeki kod, bu numarayı hesabına bağlar.';

  @override
  String get speechToTextUnavailableDesc =>
      'Konuşmayı metne dönüştürme şu anda kullanılamıyor. İnternet bağlantınızı ve cihazınızın konuşma tanıma ayarlarını kontrol edip tekrar deneyin.';

  @override
  String get chatReplyTimeout => 'Yanıt çok uzun sürdü. Lütfen tekrar deneyin.';

  @override
  String get passwordMinLengthError => 'Şifre en az 8 karakter olmalıdır';

  @override
  String get chatAppsWhatsAppMessage =>
      'Omi\'yi WhatsApp\'a getirmek için çalışıyoruz. Hazır olduğunda burada görünecek.';

  @override
  String get deleteAccountCheckbox =>
      'Hesabımı silmenin kalıcı olduğunu ve anılar ve konuşmalar dahil tüm verilerin kaybolacağını ve kurtarılamayacağını anlıyorum.';

  @override
  String get firmwareConnectWifi => 'WiFi veya hücresel veriye bağlanın.';

  @override
  String get forgetDeviceConfirmMessage => 'Omi bu cihaza bağlanmayı bırakacak.';

  @override
  String get editSwipeFeature => 'Düzenlemek için dokunun, tamamlamak veya silmek için kaydırın';

  @override
  String get memoryManagement => 'Bellek Yönetimi';

  @override
  String get transcriptLoadFailed => 'Döküm yüklenemedi.';

  @override
  String get diagnosticsExportTitle => 'Omi Cihaz Tanılama';

  @override
  String get updateOmiFirmware => 'Omi yazılımını güncelle';

  @override
  String get importTooManyAttempts => 'Şu anda çok fazla içe aktarma var. Daha sonra tekrar deneyin.';

  @override
  String get noAppsFound => 'Uygulama bulunamadı';

  @override
  String get phoneSetupStep1Subtitle => 'Onaylamak icin sizi arayacagiz';

  @override
  String get deleteSyncedFiles => 'Senkronize kayıtları sil';

  @override
  String speakerLabelVoiceStatus(String state) {
    String _temp0 = intl.Intl.selectLogic(
      state,
      {
        'learned': 'Ses öğrenildi',
        'pending': 'Ses öğreniliyor…',
        'disabled': 'Ses kaydetme kapalı',
        'other': 'Ses henüz öğrenilmedi',
      },
    );
    return '$_temp0';
  }

  @override
  String get recordingsMayCaptureOthers =>
      'Kayıtlar başkalarının seslerini yakalayabilir. Etkinleştirmeden önce tüm katılımcıların onayını aldığınızdan emin olun.';

  @override
  String get helpful => 'Yararlı';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return '$model indiriliyor: $received / $total MB';
  }

  @override
  String get permissions => 'İzinler';

  @override
  String get audioDownloadSuccess => 'Ses başarıyla indirildi';

  @override
  String get confirmPlanChange => 'Plan Değişikliğini Onayla';

  @override
  String get wrappedThatAwkwardMoment => 'O Garip An';

  @override
  String get calendarProviders => 'Takvim Sağlayıcıları';

  @override
  String evidenceAutoUnconfirmed(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count otomatik etiket henüz onaylanmadı',
      one: '1 otomatik etiket henüz onaylanmadı',
    );
    return '$_temp0';
  }

  @override
  String get importData => 'Veri İçe Aktar';

  @override
  String get weekdayMon => 'Pzt';

  @override
  String get deviceStorageTitle => 'Cihaz depolama';

  @override
  String get externalAppAccess => 'Harici Uygulama Erişimi';

  @override
  String get transcriptionUnavailable => 'Transkripsiyon kullanılamıyor';

  @override
  String get termsAndPrivacyPolicy => 'Şartlar ve Gizlilik Politikası';

  @override
  String get noImportsYet => 'Henüz içe aktarma yok';

  @override
  String get openOmiOnAppleWatchDescription =>
      'Omi uygulaması Apple Watch\'unuza yüklü. Açın ve başlamak için Başlat\'a dokunun.';

  @override
  String dreamReportFailed(String error) {
    return 'Başarısız ($error)';
  }

  @override
  String get sendSummary => 'Özet gönder';

  @override
  String get filterAll => 'Tümü';

  @override
  String get deleteChatMessage => 'Geçmiş sohbetlerden kalıcı olarak kaldırılır.';

  @override
  String get timeout10Minutes => '10 dakika';

  @override
  String get noCalendarEventsNearby => 'Bu saat civarında takvim etkinliği bulunamadı.';

  @override
  String get cancelSyncQuestion => 'Senkronizasyon iptal edilsin mi?';

  @override
  String get whatShouldWeMake => 'Ne yapalım?';

  @override
  String get usageListened => 'Listened';

  @override
  String get errorUpdatingStripeDetails => 'Stripe bilgilerini güncellerken hata! Lütfen daha sonra tekrar deneyin.';

  @override
  String get conversationEndAfterHours => 'Konuşmalar artık 4 saat sessizlikten sonra sonlanacak';

  @override
  String get issueActivatingApp => 'Bu uygulamayı etkinleştirirken bir sorun oluştu. Lütfen tekrar deneyin.';

  @override
  String get appCreatedSuccessfully => 'Uygulama başarıyla oluşturuldu!';

  @override
  String get categoryNews => 'Haberler';

  @override
  String get phoneSearchHint => 'Ara';

  @override
  String peoplePinnedCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count sabitli',
      one: '1 sabitli',
    );
    return '$_temp0';
  }

  @override
  String get wrappedHours => 'saat';

  @override
  String get phoneKeypad => 'Tuş takımı';

  @override
  String get peopleFilterLowConfidence => 'Düşük güven';

  @override
  String get agreeToContributeData => 'AI eğitimi için verilerimi katkıda bulunmayı anlıyorum ve kabul ediyorum';

  @override
  String get addGoal => 'Hedef Ekle';

  @override
  String get dreamReportRunInProgress => 'Bir tur zaten çalışıyor. Bir dakika sonra tekrar dene.';

  @override
  String importedConfig(String providerName) {
    return '$providerName yapılandırması içe aktarıldı';
  }

  @override
  String monthsAgo(int count) {
    return '$count ay önce';
  }

  @override
  String get downgradeLimitationsHeading => 'Şu kısıtlamalarla karşılaşacaksınız:';

  @override
  String get chatRemoveSelectedText => 'Alıntılanan metni kaldır';

  @override
  String get firmwareBatteryAbove15 => 'Pil %15\'in üzerinde';

  @override
  String reviewQuestionSamePerson(String name) {
    return '“$name” ile aynı kişi mi?';
  }

  @override
  String get effectCountsALot => 'Çok yardımcı olur';

  @override
  String get sdCard => 'SD Kart';

  @override
  String get openInGoogleCalendar => 'Google Takvim\'de Aç';

  @override
  String get appleHealthFeatureSecureTitle => 'Güvenli senkronizasyon';

  @override
  String get conversationDeveloperToolsDescription =>
      'Konuşma menüsünde Konuşma kimliğini kopyala ve İstemi test et seçeneklerini göster';

  @override
  String get host => 'Sunucu';

  @override
  String get deleteReasonMissingFeatures => 'İhtiyacım olan özellikler eksik';

  @override
  String get syncingInProgress => 'Senkronizasyon devam ediyor';

  @override
  String get tabDone => 'Bitti';

  @override
  String get revoke => 'İptal Et';

  @override
  String get mcp => 'MCP';

  @override
  String get anyoneCanDiscoverTemplate => 'Herkes şablonunuzu keşfedebilir';

  @override
  String get mcpDescription =>
      'Anılarınızı ve konuşmalarınızı okumak, aramak ve yönetmek için Omi\'yi diğer uygulamalarla bağlamak için. Başlamak için bir anahtar oluşturun.';

  @override
  String get connectionLostDescription => 'Bağlantı kesildi. İnternet bağlantınızı kontrol edin ve tekrar deneyin.';

  @override
  String chatAppsNoChatsMessage(String app) {
    return '$app içinde Omi ile yaptığın sohbetler burada görünür.';
  }

  @override
  String get storedLocallyNeverShared => 'Bu telefonda kaydedilir. Yalnızca transkripsiyon sağlayıcınıza gönderilir.';

  @override
  String get morePaymentMethodsComingSoon => 'Daha fazla ödeme yöntemi yakında';

  @override
  String get allCaughtUp => 'Her şey güncel';

  @override
  String previewImageLabel(int index, int total) {
    return 'Ekran görüntüsü $index/$total';
  }

  @override
  String get disable => 'Devre Dışı Bırak';

  @override
  String get recordings => 'Kayıtlar';

  @override
  String get enterPersonsName => 'Kişinin Adını Girin';

  @override
  String get newConversationCreated => 'Yeni konuşma oluşturuldu';

  @override
  String resetsInDays(int count) {
    return '$count gün sonra sıfırlanır';
  }

  @override
  String get confidenceConfirmed => 'Onaylandı';

  @override
  String get bulkExportInProgress => 'Dışa aktarılıyor…';

  @override
  String get detectLanguages => '10+ dil algıla';

  @override
  String get phoneSpeaker => 'Hoparlor';

  @override
  String get visitWebsite => 'Web sitesini ziyaret edin';

  @override
  String get howToTakeGoodSample => 'İyi bir örnek nasıl alınır?';

  @override
  String get clearChat => 'Sohbeti Temizle';

  @override
  String languageSetTo(String language) {
    return 'Dil $language olarak ayarlandı';
  }

  @override
  String get deviceOnboardingVoiceReplyHeadphonesDescription =>
      'Özel. Yalnızca AirPods, Bluetooth veya kablolu kulaklık aracılığıyla konuşur.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'Planınız $date tarihine kadar aktif kalacak. Bundan sonra sınırsız özelliklerinize erişiminizi kaybedeceksiniz.';
  }

  @override
  String get clientSecret => 'İstemci Gizli Anahtarı';

  @override
  String get pairingTitleAppleWatch => 'Apple Watch Bağlayın';

  @override
  String get share => 'Paylaş';

  @override
  String get yourPrivacyYourControl => 'Gizliliğiniz, Kontrolünüz';

  @override
  String get tapToCopy => 'Kopyalamak için dokunun';

  @override
  String get feedbackTitleFoundAlternative => 'Neye geçiyorsunuz?';

  @override
  String get all => 'Tümü';

  @override
  String get filterCapabilities => 'Yetenekler';

  @override
  String get tagOtherSegments => 'Diğer bölümleri etiketle';

  @override
  String get entityDecisions => 'Kararlar';

  @override
  String get tasksCreatedInWorkspace => 'Görevler bu çalışma alanında oluşturulacak';

  @override
  String get fairUseDailyTranscription => 'Günlük transkripsiyon';

  @override
  String get pausePlayback => 'Duraklat';

  @override
  String get sharedTasksLinkExpired => 'Bu paylaşılan görevler bulunamadı veya bağlantının süresi doldu.';

  @override
  String get editConversationDialogTitle => 'Sohbeti Düzenle';

  @override
  String get deleteMemoryConfirmation => 'Bu anı silinsin mi? Bu işlem geri alınamaz.';

  @override
  String get appUnderReviewMessage =>
      'Uygulamanız inceleniyor ve yalnızca size görünür. Onaylandıktan sonra herkese açık olacak.';

  @override
  String get illDoItLater => 'Daha sonra yapacağım';

  @override
  String get captureStillRecording => 'Kayıt sürüyor';

  @override
  String confidenceNextLabels(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Onları $count konuşmada daha etiketleyin.',
      one: 'Onları 1 konuşmada daha etiketleyin.',
    );
    return '$_temp0';
  }

  @override
  String get speakerTagPromptAnswerFailed => 'Kaydedilemedi. Lütfen tekrar deneyin.';

  @override
  String get feedbackReasonSummaryIncomplete => 'Eksik';

  @override
  String get errorActivatingApp => 'Uygulamayı etkinleştirme hatası';

  @override
  String get tasksCompleted => 'Tamamlanan Görevler';

  @override
  String onboardingStepOf(int current, int total) {
    return 'Adım $current/$total';
  }

  @override
  String get downgradeAnyway => 'Yine de Düşür';

  @override
  String get leaveBlank => 'Boş bırakın';

  @override
  String get chatAppsViewChats => 'Sohbetleri Görüntüle';

  @override
  String get captureScreenRecordingPermissionRequired => 'Ekran kaydı izni gerekli';

  @override
  String get accountCutoverUpdateRequiredTitle => 'Güncelleme gerekli';

  @override
  String weeksAgo(int count) {
    return '$count hafta önce';
  }

  @override
  String get phoneEndCall => 'Bitir';

  @override
  String get startupFailedMessage =>
      'Omi başlatılırken bir sorun oluştu. Bağlantınızı kontrol edin, ardından tekrar deneyin.';

  @override
  String get permissionRevokedTitle => 'İzin Geri Alındı';

  @override
  String get chatFeatures => 'Sohbet Özellikleri';

  @override
  String get couldNotLoadMap => 'Harita yüklenemedi';

  @override
  String get selectContactsToShare => 'Paylaşılacak kişileri seçin';

  @override
  String get ok => 'Tamam';

  @override
  String get memoryReviewConfirmed => 'Onaylandı.';

  @override
  String get deleteKnowledgeGraph => 'Bilgi Grafiğini Sil';

  @override
  String get reviewChangeFailed => 'Bu değişiklik güncellenemedi. Tekrar deneyin.';

  @override
  String get limitless => 'Limitless';

  @override
  String uploadingToCloud(int current, int total) {
    return '$current/$total yükleniyor';
  }

  @override
  String get dontSeeYourDevice => 'Cihazınızı görmüyor musunuz?';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Görevleriniz $appName hesabınıza senkronize edilecek';
  }

  @override
  String appSettingsLabel(String appName) {
    return '$appName ayarları';
  }

  @override
  String get chatBlockShowLess => 'Daha Az Göster';

  @override
  String get mindMap => 'Mind Map';

  @override
  String get authorizationBearer => 'Authorization: Bearer <key>';

  @override
  String get dreamReportWouldSuggestTasks => 'Görev önerirdi';

  @override
  String get dreamReportWouldAsk => 'Sana sorardı';

  @override
  String get getFreeUnlimitedAccess => 'Ücretsiz sınırsız erişim kazan';

  @override
  String get yourDaysJourney => 'Günün Yolculuğu';

  @override
  String get transcriptReceived => 'Transkript alındı';

  @override
  String get expand => 'Genişlet';

  @override
  String get onboardingCompleteMessage =>
      'Omi\'yi birkaç gün açık tutun. Konuşmalarınız, anılarınız ve yapılacaklarınız dolmaya başlayacak.';

  @override
  String get trainFamilyProfiles => 'Arkadaşlar ve Aile için Profil Eğitin';

  @override
  String get selectText => 'Metin Seç';

  @override
  String get generatingDescription => 'Açıklama oluşturuluyor…';

  @override
  String get deviceOnboardingStarConversationDesc => 'Konuşmayı önemli olarak işaretle';

  @override
  String disableAppNamed(String appName) {
    return '$appName uygulamasını devre dışı bırak';
  }

  @override
  String get deleteConversationConfirmation => 'Bu konuşma silinsin mi? Bu işlem geri alınamaz.';

  @override
  String get contentCopied => 'İçerik panoya kopyalandı';

  @override
  String get joinTheCommunity => 'Topluluğa katılın!';

  @override
  String get noContactsWithPhoneNumbers => 'Telefon numarası olan kişi bulunamadı';

  @override
  String get removeAttachment => 'Eki kaldır';

  @override
  String get followTheVoiceInstructions => 'Sesli talimatlari izleyin';

  @override
  String get createYourOwnApp => 'Kendi Uygulamanızı Oluşturun';

  @override
  String get paymentDetails => 'Ödeme Detayları';

  @override
  String get tellOmiWhoSaidIt => 'Omi\'ye kimin söylediğini söyleyin 🗣️';

  @override
  String audioInputSetTo(String deviceName) {
    return 'Ses girişi $deviceName olarak ayarlandı';
  }

  @override
  String get pleaseEnterValidEmail => 'Lütfen geçerli bir e-posta adresi girin';

  @override
  String get thisYear => 'Bu Yıl';

  @override
  String get noTranscriptMessage => 'Bu sohbetin transkripti yok.';

  @override
  String get appearanceDark => 'Koyu';

  @override
  String get createCustomTemplate => 'Özel Şablon Oluştur';

  @override
  String get monthMay => 'May';

  @override
  String get tasksAddedToList => 'Görevler bu listeye eklenecek';

  @override
  String isTriggeredBy(String triggerDescription) {
    return '$triggerDescription.';
  }

  @override
  String get deleteConversationTitle => 'Konuşma Silinsin mi?';

  @override
  String get accountCutoverUpdateRequiredMessage =>
      'Hesap taşımasından sonra devam etmek için en son Omi uygulamasını yükleyin.';

  @override
  String get txtFormat => 'TXT';

  @override
  String chatAppsDisconnectMessage(String app) {
    return 'Omi, $app içinde yanıt vermeyi bırakır ve onun için tuttuğu sohbet geçmişini siler. $app içindeki mevcut mesajlar orada kalır.';
  }

  @override
  String get captureWithCamera => 'Kamera ile yakala';

  @override
  String get appIdLabel => 'Uygulama Kimliği';

  @override
  String get endpointUrl => 'Uç Nokta URL\'si';

  @override
  String get actionItemUpdated => 'Görev güncellendi';

  @override
  String itemsSelected(int count) {
    return '$count seçildi';
  }

  @override
  String get onboardingWhatIKnowAboutYouDescription => 'Bu harita, Omi konuşmalarınızdan öğrendikçe güncellenir.';

  @override
  String diagnosticsLastDuration(String duration) {
    return 'Son $duration';
  }

  @override
  String get pairingDescLimitless =>
      'Herhangi bir ışık görünürken, bir kez basın, ardından cihaz pembe ışık gösterene kadar basılı tutun, sonra bırakın.';

  @override
  String get chatBlockOpenConversation => 'Konuşmayı aç';

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return 'Bu ay $limit içgörüden $used elde edildi';
  }

  @override
  String get connectionErrorDesc =>
      'Sunucuya bağlanılamadı. Lütfen internet bağlantınızı kontrol edin ve tekrar deneyin.';

  @override
  String get enterWordsCommaSeparated => 'Kelimeleri girin (virgülle ayırın)';

  @override
  String get otherDevicesComingSoon => 'Diğer cihazlar yakında';

  @override
  String speakerSuggestionChip(String name) {
    return '$name?';
  }

  @override
  String get speakerTagPromptNotAPersonToast => 'Kişi değil olarak işaretlendi';

  @override
  String get createKeyToGetStarted => 'Başlamak için bir anahtar oluşturun';

  @override
  String get captureRecordingSeparateConfirm => 'Ayır';

  @override
  String get diagnosticsDrops => 'Kopmalar';

  @override
  String lowBatteryAlertBody(int level) {
    return 'Pil seviyeniz %$level. Şarj etme zamanı! 🔋';
  }

  @override
  String get deviceOnboardingTurnOffSubtitle => 'Düğmeyi 3 saniye basılı tutun';

  @override
  String get done => 'Tamamlandı';

  @override
  String get wifiConfigurationSubtitle =>
      'Cihazın donanım yazılımını indirebilmesi için WiFi kimlik bilgilerinizi girin.';

  @override
  String get permissionGrantedNow =>
      'İzin verildi! Şimdi:\n\nSaatinizdeki Omi uygulamasını açın ve aşağıda \"Devam Et\"e dokunun';

  @override
  String get setUpPayPal => 'PayPal\'ı Ayarla';

  @override
  String get statusProcessed => 'İşlendi';

  @override
  String phoneFreeCallsRemaining(int remaining, int limit) {
    return 'Bu ay $remaining ücretsiz arama kaldı ($limit aramadan)';
  }

  @override
  String get event => 'Etkinlik';

  @override
  String get conversationEvents => 'Konuşma Olayları';

  @override
  String get uninstall => 'Kaldır';

  @override
  String get appCreators => 'Uygulama Geliştiricileri';

  @override
  String get muted => 'Sessiz';

  @override
  String get deleteRecapAction => 'Sil';

  @override
  String get addAppErrorSelectingThumbnailRetry => 'Küçük resim seçilirken hata. Tekrar deneyin.';

  @override
  String get basicPlanDescription => '300 premium dakika + cihazda sınırsız';

  @override
  String get countrySelectionPermanent => 'Ülke seçiminiz kalıcıdır ve daha sonra değiştirilemez.';

  @override
  String get transcriptionConnecting => 'Transkripsiyon bağlanıyor…';

  @override
  String transcriptionsPendingFraction(int pending, int total) {
    return 'Bekleyen transkriptler $pending/$total';
  }

  @override
  String get apiKeyAuth => 'API Anahtar Kimlik Doğrulaması';

  @override
  String downloadModelWithName(String model) {
    return 'Model İndir ($model)';
  }

  @override
  String get devModeInvalidDaySummaryWebhookUrl => 'Geçersiz günlük özet webhook URL\'si';

  @override
  String get memoryReviewSaveFailed => 'Kaydedilemedi, tekrar deneyin';

  @override
  String get payYourSttProvider => 'Omi\'de ücretsiz. Transkripsiyon sağlayıcınıza doğrudan siz ödersiniz.';

  @override
  String get dailySummaryHeader => 'GÜNLÜK ÖZET';

  @override
  String get fairUseStageWarning => 'Uyarı';

  @override
  String get multipleSpeakersDesc =>
      'Kayıtta birden fazla konuşmacı var gibi görünüyor. Lütfen sessiz bir yerde olduğunuzdan emin olun ve tekrar deneyin.';

  @override
  String get pastChats => 'Geçmiş sohbetler';

  @override
  String get listeningMins => 'Dinleme (dk)';

  @override
  String get pairingDescOmi => 'Cihazı açmak için titreşene kadar basılı tutun.';

  @override
  String get deviceOnboardingIntroSubtitle =>
      'Canlı transkripsiyonu, bir soru sormayı ve çift dokunma kısayolunu deneyin.';

  @override
  String get autoRemoveSyncedCopiesTitle => 'Senkronize Kopyaları Otomatik Kaldır';

  @override
  String chatAppsReadOnlyFooter(String app) {
    return 'Bu sohbetler burada salt okunurdur. $app içinde yanıtla.';
  }

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'Mikrofon değiştirildi. $countdown saniye içinde devam ediliyor';
  }

  @override
  String get takePhoto => 'Fotoğraf Çek';

  @override
  String get cancelSync => 'Senkronizasyonu İptal Et';

  @override
  String appSettings(String appName) {
    return '$appName Ayarları';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'Mikrofon izni kontrol edilemedi: $error';
  }

  @override
  String get micGain => 'Mikrofon Kazancı';

  @override
  String get collectingData => 'Veri toplanıyor…';

  @override
  String get memoryReadOnlyHint => 'Bu anı geçmiş olarak saklanıyor ve düzenlenemez.';

  @override
  String get appUnderReviewOwner =>
      'Uygulamanız inceleniyor ve yalnızca size görünür. Onaylandıktan sonra herkese açık olacak.';

  @override
  String get addNewPerson => 'Yeni Kişi Ekle';

  @override
  String get nameSpeakerTitle => 'Konuşmacıyı Adlandır';

  @override
  String get downloadingAudioFromSdCard => 'Cihazınızın SD kartından ses indiriliyor';

  @override
  String get pendantSyncingRecordings => 'Pendant\'ından kayıtlar eşitleniyor…';

  @override
  String get otaNotSupported => 'Bu yazılım Wi-Fi üzerinden güncellenemez.';

  @override
  String get wrappedSomethingWentWrong => 'Bir şeyler\nyanlış gitti';

  @override
  String get screenRecording => 'Ekran Kaydı';

  @override
  String get audioProcessedLocally =>
      'Ses yerel olarak işlenir. Çevrimdışı çalışır, daha özel, ancak daha fazla pil kullanır.';

  @override
  String get onboardingSignIn => 'Giriş Yap';

  @override
  String timeDaysPlural(int count) {
    return '$count gün';
  }

  @override
  String get memoryReviewTitle => 'Bugün öğrendiklerim';

  @override
  String get hidePassword => 'Şifreyi gizle';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get disconnected => 'Bağlantı kesildi';

  @override
  String get revokeApiKeyQuestion => 'API Anahtarını İptal Et?';

  @override
  String get detectBrowserBasedMeetings => 'Tarayıcı tabanlı toplantıları algıla';

  @override
  String get failedToDeleteConversations => 'Konuşmalar silinemedi';

  @override
  String get raybanMetaCapturePhoto => 'Fotoğraf Çek';

  @override
  String get bleSpeed => 'BLE ile ~30 KB/s';

  @override
  String get conversationPromptPlaceholder =>
      'Harika bir uygulamasınız, size bir konuşmanın transkripti ve özeti verilecek…';

  @override
  String get secureAuthViaGoogleAccount => 'Google Hesabı üzerinden güvenli kimlik doğrulama';

  @override
  String get omiHas => 'Omi:';

  @override
  String get raybanMetaContinue => 'Devam Et';

  @override
  String get pauseRecording => 'Kaydı Duraklat';

  @override
  String get evidenceNothing => 'Henüz etiketlemediniz veya onaylamadınız';

  @override
  String get noActivityYet => 'Henüz Aktivite Yok';

  @override
  String get enterPasswordError => 'Lütfen şifrenizi girin';

  @override
  String get forgetDeviceConfirmTitle => 'Cihaz unutulsun mu?';

  @override
  String get ratingsAndReviews => 'Puanlar ve Yorumlar';

  @override
  String get addApiKeyAfterImport => 'İçe aktardıktan sonra kendi API anahtarınızı eklemeniz gerekecek';

  @override
  String get alreadyOnStableFirmware => 'Zaten en son kararlı sürümdesiniz.';

  @override
  String get deleteAccountConfirm => 'Hesabınızı silmek istediğinizden emin misiniz?';

  @override
  String get recordingInfo => 'Kayıt Bilgisi';

  @override
  String get feedbackReasonSummaryInaccurate => 'Hatalı';

  @override
  String get pendantRecordingTitle => 'Pendant\'ta kayıt yapılıyor';

  @override
  String get deleteWhileProcessingMessage =>
      'Bu kayıt yüklendi ancak Omi hâlâ konuşmayı oluşturuyor. Şimdi silerseniz ve işleme başarısız olursa kurtarılamaz. Yine de silinsin mi?';

  @override
  String get createNewKey => 'Yeni Anahtar Oluştur';

  @override
  String get firmwareDownloadFailedMessage =>
      'Güncelleme indirilemedi ve cihazınız değişmedi. İnternet bağlantınızı kontrol edip tekrar deneyin.';

  @override
  String get loadingTasks => 'Görevler yükleniyor…';

  @override
  String get previousResult => 'Önceki sonuç';

  @override
  String get reviewLoadFailed => 'Sorularınız yüklenemedi.';

  @override
  String get onDevice => 'Cihazda';

  @override
  String get bluetoothSyncEnabled => 'Bluetooth senkronizasyonu etkinleştirildi';

  @override
  String get categorySafety => 'Güvenlik';

  @override
  String get unknownLocation => 'Bilinmeyen konum';

  @override
  String get newMemoryTitle => 'Yeni Anı';

  @override
  String get conversationCannotBeMerged => 'Bu konuşma birleştirilemez (kilitli veya zaten birleştiriliyor)';

  @override
  String get summaryGenerated => 'Özet oluşturuldu';

  @override
  String get createKey => 'Anahtar Oluştur';

  @override
  String get letOmiChooseAutomatically => 'Omi\'nin en iyi uygulamayı otomatik olarak seçmesine izin verin';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'Güncellemeyi tamamlamak için lütfen $deviceName cihazınızı yeniden başlatın.';
  }

  @override
  String get goals => 'Hedefler';

  @override
  String get wrappedAnErrorOccurred => 'Bir hata oluştu';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'Mikrofon izni kontrol edilemedi: $error';
  }

  @override
  String get connectLater => 'Sonra Bağlan';

  @override
  String get wrappedRememberedByOmi => 'Omi tarafından hatırlandı';

  @override
  String get fairUseStatusNormal => 'Kullanımınız normal sınırlar içinde.';

  @override
  String get includePersonalEventsDescription => 'Katılımcı olmayan kişisel etkinlikleri dahil et';

  @override
  String get week => 'Hafta';

  @override
  String get willLikelyCrash =>
      'Bu özelliği etkinleştirmek muhtemelen uygulamanın çökmesine veya donmasına neden olacaktır.';

  @override
  String get selectPrimaryLanguage => 'Ana dilinizi seçin';

  @override
  String get pilotFeaturesDescription => 'Bu özellikler testlerdir ve destek garanti edilmez.';

  @override
  String get askOmi => 'Omi\'ye Sor';

  @override
  String get ifYouCancel => 'İptal ederseniz:';

  @override
  String get audioOutput => 'Ses çıkışı';

  @override
  String get memoryReviewWrong => 'Yanlış';

  @override
  String get couldNotSchedulePlanChange => 'Plan değişikliği planlanamadı. Lütfen tekrar deneyin.';

  @override
  String speakerLabelEarlierMatches(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count önceki sohbette bulundu',
      one: '1 önceki sohbette bulundu',
    );
    return '$_temp0';
  }

  @override
  String get deviceOnboardingListening => 'Dinliyor…';

  @override
  String get speechProfileEnrollmentPrompt =>
      'Omi\'nin hangi sesin size ait olduğunu bilmesi için yaklaşık 5 saniye boyunca istediğiniz bir konuda konuşun.';

  @override
  String get mcpServerUrl => 'MCP Server URL';

  @override
  String get chatBlockMemory => 'Anı';

  @override
  String get noStarredConversations => 'Yıldızlı konuşma yok';

  @override
  String get syncStatusTooOld => 'Eşitlemek için çok eski — Omi bunu kabul edemez';

  @override
  String connectedAsUser(String userId) {
    return 'Kullanıcı olarak bağlandı: $userId';
  }

  @override
  String get phonePageTitle => 'Telefon';

  @override
  String get buildGraphButton => 'Grafik Oluştur';

  @override
  String get issuesCreatedInRepo => 'Sorunlar varsayılan deponuzda oluşturulacak';

  @override
  String get scopeUserFacts => 'Kullanıcı Bilgileri';

  @override
  String get unableToLoadPlans => 'Planlar yüklenemedi';

  @override
  String get deleteRecording => 'Kaydı Sil';

  @override
  String get appDeleteFailed => 'Uygulama silinemedi. Lütfen daha sonra tekrar deneyin.';

  @override
  String get addAppUpdatedSuccess => 'Uygulama başarıyla güncellendi 🚀';

  @override
  String get reviewCaughtUpTitle => 'Yanıtlanacak bir şey yok';

  @override
  String get copyConversationId => 'Konuşma kimliğini kopyala';

  @override
  String get helpImproveOmiBySharing =>
      'Anonimleştirilmiş analitik verileri paylaşarak Omi\'yi geliştirmeye yardımcı olun';

  @override
  String get dataEncryptedBanner =>
      'Verileriniz varsayılan olarak güçlü şifreleme ile korunur ve nasıl saklanıp kullanılacağını siz kontrol edersiniz.';

  @override
  String get redo => 'Yeniden kaydet';

  @override
  String get updateOmiGlassFirmware => 'OmiGlass Yazılımını Güncelle';

  @override
  String get deviceUnpairedMessage =>
      'Cihaz eşleştirmesi kaldırıldı. Eşleştirme kaldırmayı tamamlamak için Ayarlar > Bluetooth\'a gidin ve cihazı unutun.';

  @override
  String speakerLabelText(String part, String name) {
    String _temp0 = intl.Intl.selectLogic(
      part,
      {
        'likely': 'Muhtemel',
        'soundsLike': '$name gibi duyuluyor',
        'notPerson': '$name değil',
        'carried': 'Hâlâ $name. Son sohbetinizden aktarıldı.',
        'change': 'Değiştir',
        'alsoTitle': 'Bu da $name mi?',
        'alsoBody': 'Omi aynı sesi önceki sohbetlerde buldu.',
        'confirmed': 'Bu etiketi onayladınız',
        'other': 'İncele',
      },
    );
    return '$_temp0';
  }

  @override
  String get continueWithApple => 'Apple ile devam et';

  @override
  String get iUnderstand => 'Anlıyorum';

  @override
  String get memoryProvenanceAndroid => 'Android';

  @override
  String get saving => 'Kaydediliyor…';

  @override
  String get deviceOnboardingDoubleTapTitle => 'Çift Dokunmayı Özelleştir';

  @override
  String get allMemoriesPublicResult => 'Tüm anılar artık genel';

  @override
  String get chatAppsAddToContacts => 'Omi\'yi Rehber\'e ekle';

  @override
  String get wrappedDays => 'gün';

  @override
  String get invalidJsonError => 'Geçersiz JSON';

  @override
  String syncCardNeedsAttention(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count kayıt ilgi bekliyor',
      one: '1 kayıt ilgi bekliyor',
    );
    return '$_temp0';
  }

  @override
  String get wrappedSwipeUpToBegin => 'Başlamak için yukarı kaydır';

  @override
  String addedToService(String serviceName) {
    return '$serviceName platformuna eklendi';
  }

  @override
  String get advanced => 'Gelişmiş';

  @override
  String get autoCreateAndTagNewSpeakers => 'Yeni konuşmacıları otomatik olarak oluştur ve etiketle';

  @override
  String get appCapabilities => 'Uygulama Yetenekleri';

  @override
  String get onboardingMicrophoneDenied =>
      'Mikrofon izni reddedildi. Lütfen Sistem Tercihleri > Gizlilik ve Güvenlik > Mikrofon\'da izin verin.';

  @override
  String get pleaseEnterFolderName => 'Lütfen bir klasör adı girin';

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'Bluetooth izni kontrol edilemedi: $error';
  }

  @override
  String get invalidRecordingDetected => 'Geçersiz kayıt tespit edildi';

  @override
  String get appAnalytics => 'Uygulama Analitiği';

  @override
  String get captureRecordingsSheetTitle => 'Bu konuşmanın kayıtları';

  @override
  String deletedLimitlessConversations(int count) {
    return '$count Limitless konuşması silindi';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'Görsel seçilirken hata: $error';
  }

  @override
  String get unnamedSpeakerLabel => 'Konuşmacı';

  @override
  String get failedToCreateApp => 'Uygulama oluşturulamadı. Lütfen tekrar deneyin.';

  @override
  String get planUpdate => 'Plan Güncellemesi';

  @override
  String get timeout5Minutes => '5 dakika';

  @override
  String get deleteSample => 'Örneği sil';

  @override
  String get willNotSeeAgain => 'Tekrar göremeyeceksiniz.';

  @override
  String get thisMonth => 'Bu Ay';

  @override
  String get enterName => 'Ad girin';

  @override
  String get memoryThisDevice => 'Bu cihaz';

  @override
  String get verifiedNumbersDescription => 'Birini aradiginizda bu numarayi gorecekler';

  @override
  String get deviceOnboardingSingleTapHint => 'Bu tek dokunuştu — hızlıca iki kez dokunmayı deneyin!';

  @override
  String autoClosingInSeconds(int seconds) {
    return '$seconds saniye içinde otomatik kapanıyor';
  }

  @override
  String get chatAppsProPerkContext => 'Omi bağlamı her uygulamada hatırlar';

  @override
  String get errorProcessingConversation => 'Konuşma işlenirken hata oluştu. Lütfen daha sonra tekrar deneyin.';

  @override
  String get profileSettings => 'Profil Ayarları';

  @override
  String get statusUnprocessed => 'İşlenmedi';

  @override
  String get deleteConversationMessage => 'Bu işlem ilişkili anıları, görevleri ve ses dosyalarını da silecektir.';

  @override
  String get cancelSubscriptionQuestion => 'Aboneliği iptal et?';

  @override
  String get forUnlimitedFreeTranscription => 'sınırsız ücretsiz transkripsiyon için.';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$limit dakikadan $used kullanıldı';
  }

  @override
  String get categoryPersonalWellness => 'Kişisel Sağlık';

  @override
  String get automaticTranslation => 'Otomatik Çeviri';

  @override
  String get defaultAiAssistant => 'Varsayılan AI Asistanı';

  @override
  String get allDataErased => 'Anıların ve konuşmaların silinecek.';

  @override
  String entityDue(String date) {
    return 'Son tarih: $date';
  }

  @override
  String get feedbackChatWithUs => 'Detay paylaşmak ister misin? Bizimle yazış';

  @override
  String get speakerTagPromptSomeoneNew => 'Yeni biri';

  @override
  String get inProgress => 'Devam ediyor';

  @override
  String get raybanMetaCheckAgain => 'Tekrar Kontrol Et';

  @override
  String get fairUseStageNormal => 'Normal';

  @override
  String get pairingTitleLimitless => 'Limitless\'ı Eşleştirme Moduna Alın';

  @override
  String get usingNativeIosSpeech => 'Yerel iOS Konuşma Tanıma Kullanılıyor';

  @override
  String get actionItemDeletedSuccessfully => 'Görev başarıyla silindi';

  @override
  String get failedToSetLanguage => 'Dil ayarlanamadı';

  @override
  String get appHomeUrl => 'Uygulama Ana Sayfa URL\'si';

  @override
  String get appNameLabel => 'Uygulama Adı';

  @override
  String get localStorageDisabled => 'Yerel depolama devre dışı bırakıldı';

  @override
  String get appReEnable => 'Yeniden etkinleştir';

  @override
  String get migrationFailed => 'Geçiş Başarısız';

  @override
  String get markComplete => 'Tamamlandı olarak işaretle';

  @override
  String get lastUsedLabel => 'Son Kullanılan';

  @override
  String get chatCleared => 'Sohbet temizlendi';

  @override
  String get revokeApiKeyWarning => 'Bu anahtarı kullanan uygulamalar API erişimini kaybeder. Bu işlem geri alınamaz.';

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return 'Ekran yakalama izni kontrol edilemedi: $error';
  }

  @override
  String get troubleshootingSteps =>
      'Sorun giderme:\n\n1. Omi\'nin saatinizde yüklü olduğundan emin olun\n2. Saatinizdeki Omi uygulamasını açın\n3. İzin açılır penceresini arayın\n4. İstendiğinde \"İzin Ver\"e dokunun\n5. Saatinizdeki uygulama kapanacak - yeniden açın\n6. Geri gelin ve iPhone\'unuzda \"Devam Et\"e dokunun';

  @override
  String get location => 'Konum';

  @override
  String get chatAppsWhatsAppMeantime => 'Telegram ve iMessage bugün çalışıyor, aynı anılar ve görevlerle.';

  @override
  String get sliderOff => 'Kapalı';

  @override
  String get checkingFirmwareVersion => 'Aygıt yazılımı sürümü kontrol ediliyor…';

  @override
  String get reviewUnknownSpeaker => 'Bilinmeyen konuşmacı';

  @override
  String get professionSales => 'Satış';

  @override
  String get noRssiDataYet => 'Henüz RSSI verisi yok';

  @override
  String get emptyOldMessage => '✅ Eski görev yok';

  @override
  String deleteSampleConfirmation(String name) {
    return '$name adlı kişinin ses örneği kaldırılır. Bu işlem geri alınamaz.';
  }

  @override
  String get saveUrlButton => 'URL\'yi Kaydet';

  @override
  String get onboardingNotificationDeniedSystemPrefs =>
      'Bildirim izni reddedildi. Lütfen Sistem Tercihleri\'nde izin verin.';

  @override
  String get languageForTranscription => 'Omi bu dili transkripsiyon, özetler ve anılar için kullanır.';

  @override
  String get updatedLabel => 'GÜNCELLENDİ';

  @override
  String get content => 'İçerik';

  @override
  String get phoneCallButton => 'Ara';

  @override
  String get exportStartedMayTakeFewSeconds => 'Dışa aktarma başladı. Bu birkaç saniye sürebilir…';

  @override
  String dreamReportPrivacyHeld(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count bildirim gizlilik nedeniyle tutuldu',
      one: '1 bildirim gizlilik nedeniyle tutuldu',
    );
    return '$_temp0';
  }

  @override
  String firmwareBatteryTooLow(int level) {
    return 'Pil %$level seviyesinde. Güncellemeden önce cihazınızı en az %15\'e kadar şarj edin.';
  }

  @override
  String get appearance => 'Görünüm';

  @override
  String noTasksOnDate(Object date) {
    return '$date için görev yok';
  }

  @override
  String get deleteFlowFeedbackHint => 'İsteğe bağlı — düşünceleriniz daha iyi bir ürün oluşturmamıza yardımcı olur.';

  @override
  String get bluetooth => 'Bluetooth';

  @override
  String get cancelUpdate => 'Güncellemeyi İptal Et';

  @override
  String get syncStatusConversationCreated => 'Konuşma oluşturuldu';

  @override
  String get reconnecting => 'Yeniden bağlanıyor…';

  @override
  String get tasksToday => 'Bugün';

  @override
  String taskCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count görev',
      one: '1 görev',
    );
    return '$_temp0';
  }

  @override
  String get noUpcomingMeetings => 'Yaklaşan toplantı yok';

  @override
  String get invalidRecordingMultipleSpeakers => 'Geçersiz kayıt algılandı';

  @override
  String get startupFailedTitle => 'Omi başlatılamadı';

  @override
  String contactsSelectedCount(int count) {
    return '$count seçildi';
  }

  @override
  String get skipForward10Seconds => '10 saniye ileri';

  @override
  String get noItems => 'Öğe yok';

  @override
  String get timeout30Minutes => '30 dakika';

  @override
  String get signInSuccess => 'Giriş başarılı!';

  @override
  String get syncStatusDownloadingFromDevice => 'Cihazınızdan indiriliyor';

  @override
  String get makePrivate => 'Özel yap';

  @override
  String get update => 'Güncelle';

  @override
  String get aiGenCreatingAppIcon => 'Uygulama simgesi oluşturuluyor…';

  @override
  String get wrappedIntenseDay => 'Yoğun';

  @override
  String get raybanMetaSkipForNow => 'Şimdilik Atla';

  @override
  String diagnosticsReconnectedIn(String duration) {
    return '$duration içinde yeniden bağlandı';
  }

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'Sınırsız Planınızı $title planına değiştiriyorsunuz.';
  }

  @override
  String get appsAskWith => 'Omi\'ye şununla sor';

  @override
  String get noMemoriesFound => 'Anı bulunamadı';

  @override
  String get noMemoriesYet => 'Henüz anı yok';

  @override
  String get captureRecordingSeparateFailed => 'Ayrılamadı. Tekrar deneyin.';

  @override
  String get pinAsBaseline => 'Temel olarak sabitle';

  @override
  String get voiceRecognitionSettings => 'Ses Tanıma';

  @override
  String get chatAppsComingLater => 'Daha sonra gelecek';

  @override
  String get sliderMax => 'Maks.';

  @override
  String get deleteWhileProcessingTitle => 'Hâlâ işleniyor';

  @override
  String get devModeSettingsSaved => 'Ayarlar kaydedildi!';

  @override
  String get fairUseToday => 'Bugün';

  @override
  String get exportDataDesc => 'Konuşmaları JSON dosyasına aktar';

  @override
  String get whatsYourName => 'Adın ne?';

  @override
  String get onDeviceSlower => 'Bu cihazda cihaz üzerinde transkripsiyon daha yavaş olabilir.';

  @override
  String get categoryProductivityLifestyle => 'Verimlilik ve Yaşam Tarzı';

  @override
  String get addToYourTaskList => 'Görev listenize eklensin mi?';

  @override
  String get meetingScreenshotFallbackCaption => 'Bu toplantıdan ekran görüntüsü';

  @override
  String get effectCountsALittle => 'Biraz yardımcı olur';

  @override
  String get pairingTitleFriendPendant => 'Friend Pendant\'ı Eşleştirme Moduna Alın';

  @override
  String get peopleStatsIncomplete => 'Sayımlar eksik olabilir.';

  @override
  String get tapToAddGoal => 'Hedef eklemek için dokunun';

  @override
  String get payment => 'Ödeme';

  @override
  String get omiDebugLog => 'Omi hata ayıklama günlüğü';

  @override
  String get showMeetingsMenuBar => 'Yaklaşan toplantıları menü çubuğunda göster';

  @override
  String get mostInstalls => 'En çok yükleme';

  @override
  String chatUsageMessages(String used, String limit) {
    return 'Sohbet: $used / $limit mesaj bu ay';
  }

  @override
  String get chat => 'Sohbet';

  @override
  String get areYouThere => 'Orada mısınız?';

  @override
  String get highestRating => 'En yüksek puan';

  @override
  String get pleaseSpecify => 'Lütfen belirtin';

  @override
  String get staging => 'Test ortamı';

  @override
  String get cancelReasonBatteryDrain => 'Pil tükenme endişeleri';

  @override
  String get apiKeys => 'API Anahtarları';

  @override
  String conversationsCreated(int count) {
    return '$count konuşma oluşturuldu';
  }

  @override
  String get trainingDataProgram => 'Eğitim Verisi Programı';

  @override
  String get customBackendUrlTitle => 'Özel Sunucu URL';

  @override
  String get omiSyncsAudioFiles => 'Omi daha sonra ses dosyalarını sunucu ile senkronize eder';

  @override
  String get reviewAnswerMe => 'Ben';

  @override
  String get debugDiagnostics => 'Hata Ayıklama ve Teşhis';

  @override
  String get confidenceReasonNotHeard => 'henüz duyulmadı';

  @override
  String get doubleTapAction => 'Çift Dokunma İşlemi';

  @override
  String get showTasksOnHomepage => 'Ana sayfada görevleri göster';

  @override
  String failedToStartUpdate(String error) {
    return 'Güncelleme başlatılamadı: $error';
  }

  @override
  String get feedbackReasonSummaryWrongContext => 'Yanlış bağlam';

  @override
  String get pleaseProvideValidDescription => 'Lütfen geçerli bir açıklama sağlayın';

  @override
  String get appRejectedNotice =>
      'Uygulamanız reddedildi. Lütfen uygulama ayrıntılarını güncelleyin ve inceleme için yeniden gönderin.';

  @override
  String get deleteOnDeviceModel => 'Modeli Sil';

  @override
  String get languageSettingsHelperText =>
      'Uygulama Dili menüleri ve düğmeleri değiştirir. Birincil Dil, kayıtlarınızın nasıl transkribe edildiğini etkiler.';

  @override
  String get deleteConversationsMessage => 'Bu işlem onların anılarını, görevlerini ve ses dosyalarını da siler.';

  @override
  String get usageBestMonth => 'Best month';

  @override
  String get creating => 'Oluşturuluyor…';

  @override
  String get microphoneAccessDescription =>
      'Omi, konuşmalarınızı kaydetmek ve transkript sağlamak için mikrofon erişimine ihtiyaç duyar.';

  @override
  String get cancelReasonNotUsing => 'Yeterince kullanmıyorum';

  @override
  String get wrappedWeveAllBeenThere => 'Hepimiz orada bulunduk!';

  @override
  String get chatAppsProblemRateLimited => 'Çok fazla deneme. Bir dakika bekleyip tekrar dene.';

  @override
  String get selectOption => 'Seç';

  @override
  String get languageBenefits => 'Omi bu dili transkripsiyon, özetler ve anılar için kullanır.';

  @override
  String get triggerConversationIntegration => 'Konuşma oluşturma entegrasyonunu tetikle';

  @override
  String get integrationSetupRequired => 'Bu bir entegrasyon uygulamasıysa, kurulumun tamamlandığından emin olun.';

  @override
  String get clickPlayToResumeOrStop => 'Devam etmek için oynat\'a veya bitirmek için durdur\'a tıklayın';

  @override
  String disconnectedFrom(String appName) {
    return '$appName bağlantısı kesildi';
  }

  @override
  String get subscribe => 'Abone ol';

  @override
  String get permissionsChangeAnytime => 'Bunları istediğiniz zaman Ayarlar > İzinler bölümünden değiştirebilirsiniz';

  @override
  String get enableRemindersAccess =>
      'Apple Hatırlatıcılar\'ı kullanmak için lütfen Ayarlar\'da Hatırlatıcılar erişimini etkinleştirin';

  @override
  String get selectProviderTemplate => 'Bir sağlayıcı şablonu seçin…';

  @override
  String get initialisingSystemAudio => 'Sistem Sesi Başlatılıyor';

  @override
  String get excellent => 'Mükemmel';

  @override
  String get chatBlockGoal => 'Hedef';

  @override
  String get deleteFolder => 'Klasörü sil';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'Anahtar oluşturulamadı: $error';
  }

  @override
  String get whisperModelSizeSmall => 'Küçük';

  @override
  String get pleaseCopyKeyNow => 'Lütfen şimdi kopyalayın ve güvenli bir yere yazın. ';

  @override
  String get unresolvedSpeakersNotice => 'Bu konuşmadaki kayıtlar arasında konuşmacı etiketleri eşleşmeyebilir.';

  @override
  String get omisMemoryCleared => 'Omi\'nin senin hakkındaki belleği temizlendi';

  @override
  String get manageApp => 'Uygulamayı Yönet';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return 'Ekran yakalama izin durumu: $status. Lütfen Sistem Tercihleri\'ni kontrol edin.';
  }

  @override
  String get edit => 'Düzenle';

  @override
  String get redownload => 'Yeniden İndir';

  @override
  String get chatBlockConversation => 'Konuşma';

  @override
  String get loadingApps => 'Uygulamalar yükleniyor…';

  @override
  String get chatPromptPlaceholder =>
      'Harika bir uygulamasınız, işiniz kullanıcı sorgularına yanıt vermek ve onları iyi hissettirmek…';

  @override
  String get stripeConnectedAccountAgreement => 'Stripe Bağlı Hesap Sözleşmesi';

  @override
  String get autoSync => 'Otomatik eşitleme';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'Bilgi Grafiği başarıyla silindi';

  @override
  String get optInAndOptOutOptions => 'Katılma ve Ayrılma Seçenekleri';

  @override
  String get permissionReadMemories => 'Anıları Oku';

  @override
  String get noSpacesInWorkspace => 'Bu çalışma alanında alan bulunamadı';

  @override
  String get reviewYesMerge => 'Evet, birleştir';

  @override
  String get voiceMode => 'Ses Modu';

  @override
  String get fairUseStageThrottle => 'Kısıtlı';

  @override
  String get deleteChatQuestion => 'Bu sohbet silinsin mi?';

  @override
  String get failedToGetCallToken => 'Token alinamadi. Once numaranizi dogrulayin.';

  @override
  String get selectTime => 'Saat Seç';

  @override
  String get sdCardProcessing => 'SD Kart İşleniyor';

  @override
  String errorConnectingRayBanMeta(String error) {
    return 'Ray-Ban Meta\'ya bağlanırken hata: $error';
  }

  @override
  String get couldNotLoadImportHistory => 'İçe aktarma geçmişi yüklenemedi';

  @override
  String get noApiKeysFound => 'API anahtarı bulunamadı. Başlamak için bir tane oluşturun.';

  @override
  String get appDisabledTitle => 'Bu uygulama devre dışı bırakıldı ve yüklenemiyor.';

  @override
  String get syncStatusBackedUp => 'Yedeklendi';

  @override
  String get speakerTagPromptThatsMeAction => 'Bu Benim';

  @override
  String timeCompactHoursAndMins(int hours, int mins) {
    return '${hours}sa ${mins}dk';
  }

  @override
  String get chatPrompt => 'Sohbet Yönlendirmesi';

  @override
  String get voicePreviewSample => 'Merhaba, ben Omi. Bu benim sesim.';

  @override
  String get saved => 'Kaydedildi';

  @override
  String get grantPermissionButton => 'İzin Ver';

  @override
  String get subscription => 'Abonelik';

  @override
  String get capabilityFeatured => 'Öne Çıkanlar';

  @override
  String get pdfConversationExport => 'Sohbet Dışa Aktar';

  @override
  String get unknown => 'Bilinmeyen';

  @override
  String get yourMeetings => 'Toplantılarınız';

  @override
  String get uploadingVoiceProfile => 'Ses profiliniz yükleniyor….';

  @override
  String get apiUrl => 'API URL\'si';

  @override
  String get reportMessage => 'Mesajı Bildir';

  @override
  String get passwordLabel => 'Şifre';

  @override
  String get permanentlyRemoveAllMemories => 'Omi\'den tüm anıları kalıcı olarak kaldır';

  @override
  String get transcriptionSlowerLessAccurate => 'Transkripsiyon önemli ölçüde daha yavaş ve daha az doğru olacaktır.';

  @override
  String get filterManual => 'Manuel';

  @override
  String get keepMyPlan => 'Planımı Koru';

  @override
  String get setupQuestionAge => '3. Yaş aralığınız nedir?';

  @override
  String get addAppSelectTriggerEvent => 'Uygulamanız için bir tetikleyici olay seçin';

  @override
  String get defaultWorkspace => 'Varsayılan Çalışma Alanı';

  @override
  String get errorUpdatingAppStatus => 'Uygulama durumu güncellenirken bir hata oluştu.';

  @override
  String get invalidJsonConfig => 'Geçersiz JSON yapılandırması';

  @override
  String get detailedDiagnosticMessages => 'Ayrıntılı tanılama mesajları';

  @override
  String get mergingInBackground => 'Arka planda birleştiriliyor. Bu biraz zaman alabilir.';

  @override
  String get setDefaultApp => 'Varsayılan Uygulamayı Ayarla';

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Omi\'nin $appName hesabınızda görev oluşturmasına yetki vermeniz gerekecek. Bu, kimlik doğrulama için tarayıcınızı açacaktır.';
  }

  @override
  String get cleanUpEllipsis => 'Temizle…';

  @override
  String get addTask => 'Görev ekle';

  @override
  String get getCreative => 'Yaratıcı Ol';

  @override
  String get captureRecordingOpenFailed => 'Bu kayıt açılamadı.';

  @override
  String get emptyTodoMessage => '🎉 Her şey güncel!\nBekleyen görev yok';

  @override
  String get onboardingSetupTitle => 'Omi\'niz ayarlanıyor';

  @override
  String get sharePeriodAllTime => 'Şimdiye kadar, Omi:';

  @override
  String get translationNotice => 'Çeviri Bildirimi';

  @override
  String captureRecordingError(String error) {
    return 'Kayıt sırasında bir hata oluştu: $error';
  }

  @override
  String get downloadAudio => 'Ses İndir';

  @override
  String get identifySpeaker => 'Konuşmacıyı belirle';

  @override
  String get viewTranscript => 'Transkripti Görüntüle';

  @override
  String get makeAllMemoriesPublic => 'Tüm Anıları Herkese Açık Yap';

  @override
  String get xTwitter => 'X (Twitter)';

  @override
  String get frequencyOff => 'Kapalı';

  @override
  String get apiEnvironment => 'API Ortamı';

  @override
  String get processingTakingLonger => 'Hâlâ devam ediyor — bu her zamankinden daha uzun sürüyor.';

  @override
  String get firmwareUpdateFailedTitle => 'Güncelleme Başarısız';

  @override
  String get unresolvedQuestions => 'Çözülmemiş Sorular';

  @override
  String get chatAppsMessage => 'Mesaj';

  @override
  String get dreamReportManual => 'Manuel';

  @override
  String get enterSttHttpEndpoint => 'STT HTTP uç noktanızı girin';

  @override
  String get beforeUpdateMakeSure => 'Güncellemeden önce emin olun:';

  @override
  String get transcriptionReconnecting => 'Transkripsiyon yeniden bağlanıyor…';

  @override
  String get deviceName => 'Cihaz Adı';

  @override
  String neoSubtitle(int count) {
    return 'Ayda $count soru';
  }

  @override
  String chatUsageProgress(String used, String limit) {
    return '$used / $limit kullanıldı';
  }

  @override
  String get noChangesInReview => 'Güncellenecek yorum değişikliği yok.';

  @override
  String get allMemories => 'Tüm anılar';

  @override
  String get needMicrophonePermission =>
      'Mikrofon iznine ihtiyacımız var.\n\n1. \"İzin Ver\"e dokunun\n2. iPhone\'unuzda izin verin\n3. Saat uygulaması kapanacak\n4. Yeniden açın ve \"Devam Et\"e dokunun';

  @override
  String get keepSpeakingUntil100 => '%100\'e ulaşana kadar konuşmaya devam edin.';

  @override
  String get singleLanguageModeInfo => 'Tek Dil Modu etkin. Daha yüksek doğruluk için çeviri devre dışı.';

  @override
  String get thisCannotBeUndone => 'Bu işlem geri alınamaz.';

  @override
  String get setupSkipHelp => 'Atla, yardım etmek istemiyorum :C';

  @override
  String get speakerTagPromptNoAction => 'Hayır…';

  @override
  String labelCopied(String label) {
    return '$label kopyalandı';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'Ses cihazı değiştirilirken hata: $error';
  }

  @override
  String get remembering => 'Hatırlama';

  @override
  String get externalAppAccessDescription =>
      'Aşağıdaki yüklü uygulamalar harici entegrasyonlara sahiptir ve sohbetler ve anılar gibi verilerinize erişebilir.';

  @override
  String get preferences => 'Tercihler';

  @override
  String get wrappedFunDay => 'Eğlenceli';

  @override
  String get effectNeeded => 'Onaylandı seviyesi için gerekli';

  @override
  String get importantConversationBody => 'Az önce önemli bir konuşma yaptınız. Özeti paylaşmak için dokunun.';

  @override
  String whyConfidenceMenu(String level) {
    return 'Neden $level?';
  }

  @override
  String get cmdRequired => '⌘ gerekli';

  @override
  String get completed => 'Tamamlandı';

  @override
  String get deviceOnboardingVoiceReplyStatusAlwaysSpeaker => 'Telefonun hoparlöründen yüksek sesle çalar.';

  @override
  String get effectCountsAgainst => 'Zarar verir';

  @override
  String get recaps => 'Özetler';

  @override
  String get shareConversationQuestion => 'Konuşma paylaşılsın mı?';

  @override
  String get actionItemsCopiedToClipboard => 'Görevler panoya kopyalandı';

  @override
  String get appleHealthManageNote =>
      'Omi, Apple Health\'e Apple\'ın HealthKit çerçevesi üzerinden erişir. Erişimi istediğiniz zaman iOS Ayarlar\'dan iptal edebilirsiniz.';

  @override
  String addingToService(String serviceName) {
    return '$serviceName platformuna ekleniyor…';
  }

  @override
  String get needHelpGettingStarted => 'Başlamak için yardıma mı ihtiyacınız var?';

  @override
  String get thanksForAuthorizing => 'İzin verdiğiniz için teşekkürler!';

  @override
  String get assistantVoiceSettingsTitle => 'Ses';

  @override
  String get cloudStorageDisabled => 'Bulut depolama devre dışı bırakıldı';

  @override
  String get reviewPlayClip => 'Klibi oynat';

  @override
  String get storeAudioOnCloud => 'Sesi Bulutta Depola';

  @override
  String get syncStatusBackingUp => 'Senkronize ediliyor…';

  @override
  String get peopleFilterPinned => 'Sabitlenenler';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName varsayılan özet uygulaması olarak ayarlandı';
  }

  @override
  String get githubRepositoryUrlRequired => 'GitHub depo URL\'si gerekli';

  @override
  String get microphoneAccess => 'Mikrofon Erişimi';

  @override
  String get cancelSubscriptionButton => 'Aboneliği İptal Et';

  @override
  String get signal => 'Sinyal';

  @override
  String get failedToConnectAsanaRetry => 'Asana\'ya bağlanılamadı. Lütfen tekrar deneyin.';

  @override
  String get keyCreatedMessage => 'Yeni anahtarınız oluşturuldu. Lütfen şimdi kopyalayın. Tekrar göremeyeceksiniz.';

  @override
  String autoRemoveSyncedCopiesDays(int days) {
    return 'Senkronize kopyalar $days gün sonra silinir';
  }

  @override
  String get wrappedMostCringeMoment => 'En Utanç Verici';

  @override
  String get activity => 'Etkinlik';

  @override
  String get calendarSettings => 'Takvim ayarları';

  @override
  String get additionalFeedbackOptional => 'Ek geri bildirim (isteğe bağlı)';

  @override
  String get phoneAllow => 'Izin ver';

  @override
  String get noDeviceConnectedUseMic => 'Bağlı cihaz yok. Telefon mikrofonu kullanılacak.';

  @override
  String get stripeOnboardingInstructions =>
      'Lütfen tarayıcınızda Stripe kayıt sürecini tamamlayın. Bu sayfa tamamlandıktan sonra otomatik olarak güncellenecektir.';

  @override
  String availableSpaceWithValue(String space) {
    return 'Kullanılabilir Alan: $space';
  }

  @override
  String get conversationDetails => 'Sohbet Detayları';

  @override
  String get wrappedYouHadFunnyMoments => 'Bu yıl komik anların oldu!';

  @override
  String get actionReadConversations => 'Konuşmaları oku';

  @override
  String speakerTagPromptIsThisPerson(String name) {
    return 'Bu $name mi?';
  }

  @override
  String get openSettings => 'Ayarları Aç';

  @override
  String get alwaysAvailable => 'her zaman mevcut.';

  @override
  String get rating1PlusStars => '1+ yıldız';

  @override
  String get pauseResume => 'Duraklat/Devam Et';

  @override
  String get conversationDeleted => 'Sohbet silindi';

  @override
  String get memoryReviewRight => 'Doğru';

  @override
  String get deleteGoal => 'Hedefi Sil';

  @override
  String get youtube => 'YouTube';

  @override
  String get untitledConversation => 'Başlıksız Sohbet';

  @override
  String get yourOmiInsights => 'Omi İçgörüleriniz';

  @override
  String get compareTranscripts => 'Transkriptleri karşılaştır';

  @override
  String get pause => 'Duraklat';

  @override
  String get successfullyConnectedGoogle => 'Google\'a başarıyla bağlanıldı!';

  @override
  String planRenewsOn(String date) {
    return 'Planınız $date tarihinde yenilenir.';
  }

  @override
  String chatAppsOpenApp(String app) {
    return '$app uygulamasını aç';
  }

  @override
  String get dailySummaryDescription => 'Günün konuşmalarının kişiselleştirilmiş özetini bildirim olarak alın.';

  @override
  String conversationPhotosCount(int count) {
    return '$count fotoğraf';
  }

  @override
  String get errorLoadingAudio => 'Ses yüklenirken hata oluştu';

  @override
  String get couldNotAccessFile => 'Seçilen dosyaya erişilemedi';

  @override
  String deleteGraphFailed(String error) {
    return 'Grafik silinemedi: $error';
  }

  @override
  String get reviewOpenDetailsHint => 'Ayrıntıları açar';

  @override
  String get conversationTimeoutDesc =>
      'Sessizlikte ne kadar bekledikten sonra konuşmanın otomatik olarak sonlandırılacağını seçin:';

  @override
  String get transcriptionJsonPlaceholder => 'JSON yapılandırmanızı buraya yapıştırın…';

  @override
  String get loadingCapabilities => 'Yetenekler yükleniyor…';

  @override
  String get activeStatus => 'Aktif';

  @override
  String get noDailyRecapsYet => 'Henüz günlük özet yok';

  @override
  String get wouldLikePermission => 'Ses kayıtlarınızı kaydetmek için izninizi istiyoruz. İşte nedeni:';

  @override
  String get chatBlockRecommendedNextSteps => 'Önerilen sonraki adımlar';

  @override
  String get tryAdjustingSearchTerms => 'Arama terimlerinizi ayarlamayı deneyin';

  @override
  String get connectOmiWithAI => 'Omi\'yi yapay zeka asistanlarıyla bağlayın';

  @override
  String get whenToReceiveDailySummary => 'Günlük özetinizi ne zaman alacağınız';

  @override
  String syncCardReadyCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count kayıt eşitlemeye hazır',
      one: '1 kayıt eşitlemeye hazır',
    );
    return '$_temp0';
  }

  @override
  String get yourApiKey => 'API ANAHTARINIZ';

  @override
  String failedToLoadRepos(String error) {
    return 'Depolar yüklenemedi: $error';
  }

  @override
  String get syncingMessages => 'Mesajlar sunucuyla senkronize ediliyor…';

  @override
  String get pleaseSelectARating => 'Lütfen bir puan seçin';

  @override
  String get suggestedTemplates => 'Önerilen Şablonlar';

  @override
  String get updateAppQuestion => 'Uygulama güncellensin mi?';

  @override
  String get frequencyDescOff => 'Proaktif bildirim yok';

  @override
  String get triggerAudioBytes => 'Ses Baytları';

  @override
  String get confirmClearChat => 'Bu sohbet temizlensin mi? Bu işlem geri alınamaz.';

  @override
  String get dataPrivacy => 'Veri Gizliliği';

  @override
  String get audioFromOmiWillAppearHere => 'Omi cihazınızdan gelen ses burada görünecek';

  @override
  String get durationLabel => 'Süre';

  @override
  String get deviceOnboardingAllSetTitle => 'Her Şey Hazır';

  @override
  String msgSelectImagesError(String error) {
    return 'Resim seçerken hata: $error';
  }

  @override
  String evidenceCardPicks(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count öneride seçildi',
      one: '1 öneride seçildi',
    );
    return '$_temp0';
  }

  @override
  String get connectionLostDesc => 'Bağlantı kesildi. Lütfen internet bağlantınızı kontrol edin ve tekrar deneyin.';

  @override
  String get defaultLabel => 'Varsayılan';

  @override
  String get raybanMetaAllowCamera => 'Gözlükte Kameraya İzin Ver';

  @override
  String get addAppSelectCoreCapability => 'Uygulamanız için bir temel yetenek daha seçin';

  @override
  String get noManualMemories => 'Henüz manuel anı yok';

  @override
  String get deliveryTime => 'Gönderim Saati';

  @override
  String get defaultProjectOptional => 'Varsayılan Proje (İsteğe Bağlı)';

  @override
  String get devModeInvalidAudioBytesWebhookUrl => 'Geçersiz ses baytları webhook URL\'si';

  @override
  String get ignoredVoicesTitle => 'Yok Sayılan Sesler';

  @override
  String get refreshManifest => 'Manifesti yenile';

  @override
  String get diagnosticsRightNow => 'Şu Anda';

  @override
  String get reviewDue => 'Son tarih';

  @override
  String get unmute => 'Sesi aç';

  @override
  String get recordingsDeleted => 'Kayıtlar silindi.';

  @override
  String get failedToDeleteFolder => 'Klasör silinemedi';

  @override
  String get reviewAnswerOther => 'Diğer';

  @override
  String get exportedConversations => 'Omi\'den Dışa Aktarılan Konuşmalar';

  @override
  String get privacyPolicy => 'Gizlilik Politikası';

  @override
  String get editReply => 'Yanıtı Düzenle';

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription ve $triggerDescription.';
  }

  @override
  String errorSaving(String error) {
    return 'Kaydetme hatası: $error';
  }

  @override
  String get diagnosticsConnectedFor => 'Bağlantı süresi';

  @override
  String get callStateConnecting => 'Baglaniyor…';

  @override
  String get conversationUrlNotShared => 'Konuşma URL\'si paylaşılamadı.';

  @override
  String get tooShortDesc => 'Yeterli konuşma algılanamadı. Lütfen daha fazla konuşun ve tekrar deneyin.';

  @override
  String get failedToShareRecap => 'Özet paylaşılamadı';

  @override
  String get billingMonthly => 'Aylık';

  @override
  String get developingLogic => 'Mantık geliştiriliyor';

  @override
  String get phoneContinue => 'Devam';

  @override
  String get successfullyConnectedGitHub => 'GitHub\'a başarıyla bağlanıldı!';

  @override
  String get failedToSubmitReview => 'Yorum gönderilemedi. Lütfen tekrar deneyin.';

  @override
  String get anyoneCanDiscover => 'Herkes uygulamanızı keşfedebilir';

  @override
  String get v2Undetected => 'V2 algılanamadı';

  @override
  String get usageIrlEvents => 'Gerçek Hayat Etkinliklerinde';

  @override
  String get conversationPromptHint =>
      'örn., Verilen konuşmadan görevleri, alınan kararları ve önemli çıkarımları çıkarın.';

  @override
  String get openProviderDocs => 'Belgeleri Aç';

  @override
  String get showMeetingsInMenuBar => 'Menü Çubuğunda Toplantıları Göster';

  @override
  String get viewPlansAndUsage => 'Planları ve Kullanımı Görüntüle';

  @override
  String get buildSubmitCustomOmiApp => 'Özel Omi uygulamanızı oluşturun ve gönderin';

  @override
  String get failedToRefreshGoogleStatus => 'Google bağlantı durumu yenilenemedi.';

  @override
  String get feedbackSubtitleTooExpensive => 'Geri bildiriminiz doğru dengeyi bulmamıza yardımcı olur.';

  @override
  String get startUsingOmi => 'Omi\'yi Kullanmaya Başla';

  @override
  String get dreamReportLearnedWords => 'Öğrendiği kelimeler';

  @override
  String get actionItemCreated => 'Görev oluşturuldu';

  @override
  String get exportAllConversationsToJson => 'Tüm konuşmalarınızı bir JSON dosyasına aktarın.';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'Lütfen internet bağlantınızı kontrol edin ve tekrar deneyin';

  @override
  String get callStateEnded => 'Arama sona erdi';

  @override
  String get phoneNumberHint => 'Telefon numarasi';

  @override
  String get tasksGroupByProject => 'Projeye göre grupla';

  @override
  String get phoneCallsUnlimitedOnly => 'Omi ile Telefon Aramaları';

  @override
  String get frequencyDescMinimal => 'Yalnızca acil şeyler, günde yaklaşık 1–3';

  @override
  String get changeYourName => 'Adınızı değiştirin';

  @override
  String get editYourReply => 'Yanıtını Düzenle';

  @override
  String get publicMemories => 'Genel anılar';

  @override
  String get monthDec => 'Ara';

  @override
  String get reviewNewPersonName => 'Adı';

  @override
  String get googleCalendarConnectPrompt =>
      'Konuşmaları takvim etkinliklerine bağlamak için Google Takvim hesabınızı bağlayın.';

  @override
  String get realtimeAudioBytes => 'Gerçek zamanlı ses baytları';

  @override
  String get trackYourGoalsOnHomepage => 'Ana sayfada kişisel hedeflerinizi takip edin';

  @override
  String get chatAddAttachment => 'Ek ekle';

  @override
  String get beta => 'BETA';

  @override
  String get createMemory => 'Hafıza oluştur';

  @override
  String get permissionsRequiredDescription =>
      'Omi düzgün çalışmak için birkaç izne ihtiyaç duyar. Devam etmek için lütfen bunları verin.';

  @override
  String get dataCollectionMessage =>
      'Devam ederek, konuşmalarınız, kayıtlarınız ve kişisel bilgileriniz AI destekli içgörüler sağlamak ve tüm uygulama özelliklerini etkinleştirmek için sunucularımızda güvenli bir şekilde saklanacaktır.';

  @override
  String get batteryLevel => 'Pil Seviyesi';

  @override
  String get searchCountries => 'Ülke ara...';

  @override
  String get confidenceSheetTitle => 'Güven';

  @override
  String get deviceModelLabel => 'Cihaz Modeli';

  @override
  String get noStableFirmwareFound => 'Cihazınız için kararlı bir yazılım sürümü bulunamadı.';

  @override
  String get noResultsFound => 'Sonuç bulunamadı';

  @override
  String get wrappedMins => 'dk';

  @override
  String get chatAppsTelegramSubtitle => 'İki dokunuşla kur';

  @override
  String get categoryConversationAnalysis => 'Konuşma Analizi';

  @override
  String get target => 'Hedef';

  @override
  String get apiKeyRequired => 'API anahtarı gereklidir';

  @override
  String otaUpdatedMessage(String deviceName) {
    return '$deviceName güncellendi ve kendiliğinden yeniden başlayacak.';
  }

  @override
  String get reconnections => 'Yeniden Bağlantılar';

  @override
  String errorCheckingConnection(String error) {
    return 'Bağlantı kontrol hatası: $error';
  }

  @override
  String get usageMonth => 'Bu Ay';

  @override
  String get additionalSpeechSampleRemoved => 'Ek ses örneği kaldırıldı';

  @override
  String get speakerTagPromptExcerptSaved => 'Bu bölüm için yanıt kaydedildi.';

  @override
  String get omisStorage => 'Omi\'nin Depolaması';

  @override
  String get recordingAndTranscription => 'Kayıt ve Transkripsiyon';

  @override
  String get categoryCommunication => 'İletişim';

  @override
  String get wrappedYouDidIt => 'Başardınız! 🎉';

  @override
  String get failedToDeleteItems => 'Öğeler silinemedi';

  @override
  String speakerLabelLinesLabeled(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count satır etiketlendi',
      one: '1 satır etiketlendi',
    );
    return '$_temp0';
  }

  @override
  String get generatingLink => 'Bağlantı oluşturuluyor…';

  @override
  String get clickHereForAppBuildingGuides => 'Uygulama oluşturma kılavuzları ve belgeleri için buraya tıklayın';

  @override
  String get authUrl => 'Kimlik Doğrulama URL\'si';

  @override
  String get addAppCapabilityConflictWithPersona => 'Diğer yetenekler Persona ile birlikte seçilemez';

  @override
  String get deviceOnboardingVoiceReplyGenericHeadphones => 'Kulaklıklar';

  @override
  String get clearAll => 'Tümünü temizle';

  @override
  String get noKnowledgeGraphYet => 'Henüz bilgi grafiği yok';

  @override
  String get messageReportedSuccessfully => '✅ Mesaj başarıyla bildirildi';

  @override
  String get paymentFailedToSetDefault => 'Varsayılan ödeme yöntemi ayarlanamadı. Daha sonra tekrar deneyin.';

  @override
  String get memoryReviewUpdated => 'Güncellendi.';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'Planınız $date tarihinde iptal edilecek.';
  }

  @override
  String get welcomeToOmi => 'Omi\'ye hoş geldiniz';

  @override
  String get phoneFreeCallLimitReached => 'Aylık ücretsiz arama sınırına ulaşıldı. Gelecek ay sıfırlanır.';

  @override
  String get omiTranscriptionOptimized =>
      'Omi\'nin canlı transkripsiyonu gerçek zamanlı konuşmalar için tasarlandı ve kimin ne söylediğini gösterir.';

  @override
  String get chatAppsLoadFailedTitle => 'Sohbet uygulamaları yüklenemedi';

  @override
  String get continueWithGoogle => 'Google ile devam et';

  @override
  String get setupSteps => 'Kurulum Adımları';

  @override
  String totalMemoriesCount(int count) {
    return 'Toplam $count anınız var';
  }

  @override
  String get feedbackSubtitleBatteryDrain => 'Bu, donanım ekibimizin gelişmesine yardımcı olur.';

  @override
  String get tryIt => 'Dene';

  @override
  String get chatAppsInsights => 'Omi\'den içgörüler';

  @override
  String nFiles(int count) {
    return '$count kayıt';
  }

  @override
  String get clearChatTitle => 'Sohbeti Temizle?';

  @override
  String get onlyYouCanUseTemplate => 'Bu şablonu yalnızca siz kullanabilirsiniz';

  @override
  String get raybanMetaCameraExplanation =>
      'Omi, konuşmalarınıza fotoğraf eklemek için gözlüğünüzün kamerasını kullanır. Bunu atlayıp yalnızca sesi kullanabilirsiniz.';

  @override
  String get deviceDiagnosticsTicket => 'Support ticket code';

  @override
  String get capabilityTasks => 'Görevler';

  @override
  String get copyUrl => 'URL\'yi Kopyala';

  @override
  String keepItemPublic(String item) {
    return '$item Herkese Açık Tut';
  }

  @override
  String get chatStarterTeachMe => 'Bana yeni bir şey öğretebilir misin?';

  @override
  String get cancelReasonDetailHint => 'Her türlü geri bildirimi takdir ediyoruz…';

  @override
  String get checkConnectionTryAgain => 'Bağlantını kontrol edip tekrar dene.';

  @override
  String get backToConversations => 'Konuşmalara dön';

  @override
  String get merge => 'Birleştir';

  @override
  String get couldNotLaunchUpgradePage => 'Yükseltme sayfası açılamadı. Lütfen tekrar deneyin.';

  @override
  String get deviceOnboardingTranscriptionSubtitle =>
      'Birkaç kelime söyleyin ve gerçek zamanlı olarak göründüklerini izleyin';

  @override
  String get deleteOnDeviceModelConfirm => 'Bu model silinsin mi?';

  @override
  String get reviewQuestionSpeaker => 'Bunu kim söyledi?';

  @override
  String updatedDate(String date) {
    return '$date güncellendi';
  }

  @override
  String get saveSettings => 'Ayarları Kaydet';

  @override
  String get alreadyGavePermission =>
      'Kayıtlarınızı kaydetmemiz için bize zaten izin verdiniz. İşte neden buna ihtiyacımız olduğunun bir hatırlatması:';

  @override
  String get appCreatedAndInstalled => 'Uygulama oluşturuldu ve yüklendi!';

  @override
  String get failedToRefreshNotionStatus => 'Notion bağlantı durumu yenilenemedi.';

  @override
  String get deviceOnboardingProcessingQuestion => 'Sorunuz işleniyor…';

  @override
  String get chatBlockTask => 'Görev';

  @override
  String get pendantNotConnected => 'Kolye bağlı değil. Senkronize etmek için bağlayın.';

  @override
  String get createActionItem => 'Görev oluştur';

  @override
  String get logsCopied => 'Günlükler kopyalandı';

  @override
  String get timeout5MinutesDesc => '5 dakika sessizlikten sonra konuşmayı sonlandır';

  @override
  String get msgUploadFileFailed => 'Dosya yüklenemedi, lütfen daha sonra tekrar deneyin';

  @override
  String get reportMessageConfirm => 'Bu mesaj bildirilsin mi?';

  @override
  String deletePersonConfirmation(String name) {
    return 'Bu, $name adlı kişinin ses örneklerini kaldırır ve geri alınamaz. Geçmiş konuşmalardaki sözleri adsız konuşmacılara dönüşür.';
  }

  @override
  String get weekdayTue => 'Sal';

  @override
  String get liveTranscript => 'Canlı Transkript';

  @override
  String timeDaysAndHours(int days, int hours) {
    return '$days gün $hours saat';
  }

  @override
  String versionLabel(String version) {
    return 'Sürüm $version';
  }

  @override
  String get cancelConsequenceDelay => '5-7 saniye işleme gecikmesi (cihaz modelleri)';

  @override
  String captureRecordingSeparateMessage(String recording) {
    return '$recording ayrı bir konuşma olarak görünecek ve bu etkinlikle tekrar gruplanmayacak.';
  }

  @override
  String get updateAvailableTitle => 'Güncelleme mevcut';

  @override
  String get dreamReportShadowBanner =>
      'Önizleme modu: Dream neyi değiştireceğini gösterir, ancak hesabında henüz hiçbir şey değişmez.';

  @override
  String get sharedTasksAcceptFailed => 'Bu görevler kabul edilemedi. Bu paylaşımı zaten kabul etmiş olabilirsiniz.';

  @override
  String get appPricingLabel => 'Uygulama Fiyatlandırması';

  @override
  String get reDownload => 'Yeniden indir';

  @override
  String get recordWithPhoneMic => 'Telefon mikrofonuyla kaydet';

  @override
  String appDisabledOn(String date) {
    return '$date tarihinde devre dışı bırakıldı.';
  }

  @override
  String get play => 'Oynat';

  @override
  String get private => 'Özel';

  @override
  String get speakerTagPromptNotSureAction => 'Emin Değilim';

  @override
  String get showDiscardedConversationsDesc => 'Atılanmış olarak işaretlenmiş konuşmaları dahil et';

  @override
  String get captureModeLiveDescription => 'Siz konuşurken gerçek zamanlı olarak yazıya dökün.';

  @override
  String get subscriptionCancelledSuccessfully =>
      'Abonelik başarıyla iptal edildi. Mevcut fatura döneminin sonuna kadar aktif kalacaktır.';

  @override
  String get tapToSetAGoal => 'Bir hedef belirlemek için dokun';

  @override
  String get tellUsMoreWhatWentWrong => 'Neyin yanlış gittiğini bize daha fazla anlatın…';

  @override
  String get downgradeToFreemiumTitle => 'Ücretsiz plana düşürülsün mü?';

  @override
  String get usageTasks => 'Görevler';

  @override
  String get chatReplyOffline => 'Bağlanılamıyor. Bağlantınızı kontrol edin ve yeniden deneyin.';

  @override
  String get makePublic => 'Herkese açık yap';

  @override
  String get authUnexpectedErrorFirebase => 'Giriş yaparken beklenmeyen hata, Firebase hatası, lütfen tekrar deneyin.';

  @override
  String get unlimitedConversations => 'Sınırsız konuşmalar';

  @override
  String get stagingDisclaimer =>
      'Test ortamı kararsız olabilir, tutarsız performans gösterebilir ve veriler kaybolabilir. Yalnızca test için.';

  @override
  String get captureMicrophonePermissionRequired => 'Mikrofon izni gerekli';

  @override
  String shareStatsInsights(String count) {
    return '✨ $count içgörü sağladı';
  }

  @override
  String get feedbackReasonSummaryIrrelevant => 'Alakasız';

  @override
  String get userIdCopiedToClipboard => 'Kullanıcı kimliği kopyalandı';

  @override
  String get urlCopiedToClipboard => 'URL panoya kopyalandı';

  @override
  String annualBillingSummary(int months, String price) {
    return '$months ay / $price';
  }

  @override
  String chatAppsShowInAppOff(String app) {
    return 'Kapalı: yalnızca $app içinde görürsün.';
  }

  @override
  String get replySentSuccessfully => 'Yanıt başarıyla gönderildi';

  @override
  String get deviceOnboardingTurnOffTitle => 'Kapat';

  @override
  String get phoneStorageDesc =>
      'Omi yeniden bağlandığında, kayıtlar yüklenmeden önce otomatik olarak telefonunuza aktarılır.';

  @override
  String get callRecordingConsentDisclaimer => 'Arama kaydi, yargi bolgenizde onay gerektirebilir';

  @override
  String get showDiscardedConversations => 'Atılan Konuşmaları Göster';

  @override
  String get calendarIntegration => 'Takvim Entegrasyonu';

  @override
  String get whisperModelSizeBase => 'Temel';

  @override
  String get shareViaSms => 'SMS ile paylaş';

  @override
  String get nameMustBeAtLeast3Characters => 'Ad en az 3 karakter olmalıdır';

  @override
  String get chatDiscardRecording => 'Vazgeç';

  @override
  String get chatAppsProPerkText => 'Telegram ve iMessage\'dan Omi\'ye mesaj at';

  @override
  String get readyToSync => 'Senkronize etmeye hazır';

  @override
  String get noAppsInCategoryYet => 'Bu Kategoride Henüz Uygulama Yok';

  @override
  String get firmwareUpdateAvailable => 'Yazılım Güncellemesi Mevcut';

  @override
  String get modelNumber => 'Model Numarası';

  @override
  String get sortBy => 'Sırala';

  @override
  String get slideToUpdate => 'Güncellemek için kaydırın';

  @override
  String get effectBarelyCounts => 'Neredeyse yardımcı olmaz';

  @override
  String get onlyYouCanUse => 'Yalnızca siz bu uygulamayı kullanabilirsiniz';

  @override
  String get triggersWhenNewConversationCreated => 'Yeni bir konuşma oluşturulduğunda tetiklenir.';

  @override
  String get paymentPlan => 'Ödeme Planı';

  @override
  String get whisperModelDesc => 'Cihaz üzerinde transkripsiyon için model seçin';

  @override
  String get askSuggestOwe => 'Hâlâ insanlara ne borçluyum?';

  @override
  String get starConversation => 'Konuşmayı Favorilere Ekle';

  @override
  String get hardwareSection => 'Donanım';

  @override
  String get transcribing => 'Transkribe ediliyor…';

  @override
  String get chatAppsVoiceNotesSubtitle => 'Sesli not gönder, Omi yanıtlasın.';

  @override
  String confidenceNextVoice(String name) {
    return 'Omi için $name kişisinin ses örneği de gerekli. Sesleri hatırla açıkken etiketleyin.';
  }

  @override
  String get rating3PlusStars => '3+ yıldız';

  @override
  String get recordingActive => 'Kayıt aktif';

  @override
  String starFilter(int count) {
    return '$count Yıldız';
  }

  @override
  String get storageLocationLabel => 'Depolama Konumu';

  @override
  String get reviewNoChangesBody => 'Omi notlarınızı düzenlediğinde değişiklikler burada görünür.';

  @override
  String get testPrompt => 'İstemi Test Et';

  @override
  String get otaUpdateUnavailable => 'Bu güncelleme şu anda kullanılamıyor. Daha sonra tekrar deneyin.';

  @override
  String get downloading => 'İndiriliyor…';

  @override
  String get welcomeBackSimple => 'Tekrar hoş geldiniz';

  @override
  String get sttProviderSoniox => 'Soniox';

  @override
  String get clearAllSelection => 'Tümünü temizle';

  @override
  String get confidenceReasonNeverConfirmed => 'Hiç onaylanmadı';

  @override
  String get writeScope => 'Yazma';

  @override
  String get evidenceVoiceReady => 'Ses örneği hazır';

  @override
  String get updateApp => 'Uygulamayı Güncelle';

  @override
  String get weekdayThu => 'Per';

  @override
  String chatUsageCostNoLimit(String used) {
    return 'Sohbet: \$$used bu ay kullanıldı';
  }

  @override
  String get configCopied => 'Yapılandırma panoya kopyalandı';

  @override
  String get startupFailedConfigMessage =>
      'Omi\'nin bu sürümünde bir yapılandırma sorunu var. Bu, cihazınızla ilgili bir sorun değil. Destekle iletişime geçin ve aşağıdaki ayrıntıları ekleyin.';

  @override
  String get getOmiForMac => 'Mac için Omi\'yi Edinin';

  @override
  String get appleHealthConnectedBadge => 'Bağlandı';

  @override
  String get msgCameraNotAvailable => 'Bu platformda kamera çekimi kullanılamıyor';

  @override
  String get actionItemsDescription => 'Düzenlemek için dokunun • Seçmek için uzun basın • Eylemler için kaydırın';

  @override
  String get notificationsDesc =>
      'Omi\'nin size konuşma özetleri, görev hatırlatıcıları ve uygulamalarınızdan yanıtlar gönderebilmesi için.';

  @override
  String audioUploadRetrying(String duration) {
    return 'Yükleme yeniden deneniyor… $duration ses telefonunuzda saklanıyor';
  }

  @override
  String get importStarted => 'İçe aktarma başladı! Tamamlandığında bildirim alacaksınız.';

  @override
  String get onDeviceModelDownloadFailed => 'Model indirilemedi';

  @override
  String get noProjectsInWorkspace => 'Bu çalışma alanında proje bulunamadı';

  @override
  String get helpCenter => 'Yardım Merkezi';

  @override
  String get trainingDataBullets =>
      '• Verileriniz AI modellerini geliştirmeye yardımcı olur\n• Yalnızca hassas olmayan veriler paylaşılır';

  @override
  String get invalidPromotionCode => 'Geçersiz promosyon kodu.';

  @override
  String get battery => 'Pil';

  @override
  String get clearSelection => 'Seçimi temizle';

  @override
  String get phoneSetupStep2Subtitle => 'Arama sirasinda gireceksiniz kisa bir kod';

  @override
  String get googleSearch => 'Google Search';

  @override
  String get charging => 'Şarj oluyor';

  @override
  String deleteNamedPerson(String name) {
    return '$name kişisini sil';
  }

  @override
  String get chatAppsPartOfPro => 'Sohbet uygulamaları Pro\'nun bir parçasıdır';

  @override
  String get invalidWebhookUrlError => 'Lütfen geçerli bir webhook URL\'si girin';

  @override
  String get starConversationsToFindQuickly => 'Konuşmaları burada hızlıca bulmak için yıldızlayın';

  @override
  String get permissionCreateMemories => 'Anı Oluştur';

  @override
  String get conversationIdCopied => 'Konuşma kimliği panoya kopyalandı';

  @override
  String get chatAppsMessagesApp => 'Mesajlar';

  @override
  String get understandingWords => 'Anlama (kelime)';

  @override
  String diagnosticsVerdictTroubleDetail(int count) {
    return 'Son 24 saatteki başarısız bağlantılar: $count';
  }

  @override
  String get editName => 'Adı Düzenle';

  @override
  String get askAboutThisConversation => 'Bunu sor';

  @override
  String get useTemplateFrom => 'Şablonu kullan';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'Mikrofon izin durumu: $status. Lütfen Sistem Tercihleri\'ni kontrol edin.';
  }

  @override
  String get markAsCompleted => 'Tamamlandı olarak işaretle';

  @override
  String get urlMustEndWithSlashError => 'URL \"/\" ile bitmelidir';

  @override
  String get deviceOnboardingIntroTitle => 'Omi\'nizi Tanıyın';

  @override
  String nPending(int count) {
    return '$count beklemede';
  }

  @override
  String get howShouldOmiCallYou => 'Omi size nasıl hitap etmeli?';

  @override
  String get preparingFormForYou => 'Form sizin için hazırlanıyor…';

  @override
  String get deleteChat => 'Sohbeti sil';

  @override
  String get msgPhotosPermissionDenied =>
      'Fotoğraf izni reddedildi. Resim seçmek için lütfen fotoğraflara erişime izin verin';

  @override
  String get moreWaysToRecord => 'Diğer kayıt yöntemleri';

  @override
  String get creatingPlan => 'Plan oluşturuluyor';

  @override
  String get configCopiedToClipboard => 'Yapılandırma panoya kopyalandı';

  @override
  String get transcribeLaterDescription =>
      'Şimdi kaydet, istediğin zaman metne dönüştür. O zamana kadar ses telefonunda kalır.';

  @override
  String get couldNotSwitchToFreePlan => 'Ücretsiz plana geçilemedi. Lütfen tekrar deneyin.';

  @override
  String get wrappedTasksCompleted => 'görev tamamlandı';

  @override
  String get deviceOnboardingTranscriptionTitle => 'Omi\'nize Konuşun';

  @override
  String get thankYouRequestUnderReview =>
      'Teşekkürler! İsteğiniz inceleniyor. Onaylandıktan sonra sizi bilgilendireceğiz.';

  @override
  String get unpairAndForgetDevice => 'Eşleştirmeyi Kaldır ve Cihazı Unut';

  @override
  String get sendWebUrl => 'Web URL gönder';

  @override
  String get noTasksForToday => 'Bugün için görev yok.\nDaha fazla görev için Omi\'ye sorun veya manuel oluşturun.';

  @override
  String get conversationSummaryFailed => 'Özet oluşturulamadı';

  @override
  String get realtimeTranscript => 'Gerçek zamanlı transkript';

  @override
  String nConversationsCreated(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count konuşma oluşturuldu',
      one: '1 konuşma oluşturuldu',
    );
    return '$_temp0';
  }

  @override
  String get noEmailSet => 'E-posta ayarlanmadı';

  @override
  String get setDueDateAndTime => 'Bitiş tarihini ve saatini ayarla';

  @override
  String get pairingDescFieldy => 'Cihazı açmak için ışık görünene kadar basılı tutun.';

  @override
  String get maximumSecurityE2ee => 'Maksimum Güvenlik (E2EE)';

  @override
  String get instantSpeakerLabels => 'Anında konuşmacı etiketleri';

  @override
  String get resetRequestConfig => 'İstek yapılandırmasını varsayılana sıfırla';

  @override
  String get webhookUrlNotSet => 'Webhook URL ayarlanmadı';

  @override
  String get feedbackReasonRecordingOther => 'Başka bir şey';

  @override
  String get accountCutoverMigrationRollbackMessage =>
      'Taşıma geri alınmasından sonra hesabınız bakımda. Daha yeni bazı veriler izole kalabilir.';

  @override
  String get cancelConsequenceQuality => '%30 daha düşük transkripsiyon kalitesi (cihaz modelleri)';

  @override
  String get pairingDescPlaudNote =>
      'Yan düğmeyi 2 saniye basılı tutun. Eşleştirmeye hazır olduğunda kırmızı LED yanıp söner.';

  @override
  String get plansAndBilling => 'Planlar ve Faturalama';

  @override
  String get deviceOnboardingVoiceReplyTitle => 'Omi\'nin yanıtlarını dinleyin';

  @override
  String get generatingIcon => 'İkon oluşturuluyor…';

  @override
  String get cleanUpBannerBody => 'Çoğu yanlış duyulmuş isimler. Gözden geçirin ve gerçek olmayanları kaldırın.';

  @override
  String get speakerTagPromptSavedAsYou => 'Siz olarak kaydedildi';

  @override
  String get connectOmiOmiGlass => 'Omi / OmiGlass Bağla';

  @override
  String get capabilityConversations => 'Konuşmalar';

  @override
  String get notificationFrequencyDescription =>
      'Omi\'nin size ne sıklıkla proaktif bildirimler ve hatırlatıcılar gönderdiğini kontrol edin.';

  @override
  String chatScopeAbout(String title) {
    return 'Hakkında: $title';
  }

  @override
  String get importHistory => 'İçe Aktarma Geçmişi';

  @override
  String get getApiKey => 'API Anahtarı Al';

  @override
  String get nothingInterestingRetry => 'İlginç bir şey bulunamadı,\ntekrar denemek ister misiniz?';

  @override
  String get whatWouldYouLikeToCreate => 'Ne oluşturmak istersiniz?';

  @override
  String get pricingFree => 'Ücretsiz';

  @override
  String get speakerTagPromptHintIdentify => 'Yanıtınız, Omi\'nin bu sesi bir dahaki sefere tanımasına yardımcı olur.';

  @override
  String get noConversationsYet => 'Henüz görüşme yok';

  @override
  String get deviceNotMeetRequirements => 'Cihazınız cihaz üzerinde transkripsiyon gereksinimlerini karşılamıyor.';

  @override
  String get pressKeys => 'Tuşlara basın…';

  @override
  String get downgradeLimitDelayNotRealTime => '5-7 saniye gecikme (gerçek zamanlı değil)';

  @override
  String get conversationLinkCopiedToClipboard => 'Sohbet bağlantısı panoya kopyalandı';

  @override
  String get onboardingSetupStepMemory => 'Belleğiniz ayarlanıyor';

  @override
  String get chatAppsTelegramOtherDevice => 'Telegram başka bir cihazda mı?';

  @override
  String get appNotFoundOrRemoved => 'Bu uygulama artık kullanılamıyor';

  @override
  String appsCount(String count) {
    return 'Uygulamalar ($count)';
  }

  @override
  String get endToEndEncryption => 'Uçtan Uca Şifreleme';

  @override
  String otaConnectFailed(String deviceName) {
    return '$deviceName cihazına bağlanılamadı. Açık ve yakında tutun, sonra tekrar deneyin.';
  }

  @override
  String get continueButton => 'Devam et';

  @override
  String get failedToPrepareConversationForSharing => 'Konuşma paylaşım için hazırlanamadı. Lütfen tekrar deneyin.';

  @override
  String get showAll => 'Hepsini göster →';

  @override
  String get speakerLabelYou => 'Siz';

  @override
  String get wrappedActionItems => 'Görevler';

  @override
  String failedToInstallApp(String appName) {
    return '$appName yüklenemedi. Lütfen tekrar deneyin.';
  }

  @override
  String get searching => 'Aranıyor';

  @override
  String get deviceNotCompatibleTitle => 'Cihaz Uyumlu Değil';

  @override
  String get summarize => 'Özetle';

  @override
  String get exportConversationsToJson => 'Konuşmaları JSON dosyasına aktar';

  @override
  String makeItemPrivateExplanation(String item) {
    return '$item şimdi özel yaparsanız, herkes için çalışmayı durduracak ve yalnızca size görünür olacak';
  }

  @override
  String get wrappedFailedToShare => 'Paylaşım başarısız. Lütfen tekrar deneyin.';

  @override
  String get cancelSubscriptionConfirmation => 'Mevcut fatura döneminin sonuna kadar erişiminiz devam edecektir.';

  @override
  String get phoneHideKeypad => 'Tuş takımını gizle';

  @override
  String get vadGate => 'VAD Gate';

  @override
  String get nameUpdatedSuccessfully => 'İsim başarıyla güncellendi!';

  @override
  String get photoLibrary => 'Fotoğraf Kütüphanesi';

  @override
  String get chatAppsHeroMessage =>
      'Telegram veya iMessage üzerinden gününü sor, anıları kaydet ve görevlerini yönet. Sohbetlerin kullandığın uygulamada kalır, Omi de konuştuklarınızı her yerde hatırlar.';

  @override
  String get upgradeToAnnualPlan => 'Yıllık Plana Yükseltin';

  @override
  String get completeAuthInBrowser =>
      'Lütfen tarayıcınızda kimlik doğrulamayı tamamlayın. Tamamlandığında uygulamaya geri dönün.';

  @override
  String errorLabel(String error) {
    return 'Hata: $error';
  }

  @override
  String get durationThresholdDesc => 'Bundan kısa konuşmaları gizle';

  @override
  String transcriptionsPendingCount(int count) {
    return 'Bekleyen transkriptler $count';
  }

  @override
  String get transcribeLaterNote =>
      'Telefonun mikrofonu ile Omi ve Limitless cihazlarında çalışır. Yüklemeyi seçene kadar ses telefonunda kalır.';

  @override
  String get device => 'Cihaz';

  @override
  String get signUpSuccess => 'Kayıt başarılı!';

  @override
  String get onboardingPermissions => 'İzinler';

  @override
  String get modelTooLargeWarning =>
      'Bu model büyük ve mobil cihazlarda uygulamanın çökmesine veya çok yavaş çalışmasına neden olabilir.\n\nsmall veya base önerilir.';

  @override
  String get showDailyScoreOnHomepage => 'Ana sayfada günlük puanı göster';

  @override
  String confidenceSummaryUnverified(String name) {
    return '$name kişisini henüz etiketlemediniz veya onaylamadınız; bu yüzden Omi onun sesini tanıyıp tanımadığından emin değil.';
  }

  @override
  String get endConversation => 'Konuşmayı Sonlandır';

  @override
  String get unpinAsBaseline => 'Temelden ayır';

  @override
  String audioSavedLocally(String duration) {
    return '$duration ses yerel olarak kaydedildi';
  }

  @override
  String get editMemory => '✏️ Hafızayı düzenle';

  @override
  String get speakerTagPromptThanks => 'Teşekkürler! Omi sesleri daha iyi tanıyacak.';

  @override
  String get actionItemDescriptionEmpty => 'Görev açıklaması boş olamaz.';

  @override
  String get maybeLater => 'Belki sonra';

  @override
  String get daySummary => 'Günlük Özet';

  @override
  String get confirmReportMessage => 'Bu mesaj bildirilsin mi?';

  @override
  String get deleteAllLimitlessConversations => 'Tüm Limitless konuşmaları silinsin mi?';

  @override
  String get selectAllTasksMenu => 'Tümünü seç';

  @override
  String get syncStatusRetrying => 'İşlenemedi — yeniden deneniyor';

  @override
  String get exportButton => 'Dışa aktar';

  @override
  String get wrappedYouTalkedAboutBadge => 'Hakkında Konuştun';

  @override
  String get firmwareWarningTitle => 'Önemli: Güncellemeden Önce Okuyun';

  @override
  String get permissionTypeCreate => 'Oluştur';

  @override
  String get viewUsage => 'Kullanımı görüntüle';

  @override
  String get deviceOnboardingIntroDuration => 'Yaklaşık 1 dakika';

  @override
  String get import => 'İçe Aktar';

  @override
  String get conversationsExportStarted =>
      'Konuşma dışa aktarımı başlatıldı. Bu birkaç saniye sürebilir, lütfen bekleyin.';

  @override
  String get speechToTextProvider => 'Konuşmadan metne sağlayıcı';

  @override
  String get languageTranslation => '100+ dil çevirisi';

  @override
  String get primaryLanguage => 'Birincil Dil';

  @override
  String durationSeconds(String seconds) {
    return 'Süre: $seconds saniye';
  }

  @override
  String get autoSyncDescription => 'Cihazınız bağlandığında çevrimdışı kayıtları otomatik olarak eşitleyin';

  @override
  String get debugLogs => 'Hata ayıklama günlükleri';

  @override
  String get authorizationRevoked => 'İzin geri alındı.';

  @override
  String get noTranscriptAvailable => 'Transkript Mevcut Değil';

  @override
  String get available => 'Mevcut';

  @override
  String get wrappedObsessionsLabelUpper => 'TAKINTILER';

  @override
  String get professionStudent => 'Öğrenci';

  @override
  String get chatAppsTryRemind => 'Pazar günü annemi aramamı hatırlat';

  @override
  String get failedToStartVerification => 'Dogrulama baslatılamadi';

  @override
  String get failedToCreateFolder => 'Klasör oluşturulamadı';

  @override
  String timeMinSingular(int count) {
    return '$count dk';
  }

  @override
  String get insights => 'İçgörüler';

  @override
  String get privacyInformation => 'Gizlilik Bilgileri';

  @override
  String get finishedConversation => 'Konuşma bitti mi?';

  @override
  String get syncGoogleAccount => 'Google hesabınızla senkronize edin';

  @override
  String get pairingTitleNeoOne => 'Neo One\'ı Eşleştirme Moduna Alın';

  @override
  String get translatedByOmi => 'Omi tarafından çevrildi';

  @override
  String get githubRepositoryUrl => 'GitHub Depo URL\'si';

  @override
  String get readOnlyScope => 'Yalnızca Okuma';

  @override
  String get chatAppsChannelsTitle => 'Sohbet uygulamaları';

  @override
  String get chatAppsDoesAnswer => 'Konuşmaların ve anıların hakkındaki soruları yanıtlar';

  @override
  String get wrappedFailedToStartGeneration => 'Oluşturma başlatılamadı. Lütfen tekrar deneyin.';

  @override
  String get storageLocationSdCard => 'SD Kart';

  @override
  String get askSuggestDecide => 'Bugün neye karar verdim?';

  @override
  String get close => 'Kapat';

  @override
  String get paymentMethodPayPal => 'PayPal';

  @override
  String categoryAppCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count uygulama',
      one: '1 uygulama',
    );
    return '$_temp0';
  }

  @override
  String get speakerTagPromptRecentPeople => 'Yakın zamanda konuştuğunuz kişiler';

  @override
  String get actionCreateMemories => 'Anı oluştur';

  @override
  String get swipeTasksToIndent => 'Görevleri girintili hale getirmek için kaydırın, kategoriler arasında sürükleyin';

  @override
  String get createAccountTitle => 'Hesap Oluştur';

  @override
  String get modelRequired => 'Model gerekli';

  @override
  String get saveMemory => 'Anıyı Kaydet';

  @override
  String get successfullyConnectedClickUp => 'ClickUp\'a başarıyla bağlanıldı!';

  @override
  String get notYetSynced => 'Henüz telefonunuzla senkronize edilmedi';

  @override
  String get pendantUpToDate => 'Kolye güncel';

  @override
  String get categoryProductivityTools => 'Verimlilik Araçları';

  @override
  String get refresh => 'Yenile';

  @override
  String get cancelSyncMessage => 'İndirilen veriler kaydedilecek. Daha sonra devam edebilirsiniz.';

  @override
  String get selectImageFileTitle => 'Bir resim dosyası seçin';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'Dosya seçici açılırken hata: $message';
  }

  @override
  String get failedToGenerateConversationLink => 'Sohbet bağlantısı oluşturulamadı';

  @override
  String get voiceFailedToTranscribe => 'Ses metne dönüştürülemedi';

  @override
  String get viewAll => 'Tümünü gör';

  @override
  String get yourNewKey => 'Yeni anahtarınız:';

  @override
  String get conversationMap => 'Konuşma Haritası';

  @override
  String get contactSupportAction => 'Destekle İletişime Geç';

  @override
  String get weekdaySun => 'Paz';

  @override
  String get summaryNotFound => 'Özet bulunamadı';

  @override
  String get shortConversationThreshold => 'Kısa Konuşma Eşiği';

  @override
  String get dailyRecapsDescription => 'Günlük özetleriniz oluşturulduktan sonra burada görünecek';

  @override
  String get phoneCallsWithOmi => 'Omi ile aramalar';

  @override
  String get addAppSelectPaymentPlan => 'Bir ödeme planı seçin ve uygulamanız için fiyat girin';

  @override
  String get deleteAccountFinal =>
      'Bu işlem geri alınamaz ve hesabınızı ve tüm ilgili verileri kalıcı olarak silecektir. Devam etmek istediğinizden emin misiniz?';

  @override
  String get gettingAudioFiles => 'Ses dosyaları alınıyor…';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String get port => 'Port';

  @override
  String personPinnedToast(String name) {
    return '$name sabitlendi';
  }

  @override
  String get wrappedConversations => 'konuşma';

  @override
  String get availableOnMacMobileWeb => 'Mac, mobil ve web\'de kullanılabilir';

  @override
  String get monthAug => 'Ağu';

  @override
  String get failedToGenerateSummary => 'Özet oluşturulamadı. O gün için konuşmalarınız olduğundan emin olun.';

  @override
  String planEndedOn(String date) {
    return 'Planınız $date tarihinde sona erdi.\nŞimdi yeniden abone olun - yeni fatura dönemi için hemen ücretlendirileceksiniz.';
  }

  @override
  String get createAnApp => 'Uygulama Oluştur';

  @override
  String get cancelling => 'İptal ediliyor…';

  @override
  String get wrappedTopDaysHeader => 'En İyi Günlerin';

  @override
  String get keepEditing => 'Düzenlemeye Devam Et';

  @override
  String get ignoredVoicesEmpty => 'Yok sayılan ses yok';

  @override
  String get cannotBeUndone => 'Bu işlem geri alınamaz.';

  @override
  String get usersPayToUse => 'Kullanıcılar uygulamanızı kullanmak için ödeme yapar';

  @override
  String get maxFilesUploadError => 'Aynı anda yalnızca 4 dosya yükleyebilirsiniz';

  @override
  String get yourDeviceIsUpToDate => 'Cihazınız güncel';

  @override
  String get unableToFetchApps =>
      'Uygulamalar alınamadı :(\n\nLütfen internet bağlantınızı kontrol edin ve tekrar deneyin.';

  @override
  String get entityCorrectionFailed => 'Düzeltmeniz gönderilemedi. Tekrar deneyin.';

  @override
  String get alreadyAuthorized => 'Zaten İzin Verildi';

  @override
  String get speedAccuracyLower => 'Hız ve doğruluk Bulut modellerinden daha düşük olabilir.';

  @override
  String siriShortcutsSearchHint(String searchPhrase) {
    return ' Ayrıca “$searchPhrase for what I did today” diyebilirsiniz.';
  }

  @override
  String get unlimitedPlan => 'Sınırsız Plan';

  @override
  String get contactSupport => 'Desteğe Başvur?';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Maksimum $count hedef izin verildi';
  }

  @override
  String get deviceStorageNearlyFull => 'Cihaz neredeyse dolu — yer açmak için eşitleyin.';

  @override
  String get setDueDate => 'Bitiş tarihini ayarla';

  @override
  String privateAppsCount(String count) {
    return 'Özel Uygulamalar ($count)';
  }

  @override
  String get selectPeople => 'Kişileri seç';

  @override
  String get capabilityChat => 'Sohbet';

  @override
  String chatAppsChannelChats(String app) {
    return '$app sohbetleri';
  }

  @override
  String get transcribeLaterTitle => 'Sonradan Transkribe Et';

  @override
  String get failedToConnectAsana => 'Asana\'ya bağlanılamadı';

  @override
  String get youAreOnUnlimitedPlan => 'Sınırsız Plan\'dasınız.';

  @override
  String get chatAppsIncludedWithPro => 'OMI PRO İLE BİRLİKTE GELİR';

  @override
  String get failedToCreateKeyTryAgain => 'Anahtar oluşturulamadı. Lütfen tekrar deneyin.';

  @override
  String get backgroundModeTitle => 'Arka Plan Modu';

  @override
  String get discardChangesMessage => 'Kaydedilmemiş değişiklikleriniz kaybolacak.';

  @override
  String get captureSourcePendant => 'Kolye';

  @override
  String get exportTasksWithOneTap => 'Görevleri tek dokunuşla dışa aktarın!';

  @override
  String get sundayAbbr => 'Paz';

  @override
  String get pleaseEnterAppPrompt => 'Lütfen uygulamanız için bir istem girin';

  @override
  String deviceStoragePercentFull(int percent) {
    return '%$percent dolu';
  }

  @override
  String get developerSettings => 'Geliştirici Ayarları';

  @override
  String get selectYouFromList => 'Kendinizi etiketlemek için lütfen listeden \"Sen\" seçeneğini seçin.';

  @override
  String get deleteNow => 'Şimdi Sil';

  @override
  String get installUpdate => 'Güncellemeyi Yükle';

  @override
  String get unpairDevice => 'Cihaz Eşleştirmesini Kaldır';

  @override
  String get assistantVoice => 'Asistan Sesi';

  @override
  String get installingApp => 'Uygulama yükleniyor…';

  @override
  String get wrappedFunnyMomentTitle => 'Komik an';

  @override
  String onboardingFailedCheckNotification(String error) {
    return 'Bildirim izni kontrol edilemedi: $error';
  }

  @override
  String get dreamReportRunNow => 'Şimdi Çalıştır';

  @override
  String get notSet => 'Ayarlanmamış';

  @override
  String get startVoiceRecording => 'Ses kaydını başlat';

  @override
  String get userInformation => 'Kullanıcı Bilgileri';

  @override
  String get wrappedStruggleLabel => 'ZORLUK';

  @override
  String get filterInteresting => 'İçgörüler';

  @override
  String captureRecordingsCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count kayıt',
      one: '1 kayıt',
    );
    return '$_temp0';
  }

  @override
  String get addOrChangeYourPaymentMethod => 'Ödeme yöntemi ekleyin veya değiştirin';

  @override
  String get unableToLoadApps => 'Uygulamalar yüklenemiyor';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'Omi cihazınız için yeni bir yazılım güncellemesi ($version) mevcut. Şimdi güncellemek ister misiniz?';
  }

  @override
  String get cancelReasonTooExpensive => 'Çok pahalı';

  @override
  String get firmwareUsbWarning => 'Güncellemeler sırasında USB bağlantısı cihazınıza zarar verebilir.';

  @override
  String authAccessMessage(String appName) {
    return 'Omi\'nin $appName verilerinize erişmesine yetki vermeniz gerekecek. Bu, kimlik doğrulama için tarayıcınızı açacaktır.';
  }

  @override
  String get conversationEndsManually => 'Konuşma yalnızca manuel olarak sona erecektir.';

  @override
  String get partialRecording => 'Kısmi kayıt';

  @override
  String get dreamReportFeedback => 'Omi ekibine bildirildi';

  @override
  String get shareAudio => 'Sesi Paylaş';

  @override
  String get importDataFromOtherSources => 'Diğer kaynaklardan veri içe aktar';

  @override
  String get premiumMinutesUsed => 'Premium dakikalar kullanıldı.';

  @override
  String get phoneCallsUpgradeButton => 'Sınırsız\'a yükselt';

  @override
  String get omiUnlimited => 'Omi Sınırsız';

  @override
  String get unknownDevice => 'Bilinmeyen';

  @override
  String get failedToStartImport => 'İçe aktarma başlatılamadı. Lütfen tekrar deneyin.';

  @override
  String get searchActionItems => 'Görevleri ara';

  @override
  String get whisperModel => 'Whisper modeli';

  @override
  String get searchContacts => 'Kişilerde ara';

  @override
  String get selectAllSkipsPinned => 'Tümünü Seç, sabitli kişileri atlar. Onları kendi sayfalarından tek tek silin.';

  @override
  String get speechProfileIntro => 'Omi hedeflerinizi ve sesinizi öğrenmeli. Daha sonra değiştirebilirsiniz.';

  @override
  String get realtimeListening => 'Gerçek Zamanlı Dinleme';

  @override
  String get appNotAvailable => 'Hay aksi! Aradığınız uygulama mevcut değil görünüyor.';

  @override
  String get enterYourName => 'Adınızı girin';

  @override
  String get permissionTypeTrigger => 'Tetikleyici';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'Yeni anılar oluşturdukça bilgi grafiğiniz otomatik olarak oluşturulacak.';

  @override
  String get chatAppsLink => 'Bağlantı';

  @override
  String get minutes => 'dakika';

  @override
  String get actions => 'Eylemler';

  @override
  String get connectRayBanMeta => 'Ray-Ban Meta\'yı Bağla';

  @override
  String get monthSep => 'Eyl';

  @override
  String get selectContactsToShareSummary => 'Konuşma özetinizi paylaşmak için kişileri seçin';

  @override
  String get paymentNoneSelected => 'Seçilmedi';

  @override
  String get pinAction => 'Sabitle';

  @override
  String get monthOct => 'Eki';

  @override
  String get startRecording => 'Kaydı başlat';

  @override
  String get somethingWentWrong => 'Bir şeyler ters gitti! Lütfen daha sonra tekrar deneyin.';

  @override
  String largeTimeGapsDetected(String gaps) {
    return 'Büyük zaman farkları tespit edildi ($gaps)';
  }

  @override
  String get phoneEnterNumber => 'Numara girin';

  @override
  String get cancelConsequenceNoAccess => 'Fatura dönemi sonunda sınırsız erişim olmayacak.';

  @override
  String get appleHealthDeniedTitle => 'Apple Health erişimi reddedildi';

  @override
  String deleteItemTitle(String item) {
    return '$item Sil';
  }

  @override
  String get invalidIntegrationUrl => 'Geçersiz entegrasyon URL';

  @override
  String get welcomeActionItemsTitle => 'Görevler için Hazır';

  @override
  String get updateAppConfirmation => 'Değişiklikler ekibimiz inceledikten sonra yayına girer.';

  @override
  String get corruptedStatus => 'Bozuk';

  @override
  String get cantRateWithoutInternet => 'İnternet bağlantısı olmadan uygulama değerlendirilemez.';

  @override
  String get dontShowAgain => 'Tekrar gösterme';

  @override
  String get hardwareRevision => 'Donanım Revizyonu';

  @override
  String get trySelectingDifferentDate => 'Farklı bir tarih seçmeyi deneyin';

  @override
  String get learnings => 'Öğrenilenler';

  @override
  String get failedToConnectTodoist => 'Todoist\'a bağlanılamadı';

  @override
  String get accessDataProgrammatically => 'Verilerinize programatik olarak erişin';

  @override
  String processingProgress(int current, int total) {
    return 'İşleniyor $current/$total';
  }

  @override
  String get apiEnvSavedRestartRequired => 'Kaydedildi. Değişiklikleri uygulamak için uygulamayı kapatıp yeniden açın.';

  @override
  String get syncCardWaitingInternet => 'İnternet bekleniyor';

  @override
  String get accountCutoverOpenStore => 'Mağazayı aç';

  @override
  String get processedConversations => 'İşlenmiş Konuşmalar';

  @override
  String get holdOnPreparingForm => 'Bekleyin, formu sizin için hazırlıyoruz';

  @override
  String get waitingForDevice => 'Cihaz bekleniyor…';

  @override
  String get learnMore => 'Daha fazla bilgi…';

  @override
  String get aiGenErrorWhileCreatingApp => 'Uygulama oluşturulurken bir hata oluştu';

  @override
  String get deleteAllFilesWarning =>
      'Bu, senkronize ve bekleyen kayıtları silecek. Bekleyen kayıtlar senkronize EDİLMEDİ ve kalıcı olarak kaybolacak.';

  @override
  String get usageWordsHeard => 'Words heard';

  @override
  String get importDataDescription => 'Diğer kaynaklardan veri içe aktar';

  @override
  String get raybanMetaImageCaptureUnavailable => 'Yalnızca ses modunda kullanılamaz';

  @override
  String get appRejectedMessage => 'Uygulamanız reddedildi. Lütfen detayları güncelleyip tekrar gönderin.';

  @override
  String get capturePendantDisconnectedShort => 'Omi kendiliğinden yeniden bağlanır';

  @override
  String get improveSpeechProfileDesc =>
      'Kişisel konuşma profilinizi eğitmek ve geliştirmek için kayıtları kullanıyoruz.';

  @override
  String get voiceResponseModeTitle => 'Yanıtlar ne zaman okunsun';

  @override
  String get failedToDeleteItem => 'Görev silinemedi';

  @override
  String get firmware => 'Ürün Yazılımı';

  @override
  String failedToAddToService(String serviceName) {
    return '$serviceName platformuna eklenemedi';
  }

  @override
  String get askOmiAnything => 'Hayatınız hakkında Omi\'ye her şeyi sorun';

  @override
  String get integrationsFooter => 'Sohbette veri ve metrikleri görmek için uygulamalarınızı bağlayın.';

  @override
  String get loading => 'Yükleniyor…';

  @override
  String get showLess => 'daha az göster ↑';

  @override
  String get chatAppsNeverMessagesOthers => 'Senin yerine başkalarına asla mesaj atmaz';

  @override
  String get scopeUserName => 'Kullanıcı Adı';

  @override
  String get mute => 'Sessiz';

  @override
  String get serverProcessesAudio => 'Sunucu ses dosyalarını işler ve anılar oluşturur';

  @override
  String mergeConversationsSuccessBody(int count) {
    return '$count konuşma başarıyla birleştirildi';
  }

  @override
  String get pairingSuccessful => 'EŞLEŞTIRME BAŞARILI';

  @override
  String get websocketUrl => 'WebSocket URL\'si';

  @override
  String get wrappedFriend => 'Arkadaş';

  @override
  String get frequencyHigh => 'Yüksek';

  @override
  String get processingFailed => 'İşleme Başarısız';

  @override
  String get dataLowercase => 'veriler';

  @override
  String deviceOfflineWakeHint(String deviceName) {
    return '$deviceName çevrimdışı. Uyandırmak için düğmesine basın, sonra tekrar deneyin.';
  }

  @override
  String get updatedConversations => 'Güncellenen Konuşmalar';

  @override
  String get phoneGetStarted => 'Basla';

  @override
  String get recordingDetails => 'Kayıt Detayları';

  @override
  String get createApiKey => 'API Anahtarı Oluştur';

  @override
  String get anyoneWithLinkCanView => 'Bağlantıya sahip olan herkes görüntüleyebilir';

  @override
  String get noPendingTasks => 'Bekleyen görev yok';

  @override
  String get featureComingSoon => 'Bu özellik yakında geliyor!';

  @override
  String get bluetoothMethodDescription =>
      'Standart Bluetooth Low Energy bağlantısı kullanır. Daha yavaş ama WiFi bağlantınızı etkilemez.';

  @override
  String get chatAppsNotConnectedTitle => 'Bağlı değil';

  @override
  String get wrappedMostIntenseDay => 'En Yoğun';

  @override
  String get yesterday => 'Dün';

  @override
  String get requestConfiguration => 'İstek Yapılandırması';

  @override
  String get timeAM => 'ÖÖ';

  @override
  String autoRemoveSyncedCopiesDescription(int days) {
    return 'Senkronizasyondan $days gün sonra yerel kopyaları siler. Bulut kopyaları saklanır.';
  }

  @override
  String get chatAppsTelegramPrivacyNote =>
      'Omi ile sohbetlerin Telegram tarafından da saklanır. Omi yalnızca sana yanıt verir, başkalarına asla, ve bağlantıyı istediğin zaman kesebilirsin.';

  @override
  String speakerWithId(String speakerId) {
    return 'Konuşmacı $speakerId';
  }

  @override
  String get reviewNoDate => 'Yok';

  @override
  String get transcript => 'Transkript';

  @override
  String get deviceDiagnosticsUploadFailed => 'Could not send diagnostics to support. Please try again.';

  @override
  String get noFoldersAvailable => 'Kullanılabilir klasör yok';

  @override
  String get addAppSelectCategory => 'Uygulamanız için bir kategori seçin';

  @override
  String get conversations => 'Konuşmalar';

  @override
  String get upgradeToUnlimited => 'Sınırsıza yükselt';

  @override
  String get deleteFlowConfirmTitle => 'Hesabınız silinsin mi?';

  @override
  String get accountCutoverMigrationInProgressMessage =>
      'Hesabınız taşınıyor. Taşıma bitene kadar ürün özellikleri duraklatılır.';

  @override
  String get permissionAllowed => 'İzin verildi';

  @override
  String get pressDoneToSave => 'Kaydetmek için bitti\'ye basın';

  @override
  String get listening => 'Dinleme';

  @override
  String get audioReady => 'Ses Hazır';

  @override
  String get freeForEveryone => 'Herkes için ücretsiz';

  @override
  String get buildingKnowledgeGraphFromMemories => 'Anılardan bilgi grafiği oluşturuluyor…';

  @override
  String get onDeviceTranscription => 'Cihaz üzerinde transkripsiyon';

  @override
  String errorWithMessage(String error) {
    return 'Hata: $error';
  }

  @override
  String get chatAppsProblemOffline => 'Çevrimdışısın. Bağlantını kontrol edip tekrar dene.';

  @override
  String get callAlreadyInProgress => 'Bir arama zaten devam ediyor';

  @override
  String get reviewQuestionSpelling => 'Bu nasıl yazılır?';

  @override
  String get firmwareStableConnection => 'Kararlı bağlantı';

  @override
  String get categoryOther => 'Diğer';

  @override
  String get perMonthLabel => '/ ay';

  @override
  String get onboardingYoureAllSet => 'Hazırsınız';

  @override
  String get resumeRecording => 'Kaydı Sürdür';

  @override
  String get feedbackSubtitleAudioQuality => 'Neyin yanlış gittiğini anlamak isteriz.';

  @override
  String get speakerTagPromptPlayClip => 'Klibi oynat';

  @override
  String get anonymityAndPrivacy => 'Anonimlik ve Gizlilik';

  @override
  String get noMemoriesToDelete => 'Silinecek anı yok';

  @override
  String get syncStepProcess => 'Yazıya dök';

  @override
  String get callStateRinging => 'Caliyor…';

  @override
  String get setupOnDevice => 'Cihazda ayarla';

  @override
  String get creatorPayouts => 'İçerik Üretici Ödemeleri';

  @override
  String get olderDeviceDetected => 'Eski Cihaz Algılandı';

  @override
  String get deletePhoneNumberWarning => 'Arama yapmak icin tekrar dogrulamaniz gerekecek';

  @override
  String get appVisibilityChangedSuccessfully =>
      'Uygulama görünürlüğü başarıyla değiştirildi. Yansıması birkaç dakika sürebilir.';

  @override
  String get failedToCreateActionItem => 'Görev oluşturulamadı';

  @override
  String get msgSelectFilesGenericError => 'Dosya seçerken hata oluştu. Lütfen tekrar deneyin.';

  @override
  String get pendantRecordingSyncBlocked =>
      'Pendant hâlâ kayıt yapıyor, bu yüzden depolanan ses aktarılamıyor. Kaydı durdurmak için Pendant\'ın düğmesine basın, ardından yeniden senkronize edin.';

  @override
  String get failedToStartMerge => 'Birleştirme başlatılamadı';

  @override
  String get shortcutChangeInstruction => 'Değiştirmek için bir kısayola tıklayın. İptal etmek için Escape\'e basın.';

  @override
  String get notificationsAndDisplay => 'Bildirimler ve Görünüm';

  @override
  String get getPaidThroughStripe => 'Stripe üzerinden uygulama satışlarınız için ödeme alın';

  @override
  String get weekdayWed => 'Çar';

  @override
  String get send => 'Gönder';

  @override
  String get nativeEngineNoDownload => 'Cihazınızın yerel konuşma motoru kullanılacak. Model indirmesi gerekli değil.';

  @override
  String get wrappedActions => 'eylem';

  @override
  String get conversationTimeoutConfig => 'Omi, bir konuşmayı sonlandırmadan önce sessizlikte ne kadar bekler';

  @override
  String get mic => 'Mikrofon';

  @override
  String deviceOnboardingVoiceReplyStatusAlwaysHeadphones(String device) {
    return '$device\'e kadar oynatır.';
  }

  @override
  String failedToSendReply(String error) {
    return 'Yanıt gönderilemedi: $error';
  }

  @override
  String get whisperModelSizeTiny => 'Çok küçük';

  @override
  String get speakerTagPromptNotMeAction => 'Ben değilim';

  @override
  String get setupInstructions => 'Kurulum Talimatları';

  @override
  String get noLanguagesFound => 'Dil bulunamadı';

  @override
  String get experimental => 'Deneysel';

  @override
  String get continueRecording => 'Kayda Devam Et';

  @override
  String get selectDefaultRepoDesc =>
      'Sorun oluşturmak için varsayılan bir depo seçin. Sorun oluştururken farklı bir depo belirtebilirsiniz.';

  @override
  String sharedTasksTitle(String name, int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count görev paylaştı',
      one: '1 görev paylaştı',
    );
    return '$name $_temp0';
  }

  @override
  String get permissionsRequiredDesc =>
      'Bu uygulamanın düzgün çalışması için Bluetooth ve Konum izinlerine ihtiyacı var. Lütfen ayarlardan bunları etkinleştirin.';

  @override
  String diagnosticsVerdictReconnectsDetail(String duration) {
    return 'Kısa kopmalar, her seferinde yaklaşık $duration içinde geri geliyor';
  }

  @override
  String get transferring => 'Aktarılıyor…';

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return 'Bu ay $limit kelimeden $used kullanıldı';
  }

  @override
  String get noChatAppsEnabled => 'Etkin sohbet uygulaması yok.\nEklemek için \"Uygulamaları Etkinleştir\"e dokunun.';

  @override
  String get tipKeepPhoneNearby => 'Daha hızlı senkronizasyon için telefonunuzu yakında tutun';

  @override
  String get authFailedToSignInWithGoogle => 'Google ile giriş yapılamadı, lütfen tekrar deneyin.';

  @override
  String get frequencyDescLow => 'Yalnızca önemli şeyler, günde yaklaşık 3–5';

  @override
  String get availableTemplates => 'Mevcut Şablonlar';

  @override
  String get captureEveryMoment => 'Omi konuşmalarınızı kaydeder ve sizin için\nözeti ve yapılacakları yazar.';

  @override
  String get migrationErrorOccurred => 'Taşıma sırasında bir hata oluştu. Lütfen tekrar deneyin.';

  @override
  String get wrappedCompletedLabel => 'Tamamlandı';

  @override
  String speakerTagPromptLabeledToast(String name) {
    return '$name olarak etiketlendi';
  }

  @override
  String get docs => 'Dokümantasyon';

  @override
  String get dateTimeLabel => 'Tarih ve Saat';

  @override
  String get editFolder => 'Klasörü düzenle';

  @override
  String get apps => 'Uygulamalar';

  @override
  String segmentsSingular(String count) {
    return '$count bölüm';
  }

  @override
  String get deviceSettings => 'Cihaz Ayarları';

  @override
  String get offline => 'Çevrimdışı';

  @override
  String get createActionItemTooltip => 'Yeni görev oluştur';

  @override
  String get forgetDevice => 'Cihazı Unut';

  @override
  String get reviewEntryTitle => 'Size sorular';

  @override
  String get enterEmailError => 'Lütfen e-postanızı girin';

  @override
  String get appDisabledOwnerHint =>
      'Önce uç noktayı düzeltin — yeniden etkinleştirme, yapılandırılmış her URL\'yi tekrar kontrol eder.';

  @override
  String get chatAppsIMessageSubtitle => 'Telefon numaranla Omi\'ye mesaj at';

  @override
  String get tasksExportedOneApp => 'Görevler aynı anda bir uygulamaya aktarılabilir.';

  @override
  String transcriptSpeakerCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count konuşmacı',
      one: '1 konuşmacı',
    );
    return '$_temp0';
  }

  @override
  String get saveGoal => 'Kaydet';

  @override
  String get noBatteryDataYet => 'Henüz pil verisi yok';

  @override
  String chatUsedOfLimitMessages(String used, String limit) {
    return '$used / $limit mesaj bu ay kullanıldı';
  }

  @override
  String get backgroundActivityDesc =>
      'Ekran kapalıyken veya uygulama değiştirdiğinizde Omi\'nin kayda devam etmesi için.';

  @override
  String get addAppUpdateFailed => 'Güncelleme başarısız. Daha sonra tekrar deneyin';

  @override
  String get noMatchingPeople => 'Eşleşen Kişi Yok';

  @override
  String get unlinkCalendarEvent => 'Takvim Etkinliği Bağlantısını Kaldır';

  @override
  String get regenerateRecap => 'Özeti yeniden oluştur';

  @override
  String get deleteSynced => 'Senkronize edilenleri sil';

  @override
  String get speakerTagPromptNameHint => 'Adı';

  @override
  String get freePlan => 'Ücretsiz Plan';

  @override
  String get installs => 'YÜKLEMELER';

  @override
  String get publicLabel => 'Genel';

  @override
  String get deletingMessages => 'Mesajlarınız Omi\'nin hafızasından siliniyor…';

  @override
  String get pendingFilesDeleted => 'Bekleyen kayıtlar silindi';

  @override
  String get checkUsage => 'Kullanımı Kontrol Et';

  @override
  String get addWordsDesc => 'İsimler, terimler veya yaygın olmayan kelimeler';

  @override
  String get entityCorrectionSaved => 'Teşekkürler. Omi düzeltecek.';

  @override
  String get categoryEducation => 'Eğitim';

  @override
  String get planAndUsage => 'Plan ve Kullanım';

  @override
  String get deleteMemory => 'Hafızayı sil';

  @override
  String get dataProtectionLevel => 'Veri Koruma Seviyesi';

  @override
  String timeDaySingular(int count) {
    return '$count gün';
  }

  @override
  String get keyCreated => 'Anahtar Oluşturuldu';

  @override
  String get date => 'Tarih';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return '$itemType taşınıyor… %$percentage';
  }

  @override
  String get enableLocalStorage => 'Yerel Depolamayı Etkinleştir';

  @override
  String get omiSays => 'Omi diyor ki';

  @override
  String get appDetails => 'Uygulama Detayları';

  @override
  String get loadingYourRecording => 'Kaydınız yükleniyor…';

  @override
  String get deleteAllLimitlessWarning =>
      'Limitless\'tan içe aktarılan tüm konuşmalar silinir. Bu işlem geri alınamaz.';

  @override
  String get combiningAudioFiles => 'Ses dosyaları birleştiriliyor…';

  @override
  String get suggestFollowUpQuestion => 'Takip sorusu öner';

  @override
  String chatStarterPrompt(String kind) {
    String _temp0 = intl.Intl.selectLogic(
      kind,
      {
        'capabilities': 'Benim için neler yapabilirsin?',
        'goal': 'Bir hedef belirlememe yardım et',
        'activity': 'Son etkinliklerimi özetle',
        'improve': 'Kendimi nasıl geliştirebilirim?',
        'other': '',
      },
    );
    return '$_temp0';
  }

  @override
  String get speakerTagPromptIgnoredNote => 'Omi bu ses hakkında bir daha sormayacak';

  @override
  String get recordWithPhoneInstead => 'Bunun yerine telefonla kaydet';

  @override
  String get triggerEvent => 'Tetikleyici Olay';

  @override
  String get waitingForTranscriptOrPhotos => 'Transkript veya fotoğraflar bekleniyor…';

  @override
  String get omiApiKeys => 'Omi API Anahtarları';

  @override
  String addNamedPersonAction(String name) {
    return '“$name” ekle';
  }

  @override
  String get enableDetailedDiagnosticMessages => 'Transkripsiyon hizmetinden ayrıntılı tanı mesajlarını etkinleştir';

  @override
  String get nameCannotBeEmpty => 'İsim boş olamaz';

  @override
  String get noTasksYet => 'Henüz görev yok';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'Arama terimlerinizi veya filtrelerinizi ayarlamayı deneyin';

  @override
  String daySummaryForDate(String date) {
    return 'Gün Özeti · $date';
  }

  @override
  String get statusTimedOut => 'Sure doldu';

  @override
  String chatUsageDescription(String used, String limitDisplay, String plan) {
    return '$plan planında $limitDisplay üzerinden $used kullandınız.';
  }

  @override
  String get paypalMeLink => 'PayPal.me Bağlantısı';

  @override
  String get allMemoriesPrivateResult => 'Tüm anılar artık özel';

  @override
  String get scanAgain => 'Tekrar Tara';

  @override
  String get doItAgain => 'Tekrar yap';

  @override
  String get reviewTitle => 'İnceleme';

  @override
  String get photos => 'Fotoğraflar';

  @override
  String get phoneNoVerifiedNumbersMessage => 'Omi üzerinden arama yapmak için numaranı doğrula.';

  @override
  String get save => 'Kaydet';

  @override
  String get deleteAccount => 'Hesabı Sil';

  @override
  String get managePaymentMethod => 'Ödeme Yöntemini Yönet';

  @override
  String get selectThumbnailImageTitle => 'Bir küçük resim seçin';

  @override
  String get pairingTitleOmi => 'Omi\'yi Açın';

  @override
  String get whatsYourPrimaryLanguage => 'Ana diliniz nedir?';

  @override
  String get replyToReview => 'Yoruma Yanıt Ver';

  @override
  String failedToDeleteError(String error) {
    return 'Silme başarısız: $error';
  }

  @override
  String get newestFirst => 'Önce en yeniler';

  @override
  String get wrappedCreatingYourStory => '2025 hikayenizi\noluşturuyoruz…';

  @override
  String get chatAppsPrivateMemories => 'Özel anıları uygulamada tut';

  @override
  String get pleaseEnterPayPalEmail => 'Lütfen PayPal e-postanızı girin';

  @override
  String get transcription => 'Transkripsiyon';

  @override
  String get yourReview => 'Değerlendirmeniz';

  @override
  String get filesDownloadedUploadedNextTime => 'Zaten indirilen dosyalar bir dahaki sefere yüklenecektir.';

  @override
  String get phoneSetupStep3Subtitle => 'Yerlesik canli transkripsiyon ile';

  @override
  String get mcpConnectionFailed => 'MCP sunucusuna bağlanılamadı';

  @override
  String get chatAppsConnectTelegramTitle => 'Telegram\'ı bağla';

  @override
  String get createMemoryTooltip => 'Yeni anı oluştur';

  @override
  String get connectDeviceMessage => 'Cihaz ayarlarına ve özelleştirmeye erişmek için\nOmi cihazınızı bağlayın';

  @override
  String get authorizingMcpServer => 'Yetkilendiriliyor…';

  @override
  String charactersCount(int count) {
    return '$count karakter';
  }

  @override
  String get syncStatusUploaded => 'Yüklendi · Omi\'de işleniyor';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'Lütfen Ayarlar > Görev Entegrasyonları bölümünden $serviceName ile kimlik doğrulaması yapın';
  }

  @override
  String get setDefaultButton => 'Varsayılan Olarak Ayarla';

  @override
  String get resummarizingConversation => 'Konuşma yeniden özetleniyor…\nBu birkaç saniye sürebilir';

  @override
  String estimatedHours(int count) {
    return '~$count saat';
  }

  @override
  String get chatAppsInsightsSubtitle => 'Omi\'nin sana buradan bir özet veya içgörü göndermesine izin ver.';

  @override
  String get memoryAllowUse => 'Kullanıma izin ver';

  @override
  String get model => 'Model';

  @override
  String get memoryGraphTitle => 'Anı Grafiği';

  @override
  String get endpointURL => 'Uç Nokta URL\'si';

  @override
  String get wrappedShareYourWrapped => 'Wrapped\'ını Paylaş';

  @override
  String get micGainDescBoosted => 'Artırılmış - sessiz ortamlar için';

  @override
  String get wrappedMinutes => 'dakika';

  @override
  String get language => 'Dil';

  @override
  String downloadErrorWithMessage(String error) {
    return 'İndirme hatası: $error';
  }

  @override
  String get onboardingRatingPromptNo => 'Hayır';

  @override
  String get whatWouldYouLikeToRemember => 'Ne hatırlamak istersiniz?';

  @override
  String get deviceOnboardingMuteUnmuteDesc => 'Mikrofonu aç veya kapat';

  @override
  String secondsCount(int count) {
    return '$count saniye';
  }

  @override
  String get icon => 'Simge';

  @override
  String get realTimeTranscript => 'Gerçek Zamanlı Transkript';

  @override
  String get deviceOnboardingVoiceReplySample => 'Anladım. Sonraki toplantınız yirmi dakika içinde başlıyor.';

  @override
  String get noDisconnectsRecorded => 'Bağlantı kesilmesi kaydedilmedi';

  @override
  String get filterMyApps => 'Uygulamalarım';

  @override
  String get recapRegenerateCooldown => 'Yeniden oluşturmadan önce lütfen birkaç saniye bekleyin.';

  @override
  String get templateName => 'Şablon Adı';

  @override
  String get retry => 'Tekrar Dene';

  @override
  String get sdCardSyncDescription => 'SD Kart Senkronizasyonu, anılarınızı SD Karttan uygulamaya aktaracak';

  @override
  String get deviceTutorial => 'Omi Nasıl Kullanılır';

  @override
  String get noApiKeysCreateOne => 'API anahtarı yok. Başlamak için bir tane oluşturun.';

  @override
  String siriShortcutsSetupHint(String askPhrase, String questionPhrase) {
    return 'Kısayollar → Siri içinde Omi’yi etkinleştirin. “$askPhrase” veya “$questionPhrase” deyin, sonra sorunuzu sorun.';
  }

  @override
  String get failedToDeleteSomeItems => 'Bazı öğeler silinemedi';

  @override
  String get raybanMetaSetupDescription =>
      'Ray-Ban Meta gözlüğünüzü konuşmalar ve görsel bağlam için Omi kayıt cihazınız olarak kullanın. Omi, gözlüğünüzü bağlamak için Meta AI uygulamasını açacaktır.';

  @override
  String get tabToDo => 'Yapılacak';

  @override
  String get otaWifiFailed => 'Wi-Fi\'a katılınamadı. Ağ adını ve şifreyi kontrol edin.';

  @override
  String get changePlan => 'Planı Değiştir';

  @override
  String copiedToClipboard(String title) {
    return '$title panoya kopyalandı';
  }

  @override
  String get completeAuthBrowser =>
      'Lütfen tarayıcınızda kimlik doğrulamayı tamamlayın. Tamamlandığında uygulamaya geri dönün.';

  @override
  String get migrationInProgressMessage => 'Geçiş devam ediyor. Tamamlanana kadar koruma seviyesini değiştiremezsiniz.';

  @override
  String get keepSubscription => 'Aboneliği Koru';

  @override
  String get playbackPreparingAudio => 'Ses hazırlanıyor…';

  @override
  String get cloudStorageDialogMessage =>
      'Gerçek zamanlı kayıtlarınız konuşurken özel bulut depolamasında saklanacaktır.';

  @override
  String get newChat => 'Yeni sohbet';

  @override
  String get paymentEnterAmountGreaterThanZero => '0\'dan büyük bir tutar girin';

  @override
  String showAllPeople(int count) {
    return 'Tüm $count kişiyi göster';
  }

  @override
  String deletePersonNamedTitle(String name) {
    return '$name silinsin mi?';
  }

  @override
  String get importTranscriptFiles => 'Transkript dosyaları';

  @override
  String get transcriptPlaceholder => 'Transkripsiyon burada gorunecek…';

  @override
  String get logShared => 'Günlük paylaşıldı';

  @override
  String get deleteReasonNotUsing => 'Yeterince kullanmıyorum';

  @override
  String diagnosticsDropsPerHour(int count) {
    return 'saatte yaklaşık $count';
  }

  @override
  String get wrappedProcessingDefault => 'İşleniyor…';

  @override
  String get failedToConnectGoogleTasksRetry => 'Google Tasks\'a bağlanılamadı. Lütfen tekrar deneyin.';

  @override
  String get downloadingFromSdCard => 'SD Karttan İndiriliyor';

  @override
  String get firmwareFormatWarning =>
      'Bu yazılım SD kartı biçimlendirecektir. Lütfen yükseltmeden önce tüm çevrimdışı verilerin senkronize edildiğinden emin olun.\n\nBu sürümü yükledikten sonra yanıp sönen kırmızı bir ışık görürseniz endişelenmeyin. Cihazı uygulamaya bağlamanız yeterlidir ve mavi renğe dönmelidir. Kırmızı ışık, cihazın saatinin henüz senkronize edilmediği anlamına gelir.';

  @override
  String get pleaseProvidePrompt => 'Lütfen bir istem sağlayın';

  @override
  String get voiceResponseAlways => 'Her zaman';

  @override
  String get statusLabel => 'Durum';

  @override
  String get shareLogs => 'Günlükleri paylaş';

  @override
  String get continueAnyway => 'Devam Et';

  @override
  String get transferCompleteMessage => 'Aktarım tamamlandı! Bu kaydı artık çalabilirsiniz.';

  @override
  String get reviewCaughtUpBody => 'Omi burada yalnızca size ihtiyaç duyduğunda soru soracak.';

  @override
  String get calculatingETA => 'Hesaplanıyor…';

  @override
  String get speechProfileTopicWork => 'Ne iş yapıyorsunuz?';

  @override
  String get considerOmiCloud => 'Daha iyi performans için Omi Cloud kullanmayı düşünün.';

  @override
  String get testConversationPrompt => 'Konuşma istemini test et';

  @override
  String get deletePending => 'Bekleyenleri sil';

  @override
  String get renameConversation => 'Yeniden adlandır';

  @override
  String get batteryDrainSignificantly => 'Pil tüketimi önemli ölçüde artacaktır.';

  @override
  String get clear => 'Temizle';

  @override
  String get addAppEnterWebhookUrl => 'Uygulamanız için bir webhook URL\'si girin';

  @override
  String get active => 'Aktif';

  @override
  String get exportStartedMessage => 'Dışa aktarma başladı. Bu birkaç saniye sürebilir…';

  @override
  String get dataAccessNoticeDescription =>
      'Bu uygulama verilerinize erişecektir. Omi AI, verilerinizin bu uygulama tarafından nasıl kullanıldığından, değiştirildiğinden veya silindiğinden sorumlu değildir';

  @override
  String get yourRequestUnderReview => 'Talebin inceleniyor';

  @override
  String get unresolvedSpeakersMessage =>
      'Omi, kayıtlar arasında diğer sesleri ayırt edemedi. Konuşanın kim olduğunu adlandırmak için bir konuşmacı etiketine dokunun.';

  @override
  String downloadError(String error) {
    return 'İndirme hatası: $error';
  }

  @override
  String get offlineSync => 'Çevrimdışı Senkronizasyon';

  @override
  String get cancelSubscription => 'Aboneliği İptal Et';

  @override
  String get claudeDesktopConnectorSetup =>
      'Claude Desktop → Settings → Connectors\'de özel bir bağlayıcı ekleyin ve sunucu URL\'sini yapıştırın. Claude gelişmiş bir OAuth Client ID isterse aşağıdaki değeri kullanın ve gizli anahtarı boş bırakın — MCP API anahtarınızı asla OAuth gizli anahtarı olarak kullanmayın.';

  @override
  String get chatAppsTelegramWaiting => 'Telegram\'da Başlat\'a dokunman bekleniyor…';

  @override
  String get tryAgain => 'Tekrar Dene';

  @override
  String get syncStatusOnDevice => 'Cihazınızda';

  @override
  String get entityCorrectionTitle => 'Neresi doğru değil?';

  @override
  String peopleDeletedToast(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count kişi silindi',
      one: '1 kişi silindi',
    );
    return '$_temp0';
  }

  @override
  String get features => 'Özellikler';

  @override
  String get startEarning => 'Kazanmaya Başlayın! 💰';

  @override
  String get enterYourNumber => 'Numaranizi girin';

  @override
  String get addToClaudeCodeConfig => '~/.claude.json dosyasına ekle';

  @override
  String get cleanDisconnect => 'Temiz bağlantı kesme';

  @override
  String get grantContactsAccess => 'Kisilerinize erisim izni verin';

  @override
  String get feedbackReasonIncorrect => 'Yanlış veya uydurma';

  @override
  String get addAppErrorSelectingImageRetry => 'Görsel seçilirken hata. Tekrar deneyin.';

  @override
  String get feedbackTitleNotUsing => 'Omi\'yi daha fazla kullanmanızı ne sağlardı?';

  @override
  String get memories => 'Anılar';

  @override
  String get capturingPhotos => 'Fotoğraf çekiliyor';

  @override
  String get hideApiKey => 'API Anahtarını Gizle';

  @override
  String get signUpButton => 'Kaydol';

  @override
  String get tuesdayAbbr => 'Sal';

  @override
  String get noApiKeys => 'Henüz API anahtarı yok';

  @override
  String get keyWord => 'Anahtar';

  @override
  String reviewAnswersConversations(int count) {
    return 'Bu yanıt $count konuşmayı etiketler';
  }

  @override
  String get statusFailed => 'Başarısız';

  @override
  String get installedApps => 'Yüklü Uygulamalar';

  @override
  String get flashFirmware => 'Donanım Yazılımını Yükle';

  @override
  String get conversationUrlCouldNotBeGenerated => 'Sohbet URL\'si oluşturulamadı.';

  @override
  String get reloadingApps => 'Uygulamalar yeniden yükleniyor…';

  @override
  String get goalTitle => 'Hedef başlığı';

  @override
  String get importantConversationTitle => 'Önemli Konuşma';

  @override
  String get byContinuingAgree => 'Devam ederek ';

  @override
  String get saturdayAbbr => 'Cmt';

  @override
  String get subscriptionReactivatedDefault =>
      'Aboneliğiniz yeniden etkinleştirildi! Şimdi ücret alınmayacak - mevcut dönem sonunda faturalandırılacaksınız.';

  @override
  String get tryLatestExperimentalFeatures => 'Omi Ekibinin en son deneysel özelliklerini deneyin.';

  @override
  String get chatAppsEntrySubtitle => 'Her gün kullandığın uygulamalardan Omi ile konuş.';

  @override
  String get transcriptionPaused => 'Kaydediyor, yeniden bağlanıyor';

  @override
  String get appleHealthFeatureReadOnlyTitle => 'Yalnızca okuma erişimi';

  @override
  String get shareDataForTraining => 'Eğitim için veri paylaş';

  @override
  String get noNotificationScopesAvailable => 'Kullanılabilir bildirim kapsamı yok';

  @override
  String disconnectFromApp(String appName) {
    return '$appName Bağlantısı Kesilsin mi?';
  }

  @override
  String get failedToConnectGoogleTasks => 'Google Tasks\'a bağlanılamadı';

  @override
  String get copyToClipboard => 'Panoya kopyala';

  @override
  String get stopRecordingConfirmation => 'Kayıt durdurulup konuşma şimdi özetlensin mi?';

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'Özet oluşturulamadı. O gün için konuşmalarınız olduğundan emin olun.';

  @override
  String get monthlyLimitReached => 'Aylık limitinize ulaştınız.';

  @override
  String get permissionsPageDescription =>
      'Omi bunları cihazınıza bağlanmak, ses kaydetmek, arka planda çalışmaya devam etmek, hatırlatıcılar göndermek ve konuşmaların nerede gerçekleştiğini not etmek için kullanır.';

  @override
  String get onboardingTellUsAboutYourself => 'Bize kendinizden bahsedin';

  @override
  String get deviceOnboardingAskQuestionSubtitle => 'Düğmeye bir kez basın, sorunuzu söyleyin, bitince tekrar basın';

  @override
  String get filters => 'Filtreler';

  @override
  String get firmwareUpdateWarning => 'Uygulamayı kapatmayın veya cihazı kapatmayın. Bu, cihazınıza zarar verebilir.';

  @override
  String get oneSourceAtATime => 'Omi aynı anda yalnızca bir kaynaktan kayıt yapar.';

  @override
  String chatAppsConnectedAs(String handle) {
    return '$handle olarak bağlandı';
  }

  @override
  String get pilotFeatures => 'Pilot Özellikler';

  @override
  String get selectFirmwareZip => 'Yazılım ZIP dosyasını seçin';

  @override
  String get feedbackReasonRecordingPoorTranscription => 'Kötü transkripsiyon';

  @override
  String get deleteAccountFailed => 'Hesabınız silinemedi. Lütfen tekrar deneyin.';

  @override
  String get searchConversations => 'Konuşmaları ara';

  @override
  String get frequencyBalanced => 'Dengeli';

  @override
  String get auto => 'Otomatik';

  @override
  String get actionItemUpdatedSuccessfully => 'Görev başarıyla güncellendi';

  @override
  String get entityProjects => 'Projeler';

  @override
  String get signInWithApple => 'Apple ile Giriş Yap';

  @override
  String get backendUrlLabel => 'Sunucu URL';

  @override
  String confidenceSummaryLikely(String name) {
    return 'Omi, $name kişisinin sesini çoğunlukla tanıyor ama bunu yalnızca birkaç kez onayladınız.';
  }

  @override
  String get entityOpenThreads => 'Açık konular';

  @override
  String get deleteActionItemMessage => 'Bu görev silinsin mi?';

  @override
  String chatWithApp(String appName) {
    return '$appName ile sohbet et';
  }

  @override
  String get editActionItem => 'Görevi düzenle';

  @override
  String get cloudStorageEnabled => 'Bulut depolama etkinleştirildi';

  @override
  String get wrappedPersonalGrowth => 'Kişisel Gelişim';

  @override
  String get chatAppsProPerkSave => 'Anıları kaydet ve görevleri doğrudan sohbetten yönet';

  @override
  String get alreadyHaveAccountLogin => 'Zaten hesabınız var mı? Giriş yapın';

  @override
  String makeItemPublicQuestion(String item) {
    return '$item Herkese Açık Yap?';
  }

  @override
  String get usagePeakHour => 'Peak hour';

  @override
  String get addWords => 'Kelime Ekle';

  @override
  String get usageNow => 'now';

  @override
  String get usageMinutes => 'dakika';

  @override
  String availableSpace(String space) {
    return 'Kullanılabilir Alan: $space';
  }

  @override
  String get providingSubtitle => 'Otomatik olarak yakalanan görevler ve notlar.';

  @override
  String wrappedCompletionRate(String rate) {
    return '%$rate tamamlanma oranı';
  }

  @override
  String summaryGeneratedFor(String date) {
    return '$date için özet oluşturuldu';
  }

  @override
  String get selectCategory => 'Kategori Seçin';

  @override
  String nProcessed(int count) {
    return '$count işlendi';
  }

  @override
  String get privacyPolicyTitle => 'Gizlilik Politikası';

  @override
  String get deviceMayWarmUp => 'Cihaz uzun süreli kullanımda ısınabilir.';

  @override
  String get designingApp => 'Uygulama tasarlanıyor';

  @override
  String get couldNotLoadWhatsNew => 'Yenilikler yüklenemedi';

  @override
  String get doNotCloseApp => 'Lütfen uygulamayı kapatmayın.';

  @override
  String get voiceResponseAudio => 'Omi yanıtını sesli oku';

  @override
  String get allTime => 'Tüm Zamanlar';

  @override
  String get developerSettingsTitle => 'Geliştirici Ayarları';

  @override
  String get restoreAction => 'Geri yükle';

  @override
  String get phoneSetupStep3Title => 'Kisilerinizi aramaya baslayin';

  @override
  String get anErrorOccurredTryAgain => 'Bir hata oluştu. Lütfen tekrar deneyin.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'Az önce konuştuklarımız: $link';
  }

  @override
  String get playbackAudioLoadFailed => 'Ses Yüklenemedi';

  @override
  String get phoneMute => 'Sessiz';

  @override
  String get captureNotTranscribing => 'Metne dökülmüyor';

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return 'Kayıt durduruldu: $reason. Harici ekranları yeniden bağlamanız veya kaydı yeniden başlatmanız gerekebilir.';
  }

  @override
  String get sttProviderDeepgram => 'Deepgram';

  @override
  String get spaceKey => 'Boşluk';

  @override
  String get raybanMetaOpenMetaAI => 'Meta AI ile bağlan';

  @override
  String get linkEvent => 'Etkinliği Bağla';

  @override
  String get fairUse3Day => '3 günlük süre';

  @override
  String failedToStartAppAuth(String appName) {
    return '$appName kimlik doğrulaması başlatılamadı';
  }

  @override
  String get processingOnServer => 'Sunucuda işleniyor…';

  @override
  String errorStartingRecording(String error) {
    return 'Kayıt başlatma hatası: $error';
  }

  @override
  String get quiet => 'Sessiz';

  @override
  String get startConversationToSeeInsights =>
      'Kullanım içgörülerinizi burada görmek için\nOmi ile bir konuşma başlatın.';

  @override
  String get processAudio => 'Sesi İşle';

  @override
  String get chatAppsConnectIMessageTitle => 'Bağlanmak için Omi\'ye mesaj at';

  @override
  String get chatWithOmi => 'Omi ile Sohbet';

  @override
  String get clickToBeginRecording => 'Kaydı başlatmak için tıklayın';

  @override
  String get confirmAndProceed => 'Onayla ve Devam Et';

  @override
  String get mondayAbbr => 'Pzt';

  @override
  String sdCardProcessingMessage(int count) {
    return '$count kayıt işleniyor. Dosyalar işlendikten sonra SD karttan silinecek.';
  }

  @override
  String get chatReplyNotSignedIn => 'Oturum açmadınız. Oturum açın ve tekrar deneyin.';

  @override
  String deviceOnboardingVoiceReplySettingsHint(String settings, String voiceResponse) {
    return 'Bunu istediğiniz zaman $settings › $voiceResponse numaralı telefondan değiştirebilirsiniz.';
  }

  @override
  String get wrappedGenerateMyWrapped => 'Wrapped\'ımı Oluştur';

  @override
  String get reviewChangesIntro =>
      'Omi’nin son 30 günde kendi kendine yaptığı değişiklikler. Yanlış görünen her şeyi geri alın.';

  @override
  String get stripeReadyForPayments =>
      'Stripe hesabınız artık ödeme almaya hazır. Uygulama satışlarınızdan hemen kazanmaya başlayabilirsiniz.';

  @override
  String get appleWatchSetup => 'Apple Watch Kurulumu';

  @override
  String get failedToDisconnect => 'Bağlantı kesilemedi';

  @override
  String get localStorageEnabled => 'Yerel depolama etkinleştirildi';

  @override
  String get captureSourceDesktop => 'Bilgisayar';

  @override
  String get serialNumber => 'Seri Numarası';

  @override
  String get appleHealthFeatureSecureDesc => 'Apple Health verilerin Omi hesabına gizli şekilde senkronize edilir.';

  @override
  String get tryAdjustingSearch => 'Arama veya filtreleri ayarlamayı deneyin';

  @override
  String connectTo(String appName) {
    return '$appName\'e Bağlan';
  }

  @override
  String get exportConversationsDescription => 'Konuşmaları JSON\'a aktar';

  @override
  String get featuredLabel => 'ÖNE ÇIKAN';

  @override
  String get speechProfile => 'Ses Profili';

  @override
  String get integrations => 'Entegrasyonlar';

  @override
  String get hideCompletedTasks => 'Tamamlananları gizle';

  @override
  String get sendRawAudioToOmi => 'Ham sesi Omi\'ye gönder';

  @override
  String ratingsCount(String count) {
    return '$count+ puan';
  }

  @override
  String get exportShared => 'Dışa aktarma paylaşıldı';

  @override
  String get conversationTimeout => 'Konuşma Zaman Aşımı';

  @override
  String get installStableFirmware => 'Kararlı yazılımı yükle';

  @override
  String get secureAndReliable => 'Güvenli ve güvenilir';

  @override
  String get exportingConversations => 'Konuşmalar dışa aktarılıyor…';

  @override
  String get feedbackReasonRecordingFragmentedOrDuplicated => 'Parçalı veya tekrarlı';

  @override
  String get chatAppsWaitingMessage => 'Mesajı Mesajlar\'dan gönder. Omi\'ye ulaşır ulaşmaz bu ekran güncellenir.';

  @override
  String get onboardingSetupStepWorkspace => 'Çalışma alanınız hazırlanıyor';

  @override
  String get recap => 'Özet';

  @override
  String get lessThanAMinute => 'Bir dakikadan az';

  @override
  String get tasks => 'Görevler';

  @override
  String get onboardingSetupStepDevices => 'Cihazlarınız bağlanıyor';

  @override
  String pinPersonTitle(String name) {
    return '$name kişisini sabitle';
  }

  @override
  String get wrappedButYouPushedThrough => 'Ama başardınız 💪';

  @override
  String get fetchingYourAppDetails => 'Uygulama bilgileri alınıyor';

  @override
  String get timeout2MinutesDesc => '2 dakika sessizlikten sonra konuşmayı sonlandır';

  @override
  String get otaUpdateCancelled => 'Güncelleme iptal edildi';

  @override
  String get usageTasksNotes => 'Tasks & notes';

  @override
  String get deviceNotConnected => 'Cihaz Bağlı Değil';

  @override
  String get rayBanMetaMicPickerEmpty =>
      'Bluetooth mikrofonu bulunamadı. Gözlüğünüzü iPhone Ayarları\'ndan bağlayıp tekrar deneyin.';

  @override
  String get actionItemCompleted => 'Görev tamamlandı';

  @override
  String get usageSocialSettings => 'Sosyal Ortamlarda';

  @override
  String get from => 'itibaren';

  @override
  String get siriIndexSetting => 'Use Omi with Siri & Apple Intelligence';

  @override
  String get reviewReasonNotMine => 'Benim değil';

  @override
  String connectToDeviceName(String deviceName) {
    return '$deviceName cihazına bağlan';
  }

  @override
  String get onboardingComplete => 'Tamamlandı';

  @override
  String get chatAppsShowInApp => 'Bu sohbetleri Omi uygulamasında göster';

  @override
  String nCompleted(int count) {
    return '$count tamamlandı';
  }

  @override
  String get feedbackAllGood => 'Her şey yolunda';

  @override
  String get syncCardUploadingTitle => 'Omi\'ye yükleniyor';

  @override
  String get baselineMemory => 'Temel bellek';

  @override
  String get trainFamilyProfilesDesc =>
      'Kayıtlarınız arkadaşlarınızı ve ailenizi tanımamıza ve profil oluşturmamıza yardımcı olur.';

  @override
  String get failedToGenerateShareLink => 'Paylaşım bağlantısı oluşturulamadı';

  @override
  String get onlyYouCanSeeConversation => 'Bu konuşmayı yalnızca siz görebilirsiniz';

  @override
  String get popular => 'Popüler';

  @override
  String get captureRecordingSeparate => 'Ayır…';

  @override
  String get allTemplates => 'Tüm Şablonlar';

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
  String speakerTagPromptSavedAs(String name) {
    return '$name olarak kaydedildi';
  }

  @override
  String get configureSettings => 'Ayarları Yapılandır';

  @override
  String get noRatings => 'puan yok';

  @override
  String resumingInCountdown(String countdown) {
    return '$countdown saniye içinde devam ediliyor…';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 $count anı hatırladı';
  }

  @override
  String get clearDueDate => 'Son tarihi temizle';

  @override
  String get copy => 'Kopyala';

  @override
  String get showPhoneCallButtonDesc => 'Ana ekranda telefon arama düğmesini göster';

  @override
  String get appleHealthFeatureReadOnlyDesc => 'Omi, Apple Health\'e asla yazmaz ve verilerini değiştirmez.';

  @override
  String get multipleSpeakersDescription =>
      'Kayıtta birden fazla konuşmacı var gibi görünüyor. Sessiz bir yerde olduğunuzdan emin olun ve tekrar deneyin.';

  @override
  String get failedToUpdateDueDate => 'Son tarih güncellenemedi';

  @override
  String get successfullyConnectedWhoop => 'Whoop\'a başarıyla bağlanıldı!';

  @override
  String get categories => 'Kategoriler';

  @override
  String get loadingTranscript => 'Döküm yükleniyor…';

  @override
  String get syncCustomSttWarningMessage =>
      'Kendi transkripsiyon sağlayıcınızı kullanıyorsunuz. Bu kayıtları eşitlemek onları Omi sunucularında yazıya döker ve planınızın transkripsiyon sınırına sayılır.';

  @override
  String get newRecording => 'Yeni kayıt';

  @override
  String get transcriptionUnavailableRecordingSaved =>
      'Transkripsiyon kullanılamıyor — kayıt devam ediyor ve sesiniz kaydediliyor.';

  @override
  String get submittingYourApp => 'Uygulamanız gönderiliyor…';

  @override
  String get failedToLinkCalendarEvent => 'Takvim etkinliği bağlanamadı';

  @override
  String get paypalMeLinkHint => 'paypal.me/nik';

  @override
  String get yourInformation => 'Bilgileriniz';

  @override
  String get accountDeletionInProgressSignInAgain =>
      'Bu hesap siliniyor. Başka bir hesapla giriş yapın ya da birkaç dakika bekleyip tekrar deneyin.';

  @override
  String get on => 'On';

  @override
  String get diagnostics => 'Tanılama';

  @override
  String get errorCopied => 'Hata mesajı panoya kopyalandı';

  @override
  String get lovingOmi => 'Omi\'yi Beğeniyor musunuz?';

  @override
  String get permissionDescReadMemories => 'Bu uygulama anılarınıza erişebilir.';

  @override
  String get doNotIncludeHttpInLink => 'Bağlantıya http veya https veya www eklemeyin';

  @override
  String get shareRecording => 'Kaydı Paylaş';

  @override
  String get memoryReviewFix => 'Düzelt';

  @override
  String get selectedPlanNotAvailable => 'Seçilen plan mevcut değil. Lütfen tekrar deneyin.';

  @override
  String get autoCreateWhenDetected => 'İsim algılandığında otomatik oluştur';

  @override
  String get addAppSelectCapability => 'Uygulamanız için en az bir yetenek seçin';

  @override
  String get showPassword => 'Şifreyi göster';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Konuşmalar artık $minutes dakika sessizlikten sonra sonlanacak';
  }

  @override
  String get updateAvailableMessage => 'Omi\'nin yeni sürümü hazır; düzeltmeler ve iyileştirmeler içeriyor.';

  @override
  String get nameMustBeBetweenCharacters => 'Ad 2 ile 40 karakter arasında olmalıdır';

  @override
  String operatorSubtitle(int count) {
    return 'Ayda $count soru';
  }

  @override
  String conversationsDeletedCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count konuşma silindi',
      one: '1 konuşma silindi',
    );
    return '$_temp0';
  }

  @override
  String get monthlyPayoutsDescription => '10 \$ kazanca ulaştığınızda aylık ödemeleri doğrudan hesabınıza alın';

  @override
  String get dailyScoreExplanation =>
      'Günlük skorunuz görev tamamlamaya dayanır. Skorunuzu artırmak için görevlerinizi tamamlayın!';

  @override
  String get improveConnectionContent =>
      'Omi\'nin cihazınıza bağlı kalma şeklini iyileştirdik. Bunu etkinleştirmek için Cihaz Bilgileri sayfasına gidin, \"Cihazı Kes\" seçeneğine dokunun ve cihazınızı tekrar eşleştirin.';

  @override
  String get syncingRecordings => 'Kayıtlar senkronize ediliyor';

  @override
  String get professionProductManager => 'Ürün Yöneticisi';

  @override
  String get nameMustBeAtLeast2Characters => 'İsim en az 2 karakter olmalıdır';

  @override
  String get conversationTitle => 'Sohbet Başlığı';

  @override
  String mcpServerConnected(int count) {
    return '$count araç başarıyla bağlandı';
  }

  @override
  String get feedbackSubtitleNotUsing => 'Omi\'yi sizin için daha yararlı hale getirmek istiyoruz.';

  @override
  String get exportBeforeDelete =>
      'Hesabınızı silmeden önce verilerinizi dışa aktarabilirsiniz, ancak silindikten sonra kurtarılamaz.';

  @override
  String deleteTasksTitle(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count görev silinsin mi?',
      one: '1 görev silinsin mi?',
    );
    return '$_temp0';
  }

  @override
  String get frequencyMaximum => 'Maksimum';

  @override
  String get cancelReasonSubtitle => 'Neden ayrıldığınızı bize söyleyebilir misiniz?';

  @override
  String get generatingIconStep => 'İkon oluşturuluyor';

  @override
  String get storeAudioDescription =>
      'Tüm ses kayıtlarını telefonunuzda yerel olarak saklayın. Devre dışı bırakıldığında, depolama alanından tasarruf etmek için yalnızca başarısız yüklemeler saklanır.';

  @override
  String get unpairDeviceConfirmTitle => 'Cihaz eşleştirmesi kaldırılsın mı?';

  @override
  String get phoneCallsMaybeLater => 'Belki daha sonra';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'Bir hata oluştu: $message';
  }

  @override
  String get yourPrivacyMattersToUs => 'Gizliliğiniz Bizim İçin Önemli';

  @override
  String get collapseAction => 'Daralt';

  @override
  String get friendWordOfMouth => 'Arkadaş';

  @override
  String get deviceOnboardingVoiceReplyStatusHeadphonesDisconnected =>
      'Kulaklık bağlı değil. Omi siz bazılarını bağlayana kadar sessiz kalır.';

  @override
  String get connectDevice => 'Cihazı Bağla';

  @override
  String get deviceId => 'Cihaz Kimliği';

  @override
  String get addWordsDescription => 'Omin transkripsiyon sırasında tanıması gereken kelimeleri ekleyin.';

  @override
  String get userId => 'Kullanıcı Kimliği';

  @override
  String evidenceCardConfirms(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count öneride Evet',
      one: '1 öneride Evet',
    );
    return '$_temp0';
  }

  @override
  String segmentsCount(int count) {
    return '$count segment';
  }

  @override
  String get permissionsSetupTitle => 'En iyi deneyimi yaşayın';

  @override
  String get permissionTypeAccess => 'Erişim';

  @override
  String get speakerTagPromptSaveVoicesBody =>
      'Omi, onları bir dahaki sefere tanıyabilmek için kısa bir ses örneği saklar. Bunu istediğin zaman Ayarlar\'dan değiştirebilirsin.';

  @override
  String get developerApi => 'Geliştirici API\'si';

  @override
  String get chargingIssues => 'Şarj Sorunları';

  @override
  String get debugAndDiagnostics => 'Hata Ayıklama ve Tanılama';

  @override
  String get failedConnections => 'Başarısız bağlantılar';

  @override
  String get userIdCopied => 'Kullanıcı kimliği panoya kopyalandı';

  @override
  String get cannotReportOwnMessage => 'Kendi mesajlarınızı bildiremezsiniz.';

  @override
  String get latestVersion => 'En Son Sürüm';

  @override
  String get feedbackReasonNotHelpful => 'Faydasız veya alakasız';

  @override
  String get deletePeopleMessage =>
      'Bu, ses örneklerini kaldırır ve geri alınamaz. Geçmiş konuşmalardaki sözleri adsız konuşmacılara dönüşür.';

  @override
  String get deviceOnboardingAllSetSubtitle => 'İncelemek veya değiştirmek için bir satıra dokunun.';

  @override
  String get mergeConversations => 'Konuşmaları Birleştir';

  @override
  String get paused => 'Duraklatıldı';

  @override
  String get updateGuide => 'Güncelleme Kılavuzu';

  @override
  String cancelBillingPeriodInfo(String date) {
    return 'Planınız $date tarihine kadar aktif kalacaktır. Bundan sonra sınırlı özelliklerle ücretsiz sürüme geçirileceksiniz.';
  }

  @override
  String get reconnectingToInternet => 'İnternete yeniden bağlanılıyor…';

  @override
  String get allFilesDeleted => 'Tüm kayıtlar silindi';

  @override
  String get paypalEmailHint => 'nik@example.com';

  @override
  String get oneWeekAgo => '1 hafta önce';

  @override
  String get deviceOnboardingAllSetSinglePressBadge => '1×';

  @override
  String get playbackAudioUnavailable => 'Ses Kullanılamıyor';

  @override
  String get deviceOnboardingTryDoubleTap => 'Şimdi deneyin! Omi\'nize çift dokunun';

  @override
  String get deleteReasonPrivacy => 'Gizlilik endişeleri';

  @override
  String get cleanUpPinnedNote => 'Sabitli kişiler temizlemeye hiçbir zaman dahil edilmez.';

  @override
  String get wrappedProductiveDay => 'Verimli';

  @override
  String get voiceSharedAcrossDevices => 'Ses seçiminiz mobil ve masaüstü arasında paylaşılır.';

  @override
  String get knowledgeGraphDeleted => 'Bilgi grafiği silindi';

  @override
  String get pressDoneToCreate => 'Oluşturmak için bitti\'ye basın';

  @override
  String get cloudStorage => 'Bulut Depolaması';

  @override
  String get howDoesItWork => 'Nasıl çalışır?';

  @override
  String get submitApp => 'Uygulamayı Gönder';

  @override
  String get searchMemories => 'Anı ara';

  @override
  String get fallNotificationTitle => 'Ayy';

  @override
  String storedOnDevice(String deviceName) {
    return '$deviceName üzerinde depolandı';
  }

  @override
  String get contactsPermissionRequired => 'Kişi izni gerekli';

  @override
  String get reviewUpdatedSuccessfully => 'Yorum başarıyla güncellendi 🚀';

  @override
  String get pleaseEnterPayPalMeLink => 'Lütfen PayPal.me bağlantınızı girin';

  @override
  String get notHelpful => 'Yardımcı olmadı';

  @override
  String get recordingsToSync => 'Senkronize edilecek kayıtlar';

  @override
  String get categoryUtilities => 'Araçlar';

  @override
  String get exportStarted => 'Dışa aktarma başladı. Bu birkaç saniye sürebilir…';

  @override
  String get deviceOnboardingVoiceReplyStatusOff => 'Omi sessiz kalacak. Cevaplar hâlâ uygulamada görünüyor.';

  @override
  String get myGoal => 'Hedefim';

  @override
  String timeHourSingular(int count) {
    return '$count saat';
  }

  @override
  String get chatToolsManifestUrl => 'Sohbet Araçları Bildirim URL\'si';

  @override
  String msgSelectFilesError(String error) {
    return 'Dosya seçerken hata: $error';
  }

  @override
  String connectedToApp(String appName) {
    return '$appName\'e bağlandı';
  }

  @override
  String get entityCorrectionHint => 'Omi’ye neyi düzelteceğini söyleyin';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch başarıyla bağlandı!';

  @override
  String appIntegration(String appName) {
    return '$appName Entegrasyonu';
  }

  @override
  String get cancelReasonAudioQuality => 'Ses/transkripsiyon kalitesi';

  @override
  String get invalidProviderInConfig => 'Yapılandırmada geçersiz sağlayıcı';

  @override
  String get deselectAll => 'Tümünün Seçimini Kaldır';

  @override
  String get chatAppsCodeExpiredMessage => 'Yeni bir kod al ve Mesajlar\'dan gönder.';

  @override
  String get reviewAnswerFailed => 'Yanıtınız kaydedilemedi. Tekrar deneyin.';

  @override
  String get categorySocial => 'Sosyal';

  @override
  String get rating4PlusStars => '4+ yıldız';

  @override
  String get couldNotOpenSmsApp => 'SMS uygulaması açılamadı. Lütfen tekrar deneyin.';

  @override
  String get chatAppsNoMessages => 'Mesaj yok';

  @override
  String get wrappedCelebrity => 'ÜNLÜ';

  @override
  String get revokeKeyQuestion => 'Anahtar İptal Edilsin mi?';

  @override
  String timeMinsAndSecs(int mins, int secs) {
    return '$mins dk $secs sn';
  }

  @override
  String get searchContactsHint => 'Kişileri ara';

  @override
  String get showEventsWithoutParticipants => 'Katılımcısız Etkinlikleri Göster';

  @override
  String get fair => 'Orta';

  @override
  String get tipAutoSync => 'Kayıtlar otomatik olarak senkronize edilir';

  @override
  String get summaryCopiedToClipboard => 'Özet panoya kopyalandı';

  @override
  String get clearSearch => 'Aramayı temizle';

  @override
  String get speakerTagPromptNotAPerson => 'Kişi Değil';

  @override
  String get modelLabel => 'Model';

  @override
  String deleteItemQuestion(String item) {
    return '$item Silinsin mi?';
  }

  @override
  String get enterPromoCode => 'Promosyon kodunu girin';

  @override
  String get phoneNoContactsFound => 'Kisi bulunamadi';

  @override
  String countRemaining(String count) {
    return '$count kalan';
  }

  @override
  String get manageYourApp => 'Uygulamanızı Yönetin';

  @override
  String get willSyncAutomatically => 'otomatik olarak senkronize edilecek';

  @override
  String get promoCode => 'Promosyon kodu';

  @override
  String get trackPersonalGoalsOnHomepage => 'Ana sayfada kişisel hedeflerinizi takip edin';

  @override
  String get memoryHistoryPartial =>
      'Anı geçmişinin bir kısmı kullanılamıyor. Şimdiye kadar alınan geçmiş gösteriliyor.';

  @override
  String get sharePublicLink => 'Herkese Açık Bağlantıyı Paylaş';

  @override
  String get conversationTab => 'Konuşma';

  @override
  String get backgroundModeDescription => 'Uygulama tamamen kapalıyken bile Omi\'nizi kayıtta tutun.';

  @override
  String get pairingDescOmiDevkit => 'Açmak için düğmeye bir kez basın. Eşleştirme modunda LED mor renkte yanıp söner.';

  @override
  String get callStateFailed => 'Arama basarisiz';

  @override
  String get githubRepositoryUrlHint => 'Uygulamanın kaynak kod deposunun bağlantısı';

  @override
  String get appIconLabel => 'App Icon';

  @override
  String get uninstallApp => 'Uygulamayı kaldır';

  @override
  String get confidenceReasonNeedsVoice => 'henüz ses örneği yok';

  @override
  String get couldNotLoadApiKeys => 'API anahtarları yüklenemedi.';

  @override
  String get fetchingStableFirmware => 'En son kararlı yazılım alınıyor…';

  @override
  String get onDeviceModelDownloaded => 'İndirildi';

  @override
  String get noAPIKeys => 'API anahtarı yok. Başlamak için bir tane oluşturun.';

  @override
  String get phoneCallsUpsellFeature3 => 'Alıcılar rastgele değil, gerçek numaranızı görür';

  @override
  String get wrappedMovieRecs => 'Arkadaşlar için film önerileri';

  @override
  String msgFilePickerError(String error) {
    return 'Dosya seçici açılırken hata: $error';
  }

  @override
  String get professionEntrepreneur => 'Girişimci';

  @override
  String get recent => 'Son aramalar';

  @override
  String get permissionDescCreateMemories => 'Bu uygulama yeni anılar oluşturabilir.';

  @override
  String get tapToComplete => 'Tamamlamak için dokun';

  @override
  String vocabularyWordCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count kelime',
      one: '1 kelime',
    );
    return '$_temp0';
  }

  @override
  String get deleteSyncedFilesMessage => 'Bu kayıtlar zaten telefonunuzla senkronize edildi. Bu geri alınamaz.';

  @override
  String get cancelConsequenceSpeakers => 'Konuşmacıları tanımlayamaz.';

  @override
  String get aiGenFailedToGenerateApp => 'Uygulama oluşturulamadı. Lütfen tekrar deneyin.';

  @override
  String get account => 'Hesap';

  @override
  String get capabilityIntegrations => 'Entegrasyonlar';

  @override
  String get voiceSettingsAskToTag => 'Sesleri etiketlememi iste';

  @override
  String get chatAppsHeroTitle => 'Zaten sohbet ettiğin yerden Omi ile sohbet et';

  @override
  String get myApps => 'Benim oluşturduğum';

  @override
  String get deleteRecap => 'Özeti sil';

  @override
  String get production => 'Üretim';

  @override
  String get phoneRecordingBlockedByPendantBatch =>
      'Telefonunuzla kaydetmeden önce kolyenizdeki Transcribe Later\'ı durdurun.';

  @override
  String dataRateKbps(String rate) {
    return '$rate kbps';
  }

  @override
  String get createAKeyToGetStarted => 'Başlamak için bir anahtar oluşturun';

  @override
  String get pleaseSelectRating => 'Lütfen bir puan seçin';

  @override
  String get pdfTranscriptExport => 'Döküm Dışa Aktar';

  @override
  String get newFolder => 'Yeni Klasör';

  @override
  String get fallNotificationBody => 'Düştünüz mü?';

  @override
  String get scopeUserChat => 'Kullanıcı Sohbeti';

  @override
  String get tryDifferentSearchTerm => 'Farklı bir arama terimi deneyin';

  @override
  String get submit => 'Gönder';

  @override
  String get deviceOnboardingVoiceReplySubtitle => 'Buton ile sorduğunuz zaman Omi cevabını sesli olarak okuyabilir.';

  @override
  String get showOnLockScreen => 'Kilit ekranında göster';

  @override
  String get msgMaxImagesLimit => 'En fazla 4 resim seçebilirsiniz';

  @override
  String get wrappedOmiLifeRecap => 'Omi Yaşam Özeti';

  @override
  String get nextButton => 'İleri';

  @override
  String disconnectAppTitle(String appName) {
    return '$appName Bağlantısı Kesilsin mi?';
  }

  @override
  String get updateReview => 'Değerlendirmeyi Güncelle';

  @override
  String get noMemoriesInCategory => 'Bu kategoride henüz anı yok';

  @override
  String get memoryDeleted => 'Anı Silindi';

  @override
  String get connectOmiDevice => 'Omi Cihazını Bağla';

  @override
  String get professionSoftwareEngineer => 'Yazılım Mühendisi';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'Bu konuşmacıdan diğer bölümleri etiketle ($selected/$total)';
  }

  @override
  String get productName => 'Ürün Adı';

  @override
  String get permissionDeniedForAppleReminders => 'Apple Hatırlatıcılar için izin reddedildi';

  @override
  String get allMemoriesAreNowPrivate => 'Tüm anılar artık özel';

  @override
  String planSetToCancelOn(String date) {
    return 'Planınız $date tarihinde iptal edilecek şekilde ayarlandı.\nAvantajlarınızı korumak için şimdi yeniden abone olun - $date tarihine kadar ücret yok.';
  }

  @override
  String get deletePersonTitle => 'Kişi silinsin mi?';

  @override
  String deleteItemConfirmation(String item) {
    return '$item silinir. Bu işlem geri alınamaz.';
  }

  @override
  String get appleHealthConnectCta => 'Apple Health\'e Bağlan';

  @override
  String segmentsPlural(String count) {
    return '$count segment';
  }

  @override
  String get syncCardDownloadingTitle => 'Cihazınızdan indiriliyor';

  @override
  String additionalSampleIndex(String index) {
    return 'Ek örnek $index';
  }

  @override
  String get descriptionLabel => 'Açıklama';

  @override
  String get failedToClearDueDate => 'Son tarih temizlenemedi';

  @override
  String get timeout4HoursDesc => '4 saat sessizlikten sonra konuşmayı sonlandır';

  @override
  String get noSyncedRecordingsYet => 'Henüz senkronize edilmiş kayıt yok';

  @override
  String dreamReportDropped(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count eski değişiklik atlandı',
      one: '1 eski değişiklik atlandı',
    );
    return '$_temp0';
  }

  @override
  String get claudeCode => 'Claude Code';

  @override
  String get noPendingRecordings => 'Bekleyen kayıt yok';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'Nasıl hitap edilmesini istediğinizi bize söyleyin. Bu, Omi deneyiminizi kişiselleştirmeye yardımcı olur.';

  @override
  String get updateSummaryWithNewNames => 'Özeti yeni adlarla güncelle';

  @override
  String get setWhenConversationsAutoEnd => 'Omi, bir konuşmayı sonlandırmadan önce sessizlikte ne kadar bekler';

  @override
  String get successfullyConnectedGoogleTasks => 'Google Tasks\'a başarıyla bağlanıldı!';

  @override
  String get confirmUpgrade => 'Yükseltmeyi Onayla';

  @override
  String get speechToTextProviderDesc => 'Transkripsiyon için kullanılan hizmeti seçin';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Apple Watch\'a bağlanırken hata: $error';
  }

  @override
  String get instagram => 'Instagram';

  @override
  String sampleNumber(int number) {
    return 'Örnek $number';
  }

  @override
  String get popularApps => 'Popüler Uygulamalar';

  @override
  String get micGainDescSlightlyBoosted => 'Hafif artırılmış - normal kullanım';

  @override
  String get promptMustBeAtLeast10Characters => 'İstem en az 10 karakter olmalıdır';

  @override
  String get chatAppsEntryRowSubtitle => 'Telegram, iMessage ve daha fazlası';

  @override
  String get estimatedSizeLabel => 'Tahmini Boyut';

  @override
  String get mcpServerDesc => 'Yapay zeka asistanlarını verilerinize bağlayın';

  @override
  String get disconnectHistory => 'Bağlantı Kesme Geçmişi';

  @override
  String get downgradeLimitDelay => '5-7 saniye gecikme';

  @override
  String get msgSelectImagesGenericError => 'Resim seçerken hata oluştu. Lütfen tekrar deneyin.';

  @override
  String get audioPlaybackUnavailable => 'Ses dosyası oynatma için mevcut değil';

  @override
  String get byClickingConnectNow => '\"Şimdi Bağlan\"a tıklayarak kabul etmiş olursunuz';

  @override
  String get signalStrength => 'Sinyal Gücü';

  @override
  String get tellUsPrimaryLanguage => 'Bize ana dilinizi söyleyin';

  @override
  String get diagnosticsShareFailed => 'Tanılama paylaşılamadı. Lütfen tekrar deneyin.';

  @override
  String get createKeyToStart => 'Başlamak için bir anahtar oluşturun';

  @override
  String generatedBy(String appName) {
    return '$appName tarafından oluşturuldu';
  }

  @override
  String shareStatsListened(String minutes) {
    return '🎧 $minutes dakika dinledi';
  }

  @override
  String get getOmiDevice => 'Omi Cihazı Edinin';

  @override
  String get newTask => 'Yeni görev';

  @override
  String get conversationPrompt => 'Konuşma İstemi';

  @override
  String get otaWifiConnected => 'Wi-Fi\'a bağlandı';

  @override
  String get dismiss => 'Gizle';

  @override
  String get webhooks => 'Webhook\'lar';

  @override
  String get raybanMetaCamera => 'Kamera';

  @override
  String get recapRegenerateNoConversations => 'Bu gün için özetlenecek konuşma bulunamadı.';

  @override
  String pendantMinutesStored(int minutes) {
    return '~$minutes dk kayıtlı';
  }

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName bağlantısı kesildi';
  }

  @override
  String get normal => 'Normal';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch hala erişilebilir değil. Lütfen Omi uygulamasının saatinizde açık olduğundan emin olun.';

  @override
  String get connectionGuide => 'Bağlantı Rehberi';

  @override
  String get syncStepProcessDesc => 'Omi sesi bir konuşmaya dönüştürür';

  @override
  String get couldNotLoadPlans => 'Mevcut planlar yüklenemedi. Lütfen tekrar deneyin.';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return 'Bu ay $limit dakikadan $used kullanıldı';
  }

  @override
  String get learnMoreLink => 'daha fazla bilgi';

  @override
  String get unpairDeviceDialogMessage =>
      'Bu, cihazın başka bir telefona bağlanabilmesi için eşleştirmesini kaldıracaktır. İşlemi tamamlamak için Ayarlar > Bluetooth\'a gitmeniz ve cihazı unutmanız gerekecek.';

  @override
  String get authFailedToRetrieveToken => 'Firebase jetonu alınamadı, lütfen tekrar deneyin.';

  @override
  String get aiGenFailedToCreateApp => 'Uygulama oluşturulamadı';

  @override
  String get appAndDeviceCopied => 'Uygulama ve cihaz detayları kopyalandı';

  @override
  String get noProcessedRecordings => 'Henüz işlenmiş kayıt yok';

  @override
  String get transcriptTab => 'Transkript';

  @override
  String get permissionDescReadConversations => 'Bu uygulama konuşmalarınıza erişebilir.';

  @override
  String get tryAnotherApp => 'Başka Bir Uygulama Deneyin';

  @override
  String get subscriptionSetToCancel => 'Aboneliğiniz dönem sonunda iptal edilecek şekilde ayarlandı.';

  @override
  String chatAppsCodeExpiresIn(String time) {
    return 'Kodun süresi $time içinde doluyor';
  }

  @override
  String get authFailedToSignInWithApple => 'Apple ile giriş yapılamadı, lütfen tekrar deneyin.';

  @override
  String get feedbackReasonIgnoredInstructions => 'Talimatlara uymadı';

  @override
  String get startupFailedDetails => 'Ayrıntılar';

  @override
  String get deleteMeetingScreenshotTitle => 'Ekran görüntüsü silinsin mi?';

  @override
  String get chatAppsNotConnectedMessage => 'Bu sohbet uygulamasının bağlantısı kesildi.';

  @override
  String get aboutOmiApiKeys => 'Omi API Anahtarları Hakkında';

  @override
  String get tiktok => 'TikTok';

  @override
  String get maxFilesLimit => 'Aynı anda en fazla 4 dosya yükleyebilirsiniz';

  @override
  String get legalNotice =>
      'Yasal Uyarı: Ses verilerini kaydetme ve saklama yasallığı bulunduğunuz yere ve bu özelliği nasıl kullandığınıza bağlı olarak değişebilir. Yerel yasalara ve düzenlemelere uyumu sağlamak sizin sorumluluğunuzdur.';

  @override
  String get wrappedYourTopDays => 'En iyi günleriniz';

  @override
  String get addMcpServer => 'MCP sunucusu ekle';

  @override
  String publicAppsCount(String count) {
    return 'Herkese Açık Uygulamalar ($count)';
  }

  @override
  String get noExternalAppsHaveAccess => 'Hiçbir harici uygulama verilerinize erişemiyor.';

  @override
  String get captureStarting => 'Başlatılıyor…';

  @override
  String get downloadingAudioProgress => 'Ses İndiriliyor';

  @override
  String get audioBytes => 'Ses Baytları';

  @override
  String batteryLevelSemantics(int level) {
    return 'Pil %$level';
  }

  @override
  String captureRecordedBy(String devices) {
    return 'Kaydeden: $devices';
  }

  @override
  String get chatAppsRepliesOnlyNote => 'Omi yalnızca sana yanıt verir. Asla ilk mesajı o atmaz.';

  @override
  String get hideTranscript => 'Transkripti Gizle';

  @override
  String get permissionReadConversations => 'Konuşmaları Oku';

  @override
  String get installed => 'Yüklendi';

  @override
  String get paymentEnterValidAmount => 'Geçerli bir tutar girin';

  @override
  String get sttLanguageOverride => 'Değiştir';

  @override
  String get appInterfaceSectionTitle => 'Uygulama arayüzü';

  @override
  String get searchLanguages => 'Dil ara';

  @override
  String get otherSource => 'Diğer';

  @override
  String get pairingDescOmiGlass => 'Açmak için yan düğmeyi 3 saniye basılı tutun.';

  @override
  String get signOut => 'Çıkış Yap';

  @override
  String shareStatsWords(String words) {
    return '🧠 $words kelime anladı';
  }

  @override
  String verifiedDaysAgo(int days) {
    return '${days}g once dogrulandi';
  }

  @override
  String get captureModeLater => 'Sonra';

  @override
  String get enableMoreApps => 'Daha Fazla Uygulama Etkinleştir';

  @override
  String get frequencyDescBalanced => 'Yararlı öneriler, günde yaklaşık 5–8';

  @override
  String get startYourFirstRecording => 'İlk kaydınızı başlatın';

  @override
  String get transcriptionPausedReconnecting => 'Hâlâ kaydediyor — transkripsiyona yeniden bağlanıyor…';

  @override
  String get basicPlan => 'Ücretsiz Plan';

  @override
  String get user => 'Kullanıcı';

  @override
  String get pinPersonDescription =>
      'Sabitlenen kişiler Kişiler listenizin en üstünde kalır ve Temizle ile kaldırılmaz.';

  @override
  String get reviewProject => 'Proje';

  @override
  String get keyboardShortcuts => 'Klavye Kısayolları';

  @override
  String get diagnosticsFailBadge => 'Başarısız';

  @override
  String get debugLogCleared => 'Hata ayıklama günlüğü temizlendi';

  @override
  String get errorConnectingToStripe => 'Stripe\'a bağlanırken hata! Lütfen daha sonra tekrar deneyin.';

  @override
  String get tapPlusToStartRecording => 'Kaydı başlatmak için kayıt düğmesine dokunun';

  @override
  String get permissionBlockedHint => 'Ayarlar\'da kapalı. Kullanmak için oradan izin verin.';

  @override
  String get downloadingAudio => 'Ses indiriliyor…';

  @override
  String failedToRevokeApiKey(String error) {
    return 'API anahtarı iptal edilemedi: $error';
  }

  @override
  String largeTimeGapDetected(String gap) {
    return 'Büyük zaman farkı tespit edildi ($gap)';
  }

  @override
  String get customFirmwareWarning =>
      'Özel yazılım cihazınızı kullanılamaz hale getirebilir. Geçerli bir Omi yazılım sürümü olduğundan emin olun ve güncelleme sırasında bağlantıyı kesmeyin.';

  @override
  String get wrapped2025 => '2025 Özeti';

  @override
  String get showApiKey => 'API Anahtarını Göster';

  @override
  String get agreeAndContinue => 'Kabul Et ve Devam Et';

  @override
  String get connectExternalAiTools => 'Harici yapay zeka araçlarını bağla';

  @override
  String get batteryFullyChargedTitle => 'Omi tamamen şarj oldu';

  @override
  String get appReEnableFailedTitle => 'Yeniden etkinleştirilemedi';

  @override
  String get onboardingYourName => 'Adınız';

  @override
  String get searchApps => 'Uygulama ara';

  @override
  String get weak => 'Zayıf';

  @override
  String get tellUsMore => 'Daha fazla anlatın (isteğe bağlı)';

  @override
  String confidenceReasonPicked(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count öneride seçildi',
      one: '1 öneride seçildi',
    );
    return '$_temp0';
  }

  @override
  String chatAppsDisconnectFooter(String app) {
    return 'Bağlantıyı kesmek, Omi\'nin $app için tuttuğu geçmişi siler.';
  }

  @override
  String get selectAll => 'Tümünü seç';

  @override
  String get deleteActionItemConfirmation => 'Bu görev silinsin mi? Bu işlem geri alınamaz.';

  @override
  String get categoryTravel => 'Seyahat';

  @override
  String get lowestRating => 'En düşük puan';

  @override
  String get tasksEmptyStateMessage => 'Görev oluşturmak için bir konuşma başlatın.';

  @override
  String get unpairAndForget => 'Eşleştirmeyi Kaldır ve Cihazı Unut';

  @override
  String get listeningForAudio => 'Ses dinleniyor…';

  @override
  String get processedStatus => 'İşlendi';

  @override
  String get wrappedTheHardPart => 'Zor Kısım';

  @override
  String chatAppsReplyThereAnytime(String app) {
    return '$app üzerinden istediğin zaman Omi\'ye mesaj at.';
  }

  @override
  String get upgradePlan => 'Planı yükselt';

  @override
  String get onboardingRatingPromptYes => 'Evet';

  @override
  String timeCompactMins(int count) {
    return '${count}dk';
  }

  @override
  String get changeTheConversationTitle => 'Sohbet başlığını değiştir';

  @override
  String get accountGroup => 'Hesap';

  @override
  String get updatingYourApp => 'Uygulamanız güncelleniyor';

  @override
  String get microphone => 'Mikrofon';

  @override
  String get suggestQuestionsAfterConversations => 'Konuşmalardan sonra sorular önerin';

  @override
  String get failedToTranscribeAudio => 'Ses transkribe edilemedi';

  @override
  String get unstarConversation => 'Konuşmanın yıldızını kaldır';

  @override
  String get speakerTagPromptNotMe => 'Ben değilim';

  @override
  String get confidenceReasonCorrected => 'Eşleşmesini düzelttiniz';

  @override
  String get peopleSearchPlaceholder => 'Kişi ara';

  @override
  String get syncStatusUnsupportedAudio => 'Ses okunamadı — eşitlenemiyor';

  @override
  String get indentTask => 'Girinti ekle';

  @override
  String get selectApp => 'Uygulama Seç';

  @override
  String get updatePayPal => 'PayPal\'ı Güncelle';

  @override
  String get enterNameError => 'Lütfen adınızı girin';

  @override
  String get exportAllData => 'Tüm Verileri Dışa Aktar';

  @override
  String premiumMinsLeft(int count) {
    return '$count premium dakika kaldı.';
  }

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName varsayılan özet uygulaması olarak ayarlandı';
  }

  @override
  String get recordingStartedSuccessfully => 'Kayıt başarıyla başladı!';

  @override
  String get trySomethingLike => 'Şöyle bir şey deneyin…';

  @override
  String get chatAppsTryAsking => 'Şunu sormayı dene';

  @override
  String get categoryEntertainment => 'Eğlence';

  @override
  String get checksForAudioFiles => 'SD Karttaki ses dosyalarını kontrol eder';

  @override
  String get everyoneHeader => 'Herkes';

  @override
  String get clearMemoryButton => 'Belleği Temizle';

  @override
  String confidenceReasonLabeled(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count kez etiketlediniz',
      one: 'Bir kez etiketlediniz',
    );
    return '$_temp0';
  }

  @override
  String get selectLogFile => 'Günlük Dosyası Seç';

  @override
  String get chatAppsTelegramStepReturn => 'Buraya geri dön. Çalıştığını onaylayacağız.';

  @override
  String get discordMemberCount => 'Discord\'da 8000\'den fazla üye';

  @override
  String get public => 'Herkese açık';

  @override
  String get outdentTask => 'Girintiyi azalt';

  @override
  String get statusProcessing => 'İşleniyor';

  @override
  String get useFreePlan => 'Ücretsiz Planı Kullan';

  @override
  String get emailLabel => 'E-posta';

  @override
  String get statusCallInProgress => 'Arama devam ediyor';

  @override
  String get shortcuts => 'Kısayollar';

  @override
  String get reviewRecentChanges => 'Son değişiklikler';

  @override
  String get raybanMetaAudioOnlyExplanation =>
      'Omi\'nin bu sürümü gözlüğünüzün mikrofonunu Bluetooth üzerinden kullanabilir. Fotoğraf çekimi için Omi\'nin Meta geliştirici sürümü gerekir.';

  @override
  String get wrappedDaysActiveLabel => 'aktif gün';

  @override
  String get installOmiOnAppleWatch => 'Apple Watch\'unuza\nOmi yükleyin';

  @override
  String tasksCountLabel(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count görev',
      one: '1 görev',
    );
    return '$_temp0';
  }

  @override
  String get confidenceReasonVoiceReady => 'ses kaydedildi';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return '$count seçili görev$s silinsin mi?';
  }

  @override
  String get sdCardSync => 'SD Kart Senkronizasyonu';

  @override
  String get timeout4Hours => '4 saat';

  @override
  String get chatAppsTitle => 'Sohbet Uygulamaları';

  @override
  String get repeatPasswordLabel => 'Şifreyi Tekrarla';

  @override
  String get skip => 'Atla';

  @override
  String get phoneNoVerifiedNumbersTitle => 'Doğrulanmış Numara Yok';

  @override
  String get connectionLost => 'Bağlantı Kesildi';

  @override
  String get photoDiscardedMessage => 'Bu fotoğraf önemli olmadığı için silindi.';

  @override
  String get weekdayFri => 'Cum';

  @override
  String get moveToFolder => 'Klasöre Taşı';

  @override
  String get updateNow => 'Şimdi Güncelle';

  @override
  String get failedToUpdateActionItem => 'Görev güncellenemedi';

  @override
  String get transferRequiredDescription =>
      'Bu kayıt cihazınızın SD kartında depolanıyor. Çalmak veya paylaşmak için telefonunuza aktarın.';

  @override
  String get checkingForUpdates => 'Güncellemeler kontrol ediliyor';

  @override
  String get importTranscriptFilesDescription =>
      'SRT, VTT veya TXT transkriptlerini ya da bunları içeren bir ZIP dosyasını seçin';

  @override
  String get listenToSpeechProfile => 'Ses profilimi dinle ➡️';

  @override
  String get deleteRecapConfirmBody => 'Bu özet kalıcı olarak kaldırılacak. O güne ait orijinal sohbetler etkilenmez.';

  @override
  String get copyLogs => 'Günlükleri Kopyala';

  @override
  String get wrappedFunniestMoment => 'En Komik';

  @override
  String get onboardingMicrophoneRequired => 'Kayıt için mikrofon izni gereklidir.';

  @override
  String get whoIsItTitle => 'Bu Kim?';

  @override
  String dreamReportRunsLeft(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Bugün $count manuel çalıştırma hakkı kaldı',
      one: 'Bugün 1 manuel çalıştırma hakkı kaldı',
    );
    return '$_temp0';
  }

  @override
  String get modified => 'Değiştirildi';

  @override
  String get actionCreateConversations => 'Konuşma oluştur';

  @override
  String get chatAssistantsTitle => 'Sohbet Asistanları';

  @override
  String get connectionError => 'Bağlantı Hatası';

  @override
  String get chooseFromGallery => 'Galeriden seç';

  @override
  String get summaryPrompt => 'Özet Promptu';

  @override
  String get whatWentWrong => 'Ne ters gitti?';

  @override
  String get keepGoingGreat => 'Devam et, harika gidiyorsun';

  @override
  String get deviceConnecting => 'Bağlanıyor…';

  @override
  String get downgradeLimitBattery => '7 kat pil tüketimi';

  @override
  String get privateMemories => 'Özel anılar';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get aiGenPleaseEnterDescription => 'Lütfen uygulamanız için bir açıklama girin';

  @override
  String get enterLiveSttWebsocket => 'Canlı STT WebSocket uç noktanızı girin';

  @override
  String processingOnServerProgress(int current, int total) {
    return 'İşleniyor… $current/$total segment';
  }

  @override
  String linkedToEvent(String title) {
    return '\"$title\" etkinliğine bağlandı';
  }

  @override
  String get failedToSaveCheckConnection => 'Kaydetme başarısız. Lütfen bağlantınızı kontrol edin.';

  @override
  String get deviceOnboardingContinue => 'Devam Et';

  @override
  String get pairedToAnotherPhone => 'Başka bir telefona eşleştirildi';

  @override
  String get syncingYourRecordings => 'Kayıtlarınız senkronize ediliyor';

  @override
  String get manual => 'Manuel';

  @override
  String get oneMonthAgo => '1 ay önce';

  @override
  String get clearChatConfirm => 'Bu sohbetteki tüm mesajlar silinir. Bu işlem geri alınamaz.';

  @override
  String revokeKeyConfirmation(String keyName) {
    return '\"$keyName\" anahtarını kullanan her şey erişimini kaybeder. Bu işlem geri alınamaz.';
  }

  @override
  String get vadGateDescription => 'Maliyeti düşürmek için transkripsiyondan önce sessiz sesleri atlar.';

  @override
  String get dreamReportScheduled => 'Zamanlanmış';

  @override
  String get audioDataReceived => 'Ses verisi alındı';

  @override
  String get pro => 'Pro';

  @override
  String get micGainDescMuted => 'Mikrofon sessize alındı';

  @override
  String get enableLocationDescription => 'Yakındaki Bluetooth cihazlarını bulmak için konum izni gereklidir.';

  @override
  String get conversationTitleUpdatedSuccessfully => 'Sohbet başlığı başarıyla güncellendi';

  @override
  String get syncStepUpload => 'Eşitle';

  @override
  String get removeScreenshot => 'Ekran görüntüsünü kaldır';

  @override
  String get failedToStartCall => 'Arama baslatılamadi';

  @override
  String get deviceDiagnosticsUploadDescription =>
      'Review the diagnostics JSON below. It includes your device identifier, connection history, battery readings, firmware diagnostics, and BLE events. No audio or transcripts are included.';

  @override
  String get pairingTitleFieldy => 'Fieldy\'yi Eşleştirme Moduna Alın';

  @override
  String get autoDeletesAfterThreeDays => '3 gün sonra otomatik silinir.';

  @override
  String get wrappedDaysActive => 'aktif gün';

  @override
  String get failedToDeleteActionItem => 'Görev silinemedi';

  @override
  String get connect => 'Bağlan';

  @override
  String get unableToDeleteConversation => 'Konuşma Silinemiyor';

  @override
  String get clearChatAction => 'Sohbeti temizle';

  @override
  String get memoryThisIphone => 'Bu iPhone';

  @override
  String get captureCustomSttUnreachableDetail =>
      'Özel konuşmadan metne hizmetine ulaşılamıyor. Omi sesi bu telefonda tutar ve hizmet geri geldiğinde gönderir. Hiçbir şey kaybolmaz.';

  @override
  String get feedbackGiveFeedback => 'Geri bildirim ver';

  @override
  String failedToUpdateSettings(String error) {
    return 'Ayarlar güncellenemedi: $error';
  }

  @override
  String get deleteRecordingConfirmation => 'Bu işlem geri alınamaz.';

  @override
  String get advancedSettings => 'Gelişmiş Ayarlar';

  @override
  String get transcriptionNoAudio => 'Transkripsiyon ses almıyor';

  @override
  String deletePeopleCountAction(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count Kişiyi Sil',
      one: '1 Kişiyi Sil',
    );
    return '$_temp0';
  }

  @override
  String get speakerSuggestionAppliesToSpeaker => 'Bu konuşmacının tüm satırlarına uygulanır';

  @override
  String get deviceNotResponding => 'Cihaz yanıt vermedi. Lütfen tekrar deneyin.';

  @override
  String get everythingSynced => 'Her şey zaten senkronize edilmiş.';

  @override
  String get onDeviceModelDownloadFailedDesc => 'Whisper modeli indirilemedi. Lütfen tekrar deneyin.';

  @override
  String fairUseBannerStatus(String status) {
    return 'Adil Kullanım: $status';
  }

  @override
  String tasksDeleteSelected(int count) {
    return '$count görevi sil';
  }

  @override
  String get connectPaymentMethodInfo =>
      'Uygulamalarınız için ödeme almaya başlamak için aşağıdan bir ödeme yöntemi bağlayın.';

  @override
  String get conversationNotFoundOrDeleted => 'Konuşma bulunamadı veya silindi';

  @override
  String leaveFlowStepOf(int current, int total) {
    return 'Adım $current/$total';
  }

  @override
  String get deleteTypeToConfirm => 'Onaylamak için DELETE yazın';

  @override
  String get clearMemoryTitle => 'Omi\'nin Hafızasını Temizle';

  @override
  String get triggerConversationCreation => 'Konuşma Oluşturma';

  @override
  String get flashCustomFirmware => 'Özel Yazılım Yükle';

  @override
  String shareWithContactCount(int count) {
    return '$count kişiyle paylaş';
  }

  @override
  String get customChatbotPersonality => 'Özel Chatbot Kişiliği';

  @override
  String get betaTesterNotice =>
      'Bu uygulamanın beta test kullanıcısısınız. Henüz herkese açık değil. Onaylandıktan sonra herkese açık olacak.';

  @override
  String get tomorrow => 'Yarın';

  @override
  String get createdLabel => 'OLUŞTURULDU';

  @override
  String get searchPeople => 'Kişi ara';

  @override
  String get cancelled => 'İptal edildi';

  @override
  String basicPlanDesc(int limit) {
    return 'Planınız ayda $limit ücretsiz dakika içerir. Sınırsız kullanım için yükseltin.';
  }

  @override
  String get editMemoryTitle => 'Anıyı Düzenle';

  @override
  String get whatDoYouWantToKnow => 'Ne bilmek istersin?';

  @override
  String get confidenceFootnote =>
      'Sizin yaptığınız etiketler ve onaylar en çok ağırlığa sahiptir. Otomatik etiketler, siz onaylayana kadar pek bir şey ifade etmez.';

  @override
  String get exportFailedTryAgain => 'Dışa aktarma başarısız oldu. Lütfen tekrar deneyin.';

  @override
  String get addAppPhotosPermissionDenied => 'Fotoğraf izni reddedildi. Fotoğraflara erişime izin verin';

  @override
  String get filterByDate => 'Tarihe göre filtrele';

  @override
  String get chatAppsDoesFiles => 'Dosya, fotoğraf ve sesli not gönderir ve alır';

  @override
  String get deleteKnowledgeGraphTitle => 'Bilgi Grafiği Silinsin mi?';

  @override
  String get reloadingConversations => 'Konuşmalar yeniden yükleniyor…';

  @override
  String get aiGenPleaseGenerateAppFirst => 'Lütfen önce bir uygulama oluşturun';

  @override
  String get completeYourUpgrade => 'Yükseltmenizi Tamamlayın';

  @override
  String get capturePendantDisconnectedDetail =>
      'Kolyenin bu telefonla bağlantısı kesildi. Kolye açık ve yakındayken Omi kendiliğinden yeniden bağlanır. Bundan önce kaydedilen her şey güvende.';

  @override
  String get greetingMorning => 'Günaydın';

  @override
  String get thanksForYourFeedback => 'Geri bildiriminiz için teşekkürler!';

  @override
  String get deleteActionItemConfirmMessage => 'Bu görev silinsin mi?';

  @override
  String get syncCardProcessing => 'Omi\'de işleniyor…';

  @override
  String get chatAppsTryWeek => 'Haftamı üç satırda özetle';

  @override
  String get recordWithPhoneMicSubtitle => 'Bu telefonun mikrofonuyla kaydedin ve yazıya dökün';

  @override
  String get notifications => 'Bildirimler';

  @override
  String get annualPlanStartsAutomatically =>
      'Aylık planınız sona erdiğinde yıllık planınız otomatik olarak başlayacak.';

  @override
  String get unpairDialogMessage =>
      'Bu, cihazın eşleştirilmesini kaldıracak ve başka bir telefona bağlanabilecek. İşlemi tamamlamak için Ayarlar > Bluetooth\'a gidip cihazı unutmanız gerekecek.';

  @override
  String get pairingTitleBee => 'Bee\'yi Eşleştirme Moduna Alın';

  @override
  String conversationCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count konuşma',
      one: '1 konuşma',
    );
    return '$_temp0';
  }

  @override
  String get syncStatusWaiting => 'Eşitleme bekleniyor';

  @override
  String get validWebsocketUrlRequired => 'Geçerli WebSocket URL\'si gereklidir (wss://)';

  @override
  String get improveSpeechProfile => 'Konuşma Profilinizi Geliştirin';

  @override
  String entityWaitingOn(String name) {
    return '$name bekleniyor';
  }

  @override
  String get feedbackReasonTooVerbose => 'Fazla uzun';

  @override
  String chatAppsChannelFooter(String app) {
    return '$app sohbetlerin $app içinde kalır. Omi yine de uygulamada ve diğer sohbet uygulamalarında neler konuştuğunu bilir.';
  }

  @override
  String get wrappedNoDataAvailable => 'Veri mevcut değil';

  @override
  String deviceOnboardingAllSetReplayHint(String settings, String deviceSettings, String deviceTutorial) {
    return 'Bu turu istediğiniz zaman $settings › $deviceSettings › $deviceTutorial\'da tekrar oynatın';
  }

  @override
  String get createAKey => 'Anahtar Oluştur';

  @override
  String get successfullyConnectedNotion => 'Notion\'a başarıyla bağlanıldı!';

  @override
  String get captureMicInterruptedDetail =>
      'Bir arama veya başka bir uygulama mikrofonu aldı, bu yüzden Omi şu an duyamıyor. Mikrofon boşalınca Omi kendiliğinden devam eder. Bundan önce kaydedilen her şey güvende.';

  @override
  String get onboardingScreenCaptureDenied =>
      'Ekran yakalama izni reddedildi. Lütfen Sistem Tercihleri > Gizlilik ve Güvenlik > Ekran Kaydı\'nda izin verin.';

  @override
  String get settingUp => 'Kuruluyor…';

  @override
  String get frequencyLow => 'Düşük';

  @override
  String get sttFilterAuto => 'Otomatik';

  @override
  String get voiceQuestionNoSpeech => 'Anlayamadım — tekrar deneyin';

  @override
  String get stripeRecommendation =>
      'Stripe ülkenizde mevcutsa, daha hızlı ve kolay ödemeler için kullanmanızı şiddetle tavsiye ederiz.';

  @override
  String get confirmed => 'Onaylandı!';

  @override
  String get deletePendingFilesWarning =>
      'Bu kayıtlar telefonunuzla senkronize EDİLMEDİ ve kalıcı olarak kaybolacak. Bu geri alınamaz.';

  @override
  String get removeFilter => 'Filtreyi Kaldır';

  @override
  String get downloadModel => 'Modeli indir';

  @override
  String get performanceReduced => 'Performans düşük olabilir';

  @override
  String get hostRequired => 'Host gereklidir';

  @override
  String get alreadyBestValuePlan => 'Zaten en iyi değerli plana sahipsiniz. Değişiklik gerekmiyor.';

  @override
  String preparingModel(String model) {
    return '$model hazırlanıyor…';
  }

  @override
  String get sendTranscript => 'Transkript gönder';

  @override
  String get howItWorksTitle => 'Nasıl çalışır?';

  @override
  String get filterBySpeaker => 'Konuşmacıya göre filtrele';

  @override
  String get addAppSubmittedSuccess => 'Uygulama başarıyla gönderildi 🚀';

  @override
  String olderIphoneModelDetected(String model) {
    return 'Algılanan model: $model (iPhone XS\'ten eski). Cihaz üzerinde tanıma daha yavaş olabilir.';
  }

  @override
  String get chatAppsWhatsAppTitle => 'WhatsApp geliyor';

  @override
  String get syncingDeveloperSettings => 'Geliştirici ayarları senkronize ediliyor…';

  @override
  String get enterWifiPassword => 'WiFi şifresini girin';

  @override
  String get failedToUpdateBaselineStatus => 'Bu anı güncellenemedi. Tekrar deneyin.';

  @override
  String get joinCommunity => 'Topluluğa katılın!';

  @override
  String get helpOrInquiries => 'Yardım veya sorularınız mı var?';

  @override
  String get enable => 'Etkinleştir';

  @override
  String get deviceForgottenMessage => 'Cihaz unutuldu';

  @override
  String diagnosticsSincePairingSummary(int drops, int failed) {
    return 'Eşleştirmeden beri: $drops kopma, $failed başarısız bağlantı.';
  }

  @override
  String confidenceSummaryConfirmed(String name) {
    return 'Omi, $name kişisinin sesini tanıyor ve siz bunu onayladınız.';
  }

  @override
  String migratingToProtection(String level) {
    return '$level korumaya geçiliyor…';
  }

  @override
  String get managePlan => 'Planı Yönet';

  @override
  String get synced => 'Senkronize edildi';

  @override
  String get failedToMoveConversations => 'Konuşmalar taşınamadı';

  @override
  String get monthMar => 'Mar';

  @override
  String get timePM => 'ÖS';

  @override
  String get debugLogsAutoDelete => '3 gün sonra otomatik olarak silinir.';

  @override
  String get linkedIn => 'LinkedIn';

  @override
  String speakerLabelVoiceDetail(String state, String name) {
    String _temp0 = intl.Intl.selectLogic(
      state,
      {
        'learned': 'Omi bir dahaki sefere $name kişisini tanıyacak.',
        'pending': 'Bu birkaç saniye sürer.',
        'disabled': 'Omi $name kişisini tanıyabilsin diye Ayarlar’da ses kaydetmeyi açın.',
        'other': 'Omi, $name kişisinin daha net konuşmasına ihtiyaç duyuyor ve denemeye devam edecek.',
      },
    );
    return '$_temp0';
  }

  @override
  String get authUnexpectedError => 'Giriş yaparken beklenmeyen hata, lütfen tekrar deneyin';

  @override
  String disconnectAppMessage(String appName) {
    return '$appName bağlantısını istediğiniz zaman yeniden kurabilirsiniz.';
  }

  @override
  String get pendantPausedResumesWhenYouFinish => 'Kolye duraklatıldı · bitirdiğinde devam eder';

  @override
  String get sendToSupport => 'Send to support';

  @override
  String get fairUseBudgetExhausted => 'Günlük transkripsiyon limiti doldu';

  @override
  String evidenceAutoConfirmed(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count otomatik etiketi onayladınız',
      one: '1 otomatik etiketi onayladınız',
    );
    return '$_temp0';
  }

  @override
  String get otaWifiConnecting => 'Wi-Fi\'a bağlanıyor…';

  @override
  String starFilterLabel(int count) {
    return '$count yıldız';
  }

  @override
  String get disconnectDevice => 'Cihaz Bağlantısını Kes';

  @override
  String get installsCount => 'Yüklemeler';

  @override
  String captureStatusWithSource(String status, String source) {
    return '$status · $source';
  }

  @override
  String get pairingTitleOmiGlass => 'Omi Glass\'ı Açın';

  @override
  String get setActive => 'Aktif Olarak Ayarla';

  @override
  String get showShortConversations => 'Kısa Konuşmaları Göster';

  @override
  String get reviewNotSure => 'Emin değilim';

  @override
  String msgCameraAccessError(String error) {
    return 'Kameraya erişim hatası: $error';
  }

  @override
  String get quickActionAskOmi => 'Omi\'ye her şeyi sorun';

  @override
  String get dreamReportTimedOut => 'Süre sınırında durdu';

  @override
  String get chooseYourLanguage => 'Dilinizi seçin';

  @override
  String get unableToDetermineFirmwareVersion => 'Mevcut donanım yazılımı sürümü belirlenemiyor';

  @override
  String get addAppEnterConversationPrompt => 'Uygulamanız için bir konuşma istemi girin';

  @override
  String get readScope => 'Okuma';

  @override
  String get selectALanguage => 'Bir dil seçin';

  @override
  String get otherTemplates => 'Diğer Şablonlar';

  @override
  String get speechProfileTopicGoal => 'Uzun vadeli hedefiniz nedir?';

  @override
  String get rayBanMetaMicPickerTitle => 'Ray-Ban Meta mikrofonunuzu seçin';

  @override
  String meetingNotesSubject(String title) {
    return 'Notlar: $title';
  }

  @override
  String get feedbackTitleMissingFeatures => 'Hangi özellikleri kaçırıyorsunuz?';

  @override
  String get modelReady => 'Model Hazır';

  @override
  String todayAtTime(String time) {
    return 'Bugün saat $time';
  }

  @override
  String get deleteAccountPermanently => 'Hesabı kalıcı olarak sil';

  @override
  String get updateStripeDetails => 'Stripe Bilgilerini Güncelle';

  @override
  String get voiceResponseHeadphonesOnly => 'Sadece kulaklık';

  @override
  String get deviceOnboardingEndConversation => 'Konuşmayı Bitir';

  @override
  String openingApp(String appName) {
    return '$appName açılıyor…';
  }

  @override
  String get submitAppPublicDescription =>
      'Uygulamanız incelenecek ve herkese açık hale getirilecek. İnceleme sırasında bile hemen kullanmaya başlayabilirsiniz!';

  @override
  String connectToAppTitle(String appName) {
    return '$appName\'e Bağlan';
  }

  @override
  String get timeout10MinutesDesc => '10 dakika sessizlikten sonra konuşmayı sonlandır';

  @override
  String get googleCalendar => 'Google Takvim';

  @override
  String get initializing => 'Başlatılıyor…';

  @override
  String get noMessagesYet => 'Henüz mesaj yok!\nNeden bir konuşma başlatmıyorsunuz?';

  @override
  String get chatAppsLoadFailed => 'Sohbet uygulamaları yüklenemedi. Lütfen tekrar deneyin.';

  @override
  String get tasksLater => 'Daha sonra';

  @override
  String get speakerLabelUnknown => 'Bilinmiyor';

  @override
  String get appTitle => 'Omi';

  @override
  String get noModelDownloadRequired => 'Cihazınızın yerel konuşma motoru kullanılacak. Model indirmesi gerekmiyor.';

  @override
  String get authenticationFailed => 'Kimlik doğrulama başarısız. Lütfen tekrar deneyin.';

  @override
  String get defaultRepoSaved => 'Varsayılan depo kaydedildi';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'Küçük resim seçilirken hata: $error';
  }

  @override
  String get captureRecordingSeparateTitle => 'Bu kayıt ayrılsın mı?';

  @override
  String get back => 'Geri';

  @override
  String get preparingAudio => 'Ses Hazırlanıyor';

  @override
  String get noAutoMemories => 'Henüz otomatik çıkarılan anı yok';

  @override
  String get allDone => 'Hepsi tamam!';

  @override
  String get msgReadingMemories => 'Anılarınız okunuyor…';

  @override
  String get worksOnDesktop => 'Masaüstünde çalışır';

  @override
  String get displayOptions => 'Görüntüleme Seçenekleri';

  @override
  String get installApp => 'Uygulamayı yükle';

  @override
  String get stop => 'Durdur';

  @override
  String get grantPermissions => 'İzinleri ver';

  @override
  String get at => 'saat';

  @override
  String get checkInternetConnection => 'Lütfen internet bağlantınızı kontrol edin';

  @override
  String get actionItems => 'Görevler';

  @override
  String get nextDay => 'Sonraki gün';

  @override
  String get syncStatusFailed => 'Başarısız — Yeniden Dene\'ye dokunun';

  @override
  String get saveCredentials => 'Kimlik Bilgilerini Kaydet';

  @override
  String get peopleRecent => 'Yakınlarda';

  @override
  String get bringYourOwn => 'Kendininkini getir';

  @override
  String get cancelConsequenceBattery => '7 kat daha fazla pil tüketimi (cihazda işleme)';

  @override
  String get copyMessage => 'Mesajı kopyala';

  @override
  String get annualSubscriptionStarts => '12 aylık yıllık aboneliğiniz ödeme sonrasında otomatik olarak başlayacak';

  @override
  String get deleteImportedData => 'İçe Aktarılan Verileri Sil';

  @override
  String get chatLimitReachedUpgrade => 'Sohbet limiti doldu. Daha fazla mesaj için yükseltin.';

  @override
  String get whatsNew => 'Yenilikler';

  @override
  String get omiTraining => 'Omi Eğitimi';

  @override
  String get wrappedMyBuddies => 'Arkadaşlarım';

  @override
  String get keepRecording => 'Kayda Devam Et';

  @override
  String get suggestedEvent => 'Önerilen';

  @override
  String get name => 'Ad';

  @override
  String get screenRecordingDescription =>
      'Omi, tarayıcı tabanlı toplantılarınızdan sistem sesini yakalamak için ekran kaydı izni gerektirir.';

  @override
  String get improveConnectionTitle => 'Bağlantıyı İyileştir';

  @override
  String get syncProcessingBackgroundHint => 'Bu işlem arka planda sürer — bu ekrandan ayrılabilirsiniz.';

  @override
  String get wrappedYourTopDaysBadge => 'En iyi günlerin';

  @override
  String get noPeopleYet => 'Henüz Kişi Yok';

  @override
  String summaryGeneratedForDate(String date) {
    return '$date için özet oluşturuldu';
  }

  @override
  String get searchTranscriptOrSummary => 'Transkript veya özette ara';

  @override
  String get memoryDetailsTitle => 'Anı';

  @override
  String get chatPersonality => 'Sohbet Kişiliği';

  @override
  String get release => 'Bırak';

  @override
  String removeVocabularyWord(String word) {
    return '$word kaldır';
  }

  @override
  String get onboardingLanguage => 'Dil';

  @override
  String get wrappedYouDidItEmoji => 'Başardın! 🎉';

  @override
  String get syncInProgress => 'Eşitleme sürüyor';

  @override
  String get wrappedCouldntStopTalkingAbout => 'Hakkında konuşmayı bırakamadım';

  @override
  String get chooseSummarizationApp => 'Özet Uygulaması Seçin';

  @override
  String etaLabel(String time) {
    return 'Tahmini süre: $time';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return '$item herkese açık yaparsanız, herkes kullanabilir';
  }

  @override
  String get phoneCallsUpsellFeature2 => 'Otomatik arama özetleri ve görevler';

  @override
  String get freemiumLimitsIntro => 'Omi ücretsizdir, ancak ücretsiz sürümün deneyimini etkileyen sınırları vardır:';

  @override
  String get nameLabel => 'Ad';

  @override
  String get shortConversationThresholdSubtitle => 'Bundan kısa konuşmalar yukarıda etkinleştirilmedikçe gizlenecek';

  @override
  String get captureMicInUseElsewhere => 'Mikrofon başka bir uygulamada';

  @override
  String get selectChatAssistant => 'Sohbet Asistanı Seç';

  @override
  String get transferRequired => 'Aktarım Gerekli';

  @override
  String get unlimitedChatThisMonth => 'Bu ay sınırsız sohbet mesajı';

  @override
  String get backgroundModeUnavailable =>
      'Arka Plan Modu kullanılamıyor çünkü uyumlu bir cihaz bağlı değil. Bu özelliği kullanmak için bir Omi, OpenGlass veya Friend Pendant cihazı bağlayın.';

  @override
  String get importConfiguration => 'Yapılandırma İçe Aktar';

  @override
  String get e2eeTradeoff1 => '• Harici uygulama entegrasyonları gibi bazı özellikler devre dışı bırakılabilir.';

  @override
  String get chatAppsCodeExpiredTitle => 'Bu kodun süresi doldu';

  @override
  String get responseSchema => 'Yanıt Şeması';

  @override
  String get wrappedBestMoments => 'En iyi anlar';

  @override
  String get noAppsExternalAccess => 'Yüklü hiçbir uygulama verilerinize harici erişime sahip değil.';

  @override
  String modelReadyWithName(String model) {
    return 'Model Hazır ($model)';
  }

  @override
  String get appDisabledWebhookFailures =>
      'Uç noktası 72 saat boyunca üst üste başarısız oldu, bu yüzden gönderimler durduruldu.';

  @override
  String reviewConversationCount(int count) {
    return 'Konuşmalar: $count';
  }

  @override
  String get reviewChangesLoadFailed => 'Son değişiklikler yüklenemedi.';

  @override
  String get reviewOpenConversation => 'Konuşma';

  @override
  String get voiceRecordingFound => 'Kayıt bulundu';

  @override
  String durationAgo(String duration) {
    return '$duration önce';
  }

  @override
  String get onboardingWelcomeToOmi => 'Omi\'ye Hoş Geldiniz';

  @override
  String get deleteActionItemConfirmTitle => 'Görevi Sil';

  @override
  String get importantBillingInfo => 'Önemli Fatura Bilgileri:';

  @override
  String get pending => 'Beklemede';

  @override
  String get onboardingRatingPromptTitle => 'Omi\'yi beğeniyor musunuz?';

  @override
  String get savePayPalDetails => 'PayPal Bilgilerini Kaydet';

  @override
  String appDisabledLastError(String error) {
    return 'Son hata: $error.';
  }

  @override
  String get iveInstalledAndOpenedTheApp => 'Uygulamayı Yükledim ve Açtım';

  @override
  String get pricePlaceholder => '0,00';

  @override
  String get triggerTranscriptProcessed => 'Transkript İşlendi';

  @override
  String get decisions => 'Kararlar';

  @override
  String get conversationProcessingFailedMessage => 'Bu konuşma işlenemedi.';

  @override
  String get continueText => 'Devam Et';

  @override
  String get signInWithGoogle => 'Google ile Giriş Yap';

  @override
  String firmwareFlashTarget(String deviceName) {
    return 'Cihaz: $deviceName';
  }

  @override
  String get deleteYourAccountAndAllData => 'Hesabınızı ve tüm verilerinizi silin';

  @override
  String get provider => 'Sağlayıcı';

  @override
  String get people => 'Kişiler';

  @override
  String get perMonth => '/ Ay';

  @override
  String get monthFeb => 'Şub';

  @override
  String get fridayAbbr => 'Cum';

  @override
  String get thankYouForFeedback => 'Geri bildiriminiz için teşekkürler!';

  @override
  String get usageBestYear => 'Best year';

  @override
  String get addAppFillRequiredFields => 'Tüm gerekli alanları doğru şekilde doldurun';

  @override
  String get deviceOnboardingVoiceReplyOffDescription => 'Cevaplar ekranda kalır. Hiçbir şey konuşulmuyor.';

  @override
  String get logs => 'Günlükler';

  @override
  String get exportConversations => 'Konuşmaları dışa aktar';

  @override
  String get memoryReviewDropped => 'Anılarınızdan kaldırıldı.';

  @override
  String get appearanceLight => 'Açık';

  @override
  String get moneyEarned => 'Kazanılan para';

  @override
  String get permissionsAndTriggers => 'İzinler ve Tetikleyiciler';

  @override
  String get discardRecordingTitle => 'Kayıt silinsin mi?';

  @override
  String get wrappedMinutesLabel => 'dakika';

  @override
  String get voiceRestoredToast => 'Omi bu ses hakkında tekrar sorabilir';

  @override
  String get locationAccess => 'Konum erişimi';

  @override
  String get deleteAllMemories => 'Tüm Anıları Sil';

  @override
  String get deleteAccountTitle => 'Hesabı Sil';

  @override
  String get selectFile => 'Dosya Seç';

  @override
  String get answerTheCallFrom => 'Su numaradan gelen aramayi cevaplayin';

  @override
  String get unpairDeviceDialogTitle => 'Cihaz Eşleştirmesini Kaldır';

  @override
  String exportedToPlatform(String platform) {
    return '$platform uygulamasına aktarıldı';
  }

  @override
  String syncCardDownloadPercent(int percent) {
    return '$percent%';
  }

  @override
  String get deviceOnboardingVoiceReplyPreviewPlaying => 'Son cevabınız çalınıyor...';

  @override
  String get fromSd => 'SD\'den';

  @override
  String get goodSampleInstructions =>
      '1. Sessiz bir yerde olduğunuzdan emin olun.\n2. Net ve doğal bir şekilde konuşun.\n3. Cihazınızın boynunuzda doğal konumunda olduğundan emin olun.\n\nOluşturulduktan sonra her zaman geliştirebilir veya yeniden yapabilirsiniz.';

  @override
  String voiceIntroduction(String part) {
    String _temp0 = intl.Intl.selectLogic(
      part,
      {
        'title': 'Let Omi get to know you',
        'intro':
            'Finish four short sentences out loud. This helps Omi recognize your voice and remember what matters to you. Share only what you want.',
        'hint': 'Say the whole sentence and finish it in your own words.',
        'name': 'My name is ___, and I spend most of my time ___.',
        'work': 'Right now, I am working on ___.',
        'enjoy': 'Outside of that, I really enjoy ___.',
        'food': 'My favorite food is ___.',
        'remember': 'Something I would like help remembering is ___.',
        'day': 'A good day for me includes ___.',
        'another': 'Try Another Prompt',
        'start': 'Start Speaking',
        'skipPrompt': 'Skip Question',
        'captured': 'Voice sample captured',
        'silence': 'Take your time. Speak toward your phone microphone.',
        'audio': 'Audio detected',
        'review': 'Here is what I heard',
        'reviewHint': 'Uncheck anything you don\'t want saved.',
        'saveVoice': 'Save Voice Profile',
        'savingVoice': 'Saving your voice profile…',
        'savedVoice': 'Voice profile saved',
        'voiceLater': 'Set Up My Voice Later',
        'keep': 'Save Selected Answers',
        'without': 'Continue Without Saving Answers',
        'savedMemories': 'Your memories are saved',
        'short': 'We need a little more audio. Add one more sentence; your earlier answers are safe.',
        'addSample': 'Add Another Sentence',
        'uploadError': 'Your voice profile could not be saved. Retry with the same recording, or set it up later.',
        'memoryError': 'Some answers could not be saved. Saved items are safe; retry to save the rest.',
        'transcriptionError': 'We could not transcribe that answer. Try again, keep speaking, or skip this question.',
        'noMemories': 'You can tell Omi more about yourself whenever you like.',
        'voiceOnlyHint': 'You can skip any personal prompt and talk about something else.',
        'goalPrompt': 'Right now my number one goal is to ___.',
        'savedGoal': 'Your goal is saved',
        'goalError':
            'Your goal could not be saved. Retry to save the same goal without duplicating it. Any memories already saved are safe.',
        'goalLong': 'Shorten your goal to 500 characters or fewer, then try again.',
        'voiceUnavailable':
            'Voice setup is temporarily unavailable. Saved answers are safe. Retry, or continue and set up your voice later.',
        'saveFinish': 'Save and Finish',
        'retryRemaining': 'Retry Remaining',
        'saveHint': 'Saves your voice profile and checked answers.',
        'savedAll': 'Your introduction is saved.',
        'continueSaved': 'Continue With What Is Saved',
        'reviewAnswers': 'Review Answers',
        'originalGoal': 'Use Original Wording',
        'savingAnswers': 'Saving your answers…',
        'other': '',
      },
    );
    return '$_temp0';
  }

  @override
  String get starConversationHint =>
      'Bir konuşmayı favorilere eklemek için açın ve üst kısımdaki yıldız simgesine dokunun.';

  @override
  String get pairingTitleOmiDevkit => 'Omi DevKit\'i Eşleştirme Moduna Alın';

  @override
  String sttPrimaryLanguageUnsupported(String language, String fallback) {
    return 'Bu sağlayıcı $language dilini desteklemiyor, bu yüzden $fallback kullanılıyor.';
  }

  @override
  String get premiumMinutesMonth =>
      'Ayda 300 premium dakika. Sınırsız ücretsiz transkripsiyon için Cihazda\'yı seçin. ';

  @override
  String get firmwareEnsureBattery => 'Cihazınızın %15 pili olduğundan emin olun.';

  @override
  String get actionItemDescriptionHint => 'Ne yapılması gerekiyor?';

  @override
  String get yourScore => 'Skorunuz';

  @override
  String failedToStartAuth(String appName) {
    return '$appName kimlik doğrulaması başlatılamadı';
  }

  @override
  String get actionReadTasks => 'Görevleri oku';

  @override
  String get keepSyncing => 'Senkronizasyona devam et';

  @override
  String get overdue => 'Gecikmiş';

  @override
  String get chatAppsProblemUnavailable => 'Sohbet uygulamaları hesabın için henüz kullanılamıyor.';

  @override
  String get tapSyncToStart => 'Başlatmak için Senkronize Et\'e dokunun';

  @override
  String get emptyDoneMessage => 'Henüz tamamlanmış öğe yok';

  @override
  String get recordOptionsTip => 'İpucu: telefon görüşmesi kaydetmek için kayıt düğmesindeki oka dokunun.';

  @override
  String get setupQuestionProfession => '1. Ne iş yapıyorsunuz?';

  @override
  String get deviceInfoSection => 'Cihaz Bilgileri';

  @override
  String get teachOmiYourVoice => 'Omi\'ye sesinizi öğretin';

  @override
  String get addYourFirstMemory => 'İlk anınızı ekleyin';

  @override
  String get priceLabel => 'FİYAT';

  @override
  String get high => 'Yüksek';

  @override
  String estimatedSizeWithValue(String size) {
    return 'Tahmini Boyut: ~$size MB';
  }

  @override
  String cleanUpUnsureCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Omi için belirsiz $count kişi',
      one: 'Omi için belirsiz 1 kişi',
    );
    return '$_temp0';
  }

  @override
  String get makeAllMemoriesPrivate => 'Tüm Anıları Özel Yap';

  @override
  String get raybanMetaWaitingForMetaAI => 'Bağlantıyı Meta AI uygulamasında tamamlayın, ardından buraya geri dönün.';

  @override
  String get revokeAuthorization => 'İzni Geri Al';

  @override
  String get confidenceToReachConfirmed => 'Onaylandı Seviyesine Ulaşmak İçin';

  @override
  String get syncCardRateLimited => 'Adil kullanım sınırına ulaşıldı — eşitleme otomatik olarak sürdürülecek';

  @override
  String get reviewStopClip => 'Klibi durdur';

  @override
  String get chatAppsWhatOmiDoes => 'Omi sohbet uygulamalarında ne yapar';

  @override
  String get resume => 'Sürdür';

  @override
  String get defaultSpace => 'Varsayılan Alan';

  @override
  String get multipleSpeakersDetected => 'Birden fazla konuşmacı tespit edildi';

  @override
  String evidenceAutoCorrected(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count otomatik etiketi başka birine değiştirdiniz',
      one: '1 otomatik etiketi başka birine değiştirdiniz',
    );
    return '$_temp0';
  }

  @override
  String get voiceMatchPossible => 'Olası eşleşme';

  @override
  String get checkBoxToConfirm =>
      'Hesabınızı silmenin kalıcı ve geri alınamaz olduğunu anladığınızı onaylamak için kutucuğu işaretleyin.';

  @override
  String get quicklyPopulateResponse => 'Bilinen sağlayıcı yanıt formatıyla hızlıca doldur';

  @override
  String get monthJul => 'Tem';

  @override
  String get failedToInitializeCallService => 'Arama hizmeti baslatılamadi';

  @override
  String get connectAction => 'Bağla';

  @override
  String get onDeviceModelDeleted => 'Model silindi';

  @override
  String get micGainDescNeutral => 'Nötr - dengeli kayıt';

  @override
  String get chatOfflineHint => 'Çevrimdışısın. Mesaj göndermek için yeniden bağlan.';

  @override
  String get onboardingLocationGrantInSettings =>
      'Lütfen Ayarlar > Gizlilik ve Güvenlik > Konum Servisleri\'nde konum izni verin';

  @override
  String get invalidSetupInstructionsUrl => 'Geçersiz kurulum talimatları URL';

  @override
  String get msgCameraPermissionDenied => 'Kamera izni reddedildi. Lütfen kameraya erişime izin verin';

  @override
  String get dataAndPrivacy => 'Veri ve Gizlilik';

  @override
  String get deviceNotCompatible => 'Cihazınız cihaz üzerinde transkripsiyon ile uyumlu değil';

  @override
  String get pairingDescAppleWatch =>
      'Apple Watch\'unuza Omi uygulamasını yükleyin ve açın, ardından uygulamada Bağlan\'a dokunun.';

  @override
  String get speechProfileTopicLocation => 'Nerede yaşıyorsunuz?';

  @override
  String get makeAllPrivate => 'Tüm Anıları Özel Yap';

  @override
  String get capabilityNotification => 'Bildirim';

  @override
  String get captureAudioSavedTranscribesLater => 'Ses kaydedildi, sonra metne dökülecek';

  @override
  String get wrappedTopPhrases => 'En çok kullanılan 5 ifade';

  @override
  String get transcribeLaterPaused => 'Duraklatıldı — ses kaydedilmiyor';

  @override
  String get deviceOnboardingTurnOnTitle => 'Aç';

  @override
  String get keyNamePlaceholder => 'ör., Uygulama Entegrasyonum';

  @override
  String get languageTitle => 'Dil';

  @override
  String get statusVerifiedLabel => 'Dogrulandi';

  @override
  String get storageLocationPhoneMemory => 'Telefon (Bellek)';

  @override
  String get you => 'Siz';

  @override
  String get listeningTranscriptWillAppear => 'Dinleniyor… transkript burada görünecek.';

  @override
  String get askSuggestNotice => 'Omi neyi fark etti?';

  @override
  String get safelyBackedUp => 'Oluşturulan konuşmalar';

  @override
  String get folderName => 'Klasör adı';

  @override
  String get categorySocialEntertainment => 'Sosyal ve Eğlence';

  @override
  String speechProfileOwnerTitle(String name) {
    return '$name adlı kişinin ses profili';
  }

  @override
  String get reviewAddedSuccessfully => 'Yorum başarıyla eklendi 🚀';

  @override
  String get fairUseSpeechUsage => 'Konuşma Kullanımı';

  @override
  String get visibilitySubtitle => 'Listenizde hangi konuşmaların görüneceğini kontrol edin';

  @override
  String get wrappedWinLabelUpper => 'ZAFER';

  @override
  String timeCompactMinsAndSecs(int mins, int secs) {
    return '${mins}dk ${secs}sn';
  }

  @override
  String get phoneCallsUpsellSubtitle =>
      'Omi üzerinden arama yapın ve gerçek zamanlı transkripsiyon, otomatik özetler ve daha fazlasını alın.';

  @override
  String get sessionExpiredSignInAgain => 'Oturumun süresi doldu — tekrar giriş yapın.';

  @override
  String get newPersonEllipsis => 'Yeni Kişi…';

  @override
  String get sharePeriodToday => 'Bugün, Omi:';

  @override
  String get premiumMinutesInfo => 'Ayda 300 premium dakika. Sınırsız ücretsiz transkripsiyon için Cihazda\'yı seçin.';

  @override
  String get notConnectedStatus => 'Bağlı Değil';

  @override
  String get authorizeSavingRecordings => 'Kayıtların Kaydedilmesine İzin Ver';

  @override
  String get thinking => 'Düşünüyor';

  @override
  String get unpairDialogTitle => 'Cihazı Eşleştirmeyi Kaldır';

  @override
  String get batteryFullyChargedBody => 'Omi cihazınız tamamen şarj oldu. Fişini çekebilirsiniz!';

  @override
  String get speakerTagPromptRejectedToast => 'Etiket kaldırıldı';

  @override
  String get phone => 'Telefon';

  @override
  String get chatAppsVoiceNotes => 'Sesli notlar';

  @override
  String get deviceOnboardingStatusDisconnected => 'Bağlantı kesildi';

  @override
  String get debugModeDetected => 'Hata ayıklama modu algılandı';

  @override
  String get failedToSaveDefaultRepo => 'Varsayılan depo kaydedilemedi';

  @override
  String get showCompletedTasks => 'Tamamlananları göster';

  @override
  String deviceStorageUsedOfTotal(String used, String total) {
    return '$total alanın $used kısmı kullanıldı';
  }

  @override
  String get recordingsNotSynced => 'Henüz senkronize edilmemiş kayıtlarınız var.';

  @override
  String get performanceWarning => 'Performans Uyarısı';

  @override
  String get submitAppPrivateDescription =>
      'Uygulamanız incelenecek ve size özel olarak sunulacak. İnceleme sırasında bile hemen kullanmaya başlayabilirsiniz!';

  @override
  String get copyTranscript => 'Transkripti kopyala';

  @override
  String get providing => 'Sağlama';

  @override
  String get findDeviceNoneMessage => 'Açın ve telefonunuzun yakınında tutun.';

  @override
  String get wrappedLetsHitRewind => 'Yılını geri saralım';

  @override
  String deviceRamBelowMinimum(String ram) {
    return 'Algılanan RAM: $ram GB. Önerilen minimum: 4 GB.';
  }

  @override
  String get addOrChangePaymentMethod => 'Ödeme yönteminizi ekleyin veya değiştirin';

  @override
  String get omiAppName => 'Omi';

  @override
  String get enableBluetooth => 'Bluetooth\'u Etkinleştir';

  @override
  String get privacyNotice => 'Gizlilik Bildirimi';

  @override
  String get manufacturer => 'Üretici';

  @override
  String get byContinuingYouAgree => 'Devam ederek ';

  @override
  String dataProtectedWithSettings(String level) {
    return 'Verileriniz artık yeni $level ayarlarıyla korunuyor.';
  }

  @override
  String get selectSpaceInWorkspace => 'Çalışma alanınızda bir alan seçin';

  @override
  String get copyKey => 'Anahtarı Kopyala';

  @override
  String get password => 'Şifre';

  @override
  String estimatedSize(String size) {
    return 'Tahmini Boyut: ~$size MB';
  }

  @override
  String monthsFreeBadge(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count ay ücretsiz',
      one: '1 ay ücretsiz',
    );
    return '$_temp0';
  }

  @override
  String get chatAppsNotAvailableYet => 'Henüz mevcut değil';

  @override
  String estimatedTimeRemaining(String time) {
    return 'Tahmini: $time kaldı';
  }

  @override
  String get syncCardBackendBusy => 'Omi sunucuları yoğun — kapasite boşaldığında kayıtlarınız eşitlenecek';

  @override
  String get speakerTagPromptTitle => 'Omi\'nin sesleri tanımasına yardım edin';

  @override
  String get playFromHere => 'Buradan oynat';

  @override
  String get entityProject => 'Proje';

  @override
  String get permissionNotGrantedYet =>
      'Henüz izin verilmedi. Lütfen mikrofon erişimine izin verdiğinizden ve saatinizdeki uygulamayı yeniden açtığınızdan emin olun.';

  @override
  String get e2eeTradeoff2 => '• Parolanızı kaybederseniz, verileriniz kurtarılamaz.';

  @override
  String get exportConfiguration => 'Yapılandırmayı dışa aktar';

  @override
  String get recordWith => 'Kayıt yöntemi';

  @override
  String get greetingEvening => 'İyi akşamlar';

  @override
  String deletePhoneNumberConfirm(String phoneNumber) {
    return '$phoneNumber silinsin mi?';
  }

  @override
  String get deviceOnboardingAskQuestionTitle => 'Omi\'ye Bir Soru Sorun';

  @override
  String get appNamePlaceholder => 'Harika Uygulamam';

  @override
  String get tapPlayToResume => 'Devam etmek için oynat\'a dokunun';

  @override
  String get dueDate => 'Bitiş tarihi';

  @override
  String get appearanceSystem => 'Sistem';

  @override
  String get invalidEmailError => 'Lütfen geçerli bir e-posta girin';

  @override
  String get highResourceUsage => 'Yüksek Kaynak Kullanımı';

  @override
  String get voiceAndPeople => 'Ses ve İnsanlar';

  @override
  String get customizationSection => 'Özelleştirme';

  @override
  String get failedToCancelSubscription => 'Abonelik iptal edilemedi. Lütfen tekrar deneyin.';

  @override
  String get later => 'Daha sonra';

  @override
  String get wrappedTasksGenerated => 'görev oluşturuldu';

  @override
  String get personalizingExperience => 'Deneyiminiz kişiselleştiriliyor…';

  @override
  String get syncAvailable => 'Senkronizasyon Mevcut';

  @override
  String chatGreeting(String name) {
    return 'Merhaba $name, ne istersen sor';
  }

  @override
  String get phoneCallSettingsTitle => 'Arama ayarlari';

  @override
  String get remoteDeviceTerminated => 'Uzak cihaz bağlantıyı sonlandırdı';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'Dosya seçici açılırken hata: $message';
  }

  @override
  String get actionItemDeleted => 'Görev silindi';

  @override
  String get couldNotLoadMemories => 'Anılar yüklenemedi';

  @override
  String get generateDescription => 'Açıklama oluştur';

  @override
  String get privateLabel => 'Özel';

  @override
  String get deviceOnboardingMuteUnmute => 'Sustur / Sesi Aç';

  @override
  String get day => 'Gün';

  @override
  String get submitAppQuestion => 'Uygulama Gönderilsin mi?';

  @override
  String get usageWords => 'Words';

  @override
  String get failedToConnectClickUp => 'ClickUp\'a bağlanılamadı';

  @override
  String get selectZipFileToImport => '.zip dosyasını içe aktarmak için seçin!';

  @override
  String timeSecsPlural(int count) {
    return '$count sn';
  }

  @override
  String get wasThisHelpful => 'Bu yardımcı oldu mu?';

  @override
  String get msgLearningMemories => 'Anılarınızdan öğreniliyor…';

  @override
  String get onboardingScreenCaptureRequired => 'Sistem ses kaydı için ekran yakalama izni gereklidir.';

  @override
  String evidenceManualLabels(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count konuşmada sizin tarafınızdan etiketlendi',
      one: '1 konuşmada sizin tarafınızdan etiketlendi',
    );
    return '$_temp0';
  }

  @override
  String get transferCancelled => 'Aktarım iptal edildi';

  @override
  String get sttModelSpeed => 'Hız';

  @override
  String get fairUsePolicy => 'Adil Kullanım';

  @override
  String get phoneStorage => 'Telefon Depolaması';

  @override
  String get deviceOnboardingEndConversationDesc => 'Mevcut konuşmayı kaydet ve bitir';

  @override
  String get proceedAnyway => 'Yine de devam et';

  @override
  String get overview => 'Genel Bakış';

  @override
  String get deviceOnboardingGoodJob => 'Aferin!';

  @override
  String get delete => 'Sil';

  @override
  String get connectAiAssistantsToYourData => 'AI asistanlarını verilerinize bağlayın';

  @override
  String get startFresh => 'Baştan başla';

  @override
  String get deviceOnboardingStatusConnectedDone => 'Bağlandı!';

  @override
  String get filterInstalled => 'Yüklü';

  @override
  String get mergingStatus => 'Birleştiriliyor…';

  @override
  String get successfullyConnected => 'Başarıyla Bağlandı!';

  @override
  String get permissionCreateConversations => 'Konuşma Oluştur';

  @override
  String get cancelConsequencePhoneCalls => 'Gerçek zamanlı telefon görüşmesi transkripsiyon yok';

  @override
  String get feedbackReasonSummaryOther => 'Başka bir şey';

  @override
  String get oAuth => 'OAuth';

  @override
  String get notEnoughSpace => 'Uyarı: Yeterli alan yok!';

  @override
  String get feedbackTitleTooExpensive => 'Sizin için hangi fiyat uygun olurdu?';

  @override
  String get secureEncryption => 'Güvenli Şifreleme';

  @override
  String get rating2PlusStars => '2+ yıldız';

  @override
  String get chatAppsOpenMessagesAgain => 'Mesajlar\'ı yeniden aç';

  @override
  String fairUseBudgetResetsAt(String time) {
    return 'Sıfırlanma $time';
  }

  @override
  String get addVocabularyDescription => 'Transkripsiyon sırasında Omi\'nin tanıması gereken kelimeleri ekleyin.';

  @override
  String get whisperModelSizeMedium => 'Orta';

  @override
  String get wrappedMyBuddiesLabel => 'ARKADAŞLARIM';

  @override
  String get memoryGraph => 'Anı grafiği';

  @override
  String get paste => 'Yapıştır';

  @override
  String get failedToRefreshGitHubStatus => 'GitHub bağlantı durumu yenilenemedi.';

  @override
  String get feedbackSubtitleMissingFeatures => 'Her zaman inşa ediyoruz — bu önceliklendirmemize yardımcı olur.';

  @override
  String get itemApp => 'Uygulama';

  @override
  String get pairingDescFriendPendant =>
      'Açmak için kolye üzerindeki düğmeye basın. Otomatik olarak eşleştirme moduna geçecektir.';

  @override
  String get appDisabledGeneric => 'Omi tarafından devre dışı bırakıldı.';

  @override
  String get noSummaryForApp =>
      'Bu uygulama için özet mevcut değil. Daha iyi sonuçlar için başka bir uygulama deneyin.';

  @override
  String get deleteProcessed => 'İşlenmişleri Sil';

  @override
  String get chatBlockOpenInGoals => 'Hedefler’de aç';

  @override
  String get micGainDescModerate => 'Sessiz - orta düzey gürültü için';

  @override
  String get defaultRepository => 'Varsayılan Depo';

  @override
  String get statusPending => 'Bekliyor';

  @override
  String get referralProgram => 'Yönlendirme Programı';

  @override
  String get authFailedToLinkApple => 'Apple ile bağlantı kurulamadı, lütfen tekrar deneyin.';

  @override
  String modelNameWithFile(String model) {
    return 'Model: $model';
  }

  @override
  String get deviceOnboardingTurnOnSubtitle => 'Tekrar açmak için düğmeye basın';

  @override
  String get previewAndScreenshots => 'Önizleme ve Ekran Görüntüleri';

  @override
  String get recordingOfflineTranscriptWillCatchUp =>
      'Çevrimdışı kaydediliyor — tekrar çevrimiçi olduğunuzda transkript güncellenecek.';

  @override
  String get accessibilityDescription =>
      'Omi, tarayıcınızda Zoom, Meet veya Teams toplantılarına katıldığınızı algılamak için erişilebilirlik izni gerektirir.';

  @override
  String setDefaultAppContent(String appName) {
    return '$appName varsayılan özet uygulamanız olarak ayarlansın mı?\n\nBu uygulama gelecekteki tüm konuşma özetleri için otomatik olarak kullanılacaktır.';
  }

  @override
  String get switchRequiresRestart => 'Değiştirme uygulama yeniden başlatma gerektirir';

  @override
  String get wrappedWinHeader => 'Zafer';

  @override
  String get forYou => 'Sizin İçin';

  @override
  String get filterCategory => 'Kategori';

  @override
  String get createPersonHint => 'Yeni bir kişi oluşturun ve Omi\'yi onların konuşmasını da tanımaya eğitin!';

  @override
  String get loadingMemories => 'Anılar yükleniyor…';

  @override
  String get selectedPaymentMethod => 'Seçilen Ödeme Yöntemi';

  @override
  String get email => 'E-posta';

  @override
  String get transcriptionUnavailableRecordingContinues =>
      'Transkriptler kullanılamıyor, kayıt cihazda devam ediyor ve daha sonra işlenecek';

  @override
  String get noLogsYet =>
      'Henüz günlük yok. Transkripsiyon sağlayıcınıza giden istekleri görmek için bir şey kaydedin.';

  @override
  String get failedToStartAuthentication => 'Kimlik doğrulama başlatılamadı';

  @override
  String peopleCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count kişi',
      one: '1 kişi',
    );
    return '$_temp0';
  }

  @override
  String get enterBackendUrlError => 'Lütfen sunucu URL\'sini girin';

  @override
  String get playbackBackToCurrent => 'Geçerliye Dön';

  @override
  String clockSkewWarning(int minutes) {
    return 'Cihazınızın saati ~$minutes dk. farklı. Tarih ve saat ayarlarınızı kontrol edin.';
  }

  @override
  String get stopThese => 'Bunları Durdur';

  @override
  String get yes => 'Evet';

  @override
  String get recognizingOthers => 'Diğerlerini tanıma 👀';

  @override
  String get transcriptionLanguageDesc => 'Konuşma transkripsiyonu için dil seçin';

  @override
  String aboutMinutesRemaining(int minutes) {
    return 'Yaklaşık $minutes dakika kaldı';
  }

  @override
  String get deleteFlowReasonSubtitle => 'Geri bildiriminiz Omi\'yi herkes için iyileştirmemize yardımcı olur.';

  @override
  String get processedFilesDeleted => 'İşlenmiş dosyalar silindi';

  @override
  String get autoLanguageDetection => 'Otomatik dil algılama';

  @override
  String bulkExportPartial(int success, int total, String platform) {
    return '$total öğeden $success tanesi $platform uygulamasına aktarıldı';
  }

  @override
  String get actionItemDescriptionCannotBeEmpty => 'Görev açıklaması boş olamaz';

  @override
  String get deleteReasonFoundAlternative => 'Başka bir şey kullanıyorum';

  @override
  String get noContentToDisplay => 'Gösterilecek içerik yok';

  @override
  String get feedbackReasonRecordingWrongSpeaker => 'Yanlış konuşmacı';

  @override
  String get create => 'Oluştur';

  @override
  String get greatJobAlmostThere => 'Harika iş, neredeyse bitti';

  @override
  String get captureStorageAlmostFull => 'Depolama neredeyse dolu';

  @override
  String chatAppsConnectedOn(String date) {
    return '$date tarihinde bağlandı';
  }

  @override
  String get wrappedAGreatDay => 'Harika Bir Gün';

  @override
  String get backendUrlSavedSuccess => 'Sunucu URL başarıyla kaydedildi!';

  @override
  String get speakerTagPromptIsThisYou => 'Bu sen miydin?';

  @override
  String get knowledgeGraphDeletedSuccess => 'Bilgi grafiği başarıyla silindi';

  @override
  String timeMinsPlural(int count) {
    return '$count dk';
  }

  @override
  String get peopleNotHeardYet => 'Henüz duyulmadı';

  @override
  String get chatStarterDoDifferently => 'Bugün neyi farklı yapabilirim?';

  @override
  String get fairUseAboutBody =>
      'Omi kişisel konuşmalar, toplantılar ve canlı etkileşimler için tasarlanmıştır. Kullanım, bağlantıda geçen süreye değil, konuşarak geçirilen süreye göre ölçülür. Kullanımınız normal kişisel kullanımın çok üzerindeyse, önce bir uyarı alırsınız. Sürekli yoğun kullanım, transkripsiyonu yavaşlatabilir veya sınırlayabilir.';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'Lütfen birincil dilinizi seçin';

  @override
  String get manualDisconnect => 'Manuel bağlantı kesme';

  @override
  String get googleCalendarNotConnected => 'Google Takvim Bağlı Değil';

  @override
  String get soCloseJustLittleMore => 'Çok yakın, biraz daha';

  @override
  String appDataAccessMessage(String appName) {
    return '$appName, konuşmalarını, anılarını ve kayıtlarını geliştiricisinin sunucusunda alacak. Omi, bu verilerin orada nasıl kullanıldığından sorumlu değildir.';
  }

  @override
  String savePercent(int percent) {
    return '~%$percent tasarruf';
  }

  @override
  String get deviceDisconnectedNotificationBody => 'Omi\'yi kullanmaya devam etmek için lütfen yeniden bağlanın.';

  @override
  String get openConversation => 'Konuşmayı aç';

  @override
  String get frequencyDescMaximum => 'Her yararlı bağlantı, günde en fazla 9';

  @override
  String get readChatRepliesAloud => 'Sohbet yanıtlarını sesli oku';

  @override
  String get microphonePermissionRequired => 'Ses kaydı için mikrofon izni gereklidir.';

  @override
  String get updatePayPalAccountDetails => 'PayPal hesap bilgilerinizi güncelleyin';

  @override
  String get connectionTimeout => 'Bağlantı zaman aşımı';

  @override
  String get micGainDescHigh => 'Yüksek - uzak veya yumuşak sesler için';

  @override
  String get permissionsInfoNote => 'R = Okuma, W = Yazma. Hiçbir şey seçilmezse varsayılan salt okunur.';

  @override
  String timeHoursAndMins(int hours, int mins) {
    return '$hours saat $mins dk';
  }

  @override
  String get keepMyAccount => 'Hesabımı koru';

  @override
  String get transcriptionLanguage => 'Transkripsiyon dili';

  @override
  String dreamReportStats(int records, int tokens) {
    return '$records öğe okundu · $tokens token';
  }

  @override
  String get editPerson => 'Kişiyi Düzenle';

  @override
  String get whatWeTrack => 'Ne Takip Ediyoruz';

  @override
  String get micGainDescVeryHigh => 'Çok yüksek - çok sessiz kaynaklar için';

  @override
  String timeCompactDays(int count) {
    return '${count}g';
  }

  @override
  String get reviewTaskField => 'Görev';

  @override
  String reviewConfirmPerson(String name) {
    return '$name kişisini onayla';
  }

  @override
  String get downloadingFromDevice => 'Cihazdan indiriliyor';

  @override
  String get conversationTranscriptCopiedToClipboard => 'Sohbet transkripti panoya kopyalandı';

  @override
  String get continueAction => 'Devam Et';

  @override
  String conversationsMovedCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count konuşma taşındı',
      one: '1 konuşma taşındı',
    );
    return '$_temp0';
  }

  @override
  String get signInButton => 'Giriş Yap';

  @override
  String get startUpdate => 'Güncellemeyi Başlat';

  @override
  String get wrappedTopPhrasesLabelUpper => 'EN İYİ İFADELER';

  @override
  String get total => 'Toplam';

  @override
  String get deleting => 'Siliniyor…';

  @override
  String get skipBack10Seconds => '10 saniye geri';

  @override
  String get setupAnswerAllQuestions => 'Henüz tüm soruları yanıtlamadınız! 🥺';

  @override
  String get planUpgradeScheduledMessage =>
      'Yükseltme planlandı! Aylık planınız fatura döneminizin sonuna kadar devam eder, ardından otomatik olarak yıllık plana geçer.';

  @override
  String get needHelpChatWithUs => 'Yardıma mı ihtiyacınız var? Bizimle sohbet edin';

  @override
  String get chatBlockUnavailable => 'Artık kullanılamıyor';

  @override
  String estimatedMinutes(int count) {
    return '~$count dakika';
  }

  @override
  String get failedToSaveMemory => 'Kaydedilemedi. Lütfen bağlantınızı kontrol edin.';

  @override
  String get deleteReasonTakingBreak => 'Sadece ara veriyorum';

  @override
  String get reviewAndManageConversations => 'Kaydedilen görüşmelerinizi inceleyin ve yönetin';

  @override
  String get actionReadMemories => 'Anıları oku';

  @override
  String deletePinnedPersonMessage(String name) {
    return '$name sabitli. Ses örnekleri silinir, Omi onu artık tanımaz ve geçmiş transkriptlerde adsız bir konuşmacı olarak görünür. Bu işlem geri alınamaz.';
  }

  @override
  String get speakerTagPromptHintOwner => 'Yanıtın yalnızca oynatılan bölümü etiketler.';

  @override
  String get onboardingNotificationDeniedNotifications =>
      'Bildirim izni reddedildi. Lütfen Sistem Tercihleri > Bildirimler\'de izin verin.';

  @override
  String appDisabledNamed(String appName) {
    return '$appName devre dışı bırakıldı';
  }

  @override
  String get tabOld => 'Eski';

  @override
  String deviceOnboardingVoiceReplyStatusHeadphonesConnected(String device) {
    return '$device bağlandı. Omi burada konuşacak.';
  }

  @override
  String get deletePendingFiles => 'Bekleyen kayıtları sil';

  @override
  String get wrappedWin => 'Zafer';

  @override
  String get removeFromAllFolders => 'Tüm klasörlerden kaldır';

  @override
  String get deviceIdLabel => 'Cihaz Kimliği';

  @override
  String get upgradeAlreadyScheduled => 'Yıllık plana yükseltmeniz zaten planlandı';

  @override
  String get openCall => 'Aramayı aç';

  @override
  String get rateAndReviewThisApp => 'Bu uygulamayı değerlendirin ve yorum yazın';

  @override
  String get getStarted => 'Başlayın';

  @override
  String get deviceOnboardingVoiceReplyAlwaysDescription =>
      'Hiçbir kulaklık bağlı olmadığında telefonun hoparlörünü kullanır.';

  @override
  String chooseExportDestination(int count) {
    return '$count öğeyi dışa aktar…';
  }

  @override
  String get onboardingSetupSubtitle => 'Omi\'ye kişiselleştirmek için biraz zaman tanıyın';

  @override
  String welcomeBack(String name) {
    return 'Tekrar hoş geldiniz, $name';
  }

  @override
  String get dreamReportIdle => 'Henüz bakılacak yeni bir şey yok.';

  @override
  String get cleanUpTitle => 'Temizle';

  @override
  String get deleteProcessedFiles => 'İşlenmiş Dosyaları Sil';

  @override
  String get no => 'Hayır';

  @override
  String get msgPhotoError => 'Fotoğraf çekerken hata oluştu. Lütfen tekrar deneyin.';

  @override
  String get search => 'Ara';

  @override
  String get downloadingFirmware => 'Aygıt yazılımı indiriliyor';

  @override
  String get phoneKeypadTab => 'Tus takimi';

  @override
  String get pendantFullSyncBlocked =>
      'Pendant\'ın depolama alanı dolu ve hâlâ kayıt modunda olduğu için kayıtlı ses aktarılamıyor. Kaydı durdurmak için Pendant\'ın düğmesine basın, ardından yeniden senkronize edin.';

  @override
  String get deleteSelectedItemsTitle => 'Seçili Öğeleri Sil';

  @override
  String get appPrivacyAndTerms => 'Uygulama Gizliliği ve Şartları';

  @override
  String get omiTranscription => 'Omi Transkripsiyonu';

  @override
  String get editConversation => 'Sohbeti düzenle';

  @override
  String moveConversationsTo(int count) {
    return '$count konuşmayı taşı:';
  }

  @override
  String get signOutConfirmation =>
      'Konuşmalarınızı görmek için yeniden oturum açmanız gerekecek. Eşlenen cihazınız ve uygulama tercihleriniz bu telefonda kalır.';

  @override
  String get wrappedObsessionsLabel => 'TAKINTILARI';

  @override
  String get jumpToLatestMessage => 'En son mesaja git';

  @override
  String get failedStatus => 'Başarısız';

  @override
  String get notNow => 'Şimdi Değil';

  @override
  String transferFailedMessage(String error) {
    return 'Aktarım başarısız: $error';
  }

  @override
  String get customVocabularyTitle => 'Özel Kelime Hazinesi';

  @override
  String get internetRequired => 'İnternet gerekli';

  @override
  String get waitingForData => 'Veri bekleniyor…';

  @override
  String get noRecordingsYet => 'Henüz kayıt yok';

  @override
  String get answerWithYourVoice => 'Sesinizle yanıtlayın:';

  @override
  String personUnpinnedToast(String name) {
    return '$name sabitlemesi kaldırıldı';
  }

  @override
  String get stopRecording => 'Kaydı Durdur';

  @override
  String get off => 'Kapalı';

  @override
  String get memoryThisPhone => 'Bu telefon';

  @override
  String get thirteenMonthsCoverage => 'Toplamda 13 aylık kapsam alacaksınız (mevcut ay + 12 ay yıllık)';

  @override
  String failedToCreateApiKey(String error) {
    return 'Sağlayıcı API anahtarı oluşturulamadı: $error';
  }

  @override
  String get tipStableInternet => 'Kararlı internet bulut yüklemelerini hızlandırır';

  @override
  String get tasksMarkComplete => 'Tamamlandı olarak işaretlendi';

  @override
  String get reviewAddTask => 'Görev ekle';

  @override
  String get submitReply => 'Yanıt Gönder';

  @override
  String get captureRecoveryBanner => 'Omi ses göndermiyor — yeniden bağlanmak için dokunun';

  @override
  String get analyzing => 'Analiz ediliyor…';

  @override
  String get sttModelFaster => 'Daha hızlı';

  @override
  String get fairUseLoadError => 'Adil kullanım durumu yüklenemedi. Lütfen tekrar deneyin.';

  @override
  String get places => 'Yerler';

  @override
  String get voiceMatchWeak => 'Zayıf eşleşme';

  @override
  String captureOfflineBufferingFor(int minutes) {
    return 'Çevrimdışı, arabelleğe alınıyor · $minutes dk';
  }

  @override
  String get onboardingWhatIKnowAboutYouTitle => 'Hakkında bildiklerim';

  @override
  String get raybanMetaPhotoRequested => 'Fotoğraf istendi — konuşmanızda görünecektir.';

  @override
  String get verifyYourNumber => 'Numaranizi dogrulayin';

  @override
  String get deleteFlowConfirmSubtitle => 'Bu işlem geri alınamaz, destek ekibi tarafından bile.';

  @override
  String get submitAppTermsAgreement =>
      'Bu uygulamayı göndererek, Omi AI Hizmet Koşullarını ve Gizlilik Politikasını kabul ediyorum';

  @override
  String get stripeSecureDescription => 'Stripe, uygulama gelirinizin güvenli ve zamanında transferini sağlar';

  @override
  String get categoryProductivity => 'Verimlilik';

  @override
  String chatWithAppName(String appName) {
    return '$appName ile sohbet';
  }

  @override
  String get enableCloudStorage => 'Bulut Depolamayı Etkinleştir';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl => 'Geçersiz gerçek zamanlı transkript webhook URL\'si';

  @override
  String get wrappedShow => 'DİZİ';

  @override
  String get speakTranscribeSummarize => 'Konuş. Transkripsiyonu Oluştur. Özetle.';

  @override
  String get pricingPaid => 'Ücretli';

  @override
  String get successfullyConnectedAsana => 'Asana\'ya başarıyla bağlanıldı!';

  @override
  String get rating => 'Puan';

  @override
  String get chatQuotaExceededReply =>
      'Aylık limitinize ulaştınız. Kısıtlama olmadan Omi ile sohbete devam etmek için yükseltin.';

  @override
  String get pendantIsListeningTitle => 'Kolyen dinliyor';

  @override
  String get usageBestDay => 'Best day';

  @override
  String get personWhyConfidence => 'Neden?';

  @override
  String get permissionDescCreateConversations => 'Bu uygulama yeni konuşmalar oluşturabilir.';

  @override
  String get reviewSpellingCustom => 'Yaz';

  @override
  String resetsInHours(int count) {
    return '$count saat sonra sıfırlanır';
  }

  @override
  String get reviewAction => 'Gözden geçir';

  @override
  String get submitRequest => 'İstek Gönder';

  @override
  String get phoneCalls => 'Telefon Aramaları';

  @override
  String get actionItemsTab => 'Görevler';

  @override
  String get record => 'Kaydet';

  @override
  String get noReviewsFound => 'Yorum Bulunamadı';

  @override
  String get oauth => 'OAuth';

  @override
  String get urlCopied => 'URL kopyalandı';

  @override
  String get actionItemReminderTitle => 'Omi Hatırlatıcı';

  @override
  String sharedTasksAdded(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Listenize $count görev eklendi',
      one: 'Listenize 1 görev eklendi',
    );
    return '$_temp0';
  }

  @override
  String get contactsPermissionRequiredForSms => 'SMS ile paylaşmak için kişi izni gereklidir';

  @override
  String get apiKeyRevokedSuccessfully => 'API anahtarı başarıyla iptal edildi';

  @override
  String get authorizationSuccessful => 'İzin verme başarılı!';

  @override
  String get unpinAction => 'Sabitlemeyi kaldır';

  @override
  String get syncingStatus => 'Senkronize ediliyor';

  @override
  String get audioFormatLabel => 'Ses Formatı';

  @override
  String get phoneSelectCountryTitle => 'Ülke Seç';

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'En iyi $percentile% kullanıcı';
  }

  @override
  String get phoneContactsTab => 'Kisiler';

  @override
  String get reply => 'Yanıtla';

  @override
  String get openingShareSheet => 'Paylaşım sayfası açılıyor…';

  @override
  String get creatingAppIcon => 'Uygulama simgesi oluşturuluyor…';

  @override
  String get deviceOnboardingStartSpeaking => 'Konuşmaya başlayın…';

  @override
  String get wrappedAHilariousMoment => 'Komik Bir An';

  @override
  String get paidApp => 'Ücretli uygulama';

  @override
  String get wrappedStruggleHeader => 'Mücadele';

  @override
  String get speakerTagPromptDontKnow => 'Tanımadığım biri';

  @override
  String get wrappedStarting => 'Başlatılıyor…';

  @override
  String get getButton => 'Al';

  @override
  String get syncCustomSttWarningTitle => 'Eşitleme, Omi transkripsiyonunu kullanır';

  @override
  String get download => 'İndir';

  @override
  String get addScreenshot => 'Ekran görüntüsü ekle';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return '$serviceName hizmetine bağlanılamadı: $error';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'Lütfen $deviceName cihazınızı kullanmaya devam etmek için yeniden bağlanın.';
  }

  @override
  String get configureDailySummaryDigest => 'Günlük görev özetinizi yapılandırın';

  @override
  String get showShortConversationsDesc => 'Eşik değerinden kısa konuşmaları göster';

  @override
  String participantsSummaryUncounted(String name) {
    return '$name ve diğerleri';
  }

  @override
  String fairUseBudgetUsed(String used, String limit) {
    return '${used}dk / ${limit}dk';
  }

  @override
  String get add => 'Ekle';

  @override
  String get disconnect => 'Bağlantıyı Kes';

  @override
  String get enterApiKey => 'API anahtarınızı girin';

  @override
  String get msgMaxFilesLimit => 'En fazla 4 dosya seçebilirsiniz';

  @override
  String get space => 'Boşluk';

  @override
  String get upgrade => 'Yükselt';

  @override
  String get tapToView => 'Görüntülemek için dokunun';

  @override
  String get summaryTemplate => 'Özet Şablonu';

  @override
  String get chatAppsWaitingTitle => 'Mesajın bekleniyor';

  @override
  String yesterdayAtTime(String time) {
    return 'Dün saat $time';
  }

  @override
  String get cancel => 'İptal';

  @override
  String get checkingAppleWatch => 'Apple Watch kontrol ediliyor…';

  @override
  String syncCardDownloadPercentSpeed(int percent, String speed) {
    return '$percent% · $speed KB/s';
  }

  @override
  String get finalTouches => 'Son dokunuşlar';

  @override
  String get weekdaySat => 'Cmt';

  @override
  String get fairUseWeekly => 'Haftalık süre';

  @override
  String get invalidPaymentUrl => 'Geçersiz ödeme URL\'si';

  @override
  String get transcriptionSlowerOnDevice => 'Bu cihazda cihaz üzerinde transkripsiyon daha yavaş olabilir.';

  @override
  String get noListsInSpace => 'Bu alanda liste bulunamadı';

  @override
  String get deviceDiagnostics => 'Cihaz Tanılama';

  @override
  String get askAnything => 'Her şeyi sor';

  @override
  String confidenceMeterLabel(String level) {
    return 'Güven: $level';
  }

  @override
  String get permissionReadTasks => 'Görevleri Oku';

  @override
  String get skipForNow => 'Şimdilik atla';

  @override
  String get setupCompletedUrl => 'Kurulum Tamamlandı URL\'si';

  @override
  String get saySomething => 'Bir şey söyle…';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get chatAppsEntryTitle => 'Omi ile sohbet et';

  @override
  String get chatAppsTelegramStepOpen => 'Aşağıdaki Telegram\'ı Aç\'a dokun';

  @override
  String get pleaseEnterValidPayPalMeLink => 'Lütfen geçerli bir PayPal.me bağlantısı girin';

  @override
  String get syncFlowIntro =>
      'Kayıtlar cihazınızdan bu telefona aktarılıp yerel olarak saklanır, ardından Omi\'nin sunucusuna yüklenir; burada deşifre edilip görüşmelere dönüştürülür.';

  @override
  String get cantFindDeviceHint =>
      'Cihazınızı bulamıyor musunuz? Açık ve telefonunuza yakın olduğundan emin olun, sonra tekrar tarayın.';

  @override
  String get tryAdjustingFilter => 'Aramanızı veya filtrenizi ayarlamayı deneyin';

  @override
  String get failedConnectionsRecent => 'Başarısız bağlantılar (son 7 gün)';

  @override
  String get captureSourceCall => 'Arama';

  @override
  String get storageLocationPhone => 'Telefon';

  @override
  String get voiceMatchClose => 'Yakın eşleşme';

  @override
  String get reviewChangeUndone => 'Geri alındı. Omi bunu kendi kendine tekrarlamayacak.';

  @override
  String get tasksNoProject => 'Proje yok';

  @override
  String get dataAccessNotice => 'Veri Erişim Bildirimi';

  @override
  String deviceStorageFree(String free) {
    return '$free boş';
  }

  @override
  String alreadyExportedTo(String platform) {
    return '$platform platformuna zaten aktarıldı';
  }

  @override
  String get recapDeletedSnackbar => 'Özet silindi';

  @override
  String get apiUrlRequired => 'API URL\'si gereklidir';

  @override
  String get getOmiUnlimitedFree =>
      'Verilerinizi AI modellerini eğitmek için katkıda bulunarak Omi Unlimited\'ı ücretsiz alın.';

  @override
  String get wrappedShare => 'Paylaş';

  @override
  String get tasksTomorrow => 'Yarın';

  @override
  String get chatAppsShowInAppOn => 'Açık: Omi uygulamasında salt okunur sohbetler olarak görünür.';

  @override
  String get errorActivatingAppIntegration =>
      'Uygulama etkinleştirilirken hata oluştu. Bu bir entegrasyon uygulamasıysa, kurulumun tamamlandığından emin olun.';

  @override
  String get readChatRepliesAloudDescription => 'Yalnızca Sesli yanıt izin verdiğinde konuşur.';

  @override
  String get addDueDate => 'Teslim tarihi ekle';

  @override
  String get translated => 'çevrildi';

  @override
  String get dontAskAgain => 'Bir daha sorma';

  @override
  String get fullAccessScope => 'Tam Erişim';

  @override
  String get firmwareUpdated => 'Aygıt yazılımı güncellendi';

  @override
  String get deviceOnboardingVoiceReplyPreviewThroughPhoneSpeaker => 'Telefonun hoparlörü aracılığıyla';

  @override
  String get prompt => 'İstem';

  @override
  String get dreamReportDeletedItem => 'Silinen öğe';

  @override
  String chatAppsDisconnectChannel(String app) {
    return '$app bağlantısını kes';
  }

  @override
  String get appleHealthDeniedBody =>
      'Omi\'nin Apple Health verilerinizi okuma izni yok. Bunu iOS Ayarlar → Gizlilik ve Güvenlik → Sağlık → Omi yolundan etkinleştirin.';

  @override
  String endsOnDate(String date) {
    return '$date tarihinde sona erer';
  }

  @override
  String get searchSettings => 'Ayarlarda ara';

  @override
  String get pairingDescNeoOne => 'LED yanıp sönene kadar güç düğmesini basılı tutun. Cihaz keşfedilebilir olacaktır.';

  @override
  String get checkingNextSevenDays => 'Sonraki 7 gün kontrol ediliyor';

  @override
  String get confidenceLikely => 'Muhtemel';

  @override
  String get appleHealthFeatureChatTitle => 'Sağlığın hakkında sohbet et';

  @override
  String get loadingDevices => 'Cihazlar yükleniyor…';

  @override
  String get writeSomething => 'Bir şeyler yazın';

  @override
  String syncCardProgressOf(int current, int total) {
    return '$total / $current';
  }

  @override
  String get unableToOpenWatchApp =>
      'Apple Watch uygulaması açılamadı. Lütfen Apple Watch\'unuzda Watch uygulamasını manuel olarak açın ve \"Mevcut Uygulamalar\" bölümünden Omi\'yi yükleyin.';

  @override
  String get dreamReportWouldFix => 'Düzeltirdi';

  @override
  String get doubleTap => 'Çift Dokunma';

  @override
  String get speakerTagPromptSomeoneElse => 'Başka Biri…';

  @override
  String get cancelTransfer => 'Aktarımı İptal Et';

  @override
  String get capabilityExternalIntegration => 'Harici Entegrasyon';

  @override
  String get sttLanguageFollowsPrimary => 'Birincil dilinizi izler';

  @override
  String get wrappedCringeMomentTitle => 'Utanç verici an';

  @override
  String get allRecordingsSynced => 'Tüm kayıtlar senkronize edildi';

  @override
  String get reviewConfirm => 'Onayla';

  @override
  String get checkBackLaterForNewApps => 'Yeni uygulamalar için daha sonra tekrar kontrol edin';

  @override
  String get referAFriend => 'Arkadaş Öner';

  @override
  String cleanUpLead(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other:
          'Omi bu $count kişiden emin değil. Çoğu transkriptlerden yanlış duyulmuş isimler. Tutmak istediklerinizin işaretini kaldırın.',
      one: 'Omi bu kişiden emin değil. Tutmak için işaretini kaldırın.',
    );
    return '$_temp0';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return '$item Özel Yap?';
  }

  @override
  String get chatQuotaSubtitle => 'AI chat messages used with Omi this month.';

  @override
  String get failedTryAgain => 'Başarısız mı? Tekrar Dene';

  @override
  String get deleteAllFiles => 'Tüm kayıtları sil';

  @override
  String get onDeviceModelDownloadSuccess => 'Model indirildi';

  @override
  String get reviewNoChangesTitle => 'Henüz değişiklik yok';

  @override
  String get useMobileAppToCapture => 'Ses kaydetmek için mobil uygulamanızı kullanın';

  @override
  String get setYourName => 'Adınızı belirleyin';

  @override
  String get tasksGroupByDate => 'Tarihe göre grupla';

  @override
  String get diagnosticsLast7Days => 'Son 7 Gün';

  @override
  String get deviceOnboardingStatusConnected => 'Bağlandı';

  @override
  String get actionItemCreatedSuccessfully => 'Görev başarıyla oluşturuldu';

  @override
  String get thursdayAbbr => 'Per';

  @override
  String get wifiConfiguration => 'WiFi Yapılandırması';

  @override
  String get cancelReasonFoundAlternative => 'Bir alternatif buldum';

  @override
  String get process => 'İşle';

  @override
  String get help => 'Yardım';

  @override
  String get rollbackConfirmTitle => 'Yazılım geri alınsın mı?';

  @override
  String get visibility => 'Görünürlük';

  @override
  String get evidenceNotHeard => 'Henüz bir konuşmada duyulmadı';

  @override
  String get messageReported => 'Mesaj başarıyla bildirildi.';

  @override
  String get readyToChat => '✨ Sohbete hazır!';

  @override
  String get tryDifferentFilter => 'Farklı bir filtre deneyin';

  @override
  String get header => 'Başlık';

  @override
  String get wrappedBestHeader => 'En İyi';

  @override
  String get memoryDontUse => 'Kullanma';

  @override
  String get appStore => 'App Store';

  @override
  String get deleteMeetingScreenshotMessage =>
      'Bu işlem ekran görüntüsünü bu toplantının notundan kaldırır. Geri alınamaz.';

  @override
  String get categoryShopping => 'Alışveriş';

  @override
  String get voiceResponseOff => 'Kapalı';

  @override
  String get bluetoothNeeded =>
      'Omi\'nin giyilebilir cihazınıza bağlanması için Bluetooth gereklidir. Lütfen Bluetooth\'u etkinleştirin ve tekrar deneyin.';

  @override
  String get googleCalendarComingSoon => 'Google Takvim entegrasyonu yakında!';

  @override
  String get max => 'Maksimum';

  @override
  String get homeScreen => 'Ana Ekran';

  @override
  String get chatAppsTelegramStepStart => 'Omi ile sohbetinde Başlat\'a dokun';

  @override
  String get greetingAfternoon => 'İyi öğleden sonralar';

  @override
  String get unpair => 'Eşleştirmeyi Kaldır';

  @override
  String get diagnosticsVerdictReconnects => 'Kendiliğinden yeniden bağlanıyor';

  @override
  String get macOsCalendar => 'macOS Takvimi';

  @override
  String get onboardingSetupStepLanguage => 'Transkripsiyon diliniz için ayarlanıyor';

  @override
  String get mcpOAuthSetup =>
      'claude.ai\'de özel bir bağlayıcı ekleyin ve sunucu URL\'sini yapıştırın. Claude gelişmiş bir OAuth Client ID isterse aşağıdaki değeri kullanın ve gizli anahtarı boş bırakın — MCP API anahtarınızı asla OAuth gizli anahtarı olarak kullanmayın.';

  @override
  String get wednesdayAbbr => 'Çar';

  @override
  String get selectAudioInput => 'Ses girişini seç';

  @override
  String get deviceDisconnectedMessage => 'Omi\'nizin bağlantısı kesildi 😔';

  @override
  String get reprocessConversation => 'Konuşmayı Yeniden İşle';

  @override
  String get goal => 'HEDEF';

  @override
  String mergeConversationsMessage(int count) {
    return 'Bu işlem $count konuşmayı birleştirecek. Tüm içerik birleştirilecek ve yeniden oluşturulacak.';
  }

  @override
  String get everyXSeconds => 'Her x saniyede';

  @override
  String get chatAppsLocked => 'Omi Pro gerekir';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl => 'Geçersiz oluşturulan konuşma webhook URL\'si';

  @override
  String get secureAuthViaAppleId => 'Apple ID üzerinden güvenli kimlik doğrulama';

  @override
  String connectingToDeviceName(String deviceName) {
    return '$deviceName cihazına bağlanılıyor';
  }

  @override
  String get listeningSubtitle => 'Omi\'nin aktif olarak dinlediği toplam süre.';

  @override
  String get capturing => 'Kaydediliyor';

  @override
  String get enterWifiNetworkName => 'WiFi ağ adını girin';

  @override
  String get noAppsAvailable => 'Kullanılabilir uygulama yok';

  @override
  String get installingFirmware => 'Aygıt yazılımı yükleniyor';

  @override
  String get transferToPhone => 'Telefona Aktar';

  @override
  String get voiceResponseMode => 'Sesli yanıt';

  @override
  String get messageCopied => '✨ Mesaj panoya kopyalandı';

  @override
  String get discardRecordingMessage => 'Ses örneğiniz henüz kaydedilmedi. Şimdi çıkarsanız silinecektir.';

  @override
  String chatAppsIMessageBody(String code) {
    return 'Merhaba Omi, bağlantı kodu $code';
  }

  @override
  String get failedToRefreshWhoopStatus => 'Whoop bağlantı durumu yenilenemedi.';

  @override
  String get youreOnAnnualPlan => 'Yıllık Plan\'dasınız';

  @override
  String timeHoursPlural(int count) {
    return '$count saat';
  }

  @override
  String get usageOnline => 'Çevrimiçi';

  @override
  String get validPortRequired => 'Geçerli port gereklidir';

  @override
  String get howItWorks => 'Nasıl çalışır';

  @override
  String get viewTemplate => 'Şablonu Görüntüle';

  @override
  String get dreamReportNothingFound => 'Düzeltilecek bir şey yok';

  @override
  String get personTalkTime => 'Konuşma süresi';

  @override
  String get evidenceNoVoice => 'Henüz ses örneği yok';

  @override
  String get makeMyAppPublic => 'Uygulamamı herkese açık yap';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'Bluetooth izin durumu: $status. Lütfen Sistem Tercihleri\'ni kontrol edin.';
  }

  @override
  String get noRecordings => 'Kayıt Yok';

  @override
  String get usageChatThisMonth => 'Chat this month';

  @override
  String get addAppEnterChatPrompt => 'Uygulamanız için bir sohbet istemi girin';

  @override
  String daysAgo(int count) {
    return '$count gün önce';
  }

  @override
  String get processing => 'İşleniyor';

  @override
  String get deviceOnboardingStatusTurningOff => 'Kapatılıyor…';

  @override
  String get newTag => 'YENİ';

  @override
  String get permissionDescReadTasks => 'Bu uygulama görevlerinize erişebilir.';

  @override
  String get time => 'Saat';

  @override
  String get recording => 'Kaydediliyor';

  @override
  String get speakerTagPromptWhoIsThis => 'Bu kim?';

  @override
  String chatUsageMessagesNoLimit(String used) {
    return 'Sohbet: $used mesaj bu ay';
  }

  @override
  String get importantTradeoffs => 'Önemli Ödünler:';

  @override
  String get makeAllPublic => 'Tüm Anıları Genel Yap';

  @override
  String get noSpeechDesc =>
      'Herhangi bir konuşma algılayamadık. Lütfen en az 10 saniye, en fazla 3 dakika konuştuğunuzdan emin olun.';

  @override
  String get searchPartialFailure => 'Bazı sonuçlar yüklenemedi';

  @override
  String get prerecordedTranscript => 'Önceden kaydedilmiş';

  @override
  String get confirm => 'Onayla';

  @override
  String get statusCalling => 'Araniyor…';

  @override
  String get wrappedConvos => 'sohbet';

  @override
  String get unresolvedSpeakersTitle => 'Konuşmacı Etiketleri Hakkında';

  @override
  String get writeYourReply => 'Yanıtınızı yazın…';

  @override
  String get localCopiesSection => 'Yerel Kopyalar';

  @override
  String get noSummaryYet => 'Henüz özet yok';

  @override
  String get wrappedBiggestHeader => 'En Büyük';

  @override
  String get error => 'Hata';

  @override
  String get deviceWillRestart => 'Cihazınız yeniden başlatılacak.';

  @override
  String get consentDataMessage =>
      'Devam ederek, konuşmalarınız, kayıtlarınız ve kişisel bilgileriniz sunucularımızda güvenli bir şekilde saklanacaktır. Ses kayıtlarınız ve transkriptleriniz, size yapay zeka destekli içgörüler sağlamak ve tüm uygulama özelliklerini etkinleştirmek için üçüncü taraf yapay zeka hizmetleri (transkripsiyon için Deepgram ve analiz için OpenAI dahil) tarafından işlenir.';

  @override
  String get connectMacOsCalendar => 'Yerel macOS takviminizi bağlayın';

  @override
  String get captureSourcePhoneMic => 'Telefon mikrofonu';

  @override
  String get setupCompleted => 'Tamamlandı';

  @override
  String get installOmiOnAppleWatchDescription =>
      'Apple Watch\'unuzu Omi ile kullanmak için önce saatinize Omi uygulamasını yüklemeniz gerekir.';

  @override
  String get toggleControlBar => 'Kontrol Çubuğunu Değiştir';

  @override
  String get onboardingBluetoothDeniedSystemPrefs =>
      'Bluetooth izni reddedildi. Lütfen Sistem Tercihleri\'nde izin verin.';

  @override
  String get syncCancelled => 'Senkronizasyon iptal edildi';

  @override
  String get firmwareDisconnectUsb => 'USB\'yi çıkarın';

  @override
  String get processNow => 'Şimdi işle';

  @override
  String get appIdNotFoundError => 'Uygulama Kimliği bulunamadı';

  @override
  String get editDueDate => 'Son tarihi düzenle';

  @override
  String get home => 'Ana Sayfa';

  @override
  String get tasksOverdue => 'Gecikmiş';

  @override
  String get statusCompleted => 'Tamamlandı';

  @override
  String get otaStarting => 'Güncelleme başlatılıyor…';

  @override
  String get monthApr => 'Nis';

  @override
  String get conversationTasksEmptyMessage => 'Bu konuşmadaki görevler burada görünecek.';

  @override
  String get useDifferentAccount => 'Başka Bir Hesap Kullan';

  @override
  String get reviewReasonNotUseful => 'Faydalı değil';

  @override
  String get anonymousUser => 'Anonim Kullanıcı';

  @override
  String get viewPlansDescription => 'Aboneliğinizi yönetin ve kullanım istatistiklerini görün';

  @override
  String invalidJson(String error) {
    return 'Geçersiz JSON: $error';
  }

  @override
  String get deleteActionItem => 'Görevi sil';

  @override
  String get confirmCancellation => 'İptali Onayla';

  @override
  String get tapToDelete => 'Silmek için dokunun';

  @override
  String get onTheCallEnterThisCode => 'Arama sirasinda bu kodu girin';

  @override
  String get stableFirmware => 'Kararlı yazılım';

  @override
  String get triggerEvents => 'Tetikleyici Olaylar';

  @override
  String get speakerTagPromptSaveVoicesTitle => 'Adlandırdığın kişilerin seslerini hatırla';

  @override
  String get syncedFilesDeleted => 'Senkronize kayıtlar silindi';

  @override
  String get cloudStorageDesc =>
      'Yüklendikten sonra kayıtlarınız işlenir ve yazıya dökülür. Konuşmalar bir dakika içinde kullanılabilir olacaktır.';

  @override
  String get failedToUpdateFolder => 'Klasör güncellenemedi';

  @override
  String dreamReportFound(int fixes, int asks) {
    String _temp0 = intl.Intl.pluralLogic(
      fixes,
      locale: localeName,
      other: '$fixes düzeltme',
      one: '1 düzeltme',
    );
    String _temp1 = intl.Intl.pluralLogic(
      asks,
      locale: localeName,
      other: '$asks öneri',
      one: '1 öneri',
    );
    return '$_temp0 · $_temp1';
  }

  @override
  String get anotherPlatform => 'başka bir platform';

  @override
  String get wrappedTopPhrasesLabel => 'TOP İFADELER';

  @override
  String get dataAccessWarning =>
      'Bu uygulama verilerinize erişecek. Omi AI, bu uygulama tarafından verilerinizin nasıl kullanıldığı, değiştirildiği veya silindiğinden sorumlu değildir';

  @override
  String get pleaseCompleteAuthentication =>
      'Lütfen tarayıcınızda kimlik doğrulamayı tamamlayın. Tamamlandığında uygulamaya geri dönün.';

  @override
  String get dailySummaryTitle => 'Günlük Özet';

  @override
  String get managePeople => 'Kişileri Yönet';

  @override
  String get dreamReportEmptyBody => 'Dream, hesabında nelerin değiştiğine yaklaşık saatte bir bakar.';

  @override
  String get couldNotOpenPaymentSettings => 'Ödeme ayarları açılamadı. Lütfen tekrar deneyin.';

  @override
  String get locationServiceDisabled => 'Konum Servisi Devre Dışı';

  @override
  String get understanding => 'Anlama';

  @override
  String get recapDeleteFailed => 'Özet silinemedi. Daha sonra tekrar deneyin.';

  @override
  String get deleteKnowledgeGraphQuestion => 'Bilgi Grafiği Silinsin mi?';

  @override
  String get wrappedYourBuddy => 'Senin dostun!';

  @override
  String chatAppsChatIn(String app) {
    return '$app sohbeti';
  }

  @override
  String get speechDurationDescription => 'En az 5 saniye ve en fazla 90 saniye konuştuğunuzdan emin olun.';

  @override
  String get reviewReasonAlreadyDone => 'Zaten yapıldı';

  @override
  String get phoneSetupStep2Title => 'Dogrulama kodu girin';

  @override
  String get tasksClearCompleted => 'Tamamlananları temizle';

  @override
  String get searchingForDevices => 'Cihazlar aranıyor';

  @override
  String get siriIndexSettingDescription =>
      'Allow Siri to find your conversations, memories, and tasks on this device. Turning this off removes them from Apple search.';

  @override
  String get markIncomplete => 'Tamamlanmadı olarak işaretle';

  @override
  String get onboardingBluetoothRequired => 'Cihazınıza bağlanmak için Bluetooth izni gereklidir.';

  @override
  String get searchAppsPlaceholder => '1500+ Uygulamada Ara';

  @override
  String get pleaseEnterName => 'Lütfen bir ad girin';

  @override
  String get paymentMethodCharged =>
      'Aylık planınız sona erdiğinde mevcut ödeme yönteminiz otomatik olarak tahsil edilecek';

  @override
  String get allMemoriesAreNowPublic => 'Tüm anılar artık herkese açık';

  @override
  String taskDueDate(String date) {
    return 'Son tarih $date';
  }

  @override
  String get pendantPausesUntilYouFinish => 'Sen bitirene kadar kolye duraklar';

  @override
  String get failedToAuthorize => 'İzin verilemedi. Lütfen tekrar deneyin.';

  @override
  String get mergeConversationsSuccessTitle => 'Konuşmalar başarıyla birleştirildi';

  @override
  String get peopleFilterNeedsVoice => 'Ses Gerekli';

  @override
  String get clickToBeginRecordingSystemAudio => 'Sistem ses kaydını başlatmak için tıklayın';

  @override
  String get fairUseStageRestrict => 'Engelli';

  @override
  String get nextResult => 'Sonraki sonuç';

  @override
  String get chatAppsContactsApp => 'Rehber';

  @override
  String get categoryEmotionalSupport => 'Duygusal Destek';

  @override
  String get wrappedYourHeader => 'Senin';

  @override
  String get pendantPausesDuringCall => 'Arama sırasında kolye duraklar';

  @override
  String noConversationsOnDate(String date) {
    return '$date tarihinde konuşma yok';
  }

  @override
  String get chatStarterYesterday => 'Dün ne yaptım?';

  @override
  String get entityNotRight => 'Doğru değil mi?';

  @override
  String get failedToCreateShareLink => 'Paylaşım bağlantısı oluşturulamadı';

  @override
  String get sync => 'Senkronize Et';

  @override
  String get micGainDescMax => 'Maksimum - dikkatli kullanın';

  @override
  String get sttNone => 'Yok';

  @override
  String get chatAppsCodeNote => 'Kod yalnızca bir kez çalışır ve 10 dakika içinde sona erer.';

  @override
  String get aiGenAppCreatedSuccessfully => 'Uygulama başarıyla oluşturuldu!';

  @override
  String lastNEvents(int count) {
    return 'Son $count olay';
  }

  @override
  String get phoneDeleteButton => 'Sil';

  @override
  String get systemAudio => 'Sistem';

  @override
  String get checkOutMyMemoryGraph => 'Hafıza grafiğime göz atın!';

  @override
  String get feedbackTitleBatteryDrain => 'Pil sorunlarını bize anlatın';

  @override
  String get startCallRecording => 'Arama kaydını başlat';

  @override
  String get monthlyPlanContinues => 'Mevcut aylık planınız fatura döneminizin sonuna kadar devam edecek';

  @override
  String get syncStepUploadDesc => 'Kaydınız Omi\'nin sunucusuna gönderilir';

  @override
  String get otaKeepNearby => 'Güncelleme sırasında cihazınızı açık ve yakında tutun, uygulamayı kapatmayın.';

  @override
  String get updatePayPalDetails => 'PayPal Bilgilerini Güncelle';

  @override
  String get termsOfUse => 'Kullanım Koşulları';

  @override
  String get apiKeyCreated => 'API Anahtarı Oluşturuldu!';

  @override
  String get deviceOnboardingVoiceReplyPreviewIdle => 'Son yanıtını duy';

  @override
  String get starOngoing => 'Devam Eden Konuşmayı Favorilere Ekle';

  @override
  String get largeModelWarning =>
      'Bu model büyük ve uygulamanın çökmesine veya mobil cihazlarda çok yavaş çalışmasına neden olabilir.\n\n\"small\" veya \"base\" önerilir.';

  @override
  String get selectLanguage => 'Dil Seç';

  @override
  String get professionExecutive => 'Yönetici';

  @override
  String get importFileTooLarge => 'Bu dosya içe aktarmak için çok büyük.';

  @override
  String get updateRequiredTitle => 'Güncelleme gerekli';

  @override
  String get syncStepBackedUp => 'Konuşma hazır';

  @override
  String get openWatchApp => 'Watch Uygulamasını Aç';

  @override
  String get keyNameLabel => 'ANAHTAR ADI';

  @override
  String bulkExportSuccess(int count, String platform) {
    return '$count öğe $platform uygulamasına aktarıldı';
  }

  @override
  String get couldNotProcessSubscription => 'Abonelik işlenemedi. Lütfen tekrar deneyin.';

  @override
  String get memorizingYourVoice => 'Sesiniz hatırlanıyor…';

  @override
  String get processingAudio => 'Ses İşleniyor';

  @override
  String get syncYourRecordings => 'Kayıtlarınızı senkronize edin';

  @override
  String get resetToDefault => 'Varsayılana sıfırla';

  @override
  String get deleteConversation => 'Sohbeti Sil';

  @override
  String get flashCustomFirmwareDescription => 'Özel yazılım sürümleri yükleyin';

  @override
  String get deviceUpToDate => 'Cihazınız güncel';

  @override
  String get raybanMetaMusicPauseNote => 'Gözlüğün mikrofonu kullanılırken telefonunuzdaki müzik duraklatılır.';

  @override
  String get appleHealthNotAvailable => 'Apple Health bu cihazda kullanılamıyor';

  @override
  String hints(String text) {
    return 'İpuçları: $text';
  }

  @override
  String get cloudProvider => 'Bulut Sağlayıcı';

  @override
  String get chooseAnyFileType => 'Herhangi bir dosya türü seçin';

  @override
  String get reset => 'Sıfırla';

  @override
  String get automaticallyCreateNewPerson =>
      'Transkriptte bir ad algılandığında otomatik olarak yeni bir kişi oluştur.';

  @override
  String get timeout2Minutes => '2 dakika';

  @override
  String get newMemory => '✨ Yeni hafıza';

  @override
  String get chatAppsMoreComing => 'Daha fazla uygulama geliyor.';

  @override
  String get couldNotLoadKnowledgeGraph => 'Bilgi grafiği yüklenemedi';

  @override
  String get voiceSettingsAskToTagSubtitle => 'Omi arada bir, son konuşmalarında kimin konuştuğunu sorar';

  @override
  String get developer => 'Geliştirici';

  @override
  String get connectionNeeded => '🌐 Bağlantı gerekli';

  @override
  String get helpAndAbout => 'Yardım ve Hakkında';

  @override
  String get tasksNoDeadline => 'Son tarih yok';

  @override
  String get yourDataIsProtected => 'Verileriniz korunmaktadır ve ';

  @override
  String get confirmDeletion => 'Silmeyi Onayla';

  @override
  String get speakerTagPromptClosestVoices => 'En yakın sesler';

  @override
  String get quicklyPopulateRequest => 'Bilinen sağlayıcı istek formatıyla hızlıca doldur';

  @override
  String get exportTranscript => 'Transkripti dışa aktar';

  @override
  String get resetsSoon => 'Yakında sıfırlanır';

  @override
  String get showPhoneCallButtonTitle => 'Arama Düğmesini Göster';

  @override
  String get wrappedAChallenge => 'Bir Zorluk';

  @override
  String get revokeKey => 'Anahtarı iptal et';

  @override
  String get dailyRecaps => 'Günlük Özetler';

  @override
  String get processingConversationProgress => 'Konuşma işleniyor…';

  @override
  String get freeMinutesMonth => 'Ayda 300 ücretsiz dakika dahildir. ';

  @override
  String get downloadWhisperModel => 'Cihaz üzerinde transkripsiyonu kullanmak için bir whisper modeli indirin';

  @override
  String get noMemoriesInCategories => 'Bu kategorilerde anı yok';

  @override
  String get checkingNextDays => 'Sonraki 30 gün kontrol ediliyor';

  @override
  String get createAndSubmitNewApp => 'Yeni bir uygulama oluştur ve gönder';

  @override
  String get chatAppsInTheMeantime => 'Bu arada';

  @override
  String get deleteFlowReasonTitle => 'Neden ayrılıyorsun?';

  @override
  String get tasksSelectAll => 'Tümünü seç';

  @override
  String get webhookUrl => 'Webhook URL\'si';

  @override
  String get selected => 'Seçildi';

  @override
  String get batteryDrainIncrease => 'Pil tüketimi önemli ölçüde artacaktır.';

  @override
  String get dreamReportFixed => 'Düzeltildi';

  @override
  String get failedToConnectClickUpRetry => 'ClickUp\'a bağlanılamadı. Lütfen tekrar deneyin.';

  @override
  String get serverUrl => 'Sunucu URL\'si';

  @override
  String get starred => 'Yıldızlı';

  @override
  String get speakerTagPromptClipUnavailable => 'Bu klip oynatılamadı';

  @override
  String get feedbackSubtitleFoundAlternative => 'Dikkatinizi çeken şeyi öğrenmek isteriz.';

  @override
  String get omiButtonActions => 'Omi Düğme İşlemleri';

  @override
  String get invalidRecordingDesc => 'Lütfen en az 5 saniye, en fazla 90 saniye konuştuğunuzdan emin olun.';

  @override
  String get switchApiConfirmTitle => 'API Ortamını Değiştir';

  @override
  String gattError(String code) {
    return 'GATT hatası ($code)';
  }

  @override
  String get aiGenRegenerateIcon => 'Simgeyi yeniden oluştur';

  @override
  String get connectTaskAppToExport => 'Dışa aktarmak için Ayarlar\'da bir görev uygulaması bağlayın';

  @override
  String get firmwareFlashed => 'Yazılım yüklendi';

  @override
  String get addPerson => 'Kişi Ekle';

  @override
  String get cancelConsequencesSubtitle =>
      'İptal etmek yerine diğer seçeneklerinizi keşfetmenizi şiddetle tavsiye ediyoruz.';

  @override
  String get transcriptCopiedToClipboard => 'Transkript panoya kopyalandı';

  @override
  String get monthNov => 'Kas';

  @override
  String get switchedToOnDevice => 'Cihaz üzerinde transkripsiyona geçildi';

  @override
  String get phoneMicOfflineFallbackMessage =>
      'Bağlantı yok — yerel olarak kaydediliyor. Tekrar çevrimiçi olduğunuzda yazıya dökülecek.';

  @override
  String get scopeUserConversations => 'Kullanıcı Konuşmaları';

  @override
  String get otherAppResults => 'Diğer Uygulama Sonuçları';

  @override
  String get chatAppsGetNewCode => 'Yeni Kod Al';

  @override
  String get backgroundLocationDenied => 'Arka Plan Konum Erişimi Reddedildi';

  @override
  String get syncFailureFootnote =>
      'İşlem başarısız olursa, kayıt bir sonraki eşitlemede otomatik olarak yeniden denenir.';

  @override
  String get checkingNext7Days => 'Sonraki 7 gün kontrol ediliyor';

  @override
  String get monthlyPayouts => 'Aylık ödemeler';

  @override
  String get searchLanguageHint => 'Dili isim veya koda göre arayın';

  @override
  String get gotIt => 'Anladım';

  @override
  String get pleaseEnterAppName => 'Lütfen uygulama adını girin';

  @override
  String get newConversations => 'Yeni Konuşmalar';

  @override
  String get learnMoreAtOmiTraining => 'omi.me/training adresinde daha fazla bilgi edinin';

  @override
  String get entityOpenTasks => 'Açık görevler';

  @override
  String get summary => 'Özet';

  @override
  String get copied => 'Kopyalandı';

  @override
  String get feedbackReasonRecordingDelayedOrStuck => 'Gecikmeli veya takılı';

  @override
  String get taskIntegrations => 'Görev Entegrasyonları';

  @override
  String get tailoredConversationSummaries => 'Özelleştirilmiş Konuşma Özetleri';

  @override
  String get skipThisQuestion => 'Bu soruyu atla';

  @override
  String get descriptionOptional => 'Açıklama (isteğe bağlı)';

  @override
  String get about => 'Hakkında';

  @override
  String shareWithContactsCount(int count) {
    return '$count kişiyle paylaş';
  }

  @override
  String get discardChangesTitle => 'Değişiklikler silinsin mi?';

  @override
  String get transcriptionDiagnostics => 'Transkripsiyon Tanılaması';

  @override
  String get syncStatusFileUnavailable => 'Dosya kullanılamıyor';

  @override
  String get createNewApp => 'Yeni Uygulama Oluştur';

  @override
  String verifiedHoursAgo(int hours) {
    return '${hours}sa once dogrulandi';
  }

  @override
  String get chatLimitReachedTitle => 'Sohbet limiti doldu';

  @override
  String get wrappedShareText => '2025\'im, Omi tarafından hatırlandı ✨ omi.me/wrapped';

  @override
  String get reconnectionsRecent => 'Yeniden bağlantılar (son 7 gün)';

  @override
  String get appAccess => 'Uygulama Erişimi';

  @override
  String get description => 'Açıklama';

  @override
  String phoneFreeCallsRemainingWithMax(int remaining, int limit, int minutes) {
    return 'Bu ay $remaining ücretsiz arama kaldı ($limit aramadan) · her biri en fazla $minutes dk';
  }

  @override
  String get clearOmisMemory => 'Omi\'nin Belleğini Temizle';

  @override
  String get exportSummary => 'Özeti dışa aktar';

  @override
  String get install => 'Yükle';

  @override
  String get syncStepBackedUpDesc => 'Konuşmalar altında bulabilirsin';

  @override
  String get localProcessingInfo =>
      'Ses yerel olarak işlenir. Çevrimdışı çalışır, daha güvenlidir, ancak daha fazla pil kullanır.';

  @override
  String get connectStripeOrPayPal => 'Uygulamanız için ödeme almak üzere Stripe veya PayPal\'ı bağlayın.';

  @override
  String get wrappedMomentsHeader => 'Anlar';

  @override
  String get systemDefault => 'Sistem Varsayılanı';

  @override
  String get keepUsingPendant => 'Kolyeyi kullanmaya devam et';

  @override
  String get paymentFailedToFetchCountries => 'Desteklenen ülkeler alınamadı. Daha sonra tekrar deneyin.';

  @override
  String get micGainDescLow => 'Çok sessiz - gürültülü ortamlar için';

  @override
  String get errorUpdatingConversationTitle => 'Sohbet başlığı güncellenirken hata oluştu';

  @override
  String timeSecsSingular(int count) {
    return '$count sn';
  }

  @override
  String timeCompactHours(int count) {
    return '${count}sa';
  }

  @override
  String get browseInstallCreateApps => 'Uygulamalara göz atın, yükleyin ve oluşturun';

  @override
  String get reddit => 'Reddit';

  @override
  String get chooseFile => 'Dosya Seç';

  @override
  String participantsSummary(String name, int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count kişi daha',
      many: '$count kişi daha',
      few: '$count kişi daha',
      one: '1 kişi daha',
    );
    return '$name + $_temp0';
  }

  @override
  String get connectingYourStripeAccount => 'Stripe hesabınız bağlanıyor';

  @override
  String get cancelReasonMissingFeatures => 'Eksik özellikler';

  @override
  String get chatTitle => 'Sohbet';

  @override
  String get chatAppsNotifyMe => 'Bana Haber Ver';

  @override
  String get appAccessDesc =>
      'Aşağıdaki uygulamalar verilerinize erişebilir. İzinlerini yönetmek için bir uygulamaya dokunun.';

  @override
  String get captureDisplayDetectionFailed => 'Ekran algılama başarısız. Kayıt durduruldu.';

  @override
  String get recapRegeneratedSnackbar => 'Özet yeniden oluşturuldu';

  @override
  String get speakerTagPromptLabeledYouToast => 'Siz olarak etiketlendi';

  @override
  String get categoryFinancial => 'Finans';

  @override
  String get chatAppsPrefilled => 'Önceden dolduruldu';

  @override
  String get noSummaryForConversation => 'Bu konuşma için\nözet mevcut değil.';

  @override
  String get aiPrompts => 'Yapay Zeka Yönlendirmeleri';

  @override
  String get view => 'Görüntüle';

  @override
  String get dataAlwaysEncrypted =>
      'Seviyeden bağımsız olarak, verileriniz her zaman dinlenme halinde ve aktarım sırasında şifrelenir.';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item panoya kopyalandı';
  }

  @override
  String get currentPlan => 'Mevcut';

  @override
  String get phoneCallsUpsellFeature1 => 'Her aramanın gerçek zamanlı transkripsiyonu';

  @override
  String get lowBatteryAlertTitle => 'Düşük Pil Uyarısı';

  @override
  String get enterConversationTitle => 'Sohbet başlığı girin…';

  @override
  String get pasteJsonConfig => 'JSON yapılandırmanızı aşağıya yapıştırın:';

  @override
  String get dreamReportRunLimit => 'Bugün manuel çalıştırma hakkı kalmadı';

  @override
  String get translationNoticeMessage =>
      'Omi konuşmaları birincil dilinize çevirir. İstediğiniz zaman Ayarlar → Profiller\'de güncelleyin.';

  @override
  String get aiGenFailedToRegenerateIcon => 'Simge yeniden oluşturulamadı';

  @override
  String get pairingDescBee => 'Düğmeye art arda 5 kez basın. Işık mavi ve yeşil yanıp sönmeye başlayacaktır.';

  @override
  String sharedTasksAddButton(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count Görev Ekle',
      one: '1 Görev Ekle',
    );
    return '$_temp0';
  }

  @override
  String get paymentFailedToSavePaypal => 'PayPal bilgileri kaydedilemedi. Daha sonra tekrar deneyin.';

  @override
  String get couldNotLoadCheckout => 'Ödeme sayfası yüklenemedi. Bağlantını kontrol edip tekrar dene.';

  @override
  String get capabilitySummary => 'Özet';

  @override
  String get selectYourCountry => 'Ülkenizi seçin';

  @override
  String uploadingAudioForTranscription(String duration) {
    return '$duration ses transkripsiyon için yükleniyor…';
  }

  @override
  String get conversationUrlCouldNotBeShared => 'Konuşma URL\'si paylaşılamadı.';

  @override
  String get otaStartFailed => 'Güncelleme başlatılamadı. Wi-Fi adını ve şifresini kontrol edip tekrar deneyin.';

  @override
  String get triggersWhenAudioBytesReceived => 'Ses baytları alındığında tetiklenir.';

  @override
  String get wrappedMy2025 => '2025\'im';

  @override
  String timeCompactSecs(int count) {
    return '${count}sn';
  }

  @override
  String get shareWithAttendees => 'Katılımcılarla Paylaş';

  @override
  String get recordingsSyncAutomatically => 'Kayıtlar otomatik olarak senkronize edilir — herhangi bir işlem gerekmez.';

  @override
  String get whereDidYouHearAboutOmi => 'Bizi nasıl buldunuz?';

  @override
  String get captureMicrophonePermissionInSystemPreferences => 'Sistem Tercihleri\'nde mikrofon izni verin';

  @override
  String audioUploadFailedTapRetry(String duration) {
    return 'Yükleme başarısız — $duration ses telefonunuzda saklanıyor. Yeniden denemek için dokunun.';
  }

  @override
  String get captureModeLaterDescription => 'Sesi şimdi kaydedin ve istediğiniz zaman yazıya dökün.';

  @override
  String get cleanUpNothingTitle => 'Temizlenecek Bir Şey Yok';

  @override
  String get deletePersonLabel => 'Kişiyi sil';

  @override
  String get attachedFiles => '📎 Ekli Dosyalar';

  @override
  String get editGoal => 'Hedefi Düzenle';

  @override
  String get helpsDiagnoseIssues => 'Sorunları teşhis etmeye yardımcı olur';

  @override
  String get bulkDeleteFailed => 'Görevler silinemedi. Lütfen tekrar deneyin.';

  @override
  String get manifestRefreshFailed => 'Manifest yenilenemedi';

  @override
  String get searchPlaceholder => 'Ara';

  @override
  String get appOptions => 'Uygulama seçenekleri';

  @override
  String get reprocessingConversationProgress => 'Konuşma yeniden işleniyor…';

  @override
  String get entityWhatOmiKnows => 'Omi’nin bildikleri';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'Konuşma $minutes dakika$suffix sessizlik sonrası özetlenir.';
  }

  @override
  String get permissionRevokedMessage => 'Mevcut tüm kayıtlarınızı da kaldırmamızı ister misiniz?';

  @override
  String get phoneNumberCallerIdHint => 'Dogrulamadan sonra bu arayan kimliginiz olur';

  @override
  String chatAppsTextThisTo(String address) {
    return 'Açılmadı mı? Bunu $address numarasına gönder';
  }

  @override
  String get upcomingMeetings => 'Yaklaşan Toplantılar';

  @override
  String get preparingSystemAudioCapture => 'Sistem ses kaydı hazırlanıyor';

  @override
  String dreamReportQueued(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count değişiklik bekliyor',
      one: '1 değişiklik bekliyor',
      zero: 'Bekleyen değişiklik yok',
    );
    return '$_temp0';
  }

  @override
  String get chatReplyFailed => 'Omi yanıt veremedi. Bağlantını kontrol edip tekrar dene.';

  @override
  String get noDataToMigrateFinalizing => 'Taşınacak veri yok. Tamamlanıyor…';

  @override
  String get accessibility => 'Erişilebilirlik';

  @override
  String get openOmiOnAppleWatch => 'Apple Watch\'unuzda\nOmi\'yi açın';

  @override
  String get wrappedGettingItDone => 'Başarmak';

  @override
  String get rawData => 'Ham Veri';

  @override
  String get passwordsDoNotMatch => 'Şifreler eşleşmiyor';

  @override
  String errorInstallingApp(String appName, String error) {
    return '$appName yüklenirken hata oluştu: $error';
  }

  @override
  String deleteQuoted(String name) {
    return '\"$name\" öğesini sil';
  }

  @override
  String get wrappedTopFivePhrases => 'En İyi 5 İfade';

  @override
  String get deviceOnboardingHoldButtonHint => 'Işık sönene kadar düğmeyi sıkıca basılı tutun';

  @override
  String get capabilities => 'Yetenekler';

  @override
  String get useMcpApiKey => 'MCP API anahtarınızı kullanın';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return '$serviceName entegrasyonu yakında';
  }

  @override
  String get wrappedStruggle => 'Zorluk';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return 'Bildirim izin durumu: $status. Lütfen Sistem Tercihleri\'ni kontrol edin.';
  }

  @override
  String get meetingScreenshotsTitle => 'Ekranda olanlar';

  @override
  String verifiedMinutesAgo(int minutes) {
    return '${minutes}dk once dogrulandi';
  }

  @override
  String get permissionsRequired => 'İzinler gerekli';

  @override
  String get speakerTagPromptNotSure => 'Emin değilim';

  @override
  String get current => 'Mevcut';

  @override
  String get improveConnectionAction => 'Anladım';

  @override
  String get profile => 'Profil';

  @override
  String get audioPlaybackFailed => 'Ses oynatılamıyor. Dosya bozuk veya eksik olabilir.';

  @override
  String get billingYearly => 'Yıllık';

  @override
  String get batteryUsageHigher => 'Pil kullanımı bulut transkripsiyonundan daha yüksek olacaktır.';

  @override
  String get permissionsLabel => 'İZİNLER';

  @override
  String get enhanceTranscriptAccuracy => 'Transkript Doğruluğunu Artırın';

  @override
  String get connectedStatus => 'Bağlandı';

  @override
  String get microphonePermissionDenied =>
      'Mikrofon izni reddedildi. Lütfen Sistem Tercihleri > Gizlilik ve Güvenlik > Mikrofon\'da izin verin.';

  @override
  String get onDeviceModelDownloadSuccessDesc => 'Whisper modeli başarıyla indirildi';

  @override
  String get storageLocationLimitlessPendant => 'Limitless Kolye';

  @override
  String get chatAppsLinkExpired => 'Bu bağlantının süresi doldu. Yenisi için Telegram\'ı Aç\'a dokun.';

  @override
  String get captureOfflineBuffering => 'Çevrimdışı, arabelleğe alınıyor';

  @override
  String get pleaseCheckInternetConnection => 'Lütfen internet bağlantınızı kontrol edin ve tekrar deneyin';

  @override
  String get todaysScore => 'Bugünün Skoru';

  @override
  String get conversationReprocessed => 'Konuşma güncellendi';

  @override
  String get loadingDuration => 'Süre yükleniyor…';

  @override
  String get noSummary => 'Özet yok';

  @override
  String get raybanMetaMicrophoneReady => 'Mikrofon hazır';

  @override
  String get applyFilters => 'Filtreleri uygula';

  @override
  String get appDescriptionPlaceholder =>
      'Harika Uygulamam harika şeyler yapan harika bir uygulamadır. En iyi uygulama!';

  @override
  String get cancelSubscriptionKeepAccessMessage => 'Mevcut fatura döneminin sonuna kadar erişimin devam eder.';

  @override
  String get editYourReview => 'Değerlendirmenizi Düzenleyin';

  @override
  String get actionItemsTitle => 'Görevler';

  @override
  String get raybanMetaAudioOnlyTitle => 'Ray-Ban Meta yalnızca ses modu';

  @override
  String get reviewSomeoneElse => 'Başka biri…';

  @override
  String get betaTesterMessage =>
      'Bu uygulamanın beta test kullanıcısısınız. Henüz herkese açık değil. Onaylandıktan sonra herkese açık olacak.';

  @override
  String chatAppsIMessageTo(String address) {
    return 'Kime: Omi · $address';
  }

  @override
  String get comingSoon => 'Yakında';

  @override
  String rollbackConfirmMessage(String version) {
    return 'Bu, mevcut yazılımınızı en son kararlı sürümle ($version) değiştirecektir. Güncelleme sonrasında cihazınız yeniden başlatılacaktır.';
  }

  @override
  String get termsOfService => 'Hizmet Koşullarını';

  @override
  String get wrappedNotMentioned => 'Bahsedilmedi';

  @override
  String get deviceDisconnectedNotificationTitle => 'Omi Cihazınız Bağlantı Kesildi';

  @override
  String get rayBanMetaMicPickerDescription =>
      'Gözlüğünüzün Bluetooth mikrofonunu seçin. Omi mikrofonu kullanırken müzik duraklatılır.';

  @override
  String get chatBlockQuestion => 'Soru';

  @override
  String get successfullyConnectedTodoist => 'Todoist\'a başarıyla bağlanıldı!';

  @override
  String voiceRecognitionStatus(String status) {
    String _temp0 = intl.Intl.selectLogic(
      status,
      {
        'ready': 'Ses tanınmaya hazır',
        'saved_sample_awaiting_embedding': 'Örnek kaydedildi; sesin işlenmesi hâlâ gerekiyor',
        'not_learned': 'Ses öğrenilmedi',
        'other': 'Ses durumu bilinmiyor',
      },
    );
    return '$_temp0';
  }

  @override
  String addQueryAsNewPerson(String query) {
    return '\"$query\" adlı yeni bir kişi ekle';
  }

  @override
  String confidenceReasonAutoConfirmed(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count otomatik etiketi onayladınız',
      one: '1 otomatik etiketi onayladınız',
    );
    return '$_temp0';
  }

  @override
  String get recordAudioConversations => 'Sesli konuşmaları kaydet';

  @override
  String get saveKeyWarning => 'Bu anahtarı şimdi kaydedin! Tekrar göremeyeceksiniz.';

  @override
  String get saveChanges => 'Değişiklikleri kaydet';

  @override
  String get sttModelSlower => 'Daha yavaş';

  @override
  String get otaDownloadFailed => 'Yazılım indirilemedi. Wi-Fi bağlantısını kontrol edip tekrar deneyin.';

  @override
  String get captureRecordingViewing => 'Bu kaydı görüntülüyorsunuz';

  @override
  String get resetFilters => 'Filtreleri sıfırla';

  @override
  String get voiceSettingsSaveOthersSubtitle =>
      'Birine ad verdiğinde Omi, onu bir dahaki sefere tanıyabilmek için kısa bir ses örneği saklar';

  @override
  String get iveDoneThis => 'Bunu yaptım';

  @override
  String get howSyncingWorks => 'Senkronizasyon nasıl çalışır';

  @override
  String greetingWithName(String greeting, String name) {
    return '$greeting, $name';
  }

  @override
  String reviewRemaining(int count) {
    return '$count kaldı';
  }

  @override
  String get feedbackReasonRecordingMissingAudio => 'Ses eksik';

  @override
  String get appCategoryModalTitle => 'Uygulama Kategorisi';

  @override
  String get pushToTalk => 'Konuşmak için Bas';

  @override
  String get noApiKeysYet => 'Henüz API anahtarı yok. Uygulamanızla entegre etmek için bir tane oluşturun.';

  @override
  String minLabel(int count) {
    return '$count dk';
  }

  @override
  String appRatingCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count puan',
      one: '1 puan',
    );
    return '$_temp0';
  }

  @override
  String get wrappedFood => 'YİYECEK';

  @override
  String get aboutAMinuteRemaining => 'Yaklaşık bir dakika kaldı';

  @override
  String get clearLogs => 'Günlükleri temizle';

  @override
  String get wrappedBook => 'KİTAP';

  @override
  String get phoneCallSubtitle => 'Canlı transkripsiyonla bir aramayı kaydedin';

  @override
  String deleteConversationsTitle(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count konuşma silinsin mi?',
      one: '1 konuşma silinsin mi?',
    );
    return '$_temp0';
  }

  @override
  String get deleteSelected => 'Seçilenleri sil';

  @override
  String failedToDeleteGraph(String error) {
    return 'Grafik silinemedi: $error';
  }

  @override
  String get setupQuestionsIntro => 'Birkaç soruyu yanıtlayarak Omi\'yi geliştirmemize yardımcı olun.  🫶 💜';

  @override
  String get category => 'Kategori';

  @override
  String get timeout30MinutesDesc => '30 dakika sessizlikten sonra konuşmayı sonlandır';

  @override
  String get goalDeleted => 'Hedef silindi';

  @override
  String get conversationDisplay => 'Konuşma Görüntüleme';

  @override
  String get conversationNoSummaryYet => 'Bu konuşmanın henüz bir özeti yok.';

  @override
  String get chatsLowercase => 'sohbetler';

  @override
  String get clearChatQuestion => 'Sohbeti temizle?';

  @override
  String get signInTitle => 'Giriş Yap';

  @override
  String get loadingKnowledgeGraph => 'Bilgi grafiği yükleniyor…';

  @override
  String get goalTracker => 'Hedef İzleyici';

  @override
  String get commandRequired => '⌘ gerekli';

  @override
  String get permissionEnabled => 'Etkin';

  @override
  String get submitReview => 'Değerlendirmeyi Gönder';

  @override
  String chatUsageCost(String used, String limit) {
    return 'Sohbet: \$$used / \$$limit bu ay kullanıldı';
  }

  @override
  String get discard => 'Vazgeç';

  @override
  String dreamReportPasses(int count, int limit) {
    return 'Bugün $count/$limit tur';
  }

  @override
  String get unlockOmiInfiniteMemory => 'Sınırsız anı';

  @override
  String get addAppPersonaConflictWithCapabilities => 'Persona diğer yeteneklerle birlikte seçilemez';

  @override
  String get whyAreYouCanceling => 'Neden iptal ediyorsunuz?';

  @override
  String get permissionRequestedExclaim => 'İzin İstendi!';

  @override
  String get chatBlockOpenInMemories => 'Anılar’da aç';

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total nesne';
  }

  @override
  String get deleteActionItemTitle => 'Görevi sil';

  @override
  String get rollBack => 'Geri Al';

  @override
  String get chatAppsOmiPro => 'OMI PRO';

  @override
  String disconnectFromAppDesc(String appName) {
    return 'Bu, $appName kimlik doğrulamanızı kaldıracaktır. Tekrar kullanmak için yeniden bağlanmanız gerekecek.';
  }

  @override
  String get onDeviceModelSize => 'Model Boyutu';

  @override
  String tagSpeaker(int speakerId) {
    return 'Konuşmacıyı Etiketle $speakerId';
  }

  @override
  String get couldNotOpenUrl => 'URL açılamadı. Lütfen tekrar deneyin.';

  @override
  String get conversationNewIndicator => 'Yeni';

  @override
  String get notEnoughSpeechDescription =>
      'Yeterli konuşma tespit edilmedi. Lütfen daha fazla konuşun ve tekrar deneyin.';

  @override
  String get liveRssiOverTime => 'Zaman içinde canlı RSSI';

  @override
  String get usageEverywhere => 'Her Yerde';

  @override
  String nConversations(int count) {
    return '$count konuşma';
  }

  @override
  String get wrappedConversationsLabel => 'sohbet';

  @override
  String get usageYear => 'Bu Yıl';

  @override
  String get noContactsMatchSearch => 'Aramanızla eşleşen kişi yok';

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count görev$s silindi';
  }

  @override
  String get actionItemMarkedIncomplete => 'Görev tamamlanmamış olarak işaretlendi';

  @override
  String get start => 'Başlat';

  @override
  String discardedConversationTitle(String duration) {
    return 'Atıldı · $duration';
  }

  @override
  String get debugLogsCleared => 'Hata ayıklama günlükleri temizlendi';

  @override
  String get preparingAudioCapture => 'Ses kaydı hazırlanıyor';

  @override
  String get availablePaymentMethods => 'Mevcut Ödeme Yöntemleri';

  @override
  String get deleteReasonOther => 'Diğer';

  @override
  String get accountCutoverMigrationInProgressTitle => 'Taşıma devam ediyor';

  @override
  String get connectedKnowledgeData => 'Bağlı Bilgi Verisi';

  @override
  String get wrappedMostFunDay => 'En Eğlenceli';

  @override
  String get onboardingAccessibilityRequired =>
      'Tarayıcı toplantılarını algılamak için erişilebilirlik izni gereklidir.';

  @override
  String get selectActionItems => 'Birden fazla seç';

  @override
  String switchApiConfirmBody(String environment) {
    return '$environment ortamına geçilsin mi? Değişikliklerin geçerli olması için uygulamayı kapatıp yeniden açmanız gerekecek.';
  }

  @override
  String get whisperModelSizeLarge => 'Büyük';

  @override
  String get currentVersion => 'Mevcut Sürüm';

  @override
  String get aiAppGeneratorBannerTitle => 'Tek dokunuşla yapay zekâyla uygulama oluştur';

  @override
  String get rayBanMetaMicPickerLoadError =>
      'Bluetooth mikrofonları yüklenemedi. Bluetooth\'un açık olduğunu kontrol edip tekrar deneyin.';

  @override
  String get noneSelected => 'Seçilmedi';

  @override
  String get entityKeptCurrent => 'Omi tarafından güncel tutuluyor';

  @override
  String migratingFromTo(String source, String target) {
    return '$source konumundan $target konumuna geçiş yapılıyor';
  }

  @override
  String get controlNotificationFrequency =>
      'Omi\'nin size ne sıklıkta proaktif bildirimler göndereceğini kontrol edin.';

  @override
  String get connectionUptime => 'Çalışma Süresi';

  @override
  String get categoryLabel => 'Kategori';

  @override
  String get aboutTheApp => 'Uygulama Hakkında';

  @override
  String get planSheetChooseYourPlan => 'Sana uygun planı seç.';

  @override
  String get almostDone => 'Neredeyse tamamlandı…';

  @override
  String get tasksFromConversationsWillAppear =>
      'Konuşmalarınızdaki görevler burada görünecek.\nManuel olarak eklemek için Oluştur\'a tıklayın.';

  @override
  String get personLastHeard => 'Son duyulma';

  @override
  String get durationThreshold => 'Süre Eşiği';

  @override
  String get transcriptionServiceDiagnosticStatus => 'Transkripsiyon hizmeti tanı durumu';

  @override
  String get triggersWhenNewTranscriptReceived => 'Yeni bir transkript alındığında tetiklenir.';

  @override
  String get aboutOmi => 'Omi Hakkında';

  @override
  String get identifyingOthers => 'Diğerlerini Tanımlama';

  @override
  String get phoneCallsSubtitle => 'Gercek zamanli transkripsiyon ile arayin';

  @override
  String get creatingYourApp => 'Uygulamanız oluşturuluyor…';

  @override
  String get analyzingYourData => 'Verileriniz analiz ediliyor…';
}
