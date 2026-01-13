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
  String get deleteConversationMessage => 'คุณแน่ใจหรือไม่ว่าต้องการลบบทสนทนานี้? การดำเนินการนี้ไม่สามารถยกเลิกได้';

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
  String get copyTranscript => 'คัดลอกบันทึกเสียง';

  @override
  String get copySummary => 'คัดลอกสรุป';

  @override
  String get testPrompt => 'ทดสอบคำสั่ง';

  @override
  String get reprocessConversation => 'ประมวลผลบทสนทนาใหม่';

  @override
  String get deleteConversation => 'ลบบทสนทนา';

  @override
  String get contentCopied => 'คัดลอกเนื้อหาไปยังคลิปบอร์ดแล้ว';

  @override
  String get failedToUpdateStarred => 'ไม่สามารถอัปเดตสถานะการติดดาวได้';

  @override
  String get conversationUrlNotShared => 'ไม่สามารถแชร์ URL บทสนทนาได้';

  @override
  String get errorProcessingConversation => 'เกิดข้อผิดพลาดขณะประมวลผลบทสนทนา กรุณาลองใหม่ภายหลัง';

  @override
  String get noInternetConnection => 'กรุณาตรวจสอบการเชื่อมต่ออินเทอร์เน็ตของคุณและลองใหม่อีกครั้ง';

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
  String get disconnected => 'ตัดการเชื่อมต่อแล้ว';

  @override
  String get searching => 'กำลังค้นหา';

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
  String get noConversationsYet => 'ยังไม่มีบทสนทนา';

  @override
  String get noStarredConversations => 'ยังไม่มีบทสนทนาที่ติดดาว';

  @override
  String get starConversationHint => 'หากต้องการติดดาวบทสนทนา ให้เปิดและแตะไอคอนดาวในส่วนหัว';

  @override
  String get searchConversations => 'ค้นหาบทสนทนา';

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
  String get deletingMessages => 'กำลังลบข้อความของคุณจากความทรงจำของ Omi...';

  @override
  String get messageCopied => 'คัดลอกข้อความไปยังคลิปบอร์ดแล้ว';

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
  String get clearChat => 'ล้างแชท?';

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
  String get searchApps => 'ค้นหา 1,500+ แอป';

  @override
  String get myApps => 'แอปของฉัน';

  @override
  String get installedApps => 'แอปที่ติดตั้ง';

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
  String get helpOrInquiries => 'ต้องการความช่วยเหลือหรือสอบถามข้อมูล?';

  @override
  String get joinCommunity => 'เข้าร่วมชุมชน!';

  @override
  String get membersAndCounting => 'สมาชิก 8,000+ คนและกำลังเพิ่มขึ้น';

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
  String get conversationDisplay => 'การแสดงผลบทสนทนา';

  @override
  String get dataPrivacy => 'ข้อมูลและความเป็นส่วนตัว';

  @override
  String get userId => 'รหัสผู้ใช้';

  @override
  String get notSet => 'ยังไม่ได้ตั้งค่า';

  @override
  String get userIdCopied => 'คัดลอกรหัสผู้ใช้ไปยังคลิปบอร์ดแล้ว';

  @override
  String get systemDefault => 'ค่าเริ่มต้นของระบบ';

  @override
  String get planAndUsage => 'แผนและการใช้งาน';

  @override
  String get offlineSync => 'ซิงค์แบบออฟไลน์';

  @override
  String get deviceSettings => 'การตั้งค่าอุปกรณ์';

  @override
  String get chatTools => 'เครื่องมือแชท';

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
  String get deviceId => 'รหัสอุปกรณ์';

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
  String get upgradeToUnlimited => 'อัปเกรดเป็นแบบไม่จำกัด';

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
  String get debugLogs => 'บันทึกการแก้ไขจุดบกพร่อง';

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
  String get knowledgeGraphDeleted => 'ลบกราฟความรู้สำเร็จแล้ว';

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
  String get webhooks => 'Webhooks';

  @override
  String get conversationEvents => 'เหตุการณ์บทสนทนา';

  @override
  String get newConversationCreated => 'สร้างบทสนทนาใหม่แล้ว';

  @override
  String get realtimeTranscript => 'บันทึกเสียงแบบเรียลไทม์';

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
  String get chatToolsFooter => 'เชื่อมต่อแอปของคุณเพื่อดูข้อมูลและตัวชี้วัดในแชท';

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
  String get noUpcomingMeetings => 'ไม่พบการประชุมที่กำลังจะมาถึง';

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
  String get apiKey => 'API Key';

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
  String deviceUsesCodec(String deviceName, String codecReason) {
    return '$deviceName ใช้ $codecReason จะใช้ Omi แทน';
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
  String get appName => 'ชื่อแอป';

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
  String get makePublic => 'ทำให้เป็นสาธารณะ';

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
  String get dontShowAgain => 'อย่าแสดงอีก';

  @override
  String get iUnderstand => 'ฉันเข้าใจ';

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
  String get grantPermissions => 'อนุญาตสิทธิ์';

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
  String get maybeLater => 'ทีหลังก็ได้';

  @override
  String get speechProfileIntro => 'Omi ต้องเรียนรู้เป้าหมายและเสียงของคุณ คุณสามารถแก้ไขได้ในภายหลัง';

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
  String get personalGrowthJourney => 'เส้นทางการเติบโตส่วนบุคคลของคุณกับ AI ที่ฟังทุกคำพูดของคุณ';

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
  String get deleteActionItemTitle => 'ลบสิ่งที่ต้องทำ';

  @override
  String get deleteActionItemMessage => 'คุณแน่ใจหรือไม่ว่าต้องการลบสิ่งที่ต้องทำนี้?';

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
  String searchMemories(int count) {
    return 'ค้นหา $count ความทรงจำ';
  }

  @override
  String get memoryDeleted => 'ลบความทรงจำแล้ว';

  @override
  String get undo => 'เลิกทำ';

  @override
  String get noMemoriesYet => 'ยังไม่มีความทรงจำ';

  @override
  String get noAutoMemories => 'ยังไม่มีความทรงจำที่ดึงอัตโนมัติ';

  @override
  String get noManualMemories => 'ยังไม่มีความทรงจำที่สร้างด้วยตนเอง';

  @override
  String get noMemoriesInCategories => 'ไม่มีความทรงจำในหมวดหมู่เหล่านี้';

  @override
  String get noMemoriesFound => 'ไม่พบความทรงจำ';

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
  String get newMemory => 'ความทรงจำใหม่';

  @override
  String get editMemory => 'แก้ไขความทรงจำ';

  @override
  String get memoryContentHint => 'ฉันชอบกินไอศกรีม...';

  @override
  String get failedToSaveMemory => 'บันทึกไม่สำเร็จ กรุณาตรวจสอบการเชื่อมต่อของคุณ';

  @override
  String get saveMemory => 'บันทึกความทรงจำ';

  @override
  String get retry => 'ลองใหม่';

  @override
  String get createActionItem => 'สร้างสิ่งที่ต้องทำ';

  @override
  String get editActionItem => 'แก้ไขสิ่งที่ต้องทำ';

  @override
  String get actionItemDescriptionHint => 'ต้องทำอะไร?';

  @override
  String get actionItemDescriptionEmpty => 'คำอธิบายสิ่งที่ต้องทำต้องไม่ว่างเปล่า';

  @override
  String get actionItemUpdated => 'อัปเดตสิ่งที่ต้องทำแล้ว';

  @override
  String get failedToUpdateActionItem => 'อัปเดตสิ่งที่ต้องทำไม่สำเร็จ';

  @override
  String get actionItemCreated => 'สร้างสิ่งที่ต้องทำแล้ว';

  @override
  String get failedToCreateActionItem => 'สร้างสิ่งที่ต้องทำไม่สำเร็จ';

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
  String get completed => 'เสร็จสมบูรณ์';

  @override
  String get markComplete => 'ทำเครื่องหมายว่าเสร็จสมบูรณ์';

  @override
  String get actionItemDeleted => 'ลบสิ่งที่ต้องทำแล้ว';

  @override
  String get failedToDeleteActionItem => 'ลบสิ่งที่ต้องทำไม่สำเร็จ';

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
}
