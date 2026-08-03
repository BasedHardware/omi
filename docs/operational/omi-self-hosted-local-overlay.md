# Omi self-hosted local overlay

この文書は個人端末用のローカルoverlay契約であり、秘密値や署名ファイルをrepositoryへ保存しない。

- Firebase project選択、`GoogleService-Info.plist`、`google-services.json` は既存のdev/prod tracked設定を置換しない。
- iOS signing、personal entitlements、provisioning profileはローカルのXcode/CI secret管理だけに置く。
- Worker URL/tokenは `--dart-define` またはローカルの安全なビルド注入だけに置く。配布バイナリから抽出可能なtokenを長期credentialとして使わない。
- 追跡対象に追加するのは設定キーの契約とテストのみで、値・bundle id・チームID・証明書・entitlementの実体は含めない。

実機overlayの準備、Worker認証、デプロイはこのrepositoryのテスト成功と別の証拠として扱う。

## Current Cloudflare transcript slice boundary

- このPRはCloudflare Workerのread-only transcript一覧・詳細と、将来のWAL接続のno-op boundaryだけを扱う。
- 音声upload、chunk/finalize、ack、ローカルWAL削除、新base iPhone E2Eは後続sliceであり、この文書または本PRのテスト成功から完了を主張しない。
- 旧スパイクの端末/Worker成功は新baseの証拠ではない。新baseで同じ実機経路を再実行するまで `未確認` とする。

## Release and operations owner

Owner: local self-host operator

このPRは配布やWorker deployを自動実行しない。ownerは以下のrelease note、rollout、rollback、observability境界を確認し、ローカルoverlayを有効にする端末ごとに判断する。

### Release note

- 追加対象はopt-inのCloudflare transcript一覧・詳細のread-only表示と、将来のWAL接続に備えたno-op boundaryだけである。
- `BRAINBASE_SELF_HOSTED_WORKER_URL` またはtokenのdart-defineを渡さなければ機能は無効で、既存Omi会話を変えず、Cloudflare read request・data write・WAL mutationを行わない。
- Worker runtime、iPhone実機、VoiceOver、production telemetryはこのrelease noteの完了証拠に含めず、現時点では `未確認` とする。

### Rollout plan

1. ownerが対象端末のローカルビルドだけにWorker URLとtokenをcompile-time dart-defineとして注入する。値はrepository、Story、ログへ保存しない。
2. hermetic検証とは別に、対象Workerと新baseのiPhoneで録音、同期、会話一覧、詳細本文を順に確認する。
3. 実機またはdeployed Workerの証拠がない段階ではread-only sliceを広域配布せず、既存Omi会話をauthoritative flowとして維持する。

### Operator action

- 有効化する場合だけ、ownerが安全なローカルビルド注入から `BRAINBASE_SELF_HOSTED_WORKER_URL` とtokenを設定する。通常のOSSビルドに必要な操作はない。
- HTTP非2xx、timeout、不正JSONまたはsession/chunk shape違反はCloudflare画面内のscoped errorとして確認する。tokenやresponseの秘密値をログへ出さない。

### Rollback instruction

- ownerはdart-definesからWorker URLまたはtokenを外してdisabledへ戻す。これによりOSS conversations flowが引き続きauthoritativeとなる。
- 接続点そのものを戻す必要がある場合は薄いProvider/Conversations接続点だけをrevertする。Worker deployや既存WALへrollback操作をしない。

### Observability evidence

- ownerが確認する局所証跡は `make failure_mode_coverage -f .vibepro/verification/Makefile` の `parse_failure`（malformed JSON）と `schema_failure`（non-object session）の実行結果、ならびにscoped UI errorである。
- これはhermetic read-adapter証跡であり、production telemetry、deployed Worker、iPhone実機、VoiceOverの証拠ではない。
- build、HTTP 200、hermetic testだけではE2E完了にしない。新baseのWorker runtimeとiPhone経路は別証跡が必要で、どちらも現時点では `未確認` である。Story/Spec/ADR/runbookは同じread-only sliceを表し、生成l10nはARBからの機械生成で独立laneではない。
