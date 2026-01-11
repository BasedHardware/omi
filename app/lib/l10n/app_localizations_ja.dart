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
  String get clear => '消去';

  @override
  String get copyTranscript => 'トランスクリプトをコピー';

  @override
  String get copySummary => 'サマリーをコピー';

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
  String get noInternetConnection => 'インターネット接続を確認して、もう一度お試しください。';

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
  String get speechProfile => '音声プロフィール';

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
  String get askOmi => 'Omiに聞く';

  @override
  String get done => '完了';

  @override
  String get disconnected => '切断済み';

  @override
  String get searching => '検索中';

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
  String get noConversationsYet => 'まだ会話がありません。';

  @override
  String get noStarredConversations => 'スター付きの会話はまだありません。';

  @override
  String get starConversationHint => '会話をスターするには、会話を開いてヘッダーのスターアイコンをタップしてください。';

  @override
  String get searchConversations => '会話を検索';

  @override
  String selectedCount(int count) {
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
  String get deletingMessages => 'Omiのメモリからメッセージを削除中...';

  @override
  String get messageCopied => 'メッセージをクリップボードにコピーしました。';

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
  String get clearChat => 'チャットを消去しますか？';

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
  String get createYourOwnApp => '自分のアプリを作成';

  @override
  String get buildAndShareApp => 'カスタムアプリを作成して共有';

  @override
  String get searchApps => '1500以上のアプリを検索';

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
  String get helpOrInquiries => 'ヘルプまたはお問い合わせ';

  @override
  String get joinCommunity => 'コミュニティに参加！';

  @override
  String get membersAndCounting => '8000人以上のメンバーが参加中。';

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
  String get paymentMethods => 'お支払い方法';

  @override
  String get conversationDisplay => '会話の表示';

  @override
  String get dataPrivacy => 'データとプライバシー';

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
  String get signOut => 'ログアウト';

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
  String get disconnectDevice => 'デバイスを切断';

  @override
  String get unpairDevice => 'デバイスのペアリング解除';

  @override
  String get unpairAndForget => 'ペアリング解除してデバイスを忘れる';

  @override
  String get deviceDisconnectedMessage => 'Omiが切断されました 😔';

  @override
  String get deviceUnpairedMessage => 'デバイスのペアリングが解除されました。設定 > Bluetoothに移動してデバイスを忘れて、ペアリング解除を完了してください。';

  @override
  String get unpairDialogTitle => 'デバイスのペアリング解除';

  @override
  String get unpairDialogMessage =>
      'これにより、デバイスのペアリングが解除され、別の電話に接続できるようになります。プロセスを完了するには、設定 > Bluetoothに移動してデバイスを忘れる必要があります。';

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
  String get off => 'オフ';

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
  String get upgradeToUnlimited => '無制限プランにアップグレード';

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
  String get deleteKnowledgeGraphMessage =>
      'これにより、派生したすべてのナレッジグラフデータ（ノードと接続）が削除されます。元の記憶は安全なままです。グラフは時間の経過とともに、または次のリクエスト時に再構築されます。';

  @override
  String get knowledgeGraphDeleted => 'ナレッジグラフが正常に削除されました';

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
  String get daySummary => 'その日の要約';

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
  String get insights => 'インサイト';

  @override
  String get memories => '記憶';

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
  String get enterYourName => '名前を入力';

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
  String get noUpcomingMeetings => '今後のミーティングはありません';

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
  String deviceUsesCodec(String deviceName, String codecReason) {
    return '$deviceNameは$codecReasonを使用しています。Omiが使用されます。';
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
  String get dontShowAgain => '今後表示しない';

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
  String get speechProfileIntro => 'Omiはあなたの目標と声を学習する必要があります。後から変更することもできます。';

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
  String get whatsYourName => 'お名前は？';

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
  String get needMicrophonePermission =>
      'マイクの許可が必要です。\n\n1. 「許可する」をタップ\n2. iPhoneで許可を選択\n3. Watchアプリが閉じます\n4. 再度開いて「続ける」をタップ';

  @override
  String get grantPermissionButton => '許可する';

  @override
  String get needHelp => 'ヘルプ';

  @override
  String get troubleshootingSteps =>
      'トラブルシューティング：\n\n1. WatchにOmiがインストールされているか確認\n2. WatchでOmiアプリを開く\n3. 許可のポップアップを探す\n4. 「許可」をタップ\n5. Watchアプリが閉じたら再度開く\n6. iPhoneに戻り「続ける」をタップ';

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
  String get personalGrowthJourney => 'あなたの言葉すべてに耳を傾けるAIと共に、個人の成長の旅へ。';

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
  String get deleteActionItemTitle => 'アクションアイテムの削除';

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
  String searchMemories(int count) {
    return '$count 件のメモリを検索';
  }

  @override
  String get memoryDeleted => 'メモリを削除しました';

  @override
  String get undo => '元に戻す';

  @override
  String get noMemoriesYet => 'メモリはまだありません';

  @override
  String get noAutoMemories => '自動メモリはまだありません';

  @override
  String get noManualMemories => '手動メモリはまだありません';

  @override
  String get noMemoriesInCategories => 'このカテゴリのメモリはありません';

  @override
  String get noMemoriesFound => 'メモリが見つかりません';

  @override
  String get addFirstMemory => '最初のメモリを追加';

  @override
  String get clearMemoryTitle => 'Omiのメモリを消去';

  @override
  String get clearMemoryMessage => 'Omiのメモリを消去してもよろしいですか？この操作は取り消せません。';

  @override
  String get clearMemoryButton => 'メモリを消去';

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
  String get newMemory => '新しいメモリ';

  @override
  String get editMemory => 'メモリを編集';

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
  String get filterSystem => 'About You';

  @override
  String get filterInteresting => 'Insights';

  @override
  String get filterManual => '手動';

  @override
  String get completed => '完了';

  @override
  String get markComplete => '完了としてマーク';

  @override
  String get actionItemDeleted => 'アクションアイテムを削除しました';

  @override
  String get failedToDeleteActionItem => 'アクションアイテムの削除に失敗しました';

  @override
  String get deleteActionItemConfirmTitle => 'アクションアイテムの削除';

  @override
  String get deleteActionItemConfirmMessage => 'このアクションアイテムを削除してもよろしいですか？';

  @override
  String get appLanguage => 'アプリ言語';
}
