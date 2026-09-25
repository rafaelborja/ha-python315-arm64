"""Split the pinned package list of the official HA image into N chunks for parallel wheel builds.

Usage: python plan.py freeze.txt N outdir
Lines that are not plain "name==version" (editable installs, URLs) are listed in outdir/skipped.txt.
Chunks are dealt round-robin over a size-sorted order so the known slow compiles spread across jobs.
"""
import pathlib
import sys

freeze, n, out = sys.argv[1], int(sys.argv[2]), pathlib.Path(sys.argv[3])
out.mkdir(parents=True, exist_ok=True)
SLOW = ("grpcio", "numpy", "pydantic-core", "pydantic_core", "orjson", "cryptography", "av", "pillow", "lxml",
        "scipy", "pandas", "protobuf", "uv", "rpds-py", "jiter", "tokenizers", "zeroconf", "habluetooth", "sqlalchemy")
pins, skipped = [], []
for line in pathlib.Path(freeze).read_text().splitlines():
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    if "==" in line and " @ " not in line and not line.startswith("-e"):
        pins.append(line)
    else:
        skipped.append(line)
pins.sort(key=lambda p: (p.split("==")[0].lower() not in SLOW, p.lower()))
for i in range(n):
    (out / f"chunk-{i}.txt").write_text("\n".join(pins[i::n]) + "\n")
(out / "skipped.txt").write_text("\n".join(skipped) + "\n")
print(f"{len(pins)} pinned packages in {n} chunks; {len(skipped)} skipped")
