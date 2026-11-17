import os, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
nonce = sys.argv[1]
import gen
for seed, n in [(1, 40), (77, 120), (5, 3)]:
    data = gen.make_data(seed, n)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(data)
    r = subprocess.run([sys.executable, "main.py", f.name], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr[-1500:]
    assert r.stdout.strip() == gen.expected(data), (seed, r.stdout[-500:])
print("PASS", nonce)
