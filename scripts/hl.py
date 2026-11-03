"""Static syntax highlighter: emits <span class="tk-*"> (no JS needed at view time)."""
import html
import re

_D = r'"(?:[^"\\\n]|\\.)*"'
_S = r"'(?:[^'\\\n]|\\.)*'"
_C_KW = (r"\b(?:export|default|const|let|var|await|async|if|else|for|while|do|switch|case|break|continue|of|in|"
         r"return|function|new|delete|typeof|instanceof|interface|type|enum|class|extends|implements|import|from|as|"
         r"throw|try|catch|finally|public|private|protected|static|readonly|void|null|undefined|true|false|this|"
         r"using|namespace|struct|func|fn|package)\b")

RULES = {
    "ts": [(r"//.*|/\*.*?\*/|^[ \t]*\*.*", "com"), (_D + "|" + _S + r"|`[^`]*`?", "str"), (_C_KW, "kw"),
           (r"\b[A-Za-z_$][\w$]*(?=\()", "fn"), (r"\b\d+(?:\.\d+)?\b", "num"), (r"[{}()\[\];,.:=]", "pun")],
    "py": [(r"#.*", "com"), (r'"""|\'\'\'|' + _D + "|" + _S, "str"),
           (r"\b(?:def|class|return|if|elif|else|for|while|in|import|from|with|as|try|except|finally|raise|None|"
            r"True|False|and|or|not|lambda|yield|async|await|pass|break|continue|global)\b", "kw"),
           (r"\b[A-Za-z_]\w*(?=\()", "fn"), (r"\b\d+(?:\.\d+)?\b", "num")],
    "json": [(_D + r"(?=\s*:)", "key"), (_D, "str"), (r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", "num"),
             (r"\b(?:true|false|null)\b", "lit"), (r"[{}\[\],:]", "pun")],
    "sql": [(r"--.*|/\*.*?\*/", "com"), (_S, "str"), (r"`[^`]*`", "key"),
            (r"(?i)\b(?:SELECT|FROM|WHERE|AND|OR|NOT|IN|IS|NULL|INSERT|INTO|VALUES|UPDATE|SET|DELETE|CREATE|ALTER|"
             r"DROP|TABLE|VIEW|INDEX|TRIGGER|PROCEDURE|FUNCTION|EVENT|SCHEDULE|EVERY|BEFORE|AFTER|FOR|EACH|ROW|"
             r"BEGIN|END|IF|THEN|ELSE|ELSEIF|DECLARE|CALL|USE|JOIN|LEFT|RIGHT|INNER|ON|AS|GROUP|BY|ORDER|LIMIT|"
             r"PRIMARY|KEY|EXISTS|REPLACE|SIGNAL|SQLSTATE|RETURN|RETURNS|DISTINCT|UNION|ALL|CASE|WHEN|NEW|OLD)\b", "kw"),
            (r"\b\w+(?=\()", "fn"), (r"\b\d+\b", "num"), (r"[*(),;=]", "pun")],
    "shell": [(r"#.*", "com"), (r"^[ \t]*[\w.\\/:-]+", "cmd"), (r"(?<![\w-])--?[A-Za-z][\w-]*", "flag"),
              (_D + "|" + _S, "str")],
    "yaml": [(r"#.*", "com"), (r"^[ \t-]*[\w.-]+(?=\s*:)", "key"), (_D + "|" + _S, "str"),
             (r"\b(?:true|false|null|yes|no)\b", "lit"), (r"\b\d+(?:\.\d+)?\b", "num")],
}

ALIASES = {"js": "ts", "javascript": "ts", "typescript": "ts", "tsx": "ts", "jsx": "ts", "cs": "ts", "csharp": "ts",
           "c": "ts", "cpp": "ts", "h": "ts", "hpp": "ts", "java": "ts", "go": "ts", "rs": "ts", "rust": "ts",
           "python": "py", "bash": "shell", "sh": "shell", "powershell": "shell", "ps1": "shell", "pwsh": "shell",
           "cmd": "shell", "bat": "shell", "console": "shell", "yml": "yaml", "mysql": "sql"}

EXT_LABEL = {".ts": "ts", ".tsx": "tsx", ".js": "js", ".jsx": "jsx", ".mjs": "js", ".cjs": "js", ".cs": "cs",
             ".java": "java", ".go": "go", ".rs": "rs", ".c": "c", ".cpp": "cpp", ".h": "h", ".hpp": "hpp",
             ".py": "py", ".json": "json", ".sql": "sql", ".sh": "sh", ".ps1": "ps1", ".bat": "bat",
             ".yml": "yaml", ".yaml": "yaml"}

_compiled = {}


def rules_for(lang):
    lang = ALIASES.get(lang.lower(), lang.lower())
    if lang not in RULES:
        return None
    if lang not in _compiled:
        _compiled[lang] = [(re.compile(p, re.M), c) for p, c in RULES[lang]]
    return _compiled[lang]


def highlight(text, lang):
    """Highlight plain text; returns escaped HTML. Unknown languages are only escaped."""
    rules = rules_for(lang)
    if not rules:
        return html.escape(text, quote=False)
    out, plain, i = [], [], 0
    while i < len(text):
        for rx, cls in rules:
            m = rx.match(text, i)
            if m and m.group(0):
                out.append(html.escape("".join(plain), quote=False))
                out.append(f'<span class="tk-{cls}">{html.escape(m.group(0), quote=False)}</span>')
                plain, i = [], i + len(m.group(0))
                break
        else:
            plain.append(text[i])
            i += 1
    out.append(html.escape("".join(plain), quote=False))
    return "".join(out)
