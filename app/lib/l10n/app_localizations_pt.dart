// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Portuguese (`pt`).
class AppLocalizationsPt extends AppLocalizations {
  AppLocalizationsPt([String locale = 'pt']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'Conversa';

  @override
  String get transcriptTab => 'Transcrição';

  @override
  String get actionItemsTab => 'Ações';

  @override
  String get deleteConversationTitle => 'Apagar conversa?';

  @override
  String get deleteConversationMessage =>
      'Tem certeza de que deseja apagar esta conversa? Esta ação não pode ser desfeita.';

  @override
  String get confirm => 'Confirmar';

  @override
  String get cancel => 'Cancelar';

  @override
  String get ok => 'OK';

  @override
  String get delete => 'Apagar';

  @override
  String get add => 'Adicionar';

  @override
  String get update => 'Atualizar';

  @override
  String get save => 'Salvar';

  @override
  String get edit => 'Editar';

  @override
  String get close => 'Fechar';

  @override
  String get clear => 'Limpar';

  @override
  String get copyTranscript => 'Copiar transcrição';

  @override
  String get copySummary => 'Copiar resumo';

  @override
  String get testPrompt => 'Testar prompt';

  @override
  String get reprocessConversation => 'Reprocessar conversa';

  @override
  String get deleteConversation => 'Apagar conversa';

  @override
  String get contentCopied => 'Conteúdo copiado para a área de transferência';

  @override
  String get failedToUpdateStarred => 'Falha ao atualizar favorito.';

  @override
  String get conversationUrlNotShared => 'URL da conversa não compartilhada.';

  @override
  String get errorProcessingConversation => 'Erro ao processar conversa. Tente novamente mais tarde.';

  @override
  String get noInternetConnection => 'Verifique sua conexão com a internet e tente novamente.';

  @override
  String get unableToDeleteConversation => 'Não foi possível apagar a conversa';

  @override
  String get somethingWentWrong => 'Algo deu errado! Tente novamente mais tarde.';

  @override
  String get copyErrorMessage => 'Copiar mensagem de erro';

  @override
  String get errorCopied => 'Mensagem de erro copiada';

  @override
  String get remaining => 'Restante';

  @override
  String get loading => 'Carregando...';

  @override
  String get loadingDuration => 'Carregando duração...';

  @override
  String secondsCount(int count) {
    return '$count segundos';
  }

  @override
  String get people => 'Pessoas';

  @override
  String get addNewPerson => 'Adicionar nova pessoa';

  @override
  String get editPerson => 'Editar pessoa';

  @override
  String get createPersonHint => 'Crie uma nova pessoa e treine o Omi para reconhecer a voz dela!';

  @override
  String get speechProfile => 'Perfil de voz';

  @override
  String sampleNumber(int number) {
    return 'Amostra $number';
  }

  @override
  String get settings => 'Configurações';

  @override
  String get language => 'Idioma';

  @override
  String get selectLanguage => 'Selecionar idioma';

  @override
  String get deleting => 'Apagando...';

  @override
  String get pleaseCompleteAuthentication =>
      'Por favor, complete a autenticação no seu navegador. Volte para o app quando terminar.';

  @override
  String get failedToStartAuthentication => 'Falha ao iniciar autenticação';

  @override
  String get importStarted => 'Importação iniciada! Avisaremos quando terminar.';

  @override
  String get failedToStartImport => 'Falha ao iniciar importação. Tente novamente.';

  @override
  String get couldNotAccessFile => 'Não foi possível acessar o arquivo selecionado';

  @override
  String get askOmi => 'Pergunte ao Omi';

  @override
  String get done => 'Concluído';

  @override
  String get disconnected => 'Desconectado';

  @override
  String get searching => 'Buscando';

  @override
  String get connectDevice => 'Conectar dispositivo';

  @override
  String get monthlyLimitReached => 'Você atingiu seu limite mensal.';

  @override
  String get checkUsage => 'Verificar uso';

  @override
  String get syncingRecordings => 'Sincronizando gravações';

  @override
  String get recordingsToSync => 'Gravações para sincronizar';

  @override
  String get allCaughtUp => 'Tudo atualizado';

  @override
  String get sync => 'Sincronizar';

  @override
  String get pendantUpToDate => 'Pendant atualizado';

  @override
  String get allRecordingsSynced => 'Todas as gravações sincronizadas';

  @override
  String get syncingInProgress => 'Sincronização em andamento';

  @override
  String get readyToSync => 'Pronto para sincronizar';

  @override
  String get tapSyncToStart => 'Toque em Sincronizar para começar';

  @override
  String get pendantNotConnected => 'Pendant não conectado. Conecte para sincronizar.';

  @override
  String get everythingSynced => 'Tudo sincronizado.';

  @override
  String get recordingsNotSynced => 'Você tem gravações não sincronizadas.';

  @override
  String get syncingBackground => 'Continuaremos sincronizando em segundo plano.';

  @override
  String get noConversationsYet => 'Nenhuma conversa ainda.';

  @override
  String get noStarredConversations => 'Nenhuma conversa favorita.';

  @override
  String get starConversationHint => 'Para favoritar uma conversa, abra-a e toque na estrela no topo.';

  @override
  String get searchConversations => 'Buscar conversas';

  @override
  String selectedCount(int count) {
    return '$count selecionados';
  }

  @override
  String get merge => 'Mesclar';

  @override
  String get mergeConversations => 'Mesclar conversas';

  @override
  String mergeConversationsMessage(int count) {
    return 'Isso combinará $count conversas em uma. Todo o conteúdo será mesclado e regenerado.';
  }

  @override
  String get mergingInBackground => 'Mesclando em segundo plano. Isso pode levar um momento.';

  @override
  String get failedToStartMerge => 'Falha ao iniciar mesclagem';

  @override
  String get askAnything => 'Pergunte qualquer coisa';

  @override
  String get noMessagesYet => 'Nenhuma mensagem ainda!\nPor que não começar uma conversa?';

  @override
  String get deletingMessages => 'Apagando suas mensagens da memória do Omi...';

  @override
  String get messageCopied => 'Mensagem copiada para a área de transferência.';

  @override
  String get cannotReportOwnMessage => 'Você não pode reportar suas próprias mensagens.';

  @override
  String get reportMessage => 'Reportar mensagem';

  @override
  String get reportMessageConfirm => 'Tem certeza de que deseja reportar esta mensagem?';

  @override
  String get messageReported => 'Mensagem reportada com sucesso.';

  @override
  String get thankYouFeedback => 'Obrigado pelo feedback!';

  @override
  String get clearChat => 'Limpar chat?';

  @override
  String get clearChatConfirm => 'Tem certeza de que deseja limpar o chat? Esta ação não pode ser desfeita.';

  @override
  String get maxFilesLimit => 'Você só pode enviar 4 arquivos por vez';

  @override
  String get chatWithOmi => 'Converse com Omi';

  @override
  String get apps => 'Apps';

  @override
  String get noAppsFound => 'Nenhum app encontrado';

  @override
  String get tryAdjustingSearch => 'Tente ajustar sua busca ou filtros';

  @override
  String get createYourOwnApp => 'Crie seu próprio App';

  @override
  String get buildAndShareApp => 'Construa e compartilhe seu próprio app';

  @override
  String get searchApps => 'Buscar em 1500+ apps';

  @override
  String get myApps => 'Meus Apps';

  @override
  String get installedApps => 'Apps instalados';

  @override
  String get unableToFetchApps => 'Não foi possível carregar os apps :(\n\nVerifique sua conexão.';

  @override
  String get aboutOmi => 'Sobre o Omi';

  @override
  String get privacyPolicy => 'Política de Privacidade';

  @override
  String get visitWebsite => 'Visitar site';

  @override
  String get helpOrInquiries => 'Ajuda ou dúvidas?';

  @override
  String get joinCommunity => 'Junte-se à comunidade!';

  @override
  String get membersAndCounting => '8000+ membros e contando.';

  @override
  String get deleteAccountTitle => 'Apagar conta';

  @override
  String get deleteAccountConfirm => 'Tem certeza de que deseja apagar sua conta?';

  @override
  String get cannotBeUndone => 'Isso não pode ser desfeito.';

  @override
  String get allDataErased => 'Todas as suas memórias e conversas serão apagadas permanentemente.';

  @override
  String get appsDisconnected => 'Seus apps e integrações serão desconectados imediatamente.';

  @override
  String get exportBeforeDelete =>
      'Você pode exportar seus dados antes de apagar sua conta. Uma vez apagada, não pode ser recuperada.';

  @override
  String get deleteAccountCheckbox =>
      'Entendo que apagar minha conta é permanente e todos os dados, incluindo memórias e conversas, serão perdidos para sempre.';

  @override
  String get areYouSure => 'Tem certeza?';

  @override
  String get deleteAccountFinal =>
      'Esta ação é irreversível e apagará permanentemente sua conta e todos os dados associados. Deseja continuar?';

  @override
  String get deleteNow => 'Apagar agora';

  @override
  String get goBack => 'Voltar';

  @override
  String get checkBoxToConfirm =>
      'Marque a caixa para confirmar que entende que apagar sua conta é permanente e irreversível.';

  @override
  String get profile => 'Perfil';

  @override
  String get name => 'Nome';

  @override
  String get email => 'Email';

  @override
  String get customVocabulary => 'Vocabulário personalizado';

  @override
  String get identifyingOthers => 'Identificando outros';

  @override
  String get paymentMethods => 'Métodos de pagamento';

  @override
  String get conversationDisplay => 'Exibição de conversa';

  @override
  String get dataPrivacy => 'Dados e Privacidade';

  @override
  String get userId => 'ID de usuário';

  @override
  String get notSet => 'Não definido';

  @override
  String get userIdCopied => 'ID de usuário copiado';

  @override
  String get systemDefault => 'Padrão do sistema';

  @override
  String get planAndUsage => 'Plano e Uso';

  @override
  String get offlineSync => 'Sincronização offline';

  @override
  String get deviceSettings => 'Configurações do dispositivo';

  @override
  String get chatTools => 'Ferramentas de chat';

  @override
  String get feedbackBug => 'Feedback / Bug';

  @override
  String get helpCenter => 'Central de ajuda';

  @override
  String get developerSettings => 'Configurações de desenvolvedor';

  @override
  String get getOmiForMac => 'Obter Omi para Mac';

  @override
  String get referralProgram => 'Programa de indicação';

  @override
  String get signOut => 'Sair';

  @override
  String get appAndDeviceCopied => 'Detalhes do app e dispositivo copiados';

  @override
  String get wrapped2025 => 'Retrospectiva 2025';

  @override
  String get yourPrivacyYourControl => 'Sua privacidade, seu controle';

  @override
  String get privacyIntro =>
      'No Omi, estamos comprometidos em proteger sua privacidade. Esta página permite que você controle como seus dados são salvos e usados.';

  @override
  String get learnMore => 'Saiba mais...';

  @override
  String get dataProtectionLevel => 'Nível de proteção de dados';

  @override
  String get dataProtectionDesc => 'Seus dados são protegidos por criptografia forte por padrão.';

  @override
  String get appAccess => 'Acesso de apps';

  @override
  String get appAccessDesc => 'Os seguintes apps têm acesso aos seus dados. Toque em um app para gerenciar permissões.';

  @override
  String get noAppsExternalAccess => 'Nenhum app instalado tem acesso externo aos seus dados.';

  @override
  String get deviceName => 'Nome do dispositivo';

  @override
  String get deviceId => 'ID do dispositivo';

  @override
  String get firmware => 'Firmware';

  @override
  String get sdCardSync => 'Sincronização Cartão SD';

  @override
  String get hardwareRevision => 'Revisão de hardware';

  @override
  String get modelNumber => 'Número do modelo';

  @override
  String get manufacturer => 'Fabricante';

  @override
  String get doubleTap => 'Toque duplo';

  @override
  String get ledBrightness => 'Brilho do LED';

  @override
  String get micGain => 'Ganho do microfone';

  @override
  String get disconnect => 'Desconectar';

  @override
  String get forgetDevice => 'Esquecer dispositivo';

  @override
  String get chargingIssues => 'Problemas de carregamento';

  @override
  String get disconnectDevice => 'Desconectar dispositivo';

  @override
  String get unpairDevice => 'Desparear dispositivo';

  @override
  String get unpairAndForget => 'Desparear e esquecer';

  @override
  String get deviceDisconnectedMessage => 'Seu Omi desconectou 😔';

  @override
  String get deviceUnpairedMessage =>
      'Dispositivo despareado. Vá em Configurações > Bluetooth e esqueça o dispositivo para concluir.';

  @override
  String get unpairDialogTitle => 'Desparear dispositivo';

  @override
  String get unpairDialogMessage =>
      'Isso despareará o dispositivo para que possa ser usado em outro telefone. Você deve ir em Configurações > Bluetooth e esquecer o dispositivo para concluir.';

  @override
  String get deviceNotConnected => 'Dispositivo não conectado';

  @override
  String get connectDeviceMessage => 'Conecte seu dispositivo Omi para acessar configurações e personalização.';

  @override
  String get deviceInfoSection => 'Info do dispositivo';

  @override
  String get customizationSection => 'Personalização';

  @override
  String get hardwareSection => 'Hardware';

  @override
  String get v2Undetected => 'V2 não detectado';

  @override
  String get v2UndetectedMessage =>
      'Detectamos que você está usando um dispositivo V1 ou não está conectado. A funcionalidade de cartão SD é apenas para dispositivos V2.';

  @override
  String get endConversation => 'Terminar conversa';

  @override
  String get pauseResume => 'Pausar/Retomar';

  @override
  String get starConversation => 'Favoritar conversa';

  @override
  String get doubleTapAction => 'Ação de toque duplo';

  @override
  String get doubleTapActionDesc => 'Escolha o que acontece ao tocar duas vezes';

  @override
  String get endAndProcess => 'Terminar e processar';

  @override
  String get pauseResumeRecording => 'Pausar/Retomar gravação';

  @override
  String get starOngoing => 'Favoritar conversa atual';

  @override
  String get starOngoingDesc => 'Marcar para salvar como favorita ao terminar';

  @override
  String get off => 'Desligado';

  @override
  String get max => 'Máx';

  @override
  String get mute => 'Mudo';

  @override
  String get quiet => 'Baixo';

  @override
  String get normal => 'Normal';

  @override
  String get high => 'Alto';

  @override
  String get micGainDescMuted => 'Microfone mudo';

  @override
  String get micGainDescLow => 'Muito baixo - para ambientes ruidosos';

  @override
  String get micGainDescModerate => 'Baixo - para ruído moderado';

  @override
  String get micGainDescNeutral => 'Neutro - gravação balanceada';

  @override
  String get micGainDescSlightlyBoosted => 'Levemente aumentado - uso normal';

  @override
  String get micGainDescBoosted => 'Aumentado - para ambientes silenciosos';

  @override
  String get micGainDescHigh => 'Alto - para vozes distantes ou suaves';

  @override
  String get micGainDescVeryHigh => 'Muito alto - fontes muito silenciosas';

  @override
  String get micGainDescMax => 'Máximo - use com cuidado';

  @override
  String get developerSettingsTitle => 'Configurações de desenvolvedor';

  @override
  String get saving => 'Salvando...';

  @override
  String get personaConfig => 'Configure sua Persona IA';

  @override
  String get beta => 'BETA';

  @override
  String get transcription => 'Transcrição';

  @override
  String get transcriptionConfig => 'Configurar provedor STT';

  @override
  String get conversationTimeout => 'Tempo limite de conversa';

  @override
  String get conversationTimeoutConfig => 'Defina quando terminar conversas automaticamente';

  @override
  String get importData => 'Importar dados';

  @override
  String get importDataConfig => 'Importar dados de outras fontes';

  @override
  String get debugDiagnostics => 'Depuração e Diagnóstico';

  @override
  String get endpointUrl => 'URL do endpoint';

  @override
  String get noApiKeys => 'Sem chaves API ainda';

  @override
  String get createKeyToStart => 'Crie uma chave para começar';

  @override
  String get createKey => 'Criar chave';

  @override
  String get docs => 'Documentação';

  @override
  String get yourOmiInsights => 'Seus insights do Omi';

  @override
  String get today => 'Hoje';

  @override
  String get thisMonth => 'Este mês';

  @override
  String get thisYear => 'Este ano';

  @override
  String get allTime => 'Tudo';

  @override
  String get noActivityYet => 'Sem atividade ainda';

  @override
  String get startConversationToSeeInsights => 'Inicie uma conversa com o Omi\npara ver seus insights aqui.';

  @override
  String get listening => 'Ouvindo';

  @override
  String get listeningSubtitle => 'Tempo total que o Omi ouviu ativamente.';

  @override
  String get understanding => 'Entendendo';

  @override
  String get understandingSubtitle => 'Palavras entendidas de suas conversas.';

  @override
  String get providing => 'Fornecendo';

  @override
  String get providingSubtitle => 'Tarefas e notas capturadas automaticamente.';

  @override
  String get remembering => 'Lembrando';

  @override
  String get rememberingSubtitle => 'Fatos e detalhes lembrados para você.';

  @override
  String get unlimitedPlan => 'Plano Ilimitado';

  @override
  String get managePlan => 'Gerenciar plano';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'Seu plano termina em $date.';
  }

  @override
  String renewsOn(String date) {
    return 'Seu plano renova em $date.';
  }

  @override
  String get basicPlan => 'Plano Básico';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used de $limit minutos usados';
  }

  @override
  String get upgrade => 'Fazer upgrade';

  @override
  String get upgradeToUnlimited => 'Upgrade para Ilimitado';

  @override
  String basicPlanDesc(int limit) {
    return 'Seu plano inclui $limit minutos grátis/mês.';
  }

  @override
  String get shareStatsMessage =>
      'Compartilhando minhas estatísticas do Omi! (omi.me - meu assistente IA sempre ativo)';

  @override
  String get sharePeriodToday => 'Hoje Omi:';

  @override
  String get sharePeriodMonth => 'Este mês Omi:';

  @override
  String get sharePeriodYear => 'Este ano Omi:';

  @override
  String get sharePeriodAllTime => 'Até agora Omi:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 Ouviu por $minutes minutos';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 Entendeu $words palavras';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ Forneceu $count insights';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 Salvou $count memórias';
  }

  @override
  String get debugLogs => 'Logs de depuração';

  @override
  String get debugLogsAutoDelete => 'Deletados automaticamente após 3 dias.';

  @override
  String get debugLogsDesc => 'Ajuda a diagnosticar problemas';

  @override
  String get noLogFilesFound => 'Nenhum arquivo de log encontrado.';

  @override
  String get omiDebugLog => 'Log de depuração Omi';

  @override
  String get logShared => 'Log compartilhado';

  @override
  String get selectLogFile => 'Selecionar arquivo de log';

  @override
  String get shareLogs => 'Compartilhar logs';

  @override
  String get debugLogCleared => 'Log de depuração limpo';

  @override
  String get exportStarted => 'Exportação iniciada. Pode levar alguns segundos...';

  @override
  String get exportAllData => 'Exportar todos os dados';

  @override
  String get exportDataDesc => 'Exportar conversas para arquivo JSON';

  @override
  String get exportedConversations => 'Conversas exportadas do Omi';

  @override
  String get exportShared => 'Exportação compartilhada';

  @override
  String get deleteKnowledgeGraphTitle => 'Apagar Gráfico de Conhecimento?';

  @override
  String get deleteKnowledgeGraphMessage =>
      'Isso apagará todos os dados derivados do gráfico (nós e conexões). Suas memórias originais permanecem seguras.';

  @override
  String get knowledgeGraphDeleted => 'Gráfico de conhecimento apagado com sucesso';

  @override
  String deleteGraphFailed(String error) {
    return 'Falha ao apagar gráfico: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'Apagar gráfico de conhecimento';

  @override
  String get deleteKnowledgeGraphDesc => 'Remover todos os nós e conexões';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'Servidor MCP';

  @override
  String get mcpServerDesc => 'Conecte assistentes IA aos seus dados';

  @override
  String get serverUrl => 'URL do servidor';

  @override
  String get urlCopied => 'URL copiada';

  @override
  String get apiKeyAuth => 'Autenticação API Key';

  @override
  String get header => 'Cabeçalho';

  @override
  String get authorizationBearer => 'Authorization: Bearer <key>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'Client ID';

  @override
  String get clientSecret => 'Client Secret';

  @override
  String get useMcpApiKey => 'Use sua chave API do MCP';

  @override
  String get webhooks => 'Webhooks';

  @override
  String get conversationEvents => 'Eventos de conversa';

  @override
  String get newConversationCreated => 'Nova conversa criada';

  @override
  String get realtimeTranscript => 'Transcrição em tempo real';

  @override
  String get transcriptReceived => 'Transcrição recebida';

  @override
  String get audioBytes => 'Bytes de áudio';

  @override
  String get audioDataReceived => 'Dados de áudio recebidos';

  @override
  String get intervalSeconds => 'Intervalo (segundos)';

  @override
  String get daySummary => 'Resumo diário';

  @override
  String get summaryGenerated => 'Resumo gerado';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'Adicionar ao claude_desktop_config.json';

  @override
  String get copyConfig => 'Copiar configuração';

  @override
  String get configCopied => 'Configuração copiada para a área de transferência';

  @override
  String get listeningMins => 'Ouvindo (Mins)';

  @override
  String get understandingWords => 'Entendendo (Palavras)';

  @override
  String get insights => 'Insights';

  @override
  String get memories => 'Memórias';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '$used de $limit mins usados este mês';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '$used de $limit palavras usadas este mês';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '$used de $limit insights este mês';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return '$used de $limit memórias este mês';
  }

  @override
  String get visibility => 'Visibilidade';

  @override
  String get visibilitySubtitle => 'Controle quais conversas aparecem na sua lista';

  @override
  String get showShortConversations => 'Mostrar conversas curtas';

  @override
  String get showShortConversationsDesc => 'Mostrar conversas menores que o limite';

  @override
  String get showDiscardedConversations => 'Mostrar conversas descartadas';

  @override
  String get showDiscardedConversationsDesc => 'Incluir conversas marcadas como descartadas';

  @override
  String get shortConversationThreshold => 'Limite de conversa curta';

  @override
  String get shortConversationThresholdSubtitle => 'Conversas menores que isso são ocultadas se não ativado acima';

  @override
  String get durationThreshold => 'Limite de duração';

  @override
  String get durationThresholdDesc => 'Ocultar conversas menores que isso';

  @override
  String minLabel(int count) {
    return '$count Min';
  }

  @override
  String get customVocabularyTitle => 'Vocabulário personalizado';

  @override
  String get addWords => 'Adicionar palavras';

  @override
  String get addWordsDesc => 'Nomes, gírias ou palavras incomuns';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'Conectar';

  @override
  String get comingSoon => 'Em breve';

  @override
  String get chatToolsFooter => 'Conecte seus apps para ver dados e métricas no chat.';

  @override
  String get completeAuthInBrowser => 'Por favor, complete a autenticação no seu navegador.';

  @override
  String failedToStartAuth(String appName) {
    return 'Falha ao iniciar autenticação para $appName';
  }

  @override
  String disconnectAppTitle(String appName) {
    return 'Desconectar $appName?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'Tem certeza de que deseja desconectar $appName? Você pode reconectar a qualquer momento.';
  }

  @override
  String disconnectedFrom(String appName) {
    return 'Desconectado de $appName';
  }

  @override
  String get failedToDisconnect => 'Falha ao desconectar';

  @override
  String connectTo(String appName) {
    return 'Conectar a $appName';
  }

  @override
  String authAccessMessage(String appName) {
    return 'Você precisa autorizar o Omi a acessar seus dados de $appName.';
  }

  @override
  String get continueAction => 'Continuar';

  @override
  String get languageTitle => 'Idioma';

  @override
  String get primaryLanguage => 'Idioma principal';

  @override
  String get automaticTranslation => 'Tradução automática';

  @override
  String get detectLanguages => 'Detectar 10+ idiomas';

  @override
  String get authorizeSavingRecordings => 'Autorizar salvar gravações';

  @override
  String get thanksForAuthorizing => 'Obrigado por autorizar!';

  @override
  String get needYourPermission => 'Precisamos da sua permissão';

  @override
  String get alreadyGavePermission =>
      'Você já nos deu permissão para salvar suas gravações. Aqui está o lembrete do porquê:';

  @override
  String get wouldLikePermission => 'Gostaríamos da sua permissão para salvar suas gravações de voz. Eis o motivo:';

  @override
  String get improveSpeechProfile => 'Melhorar seu perfil de voz';

  @override
  String get improveSpeechProfileDesc => 'Usamos gravações para treinar e melhorar seu perfil de voz pessoal.';

  @override
  String get trainFamilyProfiles => 'Treinar perfis de amigos e família';

  @override
  String get trainFamilyProfilesDesc =>
      'Suas gravações ajudam a reconhecer e criar perfis para seus amigos e familiares.';

  @override
  String get enhanceTranscriptAccuracy => 'Melhorar precisão da transcrição';

  @override
  String get enhanceTranscriptAccuracyDesc => 'Conforme nosso modelo melhora, podemos oferecer melhores transcrições.';

  @override
  String get legalNotice => 'Aviso legal: A legalidade da gravação pode variar conforme sua localização.';

  @override
  String get alreadyAuthorized => 'Já autorizado';

  @override
  String get authorize => 'Autorizar';

  @override
  String get revokeAuthorization => 'Revogar autorização';

  @override
  String get authorizationSuccessful => 'Autorização bem-sucedida!';

  @override
  String get failedToAuthorize => 'Falha ao autorizar. Tente novamente.';

  @override
  String get authorizationRevoked => 'Autorização revogada.';

  @override
  String get recordingsDeleted => 'Gravações apagadas.';

  @override
  String get failedToRevoke => 'Falha ao revogar autorização.';

  @override
  String get permissionRevokedTitle => 'Permissão revogada';

  @override
  String get permissionRevokedMessage => 'Deseja que apaguemos todas as suas gravações existentes também?';

  @override
  String get yes => 'Sim';

  @override
  String get editName => 'Editar nome';

  @override
  String get howShouldOmiCallYou => 'Como o Omi deve te chamar?';

  @override
  String get enterYourName => 'Digite seu nome';

  @override
  String get nameCannotBeEmpty => 'Nome não pode ser vazio';

  @override
  String get nameUpdatedSuccessfully => 'Nome atualizado com sucesso!';

  @override
  String get calendarSettings => 'Configurações de calendário';

  @override
  String get calendarProviders => 'Provedores de calendário';

  @override
  String get macOsCalendar => 'Calendário macOS';

  @override
  String get connectMacOsCalendar => 'Conecte seu calendário local do macOS';

  @override
  String get googleCalendar => 'Google Calendar';

  @override
  String get syncGoogleAccount => 'Sincronizar com sua conta Google';

  @override
  String get showMeetingsMenuBar => 'Mostrar reuniões na barra de menu';

  @override
  String get showMeetingsMenuBarDesc => 'Mostrar sua próxima reunião e tempo restante na barra de menu do macOS';

  @override
  String get showEventsNoParticipants => 'Mostrar eventos sem participantes';

  @override
  String get showEventsNoParticipantsDesc =>
      'Se ativado, \'Em breve\' mostrará eventos sem participantes ou link de vídeo.';

  @override
  String get yourMeetings => 'Suas reuniões';

  @override
  String get refresh => 'Atualizar';

  @override
  String get noUpcomingMeetings => 'Nenhuma reunião futura';

  @override
  String get checkingNextDays => 'Verificando próximos 30 dias';

  @override
  String get tomorrow => 'Amanhã';

  @override
  String get googleCalendarComingSoon => 'Integração com Google Calendar em breve!';

  @override
  String connectedAsUser(String userId) {
    return 'Conectado como: $userId';
  }

  @override
  String get defaultWorkspace => 'Workspace padrão';

  @override
  String get tasksCreatedInWorkspace => 'Tarefas serão criadas neste workspace';

  @override
  String get defaultProjectOptional => 'Projeto padrão (Opcional)';

  @override
  String get leaveUnselectedTasks => 'Deixe desmarcado para tarefas sem projeto';

  @override
  String get noProjectsInWorkspace => 'Nenhum projeto encontrado neste workspace';

  @override
  String get conversationTimeoutDesc => 'Escolha quanto tempo esperar em silêncio antes de terminar:';

  @override
  String get timeout2Minutes => '2 minutos';

  @override
  String get timeout2MinutesDesc => 'Terminar após 2 minutos de silêncio';

  @override
  String get timeout5Minutes => '5 minutos';

  @override
  String get timeout5MinutesDesc => 'Terminar após 5 minutos de silêncio';

  @override
  String get timeout10Minutes => '10 minutos';

  @override
  String get timeout10MinutesDesc => 'Terminar após 10 minutos de silêncio';

  @override
  String get timeout30Minutes => '30 minutos';

  @override
  String get timeout30MinutesDesc => 'Terminar após 30 minutos de silêncio';

  @override
  String get timeout4Hours => '4 horas';

  @override
  String get timeout4HoursDesc => 'Terminar após 4 horas de silêncio';

  @override
  String get conversationEndAfterHours => 'Conversas terminam após 4 horas de silêncio';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Conversas terminam após $minutes minuto(s) de silêncio';
  }

  @override
  String get tellUsPrimaryLanguage => 'Diga-nos seu idioma principal';

  @override
  String get languageForTranscription => 'Configure seu idioma para transcrições mais precisas.';

  @override
  String get singleLanguageModeInfo => 'Modo de idioma único ativado.';

  @override
  String get searchLanguageHint => 'Buscar idioma por nome ou código';

  @override
  String get noLanguagesFound => 'Nenhum idioma encontrado';

  @override
  String get skip => 'Pular';

  @override
  String languageSetTo(String language) {
    return 'Idioma definido para $language';
  }

  @override
  String get failedToSetLanguage => 'Falha ao definir idioma';

  @override
  String appSettings(String appName) {
    return 'Configurações de $appName';
  }

  @override
  String disconnectFromApp(String appName) {
    return 'Desconectar de $appName?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'Isso removerá sua autenticação de $appName.';
  }

  @override
  String connectedToApp(String appName) {
    return 'Conectado a $appName';
  }

  @override
  String get account => 'Conta';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Suas tarefas são sincronizadas com sua conta $appName';
  }

  @override
  String get defaultSpace => 'Espaço padrão';

  @override
  String get selectSpaceInWorkspace => 'Selecione um espaço no workspace';

  @override
  String get noSpacesInWorkspace => 'Nenhum espaço encontrado';

  @override
  String get defaultList => 'Lista padrão';

  @override
  String get tasksAddedToList => 'Tarefas serão adicionadas a esta lista';

  @override
  String get noListsInSpace => 'Nenhuma lista encontrada';

  @override
  String failedToLoadRepos(String error) {
    return 'Falha ao carregar repositórios: $error';
  }

  @override
  String get defaultRepoSaved => 'Repositório padrão salvo';

  @override
  String get failedToSaveDefaultRepo => 'Falha ao salvar repositório padrão';

  @override
  String get defaultRepository => 'Repositório padrão';

  @override
  String get selectDefaultRepoDesc => 'Escolha um repo padrão para criar issues.';

  @override
  String get noReposFound => 'Nenhum repositório encontrado';

  @override
  String get private => 'Privado';

  @override
  String updatedDate(String date) {
    return 'Atualizado em $date';
  }

  @override
  String get yesterday => 'ontem';

  @override
  String daysAgo(int count) {
    return '$count dias atrás';
  }

  @override
  String get oneWeekAgo => '1 semana atrás';

  @override
  String weeksAgo(int count) {
    return '$count semanas atrás';
  }

  @override
  String get oneMonthAgo => '1 mês atrás';

  @override
  String monthsAgo(int count) {
    return '$count meses atrás';
  }

  @override
  String get issuesCreatedInRepo => 'Issues serão criadas no seu repo padrão';

  @override
  String get taskIntegrations => 'Integrações de tarefas';

  @override
  String get configureSettings => 'Configurar ajustes';

  @override
  String get completeAuthBrowser => 'Please complete authentication in your browser. Once done, return to the app.';

  @override
  String failedToStartAppAuth(String appName) {
    return 'Failed to start $appName authentication';
  }

  @override
  String connectToAppTitle(String appName) {
    return 'Connect to $appName';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'You\'ll need to authorize Omi to create tasks in your $appName account. This will open your browser for authentication.';
  }

  @override
  String get continueButton => 'Continue';

  @override
  String appIntegration(String appName) {
    return 'Integração $appName';
  }

  @override
  String integrationComingSoon(String appName) {
    return 'Integração com $appName em breve!';
  }

  @override
  String get gotIt => 'Entendi';

  @override
  String get tasksExportedOneApp => 'Tarefas só podem ser exportadas para um app por vez.';

  @override
  String get completeYourUpgrade => 'Complete seu upgrade';

  @override
  String get importConfiguration => 'Importar configuração';

  @override
  String get exportConfiguration => 'Exportar configuração';

  @override
  String get bringYourOwn => 'Traga o seu';

  @override
  String get payYourSttProvider => 'Use Omi de graça. Você paga apenas seu provedor STT.';

  @override
  String get freeMinutesMonth => '1.200 minutos grátis/mês incluídos.';

  @override
  String get omiUnlimited => 'Omi Ilimitado';

  @override
  String get hostRequired => 'Host é obrigatório';

  @override
  String get validPortRequired => 'Porta válida obrigatória';

  @override
  String get validWebsocketUrlRequired => 'URL WebSocket válida obrigatória (wss://)';

  @override
  String get apiUrlRequired => 'URL API obrigatória';

  @override
  String get apiKeyRequired => 'API Key obrigatória';

  @override
  String get invalidJsonConfig => 'JSON inválido';

  @override
  String errorSaving(String error) {
    return 'Erro ao salvar: $error';
  }

  @override
  String get configCopiedToClipboard => 'Configuração copiada para a área de transferência';

  @override
  String get pasteJsonConfig => 'Cole sua configuração JSON abaixo:';

  @override
  String get addApiKeyAfterImport => 'Você deve adicionar sua própria API Key após importar';

  @override
  String get paste => 'Colar';

  @override
  String get import => 'Importar';

  @override
  String get invalidProviderInConfig => 'Provedor inválido na configuração';

  @override
  String importedConfig(String providerName) {
    return 'Configuração de $providerName importada';
  }

  @override
  String invalidJson(String error) {
    return 'JSON inválido: $error';
  }

  @override
  String get provider => 'Provedor';

  @override
  String get live => 'Ao vivo';

  @override
  String get onDevice => 'No dispositivo';

  @override
  String get apiUrl => 'URL API';

  @override
  String get enterSttHttpEndpoint => 'Insira seu endpoint STT HTTP';

  @override
  String get websocketUrl => 'URL WebSocket';

  @override
  String get enterLiveSttWebsocket => 'Insira seu endpoint STT WebSocket';

  @override
  String get apiKey => 'API Key';

  @override
  String get enterApiKey => 'Insira sua API Key';

  @override
  String get storedLocallyNeverShared => 'Armazenado localmente, nunca compartilhado';

  @override
  String get host => 'Host';

  @override
  String get port => 'Porta';

  @override
  String get advanced => 'Avançado';

  @override
  String get configuration => 'Configuração';

  @override
  String get requestConfiguration => 'Configuração da requisição';

  @override
  String get responseSchema => 'Esquema de resposta';

  @override
  String get modified => 'Modificado';

  @override
  String get resetRequestConfig => 'Redefinir configuração';

  @override
  String get logs => 'Logs';

  @override
  String get logsCopied => 'Logs copiados';

  @override
  String get noLogsYet => 'Sem logs ainda. Grave para ver atividade.';

  @override
  String deviceUsesCodec(String deviceName, String codecReason) {
    return '$deviceName usa $codecReason. Omi será usado.';
  }

  @override
  String get omiTranscription => 'Transcrição Omi';

  @override
  String get bestInClassTranscription => 'Transcrição de ponta';

  @override
  String get instantSpeakerLabels => 'Rótulos de falante instantâneos';

  @override
  String get languageTranslation => 'Tradução em 100+ idiomas';

  @override
  String get optimizedForConversation => 'Otimizado para conversas';

  @override
  String get autoLanguageDetection => 'Detecção automática de idioma';

  @override
  String get highAccuracy => 'Alta precisão';

  @override
  String get privacyFirst => 'Privacidade primeiro';

  @override
  String get saveChanges => 'Salvar alterações';

  @override
  String get resetToDefault => 'Redefinir para padrão';

  @override
  String get viewTemplate => 'Ver modelo';

  @override
  String get trySomethingLike => 'Tente algo como...';

  @override
  String get tryIt => 'Testar';

  @override
  String get creatingPlan => 'Criando plano';

  @override
  String get developingLogic => 'Desenvolvendo lógica';

  @override
  String get designingApp => 'Projetando App';

  @override
  String get generatingIconStep => 'Gerando ícone';

  @override
  String get finalTouches => 'Toques finais';

  @override
  String get processing => 'Processando...';

  @override
  String get features => 'Funcionalidades';

  @override
  String get creatingYourApp => 'Criando seu App...';

  @override
  String get generatingIcon => 'Gerando ícone...';

  @override
  String get whatShouldWeMake => 'O que devemos fazer?';

  @override
  String get appName => 'Nome do App';

  @override
  String get description => 'Descrição';

  @override
  String get publicLabel => 'Público';

  @override
  String get privateLabel => 'Privado';

  @override
  String get free => 'Grátis';

  @override
  String get perMonth => '/ mês';

  @override
  String get tailoredConversationSummaries => 'Resumos de conversa sob medida';

  @override
  String get customChatbotPersonality => 'Personalidade de chatbot personalizada';

  @override
  String get makePublic => 'Tornar público';

  @override
  String get anyoneCanDiscover => 'Qualquer um pode descobrir seu App';

  @override
  String get onlyYouCanUse => 'Apenas você pode usar este App';

  @override
  String get paidApp => 'App pago';

  @override
  String get usersPayToUse => 'Usuários pagam para usar seu App';

  @override
  String get freeForEveryone => 'Grátis para todos';

  @override
  String get perMonthLabel => '/ mês';

  @override
  String get creating => 'Criando...';

  @override
  String get createApp => 'Criar App';

  @override
  String get searchingForDevices => 'Procurando dispositivos...';

  @override
  String devicesFoundNearby(int count) {
    return '$count dispositivos encontrados';
  }

  @override
  String get pairingSuccessful => 'Pareamento com sucesso';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Erro conectando Apple Watch: $error';
  }

  @override
  String get dontShowAgain => 'Não mostrar novamente';

  @override
  String get iUnderstand => 'Eu entendo';

  @override
  String get enableBluetooth => 'Ativar Bluetooth';

  @override
  String get bluetoothNeeded => 'Omi precisa de Bluetooth para conectar seu wearable.';

  @override
  String get contactSupport => 'Contatar suporte?';

  @override
  String get connectLater => 'Conectar mais tarde';

  @override
  String get grantPermissions => 'Conceder permissões';

  @override
  String get backgroundActivity => 'Atividade em segundo plano';

  @override
  String get backgroundActivityDesc => 'Deixe o Omi rodar em segundo plano para maior estabilidade';

  @override
  String get locationAccess => 'Acesso à localização';

  @override
  String get locationAccessDesc => 'Habilite localização em segundo plano para experiência completa';

  @override
  String get notifications => 'Notificações';

  @override
  String get notificationsDesc => 'Habilite notificações para ficar informado';

  @override
  String get locationServiceDisabled => 'Serviço de localização desativado';

  @override
  String get locationServiceDisabledDesc => 'Por favor ative os serviços de localização';

  @override
  String get backgroundLocationDenied => 'Acesso à localização em segundo plano negado';

  @override
  String get backgroundLocationDeniedDesc => 'Por favor permita \'Sempre\' nas configurações';

  @override
  String get lovingOmi => 'Amando o Omi?';

  @override
  String get leaveReviewIos => 'Ajude-nos a alcançar mais pessoas deixando uma avaliação na App Store.';

  @override
  String get leaveReviewAndroid => 'Ajude-nos a alcançar mais pessoas deixando uma avaliação na Google Play.';

  @override
  String get rateOnAppStore => 'Avaliar na App Store';

  @override
  String get rateOnGooglePlay => 'Avaliar na Google Play';

  @override
  String get maybeLater => 'Talvez depois';

  @override
  String get speechProfileIntro => 'Omi precisa aprender seus objetivos e sua voz.';

  @override
  String get getStarted => 'Começar';

  @override
  String get allDone => 'Tudo pronto!';

  @override
  String get keepGoing => 'Continue';

  @override
  String get skipThisQuestion => 'Pular esta pergunta';

  @override
  String get skipForNow => 'Pular por enquanto';

  @override
  String get connectionError => 'Erro de conexão';

  @override
  String get connectionErrorDesc => 'Falha ao conectar com servidor.';

  @override
  String get invalidRecordingMultipleSpeakers => 'Gravação inválida';

  @override
  String get multipleSpeakersDesc => 'Parece haver múltiplos falantes.';

  @override
  String get tooShortDesc => 'Não detectamos fala suficiente.';

  @override
  String get invalidRecordingDesc => 'Certifique-se de falar por pelo menos 5 segundos.';

  @override
  String get areYouThere => 'Está aí?';

  @override
  String get noSpeechDesc => 'Não conseguimos detectar fala.';

  @override
  String get connectionLost => 'Conexão perdida';

  @override
  String get connectionLostDesc => 'A conexão foi perdida.';

  @override
  String get tryAgain => 'Tente novamente';

  @override
  String get connectOmiOmiGlass => 'Conectar Omi / OmiGlass';

  @override
  String get continueWithoutDevice => 'Continuar sem dispositivo';

  @override
  String get permissionsRequired => 'Permissões necessárias';

  @override
  String get permissionsRequiredDesc => 'Este app requer permissões de Bluetooth e Localização.';

  @override
  String get openSettings => 'Abrir configurações';

  @override
  String get wantDifferentName => 'Quer usar um nome diferente?';

  @override
  String get whatsYourName => 'Qual é o seu nome?';

  @override
  String get speakTranscribeSummarize => 'Fale. Transcreva. Resuma.';

  @override
  String get signInWithApple => 'Entrar com Apple';

  @override
  String get signInWithGoogle => 'Entrar com Google';

  @override
  String get byContinuingAgree => 'Ao continuar, você concorda com nossos ';

  @override
  String get termsOfUse => 'Termos de Uso';

  @override
  String get omiYourAiCompanion => 'Omi – Seu companheiro IA';

  @override
  String get captureEveryMoment => 'Capture cada momento. Obtenha resumos IA.';

  @override
  String get appleWatchSetup => 'Configuração Apple Watch';

  @override
  String get permissionRequestedExclaim => 'Permissão solicitada!';

  @override
  String get microphonePermission => 'Permissão de microfone';

  @override
  String get permissionGrantedNow => 'Permissão concedida!';

  @override
  String get needMicrophonePermission => 'Precisamos de permissão do microfone.';

  @override
  String get grantPermissionButton => 'Conceder permissão';

  @override
  String get needHelp => 'Precisa de ajuda?';

  @override
  String get troubleshootingSteps => 'Passos de solução de problemas...';

  @override
  String get recordingStartedSuccessfully => 'Gravação iniciada com sucesso!';

  @override
  String get permissionNotGrantedYet => 'Permissão ainda não concedida.';

  @override
  String errorRequestingPermission(String error) {
    return 'Erro ao pedir permissão: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'Erro ao iniciar gravação: $error';
  }

  @override
  String get selectPrimaryLanguage => 'Selecione seu idioma principal';

  @override
  String get languageBenefits => 'Configure seu idioma para melhores resultados';

  @override
  String get whatsYourPrimaryLanguage => 'Qual é o seu idioma principal?';

  @override
  String get selectYourLanguage => 'Selecione seu idioma';

  @override
  String get personalGrowthJourney => 'Sua jornada de crescimento pessoal com IA.';

  @override
  String get actionItemsTitle => 'Ações';

  @override
  String get actionItemsDescription => 'Toque para editar • Segure para selecionar • Deslize para ações';

  @override
  String get tabToDo => 'A fazer';

  @override
  String get tabDone => 'Feito';

  @override
  String get tabOld => 'Antigo';

  @override
  String get emptyTodoMessage => '🎉 Tudo feito!\nSem tarefas pendentes';

  @override
  String get emptyDoneMessage => 'Nenhum item feito ainda';

  @override
  String get emptyOldMessage => '✅ Nenhuma tarefa antiga';

  @override
  String get noItems => 'Sem itens';

  @override
  String get actionItemMarkedIncomplete => 'Marcado como incompleto';

  @override
  String get actionItemCompleted => 'Tarefa completa';

  @override
  String get deleteActionItemTitle => 'Apagar tarefa';

  @override
  String get deleteActionItemMessage => 'Tem certeza de que deseja apagar esta tarefa?';

  @override
  String get deleteSelectedItemsTitle => 'Apagar selecionados';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Tem certeza de que deseja apagar $count tarefas selecionadas?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'Tarefa \"$description\" apagada';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count tarefas apagadas';
  }

  @override
  String get failedToDeleteItem => 'Falha ao apagar tarefa';

  @override
  String get failedToDeleteItems => 'Falha ao apagar itens';

  @override
  String get failedToDeleteSomeItems => 'Falha ao apagar alguns itens';

  @override
  String get welcomeActionItemsTitle => 'Pronto para Ação';

  @override
  String get welcomeActionItemsDescription => 'Sua IA extrai tarefas automaticamente.';

  @override
  String get autoExtractionFeature => 'Extraído automaticamente das conversas';

  @override
  String get editSwipeFeature => 'Toque, deslize, gerencie';

  @override
  String itemsSelected(int count) {
    return '$count selecionados';
  }

  @override
  String get selectAll => 'Selecionar tudo';

  @override
  String get deleteSelected => 'Apagar selecionados';

  @override
  String searchMemories(int count) {
    return 'Buscar $count memórias';
  }

  @override
  String get memoryDeleted => 'Memória apagada.';

  @override
  String get undo => 'Desfazer';

  @override
  String get noMemoriesYet => 'Nenhuma memória ainda';

  @override
  String get noInterestingMemories => 'Nenhuma memória interessante';

  @override
  String get noSystemMemories => 'Nenhuma memória do sistema';

  @override
  String get noMemoriesInCategories => 'Nenhuma memória nestas categorias';

  @override
  String get noMemoriesFound => 'Nenhuma memória encontrada';

  @override
  String get addFirstMemory => 'Adicione sua primeira memória';

  @override
  String get clearMemoryTitle => 'Limpar memória do Omi?';

  @override
  String get clearMemoryMessage => 'Tem certeza de que deseja limpar a memória do Omi? Isso não pode ser desfeito.';

  @override
  String get clearMemoryButton => 'Limpar memória';

  @override
  String get memoryClearedSuccess => 'Memória limpa';

  @override
  String get noMemoriesToDelete => 'Nada para apagar';

  @override
  String get createMemoryTooltip => 'Criar nova memória';

  @override
  String get createActionItemTooltip => 'Criar nova tarefa';

  @override
  String get memoryManagement => 'Gerenciamento de memória';

  @override
  String get filterMemories => 'Filtrar memórias';

  @override
  String totalMemoriesCount(int count) {
    return 'Você tem $count memórias';
  }

  @override
  String get publicMemories => 'Memórias públicas';

  @override
  String get privateMemories => 'Memórias privadas';

  @override
  String get makeAllPrivate => 'Tornar tudo privado';

  @override
  String get makeAllPublic => 'Tornar tudo público';

  @override
  String get deleteAllMemories => 'Apagar tudo';

  @override
  String get allMemoriesPrivateResult => 'Todas as memórias são agora privadas';

  @override
  String get allMemoriesPublicResult => 'Todas as memórias são agora públicas';

  @override
  String get newMemory => 'Nova memória';

  @override
  String get editMemory => 'Editar memória';

  @override
  String get memoryContentHint => 'Eu gosto de sorvete...';

  @override
  String get failedToSaveMemory => 'Falha ao salvar.';

  @override
  String get saveMemory => 'Salvar memória';

  @override
  String get retry => 'Tentar novamente';

  @override
  String get createActionItem => 'Criar tarefa';

  @override
  String get editActionItem => 'Editar tarefa';

  @override
  String get actionItemDescriptionHint => 'O que precisa ser feito?';

  @override
  String get actionItemDescriptionEmpty => 'Descrição não pode ser vazia.';

  @override
  String get actionItemUpdated => 'Tarefa atualizada';

  @override
  String get failedToUpdateActionItem => 'Falha ao atualizar';

  @override
  String get actionItemCreated => 'Tarefa criada';

  @override
  String get failedToCreateActionItem => 'Falha ao criar';

  @override
  String get dueDate => 'Prazo';

  @override
  String get time => 'Hora';

  @override
  String get addDueDate => 'Adicionar prazo';

  @override
  String get pressDoneToSave => 'Pressione Concluído para salvar';

  @override
  String get pressDoneToCreate => 'Pressione Concluído para criar';

  @override
  String get filterAll => 'Todos';

  @override
  String get filterInteresting => 'Interessante';

  @override
  String get filterManual => 'Manual';

  @override
  String get filterSystem => 'Sistema';

  @override
  String get completed => 'Concluído';

  @override
  String get markComplete => 'Marcar como concluído';

  @override
  String get actionItemDeleted => 'Tarefa apagada';

  @override
  String get failedToDeleteActionItem => 'Falha ao apagar';

  @override
  String get deleteActionItemConfirmTitle => 'Apagar tarefa';

  @override
  String get deleteActionItemConfirmMessage => 'Tem certeza de que deseja apagar esta tarefa?';

  @override
  String get appLanguage => 'Idioma do App';
}
