---
name: generate-html-doc
description: Generate a self-contained, static HTML design/overview document (diagrams, tables, syntax-highlighted code, click-to-expand source excerpts with live line numbers) that renders correctly in sanitizing viewers like Obsidian's HTML viewer — no JavaScript, no inline SVG. Use when the user asks for an HTML doc, a visual overview, an explainer page, or a "static html page" to clarify a system, plan, or code change.
---

# generate-html-doc

Produces one portable `.html` file that renders the same in a browser, VS Code, and **Obsidian's HTML viewer**, which sanitizes the page. All tooling lives next to this file:

| Path                       | Purpose                                                                                             |
| -------------------------- | --------------------------------------------------------------------------------------------------- |
| `assets/template.src.html` | Starter page: dark theme CSS plus one example of every component                                    |
| `scripts/build.py`         | `SRC → OUT`: fills code excerpts, bakes highlighting, converts SVG to `<img>`, strips JS, validates |
| `scripts/snippets.py`      | Excerpt resolver used by `build.py` (JSON spec format is in its docstring)                          |
| `scripts/hl.py`            | Static highlighter: ts/js/cs/go/…, py, json, sql, shell, yaml                                       |
| `scripts/sanitize.js`      | DOMPurify simulation of the viewer; reports anything it strips                                      |
| `scripts/render.py`        | Headless Edge/Chrome/Chromium screenshots, split into PNG chunks for visual QA                      |

`SKILL_DIR` means the folder containing this file, e.g. `~/.agents/skills/generate-html-doc`, `~/.claude/skills/generate-html-doc`, or a project-local `.agents/skills/generate-html-doc`.

**Requirements:** Python 3, Node.js, Pillow (`python3 -m pip install pillow`, only for `render.py`), and Edge, Chrome or Chromium. Commands below use `python3`; on Windows use `python` or `py`. If the browser is not found, set `HTML_DOC_BROWSER` to its executable.

## Hard rules (sanitized viewers)

What a sanitizing viewer does, and why each rule exists:

1. **No JavaScript.** `<script>` and `on*=` handlers are stripped. Highlighting is baked into static `<span class="tk-*">` at build time.
2. **No inline `<svg>` in the output.** Viewers break `viewBox`, `text-anchor` and markers. Author diagrams as inline SVG in the source; `build.py` turns them into `data:image/svg+xml` `<img>`.
   - Every `<svg>` needs `viewBox="0 0 W H"`.
   - Page CSS does **not** reach inside an image. Style the SVG with attributes, or with a `<style>` _inside_ the `<svg>`.
   - Give `text` elements explicit `text-anchor`. The default font is Segoe UI; set `font-family` on the `<svg>` to change it.
3. **Interactivity is `<details>`/`<summary>` only.** CSS `:hover` is fine. Avoid `:target`, checkbox hacks, `popover` and custom URL schemes.
4. **No fixed or sticky positioning, and nothing external.** That means no remote fonts, images, `@import` or `<link rel=stylesheet>`. Use a static `nav.toc` block at the top, not a sidebar.
5. **All CSS goes in one `<style>` block in `<head>`.** Classes and inline `style=` both survive.

## Workflow

1. **Gather facts first.** Read the code and docs, and use cheap subagents (explore / code-searcher) for broad research. Never invent paths, line numbers or status.
2. Copy `SKILL_DIR/assets/template.src.html` to `<dir>/<name>.src.html` and write the content. Keep the `.src.html` as the editable source (inline SVG, plain code) and treat `<name>.html` as the build output.
3. **Code blocks:** `<pre><code class="lang-json">…</code></pre>`. The language goes in the class; plain text inside (escape `<` `&`); no hand-written spans.
4. **Source references:** never hard-code `file:line`. Put an empty marker pair where the reference belongs, e.g. `<!--src:key-gen--><!--/src:key-gen-->`, and describe it in `<name>.snippets.json` next to the source:
   ```json
   {
     "root": ".",
     "aliases": { "very/long/prefix/": "vlp/" },
     "vars": { "ENG": "very/long/prefix/engine/src/engine.ts" },
     "cap": 120,
     "groups": {
       "key-gen": {
         "note": "optional HTML under the block",
         "items": [
           { "file": "$ENG", "sym": "selectVariant" },
           {
             "file": "$ENG",
             "anchor": "const regenerations =",
             "before": 3,
             "after": 16,
             "title": "regenerate loop"
           },
           {
             "file": "x/utils.ts",
             "enclosing": "_GUID first",
             "title": "import reads _GUID"
           },
           { "file": "scripts/tool.py", "head": 80 },
           { "tree": "very/long/prefix/engine", "depth": 2, "title": "engine" }
         ]
       }
     }
   }
   ```

   - `sym`: a declaration plus its doc comment, to the end of the block. Works for TS/JS, Python, Go, Rust and C#-style methods.
   - `anchor`: the first regex match ± N lines (`nth` picks a later match).
   - `enclosing`: the top-level declaration that contains the match (`indent` raises the allowed declaration indent).
   - `head`: the first N lines of a file.
   - `tree`: a directory listing (skips dot-dirs, `node_modules`, build output).
   - `lines`: a fixed range. Avoid it; it drifts.
   - Each item renders as a collapsed `<details class="src">`: the title and `path:start-end` stay visible, and the code expands with highlighting and line numbers.
   - Add `<span id="snip-date"></span>` somewhere to show when excerpts were generated.
5. **Build:** `python3 SKILL_DIR/scripts/build.py <dir>/<name>.src.html`. A `.src.html` source writes `<name>.html`; any other file is rebuilt in place. Fix every `ERROR`, and read every `WARN`.
6. **QA:** both steps are mandatory before claiming the doc is done.
   ```
   node SKILL_DIR/scripts/sanitize.js <dir>/<name>.html          # prints "wrote <tmp>/<name>.purified.html"
   python3 SKILL_DIR/scripts/render.py <tmp>/<name>.purified.html --width 860
   ```

   - Pass `render.py` the exact path `sanitize.js` printed (the OS temp dir differs per platform).
   - View **every** chunk PNG it prints. All `<details>` are forced open, so excerpt overflow shows up.
   - Check:
     - text clipped or overlapping in diagrams
     - tables squeezed by code
     - unhighlighted code
     - mojibake (`Â·`, `â†’`)
     - empty sections
   - Re-run at `--width 1400` if the user has a wide screen.
   - The render can be delegated to a subagent. Fixes stay with whoever authored the doc.
7. Report what was verified: "checked via DOMPurify simulation + headless render". That is not the real viewer, so say so.

## Layout lessons (each one was a real bug)

- **Diagrams:** `build.py` sets `width:100%;max-width:<W>px;height:auto` so they scale down. Never use `min-width` plus a scroll container; it looks cropped. Wrap them in `<div class="dwrap">`.
- **Code inside tables:** use `table.fixed` with a `<colgroup>`. `td .srcs{contain:inline-size}` stops a wide `<pre>` from stretching the table.
  - If a cell is narrow (under ~40%), move the excerpt into a full-width row below it: `<tr><td colspan="N">…markers…</td></tr>`.
- **`p code, li code {white-space:nowrap}`** must not hit excerpts. The template's `details.src code{white-space:pre}` overrides it; keep that rule.
- **Flow steps / cards with long identifiers:** use `overflow-wrap:anywhere`, never `nowrap`.
- **Encoding:** write files with UTF-8 tools. On Windows, never round-trip through PowerShell 5 `Set-Content`/`Get-Content`; that produces mojibake. Keep `<meta charset="utf-8">`.
- **Editing a built doc that has no `.src.html`:** `build.py` is idempotent on its own output. To edit a diagram, base64-decode the `<img>` `src` back into an SVG, edit it, and inline it again.

## Content conventions

- Open with a **TL;DR** box and a legend of status tags:
  - `built` exists in code
  - `proposal` not built
  - `gap` known defect
  - `decide` needs the user's call
  - `ext` needs an extension
- Number the sections (`0 · Overview`, `1 · …`) and link each one from `nav.toc`.
- Write concisely: tables and diagrams over prose, one idea per callout. Mark every proposal and open decision explicitly.
- Every claim about code gets an excerpt marker, so readers can verify it in place.
- After code changes, re-running `build.py` refreshes all line numbers and excerpts.
