# Pre-compilacao (2026-09-24; modos de docstring e async_mode em 2026-09-25). Roda NO BUILD da imagem do Core: compila todo .py do HA e das
# bibliotecas trocando cada docstring pelo marcador '.', e grava o .pyc padrao (__pycache__/*.cpython-314.pyc, validado
# por mtime/tamanho do fonte). Na partida o Python so carrega esses .pyc -- sem compilar, sem o modulo ast no Core.
# Os .py nao sao alterados. Pacotes que leem o CONTEUDO de docstrings ficam com a docstring real (KEEP).
import ast
import json
import importlib.util
import os
import sys
from importlib._bootstrap_external import _code_to_timestamp_pyc

# defer_from opcional: DEFER_TARGETS=/caminho/alvos.json (lista de modulos) -> adia `from X import y` (ver defer_from.py)
_tf = os.environ.get("DEFER_TARGETS")
_cfg = json.load(open(_tf)) if _tf else []
if isinstance(_cfg, list):
    _cfg = {"targets": _cfg}
EXCL_LIBS = set(_cfg.get("exclude_libs", []))
EXCL_MODS = tuple(_cfg.get("exclude_modules", []))
TARGETS = [t for t in _cfg.get("targets", []) if t not in EXCL_LIBS]
MANIFEST = os.environ.get("DEFER_MANIFEST")
# (2026-09-25) politicas do defer_from, validadas na suite do HA: async_mode="executor" (uso em async def vira
# `await _defer_import(...)` no executor) e annotation="keep". Chave do JSON; a variavel de ambiente tem precedencia.
ASYNC_MODE = os.environ.get("DEFER_ASYNC") or _cfg.get("async_mode", "keep")
ANNOTATION = os.environ.get("DEFER_ANNOTATION") or _cfg.get("annotation", "keep")
# (2026-09-25) docstrings: DOCSTRIP=remove apaga (corpo vazio -> pass; igual ao DOCSTRIP=1 do hook da suite) ou
# DOCSTRIP=placeholder troca por "." (passo 2). DOCSTRIP_KEEP=/caminho.json: modulos (nome EXATO) que mantem a
# docstring real -- a suite achou 5 (numpy._core.{memmap,multiarray,numeric}, sqlalchemy.orm.{events,exc}).
DOCSTRIP = os.environ.get("DOCSTRIP", "placeholder")
assert DOCSTRIP in ("placeholder", "remove", "none"), f"DOCSTRIP invalido: {DOCSTRIP}"
_kf = os.environ.get("DOCSTRIP_KEEP")
DOC_KEEP = frozenset(json.load(open(_kf))) if _kf else frozenset()
if TARGETS:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from defer_from import defer_from

ROOTS = os.environ.get("PRECOMPILE_ROOTS", "/usr/src/homeassistant/homeassistant:/usr/local/lib/python3.14/site-packages").split(":")
KEEP = ("/ply/", "/click/", "/typer/", "/docopt", "/fire/")
PLACEHOLDER = "."


def strip(tree, mode=None):
    """Troca (placeholder) ou apaga (remove) as docstrings. Devolve quantas mexeu."""
    mode = mode or DOCSTRIP
    if mode == "none":
        return 0
    n = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            b = node.body
            if b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, ast.Constant) and isinstance(b[0].value.value, str):
                if mode == "placeholder":
                    b[0].value.value = PLACEHOLDER
                else:
                    del b[0]
                    if not b and not isinstance(node, ast.Module):
                        b.append(ast.Pass())
                n += 1
    ast.fix_missing_locations(tree)
    return n


def _modname(path):
    for r in ROOTS:
        if path.startswith(r + "/"):
            rel = path[len(r) + 1:-3].replace("/", ".")
            rel = rel[:-9] if rel.endswith(".__init__") else rel
            return rel if r.endswith("site-packages") else os.path.basename(r) + "." + rel
    return path


STAR_EXACT = frozenset()  # preenchido no __main__ por _star_targets_without_all(); passado aos workers pelo initializer


def _set_star(s):
    global STAR_EXACT
    STAR_EXACT = s  # 3.14 usa forkserver por padrao: o worker NAO herda globais do __main__


def _excluded_module(path):
    m = _modname(path)
    if m in STAR_EXACT:
        return True
    # "pkg.mod" = modulo e submodulos; "=pkg.mod" = so aquele modulo
    return any((m == e[1:]) if e.startswith("=") else (m == e or m.startswith(e + ".")) for e in EXCL_MODS)


def _star_scan(p):
    """Um arquivo: (modulo, define __all__?, alvos de `import *`). Separado para rodar em paralelo."""
    import warnings
    mn = _modname(p)
    pkg = mn if p.endswith("/__init__.py") else mn.rpartition(".")[0]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            t = ast.parse(open(p, "rb").read())
    except (SyntaxError, ValueError, OSError):
        return mn, False, ()
    has_all = False
    for s in t.body:  # __all__ so no nivel do modulo (perder um so deixa mais conservador)
        if isinstance(s, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            tg = s.targets if isinstance(s, ast.Assign) else [s.target]
            if any(isinstance(x, ast.Name) and x.id == "__all__" for x in tg):
                has_all = True
    starred = set()
    for s in ast.walk(t):  # import * em qualquer profundidade (try/if): perder um alvo e o lado INSEGURO
        if isinstance(s, ast.ImportFrom) and any(a.name == "*" for a in s.names):
            if s.level:
                base = pkg.split(".")
                if s.level > 1:
                    base = base[: len(base) - (s.level - 1)]
                starred.add(".".join(base + ([s.module] if s.module else [])))
            else:
                starred.add(s.module)
    return mn, has_all, tuple(starred)


def _star_targets_without_all(paths, pool=None):
    """Modulos alvo de `from M import *` (absoluto ou relativo) que NAO definem __all__ (2026-09-24, gate hatest).

    Sem __all__, `import *` copia so o __dict__ do modulo: nomes servidos pelo __getattr__ do defer_from somem para
    quem faz star-import (ex.: zigpy_znp.types <- .zigpy_types: PanId/ZDOStatus -> zha inteiro quebra). Esses modulos
    nunca sao transformados. Gerado da propria imagem a cada build -- nao manter lista a mao.
    (2026-09-25) em paralelo: sob emulacao arm64, 49 mil arquivos em serie levavam ~22 min.
    """
    it = pool.map(_star_scan, paths, chunksize=256) if pool else map(_star_scan, paths)
    starred, has_all = set(), set()
    for mn, ha, st in it:
        if ha:
            has_all.add(mn)
        starred.update(st)
    return frozenset(m for m in starred if m not in has_all)


def _one(path):
    """Compila um .py e grava o .pyc. Devolve (ok, skip, bad, deferred, rec, nodoc)."""
    try:
        src = open(path, "rb").read()
        rec = None
        nd = 0
        if any(k in path for k in KEEP):
            code = compile(src, path, "exec", dont_inherit=True)
            sk, dfr = 1, 0
        else:
            mn = _modname(path)
            tree = ast.parse(src, path)
            dfr = 0
            # ordem igual a do hook validado na suite: defer_from primeiro, docstrings depois
            if TARGETS and not _excluded_module(path):
                dd, _k = defer_from(tree, TARGETS, annotation=ANNOTATION, async_mode=ASYNC_MODE, modname=mn)
                dfr = len(dd)
                if dd:
                    rec = {"arquivo": path, "adiados": dd}
            if mn in DOC_KEEP:
                sk = 1
            else:
                nd = strip(tree)
                sk = 0
            code = compile(tree, path, "exec", dont_inherit=True)
        st = os.stat(path)
        pyc = importlib.util.cache_from_source(path)
        os.makedirs(os.path.dirname(pyc), exist_ok=True)
        with open(pyc, "wb") as fh:
            fh.write(_code_to_timestamp_pyc(code, int(st.st_mtime), st.st_size))
        return (1, sk, 0, dfr, rec if MANIFEST else None, nd)
    except (SyntaxError, ValueError, OSError):
        return (0, 0, 1, 0, None, 0)


if __name__ == "__main__":
    from concurrent.futures import ProcessPoolExecutor

    paths = []
    for root in ROOTS:
        for d, _dirs, files in os.walk(root):
            if "/tests" in d or "/test/" in d:
                continue
            paths.extend(os.path.join(d, f) for f in files if f.endswith(".py"))
    # PRECOMPILE_ONLY=/caminho/lista.txt (um .py por linha): so esses (os modulos que o Core carrega de fato). Os
    # demais ficam com o .pyc normal da imagem -- nada quebra, so nao ganham placeholder/defer.
    if TARGETS:
        # varre TODOS os .py (antes do filtro PRECOMPILE_ONLY): o importador com `import *` pode estar em qualquer lugar
        _sg = os.environ.get("STAR_GUARD_IN")
        if _sg and os.path.exists(_sg):  # rodadas seguintes do gate: a guarda nao muda (os .py nao mudam)
            STAR_EXACT = frozenset(json.load(open(_sg)))
        else:
            with ProcessPoolExecutor(max_workers=int(os.environ.get("JOBS", os.cpu_count() or 1))) as _ex:
                STAR_EXACT = _star_targets_without_all(paths, _ex)
        print(f"guarda import *: {len(STAR_EXACT)} modulos sem __all__ nunca transformados", file=sys.stderr)
        if os.environ.get("STAR_GUARD_OUT"):
            json.dump(sorted(STAR_EXACT), open(os.environ["STAR_GUARD_OUT"], "w"), indent=0)
    _only = os.environ.get("PRECOMPILE_ONLY")
    if _only:
        keep = {l.strip() for l in open(_only) if l.strip().endswith(".py")}
        paths = [p for p in paths if p in keep]
    print(f"defer_from: {len(TARGETS)} alvos, async_mode={ASYNC_MODE}, annotation={ANNOTATION}; docstrings={DOCSTRIP}"
          f" (keep: {len(DOC_KEEP)} modulos); arquivos: {len(paths)}", file=sys.stderr)
    tot = [0, 0, 0, 0]
    ndoc = 0
    man = {}
    with ProcessPoolExecutor(max_workers=int(os.environ.get("JOBS", os.cpu_count() or 1)),
                             initializer=_set_star, initargs=(STAR_EXACT,)) as ex:
        for r in ex.map(_one, paths, chunksize=64):
            tot = [a + b for a, b in zip(tot, r[:4])]
            ndoc += r[5]
            if r[4]:
                man[_modname(r[4]["arquivo"])] = r[4]
    stats = {"pyc": tot[0], "com_docstring_real": tot[1], "ignorados": tot[2], "modulos_com_adiamento": len(man),
             "imports_adiados": tot[3], "docstrings_" + DOCSTRIP: ndoc, "star_guard": len(STAR_EXACT),
             "async_mode": ASYNC_MODE, "annotation": ANNOTATION}
    if MANIFEST:
        json.dump(man, open(MANIFEST, "w"), indent=0)
        json.dump(stats, open(os.path.splitext(MANIFEST)[0] + ".stats.json", "w"), indent=1)
    print(f"precompilado: {stats}", file=sys.stderr)
