# Instala sys.set_lazy_imports_filter a partir de LAZY_FILTER=/p/filtro.json:
#   {"importers": ["json", ...]}  -> imports feitos DENTRO desses modulos (prefixo) ficam eager
#   {"names": ["x.y", ...]}       -> imports DESSES modulos (prefixo) ficam eager em qualquer lugar
#   {"intra_pkg": true}          -> imports dentro do mesmo pacote de topo ficam eager
#   "*sufixo" casa por sufixo (ex.: "*_pb2" = modulos gerados do protobuf)
import json as _j, os as _o, sys as _s
_p = _o.environ.get("LAZY_FILTER")
if _p and hasattr(_s, "set_lazy_imports_filter"):
    _c = _j.load(open(_p)); _I = tuple(_c.get("importers", [])); _N = tuple(_c.get("names", []))
    def _m(x, pre): return any((x.endswith(e[1:]) or (e[1:] + ".") in x) if e[0] == "*" else (x == e or x.startswith(e + ".")) for e in pre)
    _SAME = bool(_c.get("intra_pkg"))  # true: import de um modulo do MESMO pacote de topo fica eager
    def _filter(importer, name, fromlist):
        if _SAME and importer and name and importer.partition(".")[0] == name.partition(".")[0]:
            return False
        return not (_m(importer or "", _I) or _m(name or "", _N))
    _s.set_lazy_imports_filter(_filter)
    # Modulos carregados ANTES deste hook (ex.: tokenize, com `from builtins import open as _builtin_open`) nao passam
    # pelo filtro. Com LAZY_REIFY_EARLY=1, resolvemos ja os lazy objects deles: evita capturar builtins.open depois que
    # o HA faz monkeypatch (deteccao de I/O bloqueante -> RecursionError).
    if _o.environ.get("LAZY_REIFY_EARLY") == "1":
        _n = 0
        for _mod in list(_s.modules.values()):
            _d = getattr(_mod, "__dict__", None)
            if not isinstance(_d, dict): continue
            for _k, _v in list(_d.items()):
                if type(_v).__name__ == "lazy_import":
                    try: getattr(_mod, _k); _n += 1
                    except Exception: pass
        _s._lazy_reified_early = _n
# LAZY_PRELOAD=a,b: importa esses modulos ja (eager). Ex.: tokenize precisa estar carregado ANTES do HA trocar
# builtins.open (homeassistant.block_async_io), senao `from builtins import open as _builtin_open` captura a versao
# protegida e o detector de I/O bloqueante entra em recursao (linecache -> tokenize.open -> open protegido -> ...).
for _m2 in filter(None, _o.environ.get("LAZY_PRELOAD", "").split(",")):
    __import__(_m2)
# LAZY_MOCK_FIX=1 (so para testes): unittest.mock._patch.get_original le target.__dict__[name] direto e recebe o
# proxy types.LazyImportType em vez da funcao/classe real -> escolhe MagicMock em vez de AsyncMock, autospec do proxy,
# etc. Aqui reificamos o nome antes (getattr no modulo resolve o lazy import).
if _o.environ.get("LAZY_MOCK_FIX") == "1":
    import types as _t, unittest.mock as _um
    _LT = getattr(_t, "LazyImportType", None)
    _orig_get = _um._patch.get_original
    def _get_original(self):
        try:
            tgt = self.getter(); d = getattr(tgt, "__dict__", None)
            if _LT and isinstance(d, dict) and isinstance(d.get(self.attribute), _LT):
                getattr(tgt, self.attribute)
                if isinstance(d.get(self.attribute), _LT):   # modulo nao substituiu no dict: substitui nos
                    d[self.attribute] = getattr(tgt, self.attribute)
        except Exception:
            pass
        return _orig_get(self)
    _um._patch.get_original = _get_original
