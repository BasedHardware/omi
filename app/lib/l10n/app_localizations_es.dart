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
  String get deleteConversationMessage => '¿Seguro que quieres borrar esta conversación? Esta acción no se puede deshacer.';

  @override
  String get confirm => 'Confirmar';

  @override
  String get cancel => 'Cancelar';

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
  String get conversationUrlNotShared => 'La URL de la conversación no se compartió.';

  @override
  String get errorProcessingConversation => 'Error al procesar la conversación. Inténtalo de nuevo más tarde.';

  @override
  String get noInternetConnection => 'Sin conexión a Internet';

  @override
  String get unableToDeleteConversation => 'No se pudo borrar la conversación';

  @override
  String get somethingWentWrong => '¡Algo salió mal! Por favor, inténtalo de nuevo más tarde.';

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
  String get createPersonHint => '¡Crea una nueva persona y entrena a Omi para reconocer su voz!';

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
  String get pleaseCompleteAuthentication => 'Por favor completa la autenticación en tu navegador. Regresa a la app cuando termines.';

  @override
  String get failedToStartAuthentication => 'Error al iniciar autenticación';

  @override
  String get importStarted => '¡Importación iniciada! Se te notificará cuando termine.';

  @override
  String get failedToStartImport => 'No se pudo iniciar la importación. Por favor intenta de nuevo.';

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
  String get pendantNotConnected => 'Pendant no conectado. Conecta para sincronizar.';

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
  String get starConversationHint => 'Para marcar una conversación como favorita, ábrela y toca la estrella en la cabecera.';

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
  String get mergingInBackground => 'Fusionando en segundo plano. Esto puede tardar un momento.';

  @override
  String get failedToStartMerge => 'Error al iniciar fusión';

  @override
  String get askAnything => 'Pregunta cualquier cosa';

  @override
  String get noMessagesYet => '¡No hay mensajes!\n¿Por qué no inicias una conversación?';

  @override
  String get deletingMessages => 'Eliminando tus mensajes de la memoria de Omi...';

  @override
  String get messageCopied => '✨ Mensaje copiado al portapapeles';

  @override
  String get cannotReportOwnMessage => 'No puedes reportar tus propios mensajes.';

  @override
  String get reportMessage => 'Reportar mensaje';

  @override
  String get reportMessageConfirm => '¿Seguro que quieres reportar este mensaje?';

  @override
  String get messageReported => 'Mensaje reportado exitosamente.';

  @override
  String get thankYouFeedback => '¡Gracias por tus comentarios!';

  @override
  String get clearChat => '¿Limpiar chat?';

  @override
  String get clearChatConfirm => '¿Seguro que quieres limpiar el chat? Esta acción no se puede deshacer.';

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
  String get createYourOwnApp => 'Crea tu propia App';

  @override
  String get buildAndShareApp => 'Construye y comparte tu propia app';

  @override
  String get searchApps => 'Buscar aplicaciones...';

  @override
  String get myApps => 'Mis aplicaciones';

  @override
  String get installedApps => 'Aplicaciones instaladas';

  @override
  String get unableToFetchApps => 'No se pudieron cargar las apps :(\n\nRevisa tu conexión a internet.';

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
  String get allDataErased => 'Todos tus recuerdos y conversaciones se borrarán permanentemente.';

  @override
  String get appsDisconnected => 'Tus apps e integraciones se desconectarán inmediatamente.';

  @override
  String get exportBeforeDelete => 'Puedes exportar tus datos antes de borrar tu cuenta. Una vez borrados, no se pueden recuperar.';

  @override
  String get deleteAccountCheckbox => 'Entiendo que borrar mi cuenta es permanente y que todos los datos, incluyendo recuerdos y conversaciones, se perderán para siempre.';

  @override
  String get areYouSure => '¿Estás seguro?';

  @override
  String get deleteAccountFinal => 'Esta acción es irreversible y borrará permanentemente tu cuenta y todos sus datos. ¿Deseas continuar?';

  @override
  String get deleteNow => 'Borrar ahora';

  @override
  String get goBack => 'Volver';

  @override
  String get checkBoxToConfirm => 'Marca la casilla para confirmar que entiendes que borrar tu cuenta es permanente e irreversible.';

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
  String get offlineSync => 'Sincronización offline';

  @override
  String get deviceSettings => 'Ajustes del dispositivo';

  @override
  String get chatTools => 'Herramientas de chat';

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
  String get privacyIntro => 'En Omi, nos comprometemos a proteger tu privacidad. Esta página te permite controlar cómo se guardan y usan tus datos.';

  @override
  String get learnMore => 'Saber más...';

  @override
  String get dataProtectionLevel => 'Nivel de protección de datos';

  @override
  String get dataProtectionDesc => 'Tus datos están protegidos por encriptación fuerte por defecto.';

  @override
  String get appAccess => 'Acceso de apps';

  @override
  String get appAccessDesc => 'Las siguientes apps pueden acceder a tus datos. Toca una app para gestionar sus permisos.';

  @override
  String get noAppsExternalAccess => 'Ninguna app instalada tiene acceso externo a tus datos.';

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
  String get deviceUnpairedMessage => 'Dispositivo desvinculado. Ve a Configuración > Bluetooth y olvida el dispositivo para completar la desvinculación.';

  @override
  String get unpairDialogTitle => 'Desvincular dispositivo';

  @override
  String get unpairDialogMessage => 'Esto desvinculará el dispositivo para que pueda usarse en otro teléfono. Debes ir a Ajustes > Bluetooth y olvidar el dispositivo para completar el proceso.';

  @override
  String get deviceNotConnected => 'Dispositivo no conectado';

  @override
  String get connectDeviceMessage => 'Conecta tu dispositivo Omi para acceder a los ajustes.';

  @override
  String get deviceInfoSection => 'Información del dispositivo';

  @override
  String get customizationSection => 'Personalización';

  @override
  String get hardwareSection => 'Hardware';

  @override
  String get v2Undetected => 'V2 no detectado';

  @override
  String get v2UndetectedMessage => 'Parece que tienes un dispositivo V1 o no está conectado. La funcionalidad de tarjeta SD es solo para dispositivos V2.';

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
  String get off => 'Apagado';

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
  String get conversationTimeoutConfig => 'Define cuándo terminan las conversaciones automáticamente';

  @override
  String get importData => 'Importar datos';

  @override
  String get importDataConfig => 'Importar datos de otras fuentes';

  @override
  String get debugDiagnostics => 'Depuración y Diagnóstico';

  @override
  String get endpointUrl => 'URL del punto final';

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
  String get startConversationToSeeInsights => 'Inicia una conversación con Omi\npara ver tus insights aquí.';

  @override
  String get listening => 'Escuchando';

  @override
  String get listeningSubtitle => 'Tiempo total que Omi ha escuchado activamente.';

  @override
  String get understanding => 'Entendiendo';

  @override
  String get understandingSubtitle => 'Palabras entendidas de tus conversaciones.';

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
  String get shareStatsMessage => '¡Compartiendo mis estadísticas de Omi! (omi.me - mi asistente IA siempre activo)';

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
  String get exportStarted => 'Exportación iniciada. Puede tardar unos segundos...';

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
  String get deleteKnowledgeGraphMessage => 'Esto borrará todos los datos derivados del gráfico (nodos y conexiones). Tus recuerdos originales se mantienen seguros.';

  @override
  String get knowledgeGraphDeleted => 'Gráfico de conocimiento eliminado';

  @override
  String deleteGraphFailed(String error) {
    return 'Error al borrar el gráfico: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'Borrar gráfico de conocimiento';

  @override
  String get deleteKnowledgeGraphDesc => 'Eliminar todos los nodos y conexiones';

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
  String get visibilitySubtitle => 'Controla qué conversaciones aparecen en tu lista';

  @override
  String get showShortConversations => 'Mostrar conversaciones cortas';

  @override
  String get showShortConversationsDesc => 'Mostrar conversaciones más cortas que el umbral';

  @override
  String get showDiscardedConversations => 'Mostrar conversaciones descartadas';

  @override
  String get showDiscardedConversationsDesc => 'Incluir conversaciones marcadas como descartadas';

  @override
  String get shortConversationThreshold => 'Umbral de conversación corta';

  @override
  String get shortConversationThresholdSubtitle => 'Conversaciones más cortas que esto se ocultan si no está activado arriba';

  @override
  String get durationThreshold => 'Umbral de duración';

  @override
  String get durationThresholdDesc => 'Ocultar conversaciones más cortas que esto';

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
  String get connect => 'Conectar';

  @override
  String get comingSoon => 'Próximamente';

  @override
  String get chatToolsFooter => 'Conecta tus apps para ver datos y métricas en el chat.';

  @override
  String get completeAuthInBrowser => 'Por favor completa la autenticación en tu navegador.';

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
  String get alreadyGavePermission => 'Ya nos diste permiso para guardar tus grabaciones. Aquí un recordatorio de por qué lo necesitamos:';

  @override
  String get wouldLikePermission => 'Nos gustaría tu permiso para guardar tus grabaciones de voz. Aquí está la razón:';

  @override
  String get improveSpeechProfile => 'Mejorar tu perfil de voz';

  @override
  String get improveSpeechProfileDesc => 'Usamos grabaciones para entrenar y mejorar tu perfil personal de voz.';

  @override
  String get trainFamilyProfiles => 'Entrenar perfiles de amigos y familia';

  @override
  String get trainFamilyProfilesDesc => 'Tus grabaciones ayudan a reconocer y crear perfiles para tus amigos y familiares.';

  @override
  String get enhanceTranscriptAccuracy => 'Mejorar precisión de transcripción';

  @override
  String get enhanceTranscriptAccuracyDesc => 'A medida que nuestro modelo mejora, podemos ofrecer mejores transcripciones.';

  @override
  String get legalNotice => 'Aviso legal: La legalidad de grabar puede variar según tu ubicación.';

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
  String get permissionRevokedMessage => '¿Quieres que borremos todas tus grabaciones existentes también?';

  @override
  String get yes => 'Sí';

  @override
  String get editName => 'Editar nombre';

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
  String get showMeetingsMenuBarDesc => 'Mostrar tu próxima reunión y tiempo restante en la barra de menú de macOS';

  @override
  String get showEventsNoParticipants => 'Mostrar eventos sin participantes';

  @override
  String get showEventsNoParticipantsDesc => 'Si activado, \'Próximamente\' mostrará eventos sin participantes o enlaces de video.';

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
  String get googleCalendarComingSoon => '¡Integración con Google Calendar pronto!';

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
  String get leaveUnselectedTasks => 'Dejar sin seleccionar para tareas sin proyecto';

  @override
  String get noProjectsInWorkspace => 'No se encontraron proyectos en este espacio';

  @override
  String get conversationTimeoutDesc => 'Elige cuánto tiempo esperar en silencio antes de terminar:';

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
  String get conversationEndAfterHours => 'Las conversaciones terminan tras 4 horas de silencio';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Las conversaciones terminan tras $minutes minuto(s) de silencio';
  }

  @override
  String get tellUsPrimaryLanguage => 'Dinos tu idioma principal';

  @override
  String get languageForTranscription => 'Configura tu idioma para transcripciones más precisas.';

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
  String get failedToSaveDefaultRepo => 'Error al guardar repositorio por defecto';

  @override
  String get defaultRepository => 'Repositorio por defecto';

  @override
  String get selectDefaultRepoDesc => 'Elige un repo por defecto para crear issues.';

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
  String get issuesCreatedInRepo => 'Los issues se crearán en tu repo por defecto';

  @override
  String get taskIntegrations => 'Integraciones de tareas';

  @override
  String get configureSettings => 'Configurar ajustes';

  @override
  String get completeAuthBrowser => 'Por favor completa la autenticación en tu navegador. Al terminar, vuelve a la app.';

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
  String get tasksExportedOneApp => 'Las tareas solo se pueden exportar a una app a la vez.';

  @override
  String get completeYourUpgrade => 'Completa tu mejora';

  @override
  String get importConfiguration => 'Importar configuración';

  @override
  String get exportConfiguration => 'Exportar configuración';

  @override
  String get bringYourOwn => 'Trae el tuyo';

  @override
  String get payYourSttProvider => 'Usa Omi gratis. Solo pagas a tu proveedor STT.';

  @override
  String get freeMinutesMonth => '1.200 minutos gratis/mes incluidos.';

  @override
  String get omiUnlimited => 'Omi Ilimitado';

  @override
  String get hostRequired => 'Host es requerido';

  @override
  String get validPortRequired => 'Puerto válido requerido';

  @override
  String get validWebsocketUrlRequired => 'URL WebSocket válida requerida (wss://)';

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
  String get addApiKeyAfterImport => 'Debes añadir tu propia API key tras importar';

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
  String get storedLocallyNeverShared => 'Guardado localmente, nunca compartido';

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
  String deviceUsesCodec(String deviceName, String codecReason) {
    return '$deviceName usa $codecReason. Se usa Omi.';
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
  String get appName => 'Nombre de la App';

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
  String get tailoredConversationSummaries => 'Resúmenes de conversación a medida';

  @override
  String get customChatbotPersonality => 'Personalidad de chatbot personalizada';

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
  String get bluetoothNeeded => 'Omi necesita Bluetooth para conectar tu wearable.';

  @override
  String get contactSupport => '¿Contactar soporte?';

  @override
  String get connectLater => 'Conectar más tarde';

  @override
  String get grantPermissions => 'Conceder permisos';

  @override
  String get backgroundActivity => 'Actividad en segundo plano';

  @override
  String get backgroundActivityDesc => 'Deja que Omi corra en segundo plano para mejor estabilidad';

  @override
  String get locationAccess => 'Acceso a ubicación';

  @override
  String get locationAccessDesc => 'Habilita ubicación en segundo plano para la experiencia completa';

  @override
  String get notifications => 'Notificaciones';

  @override
  String get notificationsDesc => 'Habilita notificaciones para estar informado';

  @override
  String get locationServiceDisabled => 'Servicio de ubicación desactivado';

  @override
  String get locationServiceDisabledDesc => 'Por favor activa los servicios de ubicación';

  @override
  String get backgroundLocationDenied => 'Acceso a ubicación en segundo plano denegado';

  @override
  String get backgroundLocationDeniedDesc => 'Por favor permite \'Siempre\' en los ajustes de ubicación';

  @override
  String get lovingOmi => '¿Te gusta Omi?';

  @override
  String get leaveReviewIos => 'Ayúdanos a llegar a más gente dejando una reseña en la App Store.';

  @override
  String get leaveReviewAndroid => 'Ayúdanos a llegar a más gente dejando una reseña en Google Play.';

  @override
  String get rateOnAppStore => 'Calificar en App Store';

  @override
  String get rateOnGooglePlay => 'Calificar en Google Play';

  @override
  String get maybeLater => 'Quizás más tarde';

  @override
  String get speechProfileIntro => 'Omi necesita aprender tus objetivos y tu voz.';

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
  String get permissionsRequiredDesc => 'Esta app requiere permisos de Bluetooth y Ubicación.';

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
  String get personalGrowthJourney => 'Tu viaje de crecimiento personal con IA que escucha cada palabra tuya.';

  @override
  String get actionItemsTitle => 'Acciones';

  @override
  String get actionItemsDescription => 'Toca para editar • Mantén para seleccionar • Desliza para acciones';

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
  String get deleteActionItemMessage => '¿Está seguro de que desea eliminar este elemento de acción?';

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
  String get welcomeActionItemsDescription => 'Tu IA extrae tareas automáticamente.';

  @override
  String get autoExtractionFeature => 'Extraído automáticamente de conversaciones';

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
  String get clearMemoryMessage => '¿Seguro que quieres borrar la memoria de Omi? No se puede deshacer.';

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
  String get allMemoriesPrivateResult => 'Todos los recuerdos son ahora privados';

  @override
  String get allMemoriesPublicResult => 'Todos los recuerdos son ahora públicos';

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
  String get retry => 'Reintentar';

  @override
  String get createActionItem => 'Crear tarea';

  @override
  String get editActionItem => 'Editar tarea';

  @override
  String get actionItemDescriptionHint => '¿Qué hay que hacer?';

  @override
  String get actionItemDescriptionEmpty => 'La descripción no puede estar vacía.';

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
  String get deleteActionItemConfirmMessage => '¿Seguro que quieres borrar esta tarea?';

  @override
  String get appLanguage => 'Idioma de la App';

  @override
  String get appInterfaceSectionTitle => 'INTERFAZ DE LA APLICACIÓN';

  @override
  String get speechTranscriptionSectionTitle => 'VOZ Y TRANSCRIPCIÓN';

  @override
  String get languageSettingsHelperText => 'El idioma de la aplicación cambia los menús y botones. El idioma de voz afecta cómo se transcriben tus grabaciones.';

  @override
  String get translationNotice => 'Aviso de traducción';

  @override
  String get translationNoticeMessage => 'Omi traduce las conversaciones a tu idioma principal. Actualízalo en cualquier momento en Ajustes → Perfiles.';

  @override
  String get pleaseCheckInternetConnection => 'Por favor, verifica tu conexión a Internet e inténtalo de nuevo';

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
  String get conversationCannotBeMerged => 'Esta conversación no se puede fusionar (bloqueada o ya en proceso de fusión)';

  @override
  String get pleaseEnterFolderName => 'Por favor, introduce un nombre de carpeta';

  @override
  String get failedToCreateFolder => 'Error al crear la carpeta';

  @override
  String get failedToUpdateFolder => 'Error al actualizar la carpeta';

  @override
  String get folderName => 'Nombre de carpeta';

  @override
  String get descriptionOptional => 'Descripción (opcional)';

  @override
  String get failedToDeleteFolder => 'Error al eliminar la carpeta';

  @override
  String get editFolder => 'Editar carpeta';

  @override
  String get deleteFolder => 'Eliminar carpeta';

  @override
  String get transcriptCopiedToClipboard => 'Transcripción copiada al portapapeles';

  @override
  String get summaryCopiedToClipboard => 'Resumen copiado al portapapeles';

  @override
  String get conversationUrlCouldNotBeShared => 'No se pudo compartir la URL de la conversación.';

  @override
  String get urlCopiedToClipboard => 'URL copiada al portapapeles';

  @override
  String get exportTranscript => 'Exportar transcripción';

  @override
  String get exportSummary => 'Exportar resumen';

  @override
  String get exportButton => 'Exportar';

  @override
  String get actionItemsCopiedToClipboard => 'Elementos de acción copiados al portapapeles';

  @override
  String get summarize => 'Resumir';

  @override
  String get generateSummary => 'Generar resumen';

  @override
  String get conversationNotFoundOrDeleted => 'Conversación no encontrada o ha sido eliminada';

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
  String get firmwareUsbWarning => 'La conexión USB durante las actualizaciones puede dañar tu dispositivo.';

  @override
  String get firmwareBatteryAbove15 => 'Batería superior al 15%';

  @override
  String get firmwareEnsureBattery => 'Asegúrate de que tu dispositivo tiene un 15% de batería.';

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
  String get unpairDeviceDialogMessage => 'Esto desvinculará el dispositivo para que pueda conectarse a otro teléfono. Deberás ir a Configuración > Bluetooth y olvidar el dispositivo para completar el proceso.';

  @override
  String get unpair => 'Desvincular';

  @override
  String get unpairAndForgetDevice => 'Desvincular y olvidar dispositivo';

  @override
  String get unknownDevice => 'Dispositivo desconocido';

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
    return '$label copied';
  }

  @override
  String get noApiKeysYet => 'Aún no hay claves API. Crea una para integrar con tu aplicación.';

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
  String get debugAndDiagnostics => 'Depuración y Diagnóstico';

  @override
  String get autoDeletesAfter3Days => 'Se elimina automáticamente después de 3 días';

  @override
  String get helpsDiagnoseIssues => 'Ayuda a diagnosticar problemas';

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
  String get autoCreateWhenNameDetected => 'Auto-create when name detected';

  @override
  String get followUpQuestions => 'Preguntas de Seguimiento';

  @override
  String get suggestQuestionsAfterConversations => 'Sugerir preguntas después de las conversaciones';

  @override
  String get goalTracker => 'Rastreador de Objetivos';

  @override
  String get trackPersonalGoalsOnHomepage => 'Track your personal goals on homepage';

  @override
  String get dailyReflection => 'Reflexión Diaria';

  @override
  String get get9PmReminderToReflect => 'Get a 9 PM reminder to reflect on your day';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'La descripción del elemento de acción no puede estar vacía';

  @override
  String get saved => 'Guardado';

  @override
  String get overdue => 'Atrasado';

  @override
  String get failedToUpdateDueDate => 'Error al actualizar la fecha de vencimiento';

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
  String get sdCardSyncDescription => 'La sincronización de la tarjeta SD importará tus recuerdos de la tarjeta SD a la aplicación';

  @override
  String get checksForAudioFiles => 'Comprueba archivos de audio en la tarjeta SD';

  @override
  String get omiSyncsAudioFiles => 'Omi luego sincroniza los archivos de audio con el servidor';

  @override
  String get serverProcessesAudio => 'El servidor procesa los archivos de audio y crea recuerdos';

  @override
  String get youreAllSet => '¡Estás listo!';

  @override
  String get welcomeToOmiDescription => '¡Bienvenido a Omi! Tu compañero de IA está listo para ayudarte con conversaciones, tareas y más.';

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
  String get addGoal => 'Agregar objetivo';

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
  String get tapToAddGoal => 'Toca para agregar un objetivo';

  @override
  String welcomeBack(String name) {
    return 'Bienvenido de nuevo, $name';
  }

  @override
  String get yourConversations => 'Tus conversaciones';

  @override
  String get reviewAndManageConversations => 'Revisa y gestiona tus conversaciones capturadas';

  @override
  String get startCapturingConversations => 'Comienza a capturar conversaciones con tu dispositivo Omi para verlas aquí.';

  @override
  String get useMobileAppToCapture => 'Usa tu aplicación móvil para capturar audio';

  @override
  String get conversationsProcessedAutomatically => 'Las conversaciones se procesan automáticamente';

  @override
  String get getInsightsInstantly => 'Obtén información y resúmenes al instante';

  @override
  String get showAll => 'Mostrar todo →';

  @override
  String get noTasksForToday => 'No hay tareas para hoy.\\nPregúntale a Omi por más tareas o créalas manualmente.';

  @override
  String get dailyScore => 'PUNTUACIÓN DIARIA';

  @override
  String get dailyScoreDescription => 'Una puntuación para ayudarte a concentrarte mejor en la ejecución.';

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
  String get swipeTasksToIndent => 'Desliza tareas para sangrar, arrastra entre categorías';

  @override
  String get create => 'Crear';

  @override
  String get noTasksYet => 'Aún no hay tareas';

  @override
  String get tasksFromConversationsWillAppear => 'Las tareas de tus conversaciones aparecerán aquí.\nHaz clic en Crear para añadir una manualmente.';

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
  String get deleteActionItemConfirmation => '¿Estás seguro de que quieres eliminar esta tarea? Esta acción no se puede deshacer.';

  @override
  String get enterActionItemDescription => 'Ingresa la descripción de la tarea...';

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
  String get all => 'Todos';

  @override
  String get open => 'Abrir';

  @override
  String get install => 'Instalar';

  @override
  String get noAppsAvailable => 'No hay aplicaciones disponibles';

  @override
  String get unableToLoadApps => 'No se pueden cargar las aplicaciones';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'Intenta ajustar tus términos de búsqueda o filtros';

  @override
  String get checkBackLaterForNewApps => 'Vuelve más tarde para ver nuevas aplicaciones';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'Por favor, verifica tu conexión a Internet e inténtalo de nuevo';

  @override
  String get createNewApp => 'Crear nueva aplicación';

  @override
  String get buildSubmitCustomOmiApp => 'Construye y envía tu aplicación Omi personalizada';

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
  String get chatPromptPlaceholder => 'Eres una aplicación increíble, tu trabajo es responder a las consultas de los usuarios y hacerlos sentir bien...';

  @override
  String get conversationPrompt => 'Indicación de conversación';

  @override
  String get conversationPromptPlaceholder => 'Eres una aplicación increíble, se te dará una transcripción y resumen de una conversación...';

  @override
  String get notificationScopes => 'Ámbitos de notificación';

  @override
  String get appPrivacyAndTerms => 'Privacidad y términos de la aplicación';

  @override
  String get makeMyAppPublic => 'Hacer pública mi aplicación';

  @override
  String get submitAppTermsAgreement => 'Al enviar esta aplicación, acepto los Términos de Servicio y la Política de Privacidad de Omi AI';

  @override
  String get submitApp => 'Enviar aplicación';

  @override
  String get needHelpGettingStarted => '¿Necesitas ayuda para comenzar?';

  @override
  String get clickHereForAppBuildingGuides => 'Haz clic aquí para guías de creación de aplicaciones y documentación';

  @override
  String get submitAppQuestion => '¿Enviar aplicación?';

  @override
  String get submitAppPublicDescription => 'Tu aplicación será revisada y publicada. Puedes comenzar a usarla inmediatamente, ¡incluso durante la revisión!';

  @override
  String get submitAppPrivateDescription => 'Tu aplicación será revisada y estará disponible para ti de forma privada. Puedes comenzar a usarla inmediatamente, ¡incluso durante la revisión!';

  @override
  String get startEarning => '¡Comienza a ganar! 💰';

  @override
  String get connectStripeOrPayPal => 'Conecta Stripe o PayPal para recibir pagos por tu aplicación.';

  @override
  String get connectNow => 'Conectar ahora';

  @override
  String installsCount(String count) {
    return '$count+ instalaciones';
  }

  @override
  String get uninstallApp => 'Desinstalar aplicación';

  @override
  String get subscribe => 'Suscribirse';

  @override
  String get dataAccessNotice => 'Aviso de acceso a datos';

  @override
  String get dataAccessWarning => 'Esta aplicación accederá a sus datos. Omi AI no es responsable de cómo esta aplicación utiliza, modifica o elimina sus datos';

  @override
  String get installApp => 'Instalar aplicación';

  @override
  String get betaTesterNotice => 'Eres un probador beta de esta aplicación. Aún no es pública. Será pública una vez aprobada.';

  @override
  String get appUnderReviewOwner => 'Tu aplicación está en revisión y solo visible para ti. Será pública una vez aprobada.';

  @override
  String get appRejectedNotice => 'Tu aplicación ha sido rechazada. Por favor actualiza los detalles de la aplicación y vuelve a enviarla para revisión.';

  @override
  String get setupSteps => 'Pasos de configuración';

  @override
  String get setupInstructions => 'Instrucciones de configuración';

  @override
  String get integrationInstructions => 'Instrucciones de integración';

  @override
  String get preview => 'Vista previa';

  @override
  String get aboutTheApp => 'Acerca de la aplicación';

  @override
  String get aboutThePersona => 'Acerca de la persona';

  @override
  String get chatPersonality => 'Personalidad del chat';

  @override
  String get ratingsAndReviews => 'Calificaciones y reseñas';

  @override
  String get noRatings => 'sin calificaciones';

  @override
  String ratingsCount(String count) {
    return '$count+ calificaciones';
  }

  @override
  String get errorActivatingApp => 'Error al activar la aplicación';

  @override
  String get integrationSetupRequired => 'Si esta es una aplicación de integración, asegúrese de que la configuración esté completa.';

  @override
  String get installed => 'Instalado';

  @override
  String get appIdLabel => 'ID de la aplicación';

  @override
  String get appNameLabel => 'Nombre de la aplicación';

  @override
  String get appNamePlaceholder => 'Mi aplicación increíble';

  @override
  String get pleaseEnterAppName => 'Por favor, ingrese el nombre de la aplicación';

  @override
  String get categoryLabel => 'Categoría';

  @override
  String get selectCategory => 'Seleccionar categoría';

  @override
  String get descriptionLabel => 'Descripción';

  @override
  String get appDescriptionPlaceholder => 'Mi aplicación increíble es una aplicación genial que hace cosas asombrosas. ¡Es la mejor aplicación!';

  @override
  String get pleaseProvideValidDescription => 'Por favor, proporcione una descripción válida';

  @override
  String get appPricingLabel => 'Precio de la aplicación';

  @override
  String get noneSelected => 'Ninguna seleccionada';

  @override
  String get appIdCopiedToClipboard => 'ID de la aplicación copiado al portapapeles';

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
  String get noNotificationScopesAvailable => 'No hay ámbitos de notificación disponibles';

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
  String get startConversation => 'Comienza una conversación y deja que la magia comience';

  @override
  String get checkInternetConnection => 'Por favor, verifica tu conexión a Internet';

  @override
  String get wasThisHelpful => '¿Fue esto útil?';

  @override
  String get thankYouForFeedback => '¡Gracias por tus comentarios!';

  @override
  String get maxFilesUploadError => 'Solo puedes subir 4 archivos a la vez';

  @override
  String get attachedFiles => '📎 Archivos adjuntos';

  @override
  String get takePhoto => 'Tomar una foto';

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
  String get cannotReportOwnMessages => 'No puedes reportar tus propios mensajes';

  @override
  String get messageReportedSuccessfully => '✅ Mensaje reportado exitosamente';

  @override
  String get confirmReportMessage => '¿Estás seguro de que quieres reportar este mensaje?';

  @override
  String get selectChatAssistant => 'Seleccionar asistente de chat';

  @override
  String get enableMoreApps => 'Habilitar más aplicaciones';

  @override
  String get chatCleared => 'Chat borrado';

  @override
  String get clearChatTitle => '¿Borrar chat?';

  @override
  String get confirmClearChat => '¿Estás seguro de que quieres borrar el chat? Esta acción no se puede deshacer.';

  @override
  String get copy => 'Copiar';

  @override
  String get share => 'Compartir';

  @override
  String get report => 'Reportar';

  @override
  String get microphonePermissionRequired => 'Se requiere permiso de micrófono para la grabación de voz.';

  @override
  String get microphonePermissionDenied => 'Permiso de micrófono denegado. Por favor, conceda permiso en Preferencias del Sistema > Privacidad y Seguridad > Micrófono.';

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
  String get conversationUrlCouldNotBeGenerated => 'No se pudo generar la URL de la conversación.';

  @override
  String get failedToGenerateConversationLink => 'Error al generar el enlace de la conversación';

  @override
  String get failedToGenerateShareLink => 'Error al generar el enlace para compartir';

  @override
  String get reloadingConversations => 'Recargando conversaciones...';

  @override
  String get user => 'Usuario';

  @override
  String get starred => 'Destacados';

  @override
  String get date => 'Fecha';

  @override
  String get noResultsFound => 'No se encontraron resultados';

  @override
  String get tryAdjustingSearchTerms => 'Intenta ajustar tus términos de búsqueda';

  @override
  String get starConversationsToFindQuickly => 'Marca conversaciones con estrella para encontrarlas rápidamente aquí';

  @override
  String noConversationsOnDate(String date) {
    return 'No hay conversaciones el $date';
  }

  @override
  String get trySelectingDifferentDate => 'Intenta seleccionar una fecha diferente';

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
  String get getOmiDevice => 'Obtener dispositivo Omi';

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
  String get failedToSaveCheckConnection => 'Error al guardar. Por favor, verifica tu conexión.';

  @override
  String get createMemory => 'Crear memoria';

  @override
  String get deleteMemoryConfirmation => '¿Estás seguro de que deseas eliminar esta memoria? Esta acción no se puede deshacer.';

  @override
  String get makePrivate => 'Hacer privado';

  @override
  String get organizeAndControlMemories => 'Organiza y controla tus recuerdos';

  @override
  String get total => 'Total';

  @override
  String get makeAllMemoriesPrivate => 'Hacer todos los recuerdos privados';

  @override
  String get setAllMemoriesToPrivate => 'Establecer todos los recuerdos como privados';

  @override
  String get makeAllMemoriesPublic => 'Hacer todos los recuerdos públicos';

  @override
  String get setAllMemoriesToPublic => 'Establecer todos los recuerdos como públicos';

  @override
  String get permanentlyRemoveAllMemories => 'Eliminar permanentemente todos los recuerdos de Omi';

  @override
  String get allMemoriesAreNowPrivate => 'Todos los recuerdos son ahora privados';

  @override
  String get allMemoriesAreNowPublic => 'Todos los recuerdos son ahora públicos';

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
  String get secureAuthViaGoogleAccount => 'Autenticación segura vía cuenta de Google';

  @override
  String get whatWeCollect => 'Qué recopilamos';

  @override
  String get dataCollectionMessage => 'Al continuar, tus conversaciones, grabaciones e información personal se almacenarán de forma segura en nuestros servidores para proporcionar información impulsada por IA y habilitar todas las funciones de la aplicación.';

  @override
  String get dataProtection => 'Protección de datos';

  @override
  String get yourDataIsProtected => 'Tus datos están protegidos y regidos por nuestra ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'Por favor, seleccione su idioma principal';

  @override
  String get chooseYourLanguage => 'Elige tu idioma';

  @override
  String get selectPreferredLanguageForBestExperience => 'Seleccione su idioma preferido para la mejor experiencia Omi';

  @override
  String get searchLanguages => 'Buscar idiomas...';

  @override
  String get selectALanguage => 'Seleccione un idioma';

  @override
  String get tryDifferentSearchTerm => 'Pruebe con un término de búsqueda diferente';

  @override
  String get pleaseEnterYourName => 'Por favor, introduce tu nombre';

  @override
  String get nameMustBeAtLeast2Characters => 'El nombre debe tener al menos 2 caracteres';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed => 'Díganos cómo le gustaría que nos dirigiéramos a usted. Esto ayuda a personalizar su experiencia Omi.';

  @override
  String charactersCount(int count) {
    return '$count caracteres';
  }

  @override
  String get enableFeaturesForBestExperience => 'Active funciones para la mejor experiencia Omi en su dispositivo.';

  @override
  String get microphoneAccess => 'Acceso al micrófono';

  @override
  String get recordAudioConversations => 'Grabar conversaciones de audio';

  @override
  String get microphoneAccessDescription => 'Omi necesita acceso al micrófono para grabar sus conversaciones y proporcionar transcripciones.';

  @override
  String get screenRecording => 'Grabación de pantalla';

  @override
  String get captureSystemAudioFromMeetings => 'Capturar audio del sistema de reuniones';

  @override
  String get screenRecordingDescription => 'Omi necesita permiso de grabación de pantalla para capturar el audio del sistema de sus reuniones basadas en navegador.';

  @override
  String get accessibility => 'Accesibilidad';

  @override
  String get detectBrowserBasedMeetings => 'Detectar reuniones basadas en navegador';

  @override
  String get accessibilityDescription => 'Omi necesita permiso de accesibilidad para detectar cuándo se une a reuniones de Zoom, Meet o Teams en su navegador.';

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
  String get helpImproveOmiBySharing => 'Ayuda a mejorar Omi compartiendo datos de análisis anonimizados';

  @override
  String get deleteAccount => 'Eliminar Cuenta';

  @override
  String get deleteYourAccountAndAllData => 'Elimina tu cuenta y todos los datos';

  @override
  String get clearLogs => 'Borrar registros';

  @override
  String get debugLogsCleared => 'Registros de depuración borrados';

  @override
  String get exportConversations => 'Exportar conversaciones';

  @override
  String get exportAllConversationsToJson => 'Exporte todas sus conversaciones a un archivo JSON.';

  @override
  String get conversationsExportStarted => 'Exportación de conversaciones iniciada. Esto puede tardar unos segundos, por favor espere.';

  @override
  String get mcpDescription => 'Para conectar Omi con otras aplicaciones para leer, buscar y administrar sus recuerdos y conversaciones. Cree una clave para comenzar.';

  @override
  String get apiKeys => 'Claves API';

  @override
  String errorLabel(String error) {
    return 'Error: $error';
  }

  @override
  String get noApiKeysFound => 'No se encontraron claves API. Cree una para comenzar.';

  @override
  String get advancedSettings => 'Configuración avanzada';

  @override
  String get triggersWhenNewConversationCreated => 'Se activa cuando se crea una nueva conversación.';

  @override
  String get triggersWhenNewTranscriptReceived => 'Se activa cuando se recibe una nueva transcripción.';

  @override
  String get realtimeAudioBytes => 'Bytes de audio en tiempo real';

  @override
  String get triggersWhenAudioBytesReceived => 'Se activa cuando se reciben bytes de audio.';

  @override
  String get everyXSeconds => 'Cada x segundos';

  @override
  String get triggersWhenDaySummaryGenerated => 'Se activa cuando se genera el resumen del día.';

  @override
  String get tryLatestExperimentalFeatures => 'Pruebe las últimas funciones experimentales del equipo de Omi.';

  @override
  String get transcriptionServiceDiagnosticStatus => 'Estado de diagnóstico del servicio de transcripción';

  @override
  String get enableDetailedDiagnosticMessages => 'Habilitar mensajes de diagnóstico detallados del servicio de transcripción';

  @override
  String get autoCreateAndTagNewSpeakers => 'Crear y etiquetar automáticamente nuevos hablantes';

  @override
  String get automaticallyCreateNewPerson => 'Crear automáticamente una nueva persona cuando se detecta un nombre en la transcripción.';

  @override
  String get pilotFeatures => 'Funciones piloto';

  @override
  String get pilotFeaturesDescription => 'Estas funciones son pruebas y no se garantiza soporte.';

  @override
  String get suggestFollowUpQuestion => 'Sugerir pregunta de seguimiento';

  @override
  String get saveSettings => 'Guardar Configuración';

  @override
  String get syncingDeveloperSettings => 'Sincronizando configuración de desarrollador...';

  @override
  String get summary => 'Resumen';

  @override
  String get auto => 'Automático';

  @override
  String get noSummaryForApp => 'No hay resumen disponible para esta aplicación. Prueba otra aplicación para obtener mejores resultados.';

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
  String get conversationNoSummaryYet => 'Esta conversación aún no tiene un resumen.';

  @override
  String get chooseSummarizationApp => 'Elegir aplicación de resumen';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName establecida como aplicación de resumen predeterminada';
  }

  @override
  String get letOmiChooseAutomatically => 'Deja que Omi elija automáticamente la mejor aplicación';

  @override
  String get deleteConversationConfirmation => '¿Estás seguro de que quieres eliminar esta conversación? Esta acción no se puede deshacer.';

  @override
  String get conversationDeleted => 'Conversación eliminada';

  @override
  String get generatingLink => 'Generando enlace...';

  @override
  String get editConversation => 'Editar conversación';

  @override
  String get conversationLinkCopiedToClipboard => 'Enlace de la conversación copiado al portapapeles';

  @override
  String get conversationTranscriptCopiedToClipboard => 'Transcripción de la conversación copiada al portapapeles';

  @override
  String get editConversationDialogTitle => 'Editar conversación';

  @override
  String get changeTheConversationTitle => 'Cambiar el título de la conversación';

  @override
  String get conversationTitle => 'Título de la conversación';

  @override
  String get enterConversationTitle => 'Introduzca el título de la conversación...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'Título de la conversación actualizado correctamente';

  @override
  String get failedToUpdateConversationTitle => 'Error al actualizar el título de la conversación';

  @override
  String get errorUpdatingConversationTitle => 'Error al actualizar el título de la conversación';

  @override
  String get settingUp => 'Configurando...';

  @override
  String get startYourFirstRecording => 'Comienza tu primera grabación';

  @override
  String get preparingSystemAudioCapture => 'Preparando captura de audio del sistema';

  @override
  String get clickTheButtonToCaptureAudio => 'Haz clic en el botón para capturar audio para transcripciones en vivo, información de IA y guardado automático.';

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
  String get startRecordingToSeeTranscript => 'Inicia la grabación para ver la transcripción en vivo';

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
  String get clickPlayToResumeOrStop => 'Haz clic en reproducir para reanudar o detener para finalizar';

  @override
  String get settingUpSystemAudioCapture => 'Configurando captura de audio del sistema';

  @override
  String get capturingAudioAndGeneratingTranscript => 'Capturando audio y generando transcripción';

  @override
  String get clickToBeginRecordingSystemAudio => 'Haz clic para comenzar a grabar audio del sistema';

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
  String get dailySummary => 'Resumen Diario';

  @override
  String get developer => 'Desarrollador';

  @override
  String get about => 'Acerca de';

  @override
  String get selectTime => 'Seleccionar Hora';

  @override
  String get accountGroup => 'Cuenta';

  @override
  String get signOutQuestion => '¿Cerrar Sesión?';

  @override
  String get signOutConfirmation => '¿Estás seguro de que quieres cerrar sesión?';

  @override
  String get customVocabularyHeader => 'VOCABULARIO PERSONALIZADO';

  @override
  String get addWordsDescription => 'Agrega palabras que Omi debería reconocer durante la transcripción.';

  @override
  String get enterWordsHint => 'Introduce palabras (separadas por comas)';

  @override
  String get dailySummaryHeader => 'RESUMEN DIARIO';

  @override
  String get dailySummaryTitle => 'Resumen Diario';

  @override
  String get dailySummaryDescription => 'Obtén un resumen personalizado de tus conversaciones';

  @override
  String get deliveryTime => 'Hora de Entrega';

  @override
  String get deliveryTimeDescription => 'Cuándo recibir tu resumen diario';

  @override
  String get subscription => 'Suscripción';

  @override
  String get viewPlansAndUsage => 'Ver Planes y Uso';

  @override
  String get viewPlansDescription => 'Administra tu suscripción y consulta estadísticas de uso';

  @override
  String get addOrChangePaymentMethod => 'Agrega o cambia tu método de pago';

  @override
  String get displayOptions => 'Opciones de Visualización';

  @override
  String get showMeetingsInMenuBar => 'Mostrar Reuniones en la Barra de Menú';

  @override
  String get displayUpcomingMeetingsDescription => 'Mostrar las próximas reuniones en la barra de menú';

  @override
  String get showEventsWithoutParticipants => 'Mostrar Eventos sin Participantes';

  @override
  String get includePersonalEventsDescription => 'Incluir eventos personales sin asistentes';

  @override
  String get upcomingMeetings => 'PRÓXIMAS REUNIONES';

  @override
  String get checkingNext7Days => 'Verificando los próximos 7 días';

  @override
  String get shortcuts => 'Atajos';

  @override
  String get shortcutChangeInstruction => 'Haz clic en un atajo para cambiarlo. Presiona Escape para cancelar.';

  @override
  String get configurePersonaDescription => 'Configura tu personalidad de IA';

  @override
  String get configureSTTProvider => 'Configurar proveedor de STT';

  @override
  String get setConversationEndDescription => 'Establece cuándo finalizan automáticamente las conversaciones';

  @override
  String get importDataDescription => 'Importar datos de otras fuentes';

  @override
  String get exportConversationsDescription => 'Exportar conversaciones a JSON';

  @override
  String get exportingConversations => 'Exportando conversaciones...';

  @override
  String get clearNodesDescription => 'Borrar todos los nodos y conexiones';

  @override
  String get deleteKnowledgeGraphQuestion => '¿Eliminar Gráfico de Conocimiento?';

  @override
  String get deleteKnowledgeGraphWarning => 'Esto eliminará todos los datos del gráfico de conocimiento derivados. Tus recuerdos originales permanecen seguros.';

  @override
  String get connectOmiWithAI => 'Conecta Omi con asistentes de IA';

  @override
  String get noAPIKeys => 'No hay claves API. Crea una para comenzar.';

  @override
  String get autoCreateWhenDetected => 'Crear automáticamente cuando se detecte el nombre';

  @override
  String get trackPersonalGoals => 'Seguir objetivos personales en la página de inicio';

  @override
  String get dailyReflectionDescription => 'Recordatorio a las 9 PM para reflexionar sobre tu día';

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
  String get holdOnPreparingForm => 'Espera, estamos preparando el formulario para ti';

  @override
  String get bySubmittingYouAgreeToOmi => 'Al enviar, aceptas los ';

  @override
  String get termsAndPrivacyPolicy => 'Términos y Política de Privacidad';

  @override
  String get helpsDiagnoseIssuesAutoDeletes => 'Ayuda a diagnosticar problemas. Se elimina automáticamente después de 3 días.';

  @override
  String get manageYourApp => 'Gestiona tu aplicación';

  @override
  String get updatingYourApp => 'Actualizando tu aplicación';

  @override
  String get fetchingYourAppDetails => 'Obteniendo los detalles de tu aplicación';

  @override
  String get updateAppQuestion => '¿Actualizar aplicación?';

  @override
  String get updateAppConfirmation => '¿Estás seguro de que quieres actualizar tu aplicación? Los cambios se reflejarán una vez revisados por nuestro equipo.';

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
  String get subscriptionCancelledSuccessfully => 'Suscripción cancelada con éxito. Permanecerá activa hasta el final del período de facturación actual.';

  @override
  String get failedToCancelSubscription => 'Error al cancelar la suscripción. Por favor, inténtalo de nuevo.';

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
  String get cancelSubscriptionConfirmation => '¿Estás seguro de que quieres cancelar tu suscripción? Seguirás teniendo acceso hasta el final de tu período de facturación actual.';

  @override
  String get cancelSubscriptionButton => 'Cancelar suscripción';

  @override
  String get cancelling => 'Cancelando...';

  @override
  String get betaTesterMessage => 'Eres un probador beta de esta aplicación. Aún no es pública. Será pública una vez aprobada.';

  @override
  String get appUnderReviewMessage => 'Tu aplicación está en revisión y solo es visible para ti. Será pública una vez aprobada.';

  @override
  String get appRejectedMessage => 'Tu aplicación ha sido rechazada. Actualiza los detalles y vuelve a enviarla para revisión.';

  @override
  String get invalidIntegrationUrl => 'URL de integración no válida';

  @override
  String get tapToComplete => 'Toca para completar';

  @override
  String get invalidSetupInstructionsUrl => 'URL de instrucciones de configuración no válida';

  @override
  String get pushToTalk => 'Pulsa para hablar';

  @override
  String get summaryPrompt => 'Indicación de resumen';

  @override
  String get pleaseSelectARating => 'Por favor, selecciona una calificación';

  @override
  String get reviewAddedSuccessfully => 'Reseña añadida con éxito 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'Reseña actualizada con éxito 🚀';

  @override
  String get failedToSubmitReview => 'Error al enviar la reseña. Por favor, inténtalo de nuevo.';

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
  String get issueActivatingApp => 'Hubo un problema al activar esta aplicación. Por favor, inténtalo de nuevo.';

  @override
  String get dataAccessNoticeDescription => 'Esta aplicación accederá a tus datos. Omi AI no es responsable de cómo esta aplicación utiliza, modifica o elimina tus datos';

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
  String get permissionDeniedForAppleReminders => 'Permiso denegado para Apple Reminders';

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
  String get apiKeysDescription => 'Las claves API se utilizan para la autenticación cuando tu aplicación se comunica con el servidor de OMI. Permiten que tu aplicación cree recuerdos y acceda a otros servicios de OMI de forma segura.';

  @override
  String get aboutOmiApiKeys => 'Acerca de las claves API de Omi';

  @override
  String get yourNewKey => 'Tu nueva clave:';

  @override
  String get copyToClipboard => 'Copiar al portapapeles';

  @override
  String get pleaseCopyKeyNow => 'Por favor, cópiala ahora y anótala en un lugar seguro. ';

  @override
  String get willNotSeeAgain => 'No podrás verla de nuevo.';

  @override
  String get revokeKey => 'Revocar clave';

  @override
  String get revokeApiKeyQuestion => '¿Revocar clave API?';

  @override
  String get revokeApiKeyWarning => 'Esta acción no se puede deshacer. Las aplicaciones que usen esta clave ya no podrán acceder a la API.';

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
  String get failedToCreateKeyTryAgain => 'Error al crear la clave. Por favor, inténtalo de nuevo.';

  @override
  String get keyCreated => 'Clave creada';

  @override
  String get keyCreatedMessage => 'Tu nueva clave ha sido creada. Por favor, cópiala ahora. No podrás verla de nuevo.';

  @override
  String get keyWord => 'Clave';

  @override
  String get externalAppAccess => 'Acceso de aplicaciones externas';

  @override
  String get externalAppAccessDescription => 'Las siguientes aplicaciones instaladas tienen integraciones externas y pueden acceder a tus datos, como conversaciones y recuerdos.';

  @override
  String get noExternalAppsHaveAccess => 'Ninguna aplicación externa tiene acceso a tus datos.';

  @override
  String get maximumSecurityE2ee => 'Seguridad máxima (E2EE)';

  @override
  String get e2eeDescription => 'El cifrado de extremo a extremo es el estándar de oro para la privacidad. Cuando está habilitado, tus datos se cifran en tu dispositivo antes de enviarse a nuestros servidores. Esto significa que nadie, ni siquiera Omi, puede acceder a tu contenido.';

  @override
  String get importantTradeoffs => 'Compensaciones importantes:';

  @override
  String get e2eeTradeoff1 => '• Algunas funciones como las integraciones de aplicaciones externas pueden estar deshabilitadas.';

  @override
  String get e2eeTradeoff2 => '• Si pierdes tu contraseña, tus datos no se pueden recuperar.';

  @override
  String get featureComingSoon => '¡Esta función estará disponible pronto!';

  @override
  String get migrationInProgressMessage => 'Migración en progreso. No puedes cambiar el nivel de protección hasta que se complete.';

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
  String get secureEncryptionDescription => 'Tus datos se cifran con una clave única para ti en nuestros servidores, alojados en Google Cloud. Esto significa que tu contenido sin procesar es inaccesible para cualquier persona, incluido el personal de Omi o Google, directamente desde la base de datos.';

  @override
  String get endToEndEncryption => 'Cifrado de extremo a extremo';

  @override
  String get e2eeCardDescription => 'Activa para máxima seguridad donde solo tú puedes acceder a tus datos. Toca para saber más.';

  @override
  String get dataAlwaysEncrypted => 'Independientemente del nivel, tus datos siempre están cifrados en reposo y en tránsito.';

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
  String get saveKeyWarning => '¡Guarda esta clave ahora! No podrás verla de nuevo.';

  @override
  String get yourApiKey => 'TU CLAVE API';

  @override
  String get tapToCopy => 'Toca para copiar';

  @override
  String get copyKey => 'Copiar clave';

  @override
  String get createApiKey => 'Crear clave API';

  @override
  String get accessDataProgrammatically => 'Accede a tus datos programáticamente';

  @override
  String get keyNameLabel => 'NOMBRE DE CLAVE';

  @override
  String get keyNamePlaceholder => 'ej., Mi integración de app';

  @override
  String get permissionsLabel => 'PERMISOS';

  @override
  String get permissionsInfoNote => 'R = Lectura, W = Escritura. Por defecto solo lectura si no se selecciona nada.';

  @override
  String get developerApi => 'API de desarrollador';

  @override
  String get createAKeyToGetStarted => 'Crea una clave para comenzar';

  @override
  String errorWithMessage(String error) {
    return 'Error: $error';
  }

  @override
  String get omiTraining => 'Entrenamiento de Omi';

  @override
  String get trainingDataProgram => 'Programa de datos de entrenamiento';

  @override
  String get getOmiUnlimitedFree => 'Obtén Omi Ilimitado gratis contribuyendo tus datos para entrenar modelos de IA.';

  @override
  String get trainingDataBullets => '• Tus datos ayudan a mejorar los modelos de IA\n• Solo se comparten datos no sensibles\n• Proceso completamente transparente';

  @override
  String get learnMoreAtOmiTraining => 'Aprende más en omi.me/training';

  @override
  String get agreeToContributeData => 'Entiendo y acepto contribuir mis datos para el entrenamiento de IA';

  @override
  String get submitRequest => 'Enviar solicitud';

  @override
  String get thankYouRequestUnderReview => '¡Gracias! Tu solicitud está en revisión. Te notificaremos cuando sea aprobada.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'Tu plan permanecerá activo hasta $date. Después, perderás acceso a tus funciones ilimitadas. ¿Estás seguro?';
  }

  @override
  String get confirmCancellation => 'Confirmar cancelación';

  @override
  String get keepMyPlan => 'Mantener mi plan';

  @override
  String get subscriptionSetToCancel => 'Tu suscripción está configurada para cancelarse al final del período.';

  @override
  String get switchedToOnDevice => 'Cambiado a transcripción en dispositivo';

  @override
  String get couldNotSwitchToFreePlan => 'No se pudo cambiar al plan gratuito. Por favor, inténtalo de nuevo.';

  @override
  String get couldNotLoadPlans => 'No se pudieron cargar los planes disponibles. Por favor, inténtalo de nuevo.';

  @override
  String get selectedPlanNotAvailable => 'El plan seleccionado no está disponible. Por favor, inténtalo de nuevo.';

  @override
  String get upgradeToAnnualPlan => 'Actualizar al plan anual';

  @override
  String get importantBillingInfo => 'Información de facturación importante:';

  @override
  String get monthlyPlanContinues => 'Tu plan mensual actual continuará hasta el final de tu período de facturación';

  @override
  String get paymentMethodCharged => 'Tu método de pago existente se cobrará automáticamente cuando termine tu plan mensual';

  @override
  String get annualSubscriptionStarts => 'Tu suscripción anual de 12 meses comenzará automáticamente después del cargo';

  @override
  String get thirteenMonthsCoverage => 'Obtendrás 13 meses de cobertura en total (mes actual + 12 meses anuales)';

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
  String get upgradeAlreadyScheduled => 'Tu actualización al plan anual ya está programada';

  @override
  String get youAreOnUnlimitedPlan => 'Estás en el plan Ilimitado.';

  @override
  String get yourOmiUnleashed => 'Tu Omi, liberado. Hazte ilimitado para posibilidades infinitas.';

  @override
  String planEndedOn(String date) {
    return 'Tu plan terminó el $date.\\nVuelve a suscribirte ahora - se te cobrará inmediatamente por un nuevo período de facturación.';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'Tu plan está configurado para cancelarse el $date.\\nVuelve a suscribirte ahora para mantener tus beneficios - sin cargo hasta $date.';
  }

  @override
  String get annualPlanStartsAutomatically => 'Tu plan anual comenzará automáticamente cuando termine tu plan mensual.';

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
  String get alreadyBestValuePlan => 'Ya tienes el plan de mejor valor. No se necesitan cambios.';

  @override
  String get unableToLoadPlans => 'No se pueden cargar los planes';

  @override
  String get checkConnectionTryAgain => 'Comprueba tu conexión e inténtalo de nuevo';

  @override
  String get useFreePlan => 'Usar plan gratuito';

  @override
  String get continueText => 'Continuar';

  @override
  String get resubscribe => 'Volver a suscribirse';

  @override
  String get couldNotOpenPaymentSettings => 'No se pudieron abrir los ajustes de pago. Por favor, inténtalo de nuevo.';

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
  String get privacyIntroText => 'En Omi, nos tomamos tu privacidad muy en serio. Queremos ser transparentes sobre los datos que recopilamos y cómo los usamos para mejorar nuestro producto. Esto es lo que necesitas saber:';

  @override
  String get whatWeTrack => 'Qué rastreamos';

  @override
  String get anonymityAndPrivacy => 'Anonimato y privacidad';

  @override
  String get optInAndOptOutOptions => 'Opciones de aceptación y rechazo';

  @override
  String get ourCommitment => 'Nuestro compromiso';

  @override
  String get commitmentText => 'Nos comprometemos a usar los datos que recopilamos solo para hacer de Omi un mejor producto para ti. Tu privacidad y confianza son primordiales para nosotros.';

  @override
  String get thankYouText => 'Gracias por ser un usuario valioso de Omi. Si tienes alguna pregunta o inquietud, no dudes en contactarnos en team@basedhardware.com.';
}
