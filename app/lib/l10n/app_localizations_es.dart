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
  String get deleteConversation => 'Borrar conversación';

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
  String get speechProfile => 'Perfil de voz';

  @override
  String sampleNumber(int number) {
    return 'Muestra $number';
  }

  @override
  String get settings => 'Ajustes';

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
  String get noStarredConversations => 'No hay conversaciones favoritas.';

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
  String get mergingInBackground => 'Fusionando en segundo plano. Esto puede tardar un momento.';

  @override
  String get failedToStartMerge => 'Error al iniciar fusión';

  @override
  String get askAnything => 'Pregunta cualquier cosa';

  @override
  String get noMessagesYet => '¡No hay mensajes!\n¿Por qué no inicias una conversación?';

  @override
  String get deletingMessages => 'Borrando tus mensajes de la memoria de Omi...';

  @override
  String get messageCopied => 'Mensaje copiado al portapapeles.';

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
  String get aboutOmi => 'Sobre Omi';

  @override
  String get privacyPolicy => 'Política de Privacidad';

  @override
  String get visitWebsite => 'Visitar sitio web';

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
  String get email => 'Email';

  @override
  String get customVocabulary => 'Vocabulario personalizado';

  @override
  String get identifyingOthers => 'Identificando a otros';

  @override
  String get paymentMethods => 'Métodos de pago';

  @override
  String get conversationDisplay => 'Visualización de conversación';

  @override
  String get dataPrivacy => 'Datos y Privacidad';

  @override
  String get userId => 'ID de usuario';

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
  String get developerSettings => 'Ajustes de desarrollador';

  @override
  String get getOmiForMac => 'Obtener Omi para Mac';

  @override
  String get referralProgram => 'Programa de referidos';

  @override
  String get signOut => 'Cerrar sesión';

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
  String get dataProtectionDesc => 'Tus datos están protegidos por encriptación fuerte por defecto.';

  @override
  String get appAccess => 'Acceso de apps';

  @override
  String get appAccessDesc =>
      'Las siguientes apps pueden acceder a tus datos. Toca una app para gestionar sus permisos.';

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
  String get endpointUrl => 'URL del endpoint';

  @override
  String get noApiKeys => 'Sin claves API aún';

  @override
  String get createKeyToStart => 'Crea una clave para empezar';

  @override
  String get createKey => 'Crear clave';

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
  String get noLogFilesFound => 'No se encontraron registros.';

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
  String get deleteKnowledgeGraphMessage =>
      'Esto borrará todos los datos derivados del gráfico (nodos y conexiones). Tus recuerdos originales se mantienen seguros.';

  @override
  String get knowledgeGraphDeleted => 'Gráfico de conocimiento borrado con éxito';

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
  String get daySummary => 'Resumen diario';

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
  String get insights => 'Insights';

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
  String get shortConversationThresholdSubtitle =>
      'Conversaciones más cortas que esto se ocultan si no está activado arriba';

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
  String get alreadyGavePermission =>
      'Ya nos diste permiso para guardar tus grabaciones. Aquí un recordatorio de por qué lo necesitamos:';

  @override
  String get wouldLikePermission => 'Nos gustaría tu permiso para guardar tus grabaciones de voz. Aquí está la razón:';

  @override
  String get improveSpeechProfile => 'Mejorar tu perfil de voz';

  @override
  String get improveSpeechProfileDesc => 'Usamos grabaciones para entrenar y mejorar tu perfil personal de voz.';

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
  String get enterYourName => 'Ingresa tu nombre';

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
  String get apiKey => 'API Key';

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
  String get grantPermissions => 'Otorgar permisos';

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
  String get whatsYourName => '¿Cuál es tu nombre?';

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
  String get personalGrowthJourney => 'Tu viaje de crecimiento personal con IA.';

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
  String searchMemories(int count) {
    return 'Buscar $count recuerdos';
  }

  @override
  String get memoryDeleted => 'Recuerdo borrado.';

  @override
  String get undo => 'Deshacer';

  @override
  String get noMemoriesYet => 'No hay recuerdos aún';

  @override
  String get noAutoMemories => 'No hay recuerdos automáticos';

  @override
  String get noManualMemories => 'No hay recuerdos manuales';

  @override
  String get noMemoriesInCategories => 'No hay recuerdos en estas categorías';

  @override
  String get noMemoriesFound => 'No se encontraron recuerdos';

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
  String get noMemoriesToDelete => 'Nada que borrar';

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
  String get deleteAllMemories => 'Borrar todo';

  @override
  String get allMemoriesPrivateResult => 'Todos los recuerdos son ahora privados';

  @override
  String get allMemoriesPublicResult => 'Todos los recuerdos son ahora públicos';

  @override
  String get newMemory => 'Nuevo recuerdo';

  @override
  String get editMemory => 'Editar recuerdo';

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
  String get languageSettingsHelperText =>
      'El idioma de la aplicación cambia los menús y botones. El idioma de voz afecta cómo se transcriben tus grabaciones.';

  @override
  String get translationNotice => 'Aviso de traducción';

  @override
  String get translationNoticeMessage =>
      'Omi traduce las conversaciones a tu idioma principal. Actualízalo en cualquier momento en Ajustes → Perfiles.';

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
  String get conversationCannotBeMerged =>
      'Esta conversación no se puede fusionar (bloqueada o ya en proceso de fusión)';

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
  String get deleteMemory => '¿Eliminar memoria?';

  @override
  String get thisActionCannotBeUndone => 'Esta acción no se puede deshacer.';

  @override
  String memoriesCount(int count) {
    return '$count memorias';
  }

  @override
  String get noMemoriesInCategory => 'Aún no hay memorias en esta categoría';

  @override
  String get addYourFirstMemory => 'Añade tu primera memoria';

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
  String get unpairDeviceDialogMessage =>
      'Esto desvinculará el dispositivo para que pueda conectarse a otro teléfono. Deberás ir a Configuración > Bluetooth y olvidar el dispositivo para completar el proceso.';

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
  String get noApiKeysYet => 'No API keys yet';

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
  String get debugAndDiagnostics => 'Debug & Diagnostics';

  @override
  String get autoDeletesAfter3Days => 'Auto-deletes after 3 days.';

  @override
  String get helpsDiagnoseIssues => 'Helps diagnose issues';

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
  String get realTimeTranscript => 'Real-time Transcript';

  @override
  String get experimental => 'Experimental';

  @override
  String get transcriptionDiagnostics => 'Transcription Diagnostics';

  @override
  String get detailedDiagnosticMessages => 'Detailed diagnostic messages';

  @override
  String get autoCreateSpeakers => 'Auto-create Speakers';

  @override
  String get autoCreateWhenNameDetected => 'Auto-create when name detected';

  @override
  String get followUpQuestions => 'Follow-up Questions';

  @override
  String get suggestQuestionsAfterConversations => 'Suggest questions after conversations';

  @override
  String get goalTracker => 'Goal Tracker';

  @override
  String get trackPersonalGoalsOnHomepage => 'Track your personal goals on homepage';

  @override
  String get dailyReflection => 'Daily Reflection';

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
  String get sdCardSyncDescription =>
      'La sincronización de la tarjeta SD importará tus recuerdos de la tarjeta SD a la aplicación';

  @override
  String get checksForAudioFiles => 'Comprueba archivos de audio en la tarjeta SD';

  @override
  String get omiSyncsAudioFiles => 'Omi luego sincroniza los archivos de audio con el servidor';

  @override
  String get serverProcessesAudio => 'El servidor procesa los archivos de audio y crea recuerdos';

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
  String get keyboardShortcuts => 'Atajos de teclado';

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
  String get welcomeBack => 'Bienvenido de nuevo';

  @override
  String get yourConversations => 'Tus conversaciones';

  @override
  String get reviewAndManageConversations => 'Revisa y gestiona tus conversaciones capturadas';

  @override
  String get startCapturingConversations =>
      'Comienza a capturar conversaciones con tu dispositivo Omi para verlas aquí.';

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
  String get all => 'Todas';

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
  String get pleaseCheckInternetConnectionAndTryAgain =>
      'Por favor, verifica tu conexión a Internet e inténtalo de nuevo';

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
  String get clickHereForAppBuildingGuides => 'Haz clic aquí para guías de creación de aplicaciones y documentación';

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
  String get integrationSetupRequired =>
      'Si esta es una aplicación de integración, asegúrese de que la configuración esté completa.';

  @override
  String get installed => 'Instalado';
}
