"""Fill <!--src:NAME--><!--/src:NAME--> marker pairs with click-to-expand source excerpts.

Spec (JSON sidecar, see SKILL.md):
{
  "root": "..",                                  # source root, relative to the spec file
  "aliases": {"long/prefix/": "lp/"},            # shorten displayed paths
  "vars": {"TE": "src/engine/template-engine.ts"},  # use as "$TE" in "file"/"tree"
  "cap": 120,                                    # max lines per excerpt
  "groups": {
    "NAME": {"note": "optional html under the block", "items": [
      {"file": "$TE", "sym": "selectVariant"},                       # declaration (+ doc comment) to block end
      {"file": "a.ts", "anchor": "regex", "before": 3, "after": 12, "title": "..."},
      {"file": "a.ts", "enclosing": "regex", "title": "...", "indent": 0},  # declaration containing the match
      {"file": "a.py", "head": 80},                                  # first N lines
      {"file": "a.py", "lines": [10, 40]},                           # fixed range (drifts; avoid)
      {"tree": "src/feature", "depth": 2, "title": "...", "skip": ["snapshots"]}  # directory listing
    ]}
  }
}
"""
import datetime
import html
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hl import EXT_LABEL, highlight  # noqa: E402

SKIP_DIRS = {"node_modules", "dist", "build", "out", "venv", ".venv", "__pycache__", "bin", "obj", "coverage"}

CSS = """.srcs{display:flex;flex-direction:column;gap:2px;margin:6px 0 10px}
details.src{background:none;border:0;margin:0;padding:0}details.src[open]{padding:0}
details.src>summary{cursor:pointer;font:11.5px/1.5 Consolas,"Cascadia Code",monospace;color:var(--muted,#8b95a5);padding:1px 0}
details.src>summary:hover,details.src[open]>summary{color:#fff}
details.src>summary b{color:var(--acc,#6cb6ff);font-weight:600;margin-right:4px}
details.src pre{max-height:460px;margin:4px 0 8px;font-size:12px}
details.src code{white-space:pre;overflow-wrap:normal}
.ln{display:inline-block;min-width:3.4em;padding-right:1em;text-align:right;color:#4b5563;user-select:none}
td .srcs{margin:0;contain:inline-size}"""

DECL = r"^\s*(?:export\s+)?(?:default\s+)?(?:declare\s+)?(?:abstract\s+)?(?:async\s+)?(?:function|const|let|var|class|def|interface|type|enum|func|fn)\b"


class Ctx:
    def __init__(self, spec_path):
        with open(spec_path, encoding="utf-8") as f:
            spec = json.load(f)
        self.spec = spec
        self.root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(spec_path)), spec.get("root", ".")))
        self.aliases = spec.get("aliases", {})
        self.vars = spec.get("vars", {})
        self.cap = int(spec.get("cap", 120))
        self._cache = {}

    def path(self, p):
        p = re.sub(r"\$(\w+)", lambda m: self.vars[m.group(1)], p)
        return p.replace("\\", "/")

    def read(self, rel):
        if rel not in self._cache:
            full = os.path.join(self.root, rel)
            if not os.path.isfile(full):
                raise SystemExit(f"file not found: {full}")
            with open(full, encoding="utf-8", errors="replace") as f:
                self._cache[rel] = f.read().splitlines()
        return self._cache[rel]

    def short(self, rel):
        for long, alias in self.aliases.items():
            if rel.startswith(long):
                return alias + rel[len(long):]
        return rel


def _indent(line):
    return len(line) - len(line.lstrip())


def _bracket_deltas(lines, start, is_py):
    """Yield (line_index, depth_after_line, opened) skipping strings/comments, incl. multi-line ones."""
    depth, opened, state = 0, False, None  # state: None | quote char | "`" | "/*" | '"""' | "'''"
    for i in range(start, len(lines)):
        line, j = lines[i], 0
        while j < len(line):
            ch, two, three = line[j], line[j:j + 2], line[j:j + 3]
            if state is None:
                if (not is_py and two == "//") or (is_py and ch == "#"):
                    break
                if not is_py and two == "/*":
                    state, j = "/*", j + 2
                    continue
                if is_py and three in ('"""', "'''"):
                    state, j = three, j + 3
                    continue
                if ch in "\"'`":
                    state = ch
                elif ch in "{[(":
                    depth, opened = depth + 1, True
                elif ch in "}])":
                    depth -= 1
            elif state in ("/*", '"""', "'''"):
                end = "*/" if state == "/*" else state
                if line.startswith(end, j):
                    state, j = None, j + len(end)
                    continue
            elif ch == "\\":
                j += 1
            elif ch == state:
                state = None
            j += 1
        if state in ('"', "'"):
            state = None  # unterminated single-line string: don't leak
        yield i, depth, opened


def block_end(lines, start, is_py):
    if is_py and re.match(r"\s*(?:async\s+)?(?:def|class)\b", lines[start]):
        base, last = _indent(lines[start]), start
        for j in range(start + 1, len(lines)):
            if not lines[j].strip():
                continue
            if _indent(lines[j]) <= base and not lines[j].lstrip().startswith((")", "]", "}")):
                break
            last = j
        return last
    for i, depth, opened in _bracket_deltas(lines, start, is_py):
        if opened and depth <= 0:
            return i
        if not opened and (lines[i].rstrip().endswith(";") or is_py):
            return i
    return len(lines) - 1


def with_doc_comment(lines, start):
    s = start
    while s > 0 and start - s < 12 and re.match(r"\s*(/\*\*|/\*|\*|//|#|@|\[)", lines[s - 1]):
        s -= 1
    return s


def resolve(item, ctx):
    if "tree" in item:
        rel = ctx.path(item["tree"])
        return {"kind": "tree", "title": item.get("title", os.path.basename(rel.rstrip("/"))), "rel": rel,
                "lines": tree_lines(os.path.join(ctx.root, rel), int(item.get("depth", 2)), set(item.get("skip", [])))}
    rel = ctx.path(item["file"])
    lines = ctx.read(rel)
    is_py = rel.endswith(".py")
    if "sym" in item:
        n = re.escape(item["sym"])
        pats = [rf"^\s*(?:export\s+)?(?:default\s+)?(?:declare\s+)?(?:abstract\s+)?(?:async\s+)?"
                rf"(?:function\*?\s+{n}\b|(?:const|let|var)\s+{n}\b|interface\s+{n}\b|type\s+{n}\b|enum\s+{n}\b|"
                rf"class\s+{n}\b|def\s+{n}\b|func\s+(?:\([^)]*\)\s*)?{n}\b|fn\s+{n}\b)",
                rf"^\s*(?:(?:public|private|protected|internal|static|async|readonly|override|virtual|abstract|sealed)\s+)*"
                rf"(?:[\w<>\[\],.?]+\s+)?{n}\s*[(<]"]
        for pat in pats:
            rx = re.compile(pat)
            hit = next((i for i, l in enumerate(lines) if rx.match(l)), None)
            if hit is not None:
                return code(item.get("title", item["sym"]), rel, with_doc_comment(lines, hit), block_end(lines, hit, is_py))
        raise SystemExit(f"symbol not found: {item['sym']} in {rel}")
    if "anchor" in item:
        hit = _find(lines, item["anchor"], rel, item.get("nth", 1))
        return code(item.get("title", item["anchor"]), rel, max(0, hit - int(item.get("before", 3))),
                    min(len(lines) - 1, hit + int(item.get("after", 10))))
    if "enclosing" in item:
        hit = _find(lines, item["enclosing"], rel, item.get("nth", 1))
        max_indent = int(item.get("indent", 0))
        s = hit
        while s > 0 and not (re.match(DECL, lines[s]) and _indent(lines[s]) <= max_indent):
            s -= 1
        return code(item.get("title", item["enclosing"]), rel, with_doc_comment(lines, s), block_end(lines, s, is_py))
    if "head" in item:
        return code(item.get("title", os.path.basename(rel)), rel, 0, min(int(item["head"]), len(lines)) - 1)
    if "lines" in item:
        a, b = item["lines"]
        return code(item.get("title", os.path.basename(rel)), rel, a - 1, min(b, len(lines)) - 1)
    raise SystemExit(f"unknown item kind: {item}")


def _find(lines, pattern, rel, nth):
    rx, seen = re.compile(pattern), 0
    for i, l in enumerate(lines):
        if rx.search(l):
            seen += 1
            if seen == nth:
                return i
    raise SystemExit(f"anchor not found: {pattern} in {rel}")


def code(title, rel, s, e):
    return {"kind": "code", "title": title, "rel": rel, "s": s, "e": e}


def tree_lines(base, depth, skip=frozenset()):
    if not os.path.isdir(base):
        raise SystemExit(f"directory not found: {base}")
    out = []
    for dp, dns, fns in os.walk(base):
        lvl = 0 if dp == base else os.path.relpath(dp, base).count(os.sep) + 1
        dns[:] = sorted(d for d in dns if d not in SKIP_DIRS and d not in skip and not d.startswith(".") and lvl < depth)
        ind = "  " * lvl
        if dp != base:
            out.append(f"{ind[:-2]}{os.path.basename(dp)}/")
        out += [f"{ind}{f}" for f in sorted(fns) if not f.startswith(".")]
    return out


def render(entry, ctx):
    title = html.escape(entry["title"])
    if entry["kind"] == "tree":
        body = "\n".join(html.escape(l, quote=False) for l in entry["lines"])
        return (f'<details class="src"><summary><b>{title}</b> {html.escape(ctx.short(entry["rel"]))}/</summary>'
                f'<pre data-lang="files"><code>{body}</code></pre></details>')
    rel, s, e = entry["rel"], entry["s"], entry["e"]
    lines = ctx.read(rel)
    ext = os.path.splitext(rel)[1].lower()
    label = EXT_LABEL.get(ext, ext.lstrip(".") or "text")
    last = min(e, s + ctx.cap - 1)
    body = "\n".join(f'<span class="ln">{i + 1}</span>{highlight(lines[i], label)}' for i in range(s, last + 1))
    if e > last:
        body += f'\n<span class="ln">…</span><span class="tk-com">{e - last} more lines in the file</span>'
    loc = f"{ctx.short(rel)}:{s + 1}" + (f"-{e + 1}" if e > s else "")
    return (f'<details class="src"><summary><b>{title}</b> {html.escape(loc)}</summary>'
            f'<pre data-lang="{label}"><code>{body}</code></pre></details>')


MARKER = re.compile(r"<!--src:([\w.-]+)-->.*?<!--/src:\1-->", re.S)


def fill(doc, spec_path):
    """Return (new_html, report). Every marker must have a spec group; unused groups are reported."""
    ctx = Ctx(spec_path)
    groups = ctx.spec.get("groups", {})
    found = set(MARKER.findall(doc))
    missing = sorted(found - set(groups))
    if missing:
        raise SystemExit(f"markers without a spec group: {', '.join(missing)}")

    def sub(m):
        name = m.group(1)
        g = groups[name]
        note = f'<p class="muted" style="margin:2px 0 0;font-size:12px">{g["note"]}</p>' if g.get("note") else ""
        block = '<div class="srcs">' + "".join(render(resolve(it, ctx), ctx) for it in g["items"]) + "</div>" + note
        return f"<!--src:{name}-->{block}<!--/src:{name}-->"

    doc = MARKER.sub(sub, doc)
    if found and ".srcs{" not in doc:
        doc = doc.replace("</style>", CSS + "\n</style>", 1)
    doc = re.sub(r'(<span id="snip-date">)[^<]*(</span>)', rf"\g<1>{datetime.date.today().isoformat()}\2", doc)
    unused = sorted(set(groups) - found)
    return doc, {"filled": len(found), "unused_groups": unused}
