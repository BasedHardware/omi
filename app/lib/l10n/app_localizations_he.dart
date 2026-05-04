// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Hebrew (`he`).
class AppLocalizationsHe extends AppLocalizations {
  AppLocalizationsHe([String locale = 'he']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'שיחה';

  @override
  String get transcriptTab => 'תמלול';

  @override
  String get actionItemsTab => 'פריטים לביצוע';

  @override
  String get deleteConversationTitle => 'מחיקת שיחה?';

  @override
  String get deleteConversationMessage =>
      'פעולה זו תמחק גם זיכרונות משויכים, משימות וקבצי אודיו. לא ניתן לבטל פעולה זו.';

  @override
  String get confirm => 'אישור';

  @override
  String get cancel => 'ביטול';

  @override
  String get ok => 'אוקיי';

  @override
  String get delete => 'מחיקה';

  @override
  String get add => 'הוסף';

  @override
  String get update => 'עדכון';

  @override
  String get save => 'שמור';

  @override
  String get edit => 'עריכה';

  @override
  String get close => 'סגור';

  @override
  String get clear => 'נקה';

  @override
  String get copyTranscript => 'העתק תמלול';

  @override
  String get copySummary => 'העתק סיכום';

  @override
  String get testPrompt => 'בדוק הנושא';

  @override
  String get reprocessConversation => 'עבד מחדש שיחה';

  @override
  String get deleteConversation => 'מחק שיחה';

  @override
  String get contentCopied => 'התוכן הועתק ללוח הגזוזים';

  @override
  String get failedToUpdateStarred => 'כשל בעדכון מצב כוכב.';

  @override
  String get conversationUrlNotShared => 'לא ניתן היה לשתף את כתובת ה-URL של השיחה.';

  @override
  String get errorProcessingConversation => 'שגיאה בעיבוד השיחה. אנא נסה שוב מאוחר יותר.';

  @override
  String get noInternetConnection => 'אין חיבור לאינטרנט';

  @override
  String get unableToDeleteConversation => 'לא ניתן למחוק שיחה';

  @override
  String get somethingWentWrong => 'משהו השתבש! אנא נסה שוב מאוחר יותר.';

  @override
  String get copyErrorMessage => 'העתק הודעת שגיאה';

  @override
  String get errorCopied => 'הודעת השגיאה הועתקה ללוח הגזוזים';

  @override
  String get remaining => 'נותר';

  @override
  String get loading => 'טוען...';

  @override
  String get loadingDuration => 'טוען משך זמן...';

  @override
  String secondsCount(int count) {
    return '$count שניות';
  }

  @override
  String get people => 'אנשים';

  @override
  String get addNewPerson => 'הוסף אדם חדש';

  @override
  String get editPerson => 'ערוך אדם';

  @override
  String get createPersonHint => 'צור אדם חדש והדרך את Omi להכיר את קולם!';

  @override
  String get speechProfile => 'פרופיל דיבור';

  @override
  String sampleNumber(int number) {
    return 'דוגמה $number';
  }

  @override
  String get settings => 'הגדרות';

  @override
  String get language => 'שפה';

  @override
  String get selectLanguage => 'בחר שפה';

  @override
  String get deleting => 'מוחק...';

  @override
  String get pleaseCompleteAuthentication => 'אנא השלם אימות בדפדפן שלך. לאחר שתסיים, חזור לאפליקציה.';

  @override
  String get failedToStartAuthentication => 'כשל בהתחלת אימות';

  @override
  String get importStarted => 'היבוא החל! תקבל הודעה כאשר הוא יסתיים.';

  @override
  String get failedToStartImport => 'כשל בהתחלת ייבוא. אנא נסה שוב.';

  @override
  String get couldNotAccessFile => 'לא ניתן היה לגשת לקובץ שנבחר';

  @override
  String get askOmi => 'שאל את Omi';

  @override
  String get done => 'בוצע';

  @override
  String get disconnected => 'מנותק';

  @override
  String get searching => 'חיפוש...';

  @override
  String get connectDevice => 'התחבר למכשיר';

  @override
  String get monthlyLimitReached => 'הגעת למגבלה החודשית שלך.';

  @override
  String get checkUsage => 'בדוק שימוש';

  @override
  String get syncingRecordings => 'סינכרון הקלטות';

  @override
  String get recordingsToSync => 'הקלטות לסינכרון';

  @override
  String get allCaughtUp => 'הכל עדכני';

  @override
  String get sync => 'סינכרון';

  @override
  String get pendantUpToDate => 'התליון עדכני';

  @override
  String get allRecordingsSynced => 'כל ההקלטות סונכרנו';

  @override
  String get syncingInProgress => 'סינכרון בתהליך';

  @override
  String get readyToSync => 'מוכן לסינכרון';

  @override
  String get tapSyncToStart => 'הקש סינכרון להתחלה';

  @override
  String get pendantNotConnected => 'התליון לא מחובר. התחבר כדי לסנכרן.';

  @override
  String get everythingSynced => 'הכל כבר סונכרן.';

  @override
  String get recordingsNotSynced => 'יש לך הקלטות שעדיין לא סונכרנו.';

  @override
  String get syncingBackground => 'נמשיך לסנכרן את ההקלטות שלך ברקע.';

  @override
  String get noConversationsYet => 'אין שיחות עדיין';

  @override
  String get noStarredConversations => 'אין שיחות מכוכבות';

  @override
  String get starConversationHint => 'כדי להוסיף כוכב לשיחה, פתח אותה והקש על אייקון הכוכב בכותרת.';

  @override
  String get searchConversations => 'חפש שיחות...';

  @override
  String selectedCount(int count, Object s) {
    return '$count נבחרו';
  }

  @override
  String get merge => 'מזג';

  @override
  String get mergeConversations => 'מזג שיחות';

  @override
  String mergeConversationsMessage(int count) {
    return 'פעולה זו תשלב $count שיחות לאחת. כל התוכן יוזג ויוחדש.';
  }

  @override
  String get mergingInBackground => 'מיזוג ברקע. זה אולי ייקח רגע.';

  @override
  String get failedToStartMerge => 'כשל בהתחלת מיזוג';

  @override
  String get askAnything => 'שאל כל דבר';

  @override
  String get noMessagesYet => 'אין הודעות עדיין!\nלמה לא תתחיל שיחה?';

  @override
  String get deletingMessages => 'מוחק את ההודעות שלך מהזיכרון של Omi...';

  @override
  String get messageCopied => '✨ הודעה הועתקה ללוח הגזוזים';

  @override
  String get cannotReportOwnMessage => 'אתה לא יכול לדווח על ההודעות שלך.';

  @override
  String get reportMessage => 'דווח על הודעה';

  @override
  String get reportMessageConfirm => 'האם אתה בטוח שברצונך לדווח על הודעה זו?';

  @override
  String get messageReported => 'הודעה דווחה בהצלחה.';

  @override
  String get thankYouFeedback => 'תודה על הקבלת הדעות!';

  @override
  String get clearChat => 'נקה צ\'ט';

  @override
  String get clearChatConfirm => 'האם אתה בטוח שברצונך לנקות את הצ\'ט? לא ניתן לבטל פעולה זו.';

  @override
  String get maxFilesLimit => 'אתה יכול להעלות רק 4 קבצים בכל פעם';

  @override
  String get chatWithOmi => 'צ\'ט עם Omi';

  @override
  String get apps => 'אפליקציות';

  @override
  String get noAppsFound => 'לא נמצאו אפליקציות';

  @override
  String get tryAdjustingSearch => 'נסה להתאים את החיפוש או את המסננים שלך';

  @override
  String get createYourOwnApp => 'צור את האפליקציה שלך';

  @override
  String get buildAndShareApp => 'בנה ושתף אפליקציה מותאמת אישית';

  @override
  String get searchApps => 'חפש אפליקציות...';

  @override
  String get myApps => 'האפליקציות שלי';

  @override
  String get installedApps => 'אפליקציות מותקנות';

  @override
  String get unableToFetchApps => 'לא ניתן להביא אפליקציות :(\n\nבדוק את חיבור האינטרנט שלך ונסה שוב.';

  @override
  String get aboutOmi => 'על Omi';

  @override
  String get privacyPolicy => 'מדיניות הפרטיות';

  @override
  String get visitWebsite => 'בקר בדף הבית';

  @override
  String get helpOrInquiries => 'עזרה או שאלות?';

  @override
  String get joinCommunity => 'הצטרף לקהילה!';

  @override
  String get membersAndCounting => '8000+ חברים וסופר.';

  @override
  String get deleteAccountTitle => 'מחיקת חשבון';

  @override
  String get deleteAccountConfirm => 'האם אתה בטוח שברצונך למחוק את החשבון שלך?';

  @override
  String get cannotBeUndone => 'לא ניתן לבטל זאת.';

  @override
  String get allDataErased => 'כל הזיכרונות והשיחות שלך יימחקו לצמיתות.';

  @override
  String get appsDisconnected => 'האפליקציות והאינטגרציות שלך יהיו מנותקות באופן מיידי.';

  @override
  String get exportBeforeDelete =>
      'אתה יכול לייצא את הנתונים שלך לפני מחיקת החשבון, אך לאחר מחיקה, לא ניתן להחזיר אותם.';

  @override
  String get deleteAccountCheckbox =>
      'אני מבין שמחיקת החשבון שלי היא קבע וכל הנתונים, כולל זיכרונות ושיחות, יימחקו ולא יוכלו להיאחזר.';

  @override
  String get areYouSure => 'האם אתה בטוח?';

  @override
  String get deleteAccountFinal =>
      'פעולה זו בלתי הפיכה ותמחק לצמיתות את החשבון שלך ואת כל הנתונים המשויכים. האם אתה בטוח שברצונך להמשיך?';

  @override
  String get deleteNow => 'מחק עכשיו';

  @override
  String get goBack => 'חזור';

  @override
  String get checkBoxToConfirm => 'סמן את התיבה כדי לאשר שאתה מבין שמחיקת החשבון שלך היא קבע ובלתי הפיכה.';

  @override
  String get profile => 'פרופיל';

  @override
  String get name => 'שם';

  @override
  String get email => 'דוא\"ל';

  @override
  String get customVocabulary => 'אוצר מילים מותאם';

  @override
  String get identifyingOthers => 'זיהוי אחרים';

  @override
  String get paymentMethods => 'שיטות תשלום';

  @override
  String get conversationDisplay => 'תצוגת שיחה';

  @override
  String get dataPrivacy => 'פרטיות הנתונים';

  @override
  String get userId => 'מזהה משתמש';

  @override
  String get notSet => 'לא הוגדר';

  @override
  String get userIdCopied => 'מזהה המשתמש הועתק ללוח הגזוזים';

  @override
  String get systemDefault => 'ברירת מחדל של מערכת';

  @override
  String get planAndUsage => 'תוכנית ושימוש';

  @override
  String get offlineSync => 'סינכרון במצב לא מחובר';

  @override
  String get deviceSettings => 'הגדרות המכשיר';

  @override
  String get integrations => 'אינטגרציות';

  @override
  String get feedbackBug => 'משוב / באג';

  @override
  String get helpCenter => 'מרכז עזרה';

  @override
  String get developerSettings => 'הגדרות מפתח';

  @override
  String get getOmiForMac => 'קבל Omi ל-Mac';

  @override
  String get referralProgram => 'תוכנית הפניה';

  @override
  String get signOut => 'התנתקות';

  @override
  String get appAndDeviceCopied => 'פרטי אפליקציה ומכשיר הועתקו';

  @override
  String get wrapped2025 => 'Wrapped 2025';

  @override
  String get yourPrivacyYourControl => 'הפרטיות שלך, השליטה שלך';

  @override
  String get privacyIntro =>
      'ב-Omi, אנחנו מתחייבים להגן על הפרטיות שלך. דף זה מאפשר לך לשלוט בכיצד הנתונים שלך מאוחסנים ומשומשים.';

  @override
  String get learnMore => 'למד עוד...';

  @override
  String get dataProtectionLevel => 'רמת הגנה נתונים';

  @override
  String get dataProtectionDesc =>
      'הנתונים שלך מאובטחים כברירת מחדל בהצפנה חזקה. בדוק את ההגדרות שלך ואפשרויות הפרטיות העתידיות להלן.';

  @override
  String get appAccess => 'גישה אפליקציה';

  @override
  String get appAccessDesc => 'האפליקציות הבאות יכולות לגשת לנתונים שלך. הקש על אפליקציה כדי לנהל את ההרשאות שלה.';

  @override
  String get noAppsExternalAccess => 'אף אפליקציה מותקנת אין גישה חיצונית לנתונים שלך.';

  @override
  String get deviceName => 'שם המכשיר';

  @override
  String get deviceId => 'מזהה המכשיר';

  @override
  String get firmware => 'Firmware';

  @override
  String get sdCardSync => 'סינכרון כרטיס SD';

  @override
  String get hardwareRevision => 'גרסת חומרה';

  @override
  String get modelNumber => 'מספר דגם';

  @override
  String get manufacturer => 'יצרן';

  @override
  String get doubleTap => 'לחץ כפול';

  @override
  String get ledBrightness => 'בהיקות LED';

  @override
  String get micGain => 'הגברת מיקרופון';

  @override
  String get disconnect => 'התנתק';

  @override
  String get forgetDevice => 'שכח מכשיר';

  @override
  String get chargingIssues => 'בעיות טעינה';

  @override
  String get disconnectDevice => 'התנתק מכשיר';

  @override
  String get unpairDevice => 'בטל זיווג מכשיר';

  @override
  String get unpairAndForget => 'בטל זיווג ושכח מכשיר';

  @override
  String get deviceDisconnectedMessage => 'ה-Omi שלך נותק 😔';

  @override
  String get deviceUnpairedMessage =>
      'מכשיר לא זוווג. עבור להגדרות > Bluetooth ושכח את המכשיר כדי להשלים את הביטול זיווג.';

  @override
  String get unpairDialogTitle => 'בטל זיווג מכשיר';

  @override
  String get unpairDialogMessage =>
      'פעולה זו תבטל את זיווג המכשיר כדי שניתן יהיה להתחברות אותו לטלפון אחר. תצטרך לעבור להגדרות > Bluetooth ולשכוח את המכשיר כדי להשלים את התהליך.';

  @override
  String get deviceNotConnected => 'מכשיר לא מחובר';

  @override
  String get connectDeviceMessage => 'התחבר לעצמך Omi כדי לגשת\nלהגדרות מכשיר וקילוף';

  @override
  String get deviceInfoSection => 'מידע מכשיר';

  @override
  String get customizationSection => 'התאמה אישית';

  @override
  String get hardwareSection => 'חומרה';

  @override
  String get v2Undetected => 'V2 לא זוהה';

  @override
  String get v2UndetectedMessage =>
      'אנו רואים שיש לך מכשיר V1 או שהמכשיר שלך לא מחובר. פונקציונליות כרטיס SD זמינה רק למכשירי V2.';

  @override
  String get endConversation => 'סיים שיחה';

  @override
  String get pauseResume => 'השהה/המשך';

  @override
  String get starConversation => 'כוכב שיחה';

  @override
  String get doubleTapAction => 'פעולת לחיצה כפולה';

  @override
  String get endAndProcess => 'סיים ועבד שיחה';

  @override
  String get pauseResumeRecording => 'השהה/המשך הקלטה';

  @override
  String get starOngoing => 'כוכב שיחה מתמשכת';

  @override
  String get off => 'כבוי';

  @override
  String get max => 'מקסימום';

  @override
  String get mute => 'השתק';

  @override
  String get quiet => 'שקט';

  @override
  String get normal => 'רגיל';

  @override
  String get high => 'גבוה';

  @override
  String get micGainDescMuted => 'המיקרופון מושתק';

  @override
  String get micGainDescLow => 'שקט מאוד - לסביבות רועשות';

  @override
  String get micGainDescModerate => 'שקט - לרעש בינוני';

  @override
  String get micGainDescNeutral => 'ניטרלי - הקלטה מאוזנת';

  @override
  String get micGainDescSlightlyBoosted => 'מוגבר מעט - שימוש רגיל';

  @override
  String get micGainDescBoosted => 'מוגבר - לסביבות שקטות';

  @override
  String get micGainDescHigh => 'גבוה - לקולות רחוקים או קשים';

  @override
  String get micGainDescVeryHigh => 'גבוה מאוד - למקורות שקטים מאוד';

  @override
  String get micGainDescMax => 'מקסימום - השתמש בזהירות';

  @override
  String get developerSettingsTitle => 'הגדרות מפתח';

  @override
  String get saving => 'שומר...';

  @override
  String get beta => 'בטא';

  @override
  String get transcription => 'תמלול';

  @override
  String get transcriptionConfig => 'קבע ספק STT';

  @override
  String get conversationTimeout => 'תגבול זמן שיחה';

  @override
  String get conversationTimeoutConfig => 'הגדר מתי שיחות מסתיימות באופן אוטומטי';

  @override
  String get importData => 'ייבוא נתונים';

  @override
  String get importDataConfig => 'ייבא נתונים ממקורות אחרים';

  @override
  String get debugDiagnostics => 'ניפוי באגים ואבחון';

  @override
  String get endpointUrl => 'כתובת URL של נקודה קצה';

  @override
  String get noApiKeys => 'אין מפתחות API עדיין';

  @override
  String get createKeyToStart => 'צור מפתח כדי להתחיל';

  @override
  String get createKey => 'צור מפתח';

  @override
  String get docs => 'תיעוד';

  @override
  String get yourOmiInsights => 'ההשקפות שלך של Omi';

  @override
  String get today => 'היום';

  @override
  String get thisMonth => 'חודש זה';

  @override
  String get thisYear => 'השנה';

  @override
  String get allTime => 'כל הזמן';

  @override
  String get noActivityYet => 'אין פעילות עדיין';

  @override
  String get startConversationToSeeInsights => 'התחל שיחה עם Omi\nכדי לראות את תובנות השימוש שלך כאן.';

  @override
  String get listening => 'הקשבה';

  @override
  String get listeningSubtitle => 'סך הזמן ש-Omi האזין בפעילות.';

  @override
  String get understanding => 'הבנה';

  @override
  String get understandingSubtitle => 'מילים שהובנו מהשיחות שלך.';

  @override
  String get providing => 'מתן';

  @override
  String get providingSubtitle => 'פריטים לביצוע, ותגובות שנלכדו באופן אוטומטי.';

  @override
  String get remembering => 'זיכור';

  @override
  String get rememberingSubtitle => 'עובדות ופרטים שנזכרו עבורך.';

  @override
  String get unlimitedPlan => 'תוכנית בלתי מוגבלת';

  @override
  String get managePlan => 'נהל תוכנית';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'התוכנית שלך תבוטל ב-$date.';
  }

  @override
  String renewsOn(String date) {
    return 'התוכנית שלך מתחדשת ב-$date.';
  }

  @override
  String get basicPlan => 'תוכנית חינם';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used מתוך $limit דקות בשימוש';
  }

  @override
  String get upgrade => 'שדרוג';

  @override
  String get upgradeToUnlimited => 'שדרג לבלתי מוגבל';

  @override
  String basicPlanDesc(int limit) {
    return 'התוכנית שלך כוללת $limit דקות חינם בחודש. שדרג כדי להגיע ללא מגבלה.';
  }

  @override
  String get shareStatsMessage => 'שיתוף הסטטיסטיקה שלי של Omi! (omi.me - העוזר AI שלך שתמיד פועל)';

  @override
  String get sharePeriodToday => 'היום, omi עשה:';

  @override
  String get sharePeriodMonth => 'חודש זה, omi עשה:';

  @override
  String get sharePeriodYear => 'השנה, omi עשה:';

  @override
  String get sharePeriodAllTime => 'עד כה, omi עשה:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 האזין למשך $minutes דקות';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 הבין $words מילים';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ סיפק $count תובנות';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 זכור $count זיכרונות';
  }

  @override
  String get debugLogs => 'יומני ניפוי באגים';

  @override
  String get debugLogsAutoDelete => 'מוחק באופן אוטומטי לאחר 3 ימים.';

  @override
  String get debugLogsDesc => 'עוזר לאבחן בעיות';

  @override
  String get noLogFilesFound => 'לא נמצאו קבצי יומן.';

  @override
  String get omiDebugLog => 'יומן ניפוי באגים של Omi';

  @override
  String get logShared => 'יומן שותף';

  @override
  String get selectLogFile => 'בחר קובץ יומן';

  @override
  String get shareLogs => 'שתף יומנים';

  @override
  String get debugLogCleared => 'יומן ניפוי באגים נוקה';

  @override
  String get exportStarted => 'ייצוא התחיל. זה אולי ייקח כמה שניות...';

  @override
  String get exportAllData => 'ייצא את כל הנתונים';

  @override
  String get exportDataDesc => 'ייצא שיחות לקובץ JSON';

  @override
  String get exportedConversations => 'שיחות מיוצאות מ-Omi';

  @override
  String get exportShared => 'ייצוא שותף';

  @override
  String get deleteKnowledgeGraphTitle => 'מחיקת גרף ידע?';

  @override
  String get deleteKnowledgeGraphMessage =>
      'פעולה זו תמחק את כל נתוני גרף הידע הנגזרים (צמתים וחיבורים). הזיכרונות המקוריים שלך יישארו בטוחים. הגרף יוחדש לאורך זמן או בעת הבקשה הבאה.';

  @override
  String get knowledgeGraphDeleted => 'גרף ידע נמחק';

  @override
  String deleteGraphFailed(String error) {
    return 'כשל במחיקת גרף: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'מחק גרף ידע';

  @override
  String get deleteKnowledgeGraphDesc => 'נקה את כל הצמתים וההתחברויות';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'שרת MCP';

  @override
  String get mcpServerDesc => 'חבר עוזרי AI לנתונים שלך';

  @override
  String get serverUrl => 'כתובת URL של שרת';

  @override
  String get urlCopied => 'כתובת URL הועתקה';

  @override
  String get apiKeyAuth => 'אימות מפתח API';

  @override
  String get header => 'כותרת';

  @override
  String get authorizationBearer => 'Authorization: Bearer <key>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'מזהה לקוח';

  @override
  String get clientSecret => 'סוד לקוח';

  @override
  String get useMcpApiKey => 'השתמש במפתח ה-API של MCP שלך';

  @override
  String get webhooks => 'Webhooks';

  @override
  String get conversationEvents => 'אירועי שיחה';

  @override
  String get newConversationCreated => 'שיחה חדשה נוצרה';

  @override
  String get realtimeTranscript => 'תמלול בזמן אמת';

  @override
  String get transcriptReceived => 'תמלול התקבל';

  @override
  String get audioBytes => 'בתים אודיו';

  @override
  String get audioDataReceived => 'נתוני אודיו התקבלו';

  @override
  String get intervalSeconds => 'מרווח (שניות)';

  @override
  String get daySummary => 'סיכום יום';

  @override
  String get summaryGenerated => 'סיכום נוצר';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'הוסף ל-claude_desktop_config.json';

  @override
  String get copyConfig => 'העתק קונפיגורציה';

  @override
  String get configCopied => 'קונפיגורציה הועתקה ללוח הגזוזים';

  @override
  String get listeningMins => 'הקשבה (דקות)';

  @override
  String get understandingWords => 'הבנה (מילים)';

  @override
  String get insights => 'תובנות';

  @override
  String get memories => 'זיכרונות';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '$used מתוך $limit דקה משומשת החודש';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '$used מתוך $limit מילים משומשות החודש';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '$used מתוך $limit תובנות שהתקבלו החודש';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return '$used מתוך $limit זיכרונות שנוצרו החודש';
  }

  @override
  String get visibility => 'יכולת הראות';

  @override
  String get visibilitySubtitle => 'שלוט באילו שיחות מופיעות ברשימה שלך';

  @override
  String get showShortConversations => 'הצג שיחות קצרות';

  @override
  String get showShortConversationsDesc => 'הצג שיחות קצרות מהסף';

  @override
  String get showDiscardedConversations => 'הצג שיחות מושלכות';

  @override
  String get showDiscardedConversationsDesc => 'כלול שיחות המסומנות כמושלכות';

  @override
  String get shortConversationThreshold => 'סף שיחה קצרה';

  @override
  String get shortConversationThresholdSubtitle => 'שיחות קצרות מזה יוסתרו אלא אם יתאפשר למעלה';

  @override
  String get durationThreshold => 'סף משך זמן';

  @override
  String get durationThresholdDesc => 'הסתר שיחות קצרות מזה';

  @override
  String minLabel(int count) {
    return '$count דקה';
  }

  @override
  String get customVocabularyTitle => 'אוצר מילים מותאם';

  @override
  String get addWords => 'הוסף מילים';

  @override
  String get addWordsDesc => 'שמות, מונחים, או מילים נדירות';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'התחבר';

  @override
  String get comingSoon => 'בקרוב';

  @override
  String get integrationsFooter => 'חבר את האפליקציות שלך כדי לצפות בנתונים ובמדדים בצ\'ט.';

  @override
  String get completeAuthInBrowser => 'אנא השלם אימות בדפדפן שלך. לאחר שתסיים, חזור לאפליקציה.';

  @override
  String failedToStartAuth(String appName) {
    return 'כשל בהתחלת אימות $appName';
  }

  @override
  String disconnectAppTitle(String appName) {
    return 'התנתק מ-$appName?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'האם אתה בטוח שברצונך להתנתק מ-$appName? אתה יכול להתחבר מחדש בכל עת.';
  }

  @override
  String disconnectedFrom(String appName) {
    return 'התנתק מ-$appName';
  }

  @override
  String get failedToDisconnect => 'כשל בהתנתקות';

  @override
  String connectTo(String appName) {
    return 'התחבר ל-$appName';
  }

  @override
  String authAccessMessage(String appName) {
    return 'תצטרך להרשות ל-Omi לגשת לנתונים $appName שלך. זה יפתח את הדפדפן שלך לאימות.';
  }

  @override
  String get continueAction => 'המשך';

  @override
  String get languageTitle => 'שפה';

  @override
  String get primaryLanguage => 'שפה ראשונית';

  @override
  String get automaticTranslation => 'תרגום אוטומטי';

  @override
  String get detectLanguages => 'זהה 10+ שפות';

  @override
  String get authorizeSavingRecordings => 'אשר שמירת הקלטות';

  @override
  String get thanksForAuthorizing => 'תודה על הסכמתך!';

  @override
  String get needYourPermission => 'אנחנו צריכים את ההרשאה שלך';

  @override
  String get alreadyGavePermission => 'כבר נתת לנו הרשאה לשמור את ההקלטות שלך. הנה תזכורת למה אנחנו צריכים את זה:';

  @override
  String get wouldLikePermission => 'היינו רוצים את ההרשאה שלך לשמור את הקלטות הקול שלך. הנה למה:';

  @override
  String get improveSpeechProfile => 'שפר את פרופיל הדיבור שלך';

  @override
  String get improveSpeechProfileDesc => 'אנחנו משתמשים בהקלטות כדי להכשיר עוד ולשפר את פרופיל הדיבור האישי שלך.';

  @override
  String get trainFamilyProfiles => 'הדרך פרופילים לחברים ולמשפחה';

  @override
  String get trainFamilyProfilesDesc => 'ההקלטות שלך עוזרות לנו להכיר ולהקים פרופילים לחברים ולמשפחה שלך.';

  @override
  String get enhanceTranscriptAccuracy => 'שפר את דיוק התמלול';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'כשהמודל שלנו משתפר, אנחנו יכולים לספק תוצאות תמלול טובות יותר לההקלטות שלך.';

  @override
  String get legalNotice =>
      'הודעה משפטית: חוקיות ההקלטה ואחסון נתוני קול עשויים להשתנות בהתאם למיקום ואופן השימוש בתכונה זו. זו אחריותך לוודא עמידה בחוקים ותקנות מקומיים.';

  @override
  String get alreadyAuthorized => 'כבר מוסמך';

  @override
  String get authorize => 'אשר';

  @override
  String get revokeAuthorization => 'שלול הסכמה';

  @override
  String get authorizationSuccessful => 'הסכמה הצליחה!';

  @override
  String get failedToAuthorize => 'הרשאה נכשלה. בבקשה נסה שנית.';

  @override
  String get authorizationRevoked => 'ההרשאה בוטלה.';

  @override
  String get recordingsDeleted => 'ההקלטות נמחקו.';

  @override
  String get failedToRevoke => 'ביטול ההרשאה נכשל. בבקשה נסה שנית.';

  @override
  String get permissionRevokedTitle => 'הרשאה בוטלה';

  @override
  String get permissionRevokedMessage => 'האם אתה רוצה שנמחוק גם את כל ההקלטות הקיימות שלך?';

  @override
  String get yes => 'כן';

  @override
  String get editName => 'עריכת שם';

  @override
  String get howShouldOmiCallYou => 'איך Omiצריך לקרוא לך?';

  @override
  String get enterYourName => 'הזן את שמך';

  @override
  String get nameCannotBeEmpty => 'השם לא יכול להיות ריק';

  @override
  String get nameUpdatedSuccessfully => 'השם עודכן בהצלחה!';

  @override
  String get calendarSettings => 'הגדרות קלנדר';

  @override
  String get calendarProviders => 'ספקי קלנדר';

  @override
  String get macOsCalendar => 'קלנדר macOS';

  @override
  String get connectMacOsCalendar => 'חבר את קלנדר macOS המקומי שלך';

  @override
  String get googleCalendar => 'Google Calendar';

  @override
  String get syncGoogleAccount => 'סנכרן עם חשבון Google שלך';

  @override
  String get showMeetingsMenuBar => 'הצג פגישות קרובות בסרגל התפריטים';

  @override
  String get showMeetingsMenuBarDesc => 'הצג את הפגישה הבאה שלך והזמן עד שהיא תתחיל בסרגל התפריטים של macOS';

  @override
  String get showEventsNoParticipants => 'הצג אירועים ללא משתתפים';

  @override
  String get showEventsNoParticipantsDesc => 'כשמופעל, Coming Up מציג אירועים ללא משתתפים או קישור וידאו.';

  @override
  String get yourMeetings => 'הפגישות שלך';

  @override
  String get refresh => 'רענן';

  @override
  String get noUpcomingMeetings => 'אין פגישות קרובות';

  @override
  String get checkingNextDays => 'בדיקה של 30 הימים הבאים';

  @override
  String get tomorrow => 'מחר';

  @override
  String get googleCalendarComingSoon => 'Google Calendar integration בקרוב!';

  @override
  String connectedAsUser(String userId) {
    return 'מחובר כמשתמש: $userId';
  }

  @override
  String get defaultWorkspace => 'Workspace ברירת המחדל';

  @override
  String get tasksCreatedInWorkspace => 'משימות ייווצרו בworkspace זה';

  @override
  String get defaultProjectOptional => 'פרויקט ברירת המחדל (אופציונלי)';

  @override
  String get leaveUnselectedTasks => 'השאר בלא נבחר ליצירת משימות ללא פרויקט';

  @override
  String get noProjectsInWorkspace => 'לא נמצאו פרויקטים בworkspace זה';

  @override
  String get conversationTimeoutDesc => 'בחר כמה זמן להמתין בשקט לפני סיום אוטומטי של שיחה:';

  @override
  String get timeout2Minutes => '2 דקות';

  @override
  String get timeout2MinutesDesc => 'סיים שיחה לאחר 2 דקות של שקט';

  @override
  String get timeout5Minutes => '5 דקות';

  @override
  String get timeout5MinutesDesc => 'סיים שיחה לאחר 5 דקות של שקט';

  @override
  String get timeout10Minutes => '10 דקות';

  @override
  String get timeout10MinutesDesc => 'סיים שיחה לאחר 10 דקות של שקט';

  @override
  String get timeout30Minutes => '30 דקות';

  @override
  String get timeout30MinutesDesc => 'סיים שיחה לאחר 30 דקות של שקט';

  @override
  String get timeout4Hours => '4 שעות';

  @override
  String get timeout4HoursDesc => 'סיים שיחה לאחר 4 שעות של שקט';

  @override
  String get conversationEndAfterHours => 'שיחות יסתיימו כעת לאחר 4 שעות של שקט';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'שיחות יסתיימו כעת לאחר $minutes דקות של שקט';
  }

  @override
  String get tellUsPrimaryLanguage => 'ספר לנו מהי שפתך העיקרית';

  @override
  String get languageForTranscription => 'הגדר את שפתך לתמלול חדות יותר וחוויה מעוצבת.';

  @override
  String get singleLanguageModeInfo => 'מצב שפה יחידה מופעל. תרגום מבוטל לדיוק גבוה יותר.';

  @override
  String get searchLanguageHint => 'חפש שפה לפי שם או קוד';

  @override
  String get noLanguagesFound => 'לא נמצאו שפות';

  @override
  String get skip => 'דלג';

  @override
  String languageSetTo(String language) {
    return 'שפה הוגדרה ל-$language';
  }

  @override
  String get failedToSetLanguage => 'הגדרת השפה נכשלה';

  @override
  String appSettings(String appName) {
    return 'הגדרות $appName';
  }

  @override
  String disconnectFromApp(String appName) {
    return 'התנתק מ-$appName?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'זה יסיר את אימות $appName שלך. תצטרך להתחבר מחדש כדי להשתמש בו שוב.';
  }

  @override
  String connectedToApp(String appName) {
    return 'מחובר ל-$appName';
  }

  @override
  String get account => 'חשבון';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'פריטי הפעולה שלך יסתנכרנו לחשבון $appName שלך';
  }

  @override
  String get defaultSpace => 'Space ברירת מחדל';

  @override
  String get selectSpaceInWorkspace => 'בחר space בworkspace שלך';

  @override
  String get noSpacesInWorkspace => 'לא נמצאו spaces בworkspace זה';

  @override
  String get defaultList => 'רשימה ברירת מחדל';

  @override
  String get tasksAddedToList => 'משימות יוסיפו לרשימה זו';

  @override
  String get noListsInSpace => 'לא נמצאו רשימות בspace זה';

  @override
  String failedToLoadRepos(String error) {
    return 'טעינת מאגרים נכשלה: $error';
  }

  @override
  String get defaultRepoSaved => 'מאגר ברירת המחדל נשמר';

  @override
  String get failedToSaveDefaultRepo => 'שמירת מאגר ברירת המחדל נכשלה';

  @override
  String get defaultRepository => 'מאגר ברירת המחדל';

  @override
  String get selectDefaultRepoDesc =>
      'בחר מאגר ברירת מחדל ליצירת בעיות. אתה עדיין יכול לציין מאגר שונה בעת יצירת בעיות.';

  @override
  String get noReposFound => 'לא נמצאו מאגרים';

  @override
  String get private => 'פרטי';

  @override
  String updatedDate(String date) {
    return 'עודכן $date';
  }

  @override
  String get yesterday => 'אתמול';

  @override
  String daysAgo(int count) {
    return 'לפני $count ימים';
  }

  @override
  String get oneWeekAgo => 'לפני שבוע';

  @override
  String weeksAgo(int count) {
    return 'לפני $count שבועות';
  }

  @override
  String get oneMonthAgo => 'לפני חודש';

  @override
  String monthsAgo(int count) {
    return 'לפני $count חודשים';
  }

  @override
  String get issuesCreatedInRepo => 'בעיות ייווצרו במאגר ברירת המחדל שלך';

  @override
  String get taskIntegrations => 'שילובי משימות';

  @override
  String get configureSettings => 'הגדר הגדרות';

  @override
  String get completeAuthBrowser => 'בבקשה השלם אימות בדפדפן שלך. לאחר סיום, חזור לאפליקציה.';

  @override
  String failedToStartAppAuth(String appName) {
    return 'הפעלת אימות $appName נכשלה';
  }

  @override
  String connectToAppTitle(String appName) {
    return 'התחבר ל-$appName';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'יהיה עליך להרשות ל-Omi ליצור משימות בחשבון $appName שלך. זה יפתח את הדפדפן שלך לאימות.';
  }

  @override
  String get continueButton => 'המשך';

  @override
  String appIntegration(String appName) {
    return 'שילוב $appName';
  }

  @override
  String integrationComingSoon(String appName) {
    return 'שילוב עם $appName בקרוב! אנחנו עובדים קשה כדי להביא לך עוד אפשרויות ניהול משימות.';
  }

  @override
  String get gotIt => 'הבנתי';

  @override
  String get tasksExportedOneApp => 'ניתן לייצא משימות ליישום אחד בכל פעם.';

  @override
  String get completeYourUpgrade => 'השלם את שדרוגך';

  @override
  String get importConfiguration => 'ייבא תצורה';

  @override
  String get exportConfiguration => 'ייצא תצורה';

  @override
  String get bringYourOwn => 'הביא שלך';

  @override
  String get payYourSttProvider => 'השתמש בomi בחופשיות. אתה משלם ישירות לספק STT שלך.';

  @override
  String get freeMinutesMonth => '1,200 דקות חינם לחודש כלולות. בלתי מוגבל עם ';

  @override
  String get omiUnlimited => 'Omi Unlimited';

  @override
  String get hostRequired => 'דרוש Host';

  @override
  String get validPortRequired => 'דרוש Port תקף';

  @override
  String get validWebsocketUrlRequired => 'דרוש WebSocket URL תקף (wss://)';

  @override
  String get apiUrlRequired => 'דרוש API URL';

  @override
  String get apiKeyRequired => 'דרוש API key';

  @override
  String get invalidJsonConfig => 'תצורת JSON לא תקפה';

  @override
  String errorSaving(String error) {
    return 'שגיאה בשמירה: $error';
  }

  @override
  String get configCopiedToClipboard => 'תצורה הועתקה ללוח הרשימות';

  @override
  String get pasteJsonConfig => 'הדבק את תצורת JSON שלך למטה:';

  @override
  String get addApiKeyAfterImport => 'תצטרך להוסיף את API key שלך לאחר ייבוא';

  @override
  String get paste => 'הדבק';

  @override
  String get import => 'ייבא';

  @override
  String get invalidProviderInConfig => 'ספק לא תקף בתצורה';

  @override
  String importedConfig(String providerName) {
    return 'ייבאה תצורת $providerName';
  }

  @override
  String invalidJson(String error) {
    return 'JSON לא תקף: $error';
  }

  @override
  String get provider => 'ספק';

  @override
  String get live => 'Live';

  @override
  String get onDevice => 'על המכשיר';

  @override
  String get apiUrl => 'API URL';

  @override
  String get enterSttHttpEndpoint => 'הזן את נקודת קצה STT HTTP שלך';

  @override
  String get websocketUrl => 'WebSocket URL';

  @override
  String get enterLiveSttWebsocket => 'הזן את נקודת קצה WebSocket STT live שלך';

  @override
  String get apiKey => 'API key';

  @override
  String get enterApiKey => 'הזן את API key שלך';

  @override
  String get storedLocallyNeverShared => 'מאוחסן מקומית, לעולם לא משותף';

  @override
  String get host => 'Host';

  @override
  String get port => 'Port';

  @override
  String get advanced => 'מתקדם';

  @override
  String get configuration => 'תצורה';

  @override
  String get requestConfiguration => 'תצורת בקשה';

  @override
  String get responseSchema => 'סכימת תגובה';

  @override
  String get modified => 'שונה';

  @override
  String get resetRequestConfig => 'אפס תצורת בקשה לברירת המחדל';

  @override
  String get logs => 'יומנים';

  @override
  String get logsCopied => 'יומנים הועתקו';

  @override
  String get noLogsYet => 'אין יומנים עדיין. התחל הקלטה כדי לראות פעילות STT מותאמת.';

  @override
  String deviceUsesCodec(String device, String reason) {
    return '$device משתמש ב-$reason. Omi יהיה בשימוש.';
  }

  @override
  String get omiTranscription => 'תמלול Omi';

  @override
  String get bestInClassTranscription => 'תמלול מהטובים ביותר ללא הגדרה';

  @override
  String get instantSpeakerLabels => 'תוויות דובר מיידיות';

  @override
  String get languageTranslation => 'תרגום 100+ שפות';

  @override
  String get optimizedForConversation => 'מותאם לשיחה';

  @override
  String get autoLanguageDetection => 'זיהוי שפה אוטומטי';

  @override
  String get highAccuracy => 'דיוק גבוה';

  @override
  String get privacyFirst => 'פרטיות קודם כל';

  @override
  String get saveChanges => 'שמור שינויים';

  @override
  String get resetToDefault => 'אפס לברירת המחדל';

  @override
  String get viewTemplate => 'הצג תבנית';

  @override
  String get trySomethingLike => 'נסה משהו כמו...';

  @override
  String get tryIt => 'נסה זאת';

  @override
  String get creatingPlan => 'יצירת תכנית';

  @override
  String get developingLogic => 'פיתוח לוגיקה';

  @override
  String get designingApp => 'עיצוב אפליקציה';

  @override
  String get generatingIconStep => 'יצירת אייקון';

  @override
  String get finalTouches => 'המגעות הסופיות';

  @override
  String get processing => 'מעבד...';

  @override
  String get features => 'תכונות';

  @override
  String get creatingYourApp => 'יצירת האפליקציה שלך...';

  @override
  String get generatingIcon => 'יצירת אייקון...';

  @override
  String get whatShouldWeMake => 'מה אנחנו אמורים ליצור?';

  @override
  String get appName => 'שם האפליקציה';

  @override
  String get description => 'תיאור';

  @override
  String get publicLabel => 'ציבורי';

  @override
  String get privateLabel => 'פרטי';

  @override
  String get free => 'חינם';

  @override
  String get perMonth => '/ חודש';

  @override
  String get tailoredConversationSummaries => 'סיכומי שיחה מותאמים';

  @override
  String get customChatbotPersonality => 'אישיות Chatbot מותאמת';

  @override
  String get makePublic => 'הפוך לציבורי';

  @override
  String get anyoneCanDiscover => 'כל אחד יכול לגלות את האפליקציה שלך';

  @override
  String get onlyYouCanUse => 'רק אתה יכול להשתמש באפליקציה זו';

  @override
  String get paidApp => 'אפליקציה בתשלום';

  @override
  String get usersPayToUse => 'משתמשים משלמים כדי להשתמש באפליקציה שלך';

  @override
  String get freeForEveryone => 'חינם לכולם';

  @override
  String get perMonthLabel => '/ חודש';

  @override
  String get creating => 'יוצר...';

  @override
  String get createApp => 'צור אפליקציה';

  @override
  String get searchingForDevices => 'חיפוש מכשירים...';

  @override
  String devicesFoundNearby(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'DEVICES',
      one: 'DEVICE',
    );
    return '$count $_temp0 נמצאו בקרבה';
  }

  @override
  String get pairingSuccessful => 'זיווג הצליח';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'שגיאה בחיבור ל-Apple Watch: $error';
  }

  @override
  String get dontShowAgain => 'אל תציג שוב';

  @override
  String get iUnderstand => 'אני מבין';

  @override
  String get enableBluetooth => 'הפעל Bluetooth';

  @override
  String get bluetoothNeeded => 'Omi זקוק ל-Bluetooth כדי להתחבר לציוד הלביש שלך. בבקשה הפעל Bluetooth ונסה שנית.';

  @override
  String get contactSupport => 'יצור קשר עם תמיכה?';

  @override
  String get connectLater => 'התחבר מאוחר יותר';

  @override
  String get grantPermissions => 'הנח הרשאות';

  @override
  String get backgroundActivity => 'פעילות רקע';

  @override
  String get backgroundActivityDesc => 'תן ל-Omi להפעיל ברקע לטובת יציבות טובה יותר';

  @override
  String get locationAccess => 'גישה למיקום';

  @override
  String get locationAccessDesc => 'הפעל מיקום רקע עבור החוויה המלאה';

  @override
  String get notifications => 'הודעות';

  @override
  String get notificationsDesc => 'הפעל הודעות כדי להישאר מעודכן';

  @override
  String get locationServiceDisabled => 'שירות מיקום מושבת';

  @override
  String get locationServiceDisabledDesc =>
      'שירות מיקום מושבת. בבקשה עבור להגדרות > פרטיות וביטחון > שירותי מיקום והפעל אותו';

  @override
  String get backgroundLocationDenied => 'גישת מיקום רקע נדחתה';

  @override
  String get backgroundLocationDeniedDesc => 'בבקשה עבור להגדרות המכשיר וגדר הרשאת מיקום ל-\"תמיד אפשר\"';

  @override
  String get lovingOmi => 'אוהב את Omi?';

  @override
  String get leaveReviewIos => 'עזור לנו להגיע ליותר אנשים על ידי השארת ביקורת ב-App Store. המשוב שלך אומר לנו הרבה!';

  @override
  String get leaveReviewAndroid =>
      'עזור לנו להגיע ליותר אנשים על ידי השארת ביקורת ב-Google Play Store. המשוב שלך אומר לנו הרבה!';

  @override
  String get rateOnAppStore => 'דרג ב-App Store';

  @override
  String get rateOnGooglePlay => 'דרג ב-Google Play';

  @override
  String get maybeLater => 'אולי מאוחר יותר';

  @override
  String get speechProfileIntro => 'Omi צריך ללמוד את המטרות שלך ואת הקול שלך. תוכל לשנות את זה מאוחר יותר.';

  @override
  String get getStarted => 'התחל';

  @override
  String get allDone => 'הכל בסדר!';

  @override
  String get keepGoing => 'המשך, אתה עושה טוב מאוד';

  @override
  String get skipThisQuestion => 'דלג על שאלה זו';

  @override
  String get skipForNow => 'דלג לעת עתה';

  @override
  String get connectionError => 'שגיאת חיבור';

  @override
  String get connectionErrorDesc => 'החיבור לשרת נכשל. בבקשה בדוק את חיבור האינטרנט שלך ונסה שנית.';

  @override
  String get invalidRecordingMultipleSpeakers => 'הקלטה לא תקפה בוגדה';

  @override
  String get multipleSpeakersDesc => 'נראה שיש כמה דוברים בהקלטה. בבקשה ודא שאתה במקום שקט וחזור על הניסיון.';

  @override
  String get tooShortDesc => 'אין מספיק דיבור בוגדה. בבקשה תדבר יותר וחזור על הניסיון.';

  @override
  String get invalidRecordingDesc => 'בבקשה ודא שאתה מדבר לפחות 5 שניות ולא יותר מ-90.';

  @override
  String get areYouThere => 'אתה שם?';

  @override
  String get noSpeechDesc => 'לא יכלנו לזהות דיבור. בבקשה ודא שאתה מדבר לפחות 10 שניות ולא יותר מ-3 דקות.';

  @override
  String get connectionLost => 'חיבור אבד';

  @override
  String get connectionLostDesc => 'החיבור קטע. בבקשה בדוק את חיבור האינטרנט שלך ונסה שנית.';

  @override
  String get tryAgain => 'נסה שנית';

  @override
  String get connectOmiOmiGlass => 'התחבר ל-Omi / OmiGlass';

  @override
  String get continueWithoutDevice => 'המשך ללא מכשיר';

  @override
  String get permissionsRequired => 'הרשאות נדרשות';

  @override
  String get permissionsRequiredDesc =>
      'אפליקציה זו זקוקה להרשאות Bluetooth ומיקום כדי לתפקד כראוי. בבקשה הפעל אותן בהגדרות.';

  @override
  String get openSettings => 'פתח הגדרות';

  @override
  String get wantDifferentName => 'רוצה להכנס בשם אחר?';

  @override
  String get whatsYourName => 'מה שמך?';

  @override
  String get speakTranscribeSummarize => 'דבור. תמלל. סכם.';

  @override
  String get signInWithApple => 'התחבר עם Apple';

  @override
  String get signInWithGoogle => 'התחבר עם Google';

  @override
  String get byContinuingAgree => 'בהמשך, אתה מסכים ל-';

  @override
  String get termsOfUse => 'תנאי השימוש';

  @override
  String get omiYourAiCompanion => 'Omi – בן הלוויה בינה מלאכותית שלך';

  @override
  String get captureEveryMoment => 'תופס כל רגע. קבל סיכומים מונעי בינה מלאכותית. לעולם אל תרשום הערות שוב.';

  @override
  String get appleWatchSetup => 'הגדרת Apple Watch';

  @override
  String get permissionRequestedExclaim => 'בקשת הרשאה!';

  @override
  String get microphonePermission => 'הרשאת מיקרופון';

  @override
  String get permissionGrantedNow => 'הרשאה ניתנה! עכשיו:\n\nפתח את אפליקציית Omi בשעון שלך וטפוק \"המשך\" למטה';

  @override
  String get needMicrophonePermission =>
      'אנחנו זקוקים להרשאת מיקרופון.\n\n1. טפוק \"הנח הרשאה\"\n2. אפשר באייפון שלך\n3. אפליקציית השעון תיסגר\n4. פתח מחדש וטפוק \"המשך\"';

  @override
  String get grantPermissionButton => 'הנח הרשאה';

  @override
  String get needHelp => 'זקוק לעזרה?';

  @override
  String get troubleshootingSteps =>
      'פתרון בעיות:\n\n1. ודא שOmi מותקן בשעון שלך\n2. פתח את אפליקציית Omi בשעון שלך\n3. חפש את חלון ההרשאה\n4. טפוק \"אפשר\" כשתתבקש\n5. אפליקציה בשעון שלך תיסגר - פתח מחדש\n6. חזור וטפוק \"המשך\" באייפון שלך';

  @override
  String get recordingStartedSuccessfully => 'הקלטה התחילה בהצלחה!';

  @override
  String get permissionNotGrantedYet =>
      'הרשאה עדיין לא ניתנה. בבקשה ודא שאפשרת גישת מיקרופון ופתחת את האפליקציה בשעון שלך מחדש.';

  @override
  String errorRequestingPermission(String error) {
    return 'שגיאה בבקשת הרשאה: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'שגיאה בהתחלת הקלטה: $error';
  }

  @override
  String get selectPrimaryLanguage => 'בחר את שפתך העיקרית';

  @override
  String get languageBenefits => 'הגדר את שפתך לתמלול חדות יותר וחוויה מעוצבת';

  @override
  String get whatsYourPrimaryLanguage => 'מה שפתך העיקרית?';

  @override
  String get selectYourLanguage => 'בחר את שפתך';

  @override
  String get personalGrowthJourney => 'מסע הצמיחה האישי שלך עם בינה מלאכותית שמקשיבה לכל מילה שלך.';

  @override
  String get actionItemsTitle => 'עסקים לעשות';

  @override
  String get actionItemsDescription => 'טפוק לעריכה • לחיצה ארוכה לבחירה • החלק לפעולות';

  @override
  String get tabToDo => 'עסקים לעשות';

  @override
  String get tabDone => 'בוצע';

  @override
  String get tabOld => 'ישן';

  @override
  String get emptyTodoMessage => '🎉 הכל תופס!\nאין פריטי פעולה ממתינים';

  @override
  String get emptyDoneMessage => 'אין פריטים שהושלמו עדיין';

  @override
  String get emptyOldMessage => '✅ אין משימות ישנות';

  @override
  String get noItems => 'אין פריטים';

  @override
  String get actionItemMarkedIncomplete => 'פריט פעולה סומן כלא שלם';

  @override
  String get actionItemCompleted => 'פריט פעולה הושלם';

  @override
  String get deleteActionItemTitle => 'מחק פריט פעולה';

  @override
  String get deleteActionItemMessage => 'האם אתה בטוח שברצונך למחוק פריט פעולה זה?';

  @override
  String get deleteSelectedItemsTitle => 'מחק פריטים שנבחרו';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Are you sure you want to delete $count selected action item$s?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'פריט פעולה \"$description\" מחוק';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count action item$s deleted';
  }

  @override
  String get failedToDeleteItem => 'מחיקת פריט פעולה נכשלה';

  @override
  String get failedToDeleteItems => 'מחיקת פריטים נכשלה';

  @override
  String get failedToDeleteSomeItems => 'מחיקת חלק מהפריטים נכשלה';

  @override
  String get welcomeActionItemsTitle => 'מוכן לפריטי פעולה';

  @override
  String get welcomeActionItemsDescription =>
      'הבינה המלאכותית שלך תחלץ באופן אוטומטי משימות ועסקים לעשות מהשיחות שלך. הם יופיעו כאן כשייווצרו.';

  @override
  String get autoExtractionFeature => 'מחולץ באופן אוטומטי משיחות';

  @override
  String get editSwipeFeature => 'טפוק לעריכה, החלק להשלמה או מחיקה';

  @override
  String itemsSelected(int count) {
    return '$count נבחרים';
  }

  @override
  String get selectAll => 'בחר הכל';

  @override
  String get deleteSelected => 'מחק נבחרים';

  @override
  String get searchMemories => 'חפש זכרונות...';

  @override
  String get memoryDeleted => 'זכרון מחוק.';

  @override
  String get undo => 'בטל';

  @override
  String get noMemoriesYet => '🧠 אין זכרונות עדיין';

  @override
  String get noAutoMemories => 'אין זכרונות שחולצו באופן אוטומטי עדיין';

  @override
  String get noManualMemories => 'אין זכרונות ידניים עדיין';

  @override
  String get noMemoriesInCategories => 'אין זכרונות בקטגוריות אלו';

  @override
  String get noMemoriesFound => '🔍 לא נמצאו זכרונות';

  @override
  String get addFirstMemory => 'הוסף את הזכרון הראשון שלך';

  @override
  String get clearMemoryTitle => 'נקה את הזיכרון של Omi';

  @override
  String get clearMemoryMessage => 'האם אתה בטוח שברצונך לנקות את הזיכרון של Omi? לא ניתן לבטל פעולה זו.';

  @override
  String get clearMemoryButton => 'נקה זיכרון';

  @override
  String get memoryClearedSuccess => 'הזיכרון של Omi עליך נוקה';

  @override
  String get noMemoriesToDelete => 'אין זכרונות למחיקה';

  @override
  String get createMemoryTooltip => 'צור זכרון חדש';

  @override
  String get createActionItemTooltip => 'צור פריט פעולה חדש';

  @override
  String get memoryManagement => 'ניהול זכרונות';

  @override
  String get filterMemories => 'סנן זכרונות';

  @override
  String totalMemoriesCount(int count) {
    return 'יש לך $count זכרונות בסך הכל';
  }

  @override
  String get publicMemories => 'זכרונות ציבוריים';

  @override
  String get privateMemories => 'זכרונות פרטיים';

  @override
  String get makeAllPrivate => 'הפוך את כל הזכרונות לפרטיים';

  @override
  String get makeAllPublic => 'הפוך את כל הזכרונות לציבוריים';

  @override
  String get deleteAllMemories => 'מחק את כל הזכרונות';

  @override
  String get allMemoriesPrivateResult => 'כל הזכרונות הם כעת פרטיים';

  @override
  String get allMemoriesPublicResult => 'כל הזכרונות הם כעת ציבוריים';

  @override
  String get newMemory => '✨ זכרון חדש';

  @override
  String get editMemory => '✏️ עריכת זכרון';

  @override
  String get memoryContentHint => 'אני אוהב לאכול גלידה...';

  @override
  String get failedToSaveMemory => 'שמירה נכשלה. בבקשה בדוק את החיבור שלך.';

  @override
  String get saveMemory => 'שמור זכרון';

  @override
  String get retry => 'נסה שנית';

  @override
  String get createActionItem => 'צור פריט פעולה';

  @override
  String get editActionItem => 'עריכת פריט פעולה';

  @override
  String get actionItemDescriptionHint => 'מה צריך להיות בוצע?';

  @override
  String get actionItemDescriptionEmpty => 'תיאור פריט הפעולה לא יכול להיות ריק.';

  @override
  String get actionItemUpdated => 'פריט פעולה עודכן';

  @override
  String get failedToUpdateActionItem => 'עדכון פריט פעולה נכשל';

  @override
  String get actionItemCreated => 'פריט פעולה נוצר';

  @override
  String get failedToCreateActionItem => 'יצירת פריט פעולה נכשלה';

  @override
  String get dueDate => 'תאריך יעד';

  @override
  String get time => 'זמן';

  @override
  String get addDueDate => 'הוסף תאריך יעד';

  @override
  String get pressDoneToSave => 'הקש בוצע כדי לשמור';

  @override
  String get pressDoneToCreate => 'הקש בוצע כדי ליצור';

  @override
  String get filterAll => 'הכל';

  @override
  String get filterSystem => 'עליך';

  @override
  String get filterInteresting => 'תובנות';

  @override
  String get filterManual => 'ידני';

  @override
  String get completed => 'הושלם';

  @override
  String get markComplete => 'סמן כשלם';

  @override
  String get actionItemDeleted => 'פריט פעולה מחוק';

  @override
  String get failedToDeleteActionItem => 'מחיקת פריט פעולה נכשלה';

  @override
  String get deleteActionItemConfirmTitle => 'מחק פריט פעולה';

  @override
  String get deleteActionItemConfirmMessage => 'האם אתה בטוח שברצונך למחוק פריט פעולה זה?';

  @override
  String get appLanguage => 'שפת אפליקציה';

  @override
  String get appInterfaceSectionTitle => 'ממשק אפליקציה';

  @override
  String get speechTranscriptionSectionTitle => 'דיבור וריבוי מדיה';

  @override
  String get languageSettingsHelperText =>
      'שינוי שפת אפליקציה משנה תפריטים וכפתורים. שפת דיבור משפיעה על אופן התמלול של ההקלטות שלך.';

  @override
  String get translationNotice => 'הודעת תרגום';

  @override
  String get translationNoticeMessage => 'Omi תורגם שיחות לשפתך העיקרית. עדכן זאת בכל עת בהגדרות → פרופילים.';

  @override
  String get pleaseCheckInternetConnection => 'בבקשה בדוק את חיבור האינטרנט שלך ונסה שנית';

  @override
  String get pleaseSelectReason => 'בבקשה בחר סיבה';

  @override
  String get tellUsMoreWhatWentWrong => 'ספר לנו עוד מה השתבש...';

  @override
  String get selectText => 'בחר טקסט';

  @override
  String maximumGoalsAllowed(int count) {
    return 'מקסימום $count יעדים מותרים';
  }

  @override
  String get conversationCannotBeMerged => 'לא ניתן למזג שיחה זו (נעולה או כבר מתמזגת)';

  @override
  String get pleaseEnterFolderName => 'בבקשה הזן שם תיקייה';

  @override
  String get failedToCreateFolder => 'יצירת תיקייה נכשלה';

  @override
  String get failedToUpdateFolder => 'עדכון תיקייה נכשל';

  @override
  String get folderName => 'שם התיקייה';

  @override
  String get descriptionOptional => 'תיאור (אופציונלי)';

  @override
  String get failedToDeleteFolder => 'השמדת התיקייה נכשלה';

  @override
  String get editFolder => 'ערוך תיקייה';

  @override
  String get deleteFolder => 'מחק תיקייה';

  @override
  String get transcriptCopiedToClipboard => 'התמלול הועתק ללוח';

  @override
  String get summaryCopiedToClipboard => 'הסיכום הועתק ללוח';

  @override
  String get conversationUrlCouldNotBeShared => 'לא ניתן היה לשתף את כתובת ה-URL של השיחה.';

  @override
  String get urlCopiedToClipboard => 'כתובת ה-URL הועתקה ללוח';

  @override
  String get exportTranscript => 'ייצא תמלול';

  @override
  String get exportSummary => 'ייצא סיכום';

  @override
  String get exportButton => 'ייצא';

  @override
  String get actionItemsCopiedToClipboard => 'פריטי פעולה הועתקו ללוח';

  @override
  String get summarize => 'סכם';

  @override
  String get generateSummary => 'צור סיכום';

  @override
  String get conversationNotFoundOrDeleted => 'השיחה לא נמצאה או נמחקה';

  @override
  String get deleteMemory => 'מחק זיכרון';

  @override
  String get thisActionCannotBeUndone => 'לא ניתן לבטל פעולה זו.';

  @override
  String memoriesCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count memories',
      one: '1 memory',
      zero: '0 memories',
    );
    return '$_temp0';
  }

  @override
  String get noMemoriesInCategory => 'אין זיכרונות בקטגוריה זו עדיין';

  @override
  String get addYourFirstMemory => 'הוסף את הזיכרון הראשון שלך';

  @override
  String get firmwareDisconnectUsb => 'נתק USB';

  @override
  String get firmwareUsbWarning => 'חיבור USB בזמן עדכונים עשוי להזיק למכשירך.';

  @override
  String get firmwareBatteryAbove15 => 'סוללה מעל 15%';

  @override
  String get firmwareEnsureBattery => 'וודא שהמכשיר שלך בעל 15% סוללה.';

  @override
  String get firmwareStableConnection => 'חיבור יציב';

  @override
  String get firmwareConnectWifi => 'התחבר ל-Wi-Fi או סלולר.';

  @override
  String failedToStartUpdate(String error) {
    return 'הפעלת העדכון נכשלה: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'לפני העדכון, וודא:';

  @override
  String get confirmed => 'אושר!';

  @override
  String get release => 'שחרר';

  @override
  String get slideToUpdate => 'גלול כדי לעדכן';

  @override
  String copiedToClipboard(String title) {
    return '$title הועתק ללוח';
  }

  @override
  String get batteryLevel => 'רמת הסוללה';

  @override
  String get charging => 'טוען';

  @override
  String get productUpdate => 'עדכון מוצר';

  @override
  String get offline => 'לא מחובר';

  @override
  String get available => 'זמין';

  @override
  String get unpairDeviceDialogTitle => 'נתק מכשיר';

  @override
  String get unpairDeviceDialogMessage =>
      'זה ינתק את המכשיר כדי שיוכל להתחבר לטלפון אחר. יהיה עליך ללכת להגדרות > Bluetooth ולשכוח את המכשיר כדי להשלים את התהליך.';

  @override
  String get unpair => 'נתק';

  @override
  String get unpairAndForgetDevice => 'נתק ושכח מכשיר';

  @override
  String get unknownDevice => 'לא ידוע';

  @override
  String get unknown => 'לא ידוע';

  @override
  String get productName => 'שם המוצר';

  @override
  String get serialNumber => 'מספר סידורי';

  @override
  String get connected => 'מחובר';

  @override
  String get privacyPolicyTitle => 'מדיניות הפרטיות';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label הועתק';
  }

  @override
  String get noApiKeysYet => 'אין מפתחות API עדיין';

  @override
  String get createKeyToGetStarted => 'צור מפתח כדי להתחיל';

  @override
  String get configureSttProvider => 'הגדר ספק STT';

  @override
  String get setWhenConversationsAutoEnd => 'הגדר מתי שיחות מסתיימות באופן אוטומטי';

  @override
  String get importDataFromOtherSources => 'ייבא נתונים ממקורות אחרים';

  @override
  String get debugAndDiagnostics => 'ניפוי באגים ואבחון';

  @override
  String get autoDeletesAfter3Days => 'מוחק אוטומטי לאחר 3 ימים.';

  @override
  String get helpsDiagnoseIssues => 'עוזר לאבחן בעיות';

  @override
  String get exportStartedMessage => 'הייצוא התחיל. זה עשוי לקחת כמה שניות...';

  @override
  String get exportConversationsToJson => 'ייצא שיחות לקובץ JSON';

  @override
  String get knowledgeGraphDeletedSuccess => 'גרף הידע נמחק בהצלחה';

  @override
  String failedToDeleteGraph(String error) {
    return 'מחיקת הגרף נכשלה: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'נקה את כל הצמתים והחיבורים';

  @override
  String get addToClaudeDesktopConfig => 'הוסף ל-claude_desktop_config.json';

  @override
  String get connectAiAssistantsToData => 'חבר עוזרים AI לנתונים שלך';

  @override
  String get useYourMcpApiKey => 'השתמש במפתח ה-API של MCP שלך';

  @override
  String get realTimeTranscript => 'תמלול בזמן אמת';

  @override
  String get experimental => 'ניסיוני';

  @override
  String get transcriptionDiagnostics => 'אבחון תמלול';

  @override
  String get detailedDiagnosticMessages => 'הודעות אבחון מפורטות';

  @override
  String get autoCreateSpeakers => 'אנשי דיבור שנוצרו אוטומטית';

  @override
  String get autoCreateWhenNameDetected => 'צור אוטומטית כאשר שם מזוהה';

  @override
  String get followUpQuestions => 'שאלות המשך';

  @override
  String get suggestQuestionsAfterConversations => 'הצע שאלות לאחר שיחות';

  @override
  String get goalTracker => 'עוקב יעדים';

  @override
  String get trackPersonalGoalsOnHomepage => 'עקוב אחר היעדים האישיים שלך בעמוד הבית';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'תיאור פריט פעולה לא יכול להיות ריק';

  @override
  String get saved => 'נשמר';

  @override
  String get overdue => 'פג תוקף';

  @override
  String get failedToUpdateDueDate => 'עדכון תאריך התאריך נכשל';

  @override
  String get markIncomplete => 'סמן כלא שלם';

  @override
  String get editDueDate => 'ערוך תאריך הקבלה';

  @override
  String get setDueDate => 'הגדר תאריך הקבלה';

  @override
  String get clearDueDate => 'נקה תאריך הקבלה';

  @override
  String get failedToClearDueDate => 'ניקוי תאריך הקבלה נכשל';

  @override
  String get mondayAbbr => 'ב׳';

  @override
  String get tuesdayAbbr => 'ג׳';

  @override
  String get wednesdayAbbr => 'ד׳';

  @override
  String get thursdayAbbr => 'ה׳';

  @override
  String get fridayAbbr => 'ו׳';

  @override
  String get saturdayAbbr => 'ש׳';

  @override
  String get sundayAbbr => 'א׳';

  @override
  String get howDoesItWork => 'איך זה עובד?';

  @override
  String get sdCardSyncDescription => 'סנכרון כרטיס SD יייצא את הזיכרונות שלך מכרטיס ה-SD לאפליקציה';

  @override
  String get checksForAudioFiles => 'בדוק קבצי שמע בכרטיס ה-SD';

  @override
  String get omiSyncsAudioFiles => 'לאחר מכן Omi מסנכרן את קבצי השמע עם השרת';

  @override
  String get serverProcessesAudio => 'השרת עובד על קבצי שמע ויוצר זיכרונות';

  @override
  String get youreAllSet => 'הכל מוכן!';

  @override
  String get welcomeToOmiDescription => 'ברוכים הבאים ל-Omi! עוזר ה-AI שלך מוכן לסייע לך בשיחות, משימות ועוד.';

  @override
  String get startUsingOmi => 'התחל להשתמש ב-Omi';

  @override
  String get back => 'חזור';

  @override
  String get keyboardShortcuts => 'קיצורי מקלדת';

  @override
  String get toggleControlBar => 'הפעל/כבה סרגל בקרה';

  @override
  String get pressKeys => 'לחץ על מקשים...';

  @override
  String get cmdRequired => '⌘ נדרש';

  @override
  String get invalidKey => 'מקש לא חוקי';

  @override
  String get space => 'רווח';

  @override
  String get search => 'חיפוש';

  @override
  String get searchPlaceholder => 'חיפוש...';

  @override
  String get untitledConversation => 'שיחה ללא כותרת';

  @override
  String countRemaining(String count) {
    return '$count נותר';
  }

  @override
  String get addGoal => 'הוסף יעד';

  @override
  String get editGoal => 'ערוך יעד';

  @override
  String get icon => 'סמל';

  @override
  String get goalTitle => 'כותרת היעד';

  @override
  String get current => 'נוכחי';

  @override
  String get target => 'מטרה';

  @override
  String get saveGoal => 'שמור';

  @override
  String get goals => 'יעדים';

  @override
  String get tapToAddGoal => 'הקש להוסיף יעד';

  @override
  String welcomeBack(String name) {
    return 'ברוכים הבאים, $name';
  }

  @override
  String get yourConversations => 'השיחות שלך';

  @override
  String get reviewAndManageConversations => 'בדוק וניהול השיחות שנתפסו';

  @override
  String get startCapturingConversations => 'התחל ללכוד שיחות עם מכשיר Omi שלך כדי לראות אותן כאן.';

  @override
  String get useMobileAppToCapture => 'השתמש באפליקציה הנייד שלך ללכידת שמע';

  @override
  String get conversationsProcessedAutomatically => 'שיחות מעובדות באופן אוטומטי';

  @override
  String get getInsightsInstantly => 'קבל תובנות וסיכומים באופן מיידי';

  @override
  String get showAll => 'הצג הכל';

  @override
  String get noTasksForToday => 'אין משימות להיום.\nבקש מ-Omi משימות נוספות או צור באופן ידני.';

  @override
  String get dailyScore => 'ניקוד יומי';

  @override
  String get dailyScoreDescription => 'ניקוד שיעזור לך\nלהתמקד בביצוע.';

  @override
  String get searchResults => 'תוצאות חיפוש';

  @override
  String get actionItems => 'פריטי פעולה';

  @override
  String get tasksToday => 'היום';

  @override
  String get tasksTomorrow => 'מחר';

  @override
  String get tasksNoDeadline => 'אין תאריך יעד';

  @override
  String get tasksLater => 'מאוחר יותר';

  @override
  String get loadingTasks => 'טוען משימות...';

  @override
  String get tasks => 'משימות';

  @override
  String get swipeTasksToIndent => 'החלק משימות כדי להזחה, גרור בין קטגוריות';

  @override
  String get create => 'צור';

  @override
  String get noTasksYet => 'אין משימות עדיין';

  @override
  String get tasksFromConversationsWillAppear => 'משימות מהשיחות שלך יופיעו כאן.\nלחץ צור כדי להוסיף אחת באופן ידני.';

  @override
  String get monthJan => 'ינו';

  @override
  String get monthFeb => 'פבר';

  @override
  String get monthMar => 'מרץ';

  @override
  String get monthApr => 'אפר';

  @override
  String get monthMay => 'מאי';

  @override
  String get monthJun => 'יוני';

  @override
  String get monthJul => 'יולי';

  @override
  String get monthAug => 'אוג';

  @override
  String get monthSep => 'ספט';

  @override
  String get monthOct => 'אוק';

  @override
  String get monthNov => 'נוב';

  @override
  String get monthDec => 'דצמ';

  @override
  String get timePM => 'אחה״צ';

  @override
  String get timeAM => 'בבוקר';

  @override
  String get actionItemUpdatedSuccessfully => 'פריט הפעולה עודכן בהצלחה';

  @override
  String get actionItemCreatedSuccessfully => 'פריט הפעולה נוצר בהצלחה';

  @override
  String get actionItemDeletedSuccessfully => 'פריט הפעולה נמחק בהצלחה';

  @override
  String get deleteActionItem => 'מחק פריט פעולה';

  @override
  String get deleteActionItemConfirmation => 'האם אתה בטוח שברצונך למחוק פריט פעולה זה? לא ניתן לבטל פעולה זו.';

  @override
  String get enterActionItemDescription => 'הזן תיאור פריט פעולה...';

  @override
  String get markAsCompleted => 'סמן כהושלם';

  @override
  String get setDueDateAndTime => 'הגדר תאריך וזמן הקבלה';

  @override
  String get reloadingApps => 'טוען אפליקציות מחדש...';

  @override
  String get loadingApps => 'טוען אפליקציות...';

  @override
  String get browseInstallCreateApps => 'עיין בו, התקן וצור אפליקציות';

  @override
  String get all => 'הכל';

  @override
  String get open => 'פתח';

  @override
  String get install => 'התקן';

  @override
  String get noAppsAvailable => 'אין אפליקציות זמינות';

  @override
  String get unableToLoadApps => 'לא ניתן לטעון אפליקציות';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'נסה להתאים מחדש את תנאי החיפוש או המסננים';

  @override
  String get checkBackLaterForNewApps => 'בדוק מאוחר יותר לאפליקציות חדשות';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'בדוק את חיבור האינטרנט שלך ונסה שוב';

  @override
  String get createNewApp => 'צור אפליקציה חדשה';

  @override
  String get buildSubmitCustomOmiApp => 'בנה והגש את אפליקציית Omi המותאמת שלך';

  @override
  String get submittingYourApp => 'הגשת האפליקציה שלך...';

  @override
  String get preparingFormForYou => 'הכנת הטופס עבורך...';

  @override
  String get appDetails => 'פרטי אפליקציה';

  @override
  String get paymentDetails => 'פרטי תשלום';

  @override
  String get previewAndScreenshots => 'תצוגה מקדימה וצילומי מסך';

  @override
  String get appCapabilities => 'יכולות אפליקציה';

  @override
  String get aiPrompts => 'הנושאים של AI';

  @override
  String get chatPrompt => 'הנושא של צ\'אט';

  @override
  String get chatPromptPlaceholder => 'אתה אפליקציה נהדרת, העבודה שלך היא להגיב לשאילתות המשתמש ולהרגיש אותם בטוב...';

  @override
  String get conversationPrompt => 'הנושא של שיחה';

  @override
  String get conversationPromptPlaceholder => 'אתה אפליקציה נהדרת, תינתן לך תמלול וסיכום של שיחה...';

  @override
  String get notificationScopes => 'טווחי הודעות';

  @override
  String get appPrivacyAndTerms => 'פרטיות אפליקציה ותנאים';

  @override
  String get makeMyAppPublic => 'הפוך את האפליקציה שלי לציבורית';

  @override
  String get submitAppTermsAgreement => 'בהגשת אפליקציה זו, אני מסכים לתנאי השירות ולמדיניות הפרטיות של Omi AI';

  @override
  String get submitApp => 'הגש אפליקציה';

  @override
  String get needHelpGettingStarted => 'צריך עזרה כדי להתחיל?';

  @override
  String get clickHereForAppBuildingGuides => 'לחץ כאן לקבלת מדריכי בנייה אפליקציה ותיעוד';

  @override
  String get submitAppQuestion => 'להגיש אפליקציה?';

  @override
  String get submitAppPublicDescription =>
      'האפליקציה שלך תבדוק ותהיה ציבורית. אתה יכול להתחיל להשתמש בה מיד, אפילו במהלך הבדיקה!';

  @override
  String get submitAppPrivateDescription =>
      'האפליקציה שלך תבדוק ותהיה זמינה לך באופן פרטי. אתה יכול להתחיל להשתמש בה מיד, אפילו במהלך הבדיקה!';

  @override
  String get startEarning => 'התחל להרוויח! 💰';

  @override
  String get connectStripeOrPayPal => 'חבר את Stripe או PayPal כדי לקבל תשלומים עבור האפליקציה שלך.';

  @override
  String get connectNow => 'התחבר עכשיו';

  @override
  String get installsCount => 'התקנות';

  @override
  String get uninstallApp => 'הסר התקנת אפליקציה';

  @override
  String get subscribe => 'הירשם';

  @override
  String get dataAccessNotice => 'הודעת גישה לנתונים';

  @override
  String get dataAccessWarning =>
      'אפליקציה זו תוכל לגשת לנתונים שלך. Omi AI אינה אחראית לאופן שבו הנתונים שלך משמשים, משתנים או נמחקים על ידי אפליקציה זו';

  @override
  String get installApp => 'התקן אפליקציה';

  @override
  String get betaTesterNotice => 'אתה בדוקה בטא עבור אפליקציה זו. היא עדיין לא ציבורית. היא תהיה ציבורית לאחר אישור.';

  @override
  String get appUnderReviewOwner => 'האפליקציה שלך בבדיקה וגלויה רק לך. היא תהיה ציבורית לאחר אישור.';

  @override
  String get appRejectedNotice => 'האפליקציה שלך נדחתה. אנא עדכן את פרטי האפליקציה והגש מחדש לבדיקה.';

  @override
  String get setupSteps => 'שלבי הגדרה';

  @override
  String get setupInstructions => 'הוראות הגדרה';

  @override
  String get integrationInstructions => 'הוראות שילוב';

  @override
  String get preview => 'תצוגה מקדימה';

  @override
  String get aboutTheApp => 'על האפליקציה';

  @override
  String get chatPersonality => 'אישיות הצ\'אט';

  @override
  String get ratingsAndReviews => 'דירוגים וביקורות';

  @override
  String get noRatings => 'ללא דירוגים';

  @override
  String ratingsCount(String count) {
    return '$count+ דירוגים';
  }

  @override
  String get errorActivatingApp => 'שגיאה בהפעלת האפליקציה';

  @override
  String get integrationSetupRequired => 'אם זו אפליקציית שילוב, ודא שהגדרה הושלמה.';

  @override
  String get installed => 'מותקן';

  @override
  String get appIdLabel => 'מזהה אפליקציה';

  @override
  String get appNameLabel => 'שם אפליקציה';

  @override
  String get appNamePlaceholder => 'אפליקציה נהדרת שלי';

  @override
  String get pleaseEnterAppName => 'אנא הזן שם אפליקציה';

  @override
  String get categoryLabel => 'קטגוריה';

  @override
  String get selectCategory => 'בחר קטגוריה';

  @override
  String get descriptionLabel => 'תיאור';

  @override
  String get appDescriptionPlaceholder =>
      'אפליקציה נהדרת שלי היא אפליקציה מעולה שעושה דברים מדהימים. היא האפליקציה הטובה ביותר!';

  @override
  String get pleaseProvideValidDescription => 'אנא בחר תיאור תקף';

  @override
  String get appPricingLabel => 'תמחור אפליקציה';

  @override
  String get noneSelected => 'לא נבחר';

  @override
  String get appIdCopiedToClipboard => 'מזהה אפליקציה הועתק ללוח';

  @override
  String get appCategoryModalTitle => 'קטגוריית אפליקציה';

  @override
  String get pricingFree => 'חינם';

  @override
  String get pricingPaid => 'בתשלום';

  @override
  String get loadingCapabilities => 'טוען יכולות...';

  @override
  String get filterInstalled => 'מותקן';

  @override
  String get filterMyApps => 'האפליקציות שלי';

  @override
  String get clearSelection => 'נקה בחירה';

  @override
  String get filterCategory => 'קטגוריה';

  @override
  String get rating4PlusStars => '4+ כוכבים';

  @override
  String get rating3PlusStars => '3+ כוכבים';

  @override
  String get rating2PlusStars => '2+ כוכבים';

  @override
  String get rating1PlusStars => '1+ כוכבים';

  @override
  String get filterRating => 'דירוג';

  @override
  String get filterCapabilities => 'יכולות';

  @override
  String get noNotificationScopesAvailable => 'אין טווחי הודעות זמינים';

  @override
  String get popularApps => 'אפליקציות פופולריות';

  @override
  String get pleaseProvidePrompt => 'אנא בחר הנושא';

  @override
  String chatWithAppName(String appName) {
    return 'צ\'אט עם $appName';
  }

  @override
  String get defaultAiAssistant => 'עוזר AI ברירת המחדל';

  @override
  String get readyToChat => '✨ מוכן לצ\'אט!';

  @override
  String get connectionNeeded => '🌐 נדרש חיבור';

  @override
  String get startConversation => 'התחל שיחה והנח הקסם יתחיל';

  @override
  String get checkInternetConnection => 'אנא בדוק את חיבור האינטרנט שלך';

  @override
  String get wasThisHelpful => 'האם זה היה מועיל?';

  @override
  String get thankYouForFeedback => 'תודה על משוב!';

  @override
  String get maxFilesUploadError => 'אתה יכול להעלות רק 4 קבצים בבת אחת';

  @override
  String get attachedFiles => '📎 קבצים מצורפים';

  @override
  String get takePhoto => 'צלם תמונה';

  @override
  String get captureWithCamera => 'צלם בעזרת מצלמה';

  @override
  String get selectImages => 'בחר תמונות';

  @override
  String get chooseFromGallery => 'בחר מהגלריה';

  @override
  String get selectFile => 'בחר קובץ';

  @override
  String get chooseAnyFileType => 'בחר סוג קובץ כלשהו';

  @override
  String get cannotReportOwnMessages => 'לא יכול להדיח את ההודעות שלך';

  @override
  String get messageReportedSuccessfully => '✅ הודעה דווחה בהצלחה';

  @override
  String get confirmReportMessage => 'האם אתה בטוח שברצונך להדיח הודעה זו?';

  @override
  String get selectChatAssistant => 'בחר עוזר צ\'אט';

  @override
  String get enableMoreApps => 'הפעל אפליקציות נוספות';

  @override
  String get chatCleared => 'הצ\'אט נקוי';

  @override
  String get clearChatTitle => 'נקה צ\'אט?';

  @override
  String get confirmClearChat => 'האם אתה בטוח שברצונך לנקות את הצ\'אט? לא ניתן לבטל פעולה זו.';

  @override
  String get copy => 'העתק';

  @override
  String get share => 'שתף';

  @override
  String get report => 'דווח';

  @override
  String get microphonePermissionRequired => 'הרשאת מיקרופון נדרשת לביצוע שיחות';

  @override
  String get microphonePermissionDenied =>
      'הרשאת מיקרופון נדחתה. אנא תן הרשאה בהעדפות המערכת > פרטיות וביטחון > מיקרופון.';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'בדיקת הרשאת מיקרופון נכשלה: $error';
  }

  @override
  String get failedToTranscribeAudio => 'תמלול שמע נכשל';

  @override
  String get transcribing => 'מתמללל...';

  @override
  String get transcriptionFailed => 'התמלול נכשל';

  @override
  String get discardedConversation => 'שיחה מושלכת';

  @override
  String get at => 'ב-';

  @override
  String get from => 'מ-';

  @override
  String get copied => 'הועתק!';

  @override
  String get copyLink => 'העתק קישור';

  @override
  String get hideTranscript => 'הסתר תמלול';

  @override
  String get viewTranscript => 'צפה בתמלול';

  @override
  String get conversationDetails => 'פרטי שיחה';

  @override
  String get transcript => 'תמלול';

  @override
  String segmentsCount(int count) {
    return '$count קטעים';
  }

  @override
  String get noTranscriptAvailable => 'אין תמלול זמין';

  @override
  String get noTranscriptMessage => 'לשיחה זו אין תמלול.';

  @override
  String get conversationUrlCouldNotBeGenerated => 'לא ניתן היה ליצור כתובת URL של שיחה.';

  @override
  String get failedToGenerateConversationLink => 'יצירת קישור שיחה נכשלה';

  @override
  String get failedToGenerateShareLink => 'יצירת קישור שיתוף נכשלה';

  @override
  String get reloadingConversations => 'טוען שיחות מחדש...';

  @override
  String get user => 'משתמש';

  @override
  String get starred => 'מסומן בכוכב';

  @override
  String get date => 'תאריך';

  @override
  String get noResultsFound => 'לא נמצאו תוצאות';

  @override
  String get tryAdjustingSearchTerms => 'נסה להתאים מחדש את תנאי החיפוש';

  @override
  String get starConversationsToFindQuickly => 'סמן שיחות בכוכב כדי למצוא אותן במהירות כאן';

  @override
  String noConversationsOnDate(String date) {
    return 'אין שיחות ב-$date';
  }

  @override
  String get trySelectingDifferentDate => 'נסה לבחור תאריך שונה';

  @override
  String get conversations => 'שיחות';

  @override
  String get chat => 'צ\'אט';

  @override
  String get actions => 'פעולות';

  @override
  String get syncAvailable => 'סנכרון זמין';

  @override
  String get referAFriend => 'הפנה חבר';

  @override
  String get help => 'עזרה';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'שדרג ל-Pro';

  @override
  String get getOmiDevice => 'קנה מכשיר Omi';

  @override
  String get wearableAiCompanion => 'בן לוויה AI ללבישה';

  @override
  String get loadingMemories => 'טוען זיכרונות...';

  @override
  String get allMemories => 'כל הזיכרונות';

  @override
  String get aboutYou => 'אודותיך';

  @override
  String get manual => 'ידני';

  @override
  String get loadingYourMemories => 'טוען את הזיכרונות שלך...';

  @override
  String get createYourFirstMemory => 'צור את הזיכרון הראשון שלך כדי להתחיל';

  @override
  String get tryAdjustingFilter => 'נסה להתאים מחדש את החיפוש או המסנן';

  @override
  String get whatWouldYouLikeToRemember => 'מה היית רוצה לזכור?';

  @override
  String get category => 'קטגוריה';

  @override
  String get public => 'ציבורי';

  @override
  String get failedToSaveCheckConnection => 'השמירה נכשלה. אנא בדוק את החיבור שלך.';

  @override
  String get createMemory => 'צור זיכרון';

  @override
  String get deleteMemoryConfirmation => 'האם אתה בטוח שברצונך למחוק זיכרון זה? לא ניתן לבטל פעולה זו.';

  @override
  String get makePrivate => 'הפוך לפרטי';

  @override
  String get organizeAndControlMemories => 'ארגן ושלוט בזיכרונות';

  @override
  String get total => 'סה״כ';

  @override
  String get makeAllMemoriesPrivate => 'הפוך את כל הזיכרונות לפרטיים';

  @override
  String get setAllMemoriesToPrivate => 'הגדר את כל הזיכרונות לגלויות פרטיות';

  @override
  String get makeAllMemoriesPublic => 'הפוך את כל הזיכרונות לציבוריים';

  @override
  String get setAllMemoriesToPublic => 'הגדר את כל הזיכרונות לגלויות ציבוריות';

  @override
  String get permanentlyRemoveAllMemories => 'הסר באופן קבוע את כל הזיכרונות מ-Omi';

  @override
  String get allMemoriesAreNowPrivate => 'כל הזיכרונות פרטיים כעת';

  @override
  String get allMemoriesAreNowPublic => 'כל הזיכרונות ציבוריים כעת';

  @override
  String get clearOmisMemory => 'נקה את הזיכרון של Omi';

  @override
  String clearMemoryConfirmation(int count) {
    return 'האם אתה בטוח שברצונך לנקות את הזיכרון של Omi? פעולה זו לא יכולה להיות בוטלה ותמחק בצורה קבועה את כל $count הזיכרונות.';
  }

  @override
  String get omisMemoryCleared => 'הזיכרון של Omi עליך נוקה';

  @override
  String get welcomeToOmi => 'ברוכים הבאים ל-Omi';

  @override
  String get continueWithApple => 'המשך עם Apple';

  @override
  String get continueWithGoogle => 'המשך עם Google';

  @override
  String get byContinuingYouAgree => 'בהמשך שלך, אתה מסכים ל';

  @override
  String get termsOfService => 'תנאי השירות';

  @override
  String get and => ' ו';

  @override
  String get dataAndPrivacy => 'נתונים וביטחון פרטיות';

  @override
  String get secureAuthViaAppleId => 'אימות מאובטח דרך Apple ID';

  @override
  String get secureAuthViaGoogleAccount => 'אימות מאובטח דרך חשבון Google';

  @override
  String get whatWeCollect => 'מה אנחנו אוספים';

  @override
  String get dataCollectionMessage =>
      'בהמשך שלך, השיחות, ההקלטות והמידע האישי שלך יישמרו בצורה מאובטחת בשרתים שלנו כדי לספק תובנות בהנעת AI ולהפוך את כל תכונות האפליקציה לאפשריות.';

  @override
  String get dataProtection => 'הגנת נתונים';

  @override
  String get yourDataIsProtected => 'הנתונים שלך מוגנים וכפופים ל';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'אנא בחר בשפה הראשונה שלך';

  @override
  String get chooseYourLanguage => 'בחר את שפתך';

  @override
  String get selectPreferredLanguageForBestExperience => 'בחר את השפה המועדפת עליך לחוויית Omi הטובה ביותר';

  @override
  String get searchLanguages => 'חפש שפות...';

  @override
  String get selectALanguage => 'בחר שפה';

  @override
  String get tryDifferentSearchTerm => 'נסה מונח חיפוש אחר';

  @override
  String get pleaseEnterYourName => 'אנא הזן את שמך';

  @override
  String get nameMustBeAtLeast2Characters => 'השם חייב להיות לפחות 2 תווים';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'ספר לנו איך היית רוצה להיקרא. זה עוזר להתאים אישית את חוויית Omi שלך.';

  @override
  String charactersCount(int count) {
    return '$count תווים';
  }

  @override
  String get enableFeaturesForBestExperience => 'הפעל תכונות לחוויית Omi הטובה ביותר בהתקנה שלך.';

  @override
  String get microphoneAccess => 'גישה למיקרופון';

  @override
  String get recordAudioConversations => 'הקלט שיחות אודיו';

  @override
  String get microphoneAccessDescription => 'Omi צריכה גישה למיקרופון כדי להקליט את השיחות שלך ולספק עתודות.';

  @override
  String get screenRecording => 'הקלטת מסך';

  @override
  String get captureSystemAudioFromMeetings => 'תפוס אודיו מערכת מפגישות';

  @override
  String get screenRecordingDescription => 'Omi זקוקה להרשאת הקלטת מסך כדי לתפוס אודיו מערכת מהפגישות בדפדפן שלך.';

  @override
  String get accessibility => 'נגישות';

  @override
  String get detectBrowserBasedMeetings => 'זהה פגישות מבוססות דפדפן';

  @override
  String get accessibilityDescription =>
      'Omi זקוקה להרשאת נגישות כדי לזהות כאשר אתה משתתף בפגישות Zoom, Meet או Teams בדפדפן שלך.';

  @override
  String get pleaseWait => 'אנא המתן...';

  @override
  String get joinTheCommunity => 'הצטרף לקהילה!';

  @override
  String get loadingProfile => 'טוען פרופיל...';

  @override
  String get profileSettings => 'הגדרות פרופיל';

  @override
  String get noEmailSet => 'לא הוגדר דוא\"ל';

  @override
  String get userIdCopiedToClipboard => 'מזהה משתמש הועתק ללוח העריכה';

  @override
  String get yourInformation => 'המידע שלך';

  @override
  String get setYourName => 'קבע את שמך';

  @override
  String get changeYourName => 'שנה את שמך';

  @override
  String get voiceAndPeople => 'קול ואנשים';

  @override
  String get teachOmiYourVoice => 'לימד את Omi את קולך';

  @override
  String get tellOmiWhoSaidIt => 'ספר ל-Omi מי אמר זאת 🗣️';

  @override
  String get payment => 'תשלום';

  @override
  String get addOrChangeYourPaymentMethod => 'הוסף או שנה את שיטת התשלום שלך';

  @override
  String get preferences => 'העדפות';

  @override
  String get helpImproveOmiBySharing => 'עזור לשפר את Omi בשיתוף נתוני ניתוח מאומתות';

  @override
  String get deleteAccount => 'מחק חשבון';

  @override
  String get deleteYourAccountAndAllData => 'מחק את חשבונך וכל הנתונים שלך';

  @override
  String get clearLogs => 'נקה יומנים';

  @override
  String get debugLogsCleared => 'יומני ניפוי הנתונים נוקו';

  @override
  String get exportConversations => 'ייצא שיחות';

  @override
  String get exportAllConversationsToJson => 'ייצא את כל השיחות שלך לקובץ JSON.';

  @override
  String get conversationsExportStarted => 'ייצוא שיחות החל. זה עשוי לקחת כמה שניות, אנא המתן.';

  @override
  String get mcpDescription =>
      'כדי לחבר את Omi עם יישומים אחרים כדי לקרוא, לחפוש ולנהל את הזיכרונות והשיחות שלך. צור מפתח כדי להתחיל.';

  @override
  String get apiKeys => 'מפתחות API';

  @override
  String errorLabel(String error) {
    return 'שגיאה: $error';
  }

  @override
  String get noApiKeysFound => 'לא נמצאו מפתחות API. צור אחד כדי להתחיל.';

  @override
  String get advancedSettings => 'הגדרות מתקדמות';

  @override
  String get triggersWhenNewConversationCreated => 'מופעל כאשר נוצרת שיחה חדשה.';

  @override
  String get triggersWhenNewTranscriptReceived => 'מופעל כאשר מתקבלת עתודה חדשה.';

  @override
  String get realtimeAudioBytes => 'בתים אודיו בזמן אמת';

  @override
  String get triggersWhenAudioBytesReceived => 'מופעל כאשר מתקבלים בתים אודיו.';

  @override
  String get everyXSeconds => 'כל x שניות';

  @override
  String get triggersWhenDaySummaryGenerated => 'מופעל כאשר מתבצע סיכום יום.';

  @override
  String get tryLatestExperimentalFeatures => 'נסה את התכונות הניסיוניות העדכניות מקבוצת Omi.';

  @override
  String get transcriptionServiceDiagnosticStatus => 'מצב אבחון של שירות תמלול';

  @override
  String get enableDetailedDiagnosticMessages => 'הפעל הודעות אבחון מפורטות משירות התמלול';

  @override
  String get autoCreateAndTagNewSpeakers => 'צור וציין בעלי קול חדשים באופן אוטומטי';

  @override
  String get automaticallyCreateNewPerson => 'צור באופן אוטומטי אדם חדש כאשר שם מזוהה בעתודה.';

  @override
  String get pilotFeatures => 'תכונות חלוציות';

  @override
  String get pilotFeaturesDescription => 'התכונות הללו הן בדיקות וללא התחייבות לתמיכה.';

  @override
  String get suggestFollowUpQuestion => 'הצע שאלת המשך';

  @override
  String get saveSettings => 'שמור הגדרות';

  @override
  String get syncingDeveloperSettings => 'סנכרון הגדרות מפתח...';

  @override
  String get summary => 'סיכום';

  @override
  String get auto => 'אוטומטי';

  @override
  String get noSummaryForApp => 'אין סיכום זמין עבור אפליקציה זו. נסה אפליקציה אחרת לקבלת תוצאות טובות יותר.';

  @override
  String get tryAnotherApp => 'נסה אפליקציה אחרת';

  @override
  String generatedBy(String appName) {
    return 'הנוצר על ידי $appName';
  }

  @override
  String get overview => 'סקירה כללית';

  @override
  String get otherAppResults => 'תוצאות אפליקציות אחרות';

  @override
  String get unknownApp => 'אפליקציה לא ידועה';

  @override
  String get noSummaryAvailable => 'אין סיכום זמין';

  @override
  String get conversationNoSummaryYet => 'לשיחה זו אין סיכום עדיין.';

  @override
  String get chooseSummarizationApp => 'בחר אפליקציית סיכום';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName הוגדרה כאפליקציית סיכום ברירת המחדל';
  }

  @override
  String get letOmiChooseAutomatically => 'תן לOmi לבחור את האפליקציה הטובה ביותר באופן אוטומטי';

  @override
  String get deleteConversationConfirmation => 'האם אתה בטוח שברצונך למחוק שיחה זו? אין דרך לבטל פעולה זו.';

  @override
  String get conversationDeleted => 'השיחה נמחקה';

  @override
  String get generatingLink => 'הוצר קישור...';

  @override
  String get editConversation => 'ערוך שיחה';

  @override
  String get conversationLinkCopiedToClipboard => 'קישור השיחה הועתק ללוח העריכה';

  @override
  String get conversationTranscriptCopiedToClipboard => 'עתודת השיחה הועתקה ללוח העריכה';

  @override
  String get editConversationDialogTitle => 'ערוך שיחה';

  @override
  String get changeTheConversationTitle => 'שנה את כותרת השיחה';

  @override
  String get conversationTitle => 'כותרת השיחה';

  @override
  String get enterConversationTitle => 'הזן כותרת שיחה...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'כותרת השיחה עודכנה בהצלחה';

  @override
  String get failedToUpdateConversationTitle => 'עדכון כותרת השיחה נכשל';

  @override
  String get errorUpdatingConversationTitle => 'שגיאה בעדכון כותרת השיחה';

  @override
  String get settingUp => 'מתקדם...';

  @override
  String get startYourFirstRecording => 'התחל את ההקלטה הראשונה שלך';

  @override
  String get preparingSystemAudioCapture => 'הכנה ללכידת אודיו מערכת';

  @override
  String get clickTheButtonToCaptureAudio =>
      'לחץ על הכפתור כדי ללכוד אודיו עבור עתודות חיות, תובנות AI וחיסכון אוטומטי.';

  @override
  String get reconnecting => 'חיבור חדש...';

  @override
  String get recordingPaused => 'הקלטה מושהה';

  @override
  String get recordingActive => 'הקלטה פעילה';

  @override
  String get startRecording => 'התחל הקלטה';

  @override
  String resumingInCountdown(String countdown) {
    return 'ממשך ב${countdown}s...';
  }

  @override
  String get tapPlayToResume => 'לחץ על הפעלה כדי להמשיך';

  @override
  String get listeningForAudio => 'מקשיב לאודיו...';

  @override
  String get preparingAudioCapture => 'הכנה ללכידת אודיו';

  @override
  String get clickToBeginRecording => 'לחץ כדי להתחיל הקלטה';

  @override
  String get translated => 'תורגם';

  @override
  String get liveTranscript => 'עתודה חיה';

  @override
  String segmentsSingular(String count) {
    return '$count קטע';
  }

  @override
  String segmentsPlural(String count) {
    return '$count קטעים';
  }

  @override
  String get startRecordingToSeeTranscript => 'התחל הקלטה כדי לראות עתודה חיה';

  @override
  String get paused => 'מושהה';

  @override
  String get initializing => 'אתחול...';

  @override
  String get recording => 'הקלטה';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'מיקרופון השתנה. ממשך ב${countdown}s';
  }

  @override
  String get clickPlayToResumeOrStop => 'לחץ על הפעלה כדי להמשיך או עצור כדי לסיים';

  @override
  String get settingUpSystemAudioCapture => 'הגדרה של לכידת אודיו מערכת';

  @override
  String get capturingAudioAndGeneratingTranscript => 'לכידת אודיו והוצרת עתודה';

  @override
  String get clickToBeginRecordingSystemAudio => 'לחץ כדי להתחיל הקלטת אודיו מערכת';

  @override
  String get you => 'אתה';

  @override
  String speakerWithId(String speakerId) {
    return 'דובר $speakerId';
  }

  @override
  String get translatedByOmi => 'תורגם על ידי omi';

  @override
  String get backToConversations => 'חזור לשיחות';

  @override
  String get systemAudio => 'מערכת';

  @override
  String get mic => 'מיק';

  @override
  String audioInputSetTo(String deviceName) {
    return 'קלט אודיו מוגדר ל$deviceName';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'שגיאה בהחלפת התקן אודיו: $error';
  }

  @override
  String get selectAudioInput => 'בחר קלט אודיו';

  @override
  String get loadingDevices => 'טוען התקנים...';

  @override
  String get settingsHeader => 'הגדרות';

  @override
  String get plansAndBilling => 'תוכניות וחיוב';

  @override
  String get calendarIntegration => 'שילוב יומן';

  @override
  String get dailySummary => 'סיכום יומי';

  @override
  String get developer => 'מפתח';

  @override
  String get about => 'אודות';

  @override
  String get selectTime => 'בחר זמן';

  @override
  String get accountGroup => 'חשבון';

  @override
  String get signOutQuestion => 'להתנתק?';

  @override
  String get signOutConfirmation => 'האם אתה בטוח שברצונך להתנתק?';

  @override
  String get customVocabularyHeader => 'אוצר מילים מותאם אישית';

  @override
  String get addWordsDescription => 'הוסף מילים שOmi צריכה להכיר בזמן התמלול.';

  @override
  String get enterWordsHint => 'הזן מילים (מופרדות בפסיקים)';

  @override
  String get dailySummaryHeader => 'סיכום יומי';

  @override
  String get dailySummaryTitle => 'סיכום יומי';

  @override
  String get dailySummaryDescription => 'קבל סיכום מותאם אישית של שיחות היום שלך שהועבר כהודעה.';

  @override
  String get deliveryTime => 'זמן הגשה';

  @override
  String get deliveryTimeDescription => 'כמתי תקבל את הסיכום היומי שלך';

  @override
  String get subscription => 'מנוי';

  @override
  String get viewPlansAndUsage => 'צפה בתוכניות ובשימוש';

  @override
  String get viewPlansDescription => 'נהל את המנוי שלך וראה סטטיסטיקות שימוש';

  @override
  String get addOrChangePaymentMethod => 'הוסף או שנה את שיטת התשלום שלך';

  @override
  String get displayOptions => 'אפשרויות תצוגה';

  @override
  String get showMeetingsInMenuBar => 'הצג פגישות בשורת התפריטים';

  @override
  String get displayUpcomingMeetingsDescription => 'הצג פגישות קרובות בשורת התפריטים';

  @override
  String get showEventsWithoutParticipants => 'הצג אירועים ללא משתתפים';

  @override
  String get includePersonalEventsDescription => 'כלול אירועים אישיים ללא משתתפים';

  @override
  String get upcomingMeetings => 'פגישות קרובות';

  @override
  String get checkingNext7Days => 'בדיקה 7 הימים הקרובים';

  @override
  String get shortcuts => 'קיצורים';

  @override
  String get shortcutChangeInstruction => 'לחץ על קיצור כדי לשנות אותו. לחץ Escape כדי לבטל.';

  @override
  String get configureSTTProvider => 'הגדר ספק STT';

  @override
  String get setConversationEndDescription => 'הגדר מתי שיחות מסתיימות באופן אוטומטי';

  @override
  String get importDataDescription => 'ייבא נתונים ממקורות אחרים';

  @override
  String get exportConversationsDescription => 'ייצא שיחות ל-JSON';

  @override
  String get exportingConversations => 'ייצוא שיחות...';

  @override
  String get clearNodesDescription => 'נקה את כל הצמתים וההתחברויות';

  @override
  String get deleteKnowledgeGraphQuestion => 'מחק גרף ידע?';

  @override
  String get deleteKnowledgeGraphWarning =>
      'זה ימחק את כל נתוני גרף הידע שהוכלו. הזיכרונות המקוריים שלך נשמרים בבטחון.';

  @override
  String get connectOmiWithAI => 'חבר את Omi עם עוזרים AI';

  @override
  String get noAPIKeys => 'אין מפתחות API. צור אחד כדי להתחיל.';

  @override
  String get autoCreateWhenDetected => 'צור באופן אוטומטי כאשר שם מזוהה';

  @override
  String get trackPersonalGoals => 'עקוב אחר יעדים אישיים בדף הבית';

  @override
  String get endpointURL => 'כתובת URL של נקודת קצה';

  @override
  String get links => 'קישורים';

  @override
  String get discordMemberCount => '8000+ חברים ב-Discord';

  @override
  String get userInformation => 'מידע משתמש';

  @override
  String get capabilities => 'יכולות';

  @override
  String get previewScreenshots => 'תצוגה מקדימה של צילומי מסך';

  @override
  String get holdOnPreparingForm => 'המתן, אנחנו מכינים את הטופס עבורך';

  @override
  String get bySubmittingYouAgreeToOmi => 'בהגשה, אתה מסכים ל-Omi';

  @override
  String get termsAndPrivacyPolicy => 'תנאים ומדיניות פרטיות';

  @override
  String get helpsDiagnoseIssuesAutoDeletes => 'עוזר לאבחן בעיות. מחיקה אוטומטית לאחר 3 ימים.';

  @override
  String get manageYourApp => 'נהל את האפליקציה שלך';

  @override
  String get updatingYourApp => 'עדכון האפליקציה שלך';

  @override
  String get fetchingYourAppDetails => 'אחזור פרטי האפליקציה שלך';

  @override
  String get updateAppQuestion => 'עדכן אפליקציה?';

  @override
  String get updateAppConfirmation => 'האם אתה בטוח שברצונך לעדכן את האפליקציה שלך? השינויים יישקפו לאחר בדיקה מצדנו.';

  @override
  String get updateApp => 'עדכן אפליקציה';

  @override
  String get createAndSubmitNewApp => 'צור והגש אפליקציה חדשה';

  @override
  String appsCount(String count) {
    return 'אפליקציות ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'אפליקציות פרטיות ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'אפליקציות ציבוריות ($count)';
  }

  @override
  String get newVersionAvailable => 'גרסה חדשה זמינה 🎉';

  @override
  String get no => 'לא';

  @override
  String get subscriptionCancelledSuccessfully => 'המנוי בוטל בהצלחה. הוא יישאר פעיל עד סוף תקופת החיוב הנוכחית.';

  @override
  String get failedToCancelSubscription => 'ביטול המנוי נכשל. אנא נסה שוב.';

  @override
  String get invalidPaymentUrl => 'כתובת URL לתשלום לא חוקית';

  @override
  String get permissionsAndTriggers => 'הרשאות וטריגרים';

  @override
  String get chatFeatures => 'תכונות צ\'אט';

  @override
  String get uninstall => 'הסר התקנה';

  @override
  String get installs => 'התקנות';

  @override
  String get priceLabel => 'מחיר';

  @override
  String get updatedLabel => 'עודכן';

  @override
  String get createdLabel => 'נוצר';

  @override
  String get featuredLabel => 'מובחר';

  @override
  String get cancelSubscriptionQuestion => 'בטל מנוי?';

  @override
  String get cancelSubscriptionConfirmation =>
      'האם אתה בטוח שברצונך לבטל את המנוי שלך? תהיה לך גישה מתמשכת עד סוף תקופת החיוב הנוכחית.';

  @override
  String get cancelSubscriptionButton => 'בטל מנוי';

  @override
  String get cancelling => 'ביטול...';

  @override
  String get betaTesterMessage => 'אתה בודק בטא עבור אפליקציה זו. היא עדיין לא ציבורית. היא תהיה ציבורית לאחר אישור.';

  @override
  String get appUnderReviewMessage => 'האפליקציה שלך נמצאת בבדיקה וגלויה רק לך. היא תהיה ציבורית לאחר אישור.';

  @override
  String get appRejectedMessage => 'האפליקציה שלך נדחתה. אנא עדכן את פרטי האפליקציה והגש מחדש לבדיקה.';

  @override
  String get invalidIntegrationUrl => 'כתובת URL של שילוב לא חוקית';

  @override
  String get tapToComplete => 'לחץ כדי להשלים';

  @override
  String get invalidSetupInstructionsUrl => 'כתובת URL של הוראות הגדרה לא חוקית';

  @override
  String get pushToTalk => 'דחוף לדבר';

  @override
  String get summaryPrompt => 'בקשת סיכום';

  @override
  String get pleaseSelectARating => 'אנא בחר דירוג';

  @override
  String get reviewAddedSuccessfully => 'סקירה נוספה בהצלחה 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'סקירה עודכנה בהצלחה 🚀';

  @override
  String get failedToSubmitReview => 'הגשת הסקירה נכשלה. אנא נסה שוב.';

  @override
  String get addYourReview => 'הוסף את הסקירה שלך';

  @override
  String get editYourReview => 'ערוך את הסקירה שלך';

  @override
  String get writeAReviewOptional => 'כתוב סקירה (אופציונלי)';

  @override
  String get submitReview => 'הגש סקירה';

  @override
  String get updateReview => 'עדכן סקירה';

  @override
  String get yourReview => 'הסקירה שלך';

  @override
  String get anonymousUser => 'משתמש אנונימי';

  @override
  String get issueActivatingApp => 'היתה בעיה בהפעלת האפליקציה הזו. אנא נסה שוב.';

  @override
  String get dataAccessNoticeDescription =>
      'אפליקציה זו תגיע לגישה לנתונים שלך. Omi AI אינה אחראית לאופן השימוש, השינוי או המחיקה של הנתונים שלך על ידי אפליקציה זו.';

  @override
  String get copyUrl => 'העתק כתובת URL';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => 'ב\'';

  @override
  String get weekdayTue => 'ג\'';

  @override
  String get weekdayWed => 'ד\'';

  @override
  String get weekdayThu => 'ה\'';

  @override
  String get weekdayFri => 'ו\'';

  @override
  String get weekdaySat => 'ש\'';

  @override
  String get weekdaySun => 'א\'';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return 'שילוב $serviceName בקרוב';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'כבר יצא ל$platform';
  }

  @override
  String get anotherPlatform => 'פלטפורמה אחרת';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'אנא האמת עם $serviceName בהגדרות > שילובי משימות';
  }

  @override
  String addingToService(String serviceName) {
    return 'הוספה ל$serviceName...';
  }

  @override
  String addedToService(String serviceName) {
    return 'נוסף ל$serviceName';
  }

  @override
  String failedToAddToService(String serviceName) {
    return 'הוספה ל$serviceName נכשלה';
  }

  @override
  String get permissionDeniedForAppleReminders => 'הרשאה נדחתה ל-Apple Reminders';

  @override
  String failedToCreateApiKey(String error) {
    return 'יצירת מפתח API של ספק נכשלה: $error';
  }

  @override
  String get createAKey => 'צור מפתח';

  @override
  String get apiKeyRevokedSuccessfully => 'מפתח API בוטל בהצלחה';

  @override
  String failedToRevokeApiKey(String error) {
    return 'ביטול מפתח API נכשל: $error';
  }

  @override
  String get omiApiKeys => 'מפתחות API של Omi';

  @override
  String get apiKeysDescription =>
      'מפתחות API משמשים לאימות כאשר האפליקציה שלך תקשרת עם שרת OMI. הם מאפשרים לאפליקציה שלך ליצור זיכרונות ולגשת לשירותי OMI אחרים בצורה מאובטחת.';

  @override
  String get aboutOmiApiKeys => 'אודות מפתחות API של Omi';

  @override
  String get yourNewKey => 'המפתח החדש שלך:';

  @override
  String get copyToClipboard => 'העתק ללוח העריכה';

  @override
  String get pleaseCopyKeyNow => 'אנא העתק אותו כעת וכתוב אותו למקום בטוח כלשהו.';

  @override
  String get willNotSeeAgain => 'לא תוכל לראות זאת שוב.';

  @override
  String get revokeKey => 'בטל מפתח';

  @override
  String get revokeApiKeyQuestion => 'בטל מפתח API?';

  @override
  String get revokeApiKeyWarning => 'לא ניתן לבטל פעולה זו. כל יישומים המשתמשים במפתח זה לא יוכלו עוד להשתמש ב-API.';

  @override
  String get revoke => 'בטל';

  @override
  String get whatWouldYouLikeToCreate => 'מה היית רוצה ליצור?';

  @override
  String get createAnApp => 'צור אפליקציה';

  @override
  String get createAndShareYourApp => 'צור ושתף את האפליקציה שלך';

  @override
  String get itemApp => 'אפליקציה';

  @override
  String keepItemPublic(String item) {
    return 'שמור $item ציבורית';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return 'הפוך $item לציבורית?';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return 'הפוך $item לפרטית?';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'אם תפוך את ה$item לציבורית, היא יכולה להשתמש בה כל אחד';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'אם תפוך את ה$item לפרטית כעת, היא תפסיק לעבוד עבור כולם ותהיה גלויה רק לך';
  }

  @override
  String get manageApp => 'נהל אפליקציה';

  @override
  String deleteItemTitle(String item) {
    return 'מחק $item';
  }

  @override
  String deleteItemQuestion(String item) {
    return 'מחק $item?';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'האם אתה בטוח שברצונך למחוק את ה$item הזה? אין דרך לבטל פעולה זו.';
  }

  @override
  String get revokeKeyQuestion => 'בטל מפתח?';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'האם אתה בטוח שברצונך לבטל את המפתח \"$keyName\"? אין דרך לבטל פעולה זו.';
  }

  @override
  String get createNewKey => 'צור מפתח חדש';

  @override
  String get keyNameHint => 'למשל, Claude Desktop';

  @override
  String get pleaseEnterAName => 'אנא הזן שם.';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'יצירת מפתח נכשלה: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'יצירת מפתח נכשלה. אנא נסה שוב.';

  @override
  String get keyCreated => 'מפתח נוצר';

  @override
  String get keyCreatedMessage => 'המפתח החדש שלך נוצר. אנא העתק אותו כעת. לא תוכל לראות זאת שוב.';

  @override
  String get keyWord => 'מפתח';

  @override
  String get externalAppAccess => 'גישה לאפליקציה חיצונית';

  @override
  String get externalAppAccessDescription =>
      'היישומים המותקנים הבאים כוללים שילובים חיצוניים ויכולים לגשת לנתונים שלך, כגון שיחות וזיכרונות.';

  @override
  String get noExternalAppsHaveAccess => 'לאיזה אפליקציות חיצוניות אין גישה לנתונים שלך.';

  @override
  String get maximumSecurityE2ee => 'אבטחה מקסימלית (E2EE)';

  @override
  String get e2eeDescription =>
      'הצפנה מקצה לקצה היא התקן הזהב לפרטיות. כאשר זה מופעל, הנתונים שלך מוצפנים בהתקן שלך לפני שהם נשלחים לשרתים שלנו. זה אומר שאף אחד, אפילו Omi, לא יכול לגשת לתוכן שלך.';

  @override
  String get importantTradeoffs => 'סחר חשוב:';

  @override
  String get e2eeTradeoff1 => '• ייתכן שחלק מהתכונות כמו שילובי אפליקציות חיצוניות יהיו מובטלות.';

  @override
  String get e2eeTradeoff2 => '• אם תאבד את הסיסמה שלך, לא ניתן לשחזר את הנתונים שלך.';

  @override
  String get featureComingSoon => 'התכונה הזו בקרוב!';

  @override
  String get migrationInProgressMessage => 'הגירה מתנהלת. לא תוכל לשנות את רמת ההגנה עד שזה יוסיף.';

  @override
  String get migrationFailed => 'הגירה נכשלה';

  @override
  String migratingFromTo(String source, String target) {
    return 'הגירה מ$source ל$target';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total אובייקטים';
  }

  @override
  String get secureEncryption => 'הצפנה מאובטחת';

  @override
  String get secureEncryptionDescription =>
      'הנתונים שלך מוצפנים עם מפתח ייחודי לך בשרתים שלנו, מתוחזקים על Google Cloud. זה אומר שהתוכן הגולמי שלך לא נגיש לאף אחד, כולל צוות Omi או Google, ישירות מ-DB.';

  @override
  String get endToEndEncryption => 'הצפנה מקצה לקצה';

  @override
  String get e2eeCardDescription => 'הפעל לאבטחה מקסימלית שבה רק אתה יכול לגשת לנתונים שלך. לחץ כדי ללמוד עוד.';

  @override
  String get dataAlwaysEncrypted => 'ללא קשר לרמה, הנתונים שלך תמיד מוצפנים במנוחה ובתנועה.';

  @override
  String get readOnlyScope => 'קריאה בלבד';

  @override
  String get fullAccessScope => 'גישה מלאה';

  @override
  String get readScope => 'קריאה';

  @override
  String get writeScope => 'כתיבה';

  @override
  String get apiKeyCreated => 'מפתח API נוצר!';

  @override
  String get saveKeyWarning => 'שמור מפתח זה עכשיו! לא תוכל לראות זאת שוב.';

  @override
  String get yourApiKey => 'המפתח API שלך';

  @override
  String get tapToCopy => 'לחץ כדי להעתיק';

  @override
  String get copyKey => 'העתק מפתח';

  @override
  String get createApiKey => 'צור מפתח API';

  @override
  String get accessDataProgrammatically => 'גשת לנתונים שלך בתוכנה';

  @override
  String get keyNameLabel => 'שם מפתח';

  @override
  String get keyNamePlaceholder => 'למשל, שילוב האפליקציה שלי';

  @override
  String get permissionsLabel => 'הרשאות';

  @override
  String get permissionsInfoNote => 'R = קריאה, W = כתיבה. ברירת המחדל היא קריאה בלבד אם לא נבחר דבר.';

  @override
  String get developerApi => 'API מפתח';

  @override
  String get createAKeyToGetStarted => 'צור מפתח כדי להתחיל';

  @override
  String errorWithMessage(String error) {
    return 'שגיאה: $error';
  }

  @override
  String get omiTraining => 'הדרכה של Omi';

  @override
  String get trainingDataProgram => 'תוכנית נתוני הדרכה';

  @override
  String get getOmiUnlimitedFree => 'קבל Omi Unlimited בחינם על ידי תרומת הנתונים שלך לאימון מודלי AI.';

  @override
  String get trainingDataBullets =>
      '• הנתונים שלך עוזרים לשפר את מודלי ה-AI\n• רק נתונים שאינם רגישים משותפים\n• תהליך שקוף לחלוטין';

  @override
  String get learnMoreAtOmiTraining => 'למד עוד בכתובת omi.me/training';

  @override
  String get agreeToContributeData => 'אני מבין ומסכים לתרום את הנתונים שלי לאימון AI';

  @override
  String get submitRequest => 'הגש בקשה';

  @override
  String get thankYouRequestUnderReview => 'תודה! הבקשה שלך נמצאת בבדיקה. אנחנו נודיע לך לאחר אישור.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'התוכנית שלך תישאר פעילה עד $date. לאחר מכן, תאבד גישה לתכונות הבלתי מוגבלות שלך. האם אתה בטוח?';
  }

  @override
  String get confirmCancellation => 'אשר ביטול';

  @override
  String get keepMyPlan => 'שמור את התוכנית שלי';

  @override
  String get subscriptionSetToCancel => 'המנוי שלך מוגדר לביטול בסוף התקופה.';

  @override
  String get switchedToOnDevice => 'עבר לתמלול על ההתקן';

  @override
  String get couldNotSwitchToFreePlan => 'לא ניתן לעבור לתוכנית חינם. אנא נסה שוב.';

  @override
  String get couldNotLoadPlans => 'לא ניתן לטעון תוכניות זמינות. אנא נסה שוב.';

  @override
  String get selectedPlanNotAvailable => 'התוכנית שנבחרה אינה זמינה. אנא נסה שוב.';

  @override
  String get upgradeToAnnualPlan => 'שדרוג לתוכנית שנתית';

  @override
  String get importantBillingInfo => 'מידע תשלום חשוב:';

  @override
  String get monthlyPlanContinues => 'תוכניתך החודשית הנוכחית תמשיך עד סוף תקופת החיוב שלך';

  @override
  String get paymentMethodCharged => 'שיטת התשלום הקיימת שלך תחויב באופן אוטומטי כאשר התוכנית החודשית שלך תסתיים';

  @override
  String get annualSubscriptionStarts => 'המנוי השנתי שלך ל-12 חודשים יתחיל באופן אוטומטי לאחר החיוב';

  @override
  String get thirteenMonthsCoverage => 'תקבל 13 חודשים של כיסוי בסך הכל (חודש נוכחי + 12 חודשים שנתיים)';

  @override
  String get confirmUpgrade => 'אשר שדרוג';

  @override
  String get confirmPlanChange => 'אשר שינוי תוכנית';

  @override
  String get confirmAndProceed => 'אשר והמשך';

  @override
  String get upgradeScheduled => 'שדרוג מתוכנן';

  @override
  String get changePlan => 'שנה תוכנית';

  @override
  String get upgradeAlreadyScheduled => 'השדרוג שלך לתוכנית שנתית כבר מתוכנן';

  @override
  String get youAreOnUnlimitedPlan => 'אתה ב-Unlimited Plan.';

  @override
  String get yourOmiUnleashed => 'ה-Omi שלך, משוחרר. עברו ללימיטציה עבור אפשרויות אינסופיות.';

  @override
  String planEndedOn(String date) {
    return 'התוכנית שלך הסתיימה ב-$date.\\nהירשם מחדש כעת - תחויב מיד לתקופת חיוב חדשה.';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'התוכנית שלך מוגדרת להיות מבוטלת ב-$date.\\nהירשם מחדש כעת כדי לשמור על ההטבות שלך - לא תחויב עד $date.';
  }

  @override
  String get annualPlanStartsAutomatically => 'התוכנית השנתית שלך תתחיל באופן אוטומטי כאשר התוכנית החודשית שלך תסתיים.';

  @override
  String planRenewsOn(String date) {
    return 'התוכנית שלך מתחדשת ב-$date.';
  }

  @override
  String get unlimitedConversations => 'שיחות בלתי מוגבלות';

  @override
  String get askOmiAnything => 'שאל את Omi כל דבר על חייך';

  @override
  String get unlockOmiInfiniteMemory => 'בטל את הנעילה של הזיכרון האינסופי של Omi';

  @override
  String get youreOnAnnualPlan => 'אתה ב-Annual Plan';

  @override
  String get alreadyBestValuePlan => 'כבר יש לך את התוכנית בעלת הערך הטוב ביותר. אין צורך בשינויים.';

  @override
  String get unableToLoadPlans => 'לא ניתן לטעון תוכניות';

  @override
  String get checkConnectionTryAgain => 'בדוק את החיבור ונסה שוב';

  @override
  String get useFreePlan => 'השתמש בתוכנית חינם';

  @override
  String get continueText => 'המשך';

  @override
  String get resubscribe => 'הירשם מחדש';

  @override
  String get couldNotOpenPaymentSettings => 'לא ניתן לפתוח הגדרות תשלום. אנא נסה שוב.';

  @override
  String get managePaymentMethod => 'נהל שיטת תשלום';

  @override
  String get cancelSubscription => 'בטל מנוי';

  @override
  String endsOnDate(String date) {
    return 'מסתיים ב-$date';
  }

  @override
  String get active => 'פעיל';

  @override
  String get freePlan => 'תוכנית חינם';

  @override
  String get configure => 'הגדר';

  @override
  String get privacyInformation => 'מידע פרטיות';

  @override
  String get yourPrivacyMattersToUs => 'הפרטיות שלך חשובה לנו';

  @override
  String get privacyIntroText =>
      'ב-Omi, אנחנו לוקחים את הפרטיות שלך ברצינות רבה. אנחנו רוצים להיות שקופים לגבי הנתונים שאנחנו אוספים וכיצד אנחנו משתמשים בהם כדי לשפר את המוצר שלך. הנה מה שאתה צריך לדעת:';

  @override
  String get whatWeTrack => 'מה אנחנו עוקבים';

  @override
  String get anonymityAndPrivacy => 'אנונימיות ופרטיות';

  @override
  String get optInAndOptOutOptions => 'אפשרויות הצטרפות והסרה';

  @override
  String get ourCommitment => 'ההתחייבות שלנו';

  @override
  String get commitmentText =>
      'אנחנו מחויבים להשתמש בנתונים שאנחנו אוספים רק כדי לעשות את Omi למוצר טוב יותר בשבילך. הפרטיות והאמון שלך הם חיוניים לנו.';

  @override
  String get thankYouText =>
      'תודה על היותך משתמש מוערך של Omi. אם יש לך שאלות או חששות, אתה מוזמן לפנות אלינו ל-team@basedhardware.com.';

  @override
  String get wifiSyncSettings => 'הגדרות סנכרון WiFi';

  @override
  String get enterHotspotCredentials => 'הזן את פרטי הנקודה הציבורית של הטלפון שלך';

  @override
  String get wifiSyncUsesHotspot =>
      'סנכרון WiFi משתמש בטלפון שלך כנקודה ציבורית. מצא את שם הנקודה הציבורית וסיסמה בהגדרות > Personal Hotspot.';

  @override
  String get hotspotNameSsid => 'שם הנקודה הציבורית (SSID)';

  @override
  String get exampleIphoneHotspot => 'למשל iPhone Hotspot';

  @override
  String get password => 'סיסמה';

  @override
  String get enterHotspotPassword => 'הזן סיסמה לנקודה ציבורית';

  @override
  String get saveCredentials => 'שמור פרטים';

  @override
  String get clearCredentials => 'נקה פרטים';

  @override
  String get pleaseEnterHotspotName => 'אנא הזן שם נקודה ציבורית';

  @override
  String get wifiCredentialsSaved => 'פרטי WiFi נשמרו';

  @override
  String get wifiCredentialsCleared => 'פרטי WiFi נוקו';

  @override
  String summaryGeneratedForDate(String date) {
    return 'סיכום שנוצר עבור $date';
  }

  @override
  String get failedToGenerateSummaryCheckConversations => 'נכשל בהפקת סיכום. ודא שיש לך שיחות ליום זה.';

  @override
  String get summaryNotFound => 'סיכום לא נמצא';

  @override
  String get yourDaysJourney => 'המסע של היום שלך';

  @override
  String get highlights => 'הדגשות';

  @override
  String get unresolvedQuestions => 'שאלות שלא נענו';

  @override
  String get decisions => 'החלטות';

  @override
  String get learnings => 'למידות';

  @override
  String get autoDeletesAfterThreeDays => 'מוחק באופן אוטומטי לאחר 3 ימים.';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'תרשים הידע נמחק בהצלחה';

  @override
  String get exportStartedMayTakeFewSeconds => 'ייצוא החל. זה עשוי לקחת כמה שניות...';

  @override
  String get knowledgeGraphDeleteDescription =>
      'זה יימחק את כל נתוני תרשים הידע הנגזרות (צמתים וחיבורים). הזכרונות המקוריים שלך יישארו בטוחים. התרשים יבנה מחדש לאורך זמן או בבקשה הבאה.';

  @override
  String get configureDailySummaryDigest => 'הגדר את עיכול פריטי הפעולה היומיים שלך';

  @override
  String accessesDataTypes(String dataTypes) {
    return 'גישה ל-$dataTypes';
  }

  @override
  String triggeredByType(String triggerType) {
    return 'הופעל על ידי $triggerType';
  }

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription ו-is $triggerDescription.';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return 'Is $triggerDescription.';
  }

  @override
  String get noSpecificDataAccessConfigured => 'אין גישת נתונים ספציפית מוגדרת.';

  @override
  String get basicPlanDescription => '1,200 דקות פרימיום + בלתי מוגבל במכשיר';

  @override
  String get minutes => 'דקות';

  @override
  String get omiHas => 'ל-Omi יש:';

  @override
  String get premiumMinutesUsed => 'דקות פרימיום שבהן נעשה שימוש.';

  @override
  String get setupOnDevice => 'הגדר במכשיר';

  @override
  String get forUnlimitedFreeTranscription => 'לתמלול חינם בלתי מוגבל.';

  @override
  String premiumMinsLeft(int count) {
    return '$count דקות פרימיום נותרו.';
  }

  @override
  String get alwaysAvailable => 'תמיד זמין.';

  @override
  String get importHistory => 'היסטוריית ייבוא';

  @override
  String get noImportsYet => 'אין ייבואים עדיין';

  @override
  String get selectZipFileToImport => 'בחר את קובץ .zip לייבוא!';

  @override
  String get otherDevicesComingSoon => 'מכשירים אחרים בקרוב';

  @override
  String get deleteAllLimitlessConversations => 'מחק את כל שיחות Limitless?';

  @override
  String get deleteAllLimitlessWarning => 'זה ימחק לצמיתות את כל השיחות שיובאו מ-Limitless. לא ניתן לבטל פעולה זו.';

  @override
  String deletedLimitlessConversations(int count) {
    return 'מחק $count שיחות Limitless';
  }

  @override
  String get failedToDeleteConversations => 'נכשל במחיקת שיחות';

  @override
  String get deleteImportedData => 'מחק נתונים מיובאים';

  @override
  String get statusPending => 'בתהליך';

  @override
  String get statusProcessing => 'בעיבוד';

  @override
  String get statusCompleted => 'הושלם';

  @override
  String get statusFailed => 'נכשל';

  @override
  String nConversations(int count) {
    return '$count שיחות';
  }

  @override
  String get pleaseEnterName => 'אנא הזן שם';

  @override
  String get nameMustBeBetweenCharacters => 'השם חייב להיות בין 2 ל-40 תווים';

  @override
  String get deleteSampleQuestion => 'מחק דוגמה?';

  @override
  String deleteSampleConfirmation(String name) {
    return 'האם אתה בטוח שברצונך למחוק את הדוגמה של $name?';
  }

  @override
  String get confirmDeletion => 'אשר מחיקה';

  @override
  String deletePersonConfirmation(String name) {
    return 'האם אתה בטוח שברצונך למחוק את $name? זה גם יסיר את כל דגימות הדיבור הקשורות.';
  }

  @override
  String get howItWorksTitle => 'איך זה עובד?';

  @override
  String get howPeopleWorks =>
      'ברגע שנוצרת אדם, אתה יכול ללכת לתמלול שיחה, ולהקצות להם את הקטעים המתאימים שלהם, בדרך זו Omi יוכל גם לזהות את הדיבור שלהם!';

  @override
  String get tapToDelete => 'הקש כדי למחוק';

  @override
  String get newTag => 'חדש';

  @override
  String get needHelpChatWithUs => 'צריך עזרה? שוחח איתנו';

  @override
  String get localStorageEnabled => 'אחסון מקומי מופעל';

  @override
  String get localStorageDisabled => 'אחסון מקומי מבוטל';

  @override
  String failedToUpdateSettings(String error) {
    return 'נכשל בעדכון הגדרות: $error';
  }

  @override
  String get privacyNotice => 'הודעת פרטיות';

  @override
  String get recordingsMayCaptureOthers =>
      'הקלטות עשויות ללכוד קולות של אחרים. ודא שיש לך הסכמה מכל המשתתפים לפני הפעלה.';

  @override
  String get enable => 'הפעל';

  @override
  String get storeAudioOnPhone => 'אחסן אודיו בטלפון';

  @override
  String get on => 'פעיל';

  @override
  String get storeAudioDescription =>
      'שמור את כל הקלטות האודיו באופן מקומי בטלפון שלך. כאשר מבוטל, רק ההעלאות שנכשלו נשמרות כדי לחסוך מקום אחסון.';

  @override
  String get enableLocalStorage => 'הפעל אחסון מקומי';

  @override
  String get cloudStorageEnabled => 'אחסון ענן מופעל';

  @override
  String get cloudStorageDisabled => 'אחסון ענן מבוטל';

  @override
  String get enableCloudStorage => 'הפעל אחסון ענן';

  @override
  String get storeAudioOnCloud => 'אחסן אודיו בענן';

  @override
  String get cloudStorageDialogMessage => 'הקלטות ההזמנה שלך תאוחסנה בפרטי אחסון ענן כפי שאתה מדבר.';

  @override
  String get storeAudioCloudDescription =>
      'אחסן את הקלטות ההזמנה שלך באחסון ענן פרטי כפי שאתה מדבר. אודיו נתפס ונשמר בבטחה בזמן אמת.';

  @override
  String get downloadingFirmware => 'הורדת Firmware';

  @override
  String get installingFirmware => 'התקנת Firmware';

  @override
  String get firmwareUpdateWarning => 'אל תסגור את האפליקציה או תכבה את המכשיר. זה עלול לפגוע במכשיר שלך.';

  @override
  String get firmwareUpdated => 'Firmware עודכן';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'אנא הפעל מחדש את $deviceName כדי להשלים את העדכון.';
  }

  @override
  String get yourDeviceIsUpToDate => 'המכשיר שלך עדכני';

  @override
  String get currentVersion => 'גרסה נוכחית';

  @override
  String get latestVersion => 'גרסה חדישה ביותר';

  @override
  String get whatsNew => 'מה חדש';

  @override
  String get installUpdate => 'התקן עדכון';

  @override
  String get updateNow => 'עדכן עכשיו';

  @override
  String get updateGuide => 'מדריך עדכון';

  @override
  String get checkingForUpdates => 'בדוק עדכונים';

  @override
  String get checkingFirmwareVersion => 'בדוק גרסת firmware...';

  @override
  String get firmwareUpdate => 'עדכון Firmware';

  @override
  String get payments => 'תשלומים';

  @override
  String get connectPaymentMethodInfo => 'חבר שיטת תשלום למטה כדי להתחיל לקבל כסף לאפליקציות שלך.';

  @override
  String get selectedPaymentMethod => 'שיטת תשלום שנבחרה';

  @override
  String get availablePaymentMethods => 'שיטות תשלום זמינות';

  @override
  String get activeStatus => 'פעיל';

  @override
  String get connectedStatus => 'מחובר';

  @override
  String get notConnectedStatus => 'לא מחובר';

  @override
  String get setActive => 'הגדר כפעיל';

  @override
  String get getPaidThroughStripe => 'קבל כסף עבור מכירות האפליקציה שלך דרך Stripe';

  @override
  String get monthlyPayouts => 'תשלומים חודשיים';

  @override
  String get monthlyPayoutsDescription => 'קבל תשלומים חודשיים ישירות לחשבון שלך כאשר תגיע ל-\$10 בהכנסות';

  @override
  String get secureAndReliable => 'בטוח ואמין';

  @override
  String get stripeSecureDescription => 'Stripe מבטיח העברות בטוחות וזמניות של הכנסות האפליקציה שלך';

  @override
  String get selectYourCountry => 'בחר את המדינה שלך';

  @override
  String get countrySelectionPermanent => 'בחירת המדינה שלך היא קבועה ולא ניתן לשנות אותה מאוחר יותר.';

  @override
  String get byClickingConnectNow => 'על ידי לחיצה על \"Connect Now\" אתה מסכים ל-';

  @override
  String get stripeConnectedAccountAgreement => 'הסכם Stripe Connected Account';

  @override
  String get errorConnectingToStripe => 'שגיאה בחיבור ל-Stripe! אנא נסה שוב מאוחר יותר.';

  @override
  String get connectingYourStripeAccount => 'חיבור חשבון Stripe שלך';

  @override
  String get stripeOnboardingInstructions =>
      'אנא השלם את תהליך ההתרשמות של Stripe בדפדפן שלך. דף זה יתעדכן באופן אוטומטי לאחר השלמתו.';

  @override
  String get failedTryAgain => 'נכשל? נסה שוב';

  @override
  String get illDoItLater => 'אעשה זאת מאוחר יותר';

  @override
  String get successfullyConnected => 'מחובר בהצלחה!';

  @override
  String get stripeReadyForPayments =>
      'חשבון Stripe שלך מוכן כעת לקבל תשלומים. אתה יכול להתחיל להרוויח מכל מכירות האפליקציה שלך מיד.';

  @override
  String get updateStripeDetails => 'עדכן פרטי Stripe';

  @override
  String get errorUpdatingStripeDetails => 'שגיאה בעדכון פרטי Stripe! אנא נסה שוב מאוחר יותר.';

  @override
  String get updatePayPal => 'עדכן PayPal';

  @override
  String get setUpPayPal => 'הגדר PayPal';

  @override
  String get updatePayPalAccountDetails => 'עדכן את פרטי חשבון PayPal שלך';

  @override
  String get connectPayPalToReceivePayments => 'חבר את חשבון PayPal שלך כדי להתחיל לקבל תשלומים עבור האפליקציות שלך';

  @override
  String get paypalEmail => 'אימייל PayPal';

  @override
  String get paypalMeLink => 'קישור PayPal.me';

  @override
  String get stripeRecommendation => 'אם Stripe זמין במדינתך, אנחנו ממליצים בחום להשתמש בו לתשלומים מהירים וקלים יותר.';

  @override
  String get updatePayPalDetails => 'עדכן פרטי PayPal';

  @override
  String get savePayPalDetails => 'שמור פרטי PayPal';

  @override
  String get pleaseEnterPayPalEmail => 'אנא הזן את אימייל PayPal שלך';

  @override
  String get pleaseEnterPayPalMeLink => 'אנא הזן את קישור PayPal.me שלך';

  @override
  String get doNotIncludeHttpInLink => 'אל תכלול http או https או www בקישור';

  @override
  String get pleaseEnterValidPayPalMeLink => 'אנא הזן קישור PayPal.me תקין';

  @override
  String get pleaseEnterValidEmail => 'אנא הזן כתובת דואר אלקטרוני תקינה';

  @override
  String get syncingYourRecordings => 'סנכרון ההקלטות שלך';

  @override
  String get syncYourRecordings => 'סנכרן את ההקלטות שלך';

  @override
  String get syncNow => 'סנכרן עכשיו';

  @override
  String get error => 'שגיאה';

  @override
  String get speechSamples => 'דגימות דיבור';

  @override
  String additionalSampleIndex(String index) {
    return 'דוגמה נוספת $index';
  }

  @override
  String durationSeconds(String seconds) {
    return 'משך: $seconds שניות';
  }

  @override
  String get additionalSpeechSampleRemoved => 'דוגמה דיבור נוספת הוסרה';

  @override
  String get consentDataMessage =>
      'בהמשך, השיחות, ההקלטות והמידע האישי שלך יאוחסנו בצורה מאובטחת בשרתים שלנו. הקלטות האודיו והתמלולים שלך מעובדים על ידי שירותי AI של צד שלישי (כולל Deepgram לתמלול ו-OpenAI לניתוח) כדי לספק לך תובנות מבוססות AI ולאפשר את כל תכונות האפליקציה.';

  @override
  String get tasksEmptyStateMessage => 'משימות משיחותיך יופיעו כאן.\\nלחץ + כדי ליצור אחת ידנית.';

  @override
  String get clearChatAction => 'נקה שיחה';

  @override
  String get enableApps => 'הפעל אפליקציות';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => 'הצג עוד ↓';

  @override
  String get showLess => 'הצג פחות ↑';

  @override
  String get loadingYourRecording => 'טוען את ההקלטה שלך...';

  @override
  String get photoDiscardedMessage => 'התמונה זו הושלכה מכיוון שלא הייתה משמעותית.';

  @override
  String get analyzing => 'בנתוח...';

  @override
  String get searchCountries => 'חפש מדינות';

  @override
  String get checkingAppleWatch => 'בדוק Apple Watch...';

  @override
  String get installOmiOnAppleWatch => 'התקן Omi ב-\\nApple Watch';

  @override
  String get installOmiOnAppleWatchDescription =>
      'כדי להשתמש ב-Apple Watch שלך עם Omi, תחילה עליך להתקין את אפליקציית Omi בשעון שלך.';

  @override
  String get openOmiOnAppleWatch => 'פתח Omi ב-\\nApple Watch';

  @override
  String get openOmiOnAppleWatchDescription =>
      'אפליקציית Omi מותקנת ב-Apple Watch שלך. פתח אותה והקש Start כדי להתחיל.';

  @override
  String get openWatchApp => 'פתח אפליקציית Watch';

  @override
  String get iveInstalledAndOpenedTheApp => 'התקנתי ופתחתי את האפליקציה';

  @override
  String get unableToOpenWatchApp =>
      'לא ניתן לפתוח אפליקציית Apple Watch. אנא פתח ידנית את אפליקציית Watch בשעון Apple Watch שלך והתקן את Omi מסעיף \"Available Apps\".';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch מחובר בהצלחה!';

  @override
  String get appleWatchNotReachable => 'Apple Watch עדיין לא זמין. אנא ודא שאפליקציית Omi פתוחה בשעון שלך.';

  @override
  String errorCheckingConnection(String error) {
    return 'שגיאה בבדיקת החיבור: $error';
  }

  @override
  String get muted => 'מושתק';

  @override
  String get processNow => 'עבד עכשיו';

  @override
  String get finishedConversation => 'סיימת שיחה?';

  @override
  String get stopRecordingConfirmation => 'האם אתה בטוח שברצונך להפסיק את ההקלטה ולסכם את השיחה כעת?';

  @override
  String get conversationEndsManually => 'שיחה תסתיים רק ידנית.';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'השיחה מסוכמת לאחר $minutes דקה$suffix ללא דיבור.';
  }

  @override
  String get dontAskAgain => 'אל תשאל אותי שוב';

  @override
  String get waitingForTranscriptOrPhotos => 'ממתין לתמלול או תמונות...';

  @override
  String get noSummaryYet => 'אין סיכום עדיין';

  @override
  String hints(String text) {
    return 'רמזים: $text';
  }

  @override
  String get testConversationPrompt => 'בדוק הנושא שיחה';

  @override
  String get prompt => 'הנושא';

  @override
  String get result => 'תוצאה:';

  @override
  String get compareTranscripts => 'השווה תמלולים';

  @override
  String get notHelpful => 'לא עוזר';

  @override
  String get exportTasksWithOneTap => 'ייצא משימות בלחיצה אחת!';

  @override
  String get inProgress => 'בתהליך';

  @override
  String get photos => 'תמונות';

  @override
  String get rawData => 'נתונים גולמיים';

  @override
  String get content => 'תוכן';

  @override
  String get noContentToDisplay => 'אין תוכן להצגה';

  @override
  String get noSummary => 'אין סיכום';

  @override
  String get updateOmiFirmware => 'עדכן firmware של omi';

  @override
  String get anErrorOccurredTryAgain => 'ארעה שגיאה. אנא נסה שוב.';

  @override
  String get welcomeBackSimple => 'ברוך השוב';

  @override
  String get addVocabularyDescription => 'הוסף מילים שOmi צריך לזהות במהלך תמלול.';

  @override
  String get enterWordsCommaSeparated => 'הזן מילים (מופרדות בפסיקים)';

  @override
  String get whenToReceiveDailySummary => 'מתי לקבל את הסיכום היומי שלך';

  @override
  String get checkingNextSevenDays => 'בדוק את 7 הימים הבאים';

  @override
  String failedToDeleteError(String error) {
    return 'נכשל במחיקה: $error';
  }

  @override
  String get developerApiKeys => 'מפתחות API של מפתח';

  @override
  String get noApiKeysCreateOne => 'אין מפתחות API. צור אחד כדי להתחיל.';

  @override
  String get commandRequired => '⌘ נדרש';

  @override
  String get spaceKey => 'Space';

  @override
  String loadMoreRemaining(String count) {
    return 'טען עוד ($count נותרו)';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'משתמש $percentile% עליון';
  }

  @override
  String get wrappedMinutes => 'דקות';

  @override
  String get wrappedConversations => 'שיחות';

  @override
  String get wrappedDaysActive => 'ימים פעילים';

  @override
  String get wrappedYouTalkedAbout => 'דברת על';

  @override
  String get wrappedActionItems => 'פריטי פעולה';

  @override
  String get wrappedTasksCreated => 'משימות שנוצרו';

  @override
  String get wrappedCompleted => 'הושלם';

  @override
  String wrappedCompletionRate(String rate) {
    return 'שיעור השלמה $rate%';
  }

  @override
  String get wrappedYourTopDays => 'הימים המובילים שלך';

  @override
  String get wrappedBestMoments => 'הרגעים הטובים ביותר';

  @override
  String get wrappedMyBuddies => 'החברים שלי';

  @override
  String get wrappedCouldntStopTalkingAbout => 'לא יכולתי להפסיק לדבר על';

  @override
  String get wrappedShow => 'תוכנית';

  @override
  String get wrappedMovie => 'סרט';

  @override
  String get wrappedBook => 'ספר';

  @override
  String get wrappedCelebrity => 'סלבריטי';

  @override
  String get wrappedFood => 'אוכל';

  @override
  String get wrappedMovieRecs => 'המלצות סרטים לחברים';

  @override
  String get wrappedBiggest => 'הגדול ביותר';

  @override
  String get wrappedStruggle => 'מאבק';

  @override
  String get wrappedButYouPushedThrough => 'אבל דחפת דרך 💪';

  @override
  String get wrappedWin => 'ניצחון';

  @override
  String get wrappedYouDidIt => 'עשיתם זאת! 🎉';

  @override
  String get wrappedTopPhrases => '5 ביטויים עליונים';

  @override
  String get wrappedMins => 'דקות';

  @override
  String get wrappedConvos => 'שיחות';

  @override
  String get wrappedDays => 'ימים';

  @override
  String get wrappedMyBuddiesLabel => 'החברים שלי';

  @override
  String get wrappedObsessionsLabel => 'אובססיות';

  @override
  String get wrappedStruggleLabel => 'מאבק';

  @override
  String get wrappedWinLabel => 'ניצחון';

  @override
  String get wrappedTopPhrasesLabel => '5 ביטויים עליונים';

  @override
  String get wrappedLetsHitRewind => 'בואו נחזור אחורה ל-';

  @override
  String get wrappedGenerateMyWrapped => 'צור את ה-Wrapped שלי';

  @override
  String get wrappedProcessingDefault => 'בעיבוד...';

  @override
  String get wrappedCreatingYourStory => 'יצירת הסיפור שלך\\n2025...';

  @override
  String get wrappedSomethingWentWrong => 'משהו\\nהלך לא בסדר';

  @override
  String get wrappedAnErrorOccurred => 'ארעה שגיאה';

  @override
  String get wrappedTryAgain => 'נסה שוב';

  @override
  String get wrappedNoDataAvailable => 'אין נתונים זמינים';

  @override
  String get wrappedOmiLifeRecap => 'סיכום החיים של Omi';

  @override
  String get wrappedSwipeUpToBegin => 'החלק למעלה כדי להתחיל';

  @override
  String get wrappedShareText => 'ה-2025 שלי, זכור על ידי Omi ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare => 'נכשל בשיתוף. אנא נסה שוב.';

  @override
  String get wrappedFailedToStartGeneration => 'נכשל בהתחלת דור. אנא נסה שוב.';

  @override
  String get wrappedStarting => 'התחלה...';

  @override
  String get wrappedShare => 'שתף';

  @override
  String get wrappedShareYourWrapped => 'שתף את ה-Wrapped שלך';

  @override
  String get wrappedMy2025 => 'ה-2025 שלי';

  @override
  String get wrappedRememberedByOmi => 'זכור על ידי Omi';

  @override
  String get wrappedMostFunDay => 'הכי כיף';

  @override
  String get wrappedMostProductiveDay => 'הכי פרודוקטיבי';

  @override
  String get wrappedMostIntenseDay => 'הכי עוצמתי';

  @override
  String get wrappedFunniestMoment => 'הצחוק ביותר';

  @override
  String get wrappedMostCringeMoment => 'הכי מביך';

  @override
  String get wrappedMinutesLabel => 'דקות';

  @override
  String get wrappedConversationsLabel => 'שיחות';

  @override
  String get wrappedDaysActiveLabel => 'ימים פעילים';

  @override
  String get wrappedTasksGenerated => 'משימות שנוצרו';

  @override
  String get wrappedTasksCompleted => 'משימות שהשלמת';

  @override
  String get wrappedTopFivePhrases => '5 ביטויים עליונים';

  @override
  String get wrappedAGreatDay => 'יום מדהים';

  @override
  String get wrappedGettingItDone => 'סיום זה';

  @override
  String get wrappedAChallenge => 'אתגר';

  @override
  String get wrappedAHilariousMoment => 'רגע מצחיק';

  @override
  String get wrappedThatAwkwardMoment => 'הרגע המביך הזה';

  @override
  String get wrappedYouHadFunnyMoments => 'היו לך כמה רגעים צחוקים השנה!';

  @override
  String get wrappedWeveAllBeenThere => 'כולנו היינו שם!';

  @override
  String get wrappedFriend => 'חבר';

  @override
  String get wrappedYourBuddy => 'החבר שלך!';

  @override
  String get wrappedNotMentioned => 'לא הוזכר';

  @override
  String get wrappedTheHardPart => 'החלק הקשה';

  @override
  String get wrappedPersonalGrowth => 'גדילה אישית';

  @override
  String get wrappedFunDay => 'כיף';

  @override
  String get wrappedProductiveDay => 'פרודוקטיבי';

  @override
  String get wrappedIntenseDay => 'עוצמתי';

  @override
  String get wrappedFunnyMomentTitle => 'רגע מצחיק';

  @override
  String get wrappedCringeMomentTitle => 'רגע מביך';

  @override
  String get wrappedYouTalkedAboutBadge => 'דברת על';

  @override
  String get wrappedCompletedLabel => 'הושלם';

  @override
  String get wrappedMyBuddiesCard => 'החברים שלי';

  @override
  String get wrappedBuddiesLabel => 'חברים';

  @override
  String get wrappedObsessionsLabelUpper => 'אובססיות';

  @override
  String get wrappedStruggleLabelUpper => 'מאבק';

  @override
  String get wrappedWinLabelUpper => 'ניצחון';

  @override
  String get wrappedTopPhrasesLabelUpper => '5 ביטויים עליונים';

  @override
  String get wrappedYourHeader => 'שלך';

  @override
  String get wrappedTopDaysHeader => 'הימים המובילים';

  @override
  String get wrappedYourTopDaysBadge => 'הימים המובילים שלך';

  @override
  String get wrappedBestHeader => 'הטוב ביותר';

  @override
  String get wrappedMomentsHeader => 'רגעים';

  @override
  String get wrappedBestMomentsBadge => 'הרגעים הטובים ביותר';

  @override
  String get wrappedBiggestHeader => 'הגדול ביותר';

  @override
  String get wrappedStruggleHeader => 'מאבק';

  @override
  String get wrappedWinHeader => 'ניצחון';

  @override
  String get wrappedButYouPushedThroughEmoji => 'אבל דחפת דרך 💪';

  @override
  String get wrappedYouDidItEmoji => 'עשיתם זאת! 🎉';

  @override
  String get wrappedHours => 'שעות';

  @override
  String get wrappedActions => 'פעולות';

  @override
  String get multipleSpeakersDetected => 'זוהו דוברים מרובים';

  @override
  String get multipleSpeakersDescription => 'נראה שיש מדברים מרובים בהקלטה. אנא ודא שאתה במקום שקט ונסה שוב.';

  @override
  String get invalidRecordingDetected => 'זוהתה הקלטה לא חוקית';

  @override
  String get notEnoughSpeechDescription => 'אין מספיק דיבור שזוהה. אנא דבר יותר ונסה שוב.';

  @override
  String get speechDurationDescription => 'אנא וודא שאתה מדבר לפחות 5 שניות ולא יותר מ-90.';

  @override
  String get connectionLostDescription => 'החיבור הופרע. אנא בדוק את חיבור האינטרנט שלך ונסה שוב.';

  @override
  String get howToTakeGoodSample => 'איך לקחת דגימה טובה?';

  @override
  String get goodSampleInstructions =>
      '1. וודא שאתה במקום שקט.\n2. דבר בבירור ובטבעיות.\n3. וודא שהמכשיר שלך נמצא במצבו הטבעי, על הצוואר שלך.\n\nלאחר יצירתה, תוכל תמיד לשפר אותה או לעשות אותה שוב.';

  @override
  String get noDeviceConnectedUseMic => 'אין מכשיר מחובר. יהיה שימוש במיקרופון הטלפון.';

  @override
  String get doItAgain => 'בצע זאת שוב';

  @override
  String get listenToSpeechProfile => 'הקשב לפרופיל הדיבור שלי ➡️';

  @override
  String get recognizingOthers => 'זיהוי אחרים 👀';

  @override
  String get keepGoingGreat => 'המשך, אתה עושה מצוין';

  @override
  String get somethingWentWrongTryAgain => 'משהו השתבש! אנא נסה שוב מאוחר יותר.';

  @override
  String get uploadingVoiceProfile => 'העלאת פרופיל הקול שלך...';

  @override
  String get memorizingYourVoice => 'שינון הקול שלך...';

  @override
  String get personalizingExperience => 'התאמה אישית של החוויה שלך...';

  @override
  String get keepSpeakingUntil100 => 'המשך לדבור עד שתגיע ל-100%.';

  @override
  String get greatJobAlmostThere => 'עבודה נהדרת, כמעט שם';

  @override
  String get soCloseJustLittleMore => 'כל כך קרוב, רק קצת עוד';

  @override
  String get notificationFrequency => 'תדירות הודעות';

  @override
  String get controlNotificationFrequency => 'שלוט בתדירות של הודעות Omi פרואקטיביות שלך.';

  @override
  String get yourScore => 'הניקוד שלך';

  @override
  String get dailyScoreBreakdown => 'פירוט הניקוד היומי';

  @override
  String get todaysScore => 'הניקוד של היום';

  @override
  String get tasksCompleted => 'משימות שהושלמו';

  @override
  String get completionRate => 'שיעור השלמה';

  @override
  String get howItWorks => 'איך זה עובד';

  @override
  String get dailyScoreExplanation =>
      'הניקוד היומי שלך מבוסס על השלמת משימות. השלם את המשימות שלך כדי לשפר את הניקוד שלך!';

  @override
  String get notificationFrequencyDescription => 'שלוט בתדירות של הודעות ותזכורות פרואקטיביות של Omi.';

  @override
  String get sliderOff => 'כבוי';

  @override
  String get sliderMax => 'מקסימום';

  @override
  String summaryGeneratedFor(String date) {
    return 'סיכום שנוצר עבור $date';
  }

  @override
  String get failedToGenerateSummary => 'איתור ישן. ודא שיש לך שיחות לאותו יום.';

  @override
  String get recap => 'סיכום';

  @override
  String deleteQuoted(String name) {
    return 'מחק \"$name\"';
  }

  @override
  String moveConversationsTo(int count) {
    return 'העבר $count שיחות ל:';
  }

  @override
  String get noFolder => 'ללא תיקייה';

  @override
  String get removeFromAllFolders => 'הסר מכל התיקיות';

  @override
  String get buildAndShareYourCustomApp => 'בנה ושתף את האפליקציה המותאמת שלך';

  @override
  String get searchAppsPlaceholder => 'חפש 1500+ אפליקציות';

  @override
  String get filters => 'סינונים';

  @override
  String get frequencyOff => 'כבוי';

  @override
  String get frequencyMinimal => 'מינימלי';

  @override
  String get frequencyLow => 'נמוך';

  @override
  String get frequencyBalanced => 'מאוזן';

  @override
  String get frequencyHigh => 'גבוה';

  @override
  String get frequencyMaximum => 'מקסימום';

  @override
  String get frequencyDescOff => 'אין הודעות פרואקטיביות';

  @override
  String get frequencyDescMinimal => 'רק תזכורות קריטיות';

  @override
  String get frequencyDescLow => 'עדכונים חשובים בלבד';

  @override
  String get frequencyDescBalanced => 'דחיפות מועילות רגילות';

  @override
  String get frequencyDescHigh => 'בדיקות תדירות תכופות';

  @override
  String get frequencyDescMaximum => 'היה מעורה כל הזמן';

  @override
  String get clearChatQuestion => 'נקה צ\'אט?';

  @override
  String get syncingMessages => 'סנכרון הודעות עם השרת...';

  @override
  String get chatAppsTitle => 'אפליקציות צ\'אט';

  @override
  String get selectApp => 'בחר אפליקציה';

  @override
  String get noChatAppsEnabled => 'אין אפליקציות צ\'אט מופעלות.\nהקש \"הפעל אפליקציות\" כדי להוסיף חלקן.';

  @override
  String get disable => 'בטל';

  @override
  String get photoLibrary => 'ספריית תמונות';

  @override
  String get chooseFile => 'בחר קובץ';

  @override
  String get connectAiAssistantsToYourData => 'חבר עוזרי AI לנתונים שלך';

  @override
  String get oAuth => 'OAuth';

  @override
  String get trackYourGoalsOnHomepage => 'עקוב אחר היעדים האישיים שלך בעמוד הבית';

  @override
  String get deleteRecording => 'מחק הקלטה';

  @override
  String get thisCannotBeUndone => 'לא ניתן לבטל זאת.';

  @override
  String get sdCard => 'כרטיס SD';

  @override
  String get fromSd => 'מ-SD';

  @override
  String get limitless => 'Limitless';

  @override
  String get fastTransfer => 'העברה מהירה';

  @override
  String get syncingStatus => 'סנכרון';

  @override
  String get failedStatus => 'נכשל';

  @override
  String etaLabel(String time) {
    return 'ETA: $time';
  }

  @override
  String get transferMethod => 'שיטת העברה';

  @override
  String get fast => 'מהיר';

  @override
  String get ble => 'BLE';

  @override
  String get phone => 'טלפון';

  @override
  String get cancelSync => 'ביטול סנכרון';

  @override
  String get cancelSyncMessage => 'נתונים שהורדו כבר יישמרו. אתה יכול להמשיך מאוחר יותר.';

  @override
  String get syncCancelled => 'סנכרון בוטל';

  @override
  String get deleteProcessedFiles => 'מחק קבצים שעובדו';

  @override
  String get processedFilesDeleted => 'קבצים שעובדו נמחקו';

  @override
  String get wifiEnableFailed => 'איתור בהפעלת WiFi במכשיר. אנא נסה שוב.';

  @override
  String get deviceNoFastTransfer => 'המכשיר שלך אינו תומך בהעברה מהירה. השתמש ב-Bluetooth במקום זאת.';

  @override
  String get enableHotspotMessage => 'אנא הפעל את נקודת החום של הטלפון שלך ונסה שוב.';

  @override
  String get transferStartFailed => 'איתור בהתחלת ההעברה. אנא נסה שוב.';

  @override
  String get deviceNotResponding => 'המכשיר לא הגיב. אנא נסה שוב.';

  @override
  String get invalidWifiCredentials => 'אישורי WiFi לא תקפים. בדוק את הגדרות נקודת החום שלך.';

  @override
  String get wifiConnectionFailed => 'חיבור WiFi נכשל. אנא נסה שוב.';

  @override
  String get sdCardProcessing => 'עיבוד כרטיס SD';

  @override
  String sdCardProcessingMessage(int count) {
    return 'עיבוד $count הקלטה(ות). קבצים יוסרו מכרטיס SD לאחר מכן.';
  }

  @override
  String get process => 'עיבוד';

  @override
  String get wifiSyncFailed => 'סנכרון WiFi נכשל';

  @override
  String get processingFailed => 'עיבוד נכשל';

  @override
  String get downloadingFromSdCard => 'הורדה מכרטיס SD';

  @override
  String processingProgress(int current, int total) {
    return 'עיבוד $current/$total';
  }

  @override
  String conversationsCreated(int count) {
    return '$count שיחות שנוצרו';
  }

  @override
  String get internetRequired => 'נדרש אינטרנט';

  @override
  String get processAudio => 'עיבוד אודיו';

  @override
  String get start => 'התחל';

  @override
  String get noRecordings => 'אין הקלטות';

  @override
  String get audioFromOmiWillAppearHere => 'אודיו מהמכשיר Omi שלך יופיע כאן';

  @override
  String get deleteProcessed => 'מחק שעובד';

  @override
  String get tryDifferentFilter => 'נסה סינון אחר';

  @override
  String get recordings => 'הקלטות';

  @override
  String get enableRemindersAccess => 'אנא הפעל גישה לתזכורות בהגדרות כדי להשתמש בתזכורות Apple';

  @override
  String todayAtTime(String time) {
    return 'היום ב-$time';
  }

  @override
  String yesterdayAtTime(String time) {
    return 'אתמול ב-$time';
  }

  @override
  String get lessThanAMinute => 'פחות מדקה';

  @override
  String estimatedMinutes(int count) {
    return '~$count דקה(ות)';
  }

  @override
  String estimatedHours(int count) {
    return '~$count שעה(ות)';
  }

  @override
  String estimatedTimeRemaining(String time) {
    return 'משוער: $time נותר';
  }

  @override
  String get summarizingConversation => 'סיכום השיחה...\nזה אולי יקח כמה שניות';

  @override
  String get resummarizingConversation => 'סיכום מחדש של השיחה...\nזה אולי יקח כמה שניות';

  @override
  String get nothingInterestingRetry => 'לא נמצא כלום מעניין,\nרוצה לנסות שוב?';

  @override
  String get noSummaryForConversation => 'אין סיכום זמין\nעבור שיחה זו.';

  @override
  String get unknownLocation => 'מיקום לא ידוע';

  @override
  String get couldNotLoadMap => 'לא הצליח לטעון מפה';

  @override
  String get triggerConversationIntegration => 'הפעל שיחה שנוצרה אינטגרציה';

  @override
  String get webhookUrlNotSet => 'כתובת URL של Webhook לא הוגדרה';

  @override
  String get setWebhookUrlInSettings => 'אנא הגדר את כתובת ה-Webhook בהגדרות המפתח כדי להשתמש בתכונה זו.';

  @override
  String get sendWebUrl => 'שלח כתובת אינטרנט';

  @override
  String get sendTranscript => 'שלח תמלול';

  @override
  String get sendSummary => 'שלח סיכום';

  @override
  String get debugModeDetected => 'זוהה מצב ניפוי בעיות';

  @override
  String get performanceReduced => 'ביצועים מופחתים פי 5-10. השתמש במצב Release.';

  @override
  String autoClosingInSeconds(int seconds) {
    return 'סגירה אוטומטית ב-${seconds}s';
  }

  @override
  String get modelRequired => 'דגם נדרש';

  @override
  String get downloadWhisperModel => 'אנא הורד דגם Whisper לפני שמירה.';

  @override
  String get deviceNotCompatible => 'המכשיר לא תואם';

  @override
  String get deviceRequirements => 'המכשיר שלך אינו עומד בדרישות עבור תמלול On-Device.';

  @override
  String get willLikelyCrash => 'הפעלת זה כנראה תגרום לאפליקציה להתרסק או להקפיא.';

  @override
  String get transcriptionSlowerLessAccurate => 'התמלול יהיה הרבה יותר איטי ופחות מדויק.';

  @override
  String get proceedAnyway => 'המשך בכל זאת';

  @override
  String get olderDeviceDetected => 'זוהה מכשיר ישן';

  @override
  String get onDeviceSlower => 'תמלול On-device אולי יהיה איטי יותר במכשיר זה.';

  @override
  String get batteryUsageHigher => 'צריכת הסוללה תהיה גבוהה יותר מתמלול ענן.';

  @override
  String get considerOmiCloud => 'שקול להשתמש ב-Omi Cloud לביצועים טובים יותר.';

  @override
  String get highResourceUsage => 'שימוש משאבים גבוה';

  @override
  String get onDeviceIntensive => 'תמלול On-Device הוא עתיר חישובים.';

  @override
  String get batteryDrainIncrease => 'זליגת הסוללה תגדל משמעותית.';

  @override
  String get deviceMayWarmUp => 'המכשיר אולי יתחמם בשימוש מורחב.';

  @override
  String get speedAccuracyLower => 'המהירות והדיוק אולי יהיו נמוכים יותר מדגמים Cloud.';

  @override
  String get cloudProvider => 'ספק ענן';

  @override
  String get premiumMinutesInfo => '1,200 דקות פרמיום/חודש. כרטיסייה On-Device מציעה תמלול בחינם ללא הגבלה.';

  @override
  String get viewUsage => 'הצג שימוש';

  @override
  String get localProcessingInfo => 'אודיו מעובד מקומית. עובד במצב לא מקוון, פרטי יותר, אך משתמש בסוללה יותר.';

  @override
  String get model => 'דגם';

  @override
  String get performanceWarning => 'אזהרת ביצועים';

  @override
  String get largeModelWarning =>
      'דגם זה גדול ועלול להתרסק או לרוץ לאט מאוד במכשירים ניידים.\n\n\"small\" או \"base\" מומלץ.';

  @override
  String get usingNativeIosSpeech => 'שימוש בזיהוי דיבור iOS מקומי';

  @override
  String get noModelDownloadRequired => 'מנוע הדיבור המקומי של המכשיר שלך יהיה בשימוש. הורדת דגם אינה נדרשת.';

  @override
  String get modelReady => 'דגם מוכן';

  @override
  String get redownload => 'הורד מחדש';

  @override
  String get doNotCloseApp => 'אנא אל תסגור את האפליקציה.';

  @override
  String get downloading => 'הורדה...';

  @override
  String get downloadModel => 'הורד דגם';

  @override
  String estimatedSize(String size) {
    return 'גודל משוער: ~$size MB';
  }

  @override
  String availableSpace(String space) {
    return 'מקום זמין: $space';
  }

  @override
  String get notEnoughSpace => 'אזהרה: אין מקום מספיק!';

  @override
  String get download => 'הורד';

  @override
  String downloadError(String error) {
    return 'שגיאת הורדה: $error';
  }

  @override
  String get cancelled => 'בוטל';

  @override
  String get deviceNotCompatibleTitle => 'המכשיר לא תואם';

  @override
  String get deviceNotMeetRequirements => 'המכשיר שלך אינו עומד בדרישות עבור תמלול On-Device.';

  @override
  String get transcriptionSlowerOnDevice => 'תמלול On-device אולי יהיה איטי יותר במכשיר זה.';

  @override
  String get computationallyIntensive => 'תמלול On-Device הוא עתיר חישובים.';

  @override
  String get batteryDrainSignificantly => 'זליגת הסוללה תגדל משמעותית.';

  @override
  String get premiumMinutesMonth => '1,200 דקות פרמיום/חודש. כרטיסייה On-Device מציעה תמלול בחינם ללא הגבלה. ';

  @override
  String get audioProcessedLocally => 'אודיו מעובד מקומית. עובד במצב לא מקוון, פרטי יותר, אך משתמש בסוללה יותר.';

  @override
  String get languageLabel => 'שפה';

  @override
  String get modelLabel => 'דגם';

  @override
  String get modelTooLargeWarning =>
      'דגם זה גדול ועלול להתרסק או לרוץ לאט מאוד במכשירים ניידים.\n\n\"small\" או \"base\" מומלץ.';

  @override
  String get nativeEngineNoDownload => 'מנוע הדיבור המקומי של המכשיר שלך יהיה בשימוש. הורדת דגם אינה נדרשת.';

  @override
  String modelReadyWithName(String model) {
    return 'דגם מוכן ($model)';
  }

  @override
  String get reDownload => 'הורד מחדש';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return 'הורדה של $model: $received / $total MB';
  }

  @override
  String preparingModel(String model) {
    return 'הכנת $model...';
  }

  @override
  String downloadErrorWithMessage(String error) {
    return 'שגיאת הורדה: $error';
  }

  @override
  String estimatedSizeWithValue(String size) {
    return 'גודל משוער: ~$size MB';
  }

  @override
  String availableSpaceWithValue(String space) {
    return 'מקום זמין: $space';
  }

  @override
  String get omiTranscriptionOptimized =>
      'התמלול החי המובנה של Omi מותאם לשיחות בזמן אמת עם זיהוי דוברים אוטומטי וdiarization.';

  @override
  String get reset => 'איפוס';

  @override
  String get useTemplateFrom => 'השתמש בתבנית מ';

  @override
  String get selectProviderTemplate => 'בחר תבנית ספק...';

  @override
  String get quicklyPopulateResponse => 'מלא במהירות בפורמט תגובה של ספק ידוע';

  @override
  String get quicklyPopulateRequest => 'מלא במהירות בפורמט בקשה של ספק ידוע';

  @override
  String get invalidJsonError => 'JSON לא תקף';

  @override
  String downloadModelWithName(String model) {
    return 'הורד דגם ($model)';
  }

  @override
  String modelNameWithFile(String model) {
    return 'דגם: $model';
  }

  @override
  String get device => 'מכשיר';

  @override
  String get chatAssistantsTitle => 'עוזרי צ\'אט';

  @override
  String get permissionReadConversations => 'קרא שיחות';

  @override
  String get permissionReadMemories => 'קרא זיכרונות';

  @override
  String get permissionReadTasks => 'קרא משימות';

  @override
  String get permissionCreateConversations => 'צור שיחות';

  @override
  String get permissionCreateMemories => 'צור זיכרונות';

  @override
  String get permissionTypeAccess => 'גישה';

  @override
  String get permissionTypeCreate => 'צור';

  @override
  String get permissionTypeTrigger => 'הפעל';

  @override
  String get permissionDescReadConversations => 'אפליקציה זו יכולה לגשת לשיחות שלך.';

  @override
  String get permissionDescReadMemories => 'אפליקציה זו יכולה לגשת לזיכרונות שלך.';

  @override
  String get permissionDescReadTasks => 'אפליקציה זו יכולה לגשת למשימות שלך.';

  @override
  String get permissionDescCreateConversations => 'אפליקציה זו יכולה ליצור שיחות חדשות.';

  @override
  String get permissionDescCreateMemories => 'אפליקציה זו יכולה ליצור זיכרונות חדשים.';

  @override
  String get realtimeListening => 'האזנה בזמן אמת';

  @override
  String get setupCompleted => 'הושלם';

  @override
  String get pleaseSelectRating => 'אנא בחר דירוג';

  @override
  String get writeReviewOptional => 'כתוב ביקורת (אופציונלי)';

  @override
  String get setupQuestionsIntro => 'עזור לנו לשפר את Omi על ידי מענה לכמה שאלות. 🫶 💜';

  @override
  String get setupQuestionProfession => '1. מה אתה עושה?';

  @override
  String get setupQuestionUsage => '2. איפה אתה מתכנן להשתמש ב-Omi שלך?';

  @override
  String get setupQuestionAge => '3. מה טווח הגיל שלך?';

  @override
  String get setupAnswerAllQuestions => 'עדיין לא ענית לכל השאלות! 🥺';

  @override
  String get setupSkipHelp => 'דלג, אני לא רוצה לעזור :C';

  @override
  String get professionEntrepreneur => 'יזם';

  @override
  String get professionSoftwareEngineer => 'מהנדס תוכנה';

  @override
  String get professionProductManager => 'מנהל מוצר';

  @override
  String get professionExecutive => 'מנהל';

  @override
  String get professionSales => 'מכירות';

  @override
  String get professionStudent => 'סטודנט';

  @override
  String get usageAtWork => 'בעבודה';

  @override
  String get usageIrlEvents => 'אירועים בחיים האמיתיים';

  @override
  String get usageOnline => 'מקוון';

  @override
  String get usageSocialSettings => 'בהגדרות חברתיות';

  @override
  String get usageEverywhere => 'בכל מקום';

  @override
  String get customBackendUrlTitle => 'כתובת URL של Backend מותאמת אישית';

  @override
  String get backendUrlLabel => 'כתובת URL של Backend';

  @override
  String get saveUrlButton => 'שמור כתובת URL';

  @override
  String get enterBackendUrlError => 'אנא הזן את כתובת ה-Backend';

  @override
  String get urlMustEndWithSlashError => 'כתובת URL חייבת להסתיים ב-\"/\"';

  @override
  String get invalidUrlError => 'אנא הזן כתובת URL חוקית';

  @override
  String get backendUrlSavedSuccess => 'כתובת ה-Backend נשמרה בהצלחה!';

  @override
  String get signInTitle => 'התחברות';

  @override
  String get signInButton => 'התחברות';

  @override
  String get enterEmailError => 'אנא הזן את הדוא\"ל שלך';

  @override
  String get invalidEmailError => 'אנא הזן דוא\"ל חוקי';

  @override
  String get enterPasswordError => 'אנא הזן את הסיסמה שלך';

  @override
  String get passwordMinLengthError => 'הסיסמה חייבת להיות בעלת אורך של לפחות 8 תווים';

  @override
  String get signInSuccess => 'התחברות בהצלחה!';

  @override
  String get alreadyHaveAccountLogin => 'יש לך כבר חשבון? כנס';

  @override
  String get emailLabel => 'דוא\"ל';

  @override
  String get passwordLabel => 'סיסמה';

  @override
  String get createAccountTitle => 'צור חשבון';

  @override
  String get nameLabel => 'שם';

  @override
  String get repeatPasswordLabel => 'חזור על סיסמה';

  @override
  String get signUpButton => 'הירשם';

  @override
  String get enterNameError => 'אנא הזן את שמך';

  @override
  String get passwordsDoNotMatch => 'הסיסמאות אינן תואמות';

  @override
  String get signUpSuccess => 'הרשמה בהצלחה!';

  @override
  String get loadingKnowledgeGraph => 'טעינת גרף ידע...';

  @override
  String get noKnowledgeGraphYet => 'אין גרף ידע עדיין';

  @override
  String get buildingKnowledgeGraphFromMemories => 'בנייה של גרף הידע שלך מזיכרונות...';

  @override
  String get knowledgeGraphWillBuildAutomatically => 'גרף הידע שלך יבנה באופן אוטומטי כשאתה יוצר זיכרונות חדשים.';

  @override
  String get buildGraphButton => 'בנה גרף';

  @override
  String get checkOutMyMemoryGraph => 'בדוק את גרף הזיכרון שלי!';

  @override
  String get getButton => 'קבל';

  @override
  String openingApp(String appName) {
    return 'פתיחה של $appName...';
  }

  @override
  String get writeSomething => 'כתוב משהו';

  @override
  String get submitReply => 'שלח תשובה';

  @override
  String get editYourReply => 'ערוך את התשובה שלך';

  @override
  String get replyToReview => 'השב לביקורת';

  @override
  String get rateAndReviewThisApp => 'דרג וכתוב ביקורת על אפליקציה זו';

  @override
  String get noChangesInReview => 'אין שינויים בביקורת כדי לעדכן.';

  @override
  String get cantRateWithoutInternet => 'לא ניתן לדרג אפליקציה ללא חיבור אינטרנט.';

  @override
  String get appAnalytics => 'ניתוח אפליקציות';

  @override
  String get learnMoreLink => 'למד עוד';

  @override
  String get moneyEarned => 'כסף שהרווחת';

  @override
  String get writeYourReply => 'כתוב את התשובה שלך...';

  @override
  String get replySentSuccessfully => 'התשובה נשלחה בהצלחה';

  @override
  String failedToSendReply(String error) {
    return 'איתור בשליחת התשובה: $error';
  }

  @override
  String get send => 'שלח';

  @override
  String starFilter(int count) {
    return '$count כוכב';
  }

  @override
  String get noReviewsFound => 'לא נמצאו ביקורות';

  @override
  String get editReply => 'ערוך תשובה';

  @override
  String get reply => 'השב';

  @override
  String starFilterLabel(int count) {
    return '$count כוכב';
  }

  @override
  String get sharePublicLink => 'שתף קישור ציבורי';

  @override
  String get connectedKnowledgeData => 'נתוני ידע מחוברים';

  @override
  String get enterName => 'הזן שם';

  @override
  String get goal => 'יעד';

  @override
  String get tapToTrackThisGoal => 'הקש כדי לעקוב אחר יעד זה';

  @override
  String get tapToSetAGoal => 'הקש כדי להגדיר יעד';

  @override
  String get processedConversations => 'שיחות שעובדו';

  @override
  String get updatedConversations => 'שיחות מעודכנות';

  @override
  String get newConversations => 'שיחות חדשות';

  @override
  String get summaryTemplate => 'תבנית סיכום';

  @override
  String get suggestedTemplates => 'תבניות מוצעות';

  @override
  String get otherTemplates => 'תבניות אחרות';

  @override
  String get availableTemplates => 'תבניות זמינות';

  @override
  String get getCreative => 'הפוך ליצירתי';

  @override
  String get defaultLabel => 'ברירת מחדל';

  @override
  String get lastUsedLabel => 'בשימוש לאחרונה';

  @override
  String get setDefaultApp => 'הגדר אפליקציה ברירת מחדל';

  @override
  String setDefaultAppContent(String appName) {
    return 'הגדר את $appName כאפליקציית הסיכום ברירת המחדל שלך?\\n\\nאפליקציה זו תשמש באופן אוטומטי לכל סיכומי השיחות בעתיד.';
  }

  @override
  String get setDefaultButton => 'הגדר ברירת מחדל';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName הוגדרה כאפליקציית הסיכום ברירת המחדל';
  }

  @override
  String get createCustomTemplate => 'צור תבנית מותאמת אישית';

  @override
  String get allTemplates => 'כל התבניות';

  @override
  String failedToInstallApp(String appName) {
    return 'איתור בהתקנת $appName. אנא נסה שוב.';
  }

  @override
  String errorInstallingApp(String appName, String error) {
    return 'שגיאה בהתקנת $appName: $error';
  }

  @override
  String tagSpeaker(int speakerId) {
    return 'תגיד דובר $speakerId';
  }

  @override
  String get personNameAlreadyExists => 'קיים כבר אדם בשם זה.';

  @override
  String get selectYouFromList => 'כדי לתג את עצמך, בחר \"אתה\" מהרשימה.';

  @override
  String get enterPersonsName => 'הזן שם של אדם';

  @override
  String get addPerson => 'הוסף אדם';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'תגיד קטעים אחרים מדובר זה ($selected/$total)';
  }

  @override
  String get tagOtherSegments => 'תגיד קטעים אחרים';

  @override
  String get managePeople => 'נהל אנשים';

  @override
  String get shareViaSms => 'שתף דרך SMS';

  @override
  String get selectContactsToShareSummary => 'בחר אנשי קשר כדי לשתף את סיכום השיחה שלך';

  @override
  String get searchContactsHint => 'חפש אנשי קשר...';

  @override
  String contactsSelectedCount(int count) {
    return '$count נבחרו';
  }

  @override
  String get clearAllSelection => 'נקה הכל';

  @override
  String get selectContactsToShare => 'בחר אנשי קשר לשיתוף';

  @override
  String shareWithContactCount(int count) {
    return 'שתף עם $count איש קשר';
  }

  @override
  String shareWithContactsCount(int count) {
    return 'שתף עם $count אנשי קשר';
  }

  @override
  String get contactsPermissionRequired => 'נדרשת הרשאת אנשי קשר';

  @override
  String get contactsPermissionRequiredForSms => 'הרשאת אנשי קשר נדרשת לשיתוף דרך SMS';

  @override
  String get grantContactsPermissionForSms => 'אנא תן הרשאת אנשי קשר כדי לשתף דרך SMS';

  @override
  String get noContactsWithPhoneNumbers => 'לא נמצאו אנשי קשר עם מספרי טלפון';

  @override
  String get noContactsMatchSearch => 'אין אנשי קשר התואמים לחיפוש שלך';

  @override
  String get failedToLoadContacts => 'איתור בטעינת אנשי קשר';

  @override
  String get failedToPrepareConversationForSharing => 'איתור בהכנת השיחה לשיתוף. אנא נסה שוב.';

  @override
  String get couldNotOpenSmsApp => 'לא הצליח לפתוח את אפליקציית SMS. אנא נסה שוב.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'הנה מה שדיברנו עליו בדיוק: $link';
  }

  @override
  String get wifiSync => 'סנכרון WiFi';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item הועתק ללוח הגזירה';
  }

  @override
  String get wifiConnectionFailedTitle => 'החיבור נכשל';

  @override
  String connectingToDeviceName(String deviceName) {
    return 'התחברות ל-$deviceName';
  }

  @override
  String enableDeviceWifi(String deviceName) {
    return 'הפעל WiFi של $deviceName';
  }

  @override
  String connectToDeviceName(String deviceName) {
    return 'התחברות ל-$deviceName';
  }

  @override
  String get recordingDetails => 'פרטי הקלטה';

  @override
  String get storageLocationSdCard => 'כרטיס SD';

  @override
  String get storageLocationLimitlessPendant => 'Limitless Pendant';

  @override
  String get storageLocationPhone => 'טלפון';

  @override
  String get storageLocationPhoneMemory => 'טלפון (זיכרון)';

  @override
  String storedOnDevice(String deviceName) {
    return 'מאוחסן ב-$deviceName';
  }

  @override
  String get transferring => 'העברה...';

  @override
  String get transferRequired => 'העברה נדרשת';

  @override
  String get downloadingAudioFromSdCard => 'הורדה של אודיו מכרטיס ה-SD של המכשיר שלך';

  @override
  String get transferRequiredDescription =>
      'הקלטה זו מאוחסנת בכרטיס ה-SD של המכשיר שלך. העבר אותה לטלפון כדי להשמיע או לשתף.';

  @override
  String get cancelTransfer => 'ביטול העברה';

  @override
  String get transferToPhone => 'העבר לטלפון';

  @override
  String get privateAndSecureOnDevice => 'פרטי ובטוח במכשיר שלך';

  @override
  String get recordingInfo => 'מידע הקלטה';

  @override
  String get transferInProgress => 'העברה בעיצומה...';

  @override
  String get shareRecording => 'שתף הקלטה';

  @override
  String get deleteRecordingConfirmation => 'האם אתה בטוח שברצונך למחוק סופית הקלטה זו? לא ניתן לבטל פעולה זו.';

  @override
  String get recordingIdLabel => 'מזהה הקלטה';

  @override
  String get dateTimeLabel => 'תאריך וזמן';

  @override
  String get durationLabel => 'משך הזמן';

  @override
  String get audioFormatLabel => 'פורמט אודיו';

  @override
  String get storageLocationLabel => 'מיקום אחסון';

  @override
  String get estimatedSizeLabel => 'גודל משוער';

  @override
  String get deviceModelLabel => 'דגם ההתקן';

  @override
  String get deviceIdLabel => 'מזהה התקן';

  @override
  String get statusLabel => 'סטטוס';

  @override
  String get statusProcessed => 'מעובד';

  @override
  String get statusUnprocessed => 'לא מעובד';

  @override
  String get switchedToFastTransfer => 'עברת ל-Fast Transfer';

  @override
  String get transferCompleteMessage => 'ההעברה הושלמה! אתה יכול כעת להשמיע הקלטה זו.';

  @override
  String transferFailedMessage(String error) {
    return 'העברה נכשלה: $error';
  }

  @override
  String get transferCancelled => 'ביטול העברה';

  @override
  String get fastTransferEnabled => 'Fast Transfer מופעל';

  @override
  String get bluetoothSyncEnabled => 'סנכרון Bluetooth מופעל';

  @override
  String get enableFastTransfer => 'הפעל Fast Transfer';

  @override
  String get fastTransferDescription =>
      'Fast Transfer משתמש ב-WiFi כדי להשיג מהירויות גבוהות פי 5. הטלפון שלך יתחבר זמנית לרשת ה-WiFi של התקן Omi שלך במהלך ההעברה.';

  @override
  String get internetAccessPausedDuringTransfer => 'גישת האינטרנט מושהית במהלך ההעברה';

  @override
  String get chooseTransferMethodDescription => 'בחר כיצד יוסברו הקלטות מהתקן Omi שלך לטלפון שלך.';

  @override
  String get wifiSpeed => '~150 KB/s דרך WiFi';

  @override
  String get fiveTimesFaster => 'פי 5 מהר יותר';

  @override
  String get fastTransferMethodDescription =>
      'יוצר חיבור WiFi ישיר להתקן Omi שלך. הטלפון שלך יתנתק זמנית מ-WiFi הרגיל שלך במהלך ההעברה.';

  @override
  String get bluetooth => 'Bluetooth';

  @override
  String get bleSpeed => '~30 KB/s דרך BLE';

  @override
  String get bluetoothMethodDescription =>
      'משתמש בחיבור Bluetooth Low Energy סטנדרטי. איטי יותר אך לא משפיע על חיבור ה-WiFi שלך.';

  @override
  String get selected => 'נבחר';

  @override
  String get selectOption => 'בחר';

  @override
  String get lowBatteryAlertTitle => 'התראת סוללה נמוכה';

  @override
  String get lowBatteryAlertBody => 'ההתקן שלך נמצא בסוללה נמוכה. הגיע הזמן לטעינה מחדש! 🔋';

  @override
  String get deviceDisconnectedNotificationTitle => 'התקן Omi שלך התנתק';

  @override
  String get deviceDisconnectedNotificationBody => 'אנא התחבר מחדש כדי להמשיך להשתמש ב-Omi שלך.';

  @override
  String get firmwareUpdateAvailable => 'עדכון קושחה זמין';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'עדכון קושחה חדש ($version) זמין להתקן Omi שלך. האם תרצה לעדכן כעת?';
  }

  @override
  String get later => 'מאוחר יותר';

  @override
  String get appDeletedSuccessfully => 'האפליקציה נמחקה בהצלחה';

  @override
  String get appDeleteFailed => 'כישלון במחיקת האפליקציה. אנא נסה שוב מאוחר יותר.';

  @override
  String get appVisibilityChangedSuccessfully => 'שינוי הנראות של האפליקציה בוצע בהצלחה. זה עלול להימשך כמה דקות.';

  @override
  String get errorActivatingAppIntegration => 'שגיאה בהפעלת האפליקציה. אם זו אפליקציית אינטגרציה, וודא שההגדרה הושלמה.';

  @override
  String get errorUpdatingAppStatus => 'אירעה שגיאה בעדכון סטטוס האפליקציה.';

  @override
  String get calculatingETA => 'חישוב...';

  @override
  String aboutMinutesRemaining(int minutes) {
    return 'בערך $minutes דקות נותרו';
  }

  @override
  String get aboutAMinuteRemaining => 'בערך דקה אחת נותרה';

  @override
  String get almostDone => 'כמעט סיימנו...';

  @override
  String get omiSays => 'Omi אומר';

  @override
  String get analyzingYourData => 'ניתוח הנתונים שלך...';

  @override
  String migratingToProtection(String level) {
    return 'הגירה להגנת $level...';
  }

  @override
  String get noDataToMigrateFinalizing => 'אין נתונים להגרה. סיום...';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return 'הגרת $itemType... $percentage%';
  }

  @override
  String get allObjectsMigratedFinalizing => 'כל החפצים הוגרו. סיום...';

  @override
  String get migrationErrorOccurred => 'אירעה שגיאה במהלך ההגרה. אנא נסה שוב.';

  @override
  String get migrationComplete => 'ההגרה הושלמה!';

  @override
  String dataProtectedWithSettings(String level) {
    return 'הנתונים שלך מוגנים כעת עם הגדרות $level החדשות.';
  }

  @override
  String get chatsLowercase => 'צ\'אטים';

  @override
  String get dataLowercase => 'נתונים';

  @override
  String get fallNotificationTitle => 'אויך';

  @override
  String get fallNotificationBody => 'האם נפלת?';

  @override
  String get importantConversationTitle => 'שיחה חשובה';

  @override
  String get importantConversationBody => 'זה עתה הייתה לך שיחה חשובה. הקש כדי לשתף את הסיכום עם אחרים.';

  @override
  String get templateName => 'שם תבנית';

  @override
  String get templateNameHint => 'למשל, מחלץ פריטי פעולה של פגישה';

  @override
  String get nameMustBeAtLeast3Characters => 'השם חייב להיות לפחות 3 תווים';

  @override
  String get conversationPromptHint => 'למשל, חלץ פריטי פעולה, החלטות שהתקבלו וטקה-וויים חיוניים מהשיחה שסופקה.';

  @override
  String get pleaseEnterAppPrompt => 'אנא הזן הנחיה עבור האפליקציה שלך';

  @override
  String get promptMustBeAtLeast10Characters => 'ההנחיה חייבת להיות לפחות 10 תווים';

  @override
  String get anyoneCanDiscoverTemplate => 'כל אחד יכול לגלות את התבנית שלך';

  @override
  String get onlyYouCanUseTemplate => 'רק אתה יכול להשתמש בתבנית זו';

  @override
  String get generatingDescription => 'ייצור תיאור...';

  @override
  String get creatingAppIcon => 'יצירת סמל אפליקציה...';

  @override
  String get installingApp => 'התקנת אפליקציה...';

  @override
  String get appCreatedAndInstalled => 'אפליקציה נוצרה והותקנה!';

  @override
  String get appCreatedSuccessfully => 'אפליקציה נוצרה בהצלחה!';

  @override
  String get failedToCreateApp => 'כישלון ביצירת אפליקציה. אנא נסה שוב.';

  @override
  String get addAppSelectCoreCapability => 'אנא בחר עוד יכולת ליבה אחת עבור האפליקציה שלך כדי להמשיך';

  @override
  String get addAppSelectPaymentPlan => 'אנא בחר תוכנית תשלום והזן מחיר עבור האפליקציה שלך';

  @override
  String get addAppSelectCapability => 'אנא בחר לפחות יכולת אחת עבור האפליקציה שלך';

  @override
  String get addAppSelectLogo => 'אנא בחר לוגו עבור האפליקציה שלך';

  @override
  String get addAppEnterChatPrompt => 'אנא הזן הנחיית צ\'אט עבור האפליקציה שלך';

  @override
  String get addAppEnterConversationPrompt => 'אנא הזן הנחיית שיחה עבור האפליקציה שלך';

  @override
  String get addAppSelectTriggerEvent => 'אנא בחר אירוע טריגר עבור האפליקציה שלך';

  @override
  String get addAppEnterWebhookUrl => 'אנא הזן כתובת webhook עבור האפליקציה שלך';

  @override
  String get addAppSelectCategory => 'אנא בחר קטגוריה עבור האפליקציה שלך';

  @override
  String get addAppFillRequiredFields => 'אנא מלא את כל השדות הנדרשים כראוי';

  @override
  String get addAppUpdatedSuccess => 'אפליקציה עודכנה בהצלחה 🚀';

  @override
  String get addAppUpdateFailed => 'כישלון בעדכון אפליקציה. אנא נסה שוב מאוחר יותר';

  @override
  String get addAppSubmittedSuccess => 'אפליקציה הוגשה בהצלחה 🚀';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'שגיאה בפתיחת בורר קבצים: $message';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'שגיאה בבחירת תמונה: $error';
  }

  @override
  String get addAppPhotosPermissionDenied => 'הרשאת תמונות נדחתה. אנא אפשר גישה לתמונות כדי לבחור תמונה';

  @override
  String get addAppErrorSelectingImageRetry => 'שגיאה בבחירת תמונה. אנא נסה שוב.';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'שגיאה בבחירת תמונה ממוזערת: $error';
  }

  @override
  String get addAppErrorSelectingThumbnailRetry => 'שגיאה בבחירת תמונה ממוזערת. אנא נסה שוב.';

  @override
  String get addAppCapabilityConflictWithPersona => 'לא ניתן לבחור יכולות אחרות עם Persona';

  @override
  String get addAppPersonaConflictWithCapabilities => 'לא ניתן לבחור Persona עם יכולות אחרות';

  @override
  String get paymentFailedToFetchCountries => 'כישלון בטעינת מדינות נתמכות. אנא נסה שוב מאוחר יותר.';

  @override
  String get paymentFailedToSetDefault => 'כישלון בהגדרת שיטת תשלום ברירת מחדל. אנא נסה שוב מאוחר יותר.';

  @override
  String get paymentFailedToSavePaypal => 'כישלון בשמירת פרטי PayPal. אנא נסה שוב מאוחר יותר.';

  @override
  String get paypalEmailHint => 'nik@example.com';

  @override
  String get paypalMeLinkHint => 'paypal.me/nik';

  @override
  String get paymentMethodStripe => 'Stripe';

  @override
  String get paymentMethodPayPal => 'PayPal';

  @override
  String get paymentStatusActive => 'פעיל';

  @override
  String get paymentStatusConnected => 'מחובר';

  @override
  String get paymentStatusNotConnected => 'לא מחובר';

  @override
  String get paymentAppCost => 'עלות אפליקציה';

  @override
  String get paymentEnterValidAmount => 'אנא הזן סכום תקף';

  @override
  String get paymentEnterAmountGreaterThanZero => 'אנא הזן סכום גדול מ-0';

  @override
  String get paymentPlan => 'תוכנית תשלום';

  @override
  String get paymentNoneSelected => 'לא נבחרה';

  @override
  String get aiGenPleaseEnterDescription => 'אנא הזן תיאור עבור האפליקציה שלך';

  @override
  String get aiGenCreatingAppIcon => 'יצירת סמל אפליקציה...';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'אירעה שגיאה: $message';
  }

  @override
  String get aiGenAppCreatedSuccessfully => 'אפליקציה נוצרה בהצלחה!';

  @override
  String get aiGenFailedToCreateApp => 'כישלון בייצירת אפליקציה';

  @override
  String get aiGenErrorWhileCreatingApp => 'אירעה שגיאה בעת יצירת האפליקציה';

  @override
  String get aiGenFailedToGenerateApp => 'כישלון בייצור אפליקציה. אנא נסה שוב.';

  @override
  String get aiGenFailedToRegenerateIcon => 'כישלון בייצור מחדש של סמל';

  @override
  String get aiGenPleaseGenerateAppFirst => 'אנא צור אפליקציה תחילה';

  @override
  String get nextButton => 'הבא';

  @override
  String get connectOmiDevice => 'חבר התקן Omi';

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'אתה עובר מתוכנית Unlimited ל-$title. האם אתה בטוח שברצונך להמשיך?';
  }

  @override
  String get planUpgradeScheduledMessage =>
      'שדרוג זמין! תוכנית החודשית שלך נמשכת עד סוף תקופת החיוב שלך, ואז עוברת אוטומטית לתשנתי.';

  @override
  String get couldNotSchedulePlanChange => 'לא היתה אפשרות לתזמן שינוי תוכנית. אנא נסה שוב.';

  @override
  String get subscriptionReactivatedDefault => 'המנוי שלך הופעל מחדש! לא חיוב כעת - תחויב בסוף התקופה הנוכחית שלך.';

  @override
  String get subscriptionSuccessfulCharged => 'המנוי הצליח! חויבת עבור תקופת החיוב החדשה.';

  @override
  String get couldNotProcessSubscription => 'לא היתה אפשרות לעבד את המנוי. אנא נסה שוב.';

  @override
  String get couldNotLaunchUpgradePage => 'לא היתה אפשרות להשיק דף שדרוג. אנא נסה שוב.';

  @override
  String get transcriptionJsonPlaceholder => 'הדבק את תצורת ה-JSON שלך כאן...';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get pricePlaceholder => '0.00';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'שגיאה בפתיחת בורר קבצים: $message';
  }

  @override
  String importErrorGeneric(String error) {
    return 'שגיאה: $error';
  }

  @override
  String get mergeConversationsSuccessTitle => 'שיחות מוזגו בהצלחה';

  @override
  String mergeConversationsSuccessBody(int count) {
    return '$count שיחות מוזגו בהצלחה';
  }

  @override
  String get actionItemReminderTitle => 'תזכורת Omi';

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName התנתק';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'אנא התחבר מחדש כדי להמשיך להשתמש ב-$deviceName שלך.';
  }

  @override
  String get onboardingSignIn => 'כניסה';

  @override
  String get onboardingYourName => 'השם שלך';

  @override
  String get onboardingLanguage => 'שפה';

  @override
  String get onboardingPermissions => 'הרשאות';

  @override
  String get onboardingComplete => 'השלם';

  @override
  String get onboardingWelcomeToOmi => 'ברוכים הבאים ל-Omi';

  @override
  String get onboardingTellUsAboutYourself => 'ספר לנו על עצמך';

  @override
  String get onboardingChooseYourPreference => 'בחר את ההעדפה שלך';

  @override
  String get onboardingGrantRequiredAccess => 'הגרם גישה נדרשת';

  @override
  String get onboardingYoureAllSet => 'הכל מוכן';

  @override
  String get searchTranscriptOrSummary => 'חפש תמלול או סיכום...';

  @override
  String get myGoal => 'היעד שלי';

  @override
  String get appNotAvailable => 'אוops! נראה שהאפליקציה שאתה מחפש אינה זמינה.';

  @override
  String get failedToConnectTodoist => 'כישלון בחיבור לـ Todoist';

  @override
  String get failedToConnectAsana => 'כישלון בחיבור לـ Asana';

  @override
  String get failedToConnectGoogleTasks => 'כישלון בחיבור לـ Google Tasks';

  @override
  String get failedToConnectClickUp => 'כישלון בחיבור לـ ClickUp';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return 'כישלון בחיבור לـ $serviceName: $error';
  }

  @override
  String get successfullyConnectedTodoist => 'התחבר בהצלחה לـ Todoist!';

  @override
  String get failedToConnectTodoistRetry => 'כישלון בחיבור לـ Todoist. אנא נסה שוב.';

  @override
  String get successfullyConnectedAsana => 'התחבר בהצלחה לـ Asana!';

  @override
  String get failedToConnectAsanaRetry => 'כישלון בחיבור לـ Asana. אנא נסה שוב.';

  @override
  String get successfullyConnectedGoogleTasks => 'התחבר בהצלחה לـ Google Tasks!';

  @override
  String get failedToConnectGoogleTasksRetry => 'כישלון בחיבור לـ Google Tasks. אנא נסה שוב.';

  @override
  String get successfullyConnectedClickUp => 'התחבר בהצלחה לـ ClickUp!';

  @override
  String get failedToConnectClickUpRetry => 'כישלון בחיבור לـ ClickUp. אנא נסה שוב.';

  @override
  String get successfullyConnectedNotion => 'התחבר בהצלחה לـ Notion!';

  @override
  String get failedToRefreshNotionStatus => 'כישלון בחידוש סטטוס חיבור Notion.';

  @override
  String get successfullyConnectedGoogle => 'התחבר בהצלחה ל-Google!';

  @override
  String get failedToRefreshGoogleStatus => 'כישלון בחידוש סטטוס חיבור Google.';

  @override
  String get successfullyConnectedWhoop => 'התחבר בהצלחה ל-Whoop!';

  @override
  String get failedToRefreshWhoopStatus => 'כישלון בחידוש סטטוס חיבור Whoop.';

  @override
  String get successfullyConnectedGitHub => 'התחבר בהצלחה לـ GitHub!';

  @override
  String get failedToRefreshGitHubStatus => 'כישלון בחידוש סטטוס חיבור GitHub.';

  @override
  String get authFailedToSignInWithGoogle => 'כישלון בכניסה עם Google, אנא נסה שוב.';

  @override
  String get authenticationFailed => 'האימות נכשל. אנא נסה שוב.';

  @override
  String get authFailedToSignInWithApple => 'כישלון בכניסה עם Apple, אנא נסה שוב.';

  @override
  String get authFailedToRetrieveToken => 'כישלון בשליפת אסימון firebase, אנא נסה שוב.';

  @override
  String get authUnexpectedErrorFirebase => 'שגיאה בלתי צפויה בעת הכניסה, שגיאת Firebase, אנא נסה שוב.';

  @override
  String get authUnexpectedError => 'שגיאה בלתי צפויה בעת הכניסה, אנא נסה שוב';

  @override
  String get authFailedToLinkGoogle => 'כישלון בקישור עם Google, אנא נסה שוב.';

  @override
  String get authFailedToLinkApple => 'כישלון בקישור עם Apple, אנא נסה שוב.';

  @override
  String get onboardingBluetoothRequired => 'הרשאת Bluetooth נדרשת כדי להתחבר להתקן שלך.';

  @override
  String get onboardingBluetoothDeniedSystemPrefs => 'הרשאת Bluetooth נדחתה. אנא הגרם הרשאה בהעדפות מערכת.';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'סטטוס הרשאת Bluetooth: $status. אנא בדוק בהעדפות מערכת.';
  }

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'כישלון בבדיקת הרשאת Bluetooth: $error';
  }

  @override
  String get onboardingNotificationDeniedSystemPrefs => 'הרשאת התראות נדחתה. אנא הגרם הרשאה בהעדפות מערכת.';

  @override
  String get onboardingNotificationDeniedNotifications => 'הרשאת התראות נדחתה. אנא הגרם הרשאה בהעדפות מערכת > התראות.';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return 'סטטוס הרשאת התראות: $status. אנא בדוק בהעדפות מערכת.';
  }

  @override
  String onboardingFailedCheckNotification(String error) {
    return 'כישלון בבדיקת הרשאת התראות: $error';
  }

  @override
  String get onboardingLocationGrantInSettings => 'אנא הגרם הרשאת מיקום בהגדרות > פרטיות וביטחון > שירותי מיקום';

  @override
  String get onboardingMicrophoneRequired => 'הרשאת מיקרופון נדרשת להקלטה.';

  @override
  String get onboardingMicrophoneDenied =>
      'הרשאת מיקרופון נדחתה. אנא הגרם הרשאה בהעדפות מערכת > פרטיות וביטחון > מיקרופון.';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'סטטוס הרשאת מיקרופון: $status. אנא בדוק בהעדפות מערכת.';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'כישלון בבדיקת הרשאת מיקרופון: $error';
  }

  @override
  String get onboardingScreenCaptureRequired => 'הרשאת צילום מסך נדרשת להקלטת אודיו מערכת.';

  @override
  String get onboardingScreenCaptureDenied =>
      'הרשאת צילום מסך נדחתה. אנא הגרם הרשאה בהעדפות מערכת > פרטיות וביטחון > צילום מסך.';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return 'סטטוס הרשאת צילום מסך: $status. אנא בדוק בהעדפות מערכת.';
  }

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return 'כישלון בבדיקת הרשאת צילום מסך: $error';
  }

  @override
  String get onboardingAccessibilityRequired => 'הרשאת נגישות נדרשת לאתר פגישות דפדפן.';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'סטטוס הרשאת נגישות: $status. אנא בדוק בהעדפות מערכת.';
  }

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'כישלון בבדיקת הרשאת נגישות: $error';
  }

  @override
  String get msgCameraNotAvailable => 'צילום מצלמה אינו זמין בפלטפורמה זו';

  @override
  String get msgCameraPermissionDenied => 'הרשאת מצלמה נדחתה. אנא אפשר גישה למצלמה';

  @override
  String msgCameraAccessError(String error) {
    return 'שגיאה בגישה למצלמה: $error';
  }

  @override
  String get msgPhotoError => 'שגיאה בצילום תמונה. אנא נסה שוב.';

  @override
  String get msgMaxImagesLimit => 'אתה יכול לבחור עד 4 תמונות בלבד';

  @override
  String msgFilePickerError(String error) {
    return 'שגיאה בפתיחת בורר קבצים: $error';
  }

  @override
  String msgSelectImagesError(String error) {
    return 'שגיאה בבחירת תמונות: $error';
  }

  @override
  String get msgPhotosPermissionDenied => 'הרשאת תמונות נדחתה. אנא אפשר גישה לתמונות לבחירת תמונות';

  @override
  String get msgSelectImagesGenericError => 'שגיאה בבחירת תמונות. אנא נסה שוב.';

  @override
  String get msgMaxFilesLimit => 'אתה יכול לבחור עד 4 קבצים בלבד';

  @override
  String msgSelectFilesError(String error) {
    return 'שגיאה בבחירת קבצים: $error';
  }

  @override
  String get msgSelectFilesGenericError => 'שגיאה בבחירת קבצים. אנא נסה שוב.';

  @override
  String get msgUploadFileFailed => 'כישלון בהעלאת קובץ, אנא נסה שוב מאוחר יותר';

  @override
  String get msgReadingMemories => 'קריאה של הזיכרונות שלך...';

  @override
  String get msgLearningMemories => 'למידה מהזיכרונות שלך...';

  @override
  String get msgUploadAttachedFileFailed => 'כישלון בהעלאת הקובץ המצורף.';

  @override
  String captureRecordingError(String error) {
    return 'אירעה שגיאה במהלך ההקלטה: $error';
  }

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return 'ההקלטה הופסקה: $reason. אתה אולי צריך להתחבר מחדש לתצוגות חיצוניות או להתחיל להקליט מחדש.';
  }

  @override
  String get captureMicrophonePermissionRequired => 'הרשאת מיקרופון נדרשת';

  @override
  String get captureMicrophonePermissionInSystemPreferences => 'הגרם הרשאת מיקרופון בהעדפות מערכת';

  @override
  String get captureScreenRecordingPermissionRequired => 'הרשאת צילום מסך נדרשת';

  @override
  String get captureDisplayDetectionFailed => 'זיהוי תצוגה נכשל. ההקלטה הופסקה.';

  @override
  String get devModeInvalidAudioBytesWebhookUrl => 'כתובת webhook של בתים אודיו לא תקפה';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl => 'כתובת webhook של תמלול בזמן אמת לא תקפה';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl => 'כתובת webhook של שיחה שנוצרה לא תקפה';

  @override
  String get devModeInvalidDaySummaryWebhookUrl => 'כתובת webhook של סיכום יום לא תקפה';

  @override
  String get devModeSettingsSaved => 'הגדרות שמורות!';

  @override
  String get voiceFailedToTranscribe => 'כישלון בתמלול אודיו';

  @override
  String get locationPermissionRequired => 'הרשאת מיקום נדרשת';

  @override
  String get locationPermissionContent =>
      'Fast Transfer דורש הרשאת מיקום כדי לאמת חיבור WiFi. אנא הגרם הרשאת מיקום כדי להמשיך.';

  @override
  String get pdfTranscriptExport => 'ייצוא תמלול';

  @override
  String get pdfConversationExport => 'ייצוא שיחה';

  @override
  String pdfTitleLabel(String title) {
    return 'כותרת: $title';
  }

  @override
  String get conversationNewIndicator => 'חדש 🚀';

  @override
  String conversationPhotosCount(int count) {
    return '$count תמונות';
  }

  @override
  String get mergingStatus => 'מיזוג...';

  @override
  String timeSecsSingular(int count) {
    return '$count שנייה';
  }

  @override
  String timeSecsPlural(int count) {
    return '$count שניות';
  }

  @override
  String timeMinSingular(int count) {
    return '$count דקה';
  }

  @override
  String timeMinsPlural(int count) {
    return '$count דקות';
  }

  @override
  String timeMinsAndSecs(int mins, int secs) {
    return '$mins דקות $secs שניות';
  }

  @override
  String timeHourSingular(int count) {
    return '$count שעה';
  }

  @override
  String timeHoursPlural(int count) {
    return '$count שעות';
  }

  @override
  String timeHoursAndMins(int hours, int mins) {
    return '$hours שעות $mins דקות';
  }

  @override
  String timeDaySingular(int count) {
    return '$count יום';
  }

  @override
  String timeDaysPlural(int count) {
    return '$count ימים';
  }

  @override
  String timeDaysAndHours(int days, int hours) {
    return '$days ימים $hours שעות';
  }

  @override
  String timeCompactSecs(int count) {
    return '${count}s';
  }

  @override
  String timeCompactMins(int count) {
    return '${count}m';
  }

  @override
  String timeCompactMinsAndSecs(int mins, int secs) {
    return '${mins}m ${secs}s';
  }

  @override
  String timeCompactHours(int count) {
    return '${count}h';
  }

  @override
  String timeCompactHoursAndMins(int hours, int mins) {
    return '${hours}h ${mins}m';
  }

  @override
  String get moveToFolder => 'העבר לתיקייה';

  @override
  String get noFoldersAvailable => 'אין תיקיות זמינות';

  @override
  String get newFolder => 'תיקייה חדשה';

  @override
  String get color => 'צבע';

  @override
  String get waitingForDevice => 'מחכה להתקן...';

  @override
  String get saySomething => 'אמור משהו...';

  @override
  String get initialisingSystemAudio => 'אתחול אודיו מערכת';

  @override
  String get stopRecording => 'עצור הקלטה';

  @override
  String get continueRecording => 'המשך הקלטה';

  @override
  String get initialisingRecorder => 'אתחול מקליט';

  @override
  String get pauseRecording => 'השהה הקלטה';

  @override
  String get resumeRecording => 'חזור להקלטה';

  @override
  String get noDailyRecapsYet => 'אין סיכומים יומיים עדיין';

  @override
  String get dailyRecapsDescription => 'הסיכומים היומיים שלך יופיעו כאן לאחר שייווצרו';

  @override
  String get chooseTransferMethod => 'בחר שיטת העברה';

  @override
  String get fastTransferSpeed => '~150 KB/s דרך WiFi';

  @override
  String largeTimeGapDetected(String gap) {
    return 'נמצא פער זמן גדול ($gap)';
  }

  @override
  String largeTimeGapsDetected(String gaps) {
    return 'נמצאו פערי זמן גדולים ($gaps)';
  }

  @override
  String get deviceDoesNotSupportWifiSwitchingToBle => 'ההתקן אינו תומך בסנכרון WiFi, מעבר ל-Bluetooth';

  @override
  String get appleHealthNotAvailable => 'Apple Health אינו זמין בהתקן זה';

  @override
  String get downloadAudio => 'הורד אודיו';

  @override
  String get audioDownloadSuccess => 'אודיו הורד בהצלחה';

  @override
  String get audioDownloadFailed => 'כישלון בהורדת אודיו';

  @override
  String get downloadingAudio => 'הורדת אודיו...';

  @override
  String get shareAudio => 'שתף אודיו';

  @override
  String get preparingAudio => 'הכנת אודיו';

  @override
  String get gettingAudioFiles => 'קבלת קבצי אודיו...';

  @override
  String get downloadingAudioProgress => 'הורדת אודיו';

  @override
  String get processingAudio => 'עיבוד אודיו';

  @override
  String get combiningAudioFiles => 'שילוב קבצי אודיו...';

  @override
  String get audioReady => 'אודיו מוכן';

  @override
  String get openingShareSheet => 'פתיחת גיליון שתיפוי...';

  @override
  String get audioShareFailed => 'שתיפוי נכשל';

  @override
  String get dailyRecaps => 'סיכומים יומיים';

  @override
  String get removeFilter => 'הסר מסנן';

  @override
  String get categoryConversationAnalysis => 'ניתוח שיחות';

  @override
  String get categoryHealth => 'בריאות';

  @override
  String get categoryEducation => 'חינוך';

  @override
  String get categoryCommunication => 'תקשורת';

  @override
  String get categoryEmotionalSupport => 'תמיכה רגשית';

  @override
  String get categoryProductivity => 'פרודוקטיביות';

  @override
  String get categoryEntertainment => 'בידור';

  @override
  String get categoryFinancial => 'פיננסי';

  @override
  String get categoryTravel => 'נסיעות';

  @override
  String get categorySafety => 'בטיחות';

  @override
  String get categoryShopping => 'קניות';

  @override
  String get categorySocial => 'חברתי';

  @override
  String get categoryNews => 'חדשות';

  @override
  String get categoryUtilities => 'כלים שימושיים';

  @override
  String get categoryOther => 'אחר';

  @override
  String get capabilityChat => 'צ\'אט';

  @override
  String get capabilityConversations => 'שיחות';

  @override
  String get capabilityExternalIntegration => 'אינטגרציה חיצונית';

  @override
  String get capabilityNotification => 'התראה';

  @override
  String get triggerAudioBytes => 'בתים אודיו';

  @override
  String get triggerConversationCreation => 'יצירת שיחה';

  @override
  String get triggerTranscriptProcessed => 'תמלול מעובד';

  @override
  String get actionCreateConversations => 'יצור שיחות';

  @override
  String get actionCreateMemories => 'יצור זיכרונות';

  @override
  String get actionReadConversations => 'קרא שיחות';

  @override
  String get actionReadMemories => 'קרא זיכרונות';

  @override
  String get actionReadTasks => 'קרא משימות';

  @override
  String get scopeUserName => 'שם משתמש';

  @override
  String get scopeUserFacts => 'עובדות משתמש';

  @override
  String get scopeUserConversations => 'שיחות משתמש';

  @override
  String get scopeUserChat => 'צ\'אט משתמש';

  @override
  String get capabilitySummary => 'סיכום';

  @override
  String get capabilityFeatured => 'בדוגיות';

  @override
  String get capabilityTasks => 'משימות';

  @override
  String get capabilityIntegrations => 'אינטגרציות';

  @override
  String get categoryProductivityLifestyle => 'פרודוקטיביות ואורח חיים';

  @override
  String get categorySocialEntertainment => 'חברתי ובידור';

  @override
  String get categoryProductivityTools => 'פרודוקטיביות וכלים';

  @override
  String get categoryPersonalWellness => 'אישי וחיים';

  @override
  String get rating => 'דירוג';

  @override
  String get categories => 'קטגוריות';

  @override
  String get sortBy => 'מיין לפי';

  @override
  String get highestRating => 'דירוג הגבוה ביותר';

  @override
  String get lowestRating => 'דירוג הנמוך ביותר';

  @override
  String get resetFilters => 'אפס מסננים';

  @override
  String get applyFilters => 'החל מסננים';

  @override
  String get mostInstalls => 'הכי מותקן';

  @override
  String get couldNotOpenUrl => 'לא היתה אפשרות לפתוח את הקישור. נסה שוב.';

  @override
  String get newTask => 'משימה חדשה';

  @override
  String get viewAll => 'צפה בהכל';

  @override
  String get addTask => 'הוסף משימה';

  @override
  String get addMcpServer => 'הוסף שרת MCP';

  @override
  String get connectExternalAiTools => 'חבר כלים AI חיצוניים';

  @override
  String get mcpServerUrl => 'כתובת URL של שרת MCP';

  @override
  String mcpServerConnected(int count) {
    return '$count כלים התחברו בהצלחה';
  }

  @override
  String get mcpConnectionFailed => 'חיבור לשרת MCP נכשל';

  @override
  String get authorizingMcpServer => 'מאשר...';

  @override
  String get whereDidYouHearAboutOmi => 'איך גילית את Omi?';

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
  String get friendWordOfMouth => 'חבר';

  @override
  String get otherSource => 'אחר';

  @override
  String get pleaseSpecify => 'אנא ציין';

  @override
  String get event => 'אירוע';

  @override
  String get coworker => 'עמית';

  @override
  String get linkedIn => 'LinkedIn';

  @override
  String get appStore => 'App Store';

  @override
  String get googleSearch => 'חיפוש Google';

  @override
  String get audioPlaybackUnavailable => 'קובץ אודיו אינו זמין להשמעה';

  @override
  String get audioPlaybackFailed => 'לא היתה אפשרות להשמיע אודיו. ייתכן שהקובץ פגום או חסר.';

  @override
  String get connectionGuide => 'מדריך חיבור';

  @override
  String get iveDoneThis => 'עשיתי זאת';

  @override
  String get pairNewDevice => 'חבר התקן חדש';

  @override
  String get dontSeeYourDevice => 'לא רואה את ההתקן שלך?';

  @override
  String get reportAnIssue => 'דווח על בעיה';

  @override
  String get pairingTitleOmi => 'הפעל את Omi';

  @override
  String get pairingDescOmi => 'לחץ וחזיק על ההתקן עד שהוא רועד כדי להפעיל אותו.';

  @override
  String get pairingTitleOmiDevkit => 'הכנס את Omi DevKit למצב זיווג';

  @override
  String get pairingDescOmiDevkit => 'לחץ על הכפתור פעם אחת כדי להפעיל. ה-LED יהבהב בסגול כשהוא במצב זיווג.';

  @override
  String get pairingTitleOmiGlass => 'הפעל את Omi Glass';

  @override
  String get pairingDescOmiGlass => 'הפעל על ידי לחיצה על הכפתור הצדדי לשך 3 שניות.';

  @override
  String get pairingTitlePlaudNote => 'הכנס את Plaud Note למצב זיווג';

  @override
  String get pairingDescPlaudNote => 'לחץ וחזיק את הכפתור הצדדי לשך 2 שניות. ה-LED האדום יהבהב כשהוא מוכן לזיווג.';

  @override
  String get pairingTitleBee => 'הכנס את Bee למצב זיווג';

  @override
  String get pairingDescBee => 'לחץ על הכפתור 5 פעמים ברצף. האור יתחיל להבהב בכחול וירוק.';

  @override
  String get pairingTitleLimitless => 'הכנס את Limitless למצב זיווג';

  @override
  String get pairingDescLimitless =>
      'כאשר אור כלשהו נראה, לחץ פעם אחת ואז לחץ וחזיק עד שההתקן מראה אור ורוד, ואז שחרר.';

  @override
  String get pairingTitleFriendPendant => 'הכנס את Friend Pendant למצב זיווג';

  @override
  String get pairingDescFriendPendant => 'לחץ על הכפתור על התליון כדי להפעיל אותו. הוא יכנס למצב זיווג באופן אוטומטי.';

  @override
  String get pairingTitleFieldy => 'הכנס את Fieldy למצב זיווג';

  @override
  String get pairingDescFieldy => 'לחץ וחזיק על ההתקן עד שהאור מופיע כדי להפעיל אותו.';

  @override
  String get pairingTitleAppleWatch => 'חבר Apple Watch';

  @override
  String get pairingDescAppleWatch => 'התקן ופתח את אפליקציית Omi ב-Apple Watch שלך, לאחר מכן הקש על חיבור באפליקציה.';

  @override
  String get pairingTitleNeoOne => 'הכנס את Neo One למצב זיווג';

  @override
  String get pairingDescNeoOne => 'לחץ וחזיק את כפתור ההפעלה עד שה-LED הבהב. ההתקן יהיה ניתן גילוי.';

  @override
  String get downloadingFromDevice => 'הורד מהתקן';

  @override
  String get reconnectingToInternet => 'התחברות מחדש לאינטרנט...';

  @override
  String uploadingToCloud(int current, int total) {
    return 'מעלה $current מתוך $total';
  }

  @override
  String get processingOnServer => 'מעבד בשרת...';

  @override
  String processingOnServerProgress(int current, int total) {
    return 'מעבד... $current/$total קטעים';
  }

  @override
  String get processedStatus => 'מעובד';

  @override
  String get corruptedStatus => 'פגום';

  @override
  String nPending(int count) {
    return '$count בהמתנה';
  }

  @override
  String nProcessed(int count) {
    return '$count מעובד';
  }

  @override
  String get synced => 'סונכרן';

  @override
  String get noPendingRecordings => 'אין הקלטות בהמתנה';

  @override
  String get noProcessedRecordings => 'עדיין אין הקלטות מעובדות';

  @override
  String get pending => 'בהמתנה';

  @override
  String whatsNewInVersion(String version) {
    return 'חדש בגרסה $version';
  }

  @override
  String get addToYourTaskList => 'הוסף לרשימת המשימות שלך?';

  @override
  String get failedToCreateShareLink => 'פעולת יצירת קישור שיתוף נכשלה';

  @override
  String get deleteGoal => 'מחק יעד';

  @override
  String get deviceUpToDate => 'ההתקן שלך עדכני';

  @override
  String get wifiConfiguration => 'תצורת WiFi';

  @override
  String get wifiConfigurationSubtitle => 'הזן את אישורי ה-WiFi שלך כדי לאפשר להתקן להוריד את ה-firmware.';

  @override
  String get networkNameSsid => 'שם רשת (SSID)';

  @override
  String get enterWifiNetworkName => 'הזן שם רשת WiFi';

  @override
  String get enterWifiPassword => 'הזן סיסמת WiFi';

  @override
  String get appIconLabel => 'אייקון אפליקציה';

  @override
  String get onboardingWhatIKnowAboutYouTitle => 'זה מה שאני יודע עלייך';

  @override
  String get onboardingWhatIKnowAboutYouDescription => 'מפה זו מתעדכנת כש-Omi לומד מהשיחות שלך.';

  @override
  String get apiEnvironment => 'סביבת API';

  @override
  String get apiEnvironmentDescription => 'בחר איזו backend להתחבר אליה';

  @override
  String get production => 'ייצור';

  @override
  String get staging => 'שלב בדיקה';

  @override
  String get switchRequiresRestart => 'שינוי דורש אתחול אפליקציה';

  @override
  String get switchApiConfirmTitle => 'שנה סביבת API';

  @override
  String switchApiConfirmBody(String environment) {
    return 'לעבור ל-$environment? תצטרך לסגור ולפתוח מחדש את האפליקציה כדי שהשינויים יכנסו לתוקף.';
  }

  @override
  String get switchAndRestart => 'שנה';

  @override
  String get stagingDisclaimer =>
      'שלב בדיקה עלול להיות בעל באגים, ביצועים לא עקביים, וניתן שיאבדו נתונים. השתמש רק לבדיקה.';

  @override
  String get apiEnvSavedRestartRequired => 'נשמר. סגור ופתח מחדש את האפליקציה כדי להחיל.';

  @override
  String get shared => 'משותף';

  @override
  String get onlyYouCanSeeConversation => 'רק אתה יכול לראות שיחה זו';

  @override
  String get anyoneWithLinkCanView => 'כל אחד עם הקישור יכול לצפות';

  @override
  String get tasksCleanTodayTitle => 'ניקוי משימות של היום?';

  @override
  String get tasksCleanTodayMessage => 'זה יסיר רק את ההגעות';

  @override
  String get tasksOverdue => '逾期';

  @override
  String get phoneCallsWithOmi => 'שיחות טלפון עם Omi';

  @override
  String get phoneCallsSubtitle => 'השתמש בשיחות עם תמלול בזמן אמת';

  @override
  String get phoneSetupStep1Title => 'אמת את מספר הטלפון שלך';

  @override
  String get phoneSetupStep1Subtitle => 'נתקשר אליך כדי לאשר שזה שלך';

  @override
  String get phoneSetupStep2Title => 'הזן קוד אימות';

  @override
  String get phoneSetupStep2Subtitle => 'קוד קצר שתקליד בשיחה';

  @override
  String get phoneSetupStep3Title => 'התחל להתקשר לאנשי הקשר שלך';

  @override
  String get phoneSetupStep3Subtitle => 'עם תמלול בזמן אמת מובנה';

  @override
  String get phoneGetStarted => 'התחל';

  @override
  String get callRecordingConsentDisclaimer => 'הקלטת שיחה עלולה לדרוש הסכמה בתחום המשפטי שלך';

  @override
  String get enterYourNumber => 'הזן את המספר שלך';

  @override
  String get phoneNumberCallerIdHint => 'לאחר אימות, זה הופך לזהות המתקשר שלך';

  @override
  String get phoneNumberHint => 'מספר טלפון';

  @override
  String get failedToStartVerification => 'אימות התחיל נכשל';

  @override
  String get phoneContinue => 'המשך';

  @override
  String get verifyYourNumber => 'אמת את המספר שלך';

  @override
  String get answerTheCallFrom => 'ענה על השיחה מ-';

  @override
  String get onTheCallEnterThisCode => 'בשיחה, הזן את הקוד הזה';

  @override
  String get followTheVoiceInstructions => 'עקוב אחר הוראות הקול';

  @override
  String get statusCalling => 'קורא...';

  @override
  String get statusCallInProgress => 'שיחה בעיצומה';

  @override
  String get statusVerifiedLabel => 'אומת';

  @override
  String get statusCallMissed => 'שיחה החמיצה';

  @override
  String get statusTimedOut => 'פג תוקף';

  @override
  String get phoneTryAgain => 'נסה שוב';

  @override
  String get phonePageTitle => 'טלפון';

  @override
  String get phoneContactsTab => 'אנשי קשר';

  @override
  String get phoneKeypadTab => 'מקלדת מספרים';

  @override
  String get grantContactsAccess => 'הענק גישה לאנשי הקשר שלך';

  @override
  String get phoneAllow => 'אפשר';

  @override
  String get phoneSearchHint => 'חיפוש';

  @override
  String get phoneNoContactsFound => 'לא נמצאו אנשי קשר';

  @override
  String get phoneEnterNumber => 'הזן מספר';

  @override
  String get failedToStartCall => 'התחלת שיחה נכשלה';

  @override
  String get callStateConnecting => 'התחברות...';

  @override
  String get callStateRinging => 'צלצול...';

  @override
  String get callStateEnded => 'השיחה הסתיימה';

  @override
  String get callStateFailed => 'השיחה נכשלה';

  @override
  String get transcriptPlaceholder => 'תמלול יופיע כאן...';

  @override
  String get phoneUnmute => 'הפעל קול';

  @override
  String get phoneMute => 'השתק קול';

  @override
  String get phoneSpeaker => 'רמקול';

  @override
  String get phoneEndCall => 'סיים';

  @override
  String get phoneCallSettingsTitle => 'הגדרות שיחות טלפון';

  @override
  String get showPhoneCallButtonTitle => 'הצג כפתור שיחת טלפון';

  @override
  String get showPhoneCallButtonDesc => 'הצג כפתור שיחת טלפון במסך הבית';

  @override
  String get yourVerifiedNumbers => 'המספרים המאומתים שלך';

  @override
  String get verifiedNumbersDescription => 'כאשר אתה מתקשר למישהו, הם יראו את המספר הזה בטלפון שלהם';

  @override
  String get noVerifiedNumbers => 'אין מספרים מאומתים';

  @override
  String deletePhoneNumberConfirm(String phoneNumber) {
    return 'מחק $phoneNumber?';
  }

  @override
  String get deletePhoneNumberWarning => 'תצטרך לאמת שוב כדי לבצע שיחות';

  @override
  String get phoneDeleteButton => 'מחק';

  @override
  String verifiedMinutesAgo(int minutes) {
    return 'אומת לפני $minutes דקות';
  }

  @override
  String verifiedHoursAgo(int hours) {
    return 'אומת לפני $hours שעות';
  }

  @override
  String verifiedDaysAgo(int days) {
    return 'אומת לפני $days ימים';
  }

  @override
  String verifiedOnDate(String date) {
    return 'אומת בתאריך $date';
  }

  @override
  String get verifiedFallback => 'אומת';

  @override
  String get callAlreadyInProgress => 'שיחה כבר בעיצומה';

  @override
  String get failedToGetCallToken => 'כישלון בקבלת טוקן שיחה. אמת את מספר הטלפון שלך תחילה.';

  @override
  String get failedToInitializeCallService => 'כישלון בהאתחלת שירות שיחה';

  @override
  String get speakerLabelYou => 'אתה';

  @override
  String get speakerLabelUnknown => 'לא ידוע';

  @override
  String get showDailyScoreOnHomepage => 'הצג ניקוד יומי בעמוד הבית';

  @override
  String get showTasksOnHomepage => 'הצג משימות בעמוד הבית';

  @override
  String get phoneCallsUnlimitedOnly => 'שיחות טלפון דרך Omi';

  @override
  String get phoneCallsUpsellSubtitle =>
      'בצע שיחות דרך Omi וקבל תמלול בזמן אמת, סיכומים אוטומטיים ועוד. זמין אך ורק למנויי תוכנית Unlimited.';

  @override
  String get phoneCallsUpsellFeature1 => 'תמלול בזמן אמת של כל שיחה';

  @override
  String get phoneCallsUpsellFeature2 => 'סיכומי שיחות וקבצי פעולה אוטומטיים';

  @override
  String get phoneCallsUpsellFeature3 => 'מקבלים רואים את המספר האמיתי שלך, לא אחד אקראי';

  @override
  String get phoneCallsUpsellFeature4 => 'השיחות שלך נשמרות פרטיות ובטוחות';

  @override
  String get phoneCallsUpgradeButton => 'שדרג ל-Unlimited';

  @override
  String get phoneCallsMaybeLater => 'אולי מאוחר יותר';

  @override
  String get deleteSynced => 'מחק מסונכרן';

  @override
  String get deleteSyncedFiles => 'מחק הקלטות מסונכרנות';

  @override
  String get deleteSyncedFilesMessage => 'הקלטות אלה כבר סונכרנו לטלפון שלך. לא ניתן לבטל פעולה זו.';

  @override
  String get syncedFilesDeleted => 'הקלטות מסונכרנות נמחקו';

  @override
  String get deletePending => 'מחק בהמתנה';

  @override
  String get deletePendingFiles => 'מחק הקלטות בהמתנה';

  @override
  String get deletePendingFilesWarning => 'הקלטות אלה לא סונכרנו לטלפון שלך ויאבדו לצמיתות. לא ניתן לבטל פעולה זו.';

  @override
  String get pendingFilesDeleted => 'הקלטות בהמתנה נמחקו';

  @override
  String get deleteAllFiles => 'מחק את כל ההקלטות';

  @override
  String get deleteAll => 'מחק הכל';

  @override
  String get deleteAllFilesWarning =>
      'זה ימחק הן הקלטות מסונכרנות והן בהמתנה. הקלטות בהמתנה לא סונכרנו ויאבדו לצמיתות. לא ניתן לבטל פעולה זו.';

  @override
  String get allFilesDeleted => 'כל ההקלטות נמחקו';

  @override
  String nFiles(int count) {
    return '$count הקלטות';
  }

  @override
  String get manageStorage => 'נהל אחסון';

  @override
  String get safelyBackedUp => 'גיבוי בטוח בטלפון שלך';

  @override
  String get notYetSynced => 'עדיין לא סונכרן לטלפון שלך';

  @override
  String get clearAll => 'נקה הכל';

  @override
  String get phoneKeypad => 'מקלדת מספרים';

  @override
  String get phoneHideKeypad => 'הסתר מקלדת מספרים';

  @override
  String get fairUsePolicy => 'שימוש הוגן';

  @override
  String get fairUseLoadError => 'לא היתה אפשרות לטעון את מצב השימוש ההוגן. אנא נסה שוב.';

  @override
  String get fairUseStatusNormal => 'השימוש שלך בטווח עד הגבול הרגיל.';

  @override
  String get fairUseStageNormal => 'רגיל';

  @override
  String get fairUseStageWarning => 'אזהרה';

  @override
  String get fairUseStageThrottle => 'מעוכב';

  @override
  String get fairUseStageRestrict => 'מוגבל';

  @override
  String get fairUseSpeechUsage => 'שימוש בדיבור';

  @override
  String get fairUseToday => 'היום';

  @override
  String get fairUse3Day => '3 ימים מתגלגל';

  @override
  String get fairUseWeekly => 'שבוע מתגלגל';

  @override
  String get fairUseAboutTitle => 'אודות שימוש הוגן';

  @override
  String get fairUseAboutBody =>
      'Omi מעוצב לשיחות אישיות, פגישות ואינטראקציות חיות. השימוש נמדד לפי זמן דיבור אמיתי שזוהה, לא זמן חיבור. אם השימוש חורג משמעותית מדפוסים רגילים לתוכן שאינו אישי, ייתכנו התאמות.';

  @override
  String fairUseCaseRefCopied(String caseRef) {
    return '$caseRef הועתק';
  }

  @override
  String get fairUseDailyTranscription => 'תמלול יומי';

  @override
  String fairUseBudgetUsed(String used, String limit) {
    return '${used}m / ${limit}m';
  }

  @override
  String get fairUseBudgetExhausted => 'הגבול היומי של התמלול הושג';

  @override
  String fairUseBudgetResetsAt(String time) {
    return 'מתאפס $time';
  }

  @override
  String get transcriptionPaused => 'הקלטה, התחברות מחדש';

  @override
  String get transcriptionPausedReconnecting => 'עדיין מקליט — התחברות מחדש לתמלול...';

  @override
  String fairUseBannerStatus(String status) {
    return 'שימוש הוגן: $status';
  }

  @override
  String get improveConnectionTitle => 'שפר חיבור';

  @override
  String get improveConnectionContent =>
      'שיפרנו את אופן החיבור של Omi להתקן שלך. כדי להפעיל זאת, אנא עבור לעמוד פרטי ההתקן, הקש על \"ניתוק התקן\", ואז חבר את ההתקן שלך שוב.';

  @override
  String get improveConnectionAction => 'הבנתי';

  @override
  String clockSkewWarning(int minutes) {
    return 'שעון ההתקן שלך מופקע ב-~$minutes דקות. בדוק את הגדרות התאריך והשעה שלך.';
  }

  @override
  String get omisStorage => 'אחסון של Omi';

  @override
  String get phoneStorage => 'אחסון טלפון';

  @override
  String get cloudStorage => 'אחסון ענן';

  @override
  String get howSyncingWorks => 'איך הסנכרון עובד';

  @override
  String get noSyncedRecordings => 'עדיין אין הקלטות מסונכרנות';

  @override
  String get recordingsSyncAutomatically => 'הקלטות מסתנכרנות באופן אוטומטי — לא נדרשת פעולה.';

  @override
  String get filesDownloadedUploadedNextTime => 'קבצים שכבר הורדו יועלו בפעם הבאה.';

  @override
  String nConversationsCreated(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 's',
      one: '',
    );
    return '$count conversation$_temp0 created';
  }

  @override
  String get tapToView => 'הקש כדי להציג';

  @override
  String get syncFailed => 'הסנכרון נכשל';

  @override
  String get keepSyncing => 'המשך סנכרון';

  @override
  String get cancelSyncQuestion => 'בטל סנכרון?';

  @override
  String get omisStorageDesc =>
      'כאשר ה-Omi שלך לא מחובר לטלפון, הוא מאחסן אודיו מקומית בזיכרון המובנה שלו. אתה לעולם לא מאבד הקלטה.';

  @override
  String get phoneStorageDesc =>
      'כאשר Omi מתחבר מחדש, הקלטות מועברות באופן אוטומטי לטלפון שלך כאזור החזקה זמני לפני העלאה.';

  @override
  String get cloudStorageDesc => 'לאחר העלאה, ההקלטות שלך מעובדות ותמלולות. שיחות יהיו זמינות תוך דקה.';

  @override
  String get tipKeepPhoneNearby => 'שמור את הטלפון שלך בקרבת מקום לסנכרון מהיר יותר';

  @override
  String get tipStableInternet => 'אינטרנט יציב מאיץ העלאות לענן';

  @override
  String get tipAutoSync => 'הקלטות מסתנכרנות באופן אוטומטי';

  @override
  String get storageSection => 'אחסון';

  @override
  String get permissions => 'הרשאות';

  @override
  String get permissionEnabled => 'מופעל';

  @override
  String get permissionEnable => 'הפעל';

  @override
  String get permissionsPageDescription =>
      'הרשאות אלה הן ליבה לאופן ה-Omi. הן מאפשרות תכונות חיוניות כמו הודעות, חוויות מבוססות מיקום והילוכי אודיו.';

  @override
  String get permissionsRequiredDescription => 'Omi זקוק לכמה הרשאות כדי לפעול כראוי. אנא הענק אותן כדי להמשיך.';

  @override
  String get permissionsSetupTitle => 'קבל את החוויה הטובה ביותר';

  @override
  String get permissionsSetupDescription => 'הפעל כמה הרשאות כדי ש-Omi יוכל לעשות הקסם שלו.';

  @override
  String get permissionsChangeAnytime => 'אתה יכול לשנות את אלה בכל עת בהגדרות > הרשאות';

  @override
  String get location => 'מיקום';

  @override
  String get microphone => 'מיקרופון';

  @override
  String get whyAreYouCanceling => 'למה אתה מבטל?';

  @override
  String get cancelReasonSubtitle => 'אתה יכול להגיד לנו למה אתה עוזב?';

  @override
  String get cancelReasonTooExpensive => 'יקר מדי';

  @override
  String get cancelReasonNotUsing => 'לא משתמש בו מספיק';

  @override
  String get cancelReasonMissingFeatures => 'תכונות חסרות';

  @override
  String get cancelReasonAudioQuality => 'איכות אודיו/תמלול';

  @override
  String get cancelReasonBatteryDrain => 'חששות מדריקת סוללה';

  @override
  String get cancelReasonFoundAlternative => 'מצא חלופה';

  @override
  String get cancelReasonOther => 'אחר';

  @override
  String get tellUsMore => 'ספר לנו עוד (אופציונלי)';

  @override
  String get cancelReasonDetailHint => 'אנחנו מעריכים כל משוב...';

  @override
  String get justAMoment => 'רגע בלבד';

  @override
  String get cancelConsequencesSubtitle => 'אנחנו ממליצים בחום לחקור את האפשרויות האחרות שלך במקום לבטל.';

  @override
  String cancelBillingPeriodInfo(String date) {
    return 'התוכנית שלך תישאר פעילה עד $date. אחרי זה, תועבר לגרסה חינם עם תכונות מוגבלות.';
  }

  @override
  String get ifYouCancel => 'אם אתה מבטל:';

  @override
  String get cancelConsequenceNoAccess => 'לא יהיה לך גישה unlimited בסוף תקופת החיוב שלך.';

  @override
  String get cancelConsequenceBattery => '7x יותר שימוש בסוללה (עיבוד התקן)';

  @override
  String get cancelConsequenceQuality => '30% איכות תמלול נמוכה יותר (מודלים התקן)';

  @override
  String get cancelConsequenceDelay => 'עיכוב עיבוד של 5-7 שניות (מודלים התקן)';

  @override
  String get cancelConsequenceSpeakers => 'לא יכול לזהות דוברים.';

  @override
  String get confirmAndCancel => 'אשר וביטול';

  @override
  String get cancelConsequencePhoneCalls => 'אין תמלול שיחות טלפון בזמן אמת';

  @override
  String get feedbackTitleTooExpensive => 'איזה מחיר יעבוד לך?';

  @override
  String get feedbackTitleMissingFeatures => 'איזה תכונות אתה משיג?';

  @override
  String get feedbackTitleAudioQuality => 'אילו בעיות היו לך?';

  @override
  String get feedbackTitleBatteryDrain => 'ספר לנו על בעיות הסוללה';

  @override
  String get feedbackTitleFoundAlternative => 'למה אתה עובר?';

  @override
  String get feedbackTitleNotUsing => 'מה יגרום לך להשתמש ב-Omi יותר?';

  @override
  String get feedbackSubtitleTooExpensive => 'המשוב שלך עוזר לנו למצוא את האיזון הנכון.';

  @override
  String get feedbackSubtitleMissingFeatures => 'אנחנו תמיד בונים — זה עוזר לנו לעדכן עדיפויות.';

  @override
  String get feedbackSubtitleAudioQuality => 'היינו רוצים להבין מה השתבש.';

  @override
  String get feedbackSubtitleBatteryDrain => 'זה עוזר לצוות החומרה שלנו להשתפר.';

  @override
  String get feedbackSubtitleFoundAlternative => 'היינו רוצים ללמוד מה תפסת את עיניך.';

  @override
  String get feedbackSubtitleNotUsing => 'אנחנו רוצים להפוך את Omi לשימושי יותר עבורך.';

  @override
  String get deviceDiagnostics => 'אבחון התקן';

  @override
  String get signalStrength => 'עוצמת אות';

  @override
  String get connectionUptime => 'זמן עבודה';

  @override
  String get reconnections => 'התחברויות מחדש';

  @override
  String get disconnectHistory => 'היסטוריית ניתוקים';

  @override
  String get noDisconnectsRecorded => 'אין ניתוקים רשומים';

  @override
  String get diagnostics => 'אבחון';

  @override
  String get waitingForData => 'בהמתנה לנתונים...';

  @override
  String get liveRssiOverTime => 'RSSI חי על פני זמן';

  @override
  String get noRssiDataYet => 'אין נתוני RSSI עדיין';

  @override
  String get collectingData => 'אוסף נתונים...';

  @override
  String get cleanDisconnect => 'ניתוק נקי';

  @override
  String get connectionTimeout => 'פג זמן ההחיבור';

  @override
  String get remoteDeviceTerminated => 'ההתקן המרוחק הופסק';

  @override
  String get pairedToAnotherPhone => 'מזוונו לטלפון אחר';

  @override
  String get linkKeyMismatch => 'חוסר התאמה במפתח קישור';

  @override
  String get connectionFailed => 'חיבור נכשל';

  @override
  String get appClosed => 'אפליקציה סגורה';

  @override
  String get manualDisconnect => 'ניתוק ידני';

  @override
  String lastNEvents(int count) {
    return '$count אירועים אחרונים';
  }

  @override
  String get signal => 'אות';

  @override
  String get battery => 'סוללה';

  @override
  String get excellent => 'מעולה';

  @override
  String get good => 'טוב';

  @override
  String get fair => 'סביר';

  @override
  String get weak => 'חלש';

  @override
  String gattError(String code) {
    return 'שגיאת GATT ($code)';
  }

  @override
  String get batteryHistory => 'סוללה';

  @override
  String get noBatteryDataYet => 'אין עדיין נתוני סוללה';

  @override
  String get day => 'יום';

  @override
  String get week => 'שבוע';

  @override
  String get rollbackToStableFirmware => 'חזור ל-Firmware יציב';

  @override
  String get rollbackConfirmTitle => 'חזור ל-Firmware?';

  @override
  String rollbackConfirmMessage(String version) {
    return 'זה יחליף את ה-firmware הנוכחי שלך בגרסה היציבה העדכנית ($version). ההתקן שלך יתחיל מחדש לאחר העדכון.';
  }

  @override
  String get stableFirmware => 'Firmware יציב';

  @override
  String get fetchingStableFirmware => 'מביא את ה-firmware היציב העדכני ביותר...';

  @override
  String get noStableFirmwareFound => 'לא הצלחנו למצוא גרסת firmware יציבה להתקן שלך.';

  @override
  String get installStableFirmware => 'התקן Firmware יציב';

  @override
  String get alreadyOnStableFirmware => 'אתה כבר בגרסה היציבה העדכנית.';

  @override
  String audioSavedLocally(String duration) {
    return '$duration אודיו נשמר מקומית';
  }

  @override
  String get willSyncAutomatically => 'יסתנכרן באופן אוטומטי';

  @override
  String get enableLocationTitle => 'הפעל מיקום';

  @override
  String get enableLocationDescription => 'הרשאת מיקום נדרשת כדי למצוא התקני Bluetooth בקרבת מקום.';

  @override
  String get voiceRecordingFound => 'הקלטה נמצאה';

  @override
  String get transcriptionConnecting => 'חיבור תמלול...';

  @override
  String get transcriptionReconnecting => 'התחברות מחדש לתמלול...';

  @override
  String get transcriptionUnavailable => 'תמלול לא זמין';

  @override
  String get audioOutput => 'פלט אודיו';

  @override
  String get firmwareWarningTitle => 'חשוב: קראו לפני העדכון';

  @override
  String get firmwareFormatWarning =>
      'קושחה זו תפרמט את כרטיס ה-SD. אנא ודאו שכל הנתונים הלא מקוונים מסונכרנים לפני השדרוג.\n\nאם אתם רואים אור אדום מהבהב לאחר התקנת גרסה זו, אל תדאגו. פשוט חברו את המכשיר לאפליקציה והוא אמור להפוך לכחול. האור האדום אומר שהשעון של המכשיר עדיין לא סונכרן.';

  @override
  String get continueAnyway => 'המשך';

  @override
  String get tasksClearCompleted => 'נקה גמורים';

  @override
  String get tasksSelectAll => 'בחר הכל';

  @override
  String tasksDeleteSelected(int count) {
    return 'מחק $count משימה(ות)';
  }

  @override
  String get tasksMarkComplete => 'סומן כהושלם';

  @override
  String get appleHealthManageNote =>
      'Omi ניגש ל-Apple Health דרך מסגרת העבודה HealthKit של Apple. ניתן לבטל את הגישה בכל עת בהגדרות iOS.';

  @override
  String get appleHealthConnectCta => 'התחבר ל-Apple Health';

  @override
  String get appleHealthDisconnectCta => 'נתק את Apple Health';

  @override
  String get appleHealthConnectedBadge => 'מחובר';

  @override
  String get appleHealthFeatureChatTitle => 'צ\'אט על הבריאות שלך';

  @override
  String get appleHealthFeatureChatDesc => 'שאל את Omi על הצעדים, השינה, הדופק והאימונים שלך.';

  @override
  String get appleHealthFeatureReadOnlyTitle => 'גישת קריאה בלבד';

  @override
  String get appleHealthFeatureReadOnlyDesc => 'Omi לעולם לא כותב ל-Apple Health ולא משנה את הנתונים שלך.';

  @override
  String get appleHealthFeatureSecureTitle => 'סנכרון מאובטח';

  @override
  String get appleHealthFeatureSecureDesc => 'נתוני Apple Health שלך מסונכרנים באופן פרטי לחשבון Omi.';

  @override
  String get appleHealthDeniedTitle => 'הגישה ל-Apple Health נדחתה';

  @override
  String get appleHealthDeniedBody =>
      'ל-Omi אין הרשאה לקרוא את נתוני Apple Health שלך. הפעל אותה בהגדרות iOS ← פרטיות ואבטחה ← Health ← Omi.';

  @override
  String get deleteFlowReasonTitle => 'למה אתה עוזב?';

  @override
  String get deleteFlowReasonSubtitle => 'המשוב שלך עוזר לנו לשפר את Omi עבור כולם.';

  @override
  String get deleteReasonPrivacy => 'חששות פרטיות';

  @override
  String get deleteReasonNotUsing => 'לא משתמש בו מספיק';

  @override
  String get deleteReasonMissingFeatures => 'חסרות תכונות שאני צריך';

  @override
  String get deleteReasonTechnicalIssues => 'יותר מדי בעיות טכניות';

  @override
  String get deleteReasonFoundAlternative => 'משתמש במשהו אחר';

  @override
  String get deleteReasonTakingBreak => 'סתם לוקח הפסקה';

  @override
  String get deleteReasonOther => 'אחר';

  @override
  String get deleteFlowFeedbackTitle => 'ספר לנו עוד';

  @override
  String get deleteFlowFeedbackSubtitle => 'מה היה גורם ל-Omi לעבוד עבורך?';

  @override
  String get deleteFlowFeedbackHint => 'אופציונלי — המחשבות שלך עוזרות לנו לבנות מוצר טוב יותר.';

  @override
  String get deleteFlowConfirmTitle => 'זה לצמיתות';

  @override
  String get deleteFlowConfirmSubtitle => 'לאחר מחיקת החשבון, אין דרך לשחזר אותו.';

  @override
  String get deleteConsequenceSubscription => 'כל מנוי פעיל יבוטל.';

  @override
  String get deleteConsequenceNoRecovery => 'לא ניתן לשחזר את החשבון שלך — אפילו לא על ידי התמיכה.';

  @override
  String get deleteTypeToConfirm => 'הקלד DELETE לאישור';

  @override
  String get deleteConfirmationWord => 'DELETE';

  @override
  String get deleteAccountPermanently => 'מחק חשבון לצמיתות';

  @override
  String get keepMyAccount => 'שמור על החשבון שלי';

  @override
  String get deleteAccountFailed => 'לא ניתן היה למחוק את החשבון שלך. נסה שוב.';

  @override
  String get planUpdate => 'עדכון תוכנית';

  @override
  String get planDeprecationMessage =>
      'תוכנית ה-Unlimited שלך מופסקת. עברו לתוכנית Operator — אותן תכונות מעולות ב-\$49/חודש. התוכנית הנוכחית שלך תמשיך לפעול בינתיים.';

  @override
  String get upgradeYourPlan => 'שדרג את התוכנית שלך';

  @override
  String get youAreOnAPaidPlan => 'אתה על תוכנית בתשלום.';

  @override
  String get chatTitle => 'צ׳אט';

  @override
  String get chatMessages => 'הודעות';

  @override
  String get unlimitedChatThisMonth => 'הודעות צ׳אט ללא הגבלה החודש';

  @override
  String chatUsedOfLimitCompute(String used, String limit) {
    return '$used מתוך $limit תקציב מחשוב נוצל';
  }

  @override
  String chatUsedOfLimitMessages(String used, String limit) {
    return '$used מתוך $limit הודעות נוצלו החודש';
  }

  @override
  String chatUsageProgress(String used, String limit) {
    return '$used / $limit נוצל';
  }

  @override
  String get chatLimitReachedUpgrade => 'הגעת למגבלת הצ׳אט. שדרג לעוד הודעות.';

  @override
  String get chatLimitReachedTitle => 'הגעת למגבלת הצ׳אט';

  @override
  String chatUsageDescription(String used, String limitDisplay, String plan) {
    return 'השתמשת ב-$used מתוך $limitDisplay בתוכנית $plan.';
  }

  @override
  String resetsInDays(int count) {
    return 'מתאפס בעוד $count ימים';
  }

  @override
  String resetsInHours(int count) {
    return 'מתאפס בעוד $count שעות';
  }

  @override
  String get resetsSoon => 'מתאפס בקרוב';

  @override
  String get upgradePlan => 'שדרג תוכנית';

  @override
  String get billingMonthly => 'חודשי';

  @override
  String get billingYearly => 'שנתי';

  @override
  String get savePercent => 'חסוך ~17%';

  @override
  String get popular => 'פופולרי';

  @override
  String get currentPlan => 'נוכחי';

  @override
  String neoSubtitle(int count) {
    return '$count שאלות בחודש';
  }

  @override
  String operatorSubtitle(int count) {
    return '$count שאלות בחודש';
  }

  @override
  String get architectSubtitle => 'AI למשתמשים מתקדמים — אלפי שיחות + אוטומציה חכמה';

  @override
  String chatUsageCost(String used, String limit) {
    return 'צ\'אט: \$$used / \$$limit נוצל החודש';
  }

  @override
  String chatUsageCostNoLimit(String used) {
    return 'צ\'אט: \$$used נוצל החודש';
  }

  @override
  String chatUsageMessages(String used, String limit) {
    return 'צ\'אט: $used / $limit הודעות החודש';
  }

  @override
  String chatUsageMessagesNoLimit(String used) {
    return 'צ\'אט: $used הודעות החודש';
  }

  @override
  String get chatQuotaSubtitle => 'AI chat messages used with Omi this month.';

  @override
  String get chatQuotaExceededReply => 'הגעת למגבלה החודשית שלך. שדרג כדי להמשיך לשוחח עם Omi ללא הגבלות.';

  @override
  String get voiceResponseAudio => 'קרא את תגובת Omi בקול';

  @override
  String get voiceResponseMode => 'תגובה קולית';

  @override
  String get voiceResponseModeTitle => 'מתי לקרוא תשובות';

  @override
  String get voiceResponseOff => 'כבוי';

  @override
  String get voiceResponseHeadphonesOnly => 'אוזניות בלבד';

  @override
  String get voiceResponseAlways => 'תמיד';

  @override
  String get agreeAndContinue => 'אני מסכים והמשך';

  @override
  String get startVoiceRecording => 'התחל הקלטה קולית';

  @override
  String get startCallRecording => 'התחל הקלטת שיחה';

  @override
  String get mindMap => 'Mind Map';

  @override
  String get voiceMode => 'מצב קולי';

  @override
  String get quickActionAskOmi => 'שאל את Omi כל דבר';

  @override
  String get record => 'הקלט';

  @override
  String get stop => 'עצור';

  @override
  String get recordWithPhoneMic => 'הקלט עם מיקרופון הטלפון';

  @override
  String get recordWithPhoneMicSubtitle => 'הקלט שמע סביבך';

  @override
  String get phoneCall => 'שיחת טלפון';

  @override
  String get phoneCallSubtitle => 'הקלט שיחה עם תמלול חי';

  @override
  String get searchActionItems => 'חפש פריטי פעולה';

  @override
  String get selectActionItems => 'בחירה מרובה';

  @override
  String chooseExportDestination(int count) {
    return 'ייצוא $count פריט(ים) אל…';
  }

  @override
  String get bulkExportInProgress => 'מייצא…';

  @override
  String bulkExportSuccess(int count, String platform) {
    return 'יוצאו $count אל $platform';
  }

  @override
  String bulkExportPartial(int success, int total, String platform) {
    return 'יוצאו $success מתוך $total אל $platform';
  }

  @override
  String get showCompletedTasks => 'הצג הושלמו';

  @override
  String get hideCompletedTasks => 'הסתר הושלמו';

  @override
  String get selectAllTasksMenu => 'בחר הכל';

  @override
  String get connectTaskAppToExport => 'חבר אפליקציית משימות בהגדרות כדי לייצא';

  @override
  String get connectAction => 'חיבור';

  @override
  String get deselectAllTasksMenu => 'בטל בחירת הכל';
}
