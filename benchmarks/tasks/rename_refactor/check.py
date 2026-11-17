import os, re, subprocess, sys
nonce = sys.argv[1]
for root, _, files in os.walk("."):
    for f in files:
        if f.endswith(".py"):
            src = open(os.path.join(root, f)).read()
            assert not re.search(r"\bcalc_total\b", src), f"calc_total still in {f}"
src = open("shop/pricing.py").read() + open("shop/orders.py").read()
assert "def calc_total_tax" in src and "def recalc_totals" in src, "unrelated names changed"
r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], capture_output=True, text=True)
assert r.returncode == 0, r.stderr[-1500:]
code = """
import shop
from shop.pricing import compute_total, calc_total_tax
from shop.orders import recalc_totals, order_summary
from shop.cart import Cart
assert shop.compute_total([{'price': 3, 'qty': 3}]) == 9
assert calc_total_tax([{'price': 10, 'qty': 1}], 0.5) == 15
assert recalc_totals([[{'price': 1, 'qty': 2}]]) == [2]
assert 'compute_total' in shop.__all__
print('ok')
"""
r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
assert r.returncode == 0 and "ok" in r.stdout, r.stderr[-1500:]
print("PASS", nonce)
