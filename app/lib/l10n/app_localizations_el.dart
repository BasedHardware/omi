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
  String get cancel => 'Cancel';

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
  String get copyTranscript => 'Αντιγραφή απομαγνητοφώνησης';

  @override
  String get copySummary => 'Αντιγραφή σύνοψης';

  @override
  String get testPrompt => 'Δοκιμή Εντολής';

  @override
  String get reprocessConversation => 'Επανεπεξεργασία Συνομιλίας';

  @override
  String get deleteConversation => 'Διαγραφή συνομιλίας';

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
  String get noInternetConnection => 'Χωρίς σύνδεση στο διαδίκτυο';

  @override
  String get unableToDeleteConversation => 'Αδυναμία Διαγραφής Συνομιλίας';

  @override
  String get somethingWentWrong => 'Κάτι πήγε στραβά! Παρακαλώ δοκιμάστε ξανά αργότερα.';

  @override
  String get copyErrorMessage => 'Αντιγραφή μηνύματος σφάλματος';

  @override
  String get errorCopied => 'Το μήνυμα σφάλματος αντιγράφηκε στο πρόχειρο';

  @override
  String get remaining => 'Απομένει';

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
  String get askOmi => 'Ρώτησε το Omi';

  @override
  String get done => 'Ολοκληρώθηκε';

  @override
  String get disconnected => 'Αποσυνδεδεμένο';

  @override
  String get searching => 'Αναζήτηση...';

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
  String get noConversationsYet => 'Δεν υπάρχουν συνομιλίες ακόμα';

  @override
  String get noStarredConversations => 'Δεν υπάρχουν συνομιλίες με αστέρι';

  @override
  String get starConversationHint =>
      'Για να προσθέσετε μια συνομιλία στα αγαπημένα, ανοίξτε τη και πατήστε το εικονίδιο αστεριού στην κεφαλίδα.';

  @override
  String get searchConversations => 'Αναζήτηση συνομιλιών...';

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
  String get messageCopied => '✨ Μήνυμα αντιγράφηκε στο πρόχειρο';

  @override
  String get cannotReportOwnMessage => 'Δεν μπορείτε να αναφέρετε τα δικά σας μηνύματα.';

  @override
  String get reportMessage => 'Αναφορά μηνύματος';

  @override
  String get reportMessageConfirm => 'Είστε βέβαιοι ότι θέλετε να αναφέρετε αυτό το μήνυμα;';

  @override
  String get messageReported => 'Το μήνυμα αναφέρθηκε επιτυχώς.';

  @override
  String get thankYouFeedback => 'Ευχαριστούμε για τα σχόλιά σας!';

  @override
  String get clearChat => 'Διαγραφή συνομιλίας';

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
  String get createYourOwnApp => 'Δημιουργήστε τη δική σας εφαρμογή';

  @override
  String get buildAndShareApp => 'Δημιουργήστε και μοιραστείτε την προσαρμοσμένη εφαρμογή σας';

  @override
  String get searchApps => 'Αναζήτηση εφαρμογών...';

  @override
  String get myApps => 'Οι εφαρμογές μου';

  @override
  String get installedApps => 'Εγκατεστημένες εφαρμογές';

  @override
  String get unableToFetchApps =>
      'Αδυναμία λήψης εφαρμογών :(\n\nΠαρακαλώ ελέγξτε τη σύνδεσή σας στο διαδίκτυο και δοκιμάστε ξανά.';

  @override
  String get aboutOmi => 'Σχετικά με το Omi';

  @override
  String get privacyPolicy => 'Πολιτική Απορρήτου';

  @override
  String get visitWebsite => 'Επισκεφθείτε τον ιστότοπο';

  @override
  String get helpOrInquiries => 'Βοήθεια ή ερωτήσεις;';

  @override
  String get joinCommunity => 'Γίνετε μέλος της κοινότητας!';

  @override
  String get membersAndCounting => '8000+ μέλη και συνεχίζουν να αυξάνονται.';

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
  String get conversationDisplay => 'Εμφάνιση Συνομιλιών';

  @override
  String get dataPrivacy => 'Απόρρητο Δεδομένων';

  @override
  String get userId => 'ID Χρήστη';

  @override
  String get notSet => 'Δεν έχει οριστεί';

  @override
  String get userIdCopied => 'Το αναγνωριστικό χρήστη αντιγράφηκε στο πρόχειρο';

  @override
  String get systemDefault => 'Προεπιλογή Συστήματος';

  @override
  String get planAndUsage => 'Πρόγραμμα & Χρήση';

  @override
  String get offlineSync => 'Offline Sync';

  @override
  String get deviceSettings => 'Ρυθμίσεις Συσκευής';

  @override
  String get chatTools => 'Εργαλεία Συνομιλίας';

  @override
  String get feedbackBug => 'Σχόλια / Σφάλμα';

  @override
  String get helpCenter => 'Κέντρο Βοήθειας';

  @override
  String get developerSettings => 'Ρυθμίσεις προγραμματιστή';

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
  String get deviceId => 'Αναγνωριστικό συσκευής';

  @override
  String get firmware => 'Υλικολογισμικό';

  @override
  String get sdCardSync => 'Συγχρονισμός κάρτας SD';

  @override
  String get hardwareRevision => 'Αναθεώρηση Υλικού';

  @override
  String get modelNumber => 'Αριθμός μοντέλου';

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
  String get chargingIssues => 'Προβλήματα φόρτισης';

  @override
  String get disconnectDevice => 'Αποσύνδεση συσκευής';

  @override
  String get unpairDevice => 'Αποσύζευξη συσκευής';

  @override
  String get unpairAndForget => 'Κατάργηση Σύζευξης και Διαγραφή Συσκευής';

  @override
  String get deviceDisconnectedMessage => 'Το Omi σας έχει αποσυνδεθεί 😔';

  @override
  String get deviceUnpairedMessage =>
      'Η συσκευή αποσυζεύχθηκε. Μεταβείτε στις Ρυθμίσεις > Bluetooth και ξεχάστε τη συσκευή για να ολοκληρώσετε την αποσύζευξη.';

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
  String get off => 'Off';

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
  String get endpointUrl => 'URL τελικού σημείου';

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
  String get upgradeToUnlimited => 'Αναβάθμιση σε απεριόριστο';

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
  String get debugLogs => 'Αρχεία καταγραφής αποσφαλμάτωσης';

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
  String get shareLogs => 'Κοινή χρήση αρχείων καταγραφής';

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
  String get knowledgeGraphDeleted => 'Γράφημα γνώσης διαγράφηκε';

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
  String get urlCopied => 'Η διεύθυνση URL αντιγράφηκε';

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
  String get conversationEvents => 'Συμβάντα συνομιλίας';

  @override
  String get newConversationCreated => 'Δημιουργήθηκε νέα συνομιλία';

  @override
  String get realtimeTranscript => 'Μεταγραφή σε πραγματικό χρόνο';

  @override
  String get transcriptReceived => 'Λήφθηκε απομαγνητοφώνηση';

  @override
  String get audioBytes => 'Bytes Ήχου';

  @override
  String get audioDataReceived => 'Λήφθηκαν δεδομένα ήχου';

  @override
  String get intervalSeconds => 'Διάστημα (δευτερόλεπτα)';

  @override
  String get daySummary => 'Περίληψη ημέρας';

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
  String get insights => 'Ιδέες';

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
  String get primaryLanguage => 'Κύρια γλώσσα';

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
  String get editName => 'Edit Name';

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
  String get noUpcomingMeetings => 'Δεν υπάρχουν επερχόμενες συναντήσεις';

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
  String get yesterday => 'Χθες';

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
  String get gotIt => 'Κατάλαβα';

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
  String deviceUsesCodec(String device, String reason) {
    return '$device χρησιμοποιεί $reason. Θα χρησιμοποιηθεί το Omi.';
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
  String get saveChanges => 'Αποθήκευση αλλαγών';

  @override
  String get resetToDefault => 'Επαναφορά στην προεπιλογή';

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
  String get createApp => 'Δημιουργία εφαρμογής';

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
  String get iUnderstand => 'Κατανοώ';

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
  String get whatsYourName => 'Πώς σε λένε;';

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
  String get personalGrowthJourney => 'Το ταξίδι προσωπικής σας ανάπτυξης με AI που ακούει κάθε σας λέξη.';

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
  String get deleteActionItemTitle => 'Διαγραφή στοιχείου ενέργειας';

  @override
  String get deleteActionItemMessage => 'Είστε βέβαιοι ότι θέλετε να διαγράψετε αυτό το στοιχείο ενέργειας;';

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
  String get searchMemories => 'Αναζήτηση αναμνήσεων...';

  @override
  String get memoryDeleted => 'Η ανάμνηση διαγράφηκε.';

  @override
  String get undo => 'Αναίρεση';

  @override
  String get noMemoriesYet => '🧠 Δεν υπάρχουν αναμνήσεις ακόμα';

  @override
  String get noAutoMemories => 'Δεν υπάρχουν αυτόματα εξαγόμενες αναμνήσεις ακόμα';

  @override
  String get noManualMemories => 'Δεν υπάρχουν χειροκίνητες αναμνήσεις ακόμα';

  @override
  String get noMemoriesInCategories => 'Δεν υπάρχουν αναμνήσεις σε αυτές τις κατηγορίες';

  @override
  String get noMemoriesFound => '🔍 Δεν βρέθηκαν αναμνήσεις';

  @override
  String get addFirstMemory => 'Προσθέστε την πρώτη σας ανάμνηση';

  @override
  String get clearMemoryTitle => 'Εκκαθάριση Μνήμης του Omi';

  @override
  String get clearMemoryMessage =>
      'Είστε βέβαιοι ότι θέλετε να εκκαθαρίσετε τη μνήμη του Omi; Αυτή η ενέργεια δεν μπορεί να αναιρεθεί.';

  @override
  String get clearMemoryButton => 'Εκκαθάριση μνήμης';

  @override
  String get memoryClearedSuccess => 'Η μνήμη του Omi για εσάς έχει εκκαθαριστεί';

  @override
  String get noMemoriesToDelete => 'Δεν υπάρχουν μνήμες για διαγραφή';

  @override
  String get createMemoryTooltip => 'Δημιουργία νέας ανάμνησης';

  @override
  String get createActionItemTooltip => 'Δημιουργία νέας ενέργειας';

  @override
  String get memoryManagement => 'Διαχείριση μνήμης';

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
  String get deleteAllMemories => 'Διαγραφή όλων των μνημών';

  @override
  String get allMemoriesPrivateResult => 'Όλες οι αναμνήσεις είναι πλέον ιδιωτικές';

  @override
  String get allMemoriesPublicResult => 'Όλες οι αναμνήσεις είναι πλέον δημόσιες';

  @override
  String get newMemory => '✨ Νέα μνήμη';

  @override
  String get editMemory => '✏️ Επεξεργασία μνήμης';

  @override
  String get memoryContentHint => 'Μου αρέσει να τρώω παγωτό...';

  @override
  String get failedToSaveMemory => 'Αποτυχία αποθήκευσης. Παρακαλώ ελέγξτε τη σύνδεσή σας.';

  @override
  String get saveMemory => 'Αποθήκευση Ανάμνησης';

  @override
  String get retry => 'Retry';

  @override
  String get createActionItem => 'Δημιουργία εργασίας';

  @override
  String get editActionItem => 'Επεξεργασία εργασίας';

  @override
  String get actionItemDescriptionHint => 'Τι πρέπει να γίνει;';

  @override
  String get actionItemDescriptionEmpty => 'Η περιγραφή της ενέργειας δεν μπορεί να είναι κενή.';

  @override
  String get actionItemUpdated => 'Η ενέργεια ενημερώθηκε';

  @override
  String get failedToUpdateActionItem => 'Αποτυχία ενημέρωσης εργασίας';

  @override
  String get actionItemCreated => 'Η ενέργεια δημιουργήθηκε';

  @override
  String get failedToCreateActionItem => 'Αποτυχία δημιουργίας εργασίας';

  @override
  String get dueDate => 'Καταληκτική ημερομηνία';

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
  String get actionItemDeleted => 'Το στοιχείο ενέργειας διαγράφηκε';

  @override
  String get failedToDeleteActionItem => 'Αποτυχία διαγραφής εργασίας';

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

  @override
  String get translationNotice => 'Ειδοποίηση μετάφρασης';

  @override
  String get translationNoticeMessage =>
      'Το Omi μεταφράζει συνομιλίες στην κύρια γλώσσα σας. Ενημερώστε το ανά πάσα στιγμή στις Ρυθμίσεις → Προφίλ.';

  @override
  String get pleaseCheckInternetConnection => 'Ελέγξτε τη σύνδεσή σας στο διαδίκτυο και δοκιμάστε ξανά';

  @override
  String get pleaseSelectReason => 'Επιλέξτε έναν λόγο';

  @override
  String get tellUsMoreWhatWentWrong => 'Πείτε μας περισσότερα για το τι πήγε στραβά...';

  @override
  String get selectText => 'Επιλογή κειμένου';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Μέγιστος $count στόχοι επιτρέπονται';
  }

  @override
  String get conversationCannotBeMerged =>
      'Αυτή η συνομιλία δεν μπορεί να συγχωνευτεί (κλειδωμένη ή ήδη σε συγχώνευση)';

  @override
  String get pleaseEnterFolderName => 'Εισαγάγετε ένα όνομα φακέλου';

  @override
  String get failedToCreateFolder => 'Αποτυχία δημιουργίας φακέλου';

  @override
  String get failedToUpdateFolder => 'Αποτυχία ενημέρωσης φακέλου';

  @override
  String get folderName => 'Όνομα φακέλου';

  @override
  String get descriptionOptional => 'Περιγραφή (προαιρετικό)';

  @override
  String get failedToDeleteFolder => 'Αποτυχία διαγραφής φακέλου';

  @override
  String get editFolder => 'Επεξεργασία φακέλου';

  @override
  String get deleteFolder => 'Διαγραφή φακέλου';

  @override
  String get transcriptCopiedToClipboard => 'Το αντίγραφο αντιγράφηκε στο πρόχειρο';

  @override
  String get summaryCopiedToClipboard => 'Η περίληψη αντιγράφηκε στο πρόχειρο';

  @override
  String get conversationUrlCouldNotBeShared => 'Δεν ήταν δυνατή η κοινοποίηση του URL συνομιλίας.';

  @override
  String get urlCopiedToClipboard => 'Η διεύθυνση URL αντιγράφηκε στο πρόχειρο';

  @override
  String get exportTranscript => 'Εξαγωγή αντιγράφου';

  @override
  String get exportSummary => 'Εξαγωγή περίληψης';

  @override
  String get exportButton => 'Εξαγωγή';

  @override
  String get actionItemsCopiedToClipboard => 'Τα στοιχεία ενεργειών αντιγράφηκαν στο πρόχειρο';

  @override
  String get summarize => 'Περίληψη';

  @override
  String get generateSummary => 'Δημιουργία σύνοψης';

  @override
  String get conversationNotFoundOrDeleted => 'Η συνομιλία δεν βρέθηκε ή έχει διαγραφεί';

  @override
  String get deleteMemory => 'Διαγραφή μνήμης';

  @override
  String get thisActionCannotBeUndone => 'Αυτή η ενέργεια δεν μπορεί να αναιρεθεί.';

  @override
  String memoriesCount(int count) {
    return '$count μνήμες';
  }

  @override
  String get noMemoriesInCategory => 'Δεν υπάρχουν ακόμη μνήμες σε αυτήν την κατηγορία';

  @override
  String get addYourFirstMemory => 'Προσθέστε την πρώτη σας ανάμνηση';

  @override
  String get firmwareDisconnectUsb => 'Αποσυνδέστε το USB';

  @override
  String get firmwareUsbWarning => 'Η σύνδεση USB κατά τη διάρκεια ενημερώσεων μπορεί να βλάψει τη συσκευή σας.';

  @override
  String get firmwareBatteryAbove15 => 'Μπαταρία πάνω από 15%';

  @override
  String get firmwareEnsureBattery => 'Βεβαιωθείτε ότι η συσκευή σας έχει 15% μπαταρία.';

  @override
  String get firmwareStableConnection => 'Σταθερή σύνδεση';

  @override
  String get firmwareConnectWifi => 'Συνδεθείτε σε WiFi ή δίκτυο κινητής τηλεφωνίας.';

  @override
  String failedToStartUpdate(String error) {
    return 'Αποτυχία έναρξης ενημέρωσης: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'Πριν από την ενημέρωση, βεβαιωθείτε:';

  @override
  String get confirmed => 'Επιβεβαιώθηκε!';

  @override
  String get release => 'Αφήστε';

  @override
  String get slideToUpdate => 'Σύρετε για ενημέρωση';

  @override
  String copiedToClipboard(String title) {
    return '$title αντιγράφηκε στο πρόχειρο';
  }

  @override
  String get batteryLevel => 'Επίπεδο μπαταρίας';

  @override
  String get productUpdate => 'Ενημέρωση προϊόντος';

  @override
  String get offline => 'Εκτός σύνδεσης';

  @override
  String get available => 'Διαθέσιμο';

  @override
  String get unpairDeviceDialogTitle => 'Αποσύζευξη συσκευής';

  @override
  String get unpairDeviceDialogMessage =>
      'Αυτό θα αποσυζεύξει τη συσκευή ώστε να μπορεί να συνδεθεί σε άλλο τηλέφωνο. Θα πρέπει να μεταβείτε στις Ρυθμίσεις > Bluetooth και να ξεχάσετε τη συσκευή για να ολοκληρώσετε τη διαδικασία.';

  @override
  String get unpair => 'Αποσύζευξη';

  @override
  String get unpairAndForgetDevice => 'Αποσύζευξη και λήθη συσκευής';

  @override
  String get unknownDevice => 'Unknown';

  @override
  String get unknown => 'Άγνωστο';

  @override
  String get productName => 'Όνομα προϊόντος';

  @override
  String get serialNumber => 'Σειριακός αριθμός';

  @override
  String get connected => 'Συνδεδεμένο';

  @override
  String get privacyPolicyTitle => 'Πολιτική Απορρήτου';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label αντιγράφηκε';
  }

  @override
  String get noApiKeysYet => 'Δεν υπάρχουν ακόμα κλειδιά API. Δημιουργήστε ένα για ενσωμάτωση με την εφαρμογή σας.';

  @override
  String get createKeyToGetStarted => 'Δημιουργήστε ένα κλειδί για να ξεκινήσετε';

  @override
  String get persona => 'Persona';

  @override
  String get configureYourAiPersona => 'Διαμορφώστε την AI περσόνα σας';

  @override
  String get configureSttProvider => 'Διαμόρφωση παρόχου STT';

  @override
  String get setWhenConversationsAutoEnd => 'Ορίστε πότε οι συνομιλίες τερματίζονται αυτόματα';

  @override
  String get importDataFromOtherSources => 'Εισαγωγή δεδομένων από άλλες πηγές';

  @override
  String get debugAndDiagnostics => 'Αποσφαλμάτωση και διαγνωστικά';

  @override
  String get autoDeletesAfter3Days => 'Αυτόματη διαγραφή μετά από 3 ημέρες';

  @override
  String get helpsDiagnoseIssues => 'Βοηθά στη διάγνωση προβλημάτων';

  @override
  String get exportStartedMessage => 'Η εξαγωγή ξεκίνησε. Αυτό μπορεί να διαρκέσει μερικά δευτερόλεπτα...';

  @override
  String get exportConversationsToJson => 'Εξαγωγή συνομιλιών σε αρχείο JSON';

  @override
  String get knowledgeGraphDeletedSuccess => 'Το γράφημα γνώσης διαγράφηκε επιτυχώς';

  @override
  String failedToDeleteGraph(String error) {
    return 'Αποτυχία διαγραφής γραφήματος: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'Εκκαθάριση όλων των κόμβων και συνδέσεων';

  @override
  String get addToClaudeDesktopConfig => 'Προσθήκη στο claude_desktop_config.json';

  @override
  String get connectAiAssistantsToData => 'Συνδέστε βοηθούς AI με τα δεδομένα σας';

  @override
  String get useYourMcpApiKey => 'Χρησιμοποιήστε το κλειδί MCP API σας';

  @override
  String get realTimeTranscript => 'Μεταγραφή σε πραγματικό χρόνο';

  @override
  String get experimental => 'Πειραματικό';

  @override
  String get transcriptionDiagnostics => 'Διαγνωστικά μεταγραφής';

  @override
  String get detailedDiagnosticMessages => 'Λεπτομερή διαγνωστικά μηνύματα';

  @override
  String get autoCreateSpeakers => 'Αυτόματη δημιουργία ομιλητών';

  @override
  String get autoCreateWhenNameDetected => 'Αυτόματη δημιουργία όταν ανιχνευθεί όνομα';

  @override
  String get followUpQuestions => 'Συμπληρωματικές ερωτήσεις';

  @override
  String get suggestQuestionsAfterConversations => 'Προτείνετε ερωτήσεις μετά τις συνομιλίες';

  @override
  String get goalTracker => 'Παρακολούθηση στόχων';

  @override
  String get trackPersonalGoalsOnHomepage => 'Παρακολουθήστε τους προσωπικούς σας στόχους στην αρχική σελίδα';

  @override
  String get dailyReflection => 'Ημερήσιος αναστοχασμός';

  @override
  String get get9PmReminderToReflect => 'Λάβετε υπενθύμιση στις 9 μ.μ. για να αναλογιστείτε την ημέρα σας';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'Η περιγραφή του στοιχείου ενέργειας δεν μπορεί να είναι κενή';

  @override
  String get saved => 'Αποθηκεύτηκε';

  @override
  String get overdue => 'Εκπρόθεσμο';

  @override
  String get failedToUpdateDueDate => 'Αποτυχία ενημέρωσης ημερομηνίας λήξης';

  @override
  String get markIncomplete => 'Σήμανση ως ημιτελές';

  @override
  String get editDueDate => 'Επεξεργασία ημερομηνίας λήξης';

  @override
  String get setDueDate => 'Ορισμός καταληκτικής ημερομηνίας';

  @override
  String get clearDueDate => 'Εκκαθάριση ημερομηνίας λήξης';

  @override
  String get failedToClearDueDate => 'Αποτυχία εκκαθάρισης ημερομηνίας λήξης';

  @override
  String get mondayAbbr => 'Δευ';

  @override
  String get tuesdayAbbr => 'Τρί';

  @override
  String get wednesdayAbbr => 'Τετ';

  @override
  String get thursdayAbbr => 'Πέμ';

  @override
  String get fridayAbbr => 'Παρ';

  @override
  String get saturdayAbbr => 'Σάβ';

  @override
  String get sundayAbbr => 'Κυρ';

  @override
  String get howDoesItWork => 'Πώς λειτουργεί;';

  @override
  String get sdCardSyncDescription =>
      'Ο συγχρονισμός κάρτας SD θα εισαγάγει τις αναμνήσεις σας από την κάρτα SD στην εφαρμογή';

  @override
  String get checksForAudioFiles => 'Ελέγχει για αρχεία ήχου στην κάρτα SD';

  @override
  String get omiSyncsAudioFiles => 'Το Omi στη συνέχεια συγχρονίζει τα αρχεία ήχου με τον διακομιστή';

  @override
  String get serverProcessesAudio => 'Ο διακομιστής επεξεργάζεται τα αρχεία ήχου και δημιουργεί αναμνήσεις';

  @override
  String get youreAllSet => 'Είστε έτοιμοι!';

  @override
  String get welcomeToOmiDescription =>
      'Καλώς ήρθατε στο Omi! Ο AI σύντροφός σας είναι έτοιμος να σας βοηθήσει με συνομιλίες, εργασίες και πολλά άλλα.';

  @override
  String get startUsingOmi => 'Ξεκινήστε να χρησιμοποιείτε το Omi';

  @override
  String get back => 'Πίσω';

  @override
  String get keyboardShortcuts => 'Συντομεύσεις Πληκτρολογίου';

  @override
  String get toggleControlBar => 'Εναλλαγή γραμμής ελέγχου';

  @override
  String get pressKeys => 'Πατήστε πλήκτρα...';

  @override
  String get cmdRequired => '⌘ απαιτείται';

  @override
  String get invalidKey => 'Μη έγκυρο πλήκτρο';

  @override
  String get space => 'Διάστημα';

  @override
  String get search => 'Αναζήτηση';

  @override
  String get searchPlaceholder => 'Αναζήτηση...';

  @override
  String get untitledConversation => 'Συνομιλία χωρίς τίτλο';

  @override
  String countRemaining(String count) {
    return '$count απομένουν';
  }

  @override
  String get addGoal => 'Προσθήκη στόχου';

  @override
  String get editGoal => 'Επεξεργασία στόχου';

  @override
  String get icon => 'Εικονίδιο';

  @override
  String get goalTitle => 'Τίτλος στόχου';

  @override
  String get current => 'Τρέχον';

  @override
  String get target => 'Στόχος';

  @override
  String get saveGoal => 'Αποθήκευση';

  @override
  String get goals => 'Στόχοι';

  @override
  String get tapToAddGoal => 'Πατήστε για να προσθέσετε στόχο';

  @override
  String welcomeBack(String name) {
    return 'Καλώς ήρθες πάλι, $name';
  }

  @override
  String get yourConversations => 'Οι συνομιλίες σου';

  @override
  String get reviewAndManageConversations => 'Ελέγξτε και διαχειριστείτε τις καταγεγραμμένες συνομιλίες σας';

  @override
  String get startCapturingConversations =>
      'Ξεκινήστε να καταγράφετε συνομιλίες με τη συσκευή Omi για να τις δείτε εδώ.';

  @override
  String get useMobileAppToCapture => 'Χρησιμοποιήστε την εφαρμογή κινητού για να καταγράψετε ήχο';

  @override
  String get conversationsProcessedAutomatically => 'Οι συνομιλίες επεξεργάζονται αυτόματα';

  @override
  String get getInsightsInstantly => 'Λάβετε πληροφορίες και περιλήψεις αμέσως';

  @override
  String get showAll => 'Εμφάνιση όλων →';

  @override
  String get noTasksForToday =>
      'Δεν υπάρχουν εργασίες για σήμερα.\\nΡωτήστε το Omi για περισσότερες εργασίες ή δημιουργήστε χειροκίνητα.';

  @override
  String get dailyScore => 'ΗΜΕΡΗΣΙΟ ΣΚΟΡ';

  @override
  String get dailyScoreDescription => 'Ένα σκορ για να σας βοηθήσει\nνα εστιάσετε καλύτερα στην εκτέλεση.';

  @override
  String get searchResults => 'Αποτελέσματα αναζήτησης';

  @override
  String get actionItems => 'Στοιχεία δράσης';

  @override
  String get tasksToday => 'Σήμερα';

  @override
  String get tasksTomorrow => 'Αύριο';

  @override
  String get tasksNoDeadline => 'Χωρίς προθεσμία';

  @override
  String get tasksLater => 'Αργότερα';

  @override
  String get loadingTasks => 'Φόρτωση εργασιών...';

  @override
  String get tasks => 'Εργασίες';

  @override
  String get swipeTasksToIndent => 'Σύρετε εργασίες για εσοχή, σύρετε μεταξύ κατηγοριών';

  @override
  String get create => 'Δημιουργία';

  @override
  String get noTasksYet => 'Δεν υπάρχουν εργασίες ακόμα';

  @override
  String get tasksFromConversationsWillAppear =>
      'Οι εργασίες από τις συνομιλίες σας θα εμφανιστούν εδώ.\nΚάντε κλικ στο Δημιουργία για να προσθέσετε μία μη αυτόματα.';

  @override
  String get monthJan => 'Ιαν';

  @override
  String get monthFeb => 'Φεβ';

  @override
  String get monthMar => 'Μάρ';

  @override
  String get monthApr => 'Απρ';

  @override
  String get monthMay => 'Μάι';

  @override
  String get monthJun => 'Ιούν';

  @override
  String get monthJul => 'Ιούλ';

  @override
  String get monthAug => 'Αύγ';

  @override
  String get monthSep => 'Σεπ';

  @override
  String get monthOct => 'Οκτ';

  @override
  String get monthNov => 'Νοέ';

  @override
  String get monthDec => 'Δεκ';

  @override
  String get timePM => 'ΜΜ';

  @override
  String get timeAM => 'ΠΜ';

  @override
  String get actionItemUpdatedSuccessfully => 'Η εργασία ενημερώθηκε με επιτυχία';

  @override
  String get actionItemCreatedSuccessfully => 'Η εργασία δημιουργήθηκε με επιτυχία';

  @override
  String get actionItemDeletedSuccessfully => 'Η εργασία διαγράφηκε με επιτυχία';

  @override
  String get deleteActionItem => 'Διαγραφή εργασίας';

  @override
  String get deleteActionItemConfirmation =>
      'Είστε βέβαιοι ότι θέλετε να διαγράψετε αυτήν την εργασία; Αυτή η ενέργεια δεν μπορεί να αναιρεθεί.';

  @override
  String get enterActionItemDescription => 'Εισαγάγετε περιγραφή εργασίας...';

  @override
  String get markAsCompleted => 'Επισήμανση ως ολοκληρωμένη';

  @override
  String get setDueDateAndTime => 'Ορισμός καταληκτικής ημερομηνίας και ώρας';

  @override
  String get reloadingApps => 'Επαναφόρτωση εφαρμογών...';

  @override
  String get loadingApps => 'Φόρτωση εφαρμογών...';

  @override
  String get browseInstallCreateApps => 'Περιήγηση, εγκατάσταση και δημιουργία εφαρμογών';

  @override
  String get all => 'All';

  @override
  String get open => 'Άνοιγμα';

  @override
  String get install => 'Εγκατάσταση';

  @override
  String get noAppsAvailable => 'Δεν υπάρχουν διαθέσιμες εφαρμογές';

  @override
  String get unableToLoadApps => 'Αδυναμία φόρτωσης εφαρμογών';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'Δοκιμάστε να προσαρμόσετε τους όρους αναζήτησης ή τα φίλτρα';

  @override
  String get checkBackLaterForNewApps => 'Ελέγξτε ξανά αργότερα για νέες εφαρμογές';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'Ελέγξτε τη σύνδεσή σας στο διαδίκτυο και δοκιμάστε ξανά';

  @override
  String get createNewApp => 'Δημιουργία νέας εφαρμογής';

  @override
  String get buildSubmitCustomOmiApp => 'Κατασκευάστε και υποβάλετε την προσαρμοσμένη εφαρμογή Omi σας';

  @override
  String get submittingYourApp => 'Υποβολή της εφαρμογής σας...';

  @override
  String get preparingFormForYou => 'Προετοιμασία της φόρμας για εσάς...';

  @override
  String get appDetails => 'Λεπτομέρειες εφαρμογής';

  @override
  String get paymentDetails => 'Στοιχεία πληρωμής';

  @override
  String get previewAndScreenshots => 'Προεπισκόπηση και στιγμιότυπα οθόνης';

  @override
  String get appCapabilities => 'Δυνατότητες εφαρμογής';

  @override
  String get aiPrompts => 'Προτροπές τεχνητής νοημοσύνης';

  @override
  String get chatPrompt => 'Προτροπή συνομιλίας';

  @override
  String get chatPromptPlaceholder =>
      'Είστε μια υπέροχη εφαρμογή, η δουλειά σας είναι να απαντάτε στα ερωτήματα των χρηστών και να τους κάνετε να αισθάνονται καλά...';

  @override
  String get conversationPrompt => 'Προτροπή συνομιλίας';

  @override
  String get conversationPromptPlaceholder =>
      'Είστε μια υπέροχη εφαρμογή, θα σας δοθεί απομαγνητοφώνηση και περίληψη μιας συζήτησης...';

  @override
  String get notificationScopes => 'Πεδία ειδοποιήσεων';

  @override
  String get appPrivacyAndTerms => 'Απόρρητο και όροι εφαρμογής';

  @override
  String get makeMyAppPublic => 'Κάντε την εφαρμογή μου δημόσια';

  @override
  String get submitAppTermsAgreement =>
      'Υποβάλλοντας αυτήν την εφαρμογή, συμφωνώ με τους Όρους Υπηρεσίας και την Πολιτική Απορρήτου του Omi AI';

  @override
  String get submitApp => 'Υποβολή εφαρμογής';

  @override
  String get needHelpGettingStarted => 'Χρειάζεστε βοήθεια για να ξεκινήσετε;';

  @override
  String get clickHereForAppBuildingGuides => 'Κάντε κλικ εδώ για οδηγούς δημιουργίας εφαρμογών και τεκμηρίωση';

  @override
  String get submitAppQuestion => 'Υποβολή εφαρμογής;';

  @override
  String get submitAppPublicDescription =>
      'Η εφαρμογή σας θα αξιολογηθεί και θα γίνει δημόσια. Μπορείτε να αρχίσετε να τη χρησιμοποιείτε αμέσως, ακόμη και κατά τη διάρκεια της αξιολόγησης!';

  @override
  String get submitAppPrivateDescription =>
      'Η εφαρμογή σας θα αξιολογηθεί και θα διατεθεί σε εσάς ιδιωτικά. Μπορείτε να αρχίσετε να τη χρησιμοποιείτε αμέσως, ακόμη και κατά τη διάρκεια της αξιολόγησης!';

  @override
  String get startEarning => 'Ξεκινήστε να κερδίζετε! 💰';

  @override
  String get connectStripeOrPayPal => 'Συνδέστε το Stripe ή το PayPal για να λαμβάνετε πληρωμές για την εφαρμογή σας.';

  @override
  String get connectNow => 'Σύνδεση τώρα';

  @override
  String get installsCount => 'Εγκαταστάσεις';

  @override
  String get uninstallApp => 'Απεγκατάσταση εφαρμογής';

  @override
  String get subscribe => 'Εγγραφή';

  @override
  String get dataAccessNotice => 'Ειδοποίηση πρόσβασης δεδομένων';

  @override
  String get dataAccessWarning =>
      'Αυτή η εφαρμογή θα έχει πρόσβαση στα δεδομένα σας. Η Omi AI δεν είναι υπεύθυνη για τον τρόπο χρήσης, τροποποίησης ή διαγραφής των δεδομένων σας από αυτήν την εφαρμογή';

  @override
  String get installApp => 'Εγκατάσταση εφαρμογής';

  @override
  String get betaTesterNotice =>
      'Είστε δοκιμαστής beta για αυτήν την εφαρμογή. Δεν είναι ακόμα δημόσια. Θα γίνει δημόσια μόλις εγκριθεί.';

  @override
  String get appUnderReviewOwner =>
      'Η εφαρμογή σας βρίσκεται υπό αναθεώρηση και είναι ορατή μόνο σε εσάς. Θα γίνει δημόσια μόλις εγκριθεί.';

  @override
  String get appRejectedNotice =>
      'Η εφαρμογή σας απορρίφθηκε. Παρακαλούμε ενημερώστε τις λεπτομέρειες της εφαρμογής και υποβάλετε ξανά για αναθεώρηση.';

  @override
  String get setupSteps => 'Βήματα εγκατάστασης';

  @override
  String get setupInstructions => 'Οδηγίες ρύθμισης';

  @override
  String get integrationInstructions => 'Οδηγίες ενσωμάτωσης';

  @override
  String get preview => 'Προεπισκόπηση';

  @override
  String get aboutTheApp => 'Σχετικά με την εφαρμογή';

  @override
  String get aboutThePersona => 'Σχετικά με την περσόνα';

  @override
  String get chatPersonality => 'Προσωπικότητα συνομιλίας';

  @override
  String get ratingsAndReviews => 'Αξιολογήσεις και κριτικές';

  @override
  String get noRatings => 'χωρίς αξιολογήσεις';

  @override
  String ratingsCount(String count) {
    return '$count+ αξιολογήσεις';
  }

  @override
  String get errorActivatingApp => 'Σφάλμα ενεργοποίησης εφαρμογής';

  @override
  String get integrationSetupRequired =>
      'Εάν αυτή είναι μια εφαρμογή ενσωμάτωσης, βεβαιωθείτε ότι η εγκατάσταση έχει ολοκληρωθεί.';

  @override
  String get installed => 'Εγκατεστημένο';

  @override
  String get appIdLabel => 'Αναγνωριστικό εφαρμογής';

  @override
  String get appNameLabel => 'Όνομα εφαρμογής';

  @override
  String get appNamePlaceholder => 'Η υπέροχη εφαρμογή μου';

  @override
  String get pleaseEnterAppName => 'Παρακαλώ εισάγετε το όνομα της εφαρμογής';

  @override
  String get categoryLabel => 'Κατηγορία';

  @override
  String get selectCategory => 'Επιλέξτε κατηγορία';

  @override
  String get descriptionLabel => 'Περιγραφή';

  @override
  String get appDescriptionPlaceholder =>
      'Η υπέροχη εφαρμογή μου είναι μια υπέροχη εφαρμογή που κάνει καταπληκτικά πράγματα. Είναι η καλύτερη εφαρμογή!';

  @override
  String get pleaseProvideValidDescription => 'Παρακαλώ δώστε μια έγκυρη περιγραφή';

  @override
  String get appPricingLabel => 'Τιμολόγηση εφαρμογής';

  @override
  String get noneSelected => 'Δεν επιλέχθηκε κανένα';

  @override
  String get appIdCopiedToClipboard => 'Το αναγνωριστικό εφαρμογής αντιγράφηκε στο πρόχειρο';

  @override
  String get appCategoryModalTitle => 'Κατηγορία εφαρμογής';

  @override
  String get pricingFree => 'Δωρεάν';

  @override
  String get pricingPaid => 'Επί πληρωμή';

  @override
  String get loadingCapabilities => 'Φόρτωση δυνατοτήτων...';

  @override
  String get filterInstalled => 'Εγκατεστημένα';

  @override
  String get filterMyApps => 'Οι εφαρμογές μου';

  @override
  String get clearSelection => 'Εκκαθάριση επιλογής';

  @override
  String get filterCategory => 'Κατηγορία';

  @override
  String get rating4PlusStars => '4+ αστέρια';

  @override
  String get rating3PlusStars => '3+ αστέρια';

  @override
  String get rating2PlusStars => '2+ αστέρια';

  @override
  String get rating1PlusStars => '1+ αστέρι';

  @override
  String get filterRating => 'Αξιολόγηση';

  @override
  String get filterCapabilities => 'Δυνατότητες';

  @override
  String get noNotificationScopesAvailable => 'Δεν υπάρχουν διαθέσιμα πεδία ειδοποιήσεων';

  @override
  String get popularApps => 'Δημοφιλείς εφαρμογές';

  @override
  String get pleaseProvidePrompt => 'Παρακαλώ δώστε μια προτροπή';

  @override
  String chatWithAppName(String appName) {
    return 'Συνομιλία με $appName';
  }

  @override
  String get defaultAiAssistant => 'Προεπιλεγμένος βοηθός AI';

  @override
  String get readyToChat => '✨ Έτοιμος για συνομιλία!';

  @override
  String get connectionNeeded => '🌐 Απαιτείται σύνδεση';

  @override
  String get startConversation => 'Ξεκινήστε μια συνομιλία και αφήστε τη μαγεία να ξεκινήσει';

  @override
  String get checkInternetConnection => 'Παρακαλώ ελέγξτε τη σύνδεσή σας στο Internet';

  @override
  String get wasThisHelpful => 'Ήταν αυτό χρήσιμο;';

  @override
  String get thankYouForFeedback => 'Ευχαριστούμε για τα σχόλιά σας!';

  @override
  String get maxFilesUploadError => 'Μπορείτε να ανεβάσετε μόνο 4 αρχεία τη φορά';

  @override
  String get attachedFiles => '📎 Συνημμένα αρχεία';

  @override
  String get takePhoto => 'Λήψη φωτογραφίας';

  @override
  String get captureWithCamera => 'Λήψη με κάμερα';

  @override
  String get selectImages => 'Επιλέξτε εικόνες';

  @override
  String get chooseFromGallery => 'Επιλογή από τη συλλογή';

  @override
  String get selectFile => 'Επιλέξτε αρχείο';

  @override
  String get chooseAnyFileType => 'Επιλέξτε οποιονδήποτε τύπο αρχείου';

  @override
  String get cannotReportOwnMessages => 'Δεν μπορείτε να αναφέρετε τα δικά σας μηνύματα';

  @override
  String get messageReportedSuccessfully => '✅ Το μήνυμα αναφέρθηκε επιτυχώς';

  @override
  String get confirmReportMessage => 'Είστε βέβαιοι ότι θέλετε να αναφέρετε αυτό το μήνυμα;';

  @override
  String get selectChatAssistant => 'Επιλογή βοηθού συνομιλίας';

  @override
  String get enableMoreApps => 'Ενεργοποίηση περισσότερων εφαρμογών';

  @override
  String get chatCleared => 'Η συνομιλία διαγράφηκε';

  @override
  String get clearChatTitle => 'Διαγραφή συνομιλίας;';

  @override
  String get confirmClearChat =>
      'Είστε βέβαιοι ότι θέλετε να διαγράψετε τη συνομιλία; Αυτή η ενέργεια δεν μπορεί να αναιρεθεί.';

  @override
  String get copy => 'Αντιγραφή';

  @override
  String get share => 'Κοινοποίηση';

  @override
  String get report => 'Αναφορά';

  @override
  String get microphonePermissionRequired => 'Απαιτείται άδεια μικροφώνου για ηχογράφηση φωνής.';

  @override
  String get microphonePermissionDenied =>
      'Άρνηση άδειας μικροφώνου. Παρακαλώ δώστε άδεια στις Προτιμήσεις Συστήματος > Απόρρητο & Ασφάλεια > Μικρόφωνο.';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'Αποτυχία ελέγχου άδειας μικροφώνου: $error';
  }

  @override
  String get failedToTranscribeAudio => 'Αποτυχία μεταγραφής ήχου';

  @override
  String get transcribing => 'Μεταγραφή...';

  @override
  String get transcriptionFailed => 'Η μεταγραφή απέτυχε';

  @override
  String get discardedConversation => 'Απορριφθείσα συνομιλία';

  @override
  String get at => 'στις';

  @override
  String get from => 'από';

  @override
  String get copied => 'Αντιγράφηκε!';

  @override
  String get copyLink => 'Αντιγραφή συνδέσμου';

  @override
  String get hideTranscript => 'Απόκρυψη μεταγραφής';

  @override
  String get viewTranscript => 'Προβολή μεταγραφής';

  @override
  String get conversationDetails => 'Λεπτομέρειες συνομιλίας';

  @override
  String get transcript => 'Μεταγραφή';

  @override
  String segmentsCount(int count) {
    return '$count τμήματα';
  }

  @override
  String get noTranscriptAvailable => 'Δεν υπάρχει διαθέσιμη μεταγραφή';

  @override
  String get noTranscriptMessage => 'Αυτή η συνομιλία δεν έχει μεταγραφή.';

  @override
  String get conversationUrlCouldNotBeGenerated => 'Η διεύθυνση URL της συνομιλίας δεν μπόρεσε να δημιουργηθεί.';

  @override
  String get failedToGenerateConversationLink => 'Αποτυχία δημιουργίας συνδέσμου συνομιλίας';

  @override
  String get failedToGenerateShareLink => 'Αποτυχία δημιουργίας συνδέσμου κοινής χρήσης';

  @override
  String get reloadingConversations => 'Επαναφόρτωση συνομιλιών...';

  @override
  String get user => 'Χρήστης';

  @override
  String get starred => 'Με αστέρι';

  @override
  String get date => 'Ημερομηνία';

  @override
  String get noResultsFound => 'Δεν βρέθηκαν αποτελέσματα';

  @override
  String get tryAdjustingSearchTerms => 'Δοκιμάστε να προσαρμόσετε τους όρους αναζήτησης';

  @override
  String get starConversationsToFindQuickly => 'Βάλτε αστέρι στις συνομιλίες για να τις βρίσκετε γρήγορα εδώ';

  @override
  String noConversationsOnDate(String date) {
    return 'Δεν υπάρχουν συνομιλίες στις $date';
  }

  @override
  String get trySelectingDifferentDate => 'Δοκιμάστε να επιλέξετε διαφορετική ημερομηνία';

  @override
  String get conversations => 'Συνομιλίες';

  @override
  String get chat => 'Συνομιλία';

  @override
  String get actions => 'Ενέργειες';

  @override
  String get syncAvailable => 'Συγχρονισμός διαθέσιμος';

  @override
  String get referAFriend => 'Πρότεινε έναν φίλο';

  @override
  String get help => 'Βοήθεια';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'Αναβάθμιση σε Pro';

  @override
  String get getOmiDevice => 'Get Omi Device';

  @override
  String get wearableAiCompanion => 'Φορετός σύντροφος AI';

  @override
  String get loadingMemories => 'Φόρτωση αναμνήσεων...';

  @override
  String get allMemories => 'Όλες οι αναμνήσεις';

  @override
  String get aboutYou => 'Σχετικά με εσάς';

  @override
  String get manual => 'Χειροκίνητο';

  @override
  String get loadingYourMemories => 'Φόρτωση των αναμνήσεών σας...';

  @override
  String get createYourFirstMemory => 'Δημιουργήστε την πρώτη σας ανάμνηση για να ξεκινήσετε';

  @override
  String get tryAdjustingFilter => 'Δοκιμάστε να προσαρμόσετε την αναζήτηση ή το φίλτρο σας';

  @override
  String get whatWouldYouLikeToRemember => 'Τι θα θέλατε να θυμάστε;';

  @override
  String get category => 'Κατηγορία';

  @override
  String get public => 'Δημόσιο';

  @override
  String get failedToSaveCheckConnection => 'Αποτυχία αποθήκευσης. Ελέγξτε τη σύνδεσή σας.';

  @override
  String get createMemory => 'Δημιουργία μνήμης';

  @override
  String get deleteMemoryConfirmation =>
      'Είστε σίγουροι ότι θέλετε να διαγράψετε αυτήν τη μνήμη; Αυτή η ενέργεια δεν μπορεί να αναιρεθεί.';

  @override
  String get makePrivate => 'Κάντε ιδιωτική';

  @override
  String get organizeAndControlMemories => 'Οργανώστε και ελέγξτε τις μνήμες σας';

  @override
  String get total => 'Σύνολο';

  @override
  String get makeAllMemoriesPrivate => 'Κάντε όλες τις μνήμες ιδιωτικές';

  @override
  String get setAllMemoriesToPrivate => 'Ορίστε όλες τις μνήμες σε ιδιωτική ορατότητα';

  @override
  String get makeAllMemoriesPublic => 'Κάντε όλες τις μνήμες δημόσιες';

  @override
  String get setAllMemoriesToPublic => 'Ορίστε όλες τις μνήμες σε δημόσια ορατότητα';

  @override
  String get permanentlyRemoveAllMemories => 'Μόνιμη αφαίρεση όλων των μνημών από το Omi';

  @override
  String get allMemoriesAreNowPrivate => 'Όλες οι μνήμες είναι πλέον ιδιωτικές';

  @override
  String get allMemoriesAreNowPublic => 'Όλες οι μνήμες είναι πλέον δημόσιες';

  @override
  String get clearOmisMemory => 'Εκκαθάριση μνήμης του Omi';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Είστε σίγουροι ότι θέλετε να διαγράψετε τη μνήμη του Omi; Αυτή η ενέργεια δεν μπορεί να αναιρεθεί και θα διαγράψει μόνιμα όλες τις $count μνήμες.';
  }

  @override
  String get omisMemoryCleared => 'Η μνήμη του Omi για εσάς έχει διαγραφεί';

  @override
  String get welcomeToOmi => 'Καλώς ήρθατε στο Omi';

  @override
  String get continueWithApple => 'Συνέχεια με Apple';

  @override
  String get continueWithGoogle => 'Συνέχεια με Google';

  @override
  String get byContinuingYouAgree => 'Συνεχίζοντας, συμφωνείτε με τους ';

  @override
  String get termsOfService => 'Όρους Υπηρεσίας';

  @override
  String get and => ' και ';

  @override
  String get dataAndPrivacy => 'Δεδομένα & Απόρρητο';

  @override
  String get secureAuthViaAppleId => 'Ασφαλής ταυτοποίηση μέσω Apple ID';

  @override
  String get secureAuthViaGoogleAccount => 'Ασφαλής ταυτοποίηση μέσω λογαριασμού Google';

  @override
  String get whatWeCollect => 'Τι συλλέγουμε';

  @override
  String get dataCollectionMessage =>
      'Συνεχίζοντας, οι συνομιλίες, οι ηχογραφήσεις και οι προσωπικές σας πληροφορίες θα αποθηκευτούν με ασφάλεια στους διακομιστές μας για να παρέχουμε πληροφορίες που υποστηρίζονται από AI και να ενεργοποιήσουμε όλες τις λειτουργίες της εφαρμογής.';

  @override
  String get dataProtection => 'Προστασία Δεδομένων';

  @override
  String get yourDataIsProtected => 'Τα δεδομένα σας προστατεύονται και διέπονται από την ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'Παρακαλώ επιλέξτε την κύρια γλώσσα σας';

  @override
  String get chooseYourLanguage => 'Επιλέξτε τη γλώσσα σας';

  @override
  String get selectPreferredLanguageForBestExperience =>
      'Επιλέξτε την προτιμώμενη γλώσσα σας για την καλύτερη εμπειρία Omi';

  @override
  String get searchLanguages => 'Αναζήτηση γλωσσών...';

  @override
  String get selectALanguage => 'Επιλέξτε μια γλώσσα';

  @override
  String get tryDifferentSearchTerm => 'Δοκιμάστε έναν διαφορετικό όρο αναζήτησης';

  @override
  String get pleaseEnterYourName => 'Παρακαλώ εισάγετε το όνομά σας';

  @override
  String get nameMustBeAtLeast2Characters => 'Το όνομα πρέπει να έχει τουλάχιστον 2 χαρακτήρες';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'Πείτε μας πώς θα θέλατε να σας αποκαλούμε. Αυτό βοηθά στην εξατομίκευση της εμπειρίας Omi.';

  @override
  String charactersCount(int count) {
    return '$count χαρακτήρες';
  }

  @override
  String get enableFeaturesForBestExperience =>
      'Ενεργοποιήστε λειτουργίες για την καλύτερη εμπειρία Omi στη συσκευή σας.';

  @override
  String get microphoneAccess => 'Πρόσβαση στο μικρόφωνο';

  @override
  String get recordAudioConversations => 'Εγγραφή ηχητικών συνομιλιών';

  @override
  String get microphoneAccessDescription =>
      'Το Omi χρειάζεται πρόσβαση στο μικρόφωνο για να εγγράφει τις συνομιλίες σας και να παρέχει μεταγραφές.';

  @override
  String get screenRecording => 'Εγγραφή οθόνης';

  @override
  String get captureSystemAudioFromMeetings => 'Καταγραφή ήχου συστήματος από συναντήσεις';

  @override
  String get screenRecordingDescription =>
      'Το Omi χρειάζεται άδεια εγγραφής οθόνης για να καταγράφει τον ήχο συστήματος από τις συναντήσεις σας που βασίζονται στον περιηγητή.';

  @override
  String get accessibility => 'Προσβασιμότητα';

  @override
  String get detectBrowserBasedMeetings => 'Ανίχνευση συναντήσεων που βασίζονται στον περιηγητή';

  @override
  String get accessibilityDescription =>
      'Το Omi χρειάζεται άδεια προσβασιμότητας για να ανιχνεύει πότε συμμετέχετε σε συναντήσεις Zoom, Meet ή Teams στον περιηγητή σας.';

  @override
  String get pleaseWait => 'Παρακαλώ περιμένετε...';

  @override
  String get joinTheCommunity => 'Γίνετε μέλος της κοινότητας!';

  @override
  String get loadingProfile => 'Φόρτωση προφίλ...';

  @override
  String get profileSettings => 'Ρυθμίσεις προφίλ';

  @override
  String get noEmailSet => 'Δεν έχει οριστεί email';

  @override
  String get userIdCopiedToClipboard => 'ID χρήστη αντιγράφηκε';

  @override
  String get yourInformation => 'Οι Πληροφορίες Σας';

  @override
  String get setYourName => 'Ορίστε το όνομά σας';

  @override
  String get changeYourName => 'Αλλάξτε το όνομά σας';

  @override
  String get manageYourOmiPersona => 'Διαχειριστείτε την Omi persona σας';

  @override
  String get voiceAndPeople => 'Φωνή & Άνθρωποι';

  @override
  String get teachOmiYourVoice => 'Μάθετε στο Omi τη φωνή σας';

  @override
  String get tellOmiWhoSaidIt => 'Πείτε στο Omi ποιος το είπε 🗣️';

  @override
  String get payment => 'Πληρωμή';

  @override
  String get addOrChangeYourPaymentMethod => 'Προσθέστε ή αλλάξτε μέθοδο πληρωμής';

  @override
  String get preferences => 'Προτιμήσεις';

  @override
  String get helpImproveOmiBySharing => 'Βοηθήστε στη βελτίωση του Omi μοιράζοντας ανώνυμα δεδομένα ανάλυσης';

  @override
  String get deleteAccount => 'Διαγραφή Λογαριασμού';

  @override
  String get deleteYourAccountAndAllData => 'Διαγράψτε τον λογαριασμό και όλα τα δεδομένα σας';

  @override
  String get clearLogs => 'Εκκαθάριση αρχείων καταγραφής';

  @override
  String get debugLogsCleared => 'Αρχεία καταγραφής εντοπισμού σφαλμάτων διαγράφηκαν';

  @override
  String get exportConversations => 'Εξαγωγή συνομιλιών';

  @override
  String get exportAllConversationsToJson => 'Εξάγετε όλες τις συνομιλίες σας σε αρχείο JSON.';

  @override
  String get conversationsExportStarted =>
      'Η εξαγωγή συνομιλιών ξεκίνησε. Αυτό μπορεί να διαρκέσει μερικά δευτερόλεπτα, παρακαλώ περιμένετε.';

  @override
  String get mcpDescription =>
      'Για να συνδέσετε το Omi με άλλες εφαρμογές για να διαβάσετε, να αναζητήσετε και να διαχειριστείτε τις αναμνήσεις και τις συνομιλίες σας. Δημιουργήστε ένα κλειδί για να ξεκινήσετε.';

  @override
  String get apiKeys => 'Κλειδιά API';

  @override
  String errorLabel(String error) {
    return 'Σφάλμα: $error';
  }

  @override
  String get noApiKeysFound => 'Δεν βρέθηκαν κλειδιά API. Δημιουργήστε ένα για να ξεκινήσετε.';

  @override
  String get advancedSettings => 'Προηγμένες ρυθμίσεις';

  @override
  String get triggersWhenNewConversationCreated => 'Ενεργοποιείται όταν δημιουργείται μια νέα συνομιλία.';

  @override
  String get triggersWhenNewTranscriptReceived => 'Ενεργοποιείται όταν λαμβάνεται μια νέα μεταγραφή.';

  @override
  String get realtimeAudioBytes => 'Bytes ήχου σε πραγματικό χρόνο';

  @override
  String get triggersWhenAudioBytesReceived => 'Ενεργοποιείται όταν λαμβάνονται bytes ήχου.';

  @override
  String get everyXSeconds => 'Κάθε x δευτερόλεπτα';

  @override
  String get triggersWhenDaySummaryGenerated => 'Ενεργοποιείται όταν δημιουργείται η περίληψη της ημέρας.';

  @override
  String get tryLatestExperimentalFeatures => 'Δοκιμάστε τις πιο πρόσφατες πειραματικές λειτουργίες από την ομάδα Omi.';

  @override
  String get transcriptionServiceDiagnosticStatus => 'Κατάσταση διαγνωστικών υπηρεσίας μεταγραφής';

  @override
  String get enableDetailedDiagnosticMessages =>
      'Ενεργοποίηση λεπτομερών διαγνωστικών μηνυμάτων από την υπηρεσία μεταγραφής';

  @override
  String get autoCreateAndTagNewSpeakers => 'Αυτόματη δημιουργία και επισήμανση νέων ομιλητών';

  @override
  String get automaticallyCreateNewPerson => 'Αυτόματη δημιουργία νέου ατόμου όταν ανιχνεύεται όνομα στη μεταγραφή.';

  @override
  String get pilotFeatures => 'Πιλοτικές λειτουργίες';

  @override
  String get pilotFeaturesDescription => 'Αυτές οι λειτουργίες είναι δοκιμές και δεν εγγυάται η υποστήριξη.';

  @override
  String get suggestFollowUpQuestion => 'Προτείνετε ερώτηση παρακολούθησης';

  @override
  String get saveSettings => 'Αποθήκευση Ρυθμίσεων';

  @override
  String get syncingDeveloperSettings => 'Συγχρονισμός ρυθμίσεων προγραμματιστή...';

  @override
  String get summary => 'Περίληψη';

  @override
  String get auto => 'Αυτόματα';

  @override
  String get noSummaryForApp =>
      'Δεν υπάρχει διαθέσιμη σύνοψη για αυτήν την εφαρμογή. Δοκιμάστε μια άλλη εφαρμογή για καλύτερα αποτελέσματα.';

  @override
  String get tryAnotherApp => 'Δοκιμάστε άλλη εφαρμογή';

  @override
  String generatedBy(String appName) {
    return 'Δημιουργήθηκε από $appName';
  }

  @override
  String get overview => 'Επισκόπηση';

  @override
  String get otherAppResults => 'Αποτελέσματα άλλων εφαρμογών';

  @override
  String get unknownApp => 'Άγνωστη εφαρμογή';

  @override
  String get noSummaryAvailable => 'Δεν υπάρχει διαθέσιμη περίληψη';

  @override
  String get conversationNoSummaryYet => 'Αυτή η συνομιλία δεν έχει ακόμη περίληψη.';

  @override
  String get chooseSummarizationApp => 'Επιλέξτε εφαρμογή περίληψης';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return 'Η $appName ορίστηκε ως προεπιλεγμένη εφαρμογή περίληψης';
  }

  @override
  String get letOmiChooseAutomatically => 'Αφήστε το Omi να επιλέξει αυτόματα την καλύτερη εφαρμογή';

  @override
  String get deleteConversationConfirmation =>
      'Είστε σίγουροι ότι θέλετε να διαγράψετε αυτή τη συνομιλία; Αυτή η ενέργεια δεν μπορεί να αναιρεθεί.';

  @override
  String get conversationDeleted => 'Η συνομιλία διαγράφηκε';

  @override
  String get generatingLink => 'Δημιουργία συνδέσμου...';

  @override
  String get editConversation => 'Επεξεργασία συνομιλίας';

  @override
  String get conversationLinkCopiedToClipboard => 'Ο σύνδεσμος συνομιλίας αντιγράφηκε στο πρόχειρο';

  @override
  String get conversationTranscriptCopiedToClipboard => 'Η απομαγνητοφώνηση της συνομιλίας αντιγράφηκε στο πρόχειρο';

  @override
  String get editConversationDialogTitle => 'Επεξεργασία συνομιλίας';

  @override
  String get changeTheConversationTitle => 'Αλλαγή τίτλου συνομιλίας';

  @override
  String get conversationTitle => 'Τίτλος συνομιλίας';

  @override
  String get enterConversationTitle => 'Εισαγάγετε τίτλο συνομιλίας...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'Ο τίτλος της συνομιλίας ενημερώθηκε επιτυχώς';

  @override
  String get failedToUpdateConversationTitle => 'Αποτυχία ενημέρωσης τίτλου συνομιλίας';

  @override
  String get errorUpdatingConversationTitle => 'Σφάλμα κατά την ενημέρωση του τίτλου της συνομιλίας';

  @override
  String get settingUp => 'Ρύθμιση...';

  @override
  String get startYourFirstRecording => 'Ξεκινήστε την πρώτη σας καταγραφή';

  @override
  String get preparingSystemAudioCapture => 'Προετοιμασία καταγραφής ήχου συστήματος';

  @override
  String get clickTheButtonToCaptureAudio =>
      'Κάντε κλικ στο κουμπί για να καταγράψετε ήχο για ζωντανές μεταγραφές, πληροφορίες AI και αυτόματη αποθήκευση.';

  @override
  String get reconnecting => 'Επανασύνδεση...';

  @override
  String get recordingPaused => 'Καταγραφή σε παύση';

  @override
  String get recordingActive => 'Καταγραφή ενεργή';

  @override
  String get startRecording => 'Έναρξη καταγραφής';

  @override
  String resumingInCountdown(String countdown) {
    return 'Συνέχεια σε ${countdown}s...';
  }

  @override
  String get tapPlayToResume => 'Πατήστε αναπαραγωγή για συνέχεια';

  @override
  String get listeningForAudio => 'Ακρόαση για ήχο...';

  @override
  String get preparingAudioCapture => 'Προετοιμασία καταγραφής ήχου';

  @override
  String get clickToBeginRecording => 'Κάντε κλικ για να ξεκινήσετε την καταγραφή';

  @override
  String get translated => 'μεταφρασμένο';

  @override
  String get liveTranscript => 'Ζωντανή μεταγραφή';

  @override
  String segmentsSingular(String count) {
    return '$count τμήμα';
  }

  @override
  String segmentsPlural(String count) {
    return '$count τμήματα';
  }

  @override
  String get startRecordingToSeeTranscript => 'Ξεκινήστε την καταγραφή για να δείτε τη ζωντανή μεταγραφή';

  @override
  String get paused => 'Σε παύση';

  @override
  String get initializing => 'Αρχικοποίηση...';

  @override
  String get recording => 'Καταγραφή';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'Το μικρόφωνο άλλαξε. Συνέχεια σε ${countdown}s';
  }

  @override
  String get clickPlayToResumeOrStop => 'Κάντε κλικ στην αναπαραγωγή για συνέχεια ή στάση για ολοκλήρωση';

  @override
  String get settingUpSystemAudioCapture => 'Ρύθμιση καταγραφής ήχου συστήματος';

  @override
  String get capturingAudioAndGeneratingTranscript => 'Καταγραφή ήχου και δημιουργία μεταγραφής';

  @override
  String get clickToBeginRecordingSystemAudio => 'Κάντε κλικ για να ξεκινήσετε την καταγραφή ήχου συστήματος';

  @override
  String get you => 'Εσείς';

  @override
  String speakerWithId(String speakerId) {
    return 'Ομιλητής $speakerId';
  }

  @override
  String get translatedByOmi => 'μεταφρασμένο από omi';

  @override
  String get backToConversations => 'Επιστροφή στις συνομιλίες';

  @override
  String get systemAudio => 'Σύστημα';

  @override
  String get mic => 'Μικρόφωνο';

  @override
  String audioInputSetTo(String deviceName) {
    return 'Είσοδος ήχου ορίστηκε σε $deviceName';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'Σφάλμα εναλλαγής συσκευής ήχου: $error';
  }

  @override
  String get selectAudioInput => 'Επιλέξτε είσοδο ήχου';

  @override
  String get loadingDevices => 'Φόρτωση συσκευών...';

  @override
  String get settingsHeader => 'ΡΥΘΜΙΣΕΙΣ';

  @override
  String get plansAndBilling => 'Πλάνα & Χρέωση';

  @override
  String get calendarIntegration => 'Ενσωμάτωση Ημερολογίου';

  @override
  String get dailySummary => 'Ημερήσια σύνοψη';

  @override
  String get developer => 'Προγραμματιστής';

  @override
  String get about => 'Σχετικά';

  @override
  String get selectTime => 'Επιλογή ώρας';

  @override
  String get accountGroup => 'Λογαριασμός';

  @override
  String get signOutQuestion => 'Αποσύνδεση;';

  @override
  String get signOutConfirmation => 'Are you sure you want to sign out?';

  @override
  String get customVocabularyHeader => 'ΠΡΟΣΑΡΜΟΣΜΕΝΟ ΛΕΞΙΛΟΓΙΟ';

  @override
  String get addWordsDescription => 'Προσθέστε λέξεις που θα πρέπει να αναγνωρίζει το Omi κατά τη μεταγραφή.';

  @override
  String get enterWordsHint => 'Εισαγάγετε λέξεις (χωρισμένες με κόμματα)';

  @override
  String get dailySummaryHeader => 'ΗΜΕΡΗΣΙΑ ΠΕΡΙΛΗΨΗ';

  @override
  String get dailySummaryTitle => 'Ημερήσια Περίληψη';

  @override
  String get dailySummaryDescription => 'Λάβετε μια εξατομικευμένη σύνοψη των συνομιλιών της ημέρας σας ως ειδοποίηση.';

  @override
  String get deliveryTime => 'Ώρα παράδοσης';

  @override
  String get deliveryTimeDescription => 'Πότε να λαμβάνετε την ημερήσια περίληψή σας';

  @override
  String get subscription => 'Συνδρομή';

  @override
  String get viewPlansAndUsage => 'Προβολή Πλάνων & Χρήσης';

  @override
  String get viewPlansDescription => 'Διαχειριστείτε τη συνδρομή σας και δείτε στατιστικά χρήσης';

  @override
  String get addOrChangePaymentMethod => 'Προσθέστε ή αλλάξτε τον τρόπο πληρωμής σας';

  @override
  String get displayOptions => 'Επιλογές εμφάνισης';

  @override
  String get showMeetingsInMenuBar => 'Εμφάνιση συναντήσεων στη γραμμή μενού';

  @override
  String get displayUpcomingMeetingsDescription => 'Εμφάνιση επερχόμενων συναντήσεων στη γραμμή μενού';

  @override
  String get showEventsWithoutParticipants => 'Εμφάνιση γεγονότων χωρίς συμμετέχοντες';

  @override
  String get includePersonalEventsDescription => 'Συμπερίληψη προσωπικών γεγονότων χωρίς συμμετέχοντες';

  @override
  String get upcomingMeetings => 'Επερχόμενες συναντήσεις';

  @override
  String get checkingNext7Days => 'Έλεγχος των επόμενων 7 ημερών';

  @override
  String get shortcuts => 'Συντομεύσεις';

  @override
  String get shortcutChangeInstruction =>
      'Κάντε κλικ σε μια συντόμευση για να την αλλάξετε. Πατήστε Escape για ακύρωση.';

  @override
  String get configurePersonaDescription => 'Διαμορφώστε την προσωπικότητα AI σας';

  @override
  String get configureSTTProvider => 'Διαμόρφωση παρόχου STT';

  @override
  String get setConversationEndDescription => 'Ορίστε πότε τερματίζονται αυτόματα οι συνομιλίες';

  @override
  String get importDataDescription => 'Εισαγωγή δεδομένων από άλλες πηγές';

  @override
  String get exportConversationsDescription => 'Εξαγωγή συνομιλιών σε JSON';

  @override
  String get exportingConversations => 'Εξαγωγή συνομιλιών...';

  @override
  String get clearNodesDescription => 'Διαγραφή όλων των κόμβων και συνδέσεων';

  @override
  String get deleteKnowledgeGraphQuestion => 'Διαγραφή γράφου γνώσης;';

  @override
  String get deleteKnowledgeGraphWarning =>
      'Αυτό θα διαγράψει όλα τα παράγωγα δεδομένα γράφου γνώσης. Οι αρχικές σας αναμνήσεις παραμένουν ασφαλείς.';

  @override
  String get connectOmiWithAI => 'Συνδέστε το Omi με βοηθούς AI';

  @override
  String get noAPIKeys => 'Χωρίς κλειδιά API. Δημιουργήστε ένα για να ξεκινήσετε.';

  @override
  String get autoCreateWhenDetected => 'Αυτόματη δημιουργία όταν ανιχνευθεί όνομα';

  @override
  String get trackPersonalGoals => 'Παρακολουθήστε προσωπικούς στόχους στην αρχική σελίδα';

  @override
  String get dailyReflectionDescription =>
      'Λάβετε μια υπενθύμιση στις 9 μ.μ. για να αναστοχαστείτε την ημέρα σας και να καταγράψετε τις σκέψεις σας.';

  @override
  String get endpointURL => 'URL τελικού σημείου';

  @override
  String get links => 'Σύνδεσμοι';

  @override
  String get discordMemberCount => 'Πάνω από 8000 μέλη στο Discord';

  @override
  String get userInformation => 'Πληροφορίες χρήστη';

  @override
  String get capabilities => 'Δυνατότητες';

  @override
  String get previewScreenshots => 'Προεπισκόπηση στιγμιότυπων';

  @override
  String get holdOnPreparingForm => 'Περιμένετε, ετοιμάζουμε τη φόρμα για εσάς';

  @override
  String get bySubmittingYouAgreeToOmi => 'Με την υποβολή, συμφωνείτε με το Omi ';

  @override
  String get termsAndPrivacyPolicy => 'Όροι & Πολιτική Απορρήτου';

  @override
  String get helpsDiagnoseIssuesAutoDeletes =>
      'Βοηθά στη διάγνωση προβλημάτων. Διαγράφεται αυτόματα μετά από 3 ημέρες.';

  @override
  String get manageYourApp => 'Διαχείριση της εφαρμογής σας';

  @override
  String get updatingYourApp => 'Ενημέρωση της εφαρμογής σας';

  @override
  String get fetchingYourAppDetails => 'Ανάκτηση λεπτομερειών εφαρμογής';

  @override
  String get updateAppQuestion => 'Ενημέρωση εφαρμογής;';

  @override
  String get updateAppConfirmation =>
      'Είστε σίγουροι ότι θέλετε να ενημερώσετε την εφαρμογή σας; Οι αλλαγές θα εμφανιστούν μετά τον έλεγχο από την ομάδα μας.';

  @override
  String get updateApp => 'Ενημέρωση εφαρμογής';

  @override
  String get createAndSubmitNewApp => 'Δημιουργήστε και υποβάλετε μια νέα εφαρμογή';

  @override
  String appsCount(String count) {
    return 'Εφαρμογές ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'Ιδιωτικές εφαρμογές ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'Δημόσιες εφαρμογές ($count)';
  }

  @override
  String get newVersionAvailable => 'Νέα έκδοση διαθέσιμη  🎉';

  @override
  String get no => 'Όχι';

  @override
  String get subscriptionCancelledSuccessfully =>
      'Η συνδρομή ακυρώθηκε επιτυχώς. Θα παραμείνει ενεργή μέχρι το τέλος της τρέχουσας περιόδου χρέωσης.';

  @override
  String get failedToCancelSubscription => 'Αποτυχία ακύρωσης συνδρομής. Παρακαλώ δοκιμάστε ξανά.';

  @override
  String get invalidPaymentUrl => 'Μη έγκυρο URL πληρωμής';

  @override
  String get permissionsAndTriggers => 'Δικαιώματα & Ενεργοποιητές';

  @override
  String get chatFeatures => 'Λειτουργίες συνομιλίας';

  @override
  String get uninstall => 'Απεγκατάσταση';

  @override
  String get installs => 'ΕΓΚΑΤΑΣΤΑΣΕΙΣ';

  @override
  String get priceLabel => 'ΤΙΜΗ';

  @override
  String get updatedLabel => 'ΕΝΗΜΕΡΩΜΕΝΟ';

  @override
  String get createdLabel => 'ΔΗΜΙΟΥΡΓΗΘΗΚΕ';

  @override
  String get featuredLabel => 'ΠΡΟΤΕΙΝΟΜΕΝΟ';

  @override
  String get cancelSubscriptionQuestion => 'Ακύρωση συνδρομής;';

  @override
  String get cancelSubscriptionConfirmation =>
      'Είστε σίγουροι ότι θέλετε να ακυρώσετε τη συνδρομή σας; Θα συνεχίσετε να έχετε πρόσβαση μέχρι το τέλος της τρέχουσας περιόδου χρέωσης.';

  @override
  String get cancelSubscriptionButton => 'Ακύρωση συνδρομής';

  @override
  String get cancelling => 'Ακύρωση...';

  @override
  String get betaTesterMessage =>
      'Είστε δοκιμαστής beta για αυτήν την εφαρμογή. Δεν είναι ακόμα δημόσια. Θα γίνει δημόσια μετά την έγκριση.';

  @override
  String get appUnderReviewMessage =>
      'Η εφαρμογή σας είναι υπό αξιολόγηση και ορατή μόνο σε εσάς. Θα γίνει δημόσια μετά την έγκριση.';

  @override
  String get appRejectedMessage =>
      'Η εφαρμογή σας απορρίφθηκε. Ενημερώστε τα στοιχεία και υποβάλετε ξανά για αξιολόγηση.';

  @override
  String get invalidIntegrationUrl => 'Μη έγκυρη διεύθυνση URL ενσωμάτωσης';

  @override
  String get tapToComplete => 'Πατήστε για ολοκλήρωση';

  @override
  String get invalidSetupInstructionsUrl => 'Μη έγκυρη διεύθυνση URL οδηγιών ρύθμισης';

  @override
  String get pushToTalk => 'Πατήστε για ομιλία';

  @override
  String get summaryPrompt => 'Προτροπή σύνοψης';

  @override
  String get pleaseSelectARating => 'Παρακαλώ επιλέξτε βαθμολογία';

  @override
  String get reviewAddedSuccessfully => 'Η κριτική προστέθηκε επιτυχώς 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'Η κριτική ενημερώθηκε επιτυχώς 🚀';

  @override
  String get failedToSubmitReview => 'Αποτυχία υποβολής κριτικής. Δοκιμάστε ξανά.';

  @override
  String get addYourReview => 'Προσθέστε την κριτική σας';

  @override
  String get editYourReview => 'Επεξεργαστείτε την κριτική σας';

  @override
  String get writeAReviewOptional => 'Γράψτε μια κριτική (προαιρετικό)';

  @override
  String get submitReview => 'Υποβολή κριτικής';

  @override
  String get updateReview => 'Ενημέρωση κριτικής';

  @override
  String get yourReview => 'Η κριτική σας';

  @override
  String get anonymousUser => 'Ανώνυμος χρήστης';

  @override
  String get issueActivatingApp =>
      'Υπήρξε πρόβλημα κατά την ενεργοποίηση αυτής της εφαρμογής. Παρακαλώ δοκιμάστε ξανά.';

  @override
  String get dataAccessNoticeDescription =>
      'This app will access your data. Omi AI is not responsible for how your data is used, modified, or deleted by this app';

  @override
  String get copyUrl => 'Αντιγραφή URL';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => 'Δευ';

  @override
  String get weekdayTue => 'Τρί';

  @override
  String get weekdayWed => 'Τετ';

  @override
  String get weekdayThu => 'Πέμ';

  @override
  String get weekdayFri => 'Παρ';

  @override
  String get weekdaySat => 'Σάβ';

  @override
  String get weekdaySun => 'Κυρ';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return 'Ενσωμάτωση $serviceName σύντομα';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'Ήδη εξαγωγή σε $platform';
  }

  @override
  String get anotherPlatform => 'άλλη πλατφόρμα';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'Παρακαλώ συνδεθείτε με $serviceName στις Ρυθμίσεις > Ενσωματώσεις εργασιών';
  }

  @override
  String addingToService(String serviceName) {
    return 'Προσθήκη σε $serviceName...';
  }

  @override
  String addedToService(String serviceName) {
    return 'Προστέθηκε στο $serviceName';
  }

  @override
  String failedToAddToService(String serviceName) {
    return 'Αποτυχία προσθήκης στο $serviceName';
  }

  @override
  String get permissionDeniedForAppleReminders => 'Η άδεια για τις Υπενθυμίσεις Apple απορρίφθηκε';

  @override
  String failedToCreateApiKey(String error) {
    return 'Αποτυχία δημιουργίας κλειδιού API παρόχου: $error';
  }

  @override
  String get createAKey => 'Δημιουργία κλειδιού';

  @override
  String get apiKeyRevokedSuccessfully => 'Το κλειδί API ανακλήθηκε επιτυχώς';

  @override
  String failedToRevokeApiKey(String error) {
    return 'Αποτυχία ανάκλησης κλειδιού API: $error';
  }

  @override
  String get omiApiKeys => 'Κλειδιά API Omi';

  @override
  String get apiKeysDescription =>
      'Τα κλειδιά API χρησιμοποιούνται για έλεγχο ταυτότητας όταν η εφαρμογή σας επικοινωνεί με τον διακομιστή OMI. Επιτρέπουν στην εφαρμογή σας να δημιουργεί αναμνήσεις και να έχει ασφαλή πρόσβαση σε άλλες υπηρεσίες OMI.';

  @override
  String get aboutOmiApiKeys => 'Σχετικά με τα κλειδιά API Omi';

  @override
  String get yourNewKey => 'Το νέο σας κλειδί:';

  @override
  String get copyToClipboard => 'Αντιγραφή στο πρόχειρο';

  @override
  String get pleaseCopyKeyNow => 'Παρακαλούμε αντιγράψτε το τώρα και σημειώστε το κάπου ασφαλές. ';

  @override
  String get willNotSeeAgain => 'Δεν θα μπορείτε να το δείτε ξανά.';

  @override
  String get revokeKey => 'Ανάκληση κλειδιού';

  @override
  String get revokeApiKeyQuestion => 'Ανάκληση κλειδιού API;';

  @override
  String get revokeApiKeyWarning =>
      'Αυτή η ενέργεια δεν μπορεί να αναιρεθεί. Οι εφαρμογές που χρησιμοποιούν αυτό το κλειδί δεν θα έχουν πλέον πρόσβαση στο API.';

  @override
  String get revoke => 'Ανάκληση';

  @override
  String get whatWouldYouLikeToCreate => 'Τι θα θέλατε να δημιουργήσετε;';

  @override
  String get createAnApp => 'Δημιουργία εφαρμογής';

  @override
  String get createAndShareYourApp => 'Δημιουργήστε και μοιραστείτε την εφαρμογή σας';

  @override
  String get createMyClone => 'Δημιουργία του κλώνου μου';

  @override
  String get createYourDigitalClone => 'Δημιουργήστε τον ψηφιακό σας κλώνο';

  @override
  String get itemApp => 'Εφαρμογή';

  @override
  String get itemPersona => 'Περσόνα';

  @override
  String keepItemPublic(String item) {
    return 'Διατήρηση $item δημόσιο';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return 'Δημοσιοποίηση $item;';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return 'Ιδιωτικοποίηση $item;';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'Αν κάνετε το $item δημόσιο, μπορεί να χρησιμοποιηθεί από όλους';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'Αν κάνετε το $item ιδιωτικό τώρα, θα σταματήσει να λειτουργεί για όλους και θα είναι ορατό μόνο σε εσάς';
  }

  @override
  String get manageApp => 'Διαχείριση εφαρμογής';

  @override
  String get updatePersonaDetails => 'Ενημέρωση στοιχείων περσόνας';

  @override
  String deleteItemTitle(String item) {
    return 'Διαγραφή $item';
  }

  @override
  String deleteItemQuestion(String item) {
    return 'Διαγραφή $item;';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'Είστε βέβαιοι ότι θέλετε να διαγράψετε αυτό το $item; Αυτή η ενέργεια δεν μπορεί να αναιρεθεί.';
  }

  @override
  String get revokeKeyQuestion => 'Ανάκληση κλειδιού;';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'Είστε βέβαιοι ότι θέλετε να ανακαλέσετε το κλειδί \"$keyName\"; Αυτή η ενέργεια δεν μπορεί να αναιρεθεί.';
  }

  @override
  String get createNewKey => 'Δημιουργία νέου κλειδιού';

  @override
  String get keyNameHint => 'π.χ. Claude Desktop';

  @override
  String get pleaseEnterAName => 'Παρακαλώ εισάγετε ένα όνομα.';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'Αποτυχία δημιουργίας κλειδιού: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'Αποτυχία δημιουργίας κλειδιού. Παρακαλώ δοκιμάστε ξανά.';

  @override
  String get keyCreated => 'Το κλειδί δημιουργήθηκε';

  @override
  String get keyCreatedMessage =>
      'Το νέο σας κλειδί δημιουργήθηκε. Παρακαλώ αντιγράψτε το τώρα. Δεν θα μπορείτε να το δείτε ξανά.';

  @override
  String get keyWord => 'Κλειδί';

  @override
  String get externalAppAccess => 'Πρόσβαση εξωτερικών εφαρμογών';

  @override
  String get externalAppAccessDescription =>
      'Οι παρακάτω εγκατεστημένες εφαρμογές έχουν εξωτερικές ενσωματώσεις και μπορούν να έχουν πρόσβαση στα δεδομένα σας, όπως συνομιλίες και αναμνήσεις.';

  @override
  String get noExternalAppsHaveAccess => 'Καμία εξωτερική εφαρμογή δεν έχει πρόσβαση στα δεδομένα σας.';

  @override
  String get maximumSecurityE2ee => 'Μέγιστη ασφάλεια (E2EE)';

  @override
  String get e2eeDescription =>
      'Η κρυπτογράφηση από άκρο σε άκρο είναι το χρυσό πρότυπο για την ιδιωτικότητα. Όταν είναι ενεργοποιημένη, τα δεδομένα σας κρυπτογραφούνται στη συσκευή σας πριν σταλούν στους διακομιστές μας. Αυτό σημαίνει ότι κανείς, ούτε καν η Omi, δεν μπορεί να έχει πρόσβαση στο περιεχόμενό σας.';

  @override
  String get importantTradeoffs => 'Σημαντικοί συμβιβασμοί:';

  @override
  String get e2eeTradeoff1 =>
      '• Ορισμένες λειτουργίες όπως οι ενσωματώσεις εξωτερικών εφαρμογών ενδέχεται να απενεργοποιηθούν.';

  @override
  String get e2eeTradeoff2 => '• Εάν χάσετε τον κωδικό πρόσβασής σας, τα δεδομένα σας δεν μπορούν να ανακτηθούν.';

  @override
  String get featureComingSoon => 'Αυτή η λειτουργία έρχεται σύντομα!';

  @override
  String get migrationInProgressMessage =>
      'Μετανάστευση σε εξέλιξη. Δεν μπορείτε να αλλάξετε το επίπεδο προστασίας μέχρι να ολοκληρωθεί.';

  @override
  String get migrationFailed => 'Η μετανάστευση απέτυχε';

  @override
  String migratingFromTo(String source, String target) {
    return 'Μετανάστευση από $source σε $target';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total αντικείμενα';
  }

  @override
  String get secureEncryption => 'Ασφαλής κρυπτογράφηση';

  @override
  String get secureEncryptionDescription =>
      'Τα δεδομένα σας κρυπτογραφούνται με ένα μοναδικό κλειδί για εσάς στους διακομιστές μας, που φιλοξενούνται στο Google Cloud. Αυτό σημαίνει ότι το ακατέργαστο περιεχόμενό σας είναι απρόσιτο σε οποιονδήποτε, συμπεριλαμβανομένου του προσωπικού της Omi ή της Google, απευθείας από τη βάση δεδομένων.';

  @override
  String get endToEndEncryption => 'Κρυπτογράφηση από άκρο σε άκρο';

  @override
  String get e2eeCardDescription =>
      'Ενεργοποιήστε για μέγιστη ασφάλεια όπου μόνο εσείς έχετε πρόσβαση στα δεδομένα σας. Πατήστε για να μάθετε περισσότερα.';

  @override
  String get dataAlwaysEncrypted =>
      'Ανεξάρτητα από το επίπεδο, τα δεδομένα σας είναι πάντα κρυπτογραφημένα σε κατάσταση ηρεμίας και κατά τη μεταφορά.';

  @override
  String get readOnlyScope => 'Μόνο ανάγνωση';

  @override
  String get fullAccessScope => 'Πλήρης πρόσβαση';

  @override
  String get readScope => 'Ανάγνωση';

  @override
  String get writeScope => 'Εγγραφή';

  @override
  String get apiKeyCreated => 'Το κλειδί API δημιουργήθηκε!';

  @override
  String get saveKeyWarning => 'Αποθηκεύστε αυτό το κλειδί τώρα! Δεν θα μπορείτε να το δείτε ξανά.';

  @override
  String get yourApiKey => 'ΤΟ ΚΛΕΙΔΙ API ΣΑΣ';

  @override
  String get tapToCopy => 'Πατήστε για αντιγραφή';

  @override
  String get copyKey => 'Αντιγραφή κλειδιού';

  @override
  String get createApiKey => 'Δημιουργία κλειδιού API';

  @override
  String get accessDataProgrammatically => 'Πρόσβαση στα δεδομένα σας μέσω προγραμματισμού';

  @override
  String get keyNameLabel => 'ΟΝΟΜΑ ΚΛΕΙΔΙΟΥ';

  @override
  String get keyNamePlaceholder => 'π.χ., Η ενσωμάτωσή μου';

  @override
  String get permissionsLabel => 'ΔΙΚΑΙΩΜΑΤΑ';

  @override
  String get permissionsInfoNote => 'R = Ανάγνωση, W = Εγγραφή. Προεπιλογή μόνο ανάγνωση αν δεν επιλεγεί τίποτα.';

  @override
  String get developerApi => 'API προγραμματιστών';

  @override
  String get createAKeyToGetStarted => 'Δημιουργήστε ένα κλειδί για να ξεκινήσετε';

  @override
  String errorWithMessage(String error) {
    return 'Σφάλμα: $error';
  }

  @override
  String get omiTraining => 'Εκπαίδευση Omi';

  @override
  String get trainingDataProgram => 'Πρόγραμμα δεδομένων εκπαίδευσης';

  @override
  String get getOmiUnlimitedFree =>
      'Αποκτήστε το Omi Unlimited δωρεάν συνεισφέροντας τα δεδομένα σας για την εκπαίδευση μοντέλων AI.';

  @override
  String get trainingDataBullets =>
      '• Τα δεδομένα σας βοηθούν στη βελτίωση των μοντέλων AI\n• Μοιράζονται μόνο μη ευαίσθητα δεδομένα\n• Πλήρως διαφανής διαδικασία';

  @override
  String get learnMoreAtOmiTraining => 'Μάθετε περισσότερα στο omi.me/training';

  @override
  String get agreeToContributeData => 'Κατανοώ και συμφωνώ να συνεισφέρω τα δεδομένα μου για εκπαίδευση AI';

  @override
  String get submitRequest => 'Υποβολή αιτήματος';

  @override
  String get thankYouRequestUnderReview =>
      'Ευχαριστούμε! Το αίτημά σας εξετάζεται. Θα σας ειδοποιήσουμε μόλις εγκριθεί.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'Το πρόγραμμά σας θα παραμείνει ενεργό μέχρι $date. Μετά από αυτό, θα χάσετε την πρόσβαση στις απεριόριστες λειτουργίες. Είστε σίγουροι;';
  }

  @override
  String get confirmCancellation => 'Επιβεβαίωση ακύρωσης';

  @override
  String get keepMyPlan => 'Διατήρηση του προγράμματός μου';

  @override
  String get subscriptionSetToCancel => 'Η συνδρομή σας έχει ρυθμιστεί να ακυρωθεί στο τέλος της περιόδου.';

  @override
  String get switchedToOnDevice => 'Αλλαγή σε μεταγραφή στη συσκευή';

  @override
  String get couldNotSwitchToFreePlan => 'Δεν ήταν δυνατή η αλλαγή σε δωρεάν πρόγραμμα. Παρακαλώ δοκιμάστε ξανά.';

  @override
  String get couldNotLoadPlans => 'Δεν ήταν δυνατή η φόρτωση διαθέσιμων προγραμμάτων. Παρακαλώ δοκιμάστε ξανά.';

  @override
  String get selectedPlanNotAvailable => 'Το επιλεγμένο πρόγραμμα δεν είναι διαθέσιμο. Παρακαλώ δοκιμάστε ξανά.';

  @override
  String get upgradeToAnnualPlan => 'Αναβάθμιση σε ετήσιο πρόγραμμα';

  @override
  String get importantBillingInfo => 'Σημαντικές πληροφορίες χρέωσης:';

  @override
  String get monthlyPlanContinues =>
      'Το τρέχον μηνιαίο σας πρόγραμμα θα συνεχιστεί μέχρι το τέλος της περιόδου χρέωσης';

  @override
  String get paymentMethodCharged =>
      'Ο υπάρχων τρόπος πληρωμής σας θα χρεωθεί αυτόματα όταν λήξει το μηνιαίο σας πρόγραμμα';

  @override
  String get annualSubscriptionStarts => 'Η 12μηνη ετήσια συνδρομή σας θα ξεκινήσει αυτόματα μετά τη χρέωση';

  @override
  String get thirteenMonthsCoverage => 'Θα λάβετε συνολικά 13 μήνες κάλυψης (τρέχων μήνας + 12 μήνες ετησίως)';

  @override
  String get confirmUpgrade => 'Επιβεβαίωση αναβάθμισης';

  @override
  String get confirmPlanChange => 'Επιβεβαίωση αλλαγής προγράμματος';

  @override
  String get confirmAndProceed => 'Επιβεβαίωση και συνέχεια';

  @override
  String get upgradeScheduled => 'Η αναβάθμιση προγραμματίστηκε';

  @override
  String get changePlan => 'Αλλαγή προγράμματος';

  @override
  String get upgradeAlreadyScheduled => 'Η αναβάθμισή σας στο ετήσιο πρόγραμμα έχει ήδη προγραμματιστεί';

  @override
  String get youAreOnUnlimitedPlan => 'Είστε στο Απεριόριστο Πρόγραμμα.';

  @override
  String get yourOmiUnleashed => 'Το Omi σας, απελευθερωμένο. Γίνετε απεριόριστοι για ατελείωτες δυνατότητες.';

  @override
  String planEndedOn(String date) {
    return 'Το πρόγραμμά σας έληξε στις $date.\\nΕπανεγγραφείτε τώρα - θα χρεωθείτε αμέσως για μια νέα περίοδο χρέωσης.';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'Το πρόγραμμά σας έχει ρυθμιστεί να ακυρωθεί στις $date.\\nΕπανεγγραφείτε τώρα για να διατηρήσετε τα οφέλη σας - χωρίς χρέωση μέχρι $date.';
  }

  @override
  String get annualPlanStartsAutomatically =>
      'Το ετήσιο πρόγραμμά σας θα ξεκινήσει αυτόματα όταν λήξει το μηνιαίο σας πρόγραμμα.';

  @override
  String planRenewsOn(String date) {
    return 'Το πρόγραμμά σας ανανεώνεται στις $date.';
  }

  @override
  String get unlimitedConversations => 'Απεριόριστες συνομιλίες';

  @override
  String get askOmiAnything => 'Ρωτήστε το Omi οτιδήποτε για τη ζωή σας';

  @override
  String get unlockOmiInfiniteMemory => 'Ξεκλειδώστε την άπειρη μνήμη του Omi';

  @override
  String get youreOnAnnualPlan => 'Είστε στο ετήσιο πρόγραμμα';

  @override
  String get alreadyBestValuePlan => 'Έχετε ήδη το πρόγραμμα με την καλύτερη αξία. Δεν χρειάζονται αλλαγές.';

  @override
  String get unableToLoadPlans => 'Αδυναμία φόρτωσης προγραμμάτων';

  @override
  String get checkConnectionTryAgain => 'Ελέγξτε τη σύνδεσή σας και δοκιμάστε ξανά';

  @override
  String get useFreePlan => 'Χρήση δωρεάν προγράμματος';

  @override
  String get continueText => 'Συνέχεια';

  @override
  String get resubscribe => 'Επανεγγραφή';

  @override
  String get couldNotOpenPaymentSettings =>
      'Δεν ήταν δυνατό το άνοιγμα των ρυθμίσεων πληρωμής. Παρακαλώ δοκιμάστε ξανά.';

  @override
  String get managePaymentMethod => 'Διαχείριση μεθόδου πληρωμής';

  @override
  String get cancelSubscription => 'Ακύρωση συνδρομής';

  @override
  String endsOnDate(String date) {
    return 'Λήγει στις $date';
  }

  @override
  String get active => 'Ενεργό';

  @override
  String get freePlan => 'Δωρεάν πρόγραμμα';

  @override
  String get configure => 'Ρύθμιση';

  @override
  String get privacyInformation => 'Πληροφορίες απορρήτου';

  @override
  String get yourPrivacyMattersToUs => 'Το απόρρητό σας μας ενδιαφέρει';

  @override
  String get privacyIntroText =>
      'Στην Omi, λαμβάνουμε πολύ σοβαρά το απόρρητό σας. Θέλουμε να είμαστε διαφανείς σχετικά με τα δεδομένα που συλλέγουμε και πώς τα χρησιμοποιούμε. Ορίστε τι πρέπει να γνωρίζετε:';

  @override
  String get whatWeTrack => 'Τι παρακολουθούμε';

  @override
  String get anonymityAndPrivacy => 'Ανωνυμία και απόρρητο';

  @override
  String get optInAndOptOutOptions => 'Επιλογές συμμετοχής και εξαίρεσης';

  @override
  String get ourCommitment => 'Η δέσμευσή μας';

  @override
  String get commitmentText =>
      'Δεσμευόμαστε να χρησιμοποιούμε τα δεδομένα που συλλέγουμε μόνο για να κάνουμε το Omi καλύτερο προϊόν για εσάς. Το απόρρητο και η εμπιστοσύνη σας είναι υψίστης σημασίας για εμάς.';

  @override
  String get thankYouText =>
      'Σας ευχαριστούμε που είστε πολύτιμος χρήστης του Omi. Εάν έχετε ερωτήσεις ή ανησυχίες, μη διστάσετε να επικοινωνήσετε μαζί μας στο team@basedhardware.com.';

  @override
  String get wifiSyncSettings => 'Ρυθμίσεις συγχρονισμού WiFi';

  @override
  String get enterHotspotCredentials => 'Εισάγετε τα διαπιστευτήρια hotspot του τηλεφώνου σας';

  @override
  String get wifiSyncUsesHotspot =>
      'Ο συγχρονισμός WiFi χρησιμοποιεί το τηλέφωνό σας ως hotspot. Βρείτε το όνομα και τον κωδικό στις Ρυθμίσεις > Προσωπικό Hotspot.';

  @override
  String get hotspotNameSsid => 'Όνομα Hotspot (SSID)';

  @override
  String get exampleIphoneHotspot => 'π.χ. iPhone Hotspot';

  @override
  String get password => 'Κωδικός';

  @override
  String get enterHotspotPassword => 'Εισάγετε κωδικό hotspot';

  @override
  String get saveCredentials => 'Αποθήκευση διαπιστευτηρίων';

  @override
  String get clearCredentials => 'Εκκαθάριση διαπιστευτηρίων';

  @override
  String get pleaseEnterHotspotName => 'Παρακαλώ εισάγετε ένα όνομα hotspot';

  @override
  String get wifiCredentialsSaved => 'Τα διαπιστευτήρια WiFi αποθηκεύτηκαν';

  @override
  String get wifiCredentialsCleared => 'Τα διαπιστευτήρια WiFi διαγράφηκαν';

  @override
  String summaryGeneratedForDate(String date) {
    return 'Δημιουργήθηκε σύνοψη για $date';
  }

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'Αποτυχία δημιουργίας σύνοψης. Βεβαιωθείτε ότι έχετε συνομιλίες για εκείνη την ημέρα.';

  @override
  String get summaryNotFound => 'Η σύνοψη δεν βρέθηκε';

  @override
  String get yourDaysJourney => 'Η διαδρομή της ημέρας σας';

  @override
  String get highlights => 'Κυριότερα σημεία';

  @override
  String get unresolvedQuestions => 'Ανεπίλυτες ερωτήσεις';

  @override
  String get decisions => 'Αποφάσεις';

  @override
  String get learnings => 'Διδάγματα';

  @override
  String get autoDeletesAfterThreeDays => 'Αυτόματη διαγραφή μετά από 3 ημέρες.';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'Ο γράφος γνώσεων διαγράφηκε επιτυχώς';

  @override
  String get exportStartedMayTakeFewSeconds => 'Η εξαγωγή ξεκίνησε. Αυτό μπορεί να διαρκέσει λίγα δευτερόλεπτα...';

  @override
  String get knowledgeGraphDeleteDescription =>
      'Αυτό θα διαγράψει όλα τα παράγωγα δεδομένα του γράφου γνώσεων (κόμβους και συνδέσεις). Οι αρχικές σας αναμνήσεις θα παραμείνουν ασφαλείς. Ο γράφος θα ανακατασκευαστεί σταδιακά ή κατόπιν αιτήματος.';

  @override
  String get configureDailySummaryDigest => 'Διαμορφώστε την καθημερινή σύνοψη εργασιών σας';

  @override
  String accessesDataTypes(String dataTypes) {
    return 'Πρόσβαση σε $dataTypes';
  }

  @override
  String triggeredByType(String triggerType) {
    return 'ενεργοποιείται από $triggerType';
  }

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription και είναι $triggerDescription.';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return 'Είναι $triggerDescription.';
  }

  @override
  String get noSpecificDataAccessConfigured => 'Δεν έχει ρυθμιστεί συγκεκριμένη πρόσβαση δεδομένων.';

  @override
  String get basicPlanDescription => '1.200 premium λεπτά + απεριόριστα στη συσκευή';

  @override
  String get minutes => 'λεπτά';

  @override
  String get omiHas => 'Το Omi έχει:';

  @override
  String get premiumMinutesUsed => 'Χρησιμοποιήθηκαν τα premium λεπτά.';

  @override
  String get setupOnDevice => 'Ρύθμιση στη συσκευή';

  @override
  String get forUnlimitedFreeTranscription => 'για απεριόριστη δωρεάν μεταγραφή.';

  @override
  String premiumMinsLeft(int count) {
    return '$count premium λεπτά απομένουν.';
  }

  @override
  String get alwaysAvailable => 'πάντα διαθέσιμο.';

  @override
  String get importHistory => 'Ιστορικό εισαγωγής';

  @override
  String get noImportsYet => 'Δεν υπάρχουν εισαγωγές ακόμα';

  @override
  String get selectZipFileToImport => 'Επιλέξτε το αρχείο .zip για εισαγωγή!';

  @override
  String get otherDevicesComingSoon => 'Άλλες συσκευές έρχονται σύντομα';

  @override
  String get deleteAllLimitlessConversations => 'Διαγραφή όλων των συνομιλιών Limitless;';

  @override
  String get deleteAllLimitlessWarning =>
      'Αυτό θα διαγράψει μόνιμα όλες τις συνομιλίες που εισήχθησαν από το Limitless. Αυτή η ενέργεια δεν μπορεί να αναιρεθεί.';

  @override
  String deletedLimitlessConversations(int count) {
    return 'Διαγράφηκαν $count συνομιλίες Limitless';
  }

  @override
  String get failedToDeleteConversations => 'Αποτυχία διαγραφής συνομιλιών';

  @override
  String get deleteImportedData => 'Διαγραφή εισαγόμενων δεδομένων';

  @override
  String get statusPending => 'Εκκρεμεί';

  @override
  String get statusProcessing => 'Επεξεργασία';

  @override
  String get statusCompleted => 'Ολοκληρώθηκε';

  @override
  String get statusFailed => 'Απέτυχε';

  @override
  String nConversations(int count) {
    return '$count συνομιλίες';
  }

  @override
  String get pleaseEnterName => 'Παρακαλώ εισάγετε ένα όνομα';

  @override
  String get nameMustBeBetweenCharacters => 'Το όνομα πρέπει να έχει 2 έως 40 χαρακτήρες';

  @override
  String get deleteSampleQuestion => 'Διαγραφή δείγματος;';

  @override
  String deleteSampleConfirmation(String name) {
    return 'Είστε βέβαιοι ότι θέλετε να διαγράψετε το δείγμα του $name;';
  }

  @override
  String get confirmDeletion => 'Επιβεβαίωση διαγραφής';

  @override
  String deletePersonConfirmation(String name) {
    return 'Είστε βέβαιοι ότι θέλετε να διαγράψετε τον/την $name; Αυτό θα αφαιρέσει επίσης όλα τα σχετικά δείγματα ομιλίας.';
  }

  @override
  String get howItWorksTitle => 'Πώς λειτουργεί;';

  @override
  String get howPeopleWorks =>
      'Μόλις δημιουργηθεί ένα άτομο, μπορείτε να μεταβείτε σε μια μεταγραφή συνομιλίας και να του αντιστοιχίσετε τα αντίστοιχα τμήματα, έτσι το Omi θα μπορεί να αναγνωρίζει και τη δική του ομιλία!';

  @override
  String get tapToDelete => 'Πατήστε για διαγραφή';

  @override
  String get newTag => 'ΝΕΟ';

  @override
  String get needHelpChatWithUs => 'Χρειάζεστε βοήθεια; Συνομιλήστε μαζί μας';

  @override
  String get localStorageEnabled => 'Η τοπική αποθήκευση ενεργοποιήθηκε';

  @override
  String get localStorageDisabled => 'Η τοπική αποθήκευση απενεργοποιήθηκε';

  @override
  String failedToUpdateSettings(String error) {
    return 'Αποτυχία ενημέρωσης ρυθμίσεων: $error';
  }

  @override
  String get privacyNotice => 'Ειδοποίηση απορρήτου';

  @override
  String get recordingsMayCaptureOthers =>
      'Οι εγγραφές μπορεί να καταγράψουν φωνές άλλων. Βεβαιωθείτε ότι έχετε τη συγκατάθεση όλων των συμμετεχόντων πριν την ενεργοποίηση.';

  @override
  String get enable => 'Ενεργοποίηση';

  @override
  String get storeAudioOnPhone => 'Store Audio on Phone';

  @override
  String get on => 'On';

  @override
  String get storeAudioDescription =>
      'Διατηρήστε όλες τις ηχογραφήσεις αποθηκευμένες τοπικά στο τηλέφωνό σας. Όταν είναι απενεργοποιημένο, διατηρούνται μόνο οι αποτυχημένες μεταφορτώσεις για εξοικονόμηση χώρου.';

  @override
  String get enableLocalStorage => 'Ενεργοποίηση τοπικής αποθήκευσης';

  @override
  String get cloudStorageEnabled => 'Η αποθήκευση στο cloud ενεργοποιήθηκε';

  @override
  String get cloudStorageDisabled => 'Η αποθήκευση στο cloud απενεργοποιήθηκε';

  @override
  String get enableCloudStorage => 'Ενεργοποίηση αποθήκευσης στο cloud';

  @override
  String get storeAudioOnCloud => 'Store Audio on Cloud';

  @override
  String get cloudStorageDialogMessage =>
      'Οι εγγραφές σας σε πραγματικό χρόνο θα αποθηκεύονται σε ιδιωτικό χώρο αποθήκευσης cloud καθώς μιλάτε.';

  @override
  String get storeAudioCloudDescription =>
      'Αποθηκεύστε τις εγγραφές σας σε πραγματικό χρόνο σε ιδιωτικό χώρο αποθήκευσης cloud καθώς μιλάτε. Ο ήχος καταγράφεται και αποθηκεύεται με ασφάλεια σε πραγματικό χρόνο.';

  @override
  String get downloadingFirmware => 'Λήψη υλικολογισμικού';

  @override
  String get installingFirmware => 'Εγκατάσταση υλικολογισμικού';

  @override
  String get firmwareUpdateWarning =>
      'Μην κλείσετε την εφαρμογή ή απενεργοποιήσετε τη συσκευή. Αυτό μπορεί να καταστρέψει τη συσκευή σας.';

  @override
  String get firmwareUpdated => 'Το υλικολογισμικό ενημερώθηκε';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'Κάντε επανεκκίνηση της συσκευής $deviceName για να ολοκληρωθεί η ενημέρωση.';
  }

  @override
  String get yourDeviceIsUpToDate => 'Η συσκευή σας είναι ενημερωμένη';

  @override
  String get currentVersion => 'Τρέχουσα έκδοση';

  @override
  String get latestVersion => 'Τελευταία έκδοση';

  @override
  String get whatsNew => 'Τι νέο υπάρχει';

  @override
  String get installUpdate => 'Εγκατάσταση ενημέρωσης';

  @override
  String get updateNow => 'Ενημέρωση τώρα';

  @override
  String get updateGuide => 'Οδηγός ενημέρωσης';

  @override
  String get checkingForUpdates => 'Έλεγχος για ενημερώσεις';

  @override
  String get checkingFirmwareVersion => 'Έλεγχος έκδοσης υλικολογισμικού...';

  @override
  String get firmwareUpdate => 'Ενημέρωση υλικολογισμικού';

  @override
  String get payments => 'Πληρωμές';

  @override
  String get connectPaymentMethodInfo =>
      'Συνδέστε μια μέθοδο πληρωμής παρακάτω για να αρχίσετε να λαμβάνετε πληρωμές για τις εφαρμογές σας.';

  @override
  String get selectedPaymentMethod => 'Επιλεγμένη μέθοδος πληρωμής';

  @override
  String get availablePaymentMethods => 'Διαθέσιμες μέθοδοι πληρωμής';

  @override
  String get activeStatus => 'Ενεργό';

  @override
  String get connectedStatus => 'Συνδεδεμένο';

  @override
  String get notConnectedStatus => 'Δεν έχει συνδεθεί';

  @override
  String get setActive => 'Ορισμός ως ενεργό';

  @override
  String get getPaidThroughStripe => 'Λάβετε πληρωμή για τις πωλήσεις της εφαρμογής σας μέσω Stripe';

  @override
  String get monthlyPayouts => 'Μηνιαίες πληρωμές';

  @override
  String get monthlyPayoutsDescription =>
      'Λάβετε μηνιαίες πληρωμές απευθείας στον λογαριασμό σας όταν φτάσετε τα \$10 σε κέρδη';

  @override
  String get secureAndReliable => 'Ασφαλές και αξιόπιστο';

  @override
  String get stripeSecureDescription =>
      'Το Stripe εξασφαλίζει ασφαλείς και έγκαιρες μεταφορές των εσόδων της εφαρμογής σας';

  @override
  String get selectYourCountry => 'Επιλέξτε τη χώρα σας';

  @override
  String get countrySelectionPermanent => 'Η επιλογή χώρας είναι μόνιμη και δεν μπορεί να αλλάξει αργότερα.';

  @override
  String get byClickingConnectNow => 'Κάνοντας κλικ στο \"Σύνδεση τώρα\" συμφωνείτε με';

  @override
  String get stripeConnectedAccountAgreement => 'Συμφωνία Συνδεδεμένου Λογαριασμού Stripe';

  @override
  String get errorConnectingToStripe => 'Σφάλμα σύνδεσης με το Stripe! Παρακαλώ δοκιμάστε ξανά αργότερα.';

  @override
  String get connectingYourStripeAccount => 'Σύνδεση του λογαριασμού Stripe σας';

  @override
  String get stripeOnboardingInstructions =>
      'Παρακαλώ ολοκληρώστε τη διαδικασία εγγραφής Stripe στον browser σας. Αυτή η σελίδα θα ενημερωθεί αυτόματα μετά την ολοκλήρωση.';

  @override
  String get failedTryAgain => 'Απέτυχε; Δοκιμάστε ξανά';

  @override
  String get illDoItLater => 'Θα το κάνω αργότερα';

  @override
  String get successfullyConnected => 'Επιτυχής σύνδεση!';

  @override
  String get stripeReadyForPayments =>
      'Ο λογαριασμός Stripe σας είναι τώρα έτοιμος να λαμβάνει πληρωμές. Μπορείτε να αρχίσετε να κερδίζετε από τις πωλήσεις των εφαρμογών σας αμέσως.';

  @override
  String get updateStripeDetails => 'Ενημέρωση στοιχείων Stripe';

  @override
  String get errorUpdatingStripeDetails => 'Σφάλμα ενημέρωσης στοιχείων Stripe! Παρακαλώ δοκιμάστε ξανά αργότερα.';

  @override
  String get updatePayPal => 'Ενημέρωση PayPal';

  @override
  String get setUpPayPal => 'Ρύθμιση PayPal';

  @override
  String get updatePayPalAccountDetails => 'Ενημερώστε τα στοιχεία του λογαριασμού PayPal σας';

  @override
  String get connectPayPalToReceivePayments =>
      'Συνδέστε τον λογαριασμό PayPal σας για να αρχίσετε να λαμβάνετε πληρωμές για τις εφαρμογές σας';

  @override
  String get paypalEmail => 'Email PayPal';

  @override
  String get paypalMeLink => 'Σύνδεσμος PayPal.me';

  @override
  String get stripeRecommendation =>
      'Εάν το Stripe είναι διαθέσιμο στη χώρα σας, σας συνιστούμε ανεπιφύλακτα να το χρησιμοποιήσετε για ταχύτερες και ευκολότερες πληρωμές.';

  @override
  String get updatePayPalDetails => 'Ενημέρωση στοιχείων PayPal';

  @override
  String get savePayPalDetails => 'Αποθήκευση στοιχείων PayPal';

  @override
  String get pleaseEnterPayPalEmail => 'Παρακαλώ εισάγετε το email PayPal σας';

  @override
  String get pleaseEnterPayPalMeLink => 'Παρακαλώ εισάγετε τον σύνδεσμο PayPal.me σας';

  @override
  String get doNotIncludeHttpInLink => 'Μην συμπεριλάβετε http ή https ή www στον σύνδεσμο';

  @override
  String get pleaseEnterValidPayPalMeLink => 'Παρακαλώ εισάγετε έναν έγκυρο σύνδεσμο PayPal.me';

  @override
  String get pleaseEnterValidEmail => 'Παρακαλώ εισάγετε μια έγκυρη διεύθυνση email';

  @override
  String get syncingYourRecordings => 'Συγχρονισμός των εγγραφών σας';

  @override
  String get syncYourRecordings => 'Συγχρονίστε τις εγγραφές σας';

  @override
  String get syncNow => 'Συγχρονισμός τώρα';

  @override
  String get error => 'Σφάλμα';

  @override
  String get speechSamples => 'Δείγματα ομιλίας';

  @override
  String additionalSampleIndex(String index) {
    return 'Πρόσθετο δείγμα $index';
  }

  @override
  String durationSeconds(String seconds) {
    return 'Διάρκεια: $seconds δευτερόλεπτα';
  }

  @override
  String get additionalSpeechSampleRemoved => 'Το πρόσθετο δείγμα ομιλίας αφαιρέθηκε';

  @override
  String get consentDataMessage =>
      'Συνεχίζοντας, όλα τα δεδομένα που μοιράζεστε με αυτήν την εφαρμογή (συμπεριλαμβανομένων των συνομιλιών, των εγγραφών και των προσωπικών σας πληροφοριών) θα αποθηκεύονται με ασφάλεια στους διακομιστές μας για να σας παρέχουμε πληροφορίες με τεχνητή νοημοσύνη και να ενεργοποιήσουμε όλες τις λειτουργίες της εφαρμογής.';

  @override
  String get tasksEmptyStateMessage =>
      'Οι εργασίες από τις συνομιλίες σας θα εμφανιστούν εδώ.\nΠατήστε + για χειροκίνητη δημιουργία.';

  @override
  String get clearChatAction => 'Διαγραφή συνομιλίας';

  @override
  String get enableApps => 'Ενεργοποίηση εφαρμογών';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => 'περισσότερα ↓';

  @override
  String get showLess => 'λιγότερα ↑';

  @override
  String get loadingYourRecording => 'Φόρτωση της εγγραφής σας...';

  @override
  String get photoDiscardedMessage => 'Αυτή η φωτογραφία απορρίφθηκε καθώς δεν ήταν σημαντική.';

  @override
  String get analyzing => 'Ανάλυση...';

  @override
  String get searchCountries => 'Αναζήτηση χωρών...';

  @override
  String get checkingAppleWatch => 'Έλεγχος Apple Watch...';

  @override
  String get installOmiOnAppleWatch => 'Εγκαταστήστε το Omi στο\nApple Watch σας';

  @override
  String get installOmiOnAppleWatchDescription =>
      'Για να χρησιμοποιήσετε το Apple Watch με το Omi, πρέπει πρώτα να εγκαταστήσετε την εφαρμογή Omi στο ρολόι σας.';

  @override
  String get openOmiOnAppleWatch => 'Ανοίξτε το Omi στο\nApple Watch σας';

  @override
  String get openOmiOnAppleWatchDescription =>
      'Η εφαρμογή Omi είναι εγκατεστημένη στο Apple Watch σας. Ανοίξτε την και πατήστε Έναρξη.';

  @override
  String get openWatchApp => 'Άνοιγμα εφαρμογής Watch';

  @override
  String get iveInstalledAndOpenedTheApp => 'Έχω εγκαταστήσει και ανοίξει την εφαρμογή';

  @override
  String get unableToOpenWatchApp =>
      'Δεν είναι δυνατό το άνοιγμα της εφαρμογής Apple Watch. Ανοίξτε χειροκίνητα την εφαρμογή Watch στο Apple Watch και εγκαταστήστε το Omi από την ενότητα \"Διαθέσιμες εφαρμογές\".';

  @override
  String get appleWatchConnectedSuccessfully => 'Το Apple Watch συνδέθηκε επιτυχώς!';

  @override
  String get appleWatchNotReachable =>
      'Το Apple Watch δεν είναι ακόμα προσβάσιμο. Βεβαιωθείτε ότι η εφαρμογή Omi είναι ανοιχτή στο ρολόι σας.';

  @override
  String errorCheckingConnection(String error) {
    return 'Σφάλμα ελέγχου σύνδεσης: $error';
  }

  @override
  String get muted => 'Σίγαση';

  @override
  String get processNow => 'Επεξεργασία τώρα';

  @override
  String get finishedConversation => 'Τελείωσε η συνομιλία;';

  @override
  String get stopRecordingConfirmation =>
      'Είστε σίγουροι ότι θέλετε να σταματήσετε την εγγραφή και να συνοψίσετε τη συνομιλία τώρα;';

  @override
  String get conversationEndsManually => 'Η συνομιλία θα τελειώσει μόνο χειροκίνητα.';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'Η συνομιλία συνοψίζεται μετά από $minutes λεπτ$suffix χωρίς ομιλία.';
  }

  @override
  String get dontAskAgain => 'Μη με ρωτήσεις ξανά';

  @override
  String get waitingForTranscriptOrPhotos => 'Αναμονή για μεταγραφή ή φωτογραφίες...';

  @override
  String get noSummaryYet => 'Δεν υπάρχει σύνοψη ακόμα';

  @override
  String hints(String text) {
    return 'Συμβουλές: $text';
  }

  @override
  String get testConversationPrompt => 'Δοκιμή προτροπής συνομιλίας';

  @override
  String get prompt => 'Προτροπή';

  @override
  String get result => 'Αποτέλεσμα:';

  @override
  String get compareTranscripts => 'Σύγκριση μεταγραφών';

  @override
  String get notHelpful => 'Δεν ήταν χρήσιμο';

  @override
  String get exportTasksWithOneTap => 'Εξαγωγή εργασιών με ένα πάτημα!';

  @override
  String get inProgress => 'Σε εξέλιξη';

  @override
  String get photos => 'Φωτογραφίες';

  @override
  String get rawData => 'Ανεπεξέργαστα δεδομένα';

  @override
  String get content => 'Περιεχόμενο';

  @override
  String get noContentToDisplay => 'Δεν υπάρχει περιεχόμενο για εμφάνιση';

  @override
  String get noSummary => 'Χωρίς σύνοψη';

  @override
  String get updateOmiFirmware => 'Ενημέρωση firmware omi';

  @override
  String get anErrorOccurredTryAgain => 'Παρουσιάστηκε σφάλμα. Παρακαλώ δοκιμάστε ξανά.';

  @override
  String get welcomeBackSimple => 'Καλώς ήρθατε πίσω';

  @override
  String get addVocabularyDescription => 'Προσθέστε λέξεις που το Omi πρέπει να αναγνωρίζει κατά τη μεταγραφή.';

  @override
  String get enterWordsCommaSeparated => 'Εισάγετε λέξεις (διαχωρισμένες με κόμμα)';

  @override
  String get whenToReceiveDailySummary => 'Πότε να λάβετε την ημερήσια σύνοψή σας';

  @override
  String get checkingNextSevenDays => 'Έλεγχος των επόμενων 7 ημερών';

  @override
  String failedToDeleteError(String error) {
    return 'Αποτυχία διαγραφής: $error';
  }

  @override
  String get developerApiKeys => 'Κλειδιά API προγραμματιστή';

  @override
  String get noApiKeysCreateOne => 'Δεν υπάρχουν κλειδιά API. Δημιουργήστε ένα για να ξεκινήσετε.';

  @override
  String get commandRequired => 'Απαιτείται ⌘';

  @override
  String get spaceKey => 'Διάστημα';

  @override
  String loadMoreRemaining(String count) {
    return 'Φόρτωση περισσότερων ($count απομένουν)';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'Κορυφαίο $percentile% χρήστη';
  }

  @override
  String get wrappedMinutes => 'λεπτά';

  @override
  String get wrappedConversations => 'συνομιλίες';

  @override
  String get wrappedDaysActive => 'ενεργές ημέρες';

  @override
  String get wrappedYouTalkedAbout => 'Μιλήσατε για';

  @override
  String get wrappedActionItems => 'Εργασίες';

  @override
  String get wrappedTasksCreated => 'δημιουργημένες εργασίες';

  @override
  String get wrappedCompleted => 'ολοκληρώθηκαν';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% ποσοστό ολοκλήρωσης';
  }

  @override
  String get wrappedYourTopDays => 'Οι κορυφαίες μέρες σας';

  @override
  String get wrappedBestMoments => 'Καλύτερες στιγμές';

  @override
  String get wrappedMyBuddies => 'Οι φίλοι μου';

  @override
  String get wrappedCouldntStopTalkingAbout => 'Δεν μπορούσα να σταματήσω να μιλάω για';

  @override
  String get wrappedShow => 'ΣΕΙΡΑ';

  @override
  String get wrappedMovie => 'ΤΑΙΝΙΑ';

  @override
  String get wrappedBook => 'ΒΙΒΛΙΟ';

  @override
  String get wrappedCelebrity => 'ΔΙΑΣΗΜΟΣ';

  @override
  String get wrappedFood => 'ΦΑΓΗΤΟ';

  @override
  String get wrappedMovieRecs => 'Προτάσεις ταινιών για φίλους';

  @override
  String get wrappedBiggest => 'Μεγαλύτερη';

  @override
  String get wrappedStruggle => 'Πρόκληση';

  @override
  String get wrappedButYouPushedThrough => 'Αλλά τα κατάφερες 💪';

  @override
  String get wrappedWin => 'Νίκη';

  @override
  String get wrappedYouDidIt => 'Τα κατάφερες! 🎉';

  @override
  String get wrappedTopPhrases => 'Κορυφαίες 5 φράσεις';

  @override
  String get wrappedMins => 'λεπ';

  @override
  String get wrappedConvos => 'συνομιλίες';

  @override
  String get wrappedDays => 'ημ';

  @override
  String get wrappedMyBuddiesLabel => 'ΟΙ ΦΙΛΟΙ ΜΟΥ';

  @override
  String get wrappedObsessionsLabel => 'ΕΜΜΟΝΕΣ';

  @override
  String get wrappedStruggleLabel => 'ΠΡΟΚΛΗΣΗ';

  @override
  String get wrappedWinLabel => 'ΝΙΚΗ';

  @override
  String get wrappedTopPhrasesLabel => 'ΚΟΡΥΦΑΙΕΣ ΦΡΑΣΕΙΣ';

  @override
  String get wrappedLetsHitRewind => 'Ας γυρίσουμε πίσω το';

  @override
  String get wrappedGenerateMyWrapped => 'Δημιούργησε το Wrapped μου';

  @override
  String get wrappedProcessingDefault => 'Επεξεργασία...';

  @override
  String get wrappedCreatingYourStory => 'Δημιουργούμε την\nιστορία του 2025...';

  @override
  String get wrappedSomethingWentWrong => 'Κάτι πήγε\nστραβά';

  @override
  String get wrappedAnErrorOccurred => 'Παρουσιάστηκε σφάλμα';

  @override
  String get wrappedTryAgain => 'Δοκίμασε ξανά';

  @override
  String get wrappedNoDataAvailable => 'Δεν υπάρχουν διαθέσιμα δεδομένα';

  @override
  String get wrappedOmiLifeRecap => 'Ανασκόπηση ζωής Omi';

  @override
  String get wrappedSwipeUpToBegin => 'Σύρε προς τα πάνω για να ξεκινήσεις';

  @override
  String get wrappedShareText => 'Το 2025 μου, αποτυπωμένο από το Omi ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare => 'Η κοινοποίηση απέτυχε. Δοκιμάστε ξανά.';

  @override
  String get wrappedFailedToStartGeneration => 'Η εκκίνηση δημιουργίας απέτυχε. Δοκιμάστε ξανά.';

  @override
  String get wrappedStarting => 'Εκκίνηση...';

  @override
  String get wrappedShare => 'Κοινοποίηση';

  @override
  String get wrappedShareYourWrapped => 'Μοιράσου το Wrapped σου';

  @override
  String get wrappedMy2025 => 'Το 2025 μου';

  @override
  String get wrappedRememberedByOmi => 'αποτυπωμένο από το Omi';

  @override
  String get wrappedMostFunDay => 'Πιο διασκεδαστική';

  @override
  String get wrappedMostProductiveDay => 'Πιο παραγωγική';

  @override
  String get wrappedMostIntenseDay => 'Πιο έντονη';

  @override
  String get wrappedFunniestMoment => 'Πιο αστεία';

  @override
  String get wrappedMostCringeMoment => 'Πιο ντροπιαστική';

  @override
  String get wrappedMinutesLabel => 'λεπτά';

  @override
  String get wrappedConversationsLabel => 'συνομιλίες';

  @override
  String get wrappedDaysActiveLabel => 'ενεργές μέρες';

  @override
  String get wrappedTasksGenerated => 'εργασίες δημιουργήθηκαν';

  @override
  String get wrappedTasksCompleted => 'εργασίες ολοκληρώθηκαν';

  @override
  String get wrappedTopFivePhrases => 'Κορυφαίες 5 φράσεις';

  @override
  String get wrappedAGreatDay => 'Μια υπέροχη μέρα';

  @override
  String get wrappedGettingItDone => 'Ολοκληρώνοντας';

  @override
  String get wrappedAChallenge => 'Μια πρόκληση';

  @override
  String get wrappedAHilariousMoment => 'Μια αστεία στιγμή';

  @override
  String get wrappedThatAwkwardMoment => 'Εκείνη η άβολη στιγμή';

  @override
  String get wrappedYouHadFunnyMoments => 'Είχες αστείες στιγμές φέτος!';

  @override
  String get wrappedWeveAllBeenThere => 'Όλοι έχουμε περάσει από εκεί!';

  @override
  String get wrappedFriend => 'Φίλος';

  @override
  String get wrappedYourBuddy => 'Ο φίλος σου!';

  @override
  String get wrappedNotMentioned => 'Δεν αναφέρθηκε';

  @override
  String get wrappedTheHardPart => 'Το δύσκολο μέρος';

  @override
  String get wrappedPersonalGrowth => 'Προσωπική ανάπτυξη';

  @override
  String get wrappedFunDay => 'Διασκέδαση';

  @override
  String get wrappedProductiveDay => 'Παραγωγική';

  @override
  String get wrappedIntenseDay => 'Έντονη';

  @override
  String get wrappedFunnyMomentTitle => 'Αστεία στιγμή';

  @override
  String get wrappedCringeMomentTitle => 'Ντροπιαστική στιγμή';

  @override
  String get wrappedYouTalkedAboutBadge => 'Μίλησες για';

  @override
  String get wrappedCompletedLabel => 'Ολοκληρώθηκε';

  @override
  String get wrappedMyBuddiesCard => 'Οι φίλοι μου';

  @override
  String get wrappedBuddiesLabel => 'ΦΙΛΟΙ';

  @override
  String get wrappedObsessionsLabelUpper => 'ΕΜΜΟΝΕΣ';

  @override
  String get wrappedStruggleLabelUpper => 'ΑΓΩΝΑΣ';

  @override
  String get wrappedWinLabelUpper => 'ΝΙΚΗ';

  @override
  String get wrappedTopPhrasesLabelUpper => 'ΚΟΡΥΦΑΙΕΣ ΦΡΑΣΕΙΣ';

  @override
  String get wrappedYourHeader => 'Οι δικές σου';

  @override
  String get wrappedTopDaysHeader => 'Κορυφαίες μέρες';

  @override
  String get wrappedYourTopDaysBadge => 'Οι κορυφαίες μέρες σου';

  @override
  String get wrappedBestHeader => 'Καλύτερες';

  @override
  String get wrappedMomentsHeader => 'Στιγμές';

  @override
  String get wrappedBestMomentsBadge => 'Καλύτερες στιγμές';

  @override
  String get wrappedBiggestHeader => 'Μεγαλύτερος';

  @override
  String get wrappedStruggleHeader => 'Αγώνας';

  @override
  String get wrappedWinHeader => 'Νίκη';

  @override
  String get wrappedButYouPushedThroughEmoji => 'Αλλά τα κατάφερες 💪';

  @override
  String get wrappedYouDidItEmoji => 'Τα κατάφερες! 🎉';

  @override
  String get wrappedHours => 'ώρες';

  @override
  String get wrappedActions => 'ενέργειες';

  @override
  String get multipleSpeakersDetected => 'Εντοπίστηκαν πολλοί ομιλητές';

  @override
  String get multipleSpeakersDescription =>
      'Φαίνεται ότι υπάρχουν πολλοί ομιλητές στην εγγραφή. Βεβαιωθείτε ότι βρίσκεστε σε ήσυχο μέρος και δοκιμάστε ξανά.';

  @override
  String get invalidRecordingDetected => 'Εντοπίστηκε μη έγκυρη εγγραφή';

  @override
  String get notEnoughSpeechDescription => 'Δεν εντοπίστηκε αρκετή ομιλία. Μιλήστε περισσότερο και δοκιμάστε ξανά.';

  @override
  String get speechDurationDescription =>
      'Βεβαιωθείτε ότι μιλάτε τουλάχιστον 5 δευτερόλεπτα και όχι περισσότερο από 90.';

  @override
  String get connectionLostDescription =>
      'Η σύνδεση διακόπηκε. Ελέγξτε τη σύνδεσή σας στο διαδίκτυο και δοκιμάστε ξανά.';

  @override
  String get howToTakeGoodSample => 'Πώς να πάρετε ένα καλό δείγμα;';

  @override
  String get goodSampleInstructions =>
      '1. Βεβαιωθείτε ότι βρίσκεστε σε ήσυχο μέρος.\n2. Μιλήστε καθαρά και φυσικά.\n3. Βεβαιωθείτε ότι η συσκευή σας είναι στη φυσική της θέση στο λαιμό σας.\n\nΜόλις δημιουργηθεί, μπορείτε πάντα να το βελτιώσετε ή να το κάνετε ξανά.';

  @override
  String get noDeviceConnectedUseMic => 'Δεν έχει συνδεθεί συσκευή. Θα χρησιμοποιηθεί το μικρόφωνο του τηλεφώνου.';

  @override
  String get doItAgain => 'Κάντο ξανά';

  @override
  String get listenToSpeechProfile => 'Ακούστε το φωνητικό μου προφίλ ➡️';

  @override
  String get recognizingOthers => 'Αναγνώριση άλλων 👀';

  @override
  String get keepGoingGreat => 'Συνέχισε, τα πας υπέροχα';

  @override
  String get somethingWentWrongTryAgain => 'Κάτι πήγε στραβά! Παρακαλώ δοκιμάστε ξανά αργότερα.';

  @override
  String get uploadingVoiceProfile => 'Μεταφόρτωση του φωνητικού σας προφίλ....';

  @override
  String get memorizingYourVoice => 'Απομνημόνευση της φωνής σας...';

  @override
  String get personalizingExperience => 'Εξατομίκευση της εμπειρίας σας...';

  @override
  String get keepSpeakingUntil100 => 'Συνεχίστε να μιλάτε μέχρι να φτάσετε το 100%.';

  @override
  String get greatJobAlmostThere => 'Εξαιρετική δουλειά, σχεδόν τελειώσατε';

  @override
  String get soCloseJustLittleMore => 'Τόσο κοντά, λίγο ακόμα';

  @override
  String get notificationFrequency => 'Συχνότητα ειδοποιήσεων';

  @override
  String get controlNotificationFrequency => 'Ελέγξτε πόσο συχνά το Omi σας στέλνει προληπτικές ειδοποιήσεις.';

  @override
  String get yourScore => 'Το σκορ σας';

  @override
  String get dailyScoreBreakdown => 'Ανάλυση ημερήσιου σκορ';

  @override
  String get todaysScore => 'Σημερινό σκορ';

  @override
  String get tasksCompleted => 'Εργασίες ολοκληρώθηκαν';

  @override
  String get completionRate => 'Ποσοστό ολοκλήρωσης';

  @override
  String get howItWorks => 'Πώς λειτουργεί';

  @override
  String get dailyScoreExplanation =>
      'Το ημερήσιο σκορ σας βασίζεται στην ολοκλήρωση εργασιών. Ολοκληρώστε τις εργασίες σας για να βελτιώσετε το σκορ!';

  @override
  String get notificationFrequencyDescription =>
      'Ελέγξτε πόσο συχνά το Omi σας στέλνει προληπτικές ειδοποιήσεις και υπενθυμίσεις.';

  @override
  String get sliderOff => 'Απεν.';

  @override
  String get sliderMax => 'Μέγ.';

  @override
  String summaryGeneratedFor(String date) {
    return 'Η σύνοψη δημιουργήθηκε για $date';
  }

  @override
  String get failedToGenerateSummary =>
      'Αποτυχία δημιουργίας σύνοψης. Βεβαιωθείτε ότι έχετε συνομιλίες για εκείνη την ημέρα.';

  @override
  String get recap => 'Ανακεφαλαίωση';

  @override
  String deleteQuoted(String name) {
    return 'Διαγραφή \"$name\"';
  }

  @override
  String moveConversationsTo(int count) {
    return 'Μετακίνηση $count συνομιλιών σε:';
  }

  @override
  String get noFolder => 'Χωρίς φάκελο';

  @override
  String get removeFromAllFolders => 'Αφαίρεση από όλους τους φακέλους';

  @override
  String get buildAndShareYourCustomApp => 'Δημιουργήστε και μοιραστείτε την προσαρμοσμένη σας εφαρμογή';

  @override
  String get searchAppsPlaceholder => 'Αναζήτηση σε 1500+ εφαρμογές';

  @override
  String get filters => 'Φίλτρα';

  @override
  String get frequencyOff => 'Απενεργοποιημένο';

  @override
  String get frequencyMinimal => 'Ελάχιστο';

  @override
  String get frequencyLow => 'Χαμηλό';

  @override
  String get frequencyBalanced => 'Ισορροπημένο';

  @override
  String get frequencyHigh => 'Υψηλό';

  @override
  String get frequencyMaximum => 'Μέγιστο';

  @override
  String get frequencyDescOff => 'Χωρίς προληπτικές ειδοποιήσεις';

  @override
  String get frequencyDescMinimal => 'Μόνο κρίσιμες υπενθυμίσεις';

  @override
  String get frequencyDescLow => 'Μόνο σημαντικές ενημερώσεις';

  @override
  String get frequencyDescBalanced => 'Τακτικές χρήσιμες υπενθυμίσεις';

  @override
  String get frequencyDescHigh => 'Συχνοί έλεγχοι';

  @override
  String get frequencyDescMaximum => 'Μείνετε συνεχώς ενεργοί';

  @override
  String get clearChatQuestion => 'Διαγραφή συνομιλίας;';

  @override
  String get syncingMessages => 'Συγχρονισμός μηνυμάτων με τον διακομιστή...';

  @override
  String get chatAppsTitle => 'Εφαρμογές συνομιλίας';

  @override
  String get selectApp => 'Επιλογή εφαρμογής';

  @override
  String get noChatAppsEnabled =>
      'Δεν έχουν ενεργοποιηθεί εφαρμογές συνομιλίας.\nΠατήστε \"Ενεργοποίηση εφαρμογών\" για προσθήκη.';

  @override
  String get disable => 'Απενεργοποίηση';

  @override
  String get photoLibrary => 'Βιβλιοθήκη φωτογραφιών';

  @override
  String get chooseFile => 'Επιλογή αρχείου';

  @override
  String get configureAiPersona => 'Configure your AI persona';

  @override
  String get connectAiAssistantsToYourData => 'Connect AI assistants to your data';

  @override
  String get oAuth => 'OAuth';

  @override
  String get trackYourGoalsOnHomepage => 'Track your personal goals on homepage';

  @override
  String get deleteRecording => 'Delete Recording';

  @override
  String get thisCannotBeUndone => 'This cannot be undone.';

  @override
  String get sdCard => 'SD Card';

  @override
  String get fromSd => 'From SD';

  @override
  String get limitless => 'Limitless';

  @override
  String get fastTransfer => 'Γρήγορη μεταφορά';

  @override
  String get syncingStatus => 'Syncing';

  @override
  String get failedStatus => 'Failed';

  @override
  String etaLabel(String time) {
    return 'ETA: $time';
  }

  @override
  String get transferMethod => 'Μέθοδος μεταφοράς';

  @override
  String get fast => 'Fast';

  @override
  String get ble => 'BLE';

  @override
  String get phone => 'Phone';

  @override
  String get cancelSync => 'Cancel Sync';

  @override
  String get cancelSyncMessage => 'Data already downloaded will be saved. You can resume later.';

  @override
  String get syncCancelled => 'Sync cancelled';

  @override
  String get deleteProcessedFiles => 'Delete Processed Files';

  @override
  String get processedFilesDeleted => 'Processed files deleted';

  @override
  String get wifiEnableFailed => 'Failed to enable WiFi on device. Please try again.';

  @override
  String get deviceNoFastTransfer => 'Your device does not support Fast Transfer. Use Bluetooth instead.';

  @override
  String get enableHotspotMessage => 'Please enable your phone\'s hotspot and try again.';

  @override
  String get transferStartFailed => 'Failed to start transfer. Please try again.';

  @override
  String get deviceNotResponding => 'Device did not respond. Please try again.';

  @override
  String get invalidWifiCredentials => 'Invalid WiFi credentials. Check your hotspot settings.';

  @override
  String get wifiConnectionFailed => 'WiFi connection failed. Please try again.';

  @override
  String get sdCardProcessing => 'SD Card Processing';

  @override
  String sdCardProcessingMessage(int count) {
    return 'Processing $count recording(s). Files will be removed from SD card after.';
  }

  @override
  String get process => 'Process';

  @override
  String get wifiSyncFailed => 'WiFi Sync Failed';

  @override
  String get processingFailed => 'Processing Failed';

  @override
  String get downloadingFromSdCard => 'Downloading from SD Card';

  @override
  String processingProgress(int current, int total) {
    return 'Processing $current/$total';
  }

  @override
  String conversationsCreated(int count) {
    return '$count conversations created';
  }

  @override
  String get internetRequired => 'Internet required';

  @override
  String get processAudio => 'Process Audio';

  @override
  String get start => 'Start';

  @override
  String get noRecordings => 'No Recordings';

  @override
  String get audioFromOmiWillAppearHere => 'Audio from your Omi device will appear here';

  @override
  String get deleteProcessed => 'Delete Processed';

  @override
  String get tryDifferentFilter => 'Try a different filter';

  @override
  String get recordings => 'Recordings';

  @override
  String get enableRemindersAccess =>
      'Παρακαλώ ενεργοποιήστε την πρόσβαση στις Υπενθυμίσεις στις Ρυθμίσεις για να χρησιμοποιήσετε τις Υπενθυμίσεις Apple';

  @override
  String todayAtTime(String time) {
    return 'Σήμερα στις $time';
  }

  @override
  String yesterdayAtTime(String time) {
    return 'Χθες στις $time';
  }

  @override
  String get lessThanAMinute => 'Λιγότερο από ένα λεπτό';

  @override
  String estimatedMinutes(int count) {
    return '~$count λεπτό/λεπτά';
  }

  @override
  String estimatedHours(int count) {
    return '~$count ώρα/ώρες';
  }

  @override
  String estimatedTimeRemaining(String time) {
    return 'Εκτίμηση: απομένει $time';
  }

  @override
  String get summarizingConversation => 'Σύνοψη συνομιλίας...\nΑυτό μπορεί να διαρκέσει μερικά δευτερόλεπτα';

  @override
  String get resummarizingConversation => 'Εκ νέου σύνοψη συνομιλίας...\nΑυτό μπορεί να διαρκέσει μερικά δευτερόλεπτα';

  @override
  String get nothingInterestingRetry => 'Δεν βρέθηκε τίποτα ενδιαφέρον,\nθέλετε να δοκιμάσετε ξανά;';

  @override
  String get noSummaryForConversation => 'Δεν υπάρχει διαθέσιμη σύνοψη\nγια αυτήν τη συνομιλία.';

  @override
  String get unknownLocation => 'Άγνωστη τοποθεσία';

  @override
  String get couldNotLoadMap => 'Δεν ήταν δυνατή η φόρτωση του χάρτη';

  @override
  String get triggerConversationIntegration => 'Ενεργοποίηση ολοκλήρωσης δημιουργίας συνομιλίας';

  @override
  String get webhookUrlNotSet => 'URL Webhook δεν έχει οριστεί';

  @override
  String get setWebhookUrlInSettings => 'Ορίστε το URL webhook στις ρυθμίσεις προγραμματιστή.';

  @override
  String get sendWebUrl => 'Αποστολή web URL';

  @override
  String get sendTranscript => 'Αποστολή απομαγνητοφώνησης';

  @override
  String get sendSummary => 'Αποστολή σύνοψης';

  @override
  String get debugModeDetected => 'Ανιχνεύθηκε λειτουργία εντοπισμού σφαλμάτων';

  @override
  String get performanceReduced => 'Η απόδοση μπορεί να μειωθεί';

  @override
  String autoClosingInSeconds(int seconds) {
    return 'Αυτόματο κλείσιμο σε $seconds δευτερόλεπτα';
  }

  @override
  String get modelRequired => 'Απαιτείται μοντέλο';

  @override
  String get downloadWhisperModel => 'Κατεβάστε ένα μοντέλο whisper για να χρησιμοποιήσετε τη μεταγραφή στη συσκευή';

  @override
  String get deviceNotCompatible => 'Η συσκευή σας δεν είναι συμβατή με τη μεταγραφή στη συσκευή';

  @override
  String get deviceRequirements => 'Your device does not meet the requirements for On-Device transcription.';

  @override
  String get willLikelyCrash => 'Η ενεργοποίηση πιθανότατα θα προκαλέσει κατάρρευση ή πάγωμα της εφαρμογής.';

  @override
  String get transcriptionSlowerLessAccurate => 'Η μεταγραφή θα είναι σημαντικά πιο αργή και λιγότερο ακριβής.';

  @override
  String get proceedAnyway => 'Συνέχεια ούτως ή άλλως';

  @override
  String get olderDeviceDetected => 'Εντοπίστηκε παλαιότερη συσκευή';

  @override
  String get onDeviceSlower => 'On-device transcription may be slower on this device.';

  @override
  String get batteryUsageHigher => 'Η χρήση μπαταρίας θα είναι υψηλότερη από τη μεταγραφή στο cloud.';

  @override
  String get considerOmiCloud => 'Σκεφτείτε να χρησιμοποιήσετε το Omi Cloud για καλύτερη απόδοση.';

  @override
  String get highResourceUsage => 'Υψηλή χρήση πόρων';

  @override
  String get onDeviceIntensive => 'On-Device transcription is computationally intensive.';

  @override
  String get batteryDrainIncrease => 'Battery drain will increase significantly.';

  @override
  String get deviceMayWarmUp => 'Η συσκευή μπορεί να ζεσταθεί κατά την παρατεταμένη χρήση.';

  @override
  String get speedAccuracyLower => 'Η ταχύτητα και η ακρίβεια μπορεί να είναι χαμηλότερες από τα μοντέλα Cloud.';

  @override
  String get cloudProvider => 'Πάροχος Cloud';

  @override
  String get premiumMinutesInfo => '1,200 premium minutes/month. On-Device tab offers unlimited free transcription.';

  @override
  String get viewUsage => 'Προβολή χρήσης';

  @override
  String get localProcessingInfo => 'Audio is processed locally. Works offline, more private, but uses more battery.';

  @override
  String get model => 'Model';

  @override
  String get performanceWarning => 'Προειδοποίηση απόδοσης';

  @override
  String get largeModelWarning =>
      'This model is large and may crash the app or run very slowly on mobile devices.\n\n\"small\" or \"base\" is recommended.';

  @override
  String get usingNativeIosSpeech => 'Χρήση εγγενούς αναγνώρισης ομιλίας iOS';

  @override
  String get noModelDownloadRequired => 'Your device\'s native speech engine will be used. No model download required.';

  @override
  String get modelReady => 'Model Ready';

  @override
  String get redownload => 'Re-download';

  @override
  String get doNotCloseApp => 'Παρακαλώ μην κλείσετε την εφαρμογή.';

  @override
  String get downloading => 'Λήψη σε εξέλιξη...';

  @override
  String get downloadModel => 'Λήψη μοντέλου';

  @override
  String estimatedSize(String size) {
    return 'Estimated Size: ~$size MB';
  }

  @override
  String availableSpace(String space) {
    return 'Available Space: $space';
  }

  @override
  String get notEnoughSpace => 'Προειδοποίηση: Δεν υπάρχει αρκετός χώρος!';

  @override
  String get download => 'Λήψη';

  @override
  String downloadError(String error) {
    return 'Download error: $error';
  }

  @override
  String get cancelled => 'Ακυρώθηκε';

  @override
  String get deviceNotCompatibleTitle => 'Η συσκευή δεν είναι συμβατή';

  @override
  String get deviceNotMeetRequirements => 'Η συσκευή σας δεν πληροί τις απαιτήσεις για μεταγραφή στη συσκευή.';

  @override
  String get transcriptionSlowerOnDevice => 'Η μεταγραφή στη συσκευή μπορεί να είναι πιο αργή σε αυτήν τη συσκευή.';

  @override
  String get computationallyIntensive => 'Η μεταγραφή στη συσκευή είναι υπολογιστικά απαιτητική.';

  @override
  String get batteryDrainSignificantly => 'Η κατανάλωση μπαταρίας θα αυξηθεί σημαντικά.';

  @override
  String get premiumMinutesMonth =>
      '1.200 premium λεπτά/μήνα. Η καρτέλα Στη συσκευή προσφέρει απεριόριστη δωρεάν μεταγραφή. ';

  @override
  String get audioProcessedLocally =>
      'Ο ήχος επεξεργάζεται τοπικά. Λειτουργεί εκτός σύνδεσης, πιο ιδιωτικό, αλλά καταναλώνει περισσότερη μπαταρία.';

  @override
  String get languageLabel => 'Γλώσσα';

  @override
  String get modelLabel => 'Μοντέλο';

  @override
  String get modelTooLargeWarning =>
      'Αυτό το μοντέλο είναι μεγάλο και μπορεί να προκαλέσει κατάρρευση της εφαρμογής ή πολύ αργή λειτουργία σε κινητές συσκευές.\n\nΣυνιστάται το small ή base.';

  @override
  String get nativeEngineNoDownload =>
      'Θα χρησιμοποιηθεί η εγγενής μηχανή ομιλίας της συσκευής σας. Δεν απαιτείται λήψη μοντέλου.';

  @override
  String modelReadyWithName(String model) {
    return 'Μοντέλο έτοιμο ($model)';
  }

  @override
  String get reDownload => 'Εκ νέου λήψη';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return 'Λήψη $model: $received / $total MB';
  }

  @override
  String preparingModel(String model) {
    return 'Προετοιμασία $model...';
  }

  @override
  String downloadErrorWithMessage(String error) {
    return 'Σφάλμα λήψης: $error';
  }

  @override
  String estimatedSizeWithValue(String size) {
    return 'Εκτιμώμενο μέγεθος: ~$size MB';
  }

  @override
  String availableSpaceWithValue(String space) {
    return 'Διαθέσιμος χώρος: $space';
  }

  @override
  String get omiTranscriptionOptimized =>
      'Η ενσωματωμένη ζωντανή μεταγραφή του Omi είναι βελτιστοποιημένη για συνομιλίες σε πραγματικό χρόνο με αυτόματη ανίχνευση και διαχωρισμό ομιλητών.';

  @override
  String get reset => 'Επαναφορά';

  @override
  String get useTemplateFrom => 'Χρήση προτύπου από';

  @override
  String get selectProviderTemplate => 'Επιλέξτε πρότυπο παρόχου...';

  @override
  String get quicklyPopulateResponse => 'Γρήγορη συμπλήρωση με γνωστή μορφή απόκρισης παρόχου';

  @override
  String get quicklyPopulateRequest => 'Γρήγορη συμπλήρωση με γνωστή μορφή αιτήματος παρόχου';

  @override
  String get invalidJsonError => 'Μη έγκυρο JSON';

  @override
  String downloadModelWithName(String model) {
    return 'Λήψη μοντέλου ($model)';
  }

  @override
  String modelNameWithFile(String model) {
    return 'Μοντέλο: $model';
  }

  @override
  String get device => 'Device';

  @override
  String get chatAssistantsTitle => 'Βοηθοί συνομιλίας';

  @override
  String get permissionReadConversations => 'Ανάγνωση συνομιλιών';

  @override
  String get permissionReadMemories => 'Ανάγνωση αναμνήσεων';

  @override
  String get permissionReadTasks => 'Ανάγνωση εργασιών';

  @override
  String get permissionCreateConversations => 'Δημιουργία συνομιλιών';

  @override
  String get permissionCreateMemories => 'Δημιουργία αναμνήσεων';

  @override
  String get permissionTypeAccess => 'Πρόσβαση';

  @override
  String get permissionTypeCreate => 'Δημιουργία';

  @override
  String get permissionTypeTrigger => 'Ενεργοποιητής';

  @override
  String get permissionDescReadConversations => 'Αυτή η εφαρμογή μπορεί να έχει πρόσβαση στις συνομιλίες σας.';

  @override
  String get permissionDescReadMemories => 'Αυτή η εφαρμογή μπορεί να έχει πρόσβαση στις αναμνήσεις σας.';

  @override
  String get permissionDescReadTasks => 'Αυτή η εφαρμογή μπορεί να έχει πρόσβαση στις εργασίες σας.';

  @override
  String get permissionDescCreateConversations => 'Αυτή η εφαρμογή μπορεί να δημιουργεί νέες συνομιλίες.';

  @override
  String get permissionDescCreateMemories => 'Αυτή η εφαρμογή μπορεί να δημιουργεί νέες αναμνήσεις.';

  @override
  String get realtimeListening => 'Ακρόαση σε πραγματικό χρόνο';

  @override
  String get setupCompleted => 'Ολοκληρώθηκε';

  @override
  String get pleaseSelectRating => 'Παρακαλώ επιλέξτε αξιολόγηση';

  @override
  String get writeReviewOptional => 'Γράψτε μια κριτική (προαιρετικό)';

  @override
  String get setupQuestionsIntro => 'Help us improve Omi by answering a few questions.  🫶 💜';

  @override
  String get setupQuestionProfession => '1. What do you do?';

  @override
  String get setupQuestionUsage => '2. Where do you plan to use your Omi?';

  @override
  String get setupQuestionAge => '3. What\'s your age range?';

  @override
  String get setupAnswerAllQuestions => 'You haven\'t answered all the questions yet! 🥺';

  @override
  String get setupSkipHelp => 'Skip, I don\'t want to help :C';

  @override
  String get professionEntrepreneur => 'Entrepreneur';

  @override
  String get professionSoftwareEngineer => 'Software Engineer';

  @override
  String get professionProductManager => 'Product Manager';

  @override
  String get professionExecutive => 'Executive';

  @override
  String get professionSales => 'Sales';

  @override
  String get professionStudent => 'Student';

  @override
  String get usageAtWork => 'At work';

  @override
  String get usageIrlEvents => 'IRL Events';

  @override
  String get usageOnline => 'Online';

  @override
  String get usageSocialSettings => 'In Social Settings';

  @override
  String get usageEverywhere => 'Everywhere';

  @override
  String get customBackendUrlTitle => 'Προσαρμοσμένο URL διακομιστή';

  @override
  String get backendUrlLabel => 'URL διακομιστή';

  @override
  String get saveUrlButton => 'Αποθήκευση URL';

  @override
  String get enterBackendUrlError => 'Εισάγετε το URL του διακομιστή';

  @override
  String get urlMustEndWithSlashError => 'Το URL πρέπει να τελειώνει με \"/\"';

  @override
  String get invalidUrlError => 'Εισάγετε ένα έγκυρο URL';

  @override
  String get backendUrlSavedSuccess => 'Το URL του διακομιστή αποθηκεύτηκε!';

  @override
  String get signInTitle => 'Σύνδεση';

  @override
  String get signInButton => 'Σύνδεση';

  @override
  String get enterEmailError => 'Εισάγετε το email σας';

  @override
  String get invalidEmailError => 'Εισάγετε ένα έγκυρο email';

  @override
  String get enterPasswordError => 'Εισάγετε τον κωδικό σας';

  @override
  String get passwordMinLengthError => 'Ο κωδικός πρέπει να έχει τουλάχιστον 8 χαρακτήρες';

  @override
  String get signInSuccess => 'Επιτυχής σύνδεση!';

  @override
  String get alreadyHaveAccountLogin => 'Έχετε ήδη λογαριασμό; Συνδεθείτε';

  @override
  String get emailLabel => 'Email';

  @override
  String get passwordLabel => 'Κωδικός';

  @override
  String get createAccountTitle => 'Δημιουργία λογαριασμού';

  @override
  String get nameLabel => 'Όνομα';

  @override
  String get repeatPasswordLabel => 'Επανάληψη κωδικού';

  @override
  String get signUpButton => 'Εγγραφή';

  @override
  String get enterNameError => 'Εισάγετε το όνομά σας';

  @override
  String get passwordsDoNotMatch => 'Οι κωδικοί δεν ταιριάζουν';

  @override
  String get signUpSuccess => 'Επιτυχής εγγραφή!';

  @override
  String get loadingKnowledgeGraph => 'Φόρτωση γραφήματος γνώσης...';

  @override
  String get noKnowledgeGraphYet => 'Δεν υπάρχει ακόμα γράφημα γνώσης';

  @override
  String get buildingKnowledgeGraphFromMemories => 'Δημιουργία γραφήματος γνώσης από αναμνήσεις...';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'Το γράφημα γνώσης θα δημιουργηθεί αυτόματα καθώς δημιουργείτε νέες αναμνήσεις.';

  @override
  String get buildGraphButton => 'Δημιουργία γραφήματος';

  @override
  String get checkOutMyMemoryGraph => 'Δείτε το γράφημα μνήμης μου!';

  @override
  String get getButton => 'Λήψη';

  @override
  String openingApp(String appName) {
    return 'Άνοιγμα $appName...';
  }

  @override
  String get writeSomething => 'Γράψτε κάτι';

  @override
  String get submitReply => 'Υποβολή απάντησης';

  @override
  String get editYourReply => 'Επεξεργασία απάντησης';

  @override
  String get replyToReview => 'Απάντηση στην κριτική';

  @override
  String get rateAndReviewThisApp => 'Βαθμολογήστε και αξιολογήστε αυτή την εφαρμογή';

  @override
  String get noChangesInReview => 'Δεν υπάρχουν αλλαγές στην κριτική για ενημέρωση.';

  @override
  String get cantRateWithoutInternet => 'Δεν είναι δυνατή η βαθμολόγηση χωρίς σύνδεση στο διαδίκτυο.';

  @override
  String get appAnalytics => 'Αναλυτικά εφαρμογής';

  @override
  String get learnMoreLink => 'μάθετε περισσότερα';

  @override
  String get moneyEarned => 'Κέρδη';

  @override
  String get writeYourReply => 'Write your reply...';

  @override
  String get replySentSuccessfully => 'Reply sent successfully';

  @override
  String failedToSendReply(String error) {
    return 'Failed to send reply: $error';
  }

  @override
  String get send => 'Send';

  @override
  String starFilter(int count) {
    return '$count Star';
  }

  @override
  String get noReviewsFound => 'No Reviews Found';

  @override
  String get editReply => 'Edit Reply';

  @override
  String get reply => 'Reply';

  @override
  String starFilterLabel(int count) {
    return '$count αστέρι';
  }

  @override
  String get sharePublicLink => 'Share Public Link';

  @override
  String get makePersonaPublic => 'Make Persona Public';

  @override
  String get connectedKnowledgeData => 'Connected Knowledge Data';

  @override
  String get enterName => 'Enter name';

  @override
  String get disconnectTwitter => 'Disconnect Twitter';

  @override
  String get disconnectTwitterConfirmation =>
      'Are you sure you want to disconnect your Twitter account? Your persona will no longer have access to your Twitter data.';

  @override
  String get getOmiDeviceDescription => 'Create a more accurate clone with your personal conversations';

  @override
  String get getOmi => 'Get Omi';

  @override
  String get iHaveOmiDevice => 'I have Omi device';

  @override
  String get goal => 'ΣΤΟΧΟΣ';

  @override
  String get tapToTrackThisGoal => 'Πατήστε για παρακολούθηση αυτού του στόχου';

  @override
  String get tapToSetAGoal => 'Πατήστε για να ορίσετε έναν στόχο';

  @override
  String get processedConversations => 'Επεξεργασμένες συνομιλίες';

  @override
  String get updatedConversations => 'Ενημερωμένες συνομιλίες';

  @override
  String get newConversations => 'Νέες συνομιλίες';

  @override
  String get summaryTemplate => 'Πρότυπο σύνοψης';

  @override
  String get suggestedTemplates => 'Προτεινόμενα πρότυπα';

  @override
  String get otherTemplates => 'Άλλα πρότυπα';

  @override
  String get availableTemplates => 'Διαθέσιμα πρότυπα';

  @override
  String get getCreative => 'Γίνε δημιουργικός';

  @override
  String get defaultLabel => 'Προεπιλογή';

  @override
  String get lastUsedLabel => 'Τελευταία χρήση';

  @override
  String get setDefaultApp => 'Ορισμός προεπιλεγμένης εφαρμογής';

  @override
  String setDefaultAppContent(String appName) {
    return 'Να οριστεί το $appName ως προεπιλεγμένη εφαρμογή σύνοψης;\\n\\nΑυτή η εφαρμογή θα χρησιμοποιείται αυτόματα για όλες τις μελλοντικές συνόψεις συνομιλιών.';
  }

  @override
  String get setDefaultButton => 'Ορισμός προεπιλογής';

  @override
  String setAsDefaultSuccess(String appName) {
    return 'Το $appName ορίστηκε ως προεπιλεγμένη εφαρμογή σύνοψης';
  }

  @override
  String get createCustomTemplate => 'Δημιουργία προσαρμοσμένου προτύπου';

  @override
  String get allTemplates => 'Όλα τα πρότυπα';

  @override
  String failedToInstallApp(String appName) {
    return 'Αποτυχία εγκατάστασης του $appName. Παρακαλώ δοκιμάστε ξανά.';
  }

  @override
  String errorInstallingApp(String appName, String error) {
    return 'Σφάλμα εγκατάστασης του $appName: $error';
  }

  @override
  String tagSpeaker(int speakerId) {
    return 'Tag Speaker $speakerId';
  }

  @override
  String get personNameAlreadyExists => 'A person with this name already exists.';

  @override
  String get selectYouFromList => 'To tag yourself, please select \"You\" from the list.';

  @override
  String get enterPersonsName => 'Enter Person\'s Name';

  @override
  String get addPerson => 'Add Person';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'Tag other segments from this speaker ($selected/$total)';
  }

  @override
  String get tagOtherSegments => 'Tag other segments';

  @override
  String get managePeople => 'Manage People';

  @override
  String get shareViaSms => 'Κοινοποίηση μέσω SMS';

  @override
  String get selectContactsToShareSummary => 'Επιλέξτε επαφές για κοινοποίηση της περίληψης συνομιλίας';

  @override
  String get searchContactsHint => 'Αναζήτηση επαφών...';

  @override
  String contactsSelectedCount(int count) {
    return '$count επιλεγμένα';
  }

  @override
  String get clearAllSelection => 'Εκκαθάριση όλων';

  @override
  String get selectContactsToShare => 'Επιλέξτε επαφές για κοινοποίηση';

  @override
  String shareWithContactCount(int count) {
    return 'Κοινοποίηση σε $count επαφή';
  }

  @override
  String shareWithContactsCount(int count) {
    return 'Κοινοποίηση σε $count επαφές';
  }

  @override
  String get contactsPermissionRequired => 'Απαιτείται άδεια επαφών';

  @override
  String get contactsPermissionRequiredForSms => 'Απαιτείται άδεια επαφών για κοινοποίηση μέσω SMS';

  @override
  String get grantContactsPermissionForSms => 'Παρακαλώ δώστε άδεια επαφών για κοινοποίηση μέσω SMS';

  @override
  String get noContactsWithPhoneNumbers => 'Δεν βρέθηκαν επαφές με τηλεφωνικούς αριθμούς';

  @override
  String get noContactsMatchSearch => 'Καμία επαφή δεν ταιριάζει με την αναζήτησή σας';

  @override
  String get failedToLoadContacts => 'Αποτυχία φόρτωσης επαφών';

  @override
  String get failedToPrepareConversationForSharing =>
      'Αποτυχία προετοιμασίας συνομιλίας για κοινοποίηση. Παρακαλώ δοκιμάστε ξανά.';

  @override
  String get couldNotOpenSmsApp => 'Δεν ήταν δυνατό το άνοιγμα της εφαρμογής SMS. Παρακαλώ δοκιμάστε ξανά.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'Εδώ είναι τι συζητήσαμε: $link';
  }

  @override
  String get wifiSync => 'Συγχρονισμός WiFi';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item αντιγράφηκε στο πρόχειρο';
  }

  @override
  String get wifiConnectionFailedTitle => 'Connection Failed';

  @override
  String connectingToDeviceName(String deviceName) {
    return 'Connecting to $deviceName';
  }

  @override
  String enableDeviceWifi(String deviceName) {
    return 'Enable $deviceName\'s WiFi';
  }

  @override
  String connectToDeviceName(String deviceName) {
    return 'Connect to $deviceName';
  }

  @override
  String get recordingDetails => 'Recording Details';

  @override
  String get storageLocationSdCard => 'SD Card';

  @override
  String get storageLocationLimitlessPendant => 'Limitless Pendant';

  @override
  String get storageLocationPhone => 'Phone';

  @override
  String get storageLocationPhoneMemory => 'Phone (Memory)';

  @override
  String storedOnDevice(String deviceName) {
    return 'Stored on $deviceName';
  }

  @override
  String get transferring => 'Transferring...';

  @override
  String get transferRequired => 'Transfer Required';

  @override
  String get downloadingAudioFromSdCard => 'Downloading audio from your device\'s SD card';

  @override
  String get transferRequiredDescription =>
      'This recording is stored on your device\'s SD card. Transfer it to your phone to play or share.';

  @override
  String get cancelTransfer => 'Cancel Transfer';

  @override
  String get transferToPhone => 'Transfer to Phone';

  @override
  String get privateAndSecureOnDevice => 'Private & secure on your device';

  @override
  String get recordingInfo => 'Recording Info';

  @override
  String get transferInProgress => 'Transfer in progress...';

  @override
  String get shareRecording => 'Share Recording';

  @override
  String get deleteRecordingConfirmation =>
      'Are you sure you want to permanently delete this recording? This can\'t be undone.';

  @override
  String get recordingIdLabel => 'Recording ID';

  @override
  String get dateTimeLabel => 'Date & Time';

  @override
  String get durationLabel => 'Duration';

  @override
  String get audioFormatLabel => 'Audio Format';

  @override
  String get storageLocationLabel => 'Storage Location';

  @override
  String get estimatedSizeLabel => 'Estimated Size';

  @override
  String get deviceModelLabel => 'Device Model';

  @override
  String get deviceIdLabel => 'Device ID';

  @override
  String get statusLabel => 'Status';

  @override
  String get statusProcessed => 'Processed';

  @override
  String get statusUnprocessed => 'Unprocessed';

  @override
  String get switchedToFastTransfer => 'Switched to Fast Transfer';

  @override
  String get transferCompleteMessage => 'Transfer complete! You can now play this recording.';

  @override
  String transferFailedMessage(String error) {
    return 'Transfer failed: $error';
  }

  @override
  String get transferCancelled => 'Transfer cancelled';

  @override
  String get fastTransferEnabled => 'Η γρήγορη μεταφορά ενεργοποιήθηκε';

  @override
  String get bluetoothSyncEnabled => 'Ο συγχρονισμός Bluetooth ενεργοποιήθηκε';

  @override
  String get enableFastTransfer => 'Ενεργοποίηση γρήγορης μεταφοράς';

  @override
  String get fastTransferDescription =>
      'Η γρήγορη μεταφορά χρησιμοποιεί WiFi για ~5x ταχύτερες ταχύτητες. Το τηλέφωνό σας θα συνδεθεί προσωρινά στο δίκτυο WiFi της συσκευής Omi κατά τη μεταφορά.';

  @override
  String get internetAccessPausedDuringTransfer => 'Η πρόσβαση στο διαδίκτυο διακόπτεται κατά τη μεταφορά';

  @override
  String get chooseTransferMethodDescription =>
      'Επιλέξτε πώς μεταφέρονται οι εγγραφές από τη συσκευή Omi στο τηλέφωνό σας.';

  @override
  String get wifiSpeed => '~150 KB/s μέσω WiFi';

  @override
  String get fiveTimesFaster => '5X ΓΡΗΓΟΡΟΤΕΡΟ';

  @override
  String get fastTransferMethodDescription =>
      'Δημιουργεί απευθείας σύνδεση WiFi με τη συσκευή Omi. Το τηλέφωνό σας αποσυνδέεται προσωρινά από το κανονικό WiFi κατά τη μεταφορά.';

  @override
  String get bluetooth => 'Bluetooth';

  @override
  String get bleSpeed => '~30 KB/s μέσω BLE';

  @override
  String get bluetoothMethodDescription =>
      'Χρησιμοποιεί τυπική σύνδεση Bluetooth Low Energy. Πιο αργό αλλά δεν επηρεάζει τη σύνδεση WiFi.';

  @override
  String get selected => 'Επιλεγμένο';

  @override
  String get selectOption => 'Επιλογή';

  @override
  String get lowBatteryAlertTitle => 'Ειδοποίηση χαμηλής μπαταρίας';

  @override
  String get lowBatteryAlertBody => 'Η μπαταρία της συσκευής σας είναι χαμηλή. Ώρα για επαναφόρτιση! 🔋';

  @override
  String get deviceDisconnectedNotificationTitle => 'Η συσκευή Omi σας αποσυνδέθηκε';

  @override
  String get deviceDisconnectedNotificationBody =>
      'Παρακαλώ επανασυνδεθείτε για να συνεχίσετε να χρησιμοποιείτε το Omi.';

  @override
  String get firmwareUpdateAvailable => 'Διαθέσιμη ενημέρωση υλικολογισμικού';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'Μια νέα ενημέρωση υλικολογισμικού ($version) είναι διαθέσιμη για τη συσκευή Omi σας. Θέλετε να ενημερώσετε τώρα;';
  }

  @override
  String get later => 'Αργότερα';

  @override
  String get appDeletedSuccessfully => 'Η εφαρμογή διαγράφηκε επιτυχώς';

  @override
  String get appDeleteFailed => 'Αποτυχία διαγραφής εφαρμογής. Δοκιμάστε ξανά αργότερα.';

  @override
  String get appVisibilityChangedSuccessfully =>
      'Η ορατότητα της εφαρμογής άλλαξε επιτυχώς. Μπορεί να χρειαστούν μερικά λεπτά.';

  @override
  String get errorActivatingAppIntegration =>
      'Σφάλμα κατά την ενεργοποίηση της εφαρμογής. Αν είναι εφαρμογή ενσωμάτωσης, βεβαιωθείτε ότι η ρύθμιση έχει ολοκληρωθεί.';

  @override
  String get errorUpdatingAppStatus => 'Παρουσιάστηκε σφάλμα κατά την ενημέρωση της κατάστασης της εφαρμογής.';

  @override
  String get calculatingETA => 'Calculating...';

  @override
  String aboutMinutesRemaining(int minutes) {
    return 'About $minutes minutes remaining';
  }

  @override
  String get aboutAMinuteRemaining => 'About a minute remaining';

  @override
  String get almostDone => 'Almost done...';

  @override
  String get omiSays => 'omi says';

  @override
  String get analyzingYourData => 'Analyzing your data...';

  @override
  String migratingToProtection(String level) {
    return 'Migrating to $level protection...';
  }

  @override
  String get noDataToMigrateFinalizing => 'No data to migrate. Finalizing...';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return 'Migrating $itemType... $percentage%';
  }

  @override
  String get allObjectsMigratedFinalizing => 'All objects migrated. Finalizing...';

  @override
  String get migrationErrorOccurred => 'An error occurred during migration. Please try again.';

  @override
  String get migrationComplete => 'Migration complete!';

  @override
  String dataProtectedWithSettings(String level) {
    return 'Your data is now protected with the new $level settings.';
  }

  @override
  String get chatsLowercase => 'chats';

  @override
  String get dataLowercase => 'data';

  @override
  String get fallNotificationTitle => 'Ouch';

  @override
  String get fallNotificationBody => 'Did you fall?';

  @override
  String get importantConversationTitle => 'Σημαντική συνομιλία';

  @override
  String get importantConversationBody => 'Μόλις είχατε μια σημαντική συνομιλία. Πατήστε για να μοιραστείτε τη σύνοψη.';

  @override
  String get templateName => 'Όνομα προτύπου';

  @override
  String get templateNameHint => 'π.χ., Εξαγωγέας ενεργειών συναντήσεων';

  @override
  String get nameMustBeAtLeast3Characters => 'Το όνομα πρέπει να έχει τουλάχιστον 3 χαρακτήρες';

  @override
  String get conversationPromptHint => 'π.χ., Εξάγετε ενέργειες, αποφάσεις και βασικά συμπεράσματα από τη συνομιλία.';

  @override
  String get pleaseEnterAppPrompt => 'Παρακαλώ εισάγετε μια προτροπή για την εφαρμογή σας';

  @override
  String get promptMustBeAtLeast10Characters => 'Η προτροπή πρέπει να έχει τουλάχιστον 10 χαρακτήρες';

  @override
  String get anyoneCanDiscoverTemplate => 'Ο καθένας μπορεί να ανακαλύψει το πρότυπό σας';

  @override
  String get onlyYouCanUseTemplate => 'Μόνο εσείς μπορείτε να χρησιμοποιήσετε αυτό το πρότυπο';

  @override
  String get generatingDescription => 'Δημιουργία περιγραφής...';

  @override
  String get creatingAppIcon => 'Δημιουργία εικονιδίου...';

  @override
  String get installingApp => 'Εγκατάσταση εφαρμογής...';

  @override
  String get appCreatedAndInstalled => 'Η εφαρμογή δημιουργήθηκε και εγκαταστάθηκε!';

  @override
  String get appCreatedSuccessfully => 'Η εφαρμογή δημιουργήθηκε επιτυχώς!';

  @override
  String get failedToCreateApp => 'Αποτυχία δημιουργίας. Παρακαλώ δοκιμάστε ξανά.';

  @override
  String get addAppSelectCoreCapability => 'Please select one more core capability for your app to proceed';

  @override
  String get addAppSelectPaymentPlan => 'Please select a payment plan and enter a price for your app';

  @override
  String get addAppSelectCapability => 'Please select at least one capability for your app';

  @override
  String get addAppSelectLogo => 'Please select a logo for your app';

  @override
  String get addAppEnterChatPrompt => 'Please enter a chat prompt for your app';

  @override
  String get addAppEnterConversationPrompt => 'Please enter a conversation prompt for your app';

  @override
  String get addAppSelectTriggerEvent => 'Please select a trigger event for your app';

  @override
  String get addAppEnterWebhookUrl => 'Please enter a webhook URL for your app';

  @override
  String get addAppSelectCategory => 'Please select a category for your app';

  @override
  String get addAppFillRequiredFields => 'Please fill in all the required fields correctly';

  @override
  String get addAppUpdatedSuccess => 'App updated successfully 🚀';

  @override
  String get addAppUpdateFailed => 'Failed to update app. Please try again later';

  @override
  String get addAppSubmittedSuccess => 'App submitted successfully 🚀';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'Error opening file picker: $message';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'Error selecting image: $error';
  }

  @override
  String get addAppPhotosPermissionDenied =>
      'Photos permission denied. Please allow access to photos to select an image';

  @override
  String get addAppErrorSelectingImageRetry => 'Error selecting image. Please try again.';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'Error selecting thumbnail: $error';
  }

  @override
  String get addAppErrorSelectingThumbnailRetry => 'Error selecting thumbnail. Please try again.';

  @override
  String get addAppCapabilityConflictWithPersona => 'Other capabilities cannot be selected with Persona';

  @override
  String get addAppPersonaConflictWithCapabilities => 'Persona cannot be selected with other capabilities';

  @override
  String get personaTwitterHandleNotFound => 'Twitter handle not found';

  @override
  String get personaTwitterHandleSuspended => 'Twitter handle is suspended';

  @override
  String get personaFailedToVerifyTwitter => 'Failed to verify Twitter handle';

  @override
  String get personaFailedToFetch => 'Failed to fetch your persona';

  @override
  String get personaFailedToCreate => 'Failed to create your persona';

  @override
  String get personaConnectKnowledgeSource => 'Please connect at least one knowledge data source (Omi or Twitter)';

  @override
  String get personaUpdatedSuccessfully => 'Persona updated successfully';

  @override
  String get personaFailedToUpdate => 'Failed to update persona';

  @override
  String get personaPleaseSelectImage => 'Please select an image';

  @override
  String get personaFailedToCreateTryLater => 'Failed to create your persona. Please try again later.';

  @override
  String personaFailedToCreateWithError(String error) {
    return 'Failed to create persona: $error';
  }

  @override
  String get personaFailedToEnable => 'Failed to enable persona';

  @override
  String personaErrorEnablingWithError(String error) {
    return 'Error enabling persona: $error';
  }

  @override
  String get paymentFailedToFetchCountries => 'Failed to fetch supported countries. Please try again later.';

  @override
  String get paymentFailedToSetDefault => 'Failed to set default payment method. Please try again later.';

  @override
  String get paymentFailedToSavePaypal => 'Failed to save PayPal details. Please try again later.';

  @override
  String get paypalEmailHint => 'nik@example.com';

  @override
  String get paypalMeLinkHint => 'paypal.me/nik';

  @override
  String get paymentMethodStripe => 'Stripe';

  @override
  String get paymentMethodPayPal => 'PayPal';

  @override
  String get paymentStatusActive => 'Active';

  @override
  String get paymentStatusConnected => 'Connected';

  @override
  String get paymentStatusNotConnected => 'Not Connected';
}
