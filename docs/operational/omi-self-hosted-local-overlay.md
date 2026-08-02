# Omi self-hosted local overlay

この文書は個人端末用のローカルoverlay契約であり、秘密値や署名ファイルをrepositoryへ保存しない。

- Firebase project選択、`GoogleService-Info.plist`、`google-services.json` は既存のdev/prod tracked設定を置換しない。
- iOS signing、personal entitlements、provisioning profileはローカルのXcode/CI secret管理だけに置く。
- Worker URL/tokenは `--dart-define` またはローカルの安全なビルド注入だけに置く。配布バイナリから抽出可能なtokenを長期credentialとして使わない。
- 追跡対象に追加するのは設定キーの契約とテストのみで、値・bundle id・チームID・証明書・entitlementの実体は含めない。

実機overlayの準備、Worker認証、デプロイはこのrepositoryのテスト成功と別の証拠として扱う。
