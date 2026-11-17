"""DGM-style open-ended archive of harness generations."""
from __future__ import annotations

import json
import math
import random
import shutil
from pathlib import Path


class Archive:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # -- storage ---------------------------------------------------------------------
    def gen_dir(self, gid: str) -> Path:
        return self.root / gid

    def ids(self) -> list[str]:
        return sorted(p.name for p in self.root.iterdir() if (p / "meta.json").exists())

    def next_id(self) -> str:
        return f"gen_{len(self.ids()):04d}"

    def meta(self, gid: str) -> dict:
        return json.loads((self.gen_dir(gid) / "meta.json").read_text())

    def all_meta(self) -> list[dict]:
        return [self.meta(g) for g in self.ids()]

    def harness_dir(self, gid: str) -> Path:
        return self.gen_dir(gid) / "harness"

    def add(self, gid: str, harness_src: Path | None, meta: dict, files: dict[str, object] | None = None):
        d = self.gen_dir(gid)
        d.mkdir(parents=True, exist_ok=True)
        if harness_src is not None and not (d / "harness").exists():
            shutil.copytree(harness_src, d / "harness", ignore=shutil.ignore_patterns("__pycache__"))
        for name, obj in (files or {}).items():
            p = d / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(obj if isinstance(obj, str) else json.dumps(obj, indent=2, default=str))
        meta = {"id": gid, **meta}
        (d / "meta.json").write_text(json.dumps(meta, indent=2, default=str))
        return meta

    def children_count(self) -> dict[str, int]:
        c: dict[str, int] = {}
        for m in self.all_meta():
            if m.get("parent"):
                c[m["parent"]] = c.get(m["parent"], 0) + 1
        return c

    # -- selection -------------------------------------------------------------------
    def select_parent(self, rng: random.Random, method: str = "dgm") -> str:
        cands = [m for m in self.all_meta() if m.get("valid") and m.get("selectable", True)]
        if not cands:
            raise RuntimeError("no selectable generation in the archive")
        if method == "best":
            return max(cands, key=lambda m: (m["score"], m["id"]))["id"]
        if method == "latest":
            return cands[-1]["id"]
        # DGM: favour high scores, discount generations that already have many children.
        kids = self.children_count()
        w = [1 / (1 + math.exp(-10 * (m["score"] - 0.5))) / (1 + kids.get(m["id"], 0)) for m in cands]
        return rng.choices([m["id"] for m in cands], weights=w, k=1)[0]
