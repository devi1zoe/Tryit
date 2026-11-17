import os, random
def lines():
    rnd = random.Random(42)
    ips = [f"10.{rnd.randint(0,3)}.{rnd.randint(0,255)}.{rnd.randint(1,254)}" for _ in range(60)]
    heavy = ips[:6]
    out = []
    for i in range(6000):
        ip = rnd.choice(heavy) if rnd.random() < 0.35 else rnd.choice(ips)
        status = rnd.choice([200] * 12 + [301, 404, 403, 500, 502, 503, 504])
        if ip in heavy[3:] and rnd.random() < 0.25:
            status = rnd.choice([500, 503])
        path = rnd.choice(["/", "/api/v1/items", "/login", "/static/app.js", "/api/v1/orders?id=5"])
        line = f'{ip} - - [17/Nov/2026:10:{i % 60:02d}:{rnd.randint(0,59):02d} +0000] "GET {path} HTTP/1.1" {status} {rnd.randint(100,9000)}'
        r = rnd.random()
        if r < 0.01:
            line = line[: rnd.randint(5, 30)]
        elif r < 0.015:
            line = "#### garbage " + str(rnd.random())
        elif r < 0.02:
            line = f'{ip} - - [17/Nov/2026] "GET / HTTP/1.1" 5xx -'
        out.append(line)
    return out
def expected():
    import re
    pat = re.compile(r'^(\S+) \S+ \S+ \[[^\]]+\] "[^"]*" (\d{3}) (\d+|-)$')
    c = {}
    for l in lines():
        m = pat.match(l)
        if m and m.group(2).startswith("5"):
            c[m.group(1)] = c.get(m.group(1), 0) + 1
    return sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
def build(d):
    open(os.path.join(d, "access.log"), "w").write("\n".join(lines()) + "\n")
if __name__ == "__main__":
    build(os.getcwd())
