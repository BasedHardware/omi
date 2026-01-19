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
  String get copyTranscript => 'Copia trascrizione';

  @override
  String get copySummary => 'Copia Riepilogo';

  @override
  String get testPrompt => 'Prova Prompt';

  @override
  String get reprocessConversation => 'Rielabora Conversazione';

  @override
  String get deleteConversation => 'Elimina conversazione';

  @override
  String get contentCopied => 'Contenuto copiato negli appunti';

  @override
  String get failedToUpdateStarred => 'Impossibile aggiornare lo stato preferito.';

  @override
  String get conversationUrlNotShared => 'L\'URL della conversazione non può essere condiviso.';

  @override
  String get errorProcessingConversation => 'Errore durante l\'elaborazione della conversazione. Riprova più tardi.';

  @override
  String get noInternetConnection => 'Nessuna connessione Internet';

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
  String get searching => 'Ricerca in corso...';

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
  String get noConversationsYet => 'Ancora nessuna conversazione';

  @override
  String get noStarredConversations => 'Nessuna conversazione con stella';

  @override
  String get starConversationHint =>
      'Per aggiungere una conversazione ai preferiti, aprila e tocca l\'icona stella nell\'intestazione.';

  @override
  String get searchConversations => 'Cerca conversazioni...';

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
  String get messageCopied => '✨ Messaggio copiato negli appunti';

  @override
  String get cannotReportOwnMessage => 'Non puoi segnalare i tuoi stessi messaggi.';

  @override
  String get reportMessage => 'Segnala messaggio';

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
  String get searchApps => 'Cerca app...';

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
  String get visitWebsite => 'Visita il sito web';

  @override
  String get helpOrInquiries => 'Aiuto o domande?';

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
  String get identifyingOthers => 'Identificazione di Altri';

  @override
  String get paymentMethods => 'Metodi di Pagamento';

  @override
  String get conversationDisplay => 'Visualizzazione Conversazioni';

  @override
  String get dataPrivacy => 'Privacy dei Dati';

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
  String get developerSettings => 'Impostazioni sviluppatore';

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
  String get deviceId => 'ID dispositivo';

  @override
  String get firmware => 'Firmware';

  @override
  String get sdCardSync => 'Sincronizzazione scheda SD';

  @override
  String get hardwareRevision => 'Revisione Hardware';

  @override
  String get modelNumber => 'Numero modello';

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
  String get chargingIssues => 'Problemi di ricarica';

  @override
  String get disconnectDevice => 'Disconnetti dispositivo';

  @override
  String get unpairDevice => 'Disaccoppia dispositivo';

  @override
  String get unpairAndForget => 'Disaccoppia e Dimentica Dispositivo';

  @override
  String get deviceDisconnectedMessage => 'Il tuo Omi è stato disconnesso 😔';

  @override
  String get deviceUnpairedMessage =>
      'Dispositivo disaccoppiato. Vai in Impostazioni > Bluetooth e dimentica il dispositivo per completare il disaccoppiamento.';

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
  String get endpointUrl => 'URL endpoint';

  @override
  String get noApiKeys => 'Nessuna chiave API ancora';

  @override
  String get createKeyToStart => 'Crea una chiave per iniziare';

  @override
  String get createKey => 'Crea Chiave';

  @override
  String get docs => 'Documentazione';

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
  String get upgradeToUnlimited => 'Aggiorna a illimitato';

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
  String get debugLogs => 'Log di debug';

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
  String get shareLogs => 'Condividi log';

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
  String get knowledgeGraphDeleted => 'Grafico della conoscenza eliminato';

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
  String get conversationEvents => 'Eventi conversazione';

  @override
  String get newConversationCreated => 'Nuova conversazione creata';

  @override
  String get realtimeTranscript => 'Trascrizione in tempo reale';

  @override
  String get transcriptReceived => 'Trascrizione ricevuta';

  @override
  String get audioBytes => 'Byte Audio';

  @override
  String get audioDataReceived => 'Dati audio ricevuti';

  @override
  String get intervalSeconds => 'Intervallo (secondi)';

  @override
  String get daySummary => 'Riepilogo giornaliero';

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
  String get insights => 'Approfondimenti';

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
  String get primaryLanguage => 'Lingua principale';

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
  String get yesterday => 'Ieri';

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
  String get saveChanges => 'Salva modifiche';

  @override
  String get resetToDefault => 'Ripristina predefinito';

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
  String get grantPermissions => 'Concedi autorizzazioni';

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
  String get maybeLater => 'Forse Più Tardi';

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
  String get personalGrowthJourney => 'Il tuo viaggio di crescita personale con l\'IA che ascolta ogni tua parola.';

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
  String get deleteActionItemTitle => 'Elimina elemento di azione';

  @override
  String get deleteActionItemMessage => 'Sei sicuro di voler eliminare questo elemento di azione?';

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
  String get searchMemories => 'Cerca ricordi...';

  @override
  String get memoryDeleted => 'Ricordo Eliminato.';

  @override
  String get undo => 'Annulla';

  @override
  String get noMemoriesYet => '🧠 Nessun ricordo ancora';

  @override
  String get noAutoMemories => 'Nessun ricordo auto-estratto ancora';

  @override
  String get noManualMemories => 'Nessun ricordo manuale ancora';

  @override
  String get noMemoriesInCategories => 'Nessun ricordo in queste categorie';

  @override
  String get noMemoriesFound => '🔍 Nessun ricordo trovato';

  @override
  String get addFirstMemory => 'Aggiungi il tuo primo ricordo';

  @override
  String get clearMemoryTitle => 'Cancella Memoria di Omi';

  @override
  String get clearMemoryMessage =>
      'Sei sicuro di voler cancellare la memoria di Omi? Questa azione non può essere annullata.';

  @override
  String get clearMemoryButton => 'Cancella memoria';

  @override
  String get memoryClearedSuccess => 'La memoria di Omi su di te è stata cancellata';

  @override
  String get noMemoriesToDelete => 'Nessun ricordo da eliminare';

  @override
  String get createMemoryTooltip => 'Crea nuovo ricordo';

  @override
  String get createActionItemTooltip => 'Crea nuova azione';

  @override
  String get memoryManagement => 'Gestione memoria';

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
  String get deleteAllMemories => 'Elimina tutti i ricordi';

  @override
  String get allMemoriesPrivateResult => 'Tutti i ricordi sono ora privati';

  @override
  String get allMemoriesPublicResult => 'Tutti i ricordi sono ora pubblici';

  @override
  String get newMemory => '✨ Nuova memoria';

  @override
  String get editMemory => '✏️ Modifica memoria';

  @override
  String get memoryContentHint => 'Mi piace mangiare il gelato...';

  @override
  String get failedToSaveMemory => 'Impossibile salvare. Controlla la tua connessione.';

  @override
  String get saveMemory => 'Salva Ricordo';

  @override
  String get retry => 'Riprova';

  @override
  String get createActionItem => 'Crea attività';

  @override
  String get editActionItem => 'Modifica attività';

  @override
  String get actionItemDescriptionHint => 'Cosa bisogna fare?';

  @override
  String get actionItemDescriptionEmpty => 'La descrizione dell\'azione non può essere vuota.';

  @override
  String get actionItemUpdated => 'Azione aggiornata';

  @override
  String get failedToUpdateActionItem => 'Aggiornamento attività non riuscito';

  @override
  String get actionItemCreated => 'Azione creata';

  @override
  String get failedToCreateActionItem => 'Creazione attività non riuscita';

  @override
  String get dueDate => 'Data di scadenza';

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
  String get actionItemDeleted => 'Elemento di azione eliminato';

  @override
  String get failedToDeleteActionItem => 'Eliminazione attività non riuscita';

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

  @override
  String get translationNotice => 'Avviso di traduzione';

  @override
  String get translationNoticeMessage =>
      'Omi traduce le conversazioni nella tua lingua principale. Aggiornala in qualsiasi momento in Impostazioni → Profili.';

  @override
  String get pleaseCheckInternetConnection => 'Controlla la tua connessione Internet e riprova';

  @override
  String get pleaseSelectReason => 'Seleziona un motivo';

  @override
  String get tellUsMoreWhatWentWrong => 'Raccontaci di più su cosa è andato storto...';

  @override
  String get selectText => 'Seleziona testo';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Massimo $count obiettivi consentiti';
  }

  @override
  String get conversationCannotBeMerged =>
      'Questa conversazione non può essere unita (bloccata o già in fase di unione)';

  @override
  String get pleaseEnterFolderName => 'Inserisci un nome per la cartella';

  @override
  String get failedToCreateFolder => 'Impossibile creare la cartella';

  @override
  String get failedToUpdateFolder => 'Impossibile aggiornare la cartella';

  @override
  String get folderName => 'Nome cartella';

  @override
  String get descriptionOptional => 'Descrizione (facoltativo)';

  @override
  String get failedToDeleteFolder => 'Impossibile eliminare la cartella';

  @override
  String get editFolder => 'Modifica cartella';

  @override
  String get deleteFolder => 'Elimina cartella';

  @override
  String get transcriptCopiedToClipboard => 'Trascrizione copiata negli appunti';

  @override
  String get summaryCopiedToClipboard => 'Riepilogo copiato negli appunti';

  @override
  String get conversationUrlCouldNotBeShared => 'L\'URL della conversazione non può essere condiviso.';

  @override
  String get urlCopiedToClipboard => 'URL copiato negli appunti';

  @override
  String get exportTranscript => 'Esporta trascrizione';

  @override
  String get exportSummary => 'Esporta riepilogo';

  @override
  String get exportButton => 'Esporta';

  @override
  String get actionItemsCopiedToClipboard => 'Elementi d\'azione copiati negli appunti';

  @override
  String get summarize => 'Riassumi';

  @override
  String get generateSummary => 'Genera riepilogo';

  @override
  String get conversationNotFoundOrDeleted => 'Conversazione non trovata o è stata eliminata';

  @override
  String get deleteMemory => 'Elimina memoria';

  @override
  String get thisActionCannotBeUndone => 'Questa azione non può essere annullata.';

  @override
  String memoriesCount(int count) {
    return '$count memorie';
  }

  @override
  String get noMemoriesInCategory => 'Nessuna memoria in questa categoria ancora';

  @override
  String get addYourFirstMemory => 'Aggiungi il tuo primo ricordo';

  @override
  String get firmwareDisconnectUsb => 'Disconnetti USB';

  @override
  String get firmwareUsbWarning => 'La connessione USB durante gli aggiornamenti può danneggiare il dispositivo.';

  @override
  String get firmwareBatteryAbove15 => 'Batteria sopra il 15%';

  @override
  String get firmwareEnsureBattery => 'Assicurati che il tuo dispositivo abbia il 15% di batteria.';

  @override
  String get firmwareStableConnection => 'Connessione stabile';

  @override
  String get firmwareConnectWifi => 'Connettiti a WiFi o rete cellulare.';

  @override
  String failedToStartUpdate(String error) {
    return 'Impossibile avviare l\'aggiornamento: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'Prima dell\'aggiornamento, assicurati:';

  @override
  String get confirmed => 'Confermato!';

  @override
  String get release => 'Rilascia';

  @override
  String get slideToUpdate => 'Scorri per aggiornare';

  @override
  String copiedToClipboard(String title) {
    return '$title copiato negli appunti';
  }

  @override
  String get batteryLevel => 'Livello batteria';

  @override
  String get productUpdate => 'Aggiornamento prodotto';

  @override
  String get offline => 'Offline';

  @override
  String get available => 'Disponibile';

  @override
  String get unpairDeviceDialogTitle => 'Disaccoppia dispositivo';

  @override
  String get unpairDeviceDialogMessage =>
      'Questo disaccoppierà il dispositivo in modo che possa essere connesso a un altro telefono. Dovrai andare in Impostazioni > Bluetooth e dimenticare il dispositivo per completare il processo.';

  @override
  String get unpair => 'Disaccoppia';

  @override
  String get unpairAndForgetDevice => 'Disaccoppia e dimentica dispositivo';

  @override
  String get unknownDevice => 'Dispositivo sconosciuto';

  @override
  String get unknown => 'Sconosciuto';

  @override
  String get productName => 'Nome prodotto';

  @override
  String get serialNumber => 'Numero di serie';

  @override
  String get connected => 'Connesso';

  @override
  String get privacyPolicyTitle => 'Informativa sulla privacy';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label copied';
  }

  @override
  String get noApiKeysYet => 'Nessuna chiave API ancora. Creane una per integrare con la tua app.';

  @override
  String get createKeyToGetStarted => 'Create a key to get started';

  @override
  String get persona => 'Persona';

  @override
  String get configureYourAiPersona => 'Configure your AI persona';

  @override
  String get configureSttProvider => 'Configure STT provider';

  @override
  String get setWhenConversationsAutoEnd => 'Set when conversations auto-end';

  @override
  String get importDataFromOtherSources => 'Import data from other sources';

  @override
  String get debugAndDiagnostics => 'Debug e Diagnostica';

  @override
  String get autoDeletesAfter3Days => 'Eliminazione automatica dopo 3 giorni';

  @override
  String get helpsDiagnoseIssues => 'Aiuta a diagnosticare i problemi';

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
  String get realTimeTranscript => 'Trascrizione in Tempo Reale';

  @override
  String get experimental => 'Sperimentale';

  @override
  String get transcriptionDiagnostics => 'Diagnostica Trascrizione';

  @override
  String get detailedDiagnosticMessages => 'Messaggi diagnostici dettagliati';

  @override
  String get autoCreateSpeakers => 'Crea Automaticamente Relatori';

  @override
  String get autoCreateWhenNameDetected => 'Auto-create when name detected';

  @override
  String get followUpQuestions => 'Domande di Follow-up';

  @override
  String get suggestQuestionsAfterConversations => 'Suggerisci domande dopo le conversazioni';

  @override
  String get goalTracker => 'Tracker degli Obiettivi';

  @override
  String get trackPersonalGoalsOnHomepage => 'Track your personal goals on homepage';

  @override
  String get dailyReflection => 'Riflessione Giornaliera';

  @override
  String get get9PmReminderToReflect => 'Get a 9 PM reminder to reflect on your day';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'La descrizione dell\'elemento di azione non può essere vuota';

  @override
  String get saved => 'Salvato';

  @override
  String get overdue => 'In ritardo';

  @override
  String get failedToUpdateDueDate => 'Impossibile aggiornare la data di scadenza';

  @override
  String get markIncomplete => 'Segna come incompleto';

  @override
  String get editDueDate => 'Modifica data di scadenza';

  @override
  String get setDueDate => 'Imposta data di scadenza';

  @override
  String get clearDueDate => 'Cancella data di scadenza';

  @override
  String get failedToClearDueDate => 'Impossibile cancellare la data di scadenza';

  @override
  String get mondayAbbr => 'Lun';

  @override
  String get tuesdayAbbr => 'Mar';

  @override
  String get wednesdayAbbr => 'Mer';

  @override
  String get thursdayAbbr => 'Gio';

  @override
  String get fridayAbbr => 'Ven';

  @override
  String get saturdayAbbr => 'Sab';

  @override
  String get sundayAbbr => 'Dom';

  @override
  String get howDoesItWork => 'Come funziona?';

  @override
  String get sdCardSyncDescription =>
      'La sincronizzazione della scheda SD importerà i tuoi ricordi dalla scheda SD all\'app';

  @override
  String get checksForAudioFiles => 'Controlla i file audio sulla scheda SD';

  @override
  String get omiSyncsAudioFiles => 'Omi sincronizza quindi i file audio con il server';

  @override
  String get serverProcessesAudio => 'Il server elabora i file audio e crea ricordi';

  @override
  String get youreAllSet => 'Sei pronto!';

  @override
  String get welcomeToOmiDescription =>
      'Benvenuto in Omi! Il tuo compagno AI è pronto ad aiutarti con conversazioni, attività e molto altro.';

  @override
  String get startUsingOmi => 'Inizia a usare Omi';

  @override
  String get back => 'Indietro';

  @override
  String get keyboardShortcuts => 'Scorciatoie da Tastiera';

  @override
  String get toggleControlBar => 'Attiva/Disattiva barra di controllo';

  @override
  String get pressKeys => 'Premi i tasti...';

  @override
  String get cmdRequired => '⌘ richiesto';

  @override
  String get invalidKey => 'Tasto non valido';

  @override
  String get space => 'Spazio';

  @override
  String get search => 'Cerca';

  @override
  String get searchPlaceholder => 'Cerca...';

  @override
  String get untitledConversation => 'Conversazione senza titolo';

  @override
  String countRemaining(String count) {
    return '$count rimanenti';
  }

  @override
  String get addGoal => 'Aggiungi obiettivo';

  @override
  String get editGoal => 'Modifica obiettivo';

  @override
  String get icon => 'Icona';

  @override
  String get goalTitle => 'Titolo obiettivo';

  @override
  String get current => 'Attuale';

  @override
  String get target => 'Obiettivo';

  @override
  String get saveGoal => 'Salva';

  @override
  String get goals => 'Obiettivi';

  @override
  String get tapToAddGoal => 'Tocca per aggiungere un obiettivo';

  @override
  String welcomeBack(String name) {
    return 'Bentornato, $name';
  }

  @override
  String get yourConversations => 'Le tue conversazioni';

  @override
  String get reviewAndManageConversations => 'Rivedi e gestisci le tue conversazioni registrate';

  @override
  String get startCapturingConversations =>
      'Inizia a catturare conversazioni con il tuo dispositivo Omi per vederle qui.';

  @override
  String get useMobileAppToCapture => 'Usa la tua app mobile per catturare l\'audio';

  @override
  String get conversationsProcessedAutomatically => 'Le conversazioni vengono elaborate automaticamente';

  @override
  String get getInsightsInstantly => 'Ottieni approfondimenti e riassunti all\'istante';

  @override
  String get showAll => 'Mostra tutto →';

  @override
  String get noTasksForToday => 'Nessuna attività per oggi.\\nChiedi a Omi più attività o creale manualmente.';

  @override
  String get dailyScore => 'PUNTEGGIO GIORNALIERO';

  @override
  String get dailyScoreDescription => 'Un punteggio per aiutarti a concentrarti meglio sull\'esecuzione.';

  @override
  String get searchResults => 'Risultati di ricerca';

  @override
  String get actionItems => 'Elementi d\'azione';

  @override
  String get tasksToday => 'Oggi';

  @override
  String get tasksTomorrow => 'Domani';

  @override
  String get tasksNoDeadline => 'Nessuna scadenza';

  @override
  String get tasksLater => 'Più tardi';

  @override
  String get loadingTasks => 'Caricamento attività...';

  @override
  String get tasks => 'Attività';

  @override
  String get swipeTasksToIndent => 'Scorri le attività per rientrare, trascina tra le categorie';

  @override
  String get create => 'Crea';

  @override
  String get noTasksYet => 'Nessuna attività ancora';

  @override
  String get tasksFromConversationsWillAppear =>
      'Le attività dalle tue conversazioni appariranno qui.\nFai clic su Crea per aggiungerne una manualmente.';

  @override
  String get monthJan => 'Gen';

  @override
  String get monthFeb => 'Feb';

  @override
  String get monthMar => 'Mar';

  @override
  String get monthApr => 'Apr';

  @override
  String get monthMay => 'Mag';

  @override
  String get monthJun => 'Giu';

  @override
  String get monthJul => 'Lug';

  @override
  String get monthAug => 'Ago';

  @override
  String get monthSep => 'Set';

  @override
  String get monthOct => 'Ott';

  @override
  String get monthNov => 'Nov';

  @override
  String get monthDec => 'Dic';

  @override
  String get timePM => 'PM';

  @override
  String get timeAM => 'AM';

  @override
  String get actionItemUpdatedSuccessfully => 'Attività aggiornata con successo';

  @override
  String get actionItemCreatedSuccessfully => 'Attività creata con successo';

  @override
  String get actionItemDeletedSuccessfully => 'Attività eliminata con successo';

  @override
  String get deleteActionItem => 'Elimina attività';

  @override
  String get deleteActionItemConfirmation =>
      'Sei sicuro di voler eliminare questa attività? Questa azione non può essere annullata.';

  @override
  String get enterActionItemDescription => 'Inserisci la descrizione dell\'attività...';

  @override
  String get markAsCompleted => 'Segna come completata';

  @override
  String get setDueDateAndTime => 'Imposta data e ora di scadenza';

  @override
  String get reloadingApps => 'Ricaricamento app...';

  @override
  String get loadingApps => 'Caricamento app...';

  @override
  String get browseInstallCreateApps => 'Sfoglia, installa e crea app';

  @override
  String get all => 'Tutti';

  @override
  String get open => 'Apri';

  @override
  String get install => 'Installa';

  @override
  String get noAppsAvailable => 'Nessuna app disponibile';

  @override
  String get unableToLoadApps => 'Impossibile caricare le app';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'Prova a modificare i termini di ricerca o i filtri';

  @override
  String get checkBackLaterForNewApps => 'Ricontrolla più tardi per nuove app';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'Controlla la tua connessione Internet e riprova';

  @override
  String get createNewApp => 'Crea Nuova App';

  @override
  String get buildSubmitCustomOmiApp => 'Crea e invia la tua app Omi personalizzata';

  @override
  String get submittingYourApp => 'Invio della tua app in corso...';

  @override
  String get preparingFormForYou => 'Preparazione del modulo per te...';

  @override
  String get appDetails => 'Dettagli App';

  @override
  String get paymentDetails => 'Dettagli Pagamento';

  @override
  String get previewAndScreenshots => 'Anteprima e Screenshot';

  @override
  String get appCapabilities => 'Capacità dell\'App';

  @override
  String get aiPrompts => 'Prompt IA';

  @override
  String get chatPrompt => 'Prompt Chat';

  @override
  String get chatPromptPlaceholder =>
      'Sei un\'app fantastica, il tuo compito è rispondere alle domande degli utenti e farli sentire bene...';

  @override
  String get conversationPrompt => 'Prompt di conversazione';

  @override
  String get conversationPromptPlaceholder =>
      'Sei un\'app fantastica, ti verrà fornita una trascrizione e un riepilogo di una conversazione...';

  @override
  String get notificationScopes => 'Ambiti di Notifica';

  @override
  String get appPrivacyAndTerms => 'Privacy e Termini dell\'App';

  @override
  String get makeMyAppPublic => 'Rendi pubblica la mia app';

  @override
  String get submitAppTermsAgreement =>
      'Inviando questa app, accetto i Termini di Servizio e l\'Informativa sulla Privacy di Omi AI';

  @override
  String get submitApp => 'Invia App';

  @override
  String get needHelpGettingStarted => 'Hai bisogno di aiuto per iniziare?';

  @override
  String get clickHereForAppBuildingGuides => 'Clicca qui per le guide alla creazione di app e la documentazione';

  @override
  String get submitAppQuestion => 'Inviare l\'App?';

  @override
  String get submitAppPublicDescription =>
      'La tua app sarà revisionata e resa pubblica. Puoi iniziare a usarla immediatamente, anche durante la revisione!';

  @override
  String get submitAppPrivateDescription =>
      'La tua app sarà revisionata e resa disponibile per te privatamente. Puoi iniziare a usarla immediatamente, anche durante la revisione!';

  @override
  String get startEarning => 'Inizia a Guadagnare! 💰';

  @override
  String get connectStripeOrPayPal => 'Collega Stripe o PayPal per ricevere pagamenti per la tua app.';

  @override
  String get connectNow => 'Collega Ora';

  @override
  String installsCount(String count) {
    return '$count+ installazioni';
  }

  @override
  String get uninstallApp => 'Disinstalla app';

  @override
  String get subscribe => 'Abbonati';

  @override
  String get dataAccessNotice => 'Avviso di accesso ai dati';

  @override
  String get dataAccessWarning =>
      'Questa app accederà ai tuoi dati. Omi AI non è responsabile di come i tuoi dati vengono utilizzati, modificati o eliminati da questa app';

  @override
  String get installApp => 'Installa app';

  @override
  String get betaTesterNotice =>
      'Sei un beta tester per questa app. Non è ancora pubblica. Diventerà pubblica una volta approvata.';

  @override
  String get appUnderReviewOwner =>
      'La tua app è in revisione e visibile solo a te. Diventerà pubblica una volta approvata.';

  @override
  String get appRejectedNotice =>
      'La tua app è stata rifiutata. Aggiorna i dettagli dell\'app e inviala nuovamente per la revisione.';

  @override
  String get setupSteps => 'Passaggi di configurazione';

  @override
  String get setupInstructions => 'Istruzioni di configurazione';

  @override
  String get integrationInstructions => 'Istruzioni di integrazione';

  @override
  String get preview => 'Anteprima';

  @override
  String get aboutTheApp => 'Informazioni sull\'app';

  @override
  String get aboutThePersona => 'Informazioni sulla persona';

  @override
  String get chatPersonality => 'Personalità della chat';

  @override
  String get ratingsAndReviews => 'Valutazioni e recensioni';

  @override
  String get noRatings => 'nessuna valutazione';

  @override
  String ratingsCount(String count) {
    return '$count+ valutazioni';
  }

  @override
  String get errorActivatingApp => 'Errore nell\'attivazione dell\'app';

  @override
  String get integrationSetupRequired =>
      'Se questa è un\'app di integrazione, assicurati che la configurazione sia completata.';

  @override
  String get installed => 'Installato';

  @override
  String get appIdLabel => 'ID dell\'app';

  @override
  String get appNameLabel => 'Nome dell\'app';

  @override
  String get appNamePlaceholder => 'La mia fantastica app';

  @override
  String get pleaseEnterAppName => 'Inserisci il nome dell\'app';

  @override
  String get categoryLabel => 'Categoria';

  @override
  String get selectCategory => 'Seleziona categoria';

  @override
  String get descriptionLabel => 'Descrizione';

  @override
  String get appDescriptionPlaceholder =>
      'La mia fantastica app è un\'app fantastica che fa cose incredibili. È la migliore app di sempre!';

  @override
  String get pleaseProvideValidDescription => 'Fornisci una descrizione valida';

  @override
  String get appPricingLabel => 'Prezzo dell\'app';

  @override
  String get noneSelected => 'Nessuna selezionata';

  @override
  String get appIdCopiedToClipboard => 'ID dell\'app copiato negli appunti';

  @override
  String get appCategoryModalTitle => 'Categoria dell\'app';

  @override
  String get pricingFree => 'Gratuita';

  @override
  String get pricingPaid => 'A pagamento';

  @override
  String get loadingCapabilities => 'Caricamento delle funzionalità...';

  @override
  String get filterInstalled => 'Installate';

  @override
  String get filterMyApps => 'Le mie app';

  @override
  String get clearSelection => 'Cancella selezione';

  @override
  String get filterCategory => 'Categoria';

  @override
  String get rating4PlusStars => '4+ stelle';

  @override
  String get rating3PlusStars => '3+ stelle';

  @override
  String get rating2PlusStars => '2+ stelle';

  @override
  String get rating1PlusStars => '1+ stella';

  @override
  String get filterRating => 'Valutazione';

  @override
  String get filterCapabilities => 'Funzionalità';

  @override
  String get noNotificationScopesAvailable => 'Nessun ambito di notifica disponibile';

  @override
  String get popularApps => 'App popolari';

  @override
  String get pleaseProvidePrompt => 'Si prega di fornire un prompt';

  @override
  String chatWithAppName(String appName) {
    return 'Chat con $appName';
  }

  @override
  String get defaultAiAssistant => 'Assistente AI predefinito';

  @override
  String get readyToChat => '✨ Pronto per chattare!';

  @override
  String get connectionNeeded => '🌐 Connessione necessaria';

  @override
  String get startConversation => 'Inizia una conversazione e lascia che la magia inizi';

  @override
  String get checkInternetConnection => 'Controlla la tua connessione Internet';

  @override
  String get wasThisHelpful => 'È stato utile?';

  @override
  String get thankYouForFeedback => 'Grazie per il tuo feedback!';

  @override
  String get maxFilesUploadError => 'Puoi caricare solo 4 file alla volta';

  @override
  String get attachedFiles => '📎 File allegati';

  @override
  String get takePhoto => 'Scatta una foto';

  @override
  String get captureWithCamera => 'Cattura con la fotocamera';

  @override
  String get selectImages => 'Seleziona immagini';

  @override
  String get chooseFromGallery => 'Scegli dalla galleria';

  @override
  String get selectFile => 'Seleziona un file';

  @override
  String get chooseAnyFileType => 'Scegli qualsiasi tipo di file';

  @override
  String get cannotReportOwnMessages => 'Non puoi segnalare i tuoi messaggi';

  @override
  String get messageReportedSuccessfully => '✅ Messaggio segnalato con successo';

  @override
  String get confirmReportMessage => 'Sei sicuro di voler segnalare questo messaggio?';

  @override
  String get selectChatAssistant => 'Seleziona assistente chat';

  @override
  String get enableMoreApps => 'Abilita più app';

  @override
  String get chatCleared => 'Chat cancellata';

  @override
  String get clearChatTitle => 'Cancellare la chat?';

  @override
  String get confirmClearChat => 'Sei sicuro di voler cancellare la chat? Questa azione non può essere annullata.';

  @override
  String get copy => 'Copia';

  @override
  String get share => 'Condividi';

  @override
  String get report => 'Segnala';

  @override
  String get microphonePermissionRequired => 'È richiesta l\'autorizzazione del microfono per la registrazione vocale.';

  @override
  String get microphonePermissionDenied =>
      'Autorizzazione microfono negata. Concedi l\'autorizzazione in Preferenze di Sistema > Privacy e sicurezza > Microfono.';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'Verifica autorizzazione microfono fallita: $error';
  }

  @override
  String get failedToTranscribeAudio => 'Trascrizione audio fallita';

  @override
  String get transcribing => 'Trascrizione...';

  @override
  String get transcriptionFailed => 'Trascrizione fallita';

  @override
  String get discardedConversation => 'Conversazione scartata';

  @override
  String get at => 'alle';

  @override
  String get from => 'dalle';

  @override
  String get copied => 'Copiato!';

  @override
  String get copyLink => 'Copia link';

  @override
  String get hideTranscript => 'Nascondi trascrizione';

  @override
  String get viewTranscript => 'Visualizza trascrizione';

  @override
  String get conversationDetails => 'Dettagli conversazione';

  @override
  String get transcript => 'Trascrizione';

  @override
  String segmentsCount(int count) {
    return '$count segmenti';
  }

  @override
  String get noTranscriptAvailable => 'Nessuna trascrizione disponibile';

  @override
  String get noTranscriptMessage => 'Questa conversazione non ha una trascrizione.';

  @override
  String get conversationUrlCouldNotBeGenerated => 'L\'URL della conversazione non può essere generato.';

  @override
  String get failedToGenerateConversationLink => 'Generazione del link della conversazione non riuscita';

  @override
  String get failedToGenerateShareLink => 'Generazione del link di condivisione non riuscita';

  @override
  String get reloadingConversations => 'Ricaricamento conversazioni...';

  @override
  String get user => 'Utente';

  @override
  String get starred => 'Con stella';

  @override
  String get date => 'Data';

  @override
  String get noResultsFound => 'Nessun risultato trovato';

  @override
  String get tryAdjustingSearchTerms => 'Prova a modificare i termini di ricerca';

  @override
  String get starConversationsToFindQuickly => 'Aggiungi la stella alle conversazioni per trovarle rapidamente qui';

  @override
  String noConversationsOnDate(String date) {
    return 'Nessuna conversazione il $date';
  }

  @override
  String get trySelectingDifferentDate => 'Prova a selezionare una data diversa';

  @override
  String get conversations => 'Conversazioni';

  @override
  String get chat => 'Chat';

  @override
  String get actions => 'Azioni';

  @override
  String get syncAvailable => 'Sincronizzazione disponibile';

  @override
  String get referAFriend => 'Consiglia a un amico';

  @override
  String get help => 'Aiuto';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'Passa a Pro';

  @override
  String get getOmiDevice => 'Ottieni il dispositivo Omi';

  @override
  String get wearableAiCompanion => 'Compagno AI indossabile';

  @override
  String get loadingMemories => 'Caricamento ricordi...';

  @override
  String get allMemories => 'Tutti i ricordi';

  @override
  String get aboutYou => 'Su di te';

  @override
  String get manual => 'Manuale';

  @override
  String get loadingYourMemories => 'Caricamento dei tuoi ricordi...';

  @override
  String get createYourFirstMemory => 'Crea il tuo primo ricordo per iniziare';

  @override
  String get tryAdjustingFilter => 'Prova a modificare la ricerca o il filtro';

  @override
  String get whatWouldYouLikeToRemember => 'Cosa vorresti ricordare?';

  @override
  String get category => 'Categoria';

  @override
  String get public => 'Pubblico';

  @override
  String get failedToSaveCheckConnection => 'Salvataggio fallito. Controlla la tua connessione.';

  @override
  String get createMemory => 'Crea memoria';

  @override
  String get deleteMemoryConfirmation =>
      'Sei sicuro di voler eliminare questa memoria? Questa azione non può essere annullata.';

  @override
  String get makePrivate => 'Rendi privato';

  @override
  String get organizeAndControlMemories => 'Organizza e controlla i tuoi ricordi';

  @override
  String get total => 'Totale';

  @override
  String get makeAllMemoriesPrivate => 'Rendi tutti i ricordi privati';

  @override
  String get setAllMemoriesToPrivate => 'Imposta tutti i ricordi come privati';

  @override
  String get makeAllMemoriesPublic => 'Rendi tutti i ricordi pubblici';

  @override
  String get setAllMemoriesToPublic => 'Imposta tutti i ricordi come pubblici';

  @override
  String get permanentlyRemoveAllMemories => 'Rimuovi permanentemente tutti i ricordi da Omi';

  @override
  String get allMemoriesAreNowPrivate => 'Tutti i ricordi sono ora privati';

  @override
  String get allMemoriesAreNowPublic => 'Tutti i ricordi sono ora pubblici';

  @override
  String get clearOmisMemory => 'Cancella la memoria di Omi';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Sei sicuro di voler cancellare la memoria di Omi? Questa azione non può essere annullata e eliminerà permanentemente tutti i $count ricordi.';
  }

  @override
  String get omisMemoryCleared => 'La memoria di Omi su di te è stata cancellata';

  @override
  String get welcomeToOmi => 'Benvenuto in Omi';

  @override
  String get continueWithApple => 'Continua con Apple';

  @override
  String get continueWithGoogle => 'Continua con Google';

  @override
  String get byContinuingYouAgree => 'Continuando, accetti i nostri ';

  @override
  String get termsOfService => 'Termini di servizio';

  @override
  String get and => ' e ';

  @override
  String get dataAndPrivacy => 'Dati e privacy';

  @override
  String get secureAuthViaAppleId => 'Autenticazione sicura tramite Apple ID';

  @override
  String get secureAuthViaGoogleAccount => 'Autenticazione sicura tramite account Google';

  @override
  String get whatWeCollect => 'Cosa raccogliamo';

  @override
  String get dataCollectionMessage =>
      'Continuando, le tue conversazioni, registrazioni e informazioni personali verranno archiviate in modo sicuro sui nostri server per fornire informazioni basate sull\'IA e abilitare tutte le funzionalità dell\'app.';

  @override
  String get dataProtection => 'Protezione dei dati';

  @override
  String get yourDataIsProtected => 'I tuoi dati sono protetti e regolati dalla nostra ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'Seleziona la tua lingua principale';

  @override
  String get chooseYourLanguage => 'Scegli la tua lingua';

  @override
  String get selectPreferredLanguageForBestExperience =>
      'Seleziona la tua lingua preferita per la migliore esperienza Omi';

  @override
  String get searchLanguages => 'Cerca lingue...';

  @override
  String get selectALanguage => 'Seleziona una lingua';

  @override
  String get tryDifferentSearchTerm => 'Prova un termine di ricerca diverso';

  @override
  String get pleaseEnterYourName => 'Inserisci il tuo nome';

  @override
  String get nameMustBeAtLeast2Characters => 'Il nome deve contenere almeno 2 caratteri';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'Dicci come vorresti essere chiamato. Questo aiuta a personalizzare la tua esperienza Omi.';

  @override
  String charactersCount(int count) {
    return '$count caratteri';
  }

  @override
  String get enableFeaturesForBestExperience =>
      'Abilita le funzionalità per la migliore esperienza Omi sul tuo dispositivo.';

  @override
  String get microphoneAccess => 'Accesso al microfono';

  @override
  String get recordAudioConversations => 'Registra conversazioni audio';

  @override
  String get microphoneAccessDescription =>
      'Omi ha bisogno dell\'accesso al microfono per registrare le tue conversazioni e fornire trascrizioni.';

  @override
  String get screenRecording => 'Registrazione schermo';

  @override
  String get captureSystemAudioFromMeetings => 'Cattura l\'audio di sistema dalle riunioni';

  @override
  String get screenRecordingDescription =>
      'Omi ha bisogno dell\'autorizzazione per la registrazione dello schermo per catturare l\'audio di sistema dalle tue riunioni basate sul browser.';

  @override
  String get accessibility => 'Accessibilità';

  @override
  String get detectBrowserBasedMeetings => 'Rileva riunioni basate sul browser';

  @override
  String get accessibilityDescription =>
      'Omi ha bisogno dell\'autorizzazione di accessibilità per rilevare quando partecipi a riunioni Zoom, Meet o Teams nel tuo browser.';

  @override
  String get pleaseWait => 'Attendere prego...';

  @override
  String get joinTheCommunity => 'Unisciti alla comunità!';

  @override
  String get loadingProfile => 'Caricamento del profilo...';

  @override
  String get profileSettings => 'Impostazioni del profilo';

  @override
  String get noEmailSet => 'Nessuna email impostata';

  @override
  String get userIdCopiedToClipboard => 'ID utente copiato';

  @override
  String get yourInformation => 'Le Tue Informazioni';

  @override
  String get setYourName => 'Imposta il tuo nome';

  @override
  String get changeYourName => 'Cambia il tuo nome';

  @override
  String get manageYourOmiPersona => 'Gestisci la tua persona Omi';

  @override
  String get voiceAndPeople => 'Voce e Persone';

  @override
  String get teachOmiYourVoice => 'Insegna a Omi la tua voce';

  @override
  String get tellOmiWhoSaidIt => 'Dì a Omi chi l\'ha detto 🗣️';

  @override
  String get payment => 'Pagamento';

  @override
  String get addOrChangeYourPaymentMethod => 'Aggiungi o modifica metodo di pagamento';

  @override
  String get preferences => 'Preferenze';

  @override
  String get helpImproveOmiBySharing => 'Aiuta a migliorare Omi condividendo dati analitici anonimi';

  @override
  String get deleteAccount => 'Elimina Account';

  @override
  String get deleteYourAccountAndAllData => 'Elimina account e tutti i dati';

  @override
  String get clearLogs => 'Cancella log';

  @override
  String get debugLogsCleared => 'Log di debug cancellati';

  @override
  String get exportConversations => 'Esporta conversazioni';

  @override
  String get exportAllConversationsToJson => 'Esporta tutte le tue conversazioni in un file JSON.';

  @override
  String get conversationsExportStarted =>
      'Esportazione conversazioni avviata. Questo potrebbe richiedere alcuni secondi, attendere prego.';

  @override
  String get mcpDescription =>
      'Per connettere Omi ad altre applicazioni per leggere, cercare e gestire i tuoi ricordi e conversazioni. Crea una chiave per iniziare.';

  @override
  String get apiKeys => 'Chiavi API';

  @override
  String errorLabel(String error) {
    return 'Errore: $error';
  }

  @override
  String get noApiKeysFound => 'Nessuna chiave API trovata. Creane una per iniziare.';

  @override
  String get advancedSettings => 'Impostazioni avanzate';

  @override
  String get triggersWhenNewConversationCreated => 'Si attiva quando viene creata una nuova conversazione.';

  @override
  String get triggersWhenNewTranscriptReceived => 'Si attiva quando viene ricevuta una nuova trascrizione.';

  @override
  String get realtimeAudioBytes => 'Byte audio in tempo reale';

  @override
  String get triggersWhenAudioBytesReceived => 'Si attiva quando vengono ricevuti byte audio.';

  @override
  String get everyXSeconds => 'Ogni x secondi';

  @override
  String get triggersWhenDaySummaryGenerated => 'Si attiva quando viene generato il riepilogo giornaliero.';

  @override
  String get tryLatestExperimentalFeatures => 'Prova le ultime funzionalità sperimentali dal team Omi.';

  @override
  String get transcriptionServiceDiagnosticStatus => 'Stato diagnostico del servizio di trascrizione';

  @override
  String get enableDetailedDiagnosticMessages =>
      'Abilita messaggi diagnostici dettagliati dal servizio di trascrizione';

  @override
  String get autoCreateAndTagNewSpeakers => 'Crea e etichetta automaticamente nuovi parlanti';

  @override
  String get automaticallyCreateNewPerson =>
      'Crea automaticamente una nuova persona quando viene rilevato un nome nella trascrizione.';

  @override
  String get pilotFeatures => 'Funzionalità pilota';

  @override
  String get pilotFeaturesDescription => 'Queste funzionalità sono test e non è garantito il supporto.';

  @override
  String get suggestFollowUpQuestion => 'Suggerisci domanda di follow-up';

  @override
  String get saveSettings => 'Salva Impostazioni';

  @override
  String get syncingDeveloperSettings => 'Sincronizzazione impostazioni sviluppatore...';

  @override
  String get summary => 'Riepilogo';

  @override
  String get auto => 'Automatico';

  @override
  String get noSummaryForApp =>
      'Nessun riepilogo disponibile per questa app. Prova un\'altra app per risultati migliori.';

  @override
  String get tryAnotherApp => 'Prova un\'altra app';

  @override
  String generatedBy(String appName) {
    return 'Generato da $appName';
  }

  @override
  String get overview => 'Panoramica';

  @override
  String get otherAppResults => 'Risultati di altre app';

  @override
  String get unknownApp => 'App sconosciuta';

  @override
  String get noSummaryAvailable => 'Nessun riepilogo disponibile';

  @override
  String get conversationNoSummaryYet => 'Questa conversazione non ha ancora un riepilogo.';

  @override
  String get chooseSummarizationApp => 'Scegli app di riepilogo';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName impostata come app di riepilogo predefinita';
  }

  @override
  String get letOmiChooseAutomatically => 'Lascia che Omi scelga automaticamente l\'app migliore';

  @override
  String get deleteConversationConfirmation =>
      'Sei sicuro di voler eliminare questa conversazione? Questa azione non può essere annullata.';

  @override
  String get conversationDeleted => 'Conversazione eliminata';

  @override
  String get generatingLink => 'Generazione link...';

  @override
  String get editConversation => 'Modifica conversazione';

  @override
  String get conversationLinkCopiedToClipboard => 'Link della conversazione copiato negli appunti';

  @override
  String get conversationTranscriptCopiedToClipboard => 'Trascrizione della conversazione copiata negli appunti';

  @override
  String get editConversationDialogTitle => 'Modifica conversazione';

  @override
  String get changeTheConversationTitle => 'Cambia il titolo della conversazione';

  @override
  String get conversationTitle => 'Titolo della conversazione';

  @override
  String get enterConversationTitle => 'Inserisci il titolo della conversazione...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'Titolo della conversazione aggiornato con successo';

  @override
  String get failedToUpdateConversationTitle => 'Aggiornamento del titolo della conversazione non riuscito';

  @override
  String get errorUpdatingConversationTitle => 'Errore nell\'aggiornamento del titolo della conversazione';

  @override
  String get settingUp => 'Configurazione...';

  @override
  String get startYourFirstRecording => 'Inizia la tua prima registrazione';

  @override
  String get preparingSystemAudioCapture => 'Preparazione della cattura audio di sistema';

  @override
  String get clickTheButtonToCaptureAudio =>
      'Fai clic sul pulsante per catturare audio per trascrizioni dal vivo, informazioni AI e salvataggio automatico.';

  @override
  String get reconnecting => 'Riconnessione...';

  @override
  String get recordingPaused => 'Registrazione in pausa';

  @override
  String get recordingActive => 'Registrazione attiva';

  @override
  String get startRecording => 'Avvia registrazione';

  @override
  String resumingInCountdown(String countdown) {
    return 'Ripresa tra ${countdown}s...';
  }

  @override
  String get tapPlayToResume => 'Tocca riproduci per riprendere';

  @override
  String get listeningForAudio => 'Ascolto audio...';

  @override
  String get preparingAudioCapture => 'Preparazione cattura audio';

  @override
  String get clickToBeginRecording => 'Fai clic per iniziare la registrazione';

  @override
  String get translated => 'tradotto';

  @override
  String get liveTranscript => 'Trascrizione dal vivo';

  @override
  String segmentsSingular(String count) {
    return '$count segmento';
  }

  @override
  String segmentsPlural(String count) {
    return '$count segmenti';
  }

  @override
  String get startRecordingToSeeTranscript => 'Avvia la registrazione per vedere la trascrizione dal vivo';

  @override
  String get paused => 'In pausa';

  @override
  String get initializing => 'Inizializzazione...';

  @override
  String get recording => 'Registrazione';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'Microfono cambiato. Ripresa tra ${countdown}s';
  }

  @override
  String get clickPlayToResumeOrStop => 'Fai clic su riproduci per riprendere o ferma per terminare';

  @override
  String get settingUpSystemAudioCapture => 'Configurazione della cattura audio di sistema';

  @override
  String get capturingAudioAndGeneratingTranscript => 'Cattura audio e generazione trascrizione';

  @override
  String get clickToBeginRecordingSystemAudio => 'Fai clic per iniziare la registrazione audio di sistema';

  @override
  String get you => 'Tu';

  @override
  String speakerWithId(String speakerId) {
    return 'Relatore $speakerId';
  }

  @override
  String get translatedByOmi => 'tradotto da omi';

  @override
  String get backToConversations => 'Torna alle conversazioni';

  @override
  String get systemAudio => 'Sistema';

  @override
  String get mic => 'Microfono';

  @override
  String audioInputSetTo(String deviceName) {
    return 'Ingresso audio impostato su $deviceName';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'Errore durante il cambio del dispositivo audio: $error';
  }

  @override
  String get selectAudioInput => 'Seleziona ingresso audio';

  @override
  String get loadingDevices => 'Caricamento dispositivi...';

  @override
  String get settingsHeader => 'IMPOSTAZIONI';

  @override
  String get plansAndBilling => 'Piani e Fatturazione';

  @override
  String get calendarIntegration => 'Integrazione Calendario';

  @override
  String get dailySummary => 'Riepilogo Giornaliero';

  @override
  String get developer => 'Sviluppatore';

  @override
  String get about => 'Informazioni';

  @override
  String get selectTime => 'Seleziona Ora';

  @override
  String get accountGroup => 'Account';

  @override
  String get signOutQuestion => 'Disconnetti?';

  @override
  String get signOutConfirmation => 'Sei sicuro di volerti disconnettere?';

  @override
  String get customVocabularyHeader => 'VOCABOLARIO PERSONALIZZATO';

  @override
  String get addWordsDescription => 'Aggiungi parole che Omi dovrebbe riconoscere durante la trascrizione.';

  @override
  String get enterWordsHint => 'Inserisci parole (separate da virgole)';

  @override
  String get dailySummaryHeader => 'RIEPILOGO GIORNALIERO';

  @override
  String get dailySummaryTitle => 'Riepilogo Giornaliero';

  @override
  String get dailySummaryDescription => 'Ricevi un riepilogo personalizzato delle tue conversazioni';

  @override
  String get deliveryTime => 'Ora di Consegna';

  @override
  String get deliveryTimeDescription => 'Quando ricevere il riepilogo giornaliero';

  @override
  String get subscription => 'Abbonamento';

  @override
  String get viewPlansAndUsage => 'Visualizza Piani e Utilizzo';

  @override
  String get viewPlansDescription => 'Gestisci il tuo abbonamento e visualizza le statistiche di utilizzo';

  @override
  String get addOrChangePaymentMethod => 'Aggiungi o modifica il tuo metodo di pagamento';

  @override
  String get displayOptions => 'Opzioni di Visualizzazione';

  @override
  String get showMeetingsInMenuBar => 'Mostra Riunioni nella Barra dei Menu';

  @override
  String get displayUpcomingMeetingsDescription => 'Mostra le riunioni imminenti nella barra dei menu';

  @override
  String get showEventsWithoutParticipants => 'Mostra Eventi Senza Partecipanti';

  @override
  String get includePersonalEventsDescription => 'Includi eventi personali senza partecipanti';

  @override
  String get upcomingMeetings => 'RIUNIONI IMMINENTI';

  @override
  String get checkingNext7Days => 'Controllo dei prossimi 7 giorni';

  @override
  String get shortcuts => 'Scorciatoie';

  @override
  String get shortcutChangeInstruction => 'Fai clic su una scorciatoia per modificarla. Premi Escape per annullare.';

  @override
  String get configurePersonaDescription => 'Configura la tua persona IA';

  @override
  String get configureSTTProvider => 'Configura provider STT';

  @override
  String get setConversationEndDescription => 'Imposta quando le conversazioni terminano automaticamente';

  @override
  String get importDataDescription => 'Importa dati da altre fonti';

  @override
  String get exportConversationsDescription => 'Esporta conversazioni in JSON';

  @override
  String get exportingConversations => 'Esportazione conversazioni...';

  @override
  String get clearNodesDescription => 'Cancella tutti i nodi e le connessioni';

  @override
  String get deleteKnowledgeGraphQuestion => 'Eliminare Grafico della Conoscenza?';

  @override
  String get deleteKnowledgeGraphWarning =>
      'Questo eliminerà tutti i dati derivati del grafico della conoscenza. I tuoi ricordi originali rimangono al sicuro.';

  @override
  String get connectOmiWithAI => 'Collega Omi con assistenti IA';

  @override
  String get noAPIKeys => 'Nessuna chiave API. Creane una per iniziare.';

  @override
  String get autoCreateWhenDetected => 'Crea automaticamente quando viene rilevato il nome';

  @override
  String get trackPersonalGoals => 'Tieni traccia degli obiettivi personali sulla homepage';

  @override
  String get dailyReflectionDescription => 'Promemoria alle 21:00 per riflettere sulla tua giornata';

  @override
  String get endpointURL => 'URL dell\'Endpoint';

  @override
  String get links => 'Link';

  @override
  String get discordMemberCount => 'Oltre 8000 membri su Discord';

  @override
  String get userInformation => 'Informazioni Utente';

  @override
  String get capabilities => 'Capacità';

  @override
  String get previewScreenshots => 'Anteprima schermate';

  @override
  String get holdOnPreparingForm => 'Attendi, stiamo preparando il modulo per te';

  @override
  String get bySubmittingYouAgreeToOmi => 'Inviando, accetti i ';

  @override
  String get termsAndPrivacyPolicy => 'Termini e Informativa sulla Privacy';

  @override
  String get helpsDiagnoseIssuesAutoDeletes =>
      'Aiuta a diagnosticare i problemi. Eliminato automaticamente dopo 3 giorni.';

  @override
  String get manageYourApp => 'Gestisci la tua app';

  @override
  String get updatingYourApp => 'Aggiornamento della tua app';

  @override
  String get fetchingYourAppDetails => 'Recupero dei dettagli della tua app';

  @override
  String get updateAppQuestion => 'Aggiornare l\'app?';

  @override
  String get updateAppConfirmation =>
      'Sei sicuro di voler aggiornare la tua app? Le modifiche saranno visibili dopo la revisione del nostro team.';

  @override
  String get updateApp => 'Aggiorna app';

  @override
  String get createAndSubmitNewApp => 'Crea e invia una nuova app';

  @override
  String appsCount(String count) {
    return 'App ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'App private ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'App pubbliche ($count)';
  }

  @override
  String get newVersionAvailable => 'Nuova versione disponibile  🎉';

  @override
  String get no => 'No';

  @override
  String get subscriptionCancelledSuccessfully =>
      'Abbonamento annullato con successo. Rimarrà attivo fino alla fine del periodo di fatturazione corrente.';

  @override
  String get failedToCancelSubscription => 'Impossibile annullare l\'abbonamento. Riprova.';

  @override
  String get invalidPaymentUrl => 'URL di pagamento non valido';

  @override
  String get permissionsAndTriggers => 'Permessi e trigger';

  @override
  String get chatFeatures => 'Funzioni chat';

  @override
  String get uninstall => 'Disinstalla';

  @override
  String get installs => 'INSTALLAZIONI';

  @override
  String get priceLabel => 'PREZZO';

  @override
  String get updatedLabel => 'AGGIORNATO';

  @override
  String get createdLabel => 'CREATO';

  @override
  String get featuredLabel => 'IN EVIDENZA';

  @override
  String get cancelSubscriptionQuestion => 'Annullare l\'abbonamento?';

  @override
  String get cancelSubscriptionConfirmation =>
      'Sei sicuro di voler annullare l\'abbonamento? Continuerai ad avere accesso fino alla fine del periodo di fatturazione corrente.';

  @override
  String get cancelSubscriptionButton => 'Annulla abbonamento';

  @override
  String get cancelling => 'Annullamento...';

  @override
  String get betaTesterMessage =>
      'Sei un beta tester per questa app. Non è ancora pubblica. Sarà pubblica dopo l\'approvazione.';

  @override
  String get appUnderReviewMessage =>
      'La tua app è in revisione e visibile solo a te. Sarà pubblica dopo l\'approvazione.';

  @override
  String get appRejectedMessage =>
      'La tua app è stata rifiutata. Aggiorna i dettagli e invia nuovamente per la revisione.';

  @override
  String get invalidIntegrationUrl => 'URL di integrazione non valido';

  @override
  String get tapToComplete => 'Tocca per completare';

  @override
  String get invalidSetupInstructionsUrl => 'URL delle istruzioni di configurazione non valido';

  @override
  String get pushToTalk => 'Premi per parlare';

  @override
  String get summaryPrompt => 'Prompt di riepilogo';

  @override
  String get pleaseSelectARating => 'Seleziona una valutazione';

  @override
  String get reviewAddedSuccessfully => 'Recensione aggiunta con successo 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'Recensione aggiornata con successo 🚀';

  @override
  String get failedToSubmitReview => 'Invio recensione fallito. Riprova.';

  @override
  String get addYourReview => 'Aggiungi la tua recensione';

  @override
  String get editYourReview => 'Modifica la tua recensione';

  @override
  String get writeAReviewOptional => 'Scrivi una recensione (opzionale)';

  @override
  String get submitReview => 'Invia recensione';

  @override
  String get updateReview => 'Aggiorna recensione';

  @override
  String get yourReview => 'La tua recensione';

  @override
  String get anonymousUser => 'Utente anonimo';

  @override
  String get issueActivatingApp => 'Si è verificato un problema nell\'attivazione di questa app. Riprova.';

  @override
  String get dataAccessNoticeDescription =>
      'This app will access your data. Omi AI is not responsible for how your data is used, modified, or deleted by this app';

  @override
  String get copyUrl => 'Copia URL';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => 'Lun';

  @override
  String get weekdayTue => 'Mar';

  @override
  String get weekdayWed => 'Mer';

  @override
  String get weekdayThu => 'Gio';

  @override
  String get weekdayFri => 'Ven';

  @override
  String get weekdaySat => 'Sab';

  @override
  String get weekdaySun => 'Dom';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return 'Integrazione $serviceName in arrivo';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'Già esportato in $platform';
  }

  @override
  String get anotherPlatform => 'un\'altra piattaforma';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'Per favore autenticati con $serviceName in Impostazioni > Integrazioni attività';
  }

  @override
  String addingToService(String serviceName) {
    return 'Aggiunta a $serviceName...';
  }

  @override
  String addedToService(String serviceName) {
    return 'Aggiunto a $serviceName';
  }

  @override
  String failedToAddToService(String serviceName) {
    return 'Impossibile aggiungere a $serviceName';
  }

  @override
  String get permissionDeniedForAppleReminders => 'Permesso negato per Apple Reminders';

  @override
  String failedToCreateApiKey(String error) {
    return 'Impossibile creare la chiave API del provider: $error';
  }

  @override
  String get createAKey => 'Crea una chiave';

  @override
  String get apiKeyRevokedSuccessfully => 'Chiave API revocata con successo';

  @override
  String failedToRevokeApiKey(String error) {
    return 'Impossibile revocare la chiave API: $error';
  }

  @override
  String get omiApiKeys => 'Chiavi API Omi';

  @override
  String get apiKeysDescription =>
      'Le chiavi API vengono utilizzate per l\'autenticazione quando la tua app comunica con il server OMI. Consentono alla tua applicazione di creare ricordi e accedere ad altri servizi OMI in modo sicuro.';

  @override
  String get aboutOmiApiKeys => 'Informazioni sulle chiavi API Omi';

  @override
  String get yourNewKey => 'La tua nuova chiave:';

  @override
  String get copyToClipboard => 'Copia negli appunti';

  @override
  String get pleaseCopyKeyNow => 'Per favore copiala ora e annotala in un posto sicuro. ';

  @override
  String get willNotSeeAgain => 'Non potrai vederla di nuovo.';

  @override
  String get revokeKey => 'Revoca chiave';

  @override
  String get revokeApiKeyQuestion => 'Revocare la chiave API?';

  @override
  String get revokeApiKeyWarning =>
      'Questa azione non può essere annullata. Le applicazioni che utilizzano questa chiave non potranno più accedere all\'API.';

  @override
  String get revoke => 'Revoca';

  @override
  String get whatWouldYouLikeToCreate => 'Cosa vorresti creare?';

  @override
  String get createAnApp => 'Crea un\'app';

  @override
  String get createAndShareYourApp => 'Crea e condividi la tua app';

  @override
  String get createMyClone => 'Crea il mio clone';

  @override
  String get createYourDigitalClone => 'Crea il tuo clone digitale';

  @override
  String get itemApp => 'App';

  @override
  String get itemPersona => 'Persona';

  @override
  String keepItemPublic(String item) {
    return 'Mantieni $item pubblico';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return 'Rendere $item pubblico?';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return 'Rendere $item privato?';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'Se rendi $item pubblico, può essere usato da tutti';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'Se rendi $item privato ora, smetterà di funzionare per tutti e sarà visibile solo a te';
  }

  @override
  String get manageApp => 'Gestisci app';

  @override
  String get updatePersonaDetails => 'Aggiorna dettagli persona';

  @override
  String deleteItemTitle(String item) {
    return 'Elimina $item';
  }

  @override
  String deleteItemQuestion(String item) {
    return 'Eliminare $item?';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'Sei sicuro di voler eliminare questo $item? Questa azione non può essere annullata.';
  }

  @override
  String get revokeKeyQuestion => 'Revocare la chiave?';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'Sei sicuro di voler revocare la chiave \"$keyName\"? Questa azione non può essere annullata.';
  }

  @override
  String get createNewKey => 'Crea nuova chiave';

  @override
  String get keyNameHint => 'es. Claude Desktop';

  @override
  String get pleaseEnterAName => 'Inserisci un nome.';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'Impossibile creare la chiave: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'Impossibile creare la chiave. Riprova.';

  @override
  String get keyCreated => 'Chiave creata';

  @override
  String get keyCreatedMessage => 'La tua nuova chiave è stata creata. Copiala ora. Non potrai vederla di nuovo.';

  @override
  String get keyWord => 'Chiave';

  @override
  String get externalAppAccess => 'Accesso app esterne';

  @override
  String get externalAppAccessDescription =>
      'Le seguenti app installate hanno integrazioni esterne e possono accedere ai tuoi dati, come conversazioni e ricordi.';

  @override
  String get noExternalAppsHaveAccess => 'Nessuna app esterna ha accesso ai tuoi dati.';

  @override
  String get maximumSecurityE2ee => 'Sicurezza massima (E2EE)';

  @override
  String get e2eeDescription =>
      'La crittografia end-to-end è lo standard d\'oro per la privacy. Quando abilitata, i tuoi dati vengono crittografati sul tuo dispositivo prima di essere inviati ai nostri server. Ciò significa che nessuno, nemmeno Omi, può accedere ai tuoi contenuti.';

  @override
  String get importantTradeoffs => 'Compromessi importanti:';

  @override
  String get e2eeTradeoff1 =>
      '• Alcune funzionalità come le integrazioni di app esterne potrebbero essere disabilitate.';

  @override
  String get e2eeTradeoff2 => '• Se perdi la password, i tuoi dati non possono essere recuperati.';

  @override
  String get featureComingSoon => 'Questa funzionalità sarà disponibile presto!';

  @override
  String get migrationInProgressMessage =>
      'Migrazione in corso. Non puoi cambiare il livello di protezione finché non è completata.';

  @override
  String get migrationFailed => 'Migrazione fallita';

  @override
  String migratingFromTo(String source, String target) {
    return 'Migrazione da $source a $target';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total oggetti';
  }

  @override
  String get secureEncryption => 'Crittografia sicura';

  @override
  String get secureEncryptionDescription =>
      'I tuoi dati sono crittografati con una chiave unica per te sui nostri server, ospitati su Google Cloud. Ciò significa che i tuoi contenuti grezzi sono inaccessibili a chiunque, incluso il personale di Omi o Google, direttamente dal database.';

  @override
  String get endToEndEncryption => 'Crittografia end-to-end';

  @override
  String get e2eeCardDescription =>
      'Abilita per la massima sicurezza dove solo tu puoi accedere ai tuoi dati. Tocca per saperne di più.';

  @override
  String get dataAlwaysEncrypted =>
      'Indipendentemente dal livello, i tuoi dati sono sempre crittografati a riposo e in transito.';

  @override
  String get readOnlyScope => 'Solo lettura';

  @override
  String get fullAccessScope => 'Accesso completo';

  @override
  String get readScope => 'Lettura';

  @override
  String get writeScope => 'Scrittura';

  @override
  String get apiKeyCreated => 'Chiave API creata!';

  @override
  String get saveKeyWarning => 'Salva questa chiave ora! Non potrai vederla di nuovo.';

  @override
  String get yourApiKey => 'LA TUA CHIAVE API';

  @override
  String get tapToCopy => 'Tocca per copiare';

  @override
  String get copyKey => 'Copia chiave';

  @override
  String get createApiKey => 'Crea chiave API';

  @override
  String get accessDataProgrammatically => 'Accedi ai tuoi dati in modo programmatico';

  @override
  String get keyNameLabel => 'NOME CHIAVE';

  @override
  String get keyNamePlaceholder => 'es., La mia integrazione';

  @override
  String get permissionsLabel => 'PERMESSI';

  @override
  String get permissionsInfoNote =>
      'R = Lettura, W = Scrittura. Solo lettura di default se non viene selezionato nulla.';

  @override
  String get developerApi => 'API sviluppatore';

  @override
  String get createAKeyToGetStarted => 'Crea una chiave per iniziare';

  @override
  String errorWithMessage(String error) {
    return 'Errore: $error';
  }

  @override
  String get omiTraining => 'Formazione Omi';

  @override
  String get trainingDataProgram => 'Programma dati di formazione';

  @override
  String get getOmiUnlimitedFree =>
      'Ottieni Omi Unlimited gratis contribuendo con i tuoi dati per addestrare modelli AI.';

  @override
  String get trainingDataBullets =>
      '• I tuoi dati aiutano a migliorare i modelli AI\n• Vengono condivisi solo dati non sensibili\n• Processo completamente trasparente';

  @override
  String get learnMoreAtOmiTraining => 'Scopri di più su omi.me/training';

  @override
  String get agreeToContributeData =>
      'Comprendo e accetto di contribuire con i miei dati per l\'addestramento dell\'IA';

  @override
  String get submitRequest => 'Invia richiesta';

  @override
  String get thankYouRequestUnderReview =>
      'Grazie! La tua richiesta è in revisione. Ti avviseremo una volta approvata.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'Il tuo piano rimarrà attivo fino al $date. Dopo, perderai l\'accesso alle funzionalità illimitate. Sei sicuro?';
  }

  @override
  String get confirmCancellation => 'Conferma annullamento';

  @override
  String get keepMyPlan => 'Mantieni il mio piano';

  @override
  String get subscriptionSetToCancel => 'Il tuo abbonamento è impostato per essere annullato alla fine del periodo.';

  @override
  String get switchedToOnDevice => 'Passato alla trascrizione sul dispositivo';

  @override
  String get couldNotSwitchToFreePlan => 'Impossibile passare al piano gratuito. Riprova.';

  @override
  String get couldNotLoadPlans => 'Impossibile caricare i piani disponibili. Riprova.';

  @override
  String get selectedPlanNotAvailable => 'Il piano selezionato non è disponibile. Riprova.';

  @override
  String get upgradeToAnnualPlan => 'Passa al piano annuale';

  @override
  String get importantBillingInfo => 'Informazioni di fatturazione importanti:';

  @override
  String get monthlyPlanContinues =>
      'Il tuo attuale piano mensile continuerà fino alla fine del periodo di fatturazione';

  @override
  String get paymentMethodCharged =>
      'Il tuo metodo di pagamento esistente verrà addebitato automaticamente al termine del piano mensile';

  @override
  String get annualSubscriptionStarts =>
      'Il tuo abbonamento annuale di 12 mesi inizierà automaticamente dopo l\'addebito';

  @override
  String get thirteenMonthsCoverage => 'Avrai 13 mesi di copertura totale (mese corrente + 12 mesi annuali)';

  @override
  String get confirmUpgrade => 'Conferma aggiornamento';

  @override
  String get confirmPlanChange => 'Conferma cambio piano';

  @override
  String get confirmAndProceed => 'Conferma e procedi';

  @override
  String get upgradeScheduled => 'Aggiornamento programmato';

  @override
  String get changePlan => 'Cambia piano';

  @override
  String get upgradeAlreadyScheduled => 'Il tuo aggiornamento al piano annuale è già programmato';

  @override
  String get youAreOnUnlimitedPlan => 'Sei sul piano Illimitato.';

  @override
  String get yourOmiUnleashed => 'Il tuo Omi, liberato. Passa a illimitato per possibilità infinite.';

  @override
  String planEndedOn(String date) {
    return 'Il tuo piano è terminato il $date.\\nRiabbonati ora - ti verrà addebitato immediatamente per un nuovo periodo di fatturazione.';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'Il tuo piano è impostato per essere annullato il $date.\\nRiabbonati ora per mantenere i tuoi benefici - nessun addebito fino al $date.';
  }

  @override
  String get annualPlanStartsAutomatically =>
      'Il tuo piano annuale inizierà automaticamente al termine del piano mensile.';

  @override
  String planRenewsOn(String date) {
    return 'Il tuo piano si rinnova il $date.';
  }

  @override
  String get unlimitedConversations => 'Conversazioni illimitate';

  @override
  String get askOmiAnything => 'Chiedi a Omi qualsiasi cosa sulla tua vita';

  @override
  String get unlockOmiInfiniteMemory => 'Sblocca la memoria infinita di Omi';

  @override
  String get youreOnAnnualPlan => 'Sei sul piano annuale';

  @override
  String get alreadyBestValuePlan =>
      'Hai già il piano dal miglior rapporto qualità-prezzo. Non sono necessarie modifiche.';

  @override
  String get unableToLoadPlans => 'Impossibile caricare i piani';

  @override
  String get checkConnectionTryAgain => 'Controlla la connessione e riprova';

  @override
  String get useFreePlan => 'Usa piano gratuito';

  @override
  String get continueText => 'Continua';

  @override
  String get resubscribe => 'Riabbonati';

  @override
  String get couldNotOpenPaymentSettings => 'Impossibile aprire le impostazioni di pagamento. Riprova.';

  @override
  String get managePaymentMethod => 'Gestisci metodo di pagamento';

  @override
  String get cancelSubscription => 'Annulla abbonamento';

  @override
  String endsOnDate(String date) {
    return 'Termina il $date';
  }

  @override
  String get active => 'Attivo';

  @override
  String get freePlan => 'Piano gratuito';

  @override
  String get configure => 'Configura';

  @override
  String get privacyInformation => 'Informazioni sulla privacy';

  @override
  String get yourPrivacyMattersToUs => 'La tua privacy è importante per noi';

  @override
  String get privacyIntroText =>
      'In Omi, prendiamo molto sul serio la tua privacy. Vogliamo essere trasparenti sui dati che raccogliamo e come li utilizziamo per migliorare il prodotto. Ecco cosa devi sapere:';

  @override
  String get whatWeTrack => 'Cosa monitoriamo';

  @override
  String get anonymityAndPrivacy => 'Anonimato e privacy';

  @override
  String get optInAndOptOutOptions => 'Opzioni di adesione e rinuncia';

  @override
  String get ourCommitment => 'Il nostro impegno';

  @override
  String get commitmentText =>
      'Ci impegniamo a utilizzare i dati raccolti solo per rendere Omi un prodotto migliore per te. La tua privacy e la tua fiducia sono fondamentali per noi.';

  @override
  String get thankYouText =>
      'Grazie per essere un utente prezioso di Omi. Se hai domande o dubbi, non esitare a contattarci a team@basedhardware.com.';

  @override
  String get wifiSyncSettings => 'Impostazioni sincronizzazione WiFi';

  @override
  String get enterHotspotCredentials => 'Inserisci le credenziali hotspot del tuo telefono';

  @override
  String get wifiSyncUsesHotspot =>
      'La sincronizzazione WiFi usa il telefono come hotspot. Trova nome e password in Impostazioni > Hotspot personale.';

  @override
  String get hotspotNameSsid => 'Nome hotspot (SSID)';

  @override
  String get exampleIphoneHotspot => 'es. Hotspot iPhone';

  @override
  String get password => 'Password';

  @override
  String get enterHotspotPassword => 'Inserisci la password dell\'hotspot';

  @override
  String get saveCredentials => 'Salva credenziali';

  @override
  String get clearCredentials => 'Cancella credenziali';

  @override
  String get pleaseEnterHotspotName => 'Inserisci un nome hotspot';

  @override
  String get wifiCredentialsSaved => 'Credenziali WiFi salvate';

  @override
  String get wifiCredentialsCleared => 'Credenziali WiFi cancellate';

  @override
  String summaryGeneratedForDate(String date) {
    return 'Riepilogo generato per $date';
  }

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'Impossibile generare il riepilogo. Assicurati di avere conversazioni per quel giorno.';

  @override
  String get summaryNotFound => 'Riepilogo non trovato';

  @override
  String get yourDaysJourney => 'Il viaggio della tua giornata';

  @override
  String get highlights => 'In evidenza';

  @override
  String get unresolvedQuestions => 'Domande irrisolte';

  @override
  String get decisions => 'Decisioni';

  @override
  String get learnings => 'Apprendimenti';

  @override
  String get autoDeletesAfterThreeDays => 'Eliminato automaticamente dopo 3 giorni.';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'Grafo della conoscenza eliminato con successo';

  @override
  String get exportStartedMayTakeFewSeconds => 'Esportazione avviata. Potrebbe richiedere qualche secondo...';

  @override
  String get knowledgeGraphDeleteDescription =>
      'Questo eliminerà tutti i dati derivati del grafo della conoscenza (nodi e connessioni). I tuoi ricordi originali rimarranno al sicuro. Il grafo verrà ricostruito nel tempo o alla prossima richiesta.';

  @override
  String get configureDailySummaryDigest => 'Configura il tuo riepilogo giornaliero delle attività';

  @override
  String accessesDataTypes(String dataTypes) {
    return 'Accede a $dataTypes';
  }

  @override
  String triggeredByType(String triggerType) {
    return 'attivato da $triggerType';
  }

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription ed è $triggerDescription.';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return 'È $triggerDescription.';
  }

  @override
  String get noSpecificDataAccessConfigured => 'Nessun accesso ai dati specifico configurato.';
}
