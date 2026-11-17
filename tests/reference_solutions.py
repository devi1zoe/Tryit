"""Known-good solutions, used only to validate the benchmark checkers."""
import re
from pathlib import Path


def fix_stats(wd: Path):
    s = (wd / "stats.py").read_text()
    s = s.replace("    xs.sort()\n    n = len(xs)\n    return xs[n // 2]",
                  "    s = sorted(xs)\n    n = len(s)\n    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2")
    s = s.replace("/ (len(xs) - 1)", "/ len(xs)")
    s = s.replace("key=lambda k: counts[k])", "key=lambda k: (counts[k], -k))")
    (wd / "stats.py").write_text(s)


def roman(wd: Path):
    (wd / "roman.py").write_text('''
V = [(1000,"M"),(900,"CM"),(500,"D"),(400,"CD"),(100,"C"),(90,"XC"),(50,"L"),(40,"XL"),(10,"X"),(9,"IX"),(5,"V"),(4,"IV"),(1,"I")]
def to_roman(n):
    if type(n) is not int or not 1 <= n <= 3999:
        raise ValueError(n)
    out = ""
    for v, s in V:
        while n >= v:
            out += s; n -= v
    return out
TABLE = {to_roman(i): i for i in range(1, 4000)}
def from_roman(s):
    if not isinstance(s, str) or s not in TABLE:
        raise ValueError(s)
    return TABLE[s]
''')


def csv_revenue(wd: Path):
    import csv, json
    tot = {}
    for row in csv.reader(open(wd / "sales.csv")):
        if len(row) != 5 or row[0] == "date":
            continue
        try:
            q = int(row[3])
        except ValueError:
            continue
        r = row[1].strip().lower()
        tot[r] = tot.get(r, 0) + q * float(row[4].replace("$", "").replace(",", ""))
    (wd / "revenue.json").write_text(json.dumps({k: round(v, 2) for k, v in tot.items()}))


def needle_config(wd: Path):
    for p in (wd / "configs").rglob("*"):
        if p.is_file():
            for line in p.read_text().splitlines():
                m = re.match(r'^\s*"?api_timeout_ms"?\s*[:=]\s*(\d+)', line)
                if m:
                    (wd / "answer.txt").write_text(m.group(1))


def rename_refactor(wd: Path):
    for p in wd.rglob("*.py"):
        p.write_text(re.sub(r"\bcalc_total\b", "compute_total", p.read_text()))


def log_top_errors(wd: Path):
    pat = re.compile(r'^(\S+) \S+ \S+ \[[^\]]+\] "[^"]*" (\d{3}) (\d+|-)$')
    c = {}
    for l in (wd / "access.log").read_text().splitlines():
        m = pat.match(l)
        if m and m.group(2).startswith("5"):
            c[m.group(1)] = c.get(m.group(1), 0) + 1
    top = sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
    (wd / "top3.txt").write_text("\n".join(f"{ip} {n}" for ip, n in top) + "\n")


def traceback_fix(wd: Path):
    (wd / "parse.py").write_text('''def read_records(path):
    out = {}
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, score = line.split(",")
        out.setdefault(name.strip(), []).append(int(score))
    return out
''')
    r = (wd / "report.py").read_text()
    r = r.replace("(len(xs) + 1)", "len(xs)").replace("sorted(records, key=lambda n: records[n])", "sorted(records)")
    r = r.replace('"students: " + len(records)', 'f"students: {len(records)}"')
    (wd / "report.py").write_text(r)


def long_file_edit(wd: Path):
    lines = (wd / "engine.py").read_text().split("\n")
    i = lines.index("def score_batch_137(values):")
    assert lines[i + 1] == "    THRESHOLD = 10"
    lines[i + 1] = "    THRESHOLD = 25"
    (wd / "engine.py").write_text("\n".join(lines))


SOLUTIONS = {k: v for k, v in globals().items() if callable(v) and not k.startswith("_") and k not in ("Path",)}
SOLUTIONS = {k: v for k, v in SOLUTIONS.items() if k in {
    "fix_stats", "roman", "csv_revenue", "needle_config", "rename_refactor", "log_top_errors",
    "traceback_fix", "long_file_edit"}}
