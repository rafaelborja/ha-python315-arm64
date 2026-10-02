# HA Lite U-7 (generic): stream loads numpy and PyAV only when used; camera/stream create TurboJPEG on first use.
# Same change as home-assistant/core PR #183145 (stream part). The camera img_util.py it edits is then replaced by the
# file of commit 3c74c7b1 (patch_camera_3c74c7b1.py). Original comments below are in Portuguese.
# U-7 (prototipo): o componente `stream` deixa de carregar numpy e PyAV/FFmpeg na partida.
#  - core.py:     `import numpy as np` so para anotacoes; as transformacoes de imagem importam numpy na hora.
#  - recorder.py: `import av` dentro de async_record (unico lugar que usa av).
#  - __init__.py: o setup nao chama mais set_pyav_logging (que importava av so para baixar o log do libav);
#  - worker.py:   o nivel de log do libav e aplicado quando o worker e importado (ele ja importa av).
# Aplicado no build da imagem do Core; falha alto se o codigo do HA nao for o esperado.
import sys

D = "/usr/src/homeassistant/homeassistant/components/stream/"

def patch(fn, pairs):
    p = D + fn
    s = open(p, encoding="utf-8").read()
    for a, b in pairs:
        if s.count(a) != 1:
            sys.exit(f"U-7: trecho nao encontrado (ou repetido) em {fn}: {a[:60]!r}")
        s = s.replace(a, b)
    open(p, "w", encoding="utf-8").write(s)

patch("core.py", [
    ("import numpy as np\n", ""),
    ("if TYPE_CHECKING:\n    from av import Packet, VideoCodecContext\n",
     "if TYPE_CHECKING:\n    from av import Packet, VideoCodecContext\n    import numpy as np\n"),
    ("TRANSFORM_IMAGE_FUNCTION = (\n",
     "def _numpy() -> Any:\n    \"\"\"Import numpy only when an image is transformed.\"\"\"\n"
     "    import numpy  # noqa: PLC0415\n\n    return numpy\n\n\nTRANSFORM_IMAGE_FUNCTION = (\n"),
])
s = open(D + "core.py", encoding="utf-8").read()
start = s.index("TRANSFORM_IMAGE_FUNCTION = (")
end = s.index(")\n\n", start)
block = s[start:end].replace("np.", "_numpy().")
open(D + "core.py", "w", encoding="utf-8").write(s[:start] + block + s[end:])

patch("recorder.py", [
    ("import av\nimport av.container\n\n", ""),
    ("if TYPE_CHECKING:\n", "if TYPE_CHECKING:\n    import av.container\n\n"),
    ('        """Handle saving stream."""\n',
     '        """Handle saving stream."""\n        import av  # noqa: PLC0415\n'),
])

patch("__init__.py", [
    ("    # This will load av so we run it in the executor\n"
     "    with async_pause_setup(hass, SetupPhases.WAIT_IMPORT_PACKAGES):\n"
     "        await hass.async_add_executor_job(set_pyav_logging, debug_enabled)\n",
     "    # PyAV is imported lazily by the stream worker, which sets the libav log level\n"),
])

patch("worker.py", [
    ("_LOGGER = logging.getLogger(__name__)\n",
     "_LOGGER = logging.getLogger(__name__)\n"
     "# Only pass through PyAV log messages if stream logging is at DEBUG (set here, when av is first loaded)\n"
     "av.logging.set_level(\n"
     "    av.logging.VERBOSE\n"
     "    if logging.getLogger(\"homeassistant.components.stream\").isEnabledFor(logging.DEBUG)\n"
     "    else av.logging.FATAL\n"
     ")\n"),
])
# camera/img_util.py: TurboJPEG (libturbojpeg + numpy) era importado e instanciado no import do modulo.
D2 = "/usr/src/homeassistant/homeassistant/components/camera/"
def patch2(path, pairs):
    s = open(path, encoding="utf-8").read()
    for a, b in pairs:
        if s.count(a) != 1:
            sys.exit(f"U-7: trecho nao encontrado (ou repetido) em {path}: {a[:60]!r}")
        s = s.replace(a, b)
    open(path, "w", encoding="utf-8").write(s)

patch2(D2 + "img_util.py", [
    ("from turbojpeg import TurboJPEG\n\nif TYPE_CHECKING:\n    from . import Image\n",
     "if TYPE_CHECKING:\n    from turbojpeg import TurboJPEG\n\n    from . import Image\n"),
    ("            TurboJPEGSingleton.__instance = TurboJPEG()\n",
     "            from turbojpeg import TurboJPEG  # noqa: PLC0415\n\n            TurboJPEGSingleton.__instance = TurboJPEG()\n"),
    ("# TurboJPEG loads libraries that do blocking I/O.\n# Initialize TurboJPEGSingleton in the executor to avoid\n"
     "# blocking the event loop.\nTurboJPEGSingleton.instance()\n",
     "# TurboJPEG loads libraries that do blocking I/O, so it is created on first use,\n"
     "# which happens in the executor (scale_jpeg_camera_image, stream keyframe converter).\n"),
])
patch2(D + "core.py", [
    ("        self._turbojpeg = TurboJPEGSingleton.instance()\n",
     "        self._turbojpeg: Any = None  # created on first use, in the executor\n"),
    ("        if not (self._turbojpeg and self._packet and self._codec_context):\n",
     "        if self._turbojpeg is None:\n            self._turbojpeg = TurboJPEGSingleton.instance()\n"
     "        if not (self._turbojpeg and self._packet and self._codec_context):\n"),
    ("        from homeassistant.components.camera import TurboJPEGSingleton  # noqa: PLC0415\n\n",
     ""),
    ("    def _generate_image(self, width: int | None, height: int | None) -> None:\n",
     "    def _generate_image(self, width: int | None, height: int | None) -> None:\n"
     "        from homeassistant.components.camera import TurboJPEGSingleton  # noqa: PLC0415\n\n"),
])
print("U-7 aplicado (stream + camera/img_util)")
