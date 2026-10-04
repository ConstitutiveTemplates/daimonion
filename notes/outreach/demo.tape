# demo.tape — 15-second README demo (vhs, Charmbracelet)
#
# Human runs:  vhs notes/outreach/demo.tape   (produces demo.gif; README embed)
# Prereq: vhs installed, repo root has .venv built (`uv sync --locked`).
# The tape renders the `cli` preset non-interactively so no typing races exist.

Output demo.gif

Set FontSize 16
Set Width 1200
Set Height 675
Set Theme "Catppuccin Mocha"
Set Padding 24
Set TypingSpeed 60ms

# 1. The one-liner a new user runs
Type "uvx --from git+https://github.com/ConstitutiveTemplates/foundry.git foundry new my-cli --preset cli"
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
