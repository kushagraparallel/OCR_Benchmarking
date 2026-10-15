"""One-time, online provisioning of local model weights for optional OCR engines.

The application never downloads OCR models at request time (see
``app/core/ocr/README.md``): EasyOCR and PaddleOCR adapters require
pre-provisioned local directories, and the docTR adapter requires pretrained
weights to already exist in its cache directory. This script performs that
one-time download using each engine's own library, then prints the exact
``backend/.env`` settings that point the application at the provisioned
directories.

Run from ``backend/`` with the optional-engine dependencies installed:

    python -m scripts.provision_ocr_models --engines easyocr,paddleocr,doctr

Re-running is safe: every engine here skips downloading a model file that is
already present in the target directory.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

DEFAULT_MODEL_ROOT = Path(__file__).resolve().parent.parent / "var" / "ocr-models"
SUPPORTED_ENGINES = ("easyocr", "paddleocr", "doctr")


def provision_easyocr(model_root: Path, languages: list[str]) -> Path:
    """Download EasyOCR's detection/recognition weights into a local directory."""
    import easyocr

    target = model_root / "easyocr"
    target.mkdir(parents=True, exist_ok=True)
    print(f"[easyocr] downloading weights for {languages} into {target} ...")
    easyocr.Reader(languages, model_storage_directory=str(target), download_enabled=True, gpu=False)
    print("[easyocr] done.")
    return target


def provision_paddleocr(model_root: Path, language: str) -> tuple[Path, Path, Path]:
    """Download PaddleOCR's detection, recognition, and classification models."""
    from paddleocr import PaddleOCR

    det_dir = model_root / "paddleocr" / "det"
    rec_dir = model_root / "paddleocr" / "rec"
    cls_dir = model_root / "paddleocr" / "cls"
    for directory in (det_dir, rec_dir, cls_dir):
        directory.mkdir(parents=True, exist_ok=True)

    print(f"[paddleocr] downloading detection/recognition/classification models for '{language}' ...")
    PaddleOCR(
        lang=language,
        use_angle_cls=True,
        use_gpu=False,
        show_log=False,
        det_model_dir=str(det_dir),
        rec_model_dir=str(rec_dir),
        cls_model_dir=str(cls_dir),
    )
    print(f"[paddleocr] done: {det_dir}, {rec_dir}, {cls_dir}")
    return det_dir, rec_dir, cls_dir


def provision_doctr(model_root: Path, det_arch: str, reco_arch: str) -> Path:
    """Download docTR's pretrained detection/recognition weights into a cache directory."""
    target = model_root / "doctr"
    target.mkdir(parents=True, exist_ok=True)
    os.environ["DOCTR_CACHE_DIR"] = str(target)

    from doctr.models import ocr_predictor

    print(f"[doctr] downloading '{det_arch}' + '{reco_arch}' weights into {target} ...")
    ocr_predictor(det_arch=det_arch, reco_arch=reco_arch, pretrained=True)
    print("[doctr] done.")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--engines",
        default=",".join(SUPPORTED_ENGINES),
        help=f"Comma-separated subset of {SUPPORTED_ENGINES} to provision.",
    )
    parser.add_argument(
        "--model-root",
        default=str(DEFAULT_MODEL_ROOT),
        help=f"Directory to store downloaded models under (default: {DEFAULT_MODEL_ROOT}).",
    )
    parser.add_argument("--languages", default="en", help="Comma-separated EasyOCR language codes.")
    parser.add_argument("--paddle-lang", default="en", help="PaddleOCR language code.")
    parser.add_argument("--doctr-det-arch", default="db_resnet50", help="docTR detection architecture.")
    parser.add_argument("--doctr-reco-arch", default="crnn_vgg16_bn", help="docTR recognition architecture.")
    args = parser.parse_args()

    requested = [name.strip().casefold() for name in args.engines.split(",") if name.strip()]
    unknown = sorted(set(requested) - set(SUPPORTED_ENGINES))
    if unknown:
        parser.error(f"Unknown engine(s): {', '.join(unknown)}. Supported: {SUPPORTED_ENGINES}.")

    model_root = Path(args.model_root)
    settings_lines: list[str] = []

    if "easyocr" in requested:
        target = provision_easyocr(model_root, args.languages.split(","))
        settings_lines.append(f"OCR_EASYOCR_MODEL_DIRECTORY={target}")

    if "paddleocr" in requested:
        det_dir, rec_dir, cls_dir = provision_paddleocr(model_root, args.paddle_lang)
        settings_lines.append(f"OCR_PADDLE_DETECTION_MODEL_DIRECTORY={det_dir}")
        settings_lines.append(f"OCR_PADDLE_RECOGNITION_MODEL_DIRECTORY={rec_dir}")
        settings_lines.append(f"OCR_PADDLE_CLASSIFICATION_MODEL_DIRECTORY={cls_dir}")

    if "doctr" in requested:
        target = provision_doctr(model_root, args.doctr_det_arch, args.doctr_reco_arch)
        settings_lines.append(f"OCR_DOCTR_CACHE_DIRECTORY={target}")
        settings_lines.append(f"OCR_DOCTR_DET_ARCH={args.doctr_det_arch}")
        settings_lines.append(f"OCR_DOCTR_RECO_ARCH={args.doctr_reco_arch}")

    print("\nAdd the following to backend/.env, plus the engine names in OCR_ENABLED_ENGINES:\n")
    for line in settings_lines:
        print(line)


if __name__ == "__main__":
    main()
