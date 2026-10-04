# cookiecutter-hypermodern-python 代替スレッド用返信草案 — maintainer review 必須

2026-10-05。投稿は人間。対象は「後継テンプレートを探している」第三者の
スレッドのみ。元作者 cjolowicz のスレッド・当該リポジトリの Issue では
絶対に勧誘しない（自薦は傍若無人に見える; Phase 3 の方針どおり中立性最優先）。

## 方針

- 単にリンクを置かない。「何が違うか」を先に述べ、テンプレートを
  選ぶ判断材料として提示する。
- hypermodern の強み（poetry/Nox 時代の先行実装、Read the Docs 連携）は
  認め、対比表（docs/how-to/migrate-from-hypermodern.md）を添える。
- 買収・disparage 的表現は不可。「unmaintained since 2024-05」は事実だが
  「dead」とは書かない。

## 返信文案（EN）

> If you're still looking for a maintained successor shape, we maintain
> `foundry` — a Copier template in a similar spirit (uv + ruff + pytest +
> basedpyright + generated CI, plus a generated `AGENTS.md` ethics appendix).
> The questionnaire is Z3-verified across 272 rendered leaves, and there's an
> adopt-mode for existing repos. A migration how-to with the full feature
> diff is at `docs/how-to/migrate-from-hypermodern.md`.
>
> Fair warning: it is opinionated (uv-native, no poetry path) and heavier
> than hypermodern's minimal scaffold — if you only want `src/` + CI, the
> `bare` preset is the closest fit.

## 対象スレッド候補（要人力確認）

- r/Python "Is there a maintained alternative to cookiecutter-hypermodern-python?"
  系の定期質問スレッド（投稿時に検索して直近 6 ヶ月のものを選ぶ）。
- awesome-python / cookiecutter 系リストの "replacements" 記述 — PR 文面は
  `awesome-list-entries.md` 側。

## 投稿前チェックリスト

- [ ] 対象スレッドが「代替を探している」文脈であること（質問・募集形）
- [ ] 直前 30 日に同スレッドへの自己宣伝がないこと
- [ ] 文面に `foundry` のリンク 1 本 + migration how-to のみ（3 連リンク不可）
