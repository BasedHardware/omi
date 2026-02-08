// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Chinese (`zh`).
class AppLocalizationsZh extends AppLocalizations {
  AppLocalizationsZh([String locale = 'zh']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => '对话';

  @override
  String get transcriptTab => '转录';

  @override
  String get actionItemsTab => '行动项';

  @override
  String get deleteConversationTitle => '删除对话？';

  @override
  String get deleteConversationMessage => '您确定要删除此对话吗？此操作无法撤消。';

  @override
  String get confirm => '确认';

  @override
  String get cancel => '取消';

  @override
  String get ok => '确定';

  @override
  String get delete => '删除';

  @override
  String get add => '添加';

  @override
  String get update => '更新';

  @override
  String get save => '保存';

  @override
  String get edit => '编辑';

  @override
  String get close => '关闭';

  @override
  String get clear => '清除';

  @override
  String get copyTranscript => '复制文字记录';

  @override
  String get copySummary => '复制摘要';

  @override
  String get testPrompt => '测试提示词';

  @override
  String get reprocessConversation => '重新处理对话';

  @override
  String get deleteConversation => '删除对话';

  @override
  String get contentCopied => '内容已复制到剪贴板';

  @override
  String get failedToUpdateStarred => '无法更新星标状态。';

  @override
  String get conversationUrlNotShared => '无法分享对话链接。';

  @override
  String get errorProcessingConversation => '处理对话时出错。请稍后再试。';

  @override
  String get noInternetConnection => '无网络连接';

  @override
  String get unableToDeleteConversation => '无法删除对话';

  @override
  String get somethingWentWrong => '出错了！请稍后再试。';

  @override
  String get copyErrorMessage => '复制错误信息';

  @override
  String get errorCopied => '错误信息已复制';

  @override
  String get remaining => '剩余';

  @override
  String get loading => '加载中...';

  @override
  String get loadingDuration => '加载持续时间...';

  @override
  String secondsCount(int count) {
    return '$count 秒';
  }

  @override
  String get people => '人员';

  @override
  String get addNewPerson => '添加新人员';

  @override
  String get editPerson => '编辑人员';

  @override
  String get createPersonHint => '创建一个新人员并训练 Omi 识别他们的声音！';

  @override
  String get speechProfile => '语音配置文件';

  @override
  String sampleNumber(int number) {
    return '样本 $number';
  }

  @override
  String get settings => '设置';

  @override
  String get language => '语言';

  @override
  String get selectLanguage => '选择语言';

  @override
  String get deleting => '删除中...';

  @override
  String get pleaseCompleteAuthentication => '请在浏览器中完成身份验证。完成后返回应用程序。';

  @override
  String get failedToStartAuthentication => '无法启动身份验证';

  @override
  String get importStarted => '导入已开始！完成后我们将通知您。';

  @override
  String get failedToStartImport => '无法启动导入。请重试。';

  @override
  String get couldNotAccessFile => '无法打开所选文件';

  @override
  String get askOmi => '询问Omi';

  @override
  String get done => '完成';

  @override
  String get disconnected => '已断开连接';

  @override
  String get searching => '搜索中...';

  @override
  String get connectDevice => '连接设备';

  @override
  String get monthlyLimitReached => '您已达到每月限额。';

  @override
  String get checkUsage => '检查用量';

  @override
  String get syncingRecordings => '正在同步录音';

  @override
  String get recordingsToSync => '待同步录音';

  @override
  String get allCaughtUp => '已全部同步';

  @override
  String get sync => '同步';

  @override
  String get pendantUpToDate => '设备已更新';

  @override
  String get allRecordingsSynced => '所有录音已同步';

  @override
  String get syncingInProgress => '正在同步';

  @override
  String get readyToSync => '准备同步';

  @override
  String get tapSyncToStart => '点击同步以开始';

  @override
  String get pendantNotConnected => '设备未连接。连接以同步。';

  @override
  String get everythingSynced => '所有内容已同步。';

  @override
  String get recordingsNotSynced => '您有尚未同步的录音。';

  @override
  String get syncingBackground => '我们将继续在后台同步您的录音。';

  @override
  String get noConversationsYet => '还没有对话';

  @override
  String get noStarredConversations => '没有加星标的对话';

  @override
  String get starConversationHint => '要加星标，请打开对话并点击顶部的星星图标。';

  @override
  String get searchConversations => '搜索对话...';

  @override
  String selectedCount(int count, Object s) {
    return '已选择 $count 项';
  }

  @override
  String get merge => '合并';

  @override
  String get mergeConversations => '合并对话';

  @override
  String mergeConversationsMessage(int count) {
    return '这将把 $count 个对话合并为一个。所有内容将被合并并重新生成。';
  }

  @override
  String get mergingInBackground => '后台合并中。这可能需要一点时间。';

  @override
  String get failedToStartMerge => '无法开始合并';

  @override
  String get askAnything => '随便问问';

  @override
  String get noMessagesYet => '还没有消息！\n为什么不开始一段对话呢？';

  @override
  String get deletingMessages => '正在从 Omi 的内存中删除您的消息...';

  @override
  String get messageCopied => '✨ 消息已复制到剪贴板';

  @override
  String get cannotReportOwnMessage => '您不能举报自己的消息。';

  @override
  String get reportMessage => '举报消息';

  @override
  String get reportMessageConfirm => '您确定要举报此消息吗？';

  @override
  String get messageReported => '消息举报成功。';

  @override
  String get thankYouFeedback => '感谢您的反馈！';

  @override
  String get clearChat => '清除聊天';

  @override
  String get clearChatConfirm => '您确定要清除聊天记录吗？此操作无法撤消。';

  @override
  String get maxFilesLimit => '您一次只能上传 4 个文件';

  @override
  String get chatWithOmi => '与 Omi 聊天';

  @override
  String get apps => '应用';

  @override
  String get noAppsFound => '未找到应用';

  @override
  String get tryAdjustingSearch => '尝试调整您的搜索或筛选';

  @override
  String get createYourOwnApp => '创建您自己的应用';

  @override
  String get buildAndShareApp => '构建并分享您自己的应用';

  @override
  String get searchApps => '搜索应用...';

  @override
  String get myApps => '我的应用';

  @override
  String get installedApps => '已安装应用';

  @override
  String get unableToFetchApps => '无法加载应用 :(\n\n请检查您的网络连接。';

  @override
  String get aboutOmi => '关于 Omi';

  @override
  String get privacyPolicy => '隐私政策';

  @override
  String get visitWebsite => '访问网站';

  @override
  String get helpOrInquiries => '帮助或咨询？';

  @override
  String get joinCommunity => '加入社区！';

  @override
  String get membersAndCounting => '8000+名成员并且还在增加。';

  @override
  String get deleteAccountTitle => '删除账户';

  @override
  String get deleteAccountConfirm => '您确定要删除您的账户吗？';

  @override
  String get cannotBeUndone => '此操作无法撤消。';

  @override
  String get allDataErased => '您的所有记忆和对话将被永久删除。';

  @override
  String get appsDisconnected => '您的应用和集成将立即断开连接。';

  @override
  String get exportBeforeDelete => '您可以在删除账户前导出数据。一旦删除，将无法恢复。';

  @override
  String get deleteAccountCheckbox => '我明白删除账户是永久性的，所有数据（包括记忆和对话）都将丢失且无法恢复。';

  @override
  String get areYouSure => '您确定吗？';

  @override
  String get deleteAccountFinal => '此操作不可逆，将永久删除您的账户及所有相关数据。您确定要继续吗？';

  @override
  String get deleteNow => '立即删除';

  @override
  String get goBack => '返回';

  @override
  String get checkBoxToConfirm => '请勾选复选框以确认您了解删除账户是永久且不可逆的。';

  @override
  String get profile => '个人资料';

  @override
  String get name => '姓名';

  @override
  String get email => '电子邮件';

  @override
  String get customVocabulary => '自定义词汇';

  @override
  String get identifyingOthers => '识别他人';

  @override
  String get paymentMethods => '支付方式';

  @override
  String get conversationDisplay => '对话显示';

  @override
  String get dataPrivacy => '数据隐私';

  @override
  String get userId => '用户 ID';

  @override
  String get notSet => '未设置';

  @override
  String get userIdCopied => '用户 ID 已复制';

  @override
  String get systemDefault => '系统默认';

  @override
  String get planAndUsage => '套餐与用量';

  @override
  String get offlineSync => '离线同步';

  @override
  String get deviceSettings => '设备设置';

  @override
  String get integrations => '集成';

  @override
  String get feedbackBug => '反馈 / Bug';

  @override
  String get helpCenter => '帮助中心';

  @override
  String get developerSettings => '开发者设置';

  @override
  String get getOmiForMac => '获取 Omi Mac 版';

  @override
  String get referralProgram => '推荐计划';

  @override
  String get signOut => '退出登录';

  @override
  String get appAndDeviceCopied => '应用和设备详情已复制';

  @override
  String get wrapped2025 => '2025 年度回顾';

  @override
  String get yourPrivacyYourControl => '您的隐私，由您掌控';

  @override
  String get privacyIntro => '在 Omi，我们致力于保护您的隐私。此页面允许您控制数据的保存和使用方式。';

  @override
  String get learnMore => '了解更多...';

  @override
  String get dataProtectionLevel => '数据保护级别';

  @override
  String get dataProtectionDesc => '默认情况下，您的数据受强加密保护。';

  @override
  String get appAccess => '应用访问';

  @override
  String get appAccessDesc => '以下应用可以访问您的数据。点击应用以管理其权限。';

  @override
  String get noAppsExternalAccess => '暂无已安装应用具有外部数据访问权限。';

  @override
  String get deviceName => '设备名称';

  @override
  String get deviceId => '设备ID';

  @override
  String get firmware => '固件';

  @override
  String get sdCardSync => 'SD卡同步';

  @override
  String get hardwareRevision => '硬件版本';

  @override
  String get modelNumber => '型号';

  @override
  String get manufacturer => '制造商';

  @override
  String get doubleTap => '双击';

  @override
  String get ledBrightness => 'LED 亮度';

  @override
  String get micGain => '麦克风增益';

  @override
  String get disconnect => '断开连接';

  @override
  String get forgetDevice => '遗忘设备';

  @override
  String get chargingIssues => '充电问题';

  @override
  String get disconnectDevice => '断开设备连接';

  @override
  String get unpairDevice => '取消配对设备';

  @override
  String get unpairAndForget => '取消配对并遗忘设备';

  @override
  String get deviceDisconnectedMessage => '您的 Omi 已断开连接 😔';

  @override
  String get deviceUnpairedMessage => '设备已取消配对。转到设置 > 蓝牙并忘记设备以完成取消配对。';

  @override
  String get unpairDialogTitle => '取消配对设备';

  @override
  String get unpairDialogMessage => '这将取消配对设备，使其可以连接到其他手机。您必须前往 设置 > 蓝牙 并遗忘该设备以完成此过程。';

  @override
  String get deviceNotConnected => '设备未连接';

  @override
  String get connectDeviceMessage => '连接您的 Omi 设备以访问设置和自定义。';

  @override
  String get deviceInfoSection => '设备信息';

  @override
  String get customizationSection => '自定义';

  @override
  String get hardwareSection => '硬件';

  @override
  String get v2Undetected => '未检测到 V2';

  @override
  String get v2UndetectedMessage => '我们发现您使用的是 V1 设备或设备未连接。SD 卡功能仅适用于 V2 设备。';

  @override
  String get endConversation => '结束对话';

  @override
  String get pauseResume => '暂停/恢复';

  @override
  String get starConversation => '星标对话';

  @override
  String get doubleTapAction => '双击操作';

  @override
  String get endAndProcess => '结束并处理';

  @override
  String get pauseResumeRecording => '暂停/恢复录音';

  @override
  String get starOngoing => '星标当前对话';

  @override
  String get off => '关闭';

  @override
  String get max => '最大';

  @override
  String get mute => '静音';

  @override
  String get quiet => '安静';

  @override
  String get normal => '正常';

  @override
  String get high => '高';

  @override
  String get micGainDescMuted => '麦克风已静音';

  @override
  String get micGainDescLow => '极低 - 适用于嘈杂环境';

  @override
  String get micGainDescModerate => '低 - 适用于中等噪音';

  @override
  String get micGainDescNeutral => '中性 - 平衡录音';

  @override
  String get micGainDescSlightlyBoosted => '略微增强 - 正常使用';

  @override
  String get micGainDescBoosted => '增强 - 适用于安静环境';

  @override
  String get micGainDescHigh => '高 - 适用于远距离或轻声细语';

  @override
  String get micGainDescVeryHigh => '极高 - 适用于极微弱声源';

  @override
  String get micGainDescMax => '最大 - 谨慎使用';

  @override
  String get developerSettingsTitle => '开发者设置';

  @override
  String get saving => '正在保存...';

  @override
  String get personaConfig => '配置您的 AI 人格';

  @override
  String get beta => '测试版';

  @override
  String get transcription => '转录';

  @override
  String get transcriptionConfig => '配置 STT 提供商';

  @override
  String get conversationTimeout => '对话超时';

  @override
  String get conversationTimeoutConfig => '设置对话自动结束的时间';

  @override
  String get importData => '导入数据';

  @override
  String get importDataConfig => '从其他来源导入数据';

  @override
  String get debugDiagnostics => '调试与诊断';

  @override
  String get endpointUrl => '端点 URL';

  @override
  String get noApiKeys => '暂无 API 密钥';

  @override
  String get createKeyToStart => '创建一个密钥以开始';

  @override
  String get createKey => '创建密钥';

  @override
  String get docs => '文档';

  @override
  String get yourOmiInsights => '您的 Omi 见解';

  @override
  String get today => '今天';

  @override
  String get thisMonth => '本月';

  @override
  String get thisYear => '今年';

  @override
  String get allTime => '全部时间';

  @override
  String get noActivityYet => '暂无活动';

  @override
  String get startConversationToSeeInsights => '与 Omi 开始一段对话\n以在此查看您的见解。';

  @override
  String get listening => '聆听';

  @override
  String get listeningSubtitle => 'Omi 主动聆听的总时长。';

  @override
  String get understanding => '理解';

  @override
  String get understandingSubtitle => '从您的对话中理解的单词数。';

  @override
  String get providing => '提供';

  @override
  String get providingSubtitle => '自动捕获的任务和笔记。';

  @override
  String get remembering => '记忆';

  @override
  String get rememberingSubtitle => '为您记住的事实和细节。';

  @override
  String get unlimitedPlan => '无限套餐';

  @override
  String get managePlan => '管理套餐';

  @override
  String cancelAtPeriodEnd(String date) {
    return '您的套餐将于 $date 结束。';
  }

  @override
  String renewsOn(String date) {
    return '您的套餐将于 $date 续订。';
  }

  @override
  String get basicPlan => '免费套餐';

  @override
  String usageLimitMessage(String used, int limit) {
    return '已使用 $used / $limit 分钟';
  }

  @override
  String get upgrade => '升级';

  @override
  String get upgradeToUnlimited => '升级至无限制';

  @override
  String basicPlanDesc(int limit) {
    return '您的套餐包含每月 $limit 分钟免费时长。';
  }

  @override
  String get shareStatsMessage => '分享我的 Omi 统计数据！(omi.me - 我的全天候 AI 助手)';

  @override
  String get sharePeriodToday => '今天 Omi：';

  @override
  String get sharePeriodMonth => '本月 Omi：';

  @override
  String get sharePeriodYear => '今年 Omi：';

  @override
  String get sharePeriodAllTime => '迄今为止 Omi：';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 聆听了 $minutes 分钟';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 理解了 $words 个单词';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ 提供了 $count 条见解';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 保存了 $count 条记忆';
  }

  @override
  String get debugLogs => '调试日志';

  @override
  String get debugLogsAutoDelete => '将在 3 天后自动删除。';

  @override
  String get debugLogsDesc => '帮助诊断问题';

  @override
  String get noLogFilesFound => '未找到日志文件。';

  @override
  String get omiDebugLog => 'Omi 调试日志';

  @override
  String get logShared => '日志已分享';

  @override
  String get selectLogFile => '选择日志文件';

  @override
  String get shareLogs => '分享日志';

  @override
  String get debugLogCleared => '调试日志已清除';

  @override
  String get exportStarted => '导出已开始。这可能需要几秒钟...';

  @override
  String get exportAllData => '导出所有数据';

  @override
  String get exportDataDesc => '将对话导出为 JSON 文件';

  @override
  String get exportedConversations => 'Omi 导出的对话';

  @override
  String get exportShared => '导出已分享';

  @override
  String get deleteKnowledgeGraphTitle => '删除知识图谱？';

  @override
  String get deleteKnowledgeGraphMessage => '这将删除所有导出的图谱数据（节点和连接）。您的原始记忆保持安全。';

  @override
  String get knowledgeGraphDeleted => '知识图谱已删除';

  @override
  String deleteGraphFailed(String error) {
    return '删除图谱失败: $error';
  }

  @override
  String get deleteKnowledgeGraph => '删除知识图谱';

  @override
  String get deleteKnowledgeGraphDesc => '删除所有节点和连接';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'MCP 服务器';

  @override
  String get mcpServerDesc => '将 AI 助手连接到您的数据';

  @override
  String get serverUrl => '服务器 URL';

  @override
  String get urlCopied => '已复制 URL';

  @override
  String get apiKeyAuth => 'API 密钥认证';

  @override
  String get header => '头部';

  @override
  String get authorizationBearer => 'Authorization: Bearer <key>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'Client ID';

  @override
  String get clientSecret => 'Client Secret';

  @override
  String get useMcpApiKey => '使用您的 MCP API 密钥';

  @override
  String get webhooks => 'Webhooks';

  @override
  String get conversationEvents => '对话事件';

  @override
  String get newConversationCreated => '新对话已创建';

  @override
  String get realtimeTranscript => '实时转录';

  @override
  String get transcriptReceived => '收到转录';

  @override
  String get audioBytes => '音频字节';

  @override
  String get audioDataReceived => '收到音频数据';

  @override
  String get intervalSeconds => '间隔（秒）';

  @override
  String get daySummary => '每日摘要';

  @override
  String get summaryGenerated => '摘要已生成';

  @override
  String get claudeDesktop => 'Claude 桌面版';

  @override
  String get addToClaudeConfig => '添加到 claude_desktop_config.json';

  @override
  String get copyConfig => '复制配置';

  @override
  String get configCopied => '配置已复制';

  @override
  String get listeningMins => '聆听（分钟）';

  @override
  String get understandingWords => '理解（单词）';

  @override
  String get insights => '见解';

  @override
  String get memories => '回忆';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '本月已用 $used/$limit 分钟';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '本月已用 $used/$limit 单词';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '本月获得 $used/$limit 条见解';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return '本月创建 $used/$limit 条记忆';
  }

  @override
  String get visibility => '可见性';

  @override
  String get visibilitySubtitle => '控制哪些对话显示在列表中';

  @override
  String get showShortConversations => '显示简短对话';

  @override
  String get showShortConversationsDesc => '显示短于阈值的对话';

  @override
  String get showDiscardedConversations => '显示已丢弃对话';

  @override
  String get showDiscardedConversationsDesc => '包含标记为已丢弃的对话';

  @override
  String get shortConversationThreshold => '简短对话阈值';

  @override
  String get shortConversationThresholdSubtitle => '短于此的对话将被隐藏（除非上方已启用）';

  @override
  String get durationThreshold => '时长阈值';

  @override
  String get durationThresholdDesc => '隐藏短于此的对话';

  @override
  String minLabel(int count) {
    return '$count 分钟';
  }

  @override
  String get customVocabularyTitle => '自定义词汇';

  @override
  String get addWords => '添加单词';

  @override
  String get addWordsDesc => '姓名、术语或不常见的词';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'Connect';

  @override
  String get comingSoon => '即将推出';

  @override
  String get integrationsFooter => '连接您的应用以在聊天中查看数据和指标。';

  @override
  String get completeAuthInBrowser => '请在浏览器中完成身份验证。';

  @override
  String failedToStartAuth(String appName) {
    return '无法为 $appName 启动身份验证';
  }

  @override
  String disconnectAppTitle(String appName) {
    return '断开 $appName？';
  }

  @override
  String disconnectAppMessage(String appName) {
    return '您确定要断开 $appName 吗？您可以随时重新连接。';
  }

  @override
  String disconnectedFrom(String appName) {
    return '已断开与 $appName 的连接';
  }

  @override
  String get failedToDisconnect => '断开连接失败';

  @override
  String connectTo(String appName) {
    return '连接到 $appName';
  }

  @override
  String authAccessMessage(String appName) {
    return '您需要授权 Omi 访问您的 $appName 数据。';
  }

  @override
  String get continueAction => '继续';

  @override
  String get languageTitle => '语言';

  @override
  String get primaryLanguage => '主要语言';

  @override
  String get automaticTranslation => '自动翻译';

  @override
  String get detectLanguages => '检测 10+ 种语言';

  @override
  String get authorizeSavingRecordings => '授权保存录音';

  @override
  String get thanksForAuthorizing => '感谢授权！';

  @override
  String get needYourPermission => '我们需要您的许可';

  @override
  String get alreadyGavePermission => '您已允许我们保存录音。以下是我们需要它的原因：';

  @override
  String get wouldLikePermission => '我们希望获得您保存语音录音的许可。原因是：';

  @override
  String get improveSpeechProfile => '改善您的语音档案';

  @override
  String get improveSpeechProfileDesc => '我们使用录音来进一步训练和改善您的个人语音档案。';

  @override
  String get trainFamilyProfiles => '训练朋友和家人的档案';

  @override
  String get trainFamilyProfilesDesc => '您的录音有助于我们识别并为您的朋友和家人创建档案。';

  @override
  String get enhanceTranscriptAccuracy => '提高转录准确性';

  @override
  String get enhanceTranscriptAccuracyDesc => '随着我们模型的改进，我们可以为您的录音提供更好的转录结果。';

  @override
  String get legalNotice => '法律声明：录音的合法性可能因您的位置而异。';

  @override
  String get alreadyAuthorized => '已授权';

  @override
  String get authorize => '授权';

  @override
  String get revokeAuthorization => '撤销授权';

  @override
  String get authorizationSuccessful => '授权成功！';

  @override
  String get failedToAuthorize => '授权失败。请重试。';

  @override
  String get authorizationRevoked => '授权已撤销。';

  @override
  String get recordingsDeleted => '录音已删除。';

  @override
  String get failedToRevoke => '无法撤销授权。';

  @override
  String get permissionRevokedTitle => '权限已撤销';

  @override
  String get permissionRevokedMessage => '您希望我们也删除您现有的所有录音吗？';

  @override
  String get yes => '是';

  @override
  String get editName => '编辑姓名';

  @override
  String get howShouldOmiCallYou => 'Omi 应该怎么称呼您？';

  @override
  String get enterYourName => '输入您的姓名';

  @override
  String get nameCannotBeEmpty => '姓名不能为空';

  @override
  String get nameUpdatedSuccessfully => '姓名更新成功！';

  @override
  String get calendarSettings => '日历设置';

  @override
  String get calendarProviders => '日历提供商';

  @override
  String get macOsCalendar => 'macOS 日历';

  @override
  String get connectMacOsCalendar => '连接您的本地 macOS 日历';

  @override
  String get googleCalendar => 'Google 日历';

  @override
  String get syncGoogleAccount => '与您的 Google 账户同步';

  @override
  String get showMeetingsMenuBar => '在菜单栏显示会议';

  @override
  String get showMeetingsMenuBarDesc => '在 macOS 菜单栏显示您的下一个会议和剩余时间';

  @override
  String get showEventsNoParticipants => '显示无参与者的事件';

  @override
  String get showEventsNoParticipantsDesc => '如果启用，“即将到来”将显示没有参与者或视频链接的事件。';

  @override
  String get yourMeetings => '您的会议';

  @override
  String get refresh => '刷新';

  @override
  String get noUpcomingMeetings => '没有即将到来的会议';

  @override
  String get checkingNextDays => '正在检查未来 30 天';

  @override
  String get tomorrow => '明天';

  @override
  String get googleCalendarComingSoon => 'Google 日历集成即将推出！';

  @override
  String connectedAsUser(String userId) {
    return '已作为用户连接：$userId';
  }

  @override
  String get defaultWorkspace => '默认工作区';

  @override
  String get tasksCreatedInWorkspace => '任务将在此工作区创建';

  @override
  String get defaultProjectOptional => '默认项目（可选）';

  @override
  String get leaveUnselectedTasks => '如果不选择，任务将没有项目';

  @override
  String get noProjectsInWorkspace => '在此工作区未找到项目';

  @override
  String get conversationTimeoutDesc => '选择静音多久后自动结束对话：';

  @override
  String get timeout2Minutes => '2 分钟';

  @override
  String get timeout2MinutesDesc => '静音 2 分钟后结束';

  @override
  String get timeout5Minutes => '5 分钟';

  @override
  String get timeout5MinutesDesc => '静音 5 分钟后结束';

  @override
  String get timeout10Minutes => '10 分钟';

  @override
  String get timeout10MinutesDesc => '静音 10 分钟后结束';

  @override
  String get timeout30Minutes => '30 分钟';

  @override
  String get timeout30MinutesDesc => '静音 30 分钟后结束';

  @override
  String get timeout4Hours => '4 小时';

  @override
  String get timeout4HoursDesc => '静音 4 小时后结束';

  @override
  String get conversationEndAfterHours => '对话将在静音 4 小时后结束';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return '对话将在静音 $minutes 分钟后结束';
  }

  @override
  String get tellUsPrimaryLanguage => '告诉我们您的主要语言';

  @override
  String get languageForTranscription => '设置您的语言以获得更清晰的转录。';

  @override
  String get singleLanguageModeInfo => '单一语言模式已开启。';

  @override
  String get searchLanguageHint => '按名称或代码搜索语言';

  @override
  String get noLanguagesFound => '未找到语言';

  @override
  String get skip => '跳过';

  @override
  String languageSetTo(String language) {
    return '语言已设置为 $language';
  }

  @override
  String get failedToSetLanguage => '无法设置语言';

  @override
  String appSettings(String appName) {
    return '$appName 设置';
  }

  @override
  String disconnectFromApp(String appName) {
    return '断开 $appName？';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return '这将删除您的 $appName 认证。';
  }

  @override
  String connectedToApp(String appName) {
    return '已连接到 $appName';
  }

  @override
  String get account => '账户';

  @override
  String actionItemsSyncedTo(String appName) {
    return '您的任务将同步到您的 $appName 账户';
  }

  @override
  String get defaultSpace => '默认空间';

  @override
  String get selectSpaceInWorkspace => '选择工作区中的空间';

  @override
  String get noSpacesInWorkspace => '未找到空间';

  @override
  String get defaultList => '默认列表';

  @override
  String get tasksAddedToList => '任务将添加到此列表';

  @override
  String get noListsInSpace => '未找到列表';

  @override
  String failedToLoadRepos(String error) {
    return '无法加载仓库：$error';
  }

  @override
  String get defaultRepoSaved => '默认仓库已保存';

  @override
  String get failedToSaveDefaultRepo => '无法保存默认仓库';

  @override
  String get defaultRepository => '默认仓库';

  @override
  String get selectDefaultRepoDesc => '选择创建 Issue 的默认仓库。';

  @override
  String get noReposFound => '未找到仓库';

  @override
  String get private => '私密';

  @override
  String updatedDate(String date) {
    return '更新于 $date';
  }

  @override
  String get yesterday => '昨天';

  @override
  String daysAgo(int count) {
    return '$count 天前';
  }

  @override
  String get oneWeekAgo => '1 周前';

  @override
  String weeksAgo(int count) {
    return '$count 周前';
  }

  @override
  String get oneMonthAgo => '1 个月前';

  @override
  String monthsAgo(int count) {
    return '$count 个月前';
  }

  @override
  String get issuesCreatedInRepo => 'Issue 将在默认仓库创建';

  @override
  String get taskIntegrations => '任务集成';

  @override
  String get configureSettings => '配置设置';

  @override
  String get completeAuthBrowser => '请在浏览器中完成身份验证。完成后，返回应用程序。';

  @override
  String failedToStartAppAuth(String appName) {
    return '无法启动 $appName 身份验证';
  }

  @override
  String connectToAppTitle(String appName) {
    return '连接到 $appName';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return '您需要授权 Omi 在您的 $appName 帐户中创建任务。这将打开您的浏览器进行身份验证。';
  }

  @override
  String get continueButton => '继续';

  @override
  String appIntegration(String appName) {
    return '$appName 集成';
  }

  @override
  String integrationComingSoon(String appName) {
    return '$appName 集成即将推出！';
  }

  @override
  String get gotIt => '知道了';

  @override
  String get tasksExportedOneApp => '任务一次只能导出一个应用。';

  @override
  String get completeYourUpgrade => '完成升级';

  @override
  String get importConfiguration => '导入配置';

  @override
  String get exportConfiguration => '导出配置';

  @override
  String get bringYourOwn => '自带';

  @override
  String get payYourSttProvider => '免费使用 Omi。您只需直接向 STT 提供商付费。';

  @override
  String get freeMinutesMonth => '包含 1,200 免费分钟/月。';

  @override
  String get omiUnlimited => 'Omi 无限版';

  @override
  String get hostRequired => '需要主机';

  @override
  String get validPortRequired => '需要有效端口';

  @override
  String get validWebsocketUrlRequired => '需要有效 WebSocket URL (wss://)';

  @override
  String get apiUrlRequired => '需要 API URL';

  @override
  String get apiKeyRequired => '需要 API 密钥';

  @override
  String get invalidJsonConfig => '无效的 JSON 配置';

  @override
  String errorSaving(String error) {
    return '保存时出错：$error';
  }

  @override
  String get configCopiedToClipboard => '配置已复制';

  @override
  String get pasteJsonConfig => '粘贴您的 JSON 配置：';

  @override
  String get addApiKeyAfterImport => '导入后必须添加您自己的 API 密钥';

  @override
  String get paste => '粘贴';

  @override
  String get import => '导入';

  @override
  String get invalidProviderInConfig => '配置中的提供商无效';

  @override
  String importedConfig(String providerName) {
    return '$providerName 配置已导入';
  }

  @override
  String invalidJson(String error) {
    return '无效的 JSON：$error';
  }

  @override
  String get provider => '提供商';

  @override
  String get live => '实时';

  @override
  String get onDevice => '设备端';

  @override
  String get apiUrl => 'API URL';

  @override
  String get enterSttHttpEndpoint => '输入您的 STT HTTP 端点';

  @override
  String get websocketUrl => 'WebSocket URL';

  @override
  String get enterLiveSttWebsocket => '输入您的实时 STT WebSocket 端点';

  @override
  String get apiKey => 'API密钥';

  @override
  String get enterApiKey => '输入您的 API 密钥';

  @override
  String get storedLocallyNeverShared => '本地存储，永不共享';

  @override
  String get host => '主机';

  @override
  String get port => '端口';

  @override
  String get advanced => '高级';

  @override
  String get configuration => '配置';

  @override
  String get requestConfiguration => '请求配置';

  @override
  String get responseSchema => '响应模式';

  @override
  String get modified => '已修改';

  @override
  String get resetRequestConfig => '重置请求配置';

  @override
  String get logs => '日志';

  @override
  String get logsCopied => '日志已复制';

  @override
  String get noLogsYet => '暂无日志。录音以查看活动。';

  @override
  String deviceUsesCodec(String device, String reason) {
    return '$device 使用 $reason。将使用 Omi。';
  }

  @override
  String get omiTranscription => 'Omi 转录';

  @override
  String get bestInClassTranscription => '一流的转录';

  @override
  String get instantSpeakerLabels => '即时说话人标签';

  @override
  String get languageTranslation => '100+ 语言翻译';

  @override
  String get optimizedForConversation => '为对话优化';

  @override
  String get autoLanguageDetection => '自动语言检测';

  @override
  String get highAccuracy => '高精度';

  @override
  String get privacyFirst => '隐私至上';

  @override
  String get saveChanges => '保存更改';

  @override
  String get resetToDefault => '重置为默认';

  @override
  String get viewTemplate => '查看模板';

  @override
  String get trySomethingLike => '试试类似...';

  @override
  String get tryIt => '试一试';

  @override
  String get creatingPlan => '创建计划';

  @override
  String get developingLogic => '开发逻辑';

  @override
  String get designingApp => '设计应用';

  @override
  String get generatingIconStep => '生成图标';

  @override
  String get finalTouches => '最后修饰';

  @override
  String get processing => '处理中...';

  @override
  String get features => '功能';

  @override
  String get creatingYourApp => '正在创建您的应用...';

  @override
  String get generatingIcon => '正在生成图标...';

  @override
  String get whatShouldWeMake => '我们应该做什么？';

  @override
  String get appName => 'App Name';

  @override
  String get description => '描述';

  @override
  String get publicLabel => '公开';

  @override
  String get privateLabel => '私有';

  @override
  String get free => '免费';

  @override
  String get perMonth => '/ 月';

  @override
  String get tailoredConversationSummaries => '定制对话摘要';

  @override
  String get customChatbotPersonality => '自定义聊天机器人个性';

  @override
  String get makePublic => '公开';

  @override
  String get anyoneCanDiscover => '任何人都可以发现您的应用';

  @override
  String get onlyYouCanUse => '只有您可以使用此应用';

  @override
  String get paidApp => '付费应用';

  @override
  String get usersPayToUse => '用户付费使用您的应用';

  @override
  String get freeForEveryone => '对所有人免费';

  @override
  String get perMonthLabel => '/ 月';

  @override
  String get creating => '创建中...';

  @override
  String get createApp => '创建应用';

  @override
  String get searchingForDevices => '正在搜索设备...';

  @override
  String devicesFoundNearby(int count) {
    return '附近发现 $count 个设备';
  }

  @override
  String get pairingSuccessful => '配对成功';

  @override
  String errorConnectingAppleWatch(String error) {
    return '连接 Apple Watch 出错：$error';
  }

  @override
  String get dontShowAgain => '不再显示';

  @override
  String get iUnderstand => '我理解';

  @override
  String get enableBluetooth => '启用蓝牙';

  @override
  String get bluetoothNeeded => 'Omi 需要蓝牙来连接您的穿戴设备。';

  @override
  String get contactSupport => '联系支持？';

  @override
  String get connectLater => '稍后连接';

  @override
  String get grantPermissions => '授予权限';

  @override
  String get backgroundActivity => '后台活动';

  @override
  String get backgroundActivityDesc => '允许 Omi 在后台运行以获得更好的稳定性';

  @override
  String get locationAccess => '位置权限';

  @override
  String get locationAccessDesc => '启用后台位置以获得完整体验';

  @override
  String get notifications => '通知';

  @override
  String get notificationsDesc => '启用通知以保持了解';

  @override
  String get locationServiceDisabled => '位置服务已禁用';

  @override
  String get locationServiceDisabledDesc => '请启用位置服务';

  @override
  String get backgroundLocationDenied => '后台位置权限被拒绝';

  @override
  String get backgroundLocationDeniedDesc => '请在设置中允许“始终”';

  @override
  String get lovingOmi => '喜欢 Omi 吗？';

  @override
  String get leaveReviewIos => '在 App Store 留下评论，帮助我们。';

  @override
  String get leaveReviewAndroid => '在 Google Play 留下评论，帮助我们。';

  @override
  String get rateOnAppStore => '在 App Store 评价';

  @override
  String get rateOnGooglePlay => '在 Google Play 评价';

  @override
  String get maybeLater => '稍后再说';

  @override
  String get speechProfileIntro => 'Omi需要学习您的目标和声音。您稍后可以修改它。';

  @override
  String get getStarted => '开始';

  @override
  String get allDone => '全部完成！';

  @override
  String get keepGoing => '继续加油';

  @override
  String get skipThisQuestion => '跳过此问题';

  @override
  String get skipForNow => '暂时跳过';

  @override
  String get connectionError => '连接错误';

  @override
  String get connectionErrorDesc => '无法连接到服务器。';

  @override
  String get invalidRecordingMultipleSpeakers => '无效录音';

  @override
  String get multipleSpeakersDesc => '似乎有多人说话。';

  @override
  String get tooShortDesc => '未检测到足够的语音。';

  @override
  String get invalidRecordingDesc => '请确保说话时间至少 5 秒。';

  @override
  String get areYouThere => '您在吗？';

  @override
  String get noSpeechDesc => '我们无法检测到语音。';

  @override
  String get connectionLost => '连接丢失';

  @override
  String get connectionLostDesc => '连接已丢失。';

  @override
  String get tryAgain => '重试';

  @override
  String get connectOmiOmiGlass => '连接 Omi / OmiGlass';

  @override
  String get continueWithoutDevice => '无设备继续';

  @override
  String get permissionsRequired => '需要权限';

  @override
  String get permissionsRequiredDesc => '需要蓝牙和位置权限。';

  @override
  String get openSettings => '打开设置';

  @override
  String get wantDifferentName => '想用不同的名字？';

  @override
  String get whatsYourName => '您叫什么名字？';

  @override
  String get speakTranscribeSummarize => '说话。转录。摘要。';

  @override
  String get signInWithApple => '通过 Apple 登录';

  @override
  String get signInWithGoogle => '通过 Google 登录';

  @override
  String get byContinuingAgree => '继续即表示您同意我们的 ';

  @override
  String get termsOfUse => '使用条款';

  @override
  String get omiYourAiCompanion => 'Omi – 您的 AI 伴侣';

  @override
  String get captureEveryMoment => '捕捉每一个瞬间。获得 AI 摘要。';

  @override
  String get appleWatchSetup => 'Apple Watch 设置';

  @override
  String get permissionRequestedExclaim => '已请求权限！';

  @override
  String get microphonePermission => '麦克风权限';

  @override
  String get permissionGrantedNow => '权限已授予！';

  @override
  String get needMicrophonePermission => '我们需要麦克风权限。';

  @override
  String get grantPermissionButton => '授予权限';

  @override
  String get needHelp => '需要帮助？';

  @override
  String get troubleshootingSteps => '故障排除步骤...';

  @override
  String get recordingStartedSuccessfully => '录音已成功开始！';

  @override
  String get permissionNotGrantedYet => '权限尚未授予。';

  @override
  String errorRequestingPermission(String error) {
    return '请求权限出错：$error';
  }

  @override
  String errorStartingRecording(String error) {
    return '开始录音出错：$error';
  }

  @override
  String get selectPrimaryLanguage => '选择主要语言';

  @override
  String get languageBenefits => '设置语言以获得更清晰的转录';

  @override
  String get whatsYourPrimaryLanguage => '您的主要语言是什么？';

  @override
  String get selectYourLanguage => '选择您的语言';

  @override
  String get personalGrowthJourney => '您的个人成长之旅，AI 倾听您的每一句话。';

  @override
  String get actionItemsTitle => '行动项';

  @override
  String get actionItemsDescription => '点击编辑 • 长按选择 •以此滑动';

  @override
  String get tabToDo => '待办';

  @override
  String get tabDone => '已完成';

  @override
  String get tabOld => '旧的';

  @override
  String get emptyTodoMessage => '🎉 全部完成！\n没有待办事项';

  @override
  String get emptyDoneMessage => '还没有已完成的项目';

  @override
  String get emptyOldMessage => '✅ 没有旧的任务';

  @override
  String get noItems => '无项目';

  @override
  String get actionItemMarkedIncomplete => '标记为未完成';

  @override
  String get actionItemCompleted => '任务已完成';

  @override
  String get deleteActionItemTitle => '删除操作项';

  @override
  String get deleteActionItemMessage => '您确定要删除此操作项吗？';

  @override
  String get deleteSelectedItemsTitle => '删除选中项';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return '您确定要删除 $count 个选中任务吗？';
  }

  @override
  String actionItemDeletedResult(String description) {
    return '任务 \"$description\" 已删除';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count 个任务已删除';
  }

  @override
  String get failedToDeleteItem => '无法删除任务';

  @override
  String get failedToDeleteItems => '无法删除项目';

  @override
  String get failedToDeleteSomeItems => '无法删除部分项目';

  @override
  String get welcomeActionItemsTitle => '准备好行动';

  @override
  String get welcomeActionItemsDescription => '您的 AI 会自动提取任务。';

  @override
  String get autoExtractionFeature => '从对话中自动提取';

  @override
  String get editSwipeFeature => '点击，滑动，管理';

  @override
  String itemsSelected(int count) {
    return '已选择 $count 项';
  }

  @override
  String get selectAll => '全选';

  @override
  String get deleteSelected => '删除选中';

  @override
  String get searchMemories => '搜索回忆...';

  @override
  String get memoryDeleted => '记忆已删除。';

  @override
  String get undo => '撤销';

  @override
  String get noMemoriesYet => '🧠 还没有回忆';

  @override
  String get noAutoMemories => '暂无自动记忆';

  @override
  String get noManualMemories => '暂无手动记忆';

  @override
  String get noMemoriesInCategories => '此类目无记忆';

  @override
  String get noMemoriesFound => '🔍 未找到回忆';

  @override
  String get addFirstMemory => '添加您的第一条记忆';

  @override
  String get clearMemoryTitle => '清除 Omi 记忆？';

  @override
  String get clearMemoryMessage => '您确定要清除 Omi 的记忆吗？此操作无法撤消。';

  @override
  String get clearMemoryButton => '清除记忆';

  @override
  String get memoryClearedSuccess => '记忆已清除';

  @override
  String get noMemoriesToDelete => '没有要删除的记忆';

  @override
  String get createMemoryTooltip => '创建新记忆';

  @override
  String get createActionItemTooltip => '创建新任务';

  @override
  String get memoryManagement => '记忆管理';

  @override
  String get filterMemories => '筛选记忆';

  @override
  String totalMemoriesCount(int count) {
    return '您共有 $count 条记忆';
  }

  @override
  String get publicMemories => '公开记忆';

  @override
  String get privateMemories => '私有记忆';

  @override
  String get makeAllPrivate => '全部设为私有';

  @override
  String get makeAllPublic => '全部设为公开';

  @override
  String get deleteAllMemories => '删除所有记忆';

  @override
  String get allMemoriesPrivateResult => '所有记忆现已私有';

  @override
  String get allMemoriesPublicResult => '所有记忆现已公开';

  @override
  String get newMemory => '✨ 新记忆';

  @override
  String get editMemory => '✏️ 编辑记忆';

  @override
  String get memoryContentHint => '我喜欢冰淇淋...';

  @override
  String get failedToSaveMemory => '保存失败。';

  @override
  String get saveMemory => '保存记忆';

  @override
  String get retry => '重试';

  @override
  String get createActionItem => '创建操作项';

  @override
  String get editActionItem => '编辑操作项';

  @override
  String get actionItemDescriptionHint => '有什么需要做的？';

  @override
  String get actionItemDescriptionEmpty => '描述不能为空。';

  @override
  String get actionItemUpdated => '任务已更新';

  @override
  String get failedToUpdateActionItem => '更新操作项失败';

  @override
  String get actionItemCreated => '任务已创建';

  @override
  String get failedToCreateActionItem => '创建操作项失败';

  @override
  String get dueDate => '截止日期';

  @override
  String get time => '时间';

  @override
  String get addDueDate => '添加截止日期';

  @override
  String get pressDoneToSave => '按完成保存';

  @override
  String get pressDoneToCreate => '按完成创建';

  @override
  String get filterAll => '全部';

  @override
  String get filterSystem => '关于你';

  @override
  String get filterInteresting => '见解';

  @override
  String get filterManual => '手动';

  @override
  String get completed => '已完成';

  @override
  String get markComplete => '标记为已完成';

  @override
  String get actionItemDeleted => '操作项已删除';

  @override
  String get failedToDeleteActionItem => '删除操作项失败';

  @override
  String get deleteActionItemConfirmTitle => '删除任务';

  @override
  String get deleteActionItemConfirmMessage => '您确定要删除此任务吗？';

  @override
  String get appLanguage => '应用语言';

  @override
  String get appInterfaceSectionTitle => '应用界面';

  @override
  String get speechTranscriptionSectionTitle => '语音与转录';

  @override
  String get languageSettingsHelperText => '应用语言更改菜单和按钮。语音语言影响录音的转录方式。';

  @override
  String get translationNotice => '翻译通知';

  @override
  String get translationNoticeMessage => 'Omi 将对话翻译成您的主要语言。您可以随时在设置→个人资料中更新。';

  @override
  String get pleaseCheckInternetConnection => '请检查您的互联网连接并重试';

  @override
  String get pleaseSelectReason => '请选择原因';

  @override
  String get tellUsMoreWhatWentWrong => '告诉我们更多出了什么问题...';

  @override
  String get selectText => '选择文本';

  @override
  String maximumGoalsAllowed(int count) {
    return '最多允许$count个目标';
  }

  @override
  String get conversationCannotBeMerged => '无法合并此对话（已锁定或正在合并）';

  @override
  String get pleaseEnterFolderName => '请输入文件夹名称';

  @override
  String get failedToCreateFolder => '创建文件夹失败';

  @override
  String get failedToUpdateFolder => '更新文件夹失败';

  @override
  String get folderName => '文件夹名称';

  @override
  String get descriptionOptional => 'Description (optional)';

  @override
  String get failedToDeleteFolder => '删除文件夹失败';

  @override
  String get editFolder => '编辑文件夹';

  @override
  String get deleteFolder => '删除文件夹';

  @override
  String get transcriptCopiedToClipboard => '转录已复制到剪贴板';

  @override
  String get summaryCopiedToClipboard => '摘要已复制到剪贴板';

  @override
  String get conversationUrlCouldNotBeShared => '无法分享对话链接。';

  @override
  String get urlCopiedToClipboard => '网址已复制到剪贴板';

  @override
  String get exportTranscript => '导出转录';

  @override
  String get exportSummary => '导出摘要';

  @override
  String get exportButton => '导出';

  @override
  String get actionItemsCopiedToClipboard => '行动项已复制到剪贴板';

  @override
  String get summarize => '总结';

  @override
  String get generateSummary => '生成总结';

  @override
  String get conversationNotFoundOrDeleted => '未找到对话或已被删除';

  @override
  String get deleteMemory => '删除记忆';

  @override
  String get thisActionCannotBeUndone => '此操作无法撤消。';

  @override
  String memoriesCount(int count) {
    return '$count个回忆';
  }

  @override
  String get noMemoriesInCategory => '此类别中还没有回忆';

  @override
  String get addYourFirstMemory => '添加您的第一个回忆';

  @override
  String get firmwareDisconnectUsb => '断开USB';

  @override
  String get firmwareUsbWarning => '更新期间的USB连接可能会损坏您的设备。';

  @override
  String get firmwareBatteryAbove15 => '电量高于15%';

  @override
  String get firmwareEnsureBattery => '确保您的设备有15%的电量。';

  @override
  String get firmwareStableConnection => '稳定连接';

  @override
  String get firmwareConnectWifi => '连接到WiFi或移动数据。';

  @override
  String failedToStartUpdate(String error) {
    return '启动更新失败: $error';
  }

  @override
  String get beforeUpdateMakeSure => '更新前，请确保:';

  @override
  String get confirmed => '已确认！';

  @override
  String get release => '释放';

  @override
  String get slideToUpdate => '滑动以更新';

  @override
  String copiedToClipboard(String title) {
    return '$title已复制到剪贴板';
  }

  @override
  String get batteryLevel => '电池电量';

  @override
  String get productUpdate => '产品更新';

  @override
  String get offline => '离线';

  @override
  String get available => '可用';

  @override
  String get unpairDeviceDialogTitle => '取消配对设备';

  @override
  String get unpairDeviceDialogMessage => '这将取消设备配对，以便可以连接到另一部手机。您需要转到设置 > 蓝牙并忘记设备以完成该过程。';

  @override
  String get unpair => '取消配对';

  @override
  String get unpairAndForgetDevice => '取消配对并忘记设备';

  @override
  String get unknownDevice => '未知设备';

  @override
  String get unknown => '未知';

  @override
  String get productName => '产品名称';

  @override
  String get serialNumber => '序列号';

  @override
  String get connected => '已连接';

  @override
  String get privacyPolicyTitle => '隐私政策';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label 已复制';
  }

  @override
  String get noApiKeysYet => '还没有API密钥。创建一个以与您的应用集成。';

  @override
  String get createKeyToGetStarted => '创建密钥以开始';

  @override
  String get persona => '人格';

  @override
  String get configureYourAiPersona => '配置您的 AI 角色';

  @override
  String get configureSttProvider => '配置 STT 提供商';

  @override
  String get setWhenConversationsAutoEnd => '设置对话自动结束时间';

  @override
  String get importDataFromOtherSources => '从其他来源导入数据';

  @override
  String get debugAndDiagnostics => '调试和诊断';

  @override
  String get autoDeletesAfter3Days => '3 天后自动删除';

  @override
  String get helpsDiagnoseIssues => '帮助诊断问题';

  @override
  String get exportStartedMessage => '导出已开始。这可能需要几秒钟...';

  @override
  String get exportConversationsToJson => '将对话导出为 JSON 文件';

  @override
  String get knowledgeGraphDeletedSuccess => '知识图谱删除成功';

  @override
  String failedToDeleteGraph(String error) {
    return '删除图谱失败：$error';
  }

  @override
  String get clearAllNodesAndConnections => '清除所有节点和连接';

  @override
  String get addToClaudeDesktopConfig => '添加到 claude_desktop_config.json';

  @override
  String get connectAiAssistantsToData => '将 AI 助手连接到您的数据';

  @override
  String get useYourMcpApiKey => '使用您的 MCP API 密钥';

  @override
  String get realTimeTranscript => '实时转录';

  @override
  String get experimental => '实验性';

  @override
  String get transcriptionDiagnostics => '转录诊断';

  @override
  String get detailedDiagnosticMessages => '详细诊断消息';

  @override
  String get autoCreateSpeakers => '自动创建说话者';

  @override
  String get autoCreateWhenNameDetected => '检测到名称时自动创建';

  @override
  String get followUpQuestions => '后续问题';

  @override
  String get suggestQuestionsAfterConversations => '对话后建议问题';

  @override
  String get goalTracker => '目标追踪器';

  @override
  String get trackPersonalGoalsOnHomepage => '在主页上跟踪您的个人目标';

  @override
  String get dailyReflection => '每日反思';

  @override
  String get get9PmReminderToReflect => '在晚上 9 点收到提醒，回顾您的一天';

  @override
  String get actionItemDescriptionCannotBeEmpty => '操作项描述不能为空';

  @override
  String get saved => '已保存';

  @override
  String get overdue => '已逾期';

  @override
  String get failedToUpdateDueDate => '更新截止日期失败';

  @override
  String get markIncomplete => '标记为未完成';

  @override
  String get editDueDate => '编辑截止日期';

  @override
  String get setDueDate => '设置截止日期';

  @override
  String get clearDueDate => '清除截止日期';

  @override
  String get failedToClearDueDate => '清除截止日期失败';

  @override
  String get mondayAbbr => '周一';

  @override
  String get tuesdayAbbr => '周二';

  @override
  String get wednesdayAbbr => '周三';

  @override
  String get thursdayAbbr => '周四';

  @override
  String get fridayAbbr => '周五';

  @override
  String get saturdayAbbr => '周六';

  @override
  String get sundayAbbr => '周日';

  @override
  String get howDoesItWork => '它是如何工作的？';

  @override
  String get sdCardSyncDescription => 'SD卡同步将从SD卡导入您的回忆到应用程序';

  @override
  String get checksForAudioFiles => '检查SD卡上的音频文件';

  @override
  String get omiSyncsAudioFiles => 'Omi然后将音频文件与服务器同步';

  @override
  String get serverProcessesAudio => '服务器处理音频文件并创建回忆';

  @override
  String get youreAllSet => '一切就绪！';

  @override
  String get welcomeToOmiDescription => '欢迎来到Omi！您的AI伴侣已准备好帮助您进行对话、任务等。';

  @override
  String get startUsingOmi => '开始使用Omi';

  @override
  String get back => '返回';

  @override
  String get keyboardShortcuts => '键盘快捷键';

  @override
  String get toggleControlBar => '切换控制栏';

  @override
  String get pressKeys => '按下按键...';

  @override
  String get cmdRequired => '⌘ 必需';

  @override
  String get invalidKey => '无效按键';

  @override
  String get space => '空格';

  @override
  String get search => '搜索';

  @override
  String get searchPlaceholder => '搜索...';

  @override
  String get untitledConversation => '无标题对话';

  @override
  String countRemaining(String count) {
    return '$count 剩余';
  }

  @override
  String get addGoal => '添加目标';

  @override
  String get editGoal => '编辑目标';

  @override
  String get icon => '图标';

  @override
  String get goalTitle => '目标标题';

  @override
  String get current => '当前';

  @override
  String get target => '目标';

  @override
  String get saveGoal => '保存';

  @override
  String get goals => '目标';

  @override
  String get tapToAddGoal => '点击添加目标';

  @override
  String welcomeBack(String name) {
    return '欢迎回来，$name';
  }

  @override
  String get yourConversations => '你的对话';

  @override
  String get reviewAndManageConversations => '查看和管理已录制的对话';

  @override
  String get startCapturingConversations => '开始使用您的Omi设备捕获对话以在此处查看。';

  @override
  String get useMobileAppToCapture => '使用您的移动应用程序捕获音频';

  @override
  String get conversationsProcessedAutomatically => '对话会自动处理';

  @override
  String get getInsightsInstantly => '立即获取见解和摘要';

  @override
  String get showAll => '显示全部 →';

  @override
  String get noTasksForToday => '今天没有任务。\\n向Omi询问更多任务或手动创建。';

  @override
  String get dailyScore => '每日评分';

  @override
  String get dailyScoreDescription => '帮助您更好地专注于\n执行的评分。';

  @override
  String get searchResults => '搜索结果';

  @override
  String get actionItems => '待办事项';

  @override
  String get tasksToday => '今天';

  @override
  String get tasksTomorrow => '明天';

  @override
  String get tasksNoDeadline => '无截止日期';

  @override
  String get tasksLater => '稍后';

  @override
  String get loadingTasks => '正在加载任务...';

  @override
  String get tasks => '任务';

  @override
  String get swipeTasksToIndent => '滑动任务以缩进，在类别之间拖动';

  @override
  String get create => '创建';

  @override
  String get noTasksYet => '暂无任务';

  @override
  String get tasksFromConversationsWillAppear => '您的对话中的任务将显示在此处。\n单击创建以手动添加一个。';

  @override
  String get monthJan => '1月';

  @override
  String get monthFeb => '2月';

  @override
  String get monthMar => '3月';

  @override
  String get monthApr => '4月';

  @override
  String get monthMay => '5月';

  @override
  String get monthJun => '6月';

  @override
  String get monthJul => '7月';

  @override
  String get monthAug => '8月';

  @override
  String get monthSep => '9月';

  @override
  String get monthOct => '10月';

  @override
  String get monthNov => '11月';

  @override
  String get monthDec => '12月';

  @override
  String get timePM => '下午';

  @override
  String get timeAM => '上午';

  @override
  String get actionItemUpdatedSuccessfully => '操作项已成功更新';

  @override
  String get actionItemCreatedSuccessfully => '操作项已成功创建';

  @override
  String get actionItemDeletedSuccessfully => '操作项已成功删除';

  @override
  String get deleteActionItem => '删除操作项';

  @override
  String get deleteActionItemConfirmation => '您确定要删除此操作项吗？此操作无法撤消。';

  @override
  String get enterActionItemDescription => '输入操作项描述...';

  @override
  String get markAsCompleted => '标记为已完成';

  @override
  String get setDueDateAndTime => '设置截止日期和时间';

  @override
  String get reloadingApps => '正在重新加载应用...';

  @override
  String get loadingApps => '正在加载应用...';

  @override
  String get browseInstallCreateApps => '浏览、安装和创建应用';

  @override
  String get all => '全部';

  @override
  String get open => '打开';

  @override
  String get install => '安装';

  @override
  String get noAppsAvailable => '无可用应用';

  @override
  String get unableToLoadApps => '无法加载应用';

  @override
  String get tryAdjustingSearchTermsOrFilters => '尝试调整您的搜索词或筛选条件';

  @override
  String get checkBackLaterForNewApps => '稍后查看新应用';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => '请检查您的网络连接并重试';

  @override
  String get createNewApp => '创建新应用';

  @override
  String get buildSubmitCustomOmiApp => '构建并提交您的自定义 Omi 应用';

  @override
  String get submittingYourApp => '正在提交您的应用...';

  @override
  String get preparingFormForYou => '正在为您准备表单...';

  @override
  String get appDetails => '应用详情';

  @override
  String get paymentDetails => '支付详情';

  @override
  String get previewAndScreenshots => '预览和截图';

  @override
  String get appCapabilities => '应用功能';

  @override
  String get aiPrompts => 'AI 提示';

  @override
  String get chatPrompt => '聊天提示';

  @override
  String get chatPromptPlaceholder => '您是一个很棒的应用程序，您的工作是回答用户查询并让他们感觉良好...';

  @override
  String get conversationPrompt => '对话提示';

  @override
  String get conversationPromptPlaceholder => '您是一个很棒的应用程序，您将获得对话的文字记录和摘要...';

  @override
  String get notificationScopes => '通知范围';

  @override
  String get appPrivacyAndTerms => '应用隐私与条款';

  @override
  String get makeMyAppPublic => '公开我的应用';

  @override
  String get submitAppTermsAgreement => '提交此应用即表示我同意 Omi AI 的服务条款和隐私政策';

  @override
  String get submitApp => '提交应用';

  @override
  String get needHelpGettingStarted => '需要入门帮助吗？';

  @override
  String get clickHereForAppBuildingGuides => '点击此处查看应用构建指南和文档';

  @override
  String get submitAppQuestion => '提交应用？';

  @override
  String get submitAppPublicDescription => '您的应用将被审核并公开。即使在审核期间，您也可以立即开始使用它！';

  @override
  String get submitAppPrivateDescription => '您的应用将被审核并私下提供给您。即使在审核期间，您也可以立即开始使用它！';

  @override
  String get startEarning => '开始赚钱！💰';

  @override
  String get connectStripeOrPayPal => '连接 Stripe 或 PayPal 以接收您的应用付款。';

  @override
  String get connectNow => '立即连接';

  @override
  String get installsCount => '安装量';

  @override
  String get uninstallApp => '卸载应用';

  @override
  String get subscribe => '订阅';

  @override
  String get dataAccessNotice => '数据访问通知';

  @override
  String get dataAccessWarning => '此应用将访问您的数据。Omi AI 不对此应用如何使用、修改或删除您的数据负责';

  @override
  String get installApp => '安装应用';

  @override
  String get betaTesterNotice => '您是此应用的测试版测试者。它尚未公开。获得批准后将公开。';

  @override
  String get appUnderReviewOwner => '您的应用正在审核中,仅对您可见。获得批准后将公开。';

  @override
  String get appRejectedNotice => '您的应用已被拒绝。请更新应用详情并重新提交审核。';

  @override
  String get setupSteps => '设置步骤';

  @override
  String get setupInstructions => '设置说明';

  @override
  String get integrationInstructions => '集成说明';

  @override
  String get preview => '预览';

  @override
  String get aboutTheApp => '关于应用';

  @override
  String get aboutThePersona => '关于人格';

  @override
  String get chatPersonality => '聊天个性';

  @override
  String get ratingsAndReviews => '评分和评论';

  @override
  String get noRatings => '暂无评分';

  @override
  String ratingsCount(String count) {
    return '$count+条评分';
  }

  @override
  String get errorActivatingApp => '激活应用时出错';

  @override
  String get integrationSetupRequired => '如果这是集成应用,请确保设置已完成。';

  @override
  String get installed => '已安装';

  @override
  String get appIdLabel => '应用ID';

  @override
  String get appNameLabel => '应用名称';

  @override
  String get appNamePlaceholder => '我的出色应用';

  @override
  String get pleaseEnterAppName => '请输入应用名称';

  @override
  String get categoryLabel => '类别';

  @override
  String get selectCategory => '选择类别';

  @override
  String get descriptionLabel => '描述';

  @override
  String get appDescriptionPlaceholder => '我的出色应用是一个做出惊人事情的出色应用。这是最好的应用！';

  @override
  String get pleaseProvideValidDescription => '请提供有效描述';

  @override
  String get appPricingLabel => '应用定价';

  @override
  String get noneSelected => '未选择';

  @override
  String get appIdCopiedToClipboard => '应用ID已复制到剪贴板';

  @override
  String get appCategoryModalTitle => '应用类别';

  @override
  String get pricingFree => '免费';

  @override
  String get pricingPaid => '付费';

  @override
  String get loadingCapabilities => '正在加载功能...';

  @override
  String get filterInstalled => '已安装';

  @override
  String get filterMyApps => '我的应用';

  @override
  String get clearSelection => '清除选择';

  @override
  String get filterCategory => '类别';

  @override
  String get rating4PlusStars => '4+星';

  @override
  String get rating3PlusStars => '3+星';

  @override
  String get rating2PlusStars => '2+星';

  @override
  String get rating1PlusStars => '1+星';

  @override
  String get filterRating => '评分';

  @override
  String get filterCapabilities => '功能';

  @override
  String get noNotificationScopesAvailable => '没有可用的通知范围';

  @override
  String get popularApps => '热门应用';

  @override
  String get pleaseProvidePrompt => '请提供提示';

  @override
  String chatWithAppName(String appName) {
    return '与 $appName 聊天';
  }

  @override
  String get defaultAiAssistant => '默认 AI 助手';

  @override
  String get readyToChat => '✨ 准备好聊天！';

  @override
  String get connectionNeeded => '🌐 需要连接';

  @override
  String get startConversation => '开始对话，让魔法开始';

  @override
  String get checkInternetConnection => '请检查您的互联网连接';

  @override
  String get wasThisHelpful => '这有帮助吗？';

  @override
  String get thankYouForFeedback => '感谢您的反馈！';

  @override
  String get maxFilesUploadError => '一次只能上传 4 个文件';

  @override
  String get attachedFiles => '📎 附件';

  @override
  String get takePhoto => '拍照';

  @override
  String get captureWithCamera => '用相机捕获';

  @override
  String get selectImages => '选择图像';

  @override
  String get chooseFromGallery => '从图库选择';

  @override
  String get selectFile => '选择文件';

  @override
  String get chooseAnyFileType => '选择任何文件类型';

  @override
  String get cannotReportOwnMessages => '您不能举报自己的消息';

  @override
  String get messageReportedSuccessfully => '✅ 消息举报成功';

  @override
  String get confirmReportMessage => '您确定要举报此消息吗？';

  @override
  String get selectChatAssistant => '选择聊天助手';

  @override
  String get enableMoreApps => '启用更多应用';

  @override
  String get chatCleared => '聊天已清除';

  @override
  String get clearChatTitle => '清除聊天？';

  @override
  String get confirmClearChat => '您确定要清除聊天吗？此操作无法撤销。';

  @override
  String get copy => '复制';

  @override
  String get share => '分享';

  @override
  String get report => '举报';

  @override
  String get microphonePermissionRequired => '录音需要麦克风权限。';

  @override
  String get microphonePermissionDenied => '麦克风权限被拒绝。请在系统偏好设置 > 隐私与安全 > 麦克风 中授予权限。';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return '检查麦克风权限失败：$error';
  }

  @override
  String get failedToTranscribeAudio => '音频转录失败';

  @override
  String get transcribing => '正在转录...';

  @override
  String get transcriptionFailed => '转录失败';

  @override
  String get discardedConversation => '已丢弃的对话';

  @override
  String get at => '于';

  @override
  String get from => '从';

  @override
  String get copied => '已复制！';

  @override
  String get copyLink => '复制链接';

  @override
  String get hideTranscript => '隐藏文字记录';

  @override
  String get viewTranscript => '查看文字记录';

  @override
  String get conversationDetails => '对话详情';

  @override
  String get transcript => '文字记录';

  @override
  String segmentsCount(int count) {
    return '$count个片段';
  }

  @override
  String get noTranscriptAvailable => '没有可用的文字记录';

  @override
  String get noTranscriptMessage => '此对话没有文字记录。';

  @override
  String get conversationUrlCouldNotBeGenerated => '无法生成对话URL。';

  @override
  String get failedToGenerateConversationLink => '生成对话链接失败';

  @override
  String get failedToGenerateShareLink => '生成分享链接失败';

  @override
  String get reloadingConversations => '重新加载对话...';

  @override
  String get user => '用户';

  @override
  String get starred => '已收藏';

  @override
  String get date => '日期';

  @override
  String get noResultsFound => '未找到结果';

  @override
  String get tryAdjustingSearchTerms => '尝试调整您的搜索词';

  @override
  String get starConversationsToFindQuickly => '为对话加星标以便在此快速找到它们';

  @override
  String noConversationsOnDate(String date) {
    return '$date没有对话';
  }

  @override
  String get trySelectingDifferentDate => '尝试选择其他日期';

  @override
  String get conversations => '对话';

  @override
  String get chat => '聊天';

  @override
  String get actions => '操作';

  @override
  String get syncAvailable => '可同步';

  @override
  String get referAFriend => '推荐好友';

  @override
  String get help => '帮助';

  @override
  String get pro => '专业版';

  @override
  String get upgradeToPro => '升级至Pro';

  @override
  String get getOmiDevice => '获取 Omi 设备';

  @override
  String get wearableAiCompanion => '可穿戴AI伴侣';

  @override
  String get loadingMemories => '加载回忆中...';

  @override
  String get allMemories => '所有回忆';

  @override
  String get aboutYou => '关于你';

  @override
  String get manual => '手动';

  @override
  String get loadingYourMemories => '正在加载您的回忆...';

  @override
  String get createYourFirstMemory => '创建您的第一个回忆以开始';

  @override
  String get tryAdjustingFilter => '尝试调整您的搜索或筛选条件';

  @override
  String get whatWouldYouLikeToRemember => '您想记住什么？';

  @override
  String get category => '类别';

  @override
  String get public => '公开';

  @override
  String get failedToSaveCheckConnection => '保存失败。请检查您的连接。';

  @override
  String get createMemory => '创建记忆';

  @override
  String get deleteMemoryConfirmation => '您确定要删除此记忆吗？此操作无法撤消。';

  @override
  String get makePrivate => '私密';

  @override
  String get organizeAndControlMemories => '整理和控制您的记忆';

  @override
  String get total => '总计';

  @override
  String get makeAllMemoriesPrivate => '将所有记忆设为私密';

  @override
  String get setAllMemoriesToPrivate => '将所有记忆设置为私密可见性';

  @override
  String get makeAllMemoriesPublic => '将所有记忆设为公开';

  @override
  String get setAllMemoriesToPublic => '将所有记忆设置为公开可见性';

  @override
  String get permanentlyRemoveAllMemories => '从 Omi 永久删除所有记忆';

  @override
  String get allMemoriesAreNowPrivate => '所有记忆现已私密';

  @override
  String get allMemoriesAreNowPublic => '所有记忆现已公开';

  @override
  String get clearOmisMemory => '清除 Omi 的记忆';

  @override
  String clearMemoryConfirmation(int count) {
    return '您确定要清除 Omi 的记忆吗？此操作无法撤消，将永久删除所有 $count 条记忆。';
  }

  @override
  String get omisMemoryCleared => 'Omi 关于您的记忆已被清除';

  @override
  String get welcomeToOmi => '欢迎来到 Omi';

  @override
  String get continueWithApple => '使用 Apple 继续';

  @override
  String get continueWithGoogle => '使用 Google 继续';

  @override
  String get byContinuingYouAgree => '继续即表示您同意我们的';

  @override
  String get termsOfService => '服务条款';

  @override
  String get and => '和';

  @override
  String get dataAndPrivacy => '数据与隐私';

  @override
  String get secureAuthViaAppleId => '通过 Apple ID 安全认证';

  @override
  String get secureAuthViaGoogleAccount => '通过 Google 账户安全认证';

  @override
  String get whatWeCollect => '我们收集的信息';

  @override
  String get dataCollectionMessage => '继续即表示您的对话、录音和个人信息将安全地存储在我们的服务器上，以提供 AI 驱动的见解并启用所有应用功能。';

  @override
  String get dataProtection => '数据保护';

  @override
  String get yourDataIsProtected => '您的数据受保护并受我们的';

  @override
  String get pleaseSelectYourPrimaryLanguage => '请选择您的主要语言';

  @override
  String get chooseYourLanguage => '选择您的语言';

  @override
  String get selectPreferredLanguageForBestExperience => '选择您的首选语言以获得最佳 Omi 体验';

  @override
  String get searchLanguages => '搜索语言...';

  @override
  String get selectALanguage => '选择语言';

  @override
  String get tryDifferentSearchTerm => '尝试不同的搜索词';

  @override
  String get pleaseEnterYourName => '请输入您的姓名';

  @override
  String get nameMustBeAtLeast2Characters => '姓名必须至少包含2个字符';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed => '告诉我们您希望如何称呼您。这有助于个性化您的 Omi 体验。';

  @override
  String charactersCount(int count) {
    return '$count个字符';
  }

  @override
  String get enableFeaturesForBestExperience => '启用功能以在您的设备上获得最佳 Omi 体验。';

  @override
  String get microphoneAccess => '麦克风访问';

  @override
  String get recordAudioConversations => '录制音频对话';

  @override
  String get microphoneAccessDescription => 'Omi 需要麦克风访问权限来录制您的对话并提供转录。';

  @override
  String get screenRecording => '屏幕录制';

  @override
  String get captureSystemAudioFromMeetings => '从会议中捕获系统音频';

  @override
  String get screenRecordingDescription => 'Omi 需要屏幕录制权限来从基于浏览器的会议中捕获系统音频。';

  @override
  String get accessibility => '辅助功能';

  @override
  String get detectBrowserBasedMeetings => '检测基于浏览器的会议';

  @override
  String get accessibilityDescription => 'Omi 需要辅助功能权限来检测您何时在浏览器中加入 Zoom、Meet 或 Teams 会议。';

  @override
  String get pleaseWait => '请稍候...';

  @override
  String get joinTheCommunity => '加入社区！';

  @override
  String get loadingProfile => '正在加载个人资料...';

  @override
  String get profileSettings => '个人资料设置';

  @override
  String get noEmailSet => '未设置电子邮件';

  @override
  String get userIdCopiedToClipboard => '用户 ID 已复制';

  @override
  String get yourInformation => '您的信息';

  @override
  String get setYourName => '设置您的姓名';

  @override
  String get changeYourName => '更改您的姓名';

  @override
  String get manageYourOmiPersona => '管理您的 Omi 人格';

  @override
  String get voiceAndPeople => '语音与人物';

  @override
  String get teachOmiYourVoice => '教 Omi 您的声音';

  @override
  String get tellOmiWhoSaidIt => '告诉 Omi 谁说的 🗣️';

  @override
  String get payment => '付款';

  @override
  String get addOrChangeYourPaymentMethod => '添加或更改付款方式';

  @override
  String get preferences => '偏好设置';

  @override
  String get helpImproveOmiBySharing => '通过分享匿名分析数据帮助改进 Omi';

  @override
  String get deleteAccount => '删除账户';

  @override
  String get deleteYourAccountAndAllData => '删除您的账户和所有数据';

  @override
  String get clearLogs => '清除日志';

  @override
  String get debugLogsCleared => '调试日志已清除';

  @override
  String get exportConversations => '导出对话';

  @override
  String get exportAllConversationsToJson => '将所有对话导出到JSON文件。';

  @override
  String get conversationsExportStarted => '对话导出已开始。这可能需要几秒钟，请稍候。';

  @override
  String get mcpDescription => '将Omi与其他应用程序连接以读取、搜索和管理您的记忆和对话。创建密钥以开始。';

  @override
  String get apiKeys => 'API密钥';

  @override
  String errorLabel(String error) {
    return '错误：$error';
  }

  @override
  String get noApiKeysFound => '未找到API密钥。创建一个以开始。';

  @override
  String get advancedSettings => '高级设置';

  @override
  String get triggersWhenNewConversationCreated => '创建新对话时触发。';

  @override
  String get triggersWhenNewTranscriptReceived => '收到新转录时触发。';

  @override
  String get realtimeAudioBytes => '实时音频字节';

  @override
  String get triggersWhenAudioBytesReceived => '收到音频字节时触发。';

  @override
  String get everyXSeconds => '每x秒';

  @override
  String get triggersWhenDaySummaryGenerated => '生成每日摘要时触发。';

  @override
  String get tryLatestExperimentalFeatures => '尝试Omi团队的最新实验性功能。';

  @override
  String get transcriptionServiceDiagnosticStatus => '转录服务诊断状态';

  @override
  String get enableDetailedDiagnosticMessages => '启用来自转录服务的详细诊断消息';

  @override
  String get autoCreateAndTagNewSpeakers => '自动创建和标记新发言人';

  @override
  String get automaticallyCreateNewPerson => '在转录中检测到姓名时自动创建新人员。';

  @override
  String get pilotFeatures => '试点功能';

  @override
  String get pilotFeaturesDescription => '这些功能是测试版本，不保证支持。';

  @override
  String get suggestFollowUpQuestion => '建议后续问题';

  @override
  String get saveSettings => '保存设置';

  @override
  String get syncingDeveloperSettings => '正在同步开发者设置...';

  @override
  String get summary => '摘要';

  @override
  String get auto => '自动';

  @override
  String get noSummaryForApp => '此应用没有可用的摘要。请尝试其他应用以获得更好的结果。';

  @override
  String get tryAnotherApp => '尝试其他应用';

  @override
  String generatedBy(String appName) {
    return '由 $appName 生成';
  }

  @override
  String get overview => '概述';

  @override
  String get otherAppResults => '其他应用结果';

  @override
  String get unknownApp => '未知应用';

  @override
  String get noSummaryAvailable => '没有可用的摘要';

  @override
  String get conversationNoSummaryYet => '此对话还没有摘要。';

  @override
  String get chooseSummarizationApp => '选择摘要应用';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName 已设置为默认摘要应用';
  }

  @override
  String get letOmiChooseAutomatically => '让 Omi 自动选择最佳应用';

  @override
  String get deleteConversationConfirmation => '您确定要删除此对话吗？此操作无法撤销。';

  @override
  String get conversationDeleted => '对话已删除';

  @override
  String get generatingLink => '正在生成链接...';

  @override
  String get editConversation => '编辑对话';

  @override
  String get conversationLinkCopiedToClipboard => '对话链接已复制到剪贴板';

  @override
  String get conversationTranscriptCopiedToClipboard => '对话记录已复制到剪贴板';

  @override
  String get editConversationDialogTitle => '编辑对话';

  @override
  String get changeTheConversationTitle => '更改对话标题';

  @override
  String get conversationTitle => '对话标题';

  @override
  String get enterConversationTitle => '输入对话标题...';

  @override
  String get conversationTitleUpdatedSuccessfully => '对话标题更新成功';

  @override
  String get failedToUpdateConversationTitle => '对话标题更新失败';

  @override
  String get errorUpdatingConversationTitle => '更新对话标题时出错';

  @override
  String get settingUp => '设置中...';

  @override
  String get startYourFirstRecording => '开始您的第一次录音';

  @override
  String get preparingSystemAudioCapture => '正在准备系统音频捕获';

  @override
  String get clickTheButtonToCaptureAudio => '点击按钮以捕获音频，用于实时转录、AI 洞察和自动保存。';

  @override
  String get reconnecting => '重新连接中...';

  @override
  String get recordingPaused => '录音已暂停';

  @override
  String get recordingActive => '录音活跃';

  @override
  String get startRecording => '开始录音';

  @override
  String resumingInCountdown(String countdown) {
    return '将在 $countdown 秒后恢复...';
  }

  @override
  String get tapPlayToResume => '点击播放以恢复';

  @override
  String get listeningForAudio => '正在监听音频...';

  @override
  String get preparingAudioCapture => '正在准备音频捕获';

  @override
  String get clickToBeginRecording => '点击开始录音';

  @override
  String get translated => '已翻译';

  @override
  String get liveTranscript => '实时转录';

  @override
  String segmentsSingular(String count) {
    return '$count 个片段';
  }

  @override
  String segmentsPlural(String count) {
    return '$count 个片段';
  }

  @override
  String get startRecordingToSeeTranscript => '开始录音以查看实时转录';

  @override
  String get paused => '已暂停';

  @override
  String get initializing => '初始化中...';

  @override
  String get recording => '录音中';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return '麦克风已更改。将在 $countdown 秒后恢复';
  }

  @override
  String get clickPlayToResumeOrStop => '点击播放以恢复或停止以完成';

  @override
  String get settingUpSystemAudioCapture => '正在设置系统音频捕获';

  @override
  String get capturingAudioAndGeneratingTranscript => '正在捕获音频并生成转录';

  @override
  String get clickToBeginRecordingSystemAudio => '点击开始录制系统音频';

  @override
  String get you => '您';

  @override
  String speakerWithId(String speakerId) {
    return '发言者 $speakerId';
  }

  @override
  String get translatedByOmi => '由 omi 翻译';

  @override
  String get backToConversations => '返回对话';

  @override
  String get systemAudio => '系统';

  @override
  String get mic => '麦克风';

  @override
  String audioInputSetTo(String deviceName) {
    return '音频输入已设置为 $deviceName';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return '切换音频设备时出错：$error';
  }

  @override
  String get selectAudioInput => '选择音频输入';

  @override
  String get loadingDevices => '正在加载设备...';

  @override
  String get settingsHeader => '设置';

  @override
  String get plansAndBilling => '计划与账单';

  @override
  String get calendarIntegration => '日历集成';

  @override
  String get dailySummary => '每日总结';

  @override
  String get developer => '开发者';

  @override
  String get about => '关于';

  @override
  String get selectTime => '选择时间';

  @override
  String get accountGroup => '账户';

  @override
  String get signOutQuestion => '退出登录？';

  @override
  String get signOutConfirmation => '您确定要退出登录吗？';

  @override
  String get customVocabularyHeader => '自定义词汇';

  @override
  String get addWordsDescription => '添加 Omi 在转录期间应识别的词汇。';

  @override
  String get enterWordsHint => '输入词汇（逗号分隔）';

  @override
  String get dailySummaryHeader => '每日摘要';

  @override
  String get dailySummaryTitle => '每日摘要';

  @override
  String get dailySummaryDescription => '以通知形式接收当天对话的个性化总结。';

  @override
  String get deliveryTime => '发送时间';

  @override
  String get deliveryTimeDescription => '何时接收您的每日摘要';

  @override
  String get subscription => '订阅';

  @override
  String get viewPlansAndUsage => '查看计划和使用情况';

  @override
  String get viewPlansDescription => '管理您的订阅并查看使用统计';

  @override
  String get addOrChangePaymentMethod => '添加或更改您的支付方式';

  @override
  String get displayOptions => '显示选项';

  @override
  String get showMeetingsInMenuBar => '在菜单栏中显示会议';

  @override
  String get displayUpcomingMeetingsDescription => '在菜单栏中显示即将到来的会议';

  @override
  String get showEventsWithoutParticipants => '显示无参与者的事件';

  @override
  String get includePersonalEventsDescription => '包括没有参与者的个人事件';

  @override
  String get upcomingMeetings => '即将到来的会议';

  @override
  String get checkingNext7Days => '检查接下来的 7 天';

  @override
  String get shortcuts => '快捷键';

  @override
  String get shortcutChangeInstruction => '点击快捷键进行更改。按 Escape 取消。';

  @override
  String get configurePersonaDescription => '配置您的 AI 人设';

  @override
  String get configureSTTProvider => '配置 STT 提供商';

  @override
  String get setConversationEndDescription => '设置对话何时自动结束';

  @override
  String get importDataDescription => '从其他来源导入数据';

  @override
  String get exportConversationsDescription => '将对话导出为 JSON';

  @override
  String get exportingConversations => '正在导出对话...';

  @override
  String get clearNodesDescription => '清除所有节点和连接';

  @override
  String get deleteKnowledgeGraphQuestion => '删除知识图谱？';

  @override
  String get deleteKnowledgeGraphWarning => '这将删除所有派生的知识图谱数据。您的原始记忆仍然安全。';

  @override
  String get connectOmiWithAI => '将 Omi 连接到 AI 助手';

  @override
  String get noAPIKeys => '没有 API 密钥。创建一个以开始使用。';

  @override
  String get autoCreateWhenDetected => '检测到名称时自动创建';

  @override
  String get trackPersonalGoals => '在主页上跟踪个人目标';

  @override
  String get dailyReflectionDescription => '晚上 9 点收到提醒，反思您的一天并记录想法。';

  @override
  String get endpointURL => '端点 URL';

  @override
  String get links => '链接';

  @override
  String get discordMemberCount => 'Discord 上超过 8000 名成员';

  @override
  String get userInformation => '用户信息';

  @override
  String get capabilities => '功能';

  @override
  String get previewScreenshots => '预览截图';

  @override
  String get holdOnPreparingForm => '请稍候，我们正在为您准备表单';

  @override
  String get bySubmittingYouAgreeToOmi => '提交即表示您同意Omi ';

  @override
  String get termsAndPrivacyPolicy => '条款与隐私政策';

  @override
  String get helpsDiagnoseIssuesAutoDeletes => '帮助诊断问题。3天后自动删除。';

  @override
  String get manageYourApp => '管理您的应用';

  @override
  String get updatingYourApp => '正在更新您的应用';

  @override
  String get fetchingYourAppDetails => '正在获取应用详情';

  @override
  String get updateAppQuestion => '更新应用？';

  @override
  String get updateAppConfirmation => '确定要更新您的应用吗？更改将在我们团队审核后生效。';

  @override
  String get updateApp => '更新应用';

  @override
  String get createAndSubmitNewApp => '创建并提交新应用';

  @override
  String appsCount(String count) {
    return '应用 ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return '私有应用 ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return '公开应用 ($count)';
  }

  @override
  String get newVersionAvailable => '新版本可用  🎉';

  @override
  String get no => '否';

  @override
  String get subscriptionCancelledSuccessfully => '订阅已成功取消。它将保持有效直到当前计费周期结束。';

  @override
  String get failedToCancelSubscription => '取消订阅失败。请重试。';

  @override
  String get invalidPaymentUrl => '无效的支付链接';

  @override
  String get permissionsAndTriggers => '权限和触发器';

  @override
  String get chatFeatures => '聊天功能';

  @override
  String get uninstall => '卸载';

  @override
  String get installs => '安装量';

  @override
  String get priceLabel => '价格';

  @override
  String get updatedLabel => '更新于';

  @override
  String get createdLabel => '创建于';

  @override
  String get featuredLabel => '精选';

  @override
  String get cancelSubscriptionQuestion => '取消订阅？';

  @override
  String get cancelSubscriptionConfirmation => '确定要取消订阅吗？您将继续享有访问权限直到当前计费周期结束。';

  @override
  String get cancelSubscriptionButton => '取消订阅';

  @override
  String get cancelling => '正在取消...';

  @override
  String get betaTesterMessage => '您是此应用的测试用户。目前尚未公开。批准后将公开。';

  @override
  String get appUnderReviewMessage => '您的应用正在审核中，仅对您可见。批准后将公开。';

  @override
  String get appRejectedMessage => '您的应用已被拒绝。请更新应用详情并重新提交审核。';

  @override
  String get invalidIntegrationUrl => '无效的集成链接';

  @override
  String get tapToComplete => '点击完成';

  @override
  String get invalidSetupInstructionsUrl => '无效的设置说明链接';

  @override
  String get pushToTalk => '按键说话';

  @override
  String get summaryPrompt => '摘要提示';

  @override
  String get pleaseSelectARating => '请选择评分';

  @override
  String get reviewAddedSuccessfully => '评论添加成功 🚀';

  @override
  String get reviewUpdatedSuccessfully => '评论更新成功 🚀';

  @override
  String get failedToSubmitReview => '提交评论失败。请重试。';

  @override
  String get addYourReview => '添加您的评论';

  @override
  String get editYourReview => '编辑您的评论';

  @override
  String get writeAReviewOptional => '写评论（可选）';

  @override
  String get submitReview => '提交评论';

  @override
  String get updateReview => '更新评论';

  @override
  String get yourReview => '您的评论';

  @override
  String get anonymousUser => '匿名用户';

  @override
  String get issueActivatingApp => '激活此应用时出现问题。请重试。';

  @override
  String get dataAccessNoticeDescription => '此应用将访问您的数据。Omi AI不对此应用如何使用、修改或删除您的数据负责';

  @override
  String get copyUrl => '复制链接';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => '周一';

  @override
  String get weekdayTue => '周二';

  @override
  String get weekdayWed => '周三';

  @override
  String get weekdayThu => '周四';

  @override
  String get weekdayFri => '周五';

  @override
  String get weekdaySat => '周六';

  @override
  String get weekdaySun => '周日';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return '$serviceName集成即将推出';
  }

  @override
  String alreadyExportedTo(String platform) {
    return '已导出到$platform';
  }

  @override
  String get anotherPlatform => '其他平台';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return '请在设置 > 任务集成中验证$serviceName';
  }

  @override
  String addingToService(String serviceName) {
    return '正在添加到$serviceName...';
  }

  @override
  String addedToService(String serviceName) {
    return '已添加到$serviceName';
  }

  @override
  String failedToAddToService(String serviceName) {
    return '添加到$serviceName失败';
  }

  @override
  String get permissionDeniedForAppleReminders => 'Apple提醒事项权限被拒绝';

  @override
  String failedToCreateApiKey(String error) {
    return '创建提供商API密钥失败: $error';
  }

  @override
  String get createAKey => '创建密钥';

  @override
  String get apiKeyRevokedSuccessfully => 'API密钥已成功撤销';

  @override
  String failedToRevokeApiKey(String error) {
    return '撤销API密钥失败: $error';
  }

  @override
  String get omiApiKeys => 'Omi API密钥';

  @override
  String get apiKeysDescription => 'API密钥用于在您的应用程序与OMI服务器通信时进行身份验证。它们允许您的应用程序创建记忆并安全地访问其他OMI服务。';

  @override
  String get aboutOmiApiKeys => '关于Omi API密钥';

  @override
  String get yourNewKey => '您的新密钥:';

  @override
  String get copyToClipboard => '复制到剪贴板';

  @override
  String get pleaseCopyKeyNow => '请立即复制并保存在安全的地方。';

  @override
  String get willNotSeeAgain => '您将无法再次查看。';

  @override
  String get revokeKey => '撤销密钥';

  @override
  String get revokeApiKeyQuestion => '撤销API密钥?';

  @override
  String get revokeApiKeyWarning => '此操作无法撤消。使用此密钥的任何应用程序将无法再访问API。';

  @override
  String get revoke => '撤销';

  @override
  String get whatWouldYouLikeToCreate => '您想创建什么？';

  @override
  String get createAnApp => '创建应用';

  @override
  String get createAndShareYourApp => '创建并分享您的应用';

  @override
  String get createMyClone => '创建我的克隆';

  @override
  String get createYourDigitalClone => '创建您的数字克隆';

  @override
  String get itemApp => '应用';

  @override
  String get itemPersona => '角色';

  @override
  String keepItemPublic(String item) {
    return '保持$item公开';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return '公开$item？';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return '设为私密$item？';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return '如果您将$item设为公开，所有人都可以使用';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return '如果您现在将$item设为私密，它将停止为所有人工作，只有您可以看到';
  }

  @override
  String get manageApp => '管理应用';

  @override
  String get updatePersonaDetails => '更新角色详情';

  @override
  String deleteItemTitle(String item) {
    return '删除$item';
  }

  @override
  String deleteItemQuestion(String item) {
    return '删除$item？';
  }

  @override
  String deleteItemConfirmation(String item) {
    return '您确定要删除此$item吗？此操作无法撤消。';
  }

  @override
  String get revokeKeyQuestion => '撤销密钥？';

  @override
  String revokeKeyConfirmation(String keyName) {
    return '您确定要撤销密钥\"$keyName\"吗？此操作无法撤消。';
  }

  @override
  String get createNewKey => '创建新密钥';

  @override
  String get keyNameHint => '例如：Claude Desktop';

  @override
  String get pleaseEnterAName => '请输入名称。';

  @override
  String failedToCreateKeyWithError(String error) {
    return '创建密钥失败：$error';
  }

  @override
  String get failedToCreateKeyTryAgain => '创建密钥失败。请重试。';

  @override
  String get keyCreated => '密钥已创建';

  @override
  String get keyCreatedMessage => '您的新密钥已创建。请立即复制。您将无法再次查看。';

  @override
  String get keyWord => '密钥';

  @override
  String get externalAppAccess => '外部应用访问';

  @override
  String get externalAppAccessDescription => '以下已安装的应用具有外部集成，可以访问您的数据，例如对话和记忆。';

  @override
  String get noExternalAppsHaveAccess => '没有外部应用可以访问您的数据。';

  @override
  String get maximumSecurityE2ee => '最高安全级别（E2EE）';

  @override
  String get e2eeDescription => '端到端加密是隐私保护的黄金标准。启用后，您的数据在发送到我们的服务器之前会在您的设备上加密。这意味着没有人，包括Omi，可以访问您的内容。';

  @override
  String get importantTradeoffs => '重要权衡：';

  @override
  String get e2eeTradeoff1 => '• 某些功能（如外部应用集成）可能会被禁用。';

  @override
  String get e2eeTradeoff2 => '• 如果您丢失密码，您的数据将无法恢复。';

  @override
  String get featureComingSoon => '此功能即将推出！';

  @override
  String get migrationInProgressMessage => '迁移进行中。在完成之前，您无法更改保护级别。';

  @override
  String get migrationFailed => '迁移失败';

  @override
  String migratingFromTo(String source, String target) {
    return '正在从 $source 迁移到 $target';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total 个对象';
  }

  @override
  String get secureEncryption => '安全加密';

  @override
  String get secureEncryptionDescription =>
      '您的数据使用您独有的密钥在我们托管于Google Cloud的服务器上加密。这意味着包括Omi员工或Google在内的任何人都无法直接从数据库访问您的原始内容。';

  @override
  String get endToEndEncryption => '端到端加密';

  @override
  String get e2eeCardDescription => '启用以获得最大安全性，只有您可以访问您的数据。点击了解更多。';

  @override
  String get dataAlwaysEncrypted => '无论级别如何，您的数据始终在静态和传输中加密。';

  @override
  String get readOnlyScope => '只读';

  @override
  String get fullAccessScope => '完全访问';

  @override
  String get readScope => '读取';

  @override
  String get writeScope => '写入';

  @override
  String get apiKeyCreated => 'API密钥已创建！';

  @override
  String get saveKeyWarning => '立即保存此密钥！您将无法再次查看。';

  @override
  String get yourApiKey => '您的API密钥';

  @override
  String get tapToCopy => '点击复制';

  @override
  String get copyKey => '复制密钥';

  @override
  String get createApiKey => '创建API密钥';

  @override
  String get accessDataProgrammatically => '以编程方式访问您的数据';

  @override
  String get keyNameLabel => '密钥名称';

  @override
  String get keyNamePlaceholder => '例如：我的应用集成';

  @override
  String get permissionsLabel => '权限';

  @override
  String get permissionsInfoNote => 'R = 读取，W = 写入。未选择时默认为只读。';

  @override
  String get developerApi => '开发者API';

  @override
  String get createAKeyToGetStarted => '创建密钥以开始';

  @override
  String errorWithMessage(String error) {
    return '错误：$error';
  }

  @override
  String get omiTraining => 'Omi 培训';

  @override
  String get trainingDataProgram => '训练数据计划';

  @override
  String get getOmiUnlimitedFree => '通过贡献数据来训练AI模型，免费获得Omi无限版。';

  @override
  String get trainingDataBullets => '• 您的数据有助于改进AI模型\n• 仅共享非敏感数据\n• 完全透明的流程';

  @override
  String get learnMoreAtOmiTraining => '在omi.me/training了解更多';

  @override
  String get agreeToContributeData => '我理解并同意为AI训练贡献我的数据';

  @override
  String get submitRequest => '提交请求';

  @override
  String get thankYouRequestUnderReview => '谢谢！您的请求正在审核中。批准后我们将通知您。';

  @override
  String planRemainsActiveUntil(String date) {
    return '您的计划将在$date之前保持有效。之后，您将失去无限功能的访问权限。您确定吗？';
  }

  @override
  String get confirmCancellation => '确认取消';

  @override
  String get keepMyPlan => '保留我的计划';

  @override
  String get subscriptionSetToCancel => '您的订阅将在期限结束时取消。';

  @override
  String get switchedToOnDevice => '已切换到设备端转录';

  @override
  String get couldNotSwitchToFreePlan => '无法切换到免费计划。请重试。';

  @override
  String get couldNotLoadPlans => '无法加载可用计划。请重试。';

  @override
  String get selectedPlanNotAvailable => '所选计划不可用。请重试。';

  @override
  String get upgradeToAnnualPlan => '升级到年度计划';

  @override
  String get importantBillingInfo => '重要计费信息：';

  @override
  String get monthlyPlanContinues => '您当前的月度计划将持续到计费周期结束';

  @override
  String get paymentMethodCharged => '您的现有付款方式将在月度计划结束时自动扣费';

  @override
  String get annualSubscriptionStarts => '您的12个月年度订阅将在扣费后自动开始';

  @override
  String get thirteenMonthsCoverage => '您将获得总共13个月的保障（当前月份 + 12个月年度）';

  @override
  String get confirmUpgrade => '确认升级';

  @override
  String get confirmPlanChange => '确认计划变更';

  @override
  String get confirmAndProceed => '确认并继续';

  @override
  String get upgradeScheduled => '升级已安排';

  @override
  String get changePlan => '更改计划';

  @override
  String get upgradeAlreadyScheduled => '您升级到年度计划的安排已确定';

  @override
  String get youAreOnUnlimitedPlan => '您正在使用无限版计划。';

  @override
  String get yourOmiUnleashed => '您的Omi，解放了。选择无限版，开启无限可能。';

  @override
  String planEndedOn(String date) {
    return '您的计划于$date结束。\\n立即重新订阅 - 您将立即被收取新计费周期的费用。';
  }

  @override
  String planSetToCancelOn(String date) {
    return '您的计划将于$date取消。\\n立即重新订阅以保留您的权益 - $date之前不收费。';
  }

  @override
  String get annualPlanStartsAutomatically => '您的年度计划将在月度计划结束时自动开始。';

  @override
  String planRenewsOn(String date) {
    return '您的计划将于$date续订。';
  }

  @override
  String get unlimitedConversations => '无限对话';

  @override
  String get askOmiAnything => '向Omi询问关于您生活的任何事情';

  @override
  String get unlockOmiInfiniteMemory => '解锁Omi的无限记忆';

  @override
  String get youreOnAnnualPlan => '您正在使用年度计划';

  @override
  String get alreadyBestValuePlan => '您已经拥有最超值的计划。无需更改。';

  @override
  String get unableToLoadPlans => '无法加载计划';

  @override
  String get checkConnectionTryAgain => '请检查您的连接并重试';

  @override
  String get useFreePlan => '使用免费计划';

  @override
  String get continueText => '继续';

  @override
  String get resubscribe => '重新订阅';

  @override
  String get couldNotOpenPaymentSettings => '无法打开支付设置。请重试。';

  @override
  String get managePaymentMethod => '管理支付方式';

  @override
  String get cancelSubscription => '取消订阅';

  @override
  String endsOnDate(String date) {
    return '于$date结束';
  }

  @override
  String get active => '活跃';

  @override
  String get freePlan => '免费计划';

  @override
  String get configure => '配置';

  @override
  String get privacyInformation => '隐私信息';

  @override
  String get yourPrivacyMattersToUs => '您的隐私对我们很重要';

  @override
  String get privacyIntroText => '在Omi，我们非常重视您的隐私。我们希望透明地说明我们收集的数据以及如何使用它们来改进产品。以下是您需要了解的内容：';

  @override
  String get whatWeTrack => '我们追踪什么';

  @override
  String get anonymityAndPrivacy => '匿名性和隐私';

  @override
  String get optInAndOptOutOptions => '加入和退出选项';

  @override
  String get ourCommitment => '我们的承诺';

  @override
  String get commitmentText => '我们承诺仅使用收集的数据来为您改进Omi产品。您的隐私和信任对我们至关重要。';

  @override
  String get thankYouText => '感谢您成为Omi的尊贵用户。如果您有任何问题或疑虑，请随时通过team@basedhardware.com与我们联系。';

  @override
  String get wifiSyncSettings => 'WiFi同步设置';

  @override
  String get enterHotspotCredentials => '输入您手机的热点凭据';

  @override
  String get wifiSyncUsesHotspot => 'WiFi同步使用您的手机作为热点。在设置 > 个人热点中找到热点名称和密码。';

  @override
  String get hotspotNameSsid => '热点名称 (SSID)';

  @override
  String get exampleIphoneHotspot => '例如 iPhone热点';

  @override
  String get password => '密码';

  @override
  String get enterHotspotPassword => '输入热点密码';

  @override
  String get saveCredentials => '保存凭据';

  @override
  String get clearCredentials => '清除凭据';

  @override
  String get pleaseEnterHotspotName => '请输入热点名称';

  @override
  String get wifiCredentialsSaved => 'WiFi凭据已保存';

  @override
  String get wifiCredentialsCleared => 'WiFi凭据已清除';

  @override
  String summaryGeneratedForDate(String date) {
    return '已为 $date 生成摘要';
  }

  @override
  String get failedToGenerateSummaryCheckConversations => '无法生成摘要。请确保您当天有对话记录。';

  @override
  String get summaryNotFound => '未找到摘要';

  @override
  String get yourDaysJourney => '您的一天旅程';

  @override
  String get highlights => '亮点';

  @override
  String get unresolvedQuestions => '未解决的问题';

  @override
  String get decisions => '决定';

  @override
  String get learnings => '收获';

  @override
  String get autoDeletesAfterThreeDays => '3天后自动删除。';

  @override
  String get knowledgeGraphDeletedSuccessfully => '知识图谱已成功删除';

  @override
  String get exportStartedMayTakeFewSeconds => '导出已开始。这可能需要几秒钟...';

  @override
  String get knowledgeGraphDeleteDescription => '这将删除所有派生的知识图谱数据（节点和连接）。您的原始记忆将保持安全。图谱将随时间推移或在下次请求时重建。';

  @override
  String get configureDailySummaryDigest => '配置您的每日任务摘要';

  @override
  String accessesDataTypes(String dataTypes) {
    return '访问 $dataTypes';
  }

  @override
  String triggeredByType(String triggerType) {
    return '由 $triggerType 触发';
  }

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription，$triggerDescription。';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return '$triggerDescription。';
  }

  @override
  String get noSpecificDataAccessConfigured => '未配置特定数据访问。';

  @override
  String get basicPlanDescription => '1,200 高级分钟 + 设备端无限';

  @override
  String get minutes => '分钟';

  @override
  String get omiHas => 'Omi 拥有：';

  @override
  String get premiumMinutesUsed => '高级分钟已用完。';

  @override
  String get setupOnDevice => '设置设备端';

  @override
  String get forUnlimitedFreeTranscription => '享受无限免费转录。';

  @override
  String premiumMinsLeft(int count) {
    return '剩余 $count 高级分钟。';
  }

  @override
  String get alwaysAvailable => '始终可用。';

  @override
  String get importHistory => '导入历史';

  @override
  String get noImportsYet => '暂无导入记录';

  @override
  String get selectZipFileToImport => '选择要导入的.zip文件！';

  @override
  String get otherDevicesComingSoon => '其他设备即将推出';

  @override
  String get deleteAllLimitlessConversations => '删除所有Limitless对话？';

  @override
  String get deleteAllLimitlessWarning => '这将永久删除从Limitless导入的所有对话。此操作无法撤消。';

  @override
  String deletedLimitlessConversations(int count) {
    return '已删除 $count 个Limitless对话';
  }

  @override
  String get failedToDeleteConversations => '删除对话失败';

  @override
  String get deleteImportedData => '删除导入的数据';

  @override
  String get statusPending => '待处理';

  @override
  String get statusProcessing => '处理中';

  @override
  String get statusCompleted => '已完成';

  @override
  String get statusFailed => '失败';

  @override
  String nConversations(int count) {
    return '$count 个对话';
  }

  @override
  String get pleaseEnterName => '请输入名称';

  @override
  String get nameMustBeBetweenCharacters => '名称必须在2到40个字符之间';

  @override
  String get deleteSampleQuestion => '删除样本？';

  @override
  String deleteSampleConfirmation(String name) {
    return '您确定要删除 $name 的样本吗？';
  }

  @override
  String get confirmDeletion => '确认删除';

  @override
  String deletePersonConfirmation(String name) {
    return '您确定要删除 $name 吗？这也将删除所有相关的语音样本。';
  }

  @override
  String get howItWorksTitle => '它是如何工作的？';

  @override
  String get howPeopleWorks => '创建人员后，您可以转到对话记录并为他们分配相应的片段，这样 Omi 也能识别他们的语音！';

  @override
  String get tapToDelete => '点击删除';

  @override
  String get newTag => '新';

  @override
  String get needHelpChatWithUs => '需要帮助？与我们聊天';

  @override
  String get localStorageEnabled => '本地存储已启用';

  @override
  String get localStorageDisabled => '本地存储已禁用';

  @override
  String failedToUpdateSettings(String error) {
    return '更新设置失败: $error';
  }

  @override
  String get privacyNotice => '隐私声明';

  @override
  String get recordingsMayCaptureOthers => '录音可能会捕获他人的声音。启用前请确保获得所有参与者的同意。';

  @override
  String get enable => '启用';

  @override
  String get storeAudioOnPhone => '将音频存储在手机上';

  @override
  String get on => '开启';

  @override
  String get storeAudioDescription => '将所有音频录音存储在手机本地。禁用时，仅保留上传失败的文件以节省存储空间。';

  @override
  String get enableLocalStorage => '启用本地存储';

  @override
  String get cloudStorageEnabled => '云存储已启用';

  @override
  String get cloudStorageDisabled => '云存储已禁用';

  @override
  String get enableCloudStorage => '启用云存储';

  @override
  String get storeAudioOnCloud => '将音频存储在云端';

  @override
  String get cloudStorageDialogMessage => '您的实时录音将在您说话时存储在私有云存储中。';

  @override
  String get storeAudioCloudDescription => '说话时将实时录音存储在私有云存储中。音频会被实时安全地捕获和保存。';

  @override
  String get downloadingFirmware => '正在下载固件';

  @override
  String get installingFirmware => '正在安装固件';

  @override
  String get firmwareUpdateWarning => '请勿关闭应用或关闭设备。这可能会损坏您的设备。';

  @override
  String get firmwareUpdated => '固件已更新';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return '请重启您的 $deviceName 以完成更新。';
  }

  @override
  String get yourDeviceIsUpToDate => '您的设备已是最新版本';

  @override
  String get currentVersion => '当前版本';

  @override
  String get latestVersion => '最新版本';

  @override
  String get whatsNew => '新功能';

  @override
  String get installUpdate => '安装更新';

  @override
  String get updateNow => '立即更新';

  @override
  String get updateGuide => '更新指南';

  @override
  String get checkingForUpdates => '正在检查更新';

  @override
  String get checkingFirmwareVersion => '正在检查固件版本...';

  @override
  String get firmwareUpdate => '固件更新';

  @override
  String get payments => '付款';

  @override
  String get connectPaymentMethodInfo => '在下方连接付款方式，开始接收您应用的收入。';

  @override
  String get selectedPaymentMethod => '已选付款方式';

  @override
  String get availablePaymentMethods => '可用付款方式';

  @override
  String get activeStatus => '活跃';

  @override
  String get connectedStatus => '已连接';

  @override
  String get notConnectedStatus => '未连接';

  @override
  String get setActive => '设为活跃';

  @override
  String get getPaidThroughStripe => '通过 Stripe 获取您的应用销售收入';

  @override
  String get monthlyPayouts => '月度付款';

  @override
  String get monthlyPayoutsDescription => '当您的收入达到 10 美元时，每月直接收款到您的账户';

  @override
  String get secureAndReliable => '安全可靠';

  @override
  String get stripeSecureDescription => 'Stripe 确保您的应用收入安全及时转账';

  @override
  String get selectYourCountry => '选择您的国家';

  @override
  String get countrySelectionPermanent => '您的国家选择是永久性的，以后无法更改。';

  @override
  String get byClickingConnectNow => '点击「立即连接」即表示您同意';

  @override
  String get stripeConnectedAccountAgreement => 'Stripe 关联账户协议';

  @override
  String get errorConnectingToStripe => '连接 Stripe 时出错！请稍后重试。';

  @override
  String get connectingYourStripeAccount => '正在连接您的 Stripe 账户';

  @override
  String get stripeOnboardingInstructions => '请在浏览器中完成 Stripe 注册流程。完成后此页面将自动更新。';

  @override
  String get failedTryAgain => '失败了？重试';

  @override
  String get illDoItLater => '稍后再做';

  @override
  String get successfullyConnected => '连接成功！';

  @override
  String get stripeReadyForPayments => '您的 Stripe 账户已准备好接收付款。您可以立即开始从应用销售中获利。';

  @override
  String get updateStripeDetails => '更新 Stripe 详细信息';

  @override
  String get errorUpdatingStripeDetails => '更新 Stripe 详细信息时出错！请稍后重试。';

  @override
  String get updatePayPal => '更新 PayPal';

  @override
  String get setUpPayPal => '设置 PayPal';

  @override
  String get updatePayPalAccountDetails => '更新您的 PayPal 账户详细信息';

  @override
  String get connectPayPalToReceivePayments => '连接您的 PayPal 账户，开始接收您应用的付款';

  @override
  String get paypalEmail => 'PayPal 邮箱';

  @override
  String get paypalMeLink => 'PayPal.me 链接';

  @override
  String get stripeRecommendation => '如果 Stripe 在您的国家可用，我们强烈建议使用它以获得更快更便捷的付款。';

  @override
  String get updatePayPalDetails => '更新 PayPal 详细信息';

  @override
  String get savePayPalDetails => '保存 PayPal 详细信息';

  @override
  String get pleaseEnterPayPalEmail => '请输入您的 PayPal 邮箱';

  @override
  String get pleaseEnterPayPalMeLink => '请输入您的 PayPal.me 链接';

  @override
  String get doNotIncludeHttpInLink => '链接中请勿包含 http、https 或 www';

  @override
  String get pleaseEnterValidPayPalMeLink => '请输入有效的 PayPal.me 链接';

  @override
  String get pleaseEnterValidEmail => '请输入有效的电子邮件地址';

  @override
  String get syncingYourRecordings => '正在同步您的录音';

  @override
  String get syncYourRecordings => '同步您的录音';

  @override
  String get syncNow => '立即同步';

  @override
  String get error => '错误';

  @override
  String get speechSamples => '语音样本';

  @override
  String additionalSampleIndex(String index) {
    return '附加样本 $index';
  }

  @override
  String durationSeconds(String seconds) {
    return '时长: $seconds 秒';
  }

  @override
  String get additionalSpeechSampleRemoved => '已删除附加语音样本';

  @override
  String get consentDataMessage => '继续即表示您与此应用共享的所有数据（包括您的对话、录音和个人信息）将安全存储在我们的服务器上，以便为您提供AI驱动的洞察并启用所有应用功能。';

  @override
  String get tasksEmptyStateMessage => '来自您对话的任务将显示在这里。\n点击 + 手动创建。';

  @override
  String get clearChatAction => '清除聊天';

  @override
  String get enableApps => '启用应用';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => '显示更多 ↓';

  @override
  String get showLess => '收起 ↑';

  @override
  String get loadingYourRecording => '正在加载您的录音...';

  @override
  String get photoDiscardedMessage => '此照片因不重要而被丢弃。';

  @override
  String get analyzing => '分析中...';

  @override
  String get searchCountries => '搜索国家...';

  @override
  String get checkingAppleWatch => '正在检查 Apple Watch...';

  @override
  String get installOmiOnAppleWatch => '在您的 Apple Watch 上\n安装 Omi';

  @override
  String get installOmiOnAppleWatchDescription => '要将 Apple Watch 与 Omi 配合使用，您需要先在手表上安装 Omi 应用。';

  @override
  String get openOmiOnAppleWatch => '在您的 Apple Watch 上\n打开 Omi';

  @override
  String get openOmiOnAppleWatchDescription => 'Omi 应用已安装在您的 Apple Watch 上。打开它并点击开始。';

  @override
  String get openWatchApp => '打开 Watch 应用';

  @override
  String get iveInstalledAndOpenedTheApp => '我已安装并打开应用';

  @override
  String get unableToOpenWatchApp => '无法打开 Apple Watch 应用。请在 Apple Watch 上手动打开 Watch 应用，并从「可用应用」部分安装 Omi。';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch 连接成功！';

  @override
  String get appleWatchNotReachable => '仍无法连接 Apple Watch。请确保 Omi 应用在手表上处于打开状态。';

  @override
  String errorCheckingConnection(String error) {
    return '检查连接时出错：$error';
  }

  @override
  String get muted => '已静音';

  @override
  String get processNow => '立即处理';

  @override
  String get finishedConversation => '结束对话？';

  @override
  String get stopRecordingConfirmation => '您确定要停止录音并立即总结对话吗？';

  @override
  String get conversationEndsManually => '对话只能手动结束。';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return '对话将在$minutes分钟$suffix无声后进行总结。';
  }

  @override
  String get dontAskAgain => '不再询问';

  @override
  String get waitingForTranscriptOrPhotos => '等待转录或照片...';

  @override
  String get noSummaryYet => '暂无摘要';

  @override
  String hints(String text) {
    return '提示: $text';
  }

  @override
  String get testConversationPrompt => '测试对话提示';

  @override
  String get prompt => '提示';

  @override
  String get result => '结果：';

  @override
  String get compareTranscripts => '比较转录';

  @override
  String get notHelpful => '没有帮助';

  @override
  String get exportTasksWithOneTap => '一键导出任务！';

  @override
  String get inProgress => '处理中';

  @override
  String get photos => '照片';

  @override
  String get rawData => '原始数据';

  @override
  String get content => '内容';

  @override
  String get noContentToDisplay => '没有可显示的内容';

  @override
  String get noSummary => '无摘要';

  @override
  String get updateOmiFirmware => '更新omi固件';

  @override
  String get anErrorOccurredTryAgain => '发生错误，请重试。';

  @override
  String get welcomeBackSimple => '欢迎回来';

  @override
  String get addVocabularyDescription => '添加Omi在转录时应识别的词语。';

  @override
  String get enterWordsCommaSeparated => '输入词语（逗号分隔）';

  @override
  String get whenToReceiveDailySummary => '何时收到每日摘要';

  @override
  String get checkingNextSevenDays => '检查接下来7天';

  @override
  String failedToDeleteError(String error) {
    return '删除失败：$error';
  }

  @override
  String get developerApiKeys => '开发者 API 密钥';

  @override
  String get noApiKeysCreateOne => '没有 API 密钥。创建一个以开始。';

  @override
  String get commandRequired => '需要 ⌘';

  @override
  String get spaceKey => '空格';

  @override
  String loadMoreRemaining(String count) {
    return '加载更多（剩余$count个）';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return '前$percentile%用户';
  }

  @override
  String get wrappedMinutes => '分钟';

  @override
  String get wrappedConversations => '对话';

  @override
  String get wrappedDaysActive => '活跃天数';

  @override
  String get wrappedYouTalkedAbout => '你聊过的话题';

  @override
  String get wrappedActionItems => '任务';

  @override
  String get wrappedTasksCreated => '创建的任务';

  @override
  String get wrappedCompleted => '已完成';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate%完成率';
  }

  @override
  String get wrappedYourTopDays => '你的最佳日子';

  @override
  String get wrappedBestMoments => '最佳时刻';

  @override
  String get wrappedMyBuddies => '我的伙伴';

  @override
  String get wrappedCouldntStopTalkingAbout => '停不下来聊的话题';

  @override
  String get wrappedShow => '节目';

  @override
  String get wrappedMovie => '电影';

  @override
  String get wrappedBook => '书籍';

  @override
  String get wrappedCelebrity => '名人';

  @override
  String get wrappedFood => '美食';

  @override
  String get wrappedMovieRecs => '推荐给朋友的电影';

  @override
  String get wrappedBiggest => '最大的';

  @override
  String get wrappedStruggle => '挑战';

  @override
  String get wrappedButYouPushedThrough => '但你挺过来了 💪';

  @override
  String get wrappedWin => '胜利';

  @override
  String get wrappedYouDidIt => '你做到了！🎉';

  @override
  String get wrappedTopPhrases => '最常说的5句话';

  @override
  String get wrappedMins => '分钟';

  @override
  String get wrappedConvos => '对话';

  @override
  String get wrappedDays => '天';

  @override
  String get wrappedMyBuddiesLabel => '我的伙伴';

  @override
  String get wrappedObsessionsLabel => '痴迷';

  @override
  String get wrappedStruggleLabel => '挑战';

  @override
  String get wrappedWinLabel => '胜利';

  @override
  String get wrappedTopPhrasesLabel => '常说的话';

  @override
  String get wrappedLetsHitRewind => '让我们回顾你的';

  @override
  String get wrappedGenerateMyWrapped => '生成我的年度回顾';

  @override
  String get wrappedProcessingDefault => '处理中...';

  @override
  String get wrappedCreatingYourStory => '正在创建你的\n2025年故事...';

  @override
  String get wrappedSomethingWentWrong => '出了点\n问题';

  @override
  String get wrappedAnErrorOccurred => '发生错误';

  @override
  String get wrappedTryAgain => '重试';

  @override
  String get wrappedNoDataAvailable => '暂无数据';

  @override
  String get wrappedOmiLifeRecap => 'Omi 生活回顾';

  @override
  String get wrappedSwipeUpToBegin => '向上滑动开始';

  @override
  String get wrappedShareText => '我的2025，由Omi记录 ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare => '分享失败，请重试。';

  @override
  String get wrappedFailedToStartGeneration => '无法开始生成，请重试。';

  @override
  String get wrappedStarting => '启动中...';

  @override
  String get wrappedShare => '分享';

  @override
  String get wrappedShareYourWrapped => '分享你的年度回顾';

  @override
  String get wrappedMy2025 => '我的2025';

  @override
  String get wrappedRememberedByOmi => '由Omi记录';

  @override
  String get wrappedMostFunDay => '最开心';

  @override
  String get wrappedMostProductiveDay => '最高效';

  @override
  String get wrappedMostIntenseDay => '最紧张';

  @override
  String get wrappedFunniestMoment => '最搞笑';

  @override
  String get wrappedMostCringeMoment => '最尴尬';

  @override
  String get wrappedMinutesLabel => '分钟';

  @override
  String get wrappedConversationsLabel => '对话';

  @override
  String get wrappedDaysActiveLabel => '活跃天数';

  @override
  String get wrappedTasksGenerated => '任务已创建';

  @override
  String get wrappedTasksCompleted => '任务已完成';

  @override
  String get wrappedTopFivePhrases => '前 5 常用短语';

  @override
  String get wrappedAGreatDay => '美好的一天';

  @override
  String get wrappedGettingItDone => '完成任务';

  @override
  String get wrappedAChallenge => '一个挑战';

  @override
  String get wrappedAHilariousMoment => '搞笑时刻';

  @override
  String get wrappedThatAwkwardMoment => '尴尬时刻';

  @override
  String get wrappedYouHadFunnyMoments => '今年你有很多有趣的时刻！';

  @override
  String get wrappedWeveAllBeenThere => '我们都经历过！';

  @override
  String get wrappedFriend => '朋友';

  @override
  String get wrappedYourBuddy => '你的伙伴！';

  @override
  String get wrappedNotMentioned => '未提及';

  @override
  String get wrappedTheHardPart => '困难部分';

  @override
  String get wrappedPersonalGrowth => '个人成长';

  @override
  String get wrappedFunDay => '开心';

  @override
  String get wrappedProductiveDay => '高效';

  @override
  String get wrappedIntenseDay => '紧张';

  @override
  String get wrappedFunnyMomentTitle => '搞笑时刻';

  @override
  String get wrappedCringeMomentTitle => '尴尬时刻';

  @override
  String get wrappedYouTalkedAboutBadge => '你谈论了';

  @override
  String get wrappedCompletedLabel => '已完成';

  @override
  String get wrappedMyBuddiesCard => '我的朋友们';

  @override
  String get wrappedBuddiesLabel => '朋友';

  @override
  String get wrappedObsessionsLabelUpper => '痴迷';

  @override
  String get wrappedStruggleLabelUpper => '挑战';

  @override
  String get wrappedWinLabelUpper => '胜利';

  @override
  String get wrappedTopPhrasesLabelUpper => '热门短语';

  @override
  String get wrappedYourHeader => '你的';

  @override
  String get wrappedTopDaysHeader => '最佳日子';

  @override
  String get wrappedYourTopDaysBadge => '你的最佳日子';

  @override
  String get wrappedBestHeader => '最佳';

  @override
  String get wrappedMomentsHeader => '时刻';

  @override
  String get wrappedBestMomentsBadge => '最佳时刻';

  @override
  String get wrappedBiggestHeader => '最大的';

  @override
  String get wrappedStruggleHeader => '挑战';

  @override
  String get wrappedWinHeader => '胜利';

  @override
  String get wrappedButYouPushedThroughEmoji => '但你坚持下来了 💪';

  @override
  String get wrappedYouDidItEmoji => '你做到了！ 🎉';

  @override
  String get wrappedHours => '小时';

  @override
  String get wrappedActions => '操作';

  @override
  String get multipleSpeakersDetected => '检测到多个说话者';

  @override
  String get multipleSpeakersDescription => '录音中似乎有多个说话者。请确保您在安静的地方，然后重试。';

  @override
  String get invalidRecordingDetected => '检测到无效录音';

  @override
  String get notEnoughSpeechDescription => '检测到的语音不足。请多说一些，然后重试。';

  @override
  String get speechDurationDescription => '请确保您说话至少5秒钟，但不超过90秒。';

  @override
  String get connectionLostDescription => '连接中断。请检查您的互联网连接并重试。';

  @override
  String get howToTakeGoodSample => '如何获取好的样本？';

  @override
  String get goodSampleInstructions => '1. 确保您在安静的地方。\n2. 说话要清晰自然。\n3. 确保您的设备在颈部的自然位置。\n\n创建后，您随时可以改进它或重新创建。';

  @override
  String get noDeviceConnectedUseMic => '没有连接设备。将使用手机麦克风。';

  @override
  String get doItAgain => '重新开始';

  @override
  String get listenToSpeechProfile => '听我的语音档案 ➡️';

  @override
  String get recognizingOthers => '识别他人 👀';

  @override
  String get keepGoingGreat => '继续，你做得很棒';

  @override
  String get somethingWentWrongTryAgain => '出错了！请稍后重试。';

  @override
  String get uploadingVoiceProfile => '正在上传您的语音配置文件....';

  @override
  String get memorizingYourVoice => '正在记忆您的声音...';

  @override
  String get personalizingExperience => '正在个性化您的体验...';

  @override
  String get keepSpeakingUntil100 => '继续说话直到达到100%。';

  @override
  String get greatJobAlmostThere => '做得好，就快完成了';

  @override
  String get soCloseJustLittleMore => '很接近了，再说一点';

  @override
  String get notificationFrequency => '通知频率';

  @override
  String get controlNotificationFrequency => '控制Omi向您发送主动通知的频率。';

  @override
  String get yourScore => '您的评分';

  @override
  String get dailyScoreBreakdown => '每日评分详情';

  @override
  String get todaysScore => '今日评分';

  @override
  String get tasksCompleted => '已完成任务';

  @override
  String get completionRate => '完成率';

  @override
  String get howItWorks => '运作方式';

  @override
  String get dailyScoreExplanation => '您的每日评分基于任务完成情况。完成任务以提高评分！';

  @override
  String get notificationFrequencyDescription => '控制 Omi 向您发送主动通知和提醒的频率。';

  @override
  String get sliderOff => '关闭';

  @override
  String get sliderMax => '最大';

  @override
  String summaryGeneratedFor(String date) {
    return '已为 $date 生成总结';
  }

  @override
  String get failedToGenerateSummary => '生成总结失败。请确保当天有对话记录。';

  @override
  String get recap => '回顾';

  @override
  String deleteQuoted(String name) {
    return '删除\"$name\"';
  }

  @override
  String moveConversationsTo(int count) {
    return '移动 $count 个对话到：';
  }

  @override
  String get noFolder => '无文件夹';

  @override
  String get removeFromAllFolders => '从所有文件夹中移除';

  @override
  String get buildAndShareYourCustomApp => '构建并分享您的自定义应用';

  @override
  String get searchAppsPlaceholder => '搜索 1500+ 应用';

  @override
  String get filters => '筛选';

  @override
  String get frequencyOff => '关闭';

  @override
  String get frequencyMinimal => '最少';

  @override
  String get frequencyLow => '低';

  @override
  String get frequencyBalanced => '平衡';

  @override
  String get frequencyHigh => '高';

  @override
  String get frequencyMaximum => '最大';

  @override
  String get frequencyDescOff => '无主动通知';

  @override
  String get frequencyDescMinimal => '仅关键提醒';

  @override
  String get frequencyDescLow => '仅重要更新';

  @override
  String get frequencyDescBalanced => '定期有用提醒';

  @override
  String get frequencyDescHigh => '频繁检查';

  @override
  String get frequencyDescMaximum => '保持持续参与';

  @override
  String get clearChatQuestion => '清除聊天？';

  @override
  String get syncingMessages => '正在与服务器同步消息...';

  @override
  String get chatAppsTitle => '聊天应用';

  @override
  String get selectApp => '选择应用';

  @override
  String get noChatAppsEnabled => '没有启用的聊天应用。\n点击\"启用应用\"添加。';

  @override
  String get disable => '禁用';

  @override
  String get photoLibrary => '照片库';

  @override
  String get chooseFile => '选择文件';

  @override
  String get configureAiPersona => '配置您的 AI 角色';

  @override
  String get connectAiAssistantsToYourData => '将 AI 助手连接到您的数据';

  @override
  String get oAuth => 'OAuth';

  @override
  String get trackYourGoalsOnHomepage => '在主页上跟踪您的个人目标';

  @override
  String get deleteRecording => '删除录音';

  @override
  String get thisCannotBeUndone => '此操作无法撤销。';

  @override
  String get sdCard => 'SD 卡';

  @override
  String get fromSd => '来自 SD 卡';

  @override
  String get limitless => '无限';

  @override
  String get fastTransfer => '快速传输';

  @override
  String get syncingStatus => '同步中';

  @override
  String get failedStatus => '失败';

  @override
  String etaLabel(String time) {
    return '预计时间：$time';
  }

  @override
  String get transferMethod => '传输方式';

  @override
  String get fast => '快速';

  @override
  String get ble => '蓝牙低功耗';

  @override
  String get phone => '手机';

  @override
  String get cancelSync => '取消同步';

  @override
  String get cancelSyncMessage => '已下载的数据将被保存。您可以稍后继续。';

  @override
  String get syncCancelled => '同步已取消';

  @override
  String get deleteProcessedFiles => '删除已处理的文件';

  @override
  String get processedFilesDeleted => '已处理的文件已删除';

  @override
  String get wifiEnableFailed => '无法在设备上启用 WiFi。请重试。';

  @override
  String get deviceNoFastTransfer => '您的设备不支持快速传输。请改用蓝牙。';

  @override
  String get enableHotspotMessage => '请启用您手机的热点并重试。';

  @override
  String get transferStartFailed => '无法开始传输。请重试。';

  @override
  String get deviceNotResponding => '设备无响应。请重试。';

  @override
  String get invalidWifiCredentials => 'WiFi 凭据无效。请检查您的热点设置。';

  @override
  String get wifiConnectionFailed => 'WiFi 连接失败。请重试。';

  @override
  String get sdCardProcessing => 'SD 卡处理中';

  @override
  String sdCardProcessingMessage(int count) {
    return '正在处理 $count 个录音。处理后文件将从 SD 卡中删除。';
  }

  @override
  String get process => '处理';

  @override
  String get wifiSyncFailed => 'WiFi 同步失败';

  @override
  String get processingFailed => '处理失败';

  @override
  String get downloadingFromSdCard => '正在从 SD 卡下载';

  @override
  String processingProgress(int current, int total) {
    return '正在处理 $current/$total';
  }

  @override
  String conversationsCreated(int count) {
    return '$count conversations created';
  }

  @override
  String get internetRequired => '需要互联网连接';

  @override
  String get processAudio => '处理音频';

  @override
  String get start => '开始';

  @override
  String get noRecordings => '没有录音';

  @override
  String get audioFromOmiWillAppearHere => '来自 Omi 设备的音频将显示在这里';

  @override
  String get deleteProcessed => '删除已处理的';

  @override
  String get tryDifferentFilter => '尝试其他筛选条件';

  @override
  String get recordings => '录音';

  @override
  String get enableRemindersAccess => '请在设置中启用提醒事项访问权限以使用 Apple 提醒事项';

  @override
  String todayAtTime(String time) {
    return '今天 $time';
  }

  @override
  String yesterdayAtTime(String time) {
    return '昨天 $time';
  }

  @override
  String get lessThanAMinute => '不到一分钟';

  @override
  String estimatedMinutes(int count) {
    return '约 $count 分钟';
  }

  @override
  String estimatedHours(int count) {
    return '约 $count 小时';
  }

  @override
  String estimatedTimeRemaining(String time) {
    return '预计剩余：$time';
  }

  @override
  String get summarizingConversation => '正在总结对话...\n这可能需要几秒钟';

  @override
  String get resummarizingConversation => '正在重新总结对话...\n这可能需要几秒钟';

  @override
  String get nothingInterestingRetry => '没有发现有趣的内容，\n要重试吗？';

  @override
  String get noSummaryForConversation => '此对话\n没有可用的摘要。';

  @override
  String get unknownLocation => '未知位置';

  @override
  String get couldNotLoadMap => '无法加载地图';

  @override
  String get triggerConversationIntegration => '触发对话创建集成';

  @override
  String get webhookUrlNotSet => 'Webhook URL 未设置';

  @override
  String get setWebhookUrlInSettings => '请在开发者设置中设置 webhook URL 以使用此功能。';

  @override
  String get sendWebUrl => '发送网页链接';

  @override
  String get sendTranscript => '发送文字记录';

  @override
  String get sendSummary => '发送摘要';

  @override
  String get debugModeDetected => '检测到调试模式';

  @override
  String get performanceReduced => '性能可能会降低';

  @override
  String autoClosingInSeconds(int seconds) {
    return '$seconds秒后自动关闭';
  }

  @override
  String get modelRequired => '需要模型';

  @override
  String get downloadWhisperModel => '下载whisper模型以使用设备端转录';

  @override
  String get deviceNotCompatible => '您的设备不兼容设备端转录';

  @override
  String get deviceRequirements => '您的设备不满足本地转录的要求。';

  @override
  String get willLikelyCrash => '启用此功能可能会导致应用崩溃或冻结。';

  @override
  String get transcriptionSlowerLessAccurate => '转录将明显变慢且准确度降低。';

  @override
  String get proceedAnyway => '仍然继续';

  @override
  String get olderDeviceDetected => '检测到较旧设备';

  @override
  String get onDeviceSlower => '本地转录在此设备上可能较慢。';

  @override
  String get batteryUsageHigher => '电池使用量将高于云端转录。';

  @override
  String get considerOmiCloud => '考虑使用 Omi Cloud 以获得更好的性能。';

  @override
  String get highResourceUsage => '高资源使用';

  @override
  String get onDeviceIntensive => '本地转录需要大量计算资源。';

  @override
  String get batteryDrainIncrease => '电池消耗将显著增加。';

  @override
  String get deviceMayWarmUp => '长时间使用时设备可能会发热。';

  @override
  String get speedAccuracyLower => '速度和准确度可能低于云端模型。';

  @override
  String get cloudProvider => '云服务提供商';

  @override
  String get premiumMinutesInfo => '每月 1,200 分钟高级时长。本地标签页提供无限免费转录。';

  @override
  String get viewUsage => '查看使用量';

  @override
  String get localProcessingInfo => '音频在本地处理。可离线使用，更注重隐私，但电池消耗更多。';

  @override
  String get model => '模型';

  @override
  String get performanceWarning => '性能警告';

  @override
  String get largeModelWarning => '此模型较大，可能导致应用崩溃或在移动设备上运行非常缓慢。\n\n建议使用 \"small\" 或 \"base\" 模型。';

  @override
  String get usingNativeIosSpeech => '使用原生 iOS 语音识别';

  @override
  String get noModelDownloadRequired => '将使用您设备的原生语音引擎。无需下载模型。';

  @override
  String get modelReady => '模型就绪';

  @override
  String get redownload => '重新下载';

  @override
  String get doNotCloseApp => '请不要关闭应用。';

  @override
  String get downloading => '下载中...';

  @override
  String get downloadModel => '下载模型';

  @override
  String estimatedSize(String size) {
    return '预估大小：约 $size MB';
  }

  @override
  String availableSpace(String space) {
    return '可用空间：$space';
  }

  @override
  String get notEnoughSpace => '警告: 空间不足!';

  @override
  String get download => '下载';

  @override
  String downloadError(String error) {
    return '下载错误：$error';
  }

  @override
  String get cancelled => '已取消';

  @override
  String get deviceNotCompatibleTitle => '设备不兼容';

  @override
  String get deviceNotMeetRequirements => '您的设备不满足设备端转录的要求。';

  @override
  String get transcriptionSlowerOnDevice => '在此设备上，设备端转录可能会更慢。';

  @override
  String get computationallyIntensive => '设备端转录是计算密集型的。';

  @override
  String get batteryDrainSignificantly => '电池消耗将显著增加。';

  @override
  String get premiumMinutesMonth => '每月1,200分钟高级配额。设备端选项卡提供无限免费转录。';

  @override
  String get audioProcessedLocally => '音频在本地处理。可离线使用，更私密，但消耗更多电量。';

  @override
  String get languageLabel => '语言';

  @override
  String get modelLabel => '模型';

  @override
  String get modelTooLargeWarning => '此模型较大，可能导致应用在移动设备上崩溃或运行非常缓慢。\n\n建议使用 small 或 base。';

  @override
  String get nativeEngineNoDownload => '将使用您设备的原生语音引擎。无需下载模型。';

  @override
  String modelReadyWithName(String model) {
    return '模型就绪 ($model)';
  }

  @override
  String get reDownload => '重新下载';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return '正在下载 $model: $received / $total MB';
  }

  @override
  String preparingModel(String model) {
    return '正在准备 $model...';
  }

  @override
  String downloadErrorWithMessage(String error) {
    return '下载错误: $error';
  }

  @override
  String estimatedSizeWithValue(String size) {
    return '预计大小: ~$size MB';
  }

  @override
  String availableSpaceWithValue(String space) {
    return '可用空间: $space';
  }

  @override
  String get omiTranscriptionOptimized => 'Omi 的内置实时转录针对实时对话进行了优化，具有自动说话人检测和说话人分离功能。';

  @override
  String get reset => '重置';

  @override
  String get useTemplateFrom => '使用模板来自';

  @override
  String get selectProviderTemplate => '选择提供商模板...';

  @override
  String get quicklyPopulateResponse => '快速填充已知提供商响应格式';

  @override
  String get quicklyPopulateRequest => '快速填充已知提供商请求格式';

  @override
  String get invalidJsonError => '无效的 JSON';

  @override
  String downloadModelWithName(String model) {
    return '下载模型 ($model)';
  }

  @override
  String modelNameWithFile(String model) {
    return '模型: $model';
  }

  @override
  String get device => '设备';

  @override
  String get chatAssistantsTitle => '聊天助手';

  @override
  String get permissionReadConversations => '读取对话';

  @override
  String get permissionReadMemories => '读取记忆';

  @override
  String get permissionReadTasks => '读取任务';

  @override
  String get permissionCreateConversations => '创建对话';

  @override
  String get permissionCreateMemories => '创建记忆';

  @override
  String get permissionTypeAccess => '访问';

  @override
  String get permissionTypeCreate => '创建';

  @override
  String get permissionTypeTrigger => '触发器';

  @override
  String get permissionDescReadConversations => '此应用可以访问您的对话。';

  @override
  String get permissionDescReadMemories => '此应用可以访问您的记忆。';

  @override
  String get permissionDescReadTasks => '此应用可以访问您的任务。';

  @override
  String get permissionDescCreateConversations => '此应用可以创建新对话。';

  @override
  String get permissionDescCreateMemories => '此应用可以创建新记忆。';

  @override
  String get realtimeListening => '实时监听';

  @override
  String get setupCompleted => '已完成';

  @override
  String get pleaseSelectRating => '请选择评分';

  @override
  String get writeReviewOptional => '撰写评论（可选）';

  @override
  String get setupQuestionsIntro => '告诉我们关于您自己的信息。这将帮助 Omi 更好地支持您。';

  @override
  String get setupQuestionProfession => '1. 你的职业是什么？';

  @override
  String get setupQuestionUsage => '2. 你计划在哪里使用 Omi？';

  @override
  String get setupQuestionAge => '3. 你的年龄段是？';

  @override
  String get setupAnswerAllQuestions => '你还没有回答所有问题！ 🥺';

  @override
  String get setupSkipHelp => '跳过，我不想帮忙 :C';

  @override
  String get professionEntrepreneur => '企业家';

  @override
  String get professionSoftwareEngineer => '软件工程师';

  @override
  String get professionProductManager => '产品经理';

  @override
  String get professionExecutive => '高管/经理';

  @override
  String get professionSales => '销售/市场营销';

  @override
  String get professionStudent => '学生';

  @override
  String get usageAtWork => '工作中';

  @override
  String get usageIrlEvents => '线下活动';

  @override
  String get usageOnline => '在线';

  @override
  String get usageSocialSettings => '社交场合';

  @override
  String get usageEverywhere => '到处';

  @override
  String get customBackendUrlTitle => '自定义后端URL';

  @override
  String get backendUrlLabel => '后端URL';

  @override
  String get saveUrlButton => '保存URL';

  @override
  String get enterBackendUrlError => '请输入后端URL';

  @override
  String get urlMustEndWithSlashError => 'URL必须以\"/\"结尾';

  @override
  String get invalidUrlError => '请输入有效的URL';

  @override
  String get backendUrlSavedSuccess => '后端URL保存成功！';

  @override
  String get signInTitle => '登录';

  @override
  String get signInButton => '登录';

  @override
  String get enterEmailError => '请输入您的电子邮件';

  @override
  String get invalidEmailError => '请输入有效的电子邮件';

  @override
  String get enterPasswordError => '请输入您的密码';

  @override
  String get passwordMinLengthError => '密码必须至少8个字符';

  @override
  String get signInSuccess => '登录成功！';

  @override
  String get alreadyHaveAccountLogin => '已有账户？登录';

  @override
  String get emailLabel => '电子邮件';

  @override
  String get passwordLabel => '密码';

  @override
  String get createAccountTitle => '创建账户';

  @override
  String get nameLabel => '姓名';

  @override
  String get repeatPasswordLabel => '确认密码';

  @override
  String get signUpButton => '注册';

  @override
  String get enterNameError => '请输入您的姓名';

  @override
  String get passwordsDoNotMatch => '密码不匹配';

  @override
  String get signUpSuccess => '注册成功！';

  @override
  String get loadingKnowledgeGraph => '正在加载知识图谱...';

  @override
  String get noKnowledgeGraphYet => '暂无知识图谱';

  @override
  String get buildingKnowledgeGraphFromMemories => '正在从记忆构建知识图谱...';

  @override
  String get knowledgeGraphWillBuildAutomatically => '当您创建新记忆时，知识图谱将自动构建。';

  @override
  String get buildGraphButton => '构建图谱';

  @override
  String get checkOutMyMemoryGraph => '看看我的记忆图谱！';

  @override
  String get getButton => '获取';

  @override
  String openingApp(String appName) {
    return '正在打开 $appName...';
  }

  @override
  String get writeSomething => '写点什么';

  @override
  String get submitReply => '提交回复';

  @override
  String get editYourReply => '编辑回复';

  @override
  String get replyToReview => '回复评价';

  @override
  String get rateAndReviewThisApp => '评分并评价此应用';

  @override
  String get noChangesInReview => '评论没有更改需要更新。';

  @override
  String get cantRateWithoutInternet => '没有网络连接无法评价应用。';

  @override
  String get appAnalytics => '应用分析';

  @override
  String get learnMoreLink => '了解更多';

  @override
  String get moneyEarned => '收入';

  @override
  String get writeYourReply => '写下您的回复...';

  @override
  String get replySentSuccessfully => '回复发送成功';

  @override
  String failedToSendReply(String error) {
    return '发送回复失败：$error';
  }

  @override
  String get send => '发送';

  @override
  String starFilter(int count) {
    return '$count 星';
  }

  @override
  String get noReviewsFound => '未找到评论';

  @override
  String get editReply => '编辑回复';

  @override
  String get reply => '回复';

  @override
  String starFilterLabel(int count) {
    return '$count星';
  }

  @override
  String get sharePublicLink => '分享公开链接';

  @override
  String get makePersonaPublic => '公开角色';

  @override
  String get connectedKnowledgeData => '已连接的知识数据';

  @override
  String get enterName => '输入姓名';

  @override
  String get disconnectTwitter => '断开 Twitter 连接';

  @override
  String get disconnectTwitterConfirmation => '您确定要断开 Twitter 账户连接吗？您的角色将无法再访问您的 Twitter 数据。';

  @override
  String get getOmiDeviceDescription => '通过您的个人对话创建更准确的克隆';

  @override
  String get getOmi => '获取 Omi';

  @override
  String get iHaveOmiDevice => '我有 Omi 设备';

  @override
  String get goal => '目标';

  @override
  String get tapToTrackThisGoal => '点击追踪此目标';

  @override
  String get tapToSetAGoal => '点击设置目标';

  @override
  String get processedConversations => '已处理的对话';

  @override
  String get updatedConversations => '已更新的对话';

  @override
  String get newConversations => '新对话';

  @override
  String get summaryTemplate => '摘要模板';

  @override
  String get suggestedTemplates => '推荐模板';

  @override
  String get otherTemplates => '其他模板';

  @override
  String get availableTemplates => '可用模板';

  @override
  String get getCreative => '发挥创意';

  @override
  String get defaultLabel => '默认';

  @override
  String get lastUsedLabel => '上次使用';

  @override
  String get setDefaultApp => '设置默认应用';

  @override
  String setDefaultAppContent(String appName) {
    return '将 $appName 设为您的默认摘要应用？\\n\\n此应用将自动用于所有未来的对话摘要。';
  }

  @override
  String get setDefaultButton => '设为默认';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName 已设为默认摘要应用';
  }

  @override
  String get createCustomTemplate => '创建自定义模板';

  @override
  String get allTemplates => '所有模板';

  @override
  String failedToInstallApp(String appName) {
    return '安装 $appName 失败。请重试。';
  }

  @override
  String errorInstallingApp(String appName, String error) {
    return '安装 $appName 时出错：$error';
  }

  @override
  String tagSpeaker(int speakerId) {
    return '标记说话者 $speakerId';
  }

  @override
  String get personNameAlreadyExists => '已存在同名的人员。';

  @override
  String get selectYouFromList => '要标记您自己，请从列表中选择\"您\"。';

  @override
  String get enterPersonsName => '输入人员姓名';

  @override
  String get addPerson => '添加人员';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return '标记此说话者的其他片段（$selected/$total）';
  }

  @override
  String get tagOtherSegments => '标记其他片段';

  @override
  String get managePeople => '管理人员';

  @override
  String get shareViaSms => '通过短信分享';

  @override
  String get selectContactsToShareSummary => '选择联系人分享对话摘要';

  @override
  String get searchContactsHint => '搜索联系人...';

  @override
  String contactsSelectedCount(int count) {
    return '已选择 $count 个';
  }

  @override
  String get clearAllSelection => '全部清除';

  @override
  String get selectContactsToShare => '选择要分享的联系人';

  @override
  String shareWithContactCount(int count) {
    return '分享给 $count 个联系人';
  }

  @override
  String shareWithContactsCount(int count) {
    return '分享给 $count 个联系人';
  }

  @override
  String get contactsPermissionRequired => '需要通讯录权限';

  @override
  String get contactsPermissionRequiredForSms => '需要通讯录权限才能通过短信分享';

  @override
  String get grantContactsPermissionForSms => '请授予通讯录权限以便通过短信分享';

  @override
  String get noContactsWithPhoneNumbers => '未找到有电话号码的联系人';

  @override
  String get noContactsMatchSearch => '没有联系人与您的搜索匹配';

  @override
  String get failedToLoadContacts => '无法加载联系人';

  @override
  String get failedToPrepareConversationForSharing => '无法准备对话进行分享。请重试。';

  @override
  String get couldNotOpenSmsApp => '无法打开短信应用。请重试。';

  @override
  String heresWhatWeDiscussed(String link) {
    return '这是我们刚才讨论的内容: $link';
  }

  @override
  String get wifiSync => 'WiFi 同步';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item 已复制到剪贴板';
  }

  @override
  String get wifiConnectionFailedTitle => '连接失败';

  @override
  String connectingToDeviceName(String deviceName) {
    return '正在连接到 $deviceName';
  }

  @override
  String enableDeviceWifi(String deviceName) {
    return '启用 $deviceName 的 WiFi';
  }

  @override
  String connectToDeviceName(String deviceName) {
    return '连接到 $deviceName';
  }

  @override
  String get recordingDetails => '录音详情';

  @override
  String get storageLocationSdCard => 'SD 卡';

  @override
  String get storageLocationLimitlessPendant => 'Limitless 挂件';

  @override
  String get storageLocationPhone => '手机';

  @override
  String get storageLocationPhoneMemory => '手机（内存）';

  @override
  String storedOnDevice(String deviceName) {
    return '存储在 $deviceName';
  }

  @override
  String get transferring => '传输中...';

  @override
  String get transferRequired => '需要传输';

  @override
  String get downloadingAudioFromSdCard => '正在从设备 SD 卡下载音频';

  @override
  String get transferRequiredDescription => '此录音存储在设备的 SD 卡上。将其传输到手机以播放或分享。';

  @override
  String get cancelTransfer => '取消传输';

  @override
  String get transferToPhone => '传输到手机';

  @override
  String get privateAndSecureOnDevice => '在您的设备上私密且安全';

  @override
  String get recordingInfo => '录音信息';

  @override
  String get transferInProgress => '传输进行中...';

  @override
  String get shareRecording => '分享录音';

  @override
  String get deleteRecordingConfirmation => '您确定要永久删除此录音吗？此操作无法撤销。';

  @override
  String get recordingIdLabel => '录音 ID';

  @override
  String get dateTimeLabel => '日期和时间';

  @override
  String get durationLabel => '时长';

  @override
  String get audioFormatLabel => '音频格式';

  @override
  String get storageLocationLabel => '存储位置';

  @override
  String get estimatedSizeLabel => '估计大小';

  @override
  String get deviceModelLabel => '设备型号';

  @override
  String get deviceIdLabel => '设备 ID';

  @override
  String get statusLabel => '状态';

  @override
  String get statusProcessed => '已处理';

  @override
  String get statusUnprocessed => '未处理';

  @override
  String get switchedToFastTransfer => '已切换到快速传输';

  @override
  String get transferCompleteMessage => '传输完成！您现在可以播放此录音了。';

  @override
  String transferFailedMessage(String error) {
    return '传输失败：$error';
  }

  @override
  String get transferCancelled => '传输已取消';

  @override
  String get fastTransferEnabled => '快速传输已启用';

  @override
  String get bluetoothSyncEnabled => '蓝牙同步已启用';

  @override
  String get enableFastTransfer => '启用快速传输';

  @override
  String get fastTransferDescription => '快速传输使用WiFi实现约5倍的传输速度。传输期间，您的手机将临时连接到Omi设备的WiFi网络。';

  @override
  String get internetAccessPausedDuringTransfer => '传输期间互联网访问暂停';

  @override
  String get chooseTransferMethodDescription => '选择如何将录音从Omi设备传输到您的手机。';

  @override
  String get wifiSpeed => '通过WiFi约150 KB/s';

  @override
  String get fiveTimesFaster => '快5倍';

  @override
  String get fastTransferMethodDescription => '创建与Omi设备的直接WiFi连接。传输期间，您的手机将暂时断开常规WiFi连接。';

  @override
  String get bluetooth => '蓝牙';

  @override
  String get bleSpeed => '通过BLE约30 KB/s';

  @override
  String get bluetoothMethodDescription => '使用标准蓝牙低功耗连接。速度较慢，但不影响WiFi连接。';

  @override
  String get selected => '已选择';

  @override
  String get selectOption => '选择';

  @override
  String get lowBatteryAlertTitle => '电池电量低警告';

  @override
  String get lowBatteryAlertBody => '您的设备电池电量低。是时候充电了！🔋';

  @override
  String get deviceDisconnectedNotificationTitle => '您的 Omi 设备已断开连接';

  @override
  String get deviceDisconnectedNotificationBody => '请重新连接以继续使用 Omi。';

  @override
  String get firmwareUpdateAvailable => '固件更新可用';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return '您的 Omi 设备有新的固件更新（$version）可用。您想现在更新吗？';
  }

  @override
  String get later => '稍后';

  @override
  String get appDeletedSuccessfully => '应用删除成功';

  @override
  String get appDeleteFailed => '删除应用失败。请稍后重试。';

  @override
  String get appVisibilityChangedSuccessfully => '应用可见性更改成功。可能需要几分钟才能生效。';

  @override
  String get errorActivatingAppIntegration => '激活应用时出错。如果这是集成应用，请确保设置已完成。';

  @override
  String get errorUpdatingAppStatus => '更新应用状态时发生错误。';

  @override
  String get calculatingETA => '正在计算...';

  @override
  String aboutMinutesRemaining(int minutes) {
    return '大约还需 $minutes 分钟';
  }

  @override
  String get aboutAMinuteRemaining => '大约还需一分钟';

  @override
  String get almostDone => '即将完成...';

  @override
  String get omiSays => 'omi 说';

  @override
  String get analyzingYourData => '正在分析您的数据...';

  @override
  String migratingToProtection(String level) {
    return '正在迁移到 $level 保护级别...';
  }

  @override
  String get noDataToMigrateFinalizing => '没有需要迁移的数据。正在完成...';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return '正在迁移 $itemType... $percentage%';
  }

  @override
  String get allObjectsMigratedFinalizing => '所有对象已迁移。正在完成...';

  @override
  String get migrationErrorOccurred => '迁移过程中发生错误。请重试。';

  @override
  String get migrationComplete => '迁移完成！';

  @override
  String dataProtectedWithSettings(String level) {
    return '您的数据现已受到新的 $level 设置保护。';
  }

  @override
  String get chatsLowercase => '聊天';

  @override
  String get dataLowercase => '数据';

  @override
  String get fallNotificationTitle => '哎呀';

  @override
  String get fallNotificationBody => '您摔倒了吗？';

  @override
  String get importantConversationTitle => '重要对话';

  @override
  String get importantConversationBody => '您刚刚进行了一次重要对话。点击分享摘要。';

  @override
  String get templateName => '模板名称';

  @override
  String get templateNameHint => '例如：会议行动项提取器';

  @override
  String get nameMustBeAtLeast3Characters => '名称必须至少3个字符';

  @override
  String get conversationPromptHint => '例如，从提供的对话中提取行动项、决策和关键要点。';

  @override
  String get pleaseEnterAppPrompt => '请输入应用提示';

  @override
  String get promptMustBeAtLeast10Characters => '提示必须至少10个字符';

  @override
  String get anyoneCanDiscoverTemplate => '任何人都可以发现您的模板';

  @override
  String get onlyYouCanUseTemplate => '只有您可以使用此模板';

  @override
  String get generatingDescription => '正在生成描述...';

  @override
  String get creatingAppIcon => '正在创建应用图标...';

  @override
  String get installingApp => '正在安装应用...';

  @override
  String get appCreatedAndInstalled => '应用已创建并安装！';

  @override
  String get appCreatedSuccessfully => '应用创建成功！';

  @override
  String get failedToCreateApp => '创建应用失败。请重试。';

  @override
  String get addAppSelectCoreCapability => '请为您的应用选择一个核心功能';

  @override
  String get addAppSelectPaymentPlan => '请选择付款计划并输入应用价格';

  @override
  String get addAppSelectCapability => '请为您的应用选择至少一项功能';

  @override
  String get addAppSelectLogo => '请为您的应用选择一个标志';

  @override
  String get addAppEnterChatPrompt => '请输入应用的聊天提示';

  @override
  String get addAppEnterConversationPrompt => '请输入应用的对话提示';

  @override
  String get addAppSelectTriggerEvent => '请为您的应用选择一个触发事件';

  @override
  String get addAppEnterWebhookUrl => '请输入应用的Webhook URL';

  @override
  String get addAppSelectCategory => '请为您的应用选择一个类别';

  @override
  String get addAppFillRequiredFields => '请正确填写所有必填字段';

  @override
  String get addAppUpdatedSuccess => '应用更新成功 🚀';

  @override
  String get addAppUpdateFailed => '更新失败，请稍后重试';

  @override
  String get addAppSubmittedSuccess => '应用提交成功 🚀';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return '打开文件选择器时出错：$message';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return '选择图片时出错：$error';
  }

  @override
  String get addAppPhotosPermissionDenied => '照片权限被拒绝，请允许访问照片';

  @override
  String get addAppErrorSelectingImageRetry => '选择图片时出错，请重试。';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return '选择缩略图时出错：$error';
  }

  @override
  String get addAppErrorSelectingThumbnailRetry => '选择缩略图时出错，请重试。';

  @override
  String get addAppCapabilityConflictWithPersona => '无法同时选择其他功能和角色';

  @override
  String get addAppPersonaConflictWithCapabilities => '角色无法与其他功能一起选择';

  @override
  String get personaTwitterHandleNotFound => '未找到Twitter用户名';

  @override
  String get personaTwitterHandleSuspended => 'Twitter用户名已被暂停';

  @override
  String get personaFailedToVerifyTwitter => '验证Twitter用户名失败';

  @override
  String get personaFailedToFetch => '获取角色失败';

  @override
  String get personaFailedToCreate => '创建角色失败';

  @override
  String get personaConnectKnowledgeSource => '请至少连接一个数据源（Omi或Twitter）';

  @override
  String get personaUpdatedSuccessfully => '角色更新成功';

  @override
  String get personaFailedToUpdate => '角色更新失败';

  @override
  String get personaPleaseSelectImage => '请选择一张图片';

  @override
  String get personaFailedToCreateTryLater => '创建角色失败，请稍后重试。';

  @override
  String personaFailedToCreateWithError(String error) {
    return '创建角色失败：$error';
  }

  @override
  String get personaFailedToEnable => '启用角色失败';

  @override
  String personaErrorEnablingWithError(String error) {
    return '启用角色时出错：$error';
  }

  @override
  String get paymentFailedToFetchCountries => '获取支持的国家失败，请稍后重试。';

  @override
  String get paymentFailedToSetDefault => '设置默认付款方式失败，请稍后重试。';

  @override
  String get paymentFailedToSavePaypal => '保存PayPal详细信息失败，请稍后重试。';

  @override
  String get paypalEmailHint => 'nik@example.com';

  @override
  String get paypalMeLinkHint => 'paypal.me/nik';

  @override
  String get paymentMethodStripe => 'Stripe';

  @override
  String get paymentMethodPayPal => 'PayPal';

  @override
  String get paymentStatusActive => '已激活';

  @override
  String get paymentStatusConnected => '已连接';

  @override
  String get paymentStatusNotConnected => '未连接';

  @override
  String get paymentAppCost => '应用费用';

  @override
  String get paymentEnterValidAmount => '请输入有效金额';

  @override
  String get paymentEnterAmountGreaterThanZero => '请输入大于0的金额';

  @override
  String get paymentPlan => '付款计划';

  @override
  String get paymentNoneSelected => '未选择';

  @override
  String get aiGenPleaseEnterDescription => '请输入应用描述';

  @override
  String get aiGenCreatingAppIcon => '正在创建应用图标...';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return '发生错误：$message';
  }

  @override
  String get aiGenAppCreatedSuccessfully => '应用创建成功！';

  @override
  String get aiGenFailedToCreateApp => '创建应用失败';

  @override
  String get aiGenErrorWhileCreatingApp => '创建应用时发生错误';

  @override
  String get aiGenFailedToGenerateApp => '生成应用失败，请重试。';

  @override
  String get aiGenFailedToRegenerateIcon => '重新生成图标失败';

  @override
  String get aiGenPleaseGenerateAppFirst => '请先生成一个应用';

  @override
  String get xHandleTitle => '您的 X 用户名是什么？';

  @override
  String get xHandleDescription => '我们将根据您账户的活动\n预训练您的 Omi 克隆';

  @override
  String get xHandleHint => '@nikshevchenko';

  @override
  String get xHandlePleaseEnter => '请输入您的 X 用户名';

  @override
  String get xHandlePleaseEnterValid => '请输入有效的 X 用户名';

  @override
  String get nextButton => '下一步';

  @override
  String get connectOmiDevice => '连接 Omi 设备';

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return '您正在将无限版计划切换到 $title。您确定要继续吗？';
  }

  @override
  String get planUpgradeScheduledMessage => '升级已安排！您的月度计划将持续到计费周期结束，届时自动切换为年度计划。';

  @override
  String get couldNotSchedulePlanChange => '无法安排计划变更。请重试。';

  @override
  String get subscriptionReactivatedDefault => '您的订阅已重新激活！现在不收费 - 您将在当前周期结束时计费。';

  @override
  String get subscriptionSuccessfulCharged => '订阅成功！您已为新的计费周期付费。';

  @override
  String get couldNotProcessSubscription => '无法处理订阅。请重试。';

  @override
  String get couldNotLaunchUpgradePage => '无法打开升级页面。请重试。';

  @override
  String get transcriptionJsonPlaceholder => '在此粘贴您的 JSON 配置...';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get pricePlaceholder => '0.00';

  @override
  String importErrorOpeningFilePicker(String message) {
    return '打开文件选择器时出错：$message';
  }

  @override
  String importErrorGeneric(String error) {
    return '错误：$error';
  }

  @override
  String get mergeConversationsSuccessTitle => '会话合并成功';

  @override
  String mergeConversationsSuccessBody(int count) {
    return '$count个会话已成功合并';
  }

  @override
  String get dailyReflectionNotificationTitle => '每日反思时间';

  @override
  String get dailyReflectionNotificationBody => '告诉我你今天过得怎么样';

  @override
  String get actionItemReminderTitle => 'Omi 提醒';

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName 已断开连接';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return '请重新连接以继续使用您的 $deviceName。';
  }

  @override
  String get onboardingSignIn => '登录';

  @override
  String get onboardingYourName => '您的姓名';

  @override
  String get onboardingLanguage => '语言';

  @override
  String get onboardingPermissions => '权限';

  @override
  String get onboardingComplete => '完成';

  @override
  String get onboardingWelcomeToOmi => '欢迎使用 Omi';

  @override
  String get onboardingTellUsAboutYourself => '介绍一下您自己';

  @override
  String get onboardingChooseYourPreference => '选择您的偏好';

  @override
  String get onboardingGrantRequiredAccess => '授予所需权限';

  @override
  String get onboardingYoureAllSet => '您已准备就绪';

  @override
  String get searchTranscriptOrSummary => '搜索转录或摘要...';

  @override
  String get myGoal => '我的目标';

  @override
  String get appNotAvailable => '糟糕！您正在寻找的应用似乎不可用。';

  @override
  String get failedToConnectTodoist => '连接Todoist失败';

  @override
  String get failedToConnectAsana => '连接Asana失败';

  @override
  String get failedToConnectGoogleTasks => '连接Google Tasks失败';

  @override
  String get failedToConnectClickUp => '连接ClickUp失败';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return '连接$serviceName失败：$error';
  }

  @override
  String get successfullyConnectedTodoist => '已成功连接到Todoist！';

  @override
  String get failedToConnectTodoistRetry => '连接Todoist失败。请重试。';

  @override
  String get successfullyConnectedAsana => '已成功连接到Asana！';

  @override
  String get failedToConnectAsanaRetry => '连接Asana失败。请重试。';

  @override
  String get successfullyConnectedGoogleTasks => '已成功连接到Google Tasks！';

  @override
  String get failedToConnectGoogleTasksRetry => '连接Google Tasks失败。请重试。';

  @override
  String get successfullyConnectedClickUp => '已成功连接到ClickUp！';

  @override
  String get failedToConnectClickUpRetry => '连接ClickUp失败。请重试。';

  @override
  String get successfullyConnectedNotion => '已成功连接到Notion！';

  @override
  String get failedToRefreshNotionStatus => '刷新Notion连接状态失败。';

  @override
  String get successfullyConnectedGoogle => '已成功连接到Google！';

  @override
  String get failedToRefreshGoogleStatus => '刷新Google连接状态失败。';

  @override
  String get successfullyConnectedWhoop => '已成功连接到Whoop！';

  @override
  String get failedToRefreshWhoopStatus => '刷新Whoop连接状态失败。';

  @override
  String get successfullyConnectedGitHub => '已成功连接到GitHub！';

  @override
  String get failedToRefreshGitHubStatus => '刷新GitHub连接状态失败。';

  @override
  String get authFailedToSignInWithGoogle => '使用Google登录失败，请重试。';

  @override
  String get authenticationFailed => '身份验证失败。请重试。';

  @override
  String get authFailedToSignInWithApple => '使用Apple登录失败，请重试。';

  @override
  String get authFailedToRetrieveToken => '获取Firebase令牌失败，请重试。';

  @override
  String get authUnexpectedErrorFirebase => '登录时发生意外错误，Firebase错误，请重试。';

  @override
  String get authUnexpectedError => '登录时发生意外错误，请重试';

  @override
  String get authFailedToLinkGoogle => '与Google关联失败，请重试。';

  @override
  String get authFailedToLinkApple => '与Apple关联失败，请重试。';

  @override
  String get onboardingBluetoothRequired => '需要蓝牙权限才能连接到您的设备。';

  @override
  String get onboardingBluetoothDeniedSystemPrefs => '蓝牙权限被拒绝。请在系统偏好设置中授予权限。';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return '蓝牙权限状态：$status。请检查系统偏好设置。';
  }

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return '无法检查蓝牙权限：$error';
  }

  @override
  String get onboardingNotificationDeniedSystemPrefs => '通知权限被拒绝。请在系统偏好设置中授予权限。';

  @override
  String get onboardingNotificationDeniedNotifications => '通知权限被拒绝。请在系统偏好设置 > 通知中授予权限。';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return '通知权限状态：$status。请检查系统偏好设置。';
  }

  @override
  String onboardingFailedCheckNotification(String error) {
    return '无法检查通知权限：$error';
  }

  @override
  String get onboardingLocationGrantInSettings => '请在设置 > 隐私与安全 > 定位服务中授予位置权限';

  @override
  String get onboardingMicrophoneRequired => '录音需要麦克风权限。';

  @override
  String get onboardingMicrophoneDenied => '麦克风权限被拒绝。请在系统偏好设置 > 隐私与安全 > 麦克风中授予权限。';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return '麦克风权限状态：$status。请检查系统偏好设置。';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return '无法检查麦克风权限：$error';
  }

  @override
  String get onboardingScreenCaptureRequired => '录制系统音频需要屏幕捕获权限。';

  @override
  String get onboardingScreenCaptureDenied => '屏幕捕获权限被拒绝。请在系统偏好设置 > 隐私与安全 > 屏幕录制中授予权限。';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return '屏幕捕获权限状态：$status。请检查系统偏好设置。';
  }

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return '无法检查屏幕捕获权限：$error';
  }

  @override
  String get onboardingAccessibilityRequired => '检测浏览器会议需要辅助功能权限。';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return '辅助功能权限状态：$status。请检查系统偏好设置。';
  }

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return '无法检查辅助功能权限：$error';
  }

  @override
  String get msgCameraNotAvailable => '此平台不支持相机拍摄';

  @override
  String get msgCameraPermissionDenied => '相机权限被拒绝。请允许访问相机';

  @override
  String msgCameraAccessError(String error) {
    return '访问相机错误：$error';
  }

  @override
  String get msgPhotoError => '拍照错误。请重试。';

  @override
  String get msgMaxImagesLimit => '您最多只能选择4张图片';

  @override
  String msgFilePickerError(String error) {
    return '打开文件选择器错误：$error';
  }

  @override
  String msgSelectImagesError(String error) {
    return '选择图片错误：$error';
  }

  @override
  String get msgPhotosPermissionDenied => '照片权限被拒绝。请允许访问照片以选择图片';

  @override
  String get msgSelectImagesGenericError => '选择图片错误。请重试。';

  @override
  String get msgMaxFilesLimit => '您最多只能选择4个文件';

  @override
  String msgSelectFilesError(String error) {
    return '选择文件错误：$error';
  }

  @override
  String get msgSelectFilesGenericError => '选择文件错误。请重试。';

  @override
  String get msgUploadFileFailed => '文件上传失败，请稍后重试';

  @override
  String get msgReadingMemories => '正在读取您的记忆...';

  @override
  String get msgLearningMemories => '正在从您的记忆中学习...';

  @override
  String get msgUploadAttachedFileFailed => '上传附件失败。';

  @override
  String captureRecordingError(String error) {
    return '录音过程中发生错误：$error';
  }

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return '录制已停止：$reason。您可能需要重新连接外部显示器或重新开始录制。';
  }

  @override
  String get captureMicrophonePermissionRequired => '需要麦克风权限';

  @override
  String get captureMicrophonePermissionInSystemPreferences => '在系统偏好设置中授予麦克风权限';

  @override
  String get captureScreenRecordingPermissionRequired => '需要屏幕录制权限';

  @override
  String get captureDisplayDetectionFailed => '显示器检测失败。录制已停止。';

  @override
  String get devModeInvalidAudioBytesWebhookUrl => '无效的音频字节 webhook URL';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl => '无效的实时转录 webhook URL';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl => '无效的对话创建 webhook URL';

  @override
  String get devModeInvalidDaySummaryWebhookUrl => '无效的每日摘要 webhook URL';

  @override
  String get devModeSettingsSaved => '设置已保存！';

  @override
  String get voiceFailedToTranscribe => '音频转录失败';

  @override
  String get locationPermissionRequired => '位置权限请求';

  @override
  String get locationPermissionContent => '快速传输需要位置权限来验证WiFi连接。请授予位置权限以继续。';

  @override
  String get pdfTranscriptExport => '导出文字记录';

  @override
  String get pdfConversationExport => '导出对话';

  @override
  String pdfTitleLabel(String title) {
    return '标题：$title';
  }

  @override
  String get conversationNewIndicator => '新的 🚀';

  @override
  String conversationPhotosCount(int count) {
    return '$count 张照片';
  }

  @override
  String get mergingStatus => '合并中...';

  @override
  String timeSecsSingular(int count) {
    return '$count秒';
  }

  @override
  String timeSecsPlural(int count) {
    return '$count秒';
  }

  @override
  String timeMinSingular(int count) {
    return '$count分钟';
  }

  @override
  String timeMinsPlural(int count) {
    return '$count分钟';
  }

  @override
  String timeMinsAndSecs(int mins, int secs) {
    return '$mins分钟$secs秒';
  }

  @override
  String timeHourSingular(int count) {
    return '$count小时';
  }

  @override
  String timeHoursPlural(int count) {
    return '$count小时';
  }

  @override
  String timeHoursAndMins(int hours, int mins) {
    return '$hours小时$mins分钟';
  }

  @override
  String timeDaySingular(int count) {
    return '$count天';
  }

  @override
  String timeDaysPlural(int count) {
    return '$count天';
  }

  @override
  String timeDaysAndHours(int days, int hours) {
    return '$days天$hours小时';
  }

  @override
  String timeCompactSecs(int count) {
    return '$count秒';
  }

  @override
  String timeCompactMins(int count) {
    return '$count分';
  }

  @override
  String timeCompactMinsAndSecs(int mins, int secs) {
    return '$mins分$secs秒';
  }

  @override
  String timeCompactHours(int count) {
    return '$count时';
  }

  @override
  String timeCompactHoursAndMins(int hours, int mins) {
    return '$hours时$mins分';
  }

  @override
  String get moveToFolder => '移动到文件夹';

  @override
  String get noFoldersAvailable => '没有可用的文件夹';

  @override
  String get newFolder => '新建文件夹';

  @override
  String get color => '颜色';

  @override
  String get waitingForDevice => '等待设备...';

  @override
  String get saySomething => '说点什么...';

  @override
  String get initialisingSystemAudio => '正在初始化系统音频';

  @override
  String get stopRecording => '停止录音';

  @override
  String get continueRecording => '继续录音';

  @override
  String get initialisingRecorder => '正在初始化录音器';

  @override
  String get pauseRecording => '暂停录音';

  @override
  String get resumeRecording => '继续录音';

  @override
  String get noDailyRecapsYet => '还没有每日总结';

  @override
  String get dailyRecapsDescription => '您的每日总结生成后将显示在这里';

  @override
  String get chooseTransferMethod => '选择传输方式';

  @override
  String get fastTransferSpeed => '通过WiFi ~150 KB/s';

  @override
  String largeTimeGapDetected(String gap) {
    return '检测到较大时间间隔 ($gap)';
  }

  @override
  String largeTimeGapsDetected(String gaps) {
    return '检测到多个较大时间间隔 ($gaps)';
  }

  @override
  String get deviceDoesNotSupportWifiSwitchingToBle => '设备不支持WiFi同步,正在切换到蓝牙';

  @override
  String get appleHealthNotAvailable => '此设备上不可用Apple Health';

  @override
  String get downloadAudio => '下载音频';

  @override
  String get audioDownloadSuccess => '音频下载成功';

  @override
  String get audioDownloadFailed => '音频下载失败';

  @override
  String get downloadingAudio => '正在下载音频...';

  @override
  String get shareAudio => '分享音频';

  @override
  String get preparingAudio => '正在准备音频';

  @override
  String get gettingAudioFiles => '正在获取音频文件...';

  @override
  String get downloadingAudioProgress => '正在下载音频';

  @override
  String get processingAudio => '正在处理音频';

  @override
  String get combiningAudioFiles => '正在合并音频文件...';

  @override
  String get audioReady => '音频已准备好';

  @override
  String get openingShareSheet => '正在打开分享页面...';

  @override
  String get audioShareFailed => '分享失败';

  @override
  String get dailyRecaps => '每日回顾';

  @override
  String get removeFilter => '移除筛选';

  @override
  String get categoryConversationAnalysis => '对话分析';

  @override
  String get categoryPersonalityClone => '人格克隆';

  @override
  String get categoryHealth => '健康';

  @override
  String get categoryEducation => '教育';

  @override
  String get categoryCommunication => '沟通';

  @override
  String get categoryEmotionalSupport => '情感支持';

  @override
  String get categoryProductivity => '生产力';

  @override
  String get categoryEntertainment => '娱乐';

  @override
  String get categoryFinancial => '金融';

  @override
  String get categoryTravel => '旅行';

  @override
  String get categorySafety => '安全';

  @override
  String get categoryShopping => '购物';

  @override
  String get categorySocial => '社交';

  @override
  String get categoryNews => '新闻';

  @override
  String get categoryUtilities => '工具';

  @override
  String get categoryOther => '其他';

  @override
  String get capabilityChat => '聊天';

  @override
  String get capabilityConversations => '对话';

  @override
  String get capabilityExternalIntegration => '外部集成';

  @override
  String get capabilityNotification => '通知';

  @override
  String get triggerAudioBytes => '音频字节';

  @override
  String get triggerConversationCreation => '创建对话';

  @override
  String get triggerTranscriptProcessed => '转录已处理';

  @override
  String get actionCreateConversations => '创建对话';

  @override
  String get actionCreateMemories => '创建记忆';

  @override
  String get actionReadConversations => '读取对话';

  @override
  String get actionReadMemories => '读取记忆';

  @override
  String get actionReadTasks => '读取任务';

  @override
  String get scopeUserName => '用户名';

  @override
  String get scopeUserFacts => '用户信息';

  @override
  String get scopeUserConversations => '用户对话';

  @override
  String get scopeUserChat => '用户聊天';

  @override
  String get capabilitySummary => '摘要';

  @override
  String get capabilityFeatured => '精选';

  @override
  String get capabilityTasks => '任务';

  @override
  String get capabilityIntegrations => '集成';

  @override
  String get categoryPersonalityClones => '人格克隆';

  @override
  String get categoryProductivityLifestyle => '生产力与生活方式';

  @override
  String get categorySocialEntertainment => '社交与娱乐';

  @override
  String get categoryProductivityTools => '生产力工具';

  @override
  String get categoryPersonalWellness => '个人健康';

  @override
  String get rating => '评分';

  @override
  String get categories => '分类';

  @override
  String get sortBy => '排序';

  @override
  String get highestRating => '最高评分';

  @override
  String get lowestRating => '最低评分';

  @override
  String get resetFilters => '重置筛选';

  @override
  String get applyFilters => '应用筛选';

  @override
  String get mostInstalls => '安装最多';

  @override
  String get couldNotOpenUrl => '无法打开链接，请重试。';

  @override
  String get newTask => '新任务';

  @override
  String get viewAll => '查看全部';

  @override
  String get addTask => '添加任务';

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
  String get audioPlaybackUnavailable => '音频文件无法播放';

  @override
  String get audioPlaybackFailed => '无法播放音频。文件可能已损坏或丢失。';

  @override
  String get connectionGuide => '连接指南';

  @override
  String get iveDoneThis => '我已完成';

  @override
  String get pairNewDevice => '配对新设备';

  @override
  String get dontSeeYourDevice => '看不到你的设备？';

  @override
  String get reportAnIssue => '报告问题';

  @override
  String get pairingTitleOmi => '开启Omi';

  @override
  String get pairingDescOmi => '按住设备直到振动以开机。';

  @override
  String get pairingTitleOmiDevkit => '将Omi DevKit设置为配对模式';

  @override
  String get pairingDescOmiDevkit => '按一次按钮开机。配对模式下LED将闪烁紫色。';

  @override
  String get pairingTitleOmiGlass => '开启Omi Glass';

  @override
  String get pairingDescOmiGlass => '按住侧面按钮3秒以开机。';

  @override
  String get pairingTitlePlaudNote => '将Plaud Note设置为配对模式';

  @override
  String get pairingDescPlaudNote => '按住侧面按钮2秒。准备好配对时红色LED将闪烁。';

  @override
  String get pairingTitleBee => '将Bee设置为配对模式';

  @override
  String get pairingDescBee => '连续按下按钮5次。指示灯将开始闪烁蓝色和绿色。';

  @override
  String get pairingTitleLimitless => '将Limitless设置为配对模式';

  @override
  String get pairingDescLimitless => '当有灯亮时，按一次然后按住直到设备显示粉色灯光，然后松开。';

  @override
  String get pairingTitleFriendPendant => '将Friend Pendant设置为配对模式';

  @override
  String get pairingDescFriendPendant => '按下吊坠上的按钮以开机。设备将自动进入配对模式。';

  @override
  String get pairingTitleFieldy => '将Fieldy设置为配对模式';

  @override
  String get pairingDescFieldy => '按住设备直到灯亮以开机。';

  @override
  String get pairingTitleAppleWatch => '连接Apple Watch';

  @override
  String get pairingDescAppleWatch => '在Apple Watch上安装并打开Omi应用，然后在应用中点击连接。';

  @override
  String get pairingTitleNeoOne => '将Neo One设置为配对模式';

  @override
  String get pairingDescNeoOne => '按住电源按钮直到LED闪烁。设备将变为可发现状态。';
}
