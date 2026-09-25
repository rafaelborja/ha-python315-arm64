

# --- ha-python315: Alpine/musl find_library fallback, appended at image build time ---------------------------------
# HA's own Python 3.14 (built by Alpine's recipe) carries this patch; the official python:3.15-alpine image does not,
# so on musl find_library() returned None for libraries that exist (libpcap -> no DHCP discovery). Same search as the
# Alpine patch: LD_LIBRARY_PATH, then /lib, /usr/local/lib, /usr/lib, accepting only ELF files.
_ha_upstream_find_library = find_library


_ha_musl_cache = {}


def _ha_musl_find_library(name):
    # cached: a lookup can run on HA's event loop when the importing module was imported lazily
    if name in _ha_musl_cache:
        return _ha_musl_cache[name]
    _ha_musl_cache[name] = result = _ha_musl_search(name)
    return result


def _ha_musl_search(name):
    from glob import glob

    def is_elf(path):
        try:
            with open(path, "rb") as fh:
                return fh.read(4) == b"\x7fELF"
        except OSError:
            return False

    if os.path.isabs(name):
        return name
    if name in ("m", "crypt", "pthread"):
        name = "c"
    elif name in ("libm.so", "libcrypt.so", "libpthread.so"):
        name = "libc.so"
    paths = ["/lib", "/usr/local/lib", "/usr/lib"]
    if "LD_LIBRARY_PATH" in os.environ:
        paths = os.environ["LD_LIBRARY_PATH"].split(":") + paths
    for d in paths:
        f = os.path.join(d, name)
        if is_elf(f):
            return os.path.basename(f)
        prefix = os.path.join(d, "lib" + name)
        for suffix in (".so", ".so.*"):
            for f in sorted(glob(prefix + suffix)):
                if is_elf(f):
                    return os.path.basename(f)
    return None


def find_library(name, *args, **kwargs):
    return _ha_upstream_find_library(name, *args, **kwargs) or _ha_musl_find_library(name)
