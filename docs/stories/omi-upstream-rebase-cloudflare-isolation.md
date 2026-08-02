---
id: omi-upstream-rebase-cloudflare-isolation
title: Omi OSS最新版への再ベースとCloudflareセルフホスト差分の隔離
period: 2026-08
status: active
source_of_truth: user-approved implementation request
---

# Story: Omi OSS最新版への再ベースとCloudflareセルフホスト差分の隔離

## 誰のために

Brainbase Omiセルフホスト版を保守する開発者と、その実機を使う利用者のための変更である。

## 問題

旧forkは `origin/main` より1 commit先で大量の未コミット変更を含み、`upstream/main` から3,642 commits遅れた検証スパイクである。そのまま差分を積み増すと、OSS更新、Cloudflare Worker、個人端末のFirebase/署名設定が同じ変更面に混ざり、同期経路の安全性を継続して検証できない。

## 目標成果

`upstream/main@d2d921803` を起点に、Cloudflare Workerの既存文字起こしをアプリでread-onlyに一覧・詳細表示できる最小sliceを成立させる。WALとの接続は将来のためのno-op adapter境界だけに留める。Cloudflare Workerは別リポジトリのまま維持し、Flutterの製品差分はOSSの直接変更を一桁〜十数ファイルへ抑えることを設計目標として検証する。

## 受け入れ条件

1. Cloudflare API、モデル、Provider、UIは `app/lib/self_hosted/cloudflare/` に独立し、Worker APIだけに依存する。
2. OSSへの接続点は Provider 登録、会話画面の入口、capture/WAL/sync のno-op adapter境界に限定する。既存のOmi API、Firebase、会話モデルを置換しない。
3. adapter は設定状態を `disabled` または `deferred` として表すだけで、既存WALをWorkerへ渡さない。録音の耐久性、upload、ack、deleteは既存WALが所有し、このPRの受入対象外である。
4. Worker APIは HTTPS（loopback開発を除く）、Bearer認証、ページング、期限切れ・HTTP失敗・不正JSONの非秘密値エラーを契約化してテストする。
5. 個人用Firebase、iOS署名、entitlementは製品tracked差分に含めない。必要な値なしで読めるlocal overlay契約だけを文書化する。
6. UI表示文言はARB正本で管理し、生成Dartはコピー移植せず `flutter gen-l10n` で再生成する。
7. 証拠はこの新baseでのコード/テストと、旧スパイクに存在する実機・Worker・デプロイ証拠を明確に分離する。旧証拠は新baseの成功証拠にしない。
8. Story、Spec、ADR、local overlay runbookは同一のread-only製品sliceを表す。生成l10nはARBからの機械生成物であり、独立した製品laneではない。

## KPI と証拠境界

| KPI | 目標/判定 | 証拠 |
| --- | --- | --- |
| upstream更新時のOSS direct-touch数 | direct-touchが一桁〜十数ファイルかを各更新で記録 | `git diff --name-only upstream/main` |
| adapter契約テスト | `disabled` / `deferred`、例外非伝播、既存WAL非変更を対象に緑 | hermetic Flutter unit test |
| 対象テスト | Cloudflare API/model/provider/UI と adapter のfocused testsが緑 | `flutter test <targets>` |
| Worker API | 実Workerのread responseをfixtureにした一覧・詳細契約を確認 | hermetic contract test。実Worker呼出しは未確認 |
| iPhone実機E2E | 新baseでの録音→同期→一覧→詳細 | 次slice。未実施・本PRの受入対象外 |

## 非目標

- Cloudflare Workerリポジトリ、R2設定、デプロイ、秘密値の変更
- Firebase project、署名、entitlementのtracked製品設定への組込み
- Omi OSSの既存会話APIや同期プロトコルの置換
- 音声upload、ack、ローカルWAL削除、およびそれらの完了状態の主張
- 新baseでのiPhone実機E2E
- 旧スパイクのdirty差分を機械的に移植すること

## 証拠の扱い

旧 `flutter-r2-upload-spike` のコードとテストは設計参照である。そこでの端末/Worker成功は、最新upstream baseで再現するまで `参考（新base未確認）` とする。

## このPRの受入境界

- 含む: Cloudflare Workerのread-only一覧・詳細、Omi会話が0件でも設定有効時に到達できる入口、実Worker response shapeを写したhermetic fixture、WALのno-op boundary。
- 含まない: `POST` upload、chunk/finalize、ack、ローカルWAL削除、新base iPhone E2E。これらは後続sliceでWorker idempotency契約と実機証跡を揃えて受け入れる。
- 旧スパイクの成功記録は新baseの成功証拠へ混ぜない。

## Release・rollback・observability

- Worker deployはこのPRの対象外である。URL/tokenのdart-definesが未設定ならCloudflare機能は無効で、既存Omi会話を変更せずread requestもdata writeも行わない。
- HTTP非2xx、timeout、不正response shapeはCloudflare read moduleのscoped errorであり、WAL upload、ack、deleteへ進まない。rollbackはdefinesを除去するか、Provider/Conversationsの薄い接続点をrevertする。
- focused tests、analyzer、HTTP 200、buildは局所証拠にすぎない。新baseのWorker runtimeとiPhone E2Eは別途必要で、ともに `未確認` のまま維持する。
