// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Catalan Valencian (`ca`).
class AppLocalizationsCa extends AppLocalizations {
  AppLocalizationsCa([String locale = 'ca']) : super(locale);

  @override
  String get welcomeActionItemsDescription =>
      'La vostra IA extraurà automàticament tasques de les vostres converses. Apareixeran aquí quan es creïn.';

  @override
  String get chatAppsProblemFailed => 'Alguna cosa ha anat malament. Torna-ho a provar.';

  @override
  String get deviceOnboardingStarConversation => 'Destaca la conversa en curs';

  @override
  String get deleteAll => 'Eliminar tot';

  @override
  String get copySummary => 'Copiar resum';

  @override
  String get locationAccessDesc => 'Perquè l\'Omi pugui anotar on han tingut lloc les teves converses.';

  @override
  String get firmwareUpdate => 'Actualització del firmware';

  @override
  String get chatMessages => 'missatges';

  @override
  String get showEventsNoParticipants => 'Mostrar esdeveniments sense participants';

  @override
  String get sharePeriodYear => 'Enguany, Omi ha:';

  @override
  String get dreamReportRunFailed => 'No s\'ha pogut executar Dream. Torna-ho a provar.';

  @override
  String get sttModelAccuracy => 'Precisió';

  @override
  String get scopes => 'Àmbits';

  @override
  String get deleteFlowFeedbackSubtitle => 'Què hauria fet que Omi funcionés per a tu?';

  @override
  String appDataAccessTitle(String appName) {
    return 'Vols permetre l\'accés a $appName?';
  }

  @override
  String get pendantStorageAlmostFull =>
      'L\'emmagatzematge del penjoll és gairebé ple: mantén l\'aplicació oberta per sincronitzar.';

  @override
  String get deviceOnboardingAllSetDoublePressBadge => '2×';

  @override
  String get copyErrorMessage => 'Copiar missatge d\'error';

  @override
  String get filterMemories => 'Filtrar records';

  @override
  String get helpsDiagnoseIssuesAutoDeletes =>
      'Ajuda a diagnosticar problemes. S\'elimina automàticament després de 3 dies.';

  @override
  String get locationServiceDisabledDesc =>
      'Els serveis d\'ubicació estan desactivats en aquest dispositiu. Activa\'ls a Configuració.';

  @override
  String chatAppsIsConnected(String app) {
    return '$app està connectat';
  }

  @override
  String get paymentMethodStripe => 'Stripe';

  @override
  String get deleteReasonTechnicalIssues => 'Massa problemes tècnics';

  @override
  String get payments => 'Pagaments';

  @override
  String get verifiedFallback => 'Verificat';

  @override
  String get pleaseWait => 'Si us plau, espereu…';

  @override
  String get appLanguage => 'Idioma de l\'aplicació';

  @override
  String get unknownApp => 'Aplicació desconeguda';

  @override
  String get appReEnableFailedBody => 'No s\'ha pogut reactivar aquesta app. Torna-ho a provar.';

  @override
  String get somethingWentWrongTryAgain => 'Alguna cosa ha anat malament! Si us plau, torneu-ho a provar més tard.';

  @override
  String get upgradeScheduled => 'Actualització programada';

  @override
  String get wrappedBuddiesLabel => 'AMICS';

  @override
  String get chatBlockShowMore => 'Mostra\'n més';

  @override
  String get subscriptionSuccessfulCharged => 'Subscripció correcta! Se t\'ha cobrat pel nou període de facturació.';

  @override
  String get phoneCall => 'Trucada';

  @override
  String get chatAppsRefreshFailed => 'No s\'ha pogut actualitzar. Mostrem el que vam veure per últim cop.';

  @override
  String get noDesktopAccess => 'No funciona a l\'escriptori';

  @override
  String get areYouSure => 'Esteu segur?';

  @override
  String get resubscribe => 'Tornar a subscriure';

  @override
  String voiceMatchMeterLabel(String level) {
    return 'Coincidència de veu: $level';
  }

  @override
  String get syncingBackground => 'Continuarem sincronitzant els vostres enregistraments en segon pla.';

  @override
  String get signOutQuestion => 'Tancar sessió?';

  @override
  String chatAppsReadOnlyBanner(String app) {
    return 'Només lectura. Respon a l\'Omi a $app.';
  }

  @override
  String get connected => 'Connectat';

  @override
  String get shareStatsMessage =>
      'Compartint les meves estadístiques d\'Omi! (omi.me - el vostre assistent d\'IA sempre actiu)';

  @override
  String get frequencyMinimal => 'Mínim';

  @override
  String get addAppSelectLogo => 'Seleccioneu un logotip per a la vostra aplicació';

  @override
  String get integrationInstructions => 'Instruccions d\'integració';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'Estat del permís d\'accessibilitat: $status. Si us plau, comproveu Preferències del Sistema.';
  }

  @override
  String get wrappedCompleted => 'completades';

  @override
  String get remaining => 'Restant';

  @override
  String get onDeviceIntensive => 'La transcripció al dispositiu és computacionalment intensiva.';

  @override
  String get diagnosticsVerdictTrouble => 'Té problemes per connectar-se';

  @override
  String deviceOnboardingVoiceReplyPreviewThroughDevice(String device) {
    return 'A través del $device';
  }

  @override
  String get copyConfig => 'Copiar configuració';

  @override
  String accessesDataTypes(String dataTypes) {
    return 'Accedeix a $dataTypes';
  }

  @override
  String get chatAppsWaitlistConfirmed => 'Gràcies. WhatsApp apareixerà aquí quan estigui a punt.';

  @override
  String get undo => 'Desfer';

  @override
  String get phoneContactsAccessTitle => 'Permet l\'accés als contactes';

  @override
  String confidenceIsConfirmed(String name) {
    return '$name està Confirmat. No cal fer res més.';
  }

  @override
  String get wrappedMovie => 'PEL·LÍCULA';

  @override
  String get wrappedStruggleLabelUpper => 'LLUITA';

  @override
  String get appleHealthFeatureChatDesc =>
      'Pregunta a Omi sobre els teus passos, son, freqüència cardíaca i entrenaments.';

  @override
  String get writeReviewOptional => 'Escriu una ressenya (opcional)';

  @override
  String get pairNewDevice => 'Aparellar un dispositiu nou';

  @override
  String chatUsedOfLimitCompute(String used, String limit) {
    return '$used de $limit pressupost de càlcul utilitzat';
  }

  @override
  String get dailySummary => 'Resum diari';

  @override
  String get pleaseEnterYourName => 'Si us plau, introduïu el vostre nom';

  @override
  String get continueWithoutDevice => 'Continuar sense dispositiu';

  @override
  String get configure => 'Configurar';

  @override
  String get createApp => 'Crear aplicació';

  @override
  String get invalidUrlError => 'Introduïu un URL vàlid';

  @override
  String get appClosed => 'Aplicació tancada';

  @override
  String get downgradeToFreemiumAction => 'Passa a la versió gratuïta';

  @override
  String get chatAppsUseTelegramForNow => 'Fes servir Telegram de moment';

  @override
  String get wrappedBestMomentsBadge => 'Millors moments';

  @override
  String get storageSection => 'Emmagatzematge';

  @override
  String get pauseResumeRecording => 'Pausar/Reprendre enregistrament';

  @override
  String get phoneUnmute => 'Activar so';

  @override
  String get youreAllSet => 'Estàs a punt!';

  @override
  String get migrationComplete => 'Migració completada!';

  @override
  String get paymentAppCost => 'Cost de l\'aplicació';

  @override
  String get deviceOnboardingFinish => 'Finalitza';

  @override
  String get noVerifiedNumbers => 'Cap numero verificat';

  @override
  String get connectAiAssistantsToData => 'Connecta assistents d\'IA a les teves dades';

  @override
  String get keyNameHint => 'p. ex., Claude Desktop';

  @override
  String get paymentMethods => 'Mètodes de Pagament';

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'Error en comprovar el permís d\'accessibilitat: $error';
  }

  @override
  String get confidenceReasonAutoOnly => 'Etiquetada automàticament, encara no confirmada';

  @override
  String whatsNewInVersion(String version) {
    return 'Novetats a $version';
  }

  @override
  String get selectYourLanguage => 'Seleccioneu el vostre idioma';

  @override
  String get memoryClearedSuccess => 'La memòria d\'Omi sobre vós s\'ha esborrat';

  @override
  String get memoryContentHint => 'Prefereixo les reunions al matí.';

  @override
  String get dreamReportTitle => 'Informe de Dream';

  @override
  String importErrorGeneric(String error) {
    return 'Error: $error';
  }

  @override
  String get completionRate => 'Taxa de compleció';

  @override
  String get trackPersonalGoals => 'Fes el seguiment d\'objectius personals a la pàgina d\'inici';

  @override
  String get wrappedTryAgain => 'Torna a provar';

  @override
  String get dataProtection => 'Protecció de dades';

  @override
  String get yourConversations => 'Les teves converses';

  @override
  String pdfTitleLabel(String title) {
    return 'Títol: $title';
  }

  @override
  String get sendRawAudioToOmiDescription =>
      'Desactiva-ho per impedir que l\'àudio sense processar s\'enviï a Omi. Les transcripcions i les dades necessàries per a les funcions al núvol encara es poden enviar a Omi.';

  @override
  String get entityLoadFailed => 'No s’ha pogut carregar aquesta pàgina.';

  @override
  String get networkNameSsid => 'Nom de la xarxa (SSID)';

  @override
  String get discovery => 'Descobriment';

  @override
  String get rayBanMetaMicPickerConnectError =>
      'No s\'ha pogut connectar a aquest micròfon. Assegura\'t que estigui connectat a la configuració de l\'iPhone.';

  @override
  String get fairUseAboutTitle => 'Sobre l\'ús raonable';

  @override
  String get wrappedYouTalkedAbout => 'Has parlat de';

  @override
  String get downgradeLimitQuality => '30% menys de qualitat de transcripció';

  @override
  String get sharedTasksUnknownSender => 'Algú';

  @override
  String get selectAReason => 'Tria un motiu';

  @override
  String get wrappedWinLabel => 'VICTÒRIA';

  @override
  String get configuration => 'Configuració';

  @override
  String get noFolder => 'Sense carpeta';

  @override
  String get manifestRefreshedSuccess => 'El manifest s\'ha actualitzat correctament';

  @override
  String get paymentStatusActive => 'Actiu';

  @override
  String get linkKeyMismatch => 'Clau d\'enllaç no coincident';

  @override
  String speakerTagPromptProgress(int current, int total) {
    return '$current de $total';
  }

  @override
  String get updateRequiredMessage =>
      'Aquesta versió d\'Omi ja no és compatible. Actualitza-la per continuar gravant i sincronitzant.';

  @override
  String get sharePeriodMonth => 'Aquest mes, Omi ha:';

  @override
  String get rollbackToStableFirmware => 'Tornar al firmware estable';

  @override
  String get paymentStatusConnected => 'Connectat';

  @override
  String get findDeviceNoneTitle => 'No s\'ha trobat cap Omi';

  @override
  String get appIdCopiedToClipboard => 'ID de l\'aplicació copiat al porta-retalls';

  @override
  String get bySubmittingYouAgreeToOmi => 'En enviar, acceptes Omi ';

  @override
  String get filterRating => 'Valoració';

  @override
  String get usageAtWork => 'A la feina';

  @override
  String get tasksCleanTodayMessage => 'Això només eliminarà els terminis';

  @override
  String get ignoredVoicesSubtitle => 'Televisió, pòdcasts i altres veus que has marcat com a «No és una persona»';

  @override
  String get permissionEnable => 'Activar';

  @override
  String integrationComingSoon(String appName) {
    return '$appName encara no és compatible.';
  }

  @override
  String get sttModelLower => 'Més baixa';

  @override
  String get loadingYourMemories => 'Carregant els teus records…';

  @override
  String get followUpQuestions => 'Preguntes de Seguiment';

  @override
  String get previousDay => 'Dia anterior';

  @override
  String fairUseCaseRefCopied(String caseRef) {
    return '$caseRef copiat';
  }

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get recordingPaused => 'Gravació en pausa';

  @override
  String get cannotReportOwnMessages => 'No pots informar dels teus propis missatges';

  @override
  String get enterWordsHint => 'Introdueix paraules (separades per comes)';

  @override
  String get audioDownloadFailed => 'Error en descarregar l\'àudio';

  @override
  String get clearMemoryMessage => 'Se suprimiran tots els teus records. Això no es pot desfer.';

  @override
  String get templateNameHint => 'p. ex. Extractor de tasques de reunió';

  @override
  String speakerLabelTalkTime(String duration) {
    return '$duration d’aquesta veu';
  }

  @override
  String get recordingMode => 'Mode de gravació';

  @override
  String get cancelReasonOther => 'Altres';

  @override
  String get sttModelHigher => 'Més alta';

  @override
  String get settingUpSystemAudioCapture => 'Configurant la captura d\'àudio del sistema';

  @override
  String memoriesCount(int count) {
    return '$count memòries';
  }

  @override
  String get noSpecificDataAccessConfigured => 'No hi ha accés a dades específic configurat.';

  @override
  String get recordingIdLabel => 'ID de l\'enregistrament';

  @override
  String get highlights => 'Punts destacats';

  @override
  String get phoneTryAgain => 'Torna-ho a provar';

  @override
  String chatAppsCouldNotOpen(String app) {
    return 'No s\'ha pogut obrir $app. Comprova que estigui instal·lada i torna-ho a provar.';
  }

  @override
  String get onDeviceTranscriptionDesc => 'La transcripció es processa localment al teu dispositiu';

  @override
  String get chatAppsTryPromise => 'Què li vaig prometre ahir a la Sam?';

  @override
  String get paymentStatusNotConnected => 'No connectat';

  @override
  String get intervalSeconds => 'Interval (segons)';

  @override
  String get authorize => 'Autoritzar';

  @override
  String get settingsHeader => 'CONFIGURACIÓ';

  @override
  String get personNameAlreadyExists => 'Ja existeix una persona amb aquest nom.';

  @override
  String get deviceOnboardingVoiceReplyPreviewThroughCurrentOutput => 'A través de la sortida d\'àudio actual';

  @override
  String get monthJun => 'Juny';

  @override
  String selectedCount(int count) {
    return '$count seleccionats';
  }

  @override
  String get batteryHistory => 'Bateria';

  @override
  String get noPastChats => 'Els teus xats amb Omi apareixen aquí.';

  @override
  String get chatAppsDoesSave => 'Desa records i gestiona les teves tasques';

  @override
  String get apiKey => 'Clau API';

  @override
  String get authFailedToLinkGoogle => 'No s\'ha pogut vincular amb Google, si us plau torneu-ho a provar.';

  @override
  String audioUploadFailedKeptLocal(String duration) {
    return 'Error en pujar — s\'han conservat $duration d\'àudio al telèfon.';
  }

  @override
  String get free => 'Gratuïta';

  @override
  String get deselectAllTasksMenu => 'Desselecciona tot';

  @override
  String get dreamReportLoadFailed => 'No s\'ha pogut carregar l\'informe de Dream.';

  @override
  String get entityRecentConversations => 'Converses recents';

  @override
  String get pendantRecordingNote =>
      'El teu penjoll grava pel seu compte. Les gravacions se sincronitzen amb el teu telèfon mentre l\'aplicació és oberta.';

  @override
  String get manageStorage => 'Gestionar emmagatzematge';

  @override
  String get filterSystem => 'Sobre vós';

  @override
  String get deleteConsequenceSubscription => 'Qualsevol subscripció activa es cancel·larà.';

  @override
  String get defaultList => 'Llista per defecte';

  @override
  String get shared => 'Compartit';

  @override
  String get customVocabulary => 'Vocabulari Personalitzat';

  @override
  String get feedbackTitleAudioQuality => 'Quins problemes has experimentat?';

  @override
  String get thisActionCannotBeUndone => 'Això no es pot desfer.';

  @override
  String errorRequestingPermission(String error) {
    return 'Error en sol·licitar permís: $error';
  }

  @override
  String get recapRegenerateFailed => 'No s\'ha pogut regenerar el resum. Torna-ho a provar més tard.';

  @override
  String get result => 'Resultat:';

  @override
  String get statusCallMissed => 'Trucada perduda';

  @override
  String get diagnosticsLongestGap => 'Interrupció més llarga';

  @override
  String get noLogFilesFound => 'No s\'han trobat fitxers de registre.';

  @override
  String get speechTranscriptionSectionTitle => 'Veu i transcripció';

  @override
  String get syncNow => 'Sincronitza ara';

  @override
  String get sttUsePrimaryLanguage => 'Utilitza l\'idioma principal';

  @override
  String get importUnsupportedFileType => 'Aquest tipus de fitxer no es pot importar.';

  @override
  String get chatSendMessage => 'Envia el missatge';

  @override
  String get syncCardAllBackedUp => 'Tots els enregistraments sincronitzats';

  @override
  String get settings => 'Configuració';

  @override
  String get backgroundLocationDeniedDesc =>
      'Aneu a la configuració del dispositiu i establiu el permís d\'ubicació a \"Permetre sempre\"';

  @override
  String get computationallyIntensive => 'La transcripció al dispositiu és computacionalment intensiva.';

  @override
  String get and => ' i ';

  @override
  String get yourVerifiedNumbers => 'Els teus numeros verificats';

  @override
  String get tasksCleanTodayTitle => 'Netejar les tasques d\'avui?';

  @override
  String get microphonePermission => 'Permís del micròfon';

  @override
  String get failedToUpdateConversationTitle => 'No s\'ha pogut actualitzar el títol de la conversa';

  @override
  String get appsDisconnected => 'Es desconnectaran les teves aplicacions i integracions.';

  @override
  String get live => 'En directe';

  @override
  String get connectionFailed => 'Connexió fallida';

  @override
  String get selectImages => 'Seleccionar imatges';

  @override
  String get playbackAudioNetworkFailed => 'Comprova la connexió';

  @override
  String get paypalEmail => 'Correu electrònic de PayPal';

  @override
  String get chatAppsOnTheList => 'A la llista';

  @override
  String get generateSummary => 'Generar resum';

  @override
  String get categoryHealth => 'Salut';

  @override
  String get transcribeLaterStorageFull =>
      'El telèfon té poc espai d\'emmagatzematge i la gravació s\'ha posat en pausa. Allibera espai o puja les gravacions i es reprendrà automàticament.';

  @override
  String get chatAppsNoChatsTitle => 'Encara no hi ha xats';

  @override
  String get onboardingSetupStepPersonalize => 'Personalitzant la teva experiència';

  @override
  String get leaveUnselectedTasks => 'Deixeu sense seleccionar per crear tasques sense projecte';

  @override
  String get wrappedButYouPushedThroughEmoji => 'Però ho vas aconseguir 💪';

  @override
  String get needHelp => 'Necessiteu ajuda?';

  @override
  String get confirmAndCancel => 'Confirma i cancel·la';

  @override
  String get frequencyDescHigh => 'Més suggeriments, unes 6–9 al dia';

  @override
  String get copyLink => 'Copiar enllaç';

  @override
  String get dreamReportLiveBanner =>
      'Dream aplica aquests canvis per si sol. Desfés qualsevol d\'ells a Canvis recents.';

  @override
  String get enterActionItemDescription => 'Introduïu la descripció de la tasca';

  @override
  String chatAppsInChannel(String app) {
    return 'A $app';
  }

  @override
  String get links => 'Enllaços';

  @override
  String get dreamReportEmptyTitle => 'Encara no hi ha execucions';

  @override
  String get monthJan => 'Gen';

  @override
  String get wrappedMostProductiveDay => 'Més productiu';

  @override
  String get productUpdate => 'Actualització del producte';

  @override
  String get addYourReview => 'Afegeix la teva ressenya';

  @override
  String get raybanMetaImageCaptureReady => 'Captura d\'imatge a punt';

  @override
  String get displayUpcomingMeetingsDescription => 'Mostra les reunions properes a la barra de menú';

  @override
  String get whatWeCollect => 'Què recopilem';

  @override
  String get connectPayPalToReceivePayments =>
      'Connecteu el vostre compte de PayPal per començar a rebre pagaments per les vostres aplicacions';

  @override
  String get justAMoment => 'Un moment, si us plau';

  @override
  String get chatReplyServerError => 'Alguna cosa ha fallat per part nostra. Torna-ho a provar.';

  @override
  String get transferInProgress => 'Transferència en curs…';

  @override
  String get usageAll => 'Des de sempre';

  @override
  String get failedToLoadContacts => 'Error en carregar els contactes';

  @override
  String appUsersCount(int count) {
    return '$count+ usuaris';
  }

  @override
  String get report => 'Informar';

  @override
  String get languageLabel => 'Idioma';

  @override
  String verifiedOnDate(String date) {
    return 'Verificat el $date';
  }

  @override
  String get customVocabularyHeader => 'VOCABULARI PERSONALITZAT';

  @override
  String otaRebooting(String deviceName) {
    return '$deviceName s\'està reiniciant amb el firmware nou.';
  }

  @override
  String get mcpServer => 'Servidor MCP';

  @override
  String get findDevice => 'Troba';

  @override
  String get msgUploadAttachedFileFailed => 'No s\'ha pogut pujar el fitxer adjunt.';

  @override
  String get appName => 'App Name';

  @override
  String get pairingTitlePlaudNote => 'Posa Plaud Note en mode d\'aparellament';

  @override
  String get moreOptions => 'Més opcions';

  @override
  String get noConversationsHeroMessage =>
      'Les converses que graves apareixen aquí. Toca el botó de gravació a l\'Inici per gravar la primera.';

  @override
  String get finish => 'Finalitza';

  @override
  String get goBack => 'Tornar';

  @override
  String get apiKeysDescription =>
      'Les claus API s\'utilitzen per a l\'autenticació quan la teva aplicació es comunica amb el servidor Omi. Permeten que la teva aplicació creï records i accedeixi a altres serveis d\'Omi de manera segura.';

  @override
  String get sttProviderSpeechmatics => 'Speechmatics';

  @override
  String get setWebhookUrlInSettings =>
      'Si us plau, configura l\'URL de Webhook a la configuració de desenvolupador per utilitzar aquesta funció.';

  @override
  String get dailyScoreBreakdown => 'Desglossament de la puntuació diària';

  @override
  String get showMeetingsMenuBarDesc =>
      'Mostrar la vostra propera reunió i el temps fins que comenci a la barra de menú de macOS';

  @override
  String get tapToTrackThisGoal => 'Toca per fer seguiment d\'aquest objectiu';

  @override
  String get summarizingConversation => 'Resumint la conversa…\nAixò pot trigar uns segons';

  @override
  String get noInternetConnection => 'Sense connexió a Internet';

  @override
  String diagnosticsCountSincePairing(int count) {
    return '$count des de l\'aparellament';
  }

  @override
  String get wrappedTasksCreated => 'tasques creades';

  @override
  String get deleteConsequenceNoRecovery => 'El teu compte no es pot restaurar — ni tan sols pel suport.';

  @override
  String get waitForReprocessing => 'Espera que acabi el reprocessament.';

  @override
  String get needYourPermission => 'Necessitem el vostre permís';

  @override
  String get downgradeLimitSpeakers => 'No es poden identificar els parlants';

  @override
  String conversationsTodayCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count converses avui.',
      one: '1 conversa avui.',
      zero: 'Avui cap conversa.',
    );
    return '$_temp0';
  }

  @override
  String get dailyScore => 'PUNTUACIÓ DIÀRIA';

  @override
  String get reportAnIssue => 'Informar d\'un problema';

  @override
  String get invalidKey => 'Tecla no vàlida';

  @override
  String get preview => 'Previsualització';

  @override
  String get nextWeek => 'La setmana que ve';

  @override
  String get confidenceUnverified => 'Sense verificar';

  @override
  String get previewScreenshots => 'Vista prèvia de captures';

  @override
  String get ledBrightness => 'Brillantor LED';

  @override
  String get firmwareUpdateFailedMessage =>
      'L\'actualització no ha acabat. El dispositiu continua amb el firmware actual i es pot fer servir amb seguretat. Mantén-lo carregat i a prop del telèfon i torna-ho a provar.';

  @override
  String get loadingProfile => 'Carregant perfil…';

  @override
  String get deleteRecapConfirmTitle => 'Esborrar aquest resum?';

  @override
  String get notificationFrequency => 'Freqüència de notificacions';

  @override
  String get captureSystemAudioFromMeetings => 'Capturar àudio del sistema de reunions';

  @override
  String get storeAudioCloudDescription => 'Puja les gravacions mentre parles perquè puguis reproduir-les més tard.';

  @override
  String get color => 'Color';

  @override
  String get open => 'Obrir';

  @override
  String get diagnosticsVerdictNoDrops => 'Cap tall aquesta setmana';

  @override
  String get autoExtractionFeature => 'Extret automàticament de converses';

  @override
  String get searchResults => 'Resultats de la cerca';

  @override
  String get v2UndetectedMessage =>
      'Veiem que teniu un dispositiu V1 o que el vostre dispositiu no està connectat. La funcionalitat de targeta SD només està disponible per a dispositius V2.';

  @override
  String get endAndProcess => 'Finalitzar i processar conversa';

  @override
  String get noSyncedRecordings => 'Encara no hi ha enregistraments sincronitzats';

  @override
  String get coworker => 'Company de feina';

  @override
  String get setupQuestionUsage => '2. On planifiques utilitzar el teu Omi?';

  @override
  String get pinnedNotSelectable => 'Fixada, no seleccionable';

  @override
  String get showMore => 'mostra més ↓';

  @override
  String get createYourFirstMemory => 'Crea el teu primer record per començar';

  @override
  String get discardedConversation => 'Conversa descartada';

  @override
  String get enableApps => 'Activar aplicacions';

  @override
  String get today => 'Avui';

  @override
  String get showEventsNoParticipantsDesc =>
      'Quan s\'activa, Properament mostra esdeveniments sense participants o enllaç de vídeo.';

  @override
  String get couldNotLoadPage => 'No s\'ha pogut carregar aquesta pàgina. Comprova la connexió i torna-ho a provar.';

  @override
  String actionItemDeletedResult(String description) {
    return 'Tasca \"$description\" eliminada';
  }

  @override
  String get deleteSampleQuestion => 'Eliminar la mostra?';

  @override
  String get youAreOnAPaidPlan => 'Estàs en un pla de pagament.';

  @override
  String get otaInstallFailed => 'La instal·lació ha fallat. El dispositiu continua amb el firmware actual.';

  @override
  String get addFirstMemory => 'Afegiu el vostre primer record';

  @override
  String get appDeletedSuccessfully => 'Aplicació eliminada amb èxit';

  @override
  String get chatAppsConnectTelegramMessage => 'L\'Omi obrirà Telegram amb un enllaç privat només per a tu.';

  @override
  String get phoneSetupStep1Title => 'Verifica el teu numero de telefon';

  @override
  String get deviceRequirements => 'El teu dispositiu no compleix els requisits per a la transcripció al dispositiu.';

  @override
  String get confidenceEvidenceHeader => 'Evidències';

  @override
  String get pleaseEnterAName => 'Si us plau, introdueix un nom.';

  @override
  String get deleteConfirmationWord => 'DELETE';

  @override
  String get speakerTagPromptThatsMe => 'Sóc jo';

  @override
  String get ourCommitment => 'El nostre compromís';

  @override
  String get notificationScopes => 'Àmbits de notificació';

  @override
  String get autoDeletesAfter3Days => 'S\'elimina automàticament després de 3 dies';

  @override
  String get initialisingRecorder => 'Inicialitzant el gravador';

  @override
  String get privateAndSecureOnDevice => 'Desat en aquest telèfon';

  @override
  String get allObjectsMigratedFinalizing => 'Tots els objectes migrats. Finalitzant…';

  @override
  String get chatAppsOpenMessages => 'Obre Missatges';

  @override
  String get upgradeToPro => 'Actualitza a Pro';

  @override
  String get clientId => 'ID de client';

  @override
  String get backgroundActivity => 'Activitat en segon pla';

  @override
  String get noSummaryAvailable => 'No hi ha cap resum disponible';

  @override
  String get failedToUpdateStarred => 'No s\'ha pogut actualitzar l\'estat de destacat.';

  @override
  String get omiYourAiCompanion => 'Omi – El vostre company d\'IA';

  @override
  String get pleaseSelectReason => 'Si us plau, selecciona un motiu';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Se suprimiran tots els $count records. Això no es pot desfer.';
  }

  @override
  String get connectNow => 'Connecta ara';

  @override
  String chatAppsDisconnectTitle(String app) {
    return 'Vols desconnectar $app?';
  }

  @override
  String get clearCredentials => 'Esborra les credencials';

  @override
  String get grantContactsPermissionForSms => 'Si us plau, concedeix permís de contactes per compartir via SMS';

  @override
  String get cloudTranscription => 'Transcripció al núvol';

  @override
  String get memoryHistory => 'Historial';

  @override
  String get speechSamples => 'Mostres de veu';

  @override
  String get wrappedBiggest => 'El més gran';

  @override
  String get reviewShowMore => 'Mostra’n més';

  @override
  String get triggersWhenDaySummaryGenerated => 'S\'activa quan es genera un resum del dia.';

  @override
  String get thankYouFeedback => 'Gràcies pels vostres comentaris!';

  @override
  String get allow => 'Permet';

  @override
  String triggeredByType(String triggerType) {
    return 'activat per $triggerType';
  }

  @override
  String get howToPair => 'Com vincular';

  @override
  String get conversationDeveloperTools => 'Eines de desenvolupador a les converses';

  @override
  String get memoryProvenanceIphone => 'iPhone';

  @override
  String get aboutYou => 'Sobre tu';

  @override
  String get memoryProvenanceMac => 'Mac';

  @override
  String get effectCounts => 'Ajuda';

  @override
  String get tagSpeakerIncludingLaterSpeech => 'Etiqueta també la parla posterior d\'aquest parlant';

  @override
  String get storeAudioOnPhone => 'Emmagatzemar àudio al telèfon';

  @override
  String get developerApiKeys => 'Claus API de desenvolupador';

  @override
  String get wrappedMyBuddiesCard => 'Els meus amics';

  @override
  String get bulkExportAlreadyExported => 'Totes les tasques seleccionades ja s\'han exportat';

  @override
  String get popularBadge => 'POPULAR';

  @override
  String get enableLocationTitle => 'Activa la ubicació';

  @override
  String get feedbackBug => 'Comentaris / Error';

  @override
  String get good => 'Bo';

  @override
  String get upgradeYourPlan => 'Actualitza el teu pla';

  @override
  String get exportingAllData =>
      'S\'estan exportant les teves dades… No tanquis Omi; els comptes grans poden trigar diversos minuts.';

  @override
  String get switchAndRestart => 'Canvia';

  @override
  String get noReposFound => 'No s\'han trobat repositoris';

  @override
  String get latest => 'Últim';

  @override
  String get failedToRevoke => 'No s\'ha pogut revocar l\'autorització. Torneu-ho a provar.';

  @override
  String get appleHealthDisconnectCta => 'Desconnectar Apple Health';

  @override
  String get chatAppsPrivateMemoriesSubtitle =>
      'La salut, els diners i tot el que has marcat com a privat es queda fora de les aplicacions de xat.';

  @override
  String get deleteFlowFeedbackTitle => 'Explica\'ns més';

  @override
  String get failedToConnectTodoistRetry => 'No s\'ha pogut connectar a Todoist. Si us plau, torna-ho a provar.';

  @override
  String get capturePhoneStorageFull => 'Emmagatzematge del telèfon ple';

  @override
  String deletePeopleTitle(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Eliminar $count persones?',
      one: 'Eliminar 1 persona?',
    );
    return '$_temp0';
  }

  @override
  String get cleanUpNothingMessage => 'Ara mateix Omi no dubta de ningú.';

  @override
  String get writeAReviewOptional => 'Escriu una ressenya (opcional)';

  @override
  String get syncFailed => 'Error de sincronització';

  @override
  String get audioShareFailed => 'Error en compartir';

  @override
  String loadMoreRemaining(String count) {
    return 'Carregar més ($count restants)';
  }

  @override
  String get phoneDeleteNumberFailed => 'No s\'ha pogut suprimir aquest número';

  @override
  String deviceUsesCodec(String device, String reason) {
    return '$device grava en un format que aquest proveïdor no pot llegir ($reason), així que s\'usarà la transcripció d\'Omi.';
  }

  @override
  String get chatAppsConnectIMessageMessage =>
      'Envia un sol missatge a l\'Omi des del número que vulguis fer servir. El codi que conté vincula aquest número al teu compte.';

  @override
  String get speechToTextUnavailableDesc =>
      'La transcripció de veu no està disponible ara mateix. Comprova la connexió a Internet i la configuració del reconeixement de veu del dispositiu i torna-ho a provar.';

  @override
  String get chatReplyTimeout => 'La resposta ha trigat massa. Torna-ho a provar.';

  @override
  String get passwordMinLengthError => 'La contrasenya ha de tenir almenys 8 caràcters';

  @override
  String get chatAppsWhatsAppMessage =>
      'Estem treballant per portar l\'Omi a WhatsApp. Apareixerà aquí quan estigui a punt.';

  @override
  String get deleteAccountCheckbox =>
      'Entenc que eliminar el meu compte és permanent i totes les dades, incloent records i converses, es perdran i no es poden recuperar.';

  @override
  String get firmwareConnectWifi => 'Connecta\'t a WiFi o dades mòbils.';

  @override
  String get forgetDeviceConfirmMessage => 'Omi deixarà de connectar-se a aquest dispositiu.';

  @override
  String get editSwipeFeature => 'Toqueu per editar, llisqueu per completar o eliminar';

  @override
  String get memoryManagement => 'Gestió de memòria';

  @override
  String get transcriptLoadFailed => 'No s\'ha pogut carregar la transcripció.';

  @override
  String get diagnosticsExportTitle => 'Diagnòstics del dispositiu Omi';

  @override
  String get updateOmiFirmware => 'Actualitza el firmware d\'Omi';

  @override
  String get importTooManyAttempts => 'Hi ha massa importacions ara mateix. Torna-ho a provar més tard.';

  @override
  String get noAppsFound => 'No s\'han trobat aplicacions';

  @override
  String get phoneSetupStep1Subtitle => 'Et trucarem per confirmar que es teu';

  @override
  String get deleteSyncedFiles => 'Eliminar enregistraments sincronitzats';

  @override
  String speakerLabelVoiceStatus(String state) {
    String _temp0 = intl.Intl.selectLogic(
      state,
      {
        'learned': 'Veu apresa',
        'pending': 'Aprenent la veu…',
        'disabled': 'El desament de veus està desactivat',
        'other': 'Veu encara no apresa',
      },
    );
    return '$_temp0';
  }

  @override
  String get recordingsMayCaptureOthers =>
      'Les gravacions poden capturar les veus d\'altres persones. Assegureu-vos de tenir el consentiment de tots els participants abans d\'activar.';

  @override
  String get helpful => 'Útil';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return 'Descarregant $model: $received / $total MB';
  }

  @override
  String get permissions => 'Permisos';

  @override
  String get audioDownloadSuccess => 'Àudio descarregat correctament';

  @override
  String get confirmPlanChange => 'Confirmar canvi de pla';

  @override
  String get wrappedThatAwkwardMoment => 'Aquell moment incòmode';

  @override
  String get calendarProviders => 'Proveïdors de calendari';

  @override
  String evidenceAutoUnconfirmed(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count etiquetes automàtiques encara no confirmades',
      one: '1 etiqueta automàtica encara no confirmada',
    );
    return '$_temp0';
  }

  @override
  String get importData => 'Importar dades';

  @override
  String get weekdayMon => 'Dl';

  @override
  String get deviceStorageTitle => 'Emmagatzematge del dispositiu';

  @override
  String get externalAppAccess => 'Accés d\'aplicacions externes';

  @override
  String get transcriptionUnavailable => 'Transcripció no disponible';

  @override
  String get termsAndPrivacyPolicy => 'Termes i Política de Privacitat';

  @override
  String get noImportsYet => 'Encara no hi ha importacions';

  @override
  String get openOmiOnAppleWatchDescription =>
      'L\'aplicació Omi està instal·lada al teu Apple Watch. Obre-la i toca Iniciar per començar.';

  @override
  String dreamReportFailed(String error) {
    return 'Error ($error)';
  }

  @override
  String get sendSummary => 'Enviar resum';

  @override
  String get filterAll => 'Tot';

  @override
  String get deleteChatMessage => 'Desapareixerà dels xats anteriors per sempre.';

  @override
  String get timeout10Minutes => '10 minuts';

  @override
  String get noCalendarEventsNearby => 'No s\'han trobat esdeveniments del calendari al voltant d\'aquesta hora.';

  @override
  String get cancelSyncQuestion => 'Cancel·lar la sincronització?';

  @override
  String get whatShouldWeMake => 'Què hauríem de fer?';

  @override
  String get usageListened => 'Listened';

  @override
  String get errorUpdatingStripeDetails =>
      'Error en actualitzar els detalls de Stripe! Si us plau, torneu-ho a provar més tard.';

  @override
  String get conversationEndAfterHours => 'Les converses ara finalitzaran després de 4 hores de silenci';

  @override
  String get issueActivatingApp => 'Hi ha hagut un problema en activar aquesta aplicació. Torna-ho a provar.';

  @override
  String get appCreatedSuccessfully => 'Aplicació creada amb èxit!';

  @override
  String get categoryNews => 'Notícies';

  @override
  String get phoneSearchHint => 'Cercar';

  @override
  String peoplePinnedCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count fixades',
      one: '1 fixada',
    );
    return '$_temp0';
  }

  @override
  String get wrappedHours => 'hores';

  @override
  String get phoneKeypad => 'Teclat';

  @override
  String get peopleFilterLowConfidence => 'Confiança baixa';

  @override
  String get agreeToContributeData => 'Entenc i accepto contribuir amb les meves dades per a l\'entrenament d\'IA';

  @override
  String get addGoal => 'Afegir objectiu';

  @override
  String get dreamReportRunInProgress => 'Ja hi ha una execució en curs. Torna-ho a provar d\'aquí a un minut.';

  @override
  String importedConfig(String providerName) {
    return 'Configuració de $providerName importada';
  }

  @override
  String monthsAgo(int count) {
    return 'fa $count mesos';
  }

  @override
  String get downgradeLimitationsHeading => 'Tindràs aquestes limitacions:';

  @override
  String get chatRemoveSelectedText => 'Elimina el text citat';

  @override
  String get firmwareBatteryAbove15 => 'Bateria superior al 15%';

  @override
  String reviewQuestionSamePerson(String name) {
    return 'És la mateixa persona que «$name»?';
  }

  @override
  String get effectCountsALot => 'Ajuda molt';

  @override
  String get sdCard => 'Targeta SD';

  @override
  String get openInGoogleCalendar => 'Obre a Google Calendar';

  @override
  String get appleHealthFeatureSecureTitle => 'Sincronització segura';

  @override
  String get conversationDeveloperToolsDescription =>
      'Mostra Copia l\'ID de la conversa i Prova la indicació al menú de la conversa';

  @override
  String get host => 'Amfitrió';

  @override
  String get deleteReasonMissingFeatures => 'Falten funcions que necessito';

  @override
  String get syncingInProgress => 'Sincronització en curs';

  @override
  String get tabDone => 'Fet';

  @override
  String get revoke => 'Revocar';

  @override
  String get mcp => 'MCP';

  @override
  String get anyoneCanDiscoverTemplate => 'Qualsevol pot descobrir la vostra plantilla';

  @override
  String get mcpDescription =>
      'Per connectar Omi amb altres aplicacions per llegir, cercar i gestionar els vostres records i converses. Creeu una clau per començar.';

  @override
  String get connectionLostDescription =>
      'La connexió s\'ha interromput. Comproveu la connexió a Internet i torneu-ho a provar.';

  @override
  String chatAppsNoChatsMessage(String app) {
    return 'Els xats que tinguis amb l\'Omi a $app apareixeran aquí.';
  }

  @override
  String get storedLocallyNeverShared => 'Desat en aquest telèfon. Només s\'envia al proveïdor de transcripció.';

  @override
  String get morePaymentMethodsComingSoon => 'Aviat hi haurà més mètodes de pagament';

  @override
  String get allCaughtUp => 'Tot al dia';

  @override
  String previewImageLabel(int index, int total) {
    return 'Captura $index de $total';
  }

  @override
  String get disable => 'Desactivar';

  @override
  String get recordings => 'Enregistraments';

  @override
  String get enterPersonsName => 'Introdueix el nom de la persona';

  @override
  String get newConversationCreated => 'Nova conversa creada';

  @override
  String resetsInDays(int count) {
    return 'Es reinicia en $count dies';
  }

  @override
  String get confidenceConfirmed => 'Confirmat';

  @override
  String get bulkExportInProgress => 'S\'està exportant…';

  @override
  String get detectLanguages => 'Detectar més de 10 idiomes';

  @override
  String get phoneSpeaker => 'Altaveu';

  @override
  String get visitWebsite => 'Visitar el lloc web';

  @override
  String get howToTakeGoodSample => 'Com fer una bona mostra?';

  @override
  String get clearChat => 'Esborrar xat';

  @override
  String languageSetTo(String language) {
    return 'Idioma establert a $language';
  }

  @override
  String get deviceOnboardingVoiceReplyHeadphonesDescription =>
      'Privat. Parla només a través del AirPods, Bluetooth o auriculars amb cable.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'El teu pla romandrà actiu fins $date. Després, perdràs l\'accés a les funcions il·limitades.';
  }

  @override
  String get clientSecret => 'Secret de client';

  @override
  String get pairingTitleAppleWatch => 'Connecteu Apple Watch';

  @override
  String get share => 'Compartir';

  @override
  String get yourPrivacyYourControl => 'La vostra privadesa, el vostre control';

  @override
  String get tapToCopy => 'Toca per copiar';

  @override
  String get feedbackTitleFoundAlternative => 'A què estàs canviant?';

  @override
  String get all => 'Tot';

  @override
  String get filterCapabilities => 'Capacitats';

  @override
  String get tagOtherSegments => 'Etiquetar altres segments';

  @override
  String get entityDecisions => 'Decisions';

  @override
  String get tasksCreatedInWorkspace => 'Les tasques es crearan en aquest espai de treball';

  @override
  String get fairUseDailyTranscription => 'Daily Transcription';

  @override
  String get pausePlayback => 'Pausa';

  @override
  String get sharedTasksLinkExpired => 'No s\'han trobat aquestes tasques compartides o l\'enllaç ha caducat.';

  @override
  String get editConversationDialogTitle => 'Editar conversa';

  @override
  String get deleteMemoryConfirmation => 'Vols eliminar aquest record? Això no es pot desfer.';

  @override
  String get appUnderReviewMessage =>
      'La teva aplicació està en revisió i només és visible per a tu. Serà pública un cop aprovada.';

  @override
  String get illDoItLater => 'Ho faré més tard';

  @override
  String get captureStillRecording => 'Encara s\'està gravant';

  @override
  String confidenceNextLabels(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Etiqueta\'ls en $count converses més.',
      one: 'Etiqueta\'ls en 1 conversa més.',
    );
    return '$_temp0';
  }

  @override
  String get speakerTagPromptAnswerFailed => 'No s’ha pogut desar. Torna-ho a provar.';

  @override
  String get feedbackReasonSummaryIncomplete => 'Incomplete';

  @override
  String get errorActivatingApp => 'Error en activar l\'aplicació';

  @override
  String get tasksCompleted => 'Tasques completades';

  @override
  String onboardingStepOf(int current, int total) {
    return 'Pas $current de $total';
  }

  @override
  String get downgradeAnyway => 'Baixa de pla igualment';

  @override
  String get leaveBlank => 'Deixa-ho en blanc';

  @override
  String get chatAppsViewChats => 'Mostra els xats';

  @override
  String get captureScreenRecordingPermissionRequired => 'Es requereix permís d\'enregistrament de pantalla';

  @override
  String get accountCutoverUpdateRequiredTitle => 'Actualización requerida';

  @override
  String weeksAgo(int count) {
    return 'fa $count setmanes';
  }

  @override
  String get phoneEndCall => 'Finalitzar';

  @override
  String get startupFailedMessage =>
      'S\'ha produït un error mentre l\'Omi s\'iniciava. Comprova la teva connexió i torna-ho a provar.';

  @override
  String get permissionRevokedTitle => 'Permís revocat';

  @override
  String get chatFeatures => 'Funcions de xat';

  @override
  String get couldNotLoadMap => 'No s\'ha pogut carregar el mapa';

  @override
  String get selectContactsToShare => 'Selecciona contactes per compartir';

  @override
  String get ok => 'D\'acord';

  @override
  String get memoryReviewConfirmed => 'Confirmat.';

  @override
  String get deleteKnowledgeGraph => 'Eliminar graf de coneixement';

  @override
  String get reviewChangeFailed => 'No s’ha pogut actualitzar aquest canvi. Torna-ho a provar.';

  @override
  String get limitless => 'Limitless';

  @override
  String uploadingToCloud(int current, int total) {
    return 'Pujant $current de $total';
  }

  @override
  String get dontSeeYourDevice => 'No veus el teu dispositiu?';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Les vostres tasques es sincronitzaran amb el vostre compte de $appName';
  }

  @override
  String appSettingsLabel(String appName) {
    return 'Configuració de $appName';
  }

  @override
  String get chatBlockShowLess => 'Mostra\'n menys';

  @override
  String get mindMap => 'Mind Map';

  @override
  String get authorizationBearer => 'Autorització: Bearer <clau>';

  @override
  String get dreamReportWouldSuggestTasks => 'Suggeriria tasques';

  @override
  String get dreamReportWouldAsk => 'Et preguntaria';

  @override
  String get getFreeUnlimitedAccess => 'Aconsegueix accés il·limitat gratuït';

  @override
  String get yourDaysJourney => 'El viatge del teu dia';

  @override
  String get transcriptReceived => 'Transcripció rebuda';

  @override
  String get expand => 'Expandeix';

  @override
  String get onboardingCompleteMessage =>
      'Deixa Omi en funcionament un parell de dies. Les teves converses, records i tasques començaran a omplir-se.';

  @override
  String get trainFamilyProfiles => 'Entrenar perfils d\'amics i família';

  @override
  String get selectText => 'Seleccionar text';

  @override
  String get generatingDescription => 'Generant descripció…';

  @override
  String get deviceOnboardingStarConversationDesc => 'Marca la conversa com a important';

  @override
  String disableAppNamed(String appName) {
    return 'Desactiva $appName';
  }

  @override
  String get deleteConversationConfirmation => 'Vols eliminar aquesta conversa? Això no es pot desfer.';

  @override
  String get contentCopied => 'Contingut copiat al porta-retalls';

  @override
  String get joinTheCommunity => 'Uneix-te a la comunitat!';

  @override
  String get noContactsWithPhoneNumbers => 'No s\'han trobat contactes amb números de telèfon';

  @override
  String get removeAttachment => 'Elimina el fitxer adjunt';

  @override
  String get followTheVoiceInstructions => 'Segueix les instruccions de veu';

  @override
  String get createYourOwnApp => 'Crea la teva pròpia aplicació';

  @override
  String get paymentDetails => 'Detalls de pagament';

  @override
  String get tellOmiWhoSaidIt => 'Digues a Omi qui ho va dir 🗣️';

  @override
  String audioInputSetTo(String deviceName) {
    return 'Entrada d\'àudio establerta a $deviceName';
  }

  @override
  String get pleaseEnterValidEmail => 'Si us plau, introduïu una adreça de correu electrònic vàlida';

  @override
  String get thisYear => 'Enguany';

  @override
  String get noTranscriptMessage => 'Aquesta conversa no té transcripció.';

  @override
  String get appearanceDark => 'Fosc';

  @override
  String get createCustomTemplate => 'Crear plantilla personalitzada';

  @override
  String get monthMay => 'Maig';

  @override
  String get tasksAddedToList => 'Les tasques s\'afegiran a aquesta llista';

  @override
  String isTriggeredBy(String triggerDescription) {
    return 'És $triggerDescription.';
  }

  @override
  String get deleteConversationTitle => 'Eliminar conversa?';

  @override
  String get accountCutoverUpdateRequiredMessage =>
      'Instala la última app de Omi para continuar después de la migración de la cuenta.';

  @override
  String get txtFormat => 'TXT';

  @override
  String chatAppsDisconnectMessage(String app) {
    return 'L\'Omi deixarà de respondre a $app i esborrarà l\'historial de xat que en guarda. Els missatges que ja són a $app hi continuaran.';
  }

  @override
  String get captureWithCamera => 'Capturar amb la càmera';

  @override
  String get appIdLabel => 'ID de l\'aplicació';

  @override
  String get endpointUrl => 'URL del punt final';

  @override
  String get actionItemUpdated => 'Tasca actualitzada';

  @override
  String itemsSelected(int count) {
    return '$count seleccionats';
  }

  @override
  String get onboardingWhatIKnowAboutYouDescription =>
      'Aquí tens un resum del que sé de tu basant-me en les nostres converses. Pots editar qualsevol cosa que no sigui correcta.';

  @override
  String diagnosticsLastDuration(String duration) {
    return 'Últims $duration';
  }

  @override
  String get pairingDescLimitless =>
      'Quan qualsevol llum sigui visible, premeu un cop i després manteniu premut fins que el dispositiu mostri una llum rosa, després deixeu anar.';

  @override
  String get chatBlockOpenConversation => 'Obre la conversa';

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '$used de $limit informacions obtingudes aquest mes';
  }

  @override
  String get connectionErrorDesc =>
      'No s\'ha pogut connectar amb el servidor. Comproveu la vostra connexió a internet i torneu-ho a provar.';

  @override
  String get enterWordsCommaSeparated => 'Introdueix paraules (separades per comes)';

  @override
  String get otherDevicesComingSoon => 'Altres dispositius properament';

  @override
  String speakerSuggestionChip(String name) {
    return '$name?';
  }

  @override
  String get speakerTagPromptNotAPersonToast => 'Marcat com a no és una persona';

  @override
  String get createKeyToGetStarted => 'Crea una clau per començar';

  @override
  String get captureRecordingSeparateConfirm => 'Separa';

  @override
  String get diagnosticsDrops => 'Talls';

  @override
  String lowBatteryAlertBody(int level) {
    return 'La teva bateria és al $level%. És hora de carregar! 🔋';
  }

  @override
  String get deviceOnboardingTurnOffSubtitle => 'Mantén premut el botó 3 segons';

  @override
  String get done => 'Fet';

  @override
  String get wifiConfigurationSubtitle =>
      'Introduïu les credencials WiFi per permetre al dispositiu descarregar el firmware.';

  @override
  String get permissionGrantedNow =>
      'Permís atorgat! Ara:\n\nObriu l\'aplicació Omi al vostre rellotge i toqueu \"Continuar\" a continuació';

  @override
  String get setUpPayPal => 'Configurar PayPal';

  @override
  String get statusProcessed => 'Processat';

  @override
  String phoneFreeCallsRemaining(int remaining, int limit) {
    return 'Queden $remaining de $limit trucades gratuïtes aquest mes';
  }

  @override
  String get event => 'Esdeveniment';

  @override
  String get conversationEvents => 'Esdeveniments de conversa';

  @override
  String get uninstall => 'Desinstal·lar';

  @override
  String get appCreators => 'Creadors d\'apps';

  @override
  String get muted => 'Silenciat';

  @override
  String get deleteRecapAction => 'Esborra';

  @override
  String get addAppErrorSelectingThumbnailRetry => 'Error en seleccionar la miniatura. Torneu-ho a provar.';

  @override
  String get basicPlanDescription => '300 minuts premium + il·limitat al dispositiu';

  @override
  String get countrySelectionPermanent => 'La selecció del país és permanent i no es pot canviar més tard.';

  @override
  String get transcriptionConnecting => 'Connectant la transcripció…';

  @override
  String transcriptionsPendingFraction(int pending, int total) {
    return 'Transcripcions pendents $pending/$total';
  }

  @override
  String get apiKeyAuth => 'Autenticació amb clau API';

  @override
  String downloadModelWithName(String model) {
    return 'Descarregar model ($model)';
  }

  @override
  String get devModeInvalidDaySummaryWebhookUrl => 'URL del webhook de resum del dia no vàlida';

  @override
  String get memoryReviewSaveFailed => 'No s\'ha pogut desar, torna-ho a provar';

  @override
  String get payYourSttProvider => 'Gratuït a Omi. Pagues directament al proveïdor de transcripció.';

  @override
  String get dailySummaryHeader => 'RESUM DIARI';

  @override
  String get fairUseStageWarning => 'Avís';

  @override
  String get multipleSpeakersDesc =>
      'Sembla que hi ha diversos parlants a l\'enregistrament. Assegureu-vos que esteu en un lloc tranquil i torneu-ho a provar.';

  @override
  String get pastChats => 'Xats anteriors';

  @override
  String get listeningMins => 'Escoltant (min)';

  @override
  String get pairingDescOmi => 'Manteniu premut el dispositiu fins que vibri per encendre\'l.';

  @override
  String get deviceOnboardingIntroSubtitle =>
      'Prova la transcripció en directe, fer una pregunta i la drecera de doble toc.';

  @override
  String get autoRemoveSyncedCopiesTitle => 'Elimina automàticament les còpies sincronitzades';

  @override
  String chatAppsReadOnlyFooter(String app) {
    return 'Aquests xats són de només lectura aquí. Respon a $app.';
  }

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'El micròfon ha canviat. Reprenent en ${countdown}s';
  }

  @override
  String get takePhoto => 'Fer foto';

  @override
  String get cancelSync => 'Cancel·lar sincronització';

  @override
  String appSettings(String appName) {
    return 'Configuració de $appName';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'Error en comprovar el permís de micròfon: $error';
  }

  @override
  String get micGain => 'Guany del micròfon';

  @override
  String get collectingData => 'Recollint dades…';

  @override
  String get memoryReadOnlyHint => 'Aquest record es conserva com a historial i no es pot editar.';

  @override
  String get appUnderReviewOwner =>
      'La teva aplicació està en revisió i només visible per a tu. Serà pública un cop aprovada.';

  @override
  String get addNewPerson => 'Afegir nova persona';

  @override
  String get nameSpeakerTitle => 'Anomena el parlant';

  @override
  String get downloadingAudioFromSdCard => 'Descarregant àudio de la targeta SD del teu dispositiu';

  @override
  String get pendantSyncingRecordings => 'S\'estan sincronitzant les gravacions del teu penjoll…';

  @override
  String get otaNotSupported => 'Aquest firmware no es pot actualitzar per Wi-Fi.';

  @override
  String get wrappedSomethingWentWrong => 'Alguna cosa\nha fallat';

  @override
  String get screenRecording => 'Gravació de pantalla';

  @override
  String get audioProcessedLocally =>
      'Laudio es processa localment. Funciona sense connexió, més privat, però consumeix més bateria.';

  @override
  String get onboardingSignIn => 'Inicia sessió';

  @override
  String timeDaysPlural(int count) {
    return '$count dies';
  }

  @override
  String get memoryReviewTitle => 'Coses que he après avui';

  @override
  String get hidePassword => 'Amaga la contrasenya';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get disconnected => 'Desconnectat';

  @override
  String get revokeApiKeyQuestion => 'Revocar clau API?';

  @override
  String get detectBrowserBasedMeetings => 'Detectar reunions basades en el navegador';

  @override
  String get failedToDeleteConversations => 'No s\'han pogut eliminar les converses';

  @override
  String get raybanMetaCapturePhoto => 'Captura foto';

  @override
  String get bleSpeed => '~30 KB/s via BLE';

  @override
  String get conversationPromptPlaceholder =>
      'Ets una aplicació increïble, rebràs una transcripció i resum d\'una conversa…';

  @override
  String get secureAuthViaGoogleAccount => 'Autenticació segura via compte de Google';

  @override
  String get omiHas => 'Omi té:';

  @override
  String get raybanMetaContinue => 'Continua';

  @override
  String get pauseRecording => 'Pausar la gravació';

  @override
  String get evidenceNothing => 'Encara no l\'has etiquetat ni confirmat';

  @override
  String get noActivityYet => 'Encara no hi ha activitat';

  @override
  String get enterPasswordError => 'Introduïu la vostra contrasenya';

  @override
  String get forgetDeviceConfirmTitle => 'Oblidar el dispositiu?';

  @override
  String get ratingsAndReviews => 'Valoracions i ressenyes';

  @override
  String get addApiKeyAfterImport => 'Haureu d\'afegir la vostra pròpia clau API després d\'importar';

  @override
  String get alreadyOnStableFirmware => 'Ja esteu a la darrera versió estable.';

  @override
  String get deleteAccountConfirm => 'Esteu segur que voleu eliminar el vostre compte?';

  @override
  String get recordingInfo => 'Informació de l\'enregistrament';

  @override
  String get feedbackReasonSummaryInaccurate => 'Inaccurate';

  @override
  String get pendantRecordingTitle => 'Gravant al penjoll';

  @override
  String get deleteWhileProcessingMessage =>
      'Aquest enregistrament s\'ha pujat però Omi encara està creant la conversa. Si l\'elimines ara i el processament falla, no es podrà recuperar. Vols eliminar-lo igualment?';

  @override
  String get createNewKey => 'Crear una nova clau';

  @override
  String get firmwareDownloadFailedMessage =>
      'No s\'ha pogut baixar l\'actualització i el dispositiu no ha canviat. Comprova la connexió a internet i torna-ho a provar.';

  @override
  String get loadingTasks => 'Carregant tasques…';

  @override
  String get previousResult => 'Resultat anterior';

  @override
  String get reviewLoadFailed => 'No s’han pogut carregar les teves preguntes.';

  @override
  String get onDevice => 'Al dispositiu';

  @override
  String get bluetoothSyncEnabled => 'Sincronització Bluetooth activada';

  @override
  String get categorySafety => 'Seguretat';

  @override
  String get unknownLocation => 'Ubicació desconeguda';

  @override
  String get newMemoryTitle => 'Record nou';

  @override
  String get conversationCannotBeMerged => 'Aquesta conversa no es pot fusionar (bloquejada o ja en procés de fusió)';

  @override
  String get summaryGenerated => 'Resum generat';

  @override
  String get createKey => 'Crea Clau';

  @override
  String get letOmiChooseAutomatically => 'Deixeu que Omi esculli automàticament la millor aplicació';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'Si us plau, reinicieu el vostre $deviceName per completar l\'actualització.';
  }

  @override
  String get goals => 'Objectius';

  @override
  String get wrappedAnErrorOccurred => 'S\'ha produït un error';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'Error en comprovar el permís del micròfon: $error';
  }

  @override
  String get connectLater => 'Connectar més tard';

  @override
  String get wrappedRememberedByOmi => 'recordat per Omi';

  @override
  String get fairUseStatusNormal => 'El vostre ús està dins dels límits normals.';

  @override
  String get includePersonalEventsDescription => 'Inclou esdeveniments personals sense assistents';

  @override
  String get week => 'Setmana';

  @override
  String get willLikelyCrash => 'Activar això probablement farà que laplicació es bloquegi o es congeli.';

  @override
  String get selectPrimaryLanguage => 'Seleccioneu el vostre idioma principal';

  @override
  String get pilotFeaturesDescription => 'Aquestes funcions són proves i no se\'n garanteix el suport.';

  @override
  String get askOmi => 'Pregunta a Omi';

  @override
  String get ifYouCancel => 'Si cancel·les:';

  @override
  String get audioOutput => 'Sortida d\'àudio';

  @override
  String get memoryReviewWrong => 'Incorrecte';

  @override
  String get couldNotSchedulePlanChange => 'No s\'ha pogut programar el canvi de pla. Si us plau, torna-ho a provar.';

  @override
  String speakerLabelEarlierMatches(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Trobada en $count converses anteriors',
      one: 'Trobada en 1 conversa anterior',
    );
    return '$_temp0';
  }

  @override
  String get deviceOnboardingListening => 'Escoltant…';

  @override
  String get speechProfileEnrollmentPrompt =>
      'Perquè Omi sàpiga quina veu és la teva — parla de qualsevol cosa durant uns 5 segons.';

  @override
  String get mcpServerUrl => 'MCP Server URL';

  @override
  String get chatBlockMemory => 'Record';

  @override
  String get noStarredConversations => 'No hi ha converses destacades';

  @override
  String get syncStatusTooOld => 'Massa antic per sincronitzar — Omi no el pot acceptar';

  @override
  String connectedAsUser(String userId) {
    return 'Connectat com a usuari: $userId';
  }

  @override
  String get phonePageTitle => 'Telefon';

  @override
  String get buildGraphButton => 'Construir graf';

  @override
  String get issuesCreatedInRepo => 'Les incidències es crearan al vostre repositori per defecte';

  @override
  String get scopeUserFacts => 'Fets de l\'usuari';

  @override
  String get unableToLoadPlans => 'No es poden carregar els plans';

  @override
  String get deleteRecording => 'Eliminar enregistrament';

  @override
  String get appDeleteFailed => 'No s\'ha pogut eliminar l\'aplicació. Torneu-ho a provar més tard.';

  @override
  String get addAppUpdatedSuccess => 'Aplicació actualitzada correctament 🚀';

  @override
  String get reviewCaughtUpTitle => 'Res per respondre';

  @override
  String get copyConversationId => 'Copia l\'ID de la conversa';

  @override
  String get helpImproveOmiBySharing => 'Ajuda a millorar Omi compartint dades d\'anàlisi anonimitzades';

  @override
  String get dataEncryptedBanner =>
      'Les teves dades estan protegides per defecte amb un xifratge fort, i tu controles com s\'emmagatzemen i s\'utilitzen.';

  @override
  String get redo => 'Torna a gravar';

  @override
  String get updateOmiGlassFirmware => 'Actualitza el firmware de l\'OmiGlass';

  @override
  String get deviceUnpairedMessage =>
      'Dispositiu desvinculat. Vés a Configuració > Bluetooth i oblida el dispositiu per completar la desvinculació.';

  @override
  String speakerLabelText(String part, String name) {
    String _temp0 = intl.Intl.selectLogic(
      part,
      {
        'likely': 'Probable',
        'soundsLike': 'Sona com $name',
        'notPerson': 'No és $name',
        'carried': 'Continua sent $name. Heretat de la teva última conversa.',
        'change': 'Canvia',
        'alsoTitle': 'Aquesta veu també és $name?',
        'alsoBody': 'Omi ha trobat la mateixa veu en converses anteriors.',
        'confirmed': 'Has confirmat aquesta etiqueta',
        'other': 'Revisa',
      },
    );
    return '$_temp0';
  }

  @override
  String get continueWithApple => 'Continua amb Apple';

  @override
  String get iUnderstand => 'Ho entenc';

  @override
  String get memoryProvenanceAndroid => 'Android';

  @override
  String get saving => 'Desant…';

  @override
  String get deviceOnboardingDoubleTapTitle => 'Personalitza el doble toc';

  @override
  String get allMemoriesPublicResult => 'Tots els records són ara públics';

  @override
  String get chatAppsAddToContacts => 'Afegeix l\'Omi als Contactes';

  @override
  String get wrappedDays => 'dies';

  @override
  String get invalidJsonError => 'JSON no vàlid';

  @override
  String syncCardNeedsAttention(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count gravacions requereixen atenció',
      one: '1 gravació requereix atenció',
    );
    return '$_temp0';
  }

  @override
  String get wrappedSwipeUpToBegin => 'Llisca amunt per començar';

  @override
  String addedToService(String serviceName) {
    return 'Afegit a $serviceName';
  }

  @override
  String get advanced => 'Avançat';

  @override
  String get autoCreateAndTagNewSpeakers => 'Creació i etiquetatge automàtic de parlants nous';

  @override
  String get appCapabilities => 'Capacitats de l\'aplicació';

  @override
  String get onboardingMicrophoneDenied =>
      'Permís de micròfon denegat. Si us plau, concediu permís a Preferències del Sistema > Privacitat i Seguretat > Micròfon.';

  @override
  String get pleaseEnterFolderName => 'Si us plau, introdueix un nom de carpeta';

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'Error en comprovar el permís de Bluetooth: $error';
  }

  @override
  String get invalidRecordingDetected => 'Gravació invàlida detectada';

  @override
  String get appAnalytics => 'Anàlisi de l\'aplicació';

  @override
  String get captureRecordingsSheetTitle => 'Enregistraments d\'aquesta conversa';

  @override
  String deletedLimitlessConversations(int count) {
    return 'S\'han eliminat $count converses de Limitless';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'Error en seleccionar la imatge: $error';
  }

  @override
  String get unnamedSpeakerLabel => 'Parlant';

  @override
  String get failedToCreateApp => 'No s\'ha pogut crear l\'aplicació. Si us plau, torneu-ho a provar.';

  @override
  String get planUpdate => 'Actualització del pla';

  @override
  String get timeout5Minutes => '5 minuts';

  @override
  String get deleteSample => 'Suprimeix la mostra';

  @override
  String get willNotSeeAgain => 'No podràs veure\'l de nou.';

  @override
  String get thisMonth => 'Aquest mes';

  @override
  String get enterName => 'Introdueix el nom';

  @override
  String get memoryThisDevice => 'Aquest dispositiu';

  @override
  String get verifiedNumbersDescription => 'Quan truquis a algu, veuran aquest numero al seu telefon';

  @override
  String get deviceOnboardingSingleTapHint => 'Això ha estat un sol toc: prova de tocar dues vegades ràpidament!';

  @override
  String autoClosingInSeconds(int seconds) {
    return 'Tancant automàticament en ${seconds}s';
  }

  @override
  String get chatAppsProPerkContext => 'L\'Omi recorda el context a totes les aplicacions';

  @override
  String get errorProcessingConversation => 'Error en processar la conversa. Torneu-ho a provar més tard.';

  @override
  String get profileSettings => 'Configuració del perfil';

  @override
  String get statusUnprocessed => 'No processat';

  @override
  String get deleteConversationMessage => 'Això també eliminarà els records, tasques i fitxers d\'àudio associats.';

  @override
  String get cancelSubscriptionQuestion => 'Cancel·lar subscripció?';

  @override
  String get forUnlimitedFreeTranscription => 'per a transcripció gratuïta il·limitada.';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used de $limit min utilitzats';
  }

  @override
  String get categoryPersonalWellness => 'Benestar personal';

  @override
  String get automaticTranslation => 'Traducció automàtica';

  @override
  String get defaultAiAssistant => 'Assistent d\'IA per defecte';

  @override
  String get allDataErased => 'S\'esborraran els teus records i converses.';

  @override
  String entityDue(String date) {
    return 'Venciment: $date';
  }

  @override
  String get feedbackChatWithUs => 'More detail? Chat with us';

  @override
  String get speakerTagPromptSomeoneNew => 'Algú nou';

  @override
  String get inProgress => 'En curs';

  @override
  String get raybanMetaCheckAgain => 'Torna a comprovar';

  @override
  String get fairUseStageNormal => 'Normal';

  @override
  String get pairingTitleLimitless => 'Posa Limitless en mode d\'aparellament';

  @override
  String get usingNativeIosSpeech => 'Utilitzant el reconeixement de veu natiu diOS';

  @override
  String get actionItemDeletedSuccessfully => 'Tasca eliminada correctament';

  @override
  String get failedToSetLanguage => 'No s\'ha pogut establir l\'idioma';

  @override
  String get appHomeUrl => 'URL de la pàgina d\'inici de l\'app';

  @override
  String get appNameLabel => 'Nom de l\'aplicació';

  @override
  String get localStorageDisabled => 'Emmagatzematge local desactivat';

  @override
  String get appReEnable => 'Reactiva';

  @override
  String get migrationFailed => 'La migració ha fallat';

  @override
  String get markComplete => 'Marca com a completat';

  @override
  String get lastUsedLabel => 'Últim ús';

  @override
  String get chatCleared => 'Xat esborrat';

  @override
  String get revokeApiKeyWarning =>
      'Les aplicacions que facin servir aquesta clau perdran l\'accés a l\'API. Això no es pot desfer.';

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return 'Error en comprovar el permís de captura de pantalla: $error';
  }

  @override
  String get troubleshootingSteps =>
      'Resolució de problemes:\n\n1. Assegureu-vos que Omi està instal·lat al vostre rellotge\n2. Obriu l\'aplicació Omi al vostre rellotge\n3. Busqueu la finestra emergent de permisos\n4. Toqueu \"Permetre\" quan se us demani\n5. L\'aplicació al vostre rellotge es tancarà - torneu a obrir-la\n6. Torneu i toqueu \"Continuar\" al vostre iPhone';

  @override
  String get location => 'Ubicació';

  @override
  String get chatAppsWhatsAppMeantime => 'Telegram i iMessage funcionen avui, amb els mateixos records i tasques.';

  @override
  String get sliderOff => 'Apagat';

  @override
  String get checkingFirmwareVersion => 'Comprovant la versió del firmware…';

  @override
  String get reviewUnknownSpeaker => 'Parlant desconegut';

  @override
  String get professionSales => 'Vendes';

  @override
  String get noRssiDataYet => 'Encara no hi ha dades RSSI';

  @override
  String get emptyOldMessage => '✅ No hi ha tasques antigues';

  @override
  String deleteSampleConfirmation(String name) {
    return 'Se suprimirà la mostra de veu de $name. Això no es pot desfer.';
  }

  @override
  String get saveUrlButton => 'Desar URL';

  @override
  String get onboardingNotificationDeniedSystemPrefs =>
      'Permís de notificacions denegat. Si us plau, concediu permís a Preferències del Sistema.';

  @override
  String get languageForTranscription => 'Omi usa aquest idioma per a la transcripció, els resums i els records.';

  @override
  String get updatedLabel => 'ACTUALITZAT';

  @override
  String get content => 'Contingut';

  @override
  String get phoneCallButton => 'Truca';

  @override
  String get exportStartedMayTakeFewSeconds => 'Exportació iniciada. Això pot trigar uns segons…';

  @override
  String dreamReportPrivacyHeld(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count informes retinguts per privacitat',
      one: '1 informe retingut per privacitat',
    );
    return '$_temp0';
  }

  @override
  String firmwareBatteryTooLow(int level) {
    return 'La bateria és al $level%. Carrega el dispositiu com a mínim fins al 15% abans d\'actualitzar.';
  }

  @override
  String get appearance => 'Aparença';

  @override
  String noTasksOnDate(Object date) {
    return 'Cap tasca el $date';
  }

  @override
  String get deleteFlowFeedbackHint => 'Opcional — les teves idees ens ajuden a crear un producte millor.';

  @override
  String get bluetooth => 'Bluetooth';

  @override
  String get cancelUpdate => 'Cancel·la l\'actualització';

  @override
  String get syncStatusConversationCreated => 'Conversa creada';

  @override
  String get reconnecting => 'Reconnectant…';

  @override
  String get tasksToday => 'Avui';

  @override
  String taskCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count tasques',
      one: '1 tasca',
    );
    return '$_temp0';
  }

  @override
  String get noUpcomingMeetings => 'No hi ha reunions properes';

  @override
  String get invalidRecordingMultipleSpeakers => 'S\'ha detectat un enregistrament no vàlid';

  @override
  String get startupFailedTitle => 'L\'Omi no s\'ha pogut iniciar';

  @override
  String contactsSelectedCount(int count) {
    return '$count seleccionats';
  }

  @override
  String get skipForward10Seconds => 'Endavant 10 segons';

  @override
  String get noItems => 'No hi ha elements';

  @override
  String get timeout30Minutes => '30 minuts';

  @override
  String get signInSuccess => 'Inici de sessió correcte!';

  @override
  String get syncStatusDownloadingFromDevice => 'S\'està baixant del teu dispositiu';

  @override
  String get makePrivate => 'Fer privat';

  @override
  String get update => 'Actualitzar';

  @override
  String get aiGenCreatingAppIcon => 'Creant la icona de l\'aplicació…';

  @override
  String get wrappedIntenseDay => 'Intens';

  @override
  String get raybanMetaSkipForNow => 'Omet per ara';

  @override
  String diagnosticsReconnectedIn(String duration) {
    return 'reconnectat en $duration';
  }

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'Estàs canviant el teu Pla Il·limitat al $title.';
  }

  @override
  String get appsAskWith => 'Pregunta a Omi amb';

  @override
  String get noMemoriesFound => 'No s\'han trobat records';

  @override
  String get noMemoriesYet => 'Encara no hi ha records';

  @override
  String get captureRecordingSeparateFailed => 'No s\'ha pogut separar. Torna-ho a provar.';

  @override
  String get pinAsBaseline => 'Fixa com a base';

  @override
  String get voiceRecognitionSettings => 'Reconeixement de veu';

  @override
  String get chatAppsComingLater => 'Aviat';

  @override
  String get sliderMax => 'Màx.';

  @override
  String get deleteWhileProcessingTitle => 'Encara s\'està processant';

  @override
  String get devModeSettingsSaved => 'Configuració desada!';

  @override
  String get fairUseToday => 'Avui';

  @override
  String get exportDataDesc => 'Exportar converses a un fitxer JSON';

  @override
  String get whatsYourName => 'Com et dius?';

  @override
  String get onDeviceSlower => 'La transcripció al dispositiu pot ser més lenta.';

  @override
  String get categoryProductivityLifestyle => 'Productivitat i estil de vida';

  @override
  String get addToYourTaskList => 'Afegir a la llista de tasques?';

  @override
  String get meetingScreenshotFallbackCaption => 'Captura de pantalla d\'aquesta reunió';

  @override
  String get effectCountsALittle => 'Ajuda una mica';

  @override
  String get pairingTitleFriendPendant => 'Posa Friend Pendant en mode d\'aparellament';

  @override
  String get peopleStatsIncomplete => 'Els recomptes poden ser incomplets.';

  @override
  String get tapToAddGoal => 'Toca per afegir un objectiu';

  @override
  String get payment => 'Pagament';

  @override
  String get omiDebugLog => 'Registre de depuració d\'Omi';

  @override
  String get showMeetingsMenuBar => 'Mostrar reunions properes a la barra de menú';

  @override
  String get mostInstalls => 'Més instal·lacions';

  @override
  String chatUsageMessages(String used, String limit) {
    return 'Xat: $used / $limit missatges aquest mes';
  }

  @override
  String get chat => 'Xat';

  @override
  String get areYouThere => 'Hi sou?';

  @override
  String get highestRating => 'Millor valoració';

  @override
  String get pleaseSpecify => 'Si us plau, especifica';

  @override
  String get staging => 'Staging';

  @override
  String get cancelReasonBatteryDrain => 'Preocupacions sobre el consum de bateria';

  @override
  String get apiKeys => 'Claus API';

  @override
  String conversationsCreated(int count) {
    return '$count converses creades';
  }

  @override
  String get trainingDataProgram => 'Programa de dades d\'entrenament';

  @override
  String get customBackendUrlTitle => 'URL del servidor personalitzat';

  @override
  String get omiSyncsAudioFiles => 'Omi després sincronitza els fitxers d\'àudio amb el servidor';

  @override
  String get reviewAnswerMe => 'Jo';

  @override
  String get debugDiagnostics => 'Depuració i diagnòstics';

  @override
  String get confidenceReasonNotHeard => 'encara no s\'ha sentit';

  @override
  String get doubleTapAction => 'Acció de doble toc';

  @override
  String get showTasksOnHomepage => 'Mostra les tasques a la pàgina principal';

  @override
  String failedToStartUpdate(String error) {
    return 'Error en iniciar l\'actualització: $error';
  }

  @override
  String get feedbackReasonSummaryWrongContext => 'Wrong context';

  @override
  String get pleaseProvideValidDescription => 'Si us plau, proporcioneu una descripció vàlida';

  @override
  String get appRejectedNotice =>
      'La teva aplicació ha estat rebutjada. Si us plau, actualitza els detalls de l\'aplicació i torna-la a enviar per a revisió.';

  @override
  String get deleteOnDeviceModel => 'Elimina el model';

  @override
  String get languageSettingsHelperText =>
      'L\'idioma de l\'aplicació canvia els menús i els botons. L\'idioma principal afecta com es transcriuen les teves gravacions.';

  @override
  String get deleteConversationsMessage => 'També s\'eliminaran els seus records, tasques i fitxers d\'àudio.';

  @override
  String get usageBestMonth => 'Best month';

  @override
  String get creating => 'Creant…';

  @override
  String get microphoneAccessDescription =>
      'Omi necessita accés al micròfon per enregistrar les vostres converses i proporcionar transcripcions.';

  @override
  String get cancelReasonNotUsing => 'No l\'utilitzo prou';

  @override
  String get wrappedWeveAllBeenThere => 'Tots hi hem estat!';

  @override
  String get chatAppsProblemRateLimited => 'Massa intents. Espera un minut i torna-ho a provar.';

  @override
  String get selectOption => 'Seleccionar';

  @override
  String get languageBenefits => 'Omi usa aquest idioma per a la transcripció, els resums i els records.';

  @override
  String get triggerConversationIntegration => 'Activar integració de creació de conversa';

  @override
  String get integrationSetupRequired =>
      'Si aquesta és una aplicació d\'integració, assegura\'t que la configuració està completada.';

  @override
  String get clickPlayToResumeOrStop => 'Feu clic a reproducció per reprendre o atura per acabar';

  @override
  String disconnectedFrom(String appName) {
    return 'Desconnectat de $appName';
  }

  @override
  String get subscribe => 'Subscriu-te';

  @override
  String get permissionsChangeAnytime => 'Podeu canviar-ho en qualsevol moment a Configuració > Permisos';

  @override
  String get enableRemindersAccess =>
      'Si us plau, activeu l\'accés als Recordatoris a Configuració per utilitzar els Recordatoris d\'Apple';

  @override
  String get selectProviderTemplate => 'Selecciona una plantilla de proveïdor…';

  @override
  String get initialisingSystemAudio => 'Inicialitzant l\'àudio del sistema';

  @override
  String get excellent => 'Excel·lent';

  @override
  String get chatBlockGoal => 'Objectiu';

  @override
  String get deleteFolder => 'Elimina la carpeta';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'Error en crear la clau: $error';
  }

  @override
  String get whisperModelSizeSmall => 'Petit';

  @override
  String get pleaseCopyKeyNow => 'Si us plau, copia\'l ara i escriu-lo en un lloc segur. ';

  @override
  String get unresolvedSpeakersNotice =>
      'Les etiquetes dels parlants podrien no coincidir entre els enregistraments d\'aquesta conversa.';

  @override
  String get omisMemoryCleared => 'S\'ha esborrat la memòria d\'Omi sobre tu';

  @override
  String get manageApp => 'Gestionar aplicació';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return 'Estat del permís de captura de pantalla: $status. Si us plau, comproveu Preferències del Sistema.';
  }

  @override
  String get edit => 'Edita';

  @override
  String get redownload => 'Tornar a descarregar';

  @override
  String get chatBlockConversation => 'Conversa';

  @override
  String get loadingApps => 'Carregant aplicacions…';

  @override
  String get chatPromptPlaceholder =>
      'Ets una aplicació increïble, la teva feina és respondre a les consultes de l\'usuari i fer que se sentin bé…';

  @override
  String get stripeConnectedAccountAgreement => 'Acord de compte connectat de Stripe';

  @override
  String get autoSync => 'Sincronització automàtica';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'Graf de coneixement eliminat correctament';

  @override
  String get optInAndOptOutOptions => 'Opcions d\'acceptació i rebuig';

  @override
  String get permissionReadMemories => 'Llegir records';

  @override
  String get noSpacesInWorkspace => 'No s\'han trobat espais en aquest espai de treball';

  @override
  String get reviewYesMerge => 'Sí, fusiona';

  @override
  String get voiceMode => 'Mode de veu';

  @override
  String get fairUseStageThrottle => 'Limitat';

  @override
  String get deleteChatQuestion => 'Vols suprimir aquest xat?';

  @override
  String get failedToGetCallToken => 'No s\'ha pogut obtenir el token. Verifica el teu numero primer.';

  @override
  String get selectTime => 'Selecciona hora';

  @override
  String get sdCardProcessing => 'Processament de targeta SD';

  @override
  String errorConnectingRayBanMeta(String error) {
    return 'Error en connectar amb Ray-Ban Meta: $error';
  }

  @override
  String get couldNotLoadImportHistory => 'No s\'ha pogut carregar l\'historial d\'importació';

  @override
  String get noApiKeysFound => 'No s\'han trobat claus API. Creeu-ne una per començar.';

  @override
  String get appDisabledTitle => 'Aquesta app està desactivada i no es pot instal·lar.';

  @override
  String get syncStatusBackedUp => 'Còpia feta';

  @override
  String get speakerTagPromptThatsMeAction => 'Sóc jo';

  @override
  String timeCompactHoursAndMins(int hours, int mins) {
    return '${hours}h ${mins}m';
  }

  @override
  String get chatPrompt => 'Indicació de xat';

  @override
  String get voicePreviewSample => 'Hola, soc l\'Omi. Aquesta és la meva veu.';

  @override
  String get saved => 'Desat';

  @override
  String get grantPermissionButton => 'Atorgar permís';

  @override
  String get subscription => 'Subscripció';

  @override
  String get capabilityFeatured => 'Destacats';

  @override
  String get pdfConversationExport => 'Exportació de conversa';

  @override
  String get unknown => 'Desconegut';

  @override
  String get yourMeetings => 'Les vostres reunions';

  @override
  String get uploadingVoiceProfile => 'Pujant el teu perfil de veu….';

  @override
  String get apiUrl => 'URL de l\'API';

  @override
  String get reportMessage => 'Informar del missatge';

  @override
  String get passwordLabel => 'Contrasenya';

  @override
  String get permanentlyRemoveAllMemories => 'Eliminar permanentment tots els records d\'Omi';

  @override
  String get transcriptionSlowerLessAccurate => 'La transcripció serà significativament més lenta i menys precisa.';

  @override
  String get filterManual => 'Manual';

  @override
  String get keepMyPlan => 'Conservar el meu pla';

  @override
  String get setupQuestionAge => '3. Quin és el teu rang d\'edat?';

  @override
  String get addAppSelectTriggerEvent => 'Seleccioneu un esdeveniment activador per a la vostra aplicació';

  @override
  String get defaultWorkspace => 'Espai de treball per defecte';

  @override
  String get errorUpdatingAppStatus => 'S\'ha produït un error en actualitzar l\'estat de l\'aplicació.';

  @override
  String get invalidJsonConfig => 'Configuració JSON no vàlida';

  @override
  String get detailedDiagnosticMessages => 'Missatges de diagnòstic detallats';

  @override
  String get mergingInBackground => 'Fusionant en segon pla. Això pot trigar una mica.';

  @override
  String get setDefaultApp => 'Establir aplicació predeterminada';

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Haureu d\'autoritzar Omi per crear tasques al vostre compte de $appName. Això obrirà el vostre navegador per a l\'autenticació.';
  }

  @override
  String get cleanUpEllipsis => 'Neteja…';

  @override
  String get addTask => 'Afegir tasca';

  @override
  String get getCreative => 'Sigues creatiu';

  @override
  String get captureRecordingOpenFailed => 'No s\'ha pogut obrir aquest enregistrament.';

  @override
  String get emptyTodoMessage => '🎉 Tot al dia!\nNo hi ha tasques pendents';

  @override
  String get onboardingSetupTitle => 'Configurant el teu Omi';

  @override
  String get sharePeriodAllTime => 'Fins ara, Omi ha:';

  @override
  String get translationNotice => 'Avís de traducció';

  @override
  String captureRecordingError(String error) {
    return 'S\'ha produït un error durant l\'enregistrament: $error';
  }

  @override
  String get downloadAudio => 'Descarregar àudio';

  @override
  String get identifySpeaker => 'Identifica el parlant';

  @override
  String get viewTranscript => 'Veure transcripció';

  @override
  String get makeAllMemoriesPublic => 'Fer públics tots els records';

  @override
  String get xTwitter => 'X (Twitter)';

  @override
  String get frequencyOff => 'Desactivat';

  @override
  String get apiEnvironment => 'Entorn de l\'API';

  @override
  String get processingTakingLonger => 'Encara en curs: això està trigant més del normal.';

  @override
  String get firmwareUpdateFailedTitle => 'L\'actualització ha fallat';

  @override
  String get unresolvedQuestions => 'Preguntes no resoltes';

  @override
  String get chatAppsMessage => 'Missatge';

  @override
  String get dreamReportManual => 'Manual';

  @override
  String get enterSttHttpEndpoint => 'Introduïu el vostre punt final HTTP STT';

  @override
  String get beforeUpdateMakeSure => 'Abans d\'actualitzar, assegura\'t:';

  @override
  String get transcriptionReconnecting => 'Reconnectant la transcripció…';

  @override
  String get deviceName => 'Nom del dispositiu';

  @override
  String neoSubtitle(int count) {
    return '$count preguntes al mes';
  }

  @override
  String chatUsageProgress(String used, String limit) {
    return '$used / $limit utilitzats';
  }

  @override
  String get noChangesInReview => 'No hi ha canvis a la ressenya per actualitzar.';

  @override
  String get allMemories => 'Tots els records';

  @override
  String get needMicrophonePermission =>
      'Necessitem permís del micròfon.\n\n1. Toqueu \"Atorgar permís\"\n2. Permeteu al vostre iPhone\n3. L\'aplicació del rellotge es tancarà\n4. Torneu a obrir-la i toqueu \"Continuar\"';

  @override
  String get keepSpeakingUntil100 => 'Continua parlant fins arribar al 100%.';

  @override
  String get singleLanguageModeInfo =>
      'El mode d\'idioma únic està activat. La traducció està desactivada per a una major precisió.';

  @override
  String get thisCannotBeUndone => 'Això no es pot desfer.';

  @override
  String get setupSkipHelp => 'Ometre, no vull ajudar :C';

  @override
  String get speakerTagPromptNoAction => 'No…';

  @override
  String labelCopied(String label) {
    return '$label copiat';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'Error en canviar el dispositiu d\'àudio: $error';
  }

  @override
  String get remembering => 'Recordant';

  @override
  String get externalAppAccessDescription =>
      'Les següents aplicacions instal·lades tenen integracions externes i poden accedir a les teves dades, com ara converses i records.';

  @override
  String get preferences => 'Preferències';

  @override
  String get wrappedFunDay => 'Divertit';

  @override
  String get effectNeeded => 'Necessari per a Confirmat';

  @override
  String get importantConversationBody => 'Acabes de tenir una conversa important. Toca per compartir el resum.';

  @override
  String whyConfidenceMenu(String level) {
    return 'Per què $level?';
  }

  @override
  String get cmdRequired => '⌘ necessari';

  @override
  String get completed => 'Completat';

  @override
  String get deviceOnboardingVoiceReplyStatusAlwaysSpeaker =>
      'Es reprodueix en veu alta a través de l\'altaveu del telèfon.';

  @override
  String get effectCountsAgainst => 'Perjudica';

  @override
  String get recaps => 'Resums';

  @override
  String get shareConversationQuestion => 'Vols compartir la conversa?';

  @override
  String get actionItemsCopiedToClipboard => 'Tasques copiades al porta-retalls';

  @override
  String get appleHealthManageNote =>
      'Omi accedeix a Apple Health a través del framework HealthKit d\'Apple. Pots revocar l\'accés en qualsevol moment a la configuració d\'iOS.';

  @override
  String addingToService(String serviceName) {
    return 'Afegint a $serviceName…';
  }

  @override
  String get needHelpGettingStarted => 'Necessites ajuda per començar?';

  @override
  String get thanksForAuthorizing => 'Gràcies per autoritzar!';

  @override
  String get assistantVoiceSettingsTitle => 'Veu';

  @override
  String get cloudStorageDisabled => 'Emmagatzematge al núvol desactivat';

  @override
  String get reviewPlayClip => 'Reprodueix el clip';

  @override
  String get storeAudioOnCloud => 'Emmagatzemar àudio al núvol';

  @override
  String get syncStatusBackingUp => 'Sincronitzant…';

  @override
  String get peopleFilterPinned => 'Fixades';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName establerta com a aplicació de resum predeterminada';
  }

  @override
  String get githubRepositoryUrlRequired => 'Cal la URL del repositori de GitHub';

  @override
  String get microphoneAccess => 'Accés al micròfon';

  @override
  String get cancelSubscriptionButton => 'Cancel·lar subscripció';

  @override
  String get signal => 'Senyal';

  @override
  String get failedToConnectAsanaRetry => 'No s\'ha pogut connectar a Asana. Si us plau, torna-ho a provar.';

  @override
  String get keyCreatedMessage =>
      'La teva nova clau ha estat creada. Si us plau, copia-la ara. No la podràs veure de nou.';

  @override
  String autoRemoveSyncedCopiesDays(int days) {
    return 'Les còpies sincronitzades s\'eliminen després de $days dies';
  }

  @override
  String get wrappedMostCringeMoment => 'Més vergonyós';

  @override
  String get activity => 'Activitat';

  @override
  String get calendarSettings => 'Configuració del calendari';

  @override
  String get additionalFeedbackOptional => 'Comentaris addicionals (opcional)';

  @override
  String get phoneAllow => 'Permetre';

  @override
  String get noDeviceConnectedUseMic => 'Cap dispositiu connectat. S\'utilitzarà el micròfon del telèfon.';

  @override
  String get stripeOnboardingInstructions =>
      'Si us plau, completeu el procés d\'incorporació de Stripe al vostre navegador. Aquesta pàgina s\'actualitzarà automàticament un cop completat.';

  @override
  String availableSpaceWithValue(String space) {
    return 'Espai disponible: $space';
  }

  @override
  String get conversationDetails => 'Detalls de la conversa';

  @override
  String get wrappedYouHadFunnyMoments => 'Has tingut moments divertits aquest any!';

  @override
  String get actionReadConversations => 'Llegir converses';

  @override
  String speakerTagPromptIsThisPerson(String name) {
    return 'És $name?';
  }

  @override
  String get openSettings => 'Obrir configuració';

  @override
  String get alwaysAvailable => 'sempre disponible.';

  @override
  String get rating1PlusStars => '1+ estrelles';

  @override
  String get pauseResume => 'Pausar/Reprendre';

  @override
  String get conversationDeleted => 'Conversa suprimida';

  @override
  String get memoryReviewRight => 'Correcte';

  @override
  String get deleteGoal => 'Eliminar objectiu';

  @override
  String get youtube => 'YouTube';

  @override
  String get untitledConversation => 'Conversa sense títol';

  @override
  String get yourOmiInsights => 'Les vostres estadístiques d\'Omi';

  @override
  String get compareTranscripts => 'Comparar transcripcions';

  @override
  String get pause => 'Pausa';

  @override
  String get successfullyConnectedGoogle => 'Connectat correctament a Google!';

  @override
  String planRenewsOn(String date) {
    return 'El teu pla es renova el $date.';
  }

  @override
  String chatAppsOpenApp(String app) {
    return 'Obre $app';
  }

  @override
  String get dailySummaryDescription => 'Rep un resum personalitzat de les converses del dia com a notificació.';

  @override
  String conversationPhotosCount(int count) {
    return '$count fotos';
  }

  @override
  String get errorLoadingAudio => 'Error en carregar l\'àudio';

  @override
  String get couldNotAccessFile => 'No s\'ha pogut accedir al fitxer seleccionat';

  @override
  String deleteGraphFailed(String error) {
    return 'No s\'ha pogut eliminar el graf: $error';
  }

  @override
  String get reviewOpenDetailsHint => 'Obre els detalls';

  @override
  String get conversationTimeoutDesc =>
      'Trieu quant temps esperar en silenci abans de finalitzar automàticament una conversa:';

  @override
  String get transcriptionJsonPlaceholder => 'Enganxa la teva configuració JSON aquí…';

  @override
  String get loadingCapabilities => 'Carregant capacitats…';

  @override
  String get activeStatus => 'Actiu';

  @override
  String get noDailyRecapsYet => 'Encara no hi ha resums diaris';

  @override
  String get wouldLikePermission =>
      'Ens agradaria el vostre permís per desar els vostres enregistraments de veu. Aquesta és la raó:';

  @override
  String get chatBlockRecommendedNextSteps => 'Propers passos recomanats';

  @override
  String get tryAdjustingSearchTerms => 'Prova d\'ajustar els termes de cerca';

  @override
  String get connectOmiWithAI => 'Connecta Omi amb assistents d\'IA';

  @override
  String get whenToReceiveDailySummary => 'Quan rebre el teu resum diari';

  @override
  String syncCardReadyCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count enregistraments a punt per sincronitzar',
      one: '1 enregistrament a punt per sincronitzar',
    );
    return '$_temp0';
  }

  @override
  String get yourApiKey => 'LA TEVA CLAU API';

  @override
  String failedToLoadRepos(String error) {
    return 'No s\'han pogut carregar els repositoris: $error';
  }

  @override
  String get syncingMessages => 'Sincronitzant missatges amb el servidor…';

  @override
  String get pleaseSelectARating => 'Si us plau, selecciona una valoració';

  @override
  String get suggestedTemplates => 'Plantilles suggerides';

  @override
  String get updateAppQuestion => 'Actualitzar l\'aplicació?';

  @override
  String get frequencyDescOff => 'Sense notificacions proactives';

  @override
  String get triggerAudioBytes => 'Bytes d\'àudio';

  @override
  String get confirmClearChat => 'Vols esborrar aquest xat? Això no es pot desfer.';

  @override
  String get dataPrivacy => 'Privadesa de Dades';

  @override
  String get audioFromOmiWillAppearHere => 'L\'àudio del teu dispositiu Omi apareixerà aquí';

  @override
  String get durationLabel => 'Durada';

  @override
  String get deviceOnboardingAllSetTitle => 'Ja ho tens tot a punt';

  @override
  String msgSelectImagesError(String error) {
    return 'Error en seleccionar imatges: $error';
  }

  @override
  String evidenceCardPicks(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Triat en $count suggeriments',
      one: 'Triat en 1 suggeriment',
    );
    return '$_temp0';
  }

  @override
  String get connectionLostDesc =>
      'La connexió s\'ha interromput. Comproveu la vostra connexió a internet i torneu-ho a provar.';

  @override
  String get defaultLabel => 'Predeterminada';

  @override
  String get raybanMetaAllowCamera => 'Permet la càmera de les ulleres';

  @override
  String get addAppSelectCoreCapability => 'Seleccioneu una capacitat principal més per a la vostra aplicació';

  @override
  String get noManualMemories => 'Encara no hi ha records manuals';

  @override
  String get deliveryTime => 'Hora de lliurament';

  @override
  String get defaultProjectOptional => 'Projecte per defecte (opcional)';

  @override
  String get devModeInvalidAudioBytesWebhookUrl => 'URL del webhook de bytes d\'àudio no vàlida';

  @override
  String get ignoredVoicesTitle => 'Veus ignorades';

  @override
  String get refreshManifest => 'Actualitza el manifest';

  @override
  String get diagnosticsRightNow => 'Ara mateix';

  @override
  String get reviewDue => 'Venciment';

  @override
  String get unmute => 'Activar so';

  @override
  String get recordingsDeleted => 'Enregistraments eliminats.';

  @override
  String get failedToDeleteFolder => 'No s\'ha pogut eliminar la carpeta';

  @override
  String get reviewAnswerOther => 'Altre';

  @override
  String get exportedConversations => 'Converses exportades d\'Omi';

  @override
  String get privacyPolicy => 'Política de privadesa';

  @override
  String get editReply => 'Edita la resposta';

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription i és $triggerDescription.';
  }

  @override
  String errorSaving(String error) {
    return 'Error en desar: $error';
  }

  @override
  String get diagnosticsConnectedFor => 'Connectat durant';

  @override
  String get callStateConnecting => 'Connectant…';

  @override
  String get conversationUrlNotShared => 'No s\'ha pogut compartir l\'URL de la conversa.';

  @override
  String get tooShortDesc => 'No s\'ha detectat prou veu. Parleu més i torneu-ho a provar.';

  @override
  String get failedToShareRecap => 'No s\'ha pogut compartir el resum';

  @override
  String get billingMonthly => 'Mensual';

  @override
  String get developingLogic => 'Desenvolupant lògica';

  @override
  String get phoneContinue => 'Continuar';

  @override
  String get successfullyConnectedGitHub => 'Connectat correctament a GitHub!';

  @override
  String get failedToSubmitReview => 'Error en enviar la ressenya. Si us plau, torna-ho a provar.';

  @override
  String get anyoneCanDiscover => 'Qualsevol pot descobrir la vostra aplicació';

  @override
  String get v2Undetected => 'V2 no detectat';

  @override
  String get usageIrlEvents => 'Esdeveniments presencials';

  @override
  String get conversationPromptHint =>
      'p. ex., Extreu tasques, decisions preses i punts clau de la conversa proporcionada.';

  @override
  String get openProviderDocs => 'Obre la documentació';

  @override
  String get showMeetingsInMenuBar => 'Mostra Reunions a la Barra de Menú';

  @override
  String get viewPlansAndUsage => 'Veure Plans i Ús';

  @override
  String get buildSubmitCustomOmiApp => 'Construeix i envia la teva aplicació Omi personalitzada';

  @override
  String get failedToRefreshGoogleStatus => 'No s\'ha pogut actualitzar l\'estat de connexió de Google.';

  @override
  String get feedbackSubtitleTooExpensive => 'Els teus comentaris ens ajuden a trobar l\'equilibri correcte.';

  @override
  String get startUsingOmi => 'Comença a utilitzar Omi';

  @override
  String get dreamReportLearnedWords => 'Paraules que ha après';

  @override
  String get actionItemCreated => 'Tasca creada';

  @override
  String get exportAllConversationsToJson => 'Exporteu totes les vostres converses a un fitxer JSON.';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain =>
      'Si us plau, comprova la connexió a Internet i torna-ho a provar';

  @override
  String get callStateEnded => 'Trucada finalitzada';

  @override
  String get phoneNumberHint => 'Numero de telefon';

  @override
  String get tasksGroupByProject => 'Agrupa per projecte';

  @override
  String get phoneCallsUnlimitedOnly => 'Trucades telefòniques via Omi';

  @override
  String get frequencyDescMinimal => 'Només coses urgents, unes 1–3 al dia';

  @override
  String get changeYourName => 'Canvia el vostre nom';

  @override
  String get editYourReply => 'Editar resposta';

  @override
  String get publicMemories => 'Records públics';

  @override
  String get monthDec => 'Des';

  @override
  String get reviewNewPersonName => 'El seu nom';

  @override
  String get googleCalendarConnectPrompt =>
      'Connecta el teu Google Calendar per vincular converses a esdeveniments del calendari.';

  @override
  String get realtimeAudioBytes => 'Bytes d\'àudio en temps real';

  @override
  String get trackYourGoalsOnHomepage => 'Fes seguiment dels teus objectius personals a la pàgina d\'inici';

  @override
  String get chatAddAttachment => 'Afegeix un fitxer adjunt';

  @override
  String get beta => 'BETA';

  @override
  String get createMemory => 'Crear memòria';

  @override
  String get permissionsRequiredDescription =>
      'Omi necessita alguns permisos per funcionar correctament. Si us plau, concediu-los per continuar.';

  @override
  String get dataCollectionMessage =>
      'En continuar, les teves converses, enregistraments i informació personal s\'emmagatzemaran de manera segura als nostres servidors per proporcionar informació impulsada per IA i habilitar totes les funcions de l\'aplicació.';

  @override
  String get batteryLevel => 'Nivell de bateria';

  @override
  String get searchCountries => 'Cercar països...';

  @override
  String get confidenceSheetTitle => 'Confiança';

  @override
  String get deviceModelLabel => 'Model del dispositiu';

  @override
  String get noStableFirmwareFound => 'No s\'ha pogut trobar una versió estable del firmware per al vostre dispositiu.';

  @override
  String get noResultsFound => 'No s\'han trobat resultats';

  @override
  String get wrappedMins => 'min';

  @override
  String get chatAppsTelegramSubtitle => 'Es configura en dos tocs';

  @override
  String get categoryConversationAnalysis => 'Anàlisi de converses';

  @override
  String get target => 'Objectiu';

  @override
  String get apiKeyRequired => 'Cal una clau API';

  @override
  String otaUpdatedMessage(String deviceName) {
    return '$deviceName s\'ha actualitzat i es reiniciarà sol.';
  }

  @override
  String get reconnections => 'Reconnexions';

  @override
  String errorCheckingConnection(String error) {
    return 'Error en comprovar la connexió: $error';
  }

  @override
  String get usageMonth => 'Aquest mes';

  @override
  String get additionalSpeechSampleRemoved => 'S\'ha eliminat la mostra de veu addicional';

  @override
  String get speakerTagPromptExcerptSaved => 'Resposta desada per a aquest fragment.';

  @override
  String get omisStorage => 'Emmagatzematge d\'Omi';

  @override
  String get recordingAndTranscription => 'Enregistrament i transcripció';

  @override
  String get categoryCommunication => 'Comunicació';

  @override
  String get wrappedYouDidIt => 'Ho has aconseguit! 🎉';

  @override
  String get failedToDeleteItems => 'No s\'han pogut eliminar els elements';

  @override
  String speakerLabelLinesLabeled(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'S\'han etiquetat $count línies',
      one: 'S\'ha etiquetat 1 línia',
    );
    return '$_temp0';
  }

  @override
  String get generatingLink => 'Generant enllaç…';

  @override
  String get clickHereForAppBuildingGuides => 'Fes clic aquí per a guies de creació d\'aplicacions i documentació';

  @override
  String get authUrl => 'URL d\'autenticació';

  @override
  String get addAppCapabilityConflictWithPersona => 'No es poden seleccionar altres capacitats amb Persona';

  @override
  String get deviceOnboardingVoiceReplyGenericHeadphones => 'Auriculars';

  @override
  String get clearAll => 'Esborrar tot';

  @override
  String get noKnowledgeGraphYet => 'Encara no hi ha graf de coneixement';

  @override
  String get messageReportedSuccessfully => '✅ Missatge informat correctament';

  @override
  String get paymentFailedToSetDefault =>
      'Error en establir el mètode de pagament predeterminat. Torneu-ho a provar més tard.';

  @override
  String get memoryReviewUpdated => 'Actualitzat.';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'El vostre pla es cancel·larà el $date.';
  }

  @override
  String get welcomeToOmi => 'Benvingut a Omi';

  @override
  String get phoneFreeCallLimitReached =>
      'S\'ha arribat al límit mensual de trucades gratuïtes. Es restableix el mes vinent.';

  @override
  String get omiTranscriptionOptimized =>
      'La transcripció en directe d\'Omi està pensada per a converses en temps real i indica qui ha dit què.';

  @override
  String get chatAppsLoadFailedTitle => 'No s\'han pogut carregar les aplicacions de xat';

  @override
  String get continueWithGoogle => 'Continua amb Google';

  @override
  String get setupSteps => 'Passos de configuració';

  @override
  String totalMemoriesCount(int count) {
    return 'Teniu $count records en total';
  }

  @override
  String get feedbackSubtitleBatteryDrain => 'Això ajuda el nostre equip de maquinari a millorar.';

  @override
  String get tryIt => 'Provar-ho';

  @override
  String get chatAppsInsights => 'Idees de l\'Omi';

  @override
  String nFiles(int count) {
    return '$count enregistraments';
  }

  @override
  String get clearChatTitle => 'Esborrar el xat?';

  @override
  String get onlyYouCanUseTemplate => 'Només vós podeu utilitzar aquesta plantilla';

  @override
  String get raybanMetaCameraExplanation =>
      'Omi utilitza la càmera de les vostres ulleres per afegir fotos a les vostres converses. Podeu ometre-ho i utilitzar només àudio.';

  @override
  String get deviceDiagnosticsTicket => 'Support ticket code';

  @override
  String get capabilityTasks => 'Tasques';

  @override
  String get copyUrl => 'Copia l\'URL';

  @override
  String keepItemPublic(String item) {
    return 'Mantenir $item públic';
  }

  @override
  String get chatStarterTeachMe => 'Em pots ensenyar alguna cosa nova?';

  @override
  String get cancelReasonDetailHint => 'Agraïm qualsevol comentari…';

  @override
  String get checkConnectionTryAgain => 'Comprova la connexió i torna-ho a provar.';

  @override
  String get backToConversations => 'Tornar a Converses';

  @override
  String get merge => 'Fusionar';

  @override
  String get couldNotLaunchUpgradePage =>
      'No s\'ha pogut obrir la pàgina d\'actualització. Si us plau, torna-ho a provar.';

  @override
  String get deviceOnboardingTranscriptionSubtitle => 'Digues unes paraules i mira com apareixen en temps real';

  @override
  String get deleteOnDeviceModelConfirm => 'Vols eliminar aquest model?';

  @override
  String get reviewQuestionSpeaker => 'Qui ha dit això?';

  @override
  String updatedDate(String date) {
    return 'Actualitzat $date';
  }

  @override
  String get saveSettings => 'Desa la Configuració';

  @override
  String get alreadyGavePermission =>
      'Ja ens heu donat permís per desar els vostres enregistraments. Aquí teniu un recordatori de per què ho necessitem:';

  @override
  String get appCreatedAndInstalled => 'Aplicació creada i instal·lada!';

  @override
  String get failedToRefreshNotionStatus => 'No s\'ha pogut actualitzar l\'estat de connexió de Notion.';

  @override
  String get deviceOnboardingProcessingQuestion => 'S\'està processant la pregunta…';

  @override
  String get chatBlockTask => 'Tasca';

  @override
  String get pendantNotConnected => 'Penjoll no connectat. Connecteu-lo per sincronitzar.';

  @override
  String get createActionItem => 'Crear tasca';

  @override
  String get logsCopied => 'Registres copiats';

  @override
  String get timeout5MinutesDesc => 'Finalitzar conversa després de 5 minuts de silenci';

  @override
  String get msgUploadFileFailed => 'No s\'ha pogut pujar el fitxer, si us plau torneu-ho a provar més tard';

  @override
  String get reportMessageConfirm => 'Vols denunciar aquest missatge?';

  @override
  String deletePersonConfirmation(String name) {
    return 'Això elimina les mostres de veu de $name i no es pot desfer. Les seves intervencions en converses anteriors passen a ser parlants sense nom.';
  }

  @override
  String get weekdayTue => 'Dt';

  @override
  String get liveTranscript => 'Transcripció en directe';

  @override
  String timeDaysAndHours(int days, int hours) {
    return '$days dies $hours hores';
  }

  @override
  String versionLabel(String version) {
    return 'Versió $version';
  }

  @override
  String get cancelConsequenceDelay => 'Retard de processament de 5-7 segons (models al dispositiu)';

  @override
  String captureRecordingSeparateMessage(String recording) {
    return '$recording es mostrarà com una conversa pròpia i no es tornarà a agrupar amb aquest esdeveniment.';
  }

  @override
  String get updateAvailableTitle => 'Actualització disponible';

  @override
  String get dreamReportShadowBanner =>
      'Mode de vista prèvia: Dream mostra què canviaria, però encara no es modifica res al teu compte.';

  @override
  String get sharedTasksAcceptFailed =>
      'No s\'han pogut acceptar aquestes tasques. Potser ja has acceptat aquesta compartició.';

  @override
  String get appPricingLabel => 'Preu de l\'aplicació';

  @override
  String get reDownload => 'Tornar a descarregar';

  @override
  String get recordWithPhoneMic => 'Grava amb el micròfon del telèfon';

  @override
  String appDisabledOn(String date) {
    return 'Desactivada el $date.';
  }

  @override
  String get play => 'Reprodueix';

  @override
  String get private => 'Privat';

  @override
  String get speakerTagPromptNotSureAction => 'No ho sé';

  @override
  String get showDiscardedConversationsDesc => 'Incloure converses marcades com a descartades';

  @override
  String get captureModeLiveDescription => 'Transcriu en temps real mentre parles.';

  @override
  String get subscriptionCancelledSuccessfully =>
      'Subscripció cancel·lada amb èxit. Romandrà activa fins al final del període de facturació actual.';

  @override
  String get tapToSetAGoal => 'Toca per establir un objectiu';

  @override
  String get tellUsMoreWhatWentWrong => 'Explica\'ns més sobre què va anar malament…';

  @override
  String get downgradeToFreemiumTitle => 'Vols baixar al pla gratuït?';

  @override
  String get usageTasks => 'Tasques';

  @override
  String get chatReplyOffline => 'No s\'ha pogut connectar. Comprova la connexió i torna-ho a provar.';

  @override
  String get makePublic => 'Fer públic';

  @override
  String get authUnexpectedErrorFirebase =>
      'Error inesperat en iniciar sessió, error de Firebase, si us plau torneu-ho a provar.';

  @override
  String get unlimitedConversations => 'Converses il·limitades';

  @override
  String get stagingDisclaimer =>
      'L\'entorn de staging pot ser inestable, tenir un rendiment inconsistent i es poden perdre dades. Utilitza\'l només per a proves.';

  @override
  String get captureMicrophonePermissionRequired => 'Es requereix permís de micròfon';

  @override
  String shareStatsInsights(String count) {
    return '✨ Proporcionat $count informacions';
  }

  @override
  String get feedbackReasonSummaryIrrelevant => 'Not relevant';

  @override
  String get userIdCopiedToClipboard => 'ID d\'usuari copiat';

  @override
  String get urlCopiedToClipboard => 'URL copiat al porta-retalls';

  @override
  String annualBillingSummary(int months, String price) {
    return '$months mesos / $price';
  }

  @override
  String chatAppsShowInAppOff(String app) {
    return 'Desactivat: només els veus a $app.';
  }

  @override
  String get replySentSuccessfully => 'Resposta enviada correctament';

  @override
  String get deviceOnboardingTurnOffTitle => 'Apaga';

  @override
  String get phoneStorageDesc =>
      'Quan l\'Omi es reconnecta, els enregistraments es transfereixen automàticament al telèfon com a àrea temporal abans de pujar-los.';

  @override
  String get callRecordingConsentDisclaimer =>
      'La gravacio de trucades pot requerir consentiment a la teva jurisdiccio';

  @override
  String get showDiscardedConversations => 'Mostrar converses descartades';

  @override
  String get calendarIntegration => 'Integració de Calendari';

  @override
  String get whisperModelSizeBase => 'Base';

  @override
  String get shareViaSms => 'Comparteix via SMS';

  @override
  String get nameMustBeAtLeast3Characters => 'El nom ha de tenir almenys 3 caràcters';

  @override
  String get chatDiscardRecording => 'Descarta';

  @override
  String get chatAppsProPerkText => 'Escriu a l\'Omi des de Telegram i iMessage';

  @override
  String get readyToSync => 'Llest per sincronitzar';

  @override
  String get noAppsInCategoryYet => 'Encara no hi ha apps en aquesta categoria';

  @override
  String get firmwareUpdateAvailable => 'Actualització de firmware disponible';

  @override
  String get modelNumber => 'Número de model';

  @override
  String get sortBy => 'Ordenar';

  @override
  String get slideToUpdate => 'Llisca per actualitzar';

  @override
  String get effectBarelyCounts => 'Gairebé no ajuda';

  @override
  String get onlyYouCanUse => 'Només vós podeu utilitzar aquesta aplicació';

  @override
  String get triggersWhenNewConversationCreated => 'S\'activa quan es crea una conversa nova.';

  @override
  String get paymentPlan => 'Pla de pagament';

  @override
  String get whisperModelDesc => 'Tria el model per a la transcripció al dispositiu';

  @override
  String get askSuggestOwe => 'Què encara dec a la gent?';

  @override
  String get starConversation => 'Destacar conversa';

  @override
  String get hardwareSection => 'Maquinari';

  @override
  String get transcribing => 'Transcrivint…';

  @override
  String get chatAppsVoiceNotesSubtitle => 'Envia una nota de veu i l\'Omi et respondrà.';

  @override
  String confidenceNextVoice(String name) {
    return 'Omi també necessita una mostra de veu de $name. Etiqueta aquesta persona amb «Recorda les veus» activat.';
  }

  @override
  String get rating3PlusStars => '3+ estrelles';

  @override
  String get recordingActive => 'Gravació activa';

  @override
  String starFilter(int count) {
    return '$count Estrella';
  }

  @override
  String get storageLocationLabel => 'Ubicació d\'emmagatzematge';

  @override
  String get reviewNoChangesBody => 'Quan Omi endreci les teves notes, els canvis apareixeran aquí.';

  @override
  String get testPrompt => 'Provar indicació';

  @override
  String get otaUpdateUnavailable => 'Aquesta actualització no està disponible ara. Torna-ho a provar més tard.';

  @override
  String get downloading => 'Descarregant…';

  @override
  String get welcomeBackSimple => 'Benvingut de nou';

  @override
  String get sttProviderSoniox => 'Soniox';

  @override
  String get clearAllSelection => 'Esborra tot';

  @override
  String get confidenceReasonNeverConfirmed => 'Mai confirmat';

  @override
  String get writeScope => 'Escriptura';

  @override
  String get evidenceVoiceReady => 'Mostra de veu a punt';

  @override
  String get updateApp => 'Actualitzar aplicació';

  @override
  String get weekdayThu => 'Dj';

  @override
  String chatUsageCostNoLimit(String used) {
    return 'Xat: \$$used utilitzat aquest mes';
  }

  @override
  String get configCopied => 'Configuració copiada al porta-retalls';

  @override
  String get startupFailedConfigMessage =>
      'Aquesta versió de l\'Omi té un problema de configuració. No és un problema del teu dispositiu. Contacta amb el suport i inclou els detalls següents.';

  @override
  String get getOmiForMac => 'Obtenir Omi per a Mac';

  @override
  String get appleHealthConnectedBadge => 'Connectat';

  @override
  String get msgCameraNotAvailable => 'La captura de càmera no està disponible en aquesta plataforma';

  @override
  String get actionItemsDescription => 'Toqueu per editar • Manteniu per seleccionar • Llisqueu per a accions';

  @override
  String get notificationsDesc =>
      'Perquè l\'Omi et pugui enviar resums de converses, recordatoris de tasques i respostes de les teves apps.';

  @override
  String audioUploadRetrying(String duration) {
    return 'Tornant a provar la pujada… s\'han conservat $duration d\'àudio al telèfon';
  }

  @override
  String get importStarted => 'Importació iniciada! Se us notificarà quan estigui completa.';

  @override
  String get onDeviceModelDownloadFailed => 'No s\'ha pogut descarregar el model';

  @override
  String get noProjectsInWorkspace => 'No s\'han trobat projectes en aquest espai de treball';

  @override
  String get helpCenter => 'Centre d\'ajuda';

  @override
  String get trainingDataBullets =>
      '• Les teves dades ajuden a millorar els models d\'IA\n• Només es comparteixen dades no sensibles';

  @override
  String get invalidPromotionCode => 'Codi promocional no vàlid.';

  @override
  String get battery => 'Bateria';

  @override
  String get clearSelection => 'Esborrar selecció';

  @override
  String get phoneSetupStep2Subtitle => 'Un codi curt que escriuras a la trucada';

  @override
  String get googleSearch => 'Google Search';

  @override
  String get charging => 'Carregant';

  @override
  String deleteNamedPerson(String name) {
    return 'Elimina $name';
  }

  @override
  String get chatAppsPartOfPro => 'Les aplicacions de xat formen part de Pro';

  @override
  String get invalidWebhookUrlError => 'Introdueix una URL de webhook vàlida';

  @override
  String get starConversationsToFindQuickly => 'Destaca converses per trobar-les ràpidament aquí';

  @override
  String get permissionCreateMemories => 'Crear records';

  @override
  String get conversationIdCopied => 'ID de la conversa copiat al porta-retalls';

  @override
  String get chatAppsMessagesApp => 'Missatges';

  @override
  String get understandingWords => 'Entenent (paraules)';

  @override
  String diagnosticsVerdictTroubleDetail(int count) {
    return 'Connexions fallides en les últimes 24 hores: $count';
  }

  @override
  String get editName => 'Editar nom';

  @override
  String get askAboutThisConversation => 'Pregunta sobre això';

  @override
  String get useTemplateFrom => 'Utilitzar plantilla de';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'Estat del permís de micròfon: $status. Si us plau, comproveu Preferències del Sistema.';
  }

  @override
  String get markAsCompleted => 'Marcar com a completada';

  @override
  String get urlMustEndWithSlashError => 'L\'URL ha d\'acabar amb \"/\"';

  @override
  String get deviceOnboardingIntroTitle => 'Coneix el teu Omi';

  @override
  String nPending(int count) {
    return '$count pendents';
  }

  @override
  String get howShouldOmiCallYou => 'Com hauria d\'anomenar-vos Omi?';

  @override
  String get preparingFormForYou => 'Preparant el formulari per a tu…';

  @override
  String get deleteChat => 'Suprimeix el xat';

  @override
  String get msgPhotosPermissionDenied =>
      'Permís de fotos denegat. Si us plau, permeteu l\'accés a les fotos per seleccionar imatges';

  @override
  String get moreWaysToRecord => 'Més maneres de gravar';

  @override
  String get creatingPlan => 'Creant pla';

  @override
  String get configCopiedToClipboard => 'Configuració copiada al porta-retalls';

  @override
  String get transcribeLaterDescription =>
      'Grava ara i transcriu quan vulguis. Fins aleshores, l\'àudio es queda al telèfon.';

  @override
  String get couldNotSwitchToFreePlan => 'No s\'ha pogut canviar al pla gratuït. Si us plau, torna-ho a provar.';

  @override
  String get wrappedTasksCompleted => 'tasques completades';

  @override
  String get deviceOnboardingTranscriptionTitle => 'Parla a l\'Omi';

  @override
  String get thankYouRequestUnderReview =>
      'Gràcies! La teva sol·licitud està en revisió. T\'avisarem quan sigui aprovada.';

  @override
  String get unpairAndForgetDevice => 'Desvincula i oblida el dispositiu';

  @override
  String get sendWebUrl => 'Enviar URL web';

  @override
  String get noTasksForToday => 'No hi ha tasques per avui.\nDemana a Omi més tasques o crea-les manualment.';

  @override
  String get conversationSummaryFailed => 'No s\'ha pogut crear el resum';

  @override
  String get realtimeTranscript => 'Transcripció en temps real';

  @override
  String nConversationsCreated(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count converses creades',
      one: '1 conversa creada',
    );
    return '$_temp0';
  }

  @override
  String get noEmailSet => 'No hi ha correu electrònic configurat';

  @override
  String get setDueDateAndTime => 'Establir data i hora de venciment';

  @override
  String get pairingDescFieldy => 'Manteniu premut el dispositiu fins que aparegui la llum per encendre\'l.';

  @override
  String get maximumSecurityE2ee => 'Seguretat màxima (E2EE)';

  @override
  String get instantSpeakerLabels => 'Etiquetes d\'interlocutor instantànies';

  @override
  String get resetRequestConfig => 'Restablir configuració de sol·licitud per defecte';

  @override
  String get webhookUrlNotSet => 'URL de Webhook no configurada';

  @override
  String get feedbackReasonRecordingOther => 'Something else';

  @override
  String get accountCutoverMigrationRollbackMessage =>
      'Tu cuenta está en mantenimiento tras una reversión de migración. Algunos datos más recientes pueden quedar retenidos.';

  @override
  String get cancelConsequenceQuality => '30% menys qualitat de transcripció (models al dispositiu)';

  @override
  String get pairingDescPlaudNote =>
      'Manteniu premut el botó lateral durant 2 segons. El LED vermell parpellejarà quan estigui llest per aparellar.';

  @override
  String get plansAndBilling => 'Plans i Facturació';

  @override
  String get deviceOnboardingVoiceReplyTitle => 'Escolta les respostes d\'Omi';

  @override
  String get generatingIcon => 'Generant icona…';

  @override
  String get cleanUpBannerBody => 'Sobretot noms mal sentits. Revisa\'ls i elimina els que no siguin reals.';

  @override
  String get speakerTagPromptSavedAsYou => 'Desat com a tu';

  @override
  String get connectOmiOmiGlass => 'Connectar Omi / OmiGlass';

  @override
  String get capabilityConversations => 'Converses';

  @override
  String get notificationFrequencyDescription =>
      'Controla amb quina freqüència Omi t\'envia notificacions proactives i recordatoris.';

  @override
  String chatScopeAbout(String title) {
    return 'Sobre: $title';
  }

  @override
  String get importHistory => 'Historial d\'importació';

  @override
  String get getApiKey => 'Obtén la clau d\'API';

  @override
  String get nothingInterestingRetry => 'No s\'ha trobat res interessant,\nvols tornar-ho a provar?';

  @override
  String get whatWouldYouLikeToCreate => 'Què voldries crear?';

  @override
  String get pricingFree => 'Gratuït';

  @override
  String get speakerTagPromptHintIdentify => 'La teva resposta ajuda Omi a reconèixer aquesta veu la pròxima vegada.';

  @override
  String get noConversationsYet => 'Encara no hi ha converses';

  @override
  String get deviceNotMeetRequirements =>
      'El teu dispositiu no compleix els requisits per a la transcripció al dispositiu.';

  @override
  String get pressKeys => 'Prem tecles…';

  @override
  String get downgradeLimitDelayNotRealTime => 'Retard de 5-7 segons (no en temps real)';

  @override
  String get conversationLinkCopiedToClipboard => 'Enllaç de la conversa copiat al porta-retalls';

  @override
  String get onboardingSetupStepMemory => 'Configurant la teva memòria';

  @override
  String get chatAppsTelegramOtherDevice => 'Telegram en un altre dispositiu?';

  @override
  String get appNotFoundOrRemoved => 'Aquesta aplicació ja no està disponible';

  @override
  String appsCount(String count) {
    return 'Aplicacions ($count)';
  }

  @override
  String get endToEndEncryption => 'Xifratge d\'extrem a extrem';

  @override
  String otaConnectFailed(String deviceName) {
    return 'No s\'ha pogut connectar a $deviceName. Mantén-lo encès i a prop i torna-ho a provar.';
  }

  @override
  String get continueButton => 'Continuar';

  @override
  String get failedToPrepareConversationForSharing =>
      'Error en preparar la conversa per compartir. Si us plau, torna-ho a provar.';

  @override
  String get showAll => 'Mostra-ho tot →';

  @override
  String get speakerLabelYou => 'Tu';

  @override
  String get wrappedActionItems => 'Tasques';

  @override
  String failedToInstallApp(String appName) {
    return 'Error en instal·lar $appName. Si us plau, torna-ho a provar.';
  }

  @override
  String get searching => 'Cercant';

  @override
  String get deviceNotCompatibleTitle => 'Dispositiu no compatible';

  @override
  String get summarize => 'Resumir';

  @override
  String get exportConversationsToJson => 'Exporta les converses a un fitxer JSON';

  @override
  String makeItemPrivateExplanation(String item) {
    return 'Si fas $item privat ara, deixarà de funcionar per a tothom i només serà visible per a tu';
  }

  @override
  String get wrappedFailedToShare => 'No s\'ha pogut compartir. Torna a provar.';

  @override
  String get cancelSubscriptionConfirmation =>
      'Continuaràs tenint accés fins al final del període de facturació actual.';

  @override
  String get phoneHideKeypad => 'Amaga el teclat';

  @override
  String get vadGate => 'VAD Gate';

  @override
  String get nameUpdatedSuccessfully => 'Nom actualitzat correctament!';

  @override
  String get photoLibrary => 'Biblioteca de fotos';

  @override
  String get chatAppsHeroMessage =>
      'Pregunta sobre el teu dia, desa records i gestiona tasques des de Telegram o iMessage. Els teus xats es queden a l\'aplicació que fas servir, i l\'Omi recorda de què heu parlat a tot arreu.';

  @override
  String get upgradeToAnnualPlan => 'Actualitzar al pla anual';

  @override
  String get completeAuthInBrowser =>
      'Completeu l\'autenticació al vostre navegador. Un cop fet, torneu a l\'aplicació.';

  @override
  String errorLabel(String error) {
    return 'Error: $error';
  }

  @override
  String get durationThresholdDesc => 'Amagar converses més curtes que això';

  @override
  String transcriptionsPendingCount(int count) {
    return 'Transcripcions pendents $count';
  }

  @override
  String get transcribeLaterNote =>
      'Funciona amb el micròfon del telèfon i amb dispositius Omi i Limitless. L\'àudio es queda al teu telèfon fins que decideixis pujar-lo.';

  @override
  String get device => 'Dispositiu';

  @override
  String get signUpSuccess => 'Registre correcte!';

  @override
  String get onboardingPermissions => 'Permisos';

  @override
  String get modelTooLargeWarning =>
      'Aquest model és gran i pot fer que laplicació es bloquegi o funcioni molt lentament en dispositius mòbils.\n\nEs recomana small o base.';

  @override
  String get showDailyScoreOnHomepage => 'Mostra la puntuació diària a la pàgina principal';

  @override
  String confidenceSummaryUnverified(String name) {
    return 'Encara no has etiquetat ni confirmat $name, així que Omi no està segur de conèixer la seva veu.';
  }

  @override
  String get endConversation => 'Finalitzar conversa';

  @override
  String get unpinAsBaseline => 'Deixa de fixar com a base';

  @override
  String audioSavedLocally(String duration) {
    return '$duration d\'àudio desat localment';
  }

  @override
  String get editMemory => '✏️ Edita memòria';

  @override
  String get speakerTagPromptThanks => 'Gràcies! L’Omi reconeixerà les veus cada cop millor.';

  @override
  String get actionItemDescriptionEmpty => 'La descripció de la tasca no pot estar buida.';

  @override
  String get maybeLater => 'Potser més tard';

  @override
  String get daySummary => 'Resum del dia';

  @override
  String get confirmReportMessage => 'Vols denunciar aquest missatge?';

  @override
  String get deleteAllLimitlessConversations => 'Eliminar totes les converses de Limitless?';

  @override
  String get selectAllTasksMenu => 'Selecciona tot';

  @override
  String get syncStatusRetrying => 'No s\'ha pogut processar — reintentant';

  @override
  String get exportButton => 'Exportar';

  @override
  String get wrappedYouTalkedAboutBadge => 'Has parlat de';

  @override
  String get firmwareWarningTitle => 'Important: Llegiu abans d\'actualitzar';

  @override
  String get permissionTypeCreate => 'Crear';

  @override
  String get viewUsage => 'Veure ús';

  @override
  String get deviceOnboardingIntroDuration => 'Aproximadament 1 minut';

  @override
  String get import => 'Importar';

  @override
  String get conversationsExportStarted =>
      'S\'ha iniciat l\'exportació de converses. Això pot trigar uns segons, espereu.';

  @override
  String get speechToTextProvider => 'Proveïdor de veu a text';

  @override
  String get languageTranslation => 'Traducció de més de 100 idiomes';

  @override
  String get primaryLanguage => 'Idioma principal';

  @override
  String durationSeconds(String seconds) {
    return 'Durada: $seconds segons';
  }

  @override
  String get autoSyncDescription =>
      'Sincronitza automàticament els enregistraments fora de línia quan el dispositiu es connecti';

  @override
  String get debugLogs => 'Registres de depuració';

  @override
  String get authorizationRevoked => 'Autorització revocada.';

  @override
  String get noTranscriptAvailable => 'No hi ha transcripció disponible';

  @override
  String get available => 'Disponible';

  @override
  String get wrappedObsessionsLabelUpper => 'OBSESSIONS';

  @override
  String get professionStudent => 'Estudiant';

  @override
  String get chatAppsTryRemind => 'Recorda\'m trucar a la mare diumenge';

  @override
  String get failedToStartVerification => 'No s\'ha pogut iniciar la verificacio';

  @override
  String get failedToCreateFolder => 'No s\'ha pogut crear la carpeta';

  @override
  String timeMinSingular(int count) {
    return '$count min';
  }

  @override
  String get insights => 'Informació';

  @override
  String get privacyInformation => 'Informació de privadesa';

  @override
  String get finishedConversation => 'Conversa acabada?';

  @override
  String get syncGoogleAccount => 'Sincronitzar amb el vostre compte de Google';

  @override
  String get pairingTitleNeoOne => 'Posa Neo One en mode d\'aparellament';

  @override
  String get translatedByOmi => 'traduït per Omi';

  @override
  String get githubRepositoryUrl => 'URL del repositori de GitHub';

  @override
  String get readOnlyScope => 'Només lectura';

  @override
  String get chatAppsChannelsTitle => 'Aplicacions de xat';

  @override
  String get chatAppsDoesAnswer => 'Respon preguntes sobre les teves converses i records';

  @override
  String get wrappedFailedToStartGeneration => 'No s\'ha pogut iniciar la generació. Torna a provar.';

  @override
  String get storageLocationSdCard => 'Targeta SD';

  @override
  String get askSuggestDecide => 'Què he decidit avui?';

  @override
  String get close => 'Tancar';

  @override
  String get paymentMethodPayPal => 'PayPal';

  @override
  String categoryAppCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count aplicacions',
      one: '1 aplicació',
    );
    return '$_temp0';
  }

  @override
  String get speakerTagPromptRecentPeople => 'Persones amb qui has parlat fa poc';

  @override
  String get actionCreateMemories => 'Crear records';

  @override
  String get swipeTasksToIndent => 'Llisqueu les tasques per sagnar, arrossegueu entre categories';

  @override
  String get createAccountTitle => 'Crear un compte';

  @override
  String get modelRequired => 'Model requerit';

  @override
  String get saveMemory => 'Desar record';

  @override
  String get successfullyConnectedClickUp => 'Connectat correctament a ClickUp!';

  @override
  String get notYetSynced => 'Encara no sincronitzat amb el vostre telèfon';

  @override
  String get pendantUpToDate => 'El penjoll està actualitzat';

  @override
  String get categoryProductivityTools => 'Eines de productivitat';

  @override
  String get refresh => 'Actualitza';

  @override
  String get cancelSyncMessage => 'Les dades ja descarregades es guardaran. Pots continuar més tard.';

  @override
  String get selectImageFileTitle => 'Selecciona un fitxer d\'imatge';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'Error en obrir el selector de fitxers: $message';
  }

  @override
  String get failedToGenerateConversationLink => 'No s\'ha pogut generar l\'enllaç de la conversa';

  @override
  String get voiceFailedToTranscribe => 'No s\'ha pogut transcriure l\'àudio';

  @override
  String get viewAll => 'Veure tot';

  @override
  String get yourNewKey => 'La teva nova clau:';

  @override
  String get conversationMap => 'Mapa de converses';

  @override
  String get contactSupportAction => 'Contacta amb el suport';

  @override
  String get weekdaySun => 'Dg';

  @override
  String get summaryNotFound => 'Resum no trobat';

  @override
  String get shortConversationThreshold => 'Llindar de conversa curta';

  @override
  String get dailyRecapsDescription => 'Els teus resums diaris apareixeran aquí un cop generats';

  @override
  String get phoneCallsWithOmi => 'Trucades amb Omi';

  @override
  String get addAppSelectPaymentPlan => 'Seleccioneu un pla de pagament i introduïu un preu per a la vostra aplicació';

  @override
  String get deleteAccountFinal =>
      'Aquesta acció és irreversible i eliminarà permanentment el vostre compte i totes les dades associades. Esteu segur que voleu continuar?';

  @override
  String get gettingAudioFiles => 'Obtenint fitxers d\'àudio…';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String get port => 'Port';

  @override
  String personPinnedToast(String name) {
    return 'S\'ha fixat $name';
  }

  @override
  String get wrappedConversations => 'converses';

  @override
  String get availableOnMacMobileWeb => 'Disponible a Mac, mòbil i web';

  @override
  String get monthAug => 'Ag';

  @override
  String get failedToGenerateSummary =>
      'No s\'ha pogut generar el resum. Assegura\'t que tens converses per a aquest dia.';

  @override
  String planEndedOn(String date) {
    return 'El teu pla va acabar el $date.\nTorna a subscriure\'t ara - se\'t cobrarà immediatament per un nou període de facturació.';
  }

  @override
  String get createAnApp => 'Crear una aplicació';

  @override
  String get cancelling => 'Cancel·lant…';

  @override
  String get wrappedTopDaysHeader => 'millors dies';

  @override
  String get keepEditing => 'Continua editant';

  @override
  String get ignoredVoicesEmpty => 'Cap veu ignorada';

  @override
  String get cannotBeUndone => 'Això no es pot desfer.';

  @override
  String get usersPayToUse => 'Els usuaris paguen per utilitzar la vostra aplicació';

  @override
  String get maxFilesUploadError => 'Només pots pujar 4 fitxers a la vegada';

  @override
  String get yourDeviceIsUpToDate => 'El vostre dispositiu està actualitzat';

  @override
  String get unableToFetchApps =>
      'No s\'han pogut obtenir les aplicacions :(\n\nComproveu la vostra connexió a internet i torneu-ho a provar.';

  @override
  String get entityCorrectionFailed => 'No s’ha pogut enviar la teva correcció. Torna-ho a provar.';

  @override
  String get alreadyAuthorized => 'Ja autoritzat';

  @override
  String get speedAccuracyLower => 'La velocitat i la precisió poden ser inferiors als models al núvol.';

  @override
  String siriShortcutsSearchHint(String searchPhrase) {
    return ' També podeu dir «$searchPhrase for what I did today».';
  }

  @override
  String get unlimitedPlan => 'Pla il·limitat';

  @override
  String get contactSupport => 'Contactar amb suport?';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Màxim $count objectius permesos';
  }

  @override
  String get deviceStorageNearlyFull => 'El dispositiu és gairebé ple — sincronitza per alliberar espai.';

  @override
  String get setDueDate => 'Establir data de venciment';

  @override
  String privateAppsCount(String count) {
    return 'Aplicacions privades ($count)';
  }

  @override
  String get selectPeople => 'Selecciona persones';

  @override
  String get capabilityChat => 'Xat';

  @override
  String chatAppsChannelChats(String app) {
    return 'Xats de $app';
  }

  @override
  String get transcribeLaterTitle => 'Transcriure més tard';

  @override
  String get failedToConnectAsana => 'No s\'ha pogut connectar a Asana';

  @override
  String get youAreOnUnlimitedPlan => 'Estàs al pla Il·limitat.';

  @override
  String get chatAppsIncludedWithPro => 'INCLÒS AMB OMI PRO';

  @override
  String get failedToCreateKeyTryAgain => 'Error en crear la clau. Si us plau, torna-ho a provar.';

  @override
  String get backgroundModeTitle => 'Mode en segon pla';

  @override
  String get discardChangesMessage => 'Es perdran els canvis no desats.';

  @override
  String get captureSourcePendant => 'Penjoll';

  @override
  String get exportTasksWithOneTap => 'Exporta tasques amb un toc!';

  @override
  String get sundayAbbr => 'Dg';

  @override
  String get pleaseEnterAppPrompt => 'Si us plau, introduïu una indicació per a la vostra aplicació';

  @override
  String deviceStoragePercentFull(int percent) {
    return '$percent% ple';
  }

  @override
  String get developerSettings => 'Configuració de desenvolupador';

  @override
  String get selectYouFromList => 'Per etiquetar-te, si us plau selecciona \"Tu\" de la llista.';

  @override
  String get deleteNow => 'Eliminar ara';

  @override
  String get installUpdate => 'Instal·lar actualització';

  @override
  String get unpairDevice => 'Desvincula el dispositiu';

  @override
  String get assistantVoice => 'Veu de l\'assistent';

  @override
  String get installingApp => 'Instal·lant aplicació…';

  @override
  String get wrappedFunnyMomentTitle => 'Moment divertit';

  @override
  String onboardingFailedCheckNotification(String error) {
    return 'Error en comprovar el permís de notificacions: $error';
  }

  @override
  String get dreamReportRunNow => 'Executa ara';

  @override
  String get notSet => 'No establert';

  @override
  String get startVoiceRecording => 'Inicia l\'enregistrament de veu';

  @override
  String get userInformation => 'Informació de l\'Usuari';

  @override
  String get wrappedStruggleLabel => 'REPTE';

  @override
  String get filterInteresting => 'Informacions';

  @override
  String captureRecordingsCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count enregistraments',
      one: '1 enregistrament',
    );
    return '$_temp0';
  }

  @override
  String get addOrChangeYourPaymentMethod => 'Afegeix o canvia el mètode de pagament';

  @override
  String get unableToLoadApps => 'No es poden carregar les aplicacions';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'Hi ha una nova actualització de firmware ($version) disponible per al teu dispositiu Omi. Vols actualitzar ara?';
  }

  @override
  String get cancelReasonTooExpensive => 'Massa car';

  @override
  String get firmwareUsbWarning => 'La connexió USB durant les actualitzacions pot fer malbé el teu dispositiu.';

  @override
  String authAccessMessage(String appName) {
    return 'Haureu d\'autoritzar Omi per accedir a les vostres dades de $appName. Això obrirà el vostre navegador per a l\'autenticació.';
  }

  @override
  String get conversationEndsManually => 'La conversa només acabarà manualment.';

  @override
  String get partialRecording => 'Enregistrament parcial';

  @override
  String get dreamReportFeedback => 'Informat a l\'equip d\'Omi';

  @override
  String get shareAudio => 'Compartir àudio';

  @override
  String get importDataFromOtherSources => 'Importa dades d\'altres fonts';

  @override
  String get premiumMinutesUsed => 'Minuts premium utilitzats.';

  @override
  String get phoneCallsUpgradeButton => 'Actualitza a Il·limitat';

  @override
  String get omiUnlimited => 'Omi Il·limitat';

  @override
  String get unknownDevice => 'Desconegut';

  @override
  String get failedToStartImport => 'No s\'ha pogut iniciar la importació. Torneu-ho a provar.';

  @override
  String get searchActionItems => 'Cerca tasques';

  @override
  String get whisperModel => 'Model Whisper';

  @override
  String get searchContacts => 'Cerca contactes';

  @override
  String get selectAllSkipsPinned =>
      '«Selecciona-ho tot» omet les persones fixades. Elimina-les una a una des de la seva pàgina.';

  @override
  String get speechProfileIntro =>
      'Omi necessita aprendre els vostres objectius i la vostra veu. Podreu modificar-ho més tard.';

  @override
  String get realtimeListening => 'Escolta en temps real';

  @override
  String get appNotAvailable => 'Vaja! Sembla que l\'aplicació que busques no està disponible.';

  @override
  String get enterYourName => 'Introduïu el vostre nom';

  @override
  String get permissionTypeTrigger => 'Disparador';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'El graf de coneixement es construirà automàticament quan creïs nous records.';

  @override
  String get chatAppsLink => 'Enllaç';

  @override
  String get minutes => 'minuts';

  @override
  String get actions => 'Accions';

  @override
  String get connectRayBanMeta => 'Connecta Ray-Ban Meta';

  @override
  String get monthSep => 'Set';

  @override
  String get selectContactsToShareSummary => 'Selecciona contactes per compartir el resum de la conversa';

  @override
  String get paymentNoneSelected => 'Cap seleccionat';

  @override
  String get pinAction => 'Fixa';

  @override
  String get monthOct => 'Oct';

  @override
  String get startRecording => 'Comença la gravació';

  @override
  String get somethingWentWrong => 'Alguna cosa ha anat malament! Torneu-ho a provar més tard.';

  @override
  String largeTimeGapsDetected(String gaps) {
    return 'S\'han detectat grans intervals de temps ($gaps)';
  }

  @override
  String get phoneEnterNumber => 'Introdueix numero';

  @override
  String get cancelConsequenceNoAccess => 'Ja no tindràs accés il·limitat al final del teu període de facturació.';

  @override
  String get appleHealthDeniedTitle => 'Accés a Apple Health denegat';

  @override
  String deleteItemTitle(String item) {
    return 'Eliminar $item';
  }

  @override
  String get invalidIntegrationUrl => 'URL d\'integració no vàlida';

  @override
  String get welcomeActionItemsTitle => 'Llest per a les tasques';

  @override
  String get updateAppConfirmation => 'Els canvis es publicaran un cop revisats pel nostre equip.';

  @override
  String get corruptedStatus => 'Corrupte';

  @override
  String get cantRateWithoutInternet => 'No es pot valorar l\'aplicació sense connexió a Internet.';

  @override
  String get dontShowAgain => 'No ho tornis a mostrar';

  @override
  String get hardwareRevision => 'Revisió de maquinari';

  @override
  String get trySelectingDifferentDate => 'Prova de seleccionar una altra data';

  @override
  String get learnings => 'Aprenentatges';

  @override
  String get failedToConnectTodoist => 'No s\'ha pogut connectar a Todoist';

  @override
  String get accessDataProgrammatically => 'Accedeix a les teves dades programàticament';

  @override
  String processingProgress(int current, int total) {
    return 'Processant $current/$total';
  }

  @override
  String get apiEnvSavedRestartRequired => 'Desat. Tanca i torna a obrir l\'aplicació per aplicar els canvis.';

  @override
  String get syncCardWaitingInternet => 'Esperant connexió';

  @override
  String get accountCutoverOpenStore => 'Abrir tienda';

  @override
  String get processedConversations => 'Converses processades';

  @override
  String get holdOnPreparingForm => 'Espera, estem preparant el formulari per a tu';

  @override
  String get waitingForDevice => 'Esperant el dispositiu…';

  @override
  String get learnMore => 'Més informació…';

  @override
  String get aiGenErrorWhileCreatingApp => 'S\'ha produït un error en crear l\'aplicació';

  @override
  String get deleteAllFilesWarning =>
      'Això eliminarà els enregistraments sincronitzats i pendents. Els enregistraments pendents NO estan sincronitzats i es perdran permanentment.';

  @override
  String get usageWordsHeard => 'Words heard';

  @override
  String get importDataDescription => 'Importa dades d\'altres fonts';

  @override
  String get raybanMetaImageCaptureUnavailable => 'No disponible en mode només àudio';

  @override
  String get appRejectedMessage =>
      'La teva aplicació ha estat rebutjada. Actualitza els detalls i torna a enviar-la per a revisió.';

  @override
  String get capturePendantDisconnectedShort => 'Omi es tornarà a connectar sol';

  @override
  String get improveSpeechProfileDesc =>
      'Utilitzem els enregistraments per entrenar i millorar el vostre perfil de veu personal.';

  @override
  String get voiceResponseModeTitle => 'Quan pronunciar les respostes';

  @override
  String get failedToDeleteItem => 'No s\'ha pogut eliminar la tasca';

  @override
  String get firmware => 'Microprogramari';

  @override
  String failedToAddToService(String serviceName) {
    return 'Error en afegir a $serviceName';
  }

  @override
  String get askOmiAnything => 'Pregunta a Omi qualsevol cosa sobre la teva vida';

  @override
  String get integrationsFooter => 'Connecteu les vostres aplicacions per veure dades i estadístiques al xat.';

  @override
  String get loading => 'Carregant…';

  @override
  String get showLess => 'mostra menys ↑';

  @override
  String get chatAppsNeverMessagesOthers => 'Mai escriu a altres persones per tu';

  @override
  String get scopeUserName => 'Nom d\'usuari';

  @override
  String get mute => 'Silenciar';

  @override
  String get serverProcessesAudio => 'El servidor processa els fitxers d\'àudio i crea records';

  @override
  String mergeConversationsSuccessBody(int count) {
    return '$count converses s\'han fusionat amb èxit';
  }

  @override
  String get pairingSuccessful => 'VINCULACIÓ CORRECTA';

  @override
  String get websocketUrl => 'URL de WebSocket';

  @override
  String get wrappedFriend => 'Amic';

  @override
  String get frequencyHigh => 'Alt';

  @override
  String get processingFailed => 'Processament fallat';

  @override
  String get dataLowercase => 'dades';

  @override
  String deviceOfflineWakeHint(String deviceName) {
    return '$deviceName està fora de línia. Prem el botó per activar-lo i torna-ho a provar.';
  }

  @override
  String get updatedConversations => 'Converses actualitzades';

  @override
  String get phoneGetStarted => 'Comenca';

  @override
  String get recordingDetails => 'Detalls de l\'enregistrament';

  @override
  String get createApiKey => 'Crear clau API';

  @override
  String get anyoneWithLinkCanView => 'Qualsevol persona amb l\'enllaç pot veure';

  @override
  String get noPendingTasks => 'No hi ha tasques pendents';

  @override
  String get featureComingSoon => 'Aquesta funció arribarà aviat!';

  @override
  String get bluetoothMethodDescription =>
      'Utilitza connexió Bluetooth Low Energy estàndard. Més lent però no afecta la connexió WiFi.';

  @override
  String get chatAppsNotConnectedTitle => 'No connectat';

  @override
  String get wrappedMostIntenseDay => 'Més intens';

  @override
  String get yesterday => 'Ahir';

  @override
  String get requestConfiguration => 'Configuració de sol·licitud';

  @override
  String get timeAM => 'AM';

  @override
  String autoRemoveSyncedCopiesDescription(int days) {
    return 'Elimina les còpies locals $days dies després de la sincronització. Les còpies al núvol es conserven.';
  }

  @override
  String get chatAppsTelegramPrivacyNote =>
      'Telegram també desa els teus xats amb l\'Omi. L\'Omi només et respon a tu, mai a altres persones, i et pots desconnectar quan vulguis.';

  @override
  String speakerWithId(String speakerId) {
    return 'Parlant $speakerId';
  }

  @override
  String get reviewNoDate => 'Cap';

  @override
  String get transcript => 'Transcripció';

  @override
  String get deviceDiagnosticsUploadFailed => 'Could not send diagnostics to support. Please try again.';

  @override
  String get noFoldersAvailable => 'No hi ha carpetes disponibles';

  @override
  String get addAppSelectCategory => 'Seleccioneu una categoria per a la vostra aplicació';

  @override
  String get conversations => 'Converses';

  @override
  String get upgradeToUnlimited => 'Actualitza a il·limitat';

  @override
  String get deleteFlowConfirmTitle => 'Vols suprimir el teu compte?';

  @override
  String get accountCutoverMigrationInProgressMessage =>
      'Tu cuenta se está migrando. Las funciones del producto están en pausa hasta que termine la migración.';

  @override
  String get permissionAllowed => 'Permès';

  @override
  String get pressDoneToSave => 'Premeu fet per desar';

  @override
  String get listening => 'Escoltant';

  @override
  String get audioReady => 'Àudio llest';

  @override
  String get freeForEveryone => 'Gratuïta per a tothom';

  @override
  String get buildingKnowledgeGraphFromMemories => 'Construint el graf de coneixement a partir de records…';

  @override
  String get onDeviceTranscription => 'Transcripció al dispositiu';

  @override
  String errorWithMessage(String error) {
    return 'Error: $error';
  }

  @override
  String get chatAppsProblemOffline => 'No tens connexió. Comprova-la i torna-ho a provar.';

  @override
  String get callAlreadyInProgress => 'Ja hi ha una trucada en curs';

  @override
  String get reviewQuestionSpelling => 'Com s’escriu això?';

  @override
  String get firmwareStableConnection => 'Connexió estable';

  @override
  String get categoryOther => 'Altres';

  @override
  String get perMonthLabel => '/ mes';

  @override
  String get onboardingYoureAllSet => 'Ja estàs llest';

  @override
  String get resumeRecording => 'Reprendre la gravació';

  @override
  String get feedbackSubtitleAudioQuality => 'Ens encantaria entendre què va anar malament.';

  @override
  String get speakerTagPromptPlayClip => 'Reprodueix el clip';

  @override
  String get anonymityAndPrivacy => 'Anonimat i privadesa';

  @override
  String get noMemoriesToDelete => 'No hi ha records per eliminar';

  @override
  String get syncStepProcess => 'Transcripció';

  @override
  String get callStateRinging => 'Sonant…';

  @override
  String get setupOnDevice => 'Configura al dispositiu';

  @override
  String get creatorPayouts => 'Pagaments als creadors';

  @override
  String get olderDeviceDetected => 'Detectat dispositiu antic';

  @override
  String get deletePhoneNumberWarning => 'Hauras de verificar de nou per fer trucades';

  @override
  String get appVisibilityChangedSuccessfully =>
      'La visibilitat de l\'aplicació s\'ha canviat amb èxit. Pot trigar uns minuts a reflectir-se.';

  @override
  String get failedToCreateActionItem => 'Error en crear la tasca';

  @override
  String get msgSelectFilesGenericError => 'Error en seleccionar fitxers. Si us plau, torneu-ho a provar.';

  @override
  String get pendantRecordingSyncBlocked =>
      'El Pendant encara està gravant, així que el seu àudio emmagatzemat no es pot transferir. Prem el botó del Pendant per aturar la gravació i torna a sincronitzar.';

  @override
  String get failedToStartMerge => 'No s\'ha pogut iniciar la fusió';

  @override
  String get shortcutChangeInstruction => 'Feu clic en una drecera per canviar-la. Premeu Escape per cancel·lar.';

  @override
  String get notificationsAndDisplay => 'Notificacions i visualització';

  @override
  String get getPaidThroughStripe => 'Cobreu les vendes de les vostres aplicacions a través de Stripe';

  @override
  String get weekdayWed => 'Dc';

  @override
  String get send => 'Enviar';

  @override
  String get nativeEngineNoDownload =>
      'Sutilitzarà el motor de veu natiu del teu dispositiu. No cal descarregar cap model.';

  @override
  String get wrappedActions => 'accions';

  @override
  String get conversationTimeoutConfig => 'Quant espera Omi en silenci abans de tancar una conversa';

  @override
  String get mic => 'Micròfon';

  @override
  String deviceOnboardingVoiceReplyStatusAlwaysHeadphones(String device) {
    return 'Reproducció al $device.';
  }

  @override
  String failedToSendReply(String error) {
    return 'No s\'ha pogut enviar la resposta: $error';
  }

  @override
  String get whisperModelSizeTiny => 'Molt petit';

  @override
  String get speakerTagPromptNotMeAction => 'No sóc jo';

  @override
  String get setupInstructions => 'Instruccions de configuració';

  @override
  String get noLanguagesFound => 'No s\'han trobat idiomes';

  @override
  String get experimental => 'Experimental';

  @override
  String get continueRecording => 'Continuar la gravació';

  @override
  String get selectDefaultRepoDesc =>
      'Seleccioneu un repositori per defecte per crear incidències. Encara podeu especificar un repositori diferent quan creeu incidències.';

  @override
  String sharedTasksTitle(String name, int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count tasques',
      one: '1 tasca',
    );
    return '$name ha compartit $_temp0';
  }

  @override
  String get permissionsRequiredDesc =>
      'Aquesta aplicació necessita permisos de Bluetooth i ubicació per funcionar correctament. Activeu-los a la configuració.';

  @override
  String diagnosticsVerdictReconnectsDetail(String duration) {
    return 'Talls breus, torna en uns $duration cada vegada';
  }

  @override
  String get transferring => 'Transferint…';

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '$used de $limit paraules utilitzades aquest mes';
  }

  @override
  String get noChatAppsEnabled => 'No hi ha aplicacions de xat activades.\nToca \"Activar aplicacions\" per afegir-ne.';

  @override
  String get tipKeepPhoneNearby => 'Manteniu el telèfon a prop per a una sincronització més ràpida';

  @override
  String get authFailedToSignInWithGoogle => 'No s\'ha pogut iniciar sessió amb Google, si us plau torneu-ho a provar.';

  @override
  String get frequencyDescLow => 'Només coses importants, unes 3–5 al dia';

  @override
  String get availableTemplates => 'Plantilles disponibles';

  @override
  String get captureEveryMoment => 'Omi grava les teves converses i escriu\nel resum i les tasques per a tu.';

  @override
  String get migrationErrorOccurred => 'S\'ha produït un error durant la migració. Si us plau, torna-ho a provar.';

  @override
  String get wrappedCompletedLabel => 'Completat';

  @override
  String speakerTagPromptLabeledToast(String name) {
    return 'Etiquetat com a $name';
  }

  @override
  String get docs => 'Documentació';

  @override
  String get dateTimeLabel => 'Data i hora';

  @override
  String get editFolder => 'Edita la carpeta';

  @override
  String get apps => 'Aplicacions';

  @override
  String segmentsSingular(String count) {
    return '$count segment';
  }

  @override
  String get deviceSettings => 'Configuració del dispositiu';

  @override
  String get offline => 'Fora de línia';

  @override
  String get createActionItemTooltip => 'Crear nova tasca';

  @override
  String get forgetDevice => 'Oblidar dispositiu';

  @override
  String get reviewEntryTitle => 'Preguntes per a tu';

  @override
  String get enterEmailError => 'Introduïu el vostre correu electrònic';

  @override
  String get appDisabledOwnerHint =>
      'Corregeix primer l\'endpoint: en reactivar-la es torna a comprovar cada URL configurat.';

  @override
  String get chatAppsIMessageSubtitle => 'Escriu a l\'Omi des del teu número de telèfon';

  @override
  String get tasksExportedOneApp => 'Les tasques es poden exportar a una aplicació alhora.';

  @override
  String transcriptSpeakerCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count participants',
      one: '1 participant',
    );
    return '$_temp0';
  }

  @override
  String get saveGoal => 'Desa';

  @override
  String get noBatteryDataYet => 'Encara no hi ha dades de bateria';

  @override
  String chatUsedOfLimitMessages(String used, String limit) {
    return '$used de $limit missatges utilitzats aquest mes';
  }

  @override
  String get backgroundActivityDesc =>
      'Perquè l\'Omi continuï capturant amb la pantalla apagada o quan canvies d\'app.';

  @override
  String get addAppUpdateFailed => 'Error en actualitzar. Torneu-ho a provar més tard';

  @override
  String get noMatchingPeople => 'Cap persona coincident';

  @override
  String get unlinkCalendarEvent => 'Desenllaça l\'esdeveniment';

  @override
  String get regenerateRecap => 'Regenera el resum';

  @override
  String get deleteSynced => 'Eliminar sincronitzats';

  @override
  String get speakerTagPromptNameHint => 'El seu nom';

  @override
  String get freePlan => 'Pla gratuït';

  @override
  String get installs => 'INSTAL·LACIONS';

  @override
  String get publicLabel => 'Pública';

  @override
  String get deletingMessages => 'Suprimint els teus missatges de la memòria d\'Omi…';

  @override
  String get pendingFilesDeleted => 'Enregistraments pendents eliminats';

  @override
  String get checkUsage => 'Comprovar ús';

  @override
  String get addWordsDesc => 'Noms, termes o paraules poc comunes';

  @override
  String get entityCorrectionSaved => 'Gràcies. Omi ho corregirà.';

  @override
  String get categoryEducation => 'Educació';

  @override
  String get planAndUsage => 'Pla i ús';

  @override
  String get deleteMemory => 'Eliminar memòria';

  @override
  String get dataProtectionLevel => 'Nivell de protecció de dades';

  @override
  String timeDaySingular(int count) {
    return '$count dia';
  }

  @override
  String get keyCreated => 'Clau creada';

  @override
  String get date => 'Data';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return 'Migrant $itemType… $percentage%';
  }

  @override
  String get enableLocalStorage => 'Activa l\'emmagatzematge local';

  @override
  String get omiSays => 'Omi diu';

  @override
  String get appDetails => 'Detalls de l\'aplicació';

  @override
  String get loadingYourRecording => 'Carregant la gravació…';

  @override
  String get deleteAllLimitlessWarning =>
      'Se suprimiran totes les converses importades de Limitless. Això no es pot desfer.';

  @override
  String get combiningAudioFiles => 'Combinant fitxers d\'àudio…';

  @override
  String get suggestFollowUpQuestion => 'Suggerir una pregunta de seguiment';

  @override
  String chatStarterPrompt(String kind) {
    String _temp0 = intl.Intl.selectLogic(
      kind,
      {
        'capabilities': 'Què pots fer per mi?',
        'goal': 'Ajuda’m a fixar un objectiu',
        'activity': 'Resumeix la meva activitat recent',
        'improve': 'Com puc millorar?',
        'other': '',
      },
    );
    return '$_temp0';
  }

  @override
  String get speakerTagPromptIgnoredNote => 'Omi no tornarà a preguntar per aquesta veu';

  @override
  String get recordWithPhoneInstead => 'Grava amb el telèfon en lloc seu';

  @override
  String get triggerEvent => 'Esdeveniment desencadenant';

  @override
  String get waitingForTranscriptOrPhotos => 'Esperant transcripció o fotos…';

  @override
  String get omiApiKeys => 'Claus API d\'Omi';

  @override
  String addNamedPersonAction(String name) {
    return 'Afegeix «$name»';
  }

  @override
  String get enableDetailedDiagnosticMessages => 'Activeu missatges de diagnòstic detallats del servei de transcripció';

  @override
  String get nameCannotBeEmpty => 'El nom no pot estar buit';

  @override
  String get noTasksYet => 'Encara no hi ha tasques';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'Prova d\'ajustar els termes de cerca o els filtres';

  @override
  String daySummaryForDate(String date) {
    return 'Resum del dia · $date';
  }

  @override
  String get statusTimedOut => 'Temps esgotat';

  @override
  String chatUsageDescription(String used, String limitDisplay, String plan) {
    return 'Has utilitzat $used dels teus $limitDisplay al pla $plan.';
  }

  @override
  String get paypalMeLink => 'Enllaç PayPal.me';

  @override
  String get allMemoriesPrivateResult => 'Tots els records són ara privats';

  @override
  String get scanAgain => 'Torna a cercar';

  @override
  String get doItAgain => 'Fer-ho de nou';

  @override
  String get reviewTitle => 'Revisió';

  @override
  String get photos => 'Fotos';

  @override
  String get phoneNoVerifiedNumbersMessage => 'Verifica el teu número per fer trucades amb Omi.';

  @override
  String get save => 'Desar';

  @override
  String get deleteAccount => 'Eliminar Compte';

  @override
  String get managePaymentMethod => 'Gestionar mètode de pagament';

  @override
  String get selectThumbnailImageTitle => 'Selecciona una imatge en miniatura';

  @override
  String get pairingTitleOmi => 'Enceneu Omi';

  @override
  String get whatsYourPrimaryLanguage => 'Quin és el vostre idioma principal?';

  @override
  String get replyToReview => 'Respondre a la ressenya';

  @override
  String failedToDeleteError(String error) {
    return 'Error en eliminar: $error';
  }

  @override
  String get newestFirst => 'Més recents primer';

  @override
  String get wrappedCreatingYourStory => 'Creant la teva\nhistòria del 2025…';

  @override
  String get chatAppsPrivateMemories => 'Mantén els records privats a l\'aplicació';

  @override
  String get pleaseEnterPayPalEmail => 'Si us plau, introduïu el vostre correu electrònic de PayPal';

  @override
  String get transcription => 'Transcripció';

  @override
  String get yourReview => 'La teva ressenya';

  @override
  String get filesDownloadedUploadedNextTime => 'Els fitxers ja descarregats es pujaran la propera vegada.';

  @override
  String get phoneSetupStep3Subtitle => 'Amb transcripcio en directe integrada';

  @override
  String get mcpConnectionFailed => 'No s\'ha pogut connectar al servidor MCP';

  @override
  String get chatAppsConnectTelegramTitle => 'Connecta Telegram';

  @override
  String get createMemoryTooltip => 'Crear nou record';

  @override
  String get connectDeviceMessage =>
      'Connecteu el vostre dispositiu Omi per accedir\na la configuració i personalització del dispositiu';

  @override
  String get authorizingMcpServer => 'Autoritzant…';

  @override
  String charactersCount(int count) {
    return '$count caràcters';
  }

  @override
  String get syncStatusUploaded => 'Pujat · processant-se a Omi';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'Si us plau, autentiqueu-vos amb $serviceName a Configuració > Integracions de tasques';
  }

  @override
  String get setDefaultButton => 'Establir predeterminada';

  @override
  String get resummarizingConversation => 'Tornant a resumir la conversa…\nAixò pot trigar uns segons';

  @override
  String estimatedHours(int count) {
    return '~$count hora/hores';
  }

  @override
  String get chatAppsInsightsSubtitle => 'Deixa que l\'Omi t\'enviï aquí un resum o una idea.';

  @override
  String get memoryAllowUse => 'Permet l\'ús';

  @override
  String get model => 'Model';

  @override
  String get memoryGraphTitle => 'Gràfic de records';

  @override
  String get endpointURL => 'URL del Punt Final';

  @override
  String get wrappedShareYourWrapped => 'Comparteix el teu Wrapped';

  @override
  String get micGainDescBoosted => 'Potenciat - per entorns silenciosos';

  @override
  String get wrappedMinutes => 'minuts';

  @override
  String get language => 'Idioma';

  @override
  String downloadErrorWithMessage(String error) {
    return 'Error de descàrrega: $error';
  }

  @override
  String get onboardingRatingPromptNo => 'No';

  @override
  String get whatWouldYouLikeToRemember => 'Què vols recordar?';

  @override
  String get deviceOnboardingMuteUnmuteDesc => 'Activa o desactiva el micròfon';

  @override
  String secondsCount(int count) {
    return '$count segons';
  }

  @override
  String get icon => 'Icona';

  @override
  String get realTimeTranscript => 'Transcripció en Temps Real';

  @override
  String get deviceOnboardingVoiceReplySample => 'Entesos. La teva pròxima reunió comença d\'aquí a vint minuts.';

  @override
  String get noDisconnectsRecorded => 'No s\'han registrat desconnexions';

  @override
  String get filterMyApps => 'Les meves aplicacions';

  @override
  String get recapRegenerateCooldown => 'Espera uns segons abans de tornar a regenerar.';

  @override
  String get templateName => 'Nom de la plantilla';

  @override
  String get retry => 'Reintentar';

  @override
  String get sdCardSyncDescription => 'SD Card Sync importarà els teus records de la targeta SD a l\'aplicació';

  @override
  String get deviceTutorial => 'Com utilitzar l\'Omi';

  @override
  String get noApiKeysCreateOne => 'No hi ha claus API. Crea\'n una per començar.';

  @override
  String siriShortcutsSetupHint(String askPhrase, String questionPhrase) {
    return 'Activa Omi a Dreceres → Siri. Digueu «$askPhrase» o «$questionPhrase» i feu la vostra pregunta.';
  }

  @override
  String get failedToDeleteSomeItems => 'No s\'han pogut eliminar alguns elements';

  @override
  String get raybanMetaSetupDescription =>
      'Utilitzeu les vostres ulleres Ray-Ban Meta com a dispositiu de captura d\'Omi per a converses i context visual. Omi obrirà l\'app Meta AI per vincular les vostres ulleres.';

  @override
  String get tabToDo => 'Per fer';

  @override
  String get otaWifiFailed => 'No s\'ha pogut connectar a la Wi-Fi. Comprova el nom de la xarxa i la contrasenya.';

  @override
  String get changePlan => 'Canviar pla';

  @override
  String copiedToClipboard(String title) {
    return '$title copiat al portapapers';
  }

  @override
  String get completeAuthBrowser => 'Completeu l\'autenticació al vostre navegador. Un cop fet, torneu a l\'aplicació.';

  @override
  String get migrationInProgressMessage =>
      'Migració en curs. No pots canviar el nivell de protecció fins que s\'hagi completat.';

  @override
  String get keepSubscription => 'Mantén la subscripció';

  @override
  String get playbackPreparingAudio => 'S\'està preparant l\'àudio…';

  @override
  String get cloudStorageDialogMessage =>
      'Les vostres gravacions en temps real s\'emmagatzemaran a l\'emmagatzematge privat al núvol mentre parleu.';

  @override
  String get newChat => 'Xat nou';

  @override
  String get paymentEnterAmountGreaterThanZero => 'Introduïu un import superior a 0';

  @override
  String showAllPeople(int count) {
    return 'Mostra totes les persones ($count)';
  }

  @override
  String deletePersonNamedTitle(String name) {
    return 'Vols eliminar $name?';
  }

  @override
  String get importTranscriptFiles => 'Fitxers de transcripció';

  @override
  String get transcriptPlaceholder => 'La transcripcio apareixera aqui…';

  @override
  String get logShared => 'Registre compartit';

  @override
  String get deleteReasonNotUsing => 'No l\'utilitzo prou';

  @override
  String diagnosticsDropsPerHour(int count) {
    return 'uns $count per hora';
  }

  @override
  String get wrappedProcessingDefault => 'Processant…';

  @override
  String get failedToConnectGoogleTasksRetry =>
      'No s\'ha pogut connectar a Google Tasks. Si us plau, torna-ho a provar.';

  @override
  String get downloadingFromSdCard => 'Descarregant de la targeta SD';

  @override
  String get firmwareFormatWarning =>
      'Aquest firmware formatarà la targeta SD. Assegureu-vos que totes les dades fora de línia estiguin sincronitzades abans d\'actualitzar.\n\nSi veieu una llum vermella parpellejant després d\'instal·lar aquesta versió, no us preocupeu. Simplement connecteu el dispositiu a l\'aplicació i hauria de tornar-se blau. La llum vermella significa que el rellotge del dispositiu encara no s\'ha sincronitzat.';

  @override
  String get pleaseProvidePrompt => 'Si us plau, proporcioneu una indicació';

  @override
  String get voiceResponseAlways => 'Sempre';

  @override
  String get statusLabel => 'Estat';

  @override
  String get shareLogs => 'Compartir registres';

  @override
  String get continueAnyway => 'Continuar';

  @override
  String get transferCompleteMessage => 'Transferència completada! Ara pots reproduir aquest enregistrament.';

  @override
  String get reviewCaughtUpBody => 'Omi només preguntarà aquí quan et necessiti.';

  @override
  String get calculatingETA => 'Calculant…';

  @override
  String get speechProfileTopicWork => 'A què et dediques?';

  @override
  String get considerOmiCloud => 'Considera utilitzar Omi Cloud per a un millor rendiment.';

  @override
  String get testConversationPrompt => 'Provar un indicador de conversa';

  @override
  String get deletePending => 'Eliminar pendents';

  @override
  String get renameConversation => 'Canvia el nom';

  @override
  String get batteryDrainSignificantly => 'El consum de bateria augmentarà significativament.';

  @override
  String get clear => 'Neteja';

  @override
  String get addAppEnterWebhookUrl => 'Introduïu una URL de webhook per a la vostra aplicació';

  @override
  String get active => 'Actiu';

  @override
  String get exportStartedMessage => 'L\'exportació ha començat. Això pot trigar uns segons…';

  @override
  String get dataAccessNoticeDescription =>
      'Aquesta aplicació accedirà a les teves dades. Omi AI no és responsable de com s\'utilitzen les teves dades.';

  @override
  String get yourRequestUnderReview => 'La teva sol·licitud està en revisió';

  @override
  String get unresolvedSpeakersMessage =>
      'Omi no ha pogut distingir les altres veus entre els enregistraments. Toca una etiqueta de parlant per posar nom a qui parla.';

  @override
  String downloadError(String error) {
    return 'Error de descàrrega: $error';
  }

  @override
  String get offlineSync => 'Sincronització fora de línia';

  @override
  String get cancelSubscription => 'Cancel·lar subscripció';

  @override
  String get claudeDesktopConnectorSetup =>
      'A Claude Desktop → Settings → Connectors, afegeix un connector personalitzat i enganxa l\'URL del servidor. Si Claude demana un Client ID d\'OAuth avançat, utilitza el valor següent i deixa el secret en blanc — mai utilitzis la teva clau d\'API MCP com a secret d\'OAuth.';

  @override
  String get chatAppsTelegramWaiting => 'Esperant que toquis Comença a Telegram…';

  @override
  String get tryAgain => 'Tornar a provar';

  @override
  String get syncStatusOnDevice => 'Al teu dispositiu';

  @override
  String get entityCorrectionTitle => 'Què no és correcte?';

  @override
  String peopleDeletedToast(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count persones eliminades',
      one: '1 persona eliminada',
    );
    return '$_temp0';
  }

  @override
  String get features => 'Funcionalitats';

  @override
  String get startEarning => 'Comença a guanyar! 💰';

  @override
  String get enterYourNumber => 'Introdueix el teu numero';

  @override
  String get addToClaudeCodeConfig => 'Afegeix a ~/.claude.json';

  @override
  String get cleanDisconnect => 'Desconnexió neta';

  @override
  String get grantContactsAccess => 'Dona acces als teus contactes';

  @override
  String get feedbackReasonIncorrect => 'Incorrecte o inventat';

  @override
  String get addAppErrorSelectingImageRetry => 'Error en seleccionar la imatge. Torneu-ho a provar.';

  @override
  String get feedbackTitleNotUsing => 'Què et faria utilitzar Omi més?';

  @override
  String get memories => 'Records';

  @override
  String get capturingPhotos => 'Capturant fotos';

  @override
  String get hideApiKey => 'Amaga la clau d\'API';

  @override
  String get signUpButton => 'Registrar-se';

  @override
  String get tuesdayAbbr => 'Dt';

  @override
  String get noApiKeys => 'Encara no hi ha claus API';

  @override
  String get keyWord => 'Clau';

  @override
  String reviewAnswersConversations(int count) {
    return 'Aquesta resposta etiqueta $count converses';
  }

  @override
  String get statusFailed => 'Fallat';

  @override
  String get installedApps => 'Aplicacions instal·lades';

  @override
  String get flashFirmware => 'Grava el microprogramari';

  @override
  String get conversationUrlCouldNotBeGenerated => 'No s\'ha pogut generar l\'URL de la conversa.';

  @override
  String get reloadingApps => 'Recarregant aplicacions…';

  @override
  String get goalTitle => 'Títol de l\'objectiu';

  @override
  String get importantConversationTitle => 'Conversa important';

  @override
  String get byContinuingAgree => 'En continuar, accepteu la nostra ';

  @override
  String get saturdayAbbr => 'Ds';

  @override
  String get subscriptionReactivatedDefault =>
      'La teva subscripció s\'ha reactivat! Sense càrrecs ara - se\'t facturarà al final del període.';

  @override
  String get tryLatestExperimentalFeatures => 'Proveu les últimes funcions experimentals de l\'equip d\'Omi.';

  @override
  String get chatAppsEntrySubtitle => 'Parla amb l\'Omi des de les aplicacions que ja fas servir cada dia.';

  @override
  String get transcriptionPaused => 'Gravant, reconnectant';

  @override
  String get appleHealthFeatureReadOnlyTitle => 'Accés només de lectura';

  @override
  String get shareDataForTraining => 'Comparteix dades per a l\'entrenament';

  @override
  String get noNotificationScopesAvailable => 'No hi ha àmbits de notificació disponibles';

  @override
  String disconnectFromApp(String appName) {
    return 'Desconnectar de $appName?';
  }

  @override
  String get failedToConnectGoogleTasks => 'No s\'ha pogut connectar a Google Tasks';

  @override
  String get copyToClipboard => 'Copia al porta-retalls';

  @override
  String get stopRecordingConfirmation => 'Vols aturar la gravació i resumir la conversa ara?';

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'No s\'ha pogut generar el resum. Assegura\'t que tens converses per a aquell dia.';

  @override
  String get monthlyLimitReached => 'Heu arribat al vostre límit mensual.';

  @override
  String get permissionsPageDescription =>
      'Omi utilitza aquests permisos per connectar-se al dispositiu, gravar àudio, seguir funcionant en segon pla, enviar recordatoris i anotar on han tingut lloc les converses.';

  @override
  String get onboardingTellUsAboutYourself => 'Explica\'ns sobre tu';

  @override
  String get deviceOnboardingAskQuestionSubtitle =>
      'Prem el botó una vegada, fes la pregunta i torna a prémer quan acabis';

  @override
  String get filters => 'Filtres';

  @override
  String get firmwareUpdateWarning =>
      'No tanqueu l\'aplicació ni apagueu el dispositiu. Això podria danyar el dispositiu.';

  @override
  String get oneSourceAtATime => 'Omi grava des d\'una sola font alhora.';

  @override
  String chatAppsConnectedAs(String handle) {
    return 'Connectat com a $handle';
  }

  @override
  String get pilotFeatures => 'Funcions pilot';

  @override
  String get selectFirmwareZip => 'Selecciona el fitxer ZIP del firmware';

  @override
  String get feedbackReasonRecordingPoorTranscription => 'Poor transcription';

  @override
  String get deleteAccountFailed => 'No s\'ha pogut eliminar el teu compte. Torna-ho a provar.';

  @override
  String get searchConversations => 'Cercar converses';

  @override
  String get frequencyBalanced => 'Equilibrat';

  @override
  String get auto => 'Automàtic';

  @override
  String get actionItemUpdatedSuccessfully => 'Tasca actualitzada correctament';

  @override
  String get entityProjects => 'Projectes';

  @override
  String get signInWithApple => 'Iniciar sessió amb Apple';

  @override
  String get backendUrlLabel => 'URL del servidor';

  @override
  String confidenceSummaryLikely(String name) {
    return 'Omi normalment reconeix la veu de $name, però només ho has confirmat unes quantes vegades.';
  }

  @override
  String get entityOpenThreads => 'Fils oberts';

  @override
  String get deleteActionItemMessage => 'Vols eliminar aquesta tasca?';

  @override
  String chatWithApp(String appName) {
    return 'Xateja amb $appName';
  }

  @override
  String get editActionItem => 'Editar tasca';

  @override
  String get cloudStorageEnabled => 'Emmagatzematge al núvol activat';

  @override
  String get wrappedPersonalGrowth => 'Creixement personal';

  @override
  String get chatAppsProPerkSave => 'Desa records i gestiona tasques directament des del xat';

  @override
  String get alreadyHaveAccountLogin => 'Ja tens un compte? Inicia sessió';

  @override
  String makeItemPublicQuestion(String item) {
    return 'Fer $item públic?';
  }

  @override
  String get usagePeakHour => 'Peak hour';

  @override
  String get addWords => 'Afegir paraules';

  @override
  String get usageNow => 'now';

  @override
  String get usageMinutes => 'minuts';

  @override
  String availableSpace(String space) {
    return 'Espai disponible: $space';
  }

  @override
  String get providingSubtitle => 'Tasques i notes, capturades automàticament.';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% taxa de compleció';
  }

  @override
  String summaryGeneratedFor(String date) {
    return 'Resum generat per $date';
  }

  @override
  String get selectCategory => 'Seleccioneu categoria';

  @override
  String nProcessed(int count) {
    return '$count processats';
  }

  @override
  String get privacyPolicyTitle => 'Política de privadesa';

  @override
  String get deviceMayWarmUp => 'El dispositiu pot escalfar-se durant lús prolongat.';

  @override
  String get designingApp => 'Dissenyant aplicació';

  @override
  String get couldNotLoadWhatsNew => 'No s\'han pogut carregar les novetats';

  @override
  String get doNotCloseApp => 'Si us plau, no tanqueu laplicació.';

  @override
  String get voiceResponseAudio => 'Llegeix la resposta d\'Omi en veu alta';

  @override
  String get allTime => 'Des de sempre';

  @override
  String get developerSettingsTitle => 'Configuració de desenvolupador';

  @override
  String get restoreAction => 'Restaura';

  @override
  String get phoneSetupStep3Title => 'Comenca a trucar als teus contactes';

  @override
  String get anErrorOccurredTryAgain => 'S\'ha produït un error. Si us plau, torna-ho a provar.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'Aquí tens el que hem parlat: $link';
  }

  @override
  String get playbackAudioLoadFailed => 'No s\'ha pogut carregar l\'àudio';

  @override
  String get phoneMute => 'Silenciar';

  @override
  String get captureNotTranscribing => 'Sense transcripció';

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return 'Enregistrament aturat: $reason. És possible que hàgiu de reconnectar les pantalles externes o reiniciar l\'enregistrament.';
  }

  @override
  String get sttProviderDeepgram => 'Deepgram';

  @override
  String get spaceKey => 'Espai';

  @override
  String get raybanMetaOpenMetaAI => 'Connecta a través de Meta AI';

  @override
  String get linkEvent => 'Enllaça un esdeveniment';

  @override
  String get fairUse3Day => 'Últims 3 dies';

  @override
  String failedToStartAppAuth(String appName) {
    return 'No s\'ha pogut iniciar l\'autenticació de $appName';
  }

  @override
  String get processingOnServer => 'Processant al servidor…';

  @override
  String errorStartingRecording(String error) {
    return 'Error en iniciar l\'enregistrament: $error';
  }

  @override
  String get quiet => 'Silenciós';

  @override
  String get startConversationToSeeInsights =>
      'Comenceu una conversa amb Omi\nper veure les vostres estadístiques d\'ús aquí.';

  @override
  String get processAudio => 'Processar àudio';

  @override
  String get chatAppsConnectIMessageTitle => 'Escriu a l\'Omi per connectar';

  @override
  String get chatWithOmi => 'Xatejar amb Omi';

  @override
  String get clickToBeginRecording => 'Feu clic per començar la gravació';

  @override
  String get confirmAndProceed => 'Confirmar i continuar';

  @override
  String get mondayAbbr => 'Dl';

  @override
  String sdCardProcessingMessage(int count) {
    return 'Processant $count enregistrament(s). Els fitxers s\'eliminaran de la targeta SD després.';
  }

  @override
  String get chatReplyNotSignedIn => 'No has iniciat sessió. Inicia sessió i torna-ho a provar.';

  @override
  String deviceOnboardingVoiceReplySettingsHint(String settings, String voiceResponse) {
    return 'Podeu canviar-ho en qualsevol moment al $settings › $voiceResponse';
  }

  @override
  String get wrappedGenerateMyWrapped => 'Genera el meu Wrapped';

  @override
  String get reviewChangesIntro =>
      'El que Omi ha canviat pel seu compte en els últims 30 dies. Desfés qualsevol cosa que no sembli correcta.';

  @override
  String get stripeReadyForPayments =>
      'El vostre compte de Stripe està ara preparat per rebre pagaments. Podeu començar a guanyar amb les vendes de les vostres aplicacions de seguida.';

  @override
  String get appleWatchSetup => 'Configuració de l\'Apple Watch';

  @override
  String get failedToDisconnect => 'No s\'ha pogut desconnectar';

  @override
  String get localStorageEnabled => 'Emmagatzematge local activat';

  @override
  String get captureSourceDesktop => 'Ordinador';

  @override
  String get serialNumber => 'Número de sèrie';

  @override
  String get appleHealthFeatureSecureDesc =>
      'Les teves dades d\'Apple Health se sincronitzen de forma privada amb el teu compte d\'Omi.';

  @override
  String get tryAdjustingSearch => 'Proveu d\'ajustar la cerca o els filtres';

  @override
  String connectTo(String appName) {
    return 'Connectar a $appName';
  }

  @override
  String get exportConversationsDescription => 'Exporta converses a JSON';

  @override
  String get featuredLabel => 'DESTACAT';

  @override
  String get speechProfile => 'Perfil de veu';

  @override
  String get integrations => 'Integracions';

  @override
  String get hideCompletedTasks => 'Amaga les completades';

  @override
  String get sendRawAudioToOmi => 'Envia l\'àudio sense processar a Omi';

  @override
  String ratingsCount(String count) {
    return '$count+ valoracions';
  }

  @override
  String get exportShared => 'Exportació compartida';

  @override
  String get conversationTimeout => 'Temps d\'espera de conversa';

  @override
  String get installStableFirmware => 'Instal·lar firmware estable';

  @override
  String get secureAndReliable => 'Segur i fiable';

  @override
  String get exportingConversations => 'Exportant converses…';

  @override
  String get feedbackReasonRecordingFragmentedOrDuplicated => 'Fragmented or duplicated';

  @override
  String get chatAppsWaitingMessage =>
      'Envia el missatge a Missatges. Aquesta pantalla s\'actualitzarà quan l\'Omi el rebi.';

  @override
  String get onboardingSetupStepWorkspace => 'Preparant el teu espai de treball';

  @override
  String get recap => 'Recapitulació';

  @override
  String get lessThanAMinute => 'Menys d\'un minut';

  @override
  String get tasks => 'Tasques';

  @override
  String get onboardingSetupStepDevices => 'Connectant els teus dispositius';

  @override
  String pinPersonTitle(String name) {
    return 'Fixa $name';
  }

  @override
  String get wrappedButYouPushedThrough => 'Però ho vas aconseguir 💪';

  @override
  String get fetchingYourAppDetails => 'Obtenint els detalls de la teva aplicació';

  @override
  String get timeout2MinutesDesc => 'Finalitzar conversa després de 2 minuts de silenci';

  @override
  String get otaUpdateCancelled => 'S\'ha cancel·lat l\'actualització';

  @override
  String get usageTasksNotes => 'Tasks & notes';

  @override
  String get deviceNotConnected => 'Dispositiu no connectat';

  @override
  String get rayBanMetaMicPickerEmpty =>
      'No s\'ha trobat cap micròfon Bluetooth. Connecta les ulleres a la configuració de l\'iPhone i torna-ho a provar.';

  @override
  String get actionItemCompleted => 'Tasca completada';

  @override
  String get usageSocialSettings => 'En entorns socials';

  @override
  String get from => 'des de';

  @override
  String get siriIndexSetting => 'Use Omi with Siri & Apple Intelligence';

  @override
  String get reviewReasonNotMine => 'No és meva';

  @override
  String connectToDeviceName(String deviceName) {
    return 'Connectar a $deviceName';
  }

  @override
  String get onboardingComplete => 'Complet';

  @override
  String get chatAppsShowInApp => 'Mostra aquests xats a l\'aplicació Omi';

  @override
  String nCompleted(int count) {
    return '$count completades';
  }

  @override
  String get feedbackAllGood => 'All good';

  @override
  String get syncCardUploadingTitle => 'Pujant a Omi';

  @override
  String get baselineMemory => 'Memòria base';

  @override
  String get trainFamilyProfilesDesc =>
      'Els vostres enregistraments ens ajuden a reconèixer i crear perfils per als vostres amics i família.';

  @override
  String get failedToGenerateShareLink => 'No s\'ha pogut generar l\'enllaç per compartir';

  @override
  String get onlyYouCanSeeConversation => 'Només tu pots veure aquesta conversa';

  @override
  String get popular => 'Popular';

  @override
  String get captureRecordingSeparate => 'Separa…';

  @override
  String get allTemplates => 'Totes les plantilles';

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
  String speakerTagPromptSavedAs(String name) {
    return 'Desat com a $name';
  }

  @override
  String get configureSettings => 'Configurar opcions';

  @override
  String get noRatings => 'sense valoracions';

  @override
  String resumingInCountdown(String countdown) {
    return 'Reprenent en ${countdown}s…';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 Recordat $count records';
  }

  @override
  String get clearDueDate => 'Esborra data de venciment';

  @override
  String get copy => 'Copiar';

  @override
  String get showPhoneCallButtonDesc => 'Mostra el botó de trucada telefònica a la pantalla d\'inici';

  @override
  String get appleHealthFeatureReadOnlyDesc => 'Omi mai escriu a Apple Health ni modifica les teves dades.';

  @override
  String get multipleSpeakersDescription =>
      'Sembla que hi ha múltiples parlants a la gravació. Assegureu-vos que esteu en un lloc tranquil i torneu-ho a provar.';

  @override
  String get failedToUpdateDueDate => 'No s\'ha pogut actualitzar la data de venciment';

  @override
  String get successfullyConnectedWhoop => 'Connectat correctament a Whoop!';

  @override
  String get categories => 'Categories';

  @override
  String get loadingTranscript => 'S\'està carregant la transcripció…';

  @override
  String get syncCustomSttWarningMessage =>
      'Utilitzes el teu propi proveïdor de transcripció. Sincronitzar aquests enregistraments els transcriu als servidors d\'Omi i compten per al límit de transcripció del teu pla.';

  @override
  String get newRecording => 'Nou enregistrament';

  @override
  String get transcriptionUnavailableRecordingSaved =>
      'La transcripció no està disponible — la gravació continua i l\'àudio es desa.';

  @override
  String get submittingYourApp => 'Enviant la teva aplicació…';

  @override
  String get failedToLinkCalendarEvent => 'No s\'ha pogut vincular l\'esdeveniment del calendari';

  @override
  String get paypalMeLinkHint => 'paypal.me/nik';

  @override
  String get yourInformation => 'La Teva Informació';

  @override
  String get accountDeletionInProgressSignInAgain =>
      'Aquest compte s\'està suprimint. Inicia la sessió amb un altre compte o espera uns minuts i torna-ho a provar.';

  @override
  String get on => 'On';

  @override
  String get diagnostics => 'Diagnòstics';

  @override
  String get errorCopied => 'Missatge d\'error copiat al porta-retalls';

  @override
  String get lovingOmi => 'T\'agrada Omi?';

  @override
  String get permissionDescReadMemories => 'Aquesta app pot accedir als teus records.';

  @override
  String get doNotIncludeHttpInLink => 'No incloeu http o https o www a l\'enllaç';

  @override
  String get shareRecording => 'Compartir enregistrament';

  @override
  String get memoryReviewFix => 'Corregeix';

  @override
  String get selectedPlanNotAvailable => 'El pla seleccionat no està disponible. Si us plau, torna-ho a provar.';

  @override
  String get autoCreateWhenDetected => 'Crea automàticament quan es detecti el nom';

  @override
  String get addAppSelectCapability => 'Seleccioneu almenys una capacitat per a la vostra aplicació';

  @override
  String get showPassword => 'Mostra la contrasenya';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Les converses ara finalitzaran després de $minutes minut(s) de silenci';
  }

  @override
  String get updateAvailableMessage => 'Hi ha una nova versió d\'Omi a punt, amb correccions i millores.';

  @override
  String get nameMustBeBetweenCharacters => 'El nom ha de tenir entre 2 i 40 caràcters';

  @override
  String operatorSubtitle(int count) {
    return '$count preguntes al mes';
  }

  @override
  String conversationsDeletedCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'S\'han eliminat $count converses',
      one: 'S\'ha eliminat 1 conversa',
    );
    return '$_temp0';
  }

  @override
  String get monthlyPayoutsDescription =>
      'Rebeu pagaments mensuals directament al vostre compte quan arribeu als 10 \$ de guanys';

  @override
  String get dailyScoreExplanation =>
      'La teva puntuació diària es basa en completar tasques. Completa les teves tasques per millorar la puntuació!';

  @override
  String get improveConnectionContent =>
      'Hem millorat com Omi es manté connectat al teu dispositiu. Per activar-ho, ves a la pàgina d\'informació del dispositiu, toca \"Desconnectar dispositiu\" i torna a vincular el teu dispositiu.';

  @override
  String get syncingRecordings => 'Sincronitzant enregistraments';

  @override
  String get professionProductManager => 'Gestor de producte';

  @override
  String get nameMustBeAtLeast2Characters => 'El nom ha de tenir almenys 2 caràcters';

  @override
  String get conversationTitle => 'Títol de la conversa';

  @override
  String mcpServerConnected(int count) {
    return '$count eines connectades correctament';
  }

  @override
  String get feedbackSubtitleNotUsing => 'Volem fer Omi més útil per a tu.';

  @override
  String get exportBeforeDelete =>
      'Podeu exportar les vostres dades abans d\'eliminar el compte, però un cop eliminat, no es pot recuperar.';

  @override
  String deleteTasksTitle(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Vols suprimir $count tasques?',
      one: 'Vols suprimir 1 tasca?',
    );
    return '$_temp0';
  }

  @override
  String get frequencyMaximum => 'Màxim';

  @override
  String get cancelReasonSubtitle => 'Ens pots dir per què marxes?';

  @override
  String get generatingIconStep => 'Generant icona';

  @override
  String get storeAudioDescription =>
      'Manteniu totes les gravacions d\'àudio emmagatzemades localment al telèfon. Quan estigui desactivat, només es conserven les càrregues fallides per estalviar espai.';

  @override
  String get unpairDeviceConfirmTitle => 'Desvincular el dispositiu?';

  @override
  String get phoneCallsMaybeLater => 'Potser més tard';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'S\'ha produït un error: $message';
  }

  @override
  String get yourPrivacyMattersToUs => 'La teva privadesa ens importa';

  @override
  String get collapseAction => 'Replega';

  @override
  String get friendWordOfMouth => 'Amic';

  @override
  String get deviceOnboardingVoiceReplyStatusHeadphonesDisconnected =>
      'No hi ha auriculars connectats. Omi roman en silenci fins que en connecteu algun.';

  @override
  String get connectDevice => 'Connectar dispositiu';

  @override
  String get deviceId => 'ID del dispositiu';

  @override
  String get addWordsDescription => 'Afegeix paraules que Omi hauria de reconèixer durant la transcripció.';

  @override
  String get userId => 'ID d\'Usuari';

  @override
  String evidenceCardConfirms(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Sí en $count suggeriments',
      one: 'Sí en 1 suggeriment',
    );
    return '$_temp0';
  }

  @override
  String segmentsCount(int count) {
    return '$count segments';
  }

  @override
  String get permissionsSetupTitle => 'Obteniu la millor experiència';

  @override
  String get permissionTypeAccess => 'Accés';

  @override
  String get speakerTagPromptSaveVoicesBody =>
      'L’Omi guarda una mostra de veu breu per reconèixer-los la propera vegada. Pots canviar-ho quan vulguis a Configuració.';

  @override
  String get developerApi => 'API per a desenvolupadors';

  @override
  String get chargingIssues => 'Problemes de càrrega';

  @override
  String get debugAndDiagnostics => 'Depuració i Diagnòstics';

  @override
  String get failedConnections => 'Connexions fallides';

  @override
  String get userIdCopied => 'ID d\'usuari copiat al porta-retalls';

  @override
  String get cannotReportOwnMessage => 'No podeu denunciar els vostres propis missatges.';

  @override
  String get latestVersion => 'Última versió';

  @override
  String get feedbackReasonNotHelpful => 'Poc útil o irrellevant';

  @override
  String get deletePeopleMessage =>
      'Això elimina les seves mostres de veu i no es pot desfer. Les seves intervencions en converses anteriors passen a ser parlants sense nom.';

  @override
  String get deviceOnboardingAllSetSubtitle => 'Toca una fila per revisar-la o canviar-la.';

  @override
  String get mergeConversations => 'Fusionar converses';

  @override
  String get paused => 'En pausa';

  @override
  String get updateGuide => 'Guia d\'actualització';

  @override
  String cancelBillingPeriodInfo(String date) {
    return 'El teu pla romandrà actiu fins al $date. Després, seràs traslladat a la versió gratuïta amb funcions limitades.';
  }

  @override
  String get reconnectingToInternet => 'Reconnectant a internet…';

  @override
  String get allFilesDeleted => 'Tots els enregistraments eliminats';

  @override
  String get paypalEmailHint => 'correu@exemple.com';

  @override
  String get oneWeekAgo => 'fa 1 setmana';

  @override
  String get deviceOnboardingAllSetSinglePressBadge => '1×';

  @override
  String get playbackAudioUnavailable => 'Àudio no disponible';

  @override
  String get deviceOnboardingTryDoubleTap => 'Prova-ho ara! Fes un doble toc a l\'Omi';

  @override
  String get deleteReasonPrivacy => 'Preocupacions de privadesa';

  @override
  String get cleanUpPinnedNote => 'Les persones fixades mai s\'inclouen a la neteja.';

  @override
  String get wrappedProductiveDay => 'Productiu';

  @override
  String get voiceSharedAcrossDevices => 'La veu que tries es comparteix entre el mòbil i l\'escriptori.';

  @override
  String get knowledgeGraphDeleted => 'Graf de coneixement eliminat';

  @override
  String get pressDoneToCreate => 'Premeu fet per crear';

  @override
  String get cloudStorage => 'Emmagatzematge al núvol';

  @override
  String get howDoesItWork => 'Com funciona?';

  @override
  String get submitApp => 'Enviar aplicació';

  @override
  String get searchMemories => 'Cerca records';

  @override
  String get fallNotificationTitle => 'Ai';

  @override
  String storedOnDevice(String deviceName) {
    return 'Emmagatzemat a $deviceName';
  }

  @override
  String get contactsPermissionRequired => 'Es requereix permís de contactes';

  @override
  String get reviewUpdatedSuccessfully => 'Ressenya actualitzada amb èxit 🚀';

  @override
  String get pleaseEnterPayPalMeLink => 'Si us plau, introduïu el vostre enllaç PayPal.me';

  @override
  String get notHelpful => 'No és útil';

  @override
  String get recordingsToSync => 'Enregistraments per sincronitzar';

  @override
  String get categoryUtilities => 'Utilitats';

  @override
  String get exportStarted => 'Exportació iniciada. Això pot trigar uns segons…';

  @override
  String get deviceOnboardingVoiceReplyStatusOff =>
      'Omi romandrà en silenci. Les respostes encara apareixen a l\'aplicació.';

  @override
  String get myGoal => 'El meu objectiu';

  @override
  String timeHourSingular(int count) {
    return '$count hora';
  }

  @override
  String get chatToolsManifestUrl => 'URL del manifest d\'eines de xat';

  @override
  String msgSelectFilesError(String error) {
    return 'Error en seleccionar fitxers: $error';
  }

  @override
  String connectedToApp(String appName) {
    return 'Connectat a $appName';
  }

  @override
  String get entityCorrectionHint => 'Digues a Omi què ha de corregir';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch connectat correctament!';

  @override
  String appIntegration(String appName) {
    return 'Integració de $appName';
  }

  @override
  String get cancelReasonAudioQuality => 'Qualitat d\'àudio/transcripció';

  @override
  String get invalidProviderInConfig => 'Proveïdor no vàlid a la configuració';

  @override
  String get deselectAll => 'Desselecciona-ho tot';

  @override
  String get chatAppsCodeExpiredMessage => 'Obtén un codi nou i envia\'l des de Missatges.';

  @override
  String get reviewAnswerFailed => 'No s’ha pogut desar la teva resposta. Torna-ho a provar.';

  @override
  String get categorySocial => 'Social';

  @override
  String get rating4PlusStars => '4+ estrelles';

  @override
  String get couldNotOpenSmsApp => 'No s\'ha pogut obrir l\'aplicació de SMS. Si us plau, torna-ho a provar.';

  @override
  String get chatAppsNoMessages => 'Cap missatge';

  @override
  String get wrappedCelebrity => 'FAMÓS';

  @override
  String get revokeKeyQuestion => 'Revocar la clau?';

  @override
  String timeMinsAndSecs(int mins, int secs) {
    return '$mins mins $secs segs';
  }

  @override
  String get searchContactsHint => 'Cerca contactes';

  @override
  String get showEventsWithoutParticipants => 'Mostra Esdeveniments Sense Participants';

  @override
  String get fair => 'Acceptable';

  @override
  String get tipAutoSync => 'Els enregistraments es sincronitzen automàticament';

  @override
  String get summaryCopiedToClipboard => 'Resum copiat al porta-retalls';

  @override
  String get clearSearch => 'Esborra la cerca';

  @override
  String get speakerTagPromptNotAPerson => 'No és una persona';

  @override
  String get modelLabel => 'Model';

  @override
  String deleteItemQuestion(String item) {
    return 'Eliminar $item?';
  }

  @override
  String get enterPromoCode => 'Introduïu el codi promocional';

  @override
  String get phoneNoContactsFound => 'Cap contacte trobat';

  @override
  String countRemaining(String count) {
    return '$count restants';
  }

  @override
  String get manageYourApp => 'Gestiona la teva aplicació';

  @override
  String get willSyncAutomatically => 'es sincronitzarà automàticament';

  @override
  String get promoCode => 'Codi promocional';

  @override
  String get trackPersonalGoalsOnHomepage => 'Segueix els teus objectius personals a la pàgina d\'inici';

  @override
  String get memoryHistoryPartial =>
      'Una part de l\'historial de records no està disponible. Es mostra l\'historial rebut fins ara.';

  @override
  String get sharePublicLink => 'Compartir enllaç públic';

  @override
  String get conversationTab => 'Conversa';

  @override
  String get backgroundModeDescription =>
      'Mantén l\'Omi gravant fins i tot quan l\'aplicació està completament tancada.';

  @override
  String get pairingDescOmiDevkit =>
      'Premeu el botó un cop per encendre. El LED parpellejarà en violeta en mode d\'aparellament.';

  @override
  String get callStateFailed => 'Trucada fallida';

  @override
  String get githubRepositoryUrlHint => 'Enllaç al repositori del codi font de l\'app';

  @override
  String get appIconLabel => 'App Icon';

  @override
  String get uninstallApp => 'Desinstal·la l\'aplicació';

  @override
  String get confidenceReasonNeedsVoice => 'encara no hi ha mostra de veu';

  @override
  String get couldNotLoadApiKeys => 'No s\'han pogut carregar les claus d\'API.';

  @override
  String get fetchingStableFirmware => 'Obtenint el darrer firmware estable…';

  @override
  String get onDeviceModelDownloaded => 'Descarregat';

  @override
  String get noAPIKeys => 'No hi ha claus API. Crea\'n una per començar.';

  @override
  String get phoneCallsUpsellFeature3 => 'Els destinataris veuen el teu número real, no un d\'aleatori';

  @override
  String get wrappedMovieRecs => 'Recomanacions de pel·lícules';

  @override
  String msgFilePickerError(String error) {
    return 'Error en obrir el selector de fitxers: $error';
  }

  @override
  String get professionEntrepreneur => 'Emprenedor';

  @override
  String get recent => 'Recents';

  @override
  String get permissionDescCreateMemories => 'Aquesta app pot crear nous records.';

  @override
  String get tapToComplete => 'Toca per completar';

  @override
  String vocabularyWordCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count paraules',
      one: '1 paraula',
    );
    return '$_temp0';
  }

  @override
  String get deleteSyncedFilesMessage =>
      'Aquests enregistraments ja estan sincronitzats amb el vostre telèfon. Això no es pot desfer.';

  @override
  String get cancelConsequenceSpeakers => 'No pot identificar parlants.';

  @override
  String get aiGenFailedToGenerateApp => 'No s\'ha pogut generar l\'aplicació. Torna-ho a provar.';

  @override
  String get account => 'Compte';

  @override
  String get capabilityIntegrations => 'Integracions';

  @override
  String get voiceSettingsAskToTag => 'Demana’m que etiqueti veus';

  @override
  String get chatAppsHeroTitle => 'Xateja amb l\'Omi allà on ja xategs';

  @override
  String get myApps => 'Creat per mi';

  @override
  String get deleteRecap => 'Esborra el resum';

  @override
  String get production => 'Producció';

  @override
  String get phoneRecordingBlockedByPendantBatch =>
      'Atura Transcribe Later al penjoll abans d\'enregistrar amb el telèfon.';

  @override
  String dataRateKbps(String rate) {
    return '$rate kbps';
  }

  @override
  String get createAKeyToGetStarted => 'Crea una clau per començar';

  @override
  String get pleaseSelectRating => 'Si us plau, selecciona una valoració';

  @override
  String get pdfTranscriptExport => 'Exportació de transcripció';

  @override
  String get newFolder => 'Carpeta nova';

  @override
  String get fallNotificationBody => 'Has caigut?';

  @override
  String get scopeUserChat => 'Xat de l\'usuari';

  @override
  String get tryDifferentSearchTerm => 'Proveu un terme de cerca diferent';

  @override
  String get submit => 'Envia';

  @override
  String get deviceOnboardingVoiceReplySubtitle =>
      'Quan pregunteu amb el botó, Omi pot llegir la seva resposta en veu alta.';

  @override
  String get showOnLockScreen => 'Mostra a la pantalla de bloqueig';

  @override
  String get msgMaxImagesLimit => 'Només podeu seleccionar fins a 4 imatges';

  @override
  String get wrappedOmiLifeRecap => 'Resum de vida Omi';

  @override
  String get nextButton => 'Següent';

  @override
  String disconnectAppTitle(String appName) {
    return 'Desconnectar $appName?';
  }

  @override
  String get updateReview => 'Actualitzar ressenya';

  @override
  String get noMemoriesInCategory => 'Encara no hi ha memòries en aquesta categoria';

  @override
  String get memoryDeleted => 'Record eliminat';

  @override
  String get connectOmiDevice => 'Connectar dispositiu Omi';

  @override
  String get professionSoftwareEngineer => 'Enginyer de programari';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'Etiquetar altres segments d\'aquest parlant ($selected/$total)';
  }

  @override
  String get productName => 'Nom del producte';

  @override
  String get permissionDeniedForAppleReminders => 'Permís denegat per a Apple Reminders';

  @override
  String get allMemoriesAreNowPrivate => 'Tots els records són ara privats';

  @override
  String planSetToCancelOn(String date) {
    return 'El teu pla està configurat per cancel·lar-se el $date.\nTorna a subscriure\'t ara per mantenir els teus beneficis - sense càrrec fins $date.';
  }

  @override
  String get deletePersonTitle => 'Vols suprimir la persona?';

  @override
  String deleteItemConfirmation(String item) {
    return 'No es pot desfer l\'eliminació de $item.';
  }

  @override
  String get appleHealthConnectCta => 'Connectar a Apple Health';

  @override
  String segmentsPlural(String count) {
    return '$count segments';
  }

  @override
  String get syncCardDownloadingTitle => 'S\'està baixant del teu dispositiu';

  @override
  String additionalSampleIndex(String index) {
    return 'Mostra addicional $index';
  }

  @override
  String get descriptionLabel => 'Descripció';

  @override
  String get failedToClearDueDate => 'No s\'ha pogut esborrar la data de venciment';

  @override
  String get timeout4HoursDesc => 'Finalitzar conversa després de 4 hores de silenci';

  @override
  String get noSyncedRecordingsYet => 'Encara no hi ha enregistraments sincronitzats';

  @override
  String dreamReportDropped(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count canvis anteriors omesos',
      one: '1 canvi anterior omès',
    );
    return '$_temp0';
  }

  @override
  String get claudeCode => 'Claude Code';

  @override
  String get noPendingRecordings => 'No hi ha enregistraments pendents';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'Digueu-nos com us agradaria que us adrecem. Això ajuda a personalitzar la vostra experiència Omi.';

  @override
  String get updateSummaryWithNewNames => 'Actualitza el resum amb els noms nous';

  @override
  String get setWhenConversationsAutoEnd => 'Quant espera Omi en silenci abans de tancar una conversa';

  @override
  String get successfullyConnectedGoogleTasks => 'Connectat correctament a Google Tasks!';

  @override
  String get confirmUpgrade => 'Confirmar actualització';

  @override
  String get speechToTextProviderDesc => 'Tria el servei que s\'utilitza per a la transcripció';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Error en connectar amb l\'Apple Watch: $error';
  }

  @override
  String get instagram => 'Instagram';

  @override
  String sampleNumber(int number) {
    return 'Mostra $number';
  }

  @override
  String get popularApps => 'Aplicacions populars';

  @override
  String get micGainDescSlightlyBoosted => 'Lleugerament potenciat - ús normal';

  @override
  String get promptMustBeAtLeast10Characters => 'La indicació ha de tenir almenys 10 caràcters';

  @override
  String get chatAppsEntryRowSubtitle => 'Telegram, iMessage i més';

  @override
  String get estimatedSizeLabel => 'Mida estimada';

  @override
  String get mcpServerDesc => 'Connectar assistents d\'IA a les vostres dades';

  @override
  String get disconnectHistory => 'Historial de desconnexions';

  @override
  String get downgradeLimitDelay => 'Retard de 5-7 segons';

  @override
  String get msgSelectImagesGenericError => 'Error en seleccionar imatges. Si us plau, torneu-ho a provar.';

  @override
  String get audioPlaybackUnavailable => 'El fitxer d\'àudio no està disponible per a la reproducció';

  @override
  String get byClickingConnectNow => 'En fer clic a \"Connecta ara\" accepteu el';

  @override
  String get signalStrength => 'Intensitat del senyal';

  @override
  String get tellUsPrimaryLanguage => 'Digueu-nos el vostre idioma principal';

  @override
  String get diagnosticsShareFailed => 'No s\'ha pogut compartir el diagnòstic. Torna-ho a provar.';

  @override
  String get createKeyToStart => 'Creeu una clau per començar';

  @override
  String generatedBy(String appName) {
    return 'Generat per $appName';
  }

  @override
  String shareStatsListened(String minutes) {
    return '🎧 Escoltat durant $minutes minuts';
  }

  @override
  String get getOmiDevice => 'Obtenir dispositiu Omi';

  @override
  String get newTask => 'Nova tasca';

  @override
  String get conversationPrompt => 'Indicació de conversa';

  @override
  String get otaWifiConnected => 'Connectat a la Wi-Fi';

  @override
  String get dismiss => 'Descarta';

  @override
  String get webhooks => 'Webhooks';

  @override
  String get raybanMetaCamera => 'Càmera';

  @override
  String get recapRegenerateNoConversations => 'No hi ha converses per resumir d\'aquest dia.';

  @override
  String pendantMinutesStored(int minutes) {
    return '~$minutes min emmagatzemats';
  }

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName desconnectat';
  }

  @override
  String get normal => 'Normal';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch encara no és accessible. Assegura\'t que l\'aplicació Omi estigui oberta al teu rellotge.';

  @override
  String get connectionGuide => 'Guia de connexió';

  @override
  String get syncStepProcessDesc => 'Omi converteix l\'àudio en una conversa';

  @override
  String get couldNotLoadPlans => 'No s\'han pogut carregar els plans disponibles. Si us plau, torna-ho a provar.';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '$used de $limit min utilitzats aquest mes';
  }

  @override
  String get learnMoreLink => 'més informació';

  @override
  String get unpairDeviceDialogMessage =>
      'Això desvinculará el dispositiu perquè pugui connectar-se a un altre telèfon. Hauràs d\'anar a Configuració > Bluetooth i oblidar el dispositiu per completar el procés.';

  @override
  String get authFailedToRetrieveToken =>
      'No s\'ha pogut recuperar el token de Firebase, si us plau torneu-ho a provar.';

  @override
  String get aiGenFailedToCreateApp => 'No s\'ha pogut crear l\'aplicació';

  @override
  String get appAndDeviceCopied => 'Detalls de l\'aplicació i el dispositiu copiats';

  @override
  String get noProcessedRecordings => 'Encara no hi ha enregistraments processats';

  @override
  String get transcriptTab => 'Transcripció';

  @override
  String get permissionDescReadConversations => 'Aquesta app pot accedir a les teves converses.';

  @override
  String get tryAnotherApp => 'Provar una altra aplicació';

  @override
  String get subscriptionSetToCancel => 'La teva subscripció està configurada per cancel·lar-se al final del període.';

  @override
  String chatAppsCodeExpiresIn(String time) {
    return 'El codi caduca d\'aquí a $time';
  }

  @override
  String get authFailedToSignInWithApple => 'No s\'ha pogut iniciar sessió amb Apple, si us plau torneu-ho a provar.';

  @override
  String get feedbackReasonIgnoredInstructions => 'No ha seguit les instruccions';

  @override
  String get startupFailedDetails => 'Detalls';

  @override
  String get deleteMeetingScreenshotTitle => 'Vols suprimir la captura de pantalla?';

  @override
  String get chatAppsNotConnectedMessage => 'Aquesta aplicació de xat s\'ha desconnectat.';

  @override
  String get aboutOmiApiKeys => 'Sobre les claus API d\'Omi';

  @override
  String get tiktok => 'TikTok';

  @override
  String get maxFilesLimit => 'Només podeu pujar 4 fitxers alhora';

  @override
  String get legalNotice =>
      'Avís legal: La legalitat d\'enregistrar i emmagatzemar dades de veu pot variar segons la vostra ubicació i com utilitzeu aquesta funció. És la vostra responsabilitat assegurar el compliment de les lleis i regulacions locals.';

  @override
  String get wrappedYourTopDays => 'Els teus millors dies';

  @override
  String get addMcpServer => 'Afegeix servidor MCP';

  @override
  String publicAppsCount(String count) {
    return 'Aplicacions públiques ($count)';
  }

  @override
  String get noExternalAppsHaveAccess => 'Cap aplicació externa té accés a les teves dades.';

  @override
  String get captureStarting => 'S\'està iniciant…';

  @override
  String get downloadingAudioProgress => 'Descarregant àudio';

  @override
  String get audioBytes => 'Bytes d\'àudio';

  @override
  String batteryLevelSemantics(int level) {
    return 'Bateria $level%';
  }

  @override
  String captureRecordedBy(String devices) {
    return 'Enregistrat per $devices';
  }

  @override
  String get chatAppsRepliesOnlyNote => 'L\'Omi només et respon a tu. Mai escriu primer.';

  @override
  String get hideTranscript => 'Amagar transcripció';

  @override
  String get permissionReadConversations => 'Llegir converses';

  @override
  String get installed => 'Instal·lat';

  @override
  String get paymentEnterValidAmount => 'Introduïu un import vàlid';

  @override
  String get sttLanguageOverride => 'Canvia';

  @override
  String get appInterfaceSectionTitle => 'Interfície de l\'aplicació';

  @override
  String get searchLanguages => 'Cerca idiomes';

  @override
  String get otherSource => 'Altres';

  @override
  String get pairingDescOmiGlass => 'Manteniu premut el botó lateral durant 3 segons per encendre.';

  @override
  String get signOut => 'Tancar Sessió';

  @override
  String shareStatsWords(String words) {
    return '🧠 Entès $words paraules';
  }

  @override
  String verifiedDaysAgo(int days) {
    return 'Verificat fa ${days}d';
  }

  @override
  String get captureModeLater => 'Més tard';

  @override
  String get enableMoreApps => 'Activar més aplicacions';

  @override
  String get frequencyDescBalanced => 'Suggeriments útils, unes 5–8 al dia';

  @override
  String get startYourFirstRecording => 'Comenceu la vostra primera gravació';

  @override
  String get transcriptionPausedReconnecting => 'Encara gravant — reconnectant a la transcripció…';

  @override
  String get basicPlan => 'Pla gratuït';

  @override
  String get user => 'Usuari';

  @override
  String get pinPersonDescription =>
      'Les persones fixades es mantenen a dalt de la teva llista de Persones i Neteja no les elimina.';

  @override
  String get reviewProject => 'Projecte';

  @override
  String get keyboardShortcuts => 'Dreceres de Teclat';

  @override
  String get diagnosticsFailBadge => 'Error';

  @override
  String get debugLogCleared => 'Registre de depuració netejat';

  @override
  String get errorConnectingToStripe => 'Error en connectar amb Stripe! Si us plau, torneu-ho a provar més tard.';

  @override
  String get tapPlusToStartRecording => 'Toca el botó de gravació per començar a gravar';

  @override
  String get permissionBlockedHint => 'Desactivat a Configuració. Permet-ho allà per fer-ho servir.';

  @override
  String get downloadingAudio => 'Descarregant àudio…';

  @override
  String failedToRevokeApiKey(String error) {
    return 'Error en revocar la clau API: $error';
  }

  @override
  String largeTimeGapDetected(String gap) {
    return 'S\'ha detectat un gran interval de temps ($gap)';
  }

  @override
  String get customFirmwareWarning =>
      'Un firmware personalitzat pot inutilitzar el dispositiu. Assegura\'t que és una versió vàlida del firmware d\'Omi i no el desconnectis durant l\'actualització.';

  @override
  String get wrapped2025 => 'Resum 2025';

  @override
  String get showApiKey => 'Mostra la clau d\'API';

  @override
  String get agreeAndContinue => 'Accepto i continuo';

  @override
  String get connectExternalAiTools => 'Connecta eines d\'IA externes';

  @override
  String get batteryFullyChargedTitle => 'L\'Omi està completament carregat';

  @override
  String get appReEnableFailedTitle => 'No s\'ha pogut reactivar';

  @override
  String get onboardingYourName => 'El teu nom';

  @override
  String get searchApps => 'Cerca aplicacions';

  @override
  String get weak => 'Feble';

  @override
  String get tellUsMore => 'Explica\'ns més (opcional)';

  @override
  String confidenceReasonPicked(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Triat en $count suggeriments',
      one: 'Triat en 1 suggeriment',
    );
    return '$_temp0';
  }

  @override
  String chatAppsDisconnectFooter(String app) {
    return 'Si el desconnectes, s\'esborra l\'historial que l\'Omi guarda de $app.';
  }

  @override
  String get selectAll => 'Seleccionar tot';

  @override
  String get deleteActionItemConfirmation => 'Vols eliminar aquesta tasca? Això no es pot desfer.';

  @override
  String get categoryTravel => 'Viatges';

  @override
  String get lowestRating => 'Pitjor valoració';

  @override
  String get tasksEmptyStateMessage => 'Inicia una conversa per crear una tasca.';

  @override
  String get unpairAndForget => 'Desvincular i oblidar dispositiu';

  @override
  String get listeningForAudio => 'Escoltant àudio…';

  @override
  String get processedStatus => 'Processat';

  @override
  String get wrappedTheHardPart => 'La part difícil';

  @override
  String chatAppsReplyThereAnytime(String app) {
    return 'Escriu a l\'Omi a $app quan vulguis.';
  }

  @override
  String get upgradePlan => 'Actualitzar pla';

  @override
  String get onboardingRatingPromptYes => 'Sí';

  @override
  String timeCompactMins(int count) {
    return '${count}m';
  }

  @override
  String get changeTheConversationTitle => 'Canviar el títol de la conversa';

  @override
  String get accountGroup => 'Compte';

  @override
  String get updatingYourApp => 'Actualitzant la teva aplicació';

  @override
  String get microphone => 'Micròfon';

  @override
  String get suggestQuestionsAfterConversations => 'Suggerir preguntes després de les converses';

  @override
  String get failedToTranscribeAudio => 'Error en transcriure l\'àudio';

  @override
  String get unstarConversation => 'Treu l\'estrella de la conversa';

  @override
  String get speakerTagPromptNotMe => 'No sóc jo';

  @override
  String get confidenceReasonCorrected => 'Has corregit la seva coincidència';

  @override
  String get peopleSearchPlaceholder => 'Cerca persones';

  @override
  String get syncStatusUnsupportedAudio => 'No s\'ha pogut llegir l\'àudio — no es pot sincronitzar';

  @override
  String get indentTask => 'Augmenta el sagnat';

  @override
  String get selectApp => 'Selecciona aplicació';

  @override
  String get updatePayPal => 'Actualitzar PayPal';

  @override
  String get enterNameError => 'Introduïu el vostre nom';

  @override
  String get exportAllData => 'Exportar totes les dades';

  @override
  String premiumMinsLeft(int count) {
    return '$count minuts premium restants.';
  }

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName s\'ha establert com a aplicació de resum predeterminada';
  }

  @override
  String get recordingStartedSuccessfully => 'Enregistrament iniciat correctament!';

  @override
  String get trySomethingLike => 'Proveu quelcom com…';

  @override
  String get chatAppsTryAsking => 'Prova de preguntar';

  @override
  String get categoryEntertainment => 'Entreteniment';

  @override
  String get checksForAudioFiles => 'Comprova els fitxers d\'àudio a la targeta SD';

  @override
  String get everyoneHeader => 'Tothom';

  @override
  String get clearMemoryButton => 'Esborrar memòria';

  @override
  String confidenceReasonLabeled(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'L\'has etiquetat $count vegades',
      one: 'L\'has etiquetat una vegada',
    );
    return '$_temp0';
  }

  @override
  String get selectLogFile => 'Seleccionar fitxer de registre';

  @override
  String get chatAppsTelegramStepReturn => 'Torna aquí. Confirmarem que ha funcionat.';

  @override
  String get discordMemberCount => 'Més de 8000 membres a Discord';

  @override
  String get public => 'Públic';

  @override
  String get outdentTask => 'Redueix el sagnat';

  @override
  String get statusProcessing => 'Processant';

  @override
  String get useFreePlan => 'Utilitzar pla gratuït';

  @override
  String get emailLabel => 'Correu electrònic';

  @override
  String get statusCallInProgress => 'Trucada en curs';

  @override
  String get shortcuts => 'Dreceres';

  @override
  String get reviewRecentChanges => 'Canvis recents';

  @override
  String get raybanMetaAudioOnlyExplanation =>
      'Aquesta versió d\'Omi pot utilitzar el micròfon de les vostres ulleres per Bluetooth. La captura de fotos requereix la versió per a desenvolupadors de Meta d\'Omi.';

  @override
  String get wrappedDaysActiveLabel => 'dies actius';

  @override
  String get installOmiOnAppleWatch => 'Instal·la Omi al teu\nApple Watch';

  @override
  String tasksCountLabel(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count tasques',
      one: '1 tasca',
    );
    return '$_temp0';
  }

  @override
  String get confidenceReasonVoiceReady => 'veu desada';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Vols eliminar $count element$s de la selecció?';
  }

  @override
  String get sdCardSync => 'Sincronització de targeta SD';

  @override
  String get timeout4Hours => '4 hores';

  @override
  String get chatAppsTitle => 'Aplicacions de xat';

  @override
  String get repeatPasswordLabel => 'Repeteix la contrasenya';

  @override
  String get skip => 'Saltar';

  @override
  String get phoneNoVerifiedNumbersTitle => 'Cap número verificat';

  @override
  String get connectionLost => 'Connexió perduda';

  @override
  String get photoDiscardedMessage => 'Aquesta foto s\'ha descartat perquè no era significativa.';

  @override
  String get weekdayFri => 'Dv';

  @override
  String get moveToFolder => 'Moure a la carpeta';

  @override
  String get updateNow => 'Actualitza ara';

  @override
  String get failedToUpdateActionItem => 'Error en actualitzar la tasca';

  @override
  String get transferRequiredDescription =>
      'Aquest enregistrament està emmagatzemat a la targeta SD del teu dispositiu. Transfereix-lo al teu telèfon per reproduir-lo.';

  @override
  String get checkingForUpdates => 'Comprovant actualitzacions';

  @override
  String get importTranscriptFilesDescription => 'Selecciona transcripcions SRT, VTT o TXT, o un ZIP que les contingui';

  @override
  String get listenToSpeechProfile => 'Escolta el meu perfil de veu ➡️';

  @override
  String get deleteRecapConfirmBody =>
      'Aquest resum s\'eliminarà permanentment. Les converses originals d\'aquell dia no es veuran afectades.';

  @override
  String get copyLogs => 'Copia els registres';

  @override
  String get wrappedFunniestMoment => 'Més graciós';

  @override
  String get onboardingMicrophoneRequired => 'Es requereix permís de micròfon per gravar.';

  @override
  String get whoIsItTitle => 'Qui és?';

  @override
  String dreamReportRunsLeft(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Queden $count execucions manuals avui',
      one: 'Queda 1 execució manual avui',
    );
    return '$_temp0';
  }

  @override
  String get modified => 'Modificat';

  @override
  String get actionCreateConversations => 'Crear converses';

  @override
  String get chatAssistantsTitle => 'Assistents de xat';

  @override
  String get connectionError => 'Error de connexió';

  @override
  String get chooseFromGallery => 'Triar de la galeria';

  @override
  String get summaryPrompt => 'Prompt de resum';

  @override
  String get whatWentWrong => 'Què ha fallat?';

  @override
  String get keepGoingGreat => 'Continua, ho estàs fent genial';

  @override
  String get deviceConnecting => 'S\'està connectant…';

  @override
  String get downgradeLimitBattery => '7 vegades més consum de bateria';

  @override
  String get privateMemories => 'Records privats';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get aiGenPleaseEnterDescription => 'Introdueix una descripció per a la teva aplicació';

  @override
  String get enterLiveSttWebsocket => 'Introduïu el vostre punt final WebSocket STT en directe';

  @override
  String processingOnServerProgress(int current, int total) {
    return 'Processant… $current/$total segments';
  }

  @override
  String linkedToEvent(String title) {
    return 'Vinculat a «$title»';
  }

  @override
  String get failedToSaveCheckConnection => 'Error en desar. Comprova la connexió.';

  @override
  String get deviceOnboardingContinue => 'Continua';

  @override
  String get pairedToAnotherPhone => 'Vinculat a un altre telèfon';

  @override
  String get syncingYourRecordings => 'Sincronitzant les teves gravacions';

  @override
  String get manual => 'Manual';

  @override
  String get oneMonthAgo => 'fa 1 mes';

  @override
  String get clearChatConfirm => 'Se suprimiran tots els missatges d\'aquest xat. Això no es pot desfer.';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'Tot el que faci servir \"$keyName\" perdrà l\'accés. Això no es pot desfer.';
  }

  @override
  String get vadGateDescription => 'Omet l\'àudio en silenci abans de la transcripció per reduir el cost.';

  @override
  String get dreamReportScheduled => 'Programada';

  @override
  String get audioDataReceived => 'Dades d\'àudio rebudes';

  @override
  String get pro => 'Pro';

  @override
  String get micGainDescMuted => 'El micròfon està silenciat';

  @override
  String get enableLocationDescription =>
      'Es necessita el permís d\'ubicació per trobar dispositius Bluetooth propers.';

  @override
  String get conversationTitleUpdatedSuccessfully => 'Títol de la conversa actualitzat correctament';

  @override
  String get syncStepUpload => 'Sincronitza';

  @override
  String get removeScreenshot => 'Elimina la captura de pantalla';

  @override
  String get failedToStartCall => 'No s\'ha pogut iniciar la trucada';

  @override
  String get deviceDiagnosticsUploadDescription =>
      'Review the diagnostics JSON below. It includes your device identifier, connection history, battery readings, firmware diagnostics, and BLE events. No audio or transcripts are included.';

  @override
  String get pairingTitleFieldy => 'Posa Fieldy en mode d\'aparellament';

  @override
  String get autoDeletesAfterThreeDays => 'S\'elimina automàticament després de 3 dies.';

  @override
  String get wrappedDaysActive => 'dies actius';

  @override
  String get failedToDeleteActionItem => 'Error en eliminar la tasca';

  @override
  String get connect => 'Connecta';

  @override
  String get unableToDeleteConversation => 'No es pot eliminar la conversa';

  @override
  String get clearChatAction => 'Esborrar el xat';

  @override
  String get memoryThisIphone => 'Aquest iPhone';

  @override
  String get captureCustomSttUnreachableDetail =>
      'No es pot accedir al teu servei personalitzat de veu a text. Omi guarda l\'àudio en aquest telèfon i l\'enviarà quan el servei torni. No es perd res.';

  @override
  String get feedbackGiveFeedback => 'Give feedback';

  @override
  String failedToUpdateSettings(String error) {
    return 'No s\'han pogut actualitzar els paràmetres: $error';
  }

  @override
  String get deleteRecordingConfirmation => 'Això no es pot desfer.';

  @override
  String get advancedSettings => 'Configuració avançada';

  @override
  String get transcriptionNoAudio => 'La transcripció no rep àudio';

  @override
  String deletePeopleCountAction(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Elimina $count persones',
      one: 'Elimina 1 persona',
    );
    return '$_temp0';
  }

  @override
  String get speakerSuggestionAppliesToSpeaker => 'S\'aplica a totes les línies d\'aquest parlant';

  @override
  String get deviceNotResponding => 'El dispositiu no respon. Si us plau, torna-ho a provar.';

  @override
  String get everythingSynced => 'Tot està ja sincronitzat.';

  @override
  String get onDeviceModelDownloadFailedDesc => 'No s\'ha pogut descarregar el model Whisper. Torna-ho a provar.';

  @override
  String fairUseBannerStatus(String status) {
    return 'Ús raonable: $status';
  }

  @override
  String tasksDeleteSelected(int count) {
    return 'Elimina $count tasca(ques)';
  }

  @override
  String get connectPaymentMethodInfo =>
      'Connecteu un mètode de pagament a continuació per començar a rebre pagaments per les vostres aplicacions.';

  @override
  String get conversationNotFoundOrDeleted => 'Conversa no trobada o ha estat eliminada';

  @override
  String leaveFlowStepOf(int current, int total) {
    return 'Pas $current de $total';
  }

  @override
  String get deleteTypeToConfirm => 'Escriu DELETE per confirmar';

  @override
  String get clearMemoryTitle => 'Esborrar la memòria d\'Omi';

  @override
  String get triggerConversationCreation => 'Creació de conversa';

  @override
  String get flashCustomFirmware => 'Instal·la un firmware personalitzat';

  @override
  String shareWithContactCount(int count) {
    return 'Comparteix amb $count contacte';
  }

  @override
  String get customChatbotPersonality => 'Personalitat de xatbot personalitzada';

  @override
  String get betaTesterNotice =>
      'Ets provador beta d\'aquesta aplicació. Encara no és pública. Serà pública un cop aprovada.';

  @override
  String get tomorrow => 'Demà';

  @override
  String get createdLabel => 'CREAT';

  @override
  String get searchPeople => 'Cerca persones';

  @override
  String get cancelled => 'Cancel·lat';

  @override
  String basicPlanDesc(int limit) {
    return 'El vostre pla inclou $limit minuts gratuïts al mes. Actualitzeu per tenir-ne il·limitats.';
  }

  @override
  String get editMemoryTitle => 'Edita el record';

  @override
  String get whatDoYouWantToKnow => 'Què vols saber?';

  @override
  String get confidenceFootnote =>
      'Les teves etiquetes i confirmacions compten més. Les etiquetes automàtiques valen poc fins que les confirmes.';

  @override
  String get exportFailedTryAgain => 'No s\'ha pogut exportar. Torna-ho a provar.';

  @override
  String get addAppPhotosPermissionDenied => 'Permís de fotos denegat. Permeteu l\'accés a les fotos';

  @override
  String get filterByDate => 'Filtra per data';

  @override
  String get chatAppsDoesFiles => 'Envia i rep fitxers, fotos i notes de veu';

  @override
  String get deleteKnowledgeGraphTitle => 'Eliminar graf de coneixement?';

  @override
  String get reloadingConversations => 'Recarregant converses…';

  @override
  String get aiGenPleaseGenerateAppFirst => 'Genera primer una aplicació';

  @override
  String get completeYourUpgrade => 'Completeu la vostra actualització';

  @override
  String get capturePendantDisconnectedDetail =>
      'El penjoll ha perdut la connexió amb aquest telèfon. Omi es tornarà a connectar sol quan el penjoll estigui encès i a prop. Tot el que s\'ha gravat abans és segur.';

  @override
  String get greetingMorning => 'Bon dia';

  @override
  String get thanksForYourFeedback => 'Gràcies pel teu comentari!';

  @override
  String get deleteActionItemConfirmMessage => 'Vols eliminar aquesta tasca?';

  @override
  String get syncCardProcessing => 'Processant a Omi…';

  @override
  String get chatAppsTryWeek => 'Resumeix-me la setmana en tres línies';

  @override
  String get recordWithPhoneMicSubtitle => 'Grava i transcriu amb el micròfon d\'aquest telèfon';

  @override
  String get notifications => 'Notificacions';

  @override
  String get annualPlanStartsAutomatically =>
      'El teu pla anual començarà automàticament quan acabi el teu pla mensual.';

  @override
  String get unpairDialogMessage =>
      'Això desvin cularà el dispositiu perquè es pugui connectar a un altre telèfon. Haureu d\'anar a Configuració > Bluetooth i oblidar el dispositiu per completar el procés.';

  @override
  String get pairingTitleBee => 'Posa Bee en mode d\'aparellament';

  @override
  String conversationCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count converses',
      one: '1 conversa',
    );
    return '$_temp0';
  }

  @override
  String get syncStatusWaiting => 'Esperant a sincronitzar';

  @override
  String get validWebsocketUrlRequired => 'Cal un URL WebSocket vàlid (wss://)';

  @override
  String get improveSpeechProfile => 'Millorar el vostre perfil de veu';

  @override
  String entityWaitingOn(String name) {
    return 'Esperant $name';
  }

  @override
  String get feedbackReasonTooVerbose => 'Massa llarg';

  @override
  String chatAppsChannelFooter(String app) {
    return 'Els teus xats de $app es queden a $app. L\'Omi continua sabent de què heu parlat a l\'aplicació i a les teves altres aplicacions de xat.';
  }

  @override
  String get wrappedNoDataAvailable => 'No hi ha dades disponibles';

  @override
  String deviceOnboardingAllSetReplayHint(String settings, String deviceSettings, String deviceTutorial) {
    return 'Repetiu aquesta gira en qualsevol moment a $settings › $deviceSettings › $deviceTutorial';
  }

  @override
  String get createAKey => 'Crear una clau';

  @override
  String get successfullyConnectedNotion => 'Connectat correctament a Notion!';

  @override
  String get captureMicInterruptedDetail =>
      'Una trucada o una altra app ha agafat el micròfon, així que ara Omi no pot escoltar. Omi es reprendrà sol quan el micròfon estigui lliure. Tot el que s\'ha gravat abans és segur.';

  @override
  String get onboardingScreenCaptureDenied =>
      'Permís de captura de pantalla denegat. Si us plau, concediu permís a Preferències del Sistema > Privacitat i Seguretat > Gravació de pantalla.';

  @override
  String get settingUp => 'Configurant…';

  @override
  String get frequencyLow => 'Baix';

  @override
  String get sttFilterAuto => 'Automàtic';

  @override
  String get voiceQuestionNoSpeech => 'No ho he entès — torna-ho a provar';

  @override
  String get stripeRecommendation =>
      'Si Stripe està disponible al vostre país, us recomanem molt utilitzar-lo per a pagaments més ràpids i fàcils.';

  @override
  String get confirmed => 'Confirmat!';

  @override
  String get deletePendingFilesWarning =>
      'Aquests enregistraments NO estan sincronitzats amb el vostre telèfon i es perdran permanentment. Això no es pot desfer.';

  @override
  String get removeFilter => 'Elimina el Filtre';

  @override
  String get downloadModel => 'Descarregar model';

  @override
  String get performanceReduced => 'Rendiment reduït 5-10x. Usa el mode Release.';

  @override
  String get hostRequired => 'Cal un amfitrió';

  @override
  String get alreadyBestValuePlan => 'Ja tens el pla amb millor valor. No cal fer canvis.';

  @override
  String preparingModel(String model) {
    return 'Preparant $model…';
  }

  @override
  String get sendTranscript => 'Enviar transcripció';

  @override
  String get howItWorksTitle => 'Com funciona?';

  @override
  String get filterBySpeaker => 'Filtra per parlant';

  @override
  String get addAppSubmittedSuccess => 'Aplicació enviada correctament 🚀';

  @override
  String olderIphoneModelDetected(String model) {
    return 'Model detectat: $model (anterior a l\'iPhone XS). El reconeixement al dispositiu pot ser més lent.';
  }

  @override
  String get chatAppsWhatsAppTitle => 'WhatsApp arribarà aviat';

  @override
  String get syncingDeveloperSettings => 'S\'està sincronitzant la configuració de desenvolupador…';

  @override
  String get enterWifiPassword => 'Introduïu la contrasenya WiFi';

  @override
  String get failedToUpdateBaselineStatus => 'No s\'ha pogut actualitzar aquest record. Torna-ho a provar.';

  @override
  String get joinCommunity => 'Uniu-vos a la comunitat!';

  @override
  String get helpOrInquiries => 'Ajuda o consultes?';

  @override
  String get enable => 'Activar';

  @override
  String get deviceForgottenMessage => 'Dispositiu oblidat';

  @override
  String diagnosticsSincePairingSummary(int drops, int failed) {
    return 'Des de l\'aparellament: $drops talls, $failed connexions fallides.';
  }

  @override
  String confidenceSummaryConfirmed(String name) {
    return 'Omi reconeix la veu de $name i tu ho has confirmat.';
  }

  @override
  String migratingToProtection(String level) {
    return 'Migrant a protecció $level…';
  }

  @override
  String get managePlan => 'Gestionar pla';

  @override
  String get synced => 'Sincronitzat';

  @override
  String get failedToMoveConversations => 'No s\'han pogut moure les converses';

  @override
  String get monthMar => 'Març';

  @override
  String get timePM => 'PM';

  @override
  String get debugLogsAutoDelete => 'S\'eliminen automàticament després de 3 dies.';

  @override
  String get linkedIn => 'LinkedIn';

  @override
  String speakerLabelVoiceDetail(String state, String name) {
    String _temp0 = intl.Intl.selectLogic(
      state,
      {
        'learned': 'Omi reconeixerà $name la propera vegada.',
        'pending': 'Això triga uns segons.',
        'disabled': 'Activa el desament de veus a Configuració perquè Omi pugui reconèixer $name.',
        'other': 'Omi necessita més parla clara de $name i continuarà intentant-ho.',
      },
    );
    return '$_temp0';
  }

  @override
  String get authUnexpectedError => 'Error inesperat en iniciar sessió, si us plau torneu-ho a provar';

  @override
  String disconnectAppMessage(String appName) {
    return 'Pots tornar a connectar $appName en qualsevol moment.';
  }

  @override
  String get pendantPausedResumesWhenYouFinish => 'Penjoll en pausa · es reprèn quan acabis';

  @override
  String get sendToSupport => 'Send to support';

  @override
  String get fairUseBudgetExhausted => 'Daily transcription limit reached';

  @override
  String evidenceAutoConfirmed(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Has confirmat $count etiquetes automàtiques',
      one: 'Has confirmat 1 etiqueta automàtica',
    );
    return '$_temp0';
  }

  @override
  String get otaWifiConnecting => 'S\'està connectant a la Wi-Fi…';

  @override
  String starFilterLabel(int count) {
    return '$count estrella';
  }

  @override
  String get disconnectDevice => 'Desconnecta el dispositiu';

  @override
  String get installsCount => 'Instal·lacions';

  @override
  String captureStatusWithSource(String status, String source) {
    return '$status · $source';
  }

  @override
  String get pairingTitleOmiGlass => 'Enceneu Omi Glass';

  @override
  String get setActive => 'Establir com a actiu';

  @override
  String get showShortConversations => 'Mostrar converses curtes';

  @override
  String get reviewNotSure => 'No n’estic segur';

  @override
  String msgCameraAccessError(String error) {
    return 'Error en accedir a la càmera: $error';
  }

  @override
  String get quickActionAskOmi => 'Pregunta-li qualsevol cosa a l\'Omi';

  @override
  String get dreamReportTimedOut => 'S\'ha aturat en arribar al límit de temps';

  @override
  String get chooseYourLanguage => 'Trieu el vostre idioma';

  @override
  String get unableToDetermineFirmwareVersion => 'No s\'ha pogut determinar la versió actual del firmware';

  @override
  String get addAppEnterConversationPrompt => 'Introduïu una sol·licitud de conversa per a la vostra aplicació';

  @override
  String get readScope => 'Lectura';

  @override
  String get selectALanguage => 'Seleccioneu un idioma';

  @override
  String get otherTemplates => 'Altres plantilles';

  @override
  String get speechProfileTopicGoal => 'Quin és el teu objectiu a llarg termini?';

  @override
  String get rayBanMetaMicPickerTitle => 'Tria el micròfon de les Ray-Ban Meta';

  @override
  String meetingNotesSubject(String title) {
    return 'Notes: $title';
  }

  @override
  String get feedbackTitleMissingFeatures => 'Quines funcions trobes a faltar?';

  @override
  String get modelReady => 'Model llest';

  @override
  String todayAtTime(String time) {
    return 'Avui a les $time';
  }

  @override
  String get deleteAccountPermanently => 'Eliminar compte permanentment';

  @override
  String get updateStripeDetails => 'Actualitzar els detalls de Stripe';

  @override
  String get voiceResponseHeadphonesOnly => 'Només auriculars';

  @override
  String get deviceOnboardingEndConversation => 'Finalitza la conversa';

  @override
  String openingApp(String appName) {
    return 'Obrint $appName…';
  }

  @override
  String get submitAppPublicDescription =>
      'La teva aplicació serà revisada i feta pública. Pots començar a utilitzar-la immediatament, fins i tot durant la revisió!';

  @override
  String connectToAppTitle(String appName) {
    return 'Connectar a $appName';
  }

  @override
  String get timeout10MinutesDesc => 'Finalitzar conversa després de 10 minuts de silenci';

  @override
  String get googleCalendar => 'Google Calendar';

  @override
  String get initializing => 'Inicialitzant…';

  @override
  String get noMessagesYet => 'Encara no hi ha missatges!\nPer què no comenceu una conversa?';

  @override
  String get chatAppsLoadFailed => 'No s\'han pogut carregar les apps de xat. Torna-ho a provar.';

  @override
  String get tasksLater => 'Més tard';

  @override
  String get speakerLabelUnknown => 'Desconegut';

  @override
  String get appTitle => 'Omi';

  @override
  String get noModelDownloadRequired => 'S\'usarà el motor de veu natiu del dispositiu. No cal descarregar cap model.';

  @override
  String get authenticationFailed => 'L\'autenticació ha fallat. Si us plau, torneu-ho a provar.';

  @override
  String get defaultRepoSaved => 'Repositori per defecte desat';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'Error en seleccionar la miniatura: $error';
  }

  @override
  String get captureRecordingSeparateTitle => 'Vols separar aquest enregistrament?';

  @override
  String get back => 'Enrere';

  @override
  String get preparingAudio => 'Preparant àudio';

  @override
  String get noAutoMemories => 'Encara no hi ha records extrets automàticament';

  @override
  String get allDone => 'Tot fet!';

  @override
  String get msgReadingMemories => 'Llegint els teus records…';

  @override
  String get worksOnDesktop => 'Funciona a l\'escriptori';

  @override
  String get displayOptions => 'Opcions de Visualització';

  @override
  String get installApp => 'Instal·la l\'aplicació';

  @override
  String get stop => 'Atura';

  @override
  String get grantPermissions => 'Concedir permisos';

  @override
  String get at => 'a';

  @override
  String get checkInternetConnection => 'Si us plau, comprova la teva connexió a Internet';

  @override
  String get actionItems => 'Tasques';

  @override
  String get nextDay => 'Dia següent';

  @override
  String get syncStatusFailed => 'Ha fallat — toca Reintenta';

  @override
  String get saveCredentials => 'Desa les credencials';

  @override
  String get peopleRecent => 'Recents';

  @override
  String get bringYourOwn => 'Utilitzeu el vostre propi';

  @override
  String get cancelConsequenceBattery => '7x més consum de bateria (processament al dispositiu)';

  @override
  String get copyMessage => 'Copia el missatge';

  @override
  String get annualSubscriptionStarts =>
      'La teva subscripció anual de 12 mesos començarà automàticament després del cobrament';

  @override
  String get deleteImportedData => 'Eliminar dades importades';

  @override
  String get chatLimitReachedUpgrade => 'Límit de xat assolit. Actualitza per a més missatges.';

  @override
  String get whatsNew => 'Què hi ha de nou';

  @override
  String get omiTraining => 'Entrenament Omi';

  @override
  String get wrappedMyBuddies => 'Els meus amics';

  @override
  String get keepRecording => 'Continua enregistrant';

  @override
  String get suggestedEvent => 'Suggerit';

  @override
  String get name => 'Nom';

  @override
  String get screenRecordingDescription =>
      'Omi necessita permís de gravació de pantalla per capturar l\'àudio del sistema de les vostres reunions basades en el navegador.';

  @override
  String get improveConnectionTitle => 'Millorar la connexió';

  @override
  String get syncProcessingBackgroundHint => 'Això continua en segon pla — pots sortir d\'aquesta pantalla.';

  @override
  String get wrappedYourTopDaysBadge => 'Els teus millors dies';

  @override
  String get noPeopleYet => 'Encara no hi ha persones';

  @override
  String summaryGeneratedForDate(String date) {
    return 'Resum generat per a $date';
  }

  @override
  String get searchTranscriptOrSummary => 'Cerca a la transcripció o el resum';

  @override
  String get memoryDetailsTitle => 'Record';

  @override
  String get chatPersonality => 'Personalitat del xat';

  @override
  String get release => 'Allibera';

  @override
  String removeVocabularyWord(String word) {
    return 'Elimina $word';
  }

  @override
  String get onboardingLanguage => 'Idioma';

  @override
  String get wrappedYouDidItEmoji => 'Ho vas fer! 🎉';

  @override
  String get syncInProgress => 'Sincronització en curs';

  @override
  String get wrappedCouldntStopTalkingAbout => 'No podia parar de parlar de';

  @override
  String get chooseSummarizationApp => 'Trieu l\'aplicació de resum';

  @override
  String etaLabel(String time) {
    return 'Temps estimat: $time';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'Si fas $item públic, pot ser utilitzat per tothom';
  }

  @override
  String get phoneCallsUpsellFeature2 => 'Resums automàtics de trucades i tasques';

  @override
  String get freemiumLimitsIntro =>
      'Omi és gratuït, però la versió gratuïta té límits que afecten la teva experiència:';

  @override
  String get nameLabel => 'Nom';

  @override
  String get shortConversationThresholdSubtitle =>
      'Les converses més curtes que això s\'amagaran tret que s\'activi a dalt';

  @override
  String get captureMicInUseElsewhere => 'Una altra app fa servir el micròfon';

  @override
  String get selectChatAssistant => 'Seleccionar assistent de xat';

  @override
  String get transferRequired => 'Es requereix transferència';

  @override
  String get unlimitedChatThisMonth => 'Missatges de xat il·limitats aquest mes';

  @override
  String get backgroundModeUnavailable =>
      'El mode en segon pla no està disponible perquè no hi ha cap dispositiu compatible connectat. Connecta un dispositiu Omi, OpenGlass o Friend Pendant per utilitzar aquesta funció.';

  @override
  String get importConfiguration => 'Importar configuració';

  @override
  String get e2eeTradeoff1 =>
      '• Algunes funcions com les integracions d\'aplicacions externes poden estar desactivades.';

  @override
  String get chatAppsCodeExpiredTitle => 'Aquest codi ha caducat';

  @override
  String get responseSchema => 'Esquema de resposta';

  @override
  String get wrappedBestMoments => 'Millors moments';

  @override
  String get noAppsExternalAccess => 'Cap aplicació instal·lada té accés extern a les vostres dades.';

  @override
  String modelReadyWithName(String model) {
    return 'Model llest ($model)';
  }

  @override
  String get appDisabledWebhookFailures =>
      'El seu endpoint va fallar durant 72 hores seguides, així que es van aturar els enviaments.';

  @override
  String reviewConversationCount(int count) {
    return 'Converses: $count';
  }

  @override
  String get reviewChangesLoadFailed => 'No s’han pogut carregar els canvis recents.';

  @override
  String get reviewOpenConversation => 'Conversa';

  @override
  String get voiceRecordingFound => 'Gravació trobada';

  @override
  String durationAgo(String duration) {
    return 'fa $duration';
  }

  @override
  String get onboardingWelcomeToOmi => 'Benvingut a Omi';

  @override
  String get deleteActionItemConfirmTitle => 'Eliminar tasca';

  @override
  String get importantBillingInfo => 'Informació de facturació important:';

  @override
  String get pending => 'Pendent';

  @override
  String get onboardingRatingPromptTitle => 'T\'agrada Omi?';

  @override
  String get savePayPalDetails => 'Desar els detalls de PayPal';

  @override
  String appDisabledLastError(String error) {
    return 'Últim error: $error.';
  }

  @override
  String get iveInstalledAndOpenedTheApp => 'He instal·lat i obert l\'aplicació';

  @override
  String get pricePlaceholder => '0,00';

  @override
  String get triggerTranscriptProcessed => 'Transcripció processada';

  @override
  String get decisions => 'Decisions';

  @override
  String get conversationProcessingFailedMessage => 'No s\'ha pogut processar aquesta conversa.';

  @override
  String get continueText => 'Continuar';

  @override
  String get signInWithGoogle => 'Iniciar sessió amb Google';

  @override
  String firmwareFlashTarget(String deviceName) {
    return 'Dispositiu: $deviceName';
  }

  @override
  String get deleteYourAccountAndAllData => 'Elimina el compte i totes les dades';

  @override
  String get provider => 'Proveïdor';

  @override
  String get people => 'Persones';

  @override
  String get perMonth => '/ Mes';

  @override
  String get monthFeb => 'Febr';

  @override
  String get fridayAbbr => 'Dv';

  @override
  String get thankYouForFeedback => 'Gràcies pels teus comentaris!';

  @override
  String get usageBestYear => 'Best year';

  @override
  String get addAppFillRequiredFields => 'Ompliu correctament tots els camps obligatoris';

  @override
  String get deviceOnboardingVoiceReplyOffDescription => 'Les respostes es mantenen a la pantalla. No es parla res.';

  @override
  String get logs => 'Registres';

  @override
  String get exportConversations => 'Exportar converses';

  @override
  String get memoryReviewDropped => 'Eliminat dels teus records.';

  @override
  String get appearanceLight => 'Clar';

  @override
  String get moneyEarned => 'Diners guanyats';

  @override
  String get permissionsAndTriggers => 'Permisos i activadors';

  @override
  String get discardRecordingTitle => 'Vols descartar l\'enregistrament?';

  @override
  String get wrappedMinutesLabel => 'minuts';

  @override
  String get voiceRestoredToast => 'Omi pot tornar a preguntar per aquesta veu';

  @override
  String get locationAccess => 'Accés a la ubicació';

  @override
  String get deleteAllMemories => 'Eliminar tots els records';

  @override
  String get deleteAccountTitle => 'Eliminar compte';

  @override
  String get selectFile => 'Seleccionar un fitxer';

  @override
  String get answerTheCallFrom => 'Respon la trucada de';

  @override
  String get unpairDeviceDialogTitle => 'Desvincula el dispositiu';

  @override
  String exportedToPlatform(String platform) {
    return 'Exportat a $platform';
  }

  @override
  String syncCardDownloadPercent(int percent) {
    return '$percent%';
  }

  @override
  String get deviceOnboardingVoiceReplyPreviewPlaying => 'S\'està reproduint la teva última resposta...';

  @override
  String get fromSd => 'Des de SD';

  @override
  String get goodSampleInstructions =>
      '1. Assegureu-vos que esteu en un lloc tranquil.\n2. Parleu clarament i naturalment.\n3. Assegureu-vos que el dispositiu estigui en la seva posició natural al coll.\n\nUn cop creat, sempre podeu millorar-lo o fer-ho de nou.';

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
      'Per destacar una conversa, obriu-la i toqueu la icona d\'estrella a la capçalera.';

  @override
  String get pairingTitleOmiDevkit => 'Posa Omi DevKit en mode d\'aparellament';

  @override
  String sttPrimaryLanguageUnsupported(String language, String fallback) {
    return 'Aquest proveïdor no admet $language, així que utilitza $fallback.';
  }

  @override
  String get premiumMinutesMonth =>
      '300 minuts prèmium al mes. Tria «Al dispositiu» per a una transcripció gratuïta il·limitada. ';

  @override
  String get firmwareEnsureBattery => 'Assegura\'t que el teu dispositiu té un 15% de bateria.';

  @override
  String get actionItemDescriptionHint => 'Què cal fer?';

  @override
  String get yourScore => 'La teva puntuació';

  @override
  String failedToStartAuth(String appName) {
    return 'No s\'ha pogut iniciar l\'autenticació de $appName';
  }

  @override
  String get actionReadTasks => 'Llegir tasques';

  @override
  String get keepSyncing => 'Continuar sincronitzant';

  @override
  String get overdue => 'Endarrerit';

  @override
  String get chatAppsProblemUnavailable => 'Les aplicacions de xat encara no estan disponibles per al teu compte.';

  @override
  String get tapSyncToStart => 'Toqueu Sincronitzar per començar';

  @override
  String get emptyDoneMessage => 'Encara no hi ha elements completats';

  @override
  String get recordOptionsTip => 'Consell: toca la fletxa del botó de gravació per gravar una trucada.';

  @override
  String get setupQuestionProfession => '1. A què et dediques?';

  @override
  String get deviceInfoSection => 'Informació del dispositiu';

  @override
  String get teachOmiYourVoice => 'Ensenya a Omi la teva veu';

  @override
  String get addYourFirstMemory => 'Afegeix el teu primer record';

  @override
  String get priceLabel => 'PREU';

  @override
  String get high => 'Alt';

  @override
  String estimatedSizeWithValue(String size) {
    return 'Mida estimada: ~$size MB';
  }

  @override
  String cleanUpUnsureCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count persones de qui Omi no està segur',
      one: '1 persona de qui Omi no està segur',
    );
    return '$_temp0';
  }

  @override
  String get makeAllMemoriesPrivate => 'Fer privats tots els records';

  @override
  String get raybanMetaWaitingForMetaAI => 'Acabeu de connectar a l\'app Meta AI i torneu aquí.';

  @override
  String get revokeAuthorization => 'Revocar autorització';

  @override
  String get confidenceToReachConfirmed => 'Per arribar a Confirmat';

  @override
  String get syncCardRateLimited => 'S\'ha assolit el límit d\'ús just — la sincronització es reprendrà automàticament';

  @override
  String get reviewStopClip => 'Atura el clip';

  @override
  String get chatAppsWhatOmiDoes => 'Què fa l\'Omi a les aplicacions de xat';

  @override
  String get resume => 'Reprèn';

  @override
  String get defaultSpace => 'Espai per defecte';

  @override
  String get multipleSpeakersDetected => 'Múltiples parlants detectats';

  @override
  String evidenceAutoCorrected(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Has canviat $count etiquetes automàtiques a una altra persona',
      one: 'Has canviat 1 etiqueta automàtica a una altra persona',
    );
    return '$_temp0';
  }

  @override
  String get voiceMatchPossible => 'Coincidència possible';

  @override
  String get checkBoxToConfirm =>
      'Marqueu la casella per confirmar que enteneu que eliminar el vostre compte és permanent i irreversible.';

  @override
  String get quicklyPopulateResponse => 'Emplenar ràpidament amb un format de resposta de proveïdor conegut';

  @override
  String get monthJul => 'Jul';

  @override
  String get failedToInitializeCallService => 'No s\'ha pogut inicialitzar el servei de trucades';

  @override
  String get connectAction => 'Connecta';

  @override
  String get onDeviceModelDeleted => 'Model eliminat';

  @override
  String get micGainDescNeutral => 'Neutre - enregistrament equilibrat';

  @override
  String get chatOfflineHint => 'No tens connexió. Torna\'t a connectar per enviar missatges.';

  @override
  String get onboardingLocationGrantInSettings =>
      'Si us plau, concediu permís d\'ubicació a Configuració > Privacitat i Seguretat > Serveis d\'ubicació';

  @override
  String get invalidSetupInstructionsUrl => 'URL d\'instruccions de configuració no vàlida';

  @override
  String get msgCameraPermissionDenied => 'Permís de càmera denegat. Si us plau, permeteu l\'accés a la càmera';

  @override
  String get dataAndPrivacy => 'Dades i privadesa';

  @override
  String get deviceNotCompatible => 'Dispositiu no compatible';

  @override
  String get pairingDescAppleWatch =>
      'Instal·leu i obriu l\'aplicació Omi al vostre Apple Watch, després toqueu Connectar a l\'aplicació.';

  @override
  String get speechProfileTopicLocation => 'On vius?';

  @override
  String get makeAllPrivate => 'Fer tots els records privats';

  @override
  String get capabilityNotification => 'Notificació';

  @override
  String get captureAudioSavedTranscribesLater => 'Àudio desat, es transcriurà més tard';

  @override
  String get wrappedTopPhrases => 'Top 5 frases';

  @override
  String get transcribeLaterPaused => 'En pausa — no s\'està gravant àudio';

  @override
  String get deviceOnboardingTurnOnTitle => 'Engega';

  @override
  String get keyNamePlaceholder => 'p. ex., La meva integració';

  @override
  String get languageTitle => 'Idioma';

  @override
  String get statusVerifiedLabel => 'Verificat';

  @override
  String get storageLocationPhoneMemory => 'Telèfon (Memòria)';

  @override
  String get you => 'Tu';

  @override
  String get listeningTranscriptWillAppear => 'Escoltant… aquí apareixerà una transcripció.';

  @override
  String get askSuggestNotice => 'Què ha notat l\'Omi?';

  @override
  String get safelyBackedUp => 'Converses creades';

  @override
  String get folderName => 'Nom de la carpeta';

  @override
  String get categorySocialEntertainment => 'Social i entreteniment';

  @override
  String speechProfileOwnerTitle(String name) {
    return 'Perfil de veu de $name';
  }

  @override
  String get reviewAddedSuccessfully => 'Ressenya afegida amb èxit 🚀';

  @override
  String get fairUseSpeechUsage => 'Ús de la parla';

  @override
  String get visibilitySubtitle => 'Controleu quines converses apareixen a la vostra llista';

  @override
  String get wrappedWinLabelUpper => 'VICTÒRIA';

  @override
  String timeCompactMinsAndSecs(int mins, int secs) {
    return '${mins}m ${secs}s';
  }

  @override
  String get phoneCallsUpsellSubtitle =>
      'Fes trucades a través d\'Omi i obtin transcripció en temps real, resums automàtics i més.';

  @override
  String get sessionExpiredSignInAgain => 'La sessió ha caducat — torna a iniciar la sessió.';

  @override
  String get newPersonEllipsis => 'Persona nova…';

  @override
  String get sharePeriodToday => 'Avui, Omi ha:';

  @override
  String get premiumMinutesInfo =>
      '300 minuts prèmium al mes. Tria «Al dispositiu» per a una transcripció gratuïta il·limitada.';

  @override
  String get notConnectedStatus => 'No connectat';

  @override
  String get authorizeSavingRecordings => 'Autoritzar desar enregistraments';

  @override
  String get thinking => 'Pensant';

  @override
  String get unpairDialogTitle => 'Desvincular dispositiu';

  @override
  String get batteryFullyChargedBody => 'El teu dispositiu Omi està completament carregat. Pots desconnectar-lo!';

  @override
  String get speakerTagPromptRejectedToast => 'Etiqueta eliminada';

  @override
  String get phone => 'Telèfon';

  @override
  String get chatAppsVoiceNotes => 'Notes de veu';

  @override
  String get deviceOnboardingStatusDisconnected => 'Desconnectat';

  @override
  String get debugModeDetected => 'Mode de depuració detectat';

  @override
  String get failedToSaveDefaultRepo => 'No s\'ha pogut desar el repositori per defecte';

  @override
  String get showCompletedTasks => 'Mostra les completades';

  @override
  String deviceStorageUsedOfTotal(String used, String total) {
    return '$used de $total utilitzat';
  }

  @override
  String get recordingsNotSynced => 'Teniu enregistraments que encara no s\'han sincronitzat.';

  @override
  String get performanceWarning => 'Advertència de rendiment';

  @override
  String get submitAppPrivateDescription =>
      'La teva aplicació serà revisada i feta disponible per a tu de manera privada. Pots començar a utilitzar-la immediatament, fins i tot durant la revisió!';

  @override
  String get copyTranscript => 'Copiar transcripció';

  @override
  String get providing => 'Proporcionant';

  @override
  String get findDeviceNoneMessage => 'Engega\'l i mantén-lo a prop del telèfon.';

  @override
  String get wrappedLetsHitRewind => 'Rebobinem el teu';

  @override
  String deviceRamBelowMinimum(String ram) {
    return 'RAM detectada: $ram GB. Mínim recomanat: 4 GB.';
  }

  @override
  String get addOrChangePaymentMethod => 'Afegeix o canvia el teu mètode de pagament';

  @override
  String get omiAppName => 'Omi';

  @override
  String get enableBluetooth => 'Activar Bluetooth';

  @override
  String get privacyNotice => 'Avís de privacitat';

  @override
  String get manufacturer => 'Fabricant';

  @override
  String get byContinuingYouAgree => 'En continuar, acceptes els nostres ';

  @override
  String dataProtectedWithSettings(String level) {
    return 'Les teves dades ara estan protegides amb la configuració $level.';
  }

  @override
  String get selectSpaceInWorkspace => 'Seleccioneu un espai al vostre espai de treball';

  @override
  String get copyKey => 'Copia la clau';

  @override
  String get password => 'Contrasenya';

  @override
  String estimatedSize(String size) {
    return 'Mida estimada: ~$size MB';
  }

  @override
  String monthsFreeBadge(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count mesos gratis',
      one: '1 mes gratis',
    );
    return '$_temp0';
  }

  @override
  String get chatAppsNotAvailableYet => 'Encara no disponible';

  @override
  String estimatedTimeRemaining(String time) {
    return 'Estimat: $time restants';
  }

  @override
  String get syncCardBackendBusy =>
      'Els servidors d\'Omi estan saturats — els enregistraments se sincronitzaran quan hi hagi capacitat disponible';

  @override
  String get speakerTagPromptTitle => 'Ajuda l’Omi a reconèixer veus';

  @override
  String get playFromHere => 'Reprodueix des d\'aquí';

  @override
  String get entityProject => 'Projecte';

  @override
  String get permissionNotGrantedYet =>
      'Permís encara no atorgat. Assegureu-vos que heu permès l\'accés al micròfon i heu tornat a obrir l\'aplicació al vostre rellotge.';

  @override
  String get e2eeTradeoff2 => '• Si perds la teva contrasenya, les teves dades no es poden recuperar.';

  @override
  String get exportConfiguration => 'Exportar configuració';

  @override
  String get recordWith => 'Grava amb';

  @override
  String get greetingEvening => 'Bona nit';

  @override
  String deletePhoneNumberConfirm(String phoneNumber) {
    return 'Eliminar $phoneNumber?';
  }

  @override
  String get deviceOnboardingAskQuestionTitle => 'Fes una pregunta a l\'Omi';

  @override
  String get appNamePlaceholder => 'La meva aplicació fantàstica';

  @override
  String get tapPlayToResume => 'Toqueu reproducció per reprendre';

  @override
  String get dueDate => 'Data de venciment';

  @override
  String get appearanceSystem => 'Sistema';

  @override
  String get invalidEmailError => 'Introduïu un correu electrònic vàlid';

  @override
  String get highResourceUsage => 'Alt ús de recursos';

  @override
  String get voiceAndPeople => 'Veu i Persones';

  @override
  String get customizationSection => 'Personalització';

  @override
  String get failedToCancelSubscription => 'No s\'ha pogut cancel·lar la subscripció. Torna-ho a provar.';

  @override
  String get later => 'Més tard';

  @override
  String get wrappedTasksGenerated => 'tasques generades';

  @override
  String get personalizingExperience => 'Personalitzant la teva experiència…';

  @override
  String get syncAvailable => 'Sincronització disponible';

  @override
  String chatGreeting(String name) {
    return 'Hola $name, pregunta el que vulguis';
  }

  @override
  String get phoneCallSettingsTitle => 'Configuracio de trucades';

  @override
  String get remoteDeviceTerminated => 'El dispositiu remot ha finalitzat';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'Error en obrir el selector de fitxers: $message';
  }

  @override
  String get actionItemDeleted => 'Tasca eliminada';

  @override
  String get couldNotLoadMemories => 'No s\'han pogut carregar els records';

  @override
  String get generateDescription => 'Genera una descripció';

  @override
  String get privateLabel => 'Privada';

  @override
  String get deviceOnboardingMuteUnmute => 'Silencia / Activa';

  @override
  String get day => 'Dia';

  @override
  String get submitAppQuestion => 'Enviar aplicació?';

  @override
  String get usageWords => 'Words';

  @override
  String get failedToConnectClickUp => 'No s\'ha pogut connectar a ClickUp';

  @override
  String get selectZipFileToImport => 'Selecciona el fitxer .zip per importar!';

  @override
  String timeSecsPlural(int count) {
    return '$count segs';
  }

  @override
  String get wasThisHelpful => 'Ha estat útil?';

  @override
  String get msgLearningMemories => 'Aprenent dels teus records…';

  @override
  String get onboardingScreenCaptureRequired =>
      'Es requereix permís de captura de pantalla per gravar àudio del sistema.';

  @override
  String evidenceManualLabels(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Etiquetat per tu en $count converses',
      one: 'Etiquetat per tu en 1 conversa',
    );
    return '$_temp0';
  }

  @override
  String get transferCancelled => 'Transferència cancel·lada';

  @override
  String get sttModelSpeed => 'Velocitat';

  @override
  String get fairUsePolicy => 'Ús raonable';

  @override
  String get phoneStorage => 'Emmagatzematge del telèfon';

  @override
  String get deviceOnboardingEndConversationDesc => 'Desa i finalitza la conversa actual';

  @override
  String get proceedAnyway => 'Continuar igualment';

  @override
  String get overview => 'Visió general';

  @override
  String get deviceOnboardingGoodJob => 'Ben fet!';

  @override
  String get delete => 'Elimina';

  @override
  String get connectAiAssistantsToYourData => 'Connecta assistents IA a les teves dades';

  @override
  String get startFresh => 'Comença de nou';

  @override
  String get deviceOnboardingStatusConnectedDone => 'Connectat!';

  @override
  String get filterInstalled => 'Instal·lades';

  @override
  String get mergingStatus => 'Fusionant…';

  @override
  String get successfullyConnected => 'Connectat amb èxit!';

  @override
  String get permissionCreateConversations => 'Crear converses';

  @override
  String get cancelConsequencePhoneCalls => 'Sense transcripció de trucades en temps real';

  @override
  String get feedbackReasonSummaryOther => 'Something else';

  @override
  String get oAuth => 'OAuth';

  @override
  String get notEnoughSpace => 'Advertència: No hi ha prou espai!';

  @override
  String get feedbackTitleTooExpensive => 'Quin preu funcionaria per a tu?';

  @override
  String get secureEncryption => 'Xifratge segur';

  @override
  String get rating2PlusStars => '2+ estrelles';

  @override
  String get chatAppsOpenMessagesAgain => 'Torna a obrir Missatges';

  @override
  String fairUseBudgetResetsAt(String time) {
    return 'Resets $time';
  }

  @override
  String get addVocabularyDescription => 'Afegeix paraules que Omi hauria de reconèixer durant la transcripció.';

  @override
  String get whisperModelSizeMedium => 'Mitjà';

  @override
  String get wrappedMyBuddiesLabel => 'ELS MEUS AMICS';

  @override
  String get memoryGraph => 'Graf de memòries';

  @override
  String get paste => 'Enganxar';

  @override
  String get failedToRefreshGitHubStatus => 'No s\'ha pogut actualitzar l\'estat de connexió de GitHub.';

  @override
  String get feedbackSubtitleMissingFeatures => 'Sempre estem construint — això ens ajuda a prioritzar.';

  @override
  String get itemApp => 'Aplicació';

  @override
  String get pairingDescFriendPendant =>
      'Premeu el botó del penjoll per encendre\'l. Entrarà en mode d\'aparellament automàticament.';

  @override
  String get appDisabledGeneric => 'La va desactivar Omi.';

  @override
  String get noSummaryForApp =>
      'No hi ha resum disponible per a aquesta aplicació. Prova una altra aplicació per obtenir millors resultats.';

  @override
  String get deleteProcessed => 'Eliminar processats';

  @override
  String get chatBlockOpenInGoals => 'Obre a Objectius';

  @override
  String get micGainDescModerate => 'Silenciós - per soroll moderat';

  @override
  String get defaultRepository => 'Repositori per defecte';

  @override
  String get statusPending => 'Pendent';

  @override
  String get referralProgram => 'Programa de recomanacions';

  @override
  String get authFailedToLinkApple => 'No s\'ha pogut vincular amb Apple, si us plau torneu-ho a provar.';

  @override
  String modelNameWithFile(String model) {
    return 'Model: $model';
  }

  @override
  String get deviceOnboardingTurnOnSubtitle => 'Prem el botó per tornar-lo a engegar';

  @override
  String get previewAndScreenshots => 'Vista prèvia i captures de pantalla';

  @override
  String get recordingOfflineTranscriptWillCatchUp =>
      'Gravant sense connexió — la transcripció s\'actualitzarà quan tornis a estar en línia.';

  @override
  String get accessibilityDescription =>
      'Omi necessita permís d\'accessibilitat per detectar quan us uniu a reunions de Zoom, Meet o Teams al vostre navegador.';

  @override
  String setDefaultAppContent(String appName) {
    return 'Establir $appName com la teva aplicació de resum predeterminada?\n\nAquesta aplicació s\'utilitzarà automàticament per a tots els resums de converses futures.';
  }

  @override
  String get switchRequiresRestart => 'Canviar d\'entorn requereix reiniciar l\'aplicació';

  @override
  String get wrappedWinHeader => 'Victòria';

  @override
  String get forYou => 'Per a tu';

  @override
  String get filterCategory => 'Categoria';

  @override
  String get createPersonHint => 'Creeu una nova persona i ensenyeu a Omi a reconèixer la seva veu també!';

  @override
  String get loadingMemories => 'Carregant records…';

  @override
  String get selectedPaymentMethod => 'Mètode de pagament seleccionat';

  @override
  String get email => 'Correu electrònic';

  @override
  String get transcriptionUnavailableRecordingContinues =>
      'Les transcripcions no estan disponibles, l\'enregistrament continua al dispositiu i es processarà més tard';

  @override
  String get noLogsYet =>
      'Encara no hi ha registres. Grava alguna cosa per veure les sol·licituds al proveïdor de transcripció.';

  @override
  String get failedToStartAuthentication => 'No s\'ha pogut iniciar l\'autenticació';

  @override
  String peopleCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count persones',
      one: '1 persona',
    );
    return '$_temp0';
  }

  @override
  String get enterBackendUrlError => 'Introduïu l\'URL del servidor';

  @override
  String get playbackBackToCurrent => 'Torna a l\'actual';

  @override
  String clockSkewWarning(int minutes) {
    return 'El rellotge del dispositiu va desajustat ~$minutes min. Comproveu la configuració de data i hora.';
  }

  @override
  String get stopThese => 'Atura aquests';

  @override
  String get yes => 'Sí';

  @override
  String get recognizingOthers => 'Reconeixent altres 👀';

  @override
  String get transcriptionLanguageDesc => 'Tria l\'idioma per a la transcripció de la veu';

  @override
  String aboutMinutesRemaining(int minutes) {
    return 'Queden aproximadament $minutes minuts';
  }

  @override
  String get deleteFlowReasonSubtitle => 'El teu feedback ens ajuda a millorar Omi per a tothom.';

  @override
  String get processedFilesDeleted => 'Fitxers processats eliminats';

  @override
  String get autoLanguageDetection => 'Detecció automàtica d\'idioma';

  @override
  String bulkExportPartial(int success, int total, String platform) {
    return 'S\'han exportat $success de $total a $platform';
  }

  @override
  String get actionItemDescriptionCannotBeEmpty => 'La descripció de la tasca no pot estar buida';

  @override
  String get deleteReasonFoundAlternative => 'Utilitzo una altra cosa';

  @override
  String get noContentToDisplay => 'No hi ha contingut per mostrar';

  @override
  String get feedbackReasonRecordingWrongSpeaker => 'Wrong speaker';

  @override
  String get create => 'Crear';

  @override
  String get greatJobAlmostThere => 'Molt bé, gairebé hi ets';

  @override
  String get captureStorageAlmostFull => 'Emmagatzematge gairebé ple';

  @override
  String chatAppsConnectedOn(String date) {
    return 'Connectat el $date';
  }

  @override
  String get wrappedAGreatDay => 'Un gran dia';

  @override
  String get backendUrlSavedSuccess => 'URL del servidor desat correctament!';

  @override
  String get speakerTagPromptIsThisYou => 'Éreu vosaltres?';

  @override
  String get knowledgeGraphDeletedSuccess => 'Graf de coneixement eliminat correctament';

  @override
  String timeMinsPlural(int count) {
    return '$count mins';
  }

  @override
  String get peopleNotHeardYet => 'Encara no s\'ha sentit';

  @override
  String get chatStarterDoDifferently => 'Què podria fer diferent avui?';

  @override
  String get fairUseAboutBody =>
      'Omi està pensat per a converses personals, reunions i interaccions en directe. L\'ús es mesura pel temps que parles, no pel temps connectat. Si el teu ús és molt superior al d\'un ús personal normal, rebràs primer un avís. Un ús intensiu continuat pot alentir o limitar la transcripció.';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'Si us plau, seleccioneu la vostra llengua principal';

  @override
  String get manualDisconnect => 'Desconnexió manual';

  @override
  String get googleCalendarNotConnected => 'Google Calendar no connectat';

  @override
  String get soCloseJustLittleMore => 'Tan a prop, només una mica més';

  @override
  String appDataAccessMessage(String appName) {
    return '$appName rebrà les teves converses, records i enregistraments al servidor del seu desenvolupador. Omi no es fa responsable de com s\'hi utilitzen aquestes dades.';
  }

  @override
  String savePercent(int percent) {
    return 'Estalvia ~$percent%';
  }

  @override
  String get deviceDisconnectedNotificationBody => 'Si us plau, reconnecta per continuar utilitzant Omi.';

  @override
  String get openConversation => 'Obre la conversa';

  @override
  String get frequencyDescMaximum => 'Totes les connexions útils, fins a 9 al dia';

  @override
  String get readChatRepliesAloud => 'Llegeix les respostes del xat en veu alta';

  @override
  String get microphonePermissionRequired => 'Es requereix permís de micròfon per a l\'enregistrament de veu.';

  @override
  String get updatePayPalAccountDetails => 'Actualitzeu les dades del vostre compte de PayPal';

  @override
  String get connectionTimeout => 'Temps d\'espera de connexió esgotat';

  @override
  String get micGainDescHigh => 'Alt - per veus distants o suaus';

  @override
  String get permissionsInfoNote => 'R = Lectura, W = Escriptura. Per defecte només lectura si no es selecciona res.';

  @override
  String timeHoursAndMins(int hours, int mins) {
    return '$hours hores $mins mins';
  }

  @override
  String get keepMyAccount => 'Mantenir el meu compte';

  @override
  String get transcriptionLanguage => 'Idioma de transcripció';

  @override
  String dreamReportStats(int records, int tokens) {
    return 'S\'han llegit $records elements · $tokens tokens';
  }

  @override
  String get editPerson => 'Editar persona';

  @override
  String get whatWeTrack => 'Què fem seguiment';

  @override
  String get micGainDescVeryHigh => 'Molt alt - per fonts molt silencioses';

  @override
  String timeCompactDays(int count) {
    return '${count}d';
  }

  @override
  String get reviewTaskField => 'Tasca';

  @override
  String reviewConfirmPerson(String name) {
    return 'Confirma $name';
  }

  @override
  String get downloadingFromDevice => 'Descarregant del dispositiu';

  @override
  String get conversationTranscriptCopiedToClipboard => 'Transcripció de la conversa copiada al porta-retalls';

  @override
  String get continueAction => 'Continuar';

  @override
  String conversationsMovedCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'S\'han mogut $count converses',
      one: 'S\'ha mogut 1 conversa',
    );
    return '$_temp0';
  }

  @override
  String get signInButton => 'Inicia la sessió';

  @override
  String get startUpdate => 'Inicia l\'actualització';

  @override
  String get wrappedTopPhrasesLabelUpper => 'TOP FRASES';

  @override
  String get total => 'Total';

  @override
  String get deleting => 'Eliminant…';

  @override
  String get skipBack10Seconds => 'Enrere 10 segons';

  @override
  String get setupAnswerAllQuestions => 'Encara no has respost totes les preguntes! 🥺';

  @override
  String get planUpgradeScheduledMessage =>
      'Actualització programada! El teu pla mensual continua fins al final del teu període de facturació.';

  @override
  String get needHelpChatWithUs => 'Necessites ajuda? Xateja amb nosaltres';

  @override
  String get chatBlockUnavailable => 'Ja no està disponible';

  @override
  String estimatedMinutes(int count) {
    return '~$count minut(s)';
  }

  @override
  String get failedToSaveMemory => 'No s\'ha pogut desar. Comproveu la vostra connexió.';

  @override
  String get deleteReasonTakingBreak => 'Només em prenc un descans';

  @override
  String get reviewAndManageConversations => 'Revisa i gestiona les teves converses capturades';

  @override
  String get actionReadMemories => 'Llegir records';

  @override
  String deletePinnedPersonMessage(String name) {
    return '$name està fixat. S\'eliminen les seves mostres de veu, Omi deixa de reconèixer-lo i les transcripcions anteriors el mostren com a parlant sense nom. Això no es pot desfer.';
  }

  @override
  String get speakerTagPromptHintOwner => 'La resposta només etiqueta el fragment reproduït.';

  @override
  String get onboardingNotificationDeniedNotifications =>
      'Permís de notificacions denegat. Si us plau, concediu permís a Preferències del Sistema > Notificacions.';

  @override
  String appDisabledNamed(String appName) {
    return '$appName s\'ha desactivat';
  }

  @override
  String get tabOld => 'Antic';

  @override
  String deviceOnboardingVoiceReplyStatusHeadphonesConnected(String device) {
    return '$device connectat. Omi parlarà aquí.';
  }

  @override
  String get deletePendingFiles => 'Eliminar enregistraments pendents';

  @override
  String get wrappedWin => 'Victòria';

  @override
  String get removeFromAllFolders => 'Eliminar de totes les carpetes';

  @override
  String get deviceIdLabel => 'ID del dispositiu';

  @override
  String get upgradeAlreadyScheduled => 'La teva actualització al pla anual ja està programada';

  @override
  String get openCall => 'Obre la trucada';

  @override
  String get rateAndReviewThisApp => 'Valora i ressenya aquesta aplicació';

  @override
  String get getStarted => 'Començar';

  @override
  String get deviceOnboardingVoiceReplyAlwaysDescription =>
      'Utilitza l\'altaveu del telèfon quan no hi ha cap auricular connectat.';

  @override
  String chooseExportDestination(int count) {
    return 'Exporta $count element(s) a…';
  }

  @override
  String get onboardingSetupSubtitle => 'Dona un moment a Omi per personalitzar-se';

  @override
  String welcomeBack(String name) {
    return 'Benvingut de nou, $name';
  }

  @override
  String get dreamReportIdle => 'Encara no hi ha res de nou per revisar.';

  @override
  String get cleanUpTitle => 'Neteja';

  @override
  String get deleteProcessedFiles => 'Eliminar fitxers processats';

  @override
  String get no => 'No';

  @override
  String get msgPhotoError => 'Error en fer la foto. Si us plau, torneu-ho a provar.';

  @override
  String get search => 'Cerca';

  @override
  String get downloadingFirmware => 'Descarregant el firmware';

  @override
  String get phoneKeypadTab => 'Teclat';

  @override
  String get pendantFullSyncBlocked =>
      'L\'emmagatzematge del Pendant és ple i encara està en mode de gravació, així que l\'àudio desat no es pot transferir. Prem el botó del Pendant per aturar la gravació i torna a sincronitzar.';

  @override
  String get deleteSelectedItemsTitle => 'Eliminar elements seleccionats';

  @override
  String get appPrivacyAndTerms => 'Privadesa i condicions de l\'aplicació';

  @override
  String get omiTranscription => 'Transcripció d\'Omi';

  @override
  String get editConversation => 'Editar conversa';

  @override
  String moveConversationsTo(int count) {
    return 'Moure $count converses a:';
  }

  @override
  String get signOutConfirmation =>
      'Hauràs de tornar a iniciar la sessió per veure les converses. El dispositiu vinculat i les preferències de l\'app es queden en aquest telèfon.';

  @override
  String get wrappedObsessionsLabel => 'OBSESSIONS';

  @override
  String get jumpToLatestMessage => 'Vés a l\'últim missatge';

  @override
  String get failedStatus => 'Fallat';

  @override
  String get notNow => 'Ara no';

  @override
  String transferFailedMessage(String error) {
    return 'Transferència fallada: $error';
  }

  @override
  String get customVocabularyTitle => 'Vocabulari personalitzat';

  @override
  String get internetRequired => 'Es requereix internet';

  @override
  String get waitingForData => 'Esperant dades…';

  @override
  String get noRecordingsYet => 'Encara no hi ha enregistraments';

  @override
  String get answerWithYourVoice => 'Respon amb la veu:';

  @override
  String personUnpinnedToast(String name) {
    return 'S\'ha deixat de fixar $name';
  }

  @override
  String get stopRecording => 'Aturar la gravació';

  @override
  String get off => 'Apagat';

  @override
  String get memoryThisPhone => 'Aquest telèfon';

  @override
  String get thirteenMonthsCoverage => 'Obtindràs 13 mesos de cobertura en total (mes actual + 12 mesos anuals)';

  @override
  String failedToCreateApiKey(String error) {
    return 'Error en crear la clau API del proveïdor: $error';
  }

  @override
  String get tipStableInternet => 'Un internet estable accelera les pujades al núvol';

  @override
  String get tasksMarkComplete => 'Marcat com a completat';

  @override
  String get reviewAddTask => 'Afegeix la tasca';

  @override
  String get submitReply => 'Enviar resposta';

  @override
  String get captureRecoveryBanner => 'Omi no envia àudio — toca per tornar a connectar';

  @override
  String get analyzing => 'Analitzant…';

  @override
  String get sttModelFaster => 'Més ràpid';

  @override
  String get fairUseLoadError => 'No s\'ha pogut carregar l\'estat d\'ús raonable. Si us plau, torneu-ho a provar.';

  @override
  String get places => 'Llocs';

  @override
  String get voiceMatchWeak => 'Coincidència feble';

  @override
  String captureOfflineBufferingFor(int minutes) {
    return 'Sense connexió, emmagatzemant · $minutes min';
  }

  @override
  String get onboardingWhatIKnowAboutYouTitle => 'El que sé de tu';

  @override
  String get raybanMetaPhotoRequested => 'Foto sol·licitada: apareixerà a la vostra conversa.';

  @override
  String get verifyYourNumber => 'Verifica el teu numero';

  @override
  String get deleteFlowConfirmSubtitle => 'Això no es pot desfer, ni tan sols el servei d\'assistència.';

  @override
  String get submitAppTermsAgreement =>
      'En enviar aquesta aplicació, accepto les Condicions de Servei i la Política de Privadesa d\'Omi AI';

  @override
  String get stripeSecureDescription =>
      'Stripe garanteix transferències segures i puntuals dels ingressos de la vostra aplicació';

  @override
  String get categoryProductivity => 'Productivitat';

  @override
  String chatWithAppName(String appName) {
    return 'Xat amb $appName';
  }

  @override
  String get enableCloudStorage => 'Activa l\'emmagatzematge al núvol';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl => 'URL del webhook de transcripció en temps real no vàlida';

  @override
  String get wrappedShow => 'SÈRIE';

  @override
  String get speakTranscribeSummarize => 'Parlar. Transcriure. Resumir.';

  @override
  String get pricingPaid => 'De pagament';

  @override
  String get successfullyConnectedAsana => 'Connectat correctament a Asana!';

  @override
  String get rating => 'Valoració';

  @override
  String get chatQuotaExceededReply =>
      'Has assolit el teu límit mensual. Actualitza per continuar xatejant amb Omi sense restriccions.';

  @override
  String get pendantIsListeningTitle => 'El teu penjoll està escoltant';

  @override
  String get usageBestDay => 'Best day';

  @override
  String get personWhyConfidence => 'Per què?';

  @override
  String get permissionDescCreateConversations => 'Aquesta app pot crear noves converses.';

  @override
  String get reviewSpellingCustom => 'Escriu-ho';

  @override
  String resetsInHours(int count) {
    return 'Es reinicia en $count hores';
  }

  @override
  String get reviewAction => 'Revisa';

  @override
  String get submitRequest => 'Enviar sol·licitud';

  @override
  String get phoneCalls => 'Trucades';

  @override
  String get actionItemsTab => 'Tasques';

  @override
  String get record => 'Grava';

  @override
  String get noReviewsFound => 'No s\'han trobat ressenyes';

  @override
  String get oauth => 'OAuth';

  @override
  String get urlCopied => 'URL copiada';

  @override
  String get actionItemReminderTitle => 'Recordatori d\'Omi';

  @override
  String sharedTasksAdded(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'S\'han afegit $count tasques a la llista',
      one: 'S\'ha afegit 1 tasca a la llista',
    );
    return '$_temp0';
  }

  @override
  String get contactsPermissionRequiredForSms => 'Es requereix permís de contactes per compartir via SMS';

  @override
  String get apiKeyRevokedSuccessfully => 'Clau API revocada correctament';

  @override
  String get authorizationSuccessful => 'Autorització correcta!';

  @override
  String get unpinAction => 'Deixa de fixar';

  @override
  String get syncingStatus => 'Sincronitzant';

  @override
  String get audioFormatLabel => 'Format d\'àudio';

  @override
  String get phoneSelectCountryTitle => 'Selecciona el país';

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'Top $percentile% Usuari';
  }

  @override
  String get phoneContactsTab => 'Contactes';

  @override
  String get reply => 'Resposta';

  @override
  String get openingShareSheet => 'Obrint full de compartició…';

  @override
  String get creatingAppIcon => 'Creant icona de l\'aplicació…';

  @override
  String get deviceOnboardingStartSpeaking => 'Comença a parlar…';

  @override
  String get wrappedAHilariousMoment => 'Un moment divertit';

  @override
  String get paidApp => 'Aplicació de pagament';

  @override
  String get wrappedStruggleHeader => 'Lluita';

  @override
  String get speakerTagPromptDontKnow => 'Algú que no conec';

  @override
  String get wrappedStarting => 'Iniciant…';

  @override
  String get getButton => 'Obtenir';

  @override
  String get syncCustomSttWarningTitle => 'La sincronització utilitza la transcripció d\'Omi';

  @override
  String get download => 'Descarregar';

  @override
  String get addScreenshot => 'Afegeix una captura de pantalla';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return 'No s\'ha pogut connectar a $serviceName: $error';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'Si us plau, torneu a connectar per continuar utilitzant el vostre $deviceName.';
  }

  @override
  String get configureDailySummaryDigest => 'Configura el resum diari de les teves tasques';

  @override
  String get showShortConversationsDesc => 'Mostrar converses més curtes que el llindar';

  @override
  String participantsSummaryUncounted(String name) {
    return '$name i altres';
  }

  @override
  String fairUseBudgetUsed(String used, String limit) {
    return '${used}m / ${limit}m';
  }

  @override
  String get add => 'Afegir';

  @override
  String get disconnect => 'Desconnectar';

  @override
  String get enterApiKey => 'Introduïu la vostra clau API';

  @override
  String get msgMaxFilesLimit => 'Només podeu seleccionar fins a 4 fitxers';

  @override
  String get space => 'Espai';

  @override
  String get upgrade => 'Actualitzar';

  @override
  String get tapToView => 'Toca per veure';

  @override
  String get summaryTemplate => 'Plantilla de resum';

  @override
  String get chatAppsWaitingTitle => 'Esperant el teu missatge';

  @override
  String yesterdayAtTime(String time) {
    return 'Ahir a les $time';
  }

  @override
  String get cancel => 'Cancel·lar';

  @override
  String get checkingAppleWatch => 'Comprovant Apple Watch…';

  @override
  String syncCardDownloadPercentSpeed(int percent, String speed) {
    return '$percent% · $speed KB/s';
  }

  @override
  String get finalTouches => 'Tocs finals';

  @override
  String get weekdaySat => 'Ds';

  @override
  String get fairUseWeekly => 'Setmanal';

  @override
  String get invalidPaymentUrl => 'URL de pagament no vàlid';

  @override
  String get transcriptionSlowerOnDevice => 'La transcripció al dispositiu pot ser més lenta en aquest dispositiu.';

  @override
  String get noListsInSpace => 'No s\'han trobat llistes en aquest espai';

  @override
  String get deviceDiagnostics => 'Diagnòstics del dispositiu';

  @override
  String get askAnything => 'Pregunta qualsevol cosa';

  @override
  String confidenceMeterLabel(String level) {
    return 'Confiança: $level';
  }

  @override
  String get permissionReadTasks => 'Llegir tasques';

  @override
  String get skipForNow => 'Omet per ara';

  @override
  String get setupCompletedUrl => 'URL de configuració completada';

  @override
  String get saySomething => 'Digues alguna cosa…';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get chatAppsEntryTitle => 'Xateja amb l\'Omi';

  @override
  String get chatAppsTelegramStepOpen => 'Toca Obre Telegram a sota';

  @override
  String get pleaseEnterValidPayPalMeLink => 'Si us plau, introduïu un enllaç PayPal.me vàlid';

  @override
  String get syncFlowIntro =>
      'Els enregistraments es transfereixen del teu dispositiu a aquest telèfon i s\'emmagatzemen localment, i després es pugen al servidor d\'Omi, on es transcriuen i es converteixen en converses.';

  @override
  String get cantFindDeviceHint =>
      'No trobes el dispositiu? Comprova que estigui encès i a prop del telèfon i torna a cercar.';

  @override
  String get tryAdjustingFilter => 'Prova d\'ajustar la cerca o el filtre';

  @override
  String get failedConnectionsRecent => 'Connexions fallides (últims 7 dies)';

  @override
  String get captureSourceCall => 'Trucada';

  @override
  String get storageLocationPhone => 'Telèfon';

  @override
  String get voiceMatchClose => 'Coincidència propera';

  @override
  String get reviewChangeUndone => 'Desfet. Omi no ho tornarà a fer pel seu compte.';

  @override
  String get tasksNoProject => 'Sense projecte';

  @override
  String get dataAccessNotice => 'Avís d\'accés a dades';

  @override
  String deviceStorageFree(String free) {
    return '$free lliure';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'Ja exportat a $platform';
  }

  @override
  String get recapDeletedSnackbar => 'Resum esborrat';

  @override
  String get apiUrlRequired => 'Cal un URL API';

  @override
  String get getOmiUnlimitedFree =>
      'Obtén Omi Il·limitat gratis contribuint les teves dades per entrenar models d\'IA.';

  @override
  String get wrappedShare => 'Compartir';

  @override
  String get tasksTomorrow => 'Demà';

  @override
  String get chatAppsShowInAppOn => 'Activat: apareixen a l\'aplicació Omi com a xats de només lectura.';

  @override
  String get errorActivatingAppIntegration =>
      'Error en activar l\'aplicació. Si és una aplicació d\'integració, assegureu-vos que la configuració estigui completa.';

  @override
  String get readChatRepliesAloudDescription => 'Només parla quan la \"Resposta de veu\" ho permet.';

  @override
  String get addDueDate => 'Afegir data de venciment';

  @override
  String get translated => 'traduït';

  @override
  String get dontAskAgain => 'No em tornis a preguntar';

  @override
  String get fullAccessScope => 'Accés complet';

  @override
  String get firmwareUpdated => 'Firmware actualitzat';

  @override
  String get deviceOnboardingVoiceReplyPreviewThroughPhoneSpeaker => 'A través de l\'altaveu del telèfon';

  @override
  String get prompt => 'Indicació';

  @override
  String get dreamReportDeletedItem => 'Element eliminat';

  @override
  String chatAppsDisconnectChannel(String app) {
    return 'Desconnecta $app';
  }

  @override
  String get appleHealthDeniedBody =>
      'Omi no té permís per llegir les teves dades d\'Apple Health. Activa-ho a Configuració d\'iOS → Privadesa i seguretat → Health → Omi.';

  @override
  String endsOnDate(String date) {
    return 'Acaba el $date';
  }

  @override
  String get searchSettings => 'Cerca a la configuració';

  @override
  String get pairingDescNeoOne =>
      'Manteniu premut el botó d\'engegada fins que el LED parpellegi. El dispositiu serà detectable.';

  @override
  String get checkingNextSevenDays => 'Comprovant els propers 7 dies';

  @override
  String get confidenceLikely => 'Probable';

  @override
  String get appleHealthFeatureChatTitle => 'Parla de la teva salut';

  @override
  String get loadingDevices => 'Carregant dispositius…';

  @override
  String get writeSomething => 'Escriu alguna cosa';

  @override
  String syncCardProgressOf(int current, int total) {
    return '$current de $total';
  }

  @override
  String get unableToOpenWatchApp =>
      'No s\'ha pogut obrir l\'aplicació Apple Watch. Obre manualment l\'aplicació Watch al teu Apple Watch i instal·la Omi des de la secció \"Aplicacions disponibles\".';

  @override
  String get dreamReportWouldFix => 'Corregiria';

  @override
  String get doubleTap => 'Doble toc';

  @override
  String get speakerTagPromptSomeoneElse => 'Una altra persona…';

  @override
  String get cancelTransfer => 'Cancel·lar transferència';

  @override
  String get capabilityExternalIntegration => 'Integració externa';

  @override
  String get sttLanguageFollowsPrimary => 'Segueix el vostre idioma principal';

  @override
  String get wrappedCringeMomentTitle => 'Moment vergonyós';

  @override
  String get allRecordingsSynced => 'Tots els enregistraments estan sincronitzats';

  @override
  String get reviewConfirm => 'Confirma';

  @override
  String get checkBackLaterForNewApps => 'Torna més tard per veure aplicacions noves';

  @override
  String get referAFriend => 'Recomana a un amic';

  @override
  String cleanUpLead(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other:
          'Omi no està segur d\'aquestes $count persones. La majoria són noms mal sentits a les transcripcions. Desmarca qui vulguis conservar.',
      one: 'Omi no està segur d\'aquesta persona. Desmarca-la per conservar-la.',
    );
    return '$_temp0';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return 'Fer $item privat?';
  }

  @override
  String get chatQuotaSubtitle => 'AI chat messages used with Omi this month.';

  @override
  String get failedTryAgain => 'Ha fallat? Torneu-ho a provar';

  @override
  String get deleteAllFiles => 'Eliminar tots els enregistraments';

  @override
  String get onDeviceModelDownloadSuccess => 'Model descarregat';

  @override
  String get reviewNoChangesTitle => 'Encara no hi ha canvis';

  @override
  String get useMobileAppToCapture => 'Utilitza la teva aplicació mòbil per capturar àudio';

  @override
  String get setYourName => 'Estableix el vostre nom';

  @override
  String get tasksGroupByDate => 'Agrupa per data';

  @override
  String get diagnosticsLast7Days => 'Últims 7 dies';

  @override
  String get deviceOnboardingStatusConnected => 'Connectat';

  @override
  String get actionItemCreatedSuccessfully => 'Tasca creada correctament';

  @override
  String get thursdayAbbr => 'Dj';

  @override
  String get wifiConfiguration => 'Configuració WiFi';

  @override
  String get cancelReasonFoundAlternative => 'He trobat una alternativa';

  @override
  String get process => 'Processar';

  @override
  String get help => 'Ajuda';

  @override
  String get rollbackConfirmTitle => 'Tornar al firmware?';

  @override
  String get visibility => 'Visibilitat';

  @override
  String get evidenceNotHeard => 'Encara no s\'ha sentit en cap conversa';

  @override
  String get messageReported => 'Missatge denunciat correctament.';

  @override
  String get readyToChat => '✨ Llest per xatejar!';

  @override
  String get tryDifferentFilter => 'Prova un filtre diferent';

  @override
  String get header => 'Capçalera';

  @override
  String get wrappedBestHeader => 'Millors';

  @override
  String get memoryDontUse => 'No ho facis servir';

  @override
  String get appStore => 'App Store';

  @override
  String get deleteMeetingScreenshotMessage =>
      'Això elimina la captura de pantalla de la nota d\'aquesta reunió. No es pot desfer.';

  @override
  String get categoryShopping => 'Compres';

  @override
  String get voiceResponseOff => 'Desactivat';

  @override
  String get bluetoothNeeded =>
      'Omi necessita Bluetooth per connectar-se al vostre dispositiu portàtil. Activeu Bluetooth i torneu-ho a provar.';

  @override
  String get googleCalendarComingSoon => 'Integració de Google Calendar properament!';

  @override
  String get max => 'Màxim';

  @override
  String get homeScreen => 'Pantalla d\'inici';

  @override
  String get chatAppsTelegramStepStart => 'Toca Comença al xat amb l\'Omi';

  @override
  String get greetingAfternoon => 'Bona tarda';

  @override
  String get unpair => 'Desvincula';

  @override
  String get diagnosticsVerdictReconnects => 'Es reconnecta sol';

  @override
  String get macOsCalendar => 'Calendari de macOS';

  @override
  String get onboardingSetupStepLanguage => 'Ajustant la transcripció al teu idioma';

  @override
  String get mcpOAuthSetup =>
      'A claude.ai, afegeix un connector personalitzat i enganxa l\'URL del servidor. Si Claude demana un Client ID d\'OAuth avançat, utilitza el valor següent i deixa el secret en blanc — mai utilitzis la teva clau d\'API MCP com a secret d\'OAuth.';

  @override
  String get wednesdayAbbr => 'Dc';

  @override
  String get selectAudioInput => 'Seleccioneu l\'entrada d\'àudio';

  @override
  String get deviceDisconnectedMessage => 'El vostre Omi s\'ha desconnectat 😔';

  @override
  String get reprocessConversation => 'Reprocessar conversa';

  @override
  String get goal => 'OBJECTIU';

  @override
  String mergeConversationsMessage(int count) {
    return 'Això combinarà $count converses en una. Tot el contingut es fusionarà i regenerarà.';
  }

  @override
  String get everyXSeconds => 'Cada x segons';

  @override
  String get chatAppsLocked => 'Requereix Omi Pro';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl => 'URL del webhook de conversa creada no vàlida';

  @override
  String get secureAuthViaAppleId => 'Autenticació segura via Apple ID';

  @override
  String connectingToDeviceName(String deviceName) {
    return 'Connectant a $deviceName';
  }

  @override
  String get listeningSubtitle => 'Temps total que Omi ha estat escoltant activament.';

  @override
  String get capturing => 'Capturant';

  @override
  String get enterWifiNetworkName => 'Introduïu el nom de la xarxa WiFi';

  @override
  String get noAppsAvailable => 'No hi ha aplicacions disponibles';

  @override
  String get installingFirmware => 'Instal·lant el firmware';

  @override
  String get transferToPhone => 'Transferir al telèfon';

  @override
  String get voiceResponseMode => 'Resposta de veu';

  @override
  String get messageCopied => '✨ Missatge copiat al porta-retalls';

  @override
  String get discardRecordingMessage => 'La teva mostra de veu encara no s\'ha desat. Si surts ara, es descartarà.';

  @override
  String chatAppsIMessageBody(String code) {
    return 'Hola Omi, codi de vinculació $code';
  }

  @override
  String get failedToRefreshWhoopStatus => 'No s\'ha pogut actualitzar l\'estat de connexió de Whoop.';

  @override
  String get youreOnAnnualPlan => 'Estàs al pla anual';

  @override
  String timeHoursPlural(int count) {
    return '$count hores';
  }

  @override
  String get usageOnline => 'En línia';

  @override
  String get validPortRequired => 'Cal un port vàlid';

  @override
  String get howItWorks => 'Com funciona';

  @override
  String get viewTemplate => 'Veure plantilla';

  @override
  String get dreamReportNothingFound => 'Res a corregir';

  @override
  String get personTalkTime => 'Temps de parla';

  @override
  String get evidenceNoVoice => 'Encara no hi ha mostra de veu';

  @override
  String get makeMyAppPublic => 'Fes pública la meva aplicació';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'Estat del permís de Bluetooth: $status. Si us plau, comproveu Preferències del Sistema.';
  }

  @override
  String get noRecordings => 'Sense enregistraments';

  @override
  String get usageChatThisMonth => 'Chat this month';

  @override
  String get addAppEnterChatPrompt => 'Introduïu una sol·licitud de xat per a la vostra aplicació';

  @override
  String daysAgo(int count) {
    return 'fa $count dies';
  }

  @override
  String get processing => 'Processant';

  @override
  String get deviceOnboardingStatusTurningOff => 'S\'està apagant…';

  @override
  String get newTag => 'NOU';

  @override
  String get permissionDescReadTasks => 'Aquesta app pot accedir a les teves tasques.';

  @override
  String get time => 'Hora';

  @override
  String get recording => 'Gravant';

  @override
  String get speakerTagPromptWhoIsThis => 'Qui és?';

  @override
  String chatUsageMessagesNoLimit(String used) {
    return 'Xat: $used missatges aquest mes';
  }

  @override
  String get importantTradeoffs => 'Compensacions importants:';

  @override
  String get makeAllPublic => 'Fer tots els records públics';

  @override
  String get noSpeechDesc =>
      'No hem pogut detectar cap veu. Assegureu-vos de parlar durant almenys 10 segons i no més de 3 minuts.';

  @override
  String get searchPartialFailure => 'No s\'han pogut carregar alguns resultats';

  @override
  String get prerecordedTranscript => 'Pregravat';

  @override
  String get confirm => 'Confirmar';

  @override
  String get statusCalling => 'Trucant…';

  @override
  String get wrappedConvos => 'converses';

  @override
  String get unresolvedSpeakersTitle => 'Quant a les etiquetes de parlant';

  @override
  String get writeYourReply => 'Escriu la teva resposta…';

  @override
  String get localCopiesSection => 'Còpies locals';

  @override
  String get noSummaryYet => 'Encara no hi ha resum';

  @override
  String get wrappedBiggestHeader => 'Més gran';

  @override
  String get error => 'Error';

  @override
  String get deviceWillRestart => 'El dispositiu es reiniciarà.';

  @override
  String get consentDataMessage =>
      'Continuant, les vostres converses, enregistraments i informació personal s\'emmagatzemaran de manera segura als nostres servidors. Els vostres enregistraments d\'àudio i transcripcions són processats per serveis d\'IA de tercers (incloent Deepgram per a la transcripció i OpenAI per a l\'anàlisi) per proporcionar-vos informació impulsada per IA i habilitar totes les funcions de l\'aplicació.';

  @override
  String get connectMacOsCalendar => 'Connectar el vostre calendari local de macOS';

  @override
  String get captureSourcePhoneMic => 'Micròfon del telèfon';

  @override
  String get setupCompleted => 'Completat';

  @override
  String get installOmiOnAppleWatchDescription =>
      'Per utilitzar el teu Apple Watch amb Omi, primer has d\'instal·lar l\'aplicació Omi al teu rellotge.';

  @override
  String get toggleControlBar => 'Commuta la barra de control';

  @override
  String get onboardingBluetoothDeniedSystemPrefs =>
      'Permís de Bluetooth denegat. Si us plau, concediu permís a Preferències del Sistema.';

  @override
  String get syncCancelled => 'Sincronització cancel·lada';

  @override
  String get firmwareDisconnectUsb => 'Desconnecta USB';

  @override
  String get processNow => 'Processar ara';

  @override
  String get appIdNotFoundError => 'No s\'ha trobat l\'ID de l\'aplicació';

  @override
  String get editDueDate => 'Edita data de venciment';

  @override
  String get home => 'Inici';

  @override
  String get tasksOverdue => 'Endarrerits';

  @override
  String get statusCompleted => 'Completat';

  @override
  String get otaStarting => 'S\'està iniciant l\'actualització…';

  @override
  String get monthApr => 'Abr';

  @override
  String get conversationTasksEmptyMessage => 'Les tasques d\'aquesta conversa apareixeran aquí.';

  @override
  String get useDifferentAccount => 'Utilitza un altre compte';

  @override
  String get reviewReasonNotUseful => 'No és útil';

  @override
  String get anonymousUser => 'Usuari anònim';

  @override
  String get viewPlansDescription => 'Gestiona la teva subscripció i consulta estadístiques d\'ús';

  @override
  String invalidJson(String error) {
    return 'JSON no vàlid: $error';
  }

  @override
  String get deleteActionItem => 'Eliminar tasca';

  @override
  String get confirmCancellation => 'Confirmar cancel·lació';

  @override
  String get tapToDelete => 'Toca per eliminar';

  @override
  String get onTheCallEnterThisCode => 'A la trucada, introdueix aquest codi';

  @override
  String get stableFirmware => 'Firmware estable';

  @override
  String get triggerEvents => 'Esdeveniments d\'activació';

  @override
  String get speakerTagPromptSaveVoicesTitle => 'Recorda les veus de les persones que anomenis';

  @override
  String get syncedFilesDeleted => 'Enregistraments sincronitzats eliminats';

  @override
  String get cloudStorageDesc =>
      'Un cop pujats, els vostres enregistraments es processen i transcriuen. Les converses estaran disponibles en un minut.';

  @override
  String get failedToUpdateFolder => 'No s\'ha pogut actualitzar la carpeta';

  @override
  String dreamReportFound(int fixes, int asks) {
    String _temp0 = intl.Intl.pluralLogic(
      fixes,
      locale: localeName,
      other: '$fixes correccions',
      one: '1 correcció',
    );
    String _temp1 = intl.Intl.pluralLogic(
      asks,
      locale: localeName,
      other: '$asks suggeriments',
      one: '1 suggeriment',
    );
    return '$_temp0 · $_temp1';
  }

  @override
  String get anotherPlatform => 'una altra plataforma';

  @override
  String get wrappedTopPhrasesLabel => 'TOP FRASES';

  @override
  String get dataAccessWarning =>
      'Aquesta aplicació accedirà a les teves dades. Omi AI no és responsable de com s\'utilitzen, modifiquen o eliminen les teves dades per aquesta aplicació';

  @override
  String get pleaseCompleteAuthentication =>
      'Completeu l\'autenticació al vostre navegador. Un cop fet, torneu a l\'aplicació.';

  @override
  String get dailySummaryTitle => 'Resum Diari';

  @override
  String get managePeople => 'Gestionar persones';

  @override
  String get dreamReportEmptyBody => 'Dream revisa què ha canviat al teu compte aproximadament cada hora.';

  @override
  String get couldNotOpenPaymentSettings =>
      'No s\'han pogut obrir els ajustos de pagament. Si us plau, torna-ho a provar.';

  @override
  String get locationServiceDisabled => 'Servei d\'ubicació desactivat';

  @override
  String get understanding => 'Entenent';

  @override
  String get recapDeleteFailed => 'No s\'ha pogut esborrar el resum. Torna-ho a provar més tard.';

  @override
  String get deleteKnowledgeGraphQuestion => 'Eliminar Gràfic de Coneixement?';

  @override
  String get wrappedYourBuddy => 'El teu amic!';

  @override
  String chatAppsChatIn(String app) {
    return 'Xat a $app';
  }

  @override
  String get speechDurationDescription => 'Assegureu-vos de parlar almenys 5 segons i no més de 90.';

  @override
  String get reviewReasonAlreadyDone => 'Ja fet';

  @override
  String get phoneSetupStep2Title => 'Introdueix un codi de verificacio';

  @override
  String get tasksClearCompleted => 'Esborra els completats';

  @override
  String get searchingForDevices => 'Cercant dispositius';

  @override
  String get siriIndexSettingDescription =>
      'Allow Siri to find your conversations, memories, and tasks on this device. Turning this off removes them from Apple search.';

  @override
  String get markIncomplete => 'Marca com a incomplet';

  @override
  String get onboardingBluetoothRequired => 'Es requereix permís de Bluetooth per connectar al dispositiu.';

  @override
  String get searchAppsPlaceholder => 'Cerca entre 1500+ aplicacions';

  @override
  String get pleaseEnterName => 'Si us plau, introdueix un nom';

  @override
  String get paymentMethodCharged =>
      'El teu mètode de pagament existent es cobrarà automàticament quan acabi el teu pla mensual';

  @override
  String get allMemoriesAreNowPublic => 'Tots els records són ara públics';

  @override
  String taskDueDate(String date) {
    return 'Venciment: $date';
  }

  @override
  String get pendantPausesUntilYouFinish => 'El penjoll es posa en pausa fins que acabis';

  @override
  String get failedToAuthorize => 'No s\'ha pogut autoritzar. Torneu-ho a provar.';

  @override
  String get mergeConversationsSuccessTitle => 'Converses fusionades amb èxit';

  @override
  String get peopleFilterNeedsVoice => 'Cal la veu';

  @override
  String get clickToBeginRecordingSystemAudio => 'Feu clic per començar a gravar àudio del sistema';

  @override
  String get fairUseStageRestrict => 'Restringit';

  @override
  String get nextResult => 'Resultat següent';

  @override
  String get chatAppsContactsApp => 'Contactes';

  @override
  String get categoryEmotionalSupport => 'Suport emocional';

  @override
  String get wrappedYourHeader => 'Els teus';

  @override
  String get pendantPausesDuringCall => 'El penjoll es posa en pausa durant la trucada';

  @override
  String noConversationsOnDate(String date) {
    return 'No hi ha converses el $date';
  }

  @override
  String get chatStarterYesterday => 'Què vaig fer ahir?';

  @override
  String get entityNotRight => 'No és correcte?';

  @override
  String get failedToCreateShareLink => 'No s\'ha pogut crear l\'enllaç per compartir';

  @override
  String get sync => 'Sincronitzar';

  @override
  String get micGainDescMax => 'Màxim - utilitzeu amb precaució';

  @override
  String get sttNone => 'Cap';

  @override
  String get chatAppsCodeNote => 'El codi només funciona una vegada i caduca d\'aquí a 10 minuts.';

  @override
  String get aiGenAppCreatedSuccessfully => 'Aplicació creada amb èxit!';

  @override
  String lastNEvents(int count) {
    return 'Últims $count esdeveniments';
  }

  @override
  String get phoneDeleteButton => 'Eliminar';

  @override
  String get systemAudio => 'Sistema';

  @override
  String get checkOutMyMemoryGraph => 'Mira el meu graf de memòria!';

  @override
  String get feedbackTitleBatteryDrain => 'Explica\'ns els problemes de bateria';

  @override
  String get startCallRecording => 'Inicia l\'enregistrament de trucada';

  @override
  String get monthlyPlanContinues => 'El teu pla mensual actual continuarà fins al final del període de facturació';

  @override
  String get syncStepUploadDesc => 'La teva gravació s\'envia al servidor d\'Omi';

  @override
  String get otaKeepNearby => 'Durant l\'actualització, mantén el dispositiu encès i a prop i no tanquis l\'app.';

  @override
  String get updatePayPalDetails => 'Actualitzar els detalls de PayPal';

  @override
  String get termsOfUse => 'Condicions d\'ús';

  @override
  String get apiKeyCreated => 'Clau API creada!';

  @override
  String get deviceOnboardingVoiceReplyPreviewIdle => 'Escolta la teva última resposta';

  @override
  String get starOngoing => 'Destacar conversa en curs';

  @override
  String get largeModelWarning =>
      'Aquest model és gran i pot bloquejar l\'app o funcionar molt lentament.\n\nEs recomana \"small\" o \"base\".';

  @override
  String get selectLanguage => 'Seleccionar idioma';

  @override
  String get professionExecutive => 'Executiu';

  @override
  String get importFileTooLarge => 'Aquest fitxer és massa gran per importar-lo.';

  @override
  String get updateRequiredTitle => 'Cal actualitzar';

  @override
  String get syncStepBackedUp => 'Conversa a punt';

  @override
  String get openWatchApp => 'Obre l\'aplicació Watch';

  @override
  String get keyNameLabel => 'NOM DE LA CLAU';

  @override
  String bulkExportSuccess(int count, String platform) {
    return 'S\'han exportat $count a $platform';
  }

  @override
  String get couldNotProcessSubscription => 'No s\'ha pogut processar la subscripció. Si us plau, torna-ho a provar.';

  @override
  String get memorizingYourVoice => 'Memoritzant la teva veu…';

  @override
  String get processingAudio => 'Processant àudio';

  @override
  String get syncYourRecordings => 'Sincronitza les teves gravacions';

  @override
  String get resetToDefault => 'Restableix per defecte';

  @override
  String get deleteConversation => 'Suprimir conversa';

  @override
  String get flashCustomFirmwareDescription => 'Instal·la versions de firmware personalitzades';

  @override
  String get deviceUpToDate => 'El dispositiu està actualitzat';

  @override
  String get raybanMetaMusicPauseNote =>
      'La música del vostre telèfon es posa en pausa mentre s\'utilitza el micròfon de les ulleres.';

  @override
  String get appleHealthNotAvailable => 'Apple Health no està disponible en aquest dispositiu';

  @override
  String hints(String text) {
    return 'Consells: $text';
  }

  @override
  String get cloudProvider => 'Proveïdor al núvol';

  @override
  String get chooseAnyFileType => 'Triar qualsevol tipus de fitxer';

  @override
  String get reset => 'Restablir';

  @override
  String get automaticallyCreateNewPerson =>
      'Crear automàticament una persona nova quan es detecti un nom a la transcripció.';

  @override
  String get timeout2Minutes => '2 minuts';

  @override
  String get newMemory => '✨ Nova memòria';

  @override
  String get chatAppsMoreComing => 'Hi haurà més aplicacions.';

  @override
  String get couldNotLoadKnowledgeGraph => 'No s\'ha pogut carregar el graf de coneixement';

  @override
  String get voiceSettingsAskToTagSubtitle =>
      'De tant en tant, l’Omi et pregunta qui parlava a les teves converses recents';

  @override
  String get developer => 'Desenvolupador';

  @override
  String get connectionNeeded => '🌐 Connexió necessària';

  @override
  String get helpAndAbout => 'Ajuda i informació';

  @override
  String get tasksNoDeadline => 'Sense termini';

  @override
  String get yourDataIsProtected => 'Les teves dades estan protegides i regides per la nostra ';

  @override
  String get confirmDeletion => 'Confirmar eliminació';

  @override
  String get speakerTagPromptClosestVoices => 'Veus més properes';

  @override
  String get quicklyPopulateRequest => 'Emplenar ràpidament amb un format de sol·licitud de proveïdor conegut';

  @override
  String get exportTranscript => 'Exportar transcripció';

  @override
  String get resetsSoon => 'Es reinicia aviat';

  @override
  String get showPhoneCallButtonTitle => 'Mostra el botó de trucada';

  @override
  String get wrappedAChallenge => 'Un repte';

  @override
  String get revokeKey => 'Revocar clau';

  @override
  String get dailyRecaps => 'Resums Diaris';

  @override
  String get processingConversationProgress => 'S\'està processant la conversa…';

  @override
  String get freeMinutesMonth => '300 minuts gratuïts/mes inclosos. Il·limitat amb ';

  @override
  String get downloadWhisperModel => 'Si us plau, descarrega un model Whisper abans de desar.';

  @override
  String get noMemoriesInCategories => 'No hi ha records en aquestes categories';

  @override
  String get checkingNextDays => 'Comprovant els propers 30 dies';

  @override
  String get createAndSubmitNewApp => 'Crea i envia una nova aplicació';

  @override
  String get chatAppsInTheMeantime => 'Mentrestant';

  @override
  String get deleteFlowReasonTitle => 'Per què te\'n vas?';

  @override
  String get tasksSelectAll => 'Selecciona-ho tot';

  @override
  String get webhookUrl => 'URL del webhook';

  @override
  String get selected => 'Seleccionat';

  @override
  String get batteryDrainIncrease => 'El consum de bateria augmentarà significativament.';

  @override
  String get dreamReportFixed => 'Corregit';

  @override
  String get failedToConnectClickUpRetry => 'No s\'ha pogut connectar a ClickUp. Si us plau, torna-ho a provar.';

  @override
  String get serverUrl => 'URL del servidor';

  @override
  String get starred => 'Destacat';

  @override
  String get speakerTagPromptClipUnavailable => 'No s’ha pogut reproduir aquest clip';

  @override
  String get feedbackSubtitleFoundAlternative => 'Ens encantaria saber què t\'ha cridat l\'atenció.';

  @override
  String get omiButtonActions => 'Accions del botó Omi';

  @override
  String get invalidRecordingDesc => 'Assegureu-vos de parlar durant almenys 5 segons i no més de 90.';

  @override
  String get switchApiConfirmTitle => 'Canviar l\'entorn de l\'API?';

  @override
  String gattError(String code) {
    return 'Error GATT ($code)';
  }

  @override
  String get aiGenRegenerateIcon => 'Torna a generar la icona';

  @override
  String get connectTaskAppToExport => 'Connecta una aplicació de tasques a Configuració per exportar';

  @override
  String get firmwareFlashed => 'Firmware instal·lat';

  @override
  String get addPerson => 'Afegir persona';

  @override
  String get cancelConsequencesSubtitle => 'Recomanem explorar les teves altres opcions en lloc de cancel·lar.';

  @override
  String get transcriptCopiedToClipboard => 'Transcripció copiada al porta-retalls';

  @override
  String get monthNov => 'Nov';

  @override
  String get switchedToOnDevice => 'Canviat a transcripció al dispositiu';

  @override
  String get phoneMicOfflineFallbackMessage =>
      'Sense connexió: s\'està gravant localment. Es transcriurà quan tornis a tenir connexió.';

  @override
  String get scopeUserConversations => 'Converses de l\'usuari';

  @override
  String get otherAppResults => 'Resultats d\'altres aplicacions';

  @override
  String get chatAppsGetNewCode => 'Obtén un codi nou';

  @override
  String get backgroundLocationDenied => 'Accés a la ubicació en segon pla denegat';

  @override
  String get syncFailureFootnote =>
      'Si el processament falla, la gravació es torna a intentar automàticament a la propera sincronització.';

  @override
  String get checkingNext7Days => 'Comprovant els propers 7 dies';

  @override
  String get monthlyPayouts => 'Pagaments mensuals';

  @override
  String get searchLanguageHint => 'Cercar idioma per nom o codi';

  @override
  String get gotIt => 'Entès';

  @override
  String get pleaseEnterAppName => 'Si us plau, introduïu el nom de l\'aplicació';

  @override
  String get newConversations => 'Noves converses';

  @override
  String get learnMoreAtOmiTraining => 'Aprèn més a omi.me/training';

  @override
  String get entityOpenTasks => 'Tasques obertes';

  @override
  String get summary => 'Resum';

  @override
  String get copied => 'Copiat';

  @override
  String get feedbackReasonRecordingDelayedOrStuck => 'Delayed or stuck';

  @override
  String get taskIntegrations => 'Integracions de tasques';

  @override
  String get tailoredConversationSummaries => 'Resums de converses personalitzats';

  @override
  String get skipThisQuestion => 'Salta aquesta pregunta';

  @override
  String get descriptionOptional => 'Descripció (opcional)';

  @override
  String get about => 'Quant a';

  @override
  String shareWithContactsCount(int count) {
    return 'Comparteix amb $count contactes';
  }

  @override
  String get discardChangesTitle => 'Vols descartar els canvis?';

  @override
  String get transcriptionDiagnostics => 'Diagnòstics de Transcripció';

  @override
  String get syncStatusFileUnavailable => 'Fitxer no disponible';

  @override
  String get createNewApp => 'Crear nova aplicació';

  @override
  String verifiedHoursAgo(int hours) {
    return 'Verificat fa ${hours}h';
  }

  @override
  String get chatLimitReachedTitle => 'Límit de xat assolit';

  @override
  String get wrappedShareText => 'El meu 2025, recordat per Omi ✨ omi.me/wrapped';

  @override
  String get reconnectionsRecent => 'Reconnexions (últims 7 dies)';

  @override
  String get appAccess => 'Accés d\'aplicacions';

  @override
  String get description => 'Descripció';

  @override
  String phoneFreeCallsRemainingWithMax(int remaining, int limit, int minutes) {
    return 'Queden $remaining de $limit trucades gratuïtes aquest mes · fins a $minutes min cadascuna';
  }

  @override
  String get clearOmisMemory => 'Esborrar la memòria d\'Omi';

  @override
  String get exportSummary => 'Exportar resum';

  @override
  String get install => 'Instal·la';

  @override
  String get syncStepBackedUpDesc => 'La trobaràs a Converses';

  @override
  String get localProcessingInfo =>
      'L\'àudio es processa localment. Funciona sense connexió, més privat, però usa més bateria.';

  @override
  String get connectStripeOrPayPal => 'Connecta Stripe o PayPal per rebre pagaments per la teva aplicació.';

  @override
  String get wrappedMomentsHeader => 'moments';

  @override
  String get systemDefault => 'Per defecte del sistema';

  @override
  String get keepUsingPendant => 'Continua amb el penjoll';

  @override
  String get paymentFailedToFetchCountries => 'Error en obtenir els països compatibles. Torneu-ho a provar més tard.';

  @override
  String get micGainDescLow => 'Molt silenciós - per entorns sorollosos';

  @override
  String get errorUpdatingConversationTitle => 'Error en actualitzar el títol de la conversa';

  @override
  String timeSecsSingular(int count) {
    return '$count seg';
  }

  @override
  String timeCompactHours(int count) {
    return '${count}h';
  }

  @override
  String get browseInstallCreateApps => 'Explora, instal·la i crea aplicacions';

  @override
  String get reddit => 'Reddit';

  @override
  String get chooseFile => 'Triar fitxer';

  @override
  String participantsSummary(String name, int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count altres',
      many: '$count altres',
      few: '$count altres',
      one: '1 altre',
    );
    return '$name + $_temp0';
  }

  @override
  String get connectingYourStripeAccount => 'Connectant el vostre compte de Stripe';

  @override
  String get cancelReasonMissingFeatures => 'Funcions que falten';

  @override
  String get chatTitle => 'Xat';

  @override
  String get chatAppsNotifyMe => 'Avisa\'m';

  @override
  String get appAccessDesc =>
      'Les següents aplicacions poden accedir a les vostres dades. Toqueu una aplicació per gestionar els seus permisos.';

  @override
  String get captureDisplayDetectionFailed => 'Ha fallat la detecció de pantalla. Enregistrament aturat.';

  @override
  String get recapRegeneratedSnackbar => 'Resum regenerat';

  @override
  String get speakerTagPromptLabeledYouToast => 'Etiquetat com a tu';

  @override
  String get categoryFinancial => 'Finances';

  @override
  String get chatAppsPrefilled => 'Emplenat';

  @override
  String get noSummaryForConversation => 'No hi ha resum disponible\nper a aquesta conversa.';

  @override
  String get aiPrompts => 'Indicacions d\'IA';

  @override
  String get view => 'Mostra';

  @override
  String get dataAlwaysEncrypted =>
      'Independentment del nivell, les teves dades sempre estan xifrades en repòs i en trànsit.';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item copiat al porta-retalls';
  }

  @override
  String get currentPlan => 'Actual';

  @override
  String get phoneCallsUpsellFeature1 => 'Transcripció en temps real de cada trucada';

  @override
  String get lowBatteryAlertTitle => 'Alerta de bateria baixa';

  @override
  String get enterConversationTitle => 'Introduïu el títol de la conversa…';

  @override
  String get pasteJsonConfig => 'Enganxeu la vostra configuració JSON a continuació:';

  @override
  String get dreamReportRunLimit => 'No queden execucions manuals avui';

  @override
  String get translationNoticeMessage =>
      'Omi tradueix les converses al teu idioma principal. Actualitza-ho en qualsevol moment a Configuració → Perfils.';

  @override
  String get aiGenFailedToRegenerateIcon => 'No s\'ha pogut regenerar la icona';

  @override
  String get pairingDescBee => 'Premeu el botó 5 vegades seguidament. La llum començarà a parpellejar en blau i verd.';

  @override
  String sharedTasksAddButton(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Afegeix $count tasques',
      one: 'Afegeix 1 tasca',
    );
    return '$_temp0';
  }

  @override
  String get paymentFailedToSavePaypal => 'Error en desar les dades de PayPal. Torneu-ho a provar més tard.';

  @override
  String get couldNotLoadCheckout =>
      'No s\'ha pogut carregar la pàgina de pagament. Comprova la connexió i torna-ho a provar.';

  @override
  String get capabilitySummary => 'Resum';

  @override
  String get selectYourCountry => 'Seleccioneu el vostre país';

  @override
  String uploadingAudioForTranscription(String duration) {
    return 'Pujant $duration d\'àudio per transcriure…';
  }

  @override
  String get conversationUrlCouldNotBeShared => 'No s\'ha pogut compartir l\'URL de la conversa.';

  @override
  String get otaStartFailed =>
      'No s\'ha pogut iniciar l\'actualització. Comprova el nom i la contrasenya de la Wi-Fi i torna-ho a provar.';

  @override
  String get triggersWhenAudioBytesReceived => 'S\'activa quan es reben bytes d\'àudio.';

  @override
  String get wrappedMy2025 => 'El meu 2025';

  @override
  String timeCompactSecs(int count) {
    return '${count}s';
  }

  @override
  String get shareWithAttendees => 'Comparteix amb els assistents';

  @override
  String get recordingsSyncAutomatically => 'Els enregistraments es sincronitzen automàticament — no cal fer res.';

  @override
  String get whereDidYouHearAboutOmi => 'Com ens has trobat?';

  @override
  String get captureMicrophonePermissionInSystemPreferences =>
      'Concediu el permís de micròfon a les Preferències del Sistema';

  @override
  String audioUploadFailedTapRetry(String duration) {
    return 'Error en pujar — s\'han conservat $duration d\'àudio al telèfon. Toca per tornar-ho a provar.';
  }

  @override
  String get captureModeLaterDescription => 'Desa l\'àudio ara i transcriu-lo quan vulguis.';

  @override
  String get cleanUpNothingTitle => 'Res a netejar';

  @override
  String get deletePersonLabel => 'Suprimeix la persona';

  @override
  String get attachedFiles => '📎 Fitxers adjunts';

  @override
  String get editGoal => 'Editar objectiu';

  @override
  String get helpsDiagnoseIssues => 'Ajuda a diagnosticar problemes';

  @override
  String get bulkDeleteFailed => 'No s\'han pogut eliminar les tasques. Torna-ho a provar.';

  @override
  String get manifestRefreshFailed => 'No s\'ha pogut actualitzar el manifest';

  @override
  String get searchPlaceholder => 'Cerca';

  @override
  String get appOptions => 'Opcions de l\'app';

  @override
  String get reprocessingConversationProgress => 'S\'està tornant a processar la conversa…';

  @override
  String get entityWhatOmiKnows => 'Què sap Omi';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'La conversa es resumeix després de $minutes minut$suffix sense parlar.';
  }

  @override
  String get permissionRevokedMessage => 'Voleu que eliminem també tots els vostres enregistraments existents?';

  @override
  String get phoneNumberCallerIdHint => 'Un cop verificat, aquest sera el teu identificador de trucada';

  @override
  String chatAppsTextThisTo(String address) {
    return 'No s\'ha obert? Envia això a $address';
  }

  @override
  String get upcomingMeetings => 'Reunions properes';

  @override
  String get preparingSystemAudioCapture => 'Preparant la captura d\'àudio del sistema';

  @override
  String dreamReportQueued(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count canvis en espera',
      one: '1 canvi en espera',
      zero: 'Cap canvi en espera',
    );
    return '$_temp0';
  }

  @override
  String get chatReplyFailed => 'Omi no ha pogut respondre. Comprova la connexió i torna-ho a provar.';

  @override
  String get noDataToMigrateFinalizing => 'No hi ha dades per migrar. Finalitzant…';

  @override
  String get accessibility => 'Accessibilitat';

  @override
  String get openOmiOnAppleWatch => 'Obre Omi al teu\nApple Watch';

  @override
  String get wrappedGettingItDone => 'Fent-ho';

  @override
  String get rawData => 'Dades en brut';

  @override
  String get passwordsDoNotMatch => 'Les contrasenyes no coincideixen';

  @override
  String errorInstallingApp(String appName, String error) {
    return 'Error en instal·lar $appName: $error';
  }

  @override
  String deleteQuoted(String name) {
    return 'Eliminar \"$name\"';
  }

  @override
  String get wrappedTopFivePhrases => 'Top 5 frases';

  @override
  String get deviceOnboardingHoldButtonHint => 'Mantén el botó premut amb fermesa fins que el llum s\'apagui';

  @override
  String get capabilities => 'Capacitats';

  @override
  String get useMcpApiKey => 'Utilitzeu la vostra clau API MCP';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return 'Integració amb $serviceName properament';
  }

  @override
  String get wrappedStruggle => 'Repte';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return 'Estat del permís de notificacions: $status. Si us plau, comproveu Preferències del Sistema.';
  }

  @override
  String get meetingScreenshotsTitle => 'Què hi havia a la pantalla';

  @override
  String verifiedMinutesAgo(int minutes) {
    return 'Verificat fa ${minutes}m';
  }

  @override
  String get permissionsRequired => 'Permisos necessaris';

  @override
  String get speakerTagPromptNotSure => 'No n’estic segur';

  @override
  String get current => 'Actual';

  @override
  String get improveConnectionAction => 'Entesos';

  @override
  String get profile => 'Perfil';

  @override
  String get audioPlaybackFailed => 'No s\'ha pogut reproduir l\'àudio. El fitxer pot estar malmès o no existir.';

  @override
  String get billingYearly => 'Anual';

  @override
  String get batteryUsageHigher => 'El consum de bateria serà més alt que la transcripció al núvol.';

  @override
  String get permissionsLabel => 'PERMISOS';

  @override
  String get enhanceTranscriptAccuracy => 'Millorar la precisió de transcripció';

  @override
  String get connectedStatus => 'Connectat';

  @override
  String get microphonePermissionDenied =>
      'Permís de micròfon denegat. Si us plau, concediu permís a Preferències del Sistema > Privacitat i Seguretat > Micròfon.';

  @override
  String get onDeviceModelDownloadSuccessDesc => 'El model Whisper s\'ha descarregat correctament';

  @override
  String get storageLocationLimitlessPendant => 'Limitless Pendant';

  @override
  String get chatAppsLinkExpired => 'Aquest enllaç ha caducat. Toca Obre Telegram per obtenir-ne un de nou.';

  @override
  String get captureOfflineBuffering => 'Sense connexió, emmagatzemant';

  @override
  String get pleaseCheckInternetConnection => 'Si us plau, comprova la teva connexió a Internet i torna-ho a intentar';

  @override
  String get todaysScore => 'Puntuació d\'avui';

  @override
  String get conversationReprocessed => 'Conversa actualitzada';

  @override
  String get loadingDuration => 'Carregant durada…';

  @override
  String get noSummary => 'Sense resum';

  @override
  String get raybanMetaMicrophoneReady => 'Micròfon a punt';

  @override
  String get applyFilters => 'Aplicar filtres';

  @override
  String get appDescriptionPlaceholder =>
      'La meva aplicació fantàstica és una aplicació genial que fa coses increïbles. És la millor aplicació!';

  @override
  String get cancelSubscriptionKeepAccessMessage =>
      'Mantindràs l\'accés fins al final del període de facturació actual.';

  @override
  String get editYourReview => 'Edita la teva ressenya';

  @override
  String get actionItemsTitle => 'Tasques';

  @override
  String get raybanMetaAudioOnlyTitle => 'Mode només àudio de Ray-Ban Meta';

  @override
  String get reviewSomeoneElse => 'Algú altre…';

  @override
  String get betaTesterMessage =>
      'Ets un provador beta d\'aquesta aplicació. Encara no és pública. Serà pública un cop aprovada.';

  @override
  String chatAppsIMessageTo(String address) {
    return 'Per a: Omi · $address';
  }

  @override
  String get comingSoon => 'Properament';

  @override
  String rollbackConfirmMessage(String version) {
    return 'Això substituirà el firmware actual amb la darrera versió estable ($version). El dispositiu es reiniciarà després de l\'actualització.';
  }

  @override
  String get termsOfService => 'Termes del servei';

  @override
  String get wrappedNotMentioned => 'No mencionat';

  @override
  String get deviceDisconnectedNotificationTitle => 'El teu dispositiu Omi s\'ha desconnectat';

  @override
  String get rayBanMetaMicPickerDescription =>
      'Selecciona el micròfon Bluetooth de les ulleres. La música s\'atura mentre Omi l\'utilitza.';

  @override
  String get chatBlockQuestion => 'Pregunta';

  @override
  String get successfullyConnectedTodoist => 'Connectat correctament a Todoist!';

  @override
  String voiceRecognitionStatus(String status) {
    String _temp0 = intl.Intl.selectLogic(
      status,
      {
        'ready': 'Veu preparada per al reconeixement',
        'saved_sample_awaiting_embedding': 'Mostra desada, pendent de processar la veu',
        'not_learned': 'Veu no apresa',
        'other': 'Estat de la veu desconegut',
      },
    );
    return '$_temp0';
  }

  @override
  String addQueryAsNewPerson(String query) {
    return 'Afegeix \"$query\" com a persona nova';
  }

  @override
  String confidenceReasonAutoConfirmed(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Has confirmat $count etiquetes automàtiques',
      one: 'Has confirmat 1 etiqueta automàtica',
    );
    return '$_temp0';
  }

  @override
  String get recordAudioConversations => 'Enregistrar converses d\'àudio';

  @override
  String get saveKeyWarning => 'Desa aquesta clau ara! No la podràs veure de nou.';

  @override
  String get saveChanges => 'Desa els canvis';

  @override
  String get sttModelSlower => 'Més lent';

  @override
  String get otaDownloadFailed => 'No s\'ha pogut baixar el firmware. Comprova la connexió Wi-Fi i torna-ho a provar.';

  @override
  String get captureRecordingViewing => 'Estàs veient aquest enregistrament';

  @override
  String get resetFilters => 'Restablir filtres';

  @override
  String get voiceSettingsSaveOthersSubtitle =>
      'Quan anomenes algú, l’Omi guarda una mostra de veu breu per reconèixer-lo la propera vegada';

  @override
  String get iveDoneThis => 'Ja ho he fet';

  @override
  String get howSyncingWorks => 'Com funciona la sincronització';

  @override
  String greetingWithName(String greeting, String name) {
    return '$greeting, $name';
  }

  @override
  String reviewRemaining(int count) {
    return 'Queden $count';
  }

  @override
  String get feedbackReasonRecordingMissingAudio => 'Missing audio';

  @override
  String get appCategoryModalTitle => 'Categoria de l\'aplicació';

  @override
  String get pushToTalk => 'Prem per parlar';

  @override
  String get noApiKeysYet => 'Encara no hi ha claus API. Crea\'n una per integrar-la amb la teva aplicació.';

  @override
  String minLabel(int count) {
    return '$count min';
  }

  @override
  String appRatingCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count valoracions',
      one: '1 valoració',
    );
    return '$_temp0';
  }

  @override
  String get wrappedFood => 'MENJAR';

  @override
  String get aboutAMinuteRemaining => 'Queda aproximadament un minut';

  @override
  String get clearLogs => 'Esborrar registres';

  @override
  String get wrappedBook => 'LLIBRE';

  @override
  String get phoneCallSubtitle => 'Enregistra una trucada amb transcripció en directe';

  @override
  String deleteConversationsTitle(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'Vols eliminar $count converses?',
      one: 'Vols eliminar 1 conversa?',
    );
    return '$_temp0';
  }

  @override
  String get deleteSelected => 'Eliminar seleccionats';

  @override
  String failedToDeleteGraph(String error) {
    return 'Error en eliminar el graf: $error';
  }

  @override
  String get setupQuestionsIntro => 'Ajuda\'ns a millorar Omi responent unes quantes preguntes.  🫶 💜';

  @override
  String get category => 'Categoria';

  @override
  String get timeout30MinutesDesc => 'Finalitzar conversa després de 30 minuts de silenci';

  @override
  String get goalDeleted => 'Objectiu suprimit';

  @override
  String get conversationDisplay => 'Visualització de Converses';

  @override
  String get conversationNoSummaryYet => 'Aquesta conversa encara no té resum.';

  @override
  String get chatsLowercase => 'xats';

  @override
  String get clearChatQuestion => 'Esborrar el xat?';

  @override
  String get signInTitle => 'Inicia la sessió';

  @override
  String get loadingKnowledgeGraph => 'Carregant el graf de coneixement…';

  @override
  String get goalTracker => 'Seguidor d\'Objectius';

  @override
  String get commandRequired => '⌘ obligatori';

  @override
  String get permissionEnabled => 'Activat';

  @override
  String get submitReview => 'Enviar ressenya';

  @override
  String chatUsageCost(String used, String limit) {
    return 'Xat: \$$used / \$$limit utilitzat aquest mes';
  }

  @override
  String get discard => 'Descarta';

  @override
  String dreamReportPasses(int count, int limit) {
    return '$count de $limit execucions avui';
  }

  @override
  String get unlockOmiInfiniteMemory => 'Records il·limitats';

  @override
  String get addAppPersonaConflictWithCapabilities => 'Persona no es pot seleccionar amb altres capacitats';

  @override
  String get whyAreYouCanceling => 'Per què cancel·les?';

  @override
  String get permissionRequestedExclaim => 'Permís sol·licitat!';

  @override
  String get chatBlockOpenInMemories => 'Obre a Records';

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total objectes';
  }

  @override
  String get deleteActionItemTitle => 'Elimina la tasca';

  @override
  String get rollBack => 'Reverteix';

  @override
  String get chatAppsOmiPro => 'OMI PRO';

  @override
  String disconnectFromAppDesc(String appName) {
    return 'Això eliminarà la vostra autenticació de $appName. Haureu de reconnectar per utilitzar-la de nou.';
  }

  @override
  String get onDeviceModelSize => 'Mida del model';

  @override
  String tagSpeaker(int speakerId) {
    return 'Etiquetar parlant $speakerId';
  }

  @override
  String get couldNotOpenUrl => 'No s\'ha pogut obrir l\'URL. Torneu-ho a provar.';

  @override
  String get conversationNewIndicator => 'Nou';

  @override
  String get notEnoughSpeechDescription => 'No s\'ha detectat prou parla. Si us plau, parleu més i torneu-ho a provar.';

  @override
  String get liveRssiOverTime => 'RSSI en temps real';

  @override
  String get usageEverywhere => 'A tot arreu';

  @override
  String nConversations(int count) {
    return '$count converses';
  }

  @override
  String get wrappedConversationsLabel => 'converses';

  @override
  String get usageYear => 'Enguany';

  @override
  String get noContactsMatchSearch => 'Cap contacte coincideix amb la cerca';

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count element$s eliminat(s)';
  }

  @override
  String get actionItemMarkedIncomplete => 'Tasca marcada com a incompleta';

  @override
  String get start => 'Iniciar';

  @override
  String discardedConversationTitle(String duration) {
    return 'Descartada · $duration';
  }

  @override
  String get debugLogsCleared => 'Registres de depuració esborrats';

  @override
  String get preparingAudioCapture => 'Preparant la captura d\'àudio';

  @override
  String get availablePaymentMethods => 'Mètodes de pagament disponibles';

  @override
  String get deleteReasonOther => 'Altres';

  @override
  String get accountCutoverMigrationInProgressTitle => 'Migración en curso';

  @override
  String get connectedKnowledgeData => 'Dades de coneixement connectades';

  @override
  String get wrappedMostFunDay => 'Més divertit';

  @override
  String get onboardingAccessibilityRequired =>
      'Es requereix permís d\'accessibilitat per detectar reunions del navegador.';

  @override
  String get selectActionItems => 'Selecció múltiple';

  @override
  String switchApiConfirmBody(String environment) {
    return 'Canviar a $environment? Hauràs de tancar i tornar a obrir l\'aplicació perquè els canvis tinguin efecte.';
  }

  @override
  String get whisperModelSizeLarge => 'Gran';

  @override
  String get currentVersion => 'Versió actual';

  @override
  String get aiAppGeneratorBannerTitle => 'Crea una app amb IA amb un toc';

  @override
  String get rayBanMetaMicPickerLoadError =>
      'No s\'han pogut carregar els micròfons Bluetooth. Comprova que el Bluetooth estigui activat i torna-ho a provar.';

  @override
  String get noneSelected => 'Cap seleccionat';

  @override
  String get entityKeptCurrent => 'Mantingut al dia per Omi';

  @override
  String migratingFromTo(String source, String target) {
    return 'Migrant de $source a $target';
  }

  @override
  String get controlNotificationFrequency => 'Controla amb quina freqüència Omi t\'envia notificacions proactives.';

  @override
  String get connectionUptime => 'Temps d\'activitat';

  @override
  String get categoryLabel => 'Categoria';

  @override
  String get aboutTheApp => 'Sobre l\'app';

  @override
  String get planSheetChooseYourPlan => 'Tria el pla que t\'encaixi.';

  @override
  String get almostDone => 'Gairebé acabat…';

  @override
  String get tasksFromConversationsWillAppear =>
      'Les tasques de les vostres converses apareixeran aquí.\nFeu clic a Crear per afegir-ne una manualment.';

  @override
  String get personLastHeard => 'Última vegada';

  @override
  String get durationThreshold => 'Llindar de durada';

  @override
  String get transcriptionServiceDiagnosticStatus => 'Estat de diagnòstic del servei de transcripció';

  @override
  String get triggersWhenNewTranscriptReceived => 'S\'activa quan es rep una transcripció nova.';

  @override
  String get aboutOmi => 'Sobre Omi';

  @override
  String get identifyingOthers => 'Identificació d\'Altres';

  @override
  String get phoneCallsSubtitle => 'Fes trucades amb transcripcio en temps real';

  @override
  String get creatingYourApp => 'Creant la vostra aplicació…';

  @override
  String get analyzingYourData => 'Analitzant les teves dades…';
}
