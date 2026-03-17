#!/usr/bin/env python3
# media-pipeline/image_watcher_gemini.py

import os
import re
import json
import base64
import argparse
from datetime import datetime, timezone

import requests


def utc_now():
	return datetime.now(timezone.utc).isoformat()


def _split_keys(raw: str):
	return [k.strip() for k in (raw or "").split(",") if k.strip()]


def _key_index_path(out_path: str):
	base_dir = os.path.dirname(os.path.abspath(out_path))
	return os.path.join(base_dir, ".gemini_key_index")


def get_next_key(out_path: str):
	keys = _split_keys(os.getenv("GEMINI_API_KEYS", ""))
	if not keys:
		raise RuntimeError("GEMINI_API_KEYS is missing. Set GEMINI_API_KEYS=key1,key2,key3,key4")

	idx_path = _key_index_path(out_path)
	idx = 0
	try:
		if os.path.isfile(idx_path):
			with open(idx_path, "r", encoding="utf-8") as f:
				idx = int((f.read() or "0").strip() or "0")
	except Exception:
		idx = 0

	key = keys[idx % len(keys)]
	next_idx = (idx + 1) % len(keys)
	try:
		with open(idx_path, "w", encoding="utf-8") as f:
			f.write(str(next_idx))
	except Exception:
		pass
	return key


def _strip_code_fences(s: str) -> str:
	s = s.strip()
	s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.I)
	s = re.sub(r"\s*```$", "", s)
	return s.strip()


def extract_json(text: str):
	if not text:
		raise ValueError("Empty model response")

	candidate = _strip_code_fences(text)

	try:
		return json.loads(candidate)
	except Exception:
		pass

	start = candidate.find("{")
	if start == -1:
		raise ValueError("Model did not return JSON object")

	depth = 0
	end = -1
	in_str = False
	esc = False
	for i, ch in enumerate(candidate[start:], start=start):
		if in_str:
			if esc:
				esc = False
			elif ch == "\\":
				esc = True
			elif ch == '"':
				in_str = False
			continue

		if ch == '"':
			in_str = True
		elif ch == "{":
			depth += 1
		elif ch == "}":
			depth -= 1
			if depth == 0:
				end = i
				break

	if end == -1:
		raise ValueError("Incomplete JSON from model (truncated output)")

	return json.loads(candidate[start:end + 1])


def _clamp(v, lo, hi):
	return max(lo, min(hi, v))


def coerce_schema(meta: dict, filename: str, w: int, h: int) -> dict:
	out = {
		"version": 1,
		"generated_at": utc_now(),
		"source_image": {"filename": filename, "width": int(w), "height": int(h)},
	}

	analysis = meta.get("analysis") if isinstance(meta.get("analysis"), dict) else {}
	out["analysis"] = {
		"dominant_colors": (analysis.get("dominant_colors") or ["#111111", "#ffffff", "#e67328"])[:3],
		"brightness": float(analysis.get("brightness")) if isinstance(analysis.get("brightness"), (int, float)) else 0.5,
		"recommended_text_theme": analysis.get("recommended_text_theme") if analysis.get("recommended_text_theme") in ("light", "dark") else "light",
	}

	layout = meta.get("layout") if isinstance(meta.get("layout"), dict) else {}
	chosen = layout.get("chosen_region_px") if isinstance(layout.get("chosen_region_px"), dict) else {}
	if not chosen:
		chosen = {"x": int(w * 0.08), "y": int(h * 0.62), "w": int(w * 0.84), "h": int(h * 0.22)}

	cx = int(chosen.get("x", int(w * 0.08)))
	cy = int(chosen.get("y", int(h * 0.62)))
	cw = int(chosen.get("w", int(w * 0.84)))
	ch = int(chosen.get("h", int(h * 0.22)))

	cx = _clamp(cx, 0, max(0, w - 1))
	cy = _clamp(cy, 0, max(0, h - 1))
	cw = _clamp(cw, 120, max(120, w - cx))
	ch = _clamp(ch, 80, max(80, h - cy))

	out["layout"] = {
		"empty_regions_px": layout.get("empty_regions_px") if isinstance(layout.get("empty_regions_px"), list) else [
			{"x": cx, "y": cy, "w": cw, "h": ch, "score": 0.0}
		],
		"chosen_region_px": {"x": cx, "y": cy, "w": cw, "h": ch},
	}

	style = meta.get("text_style") if isinstance(meta.get("text_style"), dict) else {}
	shadow = style.get("shadow") if isinstance(style.get("shadow"), dict) else {}
	out["text_style"] = {
		"font_family": "Cairo",
		"font_weight": int(style.get("font_weight", 800)) if str(style.get("font_weight", "")).isdigit() else 800,
		"font_size_px": int(style.get("font_size_px", max(28, int(h * 0.055)))),
		"color": style.get("color", "#ffffff"),
		"shadow": {
			"enabled": bool(shadow.get("enabled", True)),
			"blur": int(shadow.get("blur", 18)) if str(shadow.get("blur", "")).isdigit() else 18,
			"opacity": float(shadow.get("opacity", 0.35)) if isinstance(shadow.get("opacity"), (int, float)) else 0.35,
			"x": int(shadow.get("x", 0)) if str(shadow.get("x", "")).lstrip("-").isdigit() else 0,
			"y": int(shadow.get("y", 8)) if str(shadow.get("y", "")).lstrip("-").isdigit() else 8,
		},
	}

	filters = meta.get("filters") if isinstance(meta.get("filters"), dict) else {}
	out["filters"] = {
		"brightness": float(filters.get("brightness", 1.04)) if isinstance(filters.get("brightness"), (int, float)) else 1.04,
		"contrast": float(filters.get("contrast", 1.08)) if isinstance(filters.get("contrast"), (int, float)) else 1.08,
		"saturation": float(filters.get("saturation", 1.08)) if isinstance(filters.get("saturation"), (int, float)) else 1.08,
		"sharpness": float(filters.get("sharpness", 1.08)) if isinstance(filters.get("sharpness"), (int, float)) else 1.08,
		"background_blur_px": int(filters.get("background_blur_px", 0)) if str(filters.get("background_blur_px", "")).isdigit() else 0,
	}

	copy = meta.get("copy") if isinstance(meta.get("copy"), dict) else {}
	out["copy"] = {"title": copy.get("title", "عرض اليوم"), "cta": copy.get("cta", "اطلب الآن")}
	return out


def call_gemini(endpoint: str, key: str, payload: dict, timeout: int) -> str:
	r = requests.post(endpoint, params={"key": key}, json=payload, timeout=timeout)
	if r.status_code != 200:
		raise RuntimeError(f"Gemini API error {r.status_code}: {r.text[:2000]}")
	data = r.json()

	candidates = data.get("candidates") or []
	if not candidates:
		raise RuntimeError(f"Gemini returned no candidates: {json.dumps(data)[:2000]}")

	parts = []
	for p in (candidates[0].get("content") or {}).get("parts", []):
		t = p.get("text")
		if t:
			parts.append(t)
	text = "\n".join(parts).strip()
	if not text:
		raise RuntimeError(f"Gemini returned empty text: {json.dumps(data)[:2000]}")
	return text


def main():
	ap = argparse.ArgumentParser()
	ap.add_argument("--image_path", required=True)
	ap.add_argument("--mime", required=True)
	ap.add_argument("--width", type=int, required=True)
	ap.add_argument("--height", type=int, required=True)
	ap.add_argument("--filename", required=True)
	ap.add_argument("--out", required=True)
	args = ap.parse_args()

	with open(args.image_path, "rb") as f:
		img_b64 = base64.b64encode(f.read()).decode("utf-8")

	model = (os.getenv("GEMINI_MODEL", "gemini-2.5-flash") or "gemini-2.5-flash").strip()
	endpoint_tpl = (os.getenv("GEMINI_ENDPOINT", "https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent") or "").strip()
	endpoint = endpoint_tpl.replace("{MODEL}", model)

	key = get_next_key(args.out)
	timeout = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "60"))

	prompt = (
		"أعد JSON فقط.\n"
		"المفاتيح المطلوبة فقط: analysis, layout(empty_regions_px, chosen_region_px), text_style, filters, copy.\n"
		"اختر مكان نص احترافي لا يغطي العنصر الرئيسي.\n"
		"حدد لون نص واضح عالي التباين مع الخلفية.\n"
		"اختر title قصير جذاب (3 إلى 5 كلمات) و CTA قصير.\n"
	)

	payload = {
		"contents": [{"role": "user", "parts": [{"text": prompt}, {"inline_data": {"mime_type": args.mime, "data": img_b64}}]}],
		"generationConfig": {"temperature": 0.2, "maxOutputTokens": 2400, "response_mime_type": "application/json"},
	}

	text = call_gemini(endpoint, key, payload, timeout)
	os.makedirs(os.path.dirname(args.out), exist_ok=True)
	with open(args.out + ".raw.txt", "w", encoding="utf-8") as f:
		f.write(text)

	parsed = extract_json(text)
	meta = coerce_schema(parsed, args.filename, args.width, args.height)
	with open(args.out, "w", encoding="utf-8") as f:
		json.dump(meta, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
	main()
