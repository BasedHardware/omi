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

`upstream/main@6a7e1db78` を起点に、録音を既存のcapture/WAL経路で永続化し、Cloudflare Workerへ同期し、Cloudflare側の会話（文字起こし）一覧と詳細をアプリで参照できる最小縦スライスを成立させる。Cloudflare Workerは別リポジトリのまま維持し、Flutterの製品差分はOSSの直接変更を一桁〜十数ファイルへ抑えることを設計目標として検証する。

## 受け入れ条件

1. Cloudflare API、モデル、Provider、UIは `app/lib/self_hosted/cloudflare/` に独立し、Worker APIだけに依存する。
2. OSSへの接続点は Provider 登録、会話画面の入口、capture/WAL/sync の adapter に限定する。既存のOmi API、Firebase、会話モデルを置換しない。
3. adapter は self-hosted 設定が有効な場合だけ、確定済みWALをWorker同期へ渡す。録音の耐久性は既存WALが所有し、ネットワーク失敗で録音を止めず、Worker成功前にWALを削除しない。
4. Worker APIは HTTPS（loopback開発を除く）、Bearer認証、ページング、期限切れ・HTTP失敗・不正JSONの非秘密値エラーを契約化してテストする。
5. 個人用Firebase、iOS署名、entitlementは製品tracked差分に含めない。必要な値なしで読めるlocal overlay契約だけを文書化する。
6. UI表示文言はARB正本で管理し、生成Dartはコピー移植せず `flutter gen-l10n` で再生成する。
7. 証拠はこの新baseでのコード/テストと、旧スパイクに存在する実機・Worker・デプロイ証拠を明確に分離する。旧証拠は新baseの成功証拠にしない。

## KPI と証拠境界

| KPI | 目標/判定 | 証拠 |
| --- | --- | --- |
| upstream更新時のOSS direct-touch数 | direct-touchが一桁〜十数ファイルかを各更新で記録 | `git diff --name-only upstream/main` |
| adapter契約テスト | 成功、HTTP失敗、再試行可能失敗、設定無効を対象に緑 | hermetic Flutter unit test |
| 対象テスト | Cloudflare API/model/provider/UI と adapter のfocused testsが緑 | `flutter test <targets>` |
| Worker API | 実Workerとの一覧・詳細・同期契約を確認 | Worker integration evidence（本Storyでは未確認） |
| iPhone実機E2E | 録音→同期→一覧→詳細を実機で確認 | 実機証跡（本Storyでは未確認） |

## 非目標

- Cloudflare Workerリポジトリ、R2設定、デプロイ、秘密値の変更
- Firebase project、署名、entitlementのtracked製品設定への組込み
- Omi OSSの既存会話APIや同期プロトコルの置換
- 旧スパイクのdirty差分を機械的に移植すること

## 証拠の扱い

旧 `flutter-r2-upload-spike` のコードとテストは設計参照である。そこでの端末/Worker成功は、最新upstream baseで再現するまで `参考（新base未確認）` とする。
