// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Spanish Castilian (`es`).
class AppLocalizationsEs extends AppLocalizations {
  AppLocalizationsEs([String locale = 'es']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'Conversación';

  @override
  String get transcriptTab => 'Transcripción';

  @override
  String get actionItemsTab => 'Acciones';

  @override
  String get deleteConversationTitle => '¿Borrar conversación?';

  @override
  String get deleteConversationMessage =>
      '¿Seguro que quieres borrar esta conversación? Esta acción no se puede deshacer.';

  @override
  String get confirm => 'Confirmar';

  @override
  String get cancel => 'Cancel';

  @override
  String get ok => 'Aceptar';

  @override
  String get delete => 'Eliminar';

  @override
  String get add => 'Añadir';

  @override
  String get update => 'Actualizar';

  @override
  String get save => 'Guardar';

  @override
  String get edit => 'Editar';

  @override
  String get close => 'Cerrar';

  @override
  String get clear => 'Limpiar';

  @override
  String get copyTranscript => 'Copiar transcripción';

  @override
  String get copySummary => 'Copiar resumen';

  @override
  String get testPrompt => 'Probar prompt';

  @override
  String get reprocessConversation => 'Reprocesar conversación';

  @override
  String get deleteConversation => 'Eliminar conversación';

  @override
  String get contentCopied => 'Contenido copiado al portapapeles';

  @override
  String get failedToUpdateStarred => 'Error al actualizar estado de favorito.';

  @override
  String get conversationUrlNotShared =>
      'La URL de la conversación no se compartió.';

  @override
  String get errorProcessingConversation =>
      'Error al procesar la conversación. Inténtalo de nuevo más tarde.';

  @override
  String get noInternetConnection => 'Sin conexión a Internet';

  @override
  String get unableToDeleteConversation => 'No se pudo borrar la conversación';

  @override
  String get somethingWentWrong =>
      '¡Algo salió mal! Por favor, inténtalo de nuevo más tarde.';

  @override
  String get copyErrorMessage => 'Copiar mensaje de error';

  @override
  String get errorCopied => 'Mensaje de error copiado al portapapeles';

  @override
  String get remaining => 'Restante';

  @override
  String get loading => 'Cargando...';

  @override
  String get loadingDuration => 'Cargando duración...';

  @override
  String secondsCount(int count) {
    return '$count segundos';
  }

  @override
  String get people => 'Personas';

  @override
  String get addNewPerson => 'Añadir nueva persona';

  @override
  String get editPerson => 'Editar persona';

  @override
  String get createPersonHint =>
      '¡Crea una nueva persona y entrena a Omi para reconocer su voz!';

  @override
  String get speechProfile => 'Perfil de Voz';

  @override
  String sampleNumber(int number) {
    return 'Muestra $number';
  }

  @override
  String get settings => 'Configuración';

  @override
  String get language => 'Idioma';

  @override
  String get selectLanguage => 'Seleccionar idioma';

  @override
  String get deleting => 'Borrando...';

  @override
  String get pleaseCompleteAuthentication =>
      'Por favor completa la autenticación en tu navegador. Regresa a la app cuando termines.';

  @override
  String get failedToStartAuthentication => 'Error al iniciar autenticación';

  @override
  String get importStarted =>
      '¡Importación iniciada! Se te notificará cuando termine.';

  @override
  String get failedToStartImport =>
      'No se pudo iniciar la importación. Por favor intenta de nuevo.';

  @override
  String get couldNotAccessFile => 'No se pudo abrir el archivo seleccionado';

  @override
  String get askOmi => 'Pregunta a Omi';

  @override
  String get done => 'Listo';

  @override
  String get disconnected => 'Desconectado';

  @override
  String get searching => 'Buscando...';

  @override
  String get connectDevice => 'Conectar dispositivo';

  @override
  String get monthlyLimitReached => 'Llegaste a tu límite mensual.';

  @override
  String get checkUsage => 'Verificar uso';

  @override
  String get syncingRecordings => 'Sincronizando grabaciones';

  @override
  String get recordingsToSync => 'Grabaciones por sincronizar';

  @override
  String get allCaughtUp => 'Todo al día';

  @override
  String get sync => 'Sinc';

  @override
  String get pendantUpToDate => 'Pendant actualizado';

  @override
  String get allRecordingsSynced => 'Todas las grabaciones sincronizadas';

  @override
  String get syncingInProgress => 'Sincronización en curso';

  @override
  String get readyToSync => 'Listo para sincronizar';

  @override
  String get tapSyncToStart => 'Toca Sinc para empezar';

  @override
  String get pendantNotConnected =>
      'Pendant no conectado. Conecta para sincronizar.';

  @override
  String get everythingSynced => 'Todo está sincronizado.';

  @override
  String get recordingsNotSynced => 'Tienes grabaciones sin sincronizar.';

  @override
  String get syncingBackground => 'Seguiremos sincronizando en segundo plano.';

  @override
  String get noConversationsYet => 'Aún no hay conversaciones';

  @override
  String get noStarredConversations => 'No hay conversaciones destacadas';

  @override
  String get starConversationHint =>
      'Para marcar una conversación como favorita, ábrela y toca la estrella en la cabecera.';

  @override
  String get searchConversations => 'Buscar conversaciones...';

  @override
  String selectedCount(int count, Object s) {
    return '$count seleccionados';
  }

  @override
  String get merge => 'Fusionar';

  @override
  String get mergeConversations => 'Fusionar conversaciones';

  @override
  String mergeConversationsMessage(int count) {
    return 'Esto combinará $count conversaciones en una sola. Todo el contenido se fusionará y regenerará.';
  }

  @override
  String get mergingInBackground =>
      'Fusionando en segundo plano. Esto puede tardar un momento.';

  @override
  String get failedToStartMerge => 'Error al iniciar fusión';

  @override
  String get askAnything => 'Pregunta cualquier cosa';

  @override
  String get noMessagesYet =>
      '¡No hay mensajes!\n¿Por qué no inicias una conversación?';

  @override
  String get deletingMessages =>
      'Eliminando tus mensajes de la memoria de Omi...';

  @override
  String get messageCopied => '✨ Mensaje copiado al portapapeles';

  @override
  String get cannotReportOwnMessage =>
      'No puedes reportar tus propios mensajes.';

  @override
  String get reportMessage => 'Reportar mensaje';

  @override
  String get reportMessageConfirm =>
      '¿Seguro que quieres reportar este mensaje?';

  @override
  String get messageReported => 'Mensaje reportado exitosamente.';

  @override
  String get thankYouFeedback => '¡Gracias por tus comentarios!';

  @override
  String get clearChat => 'Borrar chat';

  @override
  String get clearChatConfirm =>
      '¿Seguro que quieres limpiar el chat? Esta acción no se puede deshacer.';

  @override
  String get maxFilesLimit => 'Solo puedes subir 4 archivos a la vez';

  @override
  String get chatWithOmi => 'Chatea con Omi';

  @override
  String get apps => 'Aplicaciones';

  @override
  String get noAppsFound => 'No se encontraron aplicaciones';

  @override
  String get tryAdjustingSearch => 'Intenta ajustar tu búsqueda o filtros';

  @override
  String get createYourOwnApp => 'Crea tu propia aplicación';

  @override
  String get buildAndShareApp => 'Construye y comparte tu propia app';

  @override
  String get searchApps => 'Buscar aplicaciones...';

  @override
  String get myApps => 'Mis aplicaciones';

  @override
  String get installedApps => 'Aplicaciones instaladas';

  @override
  String get unableToFetchApps =>
      'No se pudieron cargar las apps :(\n\nRevisa tu conexión a internet.';

  @override
  String get aboutOmi => 'Acerca de Omi';

  @override
  String get privacyPolicy => 'Política de Privacidad';

  @override
  String get visitWebsite => 'Visitar el sitio web';

  @override
  String get helpOrInquiries => '¿Ayuda o consultas?';

  @override
  String get joinCommunity => '¡Únete a la comunidad!';

  @override
  String get membersAndCounting => '8000+ miembros y contando.';

  @override
  String get deleteAccountTitle => 'Borrar cuenta';

  @override
  String get deleteAccountConfirm => '¿Seguro que quieres borrar tu cuenta?';

  @override
  String get cannotBeUndone => 'Esto no se puede deshacer.';

  @override
  String get allDataErased =>
      'Todos tus recuerdos y conversaciones se borrarán permanentemente.';

  @override
  String get appsDisconnected =>
      'Tus apps e integraciones se desconectarán inmediatamente.';

  @override
  String get exportBeforeDelete =>
      'Puedes exportar tus datos antes de borrar tu cuenta. Una vez borrados, no se pueden recuperar.';

  @override
  String get deleteAccountCheckbox =>
      'Entiendo que borrar mi cuenta es permanente y que todos los datos, incluyendo recuerdos y conversaciones, se perderán para siempre.';

  @override
  String get areYouSure => '¿Estás seguro?';

  @override
  String get deleteAccountFinal =>
      'Esta acción es irreversible y borrará permanentemente tu cuenta y todos sus datos. ¿Deseas continuar?';

  @override
  String get deleteNow => 'Borrar ahora';

  @override
  String get goBack => 'Volver';

  @override
  String get checkBoxToConfirm =>
      'Marca la casilla para confirmar que entiendes que borrar tu cuenta es permanente e irreversible.';

  @override
  String get profile => 'Perfil';

  @override
  String get name => 'Nombre';

  @override
  String get email => 'Correo electrónico';

  @override
  String get customVocabulary => 'Vocabulario Personalizado';

  @override
  String get identifyingOthers => 'Identificación de Otros';

  @override
  String get paymentMethods => 'Métodos de Pago';

  @override
  String get conversationDisplay => 'Visualización de Conversaciones';

  @override
  String get dataPrivacy => 'Privacidad de Datos';

  @override
  String get userId => 'ID de Usuario';

  @override
  String get notSet => 'No establecido';

  @override
  String get userIdCopied => 'ID de usuario copiado';

  @override
  String get systemDefault => 'Por defecto del sistema';

  @override
  String get planAndUsage => 'Plan y Uso';

  @override
  String get offlineSync => 'Offline Sync';

  @override
  String get deviceSettings => 'Ajustes del dispositivo';

  @override
  String get integrations => 'Integraciones';

  @override
  String get feedbackBug => 'Feedback / Error';

  @override
  String get helpCenter => 'Centro de ayuda';

  @override
  String get developerSettings => 'Configuración de desarrollador';

  @override
  String get getOmiForMac => 'Obtener Omi para Mac';

  @override
  String get referralProgram => 'Programa de referidos';

  @override
  String get signOut => 'Cerrar Sesión';

  @override
  String get appAndDeviceCopied => 'Detalles de app y dispositivo copiados';

  @override
  String get wrapped2025 => 'Resumen 2025';

  @override
  String get yourPrivacyYourControl => 'Tu privacidad, tu control';

  @override
  String get privacyIntro =>
      'En Omi, nos comprometemos a proteger tu privacidad. Esta página te permite controlar cómo se guardan y usan tus datos.';

  @override
  String get learnMore => 'Saber más...';

  @override
  String get dataProtectionLevel => 'Nivel de protección de datos';

  @override
  String get dataProtectionDesc =>
      'Tus datos están protegidos por encriptación fuerte por defecto.';

  @override
  String get appAccess => 'Acceso de apps';

  @override
  String get appAccessDesc =>
      'Las siguientes apps pueden acceder a tus datos. Toca una app para gestionar sus permisos.';

  @override
  String get noAppsExternalAccess =>
      'Ninguna app instalada tiene acceso externo a tus datos.';

  @override
  String get deviceName => 'Nombre del dispositivo';

  @override
  String get deviceId => 'ID del dispositivo';

  @override
  String get firmware => 'Firmware';

  @override
  String get sdCardSync => 'Sincronización de tarjeta SD';

  @override
  String get hardwareRevision => 'Revisión de hardware';

  @override
  String get modelNumber => 'Número de modelo';

  @override
  String get manufacturer => 'Fabricante';

  @override
  String get doubleTap => 'Doble toque';

  @override
  String get ledBrightness => 'Brillo LED';

  @override
  String get micGain => 'Ganancia de micrófono';

  @override
  String get disconnect => 'Desconectar';

  @override
  String get forgetDevice => 'Olvidar dispositivo';

  @override
  String get chargingIssues => 'Problemas de carga';

  @override
  String get disconnectDevice => 'Desconectar dispositivo';

  @override
  String get unpairDevice => 'Desvincular dispositivo';

  @override
  String get unpairAndForget => 'Desvincular y olvidar dispositivo';

  @override
  String get deviceDisconnectedMessage => 'Tu Omi se desconectó 😔';

  @override
  String get deviceUnpairedMessage =>
      'Dispositivo desvinculado. Ve a Configuración > Bluetooth y olvida el dispositivo para completar la desvinculación.';

  @override
  String get unpairDialogTitle => 'Desvincular dispositivo';

  @override
  String get unpairDialogMessage =>
      'Esto desvinculará el dispositivo para que pueda usarse en otro teléfono. Debes ir a Ajustes > Bluetooth y olvidar el dispositivo para completar el proceso.';

  @override
  String get deviceNotConnected => 'Dispositivo no conectado';

  @override
  String get connectDeviceMessage =>
      'Conecta tu dispositivo Omi para acceder a los ajustes.';

  @override
  String get deviceInfoSection => 'Información del dispositivo';

  @override
  String get customizationSection => 'Personalización';

  @override
  String get hardwareSection => 'Hardware';

  @override
  String get v2Undetected => 'V2 no detectado';

  @override
  String get v2UndetectedMessage =>
      'Parece que tienes un dispositivo V1 o no está conectado. La funcionalidad de tarjeta SD es solo para dispositivos V2.';

  @override
  String get endConversation => 'Terminar conversación';

  @override
  String get pauseResume => 'Pausar/Reanudar';

  @override
  String get starConversation => 'Marcar conversación';

  @override
  String get doubleTapAction => 'Acción de doble toque';

  @override
  String get endAndProcess => 'Terminar y procesar';

  @override
  String get pauseResumeRecording => 'Pausar/Reanudar grabación';

  @override
  String get starOngoing => 'Marcar conversación actual';

  @override
  String get off => 'Desactivado';

  @override
  String get max => 'Máx';

  @override
  String get mute => 'Silencio';

  @override
  String get quiet => 'Bajo';

  @override
  String get normal => 'Normal';

  @override
  String get high => 'Alto';

  @override
  String get micGainDescMuted => 'Micrófono silenciado';

  @override
  String get micGainDescLow => 'Muy bajo - para entornos ruidosos';

  @override
  String get micGainDescModerate => 'Bajo - para ruido moderado';

  @override
  String get micGainDescNeutral => 'Neutral - grabación equilibrada';

  @override
  String get micGainDescSlightlyBoosted => 'Ligeramente aumentado - uso normal';

  @override
  String get micGainDescBoosted => 'Aumentado - para entornos silenciosos';

  @override
  String get micGainDescHigh => 'Alto - para voces distantes o suaves';

  @override
  String get micGainDescVeryHigh => 'Muy alto - fuentes muy silenciosas';

  @override
  String get micGainDescMax => 'Máximo - usar con precaución';

  @override
  String get developerSettingsTitle => 'Ajustes de desarrollador';

  @override
  String get saving => 'Guardando...';

  @override
  String get personaConfig => 'Configura tu Persona IA';

  @override
  String get beta => 'BETA';

  @override
  String get transcription => 'Transcripción';

  @override
  String get transcriptionConfig => 'Configurar proveedor STT';

  @override
  String get conversationTimeout => 'Tiempo de espera de conversación';

  @override
  String get conversationTimeoutConfig =>
      'Define cuándo terminan las conversaciones automáticamente';

  @override
  String get importData => 'Importar datos';

  @override
  String get importDataConfig => 'Importar datos de otras fuentes';

  @override
  String get debugDiagnostics => 'Depuración y Diagnóstico';

  @override
  String get endpointUrl => 'URL del endpoint';

  @override
  String get noApiKeys => 'Sin claves API aún';

  @override
  String get createKeyToStart => 'Crea una clave para empezar';

  @override
  String get createKey => 'Crear Clave';

  @override
  String get docs => 'Documentación';

  @override
  String get yourOmiInsights => 'Tus insights de Omi';

  @override
  String get today => 'Hoy';

  @override
  String get thisMonth => 'Este mes';

  @override
  String get thisYear => 'Este año';

  @override
  String get allTime => 'Todo el tiempo';

  @override
  String get noActivityYet => 'Sin actividad aún';

  @override
  String get startConversationToSeeInsights =>
      'Inicia una conversación con Omi\npara ver tus insights aquí.';

  @override
  String get listening => 'Escuchando';

  @override
  String get listeningSubtitle =>
      'Tiempo total que Omi ha escuchado activamente.';

  @override
  String get understanding => 'Entendiendo';

  @override
  String get understandingSubtitle =>
      'Palabras entendidas de tus conversaciones.';

  @override
  String get providing => 'Proveyendo';

  @override
  String get providingSubtitle => 'Tareas y notas capturadas automáticamente.';

  @override
  String get remembering => 'Recordando';

  @override
  String get rememberingSubtitle => 'Hechos y detalles recordados para ti.';

  @override
  String get unlimitedPlan => 'Plan Ilimitado';

  @override
  String get managePlan => 'Gestionar plan';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'Tu plan termina el $date.';
  }

  @override
  String renewsOn(String date) {
    return 'Tu plan se renueva el $date.';
  }

  @override
  String get basicPlan => 'Plan Gratuito';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used de $limit minutos usados';
  }

  @override
  String get upgrade => 'Mejorar';

  @override
  String get upgradeToUnlimited => 'Actualizar a ilimitado';

  @override
  String basicPlanDesc(int limit) {
    return 'Tu plan incluye $limit minutos gratis al mes.';
  }

  @override
  String get shareStatsMessage =>
      '¡Compartiendo mis estadísticas de Omi! (omi.me - mi asistente IA siempre activo)';

  @override
  String get sharePeriodToday => 'Hoy Omi:';

  @override
  String get sharePeriodMonth => 'Este mes Omi:';

  @override
  String get sharePeriodYear => 'Este año Omi:';

  @override
  String get sharePeriodAllTime => 'Hasta ahora Omi:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 Escuchó por $minutes minutos';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 Entendió $words palabras';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ Entregó $count insights';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 Guardó $count recuerdos';
  }

  @override
  String get debugLogs => 'Registros de depuración';

  @override
  String get debugLogsAutoDelete => 'Se borran automáticamente tras 3 días.';

  @override
  String get debugLogsDesc => 'Ayuda a diagnosticar problemas';

  @override
  String get noLogFilesFound => 'No se encontraron archivos de registro.';

  @override
  String get omiDebugLog => 'Registro de depuración Omi';

  @override
  String get logShared => 'Registro compartido';

  @override
  String get selectLogFile => 'Seleccionar archivo de registro';

  @override
  String get shareLogs => 'Compartir registros';

  @override
  String get debugLogCleared => 'Registro de depuración limpiado';

  @override
  String get exportStarted =>
      'Exportación iniciada. Puede tardar unos segundos...';

  @override
  String get exportAllData => 'Exportar todos los datos';

  @override
  String get exportDataDesc => 'Exportar conversaciones a un archivo JSON';

  @override
  String get exportedConversations => 'Conversaciones exportadas de Omi';

  @override
  String get exportShared => 'Exportación compartida';

  @override
  String get deleteKnowledgeGraphTitle => '¿Borrar Gráfico de Conocimiento?';

  @override
  String get deleteKnowledgeGraphMessage =>
      'Esto borrará todos los datos derivados del gráfico (nodos y conexiones). Tus recuerdos originales se mantienen seguros.';

  @override
  String get knowledgeGraphDeleted => 'Gráfico de conocimiento eliminado';

  @override
  String deleteGraphFailed(String error) {
    return 'Error al borrar el gráfico: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'Borrar gráfico de conocimiento';

  @override
  String get deleteKnowledgeGraphDesc =>
      'Eliminar todos los nodos y conexiones';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'Servidor MCP';

  @override
  String get mcpServerDesc => 'Conectar asistentes IA con tus datos';

  @override
  String get serverUrl => 'URL del servidor';

  @override
  String get urlCopied => 'URL copiada';

  @override
  String get apiKeyAuth => 'Autenticación API Key';

  @override
  String get header => 'Cabecera';

  @override
  String get authorizationBearer => 'Authorization: Bearer <key>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'Client ID';

  @override
  String get clientSecret => 'Client Secret';

  @override
  String get useMcpApiKey => 'Usa tu clave API MCP';

  @override
  String get webhooks => 'Webhooks';

  @override
  String get conversationEvents => 'Eventos de conversación';

  @override
  String get newConversationCreated => 'Nueva conversación creada';

  @override
  String get realtimeTranscript => 'Transcripción en tiempo real';

  @override
  String get transcriptReceived => 'Transcripción recibida';

  @override
  String get audioBytes => 'Bytes de audio';

  @override
  String get audioDataReceived => 'Datos de audio recibidos';

  @override
  String get intervalSeconds => 'Intervalo (segundos)';

  @override
  String get daySummary => 'Resumen del día';

  @override
  String get summaryGenerated => 'Resumen generado';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'Añadir a claude_desktop_config.json';

  @override
  String get copyConfig => 'Copiar configuración';

  @override
  String get configCopied => 'Configuración copiada al portapapeles';

  @override
  String get listeningMins => 'Escuchando (Mins)';

  @override
  String get understandingWords => 'Entendiendo (Palabras)';

  @override
  String get insights => 'Información';

  @override
  String get memories => 'Recuerdos';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '$used de $limit mins usados este mes';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '$used de $limit palabras usadas este mes';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '$used de $limit insights obtenidos este mes';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return '$used de $limit recuerdos hechos este mes';
  }

  @override
  String get visibility => 'Visibilidad';

  @override
  String get visibilitySubtitle =>
      'Controla qué conversaciones aparecen en tu lista';

  @override
  String get showShortConversations => 'Mostrar conversaciones cortas';

  @override
  String get showShortConversationsDesc =>
      'Mostrar conversaciones más cortas que el umbral';

  @override
  String get showDiscardedConversations => 'Mostrar conversaciones descartadas';

  @override
  String get showDiscardedConversationsDesc =>
      'Incluir conversaciones marcadas como descartadas';

  @override
  String get shortConversationThreshold => 'Umbral de conversación corta';

  @override
  String get shortConversationThresholdSubtitle =>
      'Conversaciones más cortas que esto se ocultan si no está activado arriba';

  @override
  String get durationThreshold => 'Umbral de duración';

  @override
  String get durationThresholdDesc =>
      'Ocultar conversaciones más cortas que esto';

  @override
  String minLabel(int count) {
    return '$count Min';
  }

  @override
  String get customVocabularyTitle => 'Vocabulario personalizado';

  @override
  String get addWords => 'Añadir palabras';

  @override
  String get addWordsDesc => 'Nombres, términos o palabras inusuales';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'Connect';

  @override
  String get comingSoon => 'Próximamente';

  @override
  String get integrationsFooter =>
      'Conecta tus apps para ver datos y métricas en el chat.';

  @override
  String get completeAuthInBrowser =>
      'Por favor completa la autenticación en tu navegador.';

  @override
  String failedToStartAuth(String appName) {
    return 'Error al iniciar autenticación para $appName';
  }

  @override
  String disconnectAppTitle(String appName) {
    return '¿Desconectar $appName?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return '¿Seguro que quieres desconectar $appName? Puedes reconectar en cualquier momento.';
  }

  @override
  String disconnectedFrom(String appName) {
    return 'Desconectado de $appName';
  }

  @override
  String get failedToDisconnect => 'Error al desconectar';

  @override
  String connectTo(String appName) {
    return 'Conectar a $appName';
  }

  @override
  String authAccessMessage(String appName) {
    return 'Debes autorizar a Omi para acceder a tus datos de $appName.';
  }

  @override
  String get continueAction => 'Continuar';

  @override
  String get languageTitle => 'Idioma';

  @override
  String get primaryLanguage => 'Idioma principal';

  @override
  String get automaticTranslation => 'Traducción automática';

  @override
  String get detectLanguages => 'Detectar 10+ idiomas';

  @override
  String get authorizeSavingRecordings => 'Autorizar guardado de grabaciones';

  @override
  String get thanksForAuthorizing => '¡Gracias por autorizar!';

  @override
  String get needYourPermission => 'Necesitamos tu permiso';

  @override
  String get alreadyGavePermission =>
      'Ya nos diste permiso para guardar tus grabaciones. Aquí un recordatorio de por qué lo necesitamos:';

  @override
  String get wouldLikePermission =>
      'Nos gustaría tu permiso para guardar tus grabaciones de voz. Aquí está la razón:';

  @override
  String get improveSpeechProfile => 'Mejorar tu perfil de voz';

  @override
  String get improveSpeechProfileDesc =>
      'Usamos grabaciones para entrenar y mejorar tu perfil personal de voz.';

  @override
  String get trainFamilyProfiles => 'Entrenar perfiles de amigos y familia';

  @override
  String get trainFamilyProfilesDesc =>
      'Tus grabaciones ayudan a reconocer y crear perfiles para tus amigos y familiares.';

  @override
  String get enhanceTranscriptAccuracy => 'Mejorar precisión de transcripción';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'A medida que nuestro modelo mejora, podemos ofrecer mejores transcripciones.';

  @override
  String get legalNotice =>
      'Aviso legal: La legalidad de grabar puede variar según tu ubicación.';

  @override
  String get alreadyAuthorized => 'Ya autorizado';

  @override
  String get authorize => 'Autorizar';

  @override
  String get revokeAuthorization => 'Revocar autorización';

  @override
  String get authorizationSuccessful => '¡Autorización exitosa!';

  @override
  String get failedToAuthorize => 'Error al autorizar. Inténtalo de nuevo.';

  @override
  String get authorizationRevoked => 'Autorización revocada.';

  @override
  String get recordingsDeleted => 'Grabaciones borradas.';

  @override
  String get failedToRevoke => 'Error al revocar autorización.';

  @override
  String get permissionRevokedTitle => 'Permiso revocado';

  @override
  String get permissionRevokedMessage =>
      '¿Quieres que borremos todas tus grabaciones existentes también?';

  @override
  String get yes => 'Sí';

  @override
  String get editName => 'Edit Name';

  @override
  String get howShouldOmiCallYou => '¿Cómo debería llamarte Omi?';

  @override
  String get enterYourName => 'Introduce tu nombre';

  @override
  String get nameCannotBeEmpty => 'El nombre no puede estar vacío';

  @override
  String get nameUpdatedSuccessfully => '¡Nombre actualizado con éxito!';

  @override
  String get calendarSettings => 'Ajustes de calendario';

  @override
  String get calendarProviders => 'Proveedores de calendario';

  @override
  String get macOsCalendar => 'Calendario macOS';

  @override
  String get connectMacOsCalendar => 'Conecta tu calendario local de macOS';

  @override
  String get googleCalendar => 'Google Calendar';

  @override
  String get syncGoogleAccount => 'Sincronizar con tu cuenta de Google';

  @override
  String get showMeetingsMenuBar => 'Mostrar reuniones en barra de menú';

  @override
  String get showMeetingsMenuBarDesc =>
      'Mostrar tu próxima reunión y tiempo restante en la barra de menú de macOS';

  @override
  String get showEventsNoParticipants => 'Mostrar eventos sin participantes';

  @override
  String get showEventsNoParticipantsDesc =>
      'Si activado, \'Próximamente\' mostrará eventos sin participantes o enlaces de video.';

  @override
  String get yourMeetings => 'Tus reuniones';

  @override
  String get refresh => 'Actualizar';

  @override
  String get noUpcomingMeetings => 'No hay reuniones próximas';

  @override
  String get checkingNextDays => 'Revisando los próximos 30 días';

  @override
  String get tomorrow => 'Mañana';

  @override
  String get googleCalendarComingSoon =>
      '¡Integración con Google Calendar pronto!';

  @override
  String connectedAsUser(String userId) {
    return 'Conectado como: $userId';
  }

  @override
  String get defaultWorkspace => 'Espacio de trabajo por defecto';

  @override
  String get tasksCreatedInWorkspace => 'Las tareas se crearán en este espacio';

  @override
  String get defaultProjectOptional => 'Proyecto por defecto (Opcional)';

  @override
  String get leaveUnselectedTasks =>
      'Dejar sin seleccionar para tareas sin proyecto';

  @override
  String get noProjectsInWorkspace =>
      'No se encontraron proyectos en este espacio';

  @override
  String get conversationTimeoutDesc =>
      'Elige cuánto tiempo esperar en silencio antes de terminar:';

  @override
  String get timeout2Minutes => '2 minutos';

  @override
  String get timeout2MinutesDesc => 'Terminar tras 2 minutos de silencio';

  @override
  String get timeout5Minutes => '5 minutos';

  @override
  String get timeout5MinutesDesc => 'Terminar tras 5 minutos de silencio';

  @override
  String get timeout10Minutes => '10 minutos';

  @override
  String get timeout10MinutesDesc => 'Terminar tras 10 minutos de silencio';

  @override
  String get timeout30Minutes => '30 minutos';

  @override
  String get timeout30MinutesDesc => 'Terminar tras 30 minutos de silencio';

  @override
  String get timeout4Hours => '4 horas';

  @override
  String get timeout4HoursDesc => 'Terminar tras 4 horas de silencio';

  @override
  String get conversationEndAfterHours =>
      'Las conversaciones terminan tras 4 horas de silencio';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Las conversaciones terminan tras $minutes minuto(s) de silencio';
  }

  @override
  String get tellUsPrimaryLanguage => 'Dinos tu idioma principal';

  @override
  String get languageForTranscription =>
      'Configura tu idioma para transcripciones más precisas.';

  @override
  String get singleLanguageModeInfo => 'Modo de un solo idioma activado.';

  @override
  String get searchLanguageHint => 'Buscar idioma por nombre o código';

  @override
  String get noLanguagesFound => 'No se encontraron idiomas';

  @override
  String get skip => 'Saltar';

  @override
  String languageSetTo(String language) {
    return 'Idioma establecido a $language';
  }

  @override
  String get failedToSetLanguage => 'Error al establecer idioma';

  @override
  String appSettings(String appName) {
    return 'Ajustes de $appName';
  }

  @override
  String disconnectFromApp(String appName) {
    return '¿Desconectar de $appName?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'Esto eliminará tu autenticación de $appName.';
  }

  @override
  String connectedToApp(String appName) {
    return 'Conectado a $appName';
  }

  @override
  String get account => 'Cuenta';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Tus tareas se sincronizan con tu cuenta de $appName';
  }

  @override
  String get defaultSpace => 'Espacio por defecto';

  @override
  String get selectSpaceInWorkspace => 'Selecciona un espacio';

  @override
  String get noSpacesInWorkspace => 'No hay espacios en este entorno';

  @override
  String get defaultList => 'Lista por defecto';

  @override
  String get tasksAddedToList => 'Las tareas se añadirán a esta lista';

  @override
  String get noListsInSpace => 'No hay listas en este espacio';

  @override
  String failedToLoadRepos(String error) {
    return 'Error al cargar repositorios: $error';
  }

  @override
  String get defaultRepoSaved => 'Repositorio por defecto guardado';

  @override
  String get failedToSaveDefaultRepo =>
      'Error al guardar repositorio por defecto';

  @override
  String get defaultRepository => 'Repositorio por defecto';

  @override
  String get selectDefaultRepoDesc =>
      'Elige un repo por defecto para crear issues.';

  @override
  String get noReposFound => 'No se encontraron repositorios';

  @override
  String get private => 'Privado';

  @override
  String updatedDate(String date) {
    return 'Actualizado el $date';
  }

  @override
  String get yesterday => 'Ayer';

  @override
  String daysAgo(int count) {
    return 'hace $count días';
  }

  @override
  String get oneWeekAgo => 'hace 1 semana';

  @override
  String weeksAgo(int count) {
    return 'hace $count semanas';
  }

  @override
  String get oneMonthAgo => 'hace 1 mes';

  @override
  String monthsAgo(int count) {
    return 'hace $count meses';
  }

  @override
  String get issuesCreatedInRepo =>
      'Los issues se crearán en tu repo por defecto';

  @override
  String get taskIntegrations => 'Integraciones de tareas';

  @override
  String get configureSettings => 'Configurar ajustes';

  @override
  String get completeAuthBrowser =>
      'Por favor completa la autenticación en tu navegador. Al terminar, vuelve a la app.';

  @override
  String failedToStartAppAuth(String appName) {
    return 'Error al iniciar autenticación de $appName';
  }

  @override
  String connectToAppTitle(String appName) {
    return 'Conectar a $appName';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Necesitas autorizar a Omi para crear tareas en tu cuenta de $appName. Esto abrirá tu navegador para autenticación.';
  }

  @override
  String get continueButton => 'Continuar';

  @override
  String appIntegration(String appName) {
    return 'Integración $appName';
  }

  @override
  String integrationComingSoon(String appName) {
    return '¡Integración con $appName pronto!';
  }

  @override
  String get gotIt => 'Entendido';

  @override
  String get tasksExportedOneApp =>
      'Las tareas solo se pueden exportar a una app a la vez.';

  @override
  String get completeYourUpgrade => 'Completa tu mejora';

  @override
  String get importConfiguration => 'Importar configuración';

  @override
  String get exportConfiguration => 'Exportar configuración';

  @override
  String get bringYourOwn => 'Trae el tuyo';

  @override
  String get payYourSttProvider =>
      'Usa Omi gratis. Solo pagas a tu proveedor STT.';

  @override
  String get freeMinutesMonth => '1.200 minutos gratis/mes incluidos.';

  @override
  String get omiUnlimited => 'Omi Ilimitado';

  @override
  String get hostRequired => 'Host es requerido';

  @override
  String get validPortRequired => 'Puerto válido requerido';

  @override
  String get validWebsocketUrlRequired =>
      'URL WebSocket válida requerida (wss://)';

  @override
  String get apiUrlRequired => 'URL API requerida';

  @override
  String get apiKeyRequired => 'API Key requerida';

  @override
  String get invalidJsonConfig => 'JSON inválido';

  @override
  String errorSaving(String error) {
    return 'Error guardando: $error';
  }

  @override
  String get configCopiedToClipboard => 'Configuración copiada al portapapeles';

  @override
  String get pasteJsonConfig => 'Pega tu configuración JSON abajo:';

  @override
  String get addApiKeyAfterImport =>
      'Debes añadir tu propia API key tras importar';

  @override
  String get paste => 'Pegar';

  @override
  String get import => 'Importar';

  @override
  String get invalidProviderInConfig => 'Proveedor inválido en configuración';

  @override
  String importedConfig(String providerName) {
    return 'Configuración de $providerName importada';
  }

  @override
  String invalidJson(String error) {
    return 'JSON inválido: $error';
  }

  @override
  String get provider => 'Proveedor';

  @override
  String get live => 'En vivo';

  @override
  String get onDevice => 'En el dispositivo';

  @override
  String get apiUrl => 'URL API';

  @override
  String get enterSttHttpEndpoint => 'Ingresa tu endpoint STT HTTP';

  @override
  String get websocketUrl => 'URL WebSocket';

  @override
  String get enterLiveSttWebsocket => 'Ingresa tu endpoint STT WebSocket';

  @override
  String get apiKey => 'Clave API';

  @override
  String get enterApiKey => 'Ingresa tu API Key';

  @override
  String get storedLocallyNeverShared =>
      'Guardado localmente, nunca compartido';

  @override
  String get host => 'Host';

  @override
  String get port => 'Puerto';

  @override
  String get advanced => 'Avanzado';

  @override
  String get configuration => 'Configuración';

  @override
  String get requestConfiguration => 'Configuración de petición';

  @override
  String get responseSchema => 'Esquema de respuesta';

  @override
  String get modified => 'Modificado';

  @override
  String get resetRequestConfig => 'Restablecer configuración de petición';

  @override
  String get logs => 'Registros';

  @override
  String get logsCopied => 'Registros copiados';

  @override
  String get noLogsYet => 'Sin registros. Graba para ver actividad.';

  @override
  String deviceUsesCodec(String device, String reason) {
    return '$device usa $reason. Se usará Omi.';
  }

  @override
  String get omiTranscription => 'Transcripción Omi';

  @override
  String get bestInClassTranscription => 'Transcripción de primera clase';

  @override
  String get instantSpeakerLabels => 'Etiquetas de hablante instantáneas';

  @override
  String get languageTranslation => 'Traducción en 100+ idiomas';

  @override
  String get optimizedForConversation => 'Optimizado para conversaciones';

  @override
  String get autoLanguageDetection => 'Detección automática de idioma';

  @override
  String get highAccuracy => 'Alta precisión';

  @override
  String get privacyFirst => 'Privacidad primero';

  @override
  String get saveChanges => 'Guardar cambios';

  @override
  String get resetToDefault => 'Restablecer a predeterminado';

  @override
  String get viewTemplate => 'Ver plantilla';

  @override
  String get trySomethingLike => 'Prueba algo como...';

  @override
  String get tryIt => 'Probar';

  @override
  String get creatingPlan => 'Creando plan';

  @override
  String get developingLogic => 'Desarrollando lógica';

  @override
  String get designingApp => 'Diseñando App';

  @override
  String get generatingIconStep => 'Generando ícono';

  @override
  String get finalTouches => 'Toques finales';

  @override
  String get processing => 'Procesando...';

  @override
  String get features => 'Funcionalidades';

  @override
  String get creatingYourApp => 'Creando tu App...';

  @override
  String get generatingIcon => 'Generando ícono...';

  @override
  String get whatShouldWeMake => '¿Qué deberíamos hacer?';

  @override
  String get appName => 'App Name';

  @override
  String get description => 'Descripción';

  @override
  String get publicLabel => 'Público';

  @override
  String get privateLabel => 'Privado';

  @override
  String get free => 'Gratis';

  @override
  String get perMonth => '/ mes';

  @override
  String get tailoredConversationSummaries =>
      'Resúmenes de conversación a medida';

  @override
  String get customChatbotPersonality =>
      'Personalidad de chatbot personalizada';

  @override
  String get makePublic => 'Hacer público';

  @override
  String get anyoneCanDiscover => 'Cualquiera puede descubrir tu App';

  @override
  String get onlyYouCanUse => 'Solo tú puedes usar esta App';

  @override
  String get paidApp => 'App de pago';

  @override
  String get usersPayToUse => 'Los usuarios pagan por usar tu App';

  @override
  String get freeForEveryone => 'Gratis para todos';

  @override
  String get perMonthLabel => '/ mes';

  @override
  String get creating => 'Creando...';

  @override
  String get createApp => 'Crear aplicación';

  @override
  String get searchingForDevices => 'Buscando dispositivos...';

  @override
  String devicesFoundNearby(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'DISPOSITIVOS',
      one: 'DISPOSITIVO',
    );
    return '$count $_temp0 ENCONTRADOS CERCA';
  }

  @override
  String get pairingSuccessful => 'Emparejamiento exitoso';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Error conectando con Apple Watch: $error';
  }

  @override
  String get dontShowAgain => 'No mostrar de nuevo';

  @override
  String get iUnderstand => 'Entiendo';

  @override
  String get enableBluetooth => 'Activar Bluetooth';

  @override
  String get bluetoothNeeded =>
      'Omi necesita Bluetooth para conectar tu wearable.';

  @override
  String get contactSupport => '¿Contactar soporte?';

  @override
  String get connectLater => 'Conectar más tarde';

  @override
  String get grantPermissions => 'Conceder permisos';

  @override
  String get backgroundActivity => 'Actividad en segundo plano';

  @override
  String get backgroundActivityDesc =>
      'Deja que Omi corra en segundo plano para mejor estabilidad';

  @override
  String get locationAccess => 'Acceso a ubicación';

  @override
  String get locationAccessDesc =>
      'Habilita ubicación en segundo plano para la experiencia completa';

  @override
  String get notifications => 'Notificaciones';

  @override
  String get notificationsDesc =>
      'Habilita notificaciones para estar informado';

  @override
  String get locationServiceDisabled => 'Servicio de ubicación desactivado';

  @override
  String get locationServiceDisabledDesc =>
      'Por favor activa los servicios de ubicación';

  @override
  String get backgroundLocationDenied =>
      'Acceso a ubicación en segundo plano denegado';

  @override
  String get backgroundLocationDeniedDesc =>
      'Por favor permite \'Siempre\' en los ajustes de ubicación';

  @override
  String get lovingOmi => '¿Te gusta Omi?';

  @override
  String get leaveReviewIos =>
      'Ayúdanos a llegar a más gente dejando una reseña en la App Store.';

  @override
  String get leaveReviewAndroid =>
      'Ayúdanos a llegar a más gente dejando una reseña en Google Play.';

  @override
  String get rateOnAppStore => 'Calificar en App Store';

  @override
  String get rateOnGooglePlay => 'Calificar en Google Play';

  @override
  String get maybeLater => 'Quizás más tarde';

  @override
  String get speechProfileIntro =>
      'Omi necesita aprender tus objetivos y tu voz. Podrás modificarlo más tarde.';

  @override
  String get getStarted => 'Empezar';

  @override
  String get allDone => '¡Listo!';

  @override
  String get keepGoing => 'Sigue así';

  @override
  String get skipThisQuestion => 'Saltar esta pregunta';

  @override
  String get skipForNow => 'Saltar por ahora';

  @override
  String get connectionError => 'Error de conexión';

  @override
  String get connectionErrorDesc => 'Fallo al conectar con el servidor.';

  @override
  String get invalidRecordingMultipleSpeakers => 'Grabación inválida';

  @override
  String get multipleSpeakersDesc => 'Parece haber múltiples hablantes.';

  @override
  String get tooShortDesc => 'No se detectó suficiente habla.';

  @override
  String get invalidRecordingDesc => 'Asegúrate de hablar al menos 5 segundos.';

  @override
  String get areYouThere => '¿Estás ahí?';

  @override
  String get noSpeechDesc => 'No pudimos detectar habla.';

  @override
  String get connectionLost => 'Conexión perdida';

  @override
  String get connectionLostDesc => 'Se perdió la conexión.';

  @override
  String get tryAgain => 'Intentar de nuevo';

  @override
  String get connectOmiOmiGlass => 'Conectar Omi / OmiGlass';

  @override
  String get continueWithoutDevice => 'Continuar sin dispositivo';

  @override
  String get permissionsRequired => 'Permisos requeridos';

  @override
  String get permissionsRequiredDesc =>
      'Esta app requiere permisos de Bluetooth y Ubicación.';

  @override
  String get openSettings => 'Abrir ajustes';

  @override
  String get wantDifferentName => '¿Quieres usar un nombre diferente?';

  @override
  String get whatsYourName => '¿Cómo te llamas?';

  @override
  String get speakTranscribeSummarize => 'Habla. Transcribe. Resume.';

  @override
  String get signInWithApple => 'Iniciar sesión con Apple';

  @override
  String get signInWithGoogle => 'Iniciar sesión con Google';

  @override
  String get byContinuingAgree => 'Al continuar, aceptas nuestros ';

  @override
  String get termsOfUse => 'Términos de uso';

  @override
  String get omiYourAiCompanion => 'Omi – Tu compañero IA';

  @override
  String get captureEveryMoment => 'Captura cada momento. Obtén resúmenes IA.';

  @override
  String get appleWatchSetup => 'Configuración Apple Watch';

  @override
  String get permissionRequestedExclaim => '¡Permiso solicitado!';

  @override
  String get microphonePermission => 'Permiso de micrófono';

  @override
  String get permissionGrantedNow => '¡Permiso concedido!';

  @override
  String get needMicrophonePermission => 'Necesitamos permiso de micrófono.';

  @override
  String get grantPermissionButton => 'Conceder permiso';

  @override
  String get needHelp => '¿Necesitas ayuda?';

  @override
  String get troubleshootingSteps => 'Pasos de solución de problemas...';

  @override
  String get recordingStartedSuccessfully => '¡Grabación iniciada con éxito!';

  @override
  String get permissionNotGrantedYet => 'Permiso aún no concedido.';

  @override
  String errorRequestingPermission(String error) {
    return 'Error pidiendo permiso: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'Error iniciando grabación: $error';
  }

  @override
  String get selectPrimaryLanguage => 'Selecciona tu idioma principal';

  @override
  String get languageBenefits => 'Configura tu idioma para mejores resultados';

  @override
  String get whatsYourPrimaryLanguage => '¿Cuál es tu idioma principal?';

  @override
  String get selectYourLanguage => 'Selecciona tu idioma';

  @override
  String get personalGrowthJourney =>
      'Tu viaje de crecimiento personal con IA que escucha cada palabra tuya.';

  @override
  String get actionItemsTitle => 'Acciones';

  @override
  String get actionItemsDescription =>
      'Toca para editar • Mantén para seleccionar • Desliza para acciones';

  @override
  String get tabToDo => 'Pendiente';

  @override
  String get tabDone => 'Hecho';

  @override
  String get tabOld => 'Antiguo';

  @override
  String get emptyTodoMessage => '🎉 ¡Todo hecho!\nNo hay tareas pendientes';

  @override
  String get emptyDoneMessage => 'No hay elementos hechos aún';

  @override
  String get emptyOldMessage => '✅ No hay tareas antiguas';

  @override
  String get noItems => 'Sin elementos';

  @override
  String get actionItemMarkedIncomplete => 'Marcado como incompleto';

  @override
  String get actionItemCompleted => 'Tarea completada';

  @override
  String get deleteActionItemTitle => 'Eliminar elemento de acción';

  @override
  String get deleteActionItemMessage =>
      '¿Está seguro de que desea eliminar este elemento de acción?';

  @override
  String get deleteSelectedItemsTitle => 'Borrar seleccionados';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return '¿Seguro que quieres borrar $count tareas seleccionadas?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'Tarea \"$description\" borrada';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count tareas borradas';
  }

  @override
  String get failedToDeleteItem => 'Error al borrar tarea';

  @override
  String get failedToDeleteItems => 'Error al borrar elementos';

  @override
  String get failedToDeleteSomeItems => 'Error al borrar algunos elementos';

  @override
  String get welcomeActionItemsTitle => 'Listo para Acciones';

  @override
  String get welcomeActionItemsDescription =>
      'Tu IA extrae tareas automáticamente.';

  @override
  String get autoExtractionFeature =>
      'Extraído automáticamente de conversaciones';

  @override
  String get editSwipeFeature => 'Toca, desliza, gestiona';

  @override
  String itemsSelected(int count) {
    return '$count seleccionados';
  }

  @override
  String get selectAll => 'Seleccionar todo';

  @override
  String get deleteSelected => 'Borrar seleccionados';

  @override
  String get searchMemories => 'Buscar recuerdos...';

  @override
  String get memoryDeleted => 'Recuerdo borrado.';

  @override
  String get undo => 'Deshacer';

  @override
  String get noMemoriesYet => '🧠 Aún no hay recuerdos';

  @override
  String get noAutoMemories => 'No hay recuerdos automáticos';

  @override
  String get noManualMemories => 'No hay recuerdos manuales';

  @override
  String get noMemoriesInCategories => 'No hay recuerdos en estas categorías';

  @override
  String get noMemoriesFound => '🔍 No se encontraron recuerdos';

  @override
  String get addFirstMemory => 'Añade tu primer recuerdo';

  @override
  String get clearMemoryTitle => '¿Borrar memoria de Omi?';

  @override
  String get clearMemoryMessage =>
      '¿Seguro que quieres borrar la memoria de Omi? No se puede deshacer.';

  @override
  String get clearMemoryButton => 'Borrar memoria';

  @override
  String get memoryClearedSuccess => 'Memoria borrada';

  @override
  String get noMemoriesToDelete => 'No hay recuerdos para eliminar';

  @override
  String get createMemoryTooltip => 'Crear nuevo recuerdo';

  @override
  String get createActionItemTooltip => 'Crear nueva tarea';

  @override
  String get memoryManagement => 'Gestión de memoria';

  @override
  String get filterMemories => 'Filtrar recuerdos';

  @override
  String totalMemoriesCount(int count) {
    return 'Tienes $count recuerdos';
  }

  @override
  String get publicMemories => 'Recuerdos públicos';

  @override
  String get privateMemories => 'Recuerdos privados';

  @override
  String get makeAllPrivate => 'Hacer todo privado';

  @override
  String get makeAllPublic => 'Hacer todo público';

  @override
  String get deleteAllMemories => 'Eliminar todos los recuerdos';

  @override
  String get allMemoriesPrivateResult =>
      'Todos los recuerdos son ahora privados';

  @override
  String get allMemoriesPublicResult =>
      'Todos los recuerdos son ahora públicos';

  @override
  String get newMemory => '✨ Nueva memoria';

  @override
  String get editMemory => '✏️ Editar memoria';

  @override
  String get memoryContentHint => 'Me gusta el helado...';

  @override
  String get failedToSaveMemory => 'Error al guardar.';

  @override
  String get saveMemory => 'Guardar recuerdo';

  @override
  String get retry => 'Retry';

  @override
  String get createActionItem => 'Crear tarea';

  @override
  String get editActionItem => 'Editar tarea';

  @override
  String get actionItemDescriptionHint => '¿Qué hay que hacer?';

  @override
  String get actionItemDescriptionEmpty =>
      'La descripción no puede estar vacía.';

  @override
  String get actionItemUpdated => 'Tarea actualizada';

  @override
  String get failedToUpdateActionItem => 'Error al actualizar la tarea';

  @override
  String get actionItemCreated => 'Tarea creada';

  @override
  String get failedToCreateActionItem => 'Error al crear la tarea';

  @override
  String get dueDate => 'Fecha de vencimiento';

  @override
  String get time => 'Hora';

  @override
  String get addDueDate => 'Añadir fecha límite';

  @override
  String get pressDoneToSave => 'Pulsa Hecho para guardar';

  @override
  String get pressDoneToCreate => 'Pulsa Hecho para crear';

  @override
  String get filterAll => 'Todos';

  @override
  String get filterSystem => 'Sobre ti';

  @override
  String get filterInteresting => 'Perspectivas';

  @override
  String get filterManual => 'Manual';

  @override
  String get completed => 'Completado';

  @override
  String get markComplete => 'Marcar como completado';

  @override
  String get actionItemDeleted => 'Elemento de acción eliminado';

  @override
  String get failedToDeleteActionItem => 'Error al eliminar la tarea';

  @override
  String get deleteActionItemConfirmTitle => 'Borrar tarea';

  @override
  String get deleteActionItemConfirmMessage =>
      '¿Seguro que quieres borrar esta tarea?';

  @override
  String get appLanguage => 'Idioma de la App';

  @override
  String get appInterfaceSectionTitle => 'INTERFAZ DE LA APLICACIÓN';

  @override
  String get speechTranscriptionSectionTitle => 'VOZ Y TRANSCRIPCIÓN';

  @override
  String get languageSettingsHelperText =>
      'El idioma de la aplicación cambia los menús y botones. El idioma de voz afecta cómo se transcriben tus grabaciones.';

  @override
  String get translationNotice => 'Aviso de traducción';

  @override
  String get translationNoticeMessage =>
      'Omi traduce las conversaciones a tu idioma principal. Actualízalo en cualquier momento en Ajustes → Perfiles.';

  @override
  String get pleaseCheckInternetConnection =>
      'Por favor, verifica tu conexión a Internet e inténtalo de nuevo';

  @override
  String get pleaseSelectReason => 'Por favor, selecciona un motivo';

  @override
  String get tellUsMoreWhatWentWrong => 'Cuéntanos más sobre qué salió mal...';

  @override
  String get selectText => 'Seleccionar texto';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Máximo $count objetivos permitidos';
  }

  @override
  String get conversationCannotBeMerged =>
      'Esta conversación no se puede fusionar (bloqueada o ya en proceso de fusión)';

  @override
  String get pleaseEnterFolderName =>
      'Por favor, introduce un nombre de carpeta';

  @override
  String get failedToCreateFolder => 'Error al crear la carpeta';

  @override
  String get failedToUpdateFolder => 'Error al actualizar la carpeta';

  @override
  String get folderName => 'Nombre de carpeta';

  @override
  String get descriptionOptional => 'Description (optional)';

  @override
  String get failedToDeleteFolder => 'Error al eliminar la carpeta';

  @override
  String get editFolder => 'Editar carpeta';

  @override
  String get deleteFolder => 'Eliminar carpeta';

  @override
  String get transcriptCopiedToClipboard =>
      'Transcripción copiada al portapapeles';

  @override
  String get summaryCopiedToClipboard => 'Resumen copiado al portapapeles';

  @override
  String get conversationUrlCouldNotBeShared =>
      'No se pudo compartir la URL de la conversación.';

  @override
  String get urlCopiedToClipboard => 'URL copiada al portapapeles';

  @override
  String get exportTranscript => 'Exportar transcripción';

  @override
  String get exportSummary => 'Exportar resumen';

  @override
  String get exportButton => 'Exportar';

  @override
  String get actionItemsCopiedToClipboard =>
      'Elementos de acción copiados al portapapeles';

  @override
  String get summarize => 'Resumir';

  @override
  String get generateSummary => 'Generar resumen';

  @override
  String get conversationNotFoundOrDeleted =>
      'Conversación no encontrada o ha sido eliminada';

  @override
  String get deleteMemory => 'Eliminar memoria';

  @override
  String get thisActionCannotBeUndone => 'Esta acción no se puede deshacer.';

  @override
  String memoriesCount(int count) {
    return '$count memorias';
  }

  @override
  String get noMemoriesInCategory => 'Aún no hay memorias en esta categoría';

  @override
  String get addYourFirstMemory => 'Añade tu primer recuerdo';

  @override
  String get firmwareDisconnectUsb => 'Desconectar USB';

  @override
  String get firmwareUsbWarning =>
      'La conexión USB durante las actualizaciones puede dañar tu dispositivo.';

  @override
  String get firmwareBatteryAbove15 => 'Batería superior al 15%';

  @override
  String get firmwareEnsureBattery =>
      'Asegúrate de que tu dispositivo tiene un 15% de batería.';

  @override
  String get firmwareStableConnection => 'Conexión estable';

  @override
  String get firmwareConnectWifi => 'Conéctate a WiFi o datos móviles.';

  @override
  String failedToStartUpdate(String error) {
    return 'Error al iniciar la actualización: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'Antes de actualizar, asegúrate:';

  @override
  String get confirmed => '¡Confirmado!';

  @override
  String get release => 'Soltar';

  @override
  String get slideToUpdate => 'Desliza para actualizar';

  @override
  String copiedToClipboard(String title) {
    return '$title copiado al portapapeles';
  }

  @override
  String get batteryLevel => 'Nivel de batería';

  @override
  String get productUpdate => 'Actualización del producto';

  @override
  String get offline => 'Sin conexión';

  @override
  String get available => 'Disponible';

  @override
  String get unpairDeviceDialogTitle => 'Desvincular dispositivo';

  @override
  String get unpairDeviceDialogMessage =>
      'Esto desvinculará el dispositivo para que pueda conectarse a otro teléfono. Deberás ir a Configuración > Bluetooth y olvidar el dispositivo para completar el proceso.';

  @override
  String get unpair => 'Desvincular';

  @override
  String get unpairAndForgetDevice => 'Desvincular y olvidar dispositivo';

  @override
  String get unknownDevice => 'Unknown';

  @override
  String get unknown => 'Desconocido';

  @override
  String get productName => 'Nombre del producto';

  @override
  String get serialNumber => 'Número de serie';

  @override
  String get connected => 'Conectado';

  @override
  String get privacyPolicyTitle => 'Política de privacidad';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label copiado';
  }

  @override
  String get noApiKeysYet =>
      'Aún no hay claves API. Crea una para integrar con tu aplicación.';

  @override
  String get createKeyToGetStarted => 'Crea una clave para comenzar';

  @override
  String get persona => 'Persona';

  @override
  String get configureYourAiPersona => 'Configura tu persona de IA';

  @override
  String get configureSttProvider => 'Configurar proveedor STT';

  @override
  String get setWhenConversationsAutoEnd =>
      'Establece cuándo terminan las conversaciones automáticamente';

  @override
  String get importDataFromOtherSources => 'Importar datos de otras fuentes';

  @override
  String get debugAndDiagnostics => 'Depuración y Diagnóstico';

  @override
  String get autoDeletesAfter3Days =>
      'Se elimina automáticamente después de 3 días';

  @override
  String get helpsDiagnoseIssues => 'Ayuda a diagnosticar problemas';

  @override
  String get exportStartedMessage =>
      'Exportación iniciada. Esto puede tardar unos segundos...';

  @override
  String get exportConversationsToJson =>
      'Exportar conversaciones a un archivo JSON';

  @override
  String get knowledgeGraphDeletedSuccess =>
      'Grafo de conocimiento eliminado exitosamente';

  @override
  String failedToDeleteGraph(String error) {
    return 'Error al eliminar el grafo: $error';
  }

  @override
  String get clearAllNodesAndConnections =>
      'Borrar todos los nodos y conexiones';

  @override
  String get addToClaudeDesktopConfig => 'Agregar a claude_desktop_config.json';

  @override
  String get connectAiAssistantsToData =>
      'Conecta asistentes de IA a tus datos';

  @override
  String get useYourMcpApiKey => 'Usa tu clave API de MCP';

  @override
  String get realTimeTranscript => 'Transcripción en Tiempo Real';

  @override
  String get experimental => 'Experimental';

  @override
  String get transcriptionDiagnostics => 'Diagnóstico de Transcripción';

  @override
  String get detailedDiagnosticMessages => 'Mensajes de diagnóstico detallados';

  @override
  String get autoCreateSpeakers => 'Crear Hablantes Automáticamente';

  @override
  String get autoCreateWhenNameDetected =>
      'Crear automáticamente cuando se detecte un nombre';

  @override
  String get followUpQuestions => 'Preguntas de Seguimiento';

  @override
  String get suggestQuestionsAfterConversations =>
      'Sugerir preguntas después de las conversaciones';

  @override
  String get goalTracker => 'Rastreador de Objetivos';

  @override
  String get trackPersonalGoalsOnHomepage =>
      'Sigue tus metas personales en la página de inicio';

  @override
  String get dailyReflection => 'Reflexión diaria';

  @override
  String get get9PmReminderToReflect =>
      'Recibe un recordatorio a las 9 PM para reflexionar sobre tu día';

  @override
  String get actionItemDescriptionCannotBeEmpty =>
      'La descripción del elemento de acción no puede estar vacía';

  @override
  String get saved => 'Guardado';

  @override
  String get overdue => 'Atrasado';

  @override
  String get failedToUpdateDueDate =>
      'Error al actualizar la fecha de vencimiento';

  @override
  String get markIncomplete => 'Marcar como incompleto';

  @override
  String get editDueDate => 'Editar fecha de vencimiento';

  @override
  String get setDueDate => 'Establecer fecha de vencimiento';

  @override
  String get clearDueDate => 'Borrar fecha de vencimiento';

  @override
  String get failedToClearDueDate => 'Error al borrar la fecha de vencimiento';

  @override
  String get mondayAbbr => 'Lun';

  @override
  String get tuesdayAbbr => 'Mar';

  @override
  String get wednesdayAbbr => 'Mié';

  @override
  String get thursdayAbbr => 'Jue';

  @override
  String get fridayAbbr => 'Vie';

  @override
  String get saturdayAbbr => 'Sáb';

  @override
  String get sundayAbbr => 'Dom';

  @override
  String get howDoesItWork => '¿Cómo funciona?';

  @override
  String get sdCardSyncDescription =>
      'La sincronización de la tarjeta SD importará tus recuerdos de la tarjeta SD a la aplicación';

  @override
  String get checksForAudioFiles =>
      'Comprueba archivos de audio en la tarjeta SD';

  @override
  String get omiSyncsAudioFiles =>
      'Omi luego sincroniza los archivos de audio con el servidor';

  @override
  String get serverProcessesAudio =>
      'El servidor procesa los archivos de audio y crea recuerdos';

  @override
  String get youreAllSet => '¡Estás listo!';

  @override
  String get welcomeToOmiDescription =>
      '¡Bienvenido a Omi! Tu compañero de IA está listo para ayudarte con conversaciones, tareas y más.';

  @override
  String get startUsingOmi => 'Comenzar a usar Omi';

  @override
  String get back => 'Atrás';

  @override
  String get keyboardShortcuts => 'Atajos de Teclado';

  @override
  String get toggleControlBar => 'Alternar barra de control';

  @override
  String get pressKeys => 'Presiona teclas...';

  @override
  String get cmdRequired => '⌘ requerido';

  @override
  String get invalidKey => 'Tecla inválida';

  @override
  String get space => 'Espacio';

  @override
  String get search => 'Buscar';

  @override
  String get searchPlaceholder => 'Buscar...';

  @override
  String get untitledConversation => 'Conversación sin título';

  @override
  String countRemaining(String count) {
    return '$count restantes';
  }

  @override
  String get addGoal => 'Añadir objetivo';

  @override
  String get editGoal => 'Editar objetivo';

  @override
  String get icon => 'Icono';

  @override
  String get goalTitle => 'Título del objetivo';

  @override
  String get current => 'Actual';

  @override
  String get target => 'Objetivo';

  @override
  String get saveGoal => 'Guardar';

  @override
  String get goals => 'Objetivos';

  @override
  String get tapToAddGoal => 'Toca para añadir un objetivo';

  @override
  String welcomeBack(String name) {
    return 'Bienvenido de nuevo, $name';
  }

  @override
  String get yourConversations => 'Tus conversaciones';

  @override
  String get reviewAndManageConversations =>
      'Revisa y gestiona tus conversaciones capturadas';

  @override
  String get startCapturingConversations =>
      'Comienza a capturar conversaciones con tu dispositivo Omi para verlas aquí.';

  @override
  String get useMobileAppToCapture =>
      'Usa tu aplicación móvil para capturar audio';

  @override
  String get conversationsProcessedAutomatically =>
      'Las conversaciones se procesan automáticamente';

  @override
  String get getInsightsInstantly =>
      'Obtén información y resúmenes al instante';

  @override
  String get showAll => 'Mostrar todo →';

  @override
  String get noTasksForToday =>
      'No hay tareas para hoy.\\nPregúntale a Omi por más tareas o créalas manualmente.';

  @override
  String get dailyScore => 'PUNTUACIÓN DIARIA';

  @override
  String get dailyScoreDescription =>
      'Una puntuación para ayudarte\na enfocarte mejor en la ejecución.';

  @override
  String get searchResults => 'Resultados de búsqueda';

  @override
  String get actionItems => 'Elementos de acción';

  @override
  String get tasksToday => 'Hoy';

  @override
  String get tasksTomorrow => 'Mañana';

  @override
  String get tasksNoDeadline => 'Sin plazo';

  @override
  String get tasksLater => 'Más tarde';

  @override
  String get loadingTasks => 'Cargando tareas...';

  @override
  String get tasks => 'Tareas';

  @override
  String get swipeTasksToIndent =>
      'Desliza tareas para sangrar, arrastra entre categorías';

  @override
  String get create => 'Crear';

  @override
  String get noTasksYet => 'Aún no hay tareas';

  @override
  String get tasksFromConversationsWillAppear =>
      'Las tareas de tus conversaciones aparecerán aquí.\nHaz clic en Crear para añadir una manualmente.';

  @override
  String get monthJan => 'Ene';

  @override
  String get monthFeb => 'Feb';

  @override
  String get monthMar => 'Mar';

  @override
  String get monthApr => 'Abr';

  @override
  String get monthMay => 'Mayo';

  @override
  String get monthJun => 'Jun';

  @override
  String get monthJul => 'Jul';

  @override
  String get monthAug => 'Ago';

  @override
  String get monthSep => 'Sep';

  @override
  String get monthOct => 'Oct';

  @override
  String get monthNov => 'Nov';

  @override
  String get monthDec => 'Dic';

  @override
  String get timePM => 'PM';

  @override
  String get timeAM => 'AM';

  @override
  String get actionItemUpdatedSuccessfully => 'Tarea actualizada correctamente';

  @override
  String get actionItemCreatedSuccessfully => 'Tarea creada correctamente';

  @override
  String get actionItemDeletedSuccessfully => 'Tarea eliminada correctamente';

  @override
  String get deleteActionItem => 'Eliminar tarea';

  @override
  String get deleteActionItemConfirmation =>
      '¿Estás seguro de que quieres eliminar esta tarea? Esta acción no se puede deshacer.';

  @override
  String get enterActionItemDescription =>
      'Ingresa la descripción de la tarea...';

  @override
  String get markAsCompleted => 'Marcar como completada';

  @override
  String get setDueDateAndTime => 'Establecer fecha y hora de vencimiento';

  @override
  String get reloadingApps => 'Recargando aplicaciones...';

  @override
  String get loadingApps => 'Cargando aplicaciones...';

  @override
  String get browseInstallCreateApps => 'Explora, instala y crea aplicaciones';

  @override
  String get all => 'All';

  @override
  String get open => 'Abrir';

  @override
  String get install => 'Instalar';

  @override
  String get noAppsAvailable => 'No hay aplicaciones disponibles';

  @override
  String get unableToLoadApps => 'No se pueden cargar las aplicaciones';

  @override
  String get tryAdjustingSearchTermsOrFilters =>
      'Intenta ajustar tus términos de búsqueda o filtros';

  @override
  String get checkBackLaterForNewApps =>
      'Vuelve más tarde para ver nuevas aplicaciones';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain =>
      'Por favor, verifica tu conexión a Internet e inténtalo de nuevo';

  @override
  String get createNewApp => 'Crear nueva aplicación';

  @override
  String get buildSubmitCustomOmiApp =>
      'Construye y envía tu aplicación Omi personalizada';

  @override
  String get submittingYourApp => 'Enviando tu aplicación...';

  @override
  String get preparingFormForYou => 'Preparando el formulario para ti...';

  @override
  String get appDetails => 'Detalles de la aplicación';

  @override
  String get paymentDetails => 'Detalles de pago';

  @override
  String get previewAndScreenshots => 'Vista previa y capturas de pantalla';

  @override
  String get appCapabilities => 'Capacidades de la aplicación';

  @override
  String get aiPrompts => 'Indicaciones de IA';

  @override
  String get chatPrompt => 'Indicación de chat';

  @override
  String get chatPromptPlaceholder =>
      'Eres una aplicación increíble, tu trabajo es responder a las consultas de los usuarios y hacerlos sentir bien...';

  @override
  String get conversationPrompt => 'Indicación de conversación';

  @override
  String get conversationPromptPlaceholder =>
      'Eres una aplicación increíble, se te dará una transcripción y resumen de una conversación...';

  @override
  String get notificationScopes => 'Ámbitos de notificación';

  @override
  String get appPrivacyAndTerms => 'Privacidad y términos de la aplicación';

  @override
  String get makeMyAppPublic => 'Hacer pública mi aplicación';

  @override
  String get submitAppTermsAgreement =>
      'Al enviar esta aplicación, acepto los Términos de Servicio y la Política de Privacidad de Omi AI';

  @override
  String get submitApp => 'Enviar aplicación';

  @override
  String get needHelpGettingStarted => '¿Necesitas ayuda para comenzar?';

  @override
  String get clickHereForAppBuildingGuides =>
      'Haz clic aquí para guías de creación de aplicaciones y documentación';

  @override
  String get submitAppQuestion => '¿Enviar aplicación?';

  @override
  String get submitAppPublicDescription =>
      'Tu aplicación será revisada y publicada. Puedes comenzar a usarla inmediatamente, ¡incluso durante la revisión!';

  @override
  String get submitAppPrivateDescription =>
      'Tu aplicación será revisada y estará disponible para ti de forma privada. Puedes comenzar a usarla inmediatamente, ¡incluso durante la revisión!';

  @override
  String get startEarning => '¡Comienza a ganar! 💰';

  @override
  String get connectStripeOrPayPal =>
      'Conecta Stripe o PayPal para recibir pagos por tu aplicación.';

  @override
  String get connectNow => 'Conectar ahora';

  @override
  String get installsCount => 'Instalaciones';

  @override
  String get uninstallApp => 'Desinstalar aplicación';

  @override
  String get subscribe => 'Suscribirse';

  @override
  String get dataAccessNotice => 'Aviso de acceso a datos';

  @override
  String get dataAccessWarning =>
      'Esta aplicación accederá a sus datos. Omi AI no es responsable de cómo esta aplicación utiliza, modifica o elimina sus datos';

  @override
  String get installApp => 'Instalar aplicación';

  @override
  String get betaTesterNotice =>
      'Eres un probador beta de esta aplicación. Aún no es pública. Será pública una vez aprobada.';

  @override
  String get appUnderReviewOwner =>
      'Tu aplicación está en revisión y solo visible para ti. Será pública una vez aprobada.';

  @override
  String get appRejectedNotice =>
      'Tu aplicación ha sido rechazada. Por favor actualiza los detalles de la aplicación y vuelve a enviarla para revisión.';

  @override
  String get setupSteps => 'Pasos de configuración';

  @override
  String get setupInstructions => 'Instrucciones de configuración';

  @override
  String get integrationInstructions => 'Instrucciones de integración';

  @override
  String get preview => 'Vista previa';

  @override
  String get aboutTheApp => 'Acerca de la app';

  @override
  String get aboutThePersona => 'Acerca de la persona';

  @override
  String get chatPersonality => 'Personalidad del chat';

  @override
  String get ratingsAndReviews => 'Valoraciones y reseñas';

  @override
  String get noRatings => 'sin calificaciones';

  @override
  String ratingsCount(String count) {
    return '$count+ calificaciones';
  }

  @override
  String get errorActivatingApp => 'Error al activar la aplicación';

  @override
  String get integrationSetupRequired =>
      'Si esta es una aplicación de integración, asegúrese de que la configuración esté completa.';

  @override
  String get installed => 'Instalado';

  @override
  String get appIdLabel => 'ID de la aplicación';

  @override
  String get appNameLabel => 'Nombre de la aplicación';

  @override
  String get appNamePlaceholder => 'Mi aplicación increíble';

  @override
  String get pleaseEnterAppName =>
      'Por favor, ingrese el nombre de la aplicación';

  @override
  String get categoryLabel => 'Categoría';

  @override
  String get selectCategory => 'Seleccionar categoría';

  @override
  String get descriptionLabel => 'Descripción';

  @override
  String get appDescriptionPlaceholder =>
      'Mi aplicación increíble es una aplicación genial que hace cosas asombrosas. ¡Es la mejor aplicación!';

  @override
  String get pleaseProvideValidDescription =>
      'Por favor, proporcione una descripción válida';

  @override
  String get appPricingLabel => 'Precio de la aplicación';

  @override
  String get noneSelected => 'Ninguna seleccionada';

  @override
  String get appIdCopiedToClipboard =>
      'ID de la aplicación copiado al portapapeles';

  @override
  String get appCategoryModalTitle => 'Categoría de la aplicación';

  @override
  String get pricingFree => 'Gratis';

  @override
  String get pricingPaid => 'De pago';

  @override
  String get loadingCapabilities => 'Cargando capacidades...';

  @override
  String get filterInstalled => 'Instaladas';

  @override
  String get filterMyApps => 'Mis aplicaciones';

  @override
  String get clearSelection => 'Borrar selección';

  @override
  String get filterCategory => 'Categoría';

  @override
  String get rating4PlusStars => '4+ estrellas';

  @override
  String get rating3PlusStars => '3+ estrellas';

  @override
  String get rating2PlusStars => '2+ estrellas';

  @override
  String get rating1PlusStars => '1+ estrellas';

  @override
  String get filterRating => 'Valoración';

  @override
  String get filterCapabilities => 'Capacidades';

  @override
  String get noNotificationScopesAvailable =>
      'No hay ámbitos de notificación disponibles';

  @override
  String get popularApps => 'Aplicaciones populares';

  @override
  String get pleaseProvidePrompt => 'Por favor, proporciona una indicación';

  @override
  String chatWithAppName(String appName) {
    return 'Chat con $appName';
  }

  @override
  String get defaultAiAssistant => 'Asistente de IA predeterminado';

  @override
  String get readyToChat => '✨ ¡Listo para chatear!';

  @override
  String get connectionNeeded => '🌐 Conexión necesaria';

  @override
  String get startConversation =>
      'Comienza una conversación y deja que la magia comience';

  @override
  String get checkInternetConnection =>
      'Por favor, verifica tu conexión a Internet';

  @override
  String get wasThisHelpful => '¿Fue esto útil?';

  @override
  String get thankYouForFeedback => '¡Gracias por tus comentarios!';

  @override
  String get maxFilesUploadError => 'Solo puedes subir 4 archivos a la vez';

  @override
  String get attachedFiles => '📎 Archivos adjuntos';

  @override
  String get takePhoto => 'Tomar foto';

  @override
  String get captureWithCamera => 'Capturar con cámara';

  @override
  String get selectImages => 'Seleccionar imágenes';

  @override
  String get chooseFromGallery => 'Elegir de la galería';

  @override
  String get selectFile => 'Seleccionar un archivo';

  @override
  String get chooseAnyFileType => 'Elegir cualquier tipo de archivo';

  @override
  String get cannotReportOwnMessages =>
      'No puedes reportar tus propios mensajes';

  @override
  String get messageReportedSuccessfully => '✅ Mensaje reportado exitosamente';

  @override
  String get confirmReportMessage =>
      '¿Estás seguro de que quieres reportar este mensaje?';

  @override
  String get selectChatAssistant => 'Seleccionar asistente de chat';

  @override
  String get enableMoreApps => 'Habilitar más aplicaciones';

  @override
  String get chatCleared => 'Chat borrado';

  @override
  String get clearChatTitle => '¿Borrar chat?';

  @override
  String get confirmClearChat =>
      '¿Estás seguro de que quieres borrar el chat? Esta acción no se puede deshacer.';

  @override
  String get copy => 'Copiar';

  @override
  String get share => 'Compartir';

  @override
  String get report => 'Reportar';

  @override
  String get microphonePermissionRequired =>
      'Se requiere permiso de micrófono para la grabación de voz.';

  @override
  String get microphonePermissionDenied =>
      'Permiso de micrófono denegado. Por favor, conceda permiso en Preferencias del Sistema > Privacidad y Seguridad > Micrófono.';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'Error al verificar permiso de micrófono: $error';
  }

  @override
  String get failedToTranscribeAudio => 'Error al transcribir audio';

  @override
  String get transcribing => 'Transcribiendo...';

  @override
  String get transcriptionFailed => 'Transcripción fallida';

  @override
  String get discardedConversation => 'Conversación descartada';

  @override
  String get at => 'a las';

  @override
  String get from => 'desde';

  @override
  String get copied => '¡Copiado!';

  @override
  String get copyLink => 'Copiar enlace';

  @override
  String get hideTranscript => 'Ocultar transcripción';

  @override
  String get viewTranscript => 'Ver transcripción';

  @override
  String get conversationDetails => 'Detalles de la conversación';

  @override
  String get transcript => 'Transcripción';

  @override
  String segmentsCount(int count) {
    return '$count segmentos';
  }

  @override
  String get noTranscriptAvailable => 'No hay transcripción disponible';

  @override
  String get noTranscriptMessage => 'Esta conversación no tiene transcripción.';

  @override
  String get conversationUrlCouldNotBeGenerated =>
      'No se pudo generar la URL de la conversación.';

  @override
  String get failedToGenerateConversationLink =>
      'Error al generar el enlace de la conversación';

  @override
  String get failedToGenerateShareLink =>
      'Error al generar el enlace para compartir';

  @override
  String get reloadingConversations => 'Recargando conversaciones...';

  @override
  String get user => 'Usuario';

  @override
  String get starred => 'Destacado';

  @override
  String get date => 'Fecha';

  @override
  String get noResultsFound => 'No se encontraron resultados';

  @override
  String get tryAdjustingSearchTerms =>
      'Intenta ajustar tus términos de búsqueda';

  @override
  String get starConversationsToFindQuickly =>
      'Marca conversaciones con estrella para encontrarlas rápidamente aquí';

  @override
  String noConversationsOnDate(String date) {
    return 'No hay conversaciones el $date';
  }

  @override
  String get trySelectingDifferentDate =>
      'Intenta seleccionar una fecha diferente';

  @override
  String get conversations => 'Conversaciones';

  @override
  String get chat => 'Chat';

  @override
  String get actions => 'Acciones';

  @override
  String get syncAvailable => 'Sincronización disponible';

  @override
  String get referAFriend => 'Recomendar a un amigo';

  @override
  String get help => 'Ayuda';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'Actualizar a Pro';

  @override
  String get getOmiDevice => 'Get Omi Device';

  @override
  String get wearableAiCompanion => 'Compañero de IA portátil';

  @override
  String get loadingMemories => 'Cargando recuerdos...';

  @override
  String get allMemories => 'Todos los recuerdos';

  @override
  String get aboutYou => 'Sobre ti';

  @override
  String get manual => 'Manual';

  @override
  String get loadingYourMemories => 'Cargando tus recuerdos...';

  @override
  String get createYourFirstMemory => 'Crea tu primer recuerdo para comenzar';

  @override
  String get tryAdjustingFilter => 'Intenta ajustar tu búsqueda o filtro';

  @override
  String get whatWouldYouLikeToRemember => '¿Qué te gustaría recordar?';

  @override
  String get category => 'Categoría';

  @override
  String get public => 'Público';

  @override
  String get failedToSaveCheckConnection =>
      'Error al guardar. Por favor, verifica tu conexión.';

  @override
  String get createMemory => 'Crear memoria';

  @override
  String get deleteMemoryConfirmation =>
      '¿Estás seguro de que deseas eliminar esta memoria? Esta acción no se puede deshacer.';

  @override
  String get makePrivate => 'Hacer privado';

  @override
  String get organizeAndControlMemories => 'Organiza y controla tus recuerdos';

  @override
  String get total => 'Total';

  @override
  String get makeAllMemoriesPrivate => 'Hacer todos los recuerdos privados';

  @override
  String get setAllMemoriesToPrivate =>
      'Establecer todos los recuerdos como privados';

  @override
  String get makeAllMemoriesPublic => 'Hacer todos los recuerdos públicos';

  @override
  String get setAllMemoriesToPublic =>
      'Establecer todos los recuerdos como públicos';

  @override
  String get permanentlyRemoveAllMemories =>
      'Eliminar permanentemente todos los recuerdos de Omi';

  @override
  String get allMemoriesAreNowPrivate =>
      'Todos los recuerdos son ahora privados';

  @override
  String get allMemoriesAreNowPublic =>
      'Todos los recuerdos son ahora públicos';

  @override
  String get clearOmisMemory => 'Borrar la memoria de Omi';

  @override
  String clearMemoryConfirmation(int count) {
    return '¿Estás seguro de que deseas borrar la memoria de Omi? Esta acción no se puede deshacer y eliminará permanentemente todos los $count recuerdos.';
  }

  @override
  String get omisMemoryCleared => 'La memoria de Omi sobre ti ha sido borrada';

  @override
  String get welcomeToOmi => 'Bienvenido a Omi';

  @override
  String get continueWithApple => 'Continuar con Apple';

  @override
  String get continueWithGoogle => 'Continuar con Google';

  @override
  String get byContinuingYouAgree => 'Al continuar, aceptas nuestros ';

  @override
  String get termsOfService => 'Términos de servicio';

  @override
  String get and => ' y ';

  @override
  String get dataAndPrivacy => 'Datos y privacidad';

  @override
  String get secureAuthViaAppleId => 'Autenticación segura vía Apple ID';

  @override
  String get secureAuthViaGoogleAccount =>
      'Autenticación segura vía cuenta de Google';

  @override
  String get whatWeCollect => 'Qué recopilamos';

  @override
  String get dataCollectionMessage =>
      'Al continuar, tus conversaciones, grabaciones e información personal se almacenarán de forma segura en nuestros servidores para proporcionar información impulsada por IA y habilitar todas las funciones de la aplicación.';

  @override
  String get dataProtection => 'Protección de datos';

  @override
  String get yourDataIsProtected =>
      'Tus datos están protegidos y regidos por nuestra ';

  @override
  String get pleaseSelectYourPrimaryLanguage =>
      'Por favor, seleccione su idioma principal';

  @override
  String get chooseYourLanguage => 'Elige tu idioma';

  @override
  String get selectPreferredLanguageForBestExperience =>
      'Seleccione su idioma preferido para la mejor experiencia Omi';

  @override
  String get searchLanguages => 'Buscar idiomas...';

  @override
  String get selectALanguage => 'Seleccione un idioma';

  @override
  String get tryDifferentSearchTerm =>
      'Pruebe con un término de búsqueda diferente';

  @override
  String get pleaseEnterYourName => 'Por favor, introduce tu nombre';

  @override
  String get nameMustBeAtLeast2Characters =>
      'El nombre debe tener al menos 2 caracteres';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'Díganos cómo le gustaría que nos dirigiéramos a usted. Esto ayuda a personalizar su experiencia Omi.';

  @override
  String charactersCount(int count) {
    return '$count caracteres';
  }

  @override
  String get enableFeaturesForBestExperience =>
      'Active funciones para la mejor experiencia Omi en su dispositivo.';

  @override
  String get microphoneAccess => 'Acceso al micrófono';

  @override
  String get recordAudioConversations => 'Grabar conversaciones de audio';

  @override
  String get microphoneAccessDescription =>
      'Omi necesita acceso al micrófono para grabar sus conversaciones y proporcionar transcripciones.';

  @override
  String get screenRecording => 'Grabación de pantalla';

  @override
  String get captureSystemAudioFromMeetings =>
      'Capturar audio del sistema de reuniones';

  @override
  String get screenRecordingDescription =>
      'Omi necesita permiso de grabación de pantalla para capturar el audio del sistema de sus reuniones basadas en navegador.';

  @override
  String get accessibility => 'Accesibilidad';

  @override
  String get detectBrowserBasedMeetings =>
      'Detectar reuniones basadas en navegador';

  @override
  String get accessibilityDescription =>
      'Omi necesita permiso de accesibilidad para detectar cuándo se une a reuniones de Zoom, Meet o Teams en su navegador.';

  @override
  String get pleaseWait => 'Por favor, espere...';

  @override
  String get joinTheCommunity => '¡Únete a la comunidad!';

  @override
  String get loadingProfile => 'Cargando perfil...';

  @override
  String get profileSettings => 'Configuración del perfil';

  @override
  String get noEmailSet => 'Sin correo electrónico configurado';

  @override
  String get userIdCopiedToClipboard => 'ID de usuario copiado';

  @override
  String get yourInformation => 'Tu Información';

  @override
  String get setYourName => 'Establecer tu nombre';

  @override
  String get changeYourName => 'Cambiar tu nombre';

  @override
  String get manageYourOmiPersona => 'Gestiona tu persona Omi';

  @override
  String get voiceAndPeople => 'Voz y Personas';

  @override
  String get teachOmiYourVoice => 'Enseña a Omi tu voz';

  @override
  String get tellOmiWhoSaidIt => 'Dile a Omi quién lo dijo 🗣️';

  @override
  String get payment => 'Pago';

  @override
  String get addOrChangeYourPaymentMethod => 'Agregar o cambiar método de pago';

  @override
  String get preferences => 'Preferencias';

  @override
  String get helpImproveOmiBySharing =>
      'Ayuda a mejorar Omi compartiendo datos de análisis anonimizados';

  @override
  String get deleteAccount => 'Eliminar Cuenta';

  @override
  String get deleteYourAccountAndAllData =>
      'Elimina tu cuenta y todos los datos';

  @override
  String get clearLogs => 'Borrar registros';

  @override
  String get debugLogsCleared => 'Registros de depuración borrados';

  @override
  String get exportConversations => 'Exportar conversaciones';

  @override
  String get exportAllConversationsToJson =>
      'Exporte todas sus conversaciones a un archivo JSON.';

  @override
  String get conversationsExportStarted =>
      'Exportación de conversaciones iniciada. Esto puede tardar unos segundos, por favor espere.';

  @override
  String get mcpDescription =>
      'Para conectar Omi con otras aplicaciones para leer, buscar y administrar sus recuerdos y conversaciones. Cree una clave para comenzar.';

  @override
  String get apiKeys => 'Claves API';

  @override
  String errorLabel(String error) {
    return 'Error: $error';
  }

  @override
  String get noApiKeysFound =>
      'No se encontraron claves API. Cree una para comenzar.';

  @override
  String get advancedSettings => 'Configuración avanzada';

  @override
  String get triggersWhenNewConversationCreated =>
      'Se activa cuando se crea una nueva conversación.';

  @override
  String get triggersWhenNewTranscriptReceived =>
      'Se activa cuando se recibe una nueva transcripción.';

  @override
  String get realtimeAudioBytes => 'Bytes de audio en tiempo real';

  @override
  String get triggersWhenAudioBytesReceived =>
      'Se activa cuando se reciben bytes de audio.';

  @override
  String get everyXSeconds => 'Cada x segundos';

  @override
  String get triggersWhenDaySummaryGenerated =>
      'Se activa cuando se genera el resumen del día.';

  @override
  String get tryLatestExperimentalFeatures =>
      'Pruebe las últimas funciones experimentales del equipo de Omi.';

  @override
  String get transcriptionServiceDiagnosticStatus =>
      'Estado de diagnóstico del servicio de transcripción';

  @override
  String get enableDetailedDiagnosticMessages =>
      'Habilitar mensajes de diagnóstico detallados del servicio de transcripción';

  @override
  String get autoCreateAndTagNewSpeakers =>
      'Crear y etiquetar automáticamente nuevos hablantes';

  @override
  String get automaticallyCreateNewPerson =>
      'Crear automáticamente una nueva persona cuando se detecta un nombre en la transcripción.';

  @override
  String get pilotFeatures => 'Funciones piloto';

  @override
  String get pilotFeaturesDescription =>
      'Estas funciones son pruebas y no se garantiza soporte.';

  @override
  String get suggestFollowUpQuestion => 'Sugerir pregunta de seguimiento';

  @override
  String get saveSettings => 'Guardar Configuración';

  @override
  String get syncingDeveloperSettings =>
      'Sincronizando configuración de desarrollador...';

  @override
  String get summary => 'Resumen';

  @override
  String get auto => 'Automático';

  @override
  String get noSummaryForApp =>
      'No hay resumen disponible para esta aplicación. Prueba otra aplicación para mejores resultados.';

  @override
  String get tryAnotherApp => 'Probar otra aplicación';

  @override
  String generatedBy(String appName) {
    return 'Generado por $appName';
  }

  @override
  String get overview => 'Descripción general';

  @override
  String get otherAppResults => 'Resultados de otras aplicaciones';

  @override
  String get unknownApp => 'Aplicación desconocida';

  @override
  String get noSummaryAvailable => 'No hay resumen disponible';

  @override
  String get conversationNoSummaryYet =>
      'Esta conversación aún no tiene un resumen.';

  @override
  String get chooseSummarizationApp => 'Elegir aplicación de resumen';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName establecida como aplicación de resumen predeterminada';
  }

  @override
  String get letOmiChooseAutomatically =>
      'Deja que Omi elija automáticamente la mejor aplicación';

  @override
  String get deleteConversationConfirmation =>
      '¿Estás seguro de que quieres eliminar esta conversación? Esta acción no se puede deshacer.';

  @override
  String get conversationDeleted => 'Conversación eliminada';

  @override
  String get generatingLink => 'Generando enlace...';

  @override
  String get editConversation => 'Editar conversación';

  @override
  String get conversationLinkCopiedToClipboard =>
      'Enlace de la conversación copiado al portapapeles';

  @override
  String get conversationTranscriptCopiedToClipboard =>
      'Transcripción de la conversación copiada al portapapeles';

  @override
  String get editConversationDialogTitle => 'Editar conversación';

  @override
  String get changeTheConversationTitle =>
      'Cambiar el título de la conversación';

  @override
  String get conversationTitle => 'Título de la conversación';

  @override
  String get enterConversationTitle =>
      'Introduzca el título de la conversación...';

  @override
  String get conversationTitleUpdatedSuccessfully =>
      'Título de la conversación actualizado correctamente';

  @override
  String get failedToUpdateConversationTitle =>
      'Error al actualizar el título de la conversación';

  @override
  String get errorUpdatingConversationTitle =>
      'Error al actualizar el título de la conversación';

  @override
  String get settingUp => 'Configurando...';

  @override
  String get startYourFirstRecording => 'Comienza tu primera grabación';

  @override
  String get preparingSystemAudioCapture =>
      'Preparando captura de audio del sistema';

  @override
  String get clickTheButtonToCaptureAudio =>
      'Haz clic en el botón para capturar audio para transcripciones en vivo, información de IA y guardado automático.';

  @override
  String get reconnecting => 'Reconectando...';

  @override
  String get recordingPaused => 'Grabación en pausa';

  @override
  String get recordingActive => 'Grabación activa';

  @override
  String get startRecording => 'Iniciar grabación';

  @override
  String resumingInCountdown(String countdown) {
    return 'Reanudando en ${countdown}s...';
  }

  @override
  String get tapPlayToResume => 'Toca reproducir para reanudar';

  @override
  String get listeningForAudio => 'Escuchando audio...';

  @override
  String get preparingAudioCapture => 'Preparando captura de audio';

  @override
  String get clickToBeginRecording => 'Haz clic para comenzar la grabación';

  @override
  String get translated => 'traducido';

  @override
  String get liveTranscript => 'Transcripción en vivo';

  @override
  String segmentsSingular(String count) {
    return '$count segmento';
  }

  @override
  String segmentsPlural(String count) {
    return '$count segmentos';
  }

  @override
  String get startRecordingToSeeTranscript =>
      'Inicia la grabación para ver la transcripción en vivo';

  @override
  String get paused => 'En pausa';

  @override
  String get initializing => 'Inicializando...';

  @override
  String get recording => 'Grabando';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'Micrófono cambiado. Reanudando en ${countdown}s';
  }

  @override
  String get clickPlayToResumeOrStop =>
      'Haz clic en reproducir para reanudar o detener para finalizar';

  @override
  String get settingUpSystemAudioCapture =>
      'Configurando captura de audio del sistema';

  @override
  String get capturingAudioAndGeneratingTranscript =>
      'Capturando audio y generando transcripción';

  @override
  String get clickToBeginRecordingSystemAudio =>
      'Haz clic para comenzar a grabar audio del sistema';

  @override
  String get you => 'Tú';

  @override
  String speakerWithId(String speakerId) {
    return 'Hablante $speakerId';
  }

  @override
  String get translatedByOmi => 'traducido por omi';

  @override
  String get backToConversations => 'Volver a conversaciones';

  @override
  String get systemAudio => 'Sistema';

  @override
  String get mic => 'Micrófono';

  @override
  String audioInputSetTo(String deviceName) {
    return 'Entrada de audio configurada en $deviceName';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'Error al cambiar dispositivo de audio: $error';
  }

  @override
  String get selectAudioInput => 'Seleccionar entrada de audio';

  @override
  String get loadingDevices => 'Cargando dispositivos...';

  @override
  String get settingsHeader => 'CONFIGURACIÓN';

  @override
  String get plansAndBilling => 'Planes y Facturación';

  @override
  String get calendarIntegration => 'Integración de Calendario';

  @override
  String get dailySummary => 'Resumen diario';

  @override
  String get developer => 'Desarrollador';

  @override
  String get about => 'Acerca de';

  @override
  String get selectTime => 'Seleccionar hora';

  @override
  String get accountGroup => 'Cuenta';

  @override
  String get signOutQuestion => '¿Cerrar sesión?';

  @override
  String get signOutConfirmation =>
      '¿Estás seguro de que deseas cerrar sesión?';

  @override
  String get customVocabularyHeader => 'VOCABULARIO PERSONALIZADO';

  @override
  String get addWordsDescription =>
      'Agrega palabras que Omi debería reconocer durante la transcripción.';

  @override
  String get enterWordsHint => 'Introduce palabras (separadas por comas)';

  @override
  String get dailySummaryHeader => 'RESUMEN DIARIO';

  @override
  String get dailySummaryTitle => 'Resumen Diario';

  @override
  String get dailySummaryDescription =>
      'Recibe un resumen personalizado de las conversaciones del día como notificación.';

  @override
  String get deliveryTime => 'Hora de entrega';

  @override
  String get deliveryTimeDescription => 'Cuándo recibir tu resumen diario';

  @override
  String get subscription => 'Suscripción';

  @override
  String get viewPlansAndUsage => 'Ver Planes y Uso';

  @override
  String get viewPlansDescription =>
      'Administra tu suscripción y consulta estadísticas de uso';

  @override
  String get addOrChangePaymentMethod => 'Agrega o cambia tu método de pago';

  @override
  String get displayOptions => 'Opciones de Visualización';

  @override
  String get showMeetingsInMenuBar => 'Mostrar Reuniones en la Barra de Menú';

  @override
  String get displayUpcomingMeetingsDescription =>
      'Mostrar las próximas reuniones en la barra de menú';

  @override
  String get showEventsWithoutParticipants =>
      'Mostrar Eventos sin Participantes';

  @override
  String get includePersonalEventsDescription =>
      'Incluir eventos personales sin asistentes';

  @override
  String get upcomingMeetings => 'Reuniones próximas';

  @override
  String get checkingNext7Days => 'Verificando los próximos 7 días';

  @override
  String get shortcuts => 'Atajos';

  @override
  String get shortcutChangeInstruction =>
      'Haz clic en un atajo para cambiarlo. Presiona Escape para cancelar.';

  @override
  String get configurePersonaDescription => 'Configura tu personalidad de IA';

  @override
  String get configureSTTProvider => 'Configurar proveedor de STT';

  @override
  String get setConversationEndDescription =>
      'Establece cuándo finalizan automáticamente las conversaciones';

  @override
  String get importDataDescription => 'Importar datos de otras fuentes';

  @override
  String get exportConversationsDescription => 'Exportar conversaciones a JSON';

  @override
  String get exportingConversations => 'Exportando conversaciones...';

  @override
  String get clearNodesDescription => 'Borrar todos los nodos y conexiones';

  @override
  String get deleteKnowledgeGraphQuestion =>
      '¿Eliminar Gráfico de Conocimiento?';

  @override
  String get deleteKnowledgeGraphWarning =>
      'Esto eliminará todos los datos del gráfico de conocimiento derivados. Tus recuerdos originales permanecen seguros.';

  @override
  String get connectOmiWithAI => 'Conecta Omi con asistentes de IA';

  @override
  String get noAPIKeys => 'No hay claves API. Crea una para comenzar.';

  @override
  String get autoCreateWhenDetected =>
      'Crear automáticamente cuando se detecte el nombre';

  @override
  String get trackPersonalGoals =>
      'Seguir objetivos personales en la página de inicio';

  @override
  String get dailyReflectionDescription =>
      'Recibe un recordatorio a las 9 PM para reflexionar sobre tu día y capturar tus pensamientos.';

  @override
  String get endpointURL => 'URL del Punto Final';

  @override
  String get links => 'Enlaces';

  @override
  String get discordMemberCount => 'Más de 8000 miembros en Discord';

  @override
  String get userInformation => 'Información del Usuario';

  @override
  String get capabilities => 'Capacidades';

  @override
  String get previewScreenshots => 'Vista previa de capturas';

  @override
  String get holdOnPreparingForm =>
      'Espera, estamos preparando el formulario para ti';

  @override
  String get bySubmittingYouAgreeToOmi => 'Al enviar, aceptas los ';

  @override
  String get termsAndPrivacyPolicy => 'Términos y Política de Privacidad';

  @override
  String get helpsDiagnoseIssuesAutoDeletes =>
      'Ayuda a diagnosticar problemas. Se elimina automáticamente después de 3 días.';

  @override
  String get manageYourApp => 'Gestiona tu aplicación';

  @override
  String get updatingYourApp => 'Actualizando tu aplicación';

  @override
  String get fetchingYourAppDetails =>
      'Obteniendo los detalles de tu aplicación';

  @override
  String get updateAppQuestion => '¿Actualizar aplicación?';

  @override
  String get updateAppConfirmation =>
      '¿Estás seguro de que quieres actualizar tu aplicación? Los cambios se reflejarán una vez revisados por nuestro equipo.';

  @override
  String get updateApp => 'Actualizar aplicación';

  @override
  String get createAndSubmitNewApp => 'Crear y enviar una nueva aplicación';

  @override
  String appsCount(String count) {
    return 'Aplicaciones ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'Aplicaciones privadas ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'Aplicaciones públicas ($count)';
  }

  @override
  String get newVersionAvailable => 'Nueva versión disponible  🎉';

  @override
  String get no => 'No';

  @override
  String get subscriptionCancelledSuccessfully =>
      'Suscripción cancelada con éxito. Permanecerá activa hasta el final del período de facturación actual.';

  @override
  String get failedToCancelSubscription =>
      'Error al cancelar la suscripción. Por favor, inténtalo de nuevo.';

  @override
  String get invalidPaymentUrl => 'URL de pago no válida';

  @override
  String get permissionsAndTriggers => 'Permisos y disparadores';

  @override
  String get chatFeatures => 'Funciones de chat';

  @override
  String get uninstall => 'Desinstalar';

  @override
  String get installs => 'INSTALACIONES';

  @override
  String get priceLabel => 'PRECIO';

  @override
  String get updatedLabel => 'ACTUALIZADO';

  @override
  String get createdLabel => 'CREADO';

  @override
  String get featuredLabel => 'DESTACADO';

  @override
  String get cancelSubscriptionQuestion => '¿Cancelar suscripción?';

  @override
  String get cancelSubscriptionConfirmation =>
      '¿Estás seguro de que quieres cancelar tu suscripción? Seguirás teniendo acceso hasta el final de tu período de facturación actual.';

  @override
  String get cancelSubscriptionButton => 'Cancelar suscripción';

  @override
  String get cancelling => 'Cancelando...';

  @override
  String get betaTesterMessage =>
      'Eres un probador beta de esta aplicación. Aún no es pública. Será pública una vez aprobada.';

  @override
  String get appUnderReviewMessage =>
      'Tu aplicación está en revisión y solo es visible para ti. Será pública una vez aprobada.';

  @override
  String get appRejectedMessage =>
      'Tu aplicación ha sido rechazada. Actualiza los detalles y vuelve a enviarla para revisión.';

  @override
  String get invalidIntegrationUrl => 'URL de integración no válida';

  @override
  String get tapToComplete => 'Toca para completar';

  @override
  String get invalidSetupInstructionsUrl =>
      'URL de instrucciones de configuración no válida';

  @override
  String get pushToTalk => 'Pulsar para hablar';

  @override
  String get summaryPrompt => 'Prompt de resumen';

  @override
  String get pleaseSelectARating => 'Por favor, selecciona una calificación';

  @override
  String get reviewAddedSuccessfully => 'Reseña añadida con éxito 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'Reseña actualizada con éxito 🚀';

  @override
  String get failedToSubmitReview =>
      'Error al enviar la reseña. Por favor, inténtalo de nuevo.';

  @override
  String get addYourReview => 'Añade tu reseña';

  @override
  String get editYourReview => 'Edita tu reseña';

  @override
  String get writeAReviewOptional => 'Escribe una reseña (opcional)';

  @override
  String get submitReview => 'Enviar reseña';

  @override
  String get updateReview => 'Actualizar reseña';

  @override
  String get yourReview => 'Tu reseña';

  @override
  String get anonymousUser => 'Usuario anónimo';

  @override
  String get issueActivatingApp =>
      'Hubo un problema al activar esta aplicación. Por favor, inténtalo de nuevo.';

  @override
  String get dataAccessNoticeDescription =>
      'Esta aplicación accederá a tus datos. Omi AI no es responsable de cómo esta aplicación utiliza, modifica o elimina tus datos';

  @override
  String get copyUrl => 'Copiar URL';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => 'Lun';

  @override
  String get weekdayTue => 'Mar';

  @override
  String get weekdayWed => 'Mié';

  @override
  String get weekdayThu => 'Jue';

  @override
  String get weekdayFri => 'Vie';

  @override
  String get weekdaySat => 'Sáb';

  @override
  String get weekdaySun => 'Dom';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return 'Integración con $serviceName próximamente';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'Ya exportado a $platform';
  }

  @override
  String get anotherPlatform => 'otra plataforma';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'Por favor, autentíquese con $serviceName en Configuración > Integraciones de tareas';
  }

  @override
  String addingToService(String serviceName) {
    return 'Añadiendo a $serviceName...';
  }

  @override
  String addedToService(String serviceName) {
    return 'Añadido a $serviceName';
  }

  @override
  String failedToAddToService(String serviceName) {
    return 'Error al añadir a $serviceName';
  }

  @override
  String get permissionDeniedForAppleReminders =>
      'Permiso denegado para Apple Reminders';

  @override
  String failedToCreateApiKey(String error) {
    return 'Error al crear la clave API del proveedor: $error';
  }

  @override
  String get createAKey => 'Crear una clave';

  @override
  String get apiKeyRevokedSuccessfully => 'Clave API revocada correctamente';

  @override
  String failedToRevokeApiKey(String error) {
    return 'Error al revocar la clave API: $error';
  }

  @override
  String get omiApiKeys => 'Claves API de Omi';

  @override
  String get apiKeysDescription =>
      'Las claves API se utilizan para la autenticación cuando tu aplicación se comunica con el servidor de OMI. Permiten que tu aplicación cree recuerdos y acceda a otros servicios de OMI de forma segura.';

  @override
  String get aboutOmiApiKeys => 'Acerca de las claves API de Omi';

  @override
  String get yourNewKey => 'Tu nueva clave:';

  @override
  String get copyToClipboard => 'Copiar al portapapeles';

  @override
  String get pleaseCopyKeyNow =>
      'Por favor, cópiala ahora y anótala en un lugar seguro. ';

  @override
  String get willNotSeeAgain => 'No podrás verla de nuevo.';

  @override
  String get revokeKey => 'Revocar clave';

  @override
  String get revokeApiKeyQuestion => '¿Revocar clave API?';

  @override
  String get revokeApiKeyWarning =>
      'Esta acción no se puede deshacer. Las aplicaciones que usen esta clave ya no podrán acceder a la API.';

  @override
  String get revoke => 'Revocar';

  @override
  String get whatWouldYouLikeToCreate => '¿Qué te gustaría crear?';

  @override
  String get createAnApp => 'Crear una aplicación';

  @override
  String get createAndShareYourApp => 'Crea y comparte tu aplicación';

  @override
  String get createMyClone => 'Crear mi clon';

  @override
  String get createYourDigitalClone => 'Crea tu clon digital';

  @override
  String get itemApp => 'Aplicación';

  @override
  String get itemPersona => 'Persona';

  @override
  String keepItemPublic(String item) {
    return 'Mantener $item público';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return '¿Hacer $item público?';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return '¿Hacer $item privado?';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'Si haces $item público, puede ser usado por todos';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'Si haces $item privado ahora, dejará de funcionar para todos y solo será visible para ti';
  }

  @override
  String get manageApp => 'Administrar aplicación';

  @override
  String get updatePersonaDetails => 'Actualizar detalles de persona';

  @override
  String deleteItemTitle(String item) {
    return 'Eliminar $item';
  }

  @override
  String deleteItemQuestion(String item) {
    return '¿Eliminar $item?';
  }

  @override
  String deleteItemConfirmation(String item) {
    return '¿Estás seguro de que quieres eliminar este $item? Esta acción no se puede deshacer.';
  }

  @override
  String get revokeKeyQuestion => '¿Revocar clave?';

  @override
  String revokeKeyConfirmation(String keyName) {
    return '¿Estás seguro de que quieres revocar la clave \"$keyName\"? Esta acción no se puede deshacer.';
  }

  @override
  String get createNewKey => 'Crear nueva clave';

  @override
  String get keyNameHint => 'p. ej., Claude Desktop';

  @override
  String get pleaseEnterAName => 'Por favor, introduce un nombre.';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'Error al crear la clave: $error';
  }

  @override
  String get failedToCreateKeyTryAgain =>
      'Error al crear la clave. Por favor, inténtalo de nuevo.';

  @override
  String get keyCreated => 'Clave creada';

  @override
  String get keyCreatedMessage =>
      'Tu nueva clave ha sido creada. Por favor, cópiala ahora. No podrás verla de nuevo.';

  @override
  String get keyWord => 'Clave';

  @override
  String get externalAppAccess => 'Acceso de aplicaciones externas';

  @override
  String get externalAppAccessDescription =>
      'Las siguientes aplicaciones instaladas tienen integraciones externas y pueden acceder a tus datos, como conversaciones y recuerdos.';

  @override
  String get noExternalAppsHaveAccess =>
      'Ninguna aplicación externa tiene acceso a tus datos.';

  @override
  String get maximumSecurityE2ee => 'Seguridad máxima (E2EE)';

  @override
  String get e2eeDescription =>
      'El cifrado de extremo a extremo es el estándar de oro para la privacidad. Cuando está habilitado, tus datos se cifran en tu dispositivo antes de enviarse a nuestros servidores. Esto significa que nadie, ni siquiera Omi, puede acceder a tu contenido.';

  @override
  String get importantTradeoffs => 'Compensaciones importantes:';

  @override
  String get e2eeTradeoff1 =>
      '• Algunas funciones como las integraciones de aplicaciones externas pueden estar deshabilitadas.';

  @override
  String get e2eeTradeoff2 =>
      '• Si pierdes tu contraseña, tus datos no se pueden recuperar.';

  @override
  String get featureComingSoon => '¡Esta función estará disponible pronto!';

  @override
  String get migrationInProgressMessage =>
      'Migración en progreso. No puedes cambiar el nivel de protección hasta que se complete.';

  @override
  String get migrationFailed => 'Migración fallida';

  @override
  String migratingFromTo(String source, String target) {
    return 'Migrando de $source a $target';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total objetos';
  }

  @override
  String get secureEncryption => 'Cifrado seguro';

  @override
  String get secureEncryptionDescription =>
      'Tus datos se cifran con una clave única para ti en nuestros servidores, alojados en Google Cloud. Esto significa que tu contenido sin procesar es inaccesible para cualquier persona, incluido el personal de Omi o Google, directamente desde la base de datos.';

  @override
  String get endToEndEncryption => 'Cifrado de extremo a extremo';

  @override
  String get e2eeCardDescription =>
      'Activa para máxima seguridad donde solo tú puedes acceder a tus datos. Toca para saber más.';

  @override
  String get dataAlwaysEncrypted =>
      'Independientemente del nivel, tus datos siempre están cifrados en reposo y en tránsito.';

  @override
  String get readOnlyScope => 'Solo lectura';

  @override
  String get fullAccessScope => 'Acceso completo';

  @override
  String get readScope => 'Lectura';

  @override
  String get writeScope => 'Escritura';

  @override
  String get apiKeyCreated => '¡Clave API creada!';

  @override
  String get saveKeyWarning =>
      '¡Guarda esta clave ahora! No podrás verla de nuevo.';

  @override
  String get yourApiKey => 'TU CLAVE API';

  @override
  String get tapToCopy => 'Toca para copiar';

  @override
  String get copyKey => 'Copiar clave';

  @override
  String get createApiKey => 'Crear clave API';

  @override
  String get accessDataProgrammatically =>
      'Accede a tus datos programáticamente';

  @override
  String get keyNameLabel => 'NOMBRE DE CLAVE';

  @override
  String get keyNamePlaceholder => 'ej., Mi integración de app';

  @override
  String get permissionsLabel => 'PERMISOS';

  @override
  String get permissionsInfoNote =>
      'R = Lectura, W = Escritura. Por defecto solo lectura si no se selecciona nada.';

  @override
  String get developerApi => 'API de desarrollador';

  @override
  String get createAKeyToGetStarted => 'Crea una clave para comenzar';

  @override
  String errorWithMessage(String error) {
    return 'Error: $error';
  }

  @override
  String get omiTraining => 'Entrenamiento Omi';

  @override
  String get trainingDataProgram => 'Programa de datos de entrenamiento';

  @override
  String get getOmiUnlimitedFree =>
      'Obtén Omi Ilimitado gratis contribuyendo tus datos para entrenar modelos de IA.';

  @override
  String get trainingDataBullets =>
      '• Tus datos ayudan a mejorar los modelos de IA\n• Solo se comparten datos no sensibles\n• Proceso completamente transparente';

  @override
  String get learnMoreAtOmiTraining => 'Aprende más en omi.me/training';

  @override
  String get agreeToContributeData =>
      'Entiendo y acepto contribuir mis datos para el entrenamiento de IA';

  @override
  String get submitRequest => 'Enviar solicitud';

  @override
  String get thankYouRequestUnderReview =>
      '¡Gracias! Tu solicitud está en revisión. Te notificaremos cuando sea aprobada.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'Tu plan permanecerá activo hasta $date. Después, perderás acceso a tus funciones ilimitadas. ¿Estás seguro?';
  }

  @override
  String get confirmCancellation => 'Confirmar cancelación';

  @override
  String get keepMyPlan => 'Mantener mi plan';

  @override
  String get subscriptionSetToCancel =>
      'Tu suscripción está configurada para cancelarse al final del período.';

  @override
  String get switchedToOnDevice => 'Cambiado a transcripción en dispositivo';

  @override
  String get couldNotSwitchToFreePlan =>
      'No se pudo cambiar al plan gratuito. Por favor, inténtalo de nuevo.';

  @override
  String get couldNotLoadPlans =>
      'No se pudieron cargar los planes disponibles. Por favor, inténtalo de nuevo.';

  @override
  String get selectedPlanNotAvailable =>
      'El plan seleccionado no está disponible. Por favor, inténtalo de nuevo.';

  @override
  String get upgradeToAnnualPlan => 'Actualizar al plan anual';

  @override
  String get importantBillingInfo => 'Información de facturación importante:';

  @override
  String get monthlyPlanContinues =>
      'Tu plan mensual actual continuará hasta el final de tu período de facturación';

  @override
  String get paymentMethodCharged =>
      'Tu método de pago existente se cobrará automáticamente cuando termine tu plan mensual';

  @override
  String get annualSubscriptionStarts =>
      'Tu suscripción anual de 12 meses comenzará automáticamente después del cargo';

  @override
  String get thirteenMonthsCoverage =>
      'Obtendrás 13 meses de cobertura en total (mes actual + 12 meses anuales)';

  @override
  String get confirmUpgrade => 'Confirmar actualización';

  @override
  String get confirmPlanChange => 'Confirmar cambio de plan';

  @override
  String get confirmAndProceed => 'Confirmar y continuar';

  @override
  String get upgradeScheduled => 'Actualización programada';

  @override
  String get changePlan => 'Cambiar plan';

  @override
  String get upgradeAlreadyScheduled =>
      'Tu actualización al plan anual ya está programada';

  @override
  String get youAreOnUnlimitedPlan => 'Estás en el plan Ilimitado.';

  @override
  String get yourOmiUnleashed =>
      'Tu Omi, liberado. Hazte ilimitado para posibilidades infinitas.';

  @override
  String planEndedOn(String date) {
    return 'Tu plan terminó el $date.\\nVuelve a suscribirte ahora - se te cobrará inmediatamente por un nuevo período de facturación.';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'Tu plan está configurado para cancelarse el $date.\\nVuelve a suscribirte ahora para mantener tus beneficios - sin cargo hasta $date.';
  }

  @override
  String get annualPlanStartsAutomatically =>
      'Tu plan anual comenzará automáticamente cuando termine tu plan mensual.';

  @override
  String planRenewsOn(String date) {
    return 'Tu plan se renueva el $date.';
  }

  @override
  String get unlimitedConversations => 'Conversaciones ilimitadas';

  @override
  String get askOmiAnything => 'Pregunta a Omi cualquier cosa sobre tu vida';

  @override
  String get unlockOmiInfiniteMemory => 'Desbloquea la memoria infinita de Omi';

  @override
  String get youreOnAnnualPlan => 'Estás en el plan anual';

  @override
  String get alreadyBestValuePlan =>
      'Ya tienes el plan de mejor valor. No se necesitan cambios.';

  @override
  String get unableToLoadPlans => 'No se pueden cargar los planes';

  @override
  String get checkConnectionTryAgain =>
      'Comprueba tu conexión e inténtalo de nuevo';

  @override
  String get useFreePlan => 'Usar plan gratuito';

  @override
  String get continueText => 'Continuar';

  @override
  String get resubscribe => 'Volver a suscribirse';

  @override
  String get couldNotOpenPaymentSettings =>
      'No se pudieron abrir los ajustes de pago. Por favor, inténtalo de nuevo.';

  @override
  String get managePaymentMethod => 'Gestionar método de pago';

  @override
  String get cancelSubscription => 'Cancelar suscripción';

  @override
  String endsOnDate(String date) {
    return 'Termina el $date';
  }

  @override
  String get active => 'Activo';

  @override
  String get freePlan => 'Plan gratuito';

  @override
  String get configure => 'Configurar';

  @override
  String get privacyInformation => 'Información de privacidad';

  @override
  String get yourPrivacyMattersToUs => 'Tu privacidad nos importa';

  @override
  String get privacyIntroText =>
      'En Omi, nos tomamos tu privacidad muy en serio. Queremos ser transparentes sobre los datos que recopilamos y cómo los usamos para mejorar nuestro producto. Esto es lo que necesitas saber:';

  @override
  String get whatWeTrack => 'Qué rastreamos';

  @override
  String get anonymityAndPrivacy => 'Anonimato y privacidad';

  @override
  String get optInAndOptOutOptions => 'Opciones de aceptación y rechazo';

  @override
  String get ourCommitment => 'Nuestro compromiso';

  @override
  String get commitmentText =>
      'Nos comprometemos a usar los datos que recopilamos solo para hacer de Omi un mejor producto para ti. Tu privacidad y confianza son primordiales para nosotros.';

  @override
  String get thankYouText =>
      'Gracias por ser un usuario valioso de Omi. Si tienes alguna pregunta o inquietud, no dudes en contactarnos en team@basedhardware.com.';

  @override
  String get wifiSyncSettings => 'Configuración de sincronización WiFi';

  @override
  String get enterHotspotCredentials =>
      'Ingresa las credenciales del punto de acceso de tu teléfono';

  @override
  String get wifiSyncUsesHotspot =>
      'La sincronización WiFi usa tu teléfono como punto de acceso. Encuentra el nombre y contraseña en Ajustes > Punto de acceso personal.';

  @override
  String get hotspotNameSsid => 'Nombre del punto de acceso (SSID)';

  @override
  String get exampleIphoneHotspot => 'ej. Punto de acceso iPhone';

  @override
  String get password => 'Contraseña';

  @override
  String get enterHotspotPassword =>
      'Ingresa la contraseña del punto de acceso';

  @override
  String get saveCredentials => 'Guardar credenciales';

  @override
  String get clearCredentials => 'Borrar credenciales';

  @override
  String get pleaseEnterHotspotName =>
      'Por favor ingresa un nombre de punto de acceso';

  @override
  String get wifiCredentialsSaved => 'Credenciales WiFi guardadas';

  @override
  String get wifiCredentialsCleared => 'Credenciales WiFi borradas';

  @override
  String summaryGeneratedForDate(String date) {
    return 'Resumen generado para $date';
  }

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'Error al generar el resumen. Asegúrate de tener conversaciones para ese día.';

  @override
  String get summaryNotFound => 'Resumen no encontrado';

  @override
  String get yourDaysJourney => 'Tu viaje del día';

  @override
  String get highlights => 'Destacados';

  @override
  String get unresolvedQuestions => 'Preguntas sin resolver';

  @override
  String get decisions => 'Decisiones';

  @override
  String get learnings => 'Aprendizajes';

  @override
  String get autoDeletesAfterThreeDays =>
      'Se elimina automáticamente después de 3 días.';

  @override
  String get knowledgeGraphDeletedSuccessfully =>
      'Grafo de conocimiento eliminado correctamente';

  @override
  String get exportStartedMayTakeFewSeconds =>
      'Exportación iniciada. Esto puede tardar unos segundos...';

  @override
  String get knowledgeGraphDeleteDescription =>
      'Esto eliminará todos los datos derivados del grafo de conocimiento (nodos y conexiones). Tus recuerdos originales permanecerán seguros. El grafo se reconstruirá con el tiempo o en la próxima solicitud.';

  @override
  String get configureDailySummaryDigest =>
      'Configura tu resumen diario de tareas';

  @override
  String accessesDataTypes(String dataTypes) {
    return 'Accede a $dataTypes';
  }

  @override
  String triggeredByType(String triggerType) {
    return 'activado por $triggerType';
  }

  @override
  String accessesAndTriggeredBy(
    String accessDescription,
    String triggerDescription,
  ) {
    return '$accessDescription y es $triggerDescription.';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return 'Es $triggerDescription.';
  }

  @override
  String get noSpecificDataAccessConfigured =>
      'No hay acceso a datos específico configurado.';

  @override
  String get basicPlanDescription =>
      '1.200 minutos premium + ilimitado en dispositivo';

  @override
  String get minutes => 'minutos';

  @override
  String get omiHas => 'Omi tiene:';

  @override
  String get premiumMinutesUsed => 'Minutos premium utilizados.';

  @override
  String get setupOnDevice => 'Configurar en dispositivo';

  @override
  String get forUnlimitedFreeTranscription =>
      'para transcripción gratuita ilimitada.';

  @override
  String premiumMinsLeft(int count) {
    return '$count minutos premium restantes.';
  }

  @override
  String get alwaysAvailable => 'siempre disponible.';

  @override
  String get importHistory => 'Historial de importación';

  @override
  String get noImportsYet => 'Sin importaciones aún';

  @override
  String get selectZipFileToImport =>
      '¡Selecciona el archivo .zip para importar!';

  @override
  String get otherDevicesComingSoon => 'Otros dispositivos próximamente';

  @override
  String get deleteAllLimitlessConversations =>
      '¿Eliminar todas las conversaciones de Limitless?';

  @override
  String get deleteAllLimitlessWarning =>
      'Esto eliminará permanentemente todas las conversaciones importadas de Limitless. Esta acción no se puede deshacer.';

  @override
  String deletedLimitlessConversations(int count) {
    return 'Se eliminaron $count conversaciones de Limitless';
  }

  @override
  String get failedToDeleteConversations => 'Error al eliminar conversaciones';

  @override
  String get deleteImportedData => 'Eliminar datos importados';

  @override
  String get statusPending => 'Pendiente';

  @override
  String get statusProcessing => 'Procesando';

  @override
  String get statusCompleted => 'Completado';

  @override
  String get statusFailed => 'Fallido';

  @override
  String nConversations(int count) {
    return '$count conversaciones';
  }

  @override
  String get pleaseEnterName => 'Por favor, ingrese un nombre';

  @override
  String get nameMustBeBetweenCharacters =>
      'El nombre debe tener entre 2 y 40 caracteres';

  @override
  String get deleteSampleQuestion => '¿Eliminar muestra?';

  @override
  String deleteSampleConfirmation(String name) {
    return '¿Estás seguro de que quieres eliminar la muestra de $name?';
  }

  @override
  String get confirmDeletion => 'Confirmar eliminación';

  @override
  String deletePersonConfirmation(String name) {
    return '¿Estás seguro de que quieres eliminar a $name? Esto también eliminará todas las muestras de voz asociadas.';
  }

  @override
  String get howItWorksTitle => '¿Cómo funciona?';

  @override
  String get howPeopleWorks =>
      'Una vez creada una persona, puedes ir a la transcripción de una conversación y asignarle sus segmentos correspondientes, ¡así Omi también podrá reconocer su voz!';

  @override
  String get tapToDelete => 'Toca para eliminar';

  @override
  String get newTag => 'NUEVO';

  @override
  String get needHelpChatWithUs => '¿Necesitas ayuda? Chatea con nosotros';

  @override
  String get localStorageEnabled => 'Almacenamiento local habilitado';

  @override
  String get localStorageDisabled => 'Almacenamiento local deshabilitado';

  @override
  String failedToUpdateSettings(String error) {
    return 'Error al actualizar la configuración: $error';
  }

  @override
  String get privacyNotice => 'Aviso de privacidad';

  @override
  String get recordingsMayCaptureOthers =>
      'Las grabaciones pueden capturar las voces de otros. Asegúrese de tener el consentimiento de todos los participantes antes de activar.';

  @override
  String get enable => 'Activar';

  @override
  String get storeAudioOnPhone => 'Almacenar audio en el teléfono';

  @override
  String get on => 'On';

  @override
  String get storeAudioDescription =>
      'Mantenga todas las grabaciones de audio almacenadas localmente en su teléfono. Cuando está deshabilitado, solo se guardan las cargas fallidas para ahorrar espacio.';

  @override
  String get enableLocalStorage => 'Habilitar almacenamiento local';

  @override
  String get cloudStorageEnabled => 'Almacenamiento en la nube habilitado';

  @override
  String get cloudStorageDisabled => 'Almacenamiento en la nube deshabilitado';

  @override
  String get enableCloudStorage => 'Habilitar almacenamiento en la nube';

  @override
  String get storeAudioOnCloud => 'Almacenar audio en la nube';

  @override
  String get cloudStorageDialogMessage =>
      'Sus grabaciones en tiempo real se almacenarán en almacenamiento privado en la nube mientras habla.';

  @override
  String get storeAudioCloudDescription =>
      'Almacene sus grabaciones en tiempo real en almacenamiento privado en la nube mientras habla. El audio se captura y guarda de forma segura en tiempo real.';

  @override
  String get downloadingFirmware => 'Descargando firmware';

  @override
  String get installingFirmware => 'Instalando firmware';

  @override
  String get firmwareUpdateWarning =>
      'No cierre la aplicación ni apague el dispositivo. Esto podría dañar su dispositivo.';

  @override
  String get firmwareUpdated => 'Firmware actualizado';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'Por favor, reinicie su $deviceName para completar la actualización.';
  }

  @override
  String get yourDeviceIsUpToDate => 'Su dispositivo está actualizado';

  @override
  String get currentVersion => 'Versión actual';

  @override
  String get latestVersion => 'Última versión';

  @override
  String get whatsNew => 'Novedades';

  @override
  String get installUpdate => 'Instalar actualización';

  @override
  String get updateNow => 'Actualizar ahora';

  @override
  String get updateGuide => 'Guía de actualización';

  @override
  String get checkingForUpdates => 'Buscando actualizaciones';

  @override
  String get checkingFirmwareVersion => 'Comprobando versión del firmware...';

  @override
  String get firmwareUpdate => 'Actualización de firmware';

  @override
  String get payments => 'Pagos';

  @override
  String get connectPaymentMethodInfo =>
      'Conecte un método de pago a continuación para comenzar a recibir pagos por sus aplicaciones.';

  @override
  String get selectedPaymentMethod => 'Método de pago seleccionado';

  @override
  String get availablePaymentMethods => 'Métodos de pago disponibles';

  @override
  String get activeStatus => 'Activo';

  @override
  String get connectedStatus => 'Conectado';

  @override
  String get notConnectedStatus => 'No conectado';

  @override
  String get setActive => 'Establecer como activo';

  @override
  String get getPaidThroughStripe =>
      'Reciba pagos por las ventas de sus aplicaciones a través de Stripe';

  @override
  String get monthlyPayouts => 'Pagos mensuales';

  @override
  String get monthlyPayoutsDescription =>
      'Reciba pagos mensuales directamente en su cuenta cuando alcance \$10 en ganancias';

  @override
  String get secureAndReliable => 'Seguro y confiable';

  @override
  String get stripeSecureDescription =>
      'Stripe garantiza transferencias seguras y oportunas de los ingresos de su aplicación';

  @override
  String get selectYourCountry => 'Seleccione su país';

  @override
  String get countrySelectionPermanent =>
      'La selección de país es permanente y no se puede cambiar después.';

  @override
  String get byClickingConnectNow =>
      'Al hacer clic en \"Conectar ahora\" acepta el';

  @override
  String get stripeConnectedAccountAgreement =>
      'Acuerdo de cuenta conectada de Stripe';

  @override
  String get errorConnectingToStripe =>
      '¡Error al conectar con Stripe! Por favor, inténtelo de nuevo más tarde.';

  @override
  String get connectingYourStripeAccount => 'Conectando su cuenta de Stripe';

  @override
  String get stripeOnboardingInstructions =>
      'Complete el proceso de incorporación de Stripe en su navegador. Esta página se actualizará automáticamente una vez completado.';

  @override
  String get failedTryAgain => '¿Falló? Intentar de nuevo';

  @override
  String get illDoItLater => 'Lo haré más tarde';

  @override
  String get successfullyConnected => '¡Conectado con éxito!';

  @override
  String get stripeReadyForPayments =>
      'Su cuenta de Stripe está lista para recibir pagos. Puede comenzar a ganar con las ventas de sus aplicaciones de inmediato.';

  @override
  String get updateStripeDetails => 'Actualizar detalles de Stripe';

  @override
  String get errorUpdatingStripeDetails =>
      '¡Error al actualizar los detalles de Stripe! Por favor, inténtelo de nuevo más tarde.';

  @override
  String get updatePayPal => 'Actualizar PayPal';

  @override
  String get setUpPayPal => 'Configurar PayPal';

  @override
  String get updatePayPalAccountDetails =>
      'Actualice los datos de su cuenta de PayPal';

  @override
  String get connectPayPalToReceivePayments =>
      'Conecte su cuenta de PayPal para comenzar a recibir pagos por sus aplicaciones';

  @override
  String get paypalEmail => 'Correo electrónico de PayPal';

  @override
  String get paypalMeLink => 'Enlace PayPal.me';

  @override
  String get stripeRecommendation =>
      'Si Stripe está disponible en su país, le recomendamos encarecidamente usarlo para pagos más rápidos y fáciles.';

  @override
  String get updatePayPalDetails => 'Actualizar detalles de PayPal';

  @override
  String get savePayPalDetails => 'Guardar detalles de PayPal';

  @override
  String get pleaseEnterPayPalEmail =>
      'Por favor, introduzca su correo electrónico de PayPal';

  @override
  String get pleaseEnterPayPalMeLink =>
      'Por favor, introduzca su enlace PayPal.me';

  @override
  String get doNotIncludeHttpInLink =>
      'No incluya http o https o www en el enlace';

  @override
  String get pleaseEnterValidPayPalMeLink =>
      'Por favor, introduzca un enlace PayPal.me válido';

  @override
  String get pleaseEnterValidEmail =>
      'Por favor, introduce una dirección de correo electrónico válida';

  @override
  String get syncingYourRecordings => 'Sincronizando tus grabaciones';

  @override
  String get syncYourRecordings => 'Sincroniza tus grabaciones';

  @override
  String get syncNow => 'Sincronizar ahora';

  @override
  String get error => 'Error';

  @override
  String get speechSamples => 'Muestras de voz';

  @override
  String additionalSampleIndex(String index) {
    return 'Muestra adicional $index';
  }

  @override
  String durationSeconds(String seconds) {
    return 'Duración: $seconds segundos';
  }

  @override
  String get additionalSpeechSampleRemoved =>
      'Muestra de voz adicional eliminada';

  @override
  String get consentDataMessage =>
      'Al continuar, todos los datos que compartas con esta aplicación (incluidas tus conversaciones, grabaciones e información personal) se almacenarán de forma segura en nuestros servidores para proporcionarte información basada en IA y habilitar todas las funciones de la aplicación.';

  @override
  String get tasksEmptyStateMessage =>
      'Las tareas de tus conversaciones aparecerán aquí.\nToca + para crear una manualmente.';

  @override
  String get clearChatAction => 'Borrar chat';

  @override
  String get enableApps => 'Habilitar apps';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => 'mostrar más ↓';

  @override
  String get showLess => 'mostrar menos ↑';

  @override
  String get loadingYourRecording => 'Cargando tu grabación...';

  @override
  String get photoDiscardedMessage =>
      'Esta foto fue descartada porque no era significativa.';

  @override
  String get analyzing => 'Analizando...';

  @override
  String get searchCountries => 'Buscar países...';

  @override
  String get checkingAppleWatch => 'Comprobando Apple Watch...';

  @override
  String get installOmiOnAppleWatch => 'Instala Omi en tu\nApple Watch';

  @override
  String get installOmiOnAppleWatchDescription =>
      'Para usar tu Apple Watch con Omi, primero debes instalar la aplicación Omi en tu reloj.';

  @override
  String get openOmiOnAppleWatch => 'Abre Omi en tu\nApple Watch';

  @override
  String get openOmiOnAppleWatchDescription =>
      'La aplicación Omi está instalada en tu Apple Watch. Ábrela y toca Iniciar para comenzar.';

  @override
  String get openWatchApp => 'Abrir app Watch';

  @override
  String get iveInstalledAndOpenedTheApp => 'He instalado y abierto la app';

  @override
  String get unableToOpenWatchApp =>
      'No se pudo abrir la app de Apple Watch. Abre manualmente la app Watch en tu Apple Watch e instala Omi desde la sección \"Apps disponibles\".';

  @override
  String get appleWatchConnectedSuccessfully =>
      '¡Apple Watch conectado correctamente!';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch aún no está accesible. Asegúrate de que la app Omi esté abierta en tu reloj.';

  @override
  String errorCheckingConnection(String error) {
    return 'Error al verificar la conexión: $error';
  }

  @override
  String get muted => 'Silenciado';

  @override
  String get processNow => 'Procesar ahora';

  @override
  String get finishedConversation => '¿Conversación terminada?';

  @override
  String get stopRecordingConfirmation =>
      '¿Estás seguro de que quieres detener la grabación y resumir la conversación ahora?';

  @override
  String get conversationEndsManually =>
      'La conversación solo terminará manualmente.';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'La conversación se resume después de $minutes minuto$suffix sin hablar.';
  }

  @override
  String get dontAskAgain => 'No volver a preguntar';

  @override
  String get waitingForTranscriptOrPhotos =>
      'Esperando transcripción o fotos...';

  @override
  String get noSummaryYet => 'Aún no hay resumen';

  @override
  String hints(String text) {
    return 'Consejos: $text';
  }

  @override
  String get testConversationPrompt => 'Probar un prompt de conversación';

  @override
  String get prompt => 'Prompt';

  @override
  String get result => 'Resultado:';

  @override
  String get compareTranscripts => 'Comparar transcripciones';

  @override
  String get notHelpful => 'No fue útil';

  @override
  String get exportTasksWithOneTap => '¡Exporta tareas con un toque!';

  @override
  String get inProgress => 'En progreso';

  @override
  String get photos => 'Fotos';

  @override
  String get rawData => 'Datos sin procesar';

  @override
  String get content => 'Contenido';

  @override
  String get noContentToDisplay => 'No hay contenido para mostrar';

  @override
  String get noSummary => 'Sin resumen';

  @override
  String get updateOmiFirmware => 'Actualizar firmware de omi';

  @override
  String get anErrorOccurredTryAgain =>
      'Ocurrió un error. Por favor, inténtalo de nuevo.';

  @override
  String get welcomeBackSimple => 'Bienvenido de nuevo';

  @override
  String get addVocabularyDescription =>
      'Añade palabras que Omi debe reconocer durante la transcripción.';

  @override
  String get enterWordsCommaSeparated =>
      'Ingresa palabras (separadas por comas)';

  @override
  String get whenToReceiveDailySummary => 'Cuándo recibir tu resumen diario';

  @override
  String get checkingNextSevenDays => 'Revisando los próximos 7 días';

  @override
  String failedToDeleteError(String error) {
    return 'Error al eliminar: $error';
  }

  @override
  String get developerApiKeys => 'Claves API de desarrollador';

  @override
  String get noApiKeysCreateOne => 'No hay claves API. Crea una para empezar.';

  @override
  String get commandRequired => '⌘ requerido';

  @override
  String get spaceKey => 'Espacio';

  @override
  String loadMoreRemaining(String count) {
    return 'Cargar más ($count restantes)';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'Top $percentile% Usuario';
  }

  @override
  String get wrappedMinutes => 'minutos';

  @override
  String get wrappedConversations => 'conversaciones';

  @override
  String get wrappedDaysActive => 'días activos';

  @override
  String get wrappedYouTalkedAbout => 'Hablaste sobre';

  @override
  String get wrappedActionItems => 'Tareas';

  @override
  String get wrappedTasksCreated => 'tareas creadas';

  @override
  String get wrappedCompleted => 'completadas';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% tasa de finalización';
  }

  @override
  String get wrappedYourTopDays => 'Tus mejores días';

  @override
  String get wrappedBestMoments => 'Mejores momentos';

  @override
  String get wrappedMyBuddies => 'Mis amigos';

  @override
  String get wrappedCouldntStopTalkingAbout => 'No podía parar de hablar de';

  @override
  String get wrappedShow => 'SERIE';

  @override
  String get wrappedMovie => 'PELÍCULA';

  @override
  String get wrappedBook => 'LIBRO';

  @override
  String get wrappedCelebrity => 'CELEBRIDAD';

  @override
  String get wrappedFood => 'COMIDA';

  @override
  String get wrappedMovieRecs => 'Recomendaciones de películas';

  @override
  String get wrappedBiggest => 'Mayor';

  @override
  String get wrappedStruggle => 'Reto';

  @override
  String get wrappedButYouPushedThrough => 'Pero lo superaste 💪';

  @override
  String get wrappedWin => 'Victoria';

  @override
  String get wrappedYouDidIt => '¡Lo lograste! 🎉';

  @override
  String get wrappedTopPhrases => 'Top 5 frases';

  @override
  String get wrappedMins => 'min';

  @override
  String get wrappedConvos => 'conversaciones';

  @override
  String get wrappedDays => 'días';

  @override
  String get wrappedMyBuddiesLabel => 'MIS AMIGOS';

  @override
  String get wrappedObsessionsLabel => 'OBSESIONES';

  @override
  String get wrappedStruggleLabel => 'RETO';

  @override
  String get wrappedWinLabel => 'VICTORIA';

  @override
  String get wrappedTopPhrasesLabel => 'TOP FRASES';

  @override
  String get wrappedLetsHitRewind => 'Rebobinemos tu';

  @override
  String get wrappedGenerateMyWrapped => 'Generar mi Wrapped';

  @override
  String get wrappedProcessingDefault => 'Procesando...';

  @override
  String get wrappedCreatingYourStory => 'Creando tu\nhistoria de 2025...';

  @override
  String get wrappedSomethingWentWrong => 'Algo salió\nmal';

  @override
  String get wrappedAnErrorOccurred => 'Ocurrió un error';

  @override
  String get wrappedTryAgain => 'Intentar de nuevo';

  @override
  String get wrappedNoDataAvailable => 'No hay datos disponibles';

  @override
  String get wrappedOmiLifeRecap => 'Resumen de vida Omi';

  @override
  String get wrappedSwipeUpToBegin => 'Desliza hacia arriba para comenzar';

  @override
  String get wrappedShareText => 'Mi 2025, recordado por Omi ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare =>
      'Error al compartir. Por favor, inténtalo de nuevo.';

  @override
  String get wrappedFailedToStartGeneration =>
      'Error al iniciar la generación. Por favor, inténtalo de nuevo.';

  @override
  String get wrappedStarting => 'Iniciando...';

  @override
  String get wrappedShare => 'Compartir';

  @override
  String get wrappedShareYourWrapped => 'Comparte tu Wrapped';

  @override
  String get wrappedMy2025 => 'Mi 2025';

  @override
  String get wrappedRememberedByOmi => 'recordado por Omi';

  @override
  String get wrappedMostFunDay => 'Más divertido';

  @override
  String get wrappedMostProductiveDay => 'Más productivo';

  @override
  String get wrappedMostIntenseDay => 'Más intenso';

  @override
  String get wrappedFunniestMoment => 'Más gracioso';

  @override
  String get wrappedMostCringeMoment => 'Más vergonzoso';

  @override
  String get wrappedMinutesLabel => 'minutos';

  @override
  String get wrappedConversationsLabel => 'conversaciones';

  @override
  String get wrappedDaysActiveLabel => 'días activos';

  @override
  String get wrappedTasksGenerated => 'tareas generadas';

  @override
  String get wrappedTasksCompleted => 'tareas completadas';

  @override
  String get wrappedTopFivePhrases => 'Top 5 frases';

  @override
  String get wrappedAGreatDay => 'Un gran día';

  @override
  String get wrappedGettingItDone => 'Lograrlo';

  @override
  String get wrappedAChallenge => 'Un desafío';

  @override
  String get wrappedAHilariousMoment => 'Un momento gracioso';

  @override
  String get wrappedThatAwkwardMoment => 'Ese momento incómodo';

  @override
  String get wrappedYouHadFunnyMoments =>
      '¡Tuviste momentos graciosos este año!';

  @override
  String get wrappedWeveAllBeenThere => '¡Todos hemos pasado por eso!';

  @override
  String get wrappedFriend => 'Amigo';

  @override
  String get wrappedYourBuddy => '¡Tu amigo!';

  @override
  String get wrappedNotMentioned => 'No mencionado';

  @override
  String get wrappedTheHardPart => 'La parte difícil';

  @override
  String get wrappedPersonalGrowth => 'Crecimiento personal';

  @override
  String get wrappedFunDay => 'Diversión';

  @override
  String get wrappedProductiveDay => 'Productivo';

  @override
  String get wrappedIntenseDay => 'Intenso';

  @override
  String get wrappedFunnyMomentTitle => 'Momento gracioso';

  @override
  String get wrappedCringeMomentTitle => 'Momento vergonzoso';

  @override
  String get wrappedYouTalkedAboutBadge => 'Hablaste sobre';

  @override
  String get wrappedCompletedLabel => 'Completado';

  @override
  String get wrappedMyBuddiesCard => 'Mis amigos';

  @override
  String get wrappedBuddiesLabel => 'AMIGOS';

  @override
  String get wrappedObsessionsLabelUpper => 'OBSESIONES';

  @override
  String get wrappedStruggleLabelUpper => 'LUCHA';

  @override
  String get wrappedWinLabelUpper => 'VICTORIA';

  @override
  String get wrappedTopPhrasesLabelUpper => 'TOP FRASES';

  @override
  String get wrappedYourHeader => 'Tus';

  @override
  String get wrappedTopDaysHeader => 'Mejores días';

  @override
  String get wrappedYourTopDaysBadge => 'Tus mejores días';

  @override
  String get wrappedBestHeader => 'Mejores';

  @override
  String get wrappedMomentsHeader => 'Momentos';

  @override
  String get wrappedBestMomentsBadge => 'Mejores momentos';

  @override
  String get wrappedBiggestHeader => 'Mayor';

  @override
  String get wrappedStruggleHeader => 'Lucha';

  @override
  String get wrappedWinHeader => 'Victoria';

  @override
  String get wrappedButYouPushedThroughEmoji => 'Pero lo lograste 💪';

  @override
  String get wrappedYouDidItEmoji => '¡Lo hiciste! 🎉';

  @override
  String get wrappedHours => 'horas';

  @override
  String get wrappedActions => 'acciones';

  @override
  String get multipleSpeakersDetected => 'Múltiples hablantes detectados';

  @override
  String get multipleSpeakersDescription =>
      'Parece que hay múltiples hablantes en la grabación. Asegúrate de estar en un lugar tranquilo e inténtalo de nuevo.';

  @override
  String get invalidRecordingDetected => 'Grabación inválida detectada';

  @override
  String get notEnoughSpeechDescription =>
      'No se detectó suficiente habla. Por favor, habla más e inténtalo de nuevo.';

  @override
  String get speechDurationDescription =>
      'Asegúrate de hablar al menos 5 segundos y no más de 90.';

  @override
  String get connectionLostDescription =>
      'La conexión se interrumpió. Por favor, verifica tu conexión a internet e inténtalo de nuevo.';

  @override
  String get howToTakeGoodSample => '¿Cómo tomar una buena muestra?';

  @override
  String get goodSampleInstructions =>
      '1. Asegúrate de estar en un lugar tranquilo.\n2. Habla clara y naturalmente.\n3. Asegúrate de que tu dispositivo esté en su posición natural en tu cuello.\n\nUna vez creado, siempre puedes mejorarlo o hacerlo de nuevo.';

  @override
  String get noDeviceConnectedUseMic =>
      'Ningún dispositivo conectado. Se usará el micrófono del teléfono.';

  @override
  String get doItAgain => 'Hazlo de nuevo';

  @override
  String get listenToSpeechProfile => 'Escuchar mi perfil de voz ➡️';

  @override
  String get recognizingOthers => 'Reconociendo a otros 👀';

  @override
  String get keepGoingGreat => 'Sigue así, lo estás haciendo genial';

  @override
  String get somethingWentWrongTryAgain =>
      '¡Algo salió mal! Por favor, inténtalo de nuevo más tarde.';

  @override
  String get uploadingVoiceProfile => 'Subiendo tu perfil de voz....';

  @override
  String get memorizingYourVoice => 'Memorizando tu voz...';

  @override
  String get personalizingExperience => 'Personalizando tu experiencia...';

  @override
  String get keepSpeakingUntil100 => 'Sigue hablando hasta llegar al 100%.';

  @override
  String get greatJobAlmostThere => 'Buen trabajo, ya casi terminas';

  @override
  String get soCloseJustLittleMore => 'Tan cerca, solo un poco más';

  @override
  String get notificationFrequency => 'Frecuencia de notificaciones';

  @override
  String get controlNotificationFrequency =>
      'Controla con qué frecuencia Omi te envía notificaciones proactivas.';

  @override
  String get yourScore => 'Tu puntuación';

  @override
  String get dailyScoreBreakdown => 'Desglose de puntuación diaria';

  @override
  String get todaysScore => 'Puntuación de hoy';

  @override
  String get tasksCompleted => 'Tareas completadas';

  @override
  String get completionRate => 'Tasa de completado';

  @override
  String get howItWorks => 'Cómo funciona';

  @override
  String get dailyScoreExplanation =>
      'Tu puntuación diaria se basa en completar tareas. ¡Completa tus tareas para mejorar tu puntuación!';

  @override
  String get notificationFrequencyDescription =>
      'Controla con qué frecuencia Omi te envía notificaciones proactivas y recordatorios.';

  @override
  String get sliderOff => 'Apagado';

  @override
  String get sliderMax => 'Máx.';

  @override
  String summaryGeneratedFor(String date) {
    return 'Resumen generado para $date';
  }

  @override
  String get failedToGenerateSummary =>
      'Error al generar el resumen. Asegúrate de tener conversaciones para ese día.';

  @override
  String get recap => 'Resumen';

  @override
  String deleteQuoted(String name) {
    return 'Eliminar \"$name\"';
  }

  @override
  String moveConversationsTo(int count) {
    return 'Mover $count conversaciones a:';
  }

  @override
  String get noFolder => 'Sin carpeta';

  @override
  String get removeFromAllFolders => 'Eliminar de todas las carpetas';

  @override
  String get buildAndShareYourCustomApp =>
      'Crea y comparte tu aplicación personalizada';

  @override
  String get searchAppsPlaceholder => 'Buscar en 1500+ aplicaciones';

  @override
  String get filters => 'Filtros';

  @override
  String get frequencyOff => 'Desactivado';

  @override
  String get frequencyMinimal => 'Mínimo';

  @override
  String get frequencyLow => 'Bajo';

  @override
  String get frequencyBalanced => 'Equilibrado';

  @override
  String get frequencyHigh => 'Alto';

  @override
  String get frequencyMaximum => 'Máximo';

  @override
  String get frequencyDescOff => 'Sin notificaciones proactivas';

  @override
  String get frequencyDescMinimal => 'Solo recordatorios críticos';

  @override
  String get frequencyDescLow => 'Solo actualizaciones importantes';

  @override
  String get frequencyDescBalanced => 'Avisos útiles regulares';

  @override
  String get frequencyDescHigh => 'Seguimientos frecuentes';

  @override
  String get frequencyDescMaximum => 'Mantente constantemente conectado';

  @override
  String get clearChatQuestion => '¿Borrar chat?';

  @override
  String get syncingMessages => 'Sincronizando mensajes con el servidor...';

  @override
  String get chatAppsTitle => 'Apps de chat';

  @override
  String get selectApp => 'Seleccionar app';

  @override
  String get noChatAppsEnabled =>
      'No hay apps de chat habilitadas.\nToca \"Habilitar apps\" para agregar algunas.';

  @override
  String get disable => 'Deshabilitar';

  @override
  String get photoLibrary => 'Biblioteca de fotos';

  @override
  String get chooseFile => 'Elegir archivo';

  @override
  String get configureAiPersona => 'Configura tu personaje de IA';

  @override
  String get connectAiAssistantsToYourData =>
      'Conecta asistentes de IA a tus datos';

  @override
  String get oAuth => 'OAuth';

  @override
  String get trackYourGoalsOnHomepage =>
      'Sigue tus objetivos personales en la página principal';

  @override
  String get deleteRecording => 'Eliminar grabación';

  @override
  String get thisCannotBeUndone => 'Esta acción no se puede deshacer.';

  @override
  String get sdCard => 'SD Card';

  @override
  String get fromSd => 'From SD';

  @override
  String get limitless => 'Limitless';

  @override
  String get fastTransfer => 'Transferencia rápida';

  @override
  String get syncingStatus => 'Syncing';

  @override
  String get failedStatus => 'Failed';

  @override
  String etaLabel(String time) {
    return 'ETA: $time';
  }

  @override
  String get transferMethod => 'Método de transferencia';

  @override
  String get fast => 'Fast';

  @override
  String get ble => 'BLE';

  @override
  String get phone => 'Phone';

  @override
  String get cancelSync => 'Cancel Sync';

  @override
  String get cancelSyncMessage =>
      'Los datos ya descargados se guardarán. Puedes reanudar más tarde.';

  @override
  String get syncCancelled => 'Sync cancelled';

  @override
  String get deleteProcessedFiles => 'Eliminar archivos procesados';

  @override
  String get processedFilesDeleted => 'Archivos procesados eliminados';

  @override
  String get wifiEnableFailed =>
      'Error al habilitar WiFi en el dispositivo. Por favor, inténtalo de nuevo.';

  @override
  String get deviceNoFastTransfer =>
      'Tu dispositivo no admite Transferencia rápida. Usa Bluetooth en su lugar.';

  @override
  String get enableHotspotMessage =>
      'Por favor, habilita el punto de acceso de tu teléfono e inténtalo de nuevo.';

  @override
  String get transferStartFailed =>
      'Error al iniciar la transferencia. Por favor, inténtalo de nuevo.';

  @override
  String get deviceNotResponding =>
      'El dispositivo no respondió. Por favor, inténtalo de nuevo.';

  @override
  String get invalidWifiCredentials =>
      'Credenciales WiFi inválidas. Verifica la configuración de tu punto de acceso.';

  @override
  String get wifiConnectionFailed =>
      'La conexión WiFi falló. Por favor, inténtalo de nuevo.';

  @override
  String get sdCardProcessing => 'Procesando tarjeta SD';

  @override
  String sdCardProcessingMessage(int count) {
    return 'Procesando $count grabación(es). Los archivos se eliminarán de la tarjeta SD después.';
  }

  @override
  String get process => 'Process';

  @override
  String get wifiSyncFailed => 'Sincronización WiFi fallida';

  @override
  String get processingFailed => 'Procesamiento fallido';

  @override
  String get downloadingFromSdCard => 'Descargando desde tarjeta SD';

  @override
  String processingProgress(int current, int total) {
    return 'Procesando $current/$total';
  }

  @override
  String conversationsCreated(int count) {
    return '$count conversaciones creadas';
  }

  @override
  String get internetRequired => 'Se requiere conexión a Internet';

  @override
  String get processAudio => 'Process Audio';

  @override
  String get start => 'Start';

  @override
  String get noRecordings => 'No Recordings';

  @override
  String get audioFromOmiWillAppearHere =>
      'El audio de tu dispositivo Omi aparecerá aquí';

  @override
  String get deleteProcessed => 'Eliminar procesados';

  @override
  String get tryDifferentFilter => 'Prueba un filtro diferente';

  @override
  String get recordings => 'Recordings';

  @override
  String get enableRemindersAccess =>
      'Por favor, habilite el acceso a Recordatorios en Ajustes para usar los Recordatorios de Apple';

  @override
  String todayAtTime(String time) {
    return 'Hoy a las $time';
  }

  @override
  String yesterdayAtTime(String time) {
    return 'Ayer a las $time';
  }

  @override
  String get lessThanAMinute => 'Menos de un minuto';

  @override
  String estimatedMinutes(int count) {
    return '~$count minuto(s)';
  }

  @override
  String estimatedHours(int count) {
    return '~$count hora(s)';
  }

  @override
  String estimatedTimeRemaining(String time) {
    return 'Estimado: $time restante';
  }

  @override
  String get summarizingConversation =>
      'Resumiendo conversación...\nEsto puede tardar unos segundos';

  @override
  String get resummarizingConversation =>
      'Re-resumiendo conversación...\nEsto puede tardar unos segundos';

  @override
  String get nothingInterestingRetry =>
      'No se encontró nada interesante,\n¿quieres intentarlo de nuevo?';

  @override
  String get noSummaryForConversation =>
      'No hay resumen disponible\npara esta conversación.';

  @override
  String get unknownLocation => 'Ubicación desconocida';

  @override
  String get couldNotLoadMap => 'No se pudo cargar el mapa';

  @override
  String get triggerConversationIntegration =>
      'Activar integración de creación de conversación';

  @override
  String get webhookUrlNotSet => 'URL de webhook no configurada';

  @override
  String get setWebhookUrlInSettings =>
      'Por favor, configura la URL del webhook en ajustes de desarrollador.';

  @override
  String get sendWebUrl => 'Enviar URL web';

  @override
  String get sendTranscript => 'Enviar transcripción';

  @override
  String get sendSummary => 'Enviar resumen';

  @override
  String get debugModeDetected => 'Modo de depuración detectado';

  @override
  String get performanceReduced => 'El rendimiento puede verse reducido';

  @override
  String autoClosingInSeconds(int seconds) {
    return 'Cerrando automáticamente en $seconds segundos';
  }

  @override
  String get modelRequired => 'Modelo requerido';

  @override
  String get downloadWhisperModel =>
      'Descarga un modelo whisper para usar la transcripción en el dispositivo';

  @override
  String get deviceNotCompatible =>
      'Tu dispositivo no es compatible con la transcripción en el dispositivo';

  @override
  String get deviceRequirements =>
      'Tu dispositivo no cumple con los requisitos para la transcripción en el dispositivo.';

  @override
  String get willLikelyCrash =>
      'Habilitar esto probablemente causará que la aplicación se bloquee o se congele.';

  @override
  String get transcriptionSlowerLessAccurate =>
      'La transcripción será significativamente más lenta y menos precisa.';

  @override
  String get proceedAnyway => 'Continuar de todos modos';

  @override
  String get olderDeviceDetected => 'Dispositivo antiguo detectado';

  @override
  String get onDeviceSlower =>
      'La transcripción en el dispositivo puede ser más lenta en este dispositivo.';

  @override
  String get batteryUsageHigher =>
      'El uso de batería será mayor que la transcripción en la nube.';

  @override
  String get considerOmiCloud =>
      'Considera usar Omi Cloud para un mejor rendimiento.';

  @override
  String get highResourceUsage => 'Alto uso de recursos';

  @override
  String get onDeviceIntensive =>
      'La transcripción en el dispositivo requiere muchos recursos computacionales.';

  @override
  String get batteryDrainIncrease =>
      'El consumo de batería aumentará significativamente.';

  @override
  String get deviceMayWarmUp =>
      'El dispositivo puede calentarse durante el uso prolongado.';

  @override
  String get speedAccuracyLower =>
      'La velocidad y precisión pueden ser menores que los modelos en la nube.';

  @override
  String get cloudProvider => 'Proveedor en la nube';

  @override
  String get premiumMinutesInfo =>
      '1.200 minutos premium/mes. La pestaña En el dispositivo ofrece transcripción gratuita ilimitada.';

  @override
  String get viewUsage => 'Ver uso';

  @override
  String get localProcessingInfo =>
      'El audio se procesa localmente. Funciona sin conexión, más privado, pero consume más batería.';

  @override
  String get model => 'Modelo';

  @override
  String get performanceWarning => 'Advertencia de rendimiento';

  @override
  String get largeModelWarning =>
      'Este modelo es grande y puede bloquear la aplicación o funcionar muy lento en dispositivos móviles.\n\nSe recomienda \"small\" o \"base\".';

  @override
  String get usingNativeIosSpeech =>
      'Usando reconocimiento de voz nativo de iOS';

  @override
  String get noModelDownloadRequired =>
      'Se utilizará el motor de voz nativo de tu dispositivo. No se requiere descarga de modelo.';

  @override
  String get modelReady => 'Modelo listo';

  @override
  String get redownload => 'Volver a descargar';

  @override
  String get doNotCloseApp => 'Por favor, no cierres la aplicación.';

  @override
  String get downloading => 'Descargando...';

  @override
  String get downloadModel => 'Descargar modelo';

  @override
  String estimatedSize(String size) {
    return 'Tamaño estimado: ~$size MB';
  }

  @override
  String availableSpace(String space) {
    return 'Espacio disponible: $space';
  }

  @override
  String get notEnoughSpace => 'Advertencia: ¡No hay suficiente espacio!';

  @override
  String get download => 'Descargar';

  @override
  String downloadError(String error) {
    return 'Error de descarga: $error';
  }

  @override
  String get cancelled => 'Cancelado';

  @override
  String get deviceNotCompatibleTitle => 'Dispositivo no compatible';

  @override
  String get deviceNotMeetRequirements =>
      'Tu dispositivo no cumple los requisitos para la transcripción en el dispositivo.';

  @override
  String get transcriptionSlowerOnDevice =>
      'La transcripción en el dispositivo puede ser más lenta en este dispositivo.';

  @override
  String get computationallyIntensive =>
      'La transcripción en el dispositivo es computacionalmente intensiva.';

  @override
  String get batteryDrainSignificantly =>
      'El consumo de batería aumentará significativamente.';

  @override
  String get premiumMinutesMonth =>
      '1.200 minutos premium/mes. La pestaña En dispositivo ofrece transcripción gratuita ilimitada. ';

  @override
  String get audioProcessedLocally =>
      'El audio se procesa localmente. Funciona sin conexión, más privado, pero usa más batería.';

  @override
  String get languageLabel => 'Idioma';

  @override
  String get modelLabel => 'Modelo';

  @override
  String get modelTooLargeWarning =>
      'Este modelo es grande y puede causar que la aplicación se bloquee o funcione muy lentamente en dispositivos móviles.\n\nSe recomienda small o base.';

  @override
  String get nativeEngineNoDownload =>
      'Se usará el motor de voz nativo de tu dispositivo. No se requiere descarga de modelo.';

  @override
  String modelReadyWithName(String model) {
    return 'Modelo listo ($model)';
  }

  @override
  String get reDownload => 'Volver a descargar';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return 'Descargando $model: $received / $total MB';
  }

  @override
  String preparingModel(String model) {
    return 'Preparando $model...';
  }

  @override
  String downloadErrorWithMessage(String error) {
    return 'Error de descarga: $error';
  }

  @override
  String estimatedSizeWithValue(String size) {
    return 'Tamaño estimado: ~$size MB';
  }

  @override
  String availableSpaceWithValue(String space) {
    return 'Espacio disponible: $space';
  }

  @override
  String get omiTranscriptionOptimized =>
      'La transcripción en vivo integrada de Omi está optimizada para conversaciones en tiempo real con detección automática de hablantes y diarización.';

  @override
  String get reset => 'Restablecer';

  @override
  String get useTemplateFrom => 'Usar plantilla de';

  @override
  String get selectProviderTemplate =>
      'Selecciona una plantilla de proveedor...';

  @override
  String get quicklyPopulateResponse =>
      'Rellenar rápidamente con formato de respuesta de proveedor conocido';

  @override
  String get quicklyPopulateRequest =>
      'Rellenar rápidamente con formato de solicitud de proveedor conocido';

  @override
  String get invalidJsonError => 'JSON no válido';

  @override
  String downloadModelWithName(String model) {
    return 'Descargar modelo ($model)';
  }

  @override
  String modelNameWithFile(String model) {
    return 'Modelo: $model';
  }

  @override
  String get device => 'Device';

  @override
  String get chatAssistantsTitle => 'Asistentes de chat';

  @override
  String get permissionReadConversations => 'Leer conversaciones';

  @override
  String get permissionReadMemories => 'Leer recuerdos';

  @override
  String get permissionReadTasks => 'Leer tareas';

  @override
  String get permissionCreateConversations => 'Crear conversaciones';

  @override
  String get permissionCreateMemories => 'Crear recuerdos';

  @override
  String get permissionTypeAccess => 'Acceso';

  @override
  String get permissionTypeCreate => 'Crear';

  @override
  String get permissionTypeTrigger => 'Disparador';

  @override
  String get permissionDescReadConversations =>
      'Esta app puede acceder a tus conversaciones.';

  @override
  String get permissionDescReadMemories =>
      'Esta app puede acceder a tus recuerdos.';

  @override
  String get permissionDescReadTasks => 'Esta app puede acceder a tus tareas.';

  @override
  String get permissionDescCreateConversations =>
      'Esta app puede crear nuevas conversaciones.';

  @override
  String get permissionDescCreateMemories =>
      'Esta app puede crear nuevos recuerdos.';

  @override
  String get realtimeListening => 'Escucha en tiempo real';

  @override
  String get setupCompleted => 'Completado';

  @override
  String get pleaseSelectRating => 'Por favor selecciona una valoración';

  @override
  String get writeReviewOptional => 'Escribe una reseña (opcional)';

  @override
  String get setupQuestionsIntro =>
      'Ayúdanos a mejorar Omi respondiendo algunas preguntas. 🫶 💜';

  @override
  String get setupQuestionProfession => '1. ¿A qué te dedicas?';

  @override
  String get setupQuestionUsage => '2. ¿Dónde planeas usar tu Omi?';

  @override
  String get setupQuestionAge => '3. ¿Cuál es tu rango de edad?';

  @override
  String get setupAnswerAllQuestions =>
      '¡Aún no has respondido todas las preguntas! 🥺';

  @override
  String get setupSkipHelp => 'Omitir, no quiero ayudar :C';

  @override
  String get professionEntrepreneur => 'Emprendedor';

  @override
  String get professionSoftwareEngineer => 'Ingeniero de Software';

  @override
  String get professionProductManager => 'Gerente de Producto';

  @override
  String get professionExecutive => 'Ejecutivo';

  @override
  String get professionSales => 'Ventas';

  @override
  String get professionStudent => 'Estudiante';

  @override
  String get usageAtWork => 'En el trabajo';

  @override
  String get usageIrlEvents => 'Eventos presenciales';

  @override
  String get usageOnline => 'En línea';

  @override
  String get usageSocialSettings => 'En entornos sociales';

  @override
  String get usageEverywhere => 'En todas partes';

  @override
  String get customBackendUrlTitle => 'URL del servidor personalizado';

  @override
  String get backendUrlLabel => 'URL del servidor';

  @override
  String get saveUrlButton => 'Guardar URL';

  @override
  String get enterBackendUrlError => 'Por favor, introduce la URL del servidor';

  @override
  String get urlMustEndWithSlashError => 'La URL debe terminar con \"/\"';

  @override
  String get invalidUrlError => 'Por favor, introduce una URL válida';

  @override
  String get backendUrlSavedSuccess =>
      '¡URL del servidor guardada correctamente!';

  @override
  String get signInTitle => 'Iniciar sesión';

  @override
  String get signInButton => 'Iniciar sesión';

  @override
  String get enterEmailError => 'Por favor, introduce tu correo electrónico';

  @override
  String get invalidEmailError =>
      'Por favor, introduce un correo electrónico válido';

  @override
  String get enterPasswordError => 'Por favor, introduce tu contraseña';

  @override
  String get passwordMinLengthError =>
      'La contraseña debe tener al menos 8 caracteres';

  @override
  String get signInSuccess => '¡Inicio de sesión exitoso!';

  @override
  String get alreadyHaveAccountLogin => '¿Ya tienes una cuenta? Inicia sesión';

  @override
  String get emailLabel => 'Correo electrónico';

  @override
  String get passwordLabel => 'Contraseña';

  @override
  String get createAccountTitle => 'Crear cuenta';

  @override
  String get nameLabel => 'Nombre';

  @override
  String get repeatPasswordLabel => 'Repetir contraseña';

  @override
  String get signUpButton => 'Registrarse';

  @override
  String get enterNameError => 'Por favor, introduce tu nombre';

  @override
  String get passwordsDoNotMatch => 'Las contraseñas no coinciden';

  @override
  String get signUpSuccess => '¡Registro exitoso!';

  @override
  String get loadingKnowledgeGraph => 'Cargando gráfico de conocimiento...';

  @override
  String get noKnowledgeGraphYet => 'Aún no hay gráfico de conocimiento';

  @override
  String get buildingKnowledgeGraphFromMemories =>
      'Construyendo gráfico de conocimiento a partir de recuerdos...';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'Tu gráfico de conocimiento se construirá automáticamente cuando crees nuevos recuerdos.';

  @override
  String get buildGraphButton => 'Construir gráfico';

  @override
  String get checkOutMyMemoryGraph => '¡Mira mi gráfico de memoria!';

  @override
  String get getButton => 'Obtener';

  @override
  String openingApp(String appName) {
    return 'Abriendo $appName...';
  }

  @override
  String get writeSomething => 'Escribe algo';

  @override
  String get submitReply => 'Enviar respuesta';

  @override
  String get editYourReply => 'Editar tu respuesta';

  @override
  String get replyToReview => 'Responder a la reseña';

  @override
  String get rateAndReviewThisApp => 'Califica y reseña esta aplicación';

  @override
  String get noChangesInReview =>
      'No hay cambios en la reseña para actualizar.';

  @override
  String get cantRateWithoutInternet =>
      'No se puede calificar la app sin conexión a Internet.';

  @override
  String get appAnalytics => 'Análisis de la app';

  @override
  String get learnMoreLink => 'más información';

  @override
  String get moneyEarned => 'Dinero ganado';

  @override
  String get writeYourReply => 'Escribe tu respuesta...';

  @override
  String get replySentSuccessfully => 'Respuesta enviada correctamente';

  @override
  String failedToSendReply(String error) {
    return 'Error al enviar respuesta: $error';
  }

  @override
  String get send => 'Enviar';

  @override
  String starFilter(int count) {
    return '$count Estrella';
  }

  @override
  String get noReviewsFound => 'No se encontraron reseñas';

  @override
  String get editReply => 'Editar respuesta';

  @override
  String get reply => 'Responder';

  @override
  String starFilterLabel(int count) {
    return '$count estrella';
  }

  @override
  String get sharePublicLink => 'Compartir enlace público';

  @override
  String get makePersonaPublic => 'Hacer personaje público';

  @override
  String get connectedKnowledgeData => 'Datos de conocimiento conectados';

  @override
  String get enterName => 'Enter name';

  @override
  String get disconnectTwitter => 'Desconectar Twitter';

  @override
  String get disconnectTwitterConfirmation =>
      '¿Estás seguro de que deseas desconectar tu cuenta de Twitter? Tu personaje ya no tendrá acceso a tus datos de Twitter.';

  @override
  String get getOmiDeviceDescription =>
      'Crea un clon más preciso con tus conversaciones personales';

  @override
  String get getOmi => 'Get Omi';

  @override
  String get iHaveOmiDevice => 'Tengo un dispositivo Omi';

  @override
  String get goal => 'META';

  @override
  String get tapToTrackThisGoal => 'Toca para seguir esta meta';

  @override
  String get tapToSetAGoal => 'Toca para establecer una meta';

  @override
  String get processedConversations => 'Conversaciones procesadas';

  @override
  String get updatedConversations => 'Conversaciones actualizadas';

  @override
  String get newConversations => 'Nuevas conversaciones';

  @override
  String get summaryTemplate => 'Plantilla de resumen';

  @override
  String get suggestedTemplates => 'Plantillas sugeridas';

  @override
  String get otherTemplates => 'Otras plantillas';

  @override
  String get availableTemplates => 'Plantillas disponibles';

  @override
  String get getCreative => 'Sé creativo';

  @override
  String get defaultLabel => 'Predeterminada';

  @override
  String get lastUsedLabel => 'Último uso';

  @override
  String get setDefaultApp => 'Establecer app predeterminada';

  @override
  String setDefaultAppContent(String appName) {
    return '¿Establecer $appName como tu app de resumen predeterminada?\\n\\nEsta app se usará automáticamente para todos los resúmenes de conversaciones futuras.';
  }

  @override
  String get setDefaultButton => 'Establecer predeterminada';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName establecida como app de resumen predeterminada';
  }

  @override
  String get createCustomTemplate => 'Crear plantilla personalizada';

  @override
  String get allTemplates => 'Todas las plantillas';

  @override
  String failedToInstallApp(String appName) {
    return 'Error al instalar $appName. Por favor, inténtalo de nuevo.';
  }

  @override
  String errorInstallingApp(String appName, String error) {
    return 'Error al instalar $appName: $error';
  }

  @override
  String tagSpeaker(int speakerId) {
    return 'Etiquetar Hablante $speakerId';
  }

  @override
  String get personNameAlreadyExists =>
      'Ya existe una persona con este nombre.';

  @override
  String get selectYouFromList =>
      'Para etiquetarte a ti mismo, selecciona \"Tú\" de la lista.';

  @override
  String get enterPersonsName => 'Introduce el nombre de la persona';

  @override
  String get addPerson => 'Add Person';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'Etiquetar otros segmentos de este hablante ($selected/$total)';
  }

  @override
  String get tagOtherSegments => 'Etiquetar otros segmentos';

  @override
  String get managePeople => 'Manage People';

  @override
  String get shareViaSms => 'Compartir por SMS';

  @override
  String get selectContactsToShareSummary =>
      'Selecciona contactos para compartir el resumen de tu conversación';

  @override
  String get searchContactsHint => 'Buscar contactos...';

  @override
  String contactsSelectedCount(int count) {
    return '$count seleccionados';
  }

  @override
  String get clearAllSelection => 'Borrar todo';

  @override
  String get selectContactsToShare => 'Selecciona contactos para compartir';

  @override
  String shareWithContactCount(int count) {
    return 'Compartir con $count contacto';
  }

  @override
  String shareWithContactsCount(int count) {
    return 'Compartir con $count contactos';
  }

  @override
  String get contactsPermissionRequired => 'Se requiere permiso de contactos';

  @override
  String get contactsPermissionRequiredForSms =>
      'Se requiere permiso de contactos para compartir por SMS';

  @override
  String get grantContactsPermissionForSms =>
      'Por favor, concede permiso de contactos para compartir por SMS';

  @override
  String get noContactsWithPhoneNumbers =>
      'No se encontraron contactos con números de teléfono';

  @override
  String get noContactsMatchSearch =>
      'Ningún contacto coincide con tu búsqueda';

  @override
  String get failedToLoadContacts => 'Error al cargar los contactos';

  @override
  String get failedToPrepareConversationForSharing =>
      'Error al preparar la conversación para compartir. Por favor, inténtalo de nuevo.';

  @override
  String get couldNotOpenSmsApp =>
      'No se pudo abrir la aplicación de SMS. Por favor, inténtalo de nuevo.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'Aquí está lo que acabamos de discutir: $link';
  }

  @override
  String get wifiSync => 'Sincronización WiFi';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item copiado al portapapeles';
  }

  @override
  String get wifiConnectionFailedTitle => 'Conexión fallida';

  @override
  String connectingToDeviceName(String deviceName) {
    return 'Conectando a $deviceName';
  }

  @override
  String enableDeviceWifi(String deviceName) {
    return 'Habilitar WiFi de $deviceName';
  }

  @override
  String connectToDeviceName(String deviceName) {
    return 'Conectar a $deviceName';
  }

  @override
  String get recordingDetails => 'Detalles de grabación';

  @override
  String get storageLocationSdCard => 'SD Card';

  @override
  String get storageLocationLimitlessPendant => 'Colgante Limitless';

  @override
  String get storageLocationPhone => 'Phone';

  @override
  String get storageLocationPhoneMemory => 'Phone (Memory)';

  @override
  String storedOnDevice(String deviceName) {
    return 'Almacenado en $deviceName';
  }

  @override
  String get transferring => 'Transferring...';

  @override
  String get transferRequired => 'Transferencia requerida';

  @override
  String get downloadingAudioFromSdCard =>
      'Descargando audio de la tarjeta SD de tu dispositivo';

  @override
  String get transferRequiredDescription =>
      'Esta grabación está almacenada en la tarjeta SD de tu dispositivo. Transfiérela a tu teléfono para reproducirla o compartirla.';

  @override
  String get cancelTransfer => 'Cancelar transferencia';

  @override
  String get transferToPhone => 'Transferir al teléfono';

  @override
  String get privateAndSecureOnDevice => 'Privado y seguro en tu dispositivo';

  @override
  String get recordingInfo => 'Recording Info';

  @override
  String get transferInProgress => 'Transferencia en progreso...';

  @override
  String get shareRecording => 'Compartir grabación';

  @override
  String get deleteRecordingConfirmation =>
      '¿Estás seguro de que deseas eliminar permanentemente esta grabación? Esta acción no se puede deshacer.';

  @override
  String get recordingIdLabel => 'Recording ID';

  @override
  String get dateTimeLabel => 'Date & Time';

  @override
  String get durationLabel => 'Duration';

  @override
  String get audioFormatLabel => 'Audio Format';

  @override
  String get storageLocationLabel => 'Ubicación de almacenamiento';

  @override
  String get estimatedSizeLabel => 'Estimated Size';

  @override
  String get deviceModelLabel => 'Device Model';

  @override
  String get deviceIdLabel => 'Device ID';

  @override
  String get statusLabel => 'Estado';

  @override
  String get statusProcessed => 'Processed';

  @override
  String get statusUnprocessed => 'Unprocessed';

  @override
  String get switchedToFastTransfer => 'Cambiado a Transferencia rápida';

  @override
  String get transferCompleteMessage =>
      '¡Transferencia completada! Ahora puedes reproducir esta grabación.';

  @override
  String transferFailedMessage(String error) {
    return 'Transferencia fallida: $error';
  }

  @override
  String get transferCancelled => 'Transferencia cancelada';

  @override
  String get fastTransferEnabled => 'Transferencia rápida habilitada';

  @override
  String get bluetoothSyncEnabled => 'Sincronización Bluetooth habilitada';

  @override
  String get enableFastTransfer => 'Habilitar transferencia rápida';

  @override
  String get fastTransferDescription =>
      'La transferencia rápida usa WiFi para velocidades ~5x más rápidas. Tu teléfono se conectará temporalmente a la red WiFi de tu dispositivo Omi durante la transferencia.';

  @override
  String get internetAccessPausedDuringTransfer =>
      'El acceso a internet se pausa durante la transferencia';

  @override
  String get chooseTransferMethodDescription =>
      'Elige cómo se transfieren las grabaciones de tu dispositivo Omi a tu teléfono.';

  @override
  String get wifiSpeed => '~150 KB/s vía WiFi';

  @override
  String get fiveTimesFaster => '5X MÁS RÁPIDO';

  @override
  String get fastTransferMethodDescription =>
      'Crea una conexión WiFi directa a tu dispositivo Omi. Tu teléfono se desconecta temporalmente de tu WiFi habitual durante la transferencia.';

  @override
  String get bluetooth => 'Bluetooth';

  @override
  String get bleSpeed => '~30 KB/s vía BLE';

  @override
  String get bluetoothMethodDescription =>
      'Usa conexión Bluetooth Low Energy estándar. Más lento pero no afecta tu conexión WiFi.';

  @override
  String get selected => 'Seleccionado';

  @override
  String get selectOption => 'Seleccionar';

  @override
  String get lowBatteryAlertTitle => 'Alerta de batería baja';

  @override
  String get lowBatteryAlertBody =>
      'La batería de tu dispositivo está baja. ¡Es hora de recargar! 🔋';

  @override
  String get deviceDisconnectedNotificationTitle =>
      'Tu dispositivo Omi se desconectó';

  @override
  String get deviceDisconnectedNotificationBody =>
      'Por favor, vuelve a conectar para seguir usando tu Omi.';

  @override
  String get firmwareUpdateAvailable => 'Actualización de firmware disponible';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'Hay una nueva actualización de firmware ($version) disponible para tu dispositivo Omi. ¿Deseas actualizar ahora?';
  }

  @override
  String get later => 'Más tarde';

  @override
  String get appDeletedSuccessfully => 'App eliminada con éxito';

  @override
  String get appDeleteFailed =>
      'Error al eliminar la app. Por favor, inténtalo de nuevo más tarde.';

  @override
  String get appVisibilityChangedSuccessfully =>
      'La visibilidad de la app se cambió con éxito. Puede tardar unos minutos en reflejarse.';

  @override
  String get errorActivatingAppIntegration =>
      'Error al activar la app. Si es una app de integración, asegúrate de que la configuración esté completa.';

  @override
  String get errorUpdatingAppStatus =>
      'Ocurrió un error al actualizar el estado de la app.';

  @override
  String get calculatingETA => 'Calculating...';

  @override
  String aboutMinutesRemaining(int minutes) {
    return 'Quedan aproximadamente $minutes minutos';
  }

  @override
  String get aboutAMinuteRemaining => 'Queda aproximadamente un minuto';

  @override
  String get almostDone => 'Almost done...';

  @override
  String get omiSays => 'omi says';

  @override
  String get analyzingYourData => 'Analizando tus datos...';

  @override
  String migratingToProtection(String level) {
    return 'Migrando a protección $level...';
  }

  @override
  String get noDataToMigrateFinalizing =>
      'No hay datos para migrar. Finalizando...';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return 'Migrando $itemType... $percentage%';
  }

  @override
  String get allObjectsMigratedFinalizing =>
      'Todos los objetos migrados. Finalizando...';

  @override
  String get migrationErrorOccurred =>
      'Ocurrió un error durante la migración. Por favor, inténtalo de nuevo.';

  @override
  String get migrationComplete => '¡Migración completada!';

  @override
  String dataProtectedWithSettings(String level) {
    return 'Tus datos están ahora protegidos con la nueva configuración $level.';
  }

  @override
  String get chatsLowercase => 'chats';

  @override
  String get dataLowercase => 'data';

  @override
  String get fallNotificationTitle => 'Ouch';

  @override
  String get fallNotificationBody => 'Did you fall?';

  @override
  String get importantConversationTitle => 'Conversación importante';

  @override
  String get importantConversationBody =>
      'Acabas de tener una conversación importante. Toca para compartir el resumen.';

  @override
  String get templateName => 'Nombre de plantilla';

  @override
  String get templateNameHint => 'ej. Extractor de acciones de reunión';

  @override
  String get nameMustBeAtLeast3Characters =>
      'El nombre debe tener al menos 3 caracteres';

  @override
  String get conversationPromptHint =>
      'ej., Extrae elementos de acción, decisiones tomadas y puntos clave de la conversación proporcionada.';

  @override
  String get pleaseEnterAppPrompt =>
      'Por favor, introduce una indicación para tu aplicación';

  @override
  String get promptMustBeAtLeast10Characters =>
      'La indicación debe tener al menos 10 caracteres';

  @override
  String get anyoneCanDiscoverTemplate =>
      'Cualquiera puede descubrir tu plantilla';

  @override
  String get onlyYouCanUseTemplate => 'Solo tú puedes usar esta plantilla';

  @override
  String get generatingDescription => 'Generando descripción...';

  @override
  String get creatingAppIcon => 'Creando icono de la aplicación...';

  @override
  String get installingApp => 'Instalando aplicación...';

  @override
  String get appCreatedAndInstalled => '¡Aplicación creada e instalada!';

  @override
  String get appCreatedSuccessfully => '¡Aplicación creada con éxito!';

  @override
  String get failedToCreateApp =>
      'Error al crear la aplicación. Por favor, inténtalo de nuevo.';

  @override
  String get addAppSelectCoreCapability =>
      'Por favor seleccione una capacidad principal más para su aplicación';

  @override
  String get addAppSelectPaymentPlan =>
      'Por favor seleccione un plan de pago e ingrese un precio para su aplicación';

  @override
  String get addAppSelectCapability =>
      'Por favor seleccione al menos una capacidad para su aplicación';

  @override
  String get addAppSelectLogo =>
      'Por favor seleccione un logo para su aplicación';

  @override
  String get addAppEnterChatPrompt =>
      'Por favor ingrese un mensaje de chat para su aplicación';

  @override
  String get addAppEnterConversationPrompt =>
      'Por favor ingrese un mensaje de conversación para su aplicación';

  @override
  String get addAppSelectTriggerEvent =>
      'Por favor seleccione un evento desencadenante para su aplicación';

  @override
  String get addAppEnterWebhookUrl =>
      'Por favor ingrese una URL de webhook para su aplicación';

  @override
  String get addAppSelectCategory =>
      'Por favor seleccione una categoría para su aplicación';

  @override
  String get addAppFillRequiredFields =>
      'Por favor complete correctamente todos los campos requeridos';

  @override
  String get addAppUpdatedSuccess => 'Aplicación actualizada exitosamente 🚀';

  @override
  String get addAppUpdateFailed =>
      'Error al actualizar la aplicación. Por favor intente más tarde';

  @override
  String get addAppSubmittedSuccess => 'Aplicación enviada exitosamente 🚀';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'Error al abrir el selector de archivos: $message';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'Error al seleccionar imagen: $error';
  }

  @override
  String get addAppPhotosPermissionDenied =>
      'Permiso de fotos denegado. Por favor permita el acceso a fotos';

  @override
  String get addAppErrorSelectingImageRetry =>
      'Error al seleccionar imagen. Por favor intente de nuevo.';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'Error al seleccionar miniatura: $error';
  }

  @override
  String get addAppErrorSelectingThumbnailRetry =>
      'Error al seleccionar miniatura. Por favor intente de nuevo.';

  @override
  String get addAppCapabilityConflictWithPersona =>
      'No se pueden seleccionar otras capacidades con Persona';

  @override
  String get addAppPersonaConflictWithCapabilities =>
      'Persona no se puede seleccionar con otras capacidades';

  @override
  String get personaTwitterHandleNotFound => 'Usuario de Twitter no encontrado';

  @override
  String get personaTwitterHandleSuspended => 'Usuario de Twitter suspendido';

  @override
  String get personaFailedToVerifyTwitter =>
      'Error al verificar usuario de Twitter';

  @override
  String get personaFailedToFetch => 'Error al obtener tu persona';

  @override
  String get personaFailedToCreate => 'Error al crear tu persona';

  @override
  String get personaConnectKnowledgeSource =>
      'Por favor conecte al menos una fuente de datos (Omi o Twitter)';

  @override
  String get personaUpdatedSuccessfully => 'Persona actualizada exitosamente';

  @override
  String get personaFailedToUpdate => 'Error al actualizar persona';

  @override
  String get personaPleaseSelectImage => 'Por favor seleccione una imagen';

  @override
  String get personaFailedToCreateTryLater =>
      'Error al crear persona. Por favor intente más tarde.';

  @override
  String personaFailedToCreateWithError(String error) {
    return 'Error al crear persona: $error';
  }

  @override
  String get personaFailedToEnable => 'Error al habilitar persona';

  @override
  String personaErrorEnablingWithError(String error) {
    return 'Error al habilitar persona: $error';
  }

  @override
  String get paymentFailedToFetchCountries =>
      'Error al obtener países compatibles. Por favor intente más tarde.';

  @override
  String get paymentFailedToSetDefault =>
      'Error al establecer método de pago predeterminado. Por favor intente más tarde.';

  @override
  String get paymentFailedToSavePaypal =>
      'Error al guardar detalles de PayPal. Por favor intente más tarde.';

  @override
  String get paypalEmailHint => 'nik@example.com';

  @override
  String get paypalMeLinkHint => 'paypal.me/nik';

  @override
  String get paymentMethodStripe => 'Stripe';

  @override
  String get paymentMethodPayPal => 'PayPal';

  @override
  String get paymentStatusActive => 'Activo';

  @override
  String get paymentStatusConnected => 'Conectado';

  @override
  String get paymentStatusNotConnected => 'No conectado';

  @override
  String get paymentAppCost => 'Costo de la aplicación';

  @override
  String get paymentEnterValidAmount => 'Por favor ingrese un monto válido';

  @override
  String get paymentEnterAmountGreaterThanZero =>
      'Por favor ingrese un monto mayor a 0';

  @override
  String get paymentPlan => 'Plan de pago';

  @override
  String get paymentNoneSelected => 'Ninguno seleccionado';

  @override
  String get aiGenPleaseEnterDescription =>
      'Por favor, introduce una descripción para tu aplicación';

  @override
  String get aiGenCreatingAppIcon => 'Creando icono de la aplicación...';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'Se produjo un error: $message';
  }

  @override
  String get aiGenAppCreatedSuccessfully => '¡Aplicación creada con éxito!';

  @override
  String get aiGenFailedToCreateApp => 'No se pudo crear la aplicación';

  @override
  String get aiGenErrorWhileCreatingApp =>
      'Se produjo un error al crear la aplicación';

  @override
  String get aiGenFailedToGenerateApp =>
      'No se pudo generar la aplicación. Por favor, inténtalo de nuevo.';

  @override
  String get aiGenFailedToRegenerateIcon => 'No se pudo regenerar el icono';

  @override
  String get aiGenPleaseGenerateAppFirst =>
      'Por favor, genera una aplicación primero';

  @override
  String get xHandleTitle => '¿Cuál es tu usuario de X?';

  @override
  String get xHandleDescription => 'Pre-entrenaremos tu clon de Omi';

  @override
  String get xHandleHint => '@nikshevchenko';

  @override
  String get xHandlePleaseEnter => 'Por favor, introduce tu usuario de X';

  @override
  String get xHandlePleaseEnterValid =>
      'Por favor, introduce un usuario de X válido';

  @override
  String get nextButton => 'Next';

  @override
  String get connectOmiDevice => 'Conectar dispositivo Omi';

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'Estás cambiando tu Plan Ilimitado al $title. ¿Estás seguro de que deseas continuar?';
  }

  @override
  String get planUpgradeScheduledMessage =>
      '¡Actualización programada! Tu plan mensual continúa hasta el final de tu período de facturación, luego cambia automáticamente a anual.';

  @override
  String get couldNotSchedulePlanChange =>
      'No se pudo programar el cambio de plan. Por favor, inténtalo de nuevo.';

  @override
  String get subscriptionReactivatedDefault =>
      '¡Tu suscripción ha sido reactivada! Sin cargo ahora - se te facturará al final de tu período actual.';

  @override
  String get subscriptionSuccessfulCharged =>
      '¡Suscripción exitosa! Se te ha cobrado por el nuevo período de facturación.';

  @override
  String get couldNotProcessSubscription =>
      'No se pudo procesar la suscripción. Por favor, inténtalo de nuevo.';

  @override
  String get couldNotLaunchUpgradePage =>
      'No se pudo abrir la página de actualización. Por favor, inténtalo de nuevo.';

  @override
  String get transcriptionJsonPlaceholder =>
      'Paste your JSON configuration here...';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get pricePlaceholder => '0.00';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'Error al abrir el selector de archivos: $message';
  }

  @override
  String importErrorGeneric(String error) {
    return 'Error: $error';
  }

  @override
  String get mergeConversationsSuccessTitle =>
      'Conversaciones fusionadas con éxito';

  @override
  String mergeConversationsSuccessBody(int count) {
    return '$count conversaciones se han fusionado con éxito';
  }

  @override
  String get dailyReflectionNotificationTitle => 'Hora de la reflexión diaria';

  @override
  String get dailyReflectionNotificationBody => 'Cuéntame sobre tu día';

  @override
  String get actionItemReminderTitle => 'Recordatorio de Omi';

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName desconectado';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'Por favor, vuelve a conectar para continuar usando tu $deviceName.';
  }

  @override
  String get onboardingSignIn => 'Iniciar sesión';

  @override
  String get onboardingYourName => 'Tu nombre';

  @override
  String get onboardingLanguage => 'Idioma';

  @override
  String get onboardingPermissions => 'Permisos';

  @override
  String get onboardingComplete => 'Completo';

  @override
  String get onboardingWelcomeToOmi => 'Bienvenido a Omi';

  @override
  String get onboardingTellUsAboutYourself => 'Cuéntanos sobre ti';

  @override
  String get onboardingChooseYourPreference => 'Elige tu preferencia';

  @override
  String get onboardingGrantRequiredAccess => 'Conceder acceso requerido';

  @override
  String get onboardingYoureAllSet => 'Ya estás listo';

  @override
  String get searchTranscriptOrSummary =>
      'Buscar en transcripción o resumen...';

  @override
  String get myGoal => 'Mi objetivo';

  @override
  String get appNotAvailable =>
      '¡Vaya! Parece que la aplicación que buscas no está disponible.';

  @override
  String get failedToConnectTodoist => 'Error al conectar con Todoist';

  @override
  String get failedToConnectAsana => 'Error al conectar con Asana';

  @override
  String get failedToConnectGoogleTasks => 'Error al conectar con Google Tasks';

  @override
  String get failedToConnectClickUp => 'Error al conectar con ClickUp';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return 'Error al conectar con $serviceName: $error';
  }

  @override
  String get successfullyConnectedTodoist =>
      '¡Conectado correctamente a Todoist!';

  @override
  String get failedToConnectTodoistRetry =>
      'Error al conectar con Todoist. Por favor, inténtalo de nuevo.';

  @override
  String get successfullyConnectedAsana => '¡Conectado correctamente a Asana!';

  @override
  String get failedToConnectAsanaRetry =>
      'Error al conectar con Asana. Por favor, inténtalo de nuevo.';

  @override
  String get successfullyConnectedGoogleTasks =>
      '¡Conectado correctamente a Google Tasks!';

  @override
  String get failedToConnectGoogleTasksRetry =>
      'Error al conectar con Google Tasks. Por favor, inténtalo de nuevo.';

  @override
  String get successfullyConnectedClickUp =>
      '¡Conectado correctamente a ClickUp!';

  @override
  String get failedToConnectClickUpRetry =>
      'Error al conectar con ClickUp. Por favor, inténtalo de nuevo.';

  @override
  String get successfullyConnectedNotion =>
      '¡Conectado correctamente a Notion!';

  @override
  String get failedToRefreshNotionStatus =>
      'Error al actualizar el estado de conexión de Notion.';

  @override
  String get successfullyConnectedGoogle =>
      '¡Conectado correctamente a Google!';

  @override
  String get failedToRefreshGoogleStatus =>
      'Error al actualizar el estado de conexión de Google.';

  @override
  String get successfullyConnectedWhoop => '¡Conectado correctamente a Whoop!';

  @override
  String get failedToRefreshWhoopStatus =>
      'Error al actualizar el estado de conexión de Whoop.';

  @override
  String get successfullyConnectedGitHub =>
      '¡Conectado correctamente a GitHub!';

  @override
  String get failedToRefreshGitHubStatus =>
      'Error al actualizar el estado de conexión de GitHub.';

  @override
  String get authFailedToSignInWithGoogle =>
      'Error al iniciar sesión con Google, por favor inténtalo de nuevo.';

  @override
  String get authenticationFailed =>
      'La autenticación falló. Por favor, inténtalo de nuevo.';

  @override
  String get authFailedToSignInWithApple =>
      'Error al iniciar sesión con Apple, por favor inténtalo de nuevo.';

  @override
  String get authFailedToRetrieveToken =>
      'Error al recuperar el token de Firebase, por favor inténtalo de nuevo.';

  @override
  String get authUnexpectedErrorFirebase =>
      'Error inesperado al iniciar sesión, error de Firebase, por favor inténtalo de nuevo.';

  @override
  String get authUnexpectedError =>
      'Error inesperado al iniciar sesión, por favor inténtalo de nuevo';

  @override
  String get authFailedToLinkGoogle =>
      'Error al vincular con Google, por favor inténtalo de nuevo.';

  @override
  String get authFailedToLinkApple =>
      'Error al vincular con Apple, por favor inténtalo de nuevo.';

  @override
  String get onboardingBluetoothRequired =>
      'Se requiere permiso de Bluetooth para conectarse a su dispositivo.';

  @override
  String get onboardingBluetoothDeniedSystemPrefs =>
      'Permiso de Bluetooth denegado. Por favor, conceda el permiso en Preferencias del Sistema.';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'Estado del permiso de Bluetooth: $status. Por favor, compruebe Preferencias del Sistema.';
  }

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'Error al comprobar el permiso de Bluetooth: $error';
  }

  @override
  String get onboardingNotificationDeniedSystemPrefs =>
      'Permiso de notificaciones denegado. Por favor, conceda el permiso en Preferencias del Sistema.';

  @override
  String get onboardingNotificationDeniedNotifications =>
      'Permiso de notificaciones denegado. Por favor, conceda el permiso en Preferencias del Sistema > Notificaciones.';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return 'Estado del permiso de notificaciones: $status. Por favor, compruebe Preferencias del Sistema.';
  }

  @override
  String onboardingFailedCheckNotification(String error) {
    return 'Error al comprobar el permiso de notificaciones: $error';
  }

  @override
  String get onboardingLocationGrantInSettings =>
      'Por favor, conceda permiso de ubicación en Ajustes > Privacidad y Seguridad > Servicios de ubicación';

  @override
  String get onboardingMicrophoneRequired =>
      'Se requiere permiso de micrófono para grabar.';

  @override
  String get onboardingMicrophoneDenied =>
      'Permiso de micrófono denegado. Por favor, conceda el permiso en Preferencias del Sistema > Privacidad y Seguridad > Micrófono.';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'Estado del permiso de micrófono: $status. Por favor, compruebe Preferencias del Sistema.';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'Error al comprobar el permiso de micrófono: $error';
  }

  @override
  String get onboardingScreenCaptureRequired =>
      'Se requiere permiso de captura de pantalla para grabar audio del sistema.';

  @override
  String get onboardingScreenCaptureDenied =>
      'Permiso de captura de pantalla denegado. Por favor, conceda el permiso en Preferencias del Sistema > Privacidad y Seguridad > Grabación de pantalla.';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return 'Estado del permiso de captura de pantalla: $status. Por favor, compruebe Preferencias del Sistema.';
  }

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return 'Error al comprobar el permiso de captura de pantalla: $error';
  }

  @override
  String get onboardingAccessibilityRequired =>
      'Se requiere permiso de accesibilidad para detectar reuniones del navegador.';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'Estado del permiso de accesibilidad: $status. Por favor, compruebe Preferencias del Sistema.';
  }

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'Error al comprobar el permiso de accesibilidad: $error';
  }

  @override
  String get msgCameraNotAvailable =>
      'La captura de cámara no está disponible en esta plataforma';

  @override
  String get msgCameraPermissionDenied =>
      'Permiso de cámara denegado. Por favor, permita el acceso a la cámara';

  @override
  String msgCameraAccessError(String error) {
    return 'Error al acceder a la cámara: $error';
  }

  @override
  String get msgPhotoError =>
      'Error al tomar la foto. Por favor, inténtelo de nuevo.';

  @override
  String get msgMaxImagesLimit => 'Solo puede seleccionar hasta 4 imágenes';

  @override
  String msgFilePickerError(String error) {
    return 'Error al abrir el selector de archivos: $error';
  }

  @override
  String msgSelectImagesError(String error) {
    return 'Error al seleccionar imágenes: $error';
  }

  @override
  String get msgPhotosPermissionDenied =>
      'Permiso de fotos denegado. Por favor, permita el acceso a las fotos para seleccionar imágenes';

  @override
  String get msgSelectImagesGenericError =>
      'Error al seleccionar imágenes. Por favor, inténtelo de nuevo.';

  @override
  String get msgMaxFilesLimit => 'Solo puede seleccionar hasta 4 archivos';

  @override
  String msgSelectFilesError(String error) {
    return 'Error al seleccionar archivos: $error';
  }

  @override
  String get msgSelectFilesGenericError =>
      'Error al seleccionar archivos. Por favor, inténtelo de nuevo.';

  @override
  String get msgUploadFileFailed =>
      'Error al subir el archivo, por favor inténtelo más tarde';

  @override
  String get msgReadingMemories => 'Leyendo tus recuerdos...';

  @override
  String get msgLearningMemories => 'Aprendiendo de tus recuerdos...';

  @override
  String get msgUploadAttachedFileFailed =>
      'Error al subir el archivo adjunto.';

  @override
  String captureRecordingError(String error) {
    return 'Ocurrió un error durante la grabación: $error';
  }

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return 'Grabación detenida: $reason. Es posible que necesite reconectar las pantallas externas o reiniciar la grabación.';
  }

  @override
  String get captureMicrophonePermissionRequired =>
      'Se requiere permiso de micrófono';

  @override
  String get captureMicrophonePermissionInSystemPreferences =>
      'Conceda permiso de micrófono en Preferencias del Sistema';

  @override
  String get captureScreenRecordingPermissionRequired =>
      'Se requiere permiso de grabación de pantalla';

  @override
  String get captureDisplayDetectionFailed =>
      'Error en la detección de pantalla. Grabación detenida.';

  @override
  String get devModeInvalidAudioBytesWebhookUrl =>
      'URL de webhook de bytes de audio no válida';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl =>
      'URL de webhook de transcripción en tiempo real no válida';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl =>
      'URL de webhook de conversación creada no válida';

  @override
  String get devModeInvalidDaySummaryWebhookUrl =>
      'URL de webhook de resumen diario no válida';

  @override
  String get devModeSettingsSaved => '¡Configuración guardada!';

  @override
  String get voiceFailedToTranscribe => 'Error al transcribir el audio';

  @override
  String get locationPermissionRequired => 'Permiso de ubicación requerido';

  @override
  String get locationPermissionContent =>
      'La transferencia rápida requiere permiso de ubicación para verificar la conexión WiFi. Por favor, conceda el permiso de ubicación para continuar.';

  @override
  String get pdfTranscriptExport => 'Exportar transcripción';

  @override
  String get pdfConversationExport => 'Exportar conversación';

  @override
  String pdfTitleLabel(String title) {
    return 'Título: $title';
  }

  @override
  String get conversationNewIndicator => 'Nuevo 🚀';

  @override
  String conversationPhotosCount(int count) {
    return '$count fotos';
  }

  @override
  String get mergingStatus => 'Fusionando...';

  @override
  String timeSecsSingular(int count) {
    return '$count seg';
  }

  @override
  String timeSecsPlural(int count) {
    return '$count segs';
  }

  @override
  String timeMinSingular(int count) {
    return '$count min';
  }

  @override
  String timeMinsPlural(int count) {
    return '$count mins';
  }

  @override
  String timeMinsAndSecs(int mins, int secs) {
    return '$mins mins $secs segs';
  }

  @override
  String timeHourSingular(int count) {
    return '$count hora';
  }

  @override
  String timeHoursPlural(int count) {
    return '$count horas';
  }

  @override
  String timeHoursAndMins(int hours, int mins) {
    return '$hours horas $mins mins';
  }

  @override
  String timeDaySingular(int count) {
    return '$count día';
  }

  @override
  String timeDaysPlural(int count) {
    return '$count días';
  }

  @override
  String timeDaysAndHours(int days, int hours) {
    return '$days días $hours horas';
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
  String get moveToFolder => 'Mover a carpeta';

  @override
  String get noFoldersAvailable => 'No hay carpetas disponibles';

  @override
  String get newFolder => 'Nueva carpeta';

  @override
  String get color => 'Color';

  @override
  String get waitingForDevice => 'Esperando dispositivo...';

  @override
  String get saySomething => 'Di algo...';

  @override
  String get initialisingSystemAudio => 'Inicializando audio del sistema';

  @override
  String get stopRecording => 'Detener grabación';

  @override
  String get continueRecording => 'Continuar grabación';

  @override
  String get initialisingRecorder => 'Inicializando grabadora';

  @override
  String get pauseRecording => 'Pausar grabación';

  @override
  String get resumeRecording => 'Reanudar grabación';

  @override
  String get noDailyRecapsYet => 'Aún no hay resúmenes diarios';

  @override
  String get dailyRecapsDescription =>
      'Tus resúmenes diarios aparecerán aquí una vez generados';

  @override
  String get chooseTransferMethod => 'Elegir método de transferencia';

  @override
  String get fastTransferSpeed => '~150 KB/s vía WiFi';

  @override
  String largeTimeGapDetected(String gap) {
    return 'Se detectó una brecha de tiempo grande ($gap)';
  }

  @override
  String largeTimeGapsDetected(String gaps) {
    return 'Se detectaron brechas de tiempo grandes ($gaps)';
  }

  @override
  String get deviceDoesNotSupportWifiSwitchingToBle =>
      'El dispositivo no admite sincronización WiFi, cambiando a Bluetooth';

  @override
  String get appleHealthNotAvailable =>
      'Apple Health no está disponible en este dispositivo';

  @override
  String get downloadAudio => 'Descargar audio';

  @override
  String get audioDownloadSuccess => 'Audio descargado correctamente';

  @override
  String get audioDownloadFailed => 'Error al descargar el audio';

  @override
  String get downloadingAudio => 'Descargando audio...';

  @override
  String get shareAudio => 'Compartir audio';

  @override
  String get preparingAudio => 'Preparando audio';

  @override
  String get gettingAudioFiles => 'Obteniendo archivos de audio...';

  @override
  String get downloadingAudioProgress => 'Descargando audio';

  @override
  String get processingAudio => 'Procesando audio';

  @override
  String get combiningAudioFiles => 'Combinando archivos de audio...';

  @override
  String get audioReady => 'Audio listo';

  @override
  String get openingShareSheet => 'Abriendo hoja de compartir...';

  @override
  String get audioShareFailed => 'Error al compartir';

  @override
  String get dailyRecaps => 'Resúmenes Diarios';

  @override
  String get removeFilter => 'Eliminar Filtro';

  @override
  String get categoryConversationAnalysis => 'Análisis de conversaciones';

  @override
  String get categoryPersonalityClone => 'Clon de personalidad';

  @override
  String get categoryHealth => 'Salud';

  @override
  String get categoryEducation => 'Educación';

  @override
  String get categoryCommunication => 'Comunicación';

  @override
  String get categoryEmotionalSupport => 'Apoyo emocional';

  @override
  String get categoryProductivity => 'Productividad';

  @override
  String get categoryEntertainment => 'Entretenimiento';

  @override
  String get categoryFinancial => 'Finanzas';

  @override
  String get categoryTravel => 'Viajes';

  @override
  String get categorySafety => 'Seguridad';

  @override
  String get categoryShopping => 'Compras';

  @override
  String get categorySocial => 'Social';

  @override
  String get categoryNews => 'Noticias';

  @override
  String get categoryUtilities => 'Utilidades';

  @override
  String get categoryOther => 'Otros';

  @override
  String get capabilityChat => 'Chat';

  @override
  String get capabilityConversations => 'Conversaciones';

  @override
  String get capabilityExternalIntegration => 'Integración externa';

  @override
  String get capabilityNotification => 'Notificación';

  @override
  String get triggerAudioBytes => 'Bytes de audio';

  @override
  String get triggerConversationCreation => 'Creación de conversación';

  @override
  String get triggerTranscriptProcessed => 'Transcripción procesada';

  @override
  String get actionCreateConversations => 'Crear conversaciones';

  @override
  String get actionCreateMemories => 'Crear recuerdos';

  @override
  String get actionReadConversations => 'Leer conversaciones';

  @override
  String get actionReadMemories => 'Leer recuerdos';

  @override
  String get actionReadTasks => 'Leer tareas';

  @override
  String get scopeUserName => 'Nombre de usuario';

  @override
  String get scopeUserFacts => 'Datos del usuario';

  @override
  String get scopeUserConversations => 'Conversaciones del usuario';

  @override
  String get scopeUserChat => 'Chat del usuario';

  @override
  String get capabilitySummary => 'Resumen';

  @override
  String get capabilityFeatured => 'Destacados';

  @override
  String get capabilityTasks => 'Tareas';

  @override
  String get capabilityIntegrations => 'Integraciones';

  @override
  String get categoryPersonalityClones => 'Clones de personalidad';

  @override
  String get categoryProductivityLifestyle => 'Productividad y estilo de vida';

  @override
  String get categorySocialEntertainment => 'Social y entretenimiento';

  @override
  String get categoryProductivityTools => 'Herramientas de productividad';

  @override
  String get categoryPersonalWellness => 'Bienestar personal';

  @override
  String get rating => 'Valoración';

  @override
  String get categories => 'Categorías';

  @override
  String get sortBy => 'Ordenar';

  @override
  String get highestRating => 'Mayor valoración';

  @override
  String get lowestRating => 'Menor valoración';

  @override
  String get resetFilters => 'Restablecer filtros';

  @override
  String get applyFilters => 'Aplicar filtros';

  @override
  String get mostInstalls => 'Más instalaciones';

  @override
  String get couldNotOpenUrl =>
      'No se pudo abrir la URL. Por favor, inténtalo de nuevo.';

  @override
  String get newTask => 'Nueva tarea';

  @override
  String get viewAll => 'Ver todo';

  @override
  String get addTask => 'Añadir tarea';

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
  String get audioPlaybackUnavailable =>
      'El archivo de audio no está disponible para reproducción';

  @override
  String get audioPlaybackFailed =>
      'No se puede reproducir el audio. El archivo puede estar dañado o no existir.';

  @override
  String get connectionGuide => 'Guía de conexión';

  @override
  String get iveDoneThis => 'Ya lo hice';

  @override
  String get pairNewDevice => 'Emparejar nuevo dispositivo';

  @override
  String get dontSeeYourDevice => '¿No ves tu dispositivo?';

  @override
  String get reportAnIssue => 'Reportar un problema';

  @override
  String get pairingTitleOmi => 'Enciende Omi';

  @override
  String get pairingDescOmi =>
      'Mantén presionado el dispositivo hasta que vibre para encenderlo.';

  @override
  String get pairingTitleOmiDevkit =>
      'Pon Omi DevKit en modo de emparejamiento';

  @override
  String get pairingDescOmiDevkit =>
      'Presiona el botón una vez para encender. El LED parpadeará en púrpura en modo de emparejamiento.';

  @override
  String get pairingTitleOmiGlass => 'Enciende Omi Glass';

  @override
  String get pairingDescOmiGlass =>
      'Mantén presionado el botón lateral durante 3 segundos para encender.';

  @override
  String get pairingTitlePlaudNote =>
      'Pon Plaud Note en modo de emparejamiento';

  @override
  String get pairingDescPlaudNote =>
      'Mantén presionado el botón lateral durante 2 segundos. El LED rojo parpadeará cuando esté listo para emparejar.';

  @override
  String get pairingTitleBee => 'Pon Bee en modo de emparejamiento';

  @override
  String get pairingDescBee =>
      'Presiona el botón 5 veces seguidas. La luz comenzará a parpadear en azul y verde.';

  @override
  String get pairingTitleLimitless => 'Pon Limitless en modo de emparejamiento';

  @override
  String get pairingDescLimitless =>
      'Cuando cualquier luz sea visible, presiona una vez y luego mantén presionado hasta que el dispositivo muestre una luz rosa, luego suelta.';

  @override
  String get pairingTitleFriendPendant =>
      'Pon Friend Pendant en modo de emparejamiento';

  @override
  String get pairingDescFriendPendant =>
      'Presiona el botón del colgante para encenderlo. Entrará en modo de emparejamiento automáticamente.';

  @override
  String get pairingTitleFieldy => 'Pon Fieldy en modo de emparejamiento';

  @override
  String get pairingDescFieldy =>
      'Mantén presionado el dispositivo hasta que aparezca la luz para encenderlo.';

  @override
  String get pairingTitleAppleWatch => 'Conectar Apple Watch';

  @override
  String get pairingDescAppleWatch =>
      'Instala y abre la aplicación Omi en tu Apple Watch, luego toca Conectar en la aplicación.';

  @override
  String get pairingTitleNeoOne => 'Pon Neo One en modo de emparejamiento';

  @override
  String get pairingDescNeoOne =>
      'Mantén presionado el botón de encendido hasta que el LED parpadee. El dispositivo será visible.';

  @override
  String whatsNewInVersion(String version) {
    return 'Novedades en $version';
  }

  @override
  String get addToYourTaskList => '¿Agregar a tu lista de tareas?';

  @override
  String get failedToCreateShareLink =>
      'Error al crear el enlace para compartir';

  @override
  String get deleteGoal => 'Eliminar objetivo';

  @override
  String get deviceUpToDate => 'Su dispositivo está actualizado';

  @override
  String get wifiConfiguration => 'Configuración WiFi';

  @override
  String get wifiConfigurationSubtitle =>
      'Ingrese sus credenciales WiFi para permitir que el dispositivo descargue el firmware.';

  @override
  String get networkNameSsid => 'Nombre de red (SSID)';

  @override
  String get enterWifiNetworkName => 'Ingrese el nombre de la red WiFi';

  @override
  String get enterWifiPassword => 'Ingrese la contraseña WiFi';
}
