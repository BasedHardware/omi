// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Thai (`th`).
class AppLocalizationsTh extends AppLocalizations {
  AppLocalizationsTh([String locale = 'th']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'บทสนทนา';

  @override
  String get transcriptTab => 'บันทึกเสียง';

  @override
  String get actionItemsTab => 'รายการสิ่งที่ต้องทำ';

  @override
  String get deleteConversationTitle => 'ลบบทสนทนา?';

  @override
  String get deleteConversationMessage =>
      'การดำเนินการนี้จะลบความทรงจำ งาน และไฟล์เสียงที่เกี่ยวข้องด้วย การดำเนินการนี้ไม่สามารถย้อนกลับได้';

  @override
  String get confirm => 'ยืนยัน';

  @override
  String get cancel => 'ยกเลิก';

  @override
  String get ok => 'ตกลง';

  @override
  String get delete => 'ลบ';

  @override
  String get add => 'เพิ่ม';

  @override
  String get update => 'อัปเดต';

  @override
  String get save => 'บันทึก';

  @override
  String get edit => 'แก้ไข';

  @override
  String get close => 'ปิด';

  @override
  String get clear => 'ล้าง';

  @override
  String get copyTranscript => 'คัดลอกบทถอดความ';

  @override
  String get copySummary => 'คัดลอกสรุป';

  @override
  String get testPrompt => 'ทดสอบคำสั่ง';

  @override
  String get reprocessConversation => 'ประมวลผลบทสนทนาใหม่';

  @override
  String get deleteConversation => 'ลบการสนทนา';

  @override
  String get contentCopied => 'คัดลอกเนื้อหาไปยังคลิปบอร์ดแล้ว';

  @override
  String get failedToUpdateStarred => 'ไม่สามารถอัปเดตสถานะการติดดาวได้';

  @override
  String get conversationUrlNotShared => 'ไม่สามารถแชร์ URL บทสนทนาได้';

  @override
  String get errorProcessingConversation => 'เกิดข้อผิดพลาดขณะประมวลผลบทสนทนา กรุณาลองใหม่ภายหลัง';

  @override
  String get noInternetConnection => 'ไม่มีการเชื่อมต่ออินเทอร์เน็ต';

  @override
  String get unableToDeleteConversation => 'ไม่สามารถลบบทสนทนาได้';

  @override
  String get somethingWentWrong => 'เกิดข้อผิดพลาดบางอย่าง! กรุณาลองใหม่ภายหลัง';

  @override
  String get copyErrorMessage => 'คัดลอกข้อความแสดงข้อผิดพลาด';

  @override
  String get errorCopied => 'คัดลอกข้อความแสดงข้อผิดพลาดไปยังคลิปบอร์ดแล้ว';

  @override
  String get remaining => 'เหลืออยู่';

  @override
  String get loading => 'กำลังโหลด...';

  @override
  String get loadingDuration => 'กำลังโหลดระยะเวลา...';

  @override
  String secondsCount(int count) {
    return '$count วินาที';
  }

  @override
  String get people => 'บุคคล';

  @override
  String get addNewPerson => 'เพิ่มบุคคลใหม่';

  @override
  String get editPerson => 'แก้ไขบุคคล';

  @override
  String get createPersonHint => 'สร้างบุคคลใหม่และฝึก Omi ให้รู้จักเสียงพูดของพวกเขาด้วย!';

  @override
  String get speechProfile => 'โปรไฟล์การพูด';

  @override
  String sampleNumber(int number) {
    return 'ตัวอย่างที่ $number';
  }

  @override
  String get settings => 'การตั้งค่า';

  @override
  String get language => 'ภาษา';

  @override
  String get selectLanguage => 'เลือกภาษา';

  @override
  String get deleting => 'กำลังลบ...';

  @override
  String get pleaseCompleteAuthentication => 'กรุณายืนยันตัวตนในเบราว์เซอร์ของคุณ เมื่อเสร็จแล้วกลับมาที่แอป';

  @override
  String get failedToStartAuthentication => 'ไม่สามารถเริ่มการยืนยันตัวตนได้';

  @override
  String get importStarted => 'เริ่มการนำเข้าแล้ว! คุณจะได้รับการแจ้งเตือนเมื่อเสร็จสิ้น';

  @override
  String get failedToStartImport => 'ไม่สามารถเริ่มการนำเข้าได้ กรุณาลองใหม่อีกครั้ง';

  @override
  String get couldNotAccessFile => 'ไม่สามารถเข้าถึงไฟล์ที่เลือกได้';

  @override
  String get askOmi => 'ถาม Omi';

  @override
  String get done => 'เสร็จสิ้น';

  @override
  String get disconnected => 'ตัดการเชื่อมต่อ';

  @override
  String get searching => 'กำลังค้นหา...';

  @override
  String get connectDevice => 'เชื่อมต่ออุปกรณ์';

  @override
  String get monthlyLimitReached => 'คุณถึงขีดจำกัดรายเดือนแล้ว';

  @override
  String get checkUsage => 'ตรวจสอบการใช้งาน';

  @override
  String get syncingRecordings => 'กำลังซิงค์การบันทึก';

  @override
  String get recordingsToSync => 'การบันทึกที่ต้องซิงค์';

  @override
  String get allCaughtUp => 'ทำทุกอย่างเรียบร้อยแล้ว';

  @override
  String get sync => 'ซิงค์';

  @override
  String get pendantUpToDate => 'จี้อัปเดตแล้ว';

  @override
  String get allRecordingsSynced => 'ซิงค์การบันทึกทั้งหมดแล้ว';

  @override
  String get syncingInProgress => 'กำลังดำเนินการซิงค์';

  @override
  String get readyToSync => 'พร้อมซิงค์';

  @override
  String get tapSyncToStart => 'แตะซิงค์เพื่อเริ่มต้น';

  @override
  String get pendantNotConnected => 'ไม่ได้เชื่อมต่อจี้ เชื่อมต่อเพื่อซิงค์';

  @override
  String get everythingSynced => 'ซิงค์ทุกอย่างเรียบร้อยแล้ว';

  @override
  String get recordingsNotSynced => 'คุณมีการบันทึกที่ยังไม่ได้ซิงค์';

  @override
  String get syncingBackground => 'เราจะซิงค์การบันทึกของคุณต่อในเบื้องหลัง';

  @override
  String get noConversationsYet => 'ยังไม่มีการสนทนา';

  @override
  String get noStarredConversations => 'ไม่มีการสนทนาที่ติดดาว';

  @override
  String get starConversationHint => 'หากต้องการติดดาวบทสนทนา ให้เปิดและแตะไอคอนดาวในส่วนหัว';

  @override
  String get searchConversations => 'ค้นหาการสนทนา...';

  @override
  String selectedCount(int count, Object s) {
    return 'เลือก $count รายการ';
  }

  @override
  String get merge => 'รวม';

  @override
  String get mergeConversations => 'รวมบทสนทนา';

  @override
  String mergeConversationsMessage(int count) {
    return 'นี่จะรวม $count บทสนทนาเป็นหนึ่งเดียว เนื้อหาทั้งหมดจะถูกรวมและสร้างใหม่';
  }

  @override
  String get mergingInBackground => 'กำลังรวมในเบื้องหลัง อาจใช้เวลาสักครู่';

  @override
  String get failedToStartMerge => 'ไม่สามารถเริ่มการรวมได้';

  @override
  String get askAnything => 'ถามอะไรก็ได้';

  @override
  String get noMessagesYet => 'ยังไม่มีข้อความ!\nลองเริ่มบทสนทนาสิ';

  @override
  String get deletingMessages => 'กำลังลบข้อความของคุณจากหน่วยความจำของ Omi...';

  @override
  String get messageCopied => '✨ คัดลอกข้อความไปยังคลิปบอร์ดแล้ว';

  @override
  String get cannotReportOwnMessage => 'คุณไม่สามารถรายงานข้อความของตัวเองได้';

  @override
  String get reportMessage => 'รายงานข้อความ';

  @override
  String get reportMessageConfirm => 'คุณแน่ใจหรือไม่ว่าต้องการรายงานข้อความนี้?';

  @override
  String get messageReported => 'รายงานข้อความสำเร็จแล้ว';

  @override
  String get thankYouFeedback => 'ขอบคุณสำหรับคำติชมของคุณ!';

  @override
  String get clearChat => 'ล้างแชท';

  @override
  String get clearChatConfirm => 'คุณแน่ใจหรือไม่ว่าต้องการล้างแชท? การดำเนินการนี้ไม่สามารถยกเลิกได้';

  @override
  String get maxFilesLimit => 'คุณสามารถอัปโหลดได้เพียง 4 ไฟล์ในคราวเดียว';

  @override
  String get chatWithOmi => 'แชทกับ Omi';

  @override
  String get apps => 'แอป';

  @override
  String get noAppsFound => 'ไม่พบแอป';

  @override
  String get tryAdjustingSearch => 'ลองปรับการค้นหาหรือตัวกรองของคุณ';

  @override
  String get createYourOwnApp => 'สร้างแอปของคุณเอง';

  @override
  String get buildAndShareApp => 'สร้างและแชร์แอปที่คุณกำหนดเอง';

  @override
  String get searchApps => 'ค้นหาแอป...';

  @override
  String get myApps => 'แอปของฉัน';

  @override
  String get installedApps => 'แอปที่ติดตั้งแล้ว';

  @override
  String get unableToFetchApps =>
      'ไม่สามารถดึงข้อมูลแอปได้ :(\n\nกรุณาตรวจสอบการเชื่อมต่ออินเทอร์เน็ตของคุณและลองใหม่อีกครั้ง';

  @override
  String get aboutOmi => 'เกี่ยวกับ Omi';

  @override
  String get privacyPolicy => 'นโยบายความเป็นส่วนตัว';

  @override
  String get visitWebsite => 'เยี่ยมชมเว็บไซต์';

  @override
  String get helpOrInquiries => 'ช่วยเหลือหรือสอบถาม?';

  @override
  String get joinCommunity => 'เข้าร่วมชุมชน!';

  @override
  String get membersAndCounting => '8000+ สมาชิกและนับเพิ่มขึ้นเรื่อยๆ';

  @override
  String get deleteAccountTitle => 'ลบบัญชี';

  @override
  String get deleteAccountConfirm => 'คุณแน่ใจหรือไม่ว่าต้องการลบบัญชีของคุณ?';

  @override
  String get cannotBeUndone => 'การกระทำนี้ไม่สามารถยกเลิกได้';

  @override
  String get allDataErased => 'ความทรงจำและบทสนทนาทั้งหมดของคุณจะถูกลบอย่างถาวร';

  @override
  String get appsDisconnected => 'แอปและการเชื่อมต่อของคุณจะถูกตัดการเชื่อมต่อทันที';

  @override
  String get exportBeforeDelete => 'คุณสามารถส่งออกข้อมูลของคุณก่อนลบบัญชี แต่เมื่อลบแล้วจะไม่สามารถกู้คืนได้';

  @override
  String get deleteAccountCheckbox =>
      'ฉันเข้าใจว่าการลบบัญชีของฉันเป็นการถาวรและข้อมูลทั้งหมด รวมถึงความทรงจำและบทสนทนา จะสูญหายและไม่สามารถกู้คืนได้';

  @override
  String get areYouSure => 'คุณแน่ใจหรือไม่?';

  @override
  String get deleteAccountFinal =>
      'การดำเนินการนี้ไม่สามารถย้อนกลับได้และจะลบบัญชีของคุณและข้อมูลที่เกี่ยวข้องทั้งหมดอย่างถาวร คุณแน่ใจหรือไม่ว่าต้องการดำเนินการต่อ?';

  @override
  String get deleteNow => 'ลบเลย';

  @override
  String get goBack => 'กลับ';

  @override
  String get checkBoxToConfirm =>
      'กาเครื่องหมายในช่องเพื่อยืนยันว่าคุณเข้าใจว่าการลบบัญชีของคุณเป็นการถาวรและไม่สามารถย้อนกลับได้';

  @override
  String get profile => 'โปรไฟล์';

  @override
  String get name => 'ชื่อ';

  @override
  String get email => 'อีเมล';

  @override
  String get customVocabulary => 'คำศัพท์ที่กำหนดเอง';

  @override
  String get identifyingOthers => 'การระบุบุคคลอื่น';

  @override
  String get paymentMethods => 'วิธีการชำระเงิน';

  @override
  String get conversationDisplay => 'การแสดงการสนทนา';

  @override
  String get dataPrivacy => 'ความเป็นส่วนตัวของข้อมูล';

  @override
  String get userId => 'ID ผู้ใช้';

  @override
  String get notSet => 'ไม่ได้ตั้งค่า';

  @override
  String get userIdCopied => 'คัดลอกรหัสผู้ใช้ไปยังคลิปบอร์ดแล้ว';

  @override
  String get systemDefault => 'ค่าเริ่มต้นของระบบ';

  @override
  String get planAndUsage => 'แผนและการใช้งาน';

  @override
  String get offlineSync => 'ซิงค์ออฟไลน์';

  @override
  String get deviceSettings => 'การตั้งค่าอุปกรณ์';

  @override
  String get integrations => 'การเชื่อมต่อ';

  @override
  String get feedbackBug => 'คำติชม / รายงานข้อผิดพลาด';

  @override
  String get helpCenter => 'ศูนย์ช่วยเหลือ';

  @override
  String get developerSettings => 'การตั้งค่านักพัฒนา';

  @override
  String get getOmiForMac => 'ดาวน์โหลด Omi สำหรับ Mac';

  @override
  String get referralProgram => 'โปรแกรมแนะนำเพื่อน';

  @override
  String get signOut => 'ออกจากระบบ';

  @override
  String get appAndDeviceCopied => 'คัดลอกรายละเอียดแอปและอุปกรณ์แล้ว';

  @override
  String get wrapped2025 => 'สรุปปี 2025';

  @override
  String get yourPrivacyYourControl => 'ความเป็นส่วนตัวของคุณ อยู่ในการควบคุมของคุณ';

  @override
  String get privacyIntro =>
      'ที่ Omi เรามุ่งมั่นในการปกป้องความเป็นส่วนตัวของคุณ หน้านี้ช่วยให้คุณสามารถควบคุมวิธีการจัดเก็บและใช้ข้อมูลของคุณได้';

  @override
  String get learnMore => 'เรียนรู้เพิ่มเติม...';

  @override
  String get dataProtectionLevel => 'ระดับการปกป้องข้อมูล';

  @override
  String get dataProtectionDesc =>
      'ข้อมูลของคุณได้รับการรักษาความปลอดภัยโดยค่าเริ่มต้นด้วยการเข้ารหัสที่แข็งแกร่ง ตรวจสอบการตั้งค่าและตัวเลือกความเป็นส่วนตัวในอนาคตด้านล่าง';

  @override
  String get appAccess => 'การเข้าถึงแอป';

  @override
  String get appAccessDesc => 'แอปต่อไปนี้สามารถเข้าถึงข้อมูลของคุณได้ แตะที่แอปเพื่อจัดการสิทธิ์';

  @override
  String get noAppsExternalAccess => 'ไม่มีแอปที่ติดตั้งซึ่งมีการเข้าถึงข้อมูลของคุณจากภายนอก';

  @override
  String get deviceName => 'ชื่ออุปกรณ์';

  @override
  String get deviceId => 'ID อุปกรณ์';

  @override
  String get firmware => 'เฟิร์มแวร์';

  @override
  String get sdCardSync => 'ซิงค์การ์ด SD';

  @override
  String get hardwareRevision => 'เวอร์ชันฮาร์ดแวร์';

  @override
  String get modelNumber => 'หมายเลขรุ่น';

  @override
  String get manufacturer => 'ผู้ผลิต';

  @override
  String get doubleTap => 'แตะสองครั้ง';

  @override
  String get ledBrightness => 'ความสว่าง LED';

  @override
  String get micGain => 'ระดับไมโครโฟน';

  @override
  String get disconnect => 'ตัดการเชื่อมต่อ';

  @override
  String get forgetDevice => 'ลืมอุปกรณ์';

  @override
  String get chargingIssues => 'ปัญหาการชาร์จ';

  @override
  String get disconnectDevice => 'ตัดการเชื่อมต่ออุปกรณ์';

  @override
  String get unpairDevice => 'ยกเลิกการจับคู่อุปกรณ์';

  @override
  String get unpairAndForget => 'ยกเลิกการจับคู่และลืมอุปกรณ์';

  @override
  String get deviceDisconnectedMessage => 'Omi ของคุณถูกตัดการเชื่อมต่อแล้ว 😔';

  @override
  String get deviceUnpairedMessage =>
      'ยกเลิกการจับคู่อุปกรณ์แล้ว ไปที่การตั้งค่า > Bluetooth และลืมอุปกรณ์เพื่อทำการยกเลิกการจับคู่ให้เสร็จสมบูรณ์';

  @override
  String get unpairDialogTitle => 'ยกเลิกการจับคู่อุปกรณ์';

  @override
  String get unpairDialogMessage =>
      'นี่จะยกเลิกการจับคู่อุปกรณ์เพื่อให้สามารถเชื่อมต่อกับโทรศัพท์เครื่องอื่นได้ คุณจะต้องไปที่การตั้งค่า > Bluetooth และลืมอุปกรณ์เพื่อทำกระบวนการให้เสร็จสมบูรณ์';

  @override
  String get deviceNotConnected => 'ไม่ได้เชื่อมต่ออุปกรณ์';

  @override
  String get connectDeviceMessage => 'เชื่อมต่ออุปกรณ์ Omi ของคุณเพื่อเข้าถึง\nการตั้งค่าและการปรับแต่งอุปกรณ์';

  @override
  String get deviceInfoSection => 'ข้อมูลอุปกรณ์';

  @override
  String get customizationSection => 'การปรับแต่ง';

  @override
  String get hardwareSection => 'ฮาร์ดแวร์';

  @override
  String get v2Undetected => 'ไม่พบ V2';

  @override
  String get v2UndetectedMessage =>
      'เราเห็นว่าคุณมีอุปกรณ์ V1 หรืออุปกรณ์ของคุณไม่ได้เชื่อมต่อ ฟังก์ชัน SD Card จะใช้ได้เฉพาะกับอุปกรณ์ V2 เท่านั้น';

  @override
  String get endConversation => 'จบบทสนทนา';

  @override
  String get pauseResume => 'หยุดชั่วคราว/ดำเนินการต่อ';

  @override
  String get starConversation => 'ติดดาวบทสนทนา';

  @override
  String get doubleTapAction => 'การดำเนินการแตะสองครั้ง';

  @override
  String get endAndProcess => 'จบและประมวลผลบทสนทนา';

  @override
  String get pauseResumeRecording => 'หยุดชั่วคราว/ดำเนินการบันทึกต่อ';

  @override
  String get starOngoing => 'ติดดาวบทสนทนาที่กำลังดำเนินการ';

  @override
  String get off => 'ปิด';

  @override
  String get max => 'สูงสุด';

  @override
  String get mute => 'ปิดเสียง';

  @override
  String get quiet => 'เงียบ';

  @override
  String get normal => 'ปกติ';

  @override
  String get high => 'สูง';

  @override
  String get micGainDescMuted => 'ไมโครโฟนถูกปิดเสียง';

  @override
  String get micGainDescLow => 'เงียบมาก - สำหรับสภาพแวดล้อมที่เสียงดัง';

  @override
  String get micGainDescModerate => 'เงียบ - สำหรับเสียงรบกวนปานกลาง';

  @override
  String get micGainDescNeutral => 'กลางๆ - การบันทึกที่สมดุล';

  @override
  String get micGainDescSlightlyBoosted => 'เพิ่มขึ้นเล็กน้อย - การใช้งานปกติ';

  @override
  String get micGainDescBoosted => 'เพิ่มขึ้น - สำหรับสภาพแวดล้อมที่เงียบ';

  @override
  String get micGainDescHigh => 'สูง - สำหรับเสียงที่ไกลหรือเบา';

  @override
  String get micGainDescVeryHigh => 'สูงมาก - สำหรับแหล่งเสียงที่เงียบมาก';

  @override
  String get micGainDescMax => 'สูงสุด - ใช้ด้วยความระมัดระวัง';

  @override
  String get developerSettingsTitle => 'การตั้งค่านักพัฒนา';

  @override
  String get saving => 'กำลังบันทึก...';

  @override
  String get personaConfig => 'กำหนดค่าบุคลิก AI ของคุณ';

  @override
  String get beta => 'เบต้า';

  @override
  String get transcription => 'การถอดเสียง';

  @override
  String get transcriptionConfig => 'กำหนดค่าผู้ให้บริการ STT';

  @override
  String get conversationTimeout => 'หมดเวลาบทสนทนา';

  @override
  String get conversationTimeoutConfig => 'ตั้งค่าเมื่อบทสนทนาจะจบอัตโนมัติ';

  @override
  String get importData => 'นำเข้าข้อมูล';

  @override
  String get importDataConfig => 'นำเข้าข้อมูลจากแหล่งอื่น';

  @override
  String get debugDiagnostics => 'การแก้ไขจุดบกพร่องและการวินิจฉัย';

  @override
  String get endpointUrl => 'URL ปลายทาง';

  @override
  String get noApiKeys => 'ยังไม่มีคีย์ API';

  @override
  String get createKeyToStart => 'สร้างคีย์เพื่อเริ่มต้น';

  @override
  String get createKey => 'สร้างคีย์';

  @override
  String get docs => 'เอกสาร';

  @override
  String get yourOmiInsights => 'ข้อมูลเชิงลึก Omi ของคุณ';

  @override
  String get today => 'วันนี้';

  @override
  String get thisMonth => 'เดือนนี้';

  @override
  String get thisYear => 'ปีนี้';

  @override
  String get allTime => 'ตลอดเวลา';

  @override
  String get noActivityYet => 'ยังไม่มีกิจกรรม';

  @override
  String get startConversationToSeeInsights => 'เริ่มบทสนทนากับ Omi\nเพื่อดูข้อมูลเชิงลึกการใช้งานของคุณที่นี่';

  @override
  String get listening => 'การฟัง';

  @override
  String get listeningSubtitle => 'เวลารวมที่ Omi ฟังอย่างกระตือรือร้น';

  @override
  String get understanding => 'การเข้าใจ';

  @override
  String get understandingSubtitle => 'คำที่เข้าใจจากบทสนทนาของคุณ';

  @override
  String get providing => 'การให้บริการ';

  @override
  String get providingSubtitle => 'รายการสิ่งที่ต้องทำและบันทึกที่จับได้โดยอัตโนมัติ';

  @override
  String get remembering => 'การจดจำ';

  @override
  String get rememberingSubtitle => 'ข้อเท็จจริงและรายละเอียดที่จำไว้ให้คุณ';

  @override
  String get unlimitedPlan => 'แผนไม่จำกัด';

  @override
  String get managePlan => 'จัดการแผน';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'แผนของคุณจะยกเลิกในวันที่ $date';
  }

  @override
  String renewsOn(String date) {
    return 'แผนของคุณจะต่ออายุในวันที่ $date';
  }

  @override
  String get basicPlan => 'แผนฟรี';

  @override
  String usageLimitMessage(String used, int limit) {
    return 'ใช้ไป $used จาก $limit นาที';
  }

  @override
  String get upgrade => 'อัปเกรด';

  @override
  String get upgradeToUnlimited => 'อัปเกรดเป็นไม่จำกัด';

  @override
  String basicPlanDesc(int limit) {
    return 'แผนของคุณรวม $limit นาทีฟรีต่อเดือน อัปเกรดเพื่อใช้งานแบบไม่จำกัด';
  }

  @override
  String get shareStatsMessage => 'แชร์สถิติ Omi ของฉัน! (omi.me - ผู้ช่วย AI ที่เปิดอยู่ตลอดเวลา)';

  @override
  String get sharePeriodToday => 'วันนี้ omi ได้:';

  @override
  String get sharePeriodMonth => 'เดือนนี้ omi ได้:';

  @override
  String get sharePeriodYear => 'ปีนี้ omi ได้:';

  @override
  String get sharePeriodAllTime => 'จนถึงตอนนี้ omi ได้:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 ฟังเป็นเวลา $minutes นาที';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 เข้าใจ $words คำ';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ ให้ข้อมูลเชิงลึก $count รายการ';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 จำความทรงจำ $count รายการ';
  }

  @override
  String get debugLogs => 'บันทึกการแก้ไขข้อบกพร่อง';

  @override
  String get debugLogsAutoDelete => 'ลบอัตโนมัติหลังจาก 3 วัน';

  @override
  String get debugLogsDesc => 'ช่วยวินิจฉัยปัญหา';

  @override
  String get noLogFilesFound => 'ไม่พบไฟล์บันทึก';

  @override
  String get omiDebugLog => 'บันทึกการแก้ไขจุดบกพร่อง Omi';

  @override
  String get logShared => 'แชร์บันทึกแล้ว';

  @override
  String get selectLogFile => 'เลือกไฟล์บันทึก';

  @override
  String get shareLogs => 'แชร์บันทึก';

  @override
  String get debugLogCleared => 'ล้างบันทึกการแก้ไขจุดบกพร่องแล้ว';

  @override
  String get exportStarted => 'เริ่มการส่งออกแล้ว อาจใช้เวลาสักครู่...';

  @override
  String get exportAllData => 'ส่งออกข้อมูลทั้งหมด';

  @override
  String get exportDataDesc => 'ส่งออกบทสนทนาเป็นไฟล์ JSON';

  @override
  String get exportedConversations => 'บทสนทนาที่ส่งออกจาก Omi';

  @override
  String get exportShared => 'แชร์การส่งออกแล้ว';

  @override
  String get deleteKnowledgeGraphTitle => 'ลบกราฟความรู้?';

  @override
  String get deleteKnowledgeGraphMessage =>
      'นี่จะลบข้อมูลกราฟความรู้ที่สร้างขึ้นทั้งหมด (โหนดและการเชื่อมต่อ) ความทรงจำเดิมของคุณจะยังคงปลอดภัย กราฟจะถูกสร้างขึ้นใหม่เมื่อเวลาผ่านไปหรือเมื่อมีคำขอครั้งถัดไป';

  @override
  String get knowledgeGraphDeleted => 'ลบกราฟความรู้แล้ว';

  @override
  String deleteGraphFailed(String error) {
    return 'ไม่สามารถลบกราฟ: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'ลบกราฟความรู้';

  @override
  String get deleteKnowledgeGraphDesc => 'ล้างโหนดและการเชื่อมต่อทั้งหมด';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'เซิร์ฟเวอร์ MCP';

  @override
  String get mcpServerDesc => 'เชื่อมต่อผู้ช่วย AI กับข้อมูลของคุณ';

  @override
  String get serverUrl => 'URL เซิร์ฟเวอร์';

  @override
  String get urlCopied => 'คัดลอก URL แล้ว';

  @override
  String get apiKeyAuth => 'การยืนยันตัวตนด้วยคีย์ API';

  @override
  String get header => 'ส่วนหัว';

  @override
  String get authorizationBearer => 'Authorization: Bearer <key>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'Client ID';

  @override
  String get clientSecret => 'Client Secret';

  @override
  String get useMcpApiKey => 'ใช้คีย์ API MCP ของคุณ';

  @override
  String get webhooks => 'เว็บฮุก';

  @override
  String get conversationEvents => 'เหตุการณ์การสนทนา';

  @override
  String get newConversationCreated => 'สร้างบทสนทนาใหม่แล้ว';

  @override
  String get realtimeTranscript => 'ถอดความแบบเรียลไทม์';

  @override
  String get transcriptReceived => 'ได้รับบันทึกเสียงแล้ว';

  @override
  String get audioBytes => 'ไบต์เสียง';

  @override
  String get audioDataReceived => 'ได้รับข้อมูลเสียงแล้ว';

  @override
  String get intervalSeconds => 'ช่วงเวลา (วินาที)';

  @override
  String get daySummary => 'สรุปรายวัน';

  @override
  String get summaryGenerated => 'สร้างสรุปแล้ว';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'เพิ่มไปยัง claude_desktop_config.json';

  @override
  String get copyConfig => 'คัดลอกการกำหนดค่า';

  @override
  String get configCopied => 'คัดลอกการกำหนดค่าไปยังคลิปบอร์ดแล้ว';

  @override
  String get listeningMins => 'การฟัง (นาที)';

  @override
  String get understandingWords => 'การเข้าใจ (คำ)';

  @override
  String get insights => 'ข้อมูลเชิงลึก';

  @override
  String get memories => 'ความทรงจำ';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return 'ใช้ไป $used จาก $limit นาทีในเดือนนี้';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return 'ใช้ไป $used จาก $limit คำในเดือนนี้';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return 'ได้รับข้อมูลเชิงลึก $used จาก $limit รายการในเดือนนี้';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return 'สร้างความทรงจำ $used จาก $limit รายการในเดือนนี้';
  }

  @override
  String get visibility => 'การมองเห็น';

  @override
  String get visibilitySubtitle => 'ควบคุมว่าบทสนทนาใดจะปรากฏในรายการของคุณ';

  @override
  String get showShortConversations => 'แสดงบทสนทนาสั้น';

  @override
  String get showShortConversationsDesc => 'แสดงบทสนทนาที่สั้นกว่าเกณฑ์';

  @override
  String get showDiscardedConversations => 'แสดงบทสนทนาที่ถูกทิ้ง';

  @override
  String get showDiscardedConversationsDesc => 'รวมบทสนทนาที่ถูกทำเครื่องหมายว่าทิ้ง';

  @override
  String get shortConversationThreshold => 'เกณฑ์บทสนทนาสั้น';

  @override
  String get shortConversationThresholdSubtitle => 'บทสนทนาที่สั้นกว่านี้จะถูกซ่อนเว้นแต่จะเปิดใช้งานด้านบน';

  @override
  String get durationThreshold => 'เกณฑ์ระยะเวลา';

  @override
  String get durationThresholdDesc => 'ซ่อนบทสนทนาที่สั้นกว่านี้';

  @override
  String minLabel(int count) {
    return '$count นาที';
  }

  @override
  String get customVocabularyTitle => 'คำศัพท์ที่กำหนดเอง';

  @override
  String get addWords => 'เพิ่มคำ';

  @override
  String get addWordsDesc => 'ชื่อ คำศัพท์ หรือคำที่ไม่ธรรมดา';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'เชื่อมต่อ';

  @override
  String get comingSoon => 'เร็วๆ นี้';

  @override
  String get integrationsFooter => 'เชื่อมต่อแอปของคุณเพื่อดูข้อมูลและตัวชี้วัดในแชท';

  @override
  String get completeAuthInBrowser => 'กรุณายืนยันตัวตนในเบราว์เซอร์ของคุณ เมื่อเสร็จแล้วกลับมาที่แอป';

  @override
  String failedToStartAuth(String appName) {
    return 'ไม่สามารถเริ่มการยืนยันตัวตน $appName ได้';
  }

  @override
  String disconnectAppTitle(String appName) {
    return 'ตัดการเชื่อมต่อ $appName?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'คุณแน่ใจหรือไม่ว่าต้องการตัดการเชื่อมต่อจาก $appName? คุณสามารถเชื่อมต่อใหม่ได้ตลอดเวลา';
  }

  @override
  String disconnectedFrom(String appName) {
    return 'ตัดการเชื่อมต่อจาก $appName แล้ว';
  }

  @override
  String get failedToDisconnect => 'ตัดการเชื่อมต่อไม่สำเร็จ';

  @override
  String connectTo(String appName) {
    return 'เชื่อมต่อกับ $appName';
  }

  @override
  String authAccessMessage(String appName) {
    return 'คุณต้องอนุญาตให้ Omi เข้าถึงข้อมูล $appName ของคุณ ระบบจะเปิดเบราว์เซอร์เพื่อยืนยันตัวตน';
  }

  @override
  String get continueAction => 'ดำเนินการต่อ';

  @override
  String get languageTitle => 'ภาษา';

  @override
  String get primaryLanguage => 'ภาษาหลัก';

  @override
  String get automaticTranslation => 'แปลภาษาอัตโนมัติ';

  @override
  String get detectLanguages => 'ตรวจจับมากกว่า 10 ภาษา';

  @override
  String get authorizeSavingRecordings => 'อนุญาตให้บันทึกการอัด';

  @override
  String get thanksForAuthorizing => 'ขอบคุณสำหรับการอนุญาต!';

  @override
  String get needYourPermission => 'เราต้องการความยินยอมจากคุณ';

  @override
  String get alreadyGavePermission => 'คุณได้อนุญาตให้เราบันทึกการอัดของคุณแล้ว นี่คือเหตุผลที่เราต้องการ:';

  @override
  String get wouldLikePermission => 'เราต้องการความยินยอมในการบันทึกเสียงของคุณ นี่คือเหตุผล:';

  @override
  String get improveSpeechProfile => 'ปรับปรุงโปรไฟล์เสียงของคุณ';

  @override
  String get improveSpeechProfileDesc => 'เราใช้การบันทึกเพื่อฝึกและปรับปรุงโปรไฟล์เสียงส่วนบุคคลของคุณ';

  @override
  String get trainFamilyProfiles => 'ฝึกโปรไฟล์สำหรับเพื่อนและครอบครัว';

  @override
  String get trainFamilyProfilesDesc => 'การบันทึกของคุณช่วยให้เราจดจำและสร้างโปรไฟล์สำหรับเพื่อนและครอบครัวของคุณ';

  @override
  String get enhanceTranscriptAccuracy => 'เพิ่มความแม่นยำของการถอดเสียง';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'เมื่อโมเดลของเราดีขึ้น เราสามารถให้ผลการถอดเสียงที่ดีขึ้นสำหรับการบันทึกของคุณ';

  @override
  String get legalNotice =>
      'ประกาศทางกฎหมาย: ความถูกต้องตามกฎหมายในการบันทึกและจัดเก็บข้อมูลเสียงอาจแตกต่างกันไปตามสถานที่และวิธีที่คุณใช้ฟีเจอร์นี้ เป็นความรับผิดชอบของคุณที่จะต้องปฏิบัติตามกฎหมายและข้อบังคับในพื้นที่';

  @override
  String get alreadyAuthorized => 'อนุญาตแล้ว';

  @override
  String get authorize => 'อนุญาต';

  @override
  String get revokeAuthorization => 'เพิกถอนการอนุญาต';

  @override
  String get authorizationSuccessful => 'อนุญาตสำเร็จ!';

  @override
  String get failedToAuthorize => 'อนุญาตไม่สำเร็จ กรุณาลองอีกครั้ง';

  @override
  String get authorizationRevoked => 'เพิกถอนการอนุญาตแล้ว';

  @override
  String get recordingsDeleted => 'ลบการบันทึกแล้ว';

  @override
  String get failedToRevoke => 'เพิกถอนการอนุญาตไม่สำเร็จ กรุณาลองอีกครั้ง';

  @override
  String get permissionRevokedTitle => 'เพิกถอนการอนุญาต';

  @override
  String get permissionRevokedMessage => 'คุณต้องการให้เราลบการบันทึกที่มีอยู่ทั้งหมดของคุณด้วยหรือไม่?';

  @override
  String get yes => 'ใช่';

  @override
  String get editName => 'แก้ไขชื่อ';

  @override
  String get howShouldOmiCallYou => 'Omi ควรเรียกคุณว่าอะไร?';

  @override
  String get enterYourName => 'ใส่ชื่อของคุณ';

  @override
  String get nameCannotBeEmpty => 'ชื่อต้องไม่ว่างเปล่า';

  @override
  String get nameUpdatedSuccessfully => 'อัปเดตชื่อสำเร็จ!';

  @override
  String get calendarSettings => 'การตั้งค่าปฏิทิน';

  @override
  String get calendarProviders => 'ผู้ให้บริการปฏิทิน';

  @override
  String get macOsCalendar => 'ปฏิทิน macOS';

  @override
  String get connectMacOsCalendar => 'เชื่อมต่อปฏิทิน macOS ในเครื่องของคุณ';

  @override
  String get googleCalendar => 'ปฏิทิน Google';

  @override
  String get syncGoogleAccount => 'ซิงค์กับบัญชี Google ของคุณ';

  @override
  String get showMeetingsMenuBar => 'แสดงการประชุมที่กำลังจะมาถึงในแถบเมนู';

  @override
  String get showMeetingsMenuBarDesc => 'แสดงการประชุมถัดไปและเวลาที่เหลือก่อนเริ่มในแถบเมนู macOS';

  @override
  String get showEventsNoParticipants => 'แสดงกิจกรรมที่ไม่มีผู้เข้าร่วม';

  @override
  String get showEventsNoParticipantsDesc =>
      'เมื่อเปิดใช้งาน Coming Up จะแสดงกิจกรรมที่ไม่มีผู้เข้าร่วมหรือลิงก์วิดีโอ';

  @override
  String get yourMeetings => 'การประชุมของคุณ';

  @override
  String get refresh => 'รีเฟรช';

  @override
  String get noUpcomingMeetings => 'ไม่มีการประชุมที่กำลังจะมาถึง';

  @override
  String get checkingNextDays => 'ตรวจสอบ 30 วันถัดไป';

  @override
  String get tomorrow => 'พรุ่งนี้';

  @override
  String get googleCalendarComingSoon => 'การผสานรวมปฏิทิน Google เร็วๆ นี้!';

  @override
  String connectedAsUser(String userId) {
    return 'เชื่อมต่อในชื่อผู้ใช้: $userId';
  }

  @override
  String get defaultWorkspace => 'พื้นที่ทำงานเริ่มต้น';

  @override
  String get tasksCreatedInWorkspace => 'งานจะถูกสร้างในพื้นที่ทำงานนี้';

  @override
  String get defaultProjectOptional => 'โปรเจกต์เริ่มต้น (ไม่บังคับ)';

  @override
  String get leaveUnselectedTasks => 'เว้นว่างไว้เพื่อสร้างงานโดยไม่มีโปรเจกต์';

  @override
  String get noProjectsInWorkspace => 'ไม่พบโปรเจกต์ในพื้นที่ทำงานนี้';

  @override
  String get conversationTimeoutDesc => 'เลือกระยะเวลาที่จะรอในความเงียบก่อนสิ้นสุดบทสนทนาอัตโนมัติ:';

  @override
  String get timeout2Minutes => '2 นาที';

  @override
  String get timeout2MinutesDesc => 'สิ้นสุดบทสนทนาหลังจากเงียบ 2 นาที';

  @override
  String get timeout5Minutes => '5 นาที';

  @override
  String get timeout5MinutesDesc => 'สิ้นสุดบทสนทนาหลังจากเงียบ 5 นาที';

  @override
  String get timeout10Minutes => '10 นาที';

  @override
  String get timeout10MinutesDesc => 'สิ้นสุดบทสนทนาหลังจากเงียบ 10 นาที';

  @override
  String get timeout30Minutes => '30 นาที';

  @override
  String get timeout30MinutesDesc => 'สิ้นสุดบทสนทนาหลังจากเงียบ 30 นาที';

  @override
  String get timeout4Hours => '4 ชั่วโมง';

  @override
  String get timeout4HoursDesc => 'สิ้นสุดบทสนทนาหลังจากเงียบ 4 ชั่วโมง';

  @override
  String get conversationEndAfterHours => 'บทสนทนาจะสิ้นสุดหลังจากเงียบ 4 ชั่วโมง';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'บทสนทนาจะสิ้นสุดหลังจากเงียบ $minutes นาที';
  }

  @override
  String get tellUsPrimaryLanguage => 'บอกเราถึงภาษาหลักของคุณ';

  @override
  String get languageForTranscription => 'ตั้งค่าภาษาของคุณเพื่อการถอดเสียงที่แม่นยำขึ้นและประสบการณ์ที่เป็นส่วนตัว';

  @override
  String get singleLanguageModeInfo => 'โหมดภาษาเดียวถูกเปิดใช้งาน การแปลภาษาถูกปิดเพื่อความแม่นยำที่สูงขึ้น';

  @override
  String get searchLanguageHint => 'ค้นหาภาษาตามชื่อหรือรหัส';

  @override
  String get noLanguagesFound => 'ไม่พบภาษา';

  @override
  String get skip => 'ข้าม';

  @override
  String languageSetTo(String language) {
    return 'ตั้งค่าภาษาเป็น $language';
  }

  @override
  String get failedToSetLanguage => 'ตั้งค่าภาษาไม่สำเร็จ';

  @override
  String appSettings(String appName) {
    return 'การตั้งค่า $appName';
  }

  @override
  String disconnectFromApp(String appName) {
    return 'ตัดการเชื่อมต่อจาก $appName?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'การดำเนินการนี้จะลบการยืนยันตัวตน $appName ของคุณ คุณจะต้องเชื่อมต่อใหม่เพื่อใช้งานอีกครั้ง';
  }

  @override
  String connectedToApp(String appName) {
    return 'เชื่อมต่อกับ $appName แล้ว';
  }

  @override
  String get account => 'บัญชี';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'รายการสิ่งที่ต้องทำของคุณจะถูกซิงค์ไปยังบัญชี $appName ของคุณ';
  }

  @override
  String get defaultSpace => 'พื้นที่เริ่มต้น';

  @override
  String get selectSpaceInWorkspace => 'เลือกพื้นที่ในพื้นที่ทำงานของคุณ';

  @override
  String get noSpacesInWorkspace => 'ไม่พบพื้นที่ในพื้นที่ทำงานนี้';

  @override
  String get defaultList => 'รายการเริ่มต้น';

  @override
  String get tasksAddedToList => 'งานจะถูกเพิ่มลงในรายการนี้';

  @override
  String get noListsInSpace => 'ไม่พบรายการในพื้นที่นี้';

  @override
  String failedToLoadRepos(String error) {
    return 'โหลดที่เก็บไม่สำเร็จ: $error';
  }

  @override
  String get defaultRepoSaved => 'บันทึกที่เก็บเริ่มต้นแล้ว';

  @override
  String get failedToSaveDefaultRepo => 'บันทึกที่เก็บเริ่มต้นไม่สำเร็จ';

  @override
  String get defaultRepository => 'ที่เก็บเริ่มต้น';

  @override
  String get selectDefaultRepoDesc =>
      'เลือกที่เก็บเริ่มต้นสำหรับสร้าง issue คุณยังสามารถระบุที่เก็บอื่นได้เมื่อสร้าง issue';

  @override
  String get noReposFound => 'ไม่พบที่เก็บ';

  @override
  String get private => 'ส่วนตัว';

  @override
  String updatedDate(String date) {
    return 'อัปเดต $date';
  }

  @override
  String get yesterday => 'เมื่อวาน';

  @override
  String daysAgo(int count) {
    return '$count วันที่แล้ว';
  }

  @override
  String get oneWeekAgo => '1 สัปดาห์ที่แล้ว';

  @override
  String weeksAgo(int count) {
    return '$count สัปดาห์ที่แล้ว';
  }

  @override
  String get oneMonthAgo => '1 เดือนที่แล้ว';

  @override
  String monthsAgo(int count) {
    return '$count เดือนที่แล้ว';
  }

  @override
  String get issuesCreatedInRepo => 'Issue จะถูกสร้างในที่เก็บเริ่มต้นของคุณ';

  @override
  String get taskIntegrations => 'การผสานรวมงาน';

  @override
  String get configureSettings => 'กำหนดการตั้งค่า';

  @override
  String get completeAuthBrowser => 'กรุณายืนยันตัวตนในเบราว์เซอร์ของคุณ เมื่อเสร็จแล้วกลับมาที่แอป';

  @override
  String failedToStartAppAuth(String appName) {
    return 'เริ่มการยืนยันตัวตน $appName ไม่สำเร็จ';
  }

  @override
  String connectToAppTitle(String appName) {
    return 'เชื่อมต่อกับ $appName';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'คุณต้องอนุญาตให้ Omi สร้างงานในบัญชี $appName ของคุณ ระบบจะเปิดเบราว์เซอร์เพื่อยืนยันตัวตน';
  }

  @override
  String get continueButton => 'ดำเนินการต่อ';

  @override
  String appIntegration(String appName) {
    return 'การผสานรวม $appName';
  }

  @override
  String integrationComingSoon(String appName) {
    return 'การผสานรวมกับ $appName เร็วๆ นี้! เรากำลังพยายามนำตัวเลือกการจัดการงานเพิ่มเติมมาให้คุณ';
  }

  @override
  String get gotIt => 'เข้าใจแล้ว';

  @override
  String get tasksExportedOneApp => 'สามารถส่งออกงานไปยังแอปหนึ่งแอปในแต่ละครั้ง';

  @override
  String get completeYourUpgrade => 'ดำเนินการอัปเกรดของคุณให้เสร็จสมบูรณ์';

  @override
  String get importConfiguration => 'นำเข้าการกำหนดค่า';

  @override
  String get exportConfiguration => 'ส่งออกการกำหนดค่า';

  @override
  String get bringYourOwn => 'นำของคุณเองมาใช้';

  @override
  String get payYourSttProvider => 'ใช้ Omi ได้อย่างอิสระ คุณจ่ายเฉพาะผู้ให้บริการ STT ของคุณโดยตรง';

  @override
  String get freeMinutesMonth => 'รวม 1,200 นาทีฟรี/เดือน ไม่จำกัดด้วย ';

  @override
  String get omiUnlimited => 'Omi Unlimited';

  @override
  String get hostRequired => 'ต้องระบุ Host';

  @override
  String get validPortRequired => 'ต้องระบุพอร์ตที่ถูกต้อง';

  @override
  String get validWebsocketUrlRequired => 'ต้องระบุ URL WebSocket ที่ถูกต้อง (wss://)';

  @override
  String get apiUrlRequired => 'ต้องระบุ API URL';

  @override
  String get apiKeyRequired => 'ต้องระบุ API key';

  @override
  String get invalidJsonConfig => 'การกำหนดค่า JSON ไม่ถูกต้อง';

  @override
  String errorSaving(String error) {
    return 'ข้อผิดพลาดในการบันทึก: $error';
  }

  @override
  String get configCopiedToClipboard => 'คัดลอกการกำหนดค่าไปยังคลิปบอร์ดแล้ว';

  @override
  String get pasteJsonConfig => 'วางการกำหนดค่า JSON ของคุณด้านล่าง:';

  @override
  String get addApiKeyAfterImport => 'คุณจะต้องเพิ่ม API key ของคุณเองหลังจากนำเข้า';

  @override
  String get paste => 'วาง';

  @override
  String get import => 'นำเข้า';

  @override
  String get invalidProviderInConfig => 'ผู้ให้บริการในการกำหนดค่าไม่ถูกต้อง';

  @override
  String importedConfig(String providerName) {
    return 'นำเข้าการกำหนดค่า $providerName แล้ว';
  }

  @override
  String invalidJson(String error) {
    return 'JSON ไม่ถูกต้อง: $error';
  }

  @override
  String get provider => 'ผู้ให้บริการ';

  @override
  String get live => 'สด';

  @override
  String get onDevice => 'บนอุปกรณ์';

  @override
  String get apiUrl => 'API URL';

  @override
  String get enterSttHttpEndpoint => 'ใส่ endpoint HTTP ของ STT ของคุณ';

  @override
  String get websocketUrl => 'URL WebSocket';

  @override
  String get enterLiveSttWebsocket => 'ใส่ endpoint WebSocket ของ STT แบบสดของคุณ';

  @override
  String get apiKey => 'คีย์ API';

  @override
  String get enterApiKey => 'ใส่ API key ของคุณ';

  @override
  String get storedLocallyNeverShared => 'จัดเก็บในเครื่อง ไม่แชร์เลย';

  @override
  String get host => 'Host';

  @override
  String get port => 'พอร์ต';

  @override
  String get advanced => 'ขั้นสูง';

  @override
  String get configuration => 'การกำหนดค่า';

  @override
  String get requestConfiguration => 'การกำหนดค่าคำขอ';

  @override
  String get responseSchema => 'โครงสร้างการตอบกลับ';

  @override
  String get modified => 'แก้ไขแล้ว';

  @override
  String get resetRequestConfig => 'รีเซ็ตการกำหนดค่าคำขอเป็นค่าเริ่มต้น';

  @override
  String get logs => 'บันทึก';

  @override
  String get logsCopied => 'คัดลอกบันทึกแล้ว';

  @override
  String get noLogsYet => 'ยังไม่มีบันทึก เริ่มบันทึกเพื่อดูกิจกรรม STT แบบกำหนดเอง';

  @override
  String deviceUsesCodec(String device, String reason) {
    return '$device ใช้ $reason จะใช้ Omi แทน';
  }

  @override
  String get omiTranscription => 'การถอดเสียง Omi';

  @override
  String get bestInClassTranscription => 'การถอดเสียงชั้นนำโดยไม่ต้องตั้งค่า';

  @override
  String get instantSpeakerLabels => 'ติดป้ายผู้พูดทันที';

  @override
  String get languageTranslation => 'แปลมากกว่า 100 ภาษา';

  @override
  String get optimizedForConversation => 'เหมาะสำหรับบทสนทนา';

  @override
  String get autoLanguageDetection => 'ตรวจจับภาษาอัตโนมัติ';

  @override
  String get highAccuracy => 'ความแม่นยำสูง';

  @override
  String get privacyFirst => 'ความเป็นส่วนตัวเป็นอันดับแรก';

  @override
  String get saveChanges => 'บันทึกการเปลี่ยนแปลง';

  @override
  String get resetToDefault => 'รีเซ็ตเป็นค่าเริ่มต้น';

  @override
  String get viewTemplate => 'ดูเทมเพลต';

  @override
  String get trySomethingLike => 'ลองอะไรแบบนี้...';

  @override
  String get tryIt => 'ลองดู';

  @override
  String get creatingPlan => 'กำลังสร้างแผน';

  @override
  String get developingLogic => 'กำลังพัฒนาตรรกะ';

  @override
  String get designingApp => 'กำลังออกแบบแอป';

  @override
  String get generatingIconStep => 'กำลังสร้างไอคอน';

  @override
  String get finalTouches => 'ตกแต่งขั้นสุดท้าย';

  @override
  String get processing => 'กำลังประมวลผล...';

  @override
  String get features => 'ฟีเจอร์';

  @override
  String get creatingYourApp => 'กำลังสร้างแอปของคุณ...';

  @override
  String get generatingIcon => 'กำลังสร้างไอคอน...';

  @override
  String get whatShouldWeMake => 'เราควรสร้างอะไร?';

  @override
  String get appName => 'App Name';

  @override
  String get description => 'คำอธิบาย';

  @override
  String get publicLabel => 'สาธารณะ';

  @override
  String get privateLabel => 'ส่วนตัว';

  @override
  String get free => 'ฟรี';

  @override
  String get perMonth => '/ เดือน';

  @override
  String get tailoredConversationSummaries => 'สรุปบทสนทนาที่ปรับแต่งได้';

  @override
  String get customChatbotPersonality => 'บุคลิกแชทบอทที่กำหนดเอง';

  @override
  String get makePublic => 'เปลี่ยนเป็นสาธารณะ';

  @override
  String get anyoneCanDiscover => 'ทุกคนสามารถค้นพบแอปของคุณได้';

  @override
  String get onlyYouCanUse => 'เฉพาะคุณเท่านั้นที่สามารถใช้แอปนี้ได้';

  @override
  String get paidApp => 'แอปแบบชำระเงิน';

  @override
  String get usersPayToUse => 'ผู้ใช้จ่ายเงินเพื่อใช้แอปของคุณ';

  @override
  String get freeForEveryone => 'ฟรีสำหรับทุกคน';

  @override
  String get perMonthLabel => '/ เดือน';

  @override
  String get creating => 'กำลังสร้าง...';

  @override
  String get createApp => 'สร้างแอป';

  @override
  String get searchingForDevices => 'กำลังค้นหาอุปกรณ์...';

  @override
  String devicesFoundNearby(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'อุปกรณ์',
      one: 'อุปกรณ์',
    );
    return 'พบ $count $_temp0 ในบริเวณใกล้เคียง';
  }

  @override
  String get pairingSuccessful => 'จับคู่สำเร็จ';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'เชื่อมต่อกับ Apple Watch ไม่สำเร็จ: $error';
  }

  @override
  String get dontShowAgain => 'ไม่ต้องแสดงอีก';

  @override
  String get iUnderstand => 'เข้าใจแล้ว';

  @override
  String get enableBluetooth => 'เปิดใช้งาน Bluetooth';

  @override
  String get bluetoothNeeded =>
      'Omi ต้องการ Bluetooth เพื่อเชื่อมต่อกับอุปกรณ์สวมใส่ของคุณ กรุณาเปิดใช้งาน Bluetooth แล้วลองอีกครั้ง';

  @override
  String get contactSupport => 'ติดต่อฝ่ายสนับสนุน?';

  @override
  String get connectLater => 'เชื่อมต่อภายหลัง';

  @override
  String get grantPermissions => 'ให้สิทธิ์';

  @override
  String get backgroundActivity => 'กิจกรรมพื้นหลัง';

  @override
  String get backgroundActivityDesc => 'ให้ Omi ทำงานในพื้นหลังเพื่อความเสถียรที่ดีขึ้น';

  @override
  String get locationAccess => 'การเข้าถึงตำแหน่ง';

  @override
  String get locationAccessDesc => 'เปิดใช้งานตำแหน่งพื้นหลังเพื่อประสบการณ์ที่สมบูรณ์';

  @override
  String get notifications => 'การแจ้งเตือน';

  @override
  String get notificationsDesc => 'เปิดใช้งานการแจ้งเตือนเพื่อรับข้อมูล';

  @override
  String get locationServiceDisabled => 'บริการตำแหน่งถูกปิด';

  @override
  String get locationServiceDisabledDesc =>
      'บริการตำแหน่งถูกปิด กรุณาไปที่ การตั้งค่า > ความเป็นส่วนตัวและความปลอดภัย > บริการตำแหน่ง แล้วเปิดใช้งาน';

  @override
  String get backgroundLocationDenied => 'การเข้าถึงตำแหน่งพื้นหลังถูกปฏิเสธ';

  @override
  String get backgroundLocationDeniedDesc => 'กรุณาไปที่การตั้งค่าอุปกรณ์และตั้งค่าสิทธิ์ตำแหน่งเป็น \"อนุญาตเสมอ\"';

  @override
  String get lovingOmi => 'ชอบ Omi ไหม?';

  @override
  String get leaveReviewIos =>
      'ช่วยเราเข้าถึงคนมากขึ้นด้วยการรีวิวใน App Store ความคิดเห็นของคุณมีความหมายมากสำหรับเรา!';

  @override
  String get leaveReviewAndroid =>
      'ช่วยเราเข้าถึงคนมากขึ้นด้วยการรีวิวใน Google Play Store ความคิดเห็นของคุณมีความหมายมากสำหรับเรา!';

  @override
  String get rateOnAppStore => 'ให้คะแนนบน App Store';

  @override
  String get rateOnGooglePlay => 'ให้คะแนนบน Google Play';

  @override
  String get maybeLater => 'อาจจะภายหลัง';

  @override
  String get speechProfileIntro => 'Omi จำเป็นต้องเรียนรู้เป้าหมายและเสียงของคุณ คุณจะสามารถแก้ไขได้ในภายหลัง';

  @override
  String get getStarted => 'เริ่มต้น';

  @override
  String get allDone => 'เสร็จแล้ว!';

  @override
  String get keepGoing => 'ทำต่อไป คุณทำได้ดีมาก';

  @override
  String get skipThisQuestion => 'ข้ามคำถามนี้';

  @override
  String get skipForNow => 'ข้ามไว้ก่อน';

  @override
  String get connectionError => 'ข้อผิดพลาดในการเชื่อมต่อ';

  @override
  String get connectionErrorDesc =>
      'เชื่อมต่อกับเซิร์ฟเวอร์ไม่สำเร็จ กรุณาตรวจสอบการเชื่อมต่ออินเทอร์เน็ตของคุณและลองอีกครั้ง';

  @override
  String get invalidRecordingMultipleSpeakers => 'ตรวจพบการบันทึกที่ไม่ถูกต้อง';

  @override
  String get multipleSpeakersDesc =>
      'ดูเหมือนว่ามีผู้พูดหลายคนในการบันทึก กรุณาตรวจสอบให้แน่ใจว่าคุณอยู่ในสถานที่เงียบและลองอีกครั้ง';

  @override
  String get tooShortDesc => 'ตรวจพบคำพูดไม่เพียงพอ กรุณาพูดมากขึ้นและลองอีกครั้ง';

  @override
  String get invalidRecordingDesc => 'กรุณาตรวจสอบให้แน่ใจว่าคุณพูดอย่างน้อย 5 วินาทีและไม่เกิน 90 วินาที';

  @override
  String get areYouThere => 'คุณยังอยู่ไหม?';

  @override
  String get noSpeechDesc => 'เราตรวจไม่พบคำพูดใดๆ กรุณาตรวจสอบให้แน่ใจว่าคุณพูดอย่างน้อย 10 วินาทีและไม่เกิน 3 นาที';

  @override
  String get connectionLost => 'การเชื่อมต่อขาดหาย';

  @override
  String get connectionLostDesc => 'การเชื่อมต่อถูกขัดจังหวะ กรุณาตรวจสอบการเชื่อมต่ออินเทอร์เน็ตของคุณและลองอีกครั้ง';

  @override
  String get tryAgain => 'ลองอีกครั้ง';

  @override
  String get connectOmiOmiGlass => 'เชื่อมต่อ Omi / OmiGlass';

  @override
  String get continueWithoutDevice => 'ดำเนินการต่อโดยไม่มีอุปกรณ์';

  @override
  String get permissionsRequired => 'ต้องการสิทธิ์';

  @override
  String get permissionsRequiredDesc =>
      'แอปนี้ต้องการสิทธิ์ Bluetooth และตำแหน่งเพื่อทำงานอย่างถูกต้อง กรุณาเปิดใช้งานในการตั้งค่า';

  @override
  String get openSettings => 'เปิดการตั้งค่า';

  @override
  String get wantDifferentName => 'ต้องการใช้ชื่ออื่นไหม?';

  @override
  String get whatsYourName => 'คุณชื่ออะไร?';

  @override
  String get speakTranscribeSummarize => 'พูด ถอดเสียง สรุป';

  @override
  String get signInWithApple => 'ลงชื่อเข้าใช้ด้วย Apple';

  @override
  String get signInWithGoogle => 'ลงชื่อเข้าใช้ด้วย Google';

  @override
  String get byContinuingAgree => 'การดำเนินการต่อแสดงว่าคุณยอมรับ ';

  @override
  String get termsOfUse => 'เงื่อนไขการใช้งาน';

  @override
  String get omiYourAiCompanion => 'Omi – เพื่อนคู่ใจ AI ของคุณ';

  @override
  String get captureEveryMoment => 'บันทึกทุกช่วงเวลา รับสรุปโดย AI\nไม่ต้องจดบันทึกอีกต่อไป';

  @override
  String get appleWatchSetup => 'ตั้งค่า Apple Watch';

  @override
  String get permissionRequestedExclaim => 'ขอสิทธิ์แล้ว!';

  @override
  String get microphonePermission => 'สิทธิ์ไมโครโฟน';

  @override
  String get permissionGrantedNow =>
      'อนุญาตสิทธิ์แล้ว! ตอนนี้:\n\nเปิดแอป Omi บนนาฬิกาของคุณและแตะ \"ดำเนินการต่อ\" ด้านล่าง';

  @override
  String get needMicrophonePermission =>
      'เราต้องการสิทธิ์ไมโครโฟน\n\n1. แตะ \"อนุญาตสิทธิ์\"\n2. อนุญาตบน iPhone ของคุณ\n3. แอปบนนาฬิกาจะปิด\n4. เปิดใหม่และแตะ \"ดำเนินการต่อ\"';

  @override
  String get grantPermissionButton => 'อนุญาตสิทธิ์';

  @override
  String get needHelp => 'ต้องการความช่วยเหลือ?';

  @override
  String get troubleshootingSteps =>
      'วิธีแก้ปัญหา:\n\n1. ตรวจสอบว่าได้ติดตั้ง Omi บนนาฬิกาแล้ว\n2. เปิดแอป Omi บนนาฬิกาของคุณ\n3. มองหาป๊อปอัปสิทธิ์\n4. แตะ \"อนุญาต\" เมื่อได้รับแจ้ง\n5. แอปบนนาฬิกาจะปิด - เปิดใหม่\n6. กลับมาและแตะ \"ดำเนินการต่อ\" บน iPhone ของคุณ';

  @override
  String get recordingStartedSuccessfully => 'เริ่มบันทึกสำเร็จ!';

  @override
  String get permissionNotGrantedYet =>
      'ยังไม่ได้อนุญาตสิทธิ์ กรุณาตรวจสอบให้แน่ใจว่าคุณได้อนุญาตการเข้าถึงไมโครโฟนและเปิดแอปบนนาฬิกาใหม่แล้ว';

  @override
  String errorRequestingPermission(String error) {
    return 'ขอสิทธิ์ไม่สำเร็จ: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'เริ่มบันทึกไม่สำเร็จ: $error';
  }

  @override
  String get selectPrimaryLanguage => 'เลือกภาษาหลักของคุณ';

  @override
  String get languageBenefits => 'ตั้งค่าภาษาของคุณเพื่อการถอดเสียงที่แม่นยำขึ้นและประสบการณ์ที่เป็นส่วนตัว';

  @override
  String get whatsYourPrimaryLanguage => 'ภาษาหลักของคุณคืออะไร?';

  @override
  String get selectYourLanguage => 'เลือกภาษาของคุณ';

  @override
  String get personalGrowthJourney => 'การเดินทางพัฒนาตนเองของคุณกับ AI ที่ฟังทุกคำพูดของคุณ';

  @override
  String get actionItemsTitle => 'สิ่งที่ต้องทำ';

  @override
  String get actionItemsDescription => 'แตะเพื่อแก้ไข • กดค้างเพื่อเลือก • ปัดเพื่อดำเนินการ';

  @override
  String get tabToDo => 'ต้องทำ';

  @override
  String get tabDone => 'เสร็จแล้ว';

  @override
  String get tabOld => 'เก่า';

  @override
  String get emptyTodoMessage => '🎉 ทำทุกอย่างเสร็จแล้ว!\nไม่มีสิ่งที่ต้องทำที่รอดำเนินการ';

  @override
  String get emptyDoneMessage => 'ยังไม่มีรายการที่เสร็จสมบูรณ์';

  @override
  String get emptyOldMessage => '✅ ไม่มีงานเก่า';

  @override
  String get noItems => 'ไม่มีรายการ';

  @override
  String get actionItemMarkedIncomplete => 'ทำเครื่องหมายสิ่งที่ต้องทำเป็นยังไม่เสร็จสมบูรณ์';

  @override
  String get actionItemCompleted => 'ทำสิ่งที่ต้องทำเสร็จแล้ว';

  @override
  String get deleteActionItemTitle => 'ลบรายการการดำเนินการ';

  @override
  String get deleteActionItemMessage => 'คุณแน่ใจหรือไม่ว่าต้องการลบรายการการดำเนินการนี้';

  @override
  String get deleteSelectedItemsTitle => 'ลบรายการที่เลือก';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'คุณแน่ใจหรือไม่ว่าต้องการลบสิ่งที่ต้องทำที่เลือก $count รายการ$s?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'ลบสิ่งที่ต้องทำ \"$description\" แล้ว';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return 'ลบสิ่งที่ต้องทำ $count รายการ$sแล้ว';
  }

  @override
  String get failedToDeleteItem => 'ลบสิ่งที่ต้องทำไม่สำเร็จ';

  @override
  String get failedToDeleteItems => 'ลบรายการไม่สำเร็จ';

  @override
  String get failedToDeleteSomeItems => 'ลบบางรายการไม่สำเร็จ';

  @override
  String get welcomeActionItemsTitle => 'พร้อมสำหรับสิ่งที่ต้องทำ';

  @override
  String get welcomeActionItemsDescription =>
      'AI ของคุณจะดึงงานและสิ่งที่ต้องทำจากบทสนทนาโดยอัตโนมัติ รายการจะปรากฏที่นี่เมื่อสร้าง';

  @override
  String get autoExtractionFeature => 'ดึงจากบทสนทนาอัตโนมัติ';

  @override
  String get editSwipeFeature => 'แตะเพื่อแก้ไข ปัดเพื่อทำให้เสร็จหรือลบ';

  @override
  String itemsSelected(int count) {
    return 'เลือกแล้ว $count รายการ';
  }

  @override
  String get selectAll => 'เลือกทั้งหมด';

  @override
  String get deleteSelected => 'ลบที่เลือก';

  @override
  String get searchMemories => 'ค้นหาความทรงจำ...';

  @override
  String get memoryDeleted => 'ลบความทรงจำแล้ว';

  @override
  String get undo => 'เลิกทำ';

  @override
  String get noMemoriesYet => '🧠 ยังไม่มีความทรงจำ';

  @override
  String get noAutoMemories => 'ยังไม่มีความทรงจำที่ดึงอัตโนมัติ';

  @override
  String get noManualMemories => 'ยังไม่มีความทรงจำที่สร้างด้วยตนเอง';

  @override
  String get noMemoriesInCategories => 'ไม่มีความทรงจำในหมวดหมู่เหล่านี้';

  @override
  String get noMemoriesFound => '🔍 ไม่พบความทรงจำ';

  @override
  String get addFirstMemory => 'เพิ่มความทรงจำแรกของคุณ';

  @override
  String get clearMemoryTitle => 'ล้างความทรงจำของ Omi';

  @override
  String get clearMemoryMessage => 'คุณแน่ใจหรือไม่ว่าต้องการล้างความทรงจำของ Omi? การกระทำนี้ไม่สามารถยกเลิกได้';

  @override
  String get clearMemoryButton => 'ล้างความทรงจำ';

  @override
  String get memoryClearedSuccess => 'ล้างความทรงจำของ Omi เกี่ยวกับคุณแล้ว';

  @override
  String get noMemoriesToDelete => 'ไม่มีความทรงจำที่จะลบ';

  @override
  String get createMemoryTooltip => 'สร้างความทรงจำใหม่';

  @override
  String get createActionItemTooltip => 'สร้างสิ่งที่ต้องทำใหม่';

  @override
  String get memoryManagement => 'การจัดการความทรงจำ';

  @override
  String get filterMemories => 'กรองความทรงจำ';

  @override
  String totalMemoriesCount(int count) {
    return 'คุณมีความทรงจำทั้งหมด $count รายการ';
  }

  @override
  String get publicMemories => 'ความทรงจำสาธารณะ';

  @override
  String get privateMemories => 'ความทรงจำส่วนตัว';

  @override
  String get makeAllPrivate => 'ทำให้ความทรงจำทั้งหมดเป็นส่วนตัว';

  @override
  String get makeAllPublic => 'ทำให้ความทรงจำทั้งหมดเป็นสาธารณะ';

  @override
  String get deleteAllMemories => 'ลบความทรงจำทั้งหมด';

  @override
  String get allMemoriesPrivateResult => 'ความทรงจำทั้งหมดเป็นส่วนตัวแล้ว';

  @override
  String get allMemoriesPublicResult => 'ความทรงจำทั้งหมดเป็นสาธารณะแล้ว';

  @override
  String get newMemory => '✨ ความทรงจำใหม่';

  @override
  String get editMemory => '✏️ แก้ไขความทรงจำ';

  @override
  String get memoryContentHint => 'ฉันชอบกินไอศกรีม...';

  @override
  String get failedToSaveMemory => 'บันทึกไม่สำเร็จ กรุณาตรวจสอบการเชื่อมต่อของคุณ';

  @override
  String get saveMemory => 'บันทึกความทรงจำ';

  @override
  String get retry => 'ลองอีกครั้ง';

  @override
  String get createActionItem => 'สร้างรายการงาน';

  @override
  String get editActionItem => 'แก้ไขรายการงาน';

  @override
  String get actionItemDescriptionHint => 'ต้องทำอะไร?';

  @override
  String get actionItemDescriptionEmpty => 'คำอธิบายสิ่งที่ต้องทำต้องไม่ว่างเปล่า';

  @override
  String get actionItemUpdated => 'อัปเดตสิ่งที่ต้องทำแล้ว';

  @override
  String get failedToUpdateActionItem => 'อัปเดตรายการงานล้มเหลว';

  @override
  String get actionItemCreated => 'สร้างสิ่งที่ต้องทำแล้ว';

  @override
  String get failedToCreateActionItem => 'สร้างรายการงานล้มเหลว';

  @override
  String get dueDate => 'วันครบกำหนด';

  @override
  String get time => 'เวลา';

  @override
  String get addDueDate => 'เพิ่มวันครบกำหนด';

  @override
  String get pressDoneToSave => 'กดเสร็จสิ้นเพื่อบันทึก';

  @override
  String get pressDoneToCreate => 'กดเสร็จสิ้นเพื่อสร้าง';

  @override
  String get filterAll => 'ทั้งหมด';

  @override
  String get filterSystem => 'เกี่ยวกับคุณ';

  @override
  String get filterInteresting => 'ข้อมูลเชิงลึก';

  @override
  String get filterManual => 'ด้วยตนเอง';

  @override
  String get completed => 'เสร็จสิ้น';

  @override
  String get markComplete => 'ทำเครื่องหมายว่าเสร็จสมบูรณ์';

  @override
  String get actionItemDeleted => 'ลบรายการการดำเนินการแล้ว';

  @override
  String get failedToDeleteActionItem => 'ลบรายการงานล้มเหลว';

  @override
  String get deleteActionItemConfirmTitle => 'ลบสิ่งที่ต้องทำ';

  @override
  String get deleteActionItemConfirmMessage => 'คุณแน่ใจหรือไม่ว่าต้องการลบสิ่งที่ต้องทำนี้?';

  @override
  String get appLanguage => 'ภาษาแอป';

  @override
  String get appInterfaceSectionTitle => 'อินเทอร์เฟซแอป';

  @override
  String get speechTranscriptionSectionTitle => 'คำพูดและการถอดเสียง';

  @override
  String get languageSettingsHelperText => 'ภาษาแอปเปลี่ยนเมนูและปุ่ม ภาษาคำพูดส่งผลต่อวิธีถอดเสียงการบันทึกของคุณ';

  @override
  String get translationNotice => 'ประกาศการแปล';

  @override
  String get translationNoticeMessage => 'Omi แปลการสนทนาเป็นภาษาหลักของคุณ อัปเดตได้ทุกเมื่อในการตั้งค่า → โปรไฟล์';

  @override
  String get pleaseCheckInternetConnection => 'โปรดตรวจสอบการเชื่อมต่ออินเทอร์เน็ตของคุณแล้วลองอีกครั้ง';

  @override
  String get pleaseSelectReason => 'โปรดเลือกเหตุผล';

  @override
  String get tellUsMoreWhatWentWrong => 'บอกเราเพิ่มเติมเกี่ยวกับสิ่งที่ผิดพลาด...';

  @override
  String get selectText => 'เลือกข้อความ';

  @override
  String maximumGoalsAllowed(int count) {
    return 'อนุญาตสูงสุด $count เป้าหมาย';
  }

  @override
  String get conversationCannotBeMerged => 'ไม่สามารถรวมการสนทนานี้ได้ (ถูกล็อกหรือกำลังรวมอยู่)';

  @override
  String get pleaseEnterFolderName => 'โปรดป้อนชื่อโฟลเดอร์';

  @override
  String get failedToCreateFolder => 'สร้างโฟลเดอร์ไม่สำเร็จ';

  @override
  String get failedToUpdateFolder => 'อัปเดตโฟลเดอร์ไม่สำเร็จ';

  @override
  String get folderName => 'ชื่อโฟลเดอร์';

  @override
  String get descriptionOptional => 'คำอธิบาย (ไม่จำเป็น)';

  @override
  String get failedToDeleteFolder => 'ลบโฟลเดอร์ไม่สำเร็จ';

  @override
  String get editFolder => 'แก้ไขโฟลเดอร์';

  @override
  String get deleteFolder => 'ลบโฟลเดอร์';

  @override
  String get transcriptCopiedToClipboard => 'คัดลอกบันทึกการสนทนาไปยังคลิปบอร์ดแล้ว';

  @override
  String get summaryCopiedToClipboard => 'คัดลอกสรุปไปยังคลิปบอร์ดแล้ว';

  @override
  String get conversationUrlCouldNotBeShared => 'ไม่สามารถแชร์ URL การสนทนาได้';

  @override
  String get urlCopiedToClipboard => 'คัดลอก URL ไปยังคลิปบอร์ดแล้ว';

  @override
  String get exportTranscript => 'ส่งออกบันทึกการสนทนา';

  @override
  String get exportSummary => 'ส่งออกสรุป';

  @override
  String get exportButton => 'ส่งออก';

  @override
  String get actionItemsCopiedToClipboard => 'คัดลอกรายการดำเนินการไปยังคลิปบอร์ดแล้ว';

  @override
  String get summarize => 'สรุป';

  @override
  String get generateSummary => 'สร้างสรุป';

  @override
  String get conversationNotFoundOrDeleted => 'ไม่พบการสนทนาหรือถูกลบแล้ว';

  @override
  String get deleteMemory => 'ลบความทรงจำ';

  @override
  String get thisActionCannotBeUndone => 'การดำเนินการนี้ไม่สามารถยกเลิกได้';

  @override
  String memoriesCount(int count) {
    return '$count ความทรงจำ';
  }

  @override
  String get noMemoriesInCategory => 'ยังไม่มีความทรงจำในหมวดหมู่นี้';

  @override
  String get addYourFirstMemory => 'เพิ่มความทรงจำแรกของคุณ';

  @override
  String get firmwareDisconnectUsb => 'ถอด USB';

  @override
  String get firmwareUsbWarning => 'การเชื่อมต่อ USB ระหว่างการอัปเดตอาจทำให้อุปกรณ์ของคุณเสียหาย';

  @override
  String get firmwareBatteryAbove15 => 'แบตเตอรี่เหนือ 15%';

  @override
  String get firmwareEnsureBattery => 'ตรวจสอบให้แน่ใจว่าอุปกรณ์ของคุณมีแบตเตอรี่ 15%';

  @override
  String get firmwareStableConnection => 'การเชื่อมต่อที่เสถียร';

  @override
  String get firmwareConnectWifi => 'เชื่อมต่อกับ WiFi หรือเครือข่ายมือถือ';

  @override
  String failedToStartUpdate(String error) {
    return 'ไม่สามารถเริ่มการอัปเดต: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'ก่อนอัปเดต ตรวจสอบให้แน่ใจว่า:';

  @override
  String get confirmed => 'ยืนยันแล้ว!';

  @override
  String get release => 'ปล่อย';

  @override
  String get slideToUpdate => 'เลื่อนเพื่ออัปเดต';

  @override
  String copiedToClipboard(String title) {
    return 'คัดลอก $title ไปยังคลิปบอร์ดแล้ว';
  }

  @override
  String get batteryLevel => 'ระดับแบตเตอรี่';

  @override
  String get productUpdate => 'การอัปเดตผลิตภัณฑ์';

  @override
  String get offline => 'ออฟไลน์';

  @override
  String get available => 'พร้อมใช้งาน';

  @override
  String get unpairDeviceDialogTitle => 'ยกเลิกการจับคู่อุปกรณ์';

  @override
  String get unpairDeviceDialogMessage =>
      'การดำเนินการนี้จะยกเลิกการจับคู่อุปกรณ์เพื่อให้สามารถเชื่อมต่อกับโทรศัพท์เครื่องอื่นได้ คุณจะต้องไปที่การตั้งค่า > Bluetooth และลืมอุปกรณ์เพื่อทำกระบวนการให้เสร็จสมบูรณ์';

  @override
  String get unpair => 'ยกเลิกการจับคู่';

  @override
  String get unpairAndForgetDevice => 'ยกเลิกการจับคู่และลืมอุปกรณ์';

  @override
  String get unknownDevice => 'ไม่ทราบ';

  @override
  String get unknown => 'ไม่ทราบ';

  @override
  String get productName => 'ชื่อผลิตภัณฑ์';

  @override
  String get serialNumber => 'หมายเลขซีเรียล';

  @override
  String get connected => 'เชื่อมต่อแล้ว';

  @override
  String get privacyPolicyTitle => 'นโยบายความเป็นส่วนตัว';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return 'คัดลอก $label แล้ว';
  }

  @override
  String get noApiKeysYet => 'ยังไม่มีคีย์ API สร้างคีย์เพื่อเชื่อมต่อกับแอปของคุณ';

  @override
  String get createKeyToGetStarted => 'สร้างคีย์เพื่อเริ่มต้น';

  @override
  String get persona => 'บุคลิกภาพ';

  @override
  String get configureYourAiPersona => 'กำหนดค่าบุคลิก AI ของคุณ';

  @override
  String get configureSttProvider => 'กำหนดค่าผู้ให้บริการ STT';

  @override
  String get setWhenConversationsAutoEnd => 'ตั้งค่าเวลาที่การสนทนาจะสิ้นสุดโดยอัตโนมัติ';

  @override
  String get importDataFromOtherSources => 'นำเข้าข้อมูลจากแหล่งอื่น';

  @override
  String get debugAndDiagnostics => 'การดีบักและการวินิจฉัย';

  @override
  String get autoDeletesAfter3Days => 'ลบอัตโนมัติหลังจาก 3 วัน';

  @override
  String get helpsDiagnoseIssues => 'ช่วยวินิจฉัยปัญหา';

  @override
  String get exportStartedMessage => 'เริ่มส่งออกแล้ว อาจใช้เวลาสักครู่...';

  @override
  String get exportConversationsToJson => 'ส่งออกการสนทนาเป็นไฟล์ JSON';

  @override
  String get knowledgeGraphDeletedSuccess => 'ลบกราฟความรู้สำเร็จแล้ว';

  @override
  String failedToDeleteGraph(String error) {
    return 'ไม่สามารถลบกราฟได้: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'ล้างโหนดและการเชื่อมต่อทั้งหมด';

  @override
  String get addToClaudeDesktopConfig => 'เพิ่มไปยัง claude_desktop_config.json';

  @override
  String get connectAiAssistantsToData => 'เชื่อมต่อผู้ช่วย AI กับข้อมูลของคุณ';

  @override
  String get useYourMcpApiKey => 'ใช้คีย์ MCP API ของคุณ';

  @override
  String get realTimeTranscript => 'การถอดความเรียลไทม์';

  @override
  String get experimental => 'ทดลอง';

  @override
  String get transcriptionDiagnostics => 'การวินิจฉัยการถอดความ';

  @override
  String get detailedDiagnosticMessages => 'ข้อความวินิจฉัยโดยละเอียด';

  @override
  String get autoCreateSpeakers => 'สร้างผู้พูดอัตโนมัติ';

  @override
  String get autoCreateWhenNameDetected => 'สร้างอัตโนมัติเมื่อตรวจพบชื่อ';

  @override
  String get followUpQuestions => 'คำถามติดตาม';

  @override
  String get suggestQuestionsAfterConversations => 'แนะนำคำถามหลังจากการสนทนา';

  @override
  String get goalTracker => 'ตัวติดตามเป้าหมาย';

  @override
  String get trackPersonalGoalsOnHomepage => 'ติดตามเป้าหมายส่วนตัวบนหน้าแรก';

  @override
  String get dailyReflection => 'การทบทวนรายวัน';

  @override
  String get get9PmReminderToReflect => 'รับการแจ้งเตือนเวลา 21:00 น. เพื่อทบทวนวันของคุณ';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'คำอธิบายรายการการดำเนินการต้องไม่ว่างเปล่า';

  @override
  String get saved => 'บันทึกแล้ว';

  @override
  String get overdue => 'เกินกำหนด';

  @override
  String get failedToUpdateDueDate => 'การอัปเดตวันครบกำหนดล้มเหลว';

  @override
  String get markIncomplete => 'ทำเครื่องหมายว่ายังไม่เสร็จ';

  @override
  String get editDueDate => 'แก้ไขวันครบกำหนด';

  @override
  String get setDueDate => 'ตั้งวันครบกำหนด';

  @override
  String get clearDueDate => 'ลบวันครบกำหนด';

  @override
  String get failedToClearDueDate => 'การลบวันครบกำหนดล้มเหลว';

  @override
  String get mondayAbbr => 'จ';

  @override
  String get tuesdayAbbr => 'อ';

  @override
  String get wednesdayAbbr => 'พ';

  @override
  String get thursdayAbbr => 'พฤ';

  @override
  String get fridayAbbr => 'ศ';

  @override
  String get saturdayAbbr => 'ส';

  @override
  String get sundayAbbr => 'อา';

  @override
  String get howDoesItWork => 'มันทำงานอย่างไร?';

  @override
  String get sdCardSyncDescription => 'การซิงค์การ์ด SD จะนำเข้าความทรงจำของคุณจากการ์ด SD ไปยังแอป';

  @override
  String get checksForAudioFiles => 'ตรวจสอบไฟล์เสียงบนการ์ด SD';

  @override
  String get omiSyncsAudioFiles => 'Omi จากนั้นจะซิงค์ไฟล์เสียงกับเซิร์ฟเวอร์';

  @override
  String get serverProcessesAudio => 'เซิร์ฟเวอร์ประมวลผลไฟล์เสียงและสร้างความทรงจำ';

  @override
  String get youreAllSet => 'คุณพร้อมแล้ว!';

  @override
  String get welcomeToOmiDescription =>
      'ยินดีต้อนรับสู่ Omi! คู่หูAIของคุณพร้อมที่จะช่วยเหลือคุณในการสนทนา งาน และอื่นๆ';

  @override
  String get startUsingOmi => 'เริ่มใช้ Omi';

  @override
  String get back => 'กลับ';

  @override
  String get keyboardShortcuts => 'แป้นพิมพ์ลัด';

  @override
  String get toggleControlBar => 'สลับแถบควบคุม';

  @override
  String get pressKeys => 'กดปุ่ม...';

  @override
  String get cmdRequired => '⌘ จำเป็น';

  @override
  String get invalidKey => 'ปุ่มไม่ถูกต้อง';

  @override
  String get space => 'ช่องว่าง';

  @override
  String get search => 'ค้นหา';

  @override
  String get searchPlaceholder => 'ค้นหา...';

  @override
  String get untitledConversation => 'การสนทนาที่ไม่มีชื่อ';

  @override
  String countRemaining(String count) {
    return '$count เหลือ';
  }

  @override
  String get addGoal => 'เพิ่มเป้าหมาย';

  @override
  String get editGoal => 'แก้ไขเป้าหมาย';

  @override
  String get icon => 'ไอคอน';

  @override
  String get goalTitle => 'ชื่อเป้าหมาย';

  @override
  String get current => 'ปัจจุบัน';

  @override
  String get target => 'เป้าหมาย';

  @override
  String get saveGoal => 'บันทึก';

  @override
  String get goals => 'เป้าหมาย';

  @override
  String get tapToAddGoal => 'แตะเพื่อเพิ่มเป้าหมาย';

  @override
  String welcomeBack(String name) {
    return 'ยินดีต้อนรับกลับมา $name';
  }

  @override
  String get yourConversations => 'การสนทนาของคุณ';

  @override
  String get reviewAndManageConversations => 'ตรวจสอบและจัดการการสนทนาที่บันทึกไว้';

  @override
  String get startCapturingConversations => 'เริ่มบันทึกการสนทนาด้วยอุปกรณ์ Omi ของคุณเพื่อดูที่นี่';

  @override
  String get useMobileAppToCapture => 'ใช้แอปมือถือของคุณในการบันทึกเสียง';

  @override
  String get conversationsProcessedAutomatically => 'การสนทนาได้รับการประมวลผลโดยอัตโนมัติ';

  @override
  String get getInsightsInstantly => 'รับข้อมูลเชิงลึกและสรุปได้ทันที';

  @override
  String get showAll => 'แสดงทั้งหมด →';

  @override
  String get noTasksForToday => 'ไม่มีงานสำหรับวันนี้\nถาม Omi เพื่อรับงานเพิ่มเติมหรือสร้างด้วยตนเอง';

  @override
  String get dailyScore => 'คะแนนประจำวัน';

  @override
  String get dailyScoreDescription => 'คะแนนที่ช่วยให้คุณ\nโฟกัสกับการปฏิบัติงานได้ดีขึ้น';

  @override
  String get searchResults => 'ผลการค้นหา';

  @override
  String get actionItems => 'รายการดำเนินการ';

  @override
  String get tasksToday => 'วันนี้';

  @override
  String get tasksTomorrow => 'พรุ่งนี้';

  @override
  String get tasksNoDeadline => 'ไม่มีกำหนดเวลา';

  @override
  String get tasksLater => 'ภายหลัง';

  @override
  String get loadingTasks => 'กำลังโหลดงาน...';

  @override
  String get tasks => 'งาน';

  @override
  String get swipeTasksToIndent => 'ปัดงานเพื่อเยื้อง ลากระหว่างหมวดหมู่';

  @override
  String get create => 'สร้าง';

  @override
  String get noTasksYet => 'ยังไม่มีงาน';

  @override
  String get tasksFromConversationsWillAppear => 'งานจากการสนทนาของคุณจะปรากฏที่นี่\nคลิกสร้างเพื่อเพิ่มด้วยตนเอง';

  @override
  String get monthJan => 'ม.ค.';

  @override
  String get monthFeb => 'ก.พ.';

  @override
  String get monthMar => 'มี.ค.';

  @override
  String get monthApr => 'เม.ย.';

  @override
  String get monthMay => 'พ.ค.';

  @override
  String get monthJun => 'มิ.ย.';

  @override
  String get monthJul => 'ก.ค.';

  @override
  String get monthAug => 'ส.ค.';

  @override
  String get monthSep => 'ก.ย.';

  @override
  String get monthOct => 'ต.ค.';

  @override
  String get monthNov => 'พ.ย.';

  @override
  String get monthDec => 'ธ.ค.';

  @override
  String get timePM => 'PM';

  @override
  String get timeAM => 'AM';

  @override
  String get actionItemUpdatedSuccessfully => 'อัปเดตรายการงานสำเร็จ';

  @override
  String get actionItemCreatedSuccessfully => 'สร้างรายการงานสำเร็จ';

  @override
  String get actionItemDeletedSuccessfully => 'ลบรายการงานสำเร็จ';

  @override
  String get deleteActionItem => 'ลบรายการงาน';

  @override
  String get deleteActionItemConfirmation =>
      'คุณแน่ใจหรือไม่ว่าต้องการลบรายการงานนี้ การดำเนินการนี้ไม่สามารถยกเลิกได้';

  @override
  String get enterActionItemDescription => 'ป้อนคำอธิบายรายการงาน...';

  @override
  String get markAsCompleted => 'ทำเครื่องหมายว่าเสร็จสิ้น';

  @override
  String get setDueDateAndTime => 'ตั้งวันและเวลาครบกำหนด';

  @override
  String get reloadingApps => 'กำลังโหลดแอปใหม่...';

  @override
  String get loadingApps => 'กำลังโหลดแอป...';

  @override
  String get browseInstallCreateApps => 'เรียกดู ติดตั้ง และสร้างแอป';

  @override
  String get all => 'ทั้งหมด';

  @override
  String get open => 'เปิด';

  @override
  String get install => 'ติดตั้ง';

  @override
  String get noAppsAvailable => 'ไม่มีแอปที่ใช้งานได้';

  @override
  String get unableToLoadApps => 'ไม่สามารถโหลดแอปได้';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'ลองปรับคำค้นหาหรือตัวกรองของคุณ';

  @override
  String get checkBackLaterForNewApps => 'กลับมาตรวจสอบแอปใหม่ในภายหลัง';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'โปรดตรวจสอบการเชื่อมต่ออินเทอร์เน็ตของคุณแล้วลองอีกครั้ง';

  @override
  String get createNewApp => 'สร้างแอปใหม่';

  @override
  String get buildSubmitCustomOmiApp => 'สร้างและส่งแอป Omi แบบกำหนดเองของคุณ';

  @override
  String get submittingYourApp => 'กำลังส่งแอปของคุณ...';

  @override
  String get preparingFormForYou => 'กำลังเตรียมแบบฟอร์มสำหรับคุณ...';

  @override
  String get appDetails => 'รายละเอียดแอป';

  @override
  String get paymentDetails => 'รายละเอียดการชำระเงิน';

  @override
  String get previewAndScreenshots => 'ตัวอย่างและภาพหน้าจอ';

  @override
  String get appCapabilities => 'ความสามารถของแอป';

  @override
  String get aiPrompts => 'พร้อมท์ AI';

  @override
  String get chatPrompt => 'พร้อมท์แชท';

  @override
  String get chatPromptPlaceholder => 'คุณเป็นแอปที่ยอดเยี่ยม งานของคุณคือตอบคำถามของผู้ใช้และทำให้พวกเขารู้สึกดี...';

  @override
  String get conversationPrompt => 'คำสั่งการสนทนา';

  @override
  String get conversationPromptPlaceholder => 'คุณเป็นแอปที่ยอดเยี่ยม คุณจะได้รับบทสนทนาและสรุปการสนทนา...';

  @override
  String get notificationScopes => 'ขอบเขตการแจ้งเตือน';

  @override
  String get appPrivacyAndTerms => 'ความเป็นส่วนตัวและข้อกำหนดของแอป';

  @override
  String get makeMyAppPublic => 'ทำให้แอปของฉันเป็นสาธารณะ';

  @override
  String get submitAppTermsAgreement => 'การส่งแอปนี้ ฉันยอมรับข้อกำหนดการให้บริการและนโยบายความเป็นส่วนตัวของ Omi AI';

  @override
  String get submitApp => 'ส่งแอป';

  @override
  String get needHelpGettingStarted => 'ต้องการความช่วยเหลือในการเริ่มต้นหรือไม่?';

  @override
  String get clickHereForAppBuildingGuides => 'คลิกที่นี่เพื่อดูคู่มือการสร้างแอปและเอกสาร';

  @override
  String get submitAppQuestion => 'ส่งแอปหรือไม่?';

  @override
  String get submitAppPublicDescription =>
      'แอปของคุณจะได้รับการตรวจสอบและเผยแพร่สู่สาธารณะ คุณสามารถเริ่มใช้งานได้ทันที แม้ในระหว่างการตรวจสอบ!';

  @override
  String get submitAppPrivateDescription =>
      'แอปของคุณจะได้รับการตรวจสอบและเปิดให้คุณใช้งานแบบส่วนตัว คุณสามารถเริ่มใช้งานได้ทันที แม้ในระหว่างการตรวจสอบ!';

  @override
  String get startEarning => 'เริ่มหารายได้! 💰';

  @override
  String get connectStripeOrPayPal => 'เชื่อมต่อ Stripe หรือ PayPal เพื่อรับการชำระเงินสำหรับแอปของคุณ';

  @override
  String get connectNow => 'เชื่อมต่อตอนนี้';

  @override
  String get installsCount => 'การติดตั้ง';

  @override
  String get uninstallApp => 'ถอนการติดตั้งแอป';

  @override
  String get subscribe => 'สมัครสมาชิก';

  @override
  String get dataAccessNotice => 'ประกาศการเข้าถึงข้อมูล';

  @override
  String get dataAccessWarning =>
      'แอปนี้จะเข้าถึงข้อมูลของคุณ Omi AI ไม่รับผิดชอบต่อวิธีการใช้ แก้ไข หรือลบข้อมูลของคุณโดยแอปนี้';

  @override
  String get installApp => 'ติดตั้งแอป';

  @override
  String get betaTesterNotice =>
      'คุณเป็นผู้ทดสอบเบต้าสำหรับแอปนี้ ยังไม่เปิดเผยต่อสาธารณะ จะเปิดเผยต่อสาธารณะเมื่อได้รับการอนุมัติ';

  @override
  String get appUnderReviewOwner =>
      'แอปของคุณกำลังอยู่ในระหว่างการตรวจสอบและมองเห็นได้เฉพาะคุณเท่านั้น จะเปิดเผยต่อสาธารณะเมื่อได้รับการอนุมัติ';

  @override
  String get appRejectedNotice => 'แอปของคุณถูกปฏิเสธ โปรดอัปเดตรายละเอียดแอปและส่งอีกครั้งเพื่อตรวจสอบ';

  @override
  String get setupSteps => 'ขั้นตอนการตั้งค่า';

  @override
  String get setupInstructions => 'คำแนะนำการตั้งค่า';

  @override
  String get integrationInstructions => 'คำแนะนำการผสานรวม';

  @override
  String get preview => 'ดูตัวอย่าง';

  @override
  String get aboutTheApp => 'เกี่ยวกับแอป';

  @override
  String get aboutThePersona => 'เกี่ยวกับเพอร์โซน่า';

  @override
  String get chatPersonality => 'บุคลิกแชท';

  @override
  String get ratingsAndReviews => 'คะแนนและรีวิว';

  @override
  String get noRatings => 'ไม่มีคะแนน';

  @override
  String ratingsCount(String count) {
    return '$count+ คะแนน';
  }

  @override
  String get errorActivatingApp => 'ข้อผิดพลาดในการเปิดใช้งานแอป';

  @override
  String get integrationSetupRequired => 'หากนี่เป็นแอปการผสานรวม ตรวจสอบให้แน่ใจว่าการตั้งค่าเสร็จสมบูรณ์';

  @override
  String get installed => 'ติดตั้งแล้ว';

  @override
  String get appIdLabel => 'ID แอป';

  @override
  String get appNameLabel => 'ชื่อแอป';

  @override
  String get appNamePlaceholder => 'แอปที่ยอดเยี่ยมของฉัน';

  @override
  String get pleaseEnterAppName => 'กรุณาป้อนชื่อแอป';

  @override
  String get categoryLabel => 'หมวดหมู่';

  @override
  String get selectCategory => 'เลือกหมวดหมู่';

  @override
  String get descriptionLabel => 'คำอธิบาย';

  @override
  String get appDescriptionPlaceholder =>
      'แอปที่ยอดเยี่ยมของฉันเป็นแอปที่ยอดเยี่ยมที่ทำสิ่งที่น่าทึ่ง มันเป็นแอปที่ดีที่สุด!';

  @override
  String get pleaseProvideValidDescription => 'กรุณาให้คำอธิบายที่ถูกต้อง';

  @override
  String get appPricingLabel => 'การกำหนดราคาแอป';

  @override
  String get noneSelected => 'ไม่ได้เลือก';

  @override
  String get appIdCopiedToClipboard => 'คัดลอก ID แอปไปยังคลิปบอร์ดแล้ว';

  @override
  String get appCategoryModalTitle => 'หมวดหมู่แอป';

  @override
  String get pricingFree => 'ฟรี';

  @override
  String get pricingPaid => 'เสียค่าใช้จ่าย';

  @override
  String get loadingCapabilities => 'กำลังโหลดความสามารถ...';

  @override
  String get filterInstalled => 'ติดตั้งแล้ว';

  @override
  String get filterMyApps => 'แอปของฉัน';

  @override
  String get clearSelection => 'ล้างการเลือก';

  @override
  String get filterCategory => 'หมวดหมู่';

  @override
  String get rating4PlusStars => '4+ ดาว';

  @override
  String get rating3PlusStars => '3+ ดาว';

  @override
  String get rating2PlusStars => '2+ ดาว';

  @override
  String get rating1PlusStars => '1+ ดาว';

  @override
  String get filterRating => 'คะแนน';

  @override
  String get filterCapabilities => 'ความสามารถ';

  @override
  String get noNotificationScopesAvailable => 'ไม่มีขอบเขตการแจ้งเตือนที่พร้อมใช้งาน';

  @override
  String get popularApps => 'แอปยอดนิยม';

  @override
  String get pleaseProvidePrompt => 'กรุณาระบุพรอมต์';

  @override
  String chatWithAppName(String appName) {
    return 'แชทกับ $appName';
  }

  @override
  String get defaultAiAssistant => 'ผู้ช่วย AI เริ่มต้น';

  @override
  String get readyToChat => '✨ พร้อมแชท!';

  @override
  String get connectionNeeded => '🌐 ต้องการการเชื่อมต่อ';

  @override
  String get startConversation => 'เริ่มการสนทนาและปล่อยให้มนต์ขลังเริ่มต้น';

  @override
  String get checkInternetConnection => 'โปรดตรวจสอบการเชื่อมต่ออินเทอร์เน็ตของคุณ';

  @override
  String get wasThisHelpful => 'มีประโยชน์หรือไม่?';

  @override
  String get thankYouForFeedback => 'ขอบคุณสำหรับคำติชมของคุณ!';

  @override
  String get maxFilesUploadError => 'คุณสามารถอัปโหลดได้เพียง 4 ไฟล์ต่อครั้ง';

  @override
  String get attachedFiles => '📎 ไฟล์ที่แนบมา';

  @override
  String get takePhoto => 'ถ่ายรูป';

  @override
  String get captureWithCamera => 'จับภาพด้วยกล้อง';

  @override
  String get selectImages => 'เลือกรูปภาพ';

  @override
  String get chooseFromGallery => 'เลือกจากแกลเลอรี';

  @override
  String get selectFile => 'เลือกไฟล์';

  @override
  String get chooseAnyFileType => 'เลือกประเภทไฟล์ใดก็ได้';

  @override
  String get cannotReportOwnMessages => 'คุณไม่สามารถรายงานข้อความของคุณเองได้';

  @override
  String get messageReportedSuccessfully => '✅ รายงานข้อความสำเร็จ';

  @override
  String get confirmReportMessage => 'คุณแน่ใจหรือไม่ว่าต้องการรายงานข้อความนี้?';

  @override
  String get selectChatAssistant => 'เลือกผู้ช่วยแชท';

  @override
  String get enableMoreApps => 'เปิดใช้งานแอปเพิ่มเติม';

  @override
  String get chatCleared => 'ล้างแชทแล้ว';

  @override
  String get clearChatTitle => 'ล้างแชท?';

  @override
  String get confirmClearChat => 'คุณแน่ใจหรือไม่ว่าต้องการล้างแชท? การกระทำนี้ไม่สามารถยกเลิกได้';

  @override
  String get copy => 'คัดลอก';

  @override
  String get share => 'แชร์';

  @override
  String get report => 'รายงาน';

  @override
  String get microphonePermissionRequired => 'ต้องการสิทธิ์การใช้ไมโครโฟนสำหรับการบันทึกเสียง';

  @override
  String get microphonePermissionDenied =>
      'สิทธิ์การใช้ไมโครโฟนถูกปฏิเสธ กรุณาอนุญาตสิทธิ์ใน การตั้งค่าระบบ > ความเป็นส่วนตัวและความปลอดภัย > ไมโครโฟน';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'ตรวจสอบสิทธิ์การใช้ไมโครโฟนไม่สำเร็จ: $error';
  }

  @override
  String get failedToTranscribeAudio => 'แปลงเสียงเป็นข้อความไม่สำเร็จ';

  @override
  String get transcribing => 'กำลังแปลง...';

  @override
  String get transcriptionFailed => 'การแปลงล้มเหลว';

  @override
  String get discardedConversation => 'การสนทนาที่ถูกยกเลิก';

  @override
  String get at => 'เวลา';

  @override
  String get from => 'จาก';

  @override
  String get copied => 'คัดลอกแล้ว!';

  @override
  String get copyLink => 'คัดลอกลิงก์';

  @override
  String get hideTranscript => 'ซ่อนบันทึกคำพูด';

  @override
  String get viewTranscript => 'ดูบันทึกคำพูด';

  @override
  String get conversationDetails => 'รายละเอียดการสนทนา';

  @override
  String get transcript => 'บันทึกคำพูด';

  @override
  String segmentsCount(int count) {
    return '$count ส่วน';
  }

  @override
  String get noTranscriptAvailable => 'ไม่มีบันทึกคำพูด';

  @override
  String get noTranscriptMessage => 'การสนทนานี้ไม่มีบันทึกคำพูด';

  @override
  String get conversationUrlCouldNotBeGenerated => 'ไม่สามารถสร้าง URL การสนทนาได้';

  @override
  String get failedToGenerateConversationLink => 'การสร้างลิงก์การสนทนาล้มเหลว';

  @override
  String get failedToGenerateShareLink => 'การสร้างลิงก์แชร์ล้มเหลว';

  @override
  String get reloadingConversations => 'กำลังโหลดการสนทนาใหม่...';

  @override
  String get user => 'ผู้ใช้';

  @override
  String get starred => 'ติดดาว';

  @override
  String get date => 'วันที่';

  @override
  String get noResultsFound => 'ไม่พบผลลัพธ์';

  @override
  String get tryAdjustingSearchTerms => 'ลองปรับคำค้นหาของคุณ';

  @override
  String get starConversationsToFindQuickly => 'ติดดาวการสนทนาเพื่อค้นหาได้อย่างรวดเร็วที่นี่';

  @override
  String noConversationsOnDate(String date) {
    return 'ไม่มีการสนทนาในวันที่ $date';
  }

  @override
  String get trySelectingDifferentDate => 'ลองเลือกวันที่อื่น';

  @override
  String get conversations => 'การสนทนา';

  @override
  String get chat => 'แชท';

  @override
  String get actions => 'การดำเนินการ';

  @override
  String get syncAvailable => 'มีการซิงค์';

  @override
  String get referAFriend => 'แนะนำเพื่อน';

  @override
  String get help => 'ความช่วยเหลือ';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'อัปเกรดเป็น Pro';

  @override
  String get getOmiDevice => 'รับอุปกรณ์ Omi';

  @override
  String get wearableAiCompanion => 'เพื่อน AI สวมใส่ได้';

  @override
  String get loadingMemories => 'กำลังโหลดความทรงจำ...';

  @override
  String get allMemories => 'ความทรงจำทั้งหมด';

  @override
  String get aboutYou => 'เกี่ยวกับคุณ';

  @override
  String get manual => 'แมนนวล';

  @override
  String get loadingYourMemories => 'กำลังโหลดความทรงจำของคุณ...';

  @override
  String get createYourFirstMemory => 'สร้างความทรงจำแรกของคุณเพื่อเริ่มต้น';

  @override
  String get tryAdjustingFilter => 'ลองปรับการค้นหาหรือตัวกรอง';

  @override
  String get whatWouldYouLikeToRemember => 'คุณต้องการจดจำอะไร?';

  @override
  String get category => 'หมวดหมู่';

  @override
  String get public => 'สาธารณะ';

  @override
  String get failedToSaveCheckConnection => 'บันทึกไม่สำเร็จ กรุณาตรวจสอบการเชื่อมต่อของคุณ';

  @override
  String get createMemory => 'สร้างความทรงจำ';

  @override
  String get deleteMemoryConfirmation => 'คุณแน่ใจหรือไม่ว่าต้องการลบความทรงจำนี้? การกระทำนี้ไม่สามารถยกเลิกได้';

  @override
  String get makePrivate => 'เปลี่ยนเป็นส่วนตัว';

  @override
  String get organizeAndControlMemories => 'จัดระเบียบและควบคุมความทรงจำของคุณ';

  @override
  String get total => 'ทั้งหมด';

  @override
  String get makeAllMemoriesPrivate => 'ทำให้ความทรงจำทั้งหมดเป็นส่วนตัว';

  @override
  String get setAllMemoriesToPrivate => 'ตั้งค่าความทรงจำทั้งหมดเป็นส่วนตัว';

  @override
  String get makeAllMemoriesPublic => 'ทำให้ความทรงจำทั้งหมดเป็นสาธารณะ';

  @override
  String get setAllMemoriesToPublic => 'ตั้งค่าความทรงจำทั้งหมดเป็นสาธารณะ';

  @override
  String get permanentlyRemoveAllMemories => 'ลบความทรงจำทั้งหมดจาก Omi อย่างถาวร';

  @override
  String get allMemoriesAreNowPrivate => 'ความทรงจำทั้งหมดเป็นส่วนตัวแล้ว';

  @override
  String get allMemoriesAreNowPublic => 'ความทรงจำทั้งหมดเป็นสาธารณะแล้ว';

  @override
  String get clearOmisMemory => 'ล้างความทรงจำของ Omi';

  @override
  String clearMemoryConfirmation(int count) {
    return 'คุณแน่ใจหรือไม่ว่าต้องการล้างความทรงจำของ Omi? การดำเนินการนี้ไม่สามารถยกเลิกได้และจะลบความทรงจำทั้งหมด $count รายการอย่างถาวร';
  }

  @override
  String get omisMemoryCleared => 'ความทรงจำของ Omi เกี่ยวกับคุณถูกล้างแล้ว';

  @override
  String get welcomeToOmi => 'ยินดีต้อนรับสู่ Omi';

  @override
  String get continueWithApple => 'ดำเนินการต่อด้วย Apple';

  @override
  String get continueWithGoogle => 'ดำเนินการต่อด้วย Google';

  @override
  String get byContinuingYouAgree => 'การดำเนินการต่อหมายความว่าคุณยอมรับ';

  @override
  String get termsOfService => 'ข้อกำหนดการใช้บริการ';

  @override
  String get and => 'และ';

  @override
  String get dataAndPrivacy => 'ข้อมูลและความเป็นส่วนตัว';

  @override
  String get secureAuthViaAppleId => 'การยืนยันตัวตนที่ปลอดภัยผ่าน Apple ID';

  @override
  String get secureAuthViaGoogleAccount => 'การยืนยันตัวตนที่ปลอดภัยผ่านบัญชี Google';

  @override
  String get whatWeCollect => 'สิ่งที่เราเก็บรวบรวม';

  @override
  String get dataCollectionMessage =>
      'การดำเนินการต่อจะทำให้การสนทนา การบันทึก และข้อมูลส่วนบุคคลของคุณถูกเก็บไว้อย่างปลอดภัยบนเซิร์ฟเวอร์ของเราเพื่อมอบข้อมูลเชิงลึกที่ขับเคลื่อนด้วย AI และเปิดใช้งานคุณสมบัติทั้งหมดของแอป';

  @override
  String get dataProtection => 'การป้องกันข้อมูล';

  @override
  String get yourDataIsProtected => 'ข้อมูลของคุณได้รับการปกป้องและควบคุมโดย';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'กรุณาเลือกภาษาหลักของคุณ';

  @override
  String get chooseYourLanguage => 'เลือกภาษาของคุณ';

  @override
  String get selectPreferredLanguageForBestExperience => 'เลือกภาษาที่คุณต้องการสำหรับประสบการณ์ Omi ที่ดีที่สุด';

  @override
  String get searchLanguages => 'ค้นหาภาษา...';

  @override
  String get selectALanguage => 'เลือกภาษา';

  @override
  String get tryDifferentSearchTerm => 'ลองใช้คำค้นหาอื่น';

  @override
  String get pleaseEnterYourName => 'กรุณาใส่ชื่อของคุณ';

  @override
  String get nameMustBeAtLeast2Characters => 'ชื่อต้องมีอย่างน้อย 2 ตัวอักษร';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'บอกเราว่าคุณต้องการให้เรียกคุณอย่างไร นี่จะช่วยปรับแต่งประสบการณ์ Omi ของคุณ';

  @override
  String charactersCount(int count) {
    return '$count ตัวอักษร';
  }

  @override
  String get enableFeaturesForBestExperience => 'เปิดใช้งานฟีเจอร์เพื่อประสบการณ์ Omi ที่ดีที่สุดบนอุปกรณ์ของคุณ';

  @override
  String get microphoneAccess => 'การเข้าถึงไมโครโฟน';

  @override
  String get recordAudioConversations => 'บันทึกการสนทนาเสียง';

  @override
  String get microphoneAccessDescription => 'Omi ต้องการการเข้าถึงไมโครโฟนเพื่อบันทึกการสนทนาของคุณและให้การถอดความ';

  @override
  String get screenRecording => 'การบันทึกหน้าจอ';

  @override
  String get captureSystemAudioFromMeetings => 'จับภาพเสียงระบบจากการประชุม';

  @override
  String get screenRecordingDescription =>
      'Omi ต้องการสิทธิ์ในการบันทึกหน้าจอเพื่อจับภาพเสียงระบบจากการประชุมที่ใช้เบราว์เซอร์ของคุณ';

  @override
  String get accessibility => 'การเข้าถึง';

  @override
  String get detectBrowserBasedMeetings => 'ตรวจจับการประชุมที่ใช้เบราว์เซอร์';

  @override
  String get accessibilityDescription =>
      'Omi ต้องการสิทธิ์การเข้าถึงเพื่อตรวจจับเมื่อคุณเข้าร่วมการประชุม Zoom, Meet หรือ Teams ในเบราว์เซอร์ของคุณ';

  @override
  String get pleaseWait => 'กรุณารอสักครู่...';

  @override
  String get joinTheCommunity => 'เข้าร่วมชุมชน!';

  @override
  String get loadingProfile => 'กำลังโหลดโปรไฟล์...';

  @override
  String get profileSettings => 'การตั้งค่าโปรไฟล์';

  @override
  String get noEmailSet => 'ไม่ได้ตั้งค่าอีเมล';

  @override
  String get userIdCopiedToClipboard => 'คัดลอก ID ผู้ใช้แล้ว';

  @override
  String get yourInformation => 'ข้อมูลของคุณ';

  @override
  String get setYourName => 'ตั้งชื่อของคุณ';

  @override
  String get changeYourName => 'เปลี่ยนชื่อของคุณ';

  @override
  String get manageYourOmiPersona => 'จัดการบุคลิกภาพ Omi ของคุณ';

  @override
  String get voiceAndPeople => 'เสียงและบุคคล';

  @override
  String get teachOmiYourVoice => 'สอน Omi เสียงของคุณ';

  @override
  String get tellOmiWhoSaidIt => 'บอก Omi ว่าใครพูด 🗣️';

  @override
  String get payment => 'การชำระเงิน';

  @override
  String get addOrChangeYourPaymentMethod => 'เพิ่มหรือเปลี่ยนวิธีการชำระเงิน';

  @override
  String get preferences => 'การตั้งค่า';

  @override
  String get helpImproveOmiBySharing => 'ช่วยปรับปรุง Omi โดยการแชร์ข้อมูลการวิเคราะห์แบบไม่ระบุตัวตน';

  @override
  String get deleteAccount => 'ลบบัญชี';

  @override
  String get deleteYourAccountAndAllData => 'ลบบัญชีและข้อมูลทั้งหมดของคุณ';

  @override
  String get clearLogs => 'ล้างบันทึก';

  @override
  String get debugLogsCleared => 'ล้างบันทึกการดีบักแล้ว';

  @override
  String get exportConversations => 'ส่งออกการสนทนา';

  @override
  String get exportAllConversationsToJson => 'ส่งออกการสนทนาทั้งหมดของคุณไปยังไฟล์ JSON';

  @override
  String get conversationsExportStarted => 'เริ่มการส่งออกการสนทนาแล้ว อาจใช้เวลาสักครู่ โปรดรอสักครู่';

  @override
  String get mcpDescription =>
      'เพื่อเชื่อมต่อ Omi กับแอปพลิเคชันอื่น ๆ เพื่ออ่าน ค้นหา และจัดการความทรงจำและการสนทนาของคุณ สร้างคีย์เพื่อเริ่มต้น';

  @override
  String get apiKeys => 'คีย์ API';

  @override
  String errorLabel(String error) {
    return 'ข้อผิดพลาด: $error';
  }

  @override
  String get noApiKeysFound => 'ไม่พบคีย์ API สร้างหนึ่งรายการเพื่อเริ่มต้น';

  @override
  String get advancedSettings => 'การตั้งค่าขั้นสูง';

  @override
  String get triggersWhenNewConversationCreated => 'ทริกเกอร์เมื่อสร้างการสนทนาใหม่';

  @override
  String get triggersWhenNewTranscriptReceived => 'ทริกเกอร์เมื่อได้รับการถอดความใหม่';

  @override
  String get realtimeAudioBytes => 'ไบต์เสียงแบบเรียลไทม์';

  @override
  String get triggersWhenAudioBytesReceived => 'ทริกเกอร์เมื่อได้รับไบต์เสียง';

  @override
  String get everyXSeconds => 'ทุก x วินาที';

  @override
  String get triggersWhenDaySummaryGenerated => 'ทริกเกอร์เมื่อสร้างสรุปรายวัน';

  @override
  String get tryLatestExperimentalFeatures => 'ลองใช้คุณสมบัติทดลองล่าสุดจากทีม Omi';

  @override
  String get transcriptionServiceDiagnosticStatus => 'สถานะการวินิจฉัยบริการถอดความ';

  @override
  String get enableDetailedDiagnosticMessages => 'เปิดใช้งานข้อความวินิจฉัยโดยละเอียดจากบริการถอดความ';

  @override
  String get autoCreateAndTagNewSpeakers => 'สร้างและติดแท็กผู้พูดใหม่โดยอัตโนมัติ';

  @override
  String get automaticallyCreateNewPerson => 'สร้างบุคคลใหม่โดยอัตโนมัติเมื่อตรวจพบชื่อในการถอดความ';

  @override
  String get pilotFeatures => 'คุณสมบัตินำร่อง';

  @override
  String get pilotFeaturesDescription => 'คุณสมบัติเหล่านี้เป็นการทดสอบและไม่รับประกันการสนับสนุน';

  @override
  String get suggestFollowUpQuestion => 'แนะนำคำถามติดตาม';

  @override
  String get saveSettings => 'บันทึกการตั้งค่า';

  @override
  String get syncingDeveloperSettings => 'กำลังซิงค์การตั้งค่านักพัฒนา...';

  @override
  String get summary => 'สรุป';

  @override
  String get auto => 'อัตโนมัติ';

  @override
  String get noSummaryForApp => 'ไม่มีสรุปสำหรับแอปนี้ ลองแอปอื่นเพื่อผลลัพธ์ที่ดีกว่า';

  @override
  String get tryAnotherApp => 'ลองแอปอื่น';

  @override
  String generatedBy(String appName) {
    return 'สร้างโดย $appName';
  }

  @override
  String get overview => 'ภาพรวม';

  @override
  String get otherAppResults => 'ผลลัพธ์จากแอปอื่น';

  @override
  String get unknownApp => 'แอปที่ไม่รู้จัก';

  @override
  String get noSummaryAvailable => 'ไม่มีสรุปที่พร้อมใช้งาน';

  @override
  String get conversationNoSummaryYet => 'การสนทนานี้ยังไม่มีสรุป';

  @override
  String get chooseSummarizationApp => 'เลือกแอปสรุป';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return 'ตั้ง $appName เป็นแอปสรุปเริ่มต้น';
  }

  @override
  String get letOmiChooseAutomatically => 'ให้ Omi เลือกแอปที่ดีที่สุดโดยอัตโนมัติ';

  @override
  String get deleteConversationConfirmation => 'คุณแน่ใจหรือไม่ว่าต้องการลบการสนทนานี้? การกระทำนี้ไม่สามารถยกเลิกได้';

  @override
  String get conversationDeleted => 'ลบการสนทนาแล้ว';

  @override
  String get generatingLink => 'กำลังสร้างลิงก์...';

  @override
  String get editConversation => 'แก้ไขการสนทนา';

  @override
  String get conversationLinkCopiedToClipboard => 'คัดลอกลิงก์การสนทนาไปยังคลิปบอร์ดแล้ว';

  @override
  String get conversationTranscriptCopiedToClipboard => 'คัดลอกบันทึกการสนทนาไปยังคลิปบอร์ดแล้ว';

  @override
  String get editConversationDialogTitle => 'แก้ไขการสนทนา';

  @override
  String get changeTheConversationTitle => 'เปลี่ยนชื่อการสนทนา';

  @override
  String get conversationTitle => 'ชื่อการสนทนา';

  @override
  String get enterConversationTitle => 'ป้อนชื่อการสนทนา...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'อัปเดตชื่อการสนทนาเรียบร้อยแล้ว';

  @override
  String get failedToUpdateConversationTitle => 'การอัปเดตชื่อการสนทนาล้มเหลว';

  @override
  String get errorUpdatingConversationTitle => 'เกิดข้อผิดพลาดในการอัปเดตชื่อการสนทนา';

  @override
  String get settingUp => 'กำลังตั้งค่า...';

  @override
  String get startYourFirstRecording => 'เริ่มการบันทึกครั้งแรกของคุณ';

  @override
  String get preparingSystemAudioCapture => 'กำลังเตรียมการจับภาพเสียงของระบบ';

  @override
  String get clickTheButtonToCaptureAudio =>
      'คลิกปุ่มเพื่อจับภาพเสียงสำหรับการถอดความสด ข้อมูลเชิงลึกของ AI และการบันทึกอัตโนมัติ';

  @override
  String get reconnecting => 'กำลังเชื่อมต่อใหม่...';

  @override
  String get recordingPaused => 'การบันทึกหยุดชั่วคราว';

  @override
  String get recordingActive => 'การบันทึกทำงานอยู่';

  @override
  String get startRecording => 'เริ่มการบันทึก';

  @override
  String resumingInCountdown(String countdown) {
    return 'จะดำเนินการต่อใน $countdown วินาที...';
  }

  @override
  String get tapPlayToResume => 'แตะเล่นเพื่อดำเนินการต่อ';

  @override
  String get listeningForAudio => 'กำลังฟังเสียง...';

  @override
  String get preparingAudioCapture => 'กำลังเตรียมการจับภาพเสียง';

  @override
  String get clickToBeginRecording => 'คลิกเพื่อเริ่มการบันทึก';

  @override
  String get translated => 'แปลแล้ว';

  @override
  String get liveTranscript => 'การถอดความสด';

  @override
  String segmentsSingular(String count) {
    return '$count ส่วน';
  }

  @override
  String segmentsPlural(String count) {
    return '$count ส่วน';
  }

  @override
  String get startRecordingToSeeTranscript => 'เริ่มการบันทึกเพื่อดูการถอดความสด';

  @override
  String get paused => 'หยุดชั่วคราว';

  @override
  String get initializing => 'กำลังเริ่มต้น...';

  @override
  String get recording => 'กำลังบันทึก';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'เปลี่ยนไมโครโฟนแล้ว จะดำเนินการต่อใน $countdown วินาที';
  }

  @override
  String get clickPlayToResumeOrStop => 'คลิกเล่นเพื่อดำเนินการต่อหรือหยุดเพื่อเสร็จสิ้น';

  @override
  String get settingUpSystemAudioCapture => 'กำลังตั้งค่าการจับภาพเสียงของระบบ';

  @override
  String get capturingAudioAndGeneratingTranscript => 'กำลังจับภาพเสียงและสร้างการถอดความ';

  @override
  String get clickToBeginRecordingSystemAudio => 'คลิกเพื่อเริ่มการบันทึกเสียงของระบบ';

  @override
  String get you => 'คุณ';

  @override
  String speakerWithId(String speakerId) {
    return 'ผู้พูด $speakerId';
  }

  @override
  String get translatedByOmi => 'แปลโดย omi';

  @override
  String get backToConversations => 'กลับไปที่การสนทนา';

  @override
  String get systemAudio => 'ระบบ';

  @override
  String get mic => 'ไมโครโฟน';

  @override
  String audioInputSetTo(String deviceName) {
    return 'ตั้งค่าอินพุตเสียงเป็น $deviceName';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'เกิดข้อผิดพลาดในการสลับอุปกรณ์เสียง: $error';
  }

  @override
  String get selectAudioInput => 'เลือกอินพุตเสียง';

  @override
  String get loadingDevices => 'กำลังโหลดอุปกรณ์...';

  @override
  String get settingsHeader => 'การตั้งค่า';

  @override
  String get plansAndBilling => 'แผนและการเรียกเก็บเงิน';

  @override
  String get calendarIntegration => 'การรวมปฏิทิน';

  @override
  String get dailySummary => 'สรุปรายวัน';

  @override
  String get developer => 'นักพัฒนา';

  @override
  String get about => 'เกี่ยวกับ';

  @override
  String get selectTime => 'เลือกเวลา';

  @override
  String get accountGroup => 'บัญชี';

  @override
  String get signOutQuestion => 'ออกจากระบบ?';

  @override
  String get signOutConfirmation => 'คุณแน่ใจหรือไม่ว่าต้องการออกจากระบบ?';

  @override
  String get customVocabularyHeader => 'คำศัพท์ที่กำหนดเอง';

  @override
  String get addWordsDescription => 'เพิ่มคำที่ Omi ควรจดจำระหว่างการถอดเสียง';

  @override
  String get enterWordsHint => 'ป้อนคำ (คั่นด้วยเครื่องหมายจุลภาค)';

  @override
  String get dailySummaryHeader => 'สรุปรายวัน';

  @override
  String get dailySummaryTitle => 'สรุปรายวัน';

  @override
  String get dailySummaryDescription => 'รับสรุปการสนทนาประจำวันแบบเฉพาะบุคคลในรูปแบบการแจ้งเตือน';

  @override
  String get deliveryTime => 'เวลาส่ง';

  @override
  String get deliveryTimeDescription => 'เวลาที่จะรับสรุปรายวัน';

  @override
  String get subscription => 'การสมัครสมาชิก';

  @override
  String get viewPlansAndUsage => 'ดูแผนและการใช้งาน';

  @override
  String get viewPlansDescription => 'จัดการการสมัครสมาชิกและดูสถิติการใช้งาน';

  @override
  String get addOrChangePaymentMethod => 'เพิ่มหรือเปลี่ยนวิธีการชำระเงิน';

  @override
  String get displayOptions => 'ตัวเลือกการแสดงผล';

  @override
  String get showMeetingsInMenuBar => 'แสดงการประชุมในแถบเมนู';

  @override
  String get displayUpcomingMeetingsDescription => 'แสดงการประชุมที่กำลังจะมาถึงในแถบเมนู';

  @override
  String get showEventsWithoutParticipants => 'แสดงกิจกรรมที่ไม่มีผู้เข้าร่วม';

  @override
  String get includePersonalEventsDescription => 'รวมกิจกรรมส่วนตัวที่ไม่มีผู้เข้าร่วม';

  @override
  String get upcomingMeetings => 'การประชุมที่กำลังจะมาถึง';

  @override
  String get checkingNext7Days => 'กำลังตรวจสอบ 7 วันถัดไป';

  @override
  String get shortcuts => 'ทางลัด';

  @override
  String get shortcutChangeInstruction => 'คลิกที่ทางลัดเพื่อเปลี่ยน กด Escape เพื่อยกเลิก';

  @override
  String get configurePersonaDescription => 'กำหนดค่าบุคลิกภาพ AI ของคุณ';

  @override
  String get configureSTTProvider => 'กำหนดค่าผู้ให้บริการ STT';

  @override
  String get setConversationEndDescription => 'กำหนดเวลาที่การสนทนาสิ้นสุดโดยอัตโนมัติ';

  @override
  String get importDataDescription => 'นำเข้าข้อมูลจากแหล่งอื่น';

  @override
  String get exportConversationsDescription => 'ส่งออกการสนทนาเป็น JSON';

  @override
  String get exportingConversations => 'กำลังส่งออกการสนทนา...';

  @override
  String get clearNodesDescription => 'ล้างโหนดและการเชื่อมต่อทั้งหมด';

  @override
  String get deleteKnowledgeGraphQuestion => 'ลบกราฟความรู้หรือไม่';

  @override
  String get deleteKnowledgeGraphWarning =>
      'การดำเนินการนี้จะลบข้อมูลกราฟความรู้ที่ได้รับทั้งหมด ความทรงจำต้นฉบับของคุณจะยังคงปลอดภัย';

  @override
  String get connectOmiWithAI => 'เชื่อมต่อ Omi กับผู้ช่วย AI';

  @override
  String get noAPIKeys => 'ไม่มีคีย์ API สร้างหนึ่งรายการเพื่อเริ่มต้น';

  @override
  String get autoCreateWhenDetected => 'สร้างอัตโนมัติเมื่อตรวจพบชื่อ';

  @override
  String get trackPersonalGoals => 'ติดตามเป้าหมายส่วนตัวบนหน้าแรก';

  @override
  String get dailyReflectionDescription => 'รับการเตือนความจำเวลา 21.00 น. เพื่อทบทวนวันของคุณและบันทึกความคิด';

  @override
  String get endpointURL => 'URL ปลายทาง';

  @override
  String get links => 'ลิงก์';

  @override
  String get discordMemberCount => 'สมาชิกกว่า 8000 คนใน Discord';

  @override
  String get userInformation => 'ข้อมูลผู้ใช้';

  @override
  String get capabilities => 'ความสามารถ';

  @override
  String get previewScreenshots => 'ตัวอย่างภาพหน้าจอ';

  @override
  String get holdOnPreparingForm => 'รอสักครู่ เรากำลังเตรียมแบบฟอร์มให้คุณ';

  @override
  String get bySubmittingYouAgreeToOmi => 'การส่งหมายถึงคุณยอมรับ ';

  @override
  String get termsAndPrivacyPolicy => 'ข้อกำหนดและนโยบายความเป็นส่วนตัว';

  @override
  String get helpsDiagnoseIssuesAutoDeletes => 'ช่วยในการวินิจฉัยปัญหา ลบอัตโนมัติหลังจาก 3 วัน';

  @override
  String get manageYourApp => 'จัดการแอปของคุณ';

  @override
  String get updatingYourApp => 'กำลังอัปเดตแอปของคุณ';

  @override
  String get fetchingYourAppDetails => 'กำลังดึงข้อมูลแอปของคุณ';

  @override
  String get updateAppQuestion => 'อัปเดตแอป?';

  @override
  String get updateAppConfirmation => 'คุณแน่ใจหรือไม่ว่าต้องการอัปเดตแอป? การเปลี่ยนแปลงจะมีผลหลังจากทีมของเราตรวจสอบ';

  @override
  String get updateApp => 'อัปเดตแอป';

  @override
  String get createAndSubmitNewApp => 'สร้างและส่งแอปใหม่';

  @override
  String appsCount(String count) {
    return 'แอป ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'แอปส่วนตัว ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'แอปสาธารณะ ($count)';
  }

  @override
  String get newVersionAvailable => 'มีเวอร์ชันใหม่  🎉';

  @override
  String get no => 'ไม่';

  @override
  String get subscriptionCancelledSuccessfully =>
      'ยกเลิกการสมัครสมาชิกสำเร็จ จะยังคงใช้งานได้จนถึงสิ้นสุดรอบบิลปัจจุบัน';

  @override
  String get failedToCancelSubscription => 'ไม่สามารถยกเลิกการสมัครสมาชิกได้ กรุณาลองอีกครั้ง';

  @override
  String get invalidPaymentUrl => 'URL การชำระเงินไม่ถูกต้อง';

  @override
  String get permissionsAndTriggers => 'สิทธิ์และทริกเกอร์';

  @override
  String get chatFeatures => 'คุณสมบัติแชท';

  @override
  String get uninstall => 'ถอนการติดตั้ง';

  @override
  String get installs => 'การติดตั้ง';

  @override
  String get priceLabel => 'ราคา';

  @override
  String get updatedLabel => 'อัปเดตเมื่อ';

  @override
  String get createdLabel => 'สร้างเมื่อ';

  @override
  String get featuredLabel => 'แนะนำ';

  @override
  String get cancelSubscriptionQuestion => 'ยกเลิกการสมัครสมาชิก?';

  @override
  String get cancelSubscriptionConfirmation =>
      'คุณแน่ใจหรือไม่ว่าต้องการยกเลิกการสมัครสมาชิก? คุณจะยังคงเข้าถึงได้จนถึงสิ้นสุดรอบบิลปัจจุบัน';

  @override
  String get cancelSubscriptionButton => 'ยกเลิกการสมัครสมาชิก';

  @override
  String get cancelling => 'กำลังยกเลิก...';

  @override
  String get betaTesterMessage =>
      'คุณเป็นผู้ทดสอบเบต้าของแอปนี้ ยังไม่เปิดให้สาธารณะ จะเปิดให้สาธารณะเมื่อได้รับการอนุมัติ';

  @override
  String get appUnderReviewMessage =>
      'แอปของคุณกำลังอยู่ระหว่างการตรวจสอบและมองเห็นได้เฉพาะคุณ จะเปิดให้สาธารณะเมื่อได้รับการอนุมัติ';

  @override
  String get appRejectedMessage => 'แอปของคุณถูกปฏิเสธ กรุณาอัปเดตรายละเอียดและส่งใหม่เพื่อตรวจสอบ';

  @override
  String get invalidIntegrationUrl => 'URL การผสานรวมไม่ถูกต้อง';

  @override
  String get tapToComplete => 'แตะเพื่อเสร็จสิ้น';

  @override
  String get invalidSetupInstructionsUrl => 'URL คำแนะนำการตั้งค่าไม่ถูกต้อง';

  @override
  String get pushToTalk => 'กดเพื่อพูด';

  @override
  String get summaryPrompt => 'พรอมต์สรุป';

  @override
  String get pleaseSelectARating => 'กรุณาเลือกคะแนน';

  @override
  String get reviewAddedSuccessfully => 'เพิ่มรีวิวสำเร็จ 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'อัปเดตรีวิวสำเร็จ 🚀';

  @override
  String get failedToSubmitReview => 'ส่งรีวิวไม่สำเร็จ กรุณาลองใหม่';

  @override
  String get addYourReview => 'เพิ่มรีวิวของคุณ';

  @override
  String get editYourReview => 'แก้ไขรีวิวของคุณ';

  @override
  String get writeAReviewOptional => 'เขียนรีวิว (ไม่บังคับ)';

  @override
  String get submitReview => 'ส่งรีวิว';

  @override
  String get updateReview => 'อัปเดตรีวิว';

  @override
  String get yourReview => 'รีวิวของคุณ';

  @override
  String get anonymousUser => 'ผู้ใช้นิรนาม';

  @override
  String get issueActivatingApp => 'เกิดปัญหาในการเปิดใช้งานแอปนี้ กรุณาลองอีกครั้ง';

  @override
  String get dataAccessNoticeDescription =>
      'แอปนี้จะเข้าถึงข้อมูลของคุณ Omi AI ไม่รับผิดชอบต่อวิธีการใช้ แก้ไข หรือลบข้อมูลของคุณโดยแอปนี้';

  @override
  String get copyUrl => 'คัดลอก URL';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => 'จ.';

  @override
  String get weekdayTue => 'อ.';

  @override
  String get weekdayWed => 'พ.';

  @override
  String get weekdayThu => 'พฤ.';

  @override
  String get weekdayFri => 'ศ.';

  @override
  String get weekdaySat => 'ส.';

  @override
  String get weekdaySun => 'อา.';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return 'การเชื่อมต่อ $serviceName เร็วๆ นี้';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'ส่งออกไปยัง $platform แล้ว';
  }

  @override
  String get anotherPlatform => 'แพลตฟอร์มอื่น';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'กรุณาเข้าสู่ระบบ $serviceName ในการตั้งค่า > การเชื่อมต่องาน';
  }

  @override
  String addingToService(String serviceName) {
    return 'กำลังเพิ่มไปยัง $serviceName...';
  }

  @override
  String addedToService(String serviceName) {
    return 'เพิ่มไปยัง $serviceName แล้ว';
  }

  @override
  String failedToAddToService(String serviceName) {
    return 'ไม่สามารถเพิ่มไปยัง $serviceName';
  }

  @override
  String get permissionDeniedForAppleReminders => 'ถูกปฏิเสธสิทธิ์สำหรับ Apple Reminders';

  @override
  String failedToCreateApiKey(String error) {
    return 'ไม่สามารถสร้างคีย์ API ของผู้ให้บริการ: $error';
  }

  @override
  String get createAKey => 'สร้างคีย์';

  @override
  String get apiKeyRevokedSuccessfully => 'เพิกถอนคีย์ API สำเร็จ';

  @override
  String failedToRevokeApiKey(String error) {
    return 'ไม่สามารถเพิกถอนคีย์ API: $error';
  }

  @override
  String get omiApiKeys => 'คีย์ API ของ Omi';

  @override
  String get apiKeysDescription =>
      'คีย์ API ใช้สำหรับการยืนยันตัวตนเมื่อแอปของคุณสื่อสารกับเซิร์ฟเวอร์ OMI ช่วยให้แอปพลิเคชันของคุณสร้างความทรงจำและเข้าถึงบริการ OMI อื่นๆ ได้อย่างปลอดภัย';

  @override
  String get aboutOmiApiKeys => 'เกี่ยวกับคีย์ API ของ Omi';

  @override
  String get yourNewKey => 'คีย์ใหม่ของคุณ:';

  @override
  String get copyToClipboard => 'คัดลอกไปยังคลิปบอร์ด';

  @override
  String get pleaseCopyKeyNow => 'กรุณาคัดลอกตอนนี้และจดไว้ในที่ปลอดภัย ';

  @override
  String get willNotSeeAgain => 'คุณจะไม่สามารถดูได้อีก';

  @override
  String get revokeKey => 'เพิกถอนคีย์';

  @override
  String get revokeApiKeyQuestion => 'เพิกถอนคีย์ API?';

  @override
  String get revokeApiKeyWarning =>
      'การดำเนินการนี้ไม่สามารถยกเลิกได้ แอปพลิเคชันใดๆ ที่ใช้คีย์นี้จะไม่สามารถเข้าถึง API ได้อีกต่อไป';

  @override
  String get revoke => 'เพิกถอน';

  @override
  String get whatWouldYouLikeToCreate => 'คุณต้องการสร้างอะไร?';

  @override
  String get createAnApp => 'สร้างแอป';

  @override
  String get createAndShareYourApp => 'สร้างและแชร์แอปของคุณ';

  @override
  String get createMyClone => 'สร้างโคลนของฉัน';

  @override
  String get createYourDigitalClone => 'สร้างโคลนดิจิทัลของคุณ';

  @override
  String get itemApp => 'แอป';

  @override
  String get itemPersona => 'เพอร์โซน่า';

  @override
  String keepItemPublic(String item) {
    return 'เก็บ$itemเป็นสาธารณะ';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return 'ทำให้$itemเป็นสาธารณะ?';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return 'ทำให้$itemเป็นส่วนตัว?';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'หากคุณทำให้$itemเป็นสาธารณะ ทุกคนสามารถใช้งานได้';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'หากคุณทำให้$itemเป็นส่วนตัวตอนนี้ มันจะหยุดทำงานสำหรับทุกคนและจะมองเห็นได้เฉพาะคุณเท่านั้น';
  }

  @override
  String get manageApp => 'จัดการแอป';

  @override
  String get updatePersonaDetails => 'อัปเดตรายละเอียดเพอร์โซน่า';

  @override
  String deleteItemTitle(String item) {
    return 'ลบ$item';
  }

  @override
  String deleteItemQuestion(String item) {
    return 'ลบ$item?';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'คุณแน่ใจหรือไม่ว่าต้องการลบ$itemนี้? การกระทำนี้ไม่สามารถยกเลิกได้';
  }

  @override
  String get revokeKeyQuestion => 'เพิกถอนคีย์?';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'คุณแน่ใจหรือไม่ว่าต้องการเพิกถอนคีย์ \"$keyName\"? การกระทำนี้ไม่สามารถยกเลิกได้';
  }

  @override
  String get createNewKey => 'สร้างคีย์ใหม่';

  @override
  String get keyNameHint => 'เช่น Claude Desktop';

  @override
  String get pleaseEnterAName => 'กรุณากรอกชื่อ';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'ไม่สามารถสร้างคีย์: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'ไม่สามารถสร้างคีย์ได้ กรุณาลองใหม่อีกครั้ง';

  @override
  String get keyCreated => 'สร้างคีย์แล้ว';

  @override
  String get keyCreatedMessage => 'คีย์ใหม่ของคุณถูกสร้างแล้ว กรุณาคัดลอกตอนนี้ คุณจะไม่สามารถดูได้อีก';

  @override
  String get keyWord => 'คีย์';

  @override
  String get externalAppAccess => 'การเข้าถึงแอปภายนอก';

  @override
  String get externalAppAccessDescription =>
      'แอปที่ติดตั้งต่อไปนี้มีการเชื่อมต่อภายนอกและสามารถเข้าถึงข้อมูลของคุณ เช่น การสนทนาและความทรงจำ';

  @override
  String get noExternalAppsHaveAccess => 'ไม่มีแอปภายนอกที่สามารถเข้าถึงข้อมูลของคุณ';

  @override
  String get maximumSecurityE2ee => 'ความปลอดภัยสูงสุด (E2EE)';

  @override
  String get e2eeDescription =>
      'การเข้ารหัสแบบ end-to-end เป็นมาตรฐานทองคำสำหรับความเป็นส่วนตัว เมื่อเปิดใช้งาน ข้อมูลของคุณจะถูกเข้ารหัสบนอุปกรณ์ของคุณก่อนที่จะส่งไปยังเซิร์ฟเวอร์ของเรา ซึ่งหมายความว่าไม่มีใคร แม้แต่ Omi สามารถเข้าถึงเนื้อหาของคุณได้';

  @override
  String get importantTradeoffs => 'ข้อควรพิจารณาที่สำคัญ:';

  @override
  String get e2eeTradeoff1 => '• คุณสมบัติบางอย่าง เช่น การเชื่อมต่อแอปภายนอก อาจถูกปิดใช้งาน';

  @override
  String get e2eeTradeoff2 => '• หากคุณทำรหัสผ่านหาย ข้อมูลของคุณจะไม่สามารถกู้คืนได้';

  @override
  String get featureComingSoon => 'คุณสมบัตินี้จะมาเร็วๆ นี้!';

  @override
  String get migrationInProgressMessage =>
      'การย้ายข้อมูลกำลังดำเนินการ คุณไม่สามารถเปลี่ยนระดับการป้องกันจนกว่าจะเสร็จสิ้น';

  @override
  String get migrationFailed => 'การย้ายข้อมูลล้มเหลว';

  @override
  String migratingFromTo(String source, String target) {
    return 'กำลังย้ายจาก $source ไปยัง $target';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total รายการ';
  }

  @override
  String get secureEncryption => 'การเข้ารหัสที่ปลอดภัย';

  @override
  String get secureEncryptionDescription =>
      'ข้อมูลของคุณถูกเข้ารหัสด้วยคีย์ที่ไม่ซ้ำกันสำหรับคุณบนเซิร์ฟเวอร์ของเรา ซึ่งโฮสต์บน Google Cloud ซึ่งหมายความว่าเนื้อหาดิบของคุณไม่สามารถเข้าถึงได้โดยใครก็ตาม รวมถึงพนักงาน Omi หรือ Google โดยตรงจากฐานข้อมูล';

  @override
  String get endToEndEncryption => 'การเข้ารหัสแบบ end-to-end';

  @override
  String get e2eeCardDescription =>
      'เปิดใช้งานเพื่อความปลอดภัยสูงสุดที่มีเพียงคุณเท่านั้นที่สามารถเข้าถึงข้อมูลของคุณ แตะเพื่อเรียนรู้เพิ่มเติม';

  @override
  String get dataAlwaysEncrypted => 'ไม่ว่าระดับใด ข้อมูลของคุณจะถูกเข้ารหัสเสมอทั้งขณะพักและขณะส่ง';

  @override
  String get readOnlyScope => 'อ่านอย่างเดียว';

  @override
  String get fullAccessScope => 'เข้าถึงเต็มที่';

  @override
  String get readScope => 'อ่าน';

  @override
  String get writeScope => 'เขียน';

  @override
  String get apiKeyCreated => 'สร้างคีย์ API แล้ว!';

  @override
  String get saveKeyWarning => 'บันทึกคีย์นี้ตอนนี้! คุณจะไม่สามารถดูได้อีก';

  @override
  String get yourApiKey => 'คีย์ API ของคุณ';

  @override
  String get tapToCopy => 'แตะเพื่อคัดลอก';

  @override
  String get copyKey => 'คัดลอกคีย์';

  @override
  String get createApiKey => 'สร้างคีย์ API';

  @override
  String get accessDataProgrammatically => 'เข้าถึงข้อมูลของคุณแบบโปรแกรม';

  @override
  String get keyNameLabel => 'ชื่อคีย์';

  @override
  String get keyNamePlaceholder => 'เช่น การเชื่อมต่อแอปของฉัน';

  @override
  String get permissionsLabel => 'สิทธิ์';

  @override
  String get permissionsInfoNote => 'R = อ่าน, W = เขียน ค่าเริ่มต้นเป็นอ่านอย่างเดียวถ้าไม่ได้เลือกอะไร';

  @override
  String get developerApi => 'API นักพัฒนา';

  @override
  String get createAKeyToGetStarted => 'สร้างคีย์เพื่อเริ่มต้น';

  @override
  String errorWithMessage(String error) {
    return 'ข้อผิดพลาด: $error';
  }

  @override
  String get omiTraining => 'การฝึกอบรม Omi';

  @override
  String get trainingDataProgram => 'โปรแกรมข้อมูลการฝึก';

  @override
  String get getOmiUnlimitedFree => 'รับ Omi Unlimited ฟรีโดยการมีส่วนร่วมข้อมูลของคุณเพื่อฝึกโมเดล AI';

  @override
  String get trainingDataBullets =>
      '• ข้อมูลของคุณช่วยปรับปรุงโมเดล AI\n• แชร์เฉพาะข้อมูลที่ไม่ละเอียดอ่อน\n• กระบวนการที่โปร่งใสอย่างสมบูรณ์';

  @override
  String get learnMoreAtOmiTraining => 'เรียนรู้เพิ่มเติมที่ omi.me/training';

  @override
  String get agreeToContributeData => 'ฉันเข้าใจและยินยอมที่จะมีส่วนร่วมข้อมูลของฉันสำหรับการฝึก AI';

  @override
  String get submitRequest => 'ส่งคำขอ';

  @override
  String get thankYouRequestUnderReview =>
      'ขอบคุณ! คำขอของคุณอยู่ระหว่างการตรวจสอบ เราจะแจ้งให้คุณทราบเมื่อได้รับการอนุมัติ';

  @override
  String planRemainsActiveUntil(String date) {
    return 'แพ็คเกจของคุณจะยังคงใช้งานได้จนถึง $date หลังจากนั้น คุณจะสูญเสียการเข้าถึงฟีเจอร์ไม่จำกัด คุณแน่ใจหรือไม่?';
  }

  @override
  String get confirmCancellation => 'ยืนยันการยกเลิก';

  @override
  String get keepMyPlan => 'เก็บแพ็คเกจของฉัน';

  @override
  String get subscriptionSetToCancel => 'การสมัครของคุณถูกตั้งค่าให้ยกเลิกเมื่อสิ้นสุดรอบ';

  @override
  String get switchedToOnDevice => 'เปลี่ยนเป็นการถอดความบนอุปกรณ์';

  @override
  String get couldNotSwitchToFreePlan => 'ไม่สามารถเปลี่ยนเป็นแพ็คเกจฟรีได้ กรุณาลองอีกครั้ง';

  @override
  String get couldNotLoadPlans => 'ไม่สามารถโหลดแพ็คเกจที่มีได้ กรุณาลองอีกครั้ง';

  @override
  String get selectedPlanNotAvailable => 'แพ็คเกจที่เลือกไม่พร้อมใช้งาน กรุณาลองอีกครั้ง';

  @override
  String get upgradeToAnnualPlan => 'อัปเกรดเป็นแพ็คเกจรายปี';

  @override
  String get importantBillingInfo => 'ข้อมูลการเรียกเก็บเงินที่สำคัญ:';

  @override
  String get monthlyPlanContinues => 'แพ็คเกจรายเดือนปัจจุบันของคุณจะดำเนินต่อไปจนถึงสิ้นสุดรอบการเรียกเก็บเงิน';

  @override
  String get paymentMethodCharged =>
      'วิธีการชำระเงินที่มีอยู่ของคุณจะถูกเรียกเก็บโดยอัตโนมัติเมื่อแพ็คเกจรายเดือนของคุณสิ้นสุด';

  @override
  String get annualSubscriptionStarts => 'การสมัครรายปี 12 เดือนของคุณจะเริ่มโดยอัตโนมัติหลังจากการเรียกเก็บเงิน';

  @override
  String get thirteenMonthsCoverage => 'คุณจะได้รับความคุ้มครองรวม 13 เดือน (เดือนปัจจุบัน + 12 เดือนรายปี)';

  @override
  String get confirmUpgrade => 'ยืนยันการอัปเกรด';

  @override
  String get confirmPlanChange => 'ยืนยันการเปลี่ยนแพ็คเกจ';

  @override
  String get confirmAndProceed => 'ยืนยันและดำเนินการต่อ';

  @override
  String get upgradeScheduled => 'กำหนดการอัปเกรด';

  @override
  String get changePlan => 'เปลี่ยนแพ็คเกจ';

  @override
  String get upgradeAlreadyScheduled => 'การอัปเกรดของคุณไปยังแพ็คเกจรายปีถูกกำหนดไว้แล้ว';

  @override
  String get youAreOnUnlimitedPlan => 'คุณอยู่ในแพ็คเกจ Unlimited';

  @override
  String get yourOmiUnleashed => 'Omi ของคุณ ปลดปล่อย ไปสู่ Unlimited เพื่อความเป็นไปได้ไม่สิ้นสุด';

  @override
  String planEndedOn(String date) {
    return 'แพ็คเกจของคุณสิ้นสุดเมื่อ $date\\nสมัครใหม่ตอนนี้ - คุณจะถูกเรียกเก็บเงินทันทีสำหรับรอบการเรียกเก็บเงินใหม่';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'แพ็คเกจของคุณถูกตั้งค่าให้ยกเลิกในวันที่ $date\\nสมัครใหม่ตอนนี้เพื่อรักษาสิทธิประโยชน์ - ไม่มีค่าใช้จ่ายจนถึง $date';
  }

  @override
  String get annualPlanStartsAutomatically => 'แพ็คเกจรายปีของคุณจะเริ่มโดยอัตโนมัติเมื่อแพ็คเกจรายเดือนของคุณสิ้นสุด';

  @override
  String planRenewsOn(String date) {
    return 'แพ็คเกจของคุณต่ออายุในวันที่ $date';
  }

  @override
  String get unlimitedConversations => 'บทสนทนาไม่จำกัด';

  @override
  String get askOmiAnything => 'ถาม Omi อะไรก็ได้เกี่ยวกับชีวิตของคุณ';

  @override
  String get unlockOmiInfiniteMemory => 'ปลดล็อกหน่วยความจำไม่สิ้นสุดของ Omi';

  @override
  String get youreOnAnnualPlan => 'คุณอยู่ในแพ็คเกจรายปี';

  @override
  String get alreadyBestValuePlan => 'คุณมีแพ็คเกจที่คุ้มค่าที่สุดแล้ว ไม่จำเป็นต้องเปลี่ยนแปลง';

  @override
  String get unableToLoadPlans => 'ไม่สามารถโหลดแพ็คเกจได้';

  @override
  String get checkConnectionTryAgain => 'กรุณาตรวจสอบการเชื่อมต่อแล้วลองอีกครั้ง';

  @override
  String get useFreePlan => 'ใช้แพ็คเกจฟรี';

  @override
  String get continueText => 'ดำเนินการต่อ';

  @override
  String get resubscribe => 'สมัครใหม่';

  @override
  String get couldNotOpenPaymentSettings => 'ไม่สามารถเปิดการตั้งค่าการชำระเงินได้ กรุณาลองอีกครั้ง';

  @override
  String get managePaymentMethod => 'จัดการวิธีการชำระเงิน';

  @override
  String get cancelSubscription => 'ยกเลิกการสมัครสมาชิก';

  @override
  String endsOnDate(String date) {
    return 'สิ้นสุดวันที่ $date';
  }

  @override
  String get active => 'ใช้งานอยู่';

  @override
  String get freePlan => 'แพ็คเกจฟรี';

  @override
  String get configure => 'กำหนดค่า';

  @override
  String get privacyInformation => 'ข้อมูลความเป็นส่วนตัว';

  @override
  String get yourPrivacyMattersToUs => 'ความเป็นส่วนตัวของคุณสำคัญสำหรับเรา';

  @override
  String get privacyIntroText =>
      'ที่ Omi เราให้ความสำคัญกับความเป็นส่วนตัวของคุณอย่างจริงจัง เราต้องการมีความโปร่งใสเกี่ยวกับข้อมูลที่เรารวบรวมและวิธีการใช้งาน นี่คือสิ่งที่คุณต้องรู้:';

  @override
  String get whatWeTrack => 'สิ่งที่เราติดตาม';

  @override
  String get anonymityAndPrivacy => 'การไม่เปิดเผยตัวตนและความเป็นส่วนตัว';

  @override
  String get optInAndOptOutOptions => 'ตัวเลือกการเข้าร่วมและไม่เข้าร่วม';

  @override
  String get ourCommitment => 'คำมั่นสัญญาของเรา';

  @override
  String get commitmentText =>
      'เรามุ่งมั่นที่จะใช้ข้อมูลที่เรารวบรวมเพียงเพื่อทำให้ Omi เป็นผลิตภัณฑ์ที่ดีขึ้นสำหรับคุณ ความเป็นส่วนตัวและความไว้วางใจของคุณเป็นสิ่งสำคัญที่สุดสำหรับเรา';

  @override
  String get thankYouText =>
      'ขอบคุณที่เป็นผู้ใช้ที่มีคุณค่าของ Omi หากคุณมีคำถามหรือข้อกังวลใดๆ โปรดติดต่อเราที่ team@basedhardware.com';

  @override
  String get wifiSyncSettings => 'การตั้งค่าการซิงค์ WiFi';

  @override
  String get enterHotspotCredentials => 'ป้อนข้อมูลรับรองฮอตสปอตของโทรศัพท์';

  @override
  String get wifiSyncUsesHotspot =>
      'การซิงค์ WiFi ใช้โทรศัพท์ของคุณเป็นฮอตสปอต ค้นหาชื่อและรหัสผ่านในการตั้งค่า > ฮอตสปอตส่วนตัว';

  @override
  String get hotspotNameSsid => 'ชื่อฮอตสปอต (SSID)';

  @override
  String get exampleIphoneHotspot => 'เช่น iPhone Hotspot';

  @override
  String get password => 'รหัสผ่าน';

  @override
  String get enterHotspotPassword => 'ป้อนรหัสผ่านฮอตสปอต';

  @override
  String get saveCredentials => 'บันทึกข้อมูลรับรอง';

  @override
  String get clearCredentials => 'ล้างข้อมูลรับรอง';

  @override
  String get pleaseEnterHotspotName => 'กรุณาป้อนชื่อฮอตสปอต';

  @override
  String get wifiCredentialsSaved => 'บันทึกข้อมูลรับรอง WiFi แล้ว';

  @override
  String get wifiCredentialsCleared => 'ล้างข้อมูลรับรอง WiFi แล้ว';

  @override
  String summaryGeneratedForDate(String date) {
    return 'สร้างสรุปสำหรับ $date แล้ว';
  }

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'ไม่สามารถสร้างสรุปได้ ตรวจสอบให้แน่ใจว่าคุณมีการสนทนาสำหรับวันนั้น';

  @override
  String get summaryNotFound => 'ไม่พบสรุป';

  @override
  String get yourDaysJourney => 'การเดินทางของวันนี้';

  @override
  String get highlights => 'ไฮไลท์';

  @override
  String get unresolvedQuestions => 'คำถามที่ยังไม่ได้แก้ไข';

  @override
  String get decisions => 'การตัดสินใจ';

  @override
  String get learnings => 'สิ่งที่เรียนรู้';

  @override
  String get autoDeletesAfterThreeDays => 'ลบอัตโนมัติหลัง 3 วัน';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'ลบกราฟความรู้สำเร็จ';

  @override
  String get exportStartedMayTakeFewSeconds => 'เริ่มส่งออกแล้ว อาจใช้เวลาสักครู่...';

  @override
  String get knowledgeGraphDeleteDescription =>
      'การดำเนินการนี้จะลบข้อมูลกราฟความรู้ที่ได้มาทั้งหมด (โหนดและการเชื่อมต่อ) ความทรงจำดั้งเดิมของคุณจะยังคงปลอดภัย กราฟจะถูกสร้างขึ้นใหม่เมื่อเวลาผ่านไปหรือเมื่อมีการร้องขอครั้งต่อไป';

  @override
  String get configureDailySummaryDigest => 'กำหนดค่าสรุปงานประจำวันของคุณ';

  @override
  String accessesDataTypes(String dataTypes) {
    return 'เข้าถึง $dataTypes';
  }

  @override
  String triggeredByType(String triggerType) {
    return 'ทริกเกอร์โดย $triggerType';
  }

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription และ $triggerDescription';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return '$triggerDescription';
  }

  @override
  String get noSpecificDataAccessConfigured => 'ไม่มีการกำหนดค่าการเข้าถึงข้อมูลเฉพาะ';

  @override
  String get basicPlanDescription => '1,200 นาทีพรีเมียม + ไม่จำกัดบนอุปกรณ์';

  @override
  String get minutes => 'นาที';

  @override
  String get omiHas => 'Omi มี:';

  @override
  String get premiumMinutesUsed => 'ใช้นาทีพรีเมียมแล้ว';

  @override
  String get setupOnDevice => 'ตั้งค่าบนอุปกรณ์';

  @override
  String get forUnlimitedFreeTranscription => 'สำหรับการถอดความฟรีไม่จำกัด';

  @override
  String premiumMinsLeft(int count) {
    return 'เหลือ $count นาทีพรีเมียม';
  }

  @override
  String get alwaysAvailable => 'พร้อมใช้งานเสมอ';

  @override
  String get importHistory => 'ประวัติการนำเข้า';

  @override
  String get noImportsYet => 'ยังไม่มีการนำเข้า';

  @override
  String get selectZipFileToImport => 'เลือกไฟล์ .zip เพื่อนำเข้า!';

  @override
  String get otherDevicesComingSoon => 'อุปกรณ์อื่นๆ เร็วๆ นี้';

  @override
  String get deleteAllLimitlessConversations => 'ลบการสนทนา Limitless ทั้งหมด?';

  @override
  String get deleteAllLimitlessWarning =>
      'การดำเนินการนี้จะลบการสนทนาทั้งหมดที่นำเข้าจาก Limitless อย่างถาวร ไม่สามารถยกเลิกการกระทำนี้ได้';

  @override
  String deletedLimitlessConversations(int count) {
    return 'ลบการสนทนา Limitless $count รายการแล้ว';
  }

  @override
  String get failedToDeleteConversations => 'ไม่สามารถลบการสนทนาได้';

  @override
  String get deleteImportedData => 'ลบข้อมูลที่นำเข้า';

  @override
  String get statusPending => 'รอดำเนินการ';

  @override
  String get statusProcessing => 'กำลังประมวลผล';

  @override
  String get statusCompleted => 'เสร็จสิ้น';

  @override
  String get statusFailed => 'ล้มเหลว';

  @override
  String nConversations(int count) {
    return '$count การสนทนา';
  }

  @override
  String get pleaseEnterName => 'กรุณากรอกชื่อ';

  @override
  String get nameMustBeBetweenCharacters => 'ชื่อต้องมีความยาว 2-40 ตัวอักษร';

  @override
  String get deleteSampleQuestion => 'ลบตัวอย่าง?';

  @override
  String deleteSampleConfirmation(String name) {
    return 'คุณแน่ใจหรือไม่ว่าต้องการลบตัวอย่างของ $name?';
  }

  @override
  String get confirmDeletion => 'ยืนยันการลบ';

  @override
  String deletePersonConfirmation(String name) {
    return 'คุณแน่ใจหรือไม่ว่าต้องการลบ $name? การดำเนินการนี้จะลบตัวอย่างเสียงที่เกี่ยวข้องทั้งหมดด้วย';
  }

  @override
  String get howItWorksTitle => 'มันทำงานอย่างไร?';

  @override
  String get howPeopleWorks =>
      'เมื่อสร้างบุคคลแล้ว คุณสามารถไปที่การถอดเสียงบทสนทนาและกำหนดส่วนที่เกี่ยวข้องให้พวกเขา ด้วยวิธีนี้ Omi จะสามารถจดจำเสียงพูดของพวกเขาได้เช่นกัน!';

  @override
  String get tapToDelete => 'แตะเพื่อลบ';

  @override
  String get newTag => 'ใหม่';

  @override
  String get needHelpChatWithUs => 'ต้องการความช่วยเหลือ? แชทกับเรา';

  @override
  String get localStorageEnabled => 'เปิดใช้งานที่เก็บข้อมูลในเครื่องแล้ว';

  @override
  String get localStorageDisabled => 'ปิดใช้งานที่เก็บข้อมูลในเครื่องแล้ว';

  @override
  String failedToUpdateSettings(String error) {
    return 'ไม่สามารถอัปเดตการตั้งค่า: $error';
  }

  @override
  String get privacyNotice => 'ประกาศความเป็นส่วนตัว';

  @override
  String get recordingsMayCaptureOthers =>
      'การบันทึกอาจบันทึกเสียงของผู้อื่น ตรวจสอบให้แน่ใจว่าคุณได้รับความยินยอมจากผู้เข้าร่วมทุกคนก่อนเปิดใช้งาน';

  @override
  String get enable => 'เปิดใช้งาน';

  @override
  String get storeAudioOnPhone => 'จัดเก็บเสียงในโทรศัพท์';

  @override
  String get on => 'เปิด';

  @override
  String get storeAudioDescription =>
      'เก็บการบันทึกเสียงทั้งหมดไว้ในโทรศัพท์ของคุณ เมื่อปิดใช้งาน จะเก็บเฉพาะการอัปโหลดที่ล้มเหลวเพื่อประหยัดพื้นที่';

  @override
  String get enableLocalStorage => 'เปิดใช้งานที่เก็บข้อมูลในเครื่อง';

  @override
  String get cloudStorageEnabled => 'เปิดใช้งานที่เก็บข้อมูลบนคลาวด์แล้ว';

  @override
  String get cloudStorageDisabled => 'ปิดใช้งานที่เก็บข้อมูลบนคลาวด์แล้ว';

  @override
  String get enableCloudStorage => 'เปิดใช้งานที่เก็บข้อมูลบนคลาวด์';

  @override
  String get storeAudioOnCloud => 'จัดเก็บเสียงบนคลาวด์';

  @override
  String get cloudStorageDialogMessage =>
      'การบันทึกแบบเรียลไทม์ของคุณจะถูกเก็บไว้ในที่เก็บข้อมูลคลาวด์ส่วนตัวขณะที่คุณพูด';

  @override
  String get storeAudioCloudDescription =>
      'เก็บการบันทึกแบบเรียลไทม์ของคุณในที่เก็บข้อมูลคลาวด์ส่วนตัวขณะที่คุณพูด เสียงจะถูกบันทึกและบันทึกอย่างปลอดภัยแบบเรียลไทม์';

  @override
  String get downloadingFirmware => 'กำลังดาวน์โหลดเฟิร์มแวร์';

  @override
  String get installingFirmware => 'กำลังติดตั้งเฟิร์มแวร์';

  @override
  String get firmwareUpdateWarning => 'อย่าปิดแอปหรือปิดอุปกรณ์ อาจทำให้อุปกรณ์เสียหายได้';

  @override
  String get firmwareUpdated => 'อัปเดตเฟิร์มแวร์แล้ว';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'กรุณารีสตาร์ท $deviceName ของคุณเพื่อให้การอัปเดตเสร็จสมบูรณ์';
  }

  @override
  String get yourDeviceIsUpToDate => 'อุปกรณ์ของคุณเป็นเวอร์ชันล่าสุดแล้ว';

  @override
  String get currentVersion => 'เวอร์ชันปัจจุบัน';

  @override
  String get latestVersion => 'เวอร์ชันล่าสุด';

  @override
  String get whatsNew => 'มีอะไรใหม่';

  @override
  String get installUpdate => 'ติดตั้งการอัปเดต';

  @override
  String get updateNow => 'อัปเดตตอนนี้';

  @override
  String get updateGuide => 'คู่มือการอัปเดต';

  @override
  String get checkingForUpdates => 'กำลังตรวจสอบการอัปเดต';

  @override
  String get checkingFirmwareVersion => 'กำลังตรวจสอบเวอร์ชันเฟิร์มแวร์...';

  @override
  String get firmwareUpdate => 'อัปเดตเฟิร์มแวร์';

  @override
  String get payments => 'การชำระเงิน';

  @override
  String get connectPaymentMethodInfo => 'เชื่อมต่อวิธีการชำระเงินด้านล่างเพื่อเริ่มรับการจ่ายเงินสำหรับแอปของคุณ';

  @override
  String get selectedPaymentMethod => 'วิธีการชำระเงินที่เลือก';

  @override
  String get availablePaymentMethods => 'วิธีการชำระเงินที่มี';

  @override
  String get activeStatus => 'ใช้งานอยู่';

  @override
  String get connectedStatus => 'เชื่อมต่อแล้ว';

  @override
  String get notConnectedStatus => 'ไม่ได้เชื่อมต่อ';

  @override
  String get setActive => 'ตั้งเป็นใช้งาน';

  @override
  String get getPaidThroughStripe => 'รับเงินจากการขายแอปของคุณผ่าน Stripe';

  @override
  String get monthlyPayouts => 'การจ่ายเงินรายเดือน';

  @override
  String get monthlyPayoutsDescription => 'รับเงินรายเดือนโดยตรงเข้าบัญชีของคุณเมื่อรายได้ถึง \$10';

  @override
  String get secureAndReliable => 'ปลอดภัยและเชื่อถือได้';

  @override
  String get stripeSecureDescription => 'Stripe รับประกันการโอนรายได้จากแอปของคุณอย่างปลอดภัยและตรงเวลา';

  @override
  String get selectYourCountry => 'เลือกประเทศของคุณ';

  @override
  String get countrySelectionPermanent => 'การเลือกประเทศของคุณเป็นการถาวรและไม่สามารถเปลี่ยนแปลงได้ในภายหลัง';

  @override
  String get byClickingConnectNow => 'การคลิก \"เชื่อมต่อตอนนี้\" หมายความว่าคุณยอมรับ';

  @override
  String get stripeConnectedAccountAgreement => 'ข้อตกลงบัญชี Stripe Connected';

  @override
  String get errorConnectingToStripe => 'เกิดข้อผิดพลาดในการเชื่อมต่อกับ Stripe! กรุณาลองใหม่ภายหลัง';

  @override
  String get connectingYourStripeAccount => 'กำลังเชื่อมต่อบัญชี Stripe ของคุณ';

  @override
  String get stripeOnboardingInstructions =>
      'กรุณาดำเนินการลงทะเบียน Stripe ให้เสร็จสิ้นในเบราว์เซอร์ของคุณ หน้านี้จะอัปเดตโดยอัตโนมัติเมื่อเสร็จสิ้น';

  @override
  String get failedTryAgain => 'ล้มเหลว? ลองอีกครั้ง';

  @override
  String get illDoItLater => 'ฉันจะทำทีหลัง';

  @override
  String get successfullyConnected => 'เชื่อมต่อสำเร็จ!';

  @override
  String get stripeReadyForPayments =>
      'บัญชี Stripe ของคุณพร้อมรับการชำระเงินแล้ว คุณสามารถเริ่มสร้างรายได้จากการขายแอปได้ทันที';

  @override
  String get updateStripeDetails => 'อัปเดตรายละเอียด Stripe';

  @override
  String get errorUpdatingStripeDetails => 'เกิดข้อผิดพลาดในการอัปเดตรายละเอียด Stripe! กรุณาลองใหม่ภายหลัง';

  @override
  String get updatePayPal => 'อัปเดต PayPal';

  @override
  String get setUpPayPal => 'ตั้งค่า PayPal';

  @override
  String get updatePayPalAccountDetails => 'อัปเดตรายละเอียดบัญชี PayPal ของคุณ';

  @override
  String get connectPayPalToReceivePayments => 'เชื่อมต่อบัญชี PayPal ของคุณเพื่อเริ่มรับการชำระเงินสำหรับแอปของคุณ';

  @override
  String get paypalEmail => 'อีเมล PayPal';

  @override
  String get paypalMeLink => 'ลิงก์ PayPal.me';

  @override
  String get stripeRecommendation =>
      'หาก Stripe พร้อมใช้งานในประเทศของคุณ เราขอแนะนำอย่างยิ่งให้ใช้เพื่อการจ่ายเงินที่รวดเร็วและง่ายขึ้น';

  @override
  String get updatePayPalDetails => 'อัปเดตรายละเอียด PayPal';

  @override
  String get savePayPalDetails => 'บันทึกรายละเอียด PayPal';

  @override
  String get pleaseEnterPayPalEmail => 'กรุณาใส่อีเมล PayPal ของคุณ';

  @override
  String get pleaseEnterPayPalMeLink => 'กรุณาใส่ลิงก์ PayPal.me ของคุณ';

  @override
  String get doNotIncludeHttpInLink => 'อย่าใส่ http หรือ https หรือ www ในลิงก์';

  @override
  String get pleaseEnterValidPayPalMeLink => 'กรุณาใส่ลิงก์ PayPal.me ที่ถูกต้อง';

  @override
  String get pleaseEnterValidEmail => 'กรุณากรอกที่อยู่อีเมลที่ถูกต้อง';

  @override
  String get syncingYourRecordings => 'กำลังซิงค์การบันทึกของคุณ';

  @override
  String get syncYourRecordings => 'ซิงค์การบันทึกของคุณ';

  @override
  String get syncNow => 'ซิงค์เดี๋ยวนี้';

  @override
  String get error => 'ข้อผิดพลาด';

  @override
  String get speechSamples => 'ตัวอย่างเสียง';

  @override
  String additionalSampleIndex(String index) {
    return 'ตัวอย่างเพิ่มเติม $index';
  }

  @override
  String durationSeconds(String seconds) {
    return 'ระยะเวลา: $seconds วินาที';
  }

  @override
  String get additionalSpeechSampleRemoved => 'ลบตัวอย่างเสียงเพิ่มเติมแล้ว';

  @override
  String get consentDataMessage =>
      'เมื่อดำเนินการต่อ ข้อมูลทั้งหมดที่คุณแชร์กับแอปนี้ (รวมถึงการสนทนา การบันทึก และข้อมูลส่วนบุคคลของคุณ) จะถูกจัดเก็บอย่างปลอดภัยบนเซิร์ฟเวอร์ของเราเพื่อให้ข้อมูลเชิงลึกที่ขับเคลื่อนด้วย AI และเปิดใช้งานฟีเจอร์ทั้งหมดของแอป';

  @override
  String get tasksEmptyStateMessage => 'งานจากการสนทนาของคุณจะปรากฏที่นี่\nแตะ + เพื่อสร้างด้วยตนเอง';

  @override
  String get clearChatAction => 'ล้างแชท';

  @override
  String get enableApps => 'เปิดใช้งานแอป';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => 'แสดงเพิ่มเติม ↓';

  @override
  String get showLess => 'แสดงน้อยลง ↑';

  @override
  String get loadingYourRecording => 'กำลังโหลดการบันทึกของคุณ...';

  @override
  String get photoDiscardedMessage => 'ภาพนี้ถูกละทิ้งเนื่องจากไม่สำคัญ';

  @override
  String get analyzing => 'กำลังวิเคราะห์...';

  @override
  String get searchCountries => 'ค้นหาประเทศ...';

  @override
  String get checkingAppleWatch => 'กำลังตรวจสอบ Apple Watch...';

  @override
  String get installOmiOnAppleWatch => 'ติดตั้ง Omi บน\nApple Watch ของคุณ';

  @override
  String get installOmiOnAppleWatchDescription =>
      'หากต้องการใช้ Apple Watch กับ Omi คุณต้องติดตั้งแอป Omi บนนาฬิกาก่อน';

  @override
  String get openOmiOnAppleWatch => 'เปิด Omi บน\nApple Watch ของคุณ';

  @override
  String get openOmiOnAppleWatchDescription => 'แอป Omi ติดตั้งบน Apple Watch ของคุณแล้ว เปิดแอปแล้วแตะเริ่มต้น';

  @override
  String get openWatchApp => 'เปิดแอป Watch';

  @override
  String get iveInstalledAndOpenedTheApp => 'ฉันได้ติดตั้งและเปิดแอปแล้ว';

  @override
  String get unableToOpenWatchApp =>
      'ไม่สามารถเปิดแอป Apple Watch ได้ กรุณาเปิดแอป Watch บน Apple Watch ด้วยตนเองและติดตั้ง Omi จากส่วน \"แอปที่มี\"';

  @override
  String get appleWatchConnectedSuccessfully => 'เชื่อมต่อ Apple Watch สำเร็จ!';

  @override
  String get appleWatchNotReachable =>
      'ยังไม่สามารถเข้าถึง Apple Watch ได้ โปรดตรวจสอบว่าแอป Omi เปิดอยู่บนนาฬิกาของคุณ';

  @override
  String errorCheckingConnection(String error) {
    return 'เกิดข้อผิดพลาดในการตรวจสอบการเชื่อมต่อ: $error';
  }

  @override
  String get muted => 'ปิดเสียง';

  @override
  String get processNow => 'ประมวลผลเดี๋ยวนี้';

  @override
  String get finishedConversation => 'จบการสนทนา?';

  @override
  String get stopRecordingConfirmation => 'คุณแน่ใจหรือไม่ว่าต้องการหยุดบันทึกและสรุปการสนทนาตอนนี้?';

  @override
  String get conversationEndsManually => 'การสนทนาจะจบลงด้วยตนเองเท่านั้น';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'การสนทนาจะถูกสรุปหลังจาก $minutes นาที$suffix ที่ไม่มีเสียงพูด';
  }

  @override
  String get dontAskAgain => 'ไม่ต้องถามอีก';

  @override
  String get waitingForTranscriptOrPhotos => 'กำลังรอการถอดเสียงหรือรูปภาพ...';

  @override
  String get noSummaryYet => 'ยังไม่มีสรุป';

  @override
  String hints(String text) {
    return 'คำแนะนำ: $text';
  }

  @override
  String get testConversationPrompt => 'ทดสอบพรอมต์การสนทนา';

  @override
  String get prompt => 'พรอมต์';

  @override
  String get result => 'ผลลัพธ์:';

  @override
  String get compareTranscripts => 'เปรียบเทียบการถอดเสียง';

  @override
  String get notHelpful => 'ไม่เป็นประโยชน์';

  @override
  String get exportTasksWithOneTap => 'ส่งออกงานด้วยการแตะครั้งเดียว!';

  @override
  String get inProgress => 'กำลังดำเนินการ';

  @override
  String get photos => 'รูปภาพ';

  @override
  String get rawData => 'ข้อมูลดิบ';

  @override
  String get content => 'เนื้อหา';

  @override
  String get noContentToDisplay => 'ไม่มีเนื้อหาที่จะแสดง';

  @override
  String get noSummary => 'ไม่มีสรุป';

  @override
  String get updateOmiFirmware => 'อัปเดตเฟิร์มแวร์ omi';

  @override
  String get anErrorOccurredTryAgain => 'เกิดข้อผิดพลาด กรุณาลองอีกครั้ง';

  @override
  String get welcomeBackSimple => 'ยินดีต้อนรับกลับ';

  @override
  String get addVocabularyDescription => 'เพิ่มคำที่ Omi ควรจดจำระหว่างการถอดเสียง';

  @override
  String get enterWordsCommaSeparated => 'ป้อนคำ (คั่นด้วยเครื่องหมายจุลภาค)';

  @override
  String get whenToReceiveDailySummary => 'เมื่อใดที่จะรับสรุปประจำวัน';

  @override
  String get checkingNextSevenDays => 'ตรวจสอบ 7 วันข้างหน้า';

  @override
  String failedToDeleteError(String error) {
    return 'ลบไม่สำเร็จ: $error';
  }

  @override
  String get developerApiKeys => 'คีย์ API นักพัฒนา';

  @override
  String get noApiKeysCreateOne => 'ไม่มีคีย์ API สร้างหนึ่งเพื่อเริ่มต้น';

  @override
  String get commandRequired => 'ต้องใช้ ⌘';

  @override
  String get spaceKey => 'Space';

  @override
  String loadMoreRemaining(String count) {
    return 'โหลดเพิ่มเติม (เหลือ $count)';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'ผู้ใช้ระดับ $percentile% แรก';
  }

  @override
  String get wrappedMinutes => 'นาที';

  @override
  String get wrappedConversations => 'บทสนทนา';

  @override
  String get wrappedDaysActive => 'วันที่ใช้งาน';

  @override
  String get wrappedYouTalkedAbout => 'คุณพูดถึง';

  @override
  String get wrappedActionItems => 'งาน';

  @override
  String get wrappedTasksCreated => 'งานที่สร้าง';

  @override
  String get wrappedCompleted => 'เสร็จสิ้น';

  @override
  String wrappedCompletionRate(String rate) {
    return 'อัตราความสำเร็จ $rate%';
  }

  @override
  String get wrappedYourTopDays => 'วันที่ดีที่สุดของคุณ';

  @override
  String get wrappedBestMoments => 'ช่วงเวลาที่ดีที่สุด';

  @override
  String get wrappedMyBuddies => 'เพื่อนของฉัน';

  @override
  String get wrappedCouldntStopTalkingAbout => 'หยุดพูดถึงไม่ได้';

  @override
  String get wrappedShow => 'รายการ';

  @override
  String get wrappedMovie => 'ภาพยนตร์';

  @override
  String get wrappedBook => 'หนังสือ';

  @override
  String get wrappedCelebrity => 'คนดัง';

  @override
  String get wrappedFood => 'อาหาร';

  @override
  String get wrappedMovieRecs => 'แนะนำหนังให้เพื่อน';

  @override
  String get wrappedBiggest => 'ใหญ่ที่สุด';

  @override
  String get wrappedStruggle => 'ความท้าทาย';

  @override
  String get wrappedButYouPushedThrough => 'แต่คุณผ่านมาได้ 💪';

  @override
  String get wrappedWin => 'ชัยชนะ';

  @override
  String get wrappedYouDidIt => 'คุณทำได้! 🎉';

  @override
  String get wrappedTopPhrases => '5 วลียอดนิยม';

  @override
  String get wrappedMins => 'นาที';

  @override
  String get wrappedConvos => 'บทสนทนา';

  @override
  String get wrappedDays => 'วัน';

  @override
  String get wrappedMyBuddiesLabel => 'เพื่อนของฉัน';

  @override
  String get wrappedObsessionsLabel => 'สิ่งที่หมกมุ่น';

  @override
  String get wrappedStruggleLabel => 'ความท้าทาย';

  @override
  String get wrappedWinLabel => 'ชัยชนะ';

  @override
  String get wrappedTopPhrasesLabel => 'วลียอดนิยม';

  @override
  String get wrappedLetsHitRewind => 'มาย้อนกลับไปดู';

  @override
  String get wrappedGenerateMyWrapped => 'สร้าง Wrapped ของฉัน';

  @override
  String get wrappedProcessingDefault => 'กำลังประมวลผล...';

  @override
  String get wrappedCreatingYourStory => 'กำลังสร้าง\nเรื่องราวปี 2025 ของคุณ...';

  @override
  String get wrappedSomethingWentWrong => 'เกิดข้อผิดพลาด\nบางอย่าง';

  @override
  String get wrappedAnErrorOccurred => 'เกิดข้อผิดพลาด';

  @override
  String get wrappedTryAgain => 'ลองอีกครั้ง';

  @override
  String get wrappedNoDataAvailable => 'ไม่มีข้อมูล';

  @override
  String get wrappedOmiLifeRecap => 'สรุปชีวิต Omi';

  @override
  String get wrappedSwipeUpToBegin => 'ปัดขึ้นเพื่อเริ่ม';

  @override
  String get wrappedShareText => 'ปี 2025 ของฉัน จดจำโดย Omi ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare => 'แชร์ไม่สำเร็จ กรุณาลองอีกครั้ง';

  @override
  String get wrappedFailedToStartGeneration => 'เริ่มสร้างไม่สำเร็จ กรุณาลองอีกครั้ง';

  @override
  String get wrappedStarting => 'กำลังเริ่ม...';

  @override
  String get wrappedShare => 'แชร์';

  @override
  String get wrappedShareYourWrapped => 'แชร์ Wrapped ของคุณ';

  @override
  String get wrappedMy2025 => 'ปี 2025 ของฉัน';

  @override
  String get wrappedRememberedByOmi => 'จดจำโดย Omi';

  @override
  String get wrappedMostFunDay => 'สนุกที่สุด';

  @override
  String get wrappedMostProductiveDay => 'มีประสิทธิภาพที่สุด';

  @override
  String get wrappedMostIntenseDay => 'เข้มข้นที่สุด';

  @override
  String get wrappedFunniestMoment => 'ตลกที่สุด';

  @override
  String get wrappedMostCringeMoment => 'น่าอายที่สุด';

  @override
  String get wrappedMinutesLabel => 'นาที';

  @override
  String get wrappedConversationsLabel => 'บทสนทนา';

  @override
  String get wrappedDaysActiveLabel => 'วันที่ใช้งาน';

  @override
  String get wrappedTasksGenerated => 'งานที่สร้าง';

  @override
  String get wrappedTasksCompleted => 'งานที่เสร็จ';

  @override
  String get wrappedTopFivePhrases => '5 วลียอดนิยม';

  @override
  String get wrappedAGreatDay => 'วันที่ยอดเยี่ยม';

  @override
  String get wrappedGettingItDone => 'ทำให้สำเร็จ';

  @override
  String get wrappedAChallenge => 'ความท้าทาย';

  @override
  String get wrappedAHilariousMoment => 'ช่วงเวลาตลก';

  @override
  String get wrappedThatAwkwardMoment => 'ช่วงเวลาน่าอาย';

  @override
  String get wrappedYouHadFunnyMoments => 'คุณมีช่วงเวลาตลกปีนี้!';

  @override
  String get wrappedWeveAllBeenThere => 'เราทุกคนเคยผ่านมา!';

  @override
  String get wrappedFriend => 'เพื่อน';

  @override
  String get wrappedYourBuddy => 'เพื่อนของคุณ!';

  @override
  String get wrappedNotMentioned => 'ไม่ได้กล่าวถึง';

  @override
  String get wrappedTheHardPart => 'ส่วนที่ยาก';

  @override
  String get wrappedPersonalGrowth => 'การเติบโตส่วนบุคคล';

  @override
  String get wrappedFunDay => 'สนุก';

  @override
  String get wrappedProductiveDay => 'มีประสิทธิภาพ';

  @override
  String get wrappedIntenseDay => 'เข้มข้น';

  @override
  String get wrappedFunnyMomentTitle => 'ช่วงเวลาตลก';

  @override
  String get wrappedCringeMomentTitle => 'ช่วงเวลาน่าอาย';

  @override
  String get wrappedYouTalkedAboutBadge => 'คุณพูดถึง';

  @override
  String get wrappedCompletedLabel => 'เสร็จสิ้น';

  @override
  String get wrappedMyBuddiesCard => 'เพื่อนของฉัน';

  @override
  String get wrappedBuddiesLabel => 'เพื่อน';

  @override
  String get wrappedObsessionsLabelUpper => 'ความหลงใหล';

  @override
  String get wrappedStruggleLabelUpper => 'ความท้าทาย';

  @override
  String get wrappedWinLabelUpper => 'ชัยชนะ';

  @override
  String get wrappedTopPhrasesLabelUpper => 'วลียอดนิยม';

  @override
  String get wrappedYourHeader => 'วันที่ดีที่สุด';

  @override
  String get wrappedTopDaysHeader => 'ของคุณ';

  @override
  String get wrappedYourTopDaysBadge => 'วันที่ดีที่สุดของคุณ';

  @override
  String get wrappedBestHeader => 'ดีที่สุด';

  @override
  String get wrappedMomentsHeader => 'ช่วงเวลา';

  @override
  String get wrappedBestMomentsBadge => 'ช่วงเวลาดีที่สุด';

  @override
  String get wrappedBiggestHeader => 'ใหญ่ที่สุด';

  @override
  String get wrappedStruggleHeader => 'ความท้าทาย';

  @override
  String get wrappedWinHeader => 'ชัยชนะ';

  @override
  String get wrappedButYouPushedThroughEmoji => 'แต่คุณผ่านมาได้ 💪';

  @override
  String get wrappedYouDidItEmoji => 'คุณทำได้! 🎉';

  @override
  String get wrappedHours => 'ชั่วโมง';

  @override
  String get wrappedActions => 'การกระทำ';

  @override
  String get multipleSpeakersDetected => 'ตรวจพบผู้พูดหลายคน';

  @override
  String get multipleSpeakersDescription =>
      'ดูเหมือนว่าจะมีผู้พูดหลายคนในการบันทึก กรุณาตรวจสอบว่าคุณอยู่ในที่เงียบและลองอีกครั้ง';

  @override
  String get invalidRecordingDetected => 'ตรวจพบการบันทึกที่ไม่ถูกต้อง';

  @override
  String get notEnoughSpeechDescription => 'ตรวจไม่พบคำพูดเพียงพอ กรุณาพูดมากขึ้นและลองอีกครั้ง';

  @override
  String get speechDurationDescription => 'กรุณาตรวจสอบว่าคุณพูดอย่างน้อย 5 วินาทีและไม่เกิน 90 วินาที';

  @override
  String get connectionLostDescription =>
      'การเชื่อมต่อถูกขัดจังหวะ กรุณาตรวจสอบการเชื่อมต่ออินเทอร์เน็ตของคุณและลองอีกครั้ง';

  @override
  String get howToTakeGoodSample => 'วิธีการทำตัวอย่างที่ดี?';

  @override
  String get goodSampleInstructions =>
      '1. ตรวจสอบว่าคุณอยู่ในที่เงียบ\n2. พูดชัดเจนและเป็นธรรมชาติ\n3. ตรวจสอบว่าอุปกรณ์ของคุณอยู่ในตำแหน่งธรรมชาติบนคอของคุณ\n\nเมื่อสร้างแล้ว คุณสามารถปรับปรุงหรือทำใหม่ได้เสมอ';

  @override
  String get noDeviceConnectedUseMic => 'ไม่มีอุปกรณ์ที่เชื่อมต่อ จะใช้ไมโครโฟนของโทรศัพท์';

  @override
  String get doItAgain => 'ทำอีกครั้ง';

  @override
  String get listenToSpeechProfile => 'ฟังโปรไฟล์เสียงของฉัน ➡️';

  @override
  String get recognizingOthers => 'การจดจำผู้อื่น 👀';

  @override
  String get keepGoingGreat => 'ทำต่อไป คุณทำได้ดีมาก';

  @override
  String get somethingWentWrongTryAgain => 'เกิดข้อผิดพลาด! กรุณาลองใหม่อีกครั้งในภายหลัง';

  @override
  String get uploadingVoiceProfile => 'กำลังอัปโหลดโปรไฟล์เสียงของคุณ....';

  @override
  String get memorizingYourVoice => 'กำลังจดจำเสียงของคุณ...';

  @override
  String get personalizingExperience => 'กำลังปรับแต่งประสบการณ์ของคุณ...';

  @override
  String get keepSpeakingUntil100 => 'พูดต่อไปจนกว่าจะถึง 100%';

  @override
  String get greatJobAlmostThere => 'ทำได้ดีมาก ใกล้เสร็จแล้ว';

  @override
  String get soCloseJustLittleMore => 'ใกล้มากแล้ว อีกนิดเดียว';

  @override
  String get notificationFrequency => 'ความถี่การแจ้งเตือน';

  @override
  String get controlNotificationFrequency => 'ควบคุมความถี่ที่ Omi ส่งการแจ้งเตือนเชิงรุกให้คุณ';

  @override
  String get yourScore => 'คะแนนของคุณ';

  @override
  String get dailyScoreBreakdown => 'รายละเอียดคะแนนประจำวัน';

  @override
  String get todaysScore => 'คะแนนวันนี้';

  @override
  String get tasksCompleted => 'งานที่เสร็จแล้ว';

  @override
  String get completionRate => 'อัตราความสำเร็จ';

  @override
  String get howItWorks => 'วิธีการทำงาน';

  @override
  String get dailyScoreExplanation => 'คะแนนประจำวันของคุณขึ้นอยู่กับการทำงานเสร็จ ทำงานให้เสร็จเพื่อเพิ่มคะแนน!';

  @override
  String get notificationFrequencyDescription => 'ควบคุมความถี่ที่ Omi ส่งการแจ้งเตือนเชิงรุกและการเตือนความจำให้คุณ';

  @override
  String get sliderOff => 'ปิด';

  @override
  String get sliderMax => 'สูงสุด';

  @override
  String summaryGeneratedFor(String date) {
    return 'สร้างสรุปสำหรับ $date';
  }

  @override
  String get failedToGenerateSummary => 'ไม่สามารถสร้างสรุปได้ ตรวจสอบให้แน่ใจว่าคุณมีการสนทนาในวันนั้น';

  @override
  String get recap => 'สรุป';

  @override
  String deleteQuoted(String name) {
    return 'ลบ \"$name\"';
  }

  @override
  String moveConversationsTo(int count) {
    return 'ย้าย $count การสนทนาไปที่:';
  }

  @override
  String get noFolder => 'ไม่มีโฟลเดอร์';

  @override
  String get removeFromAllFolders => 'ลบออกจากทุกโฟลเดอร์';

  @override
  String get buildAndShareYourCustomApp => 'สร้างและแชร์แอปที่กำหนดเอง';

  @override
  String get searchAppsPlaceholder => 'ค้นหาใน 1500+ แอป';

  @override
  String get filters => 'ตัวกรอง';

  @override
  String get frequencyOff => 'ปิด';

  @override
  String get frequencyMinimal => 'น้อยที่สุด';

  @override
  String get frequencyLow => 'ต่ำ';

  @override
  String get frequencyBalanced => 'สมดุล';

  @override
  String get frequencyHigh => 'สูง';

  @override
  String get frequencyMaximum => 'สูงสุด';

  @override
  String get frequencyDescOff => 'ไม่มีการแจ้งเตือนเชิงรุก';

  @override
  String get frequencyDescMinimal => 'เฉพาะการเตือนที่สำคัญ';

  @override
  String get frequencyDescLow => 'เฉพาะการอัปเดตที่สำคัญ';

  @override
  String get frequencyDescBalanced => 'การเตือนที่มีประโยชน์เป็นประจำ';

  @override
  String get frequencyDescHigh => 'การตรวจสอบบ่อยครั้ง';

  @override
  String get frequencyDescMaximum => 'ติดต่ออยู่เสมอ';

  @override
  String get clearChatQuestion => 'ล้างแชท?';

  @override
  String get syncingMessages => 'กำลังซิงค์ข้อความกับเซิร์ฟเวอร์...';

  @override
  String get chatAppsTitle => 'แอปแชท';

  @override
  String get selectApp => 'เลือกแอป';

  @override
  String get noChatAppsEnabled => 'ไม่มีแอปแชทที่เปิดใช้งาน\nแตะ \"เปิดใช้งานแอป\" เพื่อเพิ่ม';

  @override
  String get disable => 'ปิดใช้งาน';

  @override
  String get photoLibrary => 'คลังภาพ';

  @override
  String get chooseFile => 'เลือกไฟล์';

  @override
  String get configureAiPersona => 'ตั้งค่าบุคลิก AI ของคุณ';

  @override
  String get connectAiAssistantsToYourData => 'เชื่อมต่อผู้ช่วย AI กับข้อมูลของคุณ';

  @override
  String get oAuth => 'OAuth';

  @override
  String get trackYourGoalsOnHomepage => 'ติดตามเป้าหมายส่วนตัวของคุณบนหน้าหลัก';

  @override
  String get deleteRecording => 'ลบการบันทึก';

  @override
  String get thisCannotBeUndone => 'การดำเนินการนี้ไม่สามารถยกเลิกได้';

  @override
  String get sdCard => 'SD Card';

  @override
  String get fromSd => 'จาก SD';

  @override
  String get limitless => 'Limitless';

  @override
  String get fastTransfer => 'การถ่ายโอนเร็ว';

  @override
  String get syncingStatus => 'กำลังซิงค์';

  @override
  String get failedStatus => 'ล้มเหลว';

  @override
  String etaLabel(String time) {
    return 'ETA: $time';
  }

  @override
  String get transferMethod => 'วิธีการถ่ายโอน';

  @override
  String get fast => 'เร็ว';

  @override
  String get ble => 'BLE';

  @override
  String get phone => 'โทรศัพท์';

  @override
  String get cancelSync => 'ยกเลิกการซิงค์';

  @override
  String get cancelSyncMessage => 'ข้อมูลที่ดาวน์โหลดแล้วจะถูกบันทึกไว้ คุณสามารถดำเนินการต่อได้ภายหลัง';

  @override
  String get syncCancelled => 'ยกเลิกการซิงค์แล้ว';

  @override
  String get deleteProcessedFiles => 'ลบไฟล์ที่ประมวลผลแล้ว';

  @override
  String get processedFilesDeleted => 'ลบไฟล์ที่ประมวลผลแล้ว';

  @override
  String get wifiEnableFailed => 'ไม่สามารถเปิด WiFi บนอุปกรณ์ได้ กรุณาลองอีกครั้ง';

  @override
  String get deviceNoFastTransfer => 'อุปกรณ์ของคุณไม่รองรับการถ่ายโอนเร็ว ใช้ Bluetooth แทน';

  @override
  String get enableHotspotMessage => 'กรุณาเปิดฮอตสปอตของโทรศัพท์แล้วลองอีกครั้ง';

  @override
  String get transferStartFailed => 'ไม่สามารถเริ่มการถ่ายโอนได้ กรุณาลองอีกครั้ง';

  @override
  String get deviceNotResponding => 'อุปกรณ์ไม่ตอบสนอง กรุณาลองอีกครั้ง';

  @override
  String get invalidWifiCredentials => 'ข้อมูลรับรอง WiFi ไม่ถูกต้อง ตรวจสอบการตั้งค่าฮอตสปอต';

  @override
  String get wifiConnectionFailed => 'การเชื่อมต่อ WiFi ล้มเหลว กรุณาลองอีกครั้ง';

  @override
  String get sdCardProcessing => 'กำลังประมวลผล SD Card';

  @override
  String sdCardProcessingMessage(int count) {
    return 'กำลังประมวลผล $count การบันทึก ไฟล์จะถูกลบออกจาก SD card หลังจากนั้น';
  }

  @override
  String get process => 'ประมวลผล';

  @override
  String get wifiSyncFailed => 'การซิงค์ WiFi ล้มเหลว';

  @override
  String get processingFailed => 'การประมวลผลล้มเหลว';

  @override
  String get downloadingFromSdCard => 'กำลังดาวน์โหลดจาก SD Card';

  @override
  String processingProgress(int current, int total) {
    return 'กำลังประมวลผล $current/$total';
  }

  @override
  String conversationsCreated(int count) {
    return 'สร้าง $count บทสนทนาแล้ว';
  }

  @override
  String get internetRequired => 'ต้องมีอินเทอร์เน็ต';

  @override
  String get processAudio => 'ประมวลผลเสียง';

  @override
  String get start => 'เริ่ม';

  @override
  String get noRecordings => 'ไม่มีการบันทึก';

  @override
  String get audioFromOmiWillAppearHere => 'เสียงจากอุปกรณ์ Omi ของคุณจะปรากฏที่นี่';

  @override
  String get deleteProcessed => 'ลบที่ประมวลผลแล้ว';

  @override
  String get tryDifferentFilter => 'ลองใช้ตัวกรองอื่น';

  @override
  String get recordings => 'การบันทึก';

  @override
  String get enableRemindersAccess => 'กรุณาเปิดใช้งานการเข้าถึงการเตือนในการตั้งค่าเพื่อใช้การเตือนของ Apple';

  @override
  String todayAtTime(String time) {
    return 'วันนี้ เวลา $time';
  }

  @override
  String yesterdayAtTime(String time) {
    return 'เมื่อวาน เวลา $time';
  }

  @override
  String get lessThanAMinute => 'น้อยกว่าหนึ่งนาที';

  @override
  String estimatedMinutes(int count) {
    return '~$count นาที';
  }

  @override
  String estimatedHours(int count) {
    return '~$count ชั่วโมง';
  }

  @override
  String estimatedTimeRemaining(String time) {
    return 'โดยประมาณ: เหลือ $time';
  }

  @override
  String get summarizingConversation => 'กำลังสรุปการสนทนา...\nอาจใช้เวลาสักครู่';

  @override
  String get resummarizingConversation => 'กำลังสรุปการสนทนาใหม่...\nอาจใช้เวลาสักครู่';

  @override
  String get nothingInterestingRetry => 'ไม่พบสิ่งที่น่าสนใจ\nต้องการลองอีกครั้งไหม?';

  @override
  String get noSummaryForConversation => 'ไม่มีสรุป\nสำหรับการสนทนานี้';

  @override
  String get unknownLocation => 'ตำแหน่งที่ไม่รู้จัก';

  @override
  String get couldNotLoadMap => 'ไม่สามารถโหลดแผนที่ได้';

  @override
  String get triggerConversationIntegration => 'เรียกใช้การผสานการสร้างการสนทนา';

  @override
  String get webhookUrlNotSet => 'ยังไม่ได้ตั้งค่า Webhook URL';

  @override
  String get setWebhookUrlInSettings => 'กรุณาตั้งค่า webhook URL ในการตั้งค่านักพัฒนาเพื่อใช้ฟีเจอร์นี้';

  @override
  String get sendWebUrl => 'ส่ง URL เว็บ';

  @override
  String get sendTranscript => 'ส่งบทถอดความ';

  @override
  String get sendSummary => 'ส่งสรุป';

  @override
  String get debugModeDetected => 'ตรวจพบโหมดดีบัก';

  @override
  String get performanceReduced => 'ประสิทธิภาพอาจลดลง';

  @override
  String autoClosingInSeconds(int seconds) {
    return 'ปิดอัตโนมัติใน $seconds วินาที';
  }

  @override
  String get modelRequired => 'ต้องการโมเดล';

  @override
  String get downloadWhisperModel => 'ดาวน์โหลดโมเดล whisper เพื่อใช้การถอดความบนอุปกรณ์';

  @override
  String get deviceNotCompatible => 'อุปกรณ์ของคุณไม่รองรับการถอดความบนอุปกรณ์';

  @override
  String get deviceRequirements => 'อุปกรณ์ของคุณไม่ตรงตามข้อกำหนดสำหรับการถอดเสียงบนอุปกรณ์';

  @override
  String get willLikelyCrash => 'การเปิดใช้งานนี้อาจทำให้แอปหยุดทำงานหรือค้าง';

  @override
  String get transcriptionSlowerLessAccurate => 'การถอดความจะช้าลงอย่างมากและแม่นยำน้อยลง';

  @override
  String get proceedAnyway => 'ดำเนินการต่อ';

  @override
  String get olderDeviceDetected => 'ตรวจพบอุปกรณ์รุ่นเก่า';

  @override
  String get onDeviceSlower => 'การถอดเสียงบนอุปกรณ์อาจช้ากว่าบนอุปกรณ์นี้';

  @override
  String get batteryUsageHigher => 'การใช้แบตเตอรี่จะสูงกว่าการถอดความบนคลาวด์';

  @override
  String get considerOmiCloud => 'พิจารณาใช้ Omi Cloud เพื่อประสิทธิภาพที่ดีขึ้น';

  @override
  String get highResourceUsage => 'การใช้ทรัพยากรสูง';

  @override
  String get onDeviceIntensive => 'การถอดเสียงบนอุปกรณ์ต้องใช้การประมวลผลสูง';

  @override
  String get batteryDrainIncrease => 'การใช้แบตเตอรี่จะเพิ่มขึ้นอย่างมาก';

  @override
  String get deviceMayWarmUp => 'อุปกรณ์อาจร้อนขึ้นระหว่างการใช้งานเป็นเวลานาน';

  @override
  String get speedAccuracyLower => 'ความเร็วและความแม่นยำอาจต่ำกว่าโมเดลคลาวด์';

  @override
  String get cloudProvider => 'ผู้ให้บริการคลาวด์';

  @override
  String get premiumMinutesInfo => '1,200 นาทีพรีเมียม/เดือน แท็บบนอุปกรณ์มีการถอดเสียงฟรีไม่จำกัด';

  @override
  String get viewUsage => 'ดูการใช้งาน';

  @override
  String get localProcessingInfo =>
      'เสียงถูกประมวลผลในเครื่อง ใช้งานออฟไลน์ได้ เป็นส่วนตัวมากขึ้น แต่ใช้แบตเตอรี่มากขึ้น';

  @override
  String get model => 'โมเดล';

  @override
  String get performanceWarning => 'คำเตือนเกี่ยวกับประสิทธิภาพ';

  @override
  String get largeModelWarning =>
      'โมเดลนี้มีขนาดใหญ่และอาจทำให้แอปขัดข้องหรือทำงานช้ามากบนอุปกรณ์มือถือ\n\nแนะนำให้ใช้ \"small\" หรือ \"base\"';

  @override
  String get usingNativeIosSpeech => 'ใช้การรู้จำเสียง iOS แบบเนทีฟ';

  @override
  String get noModelDownloadRequired => 'จะใช้เอนจินเสียงดั้งเดิมของอุปกรณ์ ไม่ต้องดาวน์โหลดโมเดล';

  @override
  String get modelReady => 'โมเดลพร้อมใช้งาน';

  @override
  String get redownload => 'ดาวน์โหลดอีกครั้ง';

  @override
  String get doNotCloseApp => 'กรุณาอย่าปิดแอป';

  @override
  String get downloading => 'กำลังดาวน์โหลด...';

  @override
  String get downloadModel => 'ดาวน์โหลดโมเดล';

  @override
  String estimatedSize(String size) {
    return 'ขนาดโดยประมาณ: ~$size MB';
  }

  @override
  String availableSpace(String space) {
    return 'พื้นที่ว่าง: $space';
  }

  @override
  String get notEnoughSpace => 'คำเตือน: พื้นที่ไม่เพียงพอ!';

  @override
  String get download => 'ดาวน์โหลด';

  @override
  String downloadError(String error) {
    return 'ข้อผิดพลาดในการดาวน์โหลด: $error';
  }

  @override
  String get cancelled => 'ยกเลิกแล้ว';

  @override
  String get deviceNotCompatibleTitle => 'อุปกรณ์ไม่รองรับ';

  @override
  String get deviceNotMeetRequirements => 'อุปกรณ์ของคุณไม่ตรงตามข้อกำหนดสำหรับการถอดความบนอุปกรณ์';

  @override
  String get transcriptionSlowerOnDevice => 'การถอดความบนอุปกรณ์อาจช้ากว่าบนอุปกรณ์นี้';

  @override
  String get computationallyIntensive => 'การถอดความบนอุปกรณ์ต้องการการประมวลผลสูง';

  @override
  String get batteryDrainSignificantly => 'การใช้แบตเตอรี่จะเพิ่มขึ้นอย่างมาก';

  @override
  String get premiumMinutesMonth => '1,200 นาทีพรีเมียม/เดือน แท็บบนอุปกรณ์ให้การถอดความฟรีไม่จำกัด ';

  @override
  String get audioProcessedLocally =>
      'เสียงถูกประมวลผลในเครื่อง ใช้งานแบบออฟไลน์ได้ มีความเป็นส่วนตัวมากขึ้น แต่ใช้แบตเตอรี่มากขึ้น';

  @override
  String get languageLabel => 'ภาษา';

  @override
  String get modelLabel => 'โมเดล';

  @override
  String get modelTooLargeWarning =>
      'โมเดลนี้มีขนาดใหญ่และอาจทำให้แอปหยุดทำงานหรือทำงานช้ามากบนอุปกรณ์มือถือ\n\nแนะนำให้ใช้ small หรือ base';

  @override
  String get nativeEngineNoDownload => 'จะใช้เอนจินเสียงแบบเนทีฟของอุปกรณ์ ไม่ต้องดาวน์โหลดโมเดล';

  @override
  String modelReadyWithName(String model) {
    return 'โมเดลพร้อม ($model)';
  }

  @override
  String get reDownload => 'ดาวน์โหลดอีกครั้ง';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return 'กำลังดาวน์โหลด $model: $received / $total MB';
  }

  @override
  String preparingModel(String model) {
    return 'กำลังเตรียม $model...';
  }

  @override
  String downloadErrorWithMessage(String error) {
    return 'ข้อผิดพลาดในการดาวน์โหลด: $error';
  }

  @override
  String estimatedSizeWithValue(String size) {
    return 'ขนาดโดยประมาณ: ~$size MB';
  }

  @override
  String availableSpaceWithValue(String space) {
    return 'พื้นที่ว่าง: $space';
  }

  @override
  String get omiTranscriptionOptimized =>
      'การถอดความสดในตัวของ Omi ถูกปรับให้เหมาะสมสำหรับการสนทนาแบบเรียลไทม์พร้อมการตรวจจับผู้พูดอัตโนมัติและการแยกผู้พูด';

  @override
  String get reset => 'รีเซ็ต';

  @override
  String get useTemplateFrom => 'ใช้เทมเพลตจาก';

  @override
  String get selectProviderTemplate => 'เลือกเทมเพลตผู้ให้บริการ...';

  @override
  String get quicklyPopulateResponse => 'เติมอย่างรวดเร็วด้วยรูปแบบการตอบกลับของผู้ให้บริการที่รู้จัก';

  @override
  String get quicklyPopulateRequest => 'เติมอย่างรวดเร็วด้วยรูปแบบคำขอของผู้ให้บริการที่รู้จัก';

  @override
  String get invalidJsonError => 'JSON ไม่ถูกต้อง';

  @override
  String downloadModelWithName(String model) {
    return 'ดาวน์โหลดโมเดล ($model)';
  }

  @override
  String modelNameWithFile(String model) {
    return 'โมเดล: $model';
  }

  @override
  String get device => 'อุปกรณ์';

  @override
  String get chatAssistantsTitle => 'ผู้ช่วยแชท';

  @override
  String get permissionReadConversations => 'อ่านการสนทนา';

  @override
  String get permissionReadMemories => 'อ่านความทรงจำ';

  @override
  String get permissionReadTasks => 'อ่านงาน';

  @override
  String get permissionCreateConversations => 'สร้างการสนทนา';

  @override
  String get permissionCreateMemories => 'สร้างความทรงจำ';

  @override
  String get permissionTypeAccess => 'การเข้าถึง';

  @override
  String get permissionTypeCreate => 'สร้าง';

  @override
  String get permissionTypeTrigger => 'ทริกเกอร์';

  @override
  String get permissionDescReadConversations => 'แอปนี้สามารถเข้าถึงการสนทนาของคุณได้';

  @override
  String get permissionDescReadMemories => 'แอปนี้สามารถเข้าถึงความทรงจำของคุณได้';

  @override
  String get permissionDescReadTasks => 'แอปนี้สามารถเข้าถึงงานของคุณได้';

  @override
  String get permissionDescCreateConversations => 'แอปนี้สามารถสร้างการสนทนาใหม่ได้';

  @override
  String get permissionDescCreateMemories => 'แอปนี้สามารถสร้างความทรงจำใหม่ได้';

  @override
  String get realtimeListening => 'การฟังแบบเรียลไทม์';

  @override
  String get setupCompleted => 'เสร็จสิ้น';

  @override
  String get pleaseSelectRating => 'กรุณาเลือกคะแนน';

  @override
  String get writeReviewOptional => 'เขียนรีวิว (ไม่บังคับ)';

  @override
  String get setupQuestionsIntro => 'ตอบคำถามสักสองสามข้อเพื่อปรับแต่งประสบการณ์ของคุณ';

  @override
  String get setupQuestionProfession => '1. คุณทำอาชีพอะไร?';

  @override
  String get setupQuestionUsage => '2. คุณวางแผนจะใช้ Omi ที่ไหน?';

  @override
  String get setupQuestionAge => '3. ช่วงอายุของคุณคือเท่าไหร่?';

  @override
  String get setupAnswerAllQuestions => 'คุณยังไม่ได้ตอบคำถามทั้งหมด! 🥺';

  @override
  String get setupSkipHelp => 'ข้าม ฉันไม่อยากช่วย :C';

  @override
  String get professionEntrepreneur => 'ผู้ประกอบการ';

  @override
  String get professionSoftwareEngineer => 'วิศวกรซอฟต์แวร์';

  @override
  String get professionProductManager => 'ผู้จัดการผลิตภัณฑ์';

  @override
  String get professionExecutive => 'ผู้บริหาร';

  @override
  String get professionSales => 'ฝ่ายขาย';

  @override
  String get professionStudent => 'นักศึกษา';

  @override
  String get usageAtWork => 'ที่ทำงาน';

  @override
  String get usageIrlEvents => 'งานอีเวนต์';

  @override
  String get usageOnline => 'ออนไลน์';

  @override
  String get usageSocialSettings => 'ในสถานการณ์สังคม';

  @override
  String get usageEverywhere => 'ทุกที่';

  @override
  String get customBackendUrlTitle => 'URL เซิร์ฟเวอร์ที่กำหนดเอง';

  @override
  String get backendUrlLabel => 'URL เซิร์ฟเวอร์';

  @override
  String get saveUrlButton => 'บันทึก URL';

  @override
  String get enterBackendUrlError => 'กรุณาป้อน URL เซิร์ฟเวอร์';

  @override
  String get urlMustEndWithSlashError => 'URL ต้องลงท้ายด้วย \"/\"';

  @override
  String get invalidUrlError => 'กรุณาป้อน URL ที่ถูกต้อง';

  @override
  String get backendUrlSavedSuccess => 'บันทึก URL เซิร์ฟเวอร์แล้ว!';

  @override
  String get signInTitle => 'เข้าสู่ระบบ';

  @override
  String get signInButton => 'เข้าสู่ระบบ';

  @override
  String get enterEmailError => 'กรุณากรอกอีเมลของคุณ';

  @override
  String get invalidEmailError => 'กรุณากรอกอีเมลที่ถูกต้อง';

  @override
  String get enterPasswordError => 'กรุณากรอกรหัสผ่านของคุณ';

  @override
  String get passwordMinLengthError => 'รหัสผ่านต้องมีอย่างน้อย 8 ตัวอักษร';

  @override
  String get signInSuccess => 'เข้าสู่ระบบสำเร็จ!';

  @override
  String get alreadyHaveAccountLogin => 'มีบัญชีอยู่แล้ว? เข้าสู่ระบบ';

  @override
  String get emailLabel => 'อีเมล';

  @override
  String get passwordLabel => 'รหัสผ่าน';

  @override
  String get createAccountTitle => 'สร้างบัญชี';

  @override
  String get nameLabel => 'ชื่อ';

  @override
  String get repeatPasswordLabel => 'ยืนยันรหัสผ่าน';

  @override
  String get signUpButton => 'สมัครสมาชิก';

  @override
  String get enterNameError => 'กรุณากรอกชื่อของคุณ';

  @override
  String get passwordsDoNotMatch => 'รหัสผ่านไม่ตรงกัน';

  @override
  String get signUpSuccess => 'สมัครสมาชิกสำเร็จ!';

  @override
  String get loadingKnowledgeGraph => 'กำลังโหลดกราฟความรู้...';

  @override
  String get noKnowledgeGraphYet => 'ยังไม่มีกราฟความรู้';

  @override
  String get buildingKnowledgeGraphFromMemories => 'กำลังสร้างกราฟความรู้จากความทรงจำ...';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'กราฟความรู้ของคุณจะถูกสร้างโดยอัตโนมัติเมื่อคุณสร้างความทรงจำใหม่';

  @override
  String get buildGraphButton => 'สร้างกราฟ';

  @override
  String get checkOutMyMemoryGraph => 'ดูกราฟความจำของฉัน!';

  @override
  String get getButton => 'รับ';

  @override
  String openingApp(String appName) {
    return 'กำลังเปิด $appName...';
  }

  @override
  String get writeSomething => 'เขียนบางอย่าง';

  @override
  String get submitReply => 'ส่งคำตอบ';

  @override
  String get editYourReply => 'แก้ไขคำตอบ';

  @override
  String get replyToReview => 'ตอบกลับรีวิว';

  @override
  String get rateAndReviewThisApp => 'ให้คะแนนและรีวิวแอปนี้';

  @override
  String get noChangesInReview => 'ไม่มีการเปลี่ยนแปลงในรีวิวที่จะอัปเดต';

  @override
  String get cantRateWithoutInternet => 'ไม่สามารถให้คะแนนแอปได้โดยไม่มีการเชื่อมต่ออินเทอร์เน็ต';

  @override
  String get appAnalytics => 'การวิเคราะห์แอป';

  @override
  String get learnMoreLink => 'เรียนรู้เพิ่มเติม';

  @override
  String get moneyEarned => 'เงินที่ได้รับ';

  @override
  String get writeYourReply => 'เขียนการตอบกลับของคุณ...';

  @override
  String get replySentSuccessfully => 'ส่งการตอบกลับสำเร็จ';

  @override
  String failedToSendReply(String error) {
    return 'ไม่สามารถส่งการตอบกลับ: $error';
  }

  @override
  String get send => 'ส่ง';

  @override
  String starFilter(int count) {
    return '$count ดาว';
  }

  @override
  String get noReviewsFound => 'ไม่พบรีวิว';

  @override
  String get editReply => 'แก้ไขการตอบกลับ';

  @override
  String get reply => 'ตอบกลับ';

  @override
  String starFilterLabel(int count) {
    return '$count ดาว';
  }

  @override
  String get sharePublicLink => 'แชร์ลิงก์สาธารณะ';

  @override
  String get makePersonaPublic => 'ทำให้บุคลิกเป็นสาธารณะ';

  @override
  String get connectedKnowledgeData => 'ข้อมูลความรู้ที่เชื่อมต่อแล้ว';

  @override
  String get enterName => 'ป้อนชื่อ';

  @override
  String get disconnectTwitter => 'ยกเลิกการเชื่อมต่อ Twitter';

  @override
  String get disconnectTwitterConfirmation =>
      'คุณแน่ใจหรือไม่ว่าต้องการยกเลิกการเชื่อมต่อบัญชี Twitter? บุคลิกของคุณจะไม่สามารถเข้าถึงข้อมูล Twitter ของคุณได้อีกต่อไป';

  @override
  String get getOmiDeviceDescription => 'สร้างโคลนที่แม่นยำยิ่งขึ้นด้วยบทสนทนาส่วนตัวของคุณ';

  @override
  String get getOmi => 'รับ Omi';

  @override
  String get iHaveOmiDevice => 'ฉันมีอุปกรณ์ Omi';

  @override
  String get goal => 'เป้าหมาย';

  @override
  String get tapToTrackThisGoal => 'แตะเพื่อติดตามเป้าหมายนี้';

  @override
  String get tapToSetAGoal => 'แตะเพื่อตั้งเป้าหมาย';

  @override
  String get processedConversations => 'การสนทนาที่ประมวลผลแล้ว';

  @override
  String get updatedConversations => 'การสนทนาที่อัปเดต';

  @override
  String get newConversations => 'การสนทนาใหม่';

  @override
  String get summaryTemplate => 'เทมเพลตสรุป';

  @override
  String get suggestedTemplates => 'เทมเพลตที่แนะนำ';

  @override
  String get otherTemplates => 'เทมเพลตอื่นๆ';

  @override
  String get availableTemplates => 'เทมเพลตที่มีอยู่';

  @override
  String get getCreative => 'สร้างสรรค์';

  @override
  String get defaultLabel => 'ค่าเริ่มต้น';

  @override
  String get lastUsedLabel => 'ใช้ล่าสุด';

  @override
  String get setDefaultApp => 'ตั้งแอปเริ่มต้น';

  @override
  String setDefaultAppContent(String appName) {
    return 'ตั้ง $appName เป็นแอปสรุปเริ่มต้นของคุณ?\\n\\nแอปนี้จะถูกใช้โดยอัตโนมัติสำหรับการสรุปการสนทนาทั้งหมดในอนาคต';
  }

  @override
  String get setDefaultButton => 'ตั้งค่าเริ่มต้น';

  @override
  String setAsDefaultSuccess(String appName) {
    return 'ตั้ง $appName เป็นแอปสรุปเริ่มต้นแล้ว';
  }

  @override
  String get createCustomTemplate => 'สร้างเทมเพลตที่กำหนดเอง';

  @override
  String get allTemplates => 'เทมเพลตทั้งหมด';

  @override
  String failedToInstallApp(String appName) {
    return 'ติดตั้ง $appName ไม่สำเร็จ กรุณาลองอีกครั้ง';
  }

  @override
  String errorInstallingApp(String appName, String error) {
    return 'เกิดข้อผิดพลาดในการติดตั้ง $appName: $error';
  }

  @override
  String tagSpeaker(int speakerId) {
    return 'แท็กผู้พูด $speakerId';
  }

  @override
  String get personNameAlreadyExists => 'มีบุคคลที่ใช้ชื่อนี้อยู่แล้ว';

  @override
  String get selectYouFromList => 'หากต้องการแท็กตัวคุณเอง กรุณาเลือก \"คุณ\" จากรายการ';

  @override
  String get enterPersonsName => 'ป้อนชื่อบุคคล';

  @override
  String get addPerson => 'เพิ่มบุคคล';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'แท็กส่วนอื่นจากผู้พูดนี้ ($selected/$total)';
  }

  @override
  String get tagOtherSegments => 'แท็กส่วนอื่น';

  @override
  String get managePeople => 'จัดการบุคคล';

  @override
  String get shareViaSms => 'แชร์ผ่าน SMS';

  @override
  String get selectContactsToShareSummary => 'เลือกผู้ติดต่อเพื่อแชร์สรุปการสนทนาของคุณ';

  @override
  String get searchContactsHint => 'ค้นหาผู้ติดต่อ...';

  @override
  String contactsSelectedCount(int count) {
    return 'เลือก $count รายการ';
  }

  @override
  String get clearAllSelection => 'ล้างทั้งหมด';

  @override
  String get selectContactsToShare => 'เลือกผู้ติดต่อที่จะแชร์';

  @override
  String shareWithContactCount(int count) {
    return 'แชร์กับ $count ผู้ติดต่อ';
  }

  @override
  String shareWithContactsCount(int count) {
    return 'แชร์กับ $count ผู้ติดต่อ';
  }

  @override
  String get contactsPermissionRequired => 'ต้องการสิทธิ์เข้าถึงรายชื่อ';

  @override
  String get contactsPermissionRequiredForSms => 'ต้องการสิทธิ์เข้าถึงรายชื่อเพื่อแชร์ผ่าน SMS';

  @override
  String get grantContactsPermissionForSms => 'โปรดให้สิทธิ์เข้าถึงรายชื่อเพื่อแชร์ผ่าน SMS';

  @override
  String get noContactsWithPhoneNumbers => 'ไม่พบผู้ติดต่อที่มีหมายเลขโทรศัพท์';

  @override
  String get noContactsMatchSearch => 'ไม่มีผู้ติดต่อที่ตรงกับการค้นหาของคุณ';

  @override
  String get failedToLoadContacts => 'ไม่สามารถโหลดรายชื่อได้';

  @override
  String get failedToPrepareConversationForSharing => 'ไม่สามารถเตรียมการสนทนาสำหรับการแชร์ได้ โปรดลองอีกครั้ง';

  @override
  String get couldNotOpenSmsApp => 'ไม่สามารถเปิดแอป SMS ได้ โปรดลองอีกครั้ง';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'นี่คือสิ่งที่เราเพิ่งพูดคุยกัน: $link';
  }

  @override
  String get wifiSync => 'การซิงค์ WiFi';

  @override
  String itemCopiedToClipboard(String item) {
    return 'คัดลอก $item ไปยังคลิปบอร์ดแล้ว';
  }

  @override
  String get wifiConnectionFailedTitle => 'การเชื่อมต่อล้มเหลว';

  @override
  String connectingToDeviceName(String deviceName) {
    return 'กำลังเชื่อมต่อกับ $deviceName';
  }

  @override
  String enableDeviceWifi(String deviceName) {
    return 'เปิด WiFi ของ $deviceName';
  }

  @override
  String connectToDeviceName(String deviceName) {
    return 'เชื่อมต่อกับ $deviceName';
  }

  @override
  String get recordingDetails => 'รายละเอียดการบันทึก';

  @override
  String get storageLocationSdCard => 'การ์ด SD';

  @override
  String get storageLocationLimitlessPendant => 'จี้ Limitless';

  @override
  String get storageLocationPhone => 'โทรศัพท์';

  @override
  String get storageLocationPhoneMemory => 'โทรศัพท์ (หน่วยความจำ)';

  @override
  String storedOnDevice(String deviceName) {
    return 'จัดเก็บบน $deviceName';
  }

  @override
  String get transferring => 'กำลังถ่ายโอน...';

  @override
  String get transferRequired => 'ต้องถ่ายโอน';

  @override
  String get downloadingAudioFromSdCard => 'กำลังดาวน์โหลดเสียงจาก SD card ของอุปกรณ์';

  @override
  String get transferRequiredDescription =>
      'การบันทึกนี้จัดเก็บบน SD card ของอุปกรณ์ ถ่ายโอนไปยังโทรศัพท์เพื่อเล่นหรือแชร์';

  @override
  String get cancelTransfer => 'ยกเลิกการถ่ายโอน';

  @override
  String get transferToPhone => 'ถ่ายโอนไปยังโทรศัพท์';

  @override
  String get privateAndSecureOnDevice => 'เป็นส่วนตัวและปลอดภัยบนอุปกรณ์ของคุณ';

  @override
  String get recordingInfo => 'ข้อมูลการบันทึก';

  @override
  String get transferInProgress => 'กำลังถ่ายโอน...';

  @override
  String get shareRecording => 'แชร์การบันทึก';

  @override
  String get deleteRecordingConfirmation =>
      'คุณแน่ใจหรือไม่ว่าต้องการลบการบันทึกนี้ถาวร? การดำเนินการนี้ไม่สามารถยกเลิกได้';

  @override
  String get recordingIdLabel => 'รหัสการบันทึก';

  @override
  String get dateTimeLabel => 'วันที่และเวลา';

  @override
  String get durationLabel => 'ระยะเวลา';

  @override
  String get audioFormatLabel => 'รูปแบบเสียง';

  @override
  String get storageLocationLabel => 'ตำแหน่งจัดเก็บ';

  @override
  String get estimatedSizeLabel => 'ขนาดโดยประมาณ';

  @override
  String get deviceModelLabel => 'รุ่นอุปกรณ์';

  @override
  String get deviceIdLabel => 'รหัสอุปกรณ์';

  @override
  String get statusLabel => 'สถานะ';

  @override
  String get statusProcessed => 'ประมวลผลแล้ว';

  @override
  String get statusUnprocessed => 'ยังไม่ประมวลผล';

  @override
  String get switchedToFastTransfer => 'เปลี่ยนเป็นการถ่ายโอนเร็ว';

  @override
  String get transferCompleteMessage => 'การถ่ายโอนเสร็จสมบูรณ์! คุณสามารถเล่นการบันทึกนี้ได้แล้ว';

  @override
  String transferFailedMessage(String error) {
    return 'การถ่ายโอนล้มเหลว: $error';
  }

  @override
  String get transferCancelled => 'ยกเลิกการถ่ายโอนแล้ว';

  @override
  String get fastTransferEnabled => 'เปิดใช้งานการถ่ายโอนเร็วแล้ว';

  @override
  String get bluetoothSyncEnabled => 'เปิดใช้งานการซิงค์บลูทูธแล้ว';

  @override
  String get enableFastTransfer => 'เปิดใช้งานการถ่ายโอนเร็ว';

  @override
  String get fastTransferDescription =>
      'การถ่ายโอนเร็วใช้ WiFi สำหรับความเร็ว ~5 เท่า โทรศัพท์ของคุณจะเชื่อมต่อกับเครือข่าย WiFi ของอุปกรณ์ Omi ชั่วคราวระหว่างการถ่ายโอน';

  @override
  String get internetAccessPausedDuringTransfer => 'การเข้าถึงอินเทอร์เน็ตถูกหยุดชั่วคราวระหว่างการถ่ายโอน';

  @override
  String get chooseTransferMethodDescription => 'เลือกวิธีการถ่ายโอนการบันทึกจากอุปกรณ์ Omi ไปยังโทรศัพท์ของคุณ';

  @override
  String get wifiSpeed => '~150 KB/s ผ่าน WiFi';

  @override
  String get fiveTimesFaster => 'เร็วกว่า 5 เท่า';

  @override
  String get fastTransferMethodDescription =>
      'สร้างการเชื่อมต่อ WiFi โดยตรงไปยังอุปกรณ์ Omi โทรศัพท์ของคุณจะตัดการเชื่อมต่อ WiFi ปกติชั่วคราวระหว่างการถ่ายโอน';

  @override
  String get bluetooth => 'บลูทูธ';

  @override
  String get bleSpeed => '~30 KB/s ผ่าน BLE';

  @override
  String get bluetoothMethodDescription =>
      'ใช้การเชื่อมต่อ Bluetooth Low Energy มาตรฐาน ช้ากว่าแต่ไม่ส่งผลต่อการเชื่อมต่อ WiFi';

  @override
  String get selected => 'เลือกแล้ว';

  @override
  String get selectOption => 'เลือก';

  @override
  String get lowBatteryAlertTitle => 'การแจ้งเตือนแบตเตอรี่ต่ำ';

  @override
  String get lowBatteryAlertBody => 'แบตเตอรี่ของอุปกรณ์ของคุณต่ำ ถึงเวลาชาร์จแล้ว! 🔋';

  @override
  String get deviceDisconnectedNotificationTitle => 'อุปกรณ์ Omi ของคุณถูกตัดการเชื่อมต่อ';

  @override
  String get deviceDisconnectedNotificationBody => 'กรุณาเชื่อมต่อใหม่เพื่อใช้งาน Omi ต่อไป';

  @override
  String get firmwareUpdateAvailable => 'มีการอัปเดตเฟิร์มแวร์';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'มีการอัปเดตเฟิร์มแวร์ใหม่ ($version) สำหรับอุปกรณ์ Omi ของคุณ คุณต้องการอัปเดตตอนนี้หรือไม่?';
  }

  @override
  String get later => 'ภายหลัง';

  @override
  String get appDeletedSuccessfully => 'ลบแอปสำเร็จแล้ว';

  @override
  String get appDeleteFailed => 'ไม่สามารถลบแอปได้ กรุณาลองใหม่ภายหลัง';

  @override
  String get appVisibilityChangedSuccessfully => 'เปลี่ยนการมองเห็นแอปสำเร็จแล้ว อาจใช้เวลาสักครู่ในการอัปเดต';

  @override
  String get errorActivatingAppIntegration =>
      'เกิดข้อผิดพลาดในการเปิดใช้งานแอป หากเป็นแอปการรวม โปรดตรวจสอบว่าการตั้งค่าเสร็จสมบูรณ์แล้ว';

  @override
  String get errorUpdatingAppStatus => 'เกิดข้อผิดพลาดขณะอัปเดตสถานะแอป';

  @override
  String get calculatingETA => 'กำลังคำนวณ...';

  @override
  String aboutMinutesRemaining(int minutes) {
    return 'เหลืออีกประมาณ $minutes นาที';
  }

  @override
  String get aboutAMinuteRemaining => 'เหลืออีกประมาณหนึ่งนาที';

  @override
  String get almostDone => 'เกือบเสร็จแล้ว...';

  @override
  String get omiSays => 'Omi พูดว่า';

  @override
  String get analyzingYourData => 'กำลังวิเคราะห์ข้อมูลของคุณ...';

  @override
  String migratingToProtection(String level) {
    return 'กำลังย้ายไปยังการป้องกัน $level...';
  }

  @override
  String get noDataToMigrateFinalizing => 'ไม่มีข้อมูลที่จะย้าย กำลังสรุป...';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return 'กำลังย้าย $itemType... $percentage%';
  }

  @override
  String get allObjectsMigratedFinalizing => 'ย้ายออบเจ็กต์ทั้งหมดแล้ว กำลังสรุป...';

  @override
  String get migrationErrorOccurred => 'เกิดข้อผิดพลาดระหว่างการย้าย กรุณาลองอีกครั้ง';

  @override
  String get migrationComplete => 'การย้ายเสร็จสมบูรณ์!';

  @override
  String dataProtectedWithSettings(String level) {
    return 'ข้อมูลของคุณได้รับการปกป้องด้วยการตั้งค่า $level ใหม่แล้ว';
  }

  @override
  String get chatsLowercase => 'แชท';

  @override
  String get dataLowercase => 'ข้อมูล';

  @override
  String get fallNotificationTitle => 'โอ๊ะ';

  @override
  String get fallNotificationBody => 'คุณหกล้มหรือเปล่า?';

  @override
  String get importantConversationTitle => 'การสนทนาสำคัญ';

  @override
  String get importantConversationBody => 'คุณเพิ่งมีการสนทนาสำคัญ แตะเพื่อแชร์สรุปกับผู้อื่น';

  @override
  String get templateName => 'ชื่อเทมเพลต';

  @override
  String get templateNameHint => 'เช่น ตัวดึงรายการการดำเนินการประชุม';

  @override
  String get nameMustBeAtLeast3Characters => 'ชื่อต้องมีอย่างน้อย 3 ตัวอักษร';

  @override
  String get conversationPromptHint => 'เช่น ดึงรายการการดำเนินการ การตัดสินใจ และประเด็นสำคัญจากการสนทนาที่ให้มา';

  @override
  String get pleaseEnterAppPrompt => 'กรุณากรอกพรอมต์สำหรับแอปของคุณ';

  @override
  String get promptMustBeAtLeast10Characters => 'พรอมต์ต้องมีอย่างน้อย 10 ตัวอักษร';

  @override
  String get anyoneCanDiscoverTemplate => 'ใครก็สามารถค้นพบเทมเพลตของคุณได้';

  @override
  String get onlyYouCanUseTemplate => 'เฉพาะคุณเท่านั้นที่สามารถใช้เทมเพลตนี้ได้';

  @override
  String get generatingDescription => 'กำลังสร้างคำอธิบาย...';

  @override
  String get creatingAppIcon => 'กำลังสร้างไอคอนแอป...';

  @override
  String get installingApp => 'กำลังติดตั้งแอป...';

  @override
  String get appCreatedAndInstalled => 'สร้างและติดตั้งแอปแล้ว!';

  @override
  String get appCreatedSuccessfully => 'สร้างแอปสำเร็จ!';

  @override
  String get failedToCreateApp => 'ไม่สามารถสร้างแอปได้ กรุณาลองอีกครั้ง';

  @override
  String get addAppSelectCoreCapability => 'โปรดเลือกความสามารถหลักอีกหนึ่งอย่างสำหรับแอปของคุณ';

  @override
  String get addAppSelectPaymentPlan => 'โปรดเลือกแผนการชำระเงินและใส่ราคาสำหรับแอปของคุณ';

  @override
  String get addAppSelectCapability => 'โปรดเลือกความสามารถอย่างน้อยหนึ่งอย่างสำหรับแอปของคุณ';

  @override
  String get addAppSelectLogo => 'โปรดเลือกโลโก้สำหรับแอปของคุณ';

  @override
  String get addAppEnterChatPrompt => 'โปรดใส่ข้อความแชทสำหรับแอปของคุณ';

  @override
  String get addAppEnterConversationPrompt => 'โปรดใส่ข้อความสนทนาสำหรับแอปของคุณ';

  @override
  String get addAppSelectTriggerEvent => 'โปรดเลือกเหตุการณ์ทริกเกอร์สำหรับแอปของคุณ';

  @override
  String get addAppEnterWebhookUrl => 'โปรดใส่ URL webhook สำหรับแอปของคุณ';

  @override
  String get addAppSelectCategory => 'โปรดเลือกหมวดหมู่สำหรับแอปของคุณ';

  @override
  String get addAppFillRequiredFields => 'โปรดกรอกข้อมูลที่จำเป็นทั้งหมดให้ถูกต้อง';

  @override
  String get addAppUpdatedSuccess => 'อัปเดตแอปสำเร็จ 🚀';

  @override
  String get addAppUpdateFailed => 'อัปเดตล้มเหลว โปรดลองอีกครั้งภายหลัง';

  @override
  String get addAppSubmittedSuccess => 'ส่งแอปสำเร็จ 🚀';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'เกิดข้อผิดพลาดในการเปิดตัวเลือกไฟล์: $message';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'เกิดข้อผิดพลาดในการเลือกรูปภาพ: $error';
  }

  @override
  String get addAppPhotosPermissionDenied => 'การอนุญาตเข้าถึงรูปภาพถูกปฏิเสธ โปรดอนุญาตการเข้าถึงรูปภาพ';

  @override
  String get addAppErrorSelectingImageRetry => 'เกิดข้อผิดพลาดในการเลือกรูปภาพ โปรดลองอีกครั้ง';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'เกิดข้อผิดพลาดในการเลือกรูปขนาดย่อ: $error';
  }

  @override
  String get addAppErrorSelectingThumbnailRetry => 'เกิดข้อผิดพลาดในการเลือกรูปขนาดย่อ โปรดลองอีกครั้ง';

  @override
  String get addAppCapabilityConflictWithPersona => 'ไม่สามารถเลือกความสามารถอื่นพร้อมกับ Persona ได้';

  @override
  String get addAppPersonaConflictWithCapabilities => 'ไม่สามารถเลือก Persona พร้อมกับความสามารถอื่นได้';

  @override
  String get personaTwitterHandleNotFound => 'ไม่พบบัญชี Twitter';

  @override
  String get personaTwitterHandleSuspended => 'บัญชี Twitter ถูกระงับ';

  @override
  String get personaFailedToVerifyTwitter => 'ไม่สามารถยืนยันบัญชี Twitter ได้';

  @override
  String get personaFailedToFetch => 'ไม่สามารถดึงข้อมูล Persona ของคุณได้';

  @override
  String get personaFailedToCreate => 'ไม่สามารถสร้าง Persona ของคุณได้';

  @override
  String get personaConnectKnowledgeSource => 'โปรดเชื่อมต่อแหล่งข้อมูลอย่างน้อยหนึ่งแหล่ง (Omi หรือ Twitter)';

  @override
  String get personaUpdatedSuccessfully => 'อัปเดต Persona สำเร็จ';

  @override
  String get personaFailedToUpdate => 'อัปเดต Persona ล้มเหลว';

  @override
  String get personaPleaseSelectImage => 'โปรดเลือกรูปภาพ';

  @override
  String get personaFailedToCreateTryLater => 'ไม่สามารถสร้าง Persona ได้ โปรดลองอีกครั้งภายหลัง';

  @override
  String personaFailedToCreateWithError(String error) {
    return 'สร้าง Persona ล้มเหลว: $error';
  }

  @override
  String get personaFailedToEnable => 'ไม่สามารถเปิดใช้งาน Persona ได้';

  @override
  String personaErrorEnablingWithError(String error) {
    return 'เกิดข้อผิดพลาดในการเปิดใช้งาน Persona: $error';
  }

  @override
  String get paymentFailedToFetchCountries => 'ไม่สามารถดึงรายชื่อประเทศที่รองรับได้ โปรดลองอีกครั้งภายหลัง';

  @override
  String get paymentFailedToSetDefault => 'ไม่สามารถตั้งค่าวิธีการชำระเงินเริ่มต้นได้ โปรดลองอีกครั้งภายหลัง';

  @override
  String get paymentFailedToSavePaypal => 'ไม่สามารถบันทึกข้อมูล PayPal ได้ โปรดลองอีกครั้งภายหลัง';

  @override
  String get paypalEmailHint => 'nik@example.com';

  @override
  String get paypalMeLinkHint => 'paypal.me/nik';

  @override
  String get paymentMethodStripe => 'Stripe';

  @override
  String get paymentMethodPayPal => 'PayPal';

  @override
  String get paymentStatusActive => 'ใช้งานอยู่';

  @override
  String get paymentStatusConnected => 'เชื่อมต่อแล้ว';

  @override
  String get paymentStatusNotConnected => 'ไม่ได้เชื่อมต่อ';

  @override
  String get paymentAppCost => 'ค่าใช้จ่ายแอป';

  @override
  String get paymentEnterValidAmount => 'โปรดใส่จำนวนเงินที่ถูกต้อง';

  @override
  String get paymentEnterAmountGreaterThanZero => 'โปรดใส่จำนวนเงินมากกว่า 0';

  @override
  String get paymentPlan => 'แผนการชำระเงิน';

  @override
  String get paymentNoneSelected => 'ไม่ได้เลือก';

  @override
  String get aiGenPleaseEnterDescription => 'กรุณาใส่คำอธิบายสำหรับแอปของคุณ';

  @override
  String get aiGenCreatingAppIcon => 'กำลังสร้างไอคอนแอป...';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'เกิดข้อผิดพลาด: $message';
  }

  @override
  String get aiGenAppCreatedSuccessfully => 'สร้างแอปสำเร็จแล้ว!';

  @override
  String get aiGenFailedToCreateApp => 'ไม่สามารถสร้างแอปได้';

  @override
  String get aiGenErrorWhileCreatingApp => 'เกิดข้อผิดพลาดขณะสร้างแอป';

  @override
  String get aiGenFailedToGenerateApp => 'ไม่สามารถสร้างแอปได้ กรุณาลองอีกครั้ง';

  @override
  String get aiGenFailedToRegenerateIcon => 'ไม่สามารถสร้างไอคอนใหม่ได้';

  @override
  String get aiGenPleaseGenerateAppFirst => 'กรุณาสร้างแอปก่อน';

  @override
  String get xHandleTitle => 'บัญชี X ของคุณคืออะไร?';

  @override
  String get xHandleDescription => 'เราจะฝึกโคลน Omi ของคุณล่วงหน้า\nตามกิจกรรมของบัญชีคุณ';

  @override
  String get xHandleHint => '@nikshevchenko';

  @override
  String get xHandlePleaseEnter => 'กรุณาป้อนบัญชี X ของคุณ';

  @override
  String get xHandlePleaseEnterValid => 'กรุณาป้อนบัญชี X ที่ถูกต้อง';

  @override
  String get nextButton => 'ถัดไป';

  @override
  String get connectOmiDevice => 'เชื่อมต่ออุปกรณ์ Omi';

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'คุณกำลังเปลี่ยนแผน Unlimited เป็น $title คุณแน่ใจหรือไม่ว่าต้องการดำเนินการต่อ?';
  }

  @override
  String get planUpgradeScheduledMessage =>
      'กำหนดการอัปเกรดแล้ว! แผนรายเดือนของคุณจะดำเนินต่อไปจนกว่าจะสิ้นสุดรอบการเรียกเก็บเงิน จากนั้นจะเปลี่ยนเป็นรายปีโดยอัตโนมัติ';

  @override
  String get couldNotSchedulePlanChange => 'ไม่สามารถกำหนดการเปลี่ยนแผนได้ กรุณาลองอีกครั้ง';

  @override
  String get subscriptionReactivatedDefault =>
      'เปิดใช้งานการสมัครสมาชิกของคุณอีกครั้งแล้ว! ไม่มีค่าใช้จ่ายตอนนี้ - คุณจะถูกเรียกเก็บเงินเมื่อสิ้นสุดรอบปัจจุบัน';

  @override
  String get subscriptionSuccessfulCharged => 'สมัครสมาชิกสำเร็จ! คุณถูกเรียกเก็บเงินสำหรับรอบการเรียกเก็บเงินใหม่แล้ว';

  @override
  String get couldNotProcessSubscription => 'ไม่สามารถประมวลผลการสมัครสมาชิกได้ กรุณาลองอีกครั้ง';

  @override
  String get couldNotLaunchUpgradePage => 'ไม่สามารถเปิดหน้าอัปเกรดได้ กรุณาลองอีกครั้ง';

  @override
  String get transcriptionJsonPlaceholder => 'วางการตั้งค่า JSON ของคุณที่นี่...';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get pricePlaceholder => '0.00';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'เกิดข้อผิดพลาดในการเปิดตัวเลือกไฟล์: $message';
  }

  @override
  String importErrorGeneric(String error) {
    return 'ข้อผิดพลาด: $error';
  }

  @override
  String get mergeConversationsSuccessTitle => 'รวมการสนทนาสำเร็จแล้ว';

  @override
  String mergeConversationsSuccessBody(int count) {
    return 'รวม $count การสนทนาสำเร็จแล้ว';
  }

  @override
  String get dailyReflectionNotificationTitle => 'ถึงเวลาทบทวนรายวัน';

  @override
  String get dailyReflectionNotificationBody => 'เล่าให้ฟังเกี่ยวกับวันของคุณ';

  @override
  String get actionItemReminderTitle => 'การแจ้งเตือน Omi';

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName ตัดการเชื่อมต่อ';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'กรุณาเชื่อมต่อใหม่เพื่อใช้งาน $deviceName ของคุณต่อไป';
  }

  @override
  String get onboardingSignIn => 'ลงชื่อเข้าใช้';

  @override
  String get onboardingYourName => 'ชื่อของคุณ';

  @override
  String get onboardingLanguage => 'ภาษา';

  @override
  String get onboardingPermissions => 'สิทธิ์การเข้าถึง';

  @override
  String get onboardingComplete => 'เสร็จสิ้น';

  @override
  String get onboardingWelcomeToOmi => 'ยินดีต้อนรับสู่ Omi';

  @override
  String get onboardingTellUsAboutYourself => 'เล่าเกี่ยวกับตัวคุณให้เราฟัง';

  @override
  String get onboardingChooseYourPreference => 'เลือกการตั้งค่าของคุณ';

  @override
  String get onboardingGrantRequiredAccess => 'ให้สิทธิ์การเข้าถึงที่จำเป็น';

  @override
  String get onboardingYoureAllSet => 'คุณพร้อมแล้ว';

  @override
  String get searchTranscriptOrSummary => 'ค้นหาในข้อความถอดเสียงหรือสรุป...';

  @override
  String get myGoal => 'เป้าหมายของฉัน';

  @override
  String get appNotAvailable => 'อุ๊ปส์! ดูเหมือนว่าแอปที่คุณกำลังมองหาไม่พร้อมใช้งาน';

  @override
  String get failedToConnectTodoist => 'ไม่สามารถเชื่อมต่อกับ Todoist ได้';

  @override
  String get failedToConnectAsana => 'ไม่สามารถเชื่อมต่อกับ Asana ได้';

  @override
  String get failedToConnectGoogleTasks => 'ไม่สามารถเชื่อมต่อกับ Google Tasks ได้';

  @override
  String get failedToConnectClickUp => 'ไม่สามารถเชื่อมต่อกับ ClickUp ได้';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return 'ไม่สามารถเชื่อมต่อกับ $serviceName ได้: $error';
  }

  @override
  String get successfullyConnectedTodoist => 'เชื่อมต่อกับ Todoist สำเร็จ!';

  @override
  String get failedToConnectTodoistRetry => 'ไม่สามารถเชื่อมต่อกับ Todoist ได้ กรุณาลองอีกครั้ง';

  @override
  String get successfullyConnectedAsana => 'เชื่อมต่อกับ Asana สำเร็จ!';

  @override
  String get failedToConnectAsanaRetry => 'ไม่สามารถเชื่อมต่อกับ Asana ได้ กรุณาลองอีกครั้ง';

  @override
  String get successfullyConnectedGoogleTasks => 'เชื่อมต่อกับ Google Tasks สำเร็จ!';

  @override
  String get failedToConnectGoogleTasksRetry => 'ไม่สามารถเชื่อมต่อกับ Google Tasks ได้ กรุณาลองอีกครั้ง';

  @override
  String get successfullyConnectedClickUp => 'เชื่อมต่อกับ ClickUp สำเร็จ!';

  @override
  String get failedToConnectClickUpRetry => 'ไม่สามารถเชื่อมต่อกับ ClickUp ได้ กรุณาลองอีกครั้ง';

  @override
  String get successfullyConnectedNotion => 'เชื่อมต่อกับ Notion สำเร็จ!';

  @override
  String get failedToRefreshNotionStatus => 'ไม่สามารถรีเฟรชสถานะการเชื่อมต่อ Notion ได้';

  @override
  String get successfullyConnectedGoogle => 'เชื่อมต่อกับ Google สำเร็จ!';

  @override
  String get failedToRefreshGoogleStatus => 'ไม่สามารถรีเฟรชสถานะการเชื่อมต่อ Google ได้';

  @override
  String get successfullyConnectedWhoop => 'เชื่อมต่อกับ Whoop สำเร็จ!';

  @override
  String get failedToRefreshWhoopStatus => 'ไม่สามารถรีเฟรชสถานะการเชื่อมต่อ Whoop ได้';

  @override
  String get successfullyConnectedGitHub => 'เชื่อมต่อกับ GitHub สำเร็จ!';

  @override
  String get failedToRefreshGitHubStatus => 'ไม่สามารถรีเฟรชสถานะการเชื่อมต่อ GitHub ได้';

  @override
  String get authFailedToSignInWithGoogle => 'ไม่สามารถเข้าสู่ระบบด้วย Google ได้ กรุณาลองอีกครั้ง';

  @override
  String get authenticationFailed => 'การยืนยันตัวตนล้มเหลว กรุณาลองอีกครั้ง';

  @override
  String get authFailedToSignInWithApple => 'ไม่สามารถเข้าสู่ระบบด้วย Apple ได้ กรุณาลองอีกครั้ง';

  @override
  String get authFailedToRetrieveToken => 'ไม่สามารถดึงโทเคน Firebase ได้ กรุณาลองอีกครั้ง';

  @override
  String get authUnexpectedErrorFirebase =>
      'เกิดข้อผิดพลาดที่ไม่คาดคิดขณะเข้าสู่ระบบ ข้อผิดพลาด Firebase กรุณาลองอีกครั้ง';

  @override
  String get authUnexpectedError => 'เกิดข้อผิดพลาดที่ไม่คาดคิดขณะเข้าสู่ระบบ กรุณาลองอีกครั้ง';

  @override
  String get authFailedToLinkGoogle => 'ไม่สามารถเชื่อมต่อกับ Google ได้ กรุณาลองอีกครั้ง';

  @override
  String get authFailedToLinkApple => 'ไม่สามารถเชื่อมต่อกับ Apple ได้ กรุณาลองอีกครั้ง';

  @override
  String get onboardingBluetoothRequired => 'ต้องมีสิทธิ์ Bluetooth เพื่อเชื่อมต่อกับอุปกรณ์ของคุณ';

  @override
  String get onboardingBluetoothDeniedSystemPrefs => 'สิทธิ์ Bluetooth ถูกปฏิเสธ กรุณาให้สิทธิ์ในการตั้งค่าระบบ';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'สถานะสิทธิ์ Bluetooth: $status กรุณาตรวจสอบการตั้งค่าระบบ';
  }

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'ไม่สามารถตรวจสอบสิทธิ์ Bluetooth: $error';
  }

  @override
  String get onboardingNotificationDeniedSystemPrefs => 'สิทธิ์การแจ้งเตือนถูกปฏิเสธ กรุณาให้สิทธิ์ในการตั้งค่าระบบ';

  @override
  String get onboardingNotificationDeniedNotifications =>
      'สิทธิ์การแจ้งเตือนถูกปฏิเสธ กรุณาให้สิทธิ์ในการตั้งค่าระบบ > การแจ้งเตือน';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return 'สถานะสิทธิ์การแจ้งเตือน: $status กรุณาตรวจสอบการตั้งค่าระบบ';
  }

  @override
  String onboardingFailedCheckNotification(String error) {
    return 'ไม่สามารถตรวจสอบสิทธิ์การแจ้งเตือน: $error';
  }

  @override
  String get onboardingLocationGrantInSettings =>
      'กรุณาให้สิทธิ์ตำแหน่งที่ตั้งในการตั้งค่า > ความเป็นส่วนตัวและความปลอดภัย > บริการตำแหน่งที่ตั้ง';

  @override
  String get onboardingMicrophoneRequired => 'ต้องมีสิทธิ์ไมโครโฟนสำหรับการบันทึก';

  @override
  String get onboardingMicrophoneDenied =>
      'สิทธิ์ไมโครโฟนถูกปฏิเสธ กรุณาให้สิทธิ์ในการตั้งค่าระบบ > ความเป็นส่วนตัวและความปลอดภัย > ไมโครโฟน';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'สถานะสิทธิ์ไมโครโฟน: $status กรุณาตรวจสอบการตั้งค่าระบบ';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'ไม่สามารถตรวจสอบสิทธิ์ไมโครโฟน: $error';
  }

  @override
  String get onboardingScreenCaptureRequired => 'ต้องมีสิทธิ์จับภาพหน้าจอสำหรับการบันทึกเสียงระบบ';

  @override
  String get onboardingScreenCaptureDenied =>
      'สิทธิ์จับภาพหน้าจอถูกปฏิเสธ กรุณาให้สิทธิ์ในการตั้งค่าระบบ > ความเป็นส่วนตัวและความปลอดภัย > การบันทึกหน้าจอ';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return 'สถานะสิทธิ์จับภาพหน้าจอ: $status กรุณาตรวจสอบการตั้งค่าระบบ';
  }

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return 'ไม่สามารถตรวจสอบสิทธิ์จับภาพหน้าจอ: $error';
  }

  @override
  String get onboardingAccessibilityRequired => 'ต้องมีสิทธิ์การเข้าถึงสำหรับการตรวจจับการประชุมในเบราว์เซอร์';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'สถานะสิทธิ์การเข้าถึง: $status กรุณาตรวจสอบการตั้งค่าระบบ';
  }

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'ไม่สามารถตรวจสอบสิทธิ์การเข้าถึง: $error';
  }

  @override
  String get msgCameraNotAvailable => 'การถ่ายภาพจากกล้องไม่สามารถใช้งานได้บนแพลตฟอร์มนี้';

  @override
  String get msgCameraPermissionDenied => 'การอนุญาตกล้องถูกปฏิเสธ กรุณาอนุญาตการเข้าถึงกล้อง';

  @override
  String msgCameraAccessError(String error) {
    return 'เกิดข้อผิดพลาดในการเข้าถึงกล้อง: $error';
  }

  @override
  String get msgPhotoError => 'เกิดข้อผิดพลาดในการถ่ายรูป กรุณาลองอีกครั้ง';

  @override
  String get msgMaxImagesLimit => 'คุณสามารถเลือกได้สูงสุด 4 รูปภาพ';

  @override
  String msgFilePickerError(String error) {
    return 'เกิดข้อผิดพลาดในการเปิดตัวเลือกไฟล์: $error';
  }

  @override
  String msgSelectImagesError(String error) {
    return 'เกิดข้อผิดพลาดในการเลือกรูปภาพ: $error';
  }

  @override
  String get msgPhotosPermissionDenied => 'การอนุญาตรูปภาพถูกปฏิเสธ กรุณาอนุญาตการเข้าถึงรูปภาพเพื่อเลือกภาพ';

  @override
  String get msgSelectImagesGenericError => 'เกิดข้อผิดพลาดในการเลือกรูปภาพ กรุณาลองอีกครั้ง';

  @override
  String get msgMaxFilesLimit => 'คุณสามารถเลือกได้สูงสุด 4 ไฟล์';

  @override
  String msgSelectFilesError(String error) {
    return 'เกิดข้อผิดพลาดในการเลือกไฟล์: $error';
  }

  @override
  String get msgSelectFilesGenericError => 'เกิดข้อผิดพลาดในการเลือกไฟล์ กรุณาลองอีกครั้ง';

  @override
  String get msgUploadFileFailed => 'อัปโหลดไฟล์ล้มเหลว กรุณาลองอีกครั้งในภายหลัง';

  @override
  String get msgReadingMemories => 'กำลังอ่านความทรงจำของคุณ...';

  @override
  String get msgLearningMemories => 'กำลังเรียนรู้จากความทรงจำของคุณ...';

  @override
  String get msgUploadAttachedFileFailed => 'อัปโหลดไฟล์แนบล้มเหลว';

  @override
  String captureRecordingError(String error) {
    return 'เกิดข้อผิดพลาดขณะบันทึก: $error';
  }

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return 'การบันทึกหยุดลง: $reason คุณอาจต้องเชื่อมต่อจอภาพภายนอกอีกครั้งหรือเริ่มการบันทึกใหม่';
  }

  @override
  String get captureMicrophonePermissionRequired => 'ต้องได้รับอนุญาตใช้ไมโครโฟน';

  @override
  String get captureMicrophonePermissionInSystemPreferences => 'ให้สิทธิ์ไมโครโฟนในการตั้งค่าระบบ';

  @override
  String get captureScreenRecordingPermissionRequired => 'ต้องได้รับอนุญาตบันทึกหน้าจอ';

  @override
  String get captureDisplayDetectionFailed => 'การตรวจจับจอภาพล้มเหลว การบันทึกหยุดลง';

  @override
  String get devModeInvalidAudioBytesWebhookUrl => 'URL เว็บฮุคไบต์เสียงไม่ถูกต้อง';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl => 'URL เว็บฮุคการถอดเสียงแบบเรียลไทม์ไม่ถูกต้อง';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl => 'URL เว็บฮุคการสร้างการสนทนาไม่ถูกต้อง';

  @override
  String get devModeInvalidDaySummaryWebhookUrl => 'URL เว็บฮุคสรุปรายวันไม่ถูกต้อง';

  @override
  String get devModeSettingsSaved => 'บันทึกการตั้งค่าแล้ว!';

  @override
  String get voiceFailedToTranscribe => 'ไม่สามารถถอดเสียงได้';

  @override
  String get locationPermissionRequired => 'ต้องได้รับอนุญาตตำแหน่ง';

  @override
  String get locationPermissionContent =>
      'การถ่ายโอนเร็วต้องได้รับอนุญาตตำแหน่งเพื่อตรวจสอบการเชื่อมต่อ WiFi โปรดให้สิทธิ์ตำแหน่งเพื่อดำเนินการต่อ';

  @override
  String get pdfTranscriptExport => 'ส่งออกบทถอดเสียง';

  @override
  String get pdfConversationExport => 'ส่งออกการสนทนา';

  @override
  String pdfTitleLabel(String title) {
    return 'ชื่อเรื่อง: $title';
  }

  @override
  String get conversationNewIndicator => 'ใหม่ 🚀';

  @override
  String conversationPhotosCount(int count) {
    return '$count รูปภาพ';
  }

  @override
  String get mergingStatus => 'กำลังรวม...';

  @override
  String timeSecsSingular(int count) {
    return '$count วินาที';
  }

  @override
  String timeSecsPlural(int count) {
    return '$count วินาที';
  }

  @override
  String timeMinSingular(int count) {
    return '$count นาที';
  }

  @override
  String timeMinsPlural(int count) {
    return '$count นาที';
  }

  @override
  String timeMinsAndSecs(int mins, int secs) {
    return '$mins นาที $secs วินาที';
  }

  @override
  String timeHourSingular(int count) {
    return '$count ชั่วโมง';
  }

  @override
  String timeHoursPlural(int count) {
    return '$count ชั่วโมง';
  }

  @override
  String timeHoursAndMins(int hours, int mins) {
    return '$hours ชั่วโมง $mins นาที';
  }

  @override
  String timeDaySingular(int count) {
    return '$count วัน';
  }

  @override
  String timeDaysPlural(int count) {
    return '$count วัน';
  }

  @override
  String timeDaysAndHours(int days, int hours) {
    return '$days วัน $hours ชั่วโมง';
  }

  @override
  String timeCompactSecs(int count) {
    return '$countวิ';
  }

  @override
  String timeCompactMins(int count) {
    return '$countน';
  }

  @override
  String timeCompactMinsAndSecs(int mins, int secs) {
    return '$minsน $secsวิ';
  }

  @override
  String timeCompactHours(int count) {
    return '$countชม';
  }

  @override
  String timeCompactHoursAndMins(int hours, int mins) {
    return '$hoursชม $minsน';
  }

  @override
  String get moveToFolder => 'ย้ายไปยังโฟลเดอร์';

  @override
  String get noFoldersAvailable => 'ไม่มีโฟลเดอร์ที่พร้อมใช้งาน';

  @override
  String get newFolder => 'โฟลเดอร์ใหม่';

  @override
  String get color => 'สี';

  @override
  String get waitingForDevice => 'กำลังรออุปกรณ์...';

  @override
  String get saySomething => 'พูดอะไรสักอย่าง...';

  @override
  String get initialisingSystemAudio => 'กำลังเริ่มต้นเสียงระบบ';

  @override
  String get stopRecording => 'หยุดบันทึก';

  @override
  String get continueRecording => 'บันทึกต่อ';

  @override
  String get initialisingRecorder => 'กำลังเริ่มต้นเครื่องบันทึก';

  @override
  String get pauseRecording => 'หยุดชั่วคราว';

  @override
  String get resumeRecording => 'บันทึกต่อ';

  @override
  String get noDailyRecapsYet => 'ยังไม่มีสรุปรายวัน';

  @override
  String get dailyRecapsDescription => 'สรุปรายวันของคุณจะปรากฏที่นี่เมื่อสร้างเสร็จ';

  @override
  String get chooseTransferMethod => 'เลือกวิธีการถ่ายโอน';

  @override
  String get fastTransferSpeed => '~150 KB/s ผ่าน WiFi';

  @override
  String largeTimeGapDetected(String gap) {
    return 'ตรวจพบช่วงเวลาห่างมาก ($gap)';
  }

  @override
  String largeTimeGapsDetected(String gaps) {
    return 'ตรวจพบช่วงเวลาห่างมากหลายช่วง ($gaps)';
  }

  @override
  String get deviceDoesNotSupportWifiSwitchingToBle => 'อุปกรณ์ไม่รองรับการซิงค์ WiFi กำลังเปลี่ยนไปใช้ Bluetooth';

  @override
  String get appleHealthNotAvailable => 'Apple Health ไม่พร้อมใช้งานบนอุปกรณ์นี้';

  @override
  String get downloadAudio => 'ดาวน์โหลดเสียง';

  @override
  String get audioDownloadSuccess => 'ดาวน์โหลดเสียงสำเร็จ';

  @override
  String get audioDownloadFailed => 'ดาวน์โหลดเสียงล้มเหลว';

  @override
  String get downloadingAudio => 'กำลังดาวน์โหลดเสียง...';

  @override
  String get shareAudio => 'แชร์เสียง';

  @override
  String get preparingAudio => 'กำลังเตรียมเสียง';

  @override
  String get gettingAudioFiles => 'กำลังรับไฟล์เสียง...';

  @override
  String get downloadingAudioProgress => 'กำลังดาวน์โหลดเสียง';

  @override
  String get processingAudio => 'กำลังประมวลผลเสียง';

  @override
  String get combiningAudioFiles => 'กำลังรวมไฟล์เสียง...';

  @override
  String get audioReady => 'เสียงพร้อมแล้ว';

  @override
  String get openingShareSheet => 'กำลังเปิดแผ่นแชร์...';

  @override
  String get audioShareFailed => 'แชร์ล้มเหลว';

  @override
  String get dailyRecaps => 'สรุปรายวัน';

  @override
  String get removeFilter => 'ลบตัวกรอง';

  @override
  String get categoryConversationAnalysis => 'การวิเคราะห์การสนทนา';

  @override
  String get categoryPersonalityClone => 'โคลนบุคลิกภาพ';

  @override
  String get categoryHealth => 'สุขภาพ';

  @override
  String get categoryEducation => 'การศึกษา';

  @override
  String get categoryCommunication => 'การสื่อสาร';

  @override
  String get categoryEmotionalSupport => 'การสนับสนุนทางอารมณ์';

  @override
  String get categoryProductivity => 'ประสิทธิภาพ';

  @override
  String get categoryEntertainment => 'ความบันเทิง';

  @override
  String get categoryFinancial => 'การเงิน';

  @override
  String get categoryTravel => 'การเดินทาง';

  @override
  String get categorySafety => 'ความปลอดภัย';

  @override
  String get categoryShopping => 'ช้อปปิ้ง';

  @override
  String get categorySocial => 'สังคม';

  @override
  String get categoryNews => 'ข่าว';

  @override
  String get categoryUtilities => 'เครื่องมือ';

  @override
  String get categoryOther => 'อื่นๆ';

  @override
  String get capabilityChat => 'แชท';

  @override
  String get capabilityConversations => 'การสนทนา';

  @override
  String get capabilityExternalIntegration => 'การเชื่อมต่อภายนอก';

  @override
  String get capabilityNotification => 'การแจ้งเตือน';

  @override
  String get triggerAudioBytes => 'ไบต์เสียง';

  @override
  String get triggerConversationCreation => 'การสร้างการสนทนา';

  @override
  String get triggerTranscriptProcessed => 'ถอดเสียงเสร็จสิ้น';

  @override
  String get actionCreateConversations => 'สร้างการสนทนา';

  @override
  String get actionCreateMemories => 'สร้างความทรงจำ';

  @override
  String get actionReadConversations => 'อ่านการสนทนา';

  @override
  String get actionReadMemories => 'อ่านความทรงจำ';

  @override
  String get actionReadTasks => 'อ่านงาน';

  @override
  String get scopeUserName => 'ชื่อผู้ใช้';

  @override
  String get scopeUserFacts => 'ข้อมูลผู้ใช้';

  @override
  String get scopeUserConversations => 'การสนทนาของผู้ใช้';

  @override
  String get scopeUserChat => 'แชทของผู้ใช้';

  @override
  String get capabilitySummary => 'สรุป';

  @override
  String get capabilityFeatured => 'แนะนำ';

  @override
  String get capabilityTasks => 'งาน';

  @override
  String get capabilityIntegrations => 'การเชื่อมต่อ';

  @override
  String get categoryPersonalityClones => 'โคลนบุคลิกภาพ';

  @override
  String get categoryProductivityLifestyle => 'ประสิทธิภาพและไลฟ์สไตล์';

  @override
  String get categorySocialEntertainment => 'สังคมและความบันเทิง';

  @override
  String get categoryProductivityTools => 'เครื่องมือเพิ่มประสิทธิภาพ';

  @override
  String get categoryPersonalWellness => 'สุขภาพส่วนบุคคล';

  @override
  String get rating => 'คะแนน';

  @override
  String get categories => 'หมวดหมู่';

  @override
  String get sortBy => 'เรียงตาม';

  @override
  String get highestRating => 'คะแนนสูงสุด';

  @override
  String get lowestRating => 'คะแนนต่ำสุด';

  @override
  String get resetFilters => 'รีเซ็ตตัวกรอง';

  @override
  String get applyFilters => 'ใช้ตัวกรอง';

  @override
  String get mostInstalls => 'ติดตั้งมากที่สุด';

  @override
  String get couldNotOpenUrl => 'ไม่สามารถเปิด URL ได้ กรุณาลองอีกครั้ง';

  @override
  String get newTask => 'งานใหม่';

  @override
  String get viewAll => 'ดูทั้งหมด';

  @override
  String get addTask => 'เพิ่มงาน';

  @override
  String get addMcpServer => 'เพิ่มเซิร์ฟเวอร์ MCP';

  @override
  String get connectExternalAiTools => 'เชื่อมต่อเครื่องมือ AI ภายนอก';

  @override
  String get mcpServerUrl => 'MCP Server URL';

  @override
  String mcpServerConnected(int count) {
    return 'เชื่อมต่อ $count เครื่องมือสำเร็จ';
  }

  @override
  String get mcpConnectionFailed => 'ไม่สามารถเชื่อมต่อเซิร์ฟเวอร์ MCP ได้';

  @override
  String get authorizingMcpServer => 'กำลังอนุญาต...';

  @override
  String get whereDidYouHearAboutOmi => 'คุณพบเราได้อย่างไร?';

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
  String get friendWordOfMouth => 'เพื่อน';

  @override
  String get otherSource => 'อื่นๆ';

  @override
  String get pleaseSpecify => 'กรุณาระบุ';

  @override
  String get event => 'กิจกรรม';

  @override
  String get coworker => 'เพื่อนร่วมงาน';

  @override
  String get linkedIn => 'LinkedIn';

  @override
  String get appStore => 'App Store';

  @override
  String get googleSearch => 'Google Search';

  @override
  String get audioPlaybackUnavailable => 'ไฟล์เสียงไม่พร้อมสำหรับการเล่น';

  @override
  String get audioPlaybackFailed => 'ไม่สามารถเล่นเสียงได้ ไฟล์อาจเสียหายหรือหายไป';

  @override
  String get connectionGuide => 'คู่มือการเชื่อมต่อ';

  @override
  String get iveDoneThis => 'ฉันทำแล้ว';

  @override
  String get pairNewDevice => 'จับคู่อุปกรณ์ใหม่';

  @override
  String get dontSeeYourDevice => 'ไม่เห็นอุปกรณ์ของคุณ?';

  @override
  String get reportAnIssue => 'รายงานปัญหา';

  @override
  String get pairingTitleOmi => 'เปิด Omi';

  @override
  String get pairingDescOmi => 'กดค้างที่อุปกรณ์จนกว่าจะสั่นเพื่อเปิดเครื่อง';

  @override
  String get pairingTitleOmiDevkit => 'ตั้งค่า Omi DevKit ในโหมดจับคู่';

  @override
  String get pairingDescOmiDevkit => 'กดปุ่มหนึ่งครั้งเพื่อเปิด ไฟ LED จะกะพริบสีม่วงเมื่ออยู่ในโหมดจับคู่';

  @override
  String get pairingTitleOmiGlass => 'เปิด Omi Glass';

  @override
  String get pairingDescOmiGlass => 'กดปุ่มด้านข้างค้างไว้ 3 วินาทีเพื่อเปิดเครื่อง';

  @override
  String get pairingTitlePlaudNote => 'ตั้งค่า Plaud Note ในโหมดจับคู่';

  @override
  String get pairingDescPlaudNote => 'กดปุ่มด้านข้างค้างไว้ 2 วินาที ไฟ LED สีแดงจะกะพริบเมื่อพร้อมจับคู่';

  @override
  String get pairingTitleBee => 'ตั้งค่า Bee ในโหมดจับคู่';

  @override
  String get pairingDescBee => 'กดปุ่ม 5 ครั้งติดต่อกัน ไฟจะเริ่มกะพริบเป็นสีน้ำเงินและเขียว';

  @override
  String get pairingTitleLimitless => 'ตั้งค่า Limitless ในโหมดจับคู่';

  @override
  String get pairingDescLimitless => 'เมื่อมีไฟสว่าง กดหนึ่งครั้งแล้วกดค้างจนกว่าอุปกรณ์จะแสดงไฟสีชมพู จากนั้นปล่อย';

  @override
  String get pairingTitleFriendPendant => 'ตั้งค่า Friend Pendant ในโหมดจับคู่';

  @override
  String get pairingDescFriendPendant => 'กดปุ่มบนจี้เพื่อเปิด อุปกรณ์จะเข้าสู่โหมดจับคู่โดยอัตโนมัติ';

  @override
  String get pairingTitleFieldy => 'ตั้งค่า Fieldy ในโหมดจับคู่';

  @override
  String get pairingDescFieldy => 'กดค้างที่อุปกรณ์จนกว่าไฟจะปรากฏเพื่อเปิดเครื่อง';

  @override
  String get pairingTitleAppleWatch => 'เชื่อมต่อ Apple Watch';

  @override
  String get pairingDescAppleWatch => 'ติดตั้งและเปิดแอป Omi บน Apple Watch ของคุณ จากนั้นแตะเชื่อมต่อในแอป';

  @override
  String get pairingTitleNeoOne => 'ตั้งค่า Neo One ในโหมดจับคู่';

  @override
  String get pairingDescNeoOne => 'กดปุ่มเปิด/ปิดค้างจนกว่า LED จะกะพริบ อุปกรณ์จะสามารถค้นหาได้';

  @override
  String get downloadingFromDevice => 'กำลังดาวน์โหลดจากอุปกรณ์';

  @override
  String get reconnectingToInternet => 'กำลังเชื่อมต่ออินเทอร์เน็ตอีกครั้ง...';

  @override
  String uploadingToCloud(int current, int total) {
    return 'กำลังอัปโหลด $current จาก $total';
  }

  @override
  String get processedStatus => 'ประมวลผลแล้ว';

  @override
  String get corruptedStatus => 'เสียหาย';

  @override
  String nPending(int count) {
    return '$count รอดำเนินการ';
  }

  @override
  String nProcessed(int count) {
    return '$count ประมวลผลแล้ว';
  }

  @override
  String get synced => 'ซิงค์แล้ว';

  @override
  String get noPendingRecordings => 'ไม่มีการบันทึกที่รอดำเนินการ';

  @override
  String get noProcessedRecordings => 'ยังไม่มีการบันทึกที่ประมวลผลแล้ว';

  @override
  String get pending => 'รอดำเนินการ';

  @override
  String whatsNewInVersion(String version) {
    return 'มีอะไรใหม่ใน $version';
  }

  @override
  String get addToYourTaskList => 'เพิ่มในรายการงานของคุณ?';

  @override
  String get failedToCreateShareLink => 'ไม่สามารถสร้างลิงก์แชร์ได้';

  @override
  String get deleteGoal => 'ลบเป้าหมาย';

  @override
  String get deviceUpToDate => 'อุปกรณ์ของคุณเป็นเวอร์ชันล่าสุดแล้ว';

  @override
  String get wifiConfiguration => 'การตั้งค่า WiFi';

  @override
  String get wifiConfigurationSubtitle => 'ป้อนข้อมูล WiFi เพื่อให้อุปกรณ์ดาวน์โหลดเฟิร์มแวร์ได้';

  @override
  String get networkNameSsid => 'ชื่อเครือข่าย (SSID)';

  @override
  String get enterWifiNetworkName => 'ป้อนชื่อเครือข่าย WiFi';

  @override
  String get enterWifiPassword => 'ป้อนรหัสผ่าน WiFi';

  @override
  String get appIconLabel => 'App Icon';

  @override
  String get onboardingWhatIKnowAboutYouTitle => 'นี่คือสิ่งที่ฉันรู้เกี่ยวกับคุณ';

  @override
  String get onboardingWhatIKnowAboutYouDescription => 'แผนที่นี้จะอัปเดตเมื่อ Omi เรียนรู้จากการสนทนาของคุณ';

  @override
  String get apiEnvironment => 'สภาพแวดล้อม API';

  @override
  String get apiEnvironmentDescription => 'เลือกเซิร์ฟเวอร์ที่จะเชื่อมต่อ';

  @override
  String get production => 'โปรดักชัน';

  @override
  String get staging => 'สเตจจิ้ง';

  @override
  String get switchRequiresRestart => 'การสลับต้องรีสตาร์ทแอป';

  @override
  String get switchApiConfirmTitle => 'สลับสภาพแวดล้อม API';

  @override
  String switchApiConfirmBody(String environment) {
    return 'สลับไปที่ $environment? คุณจะต้องปิดและเปิดแอปใหม่เพื่อให้การเปลี่ยนแปลงมีผล';
  }

  @override
  String get switchAndRestart => 'สลับ';

  @override
  String get stagingDisclaimer =>
      'สภาพแวดล้อมทดสอบอาจไม่เสถียร มีประสิทธิภาพไม่สม่ำเสมอ และข้อมูลอาจสูญหาย สำหรับการทดสอบเท่านั้น';

  @override
  String get apiEnvSavedRestartRequired => 'บันทึกแล้ว ปิดและเปิดแอปใหม่เพื่อใช้งานการเปลี่ยนแปลง';

  @override
  String get shared => 'แชร์แล้ว';

  @override
  String get onlyYouCanSeeConversation => 'เฉพาะคุณเท่านั้นที่สามารถดูการสนทนานี้ได้';

  @override
  String get anyoneWithLinkCanView => 'ใครก็ตามที่มีลิงก์สามารถดูได้';

  @override
  String get tasksCleanTodayTitle => 'ล้างงานของวันนี้ไหม?';

  @override
  String get tasksCleanTodayMessage => 'การดำเนินการนี้จะลบเฉพาะกำหนดส่ง';

  @override
  String get tasksOverdue => 'เกินกำหนด';

  @override
  String get phoneCallsWithOmi => 'โทรกับ Omi';

  @override
  String get phoneCallsSubtitle => 'โทรพร้อมถอดความแบบเรียลไทม์';

  @override
  String get phoneSetupStep1Title => 'ยืนยันหมายเลขโทรศัพท์ของคุณ';

  @override
  String get phoneSetupStep1Subtitle => 'เราจะโทรหาคุณเพื่อยืนยัน';

  @override
  String get phoneSetupStep2Title => 'ป้อนรหัสยืนยัน';

  @override
  String get phoneSetupStep2Subtitle => 'รหัสสั้นที่คุณจะพิมพ์ขณะโทร';

  @override
  String get phoneSetupStep3Title => 'เริ่มโทรหารายชื่อของคุณ';

  @override
  String get phoneSetupStep3Subtitle => 'พร้อมการถอดความสดในตัว';

  @override
  String get phoneGetStarted => 'เริ่มต้น';

  @override
  String get callRecordingConsentDisclaimer => 'การบันทึกสายอาจต้องได้รับความยินยอมในเขตอำนาจศาลของคุณ';

  @override
  String get enterYourNumber => 'ป้อนหมายเลขของคุณ';

  @override
  String get phoneNumberCallerIdHint => 'หลังยืนยัน หมายเลขนี้จะเป็น ID ผู้โทรของคุณ';

  @override
  String get phoneNumberHint => 'หมายเลขโทรศัพท์';

  @override
  String get failedToStartVerification => 'ไม่สามารถเริ่มการยืนยัน';

  @override
  String get phoneContinue => 'ดำเนินการต่อ';

  @override
  String get verifyYourNumber => 'ยืนยันหมายเลขของคุณ';

  @override
  String get answerTheCallFrom => 'รับสายจาก';

  @override
  String get onTheCallEnterThisCode => 'ขณะโทร ป้อนรหัสนี้';

  @override
  String get followTheVoiceInstructions => 'ทำตามคำแนะนำเสียง';

  @override
  String get statusCalling => 'กำลังโทร...';

  @override
  String get statusCallInProgress => 'สายกำลังดำเนินอยู่';

  @override
  String get statusVerifiedLabel => 'ยืนยันแล้ว';

  @override
  String get statusCallMissed => 'สายที่ไม่ได้รับ';

  @override
  String get statusTimedOut => 'หมดเวลา';

  @override
  String get phoneTryAgain => 'ลองอีกครั้ง';

  @override
  String get phonePageTitle => 'โทรศัพท์';

  @override
  String get phoneContactsTab => 'รายชื่อ';

  @override
  String get phoneKeypadTab => 'แป้นกด';

  @override
  String get grantContactsAccess => 'ให้สิทธิ์เข้าถึงรายชื่อ';

  @override
  String get phoneAllow => 'อนุญาต';

  @override
  String get phoneSearchHint => 'ค้นหา';

  @override
  String get phoneNoContactsFound => 'ไม่พบรายชื่อ';

  @override
  String get phoneEnterNumber => 'ป้อนหมายเลข';

  @override
  String get failedToStartCall => 'ไม่สามารถเริ่มสาย';

  @override
  String get callStateConnecting => 'กำลังเชื่อมต่อ...';

  @override
  String get callStateRinging => 'กำลังดัง...';

  @override
  String get callStateEnded => 'สายสิ้นสุด';

  @override
  String get callStateFailed => 'สายล้มเหลว';

  @override
  String get transcriptPlaceholder => 'การถอดความจะปรากฏที่นี่...';

  @override
  String get phoneUnmute => 'เปิดเสียง';

  @override
  String get phoneMute => 'ปิดเสียง';

  @override
  String get phoneSpeaker => 'ลำโพง';

  @override
  String get phoneEndCall => 'วางสาย';

  @override
  String get phoneCallSettingsTitle => 'ตั้งค่าการโทร';

  @override
  String get yourVerifiedNumbers => 'หมายเลขที่ยืนยันแล้วของคุณ';

  @override
  String get verifiedNumbersDescription => 'เมื่อคุณโทรหาใครสักคน พวกเขาจะเห็นหมายเลขนี้';

  @override
  String get noVerifiedNumbers => 'ไม่มีหมายเลขที่ยืนยันแล้ว';

  @override
  String deletePhoneNumberConfirm(String phoneNumber) {
    return 'ลบ $phoneNumber?';
  }

  @override
  String get deletePhoneNumberWarning => 'คุณต้องยืนยันใหม่เพื่อโทรออก';

  @override
  String get phoneDeleteButton => 'ลบ';

  @override
  String verifiedMinutesAgo(int minutes) {
    return 'ยืนยัน $minutesนาทีที่แล้ว';
  }

  @override
  String verifiedHoursAgo(int hours) {
    return 'ยืนยัน $hoursชม.ที่แล้ว';
  }

  @override
  String verifiedDaysAgo(int days) {
    return 'ยืนยัน $daysวันที่แล้ว';
  }

  @override
  String verifiedOnDate(String date) {
    return 'ยืนยันเมื่อ $date';
  }

  @override
  String get verifiedFallback => 'ยืนยันแล้ว';

  @override
  String get callAlreadyInProgress => 'มีสายโทรศัพท์อยู่แล้ว';

  @override
  String get failedToGetCallToken => 'ไม่สามารถรับโทเค็น กรุณายืนยันหมายเลขก่อน';

  @override
  String get failedToInitializeCallService => 'ไม่สามารถเริ่มบริการโทรศัพท์';

  @override
  String get speakerLabelYou => 'คุณ';

  @override
  String get speakerLabelUnknown => 'ไม่ทราบ';

  @override
  String get showDailyScoreOnHomepage => 'แสดงคะแนนประจำวันบนหน้าหลัก';

  @override
  String get showTasksOnHomepage => 'แสดงงานบนหน้าหลัก';

  @override
  String get phoneCallsUnlimitedOnly => 'โทรศัพท์ผ่าน Omi';

  @override
  String get phoneCallsUpsellSubtitle => 'โทรผ่าน Omi และรับการถอดเสียงแบบเรียลไทม์ สรุปอัตโนมัติ และอื่นๆ';

  @override
  String get phoneCallsUpsellFeature1 => 'ถอดเสียงแบบเรียลไทม์ทุกสาย';

  @override
  String get phoneCallsUpsellFeature2 => 'สรุปสายอัตโนมัติและรายการดำเนินการ';

  @override
  String get phoneCallsUpsellFeature3 => 'ผู้รับเห็นหมายเลขจริงของคุณ ไม่ใช่หมายเลขสุ่ม';

  @override
  String get phoneCallsUpsellFeature4 => 'สายของคุณยังคงเป็นส่วนตัวและปลอดภัย';

  @override
  String get phoneCallsUpgradeButton => 'อัปเกรดเป็น Unlimited';

  @override
  String get phoneCallsMaybeLater => 'ไว้ทีหลัง';

  @override
  String get deleteSynced => 'ลบที่ซิงค์แล้ว';

  @override
  String get deleteSyncedFiles => 'ลบการบันทึกที่ซิงค์แล้ว';

  @override
  String get deleteSyncedFilesMessage => 'การบันทึกเหล่านี้ซิงค์กับโทรศัพท์ของคุณแล้ว ไม่สามารถย้อนกลับได้';

  @override
  String get syncedFilesDeleted => 'ลบการบันทึกที่ซิงค์แล้ว';

  @override
  String get deletePending => 'ลบที่รอดำเนินการ';

  @override
  String get deletePendingFiles => 'ลบการบันทึกที่รอดำเนินการ';

  @override
  String get deletePendingFilesWarning =>
      'การบันทึกเหล่านี้ยังไม่ได้ซิงค์กับโทรศัพท์ของคุณและจะสูญหายถาวร ไม่สามารถย้อนกลับได้';

  @override
  String get pendingFilesDeleted => 'ลบการบันทึกที่รอดำเนินการแล้ว';

  @override
  String get deleteAllFiles => 'ลบการบันทึกทั้งหมด';

  @override
  String get deleteAll => 'ลบทั้งหมด';

  @override
  String get deleteAllFilesWarning =>
      'การดำเนินการนี้จะลบการบันทึกที่ซิงค์แล้วและที่รอดำเนินการ การบันทึกที่รอดำเนินการยังไม่ได้ซิงค์และจะสูญหายถาวร';

  @override
  String get allFilesDeleted => 'ลบการบันทึกทั้งหมดแล้ว';

  @override
  String nFiles(int count) {
    return '$count การบันทึก';
  }

  @override
  String get manageStorage => 'จัดการพื้นที่จัดเก็บ';

  @override
  String get safelyBackedUp => 'สำรองข้อมูลไว้ในโทรศัพท์อย่างปลอดภัย';

  @override
  String get notYetSynced => 'ยังไม่ได้ซิงค์กับโทรศัพท์ของคุณ';

  @override
  String get clearAll => 'ล้างทั้งหมด';

  @override
  String get phoneKeypad => 'แป้นกด';

  @override
  String get phoneHideKeypad => 'ซ่อนแป้นกด';

  @override
  String get fairUsePolicy => 'การใช้งานอย่างเป็นธรรม';

  @override
  String get fairUseLoadError => 'ไม่สามารถโหลดสถานะการใช้งานอย่างเป็นธรรมได้ กรุณาลองอีกครั้ง';

  @override
  String get fairUseStatusNormal => 'การใช้งานของคุณอยู่ในขีดจำกัดปกติ';

  @override
  String get fairUseStageNormal => 'ปกติ';

  @override
  String get fairUseStageWarning => 'คำเตือน';

  @override
  String get fairUseStageThrottle => 'ถูกจำกัด';

  @override
  String get fairUseStageRestrict => 'ถูกระงับ';

  @override
  String get fairUseSpeechUsage => 'การใช้งานเสียงพูด';

  @override
  String get fairUseToday => 'วันนี้';

  @override
  String get fairUse3Day => '3 วันต่อเนื่อง';

  @override
  String get fairUseWeekly => 'รายสัปดาห์ต่อเนื่อง';

  @override
  String get fairUseAboutTitle => 'เกี่ยวกับการใช้งานอย่างเป็นธรรม';

  @override
  String get fairUseAboutBody =>
      'Omi ออกแบบมาสำหรับการสนทนาส่วนตัว การประชุม และการโต้ตอบสด การใช้งานวัดจากเวลาพูดจริงที่ตรวจพบ ไม่ใช่เวลาเชื่อมต่อ หากการใช้งานเกินรูปแบบปกติอย่างมากสำหรับเนื้อหาที่ไม่ใช่ส่วนบุคคล อาจมีการปรับเปลี่ยน';

  @override
  String fairUseCaseRefCopied(String caseRef) {
    return 'คัดลอก $caseRef แล้ว';
  }

  @override
  String get fairUseDailyTranscription => 'Daily Transcription';

  @override
  String fairUseBudgetUsed(String used, String limit) {
    return '${used}m / ${limit}m';
  }

  @override
  String get fairUseBudgetExhausted => 'Daily transcription limit reached';

  @override
  String fairUseBudgetResetsAt(String time) {
    return 'Resets $time';
  }

  @override
  String get transcriptionPaused => 'กำลังบันทึก, กำลังเชื่อมต่อใหม่';

  @override
  String get transcriptionPausedReconnecting => 'ยังคงบันทึกอยู่ — กำลังเชื่อมต่อกับการถอดเสียงใหม่...';

  @override
  String fairUseBannerStatus(String status) {
    return 'การใช้งานอย่างเป็นธรรม: $status';
  }

  @override
  String get improveConnectionTitle => 'ปรับปรุงการเชื่อมต่อ';

  @override
  String get improveConnectionContent =>
      'เราได้ปรับปรุงวิธีที่ Omi เชื่อมต่อกับอุปกรณ์ของคุณ เพื่อเปิดใช้งาน ให้ไปที่หน้าข้อมูลอุปกรณ์ แตะ \"ยกเลิกการเชื่อมต่ออุปกรณ์\" แล้วจับคู่อุปกรณ์อีกครั้ง';

  @override
  String get improveConnectionAction => 'เข้าใจแล้ว';

  @override
  String clockSkewWarning(int minutes) {
    return 'นาฬิกาอุปกรณ์ของคุณคลาดเคลื่อน ~$minutes นาที ตรวจสอบการตั้งค่าวันที่และเวลา';
  }
}
