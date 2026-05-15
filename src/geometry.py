from typing import Dict, Tuple

import cv2
import numpy as np


def _rotation_score(image_bgr: np.ndarray) -> float:
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    gx = cv2.Sobel(blur, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(blur, cv2.CV_32F, 0, 1, ksize=3)
    # Upright shipping labels usually contain strong vertical + horizontal strokes.
    return float(np.mean(np.abs(gx)) + np.mean(np.abs(gy)))


def correct_orientation(image_bgr: np.ndarray) -> Tuple[np.ndarray, int]:
    rotations = {
        0: image_bgr,
        90: cv2.rotate(image_bgr, cv2.ROTATE_90_CLOCKWISE),
        180: cv2.rotate(image_bgr, cv2.ROTATE_180),
        270: cv2.rotate(image_bgr, cv2.ROTATE_90_COUNTERCLOCKWISE),
    }
    best_angle, best_image, best_score = 0, image_bgr, -1.0
    for angle, rotated in rotations.items():
        score = _rotation_score(rotated)
        if score > best_score:
            best_angle, best_image, best_score = angle, rotated, score
    return best_image, best_angle


def rectify_perspective(image_bgr: np.ndarray) -> Tuple[np.ndarray, bool]:
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 60, 160)
    kernel = np.ones((5, 5), np.uint8)
    edges = cv2.dilate(edges, kernel, iterations=1)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return image_bgr, False

    h, w = gray.shape
    image_area = h * w
    best_quad = None
    best_area = 0.0
    for cnt in contours:
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
        if len(approx) != 4:
            continue
        area = float(cv2.contourArea(approx))
        if area < image_area * 0.35:
            continue
        if area > best_area:
            best_quad = approx.reshape(4, 2).astype(np.float32)
            best_area = area

    if best_quad is None:
        return image_bgr, False

    sums = best_quad.sum(axis=1)
    diffs = np.diff(best_quad, axis=1).reshape(-1)
    tl = best_quad[np.argmin(sums)]
    br = best_quad[np.argmax(sums)]
    tr = best_quad[np.argmin(diffs)]
    bl = best_quad[np.argmax(diffs)]
    src = np.array([tl, tr, br, bl], dtype=np.float32)

    width_a = np.linalg.norm(br - bl)
    width_b = np.linalg.norm(tr - tl)
    height_a = np.linalg.norm(tr - br)
    height_b = np.linalg.norm(tl - bl)
    max_w = int(max(width_a, width_b))
    max_h = int(max(height_a, height_b))
    if max_w < 100 or max_h < 100:
        return image_bgr, False

    dst = np.array(
        [[0, 0], [max_w - 1, 0], [max_w - 1, max_h - 1], [0, max_h - 1]],
        dtype=np.float32,
    )
    M = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(image_bgr, M, (max_w, max_h))
    return warped, True


def normalize_document(image_bgr: np.ndarray) -> Tuple[np.ndarray, Dict[str, object]]:
    # EXIF orientation is handled at load time; portrait/landscape is handled in preprocessing.
    rectified, applied = rectify_perspective(image_bgr)
    meta = {
        "rotation_applied": 0,
        "perspective_corrected": applied,
    }
    return rectified, meta
