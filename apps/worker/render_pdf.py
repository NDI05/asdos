"""Short-lived PDFium child process. It has no model credentials or API secrets."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

RENDER_POLICY_VERSION = "fit-pixel-budget.v2"


def bounded_render_dpi(width_pt: float, height_pt: float, dpi: int, max_pixels: int) -> int:
    """Fit a page inside the raster budget before PDFium allocates its bitmap."""
    if (not all(math.isfinite(value) and value > 0 for value in (width_pt, height_pt))
            or dpi < 1 or max_pixels < 1):
        raise ValueError("PDF_PIXEL_LIMIT")
    width_px, height_px = math.ceil(width_pt * dpi / 72), math.ceil(height_pt * dpi / 72)
    if width_px * height_px <= max_pixels:
        return dpi
    effective = min(dpi, math.floor(dpi * math.sqrt(max_pixels / (width_px * height_px))))
    while effective >= 1:
        if math.ceil(width_pt * effective / 72) * math.ceil(height_pt * effective / 72) <= max_pixels:
            return effective
        effective -= 1
    raise ValueError("PDF_PIXEL_LIMIT")


def render(input_pdf: Path, output_dir: Path, dpi: int, max_pages: int, max_pixels: int, extract_text: bool) -> dict:
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise RuntimeError("PDFIUM_DEPENDENCY_MISSING") from exc
    if input_pdf.stat().st_size > 50 * 1024 * 1024:
        raise ValueError("PDF_TOO_LARGE")
    with input_pdf.open("rb") as stream:
        if stream.read(5) != b"%PDF-":
            raise ValueError("NOT_A_PDF")
    document = pdfium.PdfDocument(str(input_pdf))
    pages: list[dict] = []
    try:
        count = len(document)
        if count < 1 or count > max_pages:
            raise ValueError("PDF_PAGE_LIMIT")
        for page_index in range(count):
            page = document[page_index]
            try:
                width_pt, height_pt = page.get_size()
                effective_dpi = bounded_render_dpi(width_pt, height_pt, dpi, max_pixels)
                bitmap = page.render(scale=effective_dpi / 72, rotation=0)
                try:
                    if bitmap.width * bitmap.height > max_pixels:
                        raise ValueError("PDF_PIXEL_LIMIT")
                    image = bitmap.to_pil().convert("RGB")
                    output = output_dir / f"page-{page_index:04d}.png"
                    image.save(output, format="PNG", optimize=False)
                    data = output.read_bytes()
                    page_text = ""
                    if extract_text:
                        textpage = page.get_textpage()
                        try:
                            page_text = textpage.get_text_range()
                        finally:
                            textpage.close()
                    pages.append({
                        "page_index": page_index,
                        "dpi": effective_dpi,
                        "render_scale": effective_dpi / 72,
                        "width_px": image.width,
                        "height_px": image.height,
                        "pdf_width_points": width_pt,
                        "pdf_height_points": height_pt,
                        "original_rotation": int(page.get_rotation()) if hasattr(page, "get_rotation") else 0,
                        "file": output.name,
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "text": page_text,
                        "quality_metrics": _quality_metrics(data),
                        "quality_flags": ["review_threshold_not_calibrated"] + (
                            ["render_resolution_reduced"] if effective_dpi < dpi else []),
                    })
                finally:
                    bitmap.close()
            finally:
                page.close()
    finally:
        document.close()
    manifest = {"schema_version": "render-manifest.v1", "render_policy": RENDER_POLICY_VERSION,
                "dpi": dpi, "max_pixels": max_pixels, "page_count": len(pages), "pages": pages}
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return manifest


def _quality_metrics(data: bytes) -> dict:
    try:
        import cv2
        import numpy as np
        import io
        from PIL import Image

        gray = np.asarray(Image.open(io.BytesIO(data)).convert("L"))
        return {
            "laplacian_variance": round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 3),
            "gray_stddev": round(float(gray.std()), 3),
        }
    except Exception:
        return {"status": "metrics_unavailable"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dpi", type=int, default=250)
    parser.add_argument("--max-pages", type=int, default=100)
    parser.add_argument("--max-pixels", type=int, default=25_000_000)
    parser.add_argument("--extract-text", action="store_true")
    args = parser.parse_args()
    try:
        args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
        manifest = render(args.input, args.output, args.dpi, args.max_pages, args.max_pixels, args.extract_text)
        sys.stdout.write(json.dumps(manifest, ensure_ascii=False))
        return 0
    except Exception as exc:
        code = str(exc) if str(exc) in {"PDFIUM_DEPENDENCY_MISSING", "PDF_TOO_LARGE", "NOT_A_PDF", "PDF_PAGE_LIMIT", "PDF_PIXEL_LIMIT"} else "PDF_RENDER_FAILED"
        sys.stderr.write(json.dumps({"code": code}, ensure_ascii=False) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
