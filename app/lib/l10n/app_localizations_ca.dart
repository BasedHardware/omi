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
  String get cancel => 'Cancel·lar';

  @override
  String get ok => 'D\'acord';

  @override
  String get delete => 'Eliminar';

  @override
  String get add => 'Afegir';

  @override
  String get update => 'Actualitzar';

  @override
  String get save => 'Desar';

  @override
  String get edit => 'Editar';

  @override
  String get close => 'Tancar';

  @override
  String get clear => 'Netejar';

  @override
  String get copyTranscript => 'Copiar transcripció';

  @override
  String get copySummary => 'Copiar resum';

  @override
  String get testPrompt => 'Provar indicació';

  @override
  String get reprocessConversation => 'Reprocessar conversa';

  @override
  String get deleteConversation => 'Eliminar conversa';

  @override
  String get contentCopied => 'Contingut copiat al porta-retalls';

  @override
  String get failedToUpdateStarred => 'No s\'ha pogut actualitzar l\'estat de destacat.';

  @override
  String get conversationUrlNotShared => 'No s\'ha pogut compartir l\'URL de la conversa.';

  @override
  String get errorProcessingConversation => 'Error en processar la conversa. Torneu-ho a provar més tard.';

  @override
  String get noInternetConnection => 'Comproveu la vostra connexió a internet i torneu-ho a provar.';

  @override
  String get unableToDeleteConversation => 'No es pot eliminar la conversa';

  @override
  String get somethingWentWrong => 'Alguna cosa ha anat malament! Torneu-ho a provar més tard.';

  @override
  String get copyErrorMessage => 'Copiar missatge d\'error';

  @override
  String get errorCopied => 'Missatge d\'error copiat al porta-retalls';

  @override
  String get remaining => 'Restants';

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
  String get speechProfile => 'Perfil de veu';

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
  String get askOmi => 'Preguntar a Omi';

  @override
  String get done => 'Fet';

  @override
  String get disconnected => 'Desconnectat';

  @override
  String get searching => 'Cercant';

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
  String get noConversationsYet => 'Encara no hi ha converses.';

  @override
  String get noStarredConversations => 'Encara no hi ha converses destacades.';

  @override
  String get starConversationHint =>
      'Per destacar una conversa, obriu-la i toqueu la icona d\'estrella a la capçalera.';

  @override
  String get searchConversations => 'Cercar converses';

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
  String get deletingMessages => 'Eliminant els vostres missatges de la memòria d\'Omi...';

  @override
  String get messageCopied => 'Missatge copiat al porta-retalls.';

  @override
  String get cannotReportOwnMessage => 'No podeu denunciar els vostres propis missatges.';

  @override
  String get reportMessage => 'Denunciar missatge';

  @override
  String get reportMessageConfirm => 'Esteu segur que voleu denunciar aquest missatge?';

  @override
  String get messageReported => 'Missatge denunciat correctament.';

  @override
  String get thankYouFeedback => 'Gràcies pels vostres comentaris!';

  @override
  String get clearChat => 'Netejar xat?';

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
  String get createYourOwnApp => 'Creeu la vostra pròpia aplicació';

  @override
  String get buildAndShareApp => 'Construïu i compartiu la vostra aplicació personalitzada';

  @override
  String get searchApps => 'Cercar més de 1500 aplicacions';

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
  String get visitWebsite => 'Visitar lloc web';

  @override
  String get helpOrInquiries => 'Ajuda o consultes?';

  @override
  String get joinCommunity => 'Uniu-vos a la comunitat!';

  @override
  String get membersAndCounting => 'Més de 8000 membres i sumant.';

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
  String get customVocabulary => 'Vocabulari personalitzat';

  @override
  String get identifyingOthers => 'Identificar altres';

  @override
  String get paymentMethods => 'Mètodes de pagament';

  @override
  String get conversationDisplay => 'Visualització de converses';

  @override
  String get dataPrivacy => 'Dades i privadesa';

  @override
  String get userId => 'ID d\'usuari';

  @override
  String get notSet => 'No establert';

  @override
  String get userIdCopied => 'ID d\'usuari copiat al porta-retalls';

  @override
  String get systemDefault => 'Per defecte del sistema';

  @override
  String get planAndUsage => 'Pla i ús';

  @override
  String get offlineSync => 'Sincronització fora de línia';

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
  String get signOut => 'Tancar sessió';

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
  String get disconnectDevice => 'Desconnectar dispositiu';

  @override
  String get unpairDevice => 'Desvincular dispositiu';

  @override
  String get unpairAndForget => 'Desvincular i oblidar dispositiu';

  @override
  String get deviceDisconnectedMessage => 'El vostre Omi s\'ha desconnectat 😔';

  @override
  String get deviceUnpairedMessage =>
      'Dispositiu desvinculat. Aneu a Configuració > Bluetooth i oblideu el dispositiu per completar la desvinculació.';

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
  String get off => 'Apagat';

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
  String get createKey => 'Crear clau';

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
  String get upgradeToUnlimited => 'Actualitzar a il·limitat';

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
  String get knowledgeGraphDeleted => 'Graf de coneixement eliminat correctament';

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
  String get insights => 'Informacions';

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
  String get editName => 'Editar nom';

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
  String get refresh => 'Actualitzar';

  @override
  String get noUpcomingMeetings => 'No s\'han trobat reunions properes';

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
  String get skip => 'Ometre';

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
  String get yesterday => 'ahir';

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
  String deviceUsesCodec(String deviceName, String codecReason) {
    return '$deviceName utilitza $codecReason. S\'utilitzarà Omi.';
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
  String get saveChanges => 'Desar canvis';

  @override
  String get resetToDefault => 'Restablir per defecte';

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
  String get makePublic => 'Fer pública';

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
  String get grantPermissions => 'Atorgar permisos';

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
  String get skipThisQuestion => 'Ometre aquesta pregunta';

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
  String get whatsYourName => 'Com us dieu?';

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
  String get personalGrowthJourney => 'El vostre viatge de creixement personal amb IA que escolta cada paraula vostra.';

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
  String get deleteActionItemTitle => 'Eliminar tasca';

  @override
  String get deleteActionItemMessage => 'Esteu segur que voleu eliminar aquesta tasca?';

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
  String searchMemories(int count) {
    return 'Cercar $count records';
  }

  @override
  String get memoryDeleted => 'Record eliminat.';

  @override
  String get undo => 'Desfer';

  @override
  String get noMemoriesYet => 'Encara no hi ha records';

  @override
  String get noAutoMemories => 'Encara no hi ha records extrets automàticament';

  @override
  String get noManualMemories => 'Encara no hi ha records manuals';

  @override
  String get noMemoriesInCategories => 'No hi ha records en aquestes categories';

  @override
  String get noMemoriesFound => 'No s\'han trobat records';

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
  String get memoryManagement => 'Gestió de records';

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
  String get newMemory => 'Nou record';

  @override
  String get editMemory => 'Editar record';

  @override
  String get memoryContentHint => 'M\'agrada menjar gelat...';

  @override
  String get failedToSaveMemory => 'No s\'ha pogut desar. Comproveu la vostra connexió.';

  @override
  String get saveMemory => 'Desar record';

  @override
  String get retry => 'Tornar a provar';

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
  String get failedToUpdateActionItem => 'No s\'ha pogut actualitzar la tasca';

  @override
  String get actionItemCreated => 'Tasca creada';

  @override
  String get failedToCreateActionItem => 'No s\'ha pogut crear la tasca';

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
  String get markComplete => 'Marcar com a complet';

  @override
  String get actionItemDeleted => 'Tasca eliminada';

  @override
  String get failedToDeleteActionItem => 'No s\'ha pogut eliminar la tasca';

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
}
