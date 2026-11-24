# generate-html-doc

An agent skill that generates a self-contained, static HTML design/overview document: diagrams, tables, syntax-highlighted code, and click-to-expand source excerpts with live line numbers. The output has no JavaScript and no inline SVG, so it renders the same in a browser, VS Code, and sanitizing viewers like Obsidian's HTML viewer.

- **Themes:** six built-in palettes, each with light and dark: `forest` (default), `ocean`, `ember`, `plum`, `graphite`, `paper`. Ask for one by name ("make it ocean"), or switch with `build.py --theme NAME`. Diagrams pick up the theme too.
- **File trees:** change docs include a colored "files touched" tree (new / mod / del badges, grouped by purpose, one line per file), drafted from `git diff`.

Works on Windows, macOS and Linux.

## Install

Requires Node.js 22.20 or later.

```sh
# Into the current project
npx skills add gabo0802/generate-html-doc

# Globally, for every project
npx skills add gabo0802/generate-html-doc -g

# Only for one agent
npx skills add gabo0802/generate-html-doc -g -a claude-code
```

The CLI detects your installed coding agents (Claude Code, GitHub Copilot, Cursor, Codex, …) and installs into the right skill folders.

Manage it later with:

```sh
npx skills list                       # show installed skills
npx skills check                      # check for updates
npx skills update generate-html-doc   # update
npx skills remove generate-html-doc   # uninstall
```

## Requirements

| Tool | Used by | Notes |
| --- | --- | --- |
| Python 3 | `build.py`, `render.py` | `python3` on macOS/Linux, `python` or `py` on Windows |
| Node.js | `sanitize.js` | Installs `dompurify` + `jsdom` once into `~/.cache/generate-html-doc` (override with `HTML_DOC_DEPS`) |
| Pillow | `render.py` | `python3 -m pip install pillow` |
| Edge, Chrome or Chromium | `render.py` | Found automatically; otherwise set `HTML_DOC_BROWSER` to the executable |

## Usage

Ask your agent for an "HTML doc", "visual overview" or "explainer page"; it follows [SKILL.md](SKILL.md). The scripts can also be run by hand (`SKILL_DIR` is wherever the skill was installed):

```sh
# Start from the template
cp SKILL_DIR/assets/template.src.html docs/overview.src.html

# Optional: draft a "files touched" tree from git, then paste it into the source
python3 SKILL_DIR/scripts/filetree.py main --repo .

# Build: applies the theme, fills excerpts, renders file trees, bakes highlighting, converts SVG to <img>, validates
python3 SKILL_DIR/scripts/build.py docs/overview.src.html          # -> docs/overview.html
python3 SKILL_DIR/scripts/build.py docs/overview.src.html --theme paper   # same doc, another theme

# QA: simulate the sanitizing viewer, then screenshot the result
node SKILL_DIR/scripts/sanitize.js docs/overview.html              # prints the purified file path
python3 SKILL_DIR/scripts/render.py <purified path> --width 860    # prints PNG chunk paths
```

## Layout

| Path | Purpose |
| --- | --- |
| [SKILL.md](SKILL.md) | Instructions the agent follows |
| [assets/template.src.html](assets/template.src.html) | Starter page with every component |
| [assets/themes/](assets/themes) | Named color themes (light + dark token sets) |
| [scripts/build.py](scripts/build.py) | Source → static HTML build and validation |
| [scripts/filetree.py](scripts/filetree.py) | Drafts a file-tree block from `git diff` |
| [scripts/snippets.py](scripts/snippets.py) | Source-excerpt resolver (spec format in its docstring) |
| [scripts/hl.py](scripts/hl.py) | Static syntax highlighter |
| [scripts/sanitize.js](scripts/sanitize.js) | DOMPurify simulation of the viewer |
| [scripts/render.py](scripts/render.py) | Headless browser screenshots for visual QA |
