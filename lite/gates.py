"""HA Lite build gates (python3.15, eager, inside the image being built). Any failed assertion fails the build.

Environment: WITH_HOLIDAYS=1 when the holidays lazy-import PR replaced the package; WITH_NABUCASA=1 when a
hass-nabucasa build without pycognito replaced the stock one. Checks that cannot be stated exactly for every base
(what a stock import happens to pull in) print a GitHub warning instead of failing.
"""
import asyncio
import importlib.metadata as m
import inspect
import json
import os
import subprocess
import sys

HA = "/usr/src/homeassistant/homeassistant"
PY = sys.executable


def ok(msg):
    print(f"gate {msg}: ok", flush=True)


def warn(msg):
    print(f"::warning::HA Lite gate: {msg}", flush=True)


def fresh(code):
    """Run code in a fresh interpreter (sys.modules of the gate process would mask what an import loads)."""
    return subprocess.run([PY, "-c", code], check=True, capture_output=True, text=True).stdout.strip()


# Versions of every replaced distribution
want = {"python-slugify": "9.1.2", "google-genai": "2.18.1", "aiooui": "0.1.11", "dbus-fast": "5.0.24",
        "matter-python-client": "1.4.0+lowmem.1"}
for pkg, v in want.items():
    assert m.version(pkg) == v, (pkg, m.version(pkg), v)
ok("versions " + ", ".join(f"{k} {v}" for k, v in want.items()))

# python-slugify 9.1.2: ASCII fast path
s = __import__("importlib").import_module("slugify.slugify")
assert "isascii" in inspect.getsource(s._transliterate)
ok("slugify fast path")

# dbus-fast compiled (Cython) and importable
assert fresh("import dbus_fast.aio, dbus_fast.message; import dbus_fast._private.marshaller as mm; print(mm.__file__)").endswith(".so")
ok("dbus-fast compiled marshaller")

# matter-python-client lowmem: lazy cluster registry + compact attributes; HA's matter integration imports
r = fresh("import chip.clusters.ClusterObjects as co, chip.clusters.Objects as o; n = dict.__len__(co.ALL_CLUSTERS); "
          "c = co.ALL_CLUSTERS[6]; a = c.Attributes.OnOff; "
          "assert c.__name__ == 'OnOff' and n < 143 and a.attribute_id == 0 and a.cluster_id == 6, (n, c, a); print(n)")
ok(f"chip lazy registry + compact ({r} of 143 clusters loaded at import)")
fresh("import homeassistant.components.matter, homeassistant.components.matter.discovery")
ok("HA matter import")

# Recorder c2cc05c8: importing the schema loads no dialect but SQLite
d = fresh("import sys; from homeassistant.components.recorder import db_schema; "
          "print(sorted({m.split('.')[2] for m in sys.modules if m.startswith('sqlalchemy.dialects.') and m.count('.') >= 2}))")
assert set(eval(d)) <= {"_typing", "sqlite"}, d
ok(f"recorder dialects {d}")

# Recorder SQLite cache 1 MB
assert 'PRAGMA cache_size = -1024"' in open(f"{HA}/components/recorder/util.py", encoding="utf-8").read()
ok("recorder SQLite cache_size -1024")

# Camera 3c74c7b1: helper in place at both call sites, TurboJPEG created only by it, in the executor
from homeassistant.components.camera import img_util  # noqa: E402
import homeassistant.components.camera as cam  # noqa: E402
import homeassistant.components.nest as nest  # noqa: E402

assert "async_ensure_turbojpeg(camera.hass)" in inspect.getsource(cam._async_get_image)
assert "async_ensure_turbojpeg(self.hass)" in inspect.getsource(nest)


class FakeHass:
    async def async_add_executor_job(self, f, *a):
        return await asyncio.get_running_loop().run_in_executor(None, f, *a)


async def _turbo():
    assert not img_util.TurboJPEGSingleton.created()
    await img_util.async_ensure_turbojpeg(FakeHass())
    assert img_util.TurboJPEGSingleton.created()


asyncio.run(_turbo())
ok("camera 3c74c7b1 (TurboJPEG -> %s)" % type(img_util.TurboJPEGSingleton.instance()).__name__)

# U-6 / U-7: patched modules import; what they defer is reported (a stock import elsewhere may still pull it in)
from homeassistant.components.homeassistant_hardware.util import LazyFlasherClass  # noqa: E402,F401

loaded = json.loads(fresh(
    "import json, sys, homeassistant.components.homeassistant_hardware.util, homeassistant.components.stream; "
    "print(json.dumps([m for m in ('universal_silabs_flasher', 'zigpy', 'bellows', 'av', 'numpy', 'turbojpeg') if m in sys.modules]))"))
if loaded:
    warn(f"still loaded by importing homeassistant_hardware.util + stream: {loaded}")
ok("U-6 hardware flasher + U-7 stream imports")

# Holidays lazy-import PR (optional)
if os.environ.get("WITH_HOLIDAYS") == "1":
    r = fresh("import sys, holidays; from holidays.registry import EntityLoader; "
              "n = len(list(EntityLoader.get_country_codes(include_aliases=False))); "
              "loaded = sum(1 for k in sys.modules if k.startswith('holidays.countries.')); "
              "h = holidays.country_holidays('DE', years=2026); assert n > 100 and len(h) > 5, (n, len(h)); "
              "print(n, loaded)")
    fresh("import homeassistant.components.holiday.config_flow, homeassistant.components.workday.config_flow")
    mo = sum(1 for _r, _d, f in os.walk(os.path.dirname(__import__("holidays").__file__) + "/locale") for x in f
             if x.endswith(".mo"))
    assert mo > 100, mo
    ok(f"holidays lazy registry (countries, loaded at import: {r}; {mo} .mo files)")

# hass-nabucasa without pycognito (optional)
if os.environ.get("WITH_NABUCASA") == "1":
    v = m.version("hass-nabucasa")
    assert v.startswith("2.7.0+"), v  # a local version keeps HA's hass-nabucasa==2.7.0 pin satisfied
    bad = fresh("import sys, hass_nabucasa, hass_nabucasa.auth; "
                "print(sorted(k for k in sys.modules if k.split('.')[0] in {'pycognito', 'boto3', 'botocore'}))")
    assert bad == "[]", bad
    ok(f"hass-nabucasa {v} (no pycognito/boto3/botocore imported)")

# Docstrings: placeholder in HA, libraries and the stdlib; real docstrings where code reads them
r = fresh("import homeassistant.core as c, json, asyncio, sqlalchemy.orm.exc as e; "
          "print(c.HomeAssistant.__doc__, json.dumps.__doc__, asyncio.gather.__doc__, '|', (e.__doc__ or '')[:20])")
assert r.startswith(". . . |") and not r.endswith("| ."), r
ok("docstring placeholders (DOCSTRIP_KEEP modules keep theirs)")

# Lazy filter v25 baked, defaults on without /config files
f = json.load(open("/etc/ha-lazy-filter.json"))
assert "vobject" in f["importers"] and "probatio" in f["names"], "baked filter is not v25"
assert os.environ.get("HA_LAZY") == "1" and os.environ.get("PYTHONMALLOC") == "pymalloc"
ok("filter v25 baked, HA_LAZY=1 + PYTHONMALLOC=pymalloc by default")

# Same imports with lazy imports on, every lazy name resolved
mods = ["homeassistant.core", "homeassistant.components.stream", "homeassistant.components.recorder",
        "homeassistant.components.camera", "homeassistant.components.matter", "homeassistant.components.bluetooth",
        "homeassistant.components.homeassistant_hardware.util", "sqlalchemy.orm", "google.genai", "aiooui", "slugify",
        "dbus_fast.aio"] + (["holidays"] if os.environ.get("WITH_HOLIDAYS") == "1" else [])
code = ("import importlib, sys\nbad = []\nfor n in %r:\n    try:\n        mod = importlib.import_module(n)\n"
        "        [getattr(mod, k) for k in list(vars(mod))]\n    except Exception as ex:\n"
        "        bad.append(f'{n}: {type(ex).__name__}: {ex}')\nprint(bad)\n") % mods
r = subprocess.run([PY, "-X", "lazy_imports=all", "-c", code], check=True, capture_output=True, text=True).stdout.strip()
assert r == "[]", r
ok(f"lazy imports: {len(mods)} modules import and resolve")
print("all HA Lite gates passed")
