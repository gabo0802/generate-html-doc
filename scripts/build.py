"""Build a sanitizer-proof static HTML doc (works in Obsidian's HTML viewer and similar).

usage: python build.py SRC.html [-o OUT.html] [--spec SPEC.json]

Steps: fill <!--src:*--> excerpts (if a spec exists) -> bake syntax highlighting into
<pre><code class="lang-X"> blocks -> convert inline <svg> to data-URI <img> -> strip scripts and
on* handlers -> structural checks. SRC "name.src.html" defaults to OUT "name.html"; otherwise in place.
Spec defaults to "<name>.snippets.json" next to SRC.
"""
import argparse
import base64
import html
import os
import re
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hl import highlight  # noqa: E402
import snippets  # noqa: E402

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
XML_ENT = {"amp", "lt", "gt", "quot", "apos"}
warnings = []


def bake_code(doc):
    def sub(m):
        text = html.unescape(re.sub(r"<[^>]+>", "", m.group(3)))
        return m.group(1) + highlight(text, m.group(2)) + "</code>"
    doc, n = re.subn(r'(<code\b[^>]*\bclass="(?:lang|language)-([\w+#-]+)"[^>]*>)(.*?)</code>', sub, doc, flags=re.S)
    doc = re.sub(r'<pre(?![^>]*\bdata-lang=)([^>]*)>(\s*<code\b[^>]*\bclass="(?:lang|language)-([\w+#-]+)")',
                 r'<pre data-lang="\3"\1>\2', doc)
    return doc, n


def svg_to_img(doc):
    def sub(m):
        svg = m.group(0)
        open_tag = re.match(r"<svg\b[^>]*>", svg).group(0)
        vb = re.search(r'viewBox="\s*[-\d.]+[\s,]+[-\d.]+[\s,]+([\d.]+)[\s,]+([\d.]+)\s*"', open_tag)
        if not vb:
            raise SystemExit("inline <svg> without viewBox=\"0 0 W H\": " + open_tag[:120])
        w, h = (str(round(float(x))) for x in vb.groups())
        style = re.search(r'\bstyle="([^"]*)"', open_tag)
        label = re.search(r'\baria-label="([^"]*)"', open_tag) or re.search(r"<title>(.*?)</title>", svg, re.S)
        tag = open_tag
        for attr in ("width", "height", "style", "class", "xmlns"):
            tag = re.sub(rf'\s{attr}="[^"]*"', "", tag)
        extra = "" if "font-family=" in tag else ' font-family="Segoe UI, system-ui, sans-serif"'
        tag = tag[:-1] + f' xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}"{extra}>'
        svg = tag + svg[len(open_tag):]
        svg = re.sub(r"&(\w+);", lambda e: e.group(0) if e.group(1) in XML_ENT else f"&#{ord(html.unescape(e.group(0))[0])};", svg)
        if re.search(r'\sclass="', svg) and "<style" not in svg:
            warnings.append("svg uses class= but has no internal <style>; page CSS does NOT reach data-URI images")
        try:
            ET.fromstring(svg)
        except ET.ParseError as e:
            raise SystemExit(f"svg is not well-formed XML ({e}): {svg[:160]}")
        b64 = base64.b64encode(svg.encode("utf-8")).decode()
        alt = html.escape(label.group(1).strip() if label else "diagram")
        st = f"display:block;width:100%;max-width:{w}px;height:auto;" + (style.group(1) if style else "margin:8px 0")
        return f'<img class="diagram" alt="{alt}" style="{st}" src="data:image/svg+xml;base64,{b64}">'
    n = len(re.findall(r"<svg\b", doc))
    return re.sub(r"<svg\b.*?</svg>", sub, doc, flags=re.S), n


def strip_unsafe(doc):
    doc, ns = re.subn(r"\s*<script\b.*?</script>", "", doc, flags=re.S | re.I)
    nh = 0
    handler = re.compile(r'(<[a-zA-Z][^<>]*?)\son[a-z]+=(?:"[^"]*"|\'[^\']*\')', re.I)
    while True:
        doc, k = handler.subn(r"\1", doc)
        if not k:
            break
        nh += k
    if ns or nh:
        warnings.append(f"removed {ns} <script> and {nh} on* handlers (they do not run in sanitized viewers)")
    return doc


class Balance(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack, self.errors = [], []

    def handle_starttag(self, tag, attrs):
        if tag not in VOID:
            self.stack.append((tag, self.getpos()[0]))

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if self.stack and self.stack[-1][0] == tag:
            self.stack.pop()
        else:
            self.errors.append(f"line {self.getpos()[0]}: </{tag}> but open is {self.stack[-1] if self.stack else None}")


def check(doc):
    b = Balance()
    b.feed(doc)
    errors = b.errors[:10] + [f"unclosed <{t}> from line {ln}" for t, ln in b.stack[:10]]
    for pat, msg in [(r"position\s*:\s*(fixed|sticky)", "position:fixed/sticky (sanitized viewers often clip it)"),
                     (r"@import|<link\b[^>]*stylesheet", "external stylesheet (blocked offline / by viewers)"),
                     (r"url\(\s*['\"]?https?:", "remote url() in CSS"), (r"<iframe\b", "<iframe>"),
                     (r":target\b", ":target selector (unreliable without real anchors)"),
                     (r'<img\b[^>]*src="https?:', "remote image")]:
        if re.search(pat, doc, re.I):
            warnings.append("found " + msg)
    return errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("-o", "--out")
    ap.add_argument("--spec")
    a = ap.parse_args()
    src = os.path.abspath(a.src)
    stem = re.sub(r"(\.src)?\.html?$", "", src, flags=re.I)
    out = a.out or (stem + ".html" if src.lower().endswith(".src.html") else src)
    spec = a.spec or stem + ".snippets.json"
    with open(src, encoding="utf-8") as f:
        doc = f.read()

    report = {}
    if os.path.exists(spec):
        doc, report = snippets.fill(doc, spec)
    elif re.search(r"<!--src:", doc):
        raise SystemExit(f"doc has <!--src:--> markers but no spec at {spec}")
    doc, n_code = bake_code(doc)
    doc, n_svg = svg_to_img(doc)
    doc = strip_unsafe(doc)
    errors = check(doc)

    with open(out, "w", encoding="utf-8", newline="") as f:
        f.write(doc)
    print(f"wrote {out} ({len(doc.encode()) // 1024} KB)")
    print(f"code blocks {n_code} | svgs->img {n_svg} | excerpt groups {report.get('filled', 0)}"
          + (f" | unused spec groups {report['unused_groups']}" if report.get("unused_groups") else ""))
    for w in dict.fromkeys(warnings):
        print("WARN", w)
    for e in errors:
        print("ERROR", e)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
