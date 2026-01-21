// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Japanese (`ja`).
class AppLocalizationsJa extends AppLocalizations {
  AppLocalizationsJa([String locale = 'ja']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => '会話';

  @override
  String get transcriptTab => 'トランスクリプト';

  @override
  String get actionItemsTab => 'アクションアイテム';

  @override
  String get deleteConversationTitle => '会話を削除しますか？';

  @override
  String get deleteConversationMessage => 'この会話を削除してもよろしいですか？この操作は元に戻せません。';

  @override
  String get confirm => '確認';

  @override
  String get cancel => 'キャンセル';

  @override
  String get ok => 'OK';

  @override
  String get delete => '削除';

  @override
  String get add => '追加';

  @override
  String get update => '更新';

  @override
  String get save => '保存';

  @override
  String get edit => '編集';

  @override
  String get close => '閉じる';

  @override
  String get clear => 'クリア';

  @override
  String get copyTranscript => '文字起こしをコピー';

  @override
  String get copySummary => '要約をコピー';

  @override
  String get testPrompt => 'プロンプトをテスト';

  @override
  String get reprocessConversation => '会話を再処理';

  @override
  String get deleteConversation => '会話を削除';

  @override
  String get contentCopied => 'クリップボードにコピーしました';

  @override
  String get failedToUpdateStarred => 'スター状態の更新に失敗しました。';

  @override
  String get conversationUrlNotShared => '会話URLを共有できませんでした。';

  @override
  String get errorProcessingConversation => '会話の処理中にエラーが発生しました。後でもう一度お試しください。';

  @override
  String get noInternetConnection => 'インターネット接続がありません';

  @override
  String get unableToDeleteConversation => '会話を削除できません';

  @override
  String get somethingWentWrong => '問題が発生しました！後でもう一度お試しください。';

  @override
  String get copyErrorMessage => 'エラーメッセージをコピー';

  @override
  String get errorCopied => 'エラーメッセージをクリップボードにコピーしました';

  @override
  String get remaining => '残り';

  @override
  String get loading => '読み込み中...';

  @override
  String get loadingDuration => '再生時間を読み込み中...';

  @override
  String secondsCount(int count) {
    return '$count秒';
  }

  @override
  String get people => 'ピープル';

  @override
  String get addNewPerson => '新しい人を追加';

  @override
  String get editPerson => '人を編集';

  @override
  String get createPersonHint => '新しい人を作成して、Omiにその人の声も認識させましょう！';

  @override
  String get speechProfile => '音声プロファイル';

  @override
  String sampleNumber(int number) {
    return 'サンプル $number';
  }

  @override
  String get settings => '設定';

  @override
  String get language => '言語';

  @override
  String get selectLanguage => '言語を選択';

  @override
  String get deleting => '削除中...';

  @override
  String get pleaseCompleteAuthentication => 'ブラウザで認証を完了してください。完了したらアプリに戻ってください。';

  @override
  String get failedToStartAuthentication => '認証の開始に失敗しました';

  @override
  String get importStarted => 'インポートを開始しました！完了したら通知されます。';

  @override
  String get failedToStartImport => 'インポートの開始に失敗しました。もう一度お試しください。';

  @override
  String get couldNotAccessFile => '選択したファイルにアクセスできませんでした';

  @override
  String get askOmi => 'Omiに質問';

  @override
  String get done => '完了';

  @override
  String get disconnected => '切断されました';

  @override
  String get searching => '検索中...';

  @override
  String get connectDevice => 'デバイスを接続';

  @override
  String get monthlyLimitReached => '月間制限に達しました。';

  @override
  String get checkUsage => '使用状況を確認';

  @override
  String get syncingRecordings => '録音を同期中';

  @override
  String get recordingsToSync => '同期する録音があります';

  @override
  String get allCaughtUp => 'すべて同期済み';

  @override
  String get sync => '同期';

  @override
  String get pendantUpToDate => 'ペンダントは最新です';

  @override
  String get allRecordingsSynced => 'すべての録音が同期されました';

  @override
  String get syncingInProgress => '同期中';

  @override
  String get readyToSync => '同期の準備ができました';

  @override
  String get tapSyncToStart => '同期をタップして開始';

  @override
  String get pendantNotConnected => 'ペンダントが接続されていません。接続して同期してください。';

  @override
  String get everythingSynced => 'すべて同期済みです。';

  @override
  String get recordingsNotSynced => 'まだ同期されていない録音があります。';

  @override
  String get syncingBackground => 'バックグラウンドで録音を同期し続けます。';

  @override
  String get noConversationsYet => 'まだ会話がありません';

  @override
  String get noStarredConversations => 'スター付きの会話がありません';

  @override
  String get starConversationHint => '会話をスターするには、会話を開いてヘッダーのスターアイコンをタップしてください。';

  @override
  String get searchConversations => '会話を検索...';

  @override
  String selectedCount(int count, Object s) {
    return '$count件選択中';
  }

  @override
  String get merge => 'マージ';

  @override
  String get mergeConversations => '会話をマージ';

  @override
  String mergeConversationsMessage(int count) {
    return '$count件の会話が1つにまとめられます。すべてのコンテンツがマージされ、再生成されます。';
  }

  @override
  String get mergingInBackground => 'バックグラウンドでマージ中。しばらくお待ちください。';

  @override
  String get failedToStartMerge => 'マージの開始に失敗しました';

  @override
  String get askAnything => '何でも聞いてください';

  @override
  String get noMessagesYet => 'まだメッセージがありません！\n会話を始めてみませんか？';

  @override
  String get deletingMessages => 'Omiのメモリからメッセージを削除しています...';

  @override
  String get messageCopied => '✨ メッセージをクリップボードにコピーしました';

  @override
  String get cannotReportOwnMessage => '自分のメッセージを報告することはできません。';

  @override
  String get reportMessage => 'メッセージを報告';

  @override
  String get reportMessageConfirm => 'このメッセージを報告してもよろしいですか？';

  @override
  String get messageReported => 'メッセージを報告しました。';

  @override
  String get thankYouFeedback => 'フィードバックありがとうございます！';

  @override
  String get clearChat => 'チャットを削除';

  @override
  String get clearChatConfirm => 'チャットを消去してもよろしいですか？この操作は元に戻せません。';

  @override
  String get maxFilesLimit => '一度にアップロードできるファイルは4つまでです';

  @override
  String get chatWithOmi => 'Omiとチャット';

  @override
  String get apps => 'アプリ';

  @override
  String get noAppsFound => 'アプリが見つかりません';

  @override
  String get tryAdjustingSearch => '検索やフィルターを調整してみてください';

  @override
  String get createYourOwnApp => '独自のアプリを作成';

  @override
  String get buildAndShareApp => 'カスタムアプリを作成して共有';

  @override
  String get searchApps => 'アプリを検索...';

  @override
  String get myApps => 'マイアプリ';

  @override
  String get installedApps => 'インストール済みアプリ';

  @override
  String get unableToFetchApps => 'アプリを取得できません :(\n\nインターネット接続を確認して、もう一度お試しください。';

  @override
  String get aboutOmi => 'Omiについて';

  @override
  String get privacyPolicy => 'プライバシーポリシー';

  @override
  String get visitWebsite => 'ウェブサイトを訪問';

  @override
  String get helpOrInquiries => 'ヘルプまたはお問い合わせ？';

  @override
  String get joinCommunity => 'コミュニティに参加！';

  @override
  String get membersAndCounting => '8000+人のメンバーがいて増え続けています。';

  @override
  String get deleteAccountTitle => 'アカウントを削除';

  @override
  String get deleteAccountConfirm => '本当にアカウントを削除しますか？';

  @override
  String get cannotBeUndone => 'この操作は元に戻せません。';

  @override
  String get allDataErased => 'すべての記録と会話が完全に消去されます。';

  @override
  String get appsDisconnected => 'アプリと連携は直ちに解除されます。';

  @override
  String get exportBeforeDelete => '削除前にデータをエクスポートできますが、削除後は復元できません。';

  @override
  String get deleteAccountCheckbox => 'アカウントの削除は永久的であり、記録や会話を含むすべてのデータが失われ、復元できないことを理解しています。';

  @override
  String get areYouSure => '本当によろしいですか？';

  @override
  String get deleteAccountFinal => 'この操作は取り消せず、アカウントとすべての関連データが完全に削除されます。続行してもよろしいですか？';

  @override
  String get deleteNow => '今すぐ削除';

  @override
  String get goBack => '戻る';

  @override
  String get checkBoxToConfirm => 'アカウントの削除が永久的かつ取り消し不可能であることを確認するため、チェックボックスにチェックを入れてください。';

  @override
  String get profile => 'プロフィール';

  @override
  String get name => '名前';

  @override
  String get email => 'メール';

  @override
  String get customVocabulary => 'カスタム語彙';

  @override
  String get identifyingOthers => '他者の識別';

  @override
  String get paymentMethods => '支払い方法';

  @override
  String get conversationDisplay => '会話の表示';

  @override
  String get dataPrivacy => 'データプライバシー';

  @override
  String get userId => 'ユーザーID';

  @override
  String get notSet => '未設定';

  @override
  String get userIdCopied => 'ユーザーIDをクリップボードにコピーしました';

  @override
  String get systemDefault => 'システムの既定';

  @override
  String get planAndUsage => 'プランと使用状況';

  @override
  String get offlineSync => 'オフライン同期';

  @override
  String get deviceSettings => 'デバイス設定';

  @override
  String get chatTools => 'チャットツール';

  @override
  String get feedbackBug => 'フィードバック / バグ報告';

  @override
  String get helpCenter => 'ヘルプセンター';

  @override
  String get developerSettings => '開発者設定';

  @override
  String get getOmiForMac => 'Mac用Omiを入手';

  @override
  String get referralProgram => '紹介プログラム';

  @override
  String get signOut => 'サインアウト';

  @override
  String get appAndDeviceCopied => 'アプリとデバイスの詳細をコピーしました';

  @override
  String get wrapped2025 => 'Wrapped 2025';

  @override
  String get yourPrivacyYourControl => 'プライバシーはあなたの手に';

  @override
  String get privacyIntro => 'Omiでは、あなたのプライバシーを守ることに尽力しています。このページでは、データの保存と使用方法を管理できます。';

  @override
  String get learnMore => '詳細を見る...';

  @override
  String get dataProtectionLevel => 'データ保護レベル';

  @override
  String get dataProtectionDesc => 'データは強力な暗号化で既定で保護されています。以下の設定と今後のプライバシーオプションを確認してください。';

  @override
  String get appAccess => 'アプリのアクセス';

  @override
  String get appAccessDesc => '以下のアプリがあなたのデータにアクセスできます。アプリをタップして権限を管理してください。';

  @override
  String get noAppsExternalAccess => 'インストールされたアプリは外部からデータにアクセスしていません。';

  @override
  String get deviceName => 'デバイス名';

  @override
  String get deviceId => 'デバイスID';

  @override
  String get firmware => 'ファームウェア';

  @override
  String get sdCardSync => 'SDカード同期';

  @override
  String get hardwareRevision => 'ハードウェアリビジョン';

  @override
  String get modelNumber => 'モデル番号';

  @override
  String get manufacturer => '製造元';

  @override
  String get doubleTap => 'ダブルタップ';

  @override
  String get ledBrightness => 'LED明るさ';

  @override
  String get micGain => 'マイクゲイン';

  @override
  String get disconnect => '接続解除';

  @override
  String get forgetDevice => 'デバイスを忘れる';

  @override
  String get chargingIssues => '充電の問題';

  @override
  String get disconnectDevice => 'デバイスの切断';

  @override
  String get unpairDevice => 'デバイスのペアリング解除';

  @override
  String get unpairAndForget => 'ペアリング解除してデバイスを忘れる';

  @override
  String get deviceDisconnectedMessage => 'Omiが切断されました 😔';

  @override
  String get deviceUnpairedMessage => 'デバイスのペアリングが解除されました。設定 > Bluetoothに移動し、デバイスを削除してペアリング解除を完了してください。';

  @override
  String get unpairDialogTitle => 'デバイスのペアリング解除';

  @override
  String get unpairDialogMessage => 'これにより、デバイスのペアリングが解除され、別の電話に接続できるようになります。プロセスを完了するには、設定 > Bluetoothに移動してデバイスを忘れる必要があります。';

  @override
  String get deviceNotConnected => 'デバイスが接続されていません';

  @override
  String get connectDeviceMessage => 'デバイス設定とカスタマイズにアクセスするには、Omiデバイスを接続してください';

  @override
  String get deviceInfoSection => 'デバイス情報';

  @override
  String get customizationSection => 'カスタマイズ';

  @override
  String get hardwareSection => 'ハードウェア';

  @override
  String get v2Undetected => 'V2が検出されません';

  @override
  String get v2UndetectedMessage => 'V1デバイスをお持ちか、デバイスが接続されていないようです。SDカード機能はV2デバイスでのみ利用可能です。';

  @override
  String get endConversation => '会話を終了';

  @override
  String get pauseResume => '一時停止/再開';

  @override
  String get starConversation => '会話にスターを付ける';

  @override
  String get doubleTapAction => 'ダブルタップアクション';

  @override
  String get endAndProcess => '終了して会話を処理';

  @override
  String get pauseResumeRecording => '録音の一時停止/再開';

  @override
  String get starOngoing => '進行中の会話にスターを付ける';

  @override
  String get off => 'Off';

  @override
  String get max => '最大';

  @override
  String get mute => 'ミュート';

  @override
  String get quiet => '静か';

  @override
  String get normal => '通常';

  @override
  String get high => '高';

  @override
  String get micGainDescMuted => 'マイクはミュートされています';

  @override
  String get micGainDescLow => '非常に静か - 騒がしい環境向け';

  @override
  String get micGainDescModerate => '静か - 適度な騒音向け';

  @override
  String get micGainDescNeutral => 'ニュートラル - バランスの取れた録音';

  @override
  String get micGainDescSlightlyBoosted => 'わずかにブースト - 通常使用';

  @override
  String get micGainDescBoosted => 'ブースト - 静かな環境向け';

  @override
  String get micGainDescHigh => '高 - 遠くの声や柔らかい声向け';

  @override
  String get micGainDescVeryHigh => '非常に高 - 非常に静かな音源向け';

  @override
  String get micGainDescMax => '最大 - 注意して使用してください';

  @override
  String get developerSettingsTitle => '開発者設定';

  @override
  String get saving => '保存中...';

  @override
  String get personaConfig => 'AIペルソナを設定';

  @override
  String get beta => 'ベータ';

  @override
  String get transcription => '文字起こし';

  @override
  String get transcriptionConfig => 'STTプロバイダーを設定';

  @override
  String get conversationTimeout => '会話のタイムアウト';

  @override
  String get conversationTimeoutConfig => '会話の自動終了時間を設定';

  @override
  String get importData => 'データのインポート';

  @override
  String get importDataConfig => '他のソースからデータをインポート';

  @override
  String get debugDiagnostics => 'デバッグと診断';

  @override
  String get endpointUrl => 'エンドポイントURL';

  @override
  String get noApiKeys => 'APIキーはまだありません';

  @override
  String get createKeyToStart => 'キーを作成して開始';

  @override
  String get createKey => 'キーを作成';

  @override
  String get docs => 'ドキュメント';

  @override
  String get yourOmiInsights => 'Omiの分析情報';

  @override
  String get today => '今日';

  @override
  String get thisMonth => '今月';

  @override
  String get thisYear => '今年';

  @override
  String get allTime => '全期間';

  @override
  String get noActivityYet => 'アクティビティはまだありません';

  @override
  String get startConversationToSeeInsights => 'Omiと会話を始めて\n分析情報をここに表示しましょう。';

  @override
  String get listening => 'リスニング';

  @override
  String get listeningSubtitle => 'Omiがアクティブにリスニングした合計時間。';

  @override
  String get understanding => '理解';

  @override
  String get understandingSubtitle => '会話から理解された単語数。';

  @override
  String get providing => '提供';

  @override
  String get providingSubtitle => '自動的にキャプチャされたアクションアイテムとメモ。';

  @override
  String get remembering => '記憶';

  @override
  String get rememberingSubtitle => 'あなたのために記憶された事実と詳細。';

  @override
  String get unlimitedPlan => '無制限プラン';

  @override
  String get managePlan => 'プランの管理';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'プランは$dateにキャンセルされます。';
  }

  @override
  String renewsOn(String date) {
    return 'プランは$dateに更新されます。';
  }

  @override
  String get basicPlan => '無料プラン';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$limit分中$used分使用済み';
  }

  @override
  String get upgrade => 'アップグレード';

  @override
  String get upgradeToUnlimited => '無制限にアップグレード';

  @override
  String basicPlanDesc(int limit) {
    return 'プランには月$limit分の無料枠が含まれています。無制限にするにはアップグレードしてください。';
  }

  @override
  String get shareStatsMessage => 'Omiの統計をシェア！(omi.me - 常時ONのAIアシスタント)';

  @override
  String get sharePeriodToday => '今日、Omiは:';

  @override
  String get sharePeriodMonth => '今月、Omiは:';

  @override
  String get sharePeriodYear => '今年、Omiは:';

  @override
  String get sharePeriodAllTime => 'これまで、Omiは:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 $minutes分間リスニングしました';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 $words語を理解しました';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ $count個のインサイトを提供しました';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 $count個の記憶を保存しました';
  }

  @override
  String get debugLogs => 'デバッグログ';

  @override
  String get debugLogsAutoDelete => '3日後に自動削除されます。';

  @override
  String get debugLogsDesc => '問題の診断に役立ちます';

  @override
  String get noLogFilesFound => 'ログファイルが見つかりません。';

  @override
  String get omiDebugLog => 'Omiデバッグログ';

  @override
  String get logShared => 'ログを共有しました';

  @override
  String get selectLogFile => 'ログファイルを選択';

  @override
  String get shareLogs => 'ログを共有';

  @override
  String get debugLogCleared => 'デバッグログを消去しました';

  @override
  String get exportStarted => 'エクスポートを開始しました。数秒かかる場合があります...';

  @override
  String get exportAllData => '全データをエクスポート';

  @override
  String get exportDataDesc => '会話をJSONファイルにエクスポート';

  @override
  String get exportedConversations => 'Omiからエクスポートされた会話';

  @override
  String get exportShared => 'エクスポートを共有しました';

  @override
  String get deleteKnowledgeGraphTitle => 'ナレッジグラフを削除しますか？';

  @override
  String get deleteKnowledgeGraphMessage => 'これにより、派生したすべてのナレッジグラフデータ（ノードと接続）が削除されます。元の記憶は安全なままです。グラフは時間の経過とともに、または次のリクエスト時に再構築されます。';

  @override
  String get knowledgeGraphDeleted => 'ナレッジグラフを削除しました';

  @override
  String deleteGraphFailed(String error) {
    return 'グラフの削除に失敗しました: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'ナレッジグラフを削除';

  @override
  String get deleteKnowledgeGraphDesc => 'すべてのノードと接続を消去';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'MCPサーバー';

  @override
  String get mcpServerDesc => 'AIアシスタントをデータに接続';

  @override
  String get serverUrl => 'サーバーURL';

  @override
  String get urlCopied => 'URLをコピーしました';

  @override
  String get apiKeyAuth => 'APIキー認証';

  @override
  String get header => 'ヘッダー';

  @override
  String get authorizationBearer => 'Authorization: Bearer <key>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'クライアントID';

  @override
  String get clientSecret => 'クライアントシークレット';

  @override
  String get useMcpApiKey => 'MCP APIキーを使用してください';

  @override
  String get webhooks => 'Webhook';

  @override
  String get conversationEvents => '会話イベント';

  @override
  String get newConversationCreated => '新しい会話が作成されました';

  @override
  String get realtimeTranscript => 'リアルタイム文字起こし';

  @override
  String get transcriptReceived => '文字起こしを受信しました';

  @override
  String get audioBytes => '音声バイト';

  @override
  String get audioDataReceived => '音声データを受信しました';

  @override
  String get intervalSeconds => '間隔（秒）';

  @override
  String get daySummary => '日次サマリー';

  @override
  String get summaryGenerated => '要約が生成されました';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'claude_desktop_config.jsonに追加';

  @override
  String get copyConfig => '設定をコピー';

  @override
  String get configCopied => '設定をクリップボードにコピーしました';

  @override
  String get listeningMins => 'リスニング（分）';

  @override
  String get understandingWords => '理解（語数）';

  @override
  String get insights => '洞察';

  @override
  String get memories => '思い出';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '今月 $limit分中$used分使用済み';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '今月 $limit語中$used語使用済み';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '今月 $limit個中$used個のインサイト取得済み';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return '今月 $limit個中$used個の記憶作成済み';
  }

  @override
  String get visibility => '表示設定';

  @override
  String get visibilitySubtitle => 'リストに表示する会話を管理します';

  @override
  String get showShortConversations => '短い会話を表示';

  @override
  String get showShortConversationsDesc => 'しきい値より短い会話を表示します';

  @override
  String get showDiscardedConversations => '破棄した会話を表示';

  @override
  String get showDiscardedConversationsDesc => '破棄済みの会話を含めます';

  @override
  String get shortConversationThreshold => '短い会話のしきい値';

  @override
  String get shortConversationThresholdSubtitle => '上記で有効にしない限り、この時間より短い会話は非表示になります';

  @override
  String get durationThreshold => '時間のしきい値';

  @override
  String get durationThresholdDesc => 'これより短い会話を非表示にします';

  @override
  String minLabel(int count) {
    return '$count分';
  }

  @override
  String get customVocabularyTitle => 'カスタム語彙';

  @override
  String get addWords => '単語を追加';

  @override
  String get addWordsDesc => '名前、用語、珍しい単語';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => '接続';

  @override
  String get comingSoon => '近日公開';

  @override
  String get chatToolsFooter => 'アプリを接続して、チャットでデータや指標を表示できます。';

  @override
  String get completeAuthInBrowser => 'ブラウザで認証を完了してください。完了したらアプリに戻ってください。';

  @override
  String failedToStartAuth(String appName) {
    return '$appNameの認証開始に失敗しました';
  }

  @override
  String disconnectAppTitle(String appName) {
    return '$appNameを切断しますか？';
  }

  @override
  String disconnectAppMessage(String appName) {
    return '$appNameとの接続を解除してもよろしいですか？いつでも再接続できます。';
  }

  @override
  String disconnectedFrom(String appName) {
    return '$appNameから切断しました';
  }

  @override
  String get failedToDisconnect => '切断に失敗しました';

  @override
  String connectTo(String appName) {
    return '$appNameに接続';
  }

  @override
  String authAccessMessage(String appName) {
    return 'Omiが$appNameのデータにアクセスすることを許可する必要があります。ブラウザで認証が開きます。';
  }

  @override
  String get continueAction => '続行';

  @override
  String get languageTitle => '言語';

  @override
  String get primaryLanguage => '主要言語';

  @override
  String get automaticTranslation => '自動翻訳';

  @override
  String get detectLanguages => '10以上の言語を検出';

  @override
  String get authorizeSavingRecordings => '録音の保存を許可';

  @override
  String get thanksForAuthorizing => '許可いただきありがとうございます！';

  @override
  String get needYourPermission => '許可が必要です';

  @override
  String get alreadyGavePermission => '録音を保存する許可をすでにいただいています。その理由を再確認してください：';

  @override
  String get wouldLikePermission => '音声録音を保存する許可をお願いします。理由は以下の通りです：';

  @override
  String get improveSpeechProfile => '音声プロファイルの改善';

  @override
  String get improveSpeechProfileDesc => '録音を使用して、あなたの個人的な音声プロファイルをさらに訓練・強化します。';

  @override
  String get trainFamilyProfiles => '家族や友人のプロファイルを訓練';

  @override
  String get trainFamilyProfilesDesc => '録音は、家族や友人を認識し、プロファイルを作成するのに役立ちます。';

  @override
  String get enhanceTranscriptAccuracy => '文字起こし精度の向上';

  @override
  String get enhanceTranscriptAccuracyDesc => 'モデルが改善されるにつれて、録音の文字起こし結果がより良くなります。';

  @override
  String get legalNotice => '法的通知：音声データの録音と保存の合法性は、お住まいの場所やこの機能の使用方法によって異なる場合があります。現地の法律や規制を遵守することはあなたの責任です。';

  @override
  String get alreadyAuthorized => '許可済み';

  @override
  String get authorize => '許可する';

  @override
  String get revokeAuthorization => '許可を取り消す';

  @override
  String get authorizationSuccessful => '許可が完了しました！';

  @override
  String get failedToAuthorize => '許可に失敗しました。もう一度お試しください。';

  @override
  String get authorizationRevoked => '許可が取り消されました。';

  @override
  String get recordingsDeleted => '録音が削除されました。';

  @override
  String get failedToRevoke => '許可の取り消しに失敗しました。もう一度お試しください。';

  @override
  String get permissionRevokedTitle => '許可が取り消されました';

  @override
  String get permissionRevokedMessage => '既存の録音もすべて削除しますか？';

  @override
  String get yes => 'はい';

  @override
  String get editName => '名前を編集';

  @override
  String get howShouldOmiCallYou => 'Omiはあなたをどう呼べばいいですか？';

  @override
  String get enterYourName => 'お名前を入力';

  @override
  String get nameCannotBeEmpty => '名前を空にすることはできません';

  @override
  String get nameUpdatedSuccessfully => '名前が正常に更新されました！';

  @override
  String get calendarSettings => 'カレンダー設定';

  @override
  String get calendarProviders => 'カレンダープロバイダー';

  @override
  String get macOsCalendar => 'macOSカレンダー';

  @override
  String get connectMacOsCalendar => 'ローカルのmacOSカレンダーに接続';

  @override
  String get googleCalendar => 'Googleカレンダー';

  @override
  String get syncGoogleAccount => 'Googleアカウントと同期';

  @override
  String get showMeetingsMenuBar => 'メニューバーに今後のミーティングを表示';

  @override
  String get showMeetingsMenuBarDesc => '次のミーティングと開始までの時間をmacOSメニューバーに表示します';

  @override
  String get showEventsNoParticipants => '参加者のないイベントを表示';

  @override
  String get showEventsNoParticipantsDesc => '有効にすると、Coming Upは参加者やビデオリンクのないイベントを表示します。';

  @override
  String get yourMeetings => 'あなたのミーティング';

  @override
  String get refresh => '更新';

  @override
  String get noUpcomingMeetings => '今後の予定はありません';

  @override
  String get checkingNextDays => '次の30日間を確認中';

  @override
  String get tomorrow => '明日';

  @override
  String get googleCalendarComingSoon => 'Googleカレンダー連携は近日公開予定です！';

  @override
  String connectedAsUser(String userId) {
    return 'ユーザーとして接続: $userId';
  }

  @override
  String get defaultWorkspace => 'デフォルトのワークスペース';

  @override
  String get tasksCreatedInWorkspace => 'タスクはこのワークスペースに作成されます';

  @override
  String get defaultProjectOptional => 'デフォルトプロジェクト（任意）';

  @override
  String get leaveUnselectedTasks => 'プロジェクトなしでタスクを作成するには、選択を解除したままにしてください';

  @override
  String get noProjectsInWorkspace => 'このワークスペースにはプロジェクトがありません';

  @override
  String get conversationTimeoutDesc => '会話を自動終了するまでの無音時間を選択してください：';

  @override
  String get timeout2Minutes => '2分';

  @override
  String get timeout2MinutesDesc => '2分の無音で会話を終了';

  @override
  String get timeout5Minutes => '5分';

  @override
  String get timeout5MinutesDesc => '5分の無音で会話を終了';

  @override
  String get timeout10Minutes => '10分';

  @override
  String get timeout10MinutesDesc => '10分の無音で会話を終了';

  @override
  String get timeout30Minutes => '30分';

  @override
  String get timeout30MinutesDesc => '30分の無音で会話を終了';

  @override
  String get timeout4Hours => '4時間';

  @override
  String get timeout4HoursDesc => '4時間の無音で会話を終了';

  @override
  String get conversationEndAfterHours => '4時間の無音後に会話が終了します';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return '$minutes分の無音後に会話が終了します';
  }

  @override
  String get tellUsPrimaryLanguage => '主要言語を教えてください';

  @override
  String get languageForTranscription => 'より正確な文字起こしとパーソナライズされた体験のために言語を設定してください。';

  @override
  String get singleLanguageModeInfo => '単一言語モードが有効です。より高い精度のため翻訳は無効になっています。';

  @override
  String get searchLanguageHint => '言語名またはコードで検索';

  @override
  String get noLanguagesFound => '言語が見つかりません';

  @override
  String get skip => 'スキップ';

  @override
  String languageSetTo(String language) {
    return '言語を$languageに設定しました';
  }

  @override
  String get failedToSetLanguage => '言語の設定に失敗しました';

  @override
  String appSettings(String appName) {
    return '$appName設定';
  }

  @override
  String disconnectFromApp(String appName) {
    return '$appNameから切断しますか？';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return '$appNameの認証が削除されます。再利用するには再接続が必要です。';
  }

  @override
  String connectedToApp(String appName) {
    return '$appNameに接続済み';
  }

  @override
  String get account => 'アカウント';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'アクションアイテムは$appNameアカウントに同期されます';
  }

  @override
  String get defaultSpace => 'デフォルトスペース';

  @override
  String get selectSpaceInWorkspace => 'ワークスペース内のスペースを選択';

  @override
  String get noSpacesInWorkspace => 'このワークスペースにスペースが見つかりません';

  @override
  String get defaultList => 'デフォルトリスト';

  @override
  String get tasksAddedToList => 'タスクはこのリストに追加されます';

  @override
  String get noListsInSpace => 'このスペースにリストが見つかりません';

  @override
  String failedToLoadRepos(String error) {
    return 'リポジトリの読み込みに失敗しました: $error';
  }

  @override
  String get defaultRepoSaved => 'デフォルトリポジトリを保存しました';

  @override
  String get failedToSaveDefaultRepo => 'デフォルトリポジトリの保存に失敗しました';

  @override
  String get defaultRepository => 'デフォルトリポジトリ';

  @override
  String get selectDefaultRepoDesc => 'イシュー作成用のデフォルトリポジトリを選択してください。イシュー作成時に別のリポジトリを指定することもできます。';

  @override
  String get noReposFound => 'リポジトリが見つかりません';

  @override
  String get private => '非公開';

  @override
  String updatedDate(String date) {
    return '$dateに更新';
  }

  @override
  String get yesterday => '昨日';

  @override
  String daysAgo(int count) {
    return '$count日前';
  }

  @override
  String get oneWeekAgo => '1週間前';

  @override
  String weeksAgo(int count) {
    return '$count週間前';
  }

  @override
  String get oneMonthAgo => '1ヶ月前';

  @override
  String monthsAgo(int count) {
    return '$countヶ月前';
  }

  @override
  String get issuesCreatedInRepo => 'イシューはデフォルトリポジトリに作成されます';

  @override
  String get taskIntegrations => 'タスク連携';

  @override
  String get configureSettings => '設定を構成';

  @override
  String get completeAuthBrowser => 'ブラウザで認証を完了してください。完了したらアプリに戻ってください。';

  @override
  String failedToStartAppAuth(String appName) {
    return '$appNameの認証開始に失敗しました';
  }

  @override
  String connectToAppTitle(String appName) {
    return '$appNameに接続';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Omiが$appNameアカウントでタスクを作成することを許可する必要があります。ブラウザで認証が開きます。';
  }

  @override
  String get continueButton => '続ける';

  @override
  String appIntegration(String appName) {
    return '$appName連携';
  }

  @override
  String integrationComingSoon(String appName) {
    return '$appNameとの連携は近日公開予定です！より多くのタスク管理オプションを提供するため取り組んでいます。';
  }

  @override
  String get gotIt => '了解';

  @override
  String get tasksExportedOneApp => 'タスクは一度に1つのアプリにのみエクスポートできます。';

  @override
  String get completeYourUpgrade => 'アップグレードを完了';

  @override
  String get importConfiguration => '設定をインポート';

  @override
  String get exportConfiguration => '設定をエクスポート';

  @override
  String get bringYourOwn => '自分で用意';

  @override
  String get payYourSttProvider => 'omiを無料で使用。STTプロバイダーに直接支払います。';

  @override
  String get freeMinutesMonth => '月1,200分無料。無制限は';

  @override
  String get omiUnlimited => 'Omi Unlimited';

  @override
  String get hostRequired => 'ホストが必要です';

  @override
  String get validPortRequired => '有効なポートが必要です';

  @override
  String get validWebsocketUrlRequired => '有効なWebSocket URL（wss://）が必要です';

  @override
  String get apiUrlRequired => 'API URLが必要です';

  @override
  String get apiKeyRequired => 'APIキーが必要です';

  @override
  String get invalidJsonConfig => '無効なJSON設定';

  @override
  String errorSaving(String error) {
    return '保存エラー: $error';
  }

  @override
  String get configCopiedToClipboard => '設定をクリップボードにコピーしました';

  @override
  String get pasteJsonConfig => 'JSON設定を以下に貼り付けてください:';

  @override
  String get addApiKeyAfterImport => 'インポート後にAPIキーを追加する必要があります';

  @override
  String get paste => '貼り付け';

  @override
  String get import => 'インポート';

  @override
  String get invalidProviderInConfig => '設定内の無効なプロバイダー';

  @override
  String importedConfig(String providerName) {
    return '$providerName設定をインポートしました';
  }

  @override
  String invalidJson(String error) {
    return '無効なJSON: $error';
  }

  @override
  String get provider => 'プロバイダー';

  @override
  String get live => 'ライブ';

  @override
  String get onDevice => 'オンデバイス';

  @override
  String get apiUrl => 'API URL';

  @override
  String get enterSttHttpEndpoint => 'STT HTTPエンドポイントを入力';

  @override
  String get websocketUrl => 'WebSocket URL';

  @override
  String get enterLiveSttWebsocket => 'ライブSTT WebSocketエンドポイントを入力';

  @override
  String get apiKey => 'APIキー';

  @override
  String get enterApiKey => 'APIキーを入力';

  @override
  String get storedLocallyNeverShared => 'ローカルに保存され、共有されません';

  @override
  String get host => 'ホスト';

  @override
  String get port => 'ポート';

  @override
  String get advanced => '詳細設定';

  @override
  String get configuration => '設定';

  @override
  String get requestConfiguration => 'リクエスト設定';

  @override
  String get responseSchema => 'レスポンススキーマ';

  @override
  String get modified => '変更済み';

  @override
  String get resetRequestConfig => 'リクエスト設定をデフォルトにリセット';

  @override
  String get logs => 'ログ';

  @override
  String get logsCopied => 'ログをコピーしました';

  @override
  String get noLogsYet => 'ログはまだありません。録音を開始するとカスタムSTTアクティビティが表示されます。';

  @override
  String deviceUsesCodec(String device, String reason) {
    return '$deviceは$reasonを使用しています。Omiが使用されます。';
  }

  @override
  String get omiTranscription => 'Omi文字起こし';

  @override
  String get bestInClassTranscription => '設定不要で最高クラスの文字起こし';

  @override
  String get instantSpeakerLabels => '即座に話者ラベル付け';

  @override
  String get languageTranslation => '100以上の言語翻訳';

  @override
  String get optimizedForConversation => '会話に最適化';

  @override
  String get autoLanguageDetection => '自動言語検出';

  @override
  String get highAccuracy => '高精度';

  @override
  String get privacyFirst => 'プライバシー優先';

  @override
  String get saveChanges => '変更を保存';

  @override
  String get resetToDefault => 'デフォルトにリセット';

  @override
  String get viewTemplate => 'テンプレートを表示';

  @override
  String get trySomethingLike => '例えば...';

  @override
  String get tryIt => '試す';

  @override
  String get creatingPlan => 'プランを作成中';

  @override
  String get developingLogic => 'ロジックを開発中';

  @override
  String get designingApp => 'アプリをデザイン中';

  @override
  String get generatingIconStep => 'アイコンを生成中';

  @override
  String get finalTouches => '最終調整';

  @override
  String get processing => '処理中...';

  @override
  String get features => '機能';

  @override
  String get creatingYourApp => 'アプリを作成中...';

  @override
  String get generatingIcon => 'アイコンを生成中...';

  @override
  String get whatShouldWeMake => '何を作りましょうか？';

  @override
  String get appName => 'アプリ名';

  @override
  String get description => '説明';

  @override
  String get publicLabel => '公開';

  @override
  String get privateLabel => '非公開';

  @override
  String get free => '無料';

  @override
  String get perMonth => '/月';

  @override
  String get tailoredConversationSummaries => 'カスタマイズされた会話サマリー';

  @override
  String get customChatbotPersonality => 'カスタムチャットボットパーソナリティ';

  @override
  String get makePublic => '公開する';

  @override
  String get anyoneCanDiscover => '誰でもアプリを発見できます';

  @override
  String get onlyYouCanUse => '自分だけがこのアプリを使用できます';

  @override
  String get paidApp => '有料アプリ';

  @override
  String get usersPayToUse => 'ユーザーがアプリを使用するために支払います';

  @override
  String get freeForEveryone => '全員無料';

  @override
  String get perMonthLabel => '/月';

  @override
  String get creating => '作成中...';

  @override
  String get createApp => 'アプリを作成';

  @override
  String get searchingForDevices => 'デバイスを検索中...';

  @override
  String devicesFoundNearby(int count) {
    return '$count台のデバイスが近くに見つかりました';
  }

  @override
  String get pairingSuccessful => 'ペアリング成功';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Apple Watchへの接続エラー: $error';
  }

  @override
  String get dontShowAgain => '再度表示しない';

  @override
  String get iUnderstand => '理解しました';

  @override
  String get enableBluetooth => 'Bluetoothを有効にする';

  @override
  String get bluetoothNeeded => 'Omiはウェアラブルに接続するためにBluetoothが必要です。Bluetoothを有効にして再試行してください。';

  @override
  String get contactSupport => 'サポートに連絡しますか？';

  @override
  String get connectLater => '後で接続';

  @override
  String get grantPermissions => '権限を付与';

  @override
  String get backgroundActivity => 'バックグラウンド活動';

  @override
  String get backgroundActivityDesc => 'より安定した動作のためにOmiをバックグラウンドで実行させる';

  @override
  String get locationAccess => '位置情報アクセス';

  @override
  String get locationAccessDesc => '完全な体験のためにバックグラウンド位置情報を有効にする';

  @override
  String get notifications => '通知';

  @override
  String get notificationsDesc => '最新情報を受け取るために通知を有効にする';

  @override
  String get locationServiceDisabled => '位置情報サービスが無効';

  @override
  String get locationServiceDisabledDesc => '位置情報サービスが無効です。設定 > プライバシーとセキュリティ > 位置情報サービスに移動して有効にしてください';

  @override
  String get backgroundLocationDenied => 'バックグラウンド位置情報アクセスが拒否されました';

  @override
  String get backgroundLocationDeniedDesc => 'デバイスの設定に移動して、位置情報の権限を「常に許可」に設定してください';

  @override
  String get lovingOmi => 'Omiを楽しんでいますか？';

  @override
  String get leaveReviewIos => 'App Storeでレビューを残して、より多くの人に届けるお手伝いをしてください。皆様のフィードバックは私たちにとって非常に大切です！';

  @override
  String get leaveReviewAndroid => 'Google Playストアでレビューを残して、より多くの人に届けるお手伝いをしてください。皆様のフィードバックは私たちにとって非常に大切です！';

  @override
  String get rateOnAppStore => 'App Storeで評価';

  @override
  String get rateOnGooglePlay => 'Google Playで評価';

  @override
  String get maybeLater => '後で';

  @override
  String get speechProfileIntro => 'Omiはあなたの目標と声を学ぶ必要があります。後で変更できます。';

  @override
  String get getStarted => '始める';

  @override
  String get allDone => '完了しました！';

  @override
  String get keepGoing => 'その調子です、頑張ってください';

  @override
  String get skipThisQuestion => 'この質問をスキップ';

  @override
  String get skipForNow => '今はスキップ';

  @override
  String get connectionError => '接続エラー';

  @override
  String get connectionErrorDesc => 'サーバーへの接続に失敗しました。インターネット接続を確認してもう一度お試しください。';

  @override
  String get invalidRecordingMultipleSpeakers => '無効な録音が検出されました';

  @override
  String get multipleSpeakersDesc => '録音に複数の話者がいるようです。静かな場所にいることを確認して、もう一度お試しください。';

  @override
  String get tooShortDesc => '音声が十分に検出されませんでした。もっと話してからもう一度お試しください。';

  @override
  String get invalidRecordingDesc => '5秒以上、90秒以内で話してください。';

  @override
  String get areYouThere => 'いらっしゃいますか？';

  @override
  String get noSpeechDesc => '音声が検出されませんでした。10秒以上、3分以内で話してください。';

  @override
  String get connectionLost => '接続が切断されました';

  @override
  String get connectionLostDesc => '接続が中断されました。インターネット接続を確認してもう一度お試しください。';

  @override
  String get tryAgain => '再試行';

  @override
  String get connectOmiOmiGlass => 'Omi / OmiGlassを接続';

  @override
  String get continueWithoutDevice => 'デバイスなしで続ける';

  @override
  String get permissionsRequired => '権限が必要です';

  @override
  String get permissionsRequiredDesc => 'このアプリが正しく機能するにはBluetoothと位置情報の権限が必要です。設定で有効にしてください。';

  @override
  String get openSettings => '設定を開く';

  @override
  String get wantDifferentName => '別の名前を使いますか？';

  @override
  String get whatsYourName => 'お名前は何ですか？';

  @override
  String get speakTranscribeSummarize => '話す。文字起こし。要約。';

  @override
  String get signInWithApple => 'Appleでサインイン';

  @override
  String get signInWithGoogle => 'Googleでサインイン';

  @override
  String get byContinuingAgree => '続行することで、';

  @override
  String get termsOfUse => '利用規約';

  @override
  String get omiYourAiCompanion => 'Omi – あなたのAIコンパニオン';

  @override
  String get captureEveryMoment => 'すべての瞬間を記録。AI搭載のサマリーで、もうメモを取る必要はありません。';

  @override
  String get appleWatchSetup => 'Apple Watchのセットアップ';

  @override
  String get permissionRequestedExclaim => '許可をリクエストしました！';

  @override
  String get microphonePermission => 'マイクの許可';

  @override
  String get permissionGrantedNow => '許可されました！次は：\n\nApple WatchでOmiアプリを開き、下の「続ける」をタップしてください';

  @override
  String get needMicrophonePermission => 'マイクの許可が必要です。\n\n1. 「許可する」をタップ\n2. iPhoneで許可を選択\n3. Watchアプリが閉じます\n4. 再度開いて「続ける」をタップ';

  @override
  String get grantPermissionButton => '許可する';

  @override
  String get needHelp => 'ヘルプ';

  @override
  String get troubleshootingSteps => 'トラブルシューティング：\n\n1. WatchにOmiがインストールされているか確認\n2. WatchでOmiアプリを開く\n3. 許可のポップアップを探す\n4. 「許可」をタップ\n5. Watchアプリが閉じたら再度開く\n6. iPhoneに戻り「続ける」をタップ';

  @override
  String get recordingStartedSuccessfully => '録音が正常に開始されました！';

  @override
  String get permissionNotGrantedYet => '許可がまだ付与されていません。マイクアクセスを許可し、Watchでアプリを再度開いたことを確認してください。';

  @override
  String errorRequestingPermission(String error) {
    return '許可のリクエスト中にエラーが発生しました：$error';
  }

  @override
  String errorStartingRecording(String error) {
    return '録音の開始中にエラーが発生しました：$error';
  }

  @override
  String get selectPrimaryLanguage => '主要言語を選択';

  @override
  String get languageBenefits => '言語を設定すると、より正確な文字起こしとパーソナライズされた体験が得られます';

  @override
  String get whatsYourPrimaryLanguage => '主要言語は何ですか？';

  @override
  String get selectYourLanguage => '言語を選択';

  @override
  String get personalGrowthJourney => 'あなたのすべての言葉に耳を傾けるAIとの個人的成長の旅。';

  @override
  String get actionItemsTitle => 'To-Doリスト';

  @override
  String get actionItemsDescription => 'タップして編集 • 長押しで選択 • スワイプで操作';

  @override
  String get tabToDo => '未完了';

  @override
  String get tabDone => '完了';

  @override
  String get tabOld => '過去';

  @override
  String get emptyTodoMessage => '🎉 すべて完了！\n保留中のアクションアイテムはありません';

  @override
  String get emptyDoneMessage => '完了したアイテムはまだありません';

  @override
  String get emptyOldMessage => '✅ 過去のタスクはありません';

  @override
  String get noItems => 'アイテムなし';

  @override
  String get actionItemMarkedIncomplete => 'アクションアイテムを未完了にしました';

  @override
  String get actionItemCompleted => 'アクションアイテムを完了しました';

  @override
  String get deleteActionItemTitle => 'アクションアイテムを削除';

  @override
  String get deleteActionItemMessage => 'このアクションアイテムを削除してもよろしいですか？';

  @override
  String get deleteSelectedItemsTitle => '選択したアイテムを削除';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return '選択した $count 件のアクションアイテムを削除してもよろしいですか？';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'アクションアイテム「$description」を削除しました';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count 件のアクションアイテムを削除しました';
  }

  @override
  String get failedToDeleteItem => 'アクションアイテムの削除に失敗しました';

  @override
  String get failedToDeleteItems => 'アイテムの削除に失敗しました';

  @override
  String get failedToDeleteSomeItems => '一部のアイテムの削除に失敗しました';

  @override
  String get welcomeActionItemsTitle => 'アクションアイテムの準備完了';

  @override
  String get welcomeActionItemsDescription => 'AIが会話からタスクやTo-Doを自動的に抽出します。作成されるとここに表示されます。';

  @override
  String get autoExtractionFeature => '会話から自動抽出';

  @override
  String get editSwipeFeature => 'タップして編集、スワイプで完了または削除';

  @override
  String itemsSelected(int count) {
    return '$count 件選択中';
  }

  @override
  String get selectAll => 'すべて選択';

  @override
  String get deleteSelected => '選択項目を削除';

  @override
  String get searchMemories => '思い出を検索...';

  @override
  String get memoryDeleted => 'メモリを削除しました';

  @override
  String get undo => '元に戻す';

  @override
  String get noMemoriesYet => '🧠 まだ思い出がありません';

  @override
  String get noAutoMemories => '自動メモリはまだありません';

  @override
  String get noManualMemories => '手動メモリはまだありません';

  @override
  String get noMemoriesInCategories => 'このカテゴリのメモリはありません';

  @override
  String get noMemoriesFound => '🔍 思い出が見つかりませんでした';

  @override
  String get addFirstMemory => '最初のメモリを追加';

  @override
  String get clearMemoryTitle => 'Omiのメモリを消去';

  @override
  String get clearMemoryMessage => 'Omiのメモリを消去してもよろしいですか？この操作は取り消せません。';

  @override
  String get clearMemoryButton => 'メモリをクリア';

  @override
  String get memoryClearedSuccess => 'Omiのあなたに関するメモリが消去されました';

  @override
  String get noMemoriesToDelete => '削除するメモリがありません';

  @override
  String get createMemoryTooltip => '新しいメモリを作成';

  @override
  String get createActionItemTooltip => '新しいアクションアイテムを作成';

  @override
  String get memoryManagement => 'メモリ管理';

  @override
  String get filterMemories => 'メモリをフィルタリング';

  @override
  String totalMemoriesCount(int count) {
    return '合計 $count 件のメモリがあります';
  }

  @override
  String get publicMemories => '公開メモリ';

  @override
  String get privateMemories => '非公開メモリ';

  @override
  String get makeAllPrivate => 'すべてのメモリを非公開にする';

  @override
  String get makeAllPublic => 'すべてのメモリを公開する';

  @override
  String get deleteAllMemories => 'すべてのメモリを削除';

  @override
  String get allMemoriesPrivateResult => 'すべてのメモリが非公開になりました';

  @override
  String get allMemoriesPublicResult => 'すべてのメモリが公開されました';

  @override
  String get newMemory => '✨ 新しいメモリ';

  @override
  String get editMemory => '✏️ メモリを編集';

  @override
  String get memoryContentHint => 'アイスクリームが好き...';

  @override
  String get failedToSaveMemory => '保存に失敗しました。接続を確認してください。';

  @override
  String get saveMemory => 'メモリを保存';

  @override
  String get retry => '再試行';

  @override
  String get createActionItem => 'アクションアイテムを作成';

  @override
  String get editActionItem => 'アクションアイテムを編集';

  @override
  String get actionItemDescriptionHint => '何をする必要がありますか？';

  @override
  String get actionItemDescriptionEmpty => 'アクションアイテムの説明は空にできません。';

  @override
  String get actionItemUpdated => 'アクションアイテムを更新しました';

  @override
  String get failedToUpdateActionItem => 'アクションアイテムの更新に失敗しました';

  @override
  String get actionItemCreated => 'アクションアイテムを作成しました';

  @override
  String get failedToCreateActionItem => 'アクションアイテムの作成に失敗しました';

  @override
  String get dueDate => '期限';

  @override
  String get time => '時間';

  @override
  String get addDueDate => '期限を追加';

  @override
  String get pressDoneToSave => '完了を押して保存';

  @override
  String get pressDoneToCreate => '完了を押して作成';

  @override
  String get filterAll => 'すべて';

  @override
  String get filterSystem => 'あなたについて';

  @override
  String get filterInteresting => 'インサイト';

  @override
  String get filterManual => '手動';

  @override
  String get completed => '完了';

  @override
  String get markComplete => '完了としてマーク';

  @override
  String get actionItemDeleted => 'アクションアイテムが削除されました';

  @override
  String get failedToDeleteActionItem => 'アクションアイテムの削除に失敗しました';

  @override
  String get deleteActionItemConfirmTitle => 'アクションアイテムの削除';

  @override
  String get deleteActionItemConfirmMessage => 'このアクションアイテムを削除してもよろしいですか？';

  @override
  String get appLanguage => 'アプリ言語';

  @override
  String get appInterfaceSectionTitle => 'アプリインターフェース';

  @override
  String get speechTranscriptionSectionTitle => '音声と文字起こし';

  @override
  String get languageSettingsHelperText => 'アプリ言語はメニューとボタンを変更します。音声言語は録音の文字起こし方法に影響します。';

  @override
  String get translationNotice => '翻訳に関するお知らせ';

  @override
  String get translationNoticeMessage => 'Omiは会話をあなたの主要言語に翻訳します。設定→プロフィールでいつでも更新できます。';

  @override
  String get pleaseCheckInternetConnection => 'インターネット接続を確認して、もう一度お試しください';

  @override
  String get pleaseSelectReason => '理由を選択してください';

  @override
  String get tellUsMoreWhatWentWrong => '何が問題だったか詳しく教えてください...';

  @override
  String get selectText => 'テキストを選択';

  @override
  String maximumGoalsAllowed(int count) {
    return '最大$count個の目標が許可されています';
  }

  @override
  String get conversationCannotBeMerged => 'この会話はマージできません（ロックされているか、すでにマージ中です）';

  @override
  String get pleaseEnterFolderName => 'フォルダ名を入力してください';

  @override
  String get failedToCreateFolder => 'フォルダの作成に失敗しました';

  @override
  String get failedToUpdateFolder => 'フォルダの更新に失敗しました';

  @override
  String get folderName => 'フォルダ名';

  @override
  String get descriptionOptional => '説明（任意）';

  @override
  String get failedToDeleteFolder => 'フォルダの削除に失敗しました';

  @override
  String get editFolder => 'フォルダを編集';

  @override
  String get deleteFolder => 'フォルダを削除';

  @override
  String get transcriptCopiedToClipboard => 'トランスクリプトをクリップボードにコピーしました';

  @override
  String get summaryCopiedToClipboard => '概要をクリップボードにコピーしました';

  @override
  String get conversationUrlCouldNotBeShared => '会話URLを共有できませんでした。';

  @override
  String get urlCopiedToClipboard => 'URLをクリップボードにコピーしました';

  @override
  String get exportTranscript => 'トランスクリプトをエクスポート';

  @override
  String get exportSummary => '概要をエクスポート';

  @override
  String get exportButton => 'エクスポート';

  @override
  String get actionItemsCopiedToClipboard => 'アクション項目をクリップボードにコピーしました';

  @override
  String get summarize => '要約';

  @override
  String get generateSummary => 'サマリーを生成';

  @override
  String get conversationNotFoundOrDeleted => '会話が見つからないか、削除されました';

  @override
  String get deleteMemory => 'メモリを削除';

  @override
  String get thisActionCannotBeUndone => 'この操作は元に戻せません。';

  @override
  String memoriesCount(int count) {
    return '$count個の思い出';
  }

  @override
  String get noMemoriesInCategory => 'このカテゴリにはまだメモリがありません';

  @override
  String get addYourFirstMemory => '最初の思い出を追加';

  @override
  String get firmwareDisconnectUsb => 'USBを切断';

  @override
  String get firmwareUsbWarning => '更新中のUSB接続はデバイスを損傷する可能性があります。';

  @override
  String get firmwareBatteryAbove15 => 'バッテリー15%以上';

  @override
  String get firmwareEnsureBattery => 'デバイスのバッテリーが15%あることを確認してください。';

  @override
  String get firmwareStableConnection => '安定した接続';

  @override
  String get firmwareConnectWifi => 'WiFiまたはモバイルデータに接続してください。';

  @override
  String failedToStartUpdate(String error) {
    return '更新の開始に失敗しました: $error';
  }

  @override
  String get beforeUpdateMakeSure => '更新前に確認してください:';

  @override
  String get confirmed => '確認済み！';

  @override
  String get release => '離す';

  @override
  String get slideToUpdate => 'スライドして更新';

  @override
  String copiedToClipboard(String title) {
    return '$titleをクリップボードにコピーしました';
  }

  @override
  String get batteryLevel => 'バッテリー残量';

  @override
  String get productUpdate => '製品アップデート';

  @override
  String get offline => 'オフライン';

  @override
  String get available => '利用可能';

  @override
  String get unpairDeviceDialogTitle => 'デバイスのペアリング解除';

  @override
  String get unpairDeviceDialogMessage => 'これにより、デバイスのペアリングが解除され、別の電話に接続できるようになります。設定 > Bluetoothに移動し、デバイスを削除してプロセスを完了する必要があります。';

  @override
  String get unpair => 'ペアリング解除';

  @override
  String get unpairAndForgetDevice => 'ペアリング解除してデバイスを削除';

  @override
  String get unknownDevice => '不明';

  @override
  String get unknown => '不明';

  @override
  String get productName => '製品名';

  @override
  String get serialNumber => 'シリアル番号';

  @override
  String get connected => '接続済み';

  @override
  String get privacyPolicyTitle => 'プライバシーポリシー';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$labelをコピーしました';
  }

  @override
  String get noApiKeysYet => 'まだAPIキーがありません。アプリと統合するために作成してください。';

  @override
  String get createKeyToGetStarted => '開始するにはキーを作成してください';

  @override
  String get persona => 'ペルソナ';

  @override
  String get configureYourAiPersona => 'AIペルソナを設定する';

  @override
  String get configureSttProvider => 'STTプロバイダーを設定';

  @override
  String get setWhenConversationsAutoEnd => '会話が自動終了するタイミングを設定';

  @override
  String get importDataFromOtherSources => '他のソースからデータをインポート';

  @override
  String get debugAndDiagnostics => 'デバッグと診断';

  @override
  String get autoDeletesAfter3Days => '3日後に自動削除';

  @override
  String get helpsDiagnoseIssues => '問題の診断に役立ちます';

  @override
  String get exportStartedMessage => 'エクスポートを開始しました。数秒かかる場合があります...';

  @override
  String get exportConversationsToJson => '会話をJSONファイルにエクスポート';

  @override
  String get knowledgeGraphDeletedSuccess => 'ナレッジグラフが正常に削除されました';

  @override
  String failedToDeleteGraph(String error) {
    return 'グラフの削除に失敗しました：$error';
  }

  @override
  String get clearAllNodesAndConnections => 'すべてのノードと接続をクリア';

  @override
  String get addToClaudeDesktopConfig => 'claude_desktop_config.jsonに追加';

  @override
  String get connectAiAssistantsToData => 'AIアシスタントをデータに接続';

  @override
  String get useYourMcpApiKey => 'MCP APIキーを使用';

  @override
  String get realTimeTranscript => 'リアルタイム転写';

  @override
  String get experimental => '実験的';

  @override
  String get transcriptionDiagnostics => '転写診断';

  @override
  String get detailedDiagnosticMessages => '詳細な診断メッセージ';

  @override
  String get autoCreateSpeakers => 'スピーカーを自動作成';

  @override
  String get autoCreateWhenNameDetected => '名前が検出されたら自動作成';

  @override
  String get followUpQuestions => 'フォローアップの質問';

  @override
  String get suggestQuestionsAfterConversations => '会話後に質問を提案';

  @override
  String get goalTracker => '目標トラッカー';

  @override
  String get trackPersonalGoalsOnHomepage => 'ホームページで個人目標を追跡';

  @override
  String get dailyReflection => 'デイリー振り返り';

  @override
  String get get9PmReminderToReflect => '午後9時に一日を振り返るリマインダーを受け取る';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'アクションアイテムの説明を空にすることはできません';

  @override
  String get saved => '保存しました';

  @override
  String get overdue => '期限切れ';

  @override
  String get failedToUpdateDueDate => '期限日の更新に失敗しました';

  @override
  String get markIncomplete => '未完了としてマーク';

  @override
  String get editDueDate => '期限日を編集';

  @override
  String get setDueDate => '期限を設定';

  @override
  String get clearDueDate => '期限日をクリア';

  @override
  String get failedToClearDueDate => '期限日のクリアに失敗しました';

  @override
  String get mondayAbbr => '月';

  @override
  String get tuesdayAbbr => '火';

  @override
  String get wednesdayAbbr => '水';

  @override
  String get thursdayAbbr => '木';

  @override
  String get fridayAbbr => '金';

  @override
  String get saturdayAbbr => '土';

  @override
  String get sundayAbbr => '日';

  @override
  String get howDoesItWork => 'どのように機能しますか？';

  @override
  String get sdCardSyncDescription => 'SDカード同期は、SDカードからアプリに思い出をインポートします';

  @override
  String get checksForAudioFiles => 'SDカード上のオーディオファイルをチェックします';

  @override
  String get omiSyncsAudioFiles => 'Omiはその後、オーディオファイルをサーバーと同期します';

  @override
  String get serverProcessesAudio => 'サーバーがオーディオファイルを処理し、思い出を作成します';

  @override
  String get youreAllSet => '準備完了です！';

  @override
  String get welcomeToOmiDescription => 'Omiへようこそ！あなたのAIコンパニオンは、会話、タスクなどでお手伝いする準備ができています。';

  @override
  String get startUsingOmi => 'Omiの使用を開始';

  @override
  String get back => '戻る';

  @override
  String get keyboardShortcuts => 'キーボードショートカット';

  @override
  String get toggleControlBar => 'コントロールバーの切り替え';

  @override
  String get pressKeys => 'キーを押してください...';

  @override
  String get cmdRequired => '⌘ が必要';

  @override
  String get invalidKey => '無効なキー';

  @override
  String get space => 'スペース';

  @override
  String get search => '検索';

  @override
  String get searchPlaceholder => '検索...';

  @override
  String get untitledConversation => '無題の会話';

  @override
  String countRemaining(String count) {
    return '$count 残り';
  }

  @override
  String get addGoal => '目標を追加';

  @override
  String get editGoal => '目標を編集';

  @override
  String get icon => 'アイコン';

  @override
  String get goalTitle => '目標タイトル';

  @override
  String get current => '現在';

  @override
  String get target => '目標';

  @override
  String get saveGoal => '保存';

  @override
  String get goals => '目標';

  @override
  String get tapToAddGoal => 'タップして目標を追加';

  @override
  String welcomeBack(String name) {
    return 'おかえりなさい、$name';
  }

  @override
  String get yourConversations => '会話履歴';

  @override
  String get reviewAndManageConversations => '記録された会話を確認および管理します';

  @override
  String get startCapturingConversations => 'Omiデバイスで会話のキャプチャを開始して、ここに表示します。';

  @override
  String get useMobileAppToCapture => 'モバイルアプリを使用してオーディオをキャプチャします';

  @override
  String get conversationsProcessedAutomatically => '会話は自動的に処理されます';

  @override
  String get getInsightsInstantly => 'すぐに洞察と要約を取得できます';

  @override
  String get showAll => 'すべて表示 →';

  @override
  String get noTasksForToday => '今日のタスクはありません。\\nOmiに他のタスクを尋ねるか、手動で作成してください。';

  @override
  String get dailyScore => 'デイリースコア';

  @override
  String get dailyScoreDescription => '実行に集中するための\nスコアです。';

  @override
  String get searchResults => '検索結果';

  @override
  String get actionItems => 'アクションアイテム';

  @override
  String get tasksToday => '今日';

  @override
  String get tasksTomorrow => '明日';

  @override
  String get tasksNoDeadline => '期限なし';

  @override
  String get tasksLater => '後で';

  @override
  String get loadingTasks => 'タスクを読み込んでいます...';

  @override
  String get tasks => 'タスク';

  @override
  String get swipeTasksToIndent => 'タスクをスワイプしてインデント、カテゴリ間でドラッグ';

  @override
  String get create => '作成';

  @override
  String get noTasksYet => 'まだタスクがありません';

  @override
  String get tasksFromConversationsWillAppear => '会話からのタスクがここに表示されます。\n手動で追加するには、作成をクリックしてください。';

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
  String get timePM => '午後';

  @override
  String get timeAM => '午前';

  @override
  String get actionItemUpdatedSuccessfully => 'アクションアイテムが正常に更新されました';

  @override
  String get actionItemCreatedSuccessfully => 'アクションアイテムが正常に作成されました';

  @override
  String get actionItemDeletedSuccessfully => 'アクションアイテムが正常に削除されました';

  @override
  String get deleteActionItem => 'アクションアイテムを削除';

  @override
  String get deleteActionItemConfirmation => 'このアクションアイテムを削除してもよろしいですか？この操作は元に戻せません。';

  @override
  String get enterActionItemDescription => 'アクションアイテムの説明を入力...';

  @override
  String get markAsCompleted => '完了としてマーク';

  @override
  String get setDueDateAndTime => '期限と時刻を設定';

  @override
  String get reloadingApps => 'アプリを再読み込み中...';

  @override
  String get loadingApps => 'アプリを読み込み中...';

  @override
  String get browseInstallCreateApps => 'アプリを閲覧、インストール、作成';

  @override
  String get all => 'All';

  @override
  String get open => '開く';

  @override
  String get install => 'インストール';

  @override
  String get noAppsAvailable => '利用可能なアプリがありません';

  @override
  String get unableToLoadApps => 'アプリを読み込めません';

  @override
  String get tryAdjustingSearchTermsOrFilters => '検索条件またはフィルターを調整してみてください';

  @override
  String get checkBackLaterForNewApps => '後ほど新しいアプリを確認してください';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'インターネット接続を確認して、もう一度お試しください';

  @override
  String get createNewApp => '新しいアプリを作成';

  @override
  String get buildSubmitCustomOmiApp => 'カスタムOmiアプリを構築して送信する';

  @override
  String get submittingYourApp => 'アプリを送信しています...';

  @override
  String get preparingFormForYou => 'フォームを準備しています...';

  @override
  String get appDetails => 'アプリの詳細';

  @override
  String get paymentDetails => '支払い詳細';

  @override
  String get previewAndScreenshots => 'プレビューとスクリーンショット';

  @override
  String get appCapabilities => 'アプリの機能';

  @override
  String get aiPrompts => 'AIプロンプト';

  @override
  String get chatPrompt => 'チャットプロンプト';

  @override
  String get chatPromptPlaceholder => 'あなたは素晴らしいアプリです。ユーザーのクエリに応答し、良い気分にさせることがあなたの仕事です...';

  @override
  String get conversationPrompt => '会話プロンプト';

  @override
  String get conversationPromptPlaceholder => 'あなたは素晴らしいアプリです。会話のトランスクリプトと要約が提供されます...';

  @override
  String get notificationScopes => '通知スコープ';

  @override
  String get appPrivacyAndTerms => 'アプリのプライバシーと利用規約';

  @override
  String get makeMyAppPublic => 'アプリを公開する';

  @override
  String get submitAppTermsAgreement => 'このアプリを送信することにより、Omi AIの利用規約とプライバシーポリシーに同意します';

  @override
  String get submitApp => 'アプリを送信';

  @override
  String get needHelpGettingStarted => '始めるのに助けが必要ですか？';

  @override
  String get clickHereForAppBuildingGuides => 'アプリ構築ガイドとドキュメントについてはここをクリック';

  @override
  String get submitAppQuestion => 'アプリを送信しますか？';

  @override
  String get submitAppPublicDescription => 'あなたのアプリはレビューされ、公開されます。レビュー中でもすぐに使い始めることができます！';

  @override
  String get submitAppPrivateDescription => 'あなたのアプリはレビューされ、プライベートに利用可能になります。レビュー中でもすぐに使い始めることができます！';

  @override
  String get startEarning => '収益を開始！💰';

  @override
  String get connectStripeOrPayPal => 'StripeまたはPayPalを接続して、アプリの支払いを受け取ります。';

  @override
  String get connectNow => '今すぐ接続';

  @override
  String get installsCount => 'インストール';

  @override
  String get uninstallApp => 'アプリをアンインストール';

  @override
  String get subscribe => 'サブスクライブ';

  @override
  String get dataAccessNotice => 'データアクセス通知';

  @override
  String get dataAccessWarning => 'このアプリはあなたのデータにアクセスします。Omi AIは、このアプリによってデータがどのように使用、変更、または削除されるかについて責任を負いません';

  @override
  String get installApp => 'アプリをインストール';

  @override
  String get betaTesterNotice => 'あなたはこのアプリのベータテスターです。まだ公開されていません。承認されると公開されます。';

  @override
  String get appUnderReviewOwner => 'あなたのアプリは審査中で、あなただけに表示されます。承認されると公開されます。';

  @override
  String get appRejectedNotice => 'あなたのアプリは却下されました。アプリの詳細を更新して、再度審査に提出してください。';

  @override
  String get setupSteps => 'セットアップ手順';

  @override
  String get setupInstructions => 'セットアップ手順';

  @override
  String get integrationInstructions => '統合手順';

  @override
  String get preview => 'プレビュー';

  @override
  String get aboutTheApp => 'アプリについて';

  @override
  String get aboutThePersona => 'ペルソナについて';

  @override
  String get chatPersonality => 'チャットパーソナリティ';

  @override
  String get ratingsAndReviews => '評価とレビュー';

  @override
  String get noRatings => '評価なし';

  @override
  String ratingsCount(String count) {
    return '$count+の評価';
  }

  @override
  String get errorActivatingApp => 'アプリの有効化エラー';

  @override
  String get integrationSetupRequired => 'これが統合アプリの場合は、セットアップが完了していることを確認してください。';

  @override
  String get installed => 'インストール済み';

  @override
  String get appIdLabel => 'アプリID';

  @override
  String get appNameLabel => 'アプリ名';

  @override
  String get appNamePlaceholder => '私の素晴らしいアプリ';

  @override
  String get pleaseEnterAppName => 'アプリ名を入力してください';

  @override
  String get categoryLabel => 'カテゴリ';

  @override
  String get selectCategory => 'カテゴリを選択';

  @override
  String get descriptionLabel => '説明';

  @override
  String get appDescriptionPlaceholder => '私の素晴らしいアプリは、素晴らしいことをする素晴らしいアプリです。これは最高のアプリです！';

  @override
  String get pleaseProvideValidDescription => '有効な説明を入力してください';

  @override
  String get appPricingLabel => 'アプリの価格設定';

  @override
  String get noneSelected => '未選択';

  @override
  String get appIdCopiedToClipboard => 'アプリIDをクリップボードにコピーしました';

  @override
  String get appCategoryModalTitle => 'アプリカテゴリ';

  @override
  String get pricingFree => '無料';

  @override
  String get pricingPaid => '有料';

  @override
  String get loadingCapabilities => '機能を読み込み中...';

  @override
  String get filterInstalled => 'インストール済み';

  @override
  String get filterMyApps => 'マイアプリ';

  @override
  String get clearSelection => '選択をクリア';

  @override
  String get filterCategory => 'カテゴリ';

  @override
  String get rating4PlusStars => '4+つ星';

  @override
  String get rating3PlusStars => '3+つ星';

  @override
  String get rating2PlusStars => '2+つ星';

  @override
  String get rating1PlusStars => '1+つ星';

  @override
  String get filterRating => '評価';

  @override
  String get filterCapabilities => '機能';

  @override
  String get noNotificationScopesAvailable => '通知スコープが利用できません';

  @override
  String get popularApps => '人気アプリ';

  @override
  String get pleaseProvidePrompt => 'プロンプトを入力してください';

  @override
  String chatWithAppName(String appName) {
    return '$appNameとチャット';
  }

  @override
  String get defaultAiAssistant => 'デフォルトのAIアシスタント';

  @override
  String get readyToChat => '✨ チャットの準備完了！';

  @override
  String get connectionNeeded => '🌐 接続が必要です';

  @override
  String get startConversation => '会話を始めて魔法を起こしましょう';

  @override
  String get checkInternetConnection => 'インターネット接続を確認してください';

  @override
  String get wasThisHelpful => 'これは役に立ちましたか？';

  @override
  String get thankYouForFeedback => 'フィードバックありがとうございます！';

  @override
  String get maxFilesUploadError => '一度に4ファイルまでアップロードできます';

  @override
  String get attachedFiles => '📎 添付ファイル';

  @override
  String get takePhoto => '写真を撮る';

  @override
  String get captureWithCamera => 'カメラで撮影';

  @override
  String get selectImages => '画像を選択';

  @override
  String get chooseFromGallery => 'ギャラリーから選択';

  @override
  String get selectFile => 'ファイルを選択';

  @override
  String get chooseAnyFileType => '任意のファイルタイプを選択';

  @override
  String get cannotReportOwnMessages => '自分のメッセージは報告できません';

  @override
  String get messageReportedSuccessfully => '✅ メッセージが正常に報告されました';

  @override
  String get confirmReportMessage => 'このメッセージを報告してもよろしいですか？';

  @override
  String get selectChatAssistant => 'チャットアシスタントを選択';

  @override
  String get enableMoreApps => 'より多くのアプリを有効にする';

  @override
  String get chatCleared => 'チャットをクリアしました';

  @override
  String get clearChatTitle => 'チャットをクリア？';

  @override
  String get confirmClearChat => 'チャットをクリアしてもよろしいですか？この操作は元に戻せません。';

  @override
  String get copy => 'コピー';

  @override
  String get share => '共有';

  @override
  String get report => '報告';

  @override
  String get microphonePermissionRequired => '音声録音にはマイクの許可が必要です。';

  @override
  String get microphonePermissionDenied => 'マイクの許可が拒否されました。システム環境設定 > プライバシーとセキュリティ > マイク で許可を付与してください。';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'マイクの許可確認に失敗しました: $error';
  }

  @override
  String get failedToTranscribeAudio => '音声の文字起こしに失敗しました';

  @override
  String get transcribing => '文字起こし中...';

  @override
  String get transcriptionFailed => '文字起こし失敗';

  @override
  String get discardedConversation => '破棄された会話';

  @override
  String get at => '時刻';

  @override
  String get from => 'から';

  @override
  String get copied => 'コピーしました！';

  @override
  String get copyLink => 'リンクをコピー';

  @override
  String get hideTranscript => '文字起こしを非表示';

  @override
  String get viewTranscript => '文字起こしを表示';

  @override
  String get conversationDetails => '会話の詳細';

  @override
  String get transcript => '文字起こし';

  @override
  String segmentsCount(int count) {
    return '$countセグメント';
  }

  @override
  String get noTranscriptAvailable => '文字起こしがありません';

  @override
  String get noTranscriptMessage => 'この会話には文字起こしがありません。';

  @override
  String get conversationUrlCouldNotBeGenerated => '会話のURLを生成できませんでした。';

  @override
  String get failedToGenerateConversationLink => '会話のリンク生成に失敗しました';

  @override
  String get failedToGenerateShareLink => '共有リンクの生成に失敗しました';

  @override
  String get reloadingConversations => '会話を再読み込み中...';

  @override
  String get user => 'ユーザー';

  @override
  String get starred => 'スター付き';

  @override
  String get date => '日付';

  @override
  String get noResultsFound => '結果が見つかりませんでした';

  @override
  String get tryAdjustingSearchTerms => '検索語を調整してみてください';

  @override
  String get starConversationsToFindQuickly => '会話にスターを付けると、ここですばやく見つけることができます';

  @override
  String noConversationsOnDate(String date) {
    return '$dateの会話はありません';
  }

  @override
  String get trySelectingDifferentDate => '別の日付を選択してみてください';

  @override
  String get conversations => '会話';

  @override
  String get chat => 'チャット';

  @override
  String get actions => 'アクション';

  @override
  String get syncAvailable => '同期が利用可能';

  @override
  String get referAFriend => '友達を紹介';

  @override
  String get help => 'ヘルプ';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'Proにアップグレード';

  @override
  String get getOmiDevice => 'Omiデバイスを入手';

  @override
  String get wearableAiCompanion => 'ウェアラブルAIコンパニオン';

  @override
  String get loadingMemories => '思い出を読み込んでいます...';

  @override
  String get allMemories => 'すべての思い出';

  @override
  String get aboutYou => 'あなたについて';

  @override
  String get manual => '手動';

  @override
  String get loadingYourMemories => '思い出を読み込んでいます...';

  @override
  String get createYourFirstMemory => '最初の思い出を作成して始めましょう';

  @override
  String get tryAdjustingFilter => '検索またはフィルターを調整してみてください';

  @override
  String get whatWouldYouLikeToRemember => '何を覚えておきたいですか？';

  @override
  String get category => 'カテゴリ';

  @override
  String get public => '公開';

  @override
  String get failedToSaveCheckConnection => '保存に失敗しました。接続を確認してください。';

  @override
  String get createMemory => 'メモリを作成';

  @override
  String get deleteMemoryConfirmation => 'このメモリを削除してもよろしいですか？この操作は元に戻せません。';

  @override
  String get makePrivate => '非公開にする';

  @override
  String get organizeAndControlMemories => 'メモリを整理・管理する';

  @override
  String get total => '合計';

  @override
  String get makeAllMemoriesPrivate => 'すべてのメモリを非公開にする';

  @override
  String get setAllMemoriesToPrivate => 'すべてのメモリを非公開に設定';

  @override
  String get makeAllMemoriesPublic => 'すべてのメモリを公開にする';

  @override
  String get setAllMemoriesToPublic => 'すべてのメモリを公開に設定';

  @override
  String get permanentlyRemoveAllMemories => 'Omiからすべてのメモリを完全に削除';

  @override
  String get allMemoriesAreNowPrivate => 'すべてのメモリが非公開になりました';

  @override
  String get allMemoriesAreNowPublic => 'すべてのメモリが公開になりました';

  @override
  String get clearOmisMemory => 'Omiのメモリをクリア';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Omiのメモリをクリアしてもよろしいですか？この操作は元に戻せず、すべての$count個のメモリが完全に削除されます。';
  }

  @override
  String get omisMemoryCleared => 'あなたに関するOmiのメモリがクリアされました';

  @override
  String get welcomeToOmi => 'Omiへようこそ';

  @override
  String get continueWithApple => 'Appleで続ける';

  @override
  String get continueWithGoogle => 'Googleで続ける';

  @override
  String get byContinuingYouAgree => '続行することで、';

  @override
  String get termsOfService => '利用規約';

  @override
  String get and => 'と';

  @override
  String get dataAndPrivacy => 'データとプライバシー';

  @override
  String get secureAuthViaAppleId => 'Apple IDによる安全な認証';

  @override
  String get secureAuthViaGoogleAccount => 'Googleアカウントによる安全な認証';

  @override
  String get whatWeCollect => '収集する情報';

  @override
  String get dataCollectionMessage => '続行すると、あなたの会話、録音、個人情報は、AI駆動のインサイトを提供し、すべてのアプリ機能を有効にするために、当社のサーバーに安全に保存されます。';

  @override
  String get dataProtection => 'データ保護';

  @override
  String get yourDataIsProtected => 'あなたのデータは保護され、';

  @override
  String get pleaseSelectYourPrimaryLanguage => '主要言語を選択してください';

  @override
  String get chooseYourLanguage => '言語を選択';

  @override
  String get selectPreferredLanguageForBestExperience => '最高のOmi体験のために優先言語を選択してください';

  @override
  String get searchLanguages => '言語を検索...';

  @override
  String get selectALanguage => '言語を選択';

  @override
  String get tryDifferentSearchTerm => '別の検索語を試してください';

  @override
  String get pleaseEnterYourName => 'お名前を入力してください';

  @override
  String get nameMustBeAtLeast2Characters => '名前は2文字以上である必要があります';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed => 'どのように呼ばれたいか教えてください。これにより、Omi体験をパーソナライズできます。';

  @override
  String charactersCount(int count) {
    return '$count文字';
  }

  @override
  String get enableFeaturesForBestExperience => 'デバイスで最高のOmi体験を得るために機能を有効にしてください。';

  @override
  String get microphoneAccess => 'マイクアクセス';

  @override
  String get recordAudioConversations => '音声会話を録音';

  @override
  String get microphoneAccessDescription => 'Omiは会話を録音し、文字起こしを提供するためにマイクアクセスが必要です。';

  @override
  String get screenRecording => '画面録画';

  @override
  String get captureSystemAudioFromMeetings => '会議からシステムオーディオをキャプチャ';

  @override
  String get screenRecordingDescription => 'Omiは、ブラウザベースの会議からシステムオーディオをキャプチャするために画面録画権限が必要です。';

  @override
  String get accessibility => 'アクセシビリティ';

  @override
  String get detectBrowserBasedMeetings => 'ブラウザベースの会議を検出';

  @override
  String get accessibilityDescription => 'Omiは、ブラウザでZoom、Meet、またはTeamsの会議に参加したことを検出するためにアクセシビリティ権限が必要です。';

  @override
  String get pleaseWait => 'お待ちください...';

  @override
  String get joinTheCommunity => 'コミュニティに参加！';

  @override
  String get loadingProfile => 'プロフィールを読み込んでいます...';

  @override
  String get profileSettings => 'プロフィール設定';

  @override
  String get noEmailSet => 'メールアドレスが設定されていません';

  @override
  String get userIdCopiedToClipboard => 'ユーザーIDをコピーしました';

  @override
  String get yourInformation => 'あなたの情報';

  @override
  String get setYourName => '名前を設定';

  @override
  String get changeYourName => '名前を変更';

  @override
  String get manageYourOmiPersona => 'Omiペルソナを管理';

  @override
  String get voiceAndPeople => '音声と人物';

  @override
  String get teachOmiYourVoice => 'Omiにあなたの声を教える';

  @override
  String get tellOmiWhoSaidIt => '誰が言ったかOmiに伝える 🗣️';

  @override
  String get payment => '支払い';

  @override
  String get addOrChangeYourPaymentMethod => '支払い方法を追加または変更';

  @override
  String get preferences => '環境設定';

  @override
  String get helpImproveOmiBySharing => '匿名化された分析データを共有してOmiの改善にご協力ください';

  @override
  String get deleteAccount => 'アカウント削除';

  @override
  String get deleteYourAccountAndAllData => 'アカウントとすべてのデータを削除';

  @override
  String get clearLogs => 'ログをクリア';

  @override
  String get debugLogsCleared => 'デバッグログをクリアしました';

  @override
  String get exportConversations => '会話をエクスポート';

  @override
  String get exportAllConversationsToJson => 'すべての会話をJSONファイルにエクスポートします。';

  @override
  String get conversationsExportStarted => '会話のエクスポートを開始しました。数秒かかる場合がありますので、お待ちください。';

  @override
  String get mcpDescription => 'Omiを他のアプリケーションに接続して、記憶と会話を読み取り、検索し、管理します。開始するにはキーを作成してください。';

  @override
  String get apiKeys => 'APIキー';

  @override
  String errorLabel(String error) {
    return 'エラー: $error';
  }

  @override
  String get noApiKeysFound => 'APIキーが見つかりません。開始するには1つ作成してください。';

  @override
  String get advancedSettings => '詳細設定';

  @override
  String get triggersWhenNewConversationCreated => '新しい会話が作成されたときにトリガーされます。';

  @override
  String get triggersWhenNewTranscriptReceived => '新しい文字起こしを受信したときにトリガーされます。';

  @override
  String get realtimeAudioBytes => 'リアルタイムオーディオバイト';

  @override
  String get triggersWhenAudioBytesReceived => 'オーディオバイトを受信したときにトリガーされます。';

  @override
  String get everyXSeconds => 'x秒ごと';

  @override
  String get triggersWhenDaySummaryGenerated => '日次サマリーが生成されたときにトリガーされます。';

  @override
  String get tryLatestExperimentalFeatures => 'Omiチームの最新の実験的機能をお試しください。';

  @override
  String get transcriptionServiceDiagnosticStatus => '文字起こしサービスの診断ステータス';

  @override
  String get enableDetailedDiagnosticMessages => '文字起こしサービスから詳細な診断メッセージを有効にする';

  @override
  String get autoCreateAndTagNewSpeakers => '新しい話者を自動作成およびタグ付け';

  @override
  String get automaticallyCreateNewPerson => '文字起こしで名前が検出されたときに自動的に新しい人物を作成します。';

  @override
  String get pilotFeatures => 'パイロット機能';

  @override
  String get pilotFeaturesDescription => 'これらの機能はテストであり、サポートは保証されていません。';

  @override
  String get suggestFollowUpQuestion => 'フォローアップ質問を提案';

  @override
  String get saveSettings => '設定を保存';

  @override
  String get syncingDeveloperSettings => '開発者設定を同期中...';

  @override
  String get summary => '概要';

  @override
  String get auto => '自動';

  @override
  String get noSummaryForApp => 'このアプリの要約はありません。より良い結果を得るために別のアプリをお試しください。';

  @override
  String get tryAnotherApp => '別のアプリを試す';

  @override
  String generatedBy(String appName) {
    return '$appNameによって生成';
  }

  @override
  String get overview => '概要';

  @override
  String get otherAppResults => '他のアプリの結果';

  @override
  String get unknownApp => '不明なアプリ';

  @override
  String get noSummaryAvailable => '概要がありません';

  @override
  String get conversationNoSummaryYet => 'この会話にはまだ概要がありません。';

  @override
  String get chooseSummarizationApp => '要約アプリを選択';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appNameをデフォルトの要約アプリとして設定しました';
  }

  @override
  String get letOmiChooseAutomatically => 'Omiに最適なアプリを自動的に選択させる';

  @override
  String get deleteConversationConfirmation => 'この会話を削除してもよろしいですか？この操作は元に戻せません。';

  @override
  String get conversationDeleted => '会話が削除されました';

  @override
  String get generatingLink => 'リンクを生成中...';

  @override
  String get editConversation => '会話を編集';

  @override
  String get conversationLinkCopiedToClipboard => '会話のリンクがクリップボードにコピーされました';

  @override
  String get conversationTranscriptCopiedToClipboard => '会話のトランスクリプトがクリップボードにコピーされました';

  @override
  String get editConversationDialogTitle => '会話を編集';

  @override
  String get changeTheConversationTitle => '会話のタイトルを変更';

  @override
  String get conversationTitle => '会話のタイトル';

  @override
  String get enterConversationTitle => '会話のタイトルを入力...';

  @override
  String get conversationTitleUpdatedSuccessfully => '会話のタイトルが正常に更新されました';

  @override
  String get failedToUpdateConversationTitle => '会話のタイトルの更新に失敗しました';

  @override
  String get errorUpdatingConversationTitle => '会話のタイトルの更新中にエラーが発生しました';

  @override
  String get settingUp => '設定中...';

  @override
  String get startYourFirstRecording => '最初の録音を開始';

  @override
  String get preparingSystemAudioCapture => 'システムオーディオキャプチャを準備中';

  @override
  String get clickTheButtonToCaptureAudio => 'ボタンをクリックして、ライブ文字起こし、AI インサイト、自動保存のためにオーディオをキャプチャします。';

  @override
  String get reconnecting => '再接続中...';

  @override
  String get recordingPaused => '録音一時停止中';

  @override
  String get recordingActive => '録音中';

  @override
  String get startRecording => '録音開始';

  @override
  String resumingInCountdown(String countdown) {
    return '$countdown秒後に再開...';
  }

  @override
  String get tapPlayToResume => '再開するには再生をタップ';

  @override
  String get listeningForAudio => 'オーディオを聴取中...';

  @override
  String get preparingAudioCapture => 'オーディオキャプチャを準備中';

  @override
  String get clickToBeginRecording => 'クリックして録音を開始';

  @override
  String get translated => '翻訳済み';

  @override
  String get liveTranscript => 'ライブ文字起こし';

  @override
  String segmentsSingular(String count) {
    return '$countセグメント';
  }

  @override
  String segmentsPlural(String count) {
    return '$countセグメント';
  }

  @override
  String get startRecordingToSeeTranscript => '録音を開始してライブ文字起こしを表示';

  @override
  String get paused => '一時停止中';

  @override
  String get initializing => '初期化中...';

  @override
  String get recording => '録音中';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'マイクが変更されました。$countdown秒後に再開';
  }

  @override
  String get clickPlayToResumeOrStop => '再開するには再生、終了するには停止をクリック';

  @override
  String get settingUpSystemAudioCapture => 'システムオーディオキャプチャを設定中';

  @override
  String get capturingAudioAndGeneratingTranscript => 'オーディオをキャプチャして文字起こしを生成中';

  @override
  String get clickToBeginRecordingSystemAudio => 'クリックしてシステムオーディオ録音を開始';

  @override
  String get you => 'あなた';

  @override
  String speakerWithId(String speakerId) {
    return '話者$speakerId';
  }

  @override
  String get translatedByOmi => 'omiによって翻訳';

  @override
  String get backToConversations => '会話に戻る';

  @override
  String get systemAudio => 'システム';

  @override
  String get mic => 'マイク';

  @override
  String audioInputSetTo(String deviceName) {
    return 'オーディオ入力を$deviceNameに設定';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'オーディオデバイスの切り替えエラー: $error';
  }

  @override
  String get selectAudioInput => 'オーディオ入力を選択';

  @override
  String get loadingDevices => 'デバイスを読み込み中...';

  @override
  String get settingsHeader => '設定';

  @override
  String get plansAndBilling => 'プランと請求';

  @override
  String get calendarIntegration => 'カレンダー統合';

  @override
  String get dailySummary => 'デイリーサマリー';

  @override
  String get developer => '開発者';

  @override
  String get about => 'について';

  @override
  String get selectTime => '時間を選択';

  @override
  String get accountGroup => 'アカウント';

  @override
  String get signOutQuestion => 'サインアウトしますか？';

  @override
  String get signOutConfirmation => 'サインアウトしてもよろしいですか？';

  @override
  String get customVocabularyHeader => 'カスタム語彙';

  @override
  String get addWordsDescription => '文字起こし中にOmiが認識すべき単語を追加します。';

  @override
  String get enterWordsHint => '単語を入力（カンマ区切り）';

  @override
  String get dailySummaryHeader => '日次サマリー';

  @override
  String get dailySummaryTitle => '日次サマリー';

  @override
  String get dailySummaryDescription => '1日の会話のパーソナライズされたサマリーを通知として受け取ります。';

  @override
  String get deliveryTime => '配信時間';

  @override
  String get deliveryTimeDescription => '日次サマリーを受け取る時刻';

  @override
  String get subscription => 'サブスクリプション';

  @override
  String get viewPlansAndUsage => 'プランと使用状況を表示';

  @override
  String get viewPlansDescription => 'サブスクリプションを管理し、使用統計を確認';

  @override
  String get addOrChangePaymentMethod => '支払い方法を追加または変更';

  @override
  String get displayOptions => '表示オプション';

  @override
  String get showMeetingsInMenuBar => 'メニューバーに会議を表示';

  @override
  String get displayUpcomingMeetingsDescription => 'メニューバーに今後の会議を表示';

  @override
  String get showEventsWithoutParticipants => '参加者のないイベントを表示';

  @override
  String get includePersonalEventsDescription => '参加者のない個人イベントを含める';

  @override
  String get upcomingMeetings => '今後の予定';

  @override
  String get checkingNext7Days => '次の7日間をチェック中';

  @override
  String get shortcuts => 'ショートカット';

  @override
  String get shortcutChangeInstruction => 'ショートカットをクリックして変更します。Escapeキーでキャンセル。';

  @override
  String get configurePersonaDescription => 'AIペルソナを設定';

  @override
  String get configureSTTProvider => 'STTプロバイダーを設定';

  @override
  String get setConversationEndDescription => '会話が自動的に終了するタイミングを設定';

  @override
  String get importDataDescription => '他のソースからデータをインポート';

  @override
  String get exportConversationsDescription => '会話を JSON にエクスポート';

  @override
  String get exportingConversations => '会話をエクスポート中...';

  @override
  String get clearNodesDescription => 'すべてのノードと接続をクリア';

  @override
  String get deleteKnowledgeGraphQuestion => 'ナレッジグラフを削除しますか？';

  @override
  String get deleteKnowledgeGraphWarning => 'これにより、派生したすべてのナレッジグラフデータが削除されます。元の記憶は安全に保たれます。';

  @override
  String get connectOmiWithAI => 'Omi を AI アシスタントに接続';

  @override
  String get noAPIKeys => 'APIキーがありません。開始するには作成してください。';

  @override
  String get autoCreateWhenDetected => '名前が検出されたら自動作成';

  @override
  String get trackPersonalGoals => 'ホームページで個人目標を追跡';

  @override
  String get dailyReflectionDescription => '午後9時に1日を振り返り、考えを記録するリマインダーを受け取ります。';

  @override
  String get endpointURL => 'エンドポイント URL';

  @override
  String get links => 'リンク';

  @override
  String get discordMemberCount => 'Discord に 8000 人以上のメンバー';

  @override
  String get userInformation => 'ユーザー情報';

  @override
  String get capabilities => '機能';

  @override
  String get previewScreenshots => 'スクリーンショットプレビュー';

  @override
  String get holdOnPreparingForm => 'お待ちください、フォームを準備しています';

  @override
  String get bySubmittingYouAgreeToOmi => '送信することで、Omiの';

  @override
  String get termsAndPrivacyPolicy => '利用規約とプライバシーポリシー';

  @override
  String get helpsDiagnoseIssuesAutoDeletes => '問題の診断に役立ちます。3日後に自動削除されます。';

  @override
  String get manageYourApp => 'アプリを管理';

  @override
  String get updatingYourApp => 'アプリを更新中';

  @override
  String get fetchingYourAppDetails => 'アプリの詳細を取得中';

  @override
  String get updateAppQuestion => 'アプリを更新しますか？';

  @override
  String get updateAppConfirmation => 'アプリを更新してよろしいですか？変更はチームの審査後に反映されます。';

  @override
  String get updateApp => 'アプリを更新';

  @override
  String get createAndSubmitNewApp => '新しいアプリを作成して送信';

  @override
  String appsCount(String count) {
    return 'アプリ ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'プライベートアプリ ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return '公開アプリ ($count)';
  }

  @override
  String get newVersionAvailable => '新しいバージョンが利用可能です  🎉';

  @override
  String get no => 'いいえ';

  @override
  String get subscriptionCancelledSuccessfully => 'サブスクリプションが正常にキャンセルされました。現在の請求期間の終了まで有効です。';

  @override
  String get failedToCancelSubscription => 'サブスクリプションのキャンセルに失敗しました。もう一度お試しください。';

  @override
  String get invalidPaymentUrl => '無効な支払いURL';

  @override
  String get permissionsAndTriggers => '権限とトリガー';

  @override
  String get chatFeatures => 'チャット機能';

  @override
  String get uninstall => 'アンインストール';

  @override
  String get installs => 'インストール数';

  @override
  String get priceLabel => '価格';

  @override
  String get updatedLabel => '更新日';

  @override
  String get createdLabel => '作成日';

  @override
  String get featuredLabel => 'おすすめ';

  @override
  String get cancelSubscriptionQuestion => 'サブスクリプションをキャンセルしますか？';

  @override
  String get cancelSubscriptionConfirmation => 'サブスクリプションをキャンセルしてもよろしいですか？現在の請求期間の終了までアクセスできます。';

  @override
  String get cancelSubscriptionButton => 'サブスクリプションをキャンセル';

  @override
  String get cancelling => 'キャンセル中...';

  @override
  String get betaTesterMessage => 'あなたはこのアプリのベータテスターです。まだ公開されていません。承認後に公開されます。';

  @override
  String get appUnderReviewMessage => 'あなたのアプリは審査中で、あなただけに表示されています。承認後に公開されます。';

  @override
  String get appRejectedMessage => 'アプリが却下されました。詳細を更新して再度審査に提出してください。';

  @override
  String get invalidIntegrationUrl => '無効な統合URL';

  @override
  String get tapToComplete => 'タップして完了';

  @override
  String get invalidSetupInstructionsUrl => '無効なセットアップ手順URL';

  @override
  String get pushToTalk => 'プッシュトゥトーク';

  @override
  String get summaryPrompt => '要約プロンプト';

  @override
  String get pleaseSelectARating => '評価を選択してください';

  @override
  String get reviewAddedSuccessfully => 'レビューが正常に追加されました 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'レビューが正常に更新されました 🚀';

  @override
  String get failedToSubmitReview => 'レビューの送信に失敗しました。もう一度お試しください。';

  @override
  String get addYourReview => 'レビューを追加';

  @override
  String get editYourReview => 'レビューを編集';

  @override
  String get writeAReviewOptional => 'レビューを書く（任意）';

  @override
  String get submitReview => 'レビューを送信';

  @override
  String get updateReview => 'レビューを更新';

  @override
  String get yourReview => 'あなたのレビュー';

  @override
  String get anonymousUser => '匿名ユーザー';

  @override
  String get issueActivatingApp => 'このアプリのアクティベーションで問題が発生しました。もう一度お試しください。';

  @override
  String get dataAccessNoticeDescription => 'このアプリはあなたのデータにアクセスします。Omi AIは、このアプリによるデータの使用、変更、削除について責任を負いません';

  @override
  String get copyUrl => 'URLをコピー';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => '月';

  @override
  String get weekdayTue => '火';

  @override
  String get weekdayWed => '水';

  @override
  String get weekdayThu => '木';

  @override
  String get weekdayFri => '金';

  @override
  String get weekdaySat => '土';

  @override
  String get weekdaySun => '日';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return '$serviceName連携は近日公開予定';
  }

  @override
  String alreadyExportedTo(String platform) {
    return '$platformにエクスポート済み';
  }

  @override
  String get anotherPlatform => '別のプラットフォーム';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return '設定 > タスク連携で$serviceNameの認証を行ってください';
  }

  @override
  String addingToService(String serviceName) {
    return '$serviceNameに追加中...';
  }

  @override
  String addedToService(String serviceName) {
    return '$serviceNameに追加しました';
  }

  @override
  String failedToAddToService(String serviceName) {
    return '$serviceNameへの追加に失敗しました';
  }

  @override
  String get permissionDeniedForAppleReminders => 'Appleリマインダーの権限が拒否されました';

  @override
  String failedToCreateApiKey(String error) {
    return 'プロバイダーAPIキーの作成に失敗しました: $error';
  }

  @override
  String get createAKey => 'キーを作成';

  @override
  String get apiKeyRevokedSuccessfully => 'APIキーが正常に取り消されました';

  @override
  String failedToRevokeApiKey(String error) {
    return 'APIキーの取り消しに失敗しました: $error';
  }

  @override
  String get omiApiKeys => 'Omi APIキー';

  @override
  String get apiKeysDescription => 'APIキーは、アプリがOMIサーバーと通信する際の認証に使用されます。アプリケーションがメモリを作成し、他のOMIサービスに安全にアクセスできるようにします。';

  @override
  String get aboutOmiApiKeys => 'Omi APIキーについて';

  @override
  String get yourNewKey => '新しいキー:';

  @override
  String get copyToClipboard => 'クリップボードにコピー';

  @override
  String get pleaseCopyKeyNow => '今すぐコピーして、安全な場所に書き留めてください。';

  @override
  String get willNotSeeAgain => '再度表示することはできません。';

  @override
  String get revokeKey => 'キーを取り消す';

  @override
  String get revokeApiKeyQuestion => 'APIキーを取り消しますか?';

  @override
  String get revokeApiKeyWarning => 'この操作は取り消せません。このキーを使用しているアプリケーションはAPIにアクセスできなくなります。';

  @override
  String get revoke => '取り消す';

  @override
  String get whatWouldYouLikeToCreate => '何を作成しますか？';

  @override
  String get createAnApp => 'アプリを作成';

  @override
  String get createAndShareYourApp => 'アプリを作成して共有';

  @override
  String get createMyClone => 'クローンを作成';

  @override
  String get createYourDigitalClone => 'デジタルクローンを作成';

  @override
  String get itemApp => 'アプリ';

  @override
  String get itemPersona => 'ペルソナ';

  @override
  String keepItemPublic(String item) {
    return '$itemを公開のままにする';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return '$itemを公開しますか？';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return '$itemを非公開にしますか？';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return '$itemを公開すると、誰でも使用できるようになります';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return '$itemを非公開にすると、すべての人に対して機能しなくなり、あなただけに表示されます';
  }

  @override
  String get manageApp => 'アプリを管理';

  @override
  String get updatePersonaDetails => 'ペルソナの詳細を更新';

  @override
  String deleteItemTitle(String item) {
    return '$itemを削除';
  }

  @override
  String deleteItemQuestion(String item) {
    return '$itemを削除しますか？';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'この$itemを削除してもよろしいですか？この操作は元に戻せません。';
  }

  @override
  String get revokeKeyQuestion => 'キーを取り消しますか？';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'キー「$keyName」を取り消してもよろしいですか？この操作は元に戻せません。';
  }

  @override
  String get createNewKey => '新しいキーを作成';

  @override
  String get keyNameHint => '例: Claude Desktop';

  @override
  String get pleaseEnterAName => '名前を入力してください。';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'キーの作成に失敗しました: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'キーの作成に失敗しました。もう一度お試しください。';

  @override
  String get keyCreated => 'キーが作成されました';

  @override
  String get keyCreatedMessage => '新しいキーが作成されました。今すぐコピーしてください。再度表示することはできません。';

  @override
  String get keyWord => 'キー';

  @override
  String get externalAppAccess => '外部アプリのアクセス';

  @override
  String get externalAppAccessDescription => '以下のインストール済みアプリは外部連携があり、会話やメモリーなどのデータにアクセスできます。';

  @override
  String get noExternalAppsHaveAccess => '外部アプリはデータにアクセスできません。';

  @override
  String get maximumSecurityE2ee => '最大セキュリティ（E2EE）';

  @override
  String get e2eeDescription => 'エンドツーエンド暗号化はプライバシーの最高基準です。有効にすると、データはサーバーに送信される前にデバイス上で暗号化されます。これは、Omiを含め、誰もあなたのコンテンツにアクセスできないことを意味します。';

  @override
  String get importantTradeoffs => '重要なトレードオフ：';

  @override
  String get e2eeTradeoff1 => '• 外部アプリ連携などの一部の機能が無効になる場合があります。';

  @override
  String get e2eeTradeoff2 => '• パスワードを紛失した場合、データを復元することはできません。';

  @override
  String get featureComingSoon => 'この機能は近日公開予定です！';

  @override
  String get migrationInProgressMessage => '移行中です。完了するまで保護レベルを変更できません。';

  @override
  String get migrationFailed => '移行に失敗しました';

  @override
  String migratingFromTo(String source, String target) {
    return '$source から $target に移行中';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total オブジェクト';
  }

  @override
  String get secureEncryption => '安全な暗号化';

  @override
  String get secureEncryptionDescription => 'あなたのデータは、Google Cloudでホストされている当社のサーバー上で、あなた固有の鍵で暗号化されています。これは、生のコンテンツがOmiスタッフやGoogleを含む誰にも、データベースから直接アクセスできないことを意味します。';

  @override
  String get endToEndEncryption => 'エンドツーエンド暗号化';

  @override
  String get e2eeCardDescription => '最大のセキュリティを有効にすると、あなただけがデータにアクセスできます。詳しくはタップしてください。';

  @override
  String get dataAlwaysEncrypted => 'レベルに関係なく、データは常に保存時および転送時に暗号化されています。';

  @override
  String get readOnlyScope => '読み取り専用';

  @override
  String get fullAccessScope => 'フルアクセス';

  @override
  String get readScope => '読み取り';

  @override
  String get writeScope => '書き込み';

  @override
  String get apiKeyCreated => 'APIキーが作成されました！';

  @override
  String get saveKeyWarning => 'このキーを今すぐ保存してください！再度表示することはできません。';

  @override
  String get yourApiKey => 'あなたのAPIキー';

  @override
  String get tapToCopy => 'タップしてコピー';

  @override
  String get copyKey => 'キーをコピー';

  @override
  String get createApiKey => 'APIキーを作成';

  @override
  String get accessDataProgrammatically => 'プログラムでデータにアクセス';

  @override
  String get keyNameLabel => 'キー名';

  @override
  String get keyNamePlaceholder => '例：マイアプリ連携';

  @override
  String get permissionsLabel => '権限';

  @override
  String get permissionsInfoNote => 'R = 読み取り、W = 書き込み。何も選択しない場合は読み取り専用。';

  @override
  String get developerApi => '開発者API';

  @override
  String get createAKeyToGetStarted => 'キーを作成して始めましょう';

  @override
  String errorWithMessage(String error) {
    return 'エラー: $error';
  }

  @override
  String get omiTraining => 'Omi トレーニング';

  @override
  String get trainingDataProgram => 'トレーニングデータプログラム';

  @override
  String get getOmiUnlimitedFree => 'AIモデルのトレーニングにデータを提供することで、Omi Unlimitedを無料で入手できます。';

  @override
  String get trainingDataBullets => '• あなたのデータがAIモデルの改善に役立ちます\n• 機密性のないデータのみが共有されます\n• 完全に透明なプロセス';

  @override
  String get learnMoreAtOmiTraining => '詳細はomi.me/trainingをご覧ください';

  @override
  String get agreeToContributeData => 'AIトレーニングのためにデータを提供することを理解し、同意します';

  @override
  String get submitRequest => 'リクエストを送信';

  @override
  String get thankYouRequestUnderReview => 'ありがとうございます！リクエストは審査中です。承認後にお知らせします。';

  @override
  String planRemainsActiveUntil(String date) {
    return 'プランは$dateまで有効です。その後、無制限の機能へのアクセスを失います。よろしいですか？';
  }

  @override
  String get confirmCancellation => 'キャンセルを確認';

  @override
  String get keepMyPlan => 'プランを維持';

  @override
  String get subscriptionSetToCancel => 'サブスクリプションは期間終了時にキャンセルされるよう設定されています。';

  @override
  String get switchedToOnDevice => 'デバイス上の文字起こしに切り替えました';

  @override
  String get couldNotSwitchToFreePlan => '無料プランに切り替えられませんでした。もう一度お試しください。';

  @override
  String get couldNotLoadPlans => '利用可能なプランを読み込めませんでした。もう一度お試しください。';

  @override
  String get selectedPlanNotAvailable => '選択したプランは利用できません。もう一度お試しください。';

  @override
  String get upgradeToAnnualPlan => '年間プランにアップグレード';

  @override
  String get importantBillingInfo => '重要な請求情報：';

  @override
  String get monthlyPlanContinues => '現在の月額プランは請求期間の終了まで継続されます';

  @override
  String get paymentMethodCharged => '月額プランが終了すると、既存のお支払い方法に自動的に請求されます';

  @override
  String get annualSubscriptionStarts => '12ヶ月の年間サブスクリプションは、請求後に自動的に開始されます';

  @override
  String get thirteenMonthsCoverage => '合計13ヶ月の保障を受けられます（当月 + 年間12ヶ月）';

  @override
  String get confirmUpgrade => 'アップグレードを確認';

  @override
  String get confirmPlanChange => 'プラン変更を確認';

  @override
  String get confirmAndProceed => '確認して続行';

  @override
  String get upgradeScheduled => 'アップグレード予定';

  @override
  String get changePlan => 'プランを変更';

  @override
  String get upgradeAlreadyScheduled => '年間プランへのアップグレードは既に予定されています';

  @override
  String get youAreOnUnlimitedPlan => 'Unlimitedプランをご利用中です。';

  @override
  String get yourOmiUnleashed => 'あなたのOmiを解き放とう。無限の可能性のためにUnlimitedへ。';

  @override
  String planEndedOn(String date) {
    return 'プランは$dateに終了しました。\\n今すぐ再登録 - 新しい請求期間の料金が即座に請求されます。';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'プランは$dateにキャンセル予定です。\\n特典を維持するために今すぐ再登録 - $dateまで請求はありません。';
  }

  @override
  String get annualPlanStartsAutomatically => '月額プランが終了すると、年間プランが自動的に開始されます。';

  @override
  String planRenewsOn(String date) {
    return 'プランは$dateに更新されます。';
  }

  @override
  String get unlimitedConversations => '無制限の会話';

  @override
  String get askOmiAnything => 'Omiにあなたの人生について何でも聞いてください';

  @override
  String get unlockOmiInfiniteMemory => 'Omiの無限メモリーをアンロック';

  @override
  String get youreOnAnnualPlan => '年間プランをご利用中です';

  @override
  String get alreadyBestValuePlan => 'すでに最もお得なプランをご利用中です。変更の必要はありません。';

  @override
  String get unableToLoadPlans => 'プランを読み込めません';

  @override
  String get checkConnectionTryAgain => '接続を確認してもう一度お試しください';

  @override
  String get useFreePlan => '無料プランを使用';

  @override
  String get continueText => '続ける';

  @override
  String get resubscribe => '再購読';

  @override
  String get couldNotOpenPaymentSettings => '支払い設定を開けませんでした。もう一度お試しください。';

  @override
  String get managePaymentMethod => '支払い方法を管理';

  @override
  String get cancelSubscription => 'サブスクリプションをキャンセル';

  @override
  String endsOnDate(String date) {
    return '$dateに終了';
  }

  @override
  String get active => 'アクティブ';

  @override
  String get freePlan => '無料プラン';

  @override
  String get configure => '設定';

  @override
  String get privacyInformation => 'プライバシー情報';

  @override
  String get yourPrivacyMattersToUs => 'あなたのプライバシーは私たちにとって大切です';

  @override
  String get privacyIntroText => 'Omiでは、お客様のプライバシーを非常に重要視しています。収集するデータとその使用方法について透明性を保ちたいと考えています。以下が知っておくべきことです：';

  @override
  String get whatWeTrack => '追跡する内容';

  @override
  String get anonymityAndPrivacy => '匿名性とプライバシー';

  @override
  String get optInAndOptOutOptions => 'オプトインとオプトアウトのオプション';

  @override
  String get ourCommitment => '私たちの約束';

  @override
  String get commitmentText => '私たちは収集したデータをOmiをより良い製品にするためだけに使用することを約束します。あなたのプライバシーと信頼は私たちにとって最も重要です。';

  @override
  String get thankYouText => 'Omiの大切なユーザーであることに感謝します。ご質問やご不明な点がございましたら、team@basedhardware.comまでお気軽にお問い合わせください。';

  @override
  String get wifiSyncSettings => 'WiFi同期設定';

  @override
  String get enterHotspotCredentials => 'スマートフォンのホットスポット認証情報を入力';

  @override
  String get wifiSyncUsesHotspot => 'WiFi同期はスマートフォンをホットスポットとして使用します。設定 > インターネット共有で名前とパスワードを確認してください。';

  @override
  String get hotspotNameSsid => 'ホットスポット名（SSID）';

  @override
  String get exampleIphoneHotspot => '例：iPhoneホットスポット';

  @override
  String get password => 'パスワード';

  @override
  String get enterHotspotPassword => 'ホットスポットのパスワードを入力';

  @override
  String get saveCredentials => '認証情報を保存';

  @override
  String get clearCredentials => '認証情報をクリア';

  @override
  String get pleaseEnterHotspotName => 'ホットスポット名を入力してください';

  @override
  String get wifiCredentialsSaved => 'WiFi認証情報を保存しました';

  @override
  String get wifiCredentialsCleared => 'WiFi認証情報をクリアしました';

  @override
  String summaryGeneratedForDate(String date) {
    return '$dateの要約を生成しました';
  }

  @override
  String get failedToGenerateSummaryCheckConversations => '要約の生成に失敗しました。その日の会話があることを確認してください。';

  @override
  String get summaryNotFound => '要約が見つかりません';

  @override
  String get yourDaysJourney => '今日の旅程';

  @override
  String get highlights => 'ハイライト';

  @override
  String get unresolvedQuestions => '未解決の質問';

  @override
  String get decisions => '決定事項';

  @override
  String get learnings => '学び';

  @override
  String get autoDeletesAfterThreeDays => '3日後に自動削除されます。';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'ナレッジグラフが正常に削除されました';

  @override
  String get exportStartedMayTakeFewSeconds => 'エクスポートを開始しました。数秒かかる場合があります...';

  @override
  String get knowledgeGraphDeleteDescription => 'これにより、すべての派生ナレッジグラフデータ（ノードと接続）が削除されます。元の記憶は安全に保たれます。グラフは時間の経過とともに、または次のリクエスト時に再構築されます。';

  @override
  String get configureDailySummaryDigest => '毎日のタスクダイジェストを設定する';

  @override
  String accessesDataTypes(String dataTypes) {
    return '$dataTypesにアクセス';
  }

  @override
  String triggeredByType(String triggerType) {
    return '$triggerTypeでトリガー';
  }

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription、$triggerDescription。';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return '$triggerDescription。';
  }

  @override
  String get noSpecificDataAccessConfigured => '特定のデータアクセスは設定されていません。';

  @override
  String get basicPlanDescription => '1,200プレミアム分 + デバイス無制限';

  @override
  String get minutes => '分';

  @override
  String get omiHas => 'Omiは:';

  @override
  String get premiumMinutesUsed => 'プレミアム分を使用済み。';

  @override
  String get setupOnDevice => 'オンデバイスを設定';

  @override
  String get forUnlimitedFreeTranscription => '無制限の無料文字起こしのため。';

  @override
  String premiumMinsLeft(int count) {
    return '残りプレミアム$count分。';
  }

  @override
  String get alwaysAvailable => '常に利用可能。';

  @override
  String get importHistory => 'インポート履歴';

  @override
  String get noImportsYet => 'インポートはまだありません';

  @override
  String get selectZipFileToImport => 'インポートする.zipファイルを選択してください！';

  @override
  String get otherDevicesComingSoon => '他のデバイスは近日対応';

  @override
  String get deleteAllLimitlessConversations => 'すべてのLimitless会話を削除しますか？';

  @override
  String get deleteAllLimitlessWarning => 'これにより、Limitlessからインポートされたすべての会話が完全に削除されます。この操作は元に戻せません。';

  @override
  String deletedLimitlessConversations(int count) {
    return '$count件のLimitless会話を削除しました';
  }

  @override
  String get failedToDeleteConversations => '会話の削除に失敗しました';

  @override
  String get deleteImportedData => 'インポートしたデータを削除';

  @override
  String get statusPending => '保留中';

  @override
  String get statusProcessing => '処理中';

  @override
  String get statusCompleted => '完了';

  @override
  String get statusFailed => '失敗';

  @override
  String nConversations(int count) {
    return '$count件の会話';
  }

  @override
  String get pleaseEnterName => '名前を入力してください';

  @override
  String get nameMustBeBetweenCharacters => '名前は2〜40文字である必要があります';

  @override
  String get deleteSampleQuestion => 'サンプルを削除しますか？';

  @override
  String deleteSampleConfirmation(String name) {
    return '$nameのサンプルを削除してもよろしいですか？';
  }

  @override
  String get confirmDeletion => '削除の確認';

  @override
  String deletePersonConfirmation(String name) {
    return '$nameを削除してもよろしいですか？これにより、関連するすべての音声サンプルも削除されます。';
  }

  @override
  String get howItWorksTitle => '仕組みは？';

  @override
  String get howPeopleWorks => '人物を作成したら、会話のトランスクリプトに移動して対応するセグメントを割り当てることで、Omiがその人の音声も認識できるようになります！';

  @override
  String get tapToDelete => 'タップして削除';

  @override
  String get newTag => '新着';

  @override
  String get needHelpChatWithUs => 'ヘルプが必要ですか？チャットでお問い合わせ';

  @override
  String get localStorageEnabled => 'ローカルストレージが有効';

  @override
  String get localStorageDisabled => 'ローカルストレージが無効';

  @override
  String failedToUpdateSettings(String error) {
    return '設定の更新に失敗しました: $error';
  }

  @override
  String get privacyNotice => 'プライバシー通知';

  @override
  String get recordingsMayCaptureOthers => '録音により他の人の声が記録される場合があります。有効にする前に、すべての参加者の同意を得てください。';

  @override
  String get enable => '有効にする';

  @override
  String get storeAudioOnPhone => '電話にオーディオを保存';

  @override
  String get on => 'On';

  @override
  String get storeAudioDescription => 'すべての音声録音を電話にローカルで保存します。無効にすると、ストレージ容量を節約するために失敗したアップロードのみが保持されます。';

  @override
  String get enableLocalStorage => 'ローカルストレージを有効にする';

  @override
  String get cloudStorageEnabled => 'クラウドストレージが有効';

  @override
  String get cloudStorageDisabled => 'クラウドストレージが無効';

  @override
  String get enableCloudStorage => 'クラウドストレージを有効にする';

  @override
  String get storeAudioOnCloud => 'クラウドにオーディオを保存';

  @override
  String get cloudStorageDialogMessage => 'リアルタイムの録音は、話している間にプライベートクラウドストレージに保存されます。';

  @override
  String get storeAudioCloudDescription => '話している間、リアルタイムの録音をプライベートクラウドストレージに保存します。音声はリアルタイムで安全にキャプチャおよび保存されます。';

  @override
  String get downloadingFirmware => 'ファームウェアをダウンロード中';

  @override
  String get installingFirmware => 'ファームウェアをインストール中';

  @override
  String get firmwareUpdateWarning => 'アプリを閉じたりデバイスの電源を切らないでください。デバイスが破損する可能性があります。';

  @override
  String get firmwareUpdated => 'ファームウェアが更新されました';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'アップデートを完了するには、$deviceNameを再起動してください。';
  }

  @override
  String get yourDeviceIsUpToDate => 'お使いのデバイスは最新です';

  @override
  String get currentVersion => '現在のバージョン';

  @override
  String get latestVersion => '最新バージョン';

  @override
  String get whatsNew => '新機能';

  @override
  String get installUpdate => 'アップデートをインストール';

  @override
  String get updateNow => '今すぐ更新';

  @override
  String get updateGuide => '更新ガイド';

  @override
  String get checkingForUpdates => 'アップデートを確認中';

  @override
  String get checkingFirmwareVersion => 'ファームウェアバージョンを確認中...';

  @override
  String get firmwareUpdate => 'ファームウェア更新';

  @override
  String get payments => '支払い';

  @override
  String get connectPaymentMethodInfo => '下記で支払い方法を接続して、アプリの収益を受け取り始めましょう。';

  @override
  String get selectedPaymentMethod => '選択された支払い方法';

  @override
  String get availablePaymentMethods => '利用可能な支払い方法';

  @override
  String get activeStatus => 'アクティブ';

  @override
  String get connectedStatus => '接続済み';

  @override
  String get notConnectedStatus => '未接続';

  @override
  String get setActive => 'アクティブに設定';

  @override
  String get getPaidThroughStripe => 'Stripeを通じてアプリ販売の収益を受け取りましょう';

  @override
  String get monthlyPayouts => '月次支払い';

  @override
  String get monthlyPayoutsDescription => '収益が10ドルに達すると、毎月の支払いが直接口座に届きます';

  @override
  String get secureAndReliable => '安全で信頼性が高い';

  @override
  String get stripeSecureDescription => 'Stripeはアプリ収益の安全でタイムリーな送金を保証します';

  @override
  String get selectYourCountry => '国を選択してください';

  @override
  String get countrySelectionPermanent => '国の選択は永続的で、後から変更できません。';

  @override
  String get byClickingConnectNow => '「今すぐ接続」をクリックすると、以下に同意したことになります';

  @override
  String get stripeConnectedAccountAgreement => 'Stripe Connectアカウント契約';

  @override
  String get errorConnectingToStripe => 'Stripeへの接続エラー！後でもう一度お試しください。';

  @override
  String get connectingYourStripeAccount => 'Stripeアカウントを接続中';

  @override
  String get stripeOnboardingInstructions => 'ブラウザでStripeのオンボーディングプロセスを完了してください。完了すると、このページは自動的に更新されます。';

  @override
  String get failedTryAgain => '失敗しましたか？再試行';

  @override
  String get illDoItLater => '後でやります';

  @override
  String get successfullyConnected => '接続に成功しました！';

  @override
  String get stripeReadyForPayments => 'Stripeアカウントが支払いを受け取る準備ができました。すぐにアプリ販売から収益を得られます。';

  @override
  String get updateStripeDetails => 'Stripe詳細を更新';

  @override
  String get errorUpdatingStripeDetails => 'Stripe詳細の更新エラー！後でもう一度お試しください。';

  @override
  String get updatePayPal => 'PayPalを更新';

  @override
  String get setUpPayPal => 'PayPalを設定';

  @override
  String get updatePayPalAccountDetails => 'PayPalアカウントの詳細を更新';

  @override
  String get connectPayPalToReceivePayments => 'PayPalアカウントを接続して、アプリの支払いを受け取り始めましょう';

  @override
  String get paypalEmail => 'PayPalメール';

  @override
  String get paypalMeLink => 'PayPal.meリンク';

  @override
  String get stripeRecommendation => 'お住まいの国でStripeが利用可能な場合は、より迅速で簡単な支払いのためにStripeの使用を強くお勧めします。';

  @override
  String get updatePayPalDetails => 'PayPal詳細を更新';

  @override
  String get savePayPalDetails => 'PayPal詳細を保存';

  @override
  String get pleaseEnterPayPalEmail => 'PayPalのメールアドレスを入力してください';

  @override
  String get pleaseEnterPayPalMeLink => 'PayPal.meリンクを入力してください';

  @override
  String get doNotIncludeHttpInLink => 'リンクにhttp、https、wwwを含めないでください';

  @override
  String get pleaseEnterValidPayPalMeLink => '有効なPayPal.meリンクを入力してください';

  @override
  String get pleaseEnterValidEmail => '有効なメールアドレスを入力してください';

  @override
  String get syncingYourRecordings => '録音を同期中';

  @override
  String get syncYourRecordings => '録音を同期する';

  @override
  String get syncNow => '今すぐ同期';

  @override
  String get error => 'エラー';

  @override
  String get speechSamples => '音声サンプル';

  @override
  String additionalSampleIndex(String index) {
    return '追加サンプル $index';
  }

  @override
  String durationSeconds(String seconds) {
    return '長さ: $seconds 秒';
  }

  @override
  String get additionalSpeechSampleRemoved => '追加の音声サンプルを削除しました';

  @override
  String get consentDataMessage => '続行すると、このアプリと共有するすべてのデータ（会話、録音、個人情報を含む）が安全に当社のサーバーに保存され、AI搭載のインサイトを提供し、すべてのアプリ機能を有効にします。';

  @override
  String get tasksEmptyStateMessage => '会話からのタスクがここに表示されます。\n手動で作成するには + をタップしてください。';

  @override
  String get clearChatAction => 'チャットを消去';

  @override
  String get enableApps => 'アプリを有効化';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => 'もっと見る ↓';

  @override
  String get showLess => '閉じる ↑';

  @override
  String get loadingYourRecording => '録音を読み込み中...';

  @override
  String get photoDiscardedMessage => 'この写真は重要ではなかったため破棄されました。';

  @override
  String get analyzing => '分析中...';

  @override
  String get searchCountries => '国を検索...';

  @override
  String get checkingAppleWatch => 'Apple Watchを確認中...';

  @override
  String get installOmiOnAppleWatch => 'Apple WatchにOmiを\nインストール';

  @override
  String get installOmiOnAppleWatchDescription => 'Apple WatchでOmiを使用するには、まずウォッチにOmiアプリをインストールする必要があります。';

  @override
  String get openOmiOnAppleWatch => 'Apple WatchでOmiを\n開く';

  @override
  String get openOmiOnAppleWatchDescription => 'OmiアプリはApple Watchにインストールされています。開いてスタートをタップしてください。';

  @override
  String get openWatchApp => 'Watchアプリを開く';

  @override
  String get iveInstalledAndOpenedTheApp => 'アプリをインストールして開きました';

  @override
  String get unableToOpenWatchApp => 'Apple Watchアプリを開けませんでした。Apple WatchのWatchアプリを手動で開き、「利用可能なApp」セクションからOmiをインストールしてください。';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watchが正常に接続されました！';

  @override
  String get appleWatchNotReachable => 'Apple Watchにまだ接続できません。ウォッチでOmiアプリが開いていることを確認してください。';

  @override
  String errorCheckingConnection(String error) {
    return '接続確認エラー: $error';
  }

  @override
  String get muted => 'ミュート';

  @override
  String get processNow => '今すぐ処理';

  @override
  String get finishedConversation => '会話を終了しますか？';

  @override
  String get stopRecordingConfirmation => '録音を停止して会話を今すぐ要約しますか？';

  @override
  String get conversationEndsManually => '会話は手動でのみ終了します。';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return '会話は$minutes分$suffixの無音後に要約されます。';
  }

  @override
  String get dontAskAgain => '次回から表示しない';

  @override
  String get waitingForTranscriptOrPhotos => '文字起こしまたは写真を待機中...';

  @override
  String get noSummaryYet => 'まだ要約がありません';

  @override
  String hints(String text) {
    return 'ヒント: $text';
  }

  @override
  String get testConversationPrompt => '会話プロンプトをテスト';

  @override
  String get prompt => 'プロンプト';

  @override
  String get result => '結果:';

  @override
  String get compareTranscripts => '文字起こしを比較';

  @override
  String get notHelpful => '役に立たなかった';

  @override
  String get exportTasksWithOneTap => 'ワンタップでタスクをエクスポート！';

  @override
  String get inProgress => '処理中';

  @override
  String get photos => '写真';

  @override
  String get rawData => '生データ';

  @override
  String get content => 'コンテンツ';

  @override
  String get noContentToDisplay => '表示するコンテンツがありません';

  @override
  String get noSummary => '要約なし';

  @override
  String get updateOmiFirmware => 'omiファームウェアを更新';

  @override
  String get anErrorOccurredTryAgain => 'エラーが発生しました。もう一度お試しください。';

  @override
  String get welcomeBackSimple => 'おかえりなさい';

  @override
  String get addVocabularyDescription => '文字起こし中にOmiが認識すべき単語を追加します。';

  @override
  String get enterWordsCommaSeparated => '単語を入力（カンマ区切り）';

  @override
  String get whenToReceiveDailySummary => 'デイリーサマリーを受け取る時間';

  @override
  String get checkingNextSevenDays => '今後7日間を確認中';

  @override
  String failedToDeleteError(String error) {
    return '削除に失敗しました: $error';
  }

  @override
  String get developerApiKeys => '開発者APIキー';

  @override
  String get noApiKeysCreateOne => 'APIキーがありません。作成して開始してください。';

  @override
  String get commandRequired => '⌘ が必要です';

  @override
  String get spaceKey => 'スペース';

  @override
  String loadMoreRemaining(String count) {
    return 'さらに読み込む（残り$count件）';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return '上位$percentile%ユーザー';
  }

  @override
  String get wrappedMinutes => '分';

  @override
  String get wrappedConversations => '会話';

  @override
  String get wrappedDaysActive => 'アクティブ日数';

  @override
  String get wrappedYouTalkedAbout => '話題にしたこと';

  @override
  String get wrappedActionItems => 'タスク';

  @override
  String get wrappedTasksCreated => '作成したタスク';

  @override
  String get wrappedCompleted => '完了';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate%の完了率';
  }

  @override
  String get wrappedYourTopDays => 'あなたのベストデイ';

  @override
  String get wrappedBestMoments => 'ベストモーメント';

  @override
  String get wrappedMyBuddies => '仲間たち';

  @override
  String get wrappedCouldntStopTalkingAbout => '話し続けたこと';

  @override
  String get wrappedShow => '番組';

  @override
  String get wrappedMovie => '映画';

  @override
  String get wrappedBook => '本';

  @override
  String get wrappedCelebrity => '有名人';

  @override
  String get wrappedFood => '食べ物';

  @override
  String get wrappedMovieRecs => '友達への映画おすすめ';

  @override
  String get wrappedBiggest => '最大の';

  @override
  String get wrappedStruggle => 'チャレンジ';

  @override
  String get wrappedButYouPushedThrough => 'でも乗り越えました 💪';

  @override
  String get wrappedWin => '勝利';

  @override
  String get wrappedYouDidIt => 'やりました！🎉';

  @override
  String get wrappedTopPhrases => 'トップ5フレーズ';

  @override
  String get wrappedMins => '分';

  @override
  String get wrappedConvos => '会話';

  @override
  String get wrappedDays => '日';

  @override
  String get wrappedMyBuddiesLabel => '仲間たち';

  @override
  String get wrappedObsessionsLabel => 'ハマったもの';

  @override
  String get wrappedStruggleLabel => 'チャレンジ';

  @override
  String get wrappedWinLabel => '勝利';

  @override
  String get wrappedTopPhrasesLabel => 'トップフレーズ';

  @override
  String get wrappedLetsHitRewind => 'あなたの';

  @override
  String get wrappedGenerateMyWrapped => 'Wrappedを生成';

  @override
  String get wrappedProcessingDefault => '処理中...';

  @override
  String get wrappedCreatingYourStory => 'あなたの\n2025年のストーリーを作成中...';

  @override
  String get wrappedSomethingWentWrong => '問題が\n発生しました';

  @override
  String get wrappedAnErrorOccurred => 'エラーが発生しました';

  @override
  String get wrappedTryAgain => '再試行';

  @override
  String get wrappedNoDataAvailable => 'データがありません';

  @override
  String get wrappedOmiLifeRecap => 'Omiライフまとめ';

  @override
  String get wrappedSwipeUpToBegin => '上にスワイプして開始';

  @override
  String get wrappedShareText => '私の2025年、Omiが記録 ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare => '共有に失敗しました。もう一度お試しください。';

  @override
  String get wrappedFailedToStartGeneration => '生成の開始に失敗しました。もう一度お試しください。';

  @override
  String get wrappedStarting => '開始中...';

  @override
  String get wrappedShare => '共有';

  @override
  String get wrappedShareYourWrapped => 'Wrappedを共有';

  @override
  String get wrappedMy2025 => '私の2025年';

  @override
  String get wrappedRememberedByOmi => 'Omiが記録';

  @override
  String get wrappedMostFunDay => '最も楽しい';

  @override
  String get wrappedMostProductiveDay => '最も生産的';

  @override
  String get wrappedMostIntenseDay => '最も濃密';

  @override
  String get wrappedFunniestMoment => '最も面白い';

  @override
  String get wrappedMostCringeMoment => '最も恥ずかしい';

  @override
  String get wrappedMinutesLabel => '分';

  @override
  String get wrappedConversationsLabel => '会話';

  @override
  String get wrappedDaysActiveLabel => 'アクティブ日数';

  @override
  String get wrappedTasksGenerated => 'タスク作成';

  @override
  String get wrappedTasksCompleted => 'タスク完了';

  @override
  String get wrappedTopFivePhrases => 'トップ5フレーズ';

  @override
  String get wrappedAGreatDay => '素晴らしい日';

  @override
  String get wrappedGettingItDone => 'やり遂げる';

  @override
  String get wrappedAChallenge => 'チャレンジ';

  @override
  String get wrappedAHilariousMoment => '面白い瞬間';

  @override
  String get wrappedThatAwkwardMoment => 'あの気まずい瞬間';

  @override
  String get wrappedYouHadFunnyMoments => '今年は面白い瞬間がありました！';

  @override
  String get wrappedWeveAllBeenThere => '誰もが経験すること！';

  @override
  String get wrappedFriend => '友達';

  @override
  String get wrappedYourBuddy => 'あなたの仲間！';

  @override
  String get wrappedNotMentioned => '言及なし';

  @override
  String get wrappedTheHardPart => '困難な部分';

  @override
  String get wrappedPersonalGrowth => '個人の成長';

  @override
  String get wrappedFunDay => '楽しい';

  @override
  String get wrappedProductiveDay => '生産的';

  @override
  String get wrappedIntenseDay => '濃密';

  @override
  String get wrappedFunnyMomentTitle => '面白い瞬間';

  @override
  String get wrappedCringeMomentTitle => '恥ずかしい瞬間';

  @override
  String get wrappedYouTalkedAboutBadge => '話した話題';

  @override
  String get wrappedCompletedLabel => '完了';

  @override
  String get wrappedMyBuddiesCard => '私の仲間';

  @override
  String get wrappedBuddiesLabel => '仲間';

  @override
  String get wrappedObsessionsLabelUpper => 'ハマったこと';

  @override
  String get wrappedStruggleLabelUpper => '困難';

  @override
  String get wrappedWinLabelUpper => '勝利';

  @override
  String get wrappedTopPhrasesLabelUpper => 'トップフレーズ';

  @override
  String get wrappedYourHeader => 'あなたの';

  @override
  String get wrappedTopDaysHeader => 'ベストデイ';

  @override
  String get wrappedYourTopDaysBadge => 'あなたのベストデイ';

  @override
  String get wrappedBestHeader => 'ベスト';

  @override
  String get wrappedMomentsHeader => '瞬間';

  @override
  String get wrappedBestMomentsBadge => 'ベストモーメント';

  @override
  String get wrappedBiggestHeader => '最大の';

  @override
  String get wrappedStruggleHeader => '困難';

  @override
  String get wrappedWinHeader => '勝利';

  @override
  String get wrappedButYouPushedThroughEmoji => 'でも乗り越えた 💪';

  @override
  String get wrappedYouDidItEmoji => 'やり遂げた！ 🎉';

  @override
  String get wrappedHours => '時間';

  @override
  String get wrappedActions => 'アクション';

  @override
  String get multipleSpeakersDetected => '複数の話者が検出されました';

  @override
  String get multipleSpeakersDescription => '録音に複数の話者がいるようです。静かな場所にいることを確認して、もう一度お試しください。';

  @override
  String get invalidRecordingDetected => '無効な録音が検出されました';

  @override
  String get notEnoughSpeechDescription => '十分な音声が検出されませんでした。もっと話して、もう一度お試しください。';

  @override
  String get speechDurationDescription => '少なくとも5秒以上、90秒以内で話してください。';

  @override
  String get connectionLostDescription => '接続が切断されました。インターネット接続を確認して、もう一度お試しください。';

  @override
  String get howToTakeGoodSample => '良いサンプルの取り方は？';

  @override
  String get goodSampleInstructions => '1. 静かな場所にいることを確認してください。\n2. 明確に自然に話してください。\n3. デバイスが首の自然な位置にあることを確認してください。\n\n作成後、いつでも改善したり、やり直したりできます。';

  @override
  String get noDeviceConnectedUseMic => '接続されているデバイスがありません。電話のマイクを使用します。';

  @override
  String get doItAgain => 'もう一度やる';

  @override
  String get listenToSpeechProfile => '私の音声プロフィールを聴く ➡️';

  @override
  String get recognizingOthers => '他の人を認識 👀';

  @override
  String get keepGoingGreat => '続けてください、素晴らしいです';

  @override
  String get somethingWentWrongTryAgain => 'エラーが発生しました！後でもう一度お試しください。';

  @override
  String get uploadingVoiceProfile => '音声プロファイルをアップロード中....';

  @override
  String get memorizingYourVoice => 'あなたの声を記憶中...';

  @override
  String get personalizingExperience => '体験をパーソナライズ中...';

  @override
  String get keepSpeakingUntil100 => '100%になるまで話し続けてください。';

  @override
  String get greatJobAlmostThere => '素晴らしい、もう少しです';

  @override
  String get soCloseJustLittleMore => 'あと少し';

  @override
  String get notificationFrequency => '通知頻度';

  @override
  String get controlNotificationFrequency => 'Omiがプロアクティブ通知を送信する頻度を制御します。';

  @override
  String get yourScore => 'あなたのスコア';

  @override
  String get dailyScoreBreakdown => 'デイリースコアの内訳';

  @override
  String get todaysScore => '今日のスコア';

  @override
  String get tasksCompleted => '完了したタスク';

  @override
  String get completionRate => '完了率';

  @override
  String get howItWorks => '仕組み';

  @override
  String get dailyScoreExplanation => 'デイリースコアはタスクの完了に基づいています。タスクを完了してスコアを向上させましょう！';

  @override
  String get notificationFrequencyDescription => 'Omiがプロアクティブな通知やリマインダーを送信する頻度を制御します。';

  @override
  String get sliderOff => 'オフ';

  @override
  String get sliderMax => '最大';

  @override
  String summaryGeneratedFor(String date) {
    return '$dateのサマリーを生成しました';
  }

  @override
  String get failedToGenerateSummary => 'サマリーの生成に失敗しました。その日の会話があることを確認してください。';

  @override
  String get recap => 'まとめ';

  @override
  String deleteQuoted(String name) {
    return '「$name」を削除';
  }

  @override
  String moveConversationsTo(int count) {
    return '$count件の会話を移動:';
  }

  @override
  String get noFolder => 'フォルダなし';

  @override
  String get removeFromAllFolders => 'すべてのフォルダから削除';

  @override
  String get buildAndShareYourCustomApp => 'カスタムアプリを作成して共有';

  @override
  String get searchAppsPlaceholder => '1500以上のアプリを検索';

  @override
  String get filters => 'フィルター';

  @override
  String get frequencyOff => 'オフ';

  @override
  String get frequencyMinimal => '最小限';

  @override
  String get frequencyLow => '低';

  @override
  String get frequencyBalanced => 'バランス';

  @override
  String get frequencyHigh => '高';

  @override
  String get frequencyMaximum => '最大';

  @override
  String get frequencyDescOff => 'プロアクティブな通知なし';

  @override
  String get frequencyDescMinimal => '重要なリマインダーのみ';

  @override
  String get frequencyDescLow => '重要な更新のみ';

  @override
  String get frequencyDescBalanced => '定期的な役立つリマインダー';

  @override
  String get frequencyDescHigh => '頻繁なチェックイン';

  @override
  String get frequencyDescMaximum => '常に関与し続ける';

  @override
  String get clearChatQuestion => 'チャットを削除しますか？';

  @override
  String get syncingMessages => 'サーバーとメッセージを同期中...';

  @override
  String get chatAppsTitle => 'チャットアプリ';

  @override
  String get selectApp => 'アプリを選択';

  @override
  String get noChatAppsEnabled => 'チャットアプリが有効になっていません。\n「アプリを有効化」をタップして追加してください。';

  @override
  String get disable => '無効化';

  @override
  String get photoLibrary => 'フォトライブラリ';

  @override
  String get chooseFile => 'ファイルを選択';

  @override
  String get configureAiPersona => 'AIペルソナを設定';

  @override
  String get connectAiAssistantsToYourData => 'AIアシスタントをデータに接続';

  @override
  String get oAuth => 'OAuth';

  @override
  String get trackYourGoalsOnHomepage => 'ホームページで個人の目標を追跡';

  @override
  String get deleteRecording => '録音を削除';

  @override
  String get thisCannotBeUndone => 'この操作は元に戻せません。';

  @override
  String get sdCard => 'SDカード';

  @override
  String get fromSd => 'SDから';

  @override
  String get limitless => 'Limitless';

  @override
  String get fastTransfer => '高速転送';

  @override
  String get syncingStatus => '同期中';

  @override
  String get failedStatus => '失敗';

  @override
  String etaLabel(String time) {
    return '予想時間: $time';
  }

  @override
  String get transferMethod => '転送方法';

  @override
  String get fast => '高速';

  @override
  String get ble => 'BLE';

  @override
  String get phone => '電話';

  @override
  String get cancelSync => '同期をキャンセル';

  @override
  String get cancelSyncMessage => '既にダウンロードされたデータは保存されます。後で続行できます。';

  @override
  String get syncCancelled => '同期がキャンセルされました';

  @override
  String get deleteProcessedFiles => '処理済みファイルを削除';

  @override
  String get processedFilesDeleted => '処理済みファイルを削除しました';

  @override
  String get wifiEnableFailed => 'デバイスでWiFiを有効にできませんでした。もう一度お試しください。';

  @override
  String get deviceNoFastTransfer => 'お使いのデバイスは高速転送に対応していません。Bluetoothをご使用ください。';

  @override
  String get enableHotspotMessage => '電話のホットスポットを有効にしてもう一度お試しください。';

  @override
  String get transferStartFailed => '転送を開始できませんでした。もう一度お試しください。';

  @override
  String get deviceNotResponding => 'デバイスが応答しません。もう一度お試しください。';

  @override
  String get invalidWifiCredentials => 'WiFi認証情報が無効です。ホットスポットの設定を確認してください。';

  @override
  String get wifiConnectionFailed => 'WiFi接続に失敗しました。もう一度お試しください。';

  @override
  String get sdCardProcessing => 'SDカード処理';

  @override
  String sdCardProcessingMessage(int count) {
    return '$count件の録音を処理中です。処理後、ファイルはSDカードから削除されます。';
  }

  @override
  String get process => '処理';

  @override
  String get wifiSyncFailed => 'WiFi同期に失敗しました';

  @override
  String get processingFailed => '処理に失敗しました';

  @override
  String get downloadingFromSdCard => 'SDカードからダウンロード中';

  @override
  String processingProgress(int current, int total) {
    return '処理中 $current/$total';
  }

  @override
  String conversationsCreated(int count) {
    return '$count件の会話を作成しました';
  }

  @override
  String get internetRequired => 'インターネット接続が必要です';

  @override
  String get processAudio => 'オーディオを処理';

  @override
  String get start => '開始';

  @override
  String get noRecordings => '録音なし';

  @override
  String get audioFromOmiWillAppearHere => 'Omiデバイスからのオーディオがここに表示されます';

  @override
  String get deleteProcessed => '処理済みを削除';

  @override
  String get tryDifferentFilter => '別のフィルターをお試しください';

  @override
  String get recordings => '録音';

  @override
  String get enableRemindersAccess => 'Apple リマインダーを使用するには、設定でリマインダーへのアクセスを有効にしてください';

  @override
  String todayAtTime(String time) {
    return '今日 $time';
  }

  @override
  String yesterdayAtTime(String time) {
    return '昨日 $time';
  }

  @override
  String get lessThanAMinute => '1分未満';

  @override
  String estimatedMinutes(int count) {
    return '約$count分';
  }

  @override
  String estimatedHours(int count) {
    return '約$count時間';
  }

  @override
  String estimatedTimeRemaining(String time) {
    return '推定残り時間: $time';
  }

  @override
  String get summarizingConversation => '会話を要約中...\n数秒かかる場合があります';

  @override
  String get resummarizingConversation => '会話を再要約中...\n数秒かかる場合があります';

  @override
  String get nothingInterestingRetry => '興味深い内容が見つかりませんでした。\n再試行しますか？';

  @override
  String get noSummaryForConversation => 'この会話の要約は\nありません。';

  @override
  String get unknownLocation => '不明な場所';

  @override
  String get couldNotLoadMap => 'マップを読み込めませんでした';

  @override
  String get triggerConversationIntegration => '会話作成統合をトリガー';

  @override
  String get webhookUrlNotSet => 'Webhook URLが設定されていません';

  @override
  String get setWebhookUrlInSettings => 'この機能を使用するには、開発者設定でwebhook URLを設定してください。';

  @override
  String get sendWebUrl => 'Web URLを送信';

  @override
  String get sendTranscript => '文字起こしを送信';

  @override
  String get sendSummary => '要約を送信';

  @override
  String get debugModeDetected => 'デバッグモードが検出されました';

  @override
  String get performanceReduced => 'パフォーマンスが低下する可能性があります';

  @override
  String autoClosingInSeconds(int seconds) {
    return '$seconds秒後に自動的に閉じます';
  }

  @override
  String get modelRequired => 'モデルが必要です';

  @override
  String get downloadWhisperModel => 'オンデバイス文字起こしを使用するにはwhisperモデルをダウンロードしてください';

  @override
  String get deviceNotCompatible => 'お使いのデバイスはオンデバイス文字起こしに対応していません';

  @override
  String get deviceRequirements => 'お使いのデバイスはオンデバイス文字起こしの要件を満たしていません。';

  @override
  String get willLikelyCrash => '有効にすると、アプリがクラッシュまたはフリーズする可能性があります。';

  @override
  String get transcriptionSlowerLessAccurate => '文字起こしは大幅に遅くなり、精度も低下します。';

  @override
  String get proceedAnyway => 'それでも続行';

  @override
  String get olderDeviceDetected => '古いデバイスが検出されました';

  @override
  String get onDeviceSlower => 'このデバイスではオンデバイス文字起こしが遅くなる場合があります。';

  @override
  String get batteryUsageHigher => 'バッテリー使用量はクラウド文字起こしより多くなります。';

  @override
  String get considerOmiCloud => 'パフォーマンス向上のためOmi Cloudの使用を検討してください。';

  @override
  String get highResourceUsage => '高いリソース使用量';

  @override
  String get onDeviceIntensive => 'オンデバイス文字起こしは計算負荷が高い処理です。';

  @override
  String get batteryDrainIncrease => 'バッテリー消費が大幅に増加します。';

  @override
  String get deviceMayWarmUp => '長時間の使用中にデバイスが熱くなる可能性があります。';

  @override
  String get speedAccuracyLower => '速度と精度がクラウドモデルより低くなる可能性があります。';

  @override
  String get cloudProvider => 'クラウドプロバイダー';

  @override
  String get premiumMinutesInfo => '月間1,200分のプレミアム利用可能。オンデバイスタブでは無制限の無料文字起こしが可能です。';

  @override
  String get viewUsage => '使用状況を表示';

  @override
  String get localProcessingInfo => '音声はローカルで処理されます。オフラインで動作し、よりプライベートですが、バッテリーを多く消費します。';

  @override
  String get model => 'モデル';

  @override
  String get performanceWarning => 'パフォーマンス警告';

  @override
  String get largeModelWarning => 'このモデルは大きいため、アプリがクラッシュしたり、モバイルデバイスで非常に遅く動作する可能性があります。\n\n「small」または「base」をお勧めします。';

  @override
  String get usingNativeIosSpeech => 'iOSネイティブ音声認識を使用';

  @override
  String get noModelDownloadRequired => 'デバイスのネイティブ音声エンジンが使用されます。モデルのダウンロードは不要です。';

  @override
  String get modelReady => 'モデル準備完了';

  @override
  String get redownload => '再ダウンロード';

  @override
  String get doNotCloseApp => 'アプリを閉じないでください。';

  @override
  String get downloading => 'ダウンロード中...';

  @override
  String get downloadModel => 'モデルをダウンロード';

  @override
  String estimatedSize(String size) {
    return '推定サイズ: 約$size MB';
  }

  @override
  String availableSpace(String space) {
    return '利用可能な容量: $space';
  }

  @override
  String get notEnoughSpace => '警告: 容量が不足しています！';

  @override
  String get download => 'ダウンロード';

  @override
  String downloadError(String error) {
    return 'ダウンロードエラー: $error';
  }

  @override
  String get cancelled => 'キャンセルされました';

  @override
  String get deviceNotCompatibleTitle => 'デバイスが対応していません';

  @override
  String get deviceNotMeetRequirements => 'お使いのデバイスはオンデバイス文字起こしの要件を満たしていません。';

  @override
  String get transcriptionSlowerOnDevice => 'このデバイスではオンデバイス文字起こしが遅くなる可能性があります。';

  @override
  String get computationallyIntensive => 'オンデバイス文字起こしは計算負荷が高いです。';

  @override
  String get batteryDrainSignificantly => 'バッテリー消費が大幅に増加します。';

  @override
  String get premiumMinutesMonth => '月間1,200プレミアム分。オンデバイスタブでは無制限の無料文字起こしを提供。';

  @override
  String get audioProcessedLocally => '音声はローカルで処理されます。オフラインで動作し、よりプライベートですが、バッテリー消費が増えます。';

  @override
  String get languageLabel => '言語';

  @override
  String get modelLabel => 'モデル';

  @override
  String get modelTooLargeWarning => 'このモデルは大きく、モバイルデバイスでアプリがクラッシュしたり非常に遅くなる可能性があります。\n\nsmallまたはbaseを推奨します。';

  @override
  String get nativeEngineNoDownload => 'デバイスのネイティブ音声エンジンが使用されます。モデルのダウンロードは不要です。';

  @override
  String modelReadyWithName(String model) {
    return 'モデル準備完了 ($model)';
  }

  @override
  String get reDownload => '再ダウンロード';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return '$modelをダウンロード中: $received / $total MB';
  }

  @override
  String preparingModel(String model) {
    return '$modelを準備中...';
  }

  @override
  String downloadErrorWithMessage(String error) {
    return 'ダウンロードエラー: $error';
  }

  @override
  String estimatedSizeWithValue(String size) {
    return '推定サイズ: 約$size MB';
  }

  @override
  String availableSpaceWithValue(String space) {
    return '利用可能な容量: $space';
  }

  @override
  String get omiTranscriptionOptimized => 'Omiの組み込みライブ文字起こしは、自動話者検出とダイアライゼーションによるリアルタイム会話に最適化されています。';

  @override
  String get reset => 'リセット';

  @override
  String get useTemplateFrom => 'テンプレートを使用';

  @override
  String get selectProviderTemplate => 'プロバイダーテンプレートを選択...';

  @override
  String get quicklyPopulateResponse => '既知のプロバイダー応答形式で素早く入力';

  @override
  String get quicklyPopulateRequest => '既知のプロバイダーリクエスト形式で素早く入力';

  @override
  String get invalidJsonError => '無効なJSON';

  @override
  String downloadModelWithName(String model) {
    return 'モデルをダウンロード ($model)';
  }

  @override
  String modelNameWithFile(String model) {
    return 'モデル: $model';
  }

  @override
  String get device => 'デバイス';

  @override
  String get chatAssistantsTitle => 'チャットアシスタント';

  @override
  String get permissionReadConversations => '会話を読む';

  @override
  String get permissionReadMemories => 'メモリーを読む';

  @override
  String get permissionReadTasks => 'タスクを読む';

  @override
  String get permissionCreateConversations => '会話を作成';

  @override
  String get permissionCreateMemories => 'メモリーを作成';

  @override
  String get permissionTypeAccess => 'アクセス';

  @override
  String get permissionTypeCreate => '作成';

  @override
  String get permissionTypeTrigger => 'トリガー';

  @override
  String get permissionDescReadConversations => 'このアプリはあなたの会話にアクセスできます。';

  @override
  String get permissionDescReadMemories => 'このアプリはあなたのメモリーにアクセスできます。';

  @override
  String get permissionDescReadTasks => 'このアプリはあなたのタスクにアクセスできます。';

  @override
  String get permissionDescCreateConversations => 'このアプリは新しい会話を作成できます。';

  @override
  String get permissionDescCreateMemories => 'このアプリは新しいメモリーを作成できます。';

  @override
  String get realtimeListening => 'リアルタイムリスニング';

  @override
  String get setupCompleted => '完了';

  @override
  String get pleaseSelectRating => '評価を選択してください';

  @override
  String get writeReviewOptional => 'レビューを書く（任意）';

  @override
  String get setupQuestionsIntro => 'いくつかの質問に答えて、Omiの改善にご協力ください。🫶 💜';

  @override
  String get setupQuestionProfession => '1. あなたのお仕事は何ですか？';

  @override
  String get setupQuestionUsage => '2. どこでOmiを使用する予定ですか？';

  @override
  String get setupQuestionAge => '3. あなたの年齢層は？';

  @override
  String get setupAnswerAllQuestions => 'まだすべての質問に回答していません！🥺';

  @override
  String get setupSkipHelp => 'スキップ、協力しません :C';

  @override
  String get professionEntrepreneur => '起業家';

  @override
  String get professionSoftwareEngineer => 'ソフトウェアエンジニア';

  @override
  String get professionProductManager => 'プロダクトマネージャー';

  @override
  String get professionExecutive => '経営者';

  @override
  String get professionSales => '営業';

  @override
  String get professionStudent => '学生';

  @override
  String get usageAtWork => '仕事中';

  @override
  String get usageIrlEvents => '対面イベント';

  @override
  String get usageOnline => 'オンラインで';

  @override
  String get usageSocialSettings => '社交の場';

  @override
  String get usageEverywhere => 'どこでも';

  @override
  String get customBackendUrlTitle => 'カスタムバックエンドURL';

  @override
  String get backendUrlLabel => 'バックエンドURL';

  @override
  String get saveUrlButton => 'URLを保存';

  @override
  String get enterBackendUrlError => 'バックエンドURLを入力してください';

  @override
  String get urlMustEndWithSlashError => 'URLは「/」で終わる必要があります';

  @override
  String get invalidUrlError => '有効なURLを入力してください';

  @override
  String get backendUrlSavedSuccess => 'バックエンドURLが保存されました！';

  @override
  String get signInTitle => 'サインイン';

  @override
  String get signInButton => 'サインイン';

  @override
  String get enterEmailError => 'メールアドレスを入力してください';

  @override
  String get invalidEmailError => '有効なメールアドレスを入力してください';

  @override
  String get enterPasswordError => 'パスワードを入力してください';

  @override
  String get passwordMinLengthError => 'パスワードは8文字以上である必要があります';

  @override
  String get signInSuccess => 'サインイン成功！';

  @override
  String get alreadyHaveAccountLogin => 'アカウントをお持ちですか？ログイン';

  @override
  String get emailLabel => 'メール';

  @override
  String get passwordLabel => 'パスワード';

  @override
  String get createAccountTitle => 'アカウント作成';

  @override
  String get nameLabel => '名前';

  @override
  String get repeatPasswordLabel => 'パスワードを再入力';

  @override
  String get signUpButton => '登録';

  @override
  String get enterNameError => '名前を入力してください';

  @override
  String get passwordsDoNotMatch => 'パスワードが一致しません';

  @override
  String get signUpSuccess => '登録成功！';

  @override
  String get loadingKnowledgeGraph => 'ナレッジグラフを読み込み中...';

  @override
  String get noKnowledgeGraphYet => 'ナレッジグラフはまだありません';

  @override
  String get buildingKnowledgeGraphFromMemories => '思い出からナレッジグラフを構築中...';

  @override
  String get knowledgeGraphWillBuildAutomatically => '新しい思い出を作成すると、ナレッジグラフが自動的に構築されます。';

  @override
  String get buildGraphButton => 'グラフを構築';

  @override
  String get checkOutMyMemoryGraph => '私のメモリーグラフをご覧ください！';

  @override
  String get getButton => '入手';

  @override
  String openingApp(String appName) {
    return '$appNameを開いています...';
  }

  @override
  String get writeSomething => '何か書いてください';

  @override
  String get submitReply => '返信を送信';

  @override
  String get editYourReply => '返信を編集';

  @override
  String get replyToReview => 'レビューに返信';

  @override
  String get rateAndReviewThisApp => 'このアプリを評価してレビューする';

  @override
  String get noChangesInReview => '更新するレビューの変更はありません。';

  @override
  String get cantRateWithoutInternet => 'インターネット接続なしではアプリを評価できません。';

  @override
  String get appAnalytics => 'アプリ分析';

  @override
  String get learnMoreLink => '詳細';

  @override
  String get moneyEarned => '収益';

  @override
  String get writeYourReply => '返信を入力...';

  @override
  String get replySentSuccessfully => '返信を送信しました';

  @override
  String failedToSendReply(String error) {
    return '返信の送信に失敗しました: $error';
  }

  @override
  String get send => '送信';

  @override
  String starFilter(int count) {
    return '$countつ星';
  }

  @override
  String get noReviewsFound => 'レビューが見つかりません';

  @override
  String get editReply => '返信を編集';

  @override
  String get reply => '返信';

  @override
  String starFilterLabel(int count) {
    return '$countつ星';
  }

  @override
  String get sharePublicLink => '公開リンクを共有';

  @override
  String get makePersonaPublic => 'ペルソナを公開';

  @override
  String get connectedKnowledgeData => '接続されたナレッジデータ';

  @override
  String get enterName => '名前を入力';

  @override
  String get disconnectTwitter => 'Twitterを切断';

  @override
  String get disconnectTwitterConfirmation => 'Twitterアカウントを切断してもよろしいですか？ペルソナはTwitterデータにアクセスできなくなります。';

  @override
  String get getOmiDeviceDescription => '個人の会話でより正確なクローンを作成';

  @override
  String get getOmi => 'Omiを入手';

  @override
  String get iHaveOmiDevice => 'Omiデバイスを持っています';

  @override
  String get goal => '目標';

  @override
  String get tapToTrackThisGoal => 'タップしてこの目標を追跡';

  @override
  String get tapToSetAGoal => 'タップして目標を設定';

  @override
  String get processedConversations => '処理済みの会話';

  @override
  String get updatedConversations => '更新された会話';

  @override
  String get newConversations => '新しい会話';

  @override
  String get summaryTemplate => '要約テンプレート';

  @override
  String get suggestedTemplates => 'おすすめのテンプレート';

  @override
  String get otherTemplates => 'その他のテンプレート';

  @override
  String get availableTemplates => '利用可能なテンプレート';

  @override
  String get getCreative => 'クリエイティブに';

  @override
  String get defaultLabel => 'デフォルト';

  @override
  String get lastUsedLabel => '最後に使用';

  @override
  String get setDefaultApp => 'デフォルトアプリを設定';

  @override
  String setDefaultAppContent(String appName) {
    return '$appNameをデフォルトの要約アプリとして設定しますか？\\n\\nこのアプリは今後のすべての会話の要約に自動的に使用されます。';
  }

  @override
  String get setDefaultButton => 'デフォルトに設定';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appNameがデフォルトの要約アプリとして設定されました';
  }

  @override
  String get createCustomTemplate => 'カスタムテンプレートを作成';

  @override
  String get allTemplates => 'すべてのテンプレート';

  @override
  String failedToInstallApp(String appName) {
    return '$appNameのインストールに失敗しました。もう一度お試しください。';
  }

  @override
  String errorInstallingApp(String appName, String error) {
    return '$appNameのインストール中にエラーが発生: $error';
  }

  @override
  String tagSpeaker(int speakerId) {
    return '話者 $speakerId にタグ付け';
  }

  @override
  String get personNameAlreadyExists => 'この名前の人物は既に存在します。';

  @override
  String get selectYouFromList => '自分にタグ付けするには、リストから「あなた」を選択してください。';

  @override
  String get enterPersonsName => '人物の名前を入力';

  @override
  String get addPerson => '人物を追加';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'この話者の他のセグメントにタグ付け ($selected/$total)';
  }

  @override
  String get tagOtherSegments => '他のセグメントにタグ付け';

  @override
  String get managePeople => '人物を管理';

  @override
  String get shareViaSms => 'SMSで共有';

  @override
  String get selectContactsToShareSummary => '会話の要約を共有する連絡先を選択';

  @override
  String get searchContactsHint => '連絡先を検索...';

  @override
  String contactsSelectedCount(int count) {
    return '$count件選択中';
  }

  @override
  String get clearAllSelection => 'すべて解除';

  @override
  String get selectContactsToShare => '共有する連絡先を選択';

  @override
  String shareWithContactCount(int count) {
    return '$count件の連絡先と共有';
  }

  @override
  String shareWithContactsCount(int count) {
    return '$count件の連絡先と共有';
  }

  @override
  String get contactsPermissionRequired => '連絡先へのアクセス許可が必要';

  @override
  String get contactsPermissionRequiredForSms => 'SMSで共有するには連絡先へのアクセス許可が必要です';

  @override
  String get grantContactsPermissionForSms => 'SMSで共有するには連絡先へのアクセスを許可してください';

  @override
  String get noContactsWithPhoneNumbers => '電話番号のある連絡先が見つかりません';

  @override
  String get noContactsMatchSearch => '検索に一致する連絡先がありません';

  @override
  String get failedToLoadContacts => '連絡先の読み込みに失敗しました';

  @override
  String get failedToPrepareConversationForSharing => '会話の共有準備に失敗しました。もう一度お試しください。';

  @override
  String get couldNotOpenSmsApp => 'SMSアプリを開けませんでした。もう一度お試しください。';

  @override
  String heresWhatWeDiscussed(String link) {
    return '先ほど話した内容はこちらです: $link';
  }

  @override
  String get wifiSync => 'WiFi同期';

  @override
  String itemCopiedToClipboard(String item) {
    return '$itemがクリップボードにコピーされました';
  }

  @override
  String get wifiConnectionFailedTitle => '接続に失敗しました';

  @override
  String connectingToDeviceName(String deviceName) {
    return '$deviceNameに接続中';
  }

  @override
  String enableDeviceWifi(String deviceName) {
    return '$deviceNameのWiFiを有効化';
  }

  @override
  String connectToDeviceName(String deviceName) {
    return '$deviceNameに接続';
  }

  @override
  String get recordingDetails => '録音の詳細';

  @override
  String get storageLocationSdCard => 'SDカード';

  @override
  String get storageLocationLimitlessPendant => 'Limitless Pendant';

  @override
  String get storageLocationPhone => '電話';

  @override
  String get storageLocationPhoneMemory => '電話（メモリ）';

  @override
  String storedOnDevice(String deviceName) {
    return '$deviceNameに保存';
  }

  @override
  String get transferring => '転送中...';

  @override
  String get transferRequired => '転送が必要です';

  @override
  String get downloadingAudioFromSdCard => 'デバイスのSDカードからオーディオをダウンロード中';

  @override
  String get transferRequiredDescription => 'この録音はデバイスのSDカードに保存されています。再生や共有するには電話に転送してください。';

  @override
  String get cancelTransfer => '転送をキャンセル';

  @override
  String get transferToPhone => '電話に転送';

  @override
  String get privateAndSecureOnDevice => 'デバイスで安全にプライベート保存';

  @override
  String get recordingInfo => '録音情報';

  @override
  String get transferInProgress => '転送中...';

  @override
  String get shareRecording => '録音を共有';

  @override
  String get deleteRecordingConfirmation => 'この録音を完全に削除してもよろしいですか？この操作は元に戻せません。';

  @override
  String get recordingIdLabel => '録音ID';

  @override
  String get dateTimeLabel => '日時';

  @override
  String get durationLabel => '再生時間';

  @override
  String get audioFormatLabel => 'オーディオ形式';

  @override
  String get storageLocationLabel => '保存場所';

  @override
  String get estimatedSizeLabel => '推定サイズ';

  @override
  String get deviceModelLabel => 'デバイスモデル';

  @override
  String get deviceIdLabel => 'デバイスID';

  @override
  String get statusLabel => 'Status';

  @override
  String get statusProcessed => '処理済み';

  @override
  String get statusUnprocessed => '未処理';

  @override
  String get switchedToFastTransfer => '高速転送に切り替えました';

  @override
  String get transferCompleteMessage => '転送完了！この録音を再生できます。';

  @override
  String transferFailedMessage(String error) {
    return '転送に失敗しました: $error';
  }

  @override
  String get transferCancelled => '転送がキャンセルされました';

  @override
  String get fastTransferEnabled => '高速転送が有効になりました';

  @override
  String get bluetoothSyncEnabled => 'Bluetooth同期が有効になりました';

  @override
  String get enableFastTransfer => '高速転送を有効にする';

  @override
  String get fastTransferDescription => '高速転送はWiFiを使用して約5倍の速度を実現します。転送中、電話は一時的にOmiデバイスのWiFiネットワークに接続されます。';

  @override
  String get internetAccessPausedDuringTransfer => '転送中はインターネットアクセスが一時停止されます';

  @override
  String get chooseTransferMethodDescription => 'Omiデバイスから電話への録音の転送方法を選択してください。';

  @override
  String get wifiSpeed => 'WiFi経由で約150 KB/s';

  @override
  String get fiveTimesFaster => '5倍高速';

  @override
  String get fastTransferMethodDescription => 'Omiデバイスへの直接WiFi接続を作成します。転送中、電話は通常のWiFiから一時的に切断されます。';

  @override
  String get bluetooth => 'Bluetooth';

  @override
  String get bleSpeed => 'BLE経由で約30 KB/s';

  @override
  String get bluetoothMethodDescription => '標準のBluetooth Low Energy接続を使用します。遅いですがWiFi接続に影響しません。';

  @override
  String get selected => '選択済み';

  @override
  String get selectOption => '選択';

  @override
  String get lowBatteryAlertTitle => 'バッテリー残量低下アラート';

  @override
  String get lowBatteryAlertBody => 'デバイスのバッテリーが少なくなっています。充電してください！🔋';

  @override
  String get deviceDisconnectedNotificationTitle => 'Omiデバイスが切断されました';

  @override
  String get deviceDisconnectedNotificationBody => 'Omiを引き続き使用するには再接続してください。';

  @override
  String get firmwareUpdateAvailable => 'ファームウェアアップデートが利用可能';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'Omiデバイスの新しいファームウェアアップデート（$version）が利用可能です。今すぐアップデートしますか？';
  }

  @override
  String get later => '後で';

  @override
  String get appDeletedSuccessfully => 'アプリが正常に削除されました';

  @override
  String get appDeleteFailed => 'アプリの削除に失敗しました。後でもう一度お試しください。';

  @override
  String get appVisibilityChangedSuccessfully => 'アプリの公開設定が正常に変更されました。反映まで数分かかる場合があります。';

  @override
  String get errorActivatingAppIntegration => 'アプリの有効化中にエラーが発生しました。連携アプリの場合は、設定が完了していることを確認してください。';

  @override
  String get errorUpdatingAppStatus => 'アプリのステータス更新中にエラーが発生しました。';

  @override
  String get calculatingETA => '計算中...';

  @override
  String aboutMinutesRemaining(int minutes) {
    return '残り約$minutes分';
  }

  @override
  String get aboutAMinuteRemaining => '残り約1分';

  @override
  String get almostDone => 'もうすぐ完了...';

  @override
  String get omiSays => 'omiより';

  @override
  String get analyzingYourData => 'データを分析中...';

  @override
  String migratingToProtection(String level) {
    return '$level保護に移行中...';
  }

  @override
  String get noDataToMigrateFinalizing => '移行するデータがありません。完了処理中...';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return '$itemTypeを移行中... $percentage%';
  }

  @override
  String get allObjectsMigratedFinalizing => 'すべてのオブジェクトを移行しました。完了処理中...';

  @override
  String get migrationErrorOccurred => '移行中にエラーが発生しました。もう一度お試しください。';

  @override
  String get migrationComplete => '移行が完了しました！';

  @override
  String dataProtectedWithSettings(String level) {
    return 'データは新しい$level設定で保護されました。';
  }

  @override
  String get chatsLowercase => 'chats';

  @override
  String get dataLowercase => 'データ';

  @override
  String get fallNotificationTitle => 'おっと';

  @override
  String get fallNotificationBody => '転倒しましたか？';

  @override
  String get importantConversationTitle => '重要な会話';

  @override
  String get importantConversationBody => '重要な会話がありました。タップして要約を共有しましょう。';

  @override
  String get templateName => 'テンプレート名';

  @override
  String get templateNameHint => '例: 会議アクション項目抽出';

  @override
  String get nameMustBeAtLeast3Characters => '名前は3文字以上である必要があります';

  @override
  String get conversationPromptHint => '例：会話からアクションアイテム、決定事項、重要なポイントを抽出します。';

  @override
  String get pleaseEnterAppPrompt => 'アプリのプロンプトを入力してください';

  @override
  String get promptMustBeAtLeast10Characters => 'プロンプトは10文字以上である必要があります';

  @override
  String get anyoneCanDiscoverTemplate => '誰でもテンプレートを見つけられます';

  @override
  String get onlyYouCanUseTemplate => 'このテンプレートを使用できるのはあなただけです';

  @override
  String get generatingDescription => '説明を生成中...';

  @override
  String get creatingAppIcon => 'アプリアイコンを作成中...';

  @override
  String get installingApp => 'アプリをインストール中...';

  @override
  String get appCreatedAndInstalled => 'アプリが作成・インストールされました！';

  @override
  String get appCreatedSuccessfully => 'アプリが正常に作成されました！';

  @override
  String get failedToCreateApp => 'アプリの作成に失敗しました。もう一度お試しください。';

  @override
  String get addAppSelectCoreCapability => 'アプリのコア機能をもう1つ選択してください';

  @override
  String get addAppSelectPaymentPlan => '支払いプランを選択し、アプリの価格を入力してください';

  @override
  String get addAppSelectCapability => 'アプリの機能を少なくとも1つ選択してください';

  @override
  String get addAppSelectLogo => 'アプリのロゴを選択してください';

  @override
  String get addAppEnterChatPrompt => 'アプリのチャットプロンプトを入力してください';

  @override
  String get addAppEnterConversationPrompt => 'アプリの会話プロンプトを入力してください';

  @override
  String get addAppSelectTriggerEvent => 'アプリのトリガーイベントを選択してください';

  @override
  String get addAppEnterWebhookUrl => 'アプリのWebhook URLを入力してください';

  @override
  String get addAppSelectCategory => 'アプリのカテゴリを選択してください';

  @override
  String get addAppFillRequiredFields => '必須項目をすべて正しく入力してください';

  @override
  String get addAppUpdatedSuccess => 'アプリが正常に更新されました 🚀';

  @override
  String get addAppUpdateFailed => '更新に失敗しました。後でもう一度お試しください';

  @override
  String get addAppSubmittedSuccess => 'アプリが正常に送信されました 🚀';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'ファイル選択エラー: $message';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return '画像選択エラー: $error';
  }

  @override
  String get addAppPhotosPermissionDenied => '写真へのアクセスが拒否されました。写真へのアクセスを許可してください';

  @override
  String get addAppErrorSelectingImageRetry => '画像選択エラー。もう一度お試しください。';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'サムネイル選択エラー: $error';
  }

  @override
  String get addAppErrorSelectingThumbnailRetry => 'サムネイル選択エラー。もう一度お試しください。';

  @override
  String get addAppCapabilityConflictWithPersona => 'ペルソナと他の機能を同時に選択することはできません';

  @override
  String get addAppPersonaConflictWithCapabilities => 'ペルソナは他の機能と同時に選択できません';

  @override
  String get personaTwitterHandleNotFound => 'Twitterハンドルが見つかりません';

  @override
  String get personaTwitterHandleSuspended => 'Twitterハンドルは停止されています';

  @override
  String get personaFailedToVerifyTwitter => 'Twitterハンドルの確認に失敗しました';

  @override
  String get personaFailedToFetch => 'ペルソナの取得に失敗しました';

  @override
  String get personaFailedToCreate => 'ペルソナの作成に失敗しました';

  @override
  String get personaConnectKnowledgeSource => '少なくとも1つのデータソース（OmiまたはTwitter）を接続してください';

  @override
  String get personaUpdatedSuccessfully => 'ペルソナが正常に更新されました';

  @override
  String get personaFailedToUpdate => 'ペルソナの更新に失敗しました';

  @override
  String get personaPleaseSelectImage => '画像を選択してください';

  @override
  String get personaFailedToCreateTryLater => 'ペルソナの作成に失敗しました。後でもう一度お試しください。';

  @override
  String personaFailedToCreateWithError(String error) {
    return 'ペルソナの作成に失敗: $error';
  }

  @override
  String get personaFailedToEnable => 'ペルソナの有効化に失敗しました';

  @override
  String personaErrorEnablingWithError(String error) {
    return 'ペルソナの有効化エラー: $error';
  }

  @override
  String get paymentFailedToFetchCountries => '対応国の取得に失敗しました。後でもう一度お試しください。';

  @override
  String get paymentFailedToSetDefault => 'デフォルトの支払い方法の設定に失敗しました。後でもう一度お試しください。';

  @override
  String get paymentFailedToSavePaypal => 'PayPal詳細の保存に失敗しました。後でもう一度お試しください。';

  @override
  String get paypalEmailHint => 'nik@example.com';

  @override
  String get paypalMeLinkHint => 'paypal.me/nik';

  @override
  String get paymentMethodStripe => 'Stripe';

  @override
  String get paymentMethodPayPal => 'PayPal';

  @override
  String get paymentStatusActive => 'アクティブ';

  @override
  String get paymentStatusConnected => '接続済み';

  @override
  String get paymentStatusNotConnected => '未接続';

  @override
  String get paymentAppCost => 'アプリ料金';

  @override
  String get paymentEnterValidAmount => '有効な金額を入力してください';

  @override
  String get paymentEnterAmountGreaterThanZero => '0より大きい金額を入力してください';

  @override
  String get paymentPlan => '支払いプラン';

  @override
  String get paymentNoneSelected => '未選択';

  @override
  String get aiGenPleaseEnterDescription => 'アプリの説明を入力してください';

  @override
  String get aiGenCreatingAppIcon => 'アプリアイコンを作成中...';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'エラーが発生しました: $message';
  }

  @override
  String get aiGenAppCreatedSuccessfully => 'アプリが正常に作成されました！';

  @override
  String get aiGenFailedToCreateApp => 'アプリの作成に失敗しました';

  @override
  String get aiGenErrorWhileCreatingApp => 'アプリの作成中にエラーが発生しました';

  @override
  String get aiGenFailedToGenerateApp => 'アプリの生成に失敗しました。もう一度お試しください。';

  @override
  String get aiGenFailedToRegenerateIcon => 'アイコンの再生成に失敗しました';

  @override
  String get aiGenPleaseGenerateAppFirst => '先にアプリを生成してください';

  @override
  String get xHandleTitle => 'Xのユーザー名は？';

  @override
  String get xHandleDescription => 'アカウントのアクティビティに基づいて\nOmiクローンを事前トレーニングします';

  @override
  String get xHandleHint => '@nikshevchenko';

  @override
  String get xHandlePleaseEnter => 'Xのユーザー名を入力してください';

  @override
  String get xHandlePleaseEnterValid => '有効なXのユーザー名を入力してください';

  @override
  String get nextButton => '次へ';

  @override
  String get connectOmiDevice => 'Omiデバイスを接続';

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return '無制限プランを$titleに変更します。続行してもよろしいですか？';
  }

  @override
  String get planUpgradeScheduledMessage => 'アップグレードが予約されました！月額プランは請求期間の終了まで継続し、その後自動的に年額に変更されます。';

  @override
  String get couldNotSchedulePlanChange => 'プラン変更を予約できませんでした。もう一度お試しください。';

  @override
  String get subscriptionReactivatedDefault => 'サブスクリプションが再開されました！今すぐ請求はありません - 現在の期間の終了時に請求されます。';

  @override
  String get subscriptionSuccessfulCharged => 'サブスクリプションが成功しました！新しい請求期間分が請求されました。';

  @override
  String get couldNotProcessSubscription => 'サブスクリプションを処理できませんでした。もう一度お試しください。';

  @override
  String get couldNotLaunchUpgradePage => 'アップグレードページを開けませんでした。もう一度お試しください。';

  @override
  String get transcriptionJsonPlaceholder => 'JSON設定をここに貼り付け...';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get pricePlaceholder => '0.00';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'ファイルピッカーを開く際にエラーが発生しました: $message';
  }

  @override
  String importErrorGeneric(String error) {
    return 'エラー: $error';
  }

  @override
  String get mergeConversationsSuccessTitle => '会話が正常にマージされました';

  @override
  String mergeConversationsSuccessBody(int count) {
    return '$count件の会話が正常にマージされました';
  }

  @override
  String get dailyReflectionNotificationTitle => 'デイリー振り返りの時間です';

  @override
  String get dailyReflectionNotificationBody => '今日のことを教えてください';

  @override
  String get actionItemReminderTitle => 'Omiリマインダー';

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceNameが切断されました';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return '$deviceNameを引き続きご使用いただくには、再接続してください。';
  }

  @override
  String get onboardingSignIn => 'サインイン';

  @override
  String get onboardingYourName => 'あなたの名前';

  @override
  String get onboardingLanguage => '言語';

  @override
  String get onboardingPermissions => '権限';

  @override
  String get onboardingComplete => '完了';

  @override
  String get onboardingWelcomeToOmi => 'Omiへようこそ';

  @override
  String get onboardingTellUsAboutYourself => '自己紹介してください';

  @override
  String get onboardingChooseYourPreference => 'お好みを選択してください';

  @override
  String get onboardingGrantRequiredAccess => '必要なアクセスを許可';

  @override
  String get onboardingYoureAllSet => '準備完了です';

  @override
  String get searchTranscriptOrSummary => '文字起こしまたは要約を検索...';

  @override
  String get myGoal => '私の目標';

  @override
  String get appNotAvailable => 'おっと！お探しのアプリは利用できないようです。';

  @override
  String get failedToConnectTodoist => 'Todoistへの接続に失敗しました';

  @override
  String get failedToConnectAsana => 'Asanaへの接続に失敗しました';

  @override
  String get failedToConnectGoogleTasks => 'Google Tasksへの接続に失敗しました';

  @override
  String get failedToConnectClickUp => 'ClickUpへの接続に失敗しました';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return '$serviceNameへの接続に失敗しました: $error';
  }

  @override
  String get successfullyConnectedTodoist => 'Todoistに正常に接続されました！';

  @override
  String get failedToConnectTodoistRetry => 'Todoistへの接続に失敗しました。もう一度お試しください。';

  @override
  String get successfullyConnectedAsana => 'Asanaに正常に接続されました！';

  @override
  String get failedToConnectAsanaRetry => 'Asanaへの接続に失敗しました。もう一度お試しください。';

  @override
  String get successfullyConnectedGoogleTasks => 'Google Tasksに正常に接続されました！';

  @override
  String get failedToConnectGoogleTasksRetry => 'Google Tasksへの接続に失敗しました。もう一度お試しください。';

  @override
  String get successfullyConnectedClickUp => 'ClickUpに正常に接続されました！';

  @override
  String get failedToConnectClickUpRetry => 'ClickUpへの接続に失敗しました。もう一度お試しください。';

  @override
  String get successfullyConnectedNotion => 'Notionに正常に接続されました！';

  @override
  String get failedToRefreshNotionStatus => 'Notionの接続状態の更新に失敗しました。';

  @override
  String get successfullyConnectedGoogle => 'Googleに正常に接続されました！';

  @override
  String get failedToRefreshGoogleStatus => 'Googleの接続状態の更新に失敗しました。';

  @override
  String get successfullyConnectedWhoop => 'Whoopに正常に接続されました！';

  @override
  String get failedToRefreshWhoopStatus => 'Whoopの接続状態の更新に失敗しました。';

  @override
  String get successfullyConnectedGitHub => 'GitHubに正常に接続されました！';

  @override
  String get failedToRefreshGitHubStatus => 'GitHubの接続状態の更新に失敗しました。';

  @override
  String get authFailedToSignInWithGoogle => 'Googleでのサインインに失敗しました。もう一度お試しください。';

  @override
  String get authenticationFailed => '認証に失敗しました。もう一度お試しください。';

  @override
  String get authFailedToSignInWithApple => 'Appleでのサインインに失敗しました。もう一度お試しください。';

  @override
  String get authFailedToRetrieveToken => 'Firebaseトークンの取得に失敗しました。もう一度お試しください。';

  @override
  String get authUnexpectedErrorFirebase => 'サインイン中に予期しないエラーが発生しました。Firebaseエラー、もう一度お試しください。';

  @override
  String get authUnexpectedError => 'サインイン中に予期しないエラーが発生しました。もう一度お試しください';

  @override
  String get authFailedToLinkGoogle => 'Googleとの連携に失敗しました。もう一度お試しください。';

  @override
  String get authFailedToLinkApple => 'Appleとの連携に失敗しました。もう一度お試しください。';

  @override
  String get onboardingBluetoothRequired => 'デバイスに接続するにはBluetooth権限が必要です。';

  @override
  String get onboardingBluetoothDeniedSystemPrefs => 'Bluetooth権限が拒否されました。システム環境設定で権限を許可してください。';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'Bluetooth権限の状態：$status。システム環境設定を確認してください。';
  }

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'Bluetooth権限の確認に失敗しました：$error';
  }

  @override
  String get onboardingNotificationDeniedSystemPrefs => '通知権限が拒否されました。システム環境設定で権限を許可してください。';

  @override
  String get onboardingNotificationDeniedNotifications => '通知権限が拒否されました。システム環境設定 > 通知で権限を許可してください。';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return '通知権限の状態：$status。システム環境設定を確認してください。';
  }

  @override
  String onboardingFailedCheckNotification(String error) {
    return '通知権限の確認に失敗しました：$error';
  }

  @override
  String get onboardingLocationGrantInSettings => '設定 > プライバシーとセキュリティ > 位置情報サービスで位置情報の権限を許可してください';

  @override
  String get onboardingMicrophoneRequired => '録音にはマイク権限が必要です。';

  @override
  String get onboardingMicrophoneDenied => 'マイク権限が拒否されました。システム環境設定 > プライバシーとセキュリティ > マイクで権限を許可してください。';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'マイク権限の状態：$status。システム環境設定を確認してください。';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'マイク権限の確認に失敗しました：$error';
  }

  @override
  String get onboardingScreenCaptureRequired => 'システムオーディオの録音には画面キャプチャ権限が必要です。';

  @override
  String get onboardingScreenCaptureDenied => '画面キャプチャ権限が拒否されました。システム環境設定 > プライバシーとセキュリティ > 画面収録で権限を許可してください。';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return '画面キャプチャ権限の状態：$status。システム環境設定を確認してください。';
  }

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return '画面キャプチャ権限の確認に失敗しました：$error';
  }

  @override
  String get onboardingAccessibilityRequired => 'ブラウザミーティングを検出するにはアクセシビリティ権限が必要です。';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'アクセシビリティ権限の状態：$status。システム環境設定を確認してください。';
  }

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'アクセシビリティ権限の確認に失敗しました：$error';
  }

  @override
  String get msgCameraNotAvailable => 'このプラットフォームではカメラキャプチャは利用できません';

  @override
  String get msgCameraPermissionDenied => 'カメラの許可が拒否されました。カメラへのアクセスを許可してください';

  @override
  String msgCameraAccessError(String error) {
    return 'カメラへのアクセスエラー: $error';
  }

  @override
  String get msgPhotoError => '写真の撮影エラー。もう一度お試しください。';

  @override
  String get msgMaxImagesLimit => '選択できる画像は最大4枚です';

  @override
  String msgFilePickerError(String error) {
    return 'ファイルピッカーを開くエラー: $error';
  }

  @override
  String msgSelectImagesError(String error) {
    return '画像の選択エラー: $error';
  }

  @override
  String get msgPhotosPermissionDenied => '写真の許可が拒否されました。画像を選択するには写真へのアクセスを許可してください';

  @override
  String get msgSelectImagesGenericError => '画像の選択エラー。もう一度お試しください。';

  @override
  String get msgMaxFilesLimit => '選択できるファイルは最大4つです';

  @override
  String msgSelectFilesError(String error) {
    return 'ファイルの選択エラー: $error';
  }

  @override
  String get msgSelectFilesGenericError => 'ファイルの選択エラー。もう一度お試しください。';

  @override
  String get msgUploadFileFailed => 'ファイルのアップロードに失敗しました。後でもう一度お試しください';

  @override
  String get msgReadingMemories => '思い出を読み込んでいます...';

  @override
  String get msgLearningMemories => '思い出から学習しています...';

  @override
  String get msgUploadAttachedFileFailed => '添付ファイルのアップロードに失敗しました。';

  @override
  String captureRecordingError(String error) {
    return '録音中にエラーが発生しました: $error';
  }

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return '録画が停止しました: $reason。外部ディスプレイを再接続するか、録画を再開する必要があるかもしれません。';
  }

  @override
  String get captureMicrophonePermissionRequired => 'マイクの許可が必要です';

  @override
  String get captureMicrophonePermissionInSystemPreferences => 'システム環境設定でマイクの許可を与えてください';

  @override
  String get captureScreenRecordingPermissionRequired => '画面録画の許可が必要です';

  @override
  String get captureDisplayDetectionFailed => 'ディスプレイの検出に失敗しました。録画を停止しました。';

  @override
  String get devModeInvalidAudioBytesWebhookUrl => 'オーディオバイトのWebhook URLが無効です';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl => 'リアルタイム文字起こしのWebhook URLが無効です';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl => '会話作成のWebhook URLが無効です';

  @override
  String get devModeInvalidDaySummaryWebhookUrl => '日次サマリーのWebhook URLが無効です';

  @override
  String get devModeSettingsSaved => '設定を保存しました！';

  @override
  String get voiceFailedToTranscribe => '音声の文字起こしに失敗しました';

  @override
  String get locationPermissionRequired => '位置情報の許可が必要です';

  @override
  String get locationPermissionContent => '高速転送にはWiFi接続を確認するために位置情報の許可が必要です。続行するには位置情報の許可を付与してください。';

  @override
  String get pdfTranscriptExport => '文字起こしエクスポート';

  @override
  String get pdfConversationExport => '会話エクスポート';

  @override
  String pdfTitleLabel(String title) {
    return 'タイトル: $title';
  }

  @override
  String get conversationNewIndicator => '新規 🚀';

  @override
  String conversationPhotosCount(int count) {
    return '$count枚の写真';
  }

  @override
  String get mergingStatus => '統合中...';

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
    return '$count分';
  }

  @override
  String timeMinsPlural(int count) {
    return '$count分';
  }

  @override
  String timeMinsAndSecs(int mins, int secs) {
    return '$mins分$secs秒';
  }

  @override
  String timeHourSingular(int count) {
    return '$count時間';
  }

  @override
  String timeHoursPlural(int count) {
    return '$count時間';
  }

  @override
  String timeHoursAndMins(int hours, int mins) {
    return '$hours時間$mins分';
  }

  @override
  String timeDaySingular(int count) {
    return '$count日';
  }

  @override
  String timeDaysPlural(int count) {
    return '$count日';
  }

  @override
  String timeDaysAndHours(int days, int hours) {
    return '$days日$hours時間';
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
    return '$count時';
  }

  @override
  String timeCompactHoursAndMins(int hours, int mins) {
    return '$hours時$mins分';
  }

  @override
  String get moveToFolder => 'フォルダに移動';

  @override
  String get noFoldersAvailable => '利用可能なフォルダがありません';

  @override
  String get newFolder => '新しいフォルダ';

  @override
  String get color => '色';

  @override
  String get waitingForDevice => 'デバイスを待機中...';

  @override
  String get saySomething => '何か話してください...';

  @override
  String get initialisingSystemAudio => 'システムオーディオを初期化中';

  @override
  String get stopRecording => '録音を停止';

  @override
  String get continueRecording => '録音を続ける';

  @override
  String get initialisingRecorder => 'レコーダーを初期化中';

  @override
  String get pauseRecording => '録音を一時停止';

  @override
  String get resumeRecording => '録音を再開';

  @override
  String get noDailyRecapsYet => 'まだ日次サマリーはありません';

  @override
  String get dailyRecapsDescription => '日次サマリーは生成されるとここに表示されます';

  @override
  String get chooseTransferMethod => '転送方法を選択';

  @override
  String get fastTransferSpeed => 'WiFi経由で約150 KB/s';
}
