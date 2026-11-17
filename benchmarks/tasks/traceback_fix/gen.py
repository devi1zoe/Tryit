import os, random
MAIN = '''import sys
from parse import read_records
from report import format_report


def main(path):
    records = read_records(path)
    print(format_report(records))


if __name__ == "__main__":
    main(sys.argv[1])
'''
PARSE = '''def read_records(path):
    """Return {name: [scores]} from lines "name,score". Blank lines and # comments are skipped."""
    out = {}
    for line in open(path):
        line = line.strip()
        if line.startswith("#"):
            continue
        name, score = line.split(";")
        out[name].append(score)
    return out
'''
REPORT = '''def average(xs):
    return sum(xs) / (len(xs) + 1)


def format_report(records):
    lines = []
    for name in sorted(records, key=lambda n: records[n]):
        lines.append(f"{name}: {average(records[name]):.1f}")
    lines.append("students: " + len(records))
    return "\\n".join(lines)
'''
def make_data(seed, n):
    rnd = random.Random(seed)
    names = ["alice", "bob", "carol", "dave", "erin", "frank", "grace", "heidi", "ivan", "judy"]
    lines = ["# name,score"]
    for _ in range(n):
        lines.append(f"{rnd.choice(names)},{rnd.randint(40, 100)}")
        if rnd.random() < 0.1:
            lines.append("")
    return "\n".join(lines) + "\n"
def expected(text):
    rec = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        n, s = line.split(",")
        rec.setdefault(n.strip(), []).append(int(s))
    out = [f"{n}: {sum(v)/len(v):.1f}" for n, v in sorted(rec.items())]
    out.append(f"students: {len(rec)}")
    return "\n".join(out)
def build(d):
    for name, body in [("main.py", MAIN), ("parse.py", PARSE), ("report.py", REPORT)]:
        open(os.path.join(d, name), "w").write(body)
    data = make_data(1, 40)
    open(os.path.join(d, "data.txt"), "w").write(data)
    open(os.path.join(d, "expected_output.txt"), "w").write(expected(data) + "\n")
if __name__ == "__main__":
    build(os.getcwd())
