# HA Lite U-6 (generic; applies to any install): universal_silabs_flasher (and with it zigpy + bellows) is imported only
# when a stick is probed or flashed. Same change as home-assistant/core PR #183144. Applied to the stock 2026.9.3 source;
# fails loudly if any anchor is missing. Original comments below are in Portuguese.
# U-6 (prototipo): o universal_silabs_flasher (e com ele zigpy + bellows, ~16 MiB, 199 modulos) so e importado quando
# alguem sonda/grava um stick. Hoje ele entra na partida de toda instalacao com otbr/SkyConnect/Yellow/ZBT-2, porque:
#   - homeassistant_hardware/{util,firmware_config_flow,update}.py importam o flasher no topo;
#   - SkyConnect/Yellow/ZBT-2 (config_flow e update) fazem `_flasher_cls = XFlasher` na definicao da classe.
# Correcao: TYPE_CHECKING para anotacoes; imports dentro das funcoes que usam; e um descritor LazyFlasherClass que
# resolve a classe do flasher no primeiro acesso a `_flasher_cls`. A sonda de uso mostrou que na partida o flasher,
# o zigpy e o bellows so executam definicoes de classe (nada sonda o stick) -> adiar tira o custo inteiro.
import re
import sys

C = "/usr/src/homeassistant/homeassistant/components/"
TC = "import typing as _t\n\nif _t.TYPE_CHECKING:\n"


def edit(fn, pairs):
    p = C + fn
    s = open(p, encoding="utf-8").read()
    for a, b in pairs:
        if s.count(a) != 1:
            sys.exit(f"U-6: trecho nao encontrado (ou repetido) em {fn}: {a[:70]!r}")
        s = s.replace(a, b)
    open(p, "w", encoding="utf-8").write(s)


def indent_before(fn, anchor, line):
    """Insere `line` antes da linha que contem `anchor`, com a mesma indentacao."""
    p = C + fn
    s = open(p, encoding="utf-8").read()
    m = [x for x in re.finditer(rf"^([ \t]*)[^\n]*{re.escape(anchor)}", s, re.M)]
    if len(m) != 1:
        sys.exit(f"U-6: ancora {anchor!r} em {fn}: {len(m)} ocorrencias")
    ind = m[0].group(1)
    s = s[:m[0].start()] + f"{ind}{line}\n" + s[m[0].start():]
    open(p, "w", encoding="utf-8").write(s)


H = "homeassistant_hardware/"
# util.py
edit(H + "util.py", [
    ("from universal_silabs_flasher.const import ApplicationType as FlasherApplicationType\n"
     "from universal_silabs_flasher.firmware import parse_firmware_image\n"
     "from universal_silabs_flasher.flasher import BaseFlasher, DeviceSpecificFlasher, Flasher\n",
     TC + "    from universal_silabs_flasher.const import ApplicationType as FlasherApplicationType\n"
     "    from universal_silabs_flasher.flasher import BaseFlasher, DeviceSpecificFlasher\n"),
    ("        return FlasherApplicationType(self.value)\n",
     "        from universal_silabs_flasher.const import (  # noqa: PLC0415\n"
     "            ApplicationType as FlasherApplicationType,\n        )\n\n"
     "        return FlasherApplicationType(self.value)\n"),
])
indent_before(H + "util.py", "flasher = Flasher(", "from universal_silabs_flasher.flasher import Flasher  # noqa: PLC0415")
indent_before(H + "util.py", "fw_image = await hass.async_add_executor_job(parse_firmware_image",
              "from universal_silabs_flasher.firmware import parse_firmware_image  # noqa: PLC0415")
s = open(C + H + "util.py", encoding="utf-8").read()
s += '''

class LazyFlasherClass:
    """Classe do universal_silabs_flasher resolvida no primeiro acesso (o flasher puxa zigpy e bellows)."""

    def __init__(self, name: str) -> None:
        """Guarda so o nome da classe."""
        self._name = name

    def __get__(self, obj: object, objtype: type | None = None) -> type:
        """Importa o flasher na primeira vez que alguem pede a classe."""
        from universal_silabs_flasher import flasher  # noqa: PLC0415

        return getattr(flasher, self._name)
'''
open(C + H + "util.py", "w", encoding="utf-8").write(s)

# firmware_config_flow.py
edit(H + "firmware_config_flow.py", [
    ("from universal_silabs_flasher.common import Version\n"
     "from universal_silabs_flasher.firmware import NabuCasaMetadata\n"
     "from universal_silabs_flasher.flasher import DeviceSpecificFlasher\n",
     TC + "    from universal_silabs_flasher.flasher import DeviceSpecificFlasher\n"),
])
indent_before(H + "firmware_config_flow.py", "fw_metadata = NabuCasaMetadata.from_json(",
              "from universal_silabs_flasher.firmware import NabuCasaMetadata  # noqa: PLC0415")
indent_before(H + "firmware_config_flow.py", "probed_fw_version = Version(",
              "from universal_silabs_flasher.common import Version  # noqa: PLC0415")

# update.py
edit(H + "update.py", [
    ("from universal_silabs_flasher.flasher import DeviceSpecificFlasher\n",
     TC + "    from universal_silabs_flasher.flasher import DeviceSpecificFlasher\n"),
])

# SkyConnect / Yellow / ZBT-2
for integ, cls in (("homeassistant_sky_connect", "Zbt1Flasher"), ("homeassistant_yellow", "YellowFlasher"),
                   ("homeassistant_connect_zbt2", "Zbt2Flasher")):
    for fn in ("config_flow.py", "update.py"):
        path = f"{integ}/{fn}"
        edit(path, [
            (f"from universal_silabs_flasher.flasher import {cls}\n",
             "from homeassistant.components.homeassistant_hardware.util import LazyFlasherClass\n"),
            (f"    _flasher_cls = {cls}\n", f"    _flasher_cls = LazyFlasherClass({cls!r})\n"),
        ])
        s = open(C + path, encoding="utf-8").read()
        if f"return {cls}" in s:
            indent_before(path, f"return {cls}", f"from universal_silabs_flasher.flasher import {cls}  # noqa: PLC0415")
print("U-6 aplicado (9 arquivos)")
