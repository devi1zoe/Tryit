import os
def build(d):
    open(os.path.join(d, "README.txt"), "w").write("Write roman.py here.\n")
if __name__ == "__main__":
    build(os.getcwd())
