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
  String get errorProcessingConversation =>
      'Eroare la procesarea conversației. Te rugăm să încerci din nou mai târziu.';

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
  String get starConversationHint =>
      'Pentru a marca o conversație ca favorită, deschide-o și apasă iconița de stea din antet.';

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
  String get clearChat => 'Șterge conversația';

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
  String get myApps => 'Aplicațiile mele';

  @override
  String get installedApps => 'Aplicații instalate';

  @override
  String get unableToFetchApps =>
      'Nu s-au putut prelua aplicațiile :(\n\nTe rugăm să verifici conexiunea la internet și să încerci din nou.';

  @override
  String get aboutOmi => 'Despre Omi';

  @override
  String get privacyPolicy => 'Politica de confidențialitate';

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
  String get integrations => 'Integrări';

  @override
  String get feedbackBug => 'Feedback / Eroare';

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
  String get wrapped2025 => 'Retrospectiva 2025';

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
  String get deviceUnpairedMessage =>
      'Dispozitiv deconectat. Mergeți la Setări > Bluetooth și uitați dispozitivul pentru a finaliza deconectarea.';

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
  String get noLogFilesFound => 'Nu s-au găsit fișiere jurnal.';

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
  String get deleteKnowledgeGraphMessage =>
      'Acest lucru va șterge toate datele derivate din graficul de cunoștințe (noduri și conexiuni). Amintirile tale originale vor rămâne în siguranță. Graficul va fi reconstruit în timp sau la următoarea solicitare.';

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
  String get authorizationBearer => 'Authorization: Bearer <cheie>';

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
  String get integrationsFooter => 'Conectează aplicațiile tale pentru a vizualiza date și statistici în chat.';

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
  String get refresh => 'Actualizează';

  @override
  String get noUpcomingMeetings => 'Nu există întâlniri viitoare';

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
  String get searchLanguageHint => 'Caută limba după nume sau cod';

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
  String get gotIt => 'Am înțeles';

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
  String get live => 'În direct';

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
  String get host => 'Gazdă';

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
  String deviceUsesCodec(String device, String reason) {
    return '$device folosește $reason. Omi va fi folosit.';
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
  String get appName => 'App Name';

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
  String get searchingForDevices => 'Se caută dispozitive...';

  @override
  String devicesFoundNearby(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'DISPOZITIVE',
      one: 'DISPOZITIV',
    );
    return '$count $_temp0 GĂSIT(E) ÎN APROPIERE';
  }

  @override
  String get pairingSuccessful => 'ÎMPERECHERE REUȘITĂ';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Error connecting to Apple Watch: $error';
  }

  @override
  String get dontShowAgain => 'Nu mai afișa';

  @override
  String get iUnderstand => 'Înțeleg';

  @override
  String get enableBluetooth => 'Enable Bluetooth';

  @override
  String get bluetoothNeeded =>
      'Omi needs Bluetooth to connect to your wearable. Please enable Bluetooth and try again.';

  @override
  String get contactSupport => 'Contactează suportul?';

  @override
  String get connectLater => 'Conectează mai târziu';

  @override
  String get grantPermissions => 'Acordați permisiuni';

  @override
  String get backgroundActivity => 'Activitate în fundal';

  @override
  String get backgroundActivityDesc => 'Let Omi run in the background for better stability';

  @override
  String get locationAccess => 'Acces la locație';

  @override
  String get locationAccessDesc => 'Activează locația în fundal pentru experiența completă';

  @override
  String get notifications => 'Notificări';

  @override
  String get notificationsDesc => 'Activează notificările pentru a fi informat';

  @override
  String get locationServiceDisabled => 'Serviciul de locație dezactivat';

  @override
  String get locationServiceDisabledDesc =>
      'Serviciul de locație este dezactivat. Te rugăm să mergi la Setări > Confidențialitate și securitate > Servicii de locație și să-l activezi';

  @override
  String get backgroundLocationDenied => 'Acces la locație în fundal refuzat';

  @override
  String get backgroundLocationDeniedDesc =>
      'Te rugăm să mergi la setările dispozitivului și să setezi permisiunea de locație la \"Permite întotdeauna\"';

  @override
  String get lovingOmi => 'Loving Omi?';

  @override
  String get leaveReviewIos =>
      'Ajută-ne să ajungem la mai mulți oameni lăsând o recenzie în App Store. Feedback-ul tău înseamnă enorm pentru noi!';

  @override
  String get leaveReviewAndroid =>
      'Help us reach more people by leaving a review in the Google Play Store. Your feedback means the world to us!';

  @override
  String get rateOnAppStore => 'Evaluează în App Store';

  @override
  String get rateOnGooglePlay => 'Rate on Google Play';

  @override
  String get maybeLater => 'Poate Mai Târziu';

  @override
  String get speechProfileIntro => 'Omi trebuie să învețe obiectivele și vocea ta. Vei putea să o modifici mai târziu.';

  @override
  String get getStarted => 'Începe';

  @override
  String get allDone => 'Totul e gata!';

  @override
  String get keepGoing => 'Continuă așa, te descurci excelent';

  @override
  String get skipThisQuestion => 'Sari peste această întrebare';

  @override
  String get skipForNow => 'Sari peste pentru moment';

  @override
  String get connectionError => 'Eroare de conexiune';

  @override
  String get connectionErrorDesc =>
      'Conectarea la server a eșuat. Te rugăm să verifici conexiunea la internet și să încerci din nou.';

  @override
  String get invalidRecordingMultipleSpeakers => 'Înregistrare invalidă detectată';

  @override
  String get multipleSpeakersDesc =>
      'Se pare că sunt mai mulți vorbitori în înregistrare. Te rugăm să te asiguri că ești într-un loc liniștit și să încerci din nou.';

  @override
  String get tooShortDesc => 'Nu s-a detectat suficientă vorbire. Te rugăm să vorbești mai mult și să încerci din nou.';

  @override
  String get invalidRecordingDesc => 'Te rugăm să te asiguri că vorbești cel puțin 5 secunde și nu mai mult de 90.';

  @override
  String get areYouThere => 'Ești acolo?';

  @override
  String get noSpeechDesc =>
      'Nu am putut detecta nicio vorbire. Te rugăm să vorbești cel puțin 10 secunde și nu mai mult de 3 minute.';

  @override
  String get connectionLost => 'Conexiune pierdută';

  @override
  String get connectionLostDesc =>
      'Conexiunea a fost întreruptă. Te rugăm să verifici conexiunea la internet și să încerci din nou.';

  @override
  String get tryAgain => 'Încearcă din nou';

  @override
  String get connectOmiOmiGlass => 'Connect Omi / OmiGlass';

  @override
  String get continueWithoutDevice => 'Continuă fără dispozitiv';

  @override
  String get permissionsRequired => 'Permisiuni necesare';

  @override
  String get permissionsRequiredDesc =>
      'This app needs Bluetooth and Location permissions to function properly. Please enable them in the settings.';

  @override
  String get openSettings => 'Deschide setările';

  @override
  String get wantDifferentName => 'Vrei să folosești alt nume?';

  @override
  String get whatsYourName => 'Cum te cheamă?';

  @override
  String get speakTranscribeSummarize => 'Vorbește. Transcrie. Rezumă.';

  @override
  String get signInWithApple => 'Sign in with Apple';

  @override
  String get signInWithGoogle => 'Sign in with Google';

  @override
  String get byContinuingAgree => 'Prin continuare, ești de acord cu ';

  @override
  String get termsOfUse => 'Termeni de utilizare';

  @override
  String get omiYourAiCompanion => 'Omi – Your AI Companion';

  @override
  String get captureEveryMoment => 'Capturează fiecare moment. Primește rezumate\ncu AI. Nu mai lua niciodată notițe.';

  @override
  String get appleWatchSetup => 'Apple Watch Setup';

  @override
  String get permissionRequestedExclaim => 'Permisiune solicitată!';

  @override
  String get microphonePermission => 'Permisiune microfon';

  @override
  String get permissionGrantedNow =>
      'Permission granted! Now:\n\nOpen the Omi app on your watch and tap \"Continue\" below';

  @override
  String get needMicrophonePermission =>
      'Avem nevoie de permisiunea microfonului.\n\n1. Apasă \"Acordă permisiunea\"\n2. Permite pe iPhone\n3. Aplicația de ceas se va închide\n4. Redeschide și apasă \"Continuă\"';

  @override
  String get grantPermissionButton => 'Acordă permisiunea';

  @override
  String get needHelp => 'Ai nevoie de ajutor?';

  @override
  String get troubleshootingSteps =>
      'Troubleshooting:\n\n1. Ensure Omi is installed on your watch\n2. Open the Omi app on your watch\n3. Look for the permission popup\n4. Tap \"Allow\" when prompted\n5. App on your watch will close - reopen it\n6. Come back and tap \"Continue\" on your iPhone';

  @override
  String get recordingStartedSuccessfully => 'Înregistrarea a început cu succes!';

  @override
  String get permissionNotGrantedYet =>
      'Permisiunea nu a fost acordată încă. Te rugăm să te asiguri că ai permis accesul la microfon și ai redeschis aplicația pe ceas.';

  @override
  String errorRequestingPermission(String error) {
    return 'Eroare la solicitarea permisiunii: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'Eroare la pornirea înregistrării: $error';
  }

  @override
  String get selectPrimaryLanguage => 'Selectează limba principală';

  @override
  String get languageBenefits => 'Setează-ți limba pentru transcrieri mai precise și o experiență personalizată';

  @override
  String get whatsYourPrimaryLanguage => 'Care este limba ta principală?';

  @override
  String get selectYourLanguage => 'Selectează limba ta';

  @override
  String get personalGrowthJourney => 'Călătoria ta de creștere personală cu AI care ascultă fiecare cuvânt al tău.';

  @override
  String get actionItemsTitle => 'De făcut';

  @override
  String get actionItemsDescription => 'Apasă pentru a edita • Apasă lung pentru a selecta • Glisează pentru acțiuni';

  @override
  String get tabToDo => 'De făcut';

  @override
  String get tabDone => 'Finalizate';

  @override
  String get tabOld => 'Vechi';

  @override
  String get emptyTodoMessage => '🎉 Totul e la zi!\nNiciun element de acțiune în așteptare';

  @override
  String get emptyDoneMessage => 'Niciun element finalizat încă';

  @override
  String get emptyOldMessage => '✅ Nicio sarcină veche';

  @override
  String get noItems => 'Niciun element';

  @override
  String get actionItemMarkedIncomplete => 'Element de acțiune marcat ca nefinalizat';

  @override
  String get actionItemCompleted => 'Element de acțiune finalizat';

  @override
  String get deleteActionItemTitle => 'Șterge elementul de acțiune';

  @override
  String get deleteActionItemMessage => 'Sunteți sigur că doriți să ștergeți acest element de acțiune?';

  @override
  String get deleteSelectedItemsTitle => 'Șterge elementele selectate';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Ești sigur că vrei să ștergi $count element(e) de acțiune selectat(e)?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'Elementul de acțiune \"$description\" a fost șters';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count element(e) de acțiune șters(e)';
  }

  @override
  String get failedToDeleteItem => 'Ștergerea elementului de acțiune a eșuat';

  @override
  String get failedToDeleteItems => 'Ștergerea elementelor a eșuat';

  @override
  String get failedToDeleteSomeItems => 'Ștergerea unor elemente a eșuat';

  @override
  String get welcomeActionItemsTitle => 'Pregătit pentru elemente de acțiune';

  @override
  String get welcomeActionItemsDescription =>
      'AI-ul tău va extrage automat sarcini și de făcut din conversațiile tale. Vor apărea aici când sunt create.';

  @override
  String get autoExtractionFeature => 'Extras automat din conversații';

  @override
  String get editSwipeFeature => 'Apasă pentru a edita, glisează pentru a finaliza sau șterge';

  @override
  String itemsSelected(int count) {
    return '$count selectat(e)';
  }

  @override
  String get selectAll => 'Selectează toate';

  @override
  String get deleteSelected => 'Șterge selecția';

  @override
  String get searchMemories => 'Caută amintiri...';

  @override
  String get memoryDeleted => 'Amintire ștearsă.';

  @override
  String get undo => 'Anulează';

  @override
  String get noMemoriesYet => '🧠 Încă nu există amintiri';

  @override
  String get noAutoMemories => 'Nicio amintire extrasă automat încă';

  @override
  String get noManualMemories => 'Nicio amintire manuală încă';

  @override
  String get noMemoriesInCategories => 'Nicio amintire în aceste categorii';

  @override
  String get noMemoriesFound => '🔍 Nu s-au găsit amintiri';

  @override
  String get addFirstMemory => 'Adaugă prima ta amintire';

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
  String get createMemoryTooltip => 'Creează amintire nouă';

  @override
  String get createActionItemTooltip => 'Creează element de acțiune nou';

  @override
  String get memoryManagement => 'Gestionare memorie';

  @override
  String get filterMemories => 'Filtrează amintirile';

  @override
  String totalMemoriesCount(int count) {
    return 'Ai $count amintiri în total';
  }

  @override
  String get publicMemories => 'Amintiri publice';

  @override
  String get privateMemories => 'Amintiri private';

  @override
  String get makeAllPrivate => 'Fă toate amintirile private';

  @override
  String get makeAllPublic => 'Fă toate amintirile publice';

  @override
  String get deleteAllMemories => 'Șterge toate amintirile';

  @override
  String get allMemoriesPrivateResult => 'Toate amintirile sunt acum private';

  @override
  String get allMemoriesPublicResult => 'Toate amintirile sunt acum publice';

  @override
  String get newMemory => '✨ Amintire nouă';

  @override
  String get editMemory => '✏️ Editează amintirea';

  @override
  String get memoryContentHint => 'Îmi place să mănânc înghețată...';

  @override
  String get failedToSaveMemory => 'Salvarea a eșuat. Te rugăm să verifici conexiunea.';

  @override
  String get saveMemory => 'Salvează amintirea';

  @override
  String get retry => 'Reîncearcă';

  @override
  String get createActionItem => 'Creează element de acțiune';

  @override
  String get editActionItem => 'Editează elementul de acțiune';

  @override
  String get actionItemDescriptionHint => 'Ce trebuie făcut?';

  @override
  String get actionItemDescriptionEmpty => 'Descrierea elementului de acțiune nu poate fi goală.';

  @override
  String get actionItemUpdated => 'Element de acțiune actualizat';

  @override
  String get failedToUpdateActionItem => 'Actualizarea elementului de acțiune a eșuat';

  @override
  String get actionItemCreated => 'Element de acțiune creat';

  @override
  String get failedToCreateActionItem => 'Crearea elementului de acțiune a eșuat';

  @override
  String get dueDate => 'Data scadentă';

  @override
  String get time => 'Timp';

  @override
  String get addDueDate => 'Adaugă dată limită';

  @override
  String get pressDoneToSave => 'Apasă gata pentru a salva';

  @override
  String get pressDoneToCreate => 'Apasă gata pentru a crea';

  @override
  String get filterAll => 'Toate';

  @override
  String get filterSystem => 'Despre tine';

  @override
  String get filterInteresting => 'Perspective';

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
  String get deleteActionItemConfirmTitle => 'Șterge elementul de acțiune';

  @override
  String get deleteActionItemConfirmMessage => 'Ești sigur că vrei să ștergi acest element de acțiune?';

  @override
  String get appLanguage => 'Limba aplicației';

  @override
  String get appInterfaceSectionTitle => 'INTERFAȚĂ APLICAȚIE';

  @override
  String get speechTranscriptionSectionTitle => 'VORBIRE ȘI TRANSCRIERE';

  @override
  String get languageSettingsHelperText =>
      'Limba aplicației schimbă meniurile și butoanele. Limba vorbirii afectează modul în care sunt transcrise înregistrările.';

  @override
  String get translationNotice => 'Notificare de traducere';

  @override
  String get translationNoticeMessage =>
      'Omi traduce conversațiile în limba ta principală. Actualizează-o oricând în Setări → Profiluri.';

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
  String get conversationCannotBeMerged =>
      'Această conversație nu poate fi fuzionată (blocată sau deja în curs de fuzionare)';

  @override
  String get pleaseEnterFolderName => 'Te rugăm să introduci un nume de dosar';

  @override
  String get failedToCreateFolder => 'Nu s-a putut crea dosarul';

  @override
  String get failedToUpdateFolder => 'Nu s-a putut actualiza dosarul';

  @override
  String get folderName => 'Nume dosar';

  @override
  String get descriptionOptional => 'Description (optional)';

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
  String get conversationUrlCouldNotBeShared => 'URL-ul conversației nu a putut fi distribuit.';

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
  String get generateSummary => 'Generează rezumat';

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
  String get unpairDeviceDialogMessage =>
      'Aceasta va deconecta dispozitivul astfel încât să poată fi conectat la un alt telefon. Va trebui să mergeți la Setări > Bluetooth și să uitați dispozitivul pentru a finaliza procesul.';

  @override
  String get unpair => 'Deconectează';

  @override
  String get unpairAndForgetDevice => 'Deconectează și uită dispozitivul';

  @override
  String get unknownDevice => 'Necunoscut';

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
    return '$label copiat';
  }

  @override
  String get noApiKeysYet => 'Încă nu există chei API. Creează una pentru a integra cu aplicația ta.';

  @override
  String get createKeyToGetStarted => 'Creează o cheie pentru a începe';

  @override
  String get persona => 'Personaj';

  @override
  String get configureYourAiPersona => 'Configurează-ți personajul AI';

  @override
  String get configureSttProvider => 'Configurare furnizor STT';

  @override
  String get setWhenConversationsAutoEnd => 'Setați când conversațiile se încheie automat';

  @override
  String get importDataFromOtherSources => 'Importă date din alte surse';

  @override
  String get debugAndDiagnostics => 'Depanare și diagnostice';

  @override
  String get autoDeletesAfter3Days => 'Ștergere automată după 3 zile';

  @override
  String get helpsDiagnoseIssues => 'Ajută la diagnosticarea problemelor';

  @override
  String get exportStartedMessage => 'Export început. Poate dura câteva secunde...';

  @override
  String get exportConversationsToJson => 'Exportă conversațiile într-un fișier JSON';

  @override
  String get knowledgeGraphDeletedSuccess => 'Graful de cunoștințe a fost șters cu succes';

  @override
  String failedToDeleteGraph(String error) {
    return 'Nu s-a putut șterge graful: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'Șterge toate nodurile și conexiunile';

  @override
  String get addToClaudeDesktopConfig => 'Adaugă la claude_desktop_config.json';

  @override
  String get connectAiAssistantsToData => 'Conectează asistenții AI la datele tale';

  @override
  String get useYourMcpApiKey => 'Folosește cheia ta API MCP';

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
  String get autoCreateWhenNameDetected => 'Creare automată când se detectează un nume';

  @override
  String get followUpQuestions => 'Întrebări de urmărire';

  @override
  String get suggestQuestionsAfterConversations => 'Sugerați întrebări după conversații';

  @override
  String get goalTracker => 'Urmăritor de obiective';

  @override
  String get trackPersonalGoalsOnHomepage => 'Urmărește-ți obiectivele personale pe pagina principală';

  @override
  String get dailyReflection => 'Reflecție zilnică';

  @override
  String get get9PmReminderToReflect => 'Primește o reamintire la ora 21 pentru a reflecta asupra zilei tale';

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
  String get sdCardSyncDescription =>
      'Sincronizarea cardului SD va importa amintirile tale de pe cardul SD în aplicație';

  @override
  String get checksForAudioFiles => 'Verifică fișierele audio de pe cardul SD';

  @override
  String get omiSyncsAudioFiles => 'Omi apoi sincronizează fișierele audio cu serverul';

  @override
  String get serverProcessesAudio => 'Serverul procesează fișierele audio și creează amintiri';

  @override
  String get youreAllSet => 'Sunteți gata!';

  @override
  String get welcomeToOmiDescription =>
      'Bun venit la Omi! Companionul tău AI este gata să te ajute cu conversații, sarcini și multe altele.';

  @override
  String get startUsingOmi => 'Începeți să folosiți Omi';

  @override
  String get back => 'Înapoi';

  @override
  String get keyboardShortcuts => 'Comenzi Rapide';

  @override
  String get toggleControlBar => 'Comută bara de control';

  @override
  String get pressKeys => 'Apăsați tastele...';

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
  String get goalTitle => 'Titlul obiectivului';

  @override
  String get current => 'Curent';

  @override
  String get target => 'Țintă';

  @override
  String get saveGoal => 'Salvează';

  @override
  String get goals => 'Obiective';

  @override
  String get tapToAddGoal => 'Atinge pentru a adăuga un obiectiv';

  @override
  String welcomeBack(String name) {
    return 'Bine ai revenit, $name';
  }

  @override
  String get yourConversations => 'Conversațiile tale';

  @override
  String get reviewAndManageConversations => 'Revizuiește și gestionează conversațiile înregistrate';

  @override
  String get startCapturingConversations =>
      'Începe să capturezi conversații cu dispozitivul Omi pentru a le vedea aici.';

  @override
  String get useMobileAppToCapture => 'Folosește aplicația mobilă pentru a captura audio';

  @override
  String get conversationsProcessedAutomatically => 'Conversațiile sunt procesate automat';

  @override
  String get getInsightsInstantly => 'Obține informații și rezumate instantaneu';

  @override
  String get showAll => 'Arată tot →';

  @override
  String get noTasksForToday =>
      'Nicio sarcină pentru astăzi.\\nÎntrebați Omi pentru mai multe sarcini sau creați manual.';

  @override
  String get dailyScore => 'SCOR ZILNIC';

  @override
  String get dailyScoreDescription => 'Un scor care te ajută să te\nconcentrezi mai bine pe execuție.';

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
  String get tasksFromConversationsWillAppear =>
      'Sarcinile din conversațiile dvs. vor apărea aici.\nFaceți clic pe Creați pentru a adăuga una manual.';

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
  String get deleteActionItemConfirmation =>
      'Sigur doriți să ștergeți acest element de acțiune? Această acțiune nu poate fi anulată.';

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
  String get pleaseCheckInternetConnectionAndTryAgain =>
      'Vă rugăm să verificați conexiunea la internet și să încercați din nou';

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
  String get chatPromptPlaceholder =>
      'Ești o aplicație grozavă, treaba ta este să răspunzi la întrebările utilizatorilor și să-i faci să se simtă bine...';

  @override
  String get conversationPrompt => 'Prompt de conversație';

  @override
  String get conversationPromptPlaceholder =>
      'Ești o aplicație grozavă, vei primi o transcriere și un rezumat al unei conversații...';

  @override
  String get notificationScopes => 'Domenii de Notificare';

  @override
  String get appPrivacyAndTerms => 'Confidențialitate și Termeni Aplicație';

  @override
  String get makeMyAppPublic => 'Fă aplicația mea publică';

  @override
  String get submitAppTermsAgreement =>
      'Prin trimiterea acestei aplicații, sunt de acord cu Termenii de Serviciu și Politica de Confidențialitate Omi AI';

  @override
  String get submitApp => 'Trimite Aplicația';

  @override
  String get needHelpGettingStarted => 'Ai nevoie de ajutor pentru a începe?';

  @override
  String get clickHereForAppBuildingGuides => 'Dă clic aici pentru ghiduri de creare aplicații și documentație';

  @override
  String get submitAppQuestion => 'Trimite Aplicația?';

  @override
  String get submitAppPublicDescription =>
      'Aplicația ta va fi revizuită și făcută publică. Poți începe să o folosești imediat, chiar și în timpul reviziei!';

  @override
  String get submitAppPrivateDescription =>
      'Aplicația ta va fi revizuită și pusă la dispoziția ta în mod privat. Poți începe să o folosești imediat, chiar și în timpul reviziei!';

  @override
  String get startEarning => 'Începe să Câștigi! 💰';

  @override
  String get connectStripeOrPayPal => 'Conectează Stripe sau PayPal pentru a primi plăți pentru aplicația ta.';

  @override
  String get connectNow => 'Conectează Acum';

  @override
  String get installsCount => 'Instalări';

  @override
  String get uninstallApp => 'Dezinstalează aplicația';

  @override
  String get subscribe => 'Abonează-te';

  @override
  String get dataAccessNotice => 'Notificare acces la date';

  @override
  String get dataAccessWarning =>
      'Această aplicație va accesa datele dvs. Omi AI nu este responsabil pentru modul în care datele dvs. sunt utilizate, modificate sau șterse de această aplicație';

  @override
  String get installApp => 'Instalează aplicația';

  @override
  String get betaTesterNotice =>
      'Ești tester beta pentru această aplicație. Nu este încă publică. Va fi publică odată ce va fi aprobată.';

  @override
  String get appUnderReviewOwner =>
      'Aplicația ta este în curs de revizuire și vizibilă doar pentru tine. Va fi publică odată ce va fi aprobată.';

  @override
  String get appRejectedNotice =>
      'Aplicația ta a fost respinsă. Te rugăm să actualizezi detaliile aplicației și să o trimiți din nou pentru revizuire.';

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
  String get aboutThePersona => 'Despre persona';

  @override
  String get chatPersonality => 'Personalitate chat';

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
  String get integrationSetupRequired =>
      'Dacă aceasta este o aplicație de integrare, asigurați-vă că configurarea este completă.';

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
  String get appDescriptionPlaceholder =>
      'Aplicația mea minunată este o aplicație grozavă care face lucruri uimitoare. Este cea mai bună aplicație!';

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
  String get takePhoto => 'Fă o poză';

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
  String get microphonePermissionDenied =>
      'Permisiunea microfonului refuzată. Vă rugăm să acordați permisiunea în Preferințe sistem > Confidențialitate și securitate > Microfon.';

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
  String get discardedConversation => 'Conversație eliminată';

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
  String get chat => 'Conversație';

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
  String get getOmiDevice => 'Get Omi Device';

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
  String get deleteMemoryConfirmation =>
      'Ești sigur că vrei să ștergi această amintire? Această acțiune nu poate fi anulată.';

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
  String get dataCollectionMessage =>
      'Continuând, conversațiile, înregistrările și informațiile personale vor fi stocate în siguranță pe serverele noastre pentru a oferi informații alimentate de AI și a activa toate funcțiile aplicației.';

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
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'Spuneți-ne cum doriți să fiți adresat. Acest lucru ajută la personalizarea experienței Omi.';

  @override
  String charactersCount(int count) {
    return '$count caractere';
  }

  @override
  String get enableFeaturesForBestExperience =>
      'Activați funcțiile pentru cea mai bună experiență Omi pe dispozitivul dvs.';

  @override
  String get microphoneAccess => 'Acces la microfon';

  @override
  String get recordAudioConversations => 'Înregistrați conversații audio';

  @override
  String get microphoneAccessDescription =>
      'Omi are nevoie de acces la microfon pentru a înregistra conversațiile dvs. și a furniza transcripții.';

  @override
  String get screenRecording => 'Înregistrare ecran';

  @override
  String get captureSystemAudioFromMeetings => 'Capturați audio-ul sistemului din întâlniri';

  @override
  String get screenRecordingDescription =>
      'Omi are nevoie de permisiune de înregistrare a ecranului pentru a captura audio-ul sistemului din întâlnirile dvs. bazate pe browser.';

  @override
  String get accessibility => 'Accesibilitate';

  @override
  String get detectBrowserBasedMeetings => 'Detectați întâlnirile bazate pe browser';

  @override
  String get accessibilityDescription =>
      'Omi are nevoie de permisiune de accesibilitate pentru a detecta când vă alăturați întâlnirilor Zoom, Meet sau Teams în browser-ul dvs.';

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
  String get conversationsExportStarted =>
      'Export conversații pornit. Aceasta poate dura câteva secunde, vă rugăm așteptați.';

  @override
  String get mcpDescription =>
      'Pentru a conecta Omi cu alte aplicații pentru a citi, căuta și gestiona amintirile și conversațiile dvs. Creați o cheie pentru a începe.';

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
  String get enableDetailedDiagnosticMessages =>
      'Activați mesajele de diagnostic detaliate de la serviciul de transcriere';

  @override
  String get autoCreateAndTagNewSpeakers => 'Creați și etich etați automat vorbitori noi';

  @override
  String get automaticallyCreateNewPerson =>
      'Creați automat o persoană nouă când un nume este detectat în transcriere.';

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
  String get noSummaryForApp =>
      'Nu există rezumat disponibil pentru această aplicație. Încearcă altă aplicație pentru rezultate mai bune.';

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
  String get deleteConversationConfirmation =>
      'Sigur doriți să ștergeți această conversație? Această acțiune nu poate fi anulată.';

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
  String get clickTheButtonToCaptureAudio =>
      'Faceți clic pe buton pentru a captura audio pentru transcrieri live, informații AI și salvare automată.';

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
  String get dailySummary => 'Rezumat zilnic';

  @override
  String get developer => 'Dezvoltator';

  @override
  String get about => 'Despre';

  @override
  String get selectTime => 'Selectează ora';

  @override
  String get accountGroup => 'Cont';

  @override
  String get signOutQuestion => 'Deconectare?';

  @override
  String get signOutConfirmation => 'Ești sigur că vrei să te deconectezi?';

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
  String get dailySummaryDescription => 'Primește un rezumat personalizat al conversațiilor zilei ca notificare.';

  @override
  String get deliveryTime => 'Ora livrării';

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
  String get upcomingMeetings => 'Întâlniri viitoare';

  @override
  String get checkingNext7Days => 'Verificarea următoarelor 7 zile';

  @override
  String get shortcuts => 'Comenzi rapide';

  @override
  String get shortcutChangeInstruction =>
      'Faceți clic pe o comandă rapidă pentru a o modifica. Apăsați Escape pentru a anula.';

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
  String get exportingConversations => 'Se exportă conversațiile...';

  @override
  String get clearNodesDescription => 'Ștergeți toate nodurile și conexiunile';

  @override
  String get deleteKnowledgeGraphQuestion => 'Ștergeți graficul de cunoștințe?';

  @override
  String get deleteKnowledgeGraphWarning =>
      'Aceasta va șterge toate datele derivate din graficul de cunoștințe. Amintirile dvs. originale rămân în siguranță.';

  @override
  String get connectOmiWithAI => 'Conectați Omi cu asistenți AI';

  @override
  String get noAPIKeys => 'Nicio cheie API. Creați una pentru a începe.';

  @override
  String get autoCreateWhenDetected => 'Creați automat când numele este detectat';

  @override
  String get trackPersonalGoals => 'Urmăriți obiective personale pe pagina de pornire';

  @override
  String get dailyReflectionDescription =>
      'Primește un memento la ora 21 pentru a reflecta asupra zilei și a-ți nota gândurile.';

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
  String get updateAppConfirmation =>
      'Sunteți sigur că doriți să actualizați aplicația? Modificările vor fi vizibile după examinarea de către echipa noastră.';

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
  String get subscriptionCancelledSuccessfully =>
      'Abonament anulat cu succes. Va rămâne activ până la sfârșitul perioadei curente de facturare.';

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
  String get cancelSubscriptionConfirmation =>
      'Sunteți sigur că doriți să vă anulați abonamentul? Veți avea în continuare acces până la sfârșitul perioadei curente de facturare.';

  @override
  String get cancelSubscriptionButton => 'Anulare abonament';

  @override
  String get cancelling => 'Se anulează...';

  @override
  String get betaTesterMessage =>
      'Sunteți un tester beta pentru această aplicație. Nu este încă publică. Va fi publică după aprobare.';

  @override
  String get appUnderReviewMessage =>
      'Aplicația dvs. este în curs de examinare și vizibilă doar pentru dvs. Va fi publică după aprobare.';

  @override
  String get appRejectedMessage =>
      'Aplicația dvs. a fost respinsă. Actualizați detaliile și retrimiteți pentru examinare.';

  @override
  String get invalidIntegrationUrl => 'URL de integrare invalid';

  @override
  String get tapToComplete => 'Atinge pentru a finaliza';

  @override
  String get invalidSetupInstructionsUrl => 'URL instrucțiuni de configurare invalid';

  @override
  String get pushToTalk => 'Apasă pentru a vorbi';

  @override
  String get summaryPrompt => 'Prompt rezumat';

  @override
  String get pleaseSelectARating => 'Vă rugăm să selectați o evaluare';

  @override
  String get reviewAddedSuccessfully => 'Recenzie adăugată cu succes 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'Recenzie actualizată cu succes 🚀';

  @override
  String get failedToSubmitReview => 'Nu s-a putut trimite recenzia. Te rugăm să încerci din nou.';

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
  String get dataAccessNoticeDescription =>
      'This app will access your data. Omi AI is not responsible for how your data is used, modified, or deleted by this app';

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
  String get apiKeysDescription =>
      'Cheile API sunt folosite pentru autentificare atunci când aplicația ta comunică cu serverul OMI. Ele permit aplicației tale să creeze amintiri și să acceseze alte servicii OMI în siguranță.';

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
  String get revokeApiKeyWarning =>
      'Această acțiune nu poate fi anulată. Orice aplicații care folosesc această cheie nu vor mai putea accesa API-ul.';

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
  String get itemPersona => 'Personaj';

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
  String get externalAppAccessDescription =>
      'Următoarele aplicații instalate au integrări externe și pot accesa datele tale, cum ar fi conversațiile și amintirile.';

  @override
  String get noExternalAppsHaveAccess => 'Nicio aplicație externă nu are acces la datele tale.';

  @override
  String get maximumSecurityE2ee => 'Securitate maximă (E2EE)';

  @override
  String get e2eeDescription =>
      'Criptarea end-to-end este standardul de aur pentru confidențialitate. Când este activată, datele dvs. sunt criptate pe dispozitivul dvs. înainte de a fi trimise la serverele noastre. Aceasta înseamnă că nimeni, nici măcar Omi, nu poate accesa conținutul dvs.';

  @override
  String get importantTradeoffs => 'Compromisuri importante:';

  @override
  String get e2eeTradeoff1 => '• Unele funcții precum integrările cu aplicații externe pot fi dezactivate.';

  @override
  String get e2eeTradeoff2 => '• Dacă pierdeți parola, datele dvs. nu pot fi recuperate.';

  @override
  String get featureComingSoon => 'Această funcție va fi disponibilă în curând!';

  @override
  String get migrationInProgressMessage =>
      'Migrație în curs. Nu puteți schimba nivelul de protecție până la finalizare.';

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
  String get secureEncryptionDescription =>
      'Datele dvs. sunt criptate cu o cheie unică pentru dvs. pe serverele noastre, găzduite pe Google Cloud. Aceasta înseamnă că conținutul dvs. brut este inaccesibil pentru oricine, inclusiv personalul Omi sau Google, direct din baza de date.';

  @override
  String get endToEndEncryption => 'Criptare end-to-end';

  @override
  String get e2eeCardDescription =>
      'Activați pentru securitate maximă, unde doar dvs. puteți accesa datele dvs. Atingeți pentru a afla mai multe.';

  @override
  String get dataAlwaysEncrypted =>
      'Indiferent de nivel, datele dvs. sunt întotdeauna criptate în repaus și în tranzit.';

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
  String get omiTraining => 'Instruire Omi';

  @override
  String get trainingDataProgram => 'Program de date de antrenament';

  @override
  String get getOmiUnlimitedFree =>
      'Obțineți Omi Unlimited gratuit contribuind cu datele dvs. pentru antrenarea modelelor AI.';

  @override
  String get trainingDataBullets =>
      '• Datele dvs. ajută la îmbunătățirea modelelor AI\n• Sunt partajate doar date nesensibile\n• Proces complet transparent';

  @override
  String get learnMoreAtOmiTraining => 'Aflați mai multe la omi.me/training';

  @override
  String get agreeToContributeData => 'Înțeleg și sunt de acord să contribui cu datele mele pentru antrenarea AI';

  @override
  String get submitRequest => 'Trimite cererea';

  @override
  String get thankYouRequestUnderReview =>
      'Mulțumim! Cererea dvs. este în curs de examinare. Vă vom notifica după aprobare.';

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
  String get paymentMethodCharged =>
      'Metoda dvs. de plată existentă va fi debitată automat când planul lunar se încheie';

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
  String get privacyIntroText =>
      'La Omi, luăm foarte în serios confidențialitatea ta. Vrem să fim transparenți despre datele pe care le colectăm și cum le folosim. Iată ce trebuie să știi:';

  @override
  String get whatWeTrack => 'Ce urmărim';

  @override
  String get anonymityAndPrivacy => 'Anonimat și confidențialitate';

  @override
  String get optInAndOptOutOptions => 'Opțiuni de acceptare și refuz';

  @override
  String get ourCommitment => 'Angajamentul nostru';

  @override
  String get commitmentText =>
      'Ne angajăm să folosim datele pe care le colectăm doar pentru a face Omi un produs mai bun pentru tine. Confidențialitatea și încrederea ta sunt primordiale pentru noi.';

  @override
  String get thankYouText =>
      'Îți mulțumim că ești un utilizator valoros al Omi. Dacă ai întrebări sau nelămuriri, nu ezita să ne contactezi la team@basedhardware.com.';

  @override
  String get wifiSyncSettings => 'Setări sincronizare WiFi';

  @override
  String get enterHotspotCredentials => 'Introduceți datele hotspot-ului telefonului';

  @override
  String get wifiSyncUsesHotspot =>
      'Sincronizarea WiFi folosește telefonul ca hotspot. Găsește numele și parola în Setări > Hotspot personal.';

  @override
  String get hotspotNameSsid => 'Nume hotspot (SSID)';

  @override
  String get exampleIphoneHotspot => 'ex. iPhone Hotspot';

  @override
  String get password => 'Parolă';

  @override
  String get enterHotspotPassword => 'Introduceți parola hotspot';

  @override
  String get saveCredentials => 'Salvează datele de autentificare';

  @override
  String get clearCredentials => 'Șterge datele de autentificare';

  @override
  String get pleaseEnterHotspotName => 'Vă rugăm introduceți un nume de hotspot';

  @override
  String get wifiCredentialsSaved => 'Datele WiFi au fost salvate';

  @override
  String get wifiCredentialsCleared => 'Datele WiFi au fost șterse';

  @override
  String summaryGeneratedForDate(String date) {
    return 'Rezumat generat pentru $date';
  }

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'Nu s-a putut genera rezumatul. Asigură-te că ai conversații pentru acea zi.';

  @override
  String get summaryNotFound => 'Rezumatul nu a fost găsit';

  @override
  String get yourDaysJourney => 'Călătoria zilei tale';

  @override
  String get highlights => 'Evidențieri';

  @override
  String get unresolvedQuestions => 'Întrebări nerezolvate';

  @override
  String get decisions => 'Decizii';

  @override
  String get learnings => 'Învățăminte';

  @override
  String get autoDeletesAfterThreeDays => 'Se șterge automat după 3 zile.';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'Graficul cunoștințelor șters cu succes';

  @override
  String get exportStartedMayTakeFewSeconds => 'Export început. Poate dura câteva secunde...';

  @override
  String get knowledgeGraphDeleteDescription =>
      'Aceasta va șterge toate datele derivate ale graficului cunoștințelor (noduri și conexiuni). Amintirile tale originale vor rămâne în siguranță. Graficul va fi reconstruit în timp sau la următoarea solicitare.';

  @override
  String get configureDailySummaryDigest => 'Configurați rezumatul zilnic al sarcinilor';

  @override
  String accessesDataTypes(String dataTypes) {
    return 'Accesează $dataTypes';
  }

  @override
  String triggeredByType(String triggerType) {
    return 'declanșat de $triggerType';
  }

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription și este $triggerDescription.';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return 'Este $triggerDescription.';
  }

  @override
  String get noSpecificDataAccessConfigured => 'Niciun acces specific la date configurat.';

  @override
  String get basicPlanDescription => '1.200 minute premium + nelimitat pe dispozitiv';

  @override
  String get minutes => 'minute';

  @override
  String get omiHas => 'Omi are:';

  @override
  String get premiumMinutesUsed => 'Minute premium utilizate.';

  @override
  String get setupOnDevice => 'Configurare pe dispozitiv';

  @override
  String get forUnlimitedFreeTranscription => 'pentru transcriere gratuită nelimitată.';

  @override
  String premiumMinsLeft(int count) {
    return '$count minute premium rămase.';
  }

  @override
  String get alwaysAvailable => 'întotdeauna disponibil.';

  @override
  String get importHistory => 'Istoric importuri';

  @override
  String get noImportsYet => 'Niciun import încă';

  @override
  String get selectZipFileToImport => 'Selectați fișierul .zip pentru import!';

  @override
  String get otherDevicesComingSoon => 'Alte dispozitive în curând';

  @override
  String get deleteAllLimitlessConversations => 'Ștergeți toate conversațiile Limitless?';

  @override
  String get deleteAllLimitlessWarning =>
      'Aceasta va șterge permanent toate conversațiile importate din Limitless. Această acțiune nu poate fi anulată.';

  @override
  String deletedLimitlessConversations(int count) {
    return 'Șterse $count conversații Limitless';
  }

  @override
  String get failedToDeleteConversations => 'Ștergerea conversațiilor a eșuat';

  @override
  String get deleteImportedData => 'Șterge datele importate';

  @override
  String get statusPending => 'În așteptare';

  @override
  String get statusProcessing => 'Se procesează';

  @override
  String get statusCompleted => 'Finalizat';

  @override
  String get statusFailed => 'Eșuat';

  @override
  String nConversations(int count) {
    return '$count conversații';
  }

  @override
  String get pleaseEnterName => 'Vă rugăm să introduceți un nume';

  @override
  String get nameMustBeBetweenCharacters => 'Numele trebuie să aibă între 2 și 40 de caractere';

  @override
  String get deleteSampleQuestion => 'Ștergeți eșantionul?';

  @override
  String deleteSampleConfirmation(String name) {
    return 'Sigur doriți să ștergeți eșantionul lui $name?';
  }

  @override
  String get confirmDeletion => 'Confirmați ștergerea';

  @override
  String deletePersonConfirmation(String name) {
    return 'Sigur doriți să ștergeți $name? Acest lucru va elimina și toate eșantioanele vocale asociate.';
  }

  @override
  String get howItWorksTitle => 'Cum funcționează?';

  @override
  String get howPeopleWorks =>
      'Odată ce o persoană este creată, puteți merge la transcripția unei conversații și să le atribuiți segmentele corespunzătoare, astfel Omi va putea recunoaște și vocea lor!';

  @override
  String get tapToDelete => 'Atingeți pentru a șterge';

  @override
  String get newTag => 'NOU';

  @override
  String get needHelpChatWithUs => 'Aveți nevoie de ajutor? Discutați cu noi';

  @override
  String get localStorageEnabled => 'Stocare locală activată';

  @override
  String get localStorageDisabled => 'Stocare locală dezactivată';

  @override
  String failedToUpdateSettings(String error) {
    return 'Actualizarea setărilor a eșuat: $error';
  }

  @override
  String get privacyNotice => 'Notificare de confidențialitate';

  @override
  String get recordingsMayCaptureOthers =>
      'Înregistrările pot captura vocile altora. Asigurați-vă că aveți consimțământul tuturor participanților înainte de activare.';

  @override
  String get enable => 'Activează';

  @override
  String get storeAudioOnPhone => 'Stochează audio pe telefon';

  @override
  String get on => 'Pornit';

  @override
  String get storeAudioDescription =>
      'Păstrați toate înregistrările audio stocate local pe telefon. Când este dezactivat, doar încărcările eșuate sunt păstrate pentru a economisi spațiu.';

  @override
  String get enableLocalStorage => 'Activare stocare locală';

  @override
  String get cloudStorageEnabled => 'Stocare în cloud activată';

  @override
  String get cloudStorageDisabled => 'Stocare în cloud dezactivată';

  @override
  String get enableCloudStorage => 'Activare stocare în cloud';

  @override
  String get storeAudioOnCloud => 'Stochează audio în cloud';

  @override
  String get cloudStorageDialogMessage =>
      'Înregistrările dvs. în timp real vor fi stocate în spațiul de stocare cloud privat în timp ce vorbiți.';

  @override
  String get storeAudioCloudDescription =>
      'Stocați înregistrările în timp real în spațiul de stocare cloud privat în timp ce vorbiți. Audio este capturat și salvat în siguranță în timp real.';

  @override
  String get downloadingFirmware => 'Se descarcă firmware-ul';

  @override
  String get installingFirmware => 'Se instalează firmware-ul';

  @override
  String get firmwareUpdateWarning =>
      'Nu închideți aplicația și nu opriți dispozitivul. Acest lucru ar putea deteriora dispozitivul.';

  @override
  String get firmwareUpdated => 'Firmware actualizat';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'Vă rugăm să reporniți $deviceName pentru a finaliza actualizarea.';
  }

  @override
  String get yourDeviceIsUpToDate => 'Dispozitivul dvs. este actualizat';

  @override
  String get currentVersion => 'Versiunea curentă';

  @override
  String get latestVersion => 'Ultima versiune';

  @override
  String get whatsNew => 'Ce este nou';

  @override
  String get installUpdate => 'Instalează actualizarea';

  @override
  String get updateNow => 'Actualizează acum';

  @override
  String get updateGuide => 'Ghid de actualizare';

  @override
  String get checkingForUpdates => 'Se verifică actualizările';

  @override
  String get checkingFirmwareVersion => 'Se verifică versiunea firmware-ului...';

  @override
  String get firmwareUpdate => 'Actualizare firmware';

  @override
  String get payments => 'Plăți';

  @override
  String get connectPaymentMethodInfo =>
      'Conectați o metodă de plată mai jos pentru a începe să primiți plăți pentru aplicațiile dvs.';

  @override
  String get selectedPaymentMethod => 'Metodă de plată selectată';

  @override
  String get availablePaymentMethods => 'Metode de plată disponibile';

  @override
  String get activeStatus => 'Activ';

  @override
  String get connectedStatus => 'Conectat';

  @override
  String get notConnectedStatus => 'Neconectat';

  @override
  String get setActive => 'Setează ca activ';

  @override
  String get getPaidThroughStripe => 'Primiți plăți pentru vânzările aplicațiilor prin Stripe';

  @override
  String get monthlyPayouts => 'Plăți lunare';

  @override
  String get monthlyPayoutsDescription => 'Primiți plăți lunare direct în cont când atingeți \$10 în câștiguri';

  @override
  String get secureAndReliable => 'Sigur și de încredere';

  @override
  String get stripeSecureDescription => 'Stripe asigură transferuri sigure și la timp ale veniturilor aplicației dvs.';

  @override
  String get selectYourCountry => 'Selectați țara dvs.';

  @override
  String get countrySelectionPermanent => 'Selecția țării este permanentă și nu poate fi modificată ulterior.';

  @override
  String get byClickingConnectNow => 'Făcând clic pe \"Conectați acum\" sunteți de acord cu';

  @override
  String get stripeConnectedAccountAgreement => 'Acordul contului conectat Stripe';

  @override
  String get errorConnectingToStripe => 'Eroare la conectarea la Stripe! Vă rugăm să încercați din nou mai târziu.';

  @override
  String get connectingYourStripeAccount => 'Conectarea contului dvs. Stripe';

  @override
  String get stripeOnboardingInstructions =>
      'Vă rugăm să finalizați procesul de integrare Stripe în browserul dvs. Această pagină se va actualiza automat după finalizare.';

  @override
  String get failedTryAgain => 'A eșuat? Încercați din nou';

  @override
  String get illDoItLater => 'Voi face mai târziu';

  @override
  String get successfullyConnected => 'Conectat cu succes!';

  @override
  String get stripeReadyForPayments =>
      'Contul dvs. Stripe este acum gata să primească plăți. Puteți începe să câștigați din vânzările aplicațiilor imediat.';

  @override
  String get updateStripeDetails => 'Actualizați detaliile Stripe';

  @override
  String get errorUpdatingStripeDetails =>
      'Eroare la actualizarea detaliilor Stripe! Vă rugăm să încercați din nou mai târziu.';

  @override
  String get updatePayPal => 'Actualizați PayPal';

  @override
  String get setUpPayPal => 'Configurați PayPal';

  @override
  String get updatePayPalAccountDetails => 'Actualizați detaliile contului dvs. PayPal';

  @override
  String get connectPayPalToReceivePayments =>
      'Conectați contul dvs. PayPal pentru a începe să primiți plăți pentru aplicațiile dvs.';

  @override
  String get paypalEmail => 'E-mail PayPal';

  @override
  String get paypalMeLink => 'Link PayPal.me';

  @override
  String get stripeRecommendation =>
      'Dacă Stripe este disponibil în țara dvs., vă recomandăm cu tărie să îl utilizați pentru plăți mai rapide și mai ușoare.';

  @override
  String get updatePayPalDetails => 'Actualizați detaliile PayPal';

  @override
  String get savePayPalDetails => 'Salvați detaliile PayPal';

  @override
  String get pleaseEnterPayPalEmail => 'Vă rugăm să introduceți e-mailul PayPal';

  @override
  String get pleaseEnterPayPalMeLink => 'Vă rugăm să introduceți linkul PayPal.me';

  @override
  String get doNotIncludeHttpInLink => 'Nu includeți http sau https sau www în link';

  @override
  String get pleaseEnterValidPayPalMeLink => 'Vă rugăm să introduceți un link PayPal.me valid';

  @override
  String get pleaseEnterValidEmail => 'Vă rugăm să introduceți o adresă de email validă';

  @override
  String get syncingYourRecordings => 'Sincronizarea înregistrărilor tale';

  @override
  String get syncYourRecordings => 'Sincronizează înregistrările tale';

  @override
  String get syncNow => 'Sincronizează acum';

  @override
  String get error => 'Eroare';

  @override
  String get speechSamples => 'Mostre vocale';

  @override
  String additionalSampleIndex(String index) {
    return 'Mostră suplimentară $index';
  }

  @override
  String durationSeconds(String seconds) {
    return 'Durată: $seconds secunde';
  }

  @override
  String get additionalSpeechSampleRemoved => 'Mostră vocală suplimentară eliminată';

  @override
  String get consentDataMessage =>
      'Continuând, toate datele pe care le partajați cu această aplicație (inclusiv conversațiile, înregistrările și informațiile personale) vor fi stocate în siguranță pe serverele noastre pentru a vă oferi informații bazate pe IA și pentru a activa toate funcțiile aplicației.';

  @override
  String get tasksEmptyStateMessage =>
      'Sarcinile din conversațiile tale vor apărea aici.\nAtinge + pentru a crea una manual.';

  @override
  String get clearChatAction => 'Șterge conversația';

  @override
  String get enableApps => 'Activează aplicațiile';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => 'arată mai mult ↓';

  @override
  String get showLess => 'arată mai puțin ↑';

  @override
  String get loadingYourRecording => 'Se încarcă înregistrarea...';

  @override
  String get photoDiscardedMessage => 'Această fotografie a fost eliminată deoarece nu era semnificativă.';

  @override
  String get analyzing => 'Se analizează...';

  @override
  String get searchCountries => 'Căutați țări...';

  @override
  String get checkingAppleWatch => 'Se verifică Apple Watch...';

  @override
  String get installOmiOnAppleWatch => 'Instalează Omi pe\nApple Watch';

  @override
  String get installOmiOnAppleWatchDescription =>
      'Pentru a utiliza Apple Watch cu Omi, trebuie să instalezi mai întâi aplicația Omi pe ceas.';

  @override
  String get openOmiOnAppleWatch => 'Deschide Omi pe\nApple Watch';

  @override
  String get openOmiOnAppleWatchDescription =>
      'Aplicația Omi este instalată pe Apple Watch. Deschide-o și apasă Start pentru a începe.';

  @override
  String get openWatchApp => 'Deschide aplicația Watch';

  @override
  String get iveInstalledAndOpenedTheApp => 'Am instalat și deschis aplicația';

  @override
  String get unableToOpenWatchApp =>
      'Nu se poate deschide aplicația Apple Watch. Deschide manual aplicația Watch pe Apple Watch și instalează Omi din secțiunea \"Aplicații disponibile\".';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch conectat cu succes!';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch încă nu este accesibil. Asigură-te că aplicația Omi este deschisă pe ceas.';

  @override
  String errorCheckingConnection(String error) {
    return 'Eroare la verificarea conexiunii: $error';
  }

  @override
  String get muted => 'Dezactivat';

  @override
  String get processNow => 'Procesează acum';

  @override
  String get finishedConversation => 'Conversație terminată?';

  @override
  String get stopRecordingConfirmation => 'Sigur doriți să opriți înregistrarea și să rezumați conversația acum?';

  @override
  String get conversationEndsManually => 'Conversația se va încheia doar manual.';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'Conversația este rezumată după $minutes minut$suffix de tăcere.';
  }

  @override
  String get dontAskAgain => 'Nu mai întreba';

  @override
  String get waitingForTranscriptOrPhotos => 'Se așteaptă transcriere sau fotografii...';

  @override
  String get noSummaryYet => 'Încă nu există rezumat';

  @override
  String hints(String text) {
    return 'Indicii: $text';
  }

  @override
  String get testConversationPrompt => 'Testează un prompt de conversație';

  @override
  String get prompt => 'Prompt';

  @override
  String get result => 'Rezultat:';

  @override
  String get compareTranscripts => 'Compară transcrierile';

  @override
  String get notHelpful => 'Nu a fost util';

  @override
  String get exportTasksWithOneTap => 'Exportă sarcinile cu o singură atingere!';

  @override
  String get inProgress => 'În curs';

  @override
  String get photos => 'Fotografii';

  @override
  String get rawData => 'Date brute';

  @override
  String get content => 'Conținut';

  @override
  String get noContentToDisplay => 'Nu există conținut de afișat';

  @override
  String get noSummary => 'Fără rezumat';

  @override
  String get updateOmiFirmware => 'Actualizează firmware-ul omi';

  @override
  String get anErrorOccurredTryAgain => 'A apărut o eroare. Vă rugăm să încercați din nou.';

  @override
  String get welcomeBackSimple => 'Bine ai revenit';

  @override
  String get addVocabularyDescription =>
      'Adăugați cuvinte pe care Omi ar trebui să le recunoască în timpul transcrierii.';

  @override
  String get enterWordsCommaSeparated => 'Introduceți cuvinte (separate prin virgulă)';

  @override
  String get whenToReceiveDailySummary => 'Când să primiți rezumatul zilnic';

  @override
  String get checkingNextSevenDays => 'Se verifică următoarele 7 zile';

  @override
  String failedToDeleteError(String error) {
    return 'Ștergerea a eșuat: $error';
  }

  @override
  String get developerApiKeys => 'Chei API dezvoltator';

  @override
  String get noApiKeysCreateOne => 'Nu există chei API. Creați una pentru a începe.';

  @override
  String get commandRequired => '⌘ necesar';

  @override
  String get spaceKey => 'Spațiu';

  @override
  String loadMoreRemaining(String count) {
    return 'Încarcă mai multe ($count rămase)';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'Top $percentile% utilizator';
  }

  @override
  String get wrappedMinutes => 'minute';

  @override
  String get wrappedConversations => 'conversații';

  @override
  String get wrappedDaysActive => 'zile active';

  @override
  String get wrappedYouTalkedAbout => 'Ai vorbit despre';

  @override
  String get wrappedActionItems => 'Sarcini';

  @override
  String get wrappedTasksCreated => 'sarcini create';

  @override
  String get wrappedCompleted => 'finalizate';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% rată de finalizare';
  }

  @override
  String get wrappedYourTopDays => 'Cele mai bune zile';

  @override
  String get wrappedBestMoments => 'Cele mai bune momente';

  @override
  String get wrappedMyBuddies => 'Prietenii mei';

  @override
  String get wrappedCouldntStopTalkingAbout => 'Nu mă puteam opri să vorbesc despre';

  @override
  String get wrappedShow => 'SERIAL';

  @override
  String get wrappedMovie => 'FILM';

  @override
  String get wrappedBook => 'CARTE';

  @override
  String get wrappedCelebrity => 'CELEBRITATE';

  @override
  String get wrappedFood => 'MÂNCARE';

  @override
  String get wrappedMovieRecs => 'Recomandări de filme pentru prieteni';

  @override
  String get wrappedBiggest => 'Cea mai mare';

  @override
  String get wrappedStruggle => 'Provocare';

  @override
  String get wrappedButYouPushedThrough => 'Dar ai reușit 💪';

  @override
  String get wrappedWin => 'Victorie';

  @override
  String get wrappedYouDidIt => 'Ai reușit! 🎉';

  @override
  String get wrappedTopPhrases => 'Top 5 expresii';

  @override
  String get wrappedMins => 'min';

  @override
  String get wrappedConvos => 'conversații';

  @override
  String get wrappedDays => 'zile';

  @override
  String get wrappedMyBuddiesLabel => 'PRIETENII MEI';

  @override
  String get wrappedObsessionsLabel => 'OBSESII';

  @override
  String get wrappedStruggleLabel => 'PROVOCARE';

  @override
  String get wrappedWinLabel => 'VICTORIE';

  @override
  String get wrappedTopPhrasesLabel => 'TOP EXPRESII';

  @override
  String get wrappedLetsHitRewind => 'Să derulăm înapoi';

  @override
  String get wrappedGenerateMyWrapped => 'Generează Wrapped-ul meu';

  @override
  String get wrappedProcessingDefault => 'Se procesează...';

  @override
  String get wrappedCreatingYourStory => 'Se creează\npovestea ta din 2025...';

  @override
  String get wrappedSomethingWentWrong => 'Ceva nu a\nmers bine';

  @override
  String get wrappedAnErrorOccurred => 'A apărut o eroare';

  @override
  String get wrappedTryAgain => 'Încearcă din nou';

  @override
  String get wrappedNoDataAvailable => 'Nu sunt date disponibile';

  @override
  String get wrappedOmiLifeRecap => 'Rezumatul vieții Omi';

  @override
  String get wrappedSwipeUpToBegin => 'Glisează în sus pentru a începe';

  @override
  String get wrappedShareText => '2025-ul meu, amintit de Omi ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare => 'Partajarea a eșuat. Te rugăm să încerci din nou.';

  @override
  String get wrappedFailedToStartGeneration => 'Pornirea generării a eșuat. Te rugăm să încerci din nou.';

  @override
  String get wrappedStarting => 'Se pornește...';

  @override
  String get wrappedShare => 'Partajează';

  @override
  String get wrappedShareYourWrapped => 'Partajează Wrapped-ul tău';

  @override
  String get wrappedMy2025 => '2025-ul meu';

  @override
  String get wrappedRememberedByOmi => 'amintit de Omi';

  @override
  String get wrappedMostFunDay => 'Cea mai amuzantă';

  @override
  String get wrappedMostProductiveDay => 'Cea mai productivă';

  @override
  String get wrappedMostIntenseDay => 'Cea mai intensă';

  @override
  String get wrappedFunniestMoment => 'Cel mai amuzant';

  @override
  String get wrappedMostCringeMoment => 'Cel mai jenant';

  @override
  String get wrappedMinutesLabel => 'minute';

  @override
  String get wrappedConversationsLabel => 'conversații';

  @override
  String get wrappedDaysActiveLabel => 'zile active';

  @override
  String get wrappedTasksGenerated => 'sarcini generate';

  @override
  String get wrappedTasksCompleted => 'sarcini finalizate';

  @override
  String get wrappedTopFivePhrases => 'Top 5 expresii';

  @override
  String get wrappedAGreatDay => 'O zi grozavă';

  @override
  String get wrappedGettingItDone => 'A face treaba';

  @override
  String get wrappedAChallenge => 'O provocare';

  @override
  String get wrappedAHilariousMoment => 'Un moment amuzant';

  @override
  String get wrappedThatAwkwardMoment => 'Acel moment jenant';

  @override
  String get wrappedYouHadFunnyMoments => 'Ai avut momente amuzante anul acesta!';

  @override
  String get wrappedWeveAllBeenThere => 'Am fost cu toții acolo!';

  @override
  String get wrappedFriend => 'Prieten';

  @override
  String get wrappedYourBuddy => 'Prietenul tău!';

  @override
  String get wrappedNotMentioned => 'Nemenționat';

  @override
  String get wrappedTheHardPart => 'Partea grea';

  @override
  String get wrappedPersonalGrowth => 'Creștere personală';

  @override
  String get wrappedFunDay => 'Amuzant';

  @override
  String get wrappedProductiveDay => 'Productiv';

  @override
  String get wrappedIntenseDay => 'Intens';

  @override
  String get wrappedFunnyMomentTitle => 'Moment amuzant';

  @override
  String get wrappedCringeMomentTitle => 'Moment jenant';

  @override
  String get wrappedYouTalkedAboutBadge => 'Ai vorbit despre';

  @override
  String get wrappedCompletedLabel => 'Finalizat';

  @override
  String get wrappedMyBuddiesCard => 'Prietenii mei';

  @override
  String get wrappedBuddiesLabel => 'PRIETENI';

  @override
  String get wrappedObsessionsLabelUpper => 'OBSESII';

  @override
  String get wrappedStruggleLabelUpper => 'LUPTĂ';

  @override
  String get wrappedWinLabelUpper => 'VICTORIE';

  @override
  String get wrappedTopPhrasesLabelUpper => 'TOP EXPRESII';

  @override
  String get wrappedYourHeader => 'Zilele tale';

  @override
  String get wrappedTopDaysHeader => 'de top';

  @override
  String get wrappedYourTopDaysBadge => 'Zilele tale de top';

  @override
  String get wrappedBestHeader => 'Cele mai bune';

  @override
  String get wrappedMomentsHeader => 'Momente';

  @override
  String get wrappedBestMomentsBadge => 'Cele mai bune momente';

  @override
  String get wrappedBiggestHeader => 'Cea mai mare';

  @override
  String get wrappedStruggleHeader => 'Luptă';

  @override
  String get wrappedWinHeader => 'Victorie';

  @override
  String get wrappedButYouPushedThroughEmoji => 'Dar ai reușit 💪';

  @override
  String get wrappedYouDidItEmoji => 'Ai reușit! 🎉';

  @override
  String get wrappedHours => 'ore';

  @override
  String get wrappedActions => 'acțiuni';

  @override
  String get multipleSpeakersDetected => 'Au fost detectați mai mulți vorbitori';

  @override
  String get multipleSpeakersDescription =>
      'Se pare că în înregistrare sunt mai mulți vorbitori. Asigurați-vă că sunteți într-un loc liniștit și încercați din nou.';

  @override
  String get invalidRecordingDetected => 'Înregistrare invalidă detectată';

  @override
  String get notEnoughSpeechDescription =>
      'Nu a fost detectată suficientă vorbire. Vă rugăm să vorbiți mai mult și să încercați din nou.';

  @override
  String get speechDurationDescription => 'Asigurați-vă că vorbiți cel puțin 5 secunde și nu mai mult de 90.';

  @override
  String get connectionLostDescription =>
      'Conexiunea a fost întreruptă. Verificați conexiunea la internet și încercați din nou.';

  @override
  String get howToTakeGoodSample => 'Cum să faci o probă bună?';

  @override
  String get goodSampleInstructions =>
      '1. Asigurați-vă că sunteți într-un loc liniștit.\n2. Vorbiți clar și natural.\n3. Asigurați-vă că dispozitivul dvs. este în poziția sa naturală pe gât.\n\nOdată creat, îl puteți îmbunătăți oricând sau îl puteți face din nou.';

  @override
  String get noDeviceConnectedUseMic => 'Niciun dispozitiv conectat. Se va folosi microfonul telefonului.';

  @override
  String get doItAgain => 'Fă-o din nou';

  @override
  String get listenToSpeechProfile => 'Ascultă profilul meu vocal ➡️';

  @override
  String get recognizingOthers => 'Recunoașterea altora 👀';

  @override
  String get keepGoingGreat => 'Continuă, te descurci excelent';

  @override
  String get somethingWentWrongTryAgain => 'Ceva nu a funcționat! Vă rugăm să încercați din nou mai târziu.';

  @override
  String get uploadingVoiceProfile => 'Se încarcă profilul vocal....';

  @override
  String get memorizingYourVoice => 'Se memorează vocea ta...';

  @override
  String get personalizingExperience => 'Se personalizează experiența ta...';

  @override
  String get keepSpeakingUntil100 => 'Continuă să vorbești până ajungi la 100%.';

  @override
  String get greatJobAlmostThere => 'Treabă excelentă, ești aproape gata';

  @override
  String get soCloseJustLittleMore => 'Atât de aproape, doar puțin mai mult';

  @override
  String get notificationFrequency => 'Frecvența notificărilor';

  @override
  String get controlNotificationFrequency => 'Controlați cât de des Omi vă trimite notificări proactive.';

  @override
  String get yourScore => 'Scorul tău';

  @override
  String get dailyScoreBreakdown => 'Detalii scor zilnic';

  @override
  String get todaysScore => 'Scorul de azi';

  @override
  String get tasksCompleted => 'Sarcini finalizate';

  @override
  String get completionRate => 'Rata de finalizare';

  @override
  String get howItWorks => 'Cum funcționează';

  @override
  String get dailyScoreExplanation =>
      'Scorul tău zilnic se bazează pe finalizarea sarcinilor. Finalizează sarcinile pentru a-ți îmbunătăți scorul!';

  @override
  String get notificationFrequencyDescription =>
      'Controlează cât de des îți trimite Omi notificări proactive și mementouri.';

  @override
  String get sliderOff => 'Oprit';

  @override
  String get sliderMax => 'Max.';

  @override
  String summaryGeneratedFor(String date) {
    return 'Rezumat generat pentru $date';
  }

  @override
  String get failedToGenerateSummary => 'Generarea rezumatului a eșuat. Asigură-te că ai conversații pentru acea zi.';

  @override
  String get recap => 'Recapitulare';

  @override
  String deleteQuoted(String name) {
    return 'Șterge \"$name\"';
  }

  @override
  String moveConversationsTo(int count) {
    return 'Mută $count conversații în:';
  }

  @override
  String get noFolder => 'Fără dosar';

  @override
  String get removeFromAllFolders => 'Elimină din toate folderele';

  @override
  String get buildAndShareYourCustomApp => 'Construiește și partajează aplicația ta personalizată';

  @override
  String get searchAppsPlaceholder => 'Caută în 1500+ aplicații';

  @override
  String get filters => 'Filtre';

  @override
  String get frequencyOff => 'Oprit';

  @override
  String get frequencyMinimal => 'Minim';

  @override
  String get frequencyLow => 'Scăzut';

  @override
  String get frequencyBalanced => 'Echilibrat';

  @override
  String get frequencyHigh => 'Ridicat';

  @override
  String get frequencyMaximum => 'Maxim';

  @override
  String get frequencyDescOff => 'Fără notificări proactive';

  @override
  String get frequencyDescMinimal => 'Doar memento-uri critice';

  @override
  String get frequencyDescLow => 'Doar actualizări importante';

  @override
  String get frequencyDescBalanced => 'Memento-uri utile regulate';

  @override
  String get frequencyDescHigh => 'Verificări frecvente';

  @override
  String get frequencyDescMaximum => 'Rămâneți constant implicat';

  @override
  String get clearChatQuestion => 'Ștergi conversația?';

  @override
  String get syncingMessages => 'Sincronizare mesaje cu serverul...';

  @override
  String get chatAppsTitle => 'Aplicații de chat';

  @override
  String get selectApp => 'Selectează aplicația';

  @override
  String get noChatAppsEnabled =>
      'Nicio aplicație de chat activată.\nApasă pe \"Activează aplicații\" pentru a adăuga.';

  @override
  String get disable => 'Dezactivează';

  @override
  String get photoLibrary => 'Bibliotecă foto';

  @override
  String get chooseFile => 'Alege fișier';

  @override
  String get configureAiPersona => 'Configurează-ți personajul AI';

  @override
  String get connectAiAssistantsToYourData => 'Conectează asistenții AI la datele tale';

  @override
  String get oAuth => 'OAuth';

  @override
  String get trackYourGoalsOnHomepage => 'Urmărește-ți obiectivele personale pe pagina principală';

  @override
  String get deleteRecording => 'Șterge înregistrarea';

  @override
  String get thisCannotBeUndone => 'Această acțiune nu poate fi anulată.';

  @override
  String get sdCard => 'SD Card';

  @override
  String get fromSd => 'From SD';

  @override
  String get limitless => 'Limitless';

  @override
  String get fastTransfer => 'Transfer rapid';

  @override
  String get syncingStatus => 'Se sincronizează';

  @override
  String get failedStatus => 'Eșuat';

  @override
  String etaLabel(String time) {
    return 'Timp estimat: $time';
  }

  @override
  String get transferMethod => 'Metodă de transfer';

  @override
  String get fast => 'Rapid';

  @override
  String get ble => 'BLE';

  @override
  String get phone => 'Telefon';

  @override
  String get cancelSync => 'Anulează sincronizarea';

  @override
  String get cancelSyncMessage => 'Datele deja descărcate vor fi salvate. Poți relua mai târziu.';

  @override
  String get syncCancelled => 'Sincronizare anulată';

  @override
  String get deleteProcessedFiles => 'Delete Processed Files';

  @override
  String get processedFilesDeleted => 'Processed files deleted';

  @override
  String get wifiEnableFailed => 'Failed to enable WiFi on device. Please try again.';

  @override
  String get deviceNoFastTransfer => 'Your device does not support Fast Transfer. Use Bluetooth instead.';

  @override
  String get enableHotspotMessage => 'Te rugăm să activezi hotspot-ul telefonului și să încerci din nou.';

  @override
  String get transferStartFailed => 'Pornirea transferului a eșuat. Te rugăm să încerci din nou.';

  @override
  String get deviceNotResponding => 'Dispozitivul nu a răspuns. Te rugăm să încerci din nou.';

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
    return '$count conversații create';
  }

  @override
  String get internetRequired => 'Este necesară conexiune la internet';

  @override
  String get processAudio => 'Process Audio';

  @override
  String get start => 'Start';

  @override
  String get noRecordings => 'Nicio înregistrare';

  @override
  String get audioFromOmiWillAppearHere => 'Audio from your Omi device will appear here';

  @override
  String get deleteProcessed => 'Delete Processed';

  @override
  String get tryDifferentFilter => 'Încearcă un filtru diferit';

  @override
  String get recordings => 'Înregistrări';

  @override
  String get enableRemindersAccess => 'Activați accesul la Memento-uri în Setări pentru a utiliza Memento-urile Apple';

  @override
  String todayAtTime(String time) {
    return 'Astăzi la $time';
  }

  @override
  String yesterdayAtTime(String time) {
    return 'Ieri la $time';
  }

  @override
  String get lessThanAMinute => 'Mai puțin de un minut';

  @override
  String estimatedMinutes(int count) {
    return '~$count minut(e)';
  }

  @override
  String estimatedHours(int count) {
    return '~$count oră/ore';
  }

  @override
  String estimatedTimeRemaining(String time) {
    return 'Estimat: $time rămas';
  }

  @override
  String get summarizingConversation => 'Se rezumă conversația...\nAceasta poate dura câteva secunde';

  @override
  String get resummarizingConversation => 'Se rezumă din nou conversația...\nAceasta poate dura câteva secunde';

  @override
  String get nothingInterestingRetry => 'Nu s-a găsit nimic interesant,\nvrei să încerci din nou?';

  @override
  String get noSummaryForConversation => 'Nu există rezumat disponibil\npentru această conversație.';

  @override
  String get unknownLocation => 'Locație necunoscută';

  @override
  String get couldNotLoadMap => 'Nu s-a putut încărca harta';

  @override
  String get triggerConversationIntegration => 'Declanșează integrarea creării conversației';

  @override
  String get webhookUrlNotSet => 'URL-ul webhook nu este setat';

  @override
  String get setWebhookUrlInSettings =>
      'Te rugăm să setezi URL-ul webhook în setările pentru dezvoltatori pentru a folosi această funcție.';

  @override
  String get sendWebUrl => 'Trimite URL web';

  @override
  String get sendTranscript => 'Trimite transcrierea';

  @override
  String get sendSummary => 'Trimite rezumatul';

  @override
  String get debugModeDetected => 'Mod depanare detectat';

  @override
  String get performanceReduced => 'Performanța poate fi redusă';

  @override
  String autoClosingInSeconds(int seconds) {
    return 'Se închide automat în $seconds secunde';
  }

  @override
  String get modelRequired => 'Model necesar';

  @override
  String get downloadWhisperModel => 'Descărcați un model whisper pentru a utiliza transcrierea pe dispozitiv';

  @override
  String get deviceNotCompatible => 'Dispozitivul dvs. nu este compatibil cu transcrierea pe dispozitiv';

  @override
  String get deviceRequirements => 'Dispozitivul dvs. nu îndeplinește cerințele pentru transcriere pe dispozitiv.';

  @override
  String get willLikelyCrash => 'Activarea va cauza probabil blocarea sau înghețarea aplicației.';

  @override
  String get transcriptionSlowerLessAccurate => 'Transcrierea va fi semnificativ mai lentă și mai puțin precisă.';

  @override
  String get proceedAnyway => 'Continuă oricum';

  @override
  String get olderDeviceDetected => 'Dispozitiv mai vechi detectat';

  @override
  String get onDeviceSlower => 'Transcrierea pe dispozitiv poate fi mai lentă pe acest dispozitiv.';

  @override
  String get batteryUsageHigher => 'Consumul de baterie va fi mai mare decât transcrierea în cloud.';

  @override
  String get considerOmiCloud => 'Luați în considerare utilizarea Omi Cloud pentru performanță mai bună.';

  @override
  String get highResourceUsage => 'Utilizare ridicată a resurselor';

  @override
  String get onDeviceIntensive => 'Transcrierea pe dispozitiv necesită resurse intensive de calcul.';

  @override
  String get batteryDrainIncrease => 'Consumul bateriei va crește semnificativ.';

  @override
  String get deviceMayWarmUp => 'Dispozitivul se poate încălzi în timpul utilizării prelungite.';

  @override
  String get speedAccuracyLower => 'Viteza și precizia pot fi mai mici decât modelele Cloud.';

  @override
  String get cloudProvider => 'Furnizor cloud';

  @override
  String get premiumMinutesInfo =>
      '1.200 minute premium/lună. Fila Pe dispozitiv oferă transcriere gratuită nelimitată.';

  @override
  String get viewUsage => 'Vizualizați utilizarea';

  @override
  String get localProcessingInfo =>
      'Audio este procesat local. Funcționează offline, mai privat, dar consumă mai multă baterie.';

  @override
  String get model => 'Model';

  @override
  String get performanceWarning => 'Avertisment de performanță';

  @override
  String get largeModelWarning =>
      'Acest model este mare și poate bloca aplicația sau poate rula foarte lent pe dispozitive mobile.\n\n\"small\" sau \"base\" este recomandat.';

  @override
  String get usingNativeIosSpeech => 'Utilizarea recunoașterii vocale native iOS';

  @override
  String get noModelDownloadRequired =>
      'Se va utiliza motorul de vorbire nativ al dispozitivului. Nu este necesară descărcarea unui model.';

  @override
  String get modelReady => 'Model pregătit';

  @override
  String get redownload => 'Descarcă din nou';

  @override
  String get doNotCloseApp => 'Vă rugăm să nu închideți aplicația.';

  @override
  String get downloading => 'Se descarcă...';

  @override
  String get downloadModel => 'Descărcare model';

  @override
  String estimatedSize(String size) {
    return 'Dimensiune estimată: ~$size MB';
  }

  @override
  String availableSpace(String space) {
    return 'Spațiu disponibil: $space';
  }

  @override
  String get notEnoughSpace => 'Avertisment: Spațiu insuficient!';

  @override
  String get download => 'Descărcare';

  @override
  String downloadError(String error) {
    return 'Eroare de descărcare: $error';
  }

  @override
  String get cancelled => 'Anulat';

  @override
  String get deviceNotCompatibleTitle => 'Dispozitiv incompatibil';

  @override
  String get deviceNotMeetRequirements =>
      'Dispozitivul dvs. nu îndeplinește cerințele pentru transcrierea pe dispozitiv.';

  @override
  String get transcriptionSlowerOnDevice => 'Transcrierea pe dispozitiv poate fi mai lentă pe acest dispozitiv.';

  @override
  String get computationallyIntensive => 'Transcrierea pe dispozitiv este intensivă din punct de vedere computațional.';

  @override
  String get batteryDrainSignificantly => 'Descărcarea bateriei va crește semnificativ.';

  @override
  String get premiumMinutesMonth =>
      '1.200 minute premium/lună. Fila Pe dispozitiv oferă transcriere gratuită nelimitată. ';

  @override
  String get audioProcessedLocally =>
      'Audio este procesat local. Funcționează offline, mai privat, dar consumă mai multă baterie.';

  @override
  String get languageLabel => 'Limbă';

  @override
  String get modelLabel => 'Model';

  @override
  String get modelTooLargeWarning =>
      'Acest model este mare și poate cauza blocarea aplicației sau rulare foarte lentă pe dispozitivele mobile.\n\nsmall sau base este recomandat.';

  @override
  String get nativeEngineNoDownload =>
      'Motorul vocal nativ al dispozitivului va fi folosit. Nu este necesară descărcarea modelului.';

  @override
  String modelReadyWithName(String model) {
    return 'Model pregătit ($model)';
  }

  @override
  String get reDownload => 'Descarcă din nou';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return 'Se descarcă $model: $received / $total MB';
  }

  @override
  String preparingModel(String model) {
    return 'Se pregătește $model...';
  }

  @override
  String downloadErrorWithMessage(String error) {
    return 'Eroare de descărcare: $error';
  }

  @override
  String estimatedSizeWithValue(String size) {
    return 'Dimensiune estimată: ~$size MB';
  }

  @override
  String availableSpaceWithValue(String space) {
    return 'Spațiu disponibil: $space';
  }

  @override
  String get omiTranscriptionOptimized =>
      'Transcrierea live integrată a Omi este optimizată pentru conversații în timp real cu detectarea automată a vorbitorului și diarizare.';

  @override
  String get reset => 'Resetează';

  @override
  String get useTemplateFrom => 'Folosește șablon de la';

  @override
  String get selectProviderTemplate => 'Selectați un șablon de furnizor...';

  @override
  String get quicklyPopulateResponse => 'Completați rapid cu formatul de răspuns al furnizorului cunoscut';

  @override
  String get quicklyPopulateRequest => 'Completați rapid cu formatul de cerere al furnizorului cunoscut';

  @override
  String get invalidJsonError => 'JSON invalid';

  @override
  String downloadModelWithName(String model) {
    return 'Descarcă model ($model)';
  }

  @override
  String modelNameWithFile(String model) {
    return 'Model: $model';
  }

  @override
  String get device => 'Dispozitiv';

  @override
  String get chatAssistantsTitle => 'Asistenți de chat';

  @override
  String get permissionReadConversations => 'Citește conversații';

  @override
  String get permissionReadMemories => 'Citește amintiri';

  @override
  String get permissionReadTasks => 'Citește sarcini';

  @override
  String get permissionCreateConversations => 'Creează conversații';

  @override
  String get permissionCreateMemories => 'Creează amintiri';

  @override
  String get permissionTypeAccess => 'Acces';

  @override
  String get permissionTypeCreate => 'Creare';

  @override
  String get permissionTypeTrigger => 'Declanșator';

  @override
  String get permissionDescReadConversations => 'Această aplicație poate accesa conversațiile tale.';

  @override
  String get permissionDescReadMemories => 'Această aplicație poate accesa amintirile tale.';

  @override
  String get permissionDescReadTasks => 'Această aplicație poate accesa sarcinile tale.';

  @override
  String get permissionDescCreateConversations => 'Această aplicație poate crea conversații noi.';

  @override
  String get permissionDescCreateMemories => 'Această aplicație poate crea amintiri noi.';

  @override
  String get realtimeListening => 'Ascultare în timp real';

  @override
  String get setupCompleted => 'Finalizat';

  @override
  String get pleaseSelectRating => 'Te rugăm să selectezi o evaluare';

  @override
  String get writeReviewOptional => 'Scrie o recenzie (opțional)';

  @override
  String get setupQuestionsIntro => 'Help us improve Omi by answering a few questions.  🫶 💜';

  @override
  String get setupQuestionProfession => '1. Cu ce te ocupi?';

  @override
  String get setupQuestionUsage => '2. Where do you plan to use your Omi?';

  @override
  String get setupQuestionAge => '3. Care este categoria ta de vârstă?';

  @override
  String get setupAnswerAllQuestions => 'Nu ai răspuns la toate întrebările încă! 🥺';

  @override
  String get setupSkipHelp => 'Sari peste, nu vreau să ajut :C';

  @override
  String get professionEntrepreneur => 'Antreprenor';

  @override
  String get professionSoftwareEngineer => 'Inginer software';

  @override
  String get professionProductManager => 'Product Manager';

  @override
  String get professionExecutive => 'Executiv';

  @override
  String get professionSales => 'Vânzări';

  @override
  String get professionStudent => 'Student';

  @override
  String get usageAtWork => 'La muncă';

  @override
  String get usageIrlEvents => 'Evenimente IRL';

  @override
  String get usageOnline => 'Online';

  @override
  String get usageSocialSettings => 'În contexte sociale';

  @override
  String get usageEverywhere => 'Peste tot';

  @override
  String get customBackendUrlTitle => 'URL server personalizat';

  @override
  String get backendUrlLabel => 'URL server';

  @override
  String get saveUrlButton => 'Salvează URL';

  @override
  String get enterBackendUrlError => 'Introduceți URL-ul serverului';

  @override
  String get urlMustEndWithSlashError => 'URL-ul trebuie să se termine cu \"/\"';

  @override
  String get invalidUrlError => 'Introduceți un URL valid';

  @override
  String get backendUrlSavedSuccess => 'URL-ul serverului a fost salvat!';

  @override
  String get signInTitle => 'Autentificare';

  @override
  String get signInButton => 'Autentificare';

  @override
  String get enterEmailError => 'Introduceți adresa de e-mail';

  @override
  String get invalidEmailError => 'Introduceți o adresă de e-mail validă';

  @override
  String get enterPasswordError => 'Introduceți parola';

  @override
  String get passwordMinLengthError => 'Parola trebuie să aibă cel puțin 8 caractere';

  @override
  String get signInSuccess => 'Autentificare reușită!';

  @override
  String get alreadyHaveAccountLogin => 'Aveți deja un cont? Conectați-vă';

  @override
  String get emailLabel => 'E-mail';

  @override
  String get passwordLabel => 'Parolă';

  @override
  String get createAccountTitle => 'Creează cont';

  @override
  String get nameLabel => 'Nume';

  @override
  String get repeatPasswordLabel => 'Repetă parola';

  @override
  String get signUpButton => 'Înregistrare';

  @override
  String get enterNameError => 'Introduceți numele dvs.';

  @override
  String get passwordsDoNotMatch => 'Parolele nu se potrivesc';

  @override
  String get signUpSuccess => 'Înregistrare reușită!';

  @override
  String get loadingKnowledgeGraph => 'Se încarcă graficul cunoștințelor...';

  @override
  String get noKnowledgeGraphYet => 'Niciun grafic de cunoștințe încă';

  @override
  String get buildingKnowledgeGraphFromMemories => 'Se construiește graficul cunoștințelor din amintiri...';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'Graficul cunoștințelor va fi construit automat când creați amintiri noi.';

  @override
  String get buildGraphButton => 'Construiește grafic';

  @override
  String get checkOutMyMemoryGraph => 'Vezi graficul meu de memorie!';

  @override
  String get getButton => 'Obține';

  @override
  String openingApp(String appName) {
    return 'Se deschide $appName...';
  }

  @override
  String get writeSomething => 'Scrie ceva';

  @override
  String get submitReply => 'Trimite răspuns';

  @override
  String get editYourReply => 'Editează răspunsul';

  @override
  String get replyToReview => 'Răspunde la recenzie';

  @override
  String get rateAndReviewThisApp => 'Evaluează și recenzează această aplicație';

  @override
  String get noChangesInReview => 'Nu există modificări în recenzie de actualizat.';

  @override
  String get cantRateWithoutInternet => 'Nu puteți evalua aplicația fără conexiune la internet.';

  @override
  String get appAnalytics => 'Analiză aplicație';

  @override
  String get learnMoreLink => 'află mai multe';

  @override
  String get moneyEarned => 'Bani câștigați';

  @override
  String get writeYourReply => 'Scrie răspunsul tău...';

  @override
  String get replySentSuccessfully => 'Răspuns trimis cu succes';

  @override
  String failedToSendReply(String error) {
    return 'Trimiterea răspunsului a eșuat: $error';
  }

  @override
  String get send => 'Trimite';

  @override
  String starFilter(int count) {
    return '$count stele';
  }

  @override
  String get noReviewsFound => 'Nu s-au găsit recenzii';

  @override
  String get editReply => 'Editează răspunsul';

  @override
  String get reply => 'Răspuns';

  @override
  String starFilterLabel(int count) {
    return '$count stea';
  }

  @override
  String get sharePublicLink => 'Partajează link public';

  @override
  String get makePersonaPublic => 'Fă personajul public';

  @override
  String get connectedKnowledgeData => 'Date de cunoștințe conectate';

  @override
  String get enterName => 'Introdu numele';

  @override
  String get disconnectTwitter => 'Disconnect Twitter';

  @override
  String get disconnectTwitterConfirmation =>
      'Are you sure you want to disconnect your Twitter account? Your persona will no longer have access to your Twitter data.';

  @override
  String get getOmiDeviceDescription => 'Creează o clonă mai precisă cu conversațiile tale personale';

  @override
  String get getOmi => 'Get Omi';

  @override
  String get iHaveOmiDevice => 'I have Omi device';

  @override
  String get goal => 'OBIECTIV';

  @override
  String get tapToTrackThisGoal => 'Atingeți pentru a urmări acest obiectiv';

  @override
  String get tapToSetAGoal => 'Atingeți pentru a stabili un obiectiv';

  @override
  String get processedConversations => 'Conversații procesate';

  @override
  String get updatedConversations => 'Conversații actualizate';

  @override
  String get newConversations => 'Conversații noi';

  @override
  String get summaryTemplate => 'Șablon de rezumat';

  @override
  String get suggestedTemplates => 'Șabloane sugerate';

  @override
  String get otherTemplates => 'Alte șabloane';

  @override
  String get availableTemplates => 'Șabloane disponibile';

  @override
  String get getCreative => 'Fii creativ';

  @override
  String get defaultLabel => 'Implicit';

  @override
  String get lastUsedLabel => 'Ultima utilizare';

  @override
  String get setDefaultApp => 'Setează aplicația implicită';

  @override
  String setDefaultAppContent(String appName) {
    return 'Setați $appName ca aplicație implicită de rezumat?\\n\\nAceastă aplicație va fi utilizată automat pentru toate rezumatele conversațiilor viitoare.';
  }

  @override
  String get setDefaultButton => 'Setează implicit';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName setată ca aplicație implicită de rezumat';
  }

  @override
  String get createCustomTemplate => 'Creează șablon personalizat';

  @override
  String get allTemplates => 'Toate șabloanele';

  @override
  String failedToInstallApp(String appName) {
    return 'Instalarea $appName a eșuat. Vă rugăm să încercați din nou.';
  }

  @override
  String errorInstallingApp(String appName, String error) {
    return 'Eroare la instalarea $appName: $error';
  }

  @override
  String tagSpeaker(int speakerId) {
    return 'Etichetează vorbitorul $speakerId';
  }

  @override
  String get personNameAlreadyExists => 'O persoană cu acest nume există deja.';

  @override
  String get selectYouFromList => 'Pentru a te eticheta, te rugăm să selectezi \"Tu\" din listă.';

  @override
  String get enterPersonsName => 'Introdu numele persoanei';

  @override
  String get addPerson => 'Adaugă persoană';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'Etichetează alte segmente de la acest vorbitor ($selected/$total)';
  }

  @override
  String get tagOtherSegments => 'Etichetează alte segmente';

  @override
  String get managePeople => 'Gestionează persoanele';

  @override
  String get shareViaSms => 'Partajare prin SMS';

  @override
  String get selectContactsToShareSummary => 'Selectați contacte pentru a partaja rezumatul conversației';

  @override
  String get searchContactsHint => 'Căutați contacte...';

  @override
  String contactsSelectedCount(int count) {
    return '$count selectate';
  }

  @override
  String get clearAllSelection => 'Șterge tot';

  @override
  String get selectContactsToShare => 'Selectați contacte pentru partajare';

  @override
  String shareWithContactCount(int count) {
    return 'Partajare cu $count contact';
  }

  @override
  String shareWithContactsCount(int count) {
    return 'Partajare cu $count contacte';
  }

  @override
  String get contactsPermissionRequired => 'Permisiunea pentru contacte este necesară';

  @override
  String get contactsPermissionRequiredForSms => 'Permisiunea pentru contacte este necesară pentru partajare prin SMS';

  @override
  String get grantContactsPermissionForSms =>
      'Vă rugăm să acordați permisiunea pentru contacte pentru a partaja prin SMS';

  @override
  String get noContactsWithPhoneNumbers => 'Nu s-au găsit contacte cu numere de telefon';

  @override
  String get noContactsMatchSearch => 'Niciun contact nu corespunde căutării';

  @override
  String get failedToLoadContacts => 'Nu s-au putut încărca contactele';

  @override
  String get failedToPrepareConversationForSharing =>
      'Nu s-a putut pregăti conversația pentru partajare. Vă rugăm să încercați din nou.';

  @override
  String get couldNotOpenSmsApp => 'Nu s-a putut deschide aplicația SMS. Vă rugăm să încercați din nou.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'Iată despre ce tocmai am discutat: $link';
  }

  @override
  String get wifiSync => 'Sincronizare WiFi';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item copiat în clipboard';
  }

  @override
  String get wifiConnectionFailedTitle => 'Conexiune eșuată';

  @override
  String connectingToDeviceName(String deviceName) {
    return 'Se conectează la $deviceName';
  }

  @override
  String enableDeviceWifi(String deviceName) {
    return 'Enable $deviceName\'s WiFi';
  }

  @override
  String connectToDeviceName(String deviceName) {
    return 'Conectează la $deviceName';
  }

  @override
  String get recordingDetails => 'Detalii înregistrare';

  @override
  String get storageLocationSdCard => 'SD Card';

  @override
  String get storageLocationLimitlessPendant => 'Limitless Pendant';

  @override
  String get storageLocationPhone => 'Telefon';

  @override
  String get storageLocationPhoneMemory => 'Telefon (Memorie)';

  @override
  String storedOnDevice(String deviceName) {
    return 'Stocat pe $deviceName';
  }

  @override
  String get transferring => 'Se transferă...';

  @override
  String get transferRequired => 'Transfer necesar';

  @override
  String get downloadingAudioFromSdCard => 'Downloading audio from your device\'s SD card';

  @override
  String get transferRequiredDescription =>
      'This recording is stored on your device\'s SD card. Transfer it to your phone to play or share.';

  @override
  String get cancelTransfer => 'Anulează transferul';

  @override
  String get transferToPhone => 'Transferă pe telefon';

  @override
  String get privateAndSecureOnDevice => 'Privat și securizat pe dispozitivul tău';

  @override
  String get recordingInfo => 'Informații înregistrare';

  @override
  String get transferInProgress => 'Transfer în curs...';

  @override
  String get shareRecording => 'Partajează înregistrarea';

  @override
  String get deleteRecordingConfirmation =>
      'Ești sigur că vrei să ștergi definitiv această înregistrare? Această acțiune nu poate fi anulată.';

  @override
  String get recordingIdLabel => 'ID înregistrare';

  @override
  String get dateTimeLabel => 'Dată și oră';

  @override
  String get durationLabel => 'Durată';

  @override
  String get audioFormatLabel => 'Format audio';

  @override
  String get storageLocationLabel => 'Locația de stocare';

  @override
  String get estimatedSizeLabel => 'Dimensiune estimată';

  @override
  String get deviceModelLabel => 'Model dispozitiv';

  @override
  String get deviceIdLabel => 'ID dispozitiv';

  @override
  String get statusLabel => 'Stare';

  @override
  String get statusProcessed => 'Processed';

  @override
  String get statusUnprocessed => 'Neprocesat';

  @override
  String get switchedToFastTransfer => 'S-a trecut la transfer rapid';

  @override
  String get transferCompleteMessage => 'Transfer complet! Acum poți reda această înregistrare.';

  @override
  String transferFailedMessage(String error) {
    return 'Transfer eșuat: $error';
  }

  @override
  String get transferCancelled => 'Transfer anulat';

  @override
  String get fastTransferEnabled => 'Transfer rapid activat';

  @override
  String get bluetoothSyncEnabled => 'Sincronizare Bluetooth activată';

  @override
  String get enableFastTransfer => 'Activează transferul rapid';

  @override
  String get fastTransferDescription =>
      'Transferul rapid folosește WiFi pentru viteze de ~5x mai rapide. Telefonul se va conecta temporar la rețeaua WiFi a dispozitivului Omi în timpul transferului.';

  @override
  String get internetAccessPausedDuringTransfer => 'Accesul la internet este întrerupt în timpul transferului';

  @override
  String get chooseTransferMethodDescription =>
      'Alegeți cum sunt transferate înregistrările de pe dispozitivul Omi pe telefon.';

  @override
  String get wifiSpeed => '~150 KB/s prin WiFi';

  @override
  String get fiveTimesFaster => 'DE 5X MAI RAPID';

  @override
  String get fastTransferMethodDescription =>
      'Creează o conexiune WiFi directă la dispozitivul Omi. Telefonul se deconectează temporar de la WiFi-ul obișnuit în timpul transferului.';

  @override
  String get bluetooth => 'Bluetooth';

  @override
  String get bleSpeed => '~30 KB/s prin BLE';

  @override
  String get bluetoothMethodDescription =>
      'Folosește conexiunea Bluetooth Low Energy standard. Mai lent, dar nu afectează conexiunea WiFi.';

  @override
  String get selected => 'Selectat';

  @override
  String get selectOption => 'Selectează';

  @override
  String get lowBatteryAlertTitle => 'Alertă baterie descărcată';

  @override
  String get lowBatteryAlertBody => 'Bateria dispozitivului este descărcată. E timpul să reîncărcați! 🔋';

  @override
  String get deviceDisconnectedNotificationTitle => 'Dispozitivul Omi a fost deconectat';

  @override
  String get deviceDisconnectedNotificationBody => 'Vă rugăm să vă reconectați pentru a continua să utilizați Omi.';

  @override
  String get firmwareUpdateAvailable => 'Actualizare firmware disponibilă';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'O nouă actualizare de firmware ($version) este disponibilă pentru dispozitivul Omi. Doriți să actualizați acum?';
  }

  @override
  String get later => 'Mai târziu';

  @override
  String get appDeletedSuccessfully => 'Aplicația a fost ștearsă cu succes';

  @override
  String get appDeleteFailed => 'Nu s-a putut șterge aplicația. Vă rugăm să încercați din nou mai târziu.';

  @override
  String get appVisibilityChangedSuccessfully =>
      'Vizibilitatea aplicației a fost schimbată cu succes. Poate dura câteva minute până se reflectă.';

  @override
  String get errorActivatingAppIntegration =>
      'Eroare la activarea aplicației. Dacă este o aplicație de integrare, asigurați-vă că configurarea este completă.';

  @override
  String get errorUpdatingAppStatus => 'A apărut o eroare la actualizarea stării aplicației.';

  @override
  String get calculatingETA => 'Se calculează...';

  @override
  String aboutMinutesRemaining(int minutes) {
    return 'Aproximativ $minutes minute rămase';
  }

  @override
  String get aboutAMinuteRemaining => 'Aproximativ un minut rămas';

  @override
  String get almostDone => 'Aproape gata...';

  @override
  String get omiSays => 'omi spune';

  @override
  String get analyzingYourData => 'Se analizează datele tale...';

  @override
  String migratingToProtection(String level) {
    return 'Se migrează la protecție $level...';
  }

  @override
  String get noDataToMigrateFinalizing => 'Nu sunt date de migrat. Se finalizează...';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return 'Se migrează $itemType... $percentage%';
  }

  @override
  String get allObjectsMigratedFinalizing => 'Toate obiectele au fost migrate. Se finalizează...';

  @override
  String get migrationErrorOccurred => 'A apărut o eroare în timpul migrării. Te rugăm să încerci din nou.';

  @override
  String get migrationComplete => 'Migrare completă!';

  @override
  String dataProtectedWithSettings(String level) {
    return 'Datele tale sunt acum protejate cu noile setări $level.';
  }

  @override
  String get chatsLowercase => 'conversații';

  @override
  String get dataLowercase => 'date';

  @override
  String get fallNotificationTitle => 'Aoleu';

  @override
  String get fallNotificationBody => 'Ai căzut?';

  @override
  String get importantConversationTitle => 'Conversație importantă';

  @override
  String get importantConversationBody => 'Tocmai ai avut o conversație importantă. Atinge pentru a partaja rezumatul.';

  @override
  String get templateName => 'Nume șablon';

  @override
  String get templateNameHint => 'ex. Extractor acțiuni întâlnire';

  @override
  String get nameMustBeAtLeast3Characters => 'Numele trebuie să aibă cel puțin 3 caractere';

  @override
  String get conversationPromptHint =>
      'ex., Extrageți acțiuni, decizii luate și concluzii cheie din conversația furnizată.';

  @override
  String get pleaseEnterAppPrompt => 'Vă rugăm să introduceți un prompt pentru aplicația dvs.';

  @override
  String get promptMustBeAtLeast10Characters => 'Promptul trebuie să aibă cel puțin 10 caractere';

  @override
  String get anyoneCanDiscoverTemplate => 'Oricine poate descoperi șablonul dvs.';

  @override
  String get onlyYouCanUseTemplate => 'Doar dvs. puteți folosi acest șablon';

  @override
  String get generatingDescription => 'Se generează descrierea...';

  @override
  String get creatingAppIcon => 'Se creează pictograma aplicației...';

  @override
  String get installingApp => 'Se instalează aplicația...';

  @override
  String get appCreatedAndInstalled => 'Aplicație creată și instalată!';

  @override
  String get appCreatedSuccessfully => 'Aplicație creată cu succes!';

  @override
  String get failedToCreateApp => 'Nu s-a putut crea aplicația. Vă rugăm să încercați din nou.';

  @override
  String get addAppSelectCoreCapability => 'Selectați încă o capacitate de bază pentru aplicația dvs.';

  @override
  String get addAppSelectPaymentPlan => 'Selectați un plan de plată și introduceți un preț pentru aplicație';

  @override
  String get addAppSelectCapability => 'Selectați cel puțin o capacitate pentru aplicația dvs.';

  @override
  String get addAppSelectLogo => 'Selectați un logo pentru aplicația dvs.';

  @override
  String get addAppEnterChatPrompt => 'Introduceți un prompt de chat pentru aplicația dvs.';

  @override
  String get addAppEnterConversationPrompt => 'Introduceți un prompt de conversație pentru aplicația dvs.';

  @override
  String get addAppSelectTriggerEvent => 'Selectați un eveniment declanșator pentru aplicația dvs.';

  @override
  String get addAppEnterWebhookUrl => 'Introduceți un URL webhook pentru aplicația dvs.';

  @override
  String get addAppSelectCategory => 'Selectați o categorie pentru aplicația dvs.';

  @override
  String get addAppFillRequiredFields => 'Completați corect toate câmpurile obligatorii';

  @override
  String get addAppUpdatedSuccess => 'Aplicație actualizată cu succes 🚀';

  @override
  String get addAppUpdateFailed => 'Actualizare eșuată. Încercați mai târziu';

  @override
  String get addAppSubmittedSuccess => 'Aplicație trimisă cu succes 🚀';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'Eroare la deschiderea selectorului de fișiere: $message';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'Eroare la selectarea imaginii: $error';
  }

  @override
  String get addAppPhotosPermissionDenied => 'Permisiune foto refuzată. Permiteți accesul la fotografii';

  @override
  String get addAppErrorSelectingImageRetry => 'Eroare la selectarea imaginii. Încercați din nou.';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'Eroare la selectarea miniaturii: $error';
  }

  @override
  String get addAppErrorSelectingThumbnailRetry => 'Eroare la selectarea miniaturii. Încercați din nou.';

  @override
  String get addAppCapabilityConflictWithPersona => 'Alte capacități nu pot fi selectate cu Persona';

  @override
  String get addAppPersonaConflictWithCapabilities => 'Persona nu poate fi selectată cu alte capacități';

  @override
  String get personaTwitterHandleNotFound => 'Cont Twitter negăsit';

  @override
  String get personaTwitterHandleSuspended => 'Cont Twitter suspendat';

  @override
  String get personaFailedToVerifyTwitter => 'Verificarea contului Twitter a eșuat';

  @override
  String get personaFailedToFetch => 'Nu s-a putut obține persona dvs.';

  @override
  String get personaFailedToCreate => 'Nu s-a putut crea persona';

  @override
  String get personaConnectKnowledgeSource => 'Conectați cel puțin o sursă de date (Omi sau Twitter)';

  @override
  String get personaUpdatedSuccessfully => 'Persona actualizată cu succes';

  @override
  String get personaFailedToUpdate => 'Actualizarea personei a eșuat';

  @override
  String get personaPleaseSelectImage => 'Selectați o imagine';

  @override
  String get personaFailedToCreateTryLater => 'Crearea personei a eșuat. Încercați mai târziu.';

  @override
  String personaFailedToCreateWithError(String error) {
    return 'Crearea personei a eșuat: $error';
  }

  @override
  String get personaFailedToEnable => 'Activarea personei a eșuat';

  @override
  String personaErrorEnablingWithError(String error) {
    return 'Eroare la activarea personei: $error';
  }

  @override
  String get paymentFailedToFetchCountries => 'Nu s-au putut obține țările acceptate. Încercați mai târziu.';

  @override
  String get paymentFailedToSetDefault => 'Nu s-a putut seta metoda de plată implicită. Încercați mai târziu.';

  @override
  String get paymentFailedToSavePaypal => 'Nu s-au putut salva detaliile PayPal. Încercați mai târziu.';

  @override
  String get paypalEmailHint => 'nik@example.com';

  @override
  String get paypalMeLinkHint => 'paypal.me/nik';

  @override
  String get paymentMethodStripe => 'Stripe';

  @override
  String get paymentMethodPayPal => 'PayPal';

  @override
  String get paymentStatusActive => 'Activ';

  @override
  String get paymentStatusConnected => 'Conectat';

  @override
  String get paymentStatusNotConnected => 'Neconectat';

  @override
  String get paymentAppCost => 'Cost aplicație';

  @override
  String get paymentEnterValidAmount => 'Introduceți o sumă validă';

  @override
  String get paymentEnterAmountGreaterThanZero => 'Introduceți o sumă mai mare de 0';

  @override
  String get paymentPlan => 'Plan de plată';

  @override
  String get paymentNoneSelected => 'Nimic selectat';

  @override
  String get aiGenPleaseEnterDescription => 'Vă rugăm să introduceți o descriere pentru aplicația dvs.';

  @override
  String get aiGenCreatingAppIcon => 'Se creează pictograma aplicației...';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'A apărut o eroare: $message';
  }

  @override
  String get aiGenAppCreatedSuccessfully => 'Aplicația a fost creată cu succes!';

  @override
  String get aiGenFailedToCreateApp => 'Nu s-a putut crea aplicația';

  @override
  String get aiGenErrorWhileCreatingApp => 'A apărut o eroare la crearea aplicației';

  @override
  String get aiGenFailedToGenerateApp => 'Nu s-a putut genera aplicația. Vă rugăm să încercați din nou.';

  @override
  String get aiGenFailedToRegenerateIcon => 'Nu s-a putut regenera pictograma';

  @override
  String get aiGenPleaseGenerateAppFirst => 'Vă rugăm să generați mai întâi o aplicație';

  @override
  String get xHandleTitle => 'Care este numele tău de utilizator X?';

  @override
  String get xHandleDescription => 'We will pre-train your Omi clone\nbased on your account\'s activity';

  @override
  String get xHandleHint => '@nikshevchenko';

  @override
  String get xHandlePleaseEnter => 'Te rugăm să introduci numele tău de utilizator X';

  @override
  String get xHandlePleaseEnterValid => 'Te rugăm să introduci un nume de utilizator X valid';

  @override
  String get nextButton => 'Următorul';

  @override
  String get connectOmiDevice => 'Connect Omi Device';

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'Treci de la Planul Nelimitat la $title. Ești sigur că vrei să continui?';
  }

  @override
  String get planUpgradeScheduledMessage =>
      'Upgrade programat! Planul tău lunar continuă până la sfârșitul perioadei de facturare, apoi trece automat la anual.';

  @override
  String get couldNotSchedulePlanChange => 'Nu s-a putut programa schimbarea planului. Te rugăm să încerci din nou.';

  @override
  String get subscriptionReactivatedDefault =>
      'Abonamentul tău a fost reactivat! Fără taxă acum - vei fi facturat la sfârșitul perioadei curente.';

  @override
  String get subscriptionSuccessfulCharged => 'Abonament reușit! Ai fost taxat pentru noua perioadă de facturare.';

  @override
  String get couldNotProcessSubscription => 'Nu s-a putut procesa abonamentul. Te rugăm să încerci din nou.';

  @override
  String get couldNotLaunchUpgradePage => 'Nu s-a putut deschide pagina de upgrade. Te rugăm să încerci din nou.';

  @override
  String get transcriptionJsonPlaceholder => 'Paste your JSON configuration here...';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get pricePlaceholder => '0,00';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'Eroare la deschiderea selectorului de fișiere: $message';
  }

  @override
  String importErrorGeneric(String error) {
    return 'Eroare: $error';
  }

  @override
  String get mergeConversationsSuccessTitle => 'Conversații îmbinate cu succes';

  @override
  String mergeConversationsSuccessBody(int count) {
    return '$count conversații au fost îmbinate cu succes';
  }

  @override
  String get dailyReflectionNotificationTitle => 'E timpul pentru reflecție zilnică';

  @override
  String get dailyReflectionNotificationBody => 'Povestește-mi despre ziua ta';

  @override
  String get actionItemReminderTitle => 'Memento Omi';

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName deconectat';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'Vă rugăm să vă reconectați pentru a continua să utilizați $deviceName.';
  }

  @override
  String get onboardingSignIn => 'Conectare';

  @override
  String get onboardingYourName => 'Numele tău';

  @override
  String get onboardingLanguage => 'Limbă';

  @override
  String get onboardingPermissions => 'Permisiuni';

  @override
  String get onboardingComplete => 'Finalizat';

  @override
  String get onboardingWelcomeToOmi => 'Bine ai venit la Omi';

  @override
  String get onboardingTellUsAboutYourself => 'Spune-ne despre tine';

  @override
  String get onboardingChooseYourPreference => 'Alege preferința ta';

  @override
  String get onboardingGrantRequiredAccess => 'Acordă accesul necesar';

  @override
  String get onboardingYoureAllSet => 'Ești pregătit';

  @override
  String get searchTranscriptOrSummary => 'Căutare în transcriere sau rezumat...';

  @override
  String get myGoal => 'Obiectivul meu';

  @override
  String get appNotAvailable => 'Ups! Se pare că aplicația pe care o cauți nu este disponibilă.';

  @override
  String get failedToConnectTodoist => 'Conectarea la Todoist a eșuat';

  @override
  String get failedToConnectAsana => 'Conectarea la Asana a eșuat';

  @override
  String get failedToConnectGoogleTasks => 'Conectarea la Google Tasks a eșuat';

  @override
  String get failedToConnectClickUp => 'Conectarea la ClickUp a eșuat';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return 'Conectarea la $serviceName a eșuat: $error';
  }

  @override
  String get successfullyConnectedTodoist => 'Conectat cu succes la Todoist!';

  @override
  String get failedToConnectTodoistRetry => 'Conectarea la Todoist a eșuat. Te rugăm să încerci din nou.';

  @override
  String get successfullyConnectedAsana => 'Conectat cu succes la Asana!';

  @override
  String get failedToConnectAsanaRetry => 'Conectarea la Asana a eșuat. Te rugăm să încerci din nou.';

  @override
  String get successfullyConnectedGoogleTasks => 'Conectat cu succes la Google Tasks!';

  @override
  String get failedToConnectGoogleTasksRetry => 'Conectarea la Google Tasks a eșuat. Te rugăm să încerci din nou.';

  @override
  String get successfullyConnectedClickUp => 'Conectat cu succes la ClickUp!';

  @override
  String get failedToConnectClickUpRetry => 'Conectarea la ClickUp a eșuat. Te rugăm să încerci din nou.';

  @override
  String get successfullyConnectedNotion => 'Conectat cu succes la Notion!';

  @override
  String get failedToRefreshNotionStatus => 'Actualizarea stării conexiunii Notion a eșuat.';

  @override
  String get successfullyConnectedGoogle => 'Conectat cu succes la Google!';

  @override
  String get failedToRefreshGoogleStatus => 'Actualizarea stării conexiunii Google a eșuat.';

  @override
  String get successfullyConnectedWhoop => 'Conectat cu succes la Whoop!';

  @override
  String get failedToRefreshWhoopStatus => 'Actualizarea stării conexiunii Whoop a eșuat.';

  @override
  String get successfullyConnectedGitHub => 'Conectat cu succes la GitHub!';

  @override
  String get failedToRefreshGitHubStatus => 'Actualizarea stării conexiunii GitHub a eșuat.';

  @override
  String get authFailedToSignInWithGoogle => 'Autentificarea cu Google a eșuat, vă rugăm încercați din nou.';

  @override
  String get authenticationFailed => 'Autentificarea a eșuat. Vă rugăm încercați din nou.';

  @override
  String get authFailedToSignInWithApple => 'Autentificarea cu Apple a eșuat, vă rugăm încercați din nou.';

  @override
  String get authFailedToRetrieveToken => 'Nu s-a putut obține tokenul Firebase, vă rugăm încercați din nou.';

  @override
  String get authUnexpectedErrorFirebase =>
      'Eroare neașteptată la autentificare, eroare Firebase, vă rugăm încercați din nou.';

  @override
  String get authUnexpectedError => 'Eroare neașteptată la autentificare, vă rugăm încercați din nou';

  @override
  String get authFailedToLinkGoogle => 'Nu s-a putut conecta cu Google, vă rugăm încercați din nou.';

  @override
  String get authFailedToLinkApple => 'Nu s-a putut conecta cu Apple, vă rugăm încercați din nou.';

  @override
  String get onboardingBluetoothRequired => 'Este necesară permisiunea Bluetooth pentru a vă conecta la dispozitiv.';

  @override
  String get onboardingBluetoothDeniedSystemPrefs =>
      'Permisiunea Bluetooth a fost refuzată. Acordați permisiunea în Preferințe Sistem.';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'Starea permisiunii Bluetooth: $status. Verificați Preferințele Sistem.';
  }

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'Nu s-a putut verifica permisiunea Bluetooth: $error';
  }

  @override
  String get onboardingNotificationDeniedSystemPrefs =>
      'Permisiunea pentru notificări a fost refuzată. Acordați permisiunea în Preferințe Sistem.';

  @override
  String get onboardingNotificationDeniedNotifications =>
      'Permisiunea pentru notificări a fost refuzată. Acordați permisiunea în Preferințe Sistem > Notificări.';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return 'Starea permisiunii pentru notificări: $status. Verificați Preferințele Sistem.';
  }

  @override
  String onboardingFailedCheckNotification(String error) {
    return 'Nu s-a putut verifica permisiunea pentru notificări: $error';
  }

  @override
  String get onboardingLocationGrantInSettings =>
      'Acordați permisiunea pentru locație în Setări > Confidențialitate și securitate > Servicii de localizare';

  @override
  String get onboardingMicrophoneRequired => 'Este necesară permisiunea pentru microfon pentru înregistrare.';

  @override
  String get onboardingMicrophoneDenied =>
      'Permisiunea pentru microfon a fost refuzată. Acordați permisiunea în Preferințe Sistem > Confidențialitate și securitate > Microfon.';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'Starea permisiunii pentru microfon: $status. Verificați Preferințele Sistem.';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'Nu s-a putut verifica permisiunea pentru microfon: $error';
  }

  @override
  String get onboardingScreenCaptureRequired =>
      'Este necesară permisiunea de captură a ecranului pentru înregistrarea audio a sistemului.';

  @override
  String get onboardingScreenCaptureDenied =>
      'Permisiunea de captură a ecranului a fost refuzată. Acordați permisiunea în Preferințe Sistem > Confidențialitate și securitate > Înregistrare ecran.';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return 'Starea permisiunii de captură a ecranului: $status. Verificați Preferințele Sistem.';
  }

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return 'Nu s-a putut verifica permisiunea de captură a ecranului: $error';
  }

  @override
  String get onboardingAccessibilityRequired =>
      'Este necesară permisiunea de accesibilitate pentru detectarea întâlnirilor din browser.';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'Starea permisiunii de accesibilitate: $status. Verificați Preferințele Sistem.';
  }

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'Nu s-a putut verifica permisiunea de accesibilitate: $error';
  }

  @override
  String get msgCameraNotAvailable => 'Captura camerei nu este disponibilă pe această platformă';

  @override
  String get msgCameraPermissionDenied => 'Permisiunea camerei refuzată. Vă rugăm să permiteți accesul la cameră';

  @override
  String msgCameraAccessError(String error) {
    return 'Eroare la accesarea camerei: $error';
  }

  @override
  String get msgPhotoError => 'Eroare la realizarea fotografiei. Vă rugăm să încercați din nou.';

  @override
  String get msgMaxImagesLimit => 'Puteți selecta doar până la 4 imagini';

  @override
  String msgFilePickerError(String error) {
    return 'Eroare la deschiderea selectorului de fișiere: $error';
  }

  @override
  String msgSelectImagesError(String error) {
    return 'Eroare la selectarea imaginilor: $error';
  }

  @override
  String get msgPhotosPermissionDenied =>
      'Permisiunea pentru fotografii refuzată. Vă rugăm să permiteți accesul la fotografii pentru a selecta imagini';

  @override
  String get msgSelectImagesGenericError => 'Eroare la selectarea imaginilor. Vă rugăm să încercați din nou.';

  @override
  String get msgMaxFilesLimit => 'Puteți selecta doar până la 4 fișiere';

  @override
  String msgSelectFilesError(String error) {
    return 'Eroare la selectarea fișierelor: $error';
  }

  @override
  String get msgSelectFilesGenericError => 'Eroare la selectarea fișierelor. Vă rugăm să încercați din nou.';

  @override
  String get msgUploadFileFailed => 'Încărcarea fișierului a eșuat, vă rugăm să încercați din nou mai târziu';

  @override
  String get msgReadingMemories => 'Se citesc amintirile tale...';

  @override
  String get msgLearningMemories => 'Se învață din amintirile tale...';

  @override
  String get msgUploadAttachedFileFailed => 'Încărcarea fișierului atașat a eșuat.';

  @override
  String captureRecordingError(String error) {
    return 'A apărut o eroare în timpul înregistrării: $error';
  }

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return 'Înregistrarea s-a oprit: $reason. Este posibil să fie necesar să reconectați ecranele externe sau să reporniți înregistrarea.';
  }

  @override
  String get captureMicrophonePermissionRequired => 'Este necesară permisiunea microfonului';

  @override
  String get captureMicrophonePermissionInSystemPreferences => 'Acordați permisiunea microfonului în Preferințe Sistem';

  @override
  String get captureScreenRecordingPermissionRequired => 'Este necesară permisiunea de înregistrare a ecranului';

  @override
  String get captureDisplayDetectionFailed => 'Detectarea ecranului a eșuat. Înregistrarea s-a oprit.';

  @override
  String get devModeInvalidAudioBytesWebhookUrl => 'URL webhook pentru octeți audio invalidă';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl => 'URL webhook pentru transcriere în timp real invalidă';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl => 'URL webhook pentru conversație creată invalidă';

  @override
  String get devModeInvalidDaySummaryWebhookUrl => 'URL webhook pentru rezumatul zilnic invalidă';

  @override
  String get devModeSettingsSaved => 'Setări salvate!';

  @override
  String get voiceFailedToTranscribe => 'Nu s-a reușit transcrierea audio';

  @override
  String get locationPermissionRequired => 'Permisiune de locație necesară';

  @override
  String get locationPermissionContent =>
      'Transferul rapid necesită permisiune de locație pentru a verifica conexiunea WiFi. Vă rugăm să acordați permisiunea de locație pentru a continua.';

  @override
  String get pdfTranscriptExport => 'Export transcriere';

  @override
  String get pdfConversationExport => 'Export conversație';

  @override
  String pdfTitleLabel(String title) {
    return 'Titlu: $title';
  }

  @override
  String get conversationNewIndicator => 'Nou 🚀';

  @override
  String conversationPhotosCount(int count) {
    return '$count fotografii';
  }

  @override
  String get mergingStatus => 'Se îmbină...';

  @override
  String timeSecsSingular(int count) {
    return '$count sec';
  }

  @override
  String timeSecsPlural(int count) {
    return '$count sec';
  }

  @override
  String timeMinSingular(int count) {
    return '$count min';
  }

  @override
  String timeMinsPlural(int count) {
    return '$count min';
  }

  @override
  String timeMinsAndSecs(int mins, int secs) {
    return '$mins min $secs sec';
  }

  @override
  String timeHourSingular(int count) {
    return '$count oră';
  }

  @override
  String timeHoursPlural(int count) {
    return '$count ore';
  }

  @override
  String timeHoursAndMins(int hours, int mins) {
    return '$hours ore $mins min';
  }

  @override
  String timeDaySingular(int count) {
    return '$count zi';
  }

  @override
  String timeDaysPlural(int count) {
    return '$count zile';
  }

  @override
  String timeDaysAndHours(int days, int hours) {
    return '$days zile $hours ore';
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
  String get moveToFolder => 'Mutați în dosar';

  @override
  String get noFoldersAvailable => 'Nu există dosare disponibile';

  @override
  String get newFolder => 'Dosar nou';

  @override
  String get color => 'Culoare';

  @override
  String get waitingForDevice => 'Se așteaptă dispozitivul...';

  @override
  String get saySomething => 'Spune ceva...';

  @override
  String get initialisingSystemAudio => 'Se inițializează audio-ul sistemului';

  @override
  String get stopRecording => 'Oprește înregistrarea';

  @override
  String get continueRecording => 'Continuă înregistrarea';

  @override
  String get initialisingRecorder => 'Se inițializează reportofonul';

  @override
  String get pauseRecording => 'Pauză înregistrare';

  @override
  String get resumeRecording => 'Reia înregistrarea';

  @override
  String get noDailyRecapsYet => 'Încă nu există rezumate zilnice';

  @override
  String get dailyRecapsDescription => 'Rezumatele zilnice vor apărea aici odată generate';

  @override
  String get chooseTransferMethod => 'Alegeți metoda de transfer';

  @override
  String get fastTransferSpeed => '~150 KB/s prin WiFi';

  @override
  String largeTimeGapDetected(String gap) {
    return 'A fost detectată o diferență mare de timp ($gap)';
  }

  @override
  String largeTimeGapsDetected(String gaps) {
    return 'Au fost detectate diferențe mari de timp ($gaps)';
  }

  @override
  String get deviceDoesNotSupportWifiSwitchingToBle =>
      'Dispozitivul nu acceptă sincronizare WiFi, comutare la Bluetooth';

  @override
  String get appleHealthNotAvailable => 'Apple Health nu este disponibil pe acest dispozitiv';

  @override
  String get downloadAudio => 'Descarcă audio';

  @override
  String get audioDownloadSuccess => 'Audio descărcat cu succes';

  @override
  String get audioDownloadFailed => 'Descărcarea audio a eșuat';

  @override
  String get downloadingAudio => 'Se descarcă audio...';

  @override
  String get shareAudio => 'Partajează audio';

  @override
  String get preparingAudio => 'Se pregătește audio';

  @override
  String get gettingAudioFiles => 'Se obțin fișierele audio...';

  @override
  String get downloadingAudioProgress => 'Se descarcă audio';

  @override
  String get processingAudio => 'Se procesează audio';

  @override
  String get combiningAudioFiles => 'Se combină fișierele audio...';

  @override
  String get audioReady => 'Audio pregătit';

  @override
  String get openingShareSheet => 'Se deschide foaia de partajare...';

  @override
  String get audioShareFailed => 'Partajarea a eșuat';

  @override
  String get dailyRecaps => 'Recapitulări Zilnice';

  @override
  String get removeFilter => 'Eliminare Filtru';

  @override
  String get categoryConversationAnalysis => 'Analiză conversații';

  @override
  String get categoryPersonalityClone => 'Clonă de personalitate';

  @override
  String get categoryHealth => 'Sănătate';

  @override
  String get categoryEducation => 'Educație';

  @override
  String get categoryCommunication => 'Comunicare';

  @override
  String get categoryEmotionalSupport => 'Suport emoțional';

  @override
  String get categoryProductivity => 'Productivitate';

  @override
  String get categoryEntertainment => 'Divertisment';

  @override
  String get categoryFinancial => 'Financiar';

  @override
  String get categoryTravel => 'Călătorii';

  @override
  String get categorySafety => 'Siguranță';

  @override
  String get categoryShopping => 'Cumpărături';

  @override
  String get categorySocial => 'Social';

  @override
  String get categoryNews => 'Știri';

  @override
  String get categoryUtilities => 'Utilitare';

  @override
  String get categoryOther => 'Altele';

  @override
  String get capabilityChat => 'Chat';

  @override
  String get capabilityConversations => 'Conversații';

  @override
  String get capabilityExternalIntegration => 'Integrare externă';

  @override
  String get capabilityNotification => 'Notificare';

  @override
  String get triggerAudioBytes => 'Octeți audio';

  @override
  String get triggerConversationCreation => 'Creare conversație';

  @override
  String get triggerTranscriptProcessed => 'Transcriere procesată';

  @override
  String get actionCreateConversations => 'Creează conversații';

  @override
  String get actionCreateMemories => 'Creează amintiri';

  @override
  String get actionReadConversations => 'Citește conversații';

  @override
  String get actionReadMemories => 'Citește amintiri';

  @override
  String get actionReadTasks => 'Citește sarcini';

  @override
  String get scopeUserName => 'Nume utilizator';

  @override
  String get scopeUserFacts => 'Date utilizator';

  @override
  String get scopeUserConversations => 'Conversații utilizator';

  @override
  String get scopeUserChat => 'Chat utilizator';

  @override
  String get capabilitySummary => 'Rezumat';

  @override
  String get capabilityFeatured => 'Recomandate';

  @override
  String get capabilityTasks => 'Sarcini';

  @override
  String get capabilityIntegrations => 'Integrări';

  @override
  String get categoryPersonalityClones => 'Clone de personalitate';

  @override
  String get categoryProductivityLifestyle => 'Productivitate și stil de viață';

  @override
  String get categorySocialEntertainment => 'Social și divertisment';

  @override
  String get categoryProductivityTools => 'Instrumente de productivitate';

  @override
  String get categoryPersonalWellness => 'Bunăstare personală';

  @override
  String get rating => 'Evaluare';

  @override
  String get categories => 'Categorii';

  @override
  String get sortBy => 'Sortare';

  @override
  String get highestRating => 'Cea mai mare evaluare';

  @override
  String get lowestRating => 'Cea mai mică evaluare';

  @override
  String get resetFilters => 'Resetare filtre';

  @override
  String get applyFilters => 'Aplică filtre';

  @override
  String get mostInstalls => 'Cele mai multe instalări';

  @override
  String get couldNotOpenUrl => 'Nu s-a putut deschide URL-ul. Vă rugăm să încercați din nou.';

  @override
  String get newTask => 'Sarcină nouă';

  @override
  String get viewAll => 'Vezi tot';

  @override
  String get addTask => 'Adaugă sarcină';

  @override
  String get addMcpServer => 'Add MCP Server';

  @override
  String get connectExternalAiTools => 'Connect external AI tools';

  @override
  String get mcpServerUrl => 'MCP Server URL';

  @override
  String mcpServerConnected(int count) {
    return '$count tools connected successfully';
  }

  @override
  String get mcpConnectionFailed => 'Failed to connect to MCP server';

  @override
  String get authorizingMcpServer => 'Authorizing...';

  @override
  String get whereDidYouHearAboutOmi => 'How did you find us?';

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
  String get friendWordOfMouth => 'Friend';

  @override
  String get otherSource => 'Other';

  @override
  String get pleaseSpecify => 'Please specify';

  @override
  String get event => 'Event';

  @override
  String get coworker => 'Coworker';

  @override
  String get linkedIn => 'LinkedIn';

  @override
  String get appStore => 'App Store';

  @override
  String get googleSearch => 'Google Search';

  @override
  String get audioPlaybackUnavailable => 'Fișierul audio nu este disponibil pentru redare';

  @override
  String get audioPlaybackFailed => 'Nu se poate reda audio. Fișierul poate fi corupt sau lipsă.';

  @override
  String get connectionGuide => 'Ghid de conectare';

  @override
  String get iveDoneThis => 'Am făcut asta';

  @override
  String get pairNewDevice => 'Asociază un dispozitiv nou';

  @override
  String get dontSeeYourDevice => 'Nu vedeți dispozitivul?';

  @override
  String get reportAnIssue => 'Raportați o problemă';

  @override
  String get pairingTitleOmi => 'Porniți Omi';

  @override
  String get pairingDescOmi => 'Apăsați și mențineți apăsat dispozitivul până vibrează pentru a-l porni.';

  @override
  String get pairingTitleOmiDevkit => 'Puneți Omi DevKit în modul de asociere';

  @override
  String get pairingDescOmiDevkit =>
      'Apăsați butonul o dată pentru a porni. LED-ul va clipi violet în modul de asociere.';

  @override
  String get pairingTitleOmiGlass => 'Porniți Omi Glass';

  @override
  String get pairingDescOmiGlass => 'Apăsați și mențineți apăsat butonul lateral timp de 3 secunde pentru a porni.';

  @override
  String get pairingTitlePlaudNote => 'Puneți Plaud Note în modul de asociere';

  @override
  String get pairingDescPlaudNote =>
      'Apăsați și mențineți apăsat butonul lateral timp de 2 secunde. LED-ul roșu va clipi când este gata de asociere.';

  @override
  String get pairingTitleBee => 'Puneți Bee în modul de asociere';

  @override
  String get pairingDescBee => 'Apăsați butonul de 5 ori consecutiv. Lumina va începe să clipească albastru și verde.';

  @override
  String get pairingTitleLimitless => 'Puneți Limitless în modul de asociere';

  @override
  String get pairingDescLimitless =>
      'Când orice lumină este vizibilă, apăsați o dată apoi apăsați și mențineți apăsat până când dispozitivul arată o lumină roz, apoi eliberați.';

  @override
  String get pairingTitleFriendPendant => 'Puneți Friend Pendant în modul de asociere';

  @override
  String get pairingDescFriendPendant =>
      'Apăsați butonul de pe pandantiv pentru a-l porni. Va intra automat în modul de asociere.';

  @override
  String get pairingTitleFieldy => 'Puneți Fieldy în modul de asociere';

  @override
  String get pairingDescFieldy => 'Apăsați și mențineți apăsat dispozitivul până apare lumina pentru a-l porni.';

  @override
  String get pairingTitleAppleWatch => 'Conectați Apple Watch';

  @override
  String get pairingDescAppleWatch =>
      'Instalați și deschideți aplicația Omi pe Apple Watch, apoi apăsați Conectare în aplicație.';

  @override
  String get pairingTitleNeoOne => 'Puneți Neo One în modul de asociere';

  @override
  String get pairingDescNeoOne =>
      'Apăsați și mențineți apăsat butonul de alimentare până când LED-ul clipește. Dispozitivul va fi detectabil.';
}
