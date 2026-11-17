import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
nonce = sys.argv[1]
import gen
got = [l.split() for l in open("top3.txt").read().strip().splitlines()]
exp = [[ip, str(n)] for ip, n in gen.expected()]
assert got == exp, (got, exp)
print("PASS", nonce)
