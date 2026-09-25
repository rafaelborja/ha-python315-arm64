# PEP 810 exclusion filter for Home Assistant, loaded at interpreter start by ha_lazy_hook.pth.
#
# Filter file (JSON):
#   {"importers": ["json", ...]}  imports made INSIDE these modules (and their submodules) stay eager
#   {"names": ["x.y", ...]}       these modules (and their submodules) are always imported eagerly
#   {"intra_pkg": true}           imports within the same top-level package stay eager
#   "*suffix" entries match by suffix (e.g. "*_pb2" = protobuf generated modules)
#
# Sources, in order:
#   LAZY_FILTER           the list baked into the image (default /etc/ha-lazy-filter.json)
#   LAZY_FILTER_OVERRIDE  an editable list (default /config/ha-lazy-filter.json): its entries are ADDED to the
#                         baked list; with "replace": true it replaces the baked list instead.
# If lazy imports are on and no usable filter loads, every import is made eager rather than let Core start
# unfiltered (orjson alone stops HA from starting without the filter).
#
# Other switches:
#   LAZY_PRELOAD=a,b     import these modules eagerly right away (tokenize: see below)
#   LAZY_REIFY_EARLY=1   resolve lazy objects of modules loaded before this hook ran
#   LAZY_MOCK_FIX=1      tests only: make unittest.mock see real objects instead of lazy proxies
import json as _json, os as _os, sys as _sys


def _say(msg):
    print(f"ha_lazy_hook: {msg}", file=_sys.stderr, flush=True)


def _load(path):
    with open(path, encoding="utf-8") as f:
        cfg = _json.load(f)
    if not isinstance(cfg, dict):
        raise ValueError("top level must be an object")
    for key in ("importers", "names"):
        if not all(isinstance(e, str) and e for e in cfg.get(key, [])):
            raise ValueError(f"{key} must be a list of non-empty strings")
    return cfg


def _matcher(entries):
    exact = tuple(e for e in entries if not e.startswith("*"))
    suffixes = tuple(e[1:] for e in entries if e.startswith("*"))

    def match(mod):
        if not mod:
            return False
        for e in exact:
            if mod == e or mod.startswith(e + "."):
                return True
        for s in suffixes:
            if mod.endswith(s) or (s + ".") in mod:
                return True
        return False

    return match


def _install():
    if not hasattr(_sys, "set_lazy_imports_filter"):
        return
    # While .pth files run, sys.get_lazy_imports() still says "normal": -X lazy_imports=all / PYTHON_LAZY_IMPORTS
    # is applied after site. sys.flags.lazy_imports already holds it (1 = all). For the same reason a mode change
    # made here would be overwritten; a filter is not, so the fallback below is an all-eager filter.
    lazy_on = getattr(_sys.flags, "lazy_imports", -1) == 1 or _sys.get_lazy_imports() == "all"
    base_path = _os.environ.get("LAZY_FILTER", "/etc/ha-lazy-filter.json")
    over_path = _os.environ.get("LAZY_FILTER_OVERRIDE", "/config/ha-lazy-filter.json")
    cfg, used = None, []
    try:
        cfg = _load(base_path)
        used.append(base_path)
    except Exception as err:  # noqa: BLE001
        _say(f"cannot load {base_path}: {err!r}")
    if over_path and _os.path.exists(over_path):
        try:
            over = _load(over_path)
            if over.get("replace") or cfg is None:
                cfg = over
            else:
                for key in ("importers", "names"):
                    cfg[key] = list(dict.fromkeys(cfg.get(key, []) + over.get(key, [])))
                cfg["intra_pkg"] = bool(cfg.get("intra_pkg") or over.get("intra_pkg"))
            used.append(over_path)
        except Exception as err:  # noqa: BLE001
            _say(f"ignoring {over_path}: {err!r}")
    if cfg is None:
        if lazy_on:
            _sys.set_lazy_imports_filter(lambda importer, name, fromlist: False)
            _say("no usable filter: every import made eager (lazy imports effectively OFF)")
        return
    importer_eager = _matcher(cfg.get("importers", []))
    name_eager = _matcher(cfg.get("names", []))
    same_pkg = bool(cfg.get("intra_pkg"))

    def _filter(importer, name, fromlist):
        try:
            if same_pkg and importer and name and importer.partition(".")[0] == name.partition(".")[0]:
                return False
            return not (importer_eager(importer) or name_eager(name))
        except Exception:  # noqa: BLE001 - a filter error must never break an import
            return False

    _sys.set_lazy_imports_filter(_filter)
    if lazy_on:
        _say(f"lazy imports ON, filter {' + '.join(used)}: "
             f"{len(cfg.get('importers', []))} importers, {len(cfg.get('names', []))} names")
    # Modules loaded BEFORE this hook (e.g. tokenize, with `from builtins import open as _builtin_open`) were not
    # filtered. LAZY_REIFY_EARLY=1 resolves their lazy objects now, so none of them captures builtins.open after
    # HA patches it (blocking I/O detection -> RecursionError).
    if lazy_on and _os.environ.get("LAZY_REIFY_EARLY") == "1":
        n = 0
        for mod in list(_sys.modules.values()):
            d = getattr(mod, "__dict__", None)
            if not isinstance(d, dict):
                continue
            for k, v in list(d.items()):
                if type(v).__name__ == "lazy_import":
                    try:
                        getattr(mod, k)
                        n += 1
                    except Exception:  # noqa: BLE001
                        pass
        _sys._lazy_reified_early = n


_install()

# LAZY_PRELOAD=a,b: import these now (eager). tokenize must be loaded BEFORE HA replaces builtins.open
# (homeassistant.block_async_io); otherwise `from builtins import open as _builtin_open` captures the guarded version
# and the blocking I/O detector recurses (linecache -> tokenize.open -> guarded open -> ...).
for _name in filter(None, _os.environ.get("LAZY_PRELOAD", "").split(",")):
    try:
        __import__(_name)
    except Exception as _err:  # noqa: BLE001
        _say(f"preload {_name} failed: {_err!r}")

# LAZY_MOCK_FIX=1 (tests only): unittest.mock._patch.get_original reads target.__dict__[name] directly and gets the
# lazy proxy instead of the real function/class -> MagicMock instead of AsyncMock, autospec of the proxy, etc.
# Resolve the name first (getattr on the module resolves the lazy import).
if _os.environ.get("LAZY_MOCK_FIX") == "1":
    import types as _t, unittest.mock as _um

    _LT = getattr(_t, "LazyImportType", None)
    _orig_get = _um._patch.get_original

    def _get_original(self):
        try:
            tgt = self.getter()
            d = getattr(tgt, "__dict__", None)
            if _LT and isinstance(d, dict) and isinstance(d.get(self.attribute), _LT):
                getattr(tgt, self.attribute)
                if isinstance(d.get(self.attribute), _LT):  # the module did not replace it in its dict: we do
                    d[self.attribute] = getattr(tgt, self.attribute)
        except Exception:  # noqa: BLE001
            pass
        return _orig_get(self)

    _um._patch.get_original = _get_original
