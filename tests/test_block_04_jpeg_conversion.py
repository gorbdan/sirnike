# -*- coding: utf-8 -*-
"""Блок 4: JPEG-конверсия кадров."""
import base64
import io

from PIL import Image

from test_helpers import S, png_data_url


def test_block_04_jpeg_conversion():
    rgba_url = png_data_url("RGBA")
    out = S._data_url_to_jpeg_rgb(rgba_url)
    assert out.startswith("data:image/jpeg;base64,"), "4.1 RGBA PNG -> data:image/jpeg"
    raw = base64.b64decode(out.split(",", 1)[1])
    img = Image.open(io.BytesIO(raw))
    assert img.mode == "RGB" and img.format == "JPEG", "4.2 результат RGB без альфы"
    assert S._data_url_to_jpeg_rgb("data:image/png;base64,@@@@") == "data:image/png;base64,@@@@", (
        "4.3 мусор возвращается как есть"
    )
    assert S._data_url_to_jpeg_rgb("abc") == "abc", "4.4 не-data URL не трогается"
