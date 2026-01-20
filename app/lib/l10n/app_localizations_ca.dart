// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Catalan Valencian (`ca`).
class AppLocalizationsCa extends AppLocalizations {
  AppLocalizationsCa([String locale = 'ca']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'Conversa';

  @override
  String get transcriptTab => 'Transcripció';

  @override
  String get actionItemsTab => 'Tasques';

  @override
  String get deleteConversationTitle => 'Eliminar conversa?';

  @override
  String get deleteConversationMessage =>
      'Esteu segur que voleu eliminar aquesta conversa? Aquesta acció no es pot desfer.';

  @override
  String get confirm => 'Confirmar';

  @override
  String get cancel => 'Cancel';

  @override
  String get ok => 'D\'acord';

  @override
  String get delete => 'Elimina';

  @override
  String get add => 'Afegir';

  @override
  String get update => 'Actualitzar';

  @override
  String get save => 'Desar';

  @override
  String get edit => 'Edita';

  @override
  String get close => 'Tancar';

  @override
  String get clear => 'Neteja';

  @override
  String get copyTranscript => 'Copiar transcripció';

  @override
  String get copySummary => 'Copiar resum';

  @override
  String get testPrompt => 'Provar indicació';

  @override
  String get reprocessConversation => 'Reprocessar conversa';

  @override
  String get deleteConversation => 'Suprimir conversa';

  @override
  String get contentCopied => 'Contingut copiat al porta-retalls';

  @override
  String get failedToUpdateStarred => 'No s\'ha pogut actualitzar l\'estat de destacat.';

  @override
  String get conversationUrlNotShared => 'No s\'ha pogut compartir l\'URL de la conversa.';

  @override
  String get errorProcessingConversation => 'Error en processar la conversa. Torneu-ho a provar més tard.';

  @override
  String get noInternetConnection => 'Sense connexió a Internet';

  @override
  String get unableToDeleteConversation => 'No es pot eliminar la conversa';

  @override
  String get somethingWentWrong => 'Alguna cosa ha anat malament! Torneu-ho a provar més tard.';

  @override
  String get copyErrorMessage => 'Copiar missatge d\'error';

  @override
  String get errorCopied => 'Missatge d\'error copiat al porta-retalls';

  @override
  String get remaining => 'Restant';

  @override
  String get loading => 'Carregant...';

  @override
  String get loadingDuration => 'Carregant durada...';

  @override
  String secondsCount(int count) {
    return '$count segons';
  }

  @override
  String get people => 'Persones';

  @override
  String get addNewPerson => 'Afegir nova persona';

  @override
  String get editPerson => 'Editar persona';

  @override
  String get createPersonHint => 'Creeu una nova persona i ensenyeu a Omi a reconèixer la seva veu també!';

  @override
  String get speechProfile => 'Perfil de Veu';

  @override
  String sampleNumber(int number) {
    return 'Mostra $number';
  }

  @override
  String get settings => 'Configuració';

  @override
  String get language => 'Idioma';

  @override
  String get selectLanguage => 'Seleccionar idioma';

  @override
  String get deleting => 'Eliminant...';

  @override
  String get pleaseCompleteAuthentication =>
      'Completeu l\'autenticació al vostre navegador. Un cop fet, torneu a l\'aplicació.';

  @override
  String get failedToStartAuthentication => 'No s\'ha pogut iniciar l\'autenticació';

  @override
  String get importStarted => 'Importació iniciada! Se us notificarà quan estigui completa.';

  @override
  String get failedToStartImport => 'No s\'ha pogut iniciar la importació. Torneu-ho a provar.';

  @override
  String get couldNotAccessFile => 'No s\'ha pogut accedir al fitxer seleccionat';

  @override
  String get askOmi => 'Pregunta a Omi';

  @override
  String get done => 'Fet';

  @override
  String get disconnected => 'Desconnectat';

  @override
  String get searching => 'Cercant...';

  @override
  String get connectDevice => 'Connectar dispositiu';

  @override
  String get monthlyLimitReached => 'Heu arribat al vostre límit mensual.';

  @override
  String get checkUsage => 'Comprovar ús';

  @override
  String get syncingRecordings => 'Sincronitzant enregistraments';

  @override
  String get recordingsToSync => 'Enregistraments per sincronitzar';

  @override
  String get allCaughtUp => 'Tot al dia';

  @override
  String get sync => 'Sincronitzar';

  @override
  String get pendantUpToDate => 'El penjoll està actualitzat';

  @override
  String get allRecordingsSynced => 'Tots els enregistraments estan sincronitzats';

  @override
  String get syncingInProgress => 'Sincronització en curs';

  @override
  String get readyToSync => 'Llest per sincronitzar';

  @override
  String get tapSyncToStart => 'Toqueu Sincronitzar per començar';

  @override
  String get pendantNotConnected => 'Penjoll no connectat. Connecteu-lo per sincronitzar.';

  @override
  String get everythingSynced => 'Tot està ja sincronitzat.';

  @override
  String get recordingsNotSynced => 'Teniu enregistraments que encara no s\'han sincronitzat.';

  @override
  String get syncingBackground => 'Continuarem sincronitzant els vostres enregistraments en segon pla.';

  @override
  String get noConversationsYet => 'Encara no hi ha converses';

  @override
  String get noStarredConversations => 'No hi ha converses destacades';

  @override
  String get starConversationHint =>
      'Per destacar una conversa, obriu-la i toqueu la icona d\'estrella a la capçalera.';

  @override
  String get searchConversations => 'Cercar converses...';

  @override
  String selectedCount(int count, Object s) {
    return '$count seleccionats';
  }

  @override
  String get merge => 'Fusionar';

  @override
  String get mergeConversations => 'Fusionar converses';

  @override
  String mergeConversationsMessage(int count) {
    return 'Això combinarà $count converses en una. Tot el contingut es fusionarà i regenerarà.';
  }

  @override
  String get mergingInBackground => 'Fusionant en segon pla. Això pot trigar una mica.';

  @override
  String get failedToStartMerge => 'No s\'ha pogut iniciar la fusió';

  @override
  String get askAnything => 'Pregunta qualsevol cosa';

  @override
  String get noMessagesYet => 'Encara no hi ha missatges!\nPer què no comenceu una conversa?';

  @override
  String get deletingMessages => 'Suprimint els teus missatges de la memòria d\'Omi...';

  @override
  String get messageCopied => '✨ Missatge copiat al porta-retalls';

  @override
  String get cannotReportOwnMessage => 'No podeu denunciar els vostres propis missatges.';

  @override
  String get reportMessage => 'Informar del missatge';

  @override
  String get reportMessageConfirm => 'Esteu segur que voleu denunciar aquest missatge?';

  @override
  String get messageReported => 'Missatge denunciat correctament.';

  @override
  String get thankYouFeedback => 'Gràcies pels vostres comentaris!';

  @override
  String get clearChat => 'Esborrar xat';

  @override
  String get clearChatConfirm => 'Esteu segur que voleu netejar el xat? Aquesta acció no es pot desfer.';

  @override
  String get maxFilesLimit => 'Només podeu pujar 4 fitxers alhora';

  @override
  String get chatWithOmi => 'Xatejar amb Omi';

  @override
  String get apps => 'Aplicacions';

  @override
  String get noAppsFound => 'No s\'han trobat aplicacions';

  @override
  String get tryAdjustingSearch => 'Proveu d\'ajustar la cerca o els filtres';

  @override
  String get createYourOwnApp => 'Crea la teva pròpia aplicació';

  @override
  String get buildAndShareApp => 'Construïu i compartiu la vostra aplicació personalitzada';

  @override
  String get searchApps => 'Cerca aplicacions...';

  @override
  String get myApps => 'Les meves aplicacions';

  @override
  String get installedApps => 'Aplicacions instal·lades';

  @override
  String get unableToFetchApps =>
      'No s\'han pogut obtenir les aplicacions :(\n\nComproveu la vostra connexió a internet i torneu-ho a provar.';

  @override
  String get aboutOmi => 'Sobre Omi';

  @override
  String get privacyPolicy => 'Política de privadesa';

  @override
  String get visitWebsite => 'Visitar el lloc web';

  @override
  String get helpOrInquiries => 'Ajuda o consultes?';

  @override
  String get joinCommunity => 'Uniu-vos a la comunitat!';

  @override
  String get membersAndCounting => '8000+ membres i sumant.';

  @override
  String get deleteAccountTitle => 'Eliminar compte';

  @override
  String get deleteAccountConfirm => 'Esteu segur que voleu eliminar el vostre compte?';

  @override
  String get cannotBeUndone => 'Això no es pot desfer.';

  @override
  String get allDataErased => 'Tots els vostres records i converses s\'eliminaran permanentment.';

  @override
  String get appsDisconnected => 'Les vostres aplicacions i integracions es desconnectaran immediatament.';

  @override
  String get exportBeforeDelete =>
      'Podeu exportar les vostres dades abans d\'eliminar el compte, però un cop eliminat, no es pot recuperar.';

  @override
  String get deleteAccountCheckbox =>
      'Entenc que eliminar el meu compte és permanent i totes les dades, incloent records i converses, es perdran i no es poden recuperar.';

  @override
  String get areYouSure => 'Esteu segur?';

  @override
  String get deleteAccountFinal =>
      'Aquesta acció és irreversible i eliminarà permanentment el vostre compte i totes les dades associades. Esteu segur que voleu continuar?';

  @override
  String get deleteNow => 'Eliminar ara';

  @override
  String get goBack => 'Tornar';

  @override
  String get checkBoxToConfirm =>
      'Marqueu la casella per confirmar que enteneu que eliminar el vostre compte és permanent i irreversible.';

  @override
  String get profile => 'Perfil';

  @override
  String get name => 'Nom';

  @override
  String get email => 'Correu electrònic';

  @override
  String get customVocabulary => 'Vocabulari Personalitzat';

  @override
  String get identifyingOthers => 'Identificació d\'Altres';

  @override
  String get paymentMethods => 'Mètodes de Pagament';

  @override
  String get conversationDisplay => 'Visualització de Converses';

  @override
  String get dataPrivacy => 'Privadesa de Dades';

  @override
  String get userId => 'ID d\'Usuari';

  @override
  String get notSet => 'No establert';

  @override
  String get userIdCopied => 'ID d\'usuari copiat al porta-retalls';

  @override
  String get systemDefault => 'Per defecte del sistema';

  @override
  String get planAndUsage => 'Pla i ús';

  @override
  String get offlineSync => 'Offline Sync';

  @override
  String get deviceSettings => 'Configuració del dispositiu';

  @override
  String get chatTools => 'Eines de xat';

  @override
  String get feedbackBug => 'Comentaris / Error';

  @override
  String get helpCenter => 'Centre d\'ajuda';

  @override
  String get developerSettings => 'Configuració de desenvolupador';

  @override
  String get getOmiForMac => 'Obtenir Omi per a Mac';

  @override
  String get referralProgram => 'Programa de recomanacions';

  @override
  String get signOut => 'Tancar Sessió';

  @override
  String get appAndDeviceCopied => 'Detalls de l\'aplicació i el dispositiu copiats';

  @override
  String get wrapped2025 => 'Resum 2025';

  @override
  String get yourPrivacyYourControl => 'La vostra privadesa, el vostre control';

  @override
  String get privacyIntro =>
      'A Omi, estem compromesos a protegir la vostra privadesa. Aquesta pàgina us permet controlar com s\'emmagatzemen i utilitzen les vostres dades.';

  @override
  String get learnMore => 'Més informació...';

  @override
  String get dataProtectionLevel => 'Nivell de protecció de dades';

  @override
  String get dataProtectionDesc =>
      'Les vostres dades estan protegides per defecte amb un xifratge fort. Reviseu la vostra configuració i opcions futures de privadesa a continuació.';

  @override
  String get appAccess => 'Accés d\'aplicacions';

  @override
  String get appAccessDesc =>
      'Les següents aplicacions poden accedir a les vostres dades. Toqueu una aplicació per gestionar els seus permisos.';

  @override
  String get noAppsExternalAccess => 'Cap aplicació instal·lada té accés extern a les vostres dades.';

  @override
  String get deviceName => 'Nom del dispositiu';

  @override
  String get deviceId => 'ID del dispositiu';

  @override
  String get firmware => 'Firmware';

  @override
  String get sdCardSync => 'Sincronització de targeta SD';

  @override
  String get hardwareRevision => 'Revisió de maquinari';

  @override
  String get modelNumber => 'Número de model';

  @override
  String get manufacturer => 'Fabricant';

  @override
  String get doubleTap => 'Doble toc';

  @override
  String get ledBrightness => 'Brillantor LED';

  @override
  String get micGain => 'Guany del micròfon';

  @override
  String get disconnect => 'Desconnectar';

  @override
  String get forgetDevice => 'Oblidar dispositiu';

  @override
  String get chargingIssues => 'Problemes de càrrega';

  @override
  String get disconnectDevice => 'Desconnecta el dispositiu';

  @override
  String get unpairDevice => 'Desvincula el dispositiu';

  @override
  String get unpairAndForget => 'Desvincular i oblidar dispositiu';

  @override
  String get deviceDisconnectedMessage => 'El vostre Omi s\'ha desconnectat 😔';

  @override
  String get deviceUnpairedMessage =>
      'Dispositiu desvinculat. Vés a Configuració > Bluetooth i oblida el dispositiu per completar la desvinculació.';

  @override
  String get unpairDialogTitle => 'Desvincular dispositiu';

  @override
  String get unpairDialogMessage =>
      'Això desvin cularà el dispositiu perquè es pugui connectar a un altre telèfon. Haureu d\'anar a Configuració > Bluetooth i oblidar el dispositiu per completar el procés.';

  @override
  String get deviceNotConnected => 'Dispositiu no connectat';

  @override
  String get connectDeviceMessage =>
      'Connecteu el vostre dispositiu Omi per accedir\na la configuració i personalització del dispositiu';

  @override
  String get deviceInfoSection => 'Informació del dispositiu';

  @override
  String get customizationSection => 'Personalització';

  @override
  String get hardwareSection => 'Maquinari';

  @override
  String get v2Undetected => 'V2 no detectat';

  @override
  String get v2UndetectedMessage =>
      'Veiem que teniu un dispositiu V1 o que el vostre dispositiu no està connectat. La funcionalitat de targeta SD només està disponible per a dispositius V2.';

  @override
  String get endConversation => 'Finalitzar conversa';

  @override
  String get pauseResume => 'Pausar/Reprendre';

  @override
  String get starConversation => 'Destacar conversa';

  @override
  String get doubleTapAction => 'Acció de doble toc';

  @override
  String get endAndProcess => 'Finalitzar i processar conversa';

  @override
  String get pauseResumeRecording => 'Pausar/Reprendre enregistrament';

  @override
  String get starOngoing => 'Destacar conversa en curs';

  @override
  String get off => 'Off';

  @override
  String get max => 'Màxim';

  @override
  String get mute => 'Silenciar';

  @override
  String get quiet => 'Silenciós';

  @override
  String get normal => 'Normal';

  @override
  String get high => 'Alt';

  @override
  String get micGainDescMuted => 'El micròfon està silenciat';

  @override
  String get micGainDescLow => 'Molt silenciós - per entorns sorollosos';

  @override
  String get micGainDescModerate => 'Silenciós - per soroll moderat';

  @override
  String get micGainDescNeutral => 'Neutre - enregistrament equilibrat';

  @override
  String get micGainDescSlightlyBoosted => 'Lleugerament potenciat - ús normal';

  @override
  String get micGainDescBoosted => 'Potenciat - per entorns silenciosos';

  @override
  String get micGainDescHigh => 'Alt - per veus distants o suaus';

  @override
  String get micGainDescVeryHigh => 'Molt alt - per fonts molt silencioses';

  @override
  String get micGainDescMax => 'Màxim - utilitzeu amb precaució';

  @override
  String get developerSettingsTitle => 'Configuració de desenvolupador';

  @override
  String get saving => 'Desant...';

  @override
  String get personaConfig => 'Configureu la vostra personalitat d\'IA';

  @override
  String get beta => 'BETA';

  @override
  String get transcription => 'Transcripció';

  @override
  String get transcriptionConfig => 'Configurar proveïdor STT';

  @override
  String get conversationTimeout => 'Temps d\'espera de conversa';

  @override
  String get conversationTimeoutConfig => 'Establir quan finalitzen automàticament les converses';

  @override
  String get importData => 'Importar dades';

  @override
  String get importDataConfig => 'Importar dades d\'altres fonts';

  @override
  String get debugDiagnostics => 'Depuració i diagnòstics';

  @override
  String get endpointUrl => 'URL del punt final';

  @override
  String get noApiKeys => 'Encara no hi ha claus API';

  @override
  String get createKeyToStart => 'Creeu una clau per començar';

  @override
  String get createKey => 'Crea Clau';

  @override
  String get docs => 'Documentació';

  @override
  String get yourOmiInsights => 'Les vostres estadístiques d\'Omi';

  @override
  String get today => 'Avui';

  @override
  String get thisMonth => 'Aquest mes';

  @override
  String get thisYear => 'Enguany';

  @override
  String get allTime => 'Des de sempre';

  @override
  String get noActivityYet => 'Encara no hi ha activitat';

  @override
  String get startConversationToSeeInsights =>
      'Comenceu una conversa amb Omi\nper veure les vostres estadístiques d\'ús aquí.';

  @override
  String get listening => 'Escoltant';

  @override
  String get listeningSubtitle => 'Temps total que Omi ha estat escoltant activament.';

  @override
  String get understanding => 'Entenent';

  @override
  String get understandingSubtitle => 'Paraules enteses de les vostres converses.';

  @override
  String get providing => 'Proporcionant';

  @override
  String get providingSubtitle => 'Tasques i notes capturades automàticament.';

  @override
  String get remembering => 'Recordant';

  @override
  String get rememberingSubtitle => 'Fets i detalls recordats per a vosaltres.';

  @override
  String get unlimitedPlan => 'Pla il·limitat';

  @override
  String get managePlan => 'Gestionar pla';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'El vostre pla es cancel·larà el $date.';
  }

  @override
  String renewsOn(String date) {
    return 'El vostre pla es renova el $date.';
  }

  @override
  String get basicPlan => 'Pla gratuït';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used de $limit min utilitzats';
  }

  @override
  String get upgrade => 'Actualitzar';

  @override
  String get upgradeToUnlimited => 'Actualitza a il·limitat';

  @override
  String basicPlanDesc(int limit) {
    return 'El vostre pla inclou $limit minuts gratuïts al mes. Actualitzeu per tenir-ne il·limitats.';
  }

  @override
  String get shareStatsMessage =>
      'Compartint les meves estadístiques d\'Omi! (omi.me - el vostre assistent d\'IA sempre actiu)';

  @override
  String get sharePeriodToday => 'Avui, omi ha:';

  @override
  String get sharePeriodMonth => 'Aquest mes, omi ha:';

  @override
  String get sharePeriodYear => 'Enguany, omi ha:';

  @override
  String get sharePeriodAllTime => 'Fins ara, omi ha:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 Escoltat durant $minutes minuts';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 Entès $words paraules';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ Proporcionat $count informacions';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 Recordat $count records';
  }

  @override
  String get debugLogs => 'Registres de depuració';

  @override
  String get debugLogsAutoDelete => 'S\'eliminen automàticament després de 3 dies.';

  @override
  String get debugLogsDesc => 'Ajuda a diagnosticar problemes';

  @override
  String get noLogFilesFound => 'No s\'han trobat fitxers de registre.';

  @override
  String get omiDebugLog => 'Registre de depuració d\'Omi';

  @override
  String get logShared => 'Registre compartit';

  @override
  String get selectLogFile => 'Seleccionar fitxer de registre';

  @override
  String get shareLogs => 'Compartir registres';

  @override
  String get debugLogCleared => 'Registre de depuració netejat';

  @override
  String get exportStarted => 'Exportació iniciada. Això pot trigar uns segons...';

  @override
  String get exportAllData => 'Exportar totes les dades';

  @override
  String get exportDataDesc => 'Exportar converses a un fitxer JSON';

  @override
  String get exportedConversations => 'Converses exportades d\'Omi';

  @override
  String get exportShared => 'Exportació compartida';

  @override
  String get deleteKnowledgeGraphTitle => 'Eliminar graf de coneixement?';

  @override
  String get deleteKnowledgeGraphMessage =>
      'Això eliminarà totes les dades derivades del graf de coneixement (nodes i connexions). Els vostres records originals restaran segurs. El graf es reconstruirà amb el temps o a la propera sol·licitud.';

  @override
  String get knowledgeGraphDeleted => 'Graf de coneixement eliminat';

  @override
  String deleteGraphFailed(String error) {
    return 'No s\'ha pogut eliminar el graf: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'Eliminar graf de coneixement';

  @override
  String get deleteKnowledgeGraphDesc => 'Esborrar tots els nodes i connexions';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'Servidor MCP';

  @override
  String get mcpServerDesc => 'Connectar assistents d\'IA a les vostres dades';

  @override
  String get serverUrl => 'URL del servidor';

  @override
  String get urlCopied => 'URL copiada';

  @override
  String get apiKeyAuth => 'Autenticació amb clau API';

  @override
  String get header => 'Capçalera';

  @override
  String get authorizationBearer => 'Authorization: Bearer <key>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'ID de client';

  @override
  String get clientSecret => 'Secret de client';

  @override
  String get useMcpApiKey => 'Utilitzeu la vostra clau API MCP';

  @override
  String get webhooks => 'Webhooks';

  @override
  String get conversationEvents => 'Esdeveniments de conversa';

  @override
  String get newConversationCreated => 'Nova conversa creada';

  @override
  String get realtimeTranscript => 'Transcripció en temps real';

  @override
  String get transcriptReceived => 'Transcripció rebuda';

  @override
  String get audioBytes => 'Bytes d\'àudio';

  @override
  String get audioDataReceived => 'Dades d\'àudio rebudes';

  @override
  String get intervalSeconds => 'Interval (segons)';

  @override
  String get daySummary => 'Resum del dia';

  @override
  String get summaryGenerated => 'Resum generat';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'Afegir a claude_desktop_config.json';

  @override
  String get copyConfig => 'Copiar configuració';

  @override
  String get configCopied => 'Configuració copiada al porta-retalls';

  @override
  String get listeningMins => 'Escoltant (min)';

  @override
  String get understandingWords => 'Entenent (paraules)';

  @override
  String get insights => 'Informació';

  @override
  String get memories => 'Records';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '$used de $limit min utilitzats aquest mes';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '$used de $limit paraules utilitzades aquest mes';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '$used de $limit informacions obtingudes aquest mes';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return '$used de $limit records creats aquest mes';
  }

  @override
  String get visibility => 'Visibilitat';

  @override
  String get visibilitySubtitle => 'Controleu quines converses apareixen a la vostra llista';

  @override
  String get showShortConversations => 'Mostrar converses curtes';

  @override
  String get showShortConversationsDesc => 'Mostrar converses més curtes que el llindar';

  @override
  String get showDiscardedConversations => 'Mostrar converses descartades';

  @override
  String get showDiscardedConversationsDesc => 'Incloure converses marcades com a descartades';

  @override
  String get shortConversationThreshold => 'Llindar de conversa curta';

  @override
  String get shortConversationThresholdSubtitle =>
      'Les converses més curtes que això s\'amagaran tret que s\'activi a dalt';

  @override
  String get durationThreshold => 'Llindar de durada';

  @override
  String get durationThresholdDesc => 'Amagar converses més curtes que això';

  @override
  String minLabel(int count) {
    return '$count min';
  }

  @override
  String get customVocabularyTitle => 'Vocabulari personalitzat';

  @override
  String get addWords => 'Afegir paraules';

  @override
  String get addWordsDesc => 'Noms, termes o paraules poc comunes';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'Connectar';

  @override
  String get comingSoon => 'Properament';

  @override
  String get chatToolsFooter => 'Connecteu les vostres aplicacions per veure dades i estadístiques al xat.';

  @override
  String get completeAuthInBrowser =>
      'Completeu l\'autenticació al vostre navegador. Un cop fet, torneu a l\'aplicació.';

  @override
  String failedToStartAuth(String appName) {
    return 'No s\'ha pogut iniciar l\'autenticació de $appName';
  }

  @override
  String disconnectAppTitle(String appName) {
    return 'Desconnectar $appName?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'Esteu segur que voleu desconnectar-vos de $appName? Podeu reconnectar en qualsevol moment.';
  }

  @override
  String disconnectedFrom(String appName) {
    return 'Desconnectat de $appName';
  }

  @override
  String get failedToDisconnect => 'No s\'ha pogut desconnectar';

  @override
  String connectTo(String appName) {
    return 'Connectar a $appName';
  }

  @override
  String authAccessMessage(String appName) {
    return 'Haureu d\'autoritzar Omi per accedir a les vostres dades de $appName. Això obrirà el vostre navegador per a l\'autenticació.';
  }

  @override
  String get continueAction => 'Continuar';

  @override
  String get languageTitle => 'Idioma';

  @override
  String get primaryLanguage => 'Idioma principal';

  @override
  String get automaticTranslation => 'Traducció automàtica';

  @override
  String get detectLanguages => 'Detectar més de 10 idiomes';

  @override
  String get authorizeSavingRecordings => 'Autoritzar desar enregistraments';

  @override
  String get thanksForAuthorizing => 'Gràcies per autoritzar!';

  @override
  String get needYourPermission => 'Necessitem el vostre permís';

  @override
  String get alreadyGavePermission =>
      'Ja ens heu donat permís per desar els vostres enregistraments. Aquí teniu un recordatori de per què ho necessitem:';

  @override
  String get wouldLikePermission =>
      'Ens agradaria el vostre permís per desar els vostres enregistraments de veu. Aquesta és la raó:';

  @override
  String get improveSpeechProfile => 'Millorar el vostre perfil de veu';

  @override
  String get improveSpeechProfileDesc =>
      'Utilitzem els enregistraments per entrenar i millorar el vostre perfil de veu personal.';

  @override
  String get trainFamilyProfiles => 'Entrenar perfils d\'amics i família';

  @override
  String get trainFamilyProfilesDesc =>
      'Els vostres enregistraments ens ajuden a reconèixer i crear perfils per als vostres amics i família.';

  @override
  String get enhanceTranscriptAccuracy => 'Millorar la precisió de transcripció';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'A mesura que el nostre model millora, podem proporcionar millors resultats de transcripció per als vostres enregistraments.';

  @override
  String get legalNotice =>
      'Avís legal: La legalitat d\'enregistrar i emmagatzemar dades de veu pot variar segons la vostra ubicació i com utilitzeu aquesta funció. És la vostra responsabilitat assegurar el compliment de les lleis i regulacions locals.';

  @override
  String get alreadyAuthorized => 'Ja autoritzat';

  @override
  String get authorize => 'Autoritzar';

  @override
  String get revokeAuthorization => 'Revocar autorització';

  @override
  String get authorizationSuccessful => 'Autorització correcta!';

  @override
  String get failedToAuthorize => 'No s\'ha pogut autoritzar. Torneu-ho a provar.';

  @override
  String get authorizationRevoked => 'Autorització revocada.';

  @override
  String get recordingsDeleted => 'Enregistraments eliminats.';

  @override
  String get failedToRevoke => 'No s\'ha pogut revocar l\'autorització. Torneu-ho a provar.';

  @override
  String get permissionRevokedTitle => 'Permís revocat';

  @override
  String get permissionRevokedMessage => 'Voleu que eliminem també tots els vostres enregistraments existents?';

  @override
  String get yes => 'Sí';

  @override
  String get editName => 'Edit Name';

  @override
  String get howShouldOmiCallYou => 'Com hauria d\'anomenar-vos Omi?';

  @override
  String get enterYourName => 'Introduïu el vostre nom';

  @override
  String get nameCannotBeEmpty => 'El nom no pot estar buit';

  @override
  String get nameUpdatedSuccessfully => 'Nom actualitzat correctament!';

  @override
  String get calendarSettings => 'Configuració del calendari';

  @override
  String get calendarProviders => 'Proveïdors de calendari';

  @override
  String get macOsCalendar => 'Calendari de macOS';

  @override
  String get connectMacOsCalendar => 'Connectar el vostre calendari local de macOS';

  @override
  String get googleCalendar => 'Google Calendar';

  @override
  String get syncGoogleAccount => 'Sincronitzar amb el vostre compte de Google';

  @override
  String get showMeetingsMenuBar => 'Mostrar reunions properes a la barra de menú';

  @override
  String get showMeetingsMenuBarDesc =>
      'Mostrar la vostra propera reunió i el temps fins que comenci a la barra de menú de macOS';

  @override
  String get showEventsNoParticipants => 'Mostrar esdeveniments sense participants';

  @override
  String get showEventsNoParticipantsDesc =>
      'Quan s\'activa, Properament mostra esdeveniments sense participants o enllaç de vídeo.';

  @override
  String get yourMeetings => 'Les vostres reunions';

  @override
  String get refresh => 'Actualitza';

  @override
  String get noUpcomingMeetings => 'No hi ha reunions properes';

  @override
  String get checkingNextDays => 'Comprovant els propers 30 dies';

  @override
  String get tomorrow => 'Demà';

  @override
  String get googleCalendarComingSoon => 'Integració de Google Calendar properament!';

  @override
  String connectedAsUser(String userId) {
    return 'Connectat com a usuari: $userId';
  }

  @override
  String get defaultWorkspace => 'Espai de treball per defecte';

  @override
  String get tasksCreatedInWorkspace => 'Les tasques es crearan en aquest espai de treball';

  @override
  String get defaultProjectOptional => 'Projecte per defecte (opcional)';

  @override
  String get leaveUnselectedTasks => 'Deixeu sense seleccionar per crear tasques sense projecte';

  @override
  String get noProjectsInWorkspace => 'No s\'han trobat projectes en aquest espai de treball';

  @override
  String get conversationTimeoutDesc =>
      'Trieu quant temps esperar en silenci abans de finalitzar automàticament una conversa:';

  @override
  String get timeout2Minutes => '2 minuts';

  @override
  String get timeout2MinutesDesc => 'Finalitzar conversa després de 2 minuts de silenci';

  @override
  String get timeout5Minutes => '5 minuts';

  @override
  String get timeout5MinutesDesc => 'Finalitzar conversa després de 5 minuts de silenci';

  @override
  String get timeout10Minutes => '10 minuts';

  @override
  String get timeout10MinutesDesc => 'Finalitzar conversa després de 10 minuts de silenci';

  @override
  String get timeout30Minutes => '30 minuts';

  @override
  String get timeout30MinutesDesc => 'Finalitzar conversa després de 30 minuts de silenci';

  @override
  String get timeout4Hours => '4 hores';

  @override
  String get timeout4HoursDesc => 'Finalitzar conversa després de 4 hores de silenci';

  @override
  String get conversationEndAfterHours => 'Les converses ara finalitzaran després de 4 hores de silenci';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Les converses ara finalitzaran després de $minutes minut(s) de silenci';
  }

  @override
  String get tellUsPrimaryLanguage => 'Digueu-nos el vostre idioma principal';

  @override
  String get languageForTranscription =>
      'Establiu el vostre idioma per a transcripcions més precises i una experiència personalitzada.';

  @override
  String get singleLanguageModeInfo =>
      'El mode d\'idioma únic està activat. La traducció està desactivada per a una major precisió.';

  @override
  String get searchLanguageHint => 'Cercar idioma per nom o codi';

  @override
  String get noLanguagesFound => 'No s\'han trobat idiomes';

  @override
  String get skip => 'Saltar';

  @override
  String languageSetTo(String language) {
    return 'Idioma establert a $language';
  }

  @override
  String get failedToSetLanguage => 'No s\'ha pogut establir l\'idioma';

  @override
  String appSettings(String appName) {
    return 'Configuració de $appName';
  }

  @override
  String disconnectFromApp(String appName) {
    return 'Desconnectar de $appName?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'Això eliminarà la vostra autenticació de $appName. Haureu de reconnectar per utilitzar-la de nou.';
  }

  @override
  String connectedToApp(String appName) {
    return 'Connectat a $appName';
  }

  @override
  String get account => 'Compte';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Les vostres tasques es sincronitzaran amb el vostre compte de $appName';
  }

  @override
  String get defaultSpace => 'Espai per defecte';

  @override
  String get selectSpaceInWorkspace => 'Seleccioneu un espai al vostre espai de treball';

  @override
  String get noSpacesInWorkspace => 'No s\'han trobat espais en aquest espai de treball';

  @override
  String get defaultList => 'Llista per defecte';

  @override
  String get tasksAddedToList => 'Les tasques s\'afegiran a aquesta llista';

  @override
  String get noListsInSpace => 'No s\'han trobat llistes en aquest espai';

  @override
  String failedToLoadRepos(String error) {
    return 'No s\'han pogut carregar els repositoris: $error';
  }

  @override
  String get defaultRepoSaved => 'Repositori per defecte desat';

  @override
  String get failedToSaveDefaultRepo => 'No s\'ha pogut desar el repositori per defecte';

  @override
  String get defaultRepository => 'Repositori per defecte';

  @override
  String get selectDefaultRepoDesc =>
      'Seleccioneu un repositori per defecte per crear incidències. Encara podeu especificar un repositori diferent quan creeu incidències.';

  @override
  String get noReposFound => 'No s\'han trobat repositoris';

  @override
  String get private => 'Privat';

  @override
  String updatedDate(String date) {
    return 'Actualitzat $date';
  }

  @override
  String get yesterday => 'Ahir';

  @override
  String daysAgo(int count) {
    return 'fa $count dies';
  }

  @override
  String get oneWeekAgo => 'fa 1 setmana';

  @override
  String weeksAgo(int count) {
    return 'fa $count setmanes';
  }

  @override
  String get oneMonthAgo => 'fa 1 mes';

  @override
  String monthsAgo(int count) {
    return 'fa $count mesos';
  }

  @override
  String get issuesCreatedInRepo => 'Les incidències es crearan al vostre repositori per defecte';

  @override
  String get taskIntegrations => 'Integracions de tasques';

  @override
  String get configureSettings => 'Configurar opcions';

  @override
  String get completeAuthBrowser => 'Completeu l\'autenticació al vostre navegador. Un cop fet, torneu a l\'aplicació.';

  @override
  String failedToStartAppAuth(String appName) {
    return 'No s\'ha pogut iniciar l\'autenticació de $appName';
  }

  @override
  String connectToAppTitle(String appName) {
    return 'Connectar a $appName';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Haureu d\'autoritzar Omi per crear tasques al vostre compte de $appName. Això obrirà el vostre navegador per a l\'autenticació.';
  }

  @override
  String get continueButton => 'Continuar';

  @override
  String appIntegration(String appName) {
    return 'Integració de $appName';
  }

  @override
  String integrationComingSoon(String appName) {
    return 'La integració amb $appName arribarà aviat! Estem treballant dur per oferir-vos més opcions de gestió de tasques.';
  }

  @override
  String get gotIt => 'Entès';

  @override
  String get tasksExportedOneApp => 'Les tasques es poden exportar a una aplicació alhora.';

  @override
  String get completeYourUpgrade => 'Completeu la vostra actualització';

  @override
  String get importConfiguration => 'Importar configuració';

  @override
  String get exportConfiguration => 'Exportar configuració';

  @override
  String get bringYourOwn => 'Utilitzeu el vostre propi';

  @override
  String get payYourSttProvider => 'Utilitzeu omi lliurement. Només pagueu directament al vostre proveïdor STT.';

  @override
  String get freeMinutesMonth => '1.200 minuts gratuïts/mes inclosos. Il·limitat amb ';

  @override
  String get omiUnlimited => 'Omi Il·limitat';

  @override
  String get hostRequired => 'Cal un amfitrió';

  @override
  String get validPortRequired => 'Cal un port vàlid';

  @override
  String get validWebsocketUrlRequired => 'Cal un URL WebSocket vàlid (wss://)';

  @override
  String get apiUrlRequired => 'Cal un URL API';

  @override
  String get apiKeyRequired => 'Cal una clau API';

  @override
  String get invalidJsonConfig => 'Configuració JSON no vàlida';

  @override
  String errorSaving(String error) {
    return 'Error en desar: $error';
  }

  @override
  String get configCopiedToClipboard => 'Configuració copiada al porta-retalls';

  @override
  String get pasteJsonConfig => 'Enganxeu la vostra configuració JSON a continuació:';

  @override
  String get addApiKeyAfterImport => 'Haureu d\'afegir la vostra pròpia clau API després d\'importar';

  @override
  String get paste => 'Enganxar';

  @override
  String get import => 'Importar';

  @override
  String get invalidProviderInConfig => 'Proveïdor no vàlid a la configuració';

  @override
  String importedConfig(String providerName) {
    return 'Configuració de $providerName importada';
  }

  @override
  String invalidJson(String error) {
    return 'JSON no vàlid: $error';
  }

  @override
  String get provider => 'Proveïdor';

  @override
  String get live => 'En directe';

  @override
  String get onDevice => 'Al dispositiu';

  @override
  String get apiUrl => 'URL de l\'API';

  @override
  String get enterSttHttpEndpoint => 'Introduïu el vostre punt final HTTP STT';

  @override
  String get websocketUrl => 'URL de WebSocket';

  @override
  String get enterLiveSttWebsocket => 'Introduïu el vostre punt final WebSocket STT en directe';

  @override
  String get apiKey => 'Clau API';

  @override
  String get enterApiKey => 'Introduïu la vostra clau API';

  @override
  String get storedLocallyNeverShared => 'Emmagatzemat localment, mai compartit';

  @override
  String get host => 'Amfitrió';

  @override
  String get port => 'Port';

  @override
  String get advanced => 'Avançat';

  @override
  String get configuration => 'Configuració';

  @override
  String get requestConfiguration => 'Configuració de sol·licitud';

  @override
  String get responseSchema => 'Esquema de resposta';

  @override
  String get modified => 'Modificat';

  @override
  String get resetRequestConfig => 'Restablir configuració de sol·licitud per defecte';

  @override
  String get logs => 'Registres';

  @override
  String get logsCopied => 'Registres copiats';

  @override
  String get noLogsYet =>
      'Encara no hi ha registres. Comenceu a enregistrar per veure l\'activitat STT personalitzada.';

  @override
  String deviceUsesCodec(String device, String reason) {
    return '$device utilitza $reason. Sutilitzarà Omi.';
  }

  @override
  String get omiTranscription => 'Transcripció d\'Omi';

  @override
  String get bestInClassTranscription => 'Transcripció de millor qualitat sense configuració';

  @override
  String get instantSpeakerLabels => 'Etiquetes d\'interlocutor instantànies';

  @override
  String get languageTranslation => 'Traducció de més de 100 idiomes';

  @override
  String get optimizedForConversation => 'Optimitzat per a converses';

  @override
  String get autoLanguageDetection => 'Detecció automàtica d\'idioma';

  @override
  String get highAccuracy => 'Alta precisió';

  @override
  String get privacyFirst => 'Privadesa primer';

  @override
  String get saveChanges => 'Desa els canvis';

  @override
  String get resetToDefault => 'Restableix per defecte';

  @override
  String get viewTemplate => 'Veure plantilla';

  @override
  String get trySomethingLike => 'Proveu quelcom com...';

  @override
  String get tryIt => 'Provar-ho';

  @override
  String get creatingPlan => 'Creant pla';

  @override
  String get developingLogic => 'Desenvolupant lògica';

  @override
  String get designingApp => 'Dissenyant aplicació';

  @override
  String get generatingIconStep => 'Generant icona';

  @override
  String get finalTouches => 'Tocs finals';

  @override
  String get processing => 'Processant...';

  @override
  String get features => 'Funcionalitats';

  @override
  String get creatingYourApp => 'Creant la vostra aplicació...';

  @override
  String get generatingIcon => 'Generant icona...';

  @override
  String get whatShouldWeMake => 'Què hauríem de fer?';

  @override
  String get appName => 'Nom de l\'aplicació';

  @override
  String get description => 'Descripció';

  @override
  String get publicLabel => 'Pública';

  @override
  String get privateLabel => 'Privada';

  @override
  String get free => 'Gratuïta';

  @override
  String get perMonth => '/ Mes';

  @override
  String get tailoredConversationSummaries => 'Resums de converses personalitzats';

  @override
  String get customChatbotPersonality => 'Personalitat de xatbot personalitzada';

  @override
  String get makePublic => 'Fer públic';

  @override
  String get anyoneCanDiscover => 'Qualsevol pot descobrir la vostra aplicació';

  @override
  String get onlyYouCanUse => 'Només vós podeu utilitzar aquesta aplicació';

  @override
  String get paidApp => 'Aplicació de pagament';

  @override
  String get usersPayToUse => 'Els usuaris paguen per utilitzar la vostra aplicació';

  @override
  String get freeForEveryone => 'Gratuïta per a tothom';

  @override
  String get perMonthLabel => '/ mes';

  @override
  String get creating => 'Creant...';

  @override
  String get createApp => 'Crear aplicació';

  @override
  String get searchingForDevices => 'Cercant dispositius...';

  @override
  String devicesFoundNearby(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'DISPOSITIUS',
      one: 'DISPOSITIU',
    );
    return '$count $_temp0 TROBATS A PROP';
  }

  @override
  String get pairingSuccessful => 'VINCULACIÓ CORRECTA';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Error en connectar amb l\'Apple Watch: $error';
  }

  @override
  String get dontShowAgain => 'No ho tornis a mostrar';

  @override
  String get iUnderstand => 'Ho entenc';

  @override
  String get enableBluetooth => 'Activar Bluetooth';

  @override
  String get bluetoothNeeded =>
      'Omi necessita Bluetooth per connectar-se al vostre dispositiu portàtil. Activeu Bluetooth i torneu-ho a provar.';

  @override
  String get contactSupport => 'Contactar amb suport?';

  @override
  String get connectLater => 'Connectar més tard';

  @override
  String get grantPermissions => 'Concedir permisos';

  @override
  String get backgroundActivity => 'Activitat en segon pla';

  @override
  String get backgroundActivityDesc => 'Deixeu que Omi s\'executi en segon pla per a una millor estabilitat';

  @override
  String get locationAccess => 'Accés a la ubicació';

  @override
  String get locationAccessDesc => 'Activeu la ubicació en segon pla per a l\'experiència completa';

  @override
  String get notifications => 'Notificacions';

  @override
  String get notificationsDesc => 'Activeu les notificacions per mantenir-vos informat';

  @override
  String get locationServiceDisabled => 'Servei d\'ubicació desactivat';

  @override
  String get locationServiceDisabledDesc =>
      'El servei d\'ubicació està desactivat. Aneu a Configuració > Privadesa i seguretat > Serveis d\'ubicació i activeu-lo';

  @override
  String get backgroundLocationDenied => 'Accés a la ubicació en segon pla denegat';

  @override
  String get backgroundLocationDeniedDesc =>
      'Aneu a la configuració del dispositiu i establiu el permís d\'ubicació a \"Permetre sempre\"';

  @override
  String get lovingOmi => 'T\'agrada Omi?';

  @override
  String get leaveReviewIos =>
      'Ajudeu-nos a arribar a més gent deixant una ressenya a l\'App Store. Els vostres comentaris són molt importants per a nosaltres!';

  @override
  String get leaveReviewAndroid =>
      'Ajudeu-nos a arribar a més gent deixant una ressenya a Google Play Store. Els vostres comentaris són molt importants per a nosaltres!';

  @override
  String get rateOnAppStore => 'Valorar a l\'App Store';

  @override
  String get rateOnGooglePlay => 'Valorar a Google Play';

  @override
  String get maybeLater => 'Potser més tard';

  @override
  String get speechProfileIntro =>
      'Omi necessita aprendre els vostres objectius i la vostra veu. Podreu modificar-ho més tard.';

  @override
  String get getStarted => 'Començar';

  @override
  String get allDone => 'Tot fet!';

  @override
  String get keepGoing => 'Continueu, ho esteu fent molt bé';

  @override
  String get skipThisQuestion => 'Salta aquesta pregunta';

  @override
  String get skipForNow => 'Ometre ara';

  @override
  String get connectionError => 'Error de connexió';

  @override
  String get connectionErrorDesc =>
      'No s\'ha pogut connectar amb el servidor. Comproveu la vostra connexió a internet i torneu-ho a provar.';

  @override
  String get invalidRecordingMultipleSpeakers => 'S\'ha detectat un enregistrament no vàlid';

  @override
  String get multipleSpeakersDesc =>
      'Sembla que hi ha diversos parlants a l\'enregistrament. Assegureu-vos que esteu en un lloc tranquil i torneu-ho a provar.';

  @override
  String get tooShortDesc => 'No s\'ha detectat prou veu. Parleu més i torneu-ho a provar.';

  @override
  String get invalidRecordingDesc => 'Assegureu-vos de parlar durant almenys 5 segons i no més de 90.';

  @override
  String get areYouThere => 'Hi sou?';

  @override
  String get noSpeechDesc =>
      'No hem pogut detectar cap veu. Assegureu-vos de parlar durant almenys 10 segons i no més de 3 minuts.';

  @override
  String get connectionLost => 'Connexió perduda';

  @override
  String get connectionLostDesc =>
      'La connexió s\'ha interromput. Comproveu la vostra connexió a internet i torneu-ho a provar.';

  @override
  String get tryAgain => 'Tornar a provar';

  @override
  String get connectOmiOmiGlass => 'Connectar Omi / OmiGlass';

  @override
  String get continueWithoutDevice => 'Continuar sense dispositiu';

  @override
  String get permissionsRequired => 'Permisos necessaris';

  @override
  String get permissionsRequiredDesc =>
      'Aquesta aplicació necessita permisos de Bluetooth i ubicació per funcionar correctament. Activeu-los a la configuració.';

  @override
  String get openSettings => 'Obrir configuració';

  @override
  String get wantDifferentName => 'Voleu que us anomeni d\'una altra manera?';

  @override
  String get whatsYourName => 'Com et dius?';

  @override
  String get speakTranscribeSummarize => 'Parlar. Transcriure. Resumir.';

  @override
  String get signInWithApple => 'Iniciar sessió amb Apple';

  @override
  String get signInWithGoogle => 'Iniciar sessió amb Google';

  @override
  String get byContinuingAgree => 'En continuar, accepteu la nostra ';

  @override
  String get termsOfUse => 'Condicions d\'ús';

  @override
  String get omiYourAiCompanion => 'Omi – El vostre company d\'IA';

  @override
  String get captureEveryMoment => 'Captureu cada moment. Obteniu resums\nimpulsats per IA. No prengueu més notes.';

  @override
  String get appleWatchSetup => 'Configuració de l\'Apple Watch';

  @override
  String get permissionRequestedExclaim => 'Permís sol·licitat!';

  @override
  String get microphonePermission => 'Permís del micròfon';

  @override
  String get permissionGrantedNow =>
      'Permís atorgat! Ara:\n\nObriu l\'aplicació Omi al vostre rellotge i toqueu \"Continuar\" a continuació';

  @override
  String get needMicrophonePermission =>
      'Necessitem permís del micròfon.\n\n1. Toqueu \"Atorgar permís\"\n2. Permeteu al vostre iPhone\n3. L\'aplicació del rellotge es tancarà\n4. Torneu a obrir-la i toqueu \"Continuar\"';

  @override
  String get grantPermissionButton => 'Atorgar permís';

  @override
  String get needHelp => 'Necessiteu ajuda?';

  @override
  String get troubleshootingSteps =>
      'Resolució de problemes:\n\n1. Assegureu-vos que Omi està instal·lat al vostre rellotge\n2. Obriu l\'aplicació Omi al vostre rellotge\n3. Busqueu la finestra emergent de permisos\n4. Toqueu \"Permetre\" quan se us demani\n5. L\'aplicació al vostre rellotge es tancarà - torneu a obrir-la\n6. Torneu i toqueu \"Continuar\" al vostre iPhone';

  @override
  String get recordingStartedSuccessfully => 'Enregistrament iniciat correctament!';

  @override
  String get permissionNotGrantedYet =>
      'Permís encara no atorgat. Assegureu-vos que heu permès l\'accés al micròfon i heu tornat a obrir l\'aplicació al vostre rellotge.';

  @override
  String errorRequestingPermission(String error) {
    return 'Error en sol·licitar permís: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'Error en iniciar l\'enregistrament: $error';
  }

  @override
  String get selectPrimaryLanguage => 'Seleccioneu el vostre idioma principal';

  @override
  String get languageBenefits =>
      'Establiu el vostre idioma per a transcripcions més precises i una experiència personalitzada';

  @override
  String get whatsYourPrimaryLanguage => 'Quin és el vostre idioma principal?';

  @override
  String get selectYourLanguage => 'Seleccioneu el vostre idioma';

  @override
  String get personalGrowthJourney => 'El teu viatge de creixement personal amb IA que escolta cada paraula teva.';

  @override
  String get actionItemsTitle => 'Tasques';

  @override
  String get actionItemsDescription => 'Toqueu per editar • Manteniu per seleccionar • Llisqueu per a accions';

  @override
  String get tabToDo => 'Per fer';

  @override
  String get tabDone => 'Fet';

  @override
  String get tabOld => 'Antic';

  @override
  String get emptyTodoMessage => '🎉 Tot al dia!\nNo hi ha tasques pendents';

  @override
  String get emptyDoneMessage => 'Encara no hi ha elements completats';

  @override
  String get emptyOldMessage => '✅ No hi ha tasques antigues';

  @override
  String get noItems => 'No hi ha elements';

  @override
  String get actionItemMarkedIncomplete => 'Tasca marcada com a incompleta';

  @override
  String get actionItemCompleted => 'Tasca completada';

  @override
  String get deleteActionItemTitle => 'Elimina element d\'acció';

  @override
  String get deleteActionItemMessage => 'Estàs segur que vols eliminar aquest element d\'acció?';

  @override
  String get deleteSelectedItemsTitle => 'Eliminar elements seleccionats';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Esteu segur que voleu eliminar $count tasca$s seleccionada$s?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'Tasca \"$description\" eliminada';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count tasca$s eliminada$s';
  }

  @override
  String get failedToDeleteItem => 'No s\'ha pogut eliminar la tasca';

  @override
  String get failedToDeleteItems => 'No s\'han pogut eliminar els elements';

  @override
  String get failedToDeleteSomeItems => 'No s\'han pogut eliminar alguns elements';

  @override
  String get welcomeActionItemsTitle => 'Llest per a les tasques';

  @override
  String get welcomeActionItemsDescription =>
      'La vostra IA extraurà automàticament tasques de les vostres converses. Apareixeran aquí quan es creïn.';

  @override
  String get autoExtractionFeature => 'Extret automàticament de converses';

  @override
  String get editSwipeFeature => 'Toqueu per editar, llisqueu per completar o eliminar';

  @override
  String itemsSelected(int count) {
    return '$count seleccionats';
  }

  @override
  String get selectAll => 'Seleccionar tot';

  @override
  String get deleteSelected => 'Eliminar seleccionats';

  @override
  String get searchMemories => 'Cerca records...';

  @override
  String get memoryDeleted => 'Record eliminat.';

  @override
  String get undo => 'Desfer';

  @override
  String get noMemoriesYet => '🧠 Encara no hi ha records';

  @override
  String get noAutoMemories => 'Encara no hi ha records extrets automàticament';

  @override
  String get noManualMemories => 'Encara no hi ha records manuals';

  @override
  String get noMemoriesInCategories => 'No hi ha records en aquestes categories';

  @override
  String get noMemoriesFound => '🔍 No s\'han trobat records';

  @override
  String get addFirstMemory => 'Afegiu el vostre primer record';

  @override
  String get clearMemoryTitle => 'Esborrar la memòria d\'Omi';

  @override
  String get clearMemoryMessage => 'Esteu segur que voleu esborrar la memòria d\'Omi? Aquesta acció no es pot desfer.';

  @override
  String get clearMemoryButton => 'Esborrar memòria';

  @override
  String get memoryClearedSuccess => 'La memòria d\'Omi sobre vós s\'ha esborrat';

  @override
  String get noMemoriesToDelete => 'No hi ha records per eliminar';

  @override
  String get createMemoryTooltip => 'Crear nou record';

  @override
  String get createActionItemTooltip => 'Crear nova tasca';

  @override
  String get memoryManagement => 'Gestió de memòria';

  @override
  String get filterMemories => 'Filtrar records';

  @override
  String totalMemoriesCount(int count) {
    return 'Teniu $count records en total';
  }

  @override
  String get publicMemories => 'Records públics';

  @override
  String get privateMemories => 'Records privats';

  @override
  String get makeAllPrivate => 'Fer tots els records privats';

  @override
  String get makeAllPublic => 'Fer tots els records públics';

  @override
  String get deleteAllMemories => 'Eliminar tots els records';

  @override
  String get allMemoriesPrivateResult => 'Tots els records són ara privats';

  @override
  String get allMemoriesPublicResult => 'Tots els records són ara públics';

  @override
  String get newMemory => '✨ Nova memòria';

  @override
  String get editMemory => '✏️ Edita memòria';

  @override
  String get memoryContentHint => 'M\'agrada menjar gelat...';

  @override
  String get failedToSaveMemory => 'No s\'ha pogut desar. Comproveu la vostra connexió.';

  @override
  String get saveMemory => 'Desar record';

  @override
  String get retry => 'Retry';

  @override
  String get createActionItem => 'Crear tasca';

  @override
  String get editActionItem => 'Editar tasca';

  @override
  String get actionItemDescriptionHint => 'Què cal fer?';

  @override
  String get actionItemDescriptionEmpty => 'La descripció de la tasca no pot estar buida.';

  @override
  String get actionItemUpdated => 'Tasca actualitzada';

  @override
  String get failedToUpdateActionItem => 'Error en actualitzar la tasca';

  @override
  String get actionItemCreated => 'Tasca creada';

  @override
  String get failedToCreateActionItem => 'Error en crear la tasca';

  @override
  String get dueDate => 'Data de venciment';

  @override
  String get time => 'Hora';

  @override
  String get addDueDate => 'Afegir data de venciment';

  @override
  String get pressDoneToSave => 'Premeu fet per desar';

  @override
  String get pressDoneToCreate => 'Premeu fet per crear';

  @override
  String get filterAll => 'Tot';

  @override
  String get filterSystem => 'Sobre vós';

  @override
  String get filterInteresting => 'Informacions';

  @override
  String get filterManual => 'Manual';

  @override
  String get completed => 'Completat';

  @override
  String get markComplete => 'Marca com a completat';

  @override
  String get actionItemDeleted => 'Element d\'acció eliminat';

  @override
  String get failedToDeleteActionItem => 'Error en eliminar la tasca';

  @override
  String get deleteActionItemConfirmTitle => 'Eliminar tasca';

  @override
  String get deleteActionItemConfirmMessage => 'Esteu segur que voleu eliminar aquesta tasca?';

  @override
  String get appLanguage => 'Idioma de l\'aplicació';

  @override
  String get appInterfaceSectionTitle => 'INTERFÍCIE DE L\'APLICACIÓ';

  @override
  String get speechTranscriptionSectionTitle => 'VEU I TRANSCRIPCIÓ';

  @override
  String get languageSettingsHelperText =>
      'L\'idioma de l\'aplicació canvia els menús i els botons. L\'idioma de la veu afecta com es transcriuen les teves gravacions.';

  @override
  String get translationNotice => 'Avís de traducció';

  @override
  String get translationNoticeMessage =>
      'Omi tradueix les converses al teu idioma principal. Actualitza-ho en qualsevol moment a Configuració → Perfils.';

  @override
  String get pleaseCheckInternetConnection => 'Si us plau, comprova la teva connexió a Internet i torna-ho a intentar';

  @override
  String get pleaseSelectReason => 'Si us plau, selecciona un motiu';

  @override
  String get tellUsMoreWhatWentWrong => 'Explica\'ns més sobre què va anar malament...';

  @override
  String get selectText => 'Seleccionar text';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Màxim $count objectius permesos';
  }

  @override
  String get conversationCannotBeMerged => 'Aquesta conversa no es pot fusionar (bloquejada o ja en procés de fusió)';

  @override
  String get pleaseEnterFolderName => 'Si us plau, introdueix un nom de carpeta';

  @override
  String get failedToCreateFolder => 'No s\'ha pogut crear la carpeta';

  @override
  String get failedToUpdateFolder => 'No s\'ha pogut actualitzar la carpeta';

  @override
  String get folderName => 'Nom de la carpeta';

  @override
  String get descriptionOptional => 'Descripció (opcional)';

  @override
  String get failedToDeleteFolder => 'No s\'ha pogut eliminar la carpeta';

  @override
  String get editFolder => 'Edita la carpeta';

  @override
  String get deleteFolder => 'Elimina la carpeta';

  @override
  String get transcriptCopiedToClipboard => 'Transcripció copiada al porta-retalls';

  @override
  String get summaryCopiedToClipboard => 'Resum copiat al porta-retalls';

  @override
  String get conversationUrlCouldNotBeShared => 'No s\'ha pogut compartir l\'URL de la conversa.';

  @override
  String get urlCopiedToClipboard => 'URL copiat al porta-retalls';

  @override
  String get exportTranscript => 'Exportar transcripció';

  @override
  String get exportSummary => 'Exportar resum';

  @override
  String get exportButton => 'Exportar';

  @override
  String get actionItemsCopiedToClipboard => 'Elements d\'acció copiats al porta-retalls';

  @override
  String get summarize => 'Resumir';

  @override
  String get generateSummary => 'Generar resum';

  @override
  String get conversationNotFoundOrDeleted => 'Conversa no trobada o ha estat eliminada';

  @override
  String get deleteMemory => 'Eliminar memòria';

  @override
  String get thisActionCannotBeUndone => 'Aquesta acció no es pot desfer.';

  @override
  String memoriesCount(int count) {
    return '$count memòries';
  }

  @override
  String get noMemoriesInCategory => 'Encara no hi ha memòries en aquesta categoria';

  @override
  String get addYourFirstMemory => 'Afegeix el teu primer record';

  @override
  String get firmwareDisconnectUsb => 'Desconnecta USB';

  @override
  String get firmwareUsbWarning => 'La connexió USB durant les actualitzacions pot fer malbé el teu dispositiu.';

  @override
  String get firmwareBatteryAbove15 => 'Bateria superior al 15%';

  @override
  String get firmwareEnsureBattery => 'Assegura\'t que el teu dispositiu té un 15% de bateria.';

  @override
  String get firmwareStableConnection => 'Connexió estable';

  @override
  String get firmwareConnectWifi => 'Connecta\'t a WiFi o dades mòbils.';

  @override
  String failedToStartUpdate(String error) {
    return 'Error en iniciar l\'actualització: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'Abans d\'actualitzar, assegura\'t:';

  @override
  String get confirmed => 'Confirmat!';

  @override
  String get release => 'Allibera';

  @override
  String get slideToUpdate => 'Llisca per actualitzar';

  @override
  String copiedToClipboard(String title) {
    return '$title copiat al portapapers';
  }

  @override
  String get batteryLevel => 'Nivell de bateria';

  @override
  String get productUpdate => 'Actualització del producte';

  @override
  String get offline => 'Fora de línia';

  @override
  String get available => 'Disponible';

  @override
  String get unpairDeviceDialogTitle => 'Desvincula el dispositiu';

  @override
  String get unpairDeviceDialogMessage =>
      'Això desvinculará el dispositiu perquè pugui connectar-se a un altre telèfon. Hauràs d\'anar a Configuració > Bluetooth i oblidar el dispositiu per completar el procés.';

  @override
  String get unpair => 'Desvincula';

  @override
  String get unpairAndForgetDevice => 'Desvincula i oblida el dispositiu';

  @override
  String get unknownDevice => 'Dispositiu desconegut';

  @override
  String get unknown => 'Desconegut';

  @override
  String get productName => 'Nom del producte';

  @override
  String get serialNumber => 'Número de sèrie';

  @override
  String get connected => 'Connectat';

  @override
  String get privacyPolicyTitle => 'Política de privadesa';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label copiat';
  }

  @override
  String get noApiKeysYet => 'Encara no hi ha claus API. Crea\'n una per integrar-la amb la teva aplicació.';

  @override
  String get createKeyToGetStarted => 'Crea una clau per començar';

  @override
  String get persona => 'Persona';

  @override
  String get configureYourAiPersona => 'Configura el teu personatge d\'IA';

  @override
  String get configureSttProvider => 'Configura el proveïdor STT';

  @override
  String get setWhenConversationsAutoEnd => 'Estableix quan les converses acaben automàticament';

  @override
  String get importDataFromOtherSources => 'Importa dades d\'altres fonts';

  @override
  String get debugAndDiagnostics => 'Depuració i Diagnòstics';

  @override
  String get autoDeletesAfter3Days => 'S\'elimina automàticament després de 3 dies';

  @override
  String get helpsDiagnoseIssues => 'Ajuda a diagnosticar problemes';

  @override
  String get exportStartedMessage => 'L\'exportació ha començat. Això pot trigar uns segons...';

  @override
  String get exportConversationsToJson => 'Exporta les converses a un fitxer JSON';

  @override
  String get knowledgeGraphDeletedSuccess => 'Graf de coneixement eliminat correctament';

  @override
  String failedToDeleteGraph(String error) {
    return 'Error en eliminar el graf: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'Esborra tots els nodes i connexions';

  @override
  String get addToClaudeDesktopConfig => 'Afegeix a claude_desktop_config.json';

  @override
  String get connectAiAssistantsToData => 'Connecta assistents d\'IA a les teves dades';

  @override
  String get useYourMcpApiKey => 'Utilitza la teva clau API MCP';

  @override
  String get realTimeTranscript => 'Transcripció en Temps Real';

  @override
  String get experimental => 'Experimental';

  @override
  String get transcriptionDiagnostics => 'Diagnòstics de Transcripció';

  @override
  String get detailedDiagnosticMessages => 'Missatges de diagnòstic detallats';

  @override
  String get autoCreateSpeakers => 'Crea Parlants Automàticament';

  @override
  String get autoCreateWhenNameDetected => 'Crea automàticament quan es detecti un nom';

  @override
  String get followUpQuestions => 'Preguntes de Seguiment';

  @override
  String get suggestQuestionsAfterConversations => 'Suggerir preguntes després de les converses';

  @override
  String get goalTracker => 'Seguidor d\'Objectius';

  @override
  String get trackPersonalGoalsOnHomepage => 'Segueix els teus objectius personals a la pàgina d\'inici';

  @override
  String get dailyReflection => 'Reflexió diària';

  @override
  String get get9PmReminderToReflect => 'Rep un recordatori a les 21:00 per reflexionar sobre el teu dia';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'La descripció de l\'element d\'acció no pot estar buida';

  @override
  String get saved => 'Desat';

  @override
  String get overdue => 'Endarrerit';

  @override
  String get failedToUpdateDueDate => 'No s\'ha pogut actualitzar la data de venciment';

  @override
  String get markIncomplete => 'Marca com a incomplet';

  @override
  String get editDueDate => 'Edita data de venciment';

  @override
  String get setDueDate => 'Establir data de venciment';

  @override
  String get clearDueDate => 'Esborra data de venciment';

  @override
  String get failedToClearDueDate => 'No s\'ha pogut esborrar la data de venciment';

  @override
  String get mondayAbbr => 'Dl';

  @override
  String get tuesdayAbbr => 'Dt';

  @override
  String get wednesdayAbbr => 'Dc';

  @override
  String get thursdayAbbr => 'Dj';

  @override
  String get fridayAbbr => 'Dv';

  @override
  String get saturdayAbbr => 'Ds';

  @override
  String get sundayAbbr => 'Dg';

  @override
  String get howDoesItWork => 'Com funciona?';

  @override
  String get sdCardSyncDescription => 'SD Card Sync importarà els teus records de la targeta SD a l\'aplicació';

  @override
  String get checksForAudioFiles => 'Comprova els fitxers d\'àudio a la targeta SD';

  @override
  String get omiSyncsAudioFiles => 'Omi després sincronitza els fitxers d\'àudio amb el servidor';

  @override
  String get serverProcessesAudio => 'El servidor processa els fitxers d\'àudio i crea records';

  @override
  String get youreAllSet => 'Estàs a punt!';

  @override
  String get welcomeToOmiDescription =>
      'Benvingut a Omi! El teu company d\'IA està preparat per ajudar-te amb converses, tasques i molt més.';

  @override
  String get startUsingOmi => 'Comença a utilitzar Omi';

  @override
  String get back => 'Enrere';

  @override
  String get keyboardShortcuts => 'Dreceres de Teclat';

  @override
  String get toggleControlBar => 'Commuta la barra de control';

  @override
  String get pressKeys => 'Prem tecles...';

  @override
  String get cmdRequired => '⌘ necessari';

  @override
  String get invalidKey => 'Tecla no vàlida';

  @override
  String get space => 'Espai';

  @override
  String get search => 'Cerca';

  @override
  String get searchPlaceholder => 'Cerca...';

  @override
  String get untitledConversation => 'Conversa sense títol';

  @override
  String countRemaining(String count) {
    return '$count restants';
  }

  @override
  String get addGoal => 'Afegir objectiu';

  @override
  String get editGoal => 'Editar objectiu';

  @override
  String get icon => 'Icona';

  @override
  String get goalTitle => 'Títol de l\'objectiu';

  @override
  String get current => 'Actual';

  @override
  String get target => 'Objectiu';

  @override
  String get saveGoal => 'Desa';

  @override
  String get goals => 'Objectius';

  @override
  String get tapToAddGoal => 'Toca per afegir un objectiu';

  @override
  String welcomeBack(String name) {
    return 'Benvingut de nou, $name';
  }

  @override
  String get yourConversations => 'Les teves converses';

  @override
  String get reviewAndManageConversations => 'Revisa i gestiona les teves converses capturades';

  @override
  String get startCapturingConversations =>
      'Comença a capturar converses amb el teu dispositiu Omi per veure-les aquí.';

  @override
  String get useMobileAppToCapture => 'Utilitza la teva aplicació mòbil per capturar àudio';

  @override
  String get conversationsProcessedAutomatically => 'Les converses es processen automàticament';

  @override
  String get getInsightsInstantly => 'Obtén informació i resums a l\'instant';

  @override
  String get showAll => 'Mostra-ho tot →';

  @override
  String get noTasksForToday => 'No hi ha tasques per avui.\\nDemana a Omi més tasques o crea-les manualment.';

  @override
  String get dailyScore => 'PUNTUACIÓ DIÀRIA';

  @override
  String get dailyScoreDescription => 'Una puntuació per ajudar-te\na centrar-te en l\'execució.';

  @override
  String get searchResults => 'Resultats de la cerca';

  @override
  String get actionItems => 'Elements d\'acció';

  @override
  String get tasksToday => 'Avui';

  @override
  String get tasksTomorrow => 'Demà';

  @override
  String get tasksNoDeadline => 'Sense termini';

  @override
  String get tasksLater => 'Més tard';

  @override
  String get loadingTasks => 'Carregant tasques...';

  @override
  String get tasks => 'Tasques';

  @override
  String get swipeTasksToIndent => 'Llisqueu les tasques per sagnar, arrossegueu entre categories';

  @override
  String get create => 'Crear';

  @override
  String get noTasksYet => 'Encara no hi ha tasques';

  @override
  String get tasksFromConversationsWillAppear =>
      'Les tasques de les vostres converses apareixeran aquí.\nFeu clic a Crear per afegir-ne una manualment.';

  @override
  String get monthJan => 'Gen';

  @override
  String get monthFeb => 'Febr';

  @override
  String get monthMar => 'Març';

  @override
  String get monthApr => 'Abr';

  @override
  String get monthMay => 'Maig';

  @override
  String get monthJun => 'Juny';

  @override
  String get monthJul => 'Jul';

  @override
  String get monthAug => 'Ag';

  @override
  String get monthSep => 'Set';

  @override
  String get monthOct => 'Oct';

  @override
  String get monthNov => 'Nov';

  @override
  String get monthDec => 'Des';

  @override
  String get timePM => 'PM';

  @override
  String get timeAM => 'AM';

  @override
  String get actionItemUpdatedSuccessfully => 'Tasca actualitzada correctament';

  @override
  String get actionItemCreatedSuccessfully => 'Tasca creada correctament';

  @override
  String get actionItemDeletedSuccessfully => 'Tasca eliminada correctament';

  @override
  String get deleteActionItem => 'Eliminar tasca';

  @override
  String get deleteActionItemConfirmation =>
      'Esteu segur que voleu eliminar aquesta tasca? Aquesta acció no es pot desfer.';

  @override
  String get enterActionItemDescription => 'Introduïu la descripció de la tasca...';

  @override
  String get markAsCompleted => 'Marcar com a completada';

  @override
  String get setDueDateAndTime => 'Establir data i hora de venciment';

  @override
  String get reloadingApps => 'Recarregant aplicacions...';

  @override
  String get loadingApps => 'Carregant aplicacions...';

  @override
  String get browseInstallCreateApps => 'Explora, instal·la i crea aplicacions';

  @override
  String get all => 'All';

  @override
  String get open => 'Obrir';

  @override
  String get install => 'Instal·la';

  @override
  String get noAppsAvailable => 'No hi ha aplicacions disponibles';

  @override
  String get unableToLoadApps => 'No es poden carregar les aplicacions';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'Prova d\'ajustar els termes de cerca o els filtres';

  @override
  String get checkBackLaterForNewApps => 'Torna més tard per veure aplicacions noves';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain =>
      'Si us plau, comprova la connexió a Internet i torna-ho a provar';

  @override
  String get createNewApp => 'Crear nova aplicació';

  @override
  String get buildSubmitCustomOmiApp => 'Construeix i envia la teva aplicació Omi personalitzada';

  @override
  String get submittingYourApp => 'Enviant la teva aplicació...';

  @override
  String get preparingFormForYou => 'Preparant el formulari per a tu...';

  @override
  String get appDetails => 'Detalls de l\'aplicació';

  @override
  String get paymentDetails => 'Detalls de pagament';

  @override
  String get previewAndScreenshots => 'Vista prèvia i captures de pantalla';

  @override
  String get appCapabilities => 'Capacitats de l\'aplicació';

  @override
  String get aiPrompts => 'Indicacions d\'IA';

  @override
  String get chatPrompt => 'Indicació de xat';

  @override
  String get chatPromptPlaceholder =>
      'Ets una aplicació increïble, la teva feina és respondre a les consultes de l\'usuari i fer que se sentin bé...';

  @override
  String get conversationPrompt => 'Indicació de conversa';

  @override
  String get conversationPromptPlaceholder =>
      'Ets una aplicació increïble, rebràs una transcripció i resum d\'una conversa...';

  @override
  String get notificationScopes => 'Àmbits de notificació';

  @override
  String get appPrivacyAndTerms => 'Privadesa i condicions de l\'aplicació';

  @override
  String get makeMyAppPublic => 'Fes pública la meva aplicació';

  @override
  String get submitAppTermsAgreement =>
      'En enviar aquesta aplicació, accepto les Condicions de Servei i la Política de Privadesa d\'Omi AI';

  @override
  String get submitApp => 'Enviar aplicació';

  @override
  String get needHelpGettingStarted => 'Necessites ajuda per començar?';

  @override
  String get clickHereForAppBuildingGuides => 'Fes clic aquí per a guies de creació d\'aplicacions i documentació';

  @override
  String get submitAppQuestion => 'Enviar aplicació?';

  @override
  String get submitAppPublicDescription =>
      'La teva aplicació serà revisada i feta pública. Pots començar a utilitzar-la immediatament, fins i tot durant la revisió!';

  @override
  String get submitAppPrivateDescription =>
      'La teva aplicació serà revisada i feta disponible per a tu de manera privada. Pots començar a utilitzar-la immediatament, fins i tot durant la revisió!';

  @override
  String get startEarning => 'Comença a guanyar! 💰';

  @override
  String get connectStripeOrPayPal => 'Connecta Stripe o PayPal per rebre pagaments per la teva aplicació.';

  @override
  String get connectNow => 'Connecta ara';

  @override
  String get installsCount => 'Instal·lacions';

  @override
  String get uninstallApp => 'Desinstal·la l\'aplicació';

  @override
  String get subscribe => 'Subscriu-te';

  @override
  String get dataAccessNotice => 'Avís d\'accés a dades';

  @override
  String get dataAccessWarning =>
      'Aquesta aplicació accedirà a les teves dades. Omi AI no és responsable de com s\'utilitzen, modifiquen o eliminen les teves dades per aquesta aplicació';

  @override
  String get installApp => 'Instal·la l\'aplicació';

  @override
  String get betaTesterNotice =>
      'Ets provador beta d\'aquesta aplicació. Encara no és pública. Serà pública un cop aprovada.';

  @override
  String get appUnderReviewOwner =>
      'La teva aplicació està en revisió i només visible per a tu. Serà pública un cop aprovada.';

  @override
  String get appRejectedNotice =>
      'La teva aplicació ha estat rebutjada. Si us plau, actualitza els detalls de l\'aplicació i torna-la a enviar per a revisió.';

  @override
  String get setupSteps => 'Passos de configuració';

  @override
  String get setupInstructions => 'Instruccions de configuració';

  @override
  String get integrationInstructions => 'Instruccions d\'integració';

  @override
  String get preview => 'Previsualització';

  @override
  String get aboutTheApp => 'Sobre l\'app';

  @override
  String get aboutThePersona => 'Sobre la persona';

  @override
  String get chatPersonality => 'Personalitat del xat';

  @override
  String get ratingsAndReviews => 'Valoracions i ressenyes';

  @override
  String get noRatings => 'sense valoracions';

  @override
  String ratingsCount(String count) {
    return '$count+ valoracions';
  }

  @override
  String get errorActivatingApp => 'Error en activar l\'aplicació';

  @override
  String get integrationSetupRequired =>
      'Si aquesta és una aplicació d\'integració, assegura\'t que la configuració està completada.';

  @override
  String get installed => 'Instal·lat';

  @override
  String get appIdLabel => 'ID de l\'aplicació';

  @override
  String get appNameLabel => 'Nom de l\'aplicació';

  @override
  String get appNamePlaceholder => 'La meva aplicació fantàstica';

  @override
  String get pleaseEnterAppName => 'Si us plau, introduïu el nom de l\'aplicació';

  @override
  String get categoryLabel => 'Categoria';

  @override
  String get selectCategory => 'Seleccioneu categoria';

  @override
  String get descriptionLabel => 'Descripció';

  @override
  String get appDescriptionPlaceholder =>
      'La meva aplicació fantàstica és una aplicació genial que fa coses increïbles. És la millor aplicació!';

  @override
  String get pleaseProvideValidDescription => 'Si us plau, proporcioneu una descripció vàlida';

  @override
  String get appPricingLabel => 'Preu de l\'aplicació';

  @override
  String get noneSelected => 'Cap seleccionat';

  @override
  String get appIdCopiedToClipboard => 'ID de l\'aplicació copiat al porta-retalls';

  @override
  String get appCategoryModalTitle => 'Categoria de l\'aplicació';

  @override
  String get pricingFree => 'Gratuït';

  @override
  String get pricingPaid => 'De pagament';

  @override
  String get loadingCapabilities => 'Carregant capacitats...';

  @override
  String get filterInstalled => 'Instal·lades';

  @override
  String get filterMyApps => 'Les meves aplicacions';

  @override
  String get clearSelection => 'Esborrar selecció';

  @override
  String get filterCategory => 'Categoria';

  @override
  String get rating4PlusStars => '4+ estrelles';

  @override
  String get rating3PlusStars => '3+ estrelles';

  @override
  String get rating2PlusStars => '2+ estrelles';

  @override
  String get rating1PlusStars => '1+ estrelles';

  @override
  String get filterRating => 'Valoració';

  @override
  String get filterCapabilities => 'Capacitats';

  @override
  String get noNotificationScopesAvailable => 'No hi ha àmbits de notificació disponibles';

  @override
  String get popularApps => 'Aplicacions populars';

  @override
  String get pleaseProvidePrompt => 'Si us plau, proporcioneu una indicació';

  @override
  String chatWithAppName(String appName) {
    return 'Xat amb $appName';
  }

  @override
  String get defaultAiAssistant => 'Assistent d\'IA per defecte';

  @override
  String get readyToChat => '✨ Llest per xatejar!';

  @override
  String get connectionNeeded => '🌐 Connexió necessària';

  @override
  String get startConversation => 'Comença una conversa i deixa que la màgia comenci';

  @override
  String get checkInternetConnection => 'Si us plau, comprova la teva connexió a Internet';

  @override
  String get wasThisHelpful => 'Ha estat útil?';

  @override
  String get thankYouForFeedback => 'Gràcies pels teus comentaris!';

  @override
  String get maxFilesUploadError => 'Només pots pujar 4 fitxers a la vegada';

  @override
  String get attachedFiles => '📎 Fitxers adjunts';

  @override
  String get takePhoto => 'Fer foto';

  @override
  String get captureWithCamera => 'Capturar amb la càmera';

  @override
  String get selectImages => 'Seleccionar imatges';

  @override
  String get chooseFromGallery => 'Triar de la galeria';

  @override
  String get selectFile => 'Seleccionar un fitxer';

  @override
  String get chooseAnyFileType => 'Triar qualsevol tipus de fitxer';

  @override
  String get cannotReportOwnMessages => 'No pots informar dels teus propis missatges';

  @override
  String get messageReportedSuccessfully => '✅ Missatge informat correctament';

  @override
  String get confirmReportMessage => 'Estàs segur que vols informar d\'aquest missatge?';

  @override
  String get selectChatAssistant => 'Seleccionar assistent de xat';

  @override
  String get enableMoreApps => 'Activar més aplicacions';

  @override
  String get chatCleared => 'Xat esborrat';

  @override
  String get clearChatTitle => 'Esborrar el xat?';

  @override
  String get confirmClearChat => 'Estàs segur que vols esborrar el xat? Aquesta acció no es pot desfer.';

  @override
  String get copy => 'Copiar';

  @override
  String get share => 'Compartir';

  @override
  String get report => 'Informar';

  @override
  String get microphonePermissionRequired => 'Es requereix permís de micròfon per a l\'enregistrament de veu.';

  @override
  String get microphonePermissionDenied =>
      'Permís de micròfon denegat. Si us plau, concediu permís a Preferències del Sistema > Privacitat i Seguretat > Micròfon.';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'Error en comprovar el permís del micròfon: $error';
  }

  @override
  String get failedToTranscribeAudio => 'Error en transcriure l\'àudio';

  @override
  String get transcribing => 'Transcrivint...';

  @override
  String get transcriptionFailed => 'Transcripció fallida';

  @override
  String get discardedConversation => 'Conversa descartada';

  @override
  String get at => 'a';

  @override
  String get from => 'des de';

  @override
  String get copied => 'Copiat!';

  @override
  String get copyLink => 'Copiar enllaç';

  @override
  String get hideTranscript => 'Amagar transcripció';

  @override
  String get viewTranscript => 'Veure transcripció';

  @override
  String get conversationDetails => 'Detalls de la conversa';

  @override
  String get transcript => 'Transcripció';

  @override
  String segmentsCount(int count) {
    return '$count segments';
  }

  @override
  String get noTranscriptAvailable => 'No hi ha transcripció disponible';

  @override
  String get noTranscriptMessage => 'Aquesta conversa no té transcripció.';

  @override
  String get conversationUrlCouldNotBeGenerated => 'No s\'ha pogut generar l\'URL de la conversa.';

  @override
  String get failedToGenerateConversationLink => 'No s\'ha pogut generar l\'enllaç de la conversa';

  @override
  String get failedToGenerateShareLink => 'No s\'ha pogut generar l\'enllaç per compartir';

  @override
  String get reloadingConversations => 'Recarregant converses...';

  @override
  String get user => 'Usuari';

  @override
  String get starred => 'Destacat';

  @override
  String get date => 'Data';

  @override
  String get noResultsFound => 'No s\'han trobat resultats';

  @override
  String get tryAdjustingSearchTerms => 'Prova d\'ajustar els termes de cerca';

  @override
  String get starConversationsToFindQuickly => 'Destaca converses per trobar-les ràpidament aquí';

  @override
  String noConversationsOnDate(String date) {
    return 'No hi ha converses el $date';
  }

  @override
  String get trySelectingDifferentDate => 'Prova de seleccionar una altra data';

  @override
  String get conversations => 'Converses';

  @override
  String get chat => 'Xat';

  @override
  String get actions => 'Accions';

  @override
  String get syncAvailable => 'Sincronització disponible';

  @override
  String get referAFriend => 'Recomana a un amic';

  @override
  String get help => 'Ajuda';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'Actualitza a Pro';

  @override
  String get getOmiDevice => 'Get Omi Device';

  @override
  String get wearableAiCompanion => 'Company d\'IA portàtil';

  @override
  String get loadingMemories => 'Carregant records...';

  @override
  String get allMemories => 'Tots els records';

  @override
  String get aboutYou => 'Sobre tu';

  @override
  String get manual => 'Manual';

  @override
  String get loadingYourMemories => 'Carregant els teus records...';

  @override
  String get createYourFirstMemory => 'Crea el teu primer record per començar';

  @override
  String get tryAdjustingFilter => 'Prova d\'ajustar la cerca o el filtre';

  @override
  String get whatWouldYouLikeToRemember => 'Què vols recordar?';

  @override
  String get category => 'Categoria';

  @override
  String get public => 'Públic';

  @override
  String get failedToSaveCheckConnection => 'Error en desar. Comprova la connexió.';

  @override
  String get createMemory => 'Crear memòria';

  @override
  String get deleteMemoryConfirmation =>
      'Estàs segur que vols eliminar aquesta memòria? Aquesta acció no es pot desfer.';

  @override
  String get makePrivate => 'Fer privat';

  @override
  String get organizeAndControlMemories => 'Organitza i controla els teus records';

  @override
  String get total => 'Total';

  @override
  String get makeAllMemoriesPrivate => 'Fer privats tots els records';

  @override
  String get setAllMemoriesToPrivate => 'Establir tots els records com a privats';

  @override
  String get makeAllMemoriesPublic => 'Fer públics tots els records';

  @override
  String get setAllMemoriesToPublic => 'Establir tots els records com a públics';

  @override
  String get permanentlyRemoveAllMemories => 'Eliminar permanentment tots els records d\'Omi';

  @override
  String get allMemoriesAreNowPrivate => 'Tots els records són ara privats';

  @override
  String get allMemoriesAreNowPublic => 'Tots els records són ara públics';

  @override
  String get clearOmisMemory => 'Esborrar la memòria d\'Omi';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Estàs segur que vols esborrar la memòria d\'Omi? Aquesta acció no es pot desfer i eliminarà permanentment tots els $count records.';
  }

  @override
  String get omisMemoryCleared => 'S\'ha esborrat la memòria d\'Omi sobre tu';

  @override
  String get welcomeToOmi => 'Benvingut a Omi';

  @override
  String get continueWithApple => 'Continua amb Apple';

  @override
  String get continueWithGoogle => 'Continua amb Google';

  @override
  String get byContinuingYouAgree => 'En continuar, acceptes els nostres ';

  @override
  String get termsOfService => 'Termes del servei';

  @override
  String get and => ' i ';

  @override
  String get dataAndPrivacy => 'Dades i privadesa';

  @override
  String get secureAuthViaAppleId => 'Autenticació segura via Apple ID';

  @override
  String get secureAuthViaGoogleAccount => 'Autenticació segura via compte de Google';

  @override
  String get whatWeCollect => 'Què recopilem';

  @override
  String get dataCollectionMessage =>
      'En continuar, les teves converses, enregistraments i informació personal s\'emmagatzemaran de manera segura als nostres servidors per proporcionar informació impulsada per IA i habilitar totes les funcions de l\'aplicació.';

  @override
  String get dataProtection => 'Protecció de dades';

  @override
  String get yourDataIsProtected => 'Les teves dades estan protegides i regides per la nostra ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'Si us plau, seleccioneu la vostra llengua principal';

  @override
  String get chooseYourLanguage => 'Trieu el vostre idioma';

  @override
  String get selectPreferredLanguageForBestExperience =>
      'Seleccioneu el vostre idioma preferit per a la millor experiència Omi';

  @override
  String get searchLanguages => 'Cerca idiomes...';

  @override
  String get selectALanguage => 'Seleccioneu un idioma';

  @override
  String get tryDifferentSearchTerm => 'Proveu un terme de cerca diferent';

  @override
  String get pleaseEnterYourName => 'Si us plau, introduïu el vostre nom';

  @override
  String get nameMustBeAtLeast2Characters => 'El nom ha de tenir almenys 2 caràcters';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'Digueu-nos com us agradaria que us adrecem. Això ajuda a personalitzar la vostra experiència Omi.';

  @override
  String charactersCount(int count) {
    return '$count caràcters';
  }

  @override
  String get enableFeaturesForBestExperience =>
      'Activeu les funcions per a la millor experiència Omi al vostre dispositiu.';

  @override
  String get microphoneAccess => 'Accés al micròfon';

  @override
  String get recordAudioConversations => 'Enregistrar converses d\'àudio';

  @override
  String get microphoneAccessDescription =>
      'Omi necessita accés al micròfon per enregistrar les vostres converses i proporcionar transcripcions.';

  @override
  String get screenRecording => 'Gravació de pantalla';

  @override
  String get captureSystemAudioFromMeetings => 'Capturar àudio del sistema de reunions';

  @override
  String get screenRecordingDescription =>
      'Omi necessita permís de gravació de pantalla per capturar l\'àudio del sistema de les vostres reunions basades en el navegador.';

  @override
  String get accessibility => 'Accessibilitat';

  @override
  String get detectBrowserBasedMeetings => 'Detectar reunions basades en el navegador';

  @override
  String get accessibilityDescription =>
      'Omi necessita permís d\'accessibilitat per detectar quan us uniu a reunions de Zoom, Meet o Teams al vostre navegador.';

  @override
  String get pleaseWait => 'Si us plau, espereu...';

  @override
  String get joinTheCommunity => 'Uneix-te a la comunitat!';

  @override
  String get loadingProfile => 'Carregant perfil...';

  @override
  String get profileSettings => 'Configuració del perfil';

  @override
  String get noEmailSet => 'No hi ha correu electrònic configurat';

  @override
  String get userIdCopiedToClipboard => 'ID d\'usuari copiat';

  @override
  String get yourInformation => 'La Teva Informació';

  @override
  String get setYourName => 'Estableix el vostre nom';

  @override
  String get changeYourName => 'Canvia el vostre nom';

  @override
  String get manageYourOmiPersona => 'Gestiona la teva persona Omi';

  @override
  String get voiceAndPeople => 'Veu i Persones';

  @override
  String get teachOmiYourVoice => 'Ensenya a Omi la teva veu';

  @override
  String get tellOmiWhoSaidIt => 'Digues a Omi qui ho va dir 🗣️';

  @override
  String get payment => 'Pagament';

  @override
  String get addOrChangeYourPaymentMethod => 'Afegeix o canvia el mètode de pagament';

  @override
  String get preferences => 'Preferències';

  @override
  String get helpImproveOmiBySharing => 'Ajuda a millorar Omi compartint dades d\'anàlisi anonimitzades';

  @override
  String get deleteAccount => 'Eliminar Compte';

  @override
  String get deleteYourAccountAndAllData => 'Elimina el compte i totes les dades';

  @override
  String get clearLogs => 'Esborrar registres';

  @override
  String get debugLogsCleared => 'Registres de depuració esborrats';

  @override
  String get exportConversations => 'Exportar converses';

  @override
  String get exportAllConversationsToJson => 'Exporteu totes les vostres converses a un fitxer JSON.';

  @override
  String get conversationsExportStarted =>
      'S\'ha iniciat l\'exportació de converses. Això pot trigar uns segons, espereu.';

  @override
  String get mcpDescription =>
      'Per connectar Omi amb altres aplicacions per llegir, cercar i gestionar els vostres records i converses. Creeu una clau per començar.';

  @override
  String get apiKeys => 'Claus API';

  @override
  String errorLabel(String error) {
    return 'Error: $error';
  }

  @override
  String get noApiKeysFound => 'No s\'han trobat claus API. Creeu-ne una per començar.';

  @override
  String get advancedSettings => 'Configuració avançada';

  @override
  String get triggersWhenNewConversationCreated => 'S\'activa quan es crea una conversa nova.';

  @override
  String get triggersWhenNewTranscriptReceived => 'S\'activa quan es rep una transcripció nova.';

  @override
  String get realtimeAudioBytes => 'Bytes d\'àudio en temps real';

  @override
  String get triggersWhenAudioBytesReceived => 'S\'activa quan es reben bytes d\'àudio.';

  @override
  String get everyXSeconds => 'Cada x segons';

  @override
  String get triggersWhenDaySummaryGenerated => 'S\'activa quan es genera un resum del dia.';

  @override
  String get tryLatestExperimentalFeatures => 'Proveu les últimes funcions experimentals de l\'equip d\'Omi.';

  @override
  String get transcriptionServiceDiagnosticStatus => 'Estat de diagnòstic del servei de transcripció';

  @override
  String get enableDetailedDiagnosticMessages => 'Activeu missatges de diagnòstic detallats del servei de transcripció';

  @override
  String get autoCreateAndTagNewSpeakers => 'Creació i etiquetatge automàtic de parlants nous';

  @override
  String get automaticallyCreateNewPerson =>
      'Crear automàticament una persona nova quan es detecti un nom a la transcripció.';

  @override
  String get pilotFeatures => 'Funcions pilot';

  @override
  String get pilotFeaturesDescription => 'Aquestes funcions són proves i no se\'n garanteix el suport.';

  @override
  String get suggestFollowUpQuestion => 'Suggerir una pregunta de seguiment';

  @override
  String get saveSettings => 'Desa la Configuració';

  @override
  String get syncingDeveloperSettings => 'S\'està sincronitzant la configuració de desenvolupador...';

  @override
  String get summary => 'Resum';

  @override
  String get auto => 'Automàtic';

  @override
  String get noSummaryForApp =>
      'No hi ha resum disponible per a aquesta aplicació. Prova una altra aplicació per obtenir millors resultats.';

  @override
  String get tryAnotherApp => 'Provar una altra aplicació';

  @override
  String generatedBy(String appName) {
    return 'Generat per $appName';
  }

  @override
  String get overview => 'Visió general';

  @override
  String get otherAppResults => 'Resultats d\'altres aplicacions';

  @override
  String get unknownApp => 'Aplicació desconeguda';

  @override
  String get noSummaryAvailable => 'No hi ha cap resum disponible';

  @override
  String get conversationNoSummaryYet => 'Aquesta conversa encara no té resum.';

  @override
  String get chooseSummarizationApp => 'Trieu l\'aplicació de resum';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName s\'ha establert com a aplicació de resum predeterminada';
  }

  @override
  String get letOmiChooseAutomatically => 'Deixeu que Omi esculli automàticament la millor aplicació';

  @override
  String get deleteConversationConfirmation =>
      'Esteu segur que voleu suprimir aquesta conversa? Aquesta acció no es pot desfer.';

  @override
  String get conversationDeleted => 'Conversa suprimida';

  @override
  String get generatingLink => 'Generant enllaç...';

  @override
  String get editConversation => 'Editar conversa';

  @override
  String get conversationLinkCopiedToClipboard => 'Enllaç de la conversa copiat al porta-retalls';

  @override
  String get conversationTranscriptCopiedToClipboard => 'Transcripció de la conversa copiada al porta-retalls';

  @override
  String get editConversationDialogTitle => 'Editar conversa';

  @override
  String get changeTheConversationTitle => 'Canviar el títol de la conversa';

  @override
  String get conversationTitle => 'Títol de la conversa';

  @override
  String get enterConversationTitle => 'Introduïu el títol de la conversa...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'Títol de la conversa actualitzat correctament';

  @override
  String get failedToUpdateConversationTitle => 'No s\'ha pogut actualitzar el títol de la conversa';

  @override
  String get errorUpdatingConversationTitle => 'Error en actualitzar el títol de la conversa';

  @override
  String get settingUp => 'Configurant...';

  @override
  String get startYourFirstRecording => 'Comenceu la vostra primera gravació';

  @override
  String get preparingSystemAudioCapture => 'Preparant la captura d\'àudio del sistema';

  @override
  String get clickTheButtonToCaptureAudio =>
      'Feu clic al botó per capturar àudio per a transcripcions en directe, informació d\'IA i desament automàtic.';

  @override
  String get reconnecting => 'Reconnectant...';

  @override
  String get recordingPaused => 'Gravació en pausa';

  @override
  String get recordingActive => 'Gravació activa';

  @override
  String get startRecording => 'Comença la gravació';

  @override
  String resumingInCountdown(String countdown) {
    return 'Reprenent en ${countdown}s...';
  }

  @override
  String get tapPlayToResume => 'Toqueu reproducció per reprendre';

  @override
  String get listeningForAudio => 'Escoltant àudio...';

  @override
  String get preparingAudioCapture => 'Preparant la captura d\'àudio';

  @override
  String get clickToBeginRecording => 'Feu clic per començar la gravació';

  @override
  String get translated => 'traduït';

  @override
  String get liveTranscript => 'Transcripció en directe';

  @override
  String segmentsSingular(String count) {
    return '$count segment';
  }

  @override
  String segmentsPlural(String count) {
    return '$count segments';
  }

  @override
  String get startRecordingToSeeTranscript => 'Comenceu la gravació per veure la transcripció en directe';

  @override
  String get paused => 'En pausa';

  @override
  String get initializing => 'Inicialitzant...';

  @override
  String get recording => 'Gravant';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'El micròfon ha canviat. Reprenent en ${countdown}s';
  }

  @override
  String get clickPlayToResumeOrStop => 'Feu clic a reproducció per reprendre o atura per acabar';

  @override
  String get settingUpSystemAudioCapture => 'Configurant la captura d\'àudio del sistema';

  @override
  String get capturingAudioAndGeneratingTranscript => 'Capturant àudio i generant transcripció';

  @override
  String get clickToBeginRecordingSystemAudio => 'Feu clic per començar a gravar àudio del sistema';

  @override
  String get you => 'Tu';

  @override
  String speakerWithId(String speakerId) {
    return 'Parlant $speakerId';
  }

  @override
  String get translatedByOmi => 'traduït per omi';

  @override
  String get backToConversations => 'Tornar a Converses';

  @override
  String get systemAudio => 'Sistema';

  @override
  String get mic => 'Micròfon';

  @override
  String audioInputSetTo(String deviceName) {
    return 'Entrada d\'àudio establerta a $deviceName';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'Error en canviar el dispositiu d\'àudio: $error';
  }

  @override
  String get selectAudioInput => 'Seleccioneu l\'entrada d\'àudio';

  @override
  String get loadingDevices => 'Carregant dispositius...';

  @override
  String get settingsHeader => 'CONFIGURACIÓ';

  @override
  String get plansAndBilling => 'Plans i Facturació';

  @override
  String get calendarIntegration => 'Integració de Calendari';

  @override
  String get dailySummary => 'Resum diari';

  @override
  String get developer => 'Desenvolupador';

  @override
  String get about => 'Quant a';

  @override
  String get selectTime => 'Selecciona hora';

  @override
  String get accountGroup => 'Compte';

  @override
  String get signOutQuestion => 'Tancar sessió?';

  @override
  String get signOutConfirmation => 'Are you sure you want to sign out?';

  @override
  String get customVocabularyHeader => 'VOCABULARI PERSONALITZAT';

  @override
  String get addWordsDescription => 'Afegeix paraules que Omi hauria de reconèixer durant la transcripció.';

  @override
  String get enterWordsHint => 'Introdueix paraules (separades per comes)';

  @override
  String get dailySummaryHeader => 'RESUM DIARI';

  @override
  String get dailySummaryTitle => 'Resum Diari';

  @override
  String get dailySummaryDescription => 'Rep un resum personalitzat de les converses del dia com a notificació.';

  @override
  String get deliveryTime => 'Hora de lliurament';

  @override
  String get deliveryTimeDescription => 'Quan rebre el teu resum diari';

  @override
  String get subscription => 'Subscripció';

  @override
  String get viewPlansAndUsage => 'Veure Plans i Ús';

  @override
  String get viewPlansDescription => 'Gestiona la teva subscripció i consulta estadístiques d\'ús';

  @override
  String get addOrChangePaymentMethod => 'Afegeix o canvia el teu mètode de pagament';

  @override
  String get displayOptions => 'Opcions de Visualització';

  @override
  String get showMeetingsInMenuBar => 'Mostra Reunions a la Barra de Menú';

  @override
  String get displayUpcomingMeetingsDescription => 'Mostra les reunions properes a la barra de menú';

  @override
  String get showEventsWithoutParticipants => 'Mostra Esdeveniments Sense Participants';

  @override
  String get includePersonalEventsDescription => 'Inclou esdeveniments personals sense assistents';

  @override
  String get upcomingMeetings => 'Reunions properes';

  @override
  String get checkingNext7Days => 'Comprovant els propers 7 dies';

  @override
  String get shortcuts => 'Dreceres';

  @override
  String get shortcutChangeInstruction => 'Feu clic en una drecera per canviar-la. Premeu Escape per cancel·lar.';

  @override
  String get configurePersonaDescription => 'Configura la teva persona d\'IA';

  @override
  String get configureSTTProvider => 'Configura el proveïdor STT';

  @override
  String get setConversationEndDescription => 'Estableix quan finalitzen automàticament les converses';

  @override
  String get importDataDescription => 'Importa dades d\'altres fonts';

  @override
  String get exportConversationsDescription => 'Exporta converses a JSON';

  @override
  String get exportingConversations => 'Exportant converses...';

  @override
  String get clearNodesDescription => 'Esborra tots els nodes i connexions';

  @override
  String get deleteKnowledgeGraphQuestion => 'Eliminar Gràfic de Coneixement?';

  @override
  String get deleteKnowledgeGraphWarning =>
      'Això eliminarà totes les dades derivades del gràfic de coneixement. Els teus records originals romanen segurs.';

  @override
  String get connectOmiWithAI => 'Connecta Omi amb assistents d\'IA';

  @override
  String get noAPIKeys => 'No hi ha claus API. Crea\'n una per començar.';

  @override
  String get autoCreateWhenDetected => 'Crea automàticament quan es detecti el nom';

  @override
  String get trackPersonalGoals => 'Fes el seguiment d\'objectius personals a la pàgina d\'inici';

  @override
  String get dailyReflectionDescription =>
      'Rep un recordatori a les 21:00 per reflexionar sobre el teu dia i capturar els teus pensaments.';

  @override
  String get endpointURL => 'URL del Punt Final';

  @override
  String get links => 'Enllaços';

  @override
  String get discordMemberCount => 'Més de 8000 membres a Discord';

  @override
  String get userInformation => 'Informació de l\'Usuari';

  @override
  String get capabilities => 'Capacitats';

  @override
  String get previewScreenshots => 'Vista prèvia de captures';

  @override
  String get holdOnPreparingForm => 'Espera, estem preparant el formulari per a tu';

  @override
  String get bySubmittingYouAgreeToOmi => 'En enviar, acceptes Omi ';

  @override
  String get termsAndPrivacyPolicy => 'Termes i Política de Privacitat';

  @override
  String get helpsDiagnoseIssuesAutoDeletes =>
      'Ajuda a diagnosticar problemes. S\'elimina automàticament després de 3 dies.';

  @override
  String get manageYourApp => 'Gestiona la teva aplicació';

  @override
  String get updatingYourApp => 'Actualitzant la teva aplicació';

  @override
  String get fetchingYourAppDetails => 'Obtenint els detalls de la teva aplicació';

  @override
  String get updateAppQuestion => 'Actualitzar l\'aplicació?';

  @override
  String get updateAppConfirmation =>
      'Estàs segur que vols actualitzar la teva aplicació? Els canvis es reflectiran un cop revisats pel nostre equip.';

  @override
  String get updateApp => 'Actualitzar aplicació';

  @override
  String get createAndSubmitNewApp => 'Crea i envia una nova aplicació';

  @override
  String appsCount(String count) {
    return 'Aplicacions ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'Aplicacions privades ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'Aplicacions públiques ($count)';
  }

  @override
  String get newVersionAvailable => 'Nova versió disponible  🎉';

  @override
  String get no => 'No';

  @override
  String get subscriptionCancelledSuccessfully =>
      'Subscripció cancel·lada amb èxit. Romandrà activa fins al final del període de facturació actual.';

  @override
  String get failedToCancelSubscription => 'No s\'ha pogut cancel·lar la subscripció. Torna-ho a provar.';

  @override
  String get invalidPaymentUrl => 'URL de pagament no vàlid';

  @override
  String get permissionsAndTriggers => 'Permisos i activadors';

  @override
  String get chatFeatures => 'Funcions de xat';

  @override
  String get uninstall => 'Desinstal·lar';

  @override
  String get installs => 'INSTAL·LACIONS';

  @override
  String get priceLabel => 'PREU';

  @override
  String get updatedLabel => 'ACTUALITZAT';

  @override
  String get createdLabel => 'CREAT';

  @override
  String get featuredLabel => 'DESTACAT';

  @override
  String get cancelSubscriptionQuestion => 'Cancel·lar subscripció?';

  @override
  String get cancelSubscriptionConfirmation =>
      'Estàs segur que vols cancel·lar la subscripció? Continuaràs tenint accés fins al final del període de facturació actual.';

  @override
  String get cancelSubscriptionButton => 'Cancel·lar subscripció';

  @override
  String get cancelling => 'Cancel·lant...';

  @override
  String get betaTesterMessage =>
      'Ets un provador beta d\'aquesta aplicació. Encara no és pública. Serà pública un cop aprovada.';

  @override
  String get appUnderReviewMessage =>
      'La teva aplicació està en revisió i només és visible per a tu. Serà pública un cop aprovada.';

  @override
  String get appRejectedMessage =>
      'La teva aplicació ha estat rebutjada. Actualitza els detalls i torna a enviar-la per a revisió.';

  @override
  String get invalidIntegrationUrl => 'URL d\'integració no vàlida';

  @override
  String get tapToComplete => 'Toca per completar';

  @override
  String get invalidSetupInstructionsUrl => 'URL d\'instruccions de configuració no vàlida';

  @override
  String get pushToTalk => 'Prem per parlar';

  @override
  String get summaryPrompt => 'Prompt de resum';

  @override
  String get pleaseSelectARating => 'Si us plau, selecciona una valoració';

  @override
  String get reviewAddedSuccessfully => 'Ressenya afegida amb èxit 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'Ressenya actualitzada amb èxit 🚀';

  @override
  String get failedToSubmitReview => 'Error en enviar la ressenya. Si us plau, torna-ho a provar.';

  @override
  String get addYourReview => 'Afegeix la teva ressenya';

  @override
  String get editYourReview => 'Edita la teva ressenya';

  @override
  String get writeAReviewOptional => 'Escriu una ressenya (opcional)';

  @override
  String get submitReview => 'Enviar ressenya';

  @override
  String get updateReview => 'Actualitzar ressenya';

  @override
  String get yourReview => 'La teva ressenya';

  @override
  String get anonymousUser => 'Usuari anònim';

  @override
  String get issueActivatingApp => 'Hi ha hagut un problema en activar aquesta aplicació. Torna-ho a provar.';

  @override
  String get dataAccessNoticeDescription =>
      'This app will access your data. Omi AI is not responsible for how your data is used, modified, or deleted by this app';

  @override
  String get copyUrl => 'Copia l\'URL';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => 'Dl';

  @override
  String get weekdayTue => 'Dt';

  @override
  String get weekdayWed => 'Dc';

  @override
  String get weekdayThu => 'Dj';

  @override
  String get weekdayFri => 'Dv';

  @override
  String get weekdaySat => 'Ds';

  @override
  String get weekdaySun => 'Dg';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return 'Integració amb $serviceName properament';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'Ja exportat a $platform';
  }

  @override
  String get anotherPlatform => 'una altra plataforma';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'Si us plau, autentiqueu-vos amb $serviceName a Configuració > Integracions de tasques';
  }

  @override
  String addingToService(String serviceName) {
    return 'Afegint a $serviceName...';
  }

  @override
  String addedToService(String serviceName) {
    return 'Afegit a $serviceName';
  }

  @override
  String failedToAddToService(String serviceName) {
    return 'Error en afegir a $serviceName';
  }

  @override
  String get permissionDeniedForAppleReminders => 'Permís denegat per a Apple Reminders';

  @override
  String failedToCreateApiKey(String error) {
    return 'Error en crear la clau API del proveïdor: $error';
  }

  @override
  String get createAKey => 'Crear una clau';

  @override
  String get apiKeyRevokedSuccessfully => 'Clau API revocada correctament';

  @override
  String failedToRevokeApiKey(String error) {
    return 'Error en revocar la clau API: $error';
  }

  @override
  String get omiApiKeys => 'Claus API d\'Omi';

  @override
  String get apiKeysDescription =>
      'Les claus API s\'utilitzen per a l\'autenticació quan la teva aplicació es comunica amb el servidor OMI. Permeten que la teva aplicació creï records i accedeixi a altres serveis d\'OMI de manera segura.';

  @override
  String get aboutOmiApiKeys => 'Sobre les claus API d\'Omi';

  @override
  String get yourNewKey => 'La teva nova clau:';

  @override
  String get copyToClipboard => 'Copia al porta-retalls';

  @override
  String get pleaseCopyKeyNow => 'Si us plau, copia\'l ara i escriu-lo en un lloc segur. ';

  @override
  String get willNotSeeAgain => 'No podràs veure\'l de nou.';

  @override
  String get revokeKey => 'Revocar clau';

  @override
  String get revokeApiKeyQuestion => 'Revocar clau API?';

  @override
  String get revokeApiKeyWarning =>
      'Aquesta acció no es pot desfer. Les aplicacions que utilitzin aquesta clau ja no podran accedir a l\'API.';

  @override
  String get revoke => 'Revocar';

  @override
  String get whatWouldYouLikeToCreate => 'Què voldries crear?';

  @override
  String get createAnApp => 'Crear una aplicació';

  @override
  String get createAndShareYourApp => 'Crea i comparteix la teva aplicació';

  @override
  String get createMyClone => 'Crear el meu clon';

  @override
  String get createYourDigitalClone => 'Crea el teu clon digital';

  @override
  String get itemApp => 'Aplicació';

  @override
  String get itemPersona => 'Persona';

  @override
  String keepItemPublic(String item) {
    return 'Mantenir $item públic';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return 'Fer $item públic?';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return 'Fer $item privat?';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'Si fas $item públic, pot ser utilitzat per tothom';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'Si fas $item privat ara, deixarà de funcionar per a tothom i només serà visible per a tu';
  }

  @override
  String get manageApp => 'Gestionar aplicació';

  @override
  String get updatePersonaDetails => 'Actualitzar detalls de la persona';

  @override
  String deleteItemTitle(String item) {
    return 'Eliminar $item';
  }

  @override
  String deleteItemQuestion(String item) {
    return 'Eliminar $item?';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'Estàs segur que vols eliminar aquest $item? Aquesta acció no es pot desfer.';
  }

  @override
  String get revokeKeyQuestion => 'Revocar la clau?';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'Estàs segur que vols revocar la clau \"$keyName\"? Aquesta acció no es pot desfer.';
  }

  @override
  String get createNewKey => 'Crear una nova clau';

  @override
  String get keyNameHint => 'p. ex., Claude Desktop';

  @override
  String get pleaseEnterAName => 'Si us plau, introdueix un nom.';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'Error en crear la clau: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'Error en crear la clau. Si us plau, torna-ho a provar.';

  @override
  String get keyCreated => 'Clau creada';

  @override
  String get keyCreatedMessage =>
      'La teva nova clau ha estat creada. Si us plau, copia-la ara. No la podràs veure de nou.';

  @override
  String get keyWord => 'Clau';

  @override
  String get externalAppAccess => 'Accés d\'aplicacions externes';

  @override
  String get externalAppAccessDescription =>
      'Les següents aplicacions instal·lades tenen integracions externes i poden accedir a les teves dades, com ara converses i records.';

  @override
  String get noExternalAppsHaveAccess => 'Cap aplicació externa té accés a les teves dades.';

  @override
  String get maximumSecurityE2ee => 'Seguretat màxima (E2EE)';

  @override
  String get e2eeDescription =>
      'El xifratge d\'extrem a extrem és l\'estàndard d\'or per a la privacitat. Quan està activat, les teves dades es xifren al teu dispositiu abans d\'enviar-se als nostres servidors. Això significa que ningú, ni tan sols Omi, pot accedir al teu contingut.';

  @override
  String get importantTradeoffs => 'Compensacions importants:';

  @override
  String get e2eeTradeoff1 =>
      '• Algunes funcions com les integracions d\'aplicacions externes poden estar desactivades.';

  @override
  String get e2eeTradeoff2 => '• Si perds la teva contrasenya, les teves dades no es poden recuperar.';

  @override
  String get featureComingSoon => 'Aquesta funció arribarà aviat!';

  @override
  String get migrationInProgressMessage =>
      'Migració en curs. No pots canviar el nivell de protecció fins que s\'hagi completat.';

  @override
  String get migrationFailed => 'La migració ha fallat';

  @override
  String migratingFromTo(String source, String target) {
    return 'Migrant de $source a $target';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total objectes';
  }

  @override
  String get secureEncryption => 'Xifratge segur';

  @override
  String get secureEncryptionDescription =>
      'Les teves dades es xifren amb una clau única per a tu als nostres servidors, allotjats a Google Cloud. Això significa que el teu contingut en brut és inaccessible per a qualsevol, inclòs el personal d\'Omi o Google, directament des de la base de dades.';

  @override
  String get endToEndEncryption => 'Xifratge d\'extrem a extrem';

  @override
  String get e2eeCardDescription =>
      'Activa per a la màxima seguretat on només tu pots accedir a les teves dades. Toca per saber-ne més.';

  @override
  String get dataAlwaysEncrypted =>
      'Independentment del nivell, les teves dades sempre estan xifrades en repòs i en trànsit.';

  @override
  String get readOnlyScope => 'Només lectura';

  @override
  String get fullAccessScope => 'Accés complet';

  @override
  String get readScope => 'Lectura';

  @override
  String get writeScope => 'Escriptura';

  @override
  String get apiKeyCreated => 'Clau API creada!';

  @override
  String get saveKeyWarning => 'Desa aquesta clau ara! No la podràs veure de nou.';

  @override
  String get yourApiKey => 'LA TEVA CLAU API';

  @override
  String get tapToCopy => 'Toca per copiar';

  @override
  String get copyKey => 'Copia la clau';

  @override
  String get createApiKey => 'Crear clau API';

  @override
  String get accessDataProgrammatically => 'Accedeix a les teves dades programàticament';

  @override
  String get keyNameLabel => 'NOM DE LA CLAU';

  @override
  String get keyNamePlaceholder => 'p. ex., La meva integració';

  @override
  String get permissionsLabel => 'PERMISOS';

  @override
  String get permissionsInfoNote => 'R = Lectura, W = Escriptura. Per defecte només lectura si no es selecciona res.';

  @override
  String get developerApi => 'API per a desenvolupadors';

  @override
  String get createAKeyToGetStarted => 'Crea una clau per començar';

  @override
  String errorWithMessage(String error) {
    return 'Error: $error';
  }

  @override
  String get omiTraining => 'Entrenament d\'Omi';

  @override
  String get trainingDataProgram => 'Programa de dades d\'entrenament';

  @override
  String get getOmiUnlimitedFree =>
      'Obtén Omi Il·limitat gratis contribuint les teves dades per entrenar models d\'IA.';

  @override
  String get trainingDataBullets =>
      '• Les teves dades ajuden a millorar els models d\'IA\n• Només es comparteixen dades no sensibles\n• Procés totalment transparent';

  @override
  String get learnMoreAtOmiTraining => 'Aprèn més a omi.me/training';

  @override
  String get agreeToContributeData => 'Entenc i accepto contribuir amb les meves dades per a l\'entrenament d\'IA';

  @override
  String get submitRequest => 'Enviar sol·licitud';

  @override
  String get thankYouRequestUnderReview =>
      'Gràcies! La teva sol·licitud està en revisió. T\'avisarem quan sigui aprovada.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'El teu pla romandrà actiu fins $date. Després, perdràs l\'accés a les funcions il·limitades. Estàs segur?';
  }

  @override
  String get confirmCancellation => 'Confirmar cancel·lació';

  @override
  String get keepMyPlan => 'Conservar el meu pla';

  @override
  String get subscriptionSetToCancel => 'La teva subscripció està configurada per cancel·lar-se al final del període.';

  @override
  String get switchedToOnDevice => 'Canviat a transcripció al dispositiu';

  @override
  String get couldNotSwitchToFreePlan => 'No s\'ha pogut canviar al pla gratuït. Si us plau, torna-ho a provar.';

  @override
  String get couldNotLoadPlans => 'No s\'han pogut carregar els plans disponibles. Si us plau, torna-ho a provar.';

  @override
  String get selectedPlanNotAvailable => 'El pla seleccionat no està disponible. Si us plau, torna-ho a provar.';

  @override
  String get upgradeToAnnualPlan => 'Actualitzar al pla anual';

  @override
  String get importantBillingInfo => 'Informació de facturació important:';

  @override
  String get monthlyPlanContinues => 'El teu pla mensual actual continuarà fins al final del període de facturació';

  @override
  String get paymentMethodCharged =>
      'El teu mètode de pagament existent es cobrarà automàticament quan acabi el teu pla mensual';

  @override
  String get annualSubscriptionStarts =>
      'La teva subscripció anual de 12 mesos començarà automàticament després del cobrament';

  @override
  String get thirteenMonthsCoverage => 'Obtindràs 13 mesos de cobertura en total (mes actual + 12 mesos anuals)';

  @override
  String get confirmUpgrade => 'Confirmar actualització';

  @override
  String get confirmPlanChange => 'Confirmar canvi de pla';

  @override
  String get confirmAndProceed => 'Confirmar i continuar';

  @override
  String get upgradeScheduled => 'Actualització programada';

  @override
  String get changePlan => 'Canviar pla';

  @override
  String get upgradeAlreadyScheduled => 'La teva actualització al pla anual ja està programada';

  @override
  String get youAreOnUnlimitedPlan => 'Estàs al pla Il·limitat.';

  @override
  String get yourOmiUnleashed => 'El teu Omi, deslliurat. Fes-te il·limitat per a possibilitats infinites.';

  @override
  String planEndedOn(String date) {
    return 'El teu pla va acabar el $date.\\nTorna a subscriure\'t ara - se\'t cobrarà immediatament per un nou període de facturació.';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'El teu pla està configurat per cancel·lar-se el $date.\\nTorna a subscriure\'t ara per mantenir els teus beneficis - sense càrrec fins $date.';
  }

  @override
  String get annualPlanStartsAutomatically =>
      'El teu pla anual començarà automàticament quan acabi el teu pla mensual.';

  @override
  String planRenewsOn(String date) {
    return 'El teu pla es renova el $date.';
  }

  @override
  String get unlimitedConversations => 'Converses il·limitades';

  @override
  String get askOmiAnything => 'Pregunta a Omi qualsevol cosa sobre la teva vida';

  @override
  String get unlockOmiInfiniteMemory => 'Desbloqueja la memòria infinita d\'Omi';

  @override
  String get youreOnAnnualPlan => 'Estàs al pla anual';

  @override
  String get alreadyBestValuePlan => 'Ja tens el pla amb millor valor. No cal fer canvis.';

  @override
  String get unableToLoadPlans => 'No es poden carregar els plans';

  @override
  String get checkConnectionTryAgain => 'Comprova la connexió i torna-ho a provar';

  @override
  String get useFreePlan => 'Utilitzar pla gratuït';

  @override
  String get continueText => 'Continuar';

  @override
  String get resubscribe => 'Tornar a subscriure';

  @override
  String get couldNotOpenPaymentSettings =>
      'No s\'han pogut obrir els ajustos de pagament. Si us plau, torna-ho a provar.';

  @override
  String get managePaymentMethod => 'Gestionar mètode de pagament';

  @override
  String get cancelSubscription => 'Cancel·lar subscripció';

  @override
  String endsOnDate(String date) {
    return 'Acaba el $date';
  }

  @override
  String get active => 'Actiu';

  @override
  String get freePlan => 'Pla gratuït';

  @override
  String get configure => 'Configurar';

  @override
  String get privacyInformation => 'Informació de privadesa';

  @override
  String get yourPrivacyMattersToUs => 'La teva privadesa ens importa';

  @override
  String get privacyIntroText =>
      'A Omi, ens prenem molt seriosament la teva privadesa. Volem ser transparents sobre les dades que recollim i com les utilitzem per millorar el producte. Això és el que has de saber:';

  @override
  String get whatWeTrack => 'Què fem seguiment';

  @override
  String get anonymityAndPrivacy => 'Anonimat i privadesa';

  @override
  String get optInAndOptOutOptions => 'Opcions d\'acceptació i rebuig';

  @override
  String get ourCommitment => 'El nostre compromís';

  @override
  String get commitmentText =>
      'Estem compromesos a utilitzar les dades que recollim només per fer d\'Omi un producte millor per a tu. La teva privadesa i confiança són primordials per a nosaltres.';

  @override
  String get thankYouText =>
      'Gràcies per ser un usuari valorat d\'Omi. Si tens alguna pregunta o preocupació, no dubtis a contactar-nos a team@basedhardware.com.';

  @override
  String get wifiSyncSettings => 'Configuració de sincronització WiFi';

  @override
  String get enterHotspotCredentials => 'Introdueix les credencials del punt d\'accés del telèfon';

  @override
  String get wifiSyncUsesHotspot =>
      'La sincronització WiFi utilitza el telèfon com a punt d\'accés. Troba el nom i la contrasenya a Configuració > Punt d\'accés personal.';

  @override
  String get hotspotNameSsid => 'Nom del punt d\'accés (SSID)';

  @override
  String get exampleIphoneHotspot => 'p. ex. Punt d\'accés iPhone';

  @override
  String get password => 'Contrasenya';

  @override
  String get enterHotspotPassword => 'Introdueix la contrasenya del punt d\'accés';

  @override
  String get saveCredentials => 'Desa les credencials';

  @override
  String get clearCredentials => 'Esborra les credencials';

  @override
  String get pleaseEnterHotspotName => 'Si us plau, introdueix un nom de punt d\'accés';

  @override
  String get wifiCredentialsSaved => 'Credencials WiFi desades';

  @override
  String get wifiCredentialsCleared => 'Credencials WiFi esborrades';

  @override
  String summaryGeneratedForDate(String date) {
    return 'Resum generat per a $date';
  }

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'No s\'ha pogut generar el resum. Assegura\'t que tens converses per a aquell dia.';

  @override
  String get summaryNotFound => 'Resum no trobat';

  @override
  String get yourDaysJourney => 'El viatge del teu dia';

  @override
  String get highlights => 'Punts destacats';

  @override
  String get unresolvedQuestions => 'Preguntes no resoltes';

  @override
  String get decisions => 'Decisions';

  @override
  String get learnings => 'Aprenentatges';

  @override
  String get autoDeletesAfterThreeDays => 'S\'elimina automàticament després de 3 dies.';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'Graf de coneixement eliminat correctament';

  @override
  String get exportStartedMayTakeFewSeconds => 'Exportació iniciada. Això pot trigar uns segons...';

  @override
  String get knowledgeGraphDeleteDescription =>
      'Això eliminarà totes les dades derivades del graf de coneixement (nodes i connexions). Els teus records originals romandran segurs. El graf es reconstruirà amb el temps o a la propera sol·licitud.';

  @override
  String get configureDailySummaryDigest => 'Configura el resum diari de les teves tasques';

  @override
  String accessesDataTypes(String dataTypes) {
    return 'Accedeix a $dataTypes';
  }

  @override
  String triggeredByType(String triggerType) {
    return 'activat per $triggerType';
  }

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription i és $triggerDescription.';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return 'És $triggerDescription.';
  }

  @override
  String get noSpecificDataAccessConfigured => 'No hi ha accés a dades específic configurat.';

  @override
  String get basicPlanDescription => '1.200 minuts premium + il·limitat al dispositiu';

  @override
  String get minutes => 'minuts';

  @override
  String get omiHas => 'Omi té:';

  @override
  String get premiumMinutesUsed => 'Minuts premium utilitzats.';

  @override
  String get setupOnDevice => 'Configura al dispositiu';

  @override
  String get forUnlimitedFreeTranscription => 'per a transcripció gratuïta il·limitada.';

  @override
  String premiumMinsLeft(int count) {
    return '$count minuts premium restants.';
  }

  @override
  String get alwaysAvailable => 'sempre disponible.';

  @override
  String get importHistory => 'Historial d\'importació';

  @override
  String get noImportsYet => 'Encara no hi ha importacions';

  @override
  String get selectZipFileToImport => 'Selecciona el fitxer .zip per importar!';

  @override
  String get otherDevicesComingSoon => 'Altres dispositius properament';

  @override
  String get deleteAllLimitlessConversations => 'Eliminar totes les converses de Limitless?';

  @override
  String get deleteAllLimitlessWarning =>
      'Això eliminarà permanentment totes les converses importades de Limitless. Aquesta acció no es pot desfer.';

  @override
  String deletedLimitlessConversations(int count) {
    return 'S\'han eliminat $count converses de Limitless';
  }

  @override
  String get failedToDeleteConversations => 'No s\'han pogut eliminar les converses';

  @override
  String get deleteImportedData => 'Eliminar dades importades';

  @override
  String get statusPending => 'Pendent';

  @override
  String get statusProcessing => 'Processant';

  @override
  String get statusCompleted => 'Completat';

  @override
  String get statusFailed => 'Fallat';

  @override
  String nConversations(int count) {
    return '$count converses';
  }

  @override
  String get pleaseEnterName => 'Si us plau, introdueix un nom';

  @override
  String get nameMustBeBetweenCharacters => 'El nom ha de tenir entre 2 i 40 caràcters';

  @override
  String get deleteSampleQuestion => 'Eliminar la mostra?';

  @override
  String deleteSampleConfirmation(String name) {
    return 'Estàs segur que vols eliminar la mostra de $name?';
  }

  @override
  String get confirmDeletion => 'Confirmar eliminació';

  @override
  String deletePersonConfirmation(String name) {
    return 'Estàs segur que vols eliminar $name? Això també eliminarà totes les mostres de veu associades.';
  }

  @override
  String get howItWorksTitle => 'Com funciona?';

  @override
  String get howPeopleWorks =>
      'Un cop creada una persona, pots anar a una transcripció de conversa i assignar-li els segments corresponents, així Omi també podrà reconèixer la seva parla!';

  @override
  String get tapToDelete => 'Toca per eliminar';

  @override
  String get newTag => 'NOU';

  @override
  String get needHelpChatWithUs => 'Necessites ajuda? Xateja amb nosaltres';

  @override
  String get localStorageEnabled => 'Emmagatzematge local activat';

  @override
  String get localStorageDisabled => 'Emmagatzematge local desactivat';

  @override
  String failedToUpdateSettings(String error) {
    return 'No s\'han pogut actualitzar els paràmetres: $error';
  }

  @override
  String get privacyNotice => 'Avís de privacitat';

  @override
  String get recordingsMayCaptureOthers =>
      'Les gravacions poden capturar les veus d\'altres persones. Assegureu-vos de tenir el consentiment de tots els participants abans d\'activar.';

  @override
  String get enable => 'Activar';

  @override
  String get storeAudioOnPhone => 'Store Audio on Phone';

  @override
  String get on => 'On';

  @override
  String get storeAudioDescription =>
      'Manteniu totes les gravacions d\'àudio emmagatzemades localment al telèfon. Quan estigui desactivat, només es conserven les càrregues fallides per estalviar espai.';

  @override
  String get enableLocalStorage => 'Activa l\'emmagatzematge local';

  @override
  String get cloudStorageEnabled => 'Emmagatzematge al núvol activat';

  @override
  String get cloudStorageDisabled => 'Emmagatzematge al núvol desactivat';

  @override
  String get enableCloudStorage => 'Activa l\'emmagatzematge al núvol';

  @override
  String get storeAudioOnCloud => 'Store Audio on Cloud';

  @override
  String get cloudStorageDialogMessage =>
      'Les vostres gravacions en temps real s\'emmagatzemaran a l\'emmagatzematge privat al núvol mentre parleu.';

  @override
  String get storeAudioCloudDescription =>
      'Emmagatzemeu les vostres gravacions en temps real a l\'emmagatzematge privat al núvol mentre parleu. L\'àudio es captura i es desa de manera segura en temps real.';

  @override
  String get downloadingFirmware => 'Descarregant el firmware';

  @override
  String get installingFirmware => 'Instal·lant el firmware';

  @override
  String get firmwareUpdateWarning =>
      'No tanqueu l\'aplicació ni apagueu el dispositiu. Això podria danyar el dispositiu.';

  @override
  String get firmwareUpdated => 'Firmware actualitzat';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'Si us plau, reinicieu el vostre $deviceName per completar l\'actualització.';
  }

  @override
  String get yourDeviceIsUpToDate => 'El vostre dispositiu està actualitzat';

  @override
  String get currentVersion => 'Versió actual';

  @override
  String get latestVersion => 'Última versió';

  @override
  String get whatsNew => 'Què hi ha de nou';

  @override
  String get installUpdate => 'Instal·lar actualització';

  @override
  String get updateNow => 'Actualitza ara';

  @override
  String get updateGuide => 'Guia d\'actualització';

  @override
  String get checkingForUpdates => 'Comprovant actualitzacions';

  @override
  String get checkingFirmwareVersion => 'Comprovant la versió del firmware...';

  @override
  String get firmwareUpdate => 'Actualització del firmware';

  @override
  String get payments => 'Pagaments';

  @override
  String get connectPaymentMethodInfo =>
      'Connecteu un mètode de pagament a continuació per començar a rebre pagaments per les vostres aplicacions.';

  @override
  String get selectedPaymentMethod => 'Mètode de pagament seleccionat';

  @override
  String get availablePaymentMethods => 'Mètodes de pagament disponibles';

  @override
  String get activeStatus => 'Actiu';

  @override
  String get connectedStatus => 'Connectat';

  @override
  String get notConnectedStatus => 'No connectat';

  @override
  String get setActive => 'Establir com a actiu';

  @override
  String get getPaidThroughStripe => 'Cobreu les vendes de les vostres aplicacions a través de Stripe';

  @override
  String get monthlyPayouts => 'Pagaments mensuals';

  @override
  String get monthlyPayoutsDescription =>
      'Rebeu pagaments mensuals directament al vostre compte quan arribeu als 10 \$ de guanys';

  @override
  String get secureAndReliable => 'Segur i fiable';

  @override
  String get stripeSecureDescription =>
      'Stripe garanteix transferències segures i puntuals dels ingressos de la vostra aplicació';

  @override
  String get selectYourCountry => 'Seleccioneu el vostre país';

  @override
  String get countrySelectionPermanent => 'La selecció del país és permanent i no es pot canviar més tard.';

  @override
  String get byClickingConnectNow => 'En fer clic a \"Connecta ara\" accepteu el';

  @override
  String get stripeConnectedAccountAgreement => 'Acord de compte connectat de Stripe';

  @override
  String get errorConnectingToStripe => 'Error en connectar amb Stripe! Si us plau, torneu-ho a provar més tard.';

  @override
  String get connectingYourStripeAccount => 'Connectant el vostre compte de Stripe';

  @override
  String get stripeOnboardingInstructions =>
      'Si us plau, completeu el procés d\'incorporació de Stripe al vostre navegador. Aquesta pàgina s\'actualitzarà automàticament un cop completat.';

  @override
  String get failedTryAgain => 'Ha fallat? Torneu-ho a provar';

  @override
  String get illDoItLater => 'Ho faré més tard';

  @override
  String get successfullyConnected => 'Connectat amb èxit!';

  @override
  String get stripeReadyForPayments =>
      'El vostre compte de Stripe està ara preparat per rebre pagaments. Podeu començar a guanyar amb les vendes de les vostres aplicacions de seguida.';

  @override
  String get updateStripeDetails => 'Actualitzar els detalls de Stripe';

  @override
  String get errorUpdatingStripeDetails =>
      'Error en actualitzar els detalls de Stripe! Si us plau, torneu-ho a provar més tard.';

  @override
  String get updatePayPal => 'Actualitzar PayPal';

  @override
  String get setUpPayPal => 'Configurar PayPal';

  @override
  String get updatePayPalAccountDetails => 'Actualitzeu les dades del vostre compte de PayPal';

  @override
  String get connectPayPalToReceivePayments =>
      'Connecteu el vostre compte de PayPal per començar a rebre pagaments per les vostres aplicacions';

  @override
  String get paypalEmail => 'Correu electrònic de PayPal';

  @override
  String get paypalMeLink => 'Enllaç PayPal.me';

  @override
  String get stripeRecommendation =>
      'Si Stripe està disponible al vostre país, us recomanem molt utilitzar-lo per a pagaments més ràpids i fàcils.';

  @override
  String get updatePayPalDetails => 'Actualitzar els detalls de PayPal';

  @override
  String get savePayPalDetails => 'Desar els detalls de PayPal';

  @override
  String get pleaseEnterPayPalEmail => 'Si us plau, introduïu el vostre correu electrònic de PayPal';

  @override
  String get pleaseEnterPayPalMeLink => 'Si us plau, introduïu el vostre enllaç PayPal.me';

  @override
  String get doNotIncludeHttpInLink => 'No incloeu http o https o www a l\'enllaç';

  @override
  String get pleaseEnterValidPayPalMeLink => 'Si us plau, introduïu un enllaç PayPal.me vàlid';

  @override
  String get pleaseEnterValidEmail => 'Si us plau, introduïu una adreça de correu electrònic vàlida';

  @override
  String get syncingYourRecordings => 'Sincronitzant les teves gravacions';

  @override
  String get syncYourRecordings => 'Sincronitza les teves gravacions';

  @override
  String get syncNow => 'Sincronitza ara';

  @override
  String get error => 'Error';

  @override
  String get speechSamples => 'Mostres de veu';

  @override
  String additionalSampleIndex(String index) {
    return 'Mostra addicional $index';
  }

  @override
  String durationSeconds(String seconds) {
    return 'Durada: $seconds segons';
  }

  @override
  String get additionalSpeechSampleRemoved => 'S\'ha eliminat la mostra de veu addicional';

  @override
  String get consentDataMessage =>
      'En continuar, totes les dades que comparteixis amb aquesta aplicació (incloent les teves converses, gravacions i informació personal) s\'emmagatzemaran de forma segura als nostres servidors per proporcionar-te informació basada en IA i habilitar totes les funcions de l\'aplicació.';

  @override
  String get tasksEmptyStateMessage =>
      'Les tasques de les teves converses apareixeran aquí.\nToca + per crear-ne una manualment.';

  @override
  String get clearChatAction => 'Esborrar el xat';

  @override
  String get enableApps => 'Activar aplicacions';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => 'mostra més ↓';

  @override
  String get showLess => 'mostra menys ↑';

  @override
  String get loadingYourRecording => 'Carregant la gravació...';

  @override
  String get photoDiscardedMessage => 'Aquesta foto s\'ha descartat perquè no era significativa.';

  @override
  String get analyzing => 'Analitzant...';

  @override
  String get searchCountries => 'Cercar països...';

  @override
  String get checkingAppleWatch => 'Comprovant Apple Watch...';

  @override
  String get installOmiOnAppleWatch => 'Instal·la Omi al teu\nApple Watch';

  @override
  String get installOmiOnAppleWatchDescription =>
      'Per utilitzar el teu Apple Watch amb Omi, primer has d\'instal·lar l\'aplicació Omi al teu rellotge.';

  @override
  String get openOmiOnAppleWatch => 'Obre Omi al teu\nApple Watch';

  @override
  String get openOmiOnAppleWatchDescription =>
      'L\'aplicació Omi està instal·lada al teu Apple Watch. Obre-la i toca Iniciar per començar.';

  @override
  String get openWatchApp => 'Obre l\'aplicació Watch';

  @override
  String get iveInstalledAndOpenedTheApp => 'He instal·lat i obert l\'aplicació';

  @override
  String get unableToOpenWatchApp =>
      'No s\'ha pogut obrir l\'aplicació Apple Watch. Obre manualment l\'aplicació Watch al teu Apple Watch i instal·la Omi des de la secció \"Aplicacions disponibles\".';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch connectat correctament!';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch encara no és accessible. Assegura\'t que l\'aplicació Omi estigui oberta al teu rellotge.';

  @override
  String errorCheckingConnection(String error) {
    return 'Error en comprovar la connexió: $error';
  }

  @override
  String get muted => 'Silenciat';

  @override
  String get processNow => 'Processar ara';

  @override
  String get finishedConversation => 'Conversa acabada?';

  @override
  String get stopRecordingConfirmation => 'Estàs segur que vols aturar la gravació i resumir la conversa ara?';

  @override
  String get conversationEndsManually => 'La conversa només acabarà manualment.';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'La conversa es resumeix després de $minutes minut$suffix sense parlar.';
  }

  @override
  String get dontAskAgain => 'No em tornis a preguntar';

  @override
  String get waitingForTranscriptOrPhotos => 'Esperant transcripció o fotos...';

  @override
  String get noSummaryYet => 'Encara no hi ha resum';

  @override
  String hints(String text) {
    return 'Consells: $text';
  }

  @override
  String get testConversationPrompt => 'Provar un indicador de conversa';

  @override
  String get prompt => 'Prompt';

  @override
  String get result => 'Resultat:';

  @override
  String get compareTranscripts => 'Comparar transcripcions';

  @override
  String get notHelpful => 'No és útil';

  @override
  String get exportTasksWithOneTap => 'Exporta tasques amb un toc!';

  @override
  String get inProgress => 'En curs';

  @override
  String get photos => 'Fotos';

  @override
  String get rawData => 'Dades en brut';

  @override
  String get content => 'Contingut';

  @override
  String get noContentToDisplay => 'No hi ha contingut per mostrar';

  @override
  String get noSummary => 'Sense resum';

  @override
  String get updateOmiFirmware => 'Actualitza el firmware d\'omi';

  @override
  String get anErrorOccurredTryAgain => 'S\'ha produït un error. Si us plau, torna-ho a provar.';

  @override
  String get welcomeBackSimple => 'Benvingut de nou';

  @override
  String get addVocabularyDescription => 'Afegeix paraules que Omi hauria de reconèixer durant la transcripció.';

  @override
  String get enterWordsCommaSeparated => 'Introdueix paraules (separades per comes)';

  @override
  String get whenToReceiveDailySummary => 'Quan rebre el teu resum diari';

  @override
  String get checkingNextSevenDays => 'Comprovant els propers 7 dies';

  @override
  String failedToDeleteError(String error) {
    return 'Error en eliminar: $error';
  }

  @override
  String get developerApiKeys => 'Claus API de desenvolupador';

  @override
  String get noApiKeysCreateOne => 'No hi ha claus API. Crea\'n una per començar.';

  @override
  String get commandRequired => '⌘ obligatori';

  @override
  String get spaceKey => 'Espai';

  @override
  String loadMoreRemaining(String count) {
    return 'Carregar més ($count restants)';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'Top $percentile% Usuari';
  }

  @override
  String get wrappedMinutes => 'minuts';

  @override
  String get wrappedConversations => 'converses';

  @override
  String get wrappedDaysActive => 'dies actius';

  @override
  String get wrappedYouTalkedAbout => 'Has parlat de';

  @override
  String get wrappedActionItems => 'Elements d\'acció';

  @override
  String get wrappedTasksCreated => 'tasques creades';

  @override
  String get wrappedCompleted => 'completades';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% taxa de compleció';
  }

  @override
  String get wrappedYourTopDays => 'Els teus millors dies';

  @override
  String get wrappedBestMoments => 'Millors moments';

  @override
  String get wrappedMyBuddies => 'Els meus amics';

  @override
  String get wrappedCouldntStopTalkingAbout => 'No podia parar de parlar de';

  @override
  String get wrappedShow => 'SÈRIE';

  @override
  String get wrappedMovie => 'PEL·LÍCULA';

  @override
  String get wrappedBook => 'LLIBRE';

  @override
  String get wrappedCelebrity => 'FAMÓS';

  @override
  String get wrappedFood => 'MENJAR';

  @override
  String get wrappedMovieRecs => 'Recomanacions de pel·lícules';

  @override
  String get wrappedBiggest => 'El més gran';

  @override
  String get wrappedStruggle => 'Repte';

  @override
  String get wrappedButYouPushedThrough => 'Però ho vas aconseguir 💪';

  @override
  String get wrappedWin => 'Victòria';

  @override
  String get wrappedYouDidIt => 'Ho has aconseguit! 🎉';

  @override
  String get wrappedTopPhrases => 'Top 5 frases';

  @override
  String get wrappedMins => 'min';

  @override
  String get wrappedConvos => 'converses';

  @override
  String get wrappedDays => 'dies';

  @override
  String get wrappedMyBuddiesLabel => 'ELS MEUS AMICS';

  @override
  String get wrappedObsessionsLabel => 'OBSESSIONS';

  @override
  String get wrappedStruggleLabel => 'REPTE';

  @override
  String get wrappedWinLabel => 'VICTÒRIA';

  @override
  String get wrappedTopPhrasesLabel => 'TOP FRASES';

  @override
  String get wrappedLetsHitRewind => 'Rebobinem el teu';

  @override
  String get wrappedGenerateMyWrapped => 'Genera el meu Wrapped';

  @override
  String get wrappedProcessingDefault => 'Processant...';

  @override
  String get wrappedCreatingYourStory => 'Creant la teva\nhistòria del 2025...';

  @override
  String get wrappedSomethingWentWrong => 'Alguna cosa\nha fallat';

  @override
  String get wrappedAnErrorOccurred => 'S\'ha produït un error';

  @override
  String get wrappedTryAgain => 'Torna a provar';

  @override
  String get wrappedNoDataAvailable => 'No hi ha dades disponibles';

  @override
  String get wrappedOmiLifeRecap => 'Resum de vida Omi';

  @override
  String get wrappedSwipeUpToBegin => 'Llisca amunt per començar';

  @override
  String get wrappedShareText => 'El meu 2025, recordat per Omi ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare => 'No s\'ha pogut compartir. Torna a provar.';

  @override
  String get wrappedFailedToStartGeneration => 'No s\'ha pogut iniciar la generació. Torna a provar.';

  @override
  String get wrappedStarting => 'Iniciant...';

  @override
  String get wrappedShare => 'Compartir';

  @override
  String get wrappedShareYourWrapped => 'Comparteix el teu Wrapped';

  @override
  String get wrappedMy2025 => 'El meu 2025';

  @override
  String get wrappedRememberedByOmi => 'recordat per Omi';

  @override
  String get wrappedMostFunDay => 'Més divertit';

  @override
  String get wrappedMostProductiveDay => 'Més productiu';

  @override
  String get wrappedMostIntenseDay => 'Més intens';

  @override
  String get wrappedFunniestMoment => 'Més graciós';

  @override
  String get wrappedMostCringeMoment => 'Més vergonyós';

  @override
  String get wrappedMinutesLabel => 'minuts';

  @override
  String get wrappedConversationsLabel => 'converses';

  @override
  String get wrappedDaysActiveLabel => 'dies actius';

  @override
  String get wrappedTasksGenerated => 'tasques generades';

  @override
  String get wrappedTasksCompleted => 'tasques completades';

  @override
  String get wrappedTopFivePhrases => 'Top 5 frases';

  @override
  String get wrappedAGreatDay => 'Un gran dia';

  @override
  String get wrappedGettingItDone => 'Fent-ho';

  @override
  String get wrappedAChallenge => 'Un repte';

  @override
  String get wrappedAHilariousMoment => 'Un moment divertit';

  @override
  String get wrappedThatAwkwardMoment => 'Aquell moment incòmode';

  @override
  String get wrappedYouHadFunnyMoments => 'Has tingut moments divertits aquest any!';

  @override
  String get wrappedWeveAllBeenThere => 'Tots hi hem estat!';

  @override
  String get wrappedFriend => 'Amic';

  @override
  String get wrappedYourBuddy => 'El teu amic!';

  @override
  String get wrappedNotMentioned => 'No mencionat';

  @override
  String get wrappedTheHardPart => 'La part difícil';

  @override
  String get wrappedPersonalGrowth => 'Creixement personal';

  @override
  String get wrappedFunDay => 'Divertit';

  @override
  String get wrappedProductiveDay => 'Productiu';

  @override
  String get wrappedIntenseDay => 'Intens';

  @override
  String get wrappedFunnyMomentTitle => 'Moment divertit';

  @override
  String get wrappedCringeMomentTitle => 'Moment vergonyós';

  @override
  String get wrappedYouTalkedAboutBadge => 'Has parlat de';

  @override
  String get wrappedCompletedLabel => 'Completat';

  @override
  String get wrappedMyBuddiesCard => 'Els meus amics';

  @override
  String get wrappedBuddiesLabel => 'AMICS';

  @override
  String get wrappedObsessionsLabelUpper => 'OBSESSIONS';

  @override
  String get wrappedStruggleLabelUpper => 'LLUITA';

  @override
  String get wrappedWinLabelUpper => 'VICTÒRIA';

  @override
  String get wrappedTopPhrasesLabelUpper => 'TOP FRASES';

  @override
  String get wrappedYourHeader => 'Els teus';

  @override
  String get wrappedTopDaysHeader => 'millors dies';

  @override
  String get wrappedYourTopDaysBadge => 'Els teus millors dies';

  @override
  String get wrappedBestHeader => 'Millors';

  @override
  String get wrappedMomentsHeader => 'moments';

  @override
  String get wrappedBestMomentsBadge => 'Millors moments';

  @override
  String get wrappedBiggestHeader => 'Més gran';

  @override
  String get wrappedStruggleHeader => 'Lluita';

  @override
  String get wrappedWinHeader => 'Victòria';

  @override
  String get wrappedButYouPushedThroughEmoji => 'Però ho vas aconseguir 💪';

  @override
  String get wrappedYouDidItEmoji => 'Ho vas fer! 🎉';

  @override
  String get wrappedHours => 'hores';

  @override
  String get wrappedActions => 'accions';

  @override
  String get multipleSpeakersDetected => 'Múltiples parlants detectats';

  @override
  String get multipleSpeakersDescription =>
      'Sembla que hi ha múltiples parlants a la gravació. Assegureu-vos que esteu en un lloc tranquil i torneu-ho a provar.';

  @override
  String get invalidRecordingDetected => 'Gravació invàlida detectada';

  @override
  String get notEnoughSpeechDescription => 'No s\'ha detectat prou parla. Si us plau, parleu més i torneu-ho a provar.';

  @override
  String get speechDurationDescription => 'Assegureu-vos de parlar almenys 5 segons i no més de 90.';

  @override
  String get connectionLostDescription =>
      'La connexió s\'ha interromput. Comproveu la connexió a Internet i torneu-ho a provar.';

  @override
  String get howToTakeGoodSample => 'Com fer una bona mostra?';

  @override
  String get goodSampleInstructions =>
      '1. Assegureu-vos que esteu en un lloc tranquil.\n2. Parleu clarament i naturalment.\n3. Assegureu-vos que el dispositiu estigui en la seva posició natural al coll.\n\nUn cop creat, sempre podeu millorar-lo o fer-ho de nou.';

  @override
  String get noDeviceConnectedUseMic => 'Cap dispositiu connectat. S\'utilitzarà el micròfon del telèfon.';

  @override
  String get doItAgain => 'Fer-ho de nou';

  @override
  String get listenToSpeechProfile => 'Escolta el meu perfil de veu ➡️';

  @override
  String get recognizingOthers => 'Reconeixent altres 👀';

  @override
  String get keepGoingGreat => 'Continua, ho estàs fent genial';

  @override
  String get somethingWentWrongTryAgain => 'Alguna cosa ha anat malament! Si us plau, torneu-ho a provar més tard.';

  @override
  String get uploadingVoiceProfile => 'Pujant el teu perfil de veu....';

  @override
  String get memorizingYourVoice => 'Memoritzant la teva veu...';

  @override
  String get personalizingExperience => 'Personalitzant la teva experiència...';

  @override
  String get keepSpeakingUntil100 => 'Continua parlant fins arribar al 100%.';

  @override
  String get greatJobAlmostThere => 'Molt bé, gairebé hi ets';

  @override
  String get soCloseJustLittleMore => 'Tan a prop, només una mica més';

  @override
  String get notificationFrequency => 'Freqüència de notificacions';

  @override
  String get controlNotificationFrequency => 'Controla amb quina freqüència Omi t\'envia notificacions proactives.';

  @override
  String get yourScore => 'La teva puntuació';

  @override
  String get dailyScoreBreakdown => 'Desglossament de la puntuació diària';

  @override
  String get todaysScore => 'Puntuació d\'avui';

  @override
  String get tasksCompleted => 'Tasques completades';

  @override
  String get completionRate => 'Taxa de compleció';

  @override
  String get howItWorks => 'Com funciona';

  @override
  String get dailyScoreExplanation =>
      'La teva puntuació diària es basa en completar tasques. Completa les teves tasques per millorar la puntuació!';

  @override
  String get notificationFrequencyDescription =>
      'Controla amb quina freqüència Omi t\'envia notificacions proactives i recordatoris.';

  @override
  String get sliderOff => 'Apagat';

  @override
  String get sliderMax => 'Màx.';

  @override
  String summaryGeneratedFor(String date) {
    return 'Resum generat per $date';
  }

  @override
  String get failedToGenerateSummary =>
      'No s\'ha pogut generar el resum. Assegura\'t que tens converses per a aquest dia.';

  @override
  String get recap => 'Recapitulació';

  @override
  String deleteQuoted(String name) {
    return 'Eliminar \"$name\"';
  }

  @override
  String moveConversationsTo(int count) {
    return 'Moure $count converses a:';
  }

  @override
  String get noFolder => 'Sense carpeta';

  @override
  String get removeFromAllFolders => 'Eliminar de totes les carpetes';

  @override
  String get buildAndShareYourCustomApp => 'Crea i comparteix la teva aplicació personalitzada';

  @override
  String get searchAppsPlaceholder => 'Cerca entre 1500+ aplicacions';

  @override
  String get filters => 'Filtres';

  @override
  String get frequencyOff => 'Desactivat';

  @override
  String get frequencyMinimal => 'Mínim';

  @override
  String get frequencyLow => 'Baix';

  @override
  String get frequencyBalanced => 'Equilibrat';

  @override
  String get frequencyHigh => 'Alt';

  @override
  String get frequencyMaximum => 'Màxim';

  @override
  String get frequencyDescOff => 'Sense notificacions proactives';

  @override
  String get frequencyDescMinimal => 'Només recordatoris crítics';

  @override
  String get frequencyDescLow => 'Només actualitzacions importants';

  @override
  String get frequencyDescBalanced => 'Avisos útils regulars';

  @override
  String get frequencyDescHigh => 'Seguiments freqüents';

  @override
  String get frequencyDescMaximum => 'Mantén-te sempre connectat';

  @override
  String get clearChatQuestion => 'Esborrar el xat?';

  @override
  String get syncingMessages => 'Sincronitzant missatges amb el servidor...';

  @override
  String get chatAppsTitle => 'Aplicacions de xat';

  @override
  String get selectApp => 'Selecciona aplicació';

  @override
  String get noChatAppsEnabled => 'No hi ha aplicacions de xat activades.\nToca \"Activar aplicacions\" per afegir-ne.';

  @override
  String get disable => 'Desactivar';

  @override
  String get photoLibrary => 'Biblioteca de fotos';

  @override
  String get chooseFile => 'Triar fitxer';

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
  String get fastTransfer => 'Fast Transfer';

  @override
  String get syncingStatus => 'Syncing';

  @override
  String get failedStatus => 'Failed';

  @override
  String etaLabel(String time) {
    return 'ETA: $time';
  }

  @override
  String get transferMethod => 'Transfer Method';

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
      'Si us plau, activeu l\'accés als Recordatoris a Configuració per utilitzar els Recordatoris d\'Apple';

  @override
  String todayAtTime(String time) {
    return 'Avui a les $time';
  }

  @override
  String yesterdayAtTime(String time) {
    return 'Ahir a les $time';
  }

  @override
  String get lessThanAMinute => 'Menys d\'un minut';

  @override
  String estimatedMinutes(int count) {
    return '~$count minut(s)';
  }

  @override
  String estimatedHours(int count) {
    return '~$count hora/hores';
  }

  @override
  String estimatedTimeRemaining(String time) {
    return 'Estimat: $time restants';
  }

  @override
  String get summarizingConversation => 'Resumint la conversa...\nAixò pot trigar uns segons';

  @override
  String get resummarizingConversation => 'Tornant a resumir la conversa...\nAixò pot trigar uns segons';

  @override
  String get nothingInterestingRetry => 'No s\'ha trobat res interessant,\nvols tornar-ho a provar?';

  @override
  String get noSummaryForConversation => 'No hi ha resum disponible\nper a aquesta conversa.';

  @override
  String get unknownLocation => 'Ubicació desconeguda';

  @override
  String get couldNotLoadMap => 'No s\'ha pogut carregar el mapa';

  @override
  String get triggerConversationIntegration => 'Activar integració de creació de conversa';

  @override
  String get webhookUrlNotSet => 'URL de Webhook no configurada';

  @override
  String get setWebhookUrlInSettings =>
      'Si us plau, configura l\'URL de Webhook a la configuració de desenvolupador per utilitzar aquesta funció.';

  @override
  String get sendWebUrl => 'Enviar URL web';

  @override
  String get sendTranscript => 'Enviar transcripció';

  @override
  String get sendSummary => 'Enviar resum';

  @override
  String get debugModeDetected => 'Mode de depuració detectat';

  @override
  String get performanceReduced => 'Rendiment reduït 5-10x. Usa el mode Release.';

  @override
  String autoClosingInSeconds(int seconds) {
    return 'Tancant automàticament en ${seconds}s';
  }

  @override
  String get modelRequired => 'Model requerit';

  @override
  String get downloadWhisperModel => 'Si us plau, descarrega un model Whisper abans de desar.';

  @override
  String get deviceNotCompatible => 'Dispositiu no compatible';

  @override
  String get deviceRequirements => 'El teu dispositiu no compleix els requisits per a la transcripció al dispositiu.';

  @override
  String get willLikelyCrash => 'Activar això probablement farà que laplicació es bloquegi o es congeli.';

  @override
  String get transcriptionSlowerLessAccurate => 'La transcripció serà significativament més lenta i menys precisa.';

  @override
  String get proceedAnyway => 'Continuar igualment';

  @override
  String get olderDeviceDetected => 'Detectat dispositiu antic';

  @override
  String get onDeviceSlower => 'La transcripció al dispositiu pot ser més lenta.';

  @override
  String get batteryUsageHigher => 'El consum de bateria serà més alt que la transcripció al núvol.';

  @override
  String get considerOmiCloud => 'Considera utilitzar Omi Cloud per a un millor rendiment.';

  @override
  String get highResourceUsage => 'Alt ús de recursos';

  @override
  String get onDeviceIntensive => 'La transcripció al dispositiu és computacionalment intensiva.';

  @override
  String get batteryDrainIncrease => 'El consum de bateria augmentarà significativament.';

  @override
  String get deviceMayWarmUp => 'El dispositiu pot escalfar-se durant lús prolongat.';

  @override
  String get speedAccuracyLower => 'La velocitat i la precisió poden ser inferiors als models al núvol.';

  @override
  String get cloudProvider => 'Proveïdor al núvol';

  @override
  String get premiumMinutesInfo =>
      '1.200 minuts premium/mes. La pestanya Al dispositiu ofereix transcripció gratuïta il·limitada.';

  @override
  String get viewUsage => 'Veure ús';

  @override
  String get localProcessingInfo =>
      'L\'àudio es processa localment. Funciona sense connexió, més privat, però usa més bateria.';

  @override
  String get model => 'Model';

  @override
  String get performanceWarning => 'Advertència de rendiment';

  @override
  String get largeModelWarning =>
      'Aquest model és gran i pot bloquejar l\'app o funcionar molt lentament.\n\nEs recomana \"small\" o \"base\".';

  @override
  String get usingNativeIosSpeech => 'Utilitzant el reconeixement de veu natiu diOS';

  @override
  String get noModelDownloadRequired => 'S\'usarà el motor de veu natiu del dispositiu. No cal descarregar cap model.';

  @override
  String get modelReady => 'Model llest';

  @override
  String get redownload => 'Tornar a descarregar';

  @override
  String get doNotCloseApp => 'Si us plau, no tanqueu laplicació.';

  @override
  String get downloading => 'Descarregant...';

  @override
  String get downloadModel => 'Descarregar model';

  @override
  String estimatedSize(String size) {
    return 'Mida estimada: ~$size MB';
  }

  @override
  String availableSpace(String space) {
    return 'Espai disponible: $space';
  }

  @override
  String get notEnoughSpace => 'Advertència: No hi ha prou espai!';

  @override
  String get download => 'Descarregar';

  @override
  String downloadError(String error) {
    return 'Error de descàrrega: $error';
  }

  @override
  String get cancelled => 'Cancel·lat';

  @override
  String get deviceNotCompatibleTitle => 'Dispositiu no compatible';

  @override
  String get deviceNotMeetRequirements =>
      'El teu dispositiu no compleix els requisits per a la transcripció al dispositiu.';

  @override
  String get transcriptionSlowerOnDevice => 'La transcripció al dispositiu pot ser més lenta en aquest dispositiu.';

  @override
  String get computationallyIntensive => 'La transcripció al dispositiu és computacionalment intensiva.';

  @override
  String get batteryDrainSignificantly => 'El consum de bateria augmentarà significativament.';

  @override
  String get premiumMinutesMonth =>
      '1.200 minuts premium/mes. La pestanya Al dispositiu ofereix transcripció gratuïta il·limitada. ';

  @override
  String get audioProcessedLocally =>
      'Laudio es processa localment. Funciona sense connexió, més privat, però consumeix més bateria.';

  @override
  String get languageLabel => 'Idioma';

  @override
  String get modelLabel => 'Model';

  @override
  String get modelTooLargeWarning =>
      'Aquest model és gran i pot fer que laplicació es bloquegi o funcioni molt lentament en dispositius mòbils.\n\nEs recomana small o base.';

  @override
  String get nativeEngineNoDownload =>
      'Sutilitzarà el motor de veu natiu del teu dispositiu. No cal descarregar cap model.';

  @override
  String modelReadyWithName(String model) {
    return 'Model llest ($model)';
  }

  @override
  String get reDownload => 'Tornar a descarregar';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return 'Descarregant $model: $received / $total MB';
  }

  @override
  String preparingModel(String model) {
    return 'Preparant $model...';
  }

  @override
  String downloadErrorWithMessage(String error) {
    return 'Error de descàrrega: $error';
  }

  @override
  String estimatedSizeWithValue(String size) {
    return 'Mida estimada: ~$size MB';
  }

  @override
  String availableSpaceWithValue(String space) {
    return 'Espai disponible: $space';
  }

  @override
  String get omiTranscriptionOptimized =>
      'La transcripció en directe integrada dOmi està optimitzada per a converses en temps real amb detecció automàtica de parlants i diarització.';

  @override
  String get reset => 'Restablir';

  @override
  String get useTemplateFrom => 'Utilitzar plantilla de';

  @override
  String get selectProviderTemplate => 'Selecciona una plantilla de proveïdor...';

  @override
  String get quicklyPopulateResponse => 'Emplenar ràpidament amb un format de resposta de proveïdor conegut';

  @override
  String get quicklyPopulateRequest => 'Emplenar ràpidament amb un format de sol·licitud de proveïdor conegut';

  @override
  String get invalidJsonError => 'JSON no vàlid';

  @override
  String downloadModelWithName(String model) {
    return 'Descarregar model ($model)';
  }

  @override
  String modelNameWithFile(String model) {
    return 'Model: $model';
  }

  @override
  String get device => 'Device';

  @override
  String get chatAssistantsTitle => 'Assistents de xat';

  @override
  String get permissionReadConversations => 'Llegir converses';

  @override
  String get permissionReadMemories => 'Llegir records';

  @override
  String get permissionReadTasks => 'Llegir tasques';

  @override
  String get permissionCreateConversations => 'Crear converses';

  @override
  String get permissionCreateMemories => 'Crear records';

  @override
  String get permissionTypeAccess => 'Accés';

  @override
  String get permissionTypeCreate => 'Crear';

  @override
  String get permissionTypeTrigger => 'Disparador';

  @override
  String get permissionDescReadConversations => 'Aquesta app pot accedir a les teves converses.';

  @override
  String get permissionDescReadMemories => 'Aquesta app pot accedir als teus records.';

  @override
  String get permissionDescReadTasks => 'Aquesta app pot accedir a les teves tasques.';

  @override
  String get permissionDescCreateConversations => 'Aquesta app pot crear noves converses.';

  @override
  String get permissionDescCreateMemories => 'Aquesta app pot crear nous records.';

  @override
  String get realtimeListening => 'Escolta en temps real';

  @override
  String get setupCompleted => 'Completat';

  @override
  String get pleaseSelectRating => 'Si us plau, selecciona una valoració';

  @override
  String get writeReviewOptional => 'Escriu una ressenya (opcional)';

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
  String get customBackendUrlTitle => 'URL del servidor personalitzat';

  @override
  String get backendUrlLabel => 'URL del servidor';

  @override
  String get saveUrlButton => 'Desar URL';

  @override
  String get enterBackendUrlError => 'Introduïu l\'URL del servidor';

  @override
  String get urlMustEndWithSlashError => 'L\'URL ha d\'acabar amb \"/\"';

  @override
  String get invalidUrlError => 'Introduïu un URL vàlid';

  @override
  String get backendUrlSavedSuccess => 'URL del servidor desat correctament!';

  @override
  String get signInTitle => 'Inicia la sessió';

  @override
  String get signInButton => 'Inicia la sessió';

  @override
  String get enterEmailError => 'Introduïu el vostre correu electrònic';

  @override
  String get invalidEmailError => 'Introduïu un correu electrònic vàlid';

  @override
  String get enterPasswordError => 'Introduïu la vostra contrasenya';

  @override
  String get passwordMinLengthError => 'La contrasenya ha de tenir almenys 8 caràcters';

  @override
  String get signInSuccess => 'Inici de sessió correcte!';

  @override
  String get alreadyHaveAccountLogin => 'Ja tens un compte? Inicia sessió';

  @override
  String get emailLabel => 'Correu electrònic';

  @override
  String get passwordLabel => 'Contrasenya';

  @override
  String get createAccountTitle => 'Crear un compte';

  @override
  String get nameLabel => 'Nom';

  @override
  String get repeatPasswordLabel => 'Repeteix la contrasenya';

  @override
  String get signUpButton => 'Registrar-se';

  @override
  String get enterNameError => 'Introduïu el vostre nom';

  @override
  String get passwordsDoNotMatch => 'Les contrasenyes no coincideixen';

  @override
  String get signUpSuccess => 'Registre correcte!';

  @override
  String get loadingKnowledgeGraph => 'Carregant el graf de coneixement...';

  @override
  String get noKnowledgeGraphYet => 'Encara no hi ha graf de coneixement';

  @override
  String get buildingKnowledgeGraphFromMemories => 'Construint el graf de coneixement a partir de records...';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'El graf de coneixement es construirà automàticament quan creïs nous records.';

  @override
  String get buildGraphButton => 'Construir graf';

  @override
  String get checkOutMyMemoryGraph => 'Mira el meu graf de memòria!';

  @override
  String get getButton => 'Obtenir';

  @override
  String openingApp(String appName) {
    return 'Obrint $appName...';
  }

  @override
  String get writeSomething => 'Escriu alguna cosa';

  @override
  String get submitReply => 'Enviar resposta';

  @override
  String get editYourReply => 'Editar resposta';

  @override
  String get replyToReview => 'Respondre a la ressenya';

  @override
  String get rateAndReviewThisApp => 'Valora i ressenya aquesta aplicació';

  @override
  String get noChangesInReview => 'No hi ha canvis a la ressenya per actualitzar.';

  @override
  String get cantRateWithoutInternet => 'No es pot valorar l\'aplicació sense connexió a Internet.';

  @override
  String get appAnalytics => 'Anàlisi de l\'aplicació';

  @override
  String get learnMoreLink => 'més informació';

  @override
  String get moneyEarned => 'Diners guanyats';

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
    return '$count estrella';
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
  String get goal => 'OBJECTIU';

  @override
  String get tapToTrackThisGoal => 'Toca per fer seguiment d\'aquest objectiu';

  @override
  String get tapToSetAGoal => 'Toca per establir un objectiu';

  @override
  String get processedConversations => 'Converses processades';

  @override
  String get updatedConversations => 'Converses actualitzades';

  @override
  String get newConversations => 'Noves converses';

  @override
  String get summaryTemplate => 'Plantilla de resum';

  @override
  String get suggestedTemplates => 'Plantilles suggerides';

  @override
  String get otherTemplates => 'Altres plantilles';

  @override
  String get availableTemplates => 'Plantilles disponibles';

  @override
  String get getCreative => 'Sigues creatiu';

  @override
  String get defaultLabel => 'Predeterminada';

  @override
  String get lastUsedLabel => 'Últim ús';

  @override
  String get setDefaultApp => 'Establir aplicació predeterminada';

  @override
  String setDefaultAppContent(String appName) {
    return 'Establir $appName com la teva aplicació de resum predeterminada?\\n\\nAquesta aplicació s\'utilitzarà automàticament per a tots els resums de converses futures.';
  }

  @override
  String get setDefaultButton => 'Establir predeterminada';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName establerta com a aplicació de resum predeterminada';
  }

  @override
  String get createCustomTemplate => 'Crear plantilla personalitzada';

  @override
  String get allTemplates => 'Totes les plantilles';

  @override
  String failedToInstallApp(String appName) {
    return 'Error en instal·lar $appName. Si us plau, torna-ho a provar.';
  }

  @override
  String errorInstallingApp(String appName, String error) {
    return 'Error en instal·lar $appName: $error';
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
  String get shareViaSms => 'Comparteix via SMS';

  @override
  String get selectContactsToShareSummary => 'Selecciona contactes per compartir el resum de la conversa';

  @override
  String get searchContactsHint => 'Cerca contactes...';

  @override
  String contactsSelectedCount(int count) {
    return '$count seleccionats';
  }

  @override
  String get clearAllSelection => 'Esborra tot';

  @override
  String get selectContactsToShare => 'Selecciona contactes per compartir';

  @override
  String shareWithContactCount(int count) {
    return 'Comparteix amb $count contacte';
  }

  @override
  String shareWithContactsCount(int count) {
    return 'Comparteix amb $count contactes';
  }

  @override
  String get contactsPermissionRequired => 'Es requereix permís de contactes';

  @override
  String get contactsPermissionRequiredForSms => 'Es requereix permís de contactes per compartir via SMS';

  @override
  String get grantContactsPermissionForSms => 'Si us plau, concedeix permís de contactes per compartir via SMS';

  @override
  String get noContactsWithPhoneNumbers => 'No s\'han trobat contactes amb números de telèfon';

  @override
  String get noContactsMatchSearch => 'Cap contacte coincideix amb la cerca';

  @override
  String get failedToLoadContacts => 'Error en carregar els contactes';

  @override
  String get failedToPrepareConversationForSharing =>
      'Error en preparar la conversa per compartir. Si us plau, torna-ho a provar.';

  @override
  String get couldNotOpenSmsApp => 'No s\'ha pogut obrir l\'aplicació de SMS. Si us plau, torna-ho a provar.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'Aquí tens el que hem parlat: $link';
  }

  @override
  String get wifiSync => 'Sincronització WiFi';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item copiat al porta-retalls';
  }
}
