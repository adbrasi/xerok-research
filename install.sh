#!/usr/bin/env bash
# XEROK RESEARCH installer — installs the skill for Claude Code, Codex CLI, and
# the Antigravity (agy) / Gemini CLI, globally or into the current project.
#
# Skill dirs (source-verified):
#   Claude Code  global ~/.claude/skills            local ./.claude/skills
#   Codex CLI    global ~/.agents/skills            local ./.codex/skills (+ ./.agents/skills)
#   agy/Gemini   global ~/.gemini/skills            local ./.agents/skills
#                       + ~/.gemini/antigravity-cli/skills (agy CLI)
set -euo pipefail

SKILL="xerok-research"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$SCRIPT_DIR/skills/$SKILL"
BIN_SRC="$SCRIPT_DIR/bin/xerok"

# defaults
do_claude=0 do_codex=0 do_agy=0 any_target=0
scope="global"
install_bin=1
uninstall=0
dry=0

usage() {
  cat <<'USAGE'
XEROK RESEARCH installer

Usage: ./install.sh [TARGETS] [SCOPE] [OPTIONS]

TARGETS (default: all three):
  --claude       Claude Code        (~/.claude/skills  | ./.claude/skills)
  --codex        Codex CLI          (~/.agents/skills  | ./.codex/skills)
  --agy          Antigravity + Gemini CLI (~/.gemini/skills + antigravity-cli | ./.agents/skills)
  --all          all of the above (default when no target given)

SCOPE (default: --global):
  --global       install for the current user (home dirs)
  --local        install into the current project ($PWD)

OPTIONS:
  --no-bin       do not install the `xerok` launcher into ~/.local/bin
  --uninstall    remove the skill (and launcher) for the selected targets/scope
  -n, --dry-run  print what would happen, do nothing
  -h, --help     this help

Examples:
  ./install.sh                      # all tools, global
  ./install.sh --claude --codex     # only Claude Code + Codex, global
  ./install.sh --agy --local        # Antigravity/Gemini into this project
  ./install.sh --uninstall --all     # remove everywhere (global)
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --claude) do_claude=1; any_target=1 ;;
    --codex)  do_codex=1;  any_target=1 ;;
    --agy|--antigravity|--gemini) do_agy=1; any_target=1 ;;
    --all)    do_claude=1; do_codex=1; do_agy=1; any_target=1 ;;
    --global) scope="global" ;;
    --local)  scope="local" ;;
    --no-bin) install_bin=0 ;;
    --uninstall) uninstall=1 ;;
    -n|--dry-run) dry=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

[ "$any_target" -eq 1 ] || { do_claude=1; do_codex=1; do_agy=1; }

[ -f "$SRC/SKILL.md" ] || { echo "error: $SRC/SKILL.md not found (run from the repo)"; exit 1; }

run() { if [ "$dry" -eq 1 ]; then echo "  [dry-run] $*"; else eval "$*"; fi; }

# collect destination skill ROOTS (without the skill name) for the chosen scope
roots=()
add_root() { for r in "${roots[@]:-}"; do [ "$r" = "$1" ] && return; done; roots+=("$1"); }

if [ "$scope" = "global" ]; then
  [ "$do_claude" -eq 1 ] && add_root "$HOME/.claude/skills"
  [ "$do_codex"  -eq 1 ] && add_root "$HOME/.agents/skills"
  if [ "$do_agy" -eq 1 ]; then
    add_root "$HOME/.gemini/skills"
    add_root "$HOME/.gemini/antigravity-cli/skills"
  fi
else
  [ "$do_claude" -eq 1 ] && add_root "$PWD/.claude/skills"
  if [ "$do_codex" -eq 1 ]; then add_root "$PWD/.codex/skills"; add_root "$PWD/.agents/skills"; fi
  [ "$do_agy" -eq 1 ] && add_root "$PWD/.agents/skills"
fi

action="install"; [ "$uninstall" -eq 1 ] && action="uninstall"
echo "XEROK RESEARCH — $action ($scope)"
echo

for root in "${roots[@]:-}"; do
  dest="$root/$SKILL"
  if [ "$uninstall" -eq 1 ]; then
    if [ -d "$dest" ]; then run "rm -rf \"$dest\""; echo "  removed $dest"; else echo "  (absent) $dest"; fi
  else
    run "rm -rf \"$dest\""
    run "mkdir -p \"$dest\""
    run "cp -R \"$SRC/.\" \"$dest/\""
    run "chmod +x \"$dest/scripts/xerok.py\" 2>/dev/null || true"
    echo "  installed -> $dest"
  fi
done

# the `xerok` launcher (global scope only; local installs resolve via the repo)
if [ "$install_bin" -eq 1 ] && [ "$scope" = "global" ]; then
  bindir="$HOME/.local/bin"
  target="$bindir/xerok"
  if [ "$uninstall" -eq 1 ]; then
    [ -f "$target" ] && { run "rm -f \"$target\""; echo "  removed $target"; }
  else
    run "mkdir -p \"$bindir\""
    run "cp \"$BIN_SRC\" \"$target\""
    run "chmod +x \"$target\""
    echo "  launcher  -> $target"
    case ":$PATH:" in
      *":$bindir:"*) : ;;
      *) echo; echo "  NOTE: $bindir is not on PATH. Add to your shell rc:"; echo "        export PATH=\"\$HOME/.local/bin:\$PATH\"";;
    esac
  fi
fi

echo
if [ "$uninstall" -eq 1 ]; then
  echo "Done. Restart your agent CLI to drop the skill."
else
  echo "Done. Restart your agent CLI, then ask for \"deep research on <topic>\""
  echo "or invoke the skill directly:"
  [ "$do_claude" -eq 1 ] && echo "  Claude Code : /$SKILL  (or /plugin if packaged)"
  [ "$do_codex"  -eq 1 ] && echo "  Codex CLI   : \$$SKILL  (skills load natively; needs multi_agent=true, the default)"
  [ "$do_agy"    -eq 1 ] && echo "  agy/Gemini  : skill name surfaces at session start; agy reads SKILL.md, Gemini uses activate_skill"
  echo
  echo "Engine CLI available as: xerok <init|merge-evidence|postpass|metrics|validate>"
fi
