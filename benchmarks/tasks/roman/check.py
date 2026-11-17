import os, sys
sys.path.insert(0, os.getcwd())
nonce = sys.argv[1]
from roman import to_roman, from_roman
V = [(1000,"M"),(900,"CM"),(500,"D"),(400,"CD"),(100,"C"),(90,"XC"),(50,"L"),(40,"XL"),(10,"X"),(9,"IX"),(5,"V"),(4,"IV"),(1,"I")]
def ref(n):
    out = ""
    for v, s in V:
        while n >= v:
            out += s; n -= v
    return out
for n in range(1, 4000):
    r = ref(n)
    assert to_roman(n) == r, (n, to_roman(n))
    assert from_roman(r) == n, (r, from_roman(r))
def raises(f, x):
    try:
        f(x)
    except ValueError:
        return True
    except Exception:
        return False
    return False
for bad in [0, -1, 4000, 2.5, "12", None]:
    assert raises(to_roman, bad), bad
for bad in ["", "IIII", "VX", "IC", "MMMM", "mcm", "IIV", "XM", "VV", "CMCM", "ABC", " X"]:
    assert raises(from_roman, bad), bad
print("PASS", nonce)
