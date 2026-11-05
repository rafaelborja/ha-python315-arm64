"""HA Lite: camera TurboJPEG created in the executor before first use (PR head ebc35e6a44a68bb51b31c25d79da0f900a1bf46b,
branch lazy-import-stream-numpy-av of rafaelborja/homeassistant-core, PR home-assistant/core#183145).

camera/img_util.py is replaced by that commit's file before this runs (sha256-pinned in lite/sources.txt); this adds
the two call sites the same commit changes: camera/__init__.py and nest/__init__.py await async_ensure_turbojpeg()
before the first scaled image. Usage: patch_camera_3c74c7b1.py <.../homeassistant/components>. Fails if an anchor
is missing."""
import sys

C = sys.argv[1]


def patch(path, old, new):
    s = open(path, encoding="utf-8").read()
    if s.count(old) != 1:
        sys.exit(f"camera 3c74c7b1: anchor not found (or repeated) in {path}: {old[:60]!r}")
    open(path, "w", encoding="utf-8").write(s.replace(old, new))


patch(f"{C}/camera/__init__.py",
      "from .img_util import TurboJPEGSingleton, scale_jpeg_camera_image\n",
      "from .img_util import (\n    TurboJPEGSingleton,\n    async_ensure_turbojpeg,\n    scale_jpeg_camera_image,\n)\n")
patch(f"{C}/camera/__init__.py",
      "                    assert height is not None\n                    return Image(\n",
      "                    assert height is not None\n                    await async_ensure_turbojpeg(camera.hass)\n"
      "                    return Image(\n")
patch(f"{C}/nest/__init__.py",
      "            contents = img_util.scale_jpeg_camera_image(\n",
      "            await img_util.async_ensure_turbojpeg(self.hass)\n            contents = img_util.scale_jpeg_camera_image(\n")
print("camera/nest 3c74c7b1 applied")
