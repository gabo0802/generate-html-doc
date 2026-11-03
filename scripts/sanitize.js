// Approximate a sanitizing HTML viewer (e.g. Obsidian) with DOMPurify, then report what was removed.
// usage: node sanitize.js IN.html [OUT.html]   (OUT defaults to <tmp>/<name>.purified.html)
// Deps auto-install once into ~/.cache/generate-html-doc (override with HTML_DOC_DEPS).
const fs = require("fs"), os = require("os"), path = require("path"), { execSync } = require("child_process");
const { createRequire } = require("module");

const deps = process.env.HTML_DOC_DEPS || path.join(os.homedir(), ".cache", "generate-html-doc");
if (!fs.existsSync(path.join(deps, "node_modules", "dompurify")) || !fs.existsSync(path.join(deps, "node_modules", "jsdom"))) {
  fs.mkdirSync(deps, { recursive: true });
  console.log("installing dompurify + jsdom into", deps);
  execSync(`npm install --prefix "${deps}" dompurify jsdom --silent --no-audit --no-fund`, { stdio: "inherit" });
}
const req = createRequire(path.join(deps, "index.js"));
const { JSDOM } = req("jsdom");
const P = req("dompurify")(new JSDOM("").window);

const [inp, outArg] = process.argv.slice(2);
if (!inp) { console.error("usage: node sanitize.js IN.html [OUT.html]"); process.exit(2); }
const out = outArg || path.join(os.tmpdir(), path.basename(inp).replace(/\.html?$/i, "") + ".purified.html");
const src = fs.readFileSync(inp, "utf8");
const clean = P.sanitize(src, { WHOLE_DOCUMENT: true, ADD_TAGS: ["style"] });
fs.writeFileSync(out, clean);

const removed = {};
for (const r of P.removed) {
  const k = r.element ? `<${r.element.nodeName.toLowerCase()}>` : `@${r.attribute && r.attribute.name} on <${r.from && r.from.nodeName.toLowerCase()}>`;
  removed[k] = (removed[k] || 0) + 1;
}
const count = (re) => (clean.match(re) || []).length;
console.log("wrote", out);
console.log(`kept: style ${clean.includes("<style")} | data-URI imgs ${count(/<img[^>]+src="data:image\//g)} | tk spans ${count(/class="tk-/g)} | details ${count(/<details/g)}`);
const significant = Object.entries(removed).filter(([k]) => !/^<(html|head|body|meta|title|#comment)>$/.test(k));
console.log(significant.length ? "REMOVED: " + significant.map(([k, v]) => `${k} x${v}`).join(", ") : "removed: nothing significant");
