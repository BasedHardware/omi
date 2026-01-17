// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Vietnamese (`vi`).
class AppLocalizationsVi extends AppLocalizations {
  AppLocalizationsVi([String locale = 'vi']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'Cuộc trò chuyện';

  @override
  String get transcriptTab => 'Bản ghi';

  @override
  String get actionItemsTab => 'Việc cần làm';

  @override
  String get deleteConversationTitle => 'Xóa cuộc trò chuyện?';

  @override
  String get deleteConversationMessage => 'Bạn có chắc chắn muốn xóa cuộc trò chuyện này? Hành động này không thể hoàn tác.';

  @override
  String get confirm => 'Xác nhận';

  @override
  String get cancel => 'Hủy';

  @override
  String get ok => 'Ok';

  @override
  String get delete => 'Xóa';

  @override
  String get add => 'Thêm';

  @override
  String get update => 'Cập nhật';

  @override
  String get save => 'Lưu';

  @override
  String get edit => 'Chỉnh sửa';

  @override
  String get close => 'Đóng';

  @override
  String get clear => 'Xóa sạch';

  @override
  String get copyTranscript => 'Sao chép bản ghi';

  @override
  String get copySummary => 'Sao chép tóm tắt';

  @override
  String get testPrompt => 'Thử nghiệm';

  @override
  String get reprocessConversation => 'Xử lý lại cuộc trò chuyện';

  @override
  String get deleteConversation => 'Xóa cuộc trò chuyện';

  @override
  String get contentCopied => 'Đã sao chép nội dung vào clipboard';

  @override
  String get failedToUpdateStarred => 'Không thể cập nhật trạng thái gắn sao.';

  @override
  String get conversationUrlNotShared => 'Không thể chia sẻ URL cuộc trò chuyện.';

  @override
  String get errorProcessingConversation => 'Lỗi khi xử lý cuộc trò chuyện. Vui lòng thử lại sau.';

  @override
  String get noInternetConnection => 'Không có kết nối internet';

  @override
  String get unableToDeleteConversation => 'Không thể xóa cuộc trò chuyện';

  @override
  String get somethingWentWrong => 'Đã có lỗi xảy ra! Vui lòng thử lại sau.';

  @override
  String get copyErrorMessage => 'Sao chép thông báo lỗi';

  @override
  String get errorCopied => 'Đã sao chép thông báo lỗi vào clipboard';

  @override
  String get remaining => 'Còn lại';

  @override
  String get loading => 'Đang tải...';

  @override
  String get loadingDuration => 'Đang tải thời lượng...';

  @override
  String secondsCount(int count) {
    return '$count giây';
  }

  @override
  String get people => 'Mọi người';

  @override
  String get addNewPerson => 'Thêm người mới';

  @override
  String get editPerson => 'Chỉnh sửa người';

  @override
  String get createPersonHint => 'Tạo một người mới và huấn luyện Omi để nhận biết giọng nói của họ!';

  @override
  String get speechProfile => 'Hồ sơ Giọng nói';

  @override
  String sampleNumber(int number) {
    return 'Mẫu $number';
  }

  @override
  String get settings => 'Cài đặt';

  @override
  String get language => 'Ngôn ngữ';

  @override
  String get selectLanguage => 'Chọn ngôn ngữ';

  @override
  String get deleting => 'Đang xóa...';

  @override
  String get pleaseCompleteAuthentication => 'Vui lòng hoàn tất xác thực trong trình duyệt của bạn. Sau khi hoàn tất, hãy quay lại ứng dụng.';

  @override
  String get failedToStartAuthentication => 'Không thể bắt đầu xác thực';

  @override
  String get importStarted => 'Đã bắt đầu nhập dữ liệu! Bạn sẽ được thông báo khi hoàn tất.';

  @override
  String get failedToStartImport => 'Không thể bắt đầu nhập dữ liệu. Vui lòng thử lại.';

  @override
  String get couldNotAccessFile => 'Không thể truy cập tệp đã chọn';

  @override
  String get askOmi => 'Hỏi Omi';

  @override
  String get done => 'Xong';

  @override
  String get disconnected => 'Đã ngắt kết nối';

  @override
  String get searching => 'Đang tìm kiếm...';

  @override
  String get connectDevice => 'Kết nối thiết bị';

  @override
  String get monthlyLimitReached => 'Bạn đã đạt đến giới hạn hàng tháng.';

  @override
  String get checkUsage => 'Kiểm tra mức sử dụng';

  @override
  String get syncingRecordings => 'Đang đồng bộ bản ghi âm';

  @override
  String get recordingsToSync => 'Bản ghi âm cần đồng bộ';

  @override
  String get allCaughtUp => 'Đã đồng bộ tất cả';

  @override
  String get sync => 'Đồng bộ';

  @override
  String get pendantUpToDate => 'Pendant đã được cập nhật';

  @override
  String get allRecordingsSynced => 'Tất cả bản ghi âm đã được đồng bộ';

  @override
  String get syncingInProgress => 'Đang đồng bộ';

  @override
  String get readyToSync => 'Sẵn sàng đồng bộ';

  @override
  String get tapSyncToStart => 'Nhấn Đồng bộ để bắt đầu';

  @override
  String get pendantNotConnected => 'Pendant chưa kết nối. Kết nối để đồng bộ.';

  @override
  String get everythingSynced => 'Mọi thứ đã được đồng bộ.';

  @override
  String get recordingsNotSynced => 'Bạn có những bản ghi âm chưa được đồng bộ.';

  @override
  String get syncingBackground => 'Chúng tôi sẽ tiếp tục đồng bộ bản ghi âm của bạn trong nền.';

  @override
  String get noConversationsYet => 'Chưa có cuộc trò chuyện nào';

  @override
  String get noStarredConversations => 'Không có cuộc trò chuyện đã gắn sao';

  @override
  String get starConversationHint => 'Để gắn sao cuộc trò chuyện, hãy mở nó và nhấn vào biểu tượng ngôi sao ở phần đầu.';

  @override
  String get searchConversations => 'Tìm kiếm cuộc trò chuyện...';

  @override
  String selectedCount(int count, Object s) {
    return 'Đã chọn $count';
  }

  @override
  String get merge => 'Gộp';

  @override
  String get mergeConversations => 'Gộp cuộc trò chuyện';

  @override
  String mergeConversationsMessage(int count) {
    return 'Thao tác này sẽ kết hợp $count cuộc trò chuyện thành một. Tất cả nội dung sẽ được gộp và tạo lại.';
  }

  @override
  String get mergingInBackground => 'Đang gộp trong nền. Có thể mất một chút thời gian.';

  @override
  String get failedToStartMerge => 'Không thể bắt đầu gộp';

  @override
  String get askAnything => 'Hỏi bất cứ điều gì';

  @override
  String get noMessagesYet => 'Chưa có tin nhắn nào!\nHãy bắt đầu cuộc trò chuyện nhé?';

  @override
  String get deletingMessages => 'Đang xóa tin nhắn của bạn khỏi bộ nhớ của Omi...';

  @override
  String get messageCopied => '✨ Tin nhắn đã được sao chép vào clipboard';

  @override
  String get cannotReportOwnMessage => 'Bạn không thể báo cáo tin nhắn của chính mình.';

  @override
  String get reportMessage => 'Báo cáo tin nhắn';

  @override
  String get reportMessageConfirm => 'Bạn có chắc chắn muốn báo cáo tin nhắn này?';

  @override
  String get messageReported => 'Đã báo cáo tin nhắn thành công.';

  @override
  String get thankYouFeedback => 'Cảm ơn phản hồi của bạn!';

  @override
  String get clearChat => 'Xóa trò chuyện?';

  @override
  String get clearChatConfirm => 'Bạn có chắc chắn muốn xóa trò chuyện? Hành động này không thể hoàn tác.';

  @override
  String get maxFilesLimit => 'Bạn chỉ có thể tải lên tối đa 4 tệp cùng lúc';

  @override
  String get chatWithOmi => 'Trò chuyện với Omi';

  @override
  String get apps => 'Ứng dụng';

  @override
  String get noAppsFound => 'Không tìm thấy ứng dụng';

  @override
  String get tryAdjustingSearch => 'Thử điều chỉnh tìm kiếm hoặc bộ lọc của bạn';

  @override
  String get createYourOwnApp => 'Tạo ứng dụng của riêng bạn';

  @override
  String get buildAndShareApp => 'Xây dựng và chia sẻ ứng dụng tùy chỉnh của bạn';

  @override
  String get searchApps => 'Tìm kiếm ứng dụng...';

  @override
  String get myApps => 'Ứng Dụng Của Tôi';

  @override
  String get installedApps => 'Ứng Dụng Đã Cài';

  @override
  String get unableToFetchApps => 'Không thể tải ứng dụng :(\n\nVui lòng kiểm tra kết nối internet và thử lại.';

  @override
  String get aboutOmi => 'Giới thiệu về Omi';

  @override
  String get privacyPolicy => 'Chính sách bảo mật';

  @override
  String get visitWebsite => 'Truy cập trang web';

  @override
  String get helpOrInquiries => 'Trợ giúp hoặc thắc mắc?';

  @override
  String get joinCommunity => 'Tham gia cộng đồng!';

  @override
  String get membersAndCounting => '8000+ thành viên và tiếp tục tăng.';

  @override
  String get deleteAccountTitle => 'Xóa tài khoản';

  @override
  String get deleteAccountConfirm => 'Bạn có chắc chắn muốn xóa tài khoản của mình?';

  @override
  String get cannotBeUndone => 'Hành động này không thể hoàn tác.';

  @override
  String get allDataErased => 'Tất cả ký ức và cuộc trò chuyện của bạn sẽ bị xóa vĩnh viễn.';

  @override
  String get appsDisconnected => 'Các ứng dụng và tích hợp của bạn sẽ bị ngắt kết nối ngay lập tức.';

  @override
  String get exportBeforeDelete => 'Bạn có thể xuất dữ liệu trước khi xóa tài khoản, nhưng một khi đã xóa, dữ liệu không thể khôi phục.';

  @override
  String get deleteAccountCheckbox => 'Tôi hiểu rằng việc xóa tài khoản là vĩnh viễn và tất cả dữ liệu, bao gồm ký ức và cuộc trò chuyện, sẽ bị mất và không thể khôi phục.';

  @override
  String get areYouSure => 'Bạn có chắc chắn?';

  @override
  String get deleteAccountFinal => 'Hành động này không thể hoàn tác và sẽ xóa vĩnh viễn tài khoản cùng tất cả dữ liệu liên quan. Bạn có chắc chắn muốn tiếp tục?';

  @override
  String get deleteNow => 'Xóa ngay';

  @override
  String get goBack => 'Quay lại';

  @override
  String get checkBoxToConfirm => 'Đánh dấu vào ô để xác nhận bạn hiểu rằng việc xóa tài khoản là vĩnh viễn và không thể hoàn tác.';

  @override
  String get profile => 'Hồ sơ';

  @override
  String get name => 'Tên';

  @override
  String get email => 'Email';

  @override
  String get customVocabulary => 'Từ vựng Tùy chỉnh';

  @override
  String get identifyingOthers => 'Nhận dạng Người khác';

  @override
  String get paymentMethods => 'Phương thức Thanh toán';

  @override
  String get conversationDisplay => 'Hiển thị Cuộc trò chuyện';

  @override
  String get dataPrivacy => 'Quyền riêng tư Dữ liệu';

  @override
  String get userId => 'ID Người dùng';

  @override
  String get notSet => 'Chưa đặt';

  @override
  String get userIdCopied => 'Đã sao chép ID người dùng vào clipboard';

  @override
  String get systemDefault => 'Mặc định hệ thống';

  @override
  String get planAndUsage => 'Gói & Mức sử dụng';

  @override
  String get offlineSync => 'Đồng bộ ngoại tuyến';

  @override
  String get deviceSettings => 'Cài đặt thiết bị';

  @override
  String get chatTools => 'Công cụ trò chuyện';

  @override
  String get feedbackBug => 'Phản hồi / Báo lỗi';

  @override
  String get helpCenter => 'Trung tâm trợ giúp';

  @override
  String get developerSettings => 'Cài đặt nhà phát triển';

  @override
  String get getOmiForMac => 'Tải Omi cho Mac';

  @override
  String get referralProgram => 'Chương trình giới thiệu';

  @override
  String get signOut => 'Đăng xuất';

  @override
  String get appAndDeviceCopied => 'Đã sao chép thông tin ứng dụng và thiết bị';

  @override
  String get wrapped2025 => 'Tổng kết 2025';

  @override
  String get yourPrivacyYourControl => 'Quyền riêng tư của bạn, Quyền kiểm soát của bạn';

  @override
  String get privacyIntro => 'Tại Omi, chúng tôi cam kết bảo vệ quyền riêng tư của bạn. Trang này cho phép bạn kiểm soát cách dữ liệu của bạn được lưu trữ và sử dụng.';

  @override
  String get learnMore => 'Tìm hiểu thêm...';

  @override
  String get dataProtectionLevel => 'Mức độ bảo vệ dữ liệu';

  @override
  String get dataProtectionDesc => 'Dữ liệu của bạn được bảo mật mặc định với mã hóa mạnh. Xem lại cài đặt và các tùy chọn bảo mật trong tương lai bên dưới.';

  @override
  String get appAccess => 'Quyền truy cập ứng dụng';

  @override
  String get appAccessDesc => 'Các ứng dụng sau có thể truy cập dữ liệu của bạn. Nhấn vào ứng dụng để quản lý quyền của nó.';

  @override
  String get noAppsExternalAccess => 'Không có ứng dụng đã cài đặt nào có quyền truy cập bên ngoài vào dữ liệu của bạn.';

  @override
  String get deviceName => 'Tên thiết bị';

  @override
  String get deviceId => 'ID Thiết Bị';

  @override
  String get firmware => 'Phần Mềm';

  @override
  String get sdCardSync => 'Đồng bộ thẻ SD';

  @override
  String get hardwareRevision => 'Phiên bản phần cứng';

  @override
  String get modelNumber => 'Số Mô Hình';

  @override
  String get manufacturer => 'Nhà Sản Xuất';

  @override
  String get doubleTap => 'Nhấn đúp';

  @override
  String get ledBrightness => 'Độ sáng đèn LED';

  @override
  String get micGain => 'Độ tăng micro';

  @override
  String get disconnect => 'Ngắt kết nối';

  @override
  String get forgetDevice => 'Xóa thiết bị';

  @override
  String get chargingIssues => 'Sự cố sạc';

  @override
  String get disconnectDevice => 'Ngắt kết nối thiết bị';

  @override
  String get unpairDevice => 'Hủy ghép nối thiết bị';

  @override
  String get unpairAndForget => 'Hủy ghép nối và xóa thiết bị';

  @override
  String get deviceDisconnectedMessage => 'Omi của bạn đã bị ngắt kết nối 😔';

  @override
  String get deviceUnpairedMessage => 'Đã hủy ghép nối thiết bị. Đi tới Cài đặt > Bluetooth và quên thiết bị để hoàn tất việc hủy ghép nối.';

  @override
  String get unpairDialogTitle => 'Hủy ghép nối thiết bị';

  @override
  String get unpairDialogMessage => 'Thao tác này sẽ hủy ghép nối thiết bị để có thể kết nối với điện thoại khác. Bạn cần vào Cài đặt > Bluetooth và xóa thiết bị để hoàn tất quá trình.';

  @override
  String get deviceNotConnected => 'Thiết bị chưa kết nối';

  @override
  String get connectDeviceMessage => 'Kết nối thiết bị Omi của bạn để truy cập\ncài đặt thiết bị và tùy chỉnh';

  @override
  String get deviceInfoSection => 'Thông tin thiết bị';

  @override
  String get customizationSection => 'Tùy chỉnh';

  @override
  String get hardwareSection => 'Phần cứng';

  @override
  String get v2Undetected => 'Không phát hiện V2';

  @override
  String get v2UndetectedMessage => 'Chúng tôi thấy rằng bạn có thiết bị V1 hoặc thiết bị của bạn chưa được kết nối. Chức năng thẻ SD chỉ khả dụng cho thiết bị V2.';

  @override
  String get endConversation => 'Kết thúc cuộc trò chuyện';

  @override
  String get pauseResume => 'Tạm dừng/Tiếp tục';

  @override
  String get starConversation => 'Gắn sao cuộc trò chuyện';

  @override
  String get doubleTapAction => 'Hành động nhấn đúp';

  @override
  String get endAndProcess => 'Kết thúc & Xử lý cuộc trò chuyện';

  @override
  String get pauseResumeRecording => 'Tạm dừng/Tiếp tục ghi âm';

  @override
  String get starOngoing => 'Gắn sao cuộc trò chuyện đang diễn ra';

  @override
  String get off => 'Tắt';

  @override
  String get max => 'Tối đa';

  @override
  String get mute => 'Tắt tiếng';

  @override
  String get quiet => 'Yên tĩnh';

  @override
  String get normal => 'Bình thường';

  @override
  String get high => 'Cao';

  @override
  String get micGainDescMuted => 'Microphone đã tắt tiếng';

  @override
  String get micGainDescLow => 'Rất yên tĩnh - cho môi trường ồn ào';

  @override
  String get micGainDescModerate => 'Yên tĩnh - cho tiếng ồn vừa phải';

  @override
  String get micGainDescNeutral => 'Trung tính - ghi âm cân bằng';

  @override
  String get micGainDescSlightlyBoosted => 'Tăng nhẹ - sử dụng thông thường';

  @override
  String get micGainDescBoosted => 'Tăng cao - cho môi trường yên tĩnh';

  @override
  String get micGainDescHigh => 'Cao - cho giọng nói xa hoặc nhỏ';

  @override
  String get micGainDescVeryHigh => 'Rất cao - cho nguồn rất yên tĩnh';

  @override
  String get micGainDescMax => 'Tối đa - sử dụng cẩn thận';

  @override
  String get developerSettingsTitle => 'Cài đặt nhà phát triển';

  @override
  String get saving => 'Đang lưu...';

  @override
  String get personaConfig => 'Cấu hình nhân cách AI của bạn';

  @override
  String get beta => 'BETA';

  @override
  String get transcription => 'Phiên âm';

  @override
  String get transcriptionConfig => 'Cấu hình nhà cung cấp STT';

  @override
  String get conversationTimeout => 'Thời gian chờ cuộc trò chuyện';

  @override
  String get conversationTimeoutConfig => 'Đặt thời gian tự động kết thúc cuộc trò chuyện';

  @override
  String get importData => 'Nhập dữ liệu';

  @override
  String get importDataConfig => 'Nhập dữ liệu từ các nguồn khác';

  @override
  String get debugDiagnostics => 'Gỡ lỗi & Chẩn đoán';

  @override
  String get endpointUrl => 'URL điểm cuối';

  @override
  String get noApiKeys => 'Chưa có API key';

  @override
  String get createKeyToStart => 'Tạo key để bắt đầu';

  @override
  String get createKey => 'Tạo Khóa';

  @override
  String get docs => 'Tài liệu';

  @override
  String get yourOmiInsights => 'Thông tin chi tiết Omi của bạn';

  @override
  String get today => 'Hôm nay';

  @override
  String get thisMonth => 'Tháng này';

  @override
  String get thisYear => 'Năm nay';

  @override
  String get allTime => 'Tất cả thời gian';

  @override
  String get noActivityYet => 'Chưa có hoạt động';

  @override
  String get startConversationToSeeInsights => 'Bắt đầu cuộc trò chuyện với Omi\nđể xem thông tin chi tiết về mức sử dụng của bạn tại đây.';

  @override
  String get listening => 'Lắng nghe';

  @override
  String get listeningSubtitle => 'Tổng thời gian Omi đã lắng nghe tích cực.';

  @override
  String get understanding => 'Hiểu biết';

  @override
  String get understandingSubtitle => 'Số từ đã hiểu từ cuộc trò chuyện của bạn.';

  @override
  String get providing => 'Cung cấp';

  @override
  String get providingSubtitle => 'Việc cần làm và ghi chú được ghi lại tự động.';

  @override
  String get remembering => 'Ghi nhớ';

  @override
  String get rememberingSubtitle => 'Sự kiện và chi tiết được ghi nhớ cho bạn.';

  @override
  String get unlimitedPlan => 'Gói không giới hạn';

  @override
  String get managePlan => 'Quản lý gói';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'Gói của bạn sẽ bị hủy vào $date.';
  }

  @override
  String renewsOn(String date) {
    return 'Gói của bạn sẽ gia hạn vào $date.';
  }

  @override
  String get basicPlan => 'Gói miễn phí';

  @override
  String usageLimitMessage(String used, int limit) {
    return 'Đã sử dụng $used trong số $limit phút';
  }

  @override
  String get upgrade => 'Nâng cấp';

  @override
  String get upgradeToUnlimited => 'Nâng cấp lên không giới hạn';

  @override
  String basicPlanDesc(int limit) {
    return 'Gói của bạn bao gồm $limit phút miễn phí mỗi tháng. Nâng cấp để sử dụng không giới hạn.';
  }

  @override
  String get shareStatsMessage => 'Chia sẻ thống kê Omi của tôi! (omi.me - trợ lý AI luôn bên bạn)';

  @override
  String get sharePeriodToday => 'Hôm nay, omi đã:';

  @override
  String get sharePeriodMonth => 'Tháng này, omi đã:';

  @override
  String get sharePeriodYear => 'Năm nay, omi đã:';

  @override
  String get sharePeriodAllTime => 'Cho đến nay, omi đã:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 Đã lắng nghe trong $minutes phút';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 Đã hiểu $words từ';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ Đã cung cấp $count thông tin chi tiết';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 Đã ghi nhớ $count ký ức';
  }

  @override
  String get debugLogs => 'Nhật ký gỡ lỗi';

  @override
  String get debugLogsAutoDelete => 'Tự động xóa sau 3 ngày.';

  @override
  String get debugLogsDesc => 'Giúp chẩn đoán các vấn đề';

  @override
  String get noLogFilesFound => 'Không tìm thấy tệp nhật ký.';

  @override
  String get omiDebugLog => 'Nhật ký gỡ lỗi Omi';

  @override
  String get logShared => 'Đã chia sẻ nhật ký';

  @override
  String get selectLogFile => 'Chọn tệp nhật ký';

  @override
  String get shareLogs => 'Chia sẻ nhật ký';

  @override
  String get debugLogCleared => 'Đã xóa nhật ký gỡ lỗi';

  @override
  String get exportStarted => 'Đã bắt đầu xuất dữ liệu. Có thể mất vài giây...';

  @override
  String get exportAllData => 'Xuất tất cả dữ liệu';

  @override
  String get exportDataDesc => 'Xuất cuộc trò chuyện sang tệp JSON';

  @override
  String get exportedConversations => 'Cuộc trò chuyện đã xuất từ Omi';

  @override
  String get exportShared => 'Đã chia sẻ bản xuất';

  @override
  String get deleteKnowledgeGraphTitle => 'Xóa biểu đồ tri thức?';

  @override
  String get deleteKnowledgeGraphMessage => 'Thao tác này sẽ xóa tất cả dữ liệu biểu đồ tri thức được tạo ra (nút và kết nối). Ký ức gốc của bạn sẽ vẫn an toàn. Biểu đồ sẽ được xây dựng lại theo thời gian hoặc khi có yêu cầu tiếp theo.';

  @override
  String get knowledgeGraphDeleted => 'Đã xóa đồ thị kiến thức';

  @override
  String deleteGraphFailed(String error) {
    return 'Không thể xóa biểu đồ: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'Xóa biểu đồ tri thức';

  @override
  String get deleteKnowledgeGraphDesc => 'Xóa tất cả nút và kết nối';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'Máy chủ MCP';

  @override
  String get mcpServerDesc => 'Kết nối trợ lý AI với dữ liệu của bạn';

  @override
  String get serverUrl => 'URL máy chủ';

  @override
  String get urlCopied => 'Đã sao chép URL';

  @override
  String get apiKeyAuth => 'Xác thực API Key';

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
  String get useMcpApiKey => 'Sử dụng API key MCP của bạn';

  @override
  String get webhooks => 'Webhooks';

  @override
  String get conversationEvents => 'Sự kiện cuộc trò chuyện';

  @override
  String get newConversationCreated => 'Đã tạo cuộc trò chuyện mới';

  @override
  String get realtimeTranscript => 'Bản ghi thời gian thực';

  @override
  String get transcriptReceived => 'Đã nhận bản ghi';

  @override
  String get audioBytes => 'Dữ liệu âm thanh';

  @override
  String get audioDataReceived => 'Đã nhận dữ liệu âm thanh';

  @override
  String get intervalSeconds => 'Khoảng thời gian (giây)';

  @override
  String get daySummary => 'Tóm tắt ngày';

  @override
  String get summaryGenerated => 'Đã tạo tóm tắt';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'Thêm vào claude_desktop_config.json';

  @override
  String get copyConfig => 'Sao chép cấu hình';

  @override
  String get configCopied => 'Đã sao chép cấu hình vào clipboard';

  @override
  String get listeningMins => 'Lắng nghe (phút)';

  @override
  String get understandingWords => 'Hiểu biết (từ)';

  @override
  String get insights => 'Thông tin chi tiết';

  @override
  String get memories => 'Kỷ niệm';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return 'Đã sử dụng $used trong số $limit phút trong tháng này';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return 'Đã sử dụng $used trong số $limit từ trong tháng này';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return 'Đã thu được $used trong số $limit thông tin chi tiết trong tháng này';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return 'Đã tạo $used trong số $limit ký ức trong tháng này';
  }

  @override
  String get visibility => 'Hiển thị';

  @override
  String get visibilitySubtitle => 'Kiểm soát cuộc trò chuyện nào xuất hiện trong danh sách của bạn';

  @override
  String get showShortConversations => 'Hiển thị cuộc trò chuyện ngắn';

  @override
  String get showShortConversationsDesc => 'Hiển thị cuộc trò chuyện ngắn hơn ngưỡng';

  @override
  String get showDiscardedConversations => 'Hiển thị cuộc trò chuyện đã hủy';

  @override
  String get showDiscardedConversationsDesc => 'Bao gồm cuộc trò chuyện được đánh dấu là đã hủy';

  @override
  String get shortConversationThreshold => 'Ngưỡng cuộc trò chuyện ngắn';

  @override
  String get shortConversationThresholdSubtitle => 'Cuộc trò chuyện ngắn hơn sẽ bị ẩn trừ khi được bật ở trên';

  @override
  String get durationThreshold => 'Ngưỡng thời lượng';

  @override
  String get durationThresholdDesc => 'Ẩn cuộc trò chuyện ngắn hơn';

  @override
  String minLabel(int count) {
    return '$count phút';
  }

  @override
  String get customVocabularyTitle => 'Từ vựng tùy chỉnh';

  @override
  String get addWords => 'Thêm từ';

  @override
  String get addWordsDesc => 'Tên, thuật ngữ hoặc từ không phổ biến';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'Kết nối';

  @override
  String get comingSoon => 'Sắp ra mắt';

  @override
  String get chatToolsFooter => 'Kết nối ứng dụng của bạn để xem dữ liệu và số liệu trong trò chuyện.';

  @override
  String get completeAuthInBrowser => 'Vui lòng hoàn tất xác thực trong trình duyệt của bạn. Sau khi hoàn tất, hãy quay lại ứng dụng.';

  @override
  String failedToStartAuth(String appName) {
    return 'Không thể bắt đầu xác thực $appName';
  }

  @override
  String disconnectAppTitle(String appName) {
    return 'Ngắt kết nối $appName?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'Bạn có chắc chắn muốn ngắt kết nối khỏi $appName? Bạn có thể kết nối lại bất kỳ lúc nào.';
  }

  @override
  String disconnectedFrom(String appName) {
    return 'Đã ngắt kết nối khỏi $appName';
  }

  @override
  String get failedToDisconnect => 'Không thể ngắt kết nối';

  @override
  String connectTo(String appName) {
    return 'Kết nối với $appName';
  }

  @override
  String authAccessMessage(String appName) {
    return 'Bạn cần cho phép Omi truy cập dữ liệu $appName của bạn. Thao tác này sẽ mở trình duyệt để xác thực.';
  }

  @override
  String get continueAction => 'Tiếp tục';

  @override
  String get languageTitle => 'Ngôn ngữ';

  @override
  String get primaryLanguage => 'Ngôn ngữ chính';

  @override
  String get automaticTranslation => 'Dịch tự động';

  @override
  String get detectLanguages => 'Phát hiện hơn 10 ngôn ngữ';

  @override
  String get authorizeSavingRecordings => 'Cho phép lưu bản ghi âm';

  @override
  String get thanksForAuthorizing => 'Cảm ơn bạn đã cho phép!';

  @override
  String get needYourPermission => 'Chúng tôi cần sự cho phép của bạn';

  @override
  String get alreadyGavePermission => 'Bạn đã cho phép chúng tôi lưu bản ghi âm của bạn. Đây là lời nhắc nhở về lý do chúng tôi cần:';

  @override
  String get wouldLikePermission => 'Chúng tôi muốn được phép lưu bản ghi âm giọng nói của bạn. Đây là lý do:';

  @override
  String get improveSpeechProfile => 'Cải thiện hồ sơ giọng nói của bạn';

  @override
  String get improveSpeechProfileDesc => 'Chúng tôi sử dụng bản ghi âm để huấn luyện và nâng cao hồ sơ giọng nói cá nhân của bạn.';

  @override
  String get trainFamilyProfiles => 'Huấn luyện hồ sơ cho bạn bè và gia đình';

  @override
  String get trainFamilyProfilesDesc => 'Bản ghi âm của bạn giúp chúng tôi nhận dạng và tạo hồ sơ cho bạn bè và gia đình của bạn.';

  @override
  String get enhanceTranscriptAccuracy => 'Tăng độ chính xác bản ghi';

  @override
  String get enhanceTranscriptAccuracyDesc => 'Khi mô hình của chúng tôi được cải thiện, chúng tôi có thể cung cấp kết quả phiên âm tốt hơn cho bản ghi âm của bạn.';

  @override
  String get legalNotice => 'Thông báo pháp lý: Tính hợp pháp của việc ghi âm và lưu trữ dữ liệu giọng nói có thể khác nhau tùy thuộc vào vị trí của bạn và cách bạn sử dụng tính năng này. Bạn có trách nhiệm đảm bảo tuân thủ luật pháp và quy định địa phương.';

  @override
  String get alreadyAuthorized => 'Đã cho phép';

  @override
  String get authorize => 'Cho phép';

  @override
  String get revokeAuthorization => 'Thu hồi quyền';

  @override
  String get authorizationSuccessful => 'Cho phép thành công!';

  @override
  String get failedToAuthorize => 'Không thể cho phép. Vui lòng thử lại.';

  @override
  String get authorizationRevoked => 'Đã thu hồi quyền.';

  @override
  String get recordingsDeleted => 'Đã xóa bản ghi âm.';

  @override
  String get failedToRevoke => 'Không thể thu hồi quyền. Vui lòng thử lại.';

  @override
  String get permissionRevokedTitle => 'Đã thu hồi quyền';

  @override
  String get permissionRevokedMessage => 'Bạn có muốn chúng tôi xóa tất cả bản ghi âm hiện có của bạn không?';

  @override
  String get yes => 'Có';

  @override
  String get editName => 'Chỉnh sửa tên';

  @override
  String get howShouldOmiCallYou => 'Omi nên gọi bạn như thế nào?';

  @override
  String get enterYourName => 'Nhập tên của bạn';

  @override
  String get nameCannotBeEmpty => 'Tên không được để trống';

  @override
  String get nameUpdatedSuccessfully => 'Đã cập nhật tên thành công!';

  @override
  String get calendarSettings => 'Cài đặt lịch';

  @override
  String get calendarProviders => 'Nhà cung cấp lịch';

  @override
  String get macOsCalendar => 'Lịch macOS';

  @override
  String get connectMacOsCalendar => 'Kết nối lịch macOS cục bộ của bạn';

  @override
  String get googleCalendar => 'Google Calendar';

  @override
  String get syncGoogleAccount => 'Đồng bộ với tài khoản Google của bạn';

  @override
  String get showMeetingsMenuBar => 'Hiển thị cuộc họp sắp tới trên thanh menu';

  @override
  String get showMeetingsMenuBarDesc => 'Hiển thị cuộc họp tiếp theo và thời gian cho đến khi nó bắt đầu trên thanh menu macOS';

  @override
  String get showEventsNoParticipants => 'Hiển thị sự kiện không có người tham gia';

  @override
  String get showEventsNoParticipantsDesc => 'Khi được bật, Coming Up hiển thị các sự kiện không có người tham gia hoặc liên kết video.';

  @override
  String get yourMeetings => 'Cuộc họp của bạn';

  @override
  String get refresh => 'Làm mới';

  @override
  String get noUpcomingMeetings => 'Không tìm thấy cuộc họp sắp tới';

  @override
  String get checkingNextDays => 'Kiểm tra 30 ngày tiếp theo';

  @override
  String get tomorrow => 'Ngày mai';

  @override
  String get googleCalendarComingSoon => 'Tích hợp Google Calendar sắp ra mắt!';

  @override
  String connectedAsUser(String userId) {
    return 'Đã kết nối với tư cách người dùng: $userId';
  }

  @override
  String get defaultWorkspace => 'Workspace mặc định';

  @override
  String get tasksCreatedInWorkspace => 'Nhiệm vụ sẽ được tạo trong workspace này';

  @override
  String get defaultProjectOptional => 'Dự án mặc định (Tùy chọn)';

  @override
  String get leaveUnselectedTasks => 'Bỏ trống để tạo nhiệm vụ không có dự án';

  @override
  String get noProjectsInWorkspace => 'Không tìm thấy dự án trong workspace này';

  @override
  String get conversationTimeoutDesc => 'Chọn thời gian chờ im lặng trước khi tự động kết thúc cuộc trò chuyện:';

  @override
  String get timeout2Minutes => '2 phút';

  @override
  String get timeout2MinutesDesc => 'Kết thúc cuộc trò chuyện sau 2 phút im lặng';

  @override
  String get timeout5Minutes => '5 phút';

  @override
  String get timeout5MinutesDesc => 'Kết thúc cuộc trò chuyện sau 5 phút im lặng';

  @override
  String get timeout10Minutes => '10 phút';

  @override
  String get timeout10MinutesDesc => 'Kết thúc cuộc trò chuyện sau 10 phút im lặng';

  @override
  String get timeout30Minutes => '30 phút';

  @override
  String get timeout30MinutesDesc => 'Kết thúc cuộc trò chuyện sau 30 phút im lặng';

  @override
  String get timeout4Hours => '4 giờ';

  @override
  String get timeout4HoursDesc => 'Kết thúc cuộc trò chuyện sau 4 giờ im lặng';

  @override
  String get conversationEndAfterHours => 'Cuộc trò chuyện bây giờ sẽ kết thúc sau 4 giờ im lặng';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Cuộc trò chuyện bây giờ sẽ kết thúc sau $minutes phút im lặng';
  }

  @override
  String get tellUsPrimaryLanguage => 'Cho chúng tôi biết ngôn ngữ chính của bạn';

  @override
  String get languageForTranscription => 'Đặt ngôn ngữ của bạn để có phiên âm chính xác hơn và trải nghiệm được cá nhân hóa.';

  @override
  String get singleLanguageModeInfo => 'Chế độ đơn ngôn ngữ đã được bật. Dịch bị vô hiệu hóa để có độ chính xác cao hơn.';

  @override
  String get searchLanguageHint => 'Tìm kiếm ngôn ngữ theo tên hoặc mã';

  @override
  String get noLanguagesFound => 'Không tìm thấy ngôn ngữ';

  @override
  String get skip => 'Bỏ qua';

  @override
  String languageSetTo(String language) {
    return 'Đã đặt ngôn ngữ thành $language';
  }

  @override
  String get failedToSetLanguage => 'Không thể đặt ngôn ngữ';

  @override
  String appSettings(String appName) {
    return 'Cài đặt $appName';
  }

  @override
  String disconnectFromApp(String appName) {
    return 'Ngắt kết nối khỏi $appName?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'Thao tác này sẽ xóa xác thực $appName của bạn. Bạn sẽ cần kết nối lại để sử dụng.';
  }

  @override
  String connectedToApp(String appName) {
    return 'Đã kết nối với $appName';
  }

  @override
  String get account => 'Tài khoản';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Việc cần làm của bạn sẽ được đồng bộ với tài khoản $appName của bạn';
  }

  @override
  String get defaultSpace => 'Space mặc định';

  @override
  String get selectSpaceInWorkspace => 'Chọn một space trong workspace của bạn';

  @override
  String get noSpacesInWorkspace => 'Không tìm thấy space trong workspace này';

  @override
  String get defaultList => 'Danh sách mặc định';

  @override
  String get tasksAddedToList => 'Nhiệm vụ sẽ được thêm vào danh sách này';

  @override
  String get noListsInSpace => 'Không tìm thấy danh sách trong space này';

  @override
  String failedToLoadRepos(String error) {
    return 'Không thể tải kho lưu trữ: $error';
  }

  @override
  String get defaultRepoSaved => 'Đã lưu kho lưu trữ mặc định';

  @override
  String get failedToSaveDefaultRepo => 'Không thể lưu kho lưu trữ mặc định';

  @override
  String get defaultRepository => 'Kho lưu trữ mặc định';

  @override
  String get selectDefaultRepoDesc => 'Chọn một kho lưu trữ mặc định để tạo issue. Bạn vẫn có thể chỉ định kho lưu trữ khác khi tạo issue.';

  @override
  String get noReposFound => 'Không tìm thấy kho lưu trữ';

  @override
  String get private => 'Riêng tư';

  @override
  String updatedDate(String date) {
    return 'Đã cập nhật $date';
  }

  @override
  String get yesterday => 'Hôm qua';

  @override
  String daysAgo(int count) {
    return '$count ngày trước';
  }

  @override
  String get oneWeekAgo => '1 tuần trước';

  @override
  String weeksAgo(int count) {
    return '$count tuần trước';
  }

  @override
  String get oneMonthAgo => '1 tháng trước';

  @override
  String monthsAgo(int count) {
    return '$count tháng trước';
  }

  @override
  String get issuesCreatedInRepo => 'Issue sẽ được tạo trong kho lưu trữ mặc định của bạn';

  @override
  String get taskIntegrations => 'Tích hợp nhiệm vụ';

  @override
  String get configureSettings => 'Cấu hình cài đặt';

  @override
  String get completeAuthBrowser => 'Vui lòng hoàn tất xác thực trong trình duyệt của bạn. Sau khi hoàn tất, hãy quay lại ứng dụng.';

  @override
  String failedToStartAppAuth(String appName) {
    return 'Không thể bắt đầu xác thực $appName';
  }

  @override
  String connectToAppTitle(String appName) {
    return 'Kết nối với $appName';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Bạn cần cho phép Omi tạo nhiệm vụ trong tài khoản $appName của bạn. Thao tác này sẽ mở trình duyệt để xác thực.';
  }

  @override
  String get continueButton => 'Tiếp tục';

  @override
  String appIntegration(String appName) {
    return 'Tích hợp $appName';
  }

  @override
  String integrationComingSoon(String appName) {
    return 'Tích hợp với $appName sắp ra mắt! Chúng tôi đang nỗ lực để mang đến cho bạn nhiều tùy chọn quản lý nhiệm vụ hơn.';
  }

  @override
  String get gotIt => 'Đã hiểu';

  @override
  String get tasksExportedOneApp => 'Nhiệm vụ có thể được xuất sang một ứng dụng tại một thời điểm.';

  @override
  String get completeYourUpgrade => 'Hoàn tất nâng cấp của bạn';

  @override
  String get importConfiguration => 'Nhập cấu hình';

  @override
  String get exportConfiguration => 'Xuất cấu hình';

  @override
  String get bringYourOwn => 'Mang của riêng bạn';

  @override
  String get payYourSttProvider => 'Sử dụng omi tự do. Bạn chỉ trả tiền cho nhà cung cấp STT trực tiếp.';

  @override
  String get freeMinutesMonth => '1.200 phút miễn phí/tháng được bao gồm. Không giới hạn với ';

  @override
  String get omiUnlimited => 'Omi Unlimited';

  @override
  String get hostRequired => 'Bắt buộc có host';

  @override
  String get validPortRequired => 'Bắt buộc có port hợp lệ';

  @override
  String get validWebsocketUrlRequired => 'Bắt buộc có URL WebSocket hợp lệ (wss://)';

  @override
  String get apiUrlRequired => 'Bắt buộc có URL API';

  @override
  String get apiKeyRequired => 'Bắt buộc có API key';

  @override
  String get invalidJsonConfig => 'Cấu hình JSON không hợp lệ';

  @override
  String errorSaving(String error) {
    return 'Lỗi khi lưu: $error';
  }

  @override
  String get configCopiedToClipboard => 'Đã sao chép cấu hình vào clipboard';

  @override
  String get pasteJsonConfig => 'Dán cấu hình JSON của bạn bên dưới:';

  @override
  String get addApiKeyAfterImport => 'Bạn cần thêm API key của riêng mình sau khi nhập';

  @override
  String get paste => 'Dán';

  @override
  String get import => 'Nhập';

  @override
  String get invalidProviderInConfig => 'Nhà cung cấp không hợp lệ trong cấu hình';

  @override
  String importedConfig(String providerName) {
    return 'Đã nhập cấu hình $providerName';
  }

  @override
  String invalidJson(String error) {
    return 'JSON không hợp lệ: $error';
  }

  @override
  String get provider => 'Nhà cung cấp';

  @override
  String get live => 'Trực tiếp';

  @override
  String get onDevice => 'Trên thiết bị';

  @override
  String get apiUrl => 'URL API';

  @override
  String get enterSttHttpEndpoint => 'Nhập điểm cuối HTTP STT của bạn';

  @override
  String get websocketUrl => 'URL WebSocket';

  @override
  String get enterLiveSttWebsocket => 'Nhập điểm cuối WebSocket STT trực tiếp của bạn';

  @override
  String get apiKey => 'Khóa API';

  @override
  String get enterApiKey => 'Nhập API key của bạn';

  @override
  String get storedLocallyNeverShared => 'Lưu trữ cục bộ, không bao giờ chia sẻ';

  @override
  String get host => 'Host';

  @override
  String get port => 'Port';

  @override
  String get advanced => 'Nâng cao';

  @override
  String get configuration => 'Cấu hình';

  @override
  String get requestConfiguration => 'Cấu hình yêu cầu';

  @override
  String get responseSchema => 'Schema phản hồi';

  @override
  String get modified => 'Đã sửa đổi';

  @override
  String get resetRequestConfig => 'Đặt lại cấu hình yêu cầu về mặc định';

  @override
  String get logs => 'Nhật ký';

  @override
  String get logsCopied => 'Đã sao chép nhật ký';

  @override
  String get noLogsYet => 'Chưa có nhật ký. Bắt đầu ghi âm để xem hoạt động STT tùy chỉnh.';

  @override
  String deviceUsesCodec(String deviceName, String codecReason) {
    return '$deviceName sử dụng $codecReason. Omi sẽ được sử dụng.';
  }

  @override
  String get omiTranscription => 'Phiên âm Omi';

  @override
  String get bestInClassTranscription => 'Phiên âm tốt nhất với cài đặt bằng không';

  @override
  String get instantSpeakerLabels => 'Nhãn người nói tức thì';

  @override
  String get languageTranslation => 'Dịch hơn 100 ngôn ngữ';

  @override
  String get optimizedForConversation => 'Được tối ưu hóa cho cuộc trò chuyện';

  @override
  String get autoLanguageDetection => 'Tự động phát hiện ngôn ngữ';

  @override
  String get highAccuracy => 'Độ chính xác cao';

  @override
  String get privacyFirst => 'Ưu tiên bảo mật';

  @override
  String get saveChanges => 'Lưu thay đổi';

  @override
  String get resetToDefault => 'Đặt lại về mặc định';

  @override
  String get viewTemplate => 'Xem mẫu';

  @override
  String get trySomethingLike => 'Thử một cái gì đó như...';

  @override
  String get tryIt => 'Thử ngay';

  @override
  String get creatingPlan => 'Đang tạo kế hoạch';

  @override
  String get developingLogic => 'Đang phát triển logic';

  @override
  String get designingApp => 'Đang thiết kế ứng dụng';

  @override
  String get generatingIconStep => 'Đang tạo biểu tượng';

  @override
  String get finalTouches => 'Hoàn thiện cuối cùng';

  @override
  String get processing => 'Đang xử lý...';

  @override
  String get features => 'Tính năng';

  @override
  String get creatingYourApp => 'Đang tạo ứng dụng của bạn...';

  @override
  String get generatingIcon => 'Đang tạo biểu tượng...';

  @override
  String get whatShouldWeMake => 'Chúng ta nên tạo gì?';

  @override
  String get appName => 'Tên ứng dụng';

  @override
  String get description => 'Mô tả';

  @override
  String get publicLabel => 'Công khai';

  @override
  String get privateLabel => 'Riêng tư';

  @override
  String get free => 'Miễn phí';

  @override
  String get perMonth => '/ Tháng';

  @override
  String get tailoredConversationSummaries => 'Tóm tắt cuộc trò chuyện được tùy chỉnh';

  @override
  String get customChatbotPersonality => 'Tính cách chatbot tùy chỉnh';

  @override
  String get makePublic => 'Công khai';

  @override
  String get anyoneCanDiscover => 'Bất kỳ ai cũng có thể khám phá ứng dụng của bạn';

  @override
  String get onlyYouCanUse => 'Chỉ bạn mới có thể sử dụng ứng dụng này';

  @override
  String get paidApp => 'Ứng dụng trả phí';

  @override
  String get usersPayToUse => 'Người dùng trả tiền để sử dụng ứng dụng của bạn';

  @override
  String get freeForEveryone => 'Miễn phí cho tất cả mọi người';

  @override
  String get perMonthLabel => '/ tháng';

  @override
  String get creating => 'Đang tạo...';

  @override
  String get createApp => 'Tạo Ứng Dụng';

  @override
  String get searchingForDevices => 'Đang tìm kiếm thiết bị...';

  @override
  String devicesFoundNearby(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'THIẾT BỊ',
      one: 'THIẾT BỊ',
    );
    return 'ĐÃ TÌM THẤY $count $_temp0 GẦN ĐÂY';
  }

  @override
  String get pairingSuccessful => 'GHÉP NỐI THÀNH CÔNG';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Lỗi khi kết nối với Apple Watch: $error';
  }

  @override
  String get dontShowAgain => 'Không hiển thị lại';

  @override
  String get iUnderstand => 'Tôi hiểu';

  @override
  String get enableBluetooth => 'Bật Bluetooth';

  @override
  String get bluetoothNeeded => 'Omi cần Bluetooth để kết nối với thiết bị đeo của bạn. Vui lòng bật Bluetooth và thử lại.';

  @override
  String get contactSupport => 'Liên hệ hỗ trợ?';

  @override
  String get connectLater => 'Kết nối sau';

  @override
  String get grantPermissions => 'Cấp quyền';

  @override
  String get backgroundActivity => 'Hoạt động nền';

  @override
  String get backgroundActivityDesc => 'Cho phép Omi chạy trong nền để ổn định hơn';

  @override
  String get locationAccess => 'Truy cập vị trí';

  @override
  String get locationAccessDesc => 'Bật vị trí nền để có trải nghiệm đầy đủ';

  @override
  String get notifications => 'Thông báo';

  @override
  String get notificationsDesc => 'Bật thông báo để luôn được thông tin';

  @override
  String get locationServiceDisabled => 'Dịch vụ vị trí đã bị tắt';

  @override
  String get locationServiceDisabledDesc => 'Dịch vụ vị trí đã bị tắt. Vui lòng vào Cài đặt > Quyền riêng tư & Bảo mật > Dịch vụ vị trí và bật nó';

  @override
  String get backgroundLocationDenied => 'Quyền truy cập vị trí nền bị từ chối';

  @override
  String get backgroundLocationDeniedDesc => 'Vui lòng vào cài đặt thiết bị và đặt quyền vị trí thành \"Luôn cho phép\"';

  @override
  String get lovingOmi => 'Bạn thích Omi?';

  @override
  String get leaveReviewIos => 'Giúp chúng tôi tiếp cận nhiều người hơn bằng cách để lại đánh giá trên App Store. Phản hồi của bạn có ý nghĩa rất lớn với chúng tôi!';

  @override
  String get leaveReviewAndroid => 'Giúp chúng tôi tiếp cận nhiều người hơn bằng cách để lại đánh giá trên Google Play Store. Phản hồi của bạn có ý nghĩa rất lớn với chúng tôi!';

  @override
  String get rateOnAppStore => 'Đánh giá trên App Store';

  @override
  String get rateOnGooglePlay => 'Đánh giá trên Google Play';

  @override
  String get maybeLater => 'Có thể Sau';

  @override
  String get speechProfileIntro => 'Omi cần học hỏi mục tiêu và giọng nói của bạn. Bạn có thể sửa đổi nó sau.';

  @override
  String get getStarted => 'Bắt đầu';

  @override
  String get allDone => 'Hoàn tất!';

  @override
  String get keepGoing => 'Tiếp tục, bạn đang làm rất tốt';

  @override
  String get skipThisQuestion => 'Bỏ qua câu hỏi này';

  @override
  String get skipForNow => 'Bỏ qua bây giờ';

  @override
  String get connectionError => 'Lỗi kết nối';

  @override
  String get connectionErrorDesc => 'Không thể kết nối với máy chủ. Vui lòng kiểm tra kết nối internet và thử lại.';

  @override
  String get invalidRecordingMultipleSpeakers => 'Phát hiện bản ghi âm không hợp lệ';

  @override
  String get multipleSpeakersDesc => 'Có vẻ như có nhiều người nói trong bản ghi âm. Vui lòng đảm bảo bạn ở nơi yên tĩnh và thử lại.';

  @override
  String get tooShortDesc => 'Không phát hiện đủ giọng nói. Vui lòng nói nhiều hơn và thử lại.';

  @override
  String get invalidRecordingDesc => 'Vui lòng đảm bảo bạn nói ít nhất 5 giây và không quá 90 giây.';

  @override
  String get areYouThere => 'Bạn có ở đó không?';

  @override
  String get noSpeechDesc => 'Chúng tôi không thể phát hiện giọng nói nào. Vui lòng đảm bảo nói ít nhất 10 giây và không quá 3 phút.';

  @override
  String get connectionLost => 'Mất kết nối';

  @override
  String get connectionLostDesc => 'Kết nối đã bị gián đoạn. Vui lòng kiểm tra kết nối internet và thử lại.';

  @override
  String get tryAgain => 'Thử lại';

  @override
  String get connectOmiOmiGlass => 'Kết nối Omi / OmiGlass';

  @override
  String get continueWithoutDevice => 'Tiếp tục không có thiết bị';

  @override
  String get permissionsRequired => 'Yêu cầu quyền';

  @override
  String get permissionsRequiredDesc => 'Ứng dụng này cần quyền Bluetooth và Vị trí để hoạt động đúng cách. Vui lòng bật chúng trong cài đặt.';

  @override
  String get openSettings => 'Mở cài đặt';

  @override
  String get wantDifferentName => 'Muốn được gọi bằng tên khác?';

  @override
  String get whatsYourName => 'Tên bạn là gì?';

  @override
  String get speakTranscribeSummarize => 'Nói. Phiên âm. Tóm tắt.';

  @override
  String get signInWithApple => 'Đăng nhập bằng Apple';

  @override
  String get signInWithGoogle => 'Đăng nhập bằng Google';

  @override
  String get byContinuingAgree => 'Bằng cách tiếp tục, bạn đồng ý với ';

  @override
  String get termsOfUse => 'Điều khoản sử dụng';

  @override
  String get omiYourAiCompanion => 'Omi – Trợ lý AI của bạn';

  @override
  String get captureEveryMoment => 'Ghi lại mọi khoảnh khắc. Nhận tóm tắt\nbằng AI. Không bao giờ phải ghi chú lại.';

  @override
  String get appleWatchSetup => 'Thiết lập Apple Watch';

  @override
  String get permissionRequestedExclaim => 'Đã yêu cầu quyền!';

  @override
  String get microphonePermission => 'Quyền microphone';

  @override
  String get permissionGrantedNow => 'Đã cấp quyền! Bây giờ:\n\nMở ứng dụng Omi trên đồng hồ của bạn và nhấn \"Tiếp tục\" bên dưới';

  @override
  String get needMicrophonePermission => 'Chúng tôi cần quyền microphone.\n\n1. Nhấn \"Cấp quyền\"\n2. Cho phép trên iPhone của bạn\n3. Ứng dụng đồng hồ sẽ đóng\n4. Mở lại và nhấn \"Tiếp tục\"';

  @override
  String get grantPermissionButton => 'Cấp quyền';

  @override
  String get needHelp => 'Cần trợ giúp?';

  @override
  String get troubleshootingSteps => 'Khắc phục sự cố:\n\n1. Đảm bảo Omi được cài đặt trên đồng hồ của bạn\n2. Mở ứng dụng Omi trên đồng hồ của bạn\n3. Tìm cửa sổ bật lên yêu cầu quyền\n4. Nhấn \"Cho phép\" khi được nhắc\n5. Ứng dụng trên đồng hồ của bạn sẽ đóng - mở lại\n6. Quay lại và nhấn \"Tiếp tục\" trên iPhone của bạn';

  @override
  String get recordingStartedSuccessfully => 'Đã bắt đầu ghi âm thành công!';

  @override
  String get permissionNotGrantedYet => 'Quyền chưa được cấp. Vui lòng đảm bảo bạn đã cho phép quyền microphone và mở lại ứng dụng trên đồng hồ của bạn.';

  @override
  String errorRequestingPermission(String error) {
    return 'Lỗi khi yêu cầu quyền: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'Lỗi khi bắt đầu ghi âm: $error';
  }

  @override
  String get selectPrimaryLanguage => 'Chọn ngôn ngữ chính của bạn';

  @override
  String get languageBenefits => 'Đặt ngôn ngữ của bạn để có phiên âm chính xác hơn và trải nghiệm được cá nhân hóa';

  @override
  String get whatsYourPrimaryLanguage => 'Ngôn ngữ chính của bạn là gì?';

  @override
  String get selectYourLanguage => 'Chọn ngôn ngữ của bạn';

  @override
  String get personalGrowthJourney => 'Hành trình phát triển cá nhân của bạn với AI lắng nghe từng lời nói.';

  @override
  String get actionItemsTitle => 'Việc cần làm';

  @override
  String get actionItemsDescription => 'Nhấn để sửa • Nhấn giữ để chọn • Vuốt để thực hiện hành động';

  @override
  String get tabToDo => 'Cần làm';

  @override
  String get tabDone => 'Đã xong';

  @override
  String get tabOld => 'Cũ';

  @override
  String get emptyTodoMessage => '🎉 Đã hoàn tất tất cả!\nKhông còn việc cần làm';

  @override
  String get emptyDoneMessage => 'Chưa có mục nào hoàn thành';

  @override
  String get emptyOldMessage => '✅ Không có nhiệm vụ cũ';

  @override
  String get noItems => 'Không có mục nào';

  @override
  String get actionItemMarkedIncomplete => 'Đã đánh dấu việc cần làm là chưa hoàn thành';

  @override
  String get actionItemCompleted => 'Đã hoàn thành việc cần làm';

  @override
  String get deleteActionItemTitle => 'Xóa mục hành động';

  @override
  String get deleteActionItemMessage => 'Bạn có chắc chắn muốn xóa mục hành động này không?';

  @override
  String get deleteSelectedItemsTitle => 'Xóa các mục đã chọn';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Bạn có chắc chắn muốn xóa $count việc cần làm$s đã chọn?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'Đã xóa việc cần làm \"$description\"';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return 'Đã xóa $count việc cần làm$s';
  }

  @override
  String get failedToDeleteItem => 'Không thể xóa việc cần làm';

  @override
  String get failedToDeleteItems => 'Không thể xóa các mục';

  @override
  String get failedToDeleteSomeItems => 'Không thể xóa một số mục';

  @override
  String get welcomeActionItemsTitle => 'Sẵn sàng cho việc cần làm';

  @override
  String get welcomeActionItemsDescription => 'AI của bạn sẽ tự động trích xuất nhiệm vụ và việc cần làm từ cuộc trò chuyện của bạn. Chúng sẽ xuất hiện ở đây khi được tạo.';

  @override
  String get autoExtractionFeature => 'Tự động trích xuất từ cuộc trò chuyện';

  @override
  String get editSwipeFeature => 'Nhấn để sửa, vuốt để hoàn thành hoặc xóa';

  @override
  String itemsSelected(int count) {
    return 'Đã chọn $count';
  }

  @override
  String get selectAll => 'Chọn tất cả';

  @override
  String get deleteSelected => 'Xóa đã chọn';

  @override
  String get searchMemories => 'Tìm kiếm ký ức...';

  @override
  String get memoryDeleted => 'Đã xóa ký ức.';

  @override
  String get undo => 'Hoàn tác';

  @override
  String get noMemoriesYet => '🧠 Chưa có ký ức';

  @override
  String get noAutoMemories => 'Chưa có ký ức tự động trích xuất';

  @override
  String get noManualMemories => 'Chưa có ký ức thủ công';

  @override
  String get noMemoriesInCategories => 'Không có ký ức trong các danh mục này';

  @override
  String get noMemoriesFound => '🔍 Không tìm thấy ký ức';

  @override
  String get addFirstMemory => 'Thêm ký ức đầu tiên của bạn';

  @override
  String get clearMemoryTitle => 'Xóa bộ nhớ của Omi';

  @override
  String get clearMemoryMessage => 'Bạn có chắc chắn muốn xóa bộ nhớ của Omi? Hành động này không thể hoàn tác.';

  @override
  String get clearMemoryButton => 'Xóa bộ nhớ';

  @override
  String get memoryClearedSuccess => 'Đã xóa bộ nhớ của Omi về bạn';

  @override
  String get noMemoriesToDelete => 'Không có ký ức nào để xóa';

  @override
  String get createMemoryTooltip => 'Tạo ký ức mới';

  @override
  String get createActionItemTooltip => 'Tạo việc cần làm mới';

  @override
  String get memoryManagement => 'Quản lý bộ nhớ';

  @override
  String get filterMemories => 'Lọc ký ức';

  @override
  String totalMemoriesCount(int count) {
    return 'Bạn có tổng cộng $count ký ức';
  }

  @override
  String get publicMemories => 'Ký ức công khai';

  @override
  String get privateMemories => 'Ký ức riêng tư';

  @override
  String get makeAllPrivate => 'Đặt tất cả ký ức thành riêng tư';

  @override
  String get makeAllPublic => 'Đặt tất cả ký ức thành công khai';

  @override
  String get deleteAllMemories => 'Xóa tất cả ký ức';

  @override
  String get allMemoriesPrivateResult => 'Tất cả ký ức hiện là riêng tư';

  @override
  String get allMemoriesPublicResult => 'Tất cả ký ức hiện là công khai';

  @override
  String get newMemory => '✨ Bộ nhớ mới';

  @override
  String get editMemory => '✏️ Chỉnh sửa bộ nhớ';

  @override
  String get memoryContentHint => 'Tôi thích ăn kem...';

  @override
  String get failedToSaveMemory => 'Không thể lưu. Vui lòng kiểm tra kết nối của bạn.';

  @override
  String get saveMemory => 'Lưu ký ức';

  @override
  String get retry => 'Thử lại';

  @override
  String get createActionItem => 'Tạo mục hành động';

  @override
  String get editActionItem => 'Chỉnh sửa mục hành động';

  @override
  String get actionItemDescriptionHint => 'Cần làm gì?';

  @override
  String get actionItemDescriptionEmpty => 'Mô tả việc cần làm không được để trống.';

  @override
  String get actionItemUpdated => 'Đã cập nhật việc cần làm';

  @override
  String get failedToUpdateActionItem => 'Không thể cập nhật mục hành động';

  @override
  String get actionItemCreated => 'Đã tạo việc cần làm';

  @override
  String get failedToCreateActionItem => 'Không thể tạo mục hành động';

  @override
  String get dueDate => 'Ngày đến hạn';

  @override
  String get time => 'Thời gian';

  @override
  String get addDueDate => 'Thêm ngày đến hạn';

  @override
  String get pressDoneToSave => 'Nhấn xong để lưu';

  @override
  String get pressDoneToCreate => 'Nhấn xong để tạo';

  @override
  String get filterAll => 'Tất cả';

  @override
  String get filterSystem => 'Về bạn';

  @override
  String get filterInteresting => 'Thông tin chi tiết';

  @override
  String get filterManual => 'Thủ công';

  @override
  String get completed => 'Đã hoàn thành';

  @override
  String get markComplete => 'Đánh dấu hoàn thành';

  @override
  String get actionItemDeleted => 'Đã xóa mục hành động';

  @override
  String get failedToDeleteActionItem => 'Không thể xóa mục hành động';

  @override
  String get deleteActionItemConfirmTitle => 'Xóa việc cần làm';

  @override
  String get deleteActionItemConfirmMessage => 'Bạn có chắc chắn muốn xóa việc cần làm này?';

  @override
  String get appLanguage => 'Ngôn ngữ ứng dụng';

  @override
  String get appInterfaceSectionTitle => 'GIAO DIỆN ỨNG DỤNG';

  @override
  String get speechTranscriptionSectionTitle => 'GIỌNG NÓI & PHIÊN ÂM';

  @override
  String get languageSettingsHelperText => 'Ngôn ngữ Ứng dụng thay đổi menu và nút. Ngôn ngữ Giọng nói ảnh hưởng đến cách bản ghi âm của bạn được phiên âm.';

  @override
  String get translationNotice => 'Thông báo dịch';

  @override
  String get translationNoticeMessage => 'Omi dịch các cuộc trò chuyện sang ngôn ngữ chính của bạn. Cập nhật bất cứ lúc nào trong Cài đặt → Hồ sơ.';

  @override
  String get pleaseCheckInternetConnection => 'Vui lòng kiểm tra kết nối internet và thử lại';

  @override
  String get pleaseSelectReason => 'Vui lòng chọn lý do';

  @override
  String get tellUsMoreWhatWentWrong => 'Cho chúng tôi biết thêm về điều gì đã xảy ra sai...';

  @override
  String get selectText => 'Chọn văn bản';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Tối đa $count mục tiêu được phép';
  }

  @override
  String get conversationCannotBeMerged => 'Cuộc trò chuyện này không thể hợp nhất (đã khóa hoặc đang hợp nhất)';

  @override
  String get pleaseEnterFolderName => 'Vui lòng nhập tên thư mục';

  @override
  String get failedToCreateFolder => 'Tạo thư mục thất bại';

  @override
  String get failedToUpdateFolder => 'Cập nhật thư mục thất bại';

  @override
  String get folderName => 'Tên thư mục';

  @override
  String get descriptionOptional => 'Mô tả (tùy chọn)';

  @override
  String get failedToDeleteFolder => 'Xóa thư mục thất bại';

  @override
  String get editFolder => 'Chỉnh sửa thư mục';

  @override
  String get deleteFolder => 'Xóa thư mục';

  @override
  String get transcriptCopiedToClipboard => 'Đã sao chép bản ghi vào clipboard';

  @override
  String get summaryCopiedToClipboard => 'Đã sao chép bản tóm tắt vào clipboard';

  @override
  String get conversationUrlCouldNotBeShared => 'Không thể chia sẻ URL cuộc trò chuyện.';

  @override
  String get urlCopiedToClipboard => 'Đã sao chép URL vào clipboard';

  @override
  String get exportTranscript => 'Xuất bản ghi';

  @override
  String get exportSummary => 'Xuất tóm tắt';

  @override
  String get exportButton => 'Xuất';

  @override
  String get actionItemsCopiedToClipboard => 'Đã sao chép các mục hành động vào clipboard';

  @override
  String get summarize => 'Tóm tắt';

  @override
  String get generateSummary => 'Tạo bản tóm tắt';

  @override
  String get conversationNotFoundOrDeleted => 'Không tìm thấy cuộc trò chuyện hoặc đã bị xóa';

  @override
  String get deleteMemory => 'Xóa bộ nhớ';

  @override
  String get thisActionCannotBeUndone => 'Hành động này không thể hoàn tác.';

  @override
  String memoriesCount(int count) {
    return '$count kỷ niệm';
  }

  @override
  String get noMemoriesInCategory => 'Chưa có kỷ niệm nào trong danh mục này';

  @override
  String get addYourFirstMemory => 'Thêm ký ức đầu tiên của bạn';

  @override
  String get firmwareDisconnectUsb => 'Ngắt kết nối USB';

  @override
  String get firmwareUsbWarning => 'Kết nối USB trong khi cập nhật có thể làm hỏng thiết bị của bạn.';

  @override
  String get firmwareBatteryAbove15 => 'Pin trên 15%';

  @override
  String get firmwareEnsureBattery => 'Đảm bảo thiết bị của bạn có 15% pin.';

  @override
  String get firmwareStableConnection => 'Kết nối ổn định';

  @override
  String get firmwareConnectWifi => 'Kết nối với WiFi hoặc dữ liệu di động.';

  @override
  String failedToStartUpdate(String error) {
    return 'Không thể bắt đầu cập nhật: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'Trước khi cập nhật, đảm bảo:';

  @override
  String get confirmed => 'Đã xác nhận!';

  @override
  String get release => 'Thả ra';

  @override
  String get slideToUpdate => 'Vuốt để cập nhật';

  @override
  String copiedToClipboard(String title) {
    return 'Đã sao chép $title vào khay nhớ tạm';
  }

  @override
  String get batteryLevel => 'Mức Pin';

  @override
  String get productUpdate => 'Cập Nhật Sản Phẩm';

  @override
  String get offline => 'Ngoại tuyến';

  @override
  String get available => 'Có sẵn';

  @override
  String get unpairDeviceDialogTitle => 'Hủy ghép nối thiết bị';

  @override
  String get unpairDeviceDialogMessage => 'Điều này sẽ hủy ghép nối thiết bị để có thể kết nối với điện thoại khác. Bạn sẽ cần đi tới Cài đặt > Bluetooth và quên thiết bị để hoàn tất quy trình.';

  @override
  String get unpair => 'Hủy ghép nối';

  @override
  String get unpairAndForgetDevice => 'Hủy ghép nối và quên thiết bị';

  @override
  String get unknownDevice => 'Thiết bị không xác định';

  @override
  String get unknown => 'Không xác định';

  @override
  String get productName => 'Tên Sản Phẩm';

  @override
  String get serialNumber => 'Số Seri';

  @override
  String get connected => 'Đã kết nối';

  @override
  String get privacyPolicyTitle => 'Chính sách bảo mật';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label copied';
  }

  @override
  String get noApiKeysYet => 'Chưa có khóa API. Tạo một khóa để tích hợp với ứng dụng của bạn.';

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
  String get debugAndDiagnostics => 'Gỡ lỗi và Chẩn đoán';

  @override
  String get autoDeletesAfter3Days => 'Tự động xóa sau 3 ngày';

  @override
  String get helpsDiagnoseIssues => 'Giúp chẩn đoán vấn đề';

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
  String get realTimeTranscript => 'Bản ghi âm Thời gian thực';

  @override
  String get experimental => 'Thử nghiệm';

  @override
  String get transcriptionDiagnostics => 'Chẩn đoán Ghi âm';

  @override
  String get detailedDiagnosticMessages => 'Thông báo chẩn đoán chi tiết';

  @override
  String get autoCreateSpeakers => 'Tự động tạo Người nói';

  @override
  String get autoCreateWhenNameDetected => 'Auto-create when name detected';

  @override
  String get followUpQuestions => 'Câu hỏi Theo dõi';

  @override
  String get suggestQuestionsAfterConversations => 'Đề xuất câu hỏi sau cuộc trò chuyện';

  @override
  String get goalTracker => 'Theo dõi Mục tiêu';

  @override
  String get trackPersonalGoalsOnHomepage => 'Track your personal goals on homepage';

  @override
  String get dailyReflection => 'Suy ngẫm Hàng ngày';

  @override
  String get get9PmReminderToReflect => 'Get a 9 PM reminder to reflect on your day';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'Mô tả mục hành động không được để trống';

  @override
  String get saved => 'Đã lưu';

  @override
  String get overdue => 'Quá hạn';

  @override
  String get failedToUpdateDueDate => 'Không thể cập nhật ngày đến hạn';

  @override
  String get markIncomplete => 'Đánh dấu chưa hoàn thành';

  @override
  String get editDueDate => 'Chỉnh sửa ngày đến hạn';

  @override
  String get setDueDate => 'Đặt ngày đến hạn';

  @override
  String get clearDueDate => 'Xóa ngày đến hạn';

  @override
  String get failedToClearDueDate => 'Không thể xóa ngày đến hạn';

  @override
  String get mondayAbbr => 'T2';

  @override
  String get tuesdayAbbr => 'T3';

  @override
  String get wednesdayAbbr => 'T4';

  @override
  String get thursdayAbbr => 'T5';

  @override
  String get fridayAbbr => 'T6';

  @override
  String get saturdayAbbr => 'T7';

  @override
  String get sundayAbbr => 'CN';

  @override
  String get howDoesItWork => 'Nó hoạt động như thế nào?';

  @override
  String get sdCardSyncDescription => 'Đồng bộ hóa thẻ SD sẽ nhập ký ức của bạn từ thẻ SD vào ứng dụng';

  @override
  String get checksForAudioFiles => 'Kiểm tra các tệp âm thanh trên thẻ SD';

  @override
  String get omiSyncsAudioFiles => 'Omi sau đó đồng bộ hóa các tệp âm thanh với máy chủ';

  @override
  String get serverProcessesAudio => 'Máy chủ xử lý các tệp âm thanh và tạo ký ức';

  @override
  String get youreAllSet => 'Bạn đã sẵn sàng!';

  @override
  String get welcomeToOmiDescription => 'Chào mừng đến với Omi! Người bạn đồng hành AI của bạn đã sẵn sàng hỗ trợ bạn với các cuộc trò chuyện, nhiệm vụ và hơn thế nữa.';

  @override
  String get startUsingOmi => 'Bắt đầu sử dụng Omi';

  @override
  String get back => 'Quay lại';

  @override
  String get keyboardShortcuts => 'Phím tắt';

  @override
  String get toggleControlBar => 'Chuyển đổi thanh điều khiển';

  @override
  String get pressKeys => 'Nhấn phím...';

  @override
  String get cmdRequired => '⌘ bắt buộc';

  @override
  String get invalidKey => 'Phím không hợp lệ';

  @override
  String get space => 'Dấu cách';

  @override
  String get search => 'Tìm kiếm';

  @override
  String get searchPlaceholder => 'Tìm kiếm...';

  @override
  String get untitledConversation => 'Cuộc trò chuyện không có tiêu đề';

  @override
  String countRemaining(String count) {
    return '$count còn lại';
  }

  @override
  String get addGoal => 'Thêm mục tiêu';

  @override
  String get editGoal => 'Chỉnh sửa mục tiêu';

  @override
  String get icon => 'Biểu tượng';

  @override
  String get goalTitle => 'Tiêu đề mục tiêu';

  @override
  String get current => 'Hiện tại';

  @override
  String get target => 'Mục tiêu';

  @override
  String get saveGoal => 'Lưu';

  @override
  String get goals => 'Mục tiêu';

  @override
  String get tapToAddGoal => 'Nhấn để thêm mục tiêu';

  @override
  String welcomeBack(String name) {
    return 'Chào mừng trở lại, $name';
  }

  @override
  String get yourConversations => 'Cuộc trò chuyện của bạn';

  @override
  String get reviewAndManageConversations => 'Xem xét và quản lý các cuộc trò chuyện đã ghi âm';

  @override
  String get startCapturingConversations => 'Bắt đầu ghi lại các cuộc trò chuyện bằng thiết bị Omi của bạn để xem chúng ở đây.';

  @override
  String get useMobileAppToCapture => 'Sử dụng ứng dụng di động của bạn để ghi âm';

  @override
  String get conversationsProcessedAutomatically => 'Các cuộc trò chuyện được xử lý tự động';

  @override
  String get getInsightsInstantly => 'Nhận thông tin chi tiết và tóm tắt ngay lập tức';

  @override
  String get showAll => 'Hiển thị tất cả →';

  @override
  String get noTasksForToday => 'Không có nhiệm vụ cho hôm nay.\\nHỏi Omi để có thêm nhiệm vụ hoặc tạo thủ công.';

  @override
  String get dailyScore => 'ĐIỂM HÀNG NGÀY';

  @override
  String get dailyScoreDescription => 'Điểm giúp bạn tập trung tốt hơn vào việc thực hiện.';

  @override
  String get searchResults => 'Kết quả tìm kiếm';

  @override
  String get actionItems => 'Mục hành động';

  @override
  String get tasksToday => 'Hôm nay';

  @override
  String get tasksTomorrow => 'Ngày mai';

  @override
  String get tasksNoDeadline => 'Không có thời hạn';

  @override
  String get tasksLater => 'Sau này';

  @override
  String get loadingTasks => 'Đang tải nhiệm vụ...';

  @override
  String get tasks => 'Nhiệm vụ';

  @override
  String get swipeTasksToIndent => 'Vuốt nhiệm vụ để thụt lề, kéo giữa các danh mục';

  @override
  String get create => 'Tạo';

  @override
  String get noTasksYet => 'Chưa có nhiệm vụ nào';

  @override
  String get tasksFromConversationsWillAppear => 'Nhiệm vụ từ các cuộc trò chuyện của bạn sẽ xuất hiện ở đây.\nNhấp vào Tạo để thêm một cách thủ công.';

  @override
  String get monthJan => 'Thg 1';

  @override
  String get monthFeb => 'Thg 2';

  @override
  String get monthMar => 'Thg 3';

  @override
  String get monthApr => 'Thg 4';

  @override
  String get monthMay => 'Thg 5';

  @override
  String get monthJun => 'Thg 6';

  @override
  String get monthJul => 'Thg 7';

  @override
  String get monthAug => 'Thg 8';

  @override
  String get monthSep => 'Thg 9';

  @override
  String get monthOct => 'Thg 10';

  @override
  String get monthNov => 'Thg 11';

  @override
  String get monthDec => 'Thg 12';

  @override
  String get timePM => 'CH';

  @override
  String get timeAM => 'SA';

  @override
  String get actionItemUpdatedSuccessfully => 'Mục hành động đã được cập nhật thành công';

  @override
  String get actionItemCreatedSuccessfully => 'Mục hành động đã được tạo thành công';

  @override
  String get actionItemDeletedSuccessfully => 'Mục hành động đã được xóa thành công';

  @override
  String get deleteActionItem => 'Xóa mục hành động';

  @override
  String get deleteActionItemConfirmation => 'Bạn có chắc chắn muốn xóa mục hành động này không? Hành động này không thể hoàn tác.';

  @override
  String get enterActionItemDescription => 'Nhập mô tả mục hành động...';

  @override
  String get markAsCompleted => 'Đánh dấu là đã hoàn thành';

  @override
  String get setDueDateAndTime => 'Đặt ngày và giờ đến hạn';

  @override
  String get reloadingApps => 'Đang tải lại ứng dụng...';

  @override
  String get loadingApps => 'Đang tải ứng dụng...';

  @override
  String get browseInstallCreateApps => 'Duyệt, cài đặt và tạo ứng dụng';

  @override
  String get all => 'Tất cả';

  @override
  String get open => 'Mở';

  @override
  String get install => 'Cài đặt';

  @override
  String get noAppsAvailable => 'Không có ứng dụng nào';

  @override
  String get unableToLoadApps => 'Không thể tải ứng dụng';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'Thử điều chỉnh từ khóa tìm kiếm hoặc bộ lọc của bạn';

  @override
  String get checkBackLaterForNewApps => 'Quay lại sau để xem ứng dụng mới';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'Vui lòng kiểm tra kết nối internet của bạn và thử lại';

  @override
  String get createNewApp => 'Tạo Ứng dụng Mới';

  @override
  String get buildSubmitCustomOmiApp => 'Xây dựng và gửi ứng dụng Omi tùy chỉnh của bạn';

  @override
  String get submittingYourApp => 'Đang gửi ứng dụng của bạn...';

  @override
  String get preparingFormForYou => 'Đang chuẩn bị biểu mẫu cho bạn...';

  @override
  String get appDetails => 'Chi tiết Ứng dụng';

  @override
  String get paymentDetails => 'Chi tiết Thanh toán';

  @override
  String get previewAndScreenshots => 'Xem trước và Ảnh chụp màn hình';

  @override
  String get appCapabilities => 'Khả năng Ứng dụng';

  @override
  String get aiPrompts => 'Lời nhắc AI';

  @override
  String get chatPrompt => 'Lời nhắc Trò chuyện';

  @override
  String get chatPromptPlaceholder => 'Bạn là một ứng dụng tuyệt vời, công việc của bạn là trả lời các truy vấn của người dùng và làm cho họ cảm thấy tốt...';

  @override
  String get conversationPrompt => 'Lời nhắc hội thoại';

  @override
  String get conversationPromptPlaceholder => 'Bạn là một ứng dụng tuyệt vời, bạn sẽ được cung cấp bản ghi và tóm tắt cuộc trò chuyện...';

  @override
  String get notificationScopes => 'Phạm vi Thông báo';

  @override
  String get appPrivacyAndTerms => 'Quyền riêng tư và Điều khoản Ứng dụng';

  @override
  String get makeMyAppPublic => 'Công khai ứng dụng của tôi';

  @override
  String get submitAppTermsAgreement => 'Bằng việc gửi ứng dụng này, tôi đồng ý với Điều khoản Dịch vụ và Chính sách Bảo mật của Omi AI';

  @override
  String get submitApp => 'Gửi Ứng dụng';

  @override
  String get needHelpGettingStarted => 'Cần trợ giúp để bắt đầu?';

  @override
  String get clickHereForAppBuildingGuides => 'Nhấp vào đây để xem hướng dẫn xây dựng ứng dụng và tài liệu';

  @override
  String get submitAppQuestion => 'Gửi Ứng dụng?';

  @override
  String get submitAppPublicDescription => 'Ứng dụng của bạn sẽ được xem xét và công khai. Bạn có thể bắt đầu sử dụng ngay lập tức, ngay cả trong quá trình xem xét!';

  @override
  String get submitAppPrivateDescription => 'Ứng dụng của bạn sẽ được xem xét và có sẵn cho bạn một cách riêng tư. Bạn có thể bắt đầu sử dụng ngay lập tức, ngay cả trong quá trình xem xét!';

  @override
  String get startEarning => 'Bắt đầu Kiếm tiền! 💰';

  @override
  String get connectStripeOrPayPal => 'Kết nối Stripe hoặc PayPal để nhận thanh toán cho ứng dụng của bạn.';

  @override
  String get connectNow => 'Kết nối Ngay';

  @override
  String installsCount(String count) {
    return '$count+ lượt cài đặt';
  }

  @override
  String get uninstallApp => 'Gỡ cài đặt ứng dụng';

  @override
  String get subscribe => 'Đăng ký';

  @override
  String get dataAccessNotice => 'Thông báo truy cập dữ liệu';

  @override
  String get dataAccessWarning => 'Ứng dụng này sẽ truy cập dữ liệu của bạn. Omi AI không chịu trách nhiệm về cách dữ liệu của bạn được sử dụng, sửa đổi hoặc xóa bởi ứng dụng này';

  @override
  String get installApp => 'Cài đặt ứng dụng';

  @override
  String get betaTesterNotice => 'Bạn là người kiểm tra beta cho ứng dụng này. Nó chưa được công khai. Nó sẽ được công khai sau khi được phê duyệt.';

  @override
  String get appUnderReviewOwner => 'Ứng dụng của bạn đang được xem xét và chỉ hiển thị cho bạn. Nó sẽ được công khai sau khi được phê duyệt.';

  @override
  String get appRejectedNotice => 'Ứng dụng của bạn đã bị từ chối. Vui lòng cập nhật chi tiết ứng dụng và gửi lại để xem xét.';

  @override
  String get setupSteps => 'Các bước thiết lập';

  @override
  String get setupInstructions => 'Hướng dẫn thiết lập';

  @override
  String get integrationInstructions => 'Hướng dẫn tích hợp';

  @override
  String get preview => 'Xem trước';

  @override
  String get aboutTheApp => 'Về ứng dụng';

  @override
  String get aboutThePersona => 'Về nhân vật';

  @override
  String get chatPersonality => 'Cá tính trò chuyện';

  @override
  String get ratingsAndReviews => 'Đánh giá & Nhận xét';

  @override
  String get noRatings => 'không có đánh giá';

  @override
  String ratingsCount(String count) {
    return '$count+ đánh giá';
  }

  @override
  String get errorActivatingApp => 'Lỗi kích hoạt ứng dụng';

  @override
  String get integrationSetupRequired => 'Nếu đây là ứng dụng tích hợp, hãy đảm bảo thiết lập đã hoàn tất.';

  @override
  String get installed => 'Đã cài đặt';

  @override
  String get appIdLabel => 'ID ứng dụng';

  @override
  String get appNameLabel => 'Tên ứng dụng';

  @override
  String get appNamePlaceholder => 'Ứng dụng tuyệt vời của tôi';

  @override
  String get pleaseEnterAppName => 'Vui lòng nhập tên ứng dụng';

  @override
  String get categoryLabel => 'Danh mục';

  @override
  String get selectCategory => 'Chọn danh mục';

  @override
  String get descriptionLabel => 'Mô tả';

  @override
  String get appDescriptionPlaceholder => 'Ứng dụng tuyệt vời của tôi là một ứng dụng tuyệt vời làm những điều tuyệt vời. Đây là ứng dụng tốt nhất!';

  @override
  String get pleaseProvideValidDescription => 'Vui lòng cung cấp mô tả hợp lệ';

  @override
  String get appPricingLabel => 'Giá ứng dụng';

  @override
  String get noneSelected => 'Không có lựa chọn';

  @override
  String get appIdCopiedToClipboard => 'Đã sao chép ID ứng dụng vào clipboard';

  @override
  String get appCategoryModalTitle => 'Danh mục ứng dụng';

  @override
  String get pricingFree => 'Miễn phí';

  @override
  String get pricingPaid => 'Trả phí';

  @override
  String get loadingCapabilities => 'Đang tải khả năng...';

  @override
  String get filterInstalled => 'Đã cài đặt';

  @override
  String get filterMyApps => 'Ứng dụng của tôi';

  @override
  String get clearSelection => 'Xóa lựa chọn';

  @override
  String get filterCategory => 'Danh mục';

  @override
  String get rating4PlusStars => '4+ sao';

  @override
  String get rating3PlusStars => '3+ sao';

  @override
  String get rating2PlusStars => '2+ sao';

  @override
  String get rating1PlusStars => '1+ sao';

  @override
  String get filterRating => 'Đánh giá';

  @override
  String get filterCapabilities => 'Khả năng';

  @override
  String get noNotificationScopesAvailable => 'Không có phạm vi thông báo nào';

  @override
  String get popularApps => 'Ứng dụng phổ biến';

  @override
  String get pleaseProvidePrompt => 'Vui lòng cung cấp lời nhắc';

  @override
  String chatWithAppName(String appName) {
    return 'Trò chuyện với $appName';
  }

  @override
  String get defaultAiAssistant => 'Trợ lý AI mặc định';

  @override
  String get readyToChat => '✨ Sẵn sàng trò chuyện!';

  @override
  String get connectionNeeded => '🌐 Cần kết nối';

  @override
  String get startConversation => 'Bắt đầu cuộc trò chuyện và để phép màu bắt đầu';

  @override
  String get checkInternetConnection => 'Vui lòng kiểm tra kết nối internet của bạn';

  @override
  String get wasThisHelpful => 'Điều này có hữu ích không?';

  @override
  String get thankYouForFeedback => 'Cảm ơn phản hồi của bạn!';

  @override
  String get maxFilesUploadError => 'Bạn chỉ có thể tải lên 4 tệp cùng một lúc';

  @override
  String get attachedFiles => '📎 Tệp đính kèm';

  @override
  String get takePhoto => 'Chụp ảnh';

  @override
  String get captureWithCamera => 'Chụp bằng máy ảnh';

  @override
  String get selectImages => 'Chọn hình ảnh';

  @override
  String get chooseFromGallery => 'Chọn từ thư viện';

  @override
  String get selectFile => 'Chọn tệp';

  @override
  String get chooseAnyFileType => 'Chọn bất kỳ loại tệp nào';

  @override
  String get cannotReportOwnMessages => 'Bạn không thể báo cáo tin nhắn của chính mình';

  @override
  String get messageReportedSuccessfully => '✅ Tin nhắn đã được báo cáo thành công';

  @override
  String get confirmReportMessage => 'Bạn có chắc chắn muốn báo cáo tin nhắn này không?';

  @override
  String get selectChatAssistant => 'Chọn trợ lý trò chuyện';

  @override
  String get enableMoreApps => 'Kích hoạt thêm ứng dụng';

  @override
  String get chatCleared => 'Đã xóa cuộc trò chuyện';

  @override
  String get clearChatTitle => 'Xóa cuộc trò chuyện?';

  @override
  String get confirmClearChat => 'Bạn có chắc chắn muốn xóa cuộc trò chuyện không? Hành động này không thể hoàn tác.';

  @override
  String get copy => 'Sao chép';

  @override
  String get share => 'Chia sẻ';

  @override
  String get report => 'Báo cáo';

  @override
  String get microphonePermissionRequired => 'Cần quyền microphone để ghi âm giọng nói.';

  @override
  String get microphonePermissionDenied => 'Quyền microphone bị từ chối. Vui lòng cấp quyền trong Tùy chọn Hệ thống > Quyền riêng tư & Bảo mật > Microphone.';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'Không thể kiểm tra quyền microphone: $error';
  }

  @override
  String get failedToTranscribeAudio => 'Không thể phiên âm audio';

  @override
  String get transcribing => 'Đang phiên âm...';

  @override
  String get transcriptionFailed => 'Phiên âm thất bại';

  @override
  String get discardedConversation => 'Cuộc trò chuyện bị loại bỏ';

  @override
  String get at => 'lúc';

  @override
  String get from => 'từ';

  @override
  String get copied => 'Đã sao chép!';

  @override
  String get copyLink => 'Sao chép liên kết';

  @override
  String get hideTranscript => 'Ẩn Bản ghi';

  @override
  String get viewTranscript => 'Xem Bản ghi';

  @override
  String get conversationDetails => 'Chi tiết Cuộc trò chuyện';

  @override
  String get transcript => 'Bản ghi';

  @override
  String segmentsCount(int count) {
    return '$count đoạn';
  }

  @override
  String get noTranscriptAvailable => 'Không có Bản ghi';

  @override
  String get noTranscriptMessage => 'Cuộc trò chuyện này không có bản ghi.';

  @override
  String get conversationUrlCouldNotBeGenerated => 'Không thể tạo URL cuộc trò chuyện.';

  @override
  String get failedToGenerateConversationLink => 'Không tạo được liên kết cuộc trò chuyện';

  @override
  String get failedToGenerateShareLink => 'Không tạo được liên kết chia sẻ';

  @override
  String get reloadingConversations => 'Đang tải lại cuộc trò chuyện...';

  @override
  String get user => 'Người dùng';

  @override
  String get starred => 'Đã gắn sao';

  @override
  String get date => 'Ngày';

  @override
  String get noResultsFound => 'Không tìm thấy kết quả';

  @override
  String get tryAdjustingSearchTerms => 'Thử điều chỉnh các từ khóa tìm kiếm của bạn';

  @override
  String get starConversationsToFindQuickly => 'Gắn sao cuộc trò chuyện để tìm chúng nhanh chóng ở đây';

  @override
  String noConversationsOnDate(String date) {
    return 'Không có cuộc trò chuyện vào ngày $date';
  }

  @override
  String get trySelectingDifferentDate => 'Thử chọn ngày khác';

  @override
  String get conversations => 'Cuộc trò chuyện';

  @override
  String get chat => 'Trò chuyện';

  @override
  String get actions => 'Hành động';

  @override
  String get syncAvailable => 'Đồng bộ có sẵn';

  @override
  String get referAFriend => 'Giới thiệu bạn bè';

  @override
  String get help => 'Trợ giúp';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'Nâng cấp lên Pro';

  @override
  String get getOmiDevice => 'Nhận thiết bị Omi';

  @override
  String get wearableAiCompanion => 'Trợ lý AI đeo được';

  @override
  String get loadingMemories => 'Đang tải ký ức...';

  @override
  String get allMemories => 'Tất cả ký ức';

  @override
  String get aboutYou => 'Về bạn';

  @override
  String get manual => 'Thủ công';

  @override
  String get loadingYourMemories => 'Đang tải ký ức của bạn...';

  @override
  String get createYourFirstMemory => 'Tạo ký ức đầu tiên để bắt đầu';

  @override
  String get tryAdjustingFilter => 'Thử điều chỉnh tìm kiếm hoặc bộ lọc của bạn';

  @override
  String get whatWouldYouLikeToRemember => 'Bạn muốn nhớ điều gì?';

  @override
  String get category => 'Danh mục';

  @override
  String get public => 'Công khai';

  @override
  String get failedToSaveCheckConnection => 'Lưu thất bại. Vui lòng kiểm tra kết nối của bạn.';

  @override
  String get createMemory => 'Tạo bộ nhớ';

  @override
  String get deleteMemoryConfirmation => 'Bạn có chắc chắn muốn xóa bộ nhớ này không? Hành động này không thể hoàn tác.';

  @override
  String get makePrivate => 'Riêng tư';

  @override
  String get organizeAndControlMemories => 'Tổ chức và kiểm soát ký ức của bạn';

  @override
  String get total => 'Tổng cộng';

  @override
  String get makeAllMemoriesPrivate => 'Đặt tất cả ký ức thành riêng tư';

  @override
  String get setAllMemoriesToPrivate => 'Đặt tất cả ký ức thành riêng tư';

  @override
  String get makeAllMemoriesPublic => 'Đặt tất cả ký ức thành công khai';

  @override
  String get setAllMemoriesToPublic => 'Đặt tất cả ký ức thành công khai';

  @override
  String get permanentlyRemoveAllMemories => 'Xóa vĩnh viễn tất cả ký ức khỏi Omi';

  @override
  String get allMemoriesAreNowPrivate => 'Tất cả ký ức hiện đã ở chế độ riêng tư';

  @override
  String get allMemoriesAreNowPublic => 'Tất cả ký ức hiện đã ở chế độ công khai';

  @override
  String get clearOmisMemory => 'Xóa bộ nhớ của Omi';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Bạn có chắc chắn muốn xóa bộ nhớ của Omi không? Hành động này không thể hoàn tác và sẽ xóa vĩnh viễn tất cả $count ký ức.';
  }

  @override
  String get omisMemoryCleared => 'Bộ nhớ của Omi về bạn đã được xóa';

  @override
  String get welcomeToOmi => 'Chào mừng đến với Omi';

  @override
  String get continueWithApple => 'Tiếp tục với Apple';

  @override
  String get continueWithGoogle => 'Tiếp tục với Google';

  @override
  String get byContinuingYouAgree => 'Bằng cách tiếp tục, bạn đồng ý với ';

  @override
  String get termsOfService => 'Điều khoản dịch vụ';

  @override
  String get and => ' và ';

  @override
  String get dataAndPrivacy => 'Dữ liệu & Quyền riêng tư';

  @override
  String get secureAuthViaAppleId => 'Xác thực an toàn qua Apple ID';

  @override
  String get secureAuthViaGoogleAccount => 'Xác thực an toàn qua tài khoản Google';

  @override
  String get whatWeCollect => 'Những gì chúng tôi thu thập';

  @override
  String get dataCollectionMessage => 'Bằng cách tiếp tục, các cuộc trò chuyện, bản ghi và thông tin cá nhân của bạn sẽ được lưu trữ an toàn trên máy chủ của chúng tôi để cung cấp thông tin chi tiết được hỗ trợ bởi AI và kích hoạt tất cả các tính năng ứng dụng.';

  @override
  String get dataProtection => 'Bảo vệ dữ liệu';

  @override
  String get yourDataIsProtected => 'Dữ liệu của bạn được bảo vệ và quản lý bởi ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'Vui lòng chọn ngôn ngữ chính của bạn';

  @override
  String get chooseYourLanguage => 'Chọn ngôn ngữ của bạn';

  @override
  String get selectPreferredLanguageForBestExperience => 'Chọn ngôn ngữ ưu tiên của bạn để có trải nghiệm Omi tốt nhất';

  @override
  String get searchLanguages => 'Tìm kiếm ngôn ngữ...';

  @override
  String get selectALanguage => 'Chọn một ngôn ngữ';

  @override
  String get tryDifferentSearchTerm => 'Thử một từ khóa tìm kiếm khác';

  @override
  String get pleaseEnterYourName => 'Vui lòng nhập tên của bạn';

  @override
  String get nameMustBeAtLeast2Characters => 'Tên phải có ít nhất 2 ký tự';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed => 'Cho chúng tôi biết bạn muốn được gọi như thế nào. Điều này giúp cá nhân hóa trải nghiệm Omi của bạn.';

  @override
  String charactersCount(int count) {
    return '$count ký tự';
  }

  @override
  String get enableFeaturesForBestExperience => 'Bật các tính năng để có trải nghiệm Omi tốt nhất trên thiết bị của bạn.';

  @override
  String get microphoneAccess => 'Quyền truy cập micrô';

  @override
  String get recordAudioConversations => 'Ghi âm cuộc trò chuyện';

  @override
  String get microphoneAccessDescription => 'Omi cần quyền truy cập micrô để ghi lại các cuộc trò chuyện của bạn và cung cấp bản ghi âm.';

  @override
  String get screenRecording => 'Ghi màn hình';

  @override
  String get captureSystemAudioFromMeetings => 'Ghi âm hệ thống từ các cuộc họp';

  @override
  String get screenRecordingDescription => 'Omi cần quyền ghi màn hình để ghi âm hệ thống từ các cuộc họp dựa trên trình duyệt của bạn.';

  @override
  String get accessibility => 'Khả năng truy cập';

  @override
  String get detectBrowserBasedMeetings => 'Phát hiện các cuộc họp dựa trên trình duyệt';

  @override
  String get accessibilityDescription => 'Omi cần quyền truy cập để phát hiện khi bạn tham gia các cuộc họp Zoom, Meet hoặc Teams trong trình duyệt của bạn.';

  @override
  String get pleaseWait => 'Vui lòng đợi...';

  @override
  String get joinTheCommunity => 'Tham gia cộng đồng!';

  @override
  String get loadingProfile => 'Đang tải hồ sơ...';

  @override
  String get profileSettings => 'Cài đặt hồ sơ';

  @override
  String get noEmailSet => 'Chưa đặt email';

  @override
  String get userIdCopiedToClipboard => 'Đã sao chép ID người dùng';

  @override
  String get yourInformation => 'Thông tin của Bạn';

  @override
  String get setYourName => 'Đặt tên của bạn';

  @override
  String get changeYourName => 'Thay đổi tên của bạn';

  @override
  String get manageYourOmiPersona => 'Quản lý persona Omi của bạn';

  @override
  String get voiceAndPeople => 'Giọng nói & Con người';

  @override
  String get teachOmiYourVoice => 'Dạy Omi giọng nói của bạn';

  @override
  String get tellOmiWhoSaidIt => 'Cho Omi biết ai đã nói điều đó 🗣️';

  @override
  String get payment => 'Thanh toán';

  @override
  String get addOrChangeYourPaymentMethod => 'Thêm hoặc thay đổi phương thức thanh toán';

  @override
  String get preferences => 'Tùy chọn';

  @override
  String get helpImproveOmiBySharing => 'Giúp cải thiện Omi bằng cách chia sẻ dữ liệu phân tích ẩn danh';

  @override
  String get deleteAccount => 'Xóa Tài khoản';

  @override
  String get deleteYourAccountAndAllData => 'Xóa tài khoản và tất cả dữ liệu của bạn';

  @override
  String get clearLogs => 'Xóa nhật ký';

  @override
  String get debugLogsCleared => 'Đã xóa nhật ký gỡ lỗi';

  @override
  String get exportConversations => 'Xuất cuộc trò chuyện';

  @override
  String get exportAllConversationsToJson => 'Xuất tất cả cuộc trò chuyện của bạn vào tệp JSON.';

  @override
  String get conversationsExportStarted => 'Đã bắt đầu xuất cuộc trò chuyện. Điều này có thể mất vài giây, vui lòng đợi.';

  @override
  String get mcpDescription => 'Để kết nối Omi với các ứng dụng khác để đọc, tìm kiếm và quản lý ký ức và cuộc trò chuyện của bạn. Tạo khóa để bắt đầu.';

  @override
  String get apiKeys => 'Khóa API';

  @override
  String errorLabel(String error) {
    return 'Lỗi: $error';
  }

  @override
  String get noApiKeysFound => 'Không tìm thấy khóa API. Tạo một khóa để bắt đầu.';

  @override
  String get advancedSettings => 'Cài đặt nâng cao';

  @override
  String get triggersWhenNewConversationCreated => 'Kích hoạt khi tạo cuộc trò chuyện mới.';

  @override
  String get triggersWhenNewTranscriptReceived => 'Kích hoạt khi nhận được bản ghi mới.';

  @override
  String get realtimeAudioBytes => 'Byte âm thanh thời gian thực';

  @override
  String get triggersWhenAudioBytesReceived => 'Kích hoạt khi nhận được byte âm thanh.';

  @override
  String get everyXSeconds => 'Mỗi x giây';

  @override
  String get triggersWhenDaySummaryGenerated => 'Kích hoạt khi tạo tóm tắt ngày.';

  @override
  String get tryLatestExperimentalFeatures => 'Dùng thử các tính năng thử nghiệm mới nhất từ ​​Nhóm Omi.';

  @override
  String get transcriptionServiceDiagnosticStatus => 'Trạng thái chẩn đoán dịch vụ phiên âm';

  @override
  String get enableDetailedDiagnosticMessages => 'Bật thông báo chẩn đoán chi tiết từ dịch vụ phiên âm';

  @override
  String get autoCreateAndTagNewSpeakers => 'Tự động tạo và gắn thẻ người nói mới';

  @override
  String get automaticallyCreateNewPerson => 'Tự động tạo người mới khi phát hiện tên trong bản ghi.';

  @override
  String get pilotFeatures => 'Tính năng thử nghiệm';

  @override
  String get pilotFeaturesDescription => 'Các tính năng này là thử nghiệm và không đảm bảo hỗ trợ.';

  @override
  String get suggestFollowUpQuestion => 'Đề xuất câu hỏi tiếp theo';

  @override
  String get saveSettings => 'Lưu Cài đặt';

  @override
  String get syncingDeveloperSettings => 'Đang đồng bộ cài đặt nhà phát triển...';

  @override
  String get summary => 'Tóm tắt';

  @override
  String get auto => 'Tự động';

  @override
  String get noSummaryForApp => 'Không có bản tóm tắt nào cho ứng dụng này. Hãy thử ứng dụng khác để có kết quả tốt hơn.';

  @override
  String get tryAnotherApp => 'Thử ứng dụng khác';

  @override
  String generatedBy(String appName) {
    return 'Được tạo bởi $appName';
  }

  @override
  String get overview => 'Tổng quan';

  @override
  String get otherAppResults => 'Kết quả từ các ứng dụng khác';

  @override
  String get unknownApp => 'Ứng dụng không xác định';

  @override
  String get noSummaryAvailable => 'Không có bản tóm tắt';

  @override
  String get conversationNoSummaryYet => 'Cuộc trò chuyện này chưa có bản tóm tắt.';

  @override
  String get chooseSummarizationApp => 'Chọn ứng dụng tóm tắt';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return 'Đã đặt $appName làm ứng dụng tóm tắt mặc định';
  }

  @override
  String get letOmiChooseAutomatically => 'Để Omi tự động chọn ứng dụng tốt nhất';

  @override
  String get deleteConversationConfirmation => 'Bạn có chắc chắn muốn xóa cuộc trò chuyện này không? Hành động này không thể hoàn tác.';

  @override
  String get conversationDeleted => 'Đã xóa cuộc trò chuyện';

  @override
  String get generatingLink => 'Đang tạo liên kết...';

  @override
  String get editConversation => 'Chỉnh sửa cuộc trò chuyện';

  @override
  String get conversationLinkCopiedToClipboard => 'Đã sao chép liên kết cuộc trò chuyện vào clipboard';

  @override
  String get conversationTranscriptCopiedToClipboard => 'Đã sao chép bản ghi cuộc trò chuyện vào clipboard';

  @override
  String get editConversationDialogTitle => 'Chỉnh sửa cuộc trò chuyện';

  @override
  String get changeTheConversationTitle => 'Thay đổi tiêu đề cuộc trò chuyện';

  @override
  String get conversationTitle => 'Tiêu đề cuộc trò chuyện';

  @override
  String get enterConversationTitle => 'Nhập tiêu đề cuộc trò chuyện...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'Đã cập nhật tiêu đề cuộc trò chuyện thành công';

  @override
  String get failedToUpdateConversationTitle => 'Không cập nhật được tiêu đề cuộc trò chuyện';

  @override
  String get errorUpdatingConversationTitle => 'Lỗi khi cập nhật tiêu đề cuộc trò chuyện';

  @override
  String get settingUp => 'Đang thiết lập...';

  @override
  String get startYourFirstRecording => 'Bắt đầu bản ghi đầu tiên của bạn';

  @override
  String get preparingSystemAudioCapture => 'Đang chuẩn bị ghi âm hệ thống';

  @override
  String get clickTheButtonToCaptureAudio => 'Nhấp vào nút để ghi âm cho bản ghi trực tiếp, thông tin chi tiết AI và lưu tự động.';

  @override
  String get reconnecting => 'Đang kết nối lại...';

  @override
  String get recordingPaused => 'Ghi âm đã tạm dừng';

  @override
  String get recordingActive => 'Ghi âm đang hoạt động';

  @override
  String get startRecording => 'Bắt đầu ghi âm';

  @override
  String resumingInCountdown(String countdown) {
    return 'Tiếp tục trong ${countdown}s...';
  }

  @override
  String get tapPlayToResume => 'Nhấn phát để tiếp tục';

  @override
  String get listeningForAudio => 'Đang lắng nghe âm thanh...';

  @override
  String get preparingAudioCapture => 'Đang chuẩn bị ghi âm';

  @override
  String get clickToBeginRecording => 'Nhấp để bắt đầu ghi âm';

  @override
  String get translated => 'đã dịch';

  @override
  String get liveTranscript => 'Bản ghi trực tiếp';

  @override
  String segmentsSingular(String count) {
    return '$count đoạn';
  }

  @override
  String segmentsPlural(String count) {
    return '$count đoạn';
  }

  @override
  String get startRecordingToSeeTranscript => 'Bắt đầu ghi âm để xem bản ghi trực tiếp';

  @override
  String get paused => 'Đã tạm dừng';

  @override
  String get initializing => 'Đang khởi tạo...';

  @override
  String get recording => 'Đang ghi âm';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'Micro đã thay đổi. Tiếp tục trong ${countdown}s';
  }

  @override
  String get clickPlayToResumeOrStop => 'Nhấp phát để tiếp tục hoặc dừng để kết thúc';

  @override
  String get settingUpSystemAudioCapture => 'Đang thiết lập ghi âm hệ thống';

  @override
  String get capturingAudioAndGeneratingTranscript => 'Đang ghi âm và tạo bản ghi';

  @override
  String get clickToBeginRecordingSystemAudio => 'Nhấp để bắt đầu ghi âm hệ thống';

  @override
  String get you => 'Bạn';

  @override
  String speakerWithId(String speakerId) {
    return 'Người nói $speakerId';
  }

  @override
  String get translatedByOmi => 'dịch bởi omi';

  @override
  String get backToConversations => 'Quay lại cuộc trò chuyện';

  @override
  String get systemAudio => 'Hệ thống';

  @override
  String get mic => 'Micro';

  @override
  String audioInputSetTo(String deviceName) {
    return 'Đầu vào âm thanh đã đặt thành $deviceName';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'Lỗi chuyển đổi thiết bị âm thanh: $error';
  }

  @override
  String get selectAudioInput => 'Chọn đầu vào âm thanh';

  @override
  String get loadingDevices => 'Đang tải thiết bị...';

  @override
  String get settingsHeader => 'CÀI ĐẶT';

  @override
  String get plansAndBilling => 'Gói và Thanh toán';

  @override
  String get calendarIntegration => 'Tích hợp Lịch';

  @override
  String get dailySummary => 'Tóm tắt Hàng ngày';

  @override
  String get developer => 'Nhà phát triển';

  @override
  String get about => 'Giới thiệu';

  @override
  String get selectTime => 'Chọn Thời gian';

  @override
  String get accountGroup => 'Tài khoản';

  @override
  String get signOutQuestion => 'Đăng xuất?';

  @override
  String get signOutConfirmation => 'Bạn có chắc chắn muốn đăng xuất không?';

  @override
  String get customVocabularyHeader => 'TỪ VỰNG TÙY CHỈNH';

  @override
  String get addWordsDescription => 'Thêm từ mà Omi nên nhận biết trong quá trình phiên âm.';

  @override
  String get enterWordsHint => 'Nhập từ (phân tách bằng dấu phẩy)';

  @override
  String get dailySummaryHeader => 'TÓM TẮT HÀNG NGÀY';

  @override
  String get dailySummaryTitle => 'Tóm tắt Hàng ngày';

  @override
  String get dailySummaryDescription => 'Nhận tóm tắt cá nhân hóa về các cuộc trò chuyện của bạn';

  @override
  String get deliveryTime => 'Thời gian Giao hàng';

  @override
  String get deliveryTimeDescription => 'Khi nào nhận tóm tắt hàng ngày của bạn';

  @override
  String get subscription => 'Đăng ký';

  @override
  String get viewPlansAndUsage => 'Xem Gói & Sử dụng';

  @override
  String get viewPlansDescription => 'Quản lý đăng ký và xem thống kê sử dụng';

  @override
  String get addOrChangePaymentMethod => 'Thêm hoặc thay đổi phương thức thanh toán của bạn';

  @override
  String get displayOptions => 'Tùy chọn Hiển thị';

  @override
  String get showMeetingsInMenuBar => 'Hiển thị Cuộc họp trong Thanh Menu';

  @override
  String get displayUpcomingMeetingsDescription => 'Hiển thị các cuộc họp sắp tới trong thanh menu';

  @override
  String get showEventsWithoutParticipants => 'Hiển thị Sự kiện Không có Người tham gia';

  @override
  String get includePersonalEventsDescription => 'Bao gồm các sự kiện cá nhân không có người tham dự';

  @override
  String get upcomingMeetings => 'CÁC CUỘC HỌP SẮP TỚI';

  @override
  String get checkingNext7Days => 'Kiểm tra 7 ngày tiếp theo';

  @override
  String get shortcuts => 'Phím tắt';

  @override
  String get shortcutChangeInstruction => 'Nhấp vào phím tắt để thay đổi. Nhấn Escape để hủy.';

  @override
  String get configurePersonaDescription => 'Cấu hình nhân vật AI của bạn';

  @override
  String get configureSTTProvider => 'Cấu hình nhà cung cấp STT';

  @override
  String get setConversationEndDescription => 'Đặt khi nào cuộc trò chuyện tự động kết thúc';

  @override
  String get importDataDescription => 'Nhập dữ liệu từ các nguồn khác';

  @override
  String get exportConversationsDescription => 'Xuất cuộc trò chuyện sang JSON';

  @override
  String get exportingConversations => 'Đang xuất cuộc trò chuyện...';

  @override
  String get clearNodesDescription => 'Xóa tất cả các nút và kết nối';

  @override
  String get deleteKnowledgeGraphQuestion => 'Xóa Đồ thị Tri thức?';

  @override
  String get deleteKnowledgeGraphWarning => 'Điều này sẽ xóa tất cả dữ liệu đồ thị tri thức dẫn xuất. Ký ức gốc của bạn vẫn an toàn.';

  @override
  String get connectOmiWithAI => 'Kết nối Omi với trợ lý AI';

  @override
  String get noAPIKeys => 'Không có khóa API. Tạo một khóa để bắt đầu.';

  @override
  String get autoCreateWhenDetected => 'Tự động tạo khi phát hiện tên';

  @override
  String get trackPersonalGoals => 'Theo dõi mục tiêu cá nhân trên trang chủ';

  @override
  String get dailyReflectionDescription => 'Nhắc nhở lúc 9 giờ tối để suy ngẫm về ngày của bạn';

  @override
  String get endpointURL => 'URL Điểm cuối';

  @override
  String get links => 'Liên kết';

  @override
  String get discordMemberCount => 'Hơn 8000 thành viên trên Discord';

  @override
  String get userInformation => 'Thông tin Người dùng';

  @override
  String get capabilities => 'Khả năng';

  @override
  String get previewScreenshots => 'Xem trước ảnh chụp màn hình';

  @override
  String get holdOnPreparingForm => 'Vui lòng đợi, chúng tôi đang chuẩn bị biểu mẫu cho bạn';

  @override
  String get bySubmittingYouAgreeToOmi => 'Bằng việc gửi, bạn đồng ý với ';

  @override
  String get termsAndPrivacyPolicy => 'Điều khoản và Chính sách Bảo mật';

  @override
  String get helpsDiagnoseIssuesAutoDeletes => 'Giúp chẩn đoán sự cố. Tự động xóa sau 3 ngày.';

  @override
  String get manageYourApp => 'Quản lý ứng dụng của bạn';

  @override
  String get updatingYourApp => 'Đang cập nhật ứng dụng của bạn';

  @override
  String get fetchingYourAppDetails => 'Đang tải thông tin ứng dụng';

  @override
  String get updateAppQuestion => 'Cập nhật ứng dụng?';

  @override
  String get updateAppConfirmation => 'Bạn có chắc chắn muốn cập nhật ứng dụng? Các thay đổi sẽ được phản ánh sau khi được đội ngũ của chúng tôi xem xét.';

  @override
  String get updateApp => 'Cập nhật ứng dụng';

  @override
  String get createAndSubmitNewApp => 'Tạo và gửi ứng dụng mới';

  @override
  String appsCount(String count) {
    return 'Ứng dụng ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'Ứng dụng riêng tư ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'Ứng dụng công khai ($count)';
  }

  @override
  String get newVersionAvailable => 'Có phiên bản mới  🎉';

  @override
  String get no => 'Không';

  @override
  String get subscriptionCancelledSuccessfully => 'Đã hủy đăng ký thành công. Nó sẽ vẫn hoạt động cho đến cuối kỳ thanh toán hiện tại.';

  @override
  String get failedToCancelSubscription => 'Không thể hủy đăng ký. Vui lòng thử lại.';

  @override
  String get invalidPaymentUrl => 'URL thanh toán không hợp lệ';

  @override
  String get permissionsAndTriggers => 'Quyền và trình kích hoạt';

  @override
  String get chatFeatures => 'Tính năng trò chuyện';

  @override
  String get uninstall => 'Gỡ cài đặt';

  @override
  String get installs => 'LƯỢT CÀI ĐẶT';

  @override
  String get priceLabel => 'GIÁ';

  @override
  String get updatedLabel => 'CẬP NHẬT';

  @override
  String get createdLabel => 'TẠO LÚC';

  @override
  String get featuredLabel => 'NỔI BẬT';

  @override
  String get cancelSubscriptionQuestion => 'Hủy đăng ký?';

  @override
  String get cancelSubscriptionConfirmation => 'Bạn có chắc chắn muốn hủy đăng ký? Bạn sẽ tiếp tục có quyền truy cập cho đến cuối kỳ thanh toán hiện tại.';

  @override
  String get cancelSubscriptionButton => 'Hủy đăng ký';

  @override
  String get cancelling => 'Đang hủy...';

  @override
  String get betaTesterMessage => 'Bạn là người thử nghiệm beta cho ứng dụng này. Nó chưa được công khai. Sẽ được công khai sau khi được phê duyệt.';

  @override
  String get appUnderReviewMessage => 'Ứng dụng của bạn đang được xem xét và chỉ hiển thị với bạn. Sẽ được công khai sau khi được phê duyệt.';

  @override
  String get appRejectedMessage => 'Ứng dụng của bạn đã bị từ chối. Vui lòng cập nhật thông tin và gửi lại để xem xét.';

  @override
  String get invalidIntegrationUrl => 'URL tích hợp không hợp lệ';

  @override
  String get tapToComplete => 'Nhấn để hoàn thành';

  @override
  String get invalidSetupInstructionsUrl => 'URL hướng dẫn cài đặt không hợp lệ';

  @override
  String get pushToTalk => 'Nhấn để nói';

  @override
  String get summaryPrompt => 'Gợi ý tóm tắt';

  @override
  String get pleaseSelectARating => 'Vui lòng chọn đánh giá';

  @override
  String get reviewAddedSuccessfully => 'Đã thêm đánh giá thành công 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'Đã cập nhật đánh giá thành công 🚀';

  @override
  String get failedToSubmitReview => 'Không thể gửi đánh giá. Vui lòng thử lại.';

  @override
  String get addYourReview => 'Thêm đánh giá của bạn';

  @override
  String get editYourReview => 'Chỉnh sửa đánh giá của bạn';

  @override
  String get writeAReviewOptional => 'Viết đánh giá (tùy chọn)';

  @override
  String get submitReview => 'Gửi đánh giá';

  @override
  String get updateReview => 'Cập nhật đánh giá';

  @override
  String get yourReview => 'Đánh giá của bạn';

  @override
  String get anonymousUser => 'Người dùng ẩn danh';

  @override
  String get issueActivatingApp => 'Đã xảy ra sự cố khi kích hoạt ứng dụng này. Vui lòng thử lại.';

  @override
  String get dataAccessNoticeDescription => 'This app will access your data. Omi AI is not responsible for how your data is used, modified, or deleted by this app';

  @override
  String get copyUrl => 'Sao chép URL';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => 'T2';

  @override
  String get weekdayTue => 'T3';

  @override
  String get weekdayWed => 'T4';

  @override
  String get weekdayThu => 'T5';

  @override
  String get weekdayFri => 'T6';

  @override
  String get weekdaySat => 'T7';

  @override
  String get weekdaySun => 'CN';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return 'Tích hợp $serviceName sắp ra mắt';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'Đã xuất sang $platform';
  }

  @override
  String get anotherPlatform => 'nền tảng khác';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'Vui lòng xác thực với $serviceName trong Cài đặt > Tích hợp tác vụ';
  }

  @override
  String addingToService(String serviceName) {
    return 'Đang thêm vào $serviceName...';
  }

  @override
  String addedToService(String serviceName) {
    return 'Đã thêm vào $serviceName';
  }

  @override
  String failedToAddToService(String serviceName) {
    return 'Không thể thêm vào $serviceName';
  }

  @override
  String get permissionDeniedForAppleReminders => 'Quyền truy cập Apple Reminders bị từ chối';

  @override
  String failedToCreateApiKey(String error) {
    return 'Không thể tạo khóa API nhà cung cấp: $error';
  }

  @override
  String get createAKey => 'Tạo khóa';

  @override
  String get apiKeyRevokedSuccessfully => 'Khóa API đã được thu hồi thành công';

  @override
  String failedToRevokeApiKey(String error) {
    return 'Không thể thu hồi khóa API: $error';
  }

  @override
  String get omiApiKeys => 'Khóa API Omi';

  @override
  String get apiKeysDescription => 'Khóa API được sử dụng để xác thực khi ứng dụng của bạn giao tiếp với máy chủ OMI. Chúng cho phép ứng dụng của bạn tạo kỷ niệm và truy cập an toàn vào các dịch vụ OMI khác.';

  @override
  String get aboutOmiApiKeys => 'Về khóa API Omi';

  @override
  String get yourNewKey => 'Khóa mới của bạn:';

  @override
  String get copyToClipboard => 'Sao chép vào bộ nhớ tạm';

  @override
  String get pleaseCopyKeyNow => 'Vui lòng sao chép ngay và ghi lại ở nơi an toàn. ';

  @override
  String get willNotSeeAgain => 'Bạn sẽ không thể xem lại được.';

  @override
  String get revokeKey => 'Thu hồi khóa';

  @override
  String get revokeApiKeyQuestion => 'Thu hồi khóa API?';

  @override
  String get revokeApiKeyWarning => 'Hành động này không thể hoàn tác. Bất kỳ ứng dụng nào sử dụng khóa này sẽ không thể truy cập API nữa.';

  @override
  String get revoke => 'Thu hồi';

  @override
  String get whatWouldYouLikeToCreate => 'Bạn muốn tạo gì?';

  @override
  String get createAnApp => 'Tạo ứng dụng';

  @override
  String get createAndShareYourApp => 'Tạo và chia sẻ ứng dụng của bạn';

  @override
  String get createMyClone => 'Tạo bản sao của tôi';

  @override
  String get createYourDigitalClone => 'Tạo bản sao kỹ thuật số của bạn';

  @override
  String get itemApp => 'Ứng dụng';

  @override
  String get itemPersona => 'Persona';

  @override
  String keepItemPublic(String item) {
    return 'Giữ $item công khai';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return 'Đặt $item thành công khai?';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return 'Đặt $item thành riêng tư?';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'Nếu bạn đặt $item thành công khai, mọi người đều có thể sử dụng';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'Nếu bạn đặt $item thành riêng tư ngay bây giờ, nó sẽ ngừng hoạt động cho mọi người và chỉ hiển thị với bạn';
  }

  @override
  String get manageApp => 'Quản lý ứng dụng';

  @override
  String get updatePersonaDetails => 'Cập nhật chi tiết persona';

  @override
  String deleteItemTitle(String item) {
    return 'Xóa $item';
  }

  @override
  String deleteItemQuestion(String item) {
    return 'Xóa $item?';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'Bạn có chắc chắn muốn xóa $item này? Hành động này không thể hoàn tác.';
  }

  @override
  String get revokeKeyQuestion => 'Thu hồi khóa?';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'Bạn có chắc chắn muốn thu hồi khóa \"$keyName\"? Hành động này không thể hoàn tác.';
  }

  @override
  String get createNewKey => 'Tạo khóa mới';

  @override
  String get keyNameHint => 'vd: Claude Desktop';

  @override
  String get pleaseEnterAName => 'Vui lòng nhập tên.';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'Không thể tạo khóa: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'Không thể tạo khóa. Vui lòng thử lại.';

  @override
  String get keyCreated => 'Đã tạo khóa';

  @override
  String get keyCreatedMessage => 'Khóa mới của bạn đã được tạo. Vui lòng sao chép ngay bây giờ. Bạn sẽ không thể xem lại.';

  @override
  String get keyWord => 'Khóa';

  @override
  String get externalAppAccess => 'Truy cập ứng dụng bên ngoài';

  @override
  String get externalAppAccessDescription => 'Các ứng dụng đã cài đặt sau có tích hợp bên ngoài và có thể truy cập dữ liệu của bạn, chẳng hạn như cuộc trò chuyện và kỷ niệm.';

  @override
  String get noExternalAppsHaveAccess => 'Không có ứng dụng bên ngoài nào có quyền truy cập vào dữ liệu của bạn.';

  @override
  String get maximumSecurityE2ee => 'Bảo mật tối đa (E2EE)';

  @override
  String get e2eeDescription => 'Mã hóa đầu cuối là tiêu chuẩn vàng cho quyền riêng tư. Khi được bật, dữ liệu của bạn được mã hóa trên thiết bị của bạn trước khi gửi đến máy chủ của chúng tôi. Điều này có nghĩa là không ai, kể cả Omi, có thể truy cập nội dung của bạn.';

  @override
  String get importantTradeoffs => 'Đánh đổi quan trọng:';

  @override
  String get e2eeTradeoff1 => '• Một số tính năng như tích hợp ứng dụng bên ngoài có thể bị tắt.';

  @override
  String get e2eeTradeoff2 => '• Nếu bạn mất mật khẩu, dữ liệu của bạn không thể được khôi phục.';

  @override
  String get featureComingSoon => 'Tính năng này sắp ra mắt!';

  @override
  String get migrationInProgressMessage => 'Đang di chuyển. Bạn không thể thay đổi mức bảo vệ cho đến khi hoàn tất.';

  @override
  String get migrationFailed => 'Di chuyển thất bại';

  @override
  String migratingFromTo(String source, String target) {
    return 'Đang di chuyển từ $source sang $target';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total đối tượng';
  }

  @override
  String get secureEncryption => 'Mã hóa an toàn';

  @override
  String get secureEncryptionDescription => 'Dữ liệu của bạn được mã hóa bằng một khóa duy nhất cho bạn trên các máy chủ của chúng tôi, được lưu trữ trên Google Cloud. Điều này có nghĩa là nội dung thô của bạn không thể truy cập được bởi bất kỳ ai, bao gồm nhân viên Omi hoặc Google, trực tiếp từ cơ sở dữ liệu.';

  @override
  String get endToEndEncryption => 'Mã hóa đầu cuối';

  @override
  String get e2eeCardDescription => 'Bật để bảo mật tối đa, nơi chỉ bạn mới có thể truy cập dữ liệu của mình. Nhấn để tìm hiểu thêm.';

  @override
  String get dataAlwaysEncrypted => 'Bất kể mức nào, dữ liệu của bạn luôn được mã hóa khi lưu trữ và khi truyền tải.';

  @override
  String get readOnlyScope => 'Chỉ đọc';

  @override
  String get fullAccessScope => 'Truy cập đầy đủ';

  @override
  String get readScope => 'Đọc';

  @override
  String get writeScope => 'Ghi';

  @override
  String get apiKeyCreated => 'Đã tạo khóa API!';

  @override
  String get saveKeyWarning => 'Lưu khóa này ngay bây giờ! Bạn sẽ không thể xem lại nó.';

  @override
  String get yourApiKey => 'KHÓA API CỦA BẠN';

  @override
  String get tapToCopy => 'Nhấn để sao chép';

  @override
  String get copyKey => 'Sao chép khóa';

  @override
  String get createApiKey => 'Tạo khóa API';

  @override
  String get accessDataProgrammatically => 'Truy cập dữ liệu của bạn theo chương trình';

  @override
  String get keyNameLabel => 'TÊN KHÓA';

  @override
  String get keyNamePlaceholder => 'vd: Tích hợp ứng dụng của tôi';

  @override
  String get permissionsLabel => 'QUYỀN';

  @override
  String get permissionsInfoNote => 'R = Đọc, W = Ghi. Mặc định chỉ đọc nếu không chọn gì.';

  @override
  String get developerApi => 'API nhà phát triển';

  @override
  String get createAKeyToGetStarted => 'Tạo khóa để bắt đầu';

  @override
  String errorWithMessage(String error) {
    return 'Lỗi: $error';
  }

  @override
  String get omiTraining => 'Huấn luyện Omi';

  @override
  String get trainingDataProgram => 'Chương trình dữ liệu huấn luyện';

  @override
  String get getOmiUnlimitedFree => 'Nhận Omi Unlimited miễn phí bằng cách đóng góp dữ liệu của bạn để huấn luyện các mô hình AI.';

  @override
  String get trainingDataBullets => '• Dữ liệu của bạn giúp cải thiện các mô hình AI\n• Chỉ chia sẻ dữ liệu không nhạy cảm\n• Quy trình hoàn toàn minh bạch';

  @override
  String get learnMoreAtOmiTraining => 'Tìm hiểu thêm tại omi.me/training';

  @override
  String get agreeToContributeData => 'Tôi hiểu và đồng ý đóng góp dữ liệu của mình để huấn luyện AI';

  @override
  String get submitRequest => 'Gửi yêu cầu';

  @override
  String get thankYouRequestUnderReview => 'Cảm ơn bạn! Yêu cầu của bạn đang được xem xét. Chúng tôi sẽ thông báo cho bạn sau khi được phê duyệt.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'Gói của bạn sẽ vẫn hoạt động cho đến $date. Sau đó, bạn sẽ mất quyền truy cập vào các tính năng không giới hạn. Bạn có chắc không?';
  }

  @override
  String get confirmCancellation => 'Xác nhận hủy';

  @override
  String get keepMyPlan => 'Giữ gói của tôi';

  @override
  String get subscriptionSetToCancel => 'Đăng ký của bạn được đặt để hủy vào cuối kỳ.';

  @override
  String get switchedToOnDevice => 'Đã chuyển sang phiên âm trên thiết bị';

  @override
  String get couldNotSwitchToFreePlan => 'Không thể chuyển sang gói miễn phí. Vui lòng thử lại.';

  @override
  String get couldNotLoadPlans => 'Không thể tải các gói có sẵn. Vui lòng thử lại.';

  @override
  String get selectedPlanNotAvailable => 'Gói đã chọn không khả dụng. Vui lòng thử lại.';

  @override
  String get upgradeToAnnualPlan => 'Nâng cấp lên gói năm';

  @override
  String get importantBillingInfo => 'Thông tin thanh toán quan trọng:';

  @override
  String get monthlyPlanContinues => 'Gói hàng tháng hiện tại của bạn sẽ tiếp tục cho đến cuối kỳ thanh toán';

  @override
  String get paymentMethodCharged => 'Phương thức thanh toán hiện tại của bạn sẽ được tính phí tự động khi gói hàng tháng kết thúc';

  @override
  String get annualSubscriptionStarts => 'Đăng ký năm 12 tháng của bạn sẽ tự động bắt đầu sau khi thanh toán';

  @override
  String get thirteenMonthsCoverage => 'Bạn sẽ nhận được tổng cộng 13 tháng bảo hiểm (tháng hiện tại + 12 tháng hàng năm)';

  @override
  String get confirmUpgrade => 'Xác nhận nâng cấp';

  @override
  String get confirmPlanChange => 'Xác nhận thay đổi gói';

  @override
  String get confirmAndProceed => 'Xác nhận và tiếp tục';

  @override
  String get upgradeScheduled => 'Đã lên lịch nâng cấp';

  @override
  String get changePlan => 'Thay đổi gói';

  @override
  String get upgradeAlreadyScheduled => 'Việc nâng cấp của bạn lên gói năm đã được lên lịch';

  @override
  String get youAreOnUnlimitedPlan => 'Bạn đang sử dụng gói Unlimited.';

  @override
  String get yourOmiUnleashed => 'Omi của bạn, được giải phóng. Trở nên unlimited cho khả năng vô tận.';

  @override
  String planEndedOn(String date) {
    return 'Gói của bạn đã kết thúc vào $date.\\nĐăng ký lại ngay - bạn sẽ bị tính phí ngay lập tức cho kỳ thanh toán mới.';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'Gói của bạn được đặt để hủy vào $date.\\nĐăng ký lại ngay để giữ quyền lợi - không tính phí cho đến $date.';
  }

  @override
  String get annualPlanStartsAutomatically => 'Gói năm của bạn sẽ tự động bắt đầu khi gói tháng kết thúc.';

  @override
  String planRenewsOn(String date) {
    return 'Gói của bạn được gia hạn vào $date.';
  }

  @override
  String get unlimitedConversations => 'Cuộc trò chuyện không giới hạn';

  @override
  String get askOmiAnything => 'Hỏi Omi bất cứ điều gì về cuộc sống của bạn';

  @override
  String get unlockOmiInfiniteMemory => 'Mở khóa bộ nhớ vô hạn của Omi';

  @override
  String get youreOnAnnualPlan => 'Bạn đang sử dụng gói năm';

  @override
  String get alreadyBestValuePlan => 'Bạn đã có gói giá trị tốt nhất rồi. Không cần thay đổi.';

  @override
  String get unableToLoadPlans => 'Không thể tải các gói';

  @override
  String get checkConnectionTryAgain => 'Vui lòng kiểm tra kết nối và thử lại';

  @override
  String get useFreePlan => 'Sử dụng gói miễn phí';

  @override
  String get continueText => 'Tiếp tục';

  @override
  String get resubscribe => 'Đăng ký lại';

  @override
  String get couldNotOpenPaymentSettings => 'Không thể mở cài đặt thanh toán. Vui lòng thử lại.';

  @override
  String get managePaymentMethod => 'Quản lý phương thức thanh toán';

  @override
  String get cancelSubscription => 'Hủy đăng ký';

  @override
  String endsOnDate(String date) {
    return 'Kết thúc vào $date';
  }

  @override
  String get active => 'Đang hoạt động';

  @override
  String get freePlan => 'Gói miễn phí';

  @override
  String get configure => 'Cấu hình';

  @override
  String get privacyInformation => 'Thông tin quyền riêng tư';

  @override
  String get yourPrivacyMattersToUs => 'Quyền riêng tư của bạn quan trọng với chúng tôi';

  @override
  String get privacyIntroText => 'Tại Omi, chúng tôi rất coi trọng quyền riêng tư của bạn. Chúng tôi muốn minh bạch về dữ liệu thu thập và cách sử dụng. Đây là những gì bạn cần biết:';

  @override
  String get whatWeTrack => 'Chúng tôi theo dõi gì';

  @override
  String get anonymityAndPrivacy => 'Ẩn danh và quyền riêng tư';

  @override
  String get optInAndOptOutOptions => 'Tùy chọn đồng ý và từ chối';

  @override
  String get ourCommitment => 'Cam kết của chúng tôi';

  @override
  String get commitmentText => 'Chúng tôi cam kết sử dụng dữ liệu thu thập chỉ để làm cho Omi trở thành sản phẩm tốt hơn cho bạn. Quyền riêng tư và sự tin tưởng của bạn là điều quan trọng nhất đối với chúng tôi.';

  @override
  String get thankYouText => 'Cảm ơn bạn đã là người dùng quý giá của Omi. Nếu bạn có bất kỳ câu hỏi hoặc lo ngại nào, hãy liên hệ với chúng tôi tại team@basedhardware.com.';

  @override
  String get wifiSyncSettings => 'Cài đặt đồng bộ WiFi';

  @override
  String get enterHotspotCredentials => 'Nhập thông tin đăng nhập điểm phát sóng điện thoại';

  @override
  String get wifiSyncUsesHotspot => 'Đồng bộ WiFi sử dụng điện thoại của bạn làm điểm phát sóng. Tìm tên và mật khẩu trong Cài đặt > Điểm truy cập cá nhân.';

  @override
  String get hotspotNameSsid => 'Tên điểm phát sóng (SSID)';

  @override
  String get exampleIphoneHotspot => 'vd: iPhone Hotspot';

  @override
  String get password => 'Mật khẩu';

  @override
  String get enterHotspotPassword => 'Nhập mật khẩu điểm phát sóng';

  @override
  String get saveCredentials => 'Lưu thông tin đăng nhập';

  @override
  String get clearCredentials => 'Xóa thông tin đăng nhập';

  @override
  String get pleaseEnterHotspotName => 'Vui lòng nhập tên điểm phát sóng';

  @override
  String get wifiCredentialsSaved => 'Đã lưu thông tin WiFi';

  @override
  String get wifiCredentialsCleared => 'Đã xóa thông tin WiFi';

  @override
  String summaryGeneratedForDate(String date) {
    return 'Đã tạo tóm tắt cho $date';
  }

  @override
  String get failedToGenerateSummaryCheckConversations => 'Không thể tạo tóm tắt. Hãy đảm bảo bạn có cuộc trò chuyện cho ngày đó.';

  @override
  String get summaryNotFound => 'Không tìm thấy tóm tắt';

  @override
  String get yourDaysJourney => 'Hành trình trong ngày';

  @override
  String get highlights => 'Điểm nổi bật';

  @override
  String get unresolvedQuestions => 'Câu hỏi chưa giải quyết';

  @override
  String get decisions => 'Quyết định';

  @override
  String get learnings => 'Bài học';

  @override
  String get autoDeletesAfterThreeDays => 'Tự động xóa sau 3 ngày.';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'Đã xóa Biểu đồ tri thức thành công';

  @override
  String get exportStartedMayTakeFewSeconds => 'Đã bắt đầu xuất. Quá trình này có thể mất vài giây...';

  @override
  String get knowledgeGraphDeleteDescription => 'Thao tác này sẽ xóa tất cả dữ liệu biểu đồ tri thức phái sinh (các nút và kết nối). Ký ức gốc của bạn sẽ vẫn an toàn. Biểu đồ sẽ được xây dựng lại theo thời gian hoặc khi có yêu cầu tiếp theo.';

  @override
  String get configureDailySummaryDigest => 'Cấu hình bản tóm tắt công việc hàng ngày của bạn';

  @override
  String accessesDataTypes(String dataTypes) {
    return 'Truy cập $dataTypes';
  }

  @override
  String triggeredByType(String triggerType) {
    return 'được kích hoạt bởi $triggerType';
  }

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription và $triggerDescription.';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return '$triggerDescription.';
  }

  @override
  String get noSpecificDataAccessConfigured => 'Không có quyền truy cập dữ liệu cụ thể nào được cấu hình.';

  @override
  String get basicPlanDescription => '1.200 phút cao cấp + không giới hạn trên thiết bị';

  @override
  String get minutes => 'phút';

  @override
  String get omiHas => 'Omi có:';

  @override
  String get premiumMinutesUsed => 'Đã sử dụng phút cao cấp.';

  @override
  String get setupOnDevice => 'Thiết lập trên thiết bị';

  @override
  String get forUnlimitedFreeTranscription => 'để phiên âm miễn phí không giới hạn.';

  @override
  String premiumMinsLeft(int count) {
    return 'Còn $count phút cao cấp.';
  }

  @override
  String get alwaysAvailable => 'luôn có sẵn.';

  @override
  String get importHistory => 'Lịch sử nhập';

  @override
  String get noImportsYet => 'Chưa có lần nhập nào';

  @override
  String get selectZipFileToImport => 'Chọn tệp .zip để nhập!';

  @override
  String get otherDevicesComingSoon => 'Các thiết bị khác sắp ra mắt';

  @override
  String get deleteAllLimitlessConversations => 'Xóa tất cả cuộc hội thoại Limitless?';

  @override
  String get deleteAllLimitlessWarning => 'Điều này sẽ xóa vĩnh viễn tất cả các cuộc hội thoại được nhập từ Limitless. Hành động này không thể hoàn tác.';

  @override
  String deletedLimitlessConversations(int count) {
    return 'Đã xóa $count cuộc hội thoại Limitless';
  }

  @override
  String get failedToDeleteConversations => 'Không thể xóa cuộc hội thoại';

  @override
  String get deleteImportedData => 'Xóa dữ liệu đã nhập';

  @override
  String get statusPending => 'Đang chờ';

  @override
  String get statusProcessing => 'Đang xử lý';

  @override
  String get statusCompleted => 'Hoàn thành';

  @override
  String get statusFailed => 'Thất bại';

  @override
  String nConversations(int count) {
    return '$count cuộc hội thoại';
  }

  @override
  String get pleaseEnterName => 'Vui lòng nhập tên';

  @override
  String get nameMustBeBetweenCharacters => 'Tên phải từ 2 đến 40 ký tự';

  @override
  String get deleteSampleQuestion => 'Xóa mẫu?';

  @override
  String deleteSampleConfirmation(String name) {
    return 'Bạn có chắc chắn muốn xóa mẫu của $name?';
  }

  @override
  String get confirmDeletion => 'Xác nhận xóa';

  @override
  String deletePersonConfirmation(String name) {
    return 'Bạn có chắc chắn muốn xóa $name? Điều này cũng sẽ xóa tất cả các mẫu giọng nói liên quan.';
  }

  @override
  String get howItWorksTitle => 'Nó hoạt động như thế nào?';

  @override
  String get howPeopleWorks => 'Sau khi tạo một người, bạn có thể đi đến bản ghi cuộc trò chuyện và gán các phân đoạn tương ứng cho họ, bằng cách đó Omi cũng sẽ có thể nhận dạng giọng nói của họ!';

  @override
  String get tapToDelete => 'Nhấn để xóa';

  @override
  String get newTag => 'MỚI';

  @override
  String get needHelpChatWithUs => 'Cần trợ giúp? Trò chuyện với chúng tôi';

  @override
  String get localStorageEnabled => 'Đã bật bộ nhớ cục bộ';

  @override
  String get localStorageDisabled => 'Đã tắt bộ nhớ cục bộ';

  @override
  String failedToUpdateSettings(String error) {
    return 'Không thể cập nhật cài đặt: $error';
  }

  @override
  String get privacyNotice => 'Thông báo quyền riêng tư';

  @override
  String get recordingsMayCaptureOthers => 'Bản ghi có thể ghi lại giọng nói của người khác. Đảm bảo bạn có sự đồng ý của tất cả người tham gia trước khi bật.';

  @override
  String get enable => 'Bật';

  @override
  String get storeAudioOnPhone => 'Lưu âm thanh trên điện thoại';

  @override
  String get on => 'Bật';

  @override
  String get storeAudioDescription => 'Lưu trữ tất cả bản ghi âm trên điện thoại của bạn. Khi tắt, chỉ các tải lên thất bại được giữ lại để tiết kiệm dung lượng.';

  @override
  String get enableLocalStorage => 'Bật bộ nhớ cục bộ';

  @override
  String get cloudStorageEnabled => 'Đã bật bộ nhớ đám mây';

  @override
  String get cloudStorageDisabled => 'Đã tắt bộ nhớ đám mây';

  @override
  String get enableCloudStorage => 'Bật bộ nhớ đám mây';

  @override
  String get storeAudioOnCloud => 'Lưu âm thanh trên đám mây';

  @override
  String get cloudStorageDialogMessage => 'Bản ghi thời gian thực của bạn sẽ được lưu trữ trong bộ nhớ đám mây riêng khi bạn nói.';

  @override
  String get storeAudioCloudDescription => 'Lưu trữ bản ghi thời gian thực của bạn trong bộ nhớ đám mây riêng khi bạn nói. Âm thanh được ghi lại và lưu an toàn theo thời gian thực.';

  @override
  String get downloadingFirmware => 'Đang tải Firmware';

  @override
  String get installingFirmware => 'Đang cài đặt Firmware';

  @override
  String get firmwareUpdateWarning => 'Không đóng ứng dụng hoặc tắt thiết bị. Điều này có thể làm hỏng thiết bị của bạn.';

  @override
  String get firmwareUpdated => 'Đã cập nhật Firmware';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'Vui lòng khởi động lại $deviceName của bạn để hoàn tất cập nhật.';
  }

  @override
  String get yourDeviceIsUpToDate => 'Thiết bị của bạn đã được cập nhật';

  @override
  String get currentVersion => 'Phiên bản hiện tại';

  @override
  String get latestVersion => 'Phiên bản mới nhất';

  @override
  String get whatsNew => 'Có gì mới';

  @override
  String get installUpdate => 'Cài đặt bản cập nhật';

  @override
  String get updateNow => 'Cập nhật ngay';

  @override
  String get updateGuide => 'Hướng dẫn cập nhật';

  @override
  String get checkingForUpdates => 'Đang kiểm tra cập nhật';

  @override
  String get checkingFirmwareVersion => 'Đang kiểm tra phiên bản firmware...';

  @override
  String get firmwareUpdate => 'Cập nhật Firmware';

  @override
  String get payments => 'Thanh toán';

  @override
  String get connectPaymentMethodInfo => 'Kết nối phương thức thanh toán bên dưới để bắt đầu nhận thanh toán cho ứng dụng của bạn.';

  @override
  String get selectedPaymentMethod => 'Phương thức thanh toán đã chọn';

  @override
  String get availablePaymentMethods => 'Phương thức thanh toán có sẵn';

  @override
  String get activeStatus => 'Đang hoạt động';

  @override
  String get connectedStatus => 'Đã kết nối';

  @override
  String get notConnectedStatus => 'Chưa kết nối';

  @override
  String get setActive => 'Đặt làm hoạt động';
}
