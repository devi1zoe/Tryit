import os
STATS = '''"""Small statistics helpers."""


def mean(xs):
    """Arithmetic mean of a non-empty sequence."""
    return sum(xs) / len(xs)


def median(xs):
    """Median of a non-empty sequence. Must not modify the input."""
    xs.sort()
    n = len(xs)
    return xs[n // 2]


def variance(xs):
    """Population variance of a non-empty sequence."""
    m = mean(xs)
    return sum((x - m) ** 2 for x in xs) / (len(xs) - 1)


def mode(xs):
    """Most common value; ties are broken by the smallest value."""
    counts = {}
    for x in xs:
        counts[x] = counts.get(x, 0) + 1
    return max(counts, key=lambda k: counts[k])
'''
TESTS = '''import unittest
from stats import mean, median, variance, mode


class T(unittest.TestCase):
    def test_mean(self):
        self.assertEqual(mean([1, 2, 3]), 2)

    def test_median_even(self):
        self.assertEqual(median([4, 1, 3, 2]), 2.5)

    def test_variance(self):
        self.assertAlmostEqual(variance([1, 2, 3, 4]), 1.25)

    def test_mode_tie(self):
        self.assertEqual(mode([3, 3, 1, 1, 2]), 1)


if __name__ == "__main__":
    unittest.main()
'''
def build(d):
    open(os.path.join(d, "stats.py"), "w").write(STATS)
    open(os.path.join(d, "test_stats.py"), "w").write(TESTS)
if __name__ == "__main__":
    build(os.getcwd())
