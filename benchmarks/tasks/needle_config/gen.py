import json, os, random
def build(d):
    rnd = random.Random(7)
    decoys = ["api_timeout", "timeout_ms", "api_timeout_msec", "api_timeout_ms_default", "read_timeout_ms"]
    target = rnd.randrange(400)
    for i in range(400):
        sub = os.path.join(d, "configs", f"svc{i % 23}", f"env{i % 5}")
        os.makedirs(sub, exist_ok=True)
        kind = i % 3
        keys = {rnd.choice(decoys): rnd.randint(100, 99999) for _ in range(3)}
        keys["name"] = f"service-{i}"
        if i == target:
            keys["api_timeout_ms"] = 31337
        if kind == 0:
            body = json.dumps(keys, indent=2)
            ext = "json"
        elif kind == 1:
            body = "\n".join(f"{k}: {v}" for k, v in keys.items())
            if i % 7 == 1:
                body += "\n# TODO: set api_timeout_ms: 5000 once the API is stable"
            ext = "yaml"
        else:
            body = "[main]\n" + "\n".join(f"{k} = {v}" for k, v in keys.items())
            if i % 11 == 2:
                body += "\n; api_timeout_ms = 1200 (legacy, disabled)"
            ext = "ini"
        open(os.path.join(sub, f"cfg_{i:03d}.{ext}"), "w").write(body + "\n")
if __name__ == "__main__":
    build(os.getcwd())
