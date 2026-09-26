# Supervisor memory probe from the inside (sys.remote_exec is refused in the Supervisor container, probably by its
# AppArmor profile). Loaded by sup_probe_timer.pth only when SUP_PROBE=<seconds> is set (from /data/sup-py315.conf):
# after that delay a background thread runs /data/homeassistant/memtest/trace_split_sup315.py, which writes its result
# next to itself. Start the interpreter with -X tracemalloc=1 (SUP_PY_FLAGS) for the data part of the split.
import os
import threading
import time

_SCRIPT = "/data/homeassistant/memtest/trace_split_sup315.py"


def _run(delay):
    time.sleep(delay)
    try:
        exec(compile(open(_SCRIPT).read(), "trace_split_sup315", "exec"), {"__name__": "tssup"})
    except SystemExit:
        pass
    except BaseException as ex:  # the probe must never take the Supervisor down
        open(_SCRIPT.replace(".py", ".err"), "w").write(repr(ex))


try:
    _delay = int(os.environ.get("SUP_PROBE", "0"))
except ValueError:
    _delay = 0
if _delay > 0 and os.path.exists(_SCRIPT):
    threading.Thread(target=_run, args=(_delay,), name="sup-probe", daemon=True).start()
