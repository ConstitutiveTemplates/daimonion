---
title: 234通りを Z3 で形式検証した話
intended-venue: Zenn / Qiita（技術ブログ）
status: DRAFT — human edits before posting
date: 2026-10-05
author: ConstitutiveTemplates/daimonion メンテナ
note-to-editor: |
  タイトルは HUMAN_TODO / PLAN-widespread-adoption の『234通りを Z3 で形式検証した話』を
  採用。ただし本文の数字はリポジトリ現状（2026-10-05）に合わせてある:
  tests/matrix/witnesses.json の葉数は現在 272 枚（234 は 2026-09-18 時点の計測値で、
  その後 domain_traits / distribution / judge 別サイトの追加で増加。
  tests/test_witness_matrix.py の docstring も "272 leaves"）。
  公開前にタイトルを「272通り」に直すか、234 時点のアーカイブ記事とするか要判断。
---

# 234通りを Z3 で形式検証した話

## はじめに

私は Copier ベースの Python プロジェクトテンプレート **daimonion**（https://github.com/ConstitutiveTemplates/daimonion）のメンテナです。名前はソクラテスの内なる声（daimonion）——何をすべきかは決して言わず、止まるべき時だけを知らせる——に由来し、このテンプレートの「警告・中止・拒否」という姿勢（そして Unix の *daemon* の語源）にも重なります。このテンプレートには、プロジェクトの種類（CLI・ライブラリ・Web API・ROS2・競プロ向けなど）や推奨統合の取捨（bot・Docker・MCP・データサイエンス等）を選ぶ質問票がついており、組み合わせは単純に数えれば天文学的なオーダーになります。「全組み合わせをテストする」のは不可能に見えます。しかし今、daimonion は**質問票の全分岐を Z3 で充足可能性証明し、その全「葉」を実レンダで検証する**仕組みを回しています。どうやって可能にしたのか、という話です。

## 質問票は Boolean 式の森である

Copier の各質問には `when:` 条件が書けます。たとえば「`use_recommended_bot` を選んだときだけ `bot_platform` を聞く」といった具合です。daimonion の質問票（`copier.yml` + `questions/` の断片）ではこうした条件が積み重なり、質問同士が依存し合うグラフを形成しています。

この性質はテスト設計を根本から難しくします。`when:` は Jinja で書かれ、`==`・`!=`・`in`・`not in` と `and`/`or`/`not` が混ざるため、**「どの回答の組み合わせが実際に到達可能か」は手計算では追えません。** 到達不可能な組み合わせをテストしても無駄で、到達可能な組み合わせを見落とせば、その分岐は未検証のままリリースされます。

爆発のしかたも厄介です。このリポジトリのコスト台帳（`tests/test_marker_drift.py`）には「葉空間の成長則」が明文化されています。通常の追加は加算的で、include レイヤ1つにつき +76 葉、ゲートを1つ外す次元で +22 葉。**しかし include レイヤの排他制約（同時に1つだけ選べる）を外すと、乗数が組合せ積になり指数爆発します。** 遅くなってから気づくのでは遅すぎる、というのがこのプロジェクトの判断でした。

## `when:` を Z3 の式として読む

導入したのは SMT ソルバ **Z3**（`z3-solver>=4.13.0,<5`）です。`tools/when_model.py` が、質問票で実際に使われる `when:` 構文を Z3 の数式にエンコードします。`choices` を持つ質問は「選択肢インデックス上の整数」としてモデル化され、`x == 'value'` は `Int(x) == domain.index('value')` になります。

ここに嬉しい副産物があります。**ドメインに存在しない値との比較は自動的に偽になります。** たとえば `project_type == 'librry'` のようなタイポは、たちどころに充足不能（unsat）として検出されます。「誰も到達できない質問」というデッドブランチが、レビューではなくソルバによって数学的に排除されるわけです。実 Copier の Jinja 評価との食い違いは `tests/test_when_model.py` が差分テストとして担保しています。

## 証人葉（witness leaf）とは何か

`tools/z3_witnesses.py` は、質問票の変数（`project_type`、`oj_category`/`oj_kind`、`use_recommended_*` ゲート群、`include_*` レイヤ群）に、質問票の制約と不変条件をすべて assert したソルバを構築し、**満たすモデルをすべて列挙**します。列挙は「見つけたモデルを blocking 節で潰しながら次を探す」古典的な手法です。

列挙された各モデルが**証人葉（witness leaf）**です。SMT の用語で witness とは式を満たす割当てのこと。つまり葉1枚は、**全制約を満たす具体的な回答割当て1つ**であり、「この回答でレンダしたら、こういうファイル群が出て、これらが absent である」という期待（files/absent リスト）と不変条件までセットで定義されます。

現在の葉数は **272 枚**です（`tests/matrix/witnesses.json` と `witnesses.jsonl` が一致）。タイトルの 234 は 2026-09-18 時点の計測値で、bot platform が葉空間に加わった 228 → 234、その後 domain traits の共起・distribution・judge 別サイトの追加で 272 まで増えました。成長のたびに `task witness` で再生成されます。

## 272 葉を実行に落とす 3 段階

列挙しただけでは意味がありません。**葉は実際に copier でレンダされ、判定されなければなりません。** その実行を `tests/test_witness_matrix.py` が 3 段階で分担しています。

- **fast**: 全 272 葉を copier でレンダ（`skip_tasks=True`、venv なし）し、葉ごとの files/absent を assert。レンダ済み Python には `ruff format --check` / `ruff check` もかけます。レンダは `tests/render_cache.py` のキャッシュで共有され、同じ回答の葉は copier を1回しか走らせません。
- **full**: 有界なサンプルの葉だけ追加で `uv sync` し、**生成されたプロジェクト自身の pytest**・basedpyright・docs ビルドを通します。venv を作るので高コスト。
- **slow**: `tools/batch.py` が JSONL 全体を実バッチランナーで回し、その verdict を最終判定とします。

この分割が「全 272 通り」を現実的なコストに落としています。PR の CI ジョブ（witness.yml の fast job）は、234 葉時点の実測で **cold 16.9 秒**（240 テスト = 234 レンダ + 6 チェック、タイムアウト 30 分の 1% 未満）。nightly だけが full tier を追加で回します。ローカルの編集ループ（`task test-fast`）は venv もネットワークも触らないテストのみで、網羅は重い tier に追いやられています。コスト台帳 `tests/matrix/tiers.json` が tier ごとの wall time を記録し、30 日を超えた計測は再測定を要求します。

## ドリフトを検知する仕組み

- **葉数の上限バジェット**: `LEAF_BUDGET = 450`（`tests/test_marker_drift.py`）。加法則の範囲の追加は余裕で収まり、**乗算的な変更だけがバジェットを超える**設計。超過は事故ではなく「決断」として扱われ、台帳の再計測つきでバジェットを上げることを要求されます。
- **到達可能性ガード**: `test_witness_leaves_match_the_generator` と `test_witness_leaves_are_reachable` が、質問票の編集で宣言済みの葉が unreachable になったとき、該当する葉の名前を出して失敗します。
- **鮮度検知**: 各バッチリクエストは `ref: HEAD` をピンしているため、質問票が進んだのに `witnesses.jsonl` が古いままだと、再生成コマンドの案内つきでテストが失敗します。

質問票を変更した日の「定義完了」は **`task regen` 1 コマンド**です。葉の再生成 → 全葉バッチ判定 → tier 台帳の更新 → ethics 付録の再生成 → 生成ドキュメント → predicates レポートまで一気通貫で走ります。

## まとめ

daimonion の主張を要約すると、こうです。

1. 質問票の `when:` 条件を Z3 の式としてモデル化する（タイポやデッドブランチは unsat として機械的に検出）
2. 全充足モデル = 証人葉を列挙する（現在 272 枚）
3. 各葉を実レンダし、fast / full / slow の tier で判定し、成長則とバジェットで指数爆発を CI が死ぬ前に検知する

「組み合わせが多すぎて全部はテストできない」という諦めを、SMT ソルバと tier 設計で「全到達可能組み合わせはテストできる」に変えた、という話です。

試してみたい方はこちらから:

```shell
uvx --from git+https://github.com/ConstitutiveTemplates/daimonion.git daimonion new my-project --preset library
```

`--preset` には `bare` / `cli` / `data-science` / `library` / `mcp-server` / `micropython` / `online-judge-*` / `ros2` / `web-api` があります。ソースコード（`tools/z3_witnesses.py`・`tools/when_model.py`・`tests/matrix/witnesses.json`）はすべて公開中です。「Z3 でテンプレートを検証する」のは聞いたことがない、という方は、ぜひ実装を眺めてみてください。
