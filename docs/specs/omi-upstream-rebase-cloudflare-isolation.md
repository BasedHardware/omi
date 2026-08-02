---
id: omi-upstream-rebase-cloudflare-isolation
story: ../stories/omi-upstream-rebase-cloudflare-isolation.md
architecture: ../architecture/ADR-omi-upstream-rebase-cloudflare-isolation.md
period: 2026-08
status: approved-for-minimum-slice
---

# Spec: Cloudflareセルフホスト会話最小縦スライス

## Configuration

- `BRAINBASE_SELF_HOSTED_WORKER_URL`: Workerのabsolute HTTPS URL。loopbackのHTTPは開発テストのみ許可する。
- `BRAINBASE_SELF_HOSTED_WORKER_TOKEN`: Bearer token。空ならCloudflare一覧・詳細・adapterは無効で、ログや例外に値を出さない。
- `BRAINBASE_SELF_HOSTED_SYNC`: `true` のときだけadapterを有効にする。URLまたはtoken欠落時は無効扱いにする。

## Worker read contract

| Operation | Request | Success | Failure |
| --- | --- | --- | --- |
| list sessions | `GET /v1/transcript-sessions?limit=<n>&cursor=<cursor>` | `sessions` と任意の `next_cursor` | 非2xx、不正JSON、循環cursor、timeoutは値を含まないエラー |
| transcript detail | `GET /v1/upload-sessions/{id}/transcript` | `session` と `chunks` | 非2xx、不正JSON、timeoutは値を含まないエラー |

一覧はcursorを重複なく最後まで追い、詳細chunksはsequence昇順で表示する。tokenはHTTP header以外へ出力しない。

## Adapter contract

- 入力は既存WALが既に永続化した、再送可能なファイル/metadataである。
- 設定が無効なら何もしない。
- adapter例外は録音経路へ伝播させない。失敗はWALの既存retry経路を妨げず、Worker成功の確認前にローカルWALを終端化しない。
- Worker upload endpoint/ack schemaは別repoのWorker契約と合わせ、実Worker evidenceが得られるまでこのsliceでは実装を有効化しない。

この最小sliceで実装するadapterは設定を検査して `disabled` または `deferred` を返すno-op seamだけである。`LocalWalSyncImpl` への接続、ファイルupload、ack、ローカルWALの削除は実装しない。

## UI contract

- Cloudflare設定が有効なとき、会話画面からCloudflare transcript一覧へ遷移できる。
- 一覧はloading、空、error、session status、recorded time、文字数を表す。
- 行を選ぶと詳細で時系列順のtranscript textを表示する。
- 設定無効・ネットワーク失敗は既存Omi会話一覧を壊さず、Cloudflare画面だけで明示する。

## Verification

1. API/model/provider/unit tests: pagination、順序、timeout、HTTP failure、token非露出、設定無効。
2. Widget test: 有効時の入口、一覧、詳細、error/empty。
3. analyzer ratchet: 新しいwarning/infoを増やさない。
4. 実機E2EとWorker APIは独立して記録する。ここでテストが緑でも実機/Worker/deploy成功とはしない。
