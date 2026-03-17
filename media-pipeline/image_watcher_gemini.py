#!/usr/bin/env python3
# media-pipeline/image_watcher_gemini.py
# Gemini 2.5 Flash (Vision) watcher: analyzes the final-canvas image and outputs meta JSON.
# - Chooses empty region for text (px) + dominant colors + brightness theme + font size + suggested copy
# - Rotates across multiple API keys (round-robin) each call.

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


def _normalize_text(s: str) -> str:
	# Remove HTML breaks and weird control chars that sometimes appear in terminal capture
	s = s.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
	return s.strip()


def extract_json(text: str):
	"""Best-effort extraction of a JSON object from model output."""
	if not text:
		raise ValueError("Empty model response")

	text = _normalize_text(text)

	m = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.S | re.I)
	if m:
		return json.loads(m.group(1))

	candidate = _strip_code_fences(text)
	if candidate.startswith("{") and candidate.endswith("}"):
		return json.loads(candidate)

	start = candidate.find("{")
	end = candidate.rfind("}")
	if start != -1 and end != -1 and end > start:
		return json.loads(candidate[start : end + 1])

	m2 = re.search(r"(\{.*\})", text, flags=re.S)
	if m2:
		return json.loads(m2.group(1))

	raise ValueError("Model did not return valid JSON")


def coerce_schema(meta: dict, filename: str, w: int, h: int) -> dict:
	"""Force meta into the required schema. If model returns wrong shapes, fill defaults."""
	out = {}
	out["version"] = 1
	out["generated_at"] = utc_now()
	out["source_image"] = {"filename": filename, "width": int(w), "height": int(h)}

	analysis = meta.get("analysis") if isinstance(meta.get("analysis"), dict) else {}
	dom = analysis.get("dominant_colors") if isinstance(analysis.get("dominant_colors"), list) else []
	brightness = analysis.get("brightness")
	theme = analysis.get("recommended_text_theme")

	# fallbacks
	out["analysis"] = {
		"dominant_colors": dom[:3] if dom else ["#111111", "#ffffff", "#e67328"],
		"brightness": float(brightness) if isinstance(brightness, (int, float)) else 0.5,
		"recommended_text_theme": theme if theme in ("light", "dark") else "light",
	}

	layout = meta.get("layout") if isinstance(meta.get("layout"), dict) else {}
	empty_regions = layout.get("empty_regions_px") if isinstance(layout.get("empty_regions_px"), list) else []
	chosen = layout.get("chosen_region_px") if isinstance(layout.get("chosen_region_px"), dict) else {}
	if not chosen:
		chosen = {"x": int(w * 0.55), "y": int(h * 0.08), "w": int(w * 0.40), "h": int(h * 0.16)}

	out["layout"] = {
		"empty_regions_px": empty_regions[:4] if empty_regions else [
			{"x": chosen.get("x", 0), "y": chosen.get("y", 0), "w": chosen.get("w", 0), "h": chosen.get("h", 0), "score": 0.0}
		],
		"chosen_region_px": {
			"x": int(chosen.get("x", 0)),
			"y": int(chosen.get("y", 0)),
			"w": int(chosen.get("w", 0)),
			"h": int(chosen.get("h", 0)),
		},
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
			"blur": int(shadow.get("blur", 14)) if str(shadow.get("blur", "")).isdigit() else 14,
			"opacity": float(shadow.get("opacity", 0.28)) if isinstance(shadow.get("opacity"), (int, float)) else 0.28,
			"x": int(shadow.get("x", 0)) if str(shadow.get("x", "")).lstrip("-").isdigit() else 0,
			"y": int(shadow.get("y", 8)) if str(shadow.get("y", "")).lstrip("-").isdigit() else 8,
		},
	}

	filters = meta.get("filters") if isinstance(meta.get("filters"), dict) else {}
	out["filters"] = {
		"brightness": float(filters.get("brightness", 1.03)) if isinstance(filters.get("brightness"), (int, float)) else 1.03,
		"contrast": float(filters.get("contrast", 1.06)) if isinstance(filters.get("contrast"), (int, float)) else 1.06,
		"saturation": float(filters.get("saturation", 1.05)) if isinstance(filters.get("saturation"), (int, float)) else 1.05,
		"sharpness": float(filters.get("sharpness", 1.1)) if isinstance(filters.get("sharpness"), (int, float)) else 1.1,
		"background_blur_px": int(filters.get("background_blur_px", 0)) if str(filters.get("background_blur_px", "")).isdigit() else 0,
	}

	copy = meta.get("copy") if isinstance(meta.get("copy"), dict) else {}
	out["copy"] = {
		"title": copy.get("title", "عرض اليوم"),
		"cta": copy.get("cta", "اطلب الآن"),
	}

	return out


def call_gemini(endpoint: str, key: str, payload: dict, timeout: int) -> str:
	r = requests.post(endpoint, params={"key": key}, json=payload, timeout=timeout)
	if r.status_code != 200:
		raise RuntimeError(f"Gemini API error {r.status_code}: {r.text[:2000]}")
	data = r.json()
	parts = []
	for p in data.get("candidates", [])[0].get("content", {}).get("parts", []):
		if "text" in p:
			parts.append(p["text"])
	return "\n".join(parts).strip()


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
	endpoint_tpl = (os.getenv(
		"GEMINI_ENDPOINT",
		"{{https://generativelanguage.googleapis.com/v1beta/models/{MODEL}}}:generateContent",
	) or "").strip()
	endpoint = endpoint_tpl.replace("{MODEL}", model)

	key = get_next_key(args.out)
	timeout = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "60"))

	prompt = (
		"أعد JSON فقط بدون أي نص إضافي.\n"
		"المطلوب: analysis(layout/colors/brightness/theme) + layout(empty_regions_px + chosen_region_px px) + text_style + copy.\n"
		"اكتب مفاتيح JSON المطلوبة فقط.\n"
	)

	payload = {
		"contents": [
			{"role": "user", "parts": [
				{"text": prompt},
				{"inline_data": {"mime_type": args.mime, "data": img_b64}},
			]}},
		],
		"generationConfig": {
			"temperature": 0.2,
			"maxOutputTokens": 1600,
			"response_mime_type": "application/json",
		},
	}

	text = ""
	meta = None
	last_err = None
	for attempt in range(2):
		try:
			text = call_gemini(endpoint, key, payload, timeout)
			# save raw
			os.makedirs(os.path.dirname(args.out), exist_ok=True)
			with open(args.out + ".raw.txt", "w", encoding="utf-8") as f:
				f.write(text)
			parsed = extract_json(text)
			meta = coerce_schema(parsed, args.filename, args.width, args.height)
			break
		except Exception as e:
			last_err = e
			# make second attempt stricter
			payload["contents"][0]["parts"][0]["text"] = (
				"أعد JSON صالح 100% بدون أي نص خارج JSON.\n"
				"لا تستخدم شرح ولا اقتباسات غريبة.\n"
				"أرجع كائن واحد فقط يبدأ بـ { وينتهي بـ }.\n"
			)
			continue

	if meta is None:
		raise SystemExit(f"Failed to parse Gemini JSON: {last_err}")

	with open(args.out, "w", encoding="utf-8") as f:
		json.dump(meta, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
	main()
