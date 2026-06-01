# Installing the GRAIL skill

The skill is one folder — `skills/grail/` in the GRAIL repo — that lives at
different paths depending on which agent framework is running it.

## Per-framework install paths

| Framework | User-scope install | Project-scope install |
|---|---|---|
| Claude Code (CLI + claude.ai) | `~/.claude/skills/grail/` | `<repo>/.claude/skills/grail/` |
| OpenAI Codex | `~/.agents/skills/grail/` | `<repo>/.agents/skills/grail/` |
| Hermes (Nous) | local Skills Hub directory | n/a |

## Quick install (manual)

Symlink (preferred — fast updates when you `git pull` the GRAIL repo):

```bash
# Claude Code, user scope
mkdir -p ~/.claude/skills
ln -s "$(pwd)/skills/grail" ~/.claude/skills/grail

# Codex, user scope
mkdir -p ~/.agents/skills
ln -s "$(pwd)/skills/grail" ~/.agents/skills/grail

# Project scope (e.g. for a repo where you want the skill bundled):
mkdir -p .claude/skills
ln -s "$(realpath skills/grail)" .claude/skills/grail
```

Copy instead of symlink when symlinks aren't supported (e.g. some Windows
configurations):

```bash
cp -R skills/grail ~/.claude/skills/grail
```

## Runtime requirements

The skill installs `grail` via `pip` on first use through
`scripts/setup.sh`. The setup script is idempotent — safe to call every
session.

| Runtime | Network | Outcome |
|---|---|---|
| Claude Code | yes | `setup.sh` pip-installs GRAIL the first time |
| OpenAI Codex | yes | same |
| Hermes | yes | same |
| Anthropic API code-execution | **no** | not supported; the skill cannot pip-install at runtime |

If you have GRAIL pre-installed in the runtime, `setup.sh` short-circuits
with `status="already-installed"`.

## Required environment variables

GRAIL's LLM and embedding clients read API keys from environment
variables. The skill does **not** require any single vendor — it's whatever
your `grail.yaml` references. Common ones:

| Endpoint | Env var |
|---|---|
| OpenAI | `OPENAI_API_KEY` |
| DeepInfra | `DEEPINFRA_API_KEY` |
| Anthropic | `ANTHROPIC_API_KEY` |
| Together | `TOGETHER_API_KEY` |
| Groq | `GROQ_API_KEY` |

Memory mode can run **without an API key** — pass `embeddings=None` in
Python or omit the embeddings stanza in `grail.yaml`. Recall mode also
needs zero LLM. Other search modes (local / cascade / global / document /
agent) require an LLM.

## Verifying the install

```bash
bash ~/.claude/skills/grail/scripts/setup.sh
# → {"ok": true, "status": "installed", "grail_version": "0.1.0"}

python ~/.claude/skills/grail/scripts/env_check.py
# → {"ok": true, "data": {"grail_version": "...", "python": "...", "extras_present": [...]}}
```

## Updating

Symlinked installs update automatically when you `git pull` the GRAIL
repo. Copied installs require re-copying.

## Uninstalling

Remove the symlink / folder at the framework-specific path. The
`~/.grail/registry.json` workspace registry is separate — delete it
yourself if you want a clean slate:

```bash
rm ~/.grail/registry.json
```

(Per-project `meta.json` files are not touched; they are authoritative
and survive a registry wipe.)
