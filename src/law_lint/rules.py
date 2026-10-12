from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from law_lint.models import Rule

# Canonical compliance rules derived from ConstitutiveTemplates ethical and legal baseline
DEFAULT_RULES: list[dict[str, str]] = [
    {
        "id": "licensing-drift",
        "title": "ライセンス変動 — 依存の現行ライセンス確認とBSL/SSPL等の混入防止",
        "triggers": r"(?i)\b(licen[cs]e|bsl|busl|sspl|rsal|elv2|copyleft|gpl|agpl|lgpl|terraform|opentofu|elasticsearch|redis|source-available)\b",
        "summary": "依存追加・更新時に現行ライセンスを確認し、BSL/SSPL等のソース可用ライセンスや強copyleftを不注意に混入させない。",
        "category": "licensing",
        "enforcement": "L2",
        "gate": "true",
    },
    {
        "id": "deprecated-crypto",
        "title": "枯れた暗号 — MD5/SHA1署名・DES・TLS 1.0/1.1 の新規採用禁止",
        "triggers": r"(?i)\b(md5|sha-?1(?!6|384|512)|(?<!3)des(?!c)|3des|triple-?des|rc4|sslv?3|tls\s?1\.[01]|sha1withrsa|rsa[_ /-]?1024)\b",
        "summary": "署名や完全性用途にMD5/SHA-1を用いない。TLSは1.2以上を強制し、レガシー暗号の新規コード混入を避ける。",
        "category": "crypto",
        "enforcement": "L2",
        "gate": "",
    },
    {
        "id": "pqc-standards",
        "title": "PQC標準 — 新規暗号選択はML-KEM/ML-DSA系またはハイブリッド",
        "triggers": r"(?i)\b(ml-kem|ml-dsa|slh-dsa|kyber|dilithium|sphincs|fips\s?20[345]|pqc|post-quantum)\b",
        "summary": "FIPS 203/204/205標準名で扱い、KEMと署名の役割を分離し、旧暗号単独の新規採用を避ける。",
        "category": "crypto",
        "enforcement": "L1",
        "gate": "project_type in ['library', 'cli'] or web_api",
    },
    {
        "id": "pki-trust-chain",
        "title": "PKIチェーン再編 — 中間証明書・発行チェーンのハードコード禁止",
        "triggers": r"(?i)\b(certificat|trust\s?store|ca_bundle|pinn|openssl|requests|httpx|urllib3|mtls|root\s?ca|intermediate)\b",
        "summary": "中間証明書や特定CAチェーンをコード内に固定・同梱しない。OS/システムのtrust storeに従う。",
        "category": "crypto",
        "enforcement": "L1",
        "gate": "project_type in ['micropython', 'cli'] or web_api",
    },
    {
        "id": "personal-data-privacy",
        "title": "個人データ — 取得の最小化と削除経路・ログマスキング",
        "triggers": r"(?i)\b(pii|personal[_ ]?data|personal[_ ]?information|gdpr|privacy|user[_ ]?data|deletion|right[_ ]?to[_ ]?erasure|consent|retention)\b",
        "summary": "個人識別情報を取得・保存する前に必要性を問い、ログへの平文出力や外部API流出を防ぎ、削除経路を確保する。",
        "category": "privacy",
        "enforcement": "L2",
        "gate": "'personal-data' in domain_traits or 'face-recognition' in domain_traits or 'medtech' in domain_traits",
    },
    {
        "id": "ai-copyright",
        "title": "AIと著作権 — 取得・学習・RAGコードの適法性とrobots.txt遵守",
        "triggers": r"(?i)\b(scrap|crawl|robots\.txt|rag|retrieval|fine-?tun|dataset|embedding|public[- ]domain|copyright)\b",
        "summary": "robots.txtやサイト拒否措置を回避しない。表現そのものを無許諾で再出力するRAG設計を避ける。",
        "category": "copyright",
        "enforcement": "L1",
        "gate": "project_type == 'cli' or data_science_layout",
    },
    {
        "id": "llm-appsec",
        "title": "LLMアプリ/MCP安全設計 — 最小権限・人間承認・出力検証",
        "triggers": r"(?i)\b(llm|prompt|agent|tool[_-]?call|mcp|openai|anthropic|chat|completion|system[_-]?prompt|guardrail)\b",
        "summary": "ツール権限は最小CRUDに絞り、破壊的・不可逆操作には人間承認を挟み、LLM出力を直接shellに渡さない。",
        "category": "security",
        "enforcement": "L2",
        "gate": "mcp_effective",
    },
    {
        "id": "prompt-injection",
        "title": "プロンプトインジェクション — 外部入力を指示として直接実行しない",
        "triggers": r"(?i)\b(prompt[- ]?injection|jailbreak|indirect[- ]?injection|agent[- ]?hijack|system[- ]?prompt|tool[_-]?poisoning)\b",
        "summary": "指示と外部データを厳格に分離し、外部テキストをシステム指示として信用しない。",
        "category": "security",
        "enforcement": "L1",
        "gate": "mcp_effective",
    },
    {
        "id": "eu-cra-compliance",
        "title": "EU CRA — 商用製品の脆弱性報告(24h)とSBOM義務",
        "triggers": r"(?i)\b(cra|sbom|cyclonedx|vulnerability|vulnerabilities|cve|incident[_ ]?report|resilience|enisa)\b",
        "summary": "能動的悪用を知ったら24時間以内に報告する。SBOMを作成し、依存関係の出所を説明可能にする。",
        "category": "security",
        "enforcement": "L1",
        "gate": "'commercial' in distribution",
    },
    {
        "id": "eu-eaa-accessibility",
        "title": "欧州アクセシビリティ法 (EAA) — EN 301 549 / WCAG 2.1 AA 準拠",
        "triggers": r"(?i)\b(accessib|aria|wcag|a11y|axe|alt=|tabindex|focus|screen[ -]reader|en[ -]301[ -]549)\b",
        "summary": "EU市場向けUI/フロントエンドコンポーネントにおいて、EN 301 549 (WCAG 2.1 AA相当)を満たす設計を行う。",
        "category": "accessibility",
        "enforcement": "L1",
        "gate": "web_api",
    },
    {
        "id": "jp-external-transmission",
        "title": "外部送信規律 (電気通信事業法) — サードパーティ送信の事前開示",
        "triggers": r"(?i)\b(cookie|consent|gtm|gtag|analytics|opt-?out|tracker|advertis|sdk|tag manager)\b",
        "summary": "日本向けWeb/アプリでサードパーティタグやSDKを使用する場合、送信先・情報・目的を平易に事前開示する。",
        "category": "privacy",
        "enforcement": "L1",
        "gate": "web_api",
    },
    {
        "id": "kyushu-ntp-hygiene",
        "title": "NTPハイジーン — 福岡大などの静的NTP参照禁止",
        "triggers": r"(?i)\b(133\.100\.9\.2|133\.100\.11\.8|clock\.nc\.fukuoka-u\.ac\.jp)\b",
        "summary": "単一の教育機関・特定NTPサーバーをコードにハードコードせず、ntp.pool.org等のプールを使用する。",
        "category": "security",
        "enforcement": "L2",
        "gate": "",
    },
]


#: Typed view of :data:`DEFAULT_RULES`; prefer this over re-parsing the raw dicts.
BUILTIN_RULES: tuple[Rule, ...] = tuple(Rule.from_dict(item) for item in DEFAULT_RULES)


def _enrich_from_section_file(item: dict[str, Any], yaml_path: Path) -> None:
    """Fill a file-referencing entry (e.g. REGISTRY.yml) with triggers/title/summary scraped from its section file."""
    if "file" not in item or item.get("triggers"):
        return
    file_rel = str(item["file"])
    candidates = (
        yaml_path.parent / file_rel,
        yaml_path.parent.parent / file_rel,
        yaml_path.parent.parent.parent / file_rel,
    )
    sec_file = next((c for c in candidates if c.is_file()), None)
    if sec_file is None:
        return
    sec_text = sec_file.read_text(encoding="utf-8")
    triggers = re.search(r"> Triggers:\s*`([^`]+)`", sec_text)
    title = re.search(r"^# (.+)$", sec_text, re.MULTILINE)
    summary = re.search(r"> 要約:\s*(.+?)(?=\n>|\n\n)", sec_text, re.DOTALL)
    item["triggers"] = triggers.group(1).strip() if triggers else ""
    item["title"] = title.group(1).strip() if title else item.get("id", "")
    item["summary"] = summary.group(1).replace("\n> ", " ").strip() if summary else item.get("why", "")


def load_rules_from_data(data: Any, *, yaml_path: Path | None = None) -> list[Rule]:
    """Build rules from parsed YAML: a list, or a mapping holding ``sections``/``rules``."""
    if isinstance(data, Mapping):
        rules_data = data.get("sections") or data.get("rules") or data
    else:
        rules_data = data
    if not isinstance(rules_data, list):
        msg = "Expected YAML list of rules under 'sections', 'rules', or top-level"
        raise TypeError(msg)
    rules: list[Rule] = []
    for item in rules_data:
        if not isinstance(item, dict):
            continue
        if yaml_path is not None:
            _enrich_from_section_file(item, yaml_path)
        rules.append(Rule.from_dict(item))
    return rules


def load_rules_from_yaml(path: str | Path) -> list[Rule]:
    """Load rules from an external YAML file (e.g. from good-future-codex, law-map, or REGISTRY.yml)."""
    resolved = Path(path)
    data = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    return load_rules_from_data(data, yaml_path=resolved)
