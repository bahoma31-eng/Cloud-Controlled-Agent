#!/usr/bin/env python3
# media-pipeline/media_bridge.py
# GitHub-based input/output/archive pipeline
#
# Runs locally and:
# - polls media-pipeline/input/ for images
# - downloads all images
# - generates meta JSON in media-pipeline/meta/
#   - default: OpenCV heuristic watcher (image_watcher.py)
#   - optional: Gemini 2.5 Flash watcher (image_watcher_gemini.py) if USE_GEMINI_WATCHER=1
# - renders ad creatives using HTML+CSS + Playwright (Chromium) to PNG
# - uploads results to media-pipeline/output/
# - moves originals to media-pipeline/archive/

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

# ----------------------------
# Config
# ----------------------------
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

# Branding (fixed)
BRAND = os.getenv("BRAND_NAME", "boncoin restaurant")
FACEBOOK = os.getenv("FACEBOOK_NAME", "Boncoin restaurant")
INSTAGRAM = os.getenv("INSTAGRAM_HANDLE", "boncoin_fastfood")
TIKTOK = os.getenv("TIKTOK_HANDLE", "boncoin_fastfood")
WHATSAPP = os.getenv("WHATSAPP_NUMBER", "0795235138")

# Text defaults
DEFAULT_HEADLINE = os.getenv("HEADLINE_TEXT", "عرض اليوم")
DEFAULT_CTA = os.getenv("CTA_TEXT", "اطلب الآن")

# Local temp workspace
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


# ----------------------------
# Helpers
# ----------------------------
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


# ----------------------------
# GitHub API helpers
# ----------------------------
def gh_headers():
	return {
		"Authorization": f"token {GITHUB_TOKEN}",
		"Accept": "application/vnd.github+json",
		"User-Agent": "media-bridge/2.1",
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
	if not data:
		return None, None, None
	if data.get("type") != "file":
		return None, None, None
	content_b64 = data.get("content", "")
	sha = data.get("sha")
	raw = base64.b64decode(content_b64)
	return raw, sha, data.get("name")


def gh_put_file(path, content_bytes, message):
	url = gh_contents_url(path)
	old = requests.get(url, headers=gh_headers(), timeout=60)
	sha = old.json().get("sha") if old.status_code == 200 else None

	payload = {
		"message": message,
		"content": base64.b64encode(content_bytes).decode("utf-8"),
		"branch": BRANCH,
	}
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
	payload = {"message": message, "sha": sha, "branch": BRANCH}
	r = requests.delete(url, headers=gh_headers(), json=payload, timeout=120)
	return r.status_code in (200, 204), r.text


# ----------------------------
# Watcher + Rendering
# ----------------------------
def to_data_url(image_bytes, mime):
	b64 = base64.b64encode(image_bytes).decode("utf-8")
	return f"data:{mime};base64,{b64}"


def guess_mime(name: str):
	name = name.lower()
	if name.endswith(".png"):
		return "image/png"
	if name.endswith(".webp"):
		return "image/webp"
	return "image/jpeg"


def run_watcher_opencv(local_img_path: str, out_meta_path: str):
	cmd = [
		sys.executable,
		os.path.join(os.path.dirname(__file__), "image_watcher.py"),
		"--image",
		local_img_path,
		"--out",
		out_meta_path,
	]
	p = subprocess.run(cmd, capture_output=True, text=True)
	if p.returncode != 0:
		raise RuntimeError(f"watcher failed: {p.stdout}\n{p.stderr}")


def run_watcher_gemini(bg_bytes: bytes, mime: str, w: int, h: int, filename: str, out_meta_path: str):
	b64 = base64.b64encode(bg_bytes).decode("utf-8")
	cmd = [
		sys.executable,
		os.path.join(os.path.dirname(__file__), "image_watcher_gemini.py"),
		"--image_b64",
		b64,
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
		raise RuntimeError(f"gemini watcher failed: {p.stdout}\n{p.stderr}")


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

	html = f"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
	<meta charset="utf-8" />
	<meta name="viewport" content="width=device-width, initial-scale=1" />
	<link rel="preconnect" href="https://fonts.googleapis.com">
	<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
	<link href="https://fonts.googleapis.com/css2?family={font_family}:wght@400;700;800;900&display=swap" rel="stylesheet">
	<style>
		html, body {{ margin: 0; padding: 0; width: {target_w}px; height: {target_h}px; overflow: hidden; background: #000; }}
		.canvas {{ position: relative; width: {target_w}px; height: {target_h}px; font-family: '{font_family}', system-ui, -apple-system; }}
		.bg {{ position: absolute; inset: 0; background-image: url('{bg_data_url}'); background-size: cover; background-position: center; filter: none; }}
		.textbox {{ position: absolute; left: {x}px; top: {y}px; width: {bw}px; height: {bh}px; padding: 18px 22px; box-sizing: border-box; border-radius: 18px; background: rgba(0,0,0,0.22); backdrop-filter: blur(0px); }}
		.h1 {{ margin: 0; font-size: {font_size}px; font-weight: {font_weight}; color: {color}; text-shadow: {shadow_css}; line-height: 1.1; unicode-bidi: plaintext; }}
		.cta {{ margin-top: 10px; font-size: max(22px, {int(font_size*0.58)}px); font-weight: 700; color: #fff; opacity: 0.95; text-shadow: {shadow_css}; unicode-bidi: plaintext; }}
		.footer {{ position: absolute; left: 0; right: 0; bottom: 0; height: {footer_h}px; background: linear-gradient(180deg, #e67328 0%, #ffa03c 100%); display:flex; flex-direction:column; justify-content:center; align-items:center; gap: 10px; }}
		.brand {{ font-size: {int(target_h*0.06)}px; font-weight: 800; color: #fff; }}
		.handles {{ font-size: {int(target_h*0.032)}px; font-weight: 600; color: rgba(255,255,255,0.92); direction:ltr; unicode-bidi: plaintext; }}
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
			<div class="handles">facebook: {FACEBOOK}    instagram: {INSTAGRAM}    tiktok: {TIKTOK}    whatsapp: {WHATSAPP}</div>
		</div>
	</div>
</body>
</html>"""
	return html


def render_with_playwright(html_path: str, out_png_path: str, w: int, h: int):
	cmd = [
		sys.executable,
		os.path.join(os.path.dirname(__file__), "renderer_playwright.py"),
		"--html",
		html_path,
		"--out",
		out_png_path,
		"--width",
		str(w),
		"--height",
		str(h),
		"--wait_ms",
		str(WAIT_FONTS_MS),
	]
	p = subprocess.run(cmd, capture_output=True, text=True)
	if p.returncode != 0:
		raise RuntimeError(f"playwright render failed: {p.stdout}\n{p.stderr}")


def export_variants(image_bytes: bytes, image_name: str):
	out_files = []
	mime = guess_mime(image_name)
	bg_url = to_data_url(image_bytes, mime)
	base = os.path.splitext(image_name)[0]

	for s in SIZES:
		w = s["w"]
		h = s["h"]

		# build final-canvas background by rendering a pure background HTML first
		# for now we simply resize via CSS cover, and also let watcher read the final canvas bytes
		# watcher inputs should be W/H accurate -> we render background-only to PNG and pass to watcher.

		# Render background-only HTML
		bg_html = f"""<!doctype html><html><head><meta charset='utf-8'/><style>
			html,body{{margin:0;padding:0;width:{w}px;height:{h}px;overflow:hidden;}}
			.bg{{position:absolute;inset:0;background-image:url('{bg_url}');background-size:cover;background-position:center;}}
		</style></head><body><div class='bg'></div></body></html>"""

		bg_html_path = os.path.join(LOCAL_HTML, f"{base}_{w}x{h}_bg.html")
		bg_png_path = os.path.join(LOCAL_OUT, f"{base}_{w}x{h}_bg.png")
		with open(bg_html_path, "w", encoding="utf-8") as f:
			f.write(bg_html)
		render_with_playwright(bg_html_path, bg_png_path, w, h)

		with open(bg_png_path, "rb") as f:
			final_canvas_bytes = f.read()

		# watcher -> meta per size
		local_meta = os.path.join(LOCAL_META, f"{image_name}.json")
		if USE_GEMINI_WATCHER:
			run_watcher_gemini(final_canvas_bytes, "image/png", w, h, image_name, local_meta)
		else:
			# fallback uses original image path; not W/H exact.
			# keep legacy behavior.
			local_img = os.path.join(LOCAL_WORKDIR, image_name)
			run_watcher_opencv(local_img, local_meta)

		with open(local_meta, "r", encoding="utf-8") as f:
			meta = json.load(f)

		html = build_html(bg_url, w, h, meta)
		html_path = os.path.join(LOCAL_HTML, f"{base}_{w}x{h}.html")
		png_path = os.path.join(LOCAL_OUT, f"{base}_{w}x{h}.png")
		with open(html_path, "w", encoding="utf-8") as f:
			f.write(html)
		render_with_playwright(html_path, png_path, w, h)
		out_files.append((png_path, f"{base}_{w}x{h}.png", local_meta))

	return out_files


# ----------------------------
# Pipeline (GitHub)
# ----------------------------
def list_input_images():
	items = gh_list_dir(INPUT_DIR)
	files = []
	for it in items:
		if it.get("type") != "file":
			continue
		name = it.get("name", "")
		if name.lower().endswith(ALLOWED_EXT):
			files.append({"path": it["path"], "name": name, "sha": it.get("sha")})
	return files


def upload_output_file(local_path, remote_path):
	with open(local_path, "rb") as f:
		data = f.read()
	ok, resp = gh_put_file(remote_path, data, f"media-bridge: add {os.path.basename(remote_path)}")
	return ok, resp


def upload_meta_file(local_path, remote_path):
	with open(local_path, "rb") as f:
		data = f.read()
	ok, resp = gh_put_file(remote_path, data, f"media-bridge: meta {os.path.basename(remote_path)}")
	return ok, resp


def move_to_archive(src_path):
	raw, sha, name = gh_download_file(src_path)
	if not raw:
		return False, "failed to download source for archiving"

	archive_path = ARCHIVE_DIR.rstrip("/") + "/" + name
	ok, resp = gh_put_file(archive_path, raw, f"media-bridge: archive {name}")
	if not ok:
		return False, f"archive upload failed: {resp[:200]}"

	ok2, resp2 = gh_delete_file(src_path, f"media-bridge: remove {name} from input")
	if not ok2:
		return False, f"delete from input failed: {resp2[:200]}"

	return True, "archived"


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

			for fmeta in files:
				path = fmeta["path"]
				name = fmeta["name"]

				raw, sha, _ = gh_download_file(path)
				if not raw:
					log(f"Skip: cannot download {path}")
					continue

				# save locally (needed for OpenCV watcher)
				local_img = os.path.join(LOCAL_WORKDIR, name)
				os.makedirs(os.path.dirname(local_img), exist_ok=True)
				with open(local_img, "wb") as f:
					f.write(raw)

				out_files = export_variants(raw, name)

				# upload outputs and meta (meta produced per size; upload the last one for now)
				last_meta_path = None
				for local_path, out_name, meta_path in out_files:
					remote = OUTPUT_DIR.rstrip("/") + "/" + out_name
					ok, resp = upload_output_file(local_path, remote)
					if ok:
						log(f"Uploaded: {remote}")
					else:
						log(f"Upload failed: {remote} -> {resp[:200]}")
					last_meta_path = meta_path

				if last_meta_path and os.path.isfile(last_meta_path):
					remote_meta = META_DIR.rstrip("/") + "/" + os.path.basename(last_meta_path)
					okm, resp_m = upload_meta_file(last_meta_path, remote_meta)
					if okm:
						log(f"Uploaded meta: {remote_meta}")
					else:
						log(f"Meta upload failed: {resp_m[:200]}")

				ok, msg = move_to_archive(path)
				if ok:
					log(f"Archived original: {name}")
				else:
					log(f"Archive failed for {name}: {msg}")

			log("Done processing current batch. Waiting...")
			time.sleep(POLL_INTERVAL)

		except KeyboardInterrupt:
			log("Stopping media bridge.")
			break
		except Exception as e:
			log(f"ERROR: {e}")
			time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
	main()
