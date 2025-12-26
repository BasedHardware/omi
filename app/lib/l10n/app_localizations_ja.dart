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
  String get doubleTapActionDesc => 'ダブルタップ時の動作を選択';

  @override
  String get endAndProcess => '終了して会話を処理';

  @override
  String get pauseResumeRecording => '録音の一時停止/再開';

  @override
  String get starOngoing => '進行中の会話にスターを付ける';

  @override
  String get starOngoingDesc => '会話終了時にスターを付けるようにマーク';

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
  String get conversationTimeout => '会話タイムアウト';

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
  String get basicPlan => 'ベーシックプラン';

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
  String get clear => '消去';

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
}
