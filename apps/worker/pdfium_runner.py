from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from apps.api.asdos_api.config import settings


class PdfPipelineError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def render_in_isolated_process(pdf_path: Path, *, extract_text: bool = False) -> tuple[dict, Path]:
    """Run PDFium in a separate, time-bounded process with a minimal environment."""
    workdir = Path(tempfile.mkdtemp(prefix="asdos-render-", dir=settings.artifact_dir))
    output = workdir / "rendered"
    environment = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONPATH": str(Path.cwd()),
        "PYTHONNOUSERSITE": "1",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
    }
    command = [
        sys.executable,
        "-m",
        "apps.worker.render_pdf",
        "--input",
        str(pdf_path),
        "--output",
        str(output),
        "--dpi",
        str(settings.render_dpi),
        "--max-pages",
        str(settings.max_pdf_pages),
        "--max-pixels",
        str(settings.max_render_pixels),
    ]
    if extract_text:
        command.append("--extract-text")
    try:
        completed = subprocess.run(command, check=True, capture_output=True, text=True, timeout=180, env=environment)
        manifest = json.loads(completed.stdout)
    except subprocess.TimeoutExpired as exc:
        shutil.rmtree(workdir, ignore_errors=True)
        raise PdfPipelineError("PDF_RENDER_TIMEOUT") from exc
    except subprocess.CalledProcessError as exc:
        shutil.rmtree(workdir, ignore_errors=True)
        try:
            code = json.loads(exc.stderr.splitlines()[-1]).get("code", "PDF_RENDER_FAILED")
        except Exception:
            code = "PDF_RENDER_FAILED"
        raise PdfPipelineError(code) from exc
    except (OSError, json.JSONDecodeError) as exc:
        shutil.rmtree(workdir, ignore_errors=True)
        raise PdfPipelineError("PDF_RENDER_FAILED") from exc
    except Exception:
        shutil.rmtree(workdir, ignore_errors=True)
        raise
    return manifest, output
