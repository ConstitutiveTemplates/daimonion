# demo.tape — 15-second README demo (vhs, Charmbracelet)
#
# Human runs:  vhs notes/outreach/demo.tape   (produces demo.gif; README embed)
# Prereq: vhs installed, repo root has .venv built (`uv sync --locked`).
# The tape renders the `cli` preset non-interactively so no typing races exist.
# Name origin: "daimonion" is Socrates' inner voice — it never tells you what
# to do, only when to stop — matching the template's warning/abort/refusal
# posture (and the etymology of Unix *daemon*).

Output demo.gif

Set FontSize 16
Set Width 1200
Set Height 675
Set Theme "Catppuccin Mocha"
Set Padding 24
Set TypingSpeed 60ms

# 1. The one-liner a new user runs
Type "uvx --from git+https://github.com/ConstitutiveTemplates/daimonion.git daimonion new my-cli --preset cli"
Enter
Sleep 8s

# 2. What landed
Type "tree my-cli -L 1 -a | head -20"
Enter
Sleep 3s

# 3. The payoff: the full check suite is already wired
Type "cd my-cli && task check"
Enter
Sleep 10s
