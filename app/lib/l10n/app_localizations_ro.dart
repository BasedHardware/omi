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
  String get deleteConversationMessage => 'Ești sigur că vrei să ștergi această conversație? Această acțiune nu poate fi anulată.';

  @override
  String get confirm => 'Confirmă';

  @override
  String get cancel => 'Anulează';

  @override
  String get ok => 'Ok';

  @override
  String get delete => 'Șterge';

  @override
  String get add => 'Adaugă';

  @override
  String get update => 'Actualizați';

  @override
  String get save => 'Salvează';

  @override
  String get edit => 'Editează';

  @override
  String get close => 'Închide';

  @override
  String get clear => 'Curăță';

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
  String get errorProcessingConversation => 'Eroare la procesarea conversației. Te rugăm să încerci din nou mai târziu.';

  @override
  String get noInternetConnection => 'Fără conexiune la internet';

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
  String get speechProfile => 'Profil Vocal';

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
  String get pleaseCompleteAuthentication => 'Te rugăm să finalizezi autentificarea în browser. După ce ai terminat, revino la aplicație.';

  @override
  String get failedToStartAuthentication => 'Nu s-a putut inițializa autentificarea';

  @override
  String get importStarted => 'Import inițiat! Vei fi notificat când se finalizează.';

  @override
  String get failedToStartImport => 'Nu s-a putut inițializa importul. Te rugăm să încerci din nou.';

  @override
  String get couldNotAccessFile => 'Nu s-a putut accesa fișierul selectat';

  @override
  String get askOmi => 'Întreabă pe Omi';

  @override
  String get done => 'Gata';

  @override
  String get disconnected => 'Deconectat';

  @override
  String get searching => 'Se caută...';

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
  String get noConversationsYet => 'Încă nu există conversații';

  @override
  String get noStarredConversations => 'Nicio conversație cu stea';

  @override
  String get starConversationHint => 'Pentru a marca o conversație ca favorită, deschide-o și apasă iconița de stea din antet.';

  @override
  String get searchConversations => 'Căutare conversații...';

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
  String get deletingMessages => 'Ștergerea mesajelor din memoria Omi...';

  @override
  String get messageCopied => '✨ Mesaj copiat în clipboard';

  @override
  String get cannotReportOwnMessage => 'Nu poți raporta propriile mesaje.';

  @override
  String get reportMessage => 'Raportați mesajul';

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
  String get searchApps => 'Căutați aplicații...';

  @override
  String get myApps => 'Aplicațiile Mele';

  @override
  String get installedApps => 'Aplicații Instalate';

  @override
  String get unableToFetchApps => 'Nu s-au putut prelua aplicațiile :(\n\nTe rugăm să verifici conexiunea la internet și să încerci din nou.';

  @override
  String get aboutOmi => 'Despre Omi';

  @override
  String get privacyPolicy => 'Privacy Policy';

  @override
  String get visitWebsite => 'Vizitați site-ul web';

  @override
  String get helpOrInquiries => 'Ajutor sau întrebări?';

  @override
  String get joinCommunity => 'Alătură-te comunității!';

  @override
  String get membersAndCounting => '8000+ membri și numărul crește.';

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
  String get exportBeforeDelete => 'Poți exporta datele înainte de a-ți șterge contul, dar odată șters, nu poate fi recuperat.';

  @override
  String get deleteAccountCheckbox => 'Înțeleg că ștergerea contului meu este permanentă și toate datele, inclusiv amintirile și conversațiile, vor fi pierdute și nu pot fi recuperate.';

  @override
  String get areYouSure => 'Ești sigur?';

  @override
  String get deleteAccountFinal => 'Această acțiune este ireversibilă și va șterge permanent contul tău și toate datele asociate. Ești sigur că vrei să continui?';

  @override
  String get deleteNow => 'Șterge acum';

  @override
  String get goBack => 'Înapoi';

  @override
  String get checkBoxToConfirm => 'Bifează caseta pentru a confirma că înțelegi că ștergerea contului este permanentă și ireversibilă.';

  @override
  String get profile => 'Profil';

  @override
  String get name => 'Nume';

  @override
  String get email => 'E-mail';

  @override
  String get customVocabulary => 'Vocabular Personalizat';

  @override
  String get identifyingOthers => 'Identificarea Altora';

  @override
  String get paymentMethods => 'Metode de Plată';

  @override
  String get conversationDisplay => 'Afișare Conversații';

  @override
  String get dataPrivacy => 'Confidențialitatea Datelor';

  @override
  String get userId => 'ID Utilizator';

  @override
  String get notSet => 'Nu este setat';

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
  String get privacyIntro => 'La Omi, ne angajăm să îți protejăm confidențialitatea. Această pagină îți permite să controlezi modul în care datele tale sunt stocate și utilizate.';

  @override
  String get learnMore => 'Află mai multe...';

  @override
  String get dataProtectionLevel => 'Nivel de protecție a datelor';

  @override
  String get dataProtectionDesc => 'Datele tale sunt securizate implicit cu criptare puternică. Revizuiește setările și opțiunile viitoare de confidențialitate mai jos.';

  @override
  String get appAccess => 'Acces aplicații';

  @override
  String get appAccessDesc => 'Următoarele aplicații pot accesa datele tale. Apasă pe o aplicație pentru a-i gestiona permisiunile.';

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
  String get chargingIssues => 'Probleme de încărcare';

  @override
  String get disconnectDevice => 'Deconectează dispozitivul';

  @override
  String get unpairDevice => 'Deconectează dispozitivul';

  @override
  String get unpairAndForget => 'Deperechează și uită dispozitivul';

  @override
  String get deviceDisconnectedMessage => 'Omi-ul tău a fost deconectat 😔';

  @override
  String get deviceUnpairedMessage => 'Dispozitiv deconectat. Mergeți la Setări > Bluetooth și uitați dispozitivul pentru a finaliza deconectarea.';

  @override
  String get unpairDialogTitle => 'Deperechează dispozitivul';

  @override
  String get unpairDialogMessage => 'Acest lucru va deperechia dispozitivul astfel încât să poată fi conectat la alt telefon. Va trebui să mergi la Setări > Bluetooth și să uiți dispozitivul pentru a finaliza procesul.';

  @override
  String get deviceNotConnected => 'Dispozitiv neconectat';

  @override
  String get connectDeviceMessage => 'Conectează dispozitivul Omi pentru a accesa\nsetările și personalizarea dispozitivului';

  @override
  String get deviceInfoSection => 'Informații dispozitiv';

  @override
  String get customizationSection => 'Personalizare';

  @override
  String get hardwareSection => 'Hardware';

  @override
  String get v2Undetected => 'V2 nedetectat';

  @override
  String get v2UndetectedMessage => 'Vedem că ai fie un dispozitiv V1, fie dispozitivul tău nu este conectat. Funcționalitatea card SD este disponibilă doar pentru dispozitivele V2.';

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
  String get endpointUrl => 'URL punct final';

  @override
  String get noApiKeys => 'Încă nu există chei API';

  @override
  String get createKeyToStart => 'Creează o cheie pentru a începe';

  @override
  String get createKey => 'Creează Cheie';

  @override
  String get docs => 'Documentație';

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
  String get startConversationToSeeInsights => 'Începe o conversație cu Omi\npentru a vedea statisticile de utilizare aici.';

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
  String get upgradeToUnlimited => 'Actualizează la nelimitat';

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
  String get noLogFilesFound => 'Niciun fișier jurnal găsit.';

  @override
  String get omiDebugLog => 'Jurnal de depanare Omi';

  @override
  String get logShared => 'Jurnal partajat';

  @override
  String get selectLogFile => 'Selectează fișier jurnal';

  @override
  String get shareLogs => 'Distribuiți jurnalele';

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
  String get deleteKnowledgeGraphMessage => 'Acest lucru va șterge toate datele derivate din graficul de cunoștințe (noduri și conexiuni). Amintirile tale originale vor rămâne în siguranță. Graficul va fi reconstruit în timp sau la următoarea solicitare.';

  @override
  String get knowledgeGraphDeleted => 'Graficul de cunoștințe a fost șters';

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
  String get shortConversationThresholdSubtitle => 'Conversațiile mai scurte decât aceasta vor fi ascunse dacă nu este activată opțiunea de mai sus';

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
  String get completeAuthInBrowser => 'Te rugăm să finalizezi autentificarea în browser. După ce ai terminat, revino la aplicație.';

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
  String get primaryLanguage => 'Limba principală';

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
  String get alreadyGavePermission => 'Ne-ai dat deja permisiunea de a salva înregistrările tale. Iată un memento despre motivul pentru care avem nevoie:';

  @override
  String get wouldLikePermission => 'Am dori permisiunea ta de a salva înregistrările vocale. Iată de ce:';

  @override
  String get improveSpeechProfile => 'Îmbunătățește profilul tău vocal';

  @override
  String get improveSpeechProfileDesc => 'Folosim înregistrările pentru a antrena și îmbunătăți în continuare profilul tău vocal personal.';

  @override
  String get trainFamilyProfiles => 'Antrenează profiluri pentru prieteni și familie';

  @override
  String get trainFamilyProfilesDesc => 'Înregistrările tale ne ajută să recunoaștem și să creăm profiluri pentru prietenii și familia ta.';

  @override
  String get enhanceTranscriptAccuracy => 'Îmbunătățește acuratețea transcrierii';

  @override
  String get enhanceTranscriptAccuracyDesc => 'Pe măsură ce modelul nostru se îmbunătățește, putem oferi rezultate de transcriere mai bune pentru înregistrările tale.';

  @override
  String get legalNotice => 'Notificare legală: Legalitatea înregistrării și stocării datelor vocale poate varia în funcție de locația ta și modul în care folosești această funcție. Este responsabilitatea ta să te asiguri că respecți legile și reglementările locale.';

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
  String get enterYourName => 'Introduceți numele dvs.';

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
  String get showMeetingsMenuBarDesc => 'Afișează următoarea întâlnire și timpul rămas până începe în bara de meniu macOS';

  @override
  String get showEventsNoParticipants => 'Afișează evenimente fără participanți';

  @override
  String get showEventsNoParticipantsDesc => 'Când este activat, Coming Up afișează evenimente fără participanți sau link video.';

  @override
  String get yourMeetings => 'Întâlnirile tale';

  @override
  String get refresh => 'Actualizează';

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
  String get conversationTimeoutDesc => 'Alege cât timp să aștepți în tăcere înainte de a încheia automat o conversație:';

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
  String get singleLanguageModeInfo => 'Modul limbă unică este activat. Traducerea este dezactivată pentru o acuratețe mai mare.';

  @override
  String get searchLanguageHint => 'Search language by name or code';

  @override
  String get noLanguagesFound => 'Nu s-au găsit limbi';

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
  String get selectDefaultRepoDesc => 'Selectează un repository implicit pentru crearea de issue-uri. Poți specifica totuși un repository diferit când creezi issue-uri.';

  @override
  String get noReposFound => 'Nu s-au găsit repository-uri';

  @override
  String get private => 'Privat';

  @override
  String updatedDate(String date) {
    return 'Actualizat $date';
  }

  @override
  String get yesterday => 'Ieri';

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
  String get completeAuthBrowser => 'Te rugăm să finalizezi autentificarea în browser. După ce ai terminat, revino la aplicație.';

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
  String get continueButton => 'Continuați';

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
  String get noLogsYet => 'Încă nu există jurnale. Începe să înregistrezi pentru a vedea activitatea STT personalizată.';

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
  String get makePublic => 'Fă public';

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
  String get createApp => 'Creează Aplicație';

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
  String get dontShowAgain => 'Nu mai afișa';

  @override
  String get iUnderstand => 'I Understand';

  @override
  String get enableBluetooth => 'Enable Bluetooth';

  @override
  String get bluetoothNeeded => 'Omi needs Bluetooth to connect to your wearable. Please enable Bluetooth and try again.';

  @override
  String get contactSupport => 'Contact Support?';

  @override
  String get connectLater => 'Connect Later';

  @override
  String get grantPermissions => 'Acordați permisiuni';

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
  String get locationServiceDisabledDesc => 'Location Service is Disabled. Please go to Settings > Privacy & Security > Location Services and enable it';

  @override
  String get backgroundLocationDenied => 'Background Location Access Denied';

  @override
  String get backgroundLocationDeniedDesc => 'Please go to device settings and set location permission to \"Always Allow\"';

  @override
  String get lovingOmi => 'Loving Omi?';

  @override
  String get leaveReviewIos => 'Help us reach more people by leaving a review in the App Store. Your feedback means the world to us!';

  @override
  String get leaveReviewAndroid => 'Help us reach more people by leaving a review in the Google Play Store. Your feedback means the world to us!';

  @override
  String get rateOnAppStore => 'Rate on App Store';

  @override
  String get rateOnGooglePlay => 'Rate on Google Play';

  @override
  String get maybeLater => 'Poate Mai Târziu';

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
  String get connectionErrorDesc => 'Failed to connect to the server. Please check your internet connection and try again.';

  @override
  String get invalidRecordingMultipleSpeakers => 'Invalid recording detected';

  @override
  String get multipleSpeakersDesc => 'It seems like there are multiple speakers in the recording. Please make sure you are in a quiet location and try again.';

  @override
  String get tooShortDesc => 'There is not enough speech detected. Please speak more and try again.';

  @override
  String get invalidRecordingDesc => 'Please make sure you speak for at least 5 seconds and not more than 90.';

  @override
  String get areYouThere => 'Are you there?';

  @override
  String get noSpeechDesc => 'We could not detect any speech. Please make sure to speak for at least 10 seconds and not more than 3 minutes.';

  @override
  String get connectionLost => 'Connection Lost';

  @override
  String get connectionLostDesc => 'The connection was interrupted. Please check your internet connection and try again.';

  @override
  String get tryAgain => 'Try Again';

  @override
  String get connectOmiOmiGlass => 'Connect Omi / OmiGlass';

  @override
  String get continueWithoutDevice => 'Continue Without Device';

  @override
  String get permissionsRequired => 'Permissions Required';

  @override
  String get permissionsRequiredDesc => 'This app needs Bluetooth and Location permissions to function properly. Please enable them in the settings.';

  @override
  String get openSettings => 'Open Settings';

  @override
  String get wantDifferentName => 'Want to go by something else?';

  @override
  String get whatsYourName => 'Cum te cheamă?';

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
  String get permissionGrantedNow => 'Permission granted! Now:\n\nOpen the Omi app on your watch and tap \"Continue\" below';

  @override
  String get needMicrophonePermission => 'We need microphone permission.\n\n1. Tap \"Grant Permission\"\n2. Allow on your iPhone\n3. Watch app will close\n4. Reopen and tap \"Continue\"';

  @override
  String get grantPermissionButton => 'Grant Permission';

  @override
  String get needHelp => 'Need Help?';

  @override
  String get troubleshootingSteps => 'Troubleshooting:\n\n1. Ensure Omi is installed on your watch\n2. Open the Omi app on your watch\n3. Look for the permission popup\n4. Tap \"Allow\" when prompted\n5. App on your watch will close - reopen it\n6. Come back and tap \"Continue\" on your iPhone';

  @override
  String get recordingStartedSuccessfully => 'Recording started successfully!';

  @override
  String get permissionNotGrantedYet => 'Permission not granted yet. Please make sure you allowed microphone access and reopened the app on your watch.';

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
  String get personalGrowthJourney => 'Călătoria ta de creștere personală cu AI care ascultă fiecare cuvânt al tău.';

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
  String get deleteActionItemTitle => 'Șterge elementul de acțiune';

  @override
  String get deleteActionItemMessage => 'Sunteți sigur că doriți să ștergeți acest element de acțiune?';

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
  String get welcomeActionItemsDescription => 'Your AI will automatically extract tasks and to-dos from your conversations. They\'ll appear here when created.';

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
  String get searchMemories => 'Caută amintiri...';

  @override
  String get memoryDeleted => 'Memory Deleted.';

  @override
  String get undo => 'Undo';

  @override
  String get noMemoriesYet => '🧠 Încă nu există amintiri';

  @override
  String get noAutoMemories => 'No auto-extracted memories yet';

  @override
  String get noManualMemories => 'No manual memories yet';

  @override
  String get noMemoriesInCategories => 'No memories in these categories';

  @override
  String get noMemoriesFound => '🔍 Nu s-au găsit amintiri';

  @override
  String get addFirstMemory => 'Add your first memory';

  @override
  String get clearMemoryTitle => 'Clear Omi\'s Memory';

  @override
  String get clearMemoryMessage => 'Are you sure you want to clear Omi\'s memory? This action cannot be undone.';

  @override
  String get clearMemoryButton => 'Șterge memoria';

  @override
  String get memoryClearedSuccess => 'Omi\'s memory about you has been cleared';

  @override
  String get noMemoriesToDelete => 'Nu există amintiri de șters';

  @override
  String get createMemoryTooltip => 'Create new memory';

  @override
  String get createActionItemTooltip => 'Create new action item';

  @override
  String get memoryManagement => 'Gestionare memorie';

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
  String get deleteAllMemories => 'Șterge toate amintirile';

  @override
  String get allMemoriesPrivateResult => 'All memories are now private';

  @override
  String get allMemoriesPublicResult => 'All memories are now public';

  @override
  String get newMemory => '✨ Amintire nouă';

  @override
  String get editMemory => '✏️ Editează amintirea';

  @override
  String get memoryContentHint => 'I like to eat ice cream...';

  @override
  String get failedToSaveMemory => 'Failed to save. Please check your connection.';

  @override
  String get saveMemory => 'Save Memory';

  @override
  String get retry => 'Reîncearcă';

  @override
  String get createActionItem => 'Creează element de acțiune';

  @override
  String get editActionItem => 'Editează elementul de acțiune';

  @override
  String get actionItemDescriptionHint => 'What needs to be done?';

  @override
  String get actionItemDescriptionEmpty => 'Action item description cannot be empty.';

  @override
  String get actionItemUpdated => 'Action item updated';

  @override
  String get failedToUpdateActionItem => 'Actualizarea elementului de acțiune a eșuat';

  @override
  String get actionItemCreated => 'Action item created';

  @override
  String get failedToCreateActionItem => 'Crearea elementului de acțiune a eșuat';

  @override
  String get dueDate => 'Data scadentă';

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
  String get completed => 'Finalizat';

  @override
  String get markComplete => 'Marchează ca finalizat';

  @override
  String get actionItemDeleted => 'Element de acțiune șters';

  @override
  String get failedToDeleteActionItem => 'Ștergerea elementului de acțiune a eșuat';

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
  String get languageSettingsHelperText => 'Limba aplicației schimbă meniurile și butoanele. Limba vorbirii afectează modul în care sunt transcrise înregistrările.';

  @override
  String get translationNotice => 'Notificare de traducere';

  @override
  String get translationNoticeMessage => 'Omi traduce conversațiile în limba ta principală. Actualizează-o oricând în Setări → Profiluri.';

  @override
  String get pleaseCheckInternetConnection => 'Verifică conexiunea la internet și încearcă din nou';

  @override
  String get pleaseSelectReason => 'Te rugăm să selectezi un motiv';

  @override
  String get tellUsMoreWhatWentWrong => 'Spune-ne mai multe despre ce nu a mers bine...';

  @override
  String get selectText => 'Selectează text';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Maxim $count obiective permise';
  }

  @override
  String get conversationCannotBeMerged => 'Această conversație nu poate fi fuzionată (blocată sau deja în curs de fuzionare)';

  @override
  String get pleaseEnterFolderName => 'Te rugăm să introduci un nume de dosar';

  @override
  String get failedToCreateFolder => 'Nu s-a putut crea dosarul';

  @override
  String get failedToUpdateFolder => 'Nu s-a putut actualiza dosarul';

  @override
  String get folderName => 'Nume dosar';

  @override
  String get descriptionOptional => 'Descriere (opțional)';

  @override
  String get failedToDeleteFolder => 'Nu s-a putut șterge dosarul';

  @override
  String get editFolder => 'Editează dosarul';

  @override
  String get deleteFolder => 'Șterge dosarul';

  @override
  String get transcriptCopiedToClipboard => 'Transcrierea a fost copiată în clipboard';

  @override
  String get summaryCopiedToClipboard => 'Rezumat copiat în clipboard';

  @override
  String get conversationUrlCouldNotBeShared => 'URL-ul conversației nu a putut fi partajat.';

  @override
  String get urlCopiedToClipboard => 'URL copiat în clipboard';

  @override
  String get exportTranscript => 'Exportă transcrierea';

  @override
  String get exportSummary => 'Exportă rezumatul';

  @override
  String get exportButton => 'Exportă';

  @override
  String get actionItemsCopiedToClipboard => 'Elementele de acțiune au fost copiate în clipboard';

  @override
  String get summarize => 'Rezumă';

  @override
  String get generateSummary => 'Generare rezumat';

  @override
  String get conversationNotFoundOrDeleted => 'Conversația nu a fost găsită sau a fost ștearsă';

  @override
  String get deleteMemory => 'Șterge amintirea';

  @override
  String get thisActionCannotBeUndone => 'Această acțiune nu poate fi anulată.';

  @override
  String memoriesCount(int count) {
    return '$count amintiri';
  }

  @override
  String get noMemoriesInCategory => 'Nu există încă amintiri în această categorie';

  @override
  String get addYourFirstMemory => 'Adaugă prima ta amintire';

  @override
  String get firmwareDisconnectUsb => 'Deconectați USB';

  @override
  String get firmwareUsbWarning => 'Conexiunea USB în timpul actualizărilor poate deteriora dispozitivul.';

  @override
  String get firmwareBatteryAbove15 => 'Baterie peste 15%';

  @override
  String get firmwareEnsureBattery => 'Asigurați-vă că dispozitivul are 15% baterie.';

  @override
  String get firmwareStableConnection => 'Conexiune stabilă';

  @override
  String get firmwareConnectWifi => 'Conectați-vă la WiFi sau date mobile.';

  @override
  String failedToStartUpdate(String error) {
    return 'Eșec la pornirea actualizării: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'Înainte de actualizare, asigurați-vă:';

  @override
  String get confirmed => 'Confirmat!';

  @override
  String get release => 'Eliberați';

  @override
  String get slideToUpdate => 'Glisați pentru a actualiza';

  @override
  String copiedToClipboard(String title) {
    return '$title copiat în clipboard';
  }

  @override
  String get batteryLevel => 'Nivel baterie';

  @override
  String get productUpdate => 'Actualizare produs';

  @override
  String get offline => 'Offline';

  @override
  String get available => 'Disponibil';

  @override
  String get unpairDeviceDialogTitle => 'Deconectează dispozitivul';

  @override
  String get unpairDeviceDialogMessage => 'Aceasta va deconecta dispozitivul astfel încât să poată fi conectat la un alt telefon. Va trebui să mergeți la Setări > Bluetooth și să uitați dispozitivul pentru a finaliza procesul.';

  @override
  String get unpair => 'Deconectează';

  @override
  String get unpairAndForgetDevice => 'Deconectează și uită dispozitivul';

  @override
  String get unknownDevice => 'Dispozitiv necunoscut';

  @override
  String get unknown => 'Necunoscut';

  @override
  String get productName => 'Nume produs';

  @override
  String get serialNumber => 'Număr de serie';

  @override
  String get connected => 'Conectat';

  @override
  String get privacyPolicyTitle => 'Politica de confidențialitate';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label copied';
  }

  @override
  String get noApiKeysYet => 'Încă nu există chei API. Creează una pentru a integra cu aplicația ta.';

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
  String get debugAndDiagnostics => 'Depanare și diagnostice';

  @override
  String get autoDeletesAfter3Days => 'Ștergere automată după 3 zile';

  @override
  String get helpsDiagnoseIssues => 'Ajută la diagnosticarea problemelor';

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
  String get realTimeTranscript => 'Transcriere în timp real';

  @override
  String get experimental => 'Experimental';

  @override
  String get transcriptionDiagnostics => 'Diagnostice de transcriere';

  @override
  String get detailedDiagnosticMessages => 'Mesaje de diagnostic detaliate';

  @override
  String get autoCreateSpeakers => 'Creați automat vorbitori';

  @override
  String get autoCreateWhenNameDetected => 'Auto-create when name detected';

  @override
  String get followUpQuestions => 'Întrebări de urmărire';

  @override
  String get suggestQuestionsAfterConversations => 'Sugerați întrebări după conversații';

  @override
  String get goalTracker => 'Urmăritor de obiective';

  @override
  String get trackPersonalGoalsOnHomepage => 'Track your personal goals on homepage';

  @override
  String get dailyReflection => 'Reflecție zilnică';

  @override
  String get get9PmReminderToReflect => 'Get a 9 PM reminder to reflect on your day';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'Descrierea elementului de acțiune nu poate fi goală';

  @override
  String get saved => 'Salvat';

  @override
  String get overdue => 'Întârziat';

  @override
  String get failedToUpdateDueDate => 'Actualizarea datei scadente a eșuat';

  @override
  String get markIncomplete => 'Marchează ca nefinalizat';

  @override
  String get editDueDate => 'Editează data scadentă';

  @override
  String get setDueDate => 'Setați data scadentă';

  @override
  String get clearDueDate => 'Șterge data scadentă';

  @override
  String get failedToClearDueDate => 'Ștergerea datei scadente a eșuat';

  @override
  String get mondayAbbr => 'Lun';

  @override
  String get tuesdayAbbr => 'Mar';

  @override
  String get wednesdayAbbr => 'Mie';

  @override
  String get thursdayAbbr => 'Joi';

  @override
  String get fridayAbbr => 'Vin';

  @override
  String get saturdayAbbr => 'Sâm';

  @override
  String get sundayAbbr => 'Dum';

  @override
  String get howDoesItWork => 'Cum funcționează?';

  @override
  String get sdCardSyncDescription => 'Sincronizarea cardului SD va importa amintirile tale de pe cardul SD în aplicație';

  @override
  String get checksForAudioFiles => 'Verifică fișierele audio de pe cardul SD';

  @override
  String get omiSyncsAudioFiles => 'Omi apoi sincronizează fișierele audio cu serverul';

  @override
  String get serverProcessesAudio => 'Serverul procesează fișierele audio și creează amintiri';

  @override
  String get youreAllSet => 'Sunteți gata!';

  @override
  String get welcomeToOmiDescription => 'Bun venit la Omi! Companionul tău AI este gata să te ajute cu conversații, sarcini și multe altele.';

  @override
  String get startUsingOmi => 'Începeți să folosiți Omi';

  @override
  String get back => 'Înapoi';

  @override
  String get keyboardShortcuts => 'Comenzi Rapide';

  @override
  String get toggleControlBar => 'Comută bara de control';

  @override
  String get pressKeys => 'Apasă tastele...';

  @override
  String get cmdRequired => '⌘ necesar';

  @override
  String get invalidKey => 'Tastă invalidă';

  @override
  String get space => 'Spațiu';

  @override
  String get search => 'Căutare';

  @override
  String get searchPlaceholder => 'Căutare...';

  @override
  String get untitledConversation => 'Conversație fără titlu';

  @override
  String countRemaining(String count) {
    return '$count rămase';
  }

  @override
  String get addGoal => 'Adaugă obiectiv';

  @override
  String get editGoal => 'Editează obiectiv';

  @override
  String get icon => 'Pictogramă';

  @override
  String get goalTitle => 'Titlu obiectiv';

  @override
  String get current => 'Curent';

  @override
  String get target => 'Obiectiv';

  @override
  String get saveGoal => 'Salvează';

  @override
  String get goals => 'Obiective';

  @override
  String get tapToAddGoal => 'Atingeți pentru a adăuga un obiectiv';

  @override
  String welcomeBack(String name) {
    return 'Bine ai revenit, $name';
  }

  @override
  String get yourConversations => 'Conversațiile tale';

  @override
  String get reviewAndManageConversations => 'Revizuiește și gestionează conversațiile înregistrate';

  @override
  String get startCapturingConversations => 'Începe să capturezi conversații cu dispozitivul Omi pentru a le vedea aici.';

  @override
  String get useMobileAppToCapture => 'Folosește aplicația mobilă pentru a captura audio';

  @override
  String get conversationsProcessedAutomatically => 'Conversațiile sunt procesate automat';

  @override
  String get getInsightsInstantly => 'Obține informații și rezumate instantaneu';

  @override
  String get showAll => 'Arată tot →';

  @override
  String get noTasksForToday => 'Nicio sarcină pentru astăzi.\\nÎntrebați Omi pentru mai multe sarcini sau creați manual.';

  @override
  String get dailyScore => 'SCOR ZILNIC';

  @override
  String get dailyScoreDescription => 'Un scor pentru a vă ajuta să vă concentrați mai bine asupra execuției.';

  @override
  String get searchResults => 'Rezultate căutare';

  @override
  String get actionItems => 'Elemente de acțiune';

  @override
  String get tasksToday => 'Azi';

  @override
  String get tasksTomorrow => 'Mâine';

  @override
  String get tasksNoDeadline => 'Fără termen limită';

  @override
  String get tasksLater => 'Mai târziu';

  @override
  String get loadingTasks => 'Se încarcă sarcinile...';

  @override
  String get tasks => 'Sarcini';

  @override
  String get swipeTasksToIndent => 'Glisați sarcinile pentru a indenta, trageți între categorii';

  @override
  String get create => 'Creați';

  @override
  String get noTasksYet => 'Încă nu există sarcini';

  @override
  String get tasksFromConversationsWillAppear => 'Sarcinile din conversațiile dvs. vor apărea aici.\nFaceți clic pe Creați pentru a adăuga una manual.';

  @override
  String get monthJan => 'Ian';

  @override
  String get monthFeb => 'Feb';

  @override
  String get monthMar => 'Mar';

  @override
  String get monthApr => 'Apr';

  @override
  String get monthMay => 'Mai';

  @override
  String get monthJun => 'Iun';

  @override
  String get monthJul => 'Iul';

  @override
  String get monthAug => 'Aug';

  @override
  String get monthSep => 'Sep';

  @override
  String get monthOct => 'Oct';

  @override
  String get monthNov => 'Noie';

  @override
  String get monthDec => 'Dec';

  @override
  String get timePM => 'PM';

  @override
  String get timeAM => 'AM';

  @override
  String get actionItemUpdatedSuccessfully => 'Elementul de acțiune a fost actualizat cu succes';

  @override
  String get actionItemCreatedSuccessfully => 'Elementul de acțiune a fost creat cu succes';

  @override
  String get actionItemDeletedSuccessfully => 'Elementul de acțiune a fost șters cu succes';

  @override
  String get deleteActionItem => 'Șterge elementul de acțiune';

  @override
  String get deleteActionItemConfirmation => 'Sigur doriți să ștergeți acest element de acțiune? Această acțiune nu poate fi anulată.';

  @override
  String get enterActionItemDescription => 'Introduceți descrierea elementului de acțiune...';

  @override
  String get markAsCompleted => 'Marcați ca finalizat';

  @override
  String get setDueDateAndTime => 'Setați data și ora scadentă';

  @override
  String get reloadingApps => 'Reîncărcare aplicații...';

  @override
  String get loadingApps => 'Încărcare aplicații...';

  @override
  String get browseInstallCreateApps => 'Răsfoiți, instalați și creați aplicații';

  @override
  String get all => 'Toate';

  @override
  String get open => 'Deschide';

  @override
  String get install => 'Instalează';

  @override
  String get noAppsAvailable => 'Nicio aplicație disponibilă';

  @override
  String get unableToLoadApps => 'Nu se pot încărca aplicațiile';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'Încercați să ajustați termenii de căutare sau filtrele';

  @override
  String get checkBackLaterForNewApps => 'Reveniți mai târziu pentru aplicații noi';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'Vă rugăm să verificați conexiunea la internet și să încercați din nou';

  @override
  String get createNewApp => 'Creează Aplicație Nouă';

  @override
  String get buildSubmitCustomOmiApp => 'Construiește și trimite aplicația ta Omi personalizată';

  @override
  String get submittingYourApp => 'Se trimite aplicația ta...';

  @override
  String get preparingFormForYou => 'Se pregătește formularul pentru tine...';

  @override
  String get appDetails => 'Detalii Aplicație';

  @override
  String get paymentDetails => 'Detalii Plată';

  @override
  String get previewAndScreenshots => 'Previzualizare și Capturi de Ecran';

  @override
  String get appCapabilities => 'Capacități Aplicație';

  @override
  String get aiPrompts => 'Solicitări AI';

  @override
  String get chatPrompt => 'Solicitare Chat';

  @override
  String get chatPromptPlaceholder => 'Ești o aplicație grozavă, treaba ta este să răspunzi la întrebările utilizatorilor și să-i faci să se simtă bine...';

  @override
  String get conversationPrompt => 'Prompt de conversație';

  @override
  String get conversationPromptPlaceholder => 'Ești o aplicație grozavă, vei primi o transcriere și un rezumat al unei conversații...';

  @override
  String get notificationScopes => 'Domenii de Notificare';

  @override
  String get appPrivacyAndTerms => 'Confidențialitate și Termeni Aplicație';

  @override
  String get makeMyAppPublic => 'Fă aplicația mea publică';

  @override
  String get submitAppTermsAgreement => 'Prin trimiterea acestei aplicații, sunt de acord cu Termenii de Serviciu și Politica de Confidențialitate Omi AI';

  @override
  String get submitApp => 'Trimite Aplicația';

  @override
  String get needHelpGettingStarted => 'Ai nevoie de ajutor pentru a începe?';

  @override
  String get clickHereForAppBuildingGuides => 'Dă clic aici pentru ghiduri de creare aplicații și documentație';

  @override
  String get submitAppQuestion => 'Trimite Aplicația?';

  @override
  String get submitAppPublicDescription => 'Aplicația ta va fi revizuită și făcută publică. Poți începe să o folosești imediat, chiar și în timpul reviziei!';

  @override
  String get submitAppPrivateDescription => 'Aplicația ta va fi revizuită și pusă la dispoziția ta în mod privat. Poți începe să o folosești imediat, chiar și în timpul reviziei!';

  @override
  String get startEarning => 'Începe să Câștigi! 💰';

  @override
  String get connectStripeOrPayPal => 'Conectează Stripe sau PayPal pentru a primi plăți pentru aplicația ta.';

  @override
  String get connectNow => 'Conectează Acum';

  @override
  String installsCount(String count) {
    return '$count+ instalări';
  }

  @override
  String get uninstallApp => 'Dezinstalează aplicația';

  @override
  String get subscribe => 'Abonează-te';

  @override
  String get dataAccessNotice => 'Notificare acces la date';

  @override
  String get dataAccessWarning => 'Această aplicație va accesa datele dvs. Omi AI nu este responsabil pentru modul în care datele dvs. sunt utilizate, modificate sau șterse de această aplicație';

  @override
  String get installApp => 'Instalează aplicația';

  @override
  String get betaTesterNotice => 'Ești tester beta pentru această aplicație. Nu este încă publică. Va fi publică odată ce va fi aprobată.';

  @override
  String get appUnderReviewOwner => 'Aplicația ta este în curs de revizuire și vizibilă doar pentru tine. Va fi publică odată ce va fi aprobată.';

  @override
  String get appRejectedNotice => 'Aplicația ta a fost respinsă. Te rugăm să actualizezi detaliile aplicației și să o trimiți din nou pentru revizuire.';

  @override
  String get setupSteps => 'Pași de configurare';

  @override
  String get setupInstructions => 'Instrucțiuni de configurare';

  @override
  String get integrationInstructions => 'Instrucțiuni de integrare';

  @override
  String get preview => 'Previzualizare';

  @override
  String get aboutTheApp => 'Despre aplicație';

  @override
  String get aboutThePersona => 'Despre persoană';

  @override
  String get chatPersonality => 'Personalitatea chat-ului';

  @override
  String get ratingsAndReviews => 'Evaluări și recenzii';

  @override
  String get noRatings => 'fără evaluări';

  @override
  String ratingsCount(String count) {
    return '$count+ evaluări';
  }

  @override
  String get errorActivatingApp => 'Eroare la activarea aplicației';

  @override
  String get integrationSetupRequired => 'Dacă aceasta este o aplicație de integrare, asigurați-vă că configurarea este completă.';

  @override
  String get installed => 'Instalat';

  @override
  String get appIdLabel => 'ID-ul aplicației';

  @override
  String get appNameLabel => 'Numele aplicației';

  @override
  String get appNamePlaceholder => 'Aplicația mea minunată';

  @override
  String get pleaseEnterAppName => 'Vă rugăm să introduceți numele aplicației';

  @override
  String get categoryLabel => 'Categorie';

  @override
  String get selectCategory => 'Selectați categoria';

  @override
  String get descriptionLabel => 'Descriere';

  @override
  String get appDescriptionPlaceholder => 'Aplicația mea minunată este o aplicație grozavă care face lucruri uimitoare. Este cea mai bună aplicație!';

  @override
  String get pleaseProvideValidDescription => 'Vă rugăm să furnizați o descriere validă';

  @override
  String get appPricingLabel => 'Prețul aplicației';

  @override
  String get noneSelected => 'Niciuna selectată';

  @override
  String get appIdCopiedToClipboard => 'ID-ul aplicației copiat în clipboard';

  @override
  String get appCategoryModalTitle => 'Categoria aplicației';

  @override
  String get pricingFree => 'Gratuit';

  @override
  String get pricingPaid => 'Cu plată';

  @override
  String get loadingCapabilities => 'Se încarcă capacitățile...';

  @override
  String get filterInstalled => 'Instalate';

  @override
  String get filterMyApps => 'Aplicațiile mele';

  @override
  String get clearSelection => 'Șterge selecția';

  @override
  String get filterCategory => 'Categorie';

  @override
  String get rating4PlusStars => '4+ stele';

  @override
  String get rating3PlusStars => '3+ stele';

  @override
  String get rating2PlusStars => '2+ stele';

  @override
  String get rating1PlusStars => '1+ stea';

  @override
  String get filterRating => 'Evaluare';

  @override
  String get filterCapabilities => 'Capacități';

  @override
  String get noNotificationScopesAvailable => 'Nu există domenii de notificare disponibile';

  @override
  String get popularApps => 'Aplicații populare';

  @override
  String get pleaseProvidePrompt => 'Vă rugăm să furnizați o solicitare';

  @override
  String chatWithAppName(String appName) {
    return 'Chat cu $appName';
  }

  @override
  String get defaultAiAssistant => 'Asistent AI implicit';

  @override
  String get readyToChat => '✨ Pregătit pentru chat!';

  @override
  String get connectionNeeded => '🌐 Conexiune necesară';

  @override
  String get startConversation => 'Începeți o conversație și lăsați magia să înceapă';

  @override
  String get checkInternetConnection => 'Vă rugăm să verificați conexiunea la internet';

  @override
  String get wasThisHelpful => 'A fost util?';

  @override
  String get thankYouForFeedback => 'Mulțumim pentru feedback!';

  @override
  String get maxFilesUploadError => 'Puteți încărca doar 4 fișiere o dată';

  @override
  String get attachedFiles => '📎 Fișiere atașate';

  @override
  String get takePhoto => 'Faceți o fotografie';

  @override
  String get captureWithCamera => 'Capturați cu camera';

  @override
  String get selectImages => 'Selectați imagini';

  @override
  String get chooseFromGallery => 'Alegeți din galerie';

  @override
  String get selectFile => 'Selectați un fișier';

  @override
  String get chooseAnyFileType => 'Alegeți orice tip de fișier';

  @override
  String get cannotReportOwnMessages => 'Nu puteți raporta propriile mesaje';

  @override
  String get messageReportedSuccessfully => '✅ Mesaj raportat cu succes';

  @override
  String get confirmReportMessage => 'Sigur doriți să raportați acest mesaj?';

  @override
  String get selectChatAssistant => 'Selectați asistent de chat';

  @override
  String get enableMoreApps => 'Activați mai multe aplicații';

  @override
  String get chatCleared => 'Chat șters';

  @override
  String get clearChatTitle => 'Ștergeți chatul?';

  @override
  String get confirmClearChat => 'Sigur doriți să ștergeți chatul? Această acțiune nu poate fi anulată.';

  @override
  String get copy => 'Copiază';

  @override
  String get share => 'Partajează';

  @override
  String get report => 'Raportează';

  @override
  String get microphonePermissionRequired => 'Permisiunea microfonului este necesară pentru înregistrarea vocală.';

  @override
  String get microphonePermissionDenied => 'Permisiunea microfonului refuzată. Vă rugăm să acordați permisiunea în Preferințe sistem > Confidențialitate și securitate > Microfon.';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'Verificarea permisiunii microfonului a eșuat: $error';
  }

  @override
  String get failedToTranscribeAudio => 'Transcrierea audio a eșuat';

  @override
  String get transcribing => 'Transcriere...';

  @override
  String get transcriptionFailed => 'Transcrierea a eșuat';

  @override
  String get discardedConversation => 'Conversație respinsă';

  @override
  String get at => 'la';

  @override
  String get from => 'de la';

  @override
  String get copied => 'Copiat!';

  @override
  String get copyLink => 'Copiază link-ul';

  @override
  String get hideTranscript => 'Ascunde transcrierea';

  @override
  String get viewTranscript => 'Vizualizează transcrierea';

  @override
  String get conversationDetails => 'Detalii conversație';

  @override
  String get transcript => 'Transcriere';

  @override
  String segmentsCount(int count) {
    return '$count segmente';
  }

  @override
  String get noTranscriptAvailable => 'Nicio transcriere disponibilă';

  @override
  String get noTranscriptMessage => 'Această conversație nu are transcriere.';

  @override
  String get conversationUrlCouldNotBeGenerated => 'URL-ul conversației nu a putut fi generat.';

  @override
  String get failedToGenerateConversationLink => 'Generarea link-ului conversației a eșuat';

  @override
  String get failedToGenerateShareLink => 'Generarea link-ului de partajare a eșuat';

  @override
  String get reloadingConversations => 'Reîncărcare conversații...';

  @override
  String get user => 'Utilizator';

  @override
  String get starred => 'Cu stea';

  @override
  String get date => 'Dată';

  @override
  String get noResultsFound => 'Nu s-au găsit rezultate';

  @override
  String get tryAdjustingSearchTerms => 'Încercați să ajustați termenii de căutare';

  @override
  String get starConversationsToFindQuickly => 'Marcați conversațiile cu stea pentru a le găsi rapid aici';

  @override
  String noConversationsOnDate(String date) {
    return 'Nicio conversație pe $date';
  }

  @override
  String get trySelectingDifferentDate => 'Încercați să selectați o altă dată';

  @override
  String get conversations => 'Conversații';

  @override
  String get chat => 'Chat';

  @override
  String get actions => 'Acțiuni';

  @override
  String get syncAvailable => 'Sincronizare disponibilă';

  @override
  String get referAFriend => 'Recomandă un prieten';

  @override
  String get help => 'Ajutor';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'Actualizează la Pro';

  @override
  String get getOmiDevice => 'Obține dispozitiv Omi';

  @override
  String get wearableAiCompanion => 'Companion AI portabil';

  @override
  String get loadingMemories => 'Se încarcă amintirile...';

  @override
  String get allMemories => 'Toate amintirile';

  @override
  String get aboutYou => 'Despre tine';

  @override
  String get manual => 'Manual';

  @override
  String get loadingYourMemories => 'Se încarcă amintirile tale...';

  @override
  String get createYourFirstMemory => 'Creează prima ta amintire pentru a începe';

  @override
  String get tryAdjustingFilter => 'Încearcă să ajustezi căutarea sau filtrul';

  @override
  String get whatWouldYouLikeToRemember => 'Ce ai vrea să ții minte?';

  @override
  String get category => 'Categorie';

  @override
  String get public => 'Public';

  @override
  String get failedToSaveCheckConnection => 'Salvare eșuată. Verifică conexiunea.';

  @override
  String get createMemory => 'Creează amintire';

  @override
  String get deleteMemoryConfirmation => 'Ești sigur că vrei să ștergi această amintire? Această acțiune nu poate fi anulată.';

  @override
  String get makePrivate => 'Fă privat';

  @override
  String get organizeAndControlMemories => 'Organizează și controlează-ți amintirile';

  @override
  String get total => 'Total';

  @override
  String get makeAllMemoriesPrivate => 'Fă toate amintirile private';

  @override
  String get setAllMemoriesToPrivate => 'Setează toate amintirile ca private';

  @override
  String get makeAllMemoriesPublic => 'Fă toate amintirile publice';

  @override
  String get setAllMemoriesToPublic => 'Setează toate amintirile ca publice';

  @override
  String get permanentlyRemoveAllMemories => 'Elimină permanent toate amintirile din Omi';

  @override
  String get allMemoriesAreNowPrivate => 'Toate amintirile sunt acum private';

  @override
  String get allMemoriesAreNowPublic => 'Toate amintirile sunt acum publice';

  @override
  String get clearOmisMemory => 'Șterge memoria lui Omi';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Sigur vrei să ștergi memoria lui Omi? Această acțiune nu poate fi anulată și va șterge permanent toate cele $count amintiri.';
  }

  @override
  String get omisMemoryCleared => 'Memoria lui Omi despre tine a fost ștearsă';

  @override
  String get welcomeToOmi => 'Bun venit la Omi';

  @override
  String get continueWithApple => 'Continuă cu Apple';

  @override
  String get continueWithGoogle => 'Continuă cu Google';

  @override
  String get byContinuingYouAgree => 'Continuând, ești de acord cu ';

  @override
  String get termsOfService => 'Termenii de serviciu';

  @override
  String get and => ' și ';

  @override
  String get dataAndPrivacy => 'Date și confidențialitate';

  @override
  String get secureAuthViaAppleId => 'Autentificare securizată prin Apple ID';

  @override
  String get secureAuthViaGoogleAccount => 'Autentificare securizată prin cont Google';

  @override
  String get whatWeCollect => 'Ce colectăm';

  @override
  String get dataCollectionMessage => 'Continuând, conversațiile, înregistrările și informațiile personale vor fi stocate în siguranță pe serverele noastre pentru a oferi informații alimentate de AI și a activa toate funcțiile aplicației.';

  @override
  String get dataProtection => 'Protecția datelor';

  @override
  String get yourDataIsProtected => 'Datele tale sunt protejate și guvernate de ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'Vă rugăm să selectați limba principală';

  @override
  String get chooseYourLanguage => 'Alegeți limba dvs.';

  @override
  String get selectPreferredLanguageForBestExperience => 'Selectați limba preferată pentru cea mai bună experiență Omi';

  @override
  String get searchLanguages => 'Căutați limbi...';

  @override
  String get selectALanguage => 'Selectați o limbă';

  @override
  String get tryDifferentSearchTerm => 'Încercați un alt termen de căutare';

  @override
  String get pleaseEnterYourName => 'Vă rugăm să introduceți numele dvs.';

  @override
  String get nameMustBeAtLeast2Characters => 'Numele trebuie să aibă cel puțin 2 caractere';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed => 'Spuneți-ne cum doriți să fiți adresat. Acest lucru ajută la personalizarea experienței Omi.';

  @override
  String charactersCount(int count) {
    return '$count caractere';
  }

  @override
  String get enableFeaturesForBestExperience => 'Activați funcțiile pentru cea mai bună experiență Omi pe dispozitivul dvs.';

  @override
  String get microphoneAccess => 'Acces la microfon';

  @override
  String get recordAudioConversations => 'Înregistrați conversații audio';

  @override
  String get microphoneAccessDescription => 'Omi are nevoie de acces la microfon pentru a înregistra conversațiile dvs. și a furniza transcripții.';

  @override
  String get screenRecording => 'Înregistrare ecran';

  @override
  String get captureSystemAudioFromMeetings => 'Capturați audio-ul sistemului din întâlniri';

  @override
  String get screenRecordingDescription => 'Omi are nevoie de permisiune de înregistrare a ecranului pentru a captura audio-ul sistemului din întâlnirile dvs. bazate pe browser.';

  @override
  String get accessibility => 'Accesibilitate';

  @override
  String get detectBrowserBasedMeetings => 'Detectați întâlnirile bazate pe browser';

  @override
  String get accessibilityDescription => 'Omi are nevoie de permisiune de accesibilitate pentru a detecta când vă alăturați întâlnirilor Zoom, Meet sau Teams în browser-ul dvs.';

  @override
  String get pleaseWait => 'Vă rugăm așteptați...';

  @override
  String get joinTheCommunity => 'Alăturați-vă comunității!';

  @override
  String get loadingProfile => 'Se încarcă profilul...';

  @override
  String get profileSettings => 'Setări profil';

  @override
  String get noEmailSet => 'Niciun e-mail setat';

  @override
  String get userIdCopiedToClipboard => 'ID utilizator copiat';

  @override
  String get yourInformation => 'Informațiile Dvs.';

  @override
  String get setYourName => 'Setați numele';

  @override
  String get changeYourName => 'Schimbați numele';

  @override
  String get manageYourOmiPersona => 'Gestionați persona Omi';

  @override
  String get voiceAndPeople => 'Voce și Oameni';

  @override
  String get teachOmiYourVoice => 'Învățați Omi vocea dvs.';

  @override
  String get tellOmiWhoSaidIt => 'Spuneți Omi cine a spus-o 🗣️';

  @override
  String get payment => 'Plată';

  @override
  String get addOrChangeYourPaymentMethod => 'Adăugați sau schimbați metoda de plată';

  @override
  String get preferences => 'Preferințe';

  @override
  String get helpImproveOmiBySharing => 'Ajutați la îmbunătățirea Omi prin partajarea datelor de analiză anonimizate';

  @override
  String get deleteAccount => 'Șterge Contul';

  @override
  String get deleteYourAccountAndAllData => 'Ștergeți contul și toate datele';

  @override
  String get clearLogs => 'Ștergeți jurnalele';

  @override
  String get debugLogsCleared => 'Jurnalele de depanare au fost șterse';

  @override
  String get exportConversations => 'Exportați conversații';

  @override
  String get exportAllConversationsToJson => 'Exportați toate conversațiile dvs. într-un fișier JSON.';

  @override
  String get conversationsExportStarted => 'Export conversații pornit. Aceasta poate dura câteva secunde, vă rugăm așteptați.';

  @override
  String get mcpDescription => 'Pentru a conecta Omi cu alte aplicații pentru a citi, căuta și gestiona amintirile și conversațiile dvs. Creați o cheie pentru a începe.';

  @override
  String get apiKeys => 'Chei API';

  @override
  String errorLabel(String error) {
    return 'Eroare: $error';
  }

  @override
  String get noApiKeysFound => 'Nu au fost găsite chei API. Creați una pentru a începe.';

  @override
  String get advancedSettings => 'Setări avansate';

  @override
  String get triggersWhenNewConversationCreated => 'Se declanșează când este creată o nouă conversație.';

  @override
  String get triggersWhenNewTranscriptReceived => 'Se declanșează când este primită o nouă transcriere.';

  @override
  String get realtimeAudioBytes => 'Octeți audio în timp real';

  @override
  String get triggersWhenAudioBytesReceived => 'Se declanșează când sunt primiți octeți audio.';

  @override
  String get everyXSeconds => 'La fiecare x secunde';

  @override
  String get triggersWhenDaySummaryGenerated => 'Se declanșează când este generat rezumatul zilnic.';

  @override
  String get tryLatestExperimentalFeatures => 'Încercați cele mai recente funcții experimentale de la echipa Omi.';

  @override
  String get transcriptionServiceDiagnosticStatus => 'Starea diagnostică a serviciului de transcriere';

  @override
  String get enableDetailedDiagnosticMessages => 'Activați mesajele de diagnostic detaliate de la serviciul de transcriere';

  @override
  String get autoCreateAndTagNewSpeakers => 'Creați și etich etați automat vorbitori noi';

  @override
  String get automaticallyCreateNewPerson => 'Creați automat o persoană nouă când un nume este detectat în transcriere.';

  @override
  String get pilotFeatures => 'Funcții pilot';

  @override
  String get pilotFeaturesDescription => 'Aceste funcții sunt teste și nu se garantează suportul.';

  @override
  String get suggestFollowUpQuestion => 'Sugerați întrebare de urmărire';

  @override
  String get saveSettings => 'Salvează Setările';

  @override
  String get syncingDeveloperSettings => 'Sincronizare setări dezvoltator...';

  @override
  String get summary => 'Rezumat';

  @override
  String get auto => 'Automat';

  @override
  String get noSummaryForApp => 'Niciun rezumat disponibil pentru această aplicație. Încercați o altă aplicație pentru rezultate mai bune.';

  @override
  String get tryAnotherApp => 'Încercați o altă aplicație';

  @override
  String generatedBy(String appName) {
    return 'Generat de $appName';
  }

  @override
  String get overview => 'Prezentare generală';

  @override
  String get otherAppResults => 'Rezultate ale altor aplicații';

  @override
  String get unknownApp => 'Aplicație necunoscută';

  @override
  String get noSummaryAvailable => 'Niciun rezumat disponibil';

  @override
  String get conversationNoSummaryYet => 'Această conversație nu are încă un rezumat.';

  @override
  String get chooseSummarizationApp => 'Alegeți aplicația de rezumat';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName setată ca aplicație de rezumat implicită';
  }

  @override
  String get letOmiChooseAutomatically => 'Lăsați Omi să aleagă automat cea mai bună aplicație';

  @override
  String get deleteConversationConfirmation => 'Sigur doriți să ștergeți această conversație? Această acțiune nu poate fi anulată.';

  @override
  String get conversationDeleted => 'Conversație ștearsă';

  @override
  String get generatingLink => 'Generare link...';

  @override
  String get editConversation => 'Editează conversația';

  @override
  String get conversationLinkCopiedToClipboard => 'Link-ul conversației a fost copiat în clipboard';

  @override
  String get conversationTranscriptCopiedToClipboard => 'Transcrierea conversației a fost copiată în clipboard';

  @override
  String get editConversationDialogTitle => 'Editează conversația';

  @override
  String get changeTheConversationTitle => 'Schimbă titlul conversației';

  @override
  String get conversationTitle => 'Titlul conversației';

  @override
  String get enterConversationTitle => 'Introduceți titlul conversației...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'Titlul conversației a fost actualizat cu succes';

  @override
  String get failedToUpdateConversationTitle => 'Actualizarea titlului conversației a eșuat';

  @override
  String get errorUpdatingConversationTitle => 'Eroare la actualizarea titlului conversației';

  @override
  String get settingUp => 'Configurare...';

  @override
  String get startYourFirstRecording => 'Începeți prima înregistrare';

  @override
  String get preparingSystemAudioCapture => 'Pregătirea capturării audio a sistemului';

  @override
  String get clickTheButtonToCaptureAudio => 'Faceți clic pe buton pentru a captura audio pentru transcrieri live, informații AI și salvare automată.';

  @override
  String get reconnecting => 'Reconectare...';

  @override
  String get recordingPaused => 'Înregistrare întreruptă';

  @override
  String get recordingActive => 'Înregistrare activă';

  @override
  String get startRecording => 'Începeți înregistrarea';

  @override
  String resumingInCountdown(String countdown) {
    return 'Reluare în ${countdown}s...';
  }

  @override
  String get tapPlayToResume => 'Atingeți redare pentru a relua';

  @override
  String get listeningForAudio => 'Ascultare audio...';

  @override
  String get preparingAudioCapture => 'Pregătirea capturării audio';

  @override
  String get clickToBeginRecording => 'Faceți clic pentru a începe înregistrarea';

  @override
  String get translated => 'tradus';

  @override
  String get liveTranscript => 'Transcriere live';

  @override
  String segmentsSingular(String count) {
    return '$count segment';
  }

  @override
  String segmentsPlural(String count) {
    return '$count segmente';
  }

  @override
  String get startRecordingToSeeTranscript => 'Începeți înregistrarea pentru a vedea transcrierea live';

  @override
  String get paused => 'Întrerupt';

  @override
  String get initializing => 'Inițializare...';

  @override
  String get recording => 'Înregistrare';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'Microfon schimbat. Reluare în ${countdown}s';
  }

  @override
  String get clickPlayToResumeOrStop => 'Faceți clic pe redare pentru a relua sau oprire pentru a finaliza';

  @override
  String get settingUpSystemAudioCapture => 'Configurarea capturării audio a sistemului';

  @override
  String get capturingAudioAndGeneratingTranscript => 'Capturarea audio și generarea transcrierii';

  @override
  String get clickToBeginRecordingSystemAudio => 'Faceți clic pentru a începe înregistrarea audio a sistemului';

  @override
  String get you => 'Tu';

  @override
  String speakerWithId(String speakerId) {
    return 'Vorbitor $speakerId';
  }

  @override
  String get translatedByOmi => 'tradus de omi';

  @override
  String get backToConversations => 'Înapoi la conversații';

  @override
  String get systemAudio => 'Sistem';

  @override
  String get mic => 'Microfon';

  @override
  String audioInputSetTo(String deviceName) {
    return 'Intrare audio setată la $deviceName';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'Eroare la comutarea dispozitivului audio: $error';
  }

  @override
  String get selectAudioInput => 'Selectați intrarea audio';

  @override
  String get loadingDevices => 'Se încarcă dispozitivele...';

  @override
  String get settingsHeader => 'SETĂRI';

  @override
  String get plansAndBilling => 'Planuri și Facturare';

  @override
  String get calendarIntegration => 'Integrare Calendar';

  @override
  String get dailySummary => 'Rezumat Zilnic';

  @override
  String get developer => 'Dezvoltator';

  @override
  String get about => 'Despre';

  @override
  String get selectTime => 'Selectează Ora';

  @override
  String get accountGroup => 'Cont';

  @override
  String get signOutQuestion => 'Deconectare?';

  @override
  String get signOutConfirmation => 'Sigur doriți să vă deconectați?';

  @override
  String get customVocabularyHeader => 'VOCABULAR PERSONALIZAT';

  @override
  String get addWordsDescription => 'Adăugați cuvinte pe care Omi ar trebui să le recunoască în timpul transcrierii.';

  @override
  String get enterWordsHint => 'Introduceți cuvinte (separate prin virgulă)';

  @override
  String get dailySummaryHeader => 'REZUMAT ZILNIC';

  @override
  String get dailySummaryTitle => 'Rezumat Zilnic';

  @override
  String get dailySummaryDescription => 'Primiți un rezumat personalizat al conversațiilor dvs.';

  @override
  String get deliveryTime => 'Ora de Livrare';

  @override
  String get deliveryTimeDescription => 'Când să primiți rezumatul zilnic';

  @override
  String get subscription => 'Abonament';

  @override
  String get viewPlansAndUsage => 'Vezi Planuri și Utilizare';

  @override
  String get viewPlansDescription => 'Gestionați abonamentul și vedeți statistici de utilizare';

  @override
  String get addOrChangePaymentMethod => 'Adăugați sau schimbați metoda de plată';

  @override
  String get displayOptions => 'Opțiuni de afișare';

  @override
  String get showMeetingsInMenuBar => 'Afișați întâlnirile în bara de meniu';

  @override
  String get displayUpcomingMeetingsDescription => 'Afișați întâlnirile viitoare în bara de meniu';

  @override
  String get showEventsWithoutParticipants => 'Afișați evenimentele fără participanți';

  @override
  String get includePersonalEventsDescription => 'Includeți evenimentele personale fără participanți';

  @override
  String get upcomingMeetings => 'ÎNTÂLNIRI VIITOARE';

  @override
  String get checkingNext7Days => 'Verificarea următoarelor 7 zile';

  @override
  String get shortcuts => 'Comenzi rapide';

  @override
  String get shortcutChangeInstruction => 'Faceți clic pe o comandă rapidă pentru a o modifica. Apăsați Escape pentru a anula.';

  @override
  String get configurePersonaDescription => 'Configurați-vă persona AI';

  @override
  String get configureSTTProvider => 'Configurați furnizorul STT';

  @override
  String get setConversationEndDescription => 'Setați când conversațiile se termină automat';

  @override
  String get importDataDescription => 'Importați date din alte surse';

  @override
  String get exportConversationsDescription => 'Exportați conversațiile în JSON';

  @override
  String get exportingConversations => 'Exportarea conversațiilor...';

  @override
  String get clearNodesDescription => 'Ștergeți toate nodurile și conexiunile';

  @override
  String get deleteKnowledgeGraphQuestion => 'Ștergeți graficul de cunoștințe?';

  @override
  String get deleteKnowledgeGraphWarning => 'Aceasta va șterge toate datele derivate din graficul de cunoștințe. Amintirile dvs. originale rămân în siguranță.';

  @override
  String get connectOmiWithAI => 'Conectați Omi cu asistenți AI';

  @override
  String get noAPIKeys => 'Nicio cheie API. Creați una pentru a începe.';

  @override
  String get autoCreateWhenDetected => 'Creați automat când numele este detectat';

  @override
  String get trackPersonalGoals => 'Urmăriți obiective personale pe pagina de pornire';

  @override
  String get dailyReflectionDescription => 'Memento la ora 21:00 pentru a reflecta asupra zilei tale';

  @override
  String get endpointURL => 'URL punct final';

  @override
  String get links => 'Linkuri';

  @override
  String get discordMemberCount => 'Peste 8000 de membri pe Discord';

  @override
  String get userInformation => 'Informații despre utilizator';

  @override
  String get capabilities => 'Capabilități';

  @override
  String get previewScreenshots => 'Previzualizare capturi de ecran';

  @override
  String get holdOnPreparingForm => 'Așteptați, pregătim formularul pentru dumneavoastră';

  @override
  String get bySubmittingYouAgreeToOmi => 'Prin trimitere, sunteți de acord cu ';

  @override
  String get termsAndPrivacyPolicy => 'Termeni și Politica de Confidențialitate';

  @override
  String get helpsDiagnoseIssuesAutoDeletes => 'Ajută la diagnosticarea problemelor. Șters automat după 3 zile.';

  @override
  String get manageYourApp => 'Gestionează-ți aplicația';

  @override
  String get updatingYourApp => 'Se actualizează aplicația';

  @override
  String get fetchingYourAppDetails => 'Se preiau detaliile aplicației';

  @override
  String get updateAppQuestion => 'Actualizați aplicația?';

  @override
  String get updateAppConfirmation => 'Sunteți sigur că doriți să actualizați aplicația? Modificările vor fi vizibile după examinarea de către echipa noastră.';

  @override
  String get updateApp => 'Actualizare aplicație';

  @override
  String get createAndSubmitNewApp => 'Creați și trimiteți o aplicație nouă';

  @override
  String appsCount(String count) {
    return 'Aplicații ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'Aplicații private ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'Aplicații publice ($count)';
  }

  @override
  String get newVersionAvailable => 'Versiune nouă disponibilă  🎉';

  @override
  String get no => 'Nu';

  @override
  String get subscriptionCancelledSuccessfully => 'Abonament anulat cu succes. Va rămâne activ până la sfârșitul perioadei curente de facturare.';

  @override
  String get failedToCancelSubscription => 'Anularea abonamentului a eșuat. Vă rugăm să încercați din nou.';

  @override
  String get invalidPaymentUrl => 'URL de plată invalid';

  @override
  String get permissionsAndTriggers => 'Permisiuni și declanșatoare';

  @override
  String get chatFeatures => 'Funcții de chat';

  @override
  String get uninstall => 'Dezinstalare';

  @override
  String get installs => 'INSTALĂRI';

  @override
  String get priceLabel => 'PREȚ';

  @override
  String get updatedLabel => 'ACTUALIZAT';

  @override
  String get createdLabel => 'CREAT';

  @override
  String get featuredLabel => 'RECOMANDAT';

  @override
  String get cancelSubscriptionQuestion => 'Anulați abonamentul?';

  @override
  String get cancelSubscriptionConfirmation => 'Sunteți sigur că doriți să vă anulați abonamentul? Veți avea în continuare acces până la sfârșitul perioadei curente de facturare.';

  @override
  String get cancelSubscriptionButton => 'Anulare abonament';

  @override
  String get cancelling => 'Se anulează...';

  @override
  String get betaTesterMessage => 'Sunteți un tester beta pentru această aplicație. Nu este încă publică. Va fi publică după aprobare.';

  @override
  String get appUnderReviewMessage => 'Aplicația dvs. este în curs de examinare și vizibilă doar pentru dvs. Va fi publică după aprobare.';

  @override
  String get appRejectedMessage => 'Aplicația dvs. a fost respinsă. Actualizați detaliile și retrimiteți pentru examinare.';

  @override
  String get invalidIntegrationUrl => 'URL de integrare invalid';

  @override
  String get tapToComplete => 'Atingeți pentru a finaliza';

  @override
  String get invalidSetupInstructionsUrl => 'URL instrucțiuni de configurare invalid';

  @override
  String get pushToTalk => 'Apăsați pentru a vorbi';

  @override
  String get summaryPrompt => 'Prompt de rezumat';

  @override
  String get pleaseSelectARating => 'Vă rugăm să selectați o evaluare';

  @override
  String get reviewAddedSuccessfully => 'Recenzie adăugată cu succes 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'Recenzie actualizată cu succes 🚀';

  @override
  String get failedToSubmitReview => 'Trimiterea recenziei a eșuat. Vă rugăm să încercați din nou.';

  @override
  String get addYourReview => 'Adăugați recenzia dvs.';

  @override
  String get editYourReview => 'Editați recenzia dvs.';

  @override
  String get writeAReviewOptional => 'Scrieți o recenzie (opțional)';

  @override
  String get submitReview => 'Trimite recenzia';

  @override
  String get updateReview => 'Actualizare recenzie';

  @override
  String get yourReview => 'Recenzia dvs.';

  @override
  String get anonymousUser => 'Utilizator anonim';

  @override
  String get issueActivatingApp => 'A apărut o problemă la activarea acestei aplicații. Vă rugăm să încercați din nou.';

  @override
  String get dataAccessNoticeDescription => 'This app will access your data. Omi AI is not responsible for how your data is used, modified, or deleted by this app';

  @override
  String get copyUrl => 'Copiază URL';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => 'Lun';

  @override
  String get weekdayTue => 'Mar';

  @override
  String get weekdayWed => 'Mie';

  @override
  String get weekdayThu => 'Joi';

  @override
  String get weekdayFri => 'Vin';

  @override
  String get weekdaySat => 'Sâm';

  @override
  String get weekdaySun => 'Dum';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return 'Integrarea $serviceName în curând';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'Deja exportat în $platform';
  }

  @override
  String get anotherPlatform => 'altă platformă';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'Vă rugăm să vă autentificați cu $serviceName în Setări > Integrări sarcini';
  }

  @override
  String addingToService(String serviceName) {
    return 'Se adaugă în $serviceName...';
  }

  @override
  String addedToService(String serviceName) {
    return 'Adăugat în $serviceName';
  }

  @override
  String failedToAddToService(String serviceName) {
    return 'Nu s-a putut adăuga în $serviceName';
  }

  @override
  String get permissionDeniedForAppleReminders => 'Permisiune refuzată pentru Apple Reminders';

  @override
  String failedToCreateApiKey(String error) {
    return 'Nu s-a putut crea cheia API a furnizorului: $error';
  }

  @override
  String get createAKey => 'Creează o cheie';

  @override
  String get apiKeyRevokedSuccessfully => 'Cheie API revocată cu succes';

  @override
  String failedToRevokeApiKey(String error) {
    return 'Nu s-a putut revoca cheia API: $error';
  }

  @override
  String get omiApiKeys => 'Chei API Omi';

  @override
  String get apiKeysDescription => 'Cheile API sunt folosite pentru autentificare atunci când aplicația ta comunică cu serverul OMI. Ele permit aplicației tale să creeze amintiri și să acceseze alte servicii OMI în siguranță.';

  @override
  String get aboutOmiApiKeys => 'Despre cheile API Omi';

  @override
  String get yourNewKey => 'Noua ta cheie:';

  @override
  String get copyToClipboard => 'Copiază în clipboard';

  @override
  String get pleaseCopyKeyNow => 'Te rugăm să o copiezi acum și să o notezi într-un loc sigur. ';

  @override
  String get willNotSeeAgain => 'Nu o vei mai putea vedea din nou.';

  @override
  String get revokeKey => 'Revocă cheia';

  @override
  String get revokeApiKeyQuestion => 'Revoci cheia API?';

  @override
  String get revokeApiKeyWarning => 'Această acțiune nu poate fi anulată. Orice aplicații care folosesc această cheie nu vor mai putea accesa API-ul.';

  @override
  String get revoke => 'Revocă';

  @override
  String get whatWouldYouLikeToCreate => 'Ce ai dori să creezi?';

  @override
  String get createAnApp => 'Creează o aplicație';

  @override
  String get createAndShareYourApp => 'Creează și partajează aplicația ta';

  @override
  String get createMyClone => 'Creează clona mea';

  @override
  String get createYourDigitalClone => 'Creează clona ta digitală';

  @override
  String get itemApp => 'Aplicație';

  @override
  String get itemPersona => 'Persona';

  @override
  String keepItemPublic(String item) {
    return 'Păstrează $item public';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return 'Faci $item public?';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return 'Faci $item privat?';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'Dacă faci $item public, poate fi folosit de toată lumea';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'Dacă faci $item privat acum, va înceta să funcționeze pentru toată lumea și va fi vizibil doar pentru tine';
  }

  @override
  String get manageApp => 'Gestionează aplicația';

  @override
  String get updatePersonaDetails => 'Actualizează detaliile persona';

  @override
  String deleteItemTitle(String item) {
    return 'Șterge $item';
  }

  @override
  String deleteItemQuestion(String item) {
    return 'Ștergi $item?';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'Ești sigur că vrei să ștergi acest $item? Această acțiune nu poate fi anulată.';
  }

  @override
  String get revokeKeyQuestion => 'Revoci cheia?';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'Ești sigur că vrei să revoci cheia \"$keyName\"? Această acțiune nu poate fi anulată.';
  }

  @override
  String get createNewKey => 'Creează cheie nouă';

  @override
  String get keyNameHint => 'ex. Claude Desktop';

  @override
  String get pleaseEnterAName => 'Te rugăm să introduci un nume.';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'Nu s-a putut crea cheia: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'Nu s-a putut crea cheia. Te rugăm să încerci din nou.';

  @override
  String get keyCreated => 'Cheie creată';

  @override
  String get keyCreatedMessage => 'Cheia ta nouă a fost creată. Te rugăm să o copiezi acum. Nu o vei mai putea vedea.';

  @override
  String get keyWord => 'Cheie';

  @override
  String get externalAppAccess => 'Acces aplicații externe';

  @override
  String get externalAppAccessDescription => 'Următoarele aplicații instalate au integrări externe și pot accesa datele tale, cum ar fi conversațiile și amintirile.';

  @override
  String get noExternalAppsHaveAccess => 'Nicio aplicație externă nu are acces la datele tale.';

  @override
  String get maximumSecurityE2ee => 'Securitate maximă (E2EE)';

  @override
  String get e2eeDescription => 'Criptarea end-to-end este standardul de aur pentru confidențialitate. Când este activată, datele dvs. sunt criptate pe dispozitivul dvs. înainte de a fi trimise la serverele noastre. Aceasta înseamnă că nimeni, nici măcar Omi, nu poate accesa conținutul dvs.';

  @override
  String get importantTradeoffs => 'Compromisuri importante:';

  @override
  String get e2eeTradeoff1 => '• Unele funcții precum integrările cu aplicații externe pot fi dezactivate.';

  @override
  String get e2eeTradeoff2 => '• Dacă pierdeți parola, datele dvs. nu pot fi recuperate.';

  @override
  String get featureComingSoon => 'Această funcție va fi disponibilă în curând!';

  @override
  String get migrationInProgressMessage => 'Migrație în curs. Nu puteți schimba nivelul de protecție până la finalizare.';

  @override
  String get migrationFailed => 'Migrația a eșuat';

  @override
  String migratingFromTo(String source, String target) {
    return 'Migrare de la $source la $target';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total obiecte';
  }

  @override
  String get secureEncryption => 'Criptare securizată';

  @override
  String get secureEncryptionDescription => 'Datele dvs. sunt criptate cu o cheie unică pentru dvs. pe serverele noastre, găzduite pe Google Cloud. Aceasta înseamnă că conținutul dvs. brut este inaccesibil pentru oricine, inclusiv personalul Omi sau Google, direct din baza de date.';

  @override
  String get endToEndEncryption => 'Criptare end-to-end';

  @override
  String get e2eeCardDescription => 'Activați pentru securitate maximă, unde doar dvs. puteți accesa datele dvs. Atingeți pentru a afla mai multe.';

  @override
  String get dataAlwaysEncrypted => 'Indiferent de nivel, datele dvs. sunt întotdeauna criptate în repaus și în tranzit.';

  @override
  String get readOnlyScope => 'Doar citire';

  @override
  String get fullAccessScope => 'Acces complet';

  @override
  String get readScope => 'Citire';

  @override
  String get writeScope => 'Scriere';

  @override
  String get apiKeyCreated => 'Cheie API creată!';

  @override
  String get saveKeyWarning => 'Salvați această cheie acum! Nu o veți mai putea vedea.';

  @override
  String get yourApiKey => 'CHEIA DVS. API';

  @override
  String get tapToCopy => 'Atingeți pentru a copia';

  @override
  String get copyKey => 'Copiază cheia';

  @override
  String get createApiKey => 'Creați cheie API';

  @override
  String get accessDataProgrammatically => 'Accesați datele dvs. programatic';

  @override
  String get keyNameLabel => 'NUMELE CHEII';

  @override
  String get keyNamePlaceholder => 'ex., Integrarea mea';

  @override
  String get permissionsLabel => 'PERMISIUNI';

  @override
  String get permissionsInfoNote => 'R = Citire, W = Scriere. Implicit doar citire dacă nu este selectat nimic.';

  @override
  String get developerApi => 'API pentru dezvoltatori';

  @override
  String get createAKeyToGetStarted => 'Creați o cheie pentru a începe';

  @override
  String errorWithMessage(String error) {
    return 'Eroare: $error';
  }

  @override
  String get omiTraining => 'Antrenament Omi';

  @override
  String get trainingDataProgram => 'Program de date de antrenament';

  @override
  String get getOmiUnlimitedFree => 'Obțineți Omi Unlimited gratuit contribuind cu datele dvs. pentru antrenarea modelelor AI.';

  @override
  String get trainingDataBullets => '• Datele dvs. ajută la îmbunătățirea modelelor AI\n• Sunt partajate doar date nesensibile\n• Proces complet transparent';

  @override
  String get learnMoreAtOmiTraining => 'Aflați mai multe la omi.me/training';

  @override
  String get agreeToContributeData => 'Înțeleg și sunt de acord să contribui cu datele mele pentru antrenarea AI';

  @override
  String get submitRequest => 'Trimite cererea';

  @override
  String get thankYouRequestUnderReview => 'Mulțumim! Cererea dvs. este în curs de examinare. Vă vom notifica după aprobare.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'Planul dvs. va rămâne activ până la $date. După aceea, veți pierde accesul la funcțiile nelimitate. Sunteți sigur?';
  }

  @override
  String get confirmCancellation => 'Confirmă anularea';

  @override
  String get keepMyPlan => 'Păstrează planul meu';

  @override
  String get subscriptionSetToCancel => 'Abonamentul dvs. este setat să fie anulat la sfârșitul perioadei.';

  @override
  String get switchedToOnDevice => 'Comutat la transcrierea pe dispozitiv';

  @override
  String get couldNotSwitchToFreePlan => 'Nu s-a putut comuta la planul gratuit. Vă rugăm să încercați din nou.';

  @override
  String get couldNotLoadPlans => 'Nu s-au putut încărca planurile disponibile. Vă rugăm să încercați din nou.';

  @override
  String get selectedPlanNotAvailable => 'Planul selectat nu este disponibil. Vă rugăm să încercați din nou.';

  @override
  String get upgradeToAnnualPlan => 'Treceți la planul anual';

  @override
  String get importantBillingInfo => 'Informații importante de facturare:';

  @override
  String get monthlyPlanContinues => 'Planul dvs. lunar actual va continua până la sfârșitul perioadei de facturare';

  @override
  String get paymentMethodCharged => 'Metoda dvs. de plată existentă va fi debitată automat când planul lunar se încheie';

  @override
  String get annualSubscriptionStarts => 'Abonamentul dvs. anual de 12 luni va începe automat după debitare';

  @override
  String get thirteenMonthsCoverage => 'Veți primi în total 13 luni de acoperire (luna curentă + 12 luni anual)';

  @override
  String get confirmUpgrade => 'Confirmă upgrade-ul';

  @override
  String get confirmPlanChange => 'Confirmă schimbarea planului';

  @override
  String get confirmAndProceed => 'Confirmă și continuă';

  @override
  String get upgradeScheduled => 'Upgrade programat';

  @override
  String get changePlan => 'Schimbă planul';

  @override
  String get upgradeAlreadyScheduled => 'Upgrade-ul dvs. la planul anual este deja programat';

  @override
  String get youAreOnUnlimitedPlan => 'Sunteți pe planul Nelimitat.';

  @override
  String get yourOmiUnleashed => 'Omi-ul dvs., dezlănțuit. Deveniți nelimitat pentru posibilități nesfârșite.';

  @override
  String planEndedOn(String date) {
    return 'Planul dvs. s-a încheiat pe $date.\\nReabonați-vă acum - veți fi taxat imediat pentru o nouă perioadă de facturare.';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'Planul dvs. este setat să fie anulat pe $date.\\nReabonați-vă acum pentru a vă păstra beneficiile - fără taxă până la $date.';
  }

  @override
  String get annualPlanStartsAutomatically => 'Planul dvs. anual va începe automat când planul lunar se încheie.';

  @override
  String planRenewsOn(String date) {
    return 'Planul dvs. se reînnoiește pe $date.';
  }

  @override
  String get unlimitedConversations => 'Conversații nelimitate';

  @override
  String get askOmiAnything => 'Întrebați Omi orice despre viața dvs.';

  @override
  String get unlockOmiInfiniteMemory => 'Deblocați memoria infinită a lui Omi';

  @override
  String get youreOnAnnualPlan => 'Sunteți pe planul anual';

  @override
  String get alreadyBestValuePlan => 'Aveți deja planul cu cea mai bună valoare. Nu sunt necesare modificări.';

  @override
  String get unableToLoadPlans => 'Nu se pot încărca planurile';

  @override
  String get checkConnectionTryAgain => 'Verificați conexiunea și încercați din nou';

  @override
  String get useFreePlan => 'Folosește planul gratuit';

  @override
  String get continueText => 'Continuă';

  @override
  String get resubscribe => 'Reabonează-te';

  @override
  String get couldNotOpenPaymentSettings => 'Nu s-au putut deschide setările de plată. Vă rugăm să încercați din nou.';

  @override
  String get managePaymentMethod => 'Gestionează metoda de plată';

  @override
  String get cancelSubscription => 'Anulează abonamentul';

  @override
  String endsOnDate(String date) {
    return 'Se termină pe $date';
  }

  @override
  String get active => 'Activ';

  @override
  String get freePlan => 'Plan gratuit';

  @override
  String get configure => 'Configurează';

  @override
  String get privacyInformation => 'Informații de confidențialitate';

  @override
  String get yourPrivacyMattersToUs => 'Confidențialitatea ta ne interesează';

  @override
  String get privacyIntroText => 'La Omi, luăm foarte în serios confidențialitatea ta. Vrem să fim transparenți despre datele pe care le colectăm și cum le folosim. Iată ce trebuie să știi:';

  @override
  String get whatWeTrack => 'Ce urmărim';

  @override
  String get anonymityAndPrivacy => 'Anonimat și confidențialitate';

  @override
  String get optInAndOptOutOptions => 'Opțiuni de acceptare și refuz';

  @override
  String get ourCommitment => 'Angajamentul nostru';

  @override
  String get commitmentText => 'Ne angajăm să folosim datele pe care le colectăm doar pentru a face Omi un produs mai bun pentru tine. Confidențialitatea și încrederea ta sunt primordiale pentru noi.';

  @override
  String get thankYouText => 'Îți mulțumim că ești un utilizator valoros al Omi. Dacă ai întrebări sau nelămuriri, nu ezita să ne contactezi la team@basedhardware.com.';
}
