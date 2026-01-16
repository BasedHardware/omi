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
  String get copyTranscript => 'คัดลอกบันทึก';

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
  String get searchApps => 'ค้นหาแอป...';

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
  String get webhooks => 'Webhooks';

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
  String get descriptionOptional => 'คำอธิบาย (ตัวเลือก)';

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
  String get unknownDevice => 'อุปกรณ์ที่ไม่รู้จัก';

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
    return '$label copied';
  }

  @override
  String get noApiKeysYet => 'ยังไม่มีคีย์ API สร้างคีย์เพื่อเชื่อมต่อกับแอปของคุณ';

  @override
  String get createKeyToGetStarted => 'Create a key to get started';

  @override
  String get persona => 'บุคลิกภาพ';

  @override
  String get configureYourAiPersona => 'Configure your AI persona';

  @override
  String get configureSttProvider => 'Configure STT provider';

  @override
  String get setWhenConversationsAutoEnd => 'Set when conversations auto-end';

  @override
  String get importDataFromOtherSources => 'Import data from other sources';

  @override
  String get debugAndDiagnostics => 'การดีบักและการวินิจฉัย';

  @override
  String get autoDeletesAfter3Days => 'ลบอัตโนมัติหลังจาก 3 วัน';

  @override
  String get helpsDiagnoseIssues => 'ช่วยวินิจฉัยปัญหา';

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
  String get autoCreateWhenNameDetected => 'Auto-create when name detected';

  @override
  String get followUpQuestions => 'คำถามติดตาม';

  @override
  String get suggestQuestionsAfterConversations => 'แนะนำคำถามหลังจากการสนทนา';

  @override
  String get goalTracker => 'ตัวติดตามเป้าหมาย';

  @override
  String get trackPersonalGoalsOnHomepage => 'Track your personal goals on homepage';

  @override
  String get dailyReflection => 'การไตร่ตรองประจำวัน';

  @override
  String get get9PmReminderToReflect => 'Get a 9 PM reminder to reflect on your day';

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
  String get noTasksForToday => 'ไม่มีงานสำหรับวันนี้\\nถาม Omi เพื่อรับงานเพิ่มเติมหรือสร้างด้วยตนเอง';

  @override
  String get dailyScore => 'คะแนนประจำวัน';

  @override
  String get dailyScoreDescription => 'คะแนนที่ช่วยให้คุณโฟกัสกับการดำเนินการได้ดีขึ้น';

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
  String installsCount(String count) {
    return '$count+ การติดตั้ง';
  }

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
  String get aboutThePersona => 'เกี่ยวกับบุคลิก';

  @override
  String get chatPersonality => 'บุคลิกการแชท';

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
  String get takePhoto => 'ถ่ายภาพ';

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
  String get discardedConversation => 'การสนทนาที่ถูกทิ้ง';

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
  String get starred => 'ที่ติดดาว';

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
  String get noSummaryForApp => 'ไม่มีสรุปสำหรับแอปนี้ ลองแอปอื่นเพื่อผลลัพธ์ที่ดีขึ้น';

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
  String get signOutConfirmation => 'คุณแน่ใจหรือว่าต้องการออกจากระบบ?';

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
  String get dailySummaryDescription => 'รับสรุปส่วนตัวของการสนทนาของคุณ';

  @override
  String get deliveryTime => 'เวลาจัดส่ง';

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
  String get dailyReflectionDescription => 'การแจ้งเตือนเวลา 21.00 น. เพื่อไตร่ตรองวันของคุณ';

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
  String get invalidIntegrationUrl => 'URL การรวมระบบไม่ถูกต้อง';

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
  String get failedToSubmitReview => 'ไม่สามารถส่งรีวิวได้ กรุณาลองอีกครั้ง';

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
      'This app will access your data. Omi AI is not responsible for how your data is used, modified, or deleted by this app';

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
  String get omiTraining => 'การฝึก Omi';

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
  String get cancelSubscription => 'ยกเลิกการสมัคร';

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
}
