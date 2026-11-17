import os
FILES = {
"shop/__init__.py": "from .pricing import calc_total, calc_total_tax\n__all__ = ['calc_total', 'calc_total_tax']\n",
"shop/pricing.py": '''def calc_total(items):
    """Sum of price * qty."""
    return round(sum(i["price"] * i["qty"] for i in items), 2)


def calc_total_tax(items, rate):
    return round(calc_total(items) * (1 + rate), 2)
''',
"shop/cart.py": '''from .pricing import calc_total as _total


class Cart:
    def __init__(self):
        self.items = []

    def add(self, price, qty=1):
        self.items.append({"price": price, "qty": qty})

    def total(self):
        return _total(self.items)
''',
"shop/orders.py": '''from . import pricing
from .pricing import (
    calc_total_tax,
    calc_total,
)


def recalc_totals(orders):
    return [calc_total(o) for o in orders]


def order_summary(order, rate=0.1):
    return {"net": pricing.calc_total(order), "gross": calc_total_tax(order, rate)}
''',
"shop/report.py": '''import shop


def report(orders):
    lines = []
    for i, o in enumerate(orders):
        lines.append(f"order {i}: {shop.calc_total(o):.2f}")
    return "\\n".join(lines)
''',
"tests/test_shop.py": '''import unittest
from shop import calc_total
from shop.cart import Cart
from shop.orders import order_summary, recalc_totals
from shop.report import report


class T(unittest.TestCase):
    def test_total(self):
        self.assertEqual(calc_total([{"price": 2.5, "qty": 2}]), 5.0)

    def test_cart(self):
        c = Cart(); c.add(1.25, 4)
        self.assertEqual(c.total(), 5.0)

    def test_orders(self):
        o = [{"price": 10, "qty": 1}]
        self.assertEqual(recalc_totals([o, o]), [10, 10])
        self.assertEqual(order_summary(o), {"net": 10, "gross": 11.0})
        self.assertIn("order 0: 10.00", report([o]))
''',
}
def build(d):
    for p, body in FILES.items():
        full = os.path.join(d, p)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        open(full, "w").write(body)
if __name__ == "__main__":
    build(os.getcwd())
