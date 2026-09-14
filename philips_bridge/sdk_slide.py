"""Python 3.7 SDK reader: tissue only, no label/macro pixels or raw metadata."""
import os
import base64
import shutil
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
import pixelengine
import softwarerenderbackend
import softwarerendercontext


class SDKSlide:
    def __init__(self, filename, view="display"):
        if view != "display":
            raise ValueError("Only SDK display RGB view is supported")
        self._alias = None
        self.pe = pixelengine.PixelEngine(softwarerenderbackend.SoftwareRenderBackend(),
                                         softwarerendercontext.SoftwareRenderContext())
        path = Path(filename).resolve()
        # This SDK takes narrow strings. A Unicode cwd is safe; the SDK sees only
        # an ASCII filename. The bridge has its own process, so chdir is isolated.
        if not path.name.isascii():
            self._alias = tempfile.TemporaryDirectory(prefix="wsi_sdk_", dir=os.environ.get("WSI_PHILIPS_SCRATCH"))
            alias = Path(self._alias.name) / "input.i2syntax"
            try:
                os.link(str(path), str(alias))
            except OSError:
                shutil.copyfile(str(path), str(alias))
            path = alias
        os.chdir(str(path.parent))
        self.path = path
        try:
            self.pe["in"].open(path.name, "ficom")
            self.image = self.pe["in"]["WSI"]
            self.view_wsi = self.image.display_view
            self.view_wsi.load_default_parameters()
            v = self.view_wsi
            self.xind, self.yind = v.dimension_names.index("x"), v.dimension_names.index("y")
            if v.bits_allocated != 8:
                raise ValueError("Only 8-bit SDK display RGB is supported")
            self.level_dimensions, self.level_downsamples, self.origins = [], [], []
            # SDK num_derived_levels excludes the base level.
            for level in range(v.num_derived_levels + 1):
                ranges = v.dimension_ranges(level)
                x, y = ranges[self.xind], ranges[self.yind]
                if x[1] != y[1] or x[1] <= 0:
                    raise ValueError("Unsupported Philips spatial grid")
                self.level_dimensions.append((int((x[2]-x[0])//x[1]+1), int((y[2]-y[0])//y[1]+1)))
                self.level_downsamples.append(int(x[1]))
                self.origins.append((int(x[0]), int(y[0])))
            self.dimensions = self.level_dimensions[0]
            self.level_count = len(self.level_dimensions)
            self.properties = {"openslide.vendor": "philips"}
            for axis, index in (("x", self.xind), ("y", self.yind)):
                # SDK scale is in the stated dimension unit; never guess units.
                unit = str(v.dimension_units[index]).lower()
                factor = {"um": 1, "micrometer": 1, "micrometers": 1, "mm": 1000}.get(unit)
                if factor is not None:
                    self.properties["openslide.mpp-" + axis] = str(float(v.scale[index]) * factor)
            # The SDK exposes no objective-power here. OpenPhi's hardcoded 40
            # must not be treated as measured metadata.
            self.associated_images = {}
            for index in range(self.pe["in"].num_images):
                kind = self.pe["in"][index].image_type
                if kind != "WSI":
                    self.associated_images[{"LABELIMAGE": "label", "MACROIMAGE": "macro"}.get(kind, "other")] = None
            profile = self.image.icc_profile
            self.icc = (base64.b64decode(profile, validate=True) if isinstance(profile, str)
                        else bytes(profile)) if profile else None
            if self.icc and (len(self.icc) < 128 or self.icc[36:40] != b"acsp"):
                raise ValueError("Invalid Philips ICC profile")
        except Exception:
            self.close()
            raise

    def read_region(self, location, level, size):
        step = self.level_downsamples[level]
        ox, oy = self.origins[level]
        x, y = int(location[0] // step) * step + ox, int(location[1] // step) * step + oy
        width, height = map(int, size)
        if not (0 < width <= 4096 and 0 < height <= 4096):
            raise ValueError("Philips region exceeds bounded buffer")
        regions = self.view_wsi.request_regions(
            region=[[x, x+(width-1)*step, y, y+(height-1)*step, level]],
            data_envelopes=self.view_wsi.data_envelopes(level), enable_async_rendering=False,
            background_color=[255, 255, 255], buffer_type=pixelengine.PixelEngine.BufferType.RGB)
        pixels = np.empty(width * height * 3, dtype=np.uint8)
        regions[0].get(pixels)
        image = Image.frombytes("RGB", (width, height), pixels.tobytes()).convert("RGBA")
        if self.icc:
            image.info["icc_profile"] = self.icc
        return image

    def close(self):
        try:
            self.pe["in"].close()
        finally:
            if self._alias is not None:
                os.chdir(tempfile.gettempdir())
                self._alias.cleanup()
                self._alias = None
