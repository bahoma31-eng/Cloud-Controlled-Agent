#!/usr/bin/env python3
# media-pipeline/media_bridge.py

import os
import sys
import json
import time
import base64
import shutil
import subprocess
from datetime import datetime

import requests

try:
	from dotenv import load_dotenv
	load_dotenv()
except Exception:
	pass

REPO_OWNER = os.getenv("REPO_OWNER", "bahoma31-eng")
REPO_NAME = os.getenv("REPO_NAME", "Cloud-Controlled-Agent")
BRANCH = os.getenv("REPO_BRANCH", "main")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()

POLL_INTERVAL = int(os.getenv("BRIDGE_POLL_SECONDS", "20"))

INPUT_DIR = "media-pipeline/input/"
OUTPUT_DIR = "media-pipeline/output/"
ARCHIVE_DIR = "media-pipeline/archive/"
META_DIR = "media-pipeline/meta/"

WAIT_FONTS_MS = int(os.getenv("PLAYWRIGHT_WAIT_FONTS_MS", "3000"))
USE_GEMINI_WATCHER = (os.getenv("USE_GEMINI_WATCHER", "0").strip() in ("1", "true", "yes"))
PRINT_META_TO_TERMINAL = (os.getenv("PRINT_META_TO_TERMINAL", "1").strip() in ("1", "true", "yes"))
PRINT_GEMINI_RAW_TO_TERMINAL = (os.getenv("PRINT_GEMINI_RAW_TO_TERMINAL", "1").strip() in ("1", "true", "yes"))
FALLBACK_TO_OPENCV_ON_GEMINI_FAIL = (os.getenv("FALLBACK_TO_OPENCV_ON_GEMINI_FAIL", "1").strip() in ("1", "true", "yes"))

BRAND = os.getenv("BRAND_NAME", "boncoin restaurant")
FACEBOOK = os.getenv("FACEBOOK_NAME", "Boncoin restaurant")
INSTAGRAM = os.getenv("INSTAGRAM_HANDLE", "boncoin_fastfood")
TIKTOK = os.getenv("TIKTOK_HANDLE", "boncoin_fastfood")
WHATSAPP = os.getenv("WHATSAPP_NUMBER", "0795235138")

DEFAULT_HEADLINE = os.getenv("HEADLINE_TEXT", "عرض اليوم")
DEFAULT_CTA = os.getenv("CTA_TEXT", "اطلب الآن")

LOCAL_WORKDIR = os.path.join(os.getcwd(), ".media_bridge_tmp")
LOCAL_OUT = os.path.join(LOCAL_WORKDIR, "out")
LOCAL_META = os.path.join(LOCAL_WORKDIR, "meta")
LOCAL_HTML = os.path.join(LOCAL_WORKDIR, "html")

GITHUB_API_BASE = "https://api.github.com"
ALLOWED_EXT = (".png", ".jpg", ".jpeg", ".webp")

SIZES = [
	{"key": "post", "w": 1080, "h": 1350},
	{"key": "square", "w": 1080, "h": 1080},
	{"key": "story", "w": 1080, "h": 1920},
	{"key": "landscape", "w": 1200, "h": 630},
	{"key": "profile", "w": 400, "h": 400},
]


def log(msg):
	print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")


def die(msg, code=1):
	print(msg)
	sys.exit(code)


def ensure_dirs():
	os.makedirs(LOCAL_OUT, exist_ok=True)
	os.makedirs(LOCAL_META, exist_ok=True)
	os.makedirs(LOCAL_HTML, exist_ok=True)


def clean_local_tmp():
	if os.path.isdir(LOCAL_WORKDIR):
		shutil.rmtree(LOCAL_WORKDIR, ignore_errors=True)


def gh_headers():
	return {
		"Authorization": f"token {GITHUB_TOKEN}",
		"Accept": "application/vnd.github+json",
		"User-Agent": "media-bridge/2.5",
	}


def gh_contents_url(path):
	path = path.lstrip("/")
	return f"{GITHUB_API_BASE}/repos/{REPO_OWNER}/{REPO_NAME}/contents/{path}"


def gh_get_json(url, timeout=60):
	r = requests.get(url, headers=gh_headers(), timeout=timeout)
	if r.status_code == 200:
		return r.json()
	if r.status_code == 404:
		return None
	raise RuntimeError(f"GitHub GET failed {r.status_code}: {r.text[:2000]}")


def gh_list_dir(path):
	data = gh_get_json(gh_contents_url(path))
	if not data:
		return []
	if isinstance(data, list):
		return data
	return []


def gh_download_file(path):
	data = gh_get_json(gh_contents_url(path))
	if not data or data.get("type") != "file":
		return None, None, None
	raw = base64.b64decode(data.get("content", ""))
	return raw, data.get("sha"), data.get("name")


def gh_put_file(path, content_bytes, message):
	url = gh_contents_url(path)
	old = requests.get(url, headers=gh_headers(), timeout=60)
	sha = old.json().get("sha") if old.status_code == 200 else None
	payload = {"message": message, "content": base64.b64encode(content_bytes).decode("utf-8"), "branch": BRANCH}
	if sha:
		payload["sha"] = sha
	r = requests.put(url, headers=gh_headers(), json=payload, timeout=120)
	return r.status_code in (200, 201), r.text


def gh_delete_file(path, message):
	url = gh_contents_url(path)
	old = requests.get(url, headers=gh_headers(), timeout=60)
	if old.status_code != 200:
		return False, f"Not found: {path}"
	sha = old.json().get("sha")
	r = requests.delete(url, headers=gh_headers(), json={"message": message, "sha": sha, "branch": BRANCH}, timeout=120)
	return r.status_code in (200, 204), r.text


def to_data_url(image_bytes, mime):
	return f"data:{mime};base64,{base64.b64encode(image_bytes).decode('utf-8')}"


def guess_mime(name: str):
	name = name.lower()
	if name.endswith(".png"):
		return "image/png"
	if name.endswith(".webp"):
		return "image/webp"
	return "image/jpeg"


def run_watcher_opencv(local_img_path: str, out_meta_path: str):
	cmd = [sys.executable, os.path.join(os.path.dirname(__file__), "image_watcher.py"), "--image", local_img_path, "--out", out_meta_path]
	p = subprocess.run(cmd, capture_output=True, text=True)
	if p.returncode != 0:
		raise RuntimeError(f"opencv watcher failed: {p.stdout}\n{p.stderr}")


def _print_raw_if_exists(out_meta_path: str, w: int, h: int):
	raw_path = out_meta_path + ".raw.txt"
	if PRINT_GEMINI_RAW_TO_TERMINAL and os.path.isfile(raw_path):
		log(f"Gemini raw output ({w}x{h}):")
		try:
			print(open(raw_path, "r", encoding="utf-8").read()[:8000])
		except Exception:
			pass


def run_watcher_gemini(final_canvas_path: str, mime: str, w: int, h: int, filename: str, out_meta_path: str):
	cmd = [
		sys.executable,
		os.path.join(os.path.dirname(__file__), "image_watcher_gemini.py"),
		"--image_path",
		final_canvas_path,
		"--mime",
		mime,
		"--width",
		str(w),
		"--height",
		str(h),
		"--filename",
		filename,
		"--out",
		out_meta_path,
	]
	p = subprocess.run(cmd, capture_output=True, text=True)
	if p.returncode != 0:
		_print_raw_if_exists(out_meta_path, w, h)
		raise RuntimeError(f"gemini watcher failed:\n{p.stdout}\n{p.stderr}")


def build_html(bg_data_url: str, target_w: int, target_h: int, meta: dict):
	copy = meta.get("copy", {})
	style = meta.get("text_style", {})
	layout = meta.get("layout", {})
	box = (layout.get("chosen_region_px") or {})

	title = copy.get("title") or DEFAULT_HEADLINE
	cta = copy.get("cta") or DEFAULT_CTA

	font_family = style.get("font_family", "Cairo")
	font_weight = int(style.get("font_weight", 800))
	font_size = int(style.get("font_size_px", 64))
	color = style.get("color", "#111111")
	shadow = style.get("shadow", {})
	shadow_css = "none"
	if shadow.get("enabled"):
		op = float(shadow.get("opacity", 0.25))
		sx = int(shadow.get("x", 0))
		sy = int(shadow.get("y", 6))
		blur = int(shadow.get("blur", 12))
		shadow_css = f"{sx}px {sy}px {blur}px rgba(0,0,0,{op})"

	src = meta.get("source_image", {})
	src_w = int(src.get("width", target_w))
	src_h = int(src.get("height", target_h))
	x = int(box.get("x", int(src_w * 0.08)) * (target_w / max(1, src_w)))
	y = int(box.get("y", int(src_h * 0.70)) * (target_h / max(1, src_h)))
	bw = int(box.get("w", int(src_w * 0.84)) * (target_w / max(1, src_w)))
	bh = int(box.get("h", int(src_h * 0.18)) * (target_h / max(1, src_h)))

	footer_h = int(target_h * 0.18)

	return f"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
	<meta charset="utf-8" />
	<link rel="preconnect" href="https://fonts.googleapis.com">
	<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
	<link href="https://fonts.googleapis.com/css2?family={font_family}:wght@400;700;800;900&display=swap" rel="stylesheet">
	<style>
		html, body {{ margin: 0; padding: 0; width: {target_w}px; height: {target_h}px; overflow: hidden; background: #000; }}
		.canvas {{ position: relative; width: {target_w}px; height: {target_h}px; font-family: '{font_family}', system-ui; }}
		.bg {{ position: absolute; inset: 0; background-image: url('{bg_data_url}'); background-size: cover; background-position: center; }}
		.textbox {{ position: absolute; left: {x}px; top: {y}px; width: {bw}px; height: {bh}px; padding: 18px 22px; box-sizing: border-box; border-radius: 18px; background: rgba(0,0,0,0.22); }}
		.h1 {{ margin: 0; font-size: {font_size}px; font-weight: {font_weight}; color: {color}; text-shadow: {shadow_css}; line-height: 1.1; unicode-bidi: plaintext; }}
		.cta {{ margin-top: 10px; font-size: max(22px, {int(font_size*0.58)}px); font-weight: 700; color: #fff; opacity: 0.95; text-shadow: {shadow_css}; unicode-bidi: plaintext; }}
		.footer {{ position: absolute; left: 0; right: 0; bottom: 0; height: {footer_h}px; background: linear-gradient(180deg, #e67328 0%, #ffa03c 100%); display: flex; flex-direction: column; justify-content: center; align-items: center; gap: 8px; }}
		.brand {{ font-size: {int(target_h*0.06)}px; font-weight: 800; color: #fff; }}
		.handles {{ font-size: {int(target_h*0.032)}px; font-weight: 600; color: rgba(255,255,255,0.92); direction: ltr; unicode-bidi: plaintext; }}
	</style>
</head>
<body>
	<div class="canvas">
		<div class="bg"></div>
		<div class="textbox">
			<div class="h1">{title}</div>
			<div class="cta">{cta}</div>
		</div>
		<div class="footer">
			<div class="brand">{BRAND}</div>
			<div class="handles">facebook: {FACEBOOK} instagram: {INSTAGRAM} tiktok: {TIKTOK} whatsapp: {WHATSAPP}</div>
		</div>
	</div>
</body>
</html>"""


def render_with_playwright(html_path: str, out_png_path: str, w: int, h: int):
	cmd = [
		sys.executable,
		os.path.join(os.path.dirname(__file__), "renderer_playwright.py"),
		"--html", html_path,
		"--out", out_png_path,
		"--width", str(w),
		"--height", str(h),
		"--wait_ms", str(WAIT_FONTS_MS),
	]
	p = subprocess.run(cmd, capture_output=True, text=True)
	if p.returncode != 0:
		raise RuntimeError(f"playwright render failed: {p.stdout}\n{p.stderr}")


def export_variants(image_bytes: bytes, image_name: str):
	out_files = []
	mime_in = guess_mime(image_name)
	bg_url = to_data_url(image_bytes, mime_in)
	base = os.path.splitext(image_name)[0]

	for s in SIZES:
		w = s["w"]
		h = s["h"]

		bg_html = f"""<!doctype html><html><head><meta charset='utf-8'/><style>
			html,body{{margin:0;padding:0;width:{w}px;height:{h}px;overflow:hidden;}}
			.bg{{position:absolute;inset:0;background-image:url('{bg_url}');background-size:cover;background-position:center;}}
		</style></head><body><div class='bg'></div></body></html>"""
		bg_html_path = os.path.join(LOCAL_HTML, f"{base}_{w}x{h}_bg.html")
		bg_png_path = os.path.join(LOCAL_OUT, f"{base}_{w}x{h}_bg.png")
		with open(bg_html_path, "w", encoding="utf-8") as f:
			f.write(bg_html)
		render_with_playwright(bg_html_path, bg_png_path, w, h)

		meta_name = f"{image_name}.{w}x{h}.json"
		local_meta = os.path.join(LOCAL_META, meta_name)

		if USE_GEMINI_WATCHER:
			try:
				run_watcher_gemini(bg_png_path, "image/png", w, h, image_name, local_meta)
			except Exception as e:
				log(str(e).strip())
				if FALLBACK_TO_OPENCV_ON_GEMINI_FAIL:
					log(f"Falling back to OpenCV watcher for {w}x{h}...")
					local_img = os.path.join(LOCAL_WORKDIR, image_name)
					run_watcher_opencv(local_img, local_meta)
				else:
					raise
		else:
			local_img = os.path.join(LOCAL_WORKDIR, image_name)
			run_watcher_opencv(local_img, local_meta)

		meta = json.load(open(local_meta, "r", encoding="utf-8"))
		if PRINT_META_TO_TERMINAL:
			log(f"Meta JSON ({w}x{h}):")
			print(json.dumps(meta, ensure_ascii=False, indent=2)[:4000])

		html = build_html(bg_url, w, h, meta)
		html_path = os.path.join(LOCAL_HTML, f"{base}_{w}x{h}.html")
		png_path = os.path.join(LOCAL_OUT, f"{base}_{w}x{h}.png")
		with open(html_path, "w", encoding="utf-8") as f:
			f.write(html)
		render_with_playwright(html_path, png_path, w, h)
		out_files.append((png_path, f"{base}_{w}x{h}.png", local_meta))

	return out_files


def list_input_images():
	items = gh_list_dir(INPUT_DIR)
	return [it for it in items if it.get("type") == "file" and it.get("name", "").lower().endswith(ALLOWED_EXT)]


def main():
	if not GITHUB_TOKEN:
		die("GITHUB_TOKEN is missing. Create a .env file next to this script and add: GITHUB_TOKEN=...\n")

	log("Starting media_bridge.py")
	log(f"Repo: {REPO_OWNER}/{REPO_NAME} (branch: {BRANCH})")
	log(f"Input: {INPUT_DIR}")
	log(f"Output: {OUTPUT_DIR}")
	log(f"Archive: {ARCHIVE_DIR}")
	log(f"Meta: {META_DIR}")
	log(f"Playwright wait fonts: {WAIT_FONTS_MS}ms")
	log(f"Gemini watcher: {'ON' if USE_GEMINI_WATCHER else 'OFF'}")
	log(f"Polling every {POLL_INTERVAL}s")

	while True:
		try:
			clean_local_tmp()
			ensure_dirs()

			files = list_input_images()
			if not files:
				time.sleep(POLL_INTERVAL)
				continue

			log(f"Found {len(files)} image(s) in input.")
			for it in files:
				path = it["path"]
				name = it["name"]

				raw, sha, _ = gh_download_file(path)
				if not raw:
					log(f"Skip: cannot download {path}")
					continue

				local_img = os.path.join(LOCAL_WORKDIR, name)
				os.makedirs(os.path.dirname(local_img), exist_ok=True)
				with open(local_img, "wb") as f:
					f.write(raw)

				out_files = export_variants(raw, name)

				last_meta_path = None
				for local_path, out_name, meta_path in out_files:
					remote = OUTPUT_DIR.rstrip("/") + "/" + out_name
					ok, resp = gh_put_file(remote, open(local_path, "rb").read(), f"media-bridge: add {out_name}")
					log(f"Uploaded: {remote}" if ok else f"Upload failed: {remote} -> {resp[:200]}")
					last_meta_path = meta_path

				if last_meta_path and os.path.isfile(last_meta_path):
					remote_meta = META_DIR.rstrip("/") + "/" + os.path.basename(last_meta_path)
					okm, resp_m = gh_put_file(remote_meta, open(last_meta_path, "rb").read(), f"media-bridge: meta {os.path.basename(last_meta_path)}")
					log(f"Uploaded meta: {remote_meta}" if okm else f"Meta upload failed: {resp_m[:200]}")

				archive_path = ARCHIVE_DIR.rstrip("/") + "/" + name
				ok_a, resp_a = gh_put_file(archive_path, raw, f"media-bridge: archive {name}")
				if ok_a:
					gh_delete_file(path, f"media-bridge: remove {name} from input")
					log(f"Archived original: {name}")
				else:
					log(f"Archive failed for {name}: {resp_a[:200]}")

			time.sleep(POLL_INTERVAL)
		except KeyboardInterrupt:
			log("Stopping media bridge.")
			break
		except Exception as e:
			log(f"ERROR: {e}")
			time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
	main()
