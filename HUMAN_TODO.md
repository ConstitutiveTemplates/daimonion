# HUMAN_TODO: 普及戦略のうち人間が実行する作業

出典: `notes/PLAN-widespread-adoption.md` / `TODO.md` §36-§37（2026-10-04）。
リポジトリ内で実装可能な項目は済（`task regen`、CLI リモート delegation、
`presets/mcp-server.yml`、README/CONTRIBUTING 刷新、foundry リネーム統一、
移行ガイド、good first issue 5件、§38 law-map 連携、実 `uvx` 検証）。
以下は権限・判断・対外発信が必要な残作業。

## Phase 2: 独立・リブランディング（目安 1週間）

- [x] **フォーク解除**: ✅ 2026-10-04 完了。delete+recreate で実施（API の
      `fork=leave` は no-op、Support/web UI は非対話不可のため）。注意:
      push protection（旧履歴のダミー slack webhook）回避のため
      `test_gitleaks_precommit.py` を履歴から除去した全書き換え — **全コミット
      SHA とタグ SHA が変わった**。タグ名参照の copier プロジェクトは無影響、
      SHA ピンのみ壊れる。gh-pages/releases/secrets/topics/Pages/issues は
      復元済み。push protection は現時点で OFF（履歴に別の疑似値が残る可能性
      への一時措置；再有効化は要判断）。
- [x] **固有ブランド名の決定**: ✅ `foundry`（`ConstitutiveTemplates/foundry`
      として公開済み）。pyproject.toml・README・CITATION.cff・codemeta.json・
      zensical.toml・workflows・docs・template jinja・tools/ の名称/URL は
      2026-10-04 に一括統一済み（残る `kasi-x/python-copier-template` 参照は
      履歴記録と example リポのみ）
- [x] **NOTICE ファイル新設**: ✅ DiamondLightSource / python3-pip-skeleton /
      copier の系譜と Apache-2.0 を明記済み（2026-10-04）
- [ ] **v1.0.0 リリース**: タグ打ち直し、リリースノート確認。
- [ ] **Secrets 再設定（3種）**: org 再作成で旧リポの secret が消滅。
      `GITLEAKS_LICENSE`（なしだと hygiene の gitleaks がエラー死・2026-10-04
      実測）、`EXAMPLE_DEPLOY_KEY`（example 連携の deploy key。
      org リポは設定で deploy key 無効のため _example.yml の publish 経路を
      見直す必要あり）、`PYPI_API_TOKEN`。
- [x] **`uvx --from git+...` の実ネットワーク検証**: ✅ 2026-10-04。
      `uvx --from git+https://github.com/ConstitutiveTemplates/foundry.git
      foundry new . --preset bare` が clone→cache→render（61 files）まで
      完走（cold cache、実 GitHub 経由）。tag 6.1.0 が最新 questionnaire を
      持たないため ref は main にフォールバック（v1.0.0 タグで解消）
- [ ] **PyPI 公開判断**: `uvx foundry`（git+ URL なし）に
      するかどうか。公開するなら `_pypi.yml` の有効化・トークン設定。

## Phase 3: 対外発信（ローンチ後 2〜4週間）

- [ ] **3大技術記事の執筆・公開**（PLAN §3 ステップ1 に構成案あり）:
  下書き 3 本は `notes/outreach/` に起票済み（DRAFT ヘッダ付き。
  葉数は現行 272 に同期済み。公開・最終編集は人間）:
  - [ ] EN: "Why we used an SMT solver (Z3) to verify 272 question
        combinations" → Show HN + r/Python（PST 火/水 7-8時）
        `notes/outreach/show-hn-z3-verified-template.md`
  - [ ] EN: "Continuous Drift Detection: 5 failure dimensions" →
        r/programming / DevOps 系 `notes/outreach/drift-detection-article.md`
  - [ ] JA: 『272通りを Z3 で形式検証した話』→ Zenn/Qiita
        `notes/outreach/zenn-z3-template.md`
- [ ] **Awesome リスト PR**: `vinta/awesome-python`（Project Templates）、
      `copier-org/awesome-copier`。Astral Discord `#showcase` への投稿。
- [ ] **ニュースレター推薦**: Python Weekly / PyCoder's Weekly の
      推薦フォーム、Python Bytes へのトピック提案。
- [x] **移行ガイド**: ✅ `docs/how-to/migrate-from-hypermodern.md` 新設済み
      （2026-10-04。toolchain 対比表 + fresh/adopt 2 経路 + 実在の gap 列挙。
      zensical.toml nav 登録済み）
- [ ] **`cookiecutter-hypermodern-python` の代替探しスレッドへ案内**:
      敬意を払い中立な形で後継として言及（元作者のスレッドは慎重に）。

## Phase 4: コミュニティ定着（継続）

- [ ] **demo GIF 作成**: `vhs` (Charmbracelet) で15秒 — 生成→`task check`
      通過→`AGENTS.md` 配備。README ヘッダへ埋め込み。
- [ ] **Showcase 開設**: 自分のプロジェクトを本テンプレートで生成し
      「採用例」を README/Docs に掲載。`built with` バッジの配布。
- [x] **`good first issue` シード**: ✅ 5 件起票済み（#4 preset 追加、#5
      プリセット表 docs、#6 `--list-presets`、#7 installation troubleshooting、
      #8 codex セクション草案 — すべて leaf 空間非接触）
- [ ] **Issue/PR 初動体制**: 24h 以内応答、`CONTRIBUTORS.md` 記載で
      リテンション。
- [x] **marimo 統合の判断**: ✅ 実装済み + 本セッションで 3 件のギャップを修正
      （data_science の notebooks/ に marimo seed 追加、`notebook` task が
      必要とする jupyterlab を experiment extra へ、per-file-ignores を
      kaggle 専用から `**/notebook*/**` へ一般化 — 2026-10-04）

## Phase 1 補遺（判断待ち）

- [x] **質問票第1問のプリセット案内**: ✅ 採用（A: help 追記、2026-10-05）。
      `project_type.help` に全 12 プリセット名を列挙する導線を追加 +
      `test_every_preset_is_named_in_project_type_help` でプリセット名↔help
      の一致を機械化（新プリセットで help 未更新なら失敗）。leaf 空間非接触。
