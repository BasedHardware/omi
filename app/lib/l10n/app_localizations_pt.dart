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
  String get cancel => 'Cancel';

  @override
  String get ok => 'OK';

  @override
  String get delete => 'Excluir';

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
  String get deleteConversation => 'Excluir Conversa';

  @override
  String get contentCopied => 'Conteúdo copiado para a área de transferência';

  @override
  String get failedToUpdateStarred => 'Falha ao atualizar favorito.';

  @override
  String get conversationUrlNotShared => 'URL da conversa não compartilhada.';

  @override
  String get errorProcessingConversation => 'Erro ao processar conversa. Tente novamente mais tarde.';

  @override
  String get noInternetConnection => 'Sem conexão com a internet';

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
  String get speechProfile => 'Perfil de Fala';

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
  String get askOmi => 'Perguntar ao Omi';

  @override
  String get done => 'Concluído';

  @override
  String get disconnected => 'Desconectado';

  @override
  String get searching => 'Pesquisando...';

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
  String get noConversationsYet => 'Ainda não há conversas';

  @override
  String get noStarredConversations => 'Nenhuma conversa favorita';

  @override
  String get starConversationHint => 'Para favoritar uma conversa, abra-a e toque na estrela no topo.';

  @override
  String get searchConversations => 'Pesquisar conversas...';

  @override
  String selectedCount(int count, Object s) {
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
  String get deletingMessages => 'Excluindo suas mensagens da memória do Omi...';

  @override
  String get messageCopied => '✨ Mensagem copiada para a área de transferência';

  @override
  String get cannotReportOwnMessage => 'Você não pode reportar suas próprias mensagens.';

  @override
  String get reportMessage => 'Denunciar mensagem';

  @override
  String get reportMessageConfirm => 'Tem certeza de que deseja reportar esta mensagem?';

  @override
  String get messageReported => 'Mensagem reportada com sucesso.';

  @override
  String get thankYouFeedback => 'Obrigado pelo feedback!';

  @override
  String get clearChat => 'Limpar conversa';

  @override
  String get clearChatConfirm => 'Tem certeza de que deseja limpar o chat? Esta ação não pode ser desfeita.';

  @override
  String get maxFilesLimit => 'Você só pode enviar 4 arquivos por vez';

  @override
  String get chatWithOmi => 'Converse com Omi';

  @override
  String get apps => 'Aplicativos';

  @override
  String get noAppsFound => 'Nenhum aplicativo encontrado';

  @override
  String get tryAdjustingSearch => 'Tente ajustar sua busca ou filtros';

  @override
  String get createYourOwnApp => 'Crie seu próprio aplicativo';

  @override
  String get buildAndShareApp => 'Construa e compartilhe seu próprio app';

  @override
  String get searchApps => 'Pesquisar aplicativos...';

  @override
  String get myApps => 'Meus aplicativos';

  @override
  String get installedApps => 'Aplicativos instalados';

  @override
  String get unableToFetchApps => 'Não foi possível carregar os apps :(\n\nVerifique sua conexão.';

  @override
  String get aboutOmi => 'Sobre o Omi';

  @override
  String get privacyPolicy => 'Política de Privacidade';

  @override
  String get visitWebsite => 'Visitar o site';

  @override
  String get helpOrInquiries => 'Ajuda ou perguntas?';

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
  String get email => 'E-mail';

  @override
  String get customVocabulary => 'Vocabulário Personalizado';

  @override
  String get identifyingOthers => 'Identificação de Outros';

  @override
  String get paymentMethods => 'Métodos de Pagamento';

  @override
  String get conversationDisplay => 'Exibição de Conversas';

  @override
  String get dataPrivacy => 'Privacidade de Dados';

  @override
  String get userId => 'ID do Usuário';

  @override
  String get notSet => 'Não definido';

  @override
  String get userIdCopied => 'ID de usuário copiado';

  @override
  String get systemDefault => 'Padrão do sistema';

  @override
  String get planAndUsage => 'Plano e Uso';

  @override
  String get offlineSync => 'Offline Sync';

  @override
  String get deviceSettings => 'Configurações do dispositivo';

  @override
  String get chatTools => 'Ferramentas de chat';

  @override
  String get feedbackBug => 'Feedback / Bug';

  @override
  String get helpCenter => 'Central de ajuda';

  @override
  String get developerSettings => 'Configurações do Desenvolvedor';

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
  String get deviceId => 'ID do Dispositivo';

  @override
  String get firmware => 'Firmware';

  @override
  String get sdCardSync => 'Sincronização do Cartão SD';

  @override
  String get hardwareRevision => 'Revisão de hardware';

  @override
  String get modelNumber => 'Número do Modelo';

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
  String get chargingIssues => 'Problemas de Carregamento';

  @override
  String get disconnectDevice => 'Desconectar Dispositivo';

  @override
  String get unpairDevice => 'Desvincular Dispositivo';

  @override
  String get unpairAndForget => 'Desparear e esquecer';

  @override
  String get deviceDisconnectedMessage => 'Seu Omi desconectou 😔';

  @override
  String get deviceUnpairedMessage =>
      'Dispositivo desvinculado. Vá para Configurações > Bluetooth e esqueça o dispositivo para concluir a desvinculação.';

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
  String get endAndProcess => 'Terminar e processar';

  @override
  String get pauseResumeRecording => 'Pausar/Retomar gravação';

  @override
  String get starOngoing => 'Favoritar conversa atual';

  @override
  String get off => 'Off';

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
  String get createKey => 'Criar Chave';

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
  String get basicPlan => 'Plano Gratuito';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used de $limit minutos usados';
  }

  @override
  String get upgrade => 'Fazer upgrade';

  @override
  String get upgradeToUnlimited => 'Atualizar para ilimitado';

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
  String get debugLogs => 'Registos de depuração';

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
  String get shareLogs => 'Partilhar registos';

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
  String get knowledgeGraphDeleted => 'Gráfico de conhecimento excluído';

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
  String get daySummary => 'Resumo do dia';

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
  String get editName => 'Edit Name';

  @override
  String get howShouldOmiCallYou => 'Como o Omi deve te chamar?';

  @override
  String get enterYourName => 'Insira o seu nome';

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
  String get noUpcomingMeetings => 'Sem reuniões próximas';

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
  String get yesterday => 'Ontem';

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
  String get completeAuthBrowser =>
      'Por favor, complete a autenticação no seu navegador. Quando terminar, volte para o app.';

  @override
  String failedToStartAppAuth(String appName) {
    return 'Falha ao iniciar autenticação do $appName';
  }

  @override
  String connectToAppTitle(String appName) {
    return 'Conectar ao $appName';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Você precisará autorizar o Omi para criar tarefas na sua conta $appName. Isso abrirá seu navegador para autenticação.';
  }

  @override
  String get continueButton => 'Continuar';

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
  String get apiKey => 'Chave API';

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
  String deviceUsesCodec(String device, String reason) {
    return '$device usa $reason. Omi será usado.';
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
  String get createApp => 'Criar Aplicativo';

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
  String get maybeLater => 'Talvez Mais Tarde';

  @override
  String get speechProfileIntro =>
      'O Omi precisa de aprender os seus objetivos e a sua voz. Poderá modificá-lo mais tarde.';

  @override
  String get getStarted => 'Começar';

  @override
  String get allDone => 'Tudo pronto!';

  @override
  String get keepGoing => 'Continue';

  @override
  String get skipThisQuestion => 'Saltar esta pergunta';

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
  String get personalGrowthJourney => 'Sua jornada de crescimento pessoal com IA que ouve cada palavra sua.';

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
  String get deleteActionItemTitle => 'Excluir item de ação';

  @override
  String get deleteActionItemMessage => 'Tem certeza de que deseja excluir este item de ação?';

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
  String get searchMemories => 'Buscar memórias...';

  @override
  String get memoryDeleted => 'Memória apagada.';

  @override
  String get undo => 'Desfazer';

  @override
  String get noMemoriesYet => '🧠 Ainda não há memórias';

  @override
  String get noAutoMemories => 'Nenhuma memória automática';

  @override
  String get noManualMemories => 'Nenhuma memória manual';

  @override
  String get noMemoriesInCategories => 'Nenhuma memória nestas categorias';

  @override
  String get noMemoriesFound => '🔍 Nenhuma memória encontrada';

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
  String get noMemoriesToDelete => 'Nenhuma memória para excluir';

  @override
  String get createMemoryTooltip => 'Criar nova memória';

  @override
  String get createActionItemTooltip => 'Criar nova tarefa';

  @override
  String get memoryManagement => 'Gestão de memória';

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
  String get deleteAllMemories => 'Excluir todas as memórias';

  @override
  String get allMemoriesPrivateResult => 'Todas as memórias são agora privadas';

  @override
  String get allMemoriesPublicResult => 'Todas as memórias são agora públicas';

  @override
  String get newMemory => '✨ Nova memória';

  @override
  String get editMemory => '✏️ Editar memória';

  @override
  String get memoryContentHint => 'Eu gosto de sorvete...';

  @override
  String get failedToSaveMemory => 'Falha ao salvar.';

  @override
  String get saveMemory => 'Salvar memória';

  @override
  String get retry => 'Retry';

  @override
  String get createActionItem => 'Criar item de ação';

  @override
  String get editActionItem => 'Editar item de ação';

  @override
  String get actionItemDescriptionHint => 'O que precisa ser feito?';

  @override
  String get actionItemDescriptionEmpty => 'Descrição não pode ser vazia.';

  @override
  String get actionItemUpdated => 'Tarefa atualizada';

  @override
  String get failedToUpdateActionItem => 'Falha ao atualizar item de ação';

  @override
  String get actionItemCreated => 'Tarefa criada';

  @override
  String get failedToCreateActionItem => 'Falha ao criar item de ação';

  @override
  String get dueDate => 'Data de vencimento';

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
  String get filterSystem => 'Sobre você';

  @override
  String get filterInteresting => 'Insights';

  @override
  String get filterManual => 'Manual';

  @override
  String get completed => 'Concluído';

  @override
  String get markComplete => 'Marcar como concluído';

  @override
  String get actionItemDeleted => 'Item de ação excluído';

  @override
  String get failedToDeleteActionItem => 'Falha ao excluir item de ação';

  @override
  String get deleteActionItemConfirmTitle => 'Apagar tarefa';

  @override
  String get deleteActionItemConfirmMessage => 'Tem certeza de que deseja apagar esta tarefa?';

  @override
  String get appLanguage => 'Idioma do App';

  @override
  String get appInterfaceSectionTitle => 'INTERFACE DO APLICATIVO';

  @override
  String get speechTranscriptionSectionTitle => 'FALA E TRANSCRIÇÃO';

  @override
  String get languageSettingsHelperText =>
      'O idioma do aplicativo altera menus e botões. O idioma de fala afeta como suas gravações são transcritas.';

  @override
  String get translationNotice => 'Aviso de tradução';

  @override
  String get translationNoticeMessage =>
      'O Omi traduz conversas para o seu idioma principal. Atualize-o a qualquer momento em Configurações → Perfis.';

  @override
  String get pleaseCheckInternetConnection => 'Verifique sua conexão com a Internet e tente novamente';

  @override
  String get pleaseSelectReason => 'Por favor, selecione um motivo';

  @override
  String get tellUsMoreWhatWentWrong => 'Conte-nos mais sobre o que deu errado...';

  @override
  String get selectText => 'Selecionar texto';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Máximo de $count objetivos permitidos';
  }

  @override
  String get conversationCannotBeMerged =>
      'Esta conversa não pode ser mesclada (bloqueada ou já em processo de mesclagem)';

  @override
  String get pleaseEnterFolderName => 'Por favor, insira um nome de pasta';

  @override
  String get failedToCreateFolder => 'Falha ao criar pasta';

  @override
  String get failedToUpdateFolder => 'Falha ao atualizar pasta';

  @override
  String get folderName => 'Nome da pasta';

  @override
  String get descriptionOptional => 'Descrição (opcional)';

  @override
  String get failedToDeleteFolder => 'Falha ao excluir pasta';

  @override
  String get editFolder => 'Editar pasta';

  @override
  String get deleteFolder => 'Excluir pasta';

  @override
  String get transcriptCopiedToClipboard => 'Transcrição copiada para a área de transferência';

  @override
  String get summaryCopiedToClipboard => 'Resumo copiado para a área de transferência';

  @override
  String get conversationUrlCouldNotBeShared => 'A URL da conversa não pôde ser compartilhada.';

  @override
  String get urlCopiedToClipboard => 'URL copiado para a área de transferência';

  @override
  String get exportTranscript => 'Exportar transcrição';

  @override
  String get exportSummary => 'Exportar resumo';

  @override
  String get exportButton => 'Exportar';

  @override
  String get actionItemsCopiedToClipboard => 'Itens de ação copiados para a área de transferência';

  @override
  String get summarize => 'Resumir';

  @override
  String get generateSummary => 'Gerar resumo';

  @override
  String get conversationNotFoundOrDeleted => 'Conversa não encontrada ou foi excluída';

  @override
  String get deleteMemory => 'Excluir memória';

  @override
  String get thisActionCannotBeUndone => 'Esta ação não pode ser desfeita.';

  @override
  String memoriesCount(int count) {
    return '$count memórias';
  }

  @override
  String get noMemoriesInCategory => 'Ainda não há memórias nesta categoria';

  @override
  String get addYourFirstMemory => 'Adicione sua primeira memória';

  @override
  String get firmwareDisconnectUsb => 'Desconectar USB';

  @override
  String get firmwareUsbWarning => 'A conexão USB durante as atualizações pode danificar seu dispositivo.';

  @override
  String get firmwareBatteryAbove15 => 'Bateria acima de 15%';

  @override
  String get firmwareEnsureBattery => 'Certifique-se de que seu dispositivo tenha 15% de bateria.';

  @override
  String get firmwareStableConnection => 'Conexão estável';

  @override
  String get firmwareConnectWifi => 'Conecte-se ao WiFi ou dados móveis.';

  @override
  String failedToStartUpdate(String error) {
    return 'Falha ao iniciar atualização: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'Antes de atualizar, certifique-se:';

  @override
  String get confirmed => 'Confirmado!';

  @override
  String get release => 'Soltar';

  @override
  String get slideToUpdate => 'Deslize para atualizar';

  @override
  String copiedToClipboard(String title) {
    return '$title copiado para a área de transferência';
  }

  @override
  String get batteryLevel => 'Nível da Bateria';

  @override
  String get productUpdate => 'Atualização do Produto';

  @override
  String get offline => 'Offline';

  @override
  String get available => 'Disponível';

  @override
  String get unpairDeviceDialogTitle => 'Desvincular Dispositivo';

  @override
  String get unpairDeviceDialogMessage =>
      'Isso desvinculará o dispositivo para que ele possa ser conectado a outro telefone. Você precisará ir para Configurações > Bluetooth e esquecer o dispositivo para concluir o processo.';

  @override
  String get unpair => 'Desvincular';

  @override
  String get unpairAndForgetDevice => 'Desvincular e Esquecer Dispositivo';

  @override
  String get unknownDevice => 'Unknown';

  @override
  String get unknown => 'Desconhecido';

  @override
  String get productName => 'Nome do Produto';

  @override
  String get serialNumber => 'Número de Série';

  @override
  String get connected => 'Conectado';

  @override
  String get privacyPolicyTitle => 'Política de Privacidade';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label copiado';
  }

  @override
  String get noApiKeysYet => 'Ainda não há chaves API. Crie uma para integrar com seu aplicativo.';

  @override
  String get createKeyToGetStarted => 'Crie uma chave para começar';

  @override
  String get persona => 'Persona';

  @override
  String get configureYourAiPersona => 'Configure sua persona de IA';

  @override
  String get configureSttProvider => 'Configurar provedor STT';

  @override
  String get setWhenConversationsAutoEnd => 'Defina quando as conversas terminam automaticamente';

  @override
  String get importDataFromOtherSources => 'Importar dados de outras fontes';

  @override
  String get debugAndDiagnostics => 'Depuração e Diagnósticos';

  @override
  String get autoDeletesAfter3Days => 'Exclusão automática após 3 dias';

  @override
  String get helpsDiagnoseIssues => 'Ajuda a diagnosticar problemas';

  @override
  String get exportStartedMessage => 'Exportação iniciada. Isso pode levar alguns segundos...';

  @override
  String get exportConversationsToJson => 'Exportar conversas para um arquivo JSON';

  @override
  String get knowledgeGraphDeletedSuccess => 'Grafo de conhecimento excluído com sucesso';

  @override
  String failedToDeleteGraph(String error) {
    return 'Falha ao excluir o grafo: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'Limpar todos os nós e conexões';

  @override
  String get addToClaudeDesktopConfig => 'Adicionar ao claude_desktop_config.json';

  @override
  String get connectAiAssistantsToData => 'Conecte assistentes de IA aos seus dados';

  @override
  String get useYourMcpApiKey => 'Use sua chave API MCP';

  @override
  String get realTimeTranscript => 'Transcrição em Tempo Real';

  @override
  String get experimental => 'Experimental';

  @override
  String get transcriptionDiagnostics => 'Diagnósticos de Transcrição';

  @override
  String get detailedDiagnosticMessages => 'Mensagens de diagnóstico detalhadas';

  @override
  String get autoCreateSpeakers => 'Criar Oradores Automaticamente';

  @override
  String get autoCreateWhenNameDetected => 'Criar automaticamente quando nome for detectado';

  @override
  String get followUpQuestions => 'Perguntas de Acompanhamento';

  @override
  String get suggestQuestionsAfterConversations => 'Sugerir perguntas após conversas';

  @override
  String get goalTracker => 'Rastreador de Metas';

  @override
  String get trackPersonalGoalsOnHomepage => 'Acompanhe suas metas pessoais na página inicial';

  @override
  String get dailyReflection => 'Reflexão diária';

  @override
  String get get9PmReminderToReflect => 'Receba um lembrete às 21h para refletir sobre seu dia';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'A descrição do item de ação não pode estar vazia';

  @override
  String get saved => 'Salvo';

  @override
  String get overdue => 'Atrasado';

  @override
  String get failedToUpdateDueDate => 'Falha ao atualizar a data de vencimento';

  @override
  String get markIncomplete => 'Marcar como incompleto';

  @override
  String get editDueDate => 'Editar data de vencimento';

  @override
  String get setDueDate => 'Definir data de vencimento';

  @override
  String get clearDueDate => 'Limpar data de vencimento';

  @override
  String get failedToClearDueDate => 'Falha ao limpar a data de vencimento';

  @override
  String get mondayAbbr => 'Seg';

  @override
  String get tuesdayAbbr => 'Ter';

  @override
  String get wednesdayAbbr => 'Qua';

  @override
  String get thursdayAbbr => 'Qui';

  @override
  String get fridayAbbr => 'Sex';

  @override
  String get saturdayAbbr => 'Sáb';

  @override
  String get sundayAbbr => 'Dom';

  @override
  String get howDoesItWork => 'Como funciona?';

  @override
  String get sdCardSyncDescription =>
      'A sincronização do cartão SD importará suas memórias do cartão SD para o aplicativo';

  @override
  String get checksForAudioFiles => 'Verifica arquivos de áudio no cartão SD';

  @override
  String get omiSyncsAudioFiles => 'O Omi então sincroniza os arquivos de áudio com o servidor';

  @override
  String get serverProcessesAudio => 'O servidor processa os arquivos de áudio e cria memórias';

  @override
  String get youreAllSet => 'Está tudo pronto!';

  @override
  String get welcomeToOmiDescription =>
      'Bem-vindo ao Omi! Seu companheiro de IA está pronto para ajudá-lo com conversas, tarefas e muito mais.';

  @override
  String get startUsingOmi => 'Começar a usar o Omi';

  @override
  String get back => 'Voltar';

  @override
  String get keyboardShortcuts => 'Atalhos de Teclado';

  @override
  String get toggleControlBar => 'Alternar barra de controle';

  @override
  String get pressKeys => 'Pressione as teclas...';

  @override
  String get cmdRequired => '⌘ necessário';

  @override
  String get invalidKey => 'Tecla inválida';

  @override
  String get space => 'Espaço';

  @override
  String get search => 'Pesquisar';

  @override
  String get searchPlaceholder => 'Pesquisar...';

  @override
  String get untitledConversation => 'Conversa Sem Título';

  @override
  String countRemaining(String count) {
    return '$count restantes';
  }

  @override
  String get addGoal => 'Adicionar meta';

  @override
  String get editGoal => 'Editar meta';

  @override
  String get icon => 'Ícone';

  @override
  String get goalTitle => 'Título da meta';

  @override
  String get current => 'Atual';

  @override
  String get target => 'Meta';

  @override
  String get saveGoal => 'Salvar';

  @override
  String get goals => 'Metas';

  @override
  String get tapToAddGoal => 'Toque para adicionar uma meta';

  @override
  String welcomeBack(String name) {
    return 'Bem-vindo de volta, $name';
  }

  @override
  String get yourConversations => 'Suas conversas';

  @override
  String get reviewAndManageConversations => 'Revise e gerencie suas conversas gravadas';

  @override
  String get startCapturingConversations => 'Comece a capturar conversas com seu dispositivo Omi para vê-las aqui.';

  @override
  String get useMobileAppToCapture => 'Use seu aplicativo móvel para capturar áudio';

  @override
  String get conversationsProcessedAutomatically => 'As conversas são processadas automaticamente';

  @override
  String get getInsightsInstantly => 'Obtenha insights e resumos instantaneamente';

  @override
  String get showAll => 'Mostrar tudo →';

  @override
  String get noTasksForToday => 'Nenhuma tarefa para hoje.\\nPergunte ao Omi por mais tarefas ou crie manualmente.';

  @override
  String get dailyScore => 'PONTUAÇÃO DIÁRIA';

  @override
  String get dailyScoreDescription => 'Uma pontuação para ajudá-lo\na focar melhor na execução.';

  @override
  String get searchResults => 'Resultados da pesquisa';

  @override
  String get actionItems => 'Itens de ação';

  @override
  String get tasksToday => 'Hoje';

  @override
  String get tasksTomorrow => 'Amanhã';

  @override
  String get tasksNoDeadline => 'Sem prazo';

  @override
  String get tasksLater => 'Mais tarde';

  @override
  String get loadingTasks => 'Carregando tarefas...';

  @override
  String get tasks => 'Tarefas';

  @override
  String get swipeTasksToIndent => 'Deslize tarefas para recuar, arraste entre categorias';

  @override
  String get create => 'Criar';

  @override
  String get noTasksYet => 'Ainda não há tarefas';

  @override
  String get tasksFromConversationsWillAppear =>
      'As tarefas de suas conversas aparecerão aqui.\nClique em Criar para adicionar uma manualmente.';

  @override
  String get monthJan => 'Jan';

  @override
  String get monthFeb => 'Fev';

  @override
  String get monthMar => 'Mar';

  @override
  String get monthApr => 'Abr';

  @override
  String get monthMay => 'Maio';

  @override
  String get monthJun => 'Jun';

  @override
  String get monthJul => 'Jul';

  @override
  String get monthAug => 'Ago';

  @override
  String get monthSep => 'Set';

  @override
  String get monthOct => 'Out';

  @override
  String get monthNov => 'Nov';

  @override
  String get monthDec => 'Dez';

  @override
  String get timePM => 'PM';

  @override
  String get timeAM => 'AM';

  @override
  String get actionItemUpdatedSuccessfully => 'Item de ação atualizado com sucesso';

  @override
  String get actionItemCreatedSuccessfully => 'Item de ação criado com sucesso';

  @override
  String get actionItemDeletedSuccessfully => 'Item de ação excluído com sucesso';

  @override
  String get deleteActionItem => 'Excluir item de ação';

  @override
  String get deleteActionItemConfirmation =>
      'Tem certeza de que deseja excluir este item de ação? Esta ação não pode ser desfeita.';

  @override
  String get enterActionItemDescription => 'Digite a descrição do item de ação...';

  @override
  String get markAsCompleted => 'Marcar como concluído';

  @override
  String get setDueDateAndTime => 'Definir data e hora de vencimento';

  @override
  String get reloadingApps => 'Recarregando aplicativos...';

  @override
  String get loadingApps => 'Carregando aplicativos...';

  @override
  String get browseInstallCreateApps => 'Navegue, instale e crie aplicativos';

  @override
  String get all => 'All';

  @override
  String get open => 'Abrir';

  @override
  String get install => 'Instalar';

  @override
  String get noAppsAvailable => 'Nenhum aplicativo disponível';

  @override
  String get unableToLoadApps => 'Não foi possível carregar aplicativos';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'Tente ajustar seus termos de pesquisa ou filtros';

  @override
  String get checkBackLaterForNewApps => 'Volte mais tarde para novos aplicativos';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain =>
      'Por favor, verifique sua conexão com a internet e tente novamente';

  @override
  String get createNewApp => 'Criar Novo Aplicativo';

  @override
  String get buildSubmitCustomOmiApp => 'Construa e envie seu aplicativo Omi personalizado';

  @override
  String get submittingYourApp => 'Enviando seu aplicativo...';

  @override
  String get preparingFormForYou => 'Preparando o formulário para você...';

  @override
  String get appDetails => 'Detalhes do Aplicativo';

  @override
  String get paymentDetails => 'Detalhes de Pagamento';

  @override
  String get previewAndScreenshots => 'Visualização e Capturas de Tela';

  @override
  String get appCapabilities => 'Recursos do Aplicativo';

  @override
  String get aiPrompts => 'Prompts de IA';

  @override
  String get chatPrompt => 'Prompt de Chat';

  @override
  String get chatPromptPlaceholder =>
      'Você é um aplicativo incrível, seu trabalho é responder às consultas dos usuários e fazê-los se sentirem bem...';

  @override
  String get conversationPrompt => 'Prompt de conversa';

  @override
  String get conversationPromptPlaceholder =>
      'Você é um aplicativo incrível, você receberá uma transcrição e resumo de uma conversa...';

  @override
  String get notificationScopes => 'Escopos de Notificação';

  @override
  String get appPrivacyAndTerms => 'Privacidade e Termos do Aplicativo';

  @override
  String get makeMyAppPublic => 'Tornar meu aplicativo público';

  @override
  String get submitAppTermsAgreement =>
      'Ao enviar este aplicativo, concordo com os Termos de Serviço e Política de Privacidade do Omi AI';

  @override
  String get submitApp => 'Enviar Aplicativo';

  @override
  String get needHelpGettingStarted => 'Precisa de ajuda para começar?';

  @override
  String get clickHereForAppBuildingGuides => 'Clique aqui para guias de criação de aplicativos e documentação';

  @override
  String get submitAppQuestion => 'Enviar Aplicativo?';

  @override
  String get submitAppPublicDescription =>
      'Seu aplicativo será revisado e tornado público. Você pode começar a usá-lo imediatamente, mesmo durante a revisão!';

  @override
  String get submitAppPrivateDescription =>
      'Seu aplicativo será revisado e disponibilizado para você de forma privada. Você pode começar a usá-lo imediatamente, mesmo durante a revisão!';

  @override
  String get startEarning => 'Comece a Ganhar! 💰';

  @override
  String get connectStripeOrPayPal => 'Conecte Stripe ou PayPal para receber pagamentos pelo seu aplicativo.';

  @override
  String get connectNow => 'Conectar Agora';

  @override
  String get installsCount => 'Instalações';

  @override
  String get uninstallApp => 'Desinstalar aplicativo';

  @override
  String get subscribe => 'Assinar';

  @override
  String get dataAccessNotice => 'Aviso de acesso a dados';

  @override
  String get dataAccessWarning =>
      'Este aplicativo acessará seus dados. Omi AI não é responsável por como seus dados são usados, modificados ou excluídos por este aplicativo';

  @override
  String get installApp => 'Instalar aplicativo';

  @override
  String get betaTesterNotice =>
      'Você é um testador beta deste aplicativo. Ele ainda não é público. Ele será público assim que for aprovado.';

  @override
  String get appUnderReviewOwner =>
      'Seu aplicativo está em análise e visível apenas para você. Ele será público assim que for aprovado.';

  @override
  String get appRejectedNotice =>
      'Seu aplicativo foi rejeitado. Por favor, atualize os detalhes do aplicativo e reenvie para análise.';

  @override
  String get setupSteps => 'Etapas de configuração';

  @override
  String get setupInstructions => 'Instruções de configuração';

  @override
  String get integrationInstructions => 'Instruções de integração';

  @override
  String get preview => 'Visualização';

  @override
  String get aboutTheApp => 'Sobre o app';

  @override
  String get aboutThePersona => 'Sobre a persona';

  @override
  String get chatPersonality => 'Personalidade do chat';

  @override
  String get ratingsAndReviews => 'Avaliações e resenhas';

  @override
  String get noRatings => 'sem avaliações';

  @override
  String ratingsCount(String count) {
    return '$count+ avaliações';
  }

  @override
  String get errorActivatingApp => 'Erro ao ativar o aplicativo';

  @override
  String get integrationSetupRequired =>
      'Se este for um aplicativo de integração, certifique-se de que a configuração está concluída.';

  @override
  String get installed => 'Instalado';

  @override
  String get appIdLabel => 'ID do aplicativo';

  @override
  String get appNameLabel => 'Nome do aplicativo';

  @override
  String get appNamePlaceholder => 'Meu aplicativo incrível';

  @override
  String get pleaseEnterAppName => 'Por favor, insira o nome do aplicativo';

  @override
  String get categoryLabel => 'Categoria';

  @override
  String get selectCategory => 'Selecionar categoria';

  @override
  String get descriptionLabel => 'Descrição';

  @override
  String get appDescriptionPlaceholder =>
      'Meu aplicativo incrível é um aplicativo incrível que faz coisas incríveis. É o melhor aplicativo!';

  @override
  String get pleaseProvideValidDescription => 'Por favor, forneça uma descrição válida';

  @override
  String get appPricingLabel => 'Preço do aplicativo';

  @override
  String get noneSelected => 'Nenhum selecionado';

  @override
  String get appIdCopiedToClipboard => 'ID do aplicativo copiado para a área de transferência';

  @override
  String get appCategoryModalTitle => 'Categoria do aplicativo';

  @override
  String get pricingFree => 'Grátis';

  @override
  String get pricingPaid => 'Pago';

  @override
  String get loadingCapabilities => 'Carregando recursos...';

  @override
  String get filterInstalled => 'Instalados';

  @override
  String get filterMyApps => 'Meus aplicativos';

  @override
  String get clearSelection => 'Limpar seleção';

  @override
  String get filterCategory => 'Categoria';

  @override
  String get rating4PlusStars => '4+ estrelas';

  @override
  String get rating3PlusStars => '3+ estrelas';

  @override
  String get rating2PlusStars => '2+ estrelas';

  @override
  String get rating1PlusStars => '1+ estrela';

  @override
  String get filterRating => 'Avaliação';

  @override
  String get filterCapabilities => 'Recursos';

  @override
  String get noNotificationScopesAvailable => 'Nenhum escopo de notificação disponível';

  @override
  String get popularApps => 'Aplicativos populares';

  @override
  String get pleaseProvidePrompt => 'Por favor, forneça um prompt';

  @override
  String chatWithAppName(String appName) {
    return 'Chat com $appName';
  }

  @override
  String get defaultAiAssistant => 'Assistente de IA padrão';

  @override
  String get readyToChat => '✨ Pronto para conversar!';

  @override
  String get connectionNeeded => '🌐 Conexão necessária';

  @override
  String get startConversation => 'Inicie uma conversa e deixe a mágica começar';

  @override
  String get checkInternetConnection => 'Por favor, verifique sua conexão com a internet';

  @override
  String get wasThisHelpful => 'Isso foi útil?';

  @override
  String get thankYouForFeedback => 'Obrigado pelo seu feedback!';

  @override
  String get maxFilesUploadError => 'Você só pode fazer upload de 4 arquivos por vez';

  @override
  String get attachedFiles => '📎 Arquivos anexados';

  @override
  String get takePhoto => 'Tirar foto';

  @override
  String get captureWithCamera => 'Capturar com câmera';

  @override
  String get selectImages => 'Selecionar imagens';

  @override
  String get chooseFromGallery => 'Escolher da galeria';

  @override
  String get selectFile => 'Selecionar um arquivo';

  @override
  String get chooseAnyFileType => 'Escolher qualquer tipo de arquivo';

  @override
  String get cannotReportOwnMessages => 'Você não pode denunciar suas próprias mensagens';

  @override
  String get messageReportedSuccessfully => '✅ Mensagem denunciada com sucesso';

  @override
  String get confirmReportMessage => 'Tem certeza de que deseja denunciar esta mensagem?';

  @override
  String get selectChatAssistant => 'Selecionar assistente de chat';

  @override
  String get enableMoreApps => 'Ativar mais aplicativos';

  @override
  String get chatCleared => 'Chat limpo';

  @override
  String get clearChatTitle => 'Limpar chat?';

  @override
  String get confirmClearChat => 'Tem certeza de que deseja limpar o chat? Esta ação não pode ser desfeita.';

  @override
  String get copy => 'Copiar';

  @override
  String get share => 'Compartilhar';

  @override
  String get report => 'Denunciar';

  @override
  String get microphonePermissionRequired => 'Permissão de microfone é necessária para gravação de voz.';

  @override
  String get microphonePermissionDenied =>
      'Permissão de microfone negada. Por favor, conceda permissão em Preferências do Sistema > Privacidade e Segurança > Microfone.';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'Falha ao verificar permissão do microfone: $error';
  }

  @override
  String get failedToTranscribeAudio => 'Falha ao transcrever áudio';

  @override
  String get transcribing => 'Transcrevendo...';

  @override
  String get transcriptionFailed => 'Transcrição falhou';

  @override
  String get discardedConversation => 'Conversa descartada';

  @override
  String get at => 'às';

  @override
  String get from => 'de';

  @override
  String get copied => 'Copiado!';

  @override
  String get copyLink => 'Copiar link';

  @override
  String get hideTranscript => 'Ocultar Transcrição';

  @override
  String get viewTranscript => 'Ver Transcrição';

  @override
  String get conversationDetails => 'Detalhes da Conversa';

  @override
  String get transcript => 'Transcrição';

  @override
  String segmentsCount(int count) {
    return '$count segmentos';
  }

  @override
  String get noTranscriptAvailable => 'Nenhuma Transcrição Disponível';

  @override
  String get noTranscriptMessage => 'Esta conversa não tem transcrição.';

  @override
  String get conversationUrlCouldNotBeGenerated => 'O URL da conversa não pôde ser gerado.';

  @override
  String get failedToGenerateConversationLink => 'Falha ao gerar link da conversa';

  @override
  String get failedToGenerateShareLink => 'Falha ao gerar link de compartilhamento';

  @override
  String get reloadingConversations => 'Recarregando conversas...';

  @override
  String get user => 'Usuário';

  @override
  String get starred => 'Favoritos';

  @override
  String get date => 'Data';

  @override
  String get noResultsFound => 'Nenhum resultado encontrado';

  @override
  String get tryAdjustingSearchTerms => 'Tente ajustar seus termos de pesquisa';

  @override
  String get starConversationsToFindQuickly => 'Marque conversas como favoritas para encontrá-las rapidamente aqui';

  @override
  String noConversationsOnDate(String date) {
    return 'Nenhuma conversa em $date';
  }

  @override
  String get trySelectingDifferentDate => 'Tente selecionar uma data diferente';

  @override
  String get conversations => 'Conversas';

  @override
  String get chat => 'Chat';

  @override
  String get actions => 'Ações';

  @override
  String get syncAvailable => 'Sincronização disponível';

  @override
  String get referAFriend => 'Indicar um amigo';

  @override
  String get help => 'Ajuda';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'Atualizar para Pro';

  @override
  String get getOmiDevice => 'Get Omi Device';

  @override
  String get wearableAiCompanion => 'Companheiro de IA vestível';

  @override
  String get loadingMemories => 'Carregando memórias...';

  @override
  String get allMemories => 'Todas as memórias';

  @override
  String get aboutYou => 'Sobre você';

  @override
  String get manual => 'Manual';

  @override
  String get loadingYourMemories => 'Carregando suas memórias...';

  @override
  String get createYourFirstMemory => 'Crie sua primeira memória para começar';

  @override
  String get tryAdjustingFilter => 'Tente ajustar sua pesquisa ou filtro';

  @override
  String get whatWouldYouLikeToRemember => 'O que você gostaria de lembrar?';

  @override
  String get category => 'Categoria';

  @override
  String get public => 'Público';

  @override
  String get failedToSaveCheckConnection => 'Falha ao salvar. Verifique sua conexão.';

  @override
  String get createMemory => 'Criar memória';

  @override
  String get deleteMemoryConfirmation =>
      'Tem certeza de que deseja excluir esta memória? Esta ação não pode ser desfeita.';

  @override
  String get makePrivate => 'Tornar privado';

  @override
  String get organizeAndControlMemories => 'Organize e controle suas memórias';

  @override
  String get total => 'Total';

  @override
  String get makeAllMemoriesPrivate => 'Tornar todas as memórias privadas';

  @override
  String get setAllMemoriesToPrivate => 'Definir todas as memórias como privadas';

  @override
  String get makeAllMemoriesPublic => 'Tornar todas as memórias públicas';

  @override
  String get setAllMemoriesToPublic => 'Definir todas as memórias como públicas';

  @override
  String get permanentlyRemoveAllMemories => 'Remover permanentemente todas as memórias do Omi';

  @override
  String get allMemoriesAreNowPrivate => 'Todas as memórias agora são privadas';

  @override
  String get allMemoriesAreNowPublic => 'Todas as memórias agora são públicas';

  @override
  String get clearOmisMemory => 'Limpar memória do Omi';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Tem certeza de que deseja limpar a memória do Omi? Esta ação não pode ser desfeita e excluirá permanentemente todas as $count memórias.';
  }

  @override
  String get omisMemoryCleared => 'A memória do Omi sobre você foi limpa';

  @override
  String get welcomeToOmi => 'Bem-vindo ao Omi';

  @override
  String get continueWithApple => 'Continuar com Apple';

  @override
  String get continueWithGoogle => 'Continuar com Google';

  @override
  String get byContinuingYouAgree => 'Ao continuar, você concorda com nossos ';

  @override
  String get termsOfService => 'Termos de serviço';

  @override
  String get and => ' e ';

  @override
  String get dataAndPrivacy => 'Dados e privacidade';

  @override
  String get secureAuthViaAppleId => 'Autenticação segura via Apple ID';

  @override
  String get secureAuthViaGoogleAccount => 'Autenticação segura via conta Google';

  @override
  String get whatWeCollect => 'O que coletamos';

  @override
  String get dataCollectionMessage =>
      'Ao continuar, suas conversas, gravações e informações pessoais serão armazenadas com segurança em nossos servidores para fornecer insights alimentados por IA e habilitar todos os recursos do aplicativo.';

  @override
  String get dataProtection => 'Proteção de dados';

  @override
  String get yourDataIsProtected => 'Seus dados são protegidos e regidos por nossa ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'Por favor, selecione o seu idioma principal';

  @override
  String get chooseYourLanguage => 'Escolha o seu idioma';

  @override
  String get selectPreferredLanguageForBestExperience =>
      'Selecione o seu idioma preferido para a melhor experiência Omi';

  @override
  String get searchLanguages => 'Pesquisar idiomas...';

  @override
  String get selectALanguage => 'Selecione um idioma';

  @override
  String get tryDifferentSearchTerm => 'Tente um termo de pesquisa diferente';

  @override
  String get pleaseEnterYourName => 'Por favor, insira o seu nome';

  @override
  String get nameMustBeAtLeast2Characters => 'O nome deve ter pelo menos 2 caracteres';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'Diga-nos como gostaria de ser chamado. Isso ajuda a personalizar sua experiência Omi.';

  @override
  String charactersCount(int count) {
    return '$count caracteres';
  }

  @override
  String get enableFeaturesForBestExperience => 'Ative recursos para a melhor experiência Omi no seu dispositivo.';

  @override
  String get microphoneAccess => 'Acesso ao Microfone';

  @override
  String get recordAudioConversations => 'Gravar conversas de áudio';

  @override
  String get microphoneAccessDescription =>
      'Omi precisa de acesso ao microfone para gravar suas conversas e fornecer transcrições.';

  @override
  String get screenRecording => 'Gravação de Tela';

  @override
  String get captureSystemAudioFromMeetings => 'Capturar áudio do sistema de reuniões';

  @override
  String get screenRecordingDescription =>
      'Omi precisa de permissão de gravação de tela para capturar o áudio do sistema de suas reuniões baseadas no navegador.';

  @override
  String get accessibility => 'Acessibilidade';

  @override
  String get detectBrowserBasedMeetings => 'Detectar reuniões baseadas no navegador';

  @override
  String get accessibilityDescription =>
      'Omi precisa de permissão de acessibilidade para detectar quando você participa de reuniões do Zoom, Meet ou Teams no seu navegador.';

  @override
  String get pleaseWait => 'Por favor, aguarde...';

  @override
  String get joinTheCommunity => 'Junte-se à comunidade!';

  @override
  String get loadingProfile => 'Carregando perfil...';

  @override
  String get profileSettings => 'Configurações do perfil';

  @override
  String get noEmailSet => 'Nenhum e-mail definido';

  @override
  String get userIdCopiedToClipboard => 'ID do usuário copiado';

  @override
  String get yourInformation => 'Suas Informações';

  @override
  String get setYourName => 'Definir seu nome';

  @override
  String get changeYourName => 'Alterar seu nome';

  @override
  String get manageYourOmiPersona => 'Gerencie sua persona Omi';

  @override
  String get voiceAndPeople => 'Voz e Pessoas';

  @override
  String get teachOmiYourVoice => 'Ensine à Omi sua voz';

  @override
  String get tellOmiWhoSaidIt => 'Diga à Omi quem disse 🗣️';

  @override
  String get payment => 'Pagamento';

  @override
  String get addOrChangeYourPaymentMethod => 'Adicionar ou alterar método de pagamento';

  @override
  String get preferences => 'Preferências';

  @override
  String get helpImproveOmiBySharing => 'Ajude a melhorar o Omi compartilhando dados de análise anonimizados';

  @override
  String get deleteAccount => 'Excluir Conta';

  @override
  String get deleteYourAccountAndAllData => 'Excluir sua conta e todos os dados';

  @override
  String get clearLogs => 'Limpar registos';

  @override
  String get debugLogsCleared => 'Logs de depuração limpos';

  @override
  String get exportConversations => 'Exportar conversas';

  @override
  String get exportAllConversationsToJson => 'Exporte todas as suas conversas para um ficheiro JSON.';

  @override
  String get conversationsExportStarted =>
      'Exportação de conversas iniciada. Isto pode demorar alguns segundos, por favor aguarde.';

  @override
  String get mcpDescription =>
      'Para conectar Omi com outras aplicações para ler, pesquisar e gerir as suas memórias e conversas. Crie uma chave para começar.';

  @override
  String get apiKeys => 'Chaves API';

  @override
  String errorLabel(String error) {
    return 'Erro: $error';
  }

  @override
  String get noApiKeysFound => 'Nenhuma chave API encontrada. Crie uma para começar.';

  @override
  String get advancedSettings => 'Configurações avançadas';

  @override
  String get triggersWhenNewConversationCreated => 'Dispara quando uma nova conversa é criada.';

  @override
  String get triggersWhenNewTranscriptReceived => 'Dispara quando uma nova transcrição é recebida.';

  @override
  String get realtimeAudioBytes => 'Bytes de áudio em tempo real';

  @override
  String get triggersWhenAudioBytesReceived => 'Dispara quando bytes de áudio são recebidos.';

  @override
  String get everyXSeconds => 'A cada x segundos';

  @override
  String get triggersWhenDaySummaryGenerated => 'Dispara quando o resumo do dia é gerado.';

  @override
  String get tryLatestExperimentalFeatures =>
      'Experimente as mais recentes funcionalidades experimentais da equipa Omi.';

  @override
  String get transcriptionServiceDiagnosticStatus => 'Estado de diagnóstico do serviço de transcrição';

  @override
  String get enableDetailedDiagnosticMessages => 'Ativar mensagens de diagnóstico detalhadas do serviço de transcrição';

  @override
  String get autoCreateAndTagNewSpeakers => 'Criar e etiquetar automaticamente novos oradores';

  @override
  String get automaticallyCreateNewPerson =>
      'Criar automaticamente uma nova pessoa quando um nome é detetado na transcrição.';

  @override
  String get pilotFeatures => 'Funcionalidades piloto';

  @override
  String get pilotFeaturesDescription => 'Estas funcionalidades são testes e não há garantia de suporte.';

  @override
  String get suggestFollowUpQuestion => 'Sugerir pergunta de acompanhamento';

  @override
  String get saveSettings => 'Salvar Configurações';

  @override
  String get syncingDeveloperSettings => 'A sincronizar configurações do desenvolvedor...';

  @override
  String get summary => 'Resumo';

  @override
  String get auto => 'Automático';

  @override
  String get noSummaryForApp => 'Nenhum resumo disponível para este app. Tente outro app para melhores resultados.';

  @override
  String get tryAnotherApp => 'Experimentar outro aplicativo';

  @override
  String generatedBy(String appName) {
    return 'Gerado por $appName';
  }

  @override
  String get overview => 'Visão geral';

  @override
  String get otherAppResults => 'Resultados de outros aplicativos';

  @override
  String get unknownApp => 'App desconhecido';

  @override
  String get noSummaryAvailable => 'Nenhum resumo disponível';

  @override
  String get conversationNoSummaryYet => 'Esta conversa ainda não tem um resumo.';

  @override
  String get chooseSummarizationApp => 'Escolher aplicativo de resumo';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName definido como aplicativo de resumo padrão';
  }

  @override
  String get letOmiChooseAutomatically => 'Deixe o Omi escolher automaticamente o melhor aplicativo';

  @override
  String get deleteConversationConfirmation =>
      'Tem certeza de que deseja excluir esta conversa? Esta ação não pode ser desfeita.';

  @override
  String get conversationDeleted => 'Conversa excluída';

  @override
  String get generatingLink => 'Gerando link...';

  @override
  String get editConversation => 'Editar conversa';

  @override
  String get conversationLinkCopiedToClipboard => 'Link da conversa copiado para a área de transferência';

  @override
  String get conversationTranscriptCopiedToClipboard => 'Transcrição da conversa copiada para a área de transferência';

  @override
  String get editConversationDialogTitle => 'Editar Conversa';

  @override
  String get changeTheConversationTitle => 'Alterar o título da conversa';

  @override
  String get conversationTitle => 'Título da Conversa';

  @override
  String get enterConversationTitle => 'Digite o título da conversa...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'Título da conversa atualizado com sucesso';

  @override
  String get failedToUpdateConversationTitle => 'Falha ao atualizar o título da conversa';

  @override
  String get errorUpdatingConversationTitle => 'Erro ao atualizar o título da conversa';

  @override
  String get settingUp => 'Configurando...';

  @override
  String get startYourFirstRecording => 'Inicie sua primeira gravação';

  @override
  String get preparingSystemAudioCapture => 'Preparando captura de áudio do sistema';

  @override
  String get clickTheButtonToCaptureAudio =>
      'Clique no botão para capturar áudio para transcrições ao vivo, insights de IA e salvamento automático.';

  @override
  String get reconnecting => 'Reconectando...';

  @override
  String get recordingPaused => 'Gravação pausada';

  @override
  String get recordingActive => 'Gravação ativa';

  @override
  String get startRecording => 'Iniciar gravação';

  @override
  String resumingInCountdown(String countdown) {
    return 'Retomando em ${countdown}s...';
  }

  @override
  String get tapPlayToResume => 'Toque em reproduzir para retomar';

  @override
  String get listeningForAudio => 'Ouvindo áudio...';

  @override
  String get preparingAudioCapture => 'Preparando captura de áudio';

  @override
  String get clickToBeginRecording => 'Clique para iniciar a gravação';

  @override
  String get translated => 'traduzido';

  @override
  String get liveTranscript => 'Transcrição ao vivo';

  @override
  String segmentsSingular(String count) {
    return '$count segmento';
  }

  @override
  String segmentsPlural(String count) {
    return '$count segmentos';
  }

  @override
  String get startRecordingToSeeTranscript => 'Inicie a gravação para ver a transcrição ao vivo';

  @override
  String get paused => 'Pausado';

  @override
  String get initializing => 'Inicializando...';

  @override
  String get recording => 'Gravando';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'Microfone alterado. Retomando em ${countdown}s';
  }

  @override
  String get clickPlayToResumeOrStop => 'Clique em reproduzir para retomar ou parar para finalizar';

  @override
  String get settingUpSystemAudioCapture => 'Configurando captura de áudio do sistema';

  @override
  String get capturingAudioAndGeneratingTranscript => 'Capturando áudio e gerando transcrição';

  @override
  String get clickToBeginRecordingSystemAudio => 'Clique para iniciar a gravação de áudio do sistema';

  @override
  String get you => 'Você';

  @override
  String speakerWithId(String speakerId) {
    return 'Palestrante $speakerId';
  }

  @override
  String get translatedByOmi => 'traduzido por omi';

  @override
  String get backToConversations => 'Voltar para conversas';

  @override
  String get systemAudio => 'Sistema';

  @override
  String get mic => 'Microfone';

  @override
  String audioInputSetTo(String deviceName) {
    return 'Entrada de áudio definida para $deviceName';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'Erro ao alternar dispositivo de áudio: $error';
  }

  @override
  String get selectAudioInput => 'Selecionar entrada de áudio';

  @override
  String get loadingDevices => 'Carregando dispositivos...';

  @override
  String get settingsHeader => 'CONFIGURAÇÕES';

  @override
  String get plansAndBilling => 'Planos e Faturamento';

  @override
  String get calendarIntegration => 'Integração de Calendário';

  @override
  String get dailySummary => 'Resumo diário';

  @override
  String get developer => 'Desenvolvedor';

  @override
  String get about => 'Sobre';

  @override
  String get selectTime => 'Selecionar horário';

  @override
  String get accountGroup => 'Conta';

  @override
  String get signOutQuestion => 'Sair?';

  @override
  String get signOutConfirmation => 'Are you sure you want to sign out?';

  @override
  String get customVocabularyHeader => 'VOCABULÁRIO PERSONALIZADO';

  @override
  String get addWordsDescription => 'Adicione palavras que o Omi deve reconhecer durante a transcrição.';

  @override
  String get enterWordsHint => 'Digite palavras (separadas por vírgulas)';

  @override
  String get dailySummaryHeader => 'RESUMO DIÁRIO';

  @override
  String get dailySummaryTitle => 'Resumo Diário';

  @override
  String get dailySummaryDescription => 'Receba um resumo personalizado das conversas do dia como notificação.';

  @override
  String get deliveryTime => 'Horário de entrega';

  @override
  String get deliveryTimeDescription => 'Quando receber seu resumo diário';

  @override
  String get subscription => 'Assinatura';

  @override
  String get viewPlansAndUsage => 'Ver Planos e Uso';

  @override
  String get viewPlansDescription => 'Gerencie sua assinatura e veja estatísticas de uso';

  @override
  String get addOrChangePaymentMethod => 'Adicionar ou alterar método de pagamento';

  @override
  String get displayOptions => 'Opções de Exibição';

  @override
  String get showMeetingsInMenuBar => 'Mostrar Reuniões na Barra de Menu';

  @override
  String get displayUpcomingMeetingsDescription => 'Exibir reuniões futuras na barra de menu';

  @override
  String get showEventsWithoutParticipants => 'Mostrar Eventos Sem Participantes';

  @override
  String get includePersonalEventsDescription => 'Incluir eventos pessoais sem participantes';

  @override
  String get upcomingMeetings => 'Próximas reuniões';

  @override
  String get checkingNext7Days => 'Verificando os próximos 7 dias';

  @override
  String get shortcuts => 'Atalhos';

  @override
  String get shortcutChangeInstruction => 'Clique em um atalho para alterá-lo. Pressione Escape para cancelar.';

  @override
  String get configurePersonaDescription => 'Configure sua persona de IA';

  @override
  String get configureSTTProvider => 'Configurar provedor de STT';

  @override
  String get setConversationEndDescription => 'Defina quando as conversas terminam automaticamente';

  @override
  String get importDataDescription => 'Importar dados de outras fontes';

  @override
  String get exportConversationsDescription => 'Exportar conversas para JSON';

  @override
  String get exportingConversations => 'Exportando conversas...';

  @override
  String get clearNodesDescription => 'Limpar todos os nós e conexões';

  @override
  String get deleteKnowledgeGraphQuestion => 'Excluir Grafo de Conhecimento?';

  @override
  String get deleteKnowledgeGraphWarning =>
      'Isso excluirá todos os dados derivados do grafo de conhecimento. Suas memórias originais permanecem seguras.';

  @override
  String get connectOmiWithAI => 'Conecte Omi com assistentes de IA';

  @override
  String get noAPIKeys => 'Sem chaves de API. Crie uma para começar.';

  @override
  String get autoCreateWhenDetected => 'Criar automaticamente quando o nome for detectado';

  @override
  String get trackPersonalGoals => 'Acompanhar metas pessoais na página inicial';

  @override
  String get dailyReflectionDescription =>
      'Receba um lembrete às 21h para refletir sobre seu dia e capturar seus pensamentos.';

  @override
  String get endpointURL => 'URL do Endpoint';

  @override
  String get links => 'Links';

  @override
  String get discordMemberCount => 'Mais de 8000 membros no Discord';

  @override
  String get userInformation => 'Informações do Usuário';

  @override
  String get capabilities => 'Capacidades';

  @override
  String get previewScreenshots => 'Pré-visualização de capturas';

  @override
  String get holdOnPreparingForm => 'Aguarde, estamos preparando o formulário para você';

  @override
  String get bySubmittingYouAgreeToOmi => 'Ao enviar, você concorda com os ';

  @override
  String get termsAndPrivacyPolicy => 'Termos e Política de Privacidade';

  @override
  String get helpsDiagnoseIssuesAutoDeletes => 'Ajuda a diagnosticar problemas. Eliminado automaticamente após 3 dias.';

  @override
  String get manageYourApp => 'Gerir a sua aplicação';

  @override
  String get updatingYourApp => 'A atualizar a sua aplicação';

  @override
  String get fetchingYourAppDetails => 'A obter detalhes da aplicação';

  @override
  String get updateAppQuestion => 'Atualizar aplicação?';

  @override
  String get updateAppConfirmation =>
      'Tem a certeza de que pretende atualizar a sua aplicação? As alterações serão refletidas após revisão pela nossa equipa.';

  @override
  String get updateApp => 'Atualizar aplicação';

  @override
  String get createAndSubmitNewApp => 'Criar e enviar uma nova aplicação';

  @override
  String appsCount(String count) {
    return 'Aplicações ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'Aplicações privadas ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'Aplicações públicas ($count)';
  }

  @override
  String get newVersionAvailable => 'Nova versão disponível  🎉';

  @override
  String get no => 'Não';

  @override
  String get subscriptionCancelledSuccessfully =>
      'Assinatura cancelada com sucesso. Permanecerá ativa até o final do período de faturamento atual.';

  @override
  String get failedToCancelSubscription => 'Falha ao cancelar a assinatura. Por favor, tente novamente.';

  @override
  String get invalidPaymentUrl => 'URL de pagamento inválido';

  @override
  String get permissionsAndTriggers => 'Permissões e gatilhos';

  @override
  String get chatFeatures => 'Recursos de chat';

  @override
  String get uninstall => 'Desinstalar';

  @override
  String get installs => 'INSTALAÇÕES';

  @override
  String get priceLabel => 'PREÇO';

  @override
  String get updatedLabel => 'ATUALIZADO';

  @override
  String get createdLabel => 'CRIADO';

  @override
  String get featuredLabel => 'DESTAQUE';

  @override
  String get cancelSubscriptionQuestion => 'Cancelar assinatura?';

  @override
  String get cancelSubscriptionConfirmation =>
      'Tem certeza de que deseja cancelar sua assinatura? Você continuará tendo acesso até o final do período de faturamento atual.';

  @override
  String get cancelSubscriptionButton => 'Cancelar assinatura';

  @override
  String get cancelling => 'Cancelando...';

  @override
  String get betaTesterMessage =>
      'Você é um testador beta deste aplicativo. Ainda não é público. Será público após aprovação.';

  @override
  String get appUnderReviewMessage =>
      'Seu aplicativo está em análise e visível apenas para você. Será público após aprovação.';

  @override
  String get appRejectedMessage => 'Seu aplicativo foi rejeitado. Atualize os detalhes e envie novamente para análise.';

  @override
  String get invalidIntegrationUrl => 'URL de integração inválida';

  @override
  String get tapToComplete => 'Toque para concluir';

  @override
  String get invalidSetupInstructionsUrl => 'URL das instruções de configuração inválida';

  @override
  String get pushToTalk => 'Pressione para falar';

  @override
  String get summaryPrompt => 'Prompt de resumo';

  @override
  String get pleaseSelectARating => 'Por favor, selecione uma avaliação';

  @override
  String get reviewAddedSuccessfully => 'Resenha adicionada com sucesso 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'Resenha atualizada com sucesso 🚀';

  @override
  String get failedToSubmitReview => 'Falha ao enviar resenha. Por favor, tente novamente.';

  @override
  String get addYourReview => 'Adicione sua avaliação';

  @override
  String get editYourReview => 'Edite sua avaliação';

  @override
  String get writeAReviewOptional => 'Escreva uma avaliação (opcional)';

  @override
  String get submitReview => 'Enviar avaliação';

  @override
  String get updateReview => 'Atualizar avaliação';

  @override
  String get yourReview => 'Sua avaliação';

  @override
  String get anonymousUser => 'Usuário anônimo';

  @override
  String get issueActivatingApp => 'Houve um problema ao ativar este aplicativo. Por favor, tente novamente.';

  @override
  String get dataAccessNoticeDescription =>
      'Este aplicativo acessará seus dados. Omi AI não é responsável por como seus dados são usados, modificados ou excluídos por este aplicativo';

  @override
  String get copyUrl => 'Copiar URL';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => 'Seg';

  @override
  String get weekdayTue => 'Ter';

  @override
  String get weekdayWed => 'Qua';

  @override
  String get weekdayThu => 'Qui';

  @override
  String get weekdayFri => 'Sex';

  @override
  String get weekdaySat => 'Sáb';

  @override
  String get weekdaySun => 'Dom';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return 'Integração com $serviceName em breve';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'Já exportado para $platform';
  }

  @override
  String get anotherPlatform => 'outra plataforma';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'Por favor, autentique-se com $serviceName em Configurações > Integrações de tarefas';
  }

  @override
  String addingToService(String serviceName) {
    return 'Adicionando ao $serviceName...';
  }

  @override
  String addedToService(String serviceName) {
    return 'Adicionado ao $serviceName';
  }

  @override
  String failedToAddToService(String serviceName) {
    return 'Falha ao adicionar ao $serviceName';
  }

  @override
  String get permissionDeniedForAppleReminders => 'Permissão negada para Apple Reminders';

  @override
  String failedToCreateApiKey(String error) {
    return 'Falha ao criar chave API do provedor: $error';
  }

  @override
  String get createAKey => 'Criar uma chave';

  @override
  String get apiKeyRevokedSuccessfully => 'Chave API revogada com sucesso';

  @override
  String failedToRevokeApiKey(String error) {
    return 'Falha ao revogar chave API: $error';
  }

  @override
  String get omiApiKeys => 'Chaves API do Omi';

  @override
  String get apiKeysDescription =>
      'As chaves API são usadas para autenticação quando seu aplicativo se comunica com o servidor OMI. Elas permitem que seu aplicativo crie memórias e acesse outros serviços do OMI com segurança.';

  @override
  String get aboutOmiApiKeys => 'Sobre as chaves API do Omi';

  @override
  String get yourNewKey => 'Sua nova chave:';

  @override
  String get copyToClipboard => 'Copiar para a área de transferência';

  @override
  String get pleaseCopyKeyNow => 'Por favor, copie agora e anote em um lugar seguro. ';

  @override
  String get willNotSeeAgain => 'Você não poderá vê-la novamente.';

  @override
  String get revokeKey => 'Revogar chave';

  @override
  String get revokeApiKeyQuestion => 'Revogar chave API?';

  @override
  String get revokeApiKeyWarning =>
      'Esta ação não pode ser desfeita. Quaisquer aplicativos que usem esta chave não poderão mais acessar a API.';

  @override
  String get revoke => 'Revogar';

  @override
  String get whatWouldYouLikeToCreate => 'O que você gostaria de criar?';

  @override
  String get createAnApp => 'Criar um aplicativo';

  @override
  String get createAndShareYourApp => 'Crie e compartilhe seu aplicativo';

  @override
  String get createMyClone => 'Criar meu clone';

  @override
  String get createYourDigitalClone => 'Crie seu clone digital';

  @override
  String get itemApp => 'Aplicativo';

  @override
  String get itemPersona => 'Persona';

  @override
  String keepItemPublic(String item) {
    return 'Manter $item público';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return 'Tornar $item público?';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return 'Tornar $item privado?';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'Se você tornar $item público, ele pode ser usado por todos';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'Se você tornar $item privado agora, ele deixará de funcionar para todos e será visível apenas para você';
  }

  @override
  String get manageApp => 'Gerenciar aplicativo';

  @override
  String get updatePersonaDetails => 'Atualizar detalhes da persona';

  @override
  String deleteItemTitle(String item) {
    return 'Excluir $item';
  }

  @override
  String deleteItemQuestion(String item) {
    return 'Excluir $item?';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'Tem certeza de que deseja excluir este $item? Esta ação não pode ser desfeita.';
  }

  @override
  String get revokeKeyQuestion => 'Revogar chave?';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'Tem certeza de que deseja revogar a chave \"$keyName\"? Esta ação não pode ser desfeita.';
  }

  @override
  String get createNewKey => 'Criar nova chave';

  @override
  String get keyNameHint => 'ex.: Claude Desktop';

  @override
  String get pleaseEnterAName => 'Por favor, insira um nome.';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'Falha ao criar chave: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'Falha ao criar chave. Por favor, tente novamente.';

  @override
  String get keyCreated => 'Chave criada';

  @override
  String get keyCreatedMessage =>
      'Sua nova chave foi criada. Por favor, copie-a agora. Você não poderá vê-la novamente.';

  @override
  String get keyWord => 'Chave';

  @override
  String get externalAppAccess => 'Acesso de aplicativos externos';

  @override
  String get externalAppAccessDescription =>
      'Os seguintes aplicativos instalados têm integrações externas e podem acessar seus dados, como conversas e memórias.';

  @override
  String get noExternalAppsHaveAccess => 'Nenhum aplicativo externo tem acesso aos seus dados.';

  @override
  String get maximumSecurityE2ee => 'Segurança máxima (E2EE)';

  @override
  String get e2eeDescription =>
      'A criptografia de ponta a ponta é o padrão ouro para privacidade. Quando ativada, seus dados são criptografados no seu dispositivo antes de serem enviados para nossos servidores. Isso significa que ninguém, nem mesmo a Omi, pode acessar seu conteúdo.';

  @override
  String get importantTradeoffs => 'Compromissos importantes:';

  @override
  String get e2eeTradeoff1 => '• Alguns recursos como integrações de aplicativos externos podem ser desativados.';

  @override
  String get e2eeTradeoff2 => '• Se você perder sua senha, seus dados não poderão ser recuperados.';

  @override
  String get featureComingSoon => 'Este recurso estará disponível em breve!';

  @override
  String get migrationInProgressMessage =>
      'Migração em andamento. Você não pode alterar o nível de proteção até que seja concluída.';

  @override
  String get migrationFailed => 'Falha na migração';

  @override
  String migratingFromTo(String source, String target) {
    return 'Migrando de $source para $target';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total objetos';
  }

  @override
  String get secureEncryption => 'Criptografia segura';

  @override
  String get secureEncryptionDescription =>
      'Seus dados são criptografados com uma chave única para você em nossos servidores, hospedados no Google Cloud. Isso significa que seu conteúdo bruto é inacessível para qualquer pessoa, incluindo funcionários da Omi ou Google, diretamente do banco de dados.';

  @override
  String get endToEndEncryption => 'Criptografia de ponta a ponta';

  @override
  String get e2eeCardDescription =>
      'Ative para máxima segurança onde apenas você pode acessar seus dados. Toque para saber mais.';

  @override
  String get dataAlwaysEncrypted =>
      'Independentemente do nível, seus dados estão sempre criptografados em repouso e em trânsito.';

  @override
  String get readOnlyScope => 'Somente leitura';

  @override
  String get fullAccessScope => 'Acesso total';

  @override
  String get readScope => 'Leitura';

  @override
  String get writeScope => 'Escrita';

  @override
  String get apiKeyCreated => 'Chave API criada!';

  @override
  String get saveKeyWarning => 'Salve esta chave agora! Você não poderá vê-la novamente.';

  @override
  String get yourApiKey => 'SUA CHAVE API';

  @override
  String get tapToCopy => 'Toque para copiar';

  @override
  String get copyKey => 'Copiar chave';

  @override
  String get createApiKey => 'Criar chave API';

  @override
  String get accessDataProgrammatically => 'Acesse seus dados programaticamente';

  @override
  String get keyNameLabel => 'NOME DA CHAVE';

  @override
  String get keyNamePlaceholder => 'ex., Minha integração';

  @override
  String get permissionsLabel => 'PERMISSÕES';

  @override
  String get permissionsInfoNote => 'R = Leitura, W = Escrita. Padrão somente leitura se nada for selecionado.';

  @override
  String get developerApi => 'API de desenvolvedor';

  @override
  String get createAKeyToGetStarted => 'Crie uma chave para começar';

  @override
  String errorWithMessage(String error) {
    return 'Erro: $error';
  }

  @override
  String get omiTraining => 'Treinamento Omi';

  @override
  String get trainingDataProgram => 'Programa de dados de treinamento';

  @override
  String get getOmiUnlimitedFree =>
      'Obtenha Omi Ilimitado grátis contribuindo com seus dados para treinar modelos de IA.';

  @override
  String get trainingDataBullets =>
      '• Seus dados ajudam a melhorar os modelos de IA\n• Apenas dados não sensíveis são compartilhados\n• Processo totalmente transparente';

  @override
  String get learnMoreAtOmiTraining => 'Saiba mais em omi.me/training';

  @override
  String get agreeToContributeData => 'Eu entendo e concordo em contribuir com meus dados para treinamento de IA';

  @override
  String get submitRequest => 'Enviar solicitação';

  @override
  String get thankYouRequestUnderReview =>
      'Obrigado! Sua solicitação está em análise. Notificaremos você após a aprovação.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'Seu plano permanecerá ativo até $date. Depois disso, você perderá o acesso aos recursos ilimitados. Tem certeza?';
  }

  @override
  String get confirmCancellation => 'Confirmar cancelamento';

  @override
  String get keepMyPlan => 'Manter meu plano';

  @override
  String get subscriptionSetToCancel => 'Sua assinatura está configurada para ser cancelada no final do período.';

  @override
  String get switchedToOnDevice => 'Alterado para transcrição no dispositivo';

  @override
  String get couldNotSwitchToFreePlan => 'Não foi possível mudar para o plano gratuito. Por favor, tente novamente.';

  @override
  String get couldNotLoadPlans => 'Não foi possível carregar os planos disponíveis. Por favor, tente novamente.';

  @override
  String get selectedPlanNotAvailable => 'O plano selecionado não está disponível. Por favor, tente novamente.';

  @override
  String get upgradeToAnnualPlan => 'Atualizar para plano anual';

  @override
  String get importantBillingInfo => 'Informações importantes de cobrança:';

  @override
  String get monthlyPlanContinues => 'Seu plano mensal atual continuará até o final do período de cobrança';

  @override
  String get paymentMethodCharged =>
      'Seu método de pagamento existente será cobrado automaticamente quando seu plano mensal terminar';

  @override
  String get annualSubscriptionStarts => 'Sua assinatura anual de 12 meses começará automaticamente após a cobrança';

  @override
  String get thirteenMonthsCoverage => 'Você terá 13 meses de cobertura no total (mês atual + 12 meses anuais)';

  @override
  String get confirmUpgrade => 'Confirmar atualização';

  @override
  String get confirmPlanChange => 'Confirmar mudança de plano';

  @override
  String get confirmAndProceed => 'Confirmar e prosseguir';

  @override
  String get upgradeScheduled => 'Atualização agendada';

  @override
  String get changePlan => 'Alterar plano';

  @override
  String get upgradeAlreadyScheduled => 'Sua atualização para o plano anual já está agendada';

  @override
  String get youAreOnUnlimitedPlan => 'Você está no plano Ilimitado.';

  @override
  String get yourOmiUnleashed => 'Seu Omi, liberado. Torne-se ilimitado para possibilidades infinitas.';

  @override
  String planEndedOn(String date) {
    return 'Seu plano terminou em $date.\\nAssine novamente agora - você será cobrado imediatamente por um novo período de cobrança.';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'Seu plano está configurado para cancelar em $date.\\nAssine novamente agora para manter seus benefícios - sem cobrança até $date.';
  }

  @override
  String get annualPlanStartsAutomatically =>
      'Seu plano anual começará automaticamente quando seu plano mensal terminar.';

  @override
  String planRenewsOn(String date) {
    return 'Seu plano é renovado em $date.';
  }

  @override
  String get unlimitedConversations => 'Conversas ilimitadas';

  @override
  String get askOmiAnything => 'Pergunte ao Omi qualquer coisa sobre sua vida';

  @override
  String get unlockOmiInfiniteMemory => 'Desbloqueie a memória infinita do Omi';

  @override
  String get youreOnAnnualPlan => 'Você está no plano anual';

  @override
  String get alreadyBestValuePlan => 'Você já tem o plano de melhor custo-benefício. Nenhuma alteração necessária.';

  @override
  String get unableToLoadPlans => 'Não foi possível carregar os planos';

  @override
  String get checkConnectionTryAgain => 'Verifique sua conexão e tente novamente';

  @override
  String get useFreePlan => 'Usar plano gratuito';

  @override
  String get continueText => 'Continuar';

  @override
  String get resubscribe => 'Assinar novamente';

  @override
  String get couldNotOpenPaymentSettings =>
      'Não foi possível abrir as configurações de pagamento. Por favor, tente novamente.';

  @override
  String get managePaymentMethod => 'Gerenciar método de pagamento';

  @override
  String get cancelSubscription => 'Cancelar assinatura';

  @override
  String endsOnDate(String date) {
    return 'Termina em $date';
  }

  @override
  String get active => 'Ativo';

  @override
  String get freePlan => 'Plano gratuito';

  @override
  String get configure => 'Configurar';

  @override
  String get privacyInformation => 'Informações de privacidade';

  @override
  String get yourPrivacyMattersToUs => 'Sua privacidade é importante para nós';

  @override
  String get privacyIntroText =>
      'Na Omi, levamos sua privacidade muito a sério. Queremos ser transparentes sobre os dados que coletamos e como os usamos. Aqui está o que você precisa saber:';

  @override
  String get whatWeTrack => 'O que rastreamos';

  @override
  String get anonymityAndPrivacy => 'Anonimato e privacidade';

  @override
  String get optInAndOptOutOptions => 'Opções de aceitar e recusar';

  @override
  String get ourCommitment => 'Nosso compromisso';

  @override
  String get commitmentText =>
      'Estamos comprometidos em usar os dados que coletamos apenas para tornar o Omi um produto melhor para você. Sua privacidade e confiança são primordiais para nós.';

  @override
  String get thankYouText =>
      'Obrigado por ser um usuário valioso do Omi. Se você tiver alguma dúvida ou preocupação, entre em contato conosco em team@basedhardware.com.';

  @override
  String get wifiSyncSettings => 'Configurações de sincronização WiFi';

  @override
  String get enterHotspotCredentials => 'Insira as credenciais do ponto de acesso do seu telefone';

  @override
  String get wifiSyncUsesHotspot =>
      'A sincronização WiFi usa seu telefone como ponto de acesso. Encontre o nome e a senha em Ajustes > Ponto de Acesso Pessoal.';

  @override
  String get hotspotNameSsid => 'Nome do ponto de acesso (SSID)';

  @override
  String get exampleIphoneHotspot => 'ex. Ponto de Acesso iPhone';

  @override
  String get password => 'Senha';

  @override
  String get enterHotspotPassword => 'Insira a senha do ponto de acesso';

  @override
  String get saveCredentials => 'Salvar credenciais';

  @override
  String get clearCredentials => 'Limpar credenciais';

  @override
  String get pleaseEnterHotspotName => 'Por favor, insira um nome de ponto de acesso';

  @override
  String get wifiCredentialsSaved => 'Credenciais WiFi salvas';

  @override
  String get wifiCredentialsCleared => 'Credenciais WiFi limpas';

  @override
  String summaryGeneratedForDate(String date) {
    return 'Resumo gerado para $date';
  }

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'Falha ao gerar resumo. Certifique-se de ter conversas para esse dia.';

  @override
  String get summaryNotFound => 'Resumo não encontrado';

  @override
  String get yourDaysJourney => 'Sua jornada do dia';

  @override
  String get highlights => 'Destaques';

  @override
  String get unresolvedQuestions => 'Perguntas não resolvidas';

  @override
  String get decisions => 'Decisões';

  @override
  String get learnings => 'Aprendizados';

  @override
  String get autoDeletesAfterThreeDays => 'Excluído automaticamente após 3 dias.';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'Grafo de conhecimento excluído com sucesso';

  @override
  String get exportStartedMayTakeFewSeconds => 'Exportação iniciada. Isso pode levar alguns segundos...';

  @override
  String get knowledgeGraphDeleteDescription =>
      'Isso excluirá todos os dados derivados do grafo de conhecimento (nós e conexões). Suas memórias originais permanecerão seguras. O grafo será reconstruído ao longo do tempo ou na próxima solicitação.';

  @override
  String get configureDailySummaryDigest => 'Configure seu resumo diário de tarefas';

  @override
  String accessesDataTypes(String dataTypes) {
    return 'Acessa $dataTypes';
  }

  @override
  String triggeredByType(String triggerType) {
    return 'acionado por $triggerType';
  }

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription e é $triggerDescription.';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return 'É $triggerDescription.';
  }

  @override
  String get noSpecificDataAccessConfigured => 'Nenhum acesso a dados específico configurado.';

  @override
  String get basicPlanDescription => '1.200 minutos premium + ilimitado no dispositivo';

  @override
  String get minutes => 'minutos';

  @override
  String get omiHas => 'Omi tem:';

  @override
  String get premiumMinutesUsed => 'Minutos premium utilizados.';

  @override
  String get setupOnDevice => 'Configurar no dispositivo';

  @override
  String get forUnlimitedFreeTranscription => 'para transcrição gratuita ilimitada.';

  @override
  String premiumMinsLeft(int count) {
    return '$count minutos premium restantes.';
  }

  @override
  String get alwaysAvailable => 'sempre disponível.';

  @override
  String get importHistory => 'Histórico de importação';

  @override
  String get noImportsYet => 'Nenhuma importação ainda';

  @override
  String get selectZipFileToImport => 'Selecione o arquivo .zip para importar!';

  @override
  String get otherDevicesComingSoon => 'Outros dispositivos em breve';

  @override
  String get deleteAllLimitlessConversations => 'Excluir todas as conversas do Limitless?';

  @override
  String get deleteAllLimitlessWarning =>
      'Isso excluirá permanentemente todas as conversas importadas do Limitless. Esta ação não pode ser desfeita.';

  @override
  String deletedLimitlessConversations(int count) {
    return 'Excluídas $count conversas do Limitless';
  }

  @override
  String get failedToDeleteConversations => 'Falha ao excluir conversas';

  @override
  String get deleteImportedData => 'Excluir dados importados';

  @override
  String get statusPending => 'Pendente';

  @override
  String get statusProcessing => 'Processando';

  @override
  String get statusCompleted => 'Concluído';

  @override
  String get statusFailed => 'Falhou';

  @override
  String nConversations(int count) {
    return '$count conversas';
  }

  @override
  String get pleaseEnterName => 'Por favor, insira um nome';

  @override
  String get nameMustBeBetweenCharacters => 'O nome deve ter entre 2 e 40 caracteres';

  @override
  String get deleteSampleQuestion => 'Excluir amostra?';

  @override
  String deleteSampleConfirmation(String name) {
    return 'Tem certeza de que deseja excluir a amostra de $name?';
  }

  @override
  String get confirmDeletion => 'Confirmar exclusão';

  @override
  String deletePersonConfirmation(String name) {
    return 'Tem certeza de que deseja excluir $name? Isso também removerá todas as amostras de fala associadas.';
  }

  @override
  String get howItWorksTitle => 'Como funciona?';

  @override
  String get howPeopleWorks =>
      'Depois que uma pessoa é criada, você pode ir para a transcrição de uma conversa e atribuir os segmentos correspondentes, assim o Omi também poderá reconhecer a fala dela!';

  @override
  String get tapToDelete => 'Toque para excluir';

  @override
  String get newTag => 'NOVO';

  @override
  String get needHelpChatWithUs => 'Precisa de ajuda? Fale conosco';

  @override
  String get localStorageEnabled => 'Armazenamento local ativado';

  @override
  String get localStorageDisabled => 'Armazenamento local desativado';

  @override
  String failedToUpdateSettings(String error) {
    return 'Falha ao atualizar configurações: $error';
  }

  @override
  String get privacyNotice => 'Aviso de privacidade';

  @override
  String get recordingsMayCaptureOthers =>
      'As gravações podem capturar as vozes de outras pessoas. Certifique-se de ter o consentimento de todos os participantes antes de ativar.';

  @override
  String get enable => 'Ativar';

  @override
  String get storeAudioOnPhone => 'Store Audio on Phone';

  @override
  String get on => 'On';

  @override
  String get storeAudioDescription =>
      'Mantenha todas as gravações de áudio armazenadas localmente no seu telefone. Quando desativado, apenas uploads com falha são mantidos para economizar espaço.';

  @override
  String get enableLocalStorage => 'Ativar armazenamento local';

  @override
  String get cloudStorageEnabled => 'Armazenamento em nuvem ativado';

  @override
  String get cloudStorageDisabled => 'Armazenamento em nuvem desativado';

  @override
  String get enableCloudStorage => 'Ativar armazenamento em nuvem';

  @override
  String get storeAudioOnCloud => 'Store Audio on Cloud';

  @override
  String get cloudStorageDialogMessage =>
      'Suas gravações em tempo real serão armazenadas em armazenamento em nuvem privado enquanto você fala.';

  @override
  String get storeAudioCloudDescription =>
      'Armazene suas gravações em tempo real em armazenamento em nuvem privado enquanto você fala. O áudio é capturado e salvo com segurança em tempo real.';

  @override
  String get downloadingFirmware => 'Baixando Firmware';

  @override
  String get installingFirmware => 'Instalando Firmware';

  @override
  String get firmwareUpdateWarning =>
      'Não feche o aplicativo ou desligue o dispositivo. Isso pode danificar seu dispositivo.';

  @override
  String get firmwareUpdated => 'Firmware Atualizado';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'Por favor, reinicie seu $deviceName para concluir a atualização.';
  }

  @override
  String get yourDeviceIsUpToDate => 'Seu dispositivo está atualizado';

  @override
  String get currentVersion => 'Versão Atual';

  @override
  String get latestVersion => 'Versão Mais Recente';

  @override
  String get whatsNew => 'Novidades';

  @override
  String get installUpdate => 'Instalar Atualização';

  @override
  String get updateNow => 'Atualizar Agora';

  @override
  String get updateGuide => 'Guia de Atualização';

  @override
  String get checkingForUpdates => 'Verificando Atualizações';

  @override
  String get checkingFirmwareVersion => 'Verificando versão do firmware...';

  @override
  String get firmwareUpdate => 'Atualização de Firmware';

  @override
  String get payments => 'Pagamentos';

  @override
  String get connectPaymentMethodInfo =>
      'Conecte um método de pagamento abaixo para começar a receber pagamentos pelos seus aplicativos.';

  @override
  String get selectedPaymentMethod => 'Método de Pagamento Selecionado';

  @override
  String get availablePaymentMethods => 'Métodos de Pagamento Disponíveis';

  @override
  String get activeStatus => 'Ativo';

  @override
  String get connectedStatus => 'Conectado';

  @override
  String get notConnectedStatus => 'Não Conectado';

  @override
  String get setActive => 'Definir como Ativo';

  @override
  String get getPaidThroughStripe => 'Receba pagamentos pelas vendas dos seus aplicativos através do Stripe';

  @override
  String get monthlyPayouts => 'Pagamentos mensais';

  @override
  String get monthlyPayoutsDescription =>
      'Receba pagamentos mensais diretamente em sua conta quando atingir \$10 em ganhos';

  @override
  String get secureAndReliable => 'Seguro e confiável';

  @override
  String get stripeSecureDescription =>
      'O Stripe garante transferências seguras e pontuais das receitas do seu aplicativo';

  @override
  String get selectYourCountry => 'Selecione seu país';

  @override
  String get countrySelectionPermanent => 'A seleção do país é permanente e não pode ser alterada posteriormente.';

  @override
  String get byClickingConnectNow => 'Ao clicar em \"Conectar Agora\" você concorda com o';

  @override
  String get stripeConnectedAccountAgreement => 'Acordo de Conta Conectada do Stripe';

  @override
  String get errorConnectingToStripe => 'Erro ao conectar ao Stripe! Por favor, tente novamente mais tarde.';

  @override
  String get connectingYourStripeAccount => 'Conectando sua conta Stripe';

  @override
  String get stripeOnboardingInstructions =>
      'Por favor, complete o processo de integração do Stripe no seu navegador. Esta página será atualizada automaticamente após a conclusão.';

  @override
  String get failedTryAgain => 'Falhou? Tente Novamente';

  @override
  String get illDoItLater => 'Farei isso depois';

  @override
  String get successfullyConnected => 'Conectado com Sucesso!';

  @override
  String get stripeReadyForPayments =>
      'Sua conta Stripe está pronta para receber pagamentos. Você pode começar a ganhar com as vendas dos seus aplicativos imediatamente.';

  @override
  String get updateStripeDetails => 'Atualizar Detalhes do Stripe';

  @override
  String get errorUpdatingStripeDetails =>
      'Erro ao atualizar detalhes do Stripe! Por favor, tente novamente mais tarde.';

  @override
  String get updatePayPal => 'Atualizar PayPal';

  @override
  String get setUpPayPal => 'Configurar PayPal';

  @override
  String get updatePayPalAccountDetails => 'Atualize os detalhes da sua conta PayPal';

  @override
  String get connectPayPalToReceivePayments =>
      'Conecte sua conta PayPal para começar a receber pagamentos pelos seus aplicativos';

  @override
  String get paypalEmail => 'E-mail do PayPal';

  @override
  String get paypalMeLink => 'Link do PayPal.me';

  @override
  String get stripeRecommendation =>
      'Se o Stripe estiver disponível em seu país, recomendamos fortemente usá-lo para pagamentos mais rápidos e fáceis.';

  @override
  String get updatePayPalDetails => 'Atualizar Detalhes do PayPal';

  @override
  String get savePayPalDetails => 'Salvar Detalhes do PayPal';

  @override
  String get pleaseEnterPayPalEmail => 'Por favor, insira seu e-mail do PayPal';

  @override
  String get pleaseEnterPayPalMeLink => 'Por favor, insira seu link do PayPal.me';

  @override
  String get doNotIncludeHttpInLink => 'Não inclua http ou https ou www no link';

  @override
  String get pleaseEnterValidPayPalMeLink => 'Por favor, insira um link do PayPal.me válido';

  @override
  String get pleaseEnterValidEmail => 'Por favor, insira um endereço de e-mail válido';

  @override
  String get syncingYourRecordings => 'Sincronizando suas gravações';

  @override
  String get syncYourRecordings => 'Sincronizar suas gravações';

  @override
  String get syncNow => 'Sincronizar agora';

  @override
  String get error => 'Erro';

  @override
  String get speechSamples => 'Amostras de voz';

  @override
  String additionalSampleIndex(String index) {
    return 'Amostra adicional $index';
  }

  @override
  String durationSeconds(String seconds) {
    return 'Duração: $seconds segundos';
  }

  @override
  String get additionalSpeechSampleRemoved => 'Amostra de voz adicional removida';

  @override
  String get consentDataMessage =>
      'Ao continuar, todos os dados que você compartilha com este aplicativo (incluindo suas conversas, gravações e informações pessoais) serão armazenados com segurança em nossos servidores para fornecer insights baseados em IA e habilitar todos os recursos do aplicativo.';

  @override
  String get tasksEmptyStateMessage =>
      'As tarefas das suas conversas aparecerão aqui.\nToque em + para criar uma manualmente.';

  @override
  String get clearChatAction => 'Limpar conversa';

  @override
  String get enableApps => 'Ativar aplicativos';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => 'mostrar mais ↓';

  @override
  String get showLess => 'mostrar menos ↑';

  @override
  String get loadingYourRecording => 'Carregando sua gravação...';

  @override
  String get photoDiscardedMessage => 'Esta foto foi descartada pois não era significativa.';

  @override
  String get analyzing => 'Analisando...';

  @override
  String get searchCountries => 'Pesquisar países...';

  @override
  String get checkingAppleWatch => 'Verificando Apple Watch...';

  @override
  String get installOmiOnAppleWatch => 'Instale o Omi no seu\nApple Watch';

  @override
  String get installOmiOnAppleWatchDescription =>
      'Para usar seu Apple Watch com o Omi, você precisa primeiro instalar o aplicativo Omi no seu relógio.';

  @override
  String get openOmiOnAppleWatch => 'Abra o Omi no seu\nApple Watch';

  @override
  String get openOmiOnAppleWatchDescription =>
      'O aplicativo Omi está instalado no seu Apple Watch. Abra-o e toque em Iniciar para começar.';

  @override
  String get openWatchApp => 'Abrir app Watch';

  @override
  String get iveInstalledAndOpenedTheApp => 'Instalei e abri o aplicativo';

  @override
  String get unableToOpenWatchApp =>
      'Não foi possível abrir o app Apple Watch. Abra manualmente o app Watch no seu Apple Watch e instale o Omi na seção \"Apps Disponíveis\".';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch conectado com sucesso!';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch ainda não está acessível. Certifique-se de que o app Omi está aberto no seu relógio.';

  @override
  String errorCheckingConnection(String error) {
    return 'Erro ao verificar conexão: $error';
  }

  @override
  String get muted => 'Silenciado';

  @override
  String get processNow => 'Processar agora';

  @override
  String get finishedConversation => 'Conversa finalizada?';

  @override
  String get stopRecordingConfirmation => 'Tem certeza de que deseja parar a gravação e resumir a conversa agora?';

  @override
  String get conversationEndsManually => 'A conversa só terminará manualmente.';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'A conversa é resumida após $minutes minuto$suffix sem fala.';
  }

  @override
  String get dontAskAgain => 'Não perguntar novamente';

  @override
  String get waitingForTranscriptOrPhotos => 'Aguardando transcrição ou fotos...';

  @override
  String get noSummaryYet => 'Ainda sem resumo';

  @override
  String hints(String text) {
    return 'Dicas: $text';
  }

  @override
  String get testConversationPrompt => 'Testar prompt de conversa';

  @override
  String get prompt => 'Prompt';

  @override
  String get result => 'Resultado:';

  @override
  String get compareTranscripts => 'Comparar transcrições';

  @override
  String get notHelpful => 'Não foi útil';

  @override
  String get exportTasksWithOneTap => 'Exporte tarefas com um toque!';

  @override
  String get inProgress => 'Em andamento';

  @override
  String get photos => 'Fotos';

  @override
  String get rawData => 'Dados brutos';

  @override
  String get content => 'Conteúdo';

  @override
  String get noContentToDisplay => 'Nenhum conteúdo para exibir';

  @override
  String get noSummary => 'Sem resumo';

  @override
  String get updateOmiFirmware => 'Atualizar firmware do omi';

  @override
  String get anErrorOccurredTryAgain => 'Ocorreu um erro. Por favor, tente novamente.';

  @override
  String get welcomeBackSimple => 'Bem-vindo de volta';

  @override
  String get addVocabularyDescription => 'Adicione palavras que o Omi deve reconhecer durante a transcrição.';

  @override
  String get enterWordsCommaSeparated => 'Digite palavras (separadas por vírgula)';

  @override
  String get whenToReceiveDailySummary => 'Quando receber seu resumo diário';

  @override
  String get checkingNextSevenDays => 'Verificando os próximos 7 dias';

  @override
  String failedToDeleteError(String error) {
    return 'Falha ao excluir: $error';
  }

  @override
  String get developerApiKeys => 'Chaves de API do desenvolvedor';

  @override
  String get noApiKeysCreateOne => 'Sem chaves de API. Crie uma para começar.';

  @override
  String get commandRequired => '⌘ necessário';

  @override
  String get spaceKey => 'Espaço';

  @override
  String loadMoreRemaining(String count) {
    return 'Carregar mais ($count restantes)';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'Top $percentile% Usuário';
  }

  @override
  String get wrappedMinutes => 'minutos';

  @override
  String get wrappedConversations => 'conversas';

  @override
  String get wrappedDaysActive => 'dias ativos';

  @override
  String get wrappedYouTalkedAbout => 'Você falou sobre';

  @override
  String get wrappedActionItems => 'Tarefas';

  @override
  String get wrappedTasksCreated => 'tarefas criadas';

  @override
  String get wrappedCompleted => 'concluídas';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% taxa de conclusão';
  }

  @override
  String get wrappedYourTopDays => 'Seus melhores dias';

  @override
  String get wrappedBestMoments => 'Melhores momentos';

  @override
  String get wrappedMyBuddies => 'Meus amigos';

  @override
  String get wrappedCouldntStopTalkingAbout => 'Não parava de falar sobre';

  @override
  String get wrappedShow => 'SÉRIE';

  @override
  String get wrappedMovie => 'FILME';

  @override
  String get wrappedBook => 'LIVRO';

  @override
  String get wrappedCelebrity => 'CELEBRIDADE';

  @override
  String get wrappedFood => 'COMIDA';

  @override
  String get wrappedMovieRecs => 'Recomendações de filmes';

  @override
  String get wrappedBiggest => 'Maior';

  @override
  String get wrappedStruggle => 'Desafio';

  @override
  String get wrappedButYouPushedThrough => 'Mas você conseguiu 💪';

  @override
  String get wrappedWin => 'Vitória';

  @override
  String get wrappedYouDidIt => 'Você conseguiu! 🎉';

  @override
  String get wrappedTopPhrases => 'Top 5 frases';

  @override
  String get wrappedMins => 'min';

  @override
  String get wrappedConvos => 'conversas';

  @override
  String get wrappedDays => 'dias';

  @override
  String get wrappedMyBuddiesLabel => 'MEUS AMIGOS';

  @override
  String get wrappedObsessionsLabel => 'OBSESSÕES';

  @override
  String get wrappedStruggleLabel => 'DESAFIO';

  @override
  String get wrappedWinLabel => 'VITÓRIA';

  @override
  String get wrappedTopPhrasesLabel => 'TOP FRASES';

  @override
  String get wrappedLetsHitRewind => 'Vamos rebobinar o seu';

  @override
  String get wrappedGenerateMyWrapped => 'Gerar meu Wrapped';

  @override
  String get wrappedProcessingDefault => 'Processando...';

  @override
  String get wrappedCreatingYourStory => 'Criando sua\nhistória de 2025...';

  @override
  String get wrappedSomethingWentWrong => 'Algo deu\nerrado';

  @override
  String get wrappedAnErrorOccurred => 'Ocorreu um erro';

  @override
  String get wrappedTryAgain => 'Tentar novamente';

  @override
  String get wrappedNoDataAvailable => 'Nenhum dado disponível';

  @override
  String get wrappedOmiLifeRecap => 'Resumo de vida Omi';

  @override
  String get wrappedSwipeUpToBegin => 'Deslize para cima para começar';

  @override
  String get wrappedShareText => 'Meu 2025, lembrado pelo Omi ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare => 'Falha ao compartilhar. Por favor, tente novamente.';

  @override
  String get wrappedFailedToStartGeneration => 'Falha ao iniciar a geração. Por favor, tente novamente.';

  @override
  String get wrappedStarting => 'Iniciando...';

  @override
  String get wrappedShare => 'Compartilhar';

  @override
  String get wrappedShareYourWrapped => 'Compartilhe seu Wrapped';

  @override
  String get wrappedMy2025 => 'Meu 2025';

  @override
  String get wrappedRememberedByOmi => 'lembrado pelo Omi';

  @override
  String get wrappedMostFunDay => 'Mais divertido';

  @override
  String get wrappedMostProductiveDay => 'Mais produtivo';

  @override
  String get wrappedMostIntenseDay => 'Mais intenso';

  @override
  String get wrappedFunniestMoment => 'Mais engraçado';

  @override
  String get wrappedMostCringeMoment => 'Mais constrangedor';

  @override
  String get wrappedMinutesLabel => 'minutos';

  @override
  String get wrappedConversationsLabel => 'conversas';

  @override
  String get wrappedDaysActiveLabel => 'dias ativos';

  @override
  String get wrappedTasksGenerated => 'tarefas geradas';

  @override
  String get wrappedTasksCompleted => 'tarefas concluídas';

  @override
  String get wrappedTopFivePhrases => 'Top 5 frases';

  @override
  String get wrappedAGreatDay => 'Um ótimo dia';

  @override
  String get wrappedGettingItDone => 'Fazendo acontecer';

  @override
  String get wrappedAChallenge => 'Um desafio';

  @override
  String get wrappedAHilariousMoment => 'Um momento hilário';

  @override
  String get wrappedThatAwkwardMoment => 'Aquele momento constrangedor';

  @override
  String get wrappedYouHadFunnyMoments => 'Você teve momentos engraçados este ano!';

  @override
  String get wrappedWeveAllBeenThere => 'Todos nós já passamos por isso!';

  @override
  String get wrappedFriend => 'Amigo';

  @override
  String get wrappedYourBuddy => 'Seu amigo!';

  @override
  String get wrappedNotMentioned => 'Não mencionado';

  @override
  String get wrappedTheHardPart => 'A parte difícil';

  @override
  String get wrappedPersonalGrowth => 'Crescimento pessoal';

  @override
  String get wrappedFunDay => 'Divertido';

  @override
  String get wrappedProductiveDay => 'Produtivo';

  @override
  String get wrappedIntenseDay => 'Intenso';

  @override
  String get wrappedFunnyMomentTitle => 'Momento engraçado';

  @override
  String get wrappedCringeMomentTitle => 'Momento constrangedor';

  @override
  String get wrappedYouTalkedAboutBadge => 'Você falou sobre';

  @override
  String get wrappedCompletedLabel => 'Concluído';

  @override
  String get wrappedMyBuddiesCard => 'Meus amigos';

  @override
  String get wrappedBuddiesLabel => 'AMIGOS';

  @override
  String get wrappedObsessionsLabelUpper => 'OBSESSÕES';

  @override
  String get wrappedStruggleLabelUpper => 'LUTA';

  @override
  String get wrappedWinLabelUpper => 'VITÓRIA';

  @override
  String get wrappedTopPhrasesLabelUpper => 'TOP FRASES';

  @override
  String get wrappedYourHeader => 'Seus';

  @override
  String get wrappedTopDaysHeader => 'Melhores dias';

  @override
  String get wrappedYourTopDaysBadge => 'Seus melhores dias';

  @override
  String get wrappedBestHeader => 'Melhores';

  @override
  String get wrappedMomentsHeader => 'Momentos';

  @override
  String get wrappedBestMomentsBadge => 'Melhores momentos';

  @override
  String get wrappedBiggestHeader => 'Maior';

  @override
  String get wrappedStruggleHeader => 'Luta';

  @override
  String get wrappedWinHeader => 'Vitória';

  @override
  String get wrappedButYouPushedThroughEmoji => 'Mas você conseguiu 💪';

  @override
  String get wrappedYouDidItEmoji => 'Você conseguiu! 🎉';

  @override
  String get wrappedHours => 'horas';

  @override
  String get wrappedActions => 'ações';

  @override
  String get multipleSpeakersDetected => 'Vários oradores detectados';

  @override
  String get multipleSpeakersDescription =>
      'Parece que há vários oradores na gravação. Certifique-se de que está num local silencioso e tente novamente.';

  @override
  String get invalidRecordingDetected => 'Gravação inválida detectada';

  @override
  String get notEnoughSpeechDescription => 'Não foi detectada fala suficiente. Por favor, fale mais e tente novamente.';

  @override
  String get speechDurationDescription => 'Certifique-se de falar pelo menos 5 segundos e não mais de 90.';

  @override
  String get connectionLostDescription =>
      'A ligação foi interrompida. Por favor, verifique a sua ligação à internet e tente novamente.';

  @override
  String get howToTakeGoodSample => 'Como fazer uma boa amostra?';

  @override
  String get goodSampleInstructions =>
      '1. Certifique-se de que está num local silencioso.\n2. Fale clara e naturalmente.\n3. Certifique-se de que o seu dispositivo está na posição natural no pescoço.\n\nDepois de criado, pode sempre melhorá-lo ou fazê-lo novamente.';

  @override
  String get noDeviceConnectedUseMic => 'Nenhum dispositivo ligado. Será utilizado o microfone do telefone.';

  @override
  String get doItAgain => 'Fazer novamente';

  @override
  String get listenToSpeechProfile => 'Ouvir o meu perfil de voz ➡️';

  @override
  String get recognizingOthers => 'Reconhecer outros 👀';

  @override
  String get keepGoingGreat => 'Continue, está a ir muito bem';

  @override
  String get somethingWentWrongTryAgain => 'Algo deu errado! Por favor, tente novamente mais tarde.';

  @override
  String get uploadingVoiceProfile => 'Enviando seu perfil de voz....';

  @override
  String get memorizingYourVoice => 'Memorizando sua voz...';

  @override
  String get personalizingExperience => 'Personalizando sua experiência...';

  @override
  String get keepSpeakingUntil100 => 'Continue falando até chegar a 100%.';

  @override
  String get greatJobAlmostThere => 'Ótimo trabalho, está quase lá';

  @override
  String get soCloseJustLittleMore => 'Tão perto, só mais um pouco';

  @override
  String get notificationFrequency => 'Frequência de notificações';

  @override
  String get controlNotificationFrequency => 'Controle com que frequência o Omi envia notificações proativas.';

  @override
  String get yourScore => 'Sua pontuação';

  @override
  String get dailyScoreBreakdown => 'Detalhes da pontuação diária';

  @override
  String get todaysScore => 'Pontuação de hoje';

  @override
  String get tasksCompleted => 'Tarefas concluídas';

  @override
  String get completionRate => 'Taxa de conclusão';

  @override
  String get howItWorks => 'Como funciona';

  @override
  String get dailyScoreExplanation =>
      'Sua pontuação diária é baseada na conclusão de tarefas. Conclua suas tarefas para melhorar sua pontuação!';

  @override
  String get notificationFrequencyDescription =>
      'Controle com que frequência o Omi envia notificações proativas e lembretes.';

  @override
  String get sliderOff => 'Desligado';

  @override
  String get sliderMax => 'Máx.';

  @override
  String summaryGeneratedFor(String date) {
    return 'Resumo gerado para $date';
  }

  @override
  String get failedToGenerateSummary => 'Falha ao gerar resumo. Certifique-se de ter conversas para esse dia.';

  @override
  String get recap => 'Resumo';

  @override
  String deleteQuoted(String name) {
    return 'Excluir \"$name\"';
  }

  @override
  String moveConversationsTo(int count) {
    return 'Mover $count conversas para:';
  }

  @override
  String get noFolder => 'Sem pasta';

  @override
  String get removeFromAllFolders => 'Remover de todas as pastas';

  @override
  String get buildAndShareYourCustomApp => 'Crie e compartilhe seu aplicativo personalizado';

  @override
  String get searchAppsPlaceholder => 'Pesquisar em 1500+ aplicativos';

  @override
  String get filters => 'Filtros';

  @override
  String get frequencyOff => 'Desligado';

  @override
  String get frequencyMinimal => 'Mínimo';

  @override
  String get frequencyLow => 'Baixo';

  @override
  String get frequencyBalanced => 'Equilibrado';

  @override
  String get frequencyHigh => 'Alto';

  @override
  String get frequencyMaximum => 'Máximo';

  @override
  String get frequencyDescOff => 'Sem notificações proativas';

  @override
  String get frequencyDescMinimal => 'Apenas lembretes críticos';

  @override
  String get frequencyDescLow => 'Apenas atualizações importantes';

  @override
  String get frequencyDescBalanced => 'Lembretes úteis regulares';

  @override
  String get frequencyDescHigh => 'Verificações frequentes';

  @override
  String get frequencyDescMaximum => 'Mantenha-se constantemente engajado';

  @override
  String get clearChatQuestion => 'Limpar conversa?';

  @override
  String get syncingMessages => 'Sincronizando mensagens com o servidor...';

  @override
  String get chatAppsTitle => 'Apps de chat';

  @override
  String get selectApp => 'Selecionar app';

  @override
  String get noChatAppsEnabled => 'Nenhum app de chat ativado.\nToque em \"Ativar apps\" para adicionar.';

  @override
  String get disable => 'Desativar';

  @override
  String get photoLibrary => 'Biblioteca de fotos';

  @override
  String get chooseFile => 'Escolher arquivo';

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
  String get fastTransfer => 'Transferência rápida';

  @override
  String get syncingStatus => 'Syncing';

  @override
  String get failedStatus => 'Failed';

  @override
  String etaLabel(String time) {
    return 'ETA: $time';
  }

  @override
  String get transferMethod => 'Método de transferência';

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
      'Por favor, ative o acesso aos Lembretes nas Configurações para usar os Lembretes da Apple';

  @override
  String todayAtTime(String time) {
    return 'Hoje às $time';
  }

  @override
  String yesterdayAtTime(String time) {
    return 'Ontem às $time';
  }

  @override
  String get lessThanAMinute => 'Menos de um minuto';

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
  String get summarizingConversation => 'Resumindo conversa...\nIsso pode levar alguns segundos';

  @override
  String get resummarizingConversation => 'Resumindo conversa novamente...\nIsso pode levar alguns segundos';

  @override
  String get nothingInterestingRetry => 'Nada interessante encontrado,\nquer tentar novamente?';

  @override
  String get noSummaryForConversation => 'Nenhum resumo disponível\npara esta conversa.';

  @override
  String get unknownLocation => 'Localização desconhecida';

  @override
  String get couldNotLoadMap => 'Não foi possível carregar o mapa';

  @override
  String get triggerConversationIntegration => 'Acionar integração de criação de conversa';

  @override
  String get webhookUrlNotSet => 'URL do webhook não definida';

  @override
  String get setWebhookUrlInSettings =>
      'Por favor, defina a URL do webhook nas configurações de desenvolvedor para usar este recurso.';

  @override
  String get sendWebUrl => 'Enviar URL da web';

  @override
  String get sendTranscript => 'Enviar transcrição';

  @override
  String get sendSummary => 'Enviar resumo';

  @override
  String get debugModeDetected => 'Modo de depuração detectado';

  @override
  String get performanceReduced => 'O desempenho pode estar reduzido';

  @override
  String autoClosingInSeconds(int seconds) {
    return 'Fechando automaticamente em $seconds segundos';
  }

  @override
  String get modelRequired => 'Modelo necessário';

  @override
  String get downloadWhisperModel => 'Baixe um modelo whisper para usar a transcrição no dispositivo';

  @override
  String get deviceNotCompatible => 'Seu dispositivo não é compatível com transcrição no dispositivo';

  @override
  String get deviceRequirements => 'Your device does not meet the requirements for On-Device transcription.';

  @override
  String get willLikelyCrash => 'Habilitar isso provavelmente fará o app travar ou congelar.';

  @override
  String get transcriptionSlowerLessAccurate => 'A transcrição será significativamente mais lenta e menos precisa.';

  @override
  String get proceedAnyway => 'Continuar mesmo assim';

  @override
  String get olderDeviceDetected => 'Dispositivo antigo detectado';

  @override
  String get onDeviceSlower => 'On-device transcription may be slower on this device.';

  @override
  String get batteryUsageHigher => 'O uso da bateria será maior do que a transcrição na nuvem.';

  @override
  String get considerOmiCloud => 'Considere usar o Omi Cloud para melhor desempenho.';

  @override
  String get highResourceUsage => 'Alto uso de recursos';

  @override
  String get onDeviceIntensive => 'On-Device transcription is computationally intensive.';

  @override
  String get batteryDrainIncrease => 'Battery drain will increase significantly.';

  @override
  String get deviceMayWarmUp => 'O dispositivo pode esquentar durante o uso prolongado.';

  @override
  String get speedAccuracyLower => 'Velocidade e precisão podem ser menores do que os modelos na nuvem.';

  @override
  String get cloudProvider => 'Provedor de nuvem';

  @override
  String get premiumMinutesInfo => '1,200 premium minutes/month. On-Device tab offers unlimited free transcription.';

  @override
  String get viewUsage => 'Ver uso';

  @override
  String get localProcessingInfo => 'Audio is processed locally. Works offline, more private, but uses more battery.';

  @override
  String get model => 'Model';

  @override
  String get performanceWarning => 'Aviso de desempenho';

  @override
  String get largeModelWarning =>
      'This model is large and may crash the app or run very slowly on mobile devices.\n\n\"small\" or \"base\" is recommended.';

  @override
  String get usingNativeIosSpeech => 'Usando reconhecimento de fala nativo do iOS';

  @override
  String get noModelDownloadRequired => 'Your device\'s native speech engine will be used. No model download required.';

  @override
  String get modelReady => 'Model Ready';

  @override
  String get redownload => 'Re-download';

  @override
  String get doNotCloseApp => 'Por favor, não feche o app.';

  @override
  String get downloading => 'Baixando...';

  @override
  String get downloadModel => 'Baixar modelo';

  @override
  String estimatedSize(String size) {
    return 'Estimated Size: ~$size MB';
  }

  @override
  String availableSpace(String space) {
    return 'Available Space: $space';
  }

  @override
  String get notEnoughSpace => 'Aviso: Espaço insuficiente!';

  @override
  String get download => 'Baixar';

  @override
  String downloadError(String error) {
    return 'Download error: $error';
  }

  @override
  String get cancelled => 'Cancelado';

  @override
  String get deviceNotCompatibleTitle => 'Dispositivo não compatível';

  @override
  String get deviceNotMeetRequirements => 'Seu dispositivo não atende aos requisitos para transcrição no dispositivo.';

  @override
  String get transcriptionSlowerOnDevice => 'A transcrição no dispositivo pode ser mais lenta neste dispositivo.';

  @override
  String get computationallyIntensive => 'A transcrição no dispositivo é computacionalmente intensiva.';

  @override
  String get batteryDrainSignificantly => 'O consumo de bateria aumentará significativamente.';

  @override
  String get premiumMinutesMonth =>
      '1.200 minutos premium/mês. A aba No dispositivo oferece transcrição gratuita ilimitada. ';

  @override
  String get audioProcessedLocally =>
      'O áudio é processado localmente. Funciona offline, mais privado, mas usa mais bateria.';

  @override
  String get languageLabel => 'Idioma';

  @override
  String get modelLabel => 'Modelo';

  @override
  String get modelTooLargeWarning =>
      'Este modelo é grande e pode fazer o app travar ou funcionar muito lentamente em dispositivos móveis.\n\nsmall ou base é recomendado.';

  @override
  String get nativeEngineNoDownload =>
      'O mecanismo de fala nativo do seu dispositivo será usado. Não é necessário baixar modelo.';

  @override
  String modelReadyWithName(String model) {
    return 'Modelo pronto ($model)';
  }

  @override
  String get reDownload => 'Baixar novamente';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return 'Baixando $model: $received / $total MB';
  }

  @override
  String preparingModel(String model) {
    return 'Preparando $model...';
  }

  @override
  String downloadErrorWithMessage(String error) {
    return 'Erro de download: $error';
  }

  @override
  String estimatedSizeWithValue(String size) {
    return 'Tamanho estimado: ~$size MB';
  }

  @override
  String availableSpaceWithValue(String space) {
    return 'Espaço disponível: $space';
  }

  @override
  String get omiTranscriptionOptimized =>
      'A transcrição ao vivo integrada do Omi é otimizada para conversas em tempo real com detecção automática de falantes e diarização.';

  @override
  String get reset => 'Redefinir';

  @override
  String get useTemplateFrom => 'Usar modelo de';

  @override
  String get selectProviderTemplate => 'Selecione um modelo de provedor...';

  @override
  String get quicklyPopulateResponse => 'Preencher rapidamente com formato de resposta de provedor conhecido';

  @override
  String get quicklyPopulateRequest => 'Preencher rapidamente com formato de solicitação de provedor conhecido';

  @override
  String get invalidJsonError => 'JSON inválido';

  @override
  String downloadModelWithName(String model) {
    return 'Baixar modelo ($model)';
  }

  @override
  String modelNameWithFile(String model) {
    return 'Modelo: $model';
  }

  @override
  String get device => 'Device';

  @override
  String get chatAssistantsTitle => 'Assistentes de chat';

  @override
  String get permissionReadConversations => 'Ler conversas';

  @override
  String get permissionReadMemories => 'Ler memórias';

  @override
  String get permissionReadTasks => 'Ler tarefas';

  @override
  String get permissionCreateConversations => 'Criar conversas';

  @override
  String get permissionCreateMemories => 'Criar memórias';

  @override
  String get permissionTypeAccess => 'Acesso';

  @override
  String get permissionTypeCreate => 'Criar';

  @override
  String get permissionTypeTrigger => 'Gatilho';

  @override
  String get permissionDescReadConversations => 'Este app pode acessar suas conversas.';

  @override
  String get permissionDescReadMemories => 'Este app pode acessar suas memórias.';

  @override
  String get permissionDescReadTasks => 'Este app pode acessar suas tarefas.';

  @override
  String get permissionDescCreateConversations => 'Este app pode criar novas conversas.';

  @override
  String get permissionDescCreateMemories => 'Este app pode criar novas memórias.';

  @override
  String get realtimeListening => 'Escuta em tempo real';

  @override
  String get setupCompleted => 'Concluído';

  @override
  String get pleaseSelectRating => 'Por favor, selecione uma avaliação';

  @override
  String get writeReviewOptional => 'Escreva uma resenha (opcional)';

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
  String get customBackendUrlTitle => 'URL do servidor personalizada';

  @override
  String get backendUrlLabel => 'URL do servidor';

  @override
  String get saveUrlButton => 'Salvar URL';

  @override
  String get enterBackendUrlError => 'Por favor, insira a URL do servidor';

  @override
  String get urlMustEndWithSlashError => 'A URL deve terminar com \"/\"';

  @override
  String get invalidUrlError => 'Por favor, insira uma URL válida';

  @override
  String get backendUrlSavedSuccess => 'URL do servidor salva com sucesso!';

  @override
  String get signInTitle => 'Entrar';

  @override
  String get signInButton => 'Entrar';

  @override
  String get enterEmailError => 'Por favor, insira seu e-mail';

  @override
  String get invalidEmailError => 'Por favor, insira um e-mail válido';

  @override
  String get enterPasswordError => 'Por favor, insira sua senha';

  @override
  String get passwordMinLengthError => 'A senha deve ter pelo menos 8 caracteres';

  @override
  String get signInSuccess => 'Login realizado com sucesso!';

  @override
  String get alreadyHaveAccountLogin => 'Já tem uma conta? Entre';

  @override
  String get emailLabel => 'E-mail';

  @override
  String get passwordLabel => 'Senha';

  @override
  String get createAccountTitle => 'Criar conta';

  @override
  String get nameLabel => 'Nome';

  @override
  String get repeatPasswordLabel => 'Repetir senha';

  @override
  String get signUpButton => 'Cadastrar';

  @override
  String get enterNameError => 'Por favor, insira seu nome';

  @override
  String get passwordsDoNotMatch => 'As senhas não coincidem';

  @override
  String get signUpSuccess => 'Cadastro realizado com sucesso!';

  @override
  String get loadingKnowledgeGraph => 'Carregando grafo de conhecimento...';

  @override
  String get noKnowledgeGraphYet => 'Ainda não há grafo de conhecimento';

  @override
  String get buildingKnowledgeGraphFromMemories => 'Construindo grafo de conhecimento a partir de memórias...';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'Seu grafo de conhecimento será construído automaticamente quando você criar novas memórias.';

  @override
  String get buildGraphButton => 'Construir grafo';

  @override
  String get checkOutMyMemoryGraph => 'Confira meu grafo de memória!';

  @override
  String get getButton => 'Obter';

  @override
  String openingApp(String appName) {
    return 'Abrindo $appName...';
  }

  @override
  String get writeSomething => 'Escreva algo';

  @override
  String get submitReply => 'Enviar resposta';

  @override
  String get editYourReply => 'Editar sua resposta';

  @override
  String get replyToReview => 'Responder à avaliação';

  @override
  String get rateAndReviewThisApp => 'Avalie e comente esta aplicação';

  @override
  String get noChangesInReview => 'Sem alterações na avaliação para atualizar.';

  @override
  String get cantRateWithoutInternet => 'Não é possível avaliar o app sem conexão com a Internet.';

  @override
  String get appAnalytics => 'Análise do aplicativo';

  @override
  String get learnMoreLink => 'saiba mais';

  @override
  String get moneyEarned => 'Dinheiro ganho';

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
    return '$count estrela';
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
  String get goal => 'META';

  @override
  String get tapToTrackThisGoal => 'Toque para acompanhar esta meta';

  @override
  String get tapToSetAGoal => 'Toque para definir uma meta';

  @override
  String get processedConversations => 'Conversas processadas';

  @override
  String get updatedConversations => 'Conversas atualizadas';

  @override
  String get newConversations => 'Novas conversas';

  @override
  String get summaryTemplate => 'Modelo de resumo';

  @override
  String get suggestedTemplates => 'Modelos sugeridos';

  @override
  String get otherTemplates => 'Outros modelos';

  @override
  String get availableTemplates => 'Modelos disponíveis';

  @override
  String get getCreative => 'Seja criativo';

  @override
  String get defaultLabel => 'Padrão';

  @override
  String get lastUsedLabel => 'Último uso';

  @override
  String get setDefaultApp => 'Definir app padrão';

  @override
  String setDefaultAppContent(String appName) {
    return 'Definir $appName como seu app de resumo padrão?\\n\\nEste app será usado automaticamente para todos os resumos de conversas futuras.';
  }

  @override
  String get setDefaultButton => 'Definir padrão';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName definido como app de resumo padrão';
  }

  @override
  String get createCustomTemplate => 'Criar modelo personalizado';

  @override
  String get allTemplates => 'Todos os modelos';

  @override
  String failedToInstallApp(String appName) {
    return 'Falha ao instalar $appName. Por favor, tente novamente.';
  }

  @override
  String errorInstallingApp(String appName, String error) {
    return 'Erro ao instalar $appName: $error';
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
  String get shareViaSms => 'Compartilhar por SMS';

  @override
  String get selectContactsToShareSummary => 'Selecione contatos para compartilhar o resumo da conversa';

  @override
  String get searchContactsHint => 'Pesquisar contatos...';

  @override
  String contactsSelectedCount(int count) {
    return '$count selecionados';
  }

  @override
  String get clearAllSelection => 'Limpar tudo';

  @override
  String get selectContactsToShare => 'Selecione contatos para compartilhar';

  @override
  String shareWithContactCount(int count) {
    return 'Compartilhar com $count contato';
  }

  @override
  String shareWithContactsCount(int count) {
    return 'Compartilhar com $count contatos';
  }

  @override
  String get contactsPermissionRequired => 'Permissão de contatos necessária';

  @override
  String get contactsPermissionRequiredForSms => 'Permissão de contatos é necessária para compartilhar por SMS';

  @override
  String get grantContactsPermissionForSms => 'Por favor, conceda permissão de contatos para compartilhar por SMS';

  @override
  String get noContactsWithPhoneNumbers => 'Nenhum contato com número de telefone encontrado';

  @override
  String get noContactsMatchSearch => 'Nenhum contato corresponde à sua pesquisa';

  @override
  String get failedToLoadContacts => 'Falha ao carregar contatos';

  @override
  String get failedToPrepareConversationForSharing =>
      'Falha ao preparar a conversa para compartilhamento. Por favor, tente novamente.';

  @override
  String get couldNotOpenSmsApp => 'Não foi possível abrir o aplicativo de SMS. Por favor, tente novamente.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'Aqui está o que acabamos de discutir: $link';
  }

  @override
  String get wifiSync => 'Sincronização WiFi';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item copiado para a área de transferência';
  }

  @override
  String get wifiConnectionFailedTitle => 'Connection Failed';

  @override
  String connectingToDeviceName(String deviceName) {
    return 'Connecting to $deviceName';
  }

  @override
  String enableDeviceWifi(String deviceName) {
    return 'Enable $deviceName\'s WiFi';
  }

  @override
  String connectToDeviceName(String deviceName) {
    return 'Connect to $deviceName';
  }

  @override
  String get recordingDetails => 'Recording Details';

  @override
  String get storageLocationSdCard => 'SD Card';

  @override
  String get storageLocationLimitlessPendant => 'Limitless Pendant';

  @override
  String get storageLocationPhone => 'Phone';

  @override
  String get storageLocationPhoneMemory => 'Phone (Memory)';

  @override
  String storedOnDevice(String deviceName) {
    return 'Stored on $deviceName';
  }

  @override
  String get transferring => 'Transferring...';

  @override
  String get transferRequired => 'Transfer Required';

  @override
  String get downloadingAudioFromSdCard => 'Downloading audio from your device\'s SD card';

  @override
  String get transferRequiredDescription =>
      'This recording is stored on your device\'s SD card. Transfer it to your phone to play or share.';

  @override
  String get cancelTransfer => 'Cancel Transfer';

  @override
  String get transferToPhone => 'Transfer to Phone';

  @override
  String get privateAndSecureOnDevice => 'Private & secure on your device';

  @override
  String get recordingInfo => 'Recording Info';

  @override
  String get transferInProgress => 'Transfer in progress...';

  @override
  String get shareRecording => 'Share Recording';

  @override
  String get deleteRecordingConfirmation =>
      'Are you sure you want to permanently delete this recording? This can\'t be undone.';

  @override
  String get recordingIdLabel => 'Recording ID';

  @override
  String get dateTimeLabel => 'Date & Time';

  @override
  String get durationLabel => 'Duration';

  @override
  String get audioFormatLabel => 'Audio Format';

  @override
  String get storageLocationLabel => 'Storage Location';

  @override
  String get estimatedSizeLabel => 'Estimated Size';

  @override
  String get deviceModelLabel => 'Device Model';

  @override
  String get deviceIdLabel => 'Device ID';

  @override
  String get statusLabel => 'Status';

  @override
  String get statusProcessed => 'Processed';

  @override
  String get statusUnprocessed => 'Unprocessed';

  @override
  String get switchedToFastTransfer => 'Switched to Fast Transfer';

  @override
  String get transferCompleteMessage => 'Transfer complete! You can now play this recording.';

  @override
  String transferFailedMessage(String error) {
    return 'Transfer failed: $error';
  }

  @override
  String get transferCancelled => 'Transfer cancelled';

  @override
  String get fastTransferEnabled => 'Transferência rápida ativada';

  @override
  String get bluetoothSyncEnabled => 'Sincronização Bluetooth ativada';

  @override
  String get enableFastTransfer => 'Ativar transferência rápida';

  @override
  String get fastTransferDescription =>
      'A transferência rápida usa WiFi para velocidades ~5x mais rápidas. Seu telefone se conectará temporariamente à rede WiFi do dispositivo Omi durante a transferência.';

  @override
  String get internetAccessPausedDuringTransfer => 'O acesso à internet é pausado durante a transferência';

  @override
  String get chooseTransferMethodDescription =>
      'Escolha como as gravações são transferidas do dispositivo Omi para seu telefone.';

  @override
  String get wifiSpeed => '~150 KB/s via WiFi';

  @override
  String get fiveTimesFaster => '5X MAIS RÁPIDO';

  @override
  String get fastTransferMethodDescription =>
      'Cria uma conexão WiFi direta com seu dispositivo Omi. Seu telefone se desconecta temporariamente do WiFi normal durante a transferência.';

  @override
  String get bluetooth => 'Bluetooth';

  @override
  String get bleSpeed => '~30 KB/s via BLE';

  @override
  String get bluetoothMethodDescription =>
      'Usa conexão Bluetooth Low Energy padrão. Mais lento, mas não afeta sua conexão WiFi.';

  @override
  String get selected => 'Selecionado';

  @override
  String get selectOption => 'Selecionar';

  @override
  String get lowBatteryAlertTitle => 'Alerta de bateria fraca';

  @override
  String get lowBatteryAlertBody => 'A bateria do seu dispositivo está fraca. Hora de recarregar! 🔋';

  @override
  String get deviceDisconnectedNotificationTitle => 'Seu dispositivo Omi foi desconectado';

  @override
  String get deviceDisconnectedNotificationBody => 'Por favor, reconecte para continuar usando o Omi.';

  @override
  String get firmwareUpdateAvailable => 'Atualização de firmware disponível';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'Uma nova atualização de firmware ($version) está disponível para seu dispositivo Omi. Deseja atualizar agora?';
  }

  @override
  String get later => 'Mais tarde';

  @override
  String get appDeletedSuccessfully => 'App excluído com sucesso';

  @override
  String get appDeleteFailed => 'Falha ao excluir o app. Por favor, tente novamente mais tarde.';

  @override
  String get appVisibilityChangedSuccessfully =>
      'Visibilidade do app alterada com sucesso. Pode levar alguns minutos para refletir.';

  @override
  String get errorActivatingAppIntegration =>
      'Erro ao ativar o app. Se for um app de integração, certifique-se de que a configuração esteja concluída.';

  @override
  String get errorUpdatingAppStatus => 'Ocorreu um erro ao atualizar o status do app.';

  @override
  String get calculatingETA => 'Calculating...';

  @override
  String aboutMinutesRemaining(int minutes) {
    return 'About $minutes minutes remaining';
  }

  @override
  String get aboutAMinuteRemaining => 'About a minute remaining';

  @override
  String get almostDone => 'Almost done...';

  @override
  String get omiSays => 'omi says';

  @override
  String get analyzingYourData => 'Analyzing your data...';

  @override
  String migratingToProtection(String level) {
    return 'Migrating to $level protection...';
  }

  @override
  String get noDataToMigrateFinalizing => 'No data to migrate. Finalizing...';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return 'Migrating $itemType... $percentage%';
  }

  @override
  String get allObjectsMigratedFinalizing => 'All objects migrated. Finalizing...';

  @override
  String get migrationErrorOccurred => 'An error occurred during migration. Please try again.';

  @override
  String get migrationComplete => 'Migration complete!';

  @override
  String dataProtectedWithSettings(String level) {
    return 'Your data is now protected with the new $level settings.';
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
  String get importantConversationTitle => 'Conversa importante';

  @override
  String get importantConversationBody =>
      'Você acabou de ter uma conversa importante. Toque para compartilhar o resumo.';

  @override
  String get templateName => 'Nome do modelo';

  @override
  String get templateNameHint => 'ex., Extrator de itens de ação de reuniões';

  @override
  String get nameMustBeAtLeast3Characters => 'O nome deve ter pelo menos 3 caracteres';

  @override
  String get conversationPromptHint =>
      'ex., Extraia itens de ação, decisões tomadas e pontos-chave da conversa fornecida.';

  @override
  String get pleaseEnterAppPrompt => 'Por favor, insira um prompt para o seu aplicativo';

  @override
  String get promptMustBeAtLeast10Characters => 'O prompt deve ter pelo menos 10 caracteres';

  @override
  String get anyoneCanDiscoverTemplate => 'Qualquer pessoa pode descobrir seu modelo';

  @override
  String get onlyYouCanUseTemplate => 'Apenas você pode usar este modelo';

  @override
  String get generatingDescription => 'Gerando descrição...';

  @override
  String get creatingAppIcon => 'Criando ícone do aplicativo...';

  @override
  String get installingApp => 'Instalando aplicativo...';

  @override
  String get appCreatedAndInstalled => 'Aplicativo criado e instalado!';

  @override
  String get appCreatedSuccessfully => 'Aplicativo criado com sucesso!';

  @override
  String get failedToCreateApp => 'Falha ao criar o aplicativo. Por favor, tente novamente.';

  @override
  String get addAppSelectCoreCapability => 'Please select one more core capability for your app to proceed';

  @override
  String get addAppSelectPaymentPlan => 'Please select a payment plan and enter a price for your app';

  @override
  String get addAppSelectCapability => 'Please select at least one capability for your app';

  @override
  String get addAppSelectLogo => 'Please select a logo for your app';

  @override
  String get addAppEnterChatPrompt => 'Please enter a chat prompt for your app';

  @override
  String get addAppEnterConversationPrompt => 'Please enter a conversation prompt for your app';

  @override
  String get addAppSelectTriggerEvent => 'Please select a trigger event for your app';

  @override
  String get addAppEnterWebhookUrl => 'Please enter a webhook URL for your app';

  @override
  String get addAppSelectCategory => 'Please select a category for your app';

  @override
  String get addAppFillRequiredFields => 'Please fill in all the required fields correctly';

  @override
  String get addAppUpdatedSuccess => 'App updated successfully 🚀';

  @override
  String get addAppUpdateFailed => 'Failed to update app. Please try again later';

  @override
  String get addAppSubmittedSuccess => 'App submitted successfully 🚀';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'Error opening file picker: $message';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'Error selecting image: $error';
  }

  @override
  String get addAppPhotosPermissionDenied =>
      'Photos permission denied. Please allow access to photos to select an image';

  @override
  String get addAppErrorSelectingImageRetry => 'Error selecting image. Please try again.';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'Error selecting thumbnail: $error';
  }

  @override
  String get addAppErrorSelectingThumbnailRetry => 'Error selecting thumbnail. Please try again.';

  @override
  String get addAppCapabilityConflictWithPersona => 'Other capabilities cannot be selected with Persona';

  @override
  String get addAppPersonaConflictWithCapabilities => 'Persona cannot be selected with other capabilities';

  @override
  String get personaTwitterHandleNotFound => 'Twitter handle not found';

  @override
  String get personaTwitterHandleSuspended => 'Twitter handle is suspended';

  @override
  String get personaFailedToVerifyTwitter => 'Failed to verify Twitter handle';

  @override
  String get personaFailedToFetch => 'Failed to fetch your persona';

  @override
  String get personaFailedToCreate => 'Failed to create your persona';

  @override
  String get personaConnectKnowledgeSource => 'Please connect at least one knowledge data source (Omi or Twitter)';

  @override
  String get personaUpdatedSuccessfully => 'Persona updated successfully';

  @override
  String get personaFailedToUpdate => 'Failed to update persona';

  @override
  String get personaPleaseSelectImage => 'Please select an image';

  @override
  String get personaFailedToCreateTryLater => 'Failed to create your persona. Please try again later.';

  @override
  String personaFailedToCreateWithError(String error) {
    return 'Failed to create persona: $error';
  }

  @override
  String get personaFailedToEnable => 'Failed to enable persona';

  @override
  String personaErrorEnablingWithError(String error) {
    return 'Error enabling persona: $error';
  }

  @override
  String get paymentFailedToFetchCountries => 'Failed to fetch supported countries. Please try again later.';

  @override
  String get paymentFailedToSetDefault => 'Failed to set default payment method. Please try again later.';

  @override
  String get paymentFailedToSavePaypal => 'Failed to save PayPal details. Please try again later.';

  @override
  String get paypalEmailHint => 'nik@example.com';

  @override
  String get paypalMeLinkHint => 'paypal.me/nik';

  @override
  String get paymentMethodStripe => 'Stripe';

  @override
  String get paymentMethodPayPal => 'PayPal';

  @override
  String get paymentStatusActive => 'Active';

  @override
  String get paymentStatusConnected => 'Connected';

  @override
  String get paymentStatusNotConnected => 'Not Connected';

  @override
  String get paymentAppCost => 'App Cost';

  @override
  String get paymentEnterValidAmount => 'Please enter a valid amount';

  @override
  String get paymentEnterAmountGreaterThanZero => 'Please enter an amount greater than 0';

  @override
  String get paymentPlan => 'Payment Plan';

  @override
  String get paymentNoneSelected => 'None Selected';
}
