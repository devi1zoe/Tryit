import ast, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
nonce = sys.argv[1]
import gen
tmp = tempfile.mkdtemp()
gen.build(tmp)
orig = open(os.path.join(tmp, "engine.py")).read().splitlines()
new = open("engine.py").read().splitlines()
assert len(orig) == len(new), "line count changed"
diff = [i for i, (a, b) in enumerate(zip(orig, new)) if a != b]
assert len(diff) == 1, f"{len(diff)} lines differ"
i = diff[0]
assert new[i] == "    THRESHOLD = 25", new[i]
tree = ast.parse("\n".join(new))
for fn in tree.body:
    if isinstance(fn, ast.FunctionDef) and fn.lineno - 1 < i <= fn.end_lineno - 1:
        assert fn.name == "score_batch_137", fn.name
        break
else:
    raise AssertionError("changed line not in a function")
print("PASS", nonce)
