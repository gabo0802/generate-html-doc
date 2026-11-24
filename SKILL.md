---
name: generate-html-doc
description: Generate a self-contained, static HTML design/overview document (diagrams, tables, syntax-highlighted code, click-to-expand source excerpts with live line numbers) that renders correctly in sanitizing viewers like Obsidian's HTML viewer — no JavaScript, no inline SVG. Use when the user asks for an HTML doc, a visual overview, an explainer page, or a "static html page" to clarify a system, plan, or code change.
---

# generate-html-doc

Produces one portable `.html` file that renders the same in a browser, VS Code, and **Obsidian's HTML viewer**, which sanitizes the page. All tooling lives next to this file:

| Path                       | Purpose                                                                                             |
| -------------------------- | --------------------------------------------------------------------------------------------------- |
| `assets/template.src.html` | Starter page: themed CSS (light and dark from one token set), a left contents rail, and one example of every component |
| `assets/themes/*.css`      | Named color themes (light + dark tokens): `forest`, `ocean`, `ember`, `plum`, `graphite`, `paper`    |
| `scripts/build.py`         | `SRC → OUT`: applies the theme, fills code excerpts, renders file trees, bakes highlighting, converts SVG to `<img>`, strips JS, validates |
| `scripts/filetree.py`      | Drafts a `<pre class="filetree">` block from `git diff` (new / mod / del / ren per file)           |
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
4. **Nothing external, and no fixed positioning.** That means no remote fonts, images, `@import` or `<link rel=stylesheet>`; use local font stacks. The one positioned element is the contents rail: `nav.toc` in the template's `.shell` grid is `position:sticky`. A viewer that does not honour it shows the rail as a plain left column that scrolls away, which still reads well; `build.py` warns about sticky or fixed anywhere else.
5. **All CSS goes in one `<style>` block in `<head>`.** Classes and inline `style=` both survive. Never write `<` followed by a letter, `/` or `!` inside the CSS, even in a comment: DOMPurify then drops the whole stylesheet (`build.py` errors on it).

## Workflow

1. **Gather facts first.** Read the code and docs, and use cheap subagents (explore / code-searcher) for broad research. Never invent paths, line numbers or status.
2. Copy `SKILL_DIR/assets/template.src.html` to `<dir>/<name>.src.html`, **pick a theme** (see Themes), and write the content. Keep the `.src.html` as the editable source (inline SVG, plain code) and treat `<name>.html` as the build output.
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
   - `tree`: a directory listing (skips dot-dirs, `node_modules`, build output). `skip` takes names or glob patterns, e.g. `["*.meta"]` for a Unity project.
   - `lines`: a fixed range. Avoid it; it drifts.
   - Each item renders as a collapsed `<details class="src">`: the title and `path:start-end` stay visible, and the code expands with highlighting and line numbers.
   - Add `<span id="snip-date"></span>` somewhere to show when excerpts were generated.
5. **Files touched:** for a feature, change or PR, add a file-tree section (see File trees). Draft it with `python3 SKILL_DIR/scripts/filetree.py [BASE] --repo <repo>`, then group and describe each line.
6. **Build:** `python3 SKILL_DIR/scripts/build.py <dir>/<name>.src.html`. A `.src.html` source writes `<name>.html`; any other file is rebuilt in place. Fix every `ERROR`, and read every `WARN`.
7. **QA:** both steps are mandatory before claiming the doc is done.
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
     - a file tree whose descriptions wrap badly or whose guide lines misalign
   - Re-run at `--width 1400` (with `--closed`, as a reader first sees it) if the user has a wide screen, and once with `--theme dark` (the default is light) to check the dark theme and the diagrams' dark styles.
   - The render can be delegated to a subagent. Fixes stay with whoever authored the doc.
8. Report what was verified: "checked via DOMPurify simulation + headless render". That is not the real viewer, so say so.

## Themes

Every doc has one theme, named in the source head: `<meta name="doc-theme" content="ocean">`. On each build, `build.py` replaces the CSS between `/*theme:start` and `/*theme:end*/` with `assets/themes/<name>.css`; `--theme NAME` on the command line overrides the meta tag.

| Theme      | Look                                                                     | Suits                                   |
| ---------- | ------------------------------------------------------------------------ | --------------------------------------- |
| `forest`   | Deep green on warm white, amber second accent (the default)              | General technical docs                  |
| `ocean`    | Navy and sky blue, burnt-orange second accent                            | Infrastructure, data, cloud, backend     |
| `ember`    | Rust and terracotta on warm neutrals, cool blue second accent            | Product, games, incident write-ups      |
| `plum`     | Violet, amber second accent                                              | Design systems, UI, proposals           |
| `graphite` | Near-monochrome greys, one orange signal color                           | Terse engineering specs, reviews        |
| `paper`    | Serif type on cream, oxblood ink                                         | Long-form explainers, design narratives |

- **Choosing:** use the theme the user names. Otherwise pick the one that best suits the subject and say which in the report, so the user can ask for another. A rebuild with `--theme` is all it takes to switch.
- **Custom:** for a subject with its own palette (a brand, a product UI), set `content="custom"` and hand-edit the tokens in the theme region, keeping every token the theme files define, in all three blocks. To make a palette reusable, save it as a new file in `assets/themes/`.
- Every theme defines both light and dark; the page follows the reader's system setting, and a host's `data-theme` attribute wins.
- **Diagrams follow the theme automatically.** Write SVG colors as `var(--token)` inside the SVG's own `<style>` (e.g. `.box{fill:var(--surface);stroke:var(--line)}`). `build.py` resolves them from the theme and appends a `prefers-color-scheme:dark` copy with the dark values, and sets the SVG's font to the theme's body font. Write no `@media` block yourself in that case; a style that has one is resolved with light values only.

## File trees

For any doc about a feature, change or PR, include a file tree: what was added, changed or removed, grouped by purpose, one short phrase per file. Author it as plain text; `build.py` draws the guide lines, badges, colors and legend.

```html
<pre class="filetree" data-groups="page=New compare page; tree=Tree browser shared with History; links=Links into the page">
ui/
  components/
    CompareBuildsPage/            new  @page   # the new page
      CompareBuildsPage.tsx       new          # page, build pickers, comparison states
      buildCompareReport.ts       new          # CSV export
    EnvBuild/DisplayBuildInfo.tsx mod  @links  # Compare button, shown when a page turns it on
  diffHooks.ts                    mod  @tree   # grouping step split out
  legacy/oldCompare.ts            del          # replaced by CompareBuildsPage
madden/components/App.tsx         mod  @links  # registers the page
</pre>
```

- **Line format:** `INDENT NAME [status] [@group] [# description]`. Nesting comes from indentation (any consistent width). End directories with `/`. Collapse single-child chains into one line (`Log/components/ExpandedRow.tsx`), as `filetree.py` does.
- **Status:** `new`, `mod`, `del` (struck through), `ren`; omit it for context lines that did not change.
- **Groups:** `data-groups="key=Label; ..."` declares up to six, in legend order (colors `--g1`..`--g6`). `@key` colors a line; children inherit their directory's group. Two to four groups that tell the story of the change ("new page", "shared refactor", "entry points") read best; leave unrelated files ungrouped.
- **Descriptions:** a phrase, not a sentence: what the file does *for this change*. Keep them short enough to stay on one line at 860px.
- Put it near the top of a change doc (often right after the TL;DR or as section `0 · Files`), and link to it from the rail.

## Design

The template is a starting point, not a look to keep. A doc should read as made for its subject, not as a generated page.

- **Color comes from the theme** (see Themes). Never hard-code colors in the page body or diagrams; use tokens, so a theme switch restyles everything. A `custom` palette keeps the same rules: 4-6 colors from the subject's own world, a neutral with a slight hue toward the accent, a second accent for warnings, every color a token on `:root`, redefined for dark under `@media (prefers-color-scheme:dark)` guarded by `:root:not([data-theme="light"])` and again under `:root[data-theme="dark"]`.
- **Layout.** A left contents rail (`nav.toc`, numbered sections, the excerpt date) beside one reading column. Open with a header: a mono eyebrow (repo, branch, commit, date), the title, a one- or two-sentence lede, the legend and, when figures matter, stat tiles (`.stats`). It stacks to one column under 900px.
- **Type.** A display stack for headings (heavy weight, slight negative tracking), a body stack, a mono stack; one scale, kept to. Uppercase labels get letter-spacing. Running text stays near 75 characters wide.
- **Restraint.** Borders, fills and radius mark separate objects (cards, tiles, diagrams), not every block. Callouts are a colored left rule, not a filled box. Tables use row rules only. No gradients, no emoji as section markers, no glow or shadows.
- **Diagrams follow the theme.** Page CSS cannot reach a data-URI image, so give each `<svg>` its own `<style>` that uses `var(--token)` colors; `build.py` bakes in the theme's light and dark values (the template's example shows the pattern; arrowheads take a class, not a `fill=` attribute). A host's explicit theme toggle cannot reach inside the image; the diagram follows the system setting.

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
- Number the sections (`0 · Overview`, `1 · …`) and link each one from the `nav.toc` rail; sub-sections use `class="sub"`.
- Write concisely: tables and diagrams over prose, one idea per callout. Mark every proposal and open decision explicitly.
- Every claim about code gets an excerpt marker, so readers can verify it in place.
- After code changes, re-running `build.py` refreshes all line numbers and excerpts.
