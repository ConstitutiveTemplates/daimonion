---
title: 272通りを Z3 で形式検証した話
intended-venue: Zenn / Qiita（技術ブログ）
status: DRAFT — human edits before posting
date: 2026-10-05
author: ConstitutiveTemplates/foundry メンテナ
note-to-editor: |
  タイトルは HUMAN_TODO / PLAN-widespread-adoption の『234通りを Z3 で形式検証した話』を
  そのまま採用。ただし本文の数字はリポジトリ現状（2026-10-05）に合わせてある:
  tests/matrix/witnesses.json の葉数は現在 272 枚（234 は 2026-09-18 時点の計測値で、
  その後 domain_traits / distribution / per-site judges の追加で 272 に増加。
  tests/test_witness_matrix.py の docstring も "272 leaves"）。
  公開前にタイトルを「272通り」に直すか、234 時点のアーカイブ記事とするか要判断。
---

# 272通りを Z3 で形式検証した話

## はじめに

私は Copier ベースの Python プロジェクトテンプレート **foundry** をメンテナンスしています。

- https://github.com/ConstitutiveTemplates/foundry

このテンプレートには、プロジェクトの種類（CLI・ライブラリ・Web API・ROS2・マイコン・競プロ向けなど）や、推奨統合の取捨（bot・Docker・MCP・データサイエンス等）を選ぶ質問票がついています。質問の数は数十、組み合わせは単純に数えれば天文学的なオーダーになります。その「全組み合わせ」をまともにテストするのは不可能に見えます。

しかし私たちは今、**質問票の全分岐を Z3 で充足可能性証明し、その全「葉」を実レンダで検証する**仕組みを回しています。この記事は、どうやってそれが可能になったのか、という話です。

## 質問票は Boolean 式の森である

Copier の質問票では、各質問に `when:` という条件が書けます。たとえば「`use_recommended_bot` を選んだときだけ `bot_platform` を聞く」といった具合です。foundry の質問票（`copier.yml` + `questions/` の断片ファイル）にはこうした条件が積み重なり、質問同士が依存し合うグラフを形成しています。

このグラフの性質は、テスト設計を根本から難しくします。`when:` の条件は Jinja で書かれ、`==`・`!=`・`in`・`not in` と `and`/`or`/`not` が混ざります。**「どの組み合わせの回答が実際に到達可能か」は手計算では追えません。** そして到達不可能な組み合わせをテストしても無駄で、逆に到達可能な組み合わせを見落とせば、その分岐は未検証のままリリースされます。

さらに深刻なのは爆発のしかたです。このリポジトリのコスト台帳（`tests/test_marker_drift.py`）には「葉空間の成長則」が明文化されています。通常の追加は加算的で、include レイヤ1つにつき +76 葉、ゲートを1つ外す次元で +22 葉。**しかし include レイヤの排他制約（同時に1つだけ選べる）を外すと、レイヤ乗数が組合せ積になり指数爆発します。** テストが遅くなってから気づくのでは遅すぎる、というのがこのプロジェクトの判断でした。

## `when:` を Z3 の式として読む

そこで導入したのが SMT ソルバ **Z3**（依存は `z3-solver>=4.13.0,<5`）です。`tools/when_model.py` が、質問票で実際に使われる `when:` 構文（`==`・`!=`・`in`・`not in` と論理結合・括弧）を Z3 の数式にエンコードします。`choices` を持つ質問は「選択肢インデックス上の整数」としてモデル化され、`x == 'value'` は `Int(x) == domain.index('value')` になります。

このエンコードには嬉しい副産物があります。**ドメインに存在しない値との比較は自動的に偽になります。** たとえば `project_type == 'librry'` のようなタイポは、たちどころに充足不能（unsat）として検出されます。「この質問は誰も到達できないのでは？」という質問票のデッドブランチが、手作業のレビューではなくソルバによって数学的に排除されるわけです。実際の Copier の Jinja 評価との食い違いは `tests/test_when_model.py` が差分テスト（differential oracle）として担保しています。

## 証人葉（witness leaf）とは何か

ここからが本題です。`tools/z3_witnesses.py` は、質問票の変数（`project_type`、`oj_category`/`oj_kind`、`use_recommended_*` ゲート群、`include_*` レイヤ群）に、質問票の制約と不変条件をすべて assert したソルバを構築し、**満たすモデルをすべて列挙**します。列挙は「見つけたモデルを blocking 節で潰しながら次を探す」という古典的な手法です。

列挙された各モデルが**証人葉（witness leaf）**です。SMT の用語で「witness」とは式を満たす割当てのこと。つまり葉1枚は、**全制約を満たす具体的な回答割当て1つ**であり、その葉は「この回答でレンダしたら、こういうファイル群が出て、これらが absent である」という期待（`expect` の files/absent リスト）と不変条件までセットで定義されます。

現在の葉数は **272 枚**です（`tests/matrix/witnesses.json`、`witnesses.jsonl` とも一致）。この記事のタイトルにある 234 は 2026-09-18 時点の計測値で、そのとき bot platform が葉空間に加わって 228 → 234 になり、その後 domain traits の共起・distribution（商用/OSS の区別）・judge 別サイトの追加で 272 まで増えました。成長のたびに葉は `task witness` で再生成されます。ちなみに「葉」と呼ぶのは、質問票の制約グラフを decision tree とみたときの充足可能な末端（leaf）という意味です。

## 272 葉を実行に落とす 3 段階

列挙しただけでは意味がありません。**葉は実際に copier でレンダされ、判定されなければなりません。** その実行を `tests/test_witness_matrix.py` が 3 段階の tier で分担しています。

- **fast**: 全 272 葉を copier でレンダ（`skip_tasks=True`、venv を作らない）し、葉ごとに宣言された files/absent を assert。加えてレンダ済み Python に `ruff format --check` / `ruff check` をかけます。レンダ結果は `tests/render_cache.py` のキャッシュで共有されるので、同じ回答の葉は copier を1回しか走らせません。
- **full**: 有界なサンプルの葉だけ追加で `uv sync` し、**生成されたプロジェクト自身の pytest**、basedpyright、docs ビルドを通します。venv を作るので高コスト。
- **slow**: `tools/batch.py` が JSONL 全体を実バッチランナー（§C6）で回し、その verdict を最終判定とします。

この分割が「全 272 通りを検証する」を現実的なコストに落としています。PR の CI ジョブ（`.github/workflows/witness.yml` の fast job）は、234 葉時点の実測で **cold で 16.9 秒**（240 テスト = 234 レンダ + 6 チェック。タイムアウト 30 分の 1% 未満）。nightly だけが full tier を追加で回します。ローカルの編集ループ（`task test-fast`）は venv もネットワークも触らないテストだけで構成され、葉の網羅は重い tier に追いやられています。コスト台帳 `tests/matrix/tiers.json` が tier ごとの wall time を記録し、30 日を超えた計測は再測定を要求します。

## ドリフトを検知する仕組み

葉の空間が広がり続けるなら、「気づかないうちに指数爆発して CI が死ぬ」リスクもあります。これに対する防衛も組み込まれています。

- **葉数の上限バジェット**: `LEAF_BUDGET = 450`（`tests/test_marker_drift.py`）。上記の加法則からすると通常の追加は余裕で収まる範囲で、**乗算的な変更だけがバジェットを超える**設計。超過は事故ではなく「決断」として扱われ、台帳の再計測とセットでバジェットを上げることを要求されます。
- **到達可能性ガード**: `test_witness_leaves_match_the_generator` と `test_witness_leaves_are_reachable` が、質問票の編集で宣言済みの葉が unreachable になったときに、該当する葉の名前を出して失敗します。
- **鮮度検知**: 各バッチリクエストは `ref: HEAD` をピンしているので、質問票が進んだのに `witnesses.jsonl` が古いままなら、再生成コマンドの案内つきでテストが失敗します。

そして質問票を変更した日の「定義完了」は **`task regen` 1 コマンド**です。葉の再生成 → 全葉バッチ判定 → tier 台帳の更新 → ethics 付録の再生成 → 生成ドキュメント → predicates レポートまでが一気通貫で走ります。

## まとめ

foundry がやっているのは、要するにこういうことです。

1. 質問票の `when:` 条件を Z3 の式としてモデル化する（タイポやデッドブランチは unsat として機械的に検出）
2. 全充足モデル = 証人葉を列挙する（現在 272 枚、2026-09-18 時点で 234 枚）
3. 各葉を実レンダし、files/absent と生成物の品質を fast / full / slow の tier で検証する
4. 葉空間の成長則と上限バジェットで、指数爆発を CI が死ぬ前に検知する

「組み合わせが多すぎて全部はテストできない」という諦めを、SMT ソルバと tier 設計で「全到達可能組み合わせはテストできる」に変えた、というのがこのプロジェクトの主張です。

試してみたい方はこちらから:

```shell
uvx --from git+https://github.com/ConstitutiveTemplates/foundry.git foundry new my-project --preset library
```

`--preset` には `bare` / `cli` / `data-science` / `library` / `mcp-server` / `micropython` / `online-judge-*` / `ros2` / `web-api` があり、対話をスキップしたい場合も安心です。ソースコード（`tools/z3_witnesses.py`、`tools/when_model.py`、`tests/matrix/witnesses.json`）も全部公開しています。「Z3 でテンプレートを検証する」のは聞いたことがない、という方は、ぜひ実装を眺めてみてください。