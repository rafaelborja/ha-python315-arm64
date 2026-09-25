"""Compare one shard's junit results: 3.15 without lazy imports ("eager") vs 3.15 + lazy imports ("lazy").

Usage:
  python compare_tests.py DIR CORE_CHECKOUT            -> DIR/rerun_files.txt (files holding candidate regressions)
  python compare_tests.py DIR CORE_CHECKOUT --final    -> DIR/final.json, using the reruns too
Reads DIR/eager.xml, DIR/lazy.xml and, with --final, DIR/eager-rerun.xml and DIR/lazy-rerun.xml.
A regression is a test that passed eagerly and failed (failure or error) with lazy imports. With --final it is
CONFIRMED only when it passed in both eager runs and failed in both lazy runs; otherwise it is FLAKY.
"""
import json
import pathlib
import sys
import xml.etree.ElementTree as ET


def outcomes(path: pathlib.Path) -> dict[str, tuple[str, str]] | None:
    if not path.exists() or path.stat().st_size == 0:
        return None
    res = {}
    for tc in ET.parse(path).iter("testcase"):
        tid = f"{tc.get('classname', '')}::{tc.get('name', '')}"
        state, msg = "passed", ""
        for tag in ("failure", "error", "skipped"):
            el = tc.find(tag)
            if el is not None:
                state, msg = tag, (el.get("message") or "")[:300]
                break
        if res.get(tid, ("passed",))[0] == "passed":  # setup/teardown errors can repeat an id: keep the worst
            res[tid] = (state, msg)
    return res


def bad(o) -> bool:
    return o is not None and o[0] in ("failure", "error")


def test_file(core: pathlib.Path, tid: str) -> str | None:
    classname = tid.split("::", 1)[0] or tid.split("::", 1)[1]
    parts = classname.split(".")
    for k in range(len(parts), 0, -1):
        cand = core.joinpath(*parts[:k]).with_suffix(".py")
        if cand.exists():
            return cand.relative_to(core).as_posix()
    return None


def main() -> None:
    d, core, final = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), "--final" in sys.argv
    eager, lazy = outcomes(d / "eager.xml"), outcomes(d / "lazy.xml")
    result = {"eager_ran": eager is not None, "lazy_ran": lazy is not None}
    if eager is None or lazy is None:
        result["error"] = "a run produced no junit file (session crashed?)"
        cands = []
    else:
        cands = sorted(t for t, o in lazy.items() if bad(o) and eager.get(t, ("missing",))[0] == "passed")
        missing = sorted(t for t, o in eager.items() if o[0] == "passed" and t not in lazy)
        result.update(counts={m: {s: sum(1 for o in r.values() if o[0] == s)
                                  for s in ("passed", "failure", "error", "skipped")}
                              for m, r in (("eager", eager), ("lazy", lazy))},
                      missing_in_lazy=missing)
    if not final:
        files = sorted({f for t in cands if (f := test_file(core, t))})
        (d / "rerun_files.txt").write_text("\n".join(files) + ("\n" if files else ""))
        print(f"{len(cands)} candidate regressions in {len(files)} files")
        return
    e2, l2 = outcomes(d / "eager-rerun.xml") or {}, outcomes(d / "lazy-rerun.xml") or {}
    confirmed, flaky = [], []
    for t in cands:
        entry = {"test": t, "lazy": lazy[t][1], "lazy_rerun": (l2.get(t) or ("missing", ""))[1]}
        if bad(l2.get(t)) and (e2.get(t) or ("missing",))[0] == "passed":
            confirmed.append(entry)
        else:
            flaky.append(entry)
    result.update(confirmed=confirmed, flaky=flaky)
    (d / "final.json").write_text(json.dumps(result, indent=1))
    print(f"confirmed lazy regressions: {len(confirmed)}, flaky: {len(flaky)}, "
          f"missing in lazy: {len(result.get('missing_in_lazy', []))}{' ERROR: ' + result['error'] if 'error' in result else ''}")


if __name__ == "__main__":
    main()
