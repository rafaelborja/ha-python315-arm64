"""Merge the import-check and test-suite results into one report (Markdown on stdout, JSON in OUTDIR).

Usage: python report.py IN_DIR OUTDIR
IN_DIR/import/import-*.json (import_check.py), IN_DIR/tests/shard-*/final.json (compare_tests.py),
IN_DIR/image/summary.md (wheel build + real start).
"""
import json
import pathlib
import sys

src, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
rep = {"import": {"regress_315": {}, "regress_lazy": {}, "fail_314": 0, "targets": 0}, "tests": {}}

for f in sorted((src / "import").glob("import-*.json")):
    d = json.loads(f.read_text())
    rep["import"]["targets"] += len(d["targets"])
    rep["import"]["fail_314"] += len(d["fail_314"])
    for kind, mode in (("regress_315", "315"), ("regress_lazy", "lazy")):
        for k in d[kind]:
            rep["import"][kind][k] = d["targets"][k].get(mode)

shards = sorted((src / "tests").glob("shard-*/final.json"), key=lambda p: int(p.parent.name.split("-")[1]))
tot = {"confirmed": [], "flaky": [], "missing_in_lazy": [], "errors": [], "counts": {}}
for f in shards:
    d = json.loads(f.read_text())
    tot["confirmed"] += d.get("confirmed", [])
    tot["flaky"] += d.get("flaky", [])
    tot["missing_in_lazy"] += d.get("missing_in_lazy", [])
    if "error" in d:
        tot["errors"].append(f"{f.parent.name}: {d['error']}")
    for mode, c in d.get("counts", {}).items():
        agg = tot["counts"].setdefault(mode, {})
        for k, v in c.items():
            agg[k] = agg.get(k, 0) + v
rep["tests"] = {**tot, "shards_reported": len(shards)}
(out / "report.json").write_text(json.dumps(rep, indent=1))

p = print
if (src / "image" / "summary.md").exists():
    p((src / "image" / "summary.md").read_text())
i = rep["import"]
p(f"## Import check: {i['targets']} targets (packages + integrations)")
p(f"- 3.15 regressions vs 3.14: **{len(i['regress_315'])}**; lazy regressions vs 3.15: **{len(i['regress_lazy'])}**; "
  f"broken on 3.14 too (ignored): {i['fail_314']}")
for kind in ("regress_315", "regress_lazy"):
    if i[kind]:
        p(f"\n### {kind}\n```")
        for k, v in sorted(i[kind].items()):
            p(f"{k}: {json.dumps(v)[:400]}")
        p("```")
t = rep["tests"]
p(f"\n## HA test suite, 3.15 eager vs 3.15 lazy ({t['shards_reported']} shards reported)")
for mode, c in t["counts"].items():
    p(f"- {mode}: {c}")
p(f"- **confirmed lazy regressions: {len(t['confirmed'])}**, flaky (not reproduced): {len(t['flaky'])}, "
  f"passed eagerly but missing in lazy: {len(t['missing_in_lazy'])}")
for e in t["errors"]:
    p(f"- ERROR {e}")
if t["confirmed"]:
    p("\n### Confirmed regressions\n```")
    for c in t["confirmed"]:
        p(f"{c['test']}: {c['lazy'][:200]}")
    p("```")
