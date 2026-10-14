#!/bin/sh
# 15-second demo: personal data reaches a log sink -> daimonion flags it ->
# AGENTS.md shows the sourced rule (GDPR + APPI + FTC Wyndham) -> the masked
# fix scans clean.
# Reproducible: drives the REAL daimonion CLI against docs/demo/fixture/.
# Usage: sh docs/demo/demo.sh            # full story, ~15s of typing pauses
#        sh docs/demo/demo.sh --fast      # no pauses (CI / verification)
set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"
FIX="$HERE/fixture"
DAIMONION="uv run --project $HERE/../.. daimonion --no-emoji"

pause() { [ "${1:-}" = "--fast" ] || sleep 1; }

echo '$ cat fixture/app.py'
sed -n '1,20p' "$FIX/app.py"
pause "$@"

echo ""
echo '$ daimonion scan fixture/app.py'
$DAIMONION scan "$FIX/app.py" --repo "$FIX" || true
pause "$@"

echo ""
echo '$ sed -n "/個人データ/,/kanon/p" fixture/AGENTS.md  # GDPR + APPI + FTC Wyndham'
sed -n '/個人データ/,/kanon/p' "$FIX/AGENTS.md"
pause "$@"

echo ""
# fix: a pseudonym replaces the raw identifier, then re-scan
sed -n '1,20p' "$FIX/app_fixed.py"
$DAIMONION scan "$FIX/app_fixed.py" --repo "$FIX"
