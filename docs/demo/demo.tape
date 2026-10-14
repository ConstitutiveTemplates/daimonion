# 15-second demo: personal data reaches a log sink -> daimonion flags it ->
# the AGENTS.md rule (GDPR + APPI + CCPA) -> the masked fix scans clean.
#
# Render: `vhs docs/demo/demo.tape` (run from the repo root) writes
# docs/demo/demo.gif. Uses the REAL daimonion CLI via `uv run` on
# docs/demo/fixture/, so the recording is reproducible. `sh docs/demo/demo.sh`
# runs the same beats without recording (add --fast to skip the pauses).

Output "docs/demo/demo.gif"

Require uv

Set Shell "bash"
Set FontFamily "DejaVu Sans Mono"
Set FontSize 15
Set Width 980
Set Height 620
Set Padding 12
Set TypingSpeed 28ms

Type "cat docs/demo/fixture/app.py" Sleep 400ms Enter
Sleep 1s

Type "uv run daimonion --no-emoji scan docs/demo/fixture/app.py --repo docs/demo/fixture" Sleep 400ms Enter
Sleep 2s

Type "sed -n '/個人データ/,/rulebook/p' docs/demo/fixture/AGENTS.md" Sleep 400ms Enter
Sleep 2s

Type "cat docs/demo/fixture/app_fixed.py" Sleep 400ms Enter
Sleep 1s

Type "uv run daimonion --no-emoji scan docs/demo/fixture/app_fixed.py --repo docs/demo/fixture" Sleep 400ms Enter
Sleep 2s
