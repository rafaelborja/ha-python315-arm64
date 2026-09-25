# ha-python315-arm64 (side project, experiment)

Home Assistant 2026.9.3 on **Python 3.15 RC**, built on the **official aarch64 image, unchanged**: Python 3.15 is
installed next to 3.14 and every package the image ships gets a cp315 wheel. Core starts on 3.15. PEP 810 lazy
imports (`-X lazy_imports=all`) are **off by default** and are switched on at runtime, with an editable exclusion
list, so tuning needs no rebuild.

Python 3.15 is still a release candidate. **This is not for production.** As of 2026-09-25, Home Assistant's
`docker-base` has no Python 3.15 image.

## Workflow (`.github/workflows/build.yml`, manual dispatch, native arm64 runners)
1. **plan**: the installed packages of the official image, plus `extras/vm-runtime.txt` (what the target VM's
   custom components install at runtime) and HA's `requirements_test.txt`. Fails when the HA image and the
   Python image are on different Alpine releases.
2. **wheels**: 8 chunks plus the test dependencies, built in `Dockerfile.builder` (the apk list of HA's own
   `wheels.yml`).
3. **image**: `Dockerfile.image`, then interpreter smoke tests, then a push to `ghcr.io/<owner>/ha-py315`. It also
   starts Home Assistant for real three times (3.14, 3.15, 3.15 + lazy) with `default_config`. Last, it saves the
   image as a tarball artifact for `docker load`.
4. **import-check**: `scripts/import_check.py` imports every package and every integration in 3.14 / 3.15 /
   3.15 + lazy, each in a fresh process. It then resolves every lazy name, so bugs that mocked tests hide show up.
5. **tests**: HA's test suite for the same tag, 16 shards, 3.15 eager vs 3.15 lazy. Files holding candidate
   regressions are rerun in both modes, separating real regressions from flaky tests.
6. **report**: one summary (`report-final` artifact).

## Runtime switches (Supervisor-managed installs cannot change the container environment)
`/config/ha-py315.conf`, one `KEY=value` per line (only these keys are read; the file is never sourced):
- `HA_LAZY=1`: lazy imports on;
- `HA_PYTHON=3.14`: the original interpreter;
- `HA_PY_FLAGS=...`: extra 3.15 flags;
- `PYTHONMALLOC=pymalloc|mimalloc`: the allocator (default mimalloc, as in the official image).

`/config/ha-lazy-filter.json` holds exclusions ADDED to the baked `lazy/filter_v15.json`; with `"replace": true` it
replaces it. The format is explained in `lazy/ha_lazy_hook.py`. If no filter loads, every import is made eager.
Restart Core to apply.

On 3.15 the run script also sets `UV_PYTHON`. Without it, HA's runtime package installs (`python -m uv pip install`
with `UV_SYSTEM_PYTHON`) would go to 3.14.
