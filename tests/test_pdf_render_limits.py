"""Synthetic regressions for bounded rasterization; no student scans in Git."""
import math
from pathlib import Path

import pypdfium2 as pdfium
import pytest

from apps.worker.render_pdf import RENDER_POLICY_VERSION, bounded_render_dpi, render


def test_oversized_scan_fits_without_increasing_pixel_budget():
    # Dimensions reported by the failing scan, with no document content copied.
    assert math.ceil(1824 * 250 / 72) * math.ceil(2805 * 250 / 72) > 25_000_000
    effective = bounded_render_dpi(1824, 2805, 250, 25_000_000)
    assert effective == 159
    assert math.ceil(1824 * effective / 72) * math.ceil(2805 * effective / 72) <= 25_000_000


def test_normal_page_keeps_requested_resolution():
    assert bounded_render_dpi(595, 842, 250, 25_000_000) == 250


@pytest.mark.parametrize("width,height,dpi,limit", [
    (float("nan"), 842, 250, 25_000_000), (595, float("inf"), 250, 25_000_000),
    (0, 842, 250, 25_000_000), (595, 842, 0, 25_000_000), (595, 842, 250, 0),
    (1_000_000, 1_000_000, 250, 25_000_000),
])
def test_invalid_or_unrenderable_dimensions_still_fail(width, height, dpi, limit):
    with pytest.raises(ValueError, match="PDF_PIXEL_LIMIT"):
        bounded_render_dpi(width, height, dpi, limit)


def test_pdfium_renders_all_pages_with_per_page_resolution(tmp_path: Path):
    source = tmp_path / "synthetic.pdf"
    document = pdfium.PdfDocument.new()
    for width, height in [(720, 405), (1824, 2805)]:
        page = document.new_page(width, height)
        page.close()
    document.save(str(source))
    document.close()
    output = tmp_path / "rendered"
    output.mkdir()
    manifest = render(source, output, 72, 10, 500_000, False)
    assert manifest["render_policy"] == RENDER_POLICY_VERSION
    assert manifest["page_count"] == 2
    assert manifest["pages"][0]["dpi"] == 72
    assert manifest["pages"][1]["dpi"] < 72
    for page in manifest["pages"]:
        assert 0 < page["width_px"] * page["height_px"] <= 500_000
        assert (output / page["file"]).is_file()
        # Raster coordinates retain a reversible relation to PDF points.
        x_pdf, y_pdf = 0.37 * page["pdf_width_points"], 0.61 * page["pdf_height_points"]
        sx = page["width_px"] / page["pdf_width_points"]
        sy = page["height_px"] / page["pdf_height_points"]
        assert (x_pdf * sx) / sx == pytest.approx(x_pdf)
        assert (y_pdf * sy) / sy == pytest.approx(y_pdf)
    assert "render_resolution_reduced" in manifest["pages"][1]["quality_flags"]
