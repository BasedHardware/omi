// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Bengali Bangla (`bn`).
class AppLocalizationsBn extends AppLocalizations {
  AppLocalizationsBn([String locale = 'bn']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'কথোপকথন';

  @override
  String get transcriptTab => 'প্রতিলিপি';

  @override
  String get actionItemsTab => 'কর্মপরিকল্পনা';

  @override
  String get deleteConversationTitle => 'কথোপকথন মুছে ফেলুন?';

  @override
  String get deleteConversationMessage =>
      'এটি সম্পর্কিত স্মৃতি, কাজ এবং অডিও ফাইলগুলিও মুছে ফেলবে। এই পদক্ষেপটি আনডু করা যাবে না।';

  @override
  String get confirm => 'নিশ্চিত করুন';

  @override
  String get cancel => 'বাতিল';

  @override
  String get ok => 'ঠিক আছে';

  @override
  String get delete => 'মুছুন';

  @override
  String get add => 'যোগ করুন';

  @override
  String get update => 'আপডেট করুন';

  @override
  String get save => 'সংরক্ষণ করুন';

  @override
  String get edit => 'সম্পাদনা করুন';

  @override
  String get close => 'বন্ধ করুন';

  @override
  String get clear => 'সাফ করুন';

  @override
  String get copyTranscript => 'প্রতিলিপি কপি করুন';

  @override
  String get copySummary => 'সারসংক্ষেপ কপি করুন';

  @override
  String get testPrompt => 'পরীক্ষা প্রম্পট';

  @override
  String get reprocessConversation => 'কথোপকথন পুনরায় প্রক্রিয়া করুন';

  @override
  String get deleteConversation => 'কথোপকথন মুছুন';

  @override
  String get contentCopied => 'বিষয়বস্তু ক্লিপবোর্ডে কপি হয়েছে';

  @override
  String get failedToUpdateStarred => 'তারকা চিহ্ন অবস্থা আপডেট করতে ব্যর্থ হয়েছে।';

  @override
  String get conversationUrlNotShared => 'কথোপকথন URL শেয়ার করা যায়নি।';

  @override
  String get errorProcessingConversation => 'কথোপকথন প্রক্রিয়া করার সময় ত্রুটি। অনুগ্রহ করে পরে আবার চেষ্টা করুন।';

  @override
  String get noInternetConnection => 'ইন্টারনেট সংযোগ নেই';

  @override
  String get unableToDeleteConversation => 'কথোপকথন মুছতে অক্ষম';

  @override
  String get somethingWentWrong => 'কিছু ভুল হয়েছে! অনুগ্রহ করে পরে আবার চেষ্টা করুন।';

  @override
  String get copyErrorMessage => 'ত্রুটি বার্তা কপি করুন';

  @override
  String get errorCopied => 'ত্রুটি বার্তা ক্লিপবোর্ডে কপি হয়েছে';

  @override
  String get remaining => 'অবশিষ্ট';

  @override
  String get loading => 'লোড হচ্ছে...';

  @override
  String get loadingDuration => 'সময়কাল লোড হচ্ছে...';

  @override
  String secondsCount(int count) {
    return '$count সেকেন্ড';
  }

  @override
  String get people => 'মানুষ';

  @override
  String get addNewPerson => 'নতুন ব্যক্তি যোগ করুন';

  @override
  String get editPerson => 'ব্যক্তি সম্পাদনা করুন';

  @override
  String get createPersonHint => 'একজন নতুন ব্যক্তি তৈরি করুন এবং Omi কে তাদের কণ্ঠস্বর চিনতে প্রশিক্ষণ দিন!';

  @override
  String get speechProfile => 'বক্তৃতা প্রোফাইল';

  @override
  String sampleNumber(int number) {
    return 'নমুনা $number';
  }

  @override
  String get settings => 'সেটিংস';

  @override
  String get language => 'ভাষা';

  @override
  String get selectLanguage => 'ভাষা নির্বাচন করুন';

  @override
  String get deleting => 'মুছছে...';

  @override
  String get pleaseCompleteAuthentication => 'আপনার ব্রাউজারে প্রমাণীকরণ সম্পূর্ণ করুন। সম্পন্ন হলে, অ্যাপে ফিরে আসুন।';

  @override
  String get failedToStartAuthentication => 'প্রমাণীকরণ শুরু করতে ব্যর্থ';

  @override
  String get importStarted => 'আমদানি শুরু হয়েছে! এটি সম্পূর্ণ হলে আপনাকে সূচিত করা হবে।';

  @override
  String get failedToStartImport => 'আমদানি শুরু করতে ব্যর্থ। অনুগ্রহ করে আবার চেষ্টা করুন।';

  @override
  String get couldNotAccessFile => 'নির্বাচিত ফাইলটি অ্যাক্সেস করা যায়নি';

  @override
  String get askOmi => 'Omi কে জিজ্ঞাসা করুন';

  @override
  String get done => 'সম্পন্ন';

  @override
  String get disconnected => 'সংযোগ বিচ্ছিন্ন';

  @override
  String get searching => 'অনুসন্ধান করছে...';

  @override
  String get connectDevice => 'ডিভাইস সংযুক্ত করুন';

  @override
  String get monthlyLimitReached => 'আপনি আপনার মাসিক সীমায় পৌঁছেছেন।';

  @override
  String get checkUsage => 'ব্যবহার পরীক্ষা করুন';

  @override
  String get syncingRecordings => 'রেকর্ডিং সিঙ্ক করছে';

  @override
  String get recordingsToSync => 'সিঙ্ক করার জন্য রেকর্ডিং';

  @override
  String get allCaughtUp => 'সবকিছু ধরা পড়েছে';

  @override
  String get sync => 'সিঙ্ক করুন';

  @override
  String get pendantUpToDate => 'পেন্ডেন্ট আপডেট-এ-ডেট';

  @override
  String get allRecordingsSynced => 'সমস্ত রেকর্ডিং সিঙ্ক হয়েছে';

  @override
  String get syncingInProgress => 'সিঙ্ক করা চলছে';

  @override
  String get readyToSync => 'সিঙ্ক করার জন্য প্রস্তুত';

  @override
  String get tapSyncToStart => 'শুরু করতে সিঙ্ক ট্যাপ করুন';

  @override
  String get pendantNotConnected => 'পেন্ডেন্ট সংযুক্ত নয়। সিঙ্ক করতে সংযুক্ত করুন।';

  @override
  String get everythingSynced => 'সবকিছু ইতিমধ্যে সিঙ্ক হয়েছে।';

  @override
  String get recordingsNotSynced => 'আপনার এমন রেকর্ডিং রয়েছে যা এখনও সিঙ্ক হয়নি।';

  @override
  String get syncingBackground => 'আমরা আপনার রেকর্ডিং পটভূমিতে সিঙ্ক করতে থাকব।';

  @override
  String get noConversationsYet => 'এখনো কোনো কথোপকথন নেই';

  @override
  String get noStarredConversations => 'কোনো তারকা চিহ্নিত কথোপকথন নেই';

  @override
  String get starConversationHint => 'একটি কথোপকথনকে তারকা চিহ্নিত করতে, এটি খুলুন এবং হেডারে তারকা আইকনে ট্যাপ করুন।';

  @override
  String get searchConversations => 'কথোপকথন খুঁজুন...';

  @override
  String selectedCount(int count, Object s) {
    return '$count নির্বাচিত';
  }

  @override
  String get merge => 'মার্জ করুন';

  @override
  String get mergeConversations => 'কথোপকথন মার্জ করুন';

  @override
  String mergeConversationsMessage(int count) {
    return 'এটি $count টি কথোপকথনকে একটিতে একত্রিত করবে। সমস্ত বিষয়বস্তু মার্জ এবং পুনরায় তৈরি করা হবে।';
  }

  @override
  String get mergingInBackground => 'পটভূমিতে মার্জ করছে। এটি একটি মুহূর্ত সময় নিতে পারে।';

  @override
  String get failedToStartMerge => 'মার্জ শুরু করতে ব্যর্থ';

  @override
  String get askAnything => 'যেকোনো কিছু জিজ্ঞাসা করুন';

  @override
  String get noMessagesYet => 'এখনো কোনো বার্তা নেই!\nকেন আপনি একটি কথোপকথন শুরু করবেন না?';

  @override
  String get deletingMessages => 'Omi এর স্মৃতি থেকে আপনার বার্তা মুছছে...';

  @override
  String get messageCopied => '✨ বার্তা ক্লিপবোর্ডে কপি হয়েছে';

  @override
  String get cannotReportOwnMessage => 'আপনি আপনার নিজের বার্তা রিপোর্ট করতে পারবেন না।';

  @override
  String get reportMessage => 'বার্তা রিপোর্ট করুন';

  @override
  String get reportMessageConfirm => 'আপনি কি নিশ্চিত যে এই বার্তাটি রিপোর্ট করতে চান?';

  @override
  String get messageReported => 'বার্তা সফলভাবে রিপোর্ট করা হয়েছে।';

  @override
  String get thankYouFeedback => 'আপনার প্রতিক্রিয়ার জন্য ধন্যবাদ!';

  @override
  String get clearChat => 'চ্যাট সাফ করুন';

  @override
  String get clearChatConfirm => 'আপনি কি নিশ্চিত যে আপনি চ্যাটটি সাফ করতে চান? এই পদক্ষেপটি আনডু করা যাবে না।';

  @override
  String get maxFilesLimit => 'আপনি একবারে শুধুমাত্র 4 টি ফাইল আপলোড করতে পারেন';

  @override
  String get chatWithOmi => 'Omi এর সাথে চ্যাট করুন';

  @override
  String get apps => 'অ্যাপস';

  @override
  String get noAppsFound => 'কোনো অ্যাপ পাওয়া যায়নি';

  @override
  String get tryAdjustingSearch => 'আপনার অনুসন্ধান বা ফিল্টার সামঞ্জস্য করার চেষ্টা করুন';

  @override
  String get createYourOwnApp => 'আপনার নিজের অ্যাপ তৈরি করুন';

  @override
  String get buildAndShareApp => 'আপনার কাস্টম অ্যাপ তৈরি এবং শেয়ার করুন';

  @override
  String get searchApps => 'অ্যাপস খুঁজুন...';

  @override
  String get myApps => 'আমার অ্যাপস';

  @override
  String get installedApps => 'ইনস্টল করা অ্যাপস';

  @override
  String get unableToFetchApps =>
      'অ্যাপস পেতে অক্ষম :(\n\nঅনুগ্রহ করে আপনার ইন্টারনেট সংযোগ পরীক্ষা করুন এবং আবার চেষ্টা করুন।';

  @override
  String get aboutOmi => 'Omi সম্পর্কে';

  @override
  String get privacyPolicy => 'গোপনীয়তা নীতি';

  @override
  String get visitWebsite => 'ওয়েবসাইট পরিদর্শন করুন';

  @override
  String get helpOrInquiries => 'সাহায্য বা জিজ্ঞাসা?';

  @override
  String get joinCommunity => 'সম্প্রদায়ে যোগ দিন!';

  @override
  String get membersAndCounting => '8000+ সদস্য এবং বৃদ্ধি পাচ্ছে।';

  @override
  String get deleteAccountTitle => 'অ্যাকাউন্ট মুছুন';

  @override
  String get deleteAccountConfirm => 'আপনি কি নিশ্চিত যে আপনি আপনার অ্যাকাউন্ট মুছতে চান?';

  @override
  String get cannotBeUndone => 'এটি আনডু করা যাবে না।';

  @override
  String get allDataErased => 'আপনার সমস্ত স্মৃতি এবং কথোপকথন স্থায়ীভাবে মুছে ফেলা হবে।';

  @override
  String get appsDisconnected => 'আপনার অ্যাপস এবং ইন্টিগ্রেশনগুলি তাৎক্ষণিকভাবে সংযোগ বিচ্ছিন্ন হবে।';

  @override
  String get exportBeforeDelete =>
      'আপনি আপনার অ্যাকাউন্ট মুছে ফেলার আগে আপনার ডেটা এক্সপোর্ট করতে পারেন, কিন্তু একবার মুছে গেলে, এটি পুনরুদ্ধার করা যাবে না।';

  @override
  String get deleteAccountCheckbox =>
      'আমি বুঝি যে আমার অ্যাকাউন্ট মুছে ফেলা স্থায়ী এবং সমস্ত ডেটা, স্মৃতি এবং কথোপকথন সহ হারিয়ে যাবে এবং পুনরুদ্ধার করা যাবে না।';

  @override
  String get areYouSure => 'আপনি নিশ্চিত?';

  @override
  String get deleteAccountFinal =>
      'এই পদক্ষেপটি অপ্রতিবর্তনীয় এবং আপনার অ্যাকাউন্ট এবং সমস্ত সম্পর্কিত ডেটা স্থায়ীভাবে মুছে ফেলবে। আপনি কি এগিয়ে যেতে চান?';

  @override
  String get deleteNow => 'এখনই মুছুন';

  @override
  String get goBack => 'ফিরে যান';

  @override
  String get checkBoxToConfirm =>
      'নিশ্চিত করতে বক্স চেক করুন যে আপনি বুঝেন যে আপনার অ্যাকাউন্ট মুছে ফেলা স্থায়ী এবং অপ্রতিবর্তনীয়।';

  @override
  String get profile => 'প্রোফাইল';

  @override
  String get name => 'নাম';

  @override
  String get email => 'ইমেইল';

  @override
  String get customVocabulary => 'কাস্টম শব্দাবলী';

  @override
  String get identifyingOthers => 'অন্যদের সনাক্ত করা';

  @override
  String get paymentMethods => 'পেমেন্ট পদ্ধতি';

  @override
  String get conversationDisplay => 'কথোপকথন প্রদর্শন';

  @override
  String get dataPrivacy => 'ডেটা গোপনীয়তা';

  @override
  String get userId => 'ব্যবহারকারী ID';

  @override
  String get notSet => 'সেট নয়';

  @override
  String get userIdCopied => 'ব্যবহারকারী ID ক্লিপবোর্ডে কপি হয়েছে';

  @override
  String get systemDefault => 'সিস্টেম ডিফল্ট';

  @override
  String get planAndUsage => 'পরিকল্পনা এবং ব্যবহার';

  @override
  String get offlineSync => 'অফলাইন সিঙ্ক';

  @override
  String get deviceSettings => 'ডিভাইস সেটিংস';

  @override
  String get integrations => 'ইন্টিগ্রেশনগুলি';

  @override
  String get feedbackBug => 'প্রতিক্রিয়া / বাগ';

  @override
  String get helpCenter => 'সহায়তা কেন্দ্র';

  @override
  String get developerSettings => 'ডেভেলপার সেটিংস';

  @override
  String get getOmiForMac => 'Mac এর জন্য Omi পান';

  @override
  String get referralProgram => 'রেফারেল প্রোগ্রাম';

  @override
  String get signOut => 'সাইন আউট করুন';

  @override
  String get appAndDeviceCopied => 'অ্যাপ এবং ডিভাইসের বিবরণ কপি হয়েছে';

  @override
  String get wrapped2025 => 'র্যাপড 2025';

  @override
  String get yourPrivacyYourControl => 'আপনার গোপনীয়তা, আপনার নিয়ন্ত্রণ';

  @override
  String get privacyIntro =>
      'Omi তে, আমরা আপনার গোপনীয়তা রক্ষা করতে প্রতিশ্রুতিবদ্ধ। এই পৃষ্ঠাটি আপনাকে আপনার ডেটা কীভাবে সংরক্ষণ এবং ব্যবহার করা হয় তা নিয়ন্ত্রণ করতে দেয়।';

  @override
  String get learnMore => 'আরও শিখুন...';

  @override
  String get dataProtectionLevel => 'ডেটা সুরক্ষা স্তর';

  @override
  String get dataProtectionDesc =>
      'আপনার ডেটা শক্তিশালী এনক্রিপশন দ্বারা ডিফল্টরূপে সুরক্ষিত। নীচে আপনার সেটিংস এবং ভবিষ্যত গোপনীয়তা বিকল্পগুলি পর্যালোচনা করুন।';

  @override
  String get appAccess => 'অ্যাপ অ্যাক্সেস';

  @override
  String get appAccessDesc =>
      'নিম্নলিখিত অ্যাপগুলি আপনার ডেটা অ্যাক্সেস করতে পারে। একটি অ্যাপের অনুমতি পরিচালনা করতে এটিতে ট্যাপ করুন।';

  @override
  String get noAppsExternalAccess => 'কোনো ইনস্টল করা অ্যাপের আপনার ডেটায় বাহ্যিক অ্যাক্সেস নেই।';

  @override
  String get deviceName => 'ডিভাইসের নাম';

  @override
  String get deviceId => 'ডিভাইস ID';

  @override
  String get firmware => 'ফার্মওয়্যার';

  @override
  String get sdCardSync => 'SD কার্ড সিঙ্ক';

  @override
  String get hardwareRevision => 'হার্ডওয়্যার সংশোধন';

  @override
  String get modelNumber => 'মডেল নম্বর';

  @override
  String get manufacturer => 'নির্মাতা';

  @override
  String get doubleTap => 'দ্বিগুণ ট্যাপ';

  @override
  String get ledBrightness => 'LED উজ্জ্বলতা';

  @override
  String get micGain => 'মাইক গেইন';

  @override
  String get disconnect => 'সংযোগ বিচ্ছিন্ন করুন';

  @override
  String get forgetDevice => 'ডিভাইস ভুলে যান';

  @override
  String get chargingIssues => 'চার্জিং সমস্যা';

  @override
  String get disconnectDevice => 'ডিভাইস সংযোগ বিচ্ছিন্ন করুন';

  @override
  String get unpairDevice => 'ডিভাইস আনপেয়ার করুন';

  @override
  String get unpairAndForget => 'ডিভাইস আনপেয়ার এবং ভুলে যান';

  @override
  String get deviceDisconnectedMessage => 'আপনার Omi সংযোগ বিচ্ছিন্ন হয়েছে 😔';

  @override
  String get deviceUnpairedMessage =>
      'ডিভাইস আনপেয়ার করা হয়েছে। আনপেয়ারিং সম্পূর্ণ করতে সেটিংস > ব্লুটুথ যান এবং ডিভাইসটি ভুলে যান।';

  @override
  String get unpairDialogTitle => 'ডিভাইস আনপেয়ার করুন';

  @override
  String get unpairDialogMessage =>
      'এটি ডিভাইসটি আনপেয়ার করবে যাতে এটি অন্য ফোনের সাথে সংযুক্ত হতে পারে। আপনাকে সেটিংস > ব্লুটুথ যেতে হবে এবং প্রক্রিয়াটি সম্পূর্ণ করতে ডিভাইসটি ভুলে যেতে হবে।';

  @override
  String get deviceNotConnected => 'ডিভাইস সংযুক্ত নয়';

  @override
  String get connectDeviceMessage => 'ডিভাইস সেটিংস এবং কাস্টমাইজেশন অ্যাক্সেস করতে আপনার Omi ডিভাইস সংযুক্ত করুন';

  @override
  String get deviceInfoSection => 'ডিভাইস তথ্য';

  @override
  String get customizationSection => 'কাস্টমাইজেশন';

  @override
  String get hardwareSection => 'হার্ডওয়্যার';

  @override
  String get v2Undetected => 'V2 সনাক্ত হয়নি';

  @override
  String get v2UndetectedMessage =>
      'আমরা দেখছি যে আপনার কাছে একটি V1 ডিভাইস রয়েছে বা আপনার ডিভাইস সংযুক্ত নয়। SD কার্ড কার্যকারিতা শুধুমাত্র V2 ডিভাইসের জন্য উপলব্ধ।';

  @override
  String get endConversation => 'কথোপকথন শেষ করুন';

  @override
  String get pauseResume => 'বিরাম/পুনরায় শুরু করুন';

  @override
  String get starConversation => 'কথোপকথনকে তারকা চিহ্নিত করুন';

  @override
  String get doubleTapAction => 'দ্বিগুণ ট্যাপ ক্রিয়া';

  @override
  String get endAndProcess => 'কথোপকথন শেষ এবং প্রক্রিয়া করুন';

  @override
  String get pauseResumeRecording => 'রেকর্ডিং বিরাম/পুনরায় শুরু করুন';

  @override
  String get starOngoing => 'চলমান কথোপকথনকে তারকা চিহ্নিত করুন';

  @override
  String get off => 'বন্ধ';

  @override
  String get max => 'সর্বোচ্চ';

  @override
  String get mute => 'নিঃশব্দ করুন';

  @override
  String get quiet => 'শান্ত';

  @override
  String get normal => 'সাধারণ';

  @override
  String get high => 'উচ্চ';

  @override
  String get micGainDescMuted => 'মাইক্রোফোন নিঃশব্দ করা হয়েছে';

  @override
  String get micGainDescLow => 'খুব শান্ত - জোরালো পরিবেশের জন্য';

  @override
  String get micGainDescModerate => 'শান্ত - মধ্যম শব্দের জন্য';

  @override
  String get micGainDescNeutral => 'নিরপেক্ষ - সুষম রেকর্ডিং';

  @override
  String get micGainDescSlightlyBoosted => 'সামান্য বৃদ্ধি - সাধারণ ব্যবহার';

  @override
  String get micGainDescBoosted => 'বৃদ্ধি - শান্ত পরিবেশের জন্য';

  @override
  String get micGainDescHigh => 'উচ্চ - দূরবর্তী বা নরম কণ্ঠের জন্য';

  @override
  String get micGainDescVeryHigh => 'খুব উচ্চ - খুব শান্ত উৎসের জন্য';

  @override
  String get micGainDescMax => 'সর্বোচ্চ - সতর্কতার সাথে ব্যবহার করুন';

  @override
  String get developerSettingsTitle => 'ডেভেলপার সেটিংস';

  @override
  String get saving => 'সংরক্ষণ করছে...';

  @override
  String get beta => 'বিটা';

  @override
  String get transcription => 'ট্রান্সক্রিপশন';

  @override
  String get transcriptionConfig => 'STT প্রদানকারী কনফিগার করুন';

  @override
  String get conversationTimeout => 'কথোপকথন টাইমআউট';

  @override
  String get conversationTimeoutConfig => 'কথোপকথন কখন স্বয়ংক্রিয়ভাবে শেষ হয় তা নির্ধারণ করুন';

  @override
  String get importData => 'ডেটা আমদানি করুন';

  @override
  String get importDataConfig => 'অন্যান্য উৎস থেকে ডেটা আমদানি করুন';

  @override
  String get debugDiagnostics => 'ডিবাগ এবং ডায়াগনস্টিক্স';

  @override
  String get endpointUrl => 'এন্ডপয়েন্ট URL';

  @override
  String get noApiKeys => 'এখনো কোনো API কী নেই';

  @override
  String get createKeyToStart => 'শুরু করতে একটি কী তৈরি করুন';

  @override
  String get createKey => 'কী তৈরি করুন';

  @override
  String get docs => 'ডকুমেন্টেশন';

  @override
  String get yourOmiInsights => 'আপনার Omi অন্তর্দৃষ্টি';

  @override
  String get today => 'আজ';

  @override
  String get thisMonth => 'এই মাস';

  @override
  String get thisYear => 'এই বছর';

  @override
  String get allTime => 'সর্বকাল';

  @override
  String get noActivityYet => 'এখনো কোনো কার্যকলাপ নেই';

  @override
  String get startConversationToSeeInsights =>
      'এখানে আপনার ব্যবহার অন্তর্দৃষ্টি দেখতে Omi এর সাথে একটি কথোপকথন শুরু করুন।';

  @override
  String get listening => 'শোনা';

  @override
  String get listeningSubtitle => 'মোট সময় Omi সক্রিয়ভাবে শুনেছে।';

  @override
  String get understanding => 'বোঝা';

  @override
  String get understandingSubtitle => 'আপনার কথোপকথন থেকে বোঝা শব্দ।';

  @override
  String get providing => 'প্রদান করা';

  @override
  String get providingSubtitle => 'কর্মপরিকল্পনা এবং নোট স্বয়ংক্রিয়ভাবে ক্যাপচার করা।';

  @override
  String get remembering => 'স্মরণ করা';

  @override
  String get rememberingSubtitle => 'আপনার জন্য মনে রাখা তথ্য এবং বিবরণ।';

  @override
  String get unlimitedPlan => 'আনলিমিটেড প্ল্যান';

  @override
  String get managePlan => 'প্ল্যান পরিচালনা করুন';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'আপনার প্ল্যান $date এ বাতিল হবে।';
  }

  @override
  String renewsOn(String date) {
    return 'আপনার প্ল্যান $date এ নবায়ন হয়।';
  }

  @override
  String get basicPlan => 'বিনামূল্যে পরিকল্পনা';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$limit মিনিটের মধ্যে $used ব্যবহৃত হয়েছে';
  }

  @override
  String get upgrade => 'আপগ্রেড করুন';

  @override
  String get upgradeToUnlimited => 'আনলিমিটেডে আপগ্রেড করুন';

  @override
  String basicPlanDesc(int limit) {
    return 'আপনার পরিকল্পনায় মাসিক $limit বিনামূল্যে মিনিট রয়েছে। আনলিমিটেডে যেতে আপগ্রেড করুন।';
  }

  @override
  String get shareStatsMessage => 'আমার Omi পরিসংখ্যান শেয়ার করছি! (omi.me - আপনার সর্বদা-চালু AI সহায়ক)';

  @override
  String get sharePeriodToday => 'আজ, omi এর ছিল:';

  @override
  String get sharePeriodMonth => 'এই মাস, omi এর ছিল:';

  @override
  String get sharePeriodYear => 'এই বছর, omi এর ছিল:';

  @override
  String get sharePeriodAllTime => 'এখন পর্যন্ত, omi এর ছিল:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 $minutes মিনিট শুনেছে';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 $words শব্দ বুঝেছে';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ $count অন্তর্দৃষ্টি প্রদান করেছে';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 $count স্মৃতি মনে রেখেছে';
  }

  @override
  String get debugLogs => 'ডিবাগ লগ';

  @override
  String get debugLogsAutoDelete => '3 দিনের পরে স্বয়ংক্রিয়ভাবে মুছে যায়।';

  @override
  String get debugLogsDesc => 'সমস্যা নির্ণয়ে সহায়তা করে';

  @override
  String get noLogFilesFound => 'কোনো লগ ফাইল পাওয়া যায়নি।';

  @override
  String get omiDebugLog => 'Omi ডিবাগ লগ';

  @override
  String get logShared => 'লগ শেয়ার করা হয়েছে';

  @override
  String get selectLogFile => 'লগ ফাইল নির্বাচন করুন';

  @override
  String get shareLogs => 'লগ শেয়ার করুন';

  @override
  String get debugLogCleared => 'ডিবাগ লগ সাফ করা হয়েছে';

  @override
  String get exportStarted => 'এক্সপোর্ট শুরু হয়েছে। এটি কয়েক সেকেন্ড সময় নিতে পারে...';

  @override
  String get exportAllData => 'সমস্ত ডেটা এক্সপোর্ট করুন';

  @override
  String get exportDataDesc => 'কথোপকথন একটি JSON ফাইলে এক্সপোর্ট করুন';

  @override
  String get exportedConversations => 'Omi এর কাছ থেকে রপ্তানি করা কথোপকথন';

  @override
  String get exportShared => 'এক্সপোর্ট শেয়ার করা হয়েছে';

  @override
  String get deleteKnowledgeGraphTitle => 'জ্ঞান গ্রাফ মুছুন?';

  @override
  String get deleteKnowledgeGraphMessage =>
      'এটি সমস্ত উদ্ভূত জ্ঞান গ্রাফ ডেটা (নোড এবং সংযোগ) মুছে ফেলবে। আপনার মূল স্মৃতি নিরাপদ থাকবে। গ্রাফটি সময়ের সাথে বা পরবর্তী অনুরোধে পুনর্নির্মাণ করা হবে।';

  @override
  String get knowledgeGraphDeleted => 'জ্ঞান গ্রাফ মুছে ফেলা হয়েছে';

  @override
  String deleteGraphFailed(String error) {
    return 'গ্রাফ মুছতে ব্যর্থ: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'জ্ঞান গ্রাফ মুছুন';

  @override
  String get deleteKnowledgeGraphDesc => 'সমস্ত নোড এবং সংযোগ সাফ করুন';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'MCP সার্ভার';

  @override
  String get mcpServerDesc => 'AI সহায়কদের আপনার ডেটায় সংযুক্ত করুন';

  @override
  String get serverUrl => 'সার্ভার URL';

  @override
  String get urlCopied => 'URL কপি হয়েছে';

  @override
  String get apiKeyAuth => 'API কী প্রমাণীকরণ';

  @override
  String get header => 'হেডার';

  @override
  String get authorizationBearer => 'অনুমোদন: বহন <কী>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'ক্লায়েন্ট ID';

  @override
  String get clientSecret => 'ক্লায়েন্ট গোপনীয়তা';

  @override
  String get useMcpApiKey => 'আপনার MCP API কী ব্যবহার করুন';

  @override
  String get webhooks => 'ওয়েবহুক';

  @override
  String get conversationEvents => 'কথোপকথন ইভেন্ট';

  @override
  String get newConversationCreated => 'নতুন কথোপকথন তৈরি হয়েছে';

  @override
  String get realtimeTranscript => 'রিয়েল-টাইম ট্রান্সক্রিপ্ট';

  @override
  String get transcriptReceived => 'ট্রান্সক্রিপ্ট প্রাপ্ত';

  @override
  String get audioBytes => 'অডিও বাইট';

  @override
  String get audioDataReceived => 'অডিও ডেটা প্রাপ্ত';

  @override
  String get intervalSeconds => 'বিরতি (সেকেন্ড)';

  @override
  String get daySummary => 'দিনের সারসংক্ষেপ';

  @override
  String get summaryGenerated => 'সারসংক্ষেপ তৈরি হয়েছে';

  @override
  String get claudeDesktop => 'Claude ডেস্কটপ';

  @override
  String get addToClaudeConfig => 'claude_desktop_config.json এ যোগ করুন';

  @override
  String get copyConfig => 'কনফিগ কপি করুন';

  @override
  String get configCopied => 'কনফিগ ক্লিপবোর্ডে কপি হয়েছে';

  @override
  String get listeningMins => 'শোনা (মিনিট)';

  @override
  String get understandingWords => 'বোঝা (শব্দ)';

  @override
  String get insights => 'অন্তর্দৃষ্টি';

  @override
  String get memories => 'স্মৃতি';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return 'এই মাসে $limit মিনিটের মধ্যে $used ব্যবহৃত হয়েছে';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return 'এই মাসে $limit শব্দের মধ্যে $used ব্যবহৃত হয়েছে';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return 'এই মাসে $limit অন্তর্দৃষ্টির মধ্যে $used প্রাপ্ত হয়েছে';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return 'এই মাসে $limit স্মৃতির মধ্যে $used তৈরি হয়েছে';
  }

  @override
  String get visibility => 'দৃশ্যমানতা';

  @override
  String get visibilitySubtitle => 'নিয়ন্ত্রণ করুন কোন কথোপকথনগুলি আপনার তালিকায় উপস্থিত হয়';

  @override
  String get showShortConversations => 'সংক্ষিপ্ত কথোপকথন দেখান';

  @override
  String get showShortConversationsDesc => 'থ্রেশহোল্ডের চেয়ে সংক্ষিপ্ত কথোপকথন প্রদর্শন করুন';

  @override
  String get showDiscardedConversations => 'বর্জিত কথোপকথন দেখান';

  @override
  String get showDiscardedConversationsDesc => 'পরিত্যক্ত হিসাবে চিহ্নিত কথোপকথন অন্তর্ভুক্ত করুন';

  @override
  String get shortConversationThreshold => 'সংক্ষিপ্ত কথোপকথন থ্রেশহোল্ড';

  @override
  String get shortConversationThresholdSubtitle => 'এর চেয়ে সংক্ষিপ্ত কথোপকথন উপরে সক্ষম না করলে লুকানো হবে';

  @override
  String get durationThreshold => 'সময়কাল থ্রেশহোল্ড';

  @override
  String get durationThresholdDesc => 'এর চেয়ে সংক্ষিপ্ত কথোপকথন লুকান';

  @override
  String minLabel(int count) {
    return '$count মিনিট';
  }

  @override
  String get customVocabularyTitle => 'কাস্টম শব্দাবলী';

  @override
  String get addWords => 'শব্দ যোগ করুন';

  @override
  String get addWordsDesc => 'নাম, শর্তাবলী বা অস্বাভাবিক শব্দ';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'সংযুক্ত করুন';

  @override
  String get comingSoon => 'শীঘ্রই আসছে';

  @override
  String get integrationsFooter => 'আপনার অ্যাপ সংযুক্ত করুন চ্যাটে ডেটা এবং মেট্রিক্স দেখতে।';

  @override
  String get completeAuthInBrowser =>
      'অনুগ্রহ করে আপনার ব্রাউজারে প্রমাণীকরণ সম্পূর্ণ করুন। সম্পন্ন হলে, অ্যাপে ফিরে আসুন।';

  @override
  String failedToStartAuth(String appName) {
    return '$appName প্রমাণীকরণ শুরু করতে ব্যর্থ';
  }

  @override
  String disconnectAppTitle(String appName) {
    return '$appName সংযোগ বিচ্ছিন্ন করুন?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'আপনি কি নিশ্চিত যে আপনি $appName থেকে সংযোগ বিচ্ছিন্ন করতে চান? আপনি যেকোনো সময় পুনরায় সংযুক্ত করতে পারেন।';
  }

  @override
  String disconnectedFrom(String appName) {
    return '$appName থেকে সংযোগ বিচ্ছিন্ন';
  }

  @override
  String get failedToDisconnect => 'সংযোগ বিচ্ছিন্ন করতে ব্যর্থ';

  @override
  String connectTo(String appName) {
    return '$appName এ সংযুক্ত করুন';
  }

  @override
  String authAccessMessage(String appName) {
    return 'আপনার $appName ডেটা অ্যাক্সেস করার জন্য Omi কে অনুমোদন করতে হবে। এটি প্রমাণীকরণের জন্য আপনার ব্রাউজার খুলবে।';
  }

  @override
  String get continueAction => 'চালিয়ে যান';

  @override
  String get languageTitle => 'ভাষা';

  @override
  String get primaryLanguage => 'প্রাথমিক ভাষা';

  @override
  String get automaticTranslation => 'স্বয়ংক্রিয় অনুবাদ';

  @override
  String get detectLanguages => '10+ ভাষা সনাক্ত করুন';

  @override
  String get authorizeSavingRecordings => 'রেকর্ডিং সংরক্ষণ অনুমোদন করুন';

  @override
  String get thanksForAuthorizing => 'অনুমোদনের জন্য ধন্যবাদ!';

  @override
  String get needYourPermission => 'আমাদের আপনার অনুমতি প্রয়োজন';

  @override
  String get alreadyGavePermission =>
      'আপনি ইতিমধ্যে আমাদের আপনার রেকর্ডিং সংরক্ষণ করার অনুমতি দিয়েছেন। এখানে আমাদের এটি প্রয়োজনের একটি অনুস্মারক রয়েছে:';

  @override
  String get wouldLikePermission => 'আমরা আপনার কণ্ঠস্বর রেকর্ডিং সংরক্ষণ করার অনুমতি চাই। এখানে কেন রয়েছে:';

  @override
  String get improveSpeechProfile => 'আপনার কণ্ঠ প্রোফাইল উন্নত করুন';

  @override
  String get improveSpeechProfileDesc =>
      'আমরা রেকর্ডিং ব্যবহার করে আপনার ব্যক্তিগত কণ্ঠ প্রোফাইলকে আরও প্রশিক্ষণ এবং উন্নত করি।';

  @override
  String get trainFamilyProfiles => 'বন্ধু এবং পরিবারের জন্য প্রোফাইল প্রশিক্ষণ করুন';

  @override
  String get trainFamilyProfilesDesc =>
      'আপনার রেকর্ডিং আমাদের আপনার বন্ধু এবং পরিবারকে চিনতে এবং প্রোফাইল তৈরি করতে সাহায্য করে।';

  @override
  String get enhanceTranscriptAccuracy => 'ট্রান্সক্রিপ্ট নির্ভুলতা উন্নত করুন';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'আমাদের মডেল উন্নত হওয়ায়, আমরা আপনার রেকর্ডিংয়ের জন্য আরও ভাল ট্রান্সক্রিপশন ফলাফল প্রদান করতে পারি।';

  @override
  String get legalNotice =>
      'আইনি নোটিশ: ভয়েস ডেটা রেকর্ড এবং সংরক্ষণের আইনি বৈধতা আপনার অবস্থান এবং আপনি এই বৈশিষ্ট্যটি কীভাবে ব্যবহার করেন তার উপর নির্ভর করে পরিবর্তিত হতে পারে। স্থানীয় আইন এবং প্রবিধান মেনে চলা নিশ্চিত করা আপনার দায়িত্ব।';

  @override
  String get alreadyAuthorized => 'ইতিমধ্যে অনুমোদিত';

  @override
  String get authorize => 'অনুমোদন করুন';

  @override
  String get revokeAuthorization => 'অনুমোদন প্রত্যাহার করুন';

  @override
  String get authorizationSuccessful => 'অনুমোদন সফল!';

  @override
  String get failedToAuthorize => 'অনুমোদন করতে ব্যর্থ। আবার চেষ্টা করুন।';

  @override
  String get authorizationRevoked => 'অনুমোদন প্রত্যাহার করা হয়েছে।';

  @override
  String get recordingsDeleted => 'রেকর্ডিংগুলি মুছে ফেলা হয়েছে।';

  @override
  String get failedToRevoke => 'অনুমোদন প্রত্যাহার করতে ব্যর্থ। আবার চেষ্টা করুন।';

  @override
  String get permissionRevokedTitle => 'অনুমতি প্রত্যাহার করা হয়েছে';

  @override
  String get permissionRevokedMessage => 'আপনি কি আপনার বিদ্যমান সমস্ত রেকর্ডিংও সরাতে চান?';

  @override
  String get yes => 'হ্যাঁ';

  @override
  String get editName => 'নাম সম্পাদনা করুন';

  @override
  String get howShouldOmiCallYou => 'Omi আপনাকে কী নাম দিয়ে ডাকবে?';

  @override
  String get enterYourName => 'আপনার নাম লিখুন';

  @override
  String get nameCannotBeEmpty => 'নাম খালি থাকতে পারে না';

  @override
  String get nameUpdatedSuccessfully => 'নাম সফলভাবে আপডেট করা হয়েছে!';

  @override
  String get calendarSettings => 'ক্যালেন্ডার সেটিংস';

  @override
  String get calendarProviders => 'ক্যালেন্ডার প্রদানকারীরা';

  @override
  String get macOsCalendar => 'macOS ক্যালেন্ডার';

  @override
  String get connectMacOsCalendar => 'আপনার স্থানীয় macOS ক্যালেন্ডার সংযুক্ত করুন';

  @override
  String get googleCalendar => 'Google ক্যালেন্ডার';

  @override
  String get syncGoogleAccount => 'আপনার Google অ্যাকাউন্টের সাথে সিঙ্ক করুন';

  @override
  String get showMeetingsMenuBar => 'মেনু বারে আসন্ন মিটিংগুলি দেখান';

  @override
  String get showMeetingsMenuBarDesc => 'macOS মেনু বারে আপনার পরবর্তী মিটিং এবং সময় পর্যন্ত প্রদর্শন করুন';

  @override
  String get showEventsNoParticipants => 'অংশগ্রহণকারী ছাড়াই ইভেন্টগুলি দেখান';

  @override
  String get showEventsNoParticipantsDesc => 'সক্ষম হলে, আসন্ন অংশগ্রহণকারী বা ভিডিও লিংক ছাড়াই ইভেন্টগুলি দেখায়।';

  @override
  String get yourMeetings => 'আপনার মিটিংগুলি';

  @override
  String get refresh => 'রিফ্রেশ করুন';

  @override
  String get noUpcomingMeetings => 'আসন্ন কোনো মিটিং নেই';

  @override
  String get checkingNextDays => 'পরবর্তী 30 দিন পরীক্ষা করছেন';

  @override
  String get tomorrow => 'আগামীকাল';

  @override
  String get googleCalendarComingSoon => 'Google ক্যালেন্ডার ইন্টিগ্রেশন শীঘ্রই আসছে!';

  @override
  String connectedAsUser(String userId) {
    return 'ব্যবহারকারী হিসাবে সংযুক্ত: $userId';
  }

  @override
  String get defaultWorkspace => 'ডিফল্ট কর্মক্ষেত্র';

  @override
  String get tasksCreatedInWorkspace => 'এই কর্মক্ষেত্রে কাজগুলি তৈরি করা হবে';

  @override
  String get defaultProjectOptional => 'ডিফল্ট প্রকল্প (ঐচ্ছিক)';

  @override
  String get leaveUnselectedTasks => 'প্রকল্প ছাড়াই কাজগুলি তৈরি করতে নির্বাচিত রেখে যান';

  @override
  String get noProjectsInWorkspace => 'এই কর্মক্ষেত্রে কোনো প্রকল্প পাওয়া যায়নি';

  @override
  String get conversationTimeoutDesc =>
      'অটোম্যাটিকভাবে একটি কথোপকথন শেষ করার আগে নীরবতায় কতক্ষণ অপেক্ষা করবেন তা চয়ন করুন:';

  @override
  String get timeout2Minutes => '2 মিনিট';

  @override
  String get timeout2MinutesDesc => '2 মিনিট নীরবতার পরে কথোপকথন শেষ করুন';

  @override
  String get timeout5Minutes => '5 মিনিট';

  @override
  String get timeout5MinutesDesc => '5 মিনিট নীরবতার পরে কথোপকথন শেষ করুন';

  @override
  String get timeout10Minutes => '10 মিনিট';

  @override
  String get timeout10MinutesDesc => '10 মিনিট নীরবতার পরে কথোপকথন শেষ করুন';

  @override
  String get timeout30Minutes => '30 মিনিট';

  @override
  String get timeout30MinutesDesc => '30 মিনিট নীরবতার পরে কথোপকথন শেষ করুন';

  @override
  String get timeout4Hours => '4 ঘন্টা';

  @override
  String get timeout4HoursDesc => '4 ঘন্টা নীরবতার পরে কথোপকথন শেষ করুন';

  @override
  String get conversationEndAfterHours => 'কথোপকথনগুলি এখন 4 ঘন্টা নীরবতার পরে শেষ হবে';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'কথোপকথনগুলি এখন $minutes মিনিটের নীরবতার পরে শেষ হবে';
  }

  @override
  String get tellUsPrimaryLanguage => 'আমাদের বলুন আপনার প্রাথমিক ভাষা';

  @override
  String get languageForTranscription => 'তীক্ষ্ণ ট্রান্সক্রিপশন এবং ব্যক্তিগতকৃত অভিজ্ঞতার জন্য আপনার ভাষা সেট করুন।';

  @override
  String get singleLanguageModeInfo => 'একক ভাষা মোড সক্ষম। উচ্চতর নির্ভুলতার জন্য অনুবাদ অক্ষম করা হয়েছে।';

  @override
  String get searchLanguageHint => 'নাম বা কোডের মাধ্যমে ভাষা অনুসন্ধান করুন';

  @override
  String get noLanguagesFound => 'কোনো ভাষা পাওয়া যায়নি';

  @override
  String get skip => 'এড়িয়ে যান';

  @override
  String languageSetTo(String language) {
    return '$language তে ভাষা সেট করা হয়েছে';
  }

  @override
  String get failedToSetLanguage => 'ভাষা সেট করতে ব্যর্থ';

  @override
  String appSettings(String appName) {
    return '$appName সেটিংস';
  }

  @override
  String disconnectFromApp(String appName) {
    return '$appName থেকে সংযোগ বিচ্ছিন্ন করবেন?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'এটি আপনার $appName প্রমাণীকরণ সরিয়ে দেবে। আবার ব্যবহার করতে আপনাকে পুনরায় সংযুক্ত করতে হবে।';
  }

  @override
  String connectedToApp(String appName) {
    return '$appName এর সাথে সংযুক্ত';
  }

  @override
  String get account => 'অ্যাকাউন্ট';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'আপনার অ্যাকশন আইটেমগুলি আপনার $appName অ্যাকাউন্টে সিঙ্ক করা হবে';
  }

  @override
  String get defaultSpace => 'ডিফল্ট স্পেস';

  @override
  String get selectSpaceInWorkspace => 'আপনার কর্মক্ষেত্রে একটি স্পেস নির্বাচন করুন';

  @override
  String get noSpacesInWorkspace => 'এই কর্মক্ষেত্রে কোনো স্পেস পাওয়া যায়নি';

  @override
  String get defaultList => 'ডিফল্ট তালিকা';

  @override
  String get tasksAddedToList => 'কাজগুলি এই তালিকায় যোগ করা হবে';

  @override
  String get noListsInSpace => 'এই স্পেসে কোনো তালিকা পাওয়া যায়নি';

  @override
  String failedToLoadRepos(String error) {
    return 'রিপোজিটরি লোড করতে ব্যর্থ: $error';
  }

  @override
  String get defaultRepoSaved => 'ডিফল্ট রিপোজিটরি সংরক্ষিত হয়েছে';

  @override
  String get failedToSaveDefaultRepo => 'ডিফল্ট রিপোজিটরি সংরক্ষণ করতে ব্যর্থ';

  @override
  String get defaultRepository => 'ডিফল্ট রিপোজিটরি';

  @override
  String get selectDefaultRepoDesc =>
      'সমস্যা তৈরির জন্য একটি ডিফল্ট রিপোজিটরি নির্বাচন করুন। আপনি এখনও সমস্যা তৈরি করার সময় একটি ভিন্ন রিপোজিটরি নির্দিষ্ট করতে পারেন।';

  @override
  String get noReposFound => 'কোনো রিপোজিটরি পাওয়া যায়নি';

  @override
  String get private => 'ব্যক্তিগত';

  @override
  String updatedDate(String date) {
    return '$date আপডেট করা হয়েছে';
  }

  @override
  String get yesterday => 'গতকাল';

  @override
  String daysAgo(int count) {
    return '$count দিন আগে';
  }

  @override
  String get oneWeekAgo => '1 সপ্তাহ আগে';

  @override
  String weeksAgo(int count) {
    return '$count সপ্তাহ আগে';
  }

  @override
  String get oneMonthAgo => '1 মাস আগে';

  @override
  String monthsAgo(int count) {
    return '$count মাস আগে';
  }

  @override
  String get issuesCreatedInRepo => 'সমস্যাগুলি আপনার ডিফল্ট রিপোজিটরিতে তৈরি করা হবে';

  @override
  String get taskIntegrations => 'কাজ ইন্টিগ্রেশন';

  @override
  String get configureSettings => 'সেটিংস কনফিগার করুন';

  @override
  String get completeAuthBrowser => 'আপনার ব্রাউজারে প্রমাণীকরণ সম্পন্ন করুন। একবার সম্পন্ন হলে অ্যাপে ফিরে আসুন।';

  @override
  String failedToStartAppAuth(String appName) {
    return '$appName প্রমাণীকরণ শুরু করতে ব্যর্থ';
  }

  @override
  String connectToAppTitle(String appName) {
    return '$appName এর সাথে সংযোগ করুন';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'আপনার $appName অ্যাকাউন্টে কাজ তৈরি করতে Omi অনুমোদন করতে হবে। এটি প্রমাণীকরণের জন্য আপনার ব্রাউজার খুলবে।';
  }

  @override
  String get continueButton => 'চালিয়ে যান';

  @override
  String appIntegration(String appName) {
    return '$appName ইন্টিগ্রেশন';
  }

  @override
  String integrationComingSoon(String appName) {
    return '$appName এর সাথে ইন্টিগ্রেশন শীঘ্রই আসছে! আমরা আপনাকে আরও কাজ পরিচালনার বিকল্প আনতে কঠোর পরিশ্রম করছি।';
  }

  @override
  String get gotIt => 'বুঝলাম';

  @override
  String get tasksExportedOneApp => 'কাজগুলি একবারে একটি অ্যাপে রপ্তানি করা যেতে পারে।';

  @override
  String get completeYourUpgrade => 'আপগ্রেড সম্পন্ন করুন';

  @override
  String get importConfiguration => 'কনফিগারেশন আমদানি করুন';

  @override
  String get exportConfiguration => 'কনফিগারেশন রপ্তানি করুন';

  @override
  String get bringYourOwn => 'নিজের নিয়ে আসুন';

  @override
  String get payYourSttProvider =>
      'Omi অবাধে ব্যবহার করুন। আপনি শুধুমাত্র আপনার STT প্রদানকারীকে সরাসরি অর্থ প্রদান করেন।';

  @override
  String get freeMinutesMonth => 'প্রতি মাসে 1,200 বিনামূল্যে মিনিট অন্তর্ভুক্ত। সীমাহীন ';

  @override
  String get omiUnlimited => 'Omi আনলিমিটেড';

  @override
  String get hostRequired => 'হোস্ট প্রয়োজন';

  @override
  String get validPortRequired => 'বৈধ পোর্ট প্রয়োজন';

  @override
  String get validWebsocketUrlRequired => 'বৈধ WebSocket URL প্রয়োজন (wss://)';

  @override
  String get apiUrlRequired => 'API URL প্রয়োজন';

  @override
  String get apiKeyRequired => 'API চাবি প্রয়োজন';

  @override
  String get invalidJsonConfig => 'অবৈধ JSON কনফিগারেশন';

  @override
  String errorSaving(String error) {
    return 'সংরক্ষণে ত্রুটি: $error';
  }

  @override
  String get configCopiedToClipboard => 'কনফিগ ক্লিপবোর্ডে অনুলিপি করা হয়েছে';

  @override
  String get pasteJsonConfig => 'নীচে আপনার JSON কনফিগারেশন পেস্ট করুন:';

  @override
  String get addApiKeyAfterImport => 'আমদানির পরে আপনাকে নিজের API চাবি যোগ করতে হবে';

  @override
  String get paste => 'পেস্ট করুন';

  @override
  String get import => 'আমদানি করুন';

  @override
  String get invalidProviderInConfig => 'কনফিগারেশনে অবৈধ প্রদানকারী';

  @override
  String importedConfig(String providerName) {
    return 'আমদানি করা $providerName কনফিগারেশন';
  }

  @override
  String invalidJson(String error) {
    return 'অবৈধ JSON: $error';
  }

  @override
  String get provider => 'প্রদানকারী';

  @override
  String get live => 'সরাসরি';

  @override
  String get onDevice => 'ডিভাইসে';

  @override
  String get apiUrl => 'API URL';

  @override
  String get enterSttHttpEndpoint => 'আপনার STT HTTP এন্ডপয়েন্ট লিখুন';

  @override
  String get websocketUrl => 'WebSocket URL';

  @override
  String get enterLiveSttWebsocket => 'আপনার সরাসরি STT WebSocket এন্ডপয়েন্ট লিখুন';

  @override
  String get apiKey => 'API চাবি';

  @override
  String get enterApiKey => 'আপনার API চাবি লিখুন';

  @override
  String get storedLocallyNeverShared => 'স্থানীয়ভাবে সংরক্ষিত, কখনও শেয়ার করা হয় না';

  @override
  String get host => 'হোস্ট';

  @override
  String get port => 'পোর্ট';

  @override
  String get advanced => 'উন্নত';

  @override
  String get configuration => 'কনফিগারেশন';

  @override
  String get requestConfiguration => 'কনফিগারেশন অনুরোধ করুন';

  @override
  String get responseSchema => 'প্রতিক্রিয়া স্কিমা';

  @override
  String get modified => 'সংশোধিত';

  @override
  String get resetRequestConfig => 'অনুরোধ কনফিগ ডিফল্টে রিসেট করুন';

  @override
  String get logs => 'লগ';

  @override
  String get logsCopied => 'লগ অনুলিপি করা হয়েছে';

  @override
  String get noLogsYet => 'এখনও কোনো লগ নেই। কাস্টম STT কার্যকলাপ দেখতে রেকর্ডিং শুরু করুন।';

  @override
  String deviceUsesCodec(String device, String reason) {
    return '$device $reason ব্যবহার করে। Omi ব্যবহার করা হবে।';
  }

  @override
  String get omiTranscription => 'Omi ট্রান্সক্রিপশন';

  @override
  String get bestInClassTranscription => 'শূন্য সেটআপ সহ সেরা শ্রেণীর ট্রান্সক্রিপশন';

  @override
  String get instantSpeakerLabels => 'তাত্ক্ষণিক স্পিকার লেবেল';

  @override
  String get languageTranslation => '100+ ভাষা অনুবাদ';

  @override
  String get optimizedForConversation => 'কথোপকথনের জন্য অপ্টিমাইজ করা';

  @override
  String get autoLanguageDetection => 'স্বয়ংক্রিয় ভাষা সনাক্তকরণ';

  @override
  String get highAccuracy => 'উচ্চ নির্ভুলতা';

  @override
  String get privacyFirst => 'গোপনীয়তা প্রথম';

  @override
  String get saveChanges => 'পরিবর্তনগুলি সংরক্ষণ করুন';

  @override
  String get resetToDefault => 'ডিফল্টে রিসেট করুন';

  @override
  String get viewTemplate => 'টেমপ্লেট দেখুন';

  @override
  String get trySomethingLike => 'এরকম কিছু চেষ্টা করুন...';

  @override
  String get tryIt => 'চেষ্টা করুন';

  @override
  String get creatingPlan => 'পরিকল্পনা তৈরি করছেন';

  @override
  String get developingLogic => 'লজিক্স বিকাশ করছেন';

  @override
  String get designingApp => 'অ্যাপ ডিজাইন করছেন';

  @override
  String get generatingIconStep => 'আইকন তৈরি করছেন';

  @override
  String get finalTouches => 'চূড়ান্ত স্পর্শ';

  @override
  String get processing => 'প্রক্রিয়া করছেন...';

  @override
  String get features => 'বৈশিষ্ট্য';

  @override
  String get creatingYourApp => 'আপনার অ্যাপ তৈরি করছেন...';

  @override
  String get generatingIcon => 'আইকন তৈরি করছেন...';

  @override
  String get whatShouldWeMake => 'আমরা কী তৈরি করব?';

  @override
  String get appName => 'অ্যাপের নাম';

  @override
  String get description => 'বর্ণনা';

  @override
  String get publicLabel => 'সার্বজনীন';

  @override
  String get privateLabel => 'ব্যক্তিগত';

  @override
  String get free => 'বিনামূল্যে';

  @override
  String get perMonth => '/ মাস';

  @override
  String get tailoredConversationSummaries => 'কাস্টমাইজড কথোপকথন সারসংক্ষেপ';

  @override
  String get customChatbotPersonality => 'কাস্টম চ্যাটবট ব্যক্তিত্ব';

  @override
  String get makePublic => 'সার্বজনীন করুন';

  @override
  String get anyoneCanDiscover => 'যে কেউ আপনার অ্যাপ আবিষ্কার করতে পারে';

  @override
  String get onlyYouCanUse => 'শুধুমাত্র আপনি এই অ্যাপ ব্যবহার করতে পারেন';

  @override
  String get paidApp => 'অর্থপ্রাপ্ত অ্যাপ';

  @override
  String get usersPayToUse => 'ব্যবহারকারীরা আপনার অ্যাপ ব্যবহার করতে অর্থ প্রদান করে';

  @override
  String get freeForEveryone => 'সবার জন্য বিনামূল্যে';

  @override
  String get perMonthLabel => '/ মাস';

  @override
  String get creating => 'তৈরি করছেন...';

  @override
  String get createApp => 'অ্যাপ তৈরি করুন';

  @override
  String get searchingForDevices => 'ডিভাইসগুলি অনুসন্ধান করছেন...';

  @override
  String devicesFoundNearby(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'DEVICES',
      one: 'DEVICE',
    );
    return '$count $_temp0 FOUND NEARBY';
  }

  @override
  String get pairingSuccessful => 'জোড়া করা সফল';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Apple Watch এ সংযোগ করতে ত্রুটি: $error';
  }

  @override
  String get dontShowAgain => 'আর দেখাবেন না';

  @override
  String get iUnderstand => 'আমি বুঝি';

  @override
  String get enableBluetooth => 'Bluetooth সক্ষম করুন';

  @override
  String get bluetoothNeeded =>
      'আপনার পরিধানযোগ্যের সাথে সংযোগ করতে Omi এর Bluetooth দরকার। Bluetooth সক্ষম করুন এবং আবার চেষ্টা করুন।';

  @override
  String get contactSupport => 'সাপোর্টের সাথে যোগাযোগ করবেন?';

  @override
  String get connectLater => 'পরে সংযোগ করুন';

  @override
  String get grantPermissions => 'অনুমতি প্রদান করুন';

  @override
  String get backgroundActivity => 'পটভূমিতে কার্যকলাপ';

  @override
  String get backgroundActivityDesc => 'উন্নত স্থিতিশীলতার জন্য Omi কে পটভূমিতে চলতে দিন';

  @override
  String get locationAccess => 'অবস্থান অ্যাক্সেস';

  @override
  String get locationAccessDesc => 'সম্পূর্ণ অভিজ্ঞতার জন্য পটভূমি অবস্থান সক্ষম করুন';

  @override
  String get notifications => 'বিজ্ঞপ্তি';

  @override
  String get notificationsDesc => 'অবহিত থাকতে বিজ্ঞপ্তি সক্ষম করুন';

  @override
  String get locationServiceDisabled => 'অবস্থান সেবা অক্ষম করা হয়েছে';

  @override
  String get locationServiceDisabledDesc =>
      'অবস্থান সেবা অক্ষম। সেটিংস > গোপনীয়তা ও সুরক্ষা > অবস্থান সেবায় যান এবং এটি সক্ষম করুন';

  @override
  String get backgroundLocationDenied => 'পটভূমি অবস্থান অ্যাক্সেস অনুমোদিত নয়';

  @override
  String get backgroundLocationDeniedDesc => 'ডিভাইস সেটিংসে যান এবং অবস্থান অনুমতি \"সর্বদা অনুমোদন করুন\" এ সেট করুন';

  @override
  String get lovingOmi => 'Omi ভালোবাসছেন?';

  @override
  String get leaveReviewIos =>
      'অ্যাপ স্টোরে পর্যালোচনা রেখে আমাদের আরও মানুষের কাছে পৌঁছাতে সাহায্য করুন। আপনার প্রতিক্রিয়া আমাদের কাছে বিশ্ব মানে!';

  @override
  String get leaveReviewAndroid =>
      'Google Play স্টোরে পর্যালোচনা রেখে আমাদের আরও মানুষের কাছে পৌঁছাতে সাহায্য করুন। আপনার প্রতিক্রিয়া আমাদের কাছে বিশ্ব মানে!';

  @override
  String get rateOnAppStore => 'অ্যাপ স্টোরে রেটিং দিন';

  @override
  String get rateOnGooglePlay => 'Google Play তে রেটিং দিন';

  @override
  String get maybeLater => 'হয়তো পরে';

  @override
  String get speechProfileIntro => 'Omi কে আপনার লক্ষ্য এবং আপনার কণ্ঠস্বর শিখতে হবে। আপনি পরে এটি সংশোধন করতে পারবেন।';

  @override
  String get getStarted => 'শুরু করুন';

  @override
  String get allDone => 'সবকিছু সম্পন্ন!';

  @override
  String get keepGoing => 'চলতে থাকুন, আপনি দুর্দান্ত করছেন';

  @override
  String get skipThisQuestion => 'এই প্রশ্নটি এড়িয়ে যান';

  @override
  String get skipForNow => 'এখনের জন্য এড়িয়ে যান';

  @override
  String get connectionError => 'সংযোগ ত্রুটি';

  @override
  String get connectionErrorDesc =>
      'সার্ভারের সাথে সংযোগ করতে ব্যর্থ। আপনার ইন্টারনেট সংযোগ পরীক্ষা করুন এবং আবার চেষ্টা করুন।';

  @override
  String get invalidRecordingMultipleSpeakers => 'অবৈধ রেকর্ডিং সনাক্ত করা হয়েছে';

  @override
  String get multipleSpeakersDesc =>
      'এটি দেখে মনে হচ্ছে রেকর্ডিংয়ে একাধিক স্পিকার রয়েছে। নিশ্চিত করুন যে আপনি একটি শান্ত স্থানে আছেন এবং আবার চেষ্টা করুন।';

  @override
  String get tooShortDesc => 'যথেষ্ট কথা সনাক্ত করা হয়নি। আরও কথা বলুন এবং আবার চেষ্টা করুন।';

  @override
  String get invalidRecordingDesc => 'নিশ্চিত করুন যে আপনি কমপক্ষে 5 সেকেন্ড এবং 90 এর চেয়ে বেশি নয় কথা বলেছেন।';

  @override
  String get areYouThere => 'আপনি কি সেখানে আছেন?';

  @override
  String get noSpeechDesc => 'আমরা কোনো কথা সনাক্ত করতে পারিনি। কমপক্ষে 10 সেকেন্ড এবং 3 মিনিটের বেশি নয় কথা বলুন।';

  @override
  String get connectionLost => 'সংযোগ হারিয়ে গেছে';

  @override
  String get connectionLostDesc => 'সংযোগ বাধাগ্রস্ত হয়েছে। আপনার ইন্টারনেট সংযোগ পরীক্ষা করুন এবং আবার চেষ্টা করুন।';

  @override
  String get tryAgain => 'আবার চেষ্টা করুন';

  @override
  String get connectOmiOmiGlass => 'Omi / OmiGlass সংযোগ করুন';

  @override
  String get continueWithoutDevice => 'ডিভাইস ছাড়াই চালিয়ে যান';

  @override
  String get permissionsRequired => 'অনুমতি প্রয়োজন';

  @override
  String get permissionsRequiredDesc =>
      'এই অ্যাপটি সঠিকভাবে কাজ করার জন্য Bluetooth এবং অবস্থান অনুমতি প্রয়োজন। সেটিংসে সক্ষম করুন।';

  @override
  String get openSettings => 'সেটিংস খুলুন';

  @override
  String get wantDifferentName => 'অন্য কিছু নাম পেতে চান?';

  @override
  String get whatsYourName => 'আপনার নাম কি?';

  @override
  String get speakTranscribeSummarize => 'কথা বলুন। ট্রান্সক্রাইব করুন। সংক্ষিপ্ত করুন।';

  @override
  String get signInWithApple => 'Apple দিয়ে সাইন ইন করুন';

  @override
  String get signInWithGoogle => 'Google দিয়ে সাইন ইন করুন';

  @override
  String get byContinuingAgree => 'চালিয়ে যাওয়ার মাধ্যমে আপনি সম্মত হচ্ছেন ';

  @override
  String get termsOfUse => 'ব্যবহারের শর্তাবলী';

  @override
  String get omiYourAiCompanion => 'Omi - আপনার AI সহযোগী';

  @override
  String get captureEveryMoment => 'প্রতিটি মুহূর্ত ক্যাপচার করুন। AI-চালিত সারসংক্ষেপ পান। কখনও নোট নিন না।';

  @override
  String get appleWatchSetup => 'Apple Watch সেটআপ';

  @override
  String get permissionRequestedExclaim => 'অনুমতি অনুরোধ করা হয়েছে!';

  @override
  String get microphonePermission => 'মাইক্রোফোন অনুমতি';

  @override
  String get permissionGrantedNow =>
      'অনুমতি প্রদান করা হয়েছে! এখন:\n\nআপনার ঘড়িতে Omi অ্যাপ খুলুন এবং নীচে \"চালিয়ে যান\" ট্যাপ করুন';

  @override
  String get needMicrophonePermission =>
      'আমাদের মাইক্রোফোন অনুমতি প্রয়োজন।\n\n1. \"অনুমতি প্রদান করুন\" ট্যাপ করুন\n2. আপনার iPhone এ অনুমোদন করুন\n3. ঘড়ির অ্যাপ বন্ধ হবে\n4. পুনরায় খুলুন এবং \"চালিয়ে যান\" ট্যাপ করুন';

  @override
  String get grantPermissionButton => 'অনুমতি প্রদান করুন';

  @override
  String get needHelp => 'সাহায্যের প্রয়োজন?';

  @override
  String get troubleshootingSteps =>
      'সমস্যা সমাধান:\n\n1. নিশ্চিত করুন Omi আপনার ঘড়িতে ইনস্টল করা আছে\n2. আপনার ঘড়িতে Omi অ্যাপ খুলুন\n3. অনুমতি পপআপ খুঁজুন\n4. প্রম্পট দেখা গেলে \"অনুমোদন করুন\" ট্যাপ করুন\n5. আপনার ঘড়িতে অ্যাপ বন্ধ হবে - পুনরায় খুলুন\n6. ফিরে আসুন এবং আপনার iPhone এ \"চালিয়ে যান\" ট্যাপ করুন';

  @override
  String get recordingStartedSuccessfully => 'রেকর্ডিং সফলভাবে শুরু হয়েছে!';

  @override
  String get permissionNotGrantedYet =>
      'এখনও অনুমতি প্রদান করা হয়নি। নিশ্চিত করুন যে আপনি মাইক্রোফোন অ্যাক্সেস অনুমোদন করেছেন এবং আপনার ঘড়িতে অ্যাপ পুনরায় খুলেছেন।';

  @override
  String errorRequestingPermission(String error) {
    return 'অনুমতি অনুরোধে ত্রুটি: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'রেকর্ডিং শুরু করতে ত্রুটি: $error';
  }

  @override
  String get selectPrimaryLanguage => 'আপনার প্রাথমিক ভাষা নির্বাচন করুন';

  @override
  String get languageBenefits => 'তীক্ষ্ণ ট্রান্সক্রিপশন এবং ব্যক্তিগতকৃত অভিজ্ঞতার জন্য আপনার ভাষা সেট করুন';

  @override
  String get whatsYourPrimaryLanguage => 'আপনার প্রাথমিক ভাষা কি?';

  @override
  String get selectYourLanguage => 'আপনার ভাষা নির্বাচন করুন';

  @override
  String get personalGrowthJourney => 'AI এর সাথে আপনার ব্যক্তিগত বৃদ্ধির যাত্রা যা আপনার প্রতিটি শব্দ শোনে।';

  @override
  String get actionItemsTitle => 'কাজ করার তালিকা';

  @override
  String get actionItemsDescription =>
      'সম্পাদন করতে ট্যাপ করুন • নির্বাচন করতে দীর্ঘ চাপুন • অ্যাকশনের জন্য স্যোয়াইপ করুন';

  @override
  String get tabToDo => 'করার কাজ';

  @override
  String get tabDone => 'সম্পন্ন';

  @override
  String get tabOld => 'পুরানো';

  @override
  String get emptyTodoMessage => '🎉 সব শেষ!\nকোনো অপেক্ষমাণ অ্যাকশন আইটেম নেই';

  @override
  String get emptyDoneMessage => 'এখনও কোনো সম্পন্ন আইটেম নেই';

  @override
  String get emptyOldMessage => '✅ পুরানো কাজ নেই';

  @override
  String get noItems => 'কোনো আইটেম নেই';

  @override
  String get actionItemMarkedIncomplete => 'অ্যাকশন আইটেম অসম্পূর্ণ হিসাবে চিহ্নিত করা হয়েছে';

  @override
  String get actionItemCompleted => 'অ্যাকশন আইটেম সম্পন্ন হয়েছে';

  @override
  String get deleteActionItemTitle => 'অ্যাকশন আইটেম মুছুন';

  @override
  String get deleteActionItemMessage => 'আপনি কি নিশ্চিত যে এই অ্যাকশন আইটেমটি মুছতে চান?';

  @override
  String get deleteSelectedItemsTitle => 'নির্বাচিত আইটেম মুছুন';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Are you sure you want to delete $count selected action item$s?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'অ্যাকশন আইটেম \"$description\" মুছে ফেলা হয়েছে';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count action item$s deleted';
  }

  @override
  String get failedToDeleteItem => 'অ্যাকশন আইটেম মুছতে ব্যর্থ';

  @override
  String get failedToDeleteItems => 'আইটেম মুছতে ব্যর্থ';

  @override
  String get failedToDeleteSomeItems => 'কিছু আইটেম মুছতে ব্যর্থ';

  @override
  String get welcomeActionItemsTitle => 'অ্যাকশন আইটেমের জন্য প্রস্তুত';

  @override
  String get welcomeActionItemsDescription =>
      'আপনার AI স্বয়ংক্রিয়ভাবে আপনার কথোপকথন থেকে কাজ এবং করার কাজ বের করবে। সেগুলি তৈরি হলে এখানে প্রদর্শিত হবে।';

  @override
  String get autoExtractionFeature => 'কথোপকথন থেকে স্বয়ংক্রিয়ভাবে বের করা';

  @override
  String get editSwipeFeature => 'সম্পাদন করতে ট্যাপ করুন, সম্পূর্ণ বা মুছতে স্যোয়াইপ করুন';

  @override
  String itemsSelected(int count) {
    return '$count নির্বাচিত';
  }

  @override
  String get selectAll => 'সব নির্বাচন করুন';

  @override
  String get deleteSelected => 'নির্বাচিত মুছুন';

  @override
  String get searchMemories => 'স্মৃতি অনুসন্ধান করুন...';

  @override
  String get memoryDeleted => 'স্মৃতি মুছে ফেলা হয়েছে।';

  @override
  String get undo => 'পূর্বাবস্থা';

  @override
  String get noMemoriesYet => '🧠 এখনও কোনো স্মৃতি নেই';

  @override
  String get noAutoMemories => 'এখনও কোনো স্বয়ংক্রিয়ভাবে বের করা স্মৃতি নেই';

  @override
  String get noManualMemories => 'এখনও কোনো ম্যানুয়াল স্মৃতি নেই';

  @override
  String get noMemoriesInCategories => 'এই বিভাগে কোনো স্মৃতি নেই';

  @override
  String get noMemoriesFound => '🔍 কোনো স্মৃতি পাওয়া যায়নি';

  @override
  String get addFirstMemory => 'আপনার প্রথম স্মৃতি যোগ করুন';

  @override
  String get clearMemoryTitle => 'Omi এর স্মৃতি পরিষ্কার করুন';

  @override
  String get clearMemoryMessage =>
      'আপনি কি নিশ্চিত যে আপনি Omi এর স্মৃতি পরিষ্কার করতে চান? এই অ্যাকশনটি পূর্বাবস্থা করা যাবে না।';

  @override
  String get clearMemoryButton => 'স্মৃতি পরিষ্কার করুন';

  @override
  String get memoryClearedSuccess => 'Omi এর আপনার সম্পর্কে স্মৃতি পরিষ্কার করা হয়েছে';

  @override
  String get noMemoriesToDelete => 'মুছতে কোনো স্মৃতি নেই';

  @override
  String get createMemoryTooltip => 'নতুন স্মৃতি তৈরি করুন';

  @override
  String get createActionItemTooltip => 'নতুন অ্যাকশন আইটেম তৈরি করুন';

  @override
  String get memoryManagement => 'স্মৃতি ব্যবস্থাপনা';

  @override
  String get filterMemories => 'স্মৃতি ফিল্টার করুন';

  @override
  String totalMemoriesCount(int count) {
    return 'আপনার $count মোট স্মৃতি আছে';
  }

  @override
  String get publicMemories => 'সার্বজনীন স্মৃতি';

  @override
  String get privateMemories => 'ব্যক্তিগত স্মৃতি';

  @override
  String get makeAllPrivate => 'সব স্মৃতি ব্যক্তিগত করুন';

  @override
  String get makeAllPublic => 'সব স্মৃতি সার্বজনীন করুন';

  @override
  String get deleteAllMemories => 'সব স্মৃতি মুছুন';

  @override
  String get allMemoriesPrivateResult => 'সব স্মৃতি এখন ব্যক্তিগত';

  @override
  String get allMemoriesPublicResult => 'সব স্মৃতি এখন সার্বজনীন';

  @override
  String get newMemory => '✨ নতুন স্মৃতি';

  @override
  String get editMemory => '✏️ স্মৃতি সম্পাদনা করুন';

  @override
  String get memoryContentHint => 'আমি আইসক্রিম খেতে পছন্দ করি...';

  @override
  String get failedToSaveMemory => 'সংরক্ষণ করতে ব্যর্থ। আপনার সংযোগ পরীক্ষা করুন।';

  @override
  String get saveMemory => 'স্মৃতি সংরক্ষণ করুন';

  @override
  String get retry => 'আবার চেষ্টা করুন';

  @override
  String get createActionItem => 'অ্যাকশন আইটেম তৈরি করুন';

  @override
  String get editActionItem => 'অ্যাকশন আইটেম সম্পাদনা করুন';

  @override
  String get actionItemDescriptionHint => 'কি করতে হবে?';

  @override
  String get actionItemDescriptionEmpty => 'অ্যাকশন আইটেম বর্ণনা খালি হতে পারে না।';

  @override
  String get actionItemUpdated => 'অ্যাকশন আইটেম আপডেট করা হয়েছে';

  @override
  String get failedToUpdateActionItem => 'অ্যাকশন আইটেম আপডেট করতে ব্যর্থ';

  @override
  String get actionItemCreated => 'অ্যাকশন আইটেম তৈরি করা হয়েছে';

  @override
  String get failedToCreateActionItem => 'অ্যাকশন আইটেম তৈরি করতে ব্যর্থ';

  @override
  String get dueDate => 'নির্ধারিত তারিখ';

  @override
  String get time => 'সময়';

  @override
  String get addDueDate => 'নির্ধারিত তারিখ যোগ করুন';

  @override
  String get pressDoneToSave => 'সংরক্ষণ করতে সম্পন্ন চাপুন';

  @override
  String get pressDoneToCreate => 'তৈরি করতে সম্পন্ন চাপুন';

  @override
  String get filterAll => 'সব';

  @override
  String get filterSystem => 'আপনার সম্পর্কে';

  @override
  String get filterInteresting => 'অন্তর্দৃষ্টি';

  @override
  String get filterManual => 'ম্যানুয়াল';

  @override
  String get completed => 'সম্পন্ন';

  @override
  String get markComplete => 'সম্পন্ন হিসাবে চিহ্নিত করুন';

  @override
  String get actionItemDeleted => 'অ্যাকশন আইটেম মুছে ফেলা হয়েছে';

  @override
  String get failedToDeleteActionItem => 'অ্যাকশন আইটেম মুছতে ব্যর্থ';

  @override
  String get deleteActionItemConfirmTitle => 'অ্যাকশন আইটেম মুছুন';

  @override
  String get deleteActionItemConfirmMessage => 'আপনি কি নিশ্চিত যে এই অ্যাকশন আইটেমটি মুছতে চান?';

  @override
  String get appLanguage => 'অ্যাপ ভাষা';

  @override
  String get appInterfaceSectionTitle => 'অ্যাপ ইন্টারফেস';

  @override
  String get speechTranscriptionSectionTitle => 'কথা এবং ট্রান্সক্রিপশন';

  @override
  String get languageSettingsHelperText =>
      'অ্যাপ ভাষা মেনু এবং বোতামগুলি পরিবর্তন করে। কথার ভাষা আপনার রেকর্ডিংগুলি কীভাবে ট্রান্সক্রাইব করা হয় তা প্রভাবিত করে।';

  @override
  String get translationNotice => 'অনুবাদ বিজ্ঞপ্তি';

  @override
  String get translationNoticeMessage =>
      'Omi কথোপকথনগুলি আপনার প্রাথমিক ভাষায় অনুবাদ করে। সেটিংস → প্রোফাইলে যেকোনো সময় আপডেট করুন।';

  @override
  String get pleaseCheckInternetConnection => 'আপনার ইন্টারনেট সংযোগ পরীক্ষা করুন এবং আবার চেষ্টা করুন';

  @override
  String get pleaseSelectReason => 'একটি কারণ নির্বাচন করুন';

  @override
  String get tellUsMoreWhatWentWrong => 'কি ভুল হয়েছে তা সম্পর্কে আরও বলুন...';

  @override
  String get selectText => 'পাঠ্য নির্বাচন করুন';

  @override
  String maximumGoalsAllowed(int count) {
    return 'সর্বাধিক $count লক্ষ্য অনুমোদিত';
  }

  @override
  String get conversationCannotBeMerged => 'এই কথোপকথনটি একত্রিত করা যায় না (লক করা বা ইতিমধ্যে একত্রিত করছে)';

  @override
  String get pleaseEnterFolderName => 'একটি ফোল্ডার নাম লিখুন';

  @override
  String get failedToCreateFolder => 'ফোল্ডার তৈরি করতে ব্যর্থ';

  @override
  String get failedToUpdateFolder => 'ফোল্ডার আপডেট করতে ব্যর্থ';

  @override
  String get folderName => 'ফোল্ডার নাম';

  @override
  String get descriptionOptional => 'বর্ণনা (ঐচ্ছিক)';

  @override
  String get failedToDeleteFolder => 'ফোল্ডার মুছতে ব্যর্থ হয়েছে';

  @override
  String get editFolder => 'ফোল্ডার সম্পাদনা করুন';

  @override
  String get deleteFolder => 'ফোল্ডার মুছুন';

  @override
  String get transcriptCopiedToClipboard => 'ট্রান্সক্রিপ্ট ক্লিপবোর্ডে অনুলিপি করা হয়েছে';

  @override
  String get summaryCopiedToClipboard => 'সারাংশ ক্লিপবোর্ডে অনুলিপি করা হয়েছে';

  @override
  String get conversationUrlCouldNotBeShared => 'কথোপকথনের URL শেয়ার করা যায়নি।';

  @override
  String get urlCopiedToClipboard => 'URL ক্লিপবোর্ডে অনুলিপি করা হয়েছে';

  @override
  String get exportTranscript => 'ট্রান্সক্রিপ্ট রপ্তানি করুন';

  @override
  String get exportSummary => 'সারাংশ রপ্তানি করুন';

  @override
  String get exportButton => 'রপ্তানি করুন';

  @override
  String get actionItemsCopiedToClipboard => 'কর্মপরিকল্পনা ক্লিপবোর্ডে অনুলিপি করা হয়েছে';

  @override
  String get summarize => 'সংক্ষিপ্ত করুন';

  @override
  String get generateSummary => 'সারাংশ তৈরি করুন';

  @override
  String get conversationNotFoundOrDeleted => 'কথোপকথন পাওয়া যায়নি বা মুছে ফেলা হয়েছে';

  @override
  String get deleteMemory => 'স্মৃতি মুছুন';

  @override
  String get thisActionCannotBeUndone => 'এই পদক্ষেপ পূর্বাবস্থায় ফেরানো যাবে না।';

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
  String get noMemoriesInCategory => 'এই বিভাগে এখনো কোনো স্মৃতি নেই';

  @override
  String get addYourFirstMemory => 'আপনার প্রথম স্মৃতি যোগ করুন';

  @override
  String get firmwareDisconnectUsb => 'USB বিচ্ছিন্ন করুন';

  @override
  String get firmwareUsbWarning => 'আপডেট সময় USB সংযোগ আপনার ডিভাইস ক্ষতিগ্রস্ত করতে পারে।';

  @override
  String get firmwareBatteryAbove15 => 'ব্যাটারি ১৫% এর উপরে';

  @override
  String get firmwareEnsureBattery => 'আপনার ডিভাইসে ১৫% ব্যাটারি নিশ্চিত করুন।';

  @override
  String get firmwareStableConnection => 'স্থিতিশীল সংযোগ';

  @override
  String get firmwareConnectWifi => 'Wi-Fi বা সেলুলার এ সংযুক্ত করুন।';

  @override
  String failedToStartUpdate(String error) {
    return 'আপডেট শুরু করতে ব্যর্থ হয়েছে: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'আপডেটের আগে নিশ্চিত করুন:';

  @override
  String get confirmed => 'নিশ্চিত করা হয়েছে!';

  @override
  String get release => 'প্রকাশনী';

  @override
  String get slideToUpdate => 'আপডেট করতে স্লাইড করুন';

  @override
  String copiedToClipboard(String title) {
    return '$title ক্লিপবোর্ডে অনুলিপি করা হয়েছে';
  }

  @override
  String get batteryLevel => 'ব্যাটারি স্তর';

  @override
  String get charging => 'চার্জ হচ্ছে';

  @override
  String get productUpdate => 'পণ্য আপডেট';

  @override
  String get offline => 'অফলাইন';

  @override
  String get available => 'উপলব্ধ';

  @override
  String get unpairDeviceDialogTitle => 'ডিভাইস আনপেয়ার করুন';

  @override
  String get unpairDeviceDialogMessage =>
      'এটি ডিভাইসটিকে আনপেয়ার করবে যাতে এটি অন্য ফোনের সাথে সংযুক্ত হতে পারে। প্রক্রিয়াটি সম্পূর্ণ করতে আপনাকে সেটিংস > ব্লুটুথ এ যেতে হবে এবং ডিভাইসটি ভুলে যেতে হবে।';

  @override
  String get unpair => 'আনপেয়ার করুন';

  @override
  String get unpairAndForgetDevice => 'ডিভাইস আনপেয়ার এবং ভুলে যান';

  @override
  String get unknownDevice => 'অজানা';

  @override
  String get unknown => 'অজানা';

  @override
  String get productName => 'পণ্যের নাম';

  @override
  String get serialNumber => 'সিরিয়াল নম্বর';

  @override
  String get connected => 'সংযুক্ত';

  @override
  String get privacyPolicyTitle => 'গোপনীয়তা নীতি';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label অনুলিপি করা হয়েছে';
  }

  @override
  String get noApiKeysYet => 'এখনো কোনো API চাবি নেই';

  @override
  String get createKeyToGetStarted => 'শুরু করতে একটি চাবি তৈরি করুন';

  @override
  String get configureSttProvider => 'STT প্রদানকারী কনফিগার করুন';

  @override
  String get setWhenConversationsAutoEnd => 'কথোপকথন স্বয়ংক্রিয়ভাবে শেষ হওয়ার সময় নির্ধারণ করুন';

  @override
  String get importDataFromOtherSources => 'অন্যান্য উৎস থেকে ডেটা আমদানি করুন';

  @override
  String get debugAndDiagnostics => 'ডিবাগ এবং ডায়াগনস্টিক্স';

  @override
  String get autoDeletesAfter3Days => '৩ দিন পর স্বয়ংক্রিয়ভাবে মুছে যায়।';

  @override
  String get helpsDiagnoseIssues => 'সমস্যা নির্ণয়ে সাহায্য করে';

  @override
  String get exportStartedMessage => 'রপ্তানি শুরু হয়েছে। এটি কয়েক সেকেন্ড সময় নিতে পারে...';

  @override
  String get exportConversationsToJson => 'কথোপকথন JSON ফাইলে রপ্তানি করুন';

  @override
  String get knowledgeGraphDeletedSuccess => 'জ্ঞান গ্রাফ সফলভাবে মুছে ফেলা হয়েছে';

  @override
  String failedToDeleteGraph(String error) {
    return 'গ্রাফ মুছতে ব্যর্থ হয়েছে: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'সমস্ত নোড এবং সংযোগ পরিষ্কার করুন';

  @override
  String get addToClaudeDesktopConfig => 'claude_desktop_config.json এ যোগ করুন';

  @override
  String get connectAiAssistantsToData => 'AI সহায়কদের আপনার ডেটার সাথে সংযুক্ত করুন';

  @override
  String get useYourMcpApiKey => 'আপনার MCP API চাবি ব্যবহার করুন';

  @override
  String get realTimeTranscript => 'রিয়েল-টাইম ট্রান্সক্রিপ্ট';

  @override
  String get experimental => 'পরীক্ষামূলক';

  @override
  String get transcriptionDiagnostics => 'ট্রান্সক্রিপশন ডায়াগনস্টিক্স';

  @override
  String get detailedDiagnosticMessages => 'বিস্তারিত ডায়াগনস্টিক বার্তা';

  @override
  String get autoCreateSpeakers => 'স্বয়ংক্রিয় বক্তা তৈরি করুন';

  @override
  String get autoCreateWhenNameDetected => 'নাম সনাক্ত হলে স্বয়ংক্রিয়ভাবে তৈরি করুন';

  @override
  String get followUpQuestions => 'অনুসরণকারী প্রশ্ন';

  @override
  String get suggestQuestionsAfterConversations => 'কথোপকথনের পরে প্রশ্নের পরামর্শ দিন';

  @override
  String get goalTracker => 'লক্ষ্য ট্র্যাকার';

  @override
  String get trackPersonalGoalsOnHomepage => 'হোমপেজে ব্যক্তিগত লক্ষ্য ট্র্যাক করুন';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'কর্মপরিকল্পনার বর্ণনা খালি হতে পারে না';

  @override
  String get saved => 'সংরক্ষিত';

  @override
  String get overdue => 'বকেয়া';

  @override
  String get failedToUpdateDueDate => 'ডু ডেট আপডেট করতে ব্যর্থ হয়েছে';

  @override
  String get markIncomplete => 'অসম্পূর্ণ হিসাবে চিহ্নিত করুন';

  @override
  String get editDueDate => 'ডু ডেট সম্পাদনা করুন';

  @override
  String get setDueDate => 'ডু ডেট নির্ধারণ করুন';

  @override
  String get clearDueDate => 'ডু ডেট সাফ করুন';

  @override
  String get failedToClearDueDate => 'ডু ডেট সাফ করতে ব্যর্থ হয়েছে';

  @override
  String get mondayAbbr => 'সোম';

  @override
  String get tuesdayAbbr => 'মঙ্গল';

  @override
  String get wednesdayAbbr => 'বুধ';

  @override
  String get thursdayAbbr => 'বৃহ';

  @override
  String get fridayAbbr => 'শুক্র';

  @override
  String get saturdayAbbr => 'শনি';

  @override
  String get sundayAbbr => 'রবি';

  @override
  String get howDoesItWork => 'এটি কীভাবে কাজ করে?';

  @override
  String get sdCardSyncDescription => 'SD কার্ড সিঙ্ক আপনার স্মৃতি SD কার্ড থেকে অ্যাপে আমদানি করবে';

  @override
  String get checksForAudioFiles => 'SD কার্ডে অডিও ফাইল পরীক্ষা করে';

  @override
  String get omiSyncsAudioFiles => 'Omi তারপর অডিও ফাইল সার্ভারের সাথে সিঙ্ক করে';

  @override
  String get serverProcessesAudio => 'সার্ভার অডিও ফাইল প্রক্রিয়া করে এবং স্মৃতি তৈরি করে';

  @override
  String get youreAllSet => 'আপনি সব প্রস্তুত!';

  @override
  String get welcomeToOmiDescription =>
      'Omi তে স্বাগতম! আপনার AI সহায়ক কথোপকথন, কাজ এবং আরও অনেক কিছুতে আপনাকে সাহায্য করতে প্রস্তুত।';

  @override
  String get startUsingOmi => 'Omi ব্যবহার শুরু করুন';

  @override
  String get back => 'পিছনে';

  @override
  String get keyboardShortcuts => 'কীবোর্ড শর্টকাট';

  @override
  String get toggleControlBar => 'নিয়ন্ত্রণ বার টগল করুন';

  @override
  String get pressKeys => 'কী চাপুন...';

  @override
  String get cmdRequired => '⌘ প্রয়োজন';

  @override
  String get invalidKey => 'অবৈধ কী';

  @override
  String get space => 'স্পেস';

  @override
  String get search => 'অনুসন্ধান';

  @override
  String get searchPlaceholder => 'অনুসন্ধান...';

  @override
  String get untitledConversation => 'শিরোনামহীন কথোপকথন';

  @override
  String countRemaining(String count) {
    return '$count অবশিষ্ট';
  }

  @override
  String get addGoal => 'লক্ষ্য যোগ করুন';

  @override
  String get editGoal => 'লক্ষ্য সম্পাদনা করুন';

  @override
  String get icon => 'আইকন';

  @override
  String get goalTitle => 'লক্ষ্যের শিরোনাম';

  @override
  String get current => 'বর্তমান';

  @override
  String get target => 'লক্ষ্য';

  @override
  String get saveGoal => 'সংরক্ষণ করুন';

  @override
  String get goals => 'লক্ষ্য';

  @override
  String get tapToAddGoal => 'লক্ষ্য যোগ করতে ট্যাপ করুন';

  @override
  String welcomeBack(String name) {
    return '$name, আপনাকে স্বাগতম';
  }

  @override
  String get yourConversations => 'আপনার কথোপকথন';

  @override
  String get reviewAndManageConversations => 'আপনার ক্যাপচার করা কথোপকথন পর্যালোচনা এবং পরিচালনা করুন';

  @override
  String get startCapturingConversations => 'Omi ডিভাইসের সাথে কথোপকথন ক্যাপচার করা শুরু করুন এখানে দেখতে।';

  @override
  String get useMobileAppToCapture => 'অডিও ক্যাপচার করতে আপনার মোবাইল অ্যাপ ব্যবহার করুন';

  @override
  String get conversationsProcessedAutomatically => 'কথোপকথন স্বয়ংক্রিয়ভাবে প্রক্রিয়া করা হয়';

  @override
  String get getInsightsInstantly => 'তাৎক্ষণিকভাবে অন্তর্দৃষ্টি এবং সারাংশ পান';

  @override
  String get showAll => 'সব দেখান';

  @override
  String get noTasksForToday => 'আজ কোনো কাজ নেই।\nOmi-কে আরও কাজের জন্য জিজ্ঞাসা করুন বা ম্যানুয়ালি তৈরি করুন।';

  @override
  String get dailyScore => 'দৈনিক স্কোর';

  @override
  String get dailyScoreDescription => 'একটি স্কোর যা আপনাকে আরও ভাল\nকার্যকর করতে সাহায্য করে।';

  @override
  String get searchResults => 'অনুসন্ধান ফলাফল';

  @override
  String get actionItems => 'কর্মপরিকল্পনা';

  @override
  String get tasksToday => 'আজ';

  @override
  String get tasksTomorrow => 'আগামীকাল';

  @override
  String get tasksNoDeadline => 'কোনো সময়সীমা নেই';

  @override
  String get tasksLater => 'পরে';

  @override
  String get loadingTasks => 'কাজ লোড হচ্ছে...';

  @override
  String get tasks => 'কাজ';

  @override
  String get swipeTasksToIndent => 'কাজ ইন্ডেন্ট করতে সোয়াইপ করুন, বিভাগের মধ্যে টেনে আনুন';

  @override
  String get create => 'তৈরি করুন';

  @override
  String get noTasksYet => 'এখনো কোনো কাজ নেই';

  @override
  String get tasksFromConversationsWillAppear =>
      'আপনার কথোপকথন থেকে কাজ এখানে প্রদর্শিত হবে।\nএক্স ক্লিক করুন ম্যানুয়ালি একটি যোগ করতে।';

  @override
  String get monthJan => 'জানু';

  @override
  String get monthFeb => 'ফেব';

  @override
  String get monthMar => 'মার্চ';

  @override
  String get monthApr => 'এপ্রি';

  @override
  String get monthMay => 'মে';

  @override
  String get monthJun => 'জুন';

  @override
  String get monthJul => 'জুলা';

  @override
  String get monthAug => 'আগ';

  @override
  String get monthSep => 'সেপ্ট';

  @override
  String get monthOct => 'অক্টো';

  @override
  String get monthNov => 'নভে';

  @override
  String get monthDec => 'ডিসে';

  @override
  String get timePM => 'অপরাহ্ন';

  @override
  String get timeAM => 'পূর্বাহ্ন';

  @override
  String get actionItemUpdatedSuccessfully => 'কর্মপরিকল্পনা সফলভাবে আপডেট করা হয়েছে';

  @override
  String get actionItemCreatedSuccessfully => 'কর্মপরিকল্পনা সফলভাবে তৈরি করা হয়েছে';

  @override
  String get actionItemDeletedSuccessfully => 'কর্মপরিকল্পনা সফলভাবে মুছে ফেলা হয়েছে';

  @override
  String get deleteActionItem => 'কর্মপরিকল্পনা মুছুন';

  @override
  String get deleteActionItemConfirmation =>
      'আপনি কি এই কর্মপরিকল্পনা মুছতে নিশ্চিত? এই পদক্ষেপ পূর্বাবস্থায় ফেরানো যাবে না।';

  @override
  String get enterActionItemDescription => 'কর্মপরিকল্পনা বর্ণনা লিখুন...';

  @override
  String get markAsCompleted => 'সম্পূর্ণ হিসাবে চিহ্নিত করুন';

  @override
  String get setDueDateAndTime => 'ডু ডেট এবং সময় নির্ধারণ করুন';

  @override
  String get reloadingApps => 'অ্যাপ্লিকেশন পুনরায় লোড হচ্ছে...';

  @override
  String get loadingApps => 'অ্যাপ্লিকেশন লোড হচ্ছে...';

  @override
  String get browseInstallCreateApps => 'অ্যাপ ব্রাউজ করুন, ইনস্টল করুন এবং তৈরি করুন';

  @override
  String get all => 'সব';

  @override
  String get open => 'খুলুন';

  @override
  String get install => 'ইনস্টল করুন';

  @override
  String get noAppsAvailable => 'কোনো অ্যাপ উপলব্ধ নেই';

  @override
  String get unableToLoadApps => 'অ্যাপ লোড করতে অক্ষম';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'আপনার অনুসন্ধান শর্ত বা ফিল্টার সামঞ্জস্য করার চেষ্টা করুন';

  @override
  String get checkBackLaterForNewApps => 'নতুন অ্যাপের জন্য পরে ফিরে দেখুন';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'আপনার ইন্টারনেট সংযোগ পরীক্ষা করুন এবং আবার চেষ্টা করুন';

  @override
  String get createNewApp => 'নতুন অ্যাপ তৈরি করুন';

  @override
  String get buildSubmitCustomOmiApp => 'কাস্টম Omi অ্যাপ তৈরি এবং জমা দিন';

  @override
  String get submittingYourApp => 'আপনার অ্যাপ জমা দিচ্ছেন...';

  @override
  String get preparingFormForYou => 'আপনার জন্য ফর্ম প্রস্তুত করছেন...';

  @override
  String get appDetails => 'অ্যাপ বিবরণ';

  @override
  String get paymentDetails => 'পেমেন্ট বিবরণ';

  @override
  String get previewAndScreenshots => 'প্রিভিউ এবং স্ক্রিনশট';

  @override
  String get appCapabilities => 'অ্যাপ ক্ষমতা';

  @override
  String get aiPrompts => 'AI প্রম্পট';

  @override
  String get chatPrompt => 'চ্যাট প্রম্পট';

  @override
  String get chatPromptPlaceholder =>
      'আপনি একটি দুর্দান্ত অ্যাপ, আপনার কাজ ব্যবহারকারীর প্রশ্নের উত্তর দেওয়া এবং তাদের ভালো অনুভব করান...';

  @override
  String get conversationPrompt => 'কথোপকথন প্রম্পট';

  @override
  String get conversationPromptPlaceholder =>
      'আপনি একটি দুর্দান্ত অ্যাপ, আপনাকে একটি কথোপকথনের ট্রান্সক্রিপ্ট এবং সারাংশ দেওয়া হবে...';

  @override
  String get notificationScopes => 'বিজ্ঞপ্তি স্কোপ';

  @override
  String get appPrivacyAndTerms => 'অ্যাপ গোপনীয়তা এবং শর্তাবলী';

  @override
  String get makeMyAppPublic => 'আমার অ্যাপ জনসাধারণের জন্য উপলব্ধ করুন';

  @override
  String get submitAppTermsAgreement => 'এই অ্যাপ জমা দিয়ে, আমি Omi AI পরিষেবার শর্তাবলী এবং গোপনীয়তা নীতিতে সম্মত';

  @override
  String get submitApp => 'অ্যাপ জমা দিন';

  @override
  String get needHelpGettingStarted => 'শুরু করতে সাহায্য দরকার?';

  @override
  String get clickHereForAppBuildingGuides => 'অ্যাপ তৈরির নির্দেশিকা এবং ডকুমেন্টেশনের জন্য এখানে ক্লিক করুন';

  @override
  String get submitAppQuestion => 'অ্যাপ জমা দিতে?';

  @override
  String get submitAppPublicDescription =>
      'আপনার অ্যাপ পর্যালোচনা করা হবে এবং জনসাধারণ উপলব্ধ করা হবে। পর্যালোচনার সময়ও আপনি এটি অবিলম্বে ব্যবহার শুরু করতে পারেন!';

  @override
  String get submitAppPrivateDescription =>
      'আপনার অ্যাপ পর্যালোচনা করা হবে এবং আপনার কাছে ব্যক্তিগতভাবে উপলব্ধ করা হবে। পর্যালোচনার সময়ও আপনি এটি অবিলম্বে ব্যবহার শুরু করতে পারেন!';

  @override
  String get startEarning => 'উপার্জন শুরু করুন! 💰';

  @override
  String get connectStripeOrPayPal => 'আপনার অ্যাপের জন্য পেমেন্ট পেতে Stripe বা PayPal সংযুক্ত করুন।';

  @override
  String get connectNow => 'এখনই সংযুক্ত করুন';

  @override
  String get installsCount => 'ইনস্টল';

  @override
  String get uninstallApp => 'অ্যাপ আনইনস্টল করুন';

  @override
  String get subscribe => 'সাবস্ক্রাইব করুন';

  @override
  String get dataAccessNotice => 'ডেটা অ্যাক্সেস বিজ্ঞপ্তি';

  @override
  String get dataAccessWarning =>
      'এই অ্যাপ আপনার ডেটা অ্যাক্সেস করবে। Omi AI এই অ্যাপের দ্বারা আপনার ডেটা কীভাবে ব্যবহার, পরিবর্তন বা মুছে ফেলা হয় তার জন্য দায়বদ্ধ নয়';

  @override
  String get installApp => 'অ্যাপ ইনস্টল করুন';

  @override
  String get betaTesterNotice => 'আপনি এই অ্যাপের বিটা পরীক্ষক। এটি এখনো জনসাধারণ নয়। এটি অনুমোদিত হলে জনসাধারণ হবে।';

  @override
  String get appUnderReviewOwner =>
      'আপনার অ্যাপ পর্যালোচনা অধীনে এবং শুধুমাত্র আপনার কাছে দৃশ্যমান। এটি অনুমোদিত হলে জনসাধারণ হবে।';

  @override
  String get appRejectedNotice =>
      'আপনার অ্যাপ প্রত্যাখ্যান করা হয়েছে। দয়া করে অ্যাপ বিবরণ আপডেট করুন এবং পুনর্মূল্যায়নের জন্য পুনরায় জমা দিন।';

  @override
  String get setupSteps => 'সেটআপ ধাপ';

  @override
  String get setupInstructions => 'সেটআপ নির্দেশ';

  @override
  String get integrationInstructions => 'একীকরণ নির্দেশ';

  @override
  String get preview => 'প্রিভিউ';

  @override
  String get aboutTheApp => 'অ্যাপ সম্পর্কে';

  @override
  String get chatPersonality => 'চ্যাট ব্যক্তিত্ব';

  @override
  String get ratingsAndReviews => 'রেটিং এবং পর্যালোচনা';

  @override
  String get noRatings => 'কোনো রেটিং নেই';

  @override
  String ratingsCount(String count) {
    return '$count+ রেটিং';
  }

  @override
  String get errorActivatingApp => 'অ্যাপ সক্রিয় করতে ত্রুটি';

  @override
  String get integrationSetupRequired => 'যদি এটি একটি একীকরণ অ্যাপ হয়, তবে নিশ্চিত করুন সেটআপ সম্পূর্ণ হয়েছে।';

  @override
  String get installed => 'ইনস্টল করা হয়েছে';

  @override
  String get appIdLabel => 'অ্যাপ আইডি';

  @override
  String get appNameLabel => 'অ্যাপের নাম';

  @override
  String get appNamePlaceholder => 'আমার দুর্দান্ত অ্যাপ';

  @override
  String get pleaseEnterAppName => 'দয়া করে অ্যাপের নাম লিখুন';

  @override
  String get categoryLabel => 'বিভাগ';

  @override
  String get selectCategory => 'বিভাগ নির্বাচন করুন';

  @override
  String get descriptionLabel => 'বর্ণনা';

  @override
  String get appDescriptionPlaceholder =>
      'আমার দুর্দান্ত অ্যাপ একটি দুর্দান্ত অ্যাপ যা অসাধারণ কাজ করে। এটি সর্বোত্তম অ্যাপ!';

  @override
  String get pleaseProvideValidDescription => 'দয়া করে একটি বৈধ বর্ণনা প্রদান করুন';

  @override
  String get appPricingLabel => 'অ্যাপ মূল্য';

  @override
  String get noneSelected => 'কোনো নির্বাচিত নেই';

  @override
  String get appIdCopiedToClipboard => 'অ্যাপ আইডি ক্লিপবোর্ডে অনুলিপি করা হয়েছে';

  @override
  String get appCategoryModalTitle => 'অ্যাপ বিভাগ';

  @override
  String get pricingFree => 'বিনামূল্যে';

  @override
  String get pricingPaid => 'প্রদত্ত';

  @override
  String get loadingCapabilities => 'ক্ষমতা লোড হচ্ছে...';

  @override
  String get filterInstalled => 'ইনস্টল করা হয়েছে';

  @override
  String get filterMyApps => 'আমার অ্যাপ';

  @override
  String get clearSelection => 'নির্বাচন সাফ করুন';

  @override
  String get filterCategory => 'বিভাগ';

  @override
  String get rating4PlusStars => '৪+ তারকা';

  @override
  String get rating3PlusStars => '৩+ তারকা';

  @override
  String get rating2PlusStars => '২+ তারকা';

  @override
  String get rating1PlusStars => '১+ তারকা';

  @override
  String get filterRating => 'রেটিং';

  @override
  String get filterCapabilities => 'ক্ষমতা';

  @override
  String get noNotificationScopesAvailable => 'কোনো বিজ্ঞপ্তি স্কোপ উপলব্ধ নেই';

  @override
  String get popularApps => 'জনপ্রিয় অ্যাপ';

  @override
  String get pleaseProvidePrompt => 'দয়া করে একটি প্রম্পট প্রদান করুন';

  @override
  String chatWithAppName(String appName) {
    return '$appName এর সাথে চ্যাট করুন';
  }

  @override
  String get defaultAiAssistant => 'ডিফল্ট AI সহায়ক';

  @override
  String get readyToChat => '✨ চ্যাট করতে প্রস্তুত!';

  @override
  String get connectionNeeded => '🌐 সংযোগ প্রয়োজন';

  @override
  String get startConversation => 'একটি কথোপকথন শুরু করুন এবং জাদু শুরু করুন';

  @override
  String get checkInternetConnection => 'আপনার ইন্টারনেট সংযোগ পরীক্ষা করুন';

  @override
  String get wasThisHelpful => 'এটি কি সাহায্যকর ছিল?';

  @override
  String get thankYouForFeedback => 'আপনার প্রতিক্রিয়ার জন্য ধন্যবাদ!';

  @override
  String get maxFilesUploadError => 'আপনি একবারে শুধুমাত্র ৪টি ফাইল আপলোড করতে পারেন';

  @override
  String get attachedFiles => '📎 সংযুক্ত ফাইল';

  @override
  String get takePhoto => 'ছবি তুলুন';

  @override
  String get captureWithCamera => 'ক্যামেরায় ক্যাপচার করুন';

  @override
  String get selectImages => 'ছবি নির্বাচন করুন';

  @override
  String get chooseFromGallery => 'গ্যালারি থেকে চয়ন করুন';

  @override
  String get selectFile => 'একটি ফাইল নির্বাচন করুন';

  @override
  String get chooseAnyFileType => 'যেকোনো ফাইল টাইপ চয়ন করুন';

  @override
  String get cannotReportOwnMessages => 'আপনি নিজের বার্তা রিপোর্ট করতে পারবেন না';

  @override
  String get messageReportedSuccessfully => '✅ বার্তা সফলভাবে রিপোর্ট করা হয়েছে';

  @override
  String get confirmReportMessage => 'আপনি কি এই বার্তা রিপোর্ট করতে নিশ্চিত?';

  @override
  String get selectChatAssistant => 'চ্যাট সহায়ক নির্বাচন করুন';

  @override
  String get enableMoreApps => 'আরও অ্যাপ সক্ষম করুন';

  @override
  String get chatCleared => 'চ্যাট সাফ করা হয়েছে';

  @override
  String get clearChatTitle => 'চ্যাট সাফ করুন?';

  @override
  String get confirmClearChat => 'আপনি কি চ্যাট সাফ করতে নিশ্চিত? এই পদক্ষেপ পূর্বাবস্থায় ফেরানো যাবে না।';

  @override
  String get copy => 'অনুলিপি করুন';

  @override
  String get share => 'শেয়ার করুন';

  @override
  String get report => 'রিপোর্ট করুন';

  @override
  String get microphonePermissionRequired => 'কল করার জন্য মাইক্রোফোন অনুমতি প্রয়োজন';

  @override
  String get microphonePermissionDenied =>
      'মাইক্রোফোন অনুমতি অস্বীকার করা হয়েছে। সিস্টেম পছন্দ > গোপনীয়তা এবং নিরাপত্তা > মাইক্রোফোন এ অনুমতি দিন।';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'মাইক্রোফোন অনুমতি পরীক্ষা করতে ব্যর্থ হয়েছে: $error';
  }

  @override
  String get failedToTranscribeAudio => 'অডিও ট্রান্সক্রাইব করতে ব্যর্থ হয়েছে';

  @override
  String get transcribing => 'ট্রান্সক্রাইব করছেন...';

  @override
  String get transcriptionFailed => 'ট্রান্সক্রিপশন ব্যর্থ হয়েছে';

  @override
  String get discardedConversation => 'বাতিল করা কথোপকথন';

  @override
  String get at => 'এ';

  @override
  String get from => 'থেকে';

  @override
  String get copied => 'অনুলিপি করা হয়েছে!';

  @override
  String get copyLink => 'লিঙ্ক অনুলিপি করুন';

  @override
  String get hideTranscript => 'ট্রান্সক্রিপ্ট লুকান';

  @override
  String get viewTranscript => 'ট্রান্সক্রিপ্ট দেখুন';

  @override
  String get conversationDetails => 'কথোপকথন বিবরণ';

  @override
  String get transcript => 'ট্রান্সক্রিপ্ট';

  @override
  String segmentsCount(int count) {
    return '$count সেগমেন্ট';
  }

  @override
  String get noTranscriptAvailable => 'কোনো ট্রান্সক্রিপ্ট উপলব্ধ নেই';

  @override
  String get noTranscriptMessage => 'এই কথোপকথনে কোনো ট্রান্সক্রিপ্ট নেই।';

  @override
  String get conversationUrlCouldNotBeGenerated => 'কথোপকথন URL তৈরি করা যায়নি।';

  @override
  String get failedToGenerateConversationLink => 'কথোপকথন লিঙ্ক তৈরি করতে ব্যর্থ হয়েছে';

  @override
  String get failedToGenerateShareLink => 'শেয়ার লিঙ্ক তৈরি করতে ব্যর্থ হয়েছে';

  @override
  String get reloadingConversations => 'কথোপকথন পুনরায় লোড হচ্ছে...';

  @override
  String get user => 'ব্যবহারকারী';

  @override
  String get starred => 'অনুপ্রাণিত';

  @override
  String get date => 'তারিখ';

  @override
  String get noResultsFound => 'কোনো ফলাফল পাওয়া যায়নি';

  @override
  String get tryAdjustingSearchTerms => 'আপনার অনুসন্ধান শর্ত সামঞ্জস্য করার চেষ্টা করুন';

  @override
  String get starConversationsToFindQuickly => 'দ্রুত খুঁজে পেতে কথোপকথনে তারকা লাগান';

  @override
  String noConversationsOnDate(String date) {
    return '$date এ কোনো কথোপকথন নেই';
  }

  @override
  String get trySelectingDifferentDate => 'অন্য তারিখ নির্বাচনের চেষ্টা করুন';

  @override
  String get conversations => 'কথোপকথন';

  @override
  String get chat => 'চ্যাট';

  @override
  String get actions => 'পদক্ষেপ';

  @override
  String get syncAvailable => 'সিঙ্ক উপলব্ধ';

  @override
  String get referAFriend => 'একটি বন্ধুকে রেফার করুন';

  @override
  String get help => 'সাহায্য';

  @override
  String get pro => 'প্রো';

  @override
  String get upgradeToPro => 'প্রো-তে আপগ্রেড করুন';

  @override
  String get getOmiDevice => 'Omi ডিভাইস পান';

  @override
  String get wearableAiCompanion => 'পরিধানযোগ্য AI সঙ্গী';

  @override
  String get loadingMemories => 'স্মৃতি লোড হচ্ছে...';

  @override
  String get allMemories => 'সব স্মৃতি';

  @override
  String get aboutYou => 'আপনার সম্পর্কে';

  @override
  String get manual => 'ম্যানুয়াল';

  @override
  String get loadingYourMemories => 'আপনার স্মৃতি লোড হচ্ছে...';

  @override
  String get createYourFirstMemory => 'শুরু করতে আপনার প্রথম স্মৃতি তৈরি করুন';

  @override
  String get tryAdjustingFilter => 'আপনার অনুসন্ধান বা ফিল্টার সামঞ্জস্য করার চেষ্টা করুন';

  @override
  String get whatWouldYouLikeToRemember => 'আপনি কী মনে রাখতে চান?';

  @override
  String get category => 'বিভাগ';

  @override
  String get public => 'জনসাধারণ';

  @override
  String get failedToSaveCheckConnection => 'সংরক্ষণ করতে ব্যর্থ। আপনার সংযোগ পরীক্ষা করুন।';

  @override
  String get createMemory => 'স্মৃতি তৈরি করুন';

  @override
  String get deleteMemoryConfirmation => 'আপনি কি এই স্মৃতি মুছতে নিশ্চিত? এই পদক্ষেপ পূর্বাবস্থায় ফেরানো যাবে না।';

  @override
  String get makePrivate => 'ব্যক্তিগত করুন';

  @override
  String get organizeAndControlMemories => 'আপনার স্মৃতি সংগঠিত এবং নিয়ন্ত্রণ করুন';

  @override
  String get total => 'মোট';

  @override
  String get makeAllMemoriesPrivate => 'সব স্মৃতি ব্যক্তিগত করুন';

  @override
  String get setAllMemoriesToPrivate => 'সব স্মৃতি ব্যক্তিগত দৃশ্যমানতায় সেট করুন';

  @override
  String get makeAllMemoriesPublic => 'সব স্মৃতি জনসাধারণ করুন';

  @override
  String get setAllMemoriesToPublic => 'সব স্মৃতি জনসাধারণ দৃশ্যমানতায় সেট করুন';

  @override
  String get permanentlyRemoveAllMemories => 'Omi থেকে সব স্মৃতি স্থায়ীভাবে সরান';

  @override
  String get allMemoriesAreNowPrivate => 'সব স্মৃতি এখন ব্যক্তিগত';

  @override
  String get allMemoriesAreNowPublic => 'সব স্মৃতি এখন জনসাধারণ';

  @override
  String get clearOmisMemory => 'Omi এর স্মৃতি সাফ করুন';

  @override
  String clearMemoryConfirmation(int count) {
    return 'আপনি কি Omi এর স্মৃতি সাফ করতে নিশ্চিত? এই পদক্ষেপ পূর্বাবস্থায় ফেরানো যাবে না এবং সব $count স্মৃতি স্থায়ীভাবে মুছে ফেলবে।';
  }

  @override
  String get omisMemoryCleared => 'আপনার সম্পর্কে Omi এর স্মৃতি সাফ করা হয়েছে';

  @override
  String get welcomeToOmi => 'Omi এ স্বাগতম';

  @override
  String get continueWithApple => 'Apple দিয়ে চালিয়ে যান';

  @override
  String get continueWithGoogle => 'Google দিয়ে চালিয়ে যান';

  @override
  String get byContinuingYouAgree => 'চালিয়ে গিয়ে আপনি আমাদের ';

  @override
  String get termsOfService => 'সেবার শর্তাবলী';

  @override
  String get and => ' এবং ';

  @override
  String get dataAndPrivacy => 'ডেটা ও গোপনীয়তা';

  @override
  String get secureAuthViaAppleId => 'Apple ID এর মাধ্যমে নিরাপদ প্রমাণীকরণ';

  @override
  String get secureAuthViaGoogleAccount => 'Google অ্যাকাউন্ট এর মাধ্যমে নিরাপদ প্রমাণীকরণ';

  @override
  String get whatWeCollect => 'আমরা কী সংগ্রহ করি';

  @override
  String get dataCollectionMessage =>
      'চালিয়ে গিয়ে, আপনার কথোপকথন, রেকর্ডিং এবং ব্যক্তিগত তথ্য আমাদের সার্ভারে নিরাপদে সংরক্ষণ করা হবে যাতে AI-চালিত অন্তর্দৃষ্টি প্রদান করা যায় এবং সমস্ত অ্যাপ বৈশিষ্ট্য সক্ষম করা যায়।';

  @override
  String get dataProtection => 'ডেটা সুরক্ষা';

  @override
  String get yourDataIsProtected => 'আপনার ডেটা আমাদের ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'অনুগ্রহ করে আপনার প্রাথমিক ভাষা নির্বাচন করুন';

  @override
  String get chooseYourLanguage => 'আপনার ভাষা বেছে নিন';

  @override
  String get selectPreferredLanguageForBestExperience => 'সেরা Omi অভিজ্ঞতার জন্য আপনার পছন্দের ভাষা নির্বাচন করুন';

  @override
  String get searchLanguages => 'ভাষা অনুসন্ধান করুন...';

  @override
  String get selectALanguage => 'একটি ভাষা নির্বাচন করুন';

  @override
  String get tryDifferentSearchTerm => 'অন্য একটি অনুসন্ধান শব্দ চেষ্টা করুন';

  @override
  String get pleaseEnterYourName => 'অনুগ্রহ করে আপনার নাম প্রবেশ করুন';

  @override
  String get nameMustBeAtLeast2Characters => 'নাম কমপক্ষে ২ অক্ষরের হতে হবে';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'আমাদের বলুন আপনি কীভাবে সম্বোধিত হতে চান। এটি আপনার Omi অভিজ্ঞতা ব্যক্তিগতকৃত করতে সাহায্য করে।';

  @override
  String charactersCount(int count) {
    return '$count অক্ষর';
  }

  @override
  String get enableFeaturesForBestExperience => 'আপনার ডিভাইসে সেরা Omi অভিজ্ঞতার জন্য বৈশিষ্ট্য সক্ষম করুন।';

  @override
  String get microphoneAccess => 'মাইক্রোফোন অ্যাক্সেস';

  @override
  String get recordAudioConversations => 'অডিও কথোপকথন রেকর্ড করুন';

  @override
  String get microphoneAccessDescription =>
      'Omi আপনার কথোপকথন রেকর্ড করতে এবং ট্রান্সক্রিপশন প্রদান করতে মাইক্রোফোন অ্যাক্সেসের প্রয়োজন।';

  @override
  String get screenRecording => 'স্ক্রিন রেকর্ডিং';

  @override
  String get captureSystemAudioFromMeetings => 'মিটিং থেকে সিস্টেম অডিও ক্যাপচার করুন';

  @override
  String get screenRecordingDescription =>
      'Omi আপনার ব্রাউজার-ভিত্তিক মিটিং থেকে সিস্টেম অডিও ক্যাপচার করতে স্ক্রিন রেকর্ডিং অনুমতির প্রয়োজন।';

  @override
  String get accessibility => 'অ্যাক্সেসযোগ্যতা';

  @override
  String get detectBrowserBasedMeetings => 'ব্রাউজার-ভিত্তিক মিটিং সনাক্ত করুন';

  @override
  String get accessibilityDescription =>
      'Omi আপনার ব্রাউজারে Zoom, Meet বা Teams মিটিং যোগদানের সময় সনাক্ত করতে অ্যাক্সেসযোগ্যতা অনুমতির প্রয়োজন।';

  @override
  String get pleaseWait => 'অনুগ্রহ করে অপেক্ষা করুন...';

  @override
  String get joinTheCommunity => 'সম্প্রদায়ে যোগ দিন!';

  @override
  String get loadingProfile => 'প্রোফাইল লোড করা হচ্ছে...';

  @override
  String get profileSettings => 'প্রোফাইল সেটিংস';

  @override
  String get noEmailSet => 'কোনো ইমেল সেট করা হয়নি';

  @override
  String get userIdCopiedToClipboard => 'ব্যবহারকারী ID ক্লিপবোর্ডে কপি করা হয়েছে';

  @override
  String get yourInformation => 'আপনার তথ্য';

  @override
  String get setYourName => 'আপনার নাম সেট করুন';

  @override
  String get changeYourName => 'আপনার নাম পরিবর্তন করুন';

  @override
  String get voiceAndPeople => 'ভয়েস ও মানুষ';

  @override
  String get teachOmiYourVoice => 'Omi কে আপনার কণ্ঠস্বর শেখান';

  @override
  String get tellOmiWhoSaidIt => 'Omi কে বলুন এটি কে বলেছে 🗣️';

  @override
  String get payment => 'পেমেন্ট';

  @override
  String get addOrChangeYourPaymentMethod => 'আপনার পেমেন্ট পদ্ধতি যোগ বা পরিবর্তন করুন';

  @override
  String get preferences => 'পছন্দসমূহ';

  @override
  String get helpImproveOmiBySharing => 'বেনামে বিশ্লেষণ ডেটা শেয়ার করে Omi উন্নত করতে সহায়তা করুন';

  @override
  String get deleteAccount => 'অ্যাকাউন্ট মুছুন';

  @override
  String get deleteYourAccountAndAllData => 'আপনার অ্যাকাউন্ট এবং সমস্ত ডেটা মুছুন';

  @override
  String get clearLogs => 'লগ সাফ করুন';

  @override
  String get debugLogsCleared => 'ডিবাগ লগ সাফ করা হয়েছে';

  @override
  String get exportConversations => 'কথোপকথন রপ্তানি করুন';

  @override
  String get exportAllConversationsToJson => 'আপনার সমস্ত কথোপকথন একটি JSON ফাইলে রপ্তানি করুন।';

  @override
  String get conversationsExportStarted =>
      'কথোপকথন রপ্তানি শুরু হয়েছে। এটি কয়েক সেকেন্ড সময় নিতে পারে, অনুগ্রহ করে অপেক্ষা করুন।';

  @override
  String get mcpDescription =>
      'Omi কে অন্যান্য অ্যাপ্লিকেশনের সাথে সংযুক্ত করতে আপনার স্মৃতি এবং কথোপকথন পড়তে, অনুসন্ধান করতে এবং পরিচালনা করতে। শুরু করতে একটি কী তৈরি করুন।';

  @override
  String get apiKeys => 'API চাবি';

  @override
  String errorLabel(String error) {
    return 'ত্রুটি: $error';
  }

  @override
  String get noApiKeysFound => 'কোনো API চাবি পাওয়া যায়নি। শুরু করতে একটি তৈরি করুন।';

  @override
  String get advancedSettings => 'উন্নত সেটিংস';

  @override
  String get triggersWhenNewConversationCreated => 'যখন একটি নতুন কথোপকথন তৈরি হয় তখন ট্রিগার হয়।';

  @override
  String get triggersWhenNewTranscriptReceived => 'যখন একটি নতুন ট্রান্সক্রিপ্ট গ্রহণ করা হয় তখন ট্রিগার হয়।';

  @override
  String get realtimeAudioBytes => 'রিয়েল-টাইম অডিও বাইট';

  @override
  String get triggersWhenAudioBytesReceived => 'যখন অডিও বাইট গ্রহণ করা হয় তখন ট্রিগার হয়।';

  @override
  String get everyXSeconds => 'প্রতি x সেকেন্ডে';

  @override
  String get triggersWhenDaySummaryGenerated => 'যখন দিনের সারসংক্ষেপ তৈরি হয় তখন ট্রিগার হয়।';

  @override
  String get tryLatestExperimentalFeatures => 'Omi দল থেকে সর্বশেষ পরীক্ষামূলক বৈশিষ্ট্য চেষ্টা করুন।';

  @override
  String get transcriptionServiceDiagnosticStatus => 'ট্রান্সক্রিপশন সেবা নির্ণয়বহুল অবস্থা';

  @override
  String get enableDetailedDiagnosticMessages => 'ট্রান্সক্রিপশন সেবা থেকে বিস্তারিত নির্ণয়বহুল বার্তা সক্ষম করুন';

  @override
  String get autoCreateAndTagNewSpeakers => 'নতুন স্পিকার স্বয়ংক্রিয়ভাবে তৈরি এবং ট্যাগ করুন';

  @override
  String get automaticallyCreateNewPerson =>
      'ট্রান্সক্রিপ্টে একটি নাম সনাক্ত হলে স্বয়ংক্রিয়ভাবে একটি নতুন ব্যক্তি তৈরি করুন।';

  @override
  String get pilotFeatures => 'পাইলট বৈশিষ্ট্য';

  @override
  String get pilotFeaturesDescription => 'এই বৈশিষ্ট্যগুলি পরীক্ষা এবং কোনো সহায়তার গ্যারান্টি নেই।';

  @override
  String get suggestFollowUpQuestion => 'অনুসরণকারী প্রশ্নের পরামর্শ দিন';

  @override
  String get saveSettings => 'সেটিংস সংরক্ষণ করুন';

  @override
  String get syncingDeveloperSettings => 'ডেভেলপার সেটিংস সিঙ্ক করা হচ্ছে...';

  @override
  String get summary => 'সারসংক্ষেপ';

  @override
  String get auto => 'স্বয়ংক্রিয়';

  @override
  String get noSummaryForApp => 'এই অ্যাপের জন্য কোনো সারসংক্ষেপ উপলব্ধ নেই। ভাল ফলাফলের জন্য অন্য অ্যাপ চেষ্টা করুন।';

  @override
  String get tryAnotherApp => 'অন্য অ্যাপ চেষ্টা করুন';

  @override
  String generatedBy(String appName) {
    return '$appName দ্বারা তৈরি';
  }

  @override
  String get overview => 'সারমর্ম';

  @override
  String get otherAppResults => 'অন্যান্য অ্যাপ ফলাফল';

  @override
  String get unknownApp => 'অজ্ঞাত অ্যাপ';

  @override
  String get noSummaryAvailable => 'কোনো সারসংক্ষেপ উপলব্ধ নেই';

  @override
  String get conversationNoSummaryYet => 'এই কথোপকথনের এখনও কোনো সারসংক্ষেপ নেই।';

  @override
  String get chooseSummarizationApp => 'সারসংক্ষেপ অ্যাপ চয়ন করুন';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName ডিফল্ট সারসংক্ষেপ অ্যাপ হিসাবে সেট করা হয়েছে';
  }

  @override
  String get letOmiChooseAutomatically => 'Omi কে স্বয়ংক্রিয়ভাবে সেরা অ্যাপ বেছে নিতে দিন';

  @override
  String get deleteConversationConfirmation => 'আপনি কি এই কথোপকথন মুছতে চান? এই পদক্ষেপ পূর্বাবস্থায় ফেরানো যায় না।';

  @override
  String get conversationDeleted => 'কথোপকথন মুছে ফেলা হয়েছে';

  @override
  String get generatingLink => 'লিঙ্ক তৈরি করা হচ্ছে...';

  @override
  String get editConversation => 'কথোপকথন সম্পাদনা করুন';

  @override
  String get conversationLinkCopiedToClipboard => 'কথোপকথন লিঙ্ক ক্লিপবোর্ডে কপি করা হয়েছে';

  @override
  String get conversationTranscriptCopiedToClipboard => 'কথোপকথন ট্রান্সক্রিপ্ট ক্লিপবোর্ডে কপি করা হয়েছে';

  @override
  String get editConversationDialogTitle => 'কথোপকথন সম্পাদনা করুন';

  @override
  String get changeTheConversationTitle => 'কথোপকথনের শিরোনাম পরিবর্তন করুন';

  @override
  String get conversationTitle => 'কথোপকথনের শিরোনাম';

  @override
  String get enterConversationTitle => 'কথোপকথনের শিরোনাম লিখুন...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'কথোপকথনের শিরোনাম সফলভাবে আপডেট করা হয়েছে';

  @override
  String get failedToUpdateConversationTitle => 'কথোপকথনের শিরোনাম আপডেট করতে ব্যর্থ';

  @override
  String get errorUpdatingConversationTitle => 'কথোপকথনের শিরোনাম আপডেট করতে ত্রুটি';

  @override
  String get settingUp => 'সেটআপ করা হচ্ছে...';

  @override
  String get startYourFirstRecording => 'আপনার প্রথম রেকর্ডিং শুরু করুন';

  @override
  String get preparingSystemAudioCapture => 'সিস্টেম অডিও ক্যাপচার প্রস্তুত করা হচ্ছে';

  @override
  String get clickTheButtonToCaptureAudio =>
      'লাইভ ট্রান্সক্রিপ্ট, AI অন্তর্দৃষ্টি এবং স্বয়ংক্রিয় সংরক্ষণের জন্য অডিও ক্যাপচার করতে বোতাম ক্লিক করুন।';

  @override
  String get reconnecting => 'পুনরায় সংযোগ করা হচ্ছে...';

  @override
  String get recordingPaused => 'রেকর্ডিং বিরাম';

  @override
  String get recordingActive => 'রেকর্ডিং সক্রিয়';

  @override
  String get startRecording => 'রেকর্ডিং শুরু করুন';

  @override
  String resumingInCountdown(String countdown) {
    return '${countdown}s এ চালু হবে...';
  }

  @override
  String get tapPlayToResume => 'চালু করতে প্লে ট্যাপ করুন';

  @override
  String get listeningForAudio => 'অডিওর জন্য শোনা হচ্ছে...';

  @override
  String get preparingAudioCapture => 'অডিও ক্যাপচার প্রস্তুত করা হচ্ছে';

  @override
  String get clickToBeginRecording => 'রেকর্ডিং শুরু করতে ক্লিক করুন';

  @override
  String get translated => 'অনুবাদিত';

  @override
  String get liveTranscript => 'লাইভ ট্রান্সক্রিপ্ট';

  @override
  String segmentsSingular(String count) {
    return '$count সেগমেন্ট';
  }

  @override
  String segmentsPlural(String count) {
    return '$count সেগমেন্ট';
  }

  @override
  String get startRecordingToSeeTranscript => 'লাইভ ট্রান্সক্রিপ্ট দেখতে রেকর্ডিং শুরু করুন';

  @override
  String get paused => 'বিরাম';

  @override
  String get initializing => 'শুরু করা হচ্ছে...';

  @override
  String get recording => 'রেকর্ডিং';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'মাইক্রোফোন পরিবর্তিত হয়েছে। ${countdown}s এ চালু হবে';
  }

  @override
  String get clickPlayToResumeOrStop => 'চালু করতে বা বন্ধ করতে প্লে ক্লিক করুন';

  @override
  String get settingUpSystemAudioCapture => 'সিস্টেম অডিও ক্যাপচার সেটআপ করা হচ্ছে';

  @override
  String get capturingAudioAndGeneratingTranscript => 'অডিও ক্যাপচার এবং ট্রান্সক্রিপ্ট তৈরি করা হচ্ছে';

  @override
  String get clickToBeginRecordingSystemAudio => 'সিস্টেম অডিও রেকর্ডিং শুরু করতে ক্লিক করুন';

  @override
  String get you => 'আপনি';

  @override
  String speakerWithId(String speakerId) {
    return 'স্পিকার $speakerId';
  }

  @override
  String get translatedByOmi => 'omi দ্বারা অনুবাদিত';

  @override
  String get backToConversations => 'কথোপকথনে ফিরুন';

  @override
  String get systemAudio => 'সিস্টেম';

  @override
  String get mic => 'মাইক';

  @override
  String audioInputSetTo(String deviceName) {
    return 'অডিও ইনপুট $deviceName এ সেট করা হয়েছে';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'অডিও ডিভাইস স্যুইচ করতে ত্রুটি: $error';
  }

  @override
  String get selectAudioInput => 'অডিও ইনপুট নির্বাচন করুন';

  @override
  String get loadingDevices => 'ডিভাইস লোড করা হচ্ছে...';

  @override
  String get settingsHeader => 'সেটিংস';

  @override
  String get plansAndBilling => 'পরিকল্পনা ও বিলিং';

  @override
  String get calendarIntegration => 'ক্যালেন্ডার ইন্টিগ্রেশন';

  @override
  String get dailySummary => 'দৈনিক সারসংক্ষেপ';

  @override
  String get developer => 'ডেভেলপার';

  @override
  String get about => 'সম্পর্কে';

  @override
  String get selectTime => 'সময় নির্বাচন করুন';

  @override
  String get accountGroup => 'অ্যাকাউন্ট';

  @override
  String get signOutQuestion => 'সাইন আউট করবেন?';

  @override
  String get signOutConfirmation => 'আপনি কি সাইন আউট করতে চান?';

  @override
  String get customVocabularyHeader => 'কাস্টম শব্দভান্ডার';

  @override
  String get addWordsDescription => 'এমন শব্দ যোগ করুন যা Omi ট্রান্সক্রিপশনের সময় স্বীকৃতি দেওয়া উচিত।';

  @override
  String get enterWordsHint => 'শব্দ লিখুন (কমা দ্বারা পৃথক)';

  @override
  String get dailySummaryHeader => 'দৈনিক সারসংক্ষেপ';

  @override
  String get dailySummaryTitle => 'দৈনিক সারসংক্ষেপ';

  @override
  String get dailySummaryDescription => 'আপনার দিনের কথোপকথনের একটি ব্যক্তিগতকৃত সারসংক্ষেপ বিজ্ঞপ্তি হিসাবে পান।';

  @override
  String get deliveryTime => 'ডেলিভারি সময়';

  @override
  String get deliveryTimeDescription => 'আপনার দৈনিক সারসংক্ষেপ কখন পাবেন';

  @override
  String get subscription => 'সাবস্ক্রিপশন';

  @override
  String get viewPlansAndUsage => 'পরিকল্পনা এবং ব্যবহার দেখুন';

  @override
  String get viewPlansDescription => 'আপনার সাবস্ক্রিপশন পরিচালনা করুন এবং ব্যবহার পরিসংখ্যান দেখুন';

  @override
  String get addOrChangePaymentMethod => 'আপনার পেমেন্ট পদ্ধতি যোগ বা পরিবর্তন করুন';

  @override
  String get displayOptions => 'প্রদর্শনী অপশন';

  @override
  String get showMeetingsInMenuBar => 'মেনু বারে মিটিং দেখান';

  @override
  String get displayUpcomingMeetingsDescription => 'মেনু বারে আসন্ন মিটিং প্রদর্শন করুন';

  @override
  String get showEventsWithoutParticipants => 'অংশগ্রহণকারী ছাড়া ইভেন্ট দেখান';

  @override
  String get includePersonalEventsDescription => 'কোনো উপস্থিতি ছাড়াই ব্যক্তিগত ইভেন্ট অন্তর্ভুক্ত করুন';

  @override
  String get upcomingMeetings => 'আসন্ন মিটিং';

  @override
  String get checkingNext7Days => 'পরবর্তী ৭ দিন পরীক্ষা করা হচ্ছে';

  @override
  String get shortcuts => 'শর্টকাট';

  @override
  String get shortcutChangeInstruction => 'এটি পরিবর্তন করতে একটি শর্টকাট ক্লিক করুন। বাতিল করতে Escape চাপুন।';

  @override
  String get configureSTTProvider => 'STT প্রদানকারী কনফিগার করুন';

  @override
  String get setConversationEndDescription => 'কথোপকথন কখন স্বয়ংক্রিয়ভাবে শেষ হবে তা সেট করুন';

  @override
  String get importDataDescription => 'অন্যান্য উত্স থেকে ডেটা আমদানি করুন';

  @override
  String get exportConversationsDescription => 'কথোপকথন JSON-এ রপ্তানি করুন';

  @override
  String get exportingConversations => 'কথোপকথন রপ্তানি করা হচ্ছে...';

  @override
  String get clearNodesDescription => 'সমস্ত নোড এবং সংযোগ সাফ করুন';

  @override
  String get deleteKnowledgeGraphQuestion => 'জ্ঞান গ্রাফ মুছবেন?';

  @override
  String get deleteKnowledgeGraphWarning =>
      'এটি সমস্ত উদ্ভূত জ্ঞান গ্রাফ ডেটা মুছে ফেলবে। আপনার মূল স্মৃতি নিরাপদ থাকে।';

  @override
  String get connectOmiWithAI => 'Omi কে AI সহায়কদের সাথে সংযুক্ত করুন';

  @override
  String get noAPIKeys => 'কোনো API চাবি নেই। শুরু করতে একটি তৈরি করুন।';

  @override
  String get autoCreateWhenDetected => 'নাম সনাক্ত হলে স্বয়ংক্রিয় তৈরি করুন';

  @override
  String get trackPersonalGoals => 'হোমপেজে ব্যক্তিগত লক্ষ্য ট্র্যাক করুন';

  @override
  String get endpointURL => 'এন্ডপয়েন্ট URL';

  @override
  String get links => 'লিঙ্ক';

  @override
  String get discordMemberCount => 'Discord-এ ৮০০০+ সদস্য';

  @override
  String get userInformation => 'ব্যবহারকারী তথ্য';

  @override
  String get capabilities => 'ক্ষমতা';

  @override
  String get previewScreenshots => 'স্ক্রিনশট প্রিভিউ করুন';

  @override
  String get holdOnPreparingForm => 'অপেক্ষা করুন, আমরা আপনার জন্য ফর্ম প্রস্তুত করছি';

  @override
  String get bySubmittingYouAgreeToOmi => 'জমা দিয়ে আপনি Omi ';

  @override
  String get termsAndPrivacyPolicy => 'শর্তাবলী ও গোপনীয়তা নীতিতে সম্মত হন';

  @override
  String get helpsDiagnoseIssuesAutoDeletes => 'সমস্যা নির্ণয়ে সহায়তা করে। ৩ দিন পরে স্বয়ংক্রিয়ভাবে মুছে যায়।';

  @override
  String get manageYourApp => 'আপনার অ্যাপ পরিচালনা করুন';

  @override
  String get updatingYourApp => 'আপনার অ্যাপ আপডেট করা হচ্ছে';

  @override
  String get fetchingYourAppDetails => 'আপনার অ্যাপের বিবরণ আনছি';

  @override
  String get updateAppQuestion => 'অ্যাপ আপডেট করবেন?';

  @override
  String get updateAppConfirmation =>
      'আপনি কি আপনার অ্যাপ আপডেট করতে চান? আমাদের দল দ্বারা পর্যালোচনা করার পরে পরিবর্তনগুলি প্রতিফলিত হবে।';

  @override
  String get updateApp => 'অ্যাপ আপডেট করুন';

  @override
  String get createAndSubmitNewApp => 'একটি নতুন অ্যাপ তৈরি এবং জমা দিন';

  @override
  String appsCount(String count) {
    return 'অ্যাপ ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'ব্যক্তিগত অ্যাপ ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'সর্বজনীন অ্যাপ ($count)';
  }

  @override
  String get newVersionAvailable => 'নতুন সংস্করণ উপলব্ধ 🎉';

  @override
  String get no => 'না';

  @override
  String get subscriptionCancelledSuccessfully =>
      'সাবস্ক্রিপশন সফলভাবে বাতিল করা হয়েছে। এটি বর্তমান বিলিং সময়ের শেষ পর্যন্ত সক্রিয় থাকবে।';

  @override
  String get failedToCancelSubscription => 'সাবস্ক্রিপশন বাতিল করতে ব্যর্থ। অনুগ্রহ করে আবার চেষ্টা করুন।';

  @override
  String get invalidPaymentUrl => 'অকার্যকর পেমেন্ট URL';

  @override
  String get permissionsAndTriggers => 'অনুমতি ও ট্রিগার';

  @override
  String get chatFeatures => 'চ্যাট বৈশিষ্ট্য';

  @override
  String get uninstall => 'আনইনস্টল করুন';

  @override
  String get installs => 'ইনস্টল';

  @override
  String get priceLabel => 'মূল্য';

  @override
  String get updatedLabel => 'আপডেট করা হয়েছে';

  @override
  String get createdLabel => 'তৈরি করা হয়েছে';

  @override
  String get featuredLabel => 'বৈশিষ্ট্যযুক্ত';

  @override
  String get cancelSubscriptionQuestion => 'সাবস্ক্রিপশন বাতিল করবেন?';

  @override
  String get cancelSubscriptionConfirmation =>
      'আপনি কি আপনার সাবস্ক্রিপশন বাতিল করতে চান? আপনি আপনার বর্তমান বিলিং সময়ের শেষ পর্যন্ত অ্যাক্সেস চালিয়ে যাবেন।';

  @override
  String get cancelSubscriptionButton => 'সাবস্ক্রিপশন বাতিল করুন';

  @override
  String get cancelling => 'বাতিল করা হচ্ছে...';

  @override
  String get betaTesterMessage =>
      'আপনি এই অ্যাপের একজন বিটা পরীক্ষক। এটি এখনও জনসাধারণের জন্য নেই। অনুমোদিত হলে এটি জনসাধারণের জন্য থাকবে।';

  @override
  String get appUnderReviewMessage =>
      'আপনার অ্যাপ পর্যালোচনার অধীন এবং শুধুমাত্র আপনার কাছে দৃশ্যমান। অনুমোদিত হলে এটি জনসাধারণের জন্য থাকবে।';

  @override
  String get appRejectedMessage =>
      'আপনার অ্যাপ প্রত্যাখ্যান করা হয়েছে। অনুগ্রহ করে অ্যাপের বিবরণ আপডেট করুন এবং পর্যালোচনার জন্য পুনরায় জমা দিন।';

  @override
  String get invalidIntegrationUrl => 'অকার্যকর ইন্টিগ্রেশন URL';

  @override
  String get tapToComplete => 'সম্পূর্ণ করতে ট্যাপ করুন';

  @override
  String get invalidSetupInstructionsUrl => 'অকার্যকর সেটআপ নির্দেশাবলী URL';

  @override
  String get pushToTalk => 'কথা বলতে চাপুন';

  @override
  String get summaryPrompt => 'সারসংক্ষেপ প্রম্পট';

  @override
  String get pleaseSelectARating => 'অনুগ্রহ করে একটি রেটিং নির্বাচন করুন';

  @override
  String get reviewAddedSuccessfully => 'পর্যালোচনা সফলভাবে যোগ করা হয়েছে 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'পর্যালোচনা সফলভাবে আপডেট করা হয়েছে 🚀';

  @override
  String get failedToSubmitReview => 'পর্যালোচনা জমা দিতে ব্যর্থ। অনুগ্রহ করে আবার চেষ্টা করুন।';

  @override
  String get addYourReview => 'আপনার পর্যালোচনা যোগ করুন';

  @override
  String get editYourReview => 'আপনার পর্যালোচনা সম্পাদনা করুন';

  @override
  String get writeAReviewOptional => 'একটি পর্যালোচনা লিখুন (ঐচ্ছিক)';

  @override
  String get submitReview => 'পর্যালোচনা জমা দিন';

  @override
  String get updateReview => 'পর্যালোচনা আপডেট করুন';

  @override
  String get yourReview => 'আপনার পর্যালোচনা';

  @override
  String get anonymousUser => 'বেনামে ব্যবহারকারী';

  @override
  String get issueActivatingApp => 'এই অ্যাপ সক্রিয় করতে একটি সমস্যা হয়েছিল। অনুগ্রহ করে আবার চেষ্টা করুন।';

  @override
  String get dataAccessNoticeDescription =>
      'এই অ্যাপ আপনার ডেটা অ্যাক্সেস করবে। Omi AI এই অ্যাপটি আপনার ডেটা কীভাবে ব্যবহার, সংশোধন বা মুছে ফেলে তার জন্য দায়বদ্ধ নয়';

  @override
  String get copyUrl => 'URL কপি করুন';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => 'সোম';

  @override
  String get weekdayTue => 'মঙ্গল';

  @override
  String get weekdayWed => 'বুধ';

  @override
  String get weekdayThu => 'বৃহস্পতি';

  @override
  String get weekdayFri => 'শুক্র';

  @override
  String get weekdaySat => 'শনি';

  @override
  String get weekdaySun => 'রবি';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return '$serviceName ইন্টিগ্রেশন শীঘ্রই আসছে';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'ইতিমধ্যে $platform এ রপ্তানি করা হয়েছে';
  }

  @override
  String get anotherPlatform => 'অন্য প্ল্যাটফর্ম';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'অনুগ্রহ করে সেটিংস > কাজ ইন্টিগ্রেশনে $serviceName দিয়ে প্রমাণীকরণ করুন';
  }

  @override
  String addingToService(String serviceName) {
    return '$serviceName এ যোগ করা হচ্ছে...';
  }

  @override
  String addedToService(String serviceName) {
    return '$serviceName এ যোগ করা হয়েছে';
  }

  @override
  String failedToAddToService(String serviceName) {
    return '$serviceName এ যোগ করতে ব্যর্থ';
  }

  @override
  String get permissionDeniedForAppleReminders => 'Apple Reminders এর জন্য অনুমতি অস্বীকার করা হয়েছে';

  @override
  String failedToCreateApiKey(String error) {
    return 'প্রদানকারী API চাবি তৈরি করতে ব্যর্থ: $error';
  }

  @override
  String get createAKey => 'একটি চাবি তৈরি করুন';

  @override
  String get apiKeyRevokedSuccessfully => 'API চাবি সফলভাবে প্রত্যাহার করা হয়েছে';

  @override
  String failedToRevokeApiKey(String error) {
    return 'API চাবি প্রত্যাহার করতে ব্যর্থ: $error';
  }

  @override
  String get omiApiKeys => 'Omi API চাবি';

  @override
  String get apiKeysDescription =>
      'API চাবি ব্যবহার করা হয় যখন আপনার অ্যাপ OMI সার্ভারের সাথে যোগাযোগ করে প্রমাণীকরণের জন্য। তারা আপনার অ্যাপ্লিকেশনকে স্মৃতি তৈরি করতে এবং অন্যান্য OMI সেবা নিরাপদে অ্যাক্সেস করতে দেয়।';

  @override
  String get aboutOmiApiKeys => 'Omi API চাবি সম্পর্কে';

  @override
  String get yourNewKey => 'আপনার নতুন চাবি:';

  @override
  String get copyToClipboard => 'ক্লিপবোর্ডে কপি করুন';

  @override
  String get pleaseCopyKeyNow => 'অনুগ্রহ করে এখন এটি কপি করুন এবং নিরাপদ জায়গায় লিখে রাখুন। ';

  @override
  String get willNotSeeAgain => 'আপনি এটি আর দেখতে পাবেন না।';

  @override
  String get revokeKey => 'চাবি প্রত্যাহার করুন';

  @override
  String get revokeApiKeyQuestion => 'API চাবি প্রত্যাহার করবেন?';

  @override
  String get revokeApiKeyWarning =>
      'এই পদক্ষেপ পূর্বাবস্থায় ফেরানো যায় না। এই চাবি ব্যবহার করে কোনো অ্যাপ্লিকেশন API অ্যাক্সেস করতে পারবে না।';

  @override
  String get revoke => 'প্রত্যাহার করুন';

  @override
  String get whatWouldYouLikeToCreate => 'আপনি কী তৈরি করতে চান?';

  @override
  String get createAnApp => 'একটি অ্যাপ তৈরি করুন';

  @override
  String get createAndShareYourApp => 'আপনার অ্যাপ তৈরি এবং শেয়ার করুন';

  @override
  String get itemApp => 'অ্যাপ';

  @override
  String keepItemPublic(String item) {
    return '$item সর্বজনীন রাখুন';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return '$item সর্বজনীন করবেন?';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return '$item ব্যক্তিগত করবেন?';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'যদি আপনি $item সর্বজনীন করেন তবে এটি সবাই ব্যবহার করতে পারবে';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'যদি আপনি এখন $item ব্যক্তিগত করেন তবে এটি সবার জন্য কাজ করা বন্ধ করবে এবং শুধুমাত্র আপনার কাছে দৃশ্যমান হবে';
  }

  @override
  String get manageApp => 'অ্যাপ পরিচালনা করুন';

  @override
  String deleteItemTitle(String item) {
    return '$item মুছুন';
  }

  @override
  String deleteItemQuestion(String item) {
    return '$item মুছবেন?';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'আপনি কি এই $item মুছতে চান? এই পদক্ষেপ পূর্বাবস্থায় ফেরানো যায় না।';
  }

  @override
  String get revokeKeyQuestion => 'চাবি প্রত্যাহার করবেন?';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'আপনি কি \"$keyName\" চাবি প্রত্যাহার করতে চান? এই পদক্ষেপ পূর্বাবস্থায় ফেরানো যায় না।';
  }

  @override
  String get createNewKey => 'নতুন চাবি তৈরি করুন';

  @override
  String get keyNameHint => 'যেমন, Claude Desktop';

  @override
  String get pleaseEnterAName => 'অনুগ্রহ করে একটি নাম লিখুন।';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'চাবি তৈরি করতে ব্যর্থ: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'চাবি তৈরি করতে ব্যর্থ। অনুগ্রহ করে আবার চেষ্টা করুন।';

  @override
  String get keyCreated => 'চাবি তৈরি হয়েছে';

  @override
  String get keyCreatedMessage =>
      'আপনার নতুন চাবি তৈরি করা হয়েছে। অনুগ্রহ করে এখন এটি কপি করুন। আপনি এটি আর দেখতে পাবেন না।';

  @override
  String get keyWord => 'চাবি';

  @override
  String get externalAppAccess => 'বাহ্যিক অ্যাপ অ্যাক্সেস';

  @override
  String get externalAppAccessDescription =>
      'নিম্নলিখিত ইনস্টল করা অ্যাপগুলির বাহ্যিক ইন্টিগ্রেশন রয়েছে এবং আপনার কথোপকথন এবং স্মৃতি সহ আপনার ডেটা অ্যাক্সেস করতে পারে।';

  @override
  String get noExternalAppsHaveAccess => 'কোনো বাহ্যিক অ্যাপের আপনার ডেটায় অ্যাক্সেস নেই।';

  @override
  String get maximumSecurityE2ee => 'সর্বোচ্চ নিরাপত্তা (E2EE)';

  @override
  String get e2eeDescription =>
      'এন্ড-টু-এন্ড এনক্রিপশন গোপনীয়তার স্বর্ণ মান। সক্ষম হলে, আপনার ডেটা আপনার ডিভাইসে এনক্রিপ্ট করা হয় তারপর আমাদের সার্ভারে পাঠানো হয়। এর মানে কেউ, এমনকি Omi ও, আপনার বিষয়বস্তু অ্যাক্সেস করতে পারে না।';

  @override
  String get importantTradeoffs => 'গুরুত্বপূর্ণ পারস্পরিক সম্পর্ক:';

  @override
  String get e2eeTradeoff1 => '• বাহ্যিক অ্যাপ ইন্টিগ্রেশনের মতো কিছু বৈশিষ্ট্য অক্ষম করা যেতে পারে।';

  @override
  String get e2eeTradeoff2 => '• যদি আপনি আপনার পাসওয়ার্ড হারান তবে আপনার ডেটা পুনরুদ্ধার করা যায় না।';

  @override
  String get featureComingSoon => 'এই বৈশিষ্ট্য শীঘ্রই আসছে!';

  @override
  String get migrationInProgressMessage =>
      'স্থানান্তর চলছে। এটি সম্পূর্ণ না হওয়া পর্যন্ত আপনি সুরক্ষা স্তর পরিবর্তন করতে পারবেন না।';

  @override
  String get migrationFailed => 'স্থানান্তর ব্যর্থ';

  @override
  String migratingFromTo(String source, String target) {
    return '$source থেকে $target এ স্থানান্তর করা হচ্ছে';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total অবজেক্ট';
  }

  @override
  String get secureEncryption => 'নিরাপদ এনক্রিপশন';

  @override
  String get secureEncryptionDescription =>
      'আপনার ডেটা Google Cloud-এ হোস্ট করা আমাদের সার্ভারে আপনার জন্য অনন্য একটি চাবি দিয়ে এনক্রিপ্ট করা হয়। এর মানে আপনার কাঁচা বিষয়বস্তু কেউ নয়, এমনকি Omi কর্মীরা বা Google, ডাটাবেস থেকে সরাসরি অ্যাক্সেস করতে পারে না।';

  @override
  String get endToEndEncryption => 'এন্ড-টু-এন্ড এনক্রিপশন';

  @override
  String get e2eeCardDescription =>
      'সর্বোচ্চ নিরাপত্তার জন্য সক্ষম করুন যেখানে শুধুমাত্র আপনি আপনার ডেটা অ্যাক্সেস করতে পারেন। আরও জানতে ট্যাপ করুন।';

  @override
  String get dataAlwaysEncrypted => 'স্তর নির্বিশেষে, আপনার ডেটা সর্বদা বিশ্রামে এবং রূপান্তরে এনক্রিপ্ট করা হয়।';

  @override
  String get readOnlyScope => 'শুধু পড়ুন';

  @override
  String get fullAccessScope => 'সম্পূর্ণ অ্যাক্সেস';

  @override
  String get readScope => 'পড়ুন';

  @override
  String get writeScope => 'লিখুন';

  @override
  String get apiKeyCreated => 'API চাবি তৈরি হয়েছে!';

  @override
  String get saveKeyWarning => 'এখনই এই চাবি সংরক্ষণ করুন! আপনি এটি আর দেখতে পাবেন না।';

  @override
  String get yourApiKey => 'আপনার API চাবি';

  @override
  String get tapToCopy => 'কপি করতে ট্যাপ করুন';

  @override
  String get copyKey => 'চাবি কপি করুন';

  @override
  String get createApiKey => 'API চাবি তৈরি করুন';

  @override
  String get accessDataProgrammatically => 'আপনার ডেটা প্রোগ্রামেটিকভাবে অ্যাক্সেস করুন';

  @override
  String get keyNameLabel => 'চাবির নাম';

  @override
  String get keyNamePlaceholder => 'যেমন, My App Integration';

  @override
  String get permissionsLabel => 'অনুমতি';

  @override
  String get permissionsInfoNote => 'R = পড়ুন, W = লিখুন। কিছু নির্বাচিত না হলে ডিফল্ট শুধু পড়ার।';

  @override
  String get developerApi => 'ডেভেলপার API';

  @override
  String get createAKeyToGetStarted => 'শুরু করতে একটি চাবি তৈরি করুন';

  @override
  String errorWithMessage(String error) {
    return 'ত্রুটি: $error';
  }

  @override
  String get omiTraining => 'Omi প্রশিক্ষণ';

  @override
  String get trainingDataProgram => 'প্রশিক্ষণ ডেটা প্রোগ্রাম';

  @override
  String get getOmiUnlimitedFree => 'AI মডেল প্রশিক্ষণের জন্য আপনার ডেটা অবদান রেখে বিনামূল্যে Omi Unlimited পান।';

  @override
  String get trainingDataBullets =>
      '• আপনার ডেটা AI মডেল উন্নত করতে সাহায্য করে\n• শুধুমাত্র অ-সংবেদনশীল ডেটা শেয়ার করা হয়\n• সম্পূর্ণ স্বচ্ছ প্রক্রিয়া';

  @override
  String get learnMoreAtOmiTraining => 'omi.me/training এ আরও জানুন';

  @override
  String get agreeToContributeData => 'আমি বুঝি এবং AI প্রশিক্ষণের জন্য আমার ডেটা অবদান রাখতে সম্মত';

  @override
  String get submitRequest => 'অনুরোধ জমা দিন';

  @override
  String get thankYouRequestUnderReview =>
      'ধন্যবাদ! আপনার অনুরোধ পর্যালোচনার অধীন। অনুমোদিত হলে আমরা আপনাকে সূচিত করব।';

  @override
  String planRemainsActiveUntil(String date) {
    return 'আপনার পরিকল্পনা $date পর্যন্ত সক্রিয় থাকবে। তারপর আপনি আপনার সীমাহীন বৈশিষ্ট্যের অ্যাক্সেস হারাবেন। আপনি কি নিশ্চিত?';
  }

  @override
  String get confirmCancellation => 'বাতিলকরণ নিশ্চিত করুন';

  @override
  String get keepMyPlan => 'আমার পরিকল্পনা রাখুন';

  @override
  String get subscriptionSetToCancel => 'আপনার সাবস্ক্রিপশন সময়ের শেষে বাতিল হওয়ার জন্য সেট করা হয়েছে।';

  @override
  String get switchedToOnDevice => 'অন-ডিভাইস ট্রান্সক্রিপশনে স্যুইচ করা হয়েছে';

  @override
  String get couldNotSwitchToFreePlan => 'বিনামূল্যে পরিকল্পনায় স্যুইচ করা যায়নি। দয়া করে আবার চেষ্টা করুন।';

  @override
  String get couldNotLoadPlans => 'উপলব্ধ পরিকল্পনা লোড করা যায়নি। দয়া করে আবার চেষ্টা করুন।';

  @override
  String get selectedPlanNotAvailable => 'নির্বাচিত পরিকল্পনা উপলব্ধ নয়। দয়া করে আবার চেষ্টা করুন।';

  @override
  String get upgradeToAnnualPlan => 'বার্ষিক পরিকল্পনায় আপগ্রেড করুন';

  @override
  String get importantBillingInfo => 'গুরুত্বপূর্ণ বিলিং তথ্য:';

  @override
  String get monthlyPlanContinues => 'আপনার বর্তমান মাসিক পরিকল্পনা আপনার বিলিং সময়কালের শেষ পর্যন্ত চলতে থাকবে';

  @override
  String get paymentMethodCharged =>
      'আপনার বিদ্যমান পেমেন্ট পদ্ধতি আপনার মাসিক পরিকল্পনা শেষ হলে স্বয়ংক্রিয়ভাবে চার্জ করা হবে';

  @override
  String get annualSubscriptionStarts => 'চার্জের পরে আপনার ১২-মাসের বার্ষিক সাবস্ক্রিপশন স্বয়ংক্রিয়ভাবে শুরু হবে';

  @override
  String get thirteenMonthsCoverage => 'আপনি মোট ১৩ মাসের কভারেজ পাবেন (বর্তমান মাস + ১২ মাসের বার্ষিক)';

  @override
  String get confirmUpgrade => 'আপগ্রেড নিশ্চিত করুন';

  @override
  String get confirmPlanChange => 'পরিকল্পনা পরিবর্তন নিশ্চিত করুন';

  @override
  String get confirmAndProceed => 'নিশ্চিত করুন ও এগিয়ে যান';

  @override
  String get upgradeScheduled => 'আপগ্রেড নির্ধারিত';

  @override
  String get changePlan => 'পরিকল্পনা পরিবর্তন করুন';

  @override
  String get upgradeAlreadyScheduled => 'আপনার বার্ষিক পরিকল্পনায় আপগ্রেড ইতিমধ্যে নির্ধারিত হয়েছে';

  @override
  String get youAreOnUnlimitedPlan => 'আপনি আনলিমিটেড পরিকল্পনায় আছেন।';

  @override
  String get yourOmiUnleashed => 'আপনার Omi, সীমাহীন। আনলিমিটেডের জন্য যান অসীম সম্ভাবনার জন্য।';

  @override
  String planEndedOn(String date) {
    return 'আপনার পরিকল্পনা $date তে শেষ হয়েছে।\\nএখনই পুনরায় সাবস্ক্রাইব করুন - একটি নতুন বিলিং সময়কালের জন্য অবিলম্বে চার্জ করা হবে।';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'আপনার পরিকল্পনা $date তে বাতিল হওয়ার জন্য নির্ধারিত হয়েছে।\\nআপনার সুবিধা রাখতে এখনই পুনরায় সাবস্ক্রাইব করুন - $date পর্যন্ত কোনও চার্জ নেই।';
  }

  @override
  String get annualPlanStartsAutomatically =>
      'আপনার মাসিক পরিকল্পনা শেষ হলে আপনার বার্ষিক পরিকল্পনা স্বয়ংক্রিয়ভাবে শুরু হবে।';

  @override
  String planRenewsOn(String date) {
    return 'আপনার পরিকল্পনা $date তে পুনর্নবীকরণ হয়।';
  }

  @override
  String get unlimitedConversations => 'অসীম কথোপকথন';

  @override
  String get askOmiAnything => 'আপনার জীবন সম্পর্কে Omi কে যেকোনো কিছু জিজ্ঞাসা করুন';

  @override
  String get unlockOmiInfiniteMemory => 'Omi এর অসীম স্মৃতি আনলক করুন';

  @override
  String get youreOnAnnualPlan => 'আপনি বার্ষিক পরিকল্পনায় আছেন';

  @override
  String get alreadyBestValuePlan => 'আপনার ইতিমধ্যে সেরা মূল্য পরিকল্পনা রয়েছে। কোনো পরিবর্তন প্রয়োজন নেই।';

  @override
  String get unableToLoadPlans => 'প্ল্যান লোড করা যায়নি';

  @override
  String get checkConnectionTryAgain => 'সংযোগ পরীক্ষা করুন এবং আবার চেষ্টা করুন';

  @override
  String get useFreePlan => 'বিনামূল্যে পরিকল্পনা ব্যবহার করুন';

  @override
  String get continueText => 'চালিয়ে যান';

  @override
  String get resubscribe => 'পুনরায় সাবস্ক্রাইব করুন';

  @override
  String get couldNotOpenPaymentSettings => 'পেমেন্ট সেটিংস খুলতে পারা যায়নি। দয়া করে আবার চেষ্টা করুন।';

  @override
  String get managePaymentMethod => 'পেমেন্ট পদ্ধতি পরিচালনা করুন';

  @override
  String get cancelSubscription => 'সাবস্ক্রিপশন বাতিল করুন';

  @override
  String endsOnDate(String date) {
    return '$date তে শেষ হয়';
  }

  @override
  String get active => 'সক্রিয়';

  @override
  String get freePlan => 'বিনামূল্যে পরিকল্পনা';

  @override
  String get configure => 'কনফিগার করুন';

  @override
  String get privacyInformation => 'গোপনীয়তা তথ্য';

  @override
  String get yourPrivacyMattersToUs => 'আপনার গোপনীয়তা আমাদের কাছে গুরুত্বপূর্ণ';

  @override
  String get privacyIntroText =>
      'Omi-তে, আমরা আপনার গোপনীয়তাকে অত্যন্ত গুরুত্ব সহকারে নিই। আমরা আমরা যে ডেটা সংগ্রহ করি এবং কীভাবে এটি ব্যবহার করি সে সম্পর্কে স্বচ্ছ হতে চাই আপনার পণ্য উন্নত করতে। এখানে আপনার যা জানা দরকার:';

  @override
  String get whatWeTrack => 'আমরা কী ট্র্যাক করি';

  @override
  String get anonymityAndPrivacy => 'গোপনীয়তা এবং অ্যানোনিমিটি';

  @override
  String get optInAndOptOutOptions => 'অপ্ট-ইন এবং অপ্ট-আউট বিকল্প';

  @override
  String get ourCommitment => 'আমাদের প্রতিশ্রুতি';

  @override
  String get commitmentText =>
      'আমরা আমরা যে ডেটা সংগ্রহ করি তা শুধুমাত্র Omi কে আপনার জন্য একটি ভাল পণ্য করতে ব্যবহার করতে প্রতিশ্রুতিবদ্ধ। আপনার গোপনীয়তা এবং বিশ্বাস আমাদের কাছে সর্বোচ্চ।';

  @override
  String get thankYouText =>
      'Omi এর একজন মূল্যবান ব্যবহারকারী হওয়ার জন্য ধন্যবাদ। যদি আপনার কোনো প্রশ্ন বা উদ্বেগ থাকে তবে আমাদের সাথে যোগাযোগ করুন team@basedhardware.com।';

  @override
  String get wifiSyncSettings => 'WiFi সিঙ্ক সেটিংস';

  @override
  String get enterHotspotCredentials => 'আপনার ফোনের হটস্পট শংসাপত্র প্রবেশ করুন';

  @override
  String get wifiSyncUsesHotspot =>
      'WiFi সিঙ্ক আপনার ফোনকে হটস্পট হিসাবে ব্যবহার করে। আপনার হটস্পট নাম এবং পাসওয়ার্ড খুঁজুন সেটিংস > ব্যক্তিগত হটস্পট এ।';

  @override
  String get hotspotNameSsid => 'হটস্পট নাম (SSID)';

  @override
  String get exampleIphoneHotspot => 'যেমন iPhone হটস্পট';

  @override
  String get password => 'পাসওয়ার্ড';

  @override
  String get enterHotspotPassword => 'হটস্পট পাসওয়ার্ড প্রবেশ করুন';

  @override
  String get saveCredentials => 'শংসাপত্র সংরক্ষণ করুন';

  @override
  String get clearCredentials => 'শংসাপত্র সাফ করুন';

  @override
  String get pleaseEnterHotspotName => 'দয়া করে একটি হটস্পট নাম প্রবেশ করুন';

  @override
  String get wifiCredentialsSaved => 'WiFi শংসাপত্র সংরক্ষিত';

  @override
  String get wifiCredentialsCleared => 'WiFi শংসাপত্র সাফ করা হয়েছে';

  @override
  String summaryGeneratedForDate(String date) {
    return '$date এর জন্য সারাংশ তৈরি হয়েছে';
  }

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'সারাংশ তৈরি করতে ব্যর্থ। নিশ্চিত করুন যে সেই দিনের জন্য আপনার কথোপকথন আছে।';

  @override
  String get summaryNotFound => 'সারাংশ পাওয়া যায়নি';

  @override
  String get yourDaysJourney => 'আপনার দিনের যাত্রা';

  @override
  String get highlights => 'হাইলাইটস';

  @override
  String get unresolvedQuestions => 'অমীমাংসিত প্রশ্ন';

  @override
  String get decisions => 'সিদ্ধান্ত';

  @override
  String get learnings => 'শিক্ষা';

  @override
  String get autoDeletesAfterThreeDays => '৩ দিনের পরে স্বয়ংক্রিয়ভাবে মুছে ফেলা হয়।';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'জ্ঞান গ্রাফ সফলভাবে মুছে ফেলা হয়েছে';

  @override
  String get exportStartedMayTakeFewSeconds => 'রপ্তানি শুরু হয়েছে। এটি কয়েক সেকেন্ড সময় নিতে পারে...';

  @override
  String get knowledgeGraphDeleteDescription =>
      'এটি সমস্ত উদ্ভূত জ্ঞান গ্রাফ ডেটা (নোড এবং সংযোগ) মুছে ফেলবে। আপনার মূল স্মৃতি নিরাপদ থাকবে। গ্রাফ সময়ের সাথে বা পরবর্তী অনুরোধে পুনর্নির্মাণ করা হবে।';

  @override
  String get configureDailySummaryDigest => 'আপনার দৈনিক পদক্ষেপ আইটেম পাচন কনফিগার করুন';

  @override
  String accessesDataTypes(String dataTypes) {
    return '$dataTypes অ্যাক্সেস করে';
  }

  @override
  String triggeredByType(String triggerType) {
    return '$triggerType দ্বারা ট্রিগার';
  }

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription এবং $triggerDescription দ্বারা ট্রিগার।';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return '$triggerDescription দ্বারা ট্রিগার।';
  }

  @override
  String get noSpecificDataAccessConfigured => 'কোনো নির্দিষ্ট ডেটা অ্যাক্সেস কনফিগার করা হয়নি।';

  @override
  String get basicPlanDescription => '১,২০০ প্রিমিয়াম মিনিট + ডিভাইসে আনলিমিটেড';

  @override
  String get minutes => 'মিনিট';

  @override
  String get omiHas => 'Omi আছে:';

  @override
  String get premiumMinutesUsed => 'প্রিমিয়াম মিনিট ব্যবহার করা হয়েছে।';

  @override
  String get setupOnDevice => 'ডিভাইসে সেটআপ করুন';

  @override
  String get forUnlimitedFreeTranscription => 'আনলিমিটেড বিনামূল্যে ট্রান্সক্রিপশনের জন্য।';

  @override
  String premiumMinsLeft(int count) {
    return '$count প্রিমিয়াম মিনিট বাকি।';
  }

  @override
  String get alwaysAvailable => 'সর্বদা উপলব্ধ।';

  @override
  String get importHistory => 'আমদানি ইতিহাস';

  @override
  String get noImportsYet => 'এখনও কোনো আমদানি নেই';

  @override
  String get selectZipFileToImport => '.zip ফাইল আমদানি করতে নির্বাচন করুন!';

  @override
  String get otherDevicesComingSoon => 'অন্যান্য ডিভাইস শীঘ্রই আসছে';

  @override
  String get deleteAllLimitlessConversations => 'সমস্ত Limitless কথোপকথন মুছুন?';

  @override
  String get deleteAllLimitlessWarning =>
      'এটি Limitless থেকে আমদানি করা সমস্ত কথোপকথন স্থায়ীভাবে মুছে ফেলবে। এই পদক্ষেপ পূর্বাবাস করা যায় না।';

  @override
  String deletedLimitlessConversations(int count) {
    return '$count Limitless কথোপকথন মুছে ফেলা হয়েছে';
  }

  @override
  String get failedToDeleteConversations => 'কথোপকথন মুছতে ব্যর্থ';

  @override
  String get deleteImportedData => 'আমদানি করা ডেটা মুছুন';

  @override
  String get statusPending => 'অপেক্ষমাণ';

  @override
  String get statusProcessing => 'প্রক্রিয়াজনীকরণ';

  @override
  String get statusCompleted => 'সম্পন্ন';

  @override
  String get statusFailed => 'ব্যর্থ';

  @override
  String nConversations(int count) {
    return '$count কথোপকথন';
  }

  @override
  String get pleaseEnterName => 'দয়া করে একটি নাম প্রবেশ করুন';

  @override
  String get nameMustBeBetweenCharacters => 'নাম ২ থেকে ৪০ অক্ষরের মধ্যে হতে হবে';

  @override
  String get deleteSampleQuestion => 'নমুনা মুছুন?';

  @override
  String deleteSampleConfirmation(String name) {
    return 'আপনি কি নিশ্চিত যে আপনি $name এর নমুনা মুছতে চান?';
  }

  @override
  String get confirmDeletion => 'মুছা নিশ্চিত করুন';

  @override
  String deletePersonConfirmation(String name) {
    return 'আপনি কি নিশ্চিত যে আপনি $name মুছতে চান? এটি সমস্ত সম্পর্কিত বক্তৃতা নমুনা সরিয়ে দেবে।';
  }

  @override
  String get howItWorksTitle => 'এটি কীভাবে কাজ করে?';

  @override
  String get howPeopleWorks =>
      'একবার একজন ব্যক্তি তৈরি হলে, আপনি একটি কথোপকথন ট্রান্সক্রিপ্টে যেতে পারেন এবং তাদের সংশ্লিষ্ট সেগমেন্ট বরাদ্দ করতে পারেন, এইভাবে Omi তাদের বক্তৃতাও চিনতে সক্ষম হবে!';

  @override
  String get tapToDelete => 'মুছতে ট্যাপ করুন';

  @override
  String get newTag => 'নতুন';

  @override
  String get needHelpChatWithUs => 'সাহায্যের প্রয়োজন? আমাদের সাথে চ্যাট করুন';

  @override
  String get localStorageEnabled => 'স্থানীয় স্টোরেজ সক্ষম';

  @override
  String get localStorageDisabled => 'স্থানীয় স্টোরেজ নিষ্ক্রিয়';

  @override
  String failedToUpdateSettings(String error) {
    return 'সেটিংস আপডেট করতে ব্যর্থ: $error';
  }

  @override
  String get privacyNotice => 'গোপনীয়তা নোটিশ';

  @override
  String get recordingsMayCaptureOthers =>
      'রেকর্ডিংগুলি অন্যদের কণ্ঠস্বর ক্যাপচার করতে পারে। সক্ষম করার আগে সমস্ত অংশগ্রহণকারীদের কাছ থেকে সম্মতি নিশ্চিত করুন।';

  @override
  String get enable => 'সক্ষম করুন';

  @override
  String get storeAudioOnPhone => 'ফোনে অডিও সংরক্ষণ করুন';

  @override
  String get on => 'চালু';

  @override
  String get storeAudioDescription =>
      'সমস্ত অডিও রেকর্ডিং আপনার ফোনে স্থানীয়ভাবে সংরক্ষণ করুন। নিষ্ক্রিয় হলে, শুধুমাত্র ব্যর্থ আপলোডগুলি স্টোরেজ স্থান সাশ্রয় করার জন্য রাখা হয়।';

  @override
  String get enableLocalStorage => 'স্থানীয় স্টোরেজ সক্ষম করুন';

  @override
  String get cloudStorageEnabled => 'ক্লাউড স্টোরেজ সক্ষম';

  @override
  String get cloudStorageDisabled => 'ক্লাউড স্টোরেজ নিষ্ক্রিয়';

  @override
  String get enableCloudStorage => 'ক্লাউড স্টোরেজ সক্ষম করুন';

  @override
  String get storeAudioOnCloud => 'ক্লাউডে অডিও সংরক্ষণ করুন';

  @override
  String get cloudStorageDialogMessage =>
      'আপনার রিয়েল-টাইম রেকর্ডিংগুলি আপনি কথা বলার সাথে সাথে ব্যক্তিগত ক্লাউড স্টোরেজে সংরক্ষিত হবে।';

  @override
  String get storeAudioCloudDescription =>
      'আপনার রিয়েল-টাইম রেকর্ডিংগুলি আপনি কথা বলার সাথে সাথে ব্যক্তিগত ক্লাউড স্টোরেজে সংরক্ষণ করুন। অডিও রিয়েল-টাইমে সুরক্ষিতভাবে ক্যাপচার এবং সংরক্ষিত হয়।';

  @override
  String get downloadingFirmware => 'ফার্মওয়্যার ডাউনলোড করা হচ্ছে';

  @override
  String get installingFirmware => 'ফার্মওয়্যার ইনস্টল করা হচ্ছে';

  @override
  String get firmwareUpdateWarning =>
      'অ্যাপ বন্ধ করবেন না বা ডিভাইস বন্ধ করবেন না। এটি আপনার ডিভাইস ক্ষতিগ্রস্ত করতে পারে।';

  @override
  String get firmwareUpdated => 'ফার্মওয়্যার আপডেট হয়েছে';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'আপডেটটি সম্পন্ন করতে দয়া করে আপনার $deviceName পুনরায় চালু করুন।';
  }

  @override
  String get yourDeviceIsUpToDate => 'আপনার ডিভাইস আপ-টু-ডেট';

  @override
  String get currentVersion => 'বর্তমান সংস্করণ';

  @override
  String get latestVersion => 'সর্বশেষ সংস্করণ';

  @override
  String get whatsNew => 'নতুন কী';

  @override
  String get installUpdate => 'আপডেট ইনস্টল করুন';

  @override
  String get updateNow => 'এখনই আপডেট করুন';

  @override
  String get updateGuide => 'আপডেট গাইড';

  @override
  String get checkingForUpdates => 'আপডেটগুলি পরীক্ষা করা হচ্ছে';

  @override
  String get checkingFirmwareVersion => 'ফার্মওয়্যার সংস্করণ পরীক্ষা করা হচ্ছে...';

  @override
  String get firmwareUpdate => 'ফার্মওয়্যার আপডেট';

  @override
  String get payments => 'পেমেন্ট';

  @override
  String get connectPaymentMethodInfo =>
      'আপনার অ্যাপের জন্য অর্থ প্রাপ্ত করা শুরু করতে নীচে একটি পেমেন্ট পদ্ধতি সংযোগ করুন।';

  @override
  String get selectedPaymentMethod => 'নির্বাচিত পেমেন্ট পদ্ধতি';

  @override
  String get availablePaymentMethods => 'উপলব্ধ পেমেন্ট পদ্ধতি';

  @override
  String get activeStatus => 'সক্রিয়';

  @override
  String get connectedStatus => 'সংযুক্ত';

  @override
  String get notConnectedStatus => 'সংযুক্ত নয়';

  @override
  String get setActive => 'সক্রিয় সেট করুন';

  @override
  String get getPaidThroughStripe => 'Stripe এর মাধ্যমে আপনার অ্যাপ বিক্রয়ের জন্য অর্থ পান';

  @override
  String get monthlyPayouts => 'মাসিক পেআউট';

  @override
  String get monthlyPayoutsDescription =>
      'যখন আপনি \$১০ এর উপার্জনে পৌঁছাবেন তখন আপনার অ্যাকাউন্টে সরাসরি মাসিক পেমেন্ট পান';

  @override
  String get secureAndReliable => 'নিরাপদ এবং নির্ভরযোগ্য';

  @override
  String get stripeSecureDescription => 'Stripe আপনার অ্যাপ রাজস্বের নিরাপদ এবং সময়মত স্থানান্তর নিশ্চিত করে';

  @override
  String get selectYourCountry => 'আপনার দেশ নির্বাচন করুন';

  @override
  String get countrySelectionPermanent => 'আপনার দেশ নির্বাচন স্থায়ী এবং পরে পরিবর্তন করা যায় না।';

  @override
  String get byClickingConnectNow => '\"এখনই সংযোগ করুন\" ক্লিক করে আপনি সম্মত হন';

  @override
  String get stripeConnectedAccountAgreement => 'Stripe সংযুক্ত অ্যাকাউন্ট চুক্তি';

  @override
  String get errorConnectingToStripe => 'Stripe এ সংযোগ করতে ত্রুটি! দয়া করে পরে আবার চেষ্টা করুন।';

  @override
  String get connectingYourStripeAccount => 'আপনার Stripe অ্যাকাউন্ট সংযোগ করা হচ্ছে';

  @override
  String get stripeOnboardingInstructions =>
      'দয়া করে আপনার ব্রাউজারে Stripe অনবোর্ডিং প্রক্রিয়া সম্পন্ন করুন। এই পৃষ্ঠাটি সম্পন্ন হলে স্বয়ংক্রিয়ভাবে আপডেট হবে।';

  @override
  String get failedTryAgain => 'ব্যর্থ? আবার চেষ্টা করুন';

  @override
  String get illDoItLater => 'আমি এটি পরে করব';

  @override
  String get successfullyConnected => 'সফলভাবে সংযুক্ত!';

  @override
  String get stripeReadyForPayments =>
      'আপনার Stripe অ্যাকাউন্ট এখন পেমেন্ট পেতে প্রস্তুত। আপনি আপনার অ্যাপ বিক্রয় থেকে অবিলম্বে উপার্জন শুরু করতে পারেন।';

  @override
  String get updateStripeDetails => 'Stripe বিবরণ আপডেট করুন';

  @override
  String get errorUpdatingStripeDetails => 'Stripe বিবরণ আপডেট করতে ত্রুটি! দয়া করে পরে আবার চেষ্টা করুন।';

  @override
  String get updatePayPal => 'PayPal আপডেট করুন';

  @override
  String get setUpPayPal => 'PayPal সেটআপ করুন';

  @override
  String get updatePayPalAccountDetails => 'আপনার PayPal অ্যাকাউন্ট বিবরণ আপডেট করুন';

  @override
  String get connectPayPalToReceivePayments => 'আপনার অ্যাপের জন্য পেমেন্ট পেতে আপনার PayPal অ্যাকাউন্ট সংযোগ করুন';

  @override
  String get paypalEmail => 'PayPal ইমেইল';

  @override
  String get paypalMeLink => 'PayPal.me লিঙ্ক';

  @override
  String get stripeRecommendation =>
      'যদি আপনার দেশে Stripe উপলব্ধ থাকে তবে আমরা দ্রুত এবং সহজ পেআউটের জন্য এটি ব্যবহার করার জন্য দৃঢ়ভাবে সুপারিশ করি।';

  @override
  String get updatePayPalDetails => 'PayPal বিবরণ আপডেট করুন';

  @override
  String get savePayPalDetails => 'PayPal বিবরণ সংরক্ষণ করুন';

  @override
  String get pleaseEnterPayPalEmail => 'দয়া করে আপনার PayPal ইমেইল প্রবেশ করুন';

  @override
  String get pleaseEnterPayPalMeLink => 'দয়া করে আপনার PayPal.me লিঙ্ক প্রবেশ করুন';

  @override
  String get doNotIncludeHttpInLink => 'লিঙ্কে http বা https বা www অন্তর্ভুক্ত করবেন না';

  @override
  String get pleaseEnterValidPayPalMeLink => 'দয়া করে একটি বৈধ PayPal.me লিঙ্ক প্রবেশ করুন';

  @override
  String get pleaseEnterValidEmail => 'দয়া করে একটি বৈধ ইমেইল ঠিকানা প্রবেশ করুন';

  @override
  String get syncingYourRecordings => 'আপনার রেকর্ডিংগুলি সিঙ্ক করা হচ্ছে';

  @override
  String get syncYourRecordings => 'আপনার রেকর্ডিংগুলি সিঙ্ক করুন';

  @override
  String get syncNow => 'এখনই সিঙ্ক করুন';

  @override
  String get error => 'ত্রুটি';

  @override
  String get speechSamples => 'বক্তৃতা নমুনা';

  @override
  String additionalSampleIndex(String index) {
    return 'অতিরিক্ত নমুনা $index';
  }

  @override
  String durationSeconds(String seconds) {
    return 'সময়কাল: $seconds সেকেন্ড';
  }

  @override
  String get additionalSpeechSampleRemoved => 'অতিরিক্ত বক্তৃতা নমুনা সরানো হয়েছে';

  @override
  String get consentDataMessage =>
      'চালিয়ে যাওয়ার মাধ্যমে, আপনার কথোপকথন, রেকর্ডিং এবং ব্যক্তিগত তথ্য আমাদের সার্ভারে নিরাপদে সংরক্ষণ করা হবে। আপনার অডিও রেকর্ডিং এবং ট্রান্সক্রিপ্ট তৃতীয় পক্ষের AI পরিষেবা দ্বারা প্রক্রিয়া করা হয় (ট্রান্সক্রিপশনের জন্য Deepgram এবং বিশ্লেষণের জন্য OpenAI সহ) যাতে আপনাকে AI-চালিত অন্তর্দৃষ্টি প্রদান করা যায় এবং সমস্ত অ্যাপ বৈশিষ্ট্য সক্ষম করা যায়।';

  @override
  String get tasksEmptyStateMessage =>
      'আপনার কথোপকথন থেকে কাজগুলি এখানে উপস্থিত হবে।\\nম্যানুয়ালি একটি তৈরি করতে + ট্যাপ করুন।';

  @override
  String get clearChatAction => 'চ্যাট সাফ করুন';

  @override
  String get enableApps => 'অ্যাপ্লিকেশন সক্ষম করুন';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => 'আরও দেখান ↓';

  @override
  String get showLess => 'কম দেখান ↑';

  @override
  String get loadingYourRecording => 'আপনার রেকর্ডিং লোড করা হচ্ছে...';

  @override
  String get photoDiscardedMessage => 'এই ছবিটি বাতিল করা হয়েছিল কারণ এটি উল্লেখযোগ্য ছিল না।';

  @override
  String get analyzing => 'বিশ্লেষণ করা হচ্ছে...';

  @override
  String get searchCountries => 'দেশগুলি অনুসন্ধান করুন';

  @override
  String get checkingAppleWatch => 'Apple Watch পরীক্ষা করা হচ্ছে...';

  @override
  String get installOmiOnAppleWatch => 'আপনার Apple Watch এ Omi ইনস্টল করুন';

  @override
  String get installOmiOnAppleWatchDescription =>
      'আপনার Apple Watch এর সাথে Omi ব্যবহার করতে, আপনাকে প্রথমে আপনার ঘড়িতে Omi অ্যাপ্লিকেশন ইনস্টল করতে হবে।';

  @override
  String get openOmiOnAppleWatch => 'আপনার Apple Watch এ Omi খুলুন';

  @override
  String get openOmiOnAppleWatchDescription =>
      'Omi অ্যাপ্লিকেশন আপনার Apple Watch এ ইনস্টল করা হয়েছে। এটি খুলুন এবং শুরু করতে শুরু ট্যাপ করুন।';

  @override
  String get openWatchApp => 'Watch অ্যাপ খুলুন';

  @override
  String get iveInstalledAndOpenedTheApp => 'আমি অ্যাপ্লিকেশন ইনস্টল এবং খুলেছি';

  @override
  String get unableToOpenWatchApp =>
      'Apple Watch অ্যাপ খুলতে অক্ষম। দয়া করে আপনার Apple Watch এ Watch অ্যাপটি ম্যানুয়ালি খুলুন এবং \"উপলব্ধ অ্যাপ্লিকেশন\" বিভাগ থেকে Omi ইনস্টল করুন।';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch সফলভাবে সংযুক্ত!';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch এখনও পৌঁছানো যায় না। দয়া করে নিশ্চিত করুন যে Omi অ্যাপ্লিকেশন আপনার ঘড়িতে খোলা আছে।';

  @override
  String errorCheckingConnection(String error) {
    return 'সংযোগ পরীক্ষা করতে ত্রুটি: $error';
  }

  @override
  String get muted => 'নিঃশব্দ';

  @override
  String get processNow => 'এখনই প্রক্রিয়া করুন';

  @override
  String get finishedConversation => 'কথোপকথন শেষ?';

  @override
  String get stopRecordingConfirmation =>
      'আপনি কি নিশ্চিত যে আপনি রেকর্ডিং বন্ধ করতে এবং এখনই কথোপকথন সংক্ষিপ্ত করতে চান?';

  @override
  String get conversationEndsManually => 'কথোপকথন শুধুমাত্র ম্যানুয়ালি শেষ হবে।';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'কথোপকথন $minutes মিনিট$suffix নির্বাক পরে সংক্ষিপ্ত হয়।';
  }

  @override
  String get dontAskAgain => 'আমাকে আবার জিজ্ঞাসা করবেন না';

  @override
  String get waitingForTranscriptOrPhotos => 'ট্রান্সক্রিপ্ট বা ছবির জন্য অপেক্ষা করা হচ্ছে...';

  @override
  String get noSummaryYet => 'এখনও কোনো সারাংশ নেই';

  @override
  String hints(String text) {
    return 'ইঙ্গিত: $text';
  }

  @override
  String get testConversationPrompt => 'একটি কথোপকথন প্রম্পট পরীক্ষা করুন';

  @override
  String get prompt => 'প্রম্পট';

  @override
  String get result => 'ফলাফল:';

  @override
  String get compareTranscripts => 'ট্রান্সক্রিপ্টগুলি তুলনা করুন';

  @override
  String get notHelpful => 'সহায়ক নয়';

  @override
  String get exportTasksWithOneTap => 'এক ট্যাপে কাজগুলি রপ্তানি করুন!';

  @override
  String get inProgress => 'চলছে';

  @override
  String get photos => 'ছবি';

  @override
  String get rawData => 'কাঁচা ডেটা';

  @override
  String get content => 'বিষয়বস্তু';

  @override
  String get noContentToDisplay => 'প্রদর্শন করার জন্য কোনো বিষয়বস্তু নেই';

  @override
  String get noSummary => 'কোনো সারাংশ নেই';

  @override
  String get updateOmiFirmware => 'Omi ফার্মওয়্যার আপডেট করুন';

  @override
  String get anErrorOccurredTryAgain => 'একটি ত্রুটি ঘটেছে। দয়া করে আবার চেষ্টা করুন।';

  @override
  String get welcomeBackSimple => 'স্বাগতম ফিরে আসুন';

  @override
  String get addVocabularyDescription => 'এমন শব্দ যোগ করুন যা Omi ট্রান্সক্রিপশনের সময় স্বীকৃতি দেওয়া উচিত।';

  @override
  String get enterWordsCommaSeparated => 'শব্দ প্রবেশ করুন (কমা দ্বারা বিভক্ত)';

  @override
  String get whenToReceiveDailySummary => 'আপনার দৈনিক সারাংশ কখন পেতে হবে';

  @override
  String get checkingNextSevenDays => 'পরবর্তী ৭ দিন পরীক্ষা করা হচ্ছে';

  @override
  String failedToDeleteError(String error) {
    return 'মুছতে ব্যর্থ: $error';
  }

  @override
  String get developerApiKeys => 'ডেভেলপার API কী';

  @override
  String get noApiKeysCreateOne => 'কোনো API কী নেই। শুরু করতে একটি তৈরি করুন।';

  @override
  String get commandRequired => '⌘ প্রয়োজন';

  @override
  String get spaceKey => 'স্পেস';

  @override
  String loadMoreRemaining(String count) {
    return 'আরও লোড করুন ($count বাকি)';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'শীর্ষ $percentile% ব্যবহারকারী';
  }

  @override
  String get wrappedMinutes => 'মিনিট';

  @override
  String get wrappedConversations => 'কথোপকথন';

  @override
  String get wrappedDaysActive => 'দিন সক্রিয়';

  @override
  String get wrappedYouTalkedAbout => 'আপনি কথা বলেছেন সম্পর্কে';

  @override
  String get wrappedActionItems => 'পদক্ষেপ আইটেম';

  @override
  String get wrappedTasksCreated => 'কাজ তৈরি';

  @override
  String get wrappedCompleted => 'সম্পন্ন';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% সমাপ্তির হার';
  }

  @override
  String get wrappedYourTopDays => 'আপনার শীর্ষ দিন';

  @override
  String get wrappedBestMoments => 'সেরা মুহূর্ত';

  @override
  String get wrappedMyBuddies => 'আমার বন্ধুরা';

  @override
  String get wrappedCouldntStopTalkingAbout => 'কথা বলা বন্ধ করতে পারেনি';

  @override
  String get wrappedShow => 'শো';

  @override
  String get wrappedMovie => 'চলচ্চিত্র';

  @override
  String get wrappedBook => 'বই';

  @override
  String get wrappedCelebrity => 'সেলিব্রিটি';

  @override
  String get wrappedFood => 'খাদ্য';

  @override
  String get wrappedMovieRecs => 'বন্ধুদের জন্য চলচ্চিত্র সুপারিশ';

  @override
  String get wrappedBiggest => 'সবচেয়ে বড়';

  @override
  String get wrappedStruggle => 'সংগ্রাম';

  @override
  String get wrappedButYouPushedThrough => 'কিন্তু আপনি এটির মধ্য দিয়ে চলেছেন 💪';

  @override
  String get wrappedWin => 'জয়';

  @override
  String get wrappedYouDidIt => 'আপনি এটি করেছেন! 🎉';

  @override
  String get wrappedTopPhrases => 'শীর্ষ ৫ বাক্য';

  @override
  String get wrappedMins => 'মিনিট';

  @override
  String get wrappedConvos => 'কথোপকথন';

  @override
  String get wrappedDays => 'দিন';

  @override
  String get wrappedMyBuddiesLabel => 'আমার বন্ধুরা';

  @override
  String get wrappedObsessionsLabel => 'আবেগ';

  @override
  String get wrappedStruggleLabel => 'সংগ্রাম';

  @override
  String get wrappedWinLabel => 'জয়';

  @override
  String get wrappedTopPhrasesLabel => 'শীর্ষ বাক্য';

  @override
  String get wrappedLetsHitRewind => 'আপনার পিছিয়ে চলুন';

  @override
  String get wrappedGenerateMyWrapped => 'আমার Wrapped তৈরি করুন';

  @override
  String get wrappedProcessingDefault => 'প্রক্রিয়াজনীকরণ...';

  @override
  String get wrappedCreatingYourStory => 'আপনার তৈরি করা হচ্ছে\\n২০২৫ গল্প...';

  @override
  String get wrappedSomethingWentWrong => 'কিছু\\nগলত হয়েছে';

  @override
  String get wrappedAnErrorOccurred => 'একটি ত্রুটি ঘটেছে';

  @override
  String get wrappedTryAgain => 'আবার চেষ্টা করুন';

  @override
  String get wrappedNoDataAvailable => 'কোনো ডেটা উপলব্ধ নেই';

  @override
  String get wrappedOmiLifeRecap => 'Omi জীবন পুনর্বিবৃতি';

  @override
  String get wrappedSwipeUpToBegin => 'শুরু করতে উপরে স্বাইপ করুন';

  @override
  String get wrappedShareText => 'আমার ২০২৫, Omi দ্বারা মনে রাখা ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare => 'শেয়ার করতে ব্যর্থ। দয়া করে আবার চেষ্টা করুন।';

  @override
  String get wrappedFailedToStartGeneration => 'প্রজন্ম শুরু করতে ব্যর্থ। দয়া করে আবার চেষ্টা করুন।';

  @override
  String get wrappedStarting => 'শুরু করা হচ্ছে...';

  @override
  String get wrappedShare => 'শেয়ার করুন';

  @override
  String get wrappedShareYourWrapped => 'আপনার Wrapped শেয়ার করুন';

  @override
  String get wrappedMy2025 => 'আমার ২০২৫';

  @override
  String get wrappedRememberedByOmi => 'Omi দ্বারা মনে রাখা';

  @override
  String get wrappedMostFunDay => 'সবচেয়ে মজা';

  @override
  String get wrappedMostProductiveDay => 'সবচেয়ে উৎপাদনশীল';

  @override
  String get wrappedMostIntenseDay => 'সবচেয়ে তীব্র';

  @override
  String get wrappedFunniestMoment => 'সবচেয়ে মজার';

  @override
  String get wrappedMostCringeMoment => 'সবচেয়ে বিশ্রী';

  @override
  String get wrappedMinutesLabel => 'মিনিট';

  @override
  String get wrappedConversationsLabel => 'কথোপকথন';

  @override
  String get wrappedDaysActiveLabel => 'দিন সক্রিয়';

  @override
  String get wrappedTasksGenerated => 'কাজ তৈরি';

  @override
  String get wrappedTasksCompleted => 'কাজ সম্পন্ন';

  @override
  String get wrappedTopFivePhrases => 'শীর্ষ ৫ বাক্য';

  @override
  String get wrappedAGreatDay => 'একটি দুর্দান্ত দিন';

  @override
  String get wrappedGettingItDone => 'এটি করছি';

  @override
  String get wrappedAChallenge => 'একটি চ্যালেঞ্জ';

  @override
  String get wrappedAHilariousMoment => 'একটি হাস্যরস মুহূর্ত';

  @override
  String get wrappedThatAwkwardMoment => 'সেই বিশ্রী মুহূর্ত';

  @override
  String get wrappedYouHadFunnyMoments => 'আপনার এই বছর কিছু মজার মুহূর্ত ছিল!';

  @override
  String get wrappedWeveAllBeenThere => 'আমরা সবাই সেখানে ছিলাম!';

  @override
  String get wrappedFriend => 'বন্ধু';

  @override
  String get wrappedYourBuddy => 'আপনার বন্ধু!';

  @override
  String get wrappedNotMentioned => 'উল্লেখ করা হয়নি';

  @override
  String get wrappedTheHardPart => 'কঠিন অংশ';

  @override
  String get wrappedPersonalGrowth => 'ব্যক্তিগত বৃদ্ধি';

  @override
  String get wrappedFunDay => 'মজা';

  @override
  String get wrappedProductiveDay => 'উৎপাদনশীল';

  @override
  String get wrappedIntenseDay => 'তীব্র';

  @override
  String get wrappedFunnyMomentTitle => 'মজার মুহূর্ত';

  @override
  String get wrappedCringeMomentTitle => 'বিশ্রী মুহূর্ত';

  @override
  String get wrappedYouTalkedAboutBadge => 'আপনি কথা বলেছেন সম্পর্কে';

  @override
  String get wrappedCompletedLabel => 'সম্পন্ন';

  @override
  String get wrappedMyBuddiesCard => 'আমার বন্ধুরা';

  @override
  String get wrappedBuddiesLabel => 'বন্ধুরা';

  @override
  String get wrappedObsessionsLabelUpper => 'আবেগ';

  @override
  String get wrappedStruggleLabelUpper => 'সংগ্রাম';

  @override
  String get wrappedWinLabelUpper => 'জয়';

  @override
  String get wrappedTopPhrasesLabelUpper => 'শীর্ষ বাক্য';

  @override
  String get wrappedYourHeader => 'আপনার';

  @override
  String get wrappedTopDaysHeader => 'শীর্ষ দিন';

  @override
  String get wrappedYourTopDaysBadge => 'আপনার শীর্ষ দিন';

  @override
  String get wrappedBestHeader => 'সেরা';

  @override
  String get wrappedMomentsHeader => 'মুহূর্ত';

  @override
  String get wrappedBestMomentsBadge => 'সেরা মুহূর্ত';

  @override
  String get wrappedBiggestHeader => 'সবচেয়ে বড়';

  @override
  String get wrappedStruggleHeader => 'সংগ্রাম';

  @override
  String get wrappedWinHeader => 'জয়';

  @override
  String get wrappedButYouPushedThroughEmoji => 'কিন্তু আপনি এটির মধ্য দিয়ে চলেছেন 💪';

  @override
  String get wrappedYouDidItEmoji => 'আপনি এটি করেছেন! 🎉';

  @override
  String get wrappedHours => 'ঘন্টা';

  @override
  String get wrappedActions => 'পদক্ষেপ';

  @override
  String get multipleSpeakersDetected => 'একাধিক স্পিকার সনাক্ত করা হয়েছে';

  @override
  String get multipleSpeakersDescription =>
      'মনে হয় রেকর্ডিংয়ে একাধিক স্পিকার রয়েছে। দয়া করে নিশ্চিত করুন যে আপনি একটি শান্ত জায়গায় আছেন এবং আবার চেষ্টা করুন।';

  @override
  String get invalidRecordingDetected => 'অবৈধ রেকর্ডিং সনাক্ত করা হয়েছে';

  @override
  String get notEnoughSpeechDescription =>
      'পর্যাপ্ত বক্তৃতা সনাক্ত করা হয়নি। দয়া করে আরও কথা বলুন এবং আবার চেষ্টা করুন।';

  @override
  String get speechDurationDescription => 'নিশ্চিত করুন যে আপনি অন্তত ৫ সেকেন্ড এবং ৯০ সেকেন্ডের বেশি কথা বলছেন না।';

  @override
  String get connectionLostDescription =>
      'সংযোগ বাধাগ্রস্ত হয়েছে। আপনার ইন্টারনেট সংযোগ পরীক্ষা করুন এবং আবার চেষ্টা করুন।';

  @override
  String get howToTakeGoodSample => 'একটি ভাল স্যাম্পল কীভাবে নিতে হয়?';

  @override
  String get goodSampleInstructions =>
      '১. নিশ্চিত করুন যে আপনি একটি শান্ত জায়গায় আছেন।\n২. স্পষ্টভাবে এবং স্বাভাবিকভাবে কথা বলুন।\n३. আপনার ডিভাইস আপনার গলায় প্রাকৃতিক অবস্থানে আছে তা নিশ্চিত করুন।\n\nএটি তৈরি করার পর, আপনি যেকোনো সময় এটি উন্নত করতে বা আবার করতে পারেন।';

  @override
  String get noDeviceConnectedUseMic => 'কোন ডিভাইস সংযুক্ত নেই। ফোন মাইক্রোফোন ব্যবহার করা হবে।';

  @override
  String get doItAgain => 'আবার করুন';

  @override
  String get listenToSpeechProfile => 'আমার স্পিচ প্রোফাইল শুনুন ➡️';

  @override
  String get recognizingOthers => 'অন্যদের চিনছি 👀';

  @override
  String get keepGoingGreat => 'চলতে থাকুন, আপনি দুর্দান্ত করছেন';

  @override
  String get somethingWentWrongTryAgain => 'কিছু ভুল হয়েছে! পরে আবার চেষ্টা করুন।';

  @override
  String get uploadingVoiceProfile => 'আপনার ভয়েস প্রোফাইল আপলোড করা হচ্ছে....';

  @override
  String get memorizingYourVoice => 'আপনার কণ্ঠস্বর মনে রাখা হচ্ছে...';

  @override
  String get personalizingExperience => 'আপনার অভিজ্ঞতা ব্যক্তিগতকৃত করা হচ্ছে...';

  @override
  String get keepSpeakingUntil100 => '১০০% পর্যন্ত কথা বলতে থাকুন।';

  @override
  String get greatJobAlmostThere => 'দুর্দান্ত কাজ, আপনি প্রায় সেখানে পৌঁছেছেন';

  @override
  String get soCloseJustLittleMore => 'এত কাছাকাছি, একটু আরও';

  @override
  String get notificationFrequency => 'বিজ্ঞপ্তি ফ্রিকোয়েন্সি';

  @override
  String get controlNotificationFrequency => 'Omi কতবার সক্রিয় বিজ্ঞপ্তি পাঠায় তা নিয়ন্ত্রণ করুন।';

  @override
  String get yourScore => 'আপনার স্কোর';

  @override
  String get dailyScoreBreakdown => 'দৈনিক স্কোর বিভাজন';

  @override
  String get todaysScore => 'আজকের স্কোর';

  @override
  String get tasksCompleted => 'সম্পন্ন কাজ';

  @override
  String get completionRate => 'সম্পূর্ণতার হার';

  @override
  String get howItWorks => 'এটি কীভাবে কাজ করে';

  @override
  String get dailyScoreExplanation =>
      'আপনার দৈনিক স্কোর কাজ সম্পূর্ণতার উপর ভিত্তি করে। আপনার স্কোর উন্নত করতে আপনার কাজগুলি সম্পূর্ণ করুন!';

  @override
  String get notificationFrequencyDescription => 'Omi কতবার সক্রিয় বিজ্ঞপ্তি এবং অনুস্মারক পাঠায় তা নিয়ন্ত্রণ করুন।';

  @override
  String get sliderOff => 'বন্ধ';

  @override
  String get sliderMax => 'সর্বোচ্চ';

  @override
  String summaryGeneratedFor(String date) {
    return '$date এর জন্য সারসংক্ষেপ তৈরি করা হয়েছে';
  }

  @override
  String get failedToGenerateSummary => 'সারসংক্ষেপ তৈরি করতে ব্যর্থ। সেই দিনের জন্য কথোপকথন আছে কিনা তা নিশ্চিত করুন।';

  @override
  String get recap => 'পুনরালোচনা';

  @override
  String deleteQuoted(String name) {
    return '\"$name\" মুছুন';
  }

  @override
  String moveConversationsTo(int count) {
    return '$count কথোপকথন এতে নিয়ে যান:';
  }

  @override
  String get noFolder => 'কোন ফোল্ডার নেই';

  @override
  String get removeFromAllFolders => 'সমস্ত ফোল্ডার থেকে সরান';

  @override
  String get buildAndShareYourCustomApp => 'আপনার কাস্টম অ্যাপ তৈরি এবং শেয়ার করুন';

  @override
  String get searchAppsPlaceholder => '১৫০০+ অ্যাপ খুঁজুন';

  @override
  String get filters => 'ফিল্টার';

  @override
  String get frequencyOff => 'বন্ধ';

  @override
  String get frequencyMinimal => 'ন্যূনতম';

  @override
  String get frequencyLow => 'কম';

  @override
  String get frequencyBalanced => 'ভারসাম্যপূর্ণ';

  @override
  String get frequencyHigh => 'উচ্চ';

  @override
  String get frequencyMaximum => 'সর্বোচ্চ';

  @override
  String get frequencyDescOff => 'কোন সক্রিয় বিজ্ঞপ্তি নেই';

  @override
  String get frequencyDescMinimal => 'শুধুমাত্র গুরুত্বপূর্ণ অনুস্মারক';

  @override
  String get frequencyDescLow => 'শুধুমাত্র গুরুত্বপূর্ণ আপডেট';

  @override
  String get frequencyDescBalanced => 'নিয়মিত সহায়ক পুশ';

  @override
  String get frequencyDescHigh => 'ঘন ঘন চেক-ইন';

  @override
  String get frequencyDescMaximum => 'ক্রমাগত নিযুক্ত থাকুন';

  @override
  String get clearChatQuestion => 'চ্যাট সাফ করুন?';

  @override
  String get syncingMessages => 'সার্ভারের সাথে বার্তা সিঙ্ক করা হচ্ছে...';

  @override
  String get chatAppsTitle => 'চ্যাট অ্যাপ';

  @override
  String get selectApp => 'অ্যাপ নির্বাচন করুন';

  @override
  String get noChatAppsEnabled => 'কোন চ্যাট অ্যাপ সক্ষম নেই।\n\"অ্যাপ সক্ষম করুন\" ট্যাপ করুন কিছু যোগ করতে।';

  @override
  String get disable => 'অক্ষম করুন';

  @override
  String get photoLibrary => 'ফটো লাইব্রেরি';

  @override
  String get chooseFile => 'ফাইল নির্বাচন করুন';

  @override
  String get connectAiAssistantsToYourData => 'AI সহায়কদের আপনার ডেটার সাথে সংযুক্ত করুন';

  @override
  String get oAuth => 'OAuth';

  @override
  String get trackYourGoalsOnHomepage => 'হোমপেজে আপনার ব্যক্তিগত লক্ষ্য ট্র্যাক করুন';

  @override
  String get deleteRecording => 'রেকর্ডিং মুছুন';

  @override
  String get thisCannotBeUndone => 'এটি পূর্বাবস্থায় ফিরিয়ে আনা যায় না।';

  @override
  String get sdCard => 'SD কার্ড';

  @override
  String get fromSd => 'SD থেকে';

  @override
  String get limitless => 'সীমাহীন';

  @override
  String get fastTransfer => 'দ্রুত স্থানান্তর';

  @override
  String get syncingStatus => 'সিঙ্ক করা হচ্ছে';

  @override
  String get failedStatus => 'ব্যর্থ';

  @override
  String etaLabel(String time) {
    return 'ETA: $time';
  }

  @override
  String get transferMethod => 'স্থানান্তর পদ্ধতি';

  @override
  String get fast => 'দ্রুত';

  @override
  String get ble => 'BLE';

  @override
  String get phone => 'ফোন';

  @override
  String get cancelSync => 'সিঙ্ক বাতিল করুন';

  @override
  String get cancelSyncMessage => 'ইতিমধ্যে ডাউনলোড করা ডেটা সংরক্ষণ করা হবে। আপনি পরে পুনরায় শুরু করতে পারেন।';

  @override
  String get syncCancelled => 'সিঙ্ক বাতিল করা হয়েছে';

  @override
  String get deleteProcessedFiles => 'প্রক্রিয়াজাত ফাইল মুছুন';

  @override
  String get processedFilesDeleted => 'প্রক্রিয়াজাত ফাইল মুছে দেওয়া হয়েছে';

  @override
  String get wifiEnableFailed => 'ডিভাইসে Wi-Fi সক্ষম করতে ব্যর্থ। দয়া করে আবার চেষ্টা করুন।';

  @override
  String get deviceNoFastTransfer => 'আপনার ডিভাইস দ্রুত স্থানান্তর সমর্থন করে না। পরিবর্তে Bluetooth ব্যবহার করুন।';

  @override
  String get enableHotspotMessage => 'আপনার ফোনের হটস্পট সক্ষম করুন এবং আবার চেষ্টা করুন।';

  @override
  String get transferStartFailed => 'স্থানান্তর শুরু করতে ব্যর্থ। দয়া করে আবার চেষ্টা করুন।';

  @override
  String get deviceNotResponding => 'ডিভাইস সাড়া দেয় না। দয়া করে আবার চেষ্টা করুন।';

  @override
  String get invalidWifiCredentials => 'অবৈধ Wi-Fi শংসাপত্র। আপনার হটস্পট সেটিংস পরীক্ষা করুন।';

  @override
  String get wifiConnectionFailed => 'Wi-Fi সংযোগ ব্যর্থ। দয়া করে আবার চেষ্টা করুন।';

  @override
  String get sdCardProcessing => 'SD কার্ড প্রক্রিয়াকরণ';

  @override
  String sdCardProcessingMessage(int count) {
    return '$count রেকর্ডিং প্রক্রিয়া করা হচ্ছে। ফাইলগুলি তারপর SD কার্ড থেকে সরানো হবে।';
  }

  @override
  String get process => 'প্রক্রিয়া';

  @override
  String get wifiSyncFailed => 'Wi-Fi সিঙ্ক ব্যর্থ';

  @override
  String get processingFailed => 'প্রক্রিয়াকরণ ব্যর্থ';

  @override
  String get downloadingFromSdCard => 'SD কার্ড থেকে ডাউনলোড করা হচ্ছে';

  @override
  String processingProgress(int current, int total) {
    return 'প্রক্রিয়া করা হচ্ছে $current/$total';
  }

  @override
  String conversationsCreated(int count) {
    return '$count কথোপকথন তৈরি করা হয়েছে';
  }

  @override
  String get internetRequired => 'ইন্টারনেট প্রয়োজন';

  @override
  String get processAudio => 'অডিও প্রক্রিয়া করুন';

  @override
  String get start => 'শুরু করুন';

  @override
  String get noRecordings => 'কোন রেকর্ডিং নেই';

  @override
  String get audioFromOmiWillAppearHere => 'আপনার Omi ডিভাইসের অডিও এখানে প্রদর্শিত হবে';

  @override
  String get deleteProcessed => 'প্রক্রিয়াজাত মুছুন';

  @override
  String get tryDifferentFilter => 'একটি ভিন্ন ফিল্টার চেষ্টা করুন';

  @override
  String get recordings => 'রেকর্ডিং';

  @override
  String get enableRemindersAccess => 'Apple Reminders ব্যবহার করতে সেটিংসে Reminders অ্যাক্সেস সক্ষম করুন';

  @override
  String todayAtTime(String time) {
    return 'আজ $time-এ';
  }

  @override
  String yesterdayAtTime(String time) {
    return 'গতকাল $time-এ';
  }

  @override
  String get lessThanAMinute => 'এক মিনিটের কম';

  @override
  String estimatedMinutes(int count) {
    return '~$count মিনিট';
  }

  @override
  String estimatedHours(int count) {
    return '~$count ঘন্টা';
  }

  @override
  String estimatedTimeRemaining(String time) {
    return 'অনুমানিত: $time অবশিষ্ট';
  }

  @override
  String get summarizingConversation => 'কথোপকথন সংক্ষেপ করা হচ্ছে...\nএটি কয়েক সেকেন্ড সময় নিতে পারে';

  @override
  String get resummarizingConversation => 'কথোপকথন পুনরায় সংক্ষেপ করা হচ্ছে...\nএটি কয়েক সেকেন্ড সময় নিতে পারে';

  @override
  String get nothingInterestingRetry => 'কিছুই আকর্ষণীয় পাওয়া যায়নি,\nআবার চেষ্টা করতে চান?';

  @override
  String get noSummaryForConversation => 'এই কথোপকথনের জন্য\nকোন সারসংক্ষেপ উপলব্ধ নেই।';

  @override
  String get unknownLocation => 'অজানা অবস্থান';

  @override
  String get couldNotLoadMap => 'মানচিত্র লোড করা যায় না';

  @override
  String get triggerConversationIntegration => 'ট্রিগার কথোপকথন তৈরি ইন্টিগ্রেশন';

  @override
  String get webhookUrlNotSet => 'Webhook URL সেট করা হয়নি';

  @override
  String get setWebhookUrlInSettings => 'এই বৈশিষ্ট্য ব্যবহার করতে ডেভেলপার সেটিংসে Webhook URL সেট করুন।';

  @override
  String get sendWebUrl => 'ওয়েব ইউআরএল পাঠান';

  @override
  String get sendTranscript => 'ট্রান্সক্রিপ্ট পাঠান';

  @override
  String get sendSummary => 'সারসংক্ষেপ পাঠান';

  @override
  String get debugModeDetected => 'ডিবাগ মোড সনাক্ত করা হয়েছে';

  @override
  String get performanceReduced => 'কর্মক্ষমতা ৫-১০ গুণ হ্রাস। রিলিজ মোড ব্যবহার করুন।';

  @override
  String autoClosingInSeconds(int seconds) {
    return 'স্বয়ংক্রিয় বন্ধ $secondsসে-তে';
  }

  @override
  String get modelRequired => 'মডেল প্রয়োজন';

  @override
  String get downloadWhisperModel => 'সংরক্ষণ করার আগে একটি Whisper মডেল ডাউনলোড করুন।';

  @override
  String get deviceNotCompatible => 'ডিভাইস সামঞ্জস্যপূর্ণ নয়';

  @override
  String get deviceRequirements => 'আপনার ডিভাইস অন-ডিভাইস ট্রান্সক্রিপশনের জন্য প্রয়োজনীয়তা পূরণ করে না।';

  @override
  String get willLikelyCrash => 'এটি সক্ষম করলে অ্যাপটি সম্ভবত ক্র্যাশ হবে বা ফ্রিজ করবে।';

  @override
  String get transcriptionSlowerLessAccurate => 'ট্রান্সক্রিপশন উল্লেখযোগ্যভাবে ধীর এবং কম নির্ভুল হবে।';

  @override
  String get proceedAnyway => 'তবুও এগিয়ে যান';

  @override
  String get olderDeviceDetected => 'পুরানো ডিভাইস সনাক্ত করা হয়েছে';

  @override
  String get onDeviceSlower => 'এই ডিভাইসে অন-ডিভাইস ট্রান্সক্রিপশন ধীর হতে পারে।';

  @override
  String get batteryUsageHigher => 'ব্যাটারি ব্যবহার ক্লাউড ট্রান্সক্রিপশনের চেয়ে বেশি হবে।';

  @override
  String get considerOmiCloud => 'ভাল কর্মক্ষমতার জন্য Omi ক্লাউড ব্যবহার বিবেচনা করুন।';

  @override
  String get highResourceUsage => 'উচ্চ সম্পদ ব্যবহার';

  @override
  String get onDeviceIntensive => 'অন-ডিভাইস ট্রান্সক্রিপশন গণনা করার জন্য তীব্র।';

  @override
  String get batteryDrainIncrease => 'ব্যাটারি ড্রেইন উল্লেখযোগ্যভাবে বৃদ্ধি পাবে।';

  @override
  String get deviceMayWarmUp => 'বর্ধিত ব্যবহারের সময় ডিভাইস উষ্ণ হতে পারে।';

  @override
  String get speedAccuracyLower => 'গতি এবং নির্ভুলতা ক্লাউড মডেলের চেয়ে কম হতে পারে।';

  @override
  String get cloudProvider => 'ক্লাউড প্রদানকারী';

  @override
  String get premiumMinutesInfo =>
      'প্রতি মাসে ১,২০০ প্রিমিয়াম মিনিট। অন-ডিভাইস ট্যাব আনলিমিটেড ফ্রি ট্রান্সক্রিপশন অফার করে।';

  @override
  String get viewUsage => 'ব্যবহার দেখুন';

  @override
  String get localProcessingInfo =>
      'অডিও স্থানীয়ভাবে প্রক্রিয়া করা হয়। অফলাইনে কাজ করে, আরও ব্যক্তিগত, কিন্তু আরও ব্যাটারি ব্যবহার করে।';

  @override
  String get model => 'মডেল';

  @override
  String get performanceWarning => 'কর্মক্ষমতা সতর্কতা';

  @override
  String get largeModelWarning =>
      'এই মডেল বড় এবং মোবাইল ডিভাইসে অ্যাপটি ক্র্যাশ করতে বা খুবই ধীরে চলতে পারে।\n\n\"ছোট\" বা \"বেস\" সুপারিশ করা হয়।';

  @override
  String get usingNativeIosSpeech => 'নেটিভ iOS স্পিচ রিকগনিশন ব্যবহার করা হচ্ছে';

  @override
  String get noModelDownloadRequired =>
      'আপনার ডিভাইসের নেটিভ স্পিচ ইঞ্জিন ব্যবহার করা হবে। কোন মডেল ডাউনলোড প্রয়োজন নেই।';

  @override
  String get modelReady => 'মডেল প্রস্তুত';

  @override
  String get redownload => 'পুনরায় ডাউনলোড করুন';

  @override
  String get doNotCloseApp => 'দয়া করে অ্যাপ বন্ধ করবেন না।';

  @override
  String get downloading => 'ডাউনলোড করা হচ্ছে...';

  @override
  String get downloadModel => 'মডেল ডাউনলোড করুন';

  @override
  String estimatedSize(String size) {
    return 'অনুমানিত আকার: ~$size MB';
  }

  @override
  String availableSpace(String space) {
    return 'উপলব্ধ স্থান: $space';
  }

  @override
  String get notEnoughSpace => 'সতর্কতা: যথেষ্ট স্থান নেই!';

  @override
  String get download => 'ডাউনলোড';

  @override
  String downloadError(String error) {
    return 'ডাউনলোড ত্রুটি: $error';
  }

  @override
  String get cancelled => 'বাতিল করা হয়েছে';

  @override
  String get deviceNotCompatibleTitle => 'ডিভাইস সামঞ্জস্যপূর্ণ নয়';

  @override
  String get deviceNotMeetRequirements => 'আপনার ডিভাইস অন-ডিভাইস ট্রান্সক্রিপশনের জন্য প্রয়োজনীয়তা পূরণ করে না।';

  @override
  String get transcriptionSlowerOnDevice => 'এই ডিভাইসে অন-ডিভাইস ট্রান্সক্রিপশন ধীর হতে পারে।';

  @override
  String get computationallyIntensive => 'অন-ডিভাইস ট্রান্সক্রিপশন গণনা করার জন্য তীব্র।';

  @override
  String get batteryDrainSignificantly => 'ব্যাটারি ড্রেইন উল্লেখযোগ্যভাবে বৃদ্ধি পাবে।';

  @override
  String get premiumMinutesMonth =>
      'প্রতি মাসে ১,২০০ প্রিমিয়াম মিনিট। অন-ডিভাইস ট্যাব আনলিমিটেড ফ্রি ট্রান্সক্রিপশন অফার করে।';

  @override
  String get audioProcessedLocally =>
      'অডিও স্থানীয়ভাবে প্রক্রিয়া করা হয়। অফলাইনে কাজ করে, আরও ব্যক্তিগত, কিন্তু আরও ব্যাটারি ব্যবহার করে।';

  @override
  String get languageLabel => 'ভাষা';

  @override
  String get modelLabel => 'মডেল';

  @override
  String get modelTooLargeWarning =>
      'এই মডেল বড় এবং মোবাইল ডিভাইসে অ্যাপটি ক্র্যাশ করতে বা খুবই ধীরে চলতে পারে।\n\n\"ছোট\" বা \"বেস\" সুপারিশ করা হয়।';

  @override
  String get nativeEngineNoDownload =>
      'আপনার ডিভাইসের নেটিভ স্পিচ ইঞ্জিন ব্যবহার করা হবে। কোন মডেল ডাউনলোড প্রয়োজন নেই।';

  @override
  String modelReadyWithName(String model) {
    return 'মডেল প্রস্তুত ($model)';
  }

  @override
  String get reDownload => 'পুনরায় ডাউনলোড করুন';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return '$model ডাউনলোড করা হচ্ছে: $received / $total MB';
  }

  @override
  String preparingModel(String model) {
    return '$model প্রস্তুত করা হচ্ছে...';
  }

  @override
  String downloadErrorWithMessage(String error) {
    return 'ডাউনলোড ত্রুটি: $error';
  }

  @override
  String estimatedSizeWithValue(String size) {
    return 'অনুমানিত আকার: ~$size MB';
  }

  @override
  String availableSpaceWithValue(String space) {
    return 'উপলব্ধ স্থান: $space';
  }

  @override
  String get omiTranscriptionOptimized =>
      'Omi-এর বিল্ট-ইন লাইভ ট্রান্সক্রিপশন স্বয়ংক্রিয় স্পিকার সনাক্তকরণ এবং ডায়ারাইজেশন সহ রিয়েল-টাইম কথোপকথনের জন্য অপ্টিমাইজ করা হয়েছে।';

  @override
  String get reset => 'রিসেট';

  @override
  String get useTemplateFrom => 'এ থেকে টেমপ্লেট ব্যবহার করুন';

  @override
  String get selectProviderTemplate => 'একটি প্রদানকারী টেমপ্লেট নির্বাচন করুন...';

  @override
  String get quicklyPopulateResponse => 'পরিচিত প্রদানকারীর প্রতিক্রিয়া ফরম্যাটের সাথে দ্রুত পূরণ করুন';

  @override
  String get quicklyPopulateRequest => 'পরিচিত প্রদানকারীর অনুরোধ ফরম্যাটের সাথে দ্রুত পূরণ করুন';

  @override
  String get invalidJsonError => 'অবৈধ JSON';

  @override
  String downloadModelWithName(String model) {
    return 'মডেল ডাউনলোড করুন ($model)';
  }

  @override
  String modelNameWithFile(String model) {
    return 'মডেল: $model';
  }

  @override
  String get device => 'ডিভাইস';

  @override
  String get chatAssistantsTitle => 'চ্যাট সহায়ক';

  @override
  String get permissionReadConversations => 'কথোপকথন পড়ুন';

  @override
  String get permissionReadMemories => 'স্মৃতি পড়ুন';

  @override
  String get permissionReadTasks => 'কাজ পড়ুন';

  @override
  String get permissionCreateConversations => 'কথোপকথন তৈরি করুন';

  @override
  String get permissionCreateMemories => 'স্মৃতি তৈরি করুন';

  @override
  String get permissionTypeAccess => 'অ্যাক্সেস';

  @override
  String get permissionTypeCreate => 'তৈরি';

  @override
  String get permissionTypeTrigger => 'ট্রিগার';

  @override
  String get permissionDescReadConversations => 'এই অ্যাপ আপনার কথোপকথন অ্যাক্সেস করতে পারে।';

  @override
  String get permissionDescReadMemories => 'এই অ্যাপ আপনার স্মৃতি অ্যাক্সেস করতে পারে।';

  @override
  String get permissionDescReadTasks => 'এই অ্যাপ আপনার কাজ অ্যাক্সেস করতে পারে।';

  @override
  String get permissionDescCreateConversations => 'এই অ্যাপ নতুন কথোপকথন তৈরি করতে পারে।';

  @override
  String get permissionDescCreateMemories => 'এই অ্যাপ নতুন স্মৃতি তৈরি করতে পারে।';

  @override
  String get realtimeListening => 'রিয়েল-টাইম শোনা';

  @override
  String get setupCompleted => 'সম্পন্ন';

  @override
  String get pleaseSelectRating => 'একটি রেটিং নির্বাচন করুন';

  @override
  String get writeReviewOptional => 'একটি পর্যালোচনা লিখুন (ঐচ্ছিক)';

  @override
  String get setupQuestionsIntro => 'কয়েকটি প্রশ্নের উত্তর দিয়ে Omi উন্নত করতে সাহায্য করুন। 🫶 💜';

  @override
  String get setupQuestionProfession => '१. আপনি কী করেন?';

  @override
  String get setupQuestionUsage => '२. আপনি আপনার Omi কোথায় ব্যবহার করার পরিকল্পনা করছেন?';

  @override
  String get setupQuestionAge => '३. আপনার বয়স পরিসীমা কী?';

  @override
  String get setupAnswerAllQuestions => 'আপনি এখনো সব প্রশ্নের উত্তর দেননি! 🥺';

  @override
  String get setupSkipHelp => 'এড়িয়ে যান, আমি সাহায্য করতে চাই না :C';

  @override
  String get professionEntrepreneur => 'উদ্যোক্তা';

  @override
  String get professionSoftwareEngineer => 'সফটওয়্যার ইঞ্জিনিয়ার';

  @override
  String get professionProductManager => 'পণ্য ম্যানেজার';

  @override
  String get professionExecutive => 'নির্বাহী';

  @override
  String get professionSales => 'বিক্রয়';

  @override
  String get professionStudent => 'শিক্ষার্থী';

  @override
  String get usageAtWork => 'কাজে';

  @override
  String get usageIrlEvents => 'আইআরএল ইভেন্ট';

  @override
  String get usageOnline => 'অনলাইনে';

  @override
  String get usageSocialSettings => 'সামাজিক পরিবেশে';

  @override
  String get usageEverywhere => 'সর্বত্র';

  @override
  String get customBackendUrlTitle => 'কাস্টম ব্যাকএন্ড URL';

  @override
  String get backendUrlLabel => 'ব্যাকএন্ড URL';

  @override
  String get saveUrlButton => 'URL সংরক্ষণ করুন';

  @override
  String get enterBackendUrlError => 'দয়া করে ব্যাকএন্ড URL প্রবেশ করুন';

  @override
  String get urlMustEndWithSlashError => 'URL \"/\" দিয়ে শেষ হতে হবে';

  @override
  String get invalidUrlError => 'দয়া করে একটি বৈধ URL প্রবেশ করুন';

  @override
  String get backendUrlSavedSuccess => 'ব্যাকএন্ড URL সফলভাবে সংরক্ষিত!';

  @override
  String get signInTitle => 'সাইন ইন করুন';

  @override
  String get signInButton => 'সাইন ইন করুন';

  @override
  String get enterEmailError => 'দয়া করে আপনার ইমেল প্রবেশ করুন';

  @override
  String get invalidEmailError => 'দয়া করে একটি বৈধ ইমেল প্রবেশ করুন';

  @override
  String get enterPasswordError => 'দয়া করে আপনার পাসওয়ার্ড প্রবেশ করুন';

  @override
  String get passwordMinLengthError => 'পাসওয়ার্ড কমপক্ষে ৮ অক্ষর লম্বা হতে হবে';

  @override
  String get signInSuccess => 'সাইন ইন সফল!';

  @override
  String get alreadyHaveAccountLogin => 'ইতিমধ্যে একটি অ্যাকাউন্ট আছে? লগ ইন করুন';

  @override
  String get emailLabel => 'ইমেল';

  @override
  String get passwordLabel => 'পাসওয়ার্ড';

  @override
  String get createAccountTitle => 'অ্যাকাউন্ট তৈরি করুন';

  @override
  String get nameLabel => 'নাম';

  @override
  String get repeatPasswordLabel => 'পাসওয়ার্ড পুনরাবৃত্তি করুন';

  @override
  String get signUpButton => 'সাইন আপ করুন';

  @override
  String get enterNameError => 'দয়া করে আপনার নাম প্রবেশ করুন';

  @override
  String get passwordsDoNotMatch => 'পাসওয়ার্ড মিলে না';

  @override
  String get signUpSuccess => 'সাইন আপ সফল!';

  @override
  String get loadingKnowledgeGraph => 'জ্ঞান গ্রাফ লোড করা হচ্ছে...';

  @override
  String get noKnowledgeGraphYet => 'এখনো কোন জ্ঞান গ্রাফ নেই';

  @override
  String get buildingKnowledgeGraphFromMemories => 'স্মৃতি থেকে আপনার জ্ঞান গ্রাফ তৈরি করা হচ্ছে...';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'আপনার জ্ঞান গ্রাফ স্বয়ংক্রিয়ভাবে তৈরি হবে যখন আপনি নতুন স্মৃতি তৈরি করবেন।';

  @override
  String get buildGraphButton => 'গ্রাফ তৈরি করুন';

  @override
  String get checkOutMyMemoryGraph => 'আমার স্মৃতি গ্রাফ দেখুন!';

  @override
  String get getButton => 'পান';

  @override
  String openingApp(String appName) {
    return '$appName খোলা হচ্ছে...';
  }

  @override
  String get writeSomething => 'কিছু লিখুন';

  @override
  String get submitReply => 'উত্তর জমা দিন';

  @override
  String get editYourReply => 'আপনার উত্তর সম্পাদনা করুন';

  @override
  String get replyToReview => 'পর্যালোচনার উত্তর দিন';

  @override
  String get rateAndReviewThisApp => 'এই অ্যাপ রেট এবং পর্যালোচনা করুন';

  @override
  String get noChangesInReview => 'পর্যালোচনায় কোন পরিবর্তন নেই আপডেট করার জন্য।';

  @override
  String get cantRateWithoutInternet => 'ইন্টারনেট সংযোগ ছাড়া অ্যাপ রেট করা যায় না।';

  @override
  String get appAnalytics => 'অ্যাপ বিশ্লেষণ';

  @override
  String get learnMoreLink => 'আরও জানুন';

  @override
  String get moneyEarned => 'অর্থ অর্জিত';

  @override
  String get writeYourReply => 'আপনার উত্তর লিখুন...';

  @override
  String get replySentSuccessfully => 'উত্তর সফলভাবে পাঠানো হয়েছে';

  @override
  String failedToSendReply(String error) {
    return 'উত্তর পাঠাতে ব্যর্থ: $error';
  }

  @override
  String get send => 'পাঠান';

  @override
  String starFilter(int count) {
    return '$count তারকা';
  }

  @override
  String get noReviewsFound => 'কোন পর্যালোচনা পাওয়া যায়নি';

  @override
  String get editReply => 'উত্তর সম্পাদনা করুন';

  @override
  String get reply => 'উত্তর';

  @override
  String starFilterLabel(int count) {
    return '$count তারকা';
  }

  @override
  String get sharePublicLink => 'জনসাধারণ লিংক শেয়ার করুন';

  @override
  String get connectedKnowledgeData => 'সংযুক্ত জ্ঞান ডেটা';

  @override
  String get enterName => 'নাম প্রবেশ করুন';

  @override
  String get goal => 'লক্ষ্য';

  @override
  String get tapToTrackThisGoal => 'এই লক্ষ্য ট্র্যাক করতে ট্যাপ করুন';

  @override
  String get tapToSetAGoal => 'একটি লক্ষ্য সেট করতে ট্যাপ করুন';

  @override
  String get processedConversations => 'প্রক্রিয়াজাত কথোপকথন';

  @override
  String get updatedConversations => 'আপডেট করা কথোপকথন';

  @override
  String get newConversations => 'নতুন কথোপকথন';

  @override
  String get summaryTemplate => 'সারসংক্ষেপ টেমপ্লেট';

  @override
  String get suggestedTemplates => 'প্রস্তাবিত টেমপ্লেট';

  @override
  String get otherTemplates => 'অন্যান্য টেমপ্লেট';

  @override
  String get availableTemplates => 'উপলব্ধ টেমপ্লেট';

  @override
  String get getCreative => 'সৃজনশীল হন';

  @override
  String get defaultLabel => 'ডিফল্ট';

  @override
  String get lastUsedLabel => 'সর্বশেষ ব্যবহৃত';

  @override
  String get setDefaultApp => 'ডিফল্ট অ্যাপ সেট করুন';

  @override
  String setDefaultAppContent(String appName) {
    return '$appName কে আপনার ডিফল্ট সারসংক্ষেপ অ্যাপ হিসাবে সেট করুন?\\n\\nএই অ্যাপ সমস্ত ভবিষ্যত কথোপকথন সারসংক্ষেপের জন্য স্বয়ংক্রিয়ভাবে ব্যবহার করা হবে।';
  }

  @override
  String get setDefaultButton => 'ডিফল্ট সেট করুন';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName ডিফল্ট সারসংক্ষেপ অ্যাপ হিসাবে সেট করা হয়েছে';
  }

  @override
  String get createCustomTemplate => 'কাস্টম টেমপ্লেট তৈরি করুন';

  @override
  String get allTemplates => 'সমস্ত টেমপ্লেট';

  @override
  String failedToInstallApp(String appName) {
    return '$appName ইনস্টল করতে ব্যর্থ। দয়া করে আবার চেষ্টা করুন।';
  }

  @override
  String errorInstallingApp(String appName, String error) {
    return '$appName ইনস্টল করতে ত্রুটি: $error';
  }

  @override
  String tagSpeaker(int speakerId) {
    return 'স্পিকার $speakerId ট্যাগ করুন';
  }

  @override
  String get personNameAlreadyExists => 'এই নামের একজন ব্যক্তি ইতিমধ্যে বিদ্যমান।';

  @override
  String get selectYouFromList => 'নিজেকে ট্যাগ করতে, দয়া করে তালিকা থেকে \"আপনি\" নির্বাচন করুন।';

  @override
  String get enterPersonsName => 'ব্যক্তির নাম প্রবেশ করুন';

  @override
  String get addPerson => 'ব্যক্তি যোগ করুন';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'এই স্পিকারের অন্যান্য অংশ ট্যাগ করুন ($selected/$total)';
  }

  @override
  String get tagOtherSegments => 'অন্যান্য অংশ ট্যাগ করুন';

  @override
  String get managePeople => 'মানুষ পরিচালনা করুন';

  @override
  String get shareViaSms => 'SMS এর মাধ্যমে শেয়ার করুন';

  @override
  String get selectContactsToShareSummary => 'আপনার কথোপকথন সারসংক্ষেপ শেয়ার করতে যোগাযোগ নির্বাচন করুন';

  @override
  String get searchContactsHint => 'যোগাযোগ খুঁজুন...';

  @override
  String contactsSelectedCount(int count) {
    return '$count নির্বাচিত';
  }

  @override
  String get clearAllSelection => 'সব সাফ করুন';

  @override
  String get selectContactsToShare => 'শেয়ার করতে যোগাযোগ নির্বাচন করুন';

  @override
  String shareWithContactCount(int count) {
    return '$count যোগাযোগের সাথে শেয়ার করুন';
  }

  @override
  String shareWithContactsCount(int count) {
    return '$count যোগাযোগের সাথে শেয়ার করুন';
  }

  @override
  String get contactsPermissionRequired => 'যোগাযোগ অনুমতি প্রয়োজন';

  @override
  String get contactsPermissionRequiredForSms => 'SMS এর মাধ্যমে শেয়ার করার জন্য যোগাযোগ অনুমতি প্রয়োজন';

  @override
  String get grantContactsPermissionForSms => 'SMS এর মাধ্যমে শেয়ার করার জন্য দয়া করে যোগাযোগ অনুমতি দিন';

  @override
  String get noContactsWithPhoneNumbers => 'ফোন নম্বর সহ কোন যোগাযোগ পাওয়া যায়নি';

  @override
  String get noContactsMatchSearch => 'আপনার অনুসন্ধানের সাথে কোন যোগাযোগ মেলে না';

  @override
  String get failedToLoadContacts => 'যোগাযোগ লোড করতে ব্যর্থ';

  @override
  String get failedToPrepareConversationForSharing =>
      'শেয়ারিংয়ের জন্য কথোপকথন প্রস্তুত করতে ব্যর্থ। দয়া করে আবার চেষ্টা করুন।';

  @override
  String get couldNotOpenSmsApp => 'SMS অ্যাপ খুলতে পারেনি। দয়া করে আবার চেষ্টা করুন।';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'এখানে আমরা যা আলোচনা করেছি তা: $link';
  }

  @override
  String get wifiSync => 'Wi-Fi সিঙ্ক';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item ক্লিপবোর্ডে কপি করা হয়েছে';
  }

  @override
  String get wifiConnectionFailedTitle => 'সংযোগ ব্যর্থ';

  @override
  String connectingToDeviceName(String deviceName) {
    return '$deviceName এর সাথে সংযুক্ত হচ্ছে';
  }

  @override
  String enableDeviceWifi(String deviceName) {
    return '$deviceName এর Wi-Fi সক্ষম করুন';
  }

  @override
  String connectToDeviceName(String deviceName) {
    return '$deviceName এর সাথে সংযুক্ত করুন';
  }

  @override
  String get recordingDetails => 'রেকর্ডিং বিস্তারিত';

  @override
  String get storageLocationSdCard => 'SD কার্ড';

  @override
  String get storageLocationLimitlessPendant => 'সীমাহীন পেন্ডেন্ট';

  @override
  String get storageLocationPhone => 'ফোন';

  @override
  String get storageLocationPhoneMemory => 'ফোন (মেমরি)';

  @override
  String storedOnDevice(String deviceName) {
    return '$deviceName এ সংরক্ষিত';
  }

  @override
  String get transferring => 'স্থানান্তর করা হচ্ছে...';

  @override
  String get transferRequired => 'স্থানান্তর প্রয়োজন';

  @override
  String get downloadingAudioFromSdCard => 'আপনার ডিভাইসের SD কার্ড থেকে অডিও ডাউনলোড করা হচ্ছে';

  @override
  String get transferRequiredDescription =>
      'এই রেকর্ডিং আপনার ডিভাইসের SD কার্ডে সংরক্ষিত। এটি প্লে বা শেয়ার করতে আপনার ফোনে স্থানান্তর করুন।';

  @override
  String get cancelTransfer => 'স্থানান্তর বাতিল করুন';

  @override
  String get transferToPhone => 'ফোনে স্থানান্তর করুন';

  @override
  String get privateAndSecureOnDevice => 'আপনার ডিভাইসে ব্যক্তিগত এবং সুরক্ষিত';

  @override
  String get recordingInfo => 'রেকর্ডিং তথ্য';

  @override
  String get transferInProgress => 'ট্রান্সফার চলছে...';

  @override
  String get shareRecording => 'রেকর্ডিং শেয়ার করুন';

  @override
  String get deleteRecordingConfirmation =>
      'আপনি কি নিশ্চিত যে এই রেকর্ডিং স্থায়ীভাবে মুছে ফেলতে চান? এটি পূর্বাবস্থায় ফিরানো যাবে না।';

  @override
  String get recordingIdLabel => 'রেকর্ডিং আইডি';

  @override
  String get dateTimeLabel => 'তারিখ ও সময়';

  @override
  String get durationLabel => 'দৈর্ঘ্য';

  @override
  String get audioFormatLabel => 'অডিও ফর্ম্যাট';

  @override
  String get storageLocationLabel => 'সংরক্ষণ স্থান';

  @override
  String get estimatedSizeLabel => 'আনুমানিক আকার';

  @override
  String get deviceModelLabel => 'ডিভাইসের মডেল';

  @override
  String get deviceIdLabel => 'ডিভাইস আইডি';

  @override
  String get statusLabel => 'অবস্থা';

  @override
  String get statusProcessed => 'প্রক্রিয়াকৃত';

  @override
  String get statusUnprocessed => 'প্রক্রিয়াকরণ না করা';

  @override
  String get switchedToFastTransfer => 'দ্রুত ট্রান্সফারে স্যুইচ করা হয়েছে';

  @override
  String get transferCompleteMessage => 'ট্রান্সফার সম্পূর্ণ! এখন আপনি এই রেকর্ডিং চালাতে পারেন।';

  @override
  String transferFailedMessage(String error) {
    return 'ট্রান্সফার ব্যর্থ: $error';
  }

  @override
  String get transferCancelled => 'ট্রান্সফার বাতিল করা হয়েছে';

  @override
  String get fastTransferEnabled => 'দ্রুত ট্রান্সফার সক্ষম';

  @override
  String get bluetoothSyncEnabled => 'ব্লুটুথ সিঙ্ক সক্ষম';

  @override
  String get enableFastTransfer => 'দ্রুত ট্রান্সফার সক্ষম করুন';

  @override
  String get fastTransferDescription =>
      'দ্রুত ট্রান্সফার WiFi ব্যবহার করে ~৫ গুণ দ্রুত গতি প্রদান করে। ট্রান্সফারের সময় আপনার ফোন আপনার Omi ডিভাইসের WiFi নেটওয়ার্কের সাথে সাময়িকভাবে সংযুক্ত হবে।';

  @override
  String get internetAccessPausedDuringTransfer => 'ট্রান্সফারের সময় ইন্টারনেট অ্যাক্সেস বন্ধ রয়েছে';

  @override
  String get chooseTransferMethodDescription =>
      'আপনার Omi ডিভাইস থেকে আপনার ফোনে রেকর্ডিং কীভাবে স্থানান্তরিত হবে তা নির্বাচন করুন।';

  @override
  String get wifiSpeed => 'WiFi এর মাধ্যমে ~১৫০ কেবি/সেক';

  @override
  String get fiveTimesFaster => '৫ গুণ দ্রুত';

  @override
  String get fastTransferMethodDescription =>
      'আপনার Omi ডিভাইসের সাথে সরাসরি WiFi সংযোগ তৈরি করে। ট্রান্সফারের সময় আপনার ফোন আপনার নিয়মিত WiFi থেকে সাময়িকভাবে সংযোগ বিচ্ছিন্ন হয়।';

  @override
  String get bluetooth => 'ব্লুটুথ';

  @override
  String get bleSpeed => 'BLE এর মাধ্যমে ~৩০ কেবি/সেক';

  @override
  String get bluetoothMethodDescription =>
      'আদর্শ ব্লুটুথ লো এনার্জি সংযোগ ব্যবহার করে। ধীর কিন্তু আপনার WiFi সংযোগকে প্রভাবিত করে না।';

  @override
  String get selected => 'নির্বাচিত';

  @override
  String get selectOption => 'নির্বাচন করুন';

  @override
  String get lowBatteryAlertTitle => 'কম ব্যাটারির সতর্কতা';

  @override
  String get lowBatteryAlertBody => 'আপনার ডিভাইসের ব্যাটারি কম হয়ে যাচ্ছে। চার্জ করার সময় এসেছে! 🔋';

  @override
  String get deviceDisconnectedNotificationTitle => 'আপনার Omi ডিভাইস সংযোগ বিচ্ছিন্ন হয়েছে';

  @override
  String get deviceDisconnectedNotificationBody => 'আপনার Omi ব্যবহার চালিয়ে যেতে পুনরায় সংযুক্ত করুন।';

  @override
  String get firmwareUpdateAvailable => 'ফার্মওয়্যার আপডেট উপলব্ধ';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'আপনার Omi ডিভাইসের জন্য একটি নতুন ফার্মওয়্যার আপডেট ($version) উপলব্ধ। এখনই আপডেট করতে চান?';
  }

  @override
  String get later => 'পরে';

  @override
  String get appDeletedSuccessfully => 'অ্যাপ সফলভাবে মুছে ফেলা হয়েছে';

  @override
  String get appDeleteFailed => 'অ্যাপ মুছতে ব্যর্থ। দয়া করে পরে আবার চেষ্টা করুন।';

  @override
  String get appVisibilityChangedSuccessfully =>
      'অ্যাপের দৃশ্যমানতা সফলভাবে পরিবর্তিত হয়েছে। এটি প্রতিফলিত হতে কয়েক মিনিট সময় লাগতে পারে।';

  @override
  String get errorActivatingAppIntegration =>
      'অ্যাপ সক্রিয়করণে ত্রুটি। যদি এটি একটি সংহতকরণ অ্যাপ হয় তবে সেটআপ সম্পূর্ণ হয়েছে তা নিশ্চিত করুন।';

  @override
  String get errorUpdatingAppStatus => 'অ্যাপের অবস্থা আপডেট করার সময় একটি ত্রুটি ঘটেছে।';

  @override
  String get calculatingETA => 'গণনা করছি...';

  @override
  String aboutMinutesRemaining(int minutes) {
    return 'প্রায় $minutes মিনিট বাকি';
  }

  @override
  String get aboutAMinuteRemaining => 'প্রায় একটি মিনিট বাকি';

  @override
  String get almostDone => 'প্রায় সম্পন্ন...';

  @override
  String get omiSays => 'omi বলে';

  @override
  String get analyzingYourData => 'আপনার ডেটা বিশ্লেষণ করছি...';

  @override
  String migratingToProtection(String level) {
    return '$level সুরক্ষায় স্থানান্তরিত হচ্ছে...';
  }

  @override
  String get noDataToMigrateFinalizing => 'কোনো ডেটা স্থানান্তরিত হবে না। চূড়ান্ত করছি...';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return '$itemType স্থানান্তরিত হচ্ছে... $percentage%';
  }

  @override
  String get allObjectsMigratedFinalizing => 'সমস্ত অবজেক্ট স্থানান্তরিত হয়েছে। চূড়ান্ত করছি...';

  @override
  String get migrationErrorOccurred => 'স্থানান্তরের সময় একটি ত্রুটি ঘটেছে। দয়া করে আবার চেষ্টা করুন।';

  @override
  String get migrationComplete => 'স্থানান্তর সম্পূর্ণ!';

  @override
  String dataProtectedWithSettings(String level) {
    return 'আপনার ডেটা এখন নতুন $level সেটিংস দিয়ে সুরক্ষিত।';
  }

  @override
  String get chatsLowercase => 'চ্যাট';

  @override
  String get dataLowercase => 'ডেটা';

  @override
  String get fallNotificationTitle => 'আউচ';

  @override
  String get fallNotificationBody => 'আপনি পড়ে গেছেন?';

  @override
  String get importantConversationTitle => 'গুরুত্বপূর্ণ কথোপকথন';

  @override
  String get importantConversationBody =>
      'আপনি এইমাত্র একটি গুরুত্বপূর্ণ কথোপকথন করেছেন। সারসংক্ষেপ অন্যদের সাথে শেয়ার করতে ট্যাপ করুন।';

  @override
  String get templateName => 'টেমপ্লেটের নাম';

  @override
  String get templateNameHint => 'যেমন, মিটিং অ্যাকশন আইটেম এক্সট্রাক্টর';

  @override
  String get nameMustBeAtLeast3Characters => 'নাম কমপক্ষে ৩টি অক্ষর হতে হবে';

  @override
  String get conversationPromptHint =>
      'যেমন, প্রদত্ত কথোপকথন থেকে কর্ম সামগ্রী, সিদ্ধান্ত এবং মূল টেকওভার গুলি বের করুন।';

  @override
  String get pleaseEnterAppPrompt => 'অনুগ্রহ করে আপনার অ্যাপের জন্য একটি প্রম্পট লিখুন';

  @override
  String get promptMustBeAtLeast10Characters => 'প্রম্পট কমপক্ষে ১০টি অক্ষর হতে হবে';

  @override
  String get anyoneCanDiscoverTemplate => 'যে কেউ আপনার টেমপ্লেট আবিষ্কার করতে পারে';

  @override
  String get onlyYouCanUseTemplate => 'শুধুমাত্র আপনি এই টেমপ্লেট ব্যবহার করতে পারেন';

  @override
  String get generatingDescription => 'বর্ণনা তৈরি করছি...';

  @override
  String get creatingAppIcon => 'অ্যাপ আইকন তৈরি করছি...';

  @override
  String get installingApp => 'অ্যাপ ইনস্টল করছি...';

  @override
  String get appCreatedAndInstalled => 'অ্যাপ তৈরি এবং ইনস্টল করা হয়েছে!';

  @override
  String get appCreatedSuccessfully => 'অ্যাপ সফলভাবে তৈরি হয়েছে!';

  @override
  String get failedToCreateApp => 'অ্যাপ তৈরি করতে ব্যর্থ। দয়া করে আবার চেষ্টা করুন।';

  @override
  String get addAppSelectCoreCapability => 'এগিয়ে যেতে আপনার অ্যাপের জন্য আরও একটি মূল ক্ষমতা নির্বাচন করুন';

  @override
  String get addAppSelectPaymentPlan => 'আপনার অ্যাপের জন্য একটি পেমেন্ট পরিকল্পনা নির্বাচন করুন এবং একটি মূল্য লিখুন';

  @override
  String get addAppSelectCapability => 'আপনার অ্যাপের জন্য কমপক্ষে একটি ক্ষমতা নির্বাচন করুন';

  @override
  String get addAppSelectLogo => 'আপনার অ্যাপের জন্য একটি লোগো নির্বাচন করুন';

  @override
  String get addAppEnterChatPrompt => 'আপনার অ্যাপের জন্য একটি চ্যাট প্রম্পট লিখুন';

  @override
  String get addAppEnterConversationPrompt => 'আপনার অ্যাপের জন্য একটি কথোপকথন প্রম্পট লিখুন';

  @override
  String get addAppSelectTriggerEvent => 'আপনার অ্যাপের জন্য একটি ট্রিগার ইভেন্ট নির্বাচন করুন';

  @override
  String get addAppEnterWebhookUrl => 'আপনার অ্যাপের জন্য একটি ওয়েবহুক URL লিখুন';

  @override
  String get addAppSelectCategory => 'আপনার অ্যাপের জন্য একটি বিভাগ নির্বাচন করুন';

  @override
  String get addAppFillRequiredFields => 'সমস্ত প্রয়োজনীয় ক্ষেত্র সঠিকভাবে পূরণ করুন';

  @override
  String get addAppUpdatedSuccess => 'অ্যাপ সফলভাবে আপডেট হয়েছে 🚀';

  @override
  String get addAppUpdateFailed => 'অ্যাপ আপডেট করতে ব্যর্থ। দয়া করে পরে আবার চেষ্টা করুন';

  @override
  String get addAppSubmittedSuccess => 'অ্যাপ সফলভাবে জমা দেওয়া হয়েছে 🚀';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'ফাইল পিকার খোলার ত্রুটি: $message';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'ছবি নির্বাচনের ত্রুটি: $error';
  }

  @override
  String get addAppPhotosPermissionDenied => 'ফটো অনুমতি প্রত্যাখ্যাত। একটি ছবি নির্বাচন করতে ফটোগুলিতে অ্যাক্সেস দিন';

  @override
  String get addAppErrorSelectingImageRetry => 'ছবি নির্বাচনে ত্রুটি। দয়া করে আবার চেষ্টা করুন।';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'থাম্বনেইল নির্বাচনের ত্রুটি: $error';
  }

  @override
  String get addAppErrorSelectingThumbnailRetry => 'থাম্বনেইল নির্বাচনে ত্রুটি। দয়া করে আবার চেষ্টা করুন।';

  @override
  String get addAppCapabilityConflictWithPersona => 'পার্সোনা এর সাথে অন্যান্য ক্ষমতা নির্বাচন করা যায় না';

  @override
  String get addAppPersonaConflictWithCapabilities => 'অন্যান্য ক্ষমতার সাথে পার্সোনা নির্বাচন করা যায় না';

  @override
  String get paymentFailedToFetchCountries => 'সমর্থিত দেশ নিয়ে আসতে ব্যর্থ। দয়া করে পরে আবার চেষ্টা করুন।';

  @override
  String get paymentFailedToSetDefault => 'ডিফল্ট পেমেন্ট পদ্ধতি সেট করতে ব্যর্থ। দয়া করে পরে আবার চেষ্টা করুন।';

  @override
  String get paymentFailedToSavePaypal => 'PayPal বিবরণ সংরক্ষণ করতে ব্যর্থ। দয়া করে পরে আবার চেষ্টা করুন।';

  @override
  String get paypalEmailHint => 'nik@example.com';

  @override
  String get paypalMeLinkHint => 'paypal.me/nik';

  @override
  String get paymentMethodStripe => 'Stripe';

  @override
  String get paymentMethodPayPal => 'PayPal';

  @override
  String get paymentStatusActive => 'সক্রিয়';

  @override
  String get paymentStatusConnected => 'সংযুক্ত';

  @override
  String get paymentStatusNotConnected => 'সংযুক্ত নয়';

  @override
  String get paymentAppCost => 'অ্যাপের খরচ';

  @override
  String get paymentEnterValidAmount => 'একটি বৈধ পরিমাণ লিখুন';

  @override
  String get paymentEnterAmountGreaterThanZero => '০ এর চেয়ে বেশি একটি পরিমাণ লিখুন';

  @override
  String get paymentPlan => 'পেমেন্ট পরিকল্পনা';

  @override
  String get paymentNoneSelected => 'কোনো নির্বাচিত নয়';

  @override
  String get aiGenPleaseEnterDescription => 'আপনার অ্যাপের জন্য একটি বর্ণনা লিখুন';

  @override
  String get aiGenCreatingAppIcon => 'অ্যাপ আইকন তৈরি করছি...';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'একটি ত্রুটি ঘটেছে: $message';
  }

  @override
  String get aiGenAppCreatedSuccessfully => 'অ্যাপ সফলভাবে তৈরি হয়েছে!';

  @override
  String get aiGenFailedToCreateApp => 'অ্যাপ তৈরি করতে ব্যর্থ';

  @override
  String get aiGenErrorWhileCreatingApp => 'অ্যাপ তৈরির সময় একটি ত্রুটি ঘটেছে';

  @override
  String get aiGenFailedToGenerateApp => 'অ্যাপ তৈরি করতে ব্যর্থ। দয়া করে আবার চেষ্টা করুন।';

  @override
  String get aiGenFailedToRegenerateIcon => 'আইকন পুনরায় তৈরি করতে ব্যর্থ';

  @override
  String get aiGenPleaseGenerateAppFirst => 'প্রথমে একটি অ্যাপ তৈরি করুন';

  @override
  String get nextButton => 'পরবর্তী';

  @override
  String get connectOmiDevice => 'Omi ডিভাইস সংযুক্ত করুন';

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'আপনি আপনার আনলিমিটেড পরিকল্পনা $title এ স্যুইচ করছেন। আপনি কি এগিয়ে যেতে চান?';
  }

  @override
  String get planUpgradeScheduledMessage =>
      'আপগ্রেড নির্ধারিত হয়েছে! আপনার মাসিক পরিকল্পনা আপনার বিলিং সময়কালের শেষ পর্যন্ত চলতে থাকে, তারপর স্বয়ংক্রিয়ভাবে বার্ষিকতে স্যুইচ হয়।';

  @override
  String get couldNotSchedulePlanChange => 'পরিকল্পনা পরিবর্তন নির্ধারণ করা যায়নি। দয়া করে আবার চেষ্টা করুন।';

  @override
  String get subscriptionReactivatedDefault =>
      'আপনার সাবস্ক্রিপশন পুনরায় সক্রিয় করা হয়েছে! এখন কোনো চার্জ নেই - আপনার বর্তমান সময়কালের শেষে বিলিং করা হবে।';

  @override
  String get subscriptionSuccessfulCharged => 'সাবস্ক্রিপশন সফল! নতুন বিলিং সময়কালের জন্য আপনাকে চার্জ করা হয়েছে।';

  @override
  String get couldNotProcessSubscription => 'সাবস্ক্রিপশন প্রক্রিয়াজাত করা যায়নি। দয়া করে আবার চেষ্টা করুন।';

  @override
  String get couldNotLaunchUpgradePage => 'আপগ্রেড পৃষ্ঠা চালু করা যায়নি। দয়া করে আবার চেষ্টা করুন।';

  @override
  String get transcriptionJsonPlaceholder => 'আপনার JSON কনফিগারেশন এখানে পেস্ট করুন...';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get pricePlaceholder => '0.00';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'ফাইল পিকার খোলার ত্রুটি: $message';
  }

  @override
  String importErrorGeneric(String error) {
    return 'ত্রুটি: $error';
  }

  @override
  String get mergeConversationsSuccessTitle => 'কথোপকথন সফলভাবে একীভূত হয়েছে';

  @override
  String mergeConversationsSuccessBody(int count) {
    return '$count টি কথোপকথন সফলভাবে একীভূত হয়েছে';
  }

  @override
  String get actionItemReminderTitle => 'Omi রিমাইন্ডার';

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName সংযোগ বিচ্ছিন্ন';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'আপনার $deviceName ব্যবহার চালিয়ে যেতে পুনরায় সংযুক্ত করুন।';
  }

  @override
  String get onboardingSignIn => 'সাইন ইন করুন';

  @override
  String get onboardingYourName => 'আপনার নাম';

  @override
  String get onboardingLanguage => 'ভাষা';

  @override
  String get onboardingPermissions => 'অনুমতি';

  @override
  String get onboardingComplete => 'সম্পূর্ণ';

  @override
  String get onboardingWelcomeToOmi => 'Omi তে স্বাগতম';

  @override
  String get onboardingTellUsAboutYourself => 'আমাদের আপনার সম্পর্কে বলুন';

  @override
  String get onboardingChooseYourPreference => 'আপনার পছন্দ নির্বাচন করুন';

  @override
  String get onboardingGrantRequiredAccess => 'প্রয়োজনীয় অ্যাক্সেস দিন';

  @override
  String get onboardingYoureAllSet => 'আপনি সব প্রস্তুত';

  @override
  String get searchTranscriptOrSummary => 'প্রতিলেখ বা সারসংক্ষেপ অনুসন্ধান করুন...';

  @override
  String get myGoal => 'আমার লক্ষ্য';

  @override
  String get appNotAvailable => 'আপস! আপনি যে অ্যাপটি খুঁজছেন তা উপলব্ধ নয় বলে মনে হচ্ছে।';

  @override
  String get failedToConnectTodoist => 'Todoist এ সংযোগ করতে ব্যর্থ';

  @override
  String get failedToConnectAsana => 'Asana তে সংযোগ করতে ব্যর্থ';

  @override
  String get failedToConnectGoogleTasks => 'Google Tasks এ সংযোগ করতে ব্যর্থ';

  @override
  String get failedToConnectClickUp => 'ClickUp এ সংযোগ করতে ব্যর্থ';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return '$serviceName এ সংযোগ করতে ব্যর্থ: $error';
  }

  @override
  String get successfullyConnectedTodoist => 'Todoist এ সফলভাবে সংযুক্ত!';

  @override
  String get failedToConnectTodoistRetry => 'Todoist এ সংযোগ করতে ব্যর্থ। দয়া করে আবার চেষ্টা করুন।';

  @override
  String get successfullyConnectedAsana => 'Asana তে সফলভাবে সংযুক্ত!';

  @override
  String get failedToConnectAsanaRetry => 'Asana তে সংযোগ করতে ব্যর্থ। দয়া করে আবার চেষ্টা করুন।';

  @override
  String get successfullyConnectedGoogleTasks => 'Google Tasks এ সফলভাবে সংযুক্ত!';

  @override
  String get failedToConnectGoogleTasksRetry => 'Google Tasks এ সংযোগ করতে ব্যর্থ। দয়া করে আবার চেষ্টা করুন।';

  @override
  String get successfullyConnectedClickUp => 'ClickUp এ সফলভাবে সংযুক্ত!';

  @override
  String get failedToConnectClickUpRetry => 'ClickUp এ সংযোগ করতে ব্যর্থ। দয়া করে আবার চেষ্টা করুন।';

  @override
  String get successfullyConnectedNotion => 'Notion এ সফলভাবে সংযুক্ত!';

  @override
  String get failedToRefreshNotionStatus => 'Notion সংযোগ অবস্থা রিফ্রেশ করতে ব্যর্থ।';

  @override
  String get successfullyConnectedGoogle => 'Google এ সফলভাবে সংযুক্ত!';

  @override
  String get failedToRefreshGoogleStatus => 'Google সংযোগ অবস্থা রিফ্রেশ করতে ব্যর্থ।';

  @override
  String get successfullyConnectedWhoop => 'Whoop এ সফলভাবে সংযুক্ত!';

  @override
  String get failedToRefreshWhoopStatus => 'Whoop সংযোগ অবস্থা রিফ্রেশ করতে ব্যর্থ।';

  @override
  String get successfullyConnectedGitHub => 'GitHub এ সফলভাবে সংযুক্ত!';

  @override
  String get failedToRefreshGitHubStatus => 'GitHub সংযোগ অবস্থা রিফ্রেশ করতে ব্যর্থ।';

  @override
  String get authFailedToSignInWithGoogle => 'Google দিয়ে সাইন ইন করতে ব্যর্থ, দয়া করে আবার চেষ্টা করুন।';

  @override
  String get authenticationFailed => 'প্রমাণীকরণ ব্যর্থ। দয়া করে আবার চেষ্টা করুন।';

  @override
  String get authFailedToSignInWithApple => 'Apple দিয়ে সাইন ইন করতে ব্যর্থ, দয়া করে আবার চেষ্টা করুন।';

  @override
  String get authFailedToRetrieveToken => 'Firebase টোকেন পুনরুদ্ধার করতে ব্যর্থ, দয়া করে আবার চেষ্টা করুন।';

  @override
  String get authUnexpectedErrorFirebase =>
      'সাইন ইন করতে অপ্রত্যাশিত ত্রুটি, Firebase ত্রুটি, দয়া করে আবার চেষ্টা করুন।';

  @override
  String get authUnexpectedError => 'সাইন ইন করতে অপ্রত্যাশিত ত্রুটি, দয়া করে আবার চেষ্টা করুন';

  @override
  String get authFailedToLinkGoogle => 'Google এর সাথে লিঙ্ক করতে ব্যর্থ, দয়া করে আবার চেষ্টা করুন।';

  @override
  String get authFailedToLinkApple => 'Apple এর সাথে লিঙ্ক করতে ব্যর্থ, দয়া করে আবার চেষ্টা করুন।';

  @override
  String get onboardingBluetoothRequired => 'আপনার ডিভাইসের সাথে সংযোগ করতে ব্লুটুথ অনুমতি প্রয়োজন।';

  @override
  String get onboardingBluetoothDeniedSystemPrefs => 'ব্লুটুথ অনুমতি প্রত্যাখ্যাত। সিস্টেম পছন্দগুলিতে অনুমতি দিন।';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'ব্লুটুথ অনুমতি স্থিতি: $status। সিস্টেম পছন্দগুলি পরীক্ষা করুন।';
  }

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'ব্লুটুথ অনুমতি পরীক্ষা করতে ব্যর্থ: $error';
  }

  @override
  String get onboardingNotificationDeniedSystemPrefs =>
      'বিজ্ঞপ্তি অনুমতি প্রত্যাখ্যাত। সিস্টেম পছন্দগুলিতে অনুমতি দিন।';

  @override
  String get onboardingNotificationDeniedNotifications =>
      'বিজ্ঞপ্তি অনুমতি প্রত্যাখ্যাত। সিস্টেম পছন্দগুলি > বিজ্ঞপ্তিতে অনুমতি দিন।';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return 'বিজ্ঞপ্তি অনুমতি স্থিতি: $status। সিস্টেম পছন্দগুলি পরীক্ষা করুন।';
  }

  @override
  String onboardingFailedCheckNotification(String error) {
    return 'বিজ্ঞপ্তি অনুমতি পরীক্ষা করতে ব্যর্থ: $error';
  }

  @override
  String get onboardingLocationGrantInSettings => 'সেটিংস > গোপনীয়তা ও নিরাপত্তা > অবস্থান সেবায় অবস্থান অনুমতি দিন';

  @override
  String get onboardingMicrophoneRequired => 'রেকর্ডিংয়ের জন্য মাইক্রোফোন অনুমতি প্রয়োজন।';

  @override
  String get onboardingMicrophoneDenied =>
      'মাইক্রোফোন অনুমতি প্রত্যাখ্যাত। সিস্টেম পছন্দগুলি > গোপনীয়তা ও নিরাপত্তা > মাইক্রোফোনে অনুমতি দিন।';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'মাইক্রোফোন অনুমতি স্থিতি: $status। সিস্টেম পছন্দগুলি পরীক্ষা করুন।';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'মাইক্রোফোন অনুমতি পরীক্ষা করতে ব্যর্থ: $error';
  }

  @override
  String get onboardingScreenCaptureRequired => 'সিস্টেম অডিও রেকর্ডিংয়ের জন্য স্ক্রীন ক্যাপচার অনুমতি প্রয়োজন।';

  @override
  String get onboardingScreenCaptureDenied =>
      'স্ক্রীন ক্যাপচার অনুমতি প্রত্যাখ্যাত। সিস্টেম পছন্দগুলি > গোপনীয়তা ও নিরাপত্তা > স্ক্রীন রেকর্ডিংয়ে অনুমতি দিন।';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return 'স্ক্রীন ক্যাপচার অনুমতি স্থিতি: $status। সিস্টেম পছন্দগুলি পরীক্ষা করুন।';
  }

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return 'স্ক্রীন ক্যাপচার অনুমতি পরীক্ষা করতে ব্যর্থ: $error';
  }

  @override
  String get onboardingAccessibilityRequired => 'ব্রাউজার মিটিং সনাক্ত করার জন্য অ্যাক্সেসযোগ্যতা অনুমতি প্রয়োজন।';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'অ্যাক্সেসযোগ্যতা অনুমতি স্থিতি: $status। সিস্টেম পছন্দগুলি পরীক্ষা করুন।';
  }

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'অ্যাক্সেসযোগ্যতা অনুমতি পরীক্ষা করতে ব্যর্থ: $error';
  }

  @override
  String get msgCameraNotAvailable => 'ক্যামেরা ক্যাপচার এই প্ল্যাটফর্মে উপলব্ধ নয়';

  @override
  String get msgCameraPermissionDenied => 'ক্যামেরা অনুমতি প্রত্যাখ্যাত। ক্যামেরায় অ্যাক্সেস দিন';

  @override
  String msgCameraAccessError(String error) {
    return 'ক্যামেরা অ্যাক্সেস করতে ত্রুটি: $error';
  }

  @override
  String get msgPhotoError => 'ছবি তুলতে ত্রুটি। দয়া করে আবার চেষ্টা করুন।';

  @override
  String get msgMaxImagesLimit => 'আপনি শুধুমাত্র ৪টি পর্যন্ত ছবি নির্বাচন করতে পারেন';

  @override
  String msgFilePickerError(String error) {
    return 'ফাইল পিকার খোলার ত্রুটি: $error';
  }

  @override
  String msgSelectImagesError(String error) {
    return 'ছবি নির্বাচনের ত্রুটি: $error';
  }

  @override
  String get msgPhotosPermissionDenied => 'ফটো অনুমতি প্রত্যাখ্যাত। ছবি নির্বাচন করতে ফটোগুলিতে অ্যাক্সেস দিন';

  @override
  String get msgSelectImagesGenericError => 'ছবি নির্বাচনে ত্রুটি। দয়া করে আবার চেষ্টা করুন।';

  @override
  String get msgMaxFilesLimit => 'আপনি শুধুমাত্র ৪টি পর্যন্ত ফাইল নির্বাচন করতে পারেন';

  @override
  String msgSelectFilesError(String error) {
    return 'ফাইল নির্বাচনের ত্রুটি: $error';
  }

  @override
  String get msgSelectFilesGenericError => 'ফাইল নির্বাচনে ত্রুটি। দয়া করে আবার চেষ্টা করুন।';

  @override
  String get msgUploadFileFailed => 'ফাইল আপলোড করতে ব্যর্থ, দয়া করে পরে আবার চেষ্টা করুন';

  @override
  String get msgReadingMemories => 'আপনার স্মৃতি পড়ছি...';

  @override
  String get msgLearningMemories => 'আপনার স্মৃতি থেকে শিখছি...';

  @override
  String get msgUploadAttachedFileFailed => 'সংযুক্ত ফাইল আপলোড করতে ব্যর্থ।';

  @override
  String captureRecordingError(String error) {
    return 'রেকর্ডিংয়ের সময় একটি ত্রুটি ঘটেছে: $error';
  }

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return 'রেকর্ডিং বন্ধ হয়েছে: $reason। আপনাকে বাহ্যিক ডিসপ্লে পুনরায় সংযুক্ত করতে বা রেকর্ডিং পুনরায় শুরু করতে হতে পারে।';
  }

  @override
  String get captureMicrophonePermissionRequired => 'মাইক্রোফোন অনুমতি প্রয়োজন';

  @override
  String get captureMicrophonePermissionInSystemPreferences => 'সিস্টেম পছন্দগুলিতে মাইক্রোফোন অনুমতি দিন';

  @override
  String get captureScreenRecordingPermissionRequired => 'স্ক্রীন রেকর্ডিং অনুমতি প্রয়োজন';

  @override
  String get captureDisplayDetectionFailed => 'ডিসপ্লে সনাক্তকরণ ব্যর্থ। রেকর্ডিং বন্ধ হয়েছে।';

  @override
  String get devModeInvalidAudioBytesWebhookUrl => 'অবৈধ অডিও বাইটস ওয়েবহুক URL';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl => 'অবৈধ রিয়েল-টাইম প্রতিলেখ ওয়েবহুক URL';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl => 'অবৈধ কথোপকথন তৈরি ওয়েবহুক URL';

  @override
  String get devModeInvalidDaySummaryWebhookUrl => 'অবৈধ দিন সারসংক্ষেপ ওয়েবহুক URL';

  @override
  String get devModeSettingsSaved => 'সেটিংস সংরক্ষণ করা হয়েছে!';

  @override
  String get voiceFailedToTranscribe => 'Failed to transcribe audio';

  @override
  String get locationPermissionRequired => 'অবস্থান অনুমতি প্রয়োজন';

  @override
  String get locationPermissionContent =>
      'দ্রুত ট্রান্সফার WiFi সংযোগ যাচাই করতে অবস্থান অনুমতি প্রয়োজন। এগিয়ে যেতে অবস্থান অনুমতি দিন।';

  @override
  String get pdfTranscriptExport => 'প্রতিলেখ রপ্তানি';

  @override
  String get pdfConversationExport => 'কথোপকথন রপ্তানি';

  @override
  String pdfTitleLabel(String title) {
    return 'শিরোনাম: $title';
  }

  @override
  String get conversationNewIndicator => 'নতুন 🚀';

  @override
  String conversationPhotosCount(int count) {
    return '$count ফটো';
  }

  @override
  String get mergingStatus => 'একীভূত হচ্ছে...';

  @override
  String timeSecsSingular(int count) {
    return '$count সেক';
  }

  @override
  String timeSecsPlural(int count) {
    return '$count সেক';
  }

  @override
  String timeMinSingular(int count) {
    return '$count মিনিট';
  }

  @override
  String timeMinsPlural(int count) {
    return '$count মিনিট';
  }

  @override
  String timeMinsAndSecs(int mins, int secs) {
    return '$mins মিনিট $secs সেক';
  }

  @override
  String timeHourSingular(int count) {
    return '$count ঘন্টা';
  }

  @override
  String timeHoursPlural(int count) {
    return '$count ঘন্টা';
  }

  @override
  String timeHoursAndMins(int hours, int mins) {
    return '$hours ঘন্টা $mins মিনিট';
  }

  @override
  String timeDaySingular(int count) {
    return '$count দিন';
  }

  @override
  String timeDaysPlural(int count) {
    return '$count দিন';
  }

  @override
  String timeDaysAndHours(int days, int hours) {
    return '$days দিন $hours ঘন্টা';
  }

  @override
  String timeCompactSecs(int count) {
    return '$countসেক';
  }

  @override
  String timeCompactMins(int count) {
    return '$countমি';
  }

  @override
  String timeCompactMinsAndSecs(int mins, int secs) {
    return '$minsমি $secsসেক';
  }

  @override
  String timeCompactHours(int count) {
    return '$countঘ';
  }

  @override
  String timeCompactHoursAndMins(int hours, int mins) {
    return '$hoursঘ $minsমি';
  }

  @override
  String get moveToFolder => 'ফোল্ডারে সরান';

  @override
  String get noFoldersAvailable => 'কোনো ফোল্ডার উপলব্ধ নয়';

  @override
  String get newFolder => 'নতুন ফোল্ডার';

  @override
  String get color => 'রঙ';

  @override
  String get waitingForDevice => 'ডিভাইসের জন্য অপেক্ষা করছি...';

  @override
  String get saySomething => 'কিছু বলুন...';

  @override
  String get initialisingSystemAudio => 'সিস্টেম অডিও শুরু করছি';

  @override
  String get stopRecording => 'রেকর্ডিং বন্ধ করুন';

  @override
  String get continueRecording => 'রেকর্ডিং চালিয়ে যান';

  @override
  String get initialisingRecorder => 'রেকর্ডার শুরু করছি';

  @override
  String get pauseRecording => 'রেকর্ডিং পজ করুন';

  @override
  String get resumeRecording => 'রেকর্ডিং চালু করুন';

  @override
  String get noDailyRecapsYet => 'এখনো কোনো দৈনিক সংক্ষেপ নেই';

  @override
  String get dailyRecapsDescription => 'আপনার দৈনিক সংক্ষেপ এখানে উপস্থিত হবে একবার তৈরি হয়ে গেলে';

  @override
  String get chooseTransferMethod => 'ট্রান্সফার পদ্ধতি নির্বাচন করুন';

  @override
  String get fastTransferSpeed => 'WiFi এর মাধ্যমে ~১৫০ কেবি/সেক';

  @override
  String largeTimeGapDetected(String gap) {
    return 'বড় সময়ের ব্যবধান সনাক্ত হয়েছে ($gap)';
  }

  @override
  String largeTimeGapsDetected(String gaps) {
    return 'বড় সময়ের ব্যবধান সনাক্ত হয়েছে ($gaps)';
  }

  @override
  String get deviceDoesNotSupportWifiSwitchingToBle => 'ডিভাইস WiFi সিঙ্ক সমর্থন করে না, ব্লুটুথে স্যুইচ করছি';

  @override
  String get appleHealthNotAvailable => 'এই ডিভাইসে Apple Health উপলব্ধ নয়';

  @override
  String get downloadAudio => 'অডিও ডাউনলোড করুন';

  @override
  String get audioDownloadSuccess => 'অডিও সফলভাবে ডাউনলোড করা হয়েছে';

  @override
  String get audioDownloadFailed => 'অডিও ডাউনলোড করতে ব্যর্থ';

  @override
  String get downloadingAudio => 'অডিও ডাউনলোড করছি...';

  @override
  String get shareAudio => 'অডিও শেয়ার করুন';

  @override
  String get preparingAudio => 'অডিও প্রস্তুত করছি';

  @override
  String get gettingAudioFiles => 'অডিও ফাইলগুলি পাচ্ছি...';

  @override
  String get downloadingAudioProgress => 'অডিও ডাউনলোড করছি';

  @override
  String get processingAudio => 'অডিও প্রক্রিয়া করছি';

  @override
  String get combiningAudioFiles => 'অডিও ফাইলগুলি একত্রিত করছি...';

  @override
  String get audioReady => 'অডিও প্রস্তুত';

  @override
  String get openingShareSheet => 'শেয়ার শীট খুলছি...';

  @override
  String get audioShareFailed => 'শেয়ার ব্যর্থ';

  @override
  String get dailyRecaps => 'দৈনিক সংক্ষেপ';

  @override
  String get removeFilter => 'ফিল্টার সরান';

  @override
  String get categoryConversationAnalysis => 'কথোপকথন বিশ্লেষণ';

  @override
  String get categoryHealth => 'স্বাস্থ্য';

  @override
  String get categoryEducation => 'শিক্ষা';

  @override
  String get categoryCommunication => 'যোগাযোগ';

  @override
  String get categoryEmotionalSupport => 'আবেগপূর্ণ সহায়তা';

  @override
  String get categoryProductivity => 'উৎপাদনশীলতা';

  @override
  String get categoryEntertainment => 'বিনোদন';

  @override
  String get categoryFinancial => 'আর্থিক';

  @override
  String get categoryTravel => 'ভ্রমণ';

  @override
  String get categorySafety => 'নিরাপত্তা';

  @override
  String get categoryShopping => 'কেনাকাটা';

  @override
  String get categorySocial => 'সামাজিক';

  @override
  String get categoryNews => 'খবর';

  @override
  String get categoryUtilities => 'ইউটিলিটিজ';

  @override
  String get categoryOther => 'অন্যান্য';

  @override
  String get capabilityChat => 'চ্যাট';

  @override
  String get capabilityConversations => 'কথোপকথন';

  @override
  String get capabilityExternalIntegration => 'বাহ্যিক সংহতকরণ';

  @override
  String get capabilityNotification => 'বিজ্ঞপ্তি';

  @override
  String get triggerAudioBytes => 'অডিও বাইটস';

  @override
  String get triggerConversationCreation => 'কথোপকথন সৃষ্টি';

  @override
  String get triggerTranscriptProcessed => 'প্রতিলেখ প্রক্রিয়াকৃত';

  @override
  String get actionCreateConversations => 'কথোপকথন তৈরি করুন';

  @override
  String get actionCreateMemories => 'স্মৃতি তৈরি করুন';

  @override
  String get actionReadConversations => 'কথোপকথন পড়ুন';

  @override
  String get actionReadMemories => 'স্মৃতি পড়ুন';

  @override
  String get actionReadTasks => 'কাজ পড়ুন';

  @override
  String get scopeUserName => 'ব্যবহারকারীর নাম';

  @override
  String get scopeUserFacts => 'ব্যবহারকারীর তথ্য';

  @override
  String get scopeUserConversations => 'ব্যবহারকারীর কথোপকথন';

  @override
  String get scopeUserChat => 'ব্যবহারকারীর চ্যাট';

  @override
  String get capabilitySummary => 'সারসংক্ষেপ';

  @override
  String get capabilityFeatured => 'বৈশিষ্ট্যপূর্ণ';

  @override
  String get capabilityTasks => 'কাজ';

  @override
  String get capabilityIntegrations => 'সংহতকরণ';

  @override
  String get categoryProductivityLifestyle => 'উৎপাদনশীলতা ও জীবনযাত্রা';

  @override
  String get categorySocialEntertainment => 'সামাজিক ও বিনোদন';

  @override
  String get categoryProductivityTools => 'উৎপাদনশীলতা ও সরঞ্জাম';

  @override
  String get categoryPersonalWellness => 'ব্যক্তিগত ও জীবনধারা';

  @override
  String get rating => 'রেটিং';

  @override
  String get categories => 'বিভাগ';

  @override
  String get sortBy => 'সাজান';

  @override
  String get highestRating => 'সর্বোচ্চ রেটিং';

  @override
  String get lowestRating => 'সর্বনিম্ন রেটিং';

  @override
  String get resetFilters => 'ফিল্টার রিসেট করুন';

  @override
  String get applyFilters => 'ফিল্টার প্রয়োগ করুন';

  @override
  String get mostInstalls => 'সবচেয়ে বেশি ইনস্টল';

  @override
  String get couldNotOpenUrl => 'URL খুলতে পারা যায়নি। আবার চেষ্টা করুন।';

  @override
  String get newTask => 'নতুন কাজ';

  @override
  String get viewAll => 'সব দেখুন';

  @override
  String get addTask => 'কাজ যোগ করুন';

  @override
  String get addMcpServer => 'MCP সার্ভার যোগ করুন';

  @override
  String get connectExternalAiTools => 'বাহ্যিক AI টুল সংযুক্ত করুন';

  @override
  String get mcpServerUrl => 'MCP সার্ভার URL';

  @override
  String mcpServerConnected(int count) {
    return '$count টুল সফলভাবে সংযুক্ত হয়েছে';
  }

  @override
  String get mcpConnectionFailed => 'MCP সার্ভারে সংযোগ ব্যর্থ হয়েছে';

  @override
  String get authorizingMcpServer => 'অনুমোদন করা হচ্ছে...';

  @override
  String get whereDidYouHearAboutOmi => 'আপনি আমাদের সম্পর্কে কীভাবে জানলেন?';

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
  String get friendWordOfMouth => 'বন্ধু';

  @override
  String get otherSource => 'অন্যান্য';

  @override
  String get pleaseSpecify => 'অনুগ্রহ করে উল্লেখ করুন';

  @override
  String get event => 'ইভেন্ট';

  @override
  String get coworker => 'সহকর্মী';

  @override
  String get linkedIn => 'LinkedIn';

  @override
  String get appStore => 'App Store';

  @override
  String get googleSearch => 'Google সার্চ';

  @override
  String get audioPlaybackUnavailable => 'অডিও ফাইল প্লেব্যাকের জন্য উপলব্ধ নয়';

  @override
  String get audioPlaybackFailed => 'অডিও চালাতে পারা যায়নি। ফাইলটি ক্ষতিগ্রস্ত বা অনুপলব্ধ হতে পারে।';

  @override
  String get connectionGuide => 'সংযোগ গাইড';

  @override
  String get iveDoneThis => 'আমি এটি করেছি';

  @override
  String get pairNewDevice => 'নতুন ডিভাইস পেয়ার করুন';

  @override
  String get dontSeeYourDevice => 'আপনার ডিভাইস দেখছেন না?';

  @override
  String get reportAnIssue => 'সমস্যার রিপোর্ট করুন';

  @override
  String get pairingTitleOmi => 'Omi চালু করুন';

  @override
  String get pairingDescOmi => 'এটি চালু করতে ডিভাইসটি ধরে রাখুন যতক্ষণ না এটি কাঁপে।';

  @override
  String get pairingTitleOmiDevkit => 'Omi DevKit পেয়ারিং মোডে রাখুন';

  @override
  String get pairingDescOmiDevkit => 'চালু করতে বোতাম একবার চাপুন। পেয়ারিং মোডে LED বেগুনি রঙে ঝলমলে করবে।';

  @override
  String get pairingTitleOmiGlass => 'Omi Glass চালু করুন';

  @override
  String get pairingDescOmiGlass => 'পাশের বোতাম 3 সেকেন্ডের জন্য চাপ দিয়ে চালু করুন।';

  @override
  String get pairingTitlePlaudNote => 'Plaud Note পেয়ারিং মোডে রাখুন';

  @override
  String get pairingDescPlaudNote =>
      'পাশের বোতাম 2 সেকেন্ডের জন্য চাপ দিয়ে ধরুন। লাল LED পেয়ার করার জন্য প্রস্তুত হলে ঝলমলে করবে।';

  @override
  String get pairingTitleBee => 'Bee পেয়ারিং মোডে রাখুন';

  @override
  String get pairingDescBee => 'বোতাম 5 বার ক্রমাগত চাপুন। আলো নীল এবং সবুজ রঙে ঝলমলে শুরু করবে।';

  @override
  String get pairingTitleLimitless => 'Limitless পেয়ারিং মোডে রাখুন';

  @override
  String get pairingDescLimitless =>
      'যখন কোনো আলো দৃশ্যমান হয়, একবার চাপুন এবং তারপর ধরে রাখুন যতক্ষণ না ডিভাইসটি গোলাপি আলো দেখায়, তারপর ছেড়ে দিন।';

  @override
  String get pairingTitleFriendPendant => 'Friend Pendant পেয়ারিং মোডে রাখুন';

  @override
  String get pairingDescFriendPendant =>
      'পেন্ডান্টে বোতাম চাপুন এটি চালু করতে। এটি স্বয়ংক্রিয়ভাবে পেয়ারিং মোডে প্রবেश করবে।';

  @override
  String get pairingTitleFieldy => 'Fieldy পেয়ারিং মোডে রাখুন';

  @override
  String get pairingDescFieldy => 'চালু করতে ডিভাইসটি চাপ দিয়ে ধরুন যতক্ষণ না আলো প্রদর্শিত হয়।';

  @override
  String get pairingTitleAppleWatch => 'Apple Watch সংযুক্ত করুন';

  @override
  String get pairingDescAppleWatch =>
      'আপনার Apple Watch-এ Omi অ্যাপ ইনস্টল এবং খুলুন, তারপর অ্যাপে সংযুক্ত ট্যাপ করুন।';

  @override
  String get pairingTitleNeoOne => 'Neo One পেয়ারিং মোডে রাখুন';

  @override
  String get pairingDescNeoOne => 'পাওয়ার বোতাম চাপ দিয়ে ধরুন যতক্ষণ না LED ঝলমলে করে। ডিভাইসটি আবিষ্কারযোগ্য হবে।';

  @override
  String get downloadingFromDevice => 'ডিভাইস থেকে ডাউনলোড করা হচ্ছে';

  @override
  String get reconnectingToInternet => 'ইন্টারনেটে পুনরায় সংযোগ করা হচ্ছে...';

  @override
  String uploadingToCloud(int current, int total) {
    return '$total এর $current আপলোড করা হচ্ছে';
  }

  @override
  String get processingOnServer => 'সার্ভারে প্রক্রিয়াজাত করা হচ্ছে...';

  @override
  String processingOnServerProgress(int current, int total) {
    return 'প্রক্রিয়াজাত করা হচ্ছে... $current/$total সেগমেন্ট';
  }

  @override
  String get processedStatus => 'প্রক্রিয়াজাত';

  @override
  String get corruptedStatus => 'ক্ষতিগ্রস্ত';

  @override
  String nPending(int count) {
    return '$count মুলতুবি';
  }

  @override
  String nProcessed(int count) {
    return '$count প্রক্রিয়াজাত';
  }

  @override
  String get synced => 'সিঙ্ক করা হয়েছে';

  @override
  String get noPendingRecordings => 'কোনো মুলতুবি রেকর্ডিং নেই';

  @override
  String get noProcessedRecordings => 'এখনো কোনো প্রক্রিয়াজাত রেকর্ডিং নেই';

  @override
  String get pending => 'মুলতুবি';

  @override
  String whatsNewInVersion(String version) {
    return '$version-তে নতুন কী আছে';
  }

  @override
  String get addToYourTaskList => 'আপনার কাজের তালিকায় যোগ করবেন?';

  @override
  String get failedToCreateShareLink => 'শেয়ার লিঙ্ক তৈরি করতে ব্যর্থ';

  @override
  String get deleteGoal => 'লক্ষ্য মুছুন';

  @override
  String get deviceUpToDate => 'আপনার ডিভাইস আপডেট আছে';

  @override
  String get wifiConfiguration => 'WiFi কনফিগারেশন';

  @override
  String get wifiConfigurationSubtitle => 'ফার্মওয়্যার ডাউনলোড করার জন্য আপনার WiFi শংসাপত্র প্রবেশ করুন।';

  @override
  String get networkNameSsid => 'নেটওয়ার্ক নাম (SSID)';

  @override
  String get enterWifiNetworkName => 'WiFi নেটওয়ার্ক নাম প্রবেশ করুন';

  @override
  String get enterWifiPassword => 'WiFi পাসওয়ার্ড প্রবেশ করুন';

  @override
  String get appIconLabel => 'অ্যাপ আইকন';

  @override
  String get onboardingWhatIKnowAboutYouTitle => 'এটি আমি আপনার সম্পর্কে জানি';

  @override
  String get onboardingWhatIKnowAboutYouDescription => 'এই ম্যাপটি আপডেট হয় যখন Omi আপনার কথোপকথন থেকে শিখে।';

  @override
  String get apiEnvironment => 'API পরিবেশ';

  @override
  String get apiEnvironmentDescription => 'কোন ব্যাকএন্ডে সংযোগ করতে হবে তা নির্বাচন করুন';

  @override
  String get production => 'উৎপাদন';

  @override
  String get staging => 'স্টেজিং';

  @override
  String get switchRequiresRestart => 'স্যুইচ করার জন্য অ্যাপ পুনরায় চালু করা প্রয়োজন';

  @override
  String get switchApiConfirmTitle => 'API পরিবেশ স্যুইচ করুন';

  @override
  String switchApiConfirmBody(String environment) {
    return '$environment-এ স্যুইচ করবেন? পরিবর্তনগুলি প্রয়োগ করতে অ্যাপটি বন্ধ এবং পুনরায় খুলতে হবে।';
  }

  @override
  String get switchAndRestart => 'স্যুইচ করুন';

  @override
  String get stagingDisclaimer =>
      'স্টেজিং বাগযুক্ত হতে পারে, অসঙ্গত কর্মক্ষমতা থাকতে পারে, এবং ডেটা হারিয়ে যেতে পারে। শুধুমাত্র পরীক্ষার জন্য ব্যবহার করুন।';

  @override
  String get apiEnvSavedRestartRequired => 'সংরক্ষিত। প্রয়োগ করতে অ্যাপটি বন্ধ এবং পুনরায় খুলুন।';

  @override
  String get shared => 'শেয়ার করা';

  @override
  String get onlyYouCanSeeConversation => 'শুধুমাত্র আপনি এই কথোপকথন দেখতে পারেন';

  @override
  String get anyoneWithLinkCanView => 'লিঙ্ক যার কাছে আছে তারা দেখতে পারেন';

  @override
  String get tasksCleanTodayTitle => 'আজকের কাজগুলি পরিষ্কার করবেন?';

  @override
  String get tasksCleanTodayMessage => 'এটি শুধুমাত্র সময়সীমা অপসারণ করবে';

  @override
  String get tasksOverdue => 'অতিরিক্ত সময়';

  @override
  String get phoneCallsWithOmi => 'Omi দিয়ে ফোন কল';

  @override
  String get phoneCallsSubtitle => 'রিয়েল-টাইম ট্রান্সক্রিপশন সহ কল করুন';

  @override
  String get phoneSetupStep1Title => 'আপনার ফোন নম্বর যাচাই করুন';

  @override
  String get phoneSetupStep1Subtitle => 'আমরা এটি আপনার সংখ্যা নিশ্চিত করতে কল করব';

  @override
  String get phoneSetupStep2Title => 'একটি যাচাইকরণ কোড প্রবেশ করুন';

  @override
  String get phoneSetupStep2Subtitle => 'একটি সংক্ষিপ্ত কোড যা আপনি কলে টাইপ করবেন';

  @override
  String get phoneSetupStep3Title => 'আপনার যোগাযোগ কল শুরু করুন';

  @override
  String get phoneSetupStep3Subtitle => 'নির্মিত লাইভ ট্রান্সক্রিপশন সহ';

  @override
  String get phoneGetStarted => 'শুরু করুন';

  @override
  String get callRecordingConsentDisclaimer => 'কল রেকর্ডিং আপনার এখতিয়ারে সম্মতির প্রয়োজন হতে পারে';

  @override
  String get enterYourNumber => 'আপনার নম্বর প্রবেশ করুন';

  @override
  String get phoneNumberCallerIdHint => 'যাচাই করা হলে, এটি আপনার কলার আইডি হয়ে যায়';

  @override
  String get phoneNumberHint => 'ফোন নম্বর';

  @override
  String get failedToStartVerification => 'যাচাইকরণ শুরু করতে ব্যর্থ';

  @override
  String get phoneContinue => 'অব্যাহত রাখুন';

  @override
  String get verifyYourNumber => 'আপনার নম্বর যাচাই করুন';

  @override
  String get answerTheCallFrom => 'এর থেকে কলের উত্তর দিন';

  @override
  String get onTheCallEnterThisCode => 'কলে, এই কোড প্রবেশ করুন';

  @override
  String get followTheVoiceInstructions => 'ভয়েস নির্দেশাবলী অনুসরণ করুন';

  @override
  String get statusCalling => 'কল করা হচ্ছে...';

  @override
  String get statusCallInProgress => 'চলমান কল';

  @override
  String get statusVerifiedLabel => 'যাচাইকৃত';

  @override
  String get statusCallMissed => 'কল মিস হয়েছে';

  @override
  String get statusTimedOut => 'সময় শেষ';

  @override
  String get phoneTryAgain => 'আবার চেষ্টা করুন';

  @override
  String get phonePageTitle => 'ফোন';

  @override
  String get phoneContactsTab => 'যোগাযোগ';

  @override
  String get phoneKeypadTab => 'কীপ্যাড';

  @override
  String get grantContactsAccess => 'আপনার যোগাযোগে অ্যাক্সেস প্রদান করুন';

  @override
  String get phoneAllow => 'অনুমতি দিন';

  @override
  String get phoneSearchHint => 'অনুসন্ধান';

  @override
  String get phoneNoContactsFound => 'কোনো যোগাযোগ পাওয়া যায়নি';

  @override
  String get phoneEnterNumber => 'নম্বর প্রবেশ করুন';

  @override
  String get failedToStartCall => 'কল শুরু করতে ব্যর্থ';

  @override
  String get callStateConnecting => 'সংযুক্ত করা হচ্ছে...';

  @override
  String get callStateRinging => 'বাজছে...';

  @override
  String get callStateEnded => 'কল শেষ';

  @override
  String get callStateFailed => 'কল ব্যর্থ';

  @override
  String get transcriptPlaceholder => 'ট্রান্সক্রিপ্ট এখানে প্রদর্শিত হবে...';

  @override
  String get phoneUnmute => 'আনমিউট করুন';

  @override
  String get phoneMute => 'মিউট করুন';

  @override
  String get phoneSpeaker => 'স্পিকার';

  @override
  String get phoneEndCall => 'শেষ করুন';

  @override
  String get phoneCallSettingsTitle => 'ফোন কল সেটিংস';

  @override
  String get showPhoneCallButtonTitle => 'ফোন কল বাটন দেখান';

  @override
  String get showPhoneCallButtonDesc => 'হোম স্ক্রিনে ফোন কল বাটন প্রদর্শন করুন';

  @override
  String get yourVerifiedNumbers => 'আপনার যাচাইকৃত নম্বর';

  @override
  String get verifiedNumbersDescription => 'যখন আপনি কাউকে কল করেন, তারা তাদের ফোনে এই নম্বর দেখবেন';

  @override
  String get noVerifiedNumbers => 'কোনো যাচাইকৃত নম্বর নেই';

  @override
  String deletePhoneNumberConfirm(String phoneNumber) {
    return '$phoneNumber মুছবেন?';
  }

  @override
  String get deletePhoneNumberWarning => 'কল করার জন্য আবার যাচাই করা লাগবে';

  @override
  String get phoneDeleteButton => 'মুছুন';

  @override
  String verifiedMinutesAgo(int minutes) {
    return '$minutesমিনিট আগে যাচাইকৃত';
  }

  @override
  String verifiedHoursAgo(int hours) {
    return '$hoursঘন্টা আগে যাচাইকৃত';
  }

  @override
  String verifiedDaysAgo(int days) {
    return '$daysদিন আগে যাচাইকৃত';
  }

  @override
  String verifiedOnDate(String date) {
    return '$date এ যাচাইকৃত';
  }

  @override
  String get verifiedFallback => 'যাচাইকৃত';

  @override
  String get callAlreadyInProgress => 'একটি কল ইতিমধ্যে চলছে';

  @override
  String get failedToGetCallToken => 'কল টোকেন পেতে ব্যর্থ। প্রথমে আপনার ফোন নম্বর যাচাই করুন।';

  @override
  String get failedToInitializeCallService => 'কল সেবা শুরু করতে ব্যর্থ';

  @override
  String get speakerLabelYou => 'আপনি';

  @override
  String get speakerLabelUnknown => 'অজানা';

  @override
  String get showDailyScoreOnHomepage => 'হোমপেজে দৈনিক স্কোর দেখান';

  @override
  String get showTasksOnHomepage => 'হোমপেজে কাজ দেখান';

  @override
  String get phoneCallsUnlimitedOnly => 'Omi এর মাধ্যমে ফোন কল';

  @override
  String get phoneCallsUpsellSubtitle =>
      'Omi এর মাধ্যমে কল করুন এবং রিয়েল-টাইম ট্রান্সক্রিপশন, স্বয়ংক্রিয় সারাংশ এবং আরও অনেক কিছু পান। এক্সক্লুসিভভাবে Unlimited প্ল্যান সাবস্ক্রাইবারদের জন্য উপলব্ধ।';

  @override
  String get phoneCallsUpsellFeature1 => 'প্রতিটি কলের রিয়েল-টাইম ট্রান্সক্রিপশন';

  @override
  String get phoneCallsUpsellFeature2 => 'স্বয়ংক্রিয় কল সারাংশ এবং কর্ম আইটেম';

  @override
  String get phoneCallsUpsellFeature3 => 'প্রাপকরা আপনার বাস্তব নম্বর দেখেন, একটি র্যান্ডম নয়';

  @override
  String get phoneCallsUpsellFeature4 => 'আপনার কল ব্যক্তিগত এবং সুরক্ষিত থাকে';

  @override
  String get phoneCallsUpgradeButton => 'Unlimited এ আপগ্রেড করুন';

  @override
  String get phoneCallsMaybeLater => 'পরে হবে';

  @override
  String get deleteSynced => 'সিঙ্ক করা মুছুন';

  @override
  String get deleteSyncedFiles => 'সিঙ্ক করা রেকর্ডিং মুছুন';

  @override
  String get deleteSyncedFilesMessage =>
      'এই রেকর্ডিংগুলি ইতিমধ্যে আপনার ফোনে সিঙ্ক করা হয়েছে। এটি পূর্বাবাস করা যায় না।';

  @override
  String get syncedFilesDeleted => 'সিঙ্ক করা রেকর্ডিং মুছা হয়েছে';

  @override
  String get deletePending => 'মুলতুবি মুছুন';

  @override
  String get deletePendingFiles => 'মুলতুবি রেকর্ডিং মুছুন';

  @override
  String get deletePendingFilesWarning =>
      'এই রেকর্ডিংগুলি আপনার ফোনে সিঙ্ক করা হয়নি এবং চিরকালের জন্য হারিয়ে যাবে। এটি পূর্বাবাস করা যায় না।';

  @override
  String get pendingFilesDeleted => 'মুলতুবি রেকর্ডিং মুছা হয়েছে';

  @override
  String get deleteAllFiles => 'সমস্ত রেকর্ডিং মুছুন';

  @override
  String get deleteAll => 'সব মুছুন';

  @override
  String get deleteAllFilesWarning =>
      'এটি সিঙ্ক করা এবং মুলতুবি উভয় রেকর্ডিং মুছে ফেলবে। মুলতুবি রেকর্ডিংগুলি সিঙ্ক করা হয়নি এবং চিরকালের জন্য হারিয়ে যাবে। এটি পূর্বাবাস করা যায় না।';

  @override
  String get allFilesDeleted => 'সমস্ত রেকর্ডিং মুছা হয়েছে';

  @override
  String nFiles(int count) {
    return '$count রেকর্ডিং';
  }

  @override
  String get manageStorage => 'স্টোরেজ পরিচালনা করুন';

  @override
  String get safelyBackedUp => 'আপনার ফোনে নিরাপদে ব্যাকআপ করা হয়েছে';

  @override
  String get notYetSynced => 'এখনো আপনার ফোনে সিঙ্ক হয়নি';

  @override
  String get clearAll => 'সব পরিষ্কার করুন';

  @override
  String get phoneKeypad => 'কীপ্যাড';

  @override
  String get phoneHideKeypad => 'কীপ্যাড লুকান';

  @override
  String get fairUsePolicy => 'ন্যায্য ব্যবহার';

  @override
  String get fairUseLoadError => 'ন্যায্য ব্যবহারের স্থিতি লোড করতে পারা যায়নি। আবার চেষ্টা করুন।';

  @override
  String get fairUseStatusNormal => 'আপনার ব্যবহার সাধারণ সীমার মধ্যে রয়েছে।';

  @override
  String get fairUseStageNormal => 'সাধারণ';

  @override
  String get fairUseStageWarning => 'সতর্কতা';

  @override
  String get fairUseStageThrottle => 'সীমাবদ্ধ';

  @override
  String get fairUseStageRestrict => 'প্রতিবন্ধী';

  @override
  String get fairUseSpeechUsage => 'বক্তৃতা ব্যবহার';

  @override
  String get fairUseToday => 'আজ';

  @override
  String get fairUse3Day => '3-দিনের রোলিং';

  @override
  String get fairUseWeekly => 'সাপ্তাহিক রোলিং';

  @override
  String get fairUseAboutTitle => 'ন্যায্য ব্যবহার সম্পর্কে';

  @override
  String get fairUseAboutBody =>
      'Omi ব্যক্তিগত কথোপকথন, সভা এবং লাইভ ইন্টারঅ্যাকশনের জন্য ডিজাইন করা হয়েছে। ব্যবহার সংযোগ সময় দ্বারা নয়, সনাক্ত করা প্রকৃত কথা সময় দ্বারা পরিমাপ করা হয়। যদি ব্যবহার অ-ব্যক্তিগত সামগ্রীর জন্য সাধারণ নিদর্শন উল্লেখযোগ্যভাবে অতিক্রম করে, সমন্বয় প্রযোজ্য হতে পারে।';

  @override
  String fairUseCaseRefCopied(String caseRef) {
    return '$caseRef অনুলিপি করা';
  }

  @override
  String get fairUseDailyTranscription => 'দৈনিক ট্রান্সক্রিপশন';

  @override
  String fairUseBudgetUsed(String used, String limit) {
    return '$usedমিনিট / $limitমিনিট';
  }

  @override
  String get fairUseBudgetExhausted => 'দৈনিক ট্রান্সক্রিপশন সীমা পৌঁছেছে';

  @override
  String fairUseBudgetResetsAt(String time) {
    return '$time এ রিসেট হয়';
  }

  @override
  String get transcriptionPaused => 'রেকর্ডিং, পুনরায় সংযোগ করা হচ্ছে';

  @override
  String get transcriptionPausedReconnecting => 'এখনও রেকর্ডিং করছে — ট্রান্সক্রিপশনে পুনরায় সংযোগ করা হচ্ছে...';

  @override
  String fairUseBannerStatus(String status) {
    return 'ন্যায্য ব্যবহার: $status';
  }

  @override
  String get improveConnectionTitle => 'সংযোগ উন্নত করুন';

  @override
  String get improveConnectionContent =>
      'আমরা উন্নত করেছি কীভাবে Omi আপনার ডিভাইসে সংযুক্ত থাকে। এটি সক্রিয় করতে, ডিভাইস তথ্য পৃষ্ঠায় যান, \"ডিভাইস সংযোগ বিচ্ছিন্ন করুন\" ট্যাপ করুন, তারপর আপনার ডিভাইস পুনরায় পেয়ার করুন।';

  @override
  String get improveConnectionAction => 'বুঝেছি';

  @override
  String clockSkewWarning(int minutes) {
    return 'আপনার ডিভাইস ঘড়ি ~$minutes মিনিট বন্ধ আছে। আপনার তারিখ এবং সময় সেটিংস চেক করুন।';
  }

  @override
  String get omisStorage => 'Omi এর স্টোরেজ';

  @override
  String get phoneStorage => 'ফোন স্টোরেজ';

  @override
  String get cloudStorage => 'ক্লাউড স্টোরেজ';

  @override
  String get howSyncingWorks => 'সিঙ্ক কীভাবে কাজ করে';

  @override
  String get noSyncedRecordings => 'এখনো কোনো সিঙ্ক করা রেকর্ডিং নেই';

  @override
  String get recordingsSyncAutomatically => 'রেকর্ডিংগুলি স্বয়ংক্রিয়ভাবে সিঙ্ক হয় — কোনো পদক্ষেপের প্রয়োজন নেই।';

  @override
  String get filesDownloadedUploadedNextTime => 'ইতিমধ্যে ডাউনলোড করা ফাইলগুলি পরবর্তীবার আপলোড করা হবে।';

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
  String get tapToView => 'দেখতে ট্যাপ করুন';

  @override
  String get syncFailed => 'সিঙ্ক ব্যর্থ';

  @override
  String get keepSyncing => 'সিঙ্ক করা চালিয়ে যান';

  @override
  String get cancelSyncQuestion => 'সিঙ্ক বাতিল করবেন?';

  @override
  String get omisStorageDesc =>
      'যখন আপনার Omi আপনার ফোনে সংযুক্ত নয়, এটি তার নির্মিত মেমরিতে অডিও স্থানীয়ভাবে সংরক্ষণ করে। আপনি কখনও একটি রেকর্ডিং হারাবেন না।';

  @override
  String get phoneStorageDesc =>
      'যখন Omi পুনরায় সংযুক্ত হয়, রেকর্ডিংগুলি স্বয়ংক্রিয়ভাবে আপনার ফোনে স্থানান্তরিত হয় আপলোড করার আগে অস্থায়ী ধারণ এলাকা হিসাবে।';

  @override
  String get cloudStorageDesc =>
      'একবার আপলোড করা হয়, আপনার রেকর্ডিংগুলি প্রক্রিয়াজাত এবং ট্রান্সক্রাইব করা হয়। কথোপকথনগুলি এক মিনিটের মধ্যে উপলব্ধ থাকবে।';

  @override
  String get tipKeepPhoneNearby => 'দ্রুত সিঙ্কিংয়ের জন্য আপনার ফোন কাছাকাছি রাখুন';

  @override
  String get tipStableInternet => 'স্থিতিশীল ইন্টারনেট ক্লাউড আপলোড গতি বাড়ায়';

  @override
  String get tipAutoSync => 'রেকর্ডিংগুলি স্বয়ংক্রিয়ভাবে সিঙ্ক হয়';

  @override
  String get storageSection => 'স্টোরেজ';

  @override
  String get permissions => 'অনুমতি';

  @override
  String get permissionEnabled => 'সক্ষম';

  @override
  String get permissionEnable => 'সক্ষম করুন';

  @override
  String get permissionsPageDescription =>
      'এই অনুমতিগুলি Omi কীভাবে কাজ করে তার মূল। তারা বিজ্ঞপ্তি, অবস্থান-ভিত্তিক অভিজ্ঞতা এবং অডিও ক্যাপচার মত মূল বৈশিষ্ট্য সক্ষম।';

  @override
  String get permissionsRequiredDescription =>
      'Omi সঠিকভাবে কাজ করার জন্য কয়েকটি অনুমতি প্রয়োজন। অব্যাহত রাখতে অনুগ্রহ করে তাদের প্রদান করুন।';

  @override
  String get permissionsSetupTitle => 'সেরা অভিজ্ঞতা পান';

  @override
  String get permissionsSetupDescription => 'Omi এর জাদু কাজ করার জন্য কয়েকটি অনুমতি সক্ষম করুন।';

  @override
  String get permissionsChangeAnytime => 'আপনি যেকোনো সময় এই সেটিংস > অনুমতিতে পরিবর্তন করতে পারেন';

  @override
  String get location => 'অবস্থান';

  @override
  String get microphone => 'মাইক্রোফোন';

  @override
  String get whyAreYouCanceling => 'আপনি কেন বাতিল করছেন?';

  @override
  String get cancelReasonSubtitle => 'আপনি কেন যাচ্ছেন তা বলতে পারেন?';

  @override
  String get cancelReasonTooExpensive => 'খুব ব্যয়বহুল';

  @override
  String get cancelReasonNotUsing => 'এটি যথেষ্ট ব্যবহার করছে না';

  @override
  String get cancelReasonMissingFeatures => 'বৈশিষ্ট্য নিখোঁজ';

  @override
  String get cancelReasonAudioQuality => 'অডিও/ট্রান্সক্রিপশন গুণমান';

  @override
  String get cancelReasonBatteryDrain => 'ব্যাটারি নিকাশী সম্পর্কে উদ্বিগ্ন';

  @override
  String get cancelReasonFoundAlternative => 'একটি বিকল্প খুঁজে পেয়েছি';

  @override
  String get cancelReasonOther => 'অন্যান্য';

  @override
  String get tellUsMore => 'আরও বলুন (ঐচ্ছিক)';

  @override
  String get cancelReasonDetailHint => 'আমরা যেকোনো প্রতিক্রিয়া প্রশংসা করি...';

  @override
  String get justAMoment => 'শুধু একটি মুহূর্ত, অনুগ্রহ করে';

  @override
  String get cancelConsequencesSubtitle =>
      'আমরা অত্যন্ত সুপারিশ করি বাতিল করার পরিবর্তে আপনার অন্যান্য বিকল্প অন্বেষণ করুন।';

  @override
  String cancelBillingPeriodInfo(String date) {
    return 'আপনার পরিকল্পনা $date পর্যন্ত সক্রিয় থাকবে। তার পরে, আপনি সীমিত বৈশিষ্ট্য সহ বিনামূল্যে সংস্করণে সরিয়ে দেওয়া হবেন।';
  }

  @override
  String get ifYouCancel => 'যদি আপনি বাতিল করেন:';

  @override
  String get cancelConsequenceNoAccess => 'আপনার বিলিং সময়কাল শেষে আর সীমাহীন অ্যাক্সেস নেই।';

  @override
  String get cancelConsequenceBattery => '7x আরও ব্যাটারি ব্যবহার (অন-ডিভাইস প্রসেসিং)';

  @override
  String get cancelConsequenceQuality => '30% কম ট্রান্সক্রিপশন গুণমান (অন-ডিভাইস মডেল)';

  @override
  String get cancelConsequenceDelay => '5-7 সেকেন্ড প্রক্রিয়াজাতকরণ বিলম্ব (অন-ডিভাইস মডেল)';

  @override
  String get cancelConsequenceSpeakers => 'স্পিকার সনাক্ত করতে পারে না।';

  @override
  String get confirmAndCancel => 'নিশ্চিত করুন এবং বাতিল করুন';

  @override
  String get cancelConsequencePhoneCalls => 'কোনো রিয়েল-টাইম ফোন কল ট্রান্সক্রিপশন নেই';

  @override
  String get feedbackTitleTooExpensive => 'আপনার জন্য কী মূল্য কাজ করবে?';

  @override
  String get feedbackTitleMissingFeatures => 'আপনি কী বৈশিষ্ট্য মিস করছেন?';

  @override
  String get feedbackTitleAudioQuality => 'আপনি কী সমস্যার সম্মুখীন হয়েছেন?';

  @override
  String get feedbackTitleBatteryDrain => 'ব্যাটারি সমস্যা সম্পর্কে বলুন';

  @override
  String get feedbackTitleFoundAlternative => 'আপনি কী তে স্যুইচ করছেন?';

  @override
  String get feedbackTitleNotUsing => 'আপনি Omi আরও কী ব্যবহার করবেন?';

  @override
  String get feedbackSubtitleTooExpensive => 'আপনার প্রতিক্রিয়া আমাদের সঠিক ভারসাম্য খুঁজে পেতে সাহায্য করে।';

  @override
  String get feedbackSubtitleMissingFeatures => 'আমরা সর্বদা নির্মাণ করছি — এটি আমাদের অগ্রাধিকার দিতে সাহায্য করে।';

  @override
  String get feedbackSubtitleAudioQuality => 'আমরা বুঝতে চাই কী ভুল হয়েছিল।';

  @override
  String get feedbackSubtitleBatteryDrain => 'এটি আমাদের হার্ডওয়্যার টিমকে উন্নতি করতে সাহায্য করে।';

  @override
  String get feedbackSubtitleFoundAlternative => 'আমরা শিখতে চাই কী আপনার চোখ ধরেছে।';

  @override
  String get feedbackSubtitleNotUsing => 'আমরা Omi আপনার জন্য আরও দরকারী করতে চাই।';

  @override
  String get deviceDiagnostics => 'ডিভাইস ডায়াগনস্টিক্স';

  @override
  String get signalStrength => 'সংকেত শক্তি';

  @override
  String get connectionUptime => 'আপটাইম';

  @override
  String get reconnections => 'পুনরায় সংযোগ';

  @override
  String get disconnectHistory => 'সংযোগ বিচ্ছিন্ন ইতিহাস';

  @override
  String get noDisconnectsRecorded => 'কোনো সংযোগ বিচ্ছিন্ন রেকর্ড করা হয়নি';

  @override
  String get diagnostics => 'ডায়াগনস্টিক্স';

  @override
  String get waitingForData => 'ডেটার জন্য অপেক্ষা করা হচ্ছে...';

  @override
  String get liveRssiOverTime => 'সময়ের উপর লাইভ RSSI';

  @override
  String get noRssiDataYet => 'এখনো কোনো RSSI ডেটা নেই';

  @override
  String get collectingData => 'ডেটা সংগ্রহ করা হচ্ছে...';

  @override
  String get cleanDisconnect => 'পরিষ্কার সংযোগ বিচ্ছিন্ন';

  @override
  String get connectionTimeout => 'সংযোগ সময় শেষ';

  @override
  String get remoteDeviceTerminated => 'দূরবর্তী ডিভাইস সমাপ্ত';

  @override
  String get pairedToAnotherPhone => 'অন্য ফোনে পেয়ার করা হয়েছে';

  @override
  String get linkKeyMismatch => 'লিঙ্ক কী অসামঞ্জস্য';

  @override
  String get connectionFailed => 'সংযোগ ব্যর্থ';

  @override
  String get appClosed => 'অ্যাপ বন্ধ';

  @override
  String get manualDisconnect => 'ম্যানুয়াল সংযোগ বিচ্ছিন্ন';

  @override
  String lastNEvents(int count) {
    return 'শেষ $count ইভেন্ট';
  }

  @override
  String get signal => 'সংকেত';

  @override
  String get battery => 'ব্যাটারি';

  @override
  String get excellent => 'চমৎকার';

  @override
  String get good => 'ভালো';

  @override
  String get fair => 'ন্যায্য';

  @override
  String get weak => 'দুর্বল';

  @override
  String gattError(String code) {
    return 'GATT ত্রুটি ($code)';
  }

  @override
  String get batteryHistory => 'ব্যাটারি';

  @override
  String get noBatteryDataYet => 'এখনও কোনো ব্যাটারি ডেটা নেই';

  @override
  String get day => 'দিন';

  @override
  String get week => 'সপ্তাহ';

  @override
  String get rollbackToStableFirmware => 'স্থিতিশীল ফার্মওয়্যারে রোলব্যাক করুন';

  @override
  String get rollbackConfirmTitle => 'ফার্মওয়্যার রোলব্যাক করবেন?';

  @override
  String rollbackConfirmMessage(String version) {
    return 'এটি আপনার বর্তমান ফার্মওয়্যার সর্বশেষ স্থিতিশীল সংস্করণ ($version) দিয়ে প্রতিস্থাপন করবে। আপডেটের পরে আপনার ডিভাইস পুনরায় চালু হবে।';
  }

  @override
  String get stableFirmware => 'স্থিতিশীল ফার্মওয়্যার';

  @override
  String get fetchingStableFirmware => 'সর্বশেষ স্থিতিশীল ফার্মওয়্যার আনছি...';

  @override
  String get noStableFirmwareFound => 'আপনার ডিভাইসের জন্য একটি স্থিতিশীল ফার্মওয়্যার সংস্করণ খুঁজে পেতে পারা যায়নি।';

  @override
  String get installStableFirmware => 'স্থিতিশীল ফার্মওয়্যার ইনস্টল করুন';

  @override
  String get alreadyOnStableFirmware => 'আপনি ইতিমধ্যে সর্বশেষ স্থিতিশীল সংস্করণে রয়েছেন।';

  @override
  String audioSavedLocally(String duration) {
    return '$duration অডিও স্থানীয়ভাবে সংরক্ষিত';
  }

  @override
  String get willSyncAutomatically => 'স্বয়ংক্রিয়ভাবে সিঙ্ক হবে';

  @override
  String get enableLocationTitle => 'অবস্থান সক্ষম করুন';

  @override
  String get enableLocationDescription => 'নিকটবর্তী Bluetooth ডিভাইস খুঁজতে অবস্থান অনুমতি প্রয়োজন।';

  @override
  String get voiceRecordingFound => 'রেকর্ডিং পাওয়া গেছে';

  @override
  String get transcriptionConnecting => 'ট্রান্সক্রিপশন সংযুক্ত করা হচ্ছে...';

  @override
  String get transcriptionReconnecting => 'ট্রান্সক্রিপশন পুনরায় সংযোগ করা হচ্ছে...';

  @override
  String get transcriptionUnavailable => 'ট্রান্সক্রিপশন অনুপলব্ধ';

  @override
  String get audioOutput => 'অডিও আউটপুট';

  @override
  String get firmwareWarningTitle => 'গুরুত্বপূর্ণ: আপডেটের আগে পড়ুন';

  @override
  String get firmwareFormatWarning =>
      'এই ফার্মওয়্যার SD কার্ড ফরম্যাট করবে। আপগ্রেড করার আগে দয়া করে নিশ্চিত করুন যে সমস্ত অফলাইন ডেটা সিঙ্ক হয়েছে।\n\nএই সংস্করণ ইনস্টল করার পর যদি লাল আলো জ্বলতে দেখেন, চিন্তা করবেন না। শুধু ডিভাইসটি অ্যাপের সাথে সংযুক্ত করুন এবং এটি নীল হয়ে যাওয়া উচিত। লাল আলো মানে ডিভাইসের ঘড়ি এখনও সিঙ্ক হয়নি।';

  @override
  String get continueAnyway => 'চালিয়ে যান';

  @override
  String get tasksClearCompleted => 'সম্পন্নগুলো মুছুন';

  @override
  String get tasksSelectAll => 'সব নির্বাচন করুন';

  @override
  String tasksDeleteSelected(int count) {
    return '$countটি কাজ মুছুন';
  }

  @override
  String get tasksMarkComplete => 'সম্পন্ন হিসেবে চিহ্নিত';

  @override
  String get appleHealthManageNote =>
      'Omi অ্যাপলের HealthKit ফ্রেমওয়ার্কের মাধ্যমে Apple Health-এ অ্যাক্সেস করে। আপনি যেকোনো সময় iOS সেটিংস থেকে অ্যাক্সেস প্রত্যাহার করতে পারেন।';

  @override
  String get appleHealthConnectCta => 'Apple Health-এ সংযুক্ত করুন';

  @override
  String get appleHealthDisconnectCta => 'Apple Health সংযোগ বিচ্ছিন্ন করুন';

  @override
  String get appleHealthConnectedBadge => 'সংযুক্ত';

  @override
  String get appleHealthFeatureChatTitle => 'আপনার স্বাস্থ্য নিয়ে চ্যাট করুন';

  @override
  String get appleHealthFeatureChatDesc => 'Omi-কে আপনার পদক্ষেপ, ঘুম, হৃদস্পন্দন ও ব্যায়াম সম্পর্কে জিজ্ঞাসা করুন।';

  @override
  String get appleHealthFeatureReadOnlyTitle => 'শুধুমাত্র পড়ার অ্যাক্সেস';

  @override
  String get appleHealthFeatureReadOnlyDesc => 'Omi কখনই Apple Health-এ লেখে না বা আপনার ডেটা পরিবর্তন করে না।';

  @override
  String get appleHealthFeatureSecureTitle => 'সুরক্ষিত সিঙ্ক';

  @override
  String get appleHealthFeatureSecureDesc => 'আপনার Apple Health ডেটা ব্যক্তিগতভাবে আপনার Omi অ্যাকাউন্টে সিঙ্ক হয়।';

  @override
  String get appleHealthDeniedTitle => 'Apple Health অ্যাক্সেস অস্বীকৃত';

  @override
  String get appleHealthDeniedBody =>
      'Omi-র আপনার Apple Health ডেটা পড়ার অনুমতি নেই। iOS সেটিংস → Privacy & Security → Health → Omi-তে এটি সক্ষম করুন।';

  @override
  String get deleteFlowReasonTitle => 'আপনি কেন চলে যাচ্ছেন?';

  @override
  String get deleteFlowReasonSubtitle => 'আপনার মতামত আমাদের সবার জন্য Omi-কে উন্নত করতে সাহায্য করে।';

  @override
  String get deleteReasonPrivacy => 'গোপনীয়তা সংক্রান্ত উদ্বেগ';

  @override
  String get deleteReasonNotUsing => 'যথেষ্ট ব্যবহার করছি না';

  @override
  String get deleteReasonMissingFeatures => 'আমার প্রয়োজনীয় ফিচার নেই';

  @override
  String get deleteReasonTechnicalIssues => 'অনেক প্রযুক্তিগত সমস্যা';

  @override
  String get deleteReasonFoundAlternative => 'অন্য কিছু ব্যবহার করছি';

  @override
  String get deleteReasonTakingBreak => 'শুধু একটু বিরতি নিচ্ছি';

  @override
  String get deleteReasonOther => 'অন্যান্য';

  @override
  String get deleteFlowFeedbackTitle => 'আরও বলুন';

  @override
  String get deleteFlowFeedbackSubtitle => 'কী হলে Omi আপনার জন্য কাজ করত?';

  @override
  String get deleteFlowFeedbackHint => 'ঐচ্ছিক — আপনার চিন্তা আমাদের আরও ভাল পণ্য তৈরি করতে সাহায্য করে।';

  @override
  String get deleteFlowConfirmTitle => 'এটি স্থায়ী';

  @override
  String get deleteFlowConfirmSubtitle => 'একবার অ্যাকাউন্ট মুছে ফেললে, এটি পুনরুদ্ধার করার কোনো উপায় নেই।';

  @override
  String get deleteConsequenceSubscription => 'যেকোনো সক্রিয় সাবস্ক্রিপশন বাতিল হবে।';

  @override
  String get deleteConsequenceNoRecovery => 'আপনার অ্যাকাউন্ট পুনরুদ্ধার করা যাবে না — সাপোর্টও পারবে না।';

  @override
  String get deleteTypeToConfirm => 'নিশ্চিত করতে DELETE টাইপ করুন';

  @override
  String get deleteConfirmationWord => 'DELETE';

  @override
  String get deleteAccountPermanently => 'অ্যাকাউন্ট স্থায়ীভাবে মুছুন';

  @override
  String get keepMyAccount => 'আমার অ্যাকাউন্ট রাখুন';

  @override
  String get deleteAccountFailed => 'আপনার অ্যাকাউন্ট মুছে ফেলা যায়নি। আবার চেষ্টা করুন।';

  @override
  String get planUpdate => 'প্ল্যান আপডেট';

  @override
  String get planDeprecationMessage =>
      'আপনার Unlimited প্ল্যান বন্ধ হচ্ছে। Operator প্ল্যানে স্যুইচ করুন — একই দুর্দান্ত ফিচার \$49/মাসে। আপনার বর্তমান প্ল্যান এর মধ্যে কাজ করতে থাকবে।';

  @override
  String get upgradeYourPlan => 'আপনার প্ল্যান আপগ্রেড করুন';

  @override
  String get youAreOnAPaidPlan => 'আপনি একটি পেইড প্ল্যানে আছেন।';

  @override
  String get chatTitle => 'চ্যাট';

  @override
  String get chatMessages => 'বার্তা';

  @override
  String get unlimitedChatThisMonth => 'এই মাসে সীমাহীন চ্যাট বার্তা';

  @override
  String chatUsedOfLimitCompute(String used, String limit) {
    return '$used / $limit কম্পিউট বাজেট ব্যবহৃত';
  }

  @override
  String chatUsedOfLimitMessages(String used, String limit) {
    return 'এই মাসে $used / $limit বার্তা ব্যবহৃত';
  }

  @override
  String chatUsageProgress(String used, String limit) {
    return '$used / $limit ব্যবহৃত';
  }

  @override
  String get chatLimitReachedUpgrade => 'চ্যাট সীমা পৌঁছেছে। আরও বার্তার জন্য আপগ্রেড করুন।';

  @override
  String get chatLimitReachedTitle => 'চ্যাট সীমা পৌঁছেছে';

  @override
  String chatUsageDescription(String used, String limitDisplay, String plan) {
    return '$plan প্ল্যানে আপনি $limitDisplay এর মধ্যে $used ব্যবহার করেছেন।';
  }

  @override
  String resetsInDays(int count) {
    return '$count দিনে রিসেট হবে';
  }

  @override
  String resetsInHours(int count) {
    return '$count ঘণ্টায় রিসেট হবে';
  }

  @override
  String get resetsSoon => 'শীঘ্রই রিসেট হবে';

  @override
  String get upgradePlan => 'প্ল্যান আপগ্রেড করুন';

  @override
  String get billingMonthly => 'মাসিক';

  @override
  String get billingYearly => 'বার্ষিক';

  @override
  String get savePercent => '~17% সাশ্রয়';

  @override
  String get popular => 'জনপ্রিয়';

  @override
  String get currentPlan => 'বর্তমান';

  @override
  String neoSubtitle(int count) {
    return 'মাসে $countটি প্রশ্ন';
  }

  @override
  String operatorSubtitle(int count) {
    return 'মাসে $countটি প্রশ্ন';
  }

  @override
  String get architectSubtitle => 'পাওয়ার-ইউজার AI — হাজার হাজার চ্যাট + এজেন্টিক অটোমেশন';

  @override
  String chatUsageCost(String used, String limit) {
    return 'চ্যাট: \$$used / \$$limit এই মাসে ব্যবহৃত';
  }

  @override
  String chatUsageCostNoLimit(String used) {
    return 'চ্যাট: \$$used এই মাসে ব্যবহৃত';
  }

  @override
  String chatUsageMessages(String used, String limit) {
    return 'চ্যাট: $used / $limit বার্তা এই মাসে';
  }

  @override
  String chatUsageMessagesNoLimit(String used) {
    return 'চ্যাট: $used বার্তা এই মাসে';
  }

  @override
  String get chatQuotaSubtitle => 'AI chat messages used with Omi this month.';

  @override
  String get chatQuotaExceededReply =>
      'আপনি আপনার মাসিক সীমায় পৌঁছেছেন। বিনা সীমাবদ্ধতায় Omi-এর সাথে চ্যাট চালিয়ে যেতে আপগ্রেড করুন।';

  @override
  String get voiceResponseAudio => 'Omi-র উত্তর জোরে পড়ুন';

  @override
  String get voiceResponseMode => 'ভয়েস প্রতিক্রিয়া';

  @override
  String get voiceResponseModeTitle => 'কখন উত্তর বলা হবে';

  @override
  String get voiceResponseOff => 'বন্ধ';

  @override
  String get voiceResponseHeadphonesOnly => 'শুধু হেডফোন';

  @override
  String get voiceResponseAlways => 'সর্বদা';

  @override
  String get agreeAndContinue => 'সম্মত হই এবং চালিয়ে যান';

  @override
  String get startVoiceRecording => 'ভয়েস রেকর্ডিং শুরু করুন';

  @override
  String get startCallRecording => 'কল রেকর্ডিং শুরু করুন';

  @override
  String get mindMap => 'Mind Map';

  @override
  String get voiceMode => 'ভয়েস মোড';

  @override
  String get quickActionAskOmi => 'Omi কে যেকোনো কিছু জিজ্ঞেস করুন';

  @override
  String get record => 'রেকর্ড';

  @override
  String get stop => 'থামান';

  @override
  String get recordWithPhoneMic => 'ফোনের মাইক্রোফোন দিয়ে রেকর্ড করুন';

  @override
  String get recordWithPhoneMicSubtitle => 'আপনার চারপাশের অডিও ক্যাপচার করুন';

  @override
  String get phoneCall => 'ফোন কল';

  @override
  String get phoneCallSubtitle => 'লাইভ ট্রান্সক্রিপশন সহ কল রেকর্ড করুন';

  @override
  String get searchActionItems => 'অ্যাকশন আইটেম অনুসন্ধান';

  @override
  String get selectActionItems => 'একাধিক নির্বাচন';

  @override
  String chooseExportDestination(int count) {
    return '$countটি আইটেম রপ্তানি করুন…';
  }

  @override
  String get bulkExportInProgress => 'রপ্তানি হচ্ছে…';

  @override
  String bulkExportSuccess(int count, String platform) {
    return '$countটি $platform-এ রপ্তানি হয়েছে';
  }

  @override
  String bulkExportPartial(int success, int total, String platform) {
    return '$total-এর মধ্যে $successটি $platform-এ রপ্তানি হয়েছে';
  }

  @override
  String get showCompletedTasks => 'সম্পন্ন দেখান';

  @override
  String get hideCompletedTasks => 'সম্পন্ন লুকান';

  @override
  String get selectAllTasksMenu => 'সমস্ত নির্বাচন';

  @override
  String get connectTaskAppToExport => 'রপ্তানি করতে সেটিংসে একটি টাস্ক অ্যাপ সংযুক্ত করুন';

  @override
  String get connectAction => 'সংযুক্ত করুন';

  @override
  String get deselectAllTasksMenu => 'সমস্ত নির্বাচন বাতিল';
}
