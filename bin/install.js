#!/usr/bin/env node
// XEROK RESEARCH installer (Node) — same behavior as install.sh, runnable via:
//   npx github:adbrasi/xerok-research [flags]
// Zero npm dependencies (Node builtins only). The skill itself stays Node-free.
'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');

const SKILL = 'xerok-research';
const PKG_ROOT = path.resolve(__dirname, '..');
const SRC = path.join(PKG_ROOT, 'skills', SKILL);
const BIN_SRC = path.join(PKG_ROOT, 'bin', 'xerok');
const HOME = os.homedir();
const isWin = process.platform === 'win32';

function usage() {
  console.log(`XEROK RESEARCH installer

Usage: npx github:adbrasi/xerok-research [TARGETS] [SCOPE] [OPTIONS]
   or: node bin/install.js [TARGETS] [SCOPE] [OPTIONS]

TARGETS (default: all three):
  --claude       Claude Code        (~/.claude/skills  | ./.claude/skills)
  --codex        Codex CLI          (~/.agents/skills  | ./.codex/skills)
  --agy          Antigravity + Gemini CLI (~/.gemini/skills + antigravity-cli | ./.agents/skills)
  --all          all of the above (default when no target given)

SCOPE (default: --global):
  --global       install for the current user (home dirs)
  --local        install into the current project (CWD)

OPTIONS:
  --no-bin       do not install the \`xerok\` launcher into ~/.local/bin
  --uninstall    remove the skill (and launcher) for the selected targets/scope
  -n, --dry-run  print what would happen, do nothing
  -h, --help     this help

Examples:
  npx github:adbrasi/xerok-research                 # all tools, global
  npx github:adbrasi/xerok-research --claude --codex
  npx github:adbrasi/xerok-research --agy --local
  npx github:adbrasi/xerok-research --uninstall --all`);
}

const opt = { claude: false, codex: false, agy: false, anyTarget: false,
  scope: 'global', bin: true, uninstall: false, dry: false };

for (const a of process.argv.slice(2)) {
  switch (a) {
    case '--claude': opt.claude = true; opt.anyTarget = true; break;
    case '--codex': opt.codex = true; opt.anyTarget = true; break;
    case '--agy': case '--antigravity': case '--gemini': opt.agy = true; opt.anyTarget = true; break;
    case '--all': opt.claude = opt.codex = opt.agy = true; opt.anyTarget = true; break;
    case '--global': opt.scope = 'global'; break;
    case '--local': opt.scope = 'local'; break;
    case '--no-bin': opt.bin = false; break;
    case '--uninstall': opt.uninstall = true; break;
    case '-n': case '--dry-run': opt.dry = true; break;
    case '-h': case '--help': usage(); process.exit(0);
    default: console.error(`unknown option: ${a}`); usage(); process.exit(2);
  }
}
if (!opt.anyTarget) { opt.claude = opt.codex = opt.agy = true; }

if (!fs.existsSync(path.join(SRC, 'SKILL.md'))) {
  console.error(`error: ${path.join(SRC, 'SKILL.md')} not found (broken package?)`);
  process.exit(1);
}

const base = opt.scope === 'global' ? HOME : process.cwd();
const roots = [];
const addRoot = (r) => { if (!roots.includes(r)) roots.push(r); };

if (opt.scope === 'global') {
  if (opt.claude) addRoot(path.join(HOME, '.claude', 'skills'));
  if (opt.codex) addRoot(path.join(HOME, '.agents', 'skills'));
  if (opt.agy) {
    addRoot(path.join(HOME, '.gemini', 'skills'));
    addRoot(path.join(HOME, '.gemini', 'antigravity-cli', 'skills'));
  }
} else {
  if (opt.claude) addRoot(path.join(base, '.claude', 'skills'));
  if (opt.codex) { addRoot(path.join(base, '.codex', 'skills')); addRoot(path.join(base, '.agents', 'skills')); }
  if (opt.agy) addRoot(path.join(base, '.agents', 'skills'));
}

const tag = opt.dry ? '[dry-run] ' : '';
console.log(`XEROK RESEARCH — ${opt.uninstall ? 'uninstall' : 'install'} (${opt.scope})\n`);

for (const root of roots) {
  const dest = path.join(root, SKILL);
  if (opt.uninstall) {
    if (fs.existsSync(dest)) { if (!opt.dry) fs.rmSync(dest, { recursive: true, force: true }); console.log(`  ${tag}removed ${dest}`); }
    else console.log(`  (absent) ${dest}`);
  } else {
    if (!opt.dry) {
      fs.rmSync(dest, { recursive: true, force: true });
      fs.mkdirSync(dest, { recursive: true });
      fs.cpSync(SRC, dest, { recursive: true });
      try { fs.chmodSync(path.join(dest, 'scripts', 'xerok.py'), 0o755); } catch {}
    }
    console.log(`  ${tag}installed -> ${dest}`);
  }
}

// the `xerok` launcher (global scope only; local installs resolve via the repo)
if (opt.bin && opt.scope === 'global') {
  const bindir = path.join(HOME, '.local', 'bin');
  const target = path.join(bindir, 'xerok');
  if (opt.uninstall) {
    if (fs.existsSync(target)) { if (!opt.dry) fs.rmSync(target, { force: true }); console.log(`  ${tag}removed ${target}`); }
  } else if (isWin) {
    console.log('  (windows) skipping unix launcher — call: python <skill-dir>\\scripts\\xerok.py');
  } else {
    if (!opt.dry) {
      fs.mkdirSync(bindir, { recursive: true });
      fs.copyFileSync(BIN_SRC, target);
      fs.chmodSync(target, 0o755);
    }
    console.log(`  ${tag}launcher  -> ${target}`);
    const onPath = (process.env.PATH || '').split(path.delimiter).includes(bindir);
    if (!onPath) console.log(`\n  NOTE: ${bindir} is not on PATH. Add to your shell rc:\n        export PATH="$HOME/.local/bin:$PATH"`);
  }
}

console.log('');
if (opt.uninstall) {
  console.log('Done. Restart your agent CLI to drop the skill.');
} else {
  console.log('Done. Restart your agent CLI, then ask for "deep research on <topic>"');
  console.log('or invoke the skill directly:');
  if (opt.claude) console.log(`  Claude Code : /${SKILL}`);
  if (opt.codex) console.log(`  Codex CLI   : $${SKILL}  (skills load natively; multi_agent=true is the default)`);
  if (opt.agy) console.log('  agy/Gemini  : skill name surfaces at session start; agy reads SKILL.md, Gemini uses activate_skill');
  console.log('\nEngine CLI available as: xerok <init|merge-evidence|postpass|metrics|validate>');
}
