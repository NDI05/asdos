"""Offline TrOCR adapter for experimental line-level handwriting transcription."""
from __future__ import annotations

import hashlib
import json
import os
import threading
from io import BytesIO
from pathlib import Path
from typing import Any, Sequence

from PIL import Image

from .config import settings
from .model_adapters import (
    EXPERIMENTAL_TRANSCRIBER_REVIEW_FLAG,
    LINE_SEGMENTATION_FALLBACK_FLAG,
    ModelProvenance,
    ModelUnavailable,
    TranscriptSegment,
    _select_device,
    transcription_flags,
)

MODEL_ID = "asdos/trocr-handwriting-ai-experiment-v1"
PREPROCESSING_VERSION = "region-line-segmentation.v1"
PROMPT_VERSION = "literal-transcription-trocr.v1"
SCHEMA_VERSION = "transcript.v1"
MAX_LINES_PER_REGION = 64
INFERENCE_BATCH_SIZE = 4
MAX_NEW_TOKENS = 128


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest() -> dict[str, Any]:
    manifest_path = settings.trocr_dir / "asdos-trocr-manifest.json"
    if not manifest_path.is_file():
        raise ModelUnavailable("TROCR_UNAVAILABLE", "Manifest checkpoint TrOCR lokal belum tersedia.")
    try:
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelUnavailable("TROCR_MANIFEST_INVALID", "Manifest checkpoint TrOCR tidak valid.") from exc
    if (value.get("manifest_version") != 1 or value.get("model_id") != MODEL_ID
            or value.get("experimental") is not True
            or value.get("training_label_source") != "ai_ocr_unverified"
            or value.get("human_accuracy_measured") is not False
            or value.get("held_out_evaluation") is not False):
        raise ModelUnavailable("TROCR_MANIFEST_INVALID", "Provenance checkpoint TrOCR tidak sesuai.")
    files = value.get("files")
    if not isinstance(files, dict) or "model.safetensors" not in files:
        raise ModelUnavailable("TROCR_MANIFEST_INVALID", "Daftar berkas checkpoint TrOCR tidak lengkap.")
    root = settings.trocr_dir.resolve()
    for name in files:
        if not isinstance(name, str) or not (root / name).resolve().is_relative_to(root):
            raise ModelUnavailable("TROCR_MANIFEST_INVALID", "Manifest TrOCR menunjuk berkas di luar checkpoint.")
    return value


def _line_crops(image: Image.Image) -> tuple[list[Image.Image], bool]:
    """Find horizontal text bands while retaining original pixels in each crop."""
    width, height = image.size
    if width < 24 or height < 12:
        return [image.copy()], True
    try:
        import cv2
        import numpy as np

        gray = np.asarray(image.convert("L"))
        _, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
        rule_width = max(24, min(width, round(width * 0.55)))
        rules = cv2.morphologyEx(
            ink,
            cv2.MORPH_OPEN,
            cv2.getStructuringElement(cv2.MORPH_RECT, (rule_width, 1)),
        )
        cleaned_ink = cv2.subtract(ink, rules)
        projection = np.count_nonzero(cleaned_ink, axis=1)
        minimum_ink = max(2, round(width * 0.0015))
        active = projection >= minimum_ink
        raw: list[tuple[int, int]] = []
        start = None
        for row, on in enumerate(active.tolist() + [False]):
            if on and start is None:
                start = row
            elif not on and start is not None:
                raw.append((start, row))
                start = None
        if not raw:
            return [image.copy()], True

        merge_gap = max(3, round(height * 0.015))
        bands: list[list[int]] = []
        for top, bottom in raw:
            if bands and top - bands[-1][1] <= merge_gap:
                bands[-1][1] = bottom
            else:
                bands.append([top, bottom])

        # Dots and accents can sit above the main glyph band; attach small isolated
        # marks to their nearest text band instead of treating them as another line.
        small_limit = max(3, round(height * 0.018))
        index = 0
        while index < len(bands) and len(bands) > 1:
            top, bottom = bands[index]
            if bottom - top < small_limit:
                if index == 0:
                    bands[1][0] = top
                elif index == len(bands) - 1:
                    bands[index - 1][1] = bottom
                else:
                    above_gap = top - bands[index - 1][1]
                    below_gap = bands[index + 1][0] - bottom
                    if above_gap <= below_gap:
                        bands[index - 1][1] = bottom
                    else:
                        bands[index + 1][0] = top
                bands.pop(index)
                index = max(0, index - 1)
                continue
            index += 1

        if len(bands) > MAX_LINES_PER_REGION:
            return [image.copy()], True
        if len(bands) <= 1:
            return [image.copy()], False

        heights = sorted(bottom - top for top, bottom in bands)
        median_height = heights[len(heights) // 2]
        padding = max(2, round(median_height * 0.12))
        crops = []
        for top, bottom in bands:
            band_top, band_bottom = max(0, top - padding), min(height, bottom + padding)
            columns = np.count_nonzero(cleaned_ink[band_top:band_bottom], axis=0)
            occupied = np.flatnonzero(columns >= max(1, round((band_bottom - band_top) * 0.015)))
            if len(occupied):
                horizontal_padding = max(3, round((occupied[-1] - occupied[0] + 1) * 0.025))
                left = max(0, int(occupied[0]) - horizontal_padding)
                right = min(width, int(occupied[-1]) + 1 + horizontal_padding)
            else:
                left, right = 0, width
            crops.append(image.crop((left, band_top, right, band_bottom)))
        return crops, False
    except (ImportError, ValueError):
        # Preserve service availability and original pixels; the result remains
        # explicitly flagged so a lecturer checks whether the region was one line.
        return [image.copy()], True


class TrOCRAdapter:
    model_id = MODEL_ID
    prompt_version = PROMPT_VERSION
    schema_version = SCHEMA_VERSION
    preprocessing_version = PREPROCESSING_VERSION

    def __init__(self) -> None:
        self._load_lock = threading.Lock()
        self._generation_lock = threading.Lock()
        self._processor = None
        self._model = None
        self._device = None
        self._revision = ""
        self._weights_sha256 = ""
        self._runtime = "transformers/unavailable"

    @property
    def revision(self) -> str:
        if self._revision:
            return self._revision
        try:
            return str(_manifest().get("revision", "unknown"))
        except ModelUnavailable:
            return "unavailable"

    @property
    def runtime(self) -> str:
        if self._model is not None:
            return self._runtime
        try:
            import transformers
            return f"transformers/{transformers.__version__}"
        except ImportError:
            return "transformers/unavailable"

    def status(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "backend": "trocr",
            "available": False,
            "reason": "checkpoint_not_provisioned",
            "model_id": MODEL_ID,
            "revision": "unavailable",
            "runtime": self.runtime,
            "loaded": self._model is not None,
            "inference_verified": False,
            "experimental": True,
            "review_required": True,
            "human_accuracy_measured": False,
            "held_out_evaluation": False,
            "device": str(self._device) if self._device is not None else None,
        }
        try:
            manifest = _manifest()
            root = settings.trocr_dir.resolve()
            for name in manifest["files"]:
                path = (root / name).resolve()
                if not path.is_file() or path.stat().st_size == 0:
                    raise ModelUnavailable("TROCR_CHECKPOINT_INCOMPLETE", "Berkas checkpoint TrOCR belum lengkap.")
            device_name, _, _ = _select_device()
            if self.runtime == "transformers/unavailable":
                raise ModelUnavailable("MODEL_RUNTIME_MISSING", "Paket Transformers belum tersedia.")
            result.update({
                "available": True,
                "reason": "loaded" if self._model is not None else "ready_to_load",
                "revision": str(manifest["revision"]),
                "device": str(self._device) if self._device is not None else device_name,
                "inference_verified": getattr(self, "_inference_verified", False),
            })
        except ModelUnavailable as exc:
            result["reason"] = exc.code.lower()
        except (OSError, TypeError, ValueError):
            result["reason"] = "checkpoint_manifest_invalid"
        return result

    def fingerprint(self) -> dict[str, str]:
        try:
            manifest = _manifest()
            return {"backend": "trocr", "model_id": MODEL_ID, "revision": str(manifest["revision"]),
                    "checkpoint_sha256": str(manifest["weights_sha256"])}
        except ModelUnavailable:
            return {"backend": "trocr", "model_id": MODEL_ID, "revision": "unavailable",
                    "checkpoint_sha256": "unavailable"}

    def _load(self) -> None:
        if self._model is not None:
            return
        with self._load_lock:
            if self._model is not None:
                return
            manifest = _manifest()
            root = settings.trocr_dir.resolve()
            try:
                for name, expected in manifest["files"].items():
                    path = (root / name).resolve()
                    if not path.is_relative_to(root) or not path.is_file() or _sha256(path) != expected:
                        raise ModelUnavailable("TROCR_CHECKPOINT_HASH_MISMATCH", "Hash checkpoint TrOCR tidak cocok.")
                if _sha256(root / "model.safetensors") != manifest.get("weights_sha256"):
                    raise ModelUnavailable("TROCR_CHECKPOINT_HASH_MISMATCH", "Hash bobot TrOCR tidak cocok.")
                _, device, _ = _select_device()
                os.environ["HF_HUB_OFFLINE"] = "1"
                os.environ["TRANSFORMERS_OFFLINE"] = "1"
                import torch
                import transformers

                processor_class = getattr(transformers, "TrOCRProcessor", None)
                model_class = getattr(transformers, "VisionEncoderDecoderModel", None)
                if processor_class is None or model_class is None:
                    raise ModelUnavailable("TROCR_RUNTIME_INCOMPATIBLE", "Runtime Transformers tidak menyediakan TrOCR.")
                processor = processor_class.from_pretrained(
                    str(root), local_files_only=True, trust_remote_code=False
                )
                model = model_class.from_pretrained(
                    str(root), local_files_only=True, trust_remote_code=False
                ).to(device)
                model.config.decoder_start_token_id = processor.tokenizer.cls_token_id
                model.config.pad_token_id = processor.tokenizer.pad_token_id
                model.generation_config.decoder_start_token_id = processor.tokenizer.cls_token_id
                model.generation_config.eos_token_id = processor.tokenizer.eos_token_id
                model.generation_config.pad_token_id = processor.tokenizer.pad_token_id
                model.eval()
            except ModelUnavailable:
                raise
            except ImportError as exc:
                raise ModelUnavailable("MODEL_RUNTIME_MISSING", "Pasang extra model lokal sebelum inferensi TrOCR.") from exc
            except Exception as exc:
                raise ModelUnavailable("TROCR_LOAD_FAILED", f"Checkpoint TrOCR gagal dimuat ({type(exc).__name__}).") from exc
            self._processor, self._model, self._device = processor, model, device
            self._revision = str(manifest["revision"])
            self._weights_sha256 = str(manifest["weights_sha256"])
            self._runtime = f"transformers/{transformers.__version__}; torch/{torch.__version__}"
            self._inference_verified = False

    def transcribe(self, region_images: Sequence[bytes], language: str) -> tuple[list[TranscriptSegment], ModelProvenance]:
        if language not in {"id", "en"}:
            raise ModelUnavailable("LANGUAGE_UNSUPPORTED", "MVP hanya mendukung Bahasa Indonesia atau Inggris.")
        if not region_images:
            raise ValueError("transcriber requires at least one region image")
        self._load()
        import torch

        segments = []
        for payload in region_images:
            try:
                with Image.open(BytesIO(payload)) as opened:
                    region = opened.convert("RGB")
            except Exception as exc:
                raise ModelUnavailable("TRANSCRIPTION_IMAGE_INVALID", "Crop jawaban tidak dapat dibaca.") from exc
            lines, used_fallback = _line_crops(region)
            region.close()
            if not lines or len(lines) > MAX_LINES_PER_REGION:
                for line in lines:
                    line.close()
                raise ModelUnavailable("TROCR_LINE_SEGMENTATION_FAILED", "Jumlah baris pada area tidak dapat diproses.")
            decoded: list[str] = []
            generation_limited: list[bool] = []
            try:
                with self._generation_lock, torch.inference_mode():
                    for start in range(0, len(lines), INFERENCE_BATCH_SIZE):
                        batch = lines[start:start + INFERENCE_BATCH_SIZE]
                        pixels = self._processor(images=batch, return_tensors="pt").pixel_values.to(self._device)
                        generated = self._model.generate(
                            pixels, max_new_tokens=MAX_NEW_TOKENS, num_beams=1, do_sample=False
                        )
                        eos_token_id = self._processor.tokenizer.eos_token_id
                        for row in generated:
                            token_ids = row.tolist()
                            generation_limited.append(
                                len(token_ids) - 1 >= MAX_NEW_TOKENS and eos_token_id not in token_ids[1:]
                            )
                        decoded.extend(self._processor.batch_decode(
                            generated, skip_special_tokens=True, clean_up_tokenization_spaces=False
                        ))
            except Exception as exc:
                raise ModelUnavailable("MODEL_INFERENCE_FAILED", f"Inferensi TrOCR gagal ({type(exc).__name__}).") from exc
            finally:
                for line in lines:
                    line.close()

            text = "\n".join(value.strip() for value in decoded).strip()
            flags = list(transcription_flags(text))
            flags.append(EXPERIMENTAL_TRANSCRIBER_REVIEW_FLAG)
            if used_fallback:
                flags.append(LINE_SEGMENTATION_FALLBACK_FLAG)
            if any(generation_limited):
                flags.append("transcriber_generation_limit")
            segments.append(TranscriptSegment(text=text, flags=tuple(dict.fromkeys(flags))))
        self._inference_verified = True
        provenance = ModelProvenance(
            model_id=MODEL_ID,
            revision=self._revision,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            device=str(self._device),
            runtime=self._runtime,
            checkpoint_sha256=self._weights_sha256,
        )
        return segments, provenance


trocr_adapter = TrOCRAdapter()
