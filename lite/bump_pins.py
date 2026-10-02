"""HA Lite: keep Home Assistant's own pins in step with the packages the layer replaces.

Home Assistant checks every requirement of an integration when it sets it up and reinstalls a package whose installed
version does not satisfy the pin (manifest.json "requirements", constrained by package_constraints.txt). A replaced
wheel without the matching pin bump is silently put back at runtime (bluetooth, cast, cloud, matter and mobile_app
failed that way with dbus-fast). Local versions ("1.4.0+lowmem.1") satisfy "==1.4.0" and need no bump.

  bump_pins.py bump                  apply BUMPS; fails if an old pin is missing or survives anywhere
  bump_pins.py check OUT.json        record every pin an installed distribution does not satisfy
  bump_pins.py compare BASE.json     fail if a pin is unsatisfied now that was satisfied in BASE.json
"""
import glob
import importlib.metadata as md
import json
import os
import re
import sys

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

HA = os.environ.get("HA_SRC", "/usr/src/homeassistant/homeassistant")
# (package, old, new, files under homeassistant/ that pin it in 2026.9.3)
BUMPS = [
    ("python-slugify", "8.0.4", "9.1.2", ["package_constraints.txt"]),
    ("dbus-fast", "5.0.22", "5.0.24", ["package_constraints.txt", "components/bluetooth/manifest.json"]),
    ("google-genai", "2.16.0", "2.18.1", ["components/google_generative_ai_conversation/manifest.json"]),
    ("aiooui", "0.1.9", "0.1.11", ["components/nmap_tracker/manifest.json"]),
]


def pin_files():
    yield f"{HA}/package_constraints.txt"
    yield from sorted(glob.glob(f"{HA}/components/*/manifest.json"))


def pins():
    """(file, requirement string) for every pin HA enforces."""
    for f in pin_files():
        if f.endswith(".json"):
            for r in json.load(open(f, encoding="utf-8")).get("requirements", []):
                yield f, r
        else:
            for line in open(f, encoding="utf-8"):
                line = line.split("#", 1)[0].strip()
                if line and not line.startswith("-"):
                    yield f, line


def unsatisfied():
    installed = {canonicalize_name(d.metadata["Name"]): d.version for d in md.distributions() if d.metadata["Name"]}
    out = set()
    for f, r in pins():
        try:
            req = Requirement(r)
        except InvalidRequirement:
            continue
        if req.marker and not req.marker.evaluate():
            continue
        v = installed.get(canonicalize_name(req.name))
        if v is not None and req.specifier and not req.specifier.contains(v, prereleases=True):
            out.add(f"{req.name} {req.specifier} installed={v} in {os.path.relpath(f, HA)}")
    return sorted(out)


def bump():
    for pkg, old, new, files in BUMPS:
        for rel in files:
            p = f"{HA}/{rel}"
            s = open(p, encoding="utf-8").read()
            pat = re.compile(rf"(?<![\w.-]){re.escape(pkg)}=={re.escape(old)}(?![\w.+-])")
            if len(pat.findall(s)) != 1:
                sys.exit(f"bump_pins: {pkg}=={old} not found exactly once in {rel}")
            open(p, "w", encoding="utf-8").write(pat.sub(f"{pkg}=={new}", s))
        for f in pin_files():
            if re.search(rf"(?<![\w.-]){re.escape(pkg)}=={re.escape(old)}(?![\w.+-])", open(f, encoding="utf-8").read()):
                sys.exit(f"bump_pins: {pkg}=={old} still pinned in {os.path.relpath(f, HA)}")
        print(f"pin {pkg}: {old} -> {new} ({', '.join(files)})")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "bump":
        bump()
    elif cmd == "check":
        u = unsatisfied()
        json.dump(u, open(sys.argv[2], "w"), indent=0)
        print(f"pins unsatisfied in the base image: {len(u)}")
    elif cmd == "compare":
        base = set(json.load(open(sys.argv[2])))
        new = [x for x in unsatisfied() if x not in base]
        for x in new:
            print("NEW unsatisfied pin:", x)
        if new:
            sys.exit(f"gate pins: {len(new)} pin(s) HA would reinstall at setup")
        print("gate pins: no new unsatisfied pin (HA will not reinstall a replaced package)")
    else:
        sys.exit(__doc__)
