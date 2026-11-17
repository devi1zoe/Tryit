import os, sys
sys.path.insert(0, os.getcwd())
nonce = sys.argv[1]
import stats
def close(a, b): return abs(a - b) < 1e-9
xs = [5, 1, 4]
assert close(stats.median(xs), 4) and xs == [5, 1, 4], "median must not mutate"
assert close(stats.median([7]), 7)
assert close(stats.median([1.5, 2.5]), 2.0)
assert close(stats.median([10, 2, 8, 4]), 6)
assert close(stats.variance([2, 4, 4, 4, 5, 5, 7, 9]), 4.0)
assert close(stats.variance([3]), 0.0)
assert stats.mode([3, 3, 1, 1, 2]) == 1
assert stats.mode([9, 2, 9, 2, 5, 5]) == 2
assert stats.mode([4]) == 4
assert close(stats.mean([1, 2, 3, 4]), 2.5)
test = open("test_stats.py").read()
assert "assertEqual(median([4, 1, 3, 2]), 2.5)" in test and "assertAlmostEqual(variance([1, 2, 3, 4]), 1.25)" in test, "tests were modified"
print("PASS", nonce)
