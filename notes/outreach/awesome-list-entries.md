# Awesome-list PR entries — DRAFT for the maintainer

2026-10-05. 人間が PR 本文に使う文面の素案。提出自体は人間作業。

「daimonion」という名前はソクラテスの内なる声——何をすべきかは決して言わず、
止まるべき時だけを知らせる——に由来し、このテンプレートの警告・中止・拒否の
姿勢（そして Unix の *daemon* の語源）にも重なります。

## 訂正（PLAN の前提と異なる点）

- `copier-org/awesome-copier` は **存在しない**。Copier 公式の一覧経路は
  GitHub topic `copier-template`（github.com/topics/copier-template）で、
  daimonion は既にその topic を持つ → 掲載済み。残る公式経路は
  copier Discussions の Show & tell（任意）。
- `donhui/awesome-uv` は「Projects using uv」の表形式リスト（template セクション
  なし）。daimonion は uv-native のテンプレートとして追加可能だが、星・バッジ列の
  フォーマットに合わせる必要あり。
- `vinta/awesome-python` は `Project Scaffolding` 節（Tools > Command-line Tools）
  に cookiecutter/copier と並列で入る形が自然 — ただし同リストは「ツール」の
  節であり、テンプレート本体の掲載先例が薄い。**掲載可否はメンテナ判断**;
  却下されやすい場合の代替として `awesome-project-templates` /
  `cookiecutter` 系リストや copier Discussions のほうが確度が高い。

## vinta/awesome-python（Project Scaffolding 節、copier の直後）

```markdown
- [daimonion](https://github.com/ConstitutiveTemplates/daimonion) - An opinionated Copier template for Python projects whose questionnaire is formally verified with Z3 (272 rendered witness leaves), with uv, ruff, and generated CI/AGENTS.md.
```

NOTE: 節がツール列挙なら「project template」カテゴリとして PR 文脈を明記すること。

## donhui/awesome-uv（Projects using uv 表の末尾）

```markdown
| [daimonion](https://github.com/ConstitutiveTemplates/daimonion)                 | [![GitHub stars](https://img.shields.io/github/stars/ConstitutiveTemplates/daimonion.svg?style=social&label=Star&maxAge=2592000)](https://github.com/ConstitutiveTemplates/daimonion) | An opinionated Copier template for Python projects — uv-native, Z3-verified questionnaire, generated CI/AGENTS.md. |
```

## copier Discussions — Show and tell（任意、PR 不要）

件名: `daimonion: a Z3-verified Copier template (272 witness leaves)`

本文（骨）: Show HN 下書き（`show-hn-z3-verified-template.md`）の
"How it works" 節を流用し、PR ではなく質問・フィードバック歓迎の形で。

## Astral Discord #showcase（任意）

```
daimonion — an opinionated Copier template for Python projects.
uv-native; the questionnaire's `when:` logic is verified with Z3 and all
272 witness leaves are render-tested in CI. Generated projects get ruff ALL,
basedpyright, hardened Actions (SHA-pinned) and a generated AGENTS.md.
https://github.com/ConstitutiveTemplates/daimonion
```
