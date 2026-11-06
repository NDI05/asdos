from __future__ import annotations

import os
from pathlib import Path
from typing import Any


class BaselineUnavailable(RuntimeError):
    pass


class PPV5LatinBaseline:
    """Optional PP-OCRv5 baseline for image regions, never used as silent fallback."""

    detector_name = "PP-OCRv5_mobile_det"
    recognizer_name = "latin_PP-OCRv5_mobile_rec"
    language = "id"

    def __init__(self) -> None:
        detection_dir = os.getenv("ASDOS_PPOCR_DETECTION_DIR")
        recognition_dir = os.getenv("ASDOS_PPOCR_RECOGNITION_DIR")
        if not detection_dir or not recognition_dir:
            raise BaselineUnavailable("Set ASDOS_PPOCR_DETECTION_DIR and ASDOS_PPOCR_RECOGNITION_DIR to verified local assets.")
        if not Path(detection_dir, "inference.pdmodel").exists() and not Path(detection_dir, "inference.json").exists():
            raise BaselineUnavailable("Local PP-OCRv5 detector files are missing.")
        if not Path(recognition_dir, "inference.pdmodel").exists() and not Path(recognition_dir, "inference.json").exists():
            raise BaselineUnavailable("Local Latin PP-OCRv5 recognizer files are missing.")
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise BaselineUnavailable("Install the optional vision-baseline dependency group first.") from exc
        os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
        self._pipeline = PaddleOCR(
            lang=self.language,
            text_detection_model_name=self.detector_name,
            text_recognition_model_name=self.recognizer_name,
            text_detection_model_dir=detection_dir,
            text_recognition_model_dir=recognition_dir,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )

    def transcribe(self, image_path: Path) -> list[dict[str, Any]]:
        result = self._pipeline.predict(input=str(image_path))
        rows: list[dict[str, Any]] = []
        for output in result:
            payload = output.json if hasattr(output, "json") else output
            if isinstance(payload, dict):
                payload = payload.get("res", payload)
            texts = payload.get("rec_texts", []) if isinstance(payload, dict) else []
            for index, text in enumerate(texts):
                rows.append({"order": index + 1, "text": str(text), "confidence": None})
        return rows
