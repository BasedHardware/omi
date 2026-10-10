// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Italian (`it`).
class AppLocalizationsIt extends AppLocalizations {
  AppLocalizationsIt([String locale = 'it']) : super(locale);

  @override
  String get welcomeActionItemsDescription =>
      'La tua AI estrarrà automaticamente le attività dalle tue conversazioni. Appariranno qui quando create.';

  @override
  String get chatAppsProblemFailed => 'Qualcosa è andato storto. Riprova.';

  @override
  String get deviceOnboardingStarConversation => 'Metti tra i preferiti la conversazione in corso';

  @override
  String get deleteAll => 'Elimina tutto';

  @override
  String get copySummary => 'Copia riepilogo';

  @override
  String get locationAccessDesc => 'Così Omi può annotare dove si sono svolte le tue conversazioni.';

  @override
  String get firmwareUpdate => 'Aggiornamento firmware';

  @override
  String get chatMessages => 'messaggi';

  @override
  String get showEventsNoParticipants => 'Mostra eventi senza partecipanti';

  @override
  String get sharePeriodYear => 'Quest\'anno, Omi ha:';

  @override
  String get dreamReportRunFailed => 'Impossibile eseguire Dream. Riprova.';

  @override
  String get sttModelAccuracy => 'Precisione';

  @override
  String get scopes => 'Ambiti';

  @override
  String get deleteFlowFeedbackSubtitle => 'Cosa avrebbe reso Omi adatto a te?';

  @override
  String appDataAccessTitle(String appName) {
    return 'Consentire l\'accesso a $appName?';
  }

  @override
  String get pendantStorageAlmostFull =>
      'La memoria del ciondolo è quasi piena — tieni l\'app aperta per sincronizzare.';

  @override
  String get deviceOnboardingAllSetDoublePressBadge => '2×';

  @override
  String get copyErrorMessage => 'Copia messaggio di errore';

  @override
  String get filterMemories => 'Filtra Ricordi';

  @override
  String get helpsDiagnoseIssuesAutoDeletes =>
      'Aiuta a diagnosticare i problemi. Eliminato automaticamente dopo 3 giorni.';

  @override
  String get locationServiceDisabledDesc =>
      'I servizi di localizzazione sono disattivati su questo dispositivo. Attivali nelle Impostazioni.';

  @override
  String chatAppsIsConnected(String app) {
    return '$app è connesso';
  }

  @override
  String get paymentMethodStripe => 'Stripe';

  @override
  String get deleteReasonTechnicalIssues => 'Troppi problemi tecnici';

  @override
  String get payments => 'Pagamenti';

  @override
  String get verifiedFallback => 'Verificato';

  @override
  String get pleaseWait => 'Attendere prego…';

  @override
  String get appLanguage => 'Lingua App';

  @override
  String get unknownApp => 'App sconosciuta';

  @override
  String get appReEnableFailedBody => 'Non è stato possibile riattivare questa app. Riprova.';

  @override
  String get somethingWentWrongTryAgain => 'Qualcosa è andato storto! Riprova più tardi.';

  @override
  String get upgradeScheduled => 'Aggiornamento programmato';

  @override
  String get wrappedBuddiesLabel => 'AMICI';

  @override
  String get chatBlockShowMore => 'Mostra di più';

  @override
  String get subscriptionSuccessfulCharged =>
      'Abbonamento completato! Sei stato addebitato per il nuovo periodo di fatturazione.';

  @override
  String get phoneCall => 'Chiamata';

  @override
  String get chatAppsRefreshFailed => 'Impossibile aggiornare. Vengono mostrati gli ultimi dati disponibili.';

  @override
  String get noDesktopAccess => 'Non funziona su desktop';

  @override
  String get areYouSure => 'Sei sicuro?';

  @override
  String get resubscribe => 'Riabbonati';

  @override
  String voiceMatchMeterLabel(String level) {
    return 'Corrispondenza vocale: $level';
  }

  @override
  String get syncingBackground => 'Continueremo a sincronizzare le tue registrazioni in background.';

  @override
  String get signOutQuestion => 'Disconnettersi?';

  @override
  String chatAppsReadOnlyBanner(String app) {
    return 'Sola lettura. Rispondi a Omi su $app.';
  }

  @override
  String get connected => 'Connesso';

  @override
  String get shareStatsMessage => 'Condivido le mie statistiche Omi! (omi.me - il tuo assistente AI sempre attivo)';

  @override
  String get frequencyMinimal => 'Minimo';

  @override
  String get addAppSelectLogo => 'Seleziona un logo per la tua app';

  @override
  String get integrationInstructions => 'Istruzioni di integrazione';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'Stato autorizzazione accessibilità: $status. Controlla Preferenze di Sistema.';
  }

  @override
  String get wrappedCompleted => 'completate';

  @override
  String get remaining => 'Rimanente';

  @override
  String get onDeviceIntensive => 'La trascrizione su dispositivo richiede molte risorse computazionali.';

  @override
  String get diagnosticsVerdictTrouble => 'Problemi di connessione';

  @override
  String deviceOnboardingVoiceReplyPreviewThroughDevice(String device) {
    return 'Tramite $device';
  }

  @override
  String get copyConfig => 'Copia Configurazione';

  @override
  String accessesDataTypes(String dataTypes) {
    return 'Accede a $dataTypes';
  }

  @override
  String get chatAppsWaitlistConfirmed => 'Grazie. WhatsApp comparirà qui quando sarà pronto.';

  @override
  String get undo => 'Annulla';

  @override
  String get phoneContactsAccessTitle => 'Consenti accesso ai contatti';

  @override
  String confidenceIsConfirmed(String name) {
    return '$name è nello stato Confermato. Non devi fare altro.';
  }

  @override
  String get wrappedMovie => 'FILM';

  @override
  String get wrappedStruggleLabelUpper => 'SFIDA';

  @override
  String get appleHealthFeatureChatDesc => 'Chiedi a Omi dei tuoi passi, sonno, frequenza cardiaca e allenamenti.';

  @override
  String get writeReviewOptional => 'Scrivi una recensione (opzionale)';

  @override
  String get pairNewDevice => 'Accoppia nuovo dispositivo';

  @override
  String chatUsedOfLimitCompute(String used, String limit) {
    return '$used di $limit budget di calcolo utilizzato';
  }

  @override
  String get dailySummary => 'Riepilogo giornaliero';

  @override
  String get pleaseEnterYourName => 'Inserisci il tuo nome';

  @override
  String get continueWithoutDevice => 'Continua Senza Dispositivo';

  @override
  String get configure => 'Configura';

  @override
  String get createApp => 'Crea App';

  @override
  String get invalidUrlError => 'Inserisci un URL valido';

  @override
  String get appClosed => 'App chiusa';

  @override
  String get downgradeToFreemiumAction => 'Passa alla versione gratuita';

  @override
  String get chatAppsUseTelegramForNow => 'Usa Telegram per ora';

  @override
  String get wrappedBestMomentsBadge => 'Momenti migliori';

  @override
  String get storageSection => 'Archivio';

  @override
  String get pauseResumeRecording => 'Pausa/Riprendi Registrazione';

  @override
  String get phoneUnmute => 'Riattiva audio';

  @override
  String get youreAllSet => 'Sei pronto!';

  @override
  String get migrationComplete => 'Migrazione completata!';

  @override
  String get paymentAppCost => 'Costo app';

  @override
  String get deviceOnboardingFinish => 'Fine';

  @override
  String get noVerifiedNumbers => 'Nessun numero verificato';

  @override
  String get connectAiAssistantsToData => 'Collega assistenti AI ai tuoi dati';

  @override
  String get keyNameHint => 'es. Claude Desktop';

  @override
  String get paymentMethods => 'Metodi di Pagamento';

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'Impossibile verificare l\'autorizzazione accessibilità: $error';
  }

  @override
  String get confidenceReasonAutoOnly => 'Etichettato automaticamente, non ancora confermato';

  @override
  String whatsNewInVersion(String version) {
    return 'Novità nella $version';
  }

  @override
  String get selectYourLanguage => 'Seleziona la tua lingua';

  @override
  String get memoryClearedSuccess => 'La memoria di Omi su di te è stata cancellata';

  @override
  String get memoryContentHint => 'Preferisco le riunioni al mattino.';

  @override
  String get dreamReportTitle => 'Rapporto Dream';

  @override
  String importErrorGeneric(String error) {
    return 'Errore: $error';
  }

  @override
  String get completionRate => 'Tasso di completamento';

  @override
  String get trackPersonalGoals => 'Tieni traccia degli obiettivi personali sulla homepage';

  @override
  String get wrappedTryAgain => 'Riprova';

  @override
  String get dataProtection => 'Protezione dei dati';

  @override
  String get yourConversations => 'Le tue conversazioni';

  @override
  String pdfTitleLabel(String title) {
    return 'Titolo: $title';
  }

  @override
  String get sendRawAudioToOmiDescription =>
      'Disattiva per impedire l\'invio dell\'audio grezzo a Omi. Le trascrizioni e i dati necessari alle funzioni cloud possono ancora essere inviati a Omi.';

  @override
  String get entityLoadFailed => 'Impossibile caricare questa pagina.';

  @override
  String get networkNameSsid => 'Nome rete (SSID)';

  @override
  String get discovery => 'Scoperta';

  @override
  String get rayBanMetaMicPickerConnectError =>
      'Impossibile connettersi a quel microfono. Assicurati che sia connesso nelle Impostazioni dell\'iPhone.';

  @override
  String get fairUseAboutTitle => 'Informazioni sull\'uso corretto';

  @override
  String get wrappedYouTalkedAbout => 'Hai parlato di';

  @override
  String get downgradeLimitQuality => 'Qualità di trascrizione inferiore del 30%';

  @override
  String get sharedTasksUnknownSender => 'Qualcuno';

  @override
  String get selectAReason => 'Seleziona un motivo';

  @override
  String get wrappedWinLabel => 'VITTORIA';

  @override
  String get configuration => 'Configurazione';

  @override
  String get noFolder => 'Nessuna cartella';

  @override
  String get manifestRefreshedSuccess => 'Manifest aggiornato con successo';

  @override
  String get paymentStatusActive => 'Attivo';

  @override
  String get linkKeyMismatch => 'Chiave di collegamento non corrispondente';

  @override
  String speakerTagPromptProgress(int current, int total) {
    return '$current di $total';
  }

  @override
  String get updateRequiredMessage =>
      'Questa versione di Omi non è più supportata. Aggiorna per continuare a registrare e sincronizzare.';

  @override
  String get sharePeriodMonth => 'Questo mese, Omi ha:';

  @override
  String get rollbackToStableFirmware => 'Torna al firmware stabile';

  @override
  String get paymentStatusConnected => 'Connesso';

  @override
  String get findDeviceNoneTitle => 'Nessun Omi trovato';

  @override
  String get appIdCopiedToClipboard => 'ID dell\'app copiato negli appunti';

  @override
  String get bySubmittingYouAgreeToOmi => 'Inviando, accetti i ';

  @override
  String get filterRating => 'Valutazione';

  @override
  String get usageAtWork => 'Al lavoro';

  @override
  String get tasksCleanTodayMessage => 'Questo rimuoverà solo le scadenze';

  @override
  String get ignoredVoicesSubtitle => 'TV, podcast e altre voci che hai segnato come Non una persona';

  @override
  String get permissionEnable => 'Attiva';

  @override
  String integrationComingSoon(String appName) {
    return '$appName non è ancora supportato.';
  }

  @override
  String get sttModelLower => 'Più bassa';

  @override
  String get loadingYourMemories => 'Caricamento dei tuoi ricordi…';

  @override
  String get followUpQuestions => 'Domande di Follow-up';

  @override
  String get previousDay => 'Giorno precedente';

  @override
  String fairUseCaseRefCopied(String caseRef) {
    return '$caseRef copiato';
  }

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get recordingPaused => 'Registrazione in pausa';

  @override
  String get cannotReportOwnMessages => 'Non puoi segnalare i tuoi messaggi';

  @override
  String get enterWordsHint => 'Inserisci parole (separate da virgole)';

  @override
  String get audioDownloadFailed => 'Download audio fallito';

  @override
  String get clearMemoryMessage => 'Tutti i tuoi ricordi verranno eliminati. Questa azione non può essere annullata.';

  @override
  String get templateNameHint => 'es. Estrattore attività riunione';

  @override
  String speakerLabelTalkTime(String duration) {
    return '$duration di questa voce';
  }

  @override
  String get recordingMode => 'Modalità di registrazione';

  @override
  String get cancelReasonOther => 'Altro';

  @override
  String get sttModelHigher => 'Più alta';

  @override
  String get settingUpSystemAudioCapture => 'Configurazione della cattura audio di sistema';

  @override
  String memoriesCount(int count) {
    return '$count memorie';
  }

  @override
  String get noSpecificDataAccessConfigured => 'Nessun accesso ai dati specifico configurato.';

  @override
  String get recordingIdLabel => 'ID registrazione';

  @override
  String get highlights => 'In evidenza';

  @override
  String get phoneTryAgain => 'Riprova';

  @override
  String chatAppsCouldNotOpen(String app) {
    return 'Impossibile aprire $app. Assicurati che sia installata e riprova.';
  }

  @override
  String get onDeviceTranscriptionDesc => 'La trascrizione viene elaborata localmente sul tuo dispositivo';

  @override
  String get chatAppsTryPromise => 'Cosa ho promesso a Sam ieri?';

  @override
  String get paymentStatusNotConnected => 'Non connesso';

  @override
  String get intervalSeconds => 'Intervallo (secondi)';

  @override
  String get authorize => 'Autorizza';

  @override
  String get settingsHeader => 'IMPOSTAZIONI';

  @override
  String get personNameAlreadyExists => 'Questo nome esiste già';

  @override
  String get deviceOnboardingVoiceReplyPreviewThroughCurrentOutput => 'Attraverso l\'uscita audio corrente';

  @override
  String get monthJun => 'Giu';

  @override
  String selectedCount(int count) {
    return '$count selezionati';
  }

  @override
  String get batteryHistory => 'Batteria';

  @override
  String get noPastChats => 'Le tue chat con Omi compaiono qui.';

  @override
  String get chatAppsDoesSave => 'Salva ricordi e gestisce le tue attività';

  @override
  String get apiKey => 'Chiave API';

  @override
  String get authFailedToLinkGoogle => 'Collegamento con Google non riuscito, riprova.';

  @override
  String audioUploadFailedKeptLocal(String duration) {
    return 'Caricamento non riuscito — $duration di audio conservati sul telefono.';
  }

  @override
  String get free => 'Gratuito';

  @override
  String get deselectAllTasksMenu => 'Deseleziona tutto';

  @override
  String get dreamReportLoadFailed => 'Impossibile caricare il rapporto Dream.';

  @override
  String get entityRecentConversations => 'Conversazioni recenti';

  @override
  String get pendantRecordingNote =>
      'Il tuo ciondolo registra autonomamente. Le registrazioni si sincronizzano con il telefono mentre l\'app è aperta.';

  @override
  String get manageStorage => 'Gestisci archivio';

  @override
  String get filterSystem => 'Su di Te';

  @override
  String get deleteConsequenceSubscription => 'Eventuali abbonamenti attivi verranno annullati.';

  @override
  String get defaultList => 'Lista Predefinita';

  @override
  String get shared => 'Condiviso';

  @override
  String get customVocabulary => 'Vocabolario Personalizzato';

  @override
  String get feedbackTitleAudioQuality => 'Quali problemi hai riscontrato?';

  @override
  String get thisActionCannotBeUndone => 'Questa azione non può essere annullata.';

  @override
  String errorRequestingPermission(String error) {
    return 'Errore durante la richiesta del permesso: $error';
  }

  @override
  String get recapRegenerateFailed => 'Impossibile rigenerare il riepilogo. Riprova più tardi.';

  @override
  String get result => 'Risultato:';

  @override
  String get statusCallMissed => 'Chiamata persa';

  @override
  String get diagnosticsLongestGap => 'Interruzione più lunga';

  @override
  String get noLogFilesFound => 'Nessun file di log trovato.';

  @override
  String get speechTranscriptionSectionTitle => 'Voce e trascrizione';

  @override
  String get syncNow => 'Sincronizza ora';

  @override
  String get sttUsePrimaryLanguage => 'Usa lingua principale';

  @override
  String get importUnsupportedFileType => 'Questo tipo di file non può essere importato.';

  @override
  String get chatSendMessage => 'Invia messaggio';

  @override
  String get syncCardAllBackedUp => 'Tutte le registrazioni sincronizzate';

  @override
  String get settings => 'Impostazioni';

  @override
  String get backgroundLocationDeniedDesc =>
      'Vai nelle impostazioni del dispositivo e imposta il permesso di localizzazione su \"Consenti sempre\"';

  @override
  String get computationallyIntensive => 'La trascrizione sul dispositivo è computazionalmente intensiva.';

  @override
  String get and => ' e ';

  @override
  String get yourVerifiedNumbers => 'I tuoi numeri verificati';

  @override
  String get tasksCleanTodayTitle => 'Pulire le attività di oggi?';

  @override
  String get microphonePermission => 'Permesso Microfono';

  @override
  String get failedToUpdateConversationTitle => 'Aggiornamento del titolo della conversazione non riuscito';

  @override
  String get appsDisconnected => 'Le tue app e integrazioni verranno disconnesse.';

  @override
  String get live => 'Dal vivo';

  @override
  String get connectionFailed => 'Connessione fallita';

  @override
  String get selectImages => 'Seleziona immagini';

  @override
  String get playbackAudioNetworkFailed => 'Controlla la connessione';

  @override
  String get paypalEmail => 'Email PayPal';

  @override
  String get chatAppsOnTheList => 'In lista';

  @override
  String get generateSummary => 'Genera riepilogo';

  @override
  String get categoryHealth => 'Salute';

  @override
  String get transcribeLaterStorageFull =>
      'Lo spazio sul telefono sta per esaurirsi, quindi la registrazione è in pausa. Libera spazio o carica le registrazioni e riprenderà automaticamente.';

  @override
  String get chatAppsNoChatsTitle => 'Ancora nessuna chat';

  @override
  String get onboardingSetupStepPersonalize => 'Personalizzazione della tua esperienza';

  @override
  String get leaveUnselectedTasks => 'Lascia non selezionato per creare attività senza un progetto';

  @override
  String get wrappedButYouPushedThroughEmoji => 'Ma ce l\'hai fatta 💪';

  @override
  String get needHelp => 'Serve Aiuto?';

  @override
  String get confirmAndCancel => 'Conferma e annulla';

  @override
  String get frequencyDescHigh => 'Più suggerimenti, circa 6–9 al giorno';

  @override
  String get copyLink => 'Copia link';

  @override
  String get dreamReportLiveBanner => 'Dream applica queste modifiche da solo. Annullale in Modifiche recenti.';

  @override
  String get enterActionItemDescription => 'Inserisci la descrizione dell\'attività';

  @override
  String chatAppsInChannel(String app) {
    return 'Su $app';
  }

  @override
  String get links => 'Link';

  @override
  String get dreamReportEmptyTitle => 'Ancora nessun passaggio';

  @override
  String get monthJan => 'Gen';

  @override
  String get wrappedMostProductiveDay => 'Più produttivo';

  @override
  String get productUpdate => 'Aggiornamento prodotto';

  @override
  String get addYourReview => 'Aggiungi la tua recensione';

  @override
  String get raybanMetaImageCaptureReady => 'Acquisizione immagini pronta';

  @override
  String get displayUpcomingMeetingsDescription => 'Mostra le riunioni imminenti nella barra dei menu';

  @override
  String get whatWeCollect => 'Cosa raccogliamo';

  @override
  String get connectPayPalToReceivePayments =>
      'Collega il tuo account PayPal per iniziare a ricevere pagamenti per le tue app';

  @override
  String get justAMoment => 'Un momento, per favore';

  @override
  String get chatReplyServerError => 'Qualcosa è andato storto da parte nostra. Riprova.';

  @override
  String get transferInProgress => 'Trasferimento in corso…';

  @override
  String get usageAll => 'Sempre';

  @override
  String get failedToLoadContacts => 'Impossibile caricare i contatti';

  @override
  String appUsersCount(int count) {
    return '$count+ utenti';
  }

  @override
  String get report => 'Segnala';

  @override
  String get languageLabel => 'Lingua';

  @override
  String verifiedOnDate(String date) {
    return 'Verificato il $date';
  }

  @override
  String get customVocabularyHeader => 'VOCABOLARIO PERSONALIZZATO';

  @override
  String otaRebooting(String deviceName) {
    return '$deviceName si sta riavviando con il nuovo firmware.';
  }

  @override
  String get mcpServer => 'Server MCP';

  @override
  String get findDevice => 'Trova';

  @override
  String get msgUploadAttachedFileFailed => 'Caricamento del file allegato fallito.';

  @override
  String get appName => 'App Name';

  @override
  String get pairingTitlePlaudNote => 'Metti Plaud Note in modalità di accoppiamento';

  @override
  String get moreOptions => 'Altre opzioni';

  @override
  String get noConversationsHeroMessage =>
      'Le conversazioni che registri compaiono qui. Tocca il pulsante di registrazione nella Home per registrare la prima.';

  @override
  String get finish => 'Termina';

  @override
  String get goBack => 'Indietro';

  @override
  String get apiKeysDescription =>
      'Le chiavi API vengono utilizzate per l\'autenticazione quando la tua app comunica con il server Omi. Consentono alla tua applicazione di creare ricordi e accedere ad altri servizi Omi in modo sicuro.';

  @override
  String get sttProviderSpeechmatics => 'Speechmatics';

  @override
  String get setWebhookUrlInSettings =>
      'Imposta l\'URL del webhook nelle impostazioni sviluppatore per usare questa funzione.';

  @override
  String get dailyScoreBreakdown => 'Dettaglio punteggio giornaliero';

  @override
  String get showMeetingsMenuBarDesc =>
      'Visualizza la tua prossima riunione e il tempo rimanente nella barra dei menu di macOS';

  @override
  String get tapToTrackThisGoal => 'Tocca per monitorare questo obiettivo';

  @override
  String get summarizingConversation => 'Riepilogo della conversazione…\nPotrebbe richiedere alcuni secondi';

  @override
  String get noInternetConnection => 'Nessuna connessione Internet';

  @override
  String diagnosticsCountSincePairing(int count) {
    return '$count dall\'associazione';
  }

  @override
  String get wrappedTasksCreated => 'attività create';

  @override
  String get deleteConsequenceNoRecovery => 'Il tuo account non può essere ripristinato — nemmeno dall\'assistenza.';

  @override
  String get waitForReprocessing => 'Attendi il termine della rielaborazione.';

  @override
  String get needYourPermission => 'Abbiamo bisogno del tuo permesso';

  @override
  String get downgradeLimitSpeakers => 'Impossibile identificare gli interlocutori';

  @override
  String conversationsTodayCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count conversazioni oggi.',
      one: '1 conversazione oggi.',
      zero: 'Nessuna conversazione oggi.',
    );
    return '$_temp0';
  }

  @override
  String get dailyScore => 'PUNTEGGIO GIORNALIERO';

  @override
  String get reportAnIssue => 'Segnala un problema';

  @override
  String get invalidKey => 'Tasto non valido';

  @override
  String get preview => 'Anteprima';

  @override
  String get nextWeek => 'La prossima settimana';

  @override
  String get confidenceUnverified => 'Non verificato';

  @override
  String get previewScreenshots => 'Anteprima schermate';

  @override
  String get ledBrightness => 'Luminosità LED';

  @override
  String get firmwareUpdateFailedMessage =>
      'L\'aggiornamento non è stato completato. Il dispositivo usa ancora il firmware attuale ed è sicuro da usare. Tienilo carico e vicino al telefono, poi riprova.';

  @override
  String get loadingProfile => 'Caricamento del profilo…';

  @override
  String get deleteRecapConfirmTitle => 'Eliminare questo riepilogo?';

  @override
  String get notificationFrequency => 'Frequenza notifiche';

  @override
  String get captureSystemAudioFromMeetings => 'Cattura l\'audio di sistema dalle riunioni';

  @override
  String get storeAudioCloudDescription => 'Carica le registrazioni mentre parli, così puoi riascoltarle più tardi.';

  @override
  String get color => 'Colore';

  @override
  String get open => 'Apri';

  @override
  String get diagnosticsVerdictNoDrops => 'Nessuna interruzione questa settimana';

  @override
  String get autoExtractionFeature => 'Estratto automaticamente dalle conversazioni';

  @override
  String get searchResults => 'Risultati di ricerca';

  @override
  String get v2UndetectedMessage =>
      'Vediamo che hai un dispositivo V1 o il tuo dispositivo non è connesso. La funzionalità della scheda SD è disponibile solo per i dispositivi V2.';

  @override
  String get endAndProcess => 'Termina ed Elabora Conversazione';

  @override
  String get noSyncedRecordings => 'Nessuna registrazione sincronizzata ancora';

  @override
  String get coworker => 'Collega';

  @override
  String get setupQuestionUsage => '2. Dove prevedi di usare il tuo Omi?';

  @override
  String get pinnedNotSelectable => 'Fissata, non selezionabile';

  @override
  String get showMore => 'mostra di più ↓';

  @override
  String get createYourFirstMemory => 'Crea il tuo primo ricordo per iniziare';

  @override
  String get discardedConversation => 'Conversazione scartata';

  @override
  String get enableApps => 'Abilita app';

  @override
  String get today => 'Oggi';

  @override
  String get showEventsNoParticipantsDesc =>
      'Quando abilitato, Prossimi Eventi mostra eventi senza partecipanti o link video.';

  @override
  String get couldNotLoadPage => 'Impossibile caricare la pagina. Controlla la connessione e riprova.';

  @override
  String actionItemDeletedResult(String description) {
    return 'Attività \"$description\" eliminata';
  }

  @override
  String get deleteSampleQuestion => 'Eliminare campione?';

  @override
  String get youAreOnAPaidPlan => 'Sei su un piano a pagamento.';

  @override
  String get otaInstallFailed => 'Installazione non riuscita. Il dispositivo usa ancora il firmware attuale.';

  @override
  String get addFirstMemory => 'Aggiungi il tuo primo ricordo';

  @override
  String get appDeletedSuccessfully => 'App eliminata con successo';

  @override
  String get chatAppsConnectTelegramMessage => 'Omi aprirà Telegram con un link privato solo per te.';

  @override
  String get phoneSetupStep1Title => 'Verifica il tuo numero di telefono';

  @override
  String get deviceRequirements => 'Il tuo dispositivo non soddisfa i requisiti per la trascrizione su dispositivo.';

  @override
  String get confidenceEvidenceHeader => 'Prove';

  @override
  String get pleaseEnterAName => 'Inserisci un nome.';

  @override
  String get deleteConfirmationWord => 'DELETE';

  @override
  String get speakerTagPromptThatsMe => 'Sono io';

  @override
  String get ourCommitment => 'Il nostro impegno';

  @override
  String get notificationScopes => 'Ambiti di Notifica';

  @override
  String get autoDeletesAfter3Days => 'Eliminazione automatica dopo 3 giorni';

  @override
  String get initialisingRecorder => 'Inizializzazione registratore';

  @override
  String get privateAndSecureOnDevice => 'Salvato su questo telefono';

  @override
  String get allObjectsMigratedFinalizing => 'Tutti gli oggetti migrati. Finalizzazione…';

  @override
  String get chatAppsOpenMessages => 'Apri Messaggi';

  @override
  String get upgradeToPro => 'Passa a Pro';

  @override
  String get clientId => 'ID Cliente';

  @override
  String get backgroundActivity => 'Attività in background';

  @override
  String get noSummaryAvailable => 'Nessun riepilogo disponibile';

  @override
  String get failedToUpdateStarred => 'Impossibile aggiornare lo stato preferito.';

  @override
  String get omiYourAiCompanion => 'Omi – Il Tuo Compagno AI';

  @override
  String get pleaseSelectReason => 'Seleziona un motivo';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Tutti i $count ricordi verranno eliminati. Questa azione non può essere annullata.';
  }

  @override
  String get connectNow => 'Collega Ora';

  @override
  String chatAppsDisconnectTitle(String app) {
    return 'Disconnettere $app?';
  }

  @override
  String get clearCredentials => 'Cancella credenziali';

  @override
  String get grantContactsPermissionForSms => 'Concedi l\'autorizzazione ai contatti per condividere via SMS';

  @override
  String get cloudTranscription => 'Trascrizione cloud';

  @override
  String get memoryHistory => 'Cronologia';

  @override
  String get speechSamples => 'Campioni vocali';

  @override
  String get wrappedBiggest => 'La più grande';

  @override
  String get reviewShowMore => 'Mostra altro';

  @override
  String get triggersWhenDaySummaryGenerated => 'Si attiva quando viene generato il riepilogo giornaliero.';

  @override
  String get thankYouFeedback => 'Grazie per il tuo feedback!';

  @override
  String get allow => 'Consenti';

  @override
  String triggeredByType(String triggerType) {
    return 'attivato da $triggerType';
  }

  @override
  String get howToPair => 'Come associare';

  @override
  String get conversationDeveloperTools => 'Strumenti per sviluppatori nelle conversazioni';

  @override
  String get memoryProvenanceIphone => 'iPhone';

  @override
  String get aboutYou => 'Su di te';

  @override
  String get memoryProvenanceMac => 'Mac';

  @override
  String get effectCounts => 'Aiuta';

  @override
  String get tagSpeakerIncludingLaterSpeech => 'Etichetta anche il parlato successivo di questo speaker';

  @override
  String get storeAudioOnPhone => 'Archivia audio sul telefono';

  @override
  String get developerApiKeys => 'Chiavi API sviluppatore';

  @override
  String get wrappedMyBuddiesCard => 'I miei amici';

  @override
  String get bulkExportAlreadyExported => 'Tutte le attività selezionate sono già state esportate';

  @override
  String get popularBadge => 'POPOLARE';

  @override
  String get enableLocationTitle => 'Attiva posizione';

  @override
  String get feedbackBug => 'Feedback / Bug';

  @override
  String get good => 'Buono';

  @override
  String get upgradeYourPlan => 'Aggiorna il tuo piano';

  @override
  String get exportingAllData =>
      'Esportazione dei tuoi dati in corso… Tieni Omi aperta; gli account di grandi dimensioni possono richiedere diversi minuti.';

  @override
  String get switchAndRestart => 'Cambia';

  @override
  String get noReposFound => 'Nessun repository trovato';

  @override
  String get latest => 'Più recente';

  @override
  String get failedToRevoke => 'Impossibile revocare l\'autorizzazione. Riprova.';

  @override
  String get appleHealthDisconnectCta => 'Disconnetti Apple Health';

  @override
  String get chatAppsPrivateMemoriesSubtitle =>
      'Salute, denaro e tutto ciò che hai segnato come privato restano fuori dalle app di chat.';

  @override
  String get deleteFlowFeedbackTitle => 'Raccontaci di più';

  @override
  String get failedToConnectTodoistRetry => 'Connessione a Todoist non riuscita. Riprova.';

  @override
  String get capturePhoneStorageFull => 'Memoria del telefono piena';

  @override
  String deletePeopleTitle(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Eliminare $count persone?',
      one: 'Eliminare 1 persona?',
    );
    return '$_temp0';
  }

  @override
  String get cleanUpNothingMessage => 'Al momento Omi è sicuro di tutti.';

  @override
  String get writeAReviewOptional => 'Scrivi una recensione (opzionale)';

  @override
  String get syncFailed => 'Sincronizzazione fallita';

  @override
  String get audioShareFailed => 'Condivisione fallita';

  @override
  String loadMoreRemaining(String count) {
    return 'Carica altro ($count rimanenti)';
  }

  @override
  String get phoneDeleteNumberFailed => 'Impossibile eliminare questo numero';

  @override
  String deviceUsesCodec(String device, String reason) {
    return '$device registra in un formato che questo fornitore non riesce a leggere ($reason), quindi verrà usata invece la trascrizione di Omi.';
  }

  @override
  String get chatAppsConnectIMessageMessage =>
      'Invia a Omi un messaggio dal numero che vuoi usare. Il codice al suo interno collega quel numero al tuo account.';

  @override
  String get speechToTextUnavailableDesc =>
      'La trascrizione vocale non è disponibile al momento. Controlla la connessione Internet e le impostazioni di riconoscimento vocale del dispositivo, poi riprova.';

  @override
  String get chatReplyTimeout => 'La risposta ha impiegato troppo tempo. Riprova.';

  @override
  String get passwordMinLengthError => 'La password deve essere di almeno 8 caratteri';

  @override
  String get chatAppsWhatsAppMessage =>
      'Stiamo lavorando per portare Omi su WhatsApp. Comparirà qui quando sarà pronto.';

  @override
  String get deleteAccountCheckbox =>
      'Comprendo che l\'eliminazione del mio account è permanente e tutti i dati, inclusi ricordi e conversazioni, saranno persi e non potranno essere recuperati.';

  @override
  String get firmwareConnectWifi => 'Connettiti a WiFi o rete cellulare.';

  @override
  String get forgetDeviceConfirmMessage => 'Omi smetterà di connettersi a questo dispositivo.';

  @override
  String get editSwipeFeature => 'Tocca per modificare, scorri per completare o eliminare';

  @override
  String get memoryManagement => 'Gestione memoria';

  @override
  String get transcriptLoadFailed => 'Impossibile caricare la trascrizione.';

  @override
  String get diagnosticsExportTitle => 'Diagnostica del dispositivo Omi';

  @override
  String get updateOmiFirmware => 'Aggiorna firmware Omi';

  @override
  String get importTooManyAttempts => 'Troppe importazioni in questo momento. Riprova più tardi.';

  @override
  String get noAppsFound => 'Nessuna app trovata';

  @override
  String get phoneSetupStep1Subtitle => 'Ti chiameremo per confermare';

  @override
  String get deleteSyncedFiles => 'Elimina registrazioni sincronizzate';

  @override
  String speakerLabelVoiceStatus(String state) {
    String _temp0 = intl.Intl.selectLogic(
      state,
      {
        'learned': 'Voce appresa',
        'pending': 'Apprendimento della voce…',
        'disabled': 'Il salvataggio della voce è disattivato',
        'other': 'Voce non ancora appresa',
      },
    );
    return '$_temp0';
  }

  @override
  String get recordingsMayCaptureOthers =>
      'Le registrazioni potrebbero catturare le voci di altri. Assicurati di avere il consenso di tutti i partecipanti prima di abilitare.';

  @override
  String get helpful => 'Utile';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return 'Download di $model: $received / $total MB';
  }

  @override
  String get permissions => 'Autorizzazioni';

  @override
  String get audioDownloadSuccess => 'Audio scaricato con successo';

  @override
  String get confirmPlanChange => 'Conferma cambio piano';

  @override
  String get wrappedThatAwkwardMoment => 'Quel momento imbarazzante';

  @override
  String get calendarProviders => 'Provider Calendario';

  @override
  String evidenceAutoUnconfirmed(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count etichette automatiche non ancora confermate',
      one: '1 etichetta automatica non ancora confermata',
    );
    return '$_temp0';
  }

  @override
  String get importData => 'Importa Dati';

  @override
  String get weekdayMon => 'Lun';

  @override
  String get deviceStorageTitle => 'Archiviazione del dispositivo';

  @override
  String get externalAppAccess => 'Accesso app esterne';

  @override
  String get transcriptionUnavailable => 'Trascrizione non disponibile';

  @override
  String get termsAndPrivacyPolicy => 'Termini e Informativa sulla Privacy';

  @override
  String get noImportsYet => 'Nessuna importazione ancora';

  @override
  String get openOmiOnAppleWatchDescription =>
      'L\'app Omi è installata sul tuo Apple Watch. Aprila e tocca Avvia per iniziare.';

  @override
  String dreamReportFailed(String error) {
    return 'Non riuscito ($error)';
  }

  @override
  String get sendSummary => 'Invia riepilogo';

  @override
  String get filterAll => 'Tutti';

  @override
  String get deleteChatMessage => 'Sparirà per sempre dalle chat precedenti.';

  @override
  String get timeout10Minutes => '10 minuti';

  @override
  String get noCalendarEventsNearby => 'Nessun evento del calendario trovato in questo orario.';

  @override
  String get cancelSyncQuestion => 'Annullare la sincronizzazione?';

  @override
  String get whatShouldWeMake => 'Cosa dovremmo creare?';

  @override
  String get usageListened => 'Listened';

  @override
  String get errorUpdatingStripeDetails => 'Errore nell\'aggiornamento dei dettagli Stripe! Riprova più tardi.';

  @override
  String get conversationEndAfterHours => 'Le conversazioni termineranno ora dopo 4 ore di silenzio';

  @override
  String get issueActivatingApp => 'Si è verificato un problema nell\'attivazione di questa app. Riprova.';

  @override
  String get appCreatedSuccessfully => 'App creata con successo!';

  @override
  String get categoryNews => 'Notizie';

  @override
  String get phoneSearchHint => 'Cerca';

  @override
  String peoplePinnedCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count fissate',
      one: '1 fissata',
    );
    return '$_temp0';
  }

  @override
  String get wrappedHours => 'ore';

  @override
  String get phoneKeypad => 'Tastiera';

  @override
  String get peopleFilterLowConfidence => 'Bassa affidabilità';

  @override
  String get agreeToContributeData =>
      'Comprendo e accetto di contribuire con i miei dati per l\'addestramento dell\'IA';

  @override
  String get addGoal => 'Aggiungi obiettivo';

  @override
  String get dreamReportRunInProgress => 'Un passaggio è già in corso. Riprova tra un minuto.';

  @override
  String importedConfig(String providerName) {
    return 'Configurazione $providerName importata';
  }

  @override
  String monthsAgo(int count) {
    return '$count mesi fa';
  }

  @override
  String get downgradeLimitationsHeading => 'Andrai incontro a queste limitazioni:';

  @override
  String get chatRemoveSelectedText => 'Rimuovi testo citato';

  @override
  String get firmwareBatteryAbove15 => 'Batteria sopra il 15%';

  @override
  String reviewQuestionSamePerson(String name) {
    return 'È la stessa persona di “$name”?';
  }

  @override
  String get effectCountsALot => 'Aiuta molto';

  @override
  String get sdCard => 'SD Card';

  @override
  String get openInGoogleCalendar => 'Apri in Google Calendar';

  @override
  String get appleHealthFeatureSecureTitle => 'Sincronizzazione sicura';

  @override
  String get conversationDeveloperToolsDescription =>
      'Mostra Copia ID conversazione e Prova prompt nel menu della conversazione';

  @override
  String get host => 'Host';

  @override
  String get deleteReasonMissingFeatures => 'Mancano funzionalità di cui ho bisogno';

  @override
  String get syncingInProgress => 'Sincronizzazione in corso';

  @override
  String get tabDone => 'Fatto';

  @override
  String get revoke => 'Revoca';

  @override
  String get mcp => 'MCP';

  @override
  String get anyoneCanDiscoverTemplate => 'Chiunque può scoprire il tuo modello';

  @override
  String get mcpDescription =>
      'Per connettere Omi ad altre applicazioni per leggere, cercare e gestire i tuoi ricordi e conversazioni. Crea una chiave per iniziare.';

  @override
  String get connectionLostDescription =>
      'La connessione è stata interrotta. Controlla la tua connessione internet e riprova.';

  @override
  String chatAppsNoChatsMessage(String app) {
    return 'Le chat che hai con Omi su $app compaiono qui.';
  }

  @override
  String get storedLocallyNeverShared => 'Salvato su questo telefono. Inviato solo al tuo fornitore di trascrizione.';

  @override
  String get morePaymentMethodsComingSoon => 'Presto altri metodi di pagamento';

  @override
  String get allCaughtUp => 'Tutto aggiornato';

  @override
  String previewImageLabel(int index, int total) {
    return 'Screenshot $index di $total';
  }

  @override
  String get disable => 'Disabilita';

  @override
  String get recordings => 'Registrazioni';

  @override
  String get enterPersonsName => 'Inserisci il nome della persona';

  @override
  String get newConversationCreated => 'Nuova conversazione creata';

  @override
  String resetsInDays(int count) {
    return 'Si resetta tra $count giorni';
  }

  @override
  String get confidenceConfirmed => 'Confermato';

  @override
  String get bulkExportInProgress => 'Esportazione…';

  @override
  String get detectLanguages => 'Rileva oltre 10 lingue';

  @override
  String get phoneSpeaker => 'Altoparlante';

  @override
  String get visitWebsite => 'Visita il sito web';

  @override
  String get howToTakeGoodSample => 'Come fare un buon campione?';

  @override
  String get clearChat => 'Cancella chat';

  @override
  String languageSetTo(String language) {
    return 'Lingua impostata su $language';
  }

  @override
  String get deviceOnboardingVoiceReplyHeadphonesDescription =>
      'Privato. Parla solo tramite AirPods, Bluetooth o cuffie con filo.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'Il tuo piano rimarrà attivo fino al $date. Dopo, perderai l\'accesso alle funzionalità illimitate.';
  }

  @override
  String get clientSecret => 'Segreto Cliente';

  @override
  String get pairingTitleAppleWatch => 'Collega Apple Watch';

  @override
  String get share => 'Condividi';

  @override
  String get yourPrivacyYourControl => 'La Tua Privacy, Il Tuo Controllo';

  @override
  String get tapToCopy => 'Tocca per copiare';

  @override
  String get feedbackTitleFoundAlternative => 'A cosa stai passando?';

  @override
  String get all => 'All';

  @override
  String get filterCapabilities => 'Funzionalità';

  @override
  String get tagOtherSegments => 'Tagga altri segmenti';

  @override
  String get entityDecisions => 'Decisioni';

  @override
  String get tasksCreatedInWorkspace => 'Le attività saranno create in quest\'area di lavoro';

  @override
  String get fairUseDailyTranscription => 'Trascrizione giornaliera';

  @override
  String get pausePlayback => 'Pausa';

  @override
  String get sharedTasksLinkExpired => 'Queste attività condivise non sono state trovate o il link è scaduto.';

  @override
  String get editConversationDialogTitle => 'Modifica conversazione';

  @override
  String get deleteMemoryConfirmation => 'Eliminare questo ricordo? Questa azione non può essere annullata.';

  @override
  String get appUnderReviewMessage =>
      'La tua app è in revisione e visibile solo a te. Sarà pubblica dopo l\'approvazione.';

  @override
  String get illDoItLater => 'Lo farò più tardi';

  @override
  String get captureStillRecording => 'Registrazione in corso';

  @override
  String confidenceNextLabels(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Etichettali in altre $count conversazioni.',
      one: 'Etichettali in 1 altra conversazione.',
    );
    return '$_temp0';
  }

  @override
  String get speakerTagPromptAnswerFailed => 'Impossibile salvare. Riprova.';

  @override
  String get feedbackReasonSummaryIncomplete => 'Incompleto';

  @override
  String get errorActivatingApp => 'Errore nell\'attivazione dell\'app';

  @override
  String get tasksCompleted => 'Attività completate';

  @override
  String onboardingStepOf(int current, int total) {
    return 'Passaggio $current di $total';
  }

  @override
  String get downgradeAnyway => 'Passa comunque';

  @override
  String get leaveBlank => 'Lascia vuoto';

  @override
  String get chatAppsViewChats => 'Vedi chat';

  @override
  String get captureScreenRecordingPermissionRequired => 'Autorizzazione registrazione schermo richiesta';

  @override
  String get accountCutoverUpdateRequiredTitle => 'Aggiornamento richiesto';

  @override
  String weeksAgo(int count) {
    return '$count settimane fa';
  }

  @override
  String get phoneEndCall => 'Fine';

  @override
  String get startupFailedMessage =>
      'Si è verificato un problema durante l\'avvio di Omi. Controlla la tua connessione, poi riprova.';

  @override
  String get permissionRevokedTitle => 'Permesso Revocato';

  @override
  String get chatFeatures => 'Funzioni chat';

  @override
  String get couldNotLoadMap => 'Impossibile caricare la mappa';

  @override
  String get selectContactsToShare => 'Seleziona i contatti da condividere';

  @override
  String get ok => 'OK';

  @override
  String get memoryReviewConfirmed => 'Confermato.';

  @override
  String get deleteKnowledgeGraph => 'Elimina Grafo di Conoscenza';

  @override
  String get reviewChangeFailed => 'Impossibile aggiornare questa modifica. Riprova.';

  @override
  String get limitless => 'Limitless';

  @override
  String uploadingToCloud(int current, int total) {
    return 'Caricamento di $current di $total';
  }

  @override
  String get dontSeeYourDevice => 'Non vedi il tuo dispositivo?';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Le tue attività saranno sincronizzate con il tuo account $appName';
  }

  @override
  String appSettingsLabel(String appName) {
    return 'Impostazioni di $appName';
  }

  @override
  String get chatBlockShowLess => 'Mostra di meno';

  @override
  String get mindMap => 'Mind Map';

  @override
  String get authorizationBearer => 'Authorization: Bearer <chiave>';

  @override
  String get dreamReportWouldSuggestTasks => 'Suggerirebbe attività';

  @override
  String get dreamReportWouldAsk => 'Ti chiederebbe';

  @override
  String get getFreeUnlimitedAccess => 'Ottieni accesso illimitato gratuito';

  @override
  String get yourDaysJourney => 'Il viaggio della tua giornata';

  @override
  String get transcriptReceived => 'Trascrizione ricevuta';

  @override
  String get expand => 'Espandi';

  @override
  String get onboardingCompleteMessage =>
      'Lascia Omi attivo per un paio di giorni. Conversazioni, ricordi e cose da fare inizieranno a riempirsi.';

  @override
  String get trainFamilyProfiles => 'Addestra Profili per Amici e Famiglia';

  @override
  String get selectText => 'Seleziona testo';

  @override
  String get generatingDescription => 'Generazione descrizione…';

  @override
  String get deviceOnboardingStarConversationDesc => 'Segna la conversazione come importante';

  @override
  String disableAppNamed(String appName) {
    return 'Disattiva $appName';
  }

  @override
  String get deleteConversationConfirmation =>
      'Eliminare questa conversazione? Questa azione non può essere annullata.';

  @override
  String get contentCopied => 'Contenuto copiato negli appunti';

  @override
  String get joinTheCommunity => 'Unisciti alla comunità!';

  @override
  String get noContactsWithPhoneNumbers => 'Nessun contatto con numero di telefono trovato';

  @override
  String get removeAttachment => 'Rimuovi allegato';

  @override
  String get followTheVoiceInstructions => 'Segui le istruzioni vocali';

  @override
  String get createYourOwnApp => 'Crea la tua app';

  @override
  String get paymentDetails => 'Dettagli Pagamento';

  @override
  String get tellOmiWhoSaidIt => 'Dì a Omi chi l\'ha detto 🗣️';

  @override
  String audioInputSetTo(String deviceName) {
    return 'Ingresso audio impostato su $deviceName';
  }

  @override
  String get pleaseEnterValidEmail => 'Inserisci un indirizzo email valido';

  @override
  String get thisYear => 'Quest\'Anno';

  @override
  String get noTranscriptMessage => 'Questa conversazione non ha una trascrizione.';

  @override
  String get appearanceDark => 'Scuro';

  @override
  String get createCustomTemplate => 'Crea modello personalizzato';

  @override
  String get monthMay => 'Mag';

  @override
  String get tasksAddedToList => 'Le attività saranno aggiunte a questa lista';

  @override
  String isTriggeredBy(String triggerDescription) {
    return 'È $triggerDescription.';
  }

  @override
  String get deleteConversationTitle => 'Eliminare Conversazione?';

  @override
  String get accountCutoverUpdateRequiredMessage =>
      'Installa l\'ultima app Omi per continuare dopo la migrazione dell\'account.';

  @override
  String get txtFormat => 'TXT';

  @override
  String chatAppsDisconnectMessage(String app) {
    return 'Omi smetterà di rispondere su $app ed eliminerà la cronologia delle chat che conserva per questa app. I messaggi già presenti su $app restano lì.';
  }

  @override
  String get captureWithCamera => 'Cattura con la fotocamera';

  @override
  String get appIdLabel => 'ID dell\'app';

  @override
  String get endpointUrl => 'URL endpoint';

  @override
  String get actionItemUpdated => 'Attività aggiornata';

  @override
  String itemsSelected(int count) {
    return '$count selezionati';
  }

  @override
  String get onboardingWhatIKnowAboutYouDescription =>
      'Ecco un riepilogo di ciò che so di te dalle nostre conversazioni. Puoi modificare tutto ciò che non è corretto.';

  @override
  String diagnosticsLastDuration(String duration) {
    return 'Ultimi $duration';
  }

  @override
  String get pairingDescLimitless =>
      'Quando una luce è visibile, premi una volta poi tieni premuto finché il dispositivo non mostra una luce rosa, quindi rilascia.';

  @override
  String get chatBlockOpenConversation => 'Apri conversazione';

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '$used di $limit insight ottenuti questo mese';
  }

  @override
  String get connectionErrorDesc =>
      'Impossibile connettersi al server. Controlla la tua connessione internet e riprova.';

  @override
  String get enterWordsCommaSeparated => 'Inserisci parole (separate da virgola)';

  @override
  String get otherDevicesComingSoon => 'Altri dispositivi prossimamente';

  @override
  String speakerSuggestionChip(String name) {
    return '$name?';
  }

  @override
  String get speakerTagPromptNotAPersonToast => 'Segnato come non una persona';

  @override
  String get createKeyToGetStarted => 'Crea una chiave per iniziare';

  @override
  String get captureRecordingSeparateConfirm => 'Separa';

  @override
  String get diagnosticsDrops => 'Interruzioni';

  @override
  String lowBatteryAlertBody(int level) {
    return 'La tua batteria è al $level%. È ora di ricaricare! 🔋';
  }

  @override
  String get deviceOnboardingTurnOffSubtitle => 'Tieni premuto il pulsante per 3 secondi';

  @override
  String get done => 'Fatto';

  @override
  String get wifiConfigurationSubtitle =>
      'Inserisci le credenziali WiFi per consentire al dispositivo di scaricare il firmware.';

  @override
  String get permissionGrantedNow =>
      'Permesso concesso! Ora:\n\nApri l\'app Omi sul tuo watch e tocca \"Continua\" qui sotto';

  @override
  String get setUpPayPal => 'Configura PayPal';

  @override
  String get statusProcessed => 'Elaborato';

  @override
  String phoneFreeCallsRemaining(int remaining, int limit) {
    return '$remaining chiamate gratuite rimaste su $limit questo mese';
  }

  @override
  String get event => 'Evento';

  @override
  String get conversationEvents => 'Eventi conversazione';

  @override
  String get uninstall => 'Disinstalla';

  @override
  String get appCreators => 'Creatori di app';

  @override
  String get muted => 'Disattivato';

  @override
  String get deleteRecapAction => 'Elimina';

  @override
  String get addAppErrorSelectingThumbnailRetry => 'Errore nella selezione della miniatura. Riprova.';

  @override
  String get basicPlanDescription => '300 minuti premium + illimitato sul dispositivo';

  @override
  String get countrySelectionPermanent => 'La selezione del paese è permanente e non può essere modificata in seguito.';

  @override
  String get transcriptionConnecting => 'Connessione trascrizione…';

  @override
  String transcriptionsPendingFraction(int pending, int total) {
    return 'Trascrizioni in attesa $pending/$total';
  }

  @override
  String get apiKeyAuth => 'Autenticazione Chiave API';

  @override
  String downloadModelWithName(String model) {
    return 'Scarica modello ($model)';
  }

  @override
  String get devModeInvalidDaySummaryWebhookUrl => 'URL webhook riepilogo giornaliero non valido';

  @override
  String get memoryReviewSaveFailed => 'Impossibile salvare, riprova';

  @override
  String get payYourSttProvider => 'Gratis in Omi. Paghi direttamente il tuo fornitore di trascrizione.';

  @override
  String get dailySummaryHeader => 'RIEPILOGO GIORNALIERO';

  @override
  String get fairUseStageWarning => 'Avviso';

  @override
  String get multipleSpeakersDesc =>
      'Sembra che ci siano più persone che parlano nella registrazione. Assicurati di essere in un luogo silenzioso e riprova.';

  @override
  String get pastChats => 'Chat precedenti';

  @override
  String get listeningMins => 'Ascolto (min)';

  @override
  String get pairingDescOmi => 'Tieni premuto il dispositivo finché non vibra per accenderlo.';

  @override
  String get deviceOnboardingIntroSubtitle =>
      'Prova la trascrizione dal vivo, fai una domanda e usa la scorciatoia con doppio tocco.';

  @override
  String get autoRemoveSyncedCopiesTitle => 'Rimozione automatica delle copie sincronizzate';

  @override
  String chatAppsReadOnlyFooter(String app) {
    return 'Qui queste chat sono di sola lettura. Rispondi su $app.';
  }

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'Microfono cambiato. Ripresa tra ${countdown}s';
  }

  @override
  String get takePhoto => 'Scatta foto';

  @override
  String get cancelSync => 'Annulla Sincronizzazione';

  @override
  String appSettings(String appName) {
    return 'Impostazioni $appName';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'Impossibile verificare l\'autorizzazione microfono: $error';
  }

  @override
  String get micGain => 'Guadagno Microfono';

  @override
  String get collectingData => 'Raccolta dati…';

  @override
  String get memoryReadOnlyHint => 'Questo ricordo è conservato come cronologia e non può essere modificato.';

  @override
  String get appUnderReviewOwner =>
      'La tua app è in revisione e visibile solo a te. Diventerà pubblica una volta approvata.';

  @override
  String get addNewPerson => 'Aggiungi Nuova Persona';

  @override
  String get nameSpeakerTitle => 'Nomina relatore';

  @override
  String get downloadingAudioFromSdCard => 'Scaricamento audio dalla scheda SD del dispositivo';

  @override
  String get pendantSyncingRecordings => 'Sincronizzazione delle registrazioni dal ciondolo…';

  @override
  String get otaNotSupported => 'Questo firmware non può essere aggiornato tramite Wi-Fi.';

  @override
  String get wrappedSomethingWentWrong => 'Qualcosa è\nandato storto';

  @override
  String get screenRecording => 'Registrazione schermo';

  @override
  String get audioProcessedLocally =>
      'Laudio viene elaborato localmente. Funziona offline, più privato, ma consuma più batteria.';

  @override
  String get onboardingSignIn => 'Accedi';

  @override
  String timeDaysPlural(int count) {
    return '$count giorni';
  }

  @override
  String get memoryReviewTitle => 'Cosa ho imparato oggi';

  @override
  String get hidePassword => 'Nascondi password';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get disconnected => 'Disconnesso';

  @override
  String get revokeApiKeyQuestion => 'Revocare la chiave API?';

  @override
  String get detectBrowserBasedMeetings => 'Rileva riunioni basate sul browser';

  @override
  String get failedToDeleteConversations => 'Impossibile eliminare le conversazioni';

  @override
  String get raybanMetaCapturePhoto => 'Scatta foto';

  @override
  String get bleSpeed => '~30 KB/s via BLE';

  @override
  String get conversationPromptPlaceholder =>
      'Sei un\'app fantastica, ti verrà fornita una trascrizione e un riepilogo di una conversazione…';

  @override
  String get secureAuthViaGoogleAccount => 'Autenticazione sicura tramite account Google';

  @override
  String get omiHas => 'Omi ha:';

  @override
  String get raybanMetaContinue => 'Continua';

  @override
  String get pauseRecording => 'Metti in pausa registrazione';

  @override
  String get evidenceNothing => 'Non l\'hai ancora etichettato né confermato';

  @override
  String get noActivityYet => 'Nessuna Attività Ancora';

  @override
  String get enterPasswordError => 'Inserisci la tua password';

  @override
  String get forgetDeviceConfirmTitle => 'Dimenticare il dispositivo?';

  @override
  String get ratingsAndReviews => 'Valutazioni e recensioni';

  @override
  String get addApiKeyAfterImport => 'Dovrai aggiungere la tua chiave API dopo l\'importazione';

  @override
  String get alreadyOnStableFirmware => 'Sei già sull\'ultima versione stabile.';

  @override
  String get deleteAccountConfirm => 'Sei sicuro di voler eliminare il tuo account?';

  @override
  String get recordingInfo => 'Info registrazione';

  @override
  String get feedbackReasonSummaryInaccurate => 'Non accurato';

  @override
  String get pendantRecordingTitle => 'Registrazione sul ciondolo';

  @override
  String get deleteWhileProcessingMessage =>
      'Questa registrazione è stata caricata ma Omi sta ancora creando la conversazione. Se la elimini ora e l\'elaborazione non riesce, non potrà essere recuperata. Eliminare comunque?';

  @override
  String get createNewKey => 'Crea nuova chiave';

  @override
  String get firmwareDownloadFailedMessage =>
      'Non è stato possibile scaricare l\'aggiornamento e il dispositivo non è stato modificato. Controlla la connessione a internet e riprova.';

  @override
  String get loadingTasks => 'Caricamento attività…';

  @override
  String get previousResult => 'Risultato precedente';

  @override
  String get reviewLoadFailed => 'Impossibile caricare le tue domande.';

  @override
  String get onDevice => 'Sul Dispositivo';

  @override
  String get bluetoothSyncEnabled => 'Sincronizzazione Bluetooth abilitata';

  @override
  String get categorySafety => 'Sicurezza';

  @override
  String get unknownLocation => 'Posizione sconosciuta';

  @override
  String get newMemoryTitle => 'Nuovo ricordo';

  @override
  String get conversationCannotBeMerged =>
      'Questa conversazione non può essere unita (bloccata o già in fase di unione)';

  @override
  String get summaryGenerated => 'Riepilogo generato';

  @override
  String get createKey => 'Crea Chiave';

  @override
  String get letOmiChooseAutomatically => 'Lascia che Omi scelga automaticamente l\'app migliore';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'Riavvia il tuo $deviceName per completare l\'aggiornamento.';
  }

  @override
  String get goals => 'Obiettivi';

  @override
  String get wrappedAnErrorOccurred => 'Si è verificato un errore';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'Verifica autorizzazione microfono fallita: $error';
  }

  @override
  String get connectLater => 'Connetti Più Tardi';

  @override
  String get wrappedRememberedByOmi => 'ricordato da Omi';

  @override
  String get fairUseStatusNormal => 'Il tuo utilizzo è entro i limiti normali.';

  @override
  String get includePersonalEventsDescription => 'Includi eventi personali senza partecipanti';

  @override
  String get week => 'Settimana';

  @override
  String get willLikelyCrash => 'Abilitare questo probabilmente causerà il crash o il blocco dellapp.';

  @override
  String get selectPrimaryLanguage => 'Seleziona la tua lingua principale';

  @override
  String get pilotFeaturesDescription => 'Queste funzionalità sono test e non è garantito il supporto.';

  @override
  String get askOmi => 'Chiedi a Omi';

  @override
  String get ifYouCancel => 'Se annulli:';

  @override
  String get audioOutput => 'Uscita audio';

  @override
  String get memoryReviewWrong => 'Sbagliato';

  @override
  String get couldNotSchedulePlanChange => 'Impossibile programmare il cambio di piano. Riprova.';

  @override
  String speakerLabelEarlierMatches(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Trovata in $count conversazioni precedenti',
      one: 'Trovata in 1 conversazione precedente',
    );
    return '$_temp0';
  }

  @override
  String get deviceOnboardingListening => 'In ascolto…';

  @override
  String get speechProfileEnrollmentPrompt =>
      'Perché Omi sappia qual è la tua voce — parla di qualsiasi cosa per circa 5 secondi.';

  @override
  String get mcpServerUrl => 'MCP Server URL';

  @override
  String get chatBlockMemory => 'Ricordo';

  @override
  String get noStarredConversations => 'Nessuna conversazione con stella';

  @override
  String get syncStatusTooOld => 'Troppo vecchia per la sincronizzazione — Omi non può accettarla';

  @override
  String connectedAsUser(String userId) {
    return 'Connesso come utente: $userId';
  }

  @override
  String get phonePageTitle => 'Telefono';

  @override
  String get buildGraphButton => 'Costruisci grafo';

  @override
  String get issuesCreatedInRepo => 'Le issue saranno create nel tuo repository predefinito';

  @override
  String get scopeUserFacts => 'Informazioni utente';

  @override
  String get unableToLoadPlans => 'Impossibile caricare i piani';

  @override
  String get deleteRecording => 'Elimina Registrazione';

  @override
  String get appDeleteFailed => 'Impossibile eliminare l\'app. Riprova più tardi.';

  @override
  String get addAppUpdatedSuccess => 'App aggiornata con successo 🚀';

  @override
  String get reviewCaughtUpTitle => 'Niente a cui rispondere';

  @override
  String get copyConversationId => 'Copia ID conversazione';

  @override
  String get helpImproveOmiBySharing => 'Aiuta a migliorare Omi condividendo dati analitici anonimi';

  @override
  String get dataEncryptedBanner =>
      'I tuoi dati sono protetti per impostazione predefinita con una crittografia avanzata, e sei tu a controllare come vengono archiviati e utilizzati.';

  @override
  String get redo => 'Registra di nuovo';

  @override
  String get updateOmiGlassFirmware => 'Aggiorna firmware OmiGlass';

  @override
  String get deviceUnpairedMessage =>
      'Dispositivo disaccoppiato. Vai in Impostazioni > Bluetooth e dimentica il dispositivo per completare il disaccoppiamento.';

  @override
  String speakerLabelText(String part, String name) {
    String _temp0 = intl.Intl.selectLogic(
      part,
      {
        'likely': 'Probabile',
        'soundsLike': 'Somiglia a $name',
        'notPerson': 'Non è $name',
        'carried': 'È ancora $name. Riportato dalla tua ultima conversazione.',
        'change': 'Cambia',
        'alsoTitle': 'È anche $name?',
        'alsoBody': 'Omi ha trovato la stessa voce in conversazioni precedenti.',
        'confirmed': 'Hai confermato questa etichetta',
        'other': 'Rivedi',
      },
    );
    return '$_temp0';
  }

  @override
  String get continueWithApple => 'Continua con Apple';

  @override
  String get iUnderstand => 'Ho capito';

  @override
  String get memoryProvenanceAndroid => 'Android';

  @override
  String get saving => 'Salvataggio…';

  @override
  String get deviceOnboardingDoubleTapTitle => 'Personalizza il doppio tocco';

  @override
  String get allMemoriesPublicResult => 'Tutti i ricordi sono ora pubblici';

  @override
  String get chatAppsAddToContacts => 'Aggiungi Omi ai contatti';

  @override
  String get wrappedDays => 'giorni';

  @override
  String get invalidJsonError => 'JSON non valido';

  @override
  String syncCardNeedsAttention(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count registrazioni richiedono attenzione',
      one: '1 registrazione richiede attenzione',
    );
    return '$_temp0';
  }

  @override
  String get wrappedSwipeUpToBegin => 'Scorri verso l\'alto per iniziare';

  @override
  String addedToService(String serviceName) {
    return 'Aggiunto a $serviceName';
  }

  @override
  String get advanced => 'Avanzate';

  @override
  String get autoCreateAndTagNewSpeakers => 'Crea e etichetta automaticamente nuovi parlanti';

  @override
  String get appCapabilities => 'Capacità dell\'App';

  @override
  String get onboardingMicrophoneDenied =>
      'Autorizzazione microfono negata. Concedi l\'autorizzazione in Preferenze di Sistema > Privacy e sicurezza > Microfono.';

  @override
  String get pleaseEnterFolderName => 'Inserisci un nome per la cartella';

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'Impossibile verificare l\'autorizzazione Bluetooth: $error';
  }

  @override
  String get invalidRecordingDetected => 'Rilevata registrazione non valida';

  @override
  String get appAnalytics => 'Analisi dell\'app';

  @override
  String get captureRecordingsSheetTitle => 'Registrazioni di questa conversazione';

  @override
  String deletedLimitlessConversations(int count) {
    return 'Eliminate $count conversazioni Limitless';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'Errore nella selezione dell\'immagine: $error';
  }

  @override
  String get unnamedSpeakerLabel => 'Relatore';

  @override
  String get failedToCreateApp => 'Impossibile creare l\'app. Riprova.';

  @override
  String get planUpdate => 'Aggiornamento del piano';

  @override
  String get timeout5Minutes => '5 minuti';

  @override
  String get deleteSample => 'Elimina campione';

  @override
  String get willNotSeeAgain => 'Non potrai vederla di nuovo.';

  @override
  String get thisMonth => 'Questo Mese';

  @override
  String get enterName => 'Inserisci il nome';

  @override
  String get memoryThisDevice => 'Questo dispositivo';

  @override
  String get verifiedNumbersDescription => 'Quando chiami qualcuno, vedra questo numero';

  @override
  String get deviceOnboardingSingleTapHint => 'Era un tocco singolo: prova a toccare due volte rapidamente!';

  @override
  String autoClosingInSeconds(int seconds) {
    return 'Chiusura automatica tra $seconds secondi';
  }

  @override
  String get chatAppsProPerkContext => 'Omi ricorda il contesto in ogni app';

  @override
  String get errorProcessingConversation => 'Errore durante l\'elaborazione della conversazione. Riprova più tardi.';

  @override
  String get profileSettings => 'Impostazioni del profilo';

  @override
  String get statusUnprocessed => 'Non elaborato';

  @override
  String get deleteConversationMessage => 'Questo eliminerà anche i ricordi, le attività e i file audio associati.';

  @override
  String get cancelSubscriptionQuestion => 'Annullare l\'abbonamento?';

  @override
  String get forUnlimitedFreeTranscription => 'per trascrizione gratuita illimitata.';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used di $limit min utilizzati';
  }

  @override
  String get categoryPersonalWellness => 'Benessere personale';

  @override
  String get automaticTranslation => 'Traduzione Automatica';

  @override
  String get defaultAiAssistant => 'Assistente AI predefinito';

  @override
  String get allDataErased => 'I tuoi ricordi e le tue conversazioni verranno cancellati.';

  @override
  String entityDue(String date) {
    return 'Scadenza $date';
  }

  @override
  String get feedbackChatWithUs => 'Più dettagli? Scrivici';

  @override
  String get speakerTagPromptSomeoneNew => 'Qualcuno di nuovo';

  @override
  String get inProgress => 'In corso';

  @override
  String get raybanMetaCheckAgain => 'Controlla di nuovo';

  @override
  String get fairUseStageNormal => 'Normale';

  @override
  String get pairingTitleLimitless => 'Metti Limitless in modalità di accoppiamento';

  @override
  String get usingNativeIosSpeech => 'Utilizzo del riconoscimento vocale nativo iOS';

  @override
  String get actionItemDeletedSuccessfully => 'Attività eliminata con successo';

  @override
  String get failedToSetLanguage => 'Impossibile impostare la lingua';

  @override
  String get appHomeUrl => 'URL della home dell\'app';

  @override
  String get appNameLabel => 'Nome dell\'app';

  @override
  String get localStorageDisabled => 'Archiviazione locale disabilitata';

  @override
  String get appReEnable => 'Riattiva';

  @override
  String get migrationFailed => 'Migrazione fallita';

  @override
  String get markComplete => 'Segna come completato';

  @override
  String get lastUsedLabel => 'Ultimo utilizzo';

  @override
  String get chatCleared => 'Chat cancellata';

  @override
  String get revokeApiKeyWarning =>
      'Le app che usano questa chiave perderanno l\'accesso all\'API. Questa azione non può essere annullata.';

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return 'Impossibile verificare l\'autorizzazione cattura schermo: $error';
  }

  @override
  String get troubleshootingSteps =>
      'Risoluzione problemi:\n\n1. Assicurati che Omi sia installato sul tuo watch\n2. Apri l\'app Omi sul tuo watch\n3. Cerca il popup di permesso\n4. Tocca \"Consenti\" quando richiesto\n5. L\'app sul watch si chiuderà - riaprila\n6. Torna e tocca \"Continua\" sul tuo iPhone';

  @override
  String get location => 'Posizione';

  @override
  String get chatAppsWhatsAppMeantime =>
      'Telegram e iMessage funzionano già, con gli stessi ricordi e le stesse attività.';

  @override
  String get sliderOff => 'Off';

  @override
  String get checkingFirmwareVersion => 'Controllo versione firmware…';

  @override
  String get reviewUnknownSpeaker => 'Interlocutore sconosciuto';

  @override
  String get professionSales => 'Vendite';

  @override
  String get noRssiDataYet => 'Nessun dato RSSI ancora';

  @override
  String get emptyOldMessage => '✅ Nessuna attività vecchia';

  @override
  String deleteSampleConfirmation(String name) {
    return 'Il campione vocale di $name verrà rimosso. Questa azione non può essere annullata.';
  }

  @override
  String get saveUrlButton => 'Salva URL';

  @override
  String get onboardingNotificationDeniedSystemPrefs =>
      'Autorizzazione notifiche negata. Concedi l\'autorizzazione in Preferenze di Sistema.';

  @override
  String get languageForTranscription => 'Omi usa questa lingua per trascrizioni, riepiloghi e ricordi.';

  @override
  String get updatedLabel => 'AGGIORNATO';

  @override
  String get content => 'Contenuto';

  @override
  String get phoneCallButton => 'Chiama';

  @override
  String get exportStartedMayTakeFewSeconds => 'Esportazione avviata. Potrebbe richiedere qualche secondo…';

  @override
  String dreamReportPrivacyHeld(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count segnalazioni trattenute per privacy',
      one: '1 segnalazione trattenuta per privacy',
    );
    return '$_temp0';
  }

  @override
  String firmwareBatteryTooLow(int level) {
    return 'La batteria è al $level%. Carica il dispositivo almeno al 15% prima di aggiornarlo.';
  }

  @override
  String get appearance => 'Aspetto';

  @override
  String noTasksOnDate(Object date) {
    return 'Nessuna attività il $date';
  }

  @override
  String get deleteFlowFeedbackHint => 'Facoltativo — le tue idee ci aiutano a costruire un prodotto migliore.';

  @override
  String get bluetooth => 'Bluetooth';

  @override
  String get cancelUpdate => 'Annulla aggiornamento';

  @override
  String get syncStatusConversationCreated => 'Conversazione creata';

  @override
  String get reconnecting => 'Riconnessione…';

  @override
  String get tasksToday => 'Oggi';

  @override
  String taskCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count attività',
      one: '1 attività',
    );
    return '$_temp0';
  }

  @override
  String get noUpcomingMeetings => 'Nessuna riunione imminente';

  @override
  String get invalidRecordingMultipleSpeakers => 'Registrazione non valida rilevata';

  @override
  String get startupFailedTitle => 'Omi non è riuscita ad avviarsi';

  @override
  String contactsSelectedCount(int count) {
    return '$count selezionati';
  }

  @override
  String get skipForward10Seconds => 'Avanti di 10 secondi';

  @override
  String get noItems => 'Nessun elemento';

  @override
  String get timeout30Minutes => '30 minuti';

  @override
  String get signInSuccess => 'Accesso riuscito!';

  @override
  String get syncStatusDownloadingFromDevice => 'Download dal tuo dispositivo';

  @override
  String get makePrivate => 'Rendi privato';

  @override
  String get update => 'Aggiorna';

  @override
  String get aiGenCreatingAppIcon => 'Creazione icona dell\'app…';

  @override
  String get wrappedIntenseDay => 'Intenso';

  @override
  String get raybanMetaSkipForNow => 'Salta per ora';

  @override
  String diagnosticsReconnectedIn(String duration) {
    return 'riconnesso in $duration';
  }

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'Stai passando dal tuo Piano Illimitato al $title.';
  }

  @override
  String get appsAskWith => 'Chiedi a Omi con';

  @override
  String get noMemoriesFound => 'Nessun ricordo trovato';

  @override
  String get noMemoriesYet => 'Nessun ricordo ancora';

  @override
  String get captureRecordingSeparateFailed => 'Impossibile separare. Riprova.';

  @override
  String get pinAsBaseline => 'Fissa come base';

  @override
  String get voiceRecognitionSettings => 'Riconoscimento Vocale';

  @override
  String get chatAppsComingLater => 'In arrivo più avanti';

  @override
  String get sliderMax => 'Max.';

  @override
  String get deleteWhileProcessingTitle => 'Ancora in elaborazione';

  @override
  String get devModeSettingsSaved => 'Impostazioni salvate!';

  @override
  String get fairUseToday => 'Oggi';

  @override
  String get exportDataDesc => 'Esporta conversazioni in un file JSON';

  @override
  String get whatsYourName => 'Come ti chiami?';

  @override
  String get onDeviceSlower => 'La trascrizione su dispositivo potrebbe essere più lenta su questo dispositivo.';

  @override
  String get categoryProductivityLifestyle => 'Produttività e stile di vita';

  @override
  String get addToYourTaskList => 'Aggiungere alla lista delle attività?';

  @override
  String get meetingScreenshotFallbackCaption => 'Screenshot di questa riunione';

  @override
  String get effectCountsALittle => 'Aiuta poco';

  @override
  String get pairingTitleFriendPendant => 'Metti Friend Pendant in modalità di accoppiamento';

  @override
  String get peopleStatsIncomplete => 'I conteggi potrebbero essere incompleti.';

  @override
  String get tapToAddGoal => 'Tocca per aggiungere un obiettivo';

  @override
  String get payment => 'Pagamento';

  @override
  String get omiDebugLog => 'Log di debug Omi';

  @override
  String get showMeetingsMenuBar => 'Mostra riunioni imminenti nella barra dei menu';

  @override
  String get mostInstalls => 'Più installazioni';

  @override
  String chatUsageMessages(String used, String limit) {
    return 'Chat: $used / $limit messaggi questo mese';
  }

  @override
  String get chat => 'Chat';

  @override
  String get areYouThere => 'Ci sei?';

  @override
  String get highestRating => 'Valutazione più alta';

  @override
  String get pleaseSpecify => 'Specifica';

  @override
  String get staging => 'Staging';

  @override
  String get cancelReasonBatteryDrain => 'Preoccupazioni per il consumo batteria';

  @override
  String get apiKeys => 'Chiavi API';

  @override
  String conversationsCreated(int count) {
    return '$count conversazioni create';
  }

  @override
  String get trainingDataProgram => 'Programma dati di formazione';

  @override
  String get customBackendUrlTitle => 'URL del server personalizzato';

  @override
  String get omiSyncsAudioFiles => 'Omi sincronizza quindi i file audio con il server';

  @override
  String get reviewAnswerMe => 'Io';

  @override
  String get debugDiagnostics => 'Debug e Diagnostica';

  @override
  String get confidenceReasonNotHeard => 'non ancora sentito';

  @override
  String get doubleTapAction => 'Azione Doppio Tocco';

  @override
  String get showTasksOnHomepage => 'Mostra attività nella homepage';

  @override
  String failedToStartUpdate(String error) {
    return 'Impossibile avviare l\'aggiornamento: $error';
  }

  @override
  String get feedbackReasonSummaryWrongContext => 'Contesto sbagliato';

  @override
  String get pleaseProvideValidDescription => 'Fornisci una descrizione valida';

  @override
  String get appRejectedNotice =>
      'La tua app è stata rifiutata. Aggiorna i dettagli dell\'app e inviala nuovamente per la revisione.';

  @override
  String get deleteOnDeviceModel => 'Elimina modello';

  @override
  String get languageSettingsHelperText =>
      'La lingua dell\'app modifica menu e pulsanti. La lingua principale influisce su come vengono trascritte le tue registrazioni.';

  @override
  String get deleteConversationsMessage => 'Verranno eliminati anche i relativi ricordi, attività e file audio.';

  @override
  String get usageBestMonth => 'Best month';

  @override
  String get creating => 'Creazione…';

  @override
  String get microphoneAccessDescription =>
      'Omi ha bisogno dell\'accesso al microfono per registrare le tue conversazioni e fornire trascrizioni.';

  @override
  String get cancelReasonNotUsing => 'Non lo uso abbastanza';

  @override
  String get wrappedWeveAllBeenThere => 'Ci siamo passati tutti!';

  @override
  String get chatAppsProblemRateLimited => 'Troppi tentativi. Attendi un minuto e riprova.';

  @override
  String get selectOption => 'Seleziona';

  @override
  String get languageBenefits => 'Omi usa questa lingua per trascrizioni, riepiloghi e ricordi.';

  @override
  String get triggerConversationIntegration => 'Attiva integrazione creazione conversazione';

  @override
  String get integrationSetupRequired =>
      'Se questa è un\'app di integrazione, assicurati che la configurazione sia completata.';

  @override
  String get clickPlayToResumeOrStop => 'Fai clic su riproduci per riprendere o ferma per terminare';

  @override
  String disconnectedFrom(String appName) {
    return 'Disconnesso da $appName';
  }

  @override
  String get subscribe => 'Abbonati';

  @override
  String get permissionsChangeAnytime => 'Puoi modificarle in qualsiasi momento in Impostazioni > Autorizzazioni';

  @override
  String get enableRemindersAccess =>
      'Abilita l\'accesso ai Promemoria nelle Impostazioni per utilizzare Promemoria Apple';

  @override
  String get selectProviderTemplate => 'Seleziona un modello provider…';

  @override
  String get initialisingSystemAudio => 'Inizializzazione audio di sistema';

  @override
  String get excellent => 'Eccellente';

  @override
  String get chatBlockGoal => 'Obiettivo';

  @override
  String get deleteFolder => 'Elimina cartella';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'Impossibile creare la chiave: $error';
  }

  @override
  String get whisperModelSizeSmall => 'Piccolo';

  @override
  String get pleaseCopyKeyNow => 'Per favore copiala ora e annotala in un posto sicuro. ';

  @override
  String get unresolvedSpeakersNotice =>
      'Le etichette degli speaker potrebbero non corrispondere tra le registrazioni di questa conversazione.';

  @override
  String get omisMemoryCleared => 'La memoria di Omi su di te è stata cancellata';

  @override
  String get manageApp => 'Gestisci app';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return 'Stato autorizzazione cattura schermo: $status. Controlla Preferenze di Sistema.';
  }

  @override
  String get edit => 'Modifica';

  @override
  String get redownload => 'Riscarica';

  @override
  String get chatBlockConversation => 'Conversazione';

  @override
  String get loadingApps => 'Caricamento app…';

  @override
  String get chatPromptPlaceholder =>
      'Sei un\'app fantastica, il tuo compito è rispondere alle domande degli utenti e farli sentire bene…';

  @override
  String get stripeConnectedAccountAgreement => 'Accordo Account Connesso Stripe';

  @override
  String get autoSync => 'Sincronizzazione automatica';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'Grafo della conoscenza eliminato con successo';

  @override
  String get optInAndOptOutOptions => 'Opzioni di adesione e rinuncia';

  @override
  String get permissionReadMemories => 'Leggi ricordi';

  @override
  String get noSpacesInWorkspace => 'Nessuno spazio trovato in quest\'area di lavoro';

  @override
  String get reviewYesMerge => 'Sì, unisci';

  @override
  String get voiceMode => 'Modalità vocale';

  @override
  String get fairUseStageThrottle => 'Limitato';

  @override
  String get deleteChatQuestion => 'Eliminare questa chat?';

  @override
  String get failedToGetCallToken => 'Impossibile ottenere il token. Verifica prima il tuo numero.';

  @override
  String get selectTime => 'Seleziona orario';

  @override
  String get sdCardProcessing => 'Elaborazione Scheda SD';

  @override
  String errorConnectingRayBanMeta(String error) {
    return 'Errore di connessione a Ray-Ban Meta: $error';
  }

  @override
  String get couldNotLoadImportHistory => 'Impossibile caricare la cronologia delle importazioni';

  @override
  String get noApiKeysFound => 'Nessuna chiave API trovata. Creane una per iniziare.';

  @override
  String get appDisabledTitle => 'Questa app è disattivata e non può essere installata.';

  @override
  String get syncStatusBackedUp => 'Backup eseguito';

  @override
  String get speakerTagPromptThatsMeAction => 'Sono io';

  @override
  String timeCompactHoursAndMins(int hours, int mins) {
    return '${hours}h ${mins}m';
  }

  @override
  String get chatPrompt => 'Prompt Chat';

  @override
  String get voicePreviewSample => 'Ciao, sono Omi. Questa è la mia voce.';

  @override
  String get saved => 'Salvato';

  @override
  String get grantPermissionButton => 'Concedi Permesso';

  @override
  String get subscription => 'Abbonamento';

  @override
  String get capabilityFeatured => 'In evidenza';

  @override
  String get pdfConversationExport => 'Esportazione conversazione';

  @override
  String get unknown => 'Sconosciuto';

  @override
  String get yourMeetings => 'Le Tue Riunioni';

  @override
  String get uploadingVoiceProfile => 'Caricamento del tuo profilo vocale….';

  @override
  String get apiUrl => 'URL API';

  @override
  String get reportMessage => 'Segnala messaggio';

  @override
  String get passwordLabel => 'Password';

  @override
  String get permanentlyRemoveAllMemories => 'Rimuovi permanentemente tutti i ricordi da Omi';

  @override
  String get transcriptionSlowerLessAccurate => 'La trascrizione sarà significativamente più lenta e meno accurata.';

  @override
  String get filterManual => 'Manuale';

  @override
  String get keepMyPlan => 'Mantieni il mio piano';

  @override
  String get setupQuestionAge => '3. Quanti anni hai?';

  @override
  String get addAppSelectTriggerEvent => 'Seleziona un evento trigger per la tua app';

  @override
  String get defaultWorkspace => 'Area di Lavoro Predefinita';

  @override
  String get errorUpdatingAppStatus => 'Si è verificato un errore durante l\'aggiornamento dello stato dell\'app.';

  @override
  String get invalidJsonConfig => 'Configurazione JSON non valida';

  @override
  String get detailedDiagnosticMessages => 'Messaggi diagnostici dettagliati';

  @override
  String get mergingInBackground => 'Unione in background. Potrebbe richiedere un momento.';

  @override
  String get setDefaultApp => 'Imposta app predefinita';

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Dovrai autorizzare Omi a creare attività nel tuo account $appName. Questo aprirà il tuo browser per l\'autenticazione.';
  }

  @override
  String get cleanUpEllipsis => 'Riordina…';

  @override
  String get addTask => 'Aggiungi attività';

  @override
  String get getCreative => 'Sii creativo';

  @override
  String get captureRecordingOpenFailed => 'Impossibile aprire questa registrazione.';

  @override
  String get emptyTodoMessage => '🎉 Tutto a posto!\nNessuna attività in sospeso';

  @override
  String get onboardingSetupTitle => 'Configurazione del tuo Omi';

  @override
  String get sharePeriodAllTime => 'Finora, Omi ha:';

  @override
  String get translationNotice => 'Avviso di traduzione';

  @override
  String captureRecordingError(String error) {
    return 'Si è verificato un errore durante la registrazione: $error';
  }

  @override
  String get downloadAudio => 'Scarica audio';

  @override
  String get identifySpeaker => 'Identifica chi parla';

  @override
  String get viewTranscript => 'Visualizza trascrizione';

  @override
  String get makeAllMemoriesPublic => 'Rendi tutti i ricordi pubblici';

  @override
  String get xTwitter => 'X (Twitter)';

  @override
  String get frequencyOff => 'Disattivato';

  @override
  String get apiEnvironment => 'Ambiente API';

  @override
  String get processingTakingLonger => 'Ancora in corso: ci sta mettendo più del solito.';

  @override
  String get firmwareUpdateFailedTitle => 'Aggiornamento non riuscito';

  @override
  String get unresolvedQuestions => 'Domande irrisolte';

  @override
  String get chatAppsMessage => 'Messaggio';

  @override
  String get dreamReportManual => 'Manuale';

  @override
  String get enterSttHttpEndpoint => 'Inserisci il tuo endpoint HTTP STT';

  @override
  String get beforeUpdateMakeSure => 'Prima dell\'aggiornamento, assicurati:';

  @override
  String get transcriptionReconnecting => 'Riconnessione trascrizione…';

  @override
  String get deviceName => 'Nome Dispositivo';

  @override
  String neoSubtitle(int count) {
    return '$count domande al mese';
  }

  @override
  String chatUsageProgress(String used, String limit) {
    return '$used / $limit utilizzati';
  }

  @override
  String get noChangesInReview => 'Nessuna modifica nella recensione da aggiornare.';

  @override
  String get allMemories => 'Tutti i ricordi';

  @override
  String get needMicrophonePermission =>
      'Abbiamo bisogno del permesso microfono.\n\n1. Tocca \"Concedi Permesso\"\n2. Consenti sul tuo iPhone\n3. L\'app Watch si chiuderà\n4. Riaprila e tocca \"Continua\"';

  @override
  String get keepSpeakingUntil100 => 'Continua a parlare fino al 100%.';

  @override
  String get singleLanguageModeInfo =>
      'Modalità Lingua Singola attivata. La traduzione è disabilitata per una maggiore precisione.';

  @override
  String get thisCannotBeUndone => 'Questa azione non può essere annullata.';

  @override
  String get setupSkipHelp => 'Salta, non voglio aiutare :C';

  @override
  String get speakerTagPromptNoAction => 'No…';

  @override
  String labelCopied(String label) {
    return '$label copiato';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'Errore durante il cambio del dispositivo audio: $error';
  }

  @override
  String get remembering => 'Ricordare';

  @override
  String get externalAppAccessDescription =>
      'Le seguenti app installate hanno integrazioni esterne e possono accedere ai tuoi dati, come conversazioni e ricordi.';

  @override
  String get preferences => 'Preferenze';

  @override
  String get wrappedFunDay => 'Divertente';

  @override
  String get effectNeeded => 'Necessario per Confermato';

  @override
  String get importantConversationBody =>
      'Hai appena avuto una conversazione importante. Tocca per condividere il riepilogo.';

  @override
  String whyConfidenceMenu(String level) {
    return 'Perché $level?';
  }

  @override
  String get cmdRequired => '⌘ richiesto';

  @override
  String get completed => 'Completato';

  @override
  String get deviceOnboardingVoiceReplyStatusAlwaysSpeaker =>
      'Viene riprodotto ad alta voce attraverso l\'altoparlante del telefono.';

  @override
  String get effectCountsAgainst => 'Penalizza';

  @override
  String get recaps => 'Riepiloghi';

  @override
  String get shareConversationQuestion => 'Condividere la conversazione?';

  @override
  String get actionItemsCopiedToClipboard => 'Attività copiate negli appunti';

  @override
  String get appleHealthManageNote =>
      'Omi accede ad Apple Health tramite il framework HealthKit di Apple. Puoi revocare l\'accesso in qualsiasi momento dalle Impostazioni iOS.';

  @override
  String addingToService(String serviceName) {
    return 'Aggiunta a $serviceName…';
  }

  @override
  String get needHelpGettingStarted => 'Hai bisogno di aiuto per iniziare?';

  @override
  String get thanksForAuthorizing => 'Grazie per aver autorizzato!';

  @override
  String get assistantVoiceSettingsTitle => 'Voce';

  @override
  String get cloudStorageDisabled => 'Archiviazione cloud disabilitata';

  @override
  String get reviewPlayClip => 'Riproduci clip';

  @override
  String get storeAudioOnCloud => 'Archivia audio nel cloud';

  @override
  String get syncStatusBackingUp => 'Sincronizzazione…';

  @override
  String get peopleFilterPinned => 'Fissate';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName impostata come app di riepilogo predefinita';
  }

  @override
  String get githubRepositoryUrlRequired => 'L\'URL del repository GitHub è obbligatorio';

  @override
  String get microphoneAccess => 'Accesso al microfono';

  @override
  String get cancelSubscriptionButton => 'Annulla abbonamento';

  @override
  String get signal => 'Segnale';

  @override
  String get failedToConnectAsanaRetry => 'Connessione ad Asana non riuscita. Riprova.';

  @override
  String get keyCreatedMessage => 'La tua nuova chiave è stata creata. Copiala ora. Non potrai vederla di nuovo.';

  @override
  String autoRemoveSyncedCopiesDays(int days) {
    return 'Le copie sincronizzate vengono eliminate dopo $days giorni';
  }

  @override
  String get wrappedMostCringeMoment => 'Più imbarazzante';

  @override
  String get activity => 'Attività';

  @override
  String get calendarSettings => 'Impostazioni calendario';

  @override
  String get additionalFeedbackOptional => 'Feedback aggiuntivo (facoltativo)';

  @override
  String get phoneAllow => 'Consenti';

  @override
  String get noDeviceConnectedUseMic => 'Nessun dispositivo connesso. Verrà utilizzato il microfono del telefono.';

  @override
  String get stripeOnboardingInstructions =>
      'Completa il processo di onboarding Stripe nel tuo browser. Questa pagina si aggiornerà automaticamente una volta completato.';

  @override
  String availableSpaceWithValue(String space) {
    return 'Spazio disponibile: $space';
  }

  @override
  String get conversationDetails => 'Dettagli conversazione';

  @override
  String get wrappedYouHadFunnyMoments => 'Hai avuto momenti divertenti quest\'anno!';

  @override
  String get actionReadConversations => 'Leggi conversazioni';

  @override
  String speakerTagPromptIsThisPerson(String name) {
    return 'È $name?';
  }

  @override
  String get openSettings => 'Apri Impostazioni';

  @override
  String get alwaysAvailable => 'sempre disponibile.';

  @override
  String get rating1PlusStars => '1+ stella';

  @override
  String get pauseResume => 'Pausa/Riprendi';

  @override
  String get conversationDeleted => 'Conversazione eliminata';

  @override
  String get memoryReviewRight => 'Giusto';

  @override
  String get deleteGoal => 'Elimina obiettivo';

  @override
  String get youtube => 'YouTube';

  @override
  String get untitledConversation => 'Conversazione senza titolo';

  @override
  String get yourOmiInsights => 'Le Tue Statistiche Omi';

  @override
  String get compareTranscripts => 'Confronta trascrizioni';

  @override
  String get pause => 'Pausa';

  @override
  String get successfullyConnectedGoogle => 'Connesso con successo a Google!';

  @override
  String planRenewsOn(String date) {
    return 'Il tuo piano si rinnova il $date.';
  }

  @override
  String chatAppsOpenApp(String app) {
    return 'Apri $app';
  }

  @override
  String get dailySummaryDescription =>
      'Ricevi un riepilogo personalizzato delle conversazioni della giornata come notifica.';

  @override
  String conversationPhotosCount(int count) {
    return '$count foto';
  }

  @override
  String get errorLoadingAudio => 'Errore nel caricamento dell\'audio';

  @override
  String get couldNotAccessFile => 'Impossibile accedere al file selezionato';

  @override
  String deleteGraphFailed(String error) {
    return 'Impossibile eliminare il grafo: $error';
  }

  @override
  String get reviewOpenDetailsHint => 'Apre i dettagli';

  @override
  String get conversationTimeoutDesc =>
      'Scegli quanto tempo attendere in silenzio prima di terminare automaticamente una conversazione:';

  @override
  String get transcriptionJsonPlaceholder => 'Incolla la tua configurazione JSON qui…';

  @override
  String get loadingCapabilities => 'Caricamento delle funzionalità…';

  @override
  String get activeStatus => 'Attivo';

  @override
  String get noDailyRecapsYet => 'Nessun riepilogo giornaliero ancora';

  @override
  String get wouldLikePermission => 'Vorremmo il tuo permesso per salvare le tue registrazioni vocali. Ecco perché:';

  @override
  String get chatBlockRecommendedNextSteps => 'Prossimi passi consigliati';

  @override
  String get tryAdjustingSearchTerms => 'Prova a modificare i termini di ricerca';

  @override
  String get connectOmiWithAI => 'Collega Omi con assistenti IA';

  @override
  String get whenToReceiveDailySummary => 'Quando ricevere il riepilogo giornaliero';

  @override
  String syncCardReadyCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count registrazioni pronte da sincronizzare',
      one: '1 registrazione pronta da sincronizzare',
    );
    return '$_temp0';
  }

  @override
  String get yourApiKey => 'LA TUA CHIAVE API';

  @override
  String failedToLoadRepos(String error) {
    return 'Impossibile caricare i repository: $error';
  }

  @override
  String get syncingMessages => 'Sincronizzazione messaggi con il server…';

  @override
  String get pleaseSelectARating => 'Seleziona una valutazione';

  @override
  String get suggestedTemplates => 'Modelli suggeriti';

  @override
  String get updateAppQuestion => 'Aggiornare l\'app?';

  @override
  String get frequencyDescOff => 'Nessuna notifica proattiva';

  @override
  String get triggerAudioBytes => 'Byte audio';

  @override
  String get confirmClearChat => 'Cancellare questa chat? Questa azione non può essere annullata.';

  @override
  String get dataPrivacy => 'Privacy dei Dati';

  @override
  String get audioFromOmiWillAppearHere => 'L\'audio dal tuo dispositivo Omi apparirà qui';

  @override
  String get durationLabel => 'Durata';

  @override
  String get deviceOnboardingAllSetTitle => 'È tutto pronto';

  @override
  String msgSelectImagesError(String error) {
    return 'Errore nella selezione delle immagini: $error';
  }

  @override
  String evidenceCardPicks(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Scelto in $count suggerimenti',
      one: 'Scelto in 1 suggerimento',
    );
    return '$_temp0';
  }

  @override
  String get connectionLostDesc =>
      'La connessione è stata interrotta. Controlla la tua connessione internet e riprova.';

  @override
  String get defaultLabel => 'Predefinito';

  @override
  String get raybanMetaAllowCamera => 'Consenti la fotocamera sugli occhiali';

  @override
  String get addAppSelectCoreCapability => 'Seleziona un\'altra capacità principale per la tua app';

  @override
  String get noManualMemories => 'Nessun ricordo manuale ancora';

  @override
  String get deliveryTime => 'Orario di consegna';

  @override
  String get defaultProjectOptional => 'Progetto Predefinito (Facoltativo)';

  @override
  String get devModeInvalidAudioBytesWebhookUrl => 'URL webhook byte audio non valido';

  @override
  String get ignoredVoicesTitle => 'Voci ignorate';

  @override
  String get refreshManifest => 'Aggiorna manifest';

  @override
  String get diagnosticsRightNow => 'Adesso';

  @override
  String get reviewDue => 'Scadenza';

  @override
  String get unmute => 'Riattiva audio';

  @override
  String get recordingsDeleted => 'Registrazioni eliminate.';

  @override
  String get failedToDeleteFolder => 'Impossibile eliminare la cartella';

  @override
  String get reviewAnswerOther => 'Altro';

  @override
  String get exportedConversations => 'Conversazioni Esportate da Omi';

  @override
  String get privacyPolicy => 'Politica sulla Privacy';

  @override
  String get editReply => 'Modifica risposta';

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription ed è $triggerDescription.';
  }

  @override
  String errorSaving(String error) {
    return 'Errore durante il salvataggio: $error';
  }

  @override
  String get diagnosticsConnectedFor => 'Connesso da';

  @override
  String get callStateConnecting => 'Connessione…';

  @override
  String get conversationUrlNotShared => 'L\'URL della conversazione non può essere condiviso.';

  @override
  String get tooShortDesc => 'Non è stato rilevato abbastanza parlato. Parla di più e riprova.';

  @override
  String get failedToShareRecap => 'Impossibile condividere il riepilogo';

  @override
  String get billingMonthly => 'Mensile';

  @override
  String get developingLogic => 'Sviluppo logica';

  @override
  String get phoneContinue => 'Continua';

  @override
  String get successfullyConnectedGitHub => 'Connesso con successo a GitHub!';

  @override
  String get failedToSubmitReview => 'Invio recensione fallito. Riprova.';

  @override
  String get anyoneCanDiscover => 'Chiunque può scoprire la tua app';

  @override
  String get v2Undetected => 'V2 non rilevato';

  @override
  String get usageIrlEvents => 'Eventi dal vivo';

  @override
  String get conversationPromptHint =>
      'es., Estrai attività, decisioni prese e punti chiave dalla conversazione fornita.';

  @override
  String get openProviderDocs => 'Apri documentazione';

  @override
  String get showMeetingsInMenuBar => 'Mostra Riunioni nella Barra dei Menu';

  @override
  String get viewPlansAndUsage => 'Visualizza Piani e Utilizzo';

  @override
  String get buildSubmitCustomOmiApp => 'Crea e invia la tua app Omi personalizzata';

  @override
  String get failedToRefreshGoogleStatus => 'Impossibile aggiornare lo stato della connessione Google.';

  @override
  String get feedbackSubtitleTooExpensive => 'Il tuo feedback ci aiuta a trovare il giusto equilibrio.';

  @override
  String get startUsingOmi => 'Inizia a usare Omi';

  @override
  String get dreamReportLearnedWords => 'Parole apprese';

  @override
  String get actionItemCreated => 'Attività creata';

  @override
  String get exportAllConversationsToJson => 'Esporta tutte le tue conversazioni in un file JSON.';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'Controlla la tua connessione Internet e riprova';

  @override
  String get callStateEnded => 'Chiamata terminata';

  @override
  String get phoneNumberHint => 'Numero di telefono';

  @override
  String get tasksGroupByProject => 'Raggruppa per progetto';

  @override
  String get phoneCallsUnlimitedOnly => 'Chiamate telefoniche tramite Omi';

  @override
  String get frequencyDescMinimal => 'Solo cose urgenti, circa 1–3 al giorno';

  @override
  String get changeYourName => 'Cambia il tuo nome';

  @override
  String get editYourReply => 'Modifica risposta';

  @override
  String get publicMemories => 'Ricordi pubblici';

  @override
  String get monthDec => 'Dic';

  @override
  String get reviewNewPersonName => 'Il suo nome';

  @override
  String get googleCalendarConnectPrompt =>
      'Collega il tuo Google Calendar per associare le conversazioni agli eventi del calendario.';

  @override
  String get realtimeAudioBytes => 'Byte audio in tempo reale';

  @override
  String get trackYourGoalsOnHomepage => 'Monitora i tuoi obiettivi personali nella homepage';

  @override
  String get chatAddAttachment => 'Aggiungi allegato';

  @override
  String get beta => 'BETA';

  @override
  String get createMemory => 'Crea memoria';

  @override
  String get permissionsRequiredDescription =>
      'Omi ha bisogno di alcune autorizzazioni per funzionare correttamente. Per favore, concedile per continuare.';

  @override
  String get dataCollectionMessage =>
      'Continuando, le tue conversazioni, registrazioni e informazioni personali verranno archiviate in modo sicuro sui nostri server per fornire informazioni basate sull\'IA e abilitare tutte le funzionalità dell\'app.';

  @override
  String get batteryLevel => 'Livello batteria';

  @override
  String get searchCountries => 'Cerca paesi...';

  @override
  String get confidenceSheetTitle => 'Affidabilità';

  @override
  String get deviceModelLabel => 'Modello dispositivo';

  @override
  String get noStableFirmwareFound => 'Impossibile trovare una versione stabile del firmware per il tuo dispositivo.';

  @override
  String get noResultsFound => 'Nessun risultato trovato';

  @override
  String get wrappedMins => 'min';

  @override
  String get chatAppsTelegramSubtitle => 'Si configura in due tocchi';

  @override
  String get categoryConversationAnalysis => 'Analisi delle conversazioni';

  @override
  String get target => 'Obiettivo';

  @override
  String get apiKeyRequired => 'La chiave API è richiesta';

  @override
  String otaUpdatedMessage(String deviceName) {
    return '$deviceName è aggiornato e si riavvierà da solo.';
  }

  @override
  String get reconnections => 'Riconnessioni';

  @override
  String errorCheckingConnection(String error) {
    return 'Errore durante il controllo della connessione: $error';
  }

  @override
  String get usageMonth => 'Questo Mese';

  @override
  String get additionalSpeechSampleRemoved => 'Campione vocale aggiuntivo rimosso';

  @override
  String get speakerTagPromptExcerptSaved => 'Risposta salvata per questo brano.';

  @override
  String get omisStorage => 'Archivio di Omi';

  @override
  String get recordingAndTranscription => 'Registrazione e trascrizione';

  @override
  String get categoryCommunication => 'Comunicazione';

  @override
  String get wrappedYouDidIt => 'Ce l\'hai fatta! 🎉';

  @override
  String get failedToDeleteItems => 'Impossibile eliminare gli elementi';

  @override
  String speakerLabelLinesLabeled(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count righe etichettate',
      one: '1 riga etichettata',
    );
    return '$_temp0';
  }

  @override
  String get generatingLink => 'Generazione link…';

  @override
  String get clickHereForAppBuildingGuides => 'Clicca qui per le guide alla creazione di app e la documentazione';

  @override
  String get authUrl => 'URL di autenticazione';

  @override
  String get addAppCapabilityConflictWithPersona => 'Altre capacità non possono essere selezionate con Persona';

  @override
  String get deviceOnboardingVoiceReplyGenericHeadphones => 'Cuffie';

  @override
  String get clearAll => 'Cancella tutto';

  @override
  String get noKnowledgeGraphYet => 'Nessun grafo della conoscenza ancora';

  @override
  String get messageReportedSuccessfully => '✅ Messaggio segnalato con successo';

  @override
  String get paymentFailedToSetDefault => 'Impostazione metodo di pagamento predefinito fallita. Riprova più tardi.';

  @override
  String get memoryReviewUpdated => 'Aggiornato.';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'Il tuo piano sarà annullato il $date.';
  }

  @override
  String get welcomeToOmi => 'Benvenuto in Omi';

  @override
  String get phoneFreeCallLimitReached => 'Limite mensile di chiamate gratuite raggiunto. Si azzera il mese prossimo.';

  @override
  String get omiTranscriptionOptimized =>
      'La trascrizione dal vivo di Omi è pensata per le conversazioni in tempo reale e indica chi ha detto cosa.';

  @override
  String get chatAppsLoadFailedTitle => 'Impossibile caricare le app di chat';

  @override
  String get continueWithGoogle => 'Continua con Google';

  @override
  String get setupSteps => 'Passaggi di configurazione';

  @override
  String totalMemoriesCount(int count) {
    return 'Hai $count ricordi totali';
  }

  @override
  String get feedbackSubtitleBatteryDrain => 'Questo aiuta il nostro team hardware a migliorare.';

  @override
  String get tryIt => 'Provalo';

  @override
  String get chatAppsInsights => 'Spunti da Omi';

  @override
  String nFiles(int count) {
    return '$count registrazioni';
  }

  @override
  String get clearChatTitle => 'Cancellare la chat?';

  @override
  String get onlyYouCanUseTemplate => 'Solo tu puoi usare questo modello';

  @override
  String get raybanMetaCameraExplanation =>
      'Omi usa la fotocamera dei tuoi occhiali per aggiungere foto alle tue conversazioni. Puoi saltare questo passaggio e usare solo l\'audio.';

  @override
  String get deviceDiagnosticsTicket => 'Support ticket code';

  @override
  String get capabilityTasks => 'Attività';

  @override
  String get copyUrl => 'Copia URL';

  @override
  String keepItemPublic(String item) {
    return 'Mantieni $item pubblico';
  }

  @override
  String get chatStarterTeachMe => 'Puoi insegnarmi qualcosa di nuovo?';

  @override
  String get cancelReasonDetailHint => 'Apprezziamo qualsiasi feedback…';

  @override
  String get checkConnectionTryAgain => 'Controlla la connessione e riprova.';

  @override
  String get backToConversations => 'Torna alle conversazioni';

  @override
  String get merge => 'Unisci';

  @override
  String get couldNotLaunchUpgradePage => 'Impossibile aprire la pagina di upgrade. Riprova.';

  @override
  String get deviceOnboardingTranscriptionSubtitle => 'Pronuncia qualche parola e guardale comparire in tempo reale';

  @override
  String get deleteOnDeviceModelConfirm => 'Eliminare questo modello?';

  @override
  String get reviewQuestionSpeaker => 'Chi l’ha detto?';

  @override
  String updatedDate(String date) {
    return 'Aggiornato $date';
  }

  @override
  String get saveSettings => 'Salva Impostazioni';

  @override
  String get alreadyGavePermission =>
      'Ci hai già dato il permesso di salvare le tue registrazioni. Ecco un promemoria del perché ne abbiamo bisogno:';

  @override
  String get appCreatedAndInstalled => 'App creata e installata!';

  @override
  String get failedToRefreshNotionStatus => 'Impossibile aggiornare lo stato della connessione Notion.';

  @override
  String get deviceOnboardingProcessingQuestion => 'Elaborazione della tua domanda…';

  @override
  String get chatBlockTask => 'Attività';

  @override
  String get pendantNotConnected => 'Pendente non connesso. Connettiti per sincronizzare.';

  @override
  String get createActionItem => 'Crea attività';

  @override
  String get logsCopied => 'Log copiati';

  @override
  String get timeout5MinutesDesc => 'Termina conversazione dopo 5 minuti di silenzio';

  @override
  String get msgUploadFileFailed => 'Caricamento file fallito, si prega di riprovare più tardi';

  @override
  String get reportMessageConfirm => 'Segnalare questo messaggio?';

  @override
  String deletePersonConfirmation(String name) {
    return 'Questo rimuove i campioni vocali di $name e non può essere annullato. Le sue battute nelle conversazioni passate diventano interlocutori senza nome.';
  }

  @override
  String get weekdayTue => 'Mar';

  @override
  String get liveTranscript => 'Trascrizione dal vivo';

  @override
  String timeDaysAndHours(int days, int hours) {
    return '$days giorni $hours ore';
  }

  @override
  String versionLabel(String version) {
    return 'Versione $version';
  }

  @override
  String get cancelConsequenceDelay => 'Ritardo di elaborazione di 5-7 secondi (modelli sul dispositivo)';

  @override
  String captureRecordingSeparateMessage(String recording) {
    return '$recording verrà mostrata come conversazione a sé e non sarà più raggruppata con questo evento.';
  }

  @override
  String get updateAvailableTitle => 'Aggiornamento disponibile';

  @override
  String get dreamReportShadowBanner =>
      'Modalità anteprima: Dream mostra cosa cambierebbe, ma per ora nel tuo account non cambia nulla.';

  @override
  String get sharedTasksAcceptFailed =>
      'Impossibile accettare queste attività. Forse hai già accettato questa condivisione.';

  @override
  String get appPricingLabel => 'Prezzo dell\'app';

  @override
  String get reDownload => 'Scarica di nuovo';

  @override
  String get recordWithPhoneMic => 'Registra con il microfono del telefono';

  @override
  String appDisabledOn(String date) {
    return 'Disattivata il $date.';
  }

  @override
  String get play => 'Riproduci';

  @override
  String get private => 'Privato';

  @override
  String get speakerTagPromptNotSureAction => 'Non so';

  @override
  String get showDiscardedConversationsDesc => 'Includi conversazioni contrassegnate come scartate';

  @override
  String get captureModeLiveDescription => 'Trascrivi in tempo reale mentre parli.';

  @override
  String get subscriptionCancelledSuccessfully =>
      'Abbonamento annullato con successo. Rimarrà attivo fino alla fine del periodo di fatturazione corrente.';

  @override
  String get tapToSetAGoal => 'Tocca per impostare un obiettivo';

  @override
  String get tellUsMoreWhatWentWrong => 'Raccontaci di più su cosa è andato storto…';

  @override
  String get downgradeToFreemiumTitle => 'Passare al piano gratuito?';

  @override
  String get usageTasks => 'Attività';

  @override
  String get chatReplyOffline => 'Impossibile connettersi. Controlla la connessione e riprova.';

  @override
  String get makePublic => 'Rendi pubblico';

  @override
  String get authUnexpectedErrorFirebase => 'Errore imprevisto durante l\'accesso, errore Firebase, riprova.';

  @override
  String get unlimitedConversations => 'Conversazioni illimitate';

  @override
  String get stagingDisclaimer =>
      'L\'ambiente di staging potrebbe essere instabile, avere prestazioni inconsistenti e i dati potrebbero andare persi. Usalo solo per i test.';

  @override
  String get captureMicrophonePermissionRequired => 'Autorizzazione microfono richiesta';

  @override
  String shareStatsInsights(String count) {
    return '✨ Fornito $count insight';
  }

  @override
  String get feedbackReasonSummaryIrrelevant => 'Non pertinente';

  @override
  String get userIdCopiedToClipboard => 'ID utente copiato';

  @override
  String get urlCopiedToClipboard => 'URL copiato negli appunti';

  @override
  String annualBillingSummary(int months, String price) {
    return '$months mesi / $price';
  }

  @override
  String chatAppsShowInAppOff(String app) {
    return 'Off: le vedi solo su $app.';
  }

  @override
  String get replySentSuccessfully => 'Risposta inviata con successo';

  @override
  String get deviceOnboardingTurnOffTitle => 'Spegni';

  @override
  String get phoneStorageDesc =>
      'Quando Omi si riconnette, le registrazioni vengono trasferite automaticamente al telefono prima del caricamento.';

  @override
  String get callRecordingConsentDisclaimer =>
      'La registrazione delle chiamate potrebbe richiedere il consenso nella tua giurisdizione';

  @override
  String get showDiscardedConversations => 'Mostra Conversazioni Scartate';

  @override
  String get calendarIntegration => 'Integrazione Calendario';

  @override
  String get whisperModelSizeBase => 'Base';

  @override
  String get shareViaSms => 'Condividi via SMS';

  @override
  String get nameMustBeAtLeast3Characters => 'Il nome deve essere di almeno 3 caratteri';

  @override
  String get chatDiscardRecording => 'Scarta';

  @override
  String get chatAppsProPerkText => 'Scrivi a Omi da Telegram e iMessage';

  @override
  String get readyToSync => 'Pronto per sincronizzare';

  @override
  String get noAppsInCategoryYet => 'Ancora nessuna app in questa categoria';

  @override
  String get firmwareUpdateAvailable => 'Aggiornamento firmware disponibile';

  @override
  String get modelNumber => 'Numero modello';

  @override
  String get sortBy => 'Ordina';

  @override
  String get slideToUpdate => 'Scorri per aggiornare';

  @override
  String get effectBarelyCounts => 'Aiuta pochissimo';

  @override
  String get onlyYouCanUse => 'Solo tu puoi usare questa app';

  @override
  String get triggersWhenNewConversationCreated => 'Si attiva quando viene creata una nuova conversazione.';

  @override
  String get paymentPlan => 'Piano di pagamento';

  @override
  String get whisperModelDesc => 'Seleziona il modello per la trascrizione sul dispositivo';

  @override
  String get askSuggestOwe => 'Cosa devo ancora agli altri?';

  @override
  String get starConversation => 'Aggiungi ai Preferiti';

  @override
  String get hardwareSection => 'Hardware';

  @override
  String get transcribing => 'Trascrizione…';

  @override
  String get chatAppsVoiceNotesSubtitle => 'Invia una nota vocale e Omi ti risponderà.';

  @override
  String confidenceNextVoice(String name) {
    return 'A Omi serve anche un campione vocale di $name. Etichettalo con Ricorda le voci attivo.';
  }

  @override
  String get rating3PlusStars => '3+ stelle';

  @override
  String get recordingActive => 'Registrazione attiva';

  @override
  String starFilter(int count) {
    return '$count Stelle';
  }

  @override
  String get storageLocationLabel => 'Posizione di Archiviazione';

  @override
  String get reviewNoChangesBody => 'Quando Omi riordina i tuoi appunti, le modifiche compaiono qui.';

  @override
  String get testPrompt => 'Prova Prompt';

  @override
  String get otaUpdateUnavailable => 'Questo aggiornamento non è disponibile al momento. Riprova più tardi.';

  @override
  String get downloading => 'Download in corso…';

  @override
  String get welcomeBackSimple => 'Bentornato';

  @override
  String get sttProviderSoniox => 'Soniox';

  @override
  String get clearAllSelection => 'Cancella tutto';

  @override
  String get confidenceReasonNeverConfirmed => 'Mai confermato';

  @override
  String get writeScope => 'Scrittura';

  @override
  String get evidenceVoiceReady => 'Campione vocale pronto';

  @override
  String get updateApp => 'Aggiorna app';

  @override
  String get weekdayThu => 'Gio';

  @override
  String chatUsageCostNoLimit(String used) {
    return 'Chat: \$$used utilizzato questo mese';
  }

  @override
  String get configCopied => 'Configurazione copiata negli appunti';

  @override
  String get startupFailedConfigMessage =>
      'Questa build di Omi presenta un problema di configurazione. Non è un problema del tuo dispositivo. Contatta l\'assistenza e includi i dettagli qui sotto.';

  @override
  String get getOmiForMac => 'Ottieni Omi per Mac';

  @override
  String get appleHealthConnectedBadge => 'Connesso';

  @override
  String get msgCameraNotAvailable => 'La cattura della fotocamera non è disponibile su questa piattaforma';

  @override
  String get actionItemsDescription => 'Tocca per modificare • Tieni premuto per selezionare • Scorri per azioni';

  @override
  String get notificationsDesc =>
      'Così Omi può inviarti riepiloghi delle conversazioni, promemoria delle attività e risposte dalle tue app.';

  @override
  String audioUploadRetrying(String duration) {
    return 'Nuovo tentativo di caricamento… $duration di audio conservati sul telefono';
  }

  @override
  String get importStarted => 'Importazione avviata! Riceverai una notifica quando sarà completata.';

  @override
  String get onDeviceModelDownloadFailed => 'Download del modello non riuscito';

  @override
  String get noProjectsInWorkspace => 'Nessun progetto trovato in quest\'area di lavoro';

  @override
  String get helpCenter => 'Centro Assistenza';

  @override
  String get trainingDataBullets =>
      '• I tuoi dati aiutano a migliorare i modelli AI\n• Vengono condivisi solo dati non sensibili';

  @override
  String get invalidPromotionCode => 'Codice promozionale non valido.';

  @override
  String get battery => 'Batteria';

  @override
  String get clearSelection => 'Cancella selezione';

  @override
  String get phoneSetupStep2Subtitle => 'Un codice breve che digiterai durante la chiamata';

  @override
  String get googleSearch => 'Google Search';

  @override
  String get charging => 'In carica';

  @override
  String deleteNamedPerson(String name) {
    return 'Elimina $name';
  }

  @override
  String get chatAppsPartOfPro => 'Le app di chat fanno parte di Pro';

  @override
  String get invalidWebhookUrlError => 'Inserisci un URL del webhook valido';

  @override
  String get starConversationsToFindQuickly => 'Aggiungi la stella alle conversazioni per trovarle rapidamente qui';

  @override
  String get permissionCreateMemories => 'Crea ricordi';

  @override
  String get conversationIdCopied => 'ID conversazione copiato negli appunti';

  @override
  String get chatAppsMessagesApp => 'Messaggi';

  @override
  String get understandingWords => 'Comprensione (parole)';

  @override
  String diagnosticsVerdictTroubleDetail(int count) {
    return 'Connessioni non riuscite nelle ultime 24 ore: $count';
  }

  @override
  String get editName => 'Modifica nome';

  @override
  String get askAboutThisConversation => 'Chiedi informazioni';

  @override
  String get useTemplateFrom => 'Usa modello da';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'Stato autorizzazione microfono: $status. Controlla Preferenze di Sistema.';
  }

  @override
  String get markAsCompleted => 'Segna come completata';

  @override
  String get urlMustEndWithSlashError => 'L\'URL deve terminare con \"/\"';

  @override
  String get deviceOnboardingIntroTitle => 'Scopri il tuo Omi';

  @override
  String nPending(int count) {
    return '$count in attesa';
  }

  @override
  String get howShouldOmiCallYou => 'Come dovrebbe chiamarti Omi?';

  @override
  String get preparingFormForYou => 'Preparazione del modulo per te…';

  @override
  String get deleteChat => 'Elimina chat';

  @override
  String get msgPhotosPermissionDenied =>
      'Permesso foto negato. Si prega di consentire l\'accesso alle foto per selezionare le immagini';

  @override
  String get moreWaysToRecord => 'Altri modi per registrare';

  @override
  String get creatingPlan => 'Creazione piano';

  @override
  String get configCopiedToClipboard => 'Configurazione copiata negli appunti';

  @override
  String get transcribeLaterDescription =>
      'Registra ora e trascrivi quando vuoi. Fino ad allora l\'audio resta sul tuo telefono.';

  @override
  String get couldNotSwitchToFreePlan => 'Impossibile passare al piano gratuito. Riprova.';

  @override
  String get wrappedTasksCompleted => 'attività completate';

  @override
  String get deviceOnboardingTranscriptionTitle => 'Parla al tuo Omi';

  @override
  String get thankYouRequestUnderReview =>
      'Grazie! La tua richiesta è in revisione. Ti avviseremo una volta approvata.';

  @override
  String get unpairAndForgetDevice => 'Disaccoppia e dimentica dispositivo';

  @override
  String get sendWebUrl => 'Invia URL web';

  @override
  String get noTasksForToday => 'Nessuna attività per oggi.\nChiedi a Omi più attività o creale manualmente.';

  @override
  String get conversationSummaryFailed => 'Riepilogo non riuscito';

  @override
  String get realtimeTranscript => 'Trascrizione in tempo reale';

  @override
  String nConversationsCreated(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count conversazioni create',
      one: '1 conversazione creata',
    );
    return '$_temp0';
  }

  @override
  String get noEmailSet => 'Nessuna email impostata';

  @override
  String get setDueDateAndTime => 'Imposta data e ora di scadenza';

  @override
  String get pairingDescFieldy => 'Tieni premuto il dispositivo finché non appare la luce per accenderlo.';

  @override
  String get maximumSecurityE2ee => 'Sicurezza massima (E2EE)';

  @override
  String get instantSpeakerLabels => 'Etichette dei parlanti istantanee';

  @override
  String get resetRequestConfig => 'Ripristina configurazione richiesta predefinita';

  @override
  String get webhookUrlNotSet => 'URL webhook non impostato';

  @override
  String get feedbackReasonRecordingOther => 'Altro';

  @override
  String get accountCutoverMigrationRollbackMessage =>
      'Il tuo account è in manutenzione dopo un rollback della migrazione. Alcuni dati più recenti potrebbero essere isolati.';

  @override
  String get cancelConsequenceQuality => '30% in meno di qualità di trascrizione (modelli sul dispositivo)';

  @override
  String get pairingDescPlaudNote =>
      'Tieni premuto il pulsante laterale per 2 secondi. Il LED rosso lampeggerà quando è pronto per l\'accoppiamento.';

  @override
  String get plansAndBilling => 'Piani e Fatturazione';

  @override
  String get deviceOnboardingVoiceReplyTitle => 'Ascolta le risposte di Omi';

  @override
  String get generatingIcon => 'Generazione icona…';

  @override
  String get cleanUpBannerBody => 'Per lo più nomi capiti male. Controllali e rimuovi quelli che non sono reali.';

  @override
  String get speakerTagPromptSavedAsYou => 'Salvato come te';

  @override
  String get connectOmiOmiGlass => 'Connetti Omi / OmiGlass';

  @override
  String get capabilityConversations => 'Conversazioni';

  @override
  String get notificationFrequencyDescription =>
      'Controlla quanto spesso Omi ti invia notifiche proattive e promemoria.';

  @override
  String chatScopeAbout(String title) {
    return 'Informazioni su: $title';
  }

  @override
  String get importHistory => 'Cronologia importazione';

  @override
  String get getApiKey => 'Ottieni chiave API';

  @override
  String get nothingInterestingRetry => 'Niente di interessante trovato,\nvuoi riprovare?';

  @override
  String get whatWouldYouLikeToCreate => 'Cosa vorresti creare?';

  @override
  String get pricingFree => 'Gratuita';

  @override
  String get speakerTagPromptHintIdentify => 'La tua risposta aiuta Omi a riconoscere questa voce la prossima volta.';

  @override
  String get noConversationsYet => 'Ancora nessuna conversazione';

  @override
  String get deviceNotMeetRequirements =>
      'Il tuo dispositivo non soddisfa i requisiti per la trascrizione sul dispositivo.';

  @override
  String get pressKeys => 'Premi i tasti…';

  @override
  String get downgradeLimitDelayNotRealTime => 'Ritardo di 5-7 secondi (non in tempo reale)';

  @override
  String get conversationLinkCopiedToClipboard => 'Link della conversazione copiato negli appunti';

  @override
  String get onboardingSetupStepMemory => 'Configurazione della tua memoria';

  @override
  String get chatAppsTelegramOtherDevice => 'Telegram su un altro dispositivo?';

  @override
  String get appNotFoundOrRemoved => 'Questa app non è più disponibile';

  @override
  String appsCount(String count) {
    return 'App ($count)';
  }

  @override
  String get endToEndEncryption => 'Crittografia end-to-end';

  @override
  String otaConnectFailed(String deviceName) {
    return 'Impossibile connettersi a $deviceName. Tienilo acceso e vicino, poi riprova.';
  }

  @override
  String get continueButton => 'Continua';

  @override
  String get failedToPrepareConversationForSharing =>
      'Impossibile preparare la conversazione per la condivisione. Riprova.';

  @override
  String get showAll => 'Mostra tutto →';

  @override
  String get speakerLabelYou => 'Tu';

  @override
  String get wrappedActionItems => 'Attività';

  @override
  String failedToInstallApp(String appName) {
    return 'Installazione di $appName non riuscita. Riprova.';
  }

  @override
  String get searching => 'Ricerca in corso';

  @override
  String get deviceNotCompatibleTitle => 'Dispositivo non compatibile';

  @override
  String get summarize => 'Riassumi';

  @override
  String get exportConversationsToJson => 'Esporta le conversazioni in un file JSON';

  @override
  String makeItemPrivateExplanation(String item) {
    return 'Se rendi $item privato ora, smetterà di funzionare per tutti e sarà visibile solo a te';
  }

  @override
  String get wrappedFailedToShare => 'Condivisione fallita. Riprova.';

  @override
  String get cancelSubscriptionConfirmation =>
      'Continuerai ad avere accesso fino alla fine del periodo di fatturazione corrente.';

  @override
  String get phoneHideKeypad => 'Nascondi tastiera';

  @override
  String get vadGate => 'VAD Gate';

  @override
  String get nameUpdatedSuccessfully => 'Nome aggiornato con successo!';

  @override
  String get photoLibrary => 'Libreria foto';

  @override
  String get chatAppsHeroMessage =>
      'Fai domande sulla tua giornata, salva ricordi e gestisci le attività da Telegram o iMessage. Le tue chat restano nell\'app che usi e Omi ricorda ciò di cui hai parlato ovunque.';

  @override
  String get upgradeToAnnualPlan => 'Passa al piano annuale';

  @override
  String get completeAuthInBrowser => 'Completa l\'autenticazione nel tuo browser. Una volta fatto, torna all\'app.';

  @override
  String errorLabel(String error) {
    return 'Errore: $error';
  }

  @override
  String get durationThresholdDesc => 'Nascondi conversazioni più brevi di questa soglia';

  @override
  String transcriptionsPendingCount(int count) {
    return 'Trascrizioni in attesa $count';
  }

  @override
  String get transcribeLaterNote =>
      'Funziona con il microfono del telefono e con i dispositivi Omi e Limitless. L\'audio resta sul telefono finché non scegli di caricarlo.';

  @override
  String get device => 'Dispositivo';

  @override
  String get signUpSuccess => 'Registrazione riuscita!';

  @override
  String get onboardingPermissions => 'Autorizzazioni';

  @override
  String get modelTooLargeWarning =>
      'Questo modello è grande e potrebbe causare il crash dellapp o un funzionamento molto lento sui dispositivi mobili.\n\nSi consiglia small o base.';

  @override
  String get showDailyScoreOnHomepage => 'Mostra punteggio giornaliero nella homepage';

  @override
  String confidenceSummaryUnverified(String name) {
    return 'Non hai ancora etichettato o confermato $name, quindi Omi non è sicuro di riconoscerne la voce.';
  }

  @override
  String get endConversation => 'Termina Conversazione';

  @override
  String get unpinAsBaseline => 'Rimuovi dalla base';

  @override
  String audioSavedLocally(String duration) {
    return '$duration di audio salvato localmente';
  }

  @override
  String get editMemory => '✏️ Modifica memoria';

  @override
  String get speakerTagPromptThanks => 'Grazie! Omi riconoscerà sempre meglio le voci.';

  @override
  String get actionItemDescriptionEmpty => 'La descrizione dell\'attività non può essere vuota.';

  @override
  String get maybeLater => 'Forse più tardi';

  @override
  String get daySummary => 'Riepilogo giornaliero';

  @override
  String get confirmReportMessage => 'Segnalare questo messaggio?';

  @override
  String get deleteAllLimitlessConversations => 'Eliminare tutte le conversazioni Limitless?';

  @override
  String get selectAllTasksMenu => 'Seleziona tutto';

  @override
  String get syncStatusRetrying => 'Elaborazione non riuscita — nuovo tentativo';

  @override
  String get exportButton => 'Esporta';

  @override
  String get wrappedYouTalkedAboutBadge => 'Hai parlato di';

  @override
  String get firmwareWarningTitle => 'Importante: Leggere prima dell\'aggiornamento';

  @override
  String get permissionTypeCreate => 'Crea';

  @override
  String get viewUsage => 'Visualizza utilizzo';

  @override
  String get deviceOnboardingIntroDuration => 'Circa 1 minuto';

  @override
  String get import => 'Importa';

  @override
  String get conversationsExportStarted =>
      'Esportazione conversazioni avviata. Questo potrebbe richiedere alcuni secondi, attendere prego.';

  @override
  String get speechToTextProvider => 'Provider speech-to-text';

  @override
  String get languageTranslation => 'Traduzione in oltre 100 lingue';

  @override
  String get primaryLanguage => 'Lingua principale';

  @override
  String durationSeconds(String seconds) {
    return 'Durata: $seconds secondi';
  }

  @override
  String get autoSyncDescription =>
      'Sincronizza automaticamente le registrazioni offline quando il dispositivo si connette';

  @override
  String get debugLogs => 'Log di debug';

  @override
  String get authorizationRevoked => 'Autorizzazione revocata.';

  @override
  String get noTranscriptAvailable => 'Nessuna trascrizione disponibile';

  @override
  String get available => 'Disponibile';

  @override
  String get wrappedObsessionsLabelUpper => 'OSSESSIONI';

  @override
  String get professionStudent => 'Studente';

  @override
  String get chatAppsTryRemind => 'Ricordami di chiamare la mamma domenica';

  @override
  String get failedToStartVerification => 'Impossibile avviare la verifica';

  @override
  String get failedToCreateFolder => 'Impossibile creare la cartella';

  @override
  String timeMinSingular(int count) {
    return '$count min';
  }

  @override
  String get insights => 'Approfondimenti';

  @override
  String get privacyInformation => 'Informazioni sulla privacy';

  @override
  String get finishedConversation => 'Conversazione terminata?';

  @override
  String get syncGoogleAccount => 'Sincronizza con il tuo account Google';

  @override
  String get pairingTitleNeoOne => 'Metti Neo One in modalità di accoppiamento';

  @override
  String get translatedByOmi => 'tradotto da Omi';

  @override
  String get githubRepositoryUrl => 'URL del repository GitHub';

  @override
  String get readOnlyScope => 'Solo lettura';

  @override
  String get chatAppsChannelsTitle => 'App di chat';

  @override
  String get chatAppsDoesAnswer => 'Risponde a domande sulle tue conversazioni e sui tuoi ricordi';

  @override
  String get wrappedFailedToStartGeneration => 'Avvio generazione fallito. Riprova.';

  @override
  String get storageLocationSdCard => 'Scheda SD';

  @override
  String get askSuggestDecide => 'Cosa ho deciso oggi?';

  @override
  String get close => 'Chiudi';

  @override
  String get paymentMethodPayPal => 'PayPal';

  @override
  String categoryAppCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count app',
      one: '1 app',
    );
    return '$_temp0';
  }

  @override
  String get speakerTagPromptRecentPeople => 'Persone con cui hai parlato di recente';

  @override
  String get actionCreateMemories => 'Crea ricordi';

  @override
  String get swipeTasksToIndent => 'Scorri le attività per rientrare, trascina tra le categorie';

  @override
  String get createAccountTitle => 'Crea account';

  @override
  String get modelRequired => 'Modello richiesto';

  @override
  String get saveMemory => 'Salva Ricordo';

  @override
  String get successfullyConnectedClickUp => 'Connesso con successo a ClickUp!';

  @override
  String get notYetSynced => 'Non ancora sincronizzato con il tuo telefono';

  @override
  String get pendantUpToDate => 'Il pendente è aggiornato';

  @override
  String get categoryProductivityTools => 'Strumenti di produttività';

  @override
  String get refresh => 'Aggiorna';

  @override
  String get cancelSyncMessage => 'I dati già scaricati saranno salvati. Potrai riprendere in seguito.';

  @override
  String get selectImageFileTitle => 'Seleziona un file immagine';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'Errore nell\'apertura del selettore file: $message';
  }

  @override
  String get failedToGenerateConversationLink => 'Generazione del link della conversazione non riuscita';

  @override
  String get voiceFailedToTranscribe => 'Trascrizione audio non riuscita';

  @override
  String get viewAll => 'Vedi tutto';

  @override
  String get yourNewKey => 'La tua nuova chiave:';

  @override
  String get conversationMap => 'Mappa delle conversazioni';

  @override
  String get contactSupportAction => 'Contatta l\'assistenza';

  @override
  String get weekdaySun => 'Dom';

  @override
  String get summaryNotFound => 'Riepilogo non trovato';

  @override
  String get shortConversationThreshold => 'Soglia Conversazione Breve';

  @override
  String get dailyRecapsDescription => 'I tuoi riepiloghi giornalieri appariranno qui una volta generati';

  @override
  String get phoneCallsWithOmi => 'Chiamate con Omi';

  @override
  String get addAppSelectPaymentPlan => 'Seleziona un piano di pagamento e inserisci un prezzo per la tua app';

  @override
  String get deleteAccountFinal =>
      'Questa azione è irreversibile e eliminerà permanentemente il tuo account e tutti i dati associati. Sei sicuro di voler procedere?';

  @override
  String get gettingAudioFiles => 'Recupero file audio…';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String get port => 'Porta';

  @override
  String personPinnedToast(String name) {
    return 'Fissato: $name';
  }

  @override
  String get wrappedConversations => 'conversazioni';

  @override
  String get availableOnMacMobileWeb => 'Disponibile su Mac, mobile e web';

  @override
  String get monthAug => 'Ago';

  @override
  String get failedToGenerateSummary =>
      'Impossibile generare il riepilogo. Assicurati di avere conversazioni per quel giorno.';

  @override
  String planEndedOn(String date) {
    return 'Il tuo piano è terminato il $date.\nRiabbonati ora - ti verrà addebitato immediatamente per un nuovo periodo di fatturazione.';
  }

  @override
  String get createAnApp => 'Crea un\'app';

  @override
  String get cancelling => 'Annullamento…';

  @override
  String get wrappedTopDaysHeader => 'Giorni migliori';

  @override
  String get keepEditing => 'Continua a modificare';

  @override
  String get ignoredVoicesEmpty => 'Nessuna voce ignorata';

  @override
  String get cannotBeUndone => 'Questa operazione non può essere annullata.';

  @override
  String get usersPayToUse => 'Gli utenti pagano per usare la tua app';

  @override
  String get maxFilesUploadError => 'Puoi caricare solo 4 file alla volta';

  @override
  String get yourDeviceIsUpToDate => 'Il tuo dispositivo è aggiornato';

  @override
  String get unableToFetchApps =>
      'Impossibile recuperare le app :(\n\nControlla la tua connessione internet e riprova.';

  @override
  String get entityCorrectionFailed => 'Impossibile inviare la correzione. Riprova.';

  @override
  String get alreadyAuthorized => 'Già Autorizzato';

  @override
  String get speedAccuracyLower => 'Velocità e precisione potrebbero essere inferiori rispetto ai modelli Cloud.';

  @override
  String siriShortcutsSearchHint(String searchPhrase) {
    return ' Puoi anche dire “$searchPhrase for what I did today”.';
  }

  @override
  String get unlimitedPlan => 'Piano Illimitato';

  @override
  String get contactSupport => 'Contatta Supporto?';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Massimo $count obiettivi consentiti';
  }

  @override
  String get deviceStorageNearlyFull => 'Dispositivo quasi pieno — sincronizza per liberare spazio.';

  @override
  String get setDueDate => 'Imposta data di scadenza';

  @override
  String privateAppsCount(String count) {
    return 'App private ($count)';
  }

  @override
  String get selectPeople => 'Seleziona persone';

  @override
  String get capabilityChat => 'Chat';

  @override
  String chatAppsChannelChats(String app) {
    return 'Chat di $app';
  }

  @override
  String get transcribeLaterTitle => 'Trascrivi più tardi';

  @override
  String get failedToConnectAsana => 'Connessione ad Asana non riuscita';

  @override
  String get youAreOnUnlimitedPlan => 'Sei sul piano Illimitato.';

  @override
  String get chatAppsIncludedWithPro => 'INCLUSO CON OMI PRO';

  @override
  String get failedToCreateKeyTryAgain => 'Impossibile creare la chiave. Riprova.';

  @override
  String get backgroundModeTitle => 'Modalità in background';

  @override
  String get discardChangesMessage => 'Le modifiche non salvate andranno perse.';

  @override
  String get captureSourcePendant => 'Ciondolo';

  @override
  String get exportTasksWithOneTap => 'Esporta le attività con un tocco!';

  @override
  String get sundayAbbr => 'Dom';

  @override
  String get pleaseEnterAppPrompt => 'Inserisci un prompt per la tua app';

  @override
  String deviceStoragePercentFull(int percent) {
    return '$percent% pieno';
  }

  @override
  String get developerSettings => 'Impostazioni sviluppatore';

  @override
  String get selectYouFromList => 'Per taggare te stesso, seleziona \"Tu\" dalla lista.';

  @override
  String get deleteNow => 'Elimina Ora';

  @override
  String get installUpdate => 'Installa aggiornamento';

  @override
  String get unpairDevice => 'Disaccoppia dispositivo';

  @override
  String get assistantVoice => 'Voce dell\'assistente';

  @override
  String get installingApp => 'Installazione app…';

  @override
  String get wrappedFunnyMomentTitle => 'Momento divertente';

  @override
  String onboardingFailedCheckNotification(String error) {
    return 'Impossibile verificare l\'autorizzazione notifiche: $error';
  }

  @override
  String get dreamReportRunNow => 'Esegui ora';

  @override
  String get notSet => 'Non impostato';

  @override
  String get startVoiceRecording => 'Avvia registrazione vocale';

  @override
  String get userInformation => 'Informazioni Utente';

  @override
  String get wrappedStruggleLabel => 'SFIDA';

  @override
  String get filterInteresting => 'Insight';

  @override
  String captureRecordingsCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count registrazioni',
      one: '1 registrazione',
    );
    return '$_temp0';
  }

  @override
  String get addOrChangeYourPaymentMethod => 'Aggiungi o modifica metodo di pagamento';

  @override
  String get unableToLoadApps => 'Impossibile caricare le app';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'È disponibile un nuovo aggiornamento firmware ($version) per il tuo dispositivo Omi. Vuoi aggiornare ora?';
  }

  @override
  String get cancelReasonTooExpensive => 'Troppo costoso';

  @override
  String get firmwareUsbWarning => 'La connessione USB durante gli aggiornamenti può danneggiare il dispositivo.';

  @override
  String authAccessMessage(String appName) {
    return 'Dovrai autorizzare Omi ad accedere ai tuoi dati $appName. Questo aprirà il tuo browser per l\'autenticazione.';
  }

  @override
  String get conversationEndsManually => 'La conversazione terminerà solo manualmente.';

  @override
  String get partialRecording => 'Registrazione parziale';

  @override
  String get dreamReportFeedback => 'Segnalato al team di Omi';

  @override
  String get shareAudio => 'Condividi audio';

  @override
  String get importDataFromOtherSources => 'Importa dati da altre fonti';

  @override
  String get premiumMinutesUsed => 'Minuti premium utilizzati.';

  @override
  String get phoneCallsUpgradeButton => 'Passa a Illimitato';

  @override
  String get omiUnlimited => 'Omi Unlimited';

  @override
  String get unknownDevice => 'Sconosciuto';

  @override
  String get failedToStartImport => 'Impossibile avviare l\'importazione. Riprova.';

  @override
  String get searchActionItems => 'Cerca attività';

  @override
  String get whisperModel => 'Modello Whisper';

  @override
  String get searchContacts => 'Cerca contatti';

  @override
  String get selectAllSkipsPinned =>
      'Seleziona tutto salta le persone fissate. Eliminale una alla volta dalla loro pagina.';

  @override
  String get speechProfileIntro => 'Omi deve imparare i tuoi obiettivi e la tua voce. Potrai modificarlo in seguito.';

  @override
  String get realtimeListening => 'Ascolto in tempo reale';

  @override
  String get appNotAvailable => 'Ops! Sembra che l\'app che stai cercando non sia disponibile.';

  @override
  String get enterYourName => 'Inserisci il tuo nome';

  @override
  String get permissionTypeTrigger => 'Trigger';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'Il tuo grafo della conoscenza verrà costruito automaticamente quando creerai nuovi ricordi.';

  @override
  String get chatAppsLink => 'Link';

  @override
  String get minutes => 'minuti';

  @override
  String get actions => 'Azioni';

  @override
  String get connectRayBanMeta => 'Connetti Ray-Ban Meta';

  @override
  String get monthSep => 'Set';

  @override
  String get selectContactsToShareSummary => 'Seleziona i contatti per condividere il riepilogo della conversazione';

  @override
  String get paymentNoneSelected => 'Nessuna selezione';

  @override
  String get pinAction => 'Fissa';

  @override
  String get monthOct => 'Ott';

  @override
  String get startRecording => 'Avvia registrazione';

  @override
  String get somethingWentWrong => 'Qualcosa è andato storto! Riprova più tardi.';

  @override
  String largeTimeGapsDetected(String gaps) {
    return 'Rilevati grandi divari temporali ($gaps)';
  }

  @override
  String get phoneEnterNumber => 'Inserisci numero';

  @override
  String get cancelConsequenceNoAccess => 'Non avrai più accesso illimitato alla fine del periodo di fatturazione.';

  @override
  String get appleHealthDeniedTitle => 'Accesso ad Apple Health negato';

  @override
  String deleteItemTitle(String item) {
    return 'Elimina $item';
  }

  @override
  String get invalidIntegrationUrl => 'URL di integrazione non valido';

  @override
  String get welcomeActionItemsTitle => 'Pronto per le Attività';

  @override
  String get updateAppConfirmation => 'Le modifiche saranno visibili dopo la revisione del nostro team.';

  @override
  String get corruptedStatus => 'Corrotto';

  @override
  String get cantRateWithoutInternet => 'Impossibile valutare l\'app senza connessione Internet.';

  @override
  String get dontShowAgain => 'Non mostrare più';

  @override
  String get hardwareRevision => 'Revisione Hardware';

  @override
  String get trySelectingDifferentDate => 'Prova a selezionare una data diversa';

  @override
  String get learnings => 'Apprendimenti';

  @override
  String get failedToConnectTodoist => 'Connessione a Todoist non riuscita';

  @override
  String get accessDataProgrammatically => 'Accedi ai tuoi dati in modo programmatico';

  @override
  String processingProgress(int current, int total) {
    return 'Elaborazione $current/$total';
  }

  @override
  String get apiEnvSavedRestartRequired => 'Salvato. Chiudi e riapri l\'app per applicare.';

  @override
  String get syncCardWaitingInternet => 'In attesa di connessione';

  @override
  String get accountCutoverOpenStore => 'Apri store';

  @override
  String get processedConversations => 'Conversazioni elaborate';

  @override
  String get holdOnPreparingForm => 'Attendi, stiamo preparando il modulo per te';

  @override
  String get waitingForDevice => 'In attesa del dispositivo…';

  @override
  String get learnMore => 'Scopri di più…';

  @override
  String get aiGenErrorWhileCreatingApp => 'Si è verificato un errore durante la creazione dell\'app';

  @override
  String get deleteAllFilesWarning =>
      'Questo eliminerà le registrazioni sincronizzate e in sospeso. Le registrazioni in sospeso NON sono state sincronizzate e andranno perse permanentemente.';

  @override
  String get usageWordsHeard => 'Words heard';

  @override
  String get importDataDescription => 'Importa dati da altre fonti';

  @override
  String get raybanMetaImageCaptureUnavailable => 'Non disponibile in modalità solo audio';

  @override
  String get appRejectedMessage =>
      'La tua app è stata rifiutata. Aggiorna i dettagli e invia nuovamente per la revisione.';

  @override
  String get capturePendantDisconnectedShort => 'Omi si riconnetterà da solo';

  @override
  String get improveSpeechProfileDesc =>
      'Utilizziamo le registrazioni per addestrare e migliorare ulteriormente il tuo profilo vocale personale.';

  @override
  String get voiceResponseModeTitle => 'Quando leggere le risposte';

  @override
  String get failedToDeleteItem => 'Impossibile eliminare l\'attività';

  @override
  String get firmware => 'Firmware';

  @override
  String failedToAddToService(String serviceName) {
    return 'Impossibile aggiungere a $serviceName';
  }

  @override
  String get askOmiAnything => 'Chiedi a Omi qualsiasi cosa sulla tua vita';

  @override
  String get integrationsFooter => 'Connetti le tue app per visualizzare dati e metriche nella chat.';

  @override
  String get loading => 'Caricamento…';

  @override
  String get showLess => 'mostra meno ↑';

  @override
  String get chatAppsNeverMessagesOthers => 'Non scrive mai ad altre persone al posto tuo';

  @override
  String get scopeUserName => 'Nome utente';

  @override
  String get mute => 'Muto';

  @override
  String get serverProcessesAudio => 'Il server elabora i file audio e crea ricordi';

  @override
  String mergeConversationsSuccessBody(int count) {
    return '$count conversazioni sono state unite con successo';
  }

  @override
  String get pairingSuccessful => 'ACCOPPIAMENTO RIUSCITO';

  @override
  String get websocketUrl => 'URL WebSocket';

  @override
  String get wrappedFriend => 'Amico';

  @override
  String get frequencyHigh => 'Alto';

  @override
  String get processingFailed => 'Elaborazione Fallita';

  @override
  String get dataLowercase => 'dati';

  @override
  String deviceOfflineWakeHint(String deviceName) {
    return '$deviceName è offline. Premi il suo pulsante per riattivarlo, poi riprova.';
  }

  @override
  String get updatedConversations => 'Conversazioni aggiornate';

  @override
  String get phoneGetStarted => 'Inizia';

  @override
  String get recordingDetails => 'Dettagli registrazione';

  @override
  String get createApiKey => 'Crea chiave API';

  @override
  String get anyoneWithLinkCanView => 'Chiunque abbia il link può visualizzare';

  @override
  String get noPendingTasks => 'Nessuna attività in sospeso';

  @override
  String get featureComingSoon => 'Questa funzionalità sarà disponibile presto!';

  @override
  String get bluetoothMethodDescription =>
      'Utilizza la connessione Bluetooth Low Energy standard. Più lento ma non influisce sulla connessione WiFi.';

  @override
  String get chatAppsNotConnectedTitle => 'Non connesso';

  @override
  String get wrappedMostIntenseDay => 'Più intenso';

  @override
  String get yesterday => 'Ieri';

  @override
  String get requestConfiguration => 'Configurazione Richiesta';

  @override
  String get timeAM => 'AM';

  @override
  String autoRemoveSyncedCopiesDescription(int days) {
    return 'Elimina le copie locali $days giorni dopo la sincronizzazione. Le copie sul cloud vengono conservate.';
  }

  @override
  String get chatAppsTelegramPrivacyNote =>
      'Le tue chat con Omi vengono memorizzate anche da Telegram. Omi risponde solo a te, mai ad altre persone, e puoi disconnetterti in qualsiasi momento.';

  @override
  String speakerWithId(String speakerId) {
    return 'Relatore $speakerId';
  }

  @override
  String get reviewNoDate => 'Nessuna';

  @override
  String get transcript => 'Trascrizione';

  @override
  String get deviceDiagnosticsUploadFailed => 'Could not send diagnostics to support. Please try again.';

  @override
  String get noFoldersAvailable => 'Nessuna cartella disponibile';

  @override
  String get addAppSelectCategory => 'Seleziona una categoria per la tua app';

  @override
  String get conversations => 'Conversazioni';

  @override
  String get upgradeToUnlimited => 'Aggiorna a illimitato';

  @override
  String get deleteFlowConfirmTitle => 'Eliminare il tuo account?';

  @override
  String get accountCutoverMigrationInProgressMessage =>
      'Il tuo account è in migrazione. Le funzioni del prodotto sono in pausa fino al termine della migrazione.';

  @override
  String get permissionAllowed => 'Consentito';

  @override
  String get pressDoneToSave => 'Premi fatto per salvare';

  @override
  String get listening => 'Ascolto';

  @override
  String get audioReady => 'Audio pronto';

  @override
  String get freeForEveryone => 'Gratuito per tutti';

  @override
  String get buildingKnowledgeGraphFromMemories => 'Costruzione del grafo della conoscenza dai ricordi…';

  @override
  String get onDeviceTranscription => 'Trascrizione sul dispositivo';

  @override
  String errorWithMessage(String error) {
    return 'Errore: $error';
  }

  @override
  String get chatAppsProblemOffline => 'Sei offline. Controlla la connessione e riprova.';

  @override
  String get callAlreadyInProgress => 'Una chiamata e gia in corso';

  @override
  String get reviewQuestionSpelling => 'Come si scrive?';

  @override
  String get firmwareStableConnection => 'Connessione stabile';

  @override
  String get categoryOther => 'Altro';

  @override
  String get perMonthLabel => '/ mese';

  @override
  String get onboardingYoureAllSet => 'Sei pronto';

  @override
  String get resumeRecording => 'Riprendi registrazione';

  @override
  String get feedbackSubtitleAudioQuality => 'Vorremmo capire cosa è andato storto.';

  @override
  String get speakerTagPromptPlayClip => 'Riproduci clip';

  @override
  String get anonymityAndPrivacy => 'Anonimato e privacy';

  @override
  String get noMemoriesToDelete => 'Nessun ricordo da eliminare';

  @override
  String get syncStepProcess => 'Trascrizione';

  @override
  String get callStateRinging => 'Squilla…';

  @override
  String get setupOnDevice => 'Configura sul dispositivo';

  @override
  String get creatorPayouts => 'Pagamenti ai creatori';

  @override
  String get olderDeviceDetected => 'Rilevato dispositivo più vecchio';

  @override
  String get deletePhoneNumberWarning => 'Dovrai verificare di nuovo per effettuare chiamate';

  @override
  String get appVisibilityChangedSuccessfully =>
      'Visibilità dell\'app modificata con successo. Potrebbero essere necessari alcuni minuti.';

  @override
  String get failedToCreateActionItem => 'Creazione attività non riuscita';

  @override
  String get msgSelectFilesGenericError => 'Errore nella selezione dei file. Si prega di riprovare.';

  @override
  String get pendantRecordingSyncBlocked =>
      'Il Pendant sta ancora registrando, quindi l\'audio memorizzato non può essere trasferito. Premi il pulsante del Pendant per interrompere la registrazione, poi sincronizza di nuovo.';

  @override
  String get failedToStartMerge => 'Impossibile avviare l\'unione';

  @override
  String get shortcutChangeInstruction => 'Fai clic su una scorciatoia per modificarla. Premi Escape per annullare.';

  @override
  String get notificationsAndDisplay => 'Notifiche e visualizzazione';

  @override
  String get getPaidThroughStripe => 'Ricevi pagamenti per le vendite delle tue app tramite Stripe';

  @override
  String get weekdayWed => 'Mer';

  @override
  String get send => 'Invia';

  @override
  String get nativeEngineNoDownload =>
      'Verrà utilizzato il motore vocale nativo del tuo dispositivo. Non è necessario scaricare un modello.';

  @override
  String get wrappedActions => 'azioni';

  @override
  String get conversationTimeoutConfig => 'Quanto tempo Omi aspetta in silenzio prima di terminare una conversazione';

  @override
  String get mic => 'Microfono';

  @override
  String deviceOnboardingVoiceReplyStatusAlwaysHeadphones(String device) {
    return 'Riproduce fino a $device.';
  }

  @override
  String failedToSendReply(String error) {
    return 'Impossibile inviare la risposta: $error';
  }

  @override
  String get whisperModelSizeTiny => 'Minuscolo';

  @override
  String get speakerTagPromptNotMeAction => 'Non sono io';

  @override
  String get setupInstructions => 'Istruzioni di configurazione';

  @override
  String get noLanguagesFound => 'Nessuna lingua trovata';

  @override
  String get experimental => 'Sperimentale';

  @override
  String get continueRecording => 'Continua registrazione';

  @override
  String get selectDefaultRepoDesc =>
      'Seleziona un repository predefinito per creare issue. Puoi comunque specificare un repository diverso durante la creazione di issue.';

  @override
  String sharedTasksTitle(String name, int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count attività',
      one: '1 attività',
    );
    return '$name ha condiviso $_temp0';
  }

  @override
  String get permissionsRequiredDesc =>
      'Questa app ha bisogno dei permessi Bluetooth e Posizione per funzionare correttamente. Abilitali nelle impostazioni.';

  @override
  String diagnosticsVerdictReconnectsDetail(String duration) {
    return 'Brevi interruzioni, torna in circa $duration ogni volta';
  }

  @override
  String get transferring => 'Trasferimento in corso…';

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '$used di $limit parole utilizzate questo mese';
  }

  @override
  String get noChatAppsEnabled => 'Nessuna app di chat abilitata.\nTocca \"Abilita app\" per aggiungerne.';

  @override
  String get tipKeepPhoneNearby => 'Tieni il telefono vicino per una sincronizzazione più veloce';

  @override
  String get authFailedToSignInWithGoogle => 'Accesso con Google non riuscito, riprova.';

  @override
  String get frequencyDescLow => 'Solo cose importanti, circa 3–5 al giorno';

  @override
  String get availableTemplates => 'Modelli disponibili';

  @override
  String get captureEveryMoment => 'Omi registra le tue conversazioni e scrive\nper te il riepilogo e le cose da fare.';

  @override
  String get migrationErrorOccurred => 'Si è verificato un errore durante la migrazione. Riprova.';

  @override
  String get wrappedCompletedLabel => 'Completato';

  @override
  String speakerTagPromptLabeledToast(String name) {
    return 'Etichettato come $name';
  }

  @override
  String get docs => 'Documentazione';

  @override
  String get dateTimeLabel => 'Data e ora';

  @override
  String get editFolder => 'Modifica cartella';

  @override
  String get apps => 'App';

  @override
  String segmentsSingular(String count) {
    return '$count segmento';
  }

  @override
  String get deviceSettings => 'Impostazioni Dispositivo';

  @override
  String get offline => 'Non in linea';

  @override
  String get createActionItemTooltip => 'Crea nuova attività';

  @override
  String get forgetDevice => 'Dimentica Dispositivo';

  @override
  String get reviewEntryTitle => 'Domande per te';

  @override
  String get enterEmailError => 'Inserisci la tua email';

  @override
  String get appDisabledOwnerHint => 'Correggi prima l\'endpoint: la riattivazione ricontrolla ogni URL configurato.';

  @override
  String get chatAppsIMessageSubtitle => 'Scrivi a Omi dal tuo numero di telefono';

  @override
  String get tasksExportedOneApp => 'Le attività possono essere esportate in un\'app alla volta.';

  @override
  String transcriptSpeakerCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count interlocutori',
      one: '1 interlocutore',
    );
    return '$_temp0';
  }

  @override
  String get saveGoal => 'Salva';

  @override
  String get noBatteryDataYet => 'Nessun dato sulla batteria ancora';

  @override
  String chatUsedOfLimitMessages(String used, String limit) {
    return '$used di $limit messaggi utilizzati questo mese';
  }

  @override
  String get backgroundActivityDesc => 'Così Omi continua a registrare a schermo spento o quando cambi app.';

  @override
  String get addAppUpdateFailed => 'Aggiornamento fallito. Riprova più tardi';

  @override
  String get noMatchingPeople => 'Nessuna Persona Corrispondente';

  @override
  String get unlinkCalendarEvent => 'Scollega evento del calendario';

  @override
  String get regenerateRecap => 'Rigenera il riepilogo';

  @override
  String get deleteSynced => 'Elimina sincronizzati';

  @override
  String get speakerTagPromptNameHint => 'Il suo nome';

  @override
  String get freePlan => 'Piano gratuito';

  @override
  String get installs => 'INSTALLAZIONI';

  @override
  String get publicLabel => 'Pubblico';

  @override
  String get deletingMessages => 'Eliminazione dei tuoi messaggi dalla memoria di Omi…';

  @override
  String get pendingFilesDeleted => 'Registrazioni in sospeso eliminate';

  @override
  String get checkUsage => 'Verifica Utilizzo';

  @override
  String get addWordsDesc => 'Nomi, termini o parole non comuni';

  @override
  String get entityCorrectionSaved => 'Grazie. Omi lo correggerà.';

  @override
  String get categoryEducation => 'Istruzione';

  @override
  String get planAndUsage => 'Piano e Utilizzo';

  @override
  String get deleteMemory => 'Elimina memoria';

  @override
  String get dataProtectionLevel => 'Livello di Protezione Dati';

  @override
  String timeDaySingular(int count) {
    return '$count giorno';
  }

  @override
  String get keyCreated => 'Chiave creata';

  @override
  String get date => 'Data';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return 'Migrazione di $itemType… $percentage%';
  }

  @override
  String get enableLocalStorage => 'Abilita archiviazione locale';

  @override
  String get omiSays => 'Omi says';

  @override
  String get appDetails => 'Dettagli App';

  @override
  String get loadingYourRecording => 'Caricamento della registrazione…';

  @override
  String get deleteAllLimitlessWarning =>
      'Tutte le conversazioni importate da Limitless verranno eliminate. Questa azione non può essere annullata.';

  @override
  String get combiningAudioFiles => 'Unione file audio…';

  @override
  String get suggestFollowUpQuestion => 'Suggerisci domanda di follow-up';

  @override
  String chatStarterPrompt(String kind) {
    String _temp0 = intl.Intl.selectLogic(
      kind,
      {
        'capabilities': 'Cosa puoi fare per me?',
        'goal': 'Aiutami a fissare un obiettivo',
        'activity': 'Riassumi le mie attività recenti',
        'improve': 'Come posso migliorare?',
        'other': '',
      },
    );
    return '$_temp0';
  }

  @override
  String get speakerTagPromptIgnoredNote => 'Omi non chiederà più di questa voce';

  @override
  String get recordWithPhoneInstead => 'Registra invece con il telefono';

  @override
  String get triggerEvent => 'Evento di attivazione';

  @override
  String get waitingForTranscriptOrPhotos => 'In attesa di trascrizione o foto…';

  @override
  String get omiApiKeys => 'Chiavi API Omi';

  @override
  String addNamedPersonAction(String name) {
    return 'Aggiungi “$name”';
  }

  @override
  String get enableDetailedDiagnosticMessages =>
      'Abilita messaggi diagnostici dettagliati dal servizio di trascrizione';

  @override
  String get nameCannotBeEmpty => 'Il nome non può essere vuoto';

  @override
  String get noTasksYet => 'Nessuna attività ancora';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'Prova a modificare i termini di ricerca o i filtri';

  @override
  String daySummaryForDate(String date) {
    return 'Riepilogo del giorno · $date';
  }

  @override
  String get statusTimedOut => 'Tempo scaduto';

  @override
  String chatUsageDescription(String used, String limitDisplay, String plan) {
    return 'Hai utilizzato $used dei tuoi $limitDisplay nel piano $plan.';
  }

  @override
  String get paypalMeLink => 'Link PayPal.me';

  @override
  String get allMemoriesPrivateResult => 'Tutti i ricordi sono ora privati';

  @override
  String get scanAgain => 'Cerca di nuovo';

  @override
  String get doItAgain => 'Rifai';

  @override
  String get reviewTitle => 'Revisione';

  @override
  String get photos => 'Foto';

  @override
  String get phoneNoVerifiedNumbersMessage => 'Verifica il tuo numero per chiamare tramite Omi.';

  @override
  String get save => 'Salva';

  @override
  String get deleteAccount => 'Elimina Account';

  @override
  String get managePaymentMethod => 'Gestisci metodo di pagamento';

  @override
  String get selectThumbnailImageTitle => 'Seleziona un\'immagine in miniatura';

  @override
  String get pairingTitleOmi => 'Accendi Omi';

  @override
  String get whatsYourPrimaryLanguage => 'Qual è la tua lingua principale?';

  @override
  String get replyToReview => 'Rispondi alla recensione';

  @override
  String failedToDeleteError(String error) {
    return 'Eliminazione fallita: $error';
  }

  @override
  String get newestFirst => 'Più recenti prima';

  @override
  String get wrappedCreatingYourStory => 'Creazione della tua\nstoria del 2025…';

  @override
  String get chatAppsPrivateMemories => 'Mantieni i ricordi privati nell\'app';

  @override
  String get pleaseEnterPayPalEmail => 'Inserisci il tuo indirizzo email PayPal';

  @override
  String get transcription => 'Trascrizione';

  @override
  String get yourReview => 'La tua recensione';

  @override
  String get filesDownloadedUploadedNextTime => 'I file già scaricati verranno caricati la prossima volta.';

  @override
  String get phoneSetupStep3Subtitle => 'Con trascrizione dal vivo integrata';

  @override
  String get mcpConnectionFailed => 'Connessione al server MCP non riuscita';

  @override
  String get chatAppsConnectTelegramTitle => 'Connetti Telegram';

  @override
  String get createMemoryTooltip => 'Crea nuovo ricordo';

  @override
  String get connectDeviceMessage =>
      'Connetti il tuo dispositivo Omi per accedere\nalle impostazioni e alla personalizzazione del dispositivo';

  @override
  String get authorizingMcpServer => 'Autorizzazione…';

  @override
  String charactersCount(int count) {
    return '$count caratteri';
  }

  @override
  String get syncStatusUploaded => 'Caricato · elaborazione su Omi';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'Per favore autenticati con $serviceName in Impostazioni > Integrazioni attività';
  }

  @override
  String get setDefaultButton => 'Imposta predefinita';

  @override
  String get resummarizingConversation => 'Nuovo riepilogo della conversazione…\nPotrebbe richiedere alcuni secondi';

  @override
  String estimatedHours(int count) {
    return '~$count ora/e';
  }

  @override
  String get chatAppsInsightsSubtitle => 'Lascia che Omi ti invii qui un riepilogo o uno spunto.';

  @override
  String get memoryAllowUse => 'Consenti l\'uso';

  @override
  String get model => 'Modello';

  @override
  String get memoryGraphTitle => 'Grafico dei ricordi';

  @override
  String get endpointURL => 'URL dell\'Endpoint';

  @override
  String get wrappedShareYourWrapped => 'Condividi il tuo Wrapped';

  @override
  String get micGainDescBoosted => 'Amplificato - per ambienti silenziosi';

  @override
  String get wrappedMinutes => 'minuti';

  @override
  String get language => 'Lingua';

  @override
  String downloadErrorWithMessage(String error) {
    return 'Errore di download: $error';
  }

  @override
  String get onboardingRatingPromptNo => 'No';

  @override
  String get whatWouldYouLikeToRemember => 'Cosa vorresti ricordare?';

  @override
  String get deviceOnboardingMuteUnmuteDesc => 'Attiva o disattiva il microfono';

  @override
  String secondsCount(int count) {
    return '$count secondi';
  }

  @override
  String get icon => 'Icona';

  @override
  String get realTimeTranscript => 'Trascrizione in Tempo Reale';

  @override
  String get deviceOnboardingVoiceReplySample => 'Ricevuto. La tua prossima riunione inizia tra venti minuti.';

  @override
  String get noDisconnectsRecorded => 'Nessuna disconnessione registrata';

  @override
  String get filterMyApps => 'Le mie app';

  @override
  String get recapRegenerateCooldown => 'Attendi qualche secondo prima di rigenerare.';

  @override
  String get templateName => 'Nome modello';

  @override
  String get retry => 'Riprova';

  @override
  String get sdCardSyncDescription =>
      'La sincronizzazione della scheda SD importerà i tuoi ricordi dalla scheda SD all\'app';

  @override
  String get deviceTutorial => 'Come usare Omi';

  @override
  String get noApiKeysCreateOne => 'Nessuna chiave API. Creane una per iniziare.';

  @override
  String siriShortcutsSetupHint(String askPhrase, String questionPhrase) {
    return 'Attiva Omi in Comandi rapidi → Siri. Dì “$askPhrase” o “$questionPhrase”, poi fai la tua domanda.';
  }

  @override
  String get failedToDeleteSomeItems => 'Impossibile eliminare alcuni elementi';

  @override
  String get raybanMetaSetupDescription =>
      'Usa i tuoi occhiali Ray-Ban Meta come dispositivo di acquisizione Omi per conversazioni e contesto visivo. Omi aprirà l\'app Meta AI per collegare i tuoi occhiali.';

  @override
  String get tabToDo => 'Da Fare';

  @override
  String get otaWifiFailed => 'Impossibile connettersi al Wi-Fi. Controlla nome della rete e password.';

  @override
  String get changePlan => 'Cambia piano';

  @override
  String copiedToClipboard(String title) {
    return '$title copiato negli appunti';
  }

  @override
  String get completeAuthBrowser => 'Completa l\'autenticazione nel tuo browser. Una volta fatto, torna all\'app.';

  @override
  String get migrationInProgressMessage =>
      'Migrazione in corso. Non puoi cambiare il livello di protezione finché non è completata.';

  @override
  String get keepSubscription => 'Mantieni abbonamento';

  @override
  String get playbackPreparingAudio => 'Preparazione dell\'audio…';

  @override
  String get cloudStorageDialogMessage =>
      'Le tue registrazioni in tempo reale saranno archiviate in uno spazio di archiviazione cloud privato mentre parli.';

  @override
  String get newChat => 'Nuova chat';

  @override
  String get paymentEnterAmountGreaterThanZero => 'Inserisci un importo maggiore di 0';

  @override
  String showAllPeople(int count) {
    return 'Mostra tutte le $count persone';
  }

  @override
  String deletePersonNamedTitle(String name) {
    return 'Eliminare $name?';
  }

  @override
  String get importTranscriptFiles => 'File di trascrizione';

  @override
  String get transcriptPlaceholder => 'La trascrizione apparira qui…';

  @override
  String get logShared => 'Log condiviso';

  @override
  String get deleteReasonNotUsing => 'Non lo uso abbastanza';

  @override
  String diagnosticsDropsPerHour(int count) {
    return 'circa $count all\'ora';
  }

  @override
  String get wrappedProcessingDefault => 'Elaborazione…';

  @override
  String get failedToConnectGoogleTasksRetry => 'Connessione a Google Tasks non riuscita. Riprova.';

  @override
  String get downloadingFromSdCard => 'Scaricamento dalla Scheda SD';

  @override
  String get firmwareFormatWarning =>
      'Questo firmware formatterà la scheda SD. Assicurati che tutti i dati offline siano sincronizzati prima dell\'aggiornamento.\n\nSe vedi una luce rossa lampeggiante dopo aver installato questa versione, non preoccuparti. Collega semplicemente il dispositivo all\'app e dovrebbe diventare blu. La luce rossa significa che l\'orologio del dispositivo non è ancora stato sincronizzato.';

  @override
  String get pleaseProvidePrompt => 'Si prega di fornire un prompt';

  @override
  String get voiceResponseAlways => 'Sempre';

  @override
  String get statusLabel => 'Stato';

  @override
  String get shareLogs => 'Condividi log';

  @override
  String get continueAnyway => 'Continua';

  @override
  String get transferCompleteMessage => 'Trasferimento completato! Ora puoi riprodurre questa registrazione.';

  @override
  String get reviewCaughtUpBody => 'Omi ti farà domande qui solo quando ha bisogno di te.';

  @override
  String get calculatingETA => 'Calcolo in corso…';

  @override
  String get speechProfileTopicWork => 'Che lavoro fai?';

  @override
  String get considerOmiCloud => 'Considera di usare Omi Cloud per prestazioni migliori.';

  @override
  String get testConversationPrompt => 'Testa un prompt di conversazione';

  @override
  String get deletePending => 'Elimina in sospeso';

  @override
  String get renameConversation => 'Rinomina';

  @override
  String get batteryDrainSignificantly => 'Il consumo della batteria aumenterà significativamente.';

  @override
  String get clear => 'Cancella';

  @override
  String get addAppEnterWebhookUrl => 'Inserisci un URL webhook per la tua app';

  @override
  String get active => 'Attivo';

  @override
  String get exportStartedMessage => 'Esportazione avviata. Potrebbero volerci alcuni secondi…';

  @override
  String get dataAccessNoticeDescription =>
      'I tuoi dati vengono elaborati in modo sicuro secondo le tue impostazioni sulla privacy';

  @override
  String get yourRequestUnderReview => 'La tua richiesta è in revisione';

  @override
  String get unresolvedSpeakersMessage =>
      'Omi non è riuscito a distinguere le altre voci tra le registrazioni. Tocca un\'etichetta di relatore per dare un nome a chi parla.';

  @override
  String downloadError(String error) {
    return 'Errore di download: $error';
  }

  @override
  String get offlineSync => 'Sincronizzazione offline';

  @override
  String get cancelSubscription => 'Annulla abbonamento';

  @override
  String get claudeDesktopConnectorSetup =>
      'Su Claude Desktop → Settings → Connectors, aggiungi un connettore personalizzato e incolla l\'URL del server. Se Claude richiede un Client ID OAuth avanzato, usa il valore qui sotto e lascia il segreto vuoto — non usare mai la tua chiave API MCP come segreto OAuth.';

  @override
  String get chatAppsTelegramWaiting => 'In attesa che tu tocchi Avvia in Telegram…';

  @override
  String get tryAgain => 'Riprova';

  @override
  String get syncStatusOnDevice => 'Sul tuo dispositivo';

  @override
  String get entityCorrectionTitle => 'Cosa non va?';

  @override
  String peopleDeletedToast(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count persone eliminate',
      one: '1 persona eliminata',
    );
    return '$_temp0';
  }

  @override
  String get features => 'Funzionalità';

  @override
  String get startEarning => 'Inizia a Guadagnare! 💰';

  @override
  String get enterYourNumber => 'Inserisci il tuo numero';

  @override
  String get addToClaudeCodeConfig => 'Aggiungi a ~/.claude.json';

  @override
  String get cleanDisconnect => 'Disconnessione pulita';

  @override
  String get grantContactsAccess => 'Concedi accesso ai tuoi contatti';

  @override
  String get feedbackReasonIncorrect => 'Errato o inventato';

  @override
  String get addAppErrorSelectingImageRetry => 'Errore nella selezione dell\'immagine. Riprova.';

  @override
  String get feedbackTitleNotUsing => 'Cosa ti farebbe usare Omi di più?';

  @override
  String get memories => 'Ricordi';

  @override
  String get capturingPhotos => 'Acquisizione foto';

  @override
  String get hideApiKey => 'Nascondi chiave API';

  @override
  String get signUpButton => 'Registrati';

  @override
  String get tuesdayAbbr => 'Mar';

  @override
  String get noApiKeys => 'Nessuna chiave API ancora';

  @override
  String get keyWord => 'Chiave';

  @override
  String reviewAnswersConversations(int count) {
    return 'Questa risposta etichetta $count conversazioni';
  }

  @override
  String get statusFailed => 'Fallito';

  @override
  String get installedApps => 'App installate';

  @override
  String get flashFirmware => 'Installa il firmware';

  @override
  String get conversationUrlCouldNotBeGenerated => 'L\'URL della conversazione non può essere generato.';

  @override
  String get reloadingApps => 'Ricaricamento app…';

  @override
  String get goalTitle => 'Titolo obiettivo';

  @override
  String get importantConversationTitle => 'Conversazione importante';

  @override
  String get byContinuingAgree => 'Continuando, accetti la nostra ';

  @override
  String get saturdayAbbr => 'Sab';

  @override
  String get subscriptionReactivatedDefault =>
      'Il tuo abbonamento è stato riattivato! Nessun addebito ora - sarai fatturato alla fine del periodo corrente.';

  @override
  String get tryLatestExperimentalFeatures => 'Prova le ultime funzionalità sperimentali dal team Omi.';

  @override
  String get chatAppsEntrySubtitle => 'Parla con Omi dalle app che usi ogni giorno.';

  @override
  String get transcriptionPaused => 'Registrazione, riconnessione';

  @override
  String get appleHealthFeatureReadOnlyTitle => 'Accesso in sola lettura';

  @override
  String get shareDataForTraining => 'Condividi i dati per l\'addestramento';

  @override
  String get noNotificationScopesAvailable => 'Nessun ambito di notifica disponibile';

  @override
  String disconnectFromApp(String appName) {
    return 'Disconnettere da $appName?';
  }

  @override
  String get failedToConnectGoogleTasks => 'Connessione a Google Tasks non riuscita';

  @override
  String get copyToClipboard => 'Copia negli appunti';

  @override
  String get stopRecordingConfirmation => 'Interrompere la registrazione e riassumere ora la conversazione?';

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'Impossibile generare il riepilogo. Assicurati di avere conversazioni per quel giorno.';

  @override
  String get monthlyLimitReached => 'Hai raggiunto il tuo limite mensile.';

  @override
  String get permissionsPageDescription =>
      'Omi usa queste autorizzazioni per connettersi al dispositivo, registrare audio, continuare a funzionare in background, inviare promemoria e annotare dove si sono svolte le conversazioni.';

  @override
  String get onboardingTellUsAboutYourself => 'Parlaci di te';

  @override
  String get deviceOnboardingAskQuestionSubtitle =>
      'Premi il pulsante una volta, fai la tua domanda, poi premi di nuovo quando hai finito';

  @override
  String get filters => 'Filtri';

  @override
  String get firmwareUpdateWarning =>
      'Non chiudere l\'app o spegnere il dispositivo. Questo potrebbe danneggiare il dispositivo.';

  @override
  String get oneSourceAtATime => 'Omi registra da una sola fonte alla volta.';

  @override
  String chatAppsConnectedAs(String handle) {
    return 'Connesso come $handle';
  }

  @override
  String get pilotFeatures => 'Funzionalità pilota';

  @override
  String get selectFirmwareZip => 'Seleziona il file ZIP del firmware';

  @override
  String get feedbackReasonRecordingPoorTranscription => 'Trascrizione scadente';

  @override
  String get deleteAccountFailed => 'Impossibile eliminare il tuo account. Riprova.';

  @override
  String get searchConversations => 'Cerca conversazioni';

  @override
  String get frequencyBalanced => 'Bilanciato';

  @override
  String get auto => 'Automatico';

  @override
  String get actionItemUpdatedSuccessfully => 'Attività aggiornata con successo';

  @override
  String get entityProjects => 'Progetti';

  @override
  String get signInWithApple => 'Accedi con Apple';

  @override
  String get backendUrlLabel => 'URL del server';

  @override
  String confidenceSummaryLikely(String name) {
    return 'Omi di solito riconosce la voce di $name, ma l\'hai confermata solo poche volte.';
  }

  @override
  String get entityOpenThreads => 'Questioni aperte';

  @override
  String get deleteActionItemMessage => 'Eliminare questa attività?';

  @override
  String chatWithApp(String appName) {
    return 'Chatta con $appName';
  }

  @override
  String get editActionItem => 'Modifica attività';

  @override
  String get cloudStorageEnabled => 'Archiviazione cloud abilitata';

  @override
  String get wrappedPersonalGrowth => 'Crescita personale';

  @override
  String get chatAppsProPerkSave => 'Salva ricordi e gestisci le attività direttamente dalla chat';

  @override
  String get alreadyHaveAccountLogin => 'Hai già un account? Accedi';

  @override
  String makeItemPublicQuestion(String item) {
    return 'Rendere $item pubblico?';
  }

  @override
  String get usagePeakHour => 'Peak hour';

  @override
  String get addWords => 'Aggiungi Parole';

  @override
  String get usageNow => 'now';

  @override
  String get usageMinutes => 'minuti';

  @override
  String availableSpace(String space) {
    return 'Spazio disponibile: $space';
  }

  @override
  String get providingSubtitle => 'Attività e note, acquisite automaticamente.';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% tasso di completamento';
  }

  @override
  String summaryGeneratedFor(String date) {
    return 'Riepilogo generato per $date';
  }

  @override
  String get selectCategory => 'Seleziona categoria';

  @override
  String nProcessed(int count) {
    return '$count elaborati';
  }

  @override
  String get privacyPolicyTitle => 'Informativa sulla privacy';

  @override
  String get deviceMayWarmUp => 'Il dispositivo potrebbe surriscaldarsi durante un uso prolungato.';

  @override
  String get designingApp => 'Progettazione app';

  @override
  String get couldNotLoadWhatsNew => 'Impossibile caricare le novità';

  @override
  String get doNotCloseApp => 'Non chiudere lapp.';

  @override
  String get voiceResponseAudio => 'Leggi la risposta di Omi ad alta voce';

  @override
  String get allTime => 'Sempre';

  @override
  String get developerSettingsTitle => 'Impostazioni Sviluppatore';

  @override
  String get restoreAction => 'Ripristina';

  @override
  String get phoneSetupStep3Title => 'Inizia a chiamare i tuoi contatti';

  @override
  String get anErrorOccurredTryAgain => 'Si è verificato un errore. Riprova.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'Ecco di cosa abbiamo appena discusso: $link';
  }

  @override
  String get playbackAudioLoadFailed => 'Impossibile caricare l\'audio';

  @override
  String get phoneMute => 'Muto';

  @override
  String get captureNotTranscribing => 'Nessuna trascrizione';

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return 'Registrazione interrotta: $reason. Potrebbe essere necessario ricollegare i display esterni o riavviare la registrazione.';
  }

  @override
  String get sttProviderDeepgram => 'Deepgram';

  @override
  String get spaceKey => 'Spazio';

  @override
  String get raybanMetaOpenMetaAI => 'Connetti tramite Meta AI';

  @override
  String get linkEvent => 'Collega evento';

  @override
  String get fairUse3Day => '3 giorni consecutivi';

  @override
  String failedToStartAppAuth(String appName) {
    return 'Impossibile avviare l\'autenticazione $appName';
  }

  @override
  String get processingOnServer => 'Elaborazione sul server…';

  @override
  String errorStartingRecording(String error) {
    return 'Errore durante l\'avvio della registrazione: $error';
  }

  @override
  String get quiet => 'Silenzioso';

  @override
  String get startConversationToSeeInsights =>
      'Inizia una conversazione con Omi\nper vedere le tue statistiche di utilizzo qui.';

  @override
  String get processAudio => 'Elabora audio';

  @override
  String get chatAppsConnectIMessageTitle => 'Scrivi a Omi per connetterti';

  @override
  String get chatWithOmi => 'Chatta con Omi';

  @override
  String get clickToBeginRecording => 'Fai clic per iniziare la registrazione';

  @override
  String get confirmAndProceed => 'Conferma e procedi';

  @override
  String get mondayAbbr => 'Lun';

  @override
  String sdCardProcessingMessage(int count) {
    return 'Elaborazione di $count registrazione/i. I file saranno rimossi dalla scheda SD al termine.';
  }

  @override
  String get chatReplyNotSignedIn => 'Non hai effettuato l\'accesso. Accedi e riprova.';

  @override
  String deviceOnboardingVoiceReplySettingsHint(String settings, String voiceResponse) {
    return 'Puoi modificarlo in qualsiasi momento al numero $settings › $voiceResponse';
  }

  @override
  String get wrappedGenerateMyWrapped => 'Genera il mio Wrapped';

  @override
  String get reviewChangesIntro =>
      'Cosa ha cambiato Omi da solo negli ultimi 30 giorni. Annulla tutto ciò che sembra sbagliato.';

  @override
  String get stripeReadyForPayments =>
      'Il tuo account Stripe è ora pronto a ricevere pagamenti. Puoi iniziare a guadagnare dalle vendite delle tue app subito.';

  @override
  String get appleWatchSetup => 'Configurazione Apple Watch';

  @override
  String get failedToDisconnect => 'Impossibile disconnettere';

  @override
  String get localStorageEnabled => 'Archiviazione locale abilitata';

  @override
  String get captureSourceDesktop => 'Computer';

  @override
  String get serialNumber => 'Numero di serie';

  @override
  String get appleHealthFeatureSecureDesc =>
      'I tuoi dati Apple Health si sincronizzano privatamente con il tuo account Omi.';

  @override
  String get tryAdjustingSearch => 'Prova a modificare la tua ricerca o i filtri';

  @override
  String connectTo(String appName) {
    return 'Connetti a $appName';
  }

  @override
  String get exportConversationsDescription => 'Esporta conversazioni in JSON';

  @override
  String get featuredLabel => 'IN EVIDENZA';

  @override
  String get speechProfile => 'Profilo vocale';

  @override
  String get integrations => 'Integrazioni';

  @override
  String get hideCompletedTasks => 'Nascondi completate';

  @override
  String get sendRawAudioToOmi => 'Invia l\'audio grezzo a Omi';

  @override
  String ratingsCount(String count) {
    return '$count+ valutazioni';
  }

  @override
  String get exportShared => 'Esportazione condivisa';

  @override
  String get conversationTimeout => 'Timeout Conversazione';

  @override
  String get installStableFirmware => 'Installa firmware stabile';

  @override
  String get secureAndReliable => 'Sicuro e affidabile';

  @override
  String get exportingConversations => 'Esportazione conversazioni…';

  @override
  String get feedbackReasonRecordingFragmentedOrDuplicated => 'Frammentato o duplicato';

  @override
  String get chatAppsWaitingMessage =>
      'Invia il messaggio in Messaggi. Questa schermata si aggiorna appena Omi lo riceve.';

  @override
  String get onboardingSetupStepWorkspace => 'Preparazione del tuo spazio di lavoro';

  @override
  String get recap => 'Riepilogo';

  @override
  String get lessThanAMinute => 'Meno di un minuto';

  @override
  String get tasks => 'Attività';

  @override
  String get onboardingSetupStepDevices => 'Connessione dei tuoi dispositivi';

  @override
  String pinPersonTitle(String name) {
    return 'Fissa $name';
  }

  @override
  String get wrappedButYouPushedThrough => 'Ma ce l\'hai fatta 💪';

  @override
  String get fetchingYourAppDetails => 'Recupero dei dettagli della tua app';

  @override
  String get timeout2MinutesDesc => 'Termina conversazione dopo 2 minuti di silenzio';

  @override
  String get otaUpdateCancelled => 'Aggiornamento annullato';

  @override
  String get usageTasksNotes => 'Tasks & notes';

  @override
  String get deviceNotConnected => 'Dispositivo Non Connesso';

  @override
  String get rayBanMetaMicPickerEmpty =>
      'Nessun microfono Bluetooth trovato. Collega gli occhiali nelle Impostazioni dell\'iPhone e riprova.';

  @override
  String get actionItemCompleted => 'Attività completata';

  @override
  String get usageSocialSettings => 'In contesti sociali';

  @override
  String get from => 'dalle';

  @override
  String get siriIndexSetting => 'Use Omi with Siri & Apple Intelligence';

  @override
  String get reviewReasonNotMine => 'Non è mia';

  @override
  String connectToDeviceName(String deviceName) {
    return 'Connetti a $deviceName';
  }

  @override
  String get onboardingComplete => 'Completato';

  @override
  String get chatAppsShowInApp => 'Mostra queste chat nell\'app Omi';

  @override
  String nCompleted(int count) {
    return '$count completate';
  }

  @override
  String get feedbackAllGood => 'Tutto ok';

  @override
  String get syncCardUploadingTitle => 'Caricamento su Omi';

  @override
  String get baselineMemory => 'Memoria di base';

  @override
  String get trainFamilyProfilesDesc =>
      'Le tue registrazioni ci aiutano a riconoscere e creare profili per i tuoi amici e familiari.';

  @override
  String get failedToGenerateShareLink => 'Generazione del link di condivisione non riuscita';

  @override
  String get onlyYouCanSeeConversation => 'Solo tu puoi vedere questa conversazione';

  @override
  String get popular => 'Popolare';

  @override
  String get captureRecordingSeparate => 'Separa…';

  @override
  String get allTemplates => 'Tutti i modelli';

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
  String speakerTagPromptSavedAs(String name) {
    return 'Salvato come $name';
  }

  @override
  String get configureSettings => 'Configura Impostazioni';

  @override
  String get noRatings => 'nessuna valutazione';

  @override
  String resumingInCountdown(String countdown) {
    return 'Ripresa tra ${countdown}s…';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 Ricordato $count ricordi';
  }

  @override
  String get clearDueDate => 'Cancella data di scadenza';

  @override
  String get copy => 'Copia';

  @override
  String get showPhoneCallButtonDesc => 'Mostra il pulsante di chiamata telefonica nella schermata principale';

  @override
  String get appleHealthFeatureReadOnlyDesc => 'Omi non scrive mai in Apple Health né modifica i tuoi dati.';

  @override
  String get multipleSpeakersDescription =>
      'Sembra che ci siano più interlocutori nella registrazione. Assicurati di essere in un luogo tranquillo e riprova.';

  @override
  String get failedToUpdateDueDate => 'Impossibile aggiornare la data di scadenza';

  @override
  String get successfullyConnectedWhoop => 'Connesso con successo a Whoop!';

  @override
  String get categories => 'Categorie';

  @override
  String get loadingTranscript => 'Caricamento della trascrizione…';

  @override
  String get syncCustomSttWarningMessage =>
      'Usi un tuo fornitore di trascrizione. Sincronizzare queste registrazioni le trascrive sui server di Omi e contano per il limite di trascrizione del tuo piano.';

  @override
  String get newRecording => 'Nuova registrazione';

  @override
  String get transcriptionUnavailableRecordingSaved =>
      'Trascrizione non disponibile — la registrazione continua e l\'audio viene salvato.';

  @override
  String get submittingYourApp => 'Invio della tua app in corso…';

  @override
  String get failedToLinkCalendarEvent => 'Impossibile collegare l\'evento del calendario';

  @override
  String get paypalMeLinkHint => 'paypal.me/nik';

  @override
  String get yourInformation => 'Le Tue Informazioni';

  @override
  String get accountDeletionInProgressSignInAgain =>
      'Questo account è in fase di eliminazione. Accedi con un altro account oppure attendi qualche minuto e riprova.';

  @override
  String get on => 'On';

  @override
  String get diagnostics => 'Diagnostica';

  @override
  String get errorCopied => 'Messaggio di errore copiato negli appunti';

  @override
  String get lovingOmi => 'Ti piace Omi?';

  @override
  String get permissionDescReadMemories => 'Questa app può accedere ai tuoi ricordi.';

  @override
  String get doNotIncludeHttpInLink => 'Non includere http o https o www nel link';

  @override
  String get shareRecording => 'Condividi registrazione';

  @override
  String get memoryReviewFix => 'Correggi';

  @override
  String get selectedPlanNotAvailable => 'Il piano selezionato non è disponibile. Riprova.';

  @override
  String get autoCreateWhenDetected => 'Crea automaticamente quando viene rilevato il nome';

  @override
  String get addAppSelectCapability => 'Seleziona almeno una capacità per la tua app';

  @override
  String get showPassword => 'Mostra password';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Le conversazioni termineranno ora dopo $minutes minuto/i di silenzio';
  }

  @override
  String get updateAvailableMessage => 'È pronta una nuova versione di Omi, con correzioni e miglioramenti.';

  @override
  String get nameMustBeBetweenCharacters => 'Il nome deve essere compreso tra 2 e 40 caratteri';

  @override
  String operatorSubtitle(int count) {
    return '$count domande al mese';
  }

  @override
  String conversationsDeletedCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count conversazioni eliminate',
      one: '1 conversazione eliminata',
    );
    return '$_temp0';
  }

  @override
  String get monthlyPayoutsDescription =>
      'Ricevi pagamenti mensili direttamente sul tuo conto quando raggiungi \$10 di guadagni';

  @override
  String get dailyScoreExplanation =>
      'Il tuo punteggio giornaliero si basa sul completamento delle attività. Completa le tue attività per migliorare il punteggio!';

  @override
  String get improveConnectionContent =>
      'Abbiamo migliorato il modo in cui Omi rimane connesso al tuo dispositivo. Per attivarlo, vai alla pagina Info dispositivo, tocca \"Disconnetti dispositivo\" e associa nuovamente il tuo dispositivo.';

  @override
  String get syncingRecordings => 'Sincronizzazione registrazioni';

  @override
  String get professionProductManager => 'Product Manager';

  @override
  String get nameMustBeAtLeast2Characters => 'Il nome deve contenere almeno 2 caratteri';

  @override
  String get conversationTitle => 'Titolo della conversazione';

  @override
  String mcpServerConnected(int count) {
    return '$count strumenti connessi con successo';
  }

  @override
  String get feedbackSubtitleNotUsing => 'Vogliamo rendere Omi più utile per te.';

  @override
  String get exportBeforeDelete =>
      'Puoi esportare i tuoi dati prima di eliminare il tuo account, ma una volta eliminato, non può essere recuperato.';

  @override
  String deleteTasksTitle(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Eliminare $count attività?',
      one: 'Eliminare 1 attività?',
    );
    return '$_temp0';
  }

  @override
  String get frequencyMaximum => 'Massimo';

  @override
  String get cancelReasonSubtitle => 'Puoi dirci perché stai andando via?';

  @override
  String get generatingIconStep => 'Generazione icona';

  @override
  String get storeAudioDescription =>
      'Mantieni tutte le registrazioni audio memorizzate localmente sul tuo telefono. Quando disabilitato, vengono conservati solo i caricamenti non riusciti per risparmiare spazio.';

  @override
  String get unpairDeviceConfirmTitle => 'Dissociare il dispositivo?';

  @override
  String get phoneCallsMaybeLater => 'Forse più tardi';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'Si è verificato un errore: $message';
  }

  @override
  String get yourPrivacyMattersToUs => 'La tua privacy è importante per noi';

  @override
  String get collapseAction => 'Comprimi';

  @override
  String get friendWordOfMouth => 'Amico';

  @override
  String get deviceOnboardingVoiceReplyStatusHeadphonesDisconnected =>
      'Nessuna cuffia collegata. Omi rimane silenzioso finché non ne colleghi qualcuno.';

  @override
  String get connectDevice => 'Connetti Dispositivo';

  @override
  String get deviceId => 'ID dispositivo';

  @override
  String get addWordsDescription => 'Aggiungi parole che Omi dovrebbe riconoscere durante la trascrizione.';

  @override
  String get userId => 'ID Utente';

  @override
  String evidenceCardConfirms(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Sì a $count suggerimenti',
      one: 'Sì a 1 suggerimento',
    );
    return '$_temp0';
  }

  @override
  String segmentsCount(int count) {
    return '$count segmenti';
  }

  @override
  String get permissionsSetupTitle => 'Ottieni la migliore esperienza';

  @override
  String get permissionTypeAccess => 'Accesso';

  @override
  String get speakerTagPromptSaveVoicesBody =>
      'Omi conserva un breve campione vocale per riconoscerli la prossima volta. Puoi cambiare questa opzione quando vuoi nelle Impostazioni.';

  @override
  String get developerApi => 'API sviluppatore';

  @override
  String get chargingIssues => 'Problemi di ricarica';

  @override
  String get debugAndDiagnostics => 'Debug e Diagnostica';

  @override
  String get failedConnections => 'Connessioni non riuscite';

  @override
  String get userIdCopied => 'ID utente copiato negli appunti';

  @override
  String get cannotReportOwnMessage => 'Non puoi segnalare i tuoi stessi messaggi.';

  @override
  String get latestVersion => 'Ultima versione';

  @override
  String get feedbackReasonNotHelpful => 'Non utile o non pertinente';

  @override
  String get deletePeopleMessage =>
      'Questo rimuove i loro campioni vocali e non può essere annullato. Le loro battute nelle conversazioni passate diventano interlocutori senza nome.';

  @override
  String get deviceOnboardingAllSetSubtitle => 'Tocca una riga per rivederla o modificarla.';

  @override
  String get mergeConversations => 'Unisci Conversazioni';

  @override
  String get paused => 'In pausa';

  @override
  String get updateGuide => 'Guida all\'aggiornamento';

  @override
  String cancelBillingPeriodInfo(String date) {
    return 'Il tuo piano rimarrà attivo fino al $date. Dopo sarai trasferito alla versione gratuita con funzionalità limitate.';
  }

  @override
  String get reconnectingToInternet => 'Riconnessione a internet…';

  @override
  String get allFilesDeleted => 'Tutte le registrazioni eliminate';

  @override
  String get paypalEmailHint => 'nik@example.com';

  @override
  String get oneWeekAgo => '1 settimana fa';

  @override
  String get deviceOnboardingAllSetSinglePressBadge => '1×';

  @override
  String get playbackAudioUnavailable => 'Audio non disponibile';

  @override
  String get deviceOnboardingTryDoubleTap => 'Provalo ora! Tocca due volte il tuo Omi';

  @override
  String get deleteReasonPrivacy => 'Problemi di privacy';

  @override
  String get cleanUpPinnedNote => 'Le persone fissate non sono mai incluse in Riordina.';

  @override
  String get wrappedProductiveDay => 'Produttivo';

  @override
  String get voiceSharedAcrossDevices => 'La voce scelta è condivisa tra mobile e desktop.';

  @override
  String get knowledgeGraphDeleted => 'Grafico della conoscenza eliminato';

  @override
  String get pressDoneToCreate => 'Premi fatto per creare';

  @override
  String get cloudStorage => 'Archivio cloud';

  @override
  String get howDoesItWork => 'Come funziona?';

  @override
  String get submitApp => 'Invia App';

  @override
  String get searchMemories => 'Cerca ricordi';

  @override
  String get fallNotificationTitle => 'Ahi';

  @override
  String storedOnDevice(String deviceName) {
    return 'Memorizzato su $deviceName';
  }

  @override
  String get contactsPermissionRequired => 'Autorizzazione contatti richiesta';

  @override
  String get reviewUpdatedSuccessfully => 'Recensione aggiornata con successo 🚀';

  @override
  String get pleaseEnterPayPalMeLink => 'Inserisci il tuo link PayPal.me';

  @override
  String get notHelpful => 'Non utile';

  @override
  String get recordingsToSync => 'Registrazioni da sincronizzare';

  @override
  String get categoryUtilities => 'Utilità';

  @override
  String get exportStarted => 'Esportazione avviata. Potrebbe richiedere alcuni secondi…';

  @override
  String get deviceOnboardingVoiceReplyStatusOff =>
      'Omi resterà in silenzio. Le risposte continuano ad essere visualizzate nell\'app.';

  @override
  String get myGoal => 'Il mio obiettivo';

  @override
  String timeHourSingular(int count) {
    return '$count ora';
  }

  @override
  String get chatToolsManifestUrl => 'URL del manifest degli strumenti chat';

  @override
  String msgSelectFilesError(String error) {
    return 'Errore nella selezione dei file: $error';
  }

  @override
  String connectedToApp(String appName) {
    return 'Connesso a $appName';
  }

  @override
  String get entityCorrectionHint => 'Dì a Omi cosa correggere';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch connesso con successo!';

  @override
  String appIntegration(String appName) {
    return 'Integrazione $appName';
  }

  @override
  String get cancelReasonAudioQuality => 'Qualità audio/trascrizione';

  @override
  String get invalidProviderInConfig => 'Provider non valido nella configurazione';

  @override
  String get deselectAll => 'Deseleziona Tutto';

  @override
  String get chatAppsCodeExpiredMessage => 'Ottieni un nuovo codice e invialo da Messaggi.';

  @override
  String get reviewAnswerFailed => 'Impossibile salvare la risposta. Riprova.';

  @override
  String get categorySocial => 'Sociale';

  @override
  String get rating4PlusStars => '4+ stelle';

  @override
  String get couldNotOpenSmsApp => 'Impossibile aprire l\'app SMS. Riprova.';

  @override
  String get chatAppsNoMessages => 'Nessun messaggio';

  @override
  String get wrappedCelebrity => 'CELEBRITÀ';

  @override
  String get revokeKeyQuestion => 'Revocare la chiave?';

  @override
  String timeMinsAndSecs(int mins, int secs) {
    return '$mins min $secs sec';
  }

  @override
  String get searchContactsHint => 'Cerca contatti';

  @override
  String get showEventsWithoutParticipants => 'Mostra Eventi Senza Partecipanti';

  @override
  String get fair => 'Discreto';

  @override
  String get tipAutoSync => 'Le registrazioni si sincronizzano automaticamente';

  @override
  String get summaryCopiedToClipboard => 'Riepilogo copiato negli appunti';

  @override
  String get clearSearch => 'Cancella ricerca';

  @override
  String get speakerTagPromptNotAPerson => 'Non una persona';

  @override
  String get modelLabel => 'Modello';

  @override
  String deleteItemQuestion(String item) {
    return 'Eliminare $item?';
  }

  @override
  String get enterPromoCode => 'Inserisci il codice promozionale';

  @override
  String get phoneNoContactsFound => 'Nessun contatto trovato';

  @override
  String countRemaining(String count) {
    return '$count rimanenti';
  }

  @override
  String get manageYourApp => 'Gestisci la tua app';

  @override
  String get willSyncAutomatically => 'verrà sincronizzato automaticamente';

  @override
  String get promoCode => 'Codice promozionale';

  @override
  String get trackPersonalGoalsOnHomepage => 'Monitora i tuoi obiettivi personali nella homepage';

  @override
  String get memoryHistoryPartial =>
      'Parte della cronologia dei ricordi non è disponibile. Viene mostrata la cronologia ricevuta finora.';

  @override
  String get sharePublicLink => 'Condividi link pubblico';

  @override
  String get conversationTab => 'Conversazione';

  @override
  String get backgroundModeDescription =>
      'Mantieni il tuo Omi in registrazione anche quando l\'app è completamente chiusa.';

  @override
  String get pairingDescOmiDevkit =>
      'Premi il pulsante una volta per accendere. Il LED lampeggerà in viola in modalità di accoppiamento.';

  @override
  String get callStateFailed => 'Chiamata fallita';

  @override
  String get githubRepositoryUrlHint => 'Link al repository del codice sorgente dell\'app';

  @override
  String get appIconLabel => 'App Icon';

  @override
  String get uninstallApp => 'Disinstalla app';

  @override
  String get confidenceReasonNeedsVoice => 'nessun campione vocale ancora';

  @override
  String get couldNotLoadApiKeys => 'Impossibile caricare le chiavi API.';

  @override
  String get fetchingStableFirmware => 'Recupero dell\'ultimo firmware stabile…';

  @override
  String get onDeviceModelDownloaded => 'Scaricato';

  @override
  String get noAPIKeys => 'Nessuna chiave API. Creane una per iniziare.';

  @override
  String get phoneCallsUpsellFeature3 => 'I destinatari vedono il tuo vero numero, non uno casuale';

  @override
  String get wrappedMovieRecs => 'Consigli di film per amici';

  @override
  String msgFilePickerError(String error) {
    return 'Errore nell\'apertura del selettore file: $error';
  }

  @override
  String get professionEntrepreneur => 'Imprenditore';

  @override
  String get recent => 'Recenti';

  @override
  String get permissionDescCreateMemories => 'Questa app può creare nuovi ricordi.';

  @override
  String get tapToComplete => 'Tocca per completare';

  @override
  String vocabularyWordCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count parole',
      one: '1 parola',
    );
    return '$_temp0';
  }

  @override
  String get deleteSyncedFilesMessage =>
      'Queste registrazioni sono già state sincronizzate con il tuo telefono. Questa azione non può essere annullata.';

  @override
  String get cancelConsequenceSpeakers => 'Non può identificare i parlanti.';

  @override
  String get aiGenFailedToGenerateApp => 'Impossibile generare l\'app. Riprova.';

  @override
  String get account => 'Account';

  @override
  String get capabilityIntegrations => 'Integrazioni';

  @override
  String get voiceSettingsAskToTag => 'Chiedimi di etichettare le voci';

  @override
  String get chatAppsHeroTitle => 'Chatta con Omi dove già chatti';

  @override
  String get myApps => 'Creato da me';

  @override
  String get deleteRecap => 'Elimina riepilogo';

  @override
  String get production => 'Produzione';

  @override
  String get phoneRecordingBlockedByPendantBatch =>
      'Interrompi Transcribe Later sul pendente prima di registrare con il telefono.';

  @override
  String dataRateKbps(String rate) {
    return '$rate kbps';
  }

  @override
  String get createAKeyToGetStarted => 'Crea una chiave per iniziare';

  @override
  String get pleaseSelectRating => 'Seleziona una valutazione';

  @override
  String get pdfTranscriptExport => 'Esportazione trascrizione';

  @override
  String get newFolder => 'Nuova cartella';

  @override
  String get fallNotificationBody => 'Sei caduto?';

  @override
  String get scopeUserChat => 'Chat utente';

  @override
  String get tryDifferentSearchTerm => 'Prova un termine di ricerca diverso';

  @override
  String get submit => 'Invia';

  @override
  String get deviceOnboardingVoiceReplySubtitle =>
      'Quando chiedi con il pulsante, Omi può leggere la sua risposta ad alta voce.';

  @override
  String get showOnLockScreen => 'Mostra sulla schermata di blocco';

  @override
  String get msgMaxImagesLimit => 'Puoi selezionare solo fino a 4 immagini';

  @override
  String get wrappedOmiLifeRecap => 'Riepilogo vita Omi';

  @override
  String get nextButton => 'Avanti';

  @override
  String disconnectAppTitle(String appName) {
    return 'Disconnettere $appName?';
  }

  @override
  String get updateReview => 'Aggiorna recensione';

  @override
  String get noMemoriesInCategory => 'Nessuna memoria in questa categoria ancora';

  @override
  String get memoryDeleted => 'Ricordo Eliminato';

  @override
  String get connectOmiDevice => 'Collega dispositivo Omi';

  @override
  String get professionSoftwareEngineer => 'Ingegnere del software';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'Tagga altri segmenti di questo speaker ($selected/$total)';
  }

  @override
  String get productName => 'Nome prodotto';

  @override
  String get permissionDeniedForAppleReminders => 'Permesso negato per Apple Reminders';

  @override
  String get allMemoriesAreNowPrivate => 'Tutti i ricordi sono ora privati';

  @override
  String planSetToCancelOn(String date) {
    return 'Il tuo piano è impostato per essere annullato il $date.\nRiabbonati ora per mantenere i tuoi benefici - nessun addebito fino al $date.';
  }

  @override
  String get deletePersonTitle => 'Eliminare la persona?';

  @override
  String deleteItemConfirmation(String item) {
    return '$item verrà eliminata. Questa azione non può essere annullata.';
  }

  @override
  String get appleHealthConnectCta => 'Connetti ad Apple Health';

  @override
  String segmentsPlural(String count) {
    return '$count segmenti';
  }

  @override
  String get syncCardDownloadingTitle => 'Download dal tuo dispositivo';

  @override
  String additionalSampleIndex(String index) {
    return 'Campione aggiuntivo $index';
  }

  @override
  String get descriptionLabel => 'Descrizione';

  @override
  String get failedToClearDueDate => 'Impossibile cancellare la data di scadenza';

  @override
  String get timeout4HoursDesc => 'Termina conversazione dopo 4 ore di silenzio';

  @override
  String get noSyncedRecordingsYet => 'Nessuna registrazione sincronizzata';

  @override
  String dreamReportDropped(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count modifiche meno recenti saltate',
      one: '1 modifica meno recente saltata',
    );
    return '$_temp0';
  }

  @override
  String get claudeCode => 'Claude Code';

  @override
  String get noPendingRecordings => 'Nessuna registrazione in attesa';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'Dicci come vorresti essere chiamato. Questo aiuta a personalizzare la tua esperienza Omi.';

  @override
  String get updateSummaryWithNewNames => 'Aggiorna il riepilogo con i nuovi nomi';

  @override
  String get setWhenConversationsAutoEnd => 'Quanto tempo Omi aspetta in silenzio prima di terminare una conversazione';

  @override
  String get successfullyConnectedGoogleTasks => 'Connesso con successo a Google Tasks!';

  @override
  String get confirmUpgrade => 'Conferma aggiornamento';

  @override
  String get speechToTextProviderDesc => 'Seleziona il servizio utilizzato per la trascrizione';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Errore durante la connessione all\'Apple Watch: $error';
  }

  @override
  String get instagram => 'Instagram';

  @override
  String sampleNumber(int number) {
    return 'Campione $number';
  }

  @override
  String get popularApps => 'App popolari';

  @override
  String get micGainDescSlightlyBoosted => 'Leggermente amplificato - uso normale';

  @override
  String get promptMustBeAtLeast10Characters => 'Il prompt deve essere di almeno 10 caratteri';

  @override
  String get chatAppsEntryRowSubtitle => 'Telegram, iMessage e altro';

  @override
  String get estimatedSizeLabel => 'Dimensione stimata';

  @override
  String get mcpServerDesc => 'Connetti assistenti AI ai tuoi dati';

  @override
  String get disconnectHistory => 'Cronologia disconnessioni';

  @override
  String get downgradeLimitDelay => 'Ritardo di 5-7 secondi';

  @override
  String get msgSelectImagesGenericError => 'Errore nella selezione delle immagini. Si prega di riprovare.';

  @override
  String get audioPlaybackUnavailable => 'Il file audio non è disponibile per la riproduzione';

  @override
  String get byClickingConnectNow => 'Cliccando su \"Connetti ora\" accetti il';

  @override
  String get signalStrength => 'Intensità del segnale';

  @override
  String get tellUsPrimaryLanguage => 'Dicci la tua lingua principale';

  @override
  String get diagnosticsShareFailed => 'Impossibile condividere la diagnostica. Riprova.';

  @override
  String get createKeyToStart => 'Crea una chiave per iniziare';

  @override
  String generatedBy(String appName) {
    return 'Generato da $appName';
  }

  @override
  String shareStatsListened(String minutes) {
    return '🎧 Ascoltato per $minutes minuti';
  }

  @override
  String get getOmiDevice => 'Ottieni dispositivo Omi';

  @override
  String get newTask => 'Nuova attività';

  @override
  String get conversationPrompt => 'Prompt di conversazione';

  @override
  String get otaWifiConnected => 'Connesso al Wi-Fi';

  @override
  String get dismiss => 'Ignora';

  @override
  String get webhooks => 'Webhook';

  @override
  String get raybanMetaCamera => 'Fotocamera';

  @override
  String get recapRegenerateNoConversations => 'Nessuna conversazione da riepilogare per questo giorno.';

  @override
  String pendantMinutesStored(int minutes) {
    return '~$minutes min memorizzati';
  }

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName disconnesso';
  }

  @override
  String get normal => 'Normale';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch ancora non raggiungibile. Assicurati che l\'app Omi sia aperta sul tuo orologio.';

  @override
  String get connectionGuide => 'Guida alla connessione';

  @override
  String get syncStepProcessDesc => 'Omi trasforma l\'audio in una conversazione';

  @override
  String get couldNotLoadPlans => 'Impossibile caricare i piani disponibili. Riprova.';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '$used di $limit min utilizzati questo mese';
  }

  @override
  String get learnMoreLink => 'scopri di più';

  @override
  String get unpairDeviceDialogMessage =>
      'Questo disaccoppierà il dispositivo in modo che possa essere connesso a un altro telefono. Dovrai andare in Impostazioni > Bluetooth e dimenticare il dispositivo per completare il processo.';

  @override
  String get authFailedToRetrieveToken => 'Impossibile recuperare il token Firebase, riprova.';

  @override
  String get aiGenFailedToCreateApp => 'Impossibile creare l\'app';

  @override
  String get appAndDeviceCopied => 'Dettagli app e dispositivo copiati';

  @override
  String get noProcessedRecordings => 'Nessuna registrazione elaborata ancora';

  @override
  String get transcriptTab => 'Trascrizione';

  @override
  String get permissionDescReadConversations => 'Questa app può accedere alle tue conversazioni.';

  @override
  String get tryAnotherApp => 'Prova un\'altra app';

  @override
  String get subscriptionSetToCancel => 'Il tuo abbonamento è impostato per essere annullato alla fine del periodo.';

  @override
  String chatAppsCodeExpiresIn(String time) {
    return 'Il codice scade tra $time';
  }

  @override
  String get authFailedToSignInWithApple => 'Accesso con Apple non riuscito, riprova.';

  @override
  String get feedbackReasonIgnoredInstructions => 'Non ha seguito le istruzioni';

  @override
  String get startupFailedDetails => 'Dettagli';

  @override
  String get deleteMeetingScreenshotTitle => 'Eliminare lo screenshot?';

  @override
  String get chatAppsNotConnectedMessage => 'Questa app di chat è stata disconnessa.';

  @override
  String get aboutOmiApiKeys => 'Informazioni sulle chiavi API Omi';

  @override
  String get tiktok => 'TikTok';

  @override
  String get maxFilesLimit => 'Puoi caricare solo 4 file alla volta';

  @override
  String get legalNotice =>
      'Avviso Legale: La legalità della registrazione e dell\'archiviazione dei dati vocali può variare a seconda della tua posizione e di come utilizzi questa funzione. È tua responsabilità garantire la conformità con le leggi e i regolamenti locali.';

  @override
  String get wrappedYourTopDays => 'I tuoi giorni migliori';

  @override
  String get addMcpServer => 'Aggiungi server MCP';

  @override
  String publicAppsCount(String count) {
    return 'App pubbliche ($count)';
  }

  @override
  String get noExternalAppsHaveAccess => 'Nessuna app esterna ha accesso ai tuoi dati.';

  @override
  String get captureStarting => 'Avvio…';

  @override
  String get downloadingAudioProgress => 'Download audio';

  @override
  String get audioBytes => 'Byte Audio';

  @override
  String batteryLevelSemantics(int level) {
    return 'Batteria $level%';
  }

  @override
  String captureRecordedBy(String devices) {
    return 'Registrato da $devices';
  }

  @override
  String get chatAppsRepliesOnlyNote => 'Omi risponde solo a te. Non scrive mai per primo.';

  @override
  String get hideTranscript => 'Nascondi trascrizione';

  @override
  String get permissionReadConversations => 'Leggi conversazioni';

  @override
  String get installed => 'Installato';

  @override
  String get paymentEnterValidAmount => 'Inserisci un importo valido';

  @override
  String get sttLanguageOverride => 'Sostituisci';

  @override
  String get appInterfaceSectionTitle => 'Interfaccia app';

  @override
  String get searchLanguages => 'Cerca lingue';

  @override
  String get otherSource => 'Altro';

  @override
  String get pairingDescOmiGlass => 'Tieni premuto il pulsante laterale per 3 secondi per accendere.';

  @override
  String get signOut => 'Disconnetti';

  @override
  String shareStatsWords(String words) {
    return '🧠 Compreso $words parole';
  }

  @override
  String verifiedDaysAgo(int days) {
    return 'Verificato ${days}g fa';
  }

  @override
  String get captureModeLater => 'Più tardi';

  @override
  String get enableMoreApps => 'Abilita più app';

  @override
  String get frequencyDescBalanced => 'Suggerimenti utili, circa 5–8 al giorno';

  @override
  String get startYourFirstRecording => 'Inizia la tua prima registrazione';

  @override
  String get transcriptionPausedReconnecting => 'Registrazione in corso — riconnessione alla trascrizione…';

  @override
  String get basicPlan => 'Piano Gratuito';

  @override
  String get user => 'Utente';

  @override
  String get pinPersonDescription =>
      'Le persone fissate restano in cima alla tua lista Persone e non vengono rimosse da Riordina.';

  @override
  String get reviewProject => 'Progetto';

  @override
  String get keyboardShortcuts => 'Scorciatoie da Tastiera';

  @override
  String get diagnosticsFailBadge => 'Non riuscito';

  @override
  String get debugLogCleared => 'Log di debug cancellato';

  @override
  String get errorConnectingToStripe => 'Errore di connessione a Stripe! Riprova più tardi.';

  @override
  String get tapPlusToStartRecording => 'Tocca il pulsante di registrazione per iniziare a registrare';

  @override
  String get permissionBlockedHint => 'Disattivato nelle Impostazioni. Consentilo lì per usare questa funzione.';

  @override
  String get downloadingAudio => 'Download audio in corso…';

  @override
  String failedToRevokeApiKey(String error) {
    return 'Impossibile revocare la chiave API: $error';
  }

  @override
  String largeTimeGapDetected(String gap) {
    return 'Rilevato un grande divario temporale ($gap)';
  }

  @override
  String get customFirmwareWarning =>
      'Un firmware personalizzato può rendere inutilizzabile il dispositivo. Assicurati che sia una build valida del firmware Omi e non scollegarlo durante l\'aggiornamento.';

  @override
  String get wrapped2025 => 'Resoconto 2025';

  @override
  String get showApiKey => 'Mostra chiave API';

  @override
  String get agreeAndContinue => 'Accetta e continua';

  @override
  String get connectExternalAiTools => 'Connetti strumenti AI esterni';

  @override
  String get batteryFullyChargedTitle => 'Omi è completamente carico';

  @override
  String get appReEnableFailedTitle => 'Riattivazione non riuscita';

  @override
  String get onboardingYourName => 'Il tuo nome';

  @override
  String get searchApps => 'Cerca app';

  @override
  String get weak => 'Debole';

  @override
  String get tellUsMore => 'Dicci di più (opzionale)';

  @override
  String confidenceReasonPicked(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Scelto in $count suggerimenti',
      one: 'Scelto in 1 suggerimento',
    );
    return '$_temp0';
  }

  @override
  String chatAppsDisconnectFooter(String app) {
    return 'Disconnettendo si elimina la cronologia che Omi conserva per $app.';
  }

  @override
  String get selectAll => 'Seleziona tutto';

  @override
  String get deleteActionItemConfirmation => 'Eliminare questa attività? Questa azione non può essere annullata.';

  @override
  String get categoryTravel => 'Viaggi';

  @override
  String get lowestRating => 'Valutazione più bassa';

  @override
  String get tasksEmptyStateMessage => 'Avvia una conversazione per creare un\'attività.';

  @override
  String get unpairAndForget => 'Disaccoppia e Dimentica Dispositivo';

  @override
  String get listeningForAudio => 'Ascolto audio…';

  @override
  String get processedStatus => 'Elaborato';

  @override
  String get wrappedTheHardPart => 'La parte difficile';

  @override
  String chatAppsReplyThereAnytime(String app) {
    return 'Scrivi a Omi su $app quando vuoi.';
  }

  @override
  String get upgradePlan => 'Aggiorna piano';

  @override
  String get onboardingRatingPromptYes => 'Sì';

  @override
  String timeCompactMins(int count) {
    return '${count}m';
  }

  @override
  String get changeTheConversationTitle => 'Cambia il titolo della conversazione';

  @override
  String get accountGroup => 'Account';

  @override
  String get updatingYourApp => 'Aggiornamento della tua app';

  @override
  String get microphone => 'Microfono';

  @override
  String get suggestQuestionsAfterConversations => 'Suggerisci domande dopo le conversazioni';

  @override
  String get failedToTranscribeAudio => 'Trascrizione audio fallita';

  @override
  String get unstarConversation => 'Rimuovi stella dalla conversazione';

  @override
  String get speakerTagPromptNotMe => 'Non sono io';

  @override
  String get confidenceReasonCorrected => 'Hai corretto la sua corrispondenza';

  @override
  String get peopleSearchPlaceholder => 'Cerca persone';

  @override
  String get syncStatusUnsupportedAudio => 'Audio illeggibile — impossibile sincronizzare';

  @override
  String get indentTask => 'Rientra';

  @override
  String get selectApp => 'Seleziona app';

  @override
  String get updatePayPal => 'Aggiorna PayPal';

  @override
  String get enterNameError => 'Inserisci il tuo nome';

  @override
  String get exportAllData => 'Esporta Tutti i Dati';

  @override
  String premiumMinsLeft(int count) {
    return '$count minuti premium rimasti.';
  }

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName impostata come app di riepilogo predefinita';
  }

  @override
  String get recordingStartedSuccessfully => 'Registrazione avviata con successo!';

  @override
  String get trySomethingLike => 'Prova qualcosa come…';

  @override
  String get chatAppsTryAsking => 'Prova a chiedere';

  @override
  String get categoryEntertainment => 'Intrattenimento';

  @override
  String get checksForAudioFiles => 'Controlla i file audio sulla scheda SD';

  @override
  String get everyoneHeader => 'Tutti';

  @override
  String get clearMemoryButton => 'Cancella memoria';

  @override
  String confidenceReasonLabeled(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Hai etichettato $count volte',
      one: 'Hai etichettato una volta',
    );
    return '$_temp0';
  }

  @override
  String get selectLogFile => 'Seleziona File di Log';

  @override
  String get chatAppsTelegramStepReturn => 'Torna qui. Ti confermeremo che ha funzionato.';

  @override
  String get discordMemberCount => 'Oltre 8000 membri su Discord';

  @override
  String get public => 'Pubblico';

  @override
  String get outdentTask => 'Riduci rientro';

  @override
  String get statusProcessing => 'Elaborazione';

  @override
  String get useFreePlan => 'Usa piano gratuito';

  @override
  String get emailLabel => 'Email';

  @override
  String get statusCallInProgress => 'Chiamata in corso';

  @override
  String get shortcuts => 'Scorciatoie';

  @override
  String get reviewRecentChanges => 'Modifiche recenti';

  @override
  String get raybanMetaAudioOnlyExplanation =>
      'Questa versione di Omi può usare il microfono dei tuoi occhiali tramite Bluetooth. L\'acquisizione di foto richiede la versione sviluppatore Meta di Omi.';

  @override
  String get wrappedDaysActiveLabel => 'giorni attivi';

  @override
  String get installOmiOnAppleWatch => 'Installa Omi sul tuo\nApple Watch';

  @override
  String tasksCountLabel(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count attività',
      one: '1 attività',
    );
    return '$_temp0';
  }

  @override
  String get confidenceReasonVoiceReady => 'voce salvata';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Eliminare $count attività$s selezionate?';
  }

  @override
  String get sdCardSync => 'Sincronizzazione scheda SD';

  @override
  String get timeout4Hours => '4 ore';

  @override
  String get chatAppsTitle => 'App di chat';

  @override
  String get repeatPasswordLabel => 'Ripeti password';

  @override
  String get skip => 'Salta';

  @override
  String get phoneNoVerifiedNumbersTitle => 'Nessun numero verificato';

  @override
  String get connectionLost => 'Connessione Persa';

  @override
  String get photoDiscardedMessage => 'Questa foto è stata scartata perché non era significativa.';

  @override
  String get weekdayFri => 'Ven';

  @override
  String get moveToFolder => 'Sposta nella cartella';

  @override
  String get updateNow => 'Aggiorna ora';

  @override
  String get failedToUpdateActionItem => 'Aggiornamento attività non riuscito';

  @override
  String get transferRequiredDescription =>
      'Questa registrazione è memorizzata sulla scheda SD del tuo dispositivo. Trasferiscila sul telefono per riprodurla o condividerla.';

  @override
  String get checkingForUpdates => 'Controllo aggiornamenti';

  @override
  String get importTranscriptFilesDescription =>
      'Seleziona trascrizioni SRT, VTT o TXT, oppure uno ZIP che le contenga';

  @override
  String get listenToSpeechProfile => 'Ascolta il mio profilo vocale ➡️';

  @override
  String get deleteRecapConfirmBody =>
      'Questo riepilogo verrà rimosso in modo permanente. Le conversazioni originali di quel giorno non verranno modificate.';

  @override
  String get copyLogs => 'Copia log';

  @override
  String get wrappedFunniestMoment => 'Più divertente';

  @override
  String get onboardingMicrophoneRequired => 'È necessaria l\'autorizzazione microfono per registrare.';

  @override
  String get whoIsItTitle => 'Chi è?';

  @override
  String dreamReportRunsLeft(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count esecuzioni manuali rimaste oggi',
      one: '1 esecuzione manuale rimasta oggi',
    );
    return '$_temp0';
  }

  @override
  String get modified => 'Modificato';

  @override
  String get actionCreateConversations => 'Crea conversazioni';

  @override
  String get chatAssistantsTitle => 'Assistenti chat';

  @override
  String get connectionError => 'Errore di Connessione';

  @override
  String get chooseFromGallery => 'Scegli dalla galleria';

  @override
  String get summaryPrompt => 'Prompt di riepilogo';

  @override
  String get whatWentWrong => 'Cosa non ha funzionato?';

  @override
  String get keepGoingGreat => 'Continua così, stai andando benissimo';

  @override
  String get deviceConnecting => 'Connessione…';

  @override
  String get downgradeLimitBattery => 'Consumo della batteria 7 volte superiore';

  @override
  String get privateMemories => 'Ricordi privati';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get aiGenPleaseEnterDescription => 'Inserisci una descrizione per la tua app';

  @override
  String get enterLiveSttWebsocket => 'Inserisci il tuo endpoint WebSocket STT live';

  @override
  String processingOnServerProgress(int current, int total) {
    return 'Elaborazione… $current/$total segmenti';
  }

  @override
  String linkedToEvent(String title) {
    return 'Collegata a «$title»';
  }

  @override
  String get failedToSaveCheckConnection => 'Salvataggio fallito. Controlla la tua connessione.';

  @override
  String get deviceOnboardingContinue => 'Continua';

  @override
  String get pairedToAnotherPhone => 'Associato a un altro telefono';

  @override
  String get syncingYourRecordings => 'Sincronizzazione delle tue registrazioni';

  @override
  String get manual => 'Manuale';

  @override
  String get oneMonthAgo => '1 mese fa';

  @override
  String get clearChatConfirm =>
      'Tutti i messaggi di questa chat verranno eliminati. Questa azione non può essere annullata.';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'Tutto ciò che usa \"$keyName\" perderà l\'accesso. Questa azione non può essere annullata.';
  }

  @override
  String get vadGateDescription => 'Salta l\'audio silenzioso prima della trascrizione per ridurre i costi.';

  @override
  String get dreamReportScheduled => 'Pianificato';

  @override
  String get audioDataReceived => 'Dati audio ricevuti';

  @override
  String get pro => 'Pro';

  @override
  String get micGainDescMuted => 'Microfono disattivato';

  @override
  String get enableLocationDescription =>
      'L\'autorizzazione alla posizione è necessaria per trovare i dispositivi Bluetooth nelle vicinanze.';

  @override
  String get conversationTitleUpdatedSuccessfully => 'Titolo della conversazione aggiornato con successo';

  @override
  String get syncStepUpload => 'Sincronizza';

  @override
  String get removeScreenshot => 'Rimuovi screenshot';

  @override
  String get failedToStartCall => 'Impossibile avviare la chiamata';

  @override
  String get deviceDiagnosticsUploadDescription =>
      'Review the diagnostics JSON below. It includes your device identifier, connection history, battery readings, firmware diagnostics, and BLE events. No audio or transcripts are included.';

  @override
  String get pairingTitleFieldy => 'Metti Fieldy in modalità di accoppiamento';

  @override
  String get autoDeletesAfterThreeDays => 'Eliminato automaticamente dopo 3 giorni.';

  @override
  String get wrappedDaysActive => 'giorni attivi';

  @override
  String get failedToDeleteActionItem => 'Eliminazione attività non riuscita';

  @override
  String get connect => 'Connetti';

  @override
  String get unableToDeleteConversation => 'Impossibile Eliminare Conversazione';

  @override
  String get clearChatAction => 'Cancella chat';

  @override
  String get memoryThisIphone => 'Questo iPhone';

  @override
  String get captureCustomSttUnreachableDetail =>
      'Il tuo servizio personalizzato di trascrizione vocale non è raggiungibile. Omi conserva l\'audio su questo telefono e lo invierà quando il servizio tornerà. Non si perde nulla.';

  @override
  String get feedbackGiveFeedback => 'Lascia un feedback';

  @override
  String failedToUpdateSettings(String error) {
    return 'Impossibile aggiornare le impostazioni: $error';
  }

  @override
  String get deleteRecordingConfirmation => 'Questa azione non può essere annullata.';

  @override
  String get advancedSettings => 'Impostazioni avanzate';

  @override
  String get transcriptionNoAudio => 'La trascrizione non riceve audio';

  @override
  String deletePeopleCountAction(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Elimina $count persone',
      one: 'Elimina 1 persona',
    );
    return '$_temp0';
  }

  @override
  String get speakerSuggestionAppliesToSpeaker => 'Vale per ogni riga di questo interlocutore';

  @override
  String get deviceNotResponding => 'Il dispositivo non risponde. Riprova.';

  @override
  String get everythingSynced => 'Tutto è già sincronizzato.';

  @override
  String get onDeviceModelDownloadFailedDesc => 'Impossibile scaricare il modello Whisper. Riprova.';

  @override
  String fairUseBannerStatus(String status) {
    return 'Uso corretto: $status';
  }

  @override
  String tasksDeleteSelected(int count) {
    return 'Elimina $count attività';
  }

  @override
  String get connectPaymentMethodInfo =>
      'Collega un metodo di pagamento qui sotto per iniziare a ricevere pagamenti per le tue app.';

  @override
  String get conversationNotFoundOrDeleted => 'Conversazione non trovata o è stata eliminata';

  @override
  String leaveFlowStepOf(int current, int total) {
    return 'Passaggio $current di $total';
  }

  @override
  String get deleteTypeToConfirm => 'Digita DELETE per confermare';

  @override
  String get clearMemoryTitle => 'Cancella Memoria di Omi';

  @override
  String get triggerConversationCreation => 'Creazione conversazione';

  @override
  String get flashCustomFirmware => 'Installa firmware personalizzato';

  @override
  String shareWithContactCount(int count) {
    return 'Condividi con $count contatto';
  }

  @override
  String get customChatbotPersonality => 'Personalità Chatbot Personalizzata';

  @override
  String get betaTesterNotice =>
      'Sei un beta tester per questa app. Non è ancora pubblica. Diventerà pubblica una volta approvata.';

  @override
  String get tomorrow => 'Domani';

  @override
  String get createdLabel => 'CREATO';

  @override
  String get searchPeople => 'Cerca persone';

  @override
  String get cancelled => 'Annullato';

  @override
  String basicPlanDesc(int limit) {
    return 'Il tuo piano include $limit minuti gratuiti al mese. Aggiorna per passare a illimitato.';
  }

  @override
  String get editMemoryTitle => 'Modifica ricordo';

  @override
  String get whatDoYouWantToKnow => 'Cosa vuoi sapere?';

  @override
  String get confidenceFootnote =>
      'Etichette e conferme fatte da te contano di più. Le etichette automatiche contano poco finché non le confermi.';

  @override
  String get exportFailedTryAgain => 'Esportazione non riuscita. Riprova.';

  @override
  String get addAppPhotosPermissionDenied => 'Permesso foto negato. Consenti l\'accesso alle foto';

  @override
  String get filterByDate => 'Filtra per data';

  @override
  String get chatAppsDoesFiles => 'Invia e riceve file, foto e note vocali';

  @override
  String get deleteKnowledgeGraphTitle => 'Eliminare Grafo di Conoscenza?';

  @override
  String get reloadingConversations => 'Ricaricamento conversazioni…';

  @override
  String get aiGenPleaseGenerateAppFirst => 'Prima genera un\'app';

  @override
  String get completeYourUpgrade => 'Completa il Tuo Aggiornamento';

  @override
  String get capturePendantDisconnectedDetail =>
      'Il ciondolo ha perso la connessione con questo telefono. Omi si riconnetterà da solo quando il ciondolo sarà acceso e vicino. Tutto ciò che è stato registrato prima è al sicuro.';

  @override
  String get greetingMorning => 'Buongiorno';

  @override
  String get thanksForYourFeedback => 'Grazie per il tuo feedback!';

  @override
  String get deleteActionItemConfirmMessage => 'Eliminare questa attività?';

  @override
  String get syncCardProcessing => 'Elaborazione su Omi…';

  @override
  String get chatAppsTryWeek => 'Riassumi la mia settimana in tre righe';

  @override
  String get recordWithPhoneMicSubtitle => 'Registra e trascrivi con il microfono di questo telefono';

  @override
  String get notifications => 'Notifiche';

  @override
  String get annualPlanStartsAutomatically =>
      'Il tuo piano annuale inizierà automaticamente al termine del piano mensile.';

  @override
  String get unpairDialogMessage =>
      'Questo disaccoppierà il dispositivo in modo che possa essere connesso a un altro telefono. Dovrai andare su Impostazioni > Bluetooth e dimenticare il dispositivo per completare il processo.';

  @override
  String get pairingTitleBee => 'Metti Bee in modalità di accoppiamento';

  @override
  String conversationCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count conversazioni',
      one: '1 conversazione',
    );
    return '$_temp0';
  }

  @override
  String get syncStatusWaiting => 'In attesa di sincronizzazione';

  @override
  String get validWebsocketUrlRequired => 'È richiesto un URL WebSocket valido (wss://)';

  @override
  String get improveSpeechProfile => 'Migliora il Tuo Profilo Vocale';

  @override
  String entityWaitingOn(String name) {
    return 'In attesa di $name';
  }

  @override
  String get feedbackReasonTooVerbose => 'Troppo prolisso';

  @override
  String chatAppsChannelFooter(String app) {
    return 'Le tue chat di $app restano su $app. Omi sa comunque di cosa hai parlato nell\'app e nelle altre app di chat.';
  }

  @override
  String get wrappedNoDataAvailable => 'Nessun dato disponibile';

  @override
  String deviceOnboardingAllSetReplayHint(String settings, String deviceSettings, String deviceTutorial) {
    return 'Riproduci questo tour in qualsiasi momento al numero $settings › $deviceSettings › $deviceTutorial';
  }

  @override
  String get createAKey => 'Crea una chiave';

  @override
  String get successfullyConnectedNotion => 'Connesso con successo a Notion!';

  @override
  String get captureMicInterruptedDetail =>
      'Una chiamata o un\'altra app sta usando il microfono, quindi Omi ora non può ascoltare. Omi riprenderà da solo quando il microfono sarà libero. Tutto ciò che è stato registrato prima è al sicuro.';

  @override
  String get onboardingScreenCaptureDenied =>
      'Autorizzazione cattura schermo negata. Concedi l\'autorizzazione in Preferenze di Sistema > Privacy e sicurezza > Registrazione schermo.';

  @override
  String get settingUp => 'Configurazione…';

  @override
  String get frequencyLow => 'Basso';

  @override
  String get sttFilterAuto => 'Automatico';

  @override
  String get voiceQuestionNoSpeech => 'Non ho capito — riprova';

  @override
  String get stripeRecommendation =>
      'Se Stripe è disponibile nel tuo paese, ti consigliamo vivamente di usarlo per pagamenti più veloci e facili.';

  @override
  String get confirmed => 'Confermato!';

  @override
  String get deletePendingFilesWarning =>
      'Queste registrazioni NON sono state sincronizzate con il tuo telefono e andranno perse permanentemente. Questa azione non può essere annullata.';

  @override
  String get removeFilter => 'Rimuovi Filtro';

  @override
  String get downloadModel => 'Scarica modello';

  @override
  String get performanceReduced => 'Le prestazioni potrebbero essere ridotte';

  @override
  String get hostRequired => 'L\'host è richiesto';

  @override
  String get alreadyBestValuePlan =>
      'Hai già il piano dal miglior rapporto qualità-prezzo. Non sono necessarie modifiche.';

  @override
  String preparingModel(String model) {
    return 'Preparazione di $model…';
  }

  @override
  String get sendTranscript => 'Invia trascrizione';

  @override
  String get howItWorksTitle => 'Come funziona?';

  @override
  String get filterBySpeaker => 'Filtra per interlocutore';

  @override
  String get addAppSubmittedSuccess => 'App inviata con successo 🚀';

  @override
  String olderIphoneModelDetected(String model) {
    return 'Modello rilevato: $model (precedente a iPhone XS). Il riconoscimento sul dispositivo potrebbe essere più lento.';
  }

  @override
  String get chatAppsWhatsAppTitle => 'WhatsApp è in arrivo';

  @override
  String get syncingDeveloperSettings => 'Sincronizzazione impostazioni sviluppatore…';

  @override
  String get enterWifiPassword => 'Inserisci la password WiFi';

  @override
  String get failedToUpdateBaselineStatus => 'Impossibile aggiornare questo ricordo. Riprova.';

  @override
  String get joinCommunity => 'Unisciti alla community!';

  @override
  String get helpOrInquiries => 'Aiuto o domande?';

  @override
  String get enable => 'Attiva';

  @override
  String get deviceForgottenMessage => 'Dispositivo dimenticato';

  @override
  String diagnosticsSincePairingSummary(int drops, int failed) {
    return 'Dall\'associazione: $drops interruzioni, $failed connessioni non riuscite.';
  }

  @override
  String confidenceSummaryConfirmed(String name) {
    return 'Omi riconosce la voce di $name e tu l\'hai confermata.';
  }

  @override
  String migratingToProtection(String level) {
    return 'Migrazione alla protezione $level…';
  }

  @override
  String get managePlan => 'Gestisci Piano';

  @override
  String get synced => 'Sincronizzato';

  @override
  String get failedToMoveConversations => 'Impossibile spostare le conversazioni';

  @override
  String get monthMar => 'Mar';

  @override
  String get timePM => 'PM';

  @override
  String get debugLogsAutoDelete => 'Eliminazione automatica dopo 3 giorni.';

  @override
  String get linkedIn => 'LinkedIn';

  @override
  String speakerLabelVoiceDetail(String state, String name) {
    String _temp0 = intl.Intl.selectLogic(
      state,
      {
        'learned': 'Omi riconoscerà $name la prossima volta.',
        'pending': 'Ci vogliono pochi secondi.',
        'disabled': 'Attiva il salvataggio delle voci nelle Impostazioni così Omi potrà riconoscere $name.',
        'other': 'Omi ha bisogno di più parlato chiaro da $name e continuerà a provare.',
      },
    );
    return '$_temp0';
  }

  @override
  String get authUnexpectedError => 'Errore imprevisto durante l\'accesso, riprova';

  @override
  String disconnectAppMessage(String appName) {
    return 'Puoi ricollegare $appName in qualsiasi momento.';
  }

  @override
  String get pendantPausedResumesWhenYouFinish => 'Ciondolo in pausa · riprende quando finisci';

  @override
  String get sendToSupport => 'Send to support';

  @override
  String get fairUseBudgetExhausted => 'Limite di trascrizione giornaliero raggiunto';

  @override
  String evidenceAutoConfirmed(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Hai confermato $count etichette automatiche',
      one: 'Hai confermato 1 etichetta automatica',
    );
    return '$_temp0';
  }

  @override
  String get otaWifiConnecting => 'Connessione al Wi-Fi…';

  @override
  String starFilterLabel(int count) {
    return '$count stella';
  }

  @override
  String get disconnectDevice => 'Disconnetti dispositivo';

  @override
  String get installsCount => 'Installazioni';

  @override
  String captureStatusWithSource(String status, String source) {
    return '$status · $source';
  }

  @override
  String get pairingTitleOmiGlass => 'Accendi Omi Glass';

  @override
  String get setActive => 'Imposta come attivo';

  @override
  String get showShortConversations => 'Mostra Conversazioni Brevi';

  @override
  String get reviewNotSure => 'Non sono sicuro';

  @override
  String msgCameraAccessError(String error) {
    return 'Errore nell\'accesso alla fotocamera: $error';
  }

  @override
  String get quickActionAskOmi => 'Chiedi qualsiasi cosa a Omi';

  @override
  String get dreamReportTimedOut => 'Interrotto al limite di tempo';

  @override
  String get chooseYourLanguage => 'Scegli la tua lingua';

  @override
  String get unableToDetermineFirmwareVersion => 'Impossibile determinare la versione attuale del firmware';

  @override
  String get addAppEnterConversationPrompt => 'Inserisci un prompt di conversazione per la tua app';

  @override
  String get readScope => 'Lettura';

  @override
  String get selectALanguage => 'Seleziona una lingua';

  @override
  String get otherTemplates => 'Altri modelli';

  @override
  String get speechProfileTopicGoal => 'Qual è il tuo obiettivo a lungo termine?';

  @override
  String get rayBanMetaMicPickerTitle => 'Scegli il microfono dei Ray-Ban Meta';

  @override
  String meetingNotesSubject(String title) {
    return 'Note: $title';
  }

  @override
  String get feedbackTitleMissingFeatures => 'Quali funzionalità ti mancano?';

  @override
  String get modelReady => 'Modello pronto';

  @override
  String todayAtTime(String time) {
    return 'Oggi alle $time';
  }

  @override
  String get deleteAccountPermanently => 'Elimina account definitivamente';

  @override
  String get updateStripeDetails => 'Aggiorna dettagli Stripe';

  @override
  String get voiceResponseHeadphonesOnly => 'Solo cuffie';

  @override
  String get deviceOnboardingEndConversation => 'Termina conversazione';

  @override
  String openingApp(String appName) {
    return 'Apertura di $appName…';
  }

  @override
  String get submitAppPublicDescription =>
      'La tua app sarà revisionata e resa pubblica. Puoi iniziare a usarla immediatamente, anche durante la revisione!';

  @override
  String connectToAppTitle(String appName) {
    return 'Connetti a $appName';
  }

  @override
  String get timeout10MinutesDesc => 'Termina conversazione dopo 10 minuti di silenzio';

  @override
  String get googleCalendar => 'Google Calendar';

  @override
  String get initializing => 'Inizializzazione…';

  @override
  String get noMessagesYet => 'Nessun messaggio ancora!\nPerché non inizi una conversazione?';

  @override
  String get chatAppsLoadFailed => 'Impossibile caricare le app di chat. Riprova.';

  @override
  String get tasksLater => 'Più tardi';

  @override
  String get speakerLabelUnknown => 'Sconosciuto';

  @override
  String get appTitle => 'Omi';

  @override
  String get noModelDownloadRequired =>
      'Verrà utilizzato il motore vocale nativo del dispositivo. Non è richiesto il download di alcun modello.';

  @override
  String get authenticationFailed => 'Autenticazione fallita. Riprova.';

  @override
  String get defaultRepoSaved => 'Repository predefinito salvato';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'Errore nella selezione della miniatura: $error';
  }

  @override
  String get captureRecordingSeparateTitle => 'Separare questa registrazione?';

  @override
  String get back => 'Indietro';

  @override
  String get preparingAudio => 'Preparazione audio';

  @override
  String get noAutoMemories => 'Nessun ricordo auto-estratto ancora';

  @override
  String get allDone => 'Tutto fatto!';

  @override
  String get msgReadingMemories => 'Leggendo i tuoi ricordi…';

  @override
  String get worksOnDesktop => 'Funziona su desktop';

  @override
  String get displayOptions => 'Opzioni di Visualizzazione';

  @override
  String get installApp => 'Installa app';

  @override
  String get stop => 'Ferma';

  @override
  String get grantPermissions => 'Concedi autorizzazioni';

  @override
  String get at => 'alle';

  @override
  String get checkInternetConnection => 'Controlla la tua connessione Internet';

  @override
  String get actionItems => 'Attività';

  @override
  String get nextDay => 'Giorno successivo';

  @override
  String get syncStatusFailed => 'Non riuscito — tocca Riprova';

  @override
  String get saveCredentials => 'Salva credenziali';

  @override
  String get peopleRecent => 'Recenti';

  @override
  String get bringYourOwn => 'Porta il tuo';

  @override
  String get cancelConsequenceBattery => '7x più consumo batteria (elaborazione sul dispositivo)';

  @override
  String get copyMessage => 'Copia messaggio';

  @override
  String get annualSubscriptionStarts =>
      'Il tuo abbonamento annuale di 12 mesi inizierà automaticamente dopo l\'addebito';

  @override
  String get deleteImportedData => 'Elimina dati importati';

  @override
  String get chatLimitReachedUpgrade => 'Limite chat raggiunto. Aggiorna per più messaggi.';

  @override
  String get whatsNew => 'Novità';

  @override
  String get omiTraining => 'Formazione Omi';

  @override
  String get wrappedMyBuddies => 'I miei amici';

  @override
  String get keepRecording => 'Continua a registrare';

  @override
  String get suggestedEvent => 'Suggerito';

  @override
  String get name => 'Nome';

  @override
  String get screenRecordingDescription =>
      'Omi ha bisogno dell\'autorizzazione per la registrazione dello schermo per catturare l\'audio di sistema dalle tue riunioni basate sul browser.';

  @override
  String get improveConnectionTitle => 'Migliora connessione';

  @override
  String get syncProcessingBackgroundHint => 'L\'operazione continua in background — puoi lasciare questa schermata.';

  @override
  String get wrappedYourTopDaysBadge => 'I tuoi giorni migliori';

  @override
  String get noPeopleYet => 'Ancora nessuna persona';

  @override
  String summaryGeneratedForDate(String date) {
    return 'Riepilogo generato per $date';
  }

  @override
  String get searchTranscriptOrSummary => 'Cerca nella trascrizione o nel riepilogo';

  @override
  String get memoryDetailsTitle => 'Ricordo';

  @override
  String get chatPersonality => 'Personalità chat';

  @override
  String get release => 'Rilascia';

  @override
  String removeVocabularyWord(String word) {
    return 'Rimuovi $word';
  }

  @override
  String get onboardingLanguage => 'Lingua';

  @override
  String get wrappedYouDidItEmoji => 'Ce l\'hai fatta! 🎉';

  @override
  String get syncInProgress => 'Sincronizzazione in corso';

  @override
  String get wrappedCouldntStopTalkingAbout => 'Non riuscivo a smettere di parlare di';

  @override
  String get chooseSummarizationApp => 'Scegli app di riepilogo';

  @override
  String etaLabel(String time) {
    return 'ETA: $time';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'Se rendi $item pubblico, può essere usato da tutti';
  }

  @override
  String get phoneCallsUpsellFeature2 => 'Riassunti automatici delle chiamate e attività';

  @override
  String get freemiumLimitsIntro =>
      'Omi è gratuito, ma la versione gratuita ha limiti che influiscono sulla tua esperienza:';

  @override
  String get nameLabel => 'Nome';

  @override
  String get shortConversationThresholdSubtitle =>
      'Le conversazioni più brevi di questa soglia saranno nascoste se non abilitate sopra';

  @override
  String get captureMicInUseElsewhere => 'Microfono in uso da un\'altra app';

  @override
  String get selectChatAssistant => 'Seleziona assistente chat';

  @override
  String get transferRequired => 'Trasferimento Richiesto';

  @override
  String get unlimitedChatThisMonth => 'Messaggi chat illimitati questo mese';

  @override
  String get backgroundModeUnavailable =>
      'La modalità in background non è disponibile perché non è connesso alcun dispositivo compatibile. Collega un dispositivo Omi, OpenGlass o Friend Pendant per usare questa funzione.';

  @override
  String get importConfiguration => 'Importa Configurazione';

  @override
  String get e2eeTradeoff1 =>
      '• Alcune funzionalità come le integrazioni di app esterne potrebbero essere disabilitate.';

  @override
  String get chatAppsCodeExpiredTitle => 'Questo codice è scaduto';

  @override
  String get responseSchema => 'Schema Risposta';

  @override
  String get wrappedBestMoments => 'Momenti migliori';

  @override
  String get noAppsExternalAccess => 'Nessuna app installata ha accesso esterno ai tuoi dati.';

  @override
  String modelReadyWithName(String model) {
    return 'Modello pronto ($model)';
  }

  @override
  String get appDisabledWebhookFailures =>
      'Il suo endpoint ha continuato a fallire per 72 ore, quindi gli invii sono stati interrotti.';

  @override
  String reviewConversationCount(int count) {
    return 'Conversazioni: $count';
  }

  @override
  String get reviewChangesLoadFailed => 'Impossibile caricare le modifiche recenti.';

  @override
  String get reviewOpenConversation => 'Conversazione';

  @override
  String get voiceRecordingFound => 'Registrazione trovata';

  @override
  String durationAgo(String duration) {
    return '$duration fa';
  }

  @override
  String get onboardingWelcomeToOmi => 'Benvenuto su Omi';

  @override
  String get deleteActionItemConfirmTitle => 'Elimina Attività';

  @override
  String get importantBillingInfo => 'Informazioni di fatturazione importanti:';

  @override
  String get pending => 'In attesa';

  @override
  String get onboardingRatingPromptTitle => 'Ti piace Omi?';

  @override
  String get savePayPalDetails => 'Salva dettagli PayPal';

  @override
  String appDisabledLastError(String error) {
    return 'Ultimo errore: $error.';
  }

  @override
  String get iveInstalledAndOpenedTheApp => 'Ho installato e aperto l\'app';

  @override
  String get pricePlaceholder => '0.00';

  @override
  String get triggerTranscriptProcessed => 'Trascrizione elaborata';

  @override
  String get decisions => 'Decisioni';

  @override
  String get conversationProcessingFailedMessage => 'Impossibile elaborare questa conversazione.';

  @override
  String get continueText => 'Continua';

  @override
  String get signInWithGoogle => 'Accedi con Google';

  @override
  String firmwareFlashTarget(String deviceName) {
    return 'Dispositivo: $deviceName';
  }

  @override
  String get deleteYourAccountAndAllData => 'Elimina account e tutti i dati';

  @override
  String get provider => 'Provider';

  @override
  String get people => 'Persone';

  @override
  String get perMonth => '/ Mese';

  @override
  String get monthFeb => 'Feb';

  @override
  String get fridayAbbr => 'Ven';

  @override
  String get thankYouForFeedback => 'Grazie per il tuo feedback!';

  @override
  String get usageBestYear => 'Best year';

  @override
  String get addAppFillRequiredFields => 'Compila correttamente tutti i campi obbligatori';

  @override
  String get deviceOnboardingVoiceReplyOffDescription => 'Le risposte rimangono sullo schermo. Non si parla nulla.';

  @override
  String get logs => 'Log';

  @override
  String get exportConversations => 'Esporta conversazioni';

  @override
  String get memoryReviewDropped => 'Rimosso dai tuoi ricordi.';

  @override
  String get appearanceLight => 'Chiaro';

  @override
  String get moneyEarned => 'Guadagni';

  @override
  String get permissionsAndTriggers => 'Permessi e trigger';

  @override
  String get discardRecordingTitle => 'Scartare la registrazione?';

  @override
  String get wrappedMinutesLabel => 'minuti';

  @override
  String get voiceRestoredToast => 'Omi potrebbe chiedere di nuovo di questa voce';

  @override
  String get locationAccess => 'Accesso posizione';

  @override
  String get deleteAllMemories => 'Elimina tutti i ricordi';

  @override
  String get deleteAccountTitle => 'Elimina Account';

  @override
  String get selectFile => 'Seleziona un file';

  @override
  String get answerTheCallFrom => 'Rispondi alla chiamata da';

  @override
  String get unpairDeviceDialogTitle => 'Disaccoppia dispositivo';

  @override
  String exportedToPlatform(String platform) {
    return 'Esportato in $platform';
  }

  @override
  String syncCardDownloadPercent(int percent) {
    return '$percent%';
  }

  @override
  String get deviceOnboardingVoiceReplyPreviewPlaying => 'Riproduzione della tua ultima risposta...';

  @override
  String get fromSd => 'Da SD';

  @override
  String get goodSampleInstructions =>
      '1. Assicurati di essere in un luogo tranquillo.\n2. Parla chiaramente e naturalmente.\n3. Assicurati che il tuo dispositivo sia nella sua posizione naturale sul collo.\n\nUna volta creato, puoi sempre migliorarlo o rifarlo.';

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
      'Per aggiungere una conversazione ai preferiti, aprila e tocca l\'icona stella nell\'intestazione.';

  @override
  String get pairingTitleOmiDevkit => 'Metti Omi DevKit in modalità di accoppiamento';

  @override
  String sttPrimaryLanguageUnsupported(String language, String fallback) {
    return 'Questo provider non supporta $language, quindi usa $fallback.';
  }

  @override
  String get premiumMinutesMonth =>
      '300 minuti premium al mese. Scegli «Sul Dispositivo» per una trascrizione gratuita illimitata. ';

  @override
  String get firmwareEnsureBattery => 'Assicurati che il tuo dispositivo abbia il 15% di batteria.';

  @override
  String get actionItemDescriptionHint => 'Cosa bisogna fare?';

  @override
  String get yourScore => 'Il tuo punteggio';

  @override
  String failedToStartAuth(String appName) {
    return 'Impossibile avviare l\'autenticazione $appName';
  }

  @override
  String get actionReadTasks => 'Leggi attività';

  @override
  String get keepSyncing => 'Continua sincronizzazione';

  @override
  String get overdue => 'In ritardo';

  @override
  String get chatAppsProblemUnavailable => 'Le app di chat non sono ancora disponibili per il tuo account.';

  @override
  String get tapSyncToStart => 'Tocca Sincronizza per iniziare';

  @override
  String get emptyDoneMessage => 'Nessun elemento completato ancora';

  @override
  String get recordOptionsTip =>
      'Suggerimento: tocca la freccia sul pulsante di registrazione per registrare una telefonata.';

  @override
  String get setupQuestionProfession => '1. Qual è la tua professione?';

  @override
  String get deviceInfoSection => 'Informazioni Dispositivo';

  @override
  String get teachOmiYourVoice => 'Insegna a Omi la tua voce';

  @override
  String get addYourFirstMemory => 'Aggiungi il tuo primo ricordo';

  @override
  String get priceLabel => 'PREZZO';

  @override
  String get high => 'Alto';

  @override
  String estimatedSizeWithValue(String size) {
    return 'Dimensione stimata: ~$size MB';
  }

  @override
  String cleanUpUnsureCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count persone di cui Omi non è sicuro',
      one: '1 persona di cui Omi non è sicuro',
    );
    return '$_temp0';
  }

  @override
  String get makeAllMemoriesPrivate => 'Rendi tutti i ricordi privati';

  @override
  String get raybanMetaWaitingForMetaAI => 'Completa la connessione nell\'app Meta AI, poi torna qui.';

  @override
  String get revokeAuthorization => 'Revoca Autorizzazione';

  @override
  String get confidenceToReachConfirmed => 'Per arrivare a Confermato';

  @override
  String get syncCardRateLimited => 'Limite di utilizzo raggiunto — la sincronizzazione riprenderà automaticamente';

  @override
  String get reviewStopClip => 'Interrompi clip';

  @override
  String get chatAppsWhatOmiDoes => 'Cosa fa Omi nelle app di chat';

  @override
  String get resume => 'Riprendi';

  @override
  String get defaultSpace => 'Spazio Predefinito';

  @override
  String get multipleSpeakersDetected => 'Rilevati più interlocutori';

  @override
  String evidenceAutoCorrected(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Hai cambiato $count etichette automatiche a un\'altra persona',
      one: 'Hai cambiato 1 etichetta automatica a un\'altra persona',
    );
    return '$_temp0';
  }

  @override
  String get voiceMatchPossible => 'Corrispondenza possibile';

  @override
  String get checkBoxToConfirm =>
      'Seleziona la casella per confermare di aver compreso che l\'eliminazione del tuo account è permanente e irreversibile.';

  @override
  String get quicklyPopulateResponse => 'Compila rapidamente con un formato di risposta provider noto';

  @override
  String get monthJul => 'Lug';

  @override
  String get failedToInitializeCallService => 'Impossibile inizializzare il servizio chiamate';

  @override
  String get connectAction => 'Connetti';

  @override
  String get onDeviceModelDeleted => 'Modello eliminato';

  @override
  String get micGainDescNeutral => 'Neutrale - registrazione bilanciata';

  @override
  String get chatOfflineHint => 'Sei offline. Riconnettiti per inviare messaggi.';

  @override
  String get onboardingLocationGrantInSettings =>
      'Concedi l\'autorizzazione alla posizione in Impostazioni > Privacy e sicurezza > Servizi di localizzazione';

  @override
  String get invalidSetupInstructionsUrl => 'URL istruzioni di configurazione non valido';

  @override
  String get msgCameraPermissionDenied =>
      'Permesso fotocamera negato. Si prega di consentire l\'accesso alla fotocamera';

  @override
  String get dataAndPrivacy => 'Dati e privacy';

  @override
  String get deviceNotCompatible => 'Il tuo dispositivo non è compatibile con la trascrizione sul dispositivo';

  @override
  String get pairingDescAppleWatch => 'Installa e apri l\'app Omi sul tuo Apple Watch, poi tocca Connetti nell\'app.';

  @override
  String get speechProfileTopicLocation => 'Dove vivi?';

  @override
  String get makeAllPrivate => 'Rendi Tutti i Ricordi Privati';

  @override
  String get capabilityNotification => 'Notifica';

  @override
  String get captureAudioSavedTranscribesLater => 'Audio salvato, trascritto più tardi';

  @override
  String get wrappedTopPhrases => 'Top 5 frasi';

  @override
  String get transcribeLaterPaused => 'In pausa — l\'audio non viene registrato';

  @override
  String get deviceOnboardingTurnOnTitle => 'Accendi';

  @override
  String get keyNamePlaceholder => 'es., La mia integrazione';

  @override
  String get languageTitle => 'Lingua';

  @override
  String get statusVerifiedLabel => 'Verificato';

  @override
  String get storageLocationPhoneMemory => 'Telefono (memoria)';

  @override
  String get you => 'Tu';

  @override
  String get listeningTranscriptWillAppear => 'In ascolto… qui apparirà una trascrizione.';

  @override
  String get askSuggestNotice => 'Cosa ha notato Omi?';

  @override
  String get safelyBackedUp => 'Conversazioni create';

  @override
  String get folderName => 'Nome cartella';

  @override
  String get categorySocialEntertainment => 'Sociale e intrattenimento';

  @override
  String speechProfileOwnerTitle(String name) {
    return 'Profilo vocale di $name';
  }

  @override
  String get reviewAddedSuccessfully => 'Recensione aggiunta con successo 🚀';

  @override
  String get fairUseSpeechUsage => 'Utilizzo vocale';

  @override
  String get visibilitySubtitle => 'Controlla quali conversazioni appaiono nella tua lista';

  @override
  String get wrappedWinLabelUpper => 'VITTORIA';

  @override
  String timeCompactMinsAndSecs(int mins, int secs) {
    return '${mins}m ${secs}s';
  }

  @override
  String get phoneCallsUpsellSubtitle =>
      'Effettua chiamate tramite Omi e ottieni trascrizione in tempo reale, riassunti automatici e altro.';

  @override
  String get sessionExpiredSignInAgain => 'La sessione è scaduta — accedi di nuovo.';

  @override
  String get newPersonEllipsis => 'Nuova persona…';

  @override
  String get sharePeriodToday => 'Oggi, Omi ha:';

  @override
  String get premiumMinutesInfo =>
      '300 minuti premium al mese. Scegli «Sul Dispositivo» per una trascrizione gratuita illimitata.';

  @override
  String get notConnectedStatus => 'Non connesso';

  @override
  String get authorizeSavingRecordings => 'Autorizza Salvataggio Registrazioni';

  @override
  String get thinking => 'Sto pensando';

  @override
  String get unpairDialogTitle => 'Disaccoppia Dispositivo';

  @override
  String get batteryFullyChargedBody => 'Il tuo dispositivo Omi è completamente carico. Puoi scollegarlo!';

  @override
  String get speakerTagPromptRejectedToast => 'Etichetta rimossa';

  @override
  String get phone => 'Telefono';

  @override
  String get chatAppsVoiceNotes => 'Note vocali';

  @override
  String get deviceOnboardingStatusDisconnected => 'Disconnesso';

  @override
  String get debugModeDetected => 'Modalità debug rilevata';

  @override
  String get failedToSaveDefaultRepo => 'Impossibile salvare il repository predefinito';

  @override
  String get showCompletedTasks => 'Mostra completate';

  @override
  String deviceStorageUsedOfTotal(String used, String total) {
    return '$used di $total utilizzati';
  }

  @override
  String get recordingsNotSynced => 'Hai registrazioni che non sono ancora sincronizzate.';

  @override
  String get performanceWarning => 'Avviso sulle prestazioni';

  @override
  String get submitAppPrivateDescription =>
      'La tua app sarà revisionata e resa disponibile per te privatamente. Puoi iniziare a usarla immediatamente, anche durante la revisione!';

  @override
  String get copyTranscript => 'Copia trascrizione';

  @override
  String get providing => 'Fornire';

  @override
  String get findDeviceNoneMessage => 'Accendilo e tienilo vicino al telefono.';

  @override
  String get wrappedLetsHitRewind => 'Riavvolgiamo il tuo';

  @override
  String deviceRamBelowMinimum(String ram) {
    return 'RAM rilevata: $ram GB. Minimo consigliato: 4 GB.';
  }

  @override
  String get addOrChangePaymentMethod => 'Aggiungi o modifica il tuo metodo di pagamento';

  @override
  String get omiAppName => 'Omi';

  @override
  String get enableBluetooth => 'Abilita Bluetooth';

  @override
  String get privacyNotice => 'Avviso sulla privacy';

  @override
  String get manufacturer => 'Produttore';

  @override
  String get byContinuingYouAgree => 'Continuando, accetti i nostri ';

  @override
  String dataProtectedWithSettings(String level) {
    return 'I tuoi dati sono ora protetti con le nuove impostazioni $level.';
  }

  @override
  String get selectSpaceInWorkspace => 'Seleziona uno spazio nella tua area di lavoro';

  @override
  String get copyKey => 'Copia chiave';

  @override
  String get password => 'Password';

  @override
  String estimatedSize(String size) {
    return 'Dimensione stimata: ~$size MB';
  }

  @override
  String monthsFreeBadge(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count mesi gratis',
      one: '1 mese gratis',
    );
    return '$_temp0';
  }

  @override
  String get chatAppsNotAvailableYet => 'Non ancora disponibile';

  @override
  String estimatedTimeRemaining(String time) {
    return 'Stimato: $time rimanenti';
  }

  @override
  String get syncCardBackendBusy =>
      'I server di Omi sono sovraccarichi — le tue registrazioni verranno sincronizzate appena tornerà disponibile capacità';

  @override
  String get speakerTagPromptTitle => 'Aiuta Omi a riconoscere le voci';

  @override
  String get playFromHere => 'Riproduci da qui';

  @override
  String get entityProject => 'Progetto';

  @override
  String get permissionNotGrantedYet =>
      'Permesso non ancora concesso. Assicurati di aver consentito l\'accesso al microfono e di aver riaperto l\'app sul tuo watch.';

  @override
  String get e2eeTradeoff2 => '• Se perdi la password, i tuoi dati non possono essere recuperati.';

  @override
  String get exportConfiguration => 'Esporta configurazione';

  @override
  String get recordWith => 'Registra con';

  @override
  String get greetingEvening => 'Buonasera';

  @override
  String deletePhoneNumberConfirm(String phoneNumber) {
    return 'Eliminare $phoneNumber?';
  }

  @override
  String get deviceOnboardingAskQuestionTitle => 'Fai una domanda a Omi';

  @override
  String get appNamePlaceholder => 'La mia fantastica app';

  @override
  String get tapPlayToResume => 'Tocca riproduci per riprendere';

  @override
  String get dueDate => 'Data di scadenza';

  @override
  String get appearanceSystem => 'Sistema';

  @override
  String get invalidEmailError => 'Inserisci un\'email valida';

  @override
  String get highResourceUsage => 'Alto utilizzo delle risorse';

  @override
  String get voiceAndPeople => 'Voce e Persone';

  @override
  String get customizationSection => 'Personalizzazione';

  @override
  String get failedToCancelSubscription => 'Impossibile annullare l\'abbonamento. Riprova.';

  @override
  String get later => 'Più tardi';

  @override
  String get wrappedTasksGenerated => 'attività generate';

  @override
  String get personalizingExperience => 'Personalizzazione della tua esperienza…';

  @override
  String get syncAvailable => 'Sincronizzazione disponibile';

  @override
  String chatGreeting(String name) {
    return 'Ciao $name, chiedi qualsiasi cosa';
  }

  @override
  String get phoneCallSettingsTitle => 'Impostazioni chiamate';

  @override
  String get remoteDeviceTerminated => 'Il dispositivo remoto ha terminato la connessione';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'Errore nell\'apertura del selettore file: $message';
  }

  @override
  String get actionItemDeleted => 'Attività eliminata';

  @override
  String get couldNotLoadMemories => 'Impossibile caricare i ricordi';

  @override
  String get generateDescription => 'Genera descrizione';

  @override
  String get privateLabel => 'Privato';

  @override
  String get deviceOnboardingMuteUnmute => 'Disattiva / Attiva';

  @override
  String get day => 'Giorno';

  @override
  String get submitAppQuestion => 'Inviare l\'App?';

  @override
  String get usageWords => 'Words';

  @override
  String get failedToConnectClickUp => 'Connessione a ClickUp non riuscita';

  @override
  String get selectZipFileToImport => 'Seleziona il file .zip da importare!';

  @override
  String timeSecsPlural(int count) {
    return '$count sec';
  }

  @override
  String get wasThisHelpful => 'È stato utile?';

  @override
  String get msgLearningMemories => 'Imparando dai tuoi ricordi…';

  @override
  String get onboardingScreenCaptureRequired =>
      'È necessaria l\'autorizzazione di cattura schermo per la registrazione audio di sistema.';

  @override
  String evidenceManualLabels(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Etichettato da te in $count conversazioni',
      one: 'Etichettato da te in 1 conversazione',
    );
    return '$_temp0';
  }

  @override
  String get transferCancelled => 'Trasferimento annullato';

  @override
  String get sttModelSpeed => 'Velocità';

  @override
  String get fairUsePolicy => 'Uso corretto';

  @override
  String get phoneStorage => 'Archivio del telefono';

  @override
  String get deviceOnboardingEndConversationDesc => 'Salva e termina la conversazione corrente';

  @override
  String get proceedAnyway => 'Procedi comunque';

  @override
  String get overview => 'Panoramica';

  @override
  String get deviceOnboardingGoodJob => 'Ottimo lavoro!';

  @override
  String get delete => 'Elimina';

  @override
  String get connectAiAssistantsToYourData => 'Collega assistenti AI ai tuoi dati';

  @override
  String get startFresh => 'Ricomincia da capo';

  @override
  String get deviceOnboardingStatusConnectedDone => 'Connesso!';

  @override
  String get filterInstalled => 'Installate';

  @override
  String get mergingStatus => 'Unione in corso…';

  @override
  String get successfullyConnected => 'Connesso con successo!';

  @override
  String get permissionCreateConversations => 'Crea conversazioni';

  @override
  String get cancelConsequencePhoneCalls => 'Nessuna trascrizione telefonate in tempo reale';

  @override
  String get feedbackReasonSummaryOther => 'Altro';

  @override
  String get oAuth => 'OAuth';

  @override
  String get notEnoughSpace => 'Attenzione: Spazio insufficiente!';

  @override
  String get feedbackTitleTooExpensive => 'Quale prezzo andrebbe bene per te?';

  @override
  String get secureEncryption => 'Crittografia sicura';

  @override
  String get rating2PlusStars => '2+ stelle';

  @override
  String get chatAppsOpenMessagesAgain => 'Riapri Messaggi';

  @override
  String fairUseBudgetResetsAt(String time) {
    return 'Si reimposta $time';
  }

  @override
  String get addVocabularyDescription => 'Aggiungi parole che Omi dovrebbe riconoscere durante la trascrizione.';

  @override
  String get whisperModelSizeMedium => 'Medio';

  @override
  String get wrappedMyBuddiesLabel => 'I MIEI AMICI';

  @override
  String get memoryGraph => 'Grafo dei ricordi';

  @override
  String get paste => 'Incolla';

  @override
  String get failedToRefreshGitHubStatus => 'Impossibile aggiornare lo stato della connessione GitHub.';

  @override
  String get feedbackSubtitleMissingFeatures => 'Costruiamo sempre — questo ci aiuta a stabilire le priorità.';

  @override
  String get itemApp => 'App';

  @override
  String get pairingDescFriendPendant =>
      'Premi il pulsante sul ciondolo per accenderlo. Entrerà automaticamente in modalità di accoppiamento.';

  @override
  String get appDisabledGeneric => 'È stata disattivata da Omi.';

  @override
  String get noSummaryForApp =>
      'Nessun riepilogo disponibile per questa app. Prova un\'altra app per risultati migliori.';

  @override
  String get deleteProcessed => 'Elimina Elaborati';

  @override
  String get chatBlockOpenInGoals => 'Apri in Obiettivi';

  @override
  String get micGainDescModerate => 'Silenzioso - per rumore moderato';

  @override
  String get defaultRepository => 'Repository Predefinito';

  @override
  String get statusPending => 'In attesa';

  @override
  String get referralProgram => 'Programma di Riferimento';

  @override
  String get authFailedToLinkApple => 'Collegamento con Apple non riuscito, riprova.';

  @override
  String modelNameWithFile(String model) {
    return 'Modello: $model';
  }

  @override
  String get deviceOnboardingTurnOnSubtitle => 'Premi il pulsante per riaccenderlo';

  @override
  String get previewAndScreenshots => 'Anteprima e Screenshot';

  @override
  String get recordingOfflineTranscriptWillCatchUp =>
      'Registrazione offline — la trascrizione si aggiornerà quando tornerai online.';

  @override
  String get accessibilityDescription =>
      'Omi ha bisogno dell\'autorizzazione di accessibilità per rilevare quando partecipi a riunioni Zoom, Meet o Teams nel tuo browser.';

  @override
  String setDefaultAppContent(String appName) {
    return 'Impostare $appName come app di riepilogo predefinita?\n\nQuesta app verrà utilizzata automaticamente per tutti i futuri riepiloghi delle conversazioni.';
  }

  @override
  String get switchRequiresRestart => 'Il cambio di ambiente richiede il riavvio dell\'app';

  @override
  String get wrappedWinHeader => 'Vittoria';

  @override
  String get forYou => 'Per te';

  @override
  String get filterCategory => 'Categoria';

  @override
  String get createPersonHint => 'Crea una nuova persona e allena Omi a riconoscere anche il suo modo di parlare!';

  @override
  String get loadingMemories => 'Caricamento ricordi…';

  @override
  String get selectedPaymentMethod => 'Metodo di pagamento selezionato';

  @override
  String get email => 'Email';

  @override
  String get transcriptionUnavailableRecordingContinues =>
      'Trascrizioni non disponibili, la registrazione continua sul dispositivo e verrà elaborata più tardi';

  @override
  String get noLogsYet =>
      'Ancora nessun log. Registra qualcosa per vedere le richieste al tuo fornitore di trascrizione.';

  @override
  String get failedToStartAuthentication => 'Impossibile avviare l\'autenticazione';

  @override
  String peopleCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count persone',
      one: '1 persona',
    );
    return '$_temp0';
  }

  @override
  String get enterBackendUrlError => 'Inserisci l\'URL del server';

  @override
  String get playbackBackToCurrent => 'Torna all\'attuale';

  @override
  String clockSkewWarning(int minutes) {
    return 'L\'orologio del dispositivo è sfasato di ~$minutes min. Controlla le impostazioni di data e ora.';
  }

  @override
  String get stopThese => 'Interrompi questi';

  @override
  String get yes => 'Sì';

  @override
  String get recognizingOthers => 'Riconoscere gli altri 👀';

  @override
  String get transcriptionLanguageDesc => 'Seleziona la lingua per la trascrizione vocale';

  @override
  String aboutMinutesRemaining(int minutes) {
    return 'Circa $minutes minuti rimanenti';
  }

  @override
  String get deleteFlowReasonSubtitle => 'Il tuo feedback ci aiuta a migliorare Omi per tutti.';

  @override
  String get processedFilesDeleted => 'File elaborati eliminati';

  @override
  String get autoLanguageDetection => 'Rilevamento automatico della lingua';

  @override
  String bulkExportPartial(int success, int total, String platform) {
    return 'Esportati $success di $total su $platform';
  }

  @override
  String get actionItemDescriptionCannotBeEmpty => 'La descrizione dell\'attività non può essere vuota';

  @override
  String get deleteReasonFoundAlternative => 'Sto usando qualcos\'altro';

  @override
  String get noContentToDisplay => 'Nessun contenuto da visualizzare';

  @override
  String get feedbackReasonRecordingWrongSpeaker => 'Interlocutore sbagliato';

  @override
  String get create => 'Crea';

  @override
  String get greatJobAlmostThere => 'Ottimo lavoro, ci sei quasi';

  @override
  String get captureStorageAlmostFull => 'Memoria quasi piena';

  @override
  String chatAppsConnectedOn(String date) {
    return 'Connesso il $date';
  }

  @override
  String get wrappedAGreatDay => 'Una giornata fantastica';

  @override
  String get backendUrlSavedSuccess => 'URL del server salvato con successo!';

  @override
  String get speakerTagPromptIsThisYou => 'Eri tu?';

  @override
  String get knowledgeGraphDeletedSuccess => 'Grafo della conoscenza eliminato con successo';

  @override
  String timeMinsPlural(int count) {
    return '$count min';
  }

  @override
  String get peopleNotHeardYet => 'Non ancora ascoltato';

  @override
  String get chatStarterDoDifferently => 'Cosa potrei fare di diverso oggi?';

  @override
  String get fairUseAboutBody =>
      'Omi è progettato per conversazioni personali, riunioni e interazioni dal vivo. L\'utilizzo si misura in base al tempo di parlato, non al tempo di connessione. Se il tuo utilizzo è molto superiore a quello personale normale, riceverai prima un avviso. Un utilizzo intenso e continuo può rallentare o limitare la trascrizione.';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'Seleziona la tua lingua principale';

  @override
  String get manualDisconnect => 'Disconnessione manuale';

  @override
  String get googleCalendarNotConnected => 'Google Calendar non collegato';

  @override
  String get soCloseJustLittleMore => 'Così vicino, ancora un po\'';

  @override
  String appDataAccessMessage(String appName) {
    return '$appName riceverà le tue conversazioni, i tuoi ricordi e le tue registrazioni sul server del suo sviluppatore. Omi non è responsabile di come vengono usati lì questi dati.';
  }

  @override
  String savePercent(int percent) {
    return 'Risparmia ~$percent%';
  }

  @override
  String get deviceDisconnectedNotificationBody => 'Riconnettiti per continuare a usare Omi.';

  @override
  String get openConversation => 'Apri conversazione';

  @override
  String get frequencyDescMaximum => 'Ogni collegamento utile, fino a 9 al giorno';

  @override
  String get readChatRepliesAloud => 'Leggi le risposte della chat ad alta voce';

  @override
  String get microphonePermissionRequired => 'È richiesta l\'autorizzazione del microfono per la registrazione vocale.';

  @override
  String get updatePayPalAccountDetails => 'Aggiorna i dettagli del tuo account PayPal';

  @override
  String get connectionTimeout => 'Timeout della connessione';

  @override
  String get micGainDescHigh => 'Alto - per voci distanti o basse';

  @override
  String get permissionsInfoNote =>
      'R = Lettura, W = Scrittura. Solo lettura di default se non viene selezionato nulla.';

  @override
  String timeHoursAndMins(int hours, int mins) {
    return '$hours ore $mins min';
  }

  @override
  String get keepMyAccount => 'Mantieni il mio account';

  @override
  String get transcriptionLanguage => 'Lingua di trascrizione';

  @override
  String dreamReportStats(int records, int tokens) {
    return '$records elementi letti · $tokens token';
  }

  @override
  String get editPerson => 'Modifica Persona';

  @override
  String get whatWeTrack => 'Cosa monitoriamo';

  @override
  String get micGainDescVeryHigh => 'Molto alto - per sorgenti molto silenziose';

  @override
  String timeCompactDays(int count) {
    return '${count}g';
  }

  @override
  String get reviewTaskField => 'Attività';

  @override
  String reviewConfirmPerson(String name) {
    return 'Conferma $name';
  }

  @override
  String get downloadingFromDevice => 'Download dal dispositivo';

  @override
  String get conversationTranscriptCopiedToClipboard => 'Trascrizione della conversazione copiata negli appunti';

  @override
  String get continueAction => 'Continua';

  @override
  String conversationsMovedCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count conversazioni spostate',
      one: '1 conversazione spostata',
    );
    return '$_temp0';
  }

  @override
  String get signInButton => 'Accedi';

  @override
  String get startUpdate => 'Avvia aggiornamento';

  @override
  String get wrappedTopPhrasesLabelUpper => 'TOP FRASI';

  @override
  String get total => 'Totale';

  @override
  String get deleting => 'Eliminazione…';

  @override
  String get skipBack10Seconds => 'Indietro di 10 secondi';

  @override
  String get setupAnswerAllQuestions => 'Non hai ancora risposto a tutte le domande! 🥺';

  @override
  String get planUpgradeScheduledMessage =>
      'Upgrade programmato! Il tuo piano mensile continua fino alla fine del periodo di fatturazione, poi passa automaticamente all\'annuale.';

  @override
  String get needHelpChatWithUs => 'Hai bisogno di aiuto? Chatta con noi';

  @override
  String get chatBlockUnavailable => 'Non è più disponibile';

  @override
  String estimatedMinutes(int count) {
    return '~$count minuto/i';
  }

  @override
  String get failedToSaveMemory => 'Impossibile salvare. Controlla la tua connessione.';

  @override
  String get deleteReasonTakingBreak => 'Mi sto solo prendendo una pausa';

  @override
  String get reviewAndManageConversations => 'Rivedi e gestisci le tue conversazioni registrate';

  @override
  String get actionReadMemories => 'Leggi ricordi';

  @override
  String deletePinnedPersonMessage(String name) {
    return '$name è fissato. I suoi campioni vocali vengono rimossi, Omi smette di riconoscerlo e le trascrizioni passate lo mostrano come un interlocutore senza nome. Questa azione non si può annullare.';
  }

  @override
  String get speakerTagPromptHintOwner => 'La tua risposta etichetta solo il brano riprodotto.';

  @override
  String get onboardingNotificationDeniedNotifications =>
      'Autorizzazione notifiche negata. Concedi l\'autorizzazione in Preferenze di Sistema > Notifiche.';

  @override
  String appDisabledNamed(String appName) {
    return '$appName disattivata';
  }

  @override
  String get tabOld => 'Vecchi';

  @override
  String deviceOnboardingVoiceReplyStatusHeadphonesConnected(String device) {
    return '$device collegato. Omi parlerà qui.';
  }

  @override
  String get deletePendingFiles => 'Elimina registrazioni in sospeso';

  @override
  String get wrappedWin => 'Vittoria';

  @override
  String get removeFromAllFolders => 'Rimuovi da tutte le cartelle';

  @override
  String get deviceIdLabel => 'ID dispositivo';

  @override
  String get upgradeAlreadyScheduled => 'Il tuo aggiornamento al piano annuale è già programmato';

  @override
  String get openCall => 'Apri chiamata';

  @override
  String get rateAndReviewThisApp => 'Valuta e recensisci questa app';

  @override
  String get getStarted => 'Inizia';

  @override
  String get deviceOnboardingVoiceReplyAlwaysDescription =>
      'Utilizza l\'altoparlante del telefono quando non sono collegate le cuffie.';

  @override
  String chooseExportDestination(int count) {
    return 'Esporta $count elemento/i su…';
  }

  @override
  String get onboardingSetupSubtitle => 'Dai a Omi un momento per personalizzarsi';

  @override
  String welcomeBack(String name) {
    return 'Bentornato, $name';
  }

  @override
  String get dreamReportIdle => 'Ancora niente di nuovo da esaminare.';

  @override
  String get cleanUpTitle => 'Riordina';

  @override
  String get deleteProcessedFiles => 'Elimina File Elaborati';

  @override
  String get no => 'No';

  @override
  String get msgPhotoError => 'Errore nello scattare la foto. Si prega di riprovare.';

  @override
  String get search => 'Cerca';

  @override
  String get downloadingFirmware => 'Download del firmware';

  @override
  String get phoneKeypadTab => 'Tastierino';

  @override
  String get pendantFullSyncBlocked =>
      'La memoria del Pendant è piena ed è ancora in modalità registrazione, quindi l\'audio memorizzato non può essere trasferito. Premi il pulsante del Pendant per interrompere la registrazione, poi sincronizza di nuovo.';

  @override
  String get deleteSelectedItemsTitle => 'Elimina Elementi Selezionati';

  @override
  String get appPrivacyAndTerms => 'Privacy e Termini dell\'App';

  @override
  String get omiTranscription => 'Trascrizione Omi';

  @override
  String get editConversation => 'Modifica conversazione';

  @override
  String moveConversationsTo(int count) {
    return 'Sposta $count conversazioni in:';
  }

  @override
  String get signOutConfirmation =>
      'Dovrai accedere di nuovo per vedere le conversazioni. Il dispositivo associato e le preferenze dell\'app restano su questo telefono.';

  @override
  String get wrappedObsessionsLabel => 'OSSESSIONI';

  @override
  String get jumpToLatestMessage => 'Vai all\'ultimo messaggio';

  @override
  String get failedStatus => 'Non riuscito';

  @override
  String get notNow => 'Non ora';

  @override
  String transferFailedMessage(String error) {
    return 'Trasferimento fallito: $error';
  }

  @override
  String get customVocabularyTitle => 'Vocabolario Personalizzato';

  @override
  String get internetRequired => 'Connessione internet richiesta';

  @override
  String get waitingForData => 'In attesa di dati…';

  @override
  String get noRecordingsYet => 'Ancora nessuna registrazione';

  @override
  String get answerWithYourVoice => 'Rispondi a voce:';

  @override
  String personUnpinnedToast(String name) {
    return 'Rimosso dai fissati: $name';
  }

  @override
  String get stopRecording => 'Interrompi registrazione';

  @override
  String get off => 'Disattivato';

  @override
  String get memoryThisPhone => 'Questo telefono';

  @override
  String get thirteenMonthsCoverage => 'Avrai 13 mesi di copertura totale (mese corrente + 12 mesi annuali)';

  @override
  String failedToCreateApiKey(String error) {
    return 'Impossibile creare la chiave API del provider: $error';
  }

  @override
  String get tipStableInternet => 'Internet stabile velocizza i caricamenti cloud';

  @override
  String get tasksMarkComplete => 'Contrassegnato come completato';

  @override
  String get reviewAddTask => 'Aggiungi attività';

  @override
  String get submitReply => 'Invia risposta';

  @override
  String get captureRecoveryBanner => 'Omi non invia audio — tocca per riconnetterti';

  @override
  String get analyzing => 'Analisi in corso…';

  @override
  String get sttModelFaster => 'Più veloce';

  @override
  String get fairUseLoadError => 'Impossibile caricare lo stato di uso corretto. Riprova.';

  @override
  String get places => 'Luoghi';

  @override
  String get voiceMatchWeak => 'Corrispondenza debole';

  @override
  String captureOfflineBufferingFor(int minutes) {
    return 'Offline, buffering · $minutes min';
  }

  @override
  String get onboardingWhatIKnowAboutYouTitle => 'Quello che so di te';

  @override
  String get raybanMetaPhotoRequested => 'Foto richiesta — apparirà nella tua conversazione.';

  @override
  String get verifyYourNumber => 'Verifica il tuo numero';

  @override
  String get deleteFlowConfirmSubtitle => 'Non è possibile annullare l\'operazione, nemmeno tramite l\'assistenza.';

  @override
  String get submitAppTermsAgreement =>
      'Inviando questa app, accetto i Termini di Servizio e l\'Informativa sulla Privacy di Omi AI';

  @override
  String get stripeSecureDescription => 'Stripe garantisce trasferimenti sicuri e puntuali dei ricavi della tua app';

  @override
  String get categoryProductivity => 'Produttività';

  @override
  String chatWithAppName(String appName) {
    return 'Chat con $appName';
  }

  @override
  String get enableCloudStorage => 'Abilita archiviazione cloud';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl => 'URL webhook trascrizione in tempo reale non valido';

  @override
  String get wrappedShow => 'SERIE';

  @override
  String get speakTranscribeSummarize => 'Parla. Trascrivi. Riassumi.';

  @override
  String get pricingPaid => 'A pagamento';

  @override
  String get successfullyConnectedAsana => 'Connesso con successo ad Asana!';

  @override
  String get rating => 'Valutazione';

  @override
  String get chatQuotaExceededReply =>
      'Hai raggiunto il tuo limite mensile. Aggiorna per continuare a chattare con Omi senza restrizioni.';

  @override
  String get pendantIsListeningTitle => 'Il tuo ciondolo sta ascoltando';

  @override
  String get usageBestDay => 'Best day';

  @override
  String get personWhyConfidence => 'Perché?';

  @override
  String get permissionDescCreateConversations => 'Questa app può creare nuove conversazioni.';

  @override
  String get reviewSpellingCustom => 'Scrivilo';

  @override
  String resetsInHours(int count) {
    return 'Si resetta tra $count ore';
  }

  @override
  String get reviewAction => 'Rivedi';

  @override
  String get submitRequest => 'Invia richiesta';

  @override
  String get phoneCalls => 'Chiamate';

  @override
  String get actionItemsTab => 'Attività';

  @override
  String get record => 'Registra';

  @override
  String get noReviewsFound => 'Nessuna recensione trovata';

  @override
  String get oauth => 'OAuth';

  @override
  String get urlCopied => 'URL copiato';

  @override
  String get actionItemReminderTitle => 'Promemoria Omi';

  @override
  String sharedTasksAdded(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count attività aggiunte al tuo elenco',
      one: '1 attività aggiunta al tuo elenco',
    );
    return '$_temp0';
  }

  @override
  String get contactsPermissionRequiredForSms => 'L\'autorizzazione ai contatti è necessaria per condividere via SMS';

  @override
  String get apiKeyRevokedSuccessfully => 'Chiave API revocata con successo';

  @override
  String get authorizationSuccessful => 'Autorizzazione riuscita!';

  @override
  String get unpinAction => 'Non fissare';

  @override
  String get syncingStatus => 'Sincronizzazione';

  @override
  String get audioFormatLabel => 'Formato audio';

  @override
  String get phoneSelectCountryTitle => 'Seleziona paese';

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'Top $percentile% Utente';
  }

  @override
  String get phoneContactsTab => 'Contatti';

  @override
  String get reply => 'Rispondi';

  @override
  String get openingShareSheet => 'Apertura foglio di condivisione…';

  @override
  String get creatingAppIcon => 'Creazione icona app…';

  @override
  String get deviceOnboardingStartSpeaking => 'Inizia a parlare…';

  @override
  String get wrappedAHilariousMoment => 'Un momento esilarante';

  @override
  String get paidApp => 'App a pagamento';

  @override
  String get wrappedStruggleHeader => 'Sfida';

  @override
  String get speakerTagPromptDontKnow => 'Qualcuno che non conosco';

  @override
  String get wrappedStarting => 'Avvio…';

  @override
  String get getButton => 'Ottieni';

  @override
  String get syncCustomSttWarningTitle => 'La sincronizzazione usa la trascrizione di Omi';

  @override
  String get download => 'Scarica';

  @override
  String get addScreenshot => 'Aggiungi screenshot';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return 'Connessione a $serviceName non riuscita: $error';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'Per favore riconnettiti per continuare a usare il tuo $deviceName.';
  }

  @override
  String get configureDailySummaryDigest => 'Configura il tuo riepilogo giornaliero delle attività';

  @override
  String get showShortConversationsDesc => 'Visualizza conversazioni più brevi della soglia';

  @override
  String participantsSummaryUncounted(String name) {
    return '$name e altri';
  }

  @override
  String fairUseBudgetUsed(String used, String limit) {
    return '${used}m / ${limit}m';
  }

  @override
  String get add => 'Aggiungi';

  @override
  String get disconnect => 'Disconnetti';

  @override
  String get enterApiKey => 'Inserisci la tua chiave API';

  @override
  String get msgMaxFilesLimit => 'Puoi selezionare solo fino a 4 file';

  @override
  String get space => 'Spazio';

  @override
  String get upgrade => 'Aggiorna';

  @override
  String get tapToView => 'Tocca per visualizzare';

  @override
  String get summaryTemplate => 'Modello di riepilogo';

  @override
  String get chatAppsWaitingTitle => 'In attesa del tuo messaggio';

  @override
  String yesterdayAtTime(String time) {
    return 'Ieri alle $time';
  }

  @override
  String get cancel => 'Annulla';

  @override
  String get checkingAppleWatch => 'Controllo Apple Watch…';

  @override
  String syncCardDownloadPercentSpeed(int percent, String speed) {
    return '$percent% · $speed KB/s';
  }

  @override
  String get finalTouches => 'Ritocchi finali';

  @override
  String get weekdaySat => 'Sab';

  @override
  String get fairUseWeekly => 'Settimanale';

  @override
  String get invalidPaymentUrl => 'URL di pagamento non valido';

  @override
  String get transcriptionSlowerOnDevice =>
      'La trascrizione sul dispositivo potrebbe essere più lenta su questo dispositivo.';

  @override
  String get noListsInSpace => 'Nessuna lista trovata in questo spazio';

  @override
  String get deviceDiagnostics => 'Diagnostica del dispositivo';

  @override
  String get askAnything => 'Chiedi qualsiasi cosa';

  @override
  String confidenceMeterLabel(String level) {
    return 'Affidabilità: $level';
  }

  @override
  String get permissionReadTasks => 'Leggi attività';

  @override
  String get skipForNow => 'Salta per ora';

  @override
  String get setupCompletedUrl => 'URL di configurazione completata';

  @override
  String get saySomething => 'Di\' qualcosa…';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get chatAppsEntryTitle => 'Chatta con Omi';

  @override
  String get chatAppsTelegramStepOpen => 'Tocca Apri Telegram qui sotto';

  @override
  String get pleaseEnterValidPayPalMeLink => 'Inserisci un link PayPal.me valido';

  @override
  String get syncFlowIntro =>
      'Le registrazioni vengono trasferite dal tuo dispositivo a questo telefono e memorizzate localmente, quindi caricate sul server di Omi, dove vengono trascritte e trasformate in conversazioni.';

  @override
  String get cantFindDeviceHint =>
      'Non trovi il dispositivo? Assicurati che sia acceso e vicino al telefono, poi cerca di nuovo.';

  @override
  String get tryAdjustingFilter => 'Prova a modificare la ricerca o il filtro';

  @override
  String get failedConnectionsRecent => 'Connessioni non riuscite (ultimi 7 giorni)';

  @override
  String get captureSourceCall => 'Chiamata';

  @override
  String get storageLocationPhone => 'Telefono';

  @override
  String get voiceMatchClose => 'Corrispondenza forte';

  @override
  String get reviewChangeUndone => 'Annullato. Omi non lo rifarà da solo.';

  @override
  String get tasksNoProject => 'Nessun progetto';

  @override
  String get dataAccessNotice => 'Avviso di accesso ai dati';

  @override
  String deviceStorageFree(String free) {
    return '$free liberi';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'Già esportato in $platform';
  }

  @override
  String get recapDeletedSnackbar => 'Riepilogo eliminato';

  @override
  String get apiUrlRequired => 'L\'URL API è richiesto';

  @override
  String get getOmiUnlimitedFree =>
      'Ottieni Omi Unlimited gratis contribuendo con i tuoi dati per addestrare modelli AI.';

  @override
  String get wrappedShare => 'Condividi';

  @override
  String get tasksTomorrow => 'Domani';

  @override
  String get chatAppsShowInAppOn => 'On: compaiono nell\'app Omi come chat di sola lettura.';

  @override
  String get errorActivatingAppIntegration =>
      'Errore nell\'attivazione dell\'app. Se è un\'app di integrazione, assicurati che la configurazione sia completata.';

  @override
  String get readChatRepliesAloudDescription => 'Parla solo quando \"Risposta vocale\" lo consente.';

  @override
  String get addDueDate => 'Aggiungi data di scadenza';

  @override
  String get translated => 'tradotto';

  @override
  String get dontAskAgain => 'Non chiedermelo più';

  @override
  String get fullAccessScope => 'Accesso completo';

  @override
  String get firmwareUpdated => 'Firmware aggiornato';

  @override
  String get deviceOnboardingVoiceReplyPreviewThroughPhoneSpeaker => 'Attraverso l\'altoparlante del telefono';

  @override
  String get prompt => 'Prompt';

  @override
  String get dreamReportDeletedItem => 'Elemento eliminato';

  @override
  String chatAppsDisconnectChannel(String app) {
    return 'Disconnetti $app';
  }

  @override
  String get appleHealthDeniedBody =>
      'Omi non ha il permesso di leggere i tuoi dati di Apple Health. Attivalo in Impostazioni iOS → Privacy e sicurezza → Salute → Omi.';

  @override
  String endsOnDate(String date) {
    return 'Termina il $date';
  }

  @override
  String get searchSettings => 'Cerca nelle impostazioni';

  @override
  String get pairingDescNeoOne =>
      'Tieni premuto il pulsante di accensione finché il LED non lampeggia. Il dispositivo sarà rilevabile.';

  @override
  String get checkingNextSevenDays => 'Controllo dei prossimi 7 giorni';

  @override
  String get confidenceLikely => 'Probabile';

  @override
  String get appleHealthFeatureChatTitle => 'Parla della tua salute';

  @override
  String get loadingDevices => 'Caricamento dispositivi…';

  @override
  String get writeSomething => 'Scrivi qualcosa';

  @override
  String syncCardProgressOf(int current, int total) {
    return '$current di $total';
  }

  @override
  String get unableToOpenWatchApp =>
      'Impossibile aprire l\'app Apple Watch. Apri manualmente l\'app Watch sul tuo Apple Watch e installa Omi dalla sezione \"App disponibili\".';

  @override
  String get dreamReportWouldFix => 'Correggerebbe';

  @override
  String get doubleTap => 'Doppio Tocco';

  @override
  String get speakerTagPromptSomeoneElse => 'Qualcun altro…';

  @override
  String get cancelTransfer => 'Annulla Trasferimento';

  @override
  String get capabilityExternalIntegration => 'Integrazione esterna';

  @override
  String get sttLanguageFollowsPrimary => 'Segue la tua lingua principale';

  @override
  String get wrappedCringeMomentTitle => 'Momento imbarazzante';

  @override
  String get allRecordingsSynced => 'Tutte le registrazioni sono sincronizzate';

  @override
  String get reviewConfirm => 'Conferma';

  @override
  String get checkBackLaterForNewApps => 'Ricontrolla più tardi per nuove app';

  @override
  String get referAFriend => 'Consiglia a un amico';

  @override
  String cleanUpLead(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other:
          'Omi non è sicuro di queste $count persone. Per lo più sono nomi capiti male dalle trascrizioni. Deseleziona chi vuoi tenere.',
      one: 'Omi non è sicuro di questa persona. Deseleziona per tenerla.',
    );
    return '$_temp0';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return 'Rendere $item privato?';
  }

  @override
  String get chatQuotaSubtitle => 'AI chat messages used with Omi this month.';

  @override
  String get failedTryAgain => 'Fallito? Riprova';

  @override
  String get deleteAllFiles => 'Elimina tutte le registrazioni';

  @override
  String get onDeviceModelDownloadSuccess => 'Modello scaricato';

  @override
  String get reviewNoChangesTitle => 'Ancora nessuna modifica';

  @override
  String get useMobileAppToCapture => 'Usa la tua app mobile per catturare l\'audio';

  @override
  String get setYourName => 'Imposta il tuo nome';

  @override
  String get tasksGroupByDate => 'Raggruppa per data';

  @override
  String get diagnosticsLast7Days => 'Ultimi 7 giorni';

  @override
  String get deviceOnboardingStatusConnected => 'Connesso';

  @override
  String get actionItemCreatedSuccessfully => 'Attività creata con successo';

  @override
  String get thursdayAbbr => 'Gio';

  @override
  String get wifiConfiguration => 'Configurazione WiFi';

  @override
  String get cancelReasonFoundAlternative => 'Ho trovato un\'alternativa';

  @override
  String get process => 'Elabora';

  @override
  String get help => 'Aiuto';

  @override
  String get rollbackConfirmTitle => 'Tornare al firmware?';

  @override
  String get visibility => 'Visibilità';

  @override
  String get evidenceNotHeard => 'Non ancora sentito in una conversazione';

  @override
  String get messageReported => 'Messaggio segnalato con successo.';

  @override
  String get readyToChat => '✨ Pronto per chattare!';

  @override
  String get tryDifferentFilter => 'Prova un filtro diverso';

  @override
  String get header => 'Intestazione';

  @override
  String get wrappedBestHeader => 'Migliori';

  @override
  String get memoryDontUse => 'Non usare';

  @override
  String get appStore => 'App Store';

  @override
  String get deleteMeetingScreenshotMessage =>
      'Lo screenshot verrà rimosso dalla nota di questa riunione. L\'operazione non può essere annullata.';

  @override
  String get categoryShopping => 'Shopping';

  @override
  String get voiceResponseOff => 'Off';

  @override
  String get bluetoothNeeded =>
      'Omi ha bisogno del Bluetooth per connettersi al tuo dispositivo indossabile. Abilita il Bluetooth e riprova.';

  @override
  String get googleCalendarComingSoon => 'Integrazione Google Calendar in arrivo!';

  @override
  String get max => 'Massimo';

  @override
  String get homeScreen => 'Schermata Home';

  @override
  String get chatAppsTelegramStepStart => 'Tocca Avvia nella tua chat con Omi';

  @override
  String get greetingAfternoon => 'Buon pomeriggio';

  @override
  String get unpair => 'Disaccoppia';

  @override
  String get diagnosticsVerdictReconnects => 'Si riconnette da solo';

  @override
  String get macOsCalendar => 'Calendario macOS';

  @override
  String get onboardingSetupStepLanguage => 'Ottimizzazione della trascrizione per la tua lingua';

  @override
  String get mcpOAuthSetup =>
      'Su claude.ai, aggiungi un connettore personalizzato e incolla l\'URL del server. Se Claude richiede un Client ID OAuth avanzato, usa il valore qui sotto e lascia il segreto vuoto — non usare mai la tua chiave API MCP come segreto OAuth.';

  @override
  String get wednesdayAbbr => 'Mer';

  @override
  String get selectAudioInput => 'Seleziona ingresso audio';

  @override
  String get deviceDisconnectedMessage => 'Il tuo Omi è stato disconnesso 😔';

  @override
  String get reprocessConversation => 'Rielabora Conversazione';

  @override
  String get goal => 'OBIETTIVO';

  @override
  String mergeConversationsMessage(int count) {
    return 'Questo combinerà $count conversazioni in una. Tutti i contenuti saranno uniti e rigenerati.';
  }

  @override
  String get everyXSeconds => 'Ogni x secondi';

  @override
  String get chatAppsLocked => 'Richiede Omi Pro';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl => 'URL webhook conversazione creata non valido';

  @override
  String get secureAuthViaAppleId => 'Autenticazione sicura tramite Apple ID';

  @override
  String connectingToDeviceName(String deviceName) {
    return 'Connessione a $deviceName...';
  }

  @override
  String get listeningSubtitle => 'Tempo totale in cui Omi ha ascoltato attivamente.';

  @override
  String get capturing => 'Acquisizione in corso';

  @override
  String get enterWifiNetworkName => 'Inserisci il nome della rete WiFi';

  @override
  String get noAppsAvailable => 'Nessuna app disponibile';

  @override
  String get installingFirmware => 'Installazione del firmware';

  @override
  String get transferToPhone => 'Trasferisci sul Telefono';

  @override
  String get voiceResponseMode => 'Risposta vocale';

  @override
  String get messageCopied => '✨ Messaggio copiato negli appunti';

  @override
  String get discardRecordingMessage =>
      'Il tuo campione vocale non è ancora stato salvato. Se esci ora, verrà scartato.';

  @override
  String chatAppsIMessageBody(String code) {
    return 'Ciao Omi, codice di collegamento $code';
  }

  @override
  String get failedToRefreshWhoopStatus => 'Impossibile aggiornare lo stato della connessione Whoop.';

  @override
  String get youreOnAnnualPlan => 'Sei sul piano annuale';

  @override
  String timeHoursPlural(int count) {
    return '$count ore';
  }

  @override
  String get usageOnline => 'Online';

  @override
  String get validPortRequired => 'È richiesta una porta valida';

  @override
  String get howItWorks => 'Come funziona';

  @override
  String get viewTemplate => 'Visualizza Template';

  @override
  String get dreamReportNothingFound => 'Niente da correggere';

  @override
  String get personTalkTime => 'Tempo di parola';

  @override
  String get evidenceNoVoice => 'Ancora nessun campione vocale';

  @override
  String get makeMyAppPublic => 'Rendi pubblica la mia app';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'Stato autorizzazione Bluetooth: $status. Controlla Preferenze di Sistema.';
  }

  @override
  String get noRecordings => 'Nessuna registrazione';

  @override
  String get usageChatThisMonth => 'Chat this month';

  @override
  String get addAppEnterChatPrompt => 'Inserisci un prompt di chat per la tua app';

  @override
  String daysAgo(int count) {
    return '$count giorni fa';
  }

  @override
  String get processing => 'Elaborazione';

  @override
  String get deviceOnboardingStatusTurningOff => 'Spegnimento in corso…';

  @override
  String get newTag => 'NUOVO';

  @override
  String get permissionDescReadTasks => 'Questa app può accedere alle tue attività.';

  @override
  String get time => 'Ora';

  @override
  String get recording => 'Registrazione';

  @override
  String get speakerTagPromptWhoIsThis => 'Chi è?';

  @override
  String chatUsageMessagesNoLimit(String used) {
    return 'Chat: $used messaggi questo mese';
  }

  @override
  String get importantTradeoffs => 'Compromessi importanti:';

  @override
  String get makeAllPublic => 'Rendi Tutti i Ricordi Pubblici';

  @override
  String get noSpeechDesc =>
      'Non abbiamo rilevato nessun parlato. Assicurati di parlare per almeno 10 secondi e non più di 3 minuti.';

  @override
  String get searchPartialFailure => 'Impossibile caricare alcuni risultati';

  @override
  String get prerecordedTranscript => 'Preregistrato';

  @override
  String get confirm => 'Conferma';

  @override
  String get statusCalling => 'Chiamata…';

  @override
  String get wrappedConvos => 'conversazioni';

  @override
  String get unresolvedSpeakersTitle => 'Informazioni sulle etichette dei relatori';

  @override
  String get writeYourReply => 'Scrivi la tua risposta…';

  @override
  String get localCopiesSection => 'Copie locali';

  @override
  String get noSummaryYet => 'Nessun riepilogo ancora';

  @override
  String get wrappedBiggestHeader => 'Più grande';

  @override
  String get error => 'Errore';

  @override
  String get deviceWillRestart => 'Il dispositivo verrà riavviato.';

  @override
  String get consentDataMessage =>
      'Continuando, le tue conversazioni, registrazioni e informazioni personali saranno archiviate in modo sicuro sui nostri server. Le tue registrazioni audio e trascrizioni vengono elaborate da servizi AI di terze parti (inclusi Deepgram per la trascrizione e OpenAI per l\'analisi) per fornirti approfondimenti basati sull\'AI e abilitare tutte le funzionalità dell\'app.';

  @override
  String get connectMacOsCalendar => 'Connetti il tuo calendario macOS locale';

  @override
  String get captureSourcePhoneMic => 'Microfono del telefono';

  @override
  String get setupCompleted => 'Completato';

  @override
  String get installOmiOnAppleWatchDescription =>
      'Per utilizzare il tuo Apple Watch con Omi, devi prima installare l\'app Omi sul tuo orologio.';

  @override
  String get toggleControlBar => 'Attiva/Disattiva barra di controllo';

  @override
  String get onboardingBluetoothDeniedSystemPrefs =>
      'Autorizzazione Bluetooth negata. Concedi l\'autorizzazione in Preferenze di Sistema.';

  @override
  String get syncCancelled => 'Sincronizzazione annullata';

  @override
  String get firmwareDisconnectUsb => 'Disconnetti USB';

  @override
  String get processNow => 'Elabora ora';

  @override
  String get appIdNotFoundError => 'ID dell\'app non trovato';

  @override
  String get editDueDate => 'Modifica data di scadenza';

  @override
  String get home => 'Home';

  @override
  String get tasksOverdue => 'Scadute';

  @override
  String get statusCompleted => 'Completato';

  @override
  String get otaStarting => 'Avvio dell\'aggiornamento…';

  @override
  String get monthApr => 'Apr';

  @override
  String get conversationTasksEmptyMessage => 'Le attività di questa conversazione appariranno qui.';

  @override
  String get useDifferentAccount => 'Usa un altro account';

  @override
  String get reviewReasonNotUseful => 'Non utile';

  @override
  String get anonymousUser => 'Utente anonimo';

  @override
  String get viewPlansDescription => 'Gestisci il tuo abbonamento e visualizza le statistiche di utilizzo';

  @override
  String invalidJson(String error) {
    return 'JSON non valido: $error';
  }

  @override
  String get deleteActionItem => 'Elimina attività';

  @override
  String get confirmCancellation => 'Conferma annullamento';

  @override
  String get tapToDelete => 'Tocca per eliminare';

  @override
  String get onTheCallEnterThisCode => 'Durante la chiamata, inserisci questo codice';

  @override
  String get stableFirmware => 'Firmware stabile';

  @override
  String get triggerEvents => 'Eventi di attivazione';

  @override
  String get speakerTagPromptSaveVoicesTitle => 'Ricorda le voci delle persone che nomini';

  @override
  String get syncedFilesDeleted => 'Registrazioni sincronizzate eliminate';

  @override
  String get cloudStorageDesc =>
      'Una volta caricate, le registrazioni vengono elaborate e trascritte. Le conversazioni saranno disponibili entro un minuto.';

  @override
  String get failedToUpdateFolder => 'Impossibile aggiornare la cartella';

  @override
  String dreamReportFound(int fixes, int asks) {
    String _temp0 = intl.Intl.pluralLogic(
      fixes,
      locale: localeName,
      other: '$fixes correzioni',
      one: '1 correzione',
    );
    String _temp1 = intl.Intl.pluralLogic(
      asks,
      locale: localeName,
      other: '$asks suggerimenti',
      one: '1 suggerimento',
    );
    return '$_temp0 · $_temp1';
  }

  @override
  String get anotherPlatform => 'un\'altra piattaforma';

  @override
  String get wrappedTopPhrasesLabel => 'TOP FRASI';

  @override
  String get dataAccessWarning =>
      'Questa app accederà ai tuoi dati. Omi AI non è responsabile di come i tuoi dati vengono utilizzati, modificati o eliminati da questa app';

  @override
  String get pleaseCompleteAuthentication =>
      'Completa l\'autenticazione nel tuo browser. Una volta fatto, torna all\'app.';

  @override
  String get dailySummaryTitle => 'Riepilogo Giornaliero';

  @override
  String get managePeople => 'Gestisci persone';

  @override
  String get dreamReportEmptyBody => 'Dream esamina ciò che è cambiato nel tuo account circa una volta all\'ora.';

  @override
  String get couldNotOpenPaymentSettings => 'Impossibile aprire le impostazioni di pagamento. Riprova.';

  @override
  String get locationServiceDisabled => 'Servizio di Localizzazione Disabilitato';

  @override
  String get understanding => 'Comprensione';

  @override
  String get recapDeleteFailed => 'Impossibile eliminare il riepilogo. Riprova più tardi.';

  @override
  String get deleteKnowledgeGraphQuestion => 'Eliminare Grafico della Conoscenza?';

  @override
  String get wrappedYourBuddy => 'Il tuo amico!';

  @override
  String chatAppsChatIn(String app) {
    return 'Chat su $app';
  }

  @override
  String get speechDurationDescription => 'Assicurati di parlare almeno 5 secondi e non più di 90.';

  @override
  String get reviewReasonAlreadyDone => 'Già fatto';

  @override
  String get phoneSetupStep2Title => 'Inserisci un codice di verifica';

  @override
  String get tasksClearCompleted => 'Cancella completati';

  @override
  String get searchingForDevices => 'Ricerca dispositivi';

  @override
  String get siriIndexSettingDescription =>
      'Allow Siri to find your conversations, memories, and tasks on this device. Turning this off removes them from Apple search.';

  @override
  String get markIncomplete => 'Segna come incompleto';

  @override
  String get onboardingBluetoothRequired => 'È necessaria l\'autorizzazione Bluetooth per connettersi al dispositivo.';

  @override
  String get searchAppsPlaceholder => 'Cerca tra 1500+ app';

  @override
  String get pleaseEnterName => 'Inserisci un nome';

  @override
  String get paymentMethodCharged =>
      'Il tuo metodo di pagamento esistente verrà addebitato automaticamente al termine del piano mensile';

  @override
  String get allMemoriesAreNowPublic => 'Tutti i ricordi sono ora pubblici';

  @override
  String taskDueDate(String date) {
    return 'Scadenza: $date';
  }

  @override
  String get pendantPausesUntilYouFinish => 'Il ciondolo resta in pausa finché non finisci';

  @override
  String get failedToAuthorize => 'Impossibile autorizzare. Riprova.';

  @override
  String get mergeConversationsSuccessTitle => 'Conversazioni unite con successo';

  @override
  String get peopleFilterNeedsVoice => 'Voce mancante';

  @override
  String get clickToBeginRecordingSystemAudio => 'Fai clic per iniziare la registrazione audio di sistema';

  @override
  String get fairUseStageRestrict => 'Bloccato';

  @override
  String get nextResult => 'Risultato successivo';

  @override
  String get chatAppsContactsApp => 'Contatti';

  @override
  String get categoryEmotionalSupport => 'Supporto emotivo';

  @override
  String get wrappedYourHeader => 'I tuoi';

  @override
  String get pendantPausesDuringCall => 'Il ciondolo resta in pausa durante la chiamata';

  @override
  String noConversationsOnDate(String date) {
    return 'Nessuna conversazione il $date';
  }

  @override
  String get chatStarterYesterday => 'Cosa ho fatto ieri?';

  @override
  String get entityNotRight => 'Non è corretto?';

  @override
  String get failedToCreateShareLink => 'Impossibile creare il link di condivisione';

  @override
  String get sync => 'Sincronizza';

  @override
  String get micGainDescMax => 'Massimo - usare con cautela';

  @override
  String get sttNone => 'Nessuno';

  @override
  String get chatAppsCodeNote => 'Il codice funziona una sola volta e scade tra 10 minuti.';

  @override
  String get aiGenAppCreatedSuccessfully => 'App creata con successo!';

  @override
  String lastNEvents(int count) {
    return 'Ultimi $count eventi';
  }

  @override
  String get phoneDeleteButton => 'Elimina';

  @override
  String get systemAudio => 'Sistema';

  @override
  String get checkOutMyMemoryGraph => 'Guarda il mio grafo della memoria!';

  @override
  String get feedbackTitleBatteryDrain => 'Parlaci dei problemi di batteria';

  @override
  String get startCallRecording => 'Avvia registrazione chiamata';

  @override
  String get monthlyPlanContinues =>
      'Il tuo attuale piano mensile continuerà fino alla fine del periodo di fatturazione';

  @override
  String get syncStepUploadDesc => 'La tua registrazione viene inviata al server di Omi';

  @override
  String get otaKeepNearby => 'Durante l\'aggiornamento tieni il dispositivo acceso e vicino, e non chiudere l\'app.';

  @override
  String get updatePayPalDetails => 'Aggiorna dettagli PayPal';

  @override
  String get termsOfUse => 'Condizioni d\'Uso';

  @override
  String get apiKeyCreated => 'Chiave API creata!';

  @override
  String get deviceOnboardingVoiceReplyPreviewIdle => 'Ascolta la tua ultima risposta';

  @override
  String get starOngoing => 'Aggiungi Conversazione in Corso ai Preferiti';

  @override
  String get largeModelWarning =>
      'Questo modello è grande e potrebbe causare il crash dell\'app o funzionare molto lentamente sui dispositivi mobili.\n\nSi consiglia \"small\" o \"base\".';

  @override
  String get selectLanguage => 'Seleziona Lingua';

  @override
  String get professionExecutive => 'Dirigente';

  @override
  String get importFileTooLarge => 'Questo file è troppo grande per essere importato.';

  @override
  String get updateRequiredTitle => 'Aggiornamento necessario';

  @override
  String get syncStepBackedUp => 'Conversazione pronta';

  @override
  String get openWatchApp => 'Apri app Watch';

  @override
  String get keyNameLabel => 'NOME CHIAVE';

  @override
  String bulkExportSuccess(int count, String platform) {
    return 'Esportati $count su $platform';
  }

  @override
  String get couldNotProcessSubscription => 'Impossibile elaborare l\'abbonamento. Riprova.';

  @override
  String get memorizingYourVoice => 'Memorizzazione della tua voce…';

  @override
  String get processingAudio => 'Elaborazione audio';

  @override
  String get syncYourRecordings => 'Sincronizza le tue registrazioni';

  @override
  String get resetToDefault => 'Ripristina predefinito';

  @override
  String get deleteConversation => 'Elimina conversazione';

  @override
  String get flashCustomFirmwareDescription => 'Installa build di firmware personalizzate';

  @override
  String get deviceUpToDate => 'Il dispositivo è aggiornato';

  @override
  String get raybanMetaMusicPauseNote =>
      'La musica sul telefono si mette in pausa mentre è in uso il microfono degli occhiali.';

  @override
  String get appleHealthNotAvailable => 'Apple Health non è disponibile su questo dispositivo';

  @override
  String hints(String text) {
    return 'Suggerimenti: $text';
  }

  @override
  String get cloudProvider => 'Provider cloud';

  @override
  String get chooseAnyFileType => 'Scegli qualsiasi tipo di file';

  @override
  String get reset => 'Reimposta';

  @override
  String get automaticallyCreateNewPerson =>
      'Crea automaticamente una nuova persona quando viene rilevato un nome nella trascrizione.';

  @override
  String get timeout2Minutes => '2 minuti';

  @override
  String get newMemory => '✨ Nuova memoria';

  @override
  String get chatAppsMoreComing => 'Altre app in arrivo.';

  @override
  String get couldNotLoadKnowledgeGraph => 'Impossibile caricare il grafo della conoscenza';

  @override
  String get voiceSettingsAskToTagSubtitle =>
      'Ogni tanto Omi ti chiede chi stava parlando nelle tue conversazioni recenti';

  @override
  String get developer => 'Sviluppatore';

  @override
  String get connectionNeeded => '🌐 Connessione necessaria';

  @override
  String get helpAndAbout => 'Aiuto e informazioni';

  @override
  String get tasksNoDeadline => 'Nessuna scadenza';

  @override
  String get yourDataIsProtected => 'I tuoi dati sono protetti e regolati dalla nostra ';

  @override
  String get confirmDeletion => 'Conferma eliminazione';

  @override
  String get speakerTagPromptClosestVoices => 'Voci più vicine';

  @override
  String get quicklyPopulateRequest => 'Compila rapidamente con un formato di richiesta provider noto';

  @override
  String get exportTranscript => 'Esporta trascrizione';

  @override
  String get resetsSoon => 'Si resetta presto';

  @override
  String get showPhoneCallButtonTitle => 'Mostra pulsante chiamata';

  @override
  String get wrappedAChallenge => 'Una sfida';

  @override
  String get revokeKey => 'Revoca chiave';

  @override
  String get dailyRecaps => 'Riepiloghi Giornalieri';

  @override
  String get processingConversationProgress => 'Elaborazione della conversazione…';

  @override
  String get freeMinutesMonth => '300 minuti gratuiti/mese inclusi. Illimitato con ';

  @override
  String get downloadWhisperModel => 'Scarica un modello whisper per utilizzare la trascrizione sul dispositivo';

  @override
  String get noMemoriesInCategories => 'Nessun ricordo in queste categorie';

  @override
  String get checkingNextDays => 'Controllo dei prossimi 30 giorni';

  @override
  String get createAndSubmitNewApp => 'Crea e invia una nuova app';

  @override
  String get chatAppsInTheMeantime => 'Nel frattempo';

  @override
  String get deleteFlowReasonTitle => 'Perché te ne stai andando?';

  @override
  String get tasksSelectAll => 'Seleziona tutto';

  @override
  String get webhookUrl => 'URL del webhook';

  @override
  String get selected => 'Selezionato';

  @override
  String get batteryDrainIncrease => 'Il consumo della batteria aumenterà significativamente.';

  @override
  String get dreamReportFixed => 'Corretto';

  @override
  String get failedToConnectClickUpRetry => 'Connessione a ClickUp non riuscita. Riprova.';

  @override
  String get serverUrl => 'URL Server';

  @override
  String get starred => 'Preferiti';

  @override
  String get speakerTagPromptClipUnavailable => 'Impossibile riprodurre questa clip';

  @override
  String get feedbackSubtitleFoundAlternative => 'Ci piacerebbe sapere cosa ha attirato la tua attenzione.';

  @override
  String get omiButtonActions => 'Azioni del pulsante Omi';

  @override
  String get invalidRecordingDesc => 'Assicurati di parlare per almeno 5 secondi e non più di 90.';

  @override
  String get switchApiConfirmTitle => 'Cambiare ambiente API?';

  @override
  String gattError(String code) {
    return 'Errore GATT ($code)';
  }

  @override
  String get aiGenRegenerateIcon => 'Rigenera icona';

  @override
  String get connectTaskAppToExport => 'Collega un\'app attività nelle Impostazioni per esportare';

  @override
  String get firmwareFlashed => 'Firmware installato';

  @override
  String get addPerson => 'Aggiungi persona';

  @override
  String get cancelConsequencesSubtitle =>
      'Ti consigliamo vivamente di esplorare le tue altre opzioni invece di annullare.';

  @override
  String get transcriptCopiedToClipboard => 'Trascrizione copiata negli appunti';

  @override
  String get monthNov => 'Nov';

  @override
  String get switchedToOnDevice => 'Passato alla trascrizione sul dispositivo';

  @override
  String get phoneMicOfflineFallbackMessage =>
      'Nessuna connessione: registrazione in locale. Verrà trascritto quando tornerai online.';

  @override
  String get scopeUserConversations => 'Conversazioni utente';

  @override
  String get otherAppResults => 'Risultati di altre app';

  @override
  String get chatAppsGetNewCode => 'Ottieni nuovo codice';

  @override
  String get backgroundLocationDenied => 'Accesso Posizione in Background Negato';

  @override
  String get syncFailureFootnote =>
      'Se l\'elaborazione non riesce, la registrazione viene riprovata automaticamente alla sincronizzazione successiva.';

  @override
  String get checkingNext7Days => 'Controllo dei prossimi 7 giorni';

  @override
  String get monthlyPayouts => 'Pagamenti mensili';

  @override
  String get searchLanguageHint => 'Cerca lingua per nome o codice';

  @override
  String get gotIt => 'Capito';

  @override
  String get pleaseEnterAppName => 'Inserisci il nome dell\'app';

  @override
  String get newConversations => 'Nuove conversazioni';

  @override
  String get learnMoreAtOmiTraining => 'Scopri di più su omi.me/training';

  @override
  String get entityOpenTasks => 'Attività aperte';

  @override
  String get summary => 'Riepilogo';

  @override
  String get copied => 'Copiato';

  @override
  String get feedbackReasonRecordingDelayedOrStuck => 'Ritardato o bloccato';

  @override
  String get taskIntegrations => 'Integrazioni Attività';

  @override
  String get tailoredConversationSummaries => 'Riepiloghi Conversazione Personalizzati';

  @override
  String get skipThisQuestion => 'Salta questa domanda';

  @override
  String get descriptionOptional => 'Descrizione (facoltativo)';

  @override
  String get about => 'Informazioni';

  @override
  String shareWithContactsCount(int count) {
    return 'Condividi con $count contatti';
  }

  @override
  String get discardChangesTitle => 'Scartare le modifiche?';

  @override
  String get transcriptionDiagnostics => 'Diagnostica Trascrizione';

  @override
  String get syncStatusFileUnavailable => 'File non disponibile';

  @override
  String get createNewApp => 'Crea Nuova App';

  @override
  String verifiedHoursAgo(int hours) {
    return 'Verificato ${hours}h fa';
  }

  @override
  String get chatLimitReachedTitle => 'Limite chat raggiunto';

  @override
  String get wrappedShareText => 'Il mio 2025, ricordato da Omi ✨ omi.me/wrapped';

  @override
  String get reconnectionsRecent => 'Riconnessioni (ultimi 7 giorni)';

  @override
  String get appAccess => 'Accesso App';

  @override
  String get description => 'Descrizione';

  @override
  String phoneFreeCallsRemainingWithMax(int remaining, int limit, int minutes) {
    return '$remaining chiamate gratuite rimaste su $limit questo mese · fino a $minutes min ciascuna';
  }

  @override
  String get clearOmisMemory => 'Cancella la memoria di Omi';

  @override
  String get exportSummary => 'Esporta riepilogo';

  @override
  String get install => 'Installa';

  @override
  String get syncStepBackedUpDesc => 'La trovi in Conversazioni';

  @override
  String get localProcessingInfo =>
      'L\'audio viene elaborato localmente. Funziona offline, più privato, ma consuma più batteria.';

  @override
  String get connectStripeOrPayPal => 'Collega Stripe o PayPal per ricevere pagamenti per la tua app.';

  @override
  String get wrappedMomentsHeader => 'Momenti';

  @override
  String get systemDefault => 'Predefinito del Sistema';

  @override
  String get keepUsingPendant => 'Continua con il ciondolo';

  @override
  String get paymentFailedToFetchCountries => 'Recupero paesi supportati fallito. Riprova più tardi.';

  @override
  String get micGainDescLow => 'Molto silenzioso - per ambienti rumorosi';

  @override
  String get errorUpdatingConversationTitle => 'Errore nell\'aggiornamento del titolo della conversazione';

  @override
  String timeSecsSingular(int count) {
    return '$count sec';
  }

  @override
  String timeCompactHours(int count) {
    return '${count}h';
  }

  @override
  String get browseInstallCreateApps => 'Sfoglia, installa e crea app';

  @override
  String get reddit => 'Reddit';

  @override
  String get chooseFile => 'Scegli file';

  @override
  String participantsSummary(String name, int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count altri',
      many: '$count altri',
      few: '$count altri',
      one: '1 altro',
    );
    return '$name + $_temp0';
  }

  @override
  String get connectingYourStripeAccount => 'Connessione del tuo account Stripe';

  @override
  String get cancelReasonMissingFeatures => 'Funzionalità mancanti';

  @override
  String get chatTitle => 'Chat';

  @override
  String get chatAppsNotifyMe => 'Avvisami';

  @override
  String get appAccessDesc =>
      'Le seguenti app possono accedere ai tuoi dati. Tocca un\'app per gestire i suoi permessi.';

  @override
  String get captureDisplayDetectionFailed => 'Rilevamento schermo non riuscito. Registrazione interrotta.';

  @override
  String get recapRegeneratedSnackbar => 'Riepilogo rigenerato';

  @override
  String get speakerTagPromptLabeledYouToast => 'Etichettato come te';

  @override
  String get categoryFinancial => 'Finanza';

  @override
  String get chatAppsPrefilled => 'Precompilato';

  @override
  String get noSummaryForConversation => 'Nessun riepilogo disponibile\nper questa conversazione.';

  @override
  String get aiPrompts => 'Prompt IA';

  @override
  String get view => 'Visualizza';

  @override
  String get dataAlwaysEncrypted =>
      'Indipendentemente dal livello, i tuoi dati sono sempre crittografati a riposo e in transito.';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item copiato negli appunti';
  }

  @override
  String get currentPlan => 'Attuale';

  @override
  String get phoneCallsUpsellFeature1 => 'Trascrizione in tempo reale di ogni chiamata';

  @override
  String get lowBatteryAlertTitle => 'Avviso batteria scarica';

  @override
  String get enterConversationTitle => 'Inserisci il titolo della conversazione…';

  @override
  String get pasteJsonConfig => 'Incolla la tua configurazione JSON qui sotto:';

  @override
  String get dreamReportRunLimit => 'Nessuna esecuzione manuale rimasta oggi';

  @override
  String get translationNoticeMessage =>
      'Omi traduce le conversazioni nella tua lingua principale. Aggiornala in qualsiasi momento in Impostazioni → Profili.';

  @override
  String get aiGenFailedToRegenerateIcon => 'Impossibile rigenerare l\'icona';

  @override
  String get pairingDescBee => 'Premi il pulsante 5 volte di seguito. La luce inizierà a lampeggiare in blu e verde.';

  @override
  String sharedTasksAddButton(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Aggiungi $count attività',
      one: 'Aggiungi 1 attività',
    );
    return '$_temp0';
  }

  @override
  String get paymentFailedToSavePaypal => 'Salvataggio dettagli PayPal fallito. Riprova più tardi.';

  @override
  String get couldNotLoadCheckout => 'Impossibile caricare la pagina di pagamento. Controlla la connessione e riprova.';

  @override
  String get capabilitySummary => 'Riepilogo';

  @override
  String get selectYourCountry => 'Seleziona il tuo paese';

  @override
  String uploadingAudioForTranscription(String duration) {
    return 'Caricamento di $duration di audio per la trascrizione…';
  }

  @override
  String get conversationUrlCouldNotBeShared => 'Impossibile condividere l\'URL della conversazione.';

  @override
  String get otaStartFailed =>
      'Impossibile avviare l\'aggiornamento. Controlla nome e password del Wi-Fi, poi riprova.';

  @override
  String get triggersWhenAudioBytesReceived => 'Si attiva quando vengono ricevuti byte audio.';

  @override
  String get wrappedMy2025 => 'Il mio 2025';

  @override
  String timeCompactSecs(int count) {
    return '${count}s';
  }

  @override
  String get shareWithAttendees => 'Condividi con i partecipanti';

  @override
  String get recordingsSyncAutomatically =>
      'Le registrazioni si sincronizzano automaticamente — nessuna azione necessaria.';

  @override
  String get whereDidYouHearAboutOmi => 'Come ci hai trovato?';

  @override
  String get captureMicrophonePermissionInSystemPreferences =>
      'Concedi l\'autorizzazione al microfono nelle Preferenze di Sistema';

  @override
  String audioUploadFailedTapRetry(String duration) {
    return 'Caricamento non riuscito — $duration di audio conservati sul telefono. Tocca per riprovare.';
  }

  @override
  String get captureModeLaterDescription => 'Salva l\'audio ora e trascrivilo quando vuoi.';

  @override
  String get cleanUpNothingTitle => 'Niente da riordinare';

  @override
  String get deletePersonLabel => 'Elimina persona';

  @override
  String get attachedFiles => '📎 File allegati';

  @override
  String get editGoal => 'Modifica obiettivo';

  @override
  String get helpsDiagnoseIssues => 'Aiuta a diagnosticare i problemi';

  @override
  String get bulkDeleteFailed => 'Impossibile eliminare le attività. Riprova.';

  @override
  String get manifestRefreshFailed => 'Impossibile aggiornare il manifest';

  @override
  String get searchPlaceholder => 'Cerca';

  @override
  String get appOptions => 'Opzioni app';

  @override
  String get reprocessingConversationProgress => 'Rielaborazione della conversazione…';

  @override
  String get entityWhatOmiKnows => 'Cosa sa Omi';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'La conversazione viene riassunta dopo $minutes minut$suffix di silenzio.';
  }

  @override
  String get permissionRevokedMessage => 'Vuoi che rimuoviamo anche tutte le tue registrazioni esistenti?';

  @override
  String get phoneNumberCallerIdHint => 'Dopo la verifica, questo diventa il tuo ID chiamante';

  @override
  String chatAppsTextThisTo(String address) {
    return 'Non si è aperto? Invia questo a $address';
  }

  @override
  String get upcomingMeetings => 'Riunioni imminenti';

  @override
  String get preparingSystemAudioCapture => 'Preparazione della cattura audio di sistema';

  @override
  String dreamReportQueued(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count modifiche in attesa',
      one: '1 modifica in attesa',
      zero: 'Nessuna modifica in attesa',
    );
    return '$_temp0';
  }

  @override
  String get chatReplyFailed => 'Omi non è riuscito a rispondere. Controlla la connessione e riprova.';

  @override
  String get noDataToMigrateFinalizing => 'Nessun dato da migrare. Finalizzazione…';

  @override
  String get accessibility => 'Accessibilità';

  @override
  String get openOmiOnAppleWatch => 'Apri Omi sul tuo\nApple Watch';

  @override
  String get wrappedGettingItDone => 'Portare a termine';

  @override
  String get rawData => 'Dati grezzi';

  @override
  String get passwordsDoNotMatch => 'Le password non corrispondono';

  @override
  String errorInstallingApp(String appName, String error) {
    return 'Errore durante l\'installazione di $appName: $error';
  }

  @override
  String deleteQuoted(String name) {
    return 'Elimina \"$name\"';
  }

  @override
  String get wrappedTopFivePhrases => 'Top 5 frasi';

  @override
  String get deviceOnboardingHoldButtonHint => 'Tieni premuto saldamente il pulsante finché la luce non si spegne';

  @override
  String get capabilities => 'Capacità';

  @override
  String get useMcpApiKey => 'Usa la tua chiave API MCP';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return 'Integrazione $serviceName in arrivo';
  }

  @override
  String get wrappedStruggle => 'Sfida';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return 'Stato autorizzazione notifiche: $status. Controlla Preferenze di Sistema.';
  }

  @override
  String get meetingScreenshotsTitle => 'Cosa c\'era sullo schermo';

  @override
  String verifiedMinutesAgo(int minutes) {
    return 'Verificato ${minutes}min fa';
  }

  @override
  String get permissionsRequired => 'Autorizzazioni richieste';

  @override
  String get speakerTagPromptNotSure => 'Non so';

  @override
  String get current => 'Attuale';

  @override
  String get improveConnectionAction => 'Capito';

  @override
  String get profile => 'Profilo';

  @override
  String get audioPlaybackFailed => 'Impossibile riprodurre l\'audio. Il file potrebbe essere danneggiato o mancante.';

  @override
  String get billingYearly => 'Annuale';

  @override
  String get batteryUsageHigher => 'Il consumo della batteria sarà maggiore rispetto alla trascrizione cloud.';

  @override
  String get permissionsLabel => 'PERMESSI';

  @override
  String get enhanceTranscriptAccuracy => 'Migliora Precisione Trascrizione';

  @override
  String get connectedStatus => 'Connesso';

  @override
  String get microphonePermissionDenied =>
      'Autorizzazione microfono negata. Concedi l\'autorizzazione in Preferenze di Sistema > Privacy e sicurezza > Microfono.';

  @override
  String get onDeviceModelDownloadSuccessDesc => 'Modello Whisper scaricato correttamente';

  @override
  String get storageLocationLimitlessPendant => 'Limitless Pendant';

  @override
  String get chatAppsLinkExpired => 'Quel link è scaduto. Tocca Apri Telegram per ottenerne uno nuovo.';

  @override
  String get captureOfflineBuffering => 'Offline, buffering';

  @override
  String get pleaseCheckInternetConnection => 'Controlla la tua connessione Internet e riprova';

  @override
  String get todaysScore => 'Punteggio di oggi';

  @override
  String get conversationReprocessed => 'Conversazione aggiornata';

  @override
  String get loadingDuration => 'Caricamento durata…';

  @override
  String get noSummary => 'Nessun riepilogo';

  @override
  String get raybanMetaMicrophoneReady => 'Microfono pronto';

  @override
  String get applyFilters => 'Applica filtri';

  @override
  String get appDescriptionPlaceholder =>
      'La mia fantastica app è un\'app fantastica che fa cose incredibili. È la migliore app di sempre!';

  @override
  String get cancelSubscriptionKeepAccessMessage =>
      'Manterrai l\'accesso fino alla fine del periodo di fatturazione in corso.';

  @override
  String get editYourReview => 'Modifica la tua recensione';

  @override
  String get actionItemsTitle => 'Attività';

  @override
  String get raybanMetaAudioOnlyTitle => 'Modalità solo audio di Ray-Ban Meta';

  @override
  String get reviewSomeoneElse => 'Qualcun altro…';

  @override
  String get betaTesterMessage =>
      'Sei un beta tester per questa app. Non è ancora pubblica. Sarà pubblica dopo l\'approvazione.';

  @override
  String chatAppsIMessageTo(String address) {
    return 'A: Omi · $address';
  }

  @override
  String get comingSoon => 'Prossimamente';

  @override
  String rollbackConfirmMessage(String version) {
    return 'Questo sostituirà il firmware attuale con l\'ultima versione stabile ($version). Il dispositivo si riavvierà dopo l\'aggiornamento.';
  }

  @override
  String get termsOfService => 'Termini di servizio';

  @override
  String get wrappedNotMentioned => 'Non menzionato';

  @override
  String get deviceDisconnectedNotificationTitle => 'Il tuo dispositivo Omi si è disconnesso';

  @override
  String get rayBanMetaMicPickerDescription =>
      'Seleziona il microfono Bluetooth degli occhiali. La musica viene messa in pausa mentre Omi lo usa.';

  @override
  String get chatBlockQuestion => 'Domanda';

  @override
  String get successfullyConnectedTodoist => 'Connesso con successo a Todoist!';

  @override
  String voiceRecognitionStatus(String status) {
    String _temp0 = intl.Intl.selectLogic(
      status,
      {
        'ready': 'Voce pronta per il riconoscimento',
        'saved_sample_awaiting_embedding': 'Campione salvato; elaborazione vocale ancora necessaria',
        'not_learned': 'Voce non appresa',
        'other': 'Stato della voce sconosciuto',
      },
    );
    return '$_temp0';
  }

  @override
  String addQueryAsNewPerson(String query) {
    return 'Aggiungi \"$query\" come nuova persona';
  }

  @override
  String confidenceReasonAutoConfirmed(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Hai confermato $count etichette automatiche',
      one: 'Hai confermato 1 etichetta automatica',
    );
    return '$_temp0';
  }

  @override
  String get recordAudioConversations => 'Registra conversazioni audio';

  @override
  String get saveKeyWarning => 'Salva questa chiave ora! Non potrai vederla di nuovo.';

  @override
  String get saveChanges => 'Salva modifiche';

  @override
  String get sttModelSlower => 'Più lento';

  @override
  String get otaDownloadFailed => 'Download del firmware non riuscito. Controlla la connessione Wi-Fi e riprova.';

  @override
  String get captureRecordingViewing => 'Stai visualizzando questa registrazione';

  @override
  String get resetFilters => 'Reimposta filtri';

  @override
  String get voiceSettingsSaveOthersSubtitle =>
      'Quando dai un nome a qualcuno, Omi conserva un breve campione vocale per riconoscerlo la prossima volta';

  @override
  String get iveDoneThis => 'L\'ho fatto';

  @override
  String get howSyncingWorks => 'Come funziona la sincronizzazione';

  @override
  String greetingWithName(String greeting, String name) {
    return '$greeting, $name';
  }

  @override
  String reviewRemaining(int count) {
    return 'Ne restano $count';
  }

  @override
  String get feedbackReasonRecordingMissingAudio => 'Audio mancante';

  @override
  String get appCategoryModalTitle => 'Categoria dell\'app';

  @override
  String get pushToTalk => 'Premi per parlare';

  @override
  String get noApiKeysYet => 'Nessuna chiave API ancora. Creane una per integrare con la tua app.';

  @override
  String minLabel(int count) {
    return '$count min';
  }

  @override
  String appRatingCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count valutazioni',
      one: '1 valutazione',
    );
    return '$_temp0';
  }

  @override
  String get wrappedFood => 'CIBO';

  @override
  String get aboutAMinuteRemaining => 'Circa un minuto rimanente';

  @override
  String get clearLogs => 'Cancella log';

  @override
  String get wrappedBook => 'LIBRO';

  @override
  String get phoneCallSubtitle => 'Registra una chiamata con trascrizione live';

  @override
  String deleteConversationsTitle(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Eliminare $count conversazioni?',
      one: 'Eliminare 1 conversazione?',
    );
    return '$_temp0';
  }

  @override
  String get deleteSelected => 'Elimina selezionati';

  @override
  String failedToDeleteGraph(String error) {
    return 'Impossibile eliminare il grafo: $error';
  }

  @override
  String get setupQuestionsIntro => 'Rispondi ad alcune domande per personalizzare la tua esperienza';

  @override
  String get category => 'Categoria';

  @override
  String get timeout30MinutesDesc => 'Termina conversazione dopo 30 minuti di silenzio';

  @override
  String get goalDeleted => 'Obiettivo eliminato';

  @override
  String get conversationDisplay => 'Visualizzazione Conversazioni';

  @override
  String get conversationNoSummaryYet => 'Questa conversazione non ha ancora un riepilogo.';

  @override
  String get chatsLowercase => 'chat';

  @override
  String get clearChatQuestion => 'Cancellare la chat?';

  @override
  String get signInTitle => 'Accedi';

  @override
  String get loadingKnowledgeGraph => 'Caricamento del grafo della conoscenza…';

  @override
  String get goalTracker => 'Tracker degli Obiettivi';

  @override
  String get commandRequired => '⌘ richiesto';

  @override
  String get permissionEnabled => 'Attivata';

  @override
  String get submitReview => 'Invia recensione';

  @override
  String chatUsageCost(String used, String limit) {
    return 'Chat: \$$used / \$$limit utilizzato questo mese';
  }

  @override
  String get discard => 'Scarta';

  @override
  String dreamReportPasses(int count, int limit) {
    return '$count di $limit passaggi oggi';
  }

  @override
  String get unlockOmiInfiniteMemory => 'Ricordi illimitati';

  @override
  String get addAppPersonaConflictWithCapabilities => 'Persona non può essere selezionato con altre capacità';

  @override
  String get whyAreYouCanceling => 'Perché annulli?';

  @override
  String get permissionRequestedExclaim => 'Permesso Richiesto!';

  @override
  String get chatBlockOpenInMemories => 'Apri in Ricordi';

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total oggetti';
  }

  @override
  String get deleteActionItemTitle => 'Elimina attività';

  @override
  String get rollBack => 'Ripristina';

  @override
  String get chatAppsOmiPro => 'OMI PRO';

  @override
  String disconnectFromAppDesc(String appName) {
    return 'Questo rimuoverà la tua autenticazione $appName. Dovrai riconnetterti per usarlo di nuovo.';
  }

  @override
  String get onDeviceModelSize => 'Dimensione del modello';

  @override
  String tagSpeaker(int speakerId) {
    return 'Tagga Speaker $speakerId';
  }

  @override
  String get couldNotOpenUrl => 'Impossibile aprire l\'URL. Riprova.';

  @override
  String get conversationNewIndicator => 'Nuovo';

  @override
  String get notEnoughSpeechDescription =>
      'Non è stato rilevato abbastanza parlato. Per favore parla di più e riprova.';

  @override
  String get liveRssiOverTime => 'RSSI in tempo reale';

  @override
  String get usageEverywhere => 'Ovunque';

  @override
  String nConversations(int count) {
    return '$count conversazioni';
  }

  @override
  String get wrappedConversationsLabel => 'conversazioni';

  @override
  String get usageYear => 'Quest\'Anno';

  @override
  String get noContactsMatchSearch => 'Nessun contatto corrisponde alla ricerca';

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count attività$s eliminate';
  }

  @override
  String get actionItemMarkedIncomplete => 'Attività contrassegnata come non completata';

  @override
  String get start => 'Avvia';

  @override
  String discardedConversationTitle(String duration) {
    return 'Scartata · $duration';
  }

  @override
  String get debugLogsCleared => 'Log di debug cancellati';

  @override
  String get preparingAudioCapture => 'Preparazione cattura audio';

  @override
  String get availablePaymentMethods => 'Metodi di pagamento disponibili';

  @override
  String get deleteReasonOther => 'Altro';

  @override
  String get accountCutoverMigrationInProgressTitle => 'Migrazione in corso';

  @override
  String get connectedKnowledgeData => 'Dati di conoscenza collegati';

  @override
  String get wrappedMostFunDay => 'Più divertente';

  @override
  String get onboardingAccessibilityRequired =>
      'È necessaria l\'autorizzazione accessibilità per rilevare riunioni del browser.';

  @override
  String get selectActionItems => 'Selezione multipla';

  @override
  String switchApiConfirmBody(String environment) {
    return 'Passare a $environment? Dovrai chiudere e riaprire l\'app perché le modifiche abbiano effetto.';
  }

  @override
  String get whisperModelSizeLarge => 'Grande';

  @override
  String get currentVersion => 'Versione attuale';

  @override
  String get aiAppGeneratorBannerTitle => 'Crea un\'app con l\'IA con un tocco';

  @override
  String get rayBanMetaMicPickerLoadError =>
      'Impossibile caricare i microfoni Bluetooth. Verifica che il Bluetooth sia attivo e riprova.';

  @override
  String get noneSelected => 'Nessuna selezionata';

  @override
  String get entityKeptCurrent => 'Tenuto aggiornato da Omi';

  @override
  String migratingFromTo(String source, String target) {
    return 'Migrazione da $source a $target';
  }

  @override
  String get controlNotificationFrequency => 'Controlla quanto spesso Omi ti invia notifiche proattive.';

  @override
  String get connectionUptime => 'Tempo di attività';

  @override
  String get categoryLabel => 'Categoria';

  @override
  String get aboutTheApp => 'Informazioni sull\'app';

  @override
  String get planSheetChooseYourPlan => 'Scegli il piano più adatto a te.';

  @override
  String get almostDone => 'Quasi fatto…';

  @override
  String get tasksFromConversationsWillAppear =>
      'Le attività dalle tue conversazioni appariranno qui.\nFai clic su Crea per aggiungerne una manualmente.';

  @override
  String get personLastHeard => 'Ultimo ascolto';

  @override
  String get durationThreshold => 'Soglia Durata';

  @override
  String get transcriptionServiceDiagnosticStatus => 'Stato diagnostico del servizio di trascrizione';

  @override
  String get triggersWhenNewTranscriptReceived => 'Si attiva quando viene ricevuta una nuova trascrizione.';

  @override
  String get aboutOmi => 'Informazioni su Omi';

  @override
  String get identifyingOthers => 'Identificazione di Altri';

  @override
  String get phoneCallsSubtitle => 'Chiama con trascrizione in tempo reale';

  @override
  String get creatingYourApp => 'Creazione della tua app…';

  @override
  String get analyzingYourData => 'Analisi dei tuoi dati…';
}
