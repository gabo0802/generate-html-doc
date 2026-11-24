"""Draft a <pre class="filetree"> block from git, for a doc's "files touched" section.

usage: python filetree.py [BASE] [--repo DIR] [--root PREFIX] [--no-untracked]

BASE defaults to the merge-base with main/master (falls back to HEAD). The listing covers committed,
staged and unstaged changes since BASE, plus untracked files. Single-child directory chains are
collapsed (a/b/c.ts), as in a review. Paste the output into the .src.html, then add data-groups,
@group tags and "# description" text; build.py renders it. Line format is documented in SKILL.md.
"""
import argparse
import os
import subprocess
import sys

CODE = {"A": "new", "M": "mod", "D": "del", "R": "ren", "C": "new", "T": "mod"}


def git(repo, *args):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        raise RuntimeError(r.stderr.strip())
    return r.stdout


def default_base(repo):
    for b in ("main", "master", "origin/main", "origin/master"):
        try:
            return git(repo, "merge-base", "HEAD", b).strip()
        except RuntimeError:
            continue
    return "HEAD"


def changes(repo, base, untracked):
    out = {}
    for line in git(repo, "diff", "--name-status", "-M", base).splitlines():
        parts = line.split("\t")
        st = CODE.get(parts[0][0], "mod")
        if st == "ren":
            out[parts[2]] = ("ren", "renamed from " + parts[1])
        else:
            out[parts[1]] = (st, "")
    if untracked:
        for p in git(repo, "ls-files", "--others", "--exclude-standard").splitlines():
            out.setdefault(p, ("new", ""))
    return out


def build_tree(paths):
    root = {}
    for p, info in paths.items():
        node = root
        parts = p.split("/")
        for d in parts[:-1]:
            node = node.setdefault(d + "/", {})
        node[parts[-1]] = info
    return root


def collapse(name, node):
    """Merge directory chains with a single directory child: a/ + b/ -> a/b/ ; a/ + only-file -> a/file."""
    while isinstance(node, dict) and len(node) == 1:
        (k, v), = node.items()
        name, node = name + k, v
    return name, node


def emit(node, depth, lines):
    dirs = sorted((k, v) for k, v in node.items() if isinstance(v, dict))
    files = sorted((k, v) for k, v in node.items() if not isinstance(v, dict))
    for k, v in dirs + files:
        name, v = collapse(k, v) if isinstance(v, dict) else (k, v)
        if isinstance(v, dict):
            lines.append(("  " * depth + name, "", ""))
            emit(v, depth + 1, lines)
        else:
            lines.append(("  " * depth + name, v[0], v[1]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base", nargs="?")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--root", default="", help="only list paths under this prefix")
    ap.add_argument("--no-untracked", action="store_true")
    a = ap.parse_args()
    try:
        base = a.base or default_base(a.repo)
        ch = changes(a.repo, base, not a.no_untracked)
    except RuntimeError as e:
        sys.exit(f"git failed: {e}")
    if a.root:
        pre = a.root.rstrip("/") + "/"
        ch = {k[len(pre):]: v for k, v in ch.items() if k.startswith(pre)}
    if not ch:
        sys.exit(f"no changes since {base}")
    lines = []
    emit(build_tree(ch), 0, lines)
    width = max(len(n) for n, _, _ in lines) + 2
    print('<pre class="filetree" data-groups="g1=First group; g2=Second group">')
    for name, st, desc in lines:
        row = name.ljust(width) + st.ljust(5)
        print((row + "  # " + desc if desc else row).rstrip())
    print("</pre>")
    print(f"<!-- {len(ch)} files changed since {base[:12]} -->", file=sys.stderr)


if __name__ == "__main__":
    main()
