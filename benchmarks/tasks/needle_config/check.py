import sys
nonce = sys.argv[1]
assert open("answer.txt").read().strip() == "31337"
print("PASS", nonce)
