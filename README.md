# ha-python315-arm64 (side project, experiment)

Home Assistant 2026.9.3, using the **official aarch64 image, unchanged**, plus **Python 3.15** installed next to
3.14. Every package the image ships gets a cp315 wheel, and Core starts on 3.15 with **PEP 810 lazy imports**
(`-X lazy_imports=all`) and an exclusion filter (`lazy/filter_v12.json`).

Purpose: measure how much memory Home Assistant Core saves with Python 3.15 lazy imports on a small ARM host.
Results on x86:
- Import benchmark (27 integrations): 3.14 at 476 MiB RSS, 3.15 with lazy imports at 266 MiB.
- Real start with `default_config`: 376 MiB on 3.14, 288 MiB on 3.15 with lazy imports.

Python 3.15 is still a release candidate. **This is not for production.** As of 2026-09-25, Home Assistant's
`docker-base` has no Python 3.15 image.

- `.github/workflows/build.yml` has four stages:
  - plan;
  - 8 parallel wheel jobs on native arm64 runners;
  - the image;
  - a smoke test, then the push to GHCR.
- Switches, set as environment variables on the Core container:
  - `HA_PYTHON=3.14` starts the original interpreter;
  - `HA_PY_FLAGS=""` runs 3.15 without lazy imports.
- `lazy/ha_lazy_hook.py` installs `sys.set_lazy_imports_filter` from the `LAZY_FILTER` file.
  - `LAZY_PRELOAD=tokenize` and `LAZY_REIFY_EARLY=1` work around HA's patch of `builtins.open`. The comments in the
    hook explain why.
- The report artifact lists every package that failed to build or import on 3.15.
