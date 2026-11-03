"""Screenshot an HTML doc into viewable PNG chunks for visual QA (all <details> forced open).

usage: python render.py DOC.html [--width 860] [--out-dir DIR] [--closed]
Needs Edge, Chrome or Chromium (or set HTML_DOC_BROWSER to its executable) and Pillow.
Prints the chunk paths; view every one.
Tip: render the sanitized output of sanitize.js, not the source, to see what the viewer sees.
"""
import argparse
import glob
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

try:
    from PIL import Image
except ImportError:
    sys.exit(f'Pillow missing: "{sys.executable}" -m pip install pillow')

_LOCAL = os.environ.get("LOCALAPPDATA", "")
CANDIDATES = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
              os.path.join(_LOCAL, "Google", "Chrome", "Application", "chrome.exe") if _LOCAL else "",
              "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
              "/Applications/Chromium.app/Contents/MacOS/Chromium",
              os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")]


def browser():
    override = os.environ.get("HTML_DOC_BROWSER")
    if override:
        return override
    for p in CANDIDATES:
        if p and os.path.exists(p):
            return p
    for name in ("msedge", "microsoft-edge", "microsoft-edge-stable", "google-chrome", "google-chrome-stable",
                 "chromium", "chromium-browser", "chrome"):
        if shutil.which(name):
            return shutil.which(name)
    sys.exit("no Edge/Chrome/Chromium found; set HTML_DOC_BROWSER to the browser executable")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("doc")
    ap.add_argument("--width", type=int, default=860)
    ap.add_argument("--out-dir", default=os.path.join(tempfile.gettempdir(), "html_doc_qa"))
    ap.add_argument("--closed", action="store_true", help="keep <details> as authored")
    ap.add_argument("--theme", choices=("light", "dark"), default="light",
                    help="prefers-color-scheme to render with (the default does not follow this machine's setting)")
    a = ap.parse_args()

    os.makedirs(a.out_dir, exist_ok=True)
    stem = re.sub(r"\W+", "_", os.path.splitext(os.path.basename(a.doc))[0])
    for f in glob.glob(os.path.join(a.out_dir, f"{stem}_*.png")):
        os.remove(f)
    with open(a.doc, encoding="utf-8") as f:
        page = f.read()
    if not a.closed:
        page = re.sub(r"<details(?![^>]*\bopen\b)", "<details open", page)

    exe, W, H, STEP = browser(), a.width, 8000, 1600
    profile = os.path.join(tempfile.gettempdir(), "html_doc_qa_profile")
    chunks, n = [], 0
    for idx in range(100):  # page through a tall doc with a negative top margin; tall windows fail
        tmp = os.path.join(a.out_dir, f"_page{idx}.html")
        png = os.path.join(a.out_dir, f"_page{idx}.png")
        # The page is shot in tall windows; a sticky contents rail would repeat at the top of each, so it is pinned in place here.
        shift = f"body{{margin-top:-{idx * H}px !important}}nav.toc{{position:static !important;max-height:none !important}}</style>"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(page.replace("</style>", shift, 1) if "</style>" in page else f"<style>{shift}" + page)
        if os.path.exists(png):
            os.remove(png)
        args = [exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                f"--user-data-dir={profile}", f"--window-size={W},{H}", f"--screenshot={png}"]
        # Blink's preferred color scheme: 0 is dark, 1 is light.
        args.append(f"--blink-settings=preferredColorScheme={0 if a.theme == 'dark' else 1}")
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            args.append("--no-sandbox")  # Chrome refuses to start as root (e.g. Linux containers) without it
        subprocess.run(args + [pathlib.Path(tmp).resolve().as_uri()], capture_output=True, timeout=180)
        for _ in range(60):
            if os.path.exists(png) and os.path.getsize(png) > 0:
                time.sleep(1)
                break
            time.sleep(1)
        im = Image.open(png).convert("RGB")
        px, h = im.load(), im.height
        bg = px[W - 5, h - 5]
        while h > 0 and all(px[x, h - 1] == bg for x in range(0, W, 17)):
            h -= 1
        for y in range(0, h, STEP):
            out = os.path.join(a.out_dir, f"{stem}_{n:02d}.png")
            im.crop((0, y, W, min(y + STEP, h))).save(out)
            chunks.append(out)
            n += 1
        im.close()
        os.remove(tmp)
        os.remove(png)
        if h < H - 50:
            break
    print(f"{len(chunks)} chunks at {W}px:")
    print("\n".join(chunks))


if __name__ == "__main__":
    main()
