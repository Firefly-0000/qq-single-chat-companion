from __future__ import annotations

from typing import Any

import numpy as np

from ..domain import OcrLine


class OcrError(RuntimeError):
    pass


class RapidOcrEngine:
    def __init__(self) -> None:
        self._engine: Any | None = None

    def _get_engine(self) -> Any:
        if self._engine is None:
            try:
                from rapidocr import RapidOCR
            except ImportError as exc:
                raise OcrError("RapidOCR is not installed") from exc
            self._engine = RapidOCR()
        return self._engine

    def recognize(self, image: np.ndarray) -> list[OcrLine]:
        try:
            result = self._get_engine()(image)
        except Exception as exc:
            raise OcrError(f"OCR failed: {exc}") from exc
        return self._normalize_result(result)

    @staticmethod
    def _normalize_result(result: Any) -> list[OcrLine]:
        boxes: Any = getattr(result, "boxes", None)
        texts: Any = getattr(result, "txts", None)
        scores: Any = getattr(result, "scores", None)

        if boxes is None and isinstance(result, tuple):
            legacy = result[0]
            boxes = [item[0] for item in legacy]
            texts = [item[1] for item in legacy]
            scores = [item[2] for item in legacy]

        if boxes is None or texts is None:
            return []

        lines: list[OcrLine] = []
        for index, text_value in enumerate(texts):
            text = str(text_value).strip()
            if not text:
                continue
            box = boxes[index]
            points = np.asarray(box).reshape(-1, 2)
            left = int(np.min(points[:, 0]))
            top = int(np.min(points[:, 1]))
            right = int(np.max(points[:, 0]))
            bottom = int(np.max(points[:, 1]))
            confidence = float(scores[index]) if scores is not None else 0.0
            lines.append(
                OcrLine(
                    text=text,
                    confidence=confidence,
                    left=left,
                    top=top,
                    right=right,
                    bottom=bottom,
                )
            )
        return lines
