import os, random
def source():
    rnd = random.Random(3)
    parts = ['"""Generated scoring engine. Do not reformat."""\n']
    order = [n for n in range(1, 1500) if n not in (13, 137, 1370)]
    rnd.shuffle(order)
    for n in order[:400] + [13, 137, 1370]:
        k = rnd.randint(2, 9)
        parts.append(
            f"\n\ndef score_batch_{n}(values):\n"
            f"    THRESHOLD = 10\n"
            f"    acc = 0\n"
            f"    for v in values:\n"
            f"        if v * {k} > THRESHOLD:\n"
            f"            acc += v\n"
            f"    return acc\n")
    body = "".join(parts)
    # put the three similar names far apart
    return body
def build(d):
    src = source()
    chunks = src.split("\n\n\ndef ")
    head, funcs = chunks[0], chunks[1:]
    rnd = random.Random(11)
    special = funcs[-3:]
    funcs = funcs[:-3]
    for i, f in enumerate(special):
        funcs.insert(rnd.randint(0, len(funcs)), f)
    out = head + "".join("\n\n\ndef " + f for f in funcs)
    open(os.path.join(d, "engine.py"), "w").write(out)
if __name__ == "__main__":
    build(os.getcwd())
