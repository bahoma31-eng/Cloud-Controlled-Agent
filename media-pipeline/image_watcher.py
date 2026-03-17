#!/usr/bin/env python3
# media-pipeline/image_watcher.py
# تحليل الصورة لإخراج ميتاداتا: مناطق فارغة للكتابة + ألوان مهيمنة + سطوع + اقتراح ستايل + نصوص مقترحة

import os
import json
import argparse
from datetime import datetime, timezone

import cv2
import numpy as np

ALLOWED_EXT = (".png", ".jpg", ".jpeg", ".webp")


def utc_now():
	return datetime.now(timezone.utc).isoformat()


def clamp(v, lo, hi):
	return max(lo, min(hi, v))


def hex_color(bgr):
	b, g, r = [int(x) for x in bgr]
	return f"#{r:02x}{g:02x}{b:02x}"


def dominant_colors(img_bgr, k=5):
	# downsample for speed
	small = cv2.resize(img_bgr, (0, 0), fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA)
	pixels = small.reshape((-1, 3)).astype(np.float32)
	if pixels.shape[0] < k:
		k = max(1, pixels.shape[0])

	criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
	_, labels, centers = cv2.kmeans(pixels, k, None, criteria, 5, cv2.KMEANS_PP_CENTERS)
	centers = centers.astype(np.uint8)
	counts = np.bincount(labels.flatten(), minlength=k)
	idx = np.argsort(-counts)
	return [hex_color(centers[i]) for i in idx]


def brightness_score(img_bgr):
	# normalized brightness 0..1 from V channel
	hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
	v = hsv[:, :, 2].astype(np.float32) / 255.0
	return float(np.mean(v))


def find_empty_regions(img_bgr, max_regions=4):
	"""Find low-detail regions suitable for text.
	Returns list of {x,y,w,h,score} in px.
	"""
	h, w = img_bgr.shape[:2]
	gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

	# Edge density as a proxy for details
	edges = cv2.Canny(gray, 60, 140)
	edges = cv2.GaussianBlur(edges, (0, 0), 2.0)

	# Candidate windows (heuristic grid)
	win_w = int(w * 0.45)
	win_h = int(h * 0.16)
	candidates = []
	for ry in (0.08, 0.32, 0.56, 0.72):
		for rx in (0.06, 0.50):
			x = int(w * rx)
			y = int(h * ry)
			x = clamp(x, 0, max(0, w - win_w))
			y = clamp(y, 0, max(0, h - win_h))
			patch = edges[y : y + win_h, x : x + win_w]
			score = float(np.mean(patch))  # lower is better
			candidates.append({"x": x, "y": y, "w": win_w, "h": win_h, "score": round(score, 4)})

	candidates.sort(key=lambda r: r["score"])
	return candidates[:max_regions]


def infer_text_theme(brightness):
	return "dark" if brightness > 0.55 else "light"


def main():
	ap = argparse.ArgumentParser()
	ap.add_argument("--image", required=True)
	ap.add_argument("--out", required=True)
	ap.add_argument("--title", default="")
	ap.add_argument("--cta", default="")
	args = ap.parse_args()

	img_path = args.image
	if not os.path.isfile(img_path):
		raise SystemExit(f"Image not found: {img_path}")

	if not img_path.lower().endswith(ALLOWED_EXT):
		raise SystemExit("Unsupported image extension")

	img = cv2.imread(img_path, cv2.IMREAD_COLOR)
	if img is None:
		raise SystemExit("Failed to read image")

	h, w = img.shape[:2]
	b = brightness_score(img)
	colors = dominant_colors(img, k=5)
	regions = find_empty_regions(img, max_regions=4)
	chosen = regions[0] if regions else {"x": int(w * 0.1), "y": int(h * 0.7), "w": int(w * 0.8), "h": int(h * 0.18), "score": 999}

	theme = infer_text_theme(b)
	text_color = "#111111" if theme == "dark" else "#ffffff"

	# Font size heuristic
	font_size = int(max(28, min(96, h * 0.055)))

	meta = {
		"version": 1,
		"generated_at": utc_now(),
		"source_image": {"filename": os.path.basename(img_path), "width": int(w), "height": int(h)},
		"analysis": {
			"dominant_colors": colors[:3],
			"brightness": round(b, 4),
			"recommended_text_theme": theme,
		},
		"layout": {
			"empty_regions_px": regions,
			"chosen_region_px": {k: chosen[k] for k in ("x", "y", "w", "h")},
		},
		"text_style": {
			"font_family": "Cairo",
			"font_weight": 800,
			"font_size_px": int(font_size),
			"color": text_color,
			"shadow": {"enabled": True, "blur": 14, "opacity": 0.28, "x": 0, "y": 8},
		},
		"filters": {
			"brightness": 1.03,
			"contrast": 1.06,
			"saturation": 1.05,
			"sharpness": 1.1,
			"background_blur_px": 0,
		},
		"copy": {
			"title": args.title or "عرض اليوم",
			"cta": args.cta or "اطلب الآن",
		},
	}

	os.makedirs(os.path.dirname(args.out), exist_ok=True)
	with open(args.out, "w", encoding="utf-8") as f:
		json.dump(meta, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
	main()
