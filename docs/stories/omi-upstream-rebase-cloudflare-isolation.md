---
id: omi-upstream-rebase-cloudflare-isolation
story_id: omi-upstream-rebase-cloudflare-isolation
title: Omi OSS最新版への再ベースとCloudflareセルフホスト差分の隔離
period: 2026-08
status: active
source_of_truth: user-approved implementation request
pr_scope_strategy: atomic_single_pr
pr_scope_reason: >-
  requirements-ssot、runtime-behavior、misc-follow-upは同じread-only縦スライスの契約と接続点を検証するため不可分である。生成l10nはARB由来の派生物、overlay docは設定境界であり、これらを分割すると契約と実装の原子性が失われる。
pr_scope_review_facets:
  - requirements-ssot
  - runtime-behavior
  - misc-follow-up
pr_scope_dependency_boundaries:
  - requirements-ssot->runtime-behavior
  - runtime-behavior->misc-follow-up
---

# Story: Omi OSS最新版への再ベースとCloudflareセルフホスト差分の隔離

## 誰のために

Brainbase Omiセルフホスト版を保守する開発者と、その実機を使う利用者のための変更である。

## 問題

旧forkは `origin/main` より1 commit先で大量の未コミット変更を含み、`upstream/main` から3,642 commits遅れた検証スパイクである。そのまま差分を積み増すと、OSS更新、Cloudflare Worker、個人端末のFirebase/署名設定が同じ変更面に混ざり、同期経路の安全性を継続して検証できない。

## 目標成果

`upstream/main@57ca482ed` を起点に、Cloudflare Workerの既存文字起こしをアプリでread-onlyに一覧・詳細表示できる最小sliceを成立させる。WALとの接続は将来のためのno-op adapter境界だけに留める。Cloudflare Workerは別リポジトリのまま維持し、Flutterの製品差分はOSSの直接変更を一桁〜十数ファイルへ抑えることを設計目標として検証する。

## 受け入れ条件

1. Cloudflare API、モデル、Provider、UIは `app/lib/self_hosted/cloudflare/` に独立し、Worker APIだけに依存する。
2. OSSへの接続点は Provider 登録、会話画面の入口、capture/WAL/sync のno-op adapter境界に限定する。既存のOmi API、Firebase、会話モデルを置換しない。
3. adapter は設定状態を `disabled` または `deferred` として表すだけで、既存WALをWorkerへ渡さない。録音の耐久性、upload、ack、deleteは既存WALが所有し、このPRの受入対象外である。
4. Worker APIは HTTPS（loopback開発を除く）、Bearer認証、ページング、期限切れ・HTTP失敗・不正JSONの非秘密値エラーを契約化してテストする。
5. 個人用Firebase、iOS署名、entitlementは製品tracked差分に含めない。必要な値なしで読めるlocal overlay契約だけを文書化する。
6. UI表示文言はARB正本で管理し、生成Dartはコピー移植せず `flutter gen-l10n` で再生成する。
7. 証拠はこの新baseでのコード/テストと、旧スパイクに存在する実機・Worker・デプロイ証拠を明確に分離する。旧証拠は新baseの成功証拠にしない。
8. Story、Spec、ADR、local overlay runbookは同一のread-only製品sliceを表す。生成l10nはARBからの機械生成物であり、独立した製品laneではない。

## Delivery record

### current_reality

- Cloudflareへの接続は、Workerのlist/detailを読むだけの薄いUIモジュールとして実装する。コードとfocused testはローカルで確認するが、Worker deploy、iPhone実機E2E、WALのupload-ack-deleteは未確認かつ本PRの対象外である。

### invariants

- URLまたはtokenが未設定・不正なら接続はdisabledとし、Cloudflare requestを送らない。
- operator actionはdart-definesでWorker URLとtokenを設定することだけであり、既存Omi機能の振る舞いは変えない。
- 生成l10nはARB由来の派生物、local overlay documentは設定境界として扱い、Cloudflare側のデータ書込み経路を追加しない。

### boundaries

- Workerのdeploy、Cloudflare runtimeの稼働確認、iPhone実機E2E、WAL upload-ack-deleteの確認は、このread-only縦スライスの完了条件に含めない。
- URL/tokenの実値、Cloudflareの運用権限、production telemetryはStoryの証拠範囲外とする。

### failure_modes

- URL/tokenがない場合はdisabledのままとし、既存Omi画面やデータ経路に影響を与えない。
- timeout、non-2xx、malformed JSON、認可拒否はscoped UI errorとして当該画面に限定し、retry以外の書込み・WAL mutationを行わない。

### done_evidence

- current-headに束縛したVibePro artifactsとfocused test logsで、設定無効時のno request、read-only list/detail、失敗時のscoped UI errorを確認する。
- build、HTTP 200、process起動だけではruntimeまたはiPhone E2Eの証拠にしない。Worker deploy、iPhone実機E2E、WAL upload-ack-deleteは未確認のまま残す。

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

## Product invariants affected

- INV-DATA-1

この不変条件は、既存データの書込み経路を変えず、Cloudflare連携を設定で無効化できるread-only境界に保つことで維持する。

## Release and operations

### release_note

- Cloudflare連携は設定済みの場合だけ表示するread-only list/detailである。Worker deployやiPhone実機E2Eを完了として告知せず、WAL upload-ack-deleteを含む書込み機能は提供しない。

### rollout_plan

- operatorはdart-definesでWorker URLとtokenを設定するだけである。URL/token未設定時はdisabledとなり、既存Omi機能に影響しない。Workerのdeployやproduction rolloutはこのStoryの実行手順ではない。

### rollback_instruction

- dart-definesからWorker URLまたはtokenを外してdisabledへ戻す。read-only UIを外す場合も既存Omiのデータ経路を変更せず、Cloudflareへのupload、ack、deleteを実行しない。

### observability_evidence

- 観測証拠はscoped UI errorと、検証時のcurrent-headにbindしたVibePro artifacts/test logsに限定する。docs変更後は新HEADで再検証してbindし直すまで、既存artifactをruntime証明へ昇格させない。
- production telemetry、Worker runtime、iPhone実機E2E、WAL upload-ack-deleteの観測は主張しない。
