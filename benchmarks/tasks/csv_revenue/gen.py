import csv, io, os, random
REGIONS = ["north", "south", "east", "west", "central"]
def rows():
    rnd = random.Random(1234)
    out = []
    for i in range(600):
        region = rnd.choice(REGIONS)
        style = rnd.random()
        shown = region.upper() if style < 0.2 else (" " + region.title() + " " if style < 0.4 else region)
        qty = rnd.randint(1, 20)
        price = round(rnd.uniform(0.5, 2500), 2)
        p = rnd.random()
        price_s = f"${price:,.2f}" if p < 0.3 else (f"{price:,.2f}" if p < 0.5 else f"{price:.2f}")
        qty_s = str(qty)
        bad = rnd.random()
        if bad < 0.03:
            qty_s = rnd.choice(["", "n/a", "3.5", "ten"])
        out.append((f"2026-0{rnd.randint(1,9)}-{rnd.randint(10,28)}", shown, f"P{rnd.randint(100,999)}", qty_s, price_s))
    return out
def expected():
    tot = {}
    for _, region, _, q, p in rows():
        try:
            qty = int(q)
        except ValueError:
            continue
        price = float(p.replace("$", "").replace(",", ""))
        r = region.strip().lower()
        tot[r] = tot.get(r, 0.0) + qty * price
    return {k: round(v, 2) for k, v in tot.items()}
def build(d):
    rnd = random.Random(99)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["date", "region", "product", "qty", "unit_price"])
    for i, r in enumerate(rows()):
        if i and i % 150 == 0:
            w.writerow(["date", "region", "product", "qty", "unit_price"])
        if rnd.random() < 0.02:
            buf.write("\n")
        w.writerow(r)
    open(os.path.join(d, "sales.csv"), "w").write(buf.getvalue())
if __name__ == "__main__":
    build(os.getcwd())
