"""Import what `python -m supervisor` imports at startup and report the memory per package (read-only: nothing runs).

Usage: python3[.15] [-X lazy_imports=all] sup_probe.py LABEL > probe-LABEL.json
The run on the official 3.14 answers "which libraries weigh most in Supervisor"; 3.15 with and without lazy imports
shows what lazy imports would save at import time. Runtime memory (caches, Docker/D-Bus state) is only visible on a
real install.
"""
import json
import sys
import tracemalloc

tracemalloc.start(1)


def main():
    import importlib
    import zlib_fast

    zlib_fast.enable()
    errors = {}
    for mod in ("supervisor.bootstrap", "supervisor.dbus.const", "supervisor.exceptions",
                "supervisor.utils.blockbuster", "supervisor.utils.logging"):
        try:
            importlib.import_module(mod)
        except Exception as ex:  # report and go on: this is a probe
            errors[mod] = f"{type(ex).__name__}: {ex}"
    return errors


def owner(filename):
    for marker in ("/site-packages/", "/usr/src/supervisor/"):
        if marker in filename:
            rest = filename.split(marker, 1)[1]
            return "supervisor" if marker == "/usr/src/supervisor/" else rest.split("/")[0].split(".")[0]
    if "/lib/python3." in filename:
        return "(stdlib)"
    return "(other)"


errors = main()
snap = tracemalloc.take_snapshot()
per = {}
for st in snap.statistics("filename"):
    k = owner(st.traceback[0].filename)
    per[k] = per.get(k, 0) + st.size
mods = {}
for name in list(sys.modules):
    top = name.split(".")[0]
    mods[top] = mods.get(top, 0) + 1
status = {}
for line in open("/proc/self/status"):
    if line.startswith(("VmRSS", "RssAnon", "RssFile")):
        k, v = line.split(":")
        status[k] = round(int(v.split()[0]) / 1024, 1)
out = {
    "label": sys.argv[1] if len(sys.argv) > 1 else "",
    "python": sys.version.split()[0],
    "lazy": getattr(sys.flags, "lazy_imports", 0),
    "malloc": __import__("os").environ.get("PYTHONMALLOC", ""),
    "errors": errors,
    "rss_MB": status,
    "traced_MB": round(sum(per.values()) / 2**20, 1),
    "modules": len(sys.modules),
    "per_package_MB": {k: round(v / 2**20, 2) for k, v in sorted(per.items(), key=lambda kv: -kv[1])[:30]},
    "modules_per_package": dict(sorted(mods.items(), key=lambda kv: -kv[1])[:30]),
}
print(json.dumps(out, indent=1))
