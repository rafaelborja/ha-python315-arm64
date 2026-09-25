"""Split Home Assistant's test suite into N shards of similar size (deterministic, same split for every mode).

Usage: python split_tests.py CORE_CHECKOUT N OUTDIR  -> OUTDIR/shard-<i>.txt, one pytest path per line.
Units: each tests/components/<integration> directory, and each other test_*.py file. Weight = number of
`def test_` occurrences. Greedy largest-first onto the lightest shard.
"""
import pathlib
import sys

core, n, out = pathlib.Path(sys.argv[1]), int(sys.argv[2]), pathlib.Path(sys.argv[3])
tests = core / "tests"


def weight(paths) -> int:
    return sum(p.read_text(errors="ignore").count("def test_") for p in paths) or 1


units = {}
for d in sorted((tests / "components").iterdir()):
    if d.is_dir():
        files = list(d.rglob("test_*.py"))
        if files:
            units[d.relative_to(core).as_posix()] = weight(files)
for f in sorted(tests.rglob("test_*.py")):
    rel = f.relative_to(tests)
    if rel.parts[0] != "components":
        units[f.relative_to(core).as_posix()] = weight([f])
shards = [[0, []] for _ in range(n)]
for path, w in sorted(units.items(), key=lambda kv: (-kv[1], kv[0])):
    s = min(shards, key=lambda x: x[0])
    s[0] += w
    s[1].append(path)
out.mkdir(parents=True, exist_ok=True)
for i, (w, paths) in enumerate(shards):
    (out / f"shard-{i}.txt").write_text("\n".join(sorted(paths)) + "\n")
    print(f"shard {i}: {len(paths)} units, ~{w} tests")
