"""Import every top-level package and every HA integration in three modes and report the differences.

Runs inside the built image (python3.15 as the driver):
    python3.15 import_check.py --shard I/N --out result.json

Modes, each target in its own fresh process:
  314   python3 (the image's original 3.14): the baseline
  315   python3.15, eager
  lazy  python3.15 -X lazy_imports=all + the exclusion filter (image defaults), then every lazy name left in
        sys.modules is resolved ("reified"), so an import that would only break when first used is caught here.
        Mocked tests hide exactly this kind of bug.
A target is a regression when it works in the previous mode and fails in this one:
  315 vs 314  -> a 3.15 build/runtime problem;  lazy vs 315 -> a candidate for the exclusion list.
"""
import argparse
import concurrent.futures as cf
import importlib.metadata as md
import json
import os
import pathlib
import subprocess
import sys

COMPONENTS = pathlib.Path("/usr/src/homeassistant/homeassistant/components")
SKIP_TOP = {"tests", "test", "docs", "examples", "benchmarks", "homeassistant", "setup", "conftest"}

# Runs as a function: a lazy object read through a *global* name of __main__ would resolve on the spot.
CHILD = r"""
def main():
    import importlib, json, sys, types
    LT = getattr(types, "LazyImportType", None)
    res = {"import": {}, "reify": {}}
    for name in sys.argv[1:]:
        try:
            importlib.import_module(name)
        except BaseException as e:
            res["import"][name] = f"{type(e).__name__}: {e}"[:300]
    if LT is not None:
        for _ in range(5):
            found = 0
            for mname, mod in list(sys.modules.items()):
                d = getattr(mod, "__dict__", None)
                if not isinstance(d, dict):
                    continue
                for k, v in list(d.items()):
                    if isinstance(v, LT):
                        found += 1
                        try:
                            getattr(mod, k)
                        except BaseException as e:
                            res["reify"].setdefault(f"{mname}.{k}", f"{type(e).__name__}: {e}"[:300])
                        if isinstance(d.get(k), LT):
                            d[k] = None  # unresolvable; do not count it again
            if not found:
                break
    print("\n@@RESULT@@" + json.dumps(res))
main()
"""

MODES = {
    "314": ["python3"],
    "315": ["python3.15"],
    "lazy": ["python3.15", "-X", "lazy_imports=all"],
}


def top_levels() -> dict[str, list[str]]:
    """Top-level importable names of every distribution installed for 3.15 (from RECORD; top_level.txt is
    missing from most modern wheels)."""
    targets = {}
    for dist in md.distributions():
        name = dist.metadata["Name"]
        tops = set()
        for f in dist.files or ():
            parts = f.parts
            if not parts or parts[0].endswith((".dist-info", ".data", ".egg-info")) or parts[0] in ("..", "bin"):
                continue
            first = parts[0]
            if len(parts) == 1:
                if first.endswith(".py"):
                    tops.add(first[:-3])
                elif ".cpython-" in first or first.endswith(".abi3.so"):
                    tops.add(first.split(".", 1)[0])
            elif not first.startswith("__") and first.isidentifier():
                tops.add(first)
        tops = sorted(t for t in tops if t not in SKIP_TOP and not t.startswith("_") and t.isidentifier())
        if tops:
            targets[f"pkg:{name}"] = tops
    return targets


def integrations() -> dict[str, list[str]]:
    targets = {}
    if not COMPONENTS.is_dir():
        return targets
    for d in sorted(COMPONENTS.iterdir()):
        if not (d / "__init__.py").exists():
            continue
        mods = [f"homeassistant.components.{d.name}"]
        mods += [f"homeassistant.components.{d.name}.{p.stem}" for p in sorted(d.glob("*.py")) if p.stem != "__init__"]
        targets[f"int:{d.name}"] = mods
    return targets


def run(mode: str, modules: list[str]) -> dict:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    try:
        p = subprocess.run([*MODES[mode], "-c", CHILD, *modules], capture_output=True, text=True, timeout=180,
                           env=env, cwd="/tmp")
    except subprocess.TimeoutExpired:
        return {"fatal": "timeout 180s"}
    if "@@RESULT@@" not in p.stdout:
        return {"fatal": f"exit {p.returncode}: {(p.stderr or p.stdout)[-400:]}"}
    return json.loads(p.stdout.rsplit("@@RESULT@@", 1)[1])


def failed(r: dict) -> bool:
    return bool(r.get("fatal") or r.get("import") or r.get("reify"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard", default="0/1")
    ap.add_argument("--out", required=True)
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--modes", default=",".join(MODES), help="subset of 314,315,lazy")
    ap.add_argument("--only", default="", help="file with target keys (pkg:x / int:y) to check")
    a = ap.parse_args()
    i, n = map(int, a.shard.split("/"))
    allt = {**top_levels(), **integrations()}
    keys = sorted(allt)[i::n]
    if a.only:
        want = set(pathlib.Path(a.only).read_text().split())
        keys = [k for k in keys if k in want]
    modes = [m for m in a.modes.split(",") if m in MODES]
    results: dict[str, dict] = {k: {} for k in keys}
    with cf.ThreadPoolExecutor(a.jobs) as ex:
        futs = {ex.submit(run, m, allt[k]): (k, m) for k in keys for m in modes}
        for done, f in enumerate(cf.as_completed(futs), 1):
            k, m = futs[f]
            results[k][m] = f.result()
            if done % 500 == 0:
                print(f"{done}/{len(futs)}", flush=True)
    out = {"shard": a.shard, "targets": {}, "regress_315": [], "regress_lazy": [], "fail_314": []}
    for k in keys:
        r = results[k]
        out["targets"][k] = {"modules": allt[k], **{m: r[m] for m in modes if failed(r[m])}}
        f = {m: failed(r[m]) if m in r else None for m in MODES}
        if f["314"]:
            out["fail_314"].append(k)
        if f["315"] and f["314"] is False:
            out["regress_315"].append(k)
        if f["lazy"] and f["315"] is not True:  # without an eager 3.15 run in this pass, every lazy failure is listed
            out["regress_lazy"].append(k)
    pathlib.Path(a.out).write_text(json.dumps(out, indent=1))
    print(f"shard {a.shard}: {len(keys)} targets; 3.15 regressions {len(out['regress_315'])}, "
          f"lazy regressions {len(out['regress_lazy'])}, broken on 3.14 too {len(out['fail_314'])}")


if __name__ == "__main__":
    sys.exit(main())
