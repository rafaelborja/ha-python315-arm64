"""Plan the wheel builds: the installed packages of the official HA image, plus extras, split into N chunks.

Usage: python plan.py installed.txt extras.txt N outdir [test_requirements.txt]
- installed.txt: "name==version" per line, as listed from the image's site-packages (homeassistant excluded).
- extras.txt: extra pins to build into the image (empty in public builds). A pin here replaces the image's pin of
  the same package.
- test_requirements.txt (optional): HA's requirements_test.txt; its pins go to outdir/test.txt (built with deps,
  installed only in the test image, never in the Core image).
Chunks are dealt round-robin over a slow-first order so the known long compiles spread across jobs.
"""
import pathlib
import re
import sys


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def pins(path: str) -> tuple[dict[str, str], list[str]]:
    found, skipped = {}, []
    for line in pathlib.Path(path).read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("-"):
            skipped.append(line)
        elif "==" in line and " @ " not in line:
            found[norm(line.split("==")[0].split("[")[0])] = line
        else:
            skipped.append(line)
    return found, skipped


installed, extras, n, out = sys.argv[1], sys.argv[2], int(sys.argv[3]), pathlib.Path(sys.argv[4])
out.mkdir(parents=True, exist_ok=True)
base, skipped = pins(installed)
extra, _ = pins(extras)
base.update(extra)
SLOW = {norm(s) for s in (
    "grpcio", "numpy", "pydantic-core", "orjson", "cryptography", "av", "pillow", "lxml", "scipy", "pandas",
    "protobuf", "uv", "rpds-py", "jiter", "tokenizers", "zeroconf", "habluetooth", "sqlalchemy", "awscrt",
    "deebot-client", "dbus-fast", "aiohttp", "yarl", "multidict", "propcache", "frozenlist")}
order = sorted(base, key=lambda k: (k not in SLOW, k))
for i in range(n):
    (out / f"chunk-{i}.txt").write_text("\n".join(base[k] for k in order[i::n]) + "\n")
(out / "required.txt").write_text("\n".join(base[k] for k in sorted(base)) + "\n")
(out / "skipped.txt").write_text("\n".join(skipped) + "\n")
if len(sys.argv) > 5:
    test, _ = pins(sys.argv[5])
    # When a test pin and the image disagree: test TOOLING takes the test pin (the image ships pytest 9.1.1, HA
    # tests with 9.0.3); anything else keeps the image's version, because that is what is under test (a test pin
    # of pydantic pulled another pydantic-core, which does not build for 3.15).
    TOOLS = {norm(s) for s in ("coverage", "freezegun", "syrupy", "respx", "requests-mock", "tqdm", "pluggy",
                               "iniconfig", "execnet", "pytest", "mypy", "mypy-dev", "pylint", "astroid", "isort")}
    tooling = lambda k: k in TOOLS or k.startswith("pytest")
    keep_image = sorted(k for k in test if k in base and base[k] != test[k] and not tooling(k))
    for k in keep_image:
        test[k] = base[k]
    (out / "test.txt").write_text("\n".join(test[k] for k in sorted(test)) + "\n")
    (out / "test-constraints.txt").write_text(
        "\n".join(base[k] for k in sorted(base) if not (k in test and tooling(k))) + "\n")
    print(f"test pins replaced by the image's version: {', '.join(keep_image) or 'none'}")
print(f"{len(base)} packages ({len(extra)} extras) in {n} chunks; {len(skipped)} skipped")
