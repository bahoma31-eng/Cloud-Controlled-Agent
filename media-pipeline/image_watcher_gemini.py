#!/usr/bin/env python3
# media-pipeline/image_watcher_gemini.py
# Gemini 2.5 Flash (Vision) watcher: analyzes the final-canvas image and outputs meta JSON.
# - Chooses empty region for text (px) + dominant colors + brightness theme + font size + suggested copy
# - Rotates across multiple API keys (round-robin) each call.
#
# IMPORTANT (Windows): Do NOT pass image bytes/base64 on the command line.
# This script accepts --image_path and reads the file, then sends base64 in the HTTP request.
#
# Env:
#   GEMINI_API_KEYS=key1,key2,key3,key4
#   GEMINI_MODEL=gemini-2.5-flash
#   GEMINI_ENDPOINT={{https://generativelanguage.googleapis.com/v1beta/models/{MODEL}}}:generateContent
# Optional:
#   GEMINI_TIMEOUT_SECONDS=60

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


def extract_json(text: str):
	m = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.S)
	if m:
		return json.loads(m.group(1))
	m2 = re.search(r"(\{.*\})", text, flags=re.S)
	if m2:
		return json.loads(m2.group(1))
	raise ValueError("Model did not return valid JSON")


def main():
	ap = argparse.ArgumentParser()
	ap.add_argument("--image_path", required=True, help="Path to the FINAL-canvas image (PNG/JPG)")
	ap.add_argument("--mime", required=True, help="image/png or image/jpeg")
	ap.add_argument("--width", type=int, required=True)
	ap.add_argument("--height", type=int, required=True)
	ap.add_argument("--filename", required=True)
	ap.add_argument("--out", required=True)
	args = ap.parse_args()

	if not os.path.isfile(args.image_path):
		raise SystemExit(f"Image not found: {args.image_path}")

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
		"حلّل الصورة التالية (صورة طعام لمطعم أكل خفيف). نحتاج إعدادات تصميم إعلان عربي RTL. "
		"أعد JSON فقط بدون أي شرح.\n"
		"المطلوب:\n"
		"- اختر أفضل منطقة فارغة للكتابة chosen_region_px على شكل x,y,w,h بالبيكسل داخل مساحة {W}x{H}.\n"
		"- أعد empty_regions_px: قائمة 4 مناطق مرشحة مع score (الأفضل أصغر score).\n"
		"- dominant_colors: 3 ألوان مهيمنة HEX.\n"
		"- brightness رقم 0..1 و recommended_text_theme: light أو dark.\n"
		"- text_style: font_family=Cairo, font_weight (700-900), font_size_px مناسب للمقاس، color HEX متباين، shadow.\n"
		"- copy: title و cta بالعربية (قصيرين وواضحين).\n"
		"ملاحظات: تجنب وضع النص فوق الطبق أو الموضوع الرئيسي.\n"
		"أعد JSON بهذا الشكل تماماً:\n"
		"{\n"
		"  'version': 1,\n"
		"  'source_image': {'filename': '...', 'width': W, 'height': H},\n"
		"  'analysis': {'dominant_colors': ['#...'], 'brightness': 0.0, 'recommended_text_theme': 'light|dark'},\n"
		"  'layout': {'empty_regions_px': [{'x':0,'y':0,'w':0,'h':0,'score':0.0}], 'chosen_region_px': {'x':0,'y':0,'w':0,'h':0}},\n"
		"  'text_style': {'font_family':'Cairo','font_weight':800,'font_size_px':48,'color':'#ffffff','shadow':{'enabled':true,'blur':14,'opacity':0.28,'x':0,'y':8}},\n"
		"  'filters': {'brightness': 1.03, 'contrast': 1.06, 'saturation': 1.05, 'sharpness': 1.1, 'background_blur_px': 0},\n"
		"  'copy': {'title':'...', 'cta':'...'}\n"
		"}\n"
	).replace("{W}", str(args.width)).replace("{H}", str(args.height))

	payload = {
		"contents": [
			{
				"role": "user",
				"parts": [
					{"text": prompt},
					{"inline_data": {"mime_type": args.mime, "data": img_b64}},
				],
			}
		],
		"generationConfig": {"temperature": 0.4, "maxOutputTokens": 1200},
	}

	r = requests.post(endpoint, params={"key": key}, json=payload, timeout=timeout)
	if r.status_code != 200:
		raise SystemExit(f"Gemini API error {r.status_code}: {r.text[:2000]}")

	data = r.json()
	try:
		text = data["candidates"][0]["content"]["parts"][0].get("text", "")
	except Exception:
		text = json.dumps(data, ensure_ascii=False)

	meta = extract_json(text)
	meta["version"] = 1
	meta["generated_at"] = utc_now()
	meta["source_image"] = {"filename": args.filename, "width": int(args.width), "height": int(args.height)}

	os.makedirs(os.path.dirname(args.out), exist_ok=True)
	with open(args.out, "w", encoding="utf-8") as f:
		json.dump(meta, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
	main()
