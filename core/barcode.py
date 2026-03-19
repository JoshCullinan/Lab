import re
import time
from pathlib import Path
from typing import Optional


# ── Lazy imports (opencv / pyzbar are optional at import time) ────────────────

def _import_cv2():
    try:
        import cv2
        return cv2
    except ImportError:
        raise ImportError(
            "opencv-python is required for barcode scanning. "
            "Install it with:  pip install opencv-python"
        )


def _import_pyzbar():
    try:
        from pyzbar import pyzbar
        return pyzbar
    except ImportError:
        raise ImportError(
            "pyzbar is required for barcode scanning. "
            "Install it with:  pip install pyzbar\n"
            "On Windows you also need the zbar DLL:  pip install zbar-windows"
        )


# ── NHLS specimen ID pattern ──────────────────────────────────────────────────
# NHLS barcodes are typically Code-128 and may look like:
#   "W25-123456"  or  "25123456"  or  "W2512345678"
# Adjust this regex once you have seen real barcodes from your facility.
_SPECIMEN_PATTERN = re.compile(r"[A-Z]?\d{2}-?\d{5,10}", re.IGNORECASE)


class BarcodeScanner:

    # ── Webcam scan ───────────────────────────────────────────────────────────

    @staticmethod
    def scan_from_webcam(
        camera_index: int = 0,
        timeout_seconds: int = 30,
    ) -> Optional[str]:
        """
        Open the webcam and continuously scan for a barcode.
        Draws a green rectangle around detected barcodes.
        Returns the extracted specimen ID string, or None on timeout.

        Press 'q' in the preview window to cancel early.
        """
        cv2 = _import_cv2()
        pyzbar = _import_pyzbar()

        cap = cv2.VideoCapture(camera_index)
        if not cap.isOpened():
            raise RuntimeError(
                f"Could not open camera index {camera_index}. "
                "Check that a webcam is connected and not in use by another app."
            )

        deadline = time.time() + timeout_seconds
        specimen_id = None

        try:
            while time.time() < deadline:
                ret, frame = cap.read()
                if not ret:
                    continue

                decoded = pyzbar.decode(frame)
                for barcode in decoded:
                    raw = barcode.data.decode("utf-8", errors="replace")

                    # Draw a green rectangle around the barcode
                    pts = barcode.polygon
                    if len(pts) == 4:
                        import numpy as np
                        pts_array = np.array([[p.x, p.y] for p in pts], dtype=int)
                        cv2.polylines(frame, [pts_array], True, (0, 255, 0), 2)

                    cv2.putText(
                        frame,
                        raw,
                        (barcode.rect.left, barcode.rect.top - 10),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        (0, 255, 0),
                        2,
                    )

                    extracted = BarcodeScanner._extract_specimen_id(raw)
                    if extracted:
                        specimen_id = extracted
                        break

                cv2.imshow("Barcode Scanner — press Q to cancel", frame)

                if specimen_id:
                    break

                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
        finally:
            cap.release()
            cv2.destroyAllWindows()

        return specimen_id

    # ── Image scan ────────────────────────────────────────────────────────────

    @staticmethod
    def scan_from_image(image_path: Path) -> Optional[str]:
        """
        Decode a barcode from a static image file.
        Useful for testing without a webcam.
        """
        cv2 = _import_cv2()
        pyzbar = _import_pyzbar()

        frame = cv2.imread(str(image_path))
        if frame is None:
            raise FileNotFoundError(f"Could not load image: {image_path}")

        decoded = pyzbar.decode(frame)
        for barcode in decoded:
            raw = barcode.data.decode("utf-8", errors="replace")
            extracted = BarcodeScanner._extract_specimen_id(raw)
            if extracted:
                return extracted

        return None

    # ── ID extraction ─────────────────────────────────────────────────────────

    @staticmethod
    def _extract_specimen_id(raw_barcode: str) -> Optional[str]:
        """
        Validate and clean a raw barcode string into an NHLS specimen ID.
        Returns the cleaned ID or None if it doesn't match the expected pattern.

        Update _SPECIMEN_PATTERN in this file once you have examined real barcodes.
        """
        raw = raw_barcode.strip()
        match = _SPECIMEN_PATTERN.search(raw)
        if match:
            return match.group(0).upper()
        # Fallback: if the raw value is entirely digits and a plausible length,
        # treat it as a specimen ID anyway
        if raw.isdigit() and 6 <= len(raw) <= 12:
            return raw
        return None
