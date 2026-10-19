"""Check every `ALIAS:path:LINE` “quote” citation in the given Markdown files.

A citation passes when the quote is a substring of that line (or of any line in
LINE-LINE2). BP zip aliases read the raw project.xml inside the zip.
Usage: python3 check_citations.py docs/mapping.md docs/decisions.md
"""
import re, subprocess, sys
from pathlib import Path

E = "/Users/knarayanam/WorkfusionRepos/NSS/names-screening"
BPD = E + "/names-screening-package/src/main/resources/business-process"
ROOTS = {
    "E": E,
    "J": E + "/names-screening-jnw/src/main/java/com/workfusion/dw/nss",
    "JT": E + "/names-screening-jnw/src/test/java/com/workfusion/dw/nss",
    "JR": E + "/names-screening-jnw/src/main/resources",
    "C": E + "/names-screening-core/src/main/java/com/workfusion/dw/nss/core",
    "S": E + "/names-screening-schema/src/main/java/com/workfusion/dw/nss",
    "M": E + "/names-screening-package/src/main/resources/datastore/migrations",
    "P": E + "/names-screening-package/src/main/resources",
    "K": "/Users/knarayanam/WorkfusionRepos/NSS/names-screening-contract",
    "SIM": "/Users/knarayanam/UiPathRepos/Evelyn Simulation",
    "W": "/Users/knarayanam/UiPathRepos/UiPath-WorkFusion",
    "L": "/Users/knarayanam/UiPathRepos/learning",
    "SDK": "/Users/knarayanam/UiPathRepos/Evelyn Simulation/Datastore Simulation/DatastoreSim/DatastoreSimFunction/.venv/lib/python3.11/site-packages/uipath/platform",
    "CLI": "/opt/homebrew/lib/node_modules/@uipath/maestro-tool/dist",
    "SKILL": "/Users/knarayanam/.claude/plugins/cache/uipath-marketplace/uipath/1.203.1/skills/uipath-maestro-flow/references",
    "IT": E + "/names-screening-integration-tests/src/test/java/com/workfusion/dw/nss",
}
ZIPS = {"CSVBP": BPD + "/CSV+File+Ingestion+_v_4.5.0-dev.zip", "MAINBP": BPD + "/Names+Screening+_v_4.5.0-dev.zip"}
CITE = re.compile(r"`([A-Z]+):([^`]*?):(\d+)(?:-(\d+))?` “([^”]+)”")
# A citation whose quote is missing or wrapped onto the next line would be skipped silently by CITE: it fails instead.
UNQUOTED = re.compile(r"`([A-Z]+):[^`]*?:\d+(?:-\d+)?`(?! “)")
cache = {}

def lines_of(alias, path):
    key = (alias, path)
    if key not in cache:
        if alias in ZIPS:
            text = subprocess.run(["unzip", "-p", ZIPS[alias], "project.xml"], capture_output=True, text=True).stdout
        else:
            text = Path(ROOTS[alias], path).read_text(encoding="utf-8", errors="replace")
        cache[key] = text.split("\n")
    return cache[key]

bad = total = 0
for doc in sys.argv[1:]:
    for n, row in enumerate(Path(doc).read_text(encoding="utf-8").split("\n"), 1):
        for match in UNQUOTED.finditer(row):
            if match.group(1) in ROOTS or match.group(1) in ZIPS:
                total += 1
                bad += 1
                print(f"FAIL {doc}:{n} {match.group(0)} has no “quote” on the same line")
        for alias, path, a, b, quote in CITE.findall(row):
            total += 1
            try:
                ls = lines_of(alias, path)
                first, last = int(a), int(b or a)
                ok = any(quote in ls[i - 1] for i in range(first, last + 1) if 0 < i <= len(ls))
            except (OSError, KeyError) as error:
                ok, ls = False, [str(error)]
            if not ok:
                bad += 1
                print(f"FAIL {doc}:{n} {alias}:{path}:{a}{'-' + b if b else ''} “{quote}”")
print(f"{total - bad}/{total} citations verified")
sys.exit(1 if bad else 0)
