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
