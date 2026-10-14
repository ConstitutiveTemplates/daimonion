from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from daimonion.models import Rule

# Canonical compliance rules derived from politeuma ethical and legal baseline.
# Titles and summaries are English (canonical); src/daimonion/locales/ja.yml
# carries their Japanese translation for `--lang ja`.
# Every builtin is a keyword rule (topic vocabulary, not the violation itself),
# so it is a reminder: L1 when the vocabulary is specific (md5, a hardcoded NTP
# address), L0 when it is broad (license, agent, requests). Only a rule with
# "kind": "structural" may be L2 and fail --strict; see models.effective_enforcement.
DEFAULT_RULES: list[dict[str, str]] = [
    {
        "id": "licensing-drift",
        "title": "License drift — check dependencies' current licenses; keep BSL/SSPL and the like out",
        "triggers": r"(?i)\b(licen[cs]e|bsl|busl|sspl|rsal|elv2|copyleft|gpl|agpl|lgpl|terraform|opentofu|elasticsearch|redis|source-available)\b",
        "summary": "When adding or updating a dependency, check its current license and do not let source-available licenses (BSL, SSPL, ...) or strong copyleft slip in unnoticed.",
        "category": "licensing",
        "enforcement": "L0",
        "gate": "true",
    },
    {
        "id": "deprecated-crypto",
        "title": "Deprecated cryptography — no new MD5/SHA-1 signatures, DES, or TLS 1.0/1.1",
        "triggers": r"(?i)\b(md5|sha-?1(?!6|384|512)|(?<!3)des(?!c)|3des|triple-?des|rc4|sslv?3|tls\s?1\.[01]|sha1withrsa|rsa[_ /-]?1024)\b",
        "summary": "Do not use MD5 or SHA-1 for signatures or integrity. Enforce TLS 1.2 or later and keep legacy ciphers out of new code.",
        "category": "crypto",
        "enforcement": "L1",
        "gate": "",
    },
    {
        "id": "pqc-standards",
        "title": "PQC standards — choose ML-KEM/ML-DSA or hybrids for new cryptography",
        "triggers": r"(?i)\b(ml-kem|ml-dsa|slh-dsa|kyber|dilithium|sphincs|fips\s?20[345]|pqc|post-quantum)\b",
        "summary": "Use the FIPS 203/204/205 standard names, keep the KEM and signature roles apart, and do not adopt a classical-only scheme in new designs.",
        "category": "crypto",
        "enforcement": "L1",
        "gate": "project_type in ['library', 'cli'] or web_api",
    },
    {
        "id": "pki-trust-chain",
        "title": "PKI chain changes — do not hardcode intermediate certificates or issuing chains",
        "triggers": r"(?i)\b(certificat|trust\s?store|ca_bundle|pinn|openssl|requests|httpx|urllib3|mtls|root\s?ca|intermediate)\b",
        "summary": "Do not pin or bundle intermediate certificates or a specific CA chain in code; follow the OS or system trust store.",
        "category": "crypto",
        "enforcement": "L0",
        "gate": "project_type in ['micropython', 'cli'] or web_api",
    },
    {
        "id": "personal-data-privacy",
        "title": "Personal data — minimise collection, provide a deletion path, mask logs",
        "triggers": r"(?i)\b(pii|personal[_ ]?data|personal[_ ]?information|gdpr|privacy|user[_ ]?data|deletion|right[_ ]?to[_ ]?erasure|consent|retention)\b",
        "summary": "Ask whether personal identifiers are needed before collecting or storing them, keep them out of plaintext logs and external APIs, and provide a deletion path.",
        "category": "privacy",
        "enforcement": "L1",
        "gate": "'personal-data' in domain_traits or 'face-recognition' in domain_traits or 'medtech' in domain_traits",
    },
    {
        "id": "ai-copyright",
        "title": "AI and copyright — lawful collection, training, and RAG code; respect robots.txt",
        "triggers": r"(?i)\b(scrap|crawl|robots\.txt|rag|retrieval|fine-?tun|dataset|embedding|public[- ]domain|copyright)\b",
        "summary": "Do not bypass robots.txt or a site's opt-out. Avoid RAG designs that reproduce protected expression verbatim without permission.",
        "category": "copyright",
        "enforcement": "L1",
        "gate": "project_type == 'cli' or data_science_layout",
    },
    {
        "id": "llm-appsec",
        "title": "LLM apps / MCP security — least privilege, human approval, output validation",
        "triggers": r"(?i)\b(llm|prompt|agent|tool[_-]?call|mcp|openai|anthropic|chat|completion|system[_-]?prompt|guardrail)\b",
        "summary": "Limit tool permissions to the minimum CRUD, require human approval before destructive or irreversible actions, and never pass LLM output straight to a shell.",
        "category": "security",
        "enforcement": "L0",
        "gate": "mcp_effective",
    },
    {
        "id": "prompt-injection",
        "title": "Prompt injection — never execute external input as instructions",
        "triggers": r"(?i)\b(prompt[- ]?injection|jailbreak|indirect[- ]?injection|agent[- ]?hijack|system[- ]?prompt|tool[_-]?poisoning)\b",
        "summary": "Keep instructions and external data strictly apart; never trust external text as system instructions.",
        "category": "security",
        "enforcement": "L1",
        "gate": "mcp_effective",
    },
    {
        "id": "eu-cra-compliance",
        "title": "EU CRA — 24-hour vulnerability reporting and SBOM duties for commercial products",
        "triggers": r"(?i)\b(cra|sbom|cyclonedx|vulnerability|vulnerabilities|cve|incident[_ ]?report|resilience|enisa)\b",
        "summary": "Report an actively exploited vulnerability within 24 hours of becoming aware of it. Produce an SBOM and keep dependency provenance explainable.",
        "category": "security",
        "enforcement": "L1",
        "gate": "'commercial' in distribution",
    },
    {
        "id": "eu-eaa-accessibility",
        "title": "European Accessibility Act (EAA) — EN 301 549 / WCAG 2.1 AA",
        "triggers": r"(?i)\b(accessib|aria|wcag|a11y|axe|alt=|tabindex|focus|screen[ -]reader|en[ -]301[ -]549)\b",
        "summary": "Design UI and front-end components for the EU market to meet EN 301 549 (equivalent to WCAG 2.1 AA).",
        "category": "accessibility",
        "enforcement": "L1",
        "gate": "web_api",
    },
    {
        "id": "jp-external-transmission",
        "title": "External transmission rules (Japan, Telecommunications Business Act) — disclose third-party transmissions up front",
        "triggers": r"(?i)\b(cookie|consent|gtm|gtag|analytics|opt-?out|tracker|advertis|sdk|tag manager)\b",
        "summary": "When a Japan-facing website or app uses third-party tags or SDKs, disclose the recipients, the data sent, and the purpose in plain language beforehand.",
        "category": "privacy",
        "enforcement": "L1",
        "gate": "web_api",
    },
    {
        "id": "kyushu-ntp-hygiene",
        "title": "NTP hygiene — no static references to Fukuoka University or similar NTP servers",
        "triggers": r"(?i)\b(133\.100\.9\.2|133\.100\.11\.8|clock\.nc\.fukuoka-u\.ac\.jp)\b",
        "summary": "Do not hardcode a single academic or specific NTP server in code; use a pool such as pool.ntp.org.",
        "category": "security",
        "enforcement": "L1",
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
    """Load rules from an external YAML file or a law-map ``checks/`` directory.

    A directory is consumed as a law-map checkout: every ``*.yml`` file
    beneath it is parsed as a check spec (``id``/``obligation``/``level``
    plus optional ``triggers``) and mapped to a rule. Files whose
    basename starts with ``_`` are skipped.
    """
    resolved = Path(path)
    if resolved.is_dir():
        return load_rules_from_checks_dir(resolved)
    data = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    return load_rules_from_data(data, yaml_path=resolved)


def load_rules_from_checks_dir(checks_root: str | Path) -> list[Rule]:
    """Load one rule per law-map check spec under ``checks_root`` (recursive)."""
    root = Path(checks_root)
    rules: list[Rule] = []
    for spec_file in sorted(root.rglob("*.yml")):
        if spec_file.name.startswith("_"):
            continue
        try:
            data = yaml.safe_load(spec_file.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(data, dict):
            continue
        rules.append(Rule.from_check_spec(data))
    return rules
