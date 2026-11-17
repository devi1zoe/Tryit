import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
nonce = sys.argv[1]
import gen
got = json.load(open("revenue.json"))
exp = gen.expected()
assert set(got) == set(exp), (sorted(got), sorted(exp))
for k in exp:
    assert abs(float(got[k]) - exp[k]) <= 0.011, (k, got[k], exp[k])
print("PASS", nonce)
