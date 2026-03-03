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
  String get clear => 'Löschen';

  @override
  String get copyTranscript => 'Transkript kopieren';

  @override
  String get copySummary => 'Zusammenfassung kopieren';

  @override
  String get testPrompt => 'Prompt testen';

  @override
  String get reprocessConversation => 'Unterhaltung neu verarbeiten';

  @override
  String get deleteConversation => 'Gespräch löschen';

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
  String get noInternetConnection => 'Keine Internetverbindung';

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
  String get askOmi => 'Omi fragen';

  @override
  String get done => 'Fertig';

  @override
  String get disconnected => 'Getrennt';

  @override
  String get searching => 'Suche läuft...';

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
  String get sync => 'Synchronisieren';

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
  String get noConversationsYet => 'Noch keine Unterhaltungen';

  @override
  String get noStarredConversations => 'Keine markierten Gespräche';

  @override
  String get starConversationHint =>
      'Um eine Unterhaltung zu favorisieren, öffnen Sie sie und tippen Sie auf das Sternsymbol im Kopfbereich.';

  @override
  String get searchConversations => 'Konversationen durchsuchen...';

  @override
  String selectedCount(int count, Object s) {
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
  String get deletingMessages => 'Ihre Nachrichten werden aus Omis Speicher gelöscht...';

  @override
  String get messageCopied => '✨ Nachricht in Zwischenablage kopiert';

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
  String get clearChat => 'Chat löschen';

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
  String get searchApps => 'Apps suchen...';

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
  String get identifyingOthers => 'Identifizierung Anderer';

  @override
  String get paymentMethods => 'Zahlungsmethoden';

  @override
  String get conversationDisplay => 'Gesprächsanzeige';

  @override
  String get dataPrivacy => 'Datenschutz';

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
  String get offlineSync => 'Offline-Synchronisierung';

  @override
  String get deviceSettings => 'Geräteeinstellungen';

  @override
  String get integrations => 'Integrationen';

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
  String get sdCardSync => 'SD-Karten-Synchronisierung';

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
  String get saving => 'Wird gespeichert...';

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
  String get createKey => 'Schlüssel Erstellen';

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
  String get unlimitedPlan => 'Unbegrenzter Plan';

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
  String get upgradeToUnlimited => 'Auf unbegrenzt upgraden';

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
  String get knowledgeGraphDeleted => 'Wissensgraph gelöscht';

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
  String get header => 'Überschrift';

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
  String get conversationEvents => 'Unterhaltungsereignisse';

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
  String get integrationsFooter => 'Verbinden Sie Ihre Apps, um Daten und Metriken im Chat anzuzeigen.';

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
  String get primaryLanguage => 'Hauptsprache';

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
  String get editName => 'Name bearbeiten';

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
  String get noUpcomingMeetings => 'Keine bevorstehenden Termine';

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
  String get yesterday => 'Gestern';

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
  String get omiUnlimited => 'Omi Unbegrenzt';

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
  String deviceUsesCodec(String device, String reason) {
    return '$device verwendet $reason. Omi wird verwendet.';
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
  String get appName => 'App Name';

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
  String get makePublic => 'Öffentlich machen';

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
  String get dontShowAgain => 'Nicht mehr anzeigen';

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
  String get speechProfileIntro => 'Omi muss Ihre Ziele und Ihre Stimme lernen. Sie können es später ändern.';

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
  String get whatsYourName => 'Wie heißen Sie?';

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
  String get personalGrowthJourney => 'Ihre persönliche Wachstumsreise mit KI, die auf jedes Ihrer Worte hört.';

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
  String get deleteActionItemTitle => 'Aktionselement löschen';

  @override
  String get deleteActionItemMessage => 'Möchten Sie dieses Aktionselement wirklich löschen?';

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
  String get searchMemories => 'Erinnerungen durchsuchen...';

  @override
  String get memoryDeleted => 'Erinnerung gelöscht.';

  @override
  String get undo => 'Rückgängig';

  @override
  String get noMemoriesYet => '🧠 Noch keine Erinnerungen';

  @override
  String get noAutoMemories => 'Noch keine automatischen Erinnerungen';

  @override
  String get noManualMemories => 'Noch keine manuellen Erinnerungen';

  @override
  String get noMemoriesInCategories => 'Keine Erinnerungen in diesen Kategorien';

  @override
  String get noMemoriesFound => '🔍 Keine Erinnerungen gefunden';

  @override
  String get addFirstMemory => 'Fügen Sie Ihre erste Erinnerung hinzu';

  @override
  String get clearMemoryTitle => 'Omis Gedächtnis löschen';

  @override
  String get clearMemoryMessage =>
      'Sind Sie sicher, dass Sie Omis Gedächtnis löschen möchten? Diese Aktion kann nicht rückgängig gemacht werden.';

  @override
  String get clearMemoryButton => 'Erinnerung löschen';

  @override
  String get memoryClearedSuccess => 'Omis Gedächtnis über Sie wurde gelöscht';

  @override
  String get noMemoriesToDelete => 'Keine Erinnerungen zum Löschen';

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
  String get newMemory => '✨ Neue Erinnerung';

  @override
  String get editMemory => '✏️ Erinnerung bearbeiten';

  @override
  String get memoryContentHint => 'Ich esse gerne Eis...';

  @override
  String get failedToSaveMemory => 'Speichern fehlgeschlagen. Bitte überprüfen Sie Ihre Verbindung.';

  @override
  String get saveMemory => 'Erinnerung speichern';

  @override
  String get retry => 'Erneut versuchen';

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
  String get filterSystem => 'Über Sie';

  @override
  String get filterInteresting => 'Einblicke';

  @override
  String get filterManual => 'Manuell';

  @override
  String get completed => 'Abgeschlossen';

  @override
  String get markComplete => 'Als abgeschlossen markieren';

  @override
  String get actionItemDeleted => 'Aktionselement gelöscht';

  @override
  String get failedToDeleteActionItem => 'Aufgabe konnte nicht gelöscht werden';

  @override
  String get deleteActionItemConfirmTitle => 'Aufgabe löschen';

  @override
  String get deleteActionItemConfirmMessage => 'Sind Sie sicher, dass Sie diese Aufgabe löschen möchten?';

  @override
  String get appLanguage => 'App-Sprache';

  @override
  String get appInterfaceSectionTitle => 'APP-OBERFLÄCHE';

  @override
  String get speechTranscriptionSectionTitle => 'SPRACHE UND TRANSKRIPTION';

  @override
  String get languageSettingsHelperText =>
      'Die App-Sprache ändert Menüs und Schaltflächen. Die Sprachsprache beeinflusst, wie Ihre Aufnahmen transkribiert werden.';

  @override
  String get translationNotice => 'Übersetzungshinweis';

  @override
  String get translationNoticeMessage =>
      'Omi übersetzt Unterhaltungen in Ihre Hauptsprache. Aktualisieren Sie diese jederzeit unter Einstellungen → Profile.';

  @override
  String get pleaseCheckInternetConnection =>
      'Bitte überprüfen Sie Ihre Internetverbindung und versuchen Sie es erneut';

  @override
  String get pleaseSelectReason => 'Bitte wählen Sie einen Grund aus';

  @override
  String get tellUsMoreWhatWentWrong => 'Erzählen Sie uns mehr darüber, was schief gelaufen ist...';

  @override
  String get selectText => 'Text auswählen';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Maximal $count Ziele erlaubt';
  }

  @override
  String get conversationCannotBeMerged =>
      'Diese Unterhaltung kann nicht zusammengeführt werden (gesperrt oder wird bereits zusammengeführt)';

  @override
  String get pleaseEnterFolderName => 'Bitte geben Sie einen Ordnernamen ein';

  @override
  String get failedToCreateFolder => 'Ordner konnte nicht erstellt werden';

  @override
  String get failedToUpdateFolder => 'Ordner konnte nicht aktualisiert werden';

  @override
  String get folderName => 'Ordnername';

  @override
  String get descriptionOptional => 'Beschreibung (optional)';

  @override
  String get failedToDeleteFolder => 'Ordner konnte nicht gelöscht werden';

  @override
  String get editFolder => 'Ordner bearbeiten';

  @override
  String get deleteFolder => 'Ordner löschen';

  @override
  String get transcriptCopiedToClipboard => 'Transkript in Zwischenablage kopiert';

  @override
  String get summaryCopiedToClipboard => 'Zusammenfassung in Zwischenablage kopiert';

  @override
  String get conversationUrlCouldNotBeShared => 'Konversations-URL konnte nicht geteilt werden.';

  @override
  String get urlCopiedToClipboard => 'URL in Zwischenablage kopiert';

  @override
  String get exportTranscript => 'Transkript exportieren';

  @override
  String get exportSummary => 'Zusammenfassung exportieren';

  @override
  String get exportButton => 'Exportieren';

  @override
  String get actionItemsCopiedToClipboard => 'Aktionselemente in Zwischenablage kopiert';

  @override
  String get summarize => 'Zusammenfassen';

  @override
  String get generateSummary => 'Zusammenfassung erstellen';

  @override
  String get conversationNotFoundOrDeleted => 'Unterhaltung nicht gefunden oder wurde gelöscht';

  @override
  String get deleteMemory => 'Erinnerung löschen';

  @override
  String get thisActionCannotBeUndone => 'Diese Aktion kann nicht rückgängig gemacht werden.';

  @override
  String memoriesCount(int count) {
    return '$count Erinnerungen';
  }

  @override
  String get noMemoriesInCategory => 'Noch keine Erinnerungen in dieser Kategorie';

  @override
  String get addYourFirstMemory => 'Füge deine erste Erinnerung hinzu';

  @override
  String get firmwareDisconnectUsb => 'USB trennen';

  @override
  String get firmwareUsbWarning => 'USB-Verbindung während Updates kann Ihr Gerät beschädigen.';

  @override
  String get firmwareBatteryAbove15 => 'Batterie über 15%';

  @override
  String get firmwareEnsureBattery => 'Stellen Sie sicher, dass Ihr Gerät 15% Batterie hat.';

  @override
  String get firmwareStableConnection => 'Stabile Verbindung';

  @override
  String get firmwareConnectWifi => 'Verbinden Sie sich mit WiFi oder Mobilfunk.';

  @override
  String failedToStartUpdate(String error) {
    return 'Update konnte nicht gestartet werden: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'Vor dem Update sicherstellen:';

  @override
  String get confirmed => 'Bestätigt!';

  @override
  String get release => 'Loslassen';

  @override
  String get slideToUpdate => 'Zum Aktualisieren wischen';

  @override
  String copiedToClipboard(String title) {
    return '$title in Zwischenablage kopiert';
  }

  @override
  String get batteryLevel => 'Batteriestand';

  @override
  String get productUpdate => 'Produktaktualisierung';

  @override
  String get offline => 'Offline';

  @override
  String get available => 'Verfügbar';

  @override
  String get unpairDeviceDialogTitle => 'Gerät entkoppeln';

  @override
  String get unpairDeviceDialogMessage =>
      'Dies entkoppelt das Gerät, damit es mit einem anderen Telefon verbunden werden kann. Sie müssen zu Einstellungen > Bluetooth gehen und das Gerät vergessen, um den Vorgang abzuschließen.';

  @override
  String get unpair => 'Entkoppeln';

  @override
  String get unpairAndForgetDevice => 'Gerät entkoppeln und vergessen';

  @override
  String get unknownDevice => 'Unbekannt';

  @override
  String get unknown => 'Unbekannt';

  @override
  String get productName => 'Produktname';

  @override
  String get serialNumber => 'Seriennummer';

  @override
  String get connected => 'Verbunden';

  @override
  String get privacyPolicyTitle => 'Datenschutzrichtlinie';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label kopiert';
  }

  @override
  String get noApiKeysYet => 'Noch keine API-Schlüssel. Erstellen Sie einen zur Integration mit Ihrer App.';

  @override
  String get createKeyToGetStarted => 'Erstellen Sie einen Schlüssel, um zu beginnen';

  @override
  String get persona => 'Persona';

  @override
  String get configureYourAiPersona => 'Konfigurieren Sie Ihre KI-Persona';

  @override
  String get configureSttProvider => 'STT-Anbieter konfigurieren';

  @override
  String get setWhenConversationsAutoEnd => 'Legen Sie fest, wann Gespräche automatisch enden';

  @override
  String get importDataFromOtherSources => 'Daten aus anderen Quellen importieren';

  @override
  String get debugAndDiagnostics => 'Debug & Diagnose';

  @override
  String get autoDeletesAfter3Days => 'Wird nach 3 Tagen automatisch gelöscht';

  @override
  String get helpsDiagnoseIssues => 'Hilft bei der Diagnose von Problemen';

  @override
  String get exportStartedMessage => 'Export gestartet. Dies kann einige Sekunden dauern...';

  @override
  String get exportConversationsToJson => 'Gespräche in eine JSON-Datei exportieren';

  @override
  String get knowledgeGraphDeletedSuccess => 'Wissensgraph erfolgreich gelöscht';

  @override
  String failedToDeleteGraph(String error) {
    return 'Graph konnte nicht gelöscht werden: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'Alle Knoten und Verbindungen löschen';

  @override
  String get addToClaudeDesktopConfig => 'Zu claude_desktop_config.json hinzufügen';

  @override
  String get connectAiAssistantsToData => 'KI-Assistenten mit Ihren Daten verbinden';

  @override
  String get useYourMcpApiKey => 'Verwenden Sie Ihren MCP-API-Schlüssel';

  @override
  String get realTimeTranscript => 'Echtzeit-Transkript';

  @override
  String get experimental => 'Experimentell';

  @override
  String get transcriptionDiagnostics => 'Transkriptions-Diagnose';

  @override
  String get detailedDiagnosticMessages => 'Detaillierte Diagnosemeldungen';

  @override
  String get autoCreateSpeakers => 'Sprecher automatisch erstellen';

  @override
  String get autoCreateWhenNameDetected => 'Automatisch erstellen, wenn Name erkannt wird';

  @override
  String get followUpQuestions => 'Folgefragen';

  @override
  String get suggestQuestionsAfterConversations => 'Fragen nach Gesprächen vorschlagen';

  @override
  String get goalTracker => 'Ziel-Tracker';

  @override
  String get trackPersonalGoalsOnHomepage => 'Verfolgen Sie Ihre persönlichen Ziele auf der Startseite';

  @override
  String get dailyReflection => 'Tägliche Reflexion';

  @override
  String get get9PmReminderToReflect => 'Erhalten Sie um 21 Uhr eine Erinnerung, über Ihren Tag nachzudenken';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'Aktionselementbeschreibung darf nicht leer sein';

  @override
  String get saved => 'Gespeichert';

  @override
  String get overdue => 'Überfällig';

  @override
  String get failedToUpdateDueDate => 'Aktualisierung des Fälligkeitsdatums fehlgeschlagen';

  @override
  String get markIncomplete => 'Als unvollständig markieren';

  @override
  String get editDueDate => 'Fälligkeitsdatum bearbeiten';

  @override
  String get setDueDate => 'Fälligkeitsdatum festlegen';

  @override
  String get clearDueDate => 'Fälligkeitsdatum löschen';

  @override
  String get failedToClearDueDate => 'Löschen des Fälligkeitsdatums fehlgeschlagen';

  @override
  String get mondayAbbr => 'Mo';

  @override
  String get tuesdayAbbr => 'Di';

  @override
  String get wednesdayAbbr => 'Mi';

  @override
  String get thursdayAbbr => 'Do';

  @override
  String get fridayAbbr => 'Fr';

  @override
  String get saturdayAbbr => 'Sa';

  @override
  String get sundayAbbr => 'So';

  @override
  String get howDoesItWork => 'Wie funktioniert es?';

  @override
  String get sdCardSyncDescription =>
      'SD-Karten-Synchronisierung importiert Ihre Erinnerungen von der SD-Karte in die App';

  @override
  String get checksForAudioFiles => 'Prüft auf Audiodateien auf der SD-Karte';

  @override
  String get omiSyncsAudioFiles => 'Omi synchronisiert dann die Audiodateien mit dem Server';

  @override
  String get serverProcessesAudio => 'Der Server verarbeitet die Audiodateien und erstellt Erinnerungen';

  @override
  String get youreAllSet => 'Alles bereit!';

  @override
  String get welcomeToOmiDescription =>
      'Willkommen bei Omi! Ihr KI-Begleiter ist bereit, Sie bei Gesprächen, Aufgaben und mehr zu unterstützen.';

  @override
  String get startUsingOmi => 'Omi verwenden';

  @override
  String get back => 'Zurück';

  @override
  String get keyboardShortcuts => 'Tastaturkürzel';

  @override
  String get toggleControlBar => 'Steuerleiste umschalten';

  @override
  String get pressKeys => 'Tasten drücken...';

  @override
  String get cmdRequired => '⌘ erforderlich';

  @override
  String get invalidKey => 'Ungültige Taste';

  @override
  String get space => 'Leertaste';

  @override
  String get search => 'Suchen';

  @override
  String get searchPlaceholder => 'Suchen...';

  @override
  String get untitledConversation => 'Unbenanntes Gespräch';

  @override
  String countRemaining(String count) {
    return '$count verbleibend';
  }

  @override
  String get addGoal => 'Ziel hinzufügen';

  @override
  String get editGoal => 'Ziel bearbeiten';

  @override
  String get icon => 'Symbol';

  @override
  String get goalTitle => 'Zieltitel';

  @override
  String get current => 'Aktuell';

  @override
  String get target => 'Ziel';

  @override
  String get saveGoal => 'Speichern';

  @override
  String get goals => 'Ziele';

  @override
  String get tapToAddGoal => 'Tippen, um ein Ziel hinzuzufügen';

  @override
  String welcomeBack(String name) {
    return 'Willkommen zurück, $name';
  }

  @override
  String get yourConversations => 'Deine Unterhaltungen';

  @override
  String get reviewAndManageConversations => 'Überprüfe und verwalte deine aufgenommenen Unterhaltungen';

  @override
  String get startCapturingConversations =>
      'Beginne Unterhaltungen mit deinem Omi-Gerät aufzunehmen, um sie hier zu sehen.';

  @override
  String get useMobileAppToCapture => 'Verwende deine mobile App, um Audio aufzunehmen';

  @override
  String get conversationsProcessedAutomatically => 'Unterhaltungen werden automatisch verarbeitet';

  @override
  String get getInsightsInstantly => 'Erhalte sofort Einblicke und Zusammenfassungen';

  @override
  String get showAll => 'Alle anzeigen →';

  @override
  String get noTasksForToday => 'Keine Aufgaben für heute.\\nFrage Omi nach mehr Aufgaben oder erstelle sie manuell.';

  @override
  String get dailyScore => 'TAGES-SCORE';

  @override
  String get dailyScoreDescription => 'Ein Score, der Ihnen hilft,\nsich besser auf die Ausführung zu konzentrieren.';

  @override
  String get searchResults => 'Suchergebnisse';

  @override
  String get actionItems => 'Aufgaben';

  @override
  String get tasksToday => 'Heute';

  @override
  String get tasksTomorrow => 'Morgen';

  @override
  String get tasksNoDeadline => 'Keine Frist';

  @override
  String get tasksLater => 'Später';

  @override
  String get loadingTasks => 'Aufgaben werden geladen...';

  @override
  String get tasks => 'Aufgaben';

  @override
  String get swipeTasksToIndent => 'Wischen Sie Aufgaben zum Einrücken, ziehen Sie zwischen Kategorien';

  @override
  String get create => 'Erstellen';

  @override
  String get noTasksYet => 'Noch keine Aufgaben';

  @override
  String get tasksFromConversationsWillAppear =>
      'Aufgaben aus Ihren Gesprächen werden hier angezeigt.\nKlicken Sie auf Erstellen, um eine manuell hinzuzufügen.';

  @override
  String get monthJan => 'Jan';

  @override
  String get monthFeb => 'Feb';

  @override
  String get monthMar => 'Mär';

  @override
  String get monthApr => 'Apr';

  @override
  String get monthMay => 'Mai';

  @override
  String get monthJun => 'Jun';

  @override
  String get monthJul => 'Jul';

  @override
  String get monthAug => 'Aug';

  @override
  String get monthSep => 'Sep';

  @override
  String get monthOct => 'Okt';

  @override
  String get monthNov => 'Nov';

  @override
  String get monthDec => 'Dez';

  @override
  String get timePM => 'PM';

  @override
  String get timeAM => 'AM';

  @override
  String get actionItemUpdatedSuccessfully => 'Aufgabe erfolgreich aktualisiert';

  @override
  String get actionItemCreatedSuccessfully => 'Aufgabe erfolgreich erstellt';

  @override
  String get actionItemDeletedSuccessfully => 'Aufgabe erfolgreich gelöscht';

  @override
  String get deleteActionItem => 'Aufgabe löschen';

  @override
  String get deleteActionItemConfirmation =>
      'Möchten Sie diese Aufgabe wirklich löschen? Diese Aktion kann nicht rückgängig gemacht werden.';

  @override
  String get enterActionItemDescription => 'Aufgabenbeschreibung eingeben...';

  @override
  String get markAsCompleted => 'Als erledigt markieren';

  @override
  String get setDueDateAndTime => 'Fälligkeitsdatum und Uhrzeit festlegen';

  @override
  String get reloadingApps => 'Apps werden neu geladen...';

  @override
  String get loadingApps => 'Apps werden geladen...';

  @override
  String get browseInstallCreateApps => 'Apps durchsuchen, installieren und erstellen';

  @override
  String get all => 'All';

  @override
  String get open => 'Öffnen';

  @override
  String get install => 'Installieren';

  @override
  String get noAppsAvailable => 'Keine Apps verfügbar';

  @override
  String get unableToLoadApps => 'Apps können nicht geladen werden';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'Versuchen Sie, Ihre Suchbegriffe oder Filter anzupassen';

  @override
  String get checkBackLaterForNewApps => 'Schauen Sie später nach neuen Apps';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain =>
      'Bitte überprüfen Sie Ihre Internetverbindung und versuchen Sie es erneut';

  @override
  String get createNewApp => 'Neue App erstellen';

  @override
  String get buildSubmitCustomOmiApp => 'Erstellen und senden Sie Ihre benutzerdefinierte Omi-App';

  @override
  String get submittingYourApp => 'Ihre App wird eingereicht...';

  @override
  String get preparingFormForYou => 'Das Formular wird für Sie vorbereitet...';

  @override
  String get appDetails => 'App-Details';

  @override
  String get paymentDetails => 'Zahlungsdetails';

  @override
  String get previewAndScreenshots => 'Vorschau und Screenshots';

  @override
  String get appCapabilities => 'App-Funktionen';

  @override
  String get aiPrompts => 'KI-Eingabeaufforderungen';

  @override
  String get chatPrompt => 'Chat-Eingabeaufforderung';

  @override
  String get chatPromptPlaceholder =>
      'Sie sind eine großartige App, Ihre Aufgabe ist es, auf Benutzeranfragen zu antworten und ihnen ein gutes Gefühl zu geben...';

  @override
  String get conversationPrompt => 'Gesprächsaufforderung';

  @override
  String get conversationPromptPlaceholder =>
      'Sie sind eine großartige App, Sie erhalten ein Transkript und eine Zusammenfassung eines Gesprächs...';

  @override
  String get notificationScopes => 'Benachrichtigungsbereiche';

  @override
  String get appPrivacyAndTerms => 'App-Datenschutz und -Bedingungen';

  @override
  String get makeMyAppPublic => 'Meine App öffentlich machen';

  @override
  String get submitAppTermsAgreement =>
      'Mit der Einreichung dieser App stimme ich den Nutzungsbedingungen und der Datenschutzrichtlinie von Omi AI zu';

  @override
  String get submitApp => 'App einreichen';

  @override
  String get needHelpGettingStarted => 'Benötigen Sie Hilfe beim Einstieg?';

  @override
  String get clickHereForAppBuildingGuides => 'Klicken Sie hier für App-Erstellungsanleitungen und Dokumentation';

  @override
  String get submitAppQuestion => 'App einreichen?';

  @override
  String get submitAppPublicDescription =>
      'Ihre App wird überprüft und veröffentlicht. Sie können sie sofort verwenden, auch während der Überprüfung!';

  @override
  String get submitAppPrivateDescription =>
      'Ihre App wird überprüft und Ihnen privat zur Verfügung gestellt. Sie können sie sofort verwenden, auch während der Überprüfung!';

  @override
  String get startEarning => 'Beginnen Sie zu verdienen! 💰';

  @override
  String get connectStripeOrPayPal => 'Verbinden Sie Stripe oder PayPal, um Zahlungen für Ihre App zu erhalten.';

  @override
  String get connectNow => 'Jetzt verbinden';

  @override
  String get installsCount => 'Installationen';

  @override
  String get uninstallApp => 'App deinstallieren';

  @override
  String get subscribe => 'Abonnieren';

  @override
  String get dataAccessNotice => 'Datenzugriffshinweis';

  @override
  String get dataAccessWarning =>
      'Diese App greift auf Ihre Daten zu. Omi AI ist nicht verantwortlich dafür, wie Ihre Daten von dieser App verwendet, geändert oder gelöscht werden';

  @override
  String get installApp => 'App installieren';

  @override
  String get betaTesterNotice =>
      'Sie sind Beta-Tester für diese App. Sie ist noch nicht öffentlich. Sie wird öffentlich, sobald sie genehmigt wurde.';

  @override
  String get appUnderReviewOwner =>
      'Ihre App wird überprüft und ist nur für Sie sichtbar. Sie wird öffentlich, sobald sie genehmigt wurde.';

  @override
  String get appRejectedNotice =>
      'Ihre App wurde abgelehnt. Bitte aktualisieren Sie die App-Details und reichen Sie sie erneut zur Überprüfung ein.';

  @override
  String get setupSteps => 'Einrichtungsschritte';

  @override
  String get setupInstructions => 'Einrichtungsanweisungen';

  @override
  String get integrationInstructions => 'Integrationsanleitung';

  @override
  String get preview => 'Vorschau';

  @override
  String get aboutTheApp => 'Über die App';

  @override
  String get aboutThePersona => 'Über die Persona';

  @override
  String get chatPersonality => 'Chat-Persönlichkeit';

  @override
  String get ratingsAndReviews => 'Bewertungen & Rezensionen';

  @override
  String get noRatings => 'keine Bewertungen';

  @override
  String ratingsCount(String count) {
    return '$count+ Bewertungen';
  }

  @override
  String get errorActivatingApp => 'Fehler beim Aktivieren der App';

  @override
  String get integrationSetupRequired =>
      'Wenn dies eine Integrations-App ist, stellen Sie sicher, dass die Einrichtung abgeschlossen ist.';

  @override
  String get installed => 'Installiert';

  @override
  String get appIdLabel => 'App-ID';

  @override
  String get appNameLabel => 'App-Name';

  @override
  String get appNamePlaceholder => 'Meine fantastische App';

  @override
  String get pleaseEnterAppName => 'Bitte geben Sie einen App-Namen ein';

  @override
  String get categoryLabel => 'Kategorie';

  @override
  String get selectCategory => 'Kategorie auswählen';

  @override
  String get descriptionLabel => 'Beschreibung';

  @override
  String get appDescriptionPlaceholder =>
      'Meine fantastische App ist eine großartige App, die erstaunliche Dinge tut. Sie ist die beste App aller Zeiten!';

  @override
  String get pleaseProvideValidDescription => 'Bitte geben Sie eine gültige Beschreibung an';

  @override
  String get appPricingLabel => 'App-Preisgestaltung';

  @override
  String get noneSelected => 'Keine ausgewählt';

  @override
  String get appIdCopiedToClipboard => 'App-ID in Zwischenablage kopiert';

  @override
  String get appCategoryModalTitle => 'App-Kategorie';

  @override
  String get pricingFree => 'Kostenlos';

  @override
  String get pricingPaid => 'Kostenpflichtig';

  @override
  String get loadingCapabilities => 'Funktionen werden geladen...';

  @override
  String get filterInstalled => 'Installiert';

  @override
  String get filterMyApps => 'Meine Apps';

  @override
  String get clearSelection => 'Auswahl löschen';

  @override
  String get filterCategory => 'Kategorie';

  @override
  String get rating4PlusStars => '4+ Sterne';

  @override
  String get rating3PlusStars => '3+ Sterne';

  @override
  String get rating2PlusStars => '2+ Sterne';

  @override
  String get rating1PlusStars => '1+ Sterne';

  @override
  String get filterRating => 'Bewertung';

  @override
  String get filterCapabilities => 'Funktionen';

  @override
  String get noNotificationScopesAvailable => 'Keine Benachrichtigungsbereiche verfügbar';

  @override
  String get popularApps => 'Beliebte Apps';

  @override
  String get pleaseProvidePrompt => 'Bitte geben Sie eine Eingabeaufforderung an';

  @override
  String chatWithAppName(String appName) {
    return 'Chat mit $appName';
  }

  @override
  String get defaultAiAssistant => 'Standard-KI-Assistent';

  @override
  String get readyToChat => '✨ Bereit zum Chatten!';

  @override
  String get connectionNeeded => '🌐 Verbindung erforderlich';

  @override
  String get startConversation => 'Starten Sie ein Gespräch und lassen Sie die Magie beginnen';

  @override
  String get checkInternetConnection => 'Bitte überprüfen Sie Ihre Internetverbindung';

  @override
  String get wasThisHelpful => 'War das hilfreich?';

  @override
  String get thankYouForFeedback => 'Vielen Dank für Ihr Feedback!';

  @override
  String get maxFilesUploadError => 'Sie können nur 4 Dateien gleichzeitig hochladen';

  @override
  String get attachedFiles => '📎 Angehängte Dateien';

  @override
  String get takePhoto => 'Foto aufnehmen';

  @override
  String get captureWithCamera => 'Mit Kamera aufnehmen';

  @override
  String get selectImages => 'Bilder auswählen';

  @override
  String get chooseFromGallery => 'Aus Galerie wählen';

  @override
  String get selectFile => 'Datei auswählen';

  @override
  String get chooseAnyFileType => 'Beliebigen Dateityp wählen';

  @override
  String get cannotReportOwnMessages => 'Sie können Ihre eigenen Nachrichten nicht melden';

  @override
  String get messageReportedSuccessfully => '✅ Nachricht erfolgreich gemeldet';

  @override
  String get confirmReportMessage => 'Möchten Sie diese Nachricht wirklich melden?';

  @override
  String get selectChatAssistant => 'Chat-Assistenten auswählen';

  @override
  String get enableMoreApps => 'Weitere Apps aktivieren';

  @override
  String get chatCleared => 'Chat gelöscht';

  @override
  String get clearChatTitle => 'Chat löschen?';

  @override
  String get confirmClearChat =>
      'Möchten Sie den Chat wirklich löschen? Diese Aktion kann nicht rückgängig gemacht werden.';

  @override
  String get copy => 'Kopieren';

  @override
  String get share => 'Teilen';

  @override
  String get report => 'Melden';

  @override
  String get microphonePermissionRequired => 'Mikrofonberechtigung ist für Sprachaufnahmen erforderlich.';

  @override
  String get microphonePermissionDenied =>
      'Mikrofonberechtigung verweigert. Bitte erteilen Sie die Berechtigung in Systemeinstellungen > Datenschutz & Sicherheit > Mikrofon.';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'Mikrofonberechtigung konnte nicht überprüft werden: $error';
  }

  @override
  String get failedToTranscribeAudio => 'Audio konnte nicht transkribiert werden';

  @override
  String get transcribing => 'Transkribieren...';

  @override
  String get transcriptionFailed => 'Transkription fehlgeschlagen';

  @override
  String get discardedConversation => 'Verworfene Unterhaltung';

  @override
  String get at => 'um';

  @override
  String get from => 'von';

  @override
  String get copied => 'Kopiert!';

  @override
  String get copyLink => 'Link kopieren';

  @override
  String get hideTranscript => 'Transkript ausblenden';

  @override
  String get viewTranscript => 'Transkript anzeigen';

  @override
  String get conversationDetails => 'Gesprächsdetails';

  @override
  String get transcript => 'Transkript';

  @override
  String segmentsCount(int count) {
    return '$count Segmente';
  }

  @override
  String get noTranscriptAvailable => 'Kein Transkript verfügbar';

  @override
  String get noTranscriptMessage => 'Dieses Gespräch hat kein Transkript.';

  @override
  String get conversationUrlCouldNotBeGenerated => 'Gesprächs-URL konnte nicht generiert werden.';

  @override
  String get failedToGenerateConversationLink => 'Fehler beim Generieren des Gesprächslinks';

  @override
  String get failedToGenerateShareLink => 'Fehler beim Generieren des Freigabe-Links';

  @override
  String get reloadingConversations => 'Gespräche werden neu geladen...';

  @override
  String get user => 'Benutzer';

  @override
  String get starred => 'Markiert';

  @override
  String get date => 'Datum';

  @override
  String get noResultsFound => 'Keine Ergebnisse gefunden';

  @override
  String get tryAdjustingSearchTerms => 'Versuchen Sie, Ihre Suchbegriffe anzupassen';

  @override
  String get starConversationsToFindQuickly => 'Markieren Sie Gespräche, um sie hier schnell zu finden';

  @override
  String noConversationsOnDate(String date) {
    return 'Keine Gespräche am $date';
  }

  @override
  String get trySelectingDifferentDate => 'Versuchen Sie, ein anderes Datum auszuwählen';

  @override
  String get conversations => 'Gespräche';

  @override
  String get chat => 'Chat';

  @override
  String get actions => 'Aktionen';

  @override
  String get syncAvailable => 'Synchronisierung verfügbar';

  @override
  String get referAFriend => 'Einen Freund empfehlen';

  @override
  String get help => 'Hilfe';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'Auf Pro upgraden';

  @override
  String get getOmiDevice => 'Omi-Gerät holen';

  @override
  String get wearableAiCompanion => 'Tragbarer KI-Begleiter';

  @override
  String get loadingMemories => 'Erinnerungen werden geladen...';

  @override
  String get allMemories => 'Alle Erinnerungen';

  @override
  String get aboutYou => 'Über dich';

  @override
  String get manual => 'Manuell';

  @override
  String get loadingYourMemories => 'Deine Erinnerungen werden geladen...';

  @override
  String get createYourFirstMemory => 'Erstelle deine erste Erinnerung, um zu beginnen';

  @override
  String get tryAdjustingFilter => 'Versuche, deine Suche oder den Filter anzupassen';

  @override
  String get whatWouldYouLikeToRemember => 'Woran möchten Sie sich erinnern?';

  @override
  String get category => 'Kategorie';

  @override
  String get public => 'Öffentlich';

  @override
  String get failedToSaveCheckConnection => 'Speichern fehlgeschlagen. Bitte Verbindung überprüfen.';

  @override
  String get createMemory => 'Erinnerung erstellen';

  @override
  String get deleteMemoryConfirmation =>
      'Möchten Sie diese Erinnerung wirklich löschen? Diese Aktion kann nicht rückgängig gemacht werden.';

  @override
  String get makePrivate => 'Privat machen';

  @override
  String get organizeAndControlMemories => 'Organisieren und steuern Sie Ihre Erinnerungen';

  @override
  String get total => 'Gesamt';

  @override
  String get makeAllMemoriesPrivate => 'Alle Erinnerungen privat machen';

  @override
  String get setAllMemoriesToPrivate => 'Alle Erinnerungen auf private Sichtbarkeit setzen';

  @override
  String get makeAllMemoriesPublic => 'Alle Erinnerungen öffentlich machen';

  @override
  String get setAllMemoriesToPublic => 'Alle Erinnerungen auf öffentliche Sichtbarkeit setzen';

  @override
  String get permanentlyRemoveAllMemories => 'Alle Erinnerungen dauerhaft aus Omi entfernen';

  @override
  String get allMemoriesAreNowPrivate => 'Alle Erinnerungen sind jetzt privat';

  @override
  String get allMemoriesAreNowPublic => 'Alle Erinnerungen sind jetzt öffentlich';

  @override
  String get clearOmisMemory => 'Omis Erinnerung löschen';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Möchten Sie Omis Erinnerung wirklich löschen? Diese Aktion kann nicht rückgängig gemacht werden und wird alle $count Erinnerungen dauerhaft löschen.';
  }

  @override
  String get omisMemoryCleared => 'Omis Erinnerung an Sie wurde gelöscht';

  @override
  String get welcomeToOmi => 'Willkommen bei Omi';

  @override
  String get continueWithApple => 'Mit Apple fortfahren';

  @override
  String get continueWithGoogle => 'Mit Google fortfahren';

  @override
  String get byContinuingYouAgree => 'Indem Sie fortfahren, stimmen Sie unseren ';

  @override
  String get termsOfService => 'Nutzungsbedingungen';

  @override
  String get and => ' und ';

  @override
  String get dataAndPrivacy => 'Daten & Datenschutz';

  @override
  String get secureAuthViaAppleId => 'Sichere Authentifizierung über Apple ID';

  @override
  String get secureAuthViaGoogleAccount => 'Sichere Authentifizierung über Google-Konto';

  @override
  String get whatWeCollect => 'Was wir sammeln';

  @override
  String get dataCollectionMessage =>
      'Durch Fortfahren werden Ihre Gespräche, Aufnahmen und persönlichen Informationen sicher auf unseren Servern gespeichert, um KI-gestützte Einblicke zu bieten und alle App-Funktionen zu ermöglichen.';

  @override
  String get dataProtection => 'Datenschutz';

  @override
  String get yourDataIsProtected => 'Ihre Daten sind geschützt und unterliegen unserer ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'Bitte wählen Sie Ihre Hauptsprache';

  @override
  String get chooseYourLanguage => 'Wählen Sie Ihre Sprache';

  @override
  String get selectPreferredLanguageForBestExperience =>
      'Wählen Sie Ihre bevorzugte Sprache für das beste Omi-Erlebnis';

  @override
  String get searchLanguages => 'Sprachen suchen...';

  @override
  String get selectALanguage => 'Wählen Sie eine Sprache';

  @override
  String get tryDifferentSearchTerm => 'Versuchen Sie einen anderen Suchbegriff';

  @override
  String get pleaseEnterYourName => 'Bitte geben Sie Ihren Namen ein';

  @override
  String get nameMustBeAtLeast2Characters => 'Der Name muss mindestens 2 Zeichen lang sein';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'Sagen Sie uns, wie Sie angesprochen werden möchten. Dies hilft, Ihr Omi-Erlebnis zu personalisieren.';

  @override
  String charactersCount(int count) {
    return '$count Zeichen';
  }

  @override
  String get enableFeaturesForBestExperience => 'Aktivieren Sie Funktionen für das beste Omi-Erlebnis auf Ihrem Gerät.';

  @override
  String get microphoneAccess => 'Mikrofonzugriff';

  @override
  String get recordAudioConversations => 'Audio-Gespräche aufzeichnen';

  @override
  String get microphoneAccessDescription =>
      'Omi benötigt Mikrofonzugriff, um Ihre Gespräche aufzuzeichnen und Transkriptionen bereitzustellen.';

  @override
  String get screenRecording => 'Bildschirmaufzeichnung';

  @override
  String get captureSystemAudioFromMeetings => 'System-Audio von Besprechungen erfassen';

  @override
  String get screenRecordingDescription =>
      'Omi benötigt die Berechtigung zur Bildschirmaufzeichnung, um System-Audio von Ihren browserbasierten Besprechungen zu erfassen.';

  @override
  String get accessibility => 'Barrierefreiheit';

  @override
  String get detectBrowserBasedMeetings => 'Browserbasierte Besprechungen erkennen';

  @override
  String get accessibilityDescription =>
      'Omi benötigt die Berechtigung für Barrierefreiheit, um zu erkennen, wann Sie Zoom-, Meet- oder Teams-Besprechungen in Ihrem Browser beitreten.';

  @override
  String get pleaseWait => 'Bitte warten...';

  @override
  String get joinTheCommunity => 'Treten Sie der Community bei!';

  @override
  String get loadingProfile => 'Profil wird geladen...';

  @override
  String get profileSettings => 'Profileinstellungen';

  @override
  String get noEmailSet => 'Keine E-Mail festgelegt';

  @override
  String get userIdCopiedToClipboard => 'Benutzer-ID kopiert';

  @override
  String get yourInformation => 'Ihre Informationen';

  @override
  String get setYourName => 'Namen festlegen';

  @override
  String get changeYourName => 'Namen ändern';

  @override
  String get manageYourOmiPersona => 'Verwalten Sie Ihre Omi-Persona';

  @override
  String get voiceAndPeople => 'Stimme & Personen';

  @override
  String get teachOmiYourVoice => 'Bringen Sie Omi Ihre Stimme bei';

  @override
  String get tellOmiWhoSaidIt => 'Sagen Sie Omi, wer es gesagt hat 🗣️';

  @override
  String get payment => 'Zahlung';

  @override
  String get addOrChangeYourPaymentMethod => 'Zahlungsmethode hinzufügen oder ändern';

  @override
  String get preferences => 'Einstellungen';

  @override
  String get helpImproveOmiBySharing => 'Helfen Sie, Omi zu verbessern, indem Sie anonymisierte Analysedaten teilen';

  @override
  String get deleteAccount => 'Konto Löschen';

  @override
  String get deleteYourAccountAndAllData => 'Löschen Sie Ihr Konto und alle Daten';

  @override
  String get clearLogs => 'Protokolle löschen';

  @override
  String get debugLogsCleared => 'Debug-Protokolle gelöscht';

  @override
  String get exportConversations => 'Unterhaltungen exportieren';

  @override
  String get exportAllConversationsToJson => 'Exportieren Sie alle Ihre Unterhaltungen in eine JSON-Datei.';

  @override
  String get conversationsExportStarted =>
      'Export der Unterhaltungen gestartet. Dies kann einige Sekunden dauern, bitte warten.';

  @override
  String get mcpDescription =>
      'Um Omi mit anderen Anwendungen zu verbinden, um Ihre Erinnerungen und Unterhaltungen zu lesen, zu durchsuchen und zu verwalten. Erstellen Sie einen Schlüssel, um loszulegen.';

  @override
  String get apiKeys => 'API-Schlüssel';

  @override
  String errorLabel(String error) {
    return 'Fehler: $error';
  }

  @override
  String get noApiKeysFound => 'Keine API-Schlüssel gefunden. Erstellen Sie einen, um loszulegen.';

  @override
  String get advancedSettings => 'Erweiterte Einstellungen';

  @override
  String get triggersWhenNewConversationCreated => 'Wird ausgelöst, wenn eine neue Unterhaltung erstellt wird.';

  @override
  String get triggersWhenNewTranscriptReceived => 'Wird ausgelöst, wenn ein neues Transkript empfangen wird.';

  @override
  String get realtimeAudioBytes => 'Echtzeit-Audio-Bytes';

  @override
  String get triggersWhenAudioBytesReceived => 'Wird ausgelöst, wenn Audio-Bytes empfangen werden.';

  @override
  String get everyXSeconds => 'Alle x Sekunden';

  @override
  String get triggersWhenDaySummaryGenerated => 'Wird ausgelöst, wenn die Tageszusammenfassung generiert wird.';

  @override
  String get tryLatestExperimentalFeatures => 'Probieren Sie die neuesten experimentellen Funktionen vom Omi-Team aus.';

  @override
  String get transcriptionServiceDiagnosticStatus => 'Diagnosestatus des Transkriptionsdienstes';

  @override
  String get enableDetailedDiagnosticMessages => 'Detaillierte Diagnosemeldungen vom Transkriptionsdienst aktivieren';

  @override
  String get autoCreateAndTagNewSpeakers => 'Neue Sprecher automatisch erstellen und kennzeichnen';

  @override
  String get automaticallyCreateNewPerson =>
      'Automatisch eine neue Person erstellen, wenn ein Name im Transkript erkannt wird.';

  @override
  String get pilotFeatures => 'Pilotfunktionen';

  @override
  String get pilotFeaturesDescription => 'Diese Funktionen sind Tests und es wird keine Unterstützung garantiert.';

  @override
  String get suggestFollowUpQuestion => 'Folgefrage vorschlagen';

  @override
  String get saveSettings => 'Einstellungen Speichern';

  @override
  String get syncingDeveloperSettings => 'Entwicklereinstellungen synchronisieren...';

  @override
  String get summary => 'Zusammenfassung';

  @override
  String get auto => 'Automatisch';

  @override
  String get noSummaryForApp =>
      'Keine Zusammenfassung für diese App verfügbar. Probieren Sie eine andere App für bessere Ergebnisse.';

  @override
  String get tryAnotherApp => 'Andere App ausprobieren';

  @override
  String generatedBy(String appName) {
    return 'Generiert von $appName';
  }

  @override
  String get overview => 'Übersicht';

  @override
  String get otherAppResults => 'Andere App-Ergebnisse';

  @override
  String get unknownApp => 'Unbekannte App';

  @override
  String get noSummaryAvailable => 'Keine Zusammenfassung verfügbar';

  @override
  String get conversationNoSummaryYet => 'Dieses Gespräch hat noch keine Zusammenfassung.';

  @override
  String get chooseSummarizationApp => 'Zusammenfassungs-App auswählen';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName als Standard-Zusammenfassungs-App festgelegt';
  }

  @override
  String get letOmiChooseAutomatically => 'Lassen Sie Omi automatisch die beste App auswählen';

  @override
  String get deleteConversationConfirmation =>
      'Möchten Sie dieses Gespräch wirklich löschen? Diese Aktion kann nicht rückgängig gemacht werden.';

  @override
  String get conversationDeleted => 'Gespräch gelöscht';

  @override
  String get generatingLink => 'Link wird generiert...';

  @override
  String get editConversation => 'Gespräch bearbeiten';

  @override
  String get conversationLinkCopiedToClipboard => 'Gesprächslink in Zwischenablage kopiert';

  @override
  String get conversationTranscriptCopiedToClipboard => 'Gesprächstranskript in Zwischenablage kopiert';

  @override
  String get editConversationDialogTitle => 'Gespräch bearbeiten';

  @override
  String get changeTheConversationTitle => 'Gesprächstitel ändern';

  @override
  String get conversationTitle => 'Gesprächstitel';

  @override
  String get enterConversationTitle => 'Gesprächstitel eingeben...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'Gesprächstitel erfolgreich aktualisiert';

  @override
  String get failedToUpdateConversationTitle => 'Fehler beim Aktualisieren des Gesprächstitels';

  @override
  String get errorUpdatingConversationTitle => 'Fehler beim Aktualisieren des Gesprächstitels';

  @override
  String get settingUp => 'Einrichten...';

  @override
  String get startYourFirstRecording => 'Starten Sie Ihre erste Aufnahme';

  @override
  String get preparingSystemAudioCapture => 'Systemtonaufnahme wird vorbereitet';

  @override
  String get clickTheButtonToCaptureAudio =>
      'Klicken Sie auf die Schaltfläche, um Audio für Live-Transkripte, KI-Einblicke und automatisches Speichern aufzunehmen.';

  @override
  String get reconnecting => 'Verbindung wird wiederhergestellt...';

  @override
  String get recordingPaused => 'Aufnahme pausiert';

  @override
  String get recordingActive => 'Aufnahme aktiv';

  @override
  String get startRecording => 'Aufnahme starten';

  @override
  String resumingInCountdown(String countdown) {
    return 'Fortsetzung in ${countdown}s...';
  }

  @override
  String get tapPlayToResume => 'Tippen Sie auf Abspielen, um fortzufahren';

  @override
  String get listeningForAudio => 'Auf Audio hören...';

  @override
  String get preparingAudioCapture => 'Audioaufnahme wird vorbereitet';

  @override
  String get clickToBeginRecording => 'Klicken Sie, um die Aufnahme zu starten';

  @override
  String get translated => 'übersetzt';

  @override
  String get liveTranscript => 'Live-Transkript';

  @override
  String segmentsSingular(String count) {
    return '$count Segment';
  }

  @override
  String segmentsPlural(String count) {
    return '$count Segmente';
  }

  @override
  String get startRecordingToSeeTranscript => 'Starten Sie die Aufnahme, um das Live-Transkript zu sehen';

  @override
  String get paused => 'Pausiert';

  @override
  String get initializing => 'Initialisierung...';

  @override
  String get recording => 'Aufnahme';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'Mikrofon geändert. Fortsetzung in ${countdown}s';
  }

  @override
  String get clickPlayToResumeOrStop => 'Klicken Sie auf Abspielen zum Fortsetzen oder Stopp zum Beenden';

  @override
  String get settingUpSystemAudioCapture => 'Systemtonaufnahme wird eingerichtet';

  @override
  String get capturingAudioAndGeneratingTranscript => 'Audio wird aufgenommen und Transkript wird generiert';

  @override
  String get clickToBeginRecordingSystemAudio => 'Klicken Sie, um die Systemtonaufnahme zu starten';

  @override
  String get you => 'Sie';

  @override
  String speakerWithId(String speakerId) {
    return 'Sprecher $speakerId';
  }

  @override
  String get translatedByOmi => 'übersetzt von omi';

  @override
  String get backToConversations => 'Zurück zu Gesprächen';

  @override
  String get systemAudio => 'Systemaudio';

  @override
  String get mic => 'Mikrofon';

  @override
  String audioInputSetTo(String deviceName) {
    return 'Audioeingang auf $deviceName gesetzt';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'Fehler beim Wechseln des Audiogeräts: $error';
  }

  @override
  String get selectAudioInput => 'Audioeingang auswählen';

  @override
  String get loadingDevices => 'Geräte werden geladen...';

  @override
  String get settingsHeader => 'EINSTELLUNGEN';

  @override
  String get plansAndBilling => 'Pläne & Abrechnung';

  @override
  String get calendarIntegration => 'Kalenderintegration';

  @override
  String get dailySummary => 'Tägliche Zusammenfassung';

  @override
  String get developer => 'Entwickler';

  @override
  String get about => 'Über';

  @override
  String get selectTime => 'Zeit auswählen';

  @override
  String get accountGroup => 'Konto';

  @override
  String get signOutQuestion => 'Abmelden?';

  @override
  String get signOutConfirmation => 'Bist du sicher, dass du dich abmelden möchtest?';

  @override
  String get customVocabularyHeader => 'BENUTZERDEFINIERTES VOKABULAR';

  @override
  String get addWordsDescription => 'Fügen Sie Wörter hinzu, die Omi während der Transkription erkennen soll.';

  @override
  String get enterWordsHint => 'Wörter eingeben (durch Kommas getrennt)';

  @override
  String get dailySummaryHeader => 'TÄGLICHE ZUSAMMENFASSUNG';

  @override
  String get dailySummaryTitle => 'Tägliche Zusammenfassung';

  @override
  String get dailySummaryDescription =>
      'Erhalten Sie eine personalisierte Zusammenfassung Ihrer Tagesgespräche als Benachrichtigung.';

  @override
  String get deliveryTime => 'Lieferzeit';

  @override
  String get deliveryTimeDescription => 'Wann Sie Ihre tägliche Zusammenfassung erhalten';

  @override
  String get subscription => 'Abonnement';

  @override
  String get viewPlansAndUsage => 'Pläne & Nutzung Anzeigen';

  @override
  String get viewPlansDescription => 'Verwalten Sie Ihr Abonnement und sehen Sie Nutzungsstatistiken';

  @override
  String get addOrChangePaymentMethod => 'Zahlungsmethode hinzufügen oder ändern';

  @override
  String get displayOptions => 'Anzeigeoptionen';

  @override
  String get showMeetingsInMenuBar => 'Meetings in Menüleiste anzeigen';

  @override
  String get displayUpcomingMeetingsDescription => 'Anstehende Meetings in der Menüleiste anzeigen';

  @override
  String get showEventsWithoutParticipants => 'Ereignisse ohne Teilnehmer anzeigen';

  @override
  String get includePersonalEventsDescription => 'Persönliche Ereignisse ohne Teilnehmer einbeziehen';

  @override
  String get upcomingMeetings => 'Bevorstehende Termine';

  @override
  String get checkingNext7Days => 'Überprüfung der nächsten 7 Tage';

  @override
  String get shortcuts => 'Tastenkombinationen';

  @override
  String get shortcutChangeInstruction =>
      'Klicken Sie auf eine Tastenkombination, um sie zu ändern. Drücken Sie Escape, um abzubrechen.';

  @override
  String get configurePersonaDescription => 'Konfigurieren Sie Ihre KI-Persona';

  @override
  String get configureSTTProvider => 'STT-Anbieter konfigurieren';

  @override
  String get setConversationEndDescription => 'Festlegen, wann Gespräche automatisch enden';

  @override
  String get importDataDescription => 'Daten aus anderen Quellen importieren';

  @override
  String get exportConversationsDescription => 'Gespräche als JSON exportieren';

  @override
  String get exportingConversations => 'Konversationen werden exportiert...';

  @override
  String get clearNodesDescription => 'Alle Knoten und Verbindungen löschen';

  @override
  String get deleteKnowledgeGraphQuestion => 'Wissensgraph löschen?';

  @override
  String get deleteKnowledgeGraphWarning =>
      'Dadurch werden alle abgeleiteten Wissensgraph-Daten gelöscht. Ihre ursprünglichen Erinnerungen bleiben sicher.';

  @override
  String get connectOmiWithAI => 'Verbinden Sie Omi mit KI-Assistenten';

  @override
  String get noAPIKeys => 'Keine API-Schlüssel. Erstellen Sie einen, um loszulegen.';

  @override
  String get autoCreateWhenDetected => 'Automatisch erstellen, wenn Name erkannt wird';

  @override
  String get trackPersonalGoals => 'Persönliche Ziele auf der Startseite verfolgen';

  @override
  String get dailyReflectionDescription =>
      'Erhalten Sie um 21 Uhr eine Erinnerung, über Ihren Tag nachzudenken und Ihre Gedanken festzuhalten.';

  @override
  String get endpointURL => 'Endpunkt-URL';

  @override
  String get links => 'Links';

  @override
  String get discordMemberCount => 'Über 8000 Mitglieder auf Discord';

  @override
  String get userInformation => 'Benutzerinformationen';

  @override
  String get capabilities => 'Funktionen';

  @override
  String get previewScreenshots => 'Vorschau-Screenshots';

  @override
  String get holdOnPreparingForm => 'Einen Moment, wir bereiten das Formular für Sie vor';

  @override
  String get bySubmittingYouAgreeToOmi => 'Mit dem Absenden stimmen Sie Omi ';

  @override
  String get termsAndPrivacyPolicy => 'Nutzungsbedingungen & Datenschutz';

  @override
  String get helpsDiagnoseIssuesAutoDeletes =>
      'Hilft bei der Diagnose von Problemen. Wird nach 3 Tagen automatisch gelöscht.';

  @override
  String get manageYourApp => 'Verwalten Sie Ihre App';

  @override
  String get updatingYourApp => 'App wird aktualisiert';

  @override
  String get fetchingYourAppDetails => 'App-Details werden abgerufen';

  @override
  String get updateAppQuestion => 'App aktualisieren?';

  @override
  String get updateAppConfirmation =>
      'Sind Sie sicher, dass Sie Ihre App aktualisieren möchten? Die Änderungen werden nach Überprüfung durch unser Team übernommen.';

  @override
  String get updateApp => 'App aktualisieren';

  @override
  String get createAndSubmitNewApp => 'Neue App erstellen und einreichen';

  @override
  String appsCount(String count) {
    return '$count Apps';
  }

  @override
  String privateAppsCount(String count) {
    return '$count private Apps';
  }

  @override
  String publicAppsCount(String count) {
    return 'Öffentliche Apps ($count)';
  }

  @override
  String get newVersionAvailable => 'Neue Version verfügbar  🎉';

  @override
  String get no => 'Nein';

  @override
  String get subscriptionCancelledSuccessfully =>
      'Abonnement erfolgreich gekündigt. Es bleibt bis zum Ende des aktuellen Abrechnungszeitraums aktiv.';

  @override
  String get failedToCancelSubscription => 'Kündigung des Abonnements fehlgeschlagen. Bitte versuchen Sie es erneut.';

  @override
  String get invalidPaymentUrl => 'Ungültige Zahlungs-URL';

  @override
  String get permissionsAndTriggers => 'Berechtigungen & Auslöser';

  @override
  String get chatFeatures => 'Chat-Funktionen';

  @override
  String get uninstall => 'Deinstallieren';

  @override
  String get installs => 'INSTALLATIONEN';

  @override
  String get priceLabel => 'PREIS';

  @override
  String get updatedLabel => 'AKTUALISIERT';

  @override
  String get createdLabel => 'ERSTELLT';

  @override
  String get featuredLabel => 'EMPFOHLEN';

  @override
  String get cancelSubscriptionQuestion => 'Abonnement kündigen?';

  @override
  String get cancelSubscriptionConfirmation =>
      'Sind Sie sicher, dass Sie Ihr Abonnement kündigen möchten? Sie haben weiterhin Zugang bis zum Ende Ihres aktuellen Abrechnungszeitraums.';

  @override
  String get cancelSubscriptionButton => 'Abonnement kündigen';

  @override
  String get cancelling => 'Wird gekündigt...';

  @override
  String get betaTesterMessage =>
      'Sie sind Beta-Tester für diese App. Sie ist noch nicht öffentlich. Sie wird nach Genehmigung öffentlich.';

  @override
  String get appUnderReviewMessage =>
      'Ihre App wird überprüft und ist nur für Sie sichtbar. Sie wird nach Genehmigung öffentlich.';

  @override
  String get appRejectedMessage =>
      'Ihre App wurde abgelehnt. Bitte aktualisieren Sie die App-Details und reichen Sie sie erneut ein.';

  @override
  String get invalidIntegrationUrl => 'Ungültige Integrations-URL';

  @override
  String get tapToComplete => 'Tippen zum Abschließen';

  @override
  String get invalidSetupInstructionsUrl => 'Ungültige URL für Einrichtungsanweisungen';

  @override
  String get pushToTalk => 'Push-to-Talk';

  @override
  String get summaryPrompt => 'Zusammenfassungs-Prompt';

  @override
  String get pleaseSelectARating => 'Bitte wählen Sie eine Bewertung';

  @override
  String get reviewAddedSuccessfully => 'Bewertung erfolgreich hinzugefügt 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'Bewertung erfolgreich aktualisiert 🚀';

  @override
  String get failedToSubmitReview => 'Bewertung konnte nicht gesendet werden. Bitte versuche es erneut.';

  @override
  String get addYourReview => 'Bewertung hinzufügen';

  @override
  String get editYourReview => 'Bewertung bearbeiten';

  @override
  String get writeAReviewOptional => 'Bewertung schreiben (optional)';

  @override
  String get submitReview => 'Bewertung absenden';

  @override
  String get updateReview => 'Bewertung aktualisieren';

  @override
  String get yourReview => 'Ihre Bewertung';

  @override
  String get anonymousUser => 'Anonymer Benutzer';

  @override
  String get issueActivatingApp =>
      'Bei der Aktivierung dieser App ist ein Problem aufgetreten. Bitte versuchen Sie es erneut.';

  @override
  String get dataAccessNoticeDescription =>
      'Diese App wird auf Ihre Daten zugreifen. Omi AI ist nicht verantwortlich für die Verwendung, Änderung oder Löschung Ihrer Daten durch diese App';

  @override
  String get copyUrl => 'URL kopieren';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => 'Mo';

  @override
  String get weekdayTue => 'Di';

  @override
  String get weekdayWed => 'Mi';

  @override
  String get weekdayThu => 'Do';

  @override
  String get weekdayFri => 'Fr';

  @override
  String get weekdaySat => 'Sa';

  @override
  String get weekdaySun => 'So';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return '$serviceName-Integration kommt bald';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'Bereits nach $platform exportiert';
  }

  @override
  String get anotherPlatform => 'eine andere Plattform';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'Bitte authentifizieren Sie sich mit $serviceName unter Einstellungen > Aufgabenintegrationen';
  }

  @override
  String addingToService(String serviceName) {
    return 'Wird zu $serviceName hinzugefügt...';
  }

  @override
  String addedToService(String serviceName) {
    return 'Zu $serviceName hinzugefügt';
  }

  @override
  String failedToAddToService(String serviceName) {
    return 'Fehler beim Hinzufügen zu $serviceName';
  }

  @override
  String get permissionDeniedForAppleReminders => 'Berechtigung für Apple Erinnerungen verweigert';

  @override
  String failedToCreateApiKey(String error) {
    return 'Fehler beim Erstellen des Anbieter-API-Schlüssels: $error';
  }

  @override
  String get createAKey => 'Schlüssel erstellen';

  @override
  String get apiKeyRevokedSuccessfully => 'API-Schlüssel erfolgreich widerrufen';

  @override
  String failedToRevokeApiKey(String error) {
    return 'Fehler beim Widerrufen des API-Schlüssels: $error';
  }

  @override
  String get omiApiKeys => 'Omi API-Schlüssel';

  @override
  String get apiKeysDescription =>
      'API-Schlüssel werden zur Authentifizierung verwendet, wenn Ihre App mit dem OMI-Server kommuniziert. Sie ermöglichen Ihrer Anwendung, Erinnerungen zu erstellen und sicher auf andere OMI-Dienste zuzugreifen.';

  @override
  String get aboutOmiApiKeys => 'Über Omi API-Schlüssel';

  @override
  String get yourNewKey => 'Ihr neuer Schlüssel:';

  @override
  String get copyToClipboard => 'In Zwischenablage kopieren';

  @override
  String get pleaseCopyKeyNow => 'Bitte kopieren Sie ihn jetzt und notieren Sie ihn an einem sicheren Ort. ';

  @override
  String get willNotSeeAgain => 'Sie werden ihn nicht wieder sehen können.';

  @override
  String get revokeKey => 'Schlüssel widerrufen';

  @override
  String get revokeApiKeyQuestion => 'API-Schlüssel widerrufen?';

  @override
  String get revokeApiKeyWarning =>
      'Diese Aktion kann nicht rückgängig gemacht werden. Alle Anwendungen, die diesen Schlüssel verwenden, können nicht mehr auf die API zugreifen.';

  @override
  String get revoke => 'Widerrufen';

  @override
  String get whatWouldYouLikeToCreate => 'Was möchten Sie erstellen?';

  @override
  String get createAnApp => 'Eine App erstellen';

  @override
  String get createAndShareYourApp => 'Erstellen und teilen Sie Ihre App';

  @override
  String get createMyClone => 'Meinen Klon erstellen';

  @override
  String get createYourDigitalClone => 'Erstellen Sie Ihren digitalen Klon';

  @override
  String get itemApp => 'App';

  @override
  String get itemPersona => 'Persona';

  @override
  String keepItemPublic(String item) {
    return '$item öffentlich lassen';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return '$item öffentlich machen?';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return '$item privat machen?';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'Wenn Sie $item öffentlich machen, kann es von allen genutzt werden';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'Wenn Sie $item jetzt privat machen, funktioniert es für niemanden mehr und ist nur für Sie sichtbar';
  }

  @override
  String get manageApp => 'App verwalten';

  @override
  String get updatePersonaDetails => 'Persona-Details aktualisieren';

  @override
  String deleteItemTitle(String item) {
    return '$item löschen';
  }

  @override
  String deleteItemQuestion(String item) {
    return '$item löschen?';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'Sind Sie sicher, dass Sie $item löschen möchten? Diese Aktion kann nicht rückgängig gemacht werden.';
  }

  @override
  String get revokeKeyQuestion => 'Schlüssel widerrufen?';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'Sind Sie sicher, dass Sie den Schlüssel \"$keyName\" widerrufen möchten? Diese Aktion kann nicht rückgängig gemacht werden.';
  }

  @override
  String get createNewKey => 'Neuen Schlüssel erstellen';

  @override
  String get keyNameHint => 'z.B. Claude Desktop';

  @override
  String get pleaseEnterAName => 'Bitte geben Sie einen Namen ein.';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'Schlüssel konnte nicht erstellt werden: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'Schlüssel konnte nicht erstellt werden. Bitte versuchen Sie es erneut.';

  @override
  String get keyCreated => 'Schlüssel erstellt';

  @override
  String get keyCreatedMessage =>
      'Ihr neuer Schlüssel wurde erstellt. Bitte kopieren Sie ihn jetzt. Sie werden ihn nicht mehr sehen können.';

  @override
  String get keyWord => 'Schlüssel';

  @override
  String get externalAppAccess => 'Externer App-Zugriff';

  @override
  String get externalAppAccessDescription =>
      'Die folgenden installierten Apps haben externe Integrationen und können auf Ihre Daten zugreifen, wie Gespräche und Erinnerungen.';

  @override
  String get noExternalAppsHaveAccess => 'Keine externen Apps haben Zugriff auf Ihre Daten.';

  @override
  String get maximumSecurityE2ee => 'Maximale Sicherheit (E2EE)';

  @override
  String get e2eeDescription =>
      'End-to-End-Verschlüsselung ist der Goldstandard für Datenschutz. Wenn aktiviert, werden Ihre Daten auf Ihrem Gerät verschlüsselt, bevor sie an unsere Server gesendet werden. Das bedeutet, dass niemand, nicht einmal Omi, auf Ihre Inhalte zugreifen kann.';

  @override
  String get importantTradeoffs => 'Wichtige Kompromisse:';

  @override
  String get e2eeTradeoff1 => '• Einige Funktionen wie externe App-Integrationen können deaktiviert sein.';

  @override
  String get e2eeTradeoff2 => '• Wenn Sie Ihr Passwort verlieren, können Ihre Daten nicht wiederhergestellt werden.';

  @override
  String get featureComingSoon => 'Diese Funktion kommt bald!';

  @override
  String get migrationInProgressMessage =>
      'Migration läuft. Sie können das Schutzniveau nicht ändern, bis sie abgeschlossen ist.';

  @override
  String get migrationFailed => 'Migration fehlgeschlagen';

  @override
  String migratingFromTo(String source, String target) {
    return 'Migration von $source nach $target';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total Objekte';
  }

  @override
  String get secureEncryption => 'Sichere Verschlüsselung';

  @override
  String get secureEncryptionDescription =>
      'Ihre Daten werden mit einem für Sie einzigartigen Schlüssel auf unseren Servern verschlüsselt, die bei Google Cloud gehostet werden. Das bedeutet, dass Ihre Rohdaten für niemanden zugänglich sind, einschließlich Omi-Mitarbeiter oder Google, direkt aus der Datenbank.';

  @override
  String get endToEndEncryption => 'End-to-End-Verschlüsselung';

  @override
  String get e2eeCardDescription =>
      'Aktivieren Sie für maximale Sicherheit, bei der nur Sie auf Ihre Daten zugreifen können. Tippen Sie, um mehr zu erfahren.';

  @override
  String get dataAlwaysEncrypted =>
      'Unabhängig vom Level sind Ihre Daten immer im Ruhezustand und während der Übertragung verschlüsselt.';

  @override
  String get readOnlyScope => 'Nur Lesen';

  @override
  String get fullAccessScope => 'Vollzugriff';

  @override
  String get readScope => 'Lesen';

  @override
  String get writeScope => 'Schreiben';

  @override
  String get apiKeyCreated => 'API-Schlüssel erstellt!';

  @override
  String get saveKeyWarning => 'Speichern Sie diesen Schlüssel jetzt! Sie werden ihn nicht mehr sehen können.';

  @override
  String get yourApiKey => 'IHR API-SCHLÜSSEL';

  @override
  String get tapToCopy => 'Zum Kopieren tippen';

  @override
  String get copyKey => 'Schlüssel kopieren';

  @override
  String get createApiKey => 'API-Schlüssel erstellen';

  @override
  String get accessDataProgrammatically => 'Greifen Sie programmgesteuert auf Ihre Daten zu';

  @override
  String get keyNameLabel => 'SCHLÜSSELNAME';

  @override
  String get keyNamePlaceholder => 'z.B. Meine App-Integration';

  @override
  String get permissionsLabel => 'BERECHTIGUNGEN';

  @override
  String get permissionsInfoNote => 'R = Lesen, W = Schreiben. Standardmäßig nur Lesen, wenn nichts ausgewählt.';

  @override
  String get developerApi => 'Entwickler-API';

  @override
  String get createAKeyToGetStarted => 'Erstellen Sie einen Schlüssel, um loszulegen';

  @override
  String errorWithMessage(String error) {
    return 'Fehler: $error';
  }

  @override
  String get omiTraining => 'Omi-Training';

  @override
  String get trainingDataProgram => 'Trainingsdatenprogramm';

  @override
  String get getOmiUnlimitedFree =>
      'Erhalten Sie Omi Unlimited kostenlos, indem Sie Ihre Daten zum Training von KI-Modellen beitragen.';

  @override
  String get trainingDataBullets =>
      '• Ihre Daten helfen, KI-Modelle zu verbessern\n• Nur nicht sensible Daten werden geteilt\n• Vollständig transparenter Prozess';

  @override
  String get learnMoreAtOmiTraining => 'Erfahren Sie mehr unter omi.me/training';

  @override
  String get agreeToContributeData => 'Ich verstehe und stimme zu, meine Daten für das KI-Training beizutragen';

  @override
  String get submitRequest => 'Anfrage senden';

  @override
  String get thankYouRequestUnderReview =>
      'Vielen Dank! Ihre Anfrage wird geprüft. Wir benachrichtigen Sie nach der Genehmigung.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'Ihr Plan bleibt bis $date aktiv. Danach verlieren Sie den Zugang zu Ihren unbegrenzten Funktionen. Sind Sie sicher?';
  }

  @override
  String get confirmCancellation => 'Kündigung bestätigen';

  @override
  String get keepMyPlan => 'Meinen Plan behalten';

  @override
  String get subscriptionSetToCancel => 'Ihr Abonnement wird zum Ende des Zeitraums gekündigt.';

  @override
  String get switchedToOnDevice => 'Auf Geräte-Transkription umgeschaltet';

  @override
  String get couldNotSwitchToFreePlan => 'Konnte nicht zum kostenlosen Plan wechseln. Bitte versuchen Sie es erneut.';

  @override
  String get couldNotLoadPlans => 'Verfügbare Pläne konnten nicht geladen werden. Bitte versuchen Sie es erneut.';

  @override
  String get selectedPlanNotAvailable => 'Der ausgewählte Plan ist nicht verfügbar. Bitte versuchen Sie es erneut.';

  @override
  String get upgradeToAnnualPlan => 'Auf Jahresplan upgraden';

  @override
  String get importantBillingInfo => 'Wichtige Abrechnungsinformationen:';

  @override
  String get monthlyPlanContinues => 'Ihr aktueller Monatsplan läuft bis zum Ende Ihres Abrechnungszeitraums weiter';

  @override
  String get paymentMethodCharged =>
      'Ihre bestehende Zahlungsmethode wird automatisch belastet, wenn Ihr Monatsplan endet';

  @override
  String get annualSubscriptionStarts => 'Ihr 12-monatiges Jahresabonnement beginnt automatisch nach der Abbuchung';

  @override
  String get thirteenMonthsCoverage =>
      'Sie erhalten insgesamt 13 Monate Abdeckung (aktueller Monat + 12 Monate jährlich)';

  @override
  String get confirmUpgrade => 'Upgrade bestätigen';

  @override
  String get confirmPlanChange => 'Planänderung bestätigen';

  @override
  String get confirmAndProceed => 'Bestätigen und fortfahren';

  @override
  String get upgradeScheduled => 'Upgrade geplant';

  @override
  String get changePlan => 'Plan ändern';

  @override
  String get upgradeAlreadyScheduled => 'Ihr Upgrade auf den Jahresplan ist bereits geplant';

  @override
  String get youAreOnUnlimitedPlan => 'Sie haben den Unlimited-Plan.';

  @override
  String get yourOmiUnleashed => 'Ihr Omi, entfesselt. Werden Sie unbegrenzt für endlose Möglichkeiten.';

  @override
  String planEndedOn(String date) {
    return 'Ihr Plan endete am $date.\\nAbonnieren Sie jetzt erneut - Ihnen wird sofort für einen neuen Abrechnungszeitraum berechnet.';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'Ihr Plan wird am $date gekündigt.\\nAbonnieren Sie jetzt erneut, um Ihre Vorteile zu behalten - keine Gebühr bis $date.';
  }

  @override
  String get annualPlanStartsAutomatically => 'Ihr Jahresplan beginnt automatisch, wenn Ihr Monatsplan endet.';

  @override
  String planRenewsOn(String date) {
    return 'Ihr Plan verlängert sich am $date.';
  }

  @override
  String get unlimitedConversations => 'Unbegrenzte Gespräche';

  @override
  String get askOmiAnything => 'Fragen Sie Omi alles über Ihr Leben';

  @override
  String get unlockOmiInfiniteMemory => 'Schalten Sie Omis unendlichen Speicher frei';

  @override
  String get youreOnAnnualPlan => 'Sie haben den Jahresplan';

  @override
  String get alreadyBestValuePlan => 'Sie haben bereits den besten Wertplan. Keine Änderungen erforderlich.';

  @override
  String get unableToLoadPlans => 'Pläne können nicht geladen werden';

  @override
  String get checkConnectionTryAgain => 'Bitte überprüfen Sie Ihre Verbindung und versuchen Sie es erneut';

  @override
  String get useFreePlan => 'Kostenlosen Plan nutzen';

  @override
  String get continueText => 'Fortfahren';

  @override
  String get resubscribe => 'Erneut abonnieren';

  @override
  String get couldNotOpenPaymentSettings =>
      'Zahlungseinstellungen konnten nicht geöffnet werden. Bitte versuchen Sie es erneut.';

  @override
  String get managePaymentMethod => 'Zahlungsmethode verwalten';

  @override
  String get cancelSubscription => 'Abonnement kündigen';

  @override
  String endsOnDate(String date) {
    return 'Endet am $date';
  }

  @override
  String get active => 'Aktiv';

  @override
  String get freePlan => 'Kostenloser Plan';

  @override
  String get configure => 'Konfigurieren';

  @override
  String get privacyInformation => 'Datenschutzinformationen';

  @override
  String get yourPrivacyMattersToUs => 'Ihre Privatsphäre ist uns wichtig';

  @override
  String get privacyIntroText =>
      'Bei Omi nehmen wir Ihre Privatsphäre sehr ernst. Wir möchten transparent sein über die Daten, die wir sammeln und wie wir sie verwenden, um unser Produkt zu verbessern. Hier ist, was Sie wissen müssen:';

  @override
  String get whatWeTrack => 'Was wir erfassen';

  @override
  String get anonymityAndPrivacy => 'Anonymität und Datenschutz';

  @override
  String get optInAndOptOutOptions => 'Opt-In und Opt-Out Optionen';

  @override
  String get ourCommitment => 'Unser Engagement';

  @override
  String get commitmentText =>
      'Wir verpflichten uns, die gesammelten Daten nur zu verwenden, um Omi zu einem besseren Produkt für Sie zu machen. Ihre Privatsphäre und Ihr Vertrauen sind uns sehr wichtig.';

  @override
  String get thankYouText =>
      'Vielen Dank, dass Sie ein geschätzter Benutzer von Omi sind. Bei Fragen oder Bedenken können Sie uns gerne unter team@basedhardware.com kontaktieren.';

  @override
  String get wifiSyncSettings => 'WLAN-Synchronisierungseinstellungen';

  @override
  String get enterHotspotCredentials => 'Geben Sie die Hotspot-Anmeldedaten Ihres Telefons ein';

  @override
  String get wifiSyncUsesHotspot =>
      'WLAN-Sync nutzt Ihr Telefon als Hotspot. Finden Sie Name und Passwort unter Einstellungen > Persönlicher Hotspot.';

  @override
  String get hotspotNameSsid => 'Hotspot-Name (SSID)';

  @override
  String get exampleIphoneHotspot => 'z.B. iPhone Hotspot';

  @override
  String get password => 'Passwort';

  @override
  String get enterHotspotPassword => 'Hotspot-Passwort eingeben';

  @override
  String get saveCredentials => 'Anmeldedaten speichern';

  @override
  String get clearCredentials => 'Anmeldedaten löschen';

  @override
  String get pleaseEnterHotspotName => 'Bitte geben Sie einen Hotspot-Namen ein';

  @override
  String get wifiCredentialsSaved => 'WLAN-Anmeldedaten gespeichert';

  @override
  String get wifiCredentialsCleared => 'WLAN-Anmeldedaten gelöscht';

  @override
  String summaryGeneratedForDate(String date) {
    return 'Zusammenfassung erstellt für $date';
  }

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'Zusammenfassung konnte nicht erstellt werden. Stellen Sie sicher, dass Sie Gespräche für diesen Tag haben.';

  @override
  String get summaryNotFound => 'Zusammenfassung nicht gefunden';

  @override
  String get yourDaysJourney => 'Ihre Tagesreise';

  @override
  String get highlights => 'Höhepunkte';

  @override
  String get unresolvedQuestions => 'Offene Fragen';

  @override
  String get decisions => 'Entscheidungen';

  @override
  String get learnings => 'Erkenntnisse';

  @override
  String get autoDeletesAfterThreeDays => 'Wird nach 3 Tagen automatisch gelöscht.';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'Wissensgraph erfolgreich gelöscht';

  @override
  String get exportStartedMayTakeFewSeconds => 'Export gestartet. Dies kann einige Sekunden dauern...';

  @override
  String get knowledgeGraphDeleteDescription =>
      'Dies löscht alle abgeleiteten Wissensgraph-Daten (Knoten und Verbindungen). Ihre ursprünglichen Erinnerungen bleiben sicher. Der Graph wird im Laufe der Zeit oder bei der nächsten Anfrage neu erstellt.';

  @override
  String get configureDailySummaryDigest => 'Konfigurieren Sie Ihre tägliche Aufgabenübersicht';

  @override
  String accessesDataTypes(String dataTypes) {
    return 'Greift auf $dataTypes zu';
  }

  @override
  String triggeredByType(String triggerType) {
    return 'ausgelöst durch $triggerType';
  }

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription und wird $triggerDescription.';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return 'Wird $triggerDescription.';
  }

  @override
  String get noSpecificDataAccessConfigured => 'Kein spezifischer Datenzugriff konfiguriert.';

  @override
  String get basicPlanDescription => '1.200 Premium-Minuten + unbegrenzt on-device';

  @override
  String get minutes => 'Minuten';

  @override
  String get omiHas => 'Omi hat:';

  @override
  String get premiumMinutesUsed => 'Premium-Minuten aufgebraucht.';

  @override
  String get setupOnDevice => 'On-device einrichten';

  @override
  String get forUnlimitedFreeTranscription => 'für unbegrenzte kostenlose Transkription.';

  @override
  String premiumMinsLeft(int count) {
    return '$count Premium-Minuten übrig.';
  }

  @override
  String get alwaysAvailable => 'immer verfügbar.';

  @override
  String get importHistory => 'Importverlauf';

  @override
  String get noImportsYet => 'Noch keine Importe';

  @override
  String get selectZipFileToImport => 'Wählen Sie die .zip-Datei zum Importieren!';

  @override
  String get otherDevicesComingSoon => 'Weitere Geräte demnächst';

  @override
  String get deleteAllLimitlessConversations => 'Alle Limitless-Gespräche löschen?';

  @override
  String get deleteAllLimitlessWarning =>
      'Dies löscht dauerhaft alle von Limitless importierten Gespräche. Diese Aktion kann nicht rückgängig gemacht werden.';

  @override
  String deletedLimitlessConversations(int count) {
    return '$count Limitless-Gespräche gelöscht';
  }

  @override
  String get failedToDeleteConversations => 'Gespräche konnten nicht gelöscht werden';

  @override
  String get deleteImportedData => 'Importierte Daten löschen';

  @override
  String get statusPending => 'Ausstehend';

  @override
  String get statusProcessing => 'Wird verarbeitet';

  @override
  String get statusCompleted => 'Abgeschlossen';

  @override
  String get statusFailed => 'Fehlgeschlagen';

  @override
  String nConversations(int count) {
    return '$count Gespräche';
  }

  @override
  String get pleaseEnterName => 'Bitte geben Sie einen Namen ein';

  @override
  String get nameMustBeBetweenCharacters => 'Der Name muss zwischen 2 und 40 Zeichen lang sein';

  @override
  String get deleteSampleQuestion => 'Probe löschen?';

  @override
  String deleteSampleConfirmation(String name) {
    return 'Sind Sie sicher, dass Sie die Probe von $name löschen möchten?';
  }

  @override
  String get confirmDeletion => 'Löschen bestätigen';

  @override
  String deletePersonConfirmation(String name) {
    return 'Sind Sie sicher, dass Sie $name löschen möchten? Dies entfernt auch alle zugehörigen Sprachproben.';
  }

  @override
  String get howItWorksTitle => 'Wie funktioniert es?';

  @override
  String get howPeopleWorks =>
      'Sobald eine Person erstellt wurde, können Sie zum Gesprächstranskript gehen und ihr die entsprechenden Segmente zuweisen, so kann Omi auch ihre Sprache erkennen!';

  @override
  String get tapToDelete => 'Tippen zum Löschen';

  @override
  String get newTag => 'NEU';

  @override
  String get needHelpChatWithUs => 'Hilfe benötigt? Schreiben Sie uns';

  @override
  String get localStorageEnabled => 'Lokaler Speicher aktiviert';

  @override
  String get localStorageDisabled => 'Lokaler Speicher deaktiviert';

  @override
  String failedToUpdateSettings(String error) {
    return 'Einstellungen konnten nicht aktualisiert werden: $error';
  }

  @override
  String get privacyNotice => 'Datenschutzhinweis';

  @override
  String get recordingsMayCaptureOthers =>
      'Aufnahmen können die Stimmen anderer erfassen. Stellen Sie sicher, dass Sie die Zustimmung aller Teilnehmer haben, bevor Sie aktivieren.';

  @override
  String get enable => 'Aktivieren';

  @override
  String get storeAudioOnPhone => 'Audio auf dem Telefon speichern';

  @override
  String get on => 'On';

  @override
  String get storeAudioDescription =>
      'Bewahren Sie alle Audioaufnahmen lokal auf Ihrem Telefon auf. Bei Deaktivierung werden nur fehlgeschlagene Uploads gespeichert, um Speicherplatz zu sparen.';

  @override
  String get enableLocalStorage => 'Lokalen Speicher aktivieren';

  @override
  String get cloudStorageEnabled => 'Cloud-Speicher aktiviert';

  @override
  String get cloudStorageDisabled => 'Cloud-Speicher deaktiviert';

  @override
  String get enableCloudStorage => 'Cloud-Speicher aktivieren';

  @override
  String get storeAudioOnCloud => 'Audio in der Cloud speichern';

  @override
  String get cloudStorageDialogMessage =>
      'Ihre Echtzeit-Aufnahmen werden während des Sprechens in einem privaten Cloud-Speicher gespeichert.';

  @override
  String get storeAudioCloudDescription =>
      'Speichern Sie Ihre Echtzeit-Aufnahmen während des Sprechens in einem privaten Cloud-Speicher. Audio wird in Echtzeit erfasst und sicher gespeichert.';

  @override
  String get downloadingFirmware => 'Firmware wird heruntergeladen';

  @override
  String get installingFirmware => 'Firmware wird installiert';

  @override
  String get firmwareUpdateWarning =>
      'Schließen Sie die App nicht und schalten Sie das Gerät nicht aus. Dies könnte Ihr Gerät beschädigen.';

  @override
  String get firmwareUpdated => 'Firmware aktualisiert';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'Bitte starten Sie Ihr $deviceName neu, um das Update abzuschließen.';
  }

  @override
  String get yourDeviceIsUpToDate => 'Ihr Gerät ist auf dem neuesten Stand';

  @override
  String get currentVersion => 'Aktuelle Version';

  @override
  String get latestVersion => 'Neueste Version';

  @override
  String get whatsNew => 'Was ist neu';

  @override
  String get installUpdate => 'Update installieren';

  @override
  String get updateNow => 'Jetzt aktualisieren';

  @override
  String get updateGuide => 'Update-Anleitung';

  @override
  String get checkingForUpdates => 'Suche nach Updates';

  @override
  String get checkingFirmwareVersion => 'Firmware-Version wird überprüft...';

  @override
  String get firmwareUpdate => 'Firmware-Update';

  @override
  String get payments => 'Zahlungen';

  @override
  String get connectPaymentMethodInfo =>
      'Verbinden Sie unten eine Zahlungsmethode, um Auszahlungen für Ihre Apps zu erhalten.';

  @override
  String get selectedPaymentMethod => 'Ausgewählte Zahlungsmethode';

  @override
  String get availablePaymentMethods => 'Verfügbare Zahlungsmethoden';

  @override
  String get activeStatus => 'Aktiv';

  @override
  String get connectedStatus => 'Verbunden';

  @override
  String get notConnectedStatus => 'Nicht verbunden';

  @override
  String get setActive => 'Als aktiv festlegen';

  @override
  String get getPaidThroughStripe => 'Erhalten Sie Zahlungen für Ihre App-Verkäufe über Stripe';

  @override
  String get monthlyPayouts => 'Monatliche Auszahlungen';

  @override
  String get monthlyPayoutsDescription =>
      'Erhalten Sie monatliche Zahlungen direkt auf Ihr Konto, wenn Sie 10 \$ Einnahmen erreichen';

  @override
  String get secureAndReliable => 'Sicher und zuverlässig';

  @override
  String get stripeSecureDescription => 'Stripe gewährleistet sichere und pünktliche Überweisungen Ihrer App-Einnahmen';

  @override
  String get selectYourCountry => 'Wählen Sie Ihr Land';

  @override
  String get countrySelectionPermanent => 'Ihre Länderauswahl ist dauerhaft und kann später nicht geändert werden.';

  @override
  String get byClickingConnectNow => 'Durch Klicken auf \"Jetzt verbinden\" stimmen Sie zu';

  @override
  String get stripeConnectedAccountAgreement => 'Stripe Connected Account-Vereinbarung';

  @override
  String get errorConnectingToStripe => 'Fehler beim Verbinden mit Stripe! Bitte versuchen Sie es später erneut.';

  @override
  String get connectingYourStripeAccount => 'Verbindung Ihres Stripe-Kontos';

  @override
  String get stripeOnboardingInstructions =>
      'Bitte schließen Sie den Stripe-Onboarding-Prozess in Ihrem Browser ab. Diese Seite wird automatisch aktualisiert, sobald der Vorgang abgeschlossen ist.';

  @override
  String get failedTryAgain => 'Fehlgeschlagen? Erneut versuchen';

  @override
  String get illDoItLater => 'Ich mache es später';

  @override
  String get successfullyConnected => 'Erfolgreich verbunden!';

  @override
  String get stripeReadyForPayments =>
      'Ihr Stripe-Konto ist jetzt bereit, Zahlungen zu empfangen. Sie können sofort mit dem Verdienen aus Ihren App-Verkäufen beginnen.';

  @override
  String get updateStripeDetails => 'Stripe-Details aktualisieren';

  @override
  String get errorUpdatingStripeDetails =>
      'Fehler beim Aktualisieren der Stripe-Details! Bitte versuchen Sie es später erneut.';

  @override
  String get updatePayPal => 'PayPal aktualisieren';

  @override
  String get setUpPayPal => 'PayPal einrichten';

  @override
  String get updatePayPalAccountDetails => 'Aktualisieren Sie Ihre PayPal-Kontodaten';

  @override
  String get connectPayPalToReceivePayments => 'Verbinden Sie Ihr PayPal-Konto, um Zahlungen für Ihre Apps zu erhalten';

  @override
  String get paypalEmail => 'PayPal-E-Mail';

  @override
  String get paypalMeLink => 'PayPal.me-Link';

  @override
  String get stripeRecommendation =>
      'Wenn Stripe in Ihrem Land verfügbar ist, empfehlen wir dringend, es für schnellere und einfachere Auszahlungen zu verwenden.';

  @override
  String get updatePayPalDetails => 'PayPal-Details aktualisieren';

  @override
  String get savePayPalDetails => 'PayPal-Details speichern';

  @override
  String get pleaseEnterPayPalEmail => 'Bitte geben Sie Ihre PayPal-E-Mail ein';

  @override
  String get pleaseEnterPayPalMeLink => 'Bitte geben Sie Ihren PayPal.me-Link ein';

  @override
  String get doNotIncludeHttpInLink => 'Fügen Sie http, https oder www nicht in den Link ein';

  @override
  String get pleaseEnterValidPayPalMeLink => 'Bitte geben Sie einen gültigen PayPal.me-Link ein';

  @override
  String get pleaseEnterValidEmail => 'Bitte geben Sie eine gültige E-Mail-Adresse ein';

  @override
  String get syncingYourRecordings => 'Synchronisiere deine Aufnahmen';

  @override
  String get syncYourRecordings => 'Synchronisiere deine Aufnahmen';

  @override
  String get syncNow => 'Jetzt synchronisieren';

  @override
  String get error => 'Fehler';

  @override
  String get speechSamples => 'Sprachproben';

  @override
  String additionalSampleIndex(String index) {
    return 'Zusätzliche Probe $index';
  }

  @override
  String durationSeconds(String seconds) {
    return 'Dauer: $seconds Sekunden';
  }

  @override
  String get additionalSpeechSampleRemoved => 'Zusätzliche Sprachprobe entfernt';

  @override
  String get consentDataMessage =>
      'Durch Fortfahren werden alle Daten, die Sie mit dieser App teilen (einschließlich Ihrer Gespräche, Aufnahmen und persönlichen Informationen), sicher auf unseren Servern gespeichert, um Ihnen KI-gestützte Einblicke zu bieten und alle App-Funktionen zu ermöglichen.';

  @override
  String get tasksEmptyStateMessage =>
      'Aufgaben aus Ihren Gesprächen werden hier angezeigt.\nTippen Sie auf +, um eine manuell zu erstellen.';

  @override
  String get clearChatAction => 'Chat löschen';

  @override
  String get enableApps => 'Apps aktivieren';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => 'mehr anzeigen ↓';

  @override
  String get showLess => 'weniger anzeigen ↑';

  @override
  String get loadingYourRecording => 'Aufnahme wird geladen...';

  @override
  String get photoDiscardedMessage => 'Dieses Foto wurde verworfen, da es nicht bedeutsam war.';

  @override
  String get analyzing => 'Analysiere...';

  @override
  String get searchCountries => 'Länder suchen...';

  @override
  String get checkingAppleWatch => 'Apple Watch wird überprüft...';

  @override
  String get installOmiOnAppleWatch => 'Installiere Omi auf deiner\nApple Watch';

  @override
  String get installOmiOnAppleWatchDescription =>
      'Um deine Apple Watch mit Omi zu verwenden, musst du zuerst die Omi-App auf deiner Uhr installieren.';

  @override
  String get openOmiOnAppleWatch => 'Öffne Omi auf deiner\nApple Watch';

  @override
  String get openOmiOnAppleWatchDescription =>
      'Die Omi-App ist auf deiner Apple Watch installiert. Öffne sie und tippe auf Start.';

  @override
  String get openWatchApp => 'Watch-App öffnen';

  @override
  String get iveInstalledAndOpenedTheApp => 'Ich habe die App installiert und geöffnet';

  @override
  String get unableToOpenWatchApp =>
      'Apple Watch-App konnte nicht geöffnet werden. Öffne die Watch-App manuell auf deiner Apple Watch und installiere Omi aus dem Bereich \"Verfügbare Apps\".';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch erfolgreich verbunden!';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch ist noch nicht erreichbar. Stelle sicher, dass die Omi-App auf deiner Uhr geöffnet ist.';

  @override
  String errorCheckingConnection(String error) {
    return 'Fehler beim Überprüfen der Verbindung: $error';
  }

  @override
  String get muted => 'Stumm';

  @override
  String get processNow => 'Jetzt verarbeiten';

  @override
  String get finishedConversation => 'Gespräch beendet?';

  @override
  String get stopRecordingConfirmation =>
      'Möchtest du die Aufnahme wirklich beenden und das Gespräch jetzt zusammenfassen?';

  @override
  String get conversationEndsManually => 'Das Gespräch endet nur manuell.';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'Das Gespräch wird nach $minutes Minute$suffix ohne Sprache zusammengefasst.';
  }

  @override
  String get dontAskAgain => 'Nicht erneut fragen';

  @override
  String get waitingForTranscriptOrPhotos => 'Warte auf Transkript oder Fotos...';

  @override
  String get noSummaryYet => 'Noch keine Zusammenfassung';

  @override
  String hints(String text) {
    return 'Hinweise: $text';
  }

  @override
  String get testConversationPrompt => 'Konversations-Prompt testen';

  @override
  String get prompt => 'Prompt';

  @override
  String get result => 'Ergebnis:';

  @override
  String get compareTranscripts => 'Transkripte vergleichen';

  @override
  String get notHelpful => 'Nicht hilfreich';

  @override
  String get exportTasksWithOneTap => 'Aufgaben mit einem Tippen exportieren!';

  @override
  String get inProgress => 'In Bearbeitung';

  @override
  String get photos => 'Fotos';

  @override
  String get rawData => 'Rohdaten';

  @override
  String get content => 'Inhalt';

  @override
  String get noContentToDisplay => 'Kein Inhalt zum Anzeigen';

  @override
  String get noSummary => 'Keine Zusammenfassung';

  @override
  String get updateOmiFirmware => 'Omi-Firmware aktualisieren';

  @override
  String get anErrorOccurredTryAgain => 'Ein Fehler ist aufgetreten. Bitte versuchen Sie es erneut.';

  @override
  String get welcomeBackSimple => 'Willkommen zurück';

  @override
  String get addVocabularyDescription => 'Fügen Sie Wörter hinzu, die Omi bei der Transkription erkennen soll.';

  @override
  String get enterWordsCommaSeparated => 'Wörter eingeben (durch Komma getrennt)';

  @override
  String get whenToReceiveDailySummary => 'Wann Sie Ihre tägliche Zusammenfassung erhalten';

  @override
  String get checkingNextSevenDays => 'Überprüfe die nächsten 7 Tage';

  @override
  String failedToDeleteError(String error) {
    return 'Löschen fehlgeschlagen: $error';
  }

  @override
  String get developerApiKeys => 'Entwickler-API-Schlüssel';

  @override
  String get noApiKeysCreateOne => 'Keine API-Schlüssel. Erstellen Sie einen, um zu beginnen.';

  @override
  String get commandRequired => '⌘ erforderlich';

  @override
  String get spaceKey => 'Leertaste';

  @override
  String loadMoreRemaining(String count) {
    return 'Mehr laden ($count übrig)';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'Top $percentile% Nutzer';
  }

  @override
  String get wrappedMinutes => 'Minuten';

  @override
  String get wrappedConversations => 'Gespräche';

  @override
  String get wrappedDaysActive => 'aktive Tage';

  @override
  String get wrappedYouTalkedAbout => 'Du hast gesprochen über';

  @override
  String get wrappedActionItems => 'Aufgaben';

  @override
  String get wrappedTasksCreated => 'erstellte Aufgaben';

  @override
  String get wrappedCompleted => 'abgeschlossen';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% Abschlussrate';
  }

  @override
  String get wrappedYourTopDays => 'Deine besten Tage';

  @override
  String get wrappedBestMoments => 'Beste Momente';

  @override
  String get wrappedMyBuddies => 'Meine Freunde';

  @override
  String get wrappedCouldntStopTalkingAbout => 'Konnte nicht aufhören zu reden über';

  @override
  String get wrappedShow => 'SERIE';

  @override
  String get wrappedMovie => 'FILM';

  @override
  String get wrappedBook => 'BUCH';

  @override
  String get wrappedCelebrity => 'PROMI';

  @override
  String get wrappedFood => 'ESSEN';

  @override
  String get wrappedMovieRecs => 'Filmempfehlungen für Freunde';

  @override
  String get wrappedBiggest => 'Größte';

  @override
  String get wrappedStruggle => 'Herausforderung';

  @override
  String get wrappedButYouPushedThrough => 'Aber du hast es geschafft 💪';

  @override
  String get wrappedWin => 'Sieg';

  @override
  String get wrappedYouDidIt => 'Du hast es geschafft! 🎉';

  @override
  String get wrappedTopPhrases => 'Top 5 Phrasen';

  @override
  String get wrappedMins => 'Min';

  @override
  String get wrappedConvos => 'Gespräche';

  @override
  String get wrappedDays => 'Tage';

  @override
  String get wrappedMyBuddiesLabel => 'MEINE FREUNDE';

  @override
  String get wrappedObsessionsLabel => 'OBSESSIONEN';

  @override
  String get wrappedStruggleLabel => 'HERAUSFORDERUNG';

  @override
  String get wrappedWinLabel => 'SIEG';

  @override
  String get wrappedTopPhrasesLabel => 'TOP PHRASEN';

  @override
  String get wrappedLetsHitRewind => 'Lass uns dein Jahr zurückspulen';

  @override
  String get wrappedGenerateMyWrapped => 'Meinen Wrapped generieren';

  @override
  String get wrappedProcessingDefault => 'Verarbeitung...';

  @override
  String get wrappedCreatingYourStory => 'Erstelle deine\n2025 Geschichte...';

  @override
  String get wrappedSomethingWentWrong => 'Etwas ist\nschiefgelaufen';

  @override
  String get wrappedAnErrorOccurred => 'Ein Fehler ist aufgetreten';

  @override
  String get wrappedTryAgain => 'Erneut versuchen';

  @override
  String get wrappedNoDataAvailable => 'Keine Daten verfügbar';

  @override
  String get wrappedOmiLifeRecap => 'Omi Lebensrückblick';

  @override
  String get wrappedSwipeUpToBegin => 'Nach oben wischen zum Starten';

  @override
  String get wrappedShareText => 'Mein 2025, festgehalten von Omi ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare => 'Teilen fehlgeschlagen. Bitte erneut versuchen.';

  @override
  String get wrappedFailedToStartGeneration => 'Generierung konnte nicht gestartet werden. Bitte erneut versuchen.';

  @override
  String get wrappedStarting => 'Starte...';

  @override
  String get wrappedShare => 'Teilen';

  @override
  String get wrappedShareYourWrapped => 'Teile deinen Wrapped';

  @override
  String get wrappedMy2025 => 'Mein 2025';

  @override
  String get wrappedRememberedByOmi => 'festgehalten von Omi';

  @override
  String get wrappedMostFunDay => 'Am lustigsten';

  @override
  String get wrappedMostProductiveDay => 'Am produktivsten';

  @override
  String get wrappedMostIntenseDay => 'Am intensivsten';

  @override
  String get wrappedFunniestMoment => 'Lustigster';

  @override
  String get wrappedMostCringeMoment => 'Peinlichster';

  @override
  String get wrappedMinutesLabel => 'Minuten';

  @override
  String get wrappedConversationsLabel => 'Gespräche';

  @override
  String get wrappedDaysActiveLabel => 'aktive Tage';

  @override
  String get wrappedTasksGenerated => 'Aufgaben erstellt';

  @override
  String get wrappedTasksCompleted => 'Aufgaben erledigt';

  @override
  String get wrappedTopFivePhrases => 'Top 5 Phrasen';

  @override
  String get wrappedAGreatDay => 'Ein toller Tag';

  @override
  String get wrappedGettingItDone => 'Es erledigen';

  @override
  String get wrappedAChallenge => 'Eine Herausforderung';

  @override
  String get wrappedAHilariousMoment => 'Ein lustiger Moment';

  @override
  String get wrappedThatAwkwardMoment => 'Dieser peinliche Moment';

  @override
  String get wrappedYouHadFunnyMoments => 'Du hattest lustige Momente dieses Jahr!';

  @override
  String get wrappedWeveAllBeenThere => 'Das kennen wir alle!';

  @override
  String get wrappedFriend => 'Freund';

  @override
  String get wrappedYourBuddy => 'Dein Kumpel!';

  @override
  String get wrappedNotMentioned => 'Nicht erwähnt';

  @override
  String get wrappedTheHardPart => 'Der schwere Teil';

  @override
  String get wrappedPersonalGrowth => 'Persönliches Wachstum';

  @override
  String get wrappedFunDay => 'Spaß';

  @override
  String get wrappedProductiveDay => 'Produktiv';

  @override
  String get wrappedIntenseDay => 'Intensiv';

  @override
  String get wrappedFunnyMomentTitle => 'Lustiger Moment';

  @override
  String get wrappedCringeMomentTitle => 'Peinlicher Moment';

  @override
  String get wrappedYouTalkedAboutBadge => 'Du hast über gesprochen';

  @override
  String get wrappedCompletedLabel => 'Abgeschlossen';

  @override
  String get wrappedMyBuddiesCard => 'Meine Freunde';

  @override
  String get wrappedBuddiesLabel => 'FREUNDE';

  @override
  String get wrappedObsessionsLabelUpper => 'LEIDENSCHAFTEN';

  @override
  String get wrappedStruggleLabelUpper => 'KAMPF';

  @override
  String get wrappedWinLabelUpper => 'SIEG';

  @override
  String get wrappedTopPhrasesLabelUpper => 'TOP PHRASEN';

  @override
  String get wrappedYourHeader => 'Deine';

  @override
  String get wrappedTopDaysHeader => 'Top-Tage';

  @override
  String get wrappedYourTopDaysBadge => 'Deine Top-Tage';

  @override
  String get wrappedBestHeader => 'Beste';

  @override
  String get wrappedMomentsHeader => 'Momente';

  @override
  String get wrappedBestMomentsBadge => 'Beste Momente';

  @override
  String get wrappedBiggestHeader => 'Größter';

  @override
  String get wrappedStruggleHeader => 'Kampf';

  @override
  String get wrappedWinHeader => 'Sieg';

  @override
  String get wrappedButYouPushedThroughEmoji => 'Aber du hast es geschafft 💪';

  @override
  String get wrappedYouDidItEmoji => 'Du hast es geschafft! 🎉';

  @override
  String get wrappedHours => 'Stunden';

  @override
  String get wrappedActions => 'Aktionen';

  @override
  String get multipleSpeakersDetected => 'Mehrere Sprecher erkannt';

  @override
  String get multipleSpeakersDescription =>
      'Es scheint, dass mehrere Sprecher in der Aufnahme sind. Stellen Sie sicher, dass Sie an einem ruhigen Ort sind, und versuchen Sie es erneut.';

  @override
  String get invalidRecordingDetected => 'Ungültige Aufnahme erkannt';

  @override
  String get notEnoughSpeechDescription =>
      'Es wurde nicht genug Sprache erkannt. Bitte sprechen Sie mehr und versuchen Sie es erneut.';

  @override
  String get speechDurationDescription =>
      'Stellen Sie sicher, dass Sie mindestens 5 Sekunden und nicht mehr als 90 sprechen.';

  @override
  String get connectionLostDescription =>
      'Die Verbindung wurde unterbrochen. Bitte überprüfen Sie Ihre Internetverbindung und versuchen Sie es erneut.';

  @override
  String get howToTakeGoodSample => 'Wie macht man eine gute Probe?';

  @override
  String get goodSampleInstructions =>
      '1. Stellen Sie sicher, dass Sie an einem ruhigen Ort sind.\n2. Sprechen Sie klar und natürlich.\n3. Stellen Sie sicher, dass Ihr Gerät in seiner natürlichen Position an Ihrem Hals ist.\n\nSobald es erstellt ist, können Sie es jederzeit verbessern oder erneut machen.';

  @override
  String get noDeviceConnectedUseMic => 'Kein Gerät verbunden. Das Telefonmikrofon wird verwendet.';

  @override
  String get doItAgain => 'Erneut machen';

  @override
  String get listenToSpeechProfile => 'Mein Stimmprofil anhören ➡️';

  @override
  String get recognizingOthers => 'Andere erkennen 👀';

  @override
  String get keepGoingGreat => 'Weiter so, du machst das großartig';

  @override
  String get somethingWentWrongTryAgain => 'Etwas ist schiefgelaufen! Bitte versuchen Sie es später erneut.';

  @override
  String get uploadingVoiceProfile => 'Ihr Stimmprofil wird hochgeladen....';

  @override
  String get memorizingYourVoice => 'Ihre Stimme wird gespeichert...';

  @override
  String get personalizingExperience => 'Ihre Erfahrung wird personalisiert...';

  @override
  String get keepSpeakingUntil100 => 'Sprechen Sie weiter, bis Sie 100% erreichen.';

  @override
  String get greatJobAlmostThere => 'Toll gemacht, Sie sind fast fertig';

  @override
  String get soCloseJustLittleMore => 'So nah dran, nur noch ein bisschen';

  @override
  String get notificationFrequency => 'Benachrichtigungshäufigkeit';

  @override
  String get controlNotificationFrequency => 'Steuern Sie, wie oft Omi Ihnen proaktive Benachrichtigungen sendet.';

  @override
  String get yourScore => 'Ihr Score';

  @override
  String get dailyScoreBreakdown => 'Tages-Score Aufschlüsselung';

  @override
  String get todaysScore => 'Heutiger Score';

  @override
  String get tasksCompleted => 'Aufgaben erledigt';

  @override
  String get completionRate => 'Abschlussrate';

  @override
  String get howItWorks => 'So funktioniert es';

  @override
  String get dailyScoreExplanation =>
      'Ihr täglicher Score basiert auf der Aufgabenerledigung. Erledigen Sie Ihre Aufgaben, um Ihren Score zu verbessern!';

  @override
  String get notificationFrequencyDescription =>
      'Steuern Sie, wie oft Omi Ihnen proaktive Benachrichtigungen und Erinnerungen sendet.';

  @override
  String get sliderOff => 'Aus';

  @override
  String get sliderMax => 'Max.';

  @override
  String summaryGeneratedFor(String date) {
    return 'Zusammenfassung erstellt für $date';
  }

  @override
  String get failedToGenerateSummary =>
      'Zusammenfassung konnte nicht erstellt werden. Stellen Sie sicher, dass Sie Gespräche für diesen Tag haben.';

  @override
  String get recap => 'Rückblick';

  @override
  String deleteQuoted(String name) {
    return '\"$name\" löschen';
  }

  @override
  String moveConversationsTo(int count) {
    return '$count Gespräche verschieben nach:';
  }

  @override
  String get noFolder => 'Kein Ordner';

  @override
  String get removeFromAllFolders => 'Aus allen Ordnern entfernen';

  @override
  String get buildAndShareYourCustomApp => 'Erstellen und teilen Sie Ihre benutzerdefinierte App';

  @override
  String get searchAppsPlaceholder => 'Suche in 1500+ Apps';

  @override
  String get filters => 'Filter';

  @override
  String get frequencyOff => 'Aus';

  @override
  String get frequencyMinimal => 'Minimal';

  @override
  String get frequencyLow => 'Niedrig';

  @override
  String get frequencyBalanced => 'Ausgewogen';

  @override
  String get frequencyHigh => 'Hoch';

  @override
  String get frequencyMaximum => 'Maximal';

  @override
  String get frequencyDescOff => 'Keine proaktiven Benachrichtigungen';

  @override
  String get frequencyDescMinimal => 'Nur kritische Erinnerungen';

  @override
  String get frequencyDescLow => 'Nur wichtige Updates';

  @override
  String get frequencyDescBalanced => 'Regelmäßige hilfreiche Hinweise';

  @override
  String get frequencyDescHigh => 'Häufige Check-ins';

  @override
  String get frequencyDescMaximum => 'Bleiben Sie ständig engagiert';

  @override
  String get clearChatQuestion => 'Chat löschen?';

  @override
  String get syncingMessages => 'Nachrichten werden mit dem Server synchronisiert...';

  @override
  String get chatAppsTitle => 'Chat-Apps';

  @override
  String get selectApp => 'App auswählen';

  @override
  String get noChatAppsEnabled =>
      'Keine Chat-Apps aktiviert.\nTippen Sie auf \"Apps aktivieren\" um welche hinzuzufügen.';

  @override
  String get disable => 'Deaktivieren';

  @override
  String get photoLibrary => 'Fotomediathek';

  @override
  String get chooseFile => 'Datei auswählen';

  @override
  String get configureAiPersona => 'KI-Persona konfigurieren';

  @override
  String get connectAiAssistantsToYourData => 'KI-Assistenten mit deinen Daten verbinden';

  @override
  String get oAuth => 'OAuth';

  @override
  String get trackYourGoalsOnHomepage => 'Verfolge deine Ziele auf der Startseite';

  @override
  String get deleteRecording => 'Aufnahme löschen';

  @override
  String get thisCannotBeUndone => 'Dies kann nicht rückgängig gemacht werden';

  @override
  String get sdCard => 'SD Card';

  @override
  String get fromSd => 'Von SD';

  @override
  String get limitless => 'Limitless';

  @override
  String get fastTransfer => 'Schnelle Übertragung';

  @override
  String get syncingStatus => 'Synchronisierung';

  @override
  String get failedStatus => 'Fehlgeschlagen';

  @override
  String etaLabel(String time) {
    return 'ETA: $time';
  }

  @override
  String get transferMethod => 'Übertragungsmethode';

  @override
  String get fast => 'Schnell';

  @override
  String get ble => 'BLE';

  @override
  String get phone => 'Telefon';

  @override
  String get cancelSync => 'Synchronisierung abbrechen';

  @override
  String get cancelSyncMessage => 'Möchtest du die Synchronisierung wirklich abbrechen?';

  @override
  String get syncCancelled => 'Synchronisierung abgebrochen';

  @override
  String get deleteProcessedFiles => 'Verarbeitete Dateien löschen';

  @override
  String get processedFilesDeleted => 'Verarbeitete Dateien gelöscht';

  @override
  String get wifiEnableFailed => 'WLAN-Aktivierung fehlgeschlagen';

  @override
  String get deviceNoFastTransfer => 'Gerät unterstützt keine Schnellübertragung';

  @override
  String get enableHotspotMessage =>
      'Bitte aktiviere den WLAN-Hotspot auf deinem Telefon, damit sich das Omi-Gerät verbinden kann.';

  @override
  String get transferStartFailed => 'Übertragungsstart fehlgeschlagen';

  @override
  String get deviceNotResponding => 'Gerät reagiert nicht';

  @override
  String get invalidWifiCredentials => 'Ungültige WLAN-Anmeldedaten';

  @override
  String get wifiConnectionFailed => 'WLAN-Verbindung fehlgeschlagen';

  @override
  String get sdCardProcessing => 'SD-Karten-Verarbeitung';

  @override
  String sdCardProcessingMessage(int count) {
    return 'Möchtest du die verarbeiteten Dateien von der SD-Karte behalten oder löschen?';
  }

  @override
  String get process => 'Verarbeiten';

  @override
  String get wifiSyncFailed => 'WLAN-Synchronisierung fehlgeschlagen';

  @override
  String get processingFailed => 'Verarbeitung fehlgeschlagen';

  @override
  String get downloadingFromSdCard => 'Wird von SD-Karte heruntergeladen';

  @override
  String processingProgress(int current, int total) {
    return 'Verarbeitungsfortschritt';
  }

  @override
  String conversationsCreated(int count) {
    return 'Gespräche erstellt';
  }

  @override
  String get internetRequired => 'Internet erforderlich';

  @override
  String get processAudio => 'Audio verarbeiten';

  @override
  String get start => 'Starten';

  @override
  String get noRecordings => 'Keine Aufnahmen';

  @override
  String get audioFromOmiWillAppearHere => 'Audio von Omi wird hier erscheinen';

  @override
  String get deleteProcessed => 'Verarbeitete löschen';

  @override
  String get tryDifferentFilter => 'Versuche einen anderen Filter';

  @override
  String get recordings => 'Aufnahmen';

  @override
  String get enableRemindersAccess =>
      'Bitte aktivieren Sie den Zugriff auf Erinnerungen in den Einstellungen, um Apple Erinnerungen zu verwenden';

  @override
  String todayAtTime(String time) {
    return 'Heute um $time';
  }

  @override
  String yesterdayAtTime(String time) {
    return 'Gestern um $time';
  }

  @override
  String get lessThanAMinute => 'Weniger als eine Minute';

  @override
  String estimatedMinutes(int count) {
    return '~$count Minute(n)';
  }

  @override
  String estimatedHours(int count) {
    return '~$count Stunde(n)';
  }

  @override
  String estimatedTimeRemaining(String time) {
    return 'Geschätzt: $time verbleibend';
  }

  @override
  String get summarizingConversation => 'Unterhaltung wird zusammengefasst...\nDies kann einige Sekunden dauern';

  @override
  String get resummarizingConversation =>
      'Unterhaltung wird erneut zusammengefasst...\nDies kann einige Sekunden dauern';

  @override
  String get nothingInterestingRetry => 'Nichts Interessantes gefunden,\nmöchten Sie es erneut versuchen?';

  @override
  String get noSummaryForConversation => 'Keine Zusammenfassung\nfür diese Unterhaltung verfügbar.';

  @override
  String get unknownLocation => 'Unbekannter Standort';

  @override
  String get couldNotLoadMap => 'Karte konnte nicht geladen werden';

  @override
  String get triggerConversationIntegration => 'Unterhaltungs-Integration auslösen';

  @override
  String get webhookUrlNotSet => 'Webhook-URL nicht festgelegt';

  @override
  String get setWebhookUrlInSettings => 'Bitte legen Sie die Webhook-URL in den Entwicklereinstellungen fest.';

  @override
  String get sendWebUrl => 'Web-URL senden';

  @override
  String get sendTranscript => 'Transkript senden';

  @override
  String get sendSummary => 'Zusammenfassung senden';

  @override
  String get debugModeDetected => 'Debug-Modus erkannt';

  @override
  String get performanceReduced => 'Leistung um 5-10x reduziert. Verwenden Sie den Release-Modus.';

  @override
  String autoClosingInSeconds(int seconds) {
    return 'Schließt automatisch in ${seconds}s';
  }

  @override
  String get modelRequired => 'Modell erforderlich';

  @override
  String get downloadWhisperModel => 'Bitte laden Sie vor dem Speichern ein Whisper-Modell herunter.';

  @override
  String get deviceNotCompatible => 'Gerät nicht kompatibel';

  @override
  String get deviceRequirements => 'Ihr Gerät erfüllt nicht die Anforderungen für On-Device-Transkription.';

  @override
  String get willLikelyCrash => 'Das Aktivieren wird wahrscheinlich zum Absturz oder Einfrieren der App führen.';

  @override
  String get transcriptionSlowerLessAccurate => 'Die Transkription wird deutlich langsamer und weniger genau sein.';

  @override
  String get proceedAnyway => 'Trotzdem fortfahren';

  @override
  String get olderDeviceDetected => 'Älteres Gerät erkannt';

  @override
  String get onDeviceSlower => 'On-Device-Transkription kann langsamer sein.';

  @override
  String get batteryUsageHigher => 'Der Batterieverbrauch wird höher sein als bei der Cloud-Transkription.';

  @override
  String get considerOmiCloud => 'Erwägen Sie die Verwendung von Omi Cloud für bessere Leistung.';

  @override
  String get highResourceUsage => 'Hohe Ressourcennutzung';

  @override
  String get onDeviceIntensive => 'On-Device-Transkription ist rechenintensiv.';

  @override
  String get batteryDrainIncrease => 'Der Batterieverbrauch wird deutlich steigen.';

  @override
  String get deviceMayWarmUp => 'Das Gerät kann sich bei längerer Nutzung erwärmen.';

  @override
  String get speedAccuracyLower => 'Geschwindigkeit und Genauigkeit können niedriger sein als bei Cloud-Modellen.';

  @override
  String get cloudProvider => 'Cloud-Anbieter';

  @override
  String get premiumMinutesInfo =>
      '1.200 Premium-Minuten/Monat. Der Tab Auf Gerät bietet unbegrenzte kostenlose Transkription.';

  @override
  String get viewUsage => 'Nutzung anzeigen';

  @override
  String get localProcessingInfo =>
      'Audio wird lokal verarbeitet. Funktioniert offline, privater, verbraucht aber mehr Akku.';

  @override
  String get model => 'Modell';

  @override
  String get performanceWarning => 'Leistungswarnung';

  @override
  String get largeModelWarning =>
      'Dieses Modell ist groß und kann die App zum Absturz bringen oder sehr langsam laufen.\n\nsmall oder base wird empfohlen.';

  @override
  String get usingNativeIosSpeech => 'Verwende native iOS-Spracherkennung';

  @override
  String get noModelDownloadRequired =>
      'Die native Sprach-Engine Ihres Geräts wird verwendet. Kein Modell-Download erforderlich.';

  @override
  String get modelReady => 'Modell bereit';

  @override
  String get redownload => 'Erneut herunterladen';

  @override
  String get doNotCloseApp => 'Bitte schließen Sie die App nicht.';

  @override
  String get downloading => 'Wird heruntergeladen...';

  @override
  String get downloadModel => 'Modell herunterladen';

  @override
  String estimatedSize(String size) {
    return 'Geschätzte Größe: ~$size MB';
  }

  @override
  String availableSpace(String space) {
    return 'Verfügbarer Speicher: $space';
  }

  @override
  String get notEnoughSpace => 'Warnung: Nicht genug Speicherplatz!';

  @override
  String get download => 'Herunterladen';

  @override
  String downloadError(String error) {
    return 'Download-Fehler: $error';
  }

  @override
  String get cancelled => 'Abgebrochen';

  @override
  String get deviceNotCompatibleTitle => 'Gerät nicht kompatibel';

  @override
  String get deviceNotMeetRequirements =>
      'Ihr Gerät erfüllt nicht die Anforderungen für die Transkription auf dem Gerät.';

  @override
  String get transcriptionSlowerOnDevice => 'Die Transkription auf dem Gerät kann auf diesem Gerät langsamer sein.';

  @override
  String get computationallyIntensive => 'Die Transkription auf dem Gerät ist rechenintensiv.';

  @override
  String get batteryDrainSignificantly => 'Der Batterieverbrauch wird deutlich steigen.';

  @override
  String get premiumMinutesMonth =>
      '1.200 Premium-Minuten/Monat. Der Tab Auf Gerät bietet unbegrenzte kostenlose Transkription. ';

  @override
  String get audioProcessedLocally =>
      'Audio wird lokal verarbeitet. Funktioniert offline, privater, verbraucht aber mehr Batterie.';

  @override
  String get languageLabel => 'Sprache';

  @override
  String get modelLabel => 'Modell';

  @override
  String get modelTooLargeWarning =>
      'Dieses Modell ist groß und kann zum Absturz der App führen oder sehr langsam auf mobilen Geräten laufen.\n\nsmall oder base wird empfohlen.';

  @override
  String get nativeEngineNoDownload =>
      'Die native Sprach-Engine Ihres Geräts wird verwendet. Kein Modell-Download erforderlich.';

  @override
  String modelReadyWithName(String model) {
    return 'Modell bereit ($model)';
  }

  @override
  String get reDownload => 'Erneut herunterladen';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return 'Lade $model herunter: $received / $total MB';
  }

  @override
  String preparingModel(String model) {
    return 'Bereite $model vor...';
  }

  @override
  String downloadErrorWithMessage(String error) {
    return 'Download-Fehler: $error';
  }

  @override
  String estimatedSizeWithValue(String size) {
    return 'Geschätzte Größe: ~$size MB';
  }

  @override
  String availableSpaceWithValue(String space) {
    return 'Verfügbarer Speicher: $space';
  }

  @override
  String get omiTranscriptionOptimized =>
      'Omis integrierte Live-Transkription ist für Echtzeitgespräche mit automatischer Sprechererkennung und Diarisierung optimiert.';

  @override
  String get reset => 'Zurücksetzen';

  @override
  String get useTemplateFrom => 'Vorlage verwenden von';

  @override
  String get selectProviderTemplate => 'Anbietervorlage auswählen...';

  @override
  String get quicklyPopulateResponse => 'Schnell mit bekanntem Anbieter-Antwortformat ausfüllen';

  @override
  String get quicklyPopulateRequest => 'Schnell mit bekanntem Anbieter-Anforderungsformat ausfüllen';

  @override
  String get invalidJsonError => 'Ungültiges JSON';

  @override
  String downloadModelWithName(String model) {
    return 'Modell herunterladen ($model)';
  }

  @override
  String modelNameWithFile(String model) {
    return 'Modell: $model';
  }

  @override
  String get device => 'Gerät';

  @override
  String get chatAssistantsTitle => 'Chat-Assistenten';

  @override
  String get permissionReadConversations => 'Gespräche lesen';

  @override
  String get permissionReadMemories => 'Erinnerungen lesen';

  @override
  String get permissionReadTasks => 'Aufgaben lesen';

  @override
  String get permissionCreateConversations => 'Gespräche erstellen';

  @override
  String get permissionCreateMemories => 'Erinnerungen erstellen';

  @override
  String get permissionTypeAccess => 'Zugriff';

  @override
  String get permissionTypeCreate => 'Erstellen';

  @override
  String get permissionTypeTrigger => 'Auslöser';

  @override
  String get permissionDescReadConversations => 'Diese App kann auf deine Gespräche zugreifen.';

  @override
  String get permissionDescReadMemories => 'Diese App kann auf deine Erinnerungen zugreifen.';

  @override
  String get permissionDescReadTasks => 'Diese App kann auf deine Aufgaben zugreifen.';

  @override
  String get permissionDescCreateConversations => 'Diese App kann neue Gespräche erstellen.';

  @override
  String get permissionDescCreateMemories => 'Diese App kann neue Erinnerungen erstellen.';

  @override
  String get realtimeListening => 'Echtzeit-Hören';

  @override
  String get setupCompleted => 'Abgeschlossen';

  @override
  String get pleaseSelectRating => 'Bitte wähle eine Bewertung';

  @override
  String get writeReviewOptional => 'Bewertung schreiben (optional)';

  @override
  String get setupQuestionsIntro => 'Hilf uns, Omi zu verbessern, indem du ein paar Fragen beantwortest. 🫶 💜';

  @override
  String get setupQuestionProfession => '1. Was machst du beruflich?';

  @override
  String get setupQuestionUsage => '2. Wo planst du, dein Omi zu verwenden?';

  @override
  String get setupQuestionAge => '3. In welcher Altersgruppe bist du?';

  @override
  String get setupAnswerAllQuestions => 'Du hast noch nicht alle Fragen beantwortet! 🥺';

  @override
  String get setupSkipHelp => 'Überspringen, ich möchte nicht helfen :C';

  @override
  String get professionEntrepreneur => 'Unternehmer';

  @override
  String get professionSoftwareEngineer => 'Softwareentwickler';

  @override
  String get professionProductManager => 'Produktmanager';

  @override
  String get professionExecutive => 'Führungskraft';

  @override
  String get professionSales => 'Vertrieb';

  @override
  String get professionStudent => 'Student';

  @override
  String get usageAtWork => 'Bei der Arbeit';

  @override
  String get usageIrlEvents => 'Bei Veranstaltungen';

  @override
  String get usageOnline => 'Online-Nutzung';

  @override
  String get usageSocialSettings => 'In sozialen Umgebungen';

  @override
  String get usageEverywhere => 'Überall';

  @override
  String get customBackendUrlTitle => 'Benutzerdefinierte Backend-URL';

  @override
  String get backendUrlLabel => 'Backend-URL';

  @override
  String get saveUrlButton => 'URL speichern';

  @override
  String get enterBackendUrlError => 'Bitte geben Sie die Backend-URL ein';

  @override
  String get urlMustEndWithSlashError => 'URL muss mit \"/\" enden';

  @override
  String get invalidUrlError => 'Bitte geben Sie eine gültige URL ein';

  @override
  String get backendUrlSavedSuccess => 'Backend-URL erfolgreich gespeichert!';

  @override
  String get signInTitle => 'Anmelden';

  @override
  String get signInButton => 'Anmelden';

  @override
  String get enterEmailError => 'Bitte geben Sie Ihre E-Mail ein';

  @override
  String get invalidEmailError => 'Bitte geben Sie eine gültige E-Mail ein';

  @override
  String get enterPasswordError => 'Bitte geben Sie Ihr Passwort ein';

  @override
  String get passwordMinLengthError => 'Das Passwort muss mindestens 8 Zeichen lang sein';

  @override
  String get signInSuccess => 'Anmeldung erfolgreich!';

  @override
  String get alreadyHaveAccountLogin => 'Haben Sie bereits ein Konto? Anmelden';

  @override
  String get emailLabel => 'E-Mail';

  @override
  String get passwordLabel => 'Passwort';

  @override
  String get createAccountTitle => 'Konto erstellen';

  @override
  String get nameLabel => 'Name';

  @override
  String get repeatPasswordLabel => 'Passwort wiederholen';

  @override
  String get signUpButton => 'Registrieren';

  @override
  String get enterNameError => 'Bitte geben Sie Ihren Namen ein';

  @override
  String get passwordsDoNotMatch => 'Passwörter stimmen nicht überein';

  @override
  String get signUpSuccess => 'Registrierung erfolgreich!';

  @override
  String get loadingKnowledgeGraph => 'Wissensgraph wird geladen...';

  @override
  String get noKnowledgeGraphYet => 'Noch kein Wissensgraph vorhanden';

  @override
  String get buildingKnowledgeGraphFromMemories => 'Wissensgraph wird aus Erinnerungen erstellt...';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'Ihr Wissensgraph wird automatisch erstellt, wenn Sie neue Erinnerungen anlegen.';

  @override
  String get buildGraphButton => 'Graph erstellen';

  @override
  String get checkOutMyMemoryGraph => 'Schau dir meinen Erinnerungsgraphen an!';

  @override
  String get getButton => 'Laden';

  @override
  String openingApp(String appName) {
    return 'Öffne $appName...';
  }

  @override
  String get writeSomething => 'Schreiben Sie etwas';

  @override
  String get submitReply => 'Antwort senden';

  @override
  String get editYourReply => 'Antwort bearbeiten';

  @override
  String get replyToReview => 'Auf Bewertung antworten';

  @override
  String get rateAndReviewThisApp => 'Bewerte und rezensiere diese App';

  @override
  String get noChangesInReview => 'Keine Änderungen in der Bewertung zu aktualisieren.';

  @override
  String get cantRateWithoutInternet => 'Kann App ohne Internetverbindung nicht bewerten.';

  @override
  String get appAnalytics => 'App-Analytik';

  @override
  String get learnMoreLink => 'mehr erfahren';

  @override
  String get moneyEarned => 'Verdient';

  @override
  String get writeYourReply => 'Schreibe deine Antwort...';

  @override
  String get replySentSuccessfully => 'Antwort erfolgreich gesendet';

  @override
  String failedToSendReply(String error) {
    return 'Antwort konnte nicht gesendet werden: $error';
  }

  @override
  String get send => 'Senden';

  @override
  String starFilter(int count) {
    return '$count Stern';
  }

  @override
  String get noReviewsFound => 'Keine Bewertungen gefunden';

  @override
  String get editReply => 'Antwort bearbeiten';

  @override
  String get reply => 'Antworten';

  @override
  String starFilterLabel(int count) {
    return '$count Stern';
  }

  @override
  String get sharePublicLink => 'Öffentlichen Link teilen';

  @override
  String get makePersonaPublic => 'Persona öffentlich machen';

  @override
  String get connectedKnowledgeData => 'Verbundene Wissensdaten';

  @override
  String get enterName => 'Name eingeben';

  @override
  String get disconnectTwitter => 'X trennen';

  @override
  String get disconnectTwitterConfirmation => 'Bist du sicher, dass du X trennen möchtest?';

  @override
  String get getOmiDeviceDescription => 'Hol dir ein Omi-Gerät, um Gespräche automatisch aufzuzeichnen';

  @override
  String get getOmi => 'Omi holen';

  @override
  String get iHaveOmiDevice => 'Ich habe ein Omi-Gerät';

  @override
  String get goal => 'ZIEL';

  @override
  String get tapToTrackThisGoal => 'Tippen, um dieses Ziel zu verfolgen';

  @override
  String get tapToSetAGoal => 'Tippen, um ein Ziel zu setzen';

  @override
  String get processedConversations => 'Verarbeitete Gespräche';

  @override
  String get updatedConversations => 'Aktualisierte Gespräche';

  @override
  String get newConversations => 'Neue Gespräche';

  @override
  String get summaryTemplate => 'Zusammenfassungsvorlage';

  @override
  String get suggestedTemplates => 'Vorgeschlagene Vorlagen';

  @override
  String get otherTemplates => 'Andere Vorlagen';

  @override
  String get availableTemplates => 'Verfügbare Vorlagen';

  @override
  String get getCreative => 'Werde kreativ';

  @override
  String get defaultLabel => 'Standard';

  @override
  String get lastUsedLabel => 'Zuletzt verwendet';

  @override
  String get setDefaultApp => 'Standard-App festlegen';

  @override
  String setDefaultAppContent(String appName) {
    return '$appName als Standard-App für Zusammenfassungen festlegen?\\n\\nDiese App wird automatisch für alle zukünftigen Gesprächszusammenfassungen verwendet.';
  }

  @override
  String get setDefaultButton => 'Als Standard festlegen';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName als Standard-App für Zusammenfassungen festgelegt';
  }

  @override
  String get createCustomTemplate => 'Benutzerdefinierte Vorlage erstellen';

  @override
  String get allTemplates => 'Alle Vorlagen';

  @override
  String failedToInstallApp(String appName) {
    return 'Installation von $appName fehlgeschlagen. Bitte erneut versuchen.';
  }

  @override
  String errorInstallingApp(String appName, String error) {
    return 'Fehler bei der Installation von $appName: $error';
  }

  @override
  String tagSpeaker(int speakerId) {
    return 'Sprecher markieren';
  }

  @override
  String get personNameAlreadyExists => 'Dieser Personenname existiert bereits';

  @override
  String get selectYouFromList => 'Wähle dich selbst aus der Liste';

  @override
  String get enterPersonsName => 'Namen der Person eingeben';

  @override
  String get addPerson => 'Person hinzufügen';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'Andere Segmente von diesem Sprecher markieren?';
  }

  @override
  String get tagOtherSegments => 'Andere Segmente markieren';

  @override
  String get managePeople => 'Personen verwalten';

  @override
  String get shareViaSms => 'Per SMS teilen';

  @override
  String get selectContactsToShareSummary => 'Kontakte auswählen, um Ihre Gesprächszusammenfassung zu teilen';

  @override
  String get searchContactsHint => 'Kontakte suchen...';

  @override
  String contactsSelectedCount(int count) {
    return '$count ausgewählt';
  }

  @override
  String get clearAllSelection => 'Alle löschen';

  @override
  String get selectContactsToShare => 'Kontakte zum Teilen auswählen';

  @override
  String shareWithContactCount(int count) {
    return 'Mit $count Kontakt teilen';
  }

  @override
  String shareWithContactsCount(int count) {
    return 'Mit $count Kontakten teilen';
  }

  @override
  String get contactsPermissionRequired => 'Kontaktberechtigung erforderlich';

  @override
  String get contactsPermissionRequiredForSms => 'Kontaktberechtigung ist erforderlich, um per SMS zu teilen';

  @override
  String get grantContactsPermissionForSms => 'Bitte erteilen Sie die Kontaktberechtigung, um per SMS zu teilen';

  @override
  String get noContactsWithPhoneNumbers => 'Keine Kontakte mit Telefonnummern gefunden';

  @override
  String get noContactsMatchSearch => 'Keine Kontakte entsprechen Ihrer Suche';

  @override
  String get failedToLoadContacts => 'Kontakte konnten nicht geladen werden';

  @override
  String get failedToPrepareConversationForSharing =>
      'Gespräch konnte nicht zum Teilen vorbereitet werden. Bitte versuchen Sie es erneut.';

  @override
  String get couldNotOpenSmsApp => 'SMS-App konnte nicht geöffnet werden. Bitte versuchen Sie es erneut.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'Hier ist, worüber wir gerade gesprochen haben: $link';
  }

  @override
  String get wifiSync => 'WLAN-Synchronisierung';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item in Zwischenablage kopiert';
  }

  @override
  String get wifiConnectionFailedTitle => 'WLAN-Verbindung fehlgeschlagen';

  @override
  String connectingToDeviceName(String deviceName) {
    return 'Verbindung mit $deviceName wird hergestellt...';
  }

  @override
  String enableDeviceWifi(String deviceName) {
    return 'Geräte-WLAN aktivieren';
  }

  @override
  String connectToDeviceName(String deviceName) {
    return 'Mit $deviceName verbinden';
  }

  @override
  String get recordingDetails => 'Aufnahmedetails';

  @override
  String get storageLocationSdCard => 'SD-Karte';

  @override
  String get storageLocationLimitlessPendant => 'Limitless Pendant';

  @override
  String get storageLocationPhone => 'Telefon';

  @override
  String get storageLocationPhoneMemory => 'Telefon (Speicher)';

  @override
  String storedOnDevice(String deviceName) {
    return 'Auf dem Gerät gespeichert';
  }

  @override
  String get transferring => 'Übertragung...';

  @override
  String get transferRequired => 'Übertragung erforderlich';

  @override
  String get downloadingAudioFromSdCard => 'Audio von der SD-Karte deines Geräts wird heruntergeladen';

  @override
  String get transferRequiredDescription =>
      'Bitte übertrage die Dateien vom Gerät, um die SD-Karten-Einstellungen zu ändern.';

  @override
  String get cancelTransfer => 'Übertragung abbrechen';

  @override
  String get transferToPhone => 'Auf Telefon übertragen';

  @override
  String get privateAndSecureOnDevice => 'Privat & sicher auf dem Gerät';

  @override
  String get recordingInfo => 'Aufnahmeinfo';

  @override
  String get transferInProgress => 'Übertragung läuft';

  @override
  String get shareRecording => 'Aufnahme teilen';

  @override
  String get deleteRecordingConfirmation => 'Bist du sicher, dass du diese Aufnahme löschen möchtest?';

  @override
  String get recordingIdLabel => 'Aufnahme-ID';

  @override
  String get dateTimeLabel => 'Datum & Uhrzeit';

  @override
  String get durationLabel => 'Dauer';

  @override
  String get audioFormatLabel => 'Audioformat';

  @override
  String get storageLocationLabel => 'Speicherort';

  @override
  String get estimatedSizeLabel => 'Geschätzte Größe';

  @override
  String get deviceModelLabel => 'Gerätemodell';

  @override
  String get deviceIdLabel => 'Geräte-ID';

  @override
  String get statusLabel => 'Status';

  @override
  String get statusProcessed => 'Verarbeitet';

  @override
  String get statusUnprocessed => 'Unverarbeitet';

  @override
  String get switchedToFastTransfer => 'Auf Schnellübertragung umgeschaltet';

  @override
  String get transferCompleteMessage => 'Übertragung abgeschlossen! Du kannst diese Aufnahme jetzt abspielen.';

  @override
  String transferFailedMessage(String error) {
    return 'Übertragung fehlgeschlagen. Bitte versuche es erneut.';
  }

  @override
  String get transferCancelled => 'Übertragung abgebrochen';

  @override
  String get fastTransferEnabled => 'Schnelle Übertragung aktiviert';

  @override
  String get bluetoothSyncEnabled => 'Bluetooth-Synchronisierung aktiviert';

  @override
  String get enableFastTransfer => 'Schnelle Übertragung aktivieren';

  @override
  String get fastTransferDescription =>
      'Die schnelle Übertragung nutzt WLAN für ~5x schnellere Geschwindigkeiten. Ihr Telefon verbindet sich während der Übertragung vorübergehend mit dem WLAN-Netzwerk Ihres Omi-Geräts.';

  @override
  String get internetAccessPausedDuringTransfer => 'Der Internetzugang wird während der Übertragung unterbrochen';

  @override
  String get chooseTransferMethodDescription =>
      'Wählen Sie, wie Aufnahmen von Ihrem Omi-Gerät auf Ihr Telefon übertragen werden.';

  @override
  String get wifiSpeed => '~150 KB/s über WLAN';

  @override
  String get fiveTimesFaster => '5X SCHNELLER';

  @override
  String get fastTransferMethodDescription =>
      'Erstellt eine direkte WLAN-Verbindung zu Ihrem Omi-Gerät. Ihr Telefon trennt sich während der Übertragung vorübergehend von Ihrem normalen WLAN.';

  @override
  String get bluetooth => 'Bluetooth';

  @override
  String get bleSpeed => '~30 KB/s über BLE';

  @override
  String get bluetoothMethodDescription =>
      'Verwendet Standard-Bluetooth-Low-Energy-Verbindung. Langsamer, beeinträchtigt aber nicht Ihre WLAN-Verbindung.';

  @override
  String get selected => 'Ausgewählt';

  @override
  String get selectOption => 'Auswählen';

  @override
  String get lowBatteryAlertTitle => 'Warnung: Niedriger Akkustand';

  @override
  String get lowBatteryAlertBody => 'Der Akkustand Ihres Geräts ist niedrig. Zeit zum Aufladen! 🔋';

  @override
  String get deviceDisconnectedNotificationTitle => 'Ihr Omi-Gerät wurde getrennt';

  @override
  String get deviceDisconnectedNotificationBody => 'Bitte verbinden Sie sich erneut, um Ihr Omi weiter zu nutzen.';

  @override
  String get firmwareUpdateAvailable => 'Firmware-Update verfügbar';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'Ein neues Firmware-Update ($version) ist für Ihr Omi-Gerät verfügbar. Möchten Sie jetzt aktualisieren?';
  }

  @override
  String get later => 'Später';

  @override
  String get appDeletedSuccessfully => 'App erfolgreich gelöscht';

  @override
  String get appDeleteFailed => 'App konnte nicht gelöscht werden. Bitte versuche es später erneut.';

  @override
  String get appVisibilityChangedSuccessfully =>
      'App-Sichtbarkeit erfolgreich geändert. Es kann einige Minuten dauern, bis die Änderung wirksam wird.';

  @override
  String get errorActivatingAppIntegration =>
      'Fehler beim Aktivieren der App. Falls es sich um eine Integrations-App handelt, stelle sicher, dass die Einrichtung abgeschlossen ist.';

  @override
  String get errorUpdatingAppStatus => 'Beim Aktualisieren des App-Status ist ein Fehler aufgetreten.';

  @override
  String get calculatingETA => 'Berechne...';

  @override
  String aboutMinutesRemaining(int minutes) {
    return 'Etwa $minutes Minuten verbleibend';
  }

  @override
  String get aboutAMinuteRemaining => 'Etwa eine Minute verbleibend';

  @override
  String get almostDone => 'Fast fertig...';

  @override
  String get omiSays => 'omi says';

  @override
  String get analyzingYourData => 'Analyse deiner Daten';

  @override
  String migratingToProtection(String level) {
    return 'Migration zum Schutz...';
  }

  @override
  String get noDataToMigrateFinalizing => 'Keine Daten zu migrieren. Abschließen...';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return 'Migration von $itemType... $percentage%';
  }

  @override
  String get allObjectsMigratedFinalizing => 'Alle Objekte migriert. Abschließen...';

  @override
  String get migrationErrorOccurred => 'Ein Fehler ist während der Migration aufgetreten. Bitte versuche es erneut.';

  @override
  String get migrationComplete => 'Migration abgeschlossen';

  @override
  String dataProtectedWithSettings(String level) {
    return 'Deine Daten sind geschützt mit deinen aktuellen Datenschutzeinstellungen';
  }

  @override
  String get chatsLowercase => 'Chats';

  @override
  String get dataLowercase => 'Daten';

  @override
  String get fallNotificationTitle => 'Autsch';

  @override
  String get fallNotificationBody => 'Bist du gestürzt?';

  @override
  String get importantConversationTitle => 'Wichtiges Gespräch';

  @override
  String get importantConversationBody =>
      'Du hattest gerade ein wichtiges Gespräch. Tippe, um die Zusammenfassung zu teilen.';

  @override
  String get templateName => 'Vorlagenname';

  @override
  String get templateNameHint => 'z.B. Meeting-Aktionspunkte-Extraktor';

  @override
  String get nameMustBeAtLeast3Characters => 'Der Name muss mindestens 3 Zeichen haben';

  @override
  String get conversationPromptHint =>
      'z.B. Extrahieren Sie Aktionspunkte, getroffene Entscheidungen und wichtige Erkenntnisse aus dem Gespräch.';

  @override
  String get pleaseEnterAppPrompt => 'Bitte geben Sie eine Aufforderung für Ihre App ein';

  @override
  String get promptMustBeAtLeast10Characters => 'Die Aufforderung muss mindestens 10 Zeichen haben';

  @override
  String get anyoneCanDiscoverTemplate => 'Jeder kann Ihre Vorlage entdecken';

  @override
  String get onlyYouCanUseTemplate => 'Nur Sie können diese Vorlage verwenden';

  @override
  String get generatingDescription => 'Beschreibung wird generiert...';

  @override
  String get creatingAppIcon => 'App-Symbol wird erstellt...';

  @override
  String get installingApp => 'App wird installiert...';

  @override
  String get appCreatedAndInstalled => 'App erstellt und installiert!';

  @override
  String get appCreatedSuccessfully => 'App erfolgreich erstellt!';

  @override
  String get failedToCreateApp => 'App konnte nicht erstellt werden. Bitte versuchen Sie es erneut.';

  @override
  String get addAppSelectCoreCapability =>
      'Bitte wählen Sie eine weitere Kernfähigkeit für Ihre App aus, um fortzufahren';

  @override
  String get addAppSelectPaymentPlan =>
      'Bitte wählen Sie einen Zahlungsplan und geben Sie einen Preis für Ihre App ein';

  @override
  String get addAppSelectCapability => 'Bitte wählen Sie mindestens eine Fähigkeit für Ihre App aus';

  @override
  String get addAppSelectLogo => 'Bitte wählen Sie ein Logo für Ihre App aus';

  @override
  String get addAppEnterChatPrompt => 'Bitte geben Sie eine Chat-Eingabeaufforderung für Ihre App ein';

  @override
  String get addAppEnterConversationPrompt => 'Bitte geben Sie eine Konversations-Eingabeaufforderung für Ihre App ein';

  @override
  String get addAppSelectTriggerEvent => 'Bitte wählen Sie ein Auslöseereignis für Ihre App aus';

  @override
  String get addAppEnterWebhookUrl => 'Bitte geben Sie eine Webhook-URL für Ihre App ein';

  @override
  String get addAppSelectCategory => 'Bitte wählen Sie eine Kategorie für Ihre App aus';

  @override
  String get addAppFillRequiredFields => 'Bitte füllen Sie alle erforderlichen Felder korrekt aus';

  @override
  String get addAppUpdatedSuccess => 'App erfolgreich aktualisiert 🚀';

  @override
  String get addAppUpdateFailed => 'App-Aktualisierung fehlgeschlagen. Bitte versuchen Sie es später erneut';

  @override
  String get addAppSubmittedSuccess => 'App erfolgreich eingereicht 🚀';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'Fehler beim Öffnen der Dateiauswahl: $message';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'Fehler bei der Bildauswahl: $error';
  }

  @override
  String get addAppPhotosPermissionDenied => 'Fotozugriff verweigert. Bitte erlauben Sie den Zugriff auf Fotos';

  @override
  String get addAppErrorSelectingImageRetry => 'Fehler bei der Bildauswahl. Bitte versuchen Sie es erneut.';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'Fehler bei der Miniaturbildauswahl: $error';
  }

  @override
  String get addAppErrorSelectingThumbnailRetry => 'Fehler bei der Miniaturbildauswahl. Bitte versuchen Sie es erneut.';

  @override
  String get addAppCapabilityConflictWithPersona => 'Andere Fähigkeiten können nicht mit Persona ausgewählt werden';

  @override
  String get addAppPersonaConflictWithCapabilities => 'Persona kann nicht mit anderen Fähigkeiten ausgewählt werden';

  @override
  String get personaTwitterHandleNotFound => 'Twitter-Handle nicht gefunden';

  @override
  String get personaTwitterHandleSuspended => 'Twitter-Handle ist gesperrt';

  @override
  String get personaFailedToVerifyTwitter => 'Twitter-Handle konnte nicht verifiziert werden';

  @override
  String get personaFailedToFetch => 'Persona konnte nicht abgerufen werden';

  @override
  String get personaFailedToCreate => 'Persona konnte nicht erstellt werden';

  @override
  String get personaConnectKnowledgeSource =>
      'Bitte verbinden Sie mindestens eine Wissensdatenquelle (Omi oder Twitter)';

  @override
  String get personaUpdatedSuccessfully => 'Persona erfolgreich aktualisiert';

  @override
  String get personaFailedToUpdate => 'Persona-Aktualisierung fehlgeschlagen';

  @override
  String get personaPleaseSelectImage => 'Bitte wählen Sie ein Bild aus';

  @override
  String get personaFailedToCreateTryLater =>
      'Persona konnte nicht erstellt werden. Bitte versuchen Sie es später erneut.';

  @override
  String personaFailedToCreateWithError(String error) {
    return 'Persona-Erstellung fehlgeschlagen: $error';
  }

  @override
  String get personaFailedToEnable => 'Persona konnte nicht aktiviert werden';

  @override
  String personaErrorEnablingWithError(String error) {
    return 'Fehler beim Aktivieren der Persona: $error';
  }

  @override
  String get paymentFailedToFetchCountries =>
      'Unterstützte Länder konnten nicht abgerufen werden. Bitte versuchen Sie es später erneut.';

  @override
  String get paymentFailedToSetDefault =>
      'Standard-Zahlungsmethode konnte nicht festgelegt werden. Bitte versuchen Sie es später erneut.';

  @override
  String get paymentFailedToSavePaypal =>
      'PayPal-Details konnten nicht gespeichert werden. Bitte versuchen Sie es später erneut.';

  @override
  String get paypalEmailHint => 'nik@example.com';

  @override
  String get paypalMeLinkHint => 'paypal.me/nik';

  @override
  String get paymentMethodStripe => 'Stripe';

  @override
  String get paymentMethodPayPal => 'PayPal';

  @override
  String get paymentStatusActive => 'Aktiv';

  @override
  String get paymentStatusConnected => 'Verbunden';

  @override
  String get paymentStatusNotConnected => 'Nicht verbunden';

  @override
  String get paymentAppCost => 'App-Kosten';

  @override
  String get paymentEnterValidAmount => 'Bitte geben Sie einen gültigen Betrag ein';

  @override
  String get paymentEnterAmountGreaterThanZero => 'Bitte geben Sie einen Betrag größer als 0 ein';

  @override
  String get paymentPlan => 'Zahlungsplan';

  @override
  String get paymentNoneSelected => 'Keine Auswahl';

  @override
  String get aiGenPleaseEnterDescription => 'Bitte gib eine Beschreibung für deine App ein';

  @override
  String get aiGenCreatingAppIcon => 'App-Symbol wird erstellt...';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'Ein Fehler ist aufgetreten: $message';
  }

  @override
  String get aiGenAppCreatedSuccessfully => 'App erfolgreich erstellt!';

  @override
  String get aiGenFailedToCreateApp => 'App konnte nicht erstellt werden';

  @override
  String get aiGenErrorWhileCreatingApp => 'Beim Erstellen der App ist ein Fehler aufgetreten';

  @override
  String get aiGenFailedToGenerateApp => 'App konnte nicht generiert werden. Bitte versuche es erneut.';

  @override
  String get aiGenFailedToRegenerateIcon => 'Symbol konnte nicht neu generiert werden';

  @override
  String get aiGenPleaseGenerateAppFirst => 'Bitte generiere zuerst eine App';

  @override
  String get xHandleTitle => 'X-Handle';

  @override
  String get xHandleDescription => 'Verknüpfe dein X-Konto, um Inhalte deines Profils in deiner Persona zu verwenden';

  @override
  String get xHandleHint => '@nikshevchenko';

  @override
  String get xHandlePleaseEnter => 'Bitte gib dein X-Handle ein';

  @override
  String get xHandlePleaseEnterValid => 'Bitte gib ein gültiges X-Handle ein';

  @override
  String get nextButton => 'Weiter';

  @override
  String get connectOmiDevice => 'Omi-Gerät verbinden';

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'Dein $title-Plan wird nach deinem aktuellen Abrechnungszeitraum aktiviert';
  }

  @override
  String get planUpgradeScheduledMessage =>
      'Upgrade geplant! Dein Monatsplan läuft bis zum Ende deines Abrechnungszeitraums weiter und wechselt dann automatisch zum Jahresplan.';

  @override
  String get couldNotSchedulePlanChange => 'Die Planänderung konnte nicht geplant werden. Bitte versuche es erneut.';

  @override
  String get subscriptionReactivatedDefault => 'Dein Abonnement wurde reaktiviert.';

  @override
  String get subscriptionSuccessfulCharged => 'Abonnement erfolgreich belastet';

  @override
  String get couldNotProcessSubscription => 'Das Abonnement konnte nicht verarbeitet werden. Bitte versuche es erneut.';

  @override
  String get couldNotLaunchUpgradePage => 'Die Upgrade-Seite konnte nicht geöffnet werden. Bitte versuche es erneut.';

  @override
  String get transcriptionJsonPlaceholder => 'Fügen Sie hier Ihre JSON-Konfiguration ein...';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get pricePlaceholder => '0.00';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'Fehler beim Öffnen der Dateiauswahl: $message';
  }

  @override
  String importErrorGeneric(String error) {
    return 'Fehler: $error';
  }

  @override
  String get mergeConversationsSuccessTitle => 'Gespräche erfolgreich zusammengeführt';

  @override
  String mergeConversationsSuccessBody(int count) {
    return '$count Gespräche wurden erfolgreich zusammengeführt';
  }

  @override
  String get dailyReflectionNotificationTitle => 'Zeit für tägliche Reflexion';

  @override
  String get dailyReflectionNotificationBody => 'Erzähl mir von deinem Tag';

  @override
  String get actionItemReminderTitle => 'Omi-Erinnerung';

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName getrennt';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'Bitte erneut verbinden, um Ihr $deviceName weiter zu verwenden.';
  }

  @override
  String get onboardingSignIn => 'Anmelden';

  @override
  String get onboardingYourName => 'Dein Name';

  @override
  String get onboardingLanguage => 'Sprache';

  @override
  String get onboardingPermissions => 'Berechtigungen';

  @override
  String get onboardingComplete => 'Fertig';

  @override
  String get onboardingWelcomeToOmi => 'Willkommen bei Omi';

  @override
  String get onboardingTellUsAboutYourself => 'Erzähl uns von dir';

  @override
  String get onboardingChooseYourPreference => 'Wähle deine Präferenz';

  @override
  String get onboardingGrantRequiredAccess => 'Erforderlichen Zugriff gewähren';

  @override
  String get onboardingYoureAllSet => 'Du bist startklar';

  @override
  String get searchTranscriptOrSummary => 'Transkript oder Zusammenfassung durchsuchen...';

  @override
  String get myGoal => 'Mein Ziel';

  @override
  String get appNotAvailable => 'Hoppla! Die App, die Sie suchen, ist anscheinend nicht verfügbar.';

  @override
  String get failedToConnectTodoist => 'Verbindung zu Todoist fehlgeschlagen';

  @override
  String get failedToConnectAsana => 'Verbindung zu Asana fehlgeschlagen';

  @override
  String get failedToConnectGoogleTasks => 'Verbindung zu Google Tasks fehlgeschlagen';

  @override
  String get failedToConnectClickUp => 'Verbindung zu ClickUp fehlgeschlagen';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return 'Verbindung zu $serviceName fehlgeschlagen: $error';
  }

  @override
  String get successfullyConnectedTodoist => 'Erfolgreich mit Todoist verbunden!';

  @override
  String get failedToConnectTodoistRetry => 'Verbindung zu Todoist fehlgeschlagen. Bitte versuchen Sie es erneut.';

  @override
  String get successfullyConnectedAsana => 'Erfolgreich mit Asana verbunden!';

  @override
  String get failedToConnectAsanaRetry => 'Verbindung zu Asana fehlgeschlagen. Bitte versuchen Sie es erneut.';

  @override
  String get successfullyConnectedGoogleTasks => 'Erfolgreich mit Google Tasks verbunden!';

  @override
  String get failedToConnectGoogleTasksRetry =>
      'Verbindung zu Google Tasks fehlgeschlagen. Bitte versuchen Sie es erneut.';

  @override
  String get successfullyConnectedClickUp => 'Erfolgreich mit ClickUp verbunden!';

  @override
  String get failedToConnectClickUpRetry => 'Verbindung zu ClickUp fehlgeschlagen. Bitte versuchen Sie es erneut.';

  @override
  String get successfullyConnectedNotion => 'Erfolgreich mit Notion verbunden!';

  @override
  String get failedToRefreshNotionStatus => 'Notion-Verbindungsstatus konnte nicht aktualisiert werden.';

  @override
  String get successfullyConnectedGoogle => 'Erfolgreich mit Google verbunden!';

  @override
  String get failedToRefreshGoogleStatus => 'Google-Verbindungsstatus konnte nicht aktualisiert werden.';

  @override
  String get successfullyConnectedWhoop => 'Erfolgreich mit Whoop verbunden!';

  @override
  String get failedToRefreshWhoopStatus => 'Whoop-Verbindungsstatus konnte nicht aktualisiert werden.';

  @override
  String get successfullyConnectedGitHub => 'Erfolgreich mit GitHub verbunden!';

  @override
  String get failedToRefreshGitHubStatus => 'GitHub-Verbindungsstatus konnte nicht aktualisiert werden.';

  @override
  String get authFailedToSignInWithGoogle => 'Anmeldung mit Google fehlgeschlagen, bitte versuchen Sie es erneut.';

  @override
  String get authenticationFailed => 'Authentifizierung fehlgeschlagen. Bitte versuchen Sie es erneut.';

  @override
  String get authFailedToSignInWithApple => 'Anmeldung mit Apple fehlgeschlagen, bitte versuchen Sie es erneut.';

  @override
  String get authFailedToRetrieveToken =>
      'Firebase-Token konnte nicht abgerufen werden, bitte versuchen Sie es erneut.';

  @override
  String get authUnexpectedErrorFirebase =>
      'Unerwarteter Fehler bei der Anmeldung, Firebase-Fehler, bitte versuchen Sie es erneut.';

  @override
  String get authUnexpectedError => 'Unerwarteter Fehler bei der Anmeldung, bitte versuchen Sie es erneut';

  @override
  String get authFailedToLinkGoogle => 'Verknüpfung mit Google fehlgeschlagen, bitte versuchen Sie es erneut.';

  @override
  String get authFailedToLinkApple => 'Verknüpfung mit Apple fehlgeschlagen, bitte versuchen Sie es erneut.';

  @override
  String get onboardingBluetoothRequired =>
      'Bluetooth-Berechtigung ist erforderlich, um sich mit Ihrem Gerät zu verbinden.';

  @override
  String get onboardingBluetoothDeniedSystemPrefs =>
      'Bluetooth-Berechtigung verweigert. Bitte erteilen Sie die Berechtigung in den Systemeinstellungen.';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'Bluetooth-Berechtigungsstatus: $status. Bitte überprüfen Sie die Systemeinstellungen.';
  }

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'Bluetooth-Berechtigung konnte nicht überprüft werden: $error';
  }

  @override
  String get onboardingNotificationDeniedSystemPrefs =>
      'Benachrichtigungsberechtigung verweigert. Bitte erteilen Sie die Berechtigung in den Systemeinstellungen.';

  @override
  String get onboardingNotificationDeniedNotifications =>
      'Benachrichtigungsberechtigung verweigert. Bitte erteilen Sie die Berechtigung in Systemeinstellungen > Mitteilungen.';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return 'Benachrichtigungsberechtigungsstatus: $status. Bitte überprüfen Sie die Systemeinstellungen.';
  }

  @override
  String onboardingFailedCheckNotification(String error) {
    return 'Benachrichtigungsberechtigung konnte nicht überprüft werden: $error';
  }

  @override
  String get onboardingLocationGrantInSettings =>
      'Bitte erteilen Sie die Standortberechtigung in Einstellungen > Datenschutz & Sicherheit > Ortungsdienste';

  @override
  String get onboardingMicrophoneRequired => 'Mikrofonberechtigung ist für die Aufnahme erforderlich.';

  @override
  String get onboardingMicrophoneDenied =>
      'Mikrofonberechtigung verweigert. Bitte erteilen Sie die Berechtigung in Systemeinstellungen > Datenschutz & Sicherheit > Mikrofon.';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'Mikrofonberechtigungsstatus: $status. Bitte überprüfen Sie die Systemeinstellungen.';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'Mikrofonberechtigung konnte nicht überprüft werden: $error';
  }

  @override
  String get onboardingScreenCaptureRequired =>
      'Bildschirmaufnahme-Berechtigung ist für die Systemtonaufnahme erforderlich.';

  @override
  String get onboardingScreenCaptureDenied =>
      'Bildschirmaufnahme-Berechtigung verweigert. Bitte erteilen Sie die Berechtigung in Systemeinstellungen > Datenschutz & Sicherheit > Bildschirmaufnahme.';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return 'Bildschirmaufnahme-Berechtigungsstatus: $status. Bitte überprüfen Sie die Systemeinstellungen.';
  }

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return 'Bildschirmaufnahme-Berechtigung konnte nicht überprüft werden: $error';
  }

  @override
  String get onboardingAccessibilityRequired =>
      'Bedienungshilfen-Berechtigung ist erforderlich, um Browser-Meetings zu erkennen.';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'Bedienungshilfen-Berechtigungsstatus: $status. Bitte überprüfen Sie die Systemeinstellungen.';
  }

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'Bedienungshilfen-Berechtigung konnte nicht überprüft werden: $error';
  }

  @override
  String get msgCameraNotAvailable => 'Kameraaufnahme ist auf dieser Plattform nicht verfügbar';

  @override
  String get msgCameraPermissionDenied =>
      'Kameraberechtigung verweigert. Bitte erlauben Sie den Zugriff auf die Kamera';

  @override
  String msgCameraAccessError(String error) {
    return 'Fehler beim Zugriff auf die Kamera: $error';
  }

  @override
  String get msgPhotoError => 'Fehler beim Aufnehmen des Fotos. Bitte versuchen Sie es erneut.';

  @override
  String get msgMaxImagesLimit => 'Sie können nur bis zu 4 Bilder auswählen';

  @override
  String msgFilePickerError(String error) {
    return 'Fehler beim Öffnen der Dateiauswahl: $error';
  }

  @override
  String msgSelectImagesError(String error) {
    return 'Fehler beim Auswählen von Bildern: $error';
  }

  @override
  String get msgPhotosPermissionDenied =>
      'Fotos-Berechtigung verweigert. Bitte erlauben Sie den Zugriff auf Fotos, um Bilder auszuwählen';

  @override
  String get msgSelectImagesGenericError => 'Fehler beim Auswählen von Bildern. Bitte versuchen Sie es erneut.';

  @override
  String get msgMaxFilesLimit => 'Sie können nur bis zu 4 Dateien auswählen';

  @override
  String msgSelectFilesError(String error) {
    return 'Fehler beim Auswählen von Dateien: $error';
  }

  @override
  String get msgSelectFilesGenericError => 'Fehler beim Auswählen von Dateien. Bitte versuchen Sie es erneut.';

  @override
  String get msgUploadFileFailed => 'Datei-Upload fehlgeschlagen, bitte versuchen Sie es später erneut';

  @override
  String get msgReadingMemories => 'Lese deine Erinnerungen...';

  @override
  String get msgLearningMemories => 'Lerne aus deinen Erinnerungen...';

  @override
  String get msgUploadAttachedFileFailed => 'Hochladen der angehängten Datei fehlgeschlagen.';

  @override
  String captureRecordingError(String error) {
    return 'Bei der Aufnahme ist ein Fehler aufgetreten: $error';
  }

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return 'Aufnahme gestoppt: $reason. Möglicherweise müssen Sie externe Bildschirme erneut anschließen oder die Aufnahme neu starten.';
  }

  @override
  String get captureMicrophonePermissionRequired => 'Mikrofonberechtigung erforderlich';

  @override
  String get captureMicrophonePermissionInSystemPreferences =>
      'Mikrofonberechtigung in den Systemeinstellungen erteilen';

  @override
  String get captureScreenRecordingPermissionRequired => 'Bildschirmaufnahme-Berechtigung erforderlich';

  @override
  String get captureDisplayDetectionFailed => 'Bildschirmerkennung fehlgeschlagen. Aufnahme gestoppt.';

  @override
  String get devModeInvalidAudioBytesWebhookUrl => 'Ungültige Webhook-URL für Audio-Bytes';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl => 'Ungültige Webhook-URL für Echtzeit-Transkription';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl => 'Ungültige Webhook-URL für erstellte Konversation';

  @override
  String get devModeInvalidDaySummaryWebhookUrl => 'Ungültige Webhook-URL für Tageszusammenfassung';

  @override
  String get devModeSettingsSaved => 'Einstellungen gespeichert!';

  @override
  String get voiceFailedToTranscribe => 'Audiotranskription fehlgeschlagen';

  @override
  String get locationPermissionRequired => 'Standortberechtigung erforderlich';

  @override
  String get locationPermissionContent =>
      'Schnelltransfer benötigt die Standortberechtigung, um die WLAN-Verbindung zu überprüfen. Bitte erteilen Sie die Standortberechtigung, um fortzufahren.';

  @override
  String get pdfTranscriptExport => 'Transkript-Export';

  @override
  String get pdfConversationExport => 'Gesprächs-Export';

  @override
  String pdfTitleLabel(String title) {
    return 'Titel: $title';
  }

  @override
  String get conversationNewIndicator => 'Neu 🚀';

  @override
  String conversationPhotosCount(int count) {
    return '$count Fotos';
  }

  @override
  String get mergingStatus => 'Zusammenführen...';

  @override
  String timeSecsSingular(int count) {
    return '$count Sek';
  }

  @override
  String timeSecsPlural(int count) {
    return '$count Sek';
  }

  @override
  String timeMinSingular(int count) {
    return '$count Min';
  }

  @override
  String timeMinsPlural(int count) {
    return '$count Min';
  }

  @override
  String timeMinsAndSecs(int mins, int secs) {
    return '$mins Min $secs Sek';
  }

  @override
  String timeHourSingular(int count) {
    return '$count Stunde';
  }

  @override
  String timeHoursPlural(int count) {
    return '$count Stunden';
  }

  @override
  String timeHoursAndMins(int hours, int mins) {
    return '$hours Stunden $mins Min';
  }

  @override
  String timeDaySingular(int count) {
    return '$count Tag';
  }

  @override
  String timeDaysPlural(int count) {
    return '$count Tage';
  }

  @override
  String timeDaysAndHours(int days, int hours) {
    return '$days Tage $hours Stunden';
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
  String get moveToFolder => 'In Ordner verschieben';

  @override
  String get noFoldersAvailable => 'Keine Ordner verfügbar';

  @override
  String get newFolder => 'Neuer Ordner';

  @override
  String get color => 'Farbe';

  @override
  String get waitingForDevice => 'Warte auf Gerät...';

  @override
  String get saySomething => 'Sag etwas...';

  @override
  String get initialisingSystemAudio => 'Initialisiere Systemaudio';

  @override
  String get stopRecording => 'Aufnahme stoppen';

  @override
  String get continueRecording => 'Aufnahme fortsetzen';

  @override
  String get initialisingRecorder => 'Initialisiere Aufnahmegerät';

  @override
  String get pauseRecording => 'Aufnahme pausieren';

  @override
  String get resumeRecording => 'Aufnahme fortsetzen';

  @override
  String get noDailyRecapsYet => 'Noch keine täglichen Zusammenfassungen';

  @override
  String get dailyRecapsDescription => 'Ihre täglichen Zusammenfassungen erscheinen hier, sobald sie erstellt wurden';

  @override
  String get chooseTransferMethod => 'Übertragungsmethode wählen';

  @override
  String get fastTransferSpeed => '~150 KB/s über WiFi';

  @override
  String largeTimeGapDetected(String gap) {
    return 'Große Zeitlücke erkannt ($gap)';
  }

  @override
  String largeTimeGapsDetected(String gaps) {
    return 'Große Zeitlücken erkannt ($gaps)';
  }

  @override
  String get deviceDoesNotSupportWifiSwitchingToBle =>
      'Gerät unterstützt keine WiFi-Synchronisierung, Wechsel zu Bluetooth';

  @override
  String get appleHealthNotAvailable => 'Apple Health ist auf diesem Gerät nicht verfügbar';

  @override
  String get downloadAudio => 'Audio herunterladen';

  @override
  String get audioDownloadSuccess => 'Audio erfolgreich heruntergeladen';

  @override
  String get audioDownloadFailed => 'Audio-Download fehlgeschlagen';

  @override
  String get downloadingAudio => 'Lade Audio herunter...';

  @override
  String get shareAudio => 'Audio teilen';

  @override
  String get preparingAudio => 'Bereite Audio vor';

  @override
  String get gettingAudioFiles => 'Hole Audiodateien...';

  @override
  String get downloadingAudioProgress => 'Lade Audio herunter';

  @override
  String get processingAudio => 'Verarbeite Audio';

  @override
  String get combiningAudioFiles => 'Kombiniere Audiodateien...';

  @override
  String get audioReady => 'Audio bereit';

  @override
  String get openingShareSheet => 'Öffne Freigabeblatt...';

  @override
  String get audioShareFailed => 'Teilen fehlgeschlagen';

  @override
  String get dailyRecaps => 'Tägliche Zusammenfassungen';

  @override
  String get removeFilter => 'Filter Entfernen';

  @override
  String get categoryConversationAnalysis => 'Gesprächsanalyse';

  @override
  String get categoryPersonalityClone => 'Persönlichkeitsklon';

  @override
  String get categoryHealth => 'Gesundheit';

  @override
  String get categoryEducation => 'Bildung';

  @override
  String get categoryCommunication => 'Kommunikation';

  @override
  String get categoryEmotionalSupport => 'Emotionale Unterstützung';

  @override
  String get categoryProductivity => 'Produktivität';

  @override
  String get categoryEntertainment => 'Unterhaltung';

  @override
  String get categoryFinancial => 'Finanzen';

  @override
  String get categoryTravel => 'Reisen';

  @override
  String get categorySafety => 'Sicherheit';

  @override
  String get categoryShopping => 'Einkaufen';

  @override
  String get categorySocial => 'Soziales';

  @override
  String get categoryNews => 'Nachrichten';

  @override
  String get categoryUtilities => 'Werkzeuge';

  @override
  String get categoryOther => 'Sonstiges';

  @override
  String get capabilityChat => 'Chat';

  @override
  String get capabilityConversations => 'Gespräche';

  @override
  String get capabilityExternalIntegration => 'Externe Integration';

  @override
  String get capabilityNotification => 'Benachrichtigung';

  @override
  String get triggerAudioBytes => 'Audio-Bytes';

  @override
  String get triggerConversationCreation => 'Gesprächserstellung';

  @override
  String get triggerTranscriptProcessed => 'Transkript verarbeitet';

  @override
  String get actionCreateConversations => 'Gespräche erstellen';

  @override
  String get actionCreateMemories => 'Erinnerungen erstellen';

  @override
  String get actionReadConversations => 'Gespräche lesen';

  @override
  String get actionReadMemories => 'Erinnerungen lesen';

  @override
  String get actionReadTasks => 'Aufgaben lesen';

  @override
  String get scopeUserName => 'Benutzername';

  @override
  String get scopeUserFacts => 'Benutzerfakten';

  @override
  String get scopeUserConversations => 'Benutzergespräche';

  @override
  String get scopeUserChat => 'Benutzer-Chat';

  @override
  String get capabilitySummary => 'Zusammenfassung';

  @override
  String get capabilityFeatured => 'Empfohlen';

  @override
  String get capabilityTasks => 'Aufgaben';

  @override
  String get capabilityIntegrations => 'Integrationen';

  @override
  String get categoryPersonalityClones => 'Persönlichkeitsklone';

  @override
  String get categoryProductivityLifestyle => 'Produktivität & Lebensstil';

  @override
  String get categorySocialEntertainment => 'Soziales & Unterhaltung';

  @override
  String get categoryProductivityTools => 'Produktivitätswerkzeuge';

  @override
  String get categoryPersonalWellness => 'Persönliches Wohlbefinden';

  @override
  String get rating => 'Bewertung';

  @override
  String get categories => 'Kategorien';

  @override
  String get sortBy => 'Sortieren';

  @override
  String get highestRating => 'Höchste Bewertung';

  @override
  String get lowestRating => 'Niedrigste Bewertung';

  @override
  String get resetFilters => 'Filter zurücksetzen';

  @override
  String get applyFilters => 'Filter anwenden';

  @override
  String get mostInstalls => 'Meiste Installationen';

  @override
  String get couldNotOpenUrl => 'Die URL konnte nicht geöffnet werden. Bitte versuchen Sie es erneut.';

  @override
  String get newTask => 'Neue Aufgabe';

  @override
  String get viewAll => 'Alle anzeigen';

  @override
  String get addTask => 'Aufgabe hinzufügen';

  @override
  String get addMcpServer => 'MCP-Server hinzufügen';

  @override
  String get connectExternalAiTools => 'Externe KI-Tools verbinden';

  @override
  String get mcpServerUrl => 'MCP Server URL';

  @override
  String mcpServerConnected(int count) {
    return '$count Tools erfolgreich verbunden';
  }

  @override
  String get mcpConnectionFailed => 'Verbindung zum MCP-Server fehlgeschlagen';

  @override
  String get authorizingMcpServer => 'Autorisierung...';

  @override
  String get whereDidYouHearAboutOmi => 'Wie hast du uns gefunden?';

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
  String get friendWordOfMouth => 'Freund';

  @override
  String get otherSource => 'Sonstiges';

  @override
  String get pleaseSpecify => 'Bitte angeben';

  @override
  String get event => 'Veranstaltung';

  @override
  String get coworker => 'Kollege';

  @override
  String get linkedIn => 'LinkedIn';

  @override
  String get appStore => 'App Store';

  @override
  String get googleSearch => 'Google Search';

  @override
  String get audioPlaybackUnavailable => 'Audiodatei ist nicht zur Wiedergabe verfügbar';

  @override
  String get audioPlaybackFailed =>
      'Audio kann nicht abgespielt werden. Die Datei ist möglicherweise beschädigt oder fehlt.';

  @override
  String get connectionGuide => 'Verbindungsanleitung';

  @override
  String get iveDoneThis => 'Erledigt';

  @override
  String get pairNewDevice => 'Neues Gerät koppeln';

  @override
  String get dontSeeYourDevice => 'Gerät nicht sichtbar?';

  @override
  String get reportAnIssue => 'Problem melden';

  @override
  String get pairingTitleOmi => 'Omi einschalten';

  @override
  String get pairingDescOmi => 'Halten Sie das Gerät gedrückt, bis es vibriert, um es einzuschalten.';

  @override
  String get pairingTitleOmiDevkit => 'Omi DevKit in den Kopplungsmodus versetzen';

  @override
  String get pairingDescOmiDevkit =>
      'Drücken Sie die Taste einmal zum Einschalten. Die LED blinkt lila im Kopplungsmodus.';

  @override
  String get pairingTitleOmiGlass => 'Omi Glass einschalten';

  @override
  String get pairingDescOmiGlass => 'Halten Sie die Seitentaste 3 Sekunden gedrückt, um einzuschalten.';

  @override
  String get pairingTitlePlaudNote => 'Plaud Note in den Kopplungsmodus versetzen';

  @override
  String get pairingDescPlaudNote =>
      'Halten Sie die Seitentaste 2 Sekunden gedrückt. Die rote LED blinkt, wenn das Gerät kopplungsbereit ist.';

  @override
  String get pairingTitleBee => 'Bee in den Kopplungsmodus versetzen';

  @override
  String get pairingDescBee => 'Drücken Sie die Taste 5 Mal hintereinander. Das Licht blinkt dann blau und grün.';

  @override
  String get pairingTitleLimitless => 'Limitless in den Kopplungsmodus versetzen';

  @override
  String get pairingDescLimitless =>
      'Wenn ein Licht sichtbar ist, drücken Sie einmal und halten Sie dann gedrückt, bis das Gerät ein rosa Licht zeigt, dann loslassen.';

  @override
  String get pairingTitleFriendPendant => 'Friend Pendant in den Kopplungsmodus versetzen';

  @override
  String get pairingDescFriendPendant =>
      'Drücken Sie den Knopf am Anhänger, um ihn einzuschalten. Er wechselt automatisch in den Kopplungsmodus.';

  @override
  String get pairingTitleFieldy => 'Fieldy in den Kopplungsmodus versetzen';

  @override
  String get pairingDescFieldy => 'Halten Sie das Gerät gedrückt, bis das Licht erscheint, um es einzuschalten.';

  @override
  String get pairingTitleAppleWatch => 'Apple Watch verbinden';

  @override
  String get pairingDescAppleWatch =>
      'Installieren und öffnen Sie die Omi-App auf Ihrer Apple Watch und tippen Sie dann auf Verbinden in der App.';

  @override
  String get pairingTitleNeoOne => 'Neo One in den Kopplungsmodus versetzen';

  @override
  String get pairingDescNeoOne =>
      'Halten Sie die Ein-/Aus-Taste gedrückt, bis die LED blinkt. Das Gerät wird erkennbar sein.';

  @override
  String get downloadingFromDevice => 'Wird vom Gerät heruntergeladen';

  @override
  String get reconnectingToInternet => 'Verbindung zum Internet wird wiederhergestellt...';

  @override
  String uploadingToCloud(int current, int total) {
    return 'Hochladen von $current von $total';
  }

  @override
  String get processedStatus => 'Verarbeitet';

  @override
  String get corruptedStatus => 'Beschädigt';

  @override
  String nPending(int count) {
    return '$count ausstehend';
  }

  @override
  String nProcessed(int count) {
    return '$count verarbeitet';
  }

  @override
  String get synced => 'Synchronisiert';

  @override
  String get noPendingRecordings => 'Keine ausstehenden Aufnahmen';

  @override
  String get noProcessedRecordings => 'Noch keine verarbeiteten Aufnahmen';

  @override
  String get pending => 'Ausstehend';

  @override
  String whatsNewInVersion(String version) {
    return 'Neuigkeiten in $version';
  }

  @override
  String get addToYourTaskList => 'Zur Aufgabenliste hinzufügen?';

  @override
  String get failedToCreateShareLink => 'Freigabelink konnte nicht erstellt werden';

  @override
  String get deleteGoal => 'Ziel löschen';

  @override
  String get deviceUpToDate => 'Ihr Gerät ist auf dem neuesten Stand';

  @override
  String get wifiConfiguration => 'WLAN-Konfiguration';

  @override
  String get wifiConfigurationSubtitle =>
      'Geben Sie Ihre WLAN-Zugangsdaten ein, damit das Gerät die Firmware herunterladen kann.';

  @override
  String get networkNameSsid => 'Netzwerkname (SSID)';

  @override
  String get enterWifiNetworkName => 'WLAN-Netzwerknamen eingeben';

  @override
  String get enterWifiPassword => 'WLAN-Passwort eingeben';

  @override
  String get appIconLabel => 'App Icon';

  @override
  String get onboardingWhatIKnowAboutYouTitle => 'Das weiß ich über dich';

  @override
  String get onboardingWhatIKnowAboutYouDescription =>
      'Diese Karte wird aktualisiert, wenn Omi aus Ihren Gesprächen lernt.';

  @override
  String get apiEnvironment => 'API-Umgebung';

  @override
  String get apiEnvironmentDescription => 'Wählen Sie den Server zum Verbinden';

  @override
  String get production => 'Produktion';

  @override
  String get staging => 'Testumgebung';

  @override
  String get switchRequiresRestart => 'Wechsel erfordert Neustart der App';

  @override
  String get switchApiConfirmTitle => 'API-Umgebung wechseln';

  @override
  String switchApiConfirmBody(String environment) {
    return 'Zu $environment wechseln? Sie müssen die App schließen und erneut öffnen, damit die Änderungen wirksam werden.';
  }

  @override
  String get switchAndRestart => 'Wechseln';

  @override
  String get stagingDisclaimer =>
      'Die Testumgebung kann instabil sein, inkonsistente Leistung aufweisen und Daten können verloren gehen. Nur zum Testen.';

  @override
  String get apiEnvSavedRestartRequired =>
      'Gespeichert. Schließen und öffnen Sie die App erneut, um die Änderungen anzuwenden.';

  @override
  String get shared => 'Geteilt';

  @override
  String get onlyYouCanSeeConversation => 'Nur Sie können diese Unterhaltung sehen';

  @override
  String get anyoneWithLinkCanView => 'Jeder mit dem Link kann ansehen';

  @override
  String get showDailyScoreOnHomepage => 'Tagespunktzahl auf der Startseite anzeigen';

  @override
  String get showTasksOnHomepage => 'Aufgaben auf der Startseite anzeigen';
}
