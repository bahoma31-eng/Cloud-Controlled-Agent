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


def extract_json(text: str):
	"""Best-effort extraction of a JSON object from model output."""
	if not text:
		raise ValueError("Empty model response")

	# Prefer fenced block
	m = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.S | re.I)
	if m:
		return json.loads(m.group(1))

	candidate = _strip_code_fences(text)
	if candidate.startswith("{") and candidate.endswith("}"):
		return json.loads(candidate)

	# bracket first '{' to last '}'
	start = candidate.find("{")
	end = candidate.rfind("}")
	if start != -1 and end != -1 and end > start:
		return json.loads(candidate[start : end + 1])

	# fallback regex
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
		"أنت نظام يقوم بإرجاع JSON فقط. ممنوع أي نص خارج JSON.\n"
		"حلّل الصورة التالية (صورة طعام). نحتاج إعدادات تصميم إعلان عربي RTL.\n"
		"أعد كائن JSON واحد فقط. لا تستخدم Markdown.\n"
		"المفاتيح المطلوبة: version, source_image, analysis, layout, text_style, filters, copy.\n"
		"قواعد: تجنب وضع النص فوق الطبق أو الموضوع الرئيسي. اختر مناطق منخفضة التفاصيل.\n"
	)

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
		"generationConfig": {"temperature": 0.2, "maxOutputTokens": 1400},
	}

	r = requests.post(endpoint, params={"key": key}, json=payload, timeout=timeout)
	if r.status_code != 200:
		raise SystemExit(f"Gemini API error {r.status_code}: {r.text[:2000]}")

	data = r.json()
	parts = []
	try:
		for p in data.get("candidates", [])[0].get("content", {}).get("parts", []):
			if "text" in p:
				parts.append(p["text"])
	except Exception:
		pass
	text = "\n".join(parts).strip() if parts else json.dumps(data, ensure_ascii=False)

	# Always save raw output for debugging
	raw_path = args.out + ".raw.txt"
	try:
		os.makedirs(os.path.dirname(args.out), exist_ok=True)
		with open(raw_path, "w", encoding="utf-8") as f:
			f.write(text)
	except Exception:
		pass

	meta = extract_json(text)
	meta["version"] = 1
	meta["generated_at"] = utc_now()
	meta["source_image"] = {"filename": args.filename, "width": int(args.width), "height": int(args.height)}

	with open(args.out, "w", encoding="utf-8") as f:
		json.dump(meta, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
	main()
