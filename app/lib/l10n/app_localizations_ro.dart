// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Romanian Moldavian Moldovan (`ro`).
class AppLocalizationsRo extends AppLocalizations {
  AppLocalizationsRo([String locale = 'ro']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'Conversație';

  @override
  String get transcriptTab => 'Transcriere';

  @override
  String get actionItemsTab => 'Sarcini';

  @override
  String get deleteConversationTitle => 'Ștergi conversația?';

  @override
  String get deleteConversationMessage =>
      'Ești sigur că vrei să ștergi această conversație? Această acțiune nu poate fi anulată.';

  @override
  String get confirm => 'Confirmă';

  @override
  String get cancel => 'Cancel';

  @override
  String get ok => 'Ok';

  @override
  String get delete => 'Delete';

  @override
  String get add => 'Adaugă';

  @override
  String get update => 'Actualizează';

  @override
  String get save => 'Salvează';

  @override
  String get edit => 'Editează';

  @override
  String get close => 'Închide';

  @override
  String get clear => 'Șterge';

  @override
  String get copyTranscript => 'Copiază transcrierea';

  @override
  String get copySummary => 'Copiază rezumatul';

  @override
  String get testPrompt => 'Testează promptul';

  @override
  String get reprocessConversation => 'Reprocesează conversația';

  @override
  String get deleteConversation => 'Șterge conversația';

  @override
  String get contentCopied => 'Conținut copiat în clipboard';

  @override
  String get failedToUpdateStarred => 'Nu s-a putut actualiza starea de favorit.';

  @override
  String get conversationUrlNotShared => 'URL-ul conversației nu a putut fi partajat.';

  @override
  String get errorProcessingConversation =>
      'Eroare la procesarea conversației. Te rugăm să încerci din nou mai târziu.';

  @override
  String get noInternetConnection => 'Te rugăm să verifici conexiunea la internet și să încerci din nou.';

  @override
  String get unableToDeleteConversation => 'Nu se poate șterge conversația';

  @override
  String get somethingWentWrong => 'Ceva nu a mers bine! Te rugăm să încerci din nou mai târziu.';

  @override
  String get copyErrorMessage => 'Copiază mesajul de eroare';

  @override
  String get errorCopied => 'Mesaj de eroare copiat în clipboard';

  @override
  String get remaining => 'Rămas';

  @override
  String get loading => 'Se încarcă...';

  @override
  String get loadingDuration => 'Se încarcă durata...';

  @override
  String secondsCount(int count) {
    return '$count secunde';
  }

  @override
  String get people => 'Persoane';

  @override
  String get addNewPerson => 'Adaugă persoană nouă';

  @override
  String get editPerson => 'Editează persoana';

  @override
  String get createPersonHint => 'Creează o persoană nouă și antrenează Omi să recunoască și vorbirea ei!';

  @override
  String get speechProfile => 'Profil vocal';

  @override
  String sampleNumber(int number) {
    return 'Eșantion $number';
  }

  @override
  String get settings => 'Setări';

  @override
  String get language => 'Limbă';

  @override
  String get selectLanguage => 'Selectează limba';

  @override
  String get deleting => 'Se șterge...';

  @override
  String get pleaseCompleteAuthentication =>
      'Te rugăm să finalizezi autentificarea în browser. După ce ai terminat, revino la aplicație.';

  @override
  String get failedToStartAuthentication => 'Nu s-a putut inițializa autentificarea';

  @override
  String get importStarted => 'Import inițiat! Vei fi notificat când se finalizează.';

  @override
  String get failedToStartImport => 'Nu s-a putut inițializa importul. Te rugăm să încerci din nou.';

  @override
  String get couldNotAccessFile => 'Nu s-a putut accesa fișierul selectat';

  @override
  String get askOmi => 'Întreabă Omi';

  @override
  String get done => 'Done';

  @override
  String get disconnected => 'Deconectat';

  @override
  String get searching => 'Se caută';

  @override
  String get connectDevice => 'Conectează dispozitivul';

  @override
  String get monthlyLimitReached => 'Ai atins limita lunară.';

  @override
  String get checkUsage => 'Verifică utilizarea';

  @override
  String get syncingRecordings => 'Se sincronizează înregistrările';

  @override
  String get recordingsToSync => 'Înregistrări de sincronizat';

  @override
  String get allCaughtUp => 'Totul este actualizat';

  @override
  String get sync => 'Sincronizează';

  @override
  String get pendantUpToDate => 'Pandantivul este actualizat';

  @override
  String get allRecordingsSynced => 'Toate înregistrările sunt sincronizate';

  @override
  String get syncingInProgress => 'Sincronizare în curs';

  @override
  String get readyToSync => 'Pregătit pentru sincronizare';

  @override
  String get tapSyncToStart => 'Apasă Sincronizează pentru a începe';

  @override
  String get pendantNotConnected => 'Pandantivul nu este conectat. Conectează pentru a sincroniza.';

  @override
  String get everythingSynced => 'Totul este deja sincronizat.';

  @override
  String get recordingsNotSynced => 'Ai înregistrări care nu sunt încă sincronizate.';

  @override
  String get syncingBackground => 'Vom continua să sincronizăm înregistrările în fundal.';

  @override
  String get noConversationsYet => 'Încă nu există conversații.';

  @override
  String get noStarredConversations => 'Încă nu există conversații favorite.';

  @override
  String get starConversationHint =>
      'Pentru a marca o conversație ca favorită, deschide-o și apasă iconița de stea din antet.';

  @override
  String get searchConversations => 'Caută conversații';

  @override
  String selectedCount(int count, Object s) {
    return '$count selectate';
  }

  @override
  String get merge => 'Combină';

  @override
  String get mergeConversations => 'Combină conversațiile';

  @override
  String mergeConversationsMessage(int count) {
    return 'Aceasta va combina $count conversații într-una singură. Tot conținutul va fi combinat și regenerat.';
  }

  @override
  String get mergingInBackground => 'Se combină în fundal. Acest lucru poate dura câteva momente.';

  @override
  String get failedToStartMerge => 'Nu s-a putut inițializa combinarea';

  @override
  String get askAnything => 'Întreabă orice';

  @override
  String get noMessagesYet => 'Încă nu există mesaje!\nDe ce nu începi o conversație?';

  @override
  String get deletingMessages => 'Se șterg mesajele din memoria Omi...';

  @override
  String get messageCopied => 'Mesaj copiat în clipboard.';

  @override
  String get cannotReportOwnMessage => 'Nu poți raporta propriile mesaje.';

  @override
  String get reportMessage => 'Raportează mesajul';

  @override
  String get reportMessageConfirm => 'Ești sigur că vrei să raportezi acest mesaj?';

  @override
  String get messageReported => 'Mesaj raportat cu succes.';

  @override
  String get thankYouFeedback => 'Mulțumim pentru feedback!';

  @override
  String get clearChat => 'Ștergi chat-ul?';

  @override
  String get clearChatConfirm => 'Ești sigur că vrei să ștergi chat-ul? Această acțiune nu poate fi anulată.';

  @override
  String get maxFilesLimit => 'Poți încărca doar 4 fișiere simultan';

  @override
  String get chatWithOmi => 'Chat cu Omi';

  @override
  String get apps => 'Aplicații';

  @override
  String get noAppsFound => 'Nu s-au găsit aplicații';

  @override
  String get tryAdjustingSearch => 'Încearcă să ajustezi căutarea sau filtrele';

  @override
  String get createYourOwnApp => 'Creează-ți propria aplicație';

  @override
  String get buildAndShareApp => 'Construiește și partajează aplicația ta personalizată';

  @override
  String get searchApps => 'Caută peste 1500 de aplicații';

  @override
  String get myApps => 'Aplicațiile mele';

  @override
  String get installedApps => 'Aplicații instalate';

  @override
  String get unableToFetchApps =>
      'Nu s-au putut prelua aplicațiile :(\n\nTe rugăm să verifici conexiunea la internet și să încerci din nou.';

  @override
  String get aboutOmi => 'Despre Omi';

  @override
  String get privacyPolicy => 'Privacy Policy';

  @override
  String get visitWebsite => 'Vizitează site-ul web';

  @override
  String get helpOrInquiries => 'Ajutor sau întrebări?';

  @override
  String get joinCommunity => 'Alătură-te comunității!';

  @override
  String get membersAndCounting => 'Peste 8000 de membri și numărul crește.';

  @override
  String get deleteAccountTitle => 'Șterge contul';

  @override
  String get deleteAccountConfirm => 'Ești sigur că vrei să îți ștergi contul?';

  @override
  String get cannotBeUndone => 'Acest lucru nu poate fi anulat.';

  @override
  String get allDataErased => 'Toate amintirile și conversațiile tale vor fi șterse permanent.';

  @override
  String get appsDisconnected => 'Aplicațiile și integrările tale vor fi deconectate imediat.';

  @override
  String get exportBeforeDelete =>
      'Poți exporta datele înainte de a-ți șterge contul, dar odată șters, nu poate fi recuperat.';

  @override
  String get deleteAccountCheckbox =>
      'Înțeleg că ștergerea contului meu este permanentă și toate datele, inclusiv amintirile și conversațiile, vor fi pierdute și nu pot fi recuperate.';

  @override
  String get areYouSure => 'Ești sigur?';

  @override
  String get deleteAccountFinal =>
      'Această acțiune este ireversibilă și va șterge permanent contul tău și toate datele asociate. Ești sigur că vrei să continui?';

  @override
  String get deleteNow => 'Șterge acum';

  @override
  String get goBack => 'Înapoi';

  @override
  String get checkBoxToConfirm =>
      'Bifează caseta pentru a confirma că înțelegi că ștergerea contului este permanentă și ireversibilă.';

  @override
  String get profile => 'Profil';

  @override
  String get name => 'Nume';

  @override
  String get email => 'Email';

  @override
  String get customVocabulary => 'Vocabular personalizat';

  @override
  String get identifyingOthers => 'Identificarea altora';

  @override
  String get paymentMethods => 'Metode de plată';

  @override
  String get conversationDisplay => 'Afișare conversații';

  @override
  String get dataPrivacy => 'Date și confidențialitate';

  @override
  String get userId => 'ID utilizator';

  @override
  String get notSet => 'Nesetat';

  @override
  String get userIdCopied => 'ID utilizator copiat în clipboard';

  @override
  String get systemDefault => 'Implicit sistem';

  @override
  String get planAndUsage => 'Plan și utilizare';

  @override
  String get offlineSync => 'Sincronizare offline';

  @override
  String get deviceSettings => 'Setări dispozitiv';

  @override
  String get chatTools => 'Instrumente chat';

  @override
  String get feedbackBug => 'Feedback / Bug';

  @override
  String get helpCenter => 'Centru de asistență';

  @override
  String get developerSettings => 'Setări dezvoltator';

  @override
  String get getOmiForMac => 'Obține Omi pentru Mac';

  @override
  String get referralProgram => 'Program de recomandări';

  @override
  String get signOut => 'Deconectare';

  @override
  String get appAndDeviceCopied => 'Detalii aplicație și dispozitiv copiate';

  @override
  String get wrapped2025 => 'Wrapped 2025';

  @override
  String get yourPrivacyYourControl => 'Confidențialitatea ta, sub controlul tău';

  @override
  String get privacyIntro =>
      'La Omi, ne angajăm să îți protejăm confidențialitatea. Această pagină îți permite să controlezi modul în care datele tale sunt stocate și utilizate.';

  @override
  String get learnMore => 'Află mai multe...';

  @override
  String get dataProtectionLevel => 'Nivel de protecție a datelor';

  @override
  String get dataProtectionDesc =>
      'Datele tale sunt securizate implicit cu criptare puternică. Revizuiește setările și opțiunile viitoare de confidențialitate mai jos.';

  @override
  String get appAccess => 'Acces aplicații';

  @override
  String get appAccessDesc =>
      'Următoarele aplicații pot accesa datele tale. Apasă pe o aplicație pentru a-i gestiona permisiunile.';

  @override
  String get noAppsExternalAccess => 'Nicio aplicație instalată nu are acces extern la datele tale.';

  @override
  String get deviceName => 'Nume dispozitiv';

  @override
  String get deviceId => 'ID dispozitiv';

  @override
  String get firmware => 'Firmware';

  @override
  String get sdCardSync => 'Sincronizare card SD';

  @override
  String get hardwareRevision => 'Revizie hardware';

  @override
  String get modelNumber => 'Număr model';

  @override
  String get manufacturer => 'Producător';

  @override
  String get doubleTap => 'Dublă apăsare';

  @override
  String get ledBrightness => 'Luminozitate LED';

  @override
  String get micGain => 'Câștig microfon';

  @override
  String get disconnect => 'Deconectează';

  @override
  String get forgetDevice => 'Uită dispozitivul';

  @override
  String get chargingIssues => 'Probleme la încărcare';

  @override
  String get disconnectDevice => 'Deconectează dispozitivul';

  @override
  String get unpairDevice => 'Deperechează dispozitivul';

  @override
  String get unpairAndForget => 'Deperechează și uită dispozitivul';

  @override
  String get deviceDisconnectedMessage => 'Omi-ul tău a fost deconectat 😔';

  @override
  String get deviceUnpairedMessage =>
      'Dispozitiv depereche. Mergi la Setări > Bluetooth și uită dispozitivul pentru a finaliza deperecherea.';

  @override
  String get unpairDialogTitle => 'Deperechează dispozitivul';

  @override
  String get unpairDialogMessage =>
      'Acest lucru va deperechia dispozitivul astfel încât să poată fi conectat la alt telefon. Va trebui să mergi la Setări > Bluetooth și să uiți dispozitivul pentru a finaliza procesul.';

  @override
  String get deviceNotConnected => 'Dispozitiv neconectat';

  @override
  String get connectDeviceMessage =>
      'Conectează dispozitivul Omi pentru a accesa\nsetările și personalizarea dispozitivului';

  @override
  String get deviceInfoSection => 'Informații dispozitiv';

  @override
  String get customizationSection => 'Personalizare';

  @override
  String get hardwareSection => 'Hardware';

  @override
  String get v2Undetected => 'V2 nedetectat';

  @override
  String get v2UndetectedMessage =>
      'Vedem că ai fie un dispozitiv V1, fie dispozitivul tău nu este conectat. Funcționalitatea card SD este disponibilă doar pentru dispozitivele V2.';

  @override
  String get endConversation => 'Încheie conversația';

  @override
  String get pauseResume => 'Pauză/Reia';

  @override
  String get starConversation => 'Marchează conversația ca favorită';

  @override
  String get doubleTapAction => 'Acțiune dublă apăsare';

  @override
  String get endAndProcess => 'Încheie și procesează conversația';

  @override
  String get pauseResumeRecording => 'Pauză/Reia înregistrarea';

  @override
  String get starOngoing => 'Marchează conversația în curs ca favorită';

  @override
  String get off => 'Oprit';

  @override
  String get max => 'Maxim';

  @override
  String get mute => 'Mut';

  @override
  String get quiet => 'Silențios';

  @override
  String get normal => 'Normal';

  @override
  String get high => 'Ridicat';

  @override
  String get micGainDescMuted => 'Microfonul este mut';

  @override
  String get micGainDescLow => 'Foarte silențios - pentru medii zgomotoase';

  @override
  String get micGainDescModerate => 'Silențios - pentru zgomot moderat';

  @override
  String get micGainDescNeutral => 'Neutru - înregistrare echilibrată';

  @override
  String get micGainDescSlightlyBoosted => 'Ușor amplificat - utilizare normală';

  @override
  String get micGainDescBoosted => 'Amplificat - pentru medii liniștite';

  @override
  String get micGainDescHigh => 'Ridicat - pentru voci distante sau line';

  @override
  String get micGainDescVeryHigh => 'Foarte ridicat - pentru surse foarte liniștite';

  @override
  String get micGainDescMax => 'Maxim - folosește cu atenție';

  @override
  String get developerSettingsTitle => 'Setări dezvoltator';

  @override
  String get saving => 'Se salvează...';

  @override
  String get personaConfig => 'Configurează personalitatea AI';

  @override
  String get beta => 'BETA';

  @override
  String get transcription => 'Transcriere';

  @override
  String get transcriptionConfig => 'Configurează furnizorul STT';

  @override
  String get conversationTimeout => 'Timeout conversație';

  @override
  String get conversationTimeoutConfig => 'Setează când se încheie automat conversațiile';

  @override
  String get importData => 'Importă date';

  @override
  String get importDataConfig => 'Importă date din alte surse';

  @override
  String get debugDiagnostics => 'Depanare și diagnosticare';

  @override
  String get endpointUrl => 'URL endpoint';

  @override
  String get noApiKeys => 'Încă nu există chei API';

  @override
  String get createKeyToStart => 'Creează o cheie pentru a începe';

  @override
  String get createKey => 'Creează cheie';

  @override
  String get docs => 'Documente';

  @override
  String get yourOmiInsights => 'Statisticile tale Omi';

  @override
  String get today => 'Astăzi';

  @override
  String get thisMonth => 'Luna aceasta';

  @override
  String get thisYear => 'Anul acesta';

  @override
  String get allTime => 'Toate timpurile';

  @override
  String get noActivityYet => 'Încă nu există activitate';

  @override
  String get startConversationToSeeInsights =>
      'Începe o conversație cu Omi\npentru a vedea statisticile de utilizare aici.';

  @override
  String get listening => 'Ascultare';

  @override
  String get listeningSubtitle => 'Timpul total în care Omi a ascultat activ.';

  @override
  String get understanding => 'Înțelegere';

  @override
  String get understandingSubtitle => 'Cuvinte înțelese din conversațiile tale.';

  @override
  String get providing => 'Furnizare';

  @override
  String get providingSubtitle => 'Sarcini și notițe capturate automat.';

  @override
  String get remembering => 'Memorare';

  @override
  String get rememberingSubtitle => 'Fapte și detalii memorate pentru tine.';

  @override
  String get unlimitedPlan => 'Plan nelimitat';

  @override
  String get managePlan => 'Gestionează planul';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'Planul tău se va anula pe $date.';
  }

  @override
  String renewsOn(String date) {
    return 'Planul tău se reînnoiește pe $date.';
  }

  @override
  String get basicPlan => 'Plan gratuit';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used din $limit minute utilizate';
  }

  @override
  String get upgrade => 'Upgrade';

  @override
  String get upgradeToUnlimited => 'Upgrade la Nelimitat';

  @override
  String basicPlanDesc(int limit) {
    return 'Planul tău include $limit minute gratuite pe lună. Fă upgrade pentru a deveni nelimitat.';
  }

  @override
  String get shareStatsMessage => 'Împărtășesc statisticile mele Omi! (omi.me - asistentul tău AI mereu activ)';

  @override
  String get sharePeriodToday => 'Astăzi, Omi a:';

  @override
  String get sharePeriodMonth => 'Luna aceasta, Omi a:';

  @override
  String get sharePeriodYear => 'Anul acesta, Omi a:';

  @override
  String get sharePeriodAllTime => 'Până acum, Omi a:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 Ascultat timp de $minutes minute';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 Înțeles $words cuvinte';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ Furnizat $count perspective';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 Memorat $count amintiri';
  }

  @override
  String get debugLogs => 'Jurnale de depanare';

  @override
  String get debugLogsAutoDelete => 'Se șterg automat după 3 zile.';

  @override
  String get debugLogsDesc => 'Ajută la diagnosticarea problemelor';

  @override
  String get noLogFilesFound => 'Nu s-au găsit fișiere jurnal.';

  @override
  String get omiDebugLog => 'Jurnal de depanare Omi';

  @override
  String get logShared => 'Jurnal partajat';

  @override
  String get selectLogFile => 'Selectează fișier jurnal';

  @override
  String get shareLogs => 'Partajează jurnalele';

  @override
  String get debugLogCleared => 'Jurnal de depanare șters';

  @override
  String get exportStarted => 'Export inițiat. Acest lucru poate dura câteva secunde...';

  @override
  String get exportAllData => 'Exportă toate datele';

  @override
  String get exportDataDesc => 'Exportă conversațiile într-un fișier JSON';

  @override
  String get exportedConversations => 'Conversații exportate din Omi';

  @override
  String get exportShared => 'Export partajat';

  @override
  String get deleteKnowledgeGraphTitle => 'Ștergi graficul de cunoștințe?';

  @override
  String get deleteKnowledgeGraphMessage =>
      'Acest lucru va șterge toate datele derivate din graficul de cunoștințe (noduri și conexiuni). Amintirile tale originale vor rămâne în siguranță. Graficul va fi reconstruit în timp sau la următoarea solicitare.';

  @override
  String get knowledgeGraphDeleted => 'Grafic de cunoștințe șters cu succes';

  @override
  String deleteGraphFailed(String error) {
    return 'Nu s-a putut șterge graficul: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'Șterge graficul de cunoștințe';

  @override
  String get deleteKnowledgeGraphDesc => 'Șterge toate nodurile și conexiunile';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'Server MCP';

  @override
  String get mcpServerDesc => 'Conectează asistenți AI la datele tale';

  @override
  String get serverUrl => 'URL server';

  @override
  String get urlCopied => 'URL copiat';

  @override
  String get apiKeyAuth => 'Autentificare cheie API';

  @override
  String get header => 'Antet';

  @override
  String get authorizationBearer => 'Authorization: Bearer <key>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'ID client';

  @override
  String get clientSecret => 'Secret client';

  @override
  String get useMcpApiKey => 'Folosește cheia ta API MCP';

  @override
  String get webhooks => 'Webhooks';

  @override
  String get conversationEvents => 'Evenimente conversație';

  @override
  String get newConversationCreated => 'Conversație nouă creată';

  @override
  String get realtimeTranscript => 'Transcriere în timp real';

  @override
  String get transcriptReceived => 'Transcriere primită';

  @override
  String get audioBytes => 'Bytes audio';

  @override
  String get audioDataReceived => 'Date audio primite';

  @override
  String get intervalSeconds => 'Interval (secunde)';

  @override
  String get daySummary => 'Rezumat zilnic';

  @override
  String get summaryGenerated => 'Rezumat generat';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'Adaugă la claude_desktop_config.json';

  @override
  String get copyConfig => 'Copiază configurația';

  @override
  String get configCopied => 'Configurație copiată în clipboard';

  @override
  String get listeningMins => 'Ascultare (minute)';

  @override
  String get understandingWords => 'Înțelegere (cuvinte)';

  @override
  String get insights => 'Perspective';

  @override
  String get memories => 'Amintiri';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '$used din $limit minute utilizate luna aceasta';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '$used din $limit cuvinte utilizate luna aceasta';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '$used din $limit perspective obținute luna aceasta';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return '$used din $limit amintiri create luna aceasta';
  }

  @override
  String get visibility => 'Vizibilitate';

  @override
  String get visibilitySubtitle => 'Controlează care conversații apar în lista ta';

  @override
  String get showShortConversations => 'Afișează conversații scurte';

  @override
  String get showShortConversationsDesc => 'Afișează conversații mai scurte decât pragul';

  @override
  String get showDiscardedConversations => 'Afișează conversații eliminate';

  @override
  String get showDiscardedConversationsDesc => 'Include conversații marcate ca eliminate';

  @override
  String get shortConversationThreshold => 'Prag conversații scurte';

  @override
  String get shortConversationThresholdSubtitle =>
      'Conversațiile mai scurte decât aceasta vor fi ascunse dacă nu este activată opțiunea de mai sus';

  @override
  String get durationThreshold => 'Prag durată';

  @override
  String get durationThresholdDesc => 'Ascunde conversații mai scurte decât aceasta';

  @override
  String minLabel(int count) {
    return '$count min';
  }

  @override
  String get customVocabularyTitle => 'Vocabular personalizat';

  @override
  String get addWords => 'Adaugă cuvinte';

  @override
  String get addWordsDesc => 'Nume, termeni sau cuvinte neobișnuite';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'Connect';

  @override
  String get comingSoon => 'În curând';

  @override
  String get chatToolsFooter => 'Conectează aplicațiile tale pentru a vizualiza date și statistici în chat.';

  @override
  String get completeAuthInBrowser =>
      'Te rugăm să finalizezi autentificarea în browser. După ce ai terminat, revino la aplicație.';

  @override
  String failedToStartAuth(String appName) {
    return 'Nu s-a putut inițializa autentificarea $appName';
  }

  @override
  String disconnectAppTitle(String appName) {
    return 'Deconectezi $appName?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'Ești sigur că vrei să te deconectezi de la $appName? Te poți reconecta oricând.';
  }

  @override
  String disconnectedFrom(String appName) {
    return 'Deconectat de la $appName';
  }

  @override
  String get failedToDisconnect => 'Nu s-a putut deconecta';

  @override
  String connectTo(String appName) {
    return 'Conectează-te la $appName';
  }

  @override
  String authAccessMessage(String appName) {
    return 'Va trebui să autorizezi Omi să acceseze datele tale $appName. Aceasta va deschide browser-ul pentru autentificare.';
  }

  @override
  String get continueAction => 'Continuă';

  @override
  String get languageTitle => 'Limbă';

  @override
  String get primaryLanguage => 'Limbă principală';

  @override
  String get automaticTranslation => 'Traducere automată';

  @override
  String get detectLanguages => 'Detectează peste 10 limbi';

  @override
  String get authorizeSavingRecordings => 'Autorizează salvarea înregistrărilor';

  @override
  String get thanksForAuthorizing => 'Mulțumim pentru autorizare!';

  @override
  String get needYourPermission => 'Avem nevoie de permisiunea ta';

  @override
  String get alreadyGavePermission =>
      'Ne-ai dat deja permisiunea de a salva înregistrările tale. Iată un memento despre motivul pentru care avem nevoie:';

  @override
  String get wouldLikePermission => 'Am dori permisiunea ta de a salva înregistrările vocale. Iată de ce:';

  @override
  String get improveSpeechProfile => 'Îmbunătățește profilul tău vocal';

  @override
  String get improveSpeechProfileDesc =>
      'Folosim înregistrările pentru a antrena și îmbunătăți în continuare profilul tău vocal personal.';

  @override
  String get trainFamilyProfiles => 'Antrenează profiluri pentru prieteni și familie';

  @override
  String get trainFamilyProfilesDesc =>
      'Înregistrările tale ne ajută să recunoaștem și să creăm profiluri pentru prietenii și familia ta.';

  @override
  String get enhanceTranscriptAccuracy => 'Îmbunătățește acuratețea transcrierii';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'Pe măsură ce modelul nostru se îmbunătățește, putem oferi rezultate de transcriere mai bune pentru înregistrările tale.';

  @override
  String get legalNotice =>
      'Notificare legală: Legalitatea înregistrării și stocării datelor vocale poate varia în funcție de locația ta și modul în care folosești această funcție. Este responsabilitatea ta să te asiguri că respecți legile și reglementările locale.';

  @override
  String get alreadyAuthorized => 'Deja autorizat';

  @override
  String get authorize => 'Autorizează';

  @override
  String get revokeAuthorization => 'Revocă autorizarea';

  @override
  String get authorizationSuccessful => 'Autorizare reușită!';

  @override
  String get failedToAuthorize => 'Nu s-a putut autoriza. Te rugăm să încerci din nou.';

  @override
  String get authorizationRevoked => 'Autorizare revocată.';

  @override
  String get recordingsDeleted => 'Înregistrări șterse.';

  @override
  String get failedToRevoke => 'Nu s-a putut revoca autorizarea. Te rugăm să încerci din nou.';

  @override
  String get permissionRevokedTitle => 'Permisiune revocată';

  @override
  String get permissionRevokedMessage => 'Vrei să ștergem toate înregistrările tale existente?';

  @override
  String get yes => 'Da';

  @override
  String get editName => 'Editează numele';

  @override
  String get howShouldOmiCallYou => 'Cum ar trebui Omi să te numească?';

  @override
  String get enterYourName => 'Enter your name';

  @override
  String get nameCannotBeEmpty => 'Numele nu poate fi gol';

  @override
  String get nameUpdatedSuccessfully => 'Nume actualizat cu succes!';

  @override
  String get calendarSettings => 'Setări calendar';

  @override
  String get calendarProviders => 'Furnizori calendar';

  @override
  String get macOsCalendar => 'Calendar macOS';

  @override
  String get connectMacOsCalendar => 'Conectează calendarul tău local macOS';

  @override
  String get googleCalendar => 'Google Calendar';

  @override
  String get syncGoogleAccount => 'Sincronizează cu contul tău Google';

  @override
  String get showMeetingsMenuBar => 'Afișează întâlnirile viitoare în bara de meniu';

  @override
  String get showMeetingsMenuBarDesc =>
      'Afișează următoarea întâlnire și timpul rămas până începe în bara de meniu macOS';

  @override
  String get showEventsNoParticipants => 'Afișează evenimente fără participanți';

  @override
  String get showEventsNoParticipantsDesc =>
      'Când este activat, Coming Up afișează evenimente fără participanți sau link video.';

  @override
  String get yourMeetings => 'Întâlnirile tale';

  @override
  String get refresh => 'Reîmprospătează';

  @override
  String get noUpcomingMeetings => 'Nu s-au găsit întâlniri viitoare';

  @override
  String get checkingNextDays => 'Se verifică următoarele 30 de zile';

  @override
  String get tomorrow => 'Mâine';

  @override
  String get googleCalendarComingSoon => 'Integrarea Google Calendar va fi disponibilă în curând!';

  @override
  String connectedAsUser(String userId) {
    return 'Conectat ca utilizator: $userId';
  }

  @override
  String get defaultWorkspace => 'Spațiu de lucru implicit';

  @override
  String get tasksCreatedInWorkspace => 'Sarcinile vor fi create în acest spațiu de lucru';

  @override
  String get defaultProjectOptional => 'Proiect implicit (opțional)';

  @override
  String get leaveUnselectedTasks => 'Lasă neselectat pentru a crea sarcini fără proiect';

  @override
  String get noProjectsInWorkspace => 'Nu s-au găsit proiecte în acest spațiu de lucru';

  @override
  String get conversationTimeoutDesc =>
      'Alege cât timp să aștepți în tăcere înainte de a încheia automat o conversație:';

  @override
  String get timeout2Minutes => '2 minute';

  @override
  String get timeout2MinutesDesc => 'Încheie conversația după 2 minute de tăcere';

  @override
  String get timeout5Minutes => '5 minute';

  @override
  String get timeout5MinutesDesc => 'Încheie conversația după 5 minute de tăcere';

  @override
  String get timeout10Minutes => '10 minute';

  @override
  String get timeout10MinutesDesc => 'Încheie conversația după 10 minute de tăcere';

  @override
  String get timeout30Minutes => '30 de minute';

  @override
  String get timeout30MinutesDesc => 'Încheie conversația după 30 de minute de tăcere';

  @override
  String get timeout4Hours => '4 ore';

  @override
  String get timeout4HoursDesc => 'Încheie conversația după 4 ore de tăcere';

  @override
  String get conversationEndAfterHours => 'Conversațiile se vor încheia acum după 4 ore de tăcere';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Conversațiile se vor încheia acum după $minutes minut(e) de tăcere';
  }

  @override
  String get tellUsPrimaryLanguage => 'Spune-ne limba ta principală';

  @override
  String get languageForTranscription => 'Setează limba pentru transcrieri mai precise și o experiență personalizată.';

  @override
  String get singleLanguageModeInfo =>
      'Modul limbă unică este activat. Traducerea este dezactivată pentru o acuratețe mai mare.';

  @override
  String get searchLanguageHint => 'Search language by name or code';

  @override
  String get noLanguagesFound => 'No languages found';

  @override
  String get skip => 'Omite';

  @override
  String languageSetTo(String language) {
    return 'Limba setată la $language';
  }

  @override
  String get failedToSetLanguage => 'Nu s-a putut seta limba';

  @override
  String appSettings(String appName) {
    return 'Setări $appName';
  }

  @override
  String disconnectFromApp(String appName) {
    return 'Deconectezi de la $appName?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'Aceasta va elimina autentificarea ta $appName. Va trebui să te reconectezi pentru a o folosi din nou.';
  }

  @override
  String connectedToApp(String appName) {
    return 'Conectat la $appName';
  }

  @override
  String get account => 'Cont';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Sarcinile tale vor fi sincronizate cu contul tău $appName';
  }

  @override
  String get defaultSpace => 'Spațiu implicit';

  @override
  String get selectSpaceInWorkspace => 'Selectează un spațiu în spațiul tău de lucru';

  @override
  String get noSpacesInWorkspace => 'Nu s-au găsit spații în acest spațiu de lucru';

  @override
  String get defaultList => 'Listă implicită';

  @override
  String get tasksAddedToList => 'Sarcinile vor fi adăugate la această listă';

  @override
  String get noListsInSpace => 'Nu s-au găsit liste în acest spațiu';

  @override
  String failedToLoadRepos(String error) {
    return 'Nu s-au putut încărca repository-urile: $error';
  }

  @override
  String get defaultRepoSaved => 'Repository implicit salvat';

  @override
  String get failedToSaveDefaultRepo => 'Nu s-a putut salva repository-ul implicit';

  @override
  String get defaultRepository => 'Repository implicit';

  @override
  String get selectDefaultRepoDesc =>
      'Selectează un repository implicit pentru crearea de issue-uri. Poți specifica totuși un repository diferit când creezi issue-uri.';

  @override
  String get noReposFound => 'Nu s-au găsit repository-uri';

  @override
  String get private => 'Privat';

  @override
  String updatedDate(String date) {
    return 'Actualizat $date';
  }

  @override
  String get yesterday => 'ieri';

  @override
  String daysAgo(int count) {
    return 'acum $count zile';
  }

  @override
  String get oneWeekAgo => 'acum 1 săptămână';

  @override
  String weeksAgo(int count) {
    return 'acum $count săptămâni';
  }

  @override
  String get oneMonthAgo => 'acum 1 lună';

  @override
  String monthsAgo(int count) {
    return 'acum $count luni';
  }

  @override
  String get issuesCreatedInRepo => 'Issue-urile vor fi create în repository-ul tău implicit';

  @override
  String get taskIntegrations => 'Integrări sarcini';

  @override
  String get configureSettings => 'Configurează setările';

  @override
  String get completeAuthBrowser =>
      'Te rugăm să finalizezi autentificarea în browser. După ce ai terminat, revino la aplicație.';

  @override
  String failedToStartAppAuth(String appName) {
    return 'Nu s-a putut inițializa autentificarea $appName';
  }

  @override
  String connectToAppTitle(String appName) {
    return 'Conectează-te la $appName';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Va trebui să autorizezi Omi să creeze sarcini în contul tău $appName. Aceasta va deschide browser-ul pentru autentificare.';
  }

  @override
  String get continueButton => 'Continue';

  @override
  String appIntegration(String appName) {
    return 'Integrare $appName';
  }

  @override
  String integrationComingSoon(String appName) {
    return 'Integrarea cu $appName va fi disponibilă în curând! Lucrăm din greu pentru a-ți aduce mai multe opțiuni de gestionare a sarcinilor.';
  }

  @override
  String get gotIt => 'Got it';

  @override
  String get tasksExportedOneApp => 'Sarcinile pot fi exportate către o singură aplicație odată.';

  @override
  String get completeYourUpgrade => 'Finalizează upgrade-ul';

  @override
  String get importConfiguration => 'Importă configurația';

  @override
  String get exportConfiguration => 'Exportă configurația';

  @override
  String get bringYourOwn => 'Folosește propriul tău';

  @override
  String get payYourSttProvider => 'Folosește Omi liber. Plătești doar furnizorul STT direct.';

  @override
  String get freeMinutesMonth => '1.200 de minute gratuite/lună incluse. Nelimitat cu ';

  @override
  String get omiUnlimited => 'Omi Nelimitat';

  @override
  String get hostRequired => 'Host-ul este necesar';

  @override
  String get validPortRequired => 'Port valid este necesar';

  @override
  String get validWebsocketUrlRequired => 'URL WebSocket valid este necesar (wss://)';

  @override
  String get apiUrlRequired => 'URL API este necesar';

  @override
  String get apiKeyRequired => 'Cheia API este necesară';

  @override
  String get invalidJsonConfig => 'Configurație JSON invalidă';

  @override
  String errorSaving(String error) {
    return 'Eroare la salvare: $error';
  }

  @override
  String get configCopiedToClipboard => 'Configurație copiată în clipboard';

  @override
  String get pasteJsonConfig => 'Lipește configurația JSON mai jos:';

  @override
  String get addApiKeyAfterImport => 'Va trebui să adaugi propria cheie API după import';

  @override
  String get paste => 'Lipește';

  @override
  String get import => 'Importă';

  @override
  String get invalidProviderInConfig => 'Furnizor invalid în configurație';

  @override
  String importedConfig(String providerName) {
    return 'Configurație $providerName importată';
  }

  @override
  String invalidJson(String error) {
    return 'JSON invalid: $error';
  }

  @override
  String get provider => 'Furnizor';

  @override
  String get live => 'Live';

  @override
  String get onDevice => 'Pe dispozitiv';

  @override
  String get apiUrl => 'URL API';

  @override
  String get enterSttHttpEndpoint => 'Introdu endpoint-ul HTTP STT';

  @override
  String get websocketUrl => 'URL WebSocket';

  @override
  String get enterLiveSttWebsocket => 'Introdu endpoint-ul WebSocket STT live';

  @override
  String get apiKey => 'Cheie API';

  @override
  String get enterApiKey => 'Introdu cheia API';

  @override
  String get storedLocallyNeverShared => 'Stocat local, niciodată partajat';

  @override
  String get host => 'Host';

  @override
  String get port => 'Port';

  @override
  String get advanced => 'Avansat';

  @override
  String get configuration => 'Configurație';

  @override
  String get requestConfiguration => 'Configurație cerere';

  @override
  String get responseSchema => 'Schemă răspuns';

  @override
  String get modified => 'Modificat';

  @override
  String get resetRequestConfig => 'Resetează configurația cererii la implicit';

  @override
  String get logs => 'Jurnale';

  @override
  String get logsCopied => 'Jurnale copiate';

  @override
  String get noLogsYet =>
      'Încă nu există jurnale. Începe să înregistrezi pentru a vedea activitatea STT personalizată.';

  @override
  String deviceUsesCodec(String deviceName, String codecReason) {
    return '$deviceName folosește $codecReason. Omi va fi folosit.';
  }

  @override
  String get omiTranscription => 'Transcriere Omi';

  @override
  String get bestInClassTranscription => 'Cea mai bună transcriere din clasă fără configurare';

  @override
  String get instantSpeakerLabels => 'Etichete vorbitor instant';

  @override
  String get languageTranslation => 'Traducere în peste 100 de limbi';

  @override
  String get optimizedForConversation => 'Optimizat pentru conversație';

  @override
  String get autoLanguageDetection => 'Detectare automată a limbii';

  @override
  String get highAccuracy => 'Acuratețe ridicată';

  @override
  String get privacyFirst => 'Confidențialitate pe primul loc';

  @override
  String get saveChanges => 'Salvează modificările';

  @override
  String get resetToDefault => 'Resetează la implicit';

  @override
  String get viewTemplate => 'Vezi șablonul';

  @override
  String get trySomethingLike => 'Încearcă ceva precum...';

  @override
  String get tryIt => 'Încearcă';

  @override
  String get creatingPlan => 'Se creează planul';

  @override
  String get developingLogic => 'Se dezvoltă logica';

  @override
  String get designingApp => 'Se proiectează aplicația';

  @override
  String get generatingIconStep => 'Se generează iconița';

  @override
  String get finalTouches => 'Retușuri finale';

  @override
  String get processing => 'Se procesează...';

  @override
  String get features => 'Funcționalități';

  @override
  String get creatingYourApp => 'Se creează aplicația ta...';

  @override
  String get generatingIcon => 'Se generează iconița...';

  @override
  String get whatShouldWeMake => 'Ce ar trebui să facem?';

  @override
  String get appName => 'Nume aplicație';

  @override
  String get description => 'Descriere';

  @override
  String get publicLabel => 'Public';

  @override
  String get privateLabel => 'Privat';

  @override
  String get free => 'Gratuit';

  @override
  String get perMonth => '/ Lună';

  @override
  String get tailoredConversationSummaries => 'Rezumate de conversație personalizate';

  @override
  String get customChatbotPersonality => 'Personalitate chatbot personalizată';

  @override
  String get makePublic => 'Fă publică';

  @override
  String get anyoneCanDiscover => 'Oricine poate descoperi aplicația ta';

  @override
  String get onlyYouCanUse => 'Doar tu poți folosi această aplicație';

  @override
  String get paidApp => 'Aplicație plătită';

  @override
  String get usersPayToUse => 'Utilizatorii plătesc pentru a folosi aplicația ta';

  @override
  String get freeForEveryone => 'Gratuit pentru toată lumea';

  @override
  String get perMonthLabel => '/ lună';

  @override
  String get creating => 'Se creează...';

  @override
  String get createApp => 'Creează aplicație';

  @override
  String get searchingForDevices => 'Searching for devices...';

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
  String get pairingSuccessful => 'PAIRING SUCCESSFUL';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Error connecting to Apple Watch: $error';
  }

  @override
  String get dontShowAgain => 'Don\'t show it again';

  @override
  String get iUnderstand => 'I Understand';

  @override
  String get enableBluetooth => 'Enable Bluetooth';

  @override
  String get bluetoothNeeded =>
      'Omi needs Bluetooth to connect to your wearable. Please enable Bluetooth and try again.';

  @override
  String get contactSupport => 'Contact Support?';

  @override
  String get connectLater => 'Connect Later';

  @override
  String get grantPermissions => 'Grant permissions';

  @override
  String get backgroundActivity => 'Background activity';

  @override
  String get backgroundActivityDesc => 'Let Omi run in the background for better stability';

  @override
  String get locationAccess => 'Location access';

  @override
  String get locationAccessDesc => 'Enable background location for the full experience';

  @override
  String get notifications => 'Notifications';

  @override
  String get notificationsDesc => 'Enable notifications to stay informed';

  @override
  String get locationServiceDisabled => 'Location Service Disabled';

  @override
  String get locationServiceDisabledDesc =>
      'Location Service is Disabled. Please go to Settings > Privacy & Security > Location Services and enable it';

  @override
  String get backgroundLocationDenied => 'Background Location Access Denied';

  @override
  String get backgroundLocationDeniedDesc =>
      'Please go to device settings and set location permission to \"Always Allow\"';

  @override
  String get lovingOmi => 'Loving Omi?';

  @override
  String get leaveReviewIos =>
      'Help us reach more people by leaving a review in the App Store. Your feedback means the world to us!';

  @override
  String get leaveReviewAndroid =>
      'Help us reach more people by leaving a review in the Google Play Store. Your feedback means the world to us!';

  @override
  String get rateOnAppStore => 'Rate on App Store';

  @override
  String get rateOnGooglePlay => 'Rate on Google Play';

  @override
  String get maybeLater => 'Maybe later';

  @override
  String get speechProfileIntro => 'Omi needs to learn your goals and your voice. You\'ll be able to modify it later.';

  @override
  String get getStarted => 'Get Started';

  @override
  String get allDone => 'All done!';

  @override
  String get keepGoing => 'Keep going, you are doing great';

  @override
  String get skipThisQuestion => 'Skip this question';

  @override
  String get skipForNow => 'Skip for now';

  @override
  String get connectionError => 'Connection Error';

  @override
  String get connectionErrorDesc =>
      'Failed to connect to the server. Please check your internet connection and try again.';

  @override
  String get invalidRecordingMultipleSpeakers => 'Invalid recording detected';

  @override
  String get multipleSpeakersDesc =>
      'It seems like there are multiple speakers in the recording. Please make sure you are in a quiet location and try again.';

  @override
  String get tooShortDesc => 'There is not enough speech detected. Please speak more and try again.';

  @override
  String get invalidRecordingDesc => 'Please make sure you speak for at least 5 seconds and not more than 90.';

  @override
  String get areYouThere => 'Are you there?';

  @override
  String get noSpeechDesc =>
      'We could not detect any speech. Please make sure to speak for at least 10 seconds and not more than 3 minutes.';

  @override
  String get connectionLost => 'Connection Lost';

  @override
  String get connectionLostDesc =>
      'The connection was interrupted. Please check your internet connection and try again.';

  @override
  String get tryAgain => 'Try Again';

  @override
  String get connectOmiOmiGlass => 'Connect Omi / OmiGlass';

  @override
  String get continueWithoutDevice => 'Continue Without Device';

  @override
  String get permissionsRequired => 'Permissions Required';

  @override
  String get permissionsRequiredDesc =>
      'This app needs Bluetooth and Location permissions to function properly. Please enable them in the settings.';

  @override
  String get openSettings => 'Open Settings';

  @override
  String get wantDifferentName => 'Want to go by something else?';

  @override
  String get whatsYourName => 'What\'s your name?';

  @override
  String get speakTranscribeSummarize => 'Speak. Transcribe. Summarize.';

  @override
  String get signInWithApple => 'Sign in with Apple';

  @override
  String get signInWithGoogle => 'Sign in with Google';

  @override
  String get byContinuingAgree => 'By continuing, you agree to our ';

  @override
  String get termsOfUse => 'Terms of Use';

  @override
  String get omiYourAiCompanion => 'Omi – Your AI Companion';

  @override
  String get captureEveryMoment => 'Capture every moment. Get AI-powered\nsummaries. Never take notes again.';

  @override
  String get appleWatchSetup => 'Apple Watch Setup';

  @override
  String get permissionRequestedExclaim => 'Permission Requested!';

  @override
  String get microphonePermission => 'Microphone Permission';

  @override
  String get permissionGrantedNow =>
      'Permission granted! Now:\n\nOpen the Omi app on your watch and tap \"Continue\" below';

  @override
  String get needMicrophonePermission =>
      'We need microphone permission.\n\n1. Tap \"Grant Permission\"\n2. Allow on your iPhone\n3. Watch app will close\n4. Reopen and tap \"Continue\"';

  @override
  String get grantPermissionButton => 'Grant Permission';

  @override
  String get needHelp => 'Need Help?';

  @override
  String get troubleshootingSteps =>
      'Troubleshooting:\n\n1. Ensure Omi is installed on your watch\n2. Open the Omi app on your watch\n3. Look for the permission popup\n4. Tap \"Allow\" when prompted\n5. App on your watch will close - reopen it\n6. Come back and tap \"Continue\" on your iPhone';

  @override
  String get recordingStartedSuccessfully => 'Recording started successfully!';

  @override
  String get permissionNotGrantedYet =>
      'Permission not granted yet. Please make sure you allowed microphone access and reopened the app on your watch.';

  @override
  String errorRequestingPermission(String error) {
    return 'Error requesting permission: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'Error starting recording: $error';
  }

  @override
  String get selectPrimaryLanguage => 'Select your primary language';

  @override
  String get languageBenefits => 'Set your language for sharper transcriptions and a personalized experience';

  @override
  String get whatsYourPrimaryLanguage => 'What\'s your primary language?';

  @override
  String get selectYourLanguage => 'Select your language';

  @override
  String get personalGrowthJourney => 'Your personal growth journey with AI that listens to your every word.';

  @override
  String get actionItemsTitle => 'To-Do\'s';

  @override
  String get actionItemsDescription => 'Tap to edit • Long press to select • Swipe for actions';

  @override
  String get tabToDo => 'To Do';

  @override
  String get tabDone => 'Done';

  @override
  String get tabOld => 'Old';

  @override
  String get emptyTodoMessage => '🎉 All caught up!\nNo pending action items';

  @override
  String get emptyDoneMessage => 'No completed items yet';

  @override
  String get emptyOldMessage => '✅ No old tasks';

  @override
  String get noItems => 'No items';

  @override
  String get actionItemMarkedIncomplete => 'Action item marked as incomplete';

  @override
  String get actionItemCompleted => 'Action item completed';

  @override
  String get deleteActionItemTitle => 'Delete Action Item';

  @override
  String get deleteActionItemMessage => 'Are you sure you want to delete this action item?';

  @override
  String get deleteSelectedItemsTitle => 'Delete Selected Items';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Are you sure you want to delete $count selected action item$s?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'Action item \"$description\" deleted';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count action item$s deleted';
  }

  @override
  String get failedToDeleteItem => 'Failed to delete action item';

  @override
  String get failedToDeleteItems => 'Failed to delete items';

  @override
  String get failedToDeleteSomeItems => 'Failed to delete some items';

  @override
  String get welcomeActionItemsTitle => 'Ready for Action Items';

  @override
  String get welcomeActionItemsDescription =>
      'Your AI will automatically extract tasks and to-dos from your conversations. They\'ll appear here when created.';

  @override
  String get autoExtractionFeature => 'Automatically extracted from conversations';

  @override
  String get editSwipeFeature => 'Tap to edit, swipe to complete or delete';

  @override
  String itemsSelected(int count) {
    return '$count selected';
  }

  @override
  String get selectAll => 'Select all';

  @override
  String get deleteSelected => 'Delete selected';

  @override
  String searchMemories(int count) {
    return 'Search $count Memories';
  }

  @override
  String get memoryDeleted => 'Memory Deleted.';

  @override
  String get undo => 'Undo';

  @override
  String get noMemoriesYet => 'No memories yet';

  @override
  String get noAutoMemories => 'No auto-extracted memories yet';

  @override
  String get noManualMemories => 'No manual memories yet';

  @override
  String get noMemoriesInCategories => 'No memories in these categories';

  @override
  String get noMemoriesFound => 'No memories found';

  @override
  String get addFirstMemory => 'Add your first memory';

  @override
  String get clearMemoryTitle => 'Clear Omi\'s Memory';

  @override
  String get clearMemoryMessage => 'Are you sure you want to clear Omi\'s memory? This action cannot be undone.';

  @override
  String get clearMemoryButton => 'Clear Memory';

  @override
  String get memoryClearedSuccess => 'Omi\'s memory about you has been cleared';

  @override
  String get noMemoriesToDelete => 'No memories to delete';

  @override
  String get createMemoryTooltip => 'Create new memory';

  @override
  String get createActionItemTooltip => 'Create new action item';

  @override
  String get memoryManagement => 'Memory Management';

  @override
  String get filterMemories => 'Filter Memories';

  @override
  String totalMemoriesCount(int count) {
    return 'You have $count total memories';
  }

  @override
  String get publicMemories => 'Public memories';

  @override
  String get privateMemories => 'Private memories';

  @override
  String get makeAllPrivate => 'Make All Memories Private';

  @override
  String get makeAllPublic => 'Make All Memories Public';

  @override
  String get deleteAllMemories => 'Delete All Memories';

  @override
  String get allMemoriesPrivateResult => 'All memories are now private';

  @override
  String get allMemoriesPublicResult => 'All memories are now public';

  @override
  String get newMemory => 'New Memory';

  @override
  String get editMemory => 'Edit Memory';

  @override
  String get memoryContentHint => 'I like to eat ice cream...';

  @override
  String get failedToSaveMemory => 'Failed to save. Please check your connection.';

  @override
  String get saveMemory => 'Save Memory';

  @override
  String get retry => 'Retry';

  @override
  String get createActionItem => 'Create Action Item';

  @override
  String get editActionItem => 'Edit Action Item';

  @override
  String get actionItemDescriptionHint => 'What needs to be done?';

  @override
  String get actionItemDescriptionEmpty => 'Action item description cannot be empty.';

  @override
  String get actionItemUpdated => 'Action item updated';

  @override
  String get failedToUpdateActionItem => 'Failed to update action item';

  @override
  String get actionItemCreated => 'Action item created';

  @override
  String get failedToCreateActionItem => 'Failed to create action item';

  @override
  String get dueDate => 'Due Date';

  @override
  String get time => 'Time';

  @override
  String get addDueDate => 'Add due date';

  @override
  String get pressDoneToSave => 'Press done to save';

  @override
  String get pressDoneToCreate => 'Press done to create';

  @override
  String get filterAll => 'All';

  @override
  String get filterSystem => 'About You';

  @override
  String get filterInteresting => 'Insights';

  @override
  String get filterManual => 'Manual';

  @override
  String get completed => 'Completed';

  @override
  String get markComplete => 'Mark complete';

  @override
  String get actionItemDeleted => 'Action item deleted';

  @override
  String get failedToDeleteActionItem => 'Failed to delete action item';

  @override
  String get deleteActionItemConfirmTitle => 'Delete Action Item';

  @override
  String get deleteActionItemConfirmMessage => 'Are you sure you want to delete this action item?';

  @override
  String get appLanguage => 'App Language';

  @override
  String get appInterfaceSectionTitle => 'INTERFAȚĂ APLICAȚIE';

  @override
  String get speechTranscriptionSectionTitle => 'VORBIRE ȘI TRANSCRIERE';

  @override
  String get languageSettingsHelperText =>
      'Limba aplicației schimbă meniurile și butoanele. Limba vorbirii afectează modul în care sunt transcrise înregistrările.';
}
