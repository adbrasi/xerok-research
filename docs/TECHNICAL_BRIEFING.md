# Claude Code Skills, Plugins & Subagent Orchestration: Technical Reference

**Scope**: Official documentation as of June 2026 (Claude Code v2.1.172+, Agent SDK current).  
**Confidence**: All details from code.claude.com and platform.claude.com docs.

---

## 1. SKILL STRUCTURE

### 1.1 SKILL.md Format & Frontmatter

Every skill is a directory with a `SKILL.md` file at the root. The file contains YAML frontmatter (required) and Markdown instructions (required).

**File location and naming:**
- Personal skills: `~/.claude/skills/<skill-name>/SKILL.md`
- Project skills: `.claude/skills/<skill-name>/SKILL.md`
- Plugin skills: `<plugin>/skills/<skill-name>/SKILL.md` (namespaced as `/plugin-name:skill-name`)

**Frontmatter fields** (all optional except `description` is **recommended**):

```yaml
---
name: my-skill
description: "What this skill does and when to use it. Key use case first."
when_to_use: "Additional context for invocation (trigger phrases, examples)."
argument-hint: "[issue-number]"
arguments: [issue, branch]
disable-model-invocation: false
user-invocable: true
allowed-tools: "Read Grep Bash"
disallowed-tools: "Write Edit"
model: "sonnet"
effort: "high"
context: "fork"
agent: "research-explorer"
hooks: {}
paths: "src/**,lib/**"
shell: "bash"
---

# Skill instructions in Markdown

Your instructions here...
```

**Field details:**

| Field | Type | Behavior |
|-------|------|----------|
| `name` | string | Display label (not command name for directory-based skills). For plugin root `SKILL.md`, sets the invocation name if no frontmatter `name` is present. |
| `description` | string (recommended) | Claude uses this to decide when to invoke automatically. Combined with `when_to_use`, truncated at **1,536 characters** in context. This is the key signal for automatic invocation. |
| `when_to_use` | string | Appended to `description` for auto-invocation decision-making. |
| `argument-hint` | string | UI hint for expected arguments (e.g., `[filename] [format]`). |
| `arguments` | list/string | Named arguments for `$name` substitution in content. Space-separated string or YAML list. Maps to positions: `arguments: [issue, branch]` means `$issue` → first arg, `$branch` → second. |
| `disable-model-invocation` | boolean | Set to `true` to **prevent Claude from invoking automatically**. User can still invoke manually with `/name`. Also **prevents preloading into subagents**. |
| `user-invocable` | boolean | Set to `false` to **hide from `/` menu** and prevent user invocation. Only Claude can invoke automatically. |
| `allowed-tools` | string/list | **Allowlist**: tools Claude can use without permission when skill is active. Space/comma-separated or YAML list. |
| `disallowed-tools` | string/list | **Denylist**: tools removed from Claude's available set while skill is active. Cleared when user sends next message. |
| `model` | string | Override model for this skill: `opus`, `sonnet`, `haiku`, `fable`, full ID, or `inherit`. |
| `effort` | string | Override effort level: `low`, `medium`, `high`, `xhigh`, `max`. |
| `context` | string | Set to `fork` to run in isolated subagent context. |
| `agent` | string | Which subagent type to use when `context: fork`. |
| `hooks` | object | Hooks scoped to this skill's lifecycle (same format as settings.json). |
| `paths` | string/list | Glob patterns limiting when skill is auto-activated (e.g., `src/**,lib/**`). |
| `shell` | string | Shell for `` !`command` `` injection: `bash` (default) or `powershell`. |

**Constraint examples:**
- Kebab-case not required for `name`, but directory names become part of command names.
- `description` + `when_to_use` combined **cannot exceed 1,536 characters** in context.
- Command invocation comes from **directory name**, not frontmatter `name` (except plugin root case).

### 1.2 Dynamic Context Injection

Skills support live command substitution via `` !`command` `` syntax:

```markdown
---
description: Summarize changes and flag risks
---

## Current state

!`git diff HEAD`

!`git log --oneline -5`

## Instructions

Analyze the diff above...
```

Claude Code **executes the command before sending the skill content to Claude**, replacing the line with stdout. This keeps instructions grounded in live data without extra prompt slots.

**Block injection** (multi-line):

````markdown
```!
npm test
```
````

### 1.3 Directory Layout & Supporting Files

```
~/.claude/skills/my-skill/
├── SKILL.md              (required; overview & navigation)
├── reference.md          (optional; detailed API docs)
├── examples.md           (optional; usage examples)
├── scripts/              (optional; executables)
│   ├── helper.py
│   └── lint.sh
└── data/                 (optional; data files)
    └── config.json
```

**Best practices:**
- Keep `SKILL.md` under **500 lines**.
- Move detailed reference to separate files.
- Claude loads `SKILL.md` fully when invoked, but loads supporting files **on-demand** when mentioned or referenced.
- In `SKILL.md`, provide navigation: `See [reference.md](reference.md) for complete API details.`
- Scripts in `scripts/` are **executed by Claude or hooks**, not loaded as text.

### 1.4 String Substitution in Skills

Available variables in skill content:

| Variable | Substitution |
|----------|--------------|
| `$ARGUMENTS` | All arguments passed to skill invocation. If absent, appended as `ARGUMENTS: <value>`. |
| `$ARGUMENTS[N]` | Specific argument by 0-based index (`$ARGUMENTS[0]`, `$ARGUMENTS[1]`). |
| `$N` | Shorthand for `$ARGUMENTS[N]` (e.g., `$0`, `$1`). |
| `$name` | Named argument from `arguments` frontmatter. `arguments: [issue, branch]` → `$issue` = first, `$branch` = second. |
| `${CLAUDE_SESSION_ID}` | Current session ID (for logging, correlation). |
| `${CLAUDE_EFFORT}` | Effort level: `low`, `medium`, `high`, `xhigh`, `max`. |
| `${CLAUDE_SKILL_DIR}` | Directory containing `SKILL.md` (for referencing bundled scripts, regardless of working directory). |

**Example:**
```yaml
---
arguments: [issue, branch]
---

Creating issue #$issue on branch $branch in session ${CLAUDE_SESSION_ID}.
```

### 1.5 Skill Discovery & Progressive Disclosure

**When skills load into context:**
1. **Session start**: Skill **descriptions** only are loaded (not full content).
2. **On invocation**: Full **SKILL.md content** is injected as a message.
3. **Supporting files**: Loaded on-demand when Claude references them (or hook runs).

**How Claude decides to invoke automatically:**
- Claude Code indexes `description` (+ `when_to_use`).
- Combined text is truncated at **1,536 characters**.
- Claude automatically invokes when task matches description.
- `disable-model-invocation: true` hides description from context entirely.

**User invocation**: `/skill-name` works for any skill with `user-invocable: true` (default).

### 1.6 Skill Invocation Control

| Frontmatter | You invoke | Claude invokes | Loaded at start |
|-------------|-----------|----------------|-----------------|
| (default) | Yes | Yes | Description only |
| `disable-model-invocation: true` | Yes | No | Not in context |
| `user-invocable: false` | No | Yes | Description only |

**Use `disable-model-invocation: true` for:**
- Workflows with side effects (`/deploy`, `/commit`, `/send-slack`).
- Actions you want to control manually.

**Use `user-invocable: false` for:**
- Background knowledge (e.g., legacy system context).
- Information Claude should know, but users shouldn't invoke directly.

---

## 2. PLUGINS

### 2.1 Plugin Structure Overview

A plugin is a **self-contained directory** with optional `.claude-plugin/plugin.json` manifest and component directories.

**Directory layout (recommended):**
```
my-plugin/
├── .claude-plugin/
│   └── plugin.json              (optional, but recommended)
├── skills/
│   ├── skill-1/
│   │   ├── SKILL.md
│   │   ├── reference.md
│   │   └── scripts/
│   └── skill-2/
│       └── SKILL.md
├── agents/
│   ├── reviewer.md
│   └── debugger.md
├── hooks/
│   └── hooks.json
├── .mcp.json                    (MCP server configs)
├── .lsp.json                    (LSP server configs)
├── settings.json                (default settings)
├── monitors.json                (background monitors)
├── bin/                         (executables added to PATH)
└── README.md
```

**Important**: Do NOT put `commands/`, `agents/`, `skills/` inside `.claude-plugin/`. Only `plugin.json` goes there.

### 2.2 Plugin Manifest Schema (.claude-plugin/plugin.json)

**Required fields:**
- `name` (string, kebab-case): Unique identifier for namespacing.

**Optional metadata fields:**
```json
{
  "name": "my-plugin",
  "displayName": "My Plugin",
  "version": "1.2.0",
  "description": "What this plugin does",
  "author": {
    "name": "Author Name",
    "email": "author@example.com",
    "url": "https://github.com/author"
  },
  "homepage": "https://docs.example.com",
  "repository": "https://github.com/author/plugin",
  "license": "MIT",
  "keywords": ["keyword1", "keyword2"],
  "defaultEnabled": false
}
```

**Component path fields** (all optional, all relative to plugin root, start with `./`):

```json
{
  "skills": "./custom/skills/",
  "commands": ["./custom/commands/"],
  "agents": "./custom/agents/",
  "hooks": "./config/hooks.json",
  "mcpServers": "./mcp-config.json",
  "outputStyles": "./styles/",
  "lspServers": "./.lsp.json",
  "experimental": {
    "themes": "./themes/",
    "monitors": "./monitors.json"
  }
}
```

**Path behavior:**
- **Replaces default**: `commands`, `agents`, `outputStyles`, `experimental.themes`, `experimental.monitors`.
- **Adds to default**: `skills` (default `skills/` is always scanned).
- **Merge rules**: `hooks`, `mcpServers`, `lspServers` (merge with settings and other sources).

**User configuration:**
```json
{
  "userConfig": {
    "api_endpoint": {
      "type": "string",
      "title": "API Endpoint",
      "description": "Your API endpoint",
      "required": true
    },
    "api_token": {
      "type": "string",
      "title": "API Token",
      "sensitive": true
    }
  }
}
```

Fields available for substitution as `${user_config.KEY}` in MCP/LSP configs, hooks, and monitors. Non-sensitive values stored in `settings.json`; sensitive values in system keychain.

### 2.3 Plugin Installation & Discovery

**Install from marketplace:**
```bash
claude plugin install @anthropics/my-plugin
```

**Install from local directory (development):**
```bash
claude --plugin-dir ./my-plugin
```

**Install from `.zip` archive URL:**
```bash
claude --plugin-url https://example.com/my-plugin.zip
```

**Load multiple plugins at startup:**
```bash
claude --plugin-dir ./plugin-one --plugin-dir ./plugin-two
```

**Reload plugins mid-session** (picks up file changes):
```
/reload-plugins
```

### 2.4 Skills-Directory Plugins

A plugin can live in `~/.claude/skills/my-plugin/` with a `.claude-plugin/plugin.json` manifest. Claude Code auto-loads it as `my-plugin@skills-dir` without marketplace or install step.

**Rules:**
- Workspace trust required.
- Can be updated/removed from `.claude/settings.json`.
- Loads automatically on session start.
- Skills inside are invoked as `/my-plugin:skill-name`.

### 2.5 Converting Standalone to Plugin

```bash
mkdir my-plugin/.claude-plugin
cat > my-plugin/.claude-plugin/plugin.json << 'JSON'
{
  "name": "my-plugin",
  "description": "Migrated from standalone",
  "version": "1.0.0"
}
JSON

cp -r ~/.claude/commands my-plugin/
cp -r ~/.claude/agents my-plugin/
cp -r ~/.claude/skills my-plugin/
```

---

## 3. SUBAGENTS & ORCHESTRATION

### 3.1 Subagent Definition (Agent Files)

Subagents are defined as `.md` files with YAML frontmatter + Markdown system prompt.

**Location:**
- Project-level: `.claude/agents/<name>.md`
- User-level: `~/.claude/agents/<name>.md`
- Plugin-level: `<plugin>/agents/<name>.md` (namespaced as `plugin-name:agent-name`)
- Programmatically (SDK): via `agents` parameter in `ClaudeAgentOptions` or `query()` options.

**File format:**
```markdown
---
name: code-reviewer
description: Reviews code for quality and security. Delegates when PR review is needed.
tools: Read, Glob, Grep
disallowedTools: Write, Edit
model: sonnet
permissionMode: default
maxTurns: 20
skills: api-design-principles, security-review
mcpServers:
  - github
  - slack
memory: project
background: false
effort: high
isolation: worktree
color: blue
initialPrompt: "Start by examining the current PR"
---

You are a code review specialist with expertise in security, performance, and best practices.

When reviewing code:
- Identify security vulnerabilities
- Check for performance issues
- Verify adherence to coding standards
- Suggest specific improvements
```

**Frontmatter fields** (only `name` and `description` required):

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `name` | string | (required) | Unique identifier (lowercase, hyphens). |
| `description` | string | (required) | When Claude should delegate. |
| `tools` | string/list | (inherit all) | Allowlist of tools available to subagent. |
| `disallowedTools` | string/list | (none) | Denylist of tools to remove. |
| `model` | string | `inherit` | `opus`, `sonnet`, `haiku`, `fable`, full ID, or `inherit`. |
| `permissionMode` | string | `default` | `default`, `acceptEdits`, `auto`, `dontAsk`, `bypassPermissions`, or `plan`. |
| `maxTurns` | integer | (unlimited) | Max agentic turns before stop. |
| `skills` | list | (none) | Skills to preload into subagent's context at startup. |
| `mcpServers` | list/object | (none) | MCP servers available to subagent (inline or reference by name). |
| `memory` | string | (none) | `user`, `project`, or `local` for persistent memory across sessions. |
| `background` | boolean | `false` | Set to `true` to always run as background task. |
| `effort` | string | (inherit) | `low`, `medium`, `high`, `xhigh`, `max`. |
| `isolation` | string | (none) | Set to `worktree` to run in isolated git worktree. |
| `color` | string | (auto) | `red`, `blue`, `green`, `yellow`, `purple`, `orange`, `pink`, `cyan`. |
| `initialPrompt` | string | (none) | Auto-submitted first turn when agent is main session. |
| `hooks` | object | (none) | Lifecycle hooks scoped to this subagent. |

### 3.2 Programmatic Subagent Definition (SDK)

In the Agent SDK (TypeScript/Python), define subagents via `agents` parameter:

**TypeScript:**
```typescript
import { query } from "@anthropic-ai/claude-agent-sdk";

for await (const message of query({
  prompt: "Review this code",
  options: {
    allowedTools: ["Read", "Grep", "Glob", "Agent"],
    agents: {
      "code-reviewer": {
        description: "Expert code reviewer",
        prompt: "You are a code review specialist...",
        tools: ["Read", "Grep", "Glob"],
        model: "sonnet"
      }
    }
  }
})) {
  if ("result" in message) console.log(message.result);
}
```

**Python:**
```python
from claude_agent_sdk import query, ClaudeAgentOptions, AgentDefinition

async for message in query(
    prompt="Review this code",
    options=ClaudeAgentOptions(
        allowed_tools=["Read", "Grep", "Glob", "Agent"],
        agents={
            "code-reviewer": AgentDefinition(
                description="Expert code reviewer",
                prompt="You are a code review specialist...",
                tools=["Read", "Grep", "Glob"],
                model="sonnet"
            )
        }
    )
):
    if hasattr(message, "result"):
        print(message.result)
```

### 3.3 Subagent Invocation Patterns

**Automatic delegation:**
Claude decides when to spawn a subagent based on its `description`. Write clear descriptions so Claude recognizes matching tasks.

**Explicit invocation:**
In your prompt, mention the subagent by name:
```
Use the code-reviewer agent to audit this authentication module.
```

**Background execution:**
Subagents with `background: true` run as non-blocking tasks. Parent continues while subagent works independently.

**Parallel execution (SDK):**
When you invoke multiple subagents in one turn via Agent tool or multiple `query()` calls with `resume`, they can run in parallel. Each subagent gets its own context window and returns results independently.

### 3.4 Context Isolation & What Subagents Inherit

**Subagent context starts fresh:**
- Own system prompt (from `prompt` frontmatter or `prompt` in AgentDefinition).
- **Does not receive** parent conversation history or tool results.
- **Does receive**:
  - Project `.claude/CLAUDE.md` (via `settingSources`).
  - Tool definitions (full set or restricted subset via `tools`).
  - Preloaded skills (full content injected at startup via `skills` field).

**Parent receives:**
- Subagent's final message verbatim as Agent tool result.
- Subagent's internal tool calls and reasoning do not surface unless Claude summarizes them.

### 3.5 Passing Data Between Subagents (Fan-Out/Fan-In Pattern)

**Problem:** Subagents don't share memory; only the Agent tool's prompt string connects parent to subagent.

**Solution:** Use parent agent to orchestrate:

**Example: Parallel research tasks**
```markdown
---
name: research-orchestrator
description: Coordinates parallel research across multiple topics
tools: Agent, Read, WebSearch
---

You coordinate research across multiple specialized agents.

When asked to research a topic:
1. Break it into independent subtasks
2. Delegate each to a specialized agent (e.g., researcher, analyst)
3. Aggregate results into a unified summary

Pass context as structured text in the Agent tool prompt.
```

The parent agent:
1. Invokes subagent-A with `Delegate: research A, include [context]`.
2. Receives result-A.
3. Invokes subagent-B with `Delegate: research B, include [context from A]`.
4. Receives result-B.
5. Synthesizes both.

**SDK pattern (sequential):**
```python
async for msg in query(
    prompt="Research topic X",
    options=ClaudeAgentOptions(
        allowed_tools=["Agent", "Read", "WebSearch"],
        agents={
            "analyst": AgentDefinition(description="...", prompt="..."),
            "researcher": AgentDefinition(description="...", prompt="...")
        }
    )
):
    pass  # Main agent orchestrates
```

**SDK pattern (parallel with workflows):**
The `Workflow` tool (TypeScript SDK v0.3.149+) moves orchestration into an executable script, enabling dozens to hundreds of parallel subagents. See [dynamic workflows](#workflows) docs.

### 3.6 Subagent Context Management

**What loads at startup:**
- System prompt + Markdown body.
- Preloaded skills (full content from `skills` field).
- Project CLAUDE.md (if configured).

**Auto-compaction:**
When subagent context fills up, Claude Code compacts and resumes. Subagent transcripts persist independently of parent.

**Resuming subagents:**
```python
# First invocation captures session_id and agentId
session_id = message.session_id
# Extract agentId from Agent tool result text

# Second invocation resumes
async for message in query(
    prompt=f"Resume agent {agent_id} and continue analysis",
    options=ClaudeAgentOptions(resume=session_id, agents=AGENTS)
):
    pass
```

Resumed subagents retain full conversation history.

### 3.7 Nested Subagents

**Depth limit:**
- Subagent at depth 5 cannot spawn further subagents.
- To prevent spawning: omit `Agent` from `tools` or add to `disallowedTools`.

**Configuration:**
Include `Agent` in subagent's `tools` to allow nested delegation.

```markdown
---
name: coordinator
tools: Agent, Read, Bash
---

You can delegate to other agents.
```

### 3.8 Tool Restrictions in Subagents

**Allowlist pattern (recommended for safety):**
```yaml
tools: Read, Grep, Glob
```
Subagent can ONLY use these three tools.

**Denylist pattern:**
```yaml
disallowedTools: Write, Edit
```
Subagent has all tools EXCEPT Write and Edit.

**MCP server filtering:**
```yaml
disallowedTools: mcp__github
```
Removes all tools from `github` MCP server.

**Restrict subagent spawning:**
```yaml
tools: Agent(researcher, analyst), Read, Bash
```
Main agent can only spawn `researcher` or `analyst` subagents.

### 3.9 Common Orchestration Patterns

**1. Isolate high-volume research:**
```markdown
---
name: researcher
description: Explore codebase for patterns. Use when analyzing files or searching code.
tools: Read, Grep, Glob
---
```
Main agent stays clean of file content; researcher returns only summary.

**2. Parallel review:**
```markdown
---
name: security-reviewer
description: Security review. Use in PRs.
tools: Read, Grep, Glob
---

---
name: style-checker
description: Code style review. Use in PRs.
tools: Read, Grep
---
```
Both run in parallel, aggregate results.

**3. Chain specialists:**
```markdown
---
name: planner
description: Plan tasks. Use when starting complex work.
tools: Read, Bash
---

---
name: executor
description: Execute planned tasks.
tools: Bash, Edit, Write
---
```
Planner maps approach; executor acts.

---

## 4. SCRIPTS IN SKILLS

### 4.1 Bundling Scripts

Store scripts in a skill's `scripts/` directory:

```
my-skill/
├── SKILL.md
├── scripts/
│   ├── helper.py
│   ├── analyze.sh
│   └── config.json
└── reference.md
```

### 4.2 Referencing & Executing Scripts

**In SKILL.md, use `${CLAUDE_SKILL_DIR}`:**

```markdown
---
description: Analyze code quality
---

## Prerequisites

Ensure Python 3.8+ is installed.

## Analysis

Run the analysis script:

!`python ${CLAUDE_SKILL_DIR}/scripts/analyze.py --verbose`

Results will be saved to `/tmp/analysis.json`.
```

**Dynamic substitution:**
Claude Code replaces `${CLAUDE_SKILL_DIR}` with the absolute path to the skill directory **before** sending the content to Claude. This works regardless of the current working directory.

### 4.3 Script Execution Context

- Scripts run with **current working directory** set to the project root (or wherever Claude Code was launched).
- Environment variables are passed through; no special isolation.
- Stdout/stderr captured and returned to Claude as tool result.
- Exit code 0 = success; non-zero = failure (but doesn't block Claude from continuing).

### 4.4 Script Parameters & Defaults

For deterministic execution, hardcode defaults in the script itself:

**Python example:**
```python
#!/usr/bin/env python3
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--max-depth", type=int, default=3)
parser.add_argument("--timeout", type=int, default=30)
args = parser.parse_args()

# Use args.max_depth, args.timeout
```

**Bash example:**
```bash
#!/bin/bash
MAX_DEPTH=${1:-3}
TIMEOUT=${2:-30}
```

Claude can override defaults by passing arguments in the skill invocation:
```
/my-skill --max-depth 5
```

### 4.5 Injecting Output into Prompts

Use `` !`command` `` to inline script output:

```markdown
## Git Status

!`git status --short`

## Test Results

!`bash ${CLAUDE_SKILL_DIR}/scripts/run-tests.sh`

Plan next steps based on the above.
```

This is the **dynamic context injection** pattern: Claude Code executes the command and embeds stdout in the skill content before Claude sees it.

---

## 5. COMMANDS & HOOKS (Brief Reference)

### 5.1 Slash Commands

Built-in commands (`/help`, `/compact`, `/model`, etc.) are listed in the commands reference. Bundled skills like `/debug`, `/code-review`, `/loop` work the same way as custom skills.

**Custom commands (legacy):**
Flat `.md` files in `.claude/commands/`:
```
.claude/commands/deploy.md → /deploy
.claude/commands/test.md   → /test
```

**Modern approach:** Use skills in `.claude/skills/` instead.

### 5.2 Hooks Overview

Hooks are automation triggers at specific lifecycle points. They fire **automatically** without user invocation.

**Hook events:**

| Event | When | Frequency | Use |
|-------|------|-----------|-----|
| `SessionStart` | Session begins or resumes | Once per session | Load context, set env |
| `UserPromptSubmit` | User submits prompt | Once per turn | Validate/block prompts |
| `PreToolUse` | Before tool executes | Every tool call | Validate/deny dangerous ops |
| `PostToolUse` | After tool succeeds | Every tool call | Validate results, inject context |
| `Stop` | Agent turn completes | Once per turn | Logging, validation |
| `SessionEnd` | Session ends | Once per session | Cleanup |

**Hook configuration locations:**
1. `~/.claude/settings.json` (user-level)
2. `.claude/settings.json` (project-level)
3. `.claude/settings.local.json` (project-level, not committed)
4. Plugin `hooks/hooks.json`
5. Skill/agent frontmatter `hooks` field

**Hook types:**
- `command`: Shell command receiving JSON on stdin
- `http`: POST to HTTP endpoint
- `mcp_tool`: Call MCP server tool
- `prompt`: Single-turn LLM evaluation
- `agent`: Spawn a subagent

**Matcher patterns:**
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "./scripts/validate.sh"
          }
        ]
      }
    ]
  }
}
```

Matcher can be:
- `"*"` or omitted: match all occurrences
- Alphanumeric + `_` or `|`: exact/list match
- Other characters: regex pattern

**Output format (JSON):**
```json
{
  "continue": true,
  "suppressOutput": false,
  "systemMessage": "Warning...",
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow|deny|ask|defer",
    "updatedToolOutput": "..."
  }
}
```

### 5.3 Hook Path Variables

Available for substitution in hook commands and MCP/LSP configs:

- `${CLAUDE_PROJECT_DIR}`: Project root
- `${CLAUDE_PLUGIN_ROOT}`: Plugin installation directory
- `${CLAUDE_PLUGIN_DATA}`: Plugin persistent data directory (survives updates)

**Exec form** (preferred for paths):
```json
{
  "command": "node",
  "args": ["${CLAUDE_PLUGIN_ROOT}/scripts/lint.js"]
}
```

**Shell form** (wrap paths in quotes):
```json
{
  "command": "bash \"${CLAUDE_PLUGIN_ROOT}\"/check.sh"
}
```

---

## 6. EXAMPLE: ADVANCED DEEP RESEARCH SKILL

Putting it together, here's a multi-component research skill with subagent delegation:

**Directory structure:**
```
.claude/skills/deep-research/
├── SKILL.md
├── reference.md
└── scripts/
    ├── gather-sources.py
    └── validate-sources.sh

.claude/agents/
├── researcher.md
├── analyst.md
└── fact-checker.md
```

**SKILL.md:**
```markdown
---
name: deep-research
description: "Conduct comprehensive deep research on a topic via parallel subagents. Coordinates researcher, analyst, and fact-checker agents."
when_to_use: "Use when the user requests 'deep research', 'quero saber tudo sobre' (want to know everything about), or asks for exhaustive analysis."
arguments: [topic]
disable-model-invocation: false
user-invocable: true
context: fork
agent: research-orchestrator
effort: xhigh
---

# Deep Research Orchestrator

You are coordinating deep research on: **$topic**

## Process

1. Delegate to `researcher` agent to find and summarize sources
2. Delegate to `analyst` agent to synthesize findings
3. Delegate to `fact-checker` agent to validate key claims
4. Aggregate all results into a comprehensive brief

## Supporting resources

See [reference.md](reference.md) for research methodologies and best practices.

## Output format

Return a structured report:
- Executive summary
- Key findings (with sources)
- Synthesis of perspectives
- Fact-check results
- Limitations and uncertainties
```

**reference.md:**
```markdown
# Research Methodology

... detailed guidance ...
```

**agents/researcher.md:**
```markdown
---
name: researcher
description: "Find and summarize sources on a topic. Use for gathering research materials."
tools: Read, Grep, WebSearch, WebFetch
model: sonnet
effort: high
---

You are a research specialist who finds and summarizes authoritative sources.

When asked to research a topic:
1. Use WebSearch to find relevant papers, articles, docs
2. Use WebFetch to extract key information
3. Summarize each source's key points
4. Note publication date and credibility
```

**agents/analyst.md:**
```markdown
---
name: analyst
description: "Synthesize findings from multiple sources into cohesive insights."
tools: Read, Grep
model: opus
effort: xhigh
---

You synthesize disparate research into a unified narrative.

Given source summaries:
1. Identify common themes and contradictions
2. Highlight novel insights
3. Build a coherent synthesis
4. Note gaps in current understanding
```

**agents/fact-checker.md:**
```markdown
---
name: fact-checker
description: "Validate factual claims against reliable sources."
tools: Read, WebSearch, WebFetch
model: sonnet
---

You verify claims against authoritative sources.

For each claim:
1. Search for corroborating evidence
2. Note the reliability of sources
3. Flag unverified claims
4. Provide confidence level (high/medium/low)
```

---

## 7. UNCERTAIN/ADVANCED ITEMS

### 7.1 Questions Without Complete Docs

1. **Max subagent depth**: Documented as "depth 5 cannot spawn further"; exact mechanism (counting from main agent as depth 0 vs 1?) not fully clear, but rule is: no subagent 5 levels deep can spawn.

2. **Skill content re-read**: Skills are loaded once on invocation and stay in conversation; Claude Code does **not** re-read SKILL.md on later turns unless re-invoked. This means write skills as standing instructions, not one-time steps.

3. **Subagent transcript retention**: Transcripts persist independently and are cleaned up based on `cleanupPeriodDays` setting (default 30 days). No explicit retention config beyond that.

4. **Tool budget per subagent**: No documented per-subagent tool budget; budget is context-window based. Subagent context starts fresh, so effective "budget" is the subagent's allocated context window.

5. **WebSearch/WebFetch scope**: Available to subagents if listed in `tools` or not restricted. No explicit context budget or rate limiting docs.

### 7.2 Version & Compatibility

- **Claude Code v2.1.172**: Subagents can spawn nested subagents up to depth 5.
- **Agent SDK TypeScript v0.3.149+**: `Workflow` tool available for orchestrating many subagents.
- **Claude Code v2.1.154**: `defaultEnabled` field in plugin.json.
- **Claude Code v2.1.143**: `displayName` field in plugin.json.

---

## 8. QUICK REFERENCE: COMMAND INVOCATION MATRIX

| Skill location | Command | Namespace |
|---|---|---|
| `.claude/skills/deploy/SKILL.md` | `/deploy` | Project |
| `~/.claude/skills/archive/SKILL.md` | `/archive` | User |
| `my-plugin/skills/review/SKILL.md` | `/my-plugin:review` | Plugin |
| `my-plugin/SKILL.md` (with `name: review` frontmatter) | `/my-plugin:review` | Plugin root |
| `.claude/commands/push.md` | `/push` | Project (legacy) |

---

## 9. LINKS TO OFFICIAL DOCS

- **Skills**: https://code.claude.com/docs/en/skills.md
- **Plugins**: https://code.claude.com/docs/en/plugins.md
- **Plugins Reference**: https://code.claude.com/docs/en/plugins-reference.md
- **Subagents**: https://code.claude.com/docs/en/sub-agents.md
- **Subagents (SDK)**: https://code.claude.com/docs/en/agent-sdk/subagents.md
- **Hooks**: https://code.claude.com/docs/en/hooks.md
- **Commands**: https://code.claude.com/docs/en/commands.md
- **Agent SDK**: https://code.claude.com/docs/en/agent-sdk/overview.md

---

**Document compiled**: June 2026  
**Status**: Authoritative (from code.claude.com + platform.claude.com)
