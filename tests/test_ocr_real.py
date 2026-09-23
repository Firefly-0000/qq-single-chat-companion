from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from qq_autoreply.vision.ocr import RapidOcrEngine


def test_rapidocr_reads_rendered_text() -> None:
    image = Image.new("RGB", (640, 160), "white")
    draw = ImageDraw.Draw(image)
    draw.text((40, 40), "HELLO 123", fill="black", font_size=64)
    bgr = np.asarray(image)[:, :, ::-1]

    lines = RapidOcrEngine().recognize(bgr)
    text = " ".join(line.text for line in lines)

    assert "HELLO 123" in text
