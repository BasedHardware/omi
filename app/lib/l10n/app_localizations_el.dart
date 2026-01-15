// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Modern Greek (`el`).
class AppLocalizationsEl extends AppLocalizations {
  AppLocalizationsEl([String locale = 'el']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'Συνομιλία';

  @override
  String get transcriptTab => 'Απομαγνητοφώνηση';

  @override
  String get actionItemsTab => 'Ενέργειες';

  @override
  String get deleteConversationTitle => 'Διαγραφή Συνομιλίας;';

  @override
  String get deleteConversationMessage =>
      'Είστε βέβαιοι ότι θέλετε να διαγράψετε αυτή τη συνομιλία; Αυτή η ενέργεια δεν μπορεί να αναιρεθεί.';

  @override
  String get confirm => 'Επιβεβαίωση';

  @override
  String get cancel => 'Ακύρωση';

  @override
  String get ok => 'Εντάξει';

  @override
  String get delete => 'Διαγραφή';

  @override
  String get add => 'Προσθήκη';

  @override
  String get update => 'Ενημέρωση';

  @override
  String get save => 'Αποθήκευση';

  @override
  String get edit => 'Επεξεργασία';

  @override
  String get close => 'Κλείσιμο';

  @override
  String get clear => 'Εκκαθάριση';

  @override
  String get copyTranscript => 'Αντιγραφή Απομαγνητοφώνησης';

  @override
  String get copySummary => 'Αντιγραφή Περίληψης';

  @override
  String get testPrompt => 'Δοκιμή Εντολής';

  @override
  String get reprocessConversation => 'Επανεπεξεργασία Συνομιλίας';

  @override
  String get deleteConversation => 'Διαγραφή Συνομιλίας';

  @override
  String get contentCopied => 'Το περιεχόμενο αντιγράφηκε στο πρόχειρο';

  @override
  String get failedToUpdateStarred => 'Αποτυχία ενημέρωσης της κατάστασης αγαπημένων.';

  @override
  String get conversationUrlNotShared => 'Δεν ήταν δυνατή η κοινοποίηση του URL της συνομιλίας.';

  @override
  String get errorProcessingConversation =>
      'Σφάλμα κατά την επεξεργασία της συνομιλίας. Παρακαλώ δοκιμάστε ξανά αργότερα.';

  @override
  String get noInternetConnection => 'Παρακαλώ ελέγξτε τη σύνδεσή σας στο διαδίκτυο και δοκιμάστε ξανά.';

  @override
  String get unableToDeleteConversation => 'Αδυναμία Διαγραφής Συνομιλίας';

  @override
  String get somethingWentWrong => 'Κάτι πήγε στραβά! Παρακαλώ δοκιμάστε ξανά αργότερα.';

  @override
  String get copyErrorMessage => 'Αντιγραφή μηνύματος σφάλματος';

  @override
  String get errorCopied => 'Το μήνυμα σφάλματος αντιγράφηκε στο πρόχειρο';

  @override
  String get remaining => 'Υπολειπόμενα';

  @override
  String get loading => 'Φόρτωση...';

  @override
  String get loadingDuration => 'Φόρτωση διάρκειας...';

  @override
  String secondsCount(int count) {
    return '$count δευτερόλεπτα';
  }

  @override
  String get people => 'Άτομα';

  @override
  String get addNewPerson => 'Προσθήκη Νέου Ατόμου';

  @override
  String get editPerson => 'Επεξεργασία Ατόμου';

  @override
  String get createPersonHint => 'Δημιουργήστε ένα νέο άτομο και εκπαιδεύστε το Omi να αναγνωρίζει και την ομιλία του!';

  @override
  String get speechProfile => 'Προφίλ Ομιλίας';

  @override
  String sampleNumber(int number) {
    return 'Δείγμα $number';
  }

  @override
  String get settings => 'Ρυθμίσεις';

  @override
  String get language => 'Γλώσσα';

  @override
  String get selectLanguage => 'Επιλογή Γλώσσας';

  @override
  String get deleting => 'Διαγραφή...';

  @override
  String get pleaseCompleteAuthentication =>
      'Παρακαλώ ολοκληρώστε την πιστοποίηση στο πρόγραμμα περιήγησής σας. Μόλις ολοκληρωθεί, επιστρέψτε στην εφαρμογή.';

  @override
  String get failedToStartAuthentication => 'Αποτυχία έναρξης πιστοποίησης';

  @override
  String get importStarted => 'Η εισαγωγή ξεκίνησε! Θα ειδοποιηθείτε όταν ολοκληρωθεί.';

  @override
  String get failedToStartImport => 'Αποτυχία έναρξης εισαγωγής. Παρακαλώ δοκιμάστε ξανά.';

  @override
  String get couldNotAccessFile => 'Δεν ήταν δυνατή η πρόσβαση στο επιλεγμένο αρχείο';

  @override
  String get askOmi => 'Ρωτήστε το Omi';

  @override
  String get done => 'Τέλος';

  @override
  String get disconnected => 'Αποσυνδέθηκε';

  @override
  String get searching => 'Αναζήτηση';

  @override
  String get connectDevice => 'Σύνδεση Συσκευής';

  @override
  String get monthlyLimitReached => 'Φτάσατε το μηνιαίο όριό σας.';

  @override
  String get checkUsage => 'Έλεγχος Χρήσης';

  @override
  String get syncingRecordings => 'Συγχρονισμός ηχογραφήσεων';

  @override
  String get recordingsToSync => 'Ηχογραφήσεις για συγχρονισμό';

  @override
  String get allCaughtUp => 'Όλα ενημερωμένα';

  @override
  String get sync => 'Συγχρονισμός';

  @override
  String get pendantUpToDate => 'Το περιδέραιο είναι ενημερωμένο';

  @override
  String get allRecordingsSynced => 'Όλες οι ηχογραφήσεις συγχρονίστηκαν';

  @override
  String get syncingInProgress => 'Συγχρονισμός σε εξέλιξη';

  @override
  String get readyToSync => 'Έτοιμο για συγχρονισμό';

  @override
  String get tapSyncToStart => 'Πατήστε Συγχρονισμός για έναρξη';

  @override
  String get pendantNotConnected => 'Το περιδέραιο δεν είναι συνδεδεμένο. Συνδεθείτε για συγχρονισμό.';

  @override
  String get everythingSynced => 'Όλα είναι ήδη συγχρονισμένα.';

  @override
  String get recordingsNotSynced => 'Έχετε ηχογραφήσεις που δεν έχουν συγχρονιστεί ακόμα.';

  @override
  String get syncingBackground => 'Θα συνεχίσουμε να συγχρονίζουμε τις ηχογραφήσεις σας στο παρασκήνιο.';

  @override
  String get noConversationsYet => 'Δεν υπάρχουν συνομιλίες ακόμα.';

  @override
  String get noStarredConversations => 'Δεν υπάρχουν αγαπημένες συνομιλίες ακόμα.';

  @override
  String get starConversationHint =>
      'Για να προσθέσετε μια συνομιλία στα αγαπημένα, ανοίξτε τη και πατήστε το εικονίδιο αστεριού στην κεφαλίδα.';

  @override
  String get searchConversations => 'Αναζήτηση Συνομιλιών';

  @override
  String selectedCount(int count, Object s) {
    return '$count επιλεγμένα';
  }

  @override
  String get merge => 'Συγχώνευση';

  @override
  String get mergeConversations => 'Συγχώνευση Συνομιλιών';

  @override
  String mergeConversationsMessage(int count) {
    return 'Αυτό θα συνδυάσει $count συνομιλίες σε μία. Όλο το περιεχόμενο θα συγχωνευτεί και θα αναδημιουργηθεί.';
  }

  @override
  String get mergingInBackground => 'Συγχώνευση στο παρασκήνιο. Μπορεί να πάρει λίγο χρόνο.';

  @override
  String get failedToStartMerge => 'Αποτυχία έναρξης συγχώνευσης';

  @override
  String get askAnything => 'Ρωτήστε οτιδήποτε';

  @override
  String get noMessagesYet => 'Δεν υπάρχουν μηνύματα ακόμα!\nΓιατί δεν ξεκινάτε μια συνομιλία;';

  @override
  String get deletingMessages => 'Διαγραφή των μηνυμάτων σας από τη μνήμη του Omi...';

  @override
  String get messageCopied => 'Το μήνυμα αντιγράφηκε στο πρόχειρο.';

  @override
  String get cannotReportOwnMessage => 'Δεν μπορείτε να αναφέρετε τα δικά σας μηνύματα.';

  @override
  String get reportMessage => 'Αναφορά Μηνύματος';

  @override
  String get reportMessageConfirm => 'Είστε βέβαιοι ότι θέλετε να αναφέρετε αυτό το μήνυμα;';

  @override
  String get messageReported => 'Το μήνυμα αναφέρθηκε επιτυχώς.';

  @override
  String get thankYouFeedback => 'Ευχαριστούμε για τα σχόλιά σας!';

  @override
  String get clearChat => 'Εκκαθάριση Συνομιλίας;';

  @override
  String get clearChatConfirm =>
      'Είστε βέβαιοι ότι θέλετε να εκκαθαρίσετε τη συνομιλία; Αυτή η ενέργεια δεν μπορεί να αναιρεθεί.';

  @override
  String get maxFilesLimit => 'Μπορείτε να ανεβάσετε μόνο 4 αρχεία τη φορά';

  @override
  String get chatWithOmi => 'Συνομιλία με το Omi';

  @override
  String get apps => 'Εφαρμογές';

  @override
  String get noAppsFound => 'Δεν βρέθηκαν εφαρμογές';

  @override
  String get tryAdjustingSearch => 'Δοκιμάστε να προσαρμόσετε την αναζήτηση ή τα φίλτρα σας';

  @override
  String get createYourOwnApp => 'Δημιουργήστε τη Δική σας Εφαρμογή';

  @override
  String get buildAndShareApp => 'Δημιουργήστε και μοιραστείτε την προσαρμοσμένη εφαρμογή σας';

  @override
  String get searchApps => 'Αναζήτηση 1500+ Εφαρμογών';

  @override
  String get myApps => 'Οι Εφαρμογές μου';

  @override
  String get installedApps => 'Εγκατεστημένες Εφαρμογές';

  @override
  String get unableToFetchApps =>
      'Αδυναμία λήψης εφαρμογών :(\n\nΠαρακαλώ ελέγξτε τη σύνδεσή σας στο διαδίκτυο και δοκιμάστε ξανά.';

  @override
  String get aboutOmi => 'Σχετικά με το Omi';

  @override
  String get privacyPolicy => 'Πολιτική Απορρήτου';

  @override
  String get visitWebsite => 'Επισκεφτείτε τον Ιστότοπο';

  @override
  String get helpOrInquiries => 'Βοήθεια ή Ερωτήσεις;';

  @override
  String get joinCommunity => 'Γίνετε μέλος της κοινότητας!';

  @override
  String get membersAndCounting => '8000+ μέλη και συνεχίζουν.';

  @override
  String get deleteAccountTitle => 'Διαγραφή Λογαριασμού';

  @override
  String get deleteAccountConfirm => 'Είστε βέβαιοι ότι θέλετε να διαγράψετε τον λογαριασμό σας;';

  @override
  String get cannotBeUndone => 'Αυτό δεν μπορεί να αναιρεθεί.';

  @override
  String get allDataErased => 'Όλες οι αναμνήσεις και οι συνομιλίες σας θα διαγραφούν μόνιμα.';

  @override
  String get appsDisconnected => 'Οι Εφαρμογές και οι Ενσωματώσεις σας θα αποσυνδεθούν αμέσως.';

  @override
  String get exportBeforeDelete =>
      'Μπορείτε να εξάγετε τα δεδομένα σας πριν διαγράψετε τον λογαριασμό σας, αλλά μόλις διαγραφεί, δεν μπορεί να ανακτηθεί.';

  @override
  String get deleteAccountCheckbox =>
      'Κατανοώ ότι η διαγραφή του λογαριασμού μου είναι μόνιμη και όλα τα δεδομένα, συμπεριλαμβανομένων των αναμνήσεων και των συνομιλιών, θα χαθούν και δεν μπορούν να ανακτηθούν.';

  @override
  String get areYouSure => 'Είστε βέβαιοι;';

  @override
  String get deleteAccountFinal =>
      'Αυτή η ενέργεια είναι μη αναστρέψιμη και θα διαγράψει μόνιμα τον λογαριασμό σας και όλα τα σχετικά δεδομένα. Είστε βέβαιοι ότι θέλετε να συνεχίσετε;';

  @override
  String get deleteNow => 'Διαγραφή Τώρα';

  @override
  String get goBack => 'Επιστροφή';

  @override
  String get checkBoxToConfirm =>
      'Επιλέξτε το πλαίσιο για να επιβεβαιώσετε ότι κατανοείτε ότι η διαγραφή του λογαριασμού σας είναι μόνιμη και μη αναστρέψιμη.';

  @override
  String get profile => 'Προφίλ';

  @override
  String get name => 'Όνομα';

  @override
  String get email => 'Email';

  @override
  String get customVocabulary => 'Προσαρμοσμένο Λεξιλόγιο';

  @override
  String get identifyingOthers => 'Αναγνώριση Άλλων';

  @override
  String get paymentMethods => 'Μέθοδοι Πληρωμής';

  @override
  String get conversationDisplay => 'Εμφάνιση Συνομιλίας';

  @override
  String get dataPrivacy => 'Δεδομένα & Απόρρητο';

  @override
  String get userId => 'Αναγνωριστικό Χρήστη';

  @override
  String get notSet => 'Δεν έχει οριστεί';

  @override
  String get userIdCopied => 'Το αναγνωριστικό χρήστη αντιγράφηκε στο πρόχειρο';

  @override
  String get systemDefault => 'Προεπιλογή Συστήματος';

  @override
  String get planAndUsage => 'Πρόγραμμα & Χρήση';

  @override
  String get offlineSync => 'Συγχρονισμός Εκτός Σύνδεσης';

  @override
  String get deviceSettings => 'Ρυθμίσεις Συσκευής';

  @override
  String get chatTools => 'Εργαλεία Συνομιλίας';

  @override
  String get feedbackBug => 'Σχόλια / Σφάλμα';

  @override
  String get helpCenter => 'Κέντρο Βοήθειας';

  @override
  String get developerSettings => 'Ρυθμίσεις Προγραμματιστή';

  @override
  String get getOmiForMac => 'Αποκτήστε το Omi για Mac';

  @override
  String get referralProgram => 'Πρόγραμμα Παραπομπών';

  @override
  String get signOut => 'Αποσύνδεση';

  @override
  String get appAndDeviceCopied => 'Τα στοιχεία εφαρμογής και συσκευής αντιγράφηκαν';

  @override
  String get wrapped2025 => 'Wrapped 2025';

  @override
  String get yourPrivacyYourControl => 'Το Απόρρητό σας, ο Έλεγχός σας';

  @override
  String get privacyIntro =>
      'Στο Omi, δεσμευόμαστε να προστατεύουμε το απόρρητό σας. Αυτή η σελίδα σας επιτρέπει να ελέγχετε πώς αποθηκεύονται και χρησιμοποιούνται τα δεδομένα σας.';

  @override
  String get learnMore => 'Μάθετε περισσότερα...';

  @override
  String get dataProtectionLevel => 'Επίπεδο Προστασίας Δεδομένων';

  @override
  String get dataProtectionDesc =>
      'Τα δεδομένα σας είναι ασφαλισμένα από προεπιλογή με ισχυρή κρυπτογράφηση. Ελέγξτε τις ρυθμίσεις σας και τις μελλοντικές επιλογές απορρήτου παρακάτω.';

  @override
  String get appAccess => 'Πρόσβαση Εφαρμογών';

  @override
  String get appAccessDesc =>
      'Οι παρακάτω εφαρμογές μπορούν να έχουν πρόσβαση στα δεδομένα σας. Πατήστε σε μια εφαρμογή για να διαχειριστείτε τα δικαιώματά της.';

  @override
  String get noAppsExternalAccess => 'Καμία εγκατεστημένη εφαρμογή δεν έχει εξωτερική πρόσβαση στα δεδομένα σας.';

  @override
  String get deviceName => 'Όνομα Συσκευής';

  @override
  String get deviceId => 'Αναγνωριστικό Συσκευής';

  @override
  String get firmware => 'Λογισμικό';

  @override
  String get sdCardSync => 'Συγχρονισμός Κάρτας SD';

  @override
  String get hardwareRevision => 'Αναθεώρηση Υλικού';

  @override
  String get modelNumber => 'Αριθμός Μοντέλου';

  @override
  String get manufacturer => 'Κατασκευαστής';

  @override
  String get doubleTap => 'Διπλό Πάτημα';

  @override
  String get ledBrightness => 'Φωτεινότητα LED';

  @override
  String get micGain => 'Ενίσχυση Μικροφώνου';

  @override
  String get disconnect => 'Αποσύνδεση';

  @override
  String get forgetDevice => 'Διαγραφή Συσκευής';

  @override
  String get chargingIssues => 'Προβλήματα Φόρτισης';

  @override
  String get disconnectDevice => 'Αποσύνδεση Συσκευής';

  @override
  String get unpairDevice => 'Κατάργηση Σύζευξης Συσκευής';

  @override
  String get unpairAndForget => 'Κατάργηση Σύζευξης και Διαγραφή Συσκευής';

  @override
  String get deviceDisconnectedMessage => 'Το Omi σας έχει αποσυνδεθεί 😔';

  @override
  String get deviceUnpairedMessage =>
      'Η σύζευξη της συσκευής καταργήθηκε. Μεταβείτε στις Ρυθμίσεις > Bluetooth και διαγράψτε τη συσκευή για να ολοκληρώσετε την κατάργηση της σύζευξης.';

  @override
  String get unpairDialogTitle => 'Κατάργηση Σύζευξης Συσκευής';

  @override
  String get unpairDialogMessage =>
      'Αυτό θα καταργήσει τη σύζευξη της συσκευής ώστε να μπορεί να συνδεθεί σε άλλο τηλέφωνο. Θα χρειαστεί να μεταβείτε στις Ρυθμίσεις > Bluetooth και να διαγράψετε τη συσκευή για να ολοκληρώσετε τη διαδικασία.';

  @override
  String get deviceNotConnected => 'Η Συσκευή Δεν Είναι Συνδεδεμένη';

  @override
  String get connectDeviceMessage =>
      'Συνδέστε τη συσκευή Omi για να αποκτήσετε πρόσβαση\nστις ρυθμίσεις και την προσαρμογή της συσκευής';

  @override
  String get deviceInfoSection => 'Πληροφορίες Συσκευής';

  @override
  String get customizationSection => 'Προσαρμογή';

  @override
  String get hardwareSection => 'Υλικό';

  @override
  String get v2Undetected => 'Δεν ανιχνεύτηκε V2';

  @override
  String get v2UndetectedMessage =>
      'Βλέπουμε ότι είτε έχετε συσκευή V1 είτε η συσκευή σας δεν είναι συνδεδεμένη. Η λειτουργικότητα κάρτας SD είναι διαθέσιμη μόνο για συσκευές V2.';

  @override
  String get endConversation => 'Τερματισμός Συνομιλίας';

  @override
  String get pauseResume => 'Παύση/Συνέχιση';

  @override
  String get starConversation => 'Αγαπημένη Συνομιλία';

  @override
  String get doubleTapAction => 'Ενέργεια Διπλού Πατήματος';

  @override
  String get endAndProcess => 'Τερματισμός & Επεξεργασία Συνομιλίας';

  @override
  String get pauseResumeRecording => 'Παύση/Συνέχιση Εγγραφής';

  @override
  String get starOngoing => 'Αγαπημένη Τρέχουσα Συνομιλία';

  @override
  String get off => 'Ανενεργό';

  @override
  String get max => 'Μέγιστο';

  @override
  String get mute => 'Σίγαση';

  @override
  String get quiet => 'Ήσυχο';

  @override
  String get normal => 'Κανονικό';

  @override
  String get high => 'Υψηλό';

  @override
  String get micGainDescMuted => 'Το μικρόφωνο είναι σε σίγαση';

  @override
  String get micGainDescLow => 'Πολύ ήσυχο - για θορυβώδη περιβάλλοντα';

  @override
  String get micGainDescModerate => 'Ήσυχο - για μέτριο θόρυβο';

  @override
  String get micGainDescNeutral => 'Ουδέτερο - ισορροπημένη εγγραφή';

  @override
  String get micGainDescSlightlyBoosted => 'Ελαφρώς ενισχυμένο - κανονική χρήση';

  @override
  String get micGainDescBoosted => 'Ενισχυμένο - για ήσυχα περιβάλλοντα';

  @override
  String get micGainDescHigh => 'Υψηλό - για απομακρυσμένες ή απαλές φωνές';

  @override
  String get micGainDescVeryHigh => 'Πολύ υψηλό - για πολύ ήσυχες πηγές';

  @override
  String get micGainDescMax => 'Μέγιστο - χρησιμοποιήστε με προσοχή';

  @override
  String get developerSettingsTitle => 'Ρυθμίσεις Προγραμματιστή';

  @override
  String get saving => 'Αποθήκευση...';

  @override
  String get personaConfig => 'Διαμορφώστε την προσωπικότητα του AI σας';

  @override
  String get beta => 'BETA';

  @override
  String get transcription => 'Απομαγνητοφώνηση';

  @override
  String get transcriptionConfig => 'Διαμόρφωση παρόχου STT';

  @override
  String get conversationTimeout => 'Λήξη Χρόνου Συνομιλίας';

  @override
  String get conversationTimeoutConfig => 'Ορίστε πότε τελειώνουν αυτόματα οι συνομιλίες';

  @override
  String get importData => 'Εισαγωγή Δεδομένων';

  @override
  String get importDataConfig => 'Εισαγωγή δεδομένων από άλλες πηγές';

  @override
  String get debugDiagnostics => 'Εντοπισμός Σφαλμάτων & Διαγνωστικά';

  @override
  String get endpointUrl => 'URL Τελικού Σημείου';

  @override
  String get noApiKeys => 'Δεν υπάρχουν κλειδιά API ακόμα';

  @override
  String get createKeyToStart => 'Δημιουργήστε ένα κλειδί για να ξεκινήσετε';

  @override
  String get createKey => 'Δημιουργία Κλειδιού';

  @override
  String get docs => 'Τεκμηρίωση';

  @override
  String get yourOmiInsights => 'Οι Πληροφορίες σας στο Omi';

  @override
  String get today => 'Σήμερα';

  @override
  String get thisMonth => 'Αυτόν τον Μήνα';

  @override
  String get thisYear => 'Φέτος';

  @override
  String get allTime => 'Συνολικά';

  @override
  String get noActivityYet => 'Καμία Δραστηριότητα Ακόμα';

  @override
  String get startConversationToSeeInsights =>
      'Ξεκινήστε μια συνομιλία με το Omi\nγια να δείτε τις πληροφορίες χρήσης σας εδώ.';

  @override
  String get listening => 'Ακρόαση';

  @override
  String get listeningSubtitle => 'Συνολικός χρόνος που το Omi έχει ακούσει ενεργά.';

  @override
  String get understanding => 'Κατανόηση';

  @override
  String get understandingSubtitle => 'Λέξεις που κατανοήθηκαν από τις συνομιλίες σας.';

  @override
  String get providing => 'Παροχή';

  @override
  String get providingSubtitle => 'Ενέργειες και σημειώσεις που καταγράφονται αυτόματα.';

  @override
  String get remembering => 'Απομνημόνευση';

  @override
  String get rememberingSubtitle => 'Γεγονότα και λεπτομέρειες που απομνημονεύονται για εσάς.';

  @override
  String get unlimitedPlan => 'Απεριόριστο Πρόγραμμα';

  @override
  String get managePlan => 'Διαχείριση Προγράμματος';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'Το πρόγραμμά σας θα ακυρωθεί στις $date.';
  }

  @override
  String renewsOn(String date) {
    return 'Το πρόγραμμά σας ανανεώνεται στις $date.';
  }

  @override
  String get basicPlan => 'Δωρεάν Πρόγραμμα';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used από $limit λεπτά χρησιμοποιήθηκαν';
  }

  @override
  String get upgrade => 'Αναβάθμιση';

  @override
  String get upgradeToUnlimited => 'Αναβάθμιση σε Απεριόριστο';

  @override
  String basicPlanDesc(int limit) {
    return 'Το πρόγραμμά σας περιλαμβάνει $limit δωρεάν λεπτά ανά μήνα. Αναβαθμίστε για απεριόριστη χρήση.';
  }

  @override
  String get shareStatsMessage => 'Μοιράζομαι τα στατιστικά μου στο Omi! (omi.me - ο πάντα ενεργός βοηθός AI σας)';

  @override
  String get sharePeriodToday => 'Σήμερα, το omi:';

  @override
  String get sharePeriodMonth => 'Αυτόν τον μήνα, το omi:';

  @override
  String get sharePeriodYear => 'Φέτος, το omi:';

  @override
  String get sharePeriodAllTime => 'Μέχρι τώρα, το omi:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 Άκουσε για $minutes λεπτά';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 Κατανόησε $words λέξεις';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ Παρείχε $count πληροφορίες';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 Απομνημόνευσε $count αναμνήσεις';
  }

  @override
  String get debugLogs => 'Αρχεία Εντοπισμού Σφαλμάτων';

  @override
  String get debugLogsAutoDelete => 'Αυτόματη διαγραφή μετά από 3 ημέρες.';

  @override
  String get debugLogsDesc => 'Βοηθά στη διάγνωση προβλημάτων';

  @override
  String get noLogFilesFound => 'Δεν βρέθηκαν αρχεία καταγραφής.';

  @override
  String get omiDebugLog => 'Αρχείο εντοπισμού σφαλμάτων Omi';

  @override
  String get logShared => 'Το αρχείο καταγραφής κοινοποιήθηκε';

  @override
  String get selectLogFile => 'Επιλογή Αρχείου Καταγραφής';

  @override
  String get shareLogs => 'Κοινοποίηση Αρχείων Καταγραφής';

  @override
  String get debugLogCleared => 'Το αρχείο εντοπισμού σφαλμάτων εκκαθαρίστηκε';

  @override
  String get exportStarted => 'Η εξαγωγή ξεκίνησε. Μπορεί να διαρκέσει μερικά δευτερόλεπτα...';

  @override
  String get exportAllData => 'Εξαγωγή Όλων των Δεδομένων';

  @override
  String get exportDataDesc => 'Εξαγωγή συνομιλιών σε αρχείο JSON';

  @override
  String get exportedConversations => 'Εξαγωγή Συνομιλιών από το Omi';

  @override
  String get exportShared => 'Η εξαγωγή κοινοποιήθηκε';

  @override
  String get deleteKnowledgeGraphTitle => 'Διαγραφή Γραφήματος Γνώσης;';

  @override
  String get deleteKnowledgeGraphMessage =>
      'Αυτό θα διαγράψει όλα τα παράγωγα δεδομένα του γραφήματος γνώσης (κόμβοι και συνδέσεις). Οι αρχικές αναμνήσεις σας θα παραμείνουν ασφαλείς. Το γράφημα θα ξαναδημιουργηθεί με το χρόνο ή στο επόμενο αίτημα.';

  @override
  String get knowledgeGraphDeleted => 'Το Γράφημα Γνώσης διαγράφηκε επιτυχώς';

  @override
  String deleteGraphFailed(String error) {
    return 'Αποτυχία διαγραφής γραφήματος: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'Διαγραφή Γραφήματος Γνώσης';

  @override
  String get deleteKnowledgeGraphDesc => 'Εκκαθάριση όλων των κόμβων και των συνδέσεων';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'Διακομιστής MCP';

  @override
  String get mcpServerDesc => 'Συνδέστε βοηθούς AI στα δεδομένα σας';

  @override
  String get serverUrl => 'URL Διακομιστή';

  @override
  String get urlCopied => 'Το URL αντιγράφηκε';

  @override
  String get apiKeyAuth => 'Πιστοποίηση Κλειδιού API';

  @override
  String get header => 'Κεφαλίδα';

  @override
  String get authorizationBearer => 'Authorization: Bearer <key>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'Αναγνωριστικό Πελάτη';

  @override
  String get clientSecret => 'Μυστικό Πελάτη';

  @override
  String get useMcpApiKey => 'Χρησιμοποιήστε το κλειδί MCP API σας';

  @override
  String get webhooks => 'Webhooks';

  @override
  String get conversationEvents => 'Συμβάντα Συνομιλίας';

  @override
  String get newConversationCreated => 'Δημιουργήθηκε νέα συνομιλία';

  @override
  String get realtimeTranscript => 'Απομαγνητοφώνηση σε Πραγματικό Χρόνο';

  @override
  String get transcriptReceived => 'Λήφθηκε απομαγνητοφώνηση';

  @override
  String get audioBytes => 'Bytes Ήχου';

  @override
  String get audioDataReceived => 'Λήφθηκαν δεδομένα ήχου';

  @override
  String get intervalSeconds => 'Διάστημα (δευτερόλεπτα)';

  @override
  String get daySummary => 'Περίληψη Ημέρας';

  @override
  String get summaryGenerated => 'Δημιουργήθηκε περίληψη';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'Προσθήκη στο claude_desktop_config.json';

  @override
  String get copyConfig => 'Αντιγραφή Διαμόρφωσης';

  @override
  String get configCopied => 'Η διαμόρφωση αντιγράφηκε στο πρόχειρο';

  @override
  String get listeningMins => 'Ακρόαση (λεπτά)';

  @override
  String get understandingWords => 'Κατανόηση (λέξεις)';

  @override
  String get insights => 'Πληροφορίες';

  @override
  String get memories => 'Αναμνήσεις';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '$used από $limit λεπτά χρησιμοποιήθηκαν αυτόν τον μήνα';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '$used από $limit λέξεις χρησιμοποιήθηκαν αυτόν τον μήνα';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '$used από $limit πληροφορίες αποκτήθηκαν αυτόν τον μήνα';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return '$used από $limit αναμνήσεις δημιουργήθηκαν αυτόν τον μήνα';
  }

  @override
  String get visibility => 'Ορατότητα';

  @override
  String get visibilitySubtitle => 'Ελέγξτε ποιες συνομιλίες εμφανίζονται στη λίστα σας';

  @override
  String get showShortConversations => 'Εμφάνιση Σύντομων Συνομιλιών';

  @override
  String get showShortConversationsDesc => 'Εμφάνιση συνομιλιών συντομότερων από το όριο';

  @override
  String get showDiscardedConversations => 'Εμφάνιση Απορριφθεισών Συνομιλιών';

  @override
  String get showDiscardedConversationsDesc => 'Συμπερίληψη συνομιλιών που επισημάνθηκαν ως απορριφθείσες';

  @override
  String get shortConversationThreshold => 'Όριο Σύντομης Συνομιλίας';

  @override
  String get shortConversationThresholdSubtitle =>
      'Οι συνομιλίες συντομότερες από αυτό θα αποκρύπτονται εκτός αν ενεργοποιηθούν παραπάνω';

  @override
  String get durationThreshold => 'Όριο Διάρκειας';

  @override
  String get durationThresholdDesc => 'Απόκρυψη συνομιλιών συντομότερων από αυτό';

  @override
  String minLabel(int count) {
    return '$count λεπτά';
  }

  @override
  String get customVocabularyTitle => 'Προσαρμοσμένο Λεξιλόγιο';

  @override
  String get addWords => 'Προσθήκη Λέξεων';

  @override
  String get addWordsDesc => 'Ονόματα, όροι ή ασυνήθιστες λέξεις';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'Σύνδεση';

  @override
  String get comingSoon => 'Σύντομα Διαθέσιμο';

  @override
  String get chatToolsFooter => 'Συνδέστε τις εφαρμογές σας για να δείτε δεδομένα και μετρήσεις στη συνομιλία.';

  @override
  String get completeAuthInBrowser =>
      'Παρακαλώ ολοκληρώστε την πιστοποίηση στο πρόγραμμα περιήγησής σας. Μόλις ολοκληρωθεί, επιστρέψτε στην εφαρμογή.';

  @override
  String failedToStartAuth(String appName) {
    return 'Αποτυχία έναρξης πιστοποίησης $appName';
  }

  @override
  String disconnectAppTitle(String appName) {
    return 'Αποσύνδεση από $appName;';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'Είστε βέβαιοι ότι θέλετε να αποσυνδεθείτε από το $appName; Μπορείτε να επανασυνδεθείτε ανά πάσα στιγμή.';
  }

  @override
  String disconnectedFrom(String appName) {
    return 'Αποσυνδέθηκε από $appName';
  }

  @override
  String get failedToDisconnect => 'Αποτυχία αποσύνδεσης';

  @override
  String connectTo(String appName) {
    return 'Σύνδεση με $appName';
  }

  @override
  String authAccessMessage(String appName) {
    return 'Θα χρειαστεί να εξουσιοδοτήσετε το Omi να έχει πρόσβαση στα δεδομένα σας στο $appName. Αυτό θα ανοίξει το πρόγραμμα περιήγησής σας για πιστοποίηση.';
  }

  @override
  String get continueAction => 'Συνέχεια';

  @override
  String get languageTitle => 'Γλώσσα';

  @override
  String get primaryLanguage => 'Κύρια Γλώσσα';

  @override
  String get automaticTranslation => 'Αυτόματη Μετάφραση';

  @override
  String get detectLanguages => 'Ανίχνευση 10+ γλωσσών';

  @override
  String get authorizeSavingRecordings => 'Εξουσιοδότηση Αποθήκευσης Εγγραφών';

  @override
  String get thanksForAuthorizing => 'Ευχαριστούμε για την εξουσιοδότηση!';

  @override
  String get needYourPermission => 'Χρειαζόμαστε την άδειά σας';

  @override
  String get alreadyGavePermission =>
      'Έχετε ήδη δώσει την άδειά σας για αποθήκευση των εγγραφών σας. Ορίστε μια υπενθύμιση γιατί το χρειαζόμαστε:';

  @override
  String get wouldLikePermission =>
      'Θα θέλαμε την άδειά σας για αποθήκευση των φωνητικών σας εγγραφών. Εδώ είναι γιατί:';

  @override
  String get improveSpeechProfile => 'Βελτίωση του Προφίλ Ομιλίας σας';

  @override
  String get improveSpeechProfileDesc =>
      'Χρησιμοποιούμε τις εγγραφές για περαιτέρω εκπαίδευση και βελτίωση του προσωπικού σας προφίλ ομιλίας.';

  @override
  String get trainFamilyProfiles => 'Εκπαίδευση Προφίλ για Φίλους και Οικογένεια';

  @override
  String get trainFamilyProfilesDesc =>
      'Οι εγγραφές σας μας βοηθούν να αναγνωρίζουμε και να δημιουργούμε προφίλ για τους φίλους και την οικογένειά σας.';

  @override
  String get enhanceTranscriptAccuracy => 'Βελτίωση της Ακρίβειας Απομαγνητοφώνησης';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'Καθώς το μοντέλο μας βελτιώνεται, μπορούμε να παρέχουμε καλύτερα αποτελέσματα απομαγνητοφώνησης για τις εγγραφές σας.';

  @override
  String get legalNotice =>
      'Νομική Ειδοποίηση: Η νομιμότητα της εγγραφής και αποθήκευσης φωνητικών δεδομένων μπορεί να διαφέρει ανάλογα με την τοποθεσία σας και τον τρόπο χρήσης αυτής της λειτουργίας. Είναι δική σας ευθύνη να διασφαλίσετε τη συμμόρφωση με τους τοπικούς νόμους και κανονισμούς.';

  @override
  String get alreadyAuthorized => 'Ήδη Εξουσιοδοτημένο';

  @override
  String get authorize => 'Εξουσιοδότηση';

  @override
  String get revokeAuthorization => 'Ανάκληση Εξουσιοδότησης';

  @override
  String get authorizationSuccessful => 'Η εξουσιοδότηση ήταν επιτυχής!';

  @override
  String get failedToAuthorize => 'Αποτυχία εξουσιοδότησης. Παρακαλώ δοκιμάστε ξανά.';

  @override
  String get authorizationRevoked => 'Η εξουσιοδότηση ανακλήθηκε.';

  @override
  String get recordingsDeleted => 'Οι εγγραφές διαγράφηκαν.';

  @override
  String get failedToRevoke => 'Αποτυχία ανάκλησης εξουσιοδότησης. Παρακαλώ δοκιμάστε ξανά.';

  @override
  String get permissionRevokedTitle => 'Η Άδεια Ανακλήθηκε';

  @override
  String get permissionRevokedMessage => 'Θέλετε να αφαιρέσουμε επίσης όλες τις υπάρχουσες εγγραφές σας;';

  @override
  String get yes => 'Ναι';

  @override
  String get editName => 'Επεξεργασία Ονόματος';

  @override
  String get howShouldOmiCallYou => 'Πώς θα πρέπει να σας αποκαλεί το Omi;';

  @override
  String get enterYourName => 'Εισάγετε το όνομά σας';

  @override
  String get nameCannotBeEmpty => 'Το όνομα δεν μπορεί να είναι κενό';

  @override
  String get nameUpdatedSuccessfully => 'Το όνομα ενημερώθηκε επιτυχώς!';

  @override
  String get calendarSettings => 'Ρυθμίσεις ημερολογίου';

  @override
  String get calendarProviders => 'Πάροχοι Ημερολογίου';

  @override
  String get macOsCalendar => 'Ημερολόγιο macOS';

  @override
  String get connectMacOsCalendar => 'Συνδέστε το τοπικό σας ημερολόγιο macOS';

  @override
  String get googleCalendar => 'Ημερολόγιο Google';

  @override
  String get syncGoogleAccount => 'Συγχρονισμός με τον λογαριασμό σας Google';

  @override
  String get showMeetingsMenuBar => 'Εμφάνιση επερχόμενων συναντήσεων στη γραμμή μενού';

  @override
  String get showMeetingsMenuBarDesc =>
      'Εμφάνιση της επόμενης συνάντησής σας και του χρόνου μέχρι να ξεκινήσει στη γραμμή μενού του macOS';

  @override
  String get showEventsNoParticipants => 'Εμφάνιση συμβάντων χωρίς συμμετέχοντες';

  @override
  String get showEventsNoParticipantsDesc =>
      'Όταν είναι ενεργοποιημένο, το Coming Up εμφανίζει συμβάντα χωρίς συμμετέχοντες ή σύνδεσμο βίντεο.';

  @override
  String get yourMeetings => 'Οι Συναντήσεις σας';

  @override
  String get refresh => 'Ανανέωση';

  @override
  String get noUpcomingMeetings => 'Δεν βρέθηκαν επερχόμενες συναντήσεις';

  @override
  String get checkingNextDays => 'Έλεγχος επόμενων 30 ημερών';

  @override
  String get tomorrow => 'Αύριο';

  @override
  String get googleCalendarComingSoon => 'Η ενσωμάτωση με το Ημερολόγιο Google έρχεται σύντομα!';

  @override
  String connectedAsUser(String userId) {
    return 'Συνδεδεμένο ως χρήστης: $userId';
  }

  @override
  String get defaultWorkspace => 'Προεπιλεγμένος Χώρος Εργασίας';

  @override
  String get tasksCreatedInWorkspace => 'Οι εργασίες θα δημιουργηθούν σε αυτόν τον χώρο εργασίας';

  @override
  String get defaultProjectOptional => 'Προεπιλεγμένο Έργο (Προαιρετικό)';

  @override
  String get leaveUnselectedTasks => 'Αφήστε το ανεπίλεκτο για δημιουργία εργασιών χωρίς έργο';

  @override
  String get noProjectsInWorkspace => 'Δεν βρέθηκαν έργα σε αυτόν τον χώρο εργασίας';

  @override
  String get conversationTimeoutDesc =>
      'Επιλέξτε πόσο χρόνο να περιμένει σε σιωπή πριν τερματιστεί αυτόματα μια συνομιλία:';

  @override
  String get timeout2Minutes => '2 λεπτά';

  @override
  String get timeout2MinutesDesc => 'Τερματισμός συνομιλίας μετά από 2 λεπτά σιωπής';

  @override
  String get timeout5Minutes => '5 λεπτά';

  @override
  String get timeout5MinutesDesc => 'Τερματισμός συνομιλίας μετά από 5 λεπτά σιωπής';

  @override
  String get timeout10Minutes => '10 λεπτά';

  @override
  String get timeout10MinutesDesc => 'Τερματισμός συνομιλίας μετά από 10 λεπτά σιωπής';

  @override
  String get timeout30Minutes => '30 λεπτά';

  @override
  String get timeout30MinutesDesc => 'Τερματισμός συνομιλίας μετά από 30 λεπτά σιωπής';

  @override
  String get timeout4Hours => '4 ώρες';

  @override
  String get timeout4HoursDesc => 'Τερματισμός συνομιλίας μετά από 4 ώρες σιωπής';

  @override
  String get conversationEndAfterHours => 'Οι συνομιλίες θα τερματίζονται πλέον μετά από 4 ώρες σιωπής';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Οι συνομιλίες θα τερματίζονται πλέον μετά από $minutes λεπτό(-ά) σιωπής';
  }

  @override
  String get tellUsPrimaryLanguage => 'Πείτε μας την κύρια γλώσσα σας';

  @override
  String get languageForTranscription =>
      'Ορίστε τη γλώσσα σας για πιο ακριβείς απομαγνητοφωνήσεις και εξατομικευμένη εμπειρία.';

  @override
  String get singleLanguageModeInfo =>
      'Η Λειτουργία Μονής Γλώσσας είναι ενεργοποιημένη. Η μετάφραση είναι απενεργοποιημένη για μεγαλύτερη ακρίβεια.';

  @override
  String get searchLanguageHint => 'Αναζήτηση γλώσσας με όνομα ή κωδικό';

  @override
  String get noLanguagesFound => 'Δεν βρέθηκαν γλώσσες';

  @override
  String get skip => 'Παράλειψη';

  @override
  String languageSetTo(String language) {
    return 'Η γλώσσα ορίστηκε σε $language';
  }

  @override
  String get failedToSetLanguage => 'Αποτυχία ορισμού γλώσσας';

  @override
  String appSettings(String appName) {
    return 'Ρυθμίσεις $appName';
  }

  @override
  String disconnectFromApp(String appName) {
    return 'Αποσύνδεση από $appName;';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'Αυτό θα αφαιρέσει την πιστοποίησή σας στο $appName. Θα χρειαστεί να επανασυνδεθείτε για να το χρησιμοποιήσετε ξανά.';
  }

  @override
  String connectedToApp(String appName) {
    return 'Συνδεδεμένο στο $appName';
  }

  @override
  String get account => 'Λογαριασμός';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Οι ενέργειές σας θα συγχρονιστούν με τον λογαριασμό σας $appName';
  }

  @override
  String get defaultSpace => 'Προεπιλεγμένος Χώρος';

  @override
  String get selectSpaceInWorkspace => 'Επιλέξτε έναν χώρο στον χώρο εργασίας σας';

  @override
  String get noSpacesInWorkspace => 'Δεν βρέθηκαν χώροι σε αυτόν τον χώρο εργασίας';

  @override
  String get defaultList => 'Προεπιλεγμένη Λίστα';

  @override
  String get tasksAddedToList => 'Οι εργασίες θα προστεθούν σε αυτή τη λίστα';

  @override
  String get noListsInSpace => 'Δεν βρέθηκαν λίστες σε αυτόν τον χώρο';

  @override
  String failedToLoadRepos(String error) {
    return 'Αποτυχία φόρτωσης αποθετηρίων: $error';
  }

  @override
  String get defaultRepoSaved => 'Το προεπιλεγμένο αποθετήριο αποθηκεύτηκε';

  @override
  String get failedToSaveDefaultRepo => 'Αποτυχία αποθήκευσης προεπιλεγμένου αποθετηρίου';

  @override
  String get defaultRepository => 'Προεπιλεγμένο Αποθετήριο';

  @override
  String get selectDefaultRepoDesc =>
      'Επιλέξτε ένα προεπιλεγμένο αποθετήριο για δημιουργία ζητημάτων. Μπορείτε ακόμα να καθορίσετε διαφορετικό αποθετήριο κατά τη δημιουργία ζητημάτων.';

  @override
  String get noReposFound => 'Δεν βρέθηκαν αποθετήρια';

  @override
  String get private => 'Ιδιωτικό';

  @override
  String updatedDate(String date) {
    return 'Ενημερώθηκε $date';
  }

  @override
  String get yesterday => 'χθες';

  @override
  String daysAgo(int count) {
    return 'πριν από $count ημέρες';
  }

  @override
  String get oneWeekAgo => 'πριν από 1 εβδομάδα';

  @override
  String weeksAgo(int count) {
    return 'πριν από $count εβδομάδες';
  }

  @override
  String get oneMonthAgo => 'πριν από 1 μήνα';

  @override
  String monthsAgo(int count) {
    return 'πριν από $count μήνες';
  }

  @override
  String get issuesCreatedInRepo => 'Τα ζητήματα θα δημιουργηθούν στο προεπιλεγμένο σας αποθετήριο';

  @override
  String get taskIntegrations => 'Ενσωματώσεις Εργασιών';

  @override
  String get configureSettings => 'Διαμόρφωση Ρυθμίσεων';

  @override
  String get completeAuthBrowser =>
      'Παρακαλώ ολοκληρώστε την πιστοποίηση στο πρόγραμμα περιήγησής σας. Μόλις ολοκληρωθεί, επιστρέψτε στην εφαρμογή.';

  @override
  String failedToStartAppAuth(String appName) {
    return 'Αποτυχία έναρξης πιστοποίησης $appName';
  }

  @override
  String connectToAppTitle(String appName) {
    return 'Σύνδεση με $appName';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Θα χρειαστεί να εξουσιοδοτήσετε το Omi να δημιουργεί εργασίες στον λογαριασμό σας $appName. Αυτό θα ανοίξει το πρόγραμμα περιήγησής σας για πιστοποίηση.';
  }

  @override
  String get continueButton => 'Συνέχεια';

  @override
  String appIntegration(String appName) {
    return 'Ενσωμάτωση $appName';
  }

  @override
  String integrationComingSoon(String appName) {
    return 'Η ενσωμάτωση με το $appName έρχεται σύντομα! Εργαζόμαστε σκληρά για να σας φέρουμε περισσότερες επιλογές διαχείρισης εργασιών.';
  }

  @override
  String get gotIt => 'Το κατάλαβα';

  @override
  String get tasksExportedOneApp => 'Οι εργασίες μπορούν να εξαχθούν σε μία εφαρμογή τη φορά.';

  @override
  String get completeYourUpgrade => 'Ολοκληρώστε την Αναβάθμισή σας';

  @override
  String get importConfiguration => 'Εισαγωγή Διαμόρφωσης';

  @override
  String get exportConfiguration => 'Εξαγωγή διαμόρφωσης';

  @override
  String get bringYourOwn => 'Φέρτε το δικό σας';

  @override
  String get payYourSttProvider => 'Χρησιμοποιήστε ελεύθερα το omi. Πληρώνετε μόνο τον πάροχο STT σας απευθείας.';

  @override
  String get freeMinutesMonth => '1.200 δωρεάν λεπτά/μήνα συμπεριλαμβάνονται. Απεριόριστο με ';

  @override
  String get omiUnlimited => 'Omi Απεριόριστο';

  @override
  String get hostRequired => 'Απαιτείται διακομιστής';

  @override
  String get validPortRequired => 'Απαιτείται έγκυρη θύρα';

  @override
  String get validWebsocketUrlRequired => 'Απαιτείται έγκυρο URL WebSocket (wss://)';

  @override
  String get apiUrlRequired => 'Απαιτείται URL API';

  @override
  String get apiKeyRequired => 'Απαιτείται κλειδί API';

  @override
  String get invalidJsonConfig => 'Μη έγκυρη διαμόρφωση JSON';

  @override
  String errorSaving(String error) {
    return 'Σφάλμα αποθήκευσης: $error';
  }

  @override
  String get configCopiedToClipboard => 'Η διαμόρφωση αντιγράφηκε στο πρόχειρο';

  @override
  String get pasteJsonConfig => 'Επικολλήστε τη διαμόρφωση JSON σας παρακάτω:';

  @override
  String get addApiKeyAfterImport => 'Θα χρειαστεί να προσθέσετε το δικό σας κλειδί API μετά την εισαγωγή';

  @override
  String get paste => 'Επικόλληση';

  @override
  String get import => 'Εισαγωγή';

  @override
  String get invalidProviderInConfig => 'Μη έγκυρος πάροχος στη διαμόρφωση';

  @override
  String importedConfig(String providerName) {
    return 'Εισήχθη η διαμόρφωση $providerName';
  }

  @override
  String invalidJson(String error) {
    return 'Μη έγκυρο JSON: $error';
  }

  @override
  String get provider => 'Πάροχος';

  @override
  String get live => 'Ζωντανά';

  @override
  String get onDevice => 'Στη Συσκευή';

  @override
  String get apiUrl => 'URL API';

  @override
  String get enterSttHttpEndpoint => 'Εισάγετε το τελικό σημείο HTTP STT σας';

  @override
  String get websocketUrl => 'URL WebSocket';

  @override
  String get enterLiveSttWebsocket => 'Εισάγετε το τελικό σημείο WebSocket STT ζωντανά';

  @override
  String get apiKey => 'Κλειδί API';

  @override
  String get enterApiKey => 'Εισάγετε το κλειδί API σας';

  @override
  String get storedLocallyNeverShared => 'Αποθηκεύεται τοπικά, δεν κοινοποιείται ποτέ';

  @override
  String get host => 'Διακομιστής';

  @override
  String get port => 'Θύρα';

  @override
  String get advanced => 'Προχωρημένα';

  @override
  String get configuration => 'Διαμόρφωση';

  @override
  String get requestConfiguration => 'Διαμόρφωση Αιτήματος';

  @override
  String get responseSchema => 'Σχήμα Απόκρισης';

  @override
  String get modified => 'Τροποποιημένο';

  @override
  String get resetRequestConfig => 'Επαναφορά διαμόρφωσης αιτήματος στην προεπιλογή';

  @override
  String get logs => 'Αρχεία Καταγραφής';

  @override
  String get logsCopied => 'Τα αρχεία καταγραφής αντιγράφηκαν';

  @override
  String get noLogsYet =>
      'Δεν υπάρχουν ακόμα αρχεία καταγραφής. Ξεκινήστε εγγραφή για να δείτε προσαρμοσμένη δραστηριότητα STT.';

  @override
  String deviceUsesCodec(String deviceName, String codecReason) {
    return 'Το $deviceName χρησιμοποιεί $codecReason. Θα χρησιμοποιηθεί το Omi.';
  }

  @override
  String get omiTranscription => 'Απομαγνητοφώνηση Omi';

  @override
  String get bestInClassTranscription => 'Κορυφαία απομαγνητοφώνηση χωρίς καμία ρύθμιση';

  @override
  String get instantSpeakerLabels => 'Άμεσες ετικέτες ομιλητών';

  @override
  String get languageTranslation => 'Μετάφραση 100+ γλωσσών';

  @override
  String get optimizedForConversation => 'Βελτιστοποιημένο για συνομιλία';

  @override
  String get autoLanguageDetection => 'Αυτόματη ανίχνευση γλώσσας';

  @override
  String get highAccuracy => 'Υψηλή ακρίβεια';

  @override
  String get privacyFirst => 'Πρώτα το απόρρητο';

  @override
  String get saveChanges => 'Αποθήκευση Αλλαγών';

  @override
  String get resetToDefault => 'Επαναφορά στην Προεπιλογή';

  @override
  String get viewTemplate => 'Προβολή Προτύπου';

  @override
  String get trySomethingLike => 'Δοκιμάστε κάτι σαν...';

  @override
  String get tryIt => 'Δοκιμάστε το';

  @override
  String get creatingPlan => 'Δημιουργία σχεδίου';

  @override
  String get developingLogic => 'Ανάπτυξη λογικής';

  @override
  String get designingApp => 'Σχεδιασμός εφαρμογής';

  @override
  String get generatingIconStep => 'Δημιουργία εικονιδίου';

  @override
  String get finalTouches => 'Τελικές πινελιές';

  @override
  String get processing => 'Επεξεργασία...';

  @override
  String get features => 'Χαρακτηριστικά';

  @override
  String get creatingYourApp => 'Δημιουργία της εφαρμογής σας...';

  @override
  String get generatingIcon => 'Δημιουργία εικονιδίου...';

  @override
  String get whatShouldWeMake => 'Τι να φτιάξουμε;';

  @override
  String get appName => 'Όνομα Εφαρμογής';

  @override
  String get description => 'Περιγραφή';

  @override
  String get publicLabel => 'Δημόσιο';

  @override
  String get privateLabel => 'Ιδιωτικό';

  @override
  String get free => 'Δωρεάν';

  @override
  String get perMonth => '/ Μήνα';

  @override
  String get tailoredConversationSummaries => 'Εξατομικευμένες Περιλήψεις Συνομιλιών';

  @override
  String get customChatbotPersonality => 'Προσαρμοσμένη Προσωπικότητα Chatbot';

  @override
  String get makePublic => 'Δημοσίευση';

  @override
  String get anyoneCanDiscover => 'Οποιοσδήποτε μπορεί να ανακαλύψει την εφαρμογή σας';

  @override
  String get onlyYouCanUse => 'Μόνο εσείς μπορείτε να χρησιμοποιήσετε αυτή την εφαρμογή';

  @override
  String get paidApp => 'Επί πληρωμή εφαρμογή';

  @override
  String get usersPayToUse => 'Οι χρήστες πληρώνουν για να χρησιμοποιήσουν την εφαρμογή σας';

  @override
  String get freeForEveryone => 'Δωρεάν για όλους';

  @override
  String get perMonthLabel => '/ μήνα';

  @override
  String get creating => 'Δημιουργία...';

  @override
  String get createApp => 'Δημιουργία Εφαρμογής';

  @override
  String get searchingForDevices => 'Αναζήτηση συσκευών...';

  @override
  String devicesFoundNearby(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'ΣΥΣΚΕΥΕΣ',
      one: 'ΣΥΣΚΕΥΗ',
    );
    return '$count $_temp0 ΒΡΕΘΗΚΑΝ ΚΟΝΤΑ';
  }

  @override
  String get pairingSuccessful => 'Η ΣΥΖΕΥΞΗ ΗΤΑΝ ΕΠΙΤΥΧΗΣ';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Σφάλμα σύνδεσης με Apple Watch: $error';
  }

  @override
  String get dontShowAgain => 'Να μην εμφανιστεί ξανά';

  @override
  String get iUnderstand => 'Κατάλαβα';

  @override
  String get enableBluetooth => 'Ενεργοποίηση Bluetooth';

  @override
  String get bluetoothNeeded =>
      'Το Omi χρειάζεται Bluetooth για σύνδεση με τη φορητή σας συσκευή. Παρακαλώ ενεργοποιήστε το Bluetooth και δοκιμάστε ξανά.';

  @override
  String get contactSupport => 'Επικοινωνία με Υποστήριξη;';

  @override
  String get connectLater => 'Σύνδεση Αργότερα';

  @override
  String get grantPermissions => 'Χορήγηση αδειών';

  @override
  String get backgroundActivity => 'Δραστηριότητα παρασκηνίου';

  @override
  String get backgroundActivityDesc => 'Επιτρέψτε στο Omi να εκτελείται στο παρασκήνιο για καλύτερη σταθερότητα';

  @override
  String get locationAccess => 'Πρόσβαση τοποθεσίας';

  @override
  String get locationAccessDesc => 'Ενεργοποιήστε την τοποθεσία παρασκηνίου για την πλήρη εμπειρία';

  @override
  String get notifications => 'Ειδοποιήσεις';

  @override
  String get notificationsDesc => 'Ενεργοποιήστε τις ειδοποιήσεις για να ενημερώνεστε';

  @override
  String get locationServiceDisabled => 'Η Υπηρεσία Τοποθεσίας είναι Απενεργοποιημένη';

  @override
  String get locationServiceDisabledDesc =>
      'Η Υπηρεσία Τοποθεσίας είναι Απενεργοποιημένη. Παρακαλώ μεταβείτε στις Ρυθμίσεις > Απόρρητο & Ασφάλεια > Υπηρεσίες Τοποθεσίας και ενεργοποιήστε την';

  @override
  String get backgroundLocationDenied => 'Απορρίφθηκε η Πρόσβαση Τοποθεσίας Παρασκηνίου';

  @override
  String get backgroundLocationDeniedDesc =>
      'Παρακαλώ μεταβείτε στις ρυθμίσεις της συσκευής και ορίστε την άδεια τοποθεσίας σε \"Πάντα Να Επιτρέπεται\"';

  @override
  String get lovingOmi => 'Αγαπάτε το Omi;';

  @override
  String get leaveReviewIos =>
      'Βοηθήστε μας να φτάσουμε σε περισσότερους ανθρώπους αφήνοντας μια κριτική στο App Store. Τα σχόλιά σας σημαίνουν τα πάντα για εμάς!';

  @override
  String get leaveReviewAndroid =>
      'Βοηθήστε μας να φτάσουμε σε περισσότερους ανθρώπους αφήνοντας μια κριτική στο Google Play Store. Τα σχόλιά σας σημαίνουν τα πάντα για εμάς!';

  @override
  String get rateOnAppStore => 'Αξιολόγηση στο App Store';

  @override
  String get rateOnGooglePlay => 'Αξιολόγηση στο Google Play';

  @override
  String get maybeLater => 'Ίσως αργότερα';

  @override
  String get speechProfileIntro =>
      'Το Omi πρέπει να μάθει τους στόχους και τη φωνή σας. Θα μπορείτε να το τροποποιήσετε αργότερα.';

  @override
  String get getStarted => 'Ξεκινήστε';

  @override
  String get allDone => 'Όλα έτοιμα!';

  @override
  String get keepGoing => 'Συνεχίστε, τα πηγαίνετε υπέροχα';

  @override
  String get skipThisQuestion => 'Παράλειψη αυτής της ερώτησης';

  @override
  String get skipForNow => 'Παράλειψη προς το παρόν';

  @override
  String get connectionError => 'Σφάλμα Σύνδεσης';

  @override
  String get connectionErrorDesc =>
      'Αποτυχία σύνδεσης με τον διακομιστή. Παρακαλώ ελέγξτε τη σύνδεσή σας στο διαδίκτυο και δοκιμάστε ξανά.';

  @override
  String get invalidRecordingMultipleSpeakers => 'Ανιχνεύθηκε μη έγκυρη εγγραφή';

  @override
  String get multipleSpeakersDesc =>
      'Φαίνεται ότι υπάρχουν πολλοί ομιλητές στην εγγραφή. Παρακαλώ βεβαιωθείτε ότι βρίσκεστε σε ήσυχο χώρο και δοκιμάστε ξανά.';

  @override
  String get tooShortDesc => 'Δεν ανιχνεύθηκε αρκετή ομιλία. Παρακαλώ μιλήστε περισσότερο και δοκιμάστε ξανά.';

  @override
  String get invalidRecordingDesc =>
      'Παρακαλώ βεβαιωθείτε ότι μιλάτε για τουλάχιστον 5 δευτερόλεπτα και όχι περισσότερο από 90.';

  @override
  String get areYouThere => 'Είστε εκεί;';

  @override
  String get noSpeechDesc =>
      'Δεν μπορέσαμε να ανιχνεύσουμε καμία ομιλία. Παρακαλώ βεβαιωθείτε ότι μιλάτε για τουλάχιστον 10 δευτερόλεπτα και όχι περισσότερο από 3 λεπτά.';

  @override
  String get connectionLost => 'Η Σύνδεση Χάθηκε';

  @override
  String get connectionLostDesc =>
      'Η σύνδεση διακόπηκε. Παρακαλώ ελέγξτε τη σύνδεσή σας στο διαδίκτυο και δοκιμάστε ξανά.';

  @override
  String get tryAgain => 'Δοκιμάστε Ξανά';

  @override
  String get connectOmiOmiGlass => 'Σύνδεση Omi / OmiGlass';

  @override
  String get continueWithoutDevice => 'Συνέχεια Χωρίς Συσκευή';

  @override
  String get permissionsRequired => 'Απαιτούνται Άδειες';

  @override
  String get permissionsRequiredDesc =>
      'Αυτή η εφαρμογή χρειάζεται άδειες Bluetooth και Τοποθεσίας για να λειτουργήσει σωστά. Παρακαλώ ενεργοποιήστε τις στις ρυθμίσεις.';

  @override
  String get openSettings => 'Άνοιγμα Ρυθμίσεων';

  @override
  String get wantDifferentName => 'Θέλετε να αποκαλείστε διαφορετικά;';

  @override
  String get whatsYourName => 'Ποιο είναι το όνομά σας;';

  @override
  String get speakTranscribeSummarize => 'Μιλήστε. Απομαγνητοφώνηση. Περίληψη.';

  @override
  String get signInWithApple => 'Σύνδεση με Apple';

  @override
  String get signInWithGoogle => 'Σύνδεση με Google';

  @override
  String get byContinuingAgree => 'Συνεχίζοντας, συμφωνείτε με την ';

  @override
  String get termsOfUse => 'Όροι Χρήσης';

  @override
  String get omiYourAiCompanion => 'Omi – Ο Βοηθός AI σας';

  @override
  String get captureEveryMoment =>
      'Καταγράψτε κάθε στιγμή. Λάβετε περιλήψεις\nμε AI. Μην κρατάτε ποτέ ξανά σημειώσεις.';

  @override
  String get appleWatchSetup => 'Ρύθμιση Apple Watch';

  @override
  String get permissionRequestedExclaim => 'Ζητήθηκε Άδεια!';

  @override
  String get microphonePermission => 'Άδεια Μικροφώνου';

  @override
  String get permissionGrantedNow =>
      'Η άδεια χορηγήθηκε! Τώρα:\n\nΑνοίξτε την εφαρμογή Omi στο ρολόι σας και πατήστε \"Συνέχεια\" παρακάτω';

  @override
  String get needMicrophonePermission =>
      'Χρειαζόμαστε άδεια μικροφώνου.\n\n1. Πατήστε \"Χορήγηση Άδειας\"\n2. Επιτρέψτε στο iPhone σας\n3. Η εφαρμογή ρολογιού θα κλείσει\n4. Ανοίξτε ξανά και πατήστε \"Συνέχεια\"';

  @override
  String get grantPermissionButton => 'Χορήγηση Άδειας';

  @override
  String get needHelp => 'Χρειάζεστε Βοήθεια;';

  @override
  String get troubleshootingSteps =>
      'Αντιμετώπιση προβλημάτων:\n\n1. Βεβαιωθείτε ότι το Omi είναι εγκατεστημένο στο ρολόι σας\n2. Ανοίξτε την εφαρμογή Omi στο ρολόι σας\n3. Αναζητήστε το αναδυόμενο παράθυρο άδειας\n4. Πατήστε \"Επιτρέπεται\" όταν σας ζητηθεί\n5. Η εφαρμογή στο ρολόι σας θα κλείσει - ανοίξτε την ξανά\n6. Επιστρέψτε και πατήστε \"Συνέχεια\" στο iPhone σας';

  @override
  String get recordingStartedSuccessfully => 'Η εγγραφή ξεκίνησε επιτυχώς!';

  @override
  String get permissionNotGrantedYet =>
      'Η άδεια δεν έχει χορηγηθεί ακόμα. Παρακαλώ βεβαιωθείτε ότι επιτρέψατε την πρόσβαση στο μικρόφωνο και ανοίξατε ξανά την εφαρμογή στο ρολόι σας.';

  @override
  String errorRequestingPermission(String error) {
    return 'Σφάλμα αιτήματος άδειας: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'Σφάλμα έναρξης εγγραφής: $error';
  }

  @override
  String get selectPrimaryLanguage => 'Επιλέξτε την κύρια γλώσσα σας';

  @override
  String get languageBenefits => 'Ορίστε τη γλώσσα σας για πιο ακριβείς απομαγνητοφωνήσεις και εξατομικευμένη εμπειρία';

  @override
  String get whatsYourPrimaryLanguage => 'Ποια είναι η κύρια γλώσσα σας;';

  @override
  String get selectYourLanguage => 'Επιλέξτε τη γλώσσα σας';

  @override
  String get personalGrowthJourney => 'Το προσωπικό σας ταξίδι ανάπτυξης με AI που ακούει κάθε σας λέξη.';

  @override
  String get actionItemsTitle => 'Προς Εκτέλεση';

  @override
  String get actionItemsDescription =>
      'Πατήστε για επεξεργασία • Παρατεταμένο πάτημα για επιλογή • Σύρετε για ενέργειες';

  @override
  String get tabToDo => 'Προς Εκτέλεση';

  @override
  String get tabDone => 'Ολοκληρωμένα';

  @override
  String get tabOld => 'Παλιά';

  @override
  String get emptyTodoMessage => '🎉 Είστε ενημερωμένοι!\nΔεν υπάρχουν εκκρεμείς ενέργειες';

  @override
  String get emptyDoneMessage => 'Δεν υπάρχουν ολοκληρωμένα στοιχεία ακόμα';

  @override
  String get emptyOldMessage => '✅ Δεν υπάρχουν παλιές εργασίες';

  @override
  String get noItems => 'Δεν υπάρχουν στοιχεία';

  @override
  String get actionItemMarkedIncomplete => 'Η ενέργεια επισημάνθηκε ως ημιτελής';

  @override
  String get actionItemCompleted => 'Η ενέργεια ολοκληρώθηκε';

  @override
  String get deleteActionItemTitle => 'Διαγραφή Ενέργειας';

  @override
  String get deleteActionItemMessage => 'Είστε βέβαιοι ότι θέλετε να διαγράψετε αυτή την ενέργεια;';

  @override
  String get deleteSelectedItemsTitle => 'Διαγραφή Επιλεγμένων Στοιχείων';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Είστε βέβαιοι ότι θέλετε να διαγράψετε $count επιλεγμένες ενέργειες$s;';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'Η ενέργεια \"$description\" διαγράφηκε';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count ενέργειες$s διαγράφηκαν';
  }

  @override
  String get failedToDeleteItem => 'Αποτυχία διαγραφής ενέργειας';

  @override
  String get failedToDeleteItems => 'Αποτυχία διαγραφής στοιχείων';

  @override
  String get failedToDeleteSomeItems => 'Αποτυχία διαγραφής ορισμένων στοιχείων';

  @override
  String get welcomeActionItemsTitle => 'Έτοιμοι για Ενέργειες';

  @override
  String get welcomeActionItemsDescription =>
      'Το AI σας θα εξάγει αυτόματα εργασίες και υποχρεώσεις από τις συνομιλίες σας. Θα εμφανιστούν εδώ όταν δημιουργηθούν.';

  @override
  String get autoExtractionFeature => 'Αυτόματη εξαγωγή από συνομιλίες';

  @override
  String get editSwipeFeature => 'Πατήστε για επεξεργασία, σύρετε για ολοκλήρωση ή διαγραφή';

  @override
  String itemsSelected(int count) {
    return '$count επιλεγμένα';
  }

  @override
  String get selectAll => 'Επιλογή όλων';

  @override
  String get deleteSelected => 'Διαγραφή επιλεγμένων';

  @override
  String searchMemories(int count) {
    return 'Αναζήτηση $count Αναμνήσεων';
  }

  @override
  String get memoryDeleted => 'Η ανάμνηση διαγράφηκε.';

  @override
  String get undo => 'Αναίρεση';

  @override
  String get noMemoriesYet => 'Δεν υπάρχουν αναμνήσεις ακόμα';

  @override
  String get noAutoMemories => 'Δεν υπάρχουν αυτόματα εξαγόμενες αναμνήσεις ακόμα';

  @override
  String get noManualMemories => 'Δεν υπάρχουν χειροκίνητες αναμνήσεις ακόμα';

  @override
  String get noMemoriesInCategories => 'Δεν υπάρχουν αναμνήσεις σε αυτές τις κατηγορίες';

  @override
  String get noMemoriesFound => 'Δεν βρέθηκαν αναμνήσεις';

  @override
  String get addFirstMemory => 'Προσθέστε την πρώτη σας ανάμνηση';

  @override
  String get clearMemoryTitle => 'Εκκαθάριση Μνήμης του Omi';

  @override
  String get clearMemoryMessage =>
      'Είστε βέβαιοι ότι θέλετε να εκκαθαρίσετε τη μνήμη του Omi; Αυτή η ενέργεια δεν μπορεί να αναιρεθεί.';

  @override
  String get clearMemoryButton => 'Εκκαθάριση Μνήμης';

  @override
  String get memoryClearedSuccess => 'Η μνήμη του Omi για εσάς έχει εκκαθαριστεί';

  @override
  String get noMemoriesToDelete => 'Δεν υπάρχουν αναμνήσεις προς διαγραφή';

  @override
  String get createMemoryTooltip => 'Δημιουργία νέας ανάμνησης';

  @override
  String get createActionItemTooltip => 'Δημιουργία νέας ενέργειας';

  @override
  String get memoryManagement => 'Διαχείριση Μνήμης';

  @override
  String get filterMemories => 'Φιλτράρισμα Αναμνήσεων';

  @override
  String totalMemoriesCount(int count) {
    return 'Έχετε $count συνολικές αναμνήσεις';
  }

  @override
  String get publicMemories => 'Δημόσιες αναμνήσεις';

  @override
  String get privateMemories => 'Ιδιωτικές αναμνήσεις';

  @override
  String get makeAllPrivate => 'Κάντε Όλες τις Αναμνήσεις Ιδιωτικές';

  @override
  String get makeAllPublic => 'Κάντε Όλες τις Αναμνήσεις Δημόσιες';

  @override
  String get deleteAllMemories => 'Διαγραφή Όλων των Αναμνήσεων';

  @override
  String get allMemoriesPrivateResult => 'Όλες οι αναμνήσεις είναι πλέον ιδιωτικές';

  @override
  String get allMemoriesPublicResult => 'Όλες οι αναμνήσεις είναι πλέον δημόσιες';

  @override
  String get newMemory => 'Νέα Ανάμνηση';

  @override
  String get editMemory => 'Επεξεργασία Ανάμνησης';

  @override
  String get memoryContentHint => 'Μου αρέσει να τρώω παγωτό...';

  @override
  String get failedToSaveMemory => 'Αποτυχία αποθήκευσης. Παρακαλώ ελέγξτε τη σύνδεσή σας.';

  @override
  String get saveMemory => 'Αποθήκευση Ανάμνησης';

  @override
  String get retry => 'Επανάληψη';

  @override
  String get createActionItem => 'Δημιουργία Ενέργειας';

  @override
  String get editActionItem => 'Επεξεργασία Ενέργειας';

  @override
  String get actionItemDescriptionHint => 'Τι πρέπει να γίνει;';

  @override
  String get actionItemDescriptionEmpty => 'Η περιγραφή της ενέργειας δεν μπορεί να είναι κενή.';

  @override
  String get actionItemUpdated => 'Η ενέργεια ενημερώθηκε';

  @override
  String get failedToUpdateActionItem => 'Αποτυχία ενημέρωσης ενέργειας';

  @override
  String get actionItemCreated => 'Η ενέργεια δημιουργήθηκε';

  @override
  String get failedToCreateActionItem => 'Αποτυχία δημιουργίας ενέργειας';

  @override
  String get dueDate => 'Ημερομηνία Λήξης';

  @override
  String get time => 'Ώρα';

  @override
  String get addDueDate => 'Προσθήκη ημερομηνίας λήξης';

  @override
  String get pressDoneToSave => 'Πατήστε τέλος για αποθήκευση';

  @override
  String get pressDoneToCreate => 'Πατήστε τέλος για δημιουργία';

  @override
  String get filterAll => 'Όλα';

  @override
  String get filterSystem => 'Σχετικά με Εσάς';

  @override
  String get filterInteresting => 'Πληροφορίες';

  @override
  String get filterManual => 'Χειροκίνητα';

  @override
  String get completed => 'Ολοκληρώθηκε';

  @override
  String get markComplete => 'Σήμανση ως ολοκληρωμένο';

  @override
  String get actionItemDeleted => 'Η ενέργεια διαγράφηκε';

  @override
  String get failedToDeleteActionItem => 'Αποτυχία διαγραφής ενέργειας';

  @override
  String get deleteActionItemConfirmTitle => 'Διαγραφή Ενέργειας';

  @override
  String get deleteActionItemConfirmMessage => 'Είστε βέβαιοι ότι θέλετε να διαγράψετε αυτή την ενέργεια;';

  @override
  String get appLanguage => 'Γλώσσα Εφαρμογής';

  @override
  String get appInterfaceSectionTitle => 'ΔΙΕΠΑΦΉ ΕΦΑΡΜΟΓΉΣ';

  @override
  String get speechTranscriptionSectionTitle => 'ΟΜΙΛΊΑ ΚΑΙ ΜΕΤΑΓΡΑΦΉ';

  @override
  String get languageSettingsHelperText =>
      'Η γλώσσα της εφαρμογής αλλάζει τα μενού και τα κουμπιά. Η γλώσσα ομιλίας επηρεάζει τον τρόπο μεταγραφής των ηχογραφήσεών σας.';
}
