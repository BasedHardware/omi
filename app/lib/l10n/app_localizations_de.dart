// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for German (`de`).
class AppLocalizationsDe extends AppLocalizations {
  AppLocalizationsDe([String locale = 'de']) : super(locale);

  @override
  String get welcomeActionItemsDescription =>
      'Ihre KI extrahiert automatisch Aufgaben aus Ihren Unterhaltungen. Sie erscheinen hier, wenn sie erstellt wurden.';

  @override
  String get chatAppsProblemFailed => 'Etwas ist schiefgelaufen. Versuche es erneut.';

  @override
  String get deviceOnboardingStarConversation => 'Laufendes Gespräch mit Stern markieren';

  @override
  String get deleteAll => 'Alle löschen';

  @override
  String get copySummary => 'Zusammenfassung kopieren';

  @override
  String get locationAccessDesc => 'Damit Omi festhalten kann, wo deine Gespräche stattgefunden haben.';

  @override
  String get firmwareUpdate => 'Firmware-Update';

  @override
  String get chatMessages => 'Nachrichten';

  @override
  String get showEventsNoParticipants => 'Ereignisse ohne Teilnehmer anzeigen';

  @override
  String get sharePeriodYear => 'Dieses Jahr hat Omi:';

  @override
  String get dreamReportRunFailed => 'Dream konnte nicht gestartet werden. Versuche es erneut.';

  @override
  String get sttModelAccuracy => 'Genauigkeit';

  @override
  String get scopes => 'Berechtigungen';

  @override
  String get deleteFlowFeedbackSubtitle => 'Was hätte Omi für dich besser gemacht?';

  @override
  String appDataAccessTitle(String appName) {
    return '$appName Zugriff erlauben?';
  }

  @override
  String get pendantStorageAlmostFull =>
      'Der Speicher des Pendants ist fast voll — lass die App geöffnet, um zu synchronisieren.';

  @override
  String get deviceOnboardingAllSetDoublePressBadge => '2×';

  @override
  String get copyErrorMessage => 'Fehlermeldung kopieren';

  @override
  String get filterMemories => 'Erinnerungen filtern';

  @override
  String get helpsDiagnoseIssuesAutoDeletes =>
      'Hilft bei der Diagnose von Problemen. Wird nach 3 Tagen automatisch gelöscht.';

  @override
  String get locationServiceDisabledDesc =>
      'Ortungsdienste sind auf diesem Gerät deaktiviert. Aktiviere sie in den Einstellungen.';

  @override
  String chatAppsIsConnected(String app) {
    return '$app ist verbunden';
  }

  @override
  String get paymentMethodStripe => 'Stripe';

  @override
  String get deleteReasonTechnicalIssues => 'Zu viele technische Probleme';

  @override
  String get payments => 'Zahlungen';

  @override
  String get verifiedFallback => 'Verifiziert';

  @override
  String get pleaseWait => 'Bitte warten…';

  @override
  String get appLanguage => 'App-Sprache';

  @override
  String get unknownApp => 'Unbekannte App';

  @override
  String get appReEnableFailedBody => 'Diese App konnte nicht reaktiviert werden. Bitte versuche es erneut.';

  @override
  String get somethingWentWrongTryAgain => 'Etwas ist schiefgelaufen! Bitte versuchen Sie es später erneut.';

  @override
  String get upgradeScheduled => 'Upgrade geplant';

  @override
  String get wrappedBuddiesLabel => 'FREUNDE';

  @override
  String get chatBlockShowMore => 'Mehr anzeigen';

  @override
  String get subscriptionSuccessfulCharged => 'Abonnement erfolgreich belastet';

  @override
  String get phoneCall => 'Anruf';

  @override
  String get chatAppsRefreshFailed => 'Aktualisierung fehlgeschlagen. Es wird der letzte bekannte Stand angezeigt.';

  @override
  String get noDesktopAccess => 'Funktioniert nicht auf dem Desktop';

  @override
  String get areYouSure => 'Sind Sie sicher?';

  @override
  String get resubscribe => 'Erneut abonnieren';

  @override
  String voiceMatchMeterLabel(String level) {
    return 'Stimmübereinstimmung: $level';
  }

  @override
  String get syncingBackground => 'Wir synchronisieren Ihre Aufnahmen im Hintergrund weiter.';

  @override
  String get signOutQuestion => 'Abmelden?';

  @override
  String chatAppsReadOnlyBanner(String app) {
    return 'Schreibgeschützt. Antworte Omi in $app.';
  }

  @override
  String get connected => 'Verbunden';

  @override
  String get shareStatsMessage => 'Ich teile meine Omi-Statistiken! (omi.me - mein Always-On KI-Assistent)';

  @override
  String get frequencyMinimal => 'Minimal';

  @override
  String get addAppSelectLogo => 'Bitte wählen Sie ein Logo für Ihre App aus';

  @override
  String get integrationInstructions => 'Integrationsanleitung';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'Bedienungshilfen-Berechtigungsstatus: $status. Bitte überprüfen Sie die Systemeinstellungen.';
  }

  @override
  String get wrappedCompleted => 'abgeschlossen';

  @override
  String get remaining => 'Verbleibend';

  @override
  String get onDeviceIntensive => 'On-Device-Transkription ist rechenintensiv.';

  @override
  String get diagnosticsVerdictTrouble => 'Probleme beim Verbinden';

  @override
  String deviceOnboardingVoiceReplyPreviewThroughDevice(String device) {
    return 'Durch $device';
  }

  @override
  String get copyConfig => 'Konfiguration kopieren';

  @override
  String accessesDataTypes(String dataTypes) {
    return 'Greift auf $dataTypes zu';
  }

  @override
  String get chatAppsWaitlistConfirmed => 'Danke. WhatsApp erscheint hier, sobald es fertig ist.';

  @override
  String get undo => 'Rückgängig';

  @override
  String get phoneContactsAccessTitle => 'Zugriff auf Kontakte erlauben';

  @override
  String confidenceIsConfirmed(String name) {
    return '$name ist „Bestätigt“. Du musst nichts weiter tun.';
  }

  @override
  String get wrappedMovie => 'FILM';

  @override
  String get wrappedStruggleLabelUpper => 'KAMPF';

  @override
  String get appleHealthFeatureChatDesc =>
      'Frage Omi nach deinen Schritten, deinem Schlaf, deiner Herzfrequenz und deinen Workouts.';

  @override
  String get writeReviewOptional => 'Bewertung schreiben (optional)';

  @override
  String get pairNewDevice => 'Neues Gerät koppeln';

  @override
  String chatUsedOfLimitCompute(String used, String limit) {
    return '$used von $limit Rechenbudget verwendet';
  }

  @override
  String get dailySummary => 'Tägliche Zusammenfassung';

  @override
  String get pleaseEnterYourName => 'Bitte geben Sie Ihren Namen ein';

  @override
  String get continueWithoutDevice => 'Ohne Gerät fortfahren';

  @override
  String get configure => 'Konfigurieren';

  @override
  String get createApp => 'App erstellen';

  @override
  String get invalidUrlError => 'Bitte geben Sie eine gültige URL ein';

  @override
  String get appClosed => 'App geschlossen';

  @override
  String get downgradeToFreemiumAction => 'Auf Gratisversion wechseln';

  @override
  String get chatAppsUseTelegramForNow => 'Vorerst Telegram nutzen';

  @override
  String get wrappedBestMomentsBadge => 'Beste Momente';

  @override
  String get storageSection => 'Speicher';

  @override
  String get pauseResumeRecording => 'Aufnahme pausieren/fortsetzen';

  @override
  String get phoneUnmute => 'Stummschaltung aufheben';

  @override
  String get youreAllSet => 'Alles bereit!';

  @override
  String get migrationComplete => 'Migration abgeschlossen';

  @override
  String get paymentAppCost => 'App-Kosten';

  @override
  String get deviceOnboardingFinish => 'Fertig';

  @override
  String get noVerifiedNumbers => 'Keine verifizierten Nummern';

  @override
  String get connectAiAssistantsToData => 'KI-Assistenten mit Ihren Daten verbinden';

  @override
  String get keyNameHint => 'z.B. Claude Desktop';

  @override
  String get paymentMethods => 'Zahlungsmethoden';

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'Bedienungshilfen-Berechtigung konnte nicht überprüft werden: $error';
  }

  @override
  String get confidenceReasonAutoOnly => 'Automatisch markiert, noch nicht bestätigt';

  @override
  String whatsNewInVersion(String version) {
    return 'Neuigkeiten in $version';
  }

  @override
  String get selectYourLanguage => 'Wählen Sie Ihre Sprache';

  @override
  String get memoryClearedSuccess => 'Omis Gedächtnis über Sie wurde gelöscht';

  @override
  String get memoryContentHint => 'Ich bevorzuge Besprechungen am Vormittag.';

  @override
  String get dreamReportTitle => 'Dream-Bericht';

  @override
  String importErrorGeneric(String error) {
    return 'Fehler: $error';
  }

  @override
  String get completionRate => 'Abschlussrate';

  @override
  String get trackPersonalGoals => 'Persönliche Ziele auf der Startseite verfolgen';

  @override
  String get wrappedTryAgain => 'Erneut versuchen';

  @override
  String get dataProtection => 'Datenschutz';

  @override
  String get yourConversations => 'Deine Unterhaltungen';

  @override
  String pdfTitleLabel(String title) {
    return 'Titel: $title';
  }

  @override
  String get sendRawAudioToOmiDescription =>
      'Deaktivieren, damit kein Roh-Audio an Omi gesendet wird. Transkripte und für Cloud-Funktionen benötigte Daten können weiterhin an Omi gesendet werden.';

  @override
  String get entityLoadFailed => 'Diese Seite konnte nicht geladen werden.';

  @override
  String get networkNameSsid => 'Netzwerkname (SSID)';

  @override
  String get discovery => 'Entdeckung';

  @override
  String get rayBanMetaMicPickerConnectError =>
      'Verbindung mit diesem Mikrofon fehlgeschlagen. Stelle sicher, dass es in den iPhone-Einstellungen verbunden ist.';

  @override
  String get fairUseAboutTitle => 'Über faire Nutzung';

  @override
  String get wrappedYouTalkedAbout => 'Du hast gesprochen über';

  @override
  String get downgradeLimitQuality => '30 % geringere Transkriptionsqualität';

  @override
  String get sharedTasksUnknownSender => 'Jemand';

  @override
  String get selectAReason => 'Wähle einen Grund';

  @override
  String get wrappedWinLabel => 'SIEG';

  @override
  String get configuration => 'Konfiguration';

  @override
  String get noFolder => 'Kein Ordner';

  @override
  String get manifestRefreshedSuccess => 'Manifest erfolgreich aktualisiert';

  @override
  String get paymentStatusActive => 'Aktiv';

  @override
  String get linkKeyMismatch => 'Verbindungsschlüssel stimmt nicht überein';

  @override
  String speakerTagPromptProgress(int current, int total) {
    return '$current von $total';
  }

  @override
  String get updateRequiredMessage =>
      'Diese Version von Omi wird nicht mehr unterstützt. Aktualisieren Sie, um weiterhin aufzunehmen und zu synchronisieren.';

  @override
  String get sharePeriodMonth => 'Diesen Monat hat Omi:';

  @override
  String get rollbackToStableFirmware => 'Auf stabile Firmware zurücksetzen';

  @override
  String get paymentStatusConnected => 'Verbunden';

  @override
  String get findDeviceNoneTitle => 'Kein Omi gefunden';

  @override
  String get appIdCopiedToClipboard => 'App-ID in Zwischenablage kopiert';

  @override
  String get bySubmittingYouAgreeToOmi => 'Mit dem Absenden stimmen Sie Omi ';

  @override
  String get filterRating => 'Bewertung';

  @override
  String get usageAtWork => 'Bei der Arbeit';

  @override
  String get tasksCleanTodayMessage => 'Dadurch werden nur Fristen entfernt';

  @override
  String get ignoredVoicesSubtitle => 'TV, Podcasts und andere Stimmen, die du als „Keine Person“ markiert hast';

  @override
  String get permissionEnable => 'Aktivieren';

  @override
  String integrationComingSoon(String appName) {
    return '$appName wird noch nicht unterstützt.';
  }

  @override
  String get sttModelLower => 'Niedriger';

  @override
  String get loadingYourMemories => 'Deine Erinnerungen werden geladen…';

  @override
  String get followUpQuestions => 'Folgefragen';

  @override
  String get previousDay => 'Vorheriger Tag';

  @override
  String fairUseCaseRefCopied(String caseRef) {
    return '$caseRef kopiert';
  }

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get recordingPaused => 'Aufnahme pausiert';

  @override
  String get cannotReportOwnMessages => 'Sie können Ihre eigenen Nachrichten nicht melden';

  @override
  String get enterWordsHint => 'Wörter eingeben (durch Kommas getrennt)';

  @override
  String get audioDownloadFailed => 'Audio-Download fehlgeschlagen';

  @override
  String get clearMemoryMessage => 'Alle Ihre Erinnerungen werden gelöscht. Dies kann nicht rückgängig gemacht werden.';

  @override
  String get templateNameHint => 'z.B. Meeting-Aufgaben-Extraktor';

  @override
  String speakerLabelTalkTime(String duration) {
    return '$duration dieser Stimme';
  }

  @override
  String get recordingMode => 'Aufnahmemodus';

  @override
  String get cancelReasonOther => 'Sonstiges';

  @override
  String get sttModelHigher => 'Höher';

  @override
  String get settingUpSystemAudioCapture => 'Systemtonaufnahme wird eingerichtet';

  @override
  String memoriesCount(int count) {
    return '$count Erinnerungen';
  }

  @override
  String get noSpecificDataAccessConfigured => 'Kein spezifischer Datenzugriff konfiguriert.';

  @override
  String get recordingIdLabel => 'Aufnahme-ID';

  @override
  String get highlights => 'Höhepunkte';

  @override
  String get phoneTryAgain => 'Erneut versuchen';

  @override
  String chatAppsCouldNotOpen(String app) {
    return '$app konnte nicht geöffnet werden. Stelle sicher, dass die App installiert ist, und versuche es erneut.';
  }

  @override
  String get onDeviceTranscriptionDesc => 'Die Transkription wird lokal auf Ihrem Gerät verarbeitet';

  @override
  String get chatAppsTryPromise => 'Was habe ich Sam gestern versprochen?';

  @override
  String get paymentStatusNotConnected => 'Nicht verbunden';

  @override
  String get intervalSeconds => 'Intervall (Sekunden)';

  @override
  String get authorize => 'Autorisieren';

  @override
  String get settingsHeader => 'EINSTELLUNGEN';

  @override
  String get personNameAlreadyExists => 'Dieser Personenname existiert bereits';

  @override
  String get deviceOnboardingVoiceReplyPreviewThroughCurrentOutput => 'Über die aktuelle Audioausgabe';

  @override
  String get monthJun => 'Jun';

  @override
  String selectedCount(int count) {
    return '$count ausgewählt';
  }

  @override
  String get batteryHistory => 'Batterie';

  @override
  String get noPastChats => 'Deine Chats mit Omi erscheinen hier.';

  @override
  String get chatAppsDoesSave => 'Speichert Erinnerungen und verwaltet deine Aufgaben';

  @override
  String get apiKey => 'API-Schlüssel';

  @override
  String get authFailedToLinkGoogle => 'Verknüpfung mit Google fehlgeschlagen, bitte versuchen Sie es erneut.';

  @override
  String audioUploadFailedKeptLocal(String duration) {
    return 'Upload fehlgeschlagen — $duration Audio auf Ihrem Telefon gespeichert.';
  }

  @override
  String get free => 'Kostenlos';

  @override
  String get deselectAllTasksMenu => 'Alle abwählen';

  @override
  String get dreamReportLoadFailed => 'Der Dream-Bericht konnte nicht geladen werden.';

  @override
  String get entityRecentConversations => 'Letzte Gespräche';

  @override
  String get pendantRecordingNote =>
      'Dein Pendant nimmt selbstständig auf. Aufnahmen werden mit deinem Smartphone synchronisiert, solange die App geöffnet ist.';

  @override
  String get manageStorage => 'Speicher verwalten';

  @override
  String get filterSystem => 'Über Sie';

  @override
  String get deleteConsequenceSubscription => 'Alle aktiven Abonnements werden gekündigt.';

  @override
  String get defaultList => 'Standardliste';

  @override
  String get shared => 'Geteilt';

  @override
  String get customVocabulary => 'Benutzerdefiniertes Vokabular';

  @override
  String get feedbackTitleAudioQuality => 'Welche Probleme hast du erlebt?';

  @override
  String get thisActionCannotBeUndone => 'Dies kann nicht rückgängig gemacht werden.';

  @override
  String errorRequestingPermission(String error) {
    return 'Fehler beim Anfordern der Berechtigung: $error';
  }

  @override
  String get recapRegenerateFailed =>
      'Zusammenfassung konnte nicht neu erstellt werden. Bitte später erneut versuchen.';

  @override
  String get result => 'Ergebnis:';

  @override
  String get statusCallMissed => 'Anruf verpasst';

  @override
  String get diagnosticsLongestGap => 'Längste Lücke';

  @override
  String get noLogFilesFound => 'Keine Protokolldateien gefunden.';

  @override
  String get speechTranscriptionSectionTitle => 'Sprache und Transkription';

  @override
  String get syncNow => 'Jetzt synchronisieren';

  @override
  String get sttUsePrimaryLanguage => 'Hauptsprache verwenden';

  @override
  String get importUnsupportedFileType => 'Dieser Dateityp kann nicht importiert werden.';

  @override
  String get chatSendMessage => 'Nachricht senden';

  @override
  String get syncCardAllBackedUp => 'Alle Aufnahmen synchronisiert';

  @override
  String get settings => 'Einstellungen';

  @override
  String get backgroundLocationDeniedDesc =>
      'Bitte gehen Sie zu den Geräteeinstellungen und setzen Sie die Standortberechtigung auf \'Immer zulassen\'';

  @override
  String get computationallyIntensive => 'Die Transkription auf dem Gerät ist rechenintensiv.';

  @override
  String get and => ' und ';

  @override
  String get yourVerifiedNumbers => 'Ihre verifizierten Nummern';

  @override
  String get tasksCleanTodayTitle => 'Heutige Aufgaben bereinigen?';

  @override
  String get microphonePermission => 'Mikrofonberechtigung';

  @override
  String get failedToUpdateConversationTitle => 'Fehler beim Aktualisieren des Gesprächstitels';

  @override
  String get appsDisconnected => 'Deine Apps und Integrationen werden getrennt.';

  @override
  String get live => 'Live';

  @override
  String get connectionFailed => 'Verbindung fehlgeschlagen';

  @override
  String get selectImages => 'Bilder auswählen';

  @override
  String get playbackAudioNetworkFailed => 'Verbindung prüfen';

  @override
  String get paypalEmail => 'PayPal-E-Mail';

  @override
  String get chatAppsOnTheList => 'Auf der Liste';

  @override
  String get generateSummary => 'Zusammenfassung erstellen';

  @override
  String get categoryHealth => 'Gesundheit';

  @override
  String get transcribeLaterStorageFull =>
      'Auf deinem Smartphone wird der Speicher knapp, daher ist die Aufnahme pausiert. Gib Speicher frei oder lade deine Aufnahmen hoch – danach wird sie automatisch fortgesetzt.';

  @override
  String get chatAppsNoChatsTitle => 'Noch keine Chats';

  @override
  String get onboardingSetupStepPersonalize => 'Dein Erlebnis wird personalisiert';

  @override
  String get leaveUnselectedTasks => 'Unmarkiert lassen, um Aufgaben ohne Projekt zu erstellen';

  @override
  String get wrappedButYouPushedThroughEmoji => 'Aber du hast es geschafft 💪';

  @override
  String get needHelp => 'Brauchen Sie Hilfe?';

  @override
  String get confirmAndCancel => 'Bestätigen und kündigen';

  @override
  String get frequencyDescHigh => 'Mehr Vorschläge, etwa 6–9 pro Tag';

  @override
  String get copyLink => 'Link kopieren';

  @override
  String get dreamReportLiveBanner =>
      'Dream wendet diese Änderungen selbstständig an. Mache sie unter Letzte Änderungen rückgängig.';

  @override
  String get enterActionItemDescription => 'Aufgabenbeschreibung eingeben';

  @override
  String chatAppsInChannel(String app) {
    return 'In $app';
  }

  @override
  String get links => 'Links';

  @override
  String get dreamReportEmptyTitle => 'Noch keine Durchläufe';

  @override
  String get monthJan => 'Jan';

  @override
  String get wrappedMostProductiveDay => 'Am produktivsten';

  @override
  String get productUpdate => 'Produktaktualisierung';

  @override
  String get addYourReview => 'Bewertung hinzufügen';

  @override
  String get raybanMetaImageCaptureReady => 'Bildaufnahme bereit';

  @override
  String get displayUpcomingMeetingsDescription => 'Anstehende Meetings in der Menüleiste anzeigen';

  @override
  String get whatWeCollect => 'Was wir sammeln';

  @override
  String get connectPayPalToReceivePayments => 'Verbinden Sie Ihr PayPal-Konto, um Zahlungen für Ihre Apps zu erhalten';

  @override
  String get justAMoment => 'Einen Moment bitte';

  @override
  String get chatReplyServerError => 'Auf unserer Seite ist etwas schiefgelaufen. Bitte versuche es erneut.';

  @override
  String get transferInProgress => 'Übertragung läuft';

  @override
  String get usageAll => 'Gesamte Zeit';

  @override
  String get failedToLoadContacts => 'Kontakte konnten nicht geladen werden';

  @override
  String appUsersCount(int count) {
    return '$count+ Nutzer';
  }

  @override
  String get report => 'Melden';

  @override
  String get languageLabel => 'Sprache';

  @override
  String verifiedOnDate(String date) {
    return 'Verifiziert am $date';
  }

  @override
  String get customVocabularyHeader => 'BENUTZERDEFINIERTES VOKABULAR';

  @override
  String otaRebooting(String deviceName) {
    return '$deviceName startet mit der neuen Firmware neu.';
  }

  @override
  String get mcpServer => 'MCP-Server';

  @override
  String get findDevice => 'Finden';

  @override
  String get msgUploadAttachedFileFailed => 'Hochladen der angehängten Datei fehlgeschlagen.';

  @override
  String get appName => 'App Name';

  @override
  String get pairingTitlePlaudNote => 'Plaud Note in den Kopplungsmodus versetzen';

  @override
  String get moreOptions => 'Weitere Optionen';

  @override
  String get noConversationsHeroMessage =>
      'Aufgenommene Unterhaltungen erscheinen hier. Tippe auf der Startseite auf die Aufnahmetaste, um deine erste aufzunehmen.';

  @override
  String get finish => 'Beenden';

  @override
  String get goBack => 'Zurück';

  @override
  String get apiKeysDescription =>
      'API-Schlüssel werden zur Authentifizierung verwendet, wenn Ihre App mit dem Omi-Server kommuniziert. Sie ermöglichen Ihrer Anwendung, Erinnerungen zu erstellen und sicher auf andere Omi-Dienste zuzugreifen.';

  @override
  String get sttProviderSpeechmatics => 'Speechmatics';

  @override
  String get setWebhookUrlInSettings => 'Bitte legen Sie die Webhook-URL in den Entwicklereinstellungen fest.';

  @override
  String get dailyScoreBreakdown => 'Tages-Score Aufschlüsselung';

  @override
  String get showMeetingsMenuBarDesc =>
      'Anzeige Ihres nächsten Meetings und der Zeit bis zum Beginn in der macOS-Menüleiste';

  @override
  String get tapToTrackThisGoal => 'Tippen, um dieses Ziel zu verfolgen';

  @override
  String get summarizingConversation => 'Unterhaltung wird zusammengefasst…\nDies kann einige Sekunden dauern';

  @override
  String get noInternetConnection => 'Keine Internetverbindung';

  @override
  String diagnosticsCountSincePairing(int count) {
    return '$count seit Kopplung';
  }

  @override
  String get wrappedTasksCreated => 'erstellte Aufgaben';

  @override
  String get deleteConsequenceNoRecovery => 'Dein Konto kann nicht wiederhergestellt werden — auch nicht vom Support.';

  @override
  String get waitForReprocessing => 'Warte, bis die Neuverarbeitung abgeschlossen ist.';

  @override
  String get needYourPermission => 'Wir benötigen Ihre Erlaubnis';

  @override
  String get downgradeLimitSpeakers => 'Sprecher können nicht erkannt werden';

  @override
  String conversationsTodayCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count Gespräche heute.',
      one: '1 Gespräch heute.',
      zero: 'Heute keine Gespräche.',
    );
    return '$_temp0';
  }

  @override
  String get dailyScore => 'TAGES-SCORE';

  @override
  String get reportAnIssue => 'Problem melden';

  @override
  String get invalidKey => 'Ungültige Taste';

  @override
  String get preview => 'Vorschau';

  @override
  String get nextWeek => 'Nächste Woche';

  @override
  String get confidenceUnverified => 'Unbestätigt';

  @override
  String get previewScreenshots => 'Vorschau-Screenshots';

  @override
  String get ledBrightness => 'LED-Helligkeit';

  @override
  String get firmwareUpdateFailedMessage =>
      'Das Update wurde nicht abgeschlossen. Dein Gerät läuft weiter mit der aktuellen Firmware und kann sicher genutzt werden. Lade es auf, halte es in der Nähe deines Telefons und versuche es erneut.';

  @override
  String get loadingProfile => 'Profil wird geladen…';

  @override
  String get deleteRecapConfirmTitle => 'Diese Zusammenfassung löschen?';

  @override
  String get notificationFrequency => 'Benachrichtigungshäufigkeit';

  @override
  String get captureSystemAudioFromMeetings => 'System-Audio von Besprechungen erfassen';

  @override
  String get storeAudioCloudDescription =>
      'Lädt deine Aufnahmen während des Sprechens hoch, damit du sie später wieder abspielen kannst.';

  @override
  String get color => 'Farbe';

  @override
  String get open => 'Öffnen';

  @override
  String get diagnosticsVerdictNoDrops => 'Diese Woche keine Abbrüche';

  @override
  String get autoExtractionFeature => 'Automatisch aus Unterhaltungen extrahiert';

  @override
  String get searchResults => 'Suchergebnisse';

  @override
  String get v2UndetectedMessage =>
      'Wir sehen, dass Sie entweder ein V1-Gerät haben oder Ihr Gerät nicht verbunden ist. Die SD-Karten-Funktionalität ist nur für V2-Geräte verfügbar.';

  @override
  String get endAndProcess => 'Beenden & Verarbeiten';

  @override
  String get noSyncedRecordings => 'Noch keine synchronisierten Aufnahmen';

  @override
  String get coworker => 'Kollege';

  @override
  String get setupQuestionUsage => '2. Wo planst du, dein Omi zu verwenden?';

  @override
  String get pinnedNotSelectable => 'Angeheftet, nicht auswählbar';

  @override
  String get showMore => 'mehr anzeigen ↓';

  @override
  String get createYourFirstMemory => 'Erstelle deine erste Erinnerung, um zu beginnen';

  @override
  String get discardedConversation => 'Verworfene Unterhaltung';

  @override
  String get enableApps => 'Apps aktivieren';

  @override
  String get today => 'Heute';

  @override
  String get showEventsNoParticipantsDesc =>
      'Wenn aktiviert, zeigt \'Demnächst\' Ereignisse ohne Teilnehmer oder Video-Link an.';

  @override
  String get couldNotLoadPage =>
      'Die Seite konnte nicht geladen werden. Prüfe deine Verbindung und versuche es erneut.';

  @override
  String actionItemDeletedResult(String description) {
    return 'Aufgabe \"$description\" gelöscht';
  }

  @override
  String get deleteSampleQuestion => 'Probe löschen?';

  @override
  String get youAreOnAPaidPlan => 'Du hast einen kostenpflichtigen Plan.';

  @override
  String get otaInstallFailed => 'Installation fehlgeschlagen. Dein Gerät läuft weiter mit der aktuellen Firmware.';

  @override
  String get addFirstMemory => 'Fügen Sie Ihre erste Erinnerung hinzu';

  @override
  String get appDeletedSuccessfully => 'App erfolgreich gelöscht';

  @override
  String get chatAppsConnectTelegramMessage => 'Omi öffnet Telegram mit einem privaten Link, der nur für dich ist.';

  @override
  String get phoneSetupStep1Title => 'Verifizieren Sie Ihre Telefonnummer';

  @override
  String get deviceRequirements => 'Ihr Gerät erfüllt nicht die Anforderungen für On-Device-Transkription.';

  @override
  String get confidenceEvidenceHeader => 'Grundlage';

  @override
  String get pleaseEnterAName => 'Bitte geben Sie einen Namen ein.';

  @override
  String get deleteConfirmationWord => 'DELETE';

  @override
  String get speakerTagPromptThatsMe => 'Das bin ich';

  @override
  String get ourCommitment => 'Unser Engagement';

  @override
  String get notificationScopes => 'Benachrichtigungsbereiche';

  @override
  String get autoDeletesAfter3Days => 'Wird nach 3 Tagen automatisch gelöscht';

  @override
  String get initialisingRecorder => 'Initialisiere Aufnahmegerät';

  @override
  String get privateAndSecureOnDevice => 'Auf diesem Telefon gespeichert';

  @override
  String get allObjectsMigratedFinalizing => 'Alle Objekte migriert. Abschließen…';

  @override
  String get chatAppsOpenMessages => 'Nachrichten öffnen';

  @override
  String get upgradeToPro => 'Auf Pro upgraden';

  @override
  String get clientId => 'Client ID';

  @override
  String get backgroundActivity => 'Hintergrundaktivität';

  @override
  String get noSummaryAvailable => 'Keine Zusammenfassung verfügbar';

  @override
  String get failedToUpdateStarred => 'Favoriten-Status konnte nicht aktualisiert werden.';

  @override
  String get omiYourAiCompanion => 'Omi – Ihr KI-Begleiter';

  @override
  String get pleaseSelectReason => 'Bitte wählen Sie einen Grund aus';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Alle $count Erinnerungen werden gelöscht. Dies kann nicht rückgängig gemacht werden.';
  }

  @override
  String get connectNow => 'Jetzt verbinden';

  @override
  String chatAppsDisconnectTitle(String app) {
    return '$app trennen?';
  }

  @override
  String get clearCredentials => 'Anmeldedaten löschen';

  @override
  String get grantContactsPermissionForSms => 'Bitte erteilen Sie die Kontaktberechtigung, um per SMS zu teilen';

  @override
  String get cloudTranscription => 'Cloud-Transkription';

  @override
  String get memoryHistory => 'Verlauf';

  @override
  String get speechSamples => 'Sprachproben';

  @override
  String get wrappedBiggest => 'Größte';

  @override
  String get reviewShowMore => 'Mehr anzeigen';

  @override
  String get triggersWhenDaySummaryGenerated => 'Wird ausgelöst, wenn die Tageszusammenfassung generiert wird.';

  @override
  String get thankYouFeedback => 'Danke für Ihr Feedback!';

  @override
  String get allow => 'Erlauben';

  @override
  String triggeredByType(String triggerType) {
    return 'ausgelöst durch $triggerType';
  }

  @override
  String get howToPair => 'So koppelst du';

  @override
  String get conversationDeveloperTools => 'Entwicklertools in Gesprächen';

  @override
  String get memoryProvenanceIphone => 'iPhone';

  @override
  String get aboutYou => 'Über dich';

  @override
  String get memoryProvenanceMac => 'Mac';

  @override
  String get effectCounts => 'Hilft';

  @override
  String get tagSpeakerIncludingLaterSpeech => 'Spätere Sprache dieses Sprechers ebenfalls markieren';

  @override
  String get storeAudioOnPhone => 'Audio auf dem Telefon speichern';

  @override
  String get developerApiKeys => 'Entwickler-API-Schlüssel';

  @override
  String get wrappedMyBuddiesCard => 'Meine Freunde';

  @override
  String get bulkExportAlreadyExported => 'Alle ausgewählten Aufgaben wurden bereits exportiert';

  @override
  String get popularBadge => 'BELIEBT';

  @override
  String get enableLocationTitle => 'Standort aktivieren';

  @override
  String get feedbackBug => 'Feedback / Fehler';

  @override
  String get good => 'Gut';

  @override
  String get upgradeYourPlan => 'Upgrade deinen Plan';

  @override
  String get exportingAllData =>
      'Deine Daten werden exportiert… Lass Omi geöffnet; bei großen Konten kann das mehrere Minuten dauern.';

  @override
  String get switchAndRestart => 'Wechseln';

  @override
  String get noReposFound => 'Keine Repositories gefunden';

  @override
  String get latest => 'Neueste';

  @override
  String get failedToRevoke => 'Autorisierung konnte nicht widerrufen werden. Bitte versuchen Sie es erneut.';

  @override
  String get appleHealthDisconnectCta => 'Verbindung zu Apple Health trennen';

  @override
  String get chatAppsPrivateMemoriesSubtitle =>
      'Gesundheit, Geld und alles, was du als privat markiert hast, bleibt aus Chat-Apps heraus.';

  @override
  String get deleteFlowFeedbackTitle => 'Erzähl uns mehr';

  @override
  String get failedToConnectTodoistRetry => 'Verbindung zu Todoist fehlgeschlagen. Bitte versuchen Sie es erneut.';

  @override
  String get capturePhoneStorageFull => 'Telefonspeicher voll';

  @override
  String deletePeopleTitle(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count Personen löschen?',
      one: '1 Person löschen?',
    );
    return '$_temp0';
  }

  @override
  String get cleanUpNothingMessage => 'Omi ist gerade bei niemandem unsicher.';

  @override
  String get writeAReviewOptional => 'Bewertung schreiben (optional)';

  @override
  String get syncFailed => 'Synchronisierung fehlgeschlagen';

  @override
  String get audioShareFailed => 'Teilen fehlgeschlagen';

  @override
  String loadMoreRemaining(String count) {
    return 'Mehr laden ($count übrig)';
  }

  @override
  String get phoneDeleteNumberFailed => 'Diese Nummer konnte nicht gelöscht werden';

  @override
  String deviceUsesCodec(String device, String reason) {
    return '$device nimmt in einem Format auf, das dieser Anbieter nicht lesen kann ($reason), daher wird stattdessen die Transkription von Omi verwendet.';
  }

  @override
  String get chatAppsConnectIMessageMessage =>
      'Sende Omi eine Nachricht von der Nummer, die du nutzen möchtest. Der Code darin verknüpft diese Nummer mit deinem Konto.';

  @override
  String get speechToTextUnavailableDesc =>
      'Die Spracherkennung ist derzeit nicht verfügbar. Prüfe deine Internetverbindung und die Einstellungen zur Spracherkennung auf deinem Gerät und versuche es erneut.';

  @override
  String get chatReplyTimeout => 'Die Antwort hat zu lange gedauert. Bitte versuche es erneut.';

  @override
  String get passwordMinLengthError => 'Das Passwort muss mindestens 8 Zeichen lang sein';

  @override
  String get chatAppsWhatsAppMessage =>
      'Wir arbeiten daran, Omi auch auf WhatsApp zu bringen. Es erscheint hier, sobald es fertig ist.';

  @override
  String get deleteAccountCheckbox =>
      'Ich verstehe, dass das Löschen meines Kontos dauerhaft ist und alle Daten, einschließlich Erinnerungen und Unterhaltungen, verloren gehen und nicht wiederhergestellt werden können.';

  @override
  String get firmwareConnectWifi => 'Verbinden Sie sich mit WiFi oder Mobilfunk.';

  @override
  String get forgetDeviceConfirmMessage => 'Omi verbindet sich nicht mehr mit diesem Gerät.';

  @override
  String get editSwipeFeature => 'Tippen zum Bearbeiten, Wischen zum Erledigen oder Löschen';

  @override
  String get memoryManagement => 'Erinnerungsverwaltung';

  @override
  String get transcriptLoadFailed => 'Das Transkript konnte nicht geladen werden.';

  @override
  String get diagnosticsExportTitle => 'Omi-Gerätediagnose';

  @override
  String get updateOmiFirmware => 'Omi-Firmware aktualisieren';

  @override
  String get importTooManyAttempts => 'Gerade zu viele Importe. Versuche es später erneut.';

  @override
  String get noAppsFound => 'Keine Apps gefunden';

  @override
  String get phoneSetupStep1Subtitle => 'Wir rufen Sie an, um zu bestaetigen';

  @override
  String get deleteSyncedFiles => 'Synchronisierte Aufnahmen löschen';

  @override
  String speakerLabelVoiceStatus(String state) {
    String _temp0 = intl.Intl.selectLogic(
      state,
      {
        'learned': 'Stimme gelernt',
        'pending': 'Stimme wird gelernt…',
        'disabled': 'Stimmspeicherung ist aus',
        'other': 'Stimme noch nicht gelernt',
      },
    );
    return '$_temp0';
  }

  @override
  String get recordingsMayCaptureOthers =>
      'Aufnahmen können die Stimmen anderer erfassen. Stellen Sie sicher, dass Sie die Zustimmung aller Teilnehmer haben, bevor Sie aktivieren.';

  @override
  String get helpful => 'Hilfreich';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return 'Lade $model herunter: $received / $total MB';
  }

  @override
  String get permissions => 'Berechtigungen';

  @override
  String get audioDownloadSuccess => 'Audio erfolgreich heruntergeladen';

  @override
  String get confirmPlanChange => 'Planänderung bestätigen';

  @override
  String get wrappedThatAwkwardMoment => 'Dieser peinliche Moment';

  @override
  String get calendarProviders => 'Kalenderanbieter';

  @override
  String evidenceAutoUnconfirmed(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count automatische Markierungen noch nicht bestätigt',
      one: '1 automatische Markierung noch nicht bestätigt',
    );
    return '$_temp0';
  }

  @override
  String get importData => 'Daten importieren';

  @override
  String get weekdayMon => 'Mo';

  @override
  String get deviceStorageTitle => 'Gerätespeicher';

  @override
  String get externalAppAccess => 'Externer App-Zugriff';

  @override
  String get transcriptionUnavailable => 'Transkription nicht verfügbar';

  @override
  String get termsAndPrivacyPolicy => 'Nutzungsbedingungen & Datenschutz';

  @override
  String get noImportsYet => 'Noch keine Importe';

  @override
  String get openOmiOnAppleWatchDescription =>
      'Die Omi-App ist auf deiner Apple Watch installiert. Öffne sie und tippe auf Start.';

  @override
  String dreamReportFailed(String error) {
    return 'Fehlgeschlagen ($error)';
  }

  @override
  String get sendSummary => 'Zusammenfassung senden';

  @override
  String get filterAll => 'Alle';

  @override
  String get deleteChatMessage => 'Er verschwindet endgültig aus den früheren Chats.';

  @override
  String get timeout10Minutes => '10 Minuten';

  @override
  String get noCalendarEventsNearby => 'Um diese Zeit wurden keine Kalendertermine gefunden.';

  @override
  String get cancelSyncQuestion => 'Synchronisierung abbrechen?';

  @override
  String get whatShouldWeMake => 'Was sollen wir machen?';

  @override
  String get usageListened => 'Listened';

  @override
  String get errorUpdatingStripeDetails =>
      'Fehler beim Aktualisieren der Stripe-Details! Bitte versuchen Sie es später erneut.';

  @override
  String get conversationEndAfterHours => 'Unterhaltungen enden nun nach 4 Stunden Stille';

  @override
  String get issueActivatingApp =>
      'Bei der Aktivierung dieser App ist ein Problem aufgetreten. Bitte versuchen Sie es erneut.';

  @override
  String get appCreatedSuccessfully => 'App erfolgreich erstellt!';

  @override
  String get categoryNews => 'Nachrichten';

  @override
  String get phoneSearchHint => 'Suchen';

  @override
  String peoplePinnedCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count angeheftet',
      one: '1 angeheftet',
    );
    return '$_temp0';
  }

  @override
  String get wrappedHours => 'Stunden';

  @override
  String get phoneKeypad => 'Tastatur';

  @override
  String get peopleFilterLowConfidence => 'Geringe Sicherheit';

  @override
  String get agreeToContributeData => 'Ich verstehe und stimme zu, meine Daten für das KI-Training beizutragen';

  @override
  String get addGoal => 'Ziel hinzufügen';

  @override
  String get dreamReportRunInProgress => 'Ein Durchlauf läuft bereits. Versuche es in einer Minute erneut.';

  @override
  String importedConfig(String providerName) {
    return '$providerName-Konfiguration importiert';
  }

  @override
  String monthsAgo(int count) {
    return 'vor $count Monaten';
  }

  @override
  String get downgradeLimitationsHeading => 'Diese Einschränkungen erwarten Sie:';

  @override
  String get chatRemoveSelectedText => 'Zitierten Text entfernen';

  @override
  String get firmwareBatteryAbove15 => 'Batterie über 15%';

  @override
  String reviewQuestionSamePerson(String name) {
    return 'Dieselbe Person wie „$name“?';
  }

  @override
  String get effectCountsALot => 'Hilft viel';

  @override
  String get sdCard => 'SD Card';

  @override
  String get openInGoogleCalendar => 'In Google Kalender öffnen';

  @override
  String get appleHealthFeatureSecureTitle => 'Sichere Synchronisierung';

  @override
  String get conversationDeveloperToolsDescription =>
      '„Gesprächs-ID kopieren“ und „Prompt testen“ im Gesprächsmenü anzeigen';

  @override
  String get host => 'Host';

  @override
  String get deleteReasonMissingFeatures => 'Funktionen, die ich brauche, fehlen';

  @override
  String get syncingInProgress => 'Synchronisierung läuft';

  @override
  String get tabDone => 'Erledigt';

  @override
  String get revoke => 'Widerrufen';

  @override
  String get mcp => 'MCP';

  @override
  String get anyoneCanDiscoverTemplate => 'Jeder kann Ihre Vorlage entdecken';

  @override
  String get mcpDescription =>
      'Um Omi mit anderen Anwendungen zu verbinden, um Ihre Erinnerungen und Unterhaltungen zu lesen, zu durchsuchen und zu verwalten. Erstellen Sie einen Schlüssel, um loszulegen.';

  @override
  String get connectionLostDescription =>
      'Die Verbindung wurde unterbrochen. Bitte überprüfen Sie Ihre Internetverbindung und versuchen Sie es erneut.';

  @override
  String chatAppsNoChatsMessage(String app) {
    return 'Chats, die du mit Omi in $app führst, erscheinen hier.';
  }

  @override
  String get storedLocallyNeverShared =>
      'Auf diesem Telefon gespeichert. Wird nur an deinen Transkriptionsanbieter gesendet.';

  @override
  String get morePaymentMethodsComingSoon => 'Weitere Zahlungsmethoden in Kürze';

  @override
  String get allCaughtUp => 'Alles auf dem neuesten Stand';

  @override
  String previewImageLabel(int index, int total) {
    return 'Screenshot $index von $total';
  }

  @override
  String get disable => 'Deaktivieren';

  @override
  String get recordings => 'Aufnahmen';

  @override
  String get enterPersonsName => 'Namen der Person eingeben';

  @override
  String get newConversationCreated => 'Neue Unterhaltung erstellt';

  @override
  String resetsInDays(int count) {
    return 'Wird in $count Tagen zurückgesetzt';
  }

  @override
  String get confidenceConfirmed => 'Bestätigt';

  @override
  String get bulkExportInProgress => 'Exportieren…';

  @override
  String get detectLanguages => '10+ Sprachen erkennen';

  @override
  String get phoneSpeaker => 'Lautsprecher';

  @override
  String get visitWebsite => 'Website besuchen';

  @override
  String get howToTakeGoodSample => 'Wie macht man eine gute Probe?';

  @override
  String get clearChat => 'Chat löschen';

  @override
  String languageSetTo(String language) {
    return 'Sprache auf $language eingestellt';
  }

  @override
  String get deviceOnboardingVoiceReplyHeadphonesDescription =>
      'Privat. Spricht nur über AirPods, Bluetooth oder kabelgebundene Kopfhörer.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'Ihr Plan bleibt bis $date aktiv. Danach verlieren Sie den Zugang zu Ihren unbegrenzten Funktionen.';
  }

  @override
  String get clientSecret => 'Client Secret';

  @override
  String get pairingTitleAppleWatch => 'Apple Watch verbinden';

  @override
  String get share => 'Teilen';

  @override
  String get yourPrivacyYourControl => 'Ihre Privatsphäre, Ihre Kontrolle';

  @override
  String get tapToCopy => 'Zum Kopieren tippen';

  @override
  String get feedbackTitleFoundAlternative => 'Wohin wechselst du?';

  @override
  String get all => 'All';

  @override
  String get filterCapabilities => 'Funktionen';

  @override
  String get tagOtherSegments => 'Andere Segmente markieren';

  @override
  String get entityDecisions => 'Entscheidungen';

  @override
  String get tasksCreatedInWorkspace => 'Aufgaben werden in diesem Arbeitsbereich erstellt';

  @override
  String get fairUseDailyTranscription => 'Tägliche Transkription';

  @override
  String get pausePlayback => 'Pause';

  @override
  String get sharedTasksLinkExpired => 'Diese geteilten Aufgaben wurden nicht gefunden oder der Link ist abgelaufen.';

  @override
  String get editConversationDialogTitle => 'Gespräch bearbeiten';

  @override
  String get deleteMemoryConfirmation => 'Diese Erinnerung löschen? Dies kann nicht rückgängig gemacht werden.';

  @override
  String get appUnderReviewMessage =>
      'Ihre App wird überprüft und ist nur für Sie sichtbar. Sie wird nach Genehmigung öffentlich.';

  @override
  String get illDoItLater => 'Ich mache es später';

  @override
  String get captureStillRecording => 'Nimmt weiter auf';

  @override
  String confidenceNextLabels(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Markiere sie in $count weiteren Gesprächen.',
      one: 'Markiere sie in 1 weiteren Gespräch.',
    );
    return '$_temp0';
  }

  @override
  String get speakerTagPromptAnswerFailed => 'Speichern fehlgeschlagen. Bitte versuche es erneut.';

  @override
  String get feedbackReasonSummaryIncomplete => 'Unvollständig';

  @override
  String get errorActivatingApp => 'Fehler beim Aktivieren der App';

  @override
  String get tasksCompleted => 'Aufgaben erledigt';

  @override
  String onboardingStepOf(int current, int total) {
    return 'Schritt $current von $total';
  }

  @override
  String get downgradeAnyway => 'Trotzdem herabstufen';

  @override
  String get leaveBlank => 'Leer lassen';

  @override
  String get chatAppsViewChats => 'Chats ansehen';

  @override
  String get captureScreenRecordingPermissionRequired => 'Bildschirmaufnahme-Berechtigung erforderlich';

  @override
  String get accountCutoverUpdateRequiredTitle => 'Update erforderlich';

  @override
  String weeksAgo(int count) {
    return 'vor $count Wochen';
  }

  @override
  String get phoneEndCall => 'Beenden';

  @override
  String get startupFailedMessage =>
      'Beim Starten von Omi ist ein Fehler aufgetreten. Überprüfe deine Verbindung und versuche es dann erneut.';

  @override
  String get permissionRevokedTitle => 'Berechtigung widerrufen';

  @override
  String get chatFeatures => 'Chat-Funktionen';

  @override
  String get couldNotLoadMap => 'Karte konnte nicht geladen werden';

  @override
  String get selectContactsToShare => 'Kontakte zum Teilen auswählen';

  @override
  String get ok => 'OK';

  @override
  String get memoryReviewConfirmed => 'Bestätigt.';

  @override
  String get deleteKnowledgeGraph => 'Wissensgraph löschen';

  @override
  String get reviewChangeFailed => 'Diese Änderung konnte nicht aktualisiert werden. Versuche es erneut.';

  @override
  String get limitless => 'Limitless';

  @override
  String uploadingToCloud(int current, int total) {
    return 'Hochladen von $current von $total';
  }

  @override
  String get dontSeeYourDevice => 'Gerät nicht sichtbar?';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Ihre Aufgaben werden mit Ihrem $appName-Konto synchronisiert';
  }

  @override
  String appSettingsLabel(String appName) {
    return '$appName-Einstellungen';
  }

  @override
  String get chatBlockShowLess => 'Weniger anzeigen';

  @override
  String get mindMap => 'Mind Map';

  @override
  String get authorizationBearer => 'Authorization: Bearer <key>';

  @override
  String get dreamReportWouldSuggestTasks => 'Würde Aufgaben vorschlagen';

  @override
  String get dreamReportWouldAsk => 'Würde dich fragen';

  @override
  String get getFreeUnlimitedAccess => 'Kostenlosen unbegrenzten Zugang erhalten';

  @override
  String get yourDaysJourney => 'Ihre Tagesreise';

  @override
  String get transcriptReceived => 'Transkript empfangen';

  @override
  String get expand => 'Erweitern';

  @override
  String get onboardingCompleteMessage =>
      'Lass Omi ein paar Tage laufen. Deine Gespräche, Erinnerungen und To-dos füllen sich dann nach und nach.';

  @override
  String get trainFamilyProfiles => 'Profile für Freunde und Familie trainieren';

  @override
  String get selectText => 'Text auswählen';

  @override
  String get generatingDescription => 'Beschreibung wird generiert…';

  @override
  String get deviceOnboardingStarConversationDesc => 'Gespräch als wichtig markieren';

  @override
  String disableAppNamed(String appName) {
    return '$appName deaktivieren';
  }

  @override
  String get deleteConversationConfirmation => 'Dieses Gespräch löschen? Dies kann nicht rückgängig gemacht werden.';

  @override
  String get contentCopied => 'Inhalt in die Zwischenablage kopiert';

  @override
  String get joinTheCommunity => 'Treten Sie der Community bei!';

  @override
  String get noContactsWithPhoneNumbers => 'Keine Kontakte mit Telefonnummern gefunden';

  @override
  String get removeAttachment => 'Anhang entfernen';

  @override
  String get followTheVoiceInstructions => 'Folgen Sie den Sprachanweisungen';

  @override
  String get createYourOwnApp => 'Erstellen Sie Ihre eigene App';

  @override
  String get paymentDetails => 'Zahlungsdetails';

  @override
  String get tellOmiWhoSaidIt => 'Sagen Sie Omi, wer es gesagt hat 🗣️';

  @override
  String audioInputSetTo(String deviceName) {
    return 'Audioeingang auf $deviceName gesetzt';
  }

  @override
  String get pleaseEnterValidEmail => 'Bitte geben Sie eine gültige E-Mail-Adresse ein';

  @override
  String get thisYear => 'Dieses Jahr';

  @override
  String get noTranscriptMessage => 'Dieses Gespräch hat kein Transkript.';

  @override
  String get appearanceDark => 'Dunkel';

  @override
  String get createCustomTemplate => 'Benutzerdefinierte Vorlage erstellen';

  @override
  String get monthMay => 'Mai';

  @override
  String get tasksAddedToList => 'Aufgaben werden zu dieser Liste hinzugefügt';

  @override
  String isTriggeredBy(String triggerDescription) {
    return 'Wird $triggerDescription.';
  }

  @override
  String get deleteConversationTitle => 'Unterhaltung löschen?';

  @override
  String get accountCutoverUpdateRequiredMessage =>
      'Installiere die neueste Omi-App, um nach der Kontomigration fortzufahren.';

  @override
  String get txtFormat => 'TXT';

  @override
  String chatAppsDisconnectMessage(String app) {
    return 'Omi antwortet nicht mehr in $app und löscht den Chatverlauf, den es dafür speichert. Nachrichten, die bereits in $app sind, bleiben dort.';
  }

  @override
  String get captureWithCamera => 'Mit Kamera aufnehmen';

  @override
  String get appIdLabel => 'App-ID';

  @override
  String get endpointUrl => 'Endpunkt-URL';

  @override
  String get actionItemUpdated => 'Aufgabe aktualisiert';

  @override
  String itemsSelected(int count) {
    return '$count ausgewählt';
  }

  @override
  String get onboardingWhatIKnowAboutYouDescription =>
      'Diese Karte wird aktualisiert, wenn Omi aus Ihren Gesprächen lernt.';

  @override
  String diagnosticsLastDuration(String duration) {
    return 'Letzte $duration';
  }

  @override
  String get pairingDescLimitless =>
      'Wenn ein Licht sichtbar ist, drücken Sie einmal und halten Sie dann gedrückt, bis das Gerät ein rosa Licht zeigt, dann loslassen.';

  @override
  String get chatBlockOpenConversation => 'Gespräch öffnen';

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '$used von $limit Erkenntnissen diesen Monat gewonnen';
  }

  @override
  String get connectionErrorDesc =>
      'Verbindung zum Server fehlgeschlagen. Bitte überprüfen Sie Ihre Internetverbindung und versuchen Sie es erneut.';

  @override
  String get enterWordsCommaSeparated => 'Wörter eingeben (durch Komma getrennt)';

  @override
  String get otherDevicesComingSoon => 'Weitere Geräte demnächst';

  @override
  String speakerSuggestionChip(String name) {
    return '$name?';
  }

  @override
  String get speakerTagPromptNotAPersonToast => 'Als keine Person markiert';

  @override
  String get createKeyToGetStarted => 'Erstellen Sie einen Schlüssel, um zu beginnen';

  @override
  String get captureRecordingSeparateConfirm => 'Trennen';

  @override
  String get diagnosticsDrops => 'Abbrüche';

  @override
  String lowBatteryAlertBody(int level) {
    return 'Dein Akku ist bei $level%. Zeit zum Aufladen! 🔋';
  }

  @override
  String get deviceOnboardingTurnOffSubtitle => 'Halte die Taste 3 Sekunden lang gedrückt';

  @override
  String get done => 'Fertig';

  @override
  String get wifiConfigurationSubtitle =>
      'Geben Sie Ihre WLAN-Zugangsdaten ein, damit das Gerät die Firmware herunterladen kann.';

  @override
  String get permissionGrantedNow =>
      'Berechtigung erteilt! Jetzt:\n\nÖffnen Sie die Omi-App auf Ihrer Uhr und tippen Sie unten auf \'Weiter\'';

  @override
  String get setUpPayPal => 'PayPal einrichten';

  @override
  String get statusProcessed => 'Verarbeitet';

  @override
  String phoneFreeCallsRemaining(int remaining, int limit) {
    return '$remaining von $limit kostenlosen Anrufen in diesem Monat übrig';
  }

  @override
  String get event => 'Veranstaltung';

  @override
  String get conversationEvents => 'Unterhaltungsereignisse';

  @override
  String get uninstall => 'Deinstallieren';

  @override
  String get appCreators => 'App-Entwickler';

  @override
  String get muted => 'Stumm';

  @override
  String get deleteRecapAction => 'Löschen';

  @override
  String get addAppErrorSelectingThumbnailRetry => 'Fehler bei der Miniaturbildauswahl. Bitte versuchen Sie es erneut.';

  @override
  String get basicPlanDescription => '300 Premium-Minuten + unbegrenzt on-device';

  @override
  String get countrySelectionPermanent => 'Ihre Länderauswahl ist dauerhaft und kann später nicht geändert werden.';

  @override
  String get transcriptionConnecting => 'Transkription wird verbunden…';

  @override
  String transcriptionsPendingFraction(int pending, int total) {
    return 'Offene Transkriptionen $pending/$total';
  }

  @override
  String get apiKeyAuth => 'API-Schlüssel-Authentifizierung';

  @override
  String downloadModelWithName(String model) {
    return 'Modell herunterladen ($model)';
  }

  @override
  String get devModeInvalidDaySummaryWebhookUrl => 'Ungültige Webhook-URL für Tageszusammenfassung';

  @override
  String get memoryReviewSaveFailed => 'Speichern fehlgeschlagen, bitte erneut versuchen';

  @override
  String get payYourSttProvider => 'Kostenlos in Omi. Du zahlst deinen Transkriptionsanbieter direkt.';

  @override
  String get dailySummaryHeader => 'TÄGLICHE ZUSAMMENFASSUNG';

  @override
  String get fairUseStageWarning => 'Warnung';

  @override
  String get multipleSpeakersDesc =>
      'Es scheint, dass mehrere Sprecher in der Aufnahme sind. Bitte stellen Sie sicher, dass Sie sich an einem ruhigen Ort befinden, und versuchen Sie es erneut.';

  @override
  String get pastChats => 'Frühere Chats';

  @override
  String get listeningMins => 'Zuhören (Min)';

  @override
  String get pairingDescOmi => 'Halten Sie das Gerät gedrückt, bis es vibriert, um es einzuschalten.';

  @override
  String get deviceOnboardingIntroSubtitle =>
      'Probiere Live-Transkription, Fragen stellen und die Doppeltipp-Verknüpfung aus.';

  @override
  String get autoRemoveSyncedCopiesTitle => 'Synchronisierte Kopien automatisch entfernen';

  @override
  String chatAppsReadOnlyFooter(String app) {
    return 'Diese Chats sind hier schreibgeschützt. Antworte in $app.';
  }

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'Mikrofon geändert. Fortsetzung in ${countdown}s';
  }

  @override
  String get takePhoto => 'Foto aufnehmen';

  @override
  String get cancelSync => 'Synchronisierung abbrechen';

  @override
  String appSettings(String appName) {
    return '$appName-Einstellungen';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'Mikrofonberechtigung konnte nicht überprüft werden: $error';
  }

  @override
  String get micGain => 'Mikrofonverstärkung';

  @override
  String get collectingData => 'Daten werden gesammelt…';

  @override
  String get memoryReadOnlyHint => 'Diese Erinnerung wird als Verlauf aufbewahrt und kann nicht bearbeitet werden.';

  @override
  String get appUnderReviewOwner =>
      'Ihre App wird überprüft und ist nur für Sie sichtbar. Sie wird öffentlich, sobald sie genehmigt wurde.';

  @override
  String get addNewPerson => 'Neue Person hinzufügen';

  @override
  String get nameSpeakerTitle => 'Sprecher benennen';

  @override
  String get downloadingAudioFromSdCard => 'Audio von der SD-Karte deines Geräts wird heruntergeladen';

  @override
  String get pendantSyncingRecordings => 'Aufnahmen vom Pendant werden synchronisiert…';

  @override
  String get otaNotSupported => 'Diese Firmware kann nicht über WLAN aktualisiert werden.';

  @override
  String get wrappedSomethingWentWrong => 'Etwas ist\nschiefgelaufen';

  @override
  String get screenRecording => 'Bildschirmaufzeichnung';

  @override
  String get audioProcessedLocally =>
      'Audio wird lokal verarbeitet. Funktioniert offline, privater, verbraucht aber mehr Batterie.';

  @override
  String get onboardingSignIn => 'Anmelden';

  @override
  String timeDaysPlural(int count) {
    return '$count Tage';
  }

  @override
  String get memoryReviewTitle => 'Was ich heute gelernt habe';

  @override
  String get hidePassword => 'Passwort ausblenden';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get disconnected => 'Getrennt';

  @override
  String get revokeApiKeyQuestion => 'API-Schlüssel widerrufen?';

  @override
  String get detectBrowserBasedMeetings => 'Browserbasierte Besprechungen erkennen';

  @override
  String get failedToDeleteConversations => 'Gespräche konnten nicht gelöscht werden';

  @override
  String get raybanMetaCapturePhoto => 'Foto aufnehmen';

  @override
  String get bleSpeed => '~30 KB/s über BLE';

  @override
  String get conversationPromptPlaceholder =>
      'Sie sind eine großartige App, Sie erhalten ein Transkript und eine Zusammenfassung eines Gesprächs…';

  @override
  String get secureAuthViaGoogleAccount => 'Sichere Authentifizierung über Google-Konto';

  @override
  String get omiHas => 'Omi hat:';

  @override
  String get raybanMetaContinue => 'Fortfahren';

  @override
  String get pauseRecording => 'Aufnahme pausieren';

  @override
  String get evidenceNothing => 'Du hast sie noch nicht zugeordnet oder bestätigt';

  @override
  String get noActivityYet => 'Noch keine Aktivität';

  @override
  String get enterPasswordError => 'Bitte geben Sie Ihr Passwort ein';

  @override
  String get forgetDeviceConfirmTitle => 'Gerät vergessen?';

  @override
  String get ratingsAndReviews => 'Bewertungen & Rezensionen';

  @override
  String get addApiKeyAfterImport => 'Sie müssen Ihren eigenen API-Schlüssel nach dem Importieren hinzufügen';

  @override
  String get alreadyOnStableFirmware => 'Sie verwenden bereits die neueste stabile Version.';

  @override
  String get deleteAccountConfirm => 'Sind Sie sicher, dass Sie Ihr Konto löschen möchten?';

  @override
  String get recordingInfo => 'Aufnahmeinfo';

  @override
  String get feedbackReasonSummaryInaccurate => 'Nicht korrekt';

  @override
  String get pendantRecordingTitle => 'Aufnahme auf dem Pendant';

  @override
  String get deleteWhileProcessingMessage =>
      'Diese Aufnahme wurde hochgeladen, aber Omi erstellt die Konversation noch. Wenn du sie jetzt löschst und die Verarbeitung fehlschlägt, kann sie nicht wiederhergestellt werden. Trotzdem löschen?';

  @override
  String get createNewKey => 'Neuen Schlüssel erstellen';

  @override
  String get firmwareDownloadFailedMessage =>
      'Das Update konnte nicht geladen werden, dein Gerät wurde nicht verändert. Prüfe deine Internetverbindung und versuche es erneut.';

  @override
  String get loadingTasks => 'Aufgaben werden geladen…';

  @override
  String get previousResult => 'Vorheriges Ergebnis';

  @override
  String get reviewLoadFailed => 'Deine Fragen konnten nicht geladen werden.';

  @override
  String get onDevice => 'Auf dem Gerät';

  @override
  String get bluetoothSyncEnabled => 'Bluetooth-Synchronisierung aktiviert';

  @override
  String get categorySafety => 'Sicherheit';

  @override
  String get unknownLocation => 'Unbekannter Standort';

  @override
  String get newMemoryTitle => 'Neue Erinnerung';

  @override
  String get conversationCannotBeMerged =>
      'Diese Unterhaltung kann nicht zusammengeführt werden (gesperrt oder wird bereits zusammengeführt)';

  @override
  String get summaryGenerated => 'Zusammenfassung generiert';

  @override
  String get createKey => 'Schlüssel Erstellen';

  @override
  String get letOmiChooseAutomatically => 'Lassen Sie Omi automatisch die beste App auswählen';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'Bitte starten Sie Ihr $deviceName neu, um das Update abzuschließen.';
  }

  @override
  String get goals => 'Ziele';

  @override
  String get wrappedAnErrorOccurred => 'Ein Fehler ist aufgetreten';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'Mikrofonberechtigung konnte nicht überprüft werden: $error';
  }

  @override
  String get connectLater => 'Später verbinden';

  @override
  String get wrappedRememberedByOmi => 'festgehalten von Omi';

  @override
  String get fairUseStatusNormal => 'Ihre Nutzung liegt im normalen Bereich.';

  @override
  String get includePersonalEventsDescription => 'Persönliche Ereignisse ohne Teilnehmer einbeziehen';

  @override
  String get week => 'Woche';

  @override
  String get willLikelyCrash => 'Das Aktivieren wird wahrscheinlich zum Absturz oder Einfrieren der App führen.';

  @override
  String get selectPrimaryLanguage => 'Wählen Sie Ihre primäre Sprache';

  @override
  String get pilotFeaturesDescription => 'Diese Funktionen sind Tests und es wird keine Unterstützung garantiert.';

  @override
  String get askOmi => 'Omi fragen';

  @override
  String get ifYouCancel => 'Wenn du kündigst:';

  @override
  String get audioOutput => 'Audioausgabe';

  @override
  String get memoryReviewWrong => 'Falsch';

  @override
  String get couldNotSchedulePlanChange => 'Die Planänderung konnte nicht geplant werden. Bitte versuche es erneut.';

  @override
  String speakerLabelEarlierMatches(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'In $count früheren Gesprächen gefunden',
      one: 'In 1 früheren Gespräch gefunden',
    );
    return '$_temp0';
  }

  @override
  String get deviceOnboardingListening => 'Hört zu…';

  @override
  String get speechProfileEnrollmentPrompt =>
      'Damit Omi weiß, welche Stimme deine ist — sprich etwa 5 Sekunden über irgendetwas.';

  @override
  String get mcpServerUrl => 'MCP Server URL';

  @override
  String get chatBlockMemory => 'Erinnerung';

  @override
  String get noStarredConversations => 'Keine markierten Gespräche';

  @override
  String get syncStatusTooOld => 'Zu alt für die Synchronisierung — Omi kann sie nicht annehmen';

  @override
  String connectedAsUser(String userId) {
    return 'Verbunden als Benutzer: $userId';
  }

  @override
  String get phonePageTitle => 'Telefon';

  @override
  String get buildGraphButton => 'Graph erstellen';

  @override
  String get issuesCreatedInRepo => 'Issues werden in Ihrem Standard-Repository erstellt';

  @override
  String get scopeUserFacts => 'Benutzerfakten';

  @override
  String get unableToLoadPlans => 'Pläne konnten nicht geladen werden';

  @override
  String get deleteRecording => 'Aufnahme löschen';

  @override
  String get appDeleteFailed => 'App konnte nicht gelöscht werden. Bitte versuche es später erneut.';

  @override
  String get addAppUpdatedSuccess => 'App erfolgreich aktualisiert 🚀';

  @override
  String get reviewCaughtUpTitle => 'Nichts zu beantworten';

  @override
  String get copyConversationId => 'Konversations-ID kopieren';

  @override
  String get helpImproveOmiBySharing => 'Helfen Sie, Omi zu verbessern, indem Sie anonymisierte Analysedaten teilen';

  @override
  String get dataEncryptedBanner =>
      'Deine Daten sind standardmäßig durch starke Verschlüsselung geschützt, und du behältst die Kontrolle darüber, wie sie gespeichert und verwendet werden.';

  @override
  String get redo => 'Neu aufnehmen';

  @override
  String get updateOmiGlassFirmware => 'OmiGlass-Firmware aktualisieren';

  @override
  String get deviceUnpairedMessage =>
      'Gerät entkoppelt. Gehen Sie zu Einstellungen > Bluetooth und vergessen Sie das Gerät, um die Entkopplung abzuschließen.';

  @override
  String speakerLabelText(String part, String name) {
    String _temp0 = intl.Intl.selectLogic(
      part,
      {
        'likely': 'Wahrscheinlich',
        'soundsLike': 'Klingt wie $name',
        'notPerson': 'Nicht $name',
        'carried': 'Weiterhin $name. Aus deinem letzten Gespräch übernommen.',
        'change': 'Ändern',
        'alsoTitle': 'Ist das auch $name?',
        'alsoBody': 'Omi hat dieselbe Stimme in früheren Gesprächen gefunden.',
        'confirmed': 'Du hast dieses Label bestätigt',
        'other': 'Prüfen',
      },
    );
    return '$_temp0';
  }

  @override
  String get continueWithApple => 'Mit Apple fortfahren';

  @override
  String get iUnderstand => 'Ich verstehe';

  @override
  String get memoryProvenanceAndroid => 'Android';

  @override
  String get saving => 'Wird gespeichert…';

  @override
  String get deviceOnboardingDoubleTapTitle => 'Doppeltippen anpassen';

  @override
  String get allMemoriesPublicResult => 'Alle Erinnerungen sind jetzt öffentlich';

  @override
  String get chatAppsAddToContacts => 'Omi zu Kontakten hinzufügen';

  @override
  String get wrappedDays => 'Tage';

  @override
  String get invalidJsonError => 'Ungültiges JSON';

  @override
  String syncCardNeedsAttention(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count Aufnahmen benötigen Aufmerksamkeit',
      one: '1 Aufnahme benötigt Aufmerksamkeit',
    );
    return '$_temp0';
  }

  @override
  String get wrappedSwipeUpToBegin => 'Nach oben wischen zum Starten';

  @override
  String addedToService(String serviceName) {
    return 'Zu $serviceName hinzugefügt';
  }

  @override
  String get advanced => 'Erweitert';

  @override
  String get autoCreateAndTagNewSpeakers => 'Neue Sprecher automatisch erstellen und kennzeichnen';

  @override
  String get appCapabilities => 'App-Funktionen';

  @override
  String get onboardingMicrophoneDenied =>
      'Mikrofonberechtigung verweigert. Bitte erteilen Sie die Berechtigung in Systemeinstellungen > Datenschutz & Sicherheit > Mikrofon.';

  @override
  String get pleaseEnterFolderName => 'Bitte geben Sie einen Ordnernamen ein';

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'Bluetooth-Berechtigung konnte nicht überprüft werden: $error';
  }

  @override
  String get invalidRecordingDetected => 'Ungültige Aufnahme erkannt';

  @override
  String get appAnalytics => 'App-Analytik';

  @override
  String get captureRecordingsSheetTitle => 'Aufnahmen dieses Gesprächs';

  @override
  String deletedLimitlessConversations(int count) {
    return '$count Limitless-Gespräche gelöscht';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'Fehler bei der Bildauswahl: $error';
  }

  @override
  String get unnamedSpeakerLabel => 'Sprecher';

  @override
  String get failedToCreateApp => 'App konnte nicht erstellt werden. Bitte versuchen Sie es erneut.';

  @override
  String get planUpdate => 'Plan-Aktualisierung';

  @override
  String get timeout5Minutes => '5 Minuten';

  @override
  String get deleteSample => 'Probe löschen';

  @override
  String get willNotSeeAgain => 'Sie werden ihn nicht wieder sehen können.';

  @override
  String get thisMonth => 'Diesen Monat';

  @override
  String get enterName => 'Name eingeben';

  @override
  String get memoryThisDevice => 'Dieses Gerät';

  @override
  String get verifiedNumbersDescription => 'Wenn Sie jemanden anrufen, sieht er diese Nummer';

  @override
  String get deviceOnboardingSingleTapHint => 'Das war ein einzelnes Tippen – versuche, zweimal schnell zu tippen!';

  @override
  String autoClosingInSeconds(int seconds) {
    return 'Schließt automatisch in ${seconds}s';
  }

  @override
  String get chatAppsProPerkContext => 'Omi merkt sich den Kontext in jeder App';

  @override
  String get errorProcessingConversation =>
      'Fehler beim Verarbeiten der Unterhaltung. Bitte versuchen Sie es später erneut.';

  @override
  String get profileSettings => 'Profileinstellungen';

  @override
  String get statusUnprocessed => 'Unverarbeitet';

  @override
  String get deleteConversationMessage =>
      'Dadurch werden auch zugehörige Erinnerungen, Aufgaben und Audiodateien gelöscht.';

  @override
  String get cancelSubscriptionQuestion => 'Abonnement kündigen?';

  @override
  String get forUnlimitedFreeTranscription => 'für unbegrenzte kostenlose Transkription.';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used von $limit Minuten verbraucht';
  }

  @override
  String get categoryPersonalWellness => 'Persönliches Wohlbefinden';

  @override
  String get automaticTranslation => 'Automatische Übersetzung';

  @override
  String get defaultAiAssistant => 'Standard-KI-Assistent';

  @override
  String get allDataErased => 'Deine Erinnerungen und Gespräche werden gelöscht.';

  @override
  String entityDue(String date) {
    return 'Fällig $date';
  }

  @override
  String get feedbackChatWithUs => 'Mehr Details? Schreib uns';

  @override
  String get speakerTagPromptSomeoneNew => 'Jemand Neues';

  @override
  String get inProgress => 'In Bearbeitung';

  @override
  String get raybanMetaCheckAgain => 'Erneut prüfen';

  @override
  String get fairUseStageNormal => 'Normal';

  @override
  String get pairingTitleLimitless => 'Limitless in den Kopplungsmodus versetzen';

  @override
  String get usingNativeIosSpeech => 'Verwende native iOS-Spracherkennung';

  @override
  String get actionItemDeletedSuccessfully => 'Aufgabe erfolgreich gelöscht';

  @override
  String get failedToSetLanguage => 'Sprache konnte nicht eingestellt werden';

  @override
  String get appHomeUrl => 'App-Startseiten-URL';

  @override
  String get appNameLabel => 'App-Name';

  @override
  String get localStorageDisabled => 'Lokaler Speicher deaktiviert';

  @override
  String get appReEnable => 'Reaktivieren';

  @override
  String get migrationFailed => 'Migration fehlgeschlagen';

  @override
  String get markComplete => 'Als abgeschlossen markieren';

  @override
  String get lastUsedLabel => 'Zuletzt verwendet';

  @override
  String get chatCleared => 'Chat gelöscht';

  @override
  String get revokeApiKeyWarning =>
      'Apps, die diesen Schlüssel verwenden, verlieren den API-Zugriff. Dies kann nicht rückgängig gemacht werden.';

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return 'Bildschirmaufnahme-Berechtigung konnte nicht überprüft werden: $error';
  }

  @override
  String get troubleshootingSteps =>
      'Fehlerbehebung:\n\n1. Stellen Sie sicher, dass Omi auf Ihrer Uhr installiert ist\n2. Öffnen Sie die Omi-App auf Ihrer Uhr\n3. Suchen Sie nach dem Berechtigungs-Popup\n4. Tippen Sie bei Aufforderung auf \'Zulassen\'\n5. App auf Ihrer Uhr wird geschlossen - öffnen Sie sie erneut\n6. Kommen Sie zurück und tippen Sie auf Ihrem iPhone auf \'Weiter\'';

  @override
  String get location => 'Standort';

  @override
  String get chatAppsWhatsAppMeantime =>
      'Telegram und iMessage funktionieren schon heute, mit denselben Erinnerungen und Aufgaben.';

  @override
  String get sliderOff => 'Aus';

  @override
  String get checkingFirmwareVersion => 'Firmware-Version wird überprüft…';

  @override
  String get reviewUnknownSpeaker => 'Unbekannter Sprecher';

  @override
  String get professionSales => 'Vertrieb';

  @override
  String get noRssiDataYet => 'Noch keine RSSI-Daten';

  @override
  String get emptyOldMessage => '✅ Keine alten Aufgaben';

  @override
  String deleteSampleConfirmation(String name) {
    return 'Die Stimmprobe von $name wird entfernt. Dies kann nicht rückgängig gemacht werden.';
  }

  @override
  String get saveUrlButton => 'URL speichern';

  @override
  String get onboardingNotificationDeniedSystemPrefs =>
      'Benachrichtigungsberechtigung verweigert. Bitte erteilen Sie die Berechtigung in den Systemeinstellungen.';

  @override
  String get languageForTranscription =>
      'Omi verwendet diese Sprache für Transkriptionen, Zusammenfassungen und Erinnerungen.';

  @override
  String get updatedLabel => 'AKTUALISIERT';

  @override
  String get content => 'Inhalt';

  @override
  String get phoneCallButton => 'Anrufen';

  @override
  String get exportStartedMayTakeFewSeconds => 'Export gestartet. Dies kann einige Sekunden dauern…';

  @override
  String dreamReportPrivacyHeld(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count Meldungen aus Datenschutzgründen zurückgehalten',
      one: '1 Meldung aus Datenschutzgründen zurückgehalten',
    );
    return '$_temp0';
  }

  @override
  String firmwareBatteryTooLow(int level) {
    return 'Der Akku steht bei $level %. Lade dein Gerät vor dem Update auf mindestens 15 %.';
  }

  @override
  String get appearance => 'Darstellung';

  @override
  String noTasksOnDate(Object date) {
    return 'Keine Aufgaben am $date';
  }

  @override
  String get deleteFlowFeedbackHint => 'Optional — deine Gedanken helfen uns, ein besseres Produkt zu bauen.';

  @override
  String get bluetooth => 'Bluetooth';

  @override
  String get cancelUpdate => 'Update abbrechen';

  @override
  String get syncStatusConversationCreated => 'Gespräch erstellt';

  @override
  String get reconnecting => 'Verbinde neu…';

  @override
  String get tasksToday => 'Heute';

  @override
  String taskCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count Aufgaben',
      one: '1 Aufgabe',
    );
    return '$_temp0';
  }

  @override
  String get noUpcomingMeetings => 'Keine bevorstehenden Termine';

  @override
  String get invalidRecordingMultipleSpeakers => 'Ungültige Aufnahme erkannt';

  @override
  String get startupFailedTitle => 'Omi konnte nicht starten';

  @override
  String contactsSelectedCount(int count) {
    return '$count ausgewählt';
  }

  @override
  String get skipForward10Seconds => '10 Sekunden vor';

  @override
  String get noItems => 'Keine Elemente';

  @override
  String get timeout30Minutes => '30 Minuten';

  @override
  String get signInSuccess => 'Anmeldung erfolgreich!';

  @override
  String get syncStatusDownloadingFromDevice => 'Wird von deinem Gerät heruntergeladen';

  @override
  String get makePrivate => 'Privat machen';

  @override
  String get update => 'Aktualisieren';

  @override
  String get aiGenCreatingAppIcon => 'App-Symbol wird erstellt…';

  @override
  String get wrappedIntenseDay => 'Intensiv';

  @override
  String get raybanMetaSkipForNow => 'Vorerst überspringen';

  @override
  String diagnosticsReconnectedIn(String duration) {
    return 'nach $duration wieder verbunden';
  }

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'Dein $title-Plan wird nach deinem aktuellen Abrechnungszeitraum aktiviert';
  }

  @override
  String get appsAskWith => 'Omi fragen mit';

  @override
  String get noMemoriesFound => 'Keine Erinnerungen gefunden';

  @override
  String get noMemoriesYet => 'Noch keine Erinnerungen';

  @override
  String get captureRecordingSeparateFailed => 'Trennen fehlgeschlagen. Versuche es erneut.';

  @override
  String get pinAsBaseline => 'Als Basis anheften';

  @override
  String get voiceRecognitionSettings => 'Stimmerkennung';

  @override
  String get chatAppsComingLater => 'Kommt später';

  @override
  String get sliderMax => 'Max.';

  @override
  String get deleteWhileProcessingTitle => 'Wird noch verarbeitet';

  @override
  String get devModeSettingsSaved => 'Einstellungen gespeichert!';

  @override
  String get fairUseToday => 'Heute';

  @override
  String get exportDataDesc => 'Unterhaltungen in eine JSON-Datei exportieren';

  @override
  String get whatsYourName => 'Wie heißen Sie?';

  @override
  String get onDeviceSlower => 'On-Device-Transkription kann langsamer sein.';

  @override
  String get categoryProductivityLifestyle => 'Produktivität & Lebensstil';

  @override
  String get addToYourTaskList => 'Zur Aufgabenliste hinzufügen?';

  @override
  String get meetingScreenshotFallbackCaption => 'Bildschirmfoto aus diesem Meeting';

  @override
  String get effectCountsALittle => 'Hilft etwas';

  @override
  String get pairingTitleFriendPendant => 'Friend Pendant in den Kopplungsmodus versetzen';

  @override
  String get peopleStatsIncomplete => 'Die Angaben können unvollständig sein.';

  @override
  String get tapToAddGoal => 'Tippen, um ein Ziel hinzuzufügen';

  @override
  String get payment => 'Zahlung';

  @override
  String get omiDebugLog => 'Omi Debug-Protokoll';

  @override
  String get showMeetingsMenuBar => 'Anstehende Meetings in der Menüleiste anzeigen';

  @override
  String get mostInstalls => 'Meiste Installationen';

  @override
  String chatUsageMessages(String used, String limit) {
    return 'Chat: $used / $limit Nachrichten diesen Monat';
  }

  @override
  String get chat => 'Chat';

  @override
  String get areYouThere => 'Sind Sie da?';

  @override
  String get highestRating => 'Höchste Bewertung';

  @override
  String get pleaseSpecify => 'Bitte angeben';

  @override
  String get staging => 'Testumgebung';

  @override
  String get cancelReasonBatteryDrain => 'Bedenken wegen Batterieverbrauch';

  @override
  String get apiKeys => 'API-Schlüssel';

  @override
  String conversationsCreated(int count) {
    return '$count Gespräche erstellt';
  }

  @override
  String get trainingDataProgram => 'Trainingsdatenprogramm';

  @override
  String get customBackendUrlTitle => 'Benutzerdefinierte Backend-URL';

  @override
  String get omiSyncsAudioFiles => 'Omi synchronisiert dann die Audiodateien mit dem Server';

  @override
  String get reviewAnswerMe => 'Ich';

  @override
  String get debugDiagnostics => 'Debug & Diagnose';

  @override
  String get confidenceReasonNotHeard => 'noch nicht gehört';

  @override
  String get doubleTapAction => 'Doppeltippen-Aktion';

  @override
  String get showTasksOnHomepage => 'Aufgaben auf der Startseite anzeigen';

  @override
  String failedToStartUpdate(String error) {
    return 'Update konnte nicht gestartet werden: $error';
  }

  @override
  String get feedbackReasonSummaryWrongContext => 'Falscher Kontext';

  @override
  String get pleaseProvideValidDescription => 'Bitte geben Sie eine gültige Beschreibung an';

  @override
  String get appRejectedNotice =>
      'Ihre App wurde abgelehnt. Bitte aktualisieren Sie die App-Details und reichen Sie sie erneut zur Überprüfung ein.';

  @override
  String get deleteOnDeviceModel => 'Modell löschen';

  @override
  String get languageSettingsHelperText =>
      'Die App-Sprache ändert Menüs und Schaltflächen. Die Hauptsprache beeinflusst, wie Ihre Aufnahmen transkribiert werden.';

  @override
  String get deleteConversationsMessage => 'Dadurch werden auch ihre Erinnerungen, Aufgaben und Audiodateien gelöscht.';

  @override
  String get usageBestMonth => 'Best month';

  @override
  String get creating => 'Erstellen…';

  @override
  String get microphoneAccessDescription =>
      'Omi benötigt Mikrofonzugriff, um Ihre Gespräche aufzuzeichnen und Transkriptionen bereitzustellen.';

  @override
  String get cancelReasonNotUsing => 'Nutze es nicht genug';

  @override
  String get wrappedWeveAllBeenThere => 'Das kennen wir alle!';

  @override
  String get chatAppsProblemRateLimited => 'Zu viele Versuche. Warte eine Minute und versuche es erneut.';

  @override
  String get selectOption => 'Auswählen';

  @override
  String get languageBenefits => 'Omi verwendet diese Sprache für Transkriptionen, Zusammenfassungen und Erinnerungen.';

  @override
  String get triggerConversationIntegration => 'Unterhaltungs-Integration auslösen';

  @override
  String get integrationSetupRequired =>
      'Wenn dies eine Integrations-App ist, stellen Sie sicher, dass die Einrichtung abgeschlossen ist.';

  @override
  String get clickPlayToResumeOrStop => 'Klicken Sie auf Abspielen zum Fortsetzen oder Stopp zum Beenden';

  @override
  String disconnectedFrom(String appName) {
    return 'Von $appName getrennt';
  }

  @override
  String get subscribe => 'Abonnieren';

  @override
  String get permissionsChangeAnytime => 'Du kannst diese jederzeit unter Einstellungen > Berechtigungen ändern';

  @override
  String get enableRemindersAccess =>
      'Bitte aktivieren Sie den Zugriff auf Erinnerungen in den Einstellungen, um Apple Erinnerungen zu verwenden';

  @override
  String get selectProviderTemplate => 'Anbietervorlage auswählen…';

  @override
  String get initialisingSystemAudio => 'Initialisiere Systemaudio';

  @override
  String get excellent => 'Ausgezeichnet';

  @override
  String get chatBlockGoal => 'Ziel';

  @override
  String get deleteFolder => 'Ordner löschen';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'Schlüssel konnte nicht erstellt werden: $error';
  }

  @override
  String get whisperModelSizeSmall => 'Klein';

  @override
  String get pleaseCopyKeyNow => 'Bitte kopieren Sie ihn jetzt und notieren Sie ihn an einem sicheren Ort. ';

  @override
  String get unresolvedSpeakersNotice =>
      'Sprecherlabels stimmen in den Aufnahmen dieses Gesprächs möglicherweise nicht überein.';

  @override
  String get omisMemoryCleared => 'Omis Erinnerung an Sie wurde gelöscht';

  @override
  String get manageApp => 'App verwalten';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return 'Bildschirmaufnahme-Berechtigungsstatus: $status. Bitte überprüfen Sie die Systemeinstellungen.';
  }

  @override
  String get edit => 'Bearbeiten';

  @override
  String get redownload => 'Erneut herunterladen';

  @override
  String get chatBlockConversation => 'Gespräch';

  @override
  String get loadingApps => 'Apps werden geladen…';

  @override
  String get chatPromptPlaceholder =>
      'Sie sind eine großartige App, Ihre Aufgabe ist es, auf Benutzeranfragen zu antworten und ihnen ein gutes Gefühl zu geben…';

  @override
  String get stripeConnectedAccountAgreement => 'Stripe Connected Account-Vereinbarung';

  @override
  String get autoSync => 'Automatische Synchronisierung';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'Wissensgraph erfolgreich gelöscht';

  @override
  String get optInAndOptOutOptions => 'Opt-In und Opt-Out Optionen';

  @override
  String get permissionReadMemories => 'Erinnerungen lesen';

  @override
  String get noSpacesInWorkspace => 'Keine Spaces in diesem Arbeitsbereich gefunden';

  @override
  String get reviewYesMerge => 'Ja, zusammenführen';

  @override
  String get voiceMode => 'Sprachmodus';

  @override
  String get fairUseStageThrottle => 'Gedrosselt';

  @override
  String get deleteChatQuestion => 'Diesen Chat löschen?';

  @override
  String get failedToGetCallToken => 'Token konnte nicht abgerufen werden. Verifizieren Sie zuerst Ihre Nummer.';

  @override
  String get selectTime => 'Zeit auswählen';

  @override
  String get sdCardProcessing => 'SD-Karten-Verarbeitung';

  @override
  String errorConnectingRayBanMeta(String error) {
    return 'Fehler beim Verbinden mit Ray-Ban Meta: $error';
  }

  @override
  String get couldNotLoadImportHistory => 'Importverlauf konnte nicht geladen werden';

  @override
  String get noApiKeysFound => 'Keine API-Schlüssel gefunden. Erstellen Sie einen, um loszulegen.';

  @override
  String get appDisabledTitle => 'Diese App ist deaktiviert und kann nicht installiert werden.';

  @override
  String get syncStatusBackedUp => 'Gesichert';

  @override
  String get speakerTagPromptThatsMeAction => 'Das bin ich';

  @override
  String timeCompactHoursAndMins(int hours, int mins) {
    return '${hours}h ${mins}m';
  }

  @override
  String get chatPrompt => 'Chat-Eingabeaufforderung';

  @override
  String get voicePreviewSample => 'Hallo, ich bin Omi. Das ist meine Stimme.';

  @override
  String get saved => 'Gespeichert';

  @override
  String get grantPermissionButton => 'Berechtigung erteilen';

  @override
  String get subscription => 'Abonnement';

  @override
  String get capabilityFeatured => 'Empfohlen';

  @override
  String get pdfConversationExport => 'Gesprächs-Export';

  @override
  String get unknown => 'Unbekannt';

  @override
  String get yourMeetings => 'Ihre Meetings';

  @override
  String get uploadingVoiceProfile => 'Ihr Stimmprofil wird hochgeladen….';

  @override
  String get apiUrl => 'API-URL';

  @override
  String get reportMessage => 'Nachricht melden';

  @override
  String get passwordLabel => 'Passwort';

  @override
  String get permanentlyRemoveAllMemories => 'Alle Erinnerungen dauerhaft aus Omi entfernen';

  @override
  String get transcriptionSlowerLessAccurate => 'Die Transkription wird deutlich langsamer und weniger genau sein.';

  @override
  String get filterManual => 'Manuell';

  @override
  String get keepMyPlan => 'Meinen Plan behalten';

  @override
  String get setupQuestionAge => '3. In welcher Altersgruppe bist du?';

  @override
  String get addAppSelectTriggerEvent => 'Bitte wählen Sie ein Auslöseereignis für Ihre App aus';

  @override
  String get defaultWorkspace => 'Standard-Arbeitsbereich';

  @override
  String get errorUpdatingAppStatus => 'Beim Aktualisieren des App-Status ist ein Fehler aufgetreten.';

  @override
  String get invalidJsonConfig => 'Ungültige JSON-Konfiguration';

  @override
  String get detailedDiagnosticMessages => 'Detaillierte Diagnosemeldungen';

  @override
  String get mergingInBackground => 'Zusammenführung im Hintergrund. Dies kann einen Moment dauern.';

  @override
  String get setDefaultApp => 'Standard-App festlegen';

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Sie müssen Omi autorisieren, Aufgaben in Ihrem $appName-Konto zu erstellen. Dies öffnet Ihren Browser zur Authentifizierung.';
  }

  @override
  String get cleanUpEllipsis => 'Aufräumen…';

  @override
  String get addTask => 'Aufgabe hinzufügen';

  @override
  String get getCreative => 'Werde kreativ';

  @override
  String get captureRecordingOpenFailed => 'Diese Aufnahme konnte nicht geöffnet werden.';

  @override
  String get emptyTodoMessage => '🎉 Alles erledigt!\nKeine ausstehenden Aufgaben';

  @override
  String get onboardingSetupTitle => 'Dein Omi wird eingerichtet';

  @override
  String get sharePeriodAllTime => 'Bisher hat Omi:';

  @override
  String get translationNotice => 'Übersetzungshinweis';

  @override
  String captureRecordingError(String error) {
    return 'Bei der Aufnahme ist ein Fehler aufgetreten: $error';
  }

  @override
  String get downloadAudio => 'Audio herunterladen';

  @override
  String get identifySpeaker => 'Sprecher zuordnen';

  @override
  String get viewTranscript => 'Transkript anzeigen';

  @override
  String get makeAllMemoriesPublic => 'Alle Erinnerungen öffentlich machen';

  @override
  String get xTwitter => 'X (Twitter)';

  @override
  String get frequencyOff => 'Aus';

  @override
  String get apiEnvironment => 'API-Umgebung';

  @override
  String get processingTakingLonger => 'Arbeitet noch — das dauert länger als üblich.';

  @override
  String get firmwareUpdateFailedTitle => 'Update fehlgeschlagen';

  @override
  String get unresolvedQuestions => 'Offene Fragen';

  @override
  String get chatAppsMessage => 'Nachricht';

  @override
  String get dreamReportManual => 'Manuell';

  @override
  String get enterSttHttpEndpoint => 'Geben Sie Ihren STT-HTTP-Endpunkt ein';

  @override
  String get beforeUpdateMakeSure => 'Vor dem Update sicherstellen:';

  @override
  String get transcriptionReconnecting => 'Transkription wird wiederverbunden…';

  @override
  String get deviceName => 'Gerätename';

  @override
  String neoSubtitle(int count) {
    return '$count Fragen pro Monat';
  }

  @override
  String chatUsageProgress(String used, String limit) {
    return '$used / $limit verwendet';
  }

  @override
  String get noChangesInReview => 'Keine Änderungen in der Bewertung zu aktualisieren.';

  @override
  String get allMemories => 'Alle Erinnerungen';

  @override
  String get needMicrophonePermission =>
      'Wir benötigen Mikrofonberechtigung.\n\n1. Tippen Sie auf \'Berechtigung erteilen\'\n2. Erlauben Sie auf Ihrem iPhone\n3. Uhr-App wird geschlossen\n4. Öffnen Sie sie erneut und tippen Sie auf \'Weiter\'';

  @override
  String get keepSpeakingUntil100 => 'Sprechen Sie weiter, bis Sie 100% erreichen.';

  @override
  String get singleLanguageModeInfo =>
      'Einzel-Sprachmodus ist aktiviert. Übersetzung ist für höhere Genauigkeit deaktiviert.';

  @override
  String get thisCannotBeUndone => 'Dies kann nicht rückgängig gemacht werden';

  @override
  String get setupSkipHelp => 'Überspringen, ich möchte nicht helfen :C';

  @override
  String get speakerTagPromptNoAction => 'Nein…';

  @override
  String labelCopied(String label) {
    return '$label kopiert';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'Fehler beim Wechseln des Audiogeräts: $error';
  }

  @override
  String get remembering => 'Erinnern';

  @override
  String get externalAppAccessDescription =>
      'Die folgenden installierten Apps haben externe Integrationen und können auf Ihre Daten zugreifen, wie Gespräche und Erinnerungen.';

  @override
  String get preferences => 'Einstellungen';

  @override
  String get wrappedFunDay => 'Spaß';

  @override
  String get effectNeeded => 'Nötig für „Bestätigt“';

  @override
  String get importantConversationBody =>
      'Du hattest gerade ein wichtiges Gespräch. Tippe, um die Zusammenfassung zu teilen.';

  @override
  String whyConfidenceMenu(String level) {
    return 'Warum $level?';
  }

  @override
  String get cmdRequired => '⌘ erforderlich';

  @override
  String get completed => 'Abgeschlossen';

  @override
  String get deviceOnboardingVoiceReplyStatusAlwaysSpeaker => 'Wird laut über den Telefonlautsprecher abgespielt.';

  @override
  String get effectCountsAgainst => 'Schadet';

  @override
  String get recaps => 'Rückblicke';

  @override
  String get shareConversationQuestion => 'Unterhaltung teilen?';

  @override
  String get actionItemsCopiedToClipboard => 'Aufgaben in Zwischenablage kopiert';

  @override
  String get appleHealthManageNote =>
      'Omi greift über Apples HealthKit-Framework auf Apple Health zu. Du kannst den Zugriff jederzeit in den iOS-Einstellungen widerrufen.';

  @override
  String addingToService(String serviceName) {
    return 'Wird zu $serviceName hinzugefügt…';
  }

  @override
  String get needHelpGettingStarted => 'Benötigen Sie Hilfe beim Einstieg?';

  @override
  String get thanksForAuthorizing => 'Danke für die Autorisierung!';

  @override
  String get assistantVoiceSettingsTitle => 'Stimme';

  @override
  String get cloudStorageDisabled => 'Cloud-Speicher deaktiviert';

  @override
  String get reviewPlayClip => 'Clip abspielen';

  @override
  String get storeAudioOnCloud => 'Audio in der Cloud speichern';

  @override
  String get syncStatusBackingUp => 'Wird synchronisiert…';

  @override
  String get peopleFilterPinned => 'Angeheftet';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName als Standard-App für Zusammenfassungen festgelegt';
  }

  @override
  String get githubRepositoryUrlRequired => 'GitHub-Repository-URL ist erforderlich';

  @override
  String get microphoneAccess => 'Mikrofonzugriff';

  @override
  String get cancelSubscriptionButton => 'Abonnement kündigen';

  @override
  String get signal => 'Signal';

  @override
  String get failedToConnectAsanaRetry => 'Verbindung zu Asana fehlgeschlagen. Bitte versuchen Sie es erneut.';

  @override
  String get keyCreatedMessage =>
      'Ihr neuer Schlüssel wurde erstellt. Bitte kopieren Sie ihn jetzt. Sie werden ihn nicht mehr sehen können.';

  @override
  String autoRemoveSyncedCopiesDays(int days) {
    return 'Synchronisierte Kopien werden nach $days Tagen gelöscht';
  }

  @override
  String get wrappedMostCringeMoment => 'Peinlichster';

  @override
  String get activity => 'Aktivität';

  @override
  String get calendarSettings => 'Kalendereinstellungen';

  @override
  String get additionalFeedbackOptional => 'Weiteres Feedback (optional)';

  @override
  String get phoneAllow => 'Erlauben';

  @override
  String get noDeviceConnectedUseMic => 'Kein Gerät verbunden. Das Telefonmikrofon wird verwendet.';

  @override
  String get stripeOnboardingInstructions =>
      'Bitte schließen Sie den Stripe-Onboarding-Prozess in Ihrem Browser ab. Diese Seite wird automatisch aktualisiert, sobald der Vorgang abgeschlossen ist.';

  @override
  String availableSpaceWithValue(String space) {
    return 'Verfügbarer Speicher: $space';
  }

  @override
  String get conversationDetails => 'Gesprächsdetails';

  @override
  String get wrappedYouHadFunnyMoments => 'Du hattest lustige Momente dieses Jahr!';

  @override
  String get actionReadConversations => 'Gespräche lesen';

  @override
  String speakerTagPromptIsThisPerson(String name) {
    return 'Ist das $name?';
  }

  @override
  String get openSettings => 'Einstellungen öffnen';

  @override
  String get alwaysAvailable => 'immer verfügbar.';

  @override
  String get rating1PlusStars => '1+ Sterne';

  @override
  String get pauseResume => 'Pause/Fortsetzen';

  @override
  String get conversationDeleted => 'Gespräch gelöscht';

  @override
  String get memoryReviewRight => 'Stimmt';

  @override
  String get deleteGoal => 'Ziel löschen';

  @override
  String get youtube => 'YouTube';

  @override
  String get untitledConversation => 'Unbenanntes Gespräch';

  @override
  String get yourOmiInsights => 'Ihre Omi-Erkenntnisse';

  @override
  String get compareTranscripts => 'Transkripte vergleichen';

  @override
  String get pause => 'Pause';

  @override
  String get successfullyConnectedGoogle => 'Erfolgreich mit Google verbunden!';

  @override
  String planRenewsOn(String date) {
    return 'Ihr Plan verlängert sich am $date.';
  }

  @override
  String chatAppsOpenApp(String app) {
    return '$app öffnen';
  }

  @override
  String get dailySummaryDescription =>
      'Erhalten Sie eine personalisierte Zusammenfassung Ihrer Tagesgespräche als Benachrichtigung.';

  @override
  String conversationPhotosCount(int count) {
    return '$count Fotos';
  }

  @override
  String get errorLoadingAudio => 'Fehler beim Laden der Audiodatei';

  @override
  String get couldNotAccessFile => 'Die ausgewählte Datei konnte nicht geöffnet werden';

  @override
  String deleteGraphFailed(String error) {
    return 'Löschen des Graphen fehlgeschlagen: $error';
  }

  @override
  String get reviewOpenDetailsHint => 'Öffnet Details';

  @override
  String get conversationTimeoutDesc =>
      'Wählen Sie, wie lange bei Stille gewartet werden soll, bevor eine Unterhaltung automatisch beendet wird:';

  @override
  String get transcriptionJsonPlaceholder => 'Fügen Sie hier Ihre JSON-Konfiguration ein…';

  @override
  String get loadingCapabilities => 'Funktionen werden geladen…';

  @override
  String get activeStatus => 'Aktiv';

  @override
  String get noDailyRecapsYet => 'Noch keine täglichen Zusammenfassungen';

  @override
  String get wouldLikePermission =>
      'Wir möchten Ihre Erlaubnis, Ihre Sprachaufnahmen zu speichern. Hier ist der Grund:';

  @override
  String get chatBlockRecommendedNextSteps => 'Empfohlene nächste Schritte';

  @override
  String get tryAdjustingSearchTerms => 'Versuchen Sie, Ihre Suchbegriffe anzupassen';

  @override
  String get connectOmiWithAI => 'Verbinden Sie Omi mit KI-Assistenten';

  @override
  String get whenToReceiveDailySummary => 'Wann Sie Ihre tägliche Zusammenfassung erhalten';

  @override
  String syncCardReadyCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count Aufnahmen bereit zur Synchronisierung',
      one: '1 Aufnahme bereit zur Synchronisierung',
    );
    return '$_temp0';
  }

  @override
  String get yourApiKey => 'IHR API-SCHLÜSSEL';

  @override
  String failedToLoadRepos(String error) {
    return 'Repositories konnten nicht geladen werden: $error';
  }

  @override
  String get syncingMessages => 'Nachrichten werden mit dem Server synchronisiert…';

  @override
  String get pleaseSelectARating => 'Bitte wählen Sie eine Bewertung';

  @override
  String get suggestedTemplates => 'Vorgeschlagene Vorlagen';

  @override
  String get updateAppQuestion => 'App aktualisieren?';

  @override
  String get frequencyDescOff => 'Keine proaktiven Benachrichtigungen';

  @override
  String get triggerAudioBytes => 'Audio-Bytes';

  @override
  String get confirmClearChat => 'Diesen Chat leeren? Dies kann nicht rückgängig gemacht werden.';

  @override
  String get dataPrivacy => 'Datenschutz';

  @override
  String get audioFromOmiWillAppearHere => 'Audio von Omi wird hier erscheinen';

  @override
  String get durationLabel => 'Dauer';

  @override
  String get deviceOnboardingAllSetTitle => 'Alles ist eingerichtet';

  @override
  String msgSelectImagesError(String error) {
    return 'Fehler beim Auswählen von Bildern: $error';
  }

  @override
  String evidenceCardPicks(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'In $count Vorschlägen ausgewählt',
      one: 'In 1 Vorschlag ausgewählt',
    );
    return '$_temp0';
  }

  @override
  String get connectionLostDesc =>
      'Die Verbindung wurde unterbrochen. Bitte überprüfen Sie Ihre Internetverbindung und versuchen Sie es erneut.';

  @override
  String get defaultLabel => 'Standard';

  @override
  String get raybanMetaAllowCamera => 'Kamera der Brille erlauben';

  @override
  String get addAppSelectCoreCapability =>
      'Bitte wählen Sie eine weitere Kernfähigkeit für Ihre App aus, um fortzufahren';

  @override
  String get noManualMemories => 'Noch keine manuellen Erinnerungen';

  @override
  String get deliveryTime => 'Lieferzeit';

  @override
  String get defaultProjectOptional => 'Standardprojekt (Optional)';

  @override
  String get devModeInvalidAudioBytesWebhookUrl => 'Ungültige Webhook-URL für Audio-Bytes';

  @override
  String get ignoredVoicesTitle => 'Ignorierte Stimmen';

  @override
  String get refreshManifest => 'Manifest aktualisieren';

  @override
  String get diagnosticsRightNow => 'Aktuell';

  @override
  String get reviewDue => 'Fällig';

  @override
  String get unmute => 'Ton an';

  @override
  String get recordingsDeleted => 'Aufnahmen gelöscht.';

  @override
  String get failedToDeleteFolder => 'Ordner konnte nicht gelöscht werden';

  @override
  String get reviewAnswerOther => 'Andere';

  @override
  String get exportedConversations => 'Exportierte Unterhaltungen von Omi';

  @override
  String get privacyPolicy => 'Datenschutzrichtlinie';

  @override
  String get editReply => 'Antwort bearbeiten';

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription und wird $triggerDescription.';
  }

  @override
  String errorSaving(String error) {
    return 'Fehler beim Speichern: $error';
  }

  @override
  String get diagnosticsConnectedFor => 'Verbunden seit';

  @override
  String get callStateConnecting => 'Verbinden…';

  @override
  String get conversationUrlNotShared => 'Unterhaltungs-URL konnte nicht geteilt werden.';

  @override
  String get tooShortDesc =>
      'Es wurde nicht genug Sprache erkannt. Bitte sprechen Sie mehr und versuchen Sie es erneut.';

  @override
  String get failedToShareRecap => 'Zusammenfassung konnte nicht geteilt werden';

  @override
  String get billingMonthly => 'Monatlich';

  @override
  String get developingLogic => 'Entwickle Logik';

  @override
  String get phoneContinue => 'Weiter';

  @override
  String get successfullyConnectedGitHub => 'Erfolgreich mit GitHub verbunden!';

  @override
  String get failedToSubmitReview => 'Bewertung konnte nicht gesendet werden. Bitte versuche es erneut.';

  @override
  String get anyoneCanDiscover => 'Jeder kann Ihre App entdecken';

  @override
  String get v2Undetected => 'V2 nicht erkannt';

  @override
  String get usageIrlEvents => 'Bei Veranstaltungen';

  @override
  String get conversationPromptHint =>
      'z.B. Extrahieren Sie Aufgaben, getroffene Entscheidungen und wichtige Erkenntnisse aus dem Gespräch.';

  @override
  String get openProviderDocs => 'Dokumentation öffnen';

  @override
  String get showMeetingsInMenuBar => 'Meetings in Menüleiste anzeigen';

  @override
  String get viewPlansAndUsage => 'Pläne & Nutzung Anzeigen';

  @override
  String get buildSubmitCustomOmiApp => 'Erstellen und senden Sie Ihre benutzerdefinierte Omi-App';

  @override
  String get failedToRefreshGoogleStatus => 'Google-Verbindungsstatus konnte nicht aktualisiert werden.';

  @override
  String get feedbackSubtitleTooExpensive => 'Dein Feedback hilft uns, die richtige Balance zu finden.';

  @override
  String get startUsingOmi => 'Omi verwenden';

  @override
  String get dreamReportLearnedWords => 'Gelernte Wörter';

  @override
  String get actionItemCreated => 'Aufgabe erstellt';

  @override
  String get exportAllConversationsToJson => 'Exportieren Sie alle Ihre Unterhaltungen in eine JSON-Datei.';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain =>
      'Bitte überprüfen Sie Ihre Internetverbindung und versuchen Sie es erneut';

  @override
  String get callStateEnded => 'Anruf beendet';

  @override
  String get phoneNumberHint => 'Telefonnummer';

  @override
  String get tasksGroupByProject => 'Nach Projekt gruppieren';

  @override
  String get phoneCallsUnlimitedOnly => 'Telefonanrufe über Omi';

  @override
  String get frequencyDescMinimal => 'Nur Dringendes, etwa 1–3 pro Tag';

  @override
  String get changeYourName => 'Namen ändern';

  @override
  String get editYourReply => 'Antwort bearbeiten';

  @override
  String get publicMemories => 'Öffentliche Erinnerungen';

  @override
  String get monthDec => 'Dez';

  @override
  String get reviewNewPersonName => 'Name der Person';

  @override
  String get googleCalendarConnectPrompt =>
      'Verbinden Sie Ihren Google Kalender, um Konversationen mit Kalenderterminen zu verknüpfen.';

  @override
  String get realtimeAudioBytes => 'Echtzeit-Audio-Bytes';

  @override
  String get trackYourGoalsOnHomepage => 'Verfolge deine Ziele auf der Startseite';

  @override
  String get chatAddAttachment => 'Anhang hinzufügen';

  @override
  String get beta => 'BETA';

  @override
  String get createMemory => 'Erinnerung erstellen';

  @override
  String get permissionsRequiredDescription =>
      'Omi benötigt einige Berechtigungen, um richtig zu funktionieren. Bitte erteile sie, um fortzufahren.';

  @override
  String get dataCollectionMessage =>
      'Durch Fortfahren werden Ihre Gespräche, Aufnahmen und persönlichen Informationen sicher auf unseren Servern gespeichert, um KI-gestützte Einblicke zu bieten und alle App-Funktionen zu ermöglichen.';

  @override
  String get batteryLevel => 'Batteriestand';

  @override
  String get searchCountries => 'Länder suchen...';

  @override
  String get confidenceSheetTitle => 'Sicherheit';

  @override
  String get deviceModelLabel => 'Gerätemodell';

  @override
  String get noStableFirmwareFound => 'Es konnte keine stabile Firmware-Version für Ihr Gerät gefunden werden.';

  @override
  String get noResultsFound => 'Keine Ergebnisse gefunden';

  @override
  String get wrappedMins => 'Min';

  @override
  String get chatAppsTelegramSubtitle => 'In zwei Taps eingerichtet';

  @override
  String get categoryConversationAnalysis => 'Gesprächsanalyse';

  @override
  String get target => 'Ziel';

  @override
  String get apiKeyRequired => 'API-Schlüssel ist erforderlich';

  @override
  String otaUpdatedMessage(String deviceName) {
    return '$deviceName ist aktualisiert und startet von selbst neu.';
  }

  @override
  String get reconnections => 'Neuverbindungen';

  @override
  String errorCheckingConnection(String error) {
    return 'Fehler beim Überprüfen der Verbindung: $error';
  }

  @override
  String get usageMonth => 'Diesen Monat';

  @override
  String get additionalSpeechSampleRemoved => 'Zusätzliche Sprachprobe entfernt';

  @override
  String get speakerTagPromptExcerptSaved => 'Antwort für diesen Ausschnitt gespeichert.';

  @override
  String get omisStorage => 'Omis Speicher';

  @override
  String get recordingAndTranscription => 'Aufnahme & Transkription';

  @override
  String get categoryCommunication => 'Kommunikation';

  @override
  String get wrappedYouDidIt => 'Du hast es geschafft! 🎉';

  @override
  String get failedToDeleteItems => 'Löschen der Elemente fehlgeschlagen';

  @override
  String speakerLabelLinesLabeled(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count Zeilen zugeordnet',
      one: '1 Zeile zugeordnet',
    );
    return '$_temp0';
  }

  @override
  String get generatingLink => 'Link wird generiert…';

  @override
  String get clickHereForAppBuildingGuides => 'Klicken Sie hier für App-Erstellungsanleitungen und Dokumentation';

  @override
  String get authUrl => 'Authentifizierungs-URL';

  @override
  String get addAppCapabilityConflictWithPersona => 'Andere Fähigkeiten können nicht mit Persona ausgewählt werden';

  @override
  String get deviceOnboardingVoiceReplyGenericHeadphones => 'Kopfhörer';

  @override
  String get clearAll => 'Alles löschen';

  @override
  String get noKnowledgeGraphYet => 'Noch kein Wissensgraph vorhanden';

  @override
  String get messageReportedSuccessfully => '✅ Nachricht erfolgreich gemeldet';

  @override
  String get paymentFailedToSetDefault =>
      'Standard-Zahlungsmethode konnte nicht festgelegt werden. Bitte versuchen Sie es später erneut.';

  @override
  String get memoryReviewUpdated => 'Aktualisiert.';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'Ihr Plan endet am $date.';
  }

  @override
  String get welcomeToOmi => 'Willkommen bei Omi';

  @override
  String get phoneFreeCallLimitReached =>
      'Monatliches Limit für kostenlose Anrufe erreicht. Es wird nächsten Monat zurückgesetzt.';

  @override
  String get omiTranscriptionOptimized =>
      'Die Live-Transkription von Omi ist für Echtzeitgespräche gemacht und zeigt, wer was gesagt hat.';

  @override
  String get chatAppsLoadFailedTitle => 'Chat-Apps konnten nicht geladen werden';

  @override
  String get continueWithGoogle => 'Mit Google fortfahren';

  @override
  String get setupSteps => 'Einrichtungsschritte';

  @override
  String totalMemoriesCount(int count) {
    return 'Sie haben insgesamt $count Erinnerungen';
  }

  @override
  String get feedbackSubtitleBatteryDrain => 'Das hilft unserem Hardware-Team sich zu verbessern.';

  @override
  String get tryIt => 'Ausprobieren';

  @override
  String get chatAppsInsights => 'Einblicke von Omi';

  @override
  String nFiles(int count) {
    return '$count Aufnahmen';
  }

  @override
  String get clearChatTitle => 'Chat löschen?';

  @override
  String get onlyYouCanUseTemplate => 'Nur Sie können diese Vorlage verwenden';

  @override
  String get raybanMetaCameraExplanation =>
      'Omi verwendet die Kamera Ihrer Brille, um Fotos zu Ihren Gesprächen hinzuzufügen. Sie können dies überspringen und nur Audio verwenden.';

  @override
  String get deviceDiagnosticsTicket => 'Support-Ticketcode';

  @override
  String get capabilityTasks => 'Aufgaben';

  @override
  String get copyUrl => 'URL kopieren';

  @override
  String keepItemPublic(String item) {
    return '$item öffentlich lassen';
  }

  @override
  String get chatStarterTeachMe => 'Kannst du mir etwas Neues beibringen?';

  @override
  String get cancelReasonDetailHint => 'Wir schätzen jedes Feedback…';

  @override
  String get checkConnectionTryAgain => 'Überprüfe deine Verbindung und versuche es erneut.';

  @override
  String get backToConversations => 'Zurück zu Gesprächen';

  @override
  String get merge => 'Zusammenführen';

  @override
  String get couldNotLaunchUpgradePage => 'Die Upgrade-Seite konnte nicht geöffnet werden. Bitte versuche es erneut.';

  @override
  String get deviceOnboardingTranscriptionSubtitle =>
      'Sag ein paar Worte und sieh ihnen in Echtzeit beim Erscheinen zu';

  @override
  String get deleteOnDeviceModelConfirm => 'Dieses Modell löschen?';

  @override
  String get reviewQuestionSpeaker => 'Wer hat das gesagt?';

  @override
  String updatedDate(String date) {
    return 'Aktualisiert am $date';
  }

  @override
  String get saveSettings => 'Einstellungen Speichern';

  @override
  String get alreadyGavePermission =>
      'Sie haben uns bereits die Erlaubnis gegeben, Ihre Aufnahmen zu speichern. Hier ist eine Erinnerung, warum wir sie brauchen:';

  @override
  String get appCreatedAndInstalled => 'App erstellt und installiert!';

  @override
  String get failedToRefreshNotionStatus => 'Notion-Verbindungsstatus konnte nicht aktualisiert werden.';

  @override
  String get deviceOnboardingProcessingQuestion => 'Deine Frage wird verarbeitet…';

  @override
  String get chatBlockTask => 'Aufgabe';

  @override
  String get pendantNotConnected => 'Pendant nicht verbunden. Zum Synchronisieren verbinden.';

  @override
  String get createActionItem => 'Aufgabe erstellen';

  @override
  String get logsCopied => 'Protokolle kopiert';

  @override
  String get timeout5MinutesDesc => 'Unterhaltung nach 5 Minuten Stille beenden';

  @override
  String get msgUploadFileFailed => 'Datei-Upload fehlgeschlagen, bitte versuchen Sie es später erneut';

  @override
  String get reportMessageConfirm => 'Diese Nachricht melden?';

  @override
  String deletePersonConfirmation(String name) {
    return 'Dadurch werden die Stimmproben von $name entfernt. Das lässt sich nicht rückgängig machen. Die Beiträge in früheren Gesprächen werden zu unbenannten Sprechern.';
  }

  @override
  String get weekdayTue => 'Di';

  @override
  String get liveTranscript => 'Live-Transkript';

  @override
  String timeDaysAndHours(int days, int hours) {
    return '$days Tage $hours Stunden';
  }

  @override
  String versionLabel(String version) {
    return 'Version $version';
  }

  @override
  String get cancelConsequenceDelay => '5-7 Sekunden Verarbeitungsverzögerung (Modelle auf dem Gerät)';

  @override
  String captureRecordingSeparateMessage(String recording) {
    return '$recording wird als eigenes Gespräch angezeigt und nicht erneut mit diesem Ereignis gruppiert.';
  }

  @override
  String get updateAvailableTitle => 'Update verfügbar';

  @override
  String get dreamReportShadowBanner =>
      'Vorschaumodus: Dream zeigt, was es ändern würde, aber in deinem Konto ändert sich noch nichts.';

  @override
  String get sharedTasksAcceptFailed =>
      'Diese Aufgaben konnten nicht übernommen werden. Vielleicht hast du diese Freigabe bereits angenommen.';

  @override
  String get appPricingLabel => 'App-Preisgestaltung';

  @override
  String get reDownload => 'Erneut herunterladen';

  @override
  String get recordWithPhoneMic => 'Mit Telefonmikrofon aufnehmen';

  @override
  String appDisabledOn(String date) {
    return 'Deaktiviert am $date.';
  }

  @override
  String get play => 'Abspielen';

  @override
  String get private => 'Privat';

  @override
  String get speakerTagPromptNotSureAction => 'Nicht sicher';

  @override
  String get showDiscardedConversationsDesc => 'Als verworfen markierte Unterhaltungen einschließen';

  @override
  String get captureModeLiveDescription => 'Transkribiere in Echtzeit, während du sprichst.';

  @override
  String get subscriptionCancelledSuccessfully =>
      'Abonnement erfolgreich gekündigt. Es bleibt bis zum Ende des aktuellen Abrechnungszeitraums aktiv.';

  @override
  String get tapToSetAGoal => 'Tippen, um ein Ziel zu setzen';

  @override
  String get tellUsMoreWhatWentWrong => 'Erzählen Sie uns mehr darüber, was schief gelaufen ist…';

  @override
  String get downgradeToFreemiumTitle => 'Auf Freemium herabstufen?';

  @override
  String get usageTasks => 'Aufgaben';

  @override
  String get chatReplyOffline => 'Verbindung nicht möglich. Prüfe deine Verbindung und versuche es erneut.';

  @override
  String get makePublic => 'Öffentlich machen';

  @override
  String get authUnexpectedErrorFirebase =>
      'Unerwarteter Fehler bei der Anmeldung, Firebase-Fehler, bitte versuchen Sie es erneut.';

  @override
  String get unlimitedConversations => 'Unbegrenzte Gespräche';

  @override
  String get stagingDisclaimer =>
      'Die Testumgebung kann instabil sein, inkonsistente Leistung aufweisen und Daten können verloren gehen. Nur zum Testen.';

  @override
  String get captureMicrophonePermissionRequired => 'Mikrofonberechtigung erforderlich';

  @override
  String shareStatsInsights(String count) {
    return '✨ $count Erkenntnisse geliefert';
  }

  @override
  String get feedbackReasonSummaryIrrelevant => 'Nicht relevant';

  @override
  String get userIdCopiedToClipboard => 'Benutzer-ID kopiert';

  @override
  String get urlCopiedToClipboard => 'URL in Zwischenablage kopiert';

  @override
  String annualBillingSummary(int months, String price) {
    return '$months Monate / $price';
  }

  @override
  String chatAppsShowInAppOff(String app) {
    return 'Aus: Du siehst sie nur in $app.';
  }

  @override
  String get replySentSuccessfully => 'Antwort erfolgreich gesendet';

  @override
  String get deviceOnboardingTurnOffTitle => 'Ausschalten';

  @override
  String get phoneStorageDesc =>
      'Wenn Omi sich wieder verbindet, werden Aufnahmen automatisch auf Ihr Telefon übertragen, bevor sie hochgeladen werden.';

  @override
  String get callRecordingConsentDisclaimer =>
      'Anrufaufzeichnung kann in Ihrer Gerichtsbarkeit eine Einwilligung erfordern';

  @override
  String get showDiscardedConversations => 'Verworfene Unterhaltungen anzeigen';

  @override
  String get calendarIntegration => 'Kalenderintegration';

  @override
  String get whisperModelSizeBase => 'Basis';

  @override
  String get shareViaSms => 'Per SMS teilen';

  @override
  String get nameMustBeAtLeast3Characters => 'Der Name muss mindestens 3 Zeichen haben';

  @override
  String get chatDiscardRecording => 'Verwerfen';

  @override
  String get chatAppsProPerkText => 'Schreib Omi über Telegram und iMessage';

  @override
  String get readyToSync => 'Bereit zum Synchronisieren';

  @override
  String get noAppsInCategoryYet => 'Noch keine Apps in dieser Kategorie';

  @override
  String get firmwareUpdateAvailable => 'Firmware-Update verfügbar';

  @override
  String get modelNumber => 'Modellnummer';

  @override
  String get sortBy => 'Sortieren';

  @override
  String get slideToUpdate => 'Zum Aktualisieren wischen';

  @override
  String get effectBarelyCounts => 'Hilft kaum';

  @override
  String get onlyYouCanUse => 'Nur Sie können diese App verwenden';

  @override
  String get triggersWhenNewConversationCreated => 'Wird ausgelöst, wenn eine neue Unterhaltung erstellt wird.';

  @override
  String get paymentPlan => 'Zahlungsplan';

  @override
  String get whisperModelDesc => 'Wählen Sie das Modell für die Transkription auf dem Gerät';

  @override
  String get askSuggestOwe => 'Was schulde ich anderen noch?';

  @override
  String get starConversation => 'Unterhaltung favorisieren';

  @override
  String get hardwareSection => 'Hardware';

  @override
  String get transcribing => 'Transkribieren…';

  @override
  String get chatAppsVoiceNotesSubtitle => 'Sende eine Sprachnachricht und Omi antwortet darauf.';

  @override
  String confidenceNextVoice(String name) {
    return 'Omi braucht außerdem eine Stimmprobe von $name. Ordne die Person zu, während „Stimmen merken“ aktiviert ist.';
  }

  @override
  String get rating3PlusStars => '3+ Sterne';

  @override
  String get recordingActive => 'Aufnahme aktiv';

  @override
  String starFilter(int count) {
    return '$count Stern';
  }

  @override
  String get storageLocationLabel => 'Speicherort';

  @override
  String get reviewNoChangesBody => 'Wenn Omi deine Notizen aufräumt, erscheinen die Änderungen hier.';

  @override
  String get testPrompt => 'Prompt testen';

  @override
  String get otaUpdateUnavailable => 'Dieses Update ist gerade nicht verfügbar. Versuche es später erneut.';

  @override
  String get downloading => 'Wird heruntergeladen…';

  @override
  String get welcomeBackSimple => 'Willkommen zurück';

  @override
  String get sttProviderSoniox => 'Soniox';

  @override
  String get clearAllSelection => 'Alle löschen';

  @override
  String get confidenceReasonNeverConfirmed => 'Nie bestätigt';

  @override
  String get writeScope => 'Schreiben';

  @override
  String get evidenceVoiceReady => 'Stimmprobe bereit';

  @override
  String get updateApp => 'App aktualisieren';

  @override
  String get weekdayThu => 'Do';

  @override
  String chatUsageCostNoLimit(String used) {
    return 'Chat: \$$used diesen Monat verbraucht';
  }

  @override
  String get configCopied => 'Konfiguration in die Zwischenablage kopiert';

  @override
  String get startupFailedConfigMessage =>
      'Diese Version von Omi hat ein Konfigurationsproblem. Es liegt nicht an deinem Gerät. Kontaktiere den Support und gib die Details unten an.';

  @override
  String get getOmiForMac => 'Omi für Mac holen';

  @override
  String get appleHealthConnectedBadge => 'Verbunden';

  @override
  String get msgCameraNotAvailable => 'Kameraaufnahme ist auf dieser Plattform nicht verfügbar';

  @override
  String get actionItemsDescription => 'Tippen zum Bearbeiten • Lang drücken zum Auswählen • Wischen für Aktionen';

  @override
  String get notificationsDesc =>
      'Damit Omi dir Gesprächszusammenfassungen, Aufgabenerinnerungen und Antworten deiner Apps senden kann.';

  @override
  String audioUploadRetrying(String duration) {
    return 'Upload wird wiederholt… $duration Audio auf Ihrem Telefon gespeichert';
  }

  @override
  String get importStarted => 'Import gestartet! Sie werden benachrichtigt, wenn er abgeschlossen ist.';

  @override
  String get onDeviceModelDownloadFailed => 'Modell-Download fehlgeschlagen';

  @override
  String get noProjectsInWorkspace => 'Keine Projekte in diesem Arbeitsbereich gefunden';

  @override
  String get helpCenter => 'Hilfe-Center';

  @override
  String get trainingDataBullets =>
      '• Deine Daten helfen, KI-Modelle zu verbessern\n• Nur nicht sensible Daten werden geteilt';

  @override
  String get invalidPromotionCode => 'Ungültiger Aktionscode.';

  @override
  String get battery => 'Batterie';

  @override
  String get clearSelection => 'Auswahl löschen';

  @override
  String get phoneSetupStep2Subtitle => 'Ein kurzer Code, den Sie beim Anruf eingeben';

  @override
  String get googleSearch => 'Google Search';

  @override
  String get charging => 'Wird geladen';

  @override
  String deleteNamedPerson(String name) {
    return '$name löschen';
  }

  @override
  String get chatAppsPartOfPro => 'Chat-Apps gehören zu Pro';

  @override
  String get invalidWebhookUrlError => 'Bitte gib eine gültige Webhook-URL ein';

  @override
  String get starConversationsToFindQuickly => 'Markieren Sie Gespräche, um sie hier schnell zu finden';

  @override
  String get permissionCreateMemories => 'Erinnerungen erstellen';

  @override
  String get conversationIdCopied => 'Konversations-ID in Zwischenablage kopiert';

  @override
  String get chatAppsMessagesApp => 'Nachrichten';

  @override
  String get understandingWords => 'Verstehen (Wörter)';

  @override
  String diagnosticsVerdictTroubleDetail(int count) {
    return 'Fehlgeschlagene Verbindungen in den letzten 24 Stunden: $count';
  }

  @override
  String get editName => 'Name bearbeiten';

  @override
  String get askAboutThisConversation => 'Dazu fragen';

  @override
  String get useTemplateFrom => 'Vorlage verwenden von';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'Mikrofonberechtigungsstatus: $status. Bitte überprüfen Sie die Systemeinstellungen.';
  }

  @override
  String get markAsCompleted => 'Als erledigt markieren';

  @override
  String get urlMustEndWithSlashError => 'URL muss mit \"/\" enden';

  @override
  String get deviceOnboardingIntroTitle => 'Lerne dein Omi kennen';

  @override
  String nPending(int count) {
    return '$count ausstehend';
  }

  @override
  String get howShouldOmiCallYou => 'Wie soll Omi Sie nennen?';

  @override
  String get preparingFormForYou => 'Das Formular wird für Sie vorbereitet…';

  @override
  String get deleteChat => 'Chat löschen';

  @override
  String get msgPhotosPermissionDenied =>
      'Fotos-Berechtigung verweigert. Bitte erlauben Sie den Zugriff auf Fotos, um Bilder auszuwählen';

  @override
  String get moreWaysToRecord => 'Weitere Aufnahmeoptionen';

  @override
  String get creatingPlan => 'Erstelle Plan';

  @override
  String get configCopiedToClipboard => 'Konfiguration in die Zwischenablage kopiert';

  @override
  String get transcribeLaterDescription =>
      'Jetzt aufnehmen, später transkribieren. Bis dahin bleibt das Audio auf deinem Telefon.';

  @override
  String get couldNotSwitchToFreePlan => 'Konnte nicht zum kostenlosen Plan wechseln. Bitte versuchen Sie es erneut.';

  @override
  String get wrappedTasksCompleted => 'Aufgaben erledigt';

  @override
  String get deviceOnboardingTranscriptionTitle => 'Sprich in dein Omi';

  @override
  String get thankYouRequestUnderReview =>
      'Vielen Dank! Ihre Anfrage wird geprüft. Wir benachrichtigen Sie nach der Genehmigung.';

  @override
  String get unpairAndForgetDevice => 'Gerät entkoppeln und vergessen';

  @override
  String get sendWebUrl => 'Web-URL senden';

  @override
  String get noTasksForToday => 'Keine Aufgaben für heute.\nFrage Omi nach mehr Aufgaben oder erstelle sie manuell.';

  @override
  String get conversationSummaryFailed => 'Zusammenfassung fehlgeschlagen';

  @override
  String get realtimeTranscript => 'Echtzeit-Transkript';

  @override
  String nConversationsCreated(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count Gespräche erstellt',
      one: '1 Gespräch erstellt',
    );
    return '$_temp0';
  }

  @override
  String get noEmailSet => 'Keine E-Mail festgelegt';

  @override
  String get setDueDateAndTime => 'Fälligkeitsdatum und Uhrzeit festlegen';

  @override
  String get pairingDescFieldy => 'Halten Sie das Gerät gedrückt, bis das Licht erscheint, um es einzuschalten.';

  @override
  String get maximumSecurityE2ee => 'Maximale Sicherheit (E2EE)';

  @override
  String get instantSpeakerLabels => 'Sofortige Sprecherkennzeichnung';

  @override
  String get resetRequestConfig => 'Anfragekonfiguration auf Standard zurücksetzen';

  @override
  String get webhookUrlNotSet => 'Webhook-URL nicht festgelegt';

  @override
  String get feedbackReasonRecordingOther => 'Etwas anderes';

  @override
  String get accountCutoverMigrationRollbackMessage =>
      'Dein Konto ist nach einem Migrations-Rollback in Wartung. Neuere Daten können isoliert sein.';

  @override
  String get cancelConsequenceQuality => '30% geringere Transkriptionsqualität (Modelle auf dem Gerät)';

  @override
  String get pairingDescPlaudNote =>
      'Halten Sie die Seitentaste 2 Sekunden gedrückt. Die rote LED blinkt, wenn das Gerät kopplungsbereit ist.';

  @override
  String get plansAndBilling => 'Pläne & Abrechnung';

  @override
  String get deviceOnboardingVoiceReplyTitle => 'Omis Antworten anhören';

  @override
  String get generatingIcon => 'Generiere Icon…';

  @override
  String get cleanUpBannerBody =>
      'Meist falsch verstandene Namen. Sieh sie dir an und entferne die, die es nicht wirklich gibt.';

  @override
  String get speakerTagPromptSavedAsYou => 'Als deine Stimme gespeichert';

  @override
  String get connectOmiOmiGlass => 'Omi / OmiGlass verbinden';

  @override
  String get capabilityConversations => 'Gespräche';

  @override
  String get notificationFrequencyDescription =>
      'Steuern Sie, wie oft Omi Ihnen proaktive Benachrichtigungen und Erinnerungen sendet.';

  @override
  String chatScopeAbout(String title) {
    return 'Über: $title';
  }

  @override
  String get importHistory => 'Importverlauf';

  @override
  String get getApiKey => 'API-Schlüssel holen';

  @override
  String get nothingInterestingRetry => 'Nichts Interessantes gefunden,\nmöchten Sie es erneut versuchen?';

  @override
  String get whatWouldYouLikeToCreate => 'Was möchten Sie erstellen?';

  @override
  String get pricingFree => 'Kostenlos';

  @override
  String get speakerTagPromptHintIdentify => 'Deine Antwort hilft Omi, diese Stimme beim nächsten Mal zu erkennen.';

  @override
  String get noConversationsYet => 'Noch keine Unterhaltungen';

  @override
  String get deviceNotMeetRequirements =>
      'Ihr Gerät erfüllt nicht die Anforderungen für die Transkription auf dem Gerät.';

  @override
  String get pressKeys => 'Tasten drücken…';

  @override
  String get downgradeLimitDelayNotRealTime => '5–7 Sekunden Verzögerung (nicht in Echtzeit)';

  @override
  String get conversationLinkCopiedToClipboard => 'Gesprächslink in Zwischenablage kopiert';

  @override
  String get onboardingSetupStepMemory => 'Dein Gedächtnis wird eingerichtet';

  @override
  String get chatAppsTelegramOtherDevice => 'Telegram auf einem anderen Gerät?';

  @override
  String get appNotFoundOrRemoved => 'Diese App ist nicht mehr verfügbar';

  @override
  String appsCount(String count) {
    return '$count Apps';
  }

  @override
  String get endToEndEncryption => 'End-to-End-Verschlüsselung';

  @override
  String otaConnectFailed(String deviceName) {
    return 'Keine Verbindung zu $deviceName. Lass es eingeschaltet und in der Nähe und versuche es erneut.';
  }

  @override
  String get continueButton => 'Weiter';

  @override
  String get failedToPrepareConversationForSharing =>
      'Gespräch konnte nicht zum Teilen vorbereitet werden. Bitte versuchen Sie es erneut.';

  @override
  String get showAll => 'Alle anzeigen →';

  @override
  String get speakerLabelYou => 'Sie';

  @override
  String get wrappedActionItems => 'Aufgaben';

  @override
  String failedToInstallApp(String appName) {
    return 'Installation von $appName fehlgeschlagen. Bitte erneut versuchen.';
  }

  @override
  String get searching => 'Suche läuft';

  @override
  String get deviceNotCompatibleTitle => 'Gerät nicht kompatibel';

  @override
  String get summarize => 'Zusammenfassen';

  @override
  String get exportConversationsToJson => 'Gespräche in eine JSON-Datei exportieren';

  @override
  String makeItemPrivateExplanation(String item) {
    return 'Wenn Sie $item jetzt privat machen, funktioniert es für niemanden mehr und ist nur für Sie sichtbar';
  }

  @override
  String get wrappedFailedToShare => 'Teilen fehlgeschlagen. Bitte erneut versuchen.';

  @override
  String get cancelSubscriptionConfirmation =>
      'Sie haben weiterhin Zugang bis zum Ende Ihres aktuellen Abrechnungszeitraums.';

  @override
  String get phoneHideKeypad => 'Tastatur ausblenden';

  @override
  String get vadGate => 'VAD Gate';

  @override
  String get nameUpdatedSuccessfully => 'Name erfolgreich aktualisiert!';

  @override
  String get photoLibrary => 'Fotomediathek';

  @override
  String get chatAppsHeroMessage =>
      'Frag nach deinem Tag, speichere Erinnerungen und verwalte Aufgaben über Telegram oder iMessage. Deine Chats bleiben in der App, die du nutzt, und Omi erinnert sich überall daran, worüber ihr gesprochen habt.';

  @override
  String get upgradeToAnnualPlan => 'Auf Jahresplan upgraden';

  @override
  String get completeAuthInBrowser =>
      'Bitte schließen Sie die Authentifizierung in Ihrem Browser ab. Kehren Sie danach zur App zurück.';

  @override
  String errorLabel(String error) {
    return 'Fehler: $error';
  }

  @override
  String get durationThresholdDesc => 'Unterhaltungen ausblenden, die kürzer als dies sind';

  @override
  String transcriptionsPendingCount(int count) {
    return 'Offene Transkriptionen $count';
  }

  @override
  String get transcribeLaterNote =>
      'Funktioniert mit dem Telefonmikrofon sowie Omi- und Limitless-Geräten. Das Audio bleibt auf deinem Smartphone, bis du es hochladen möchtest.';

  @override
  String get device => 'Gerät';

  @override
  String get signUpSuccess => 'Registrierung erfolgreich!';

  @override
  String get onboardingPermissions => 'Berechtigungen';

  @override
  String get modelTooLargeWarning =>
      'Dieses Modell ist groß und kann zum Absturz der App führen oder sehr langsam auf mobilen Geräten laufen.\n\nsmall oder base wird empfohlen.';

  @override
  String get showDailyScoreOnHomepage => 'Tagespunktzahl auf der Startseite anzeigen';

  @override
  String confidenceSummaryUnverified(String name) {
    return 'Du hast $name noch nicht markiert oder bestätigt, daher ist Omi nicht sicher, ob es die Stimme kennt.';
  }

  @override
  String get endConversation => 'Unterhaltung beenden';

  @override
  String get unpinAsBaseline => 'Von Basis lösen';

  @override
  String audioSavedLocally(String duration) {
    return '$duration Audio lokal gespeichert';
  }

  @override
  String get editMemory => '✏️ Erinnerung bearbeiten';

  @override
  String get speakerTagPromptThanks => 'Danke! Omi wird Stimmen immer besser erkennen.';

  @override
  String get actionItemDescriptionEmpty => 'Aufgabenbeschreibung darf nicht leer sein.';

  @override
  String get maybeLater => 'Vielleicht später';

  @override
  String get daySummary => 'Tageszusammenfassung';

  @override
  String get confirmReportMessage => 'Diese Nachricht melden?';

  @override
  String get deleteAllLimitlessConversations => 'Alle Limitless-Gespräche löschen?';

  @override
  String get selectAllTasksMenu => 'Alle auswählen';

  @override
  String get syncStatusRetrying => 'Verarbeitung fehlgeschlagen — wird wiederholt';

  @override
  String get exportButton => 'Exportieren';

  @override
  String get wrappedYouTalkedAboutBadge => 'Du hast über gesprochen';

  @override
  String get firmwareWarningTitle => 'Wichtig: Vor dem Update lesen';

  @override
  String get permissionTypeCreate => 'Erstellen';

  @override
  String get viewUsage => 'Nutzung anzeigen';

  @override
  String get deviceOnboardingIntroDuration => 'Etwa 1 Minute';

  @override
  String get import => 'Importieren';

  @override
  String get conversationsExportStarted =>
      'Export der Unterhaltungen gestartet. Dies kann einige Sekunden dauern, bitte warten.';

  @override
  String get speechToTextProvider => 'Sprache-zu-Text-Anbieter';

  @override
  String get languageTranslation => 'Übersetzung in 100+ Sprachen';

  @override
  String get primaryLanguage => 'Hauptsprache';

  @override
  String durationSeconds(String seconds) {
    return 'Dauer: $seconds Sekunden';
  }

  @override
  String get autoSyncDescription => 'Offline-Aufnahmen automatisch synchronisieren, wenn dein Gerät verbunden wird';

  @override
  String get debugLogs => 'Debug-Protokolle';

  @override
  String get authorizationRevoked => 'Autorisierung widerrufen.';

  @override
  String get noTranscriptAvailable => 'Kein Transkript verfügbar';

  @override
  String get available => 'Verfügbar';

  @override
  String get wrappedObsessionsLabelUpper => 'LEIDENSCHAFTEN';

  @override
  String get professionStudent => 'Student';

  @override
  String get chatAppsTryRemind => 'Erinnere mich daran, am Sonntag Mama anzurufen';

  @override
  String get failedToStartVerification => 'Verifizierung konnte nicht gestartet werden';

  @override
  String get failedToCreateFolder => 'Ordner konnte nicht erstellt werden';

  @override
  String timeMinSingular(int count) {
    return '$count Min';
  }

  @override
  String get insights => 'Erkenntnisse';

  @override
  String get privacyInformation => 'Datenschutzinformationen';

  @override
  String get finishedConversation => 'Gespräch beendet?';

  @override
  String get syncGoogleAccount => 'Mit Ihrem Google-Konto synchronisieren';

  @override
  String get pairingTitleNeoOne => 'Neo One in den Kopplungsmodus versetzen';

  @override
  String get translatedByOmi => 'übersetzt von Omi';

  @override
  String get githubRepositoryUrl => 'GitHub-Repository-URL';

  @override
  String get readOnlyScope => 'Nur Lesen';

  @override
  String get chatAppsChannelsTitle => 'Chat-Apps';

  @override
  String get chatAppsDoesAnswer => 'Beantwortet Fragen zu deinen Gesprächen und Erinnerungen';

  @override
  String get wrappedFailedToStartGeneration => 'Generierung konnte nicht gestartet werden. Bitte erneut versuchen.';

  @override
  String get storageLocationSdCard => 'SD-Karte';

  @override
  String get askSuggestDecide => 'Was habe ich heute entschieden?';

  @override
  String get close => 'Schließen';

  @override
  String get paymentMethodPayPal => 'PayPal';

  @override
  String categoryAppCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count Apps',
      one: '1 App',
    );
    return '$_temp0';
  }

  @override
  String get speakerTagPromptRecentPeople => 'Personen, mit denen du zuletzt gesprochen hast';

  @override
  String get actionCreateMemories => 'Erinnerungen erstellen';

  @override
  String get swipeTasksToIndent => 'Wischen Sie Aufgaben zum Einrücken, ziehen Sie zwischen Kategorien';

  @override
  String get createAccountTitle => 'Konto erstellen';

  @override
  String get modelRequired => 'Modell erforderlich';

  @override
  String get saveMemory => 'Erinnerung speichern';

  @override
  String get successfullyConnectedClickUp => 'Erfolgreich mit ClickUp verbunden!';

  @override
  String get notYetSynced => 'Noch nicht mit Ihrem Telefon synchronisiert';

  @override
  String get pendantUpToDate => 'Pendant ist aktuell';

  @override
  String get categoryProductivityTools => 'Produktivitätswerkzeuge';

  @override
  String get refresh => 'Aktualisieren';

  @override
  String get cancelSyncMessage => 'Möchtest du die Synchronisierung wirklich abbrechen?';

  @override
  String get selectImageFileTitle => 'Bilddatei auswählen';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'Fehler beim Öffnen der Dateiauswahl: $message';
  }

  @override
  String get failedToGenerateConversationLink => 'Fehler beim Generieren des Gesprächslinks';

  @override
  String get voiceFailedToTranscribe => 'Audiotranskription fehlgeschlagen';

  @override
  String get viewAll => 'Alle anzeigen';

  @override
  String get yourNewKey => 'Ihr neuer Schlüssel:';

  @override
  String get conversationMap => 'Unterhaltungskarte';

  @override
  String get contactSupportAction => 'Support kontaktieren';

  @override
  String get weekdaySun => 'So';

  @override
  String get summaryNotFound => 'Zusammenfassung nicht gefunden';

  @override
  String get shortConversationThreshold => 'Schwellenwert für kurze Unterhaltungen';

  @override
  String get dailyRecapsDescription => 'Ihre täglichen Zusammenfassungen erscheinen hier, sobald sie erstellt wurden';

  @override
  String get phoneCallsWithOmi => 'Telefonate mit Omi';

  @override
  String get addAppSelectPaymentPlan =>
      'Bitte wählen Sie einen Zahlungsplan und geben Sie einen Preis für Ihre App ein';

  @override
  String get deleteAccountFinal =>
      'Diese Aktion ist unwiderruflich und wird Ihr Konto und alle zugehörigen Daten dauerhaft löschen. Sind Sie sicher, dass Sie fortfahren möchten?';

  @override
  String get gettingAudioFiles => 'Hole Audiodateien…';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String get port => 'Port';

  @override
  String personPinnedToast(String name) {
    return '$name angeheftet';
  }

  @override
  String get wrappedConversations => 'Gespräche';

  @override
  String get availableOnMacMobileWeb => 'Verfügbar auf Mac, Mobilgerät und im Web';

  @override
  String get monthAug => 'Aug';

  @override
  String get failedToGenerateSummary =>
      'Zusammenfassung konnte nicht erstellt werden. Stellen Sie sicher, dass Sie Gespräche für diesen Tag haben.';

  @override
  String planEndedOn(String date) {
    return 'Ihr Plan endete am $date.\nAbonnieren Sie jetzt erneut - Ihnen wird sofort für einen neuen Abrechnungszeitraum berechnet.';
  }

  @override
  String get createAnApp => 'Eine App erstellen';

  @override
  String get cancelling => 'Wird gekündigt…';

  @override
  String get wrappedTopDaysHeader => 'Top-Tage';

  @override
  String get keepEditing => 'Weiter bearbeiten';

  @override
  String get ignoredVoicesEmpty => 'Keine ignorierten Stimmen';

  @override
  String get cannotBeUndone => 'Dies kann nicht rückgängig gemacht werden.';

  @override
  String get usersPayToUse => 'Benutzer zahlen für die Nutzung Ihrer App';

  @override
  String get maxFilesUploadError => 'Sie können nur 4 Dateien gleichzeitig hochladen';

  @override
  String get yourDeviceIsUpToDate => 'Ihr Gerät ist auf dem neuesten Stand';

  @override
  String get unableToFetchApps =>
      'Apps konnten nicht geladen werden :(\n\nBitte überprüfen Sie Ihre Internetverbindung und versuchen Sie es erneut.';

  @override
  String get entityCorrectionFailed => 'Deine Korrektur konnte nicht gesendet werden. Versuche es erneut.';

  @override
  String get alreadyAuthorized => 'Bereits autorisiert';

  @override
  String get speedAccuracyLower => 'Geschwindigkeit und Genauigkeit können niedriger sein als bei Cloud-Modellen.';

  @override
  String siriShortcutsSearchHint(String searchPhrase) {
    return ' Du kannst außerdem „$searchPhrase for what I did today“ sagen.';
  }

  @override
  String get unlimitedPlan => 'Unbegrenzter Plan';

  @override
  String get contactSupport => 'Support kontaktieren?';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Maximal $count Ziele erlaubt';
  }

  @override
  String get deviceStorageNearlyFull => 'Gerät fast voll — synchronisieren, um Speicher freizugeben.';

  @override
  String get setDueDate => 'Fälligkeitsdatum festlegen';

  @override
  String privateAppsCount(String count) {
    return '$count private Apps';
  }

  @override
  String get selectPeople => 'Personen auswählen';

  @override
  String get capabilityChat => 'Chat';

  @override
  String chatAppsChannelChats(String app) {
    return '$app-Chats';
  }

  @override
  String get transcribeLaterTitle => 'Später transkribieren';

  @override
  String get failedToConnectAsana => 'Verbindung zu Asana fehlgeschlagen';

  @override
  String get youAreOnUnlimitedPlan => 'Sie haben den Unlimited-Plan.';

  @override
  String get chatAppsIncludedWithPro => 'IN OMI PRO ENTHALTEN';

  @override
  String get failedToCreateKeyTryAgain => 'Schlüssel konnte nicht erstellt werden. Bitte versuchen Sie es erneut.';

  @override
  String get backgroundModeTitle => 'Hintergrundmodus';

  @override
  String get discardChangesMessage => 'Ihre nicht gespeicherten Änderungen gehen verloren.';

  @override
  String get captureSourcePendant => 'Anhänger';

  @override
  String get exportTasksWithOneTap => 'Aufgaben mit einem Tippen exportieren!';

  @override
  String get sundayAbbr => 'So';

  @override
  String get pleaseEnterAppPrompt => 'Bitte geben Sie eine Aufforderung für Ihre App ein';

  @override
  String deviceStoragePercentFull(int percent) {
    return '$percent% belegt';
  }

  @override
  String get developerSettings => 'Entwicklereinstellungen';

  @override
  String get selectYouFromList => 'Wähle dich selbst aus der Liste';

  @override
  String get deleteNow => 'Jetzt löschen';

  @override
  String get installUpdate => 'Update installieren';

  @override
  String get unpairDevice => 'Gerät entkoppeln';

  @override
  String get assistantVoice => 'Assistentenstimme';

  @override
  String get installingApp => 'App wird installiert…';

  @override
  String get wrappedFunnyMomentTitle => 'Lustiger Moment';

  @override
  String onboardingFailedCheckNotification(String error) {
    return 'Benachrichtigungsberechtigung konnte nicht überprüft werden: $error';
  }

  @override
  String get dreamReportRunNow => 'Jetzt ausführen';

  @override
  String get notSet => 'Nicht festgelegt';

  @override
  String get startVoiceRecording => 'Sprachaufnahme starten';

  @override
  String get userInformation => 'Benutzerinformationen';

  @override
  String get wrappedStruggleLabel => 'HERAUSFORDERUNG';

  @override
  String get filterInteresting => 'Einblicke';

  @override
  String captureRecordingsCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count Aufnahmen',
      one: '1 Aufnahme',
    );
    return '$_temp0';
  }

  @override
  String get addOrChangeYourPaymentMethod => 'Zahlungsmethode hinzufügen oder ändern';

  @override
  String get unableToLoadApps => 'Apps können nicht geladen werden';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'Ein neues Firmware-Update ($version) ist für Ihr Omi-Gerät verfügbar. Möchten Sie jetzt aktualisieren?';
  }

  @override
  String get cancelReasonTooExpensive => 'Zu teuer';

  @override
  String get firmwareUsbWarning => 'USB-Verbindung während Updates kann Ihr Gerät beschädigen.';

  @override
  String authAccessMessage(String appName) {
    return 'Sie müssen Omi autorisieren, auf Ihre $appName-Daten zuzugreifen. Dies öffnet Ihren Browser für die Authentifizierung.';
  }

  @override
  String get conversationEndsManually => 'Das Gespräch endet nur manuell.';

  @override
  String get partialRecording => 'Teilweise Aufnahme';

  @override
  String get dreamReportFeedback => 'An das Omi-Team gemeldet';

  @override
  String get shareAudio => 'Audio teilen';

  @override
  String get importDataFromOtherSources => 'Daten aus anderen Quellen importieren';

  @override
  String get premiumMinutesUsed => 'Premium-Minuten aufgebraucht.';

  @override
  String get phoneCallsUpgradeButton => 'Auf Unlimited upgraden';

  @override
  String get omiUnlimited => 'Omi Unbegrenzt';

  @override
  String get unknownDevice => 'Unbekannt';

  @override
  String get failedToStartImport => 'Import konnte nicht gestartet werden. Bitte versuchen Sie es erneut.';

  @override
  String get searchActionItems => 'Aufgaben durchsuchen';

  @override
  String get whisperModel => 'Whisper-Modell';

  @override
  String get searchContacts => 'Kontakte durchsuchen';

  @override
  String get selectAllSkipsPinned =>
      '„Alle auswählen“ überspringt angeheftete Personen. Lösche sie einzeln auf ihrer Seite.';

  @override
  String get speechProfileIntro => 'Omi muss Ihre Ziele und Ihre Stimme lernen. Sie können es später ändern.';

  @override
  String get realtimeListening => 'Echtzeit-Hören';

  @override
  String get appNotAvailable => 'Hoppla! Die App, die Sie suchen, ist anscheinend nicht verfügbar.';

  @override
  String get enterYourName => 'Geben Sie Ihren Namen ein';

  @override
  String get permissionTypeTrigger => 'Auslöser';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'Ihr Wissensgraph wird automatisch erstellt, wenn Sie neue Erinnerungen anlegen.';

  @override
  String get chatAppsLink => 'Link';

  @override
  String get minutes => 'Minuten';

  @override
  String get actions => 'Aktionen';

  @override
  String get connectRayBanMeta => 'Ray-Ban Meta verbinden';

  @override
  String get monthSep => 'Sep';

  @override
  String get selectContactsToShareSummary => 'Kontakte auswählen, um Ihre Gesprächszusammenfassung zu teilen';

  @override
  String get paymentNoneSelected => 'Keine Auswahl';

  @override
  String get pinAction => 'Anheften';

  @override
  String get monthOct => 'Okt';

  @override
  String get startRecording => 'Aufnahme starten';

  @override
  String get somethingWentWrong => 'Etwas ist schief gelaufen! Bitte versuchen Sie es später erneut.';

  @override
  String largeTimeGapsDetected(String gaps) {
    return 'Große Zeitlücken erkannt ($gaps)';
  }

  @override
  String get phoneEnterNumber => 'Nummer eingeben';

  @override
  String get cancelConsequenceNoAccess => 'Kein unbegrenzter Zugang mehr am Ende deines Abrechnungszeitraums.';

  @override
  String get appleHealthDeniedTitle => 'Apple Health-Zugriff verweigert';

  @override
  String deleteItemTitle(String item) {
    return '$item löschen';
  }

  @override
  String get invalidIntegrationUrl => 'Ungültige Integrations-URL';

  @override
  String get welcomeActionItemsTitle => 'Bereit für Aufgaben';

  @override
  String get updateAppConfirmation => 'Die Änderungen werden nach Überprüfung durch unser Team übernommen.';

  @override
  String get corruptedStatus => 'Beschädigt';

  @override
  String get cantRateWithoutInternet => 'Kann App ohne Internetverbindung nicht bewerten.';

  @override
  String get dontShowAgain => 'Nicht erneut anzeigen';

  @override
  String get hardwareRevision => 'Hardware-Revision';

  @override
  String get trySelectingDifferentDate => 'Versuchen Sie, ein anderes Datum auszuwählen';

  @override
  String get learnings => 'Erkenntnisse';

  @override
  String get failedToConnectTodoist => 'Verbindung zu Todoist fehlgeschlagen';

  @override
  String get accessDataProgrammatically => 'Greifen Sie programmgesteuert auf Ihre Daten zu';

  @override
  String processingProgress(int current, int total) {
    return 'Verarbeitung $current/$total';
  }

  @override
  String get apiEnvSavedRestartRequired =>
      'Gespeichert. Schließen und öffnen Sie die App erneut, um die Änderungen anzuwenden.';

  @override
  String get syncCardWaitingInternet => 'Warten auf Internet';

  @override
  String get accountCutoverOpenStore => 'Store öffnen';

  @override
  String get processedConversations => 'Verarbeitete Gespräche';

  @override
  String get holdOnPreparingForm => 'Einen Moment, wir bereiten das Formular für Sie vor';

  @override
  String get waitingForDevice => 'Warte auf Gerät…';

  @override
  String get learnMore => 'Mehr erfahren…';

  @override
  String get aiGenErrorWhileCreatingApp => 'Beim Erstellen der App ist ein Fehler aufgetreten';

  @override
  String get deleteAllFilesWarning =>
      'Dies löscht sowohl synchronisierte als auch ausstehende Aufnahmen. Ausstehende Aufnahmen wurden NICHT synchronisiert und gehen dauerhaft verloren.';

  @override
  String get usageWordsHeard => 'Words heard';

  @override
  String get importDataDescription => 'Daten aus anderen Quellen importieren';

  @override
  String get raybanMetaImageCaptureUnavailable => 'Im Nur-Audio-Modus nicht verfügbar';

  @override
  String get appRejectedMessage =>
      'Ihre App wurde abgelehnt. Bitte aktualisieren Sie die App-Details und reichen Sie sie erneut ein.';

  @override
  String get capturePendantDisconnectedShort => 'Omi verbindet sich von selbst neu';

  @override
  String get improveSpeechProfileDesc =>
      'Wir verwenden Aufnahmen, um Ihr persönliches Sprachprofil weiter zu trainieren und zu verbessern.';

  @override
  String get voiceResponseModeTitle => 'Wann Antworten vorgelesen werden';

  @override
  String get failedToDeleteItem => 'Löschen der Aufgabe fehlgeschlagen';

  @override
  String get firmware => 'Firmware';

  @override
  String failedToAddToService(String serviceName) {
    return 'Fehler beim Hinzufügen zu $serviceName';
  }

  @override
  String get askOmiAnything => 'Fragen Sie Omi alles über Ihr Leben';

  @override
  String get integrationsFooter => 'Verbinden Sie Ihre Apps, um Daten und Metriken im Chat anzuzeigen.';

  @override
  String get loading => 'Laden…';

  @override
  String get showLess => 'weniger anzeigen ↑';

  @override
  String get chatAppsNeverMessagesOthers => 'Schreibt nie in deinem Namen anderen Leuten';

  @override
  String get scopeUserName => 'Benutzername';

  @override
  String get mute => 'Stumm';

  @override
  String get serverProcessesAudio => 'Der Server verarbeitet die Audiodateien und erstellt Erinnerungen';

  @override
  String mergeConversationsSuccessBody(int count) {
    return '$count Gespräche wurden erfolgreich zusammengeführt';
  }

  @override
  String get pairingSuccessful => 'Kopplung erfolgreich';

  @override
  String get websocketUrl => 'WebSocket-URL';

  @override
  String get wrappedFriend => 'Freund';

  @override
  String get frequencyHigh => 'Hoch';

  @override
  String get processingFailed => 'Verarbeitung fehlgeschlagen';

  @override
  String get dataLowercase => 'Daten';

  @override
  String deviceOfflineWakeHint(String deviceName) {
    return '$deviceName ist offline. Drücke die Taste, um es aufzuwecken, und versuche es erneut.';
  }

  @override
  String get updatedConversations => 'Aktualisierte Gespräche';

  @override
  String get phoneGetStarted => 'Loslegen';

  @override
  String get recordingDetails => 'Aufnahmedetails';

  @override
  String get createApiKey => 'API-Schlüssel erstellen';

  @override
  String get anyoneWithLinkCanView => 'Jeder mit dem Link kann ansehen';

  @override
  String get noPendingTasks => 'Keine offenen Aufgaben';

  @override
  String get featureComingSoon => 'Diese Funktion kommt bald!';

  @override
  String get bluetoothMethodDescription =>
      'Verwendet Standard-Bluetooth-Low-Energy-Verbindung. Langsamer, beeinträchtigt aber nicht Ihre WLAN-Verbindung.';

  @override
  String get chatAppsNotConnectedTitle => 'Nicht verbunden';

  @override
  String get wrappedMostIntenseDay => 'Am intensivsten';

  @override
  String get yesterday => 'Gestern';

  @override
  String get requestConfiguration => 'Anfragekonfiguration';

  @override
  String get timeAM => 'AM';

  @override
  String autoRemoveSyncedCopiesDescription(int days) {
    return 'Löscht lokale Kopien $days Tage nach der Synchronisierung. Cloud-Kopien bleiben erhalten.';
  }

  @override
  String get chatAppsTelegramPrivacyNote =>
      'Deine Chats mit Omi werden auch von Telegram gespeichert. Omi antwortet nur dir, nie anderen Leuten, und du kannst die Verbindung jederzeit trennen.';

  @override
  String speakerWithId(String speakerId) {
    return 'Sprecher $speakerId';
  }

  @override
  String get reviewNoDate => 'Keine';

  @override
  String get transcript => 'Transkript';

  @override
  String get deviceDiagnosticsUploadFailed => 'Diagnosedaten konnten nicht gesendet werden. Bitte erneut versuchen.';

  @override
  String get noFoldersAvailable => 'Keine Ordner verfügbar';

  @override
  String get addAppSelectCategory => 'Bitte wählen Sie eine Kategorie für Ihre App aus';

  @override
  String get conversations => 'Gespräche';

  @override
  String get upgradeToUnlimited => 'Auf unbegrenzt upgraden';

  @override
  String get deleteFlowConfirmTitle => 'Konto löschen?';

  @override
  String get accountCutoverMigrationInProgressMessage =>
      'Dein Konto wird migriert. Produktfunktionen sind pausiert, bis die Migration abgeschlossen ist.';

  @override
  String get permissionAllowed => 'Erlaubt';

  @override
  String get pressDoneToSave => 'Drücken Sie Fertig zum Speichern';

  @override
  String get listening => 'Zuhören';

  @override
  String get audioReady => 'Audio bereit';

  @override
  String get freeForEveryone => 'Kostenlos für alle';

  @override
  String get buildingKnowledgeGraphFromMemories => 'Wissensgraph wird aus Erinnerungen erstellt…';

  @override
  String get onDeviceTranscription => 'Transkription auf dem Gerät';

  @override
  String errorWithMessage(String error) {
    return 'Fehler: $error';
  }

  @override
  String get chatAppsProblemOffline => 'Du bist offline. Prüfe deine Verbindung und versuche es erneut.';

  @override
  String get callAlreadyInProgress => 'Ein Anruf ist bereits aktiv';

  @override
  String get reviewQuestionSpelling => 'Wie wird das geschrieben?';

  @override
  String get firmwareStableConnection => 'Stabile Verbindung';

  @override
  String get categoryOther => 'Sonstiges';

  @override
  String get perMonthLabel => '/ Monat';

  @override
  String get onboardingYoureAllSet => 'Du bist startklar';

  @override
  String get resumeRecording => 'Aufnahme fortsetzen';

  @override
  String get feedbackSubtitleAudioQuality => 'Wir würden gerne verstehen, was schiefgelaufen ist.';

  @override
  String get speakerTagPromptPlayClip => 'Clip abspielen';

  @override
  String get anonymityAndPrivacy => 'Anonymität und Datenschutz';

  @override
  String get noMemoriesToDelete => 'Keine Erinnerungen zum Löschen';

  @override
  String get syncStepProcess => 'Transkribieren';

  @override
  String get callStateRinging => 'Klingelt…';

  @override
  String get setupOnDevice => 'On-device einrichten';

  @override
  String get creatorPayouts => 'Auszahlungen für Entwickler';

  @override
  String get olderDeviceDetected => 'Älteres Gerät erkannt';

  @override
  String get deletePhoneNumberWarning => 'Sie muessen erneut verifizieren, um Anrufe zu taetigen';

  @override
  String get appVisibilityChangedSuccessfully =>
      'App-Sichtbarkeit erfolgreich geändert. Es kann einige Minuten dauern, bis die Änderung wirksam wird.';

  @override
  String get failedToCreateActionItem => 'Aufgabe konnte nicht erstellt werden';

  @override
  String get msgSelectFilesGenericError => 'Fehler beim Auswählen von Dateien. Bitte versuchen Sie es erneut.';

  @override
  String get pendantRecordingSyncBlocked =>
      'Dein Pendant nimmt noch auf, daher kann das gespeicherte Audio nicht übertragen werden. Drücke die Taste am Pendant, um die Aufnahme zu stoppen, und synchronisiere dann erneut.';

  @override
  String get failedToStartMerge => 'Zusammenführung konnte nicht gestartet werden';

  @override
  String get shortcutChangeInstruction =>
      'Klicken Sie auf eine Tastenkombination, um sie zu ändern. Drücken Sie Escape, um abzubrechen.';

  @override
  String get notificationsAndDisplay => 'Benachrichtigungen & Anzeige';

  @override
  String get getPaidThroughStripe => 'Erhalten Sie Zahlungen für Ihre App-Verkäufe über Stripe';

  @override
  String get weekdayWed => 'Mi';

  @override
  String get send => 'Senden';

  @override
  String get nativeEngineNoDownload =>
      'Die native Sprach-Engine Ihres Geräts wird verwendet. Kein Modell-Download erforderlich.';

  @override
  String get wrappedActions => 'Aktionen';

  @override
  String get conversationTimeoutConfig => 'Wie lange Omi bei Stille wartet, bevor ein Gespräch endet';

  @override
  String get mic => 'Mikrofon';

  @override
  String deviceOnboardingVoiceReplyStatusAlwaysHeadphones(String device) {
    return 'Spielt bis $device.';
  }

  @override
  String failedToSendReply(String error) {
    return 'Antwort konnte nicht gesendet werden: $error';
  }

  @override
  String get whisperModelSizeTiny => 'Winzig';

  @override
  String get speakerTagPromptNotMeAction => 'Nicht ich';

  @override
  String get setupInstructions => 'Einrichtungsanweisungen';

  @override
  String get noLanguagesFound => 'Keine Sprachen gefunden';

  @override
  String get experimental => 'Experimentell';

  @override
  String get continueRecording => 'Aufnahme fortsetzen';

  @override
  String get selectDefaultRepoDesc =>
      'Wählen Sie ein Standard-Repository für das Erstellen von Issues. Sie können beim Erstellen von Issues immer noch ein anderes Repository angeben.';

  @override
  String sharedTasksTitle(String name, int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count Aufgaben geteilt',
      one: '1 Aufgabe geteilt',
    );
    return '$name hat $_temp0';
  }

  @override
  String get permissionsRequiredDesc =>
      'Diese App benötigt Bluetooth- und Standortberechtigungen, um ordnungsgemäß zu funktionieren. Bitte aktivieren Sie diese in den Einstellungen.';

  @override
  String diagnosticsVerdictReconnectsDetail(String duration) {
    return 'Kurze Abbrüche, jedes Mal nach etwa $duration wieder da';
  }

  @override
  String get transferring => 'Übertragung…';

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '$used von $limit Wörtern diesen Monat genutzt';
  }

  @override
  String get noChatAppsEnabled =>
      'Keine Chat-Apps aktiviert.\nTippen Sie auf \"Apps aktivieren\" um welche hinzuzufügen.';

  @override
  String get tipKeepPhoneNearby => 'Halten Sie Ihr Telefon in der Nähe für schnellere Synchronisierung';

  @override
  String get authFailedToSignInWithGoogle => 'Anmeldung mit Google fehlgeschlagen, bitte versuchen Sie es erneut.';

  @override
  String get frequencyDescLow => 'Nur Wichtiges, etwa 3–5 pro Tag';

  @override
  String get availableTemplates => 'Verfügbare Vorlagen';

  @override
  String get captureEveryMoment => 'Omi zeichnet deine Gespräche auf und schreibt\ndir die Zusammenfassung und To-dos.';

  @override
  String get migrationErrorOccurred => 'Ein Fehler ist während der Migration aufgetreten. Bitte versuche es erneut.';

  @override
  String get wrappedCompletedLabel => 'Abgeschlossen';

  @override
  String speakerTagPromptLabeledToast(String name) {
    return 'Als $name zugeordnet';
  }

  @override
  String get docs => 'Dokumentation';

  @override
  String get dateTimeLabel => 'Datum & Uhrzeit';

  @override
  String get editFolder => 'Ordner bearbeiten';

  @override
  String get apps => 'Apps';

  @override
  String segmentsSingular(String count) {
    return '$count Segment';
  }

  @override
  String get deviceSettings => 'Geräteeinstellungen';

  @override
  String get offline => 'Offline';

  @override
  String get createActionItemTooltip => 'Neue Aufgabe erstellen';

  @override
  String get forgetDevice => 'Gerät vergessen';

  @override
  String get reviewEntryTitle => 'Fragen an dich';

  @override
  String get enterEmailError => 'Bitte geben Sie Ihre E-Mail ein';

  @override
  String get appDisabledOwnerHint =>
      'Behebe zuerst den Endpunkt – beim Reaktivieren wird jede konfigurierte URL erneut geprüft.';

  @override
  String get chatAppsIMessageSubtitle => 'Schreib Omi von deiner Telefonnummer';

  @override
  String get tasksExportedOneApp => 'Aufgaben können jeweils nur in eine App exportiert werden.';

  @override
  String transcriptSpeakerCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count Sprecher',
      one: '1 Sprecher',
    );
    return '$_temp0';
  }

  @override
  String get saveGoal => 'Speichern';

  @override
  String get noBatteryDataYet => 'Noch keine Batteriedaten';

  @override
  String chatUsedOfLimitMessages(String used, String limit) {
    return '$used von $limit Nachrichten diesen Monat verwendet';
  }

  @override
  String get backgroundActivityDesc =>
      'Damit Omi weiter aufnimmt, wenn der Bildschirm aus ist oder du die App wechselst.';

  @override
  String get addAppUpdateFailed => 'App-Aktualisierung fehlgeschlagen. Bitte versuchen Sie es später erneut';

  @override
  String get noMatchingPeople => 'Keine passenden Personen';

  @override
  String get unlinkCalendarEvent => 'Termin-Verknüpfung aufheben';

  @override
  String get regenerateRecap => 'Zusammenfassung neu erstellen';

  @override
  String get deleteSynced => 'Synchronisierte löschen';

  @override
  String get speakerTagPromptNameHint => 'Name der Person';

  @override
  String get freePlan => 'Kostenloser Plan';

  @override
  String get installs => 'INSTALLATIONEN';

  @override
  String get publicLabel => 'Öffentlich';

  @override
  String get deletingMessages => 'Ihre Nachrichten werden aus Omis Speicher gelöscht…';

  @override
  String get pendingFilesDeleted => 'Ausstehende Aufnahmen gelöscht';

  @override
  String get checkUsage => 'Nutzung prüfen';

  @override
  String get addWordsDesc => 'Namen, Begriffe oder ungewöhnliche Wörter';

  @override
  String get entityCorrectionSaved => 'Danke. Omi korrigiert das.';

  @override
  String get categoryEducation => 'Bildung';

  @override
  String get planAndUsage => 'Abonnement & Nutzung';

  @override
  String get deleteMemory => 'Erinnerung löschen';

  @override
  String get dataProtectionLevel => 'Datenschutzniveau';

  @override
  String timeDaySingular(int count) {
    return '$count Tag';
  }

  @override
  String get keyCreated => 'Schlüssel erstellt';

  @override
  String get date => 'Datum';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return 'Migration von $itemType… $percentage%';
  }

  @override
  String get enableLocalStorage => 'Lokalen Speicher aktivieren';

  @override
  String get omiSays => 'Omi says';

  @override
  String get appDetails => 'App-Details';

  @override
  String get loadingYourRecording => 'Aufnahme wird geladen…';

  @override
  String get deleteAllLimitlessWarning =>
      'Alle aus Limitless importierten Gespräche werden gelöscht. Dies kann nicht rückgängig gemacht werden.';

  @override
  String get combiningAudioFiles => 'Kombiniere Audiodateien…';

  @override
  String get suggestFollowUpQuestion => 'Folgefrage vorschlagen';

  @override
  String chatStarterPrompt(String kind) {
    String _temp0 = intl.Intl.selectLogic(
      kind,
      {
        'capabilities': 'Was kannst du für mich tun?',
        'goal': 'Hilf mir, ein Ziel zu setzen',
        'activity': 'Fasse meine letzten Aktivitäten zusammen',
        'improve': 'Wie kann ich mich verbessern?',
        'other': '',
      },
    );
    return '$_temp0';
  }

  @override
  String get speakerTagPromptIgnoredNote => 'Omi fragt nicht mehr nach dieser Stimme';

  @override
  String get recordWithPhoneInstead => 'Stattdessen mit Telefon aufnehmen';

  @override
  String get triggerEvent => 'Auslöseereignis';

  @override
  String get waitingForTranscriptOrPhotos => 'Warte auf Transkript oder Fotos…';

  @override
  String get omiApiKeys => 'Omi API-Schlüssel';

  @override
  String addNamedPersonAction(String name) {
    return '„$name“ hinzufügen';
  }

  @override
  String get enableDetailedDiagnosticMessages => 'Detaillierte Diagnosemeldungen vom Transkriptionsdienst aktivieren';

  @override
  String get nameCannotBeEmpty => 'Name darf nicht leer sein';

  @override
  String get noTasksYet => 'Noch keine Aufgaben';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'Versuchen Sie, Ihre Suchbegriffe oder Filter anzupassen';

  @override
  String daySummaryForDate(String date) {
    return 'Tageszusammenfassung · $date';
  }

  @override
  String get statusTimedOut => 'Zeit abgelaufen';

  @override
  String chatUsageDescription(String used, String limitDisplay, String plan) {
    return 'Sie haben $used von $limitDisplay im $plan-Plan verwendet.';
  }

  @override
  String get paypalMeLink => 'PayPal.me-Link';

  @override
  String get allMemoriesPrivateResult => 'Alle Erinnerungen sind jetzt privat';

  @override
  String get scanAgain => 'Erneut suchen';

  @override
  String get doItAgain => 'Erneut machen';

  @override
  String get reviewTitle => 'Überprüfen';

  @override
  String get photos => 'Fotos';

  @override
  String get phoneNoVerifiedNumbersMessage => 'Bestätige deine Nummer, um über Omi zu telefonieren.';

  @override
  String get save => 'Speichern';

  @override
  String get deleteAccount => 'Konto Löschen';

  @override
  String get managePaymentMethod => 'Zahlungsmethode verwalten';

  @override
  String get selectThumbnailImageTitle => 'Vorschaubild auswählen';

  @override
  String get pairingTitleOmi => 'Omi einschalten';

  @override
  String get whatsYourPrimaryLanguage => 'Was ist Ihre primäre Sprache?';

  @override
  String get replyToReview => 'Auf Bewertung antworten';

  @override
  String failedToDeleteError(String error) {
    return 'Löschen fehlgeschlagen: $error';
  }

  @override
  String get newestFirst => 'Neueste zuerst';

  @override
  String get wrappedCreatingYourStory => 'Erstelle deine\n2025 Geschichte…';

  @override
  String get chatAppsPrivateMemories => 'Private Erinnerungen in der App behalten';

  @override
  String get pleaseEnterPayPalEmail => 'Bitte geben Sie Ihre PayPal-E-Mail ein';

  @override
  String get transcription => 'Transkription';

  @override
  String get yourReview => 'Ihre Bewertung';

  @override
  String get filesDownloadedUploadedNextTime =>
      'Bereits heruntergeladene Dateien werden beim nächsten Mal hochgeladen.';

  @override
  String get phoneSetupStep3Subtitle => 'Mit integrierter Live-Transkription';

  @override
  String get mcpConnectionFailed => 'Verbindung zum MCP-Server fehlgeschlagen';

  @override
  String get chatAppsConnectTelegramTitle => 'Telegram verbinden';

  @override
  String get createMemoryTooltip => 'Neue Erinnerung erstellen';

  @override
  String get connectDeviceMessage =>
      'Verbinden Sie Ihr Omi-Gerät, um auf Geräteeinstellungen und Anpassungen zuzugreifen';

  @override
  String get authorizingMcpServer => 'Autorisierung…';

  @override
  String charactersCount(int count) {
    return '$count Zeichen';
  }

  @override
  String get syncStatusUploaded => 'Hochgeladen · wird auf Omi verarbeitet';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'Bitte authentifizieren Sie sich mit $serviceName unter Einstellungen > Aufgabenintegrationen';
  }

  @override
  String get setDefaultButton => 'Als Standard festlegen';

  @override
  String get resummarizingConversation => 'Unterhaltung wird erneut zusammengefasst…\nDies kann einige Sekunden dauern';

  @override
  String estimatedHours(int count) {
    return '~$count Stunde(n)';
  }

  @override
  String get chatAppsInsightsSubtitle => 'Lass Omi dir hier eine Zusammenfassung oder einen Einblick senden.';

  @override
  String get memoryAllowUse => 'Verwendung erlauben';

  @override
  String get model => 'Modell';

  @override
  String get memoryGraphTitle => 'Erinnerungsgraph';

  @override
  String get endpointURL => 'Endpunkt-URL';

  @override
  String get wrappedShareYourWrapped => 'Teile deinen Wrapped';

  @override
  String get micGainDescBoosted => 'Verstärkt - für ruhige Umgebungen';

  @override
  String get wrappedMinutes => 'Minuten';

  @override
  String get language => 'Sprache';

  @override
  String downloadErrorWithMessage(String error) {
    return 'Download-Fehler: $error';
  }

  @override
  String get onboardingRatingPromptNo => 'Nein';

  @override
  String get whatWouldYouLikeToRemember => 'Woran möchten Sie sich erinnern?';

  @override
  String get deviceOnboardingMuteUnmuteDesc => 'Mikrofon ein- oder ausschalten';

  @override
  String secondsCount(int count) {
    return '$count Sekunden';
  }

  @override
  String get icon => 'Symbol';

  @override
  String get realTimeTranscript => 'Echtzeit-Transkript';

  @override
  String get deviceOnboardingVoiceReplySample => 'Alles klar. Dein nächstes Meeting beginnt in zwanzig Minuten.';

  @override
  String get noDisconnectsRecorded => 'Keine Trennungen aufgezeichnet';

  @override
  String get filterMyApps => 'Meine Apps';

  @override
  String get recapRegenerateCooldown => 'Bitte warte ein paar Sekunden, bevor du erneut generierst.';

  @override
  String get templateName => 'Vorlagenname';

  @override
  String get retry => 'Erneut versuchen';

  @override
  String get sdCardSyncDescription =>
      'SD-Karten-Synchronisierung importiert Ihre Erinnerungen von der SD-Karte in die App';

  @override
  String get deviceTutorial => 'So verwendest du Omi';

  @override
  String get noApiKeysCreateOne => 'Keine API-Schlüssel. Erstellen Sie einen, um zu beginnen.';

  @override
  String siriShortcutsSetupHint(String askPhrase, String questionPhrase) {
    return 'Aktiviere Omi unter Kurzbefehle → Siri. Sage „$askPhrase“ oder „$questionPhrase“ und stelle dann deine Frage.';
  }

  @override
  String get failedToDeleteSomeItems => 'Löschen einiger Elemente fehlgeschlagen';

  @override
  String get raybanMetaSetupDescription =>
      'Verwenden Sie Ihre Ray-Ban Meta Brille als Omi-Aufnahmegerät für Gespräche und visuellen Kontext. Omi öffnet die Meta AI App, um Ihre Brille zu verknüpfen.';

  @override
  String get tabToDo => 'Zu erledigen';

  @override
  String get otaWifiFailed => 'WLAN-Verbindung fehlgeschlagen. Prüfe Netzwerkname und Passwort.';

  @override
  String get changePlan => 'Plan ändern';

  @override
  String copiedToClipboard(String title) {
    return '$title in Zwischenablage kopiert';
  }

  @override
  String get completeAuthBrowser =>
      'Bitte schließen Sie die Authentifizierung in Ihrem Browser ab. Kehren Sie danach zur App zurück.';

  @override
  String get migrationInProgressMessage =>
      'Migration läuft. Sie können das Schutzniveau nicht ändern, bis sie abgeschlossen ist.';

  @override
  String get keepSubscription => 'Abo behalten';

  @override
  String get playbackPreparingAudio => 'Audio wird vorbereitet…';

  @override
  String get cloudStorageDialogMessage =>
      'Ihre Echtzeit-Aufnahmen werden während des Sprechens in einem privaten Cloud-Speicher gespeichert.';

  @override
  String get newChat => 'Neuer Chat';

  @override
  String get paymentEnterAmountGreaterThanZero => 'Bitte geben Sie einen Betrag größer als 0 ein';

  @override
  String showAllPeople(int count) {
    return 'Alle $count Personen anzeigen';
  }

  @override
  String deletePersonNamedTitle(String name) {
    return '$name löschen?';
  }

  @override
  String get importTranscriptFiles => 'Transkriptdateien';

  @override
  String get transcriptPlaceholder => 'Transkription erscheint hier…';

  @override
  String get logShared => 'Protokoll geteilt';

  @override
  String get deleteReasonNotUsing => 'Ich nutze es nicht oft genug';

  @override
  String diagnosticsDropsPerHour(int count) {
    return 'etwa $count pro Stunde';
  }

  @override
  String get wrappedProcessingDefault => 'Verarbeitung…';

  @override
  String get failedToConnectGoogleTasksRetry =>
      'Verbindung zu Google Tasks fehlgeschlagen. Bitte versuchen Sie es erneut.';

  @override
  String get downloadingFromSdCard => 'Wird von SD-Karte heruntergeladen';

  @override
  String get firmwareFormatWarning =>
      'Diese Firmware wird die SD-Karte formatieren. Bitte stellen Sie sicher, dass alle Offline-Daten vor dem Upgrade synchronisiert sind.\n\nWenn Sie nach der Installation dieser Version ein blinkendes rotes Licht sehen, machen Sie sich keine Sorgen. Verbinden Sie das Gerät einfach mit der App und es sollte blau werden. Das rote Licht bedeutet, dass die Uhr des Geräts noch nicht synchronisiert wurde.';

  @override
  String get pleaseProvidePrompt => 'Bitte geben Sie eine Eingabeaufforderung an';

  @override
  String get voiceResponseAlways => 'Immer';

  @override
  String get statusLabel => 'Status';

  @override
  String get shareLogs => 'Protokolle teilen';

  @override
  String get continueAnyway => 'Fortfahren';

  @override
  String get transferCompleteMessage => 'Übertragung abgeschlossen! Du kannst diese Aufnahme jetzt abspielen.';

  @override
  String get reviewCaughtUpBody => 'Omi fragt hier nur, wenn es dich braucht.';

  @override
  String get calculatingETA => 'Berechne…';

  @override
  String get speechProfileTopicWork => 'Was machst du beruflich?';

  @override
  String get considerOmiCloud => 'Erwägen Sie die Verwendung von Omi Cloud für bessere Leistung.';

  @override
  String get testConversationPrompt => 'Konversations-Prompt testen';

  @override
  String get deletePending => 'Ausstehende löschen';

  @override
  String get renameConversation => 'Umbenennen';

  @override
  String get batteryDrainSignificantly => 'Der Batterieverbrauch wird deutlich steigen.';

  @override
  String get clear => 'Löschen';

  @override
  String get addAppEnterWebhookUrl => 'Bitte geben Sie eine Webhook-URL für Ihre App ein';

  @override
  String get active => 'Aktiv';

  @override
  String get exportStartedMessage => 'Export gestartet. Dies kann einige Sekunden dauern…';

  @override
  String get dataAccessNoticeDescription =>
      'Diese App wird auf Ihre Daten zugreifen. Omi AI ist nicht verantwortlich für die Verwendung, Änderung oder Löschung Ihrer Daten durch diese App';

  @override
  String get yourRequestUnderReview => 'Deine Anfrage wird geprüft';

  @override
  String get unresolvedSpeakersMessage =>
      'Omi konnte die anderen Stimmen aufnahmeübergreifend nicht unterscheiden. Tippe auf eine Sprecher-Bezeichnung, um zu benennen, wer spricht.';

  @override
  String downloadError(String error) {
    return 'Download-Fehler: $error';
  }

  @override
  String get offlineSync => 'Offline-Synchronisierung';

  @override
  String get cancelSubscription => 'Abonnement kündigen';

  @override
  String get claudeDesktopConnectorSetup =>
      'Fügen Sie auf Claude Desktop → Settings → Connectors einen benutzerdefinierten Konnektor hinzu und fügen Sie die Server-URL ein. Wenn Claude nach einer erweiterten OAuth-Client-ID fragt, verwenden Sie den untenstehenden Wert und lassen Sie das Secret leer — verwenden Sie niemals Ihren MCP-API-Schlüssel als OAuth-Secret.';

  @override
  String get chatAppsTelegramWaiting => 'Warte darauf, dass du in Telegram auf „Starten“ tippst …';

  @override
  String get tryAgain => 'Erneut versuchen';

  @override
  String get syncStatusOnDevice => 'Auf deinem Gerät';

  @override
  String get entityCorrectionTitle => 'Was stimmt nicht?';

  @override
  String peopleDeletedToast(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count Personen gelöscht',
      one: '1 Person gelöscht',
    );
    return '$_temp0';
  }

  @override
  String get features => 'Funktionen';

  @override
  String get startEarning => 'Beginnen Sie zu verdienen! 💰';

  @override
  String get enterYourNumber => 'Geben Sie Ihre Nummer ein';

  @override
  String get addToClaudeCodeConfig => 'Zu ~/.claude.json hinzufügen';

  @override
  String get cleanDisconnect => 'Saubere Trennung';

  @override
  String get grantContactsAccess => 'Zugriff auf Ihre Kontakte gewaehren';

  @override
  String get feedbackReasonIncorrect => 'Falsch oder erfunden';

  @override
  String get addAppErrorSelectingImageRetry => 'Fehler bei der Bildauswahl. Bitte versuchen Sie es erneut.';

  @override
  String get feedbackTitleNotUsing => 'Was würde dich dazu bringen, Omi mehr zu nutzen?';

  @override
  String get memories => 'Erinnerungen';

  @override
  String get capturingPhotos => 'Fotos werden aufgenommen';

  @override
  String get hideApiKey => 'API-Schlüssel ausblenden';

  @override
  String get signUpButton => 'Registrieren';

  @override
  String get tuesdayAbbr => 'Di';

  @override
  String get noApiKeys => 'Noch keine API-Schlüssel';

  @override
  String get keyWord => 'Schlüssel';

  @override
  String reviewAnswersConversations(int count) {
    return 'Diese Antwort kennzeichnet $count Gespräche';
  }

  @override
  String get statusFailed => 'Fehlgeschlagen';

  @override
  String get installedApps => 'Installierte Apps';

  @override
  String get flashFirmware => 'Firmware flashen';

  @override
  String get conversationUrlCouldNotBeGenerated => 'Gesprächs-URL konnte nicht generiert werden.';

  @override
  String get reloadingApps => 'Apps werden neu geladen…';

  @override
  String get goalTitle => 'Zieltitel';

  @override
  String get importantConversationTitle => 'Wichtiges Gespräch';

  @override
  String get byContinuingAgree => 'Wenn Sie fortfahren, stimmen Sie unseren ';

  @override
  String get saturdayAbbr => 'Sa';

  @override
  String get subscriptionReactivatedDefault => 'Dein Abonnement wurde reaktiviert.';

  @override
  String get tryLatestExperimentalFeatures => 'Probieren Sie die neuesten experimentellen Funktionen vom Omi-Team aus.';

  @override
  String get chatAppsEntrySubtitle => 'Sprich mit Omi in den Apps, die du jeden Tag nutzt.';

  @override
  String get transcriptionPaused => 'Aufnahme läuft, verbinde neu';

  @override
  String get appleHealthFeatureReadOnlyTitle => 'Nur Lesezugriff';

  @override
  String get shareDataForTraining => 'Daten für das Training teilen';

  @override
  String get noNotificationScopesAvailable => 'Keine Benachrichtigungsbereiche verfügbar';

  @override
  String disconnectFromApp(String appName) {
    return 'Von $appName trennen?';
  }

  @override
  String get failedToConnectGoogleTasks => 'Verbindung zu Google Tasks fehlgeschlagen';

  @override
  String get copyToClipboard => 'In Zwischenablage kopieren';

  @override
  String get stopRecordingConfirmation => 'Aufnahme beenden und das Gespräch jetzt zusammenfassen?';

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'Zusammenfassung konnte nicht erstellt werden. Stellen Sie sicher, dass Sie Gespräche für diesen Tag haben.';

  @override
  String get monthlyLimitReached => 'Sie haben Ihr monatliches Limit erreicht.';

  @override
  String get permissionsPageDescription =>
      'Omi nutzt diese Berechtigungen, um sich mit deinem Gerät zu verbinden, Audio aufzunehmen, im Hintergrund zu laufen, Erinnerungen zu senden und festzuhalten, wo Gespräche stattgefunden haben.';

  @override
  String get onboardingTellUsAboutYourself => 'Erzähl uns von dir';

  @override
  String get deviceOnboardingAskQuestionSubtitle =>
      'Drücke einmal die Taste, stelle deine Frage und drücke erneut, wenn du fertig bist';

  @override
  String get filters => 'Filter';

  @override
  String get firmwareUpdateWarning =>
      'Schließen Sie die App nicht und schalten Sie das Gerät nicht aus. Dies könnte Ihr Gerät beschädigen.';

  @override
  String get oneSourceAtATime => 'Omi nimmt immer nur aus einer Quelle auf.';

  @override
  String chatAppsConnectedAs(String handle) {
    return 'Verbunden als $handle';
  }

  @override
  String get pilotFeatures => 'Pilotfunktionen';

  @override
  String get selectFirmwareZip => 'Firmware-ZIP-Datei auswählen';

  @override
  String get feedbackReasonRecordingPoorTranscription => 'Schlechte Transkription';

  @override
  String get deleteAccountFailed => 'Dein Konto konnte nicht gelöscht werden. Bitte versuche es erneut.';

  @override
  String get searchConversations => 'Konversationen durchsuchen';

  @override
  String get frequencyBalanced => 'Ausgewogen';

  @override
  String get auto => 'Automatisch';

  @override
  String get actionItemUpdatedSuccessfully => 'Aufgabe erfolgreich aktualisiert';

  @override
  String get entityProjects => 'Projekte';

  @override
  String get signInWithApple => 'Mit Apple anmelden';

  @override
  String get backendUrlLabel => 'Backend-URL';

  @override
  String confidenceSummaryLikely(String name) {
    return 'Omi erkennt die Stimme von $name meist, aber du hast sie erst wenige Male bestätigt.';
  }

  @override
  String get entityOpenThreads => 'Offene Themen';

  @override
  String get deleteActionItemMessage => 'Diese Aufgabe löschen?';

  @override
  String chatWithApp(String appName) {
    return 'Mit $appName chatten';
  }

  @override
  String get editActionItem => 'Aufgabe bearbeiten';

  @override
  String get cloudStorageEnabled => 'Cloud-Speicher aktiviert';

  @override
  String get wrappedPersonalGrowth => 'Persönliches Wachstum';

  @override
  String get chatAppsProPerkSave => 'Speichere Erinnerungen und verwalte Aufgaben direkt im Chat';

  @override
  String get alreadyHaveAccountLogin => 'Haben Sie bereits ein Konto? Anmelden';

  @override
  String makeItemPublicQuestion(String item) {
    return '$item öffentlich machen?';
  }

  @override
  String get usagePeakHour => 'Peak hour';

  @override
  String get addWords => 'Wörter hinzufügen';

  @override
  String get usageNow => 'now';

  @override
  String get usageMinutes => 'Minuten';

  @override
  String availableSpace(String space) {
    return 'Verfügbarer Speicher: $space';
  }

  @override
  String get providingSubtitle => 'Aufgaben und Notizen, automatisch erfasst.';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% Abschlussrate';
  }

  @override
  String summaryGeneratedFor(String date) {
    return 'Zusammenfassung erstellt für $date';
  }

  @override
  String get selectCategory => 'Kategorie auswählen';

  @override
  String nProcessed(int count) {
    return '$count verarbeitet';
  }

  @override
  String get privacyPolicyTitle => 'Datenschutzrichtlinie';

  @override
  String get deviceMayWarmUp => 'Das Gerät kann sich bei längerer Nutzung erwärmen.';

  @override
  String get designingApp => 'Designe App';

  @override
  String get couldNotLoadWhatsNew => 'Neuigkeiten konnten nicht geladen werden';

  @override
  String get doNotCloseApp => 'Bitte schließen Sie die App nicht.';

  @override
  String get voiceResponseAudio => 'Omis Antwort laut vorlesen';

  @override
  String get allTime => 'Gesamte Zeit';

  @override
  String get developerSettingsTitle => 'Entwicklereinstellungen';

  @override
  String get restoreAction => 'Wiederherstellen';

  @override
  String get phoneSetupStep3Title => 'Beginnen Sie Ihre Kontakte anzurufen';

  @override
  String get anErrorOccurredTryAgain => 'Ein Fehler ist aufgetreten. Bitte versuchen Sie es erneut.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'Hier ist, worüber wir gerade gesprochen haben: $link';
  }

  @override
  String get playbackAudioLoadFailed => 'Audio konnte nicht geladen werden';

  @override
  String get phoneMute => 'Stumm';

  @override
  String get captureNotTranscribing => 'Kein Transkript';

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return 'Aufnahme gestoppt: $reason. Möglicherweise müssen Sie externe Bildschirme erneut anschließen oder die Aufnahme neu starten.';
  }

  @override
  String get sttProviderDeepgram => 'Deepgram';

  @override
  String get spaceKey => 'Leertaste';

  @override
  String get raybanMetaOpenMetaAI => 'Über Meta AI verbinden';

  @override
  String get linkEvent => 'Termin verknüpfen';

  @override
  String get fairUse3Day => '3-Tage-Zeitraum';

  @override
  String failedToStartAppAuth(String appName) {
    return 'Authentifizierung für $appName konnte nicht gestartet werden';
  }

  @override
  String get processingOnServer => 'Verarbeitung auf dem Server…';

  @override
  String errorStartingRecording(String error) {
    return 'Fehler beim Starten der Aufnahme: $error';
  }

  @override
  String get quiet => 'Leise';

  @override
  String get startConversationToSeeInsights =>
      'Starten Sie eine Unterhaltung mit Omi,\num hier Ihre Nutzungserkenntnisse zu sehen.';

  @override
  String get processAudio => 'Audio verarbeiten';

  @override
  String get chatAppsConnectIMessageTitle => 'Schreib Omi zum Verbinden';

  @override
  String get chatWithOmi => 'Chat mit Omi';

  @override
  String get clickToBeginRecording => 'Klicken Sie, um die Aufnahme zu starten';

  @override
  String get confirmAndProceed => 'Bestätigen und fortfahren';

  @override
  String get mondayAbbr => 'Mo';

  @override
  String sdCardProcessingMessage(int count) {
    return '$count Aufnahme(n) werden verarbeitet. Die Dateien werden danach von der SD-Karte entfernt.';
  }

  @override
  String get chatReplyNotSignedIn => 'Du bist nicht angemeldet. Melde dich an und versuche es erneut.';

  @override
  String deviceOnboardingVoiceReplySettingsHint(String settings, String voiceResponse) {
    return 'Sie können dies jederzeit unter $settings › $voiceResponse ändern';
  }

  @override
  String get wrappedGenerateMyWrapped => 'Meinen Wrapped generieren';

  @override
  String get reviewChangesIntro =>
      'Was Omi in den letzten 30 Tagen selbst geändert hat. Mach alles rückgängig, was falsch aussieht.';

  @override
  String get stripeReadyForPayments =>
      'Ihr Stripe-Konto ist jetzt bereit, Zahlungen zu empfangen. Sie können sofort mit dem Verdienen aus Ihren App-Verkäufen beginnen.';

  @override
  String get appleWatchSetup => 'Apple Watch Einrichtung';

  @override
  String get failedToDisconnect => 'Trennen fehlgeschlagen';

  @override
  String get localStorageEnabled => 'Lokaler Speicher aktiviert';

  @override
  String get captureSourceDesktop => 'Desktop';

  @override
  String get serialNumber => 'Seriennummer';

  @override
  String get appleHealthFeatureSecureDesc =>
      'Deine Apple Health-Daten werden privat mit deinem Omi-Konto synchronisiert.';

  @override
  String get tryAdjustingSearch => 'Versuchen Sie, Ihre Suche oder Filter anzupassen';

  @override
  String connectTo(String appName) {
    return 'Verbinden mit $appName';
  }

  @override
  String get exportConversationsDescription => 'Gespräche als JSON exportieren';

  @override
  String get featuredLabel => 'EMPFOHLEN';

  @override
  String get speechProfile => 'Stimmprofil';

  @override
  String get integrations => 'Integrationen';

  @override
  String get hideCompletedTasks => 'Erledigte ausblenden';

  @override
  String get sendRawAudioToOmi => 'Roh-Audio an Omi senden';

  @override
  String ratingsCount(String count) {
    return '$count+ Bewertungen';
  }

  @override
  String get exportShared => 'Export geteilt';

  @override
  String get conversationTimeout => 'Unterhaltungs-Timeout';

  @override
  String get installStableFirmware => 'Stabile Firmware installieren';

  @override
  String get secureAndReliable => 'Sicher und zuverlässig';

  @override
  String get exportingConversations => 'Konversationen werden exportiert…';

  @override
  String get feedbackReasonRecordingFragmentedOrDuplicated => 'Fragmentiert oder dupliziert';

  @override
  String get chatAppsWaitingMessage =>
      'Sende die Nachricht in Nachrichten. Dieser Bildschirm aktualisiert sich, sobald Omi sie erhält.';

  @override
  String get onboardingSetupStepWorkspace => 'Dein Arbeitsbereich wird vorbereitet';

  @override
  String get recap => 'Rückblick';

  @override
  String get lessThanAMinute => 'Weniger als eine Minute';

  @override
  String get tasks => 'Aufgaben';

  @override
  String get onboardingSetupStepDevices => 'Deine Geräte werden verbunden';

  @override
  String pinPersonTitle(String name) {
    return '$name anheften';
  }

  @override
  String get wrappedButYouPushedThrough => 'Aber du hast es geschafft 💪';

  @override
  String get fetchingYourAppDetails => 'App-Details werden abgerufen';

  @override
  String get timeout2MinutesDesc => 'Unterhaltung nach 2 Minuten Stille beenden';

  @override
  String get otaUpdateCancelled => 'Update abgebrochen';

  @override
  String get usageTasksNotes => 'Tasks & notes';

  @override
  String get deviceNotConnected => 'Gerät nicht verbunden';

  @override
  String get rayBanMetaMicPickerEmpty =>
      'Keine Bluetooth-Mikrofone gefunden. Verbinde deine Brille in den iPhone-Einstellungen und versuche es erneut.';

  @override
  String get actionItemCompleted => 'Aufgabe erledigt';

  @override
  String get usageSocialSettings => 'In sozialen Umgebungen';

  @override
  String get from => 'von';

  @override
  String get siriIndexSetting => 'Use Omi with Siri & Apple Intelligence';

  @override
  String get reviewReasonNotMine => 'Nicht meine';

  @override
  String connectToDeviceName(String deviceName) {
    return 'Mit $deviceName verbinden';
  }

  @override
  String get onboardingComplete => 'Fertig';

  @override
  String get chatAppsShowInApp => 'Diese Chats in der Omi-App anzeigen';

  @override
  String nCompleted(int count) {
    return '$count erledigt';
  }

  @override
  String get feedbackAllGood => 'Alles gut';

  @override
  String get syncCardUploadingTitle => 'Wird zu Omi hochgeladen';

  @override
  String get baselineMemory => 'Basis-Erinnerung';

  @override
  String get trainFamilyProfilesDesc =>
      'Ihre Aufnahmen helfen uns, Profile für Ihre Freunde und Familie zu erkennen und zu erstellen.';

  @override
  String get failedToGenerateShareLink => 'Fehler beim Generieren des Freigabe-Links';

  @override
  String get onlyYouCanSeeConversation => 'Nur Sie können diese Unterhaltung sehen';

  @override
  String get popular => 'Beliebt';

  @override
  String get captureRecordingSeparate => 'Trennen…';

  @override
  String get allTemplates => 'Alle Vorlagen';

  @override
  String devicesFoundNearby(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'GERÄTE',
      one: 'GERÄT',
    );
    return '$count $_temp0 IN DER NÄHE GEFUNDEN';
  }

  @override
  String speakerTagPromptSavedAs(String name) {
    return 'Gespeichert als $name';
  }

  @override
  String get configureSettings => 'Einstellungen konfigurieren';

  @override
  String get noRatings => 'keine Bewertungen';

  @override
  String resumingInCountdown(String countdown) {
    return 'Fortsetzung in ${countdown}s…';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 $count Erinnerungen gespeichert';
  }

  @override
  String get clearDueDate => 'Fälligkeitsdatum löschen';

  @override
  String get copy => 'Kopieren';

  @override
  String get showPhoneCallButtonDesc => 'Anruf-Schaltfläche auf dem Startbildschirm anzeigen';

  @override
  String get appleHealthFeatureReadOnlyDesc => 'Omi schreibt nie in Apple Health und ändert deine Daten nicht.';

  @override
  String get multipleSpeakersDescription =>
      'Es scheint, dass mehrere Sprecher in der Aufnahme sind. Stellen Sie sicher, dass Sie an einem ruhigen Ort sind, und versuchen Sie es erneut.';

  @override
  String get failedToUpdateDueDate => 'Aktualisierung des Fälligkeitsdatums fehlgeschlagen';

  @override
  String get successfullyConnectedWhoop => 'Erfolgreich mit Whoop verbunden!';

  @override
  String get categories => 'Kategorien';

  @override
  String get loadingTranscript => 'Transkript wird geladen…';

  @override
  String get syncCustomSttWarningMessage =>
      'Du verwendest einen eigenen Transkriptionsanbieter. Beim Synchronisieren werden diese Aufnahmen stattdessen auf den Servern von Omi transkribiert und auf das Transkriptionslimit deines Tarifs angerechnet.';

  @override
  String get newRecording => 'Neue Aufnahme';

  @override
  String get transcriptionUnavailableRecordingSaved =>
      'Transkription nicht verfügbar — die Aufnahme läuft weiter und Ihr Audio wird gespeichert.';

  @override
  String get submittingYourApp => 'Ihre App wird eingereicht…';

  @override
  String get failedToLinkCalendarEvent => 'Kalendertermin konnte nicht verknüpft werden';

  @override
  String get paypalMeLinkHint => 'paypal.me/nik';

  @override
  String get yourInformation => 'Ihre Informationen';

  @override
  String get accountDeletionInProgressSignInAgain =>
      'Dieses Konto wird gerade gelöscht. Melde dich mit einem anderen Konto an oder warte ein paar Minuten und versuche es erneut.';

  @override
  String get on => 'On';

  @override
  String get diagnostics => 'Diagnose';

  @override
  String get errorCopied => 'Fehlermeldung in die Zwischenablage kopiert';

  @override
  String get lovingOmi => 'Gefällt Ihnen Omi?';

  @override
  String get permissionDescReadMemories => 'Diese App kann auf deine Erinnerungen zugreifen.';

  @override
  String get doNotIncludeHttpInLink => 'Fügen Sie http, https oder www nicht in den Link ein';

  @override
  String get shareRecording => 'Aufnahme teilen';

  @override
  String get memoryReviewFix => 'Korrigieren';

  @override
  String get selectedPlanNotAvailable => 'Der ausgewählte Plan ist nicht verfügbar. Bitte versuchen Sie es erneut.';

  @override
  String get autoCreateWhenDetected => 'Automatisch erstellen, wenn Name erkannt wird';

  @override
  String get addAppSelectCapability => 'Bitte wählen Sie mindestens eine Fähigkeit für Ihre App aus';

  @override
  String get showPassword => 'Passwort anzeigen';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Unterhaltungen enden nun nach $minutes Minute(n) Stille';
  }

  @override
  String get updateAvailableMessage => 'Eine neue Version von Omi ist bereit, mit Fehlerbehebungen und Verbesserungen.';

  @override
  String get nameMustBeBetweenCharacters => 'Der Name muss zwischen 2 und 40 Zeichen lang sein';

  @override
  String operatorSubtitle(int count) {
    return '$count Fragen pro Monat';
  }

  @override
  String conversationsDeletedCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count Unterhaltungen gelöscht',
      one: '1 Unterhaltung gelöscht',
    );
    return '$_temp0';
  }

  @override
  String get monthlyPayoutsDescription =>
      'Erhalten Sie monatliche Zahlungen direkt auf Ihr Konto, wenn Sie 10 \$ Einnahmen erreichen';

  @override
  String get dailyScoreExplanation =>
      'Ihr täglicher Score basiert auf der Aufgabenerledigung. Erledigen Sie Ihre Aufgaben, um Ihren Score zu verbessern!';

  @override
  String get improveConnectionContent =>
      'Wir haben verbessert, wie Omi mit deinem Gerät verbunden bleibt. Um dies zu aktivieren, gehe zur Geräteinfo-Seite, tippe auf \"Gerät trennen\" und verbinde dein Gerät erneut.';

  @override
  String get syncingRecordings => 'Synchronisiere Aufnahmen';

  @override
  String get professionProductManager => 'Produktmanager';

  @override
  String get nameMustBeAtLeast2Characters => 'Der Name muss mindestens 2 Zeichen lang sein';

  @override
  String get conversationTitle => 'Gesprächstitel';

  @override
  String mcpServerConnected(int count) {
    return '$count Tools erfolgreich verbunden';
  }

  @override
  String get feedbackSubtitleNotUsing => 'Wir möchten Omi nützlicher für dich machen.';

  @override
  String get exportBeforeDelete =>
      'Sie können Ihre Daten exportieren, bevor Sie Ihr Konto löschen. Einmal gelöscht, können sie nicht wiederhergestellt werden.';

  @override
  String deleteTasksTitle(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count Aufgaben löschen?',
      one: '1 Aufgabe löschen?',
    );
    return '$_temp0';
  }

  @override
  String get frequencyMaximum => 'Maximal';

  @override
  String get cancelReasonSubtitle => 'Kannst du uns sagen, warum du gehst?';

  @override
  String get generatingIconStep => 'Generiere Icon';

  @override
  String get storeAudioDescription =>
      'Bewahren Sie alle Audioaufnahmen lokal auf Ihrem Telefon auf. Bei Deaktivierung werden nur fehlgeschlagene Uploads gespeichert, um Speicherplatz zu sparen.';

  @override
  String get unpairDeviceConfirmTitle => 'Gerät entkoppeln?';

  @override
  String get phoneCallsMaybeLater => 'Vielleicht später';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'Ein Fehler ist aufgetreten: $message';
  }

  @override
  String get yourPrivacyMattersToUs => 'Ihre Privatsphäre ist uns wichtig';

  @override
  String get collapseAction => 'Einklappen';

  @override
  String get friendWordOfMouth => 'Freund';

  @override
  String get deviceOnboardingVoiceReplyStatusHeadphonesDisconnected =>
      'Keine Kopfhörer angeschlossen. Omi bleibt stumm, bis Sie eine Verbindung herstellen.';

  @override
  String get connectDevice => 'Gerät verbinden';

  @override
  String get deviceId => 'Geräte-ID';

  @override
  String get addWordsDescription => 'Fügen Sie Wörter hinzu, die Omi während der Transkription erkennen soll.';

  @override
  String get userId => 'Benutzer-ID';

  @override
  String evidenceCardConfirms(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Ja bei $count Vorschlägen',
      one: 'Ja bei 1 Vorschlag',
    );
    return '$_temp0';
  }

  @override
  String segmentsCount(int count) {
    return '$count Segmente';
  }

  @override
  String get permissionsSetupTitle => 'Hol dir das beste Erlebnis';

  @override
  String get permissionTypeAccess => 'Zugriff';

  @override
  String get speakerTagPromptSaveVoicesBody =>
      'Omi speichert eine kurze Stimmprobe, um sie beim nächsten Mal zu erkennen. Du kannst das jederzeit in den Einstellungen ändern.';

  @override
  String get developerApi => 'Entwickler-API';

  @override
  String get chargingIssues => 'Ladeprobleme';

  @override
  String get debugAndDiagnostics => 'Debug & Diagnose';

  @override
  String get failedConnections => 'Fehlgeschlagene Verbindungen';

  @override
  String get userIdCopied => 'Benutzer-ID in die Zwischenablage kopiert';

  @override
  String get cannotReportOwnMessage => 'Sie können Ihre eigenen Nachrichten nicht melden.';

  @override
  String get latestVersion => 'Neueste Version';

  @override
  String get feedbackReasonNotHelpful => 'Nicht hilfreich oder irrelevant';

  @override
  String get deletePeopleMessage =>
      'Dadurch werden die Stimmproben entfernt. Das lässt sich nicht rückgängig machen. Ihre Beiträge in früheren Gesprächen werden zu unbenannten Sprechern.';

  @override
  String get deviceOnboardingAllSetSubtitle => 'Tippe auf eine Zeile, um sie zu prüfen oder zu ändern.';

  @override
  String get mergeConversations => 'Unterhaltungen zusammenführen';

  @override
  String get paused => 'Pausiert';

  @override
  String get updateGuide => 'Update-Anleitung';

  @override
  String cancelBillingPeriodInfo(String date) {
    return 'Dein Plan bleibt bis zum $date aktiv. Danach wirst du auf die kostenlose Version mit eingeschränkten Funktionen umgestellt.';
  }

  @override
  String get reconnectingToInternet => 'Verbindung zum Internet wird wiederhergestellt…';

  @override
  String get allFilesDeleted => 'Alle Aufnahmen gelöscht';

  @override
  String get paypalEmailHint => 'nik@example.com';

  @override
  String get oneWeekAgo => 'vor 1 Woche';

  @override
  String get deviceOnboardingAllSetSinglePressBadge => '1×';

  @override
  String get playbackAudioUnavailable => 'Audio nicht verfügbar';

  @override
  String get deviceOnboardingTryDoubleTap => 'Probier es jetzt aus! Tippe zweimal auf dein Omi';

  @override
  String get deleteReasonPrivacy => 'Datenschutzbedenken';

  @override
  String get cleanUpPinnedNote => 'Angeheftete Personen werden nie ins Aufräumen einbezogen.';

  @override
  String get wrappedProductiveDay => 'Produktiv';

  @override
  String get voiceSharedAcrossDevices => 'Deine Stimmauswahl wird auf Mobilgerät und Desktop geteilt.';

  @override
  String get knowledgeGraphDeleted => 'Wissensgraph gelöscht';

  @override
  String get pressDoneToCreate => 'Drücken Sie Fertig zum Erstellen';

  @override
  String get cloudStorage => 'Cloud-Speicher';

  @override
  String get howDoesItWork => 'Wie funktioniert es?';

  @override
  String get submitApp => 'App einreichen';

  @override
  String get searchMemories => 'Erinnerungen durchsuchen';

  @override
  String get fallNotificationTitle => 'Autsch';

  @override
  String storedOnDevice(String deviceName) {
    return 'Speicherort: $deviceName';
  }

  @override
  String get contactsPermissionRequired => 'Kontaktberechtigung erforderlich';

  @override
  String get reviewUpdatedSuccessfully => 'Bewertung erfolgreich aktualisiert 🚀';

  @override
  String get pleaseEnterPayPalMeLink => 'Bitte geben Sie Ihren PayPal.me-Link ein';

  @override
  String get notHelpful => 'Nicht hilfreich';

  @override
  String get recordingsToSync => 'Aufnahmen zu synchronisieren';

  @override
  String get categoryUtilities => 'Werkzeuge';

  @override
  String get exportStarted => 'Export gestartet. Dies kann einige Sekunden dauern…';

  @override
  String get deviceOnboardingVoiceReplyStatusOff =>
      'Omi wird schweigen. Antworten werden weiterhin in der App angezeigt.';

  @override
  String get myGoal => 'Mein Ziel';

  @override
  String timeHourSingular(int count) {
    return '$count Stunde';
  }

  @override
  String get chatToolsManifestUrl => 'URL des Chat-Tools-Manifests';

  @override
  String msgSelectFilesError(String error) {
    return 'Fehler beim Auswählen von Dateien: $error';
  }

  @override
  String connectedToApp(String appName) {
    return 'Verbunden mit $appName';
  }

  @override
  String get entityCorrectionHint => 'Sag Omi, was korrigiert werden soll';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch erfolgreich verbunden!';

  @override
  String appIntegration(String appName) {
    return '$appName-Integration';
  }

  @override
  String get cancelReasonAudioQuality => 'Audio-/Transkriptionsqualität';

  @override
  String get invalidProviderInConfig => 'Ungültiger Anbieter in der Konfiguration';

  @override
  String get deselectAll => 'Alle abwählen';

  @override
  String get chatAppsCodeExpiredMessage => 'Hol dir einen neuen Code und sende ihn in Nachrichten.';

  @override
  String get reviewAnswerFailed => 'Deine Antwort konnte nicht gespeichert werden. Versuche es erneut.';

  @override
  String get categorySocial => 'Soziales';

  @override
  String get rating4PlusStars => '4+ Sterne';

  @override
  String get couldNotOpenSmsApp => 'SMS-App konnte nicht geöffnet werden. Bitte versuchen Sie es erneut.';

  @override
  String get chatAppsNoMessages => 'Keine Nachrichten';

  @override
  String get wrappedCelebrity => 'PROMI';

  @override
  String get revokeKeyQuestion => 'Schlüssel widerrufen?';

  @override
  String timeMinsAndSecs(int mins, int secs) {
    return '$mins Min $secs Sek';
  }

  @override
  String get searchContactsHint => 'Kontakte suchen';

  @override
  String get showEventsWithoutParticipants => 'Ereignisse ohne Teilnehmer anzeigen';

  @override
  String get fair => 'Befriedigend';

  @override
  String get tipAutoSync => 'Aufnahmen werden automatisch synchronisiert';

  @override
  String get summaryCopiedToClipboard => 'Zusammenfassung in Zwischenablage kopiert';

  @override
  String get clearSearch => 'Suche löschen';

  @override
  String get speakerTagPromptNotAPerson => 'Keine Person';

  @override
  String get modelLabel => 'Modell';

  @override
  String deleteItemQuestion(String item) {
    return '$item löschen?';
  }

  @override
  String get enterPromoCode => 'Aktionscode eingeben';

  @override
  String get phoneNoContactsFound => 'Keine Kontakte gefunden';

  @override
  String countRemaining(String count) {
    return '$count verbleibend';
  }

  @override
  String get manageYourApp => 'Verwalten Sie Ihre App';

  @override
  String get willSyncAutomatically => 'wird automatisch synchronisiert';

  @override
  String get promoCode => 'Aktionscode';

  @override
  String get trackPersonalGoalsOnHomepage => 'Verfolgen Sie Ihre persönlichen Ziele auf der Startseite';

  @override
  String get memoryHistoryPartial =>
      'Ein Teil des Erinnerungsverlaufs ist nicht verfügbar. Der bisher empfangene Verlauf wird angezeigt.';

  @override
  String get sharePublicLink => 'Öffentlichen Link teilen';

  @override
  String get conversationTab => 'Unterhaltung';

  @override
  String get backgroundModeDescription =>
      'Lass deinen Omi weiter aufnehmen, auch wenn die App vollständig geschlossen ist.';

  @override
  String get pairingDescOmiDevkit =>
      'Drücken Sie die Taste einmal zum Einschalten. Die LED blinkt lila im Kopplungsmodus.';

  @override
  String get callStateFailed => 'Anruf fehlgeschlagen';

  @override
  String get githubRepositoryUrlHint => 'Link zum Quellcode-Repository deiner App';

  @override
  String get appIconLabel => 'App Icon';

  @override
  String get uninstallApp => 'App deinstallieren';

  @override
  String get confidenceReasonNeedsVoice => 'noch keine Stimmprobe';

  @override
  String get couldNotLoadApiKeys => 'API-Schlüssel konnten nicht geladen werden.';

  @override
  String get fetchingStableFirmware => 'Neueste stabile Firmware wird abgerufen…';

  @override
  String get onDeviceModelDownloaded => 'Heruntergeladen';

  @override
  String get noAPIKeys => 'Keine API-Schlüssel. Erstellen Sie einen, um loszulegen.';

  @override
  String get phoneCallsUpsellFeature3 => 'Empfänger sehen deine echte Nummer, keine zufällige';

  @override
  String get wrappedMovieRecs => 'Filmempfehlungen für Freunde';

  @override
  String msgFilePickerError(String error) {
    return 'Fehler beim Öffnen der Dateiauswahl: $error';
  }

  @override
  String get professionEntrepreneur => 'Unternehmer';

  @override
  String get recent => 'Zuletzt';

  @override
  String get permissionDescCreateMemories => 'Diese App kann neue Erinnerungen erstellen.';

  @override
  String get tapToComplete => 'Tippen zum Abschließen';

  @override
  String vocabularyWordCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count Wörter',
      one: '1 Wort',
    );
    return '$_temp0';
  }

  @override
  String get deleteSyncedFilesMessage =>
      'Diese Aufnahmen wurden bereits mit Ihrem Telefon synchronisiert. Dies kann nicht rückgängig gemacht werden.';

  @override
  String get cancelConsequenceSpeakers => 'Kann Sprecher nicht identifizieren.';

  @override
  String get aiGenFailedToGenerateApp => 'App konnte nicht generiert werden. Bitte versuche es erneut.';

  @override
  String get account => 'Konto';

  @override
  String get capabilityIntegrations => 'Integrationen';

  @override
  String get voiceSettingsAskToTag => 'Mich bitten, Stimmen zuzuordnen';

  @override
  String get chatAppsHeroTitle => 'Chatte mit Omi, wo du sowieso chattest';

  @override
  String get myApps => 'Von mir erstellt';

  @override
  String get deleteRecap => 'Zusammenfassung löschen';

  @override
  String get production => 'Produktion';

  @override
  String get phoneRecordingBlockedByPendantBatch =>
      'Beende Transcribe Later auf deinem Anhänger, bevor du mit dem Telefon aufnimmst.';

  @override
  String dataRateKbps(String rate) {
    return '$rate kbit/s';
  }

  @override
  String get createAKeyToGetStarted => 'Erstellen Sie einen Schlüssel, um loszulegen';

  @override
  String get pleaseSelectRating => 'Bitte wähle eine Bewertung';

  @override
  String get pdfTranscriptExport => 'Transkript-Export';

  @override
  String get newFolder => 'Neuer Ordner';

  @override
  String get fallNotificationBody => 'Bist du gestürzt?';

  @override
  String get scopeUserChat => 'Benutzer-Chat';

  @override
  String get tryDifferentSearchTerm => 'Versuchen Sie einen anderen Suchbegriff';

  @override
  String get submit => 'Senden';

  @override
  String get deviceOnboardingVoiceReplySubtitle => 'Wenn Sie mit der Taste fragen, kann Omi die Antwort laut vorlesen.';

  @override
  String get showOnLockScreen => 'Auf dem Sperrbildschirm anzeigen';

  @override
  String get msgMaxImagesLimit => 'Sie können nur bis zu 4 Bilder auswählen';

  @override
  String get wrappedOmiLifeRecap => 'Omi Lebensrückblick';

  @override
  String get nextButton => 'Weiter';

  @override
  String disconnectAppTitle(String appName) {
    return '$appName trennen?';
  }

  @override
  String get updateReview => 'Bewertung aktualisieren';

  @override
  String get noMemoriesInCategory => 'Noch keine Erinnerungen in dieser Kategorie';

  @override
  String get memoryDeleted => 'Erinnerung gelöscht';

  @override
  String get connectOmiDevice => 'Omi-Gerät verbinden';

  @override
  String get professionSoftwareEngineer => 'Softwareentwickler';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'Andere Segmente von diesem Sprecher markieren ($selected/$total)';
  }

  @override
  String get productName => 'Produktname';

  @override
  String get permissionDeniedForAppleReminders => 'Berechtigung für Apple Erinnerungen verweigert';

  @override
  String get allMemoriesAreNowPrivate => 'Alle Erinnerungen sind jetzt privat';

  @override
  String planSetToCancelOn(String date) {
    return 'Ihr Plan wird am $date gekündigt.\nAbonnieren Sie jetzt erneut, um Ihre Vorteile zu behalten - keine Gebühr bis $date.';
  }

  @override
  String get deletePersonTitle => 'Person löschen?';

  @override
  String deleteItemConfirmation(String item) {
    return '$item wird gelöscht. Dies kann nicht rückgängig gemacht werden.';
  }

  @override
  String get appleHealthConnectCta => 'Mit Apple Health verbinden';

  @override
  String segmentsPlural(String count) {
    return '$count Segmente';
  }

  @override
  String get syncCardDownloadingTitle => 'Wird von deinem Gerät heruntergeladen';

  @override
  String additionalSampleIndex(String index) {
    return 'Zusätzliche Probe $index';
  }

  @override
  String get descriptionLabel => 'Beschreibung';

  @override
  String get failedToClearDueDate => 'Löschen des Fälligkeitsdatums fehlgeschlagen';

  @override
  String get timeout4HoursDesc => 'Unterhaltung nach 4 Stunden Stille beenden';

  @override
  String get noSyncedRecordingsYet => 'Noch keine synchronisierten Aufnahmen';

  @override
  String dreamReportDropped(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count ältere Änderungen übersprungen',
      one: '1 ältere Änderung übersprungen',
    );
    return '$_temp0';
  }

  @override
  String get claudeCode => 'Claude Code';

  @override
  String get noPendingRecordings => 'Keine ausstehenden Aufnahmen';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'Sagen Sie uns, wie Sie angesprochen werden möchten. Dies hilft, Ihr Omi-Erlebnis zu personalisieren.';

  @override
  String get updateSummaryWithNewNames => 'Zusammenfassung mit neuen Namen aktualisieren';

  @override
  String get setWhenConversationsAutoEnd => 'Wie lange Omi bei Stille wartet, bevor ein Gespräch endet';

  @override
  String get successfullyConnectedGoogleTasks => 'Erfolgreich mit Google Tasks verbunden!';

  @override
  String get confirmUpgrade => 'Upgrade bestätigen';

  @override
  String get speechToTextProviderDesc => 'Wählen Sie den Dienst für die Transkription';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Fehler beim Verbinden mit Apple Watch: $error';
  }

  @override
  String get instagram => 'Instagram';

  @override
  String sampleNumber(int number) {
    return 'Beispiel $number';
  }

  @override
  String get popularApps => 'Beliebte Apps';

  @override
  String get micGainDescSlightlyBoosted => 'Leicht verstärkt - normale Nutzung';

  @override
  String get promptMustBeAtLeast10Characters => 'Die Aufforderung muss mindestens 10 Zeichen haben';

  @override
  String get chatAppsEntryRowSubtitle => 'Telegram, iMessage und mehr';

  @override
  String get estimatedSizeLabel => 'Geschätzte Größe';

  @override
  String get mcpServerDesc => 'KI-Assistenten mit Ihren Daten verbinden';

  @override
  String get disconnectHistory => 'Trennungsverlauf';

  @override
  String get downgradeLimitDelay => '5–7 Sekunden Verzögerung';

  @override
  String get msgSelectImagesGenericError => 'Fehler beim Auswählen von Bildern. Bitte versuchen Sie es erneut.';

  @override
  String get audioPlaybackUnavailable => 'Audiodatei ist nicht zur Wiedergabe verfügbar';

  @override
  String get byClickingConnectNow => 'Durch Klicken auf \"Jetzt verbinden\" stimmen Sie zu';

  @override
  String get signalStrength => 'Signalstärke';

  @override
  String get tellUsPrimaryLanguage => 'Sagen Sie uns Ihre primäre Sprache';

  @override
  String get diagnosticsShareFailed => 'Diagnose konnte nicht geteilt werden. Bitte versuche es erneut.';

  @override
  String get createKeyToStart => 'Erstellen Sie einen Schlüssel, um zu beginnen';

  @override
  String generatedBy(String appName) {
    return 'Generiert von $appName';
  }

  @override
  String shareStatsListened(String minutes) {
    return '🎧 Für $minutes Minuten zugehört';
  }

  @override
  String get getOmiDevice => 'Omi-Gerät holen';

  @override
  String get newTask => 'Neue Aufgabe';

  @override
  String get conversationPrompt => 'Gesprächsaufforderung';

  @override
  String get otaWifiConnected => 'Mit WLAN verbunden';

  @override
  String get dismiss => 'Ausblenden';

  @override
  String get webhooks => 'Webhooks';

  @override
  String get raybanMetaCamera => 'Kamera';

  @override
  String get recapRegenerateNoConversations => 'Keine Konversationen für diesen Tag zum Zusammenfassen.';

  @override
  String pendantMinutesStored(int minutes) {
    return '~$minutes Min. gespeichert';
  }

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName getrennt';
  }

  @override
  String get normal => 'Normal';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch ist noch nicht erreichbar. Stelle sicher, dass die Omi-App auf deiner Uhr geöffnet ist.';

  @override
  String get connectionGuide => 'Verbindungsanleitung';

  @override
  String get syncStepProcessDesc => 'Omi macht aus dem Audio ein Gespräch';

  @override
  String get couldNotLoadPlans => 'Verfügbare Pläne konnten nicht geladen werden. Bitte versuchen Sie es erneut.';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '$used von $limit Min. diesen Monat genutzt';
  }

  @override
  String get learnMoreLink => 'mehr erfahren';

  @override
  String get unpairDeviceDialogMessage =>
      'Dies entkoppelt das Gerät, damit es mit einem anderen Telefon verbunden werden kann. Sie müssen zu Einstellungen > Bluetooth gehen und das Gerät vergessen, um den Vorgang abzuschließen.';

  @override
  String get authFailedToRetrieveToken =>
      'Firebase-Token konnte nicht abgerufen werden, bitte versuchen Sie es erneut.';

  @override
  String get aiGenFailedToCreateApp => 'App konnte nicht erstellt werden';

  @override
  String get appAndDeviceCopied => 'App- und Gerätedetails kopiert';

  @override
  String get noProcessedRecordings => 'Noch keine verarbeiteten Aufnahmen';

  @override
  String get transcriptTab => 'Transkript';

  @override
  String get permissionDescReadConversations => 'Diese App kann auf deine Gespräche zugreifen.';

  @override
  String get tryAnotherApp => 'Andere App ausprobieren';

  @override
  String get subscriptionSetToCancel => 'Ihr Abonnement wird zum Ende des Zeitraums gekündigt.';

  @override
  String chatAppsCodeExpiresIn(String time) {
    return 'Code läuft ab in $time';
  }

  @override
  String get authFailedToSignInWithApple => 'Anmeldung mit Apple fehlgeschlagen, bitte versuchen Sie es erneut.';

  @override
  String get feedbackReasonIgnoredInstructions => 'Anweisungen nicht befolgt';

  @override
  String get startupFailedDetails => 'Details';

  @override
  String get deleteMeetingScreenshotTitle => 'Bildschirmfoto löschen?';

  @override
  String get chatAppsNotConnectedMessage => 'Diese Chat-App wurde getrennt.';

  @override
  String get aboutOmiApiKeys => 'Über Omi API-Schlüssel';

  @override
  String get tiktok => 'TikTok';

  @override
  String get maxFilesLimit => 'Sie können nur 4 Dateien gleichzeitig hochladen';

  @override
  String get legalNotice =>
      'Rechtlicher Hinweis: Die Rechtmäßigkeit der Aufnahme und Speicherung von Sprachdaten kann je nach Ihrem Standort und der Art und Weise, wie Sie diese Funktion nutzen, variieren. Es liegt in Ihrer Verantwortung, die Einhaltung der örtlichen Gesetze und Vorschriften sicherzustellen.';

  @override
  String get wrappedYourTopDays => 'Deine besten Tage';

  @override
  String get addMcpServer => 'MCP-Server hinzufügen';

  @override
  String publicAppsCount(String count) {
    return 'Öffentliche Apps ($count)';
  }

  @override
  String get noExternalAppsHaveAccess => 'Keine externen Apps haben Zugriff auf Ihre Daten.';

  @override
  String get captureStarting => 'Startet…';

  @override
  String get downloadingAudioProgress => 'Lade Audio herunter';

  @override
  String get audioBytes => 'Audio-Bytes';

  @override
  String batteryLevelSemantics(int level) {
    return 'Akku $level %';
  }

  @override
  String captureRecordedBy(String devices) {
    return 'Aufgenommen von $devices';
  }

  @override
  String get chatAppsRepliesOnlyNote => 'Omi antwortet nur dir. Omi schreibt nie zuerst.';

  @override
  String get hideTranscript => 'Transkript ausblenden';

  @override
  String get permissionReadConversations => 'Gespräche lesen';

  @override
  String get installed => 'Installiert';

  @override
  String get paymentEnterValidAmount => 'Bitte geben Sie einen gültigen Betrag ein';

  @override
  String get sttLanguageOverride => 'Überschreiben';

  @override
  String get appInterfaceSectionTitle => 'App-Oberfläche';

  @override
  String get searchLanguages => 'Sprachen suchen';

  @override
  String get otherSource => 'Sonstiges';

  @override
  String get pairingDescOmiGlass => 'Halten Sie die Seitentaste 3 Sekunden gedrückt, um einzuschalten.';

  @override
  String get signOut => 'Abmelden';

  @override
  String shareStatsWords(String words) {
    return '🧠 $words Wörter verstanden';
  }

  @override
  String verifiedDaysAgo(int days) {
    return 'Vor ${days}T verifiziert';
  }

  @override
  String get captureModeLater => 'Später';

  @override
  String get enableMoreApps => 'Weitere Apps aktivieren';

  @override
  String get frequencyDescBalanced => 'Nützliche Vorschläge, etwa 5–8 pro Tag';

  @override
  String get startYourFirstRecording => 'Starten Sie Ihre erste Aufnahme';

  @override
  String get transcriptionPausedReconnecting =>
      'Nimmt weiterhin auf — Verbindung zur Transkription wird wiederhergestellt…';

  @override
  String get basicPlan => 'Kostenloser Plan';

  @override
  String get user => 'Benutzer';

  @override
  String get pinPersonDescription =>
      'Angeheftete Personen bleiben oben in deiner Personenliste und werden nicht durch Aufräumen entfernt.';

  @override
  String get reviewProject => 'Projekt';

  @override
  String get keyboardShortcuts => 'Tastaturkürzel';

  @override
  String get diagnosticsFailBadge => 'Fehlgeschlagen';

  @override
  String get debugLogCleared => 'Debug-Protokoll gelöscht';

  @override
  String get errorConnectingToStripe => 'Fehler beim Verbinden mit Stripe! Bitte versuchen Sie es später erneut.';

  @override
  String get tapPlusToStartRecording => 'Tippe auf die Aufnahmetaste, um die Aufnahme zu starten';

  @override
  String get permissionBlockedHint => 'In den Einstellungen deaktiviert. Erlaube es dort, um diese Funktion zu nutzen.';

  @override
  String get downloadingAudio => 'Lade Audio herunter…';

  @override
  String failedToRevokeApiKey(String error) {
    return 'Fehler beim Widerrufen des API-Schlüssels: $error';
  }

  @override
  String largeTimeGapDetected(String gap) {
    return 'Große Zeitlücke erkannt ($gap)';
  }

  @override
  String get customFirmwareWarning =>
      'Eigene Firmware kann dein Gerät unbrauchbar machen. Stelle sicher, dass es ein gültiger Omi-Firmware-Build ist, und trenne das Gerät während des Updates nicht.';

  @override
  String get wrapped2025 => 'Jahresrückblick 2025';

  @override
  String get showApiKey => 'API-Schlüssel anzeigen';

  @override
  String get agreeAndContinue => 'Zustimmen und fortfahren';

  @override
  String get connectExternalAiTools => 'Externe KI-Tools verbinden';

  @override
  String get batteryFullyChargedTitle => 'Omi ist vollständig geladen';

  @override
  String get appReEnableFailedTitle => 'Reaktivieren fehlgeschlagen';

  @override
  String get onboardingYourName => 'Dein Name';

  @override
  String get searchApps => 'Apps suchen';

  @override
  String get weak => 'Schwach';

  @override
  String get tellUsMore => 'Erzähl uns mehr (optional)';

  @override
  String confidenceReasonPicked(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'In $count Vorschlägen ausgewählt',
      one: 'In 1 Vorschlag ausgewählt',
    );
    return '$_temp0';
  }

  @override
  String chatAppsDisconnectFooter(String app) {
    return 'Beim Trennen wird der Verlauf gelöscht, den Omi für $app speichert.';
  }

  @override
  String get selectAll => 'Alle auswählen';

  @override
  String get deleteActionItemConfirmation => 'Diese Aufgabe löschen? Dies kann nicht rückgängig gemacht werden.';

  @override
  String get categoryTravel => 'Reisen';

  @override
  String get lowestRating => 'Niedrigste Bewertung';

  @override
  String get tasksEmptyStateMessage => 'Starte ein Gespräch, um eine Aufgabe zu erstellen.';

  @override
  String get unpairAndForget => 'Entkoppeln und Gerät vergessen';

  @override
  String get listeningForAudio => 'Auf Audio hören…';

  @override
  String get processedStatus => 'Verarbeitet';

  @override
  String get wrappedTheHardPart => 'Der schwere Teil';

  @override
  String chatAppsReplyThereAnytime(String app) {
    return 'Schreib Omi jederzeit in $app.';
  }

  @override
  String get upgradePlan => 'Plan upgraden';

  @override
  String get onboardingRatingPromptYes => 'Ja';

  @override
  String timeCompactMins(int count) {
    return '${count}m';
  }

  @override
  String get changeTheConversationTitle => 'Gesprächstitel ändern';

  @override
  String get accountGroup => 'Konto';

  @override
  String get updatingYourApp => 'App wird aktualisiert';

  @override
  String get microphone => 'Mikrofon';

  @override
  String get suggestQuestionsAfterConversations => 'Fragen nach Gesprächen vorschlagen';

  @override
  String get failedToTranscribeAudio => 'Audio konnte nicht transkribiert werden';

  @override
  String get unstarConversation => 'Stern von Unterhaltung entfernen';

  @override
  String get speakerTagPromptNotMe => 'Nicht ich';

  @override
  String get confidenceReasonCorrected => 'Du hast die Zuordnung korrigiert';

  @override
  String get peopleSearchPlaceholder => 'Personen suchen';

  @override
  String get syncStatusUnsupportedAudio => 'Audio nicht lesbar — Synchronisierung nicht möglich';

  @override
  String get indentTask => 'Einrücken';

  @override
  String get selectApp => 'App auswählen';

  @override
  String get updatePayPal => 'PayPal aktualisieren';

  @override
  String get enterNameError => 'Bitte geben Sie Ihren Namen ein';

  @override
  String get exportAllData => 'Alle Daten exportieren';

  @override
  String premiumMinsLeft(int count) {
    return '$count Premium-Minuten übrig.';
  }

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName als Standard-Zusammenfassungs-App festgelegt';
  }

  @override
  String get recordingStartedSuccessfully => 'Aufnahme erfolgreich gestartet!';

  @override
  String get trySomethingLike => 'Versuchen Sie so etwas wie…';

  @override
  String get chatAppsTryAsking => 'Frag zum Beispiel';

  @override
  String get categoryEntertainment => 'Unterhaltung';

  @override
  String get checksForAudioFiles => 'Prüft auf Audiodateien auf der SD-Karte';

  @override
  String get everyoneHeader => 'Alle';

  @override
  String get clearMemoryButton => 'Erinnerung löschen';

  @override
  String confidenceReasonLabeled(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count-mal von dir zugeordnet',
      one: 'Einmal von dir zugeordnet',
    );
    return '$_temp0';
  }

  @override
  String get selectLogFile => 'Protokolldatei auswählen';

  @override
  String get chatAppsTelegramStepReturn => 'Komm hierher zurück. Wir bestätigen, dass es geklappt hat.';

  @override
  String get discordMemberCount => 'Über 8000 Mitglieder auf Discord';

  @override
  String get public => 'Öffentlich';

  @override
  String get outdentTask => 'Ausrücken';

  @override
  String get statusProcessing => 'Wird verarbeitet';

  @override
  String get useFreePlan => 'Kostenlosen Plan nutzen';

  @override
  String get emailLabel => 'E-Mail';

  @override
  String get statusCallInProgress => 'Anruf aktiv';

  @override
  String get shortcuts => 'Tastenkombinationen';

  @override
  String get reviewRecentChanges => 'Letzte Änderungen';

  @override
  String get raybanMetaAudioOnlyExplanation =>
      'Diese Version von Omi kann das Mikrofon Ihrer Brille über Bluetooth verwenden. Die Fotoaufnahme erfordert den Meta-Entwickler-Build von Omi.';

  @override
  String get wrappedDaysActiveLabel => 'aktive Tage';

  @override
  String get installOmiOnAppleWatch => 'Installiere Omi auf deiner\nApple Watch';

  @override
  String tasksCountLabel(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count Aufgaben',
      one: '1 Aufgabe',
    );
    return '$_temp0';
  }

  @override
  String get confidenceReasonVoiceReady => 'Stimme gespeichert';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return '$count ausgewählte Aufgaben$s löschen?';
  }

  @override
  String get sdCardSync => 'SD-Karten-Synchronisierung';

  @override
  String get timeout4Hours => '4 Stunden';

  @override
  String get chatAppsTitle => 'Chat-Apps';

  @override
  String get repeatPasswordLabel => 'Passwort wiederholen';

  @override
  String get skip => 'Überspringen';

  @override
  String get phoneNoVerifiedNumbersTitle => 'Keine bestätigten Nummern';

  @override
  String get connectionLost => 'Verbindung unterbrochen';

  @override
  String get photoDiscardedMessage => 'Dieses Foto wurde verworfen, da es nicht bedeutsam war.';

  @override
  String get weekdayFri => 'Fr';

  @override
  String get moveToFolder => 'In Ordner verschieben';

  @override
  String get updateNow => 'Jetzt aktualisieren';

  @override
  String get failedToUpdateActionItem => 'Aufgabe konnte nicht aktualisiert werden';

  @override
  String get transferRequiredDescription =>
      'Bitte übertrage die Dateien vom Gerät, um die SD-Karten-Einstellungen zu ändern.';

  @override
  String get checkingForUpdates => 'Suche nach Updates';

  @override
  String get importTranscriptFilesDescription => 'Wähle SRT-, VTT- oder TXT-Transkripte oder ein ZIP mit ihnen aus';

  @override
  String get listenToSpeechProfile => 'Mein Stimmprofil anhören ➡️';

  @override
  String get deleteRecapConfirmBody =>
      'Diese Zusammenfassung wird dauerhaft entfernt. Die ursprünglichen Gespräche dieses Tages bleiben erhalten.';

  @override
  String get copyLogs => 'Protokolle kopieren';

  @override
  String get wrappedFunniestMoment => 'Lustigster';

  @override
  String get onboardingMicrophoneRequired => 'Mikrofonberechtigung ist für die Aufnahme erforderlich.';

  @override
  String get whoIsItTitle => 'Wer ist das?';

  @override
  String dreamReportRunsLeft(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Heute noch $count manuelle Durchläufe',
      one: 'Heute noch 1 manueller Durchlauf',
    );
    return '$_temp0';
  }

  @override
  String get modified => 'Geändert';

  @override
  String get actionCreateConversations => 'Gespräche erstellen';

  @override
  String get chatAssistantsTitle => 'Chat-Assistenten';

  @override
  String get connectionError => 'Verbindungsfehler';

  @override
  String get chooseFromGallery => 'Aus Galerie wählen';

  @override
  String get summaryPrompt => 'Zusammenfassungs-Prompt';

  @override
  String get whatWentWrong => 'Was lief schief?';

  @override
  String get keepGoingGreat => 'Weiter so, du machst das großartig';

  @override
  String get deviceConnecting => 'Verbindung wird hergestellt…';

  @override
  String get downgradeLimitBattery => '7-facher Batterieverbrauch';

  @override
  String get privateMemories => 'Private Erinnerungen';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get aiGenPleaseEnterDescription => 'Bitte gib eine Beschreibung für deine App ein';

  @override
  String get enterLiveSttWebsocket => 'Geben Sie Ihren Live-STT-WebSocket-Endpunkt ein';

  @override
  String processingOnServerProgress(int current, int total) {
    return 'Verarbeitung… $current/$total Segmente';
  }

  @override
  String linkedToEvent(String title) {
    return 'Verknüpft mit „$title“';
  }

  @override
  String get failedToSaveCheckConnection => 'Speichern fehlgeschlagen. Bitte Verbindung überprüfen.';

  @override
  String get deviceOnboardingContinue => 'Weiter';

  @override
  String get pairedToAnotherPhone => 'Mit einem anderen Telefon gekoppelt';

  @override
  String get syncingYourRecordings => 'Synchronisiere deine Aufnahmen';

  @override
  String get manual => 'Manuell';

  @override
  String get oneMonthAgo => 'vor 1 Monat';

  @override
  String get clearChatConfirm =>
      'Alle Nachrichten in diesem Chat werden gelöscht. Dies kann nicht rückgängig gemacht werden.';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'Alles, was \"$keyName\" verwendet, verliert den Zugriff. Dies kann nicht rückgängig gemacht werden.';
  }

  @override
  String get vadGateDescription => 'Überspringt stille Audioabschnitte vor der Transkription, um Kosten zu senken.';

  @override
  String get dreamReportScheduled => 'Geplant';

  @override
  String get audioDataReceived => 'Audiodaten empfangen';

  @override
  String get pro => 'Pro';

  @override
  String get micGainDescMuted => 'Mikrofon ist stummgeschaltet';

  @override
  String get enableLocationDescription =>
      'Standortberechtigung wird benötigt, um Bluetooth-Geräte in der Nähe zu finden.';

  @override
  String get conversationTitleUpdatedSuccessfully => 'Gesprächstitel erfolgreich aktualisiert';

  @override
  String get syncStepUpload => 'Synchronisieren';

  @override
  String get removeScreenshot => 'Screenshot entfernen';

  @override
  String get failedToStartCall => 'Anruf konnte nicht gestartet werden';

  @override
  String get deviceDiagnosticsUploadDescription =>
      'Prüfe die Diagnosedaten im JSON unten. Sie enthalten Gerätekennung, Verbindungen, Akkuwerte, Firmwarediagnose und Bluetooth-Ereignisse. Audio und Transkripte sind nicht enthalten.';

  @override
  String get pairingTitleFieldy => 'Fieldy in den Kopplungsmodus versetzen';

  @override
  String get autoDeletesAfterThreeDays => 'Wird nach 3 Tagen automatisch gelöscht.';

  @override
  String get wrappedDaysActive => 'aktive Tage';

  @override
  String get failedToDeleteActionItem => 'Aufgabe konnte nicht gelöscht werden';

  @override
  String get connect => 'Verbinden';

  @override
  String get unableToDeleteConversation => 'Unterhaltung konnte nicht gelöscht werden';

  @override
  String get clearChatAction => 'Chat löschen';

  @override
  String get memoryThisIphone => 'Dieses iPhone';

  @override
  String get captureCustomSttUnreachableDetail =>
      'Dein eigener Sprache-zu-Text-Dienst ist nicht erreichbar. Omi behält das Audio auf diesem Telefon und sendet es, sobald der Dienst wieder da ist. Nichts geht verloren.';

  @override
  String get feedbackGiveFeedback => 'Feedback geben';

  @override
  String failedToUpdateSettings(String error) {
    return 'Einstellungen konnten nicht aktualisiert werden: $error';
  }

  @override
  String get deleteRecordingConfirmation => 'Dies kann nicht rückgängig gemacht werden.';

  @override
  String get advancedSettings => 'Erweiterte Einstellungen';

  @override
  String get transcriptionNoAudio => 'Transkription empfängt kein Audio';

  @override
  String deletePeopleCountAction(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count Personen löschen',
      one: '1 Person löschen',
    );
    return '$_temp0';
  }

  @override
  String get speakerSuggestionAppliesToSpeaker => 'Gilt für jede Zeile dieses Sprechers';

  @override
  String get deviceNotResponding => 'Gerät reagiert nicht';

  @override
  String get everythingSynced => 'Alles ist bereits synchronisiert.';

  @override
  String get onDeviceModelDownloadFailedDesc =>
      'Whisper-Modell konnte nicht heruntergeladen werden. Bitte versuchen Sie es erneut.';

  @override
  String fairUseBannerStatus(String status) {
    return 'Faire Nutzung: $status';
  }

  @override
  String tasksDeleteSelected(int count) {
    return '$count Aufgabe(n) löschen';
  }

  @override
  String get connectPaymentMethodInfo =>
      'Verbinden Sie unten eine Zahlungsmethode, um Auszahlungen für Ihre Apps zu erhalten.';

  @override
  String get conversationNotFoundOrDeleted => 'Unterhaltung nicht gefunden oder wurde gelöscht';

  @override
  String leaveFlowStepOf(int current, int total) {
    return 'Schritt $current von $total';
  }

  @override
  String get deleteTypeToConfirm => 'Tippe DELETE zur Bestätigung';

  @override
  String get clearMemoryTitle => 'Omis Gedächtnis löschen';

  @override
  String get triggerConversationCreation => 'Gesprächserstellung';

  @override
  String get flashCustomFirmware => 'Eigene Firmware flashen';

  @override
  String shareWithContactCount(int count) {
    return 'Mit $count Kontakt teilen';
  }

  @override
  String get customChatbotPersonality => 'Benutzerdefinierte Chatbot-Persönlichkeit';

  @override
  String get betaTesterNotice =>
      'Sie sind Beta-Tester für diese App. Sie ist noch nicht öffentlich. Sie wird öffentlich, sobald sie genehmigt wurde.';

  @override
  String get tomorrow => 'Morgen';

  @override
  String get createdLabel => 'ERSTELLT';

  @override
  String get searchPeople => 'Personen suchen';

  @override
  String get cancelled => 'Abgebrochen';

  @override
  String basicPlanDesc(int limit) {
    return 'Ihr Plan enthält $limit kostenlose Minuten pro Monat. Upgrade für unbegrenzte Nutzung.';
  }

  @override
  String get editMemoryTitle => 'Erinnerung bearbeiten';

  @override
  String get whatDoYouWantToKnow => 'Was möchtest du wissen?';

  @override
  String get confidenceFootnote =>
      'Deine Markierungen und Bestätigungen zählen am meisten. Automatische Markierungen zählen wenig, bis du sie bestätigst.';

  @override
  String get exportFailedTryAgain => 'Export fehlgeschlagen. Bitte versuche es erneut.';

  @override
  String get addAppPhotosPermissionDenied => 'Fotozugriff verweigert. Bitte erlauben Sie den Zugriff auf Fotos';

  @override
  String get filterByDate => 'Nach Datum filtern';

  @override
  String get chatAppsDoesFiles => 'Sendet und empfängt Dateien, Fotos und Sprachnachrichten';

  @override
  String get deleteKnowledgeGraphTitle => 'Wissensgraph löschen?';

  @override
  String get reloadingConversations => 'Gespräche werden neu geladen…';

  @override
  String get aiGenPleaseGenerateAppFirst => 'Bitte generiere zuerst eine App';

  @override
  String get completeYourUpgrade => 'Vervollständigen Sie Ihr Upgrade';

  @override
  String get capturePendantDisconnectedDetail =>
      'Dein Anhänger hat die Verbindung zu diesem Telefon verloren. Omi verbindet sich von selbst neu, sobald der Anhänger eingeschaltet und in der Nähe ist. Alles bisher Aufgenommene ist sicher.';

  @override
  String get greetingMorning => 'Guten Morgen';

  @override
  String get thanksForYourFeedback => 'Danke für Ihr Feedback!';

  @override
  String get deleteActionItemConfirmMessage => 'Diese Aufgabe löschen?';

  @override
  String get syncCardProcessing => 'Wird in Omi verarbeitet…';

  @override
  String get chatAppsTryWeek => 'Fasse meine Woche in drei Zeilen zusammen';

  @override
  String get recordWithPhoneMicSubtitle => 'Mit dem Mikrofon dieses Telefons aufnehmen und transkribieren';

  @override
  String get notifications => 'Benachrichtigungen';

  @override
  String get annualPlanStartsAutomatically => 'Ihr Jahresplan beginnt automatisch, wenn Ihr Monatsplan endet.';

  @override
  String get unpairDialogMessage =>
      'Dies entkoppelt das Gerät, damit es mit einem anderen Telefon verbunden werden kann. Sie müssen zu Einstellungen > Bluetooth gehen und das Gerät vergessen, um den Vorgang abzuschließen.';

  @override
  String get pairingTitleBee => 'Bee in den Kopplungsmodus versetzen';

  @override
  String conversationCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count Unterhaltungen',
      one: '1 Unterhaltung',
    );
    return '$_temp0';
  }

  @override
  String get syncStatusWaiting => 'Wartet auf Synchronisierung';

  @override
  String get validWebsocketUrlRequired => 'Gültige WebSocket-URL ist erforderlich (wss://)';

  @override
  String get improveSpeechProfile => 'Ihr Sprachprofil verbessern';

  @override
  String entityWaitingOn(String name) {
    return 'Warten auf $name';
  }

  @override
  String get feedbackReasonTooVerbose => 'Zu ausführlich';

  @override
  String chatAppsChannelFooter(String app) {
    return 'Deine $app-Chats bleiben in $app. Omi weiß trotzdem, worüber ihr in der App und in deinen anderen Chat-Apps gesprochen habt.';
  }

  @override
  String get wrappedNoDataAvailable => 'Keine Daten verfügbar';

  @override
  String deviceOnboardingAllSetReplayHint(String settings, String deviceSettings, String deviceTutorial) {
    return 'Wiederholen Sie diese Tour jederzeit unter $settings › $deviceSettings › $deviceTutorial';
  }

  @override
  String get createAKey => 'Schlüssel erstellen';

  @override
  String get successfullyConnectedNotion => 'Erfolgreich mit Notion verbunden!';

  @override
  String get captureMicInterruptedDetail =>
      'Ein Anruf oder eine andere App nutzt das Mikrofon, daher kann Omi gerade nicht zuhören. Omi macht von selbst weiter, sobald das Mikrofon frei ist. Alles bisher Aufgenommene ist sicher.';

  @override
  String get onboardingScreenCaptureDenied =>
      'Bildschirmaufnahme-Berechtigung verweigert. Bitte erteilen Sie die Berechtigung in Systemeinstellungen > Datenschutz & Sicherheit > Bildschirmaufnahme.';

  @override
  String get settingUp => 'Einrichten…';

  @override
  String get frequencyLow => 'Niedrig';

  @override
  String get sttFilterAuto => 'Automatisch';

  @override
  String get voiceQuestionNoSpeech => 'Das habe ich nicht verstanden — versuche es erneut';

  @override
  String get stripeRecommendation =>
      'Wenn Stripe in Ihrem Land verfügbar ist, empfehlen wir dringend, es für schnellere und einfachere Auszahlungen zu verwenden.';

  @override
  String get confirmed => 'Bestätigt!';

  @override
  String get deletePendingFilesWarning =>
      'Diese Aufnahmen wurden NICHT mit Ihrem Telefon synchronisiert und gehen dauerhaft verloren. Dies kann nicht rückgängig gemacht werden.';

  @override
  String get removeFilter => 'Filter Entfernen';

  @override
  String get downloadModel => 'Modell herunterladen';

  @override
  String get performanceReduced => 'Leistung um 5-10x reduziert. Verwenden Sie den Release-Modus.';

  @override
  String get hostRequired => 'Host ist erforderlich';

  @override
  String get alreadyBestValuePlan => 'Sie haben bereits den besten Wertplan. Keine Änderungen erforderlich.';

  @override
  String preparingModel(String model) {
    return 'Bereite $model vor…';
  }

  @override
  String get sendTranscript => 'Transkript senden';

  @override
  String get howItWorksTitle => 'Wie funktioniert es?';

  @override
  String get filterBySpeaker => 'Nach Sprecher filtern';

  @override
  String get addAppSubmittedSuccess => 'App erfolgreich eingereicht 🚀';

  @override
  String olderIphoneModelDetected(String model) {
    return 'Erkanntes Modell: $model (älter als iPhone XS). Die Erkennung auf dem Gerät kann langsamer sein.';
  }

  @override
  String get chatAppsWhatsAppTitle => 'WhatsApp kommt bald';

  @override
  String get syncingDeveloperSettings => 'Entwicklereinstellungen synchronisieren…';

  @override
  String get enterWifiPassword => 'WLAN-Passwort eingeben';

  @override
  String get failedToUpdateBaselineStatus => 'Diese Erinnerung konnte nicht aktualisiert werden. Versuche es erneut.';

  @override
  String get joinCommunity => 'Treten Sie der Community bei!';

  @override
  String get helpOrInquiries => 'Hilfe oder Anfragen?';

  @override
  String get enable => 'Aktivieren';

  @override
  String get deviceForgottenMessage => 'Gerät vergessen';

  @override
  String diagnosticsSincePairingSummary(int drops, int failed) {
    return 'Seit der Kopplung: $drops Abbrüche, $failed fehlgeschlagene Verbindungen.';
  }

  @override
  String confidenceSummaryConfirmed(String name) {
    return 'Omi erkennt die Stimme von $name, und du hast das bestätigt.';
  }

  @override
  String migratingToProtection(String level) {
    return 'Migration zum $level-Schutz…';
  }

  @override
  String get managePlan => 'Plan verwalten';

  @override
  String get synced => 'Synchronisiert';

  @override
  String get failedToMoveConversations => 'Unterhaltungen konnten nicht verschoben werden';

  @override
  String get monthMar => 'Mär';

  @override
  String get timePM => 'PM';

  @override
  String get debugLogsAutoDelete => 'Wird nach 3 Tagen automatisch gelöscht.';

  @override
  String get linkedIn => 'LinkedIn';

  @override
  String speakerLabelVoiceDetail(String state, String name) {
    String _temp0 = intl.Intl.selectLogic(
      state,
      {
        'learned': 'Omi erkennt $name beim nächsten Mal.',
        'pending': 'Das dauert ein paar Sekunden.',
        'disabled': 'Aktiviere in den Einstellungen das Speichern von Stimmen, damit Omi $name erkennen kann.',
        'other': 'Omi braucht mehr klare Sprache von $name und versucht es weiter.',
      },
    );
    return '$_temp0';
  }

  @override
  String get authUnexpectedError => 'Unerwarteter Fehler bei der Anmeldung, bitte versuchen Sie es erneut';

  @override
  String disconnectAppMessage(String appName) {
    return 'Sie können $appName jederzeit erneut verbinden.';
  }

  @override
  String get pendantPausedResumesWhenYouFinish => 'Anhänger pausiert · läuft weiter, wenn du fertig bist';

  @override
  String get sendToSupport => 'An Support senden';

  @override
  String get fairUseBudgetExhausted => 'Tägliches Transkriptionslimit erreicht';

  @override
  String evidenceAutoConfirmed(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Du hast $count automatische Markierungen bestätigt',
      one: 'Du hast 1 automatische Markierung bestätigt',
    );
    return '$_temp0';
  }

  @override
  String get otaWifiConnecting => 'Verbindung mit WLAN…';

  @override
  String starFilterLabel(int count) {
    return '$count Stern';
  }

  @override
  String get disconnectDevice => 'Gerät trennen';

  @override
  String get installsCount => 'Installationen';

  @override
  String captureStatusWithSource(String status, String source) {
    return '$status · $source';
  }

  @override
  String get pairingTitleOmiGlass => 'Omi Glass einschalten';

  @override
  String get setActive => 'Als aktiv festlegen';

  @override
  String get showShortConversations => 'Kurze Unterhaltungen anzeigen';

  @override
  String get reviewNotSure => 'Nicht sicher';

  @override
  String msgCameraAccessError(String error) {
    return 'Fehler beim Zugriff auf die Kamera: $error';
  }

  @override
  String get quickActionAskOmi => 'Frag Omi irgendetwas';

  @override
  String get dreamReportTimedOut => 'Beim Zeitlimit gestoppt';

  @override
  String get chooseYourLanguage => 'Wählen Sie Ihre Sprache';

  @override
  String get unableToDetermineFirmwareVersion => 'Aktuelle Firmware-Version konnte nicht ermittelt werden';

  @override
  String get addAppEnterConversationPrompt => 'Bitte geben Sie eine Konversations-Eingabeaufforderung für Ihre App ein';

  @override
  String get readScope => 'Lesen';

  @override
  String get selectALanguage => 'Wählen Sie eine Sprache';

  @override
  String get otherTemplates => 'Andere Vorlagen';

  @override
  String get speechProfileTopicGoal => 'Was ist dein langfristiges Ziel?';

  @override
  String get rayBanMetaMicPickerTitle => 'Ray-Ban Meta-Mikrofon auswählen';

  @override
  String meetingNotesSubject(String title) {
    return 'Notizen: $title';
  }

  @override
  String get feedbackTitleMissingFeatures => 'Welche Funktionen fehlen dir?';

  @override
  String get modelReady => 'Modell bereit';

  @override
  String todayAtTime(String time) {
    return 'Heute um $time';
  }

  @override
  String get deleteAccountPermanently => 'Konto endgültig löschen';

  @override
  String get updateStripeDetails => 'Stripe-Details aktualisieren';

  @override
  String get voiceResponseHeadphonesOnly => 'Nur Kopfhörer';

  @override
  String get deviceOnboardingEndConversation => 'Gespräch beenden';

  @override
  String openingApp(String appName) {
    return 'Öffne $appName…';
  }

  @override
  String get submitAppPublicDescription =>
      'Ihre App wird überprüft und veröffentlicht. Sie können sie sofort verwenden, auch während der Überprüfung!';

  @override
  String connectToAppTitle(String appName) {
    return 'Mit $appName verbinden';
  }

  @override
  String get timeout10MinutesDesc => 'Unterhaltung nach 10 Minuten Stille beenden';

  @override
  String get googleCalendar => 'Google Kalender';

  @override
  String get initializing => 'Initialisierung…';

  @override
  String get noMessagesYet => 'Noch keine Nachrichten!\nWarum starten Sie keine Unterhaltung?';

  @override
  String get chatAppsLoadFailed => 'Chat-Apps konnten nicht geladen werden. Bitte versuche es erneut.';

  @override
  String get tasksLater => 'Später';

  @override
  String get speakerLabelUnknown => 'Unbekannt';

  @override
  String get appTitle => 'Omi';

  @override
  String get noModelDownloadRequired =>
      'Die native Sprach-Engine Ihres Geräts wird verwendet. Kein Modell-Download erforderlich.';

  @override
  String get authenticationFailed => 'Authentifizierung fehlgeschlagen. Bitte versuchen Sie es erneut.';

  @override
  String get defaultRepoSaved => 'Standard-Repository gespeichert';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'Fehler bei der Miniaturbildauswahl: $error';
  }

  @override
  String get captureRecordingSeparateTitle => 'Diese Aufnahme trennen?';

  @override
  String get back => 'Zurück';

  @override
  String get preparingAudio => 'Bereite Audio vor';

  @override
  String get noAutoMemories => 'Noch keine automatischen Erinnerungen';

  @override
  String get allDone => 'Alles erledigt!';

  @override
  String get msgReadingMemories => 'Lese deine Erinnerungen…';

  @override
  String get worksOnDesktop => 'Funktioniert auf dem Desktop';

  @override
  String get displayOptions => 'Anzeigeoptionen';

  @override
  String get installApp => 'App installieren';

  @override
  String get stop => 'Stopp';

  @override
  String get grantPermissions => 'Berechtigungen erteilen';

  @override
  String get at => 'um';

  @override
  String get checkInternetConnection => 'Bitte überprüfen Sie Ihre Internetverbindung';

  @override
  String get actionItems => 'Aufgaben';

  @override
  String get nextDay => 'Nächster Tag';

  @override
  String get syncStatusFailed => 'Fehlgeschlagen — auf Wiederholen tippen';

  @override
  String get saveCredentials => 'Anmeldedaten speichern';

  @override
  String get peopleRecent => 'Kürzlich';

  @override
  String get bringYourOwn => 'Bring Your Own';

  @override
  String get cancelConsequenceBattery => '7x mehr Batterieverbrauch (Verarbeitung auf dem Gerät)';

  @override
  String get copyMessage => 'Nachricht kopieren';

  @override
  String get annualSubscriptionStarts => 'Ihr 12-monatiges Jahresabonnement beginnt automatisch nach der Abbuchung';

  @override
  String get deleteImportedData => 'Importierte Daten löschen';

  @override
  String get chatLimitReachedUpgrade => 'Chatlimit erreicht. Upgraden für mehr Nachrichten.';

  @override
  String get whatsNew => 'Was ist neu';

  @override
  String get omiTraining => 'Omi-Training';

  @override
  String get wrappedMyBuddies => 'Meine Freunde';

  @override
  String get keepRecording => 'Weiter aufnehmen';

  @override
  String get suggestedEvent => 'Vorgeschlagen';

  @override
  String get name => 'Name';

  @override
  String get screenRecordingDescription =>
      'Omi benötigt die Berechtigung zur Bildschirmaufzeichnung, um System-Audio von Ihren browserbasierten Besprechungen zu erfassen.';

  @override
  String get improveConnectionTitle => 'Verbindung verbessern';

  @override
  String get syncProcessingBackgroundHint => 'Das läuft im Hintergrund weiter — du kannst diesen Bildschirm verlassen.';

  @override
  String get wrappedYourTopDaysBadge => 'Deine Top-Tage';

  @override
  String get noPeopleYet => 'Noch keine Personen';

  @override
  String summaryGeneratedForDate(String date) {
    return 'Zusammenfassung erstellt für $date';
  }

  @override
  String get searchTranscriptOrSummary => 'Transkript oder Zusammenfassung durchsuchen';

  @override
  String get memoryDetailsTitle => 'Erinnerung';

  @override
  String get chatPersonality => 'Chat-Persönlichkeit';

  @override
  String get release => 'Loslassen';

  @override
  String removeVocabularyWord(String word) {
    return '$word entfernen';
  }

  @override
  String get onboardingLanguage => 'Sprache';

  @override
  String get wrappedYouDidItEmoji => 'Du hast es geschafft! 🎉';

  @override
  String get syncInProgress => 'Synchronisierung läuft';

  @override
  String get wrappedCouldntStopTalkingAbout => 'Konnte nicht aufhören zu reden über';

  @override
  String get chooseSummarizationApp => 'Zusammenfassungs-App auswählen';

  @override
  String etaLabel(String time) {
    return 'ETA: $time';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'Wenn Sie $item öffentlich machen, kann es von allen genutzt werden';
  }

  @override
  String get phoneCallsUpsellFeature2 => 'Automatische Anrufzusammenfassungen und Aufgaben';

  @override
  String get freemiumLimitsIntro =>
      'Omi ist kostenlos, aber die Gratisversion hat Grenzen, die dein Erlebnis beeinflussen:';

  @override
  String get nameLabel => 'Name';

  @override
  String get shortConversationThresholdSubtitle =>
      'Unterhaltungen, die kürzer als dies sind, werden ausgeblendet, sofern oben nicht aktiviert';

  @override
  String get captureMicInUseElsewhere => 'Mikrofon von anderer App belegt';

  @override
  String get selectChatAssistant => 'Chat-Assistenten auswählen';

  @override
  String get transferRequired => 'Übertragung erforderlich';

  @override
  String get unlimitedChatThisMonth => 'Unbegrenzte Chatnachrichten diesen Monat';

  @override
  String get backgroundModeUnavailable =>
      'Der Hintergrundmodus ist nicht verfügbar, weil kein kompatibles Gerät verbunden ist. Verbinde ein Omi-, OpenGlass- oder Friend Pendant-Gerät, um diese Funktion zu nutzen.';

  @override
  String get importConfiguration => 'Konfiguration importieren';

  @override
  String get e2eeTradeoff1 => '• Einige Funktionen wie externe App-Integrationen können deaktiviert sein.';

  @override
  String get chatAppsCodeExpiredTitle => 'Dieser Code ist abgelaufen';

  @override
  String get responseSchema => 'Antwortschema';

  @override
  String get wrappedBestMoments => 'Beste Momente';

  @override
  String get noAppsExternalAccess => 'Keine installierten Apps haben externen Zugriff auf Ihre Daten.';

  @override
  String modelReadyWithName(String model) {
    return 'Modell bereit ($model)';
  }

  @override
  String get appDisabledWebhookFailures =>
      'Ihr Endpunkt ist 72 Stunden lang fehlgeschlagen, daher wurden die Zustellungen gestoppt.';

  @override
  String reviewConversationCount(int count) {
    return 'Gespräche: $count';
  }

  @override
  String get reviewChangesLoadFailed => 'Letzte Änderungen konnten nicht geladen werden.';

  @override
  String get reviewOpenConversation => 'Gespräch';

  @override
  String get voiceRecordingFound => 'Aufnahme gefunden';

  @override
  String durationAgo(String duration) {
    return 'vor $duration';
  }

  @override
  String get onboardingWelcomeToOmi => 'Willkommen bei Omi';

  @override
  String get deleteActionItemConfirmTitle => 'Aufgabe löschen';

  @override
  String get importantBillingInfo => 'Wichtige Abrechnungsinformationen:';

  @override
  String get pending => 'Ausstehend';

  @override
  String get onboardingRatingPromptTitle => 'Gefällt dir Omi?';

  @override
  String get savePayPalDetails => 'PayPal-Details speichern';

  @override
  String appDisabledLastError(String error) {
    return 'Letzter Fehler: $error.';
  }

  @override
  String get iveInstalledAndOpenedTheApp => 'Ich habe die App installiert und geöffnet';

  @override
  String get pricePlaceholder => '0.00';

  @override
  String get triggerTranscriptProcessed => 'Transkript verarbeitet';

  @override
  String get decisions => 'Entscheidungen';

  @override
  String get conversationProcessingFailedMessage => 'Dieses Gespräch konnte nicht verarbeitet werden.';

  @override
  String get continueText => 'Fortfahren';

  @override
  String get signInWithGoogle => 'Mit Google anmelden';

  @override
  String firmwareFlashTarget(String deviceName) {
    return 'Gerät: $deviceName';
  }

  @override
  String get deleteYourAccountAndAllData => 'Löschen Sie Ihr Konto und alle Daten';

  @override
  String get provider => 'Anbieter';

  @override
  String get people => 'Personen';

  @override
  String get perMonth => '/ Monat';

  @override
  String get monthFeb => 'Feb';

  @override
  String get fridayAbbr => 'Fr';

  @override
  String get thankYouForFeedback => 'Vielen Dank für Ihr Feedback!';

  @override
  String get usageBestYear => 'Best year';

  @override
  String get addAppFillRequiredFields => 'Bitte füllen Sie alle erforderlichen Felder korrekt aus';

  @override
  String get deviceOnboardingVoiceReplyOffDescription =>
      'Die Antworten bleiben auf dem Bildschirm. Es wird nichts gesprochen.';

  @override
  String get logs => 'Protokolle';

  @override
  String get exportConversations => 'Unterhaltungen exportieren';

  @override
  String get memoryReviewDropped => 'Aus deinen Erinnerungen entfernt.';

  @override
  String get appearanceLight => 'Hell';

  @override
  String get moneyEarned => 'Verdient';

  @override
  String get permissionsAndTriggers => 'Berechtigungen & Auslöser';

  @override
  String get discardRecordingTitle => 'Aufnahme verwerfen?';

  @override
  String get wrappedMinutesLabel => 'Minuten';

  @override
  String get voiceRestoredToast => 'Omi fragt eventuell wieder nach dieser Stimme';

  @override
  String get locationAccess => 'Standortzugriff';

  @override
  String get deleteAllMemories => 'Alle Erinnerungen löschen';

  @override
  String get deleteAccountTitle => 'Konto löschen';

  @override
  String get selectFile => 'Datei auswählen';

  @override
  String get answerTheCallFrom => 'Nehmen Sie den Anruf an von';

  @override
  String get unpairDeviceDialogTitle => 'Gerät entkoppeln';

  @override
  String exportedToPlatform(String platform) {
    return 'Nach $platform exportiert';
  }

  @override
  String syncCardDownloadPercent(int percent) {
    return '$percent%';
  }

  @override
  String get deviceOnboardingVoiceReplyPreviewPlaying => 'Deine letzte Antwort wird abgespielt...';

  @override
  String get fromSd => 'Von SD';

  @override
  String get goodSampleInstructions =>
      '1. Stellen Sie sicher, dass Sie an einem ruhigen Ort sind.\n2. Sprechen Sie klar und natürlich.\n3. Stellen Sie sicher, dass Ihr Gerät in seiner natürlichen Position an Ihrem Hals ist.\n\nSobald es erstellt ist, können Sie es jederzeit verbessern oder erneut machen.';

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
      'Um eine Unterhaltung zu favorisieren, öffnen Sie sie und tippen Sie auf das Sternsymbol im Kopfbereich.';

  @override
  String get pairingTitleOmiDevkit => 'Omi DevKit in den Kopplungsmodus versetzen';

  @override
  String sttPrimaryLanguageUnsupported(String language, String fallback) {
    return 'Dieser Anbieter unterstützt $language nicht und verwendet daher $fallback.';
  }

  @override
  String get premiumMinutesMonth =>
      '300 Premium-Minuten pro Monat. Wähle „Auf dem Gerät“ für unbegrenzte kostenlose Transkription. ';

  @override
  String get firmwareEnsureBattery => 'Stellen Sie sicher, dass Ihr Gerät 15% Batterie hat.';

  @override
  String get actionItemDescriptionHint => 'Was muss getan werden?';

  @override
  String get yourScore => 'Ihr Score';

  @override
  String failedToStartAuth(String appName) {
    return 'Authentifizierung für $appName fehlgeschlagen';
  }

  @override
  String get actionReadTasks => 'Aufgaben lesen';

  @override
  String get keepSyncing => 'Weiter synchronisieren';

  @override
  String get overdue => 'Überfällig';

  @override
  String get chatAppsProblemUnavailable => 'Chat-Apps sind für dein Konto noch nicht verfügbar.';

  @override
  String get tapSyncToStart => 'Tippen Sie auf Sync zum Starten';

  @override
  String get emptyDoneMessage => 'Noch keine erledigten Elemente';

  @override
  String get recordOptionsTip => 'Tipp: Tippe auf den Pfeil an der Aufnahmetaste, um ein Telefonat aufzunehmen.';

  @override
  String get setupQuestionProfession => '1. Was machst du beruflich?';

  @override
  String get deviceInfoSection => 'Geräteinformationen';

  @override
  String get teachOmiYourVoice => 'Bringen Sie Omi Ihre Stimme bei';

  @override
  String get addYourFirstMemory => 'Füge deine erste Erinnerung hinzu';

  @override
  String get priceLabel => 'PREIS';

  @override
  String get high => 'Hoch';

  @override
  String estimatedSizeWithValue(String size) {
    return 'Geschätzte Größe: ~$size MB';
  }

  @override
  String cleanUpUnsureCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count Personen, bei denen Omi unsicher ist',
      one: '1 Person, bei der Omi unsicher ist',
    );
    return '$_temp0';
  }

  @override
  String get makeAllMemoriesPrivate => 'Alle Erinnerungen privat machen';

  @override
  String get raybanMetaWaitingForMetaAI =>
      'Schließen Sie die Verbindung in der Meta AI App ab und kehren Sie dann hierher zurück.';

  @override
  String get revokeAuthorization => 'Autorisierung widerrufen';

  @override
  String get confidenceToReachConfirmed => 'So erreichst du „Bestätigt“';

  @override
  String get syncCardRateLimited => 'Nutzungslimit erreicht — die Synchronisierung wird automatisch fortgesetzt';

  @override
  String get reviewStopClip => 'Clip stoppen';

  @override
  String get chatAppsWhatOmiDoes => 'Was Omi in Chat-Apps macht';

  @override
  String get resume => 'Fortsetzen';

  @override
  String get defaultSpace => 'Standard-Space';

  @override
  String get multipleSpeakersDetected => 'Mehrere Sprecher erkannt';

  @override
  String evidenceAutoCorrected(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Du hast $count automatische Markierungen anderen Personen zugeordnet',
      one: 'Du hast 1 automatische Markierung einer anderen Person zugeordnet',
    );
    return '$_temp0';
  }

  @override
  String get voiceMatchPossible => 'Mögliche Übereinstimmung';

  @override
  String get checkBoxToConfirm =>
      'Aktivieren Sie das Kontrollkästchen, um zu bestätigen, dass Sie verstehen, dass das Löschen Ihres Kontos dauerhaft und unwiderruflich ist.';

  @override
  String get quicklyPopulateResponse => 'Schnell mit bekanntem Anbieter-Antwortformat ausfüllen';

  @override
  String get monthJul => 'Jul';

  @override
  String get failedToInitializeCallService => 'Anrufdienst konnte nicht initialisiert werden';

  @override
  String get connectAction => 'Verbinden';

  @override
  String get onDeviceModelDeleted => 'Modell gelöscht';

  @override
  String get micGainDescNeutral => 'Neutral - ausgewogene Aufnahme';

  @override
  String get chatOfflineHint => 'Du bist offline. Stelle die Verbindung wieder her, um Nachrichten zu senden.';

  @override
  String get onboardingLocationGrantInSettings =>
      'Bitte erteilen Sie die Standortberechtigung in Einstellungen > Datenschutz & Sicherheit > Ortungsdienste';

  @override
  String get invalidSetupInstructionsUrl => 'Ungültige URL für Einrichtungsanweisungen';

  @override
  String get msgCameraPermissionDenied =>
      'Kameraberechtigung verweigert. Bitte erlauben Sie den Zugriff auf die Kamera';

  @override
  String get dataAndPrivacy => 'Daten & Datenschutz';

  @override
  String get deviceNotCompatible => 'Gerät nicht kompatibel';

  @override
  String get pairingDescAppleWatch =>
      'Installieren und öffnen Sie die Omi-App auf Ihrer Apple Watch und tippen Sie dann auf Verbinden in der App.';

  @override
  String get speechProfileTopicLocation => 'Wo wohnst du?';

  @override
  String get makeAllPrivate => 'Alle Erinnerungen privat machen';

  @override
  String get capabilityNotification => 'Benachrichtigung';

  @override
  String get captureAudioSavedTranscribesLater => 'Audio gespeichert, wird später transkribiert';

  @override
  String get wrappedTopPhrases => 'Top 5 Phrasen';

  @override
  String get transcribeLaterPaused => 'Pausiert – Audio wird nicht aufgenommen';

  @override
  String get deviceOnboardingTurnOnTitle => 'Einschalten';

  @override
  String get keyNamePlaceholder => 'z.B. Meine App-Integration';

  @override
  String get languageTitle => 'Sprache';

  @override
  String get statusVerifiedLabel => 'Verifiziert';

  @override
  String get storageLocationPhoneMemory => 'Telefon (Speicher)';

  @override
  String get you => 'Sie';

  @override
  String get listeningTranscriptWillAppear => 'Hört zu… hier erscheint ein Transkript.';

  @override
  String get askSuggestNotice => 'Was ist Omi aufgefallen?';

  @override
  String get safelyBackedUp => 'Erstellte Gespräche';

  @override
  String get folderName => 'Ordnername';

  @override
  String get categorySocialEntertainment => 'Soziales & Unterhaltung';

  @override
  String speechProfileOwnerTitle(String name) {
    return 'Stimmprofil von $name';
  }

  @override
  String get reviewAddedSuccessfully => 'Bewertung erfolgreich hinzugefügt 🚀';

  @override
  String get fairUseSpeechUsage => 'Sprachnutzung';

  @override
  String get visibilitySubtitle => 'Steuern Sie, welche Unterhaltungen in Ihrer Liste erscheinen';

  @override
  String get wrappedWinLabelUpper => 'SIEG';

  @override
  String timeCompactMinsAndSecs(int mins, int secs) {
    return '${mins}m ${secs}s';
  }

  @override
  String get phoneCallsUpsellSubtitle =>
      'Telefoniere über Omi und erhalte Echtzeit-Transkription, automatische Zusammenfassungen und mehr.';

  @override
  String get sessionExpiredSignInAgain => 'Deine Sitzung ist abgelaufen — melde dich erneut an.';

  @override
  String get newPersonEllipsis => 'Neue Person…';

  @override
  String get sharePeriodToday => 'Heute hat Omi:';

  @override
  String get premiumMinutesInfo =>
      '300 Premium-Minuten pro Monat. Wähle „Auf dem Gerät“ für unbegrenzte kostenlose Transkription.';

  @override
  String get notConnectedStatus => 'Nicht verbunden';

  @override
  String get authorizeSavingRecordings => 'Speichern von Aufnahmen autorisieren';

  @override
  String get thinking => 'Denkt nach';

  @override
  String get unpairDialogTitle => 'Gerät entkoppeln';

  @override
  String get batteryFullyChargedBody => 'Dein Omi-Gerät ist vollständig geladen. Du kannst es jetzt ausstecken!';

  @override
  String get speakerTagPromptRejectedToast => 'Zuordnung entfernt';

  @override
  String get phone => 'Telefon';

  @override
  String get chatAppsVoiceNotes => 'Sprachnachrichten';

  @override
  String get deviceOnboardingStatusDisconnected => 'Getrennt';

  @override
  String get debugModeDetected => 'Debug-Modus erkannt';

  @override
  String get failedToSaveDefaultRepo => 'Standard-Repository konnte nicht gespeichert werden';

  @override
  String get showCompletedTasks => 'Erledigte anzeigen';

  @override
  String deviceStorageUsedOfTotal(String used, String total) {
    return '$used von $total belegt';
  }

  @override
  String get recordingsNotSynced => 'Sie haben Aufnahmen, die noch nicht synchronisiert sind.';

  @override
  String get performanceWarning => 'Leistungswarnung';

  @override
  String get submitAppPrivateDescription =>
      'Ihre App wird überprüft und Ihnen privat zur Verfügung gestellt. Sie können sie sofort verwenden, auch während der Überprüfung!';

  @override
  String get copyTranscript => 'Transkript kopieren';

  @override
  String get providing => 'Bereitstellen';

  @override
  String get findDeviceNoneMessage => 'Schalte es ein und halte es nah an dein Telefon.';

  @override
  String get wrappedLetsHitRewind => 'Lass uns dein Jahr zurückspulen';

  @override
  String deviceRamBelowMinimum(String ram) {
    return 'Erkannter RAM: $ram GB. Empfohlenes Minimum: 4 GB.';
  }

  @override
  String get addOrChangePaymentMethod => 'Zahlungsmethode hinzufügen oder ändern';

  @override
  String get omiAppName => 'Omi';

  @override
  String get enableBluetooth => 'Bluetooth aktivieren';

  @override
  String get privacyNotice => 'Datenschutzhinweis';

  @override
  String get manufacturer => 'Hersteller';

  @override
  String get byContinuingYouAgree => 'Indem Sie fortfahren, stimmen Sie unseren ';

  @override
  String dataProtectedWithSettings(String level) {
    return 'Deine Daten sind jetzt mit den neuen $level-Einstellungen geschützt.';
  }

  @override
  String get selectSpaceInWorkspace => 'Wählen Sie einen Space in Ihrem Arbeitsbereich';

  @override
  String get copyKey => 'Schlüssel kopieren';

  @override
  String get password => 'Passwort';

  @override
  String estimatedSize(String size) {
    return 'Geschätzte Größe: ~$size MB';
  }

  @override
  String monthsFreeBadge(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count Monate gratis',
      one: '1 Monat gratis',
    );
    return '$_temp0';
  }

  @override
  String get chatAppsNotAvailableYet => 'Noch nicht verfügbar';

  @override
  String estimatedTimeRemaining(String time) {
    return 'Geschätzt: $time verbleibend';
  }

  @override
  String get syncCardBackendBusy =>
      'Omis Server sind ausgelastet — deine Aufnahmen werden synchronisiert, sobald wieder Kapazität verfügbar ist';

  @override
  String get speakerTagPromptTitle => 'Hilf Omi, Stimmen zu erkennen';

  @override
  String get playFromHere => 'Ab hier abspielen';

  @override
  String get entityProject => 'Projekt';

  @override
  String get permissionNotGrantedYet =>
      'Berechtigung noch nicht erteilt. Bitte stellen Sie sicher, dass Sie den Mikrofonzugriff erlaubt und die App auf Ihrer Uhr erneut geöffnet haben.';

  @override
  String get e2eeTradeoff2 => '• Wenn Sie Ihr Passwort verlieren, können Ihre Daten nicht wiederhergestellt werden.';

  @override
  String get exportConfiguration => 'Konfiguration exportieren';

  @override
  String get recordWith => 'Aufnehmen mit';

  @override
  String get greetingEvening => 'Guten Abend';

  @override
  String deletePhoneNumberConfirm(String phoneNumber) {
    return '$phoneNumber loeschen?';
  }

  @override
  String get deviceOnboardingAskQuestionTitle => 'Stell Omi eine Frage';

  @override
  String get appNamePlaceholder => 'Meine fantastische App';

  @override
  String get tapPlayToResume => 'Tippen Sie auf Abspielen, um fortzufahren';

  @override
  String get dueDate => 'Fälligkeitsdatum';

  @override
  String get appearanceSystem => 'System';

  @override
  String get invalidEmailError => 'Bitte geben Sie eine gültige E-Mail ein';

  @override
  String get highResourceUsage => 'Hohe Ressourcennutzung';

  @override
  String get voiceAndPeople => 'Stimme & Personen';

  @override
  String get customizationSection => 'Anpassung';

  @override
  String get failedToCancelSubscription => 'Kündigung des Abonnements fehlgeschlagen. Bitte versuchen Sie es erneut.';

  @override
  String get later => 'Später';

  @override
  String get wrappedTasksGenerated => 'Aufgaben erstellt';

  @override
  String get personalizingExperience => 'Ihre Erfahrung wird personalisiert…';

  @override
  String get syncAvailable => 'Synchronisierung verfügbar';

  @override
  String chatGreeting(String name) {
    return 'Hallo $name, frag mich alles';
  }

  @override
  String get phoneCallSettingsTitle => 'Anrufeinstellungen';

  @override
  String get remoteDeviceTerminated => 'Entferntes Gerät hat die Verbindung beendet';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'Fehler beim Öffnen der Dateiauswahl: $message';
  }

  @override
  String get actionItemDeleted => 'Aufgabe gelöscht';

  @override
  String get couldNotLoadMemories => 'Erinnerungen konnten nicht geladen werden';

  @override
  String get generateDescription => 'Beschreibung generieren';

  @override
  String get privateLabel => 'Privat';

  @override
  String get deviceOnboardingMuteUnmute => 'Stummschalten / Aktivieren';

  @override
  String get day => 'Tag';

  @override
  String get submitAppQuestion => 'App einreichen?';

  @override
  String get usageWords => 'Words';

  @override
  String get failedToConnectClickUp => 'Verbindung zu ClickUp fehlgeschlagen';

  @override
  String get selectZipFileToImport => 'Wählen Sie die .zip-Datei zum Importieren!';

  @override
  String timeSecsPlural(int count) {
    return '$count Sek';
  }

  @override
  String get wasThisHelpful => 'War das hilfreich?';

  @override
  String get msgLearningMemories => 'Lerne aus deinen Erinnerungen…';

  @override
  String get onboardingScreenCaptureRequired =>
      'Bildschirmaufnahme-Berechtigung ist für die Systemtonaufnahme erforderlich.';

  @override
  String evidenceManualLabels(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Von dir in $count Gesprächen zugeordnet',
      one: 'Von dir in 1 Gespräch zugeordnet',
    );
    return '$_temp0';
  }

  @override
  String get transferCancelled => 'Übertragung abgebrochen';

  @override
  String get sttModelSpeed => 'Geschwindigkeit';

  @override
  String get fairUsePolicy => 'Faire Nutzung';

  @override
  String get phoneStorage => 'Telefonspeicher';

  @override
  String get deviceOnboardingEndConversationDesc => 'Aktuelles Gespräch speichern und beenden';

  @override
  String get proceedAnyway => 'Trotzdem fortfahren';

  @override
  String get overview => 'Übersicht';

  @override
  String get deviceOnboardingGoodJob => 'Gut gemacht!';

  @override
  String get delete => 'Löschen';

  @override
  String get connectAiAssistantsToYourData => 'KI-Assistenten mit deinen Daten verbinden';

  @override
  String get startFresh => 'Neu anfangen';

  @override
  String get deviceOnboardingStatusConnectedDone => 'Verbunden!';

  @override
  String get filterInstalled => 'Installiert';

  @override
  String get mergingStatus => 'Zusammenführen…';

  @override
  String get successfullyConnected => 'Erfolgreich verbunden!';

  @override
  String get permissionCreateConversations => 'Gespräche erstellen';

  @override
  String get cancelConsequencePhoneCalls => 'Keine Echtzeit-Transkription von Telefonaten';

  @override
  String get feedbackReasonSummaryOther => 'Etwas anderes';

  @override
  String get oAuth => 'OAuth';

  @override
  String get notEnoughSpace => 'Warnung: Nicht genug Speicherplatz!';

  @override
  String get feedbackTitleTooExpensive => 'Welcher Preis wäre passend für dich?';

  @override
  String get secureEncryption => 'Sichere Verschlüsselung';

  @override
  String get rating2PlusStars => '2+ Sterne';

  @override
  String get chatAppsOpenMessagesAgain => 'Nachrichten erneut öffnen';

  @override
  String fairUseBudgetResetsAt(String time) {
    return 'Zurücksetzung $time';
  }

  @override
  String get addVocabularyDescription => 'Fügen Sie Wörter hinzu, die Omi bei der Transkription erkennen soll.';

  @override
  String get whisperModelSizeMedium => 'Mittel';

  @override
  String get wrappedMyBuddiesLabel => 'MEINE FREUNDE';

  @override
  String get memoryGraph => 'Erinnerungsgraph';

  @override
  String get paste => 'Einfügen';

  @override
  String get failedToRefreshGitHubStatus => 'GitHub-Verbindungsstatus konnte nicht aktualisiert werden.';

  @override
  String get feedbackSubtitleMissingFeatures => 'Wir bauen ständig — das hilft uns bei der Priorisierung.';

  @override
  String get itemApp => 'App';

  @override
  String get pairingDescFriendPendant =>
      'Drücken Sie den Knopf am Anhänger, um ihn einzuschalten. Er wechselt automatisch in den Kopplungsmodus.';

  @override
  String get appDisabledGeneric => 'Sie wurde von Omi deaktiviert.';

  @override
  String get noSummaryForApp =>
      'Keine Zusammenfassung für diese App verfügbar. Probieren Sie eine andere App für bessere Ergebnisse.';

  @override
  String get deleteProcessed => 'Verarbeitete löschen';

  @override
  String get chatBlockOpenInGoals => 'In Zielen öffnen';

  @override
  String get micGainDescModerate => 'Leise - für mäßigen Lärm';

  @override
  String get defaultRepository => 'Standard-Repository';

  @override
  String get statusPending => 'Ausstehend';

  @override
  String get referralProgram => 'Empfehlungsprogramm';

  @override
  String get authFailedToLinkApple => 'Verknüpfung mit Apple fehlgeschlagen, bitte versuchen Sie es erneut.';

  @override
  String modelNameWithFile(String model) {
    return 'Modell: $model';
  }

  @override
  String get deviceOnboardingTurnOnSubtitle => 'Drücke die Taste, um es wieder einzuschalten';

  @override
  String get previewAndScreenshots => 'Vorschau und Screenshots';

  @override
  String get recordingOfflineTranscriptWillCatchUp =>
      'Offline-Aufnahme — das Transkript wird nachgeholt, sobald Sie wieder online sind.';

  @override
  String get accessibilityDescription =>
      'Omi benötigt die Berechtigung für Barrierefreiheit, um zu erkennen, wann Sie Zoom-, Meet- oder Teams-Besprechungen in Ihrem Browser beitreten.';

  @override
  String setDefaultAppContent(String appName) {
    return '$appName als Standard-App für Zusammenfassungen festlegen?\n\nDiese App wird automatisch für alle zukünftigen Gesprächszusammenfassungen verwendet.';
  }

  @override
  String get switchRequiresRestart => 'Wechsel erfordert Neustart der App';

  @override
  String get wrappedWinHeader => 'Sieg';

  @override
  String get forYou => 'Für dich';

  @override
  String get filterCategory => 'Kategorie';

  @override
  String get createPersonHint =>
      'Erstellen Sie eine neue Person und trainieren Sie Omi, deren Stimme ebenfalls zu erkennen!';

  @override
  String get loadingMemories => 'Erinnerungen werden geladen…';

  @override
  String get selectedPaymentMethod => 'Ausgewählte Zahlungsmethode';

  @override
  String get email => 'E-Mail';

  @override
  String get transcriptionUnavailableRecordingContinues =>
      'Transkriptionen sind nicht verfügbar, die Aufnahme läuft auf dem Gerät weiter und wird später verarbeitet';

  @override
  String get noLogsYet =>
      'Noch keine Protokolle. Nimm etwas auf, um Anfragen an deinen Transkriptionsanbieter zu sehen.';

  @override
  String get failedToStartAuthentication => 'Authentifizierung konnte nicht gestartet werden';

  @override
  String peopleCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count Personen',
      one: '1 Person',
    );
    return '$_temp0';
  }

  @override
  String get enterBackendUrlError => 'Bitte geben Sie die Backend-URL ein';

  @override
  String get playbackBackToCurrent => 'Zurück zum Aktuellen';

  @override
  String clockSkewWarning(int minutes) {
    return 'Die Uhr deines Geräts weicht um ~$minutes Min. ab. Überprüfe deine Datums- und Uhrzeiteinstellungen.';
  }

  @override
  String get stopThese => 'Diese stoppen';

  @override
  String get yes => 'Ja';

  @override
  String get recognizingOthers => 'Andere erkennen 👀';

  @override
  String get transcriptionLanguageDesc => 'Wählen Sie die Sprache für die Sprachtranskription';

  @override
  String aboutMinutesRemaining(int minutes) {
    return 'Etwa $minutes Minuten verbleibend';
  }

  @override
  String get deleteFlowReasonSubtitle => 'Dein Feedback hilft uns, Omi für alle zu verbessern.';

  @override
  String get processedFilesDeleted => 'Verarbeitete Dateien gelöscht';

  @override
  String get autoLanguageDetection => 'Automatische Spracherkennung';

  @override
  String bulkExportPartial(int success, int total, String platform) {
    return '$success von $total nach $platform exportiert';
  }

  @override
  String get actionItemDescriptionCannotBeEmpty => 'Aufgabenbeschreibung darf nicht leer sein';

  @override
  String get deleteReasonFoundAlternative => 'Ich nutze etwas anderes';

  @override
  String get noContentToDisplay => 'Kein Inhalt zum Anzeigen';

  @override
  String get feedbackReasonRecordingWrongSpeaker => 'Falscher Sprecher';

  @override
  String get create => 'Erstellen';

  @override
  String get greatJobAlmostThere => 'Toll gemacht, Sie sind fast fertig';

  @override
  String get captureStorageAlmostFull => 'Speicher fast voll';

  @override
  String chatAppsConnectedOn(String date) {
    return 'Verbunden am $date';
  }

  @override
  String get wrappedAGreatDay => 'Ein toller Tag';

  @override
  String get backendUrlSavedSuccess => 'Backend-URL erfolgreich gespeichert!';

  @override
  String get speakerTagPromptIsThisYou => 'Warst du das?';

  @override
  String get knowledgeGraphDeletedSuccess => 'Wissensgraph erfolgreich gelöscht';

  @override
  String timeMinsPlural(int count) {
    return '$count Min';
  }

  @override
  String get peopleNotHeardYet => 'Noch nicht gehört';

  @override
  String get chatStarterDoDifferently => 'Was könnte ich heute anders machen?';

  @override
  String get fairUseAboutBody =>
      'Omi ist für persönliche Gespräche, Meetings und Live-Interaktionen gemacht. Die Nutzung wird an der Sprechzeit gemessen, nicht an der Verbindungszeit. Liegt deine Nutzung weit über dem normalen persönlichen Gebrauch, erhältst du zuerst eine Warnung. Anhaltend starke Nutzung kann die Transkription verlangsamen oder einschränken.';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'Bitte wählen Sie Ihre Hauptsprache';

  @override
  String get manualDisconnect => 'Manuelle Trennung';

  @override
  String get googleCalendarNotConnected => 'Google Kalender nicht verbunden';

  @override
  String get soCloseJustLittleMore => 'So nah dran, nur noch ein bisschen';

  @override
  String appDataAccessMessage(String appName) {
    return '$appName erhält deine Gespräche, Erinnerungen und Aufnahmen auf dem Server seines Entwicklers. Omi ist nicht dafür verantwortlich, wie diese Daten dort verwendet werden.';
  }

  @override
  String savePercent(int percent) {
    return '~$percent% sparen';
  }

  @override
  String get deviceDisconnectedNotificationBody => 'Bitte verbinden Sie sich erneut, um Ihr Omi weiter zu nutzen.';

  @override
  String get openConversation => 'Unterhaltung öffnen';

  @override
  String get frequencyDescMaximum => 'Jede nützliche Verbindung, bis zu 9 pro Tag';

  @override
  String get readChatRepliesAloud => 'Chat-Antworten laut vorlesen';

  @override
  String get microphonePermissionRequired => 'Mikrofonberechtigung ist für Sprachaufnahmen erforderlich.';

  @override
  String get updatePayPalAccountDetails => 'Aktualisieren Sie Ihre PayPal-Kontodaten';

  @override
  String get connectionTimeout => 'Verbindungszeitüberschreitung';

  @override
  String get micGainDescHigh => 'Hoch - für entfernte oder leise Stimmen';

  @override
  String get permissionsInfoNote => 'R = Lesen, W = Schreiben. Standardmäßig nur Lesen, wenn nichts ausgewählt.';

  @override
  String timeHoursAndMins(int hours, int mins) {
    return '$hours Stunden $mins Min';
  }

  @override
  String get keepMyAccount => 'Mein Konto behalten';

  @override
  String get transcriptionLanguage => 'Transkriptionssprache';

  @override
  String dreamReportStats(int records, int tokens) {
    return '$records Elemente gelesen · $tokens Tokens';
  }

  @override
  String get editPerson => 'Person bearbeiten';

  @override
  String get whatWeTrack => 'Was wir erfassen';

  @override
  String get micGainDescVeryHigh => 'Sehr hoch - für sehr leise Quellen';

  @override
  String timeCompactDays(int count) {
    return '${count}T';
  }

  @override
  String get reviewTaskField => 'Aufgabe';

  @override
  String reviewConfirmPerson(String name) {
    return '$name bestätigen';
  }

  @override
  String get downloadingFromDevice => 'Wird vom Gerät heruntergeladen';

  @override
  String get conversationTranscriptCopiedToClipboard => 'Gesprächstranskript in Zwischenablage kopiert';

  @override
  String get continueAction => 'Weiter';

  @override
  String conversationsMovedCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count Unterhaltungen verschoben',
      one: '1 Unterhaltung verschoben',
    );
    return '$_temp0';
  }

  @override
  String get signInButton => 'Anmelden';

  @override
  String get startUpdate => 'Update starten';

  @override
  String get wrappedTopPhrasesLabelUpper => 'TOP PHRASEN';

  @override
  String get total => 'Gesamt';

  @override
  String get deleting => 'Löschen…';

  @override
  String get skipBack10Seconds => '10 Sekunden zurück';

  @override
  String get setupAnswerAllQuestions => 'Du hast noch nicht alle Fragen beantwortet! 🥺';

  @override
  String get planUpgradeScheduledMessage =>
      'Upgrade geplant! Dein Monatsplan läuft bis zum Ende deines Abrechnungszeitraums weiter und wechselt dann automatisch zum Jahresplan.';

  @override
  String get needHelpChatWithUs => 'Hilfe benötigt? Schreiben Sie uns';

  @override
  String get chatBlockUnavailable => 'Nicht mehr verfügbar';

  @override
  String estimatedMinutes(int count) {
    return '~$count Minute(n)';
  }

  @override
  String get failedToSaveMemory => 'Speichern fehlgeschlagen. Bitte überprüfen Sie Ihre Verbindung.';

  @override
  String get deleteReasonTakingBreak => 'Ich mache nur eine Pause';

  @override
  String get reviewAndManageConversations => 'Überprüfe und verwalte deine aufgenommenen Unterhaltungen';

  @override
  String get actionReadMemories => 'Erinnerungen lesen';

  @override
  String deletePinnedPersonMessage(String name) {
    return '$name ist angeheftet. Die Stimmproben werden entfernt, Omi erkennt die Person nicht mehr, und frühere Transkripte zeigen sie als unbenannten Sprecher. Das lässt sich nicht rückgängig machen.';
  }

  @override
  String get speakerTagPromptHintOwner => 'Deine Antwort kennzeichnet nur den abgespielten Ausschnitt.';

  @override
  String get onboardingNotificationDeniedNotifications =>
      'Benachrichtigungsberechtigung verweigert. Bitte erteilen Sie die Berechtigung in Systemeinstellungen > Mitteilungen.';

  @override
  String appDisabledNamed(String appName) {
    return '$appName deaktiviert';
  }

  @override
  String get tabOld => 'Alt';

  @override
  String deviceOnboardingVoiceReplyStatusHeadphonesConnected(String device) {
    return '$device verbunden. Omi wird hier sprechen.';
  }

  @override
  String get deletePendingFiles => 'Ausstehende Aufnahmen löschen';

  @override
  String get wrappedWin => 'Sieg';

  @override
  String get removeFromAllFolders => 'Aus allen Ordnern entfernen';

  @override
  String get deviceIdLabel => 'Geräte-ID';

  @override
  String get upgradeAlreadyScheduled => 'Ihr Upgrade auf den Jahresplan ist bereits geplant';

  @override
  String get openCall => 'Anruf öffnen';

  @override
  String get rateAndReviewThisApp => 'Bewerte und rezensiere diese App';

  @override
  String get getStarted => 'Loslegen';

  @override
  String get deviceOnboardingVoiceReplyAlwaysDescription =>
      'Verwendet den Telefonlautsprecher, wenn keine Kopfhörer angeschlossen sind.';

  @override
  String chooseExportDestination(int count) {
    return '$count Element(e) exportieren nach…';
  }

  @override
  String get onboardingSetupSubtitle => 'Gib Omi einen Moment zum Personalisieren';

  @override
  String welcomeBack(String name) {
    return 'Willkommen zurück, $name';
  }

  @override
  String get dreamReportIdle => 'Noch nichts Neues zu prüfen.';

  @override
  String get cleanUpTitle => 'Aufräumen';

  @override
  String get deleteProcessedFiles => 'Verarbeitete Dateien löschen';

  @override
  String get no => 'Nein';

  @override
  String get msgPhotoError => 'Fehler beim Aufnehmen des Fotos. Bitte versuchen Sie es erneut.';

  @override
  String get search => 'Suchen';

  @override
  String get downloadingFirmware => 'Firmware wird heruntergeladen';

  @override
  String get phoneKeypadTab => 'Tastatur';

  @override
  String get pendantFullSyncBlocked =>
      'Der Speicher deines Pendants ist voll und es befindet sich noch im Aufnahmemodus, daher kann das gespeicherte Audio nicht übertragen werden. Drücke die Taste am Pendant, um die Aufnahme zu stoppen, und synchronisiere dann erneut.';

  @override
  String get deleteSelectedItemsTitle => 'Ausgewählte Elemente löschen';

  @override
  String get appPrivacyAndTerms => 'App-Datenschutz und -Bedingungen';

  @override
  String get omiTranscription => 'Omi Transkription';

  @override
  String get editConversation => 'Gespräch bearbeiten';

  @override
  String moveConversationsTo(int count) {
    return '$count Gespräche verschieben nach:';
  }

  @override
  String get signOutConfirmation =>
      'Du musst dich erneut anmelden, um deine Gespräche zu sehen. Dein gekoppeltes Gerät und deine App-Einstellungen bleiben auf diesem Telefon.';

  @override
  String get wrappedObsessionsLabel => 'OBSESSIONEN';

  @override
  String get jumpToLatestMessage => 'Zur neuesten Nachricht springen';

  @override
  String get failedStatus => 'Fehlgeschlagen';

  @override
  String get notNow => 'Nicht jetzt';

  @override
  String transferFailedMessage(String error) {
    return 'Übertragung fehlgeschlagen: $error';
  }

  @override
  String get customVocabularyTitle => 'Benutzerdefiniertes Vokabular';

  @override
  String get internetRequired => 'Internet erforderlich';

  @override
  String get waitingForData => 'Warte auf Daten…';

  @override
  String get noRecordingsYet => 'Noch keine Aufnahmen';

  @override
  String get answerWithYourVoice => 'Antworte mit deiner Stimme:';

  @override
  String personUnpinnedToast(String name) {
    return '$name nicht mehr angeheftet';
  }

  @override
  String get stopRecording => 'Aufnahme stoppen';

  @override
  String get off => 'Aus';

  @override
  String get memoryThisPhone => 'Dieses Telefon';

  @override
  String get thirteenMonthsCoverage =>
      'Sie erhalten insgesamt 13 Monate Abdeckung (aktueller Monat + 12 Monate jährlich)';

  @override
  String failedToCreateApiKey(String error) {
    return 'Fehler beim Erstellen des Anbieter-API-Schlüssels: $error';
  }

  @override
  String get tipStableInternet => 'Stabiles Internet beschleunigt Cloud-Uploads';

  @override
  String get tasksMarkComplete => 'Als erledigt markiert';

  @override
  String get reviewAddTask => 'Aufgabe hinzufügen';

  @override
  String get submitReply => 'Antwort senden';

  @override
  String get captureRecoveryBanner => 'Omi sendet keinen Ton — zum erneuten Verbinden tippen';

  @override
  String get analyzing => 'Analysiere…';

  @override
  String get sttModelFaster => 'Schneller';

  @override
  String get fairUseLoadError =>
      'Der Status der fairen Nutzung konnte nicht geladen werden. Bitte versuchen Sie es erneut.';

  @override
  String get places => 'Orte';

  @override
  String get voiceMatchWeak => 'Schwache Übereinstimmung';

  @override
  String captureOfflineBufferingFor(int minutes) {
    return 'Offline, wird zwischengespeichert · $minutes Min.';
  }

  @override
  String get onboardingWhatIKnowAboutYouTitle => 'Das weiß ich über dich';

  @override
  String get raybanMetaPhotoRequested => 'Foto angefordert – es wird in Ihrem Gespräch erscheinen.';

  @override
  String get verifyYourNumber => 'Verifizieren Sie Ihre Nummer';

  @override
  String get deleteFlowConfirmSubtitle => 'Das kann nicht rückgängig gemacht werden, auch nicht vom Support.';

  @override
  String get submitAppTermsAgreement =>
      'Mit der Einreichung dieser App stimme ich den Nutzungsbedingungen und der Datenschutzrichtlinie von Omi AI zu';

  @override
  String get stripeSecureDescription => 'Stripe gewährleistet sichere und pünktliche Überweisungen Ihrer App-Einnahmen';

  @override
  String get categoryProductivity => 'Produktivität';

  @override
  String chatWithAppName(String appName) {
    return 'Chat mit $appName';
  }

  @override
  String get enableCloudStorage => 'Cloud-Speicher aktivieren';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl => 'Ungültige Webhook-URL für Echtzeit-Transkription';

  @override
  String get wrappedShow => 'SERIE';

  @override
  String get speakTranscribeSummarize => 'Sprechen. Transkribieren. Zusammenfassen.';

  @override
  String get pricingPaid => 'Kostenpflichtig';

  @override
  String get successfullyConnectedAsana => 'Erfolgreich mit Asana verbunden!';

  @override
  String get rating => 'Bewertung';

  @override
  String get chatQuotaExceededReply =>
      'Du hast dein monatliches Limit erreicht. Upgrade, um ohne Einschränkungen mit Omi weiterzuchatten.';

  @override
  String get pendantIsListeningTitle => 'Dein Anhänger hört zu';

  @override
  String get usageBestDay => 'Best day';

  @override
  String get personWhyConfidence => 'Warum?';

  @override
  String get permissionDescCreateConversations => 'Diese App kann neue Gespräche erstellen.';

  @override
  String get reviewSpellingCustom => 'Selbst eingeben';

  @override
  String resetsInHours(int count) {
    return 'Wird in $count Stunden zurückgesetzt';
  }

  @override
  String get reviewAction => 'Prüfen';

  @override
  String get submitRequest => 'Anfrage senden';

  @override
  String get phoneCalls => 'Telefonanrufe';

  @override
  String get actionItemsTab => 'Aufgaben';

  @override
  String get record => 'Aufnehmen';

  @override
  String get noReviewsFound => 'Keine Bewertungen gefunden';

  @override
  String get oauth => 'OAuth';

  @override
  String get urlCopied => 'URL kopiert';

  @override
  String get actionItemReminderTitle => 'Omi-Erinnerung';

  @override
  String sharedTasksAdded(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count Aufgaben zu deiner Liste hinzugefügt',
      one: '1 Aufgabe zu deiner Liste hinzugefügt',
    );
    return '$_temp0';
  }

  @override
  String get contactsPermissionRequiredForSms => 'Kontaktberechtigung ist erforderlich, um per SMS zu teilen';

  @override
  String get apiKeyRevokedSuccessfully => 'API-Schlüssel erfolgreich widerrufen';

  @override
  String get authorizationSuccessful => 'Autorisierung erfolgreich!';

  @override
  String get unpinAction => 'Lösen';

  @override
  String get syncingStatus => 'Synchronisierung';

  @override
  String get audioFormatLabel => 'Audioformat';

  @override
  String get phoneSelectCountryTitle => 'Land auswählen';

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'Top $percentile% Nutzer';
  }

  @override
  String get phoneContactsTab => 'Kontakte';

  @override
  String get reply => 'Antworten';

  @override
  String get openingShareSheet => 'Öffne Freigabeblatt…';

  @override
  String get creatingAppIcon => 'App-Symbol wird erstellt…';

  @override
  String get deviceOnboardingStartSpeaking => 'Fang an zu sprechen…';

  @override
  String get wrappedAHilariousMoment => 'Ein lustiger Moment';

  @override
  String get paidApp => 'Kostenpflichtige App';

  @override
  String get wrappedStruggleHeader => 'Kampf';

  @override
  String get speakerTagPromptDontKnow => 'Jemand, den ich nicht kenne';

  @override
  String get wrappedStarting => 'Starte…';

  @override
  String get getButton => 'Laden';

  @override
  String get syncCustomSttWarningTitle => 'Synchronisierung nutzt Omi-Transkription';

  @override
  String get download => 'Herunterladen';

  @override
  String get addScreenshot => 'Screenshot hinzufügen';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return 'Verbindung zu $serviceName fehlgeschlagen: $error';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'Bitte erneut verbinden, um Ihr $deviceName weiter zu verwenden.';
  }

  @override
  String get configureDailySummaryDigest => 'Konfigurieren Sie Ihre tägliche Aufgabenübersicht';

  @override
  String get showShortConversationsDesc => 'Unterhaltungen anzeigen, die kürzer als der Schwellenwert sind';

  @override
  String participantsSummaryUncounted(String name) {
    return '$name und weitere';
  }

  @override
  String fairUseBudgetUsed(String used, String limit) {
    return '${used}m / ${limit}m';
  }

  @override
  String get add => 'Hinzufügen';

  @override
  String get disconnect => 'Trennen';

  @override
  String get enterApiKey => 'Geben Sie Ihren API-Schlüssel ein';

  @override
  String get msgMaxFilesLimit => 'Sie können nur bis zu 4 Dateien auswählen';

  @override
  String get space => 'Leertaste';

  @override
  String get upgrade => 'Upgrade';

  @override
  String get tapToView => 'Tippen zum Anzeigen';

  @override
  String get summaryTemplate => 'Zusammenfassungsvorlage';

  @override
  String get chatAppsWaitingTitle => 'Warte auf deine Nachricht';

  @override
  String yesterdayAtTime(String time) {
    return 'Gestern um $time';
  }

  @override
  String get cancel => 'Abbrechen';

  @override
  String get checkingAppleWatch => 'Apple Watch wird überprüft…';

  @override
  String syncCardDownloadPercentSpeed(int percent, String speed) {
    return '$percent% · $speed KB/s';
  }

  @override
  String get finalTouches => 'Letzte Schliffe';

  @override
  String get weekdaySat => 'Sa';

  @override
  String get fairUseWeekly => 'Wöchentlich';

  @override
  String get invalidPaymentUrl => 'Ungültige Zahlungs-URL';

  @override
  String get transcriptionSlowerOnDevice => 'Die Transkription auf dem Gerät kann auf diesem Gerät langsamer sein.';

  @override
  String get noListsInSpace => 'Keine Listen in diesem Space gefunden';

  @override
  String get deviceDiagnostics => 'Gerätediagnose';

  @override
  String get askAnything => 'Frag irgendetwas';

  @override
  String confidenceMeterLabel(String level) {
    return 'Sicherheit: $level';
  }

  @override
  String get permissionReadTasks => 'Aufgaben lesen';

  @override
  String get skipForNow => 'Vorerst überspringen';

  @override
  String get setupCompletedUrl => 'URL für abgeschlossene Einrichtung';

  @override
  String get saySomething => 'Sag etwas…';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get chatAppsEntryTitle => 'Mit Omi chatten';

  @override
  String get chatAppsTelegramStepOpen => 'Tippe unten auf „Telegram öffnen“';

  @override
  String get pleaseEnterValidPayPalMeLink => 'Bitte geben Sie einen gültigen PayPal.me-Link ein';

  @override
  String get syncFlowIntro =>
      'Aufnahmen werden von deinem Gerät auf dieses Telefon übertragen und lokal gespeichert und dann auf Omis Server hochgeladen, wo sie transkribiert und in Gespräche umgewandelt werden.';

  @override
  String get cantFindDeviceHint =>
      'Gerät nicht gefunden? Achte darauf, dass es eingeschaltet und in der Nähe deines Telefons ist, und suche erneut.';

  @override
  String get tryAdjustingFilter => 'Versuche, deine Suche oder den Filter anzupassen';

  @override
  String get failedConnectionsRecent => 'Fehlgeschlagene Verbindungen (letzte 7 Tage)';

  @override
  String get captureSourceCall => 'Anruf';

  @override
  String get storageLocationPhone => 'Telefon';

  @override
  String get voiceMatchClose => 'Enge Übereinstimmung';

  @override
  String get reviewChangeUndone => 'Rückgängig gemacht. Omi wiederholt das nicht von selbst.';

  @override
  String get tasksNoProject => 'Kein Projekt';

  @override
  String get dataAccessNotice => 'Datenzugriffshinweis';

  @override
  String deviceStorageFree(String free) {
    return '$free frei';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'Bereits nach $platform exportiert';
  }

  @override
  String get recapDeletedSnackbar => 'Zusammenfassung gelöscht';

  @override
  String get apiUrlRequired => 'API-URL ist erforderlich';

  @override
  String get getOmiUnlimitedFree =>
      'Erhalten Sie Omi Unlimited kostenlos, indem Sie Ihre Daten zum Training von KI-Modellen beitragen.';

  @override
  String get wrappedShare => 'Teilen';

  @override
  String get tasksTomorrow => 'Morgen';

  @override
  String get chatAppsShowInAppOn => 'Ein: Sie erscheinen in der Omi-App als schreibgeschützte Chats.';

  @override
  String get errorActivatingAppIntegration =>
      'Fehler beim Aktivieren der App. Falls es sich um eine Integrations-App handelt, stelle sicher, dass die Einrichtung abgeschlossen ist.';

  @override
  String get readChatRepliesAloudDescription => 'Spricht nur, wenn die Sprachantwort es zulässt.';

  @override
  String get addDueDate => 'Fälligkeitsdatum hinzufügen';

  @override
  String get translated => 'übersetzt';

  @override
  String get dontAskAgain => 'Nicht erneut fragen';

  @override
  String get fullAccessScope => 'Vollzugriff';

  @override
  String get firmwareUpdated => 'Firmware aktualisiert';

  @override
  String get deviceOnboardingVoiceReplyPreviewThroughPhoneSpeaker => 'Über den Telefonlautsprecher';

  @override
  String get prompt => 'Prompt';

  @override
  String get dreamReportDeletedItem => 'Gelöschtes Element';

  @override
  String chatAppsDisconnectChannel(String app) {
    return '$app trennen';
  }

  @override
  String get appleHealthDeniedBody =>
      'Omi hat keine Berechtigung, deine Apple Health-Daten zu lesen. Aktiviere sie unter iOS Einstellungen → Datenschutz & Sicherheit → Health → Omi.';

  @override
  String endsOnDate(String date) {
    return 'Endet am $date';
  }

  @override
  String get searchSettings => 'Einstellungen durchsuchen';

  @override
  String get pairingDescNeoOne =>
      'Halten Sie die Ein-/Aus-Taste gedrückt, bis die LED blinkt. Das Gerät wird erkennbar sein.';

  @override
  String get checkingNextSevenDays => 'Überprüfe die nächsten 7 Tage';

  @override
  String get confidenceLikely => 'Wahrscheinlich';

  @override
  String get appleHealthFeatureChatTitle => 'Chatte über deine Gesundheit';

  @override
  String get loadingDevices => 'Geräte werden geladen…';

  @override
  String get writeSomething => 'Schreiben Sie etwas';

  @override
  String syncCardProgressOf(int current, int total) {
    return '$current von $total';
  }

  @override
  String get unableToOpenWatchApp =>
      'Apple Watch-App konnte nicht geöffnet werden. Öffne die Watch-App manuell auf deiner Apple Watch und installiere Omi aus dem Bereich \"Verfügbare Apps\".';

  @override
  String get dreamReportWouldFix => 'Würde korrigieren';

  @override
  String get doubleTap => 'Doppeltippen';

  @override
  String get speakerTagPromptSomeoneElse => 'Jemand anderes…';

  @override
  String get cancelTransfer => 'Übertragung abbrechen';

  @override
  String get capabilityExternalIntegration => 'Externe Integration';

  @override
  String get sttLanguageFollowsPrimary => 'Folgt deiner Hauptsprache';

  @override
  String get wrappedCringeMomentTitle => 'Peinlicher Moment';

  @override
  String get allRecordingsSynced => 'Alle Aufnahmen sind synchronisiert';

  @override
  String get reviewConfirm => 'Bestätigen';

  @override
  String get checkBackLaterForNewApps => 'Schauen Sie später nach neuen Apps';

  @override
  String get referAFriend => 'Einen Freund empfehlen';

  @override
  String cleanUpLead(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other:
          'Omi ist bei diesen $count Personen unsicher. Die meisten sind Namen, die aus Transkripten falsch verstanden wurden. Entferne das Häkchen bei allen, die du behalten möchtest.',
      one: 'Omi ist bei dieser Person unsicher. Entferne das Häkchen, um sie zu behalten.',
    );
    return '$_temp0';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return '$item privat machen?';
  }

  @override
  String get chatQuotaSubtitle => 'AI chat messages used with Omi this month.';

  @override
  String get failedTryAgain => 'Fehlgeschlagen? Erneut versuchen';

  @override
  String get deleteAllFiles => 'Alle Aufnahmen löschen';

  @override
  String get onDeviceModelDownloadSuccess => 'Modell heruntergeladen';

  @override
  String get reviewNoChangesTitle => 'Noch keine Änderungen';

  @override
  String get useMobileAppToCapture => 'Verwende deine mobile App, um Audio aufzunehmen';

  @override
  String get setYourName => 'Namen festlegen';

  @override
  String get tasksGroupByDate => 'Nach Datum gruppieren';

  @override
  String get diagnosticsLast7Days => 'Letzte 7 Tage';

  @override
  String get deviceOnboardingStatusConnected => 'Verbunden';

  @override
  String get actionItemCreatedSuccessfully => 'Aufgabe erfolgreich erstellt';

  @override
  String get thursdayAbbr => 'Do';

  @override
  String get wifiConfiguration => 'WLAN-Konfiguration';

  @override
  String get cancelReasonFoundAlternative => 'Alternative gefunden';

  @override
  String get process => 'Verarbeiten';

  @override
  String get help => 'Hilfe';

  @override
  String get rollbackConfirmTitle => 'Firmware zurücksetzen?';

  @override
  String get visibility => 'Sichtbarkeit';

  @override
  String get evidenceNotHeard => 'Noch in keinem Gespräch gehört';

  @override
  String get messageReported => 'Nachricht erfolgreich gemeldet.';

  @override
  String get readyToChat => '✨ Bereit zum Chatten!';

  @override
  String get tryDifferentFilter => 'Versuche einen anderen Filter';

  @override
  String get header => 'Überschrift';

  @override
  String get wrappedBestHeader => 'Beste';

  @override
  String get memoryDontUse => 'Nicht verwenden';

  @override
  String get appStore => 'App Store';

  @override
  String get deleteMeetingScreenshotMessage =>
      'Das Bildschirmfoto wird aus der Notiz dieses Meetings entfernt. Dies kann nicht rückgängig gemacht werden.';

  @override
  String get categoryShopping => 'Einkaufen';

  @override
  String get voiceResponseOff => 'Aus';

  @override
  String get bluetoothNeeded =>
      'Omi benötigt Bluetooth, um sich mit Ihrem Wearable zu verbinden. Bitte aktivieren Sie Bluetooth und versuchen Sie es erneut.';

  @override
  String get googleCalendarComingSoon => 'Google Kalender Integration kommt bald!';

  @override
  String get max => 'Max';

  @override
  String get homeScreen => 'Startbildschirm';

  @override
  String get chatAppsTelegramStepStart => 'Tippe in deinem Chat mit Omi auf „Starten“';

  @override
  String get greetingAfternoon => 'Guten Tag';

  @override
  String get unpair => 'Entkoppeln';

  @override
  String get diagnosticsVerdictReconnects => 'Verbindet sich selbst wieder';

  @override
  String get macOsCalendar => 'macOS Kalender';

  @override
  String get onboardingSetupStepLanguage => 'Transkription wird auf deine Sprache abgestimmt';

  @override
  String get mcpOAuthSetup =>
      'Fügen Sie auf claude.ai einen benutzerdefinierten Konnektor hinzu und fügen Sie die Server-URL ein. Wenn Claude nach einer erweiterten OAuth-Client-ID fragt, verwenden Sie den untenstehenden Wert und lassen Sie das Secret leer — verwenden Sie niemals Ihren MCP-API-Schlüssel als OAuth-Secret.';

  @override
  String get wednesdayAbbr => 'Mi';

  @override
  String get selectAudioInput => 'Audioeingang auswählen';

  @override
  String get deviceDisconnectedMessage => 'Ihr Omi wurde getrennt 😔';

  @override
  String get reprocessConversation => 'Unterhaltung neu verarbeiten';

  @override
  String get goal => 'ZIEL';

  @override
  String mergeConversationsMessage(int count) {
    return 'Dies wird $count Unterhaltungen zu einer zusammenfassen. Alle Inhalte werden zusammengeführt und neu generiert.';
  }

  @override
  String get everyXSeconds => 'Alle x Sekunden';

  @override
  String get chatAppsLocked => 'Erfordert Omi Pro';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl => 'Ungültige Webhook-URL für erstellte Konversation';

  @override
  String get secureAuthViaAppleId => 'Sichere Authentifizierung über Apple ID';

  @override
  String connectingToDeviceName(String deviceName) {
    return 'Verbindung mit $deviceName wird hergestellt...';
  }

  @override
  String get listeningSubtitle => 'Gesamtzeit, die Omi aktiv zugehört hat.';

  @override
  String get capturing => 'Aufnahme läuft';

  @override
  String get enterWifiNetworkName => 'WLAN-Netzwerknamen eingeben';

  @override
  String get noAppsAvailable => 'Keine Apps verfügbar';

  @override
  String get installingFirmware => 'Firmware wird installiert';

  @override
  String get transferToPhone => 'Auf Telefon übertragen';

  @override
  String get voiceResponseMode => 'Sprachantwort';

  @override
  String get messageCopied => '✨ Nachricht in Zwischenablage kopiert';

  @override
  String get discardRecordingMessage =>
      'Deine Sprachprobe ist noch nicht gespeichert. Wenn du jetzt gehst, wird sie verworfen.';

  @override
  String chatAppsIMessageBody(String code) {
    return 'Hallo Omi, Verknüpfungscode $code';
  }

  @override
  String get failedToRefreshWhoopStatus => 'Whoop-Verbindungsstatus konnte nicht aktualisiert werden.';

  @override
  String get youreOnAnnualPlan => 'Sie haben den Jahresplan';

  @override
  String timeHoursPlural(int count) {
    return '$count Stunden';
  }

  @override
  String get usageOnline => 'Online-Nutzung';

  @override
  String get validPortRequired => 'Gültiger Port ist erforderlich';

  @override
  String get howItWorks => 'So funktioniert es';

  @override
  String get viewTemplate => 'Vorlage anzeigen';

  @override
  String get dreamReportNothingFound => 'Nichts zu beheben';

  @override
  String get personTalkTime => 'Sprechzeit';

  @override
  String get evidenceNoVoice => 'Noch keine Stimmprobe';

  @override
  String get makeMyAppPublic => 'Meine App öffentlich machen';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'Bluetooth-Berechtigungsstatus: $status. Bitte überprüfen Sie die Systemeinstellungen.';
  }

  @override
  String get noRecordings => 'Keine Aufnahmen';

  @override
  String get usageChatThisMonth => 'Chat this month';

  @override
  String get addAppEnterChatPrompt => 'Bitte geben Sie eine Chat-Eingabeaufforderung für Ihre App ein';

  @override
  String daysAgo(int count) {
    return 'vor $count Tagen';
  }

  @override
  String get processing => 'Wird verarbeitet';

  @override
  String get deviceOnboardingStatusTurningOff => 'Wird ausgeschaltet…';

  @override
  String get newTag => 'NEU';

  @override
  String get permissionDescReadTasks => 'Diese App kann auf deine Aufgaben zugreifen.';

  @override
  String get time => 'Zeit';

  @override
  String get recording => 'Aufnahme';

  @override
  String get speakerTagPromptWhoIsThis => 'Wer ist das?';

  @override
  String chatUsageMessagesNoLimit(String used) {
    return 'Chat: $used Nachrichten diesen Monat';
  }

  @override
  String get importantTradeoffs => 'Wichtige Kompromisse:';

  @override
  String get makeAllPublic => 'Alle Erinnerungen öffentlich machen';

  @override
  String get noSpeechDesc =>
      'Wir konnten keine Sprache erkennen. Bitte stellen Sie sicher, dass Sie mindestens 10 Sekunden und nicht mehr als 3 Minuten sprechen.';

  @override
  String get searchPartialFailure => 'Einige Ergebnisse konnten nicht geladen werden';

  @override
  String get prerecordedTranscript => 'Voraufgezeichnet';

  @override
  String get confirm => 'Bestätigen';

  @override
  String get statusCalling => 'Anrufen…';

  @override
  String get wrappedConvos => 'Gespräche';

  @override
  String get unresolvedSpeakersTitle => 'Über Sprecher-Bezeichnungen';

  @override
  String get writeYourReply => 'Schreibe deine Antwort…';

  @override
  String get localCopiesSection => 'Lokale Kopien';

  @override
  String get noSummaryYet => 'Noch keine Zusammenfassung';

  @override
  String get wrappedBiggestHeader => 'Größter';

  @override
  String get error => 'Fehler';

  @override
  String get deviceWillRestart => 'Dein Gerät wird neu gestartet.';

  @override
  String get consentDataMessage =>
      'Durch Fortfahren werden Ihre Gespräche, Aufnahmen und persönlichen Daten sicher auf unseren Servern gespeichert. Ihre Audioaufnahmen und Transkripte werden von KI-Diensten Dritter verarbeitet (einschließlich Deepgram für die Transkription und OpenAI für die Analyse), um Ihnen KI-gestützte Erkenntnisse zu liefern und alle App-Funktionen zu ermöglichen.';

  @override
  String get connectMacOsCalendar => 'Verbinden Sie Ihren lokalen macOS-Kalender';

  @override
  String get captureSourcePhoneMic => 'Telefonmikrofon';

  @override
  String get setupCompleted => 'Abgeschlossen';

  @override
  String get installOmiOnAppleWatchDescription =>
      'Um deine Apple Watch mit Omi zu verwenden, musst du zuerst die Omi-App auf deiner Uhr installieren.';

  @override
  String get toggleControlBar => 'Steuerleiste umschalten';

  @override
  String get onboardingBluetoothDeniedSystemPrefs =>
      'Bluetooth-Berechtigung verweigert. Bitte erteilen Sie die Berechtigung in den Systemeinstellungen.';

  @override
  String get syncCancelled => 'Synchronisierung abgebrochen';

  @override
  String get firmwareDisconnectUsb => 'USB trennen';

  @override
  String get processNow => 'Jetzt verarbeiten';

  @override
  String get appIdNotFoundError => 'App-ID nicht gefunden';

  @override
  String get editDueDate => 'Fälligkeitsdatum bearbeiten';

  @override
  String get home => 'Start';

  @override
  String get tasksOverdue => 'Überfällig';

  @override
  String get statusCompleted => 'Abgeschlossen';

  @override
  String get otaStarting => 'Update wird gestartet…';

  @override
  String get monthApr => 'Apr';

  @override
  String get conversationTasksEmptyMessage => 'Aufgaben aus dieser Unterhaltung erscheinen hier.';

  @override
  String get useDifferentAccount => 'Anderes Konto verwenden';

  @override
  String get reviewReasonNotUseful => 'Nicht nützlich';

  @override
  String get anonymousUser => 'Anonymer Benutzer';

  @override
  String get viewPlansDescription => 'Verwalten Sie Ihr Abonnement und sehen Sie Nutzungsstatistiken';

  @override
  String invalidJson(String error) {
    return 'Ungültiges JSON: $error';
  }

  @override
  String get deleteActionItem => 'Aufgabe löschen';

  @override
  String get confirmCancellation => 'Kündigung bestätigen';

  @override
  String get tapToDelete => 'Tippen zum Löschen';

  @override
  String get onTheCallEnterThisCode => 'Geben Sie diesen Code waehrend des Anrufs ein';

  @override
  String get stableFirmware => 'Stabile Firmware';

  @override
  String get triggerEvents => 'Auslösende Ereignisse';

  @override
  String get speakerTagPromptSaveVoicesTitle => 'Stimmen von Personen merken, die du benennst';

  @override
  String get syncedFilesDeleted => 'Synchronisierte Aufnahmen gelöscht';

  @override
  String get cloudStorageDesc =>
      'Nach dem Hochladen werden Ihre Aufnahmen verarbeitet und transkribiert. Gespräche sind innerhalb einer Minute verfügbar.';

  @override
  String get failedToUpdateFolder => 'Ordner konnte nicht aktualisiert werden';

  @override
  String dreamReportFound(int fixes, int asks) {
    String _temp0 = intl.Intl.pluralLogic(
      fixes,
      locale: localeName,
      other: '$fixes Korrekturen',
      one: '1 Korrektur',
    );
    String _temp1 = intl.Intl.pluralLogic(
      asks,
      locale: localeName,
      other: '$asks Vorschläge',
      one: '1 Vorschlag',
    );
    return '$_temp0 · $_temp1';
  }

  @override
  String get anotherPlatform => 'eine andere Plattform';

  @override
  String get wrappedTopPhrasesLabel => 'TOP PHRASEN';

  @override
  String get dataAccessWarning =>
      'Diese App greift auf Ihre Daten zu. Omi AI ist nicht verantwortlich dafür, wie Ihre Daten von dieser App verwendet, geändert oder gelöscht werden';

  @override
  String get pleaseCompleteAuthentication =>
      'Bitte schließen Sie die Authentifizierung in Ihrem Browser ab. Kehren Sie danach zur App zurück.';

  @override
  String get dailySummaryTitle => 'Tägliche Zusammenfassung';

  @override
  String get managePeople => 'Personen verwalten';

  @override
  String get dreamReportEmptyBody => 'Dream prüft etwa einmal pro Stunde, was sich in deinem Konto geändert hat.';

  @override
  String get couldNotOpenPaymentSettings =>
      'Zahlungseinstellungen konnten nicht geöffnet werden. Bitte versuchen Sie es erneut.';

  @override
  String get locationServiceDisabled => 'Standortdienst deaktiviert';

  @override
  String get understanding => 'Verstehen';

  @override
  String get recapDeleteFailed => 'Zusammenfassung konnte nicht gelöscht werden. Versuche es später erneut.';

  @override
  String get deleteKnowledgeGraphQuestion => 'Wissensgraph löschen?';

  @override
  String get wrappedYourBuddy => 'Dein Kumpel!';

  @override
  String chatAppsChatIn(String app) {
    return 'Chat in $app';
  }

  @override
  String get speechDurationDescription =>
      'Stellen Sie sicher, dass Sie mindestens 5 Sekunden und nicht mehr als 90 sprechen.';

  @override
  String get reviewReasonAlreadyDone => 'Schon erledigt';

  @override
  String get phoneSetupStep2Title => 'Geben Sie einen Verifizierungscode ein';

  @override
  String get tasksClearCompleted => 'Erledigte löschen';

  @override
  String get searchingForDevices => 'Suche nach Geräten';

  @override
  String get siriIndexSettingDescription =>
      'Allow Siri to find your conversations, memories, and tasks on this device. Turning this off removes them from Apple search.';

  @override
  String get markIncomplete => 'Als unvollständig markieren';

  @override
  String get onboardingBluetoothRequired =>
      'Bluetooth-Berechtigung ist erforderlich, um sich mit Ihrem Gerät zu verbinden.';

  @override
  String get searchAppsPlaceholder => 'Suche in 1500+ Apps';

  @override
  String get pleaseEnterName => 'Bitte geben Sie einen Namen ein';

  @override
  String get paymentMethodCharged =>
      'Ihre bestehende Zahlungsmethode wird automatisch belastet, wenn Ihr Monatsplan endet';

  @override
  String get allMemoriesAreNowPublic => 'Alle Erinnerungen sind jetzt öffentlich';

  @override
  String taskDueDate(String date) {
    return 'Fällig am $date';
  }

  @override
  String get pendantPausesUntilYouFinish => 'Anhänger pausiert, bis du fertig bist';

  @override
  String get failedToAuthorize => 'Autorisierung fehlgeschlagen. Bitte versuchen Sie es erneut.';

  @override
  String get mergeConversationsSuccessTitle => 'Gespräche erfolgreich zusammengeführt';

  @override
  String get peopleFilterNeedsVoice => 'Stimme fehlt';

  @override
  String get clickToBeginRecordingSystemAudio => 'Klicken Sie, um die Systemtonaufnahme zu starten';

  @override
  String get fairUseStageRestrict => 'Eingeschränkt';

  @override
  String get nextResult => 'Nächstes Ergebnis';

  @override
  String get chatAppsContactsApp => 'Kontakte';

  @override
  String get categoryEmotionalSupport => 'Emotionale Unterstützung';

  @override
  String get wrappedYourHeader => 'Deine';

  @override
  String get pendantPausesDuringCall => 'Anhänger pausiert während des Anrufs';

  @override
  String noConversationsOnDate(String date) {
    return 'Keine Gespräche am $date';
  }

  @override
  String get chatStarterYesterday => 'Was habe ich gestern gemacht?';

  @override
  String get entityNotRight => 'Stimmt nicht?';

  @override
  String get failedToCreateShareLink => 'Freigabelink konnte nicht erstellt werden';

  @override
  String get sync => 'Synchronisieren';

  @override
  String get micGainDescMax => 'Maximum - mit Vorsicht verwenden';

  @override
  String get sttNone => 'Keine';

  @override
  String get chatAppsCodeNote => 'Der Code funktioniert nur einmal und läuft in 10 Minuten ab.';

  @override
  String get aiGenAppCreatedSuccessfully => 'App erfolgreich erstellt!';

  @override
  String lastNEvents(int count) {
    return 'Letzte $count Ereignisse';
  }

  @override
  String get phoneDeleteButton => 'Loeschen';

  @override
  String get systemAudio => 'Systemaudio';

  @override
  String get checkOutMyMemoryGraph => 'Schau dir meinen Erinnerungsgraphen an!';

  @override
  String get feedbackTitleBatteryDrain => 'Erzähl uns von den Batterieproblemen';

  @override
  String get startCallRecording => 'Anrufaufnahme starten';

  @override
  String get monthlyPlanContinues => 'Ihr aktueller Monatsplan läuft bis zum Ende Ihres Abrechnungszeitraums weiter';

  @override
  String get syncStepUploadDesc => 'Deine Aufnahme wird an Omis Server gesendet';

  @override
  String get otaKeepNearby =>
      'Lass dein Gerät während des Updates eingeschaltet und in der Nähe und schließe die App nicht.';

  @override
  String get updatePayPalDetails => 'PayPal-Details aktualisieren';

  @override
  String get termsOfUse => 'Nutzungsbedingungen';

  @override
  String get apiKeyCreated => 'API-Schlüssel erstellt!';

  @override
  String get deviceOnboardingVoiceReplyPreviewIdle => 'Hören Sie Ihre letzte Antwort';

  @override
  String get starOngoing => 'Laufende Unterhaltung favorisieren';

  @override
  String get largeModelWarning =>
      'Dieses Modell ist groß und kann die App zum Absturz bringen oder sehr langsam laufen.\n\nsmall oder base wird empfohlen.';

  @override
  String get selectLanguage => 'Sprache auswählen';

  @override
  String get professionExecutive => 'Führungskraft';

  @override
  String get importFileTooLarge => 'Diese Datei ist zu groß für den Import.';

  @override
  String get updateRequiredTitle => 'Update erforderlich';

  @override
  String get syncStepBackedUp => 'Gespräch fertig';

  @override
  String get openWatchApp => 'Watch-App öffnen';

  @override
  String get keyNameLabel => 'SCHLÜSSELNAME';

  @override
  String bulkExportSuccess(int count, String platform) {
    return '$count nach $platform exportiert';
  }

  @override
  String get couldNotProcessSubscription => 'Das Abonnement konnte nicht verarbeitet werden. Bitte versuche es erneut.';

  @override
  String get memorizingYourVoice => 'Ihre Stimme wird gespeichert…';

  @override
  String get processingAudio => 'Verarbeite Audio';

  @override
  String get syncYourRecordings => 'Synchronisiere deine Aufnahmen';

  @override
  String get resetToDefault => 'Auf Standard zurücksetzen';

  @override
  String get deleteConversation => 'Gespräch löschen';

  @override
  String get flashCustomFirmwareDescription => 'Eigene Firmware-Builds flashen';

  @override
  String get deviceUpToDate => 'Ihr Gerät ist auf dem neuesten Stand';

  @override
  String get raybanMetaMusicPauseNote =>
      'Die Musik auf Ihrem Telefon pausiert, während das Mikrofon der Brille verwendet wird.';

  @override
  String get appleHealthNotAvailable => 'Apple Health ist auf diesem Gerät nicht verfügbar';

  @override
  String hints(String text) {
    return 'Hinweise: $text';
  }

  @override
  String get cloudProvider => 'Cloud-Anbieter';

  @override
  String get chooseAnyFileType => 'Beliebigen Dateityp wählen';

  @override
  String get reset => 'Zurücksetzen';

  @override
  String get automaticallyCreateNewPerson =>
      'Automatisch eine neue Person erstellen, wenn ein Name im Transkript erkannt wird.';

  @override
  String get timeout2Minutes => '2 Minuten';

  @override
  String get newMemory => '✨ Neue Erinnerung';

  @override
  String get chatAppsMoreComing => 'Weitere Apps folgen.';

  @override
  String get couldNotLoadKnowledgeGraph => 'Wissensgraph konnte nicht geladen werden';

  @override
  String get voiceSettingsAskToTagSubtitle => 'Ab und zu fragt Omi, wer in deinen letzten Gesprächen gesprochen hat';

  @override
  String get developer => 'Entwickler';

  @override
  String get connectionNeeded => '🌐 Verbindung erforderlich';

  @override
  String get helpAndAbout => 'Hilfe & Info';

  @override
  String get tasksNoDeadline => 'Keine Frist';

  @override
  String get yourDataIsProtected => 'Ihre Daten sind geschützt und unterliegen unserer ';

  @override
  String get confirmDeletion => 'Löschen bestätigen';

  @override
  String get speakerTagPromptClosestVoices => 'Ähnlichste Stimmen';

  @override
  String get quicklyPopulateRequest => 'Schnell mit bekanntem Anbieter-Anforderungsformat ausfüllen';

  @override
  String get exportTranscript => 'Transkript exportieren';

  @override
  String get resetsSoon => 'Wird bald zurückgesetzt';

  @override
  String get showPhoneCallButtonTitle => 'Anruf-Schaltfläche anzeigen';

  @override
  String get wrappedAChallenge => 'Eine Herausforderung';

  @override
  String get revokeKey => 'Schlüssel widerrufen';

  @override
  String get dailyRecaps => 'Tägliche Zusammenfassungen';

  @override
  String get processingConversationProgress => 'Gespräch wird verarbeitet…';

  @override
  String get freeMinutesMonth => '300 kostenlose Minuten/Monat inklusive. Unbegrenzt mit ';

  @override
  String get downloadWhisperModel => 'Bitte laden Sie vor dem Speichern ein Whisper-Modell herunter.';

  @override
  String get noMemoriesInCategories => 'Keine Erinnerungen in diesen Kategorien';

  @override
  String get checkingNextDays => 'Prüfe die nächsten 30 Tage';

  @override
  String get createAndSubmitNewApp => 'Neue App erstellen und einreichen';

  @override
  String get chatAppsInTheMeantime => 'In der Zwischenzeit';

  @override
  String get deleteFlowReasonTitle => 'Warum verlässt du uns?';

  @override
  String get tasksSelectAll => 'Alle auswählen';

  @override
  String get webhookUrl => 'Webhook-URL';

  @override
  String get selected => 'Ausgewählt';

  @override
  String get batteryDrainIncrease => 'Der Batterieverbrauch wird deutlich steigen.';

  @override
  String get dreamReportFixed => 'Korrigiert';

  @override
  String get failedToConnectClickUpRetry => 'Verbindung zu ClickUp fehlgeschlagen. Bitte versuchen Sie es erneut.';

  @override
  String get serverUrl => 'Server-URL';

  @override
  String get starred => 'Markiert';

  @override
  String get speakerTagPromptClipUnavailable => 'Dieser Clip konnte nicht abgespielt werden';

  @override
  String get feedbackSubtitleFoundAlternative => 'Wir würden gerne erfahren, was dein Interesse geweckt hat.';

  @override
  String get omiButtonActions => 'Omi-Tastenaktionen';

  @override
  String get invalidRecordingDesc =>
      'Bitte stellen Sie sicher, dass Sie mindestens 5 Sekunden und nicht mehr als 90 Sekunden sprechen.';

  @override
  String get switchApiConfirmTitle => 'API-Umgebung wechseln';

  @override
  String gattError(String code) {
    return 'GATT-Fehler ($code)';
  }

  @override
  String get aiGenRegenerateIcon => 'Symbol neu generieren';

  @override
  String get connectTaskAppToExport => 'Verbinde eine Aufgaben-App in den Einstellungen zum Exportieren';

  @override
  String get firmwareFlashed => 'Firmware geflasht';

  @override
  String get addPerson => 'Person hinzufügen';

  @override
  String get cancelConsequencesSubtitle =>
      'Wir empfehlen dringend, deine anderen Optionen zu erkunden, anstatt zu kündigen.';

  @override
  String get transcriptCopiedToClipboard => 'Transkript in Zwischenablage kopiert';

  @override
  String get monthNov => 'Nov';

  @override
  String get switchedToOnDevice => 'Auf Geräte-Transkription umgeschaltet';

  @override
  String get phoneMicOfflineFallbackMessage =>
      'Keine Verbindung – Aufnahme erfolgt lokal. Sie wird transkribiert, sobald du wieder online bist.';

  @override
  String get scopeUserConversations => 'Benutzergespräche';

  @override
  String get otherAppResults => 'Andere App-Ergebnisse';

  @override
  String get chatAppsGetNewCode => 'Neuen Code holen';

  @override
  String get backgroundLocationDenied => 'Hintergrundstandortzugriff verweigert';

  @override
  String get syncFailureFootnote =>
      'Schlägt die Verarbeitung fehl, wird die Aufnahme bei der nächsten Synchronisierung automatisch erneut versucht.';

  @override
  String get checkingNext7Days => 'Überprüfung der nächsten 7 Tage';

  @override
  String get monthlyPayouts => 'Monatliche Auszahlungen';

  @override
  String get searchLanguageHint => 'Sprache nach Name oder Code suchen';

  @override
  String get gotIt => 'Verstanden';

  @override
  String get pleaseEnterAppName => 'Bitte geben Sie einen App-Namen ein';

  @override
  String get newConversations => 'Neue Gespräche';

  @override
  String get learnMoreAtOmiTraining => 'Erfahren Sie mehr unter omi.me/training';

  @override
  String get entityOpenTasks => 'Offene Aufgaben';

  @override
  String get summary => 'Zusammenfassung';

  @override
  String get copied => 'Kopiert';

  @override
  String get feedbackReasonRecordingDelayedOrStuck => 'Verzögert oder hängengeblieben';

  @override
  String get taskIntegrations => 'Aufgaben-Integrationen';

  @override
  String get tailoredConversationSummaries => 'Maßgeschneiderte Gesprächszusammenfassungen';

  @override
  String get skipThisQuestion => 'Diese Frage überspringen';

  @override
  String get descriptionOptional => 'Beschreibung (optional)';

  @override
  String get about => 'Über';

  @override
  String shareWithContactsCount(int count) {
    return 'Mit $count Kontakten teilen';
  }

  @override
  String get discardChangesTitle => 'Änderungen verwerfen?';

  @override
  String get transcriptionDiagnostics => 'Transkriptions-Diagnose';

  @override
  String get syncStatusFileUnavailable => 'Datei nicht verfügbar';

  @override
  String get createNewApp => 'Neue App erstellen';

  @override
  String verifiedHoursAgo(int hours) {
    return 'Vor ${hours}Std verifiziert';
  }

  @override
  String get chatLimitReachedTitle => 'Chatlimit erreicht';

  @override
  String get wrappedShareText => 'Mein 2025, festgehalten von Omi ✨ omi.me/wrapped';

  @override
  String get reconnectionsRecent => 'Wiederverbindungen (letzte 7 Tage)';

  @override
  String get appAccess => 'App-Zugriff';

  @override
  String get description => 'Beschreibung';

  @override
  String phoneFreeCallsRemainingWithMax(int remaining, int limit, int minutes) {
    return '$remaining von $limit kostenlosen Anrufen in diesem Monat übrig · bis zu $minutes Min. pro Anruf';
  }

  @override
  String get clearOmisMemory => 'Omis Erinnerung löschen';

  @override
  String get exportSummary => 'Zusammenfassung exportieren';

  @override
  String get install => 'Installieren';

  @override
  String get syncStepBackedUpDesc => 'Du findest es unter Gespräche';

  @override
  String get localProcessingInfo =>
      'Audio wird lokal verarbeitet. Funktioniert offline, privater, verbraucht aber mehr Akku.';

  @override
  String get connectStripeOrPayPal => 'Verbinden Sie Stripe oder PayPal, um Zahlungen für Ihre App zu erhalten.';

  @override
  String get wrappedMomentsHeader => 'Momente';

  @override
  String get systemDefault => 'Systemstandard';

  @override
  String get keepUsingPendant => 'Anhänger weiter nutzen';

  @override
  String get paymentFailedToFetchCountries =>
      'Unterstützte Länder konnten nicht abgerufen werden. Bitte versuchen Sie es später erneut.';

  @override
  String get micGainDescLow => 'Sehr leise - für laute Umgebungen';

  @override
  String get errorUpdatingConversationTitle => 'Fehler beim Aktualisieren des Gesprächstitels';

  @override
  String timeSecsSingular(int count) {
    return '$count Sek';
  }

  @override
  String timeCompactHours(int count) {
    return '${count}h';
  }

  @override
  String get browseInstallCreateApps => 'Apps durchsuchen, installieren und erstellen';

  @override
  String get reddit => 'Reddit';

  @override
  String get chooseFile => 'Datei auswählen';

  @override
  String participantsSummary(String name, int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count weitere',
      many: '$count weitere',
      few: '$count weitere',
      one: '1 weitere Person',
    );
    return '$name + $_temp0';
  }

  @override
  String get connectingYourStripeAccount => 'Verbindung Ihres Stripe-Kontos';

  @override
  String get cancelReasonMissingFeatures => 'Fehlende Funktionen';

  @override
  String get chatTitle => 'Chat';

  @override
  String get chatAppsNotifyMe => 'Benachrichtige mich';

  @override
  String get appAccessDesc =>
      'Die folgenden Apps können auf Ihre Daten zugreifen. Tippen Sie auf eine App, um deren Berechtigungen zu verwalten.';

  @override
  String get captureDisplayDetectionFailed => 'Bildschirmerkennung fehlgeschlagen. Aufnahme gestoppt.';

  @override
  String get recapRegeneratedSnackbar => 'Zusammenfassung neu erstellt';

  @override
  String get speakerTagPromptLabeledYouToast => 'Als du zugeordnet';

  @override
  String get categoryFinancial => 'Finanzen';

  @override
  String get chatAppsPrefilled => 'Vorausgefüllt';

  @override
  String get noSummaryForConversation => 'Keine Zusammenfassung\nfür diese Unterhaltung verfügbar.';

  @override
  String get aiPrompts => 'KI-Eingabeaufforderungen';

  @override
  String get view => 'Ansehen';

  @override
  String get dataAlwaysEncrypted =>
      'Unabhängig vom Level sind Ihre Daten immer im Ruhezustand und während der Übertragung verschlüsselt.';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item in Zwischenablage kopiert';
  }

  @override
  String get currentPlan => 'Aktuell';

  @override
  String get phoneCallsUpsellFeature1 => 'Echtzeit-Transkription jedes Anrufs';

  @override
  String get lowBatteryAlertTitle => 'Warnung: Niedriger Akkustand';

  @override
  String get enterConversationTitle => 'Gesprächstitel eingeben…';

  @override
  String get pasteJsonConfig => 'Fügen Sie Ihre JSON-Konfiguration unten ein:';

  @override
  String get dreamReportRunLimit => 'Heute keine manuellen Durchläufe mehr';

  @override
  String get translationNoticeMessage =>
      'Omi übersetzt Unterhaltungen in Ihre Hauptsprache. Aktualisieren Sie diese jederzeit unter Einstellungen → Profile.';

  @override
  String get aiGenFailedToRegenerateIcon => 'Symbol konnte nicht neu generiert werden';

  @override
  String get pairingDescBee => 'Drücken Sie die Taste 5 Mal hintereinander. Das Licht blinkt dann blau und grün.';

  @override
  String sharedTasksAddButton(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count Aufgaben hinzufügen',
      one: '1 Aufgabe hinzufügen',
    );
    return '$_temp0';
  }

  @override
  String get paymentFailedToSavePaypal =>
      'PayPal-Details konnten nicht gespeichert werden. Bitte versuchen Sie es später erneut.';

  @override
  String get couldNotLoadCheckout =>
      'Die Bezahlseite konnte nicht geladen werden. Prüfe deine Verbindung und versuche es erneut.';

  @override
  String get capabilitySummary => 'Zusammenfassung';

  @override
  String get selectYourCountry => 'Wählen Sie Ihr Land';

  @override
  String uploadingAudioForTranscription(String duration) {
    return '$duration Audio wird zur Transkription hochgeladen…';
  }

  @override
  String get conversationUrlCouldNotBeShared => 'Konversations-URL konnte nicht geteilt werden.';

  @override
  String get otaStartFailed =>
      'Das Update konnte nicht gestartet werden. Prüfe WLAN-Name und Passwort und versuche es erneut.';

  @override
  String get triggersWhenAudioBytesReceived => 'Wird ausgelöst, wenn Audio-Bytes empfangen werden.';

  @override
  String get wrappedMy2025 => 'Mein 2025';

  @override
  String timeCompactSecs(int count) {
    return '${count}s';
  }

  @override
  String get shareWithAttendees => 'Mit Teilnehmern teilen';

  @override
  String get recordingsSyncAutomatically => 'Aufnahmen werden automatisch synchronisiert — kein Handeln erforderlich.';

  @override
  String get whereDidYouHearAboutOmi => 'Wie hast du uns gefunden?';

  @override
  String get captureMicrophonePermissionInSystemPreferences =>
      'Mikrofonberechtigung in den Systemeinstellungen erteilen';

  @override
  String audioUploadFailedTapRetry(String duration) {
    return 'Upload fehlgeschlagen — $duration Audio auf Ihrem Telefon gespeichert. Tippen Sie, um es erneut zu versuchen.';
  }

  @override
  String get captureModeLaterDescription => 'Audio jetzt speichern und transkribieren, wann du willst.';

  @override
  String get cleanUpNothingTitle => 'Nichts aufzuräumen';

  @override
  String get deletePersonLabel => 'Person löschen';

  @override
  String get attachedFiles => '📎 Angehängte Dateien';

  @override
  String get editGoal => 'Ziel bearbeiten';

  @override
  String get helpsDiagnoseIssues => 'Hilft bei der Diagnose von Problemen';

  @override
  String get bulkDeleteFailed => 'Aufgaben konnten nicht gelöscht werden. Bitte erneut versuchen.';

  @override
  String get manifestRefreshFailed => 'Manifest konnte nicht aktualisiert werden';

  @override
  String get searchPlaceholder => 'Suchen';

  @override
  String get appOptions => 'App-Optionen';

  @override
  String get reprocessingConversationProgress => 'Gespräch wird neu verarbeitet…';

  @override
  String get entityWhatOmiKnows => 'Was Omi weiß';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'Das Gespräch wird nach $minutes Minute$suffix ohne Sprache zusammengefasst.';
  }

  @override
  String get permissionRevokedMessage => 'Möchten Sie, dass wir auch alle Ihre vorhandenen Aufnahmen löschen?';

  @override
  String get phoneNumberCallerIdHint => 'Nach der Verifizierung wird dies Ihre Anrufer-ID';

  @override
  String chatAppsTextThisTo(String address) {
    return 'Nicht geöffnet? Schreib das an $address';
  }

  @override
  String get upcomingMeetings => 'Bevorstehende Termine';

  @override
  String get preparingSystemAudioCapture => 'Systemtonaufnahme wird vorbereitet';

  @override
  String dreamReportQueued(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count Änderungen warten',
      one: '1 Änderung wartet',
      zero: 'Keine Änderungen warten',
    );
    return '$_temp0';
  }

  @override
  String get chatReplyFailed => 'Omi konnte nicht antworten. Prüfe deine Verbindung und versuche es erneut.';

  @override
  String get noDataToMigrateFinalizing => 'Keine Daten zu migrieren. Abschließen…';

  @override
  String get accessibility => 'Barrierefreiheit';

  @override
  String get openOmiOnAppleWatch => 'Öffne Omi auf deiner\nApple Watch';

  @override
  String get wrappedGettingItDone => 'Es erledigen';

  @override
  String get rawData => 'Rohdaten';

  @override
  String get passwordsDoNotMatch => 'Passwörter stimmen nicht überein';

  @override
  String errorInstallingApp(String appName, String error) {
    return 'Fehler bei der Installation von $appName: $error';
  }

  @override
  String deleteQuoted(String name) {
    return '\"$name\" löschen';
  }

  @override
  String get wrappedTopFivePhrases => 'Top 5 Phrasen';

  @override
  String get deviceOnboardingHoldButtonHint => 'Halte die Taste fest gedrückt, bis das Licht ausgeht';

  @override
  String get capabilities => 'Funktionen';

  @override
  String get useMcpApiKey => 'Verwenden Sie Ihren MCP-API-Schlüssel';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return '$serviceName-Integration kommt bald';
  }

  @override
  String get wrappedStruggle => 'Herausforderung';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return 'Benachrichtigungsberechtigungsstatus: $status. Bitte überprüfen Sie die Systemeinstellungen.';
  }

  @override
  String get meetingScreenshotsTitle => 'Was auf dem Bildschirm war';

  @override
  String verifiedMinutesAgo(int minutes) {
    return 'Vor ${minutes}Min verifiziert';
  }

  @override
  String get permissionsRequired => 'Berechtigungen erforderlich';

  @override
  String get speakerTagPromptNotSure => 'Nicht sicher';

  @override
  String get current => 'Aktuell';

  @override
  String get improveConnectionAction => 'Verstanden';

  @override
  String get profile => 'Profil';

  @override
  String get audioPlaybackFailed =>
      'Audio kann nicht abgespielt werden. Die Datei ist möglicherweise beschädigt oder fehlt.';

  @override
  String get billingYearly => 'Jährlich';

  @override
  String get batteryUsageHigher => 'Der Batterieverbrauch wird höher sein als bei der Cloud-Transkription.';

  @override
  String get permissionsLabel => 'BERECHTIGUNGEN';

  @override
  String get enhanceTranscriptAccuracy => 'Transkriptionsgenauigkeit verbessern';

  @override
  String get connectedStatus => 'Verbunden';

  @override
  String get microphonePermissionDenied =>
      'Mikrofonberechtigung verweigert. Bitte erteilen Sie die Berechtigung in Systemeinstellungen > Datenschutz & Sicherheit > Mikrofon.';

  @override
  String get onDeviceModelDownloadSuccessDesc => 'Whisper-Modell erfolgreich heruntergeladen';

  @override
  String get storageLocationLimitlessPendant => 'Limitless Pendant';

  @override
  String get chatAppsLinkExpired => 'Der Link ist abgelaufen. Tippe auf „Telegram öffnen“, um einen neuen zu erhalten.';

  @override
  String get captureOfflineBuffering => 'Offline, wird zwischengespeichert';

  @override
  String get pleaseCheckInternetConnection =>
      'Bitte überprüfen Sie Ihre Internetverbindung und versuchen Sie es erneut';

  @override
  String get todaysScore => 'Heutiger Score';

  @override
  String get conversationReprocessed => 'Gespräch aktualisiert';

  @override
  String get loadingDuration => 'Lade Dauer…';

  @override
  String get noSummary => 'Keine Zusammenfassung';

  @override
  String get raybanMetaMicrophoneReady => 'Mikrofon bereit';

  @override
  String get applyFilters => 'Filter anwenden';

  @override
  String get appDescriptionPlaceholder =>
      'Meine fantastische App ist eine großartige App, die erstaunliche Dinge tut. Sie ist die beste App aller Zeiten!';

  @override
  String get cancelSubscriptionKeepAccessMessage =>
      'Du behältst den Zugriff bis zum Ende des aktuellen Abrechnungszeitraums.';

  @override
  String get editYourReview => 'Bewertung bearbeiten';

  @override
  String get actionItemsTitle => 'Aufgaben';

  @override
  String get raybanMetaAudioOnlyTitle => 'Ray-Ban Meta Nur-Audio-Modus';

  @override
  String get reviewSomeoneElse => 'Jemand anderes…';

  @override
  String get betaTesterMessage =>
      'Sie sind Beta-Tester für diese App. Sie ist noch nicht öffentlich. Sie wird nach Genehmigung öffentlich.';

  @override
  String chatAppsIMessageTo(String address) {
    return 'An: Omi · $address';
  }

  @override
  String get comingSoon => 'Demnächst';

  @override
  String rollbackConfirmMessage(String version) {
    return 'Dies ersetzt Ihre aktuelle Firmware durch die neueste stabile Version ($version). Ihr Gerät wird nach dem Update neu gestartet.';
  }

  @override
  String get termsOfService => 'Nutzungsbedingungen';

  @override
  String get wrappedNotMentioned => 'Nicht erwähnt';

  @override
  String get deviceDisconnectedNotificationTitle => 'Ihr Omi-Gerät wurde getrennt';

  @override
  String get rayBanMetaMicPickerDescription =>
      'Wähle das Bluetooth-Mikrofon deiner Brille. Musik wird pausiert, während Omi es verwendet.';

  @override
  String get chatBlockQuestion => 'Frage';

  @override
  String get successfullyConnectedTodoist => 'Erfolgreich mit Todoist verbunden!';

  @override
  String voiceRecognitionStatus(String status) {
    String _temp0 = intl.Intl.selectLogic(
      status,
      {
        'ready': 'Stimme zur Erkennung bereit',
        'saved_sample_awaiting_embedding': 'Aufnahme gespeichert, Sprachverarbeitung ausstehend',
        'not_learned': 'Stimme nicht gelernt',
        'other': 'Stimmstatus unbekannt',
      },
    );
    return '$_temp0';
  }

  @override
  String addQueryAsNewPerson(String query) {
    return '„$query“ als neue Person hinzufügen';
  }

  @override
  String confidenceReasonAutoConfirmed(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Du hast $count automatische Markierungen bestätigt',
      one: 'Du hast 1 automatische Markierung bestätigt',
    );
    return '$_temp0';
  }

  @override
  String get recordAudioConversations => 'Audio-Gespräche aufzeichnen';

  @override
  String get saveKeyWarning => 'Speichern Sie diesen Schlüssel jetzt! Sie werden ihn nicht mehr sehen können.';

  @override
  String get saveChanges => 'Änderungen speichern';

  @override
  String get sttModelSlower => 'Langsamer';

  @override
  String get otaDownloadFailed => 'Firmware-Download fehlgeschlagen. Prüfe die WLAN-Verbindung und versuche es erneut.';

  @override
  String get captureRecordingViewing => 'Du siehst diese Aufnahme';

  @override
  String get resetFilters => 'Filter zurücksetzen';

  @override
  String get voiceSettingsSaveOthersSubtitle =>
      'Wenn du jemanden benennst, speichert Omi eine kurze Stimmprobe, um die Person beim nächsten Mal zu erkennen';

  @override
  String get iveDoneThis => 'Erledigt';

  @override
  String get howSyncingWorks => 'So funktioniert die Synchronisierung';

  @override
  String greetingWithName(String greeting, String name) {
    return '$greeting, $name';
  }

  @override
  String reviewRemaining(int count) {
    return 'Noch $count';
  }

  @override
  String get feedbackReasonRecordingMissingAudio => 'Audio fehlt';

  @override
  String get appCategoryModalTitle => 'App-Kategorie';

  @override
  String get pushToTalk => 'Push-to-Talk';

  @override
  String get noApiKeysYet => 'Noch keine API-Schlüssel. Erstellen Sie einen zur Integration mit Ihrer App.';

  @override
  String minLabel(int count) {
    return '$count Min';
  }

  @override
  String appRatingCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count Bewertungen',
      one: '1 Bewertung',
    );
    return '$_temp0';
  }

  @override
  String get wrappedFood => 'ESSEN';

  @override
  String get aboutAMinuteRemaining => 'Etwa eine Minute verbleibend';

  @override
  String get clearLogs => 'Protokolle löschen';

  @override
  String get wrappedBook => 'BUCH';

  @override
  String get phoneCallSubtitle => 'Anruf mit Live-Transkription aufnehmen';

  @override
  String deleteConversationsTitle(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count Unterhaltungen löschen?',
      one: '1 Unterhaltung löschen?',
    );
    return '$_temp0';
  }

  @override
  String get deleteSelected => 'Ausgewählte löschen';

  @override
  String failedToDeleteGraph(String error) {
    return 'Graph konnte nicht gelöscht werden: $error';
  }

  @override
  String get setupQuestionsIntro => 'Hilf uns, Omi zu verbessern, indem du ein paar Fragen beantwortest. 🫶 💜';

  @override
  String get category => 'Kategorie';

  @override
  String get timeout30MinutesDesc => 'Unterhaltung nach 30 Minuten Stille beenden';

  @override
  String get goalDeleted => 'Ziel gelöscht';

  @override
  String get conversationDisplay => 'Gesprächsanzeige';

  @override
  String get conversationNoSummaryYet => 'Dieses Gespräch hat noch keine Zusammenfassung.';

  @override
  String get chatsLowercase => 'Chats';

  @override
  String get clearChatQuestion => 'Chat löschen?';

  @override
  String get signInTitle => 'Anmelden';

  @override
  String get loadingKnowledgeGraph => 'Wissensgraph wird geladen…';

  @override
  String get goalTracker => 'Ziel-Tracker';

  @override
  String get commandRequired => '⌘ erforderlich';

  @override
  String get permissionEnabled => 'Aktiviert';

  @override
  String get submitReview => 'Bewertung absenden';

  @override
  String chatUsageCost(String used, String limit) {
    return 'Chat: \$$used / \$$limit diesen Monat verbraucht';
  }

  @override
  String get discard => 'Verwerfen';

  @override
  String dreamReportPasses(int count, int limit) {
    return '$count von $limit Durchläufen heute';
  }

  @override
  String get unlockOmiInfiniteMemory => 'Unbegrenzte Erinnerungen';

  @override
  String get addAppPersonaConflictWithCapabilities => 'Persona kann nicht mit anderen Fähigkeiten ausgewählt werden';

  @override
  String get whyAreYouCanceling => 'Warum kündigst du?';

  @override
  String get permissionRequestedExclaim => 'Berechtigung angefordert!';

  @override
  String get chatBlockOpenInMemories => 'In Erinnerungen öffnen';

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total Objekte';
  }

  @override
  String get deleteActionItemTitle => 'Aufgabe löschen';

  @override
  String get rollBack => 'Zurücksetzen';

  @override
  String get chatAppsOmiPro => 'OMI PRO';

  @override
  String disconnectFromAppDesc(String appName) {
    return 'Dies entfernt Ihre $appName-Authentifizierung. Sie müssen sich neu verbinden, um es wieder zu verwenden.';
  }

  @override
  String get onDeviceModelSize => 'Modellgröße';

  @override
  String tagSpeaker(int speakerId) {
    return 'Sprecher $speakerId markieren';
  }

  @override
  String get couldNotOpenUrl => 'Die URL konnte nicht geöffnet werden. Bitte versuchen Sie es erneut.';

  @override
  String get conversationNewIndicator => 'Neu';

  @override
  String get notEnoughSpeechDescription =>
      'Es wurde nicht genug Sprache erkannt. Bitte sprechen Sie mehr und versuchen Sie es erneut.';

  @override
  String get liveRssiOverTime => 'Live-RSSI im Zeitverlauf';

  @override
  String get usageEverywhere => 'Überall';

  @override
  String nConversations(int count) {
    return '$count Gespräche';
  }

  @override
  String get wrappedConversationsLabel => 'Gespräche';

  @override
  String get usageYear => 'Dieses Jahr';

  @override
  String get noContactsMatchSearch => 'Keine Kontakte entsprechen Ihrer Suche';

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count Aufgaben$s gelöscht';
  }

  @override
  String get actionItemMarkedIncomplete => 'Aufgabe als unvollständig markiert';

  @override
  String get start => 'Starten';

  @override
  String discardedConversationTitle(String duration) {
    return 'Verworfen · $duration';
  }

  @override
  String get debugLogsCleared => 'Debug-Protokolle gelöscht';

  @override
  String get preparingAudioCapture => 'Audioaufnahme wird vorbereitet';

  @override
  String get availablePaymentMethods => 'Verfügbare Zahlungsmethoden';

  @override
  String get deleteReasonOther => 'Sonstiges';

  @override
  String get accountCutoverMigrationInProgressTitle => 'Migration läuft';

  @override
  String get connectedKnowledgeData => 'Verbundene Wissensdaten';

  @override
  String get wrappedMostFunDay => 'Am lustigsten';

  @override
  String get onboardingAccessibilityRequired =>
      'Bedienungshilfen-Berechtigung ist erforderlich, um Browser-Meetings zu erkennen.';

  @override
  String get selectActionItems => 'Mehrere auswählen';

  @override
  String switchApiConfirmBody(String environment) {
    return 'Zu $environment wechseln? Sie müssen die App schließen und erneut öffnen, damit die Änderungen wirksam werden.';
  }

  @override
  String get whisperModelSizeLarge => 'Groß';

  @override
  String get currentVersion => 'Aktuelle Version';

  @override
  String get aiAppGeneratorBannerTitle => 'Erstelle mit einem Tippen eine App mit KI';

  @override
  String get rayBanMetaMicPickerLoadError =>
      'Bluetooth-Mikrofone konnten nicht geladen werden. Prüfe, ob Bluetooth aktiviert ist, und versuche es erneut.';

  @override
  String get noneSelected => 'Keine ausgewählt';

  @override
  String get entityKeptCurrent => 'Von Omi aktuell gehalten';

  @override
  String migratingFromTo(String source, String target) {
    return 'Migration von $source nach $target';
  }

  @override
  String get controlNotificationFrequency => 'Steuern Sie, wie oft Omi Ihnen proaktive Benachrichtigungen sendet.';

  @override
  String get connectionUptime => 'Betriebszeit';

  @override
  String get categoryLabel => 'Kategorie';

  @override
  String get aboutTheApp => 'Über die App';

  @override
  String get planSheetChooseYourPlan => 'Wähle den Plan, der zu dir passt.';

  @override
  String get almostDone => 'Fast fertig…';

  @override
  String get tasksFromConversationsWillAppear =>
      'Aufgaben aus Ihren Gesprächen werden hier angezeigt.\nKlicken Sie auf Erstellen, um eine manuell hinzuzufügen.';

  @override
  String get personLastHeard => 'Zuletzt gehört';

  @override
  String get durationThreshold => 'Dauerschwellenwert';

  @override
  String get transcriptionServiceDiagnosticStatus => 'Diagnosestatus des Transkriptionsdienstes';

  @override
  String get triggersWhenNewTranscriptReceived => 'Wird ausgelöst, wenn ein neues Transkript empfangen wird.';

  @override
  String get aboutOmi => 'Über Omi';

  @override
  String get identifyingOthers => 'Identifizierung Anderer';

  @override
  String get phoneCallsSubtitle => 'Telefonieren mit Echtzeit-Transkription';

  @override
  String get creatingYourApp => 'Erstelle Ihre App…';

  @override
  String get analyzingYourData => 'Analyse deiner Daten';
}
