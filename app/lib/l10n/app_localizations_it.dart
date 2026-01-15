// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Italian (`it`).
class AppLocalizationsIt extends AppLocalizations {
  AppLocalizationsIt([String locale = 'it']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'Conversazione';

  @override
  String get transcriptTab => 'Trascrizione';

  @override
  String get actionItemsTab => 'Azioni';

  @override
  String get deleteConversationTitle => 'Eliminare Conversazione?';

  @override
  String get deleteConversationMessage =>
      'Sei sicuro di voler eliminare questa conversazione? Questa azione non può essere annullata.';

  @override
  String get confirm => 'Conferma';

  @override
  String get cancel => 'Annulla';

  @override
  String get ok => 'OK';

  @override
  String get delete => 'Elimina';

  @override
  String get add => 'Aggiungi';

  @override
  String get update => 'Aggiorna';

  @override
  String get save => 'Salva';

  @override
  String get edit => 'Modifica';

  @override
  String get close => 'Chiudi';

  @override
  String get clear => 'Cancella';

  @override
  String get copyTranscript => 'Copia Trascrizione';

  @override
  String get copySummary => 'Copia Riepilogo';

  @override
  String get testPrompt => 'Prova Prompt';

  @override
  String get reprocessConversation => 'Rielabora Conversazione';

  @override
  String get deleteConversation => 'Elimina Conversazione';

  @override
  String get contentCopied => 'Contenuto copiato negli appunti';

  @override
  String get failedToUpdateStarred => 'Impossibile aggiornare lo stato preferito.';

  @override
  String get conversationUrlNotShared => 'L\'URL della conversazione non può essere condiviso.';

  @override
  String get errorProcessingConversation => 'Errore durante l\'elaborazione della conversazione. Riprova più tardi.';

  @override
  String get noInternetConnection => 'Controlla la tua connessione internet e riprova.';

  @override
  String get unableToDeleteConversation => 'Impossibile Eliminare Conversazione';

  @override
  String get somethingWentWrong => 'Qualcosa è andato storto! Riprova più tardi.';

  @override
  String get copyErrorMessage => 'Copia messaggio di errore';

  @override
  String get errorCopied => 'Messaggio di errore copiato negli appunti';

  @override
  String get remaining => 'Rimanente';

  @override
  String get loading => 'Caricamento...';

  @override
  String get loadingDuration => 'Caricamento durata...';

  @override
  String secondsCount(int count) {
    return '$count secondi';
  }

  @override
  String get people => 'Persone';

  @override
  String get addNewPerson => 'Aggiungi Nuova Persona';

  @override
  String get editPerson => 'Modifica Persona';

  @override
  String get createPersonHint => 'Crea una nuova persona e allena Omi a riconoscere anche il suo modo di parlare!';

  @override
  String get speechProfile => 'Profilo Vocale';

  @override
  String sampleNumber(int number) {
    return 'Campione $number';
  }

  @override
  String get settings => 'Impostazioni';

  @override
  String get language => 'Lingua';

  @override
  String get selectLanguage => 'Seleziona Lingua';

  @override
  String get deleting => 'Eliminazione...';

  @override
  String get pleaseCompleteAuthentication =>
      'Completa l\'autenticazione nel tuo browser. Una volta fatto, torna all\'app.';

  @override
  String get failedToStartAuthentication => 'Impossibile avviare l\'autenticazione';

  @override
  String get importStarted => 'Importazione avviata! Riceverai una notifica quando sarà completata.';

  @override
  String get failedToStartImport => 'Impossibile avviare l\'importazione. Riprova.';

  @override
  String get couldNotAccessFile => 'Impossibile accedere al file selezionato';

  @override
  String get askOmi => 'Chiedi a Omi';

  @override
  String get done => 'Fatto';

  @override
  String get disconnected => 'Disconnesso';

  @override
  String get searching => 'Ricerca';

  @override
  String get connectDevice => 'Connetti Dispositivo';

  @override
  String get monthlyLimitReached => 'Hai raggiunto il tuo limite mensile.';

  @override
  String get checkUsage => 'Verifica Utilizzo';

  @override
  String get syncingRecordings => 'Sincronizzazione registrazioni';

  @override
  String get recordingsToSync => 'Registrazioni da sincronizzare';

  @override
  String get allCaughtUp => 'Tutto aggiornato';

  @override
  String get sync => 'Sincronizza';

  @override
  String get pendantUpToDate => 'Il pendente è aggiornato';

  @override
  String get allRecordingsSynced => 'Tutte le registrazioni sono sincronizzate';

  @override
  String get syncingInProgress => 'Sincronizzazione in corso';

  @override
  String get readyToSync => 'Pronto per sincronizzare';

  @override
  String get tapSyncToStart => 'Tocca Sincronizza per iniziare';

  @override
  String get pendantNotConnected => 'Pendente non connesso. Connettiti per sincronizzare.';

  @override
  String get everythingSynced => 'Tutto è già sincronizzato.';

  @override
  String get recordingsNotSynced => 'Hai registrazioni che non sono ancora sincronizzate.';

  @override
  String get syncingBackground => 'Continueremo a sincronizzare le tue registrazioni in background.';

  @override
  String get noConversationsYet => 'Nessuna conversazione ancora.';

  @override
  String get noStarredConversations => 'Nessuna conversazione preferita ancora.';

  @override
  String get starConversationHint =>
      'Per aggiungere una conversazione ai preferiti, aprila e tocca l\'icona stella nell\'intestazione.';

  @override
  String get searchConversations => 'Cerca Conversazioni';

  @override
  String selectedCount(int count, Object s) {
    return '$count selezionat$s';
  }

  @override
  String get merge => 'Unisci';

  @override
  String get mergeConversations => 'Unisci Conversazioni';

  @override
  String mergeConversationsMessage(int count) {
    return 'Questo combinerà $count conversazioni in una. Tutti i contenuti saranno uniti e rigenerati.';
  }

  @override
  String get mergingInBackground => 'Unione in background. Potrebbe richiedere un momento.';

  @override
  String get failedToStartMerge => 'Impossibile avviare l\'unione';

  @override
  String get askAnything => 'Chiedi qualsiasi cosa';

  @override
  String get noMessagesYet => 'Nessun messaggio ancora!\nPerché non inizi una conversazione?';

  @override
  String get deletingMessages => 'Eliminazione dei tuoi messaggi dalla memoria di Omi...';

  @override
  String get messageCopied => 'Messaggio copiato negli appunti.';

  @override
  String get cannotReportOwnMessage => 'Non puoi segnalare i tuoi stessi messaggi.';

  @override
  String get reportMessage => 'Segnala Messaggio';

  @override
  String get reportMessageConfirm => 'Sei sicuro di voler segnalare questo messaggio?';

  @override
  String get messageReported => 'Messaggio segnalato con successo.';

  @override
  String get thankYouFeedback => 'Grazie per il tuo feedback!';

  @override
  String get clearChat => 'Cancellare Chat?';

  @override
  String get clearChatConfirm => 'Sei sicuro di voler cancellare la chat? Questa azione non può essere annullata.';

  @override
  String get maxFilesLimit => 'Puoi caricare solo 4 file alla volta';

  @override
  String get chatWithOmi => 'Chatta con Omi';

  @override
  String get apps => 'App';

  @override
  String get noAppsFound => 'Nessuna app trovata';

  @override
  String get tryAdjustingSearch => 'Prova a modificare la tua ricerca o i filtri';

  @override
  String get createYourOwnApp => 'Crea la Tua App';

  @override
  String get buildAndShareApp => 'Costruisci e condividi la tua app personalizzata';

  @override
  String get searchApps => 'Cerca tra 1500+ App';

  @override
  String get myApps => 'Le Mie App';

  @override
  String get installedApps => 'App Installate';

  @override
  String get unableToFetchApps =>
      'Impossibile recuperare le app :(\n\nControlla la tua connessione internet e riprova.';

  @override
  String get aboutOmi => 'Informazioni su Omi';

  @override
  String get privacyPolicy => 'Politica sulla Privacy';

  @override
  String get visitWebsite => 'Visita il Sito Web';

  @override
  String get helpOrInquiries => 'Aiuto o Richieste?';

  @override
  String get joinCommunity => 'Unisciti alla community!';

  @override
  String get membersAndCounting => '8000+ membri e in crescita.';

  @override
  String get deleteAccountTitle => 'Elimina Account';

  @override
  String get deleteAccountConfirm => 'Sei sicuro di voler eliminare il tuo account?';

  @override
  String get cannotBeUndone => 'Questa operazione non può essere annullata.';

  @override
  String get allDataErased => 'Tutti i tuoi ricordi e conversazioni saranno cancellati permanentemente.';

  @override
  String get appsDisconnected => 'Le tue App e Integrazioni saranno disconnesse immediatamente.';

  @override
  String get exportBeforeDelete =>
      'Puoi esportare i tuoi dati prima di eliminare il tuo account, ma una volta eliminato, non può essere recuperato.';

  @override
  String get deleteAccountCheckbox =>
      'Comprendo che l\'eliminazione del mio account è permanente e tutti i dati, inclusi ricordi e conversazioni, saranno persi e non potranno essere recuperati.';

  @override
  String get areYouSure => 'Sei sicuro?';

  @override
  String get deleteAccountFinal =>
      'Questa azione è irreversibile e eliminerà permanentemente il tuo account e tutti i dati associati. Sei sicuro di voler procedere?';

  @override
  String get deleteNow => 'Elimina Ora';

  @override
  String get goBack => 'Indietro';

  @override
  String get checkBoxToConfirm =>
      'Seleziona la casella per confermare di aver compreso che l\'eliminazione del tuo account è permanente e irreversibile.';

  @override
  String get profile => 'Profilo';

  @override
  String get name => 'Nome';

  @override
  String get email => 'Email';

  @override
  String get customVocabulary => 'Vocabolario Personalizzato';

  @override
  String get identifyingOthers => 'Identificazione Altri';

  @override
  String get paymentMethods => 'Metodi di Pagamento';

  @override
  String get conversationDisplay => 'Visualizzazione Conversazioni';

  @override
  String get dataPrivacy => 'Dati e Privacy';

  @override
  String get userId => 'ID Utente';

  @override
  String get notSet => 'Non impostato';

  @override
  String get userIdCopied => 'ID utente copiato negli appunti';

  @override
  String get systemDefault => 'Predefinito del Sistema';

  @override
  String get planAndUsage => 'Piano e Utilizzo';

  @override
  String get offlineSync => 'Sincronizzazione Offline';

  @override
  String get deviceSettings => 'Impostazioni Dispositivo';

  @override
  String get chatTools => 'Strumenti Chat';

  @override
  String get feedbackBug => 'Feedback / Bug';

  @override
  String get helpCenter => 'Centro Assistenza';

  @override
  String get developerSettings => 'Impostazioni Sviluppatore';

  @override
  String get getOmiForMac => 'Ottieni Omi per Mac';

  @override
  String get referralProgram => 'Programma di Riferimento';

  @override
  String get signOut => 'Disconnetti';

  @override
  String get appAndDeviceCopied => 'Dettagli app e dispositivo copiati';

  @override
  String get wrapped2025 => 'Resoconto 2025';

  @override
  String get yourPrivacyYourControl => 'La Tua Privacy, Il Tuo Controllo';

  @override
  String get privacyIntro =>
      'In Omi ci impegniamo a proteggere la tua privacy. Questa pagina ti permette di controllare come vengono archiviati e utilizzati i tuoi dati.';

  @override
  String get learnMore => 'Scopri di più...';

  @override
  String get dataProtectionLevel => 'Livello di Protezione Dati';

  @override
  String get dataProtectionDesc =>
      'I tuoi dati sono protetti di default con crittografia avanzata. Rivedi le tue impostazioni e le future opzioni di privacy qui sotto.';

  @override
  String get appAccess => 'Accesso App';

  @override
  String get appAccessDesc =>
      'Le seguenti app possono accedere ai tuoi dati. Tocca un\'app per gestire i suoi permessi.';

  @override
  String get noAppsExternalAccess => 'Nessuna app installata ha accesso esterno ai tuoi dati.';

  @override
  String get deviceName => 'Nome Dispositivo';

  @override
  String get deviceId => 'ID Dispositivo';

  @override
  String get firmware => 'Firmware';

  @override
  String get sdCardSync => 'Sincronizzazione Scheda SD';

  @override
  String get hardwareRevision => 'Revisione Hardware';

  @override
  String get modelNumber => 'Numero Modello';

  @override
  String get manufacturer => 'Produttore';

  @override
  String get doubleTap => 'Doppio Tocco';

  @override
  String get ledBrightness => 'Luminosità LED';

  @override
  String get micGain => 'Guadagno Microfono';

  @override
  String get disconnect => 'Disconnetti';

  @override
  String get forgetDevice => 'Dimentica Dispositivo';

  @override
  String get chargingIssues => 'Problemi di Ricarica';

  @override
  String get disconnectDevice => 'Disconnetti Dispositivo';

  @override
  String get unpairDevice => 'Disaccoppia Dispositivo';

  @override
  String get unpairAndForget => 'Disaccoppia e Dimentica Dispositivo';

  @override
  String get deviceDisconnectedMessage => 'Il tuo Omi è stato disconnesso 😔';

  @override
  String get deviceUnpairedMessage =>
      'Dispositivo disaccoppiato. Vai su Impostazioni > Bluetooth e dimentica il dispositivo per completare il disaccoppiamento.';

  @override
  String get unpairDialogTitle => 'Disaccoppia Dispositivo';

  @override
  String get unpairDialogMessage =>
      'Questo disaccoppierà il dispositivo in modo che possa essere connesso a un altro telefono. Dovrai andare su Impostazioni > Bluetooth e dimenticare il dispositivo per completare il processo.';

  @override
  String get deviceNotConnected => 'Dispositivo Non Connesso';

  @override
  String get connectDeviceMessage =>
      'Connetti il tuo dispositivo Omi per accedere\nalle impostazioni e alla personalizzazione del dispositivo';

  @override
  String get deviceInfoSection => 'Informazioni Dispositivo';

  @override
  String get customizationSection => 'Personalizzazione';

  @override
  String get hardwareSection => 'Hardware';

  @override
  String get v2Undetected => 'V2 non rilevato';

  @override
  String get v2UndetectedMessage =>
      'Vediamo che hai un dispositivo V1 o il tuo dispositivo non è connesso. La funzionalità della scheda SD è disponibile solo per i dispositivi V2.';

  @override
  String get endConversation => 'Termina Conversazione';

  @override
  String get pauseResume => 'Pausa/Riprendi';

  @override
  String get starConversation => 'Aggiungi ai Preferiti';

  @override
  String get doubleTapAction => 'Azione Doppio Tocco';

  @override
  String get endAndProcess => 'Termina ed Elabora Conversazione';

  @override
  String get pauseResumeRecording => 'Pausa/Riprendi Registrazione';

  @override
  String get starOngoing => 'Aggiungi Conversazione in Corso ai Preferiti';

  @override
  String get off => 'Spento';

  @override
  String get max => 'Massimo';

  @override
  String get mute => 'Muto';

  @override
  String get quiet => 'Silenzioso';

  @override
  String get normal => 'Normale';

  @override
  String get high => 'Alto';

  @override
  String get micGainDescMuted => 'Microfono disattivato';

  @override
  String get micGainDescLow => 'Molto silenzioso - per ambienti rumorosi';

  @override
  String get micGainDescModerate => 'Silenzioso - per rumore moderato';

  @override
  String get micGainDescNeutral => 'Neutrale - registrazione bilanciata';

  @override
  String get micGainDescSlightlyBoosted => 'Leggermente amplificato - uso normale';

  @override
  String get micGainDescBoosted => 'Amplificato - per ambienti silenziosi';

  @override
  String get micGainDescHigh => 'Alto - per voci distanti o basse';

  @override
  String get micGainDescVeryHigh => 'Molto alto - per sorgenti molto silenziose';

  @override
  String get micGainDescMax => 'Massimo - usare con cautela';

  @override
  String get developerSettingsTitle => 'Impostazioni Sviluppatore';

  @override
  String get saving => 'Salvataggio...';

  @override
  String get personaConfig => 'Configura la tua AI persona';

  @override
  String get beta => 'BETA';

  @override
  String get transcription => 'Trascrizione';

  @override
  String get transcriptionConfig => 'Configura provider STT';

  @override
  String get conversationTimeout => 'Timeout Conversazione';

  @override
  String get conversationTimeoutConfig => 'Imposta quando le conversazioni terminano automaticamente';

  @override
  String get importData => 'Importa Dati';

  @override
  String get importDataConfig => 'Importa dati da altre fonti';

  @override
  String get debugDiagnostics => 'Debug e Diagnostica';

  @override
  String get endpointUrl => 'URL Endpoint';

  @override
  String get noApiKeys => 'Nessuna chiave API ancora';

  @override
  String get createKeyToStart => 'Crea una chiave per iniziare';

  @override
  String get createKey => 'Crea Chiave';

  @override
  String get docs => 'Documenti';

  @override
  String get yourOmiInsights => 'Le Tue Statistiche Omi';

  @override
  String get today => 'Oggi';

  @override
  String get thisMonth => 'Questo Mese';

  @override
  String get thisYear => 'Quest\'Anno';

  @override
  String get allTime => 'Sempre';

  @override
  String get noActivityYet => 'Nessuna Attività Ancora';

  @override
  String get startConversationToSeeInsights =>
      'Inizia una conversazione con Omi\nper vedere le tue statistiche di utilizzo qui.';

  @override
  String get listening => 'Ascolto';

  @override
  String get listeningSubtitle => 'Tempo totale in cui Omi ha ascoltato attivamente.';

  @override
  String get understanding => 'Comprensione';

  @override
  String get understandingSubtitle => 'Parole comprese dalle tue conversazioni.';

  @override
  String get providing => 'Fornire';

  @override
  String get providingSubtitle => 'Azioni e note automaticamente catturate.';

  @override
  String get remembering => 'Ricordare';

  @override
  String get rememberingSubtitle => 'Fatti e dettagli ricordati per te.';

  @override
  String get unlimitedPlan => 'Piano Illimitato';

  @override
  String get managePlan => 'Gestisci Piano';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'Il tuo piano sarà annullato il $date.';
  }

  @override
  String renewsOn(String date) {
    return 'Il tuo piano si rinnova il $date.';
  }

  @override
  String get basicPlan => 'Piano Gratuito';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used di $limit min utilizzati';
  }

  @override
  String get upgrade => 'Aggiorna';

  @override
  String get upgradeToUnlimited => 'Passa a Illimitato';

  @override
  String basicPlanDesc(int limit) {
    return 'Il tuo piano include $limit minuti gratuiti al mese. Aggiorna per passare a illimitato.';
  }

  @override
  String get shareStatsMessage => 'Condivido le mie statistiche Omi! (omi.me - il tuo assistente AI sempre attivo)';

  @override
  String get sharePeriodToday => 'Oggi, Omi ha:';

  @override
  String get sharePeriodMonth => 'Questo mese, Omi ha:';

  @override
  String get sharePeriodYear => 'Quest\'anno, Omi ha:';

  @override
  String get sharePeriodAllTime => 'Finora, Omi ha:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 Ascoltato per $minutes minuti';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 Compreso $words parole';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ Fornito $count insight';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 Ricordato $count ricordi';
  }

  @override
  String get debugLogs => 'Log di Debug';

  @override
  String get debugLogsAutoDelete => 'Eliminazione automatica dopo 3 giorni.';

  @override
  String get debugLogsDesc => 'Aiuta a diagnosticare i problemi';

  @override
  String get noLogFilesFound => 'Nessun file di log trovato.';

  @override
  String get omiDebugLog => 'Log di debug Omi';

  @override
  String get logShared => 'Log condiviso';

  @override
  String get selectLogFile => 'Seleziona File di Log';

  @override
  String get shareLogs => 'Condividi Log';

  @override
  String get debugLogCleared => 'Log di debug cancellato';

  @override
  String get exportStarted => 'Esportazione avviata. Potrebbe richiedere alcuni secondi...';

  @override
  String get exportAllData => 'Esporta Tutti i Dati';

  @override
  String get exportDataDesc => 'Esporta conversazioni in un file JSON';

  @override
  String get exportedConversations => 'Conversazioni Esportate da Omi';

  @override
  String get exportShared => 'Esportazione condivisa';

  @override
  String get deleteKnowledgeGraphTitle => 'Eliminare Grafo di Conoscenza?';

  @override
  String get deleteKnowledgeGraphMessage =>
      'Questo eliminerà tutti i dati del grafo di conoscenza derivato (nodi e connessioni). I tuoi ricordi originali rimarranno al sicuro. Il grafo sarà ricostruito nel tempo o alla prossima richiesta.';

  @override
  String get knowledgeGraphDeleted => 'Grafo di Conoscenza eliminato con successo';

  @override
  String deleteGraphFailed(String error) {
    return 'Impossibile eliminare il grafo: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'Elimina Grafo di Conoscenza';

  @override
  String get deleteKnowledgeGraphDesc => 'Cancella tutti i nodi e le connessioni';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'Server MCP';

  @override
  String get mcpServerDesc => 'Connetti assistenti AI ai tuoi dati';

  @override
  String get serverUrl => 'URL Server';

  @override
  String get urlCopied => 'URL copiato';

  @override
  String get apiKeyAuth => 'Autenticazione Chiave API';

  @override
  String get header => 'Intestazione';

  @override
  String get authorizationBearer => 'Authorization: Bearer <chiave>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'ID Cliente';

  @override
  String get clientSecret => 'Segreto Cliente';

  @override
  String get useMcpApiKey => 'Usa la tua chiave API MCP';

  @override
  String get webhooks => 'Webhook';

  @override
  String get conversationEvents => 'Eventi Conversazione';

  @override
  String get newConversationCreated => 'Nuova conversazione creata';

  @override
  String get realtimeTranscript => 'Trascrizione in Tempo Reale';

  @override
  String get transcriptReceived => 'Trascrizione ricevuta';

  @override
  String get audioBytes => 'Byte Audio';

  @override
  String get audioDataReceived => 'Dati audio ricevuti';

  @override
  String get intervalSeconds => 'Intervallo (secondi)';

  @override
  String get daySummary => 'Riepilogo Giornaliero';

  @override
  String get summaryGenerated => 'Riepilogo generato';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'Aggiungi a claude_desktop_config.json';

  @override
  String get copyConfig => 'Copia Configurazione';

  @override
  String get configCopied => 'Configurazione copiata negli appunti';

  @override
  String get listeningMins => 'Ascolto (min)';

  @override
  String get understandingWords => 'Comprensione (parole)';

  @override
  String get insights => 'Insight';

  @override
  String get memories => 'Ricordi';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '$used di $limit min utilizzati questo mese';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '$used di $limit parole utilizzate questo mese';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '$used di $limit insight ottenuti questo mese';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return '$used di $limit ricordi creati questo mese';
  }

  @override
  String get visibility => 'Visibilità';

  @override
  String get visibilitySubtitle => 'Controlla quali conversazioni appaiono nella tua lista';

  @override
  String get showShortConversations => 'Mostra Conversazioni Brevi';

  @override
  String get showShortConversationsDesc => 'Visualizza conversazioni più brevi della soglia';

  @override
  String get showDiscardedConversations => 'Mostra Conversazioni Scartate';

  @override
  String get showDiscardedConversationsDesc => 'Includi conversazioni contrassegnate come scartate';

  @override
  String get shortConversationThreshold => 'Soglia Conversazione Breve';

  @override
  String get shortConversationThresholdSubtitle =>
      'Le conversazioni più brevi di questa soglia saranno nascoste se non abilitate sopra';

  @override
  String get durationThreshold => 'Soglia Durata';

  @override
  String get durationThresholdDesc => 'Nascondi conversazioni più brevi di questa soglia';

  @override
  String minLabel(int count) {
    return '$count min';
  }

  @override
  String get customVocabularyTitle => 'Vocabolario Personalizzato';

  @override
  String get addWords => 'Aggiungi Parole';

  @override
  String get addWordsDesc => 'Nomi, termini o parole non comuni';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'Connetti';

  @override
  String get comingSoon => 'Prossimamente';

  @override
  String get chatToolsFooter => 'Connetti le tue app per visualizzare dati e metriche nella chat.';

  @override
  String get completeAuthInBrowser => 'Completa l\'autenticazione nel tuo browser. Una volta fatto, torna all\'app.';

  @override
  String failedToStartAuth(String appName) {
    return 'Impossibile avviare l\'autenticazione $appName';
  }

  @override
  String disconnectAppTitle(String appName) {
    return 'Disconnettere $appName?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'Sei sicuro di volerti disconnettere da $appName? Puoi riconnetterti in qualsiasi momento.';
  }

  @override
  String disconnectedFrom(String appName) {
    return 'Disconnesso da $appName';
  }

  @override
  String get failedToDisconnect => 'Impossibile disconnettere';

  @override
  String connectTo(String appName) {
    return 'Connetti a $appName';
  }

  @override
  String authAccessMessage(String appName) {
    return 'Dovrai autorizzare Omi ad accedere ai tuoi dati $appName. Questo aprirà il tuo browser per l\'autenticazione.';
  }

  @override
  String get continueAction => 'Continua';

  @override
  String get languageTitle => 'Lingua';

  @override
  String get primaryLanguage => 'Lingua Principale';

  @override
  String get automaticTranslation => 'Traduzione Automatica';

  @override
  String get detectLanguages => 'Rileva oltre 10 lingue';

  @override
  String get authorizeSavingRecordings => 'Autorizza Salvataggio Registrazioni';

  @override
  String get thanksForAuthorizing => 'Grazie per aver autorizzato!';

  @override
  String get needYourPermission => 'Abbiamo bisogno del tuo permesso';

  @override
  String get alreadyGavePermission =>
      'Ci hai già dato il permesso di salvare le tue registrazioni. Ecco un promemoria del perché ne abbiamo bisogno:';

  @override
  String get wouldLikePermission => 'Vorremmo il tuo permesso per salvare le tue registrazioni vocali. Ecco perché:';

  @override
  String get improveSpeechProfile => 'Migliora il Tuo Profilo Vocale';

  @override
  String get improveSpeechProfileDesc =>
      'Utilizziamo le registrazioni per addestrare e migliorare ulteriormente il tuo profilo vocale personale.';

  @override
  String get trainFamilyProfiles => 'Addestra Profili per Amici e Famiglia';

  @override
  String get trainFamilyProfilesDesc =>
      'Le tue registrazioni ci aiutano a riconoscere e creare profili per i tuoi amici e familiari.';

  @override
  String get enhanceTranscriptAccuracy => 'Migliora Precisione Trascrizione';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'Man mano che il nostro modello migliora, possiamo fornire risultati di trascrizione migliori per le tue registrazioni.';

  @override
  String get legalNotice =>
      'Avviso Legale: La legalità della registrazione e dell\'archiviazione dei dati vocali può variare a seconda della tua posizione e di come utilizzi questa funzione. È tua responsabilità garantire la conformità con le leggi e i regolamenti locali.';

  @override
  String get alreadyAuthorized => 'Già Autorizzato';

  @override
  String get authorize => 'Autorizza';

  @override
  String get revokeAuthorization => 'Revoca Autorizzazione';

  @override
  String get authorizationSuccessful => 'Autorizzazione riuscita!';

  @override
  String get failedToAuthorize => 'Impossibile autorizzare. Riprova.';

  @override
  String get authorizationRevoked => 'Autorizzazione revocata.';

  @override
  String get recordingsDeleted => 'Registrazioni eliminate.';

  @override
  String get failedToRevoke => 'Impossibile revocare l\'autorizzazione. Riprova.';

  @override
  String get permissionRevokedTitle => 'Permesso Revocato';

  @override
  String get permissionRevokedMessage => 'Vuoi che rimuoviamo anche tutte le tue registrazioni esistenti?';

  @override
  String get yes => 'Sì';

  @override
  String get editName => 'Modifica Nome';

  @override
  String get howShouldOmiCallYou => 'Come dovrebbe chiamarti Omi?';

  @override
  String get enterYourName => 'Inserisci il tuo nome';

  @override
  String get nameCannotBeEmpty => 'Il nome non può essere vuoto';

  @override
  String get nameUpdatedSuccessfully => 'Nome aggiornato con successo!';

  @override
  String get calendarSettings => 'Impostazioni calendario';

  @override
  String get calendarProviders => 'Provider Calendario';

  @override
  String get macOsCalendar => 'Calendario macOS';

  @override
  String get connectMacOsCalendar => 'Connetti il tuo calendario macOS locale';

  @override
  String get googleCalendar => 'Google Calendar';

  @override
  String get syncGoogleAccount => 'Sincronizza con il tuo account Google';

  @override
  String get showMeetingsMenuBar => 'Mostra riunioni imminenti nella barra dei menu';

  @override
  String get showMeetingsMenuBarDesc =>
      'Visualizza la tua prossima riunione e il tempo rimanente nella barra dei menu di macOS';

  @override
  String get showEventsNoParticipants => 'Mostra eventi senza partecipanti';

  @override
  String get showEventsNoParticipantsDesc =>
      'Quando abilitato, Prossimi Eventi mostra eventi senza partecipanti o link video.';

  @override
  String get yourMeetings => 'Le Tue Riunioni';

  @override
  String get refresh => 'Aggiorna';

  @override
  String get noUpcomingMeetings => 'Nessuna riunione imminente trovata';

  @override
  String get checkingNextDays => 'Controllo dei prossimi 30 giorni';

  @override
  String get tomorrow => 'Domani';

  @override
  String get googleCalendarComingSoon => 'Integrazione Google Calendar in arrivo!';

  @override
  String connectedAsUser(String userId) {
    return 'Connesso come utente: $userId';
  }

  @override
  String get defaultWorkspace => 'Area di Lavoro Predefinita';

  @override
  String get tasksCreatedInWorkspace => 'Le attività saranno create in quest\'area di lavoro';

  @override
  String get defaultProjectOptional => 'Progetto Predefinito (Facoltativo)';

  @override
  String get leaveUnselectedTasks => 'Lascia non selezionato per creare attività senza un progetto';

  @override
  String get noProjectsInWorkspace => 'Nessun progetto trovato in quest\'area di lavoro';

  @override
  String get conversationTimeoutDesc =>
      'Scegli quanto tempo attendere in silenzio prima di terminare automaticamente una conversazione:';

  @override
  String get timeout2Minutes => '2 minuti';

  @override
  String get timeout2MinutesDesc => 'Termina conversazione dopo 2 minuti di silenzio';

  @override
  String get timeout5Minutes => '5 minuti';

  @override
  String get timeout5MinutesDesc => 'Termina conversazione dopo 5 minuti di silenzio';

  @override
  String get timeout10Minutes => '10 minuti';

  @override
  String get timeout10MinutesDesc => 'Termina conversazione dopo 10 minuti di silenzio';

  @override
  String get timeout30Minutes => '30 minuti';

  @override
  String get timeout30MinutesDesc => 'Termina conversazione dopo 30 minuti di silenzio';

  @override
  String get timeout4Hours => '4 ore';

  @override
  String get timeout4HoursDesc => 'Termina conversazione dopo 4 ore di silenzio';

  @override
  String get conversationEndAfterHours => 'Le conversazioni termineranno ora dopo 4 ore di silenzio';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Le conversazioni termineranno ora dopo $minutes minuto/i di silenzio';
  }

  @override
  String get tellUsPrimaryLanguage => 'Dicci la tua lingua principale';

  @override
  String get languageForTranscription =>
      'Imposta la tua lingua per trascrizioni più accurate e un\'esperienza personalizzata.';

  @override
  String get singleLanguageModeInfo =>
      'Modalità Lingua Singola attivata. La traduzione è disabilitata per una maggiore precisione.';

  @override
  String get searchLanguageHint => 'Cerca lingua per nome o codice';

  @override
  String get noLanguagesFound => 'Nessuna lingua trovata';

  @override
  String get skip => 'Salta';

  @override
  String languageSetTo(String language) {
    return 'Lingua impostata su $language';
  }

  @override
  String get failedToSetLanguage => 'Impossibile impostare la lingua';

  @override
  String appSettings(String appName) {
    return 'Impostazioni $appName';
  }

  @override
  String disconnectFromApp(String appName) {
    return 'Disconnettere da $appName?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'Questo rimuoverà la tua autenticazione $appName. Dovrai riconnetterti per usarlo di nuovo.';
  }

  @override
  String connectedToApp(String appName) {
    return 'Connesso a $appName';
  }

  @override
  String get account => 'Account';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Le tue azioni saranno sincronizzate con il tuo account $appName';
  }

  @override
  String get defaultSpace => 'Spazio Predefinito';

  @override
  String get selectSpaceInWorkspace => 'Seleziona uno spazio nella tua area di lavoro';

  @override
  String get noSpacesInWorkspace => 'Nessuno spazio trovato in quest\'area di lavoro';

  @override
  String get defaultList => 'Lista Predefinita';

  @override
  String get tasksAddedToList => 'Le attività saranno aggiunte a questa lista';

  @override
  String get noListsInSpace => 'Nessuna lista trovata in questo spazio';

  @override
  String failedToLoadRepos(String error) {
    return 'Impossibile caricare i repository: $error';
  }

  @override
  String get defaultRepoSaved => 'Repository predefinito salvato';

  @override
  String get failedToSaveDefaultRepo => 'Impossibile salvare il repository predefinito';

  @override
  String get defaultRepository => 'Repository Predefinito';

  @override
  String get selectDefaultRepoDesc =>
      'Seleziona un repository predefinito per creare issue. Puoi comunque specificare un repository diverso durante la creazione di issue.';

  @override
  String get noReposFound => 'Nessun repository trovato';

  @override
  String get private => 'Privato';

  @override
  String updatedDate(String date) {
    return 'Aggiornato $date';
  }

  @override
  String get yesterday => 'ieri';

  @override
  String daysAgo(int count) {
    return '$count giorni fa';
  }

  @override
  String get oneWeekAgo => '1 settimana fa';

  @override
  String weeksAgo(int count) {
    return '$count settimane fa';
  }

  @override
  String get oneMonthAgo => '1 mese fa';

  @override
  String monthsAgo(int count) {
    return '$count mesi fa';
  }

  @override
  String get issuesCreatedInRepo => 'Le issue saranno create nel tuo repository predefinito';

  @override
  String get taskIntegrations => 'Integrazioni Attività';

  @override
  String get configureSettings => 'Configura Impostazioni';

  @override
  String get completeAuthBrowser => 'Completa l\'autenticazione nel tuo browser. Una volta fatto, torna all\'app.';

  @override
  String failedToStartAppAuth(String appName) {
    return 'Impossibile avviare l\'autenticazione $appName';
  }

  @override
  String connectToAppTitle(String appName) {
    return 'Connetti a $appName';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Dovrai autorizzare Omi a creare attività nel tuo account $appName. Questo aprirà il tuo browser per l\'autenticazione.';
  }

  @override
  String get continueButton => 'Continua';

  @override
  String appIntegration(String appName) {
    return 'Integrazione $appName';
  }

  @override
  String integrationComingSoon(String appName) {
    return 'L\'integrazione con $appName è in arrivo! Stiamo lavorando sodo per offrirti più opzioni di gestione delle attività.';
  }

  @override
  String get gotIt => 'Capito';

  @override
  String get tasksExportedOneApp => 'Le attività possono essere esportate in un\'app alla volta.';

  @override
  String get completeYourUpgrade => 'Completa il Tuo Aggiornamento';

  @override
  String get importConfiguration => 'Importa Configurazione';

  @override
  String get exportConfiguration => 'Esporta configurazione';

  @override
  String get bringYourOwn => 'Porta il tuo';

  @override
  String get payYourSttProvider => 'Usa Omi liberamente. Paghi solo il tuo provider STT direttamente.';

  @override
  String get freeMinutesMonth => '1.200 minuti gratuiti/mese inclusi. Illimitato con ';

  @override
  String get omiUnlimited => 'Omi Unlimited';

  @override
  String get hostRequired => 'L\'host è richiesto';

  @override
  String get validPortRequired => 'È richiesta una porta valida';

  @override
  String get validWebsocketUrlRequired => 'È richiesto un URL WebSocket valido (wss://)';

  @override
  String get apiUrlRequired => 'L\'URL API è richiesto';

  @override
  String get apiKeyRequired => 'La chiave API è richiesta';

  @override
  String get invalidJsonConfig => 'Configurazione JSON non valida';

  @override
  String errorSaving(String error) {
    return 'Errore durante il salvataggio: $error';
  }

  @override
  String get configCopiedToClipboard => 'Configurazione copiata negli appunti';

  @override
  String get pasteJsonConfig => 'Incolla la tua configurazione JSON qui sotto:';

  @override
  String get addApiKeyAfterImport => 'Dovrai aggiungere la tua chiave API dopo l\'importazione';

  @override
  String get paste => 'Incolla';

  @override
  String get import => 'Importa';

  @override
  String get invalidProviderInConfig => 'Provider non valido nella configurazione';

  @override
  String importedConfig(String providerName) {
    return 'Configurazione $providerName importata';
  }

  @override
  String invalidJson(String error) {
    return 'JSON non valido: $error';
  }

  @override
  String get provider => 'Provider';

  @override
  String get live => 'Live';

  @override
  String get onDevice => 'Sul Dispositivo';

  @override
  String get apiUrl => 'URL API';

  @override
  String get enterSttHttpEndpoint => 'Inserisci il tuo endpoint HTTP STT';

  @override
  String get websocketUrl => 'URL WebSocket';

  @override
  String get enterLiveSttWebsocket => 'Inserisci il tuo endpoint WebSocket STT live';

  @override
  String get apiKey => 'Chiave API';

  @override
  String get enterApiKey => 'Inserisci la tua chiave API';

  @override
  String get storedLocallyNeverShared => 'Archiviato localmente, mai condiviso';

  @override
  String get host => 'Host';

  @override
  String get port => 'Porta';

  @override
  String get advanced => 'Avanzate';

  @override
  String get configuration => 'Configurazione';

  @override
  String get requestConfiguration => 'Configurazione Richiesta';

  @override
  String get responseSchema => 'Schema Risposta';

  @override
  String get modified => 'Modificato';

  @override
  String get resetRequestConfig => 'Ripristina configurazione richiesta predefinita';

  @override
  String get logs => 'Log';

  @override
  String get logsCopied => 'Log copiati';

  @override
  String get noLogsYet => 'Nessun log ancora. Inizia a registrare per vedere l\'attività STT personalizzata.';

  @override
  String deviceUsesCodec(String deviceName, String codecReason) {
    return '$deviceName usa $codecReason. Verrà utilizzato Omi.';
  }

  @override
  String get omiTranscription => 'Trascrizione Omi';

  @override
  String get bestInClassTranscription => 'Trascrizione all\'avanguardia senza configurazione';

  @override
  String get instantSpeakerLabels => 'Etichette dei parlanti istantanee';

  @override
  String get languageTranslation => 'Traduzione in oltre 100 lingue';

  @override
  String get optimizedForConversation => 'Ottimizzato per la conversazione';

  @override
  String get autoLanguageDetection => 'Rilevamento automatico della lingua';

  @override
  String get highAccuracy => 'Alta precisione';

  @override
  String get privacyFirst => 'Privacy al primo posto';

  @override
  String get saveChanges => 'Salva Modifiche';

  @override
  String get resetToDefault => 'Ripristina Predefinito';

  @override
  String get viewTemplate => 'Visualizza Template';

  @override
  String get trySomethingLike => 'Prova qualcosa come...';

  @override
  String get tryIt => 'Provalo';

  @override
  String get creatingPlan => 'Creazione piano';

  @override
  String get developingLogic => 'Sviluppo logica';

  @override
  String get designingApp => 'Progettazione app';

  @override
  String get generatingIconStep => 'Generazione icona';

  @override
  String get finalTouches => 'Ritocchi finali';

  @override
  String get processing => 'Elaborazione...';

  @override
  String get features => 'Funzionalità';

  @override
  String get creatingYourApp => 'Creazione della tua app...';

  @override
  String get generatingIcon => 'Generazione icona...';

  @override
  String get whatShouldWeMake => 'Cosa dovremmo creare?';

  @override
  String get appName => 'Nome App';

  @override
  String get description => 'Descrizione';

  @override
  String get publicLabel => 'Pubblico';

  @override
  String get privateLabel => 'Privato';

  @override
  String get free => 'Gratuito';

  @override
  String get perMonth => '/ Mese';

  @override
  String get tailoredConversationSummaries => 'Riepiloghi Conversazione Personalizzati';

  @override
  String get customChatbotPersonality => 'Personalità Chatbot Personalizzata';

  @override
  String get makePublic => 'Rendi pubblico';

  @override
  String get anyoneCanDiscover => 'Chiunque può scoprire la tua app';

  @override
  String get onlyYouCanUse => 'Solo tu puoi usare questa app';

  @override
  String get paidApp => 'App a pagamento';

  @override
  String get usersPayToUse => 'Gli utenti pagano per usare la tua app';

  @override
  String get freeForEveryone => 'Gratuito per tutti';

  @override
  String get perMonthLabel => '/ mese';

  @override
  String get creating => 'Creazione...';

  @override
  String get createApp => 'Crea App';

  @override
  String get searchingForDevices => 'Ricerca dispositivi...';

  @override
  String devicesFoundNearby(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'DISPOSITIVI',
      one: 'DISPOSITIVO',
    );
    return '$count $_temp0 TROVATO/I NELLE VICINANZE';
  }

  @override
  String get pairingSuccessful => 'ACCOPPIAMENTO RIUSCITO';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Errore durante la connessione all\'Apple Watch: $error';
  }

  @override
  String get dontShowAgain => 'Non mostrare più';

  @override
  String get iUnderstand => 'Ho Capito';

  @override
  String get enableBluetooth => 'Abilita Bluetooth';

  @override
  String get bluetoothNeeded =>
      'Omi ha bisogno del Bluetooth per connettersi al tuo dispositivo indossabile. Abilita il Bluetooth e riprova.';

  @override
  String get contactSupport => 'Contatta Supporto?';

  @override
  String get connectLater => 'Connetti Più Tardi';

  @override
  String get grantPermissions => 'Concedi permessi';

  @override
  String get backgroundActivity => 'Attività in background';

  @override
  String get backgroundActivityDesc => 'Consenti a Omi di funzionare in background per una migliore stabilità';

  @override
  String get locationAccess => 'Accesso posizione';

  @override
  String get locationAccessDesc => 'Abilita posizione in background per l\'esperienza completa';

  @override
  String get notifications => 'Notifiche';

  @override
  String get notificationsDesc => 'Abilita le notifiche per rimanere informato';

  @override
  String get locationServiceDisabled => 'Servizio di Localizzazione Disabilitato';

  @override
  String get locationServiceDisabledDesc =>
      'Il Servizio di Localizzazione è disabilitato. Vai su Impostazioni > Privacy e Sicurezza > Servizi di Localizzazione e abilitalo';

  @override
  String get backgroundLocationDenied => 'Accesso Posizione in Background Negato';

  @override
  String get backgroundLocationDeniedDesc =>
      'Vai nelle impostazioni del dispositivo e imposta il permesso di localizzazione su \"Consenti sempre\"';

  @override
  String get lovingOmi => 'Ti piace Omi?';

  @override
  String get leaveReviewIos =>
      'Aiutaci a raggiungere più persone lasciando una recensione sull\'App Store. Il tuo feedback è prezioso per noi!';

  @override
  String get leaveReviewAndroid =>
      'Aiutaci a raggiungere più persone lasciando una recensione sul Google Play Store. Il tuo feedback è prezioso per noi!';

  @override
  String get rateOnAppStore => 'Valuta su App Store';

  @override
  String get rateOnGooglePlay => 'Valuta su Google Play';

  @override
  String get maybeLater => 'Forse più tardi';

  @override
  String get speechProfileIntro =>
      'Omi ha bisogno di conoscere i tuoi obiettivi e la tua voce. Potrai modificarli in seguito.';

  @override
  String get getStarted => 'Inizia';

  @override
  String get allDone => 'Tutto fatto!';

  @override
  String get keepGoing => 'Continua così, stai andando alla grande';

  @override
  String get skipThisQuestion => 'Salta questa domanda';

  @override
  String get skipForNow => 'Salta per ora';

  @override
  String get connectionError => 'Errore di Connessione';

  @override
  String get connectionErrorDesc =>
      'Impossibile connettersi al server. Controlla la tua connessione internet e riprova.';

  @override
  String get invalidRecordingMultipleSpeakers => 'Registrazione non valida rilevata';

  @override
  String get multipleSpeakersDesc =>
      'Sembra che ci siano più persone che parlano nella registrazione. Assicurati di essere in un luogo silenzioso e riprova.';

  @override
  String get tooShortDesc => 'Non è stato rilevato abbastanza parlato. Parla di più e riprova.';

  @override
  String get invalidRecordingDesc => 'Assicurati di parlare per almeno 5 secondi e non più di 90.';

  @override
  String get areYouThere => 'Ci sei?';

  @override
  String get noSpeechDesc =>
      'Non abbiamo rilevato nessun parlato. Assicurati di parlare per almeno 10 secondi e non più di 3 minuti.';

  @override
  String get connectionLost => 'Connessione Persa';

  @override
  String get connectionLostDesc =>
      'La connessione è stata interrotta. Controlla la tua connessione internet e riprova.';

  @override
  String get tryAgain => 'Riprova';

  @override
  String get connectOmiOmiGlass => 'Connetti Omi / OmiGlass';

  @override
  String get continueWithoutDevice => 'Continua Senza Dispositivo';

  @override
  String get permissionsRequired => 'Permessi Richiesti';

  @override
  String get permissionsRequiredDesc =>
      'Questa app ha bisogno dei permessi Bluetooth e Posizione per funzionare correttamente. Abilitali nelle impostazioni.';

  @override
  String get openSettings => 'Apri Impostazioni';

  @override
  String get wantDifferentName => 'Vuoi farti chiamare diversamente?';

  @override
  String get whatsYourName => 'Come ti chiami?';

  @override
  String get speakTranscribeSummarize => 'Parla. Trascrivi. Riassumi.';

  @override
  String get signInWithApple => 'Accedi con Apple';

  @override
  String get signInWithGoogle => 'Accedi con Google';

  @override
  String get byContinuingAgree => 'Continuando, accetti la nostra ';

  @override
  String get termsOfUse => 'Condizioni d\'Uso';

  @override
  String get omiYourAiCompanion => 'Omi – Il Tuo Compagno AI';

  @override
  String get captureEveryMoment =>
      'Cattura ogni momento. Ottieni riepiloghi\nbasati sull\'AI. Non prendere mai più appunti.';

  @override
  String get appleWatchSetup => 'Configurazione Apple Watch';

  @override
  String get permissionRequestedExclaim => 'Permesso Richiesto!';

  @override
  String get microphonePermission => 'Permesso Microfono';

  @override
  String get permissionGrantedNow =>
      'Permesso concesso! Ora:\n\nApri l\'app Omi sul tuo watch e tocca \"Continua\" qui sotto';

  @override
  String get needMicrophonePermission =>
      'Abbiamo bisogno del permesso microfono.\n\n1. Tocca \"Concedi Permesso\"\n2. Consenti sul tuo iPhone\n3. L\'app Watch si chiuderà\n4. Riaprila e tocca \"Continua\"';

  @override
  String get grantPermissionButton => 'Concedi Permesso';

  @override
  String get needHelp => 'Serve Aiuto?';

  @override
  String get troubleshootingSteps =>
      'Risoluzione problemi:\n\n1. Assicurati che Omi sia installato sul tuo watch\n2. Apri l\'app Omi sul tuo watch\n3. Cerca il popup di permesso\n4. Tocca \"Consenti\" quando richiesto\n5. L\'app sul watch si chiuderà - riaprila\n6. Torna e tocca \"Continua\" sul tuo iPhone';

  @override
  String get recordingStartedSuccessfully => 'Registrazione avviata con successo!';

  @override
  String get permissionNotGrantedYet =>
      'Permesso non ancora concesso. Assicurati di aver consentito l\'accesso al microfono e di aver riaperto l\'app sul tuo watch.';

  @override
  String errorRequestingPermission(String error) {
    return 'Errore durante la richiesta del permesso: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'Errore durante l\'avvio della registrazione: $error';
  }

  @override
  String get selectPrimaryLanguage => 'Seleziona la tua lingua principale';

  @override
  String get languageBenefits => 'Imposta la tua lingua per trascrizioni più accurate e un\'esperienza personalizzata';

  @override
  String get whatsYourPrimaryLanguage => 'Qual è la tua lingua principale?';

  @override
  String get selectYourLanguage => 'Seleziona la tua lingua';

  @override
  String get personalGrowthJourney => 'Il tuo percorso di crescita personale con un\'AI che ascolta ogni tua parola.';

  @override
  String get actionItemsTitle => 'Da Fare';

  @override
  String get actionItemsDescription => 'Tocca per modificare • Tieni premuto per selezionare • Scorri per azioni';

  @override
  String get tabToDo => 'Da Fare';

  @override
  String get tabDone => 'Fatto';

  @override
  String get tabOld => 'Vecchi';

  @override
  String get emptyTodoMessage => '🎉 Tutto a posto!\nNessuna azione in sospeso';

  @override
  String get emptyDoneMessage => 'Nessun elemento completato ancora';

  @override
  String get emptyOldMessage => '✅ Nessuna attività vecchia';

  @override
  String get noItems => 'Nessun elemento';

  @override
  String get actionItemMarkedIncomplete => 'Azione contrassegnata come non completata';

  @override
  String get actionItemCompleted => 'Azione completata';

  @override
  String get deleteActionItemTitle => 'Elimina Azione';

  @override
  String get deleteActionItemMessage => 'Sei sicuro di voler eliminare questa azione?';

  @override
  String get deleteSelectedItemsTitle => 'Elimina Elementi Selezionati';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Sei sicuro di voler eliminare $count azione/i selezionata/e?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'Azione \"$description\" eliminata';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count azione/i eliminata/e';
  }

  @override
  String get failedToDeleteItem => 'Impossibile eliminare l\'azione';

  @override
  String get failedToDeleteItems => 'Impossibile eliminare gli elementi';

  @override
  String get failedToDeleteSomeItems => 'Impossibile eliminare alcuni elementi';

  @override
  String get welcomeActionItemsTitle => 'Pronto per le Azioni';

  @override
  String get welcomeActionItemsDescription =>
      'La tua AI estrarrà automaticamente attività e cose da fare dalle tue conversazioni. Appariranno qui quando create.';

  @override
  String get autoExtractionFeature => 'Estratto automaticamente dalle conversazioni';

  @override
  String get editSwipeFeature => 'Tocca per modificare, scorri per completare o eliminare';

  @override
  String itemsSelected(int count) {
    return '$count selezionati';
  }

  @override
  String get selectAll => 'Seleziona tutto';

  @override
  String get deleteSelected => 'Elimina selezionati';

  @override
  String searchMemories(int count) {
    return 'Cerca $count Ricordi';
  }

  @override
  String get memoryDeleted => 'Ricordo Eliminato.';

  @override
  String get undo => 'Annulla';

  @override
  String get noMemoriesYet => 'Nessun ricordo ancora';

  @override
  String get noAutoMemories => 'Nessun ricordo auto-estratto ancora';

  @override
  String get noManualMemories => 'Nessun ricordo manuale ancora';

  @override
  String get noMemoriesInCategories => 'Nessun ricordo in queste categorie';

  @override
  String get noMemoriesFound => 'Nessun ricordo trovato';

  @override
  String get addFirstMemory => 'Aggiungi il tuo primo ricordo';

  @override
  String get clearMemoryTitle => 'Cancella Memoria di Omi';

  @override
  String get clearMemoryMessage =>
      'Sei sicuro di voler cancellare la memoria di Omi? Questa azione non può essere annullata.';

  @override
  String get clearMemoryButton => 'Cancella Memoria';

  @override
  String get memoryClearedSuccess => 'La memoria di Omi su di te è stata cancellata';

  @override
  String get noMemoriesToDelete => 'Nessun ricordo da eliminare';

  @override
  String get createMemoryTooltip => 'Crea nuovo ricordo';

  @override
  String get createActionItemTooltip => 'Crea nuova azione';

  @override
  String get memoryManagement => 'Gestione Ricordi';

  @override
  String get filterMemories => 'Filtra Ricordi';

  @override
  String totalMemoriesCount(int count) {
    return 'Hai $count ricordi totali';
  }

  @override
  String get publicMemories => 'Ricordi pubblici';

  @override
  String get privateMemories => 'Ricordi privati';

  @override
  String get makeAllPrivate => 'Rendi Tutti i Ricordi Privati';

  @override
  String get makeAllPublic => 'Rendi Tutti i Ricordi Pubblici';

  @override
  String get deleteAllMemories => 'Elimina Tutti i Ricordi';

  @override
  String get allMemoriesPrivateResult => 'Tutti i ricordi sono ora privati';

  @override
  String get allMemoriesPublicResult => 'Tutti i ricordi sono ora pubblici';

  @override
  String get newMemory => 'Nuovo Ricordo';

  @override
  String get editMemory => 'Modifica Ricordo';

  @override
  String get memoryContentHint => 'Mi piace mangiare il gelato...';

  @override
  String get failedToSaveMemory => 'Impossibile salvare. Controlla la tua connessione.';

  @override
  String get saveMemory => 'Salva Ricordo';

  @override
  String get retry => 'Riprova';

  @override
  String get createActionItem => 'Crea Azione';

  @override
  String get editActionItem => 'Modifica Azione';

  @override
  String get actionItemDescriptionHint => 'Cosa bisogna fare?';

  @override
  String get actionItemDescriptionEmpty => 'La descrizione dell\'azione non può essere vuota.';

  @override
  String get actionItemUpdated => 'Azione aggiornata';

  @override
  String get failedToUpdateActionItem => 'Impossibile aggiornare l\'azione';

  @override
  String get actionItemCreated => 'Azione creata';

  @override
  String get failedToCreateActionItem => 'Impossibile creare l\'azione';

  @override
  String get dueDate => 'Data di Scadenza';

  @override
  String get time => 'Ora';

  @override
  String get addDueDate => 'Aggiungi data di scadenza';

  @override
  String get pressDoneToSave => 'Premi fatto per salvare';

  @override
  String get pressDoneToCreate => 'Premi fatto per creare';

  @override
  String get filterAll => 'Tutti';

  @override
  String get filterSystem => 'Su di Te';

  @override
  String get filterInteresting => 'Insight';

  @override
  String get filterManual => 'Manuale';

  @override
  String get completed => 'Completato';

  @override
  String get markComplete => 'Segna come completato';

  @override
  String get actionItemDeleted => 'Azione eliminata';

  @override
  String get failedToDeleteActionItem => 'Impossibile eliminare l\'azione';

  @override
  String get deleteActionItemConfirmTitle => 'Elimina Azione';

  @override
  String get deleteActionItemConfirmMessage => 'Sei sicuro di voler eliminare questa azione?';

  @override
  String get appLanguage => 'Lingua App';

  @override
  String get appInterfaceSectionTitle => 'INTERFACCIA APP';

  @override
  String get speechTranscriptionSectionTitle => 'VOCE E TRASCRIZIONE';

  @override
  String get languageSettingsHelperText =>
      'La lingua dell\'app modifica menu e pulsanti. La lingua vocale influisce su come vengono trascritte le tue registrazioni.';
}
