// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for German (`de`).
class AppLocalizationsDe extends AppLocalizations {
  AppLocalizationsDe([String locale = 'de']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'Unterhaltung';

  @override
  String get transcriptTab => 'Transkript';

  @override
  String get actionItemsTab => 'Aufgaben';

  @override
  String get deleteConversationTitle => 'Unterhaltung löschen?';

  @override
  String get deleteConversationMessage =>
      'Sind Sie sicher, dass Sie diese Unterhaltung löschen möchten? Diese Aktion kann nicht rückgängig gemacht werden.';

  @override
  String get confirm => 'Bestätigen';

  @override
  String get cancel => 'Abbrechen';

  @override
  String get ok => 'OK';

  @override
  String get delete => 'Löschen';

  @override
  String get add => 'Hinzufügen';

  @override
  String get update => 'Aktualisieren';

  @override
  String get save => 'Speichern';

  @override
  String get edit => 'Bearbeiten';

  @override
  String get close => 'Schließen';

  @override
  String get clear => 'Leeren';

  @override
  String get copyTranscript => 'Transkript kopieren';

  @override
  String get copySummary => 'Zusammenfassung kopieren';

  @override
  String get testPrompt => 'Prompt testen';

  @override
  String get reprocessConversation => 'Unterhaltung neu verarbeiten';

  @override
  String get deleteConversation => 'Unterhaltung löschen';

  @override
  String get contentCopied => 'Inhalt in die Zwischenablage kopiert';

  @override
  String get failedToUpdateStarred => 'Favoriten-Status konnte nicht aktualisiert werden.';

  @override
  String get conversationUrlNotShared => 'Unterhaltungs-URL konnte nicht geteilt werden.';

  @override
  String get errorProcessingConversation =>
      'Fehler beim Verarbeiten der Unterhaltung. Bitte versuchen Sie es später erneut.';

  @override
  String get noInternetConnection => 'Bitte überprüfen Sie Ihre Internetverbindung und versuchen Sie es erneut.';

  @override
  String get unableToDeleteConversation => 'Unterhaltung konnte nicht gelöscht werden';

  @override
  String get somethingWentWrong => 'Etwas ist schief gelaufen! Bitte versuchen Sie es später erneut.';

  @override
  String get copyErrorMessage => 'Fehlermeldung kopieren';

  @override
  String get errorCopied => 'Fehlermeldung in die Zwischenablage kopiert';

  @override
  String get remaining => 'Verbleibend';

  @override
  String get loading => 'Laden...';

  @override
  String get loadingDuration => 'Lade Dauer...';

  @override
  String secondsCount(int count) {
    return '$count Sekunden';
  }

  @override
  String get people => 'Personen';

  @override
  String get addNewPerson => 'Neue Person hinzufügen';

  @override
  String get editPerson => 'Person bearbeiten';

  @override
  String get createPersonHint =>
      'Erstellen Sie eine neue Person und trainieren Sie Omi, deren Stimme ebenfalls zu erkennen!';

  @override
  String get speechProfile => 'Sprachprofil';

  @override
  String sampleNumber(int number) {
    return 'Beispiel $number';
  }

  @override
  String get settings => 'Einstellungen';

  @override
  String get language => 'Sprache';

  @override
  String get selectLanguage => 'Sprache auswählen';

  @override
  String get deleting => 'Löschen...';

  @override
  String get pleaseCompleteAuthentication =>
      'Bitte schließen Sie die Authentifizierung in Ihrem Browser ab. Kehren Sie danach zur App zurück.';

  @override
  String get failedToStartAuthentication => 'Authentifizierung konnte nicht gestartet werden';

  @override
  String get importStarted => 'Import gestartet! Sie werden benachrichtigt, wenn er abgeschlossen ist.';

  @override
  String get failedToStartImport => 'Import konnte nicht gestartet werden. Bitte versuchen Sie es erneut.';

  @override
  String get couldNotAccessFile => 'Die ausgewählte Datei konnte nicht geöffnet werden';

  @override
  String get askOmi => 'Frag Omi';

  @override
  String get done => 'Fertig';

  @override
  String get disconnected => 'Getrennt';

  @override
  String get searching => 'Suche';

  @override
  String get connectDevice => 'Gerät verbinden';

  @override
  String get monthlyLimitReached => 'Sie haben Ihr monatliches Limit erreicht.';

  @override
  String get checkUsage => 'Nutzung prüfen';

  @override
  String get syncingRecordings => 'Synchronisiere Aufnahmen';

  @override
  String get recordingsToSync => 'Aufnahmen zu synchronisieren';

  @override
  String get allCaughtUp => 'Alles auf dem neuesten Stand';

  @override
  String get sync => 'Sync';

  @override
  String get pendantUpToDate => 'Pendant ist aktuell';

  @override
  String get allRecordingsSynced => 'Alle Aufnahmen sind synchronisiert';

  @override
  String get syncingInProgress => 'Synchronisierung läuft';

  @override
  String get readyToSync => 'Bereit zum Synchronisieren';

  @override
  String get tapSyncToStart => 'Tippen Sie auf Sync zum Starten';

  @override
  String get pendantNotConnected => 'Pendant nicht verbunden. Zum Synchronisieren verbinden.';

  @override
  String get everythingSynced => 'Alles ist bereits synchronisiert.';

  @override
  String get recordingsNotSynced => 'Sie haben Aufnahmen, die noch nicht synchronisiert sind.';

  @override
  String get syncingBackground => 'Wir synchronisieren Ihre Aufnahmen im Hintergrund weiter.';

  @override
  String get noConversationsYet => 'Noch keine Unterhaltungen.';

  @override
  String get noStarredConversations => 'Noch keine favorisierten Unterhaltungen.';

  @override
  String get starConversationHint =>
      'Um eine Unterhaltung zu favorisieren, öffnen Sie sie und tippen Sie auf das Sternsymbol im Kopfbereich.';

  @override
  String get searchConversations => 'Unterhaltungen durchsuchen';

  @override
  String selectedCount(int count) {
    return '$count ausgewählt';
  }

  @override
  String get merge => 'Zusammenführen';

  @override
  String get mergeConversations => 'Unterhaltungen zusammenführen';

  @override
  String mergeConversationsMessage(int count) {
    return 'Dies wird $count Unterhaltungen zu einer zusammenfassen. Alle Inhalte werden zusammengeführt und neu generiert.';
  }

  @override
  String get mergingInBackground => 'Zusammenführung im Hintergrund. Dies kann einen Moment dauern.';

  @override
  String get failedToStartMerge => 'Zusammenführung konnte nicht gestartet werden';

  @override
  String get askAnything => 'Frag irgendetwas';

  @override
  String get noMessagesYet => 'Noch keine Nachrichten!\nWarum starten Sie keine Unterhaltung?';

  @override
  String get deletingMessages => 'Lösche Ihre Nachrichten aus Omis Gedächtnis...';

  @override
  String get messageCopied => 'Nachricht in die Zwischenablage kopiert.';

  @override
  String get cannotReportOwnMessage => 'Sie können Ihre eigenen Nachrichten nicht melden.';

  @override
  String get reportMessage => 'Nachricht melden';

  @override
  String get reportMessageConfirm => 'Sind Sie sicher, dass Sie diese Nachricht melden möchten?';

  @override
  String get messageReported => 'Nachricht erfolgreich gemeldet.';

  @override
  String get thankYouFeedback => 'Danke für Ihr Feedback!';

  @override
  String get clearChat => 'Chat löschen?';

  @override
  String get clearChatConfirm =>
      'Sind Sie sicher, dass Sie den Chat löschen möchten? Diese Aktion kann nicht rückgängig gemacht werden.';

  @override
  String get maxFilesLimit => 'Sie können nur 4 Dateien gleichzeitig hochladen';

  @override
  String get chatWithOmi => 'Chat mit Omi';

  @override
  String get apps => 'Apps';

  @override
  String get noAppsFound => 'Keine Apps gefunden';

  @override
  String get tryAdjustingSearch => 'Versuchen Sie, Ihre Suche oder Filter anzupassen';

  @override
  String get createYourOwnApp => 'Erstellen Sie Ihre eigene App';

  @override
  String get buildAndShareApp => 'Erstellen und teilen Sie Ihre eigene App';

  @override
  String get searchApps => '1500+ Apps durchsuchen';

  @override
  String get myApps => 'Meine Apps';

  @override
  String get installedApps => 'Installierte Apps';

  @override
  String get unableToFetchApps =>
      'Apps konnten nicht geladen werden :(\n\nBitte überprüfen Sie Ihre Internetverbindung und versuchen Sie es erneut.';

  @override
  String get aboutOmi => 'Über Omi';

  @override
  String get privacyPolicy => 'Datenschutzrichtlinie';

  @override
  String get visitWebsite => 'Website besuchen';

  @override
  String get helpOrInquiries => 'Hilfe oder Anfragen?';

  @override
  String get joinCommunity => 'Treten Sie der Community bei!';

  @override
  String get membersAndCounting => '8000+ Mitglieder und es werden mehr.';

  @override
  String get deleteAccountTitle => 'Konto löschen';

  @override
  String get deleteAccountConfirm => 'Sind Sie sicher, dass Sie Ihr Konto löschen möchten?';

  @override
  String get cannotBeUndone => 'Dies kann nicht rückgängig gemacht werden.';

  @override
  String get allDataErased => 'Alle Ihre Erinnerungen und Unterhaltungen werden dauerhaft gelöscht.';

  @override
  String get appsDisconnected => 'Ihre Apps und Integrationen werden sofort getrennt.';

  @override
  String get exportBeforeDelete =>
      'Sie können Ihre Daten exportieren, bevor Sie Ihr Konto löschen. Einmal gelöscht, können sie nicht wiederhergestellt werden.';

  @override
  String get deleteAccountCheckbox =>
      'Ich verstehe, dass das Löschen meines Kontos dauerhaft ist und alle Daten, einschließlich Erinnerungen und Unterhaltungen, verloren gehen und nicht wiederhergestellt werden können.';

  @override
  String get areYouSure => 'Sind Sie sicher?';

  @override
  String get deleteAccountFinal =>
      'Diese Aktion ist unwiderruflich und wird Ihr Konto und alle zugehörigen Daten dauerhaft löschen. Sind Sie sicher, dass Sie fortfahren möchten?';

  @override
  String get deleteNow => 'Jetzt löschen';

  @override
  String get goBack => 'Zurück';

  @override
  String get checkBoxToConfirm =>
      'Aktivieren Sie das Kontrollkästchen, um zu bestätigen, dass Sie verstehen, dass das Löschen Ihres Kontos dauerhaft und unwiderruflich ist.';

  @override
  String get profile => 'Profil';

  @override
  String get name => 'Name';

  @override
  String get email => 'E-Mail';

  @override
  String get customVocabulary => 'Benutzerdefiniertes Vokabular';

  @override
  String get identifyingOthers => 'Andere identifizieren';

  @override
  String get paymentMethods => 'Zahlungsmethoden';

  @override
  String get conversationDisplay => 'Unterhaltungsanzeige';

  @override
  String get dataPrivacy => 'Daten & Datenschutz';

  @override
  String get userId => 'Benutzer-ID';

  @override
  String get notSet => 'Nicht festgelegt';

  @override
  String get userIdCopied => 'Benutzer-ID in die Zwischenablage kopiert';

  @override
  String get systemDefault => 'Systemstandard';

  @override
  String get planAndUsage => 'Abonnement & Nutzung';

  @override
  String get offlineSync => 'Offline-Sync';

  @override
  String get deviceSettings => 'Geräteeinstellungen';

  @override
  String get chatTools => 'Chat-Tools';

  @override
  String get feedbackBug => 'Feedback / Fehler';

  @override
  String get helpCenter => 'Hilfe-Center';

  @override
  String get developerSettings => 'Entwicklereinstellungen';

  @override
  String get getOmiForMac => 'Omi für Mac holen';

  @override
  String get referralProgram => 'Empfehlungsprogramm';

  @override
  String get signOut => 'Abmelden';

  @override
  String get appAndDeviceCopied => 'App- und Gerätedetails kopiert';

  @override
  String get wrapped2025 => 'Jahresrückblick 2025';

  @override
  String get yourPrivacyYourControl => 'Ihre Privatsphäre, Ihre Kontrolle';

  @override
  String get privacyIntro =>
      'Bei Omi verpflichten wir uns, Ihre Privatsphäre zu schützen. Auf dieser Seite können Sie steuern, wie Ihre Daten gespeichert und verwendet werden.';

  @override
  String get learnMore => 'Mehr erfahren...';

  @override
  String get dataProtectionLevel => 'Datenschutzniveau';

  @override
  String get dataProtectionDesc =>
      'Ihre Daten sind standardmäßig durch starke Verschlüsselung gesichert. Überprüfen Sie unten Ihre Einstellungen und zukünftigen Datenschutzoptionen.';

  @override
  String get appAccess => 'App-Zugriff';

  @override
  String get appAccessDesc =>
      'Die folgenden Apps können auf Ihre Daten zugreifen. Tippen Sie auf eine App, um deren Berechtigungen zu verwalten.';

  @override
  String get noAppsExternalAccess => 'Keine installierten Apps haben externen Zugriff auf Ihre Daten.';

  @override
  String get deviceName => 'Gerätename';

  @override
  String get deviceId => 'Geräte-ID';

  @override
  String get firmware => 'Firmware';

  @override
  String get sdCardSync => 'SD-Karten-Sync';

  @override
  String get hardwareRevision => 'Hardware-Revision';

  @override
  String get modelNumber => 'Modellnummer';

  @override
  String get manufacturer => 'Hersteller';

  @override
  String get doubleTap => 'Doppeltippen';

  @override
  String get ledBrightness => 'LED-Helligkeit';

  @override
  String get micGain => 'Mikrofonverstärkung';

  @override
  String get disconnect => 'Trennen';

  @override
  String get forgetDevice => 'Gerät vergessen';

  @override
  String get chargingIssues => 'Ladeprobleme';

  @override
  String get disconnectDevice => 'Gerät trennen';

  @override
  String get unpairDevice => 'Gerät entkoppeln';

  @override
  String get unpairAndForget => 'Entkoppeln und Gerät vergessen';

  @override
  String get deviceDisconnectedMessage => 'Ihr Omi wurde getrennt 😔';

  @override
  String get deviceUnpairedMessage =>
      'Gerät entkoppelt. Gehen Sie zu Einstellungen > Bluetooth und vergessen Sie das Gerät, um die Entkopplung abzuschließen.';

  @override
  String get unpairDialogTitle => 'Gerät entkoppeln';

  @override
  String get unpairDialogMessage =>
      'Dies entkoppelt das Gerät, damit es mit einem anderen Telefon verbunden werden kann. Sie müssen zu Einstellungen > Bluetooth gehen und das Gerät vergessen, um den Vorgang abzuschließen.';

  @override
  String get deviceNotConnected => 'Gerät nicht verbunden';

  @override
  String get connectDeviceMessage =>
      'Verbinden Sie Ihr Omi-Gerät, um auf Geräteeinstellungen und Anpassungen zuzugreifen';

  @override
  String get deviceInfoSection => 'Geräteinformationen';

  @override
  String get customizationSection => 'Anpassung';

  @override
  String get hardwareSection => 'Hardware';

  @override
  String get v2Undetected => 'V2 nicht erkannt';

  @override
  String get v2UndetectedMessage =>
      'Wir sehen, dass Sie entweder ein V1-Gerät haben oder Ihr Gerät nicht verbunden ist. Die SD-Karten-Funktionalität ist nur für V2-Geräte verfügbar.';

  @override
  String get endConversation => 'Unterhaltung beenden';

  @override
  String get pauseResume => 'Pause/Fortsetzen';

  @override
  String get starConversation => 'Unterhaltung favorisieren';

  @override
  String get doubleTapAction => 'Doppeltippen-Aktion';

  @override
  String get endAndProcess => 'Beenden & Verarbeiten';

  @override
  String get pauseResumeRecording => 'Aufnahme pausieren/fortsetzen';

  @override
  String get starOngoing => 'Laufende Unterhaltung favorisieren';

  @override
  String get off => 'Aus';

  @override
  String get max => 'Max';

  @override
  String get mute => 'Stumm';

  @override
  String get quiet => 'Leise';

  @override
  String get normal => 'Normal';

  @override
  String get high => 'Hoch';

  @override
  String get micGainDescMuted => 'Mikrofon ist stummgeschaltet';

  @override
  String get micGainDescLow => 'Sehr leise - für laute Umgebungen';

  @override
  String get micGainDescModerate => 'Leise - für mäßigen Lärm';

  @override
  String get micGainDescNeutral => 'Neutral - ausgewogene Aufnahme';

  @override
  String get micGainDescSlightlyBoosted => 'Leicht verstärkt - normale Nutzung';

  @override
  String get micGainDescBoosted => 'Verstärkt - für ruhige Umgebungen';

  @override
  String get micGainDescHigh => 'Hoch - für entfernte oder leise Stimmen';

  @override
  String get micGainDescVeryHigh => 'Sehr hoch - für sehr leise Quellen';

  @override
  String get micGainDescMax => 'Maximum - mit Vorsicht verwenden';

  @override
  String get developerSettingsTitle => 'Entwicklereinstellungen';

  @override
  String get saving => 'Speichern...';

  @override
  String get personaConfig => 'Konfigurieren Sie Ihre KI-Persona';

  @override
  String get beta => 'BETA';

  @override
  String get transcription => 'Transkription';

  @override
  String get transcriptionConfig => 'STT-Anbieter konfigurieren';

  @override
  String get conversationTimeout => 'Unterhaltungs-Timeout';

  @override
  String get conversationTimeoutConfig => 'Legen Sie fest, wann Unterhaltungen automatisch enden';

  @override
  String get importData => 'Daten importieren';

  @override
  String get importDataConfig => 'Daten aus anderen Quellen importieren';

  @override
  String get debugDiagnostics => 'Debug & Diagnose';

  @override
  String get endpointUrl => 'Endpunkt-URL';

  @override
  String get noApiKeys => 'Noch keine API-Schlüssel';

  @override
  String get createKeyToStart => 'Erstellen Sie einen Schlüssel, um zu beginnen';

  @override
  String get createKey => 'Schlüssel erstellen';

  @override
  String get docs => 'Dokumentation';

  @override
  String get yourOmiInsights => 'Ihre Omi-Erkenntnisse';

  @override
  String get today => 'Heute';

  @override
  String get thisMonth => 'Diesen Monat';

  @override
  String get thisYear => 'Dieses Jahr';

  @override
  String get allTime => 'Gesamte Zeit';

  @override
  String get noActivityYet => 'Noch keine Aktivität';

  @override
  String get startConversationToSeeInsights =>
      'Starten Sie eine Unterhaltung mit Omi,\num hier Ihre Nutzungserkenntnisse zu sehen.';

  @override
  String get listening => 'Zuhören';

  @override
  String get listeningSubtitle => 'Gesamtzeit, die Omi aktiv zugehört hat.';

  @override
  String get understanding => 'Verstehen';

  @override
  String get understandingSubtitle => 'Verstandene Wörter aus Ihren Unterhaltungen.';

  @override
  String get providing => 'Bereitstellen';

  @override
  String get providingSubtitle => 'Automatisch erfasste Aufgaben und Notizen.';

  @override
  String get remembering => 'Erinnern';

  @override
  String get rememberingSubtitle => 'Fakten und Details, die für Sie erinnert wurden.';

  @override
  String get unlimitedPlan => 'Unlimited Plan';

  @override
  String get managePlan => 'Plan verwalten';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'Ihr Plan endet am $date.';
  }

  @override
  String renewsOn(String date) {
    return 'Ihr Plan verlängert sich am $date.';
  }

  @override
  String get basicPlan => 'Kostenloser Plan';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used von $limit Minuten verbraucht';
  }

  @override
  String get upgrade => 'Upgrade';

  @override
  String get upgradeToUnlimited => 'Upgrade auf Unlimited';

  @override
  String basicPlanDesc(int limit) {
    return 'Ihr Plan enthält $limit kostenlose Minuten pro Monat. Upgrade für unbegrenzte Nutzung.';
  }

  @override
  String get shareStatsMessage => 'Ich teile meine Omi-Statistiken! (omi.me - mein Always-On KI-Assistent)';

  @override
  String get sharePeriodToday => 'Heute hat Omi:';

  @override
  String get sharePeriodMonth => 'Diesen Monat hat Omi:';

  @override
  String get sharePeriodYear => 'Dieses Jahr hat Omi:';

  @override
  String get sharePeriodAllTime => 'Bisher hat Omi:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 Für $minutes Minuten zugehört';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 $words Wörter verstanden';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ $count Erkenntnisse geliefert';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 $count Erinnerungen gespeichert';
  }

  @override
  String get debugLogs => 'Debug-Protokolle';

  @override
  String get debugLogsAutoDelete => 'Wird nach 3 Tagen automatisch gelöscht.';

  @override
  String get debugLogsDesc => 'Hilft bei der Diagnose von Problemen';

  @override
  String get noLogFilesFound => 'Keine Protokolldateien gefunden.';

  @override
  String get omiDebugLog => 'Omi Debug-Protokoll';

  @override
  String get logShared => 'Protokoll geteilt';

  @override
  String get selectLogFile => 'Protokolldatei auswählen';

  @override
  String get shareLogs => 'Protokolle teilen';

  @override
  String get debugLogCleared => 'Debug-Protokoll gelöscht';

  @override
  String get exportStarted => 'Export gestartet. Dies kann einige Sekunden dauern...';

  @override
  String get exportAllData => 'Alle Daten exportieren';

  @override
  String get exportDataDesc => 'Unterhaltungen in eine JSON-Datei exportieren';

  @override
  String get exportedConversations => 'Exportierte Unterhaltungen von Omi';

  @override
  String get exportShared => 'Export geteilt';

  @override
  String get deleteKnowledgeGraphTitle => 'Wissensgraph löschen?';

  @override
  String get deleteKnowledgeGraphMessage =>
      'Dies löscht alle abgeleiteten Daten des Wissensgraphen (Knoten und Verbindungen). Ihre ursprünglichen Erinnerungen bleiben sicher. Der Graph wird mit der Zeit oder bei der nächsten Anfrage neu erstellt.';

  @override
  String get knowledgeGraphDeleted => 'Wissensgraph erfolgreich gelöscht';

  @override
  String deleteGraphFailed(String error) {
    return 'Löschen des Graphen fehlgeschlagen: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'Wissensgraph löschen';

  @override
  String get deleteKnowledgeGraphDesc => 'Alle Knoten und Verbindungen löschen';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'MCP-Server';

  @override
  String get mcpServerDesc => 'KI-Assistenten mit Ihren Daten verbinden';

  @override
  String get serverUrl => 'Server-URL';

  @override
  String get urlCopied => 'URL kopiert';

  @override
  String get apiKeyAuth => 'API-Schlüssel-Authentifizierung';

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
  String get useMcpApiKey => 'Verwenden Sie Ihren MCP-API-Schlüssel';

  @override
  String get webhooks => 'Webhooks';

  @override
  String get conversationEvents => 'Unterhaltungs-Ereignisse';

  @override
  String get newConversationCreated => 'Neue Unterhaltung erstellt';

  @override
  String get realtimeTranscript => 'Echtzeit-Transkript';

  @override
  String get transcriptReceived => 'Transkript empfangen';

  @override
  String get audioBytes => 'Audio-Bytes';

  @override
  String get audioDataReceived => 'Audiodaten empfangen';

  @override
  String get intervalSeconds => 'Intervall (Sekunden)';

  @override
  String get daySummary => 'Tageszusammenfassung';

  @override
  String get summaryGenerated => 'Zusammenfassung generiert';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'Zu claude_desktop_config.json hinzufügen';

  @override
  String get copyConfig => 'Konfiguration kopieren';

  @override
  String get configCopied => 'Konfiguration in die Zwischenablage kopiert';

  @override
  String get listeningMins => 'Zuhören (Min)';

  @override
  String get understandingWords => 'Verstehen (Wörter)';

  @override
  String get insights => 'Erkenntnisse';

  @override
  String get memories => 'Erinnerungen';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '$used von $limit Min. diesen Monat genutzt';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '$used von $limit Wörtern diesen Monat genutzt';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '$used von $limit Erkenntnissen diesen Monat gewonnen';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return '$used von $limit Erinnerungen diesen Monat erstellt';
  }

  @override
  String get visibility => 'Sichtbarkeit';

  @override
  String get visibilitySubtitle => 'Steuern Sie, welche Unterhaltungen in Ihrer Liste erscheinen';

  @override
  String get showShortConversations => 'Kurze Unterhaltungen anzeigen';

  @override
  String get showShortConversationsDesc => 'Unterhaltungen anzeigen, die kürzer als der Schwellenwert sind';

  @override
  String get showDiscardedConversations => 'Verworfene Unterhaltungen anzeigen';

  @override
  String get showDiscardedConversationsDesc => 'Als verworfen markierte Unterhaltungen einschließen';

  @override
  String get shortConversationThreshold => 'Schwellenwert für kurze Unterhaltungen';

  @override
  String get shortConversationThresholdSubtitle =>
      'Unterhaltungen, die kürzer als dies sind, werden ausgeblendet, sofern oben nicht aktiviert';

  @override
  String get durationThreshold => 'Dauerschwellenwert';

  @override
  String get durationThresholdDesc => 'Unterhaltungen ausblenden, die kürzer als dies sind';

  @override
  String minLabel(int count) {
    return '$count Min';
  }

  @override
  String get customVocabularyTitle => 'Benutzerdefiniertes Vokabular';

  @override
  String get addWords => 'Wörter hinzufügen';

  @override
  String get addWordsDesc => 'Namen, Begriffe oder ungewöhnliche Wörter';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'Verbinden';

  @override
  String get comingSoon => 'Demnächst';

  @override
  String get chatToolsFooter => 'Verbinden Sie Ihre Apps, um Daten und Metriken im Chat anzuzeigen.';

  @override
  String get completeAuthInBrowser =>
      'Bitte schließen Sie die Authentifizierung in Ihrem Browser ab. Kehren Sie danach zur App zurück.';

  @override
  String failedToStartAuth(String appName) {
    return 'Authentifizierung für $appName fehlgeschlagen';
  }

  @override
  String disconnectAppTitle(String appName) {
    return '$appName trennen?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'Sind Sie sicher, dass Sie die Verbindung zu $appName trennen möchten? Sie können sich jederzeit wieder verbinden.';
  }

  @override
  String disconnectedFrom(String appName) {
    return 'Von $appName getrennt';
  }

  @override
  String get failedToDisconnect => 'Trennen fehlgeschlagen';

  @override
  String connectTo(String appName) {
    return 'Verbinden mit $appName';
  }

  @override
  String authAccessMessage(String appName) {
    return 'Sie müssen Omi autorisieren, auf Ihre $appName-Daten zuzugreifen. Dies öffnet Ihren Browser für die Authentifizierung.';
  }

  @override
  String get continueAction => 'Weiter';

  @override
  String get languageTitle => 'Sprache';

  @override
  String get primaryLanguage => 'Primärsprache';

  @override
  String get automaticTranslation => 'Automatische Übersetzung';

  @override
  String get detectLanguages => '10+ Sprachen erkennen';

  @override
  String get authorizeSavingRecordings => 'Speichern von Aufnahmen autorisieren';

  @override
  String get thanksForAuthorizing => 'Danke für die Autorisierung!';

  @override
  String get needYourPermission => 'Wir benötigen Ihre Erlaubnis';

  @override
  String get alreadyGavePermission =>
      'Sie haben uns bereits die Erlaubnis gegeben, Ihre Aufnahmen zu speichern. Hier ist eine Erinnerung, warum wir sie brauchen:';

  @override
  String get wouldLikePermission =>
      'Wir möchten Ihre Erlaubnis, Ihre Sprachaufnahmen zu speichern. Hier ist der Grund:';

  @override
  String get improveSpeechProfile => 'Ihr Sprachprofil verbessern';

  @override
  String get improveSpeechProfileDesc =>
      'Wir verwenden Aufnahmen, um Ihr persönliches Sprachprofil weiter zu trainieren und zu verbessern.';

  @override
  String get trainFamilyProfiles => 'Profile für Freunde und Familie trainieren';

  @override
  String get trainFamilyProfilesDesc =>
      'Ihre Aufnahmen helfen uns, Profile für Ihre Freunde und Familie zu erkennen und zu erstellen.';

  @override
  String get enhanceTranscriptAccuracy => 'Transkriptionsgenauigkeit verbessern';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'Wenn unser Modell besser wird, können wir bessere Transkriptionsergebnisse für Ihre Aufnahmen liefern.';

  @override
  String get legalNotice =>
      'Rechtlicher Hinweis: Die Rechtmäßigkeit der Aufnahme und Speicherung von Sprachdaten kann je nach Ihrem Standort und der Art und Weise, wie Sie diese Funktion nutzen, variieren. Es liegt in Ihrer Verantwortung, die Einhaltung der örtlichen Gesetze und Vorschriften sicherzustellen.';

  @override
  String get alreadyAuthorized => 'Bereits autorisiert';

  @override
  String get authorize => 'Autorisieren';

  @override
  String get revokeAuthorization => 'Autorisierung widerrufen';

  @override
  String get authorizationSuccessful => 'Autorisierung erfolgreich!';

  @override
  String get failedToAuthorize => 'Autorisierung fehlgeschlagen. Bitte versuchen Sie es erneut.';

  @override
  String get authorizationRevoked => 'Autorisierung widerrufen.';

  @override
  String get recordingsDeleted => 'Aufnahmen gelöscht.';

  @override
  String get failedToRevoke => 'Autorisierung konnte nicht widerrufen werden. Bitte versuchen Sie es erneut.';

  @override
  String get permissionRevokedTitle => 'Berechtigung widerrufen';

  @override
  String get permissionRevokedMessage => 'Möchten Sie, dass wir auch alle Ihre vorhandenen Aufnahmen löschen?';

  @override
  String get yes => 'Ja';

  @override
  String get editName => 'Namen bearbeiten';

  @override
  String get howShouldOmiCallYou => 'Wie soll Omi Sie nennen?';

  @override
  String get enterYourName => 'Geben Sie Ihren Namen ein';

  @override
  String get nameCannotBeEmpty => 'Name darf nicht leer sein';

  @override
  String get nameUpdatedSuccessfully => 'Name erfolgreich aktualisiert!';

  @override
  String get calendarSettings => 'Kalendereinstellungen';

  @override
  String get calendarProviders => 'Kalenderanbieter';

  @override
  String get macOsCalendar => 'macOS Kalender';

  @override
  String get connectMacOsCalendar => 'Verbinden Sie Ihren lokalen macOS-Kalender';

  @override
  String get googleCalendar => 'Google Kalender';

  @override
  String get syncGoogleAccount => 'Mit Ihrem Google-Konto synchronisieren';

  @override
  String get showMeetingsMenuBar => 'Anstehende Meetings in der Menüleiste anzeigen';

  @override
  String get showMeetingsMenuBarDesc =>
      'Anzeige Ihres nächsten Meetings und der Zeit bis zum Beginn in der macOS-Menüleiste';

  @override
  String get showEventsNoParticipants => 'Ereignisse ohne Teilnehmer anzeigen';

  @override
  String get showEventsNoParticipantsDesc =>
      'Wenn aktiviert, zeigt \'Demnächst\' Ereignisse ohne Teilnehmer oder Video-Link an.';

  @override
  String get yourMeetings => 'Ihre Meetings';

  @override
  String get refresh => 'Aktualisieren';

  @override
  String get noUpcomingMeetings => 'Keine anstehenden Meetings gefunden';

  @override
  String get checkingNextDays => 'Prüfe die nächsten 30 Tage';

  @override
  String get tomorrow => 'Morgen';

  @override
  String get googleCalendarComingSoon => 'Google Kalender Integration kommt bald!';

  @override
  String connectedAsUser(String userId) {
    return 'Verbunden als Benutzer: $userId';
  }

  @override
  String get defaultWorkspace => 'Standard-Arbeitsbereich';

  @override
  String get tasksCreatedInWorkspace => 'Aufgaben werden in diesem Arbeitsbereich erstellt';

  @override
  String get defaultProjectOptional => 'Standardprojekt (Optional)';

  @override
  String get leaveUnselectedTasks => 'Unmarkiert lassen, um Aufgaben ohne Projekt zu erstellen';

  @override
  String get noProjectsInWorkspace => 'Keine Projekte in diesem Arbeitsbereich gefunden';

  @override
  String get conversationTimeoutDesc =>
      'Wählen Sie, wie lange bei Stille gewartet werden soll, bevor eine Unterhaltung automatisch beendet wird:';

  @override
  String get timeout2Minutes => '2 Minuten';

  @override
  String get timeout2MinutesDesc => 'Unterhaltung nach 2 Minuten Stille beenden';

  @override
  String get timeout5Minutes => '5 Minuten';

  @override
  String get timeout5MinutesDesc => 'Unterhaltung nach 5 Minuten Stille beenden';

  @override
  String get timeout10Minutes => '10 Minuten';

  @override
  String get timeout10MinutesDesc => 'Unterhaltung nach 10 Minuten Stille beenden';

  @override
  String get timeout30Minutes => '30 Minuten';

  @override
  String get timeout30MinutesDesc => 'Unterhaltung nach 30 Minuten Stille beenden';

  @override
  String get timeout4Hours => '4 Stunden';

  @override
  String get timeout4HoursDesc => 'Unterhaltung nach 4 Stunden Stille beenden';

  @override
  String get conversationEndAfterHours => 'Unterhaltungen enden nun nach 4 Stunden Stille';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Unterhaltungen enden nun nach $minutes Minute(n) Stille';
  }

  @override
  String get tellUsPrimaryLanguage => 'Sagen Sie uns Ihre primäre Sprache';

  @override
  String get languageForTranscription =>
      'Stellen Sie Ihre Sprache für schärfere Transkriptionen und ein personalisiertes Erlebnis ein.';

  @override
  String get singleLanguageModeInfo =>
      'Einzel-Sprachmodus ist aktiviert. Übersetzung ist für höhere Genauigkeit deaktiviert.';

  @override
  String get searchLanguageHint => 'Sprache nach Name oder Code suchen';

  @override
  String get noLanguagesFound => 'Keine Sprachen gefunden';

  @override
  String get skip => 'Überspringen';

  @override
  String languageSetTo(String language) {
    return 'Sprache auf $language eingestellt';
  }

  @override
  String get failedToSetLanguage => 'Sprache konnte nicht eingestellt werden';

  @override
  String appSettings(String appName) {
    return '$appName-Einstellungen';
  }

  @override
  String disconnectFromApp(String appName) {
    return 'Von $appName trennen?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'Dies entfernt Ihre $appName-Authentifizierung. Sie müssen sich neu verbinden, um es wieder zu verwenden.';
  }

  @override
  String connectedToApp(String appName) {
    return 'Verbunden mit $appName';
  }

  @override
  String get account => 'Konto';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Ihre Aufgaben werden mit Ihrem $appName-Konto synchronisiert';
  }

  @override
  String get defaultSpace => 'Standard-Space';

  @override
  String get selectSpaceInWorkspace => 'Wählen Sie einen Space in Ihrem Arbeitsbereich';

  @override
  String get noSpacesInWorkspace => 'Keine Spaces in diesem Arbeitsbereich gefunden';

  @override
  String get defaultList => 'Standardliste';

  @override
  String get tasksAddedToList => 'Aufgaben werden zu dieser Liste hinzugefügt';

  @override
  String get noListsInSpace => 'Keine Listen in diesem Space gefunden';

  @override
  String failedToLoadRepos(String error) {
    return 'Repositories konnten nicht geladen werden: $error';
  }

  @override
  String get defaultRepoSaved => 'Standard-Repository gespeichert';

  @override
  String get failedToSaveDefaultRepo => 'Standard-Repository konnte nicht gespeichert werden';

  @override
  String get defaultRepository => 'Standard-Repository';

  @override
  String get selectDefaultRepoDesc =>
      'Wählen Sie ein Standard-Repository für das Erstellen von Issues. Sie können beim Erstellen von Issues immer noch ein anderes Repository angeben.';

  @override
  String get noReposFound => 'Keine Repositories gefunden';

  @override
  String get private => 'Privat';

  @override
  String updatedDate(String date) {
    return 'Aktualisiert am $date';
  }

  @override
  String get yesterday => 'gestern';

  @override
  String daysAgo(int count) {
    return 'vor $count Tagen';
  }

  @override
  String get oneWeekAgo => 'vor 1 Woche';

  @override
  String weeksAgo(int count) {
    return 'vor $count Wochen';
  }

  @override
  String get oneMonthAgo => 'vor 1 Monat';

  @override
  String monthsAgo(int count) {
    return 'vor $count Monaten';
  }

  @override
  String get issuesCreatedInRepo => 'Issues werden in Ihrem Standard-Repository erstellt';

  @override
  String get taskIntegrations => 'Aufgaben-Integrationen';

  @override
  String get configureSettings => 'Einstellungen konfigurieren';

  @override
  String get completeAuthBrowser =>
      'Bitte schließen Sie die Authentifizierung in Ihrem Browser ab. Kehren Sie danach zur App zurück.';

  @override
  String failedToStartAppAuth(String appName) {
    return 'Authentifizierung für $appName konnte nicht gestartet werden';
  }

  @override
  String connectToAppTitle(String appName) {
    return 'Mit $appName verbinden';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Sie müssen Omi autorisieren, Aufgaben in Ihrem $appName-Konto zu erstellen. Dies öffnet Ihren Browser zur Authentifizierung.';
  }

  @override
  String get continueButton => 'Weiter';

  @override
  String appIntegration(String appName) {
    return '$appName-Integration';
  }

  @override
  String integrationComingSoon(String appName) {
    return 'Integration mit $appName kommt bald! Wir arbeiten hart daran, Ihnen mehr Aufgabenmanagement-Optionen zu bieten.';
  }

  @override
  String get gotIt => 'Verstanden';

  @override
  String get tasksExportedOneApp => 'Aufgaben können jeweils nur in eine App exportiert werden.';

  @override
  String get completeYourUpgrade => 'Vervollständigen Sie Ihr Upgrade';

  @override
  String get importConfiguration => 'Konfiguration importieren';

  @override
  String get exportConfiguration => 'Konfiguration exportieren';

  @override
  String get bringYourOwn => 'Bring Your Own';

  @override
  String get payYourSttProvider => 'Nutzen Sie Omi kostenlos. Sie bezahlen nur Ihren STT-Anbieter direkt.';

  @override
  String get freeMinutesMonth => '1.200 kostenlose Minuten/Monat inklusive. Unbegrenzt mit ';

  @override
  String get omiUnlimited => 'Omi Unlimited';

  @override
  String get hostRequired => 'Host ist erforderlich';

  @override
  String get validPortRequired => 'Gültiger Port ist erforderlich';

  @override
  String get validWebsocketUrlRequired => 'Gültige WebSocket-URL ist erforderlich (wss://)';

  @override
  String get apiUrlRequired => 'API-URL ist erforderlich';

  @override
  String get apiKeyRequired => 'API-Schlüssel ist erforderlich';

  @override
  String get invalidJsonConfig => 'Ungültige JSON-Konfiguration';

  @override
  String errorSaving(String error) {
    return 'Fehler beim Speichern: $error';
  }

  @override
  String get configCopiedToClipboard => 'Konfiguration in die Zwischenablage kopiert';

  @override
  String get pasteJsonConfig => 'Fügen Sie Ihre JSON-Konfiguration unten ein:';

  @override
  String get addApiKeyAfterImport => 'Sie müssen Ihren eigenen API-Schlüssel nach dem Importieren hinzufügen';

  @override
  String get paste => 'Einfügen';

  @override
  String get import => 'Importieren';

  @override
  String get invalidProviderInConfig => 'Ungültiger Anbieter in der Konfiguration';

  @override
  String importedConfig(String providerName) {
    return '$providerName-Konfiguration importiert';
  }

  @override
  String invalidJson(String error) {
    return 'Ungültiges JSON: $error';
  }

  @override
  String get provider => 'Anbieter';

  @override
  String get live => 'Live';

  @override
  String get onDevice => 'Auf dem Gerät';

  @override
  String get apiUrl => 'API-URL';

  @override
  String get enterSttHttpEndpoint => 'Geben Sie Ihren STT-HTTP-Endpunkt ein';

  @override
  String get websocketUrl => 'WebSocket-URL';

  @override
  String get enterLiveSttWebsocket => 'Geben Sie Ihren Live-STT-WebSocket-Endpunkt ein';

  @override
  String get apiKey => 'API-Schlüssel';

  @override
  String get enterApiKey => 'Geben Sie Ihren API-Schlüssel ein';

  @override
  String get storedLocallyNeverShared => 'Lokal gespeichert, niemals geteilt';

  @override
  String get host => 'Host';

  @override
  String get port => 'Port';

  @override
  String get advanced => 'Erweitert';

  @override
  String get configuration => 'Konfiguration';

  @override
  String get requestConfiguration => 'Anfragekonfiguration';

  @override
  String get responseSchema => 'Antwortschema';

  @override
  String get modified => 'Geändert';

  @override
  String get resetRequestConfig => 'Anfragekonfiguration auf Standard zurücksetzen';

  @override
  String get logs => 'Protokolle';

  @override
  String get logsCopied => 'Protokolle kopiert';

  @override
  String get noLogsYet =>
      'Noch keine Protokolle. Starten Sie die Aufnahme, um benutzerdefinierte STT-Aktivitäten zu sehen.';

  @override
  String deviceUsesCodec(String deviceName, String codecReason) {
    return '$deviceName verwendet $codecReason. Omi wird verwendet.';
  }

  @override
  String get omiTranscription => 'Omi Transkription';

  @override
  String get bestInClassTranscription => 'Erstklassige Transkription ohne Einrichtung';

  @override
  String get instantSpeakerLabels => 'Sofortige Sprecherkennzeichnung';

  @override
  String get languageTranslation => 'Übersetzung in 100+ Sprachen';

  @override
  String get optimizedForConversation => 'Für Unterhaltungen optimiert';

  @override
  String get autoLanguageDetection => 'Automatische Spracherkennung';

  @override
  String get highAccuracy => 'Hohe Genauigkeit';

  @override
  String get privacyFirst => 'Datenschutz zuerst';

  @override
  String get saveChanges => 'Änderungen speichern';

  @override
  String get resetToDefault => 'Auf Standard zurücksetzen';

  @override
  String get viewTemplate => 'Vorlage anzeigen';

  @override
  String get trySomethingLike => 'Versuchen Sie so etwas wie...';

  @override
  String get tryIt => 'Ausprobieren';

  @override
  String get creatingPlan => 'Erstelle Plan';

  @override
  String get developingLogic => 'Entwickle Logik';

  @override
  String get designingApp => 'Designe App';

  @override
  String get generatingIconStep => 'Generiere Icon';

  @override
  String get finalTouches => 'Letzte Schliffe';

  @override
  String get processing => 'Verarbeitung...';

  @override
  String get features => 'Funktionen';

  @override
  String get creatingYourApp => 'Erstelle Ihre App...';

  @override
  String get generatingIcon => 'Generiere Icon...';

  @override
  String get whatShouldWeMake => 'Was sollen wir machen?';

  @override
  String get appName => 'App-Name';

  @override
  String get description => 'Beschreibung';

  @override
  String get publicLabel => 'Öffentlich';

  @override
  String get privateLabel => 'Privat';

  @override
  String get free => 'Kostenlos';

  @override
  String get perMonth => '/ Monat';

  @override
  String get tailoredConversationSummaries => 'Maßgeschneiderte Gesprächszusammenfassungen';

  @override
  String get customChatbotPersonality => 'Benutzerdefinierte Chatbot-Persönlichkeit';

  @override
  String get makePublic => 'Veröffentlichen';

  @override
  String get anyoneCanDiscover => 'Jeder kann Ihre App entdecken';

  @override
  String get onlyYouCanUse => 'Nur Sie können diese App verwenden';

  @override
  String get paidApp => 'Kostenpflichtige App';

  @override
  String get usersPayToUse => 'Benutzer zahlen für die Nutzung Ihrer App';

  @override
  String get freeForEveryone => 'Kostenlos für alle';

  @override
  String get perMonthLabel => '/ Monat';

  @override
  String get creating => 'Erstellen...';

  @override
  String get createApp => 'App erstellen';

  @override
  String get searchingForDevices => 'Suche nach Geräten...';

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
  String get pairingSuccessful => 'Kopplung erfolgreich';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Fehler beim Verbinden mit Apple Watch: $error';
  }

  @override
  String get dontShowAgain => 'Nicht wieder anzeigen';

  @override
  String get iUnderstand => 'Ich verstehe';

  @override
  String get enableBluetooth => 'Bluetooth aktivieren';

  @override
  String get bluetoothNeeded =>
      'Omi benötigt Bluetooth, um sich mit Ihrem Wearable zu verbinden. Bitte aktivieren Sie Bluetooth und versuchen Sie es erneut.';

  @override
  String get contactSupport => 'Support kontaktieren?';

  @override
  String get connectLater => 'Später verbinden';

  @override
  String get grantPermissions => 'Berechtigungen erteilen';

  @override
  String get backgroundActivity => 'Hintergrundaktivität';

  @override
  String get backgroundActivityDesc => 'Lassen Sie Omi im Hintergrund laufen für bessere Stabilität';

  @override
  String get locationAccess => 'Standortzugriff';

  @override
  String get locationAccessDesc => 'Aktivieren Sie den Hintergrundstandort für das volle Erlebnis';

  @override
  String get notifications => 'Benachrichtigungen';

  @override
  String get notificationsDesc => 'Aktivieren Sie Benachrichtigungen, um informiert zu bleiben';

  @override
  String get locationServiceDisabled => 'Standortdienst deaktiviert';

  @override
  String get locationServiceDisabledDesc =>
      'Der Standortdienst ist deaktiviert. Bitte gehen Sie zu Einstellungen > Datenschutz & Sicherheit > Standortdienste und aktivieren Sie ihn';

  @override
  String get backgroundLocationDenied => 'Hintergrundstandortzugriff verweigert';

  @override
  String get backgroundLocationDeniedDesc =>
      'Bitte gehen Sie zu den Geräteeinstellungen und setzen Sie die Standortberechtigung auf \'Immer zulassen\'';

  @override
  String get lovingOmi => 'Gefällt Ihnen Omi?';

  @override
  String get leaveReviewIos =>
      'Helfen Sie uns, mehr Menschen zu erreichen, indem Sie eine Bewertung im App Store hinterlassen. Ihr Feedback bedeutet uns die Welt!';

  @override
  String get leaveReviewAndroid =>
      'Helfen Sie uns, mehr Menschen zu erreichen, indem Sie eine Bewertung im Google Play Store hinterlassen. Ihr Feedback bedeutet uns die Welt!';

  @override
  String get rateOnAppStore => 'Im App Store bewerten';

  @override
  String get rateOnGooglePlay => 'Im Google Play Store bewerten';

  @override
  String get maybeLater => 'Vielleicht später';

  @override
  String get speechProfileIntro => 'Omi muss Ihre Ziele und Ihre Stimme lernen. Sie können dies später ändern.';

  @override
  String get getStarted => 'Loslegen';

  @override
  String get allDone => 'Alles erledigt!';

  @override
  String get keepGoing => 'Weiter so, Sie machen das großartig';

  @override
  String get skipThisQuestion => 'Diese Frage überspringen';

  @override
  String get skipForNow => 'Vorerst überspringen';

  @override
  String get connectionError => 'Verbindungsfehler';

  @override
  String get connectionErrorDesc =>
      'Verbindung zum Server fehlgeschlagen. Bitte überprüfen Sie Ihre Internetverbindung und versuchen Sie es erneut.';

  @override
  String get invalidRecordingMultipleSpeakers => 'Ungültige Aufnahme erkannt';

  @override
  String get multipleSpeakersDesc =>
      'Es scheint, dass mehrere Sprecher in der Aufnahme sind. Bitte stellen Sie sicher, dass Sie sich an einem ruhigen Ort befinden, und versuchen Sie es erneut.';

  @override
  String get tooShortDesc =>
      'Es wurde nicht genug Sprache erkannt. Bitte sprechen Sie mehr und versuchen Sie es erneut.';

  @override
  String get invalidRecordingDesc =>
      'Bitte stellen Sie sicher, dass Sie mindestens 5 Sekunden und nicht mehr als 90 Sekunden sprechen.';

  @override
  String get areYouThere => 'Sind Sie da?';

  @override
  String get noSpeechDesc =>
      'Wir konnten keine Sprache erkennen. Bitte stellen Sie sicher, dass Sie mindestens 10 Sekunden und nicht mehr als 3 Minuten sprechen.';

  @override
  String get connectionLost => 'Verbindung unterbrochen';

  @override
  String get connectionLostDesc =>
      'Die Verbindung wurde unterbrochen. Bitte überprüfen Sie Ihre Internetverbindung und versuchen Sie es erneut.';

  @override
  String get tryAgain => 'Erneut versuchen';

  @override
  String get connectOmiOmiGlass => 'Omi / OmiGlass verbinden';

  @override
  String get continueWithoutDevice => 'Ohne Gerät fortfahren';

  @override
  String get permissionsRequired => 'Berechtigungen erforderlich';

  @override
  String get permissionsRequiredDesc =>
      'Diese App benötigt Bluetooth- und Standortberechtigungen, um ordnungsgemäß zu funktionieren. Bitte aktivieren Sie diese in den Einstellungen.';

  @override
  String get openSettings => 'Einstellungen öffnen';

  @override
  String get wantDifferentName => 'Möchten Sie einen anderen Namen verwenden?';

  @override
  String get whatsYourName => 'Wie lautet Ihr Name?';

  @override
  String get speakTranscribeSummarize => 'Sprechen. Transkribieren. Zusammenfassen.';

  @override
  String get signInWithApple => 'Mit Apple anmelden';

  @override
  String get signInWithGoogle => 'Mit Google anmelden';

  @override
  String get byContinuingAgree => 'Wenn Sie fortfahren, stimmen Sie unseren ';

  @override
  String get termsOfUse => 'Nutzungsbedingungen';

  @override
  String get omiYourAiCompanion => 'Omi – Ihr KI-Begleiter';

  @override
  String get captureEveryMoment =>
      'Erfassen Sie jeden Moment. Erhalten Sie KI-gestützte Zusammenfassungen. Nie wieder Notizen machen.';

  @override
  String get appleWatchSetup => 'Apple Watch Einrichtung';

  @override
  String get permissionRequestedExclaim => 'Berechtigung angefordert!';

  @override
  String get microphonePermission => 'Mikrofonberechtigung';

  @override
  String get permissionGrantedNow =>
      'Berechtigung erteilt! Jetzt:\n\nÖffnen Sie die Omi-App auf Ihrer Uhr und tippen Sie unten auf \'Weiter\'';

  @override
  String get needMicrophonePermission =>
      'Wir benötigen Mikrofonberechtigung.\n\n1. Tippen Sie auf \'Berechtigung erteilen\'\n2. Erlauben Sie auf Ihrem iPhone\n3. Uhr-App wird geschlossen\n4. Öffnen Sie sie erneut und tippen Sie auf \'Weiter\'';

  @override
  String get grantPermissionButton => 'Berechtigung erteilen';

  @override
  String get needHelp => 'Brauchen Sie Hilfe?';

  @override
  String get troubleshootingSteps =>
      'Fehlerbehebung:\n\n1. Stellen Sie sicher, dass Omi auf Ihrer Uhr installiert ist\n2. Öffnen Sie die Omi-App auf Ihrer Uhr\n3. Suchen Sie nach dem Berechtigungs-Popup\n4. Tippen Sie bei Aufforderung auf \'Zulassen\'\n5. App auf Ihrer Uhr wird geschlossen - öffnen Sie sie erneut\n6. Kommen Sie zurück und tippen Sie auf Ihrem iPhone auf \'Weiter\'';

  @override
  String get recordingStartedSuccessfully => 'Aufnahme erfolgreich gestartet!';

  @override
  String get permissionNotGrantedYet =>
      'Berechtigung noch nicht erteilt. Bitte stellen Sie sicher, dass Sie den Mikrofonzugriff erlaubt und die App auf Ihrer Uhr erneut geöffnet haben.';

  @override
  String errorRequestingPermission(String error) {
    return 'Fehler beim Anfordern der Berechtigung: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'Fehler beim Starten der Aufnahme: $error';
  }

  @override
  String get selectPrimaryLanguage => 'Wählen Sie Ihre primäre Sprache';

  @override
  String get languageBenefits =>
      'Stellen Sie Ihre Sprache für schärfere Transkriptionen und ein personalisiertes Erlebnis ein';

  @override
  String get whatsYourPrimaryLanguage => 'Was ist Ihre primäre Sprache?';

  @override
  String get selectYourLanguage => 'Wählen Sie Ihre Sprache';

  @override
  String get personalGrowthJourney => 'Ihre persönliche Wachstumsreise mit KI, die jedem Ihrer Worte zuhört.';

  @override
  String get actionItemsTitle => 'Aufgaben';

  @override
  String get actionItemsDescription => 'Tippen zum Bearbeiten • Lang drücken zum Auswählen • Wischen für Aktionen';

  @override
  String get tabToDo => 'Zu erledigen';

  @override
  String get tabDone => 'Erledigt';

  @override
  String get tabOld => 'Alt';

  @override
  String get emptyTodoMessage => '🎉 Alles erledigt!\nKeine ausstehenden Aufgaben';

  @override
  String get emptyDoneMessage => 'Noch keine erledigten Elemente';

  @override
  String get emptyOldMessage => '✅ Keine alten Aufgaben';

  @override
  String get noItems => 'Keine Elemente';

  @override
  String get actionItemMarkedIncomplete => 'Aufgabe als unvollständig markiert';

  @override
  String get actionItemCompleted => 'Aufgabe erledigt';

  @override
  String get deleteActionItemTitle => 'Aufgabe löschen';

  @override
  String get deleteActionItemMessage => 'Sind Sie sicher, dass Sie diese Aufgabe löschen möchten?';

  @override
  String get deleteSelectedItemsTitle => 'Ausgewählte Elemente löschen';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Sind Sie sicher, dass Sie $count ausgewählte Aufgaben löschen möchten?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'Aufgabe \"$description\" gelöscht';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count Aufgaben gelöscht';
  }

  @override
  String get failedToDeleteItem => 'Löschen der Aufgabe fehlgeschlagen';

  @override
  String get failedToDeleteItems => 'Löschen der Elemente fehlgeschlagen';

  @override
  String get failedToDeleteSomeItems => 'Löschen einiger Elemente fehlgeschlagen';

  @override
  String get welcomeActionItemsTitle => 'Bereit für Aufgaben';

  @override
  String get welcomeActionItemsDescription =>
      'Ihre KI extrahiert automatisch Aufgaben und To-Dos aus Ihren Unterhaltungen. Sie erscheinen hier, wenn sie erstellt wurden.';

  @override
  String get autoExtractionFeature => 'Automatisch aus Unterhaltungen extrahiert';

  @override
  String get editSwipeFeature => 'Tippen zum Bearbeiten, Wischen zum Erledigen oder Löschen';

  @override
  String itemsSelected(int count) {
    return '$count ausgewählt';
  }

  @override
  String get selectAll => 'Alle auswählen';

  @override
  String get deleteSelected => 'Ausgewählte löschen';

  @override
  String searchMemories(int count) {
    return '$count Erinnerungen durchsuchen';
  }

  @override
  String get memoryDeleted => 'Erinnerung gelöscht.';

  @override
  String get undo => 'Rückgängig';

  @override
  String get noMemoriesYet => 'Noch keine Erinnerungen';

  @override
  String get noInterestingMemories => 'Noch keine interessanten Erinnerungen';

  @override
  String get noSystemMemories => 'Noch keine Systemerinnerungen';

  @override
  String get noMemoriesInCategories => 'Keine Erinnerungen in diesen Kategorien';

  @override
  String get noMemoriesFound => 'Keine Erinnerungen gefunden';

  @override
  String get addFirstMemory => 'Fügen Sie Ihre erste Erinnerung hinzu';

  @override
  String get clearMemoryTitle => 'Omis Gedächtnis löschen';

  @override
  String get clearMemoryMessage =>
      'Sind Sie sicher, dass Sie Omis Gedächtnis löschen möchten? Diese Aktion kann nicht rückgängig gemacht werden.';

  @override
  String get clearMemoryButton => 'Gedächtnis löschen';

  @override
  String get memoryClearedSuccess => 'Omis Gedächtnis über Sie wurde gelöscht';

  @override
  String get noMemoriesToDelete => 'Keine Erinnerungen zu löschen';

  @override
  String get createMemoryTooltip => 'Neue Erinnerung erstellen';

  @override
  String get createActionItemTooltip => 'Neue Aufgabe erstellen';

  @override
  String get memoryManagement => 'Erinnerungsverwaltung';

  @override
  String get filterMemories => 'Erinnerungen filtern';

  @override
  String totalMemoriesCount(int count) {
    return 'Sie haben insgesamt $count Erinnerungen';
  }

  @override
  String get publicMemories => 'Öffentliche Erinnerungen';

  @override
  String get privateMemories => 'Private Erinnerungen';

  @override
  String get makeAllPrivate => 'Alle Erinnerungen privat machen';

  @override
  String get makeAllPublic => 'Alle Erinnerungen öffentlich machen';

  @override
  String get deleteAllMemories => 'Alle Erinnerungen löschen';

  @override
  String get allMemoriesPrivateResult => 'Alle Erinnerungen sind jetzt privat';

  @override
  String get allMemoriesPublicResult => 'Alle Erinnerungen sind jetzt öffentlich';

  @override
  String get newMemory => 'Neue Erinnerung';

  @override
  String get editMemory => 'Erinnerung bearbeiten';

  @override
  String get memoryContentHint => 'Ich esse gerne Eis...';

  @override
  String get failedToSaveMemory => 'Speichern fehlgeschlagen. Bitte überprüfen Sie Ihre Verbindung.';

  @override
  String get saveMemory => 'Erinnerung speichern';

  @override
  String get retry => 'Wiederholen';

  @override
  String get createActionItem => 'Aufgabe erstellen';

  @override
  String get editActionItem => 'Aufgabe bearbeiten';

  @override
  String get actionItemDescriptionHint => 'Was muss getan werden?';

  @override
  String get actionItemDescriptionEmpty => 'Aufgabenbeschreibung darf nicht leer sein.';

  @override
  String get actionItemUpdated => 'Aufgabe aktualisiert';

  @override
  String get failedToUpdateActionItem => 'Aufgabe konnte nicht aktualisiert werden';

  @override
  String get actionItemCreated => 'Aufgabe erstellt';

  @override
  String get failedToCreateActionItem => 'Aufgabe konnte nicht erstellt werden';

  @override
  String get dueDate => 'Fälligkeitsdatum';

  @override
  String get time => 'Zeit';

  @override
  String get addDueDate => 'Fälligkeitsdatum hinzufügen';

  @override
  String get pressDoneToSave => 'Drücken Sie Fertig zum Speichern';

  @override
  String get pressDoneToCreate => 'Drücken Sie Fertig zum Erstellen';

  @override
  String get filterAll => 'Alle';

  @override
  String get filterInteresting => 'Interessant';

  @override
  String get filterManual => 'Manuell';

  @override
  String get filterSystem => 'System';

  @override
  String get completed => 'Erledigt';

  @override
  String get markComplete => 'Als erledigt markieren';

  @override
  String get actionItemDeleted => 'Aufgabe gelöscht';

  @override
  String get failedToDeleteActionItem => 'Aufgabe konnte nicht gelöscht werden';

  @override
  String get deleteActionItemConfirmTitle => 'Aufgabe löschen';

  @override
  String get deleteActionItemConfirmMessage => 'Sind Sie sicher, dass Sie diese Aufgabe löschen möchten?';

  @override
  String get appLanguage => 'App-Sprache';
}
