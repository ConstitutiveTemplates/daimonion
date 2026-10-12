from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Iterable
from pathlib import Path

import yaml

from law_lint.models import MatchFinding, Rule
from law_lint.rules import DEFAULT_RULES


class Linter:
    """Core scanning engine that inspects files or git diffs against compliance rules."""

    def __init__(self, rules: list[Rule] | None = None) -> None:
        self.rules: list[Rule] = rules if rules is not None else [Rule.from_dict(d) for d in DEFAULT_RULES]
        self._compiled: list[tuple[Rule, re.Pattern[str]]] = []
        for r in self.rules:
            try:
                pattern = re.compile(r.triggers)
                self._compiled.append((r, pattern))
            except re.error:
                continue

    @classmethod
    def from_yaml(cls, path: str | Path) -> Linter:
        """Load rules from an external YAML file (e.g. from good-future-codex, law-map, or REGISTRY.yml)."""
        yaml_path = Path(path)
        content = yaml_path.read_text(encoding="utf-8")
        data = yaml.safe_load(content)
        rules_data = data.get("sections") or data.get("rules") or data
        if not isinstance(rules_data, list):
            msg = "Expected YAML list of rules under 'sections', 'rules', or top-level"
            raise TypeError(msg)
        rules = []
        for item in rules_data:
            if not isinstance(item, dict):
                continue
            # If the item references a file (like REGISTRY.yml), try to enrich it
            if "file" in item and not item.get("triggers"):
                file_rel = str(item["file"])
                candidates = [
                    yaml_path.parent / file_rel,
                    yaml_path.parent.parent / file_rel,
                    yaml_path.parent.parent.parent / file_rel,
                ]
                sec_file = next((c for c in candidates if c.is_file()), None)
                if sec_file is not None:
                    sec_text = sec_file.read_text(encoding="utf-8")
                    t_m = re.search(r"> Triggers:\s*`([^`]+)`", sec_text)
                    title_m = re.search(r"^# (.+)$", sec_text, re.MULTILINE)
                    summary_m = re.search(r"> 要約:\s*(.+?)(?=\n>|\n\n)", sec_text, re.DOTALL)
                    item["triggers"] = t_m.group(1).strip() if t_m else ""
                    item["title"] = title_m.group(1).strip() if title_m else item.get("id", "")
                    item["summary"] = (
                        summary_m.group(1).replace("\n> ", " ").strip() if summary_m else item.get("why", "")
                    )
            rules.append(Rule.from_dict(item))
        return cls(rules)

    def scan_text(self, text: str, file_path: str = "<stdin>") -> list[MatchFinding]:
        """Scan a string line by line and report matched findings."""
        findings: list[MatchFinding] = []
        for line_no, line in enumerate(text.splitlines(), start=1):
            line_str = line.strip()
            if not line_str or line_str.startswith("#") and "Triggers:" in line_str:
                continue
            for rule, pattern in self._compiled:
                match = pattern.search(line)
                if match:
                    findings.append(
                        MatchFinding(
                            rule=rule,
                            file_path=file_path,
                            line_number=line_no,
                            matched_text=match.group(0),
                            context_line=line.strip(),
                        )
                    )
        return findings

    def scan_file(self, path: str | Path) -> list[MatchFinding]:
        """Scan a single file."""
        p = Path(path)
        if not p.is_file():
            return []
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
        return self.scan_text(content, file_path=str(p))

    def scan_paths(self, paths: Iterable[str | Path]) -> list[MatchFinding]:
        """Recursively scan given paths."""
        findings: list[MatchFinding] = []
        for p in paths:
            target = Path(p)
            if target.is_file():
                findings.extend(self.scan_file(target))
            elif target.is_dir():
                for root, _, files in os.walk(target):
                    if any(part.startswith(".") for part in Path(root).parts):
                        continue
                    for f in files:
                        file_path = Path(root) / f
                        if file_path.suffix.lower() in {
                            ".py",
                            ".ts",
                            ".js",
                            ".go",
                            ".rs",
                            ".java",
                            ".md",
                            ".yml",
                            ".yaml",
                            ".toml",
                        }:
                            findings.extend(self.scan_file(file_path))
        return findings

    def scan_git_diff(self, *, staged: bool = False, repo_dir: str | Path = ".") -> list[MatchFinding]:
        """Inspect added or modified lines in git diff."""
        cmd = ["git", "diff", "--unified=0"]
        if staged:
            cmd.append("--cached")

        try:
            res = subprocess.run(cmd, cwd=str(repo_dir), capture_output=True, text=True, check=True)
            diff_text = res.stdout
        except (subprocess.SubprocessError, OSError):
            return []

        findings: list[MatchFinding] = []
        current_file = ""
        current_line_no = 0

        for line in diff_text.splitlines():
            if line.startswith("+++ b/"):
                current_file = line.removeprefix("+++ b/")
            elif line.startswith("@@"):
                m = re.search(r"\+(\d+)", line)
                if m:
                    current_line_no = int(m.group(1)) - 1
            elif line.startswith("+") and not line.startswith("+++"):
                current_line_no += 1
                added_content = line[1:]
                for rule, pattern in self._compiled:
                    match = pattern.search(added_content)
                    if match:
                        findings.append(
                            MatchFinding(
                                rule=rule,
                                file_path=current_file,
                                line_number=current_line_no,
                                matched_text=match.group(0),
                                context_line=added_content.strip(),
                            )
                        )

        return findings
