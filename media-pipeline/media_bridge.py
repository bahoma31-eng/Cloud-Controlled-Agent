#!/usr/bin/env python3
# media-pipeline/media_bridge.py
# Local media bridge for GitHub-based input/output/archive pipeline
#
# Runs locally and:
# - polls media-pipeline/input/ for images
# - downloads all images
# - applies safe enhancements (no content-altering generation)
# - adds a fixed footer for boncoin restaurant
# - places a headline in a safe area (avoids important regions using saliency)
# - exports 1080x1350 and 1080x1920 variants
# - uploads results to media-pipeline/output/
# - moves originals to media-pipeline/archive/

import os
import sys
import time
import base64
import shutil
from io import BytesIO
from datetime import datetime, timezone

import requests
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

try:
	from dotenv import load_dotenv
	load_dotenv()
except Exception:
	pass

# ----------------------------
# Config (ready-to-run defaults)
# ----------------------------
REPO_OWNER = os.getenv("REPO_OWNER", "bahoma31-eng")
REPO_NAME = os.getenv("REPO_NAME", "Cloud-Controlled-Agent")
BRANCH = os.getenv("REPO_BRANCH", "main")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()

POLL_INTERVAL = int(os.getenv("BRIDGE_POLL_SECONDS", "20"))

INPUT_DIR = "media-pipeline/input/"
OUTPUT_DIR = "media-pipeline/output/"
ARCHIVE_DIR = "media-pipeline/archive/"

# Branding (fixed footer)
BRAND = os.getenv("BRAND_NAME", "boncoin restaurant")
FACEBOOK = os.getenv("FACEBOOK_NAME", "Boncoin restaurant")
INSTAGRAM = os.getenv("INSTAGRAM_HANDLE", "boncoin_fastfood")
TIKTOK = os.getenv("TIKTOK_HANDLE", "boncoin_fastfood")
WHATSAPP = os.getenv("WHATSAPP_NUMBER", "0795235138")

# Text overlay defaults
DEFAULT_HEADLINE = os.getenv("HEADLINE_TEXT", "عرض اليوم")
DEFAULT_CTA = os.getenv("CTA_TEXT", "اطلب الآن")

# Font (optional). If not set, uses a default font; Arabic shaping may not be perfect.
FONT_PATH = os.getenv("FONT_PATH", "").strip()

# Local temp workspace
LOCAL_WORKDIR = os.path.join(os.getcwd(), ".media_bridge_tmp")
LOCAL_OUT = os.path.join(LOCAL_WORKDIR, "out")

GITHUB_API_BASE = "https://api.github.com"
ALLOWED_EXT = (".png", ".jpg", ".jpeg", ".webp")


# ----------------------------
# Helpers - logging
# ----------------------------
def utc_now():
	return datetime.now(timezone.utc).isoformat()

def log(msg):
	print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

def die(msg, code=1):
	print(msg)
	sys.exit(code)


# ----------------------------
# GitHub API helpers
# ----------------------------
def gh_headers():
	return {
		"Authorization": f"token {GITHUB_TOKEN}",
		"Accept": "application/vnd.github+json",
		"User-Agent": "media-bridge/1.0",
	}

def gh_contents_url(path):
	path = path.lstrip("/")
	return f"{GITHUB_API_BASE}/repos/{REPO_OWNER}/{REPO_NAME}/contents/{path}"

def gh_get_json(url, timeout=30):
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
	old = requests.get(url, headers=gh_headers(), timeout=30)
	sha = old.json().get("sha") if old.status_code == 200 else None

	payload = {
		"message": message,
		"content": base64.b64encode(content_bytes).decode("utf-8"),
		"branch": BRANCH,
	}
	if sha:
		payload["sha"] = sha

	r = requests.put(url, headers=gh_headers(), json=payload, timeout=60)
	return r.status_code in (200, 201), r.text

def gh_delete_file(path, message):
	url = gh_contents_url(path)
	old = requests.get(url, headers=gh_headers(), timeout=30)
	if old.status_code != 200:
		return False, f"Not found: {path}"

	sha = old.json().get("sha")
	payload = {"message": message, "sha": sha, "branch": BRANCH}
	r = requests.delete(url, headers=gh_headers(), json=payload, timeout=60)
	return r.status_code in (200, 204), r.text


# ----------------------------
# Image processing
# ----------------------------
def ensure_dirs():
	os.makedirs(LOCAL_OUT, exist_ok=True)


def pil_to_cv(img_pil):
	arr = np.array(img_pil.convert("RGB"))
	return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def cv_to_pil(img_cv):
	rgb = cv2.cvtColor(img_cv, cv2.COLOR_BGR2RGB)
	return Image.fromarray(rgb)


def resize_cover(pil_img, target_w, target_h):
	w, h = pil_img.size
	src_aspect = w / h
	dst_aspect = target_w / target_h

	if src_aspect > dst_aspect:
		new_w = int(h * dst_aspect)
		x0 = (w - new_w) // 2
		pil_img = pil_img.crop((x0, 0, x0 + new_w, h))
	else:
		new_h = int(w / dst_aspect)
		y0 = (h - new_h) // 2
		pil_img = pil_img.crop((0, y0, w, y0 + new_h))

	return pil_img.resize((target_w, target_h), Image.LANCZOS)


def mild_food_enhance(img_cv):
	hsv = cv2.cvtColor(img_cv, cv2.COLOR_BGR2HSV).astype(np.float32)
	h, s, v = cv2.split(hsv)
	s = np.clip(s * 1.08, 0, 255)
	v = np.clip(v * 1.03, 0, 255)
	hsv2 = cv2.merge([h, s, v]).astype(np.uint8)
	out = cv2.cvtColor(hsv2, cv2.COLOR_HSV2BGR)

	blur = cv2.GaussianBlur(out, (0, 0), 1.2)
	out = cv2.addWeighted(out, 1.12, blur, -0.12, 0)
	return out


def get_font(size):
	if FONT_PATH and os.path.isfile(FONT_PATH):
		return ImageFont.truetype(FONT_PATH, size=size)
	return ImageFont.load_default()


def draw_footer(pil_img):
	w, h = pil_img.size
	footer_h = int(h * 0.18)

	overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
	d = ImageDraw.Draw(overlay)

	orange1 = (230, 115, 40, 255)
	orange2 = (255, 160, 60, 255)
	for y in range(h - footer_h, h):
		t = (y - (h - footer_h)) / max(1, footer_h - 1)
		r = int(orange1[0] * (1 - t) + orange2[0] * t)
		g = int(orange1[1] * (1 - t) + orange2[1] * t)
		b = int(orange1[2] * (1 - t) + orange2[2] * t)
		d.line([(0, y), (w, y)], fill=(r, g, b, 255))

	title_font = get_font(max(28, int(h * 0.06)))
	small_font = get_font(max(16, int(h * 0.035)))

	title = BRAND
	title_w = d.textlength(title, font=title_font)
	d.text(((w - title_w) / 2, h - footer_h + int(footer_h * 0.18)), title, font=title_font, fill=(255, 255, 255, 255))

	row_y = h - footer_h + int(footer_h * 0.63)
	info = f"facebook: {FACEBOOK}    instagram: {INSTAGRAM}    tiktok: {TIKTOK}    whatsapp: {WHATSAPP}"
	max_chars = 140
	if len(info) > max_chars:
		info = info[: max_chars - 3] + "..."
	info_w = d.textlength(info, font=small_font)
	d.text(((w - info_w) / 2, row_y), info, font=small_font, fill=(255, 255, 255, 235))

	out = Image.alpha_composite(pil_img.convert("RGBA"), overlay).convert("RGB")
	return out


def safe_text_box_by_saliency(pil_img, avoid_bottom_ratio=0.22):
	w, h = pil_img.size
	roi_h = int(h * (1 - avoid_bottom_ratio))

	img_cv = pil_to_cv(pil_img)
	roi = img_cv[:roi_h, :, :]

	try:
		sal = cv2.saliency.StaticSaliencySpectralResidual_create()
		ok, sal_map = sal.computeSaliency(roi)
		if not ok:
			raise RuntimeError("saliency failed")
		sal_map = (sal_map * 255).astype(np.uint8)
	except Exception:
		gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
		sal_map = cv2.Canny(gray, 60, 120)
		sal_map = cv2.GaussianBlur(sal_map, (0, 0), 3)

	bw = int(w * 0.48)
	bh = int(h * 0.14)
	candidates = [
		(int(w * 0.05), int(roi_h * 0.08)),
		(int(w * 0.47), int(roi_h * 0.08)),
		(int(w * 0.05), int(roi_h * 0.42)),
		(int(w * 0.47), int(roi_h * 0.42)),
	]

	best = None
	best_score = None

	for x, y in candidates:
		x2 = min(w, x + bw)
		y2 = min(roi_h, y + bh)
		patch = sal_map[y:y2, x:x2]
		if patch.size == 0:
			continue
		score = float(np.mean(patch))
		if best_score is None or score < best_score:
			best_score = score
			best = (x, y, x2 - x, y2 - y)

	if not best:
		best = (int(w * 0.26), int(roi_h * 0.08), bw, bh)

	return best


def draw_headline(pil_img, headline, cta=None):
	w, h = pil_img.size
	x, y, bw, bh = safe_text_box_by_saliency(pil_img)

	overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
	d = ImageDraw.Draw(overlay)

	box_pad = int(min(w, h) * 0.012)
	box = (x - box_pad, y - box_pad, x + bw + box_pad, y + bh + box_pad)
	box = (max(0, box[0]), max(0, box[1]), min(w, box[2]), min(h, box[3]))
	d.rounded_rectangle(box, radius=18, fill=(0, 0, 0, 90))

	head_font = get_font(max(24, int(h * 0.055)))
	cta_font = get_font(max(18, int(h * 0.04)))

	tx = box[0] + int((box[2] - box[0]) * 0.06)
	ty = box[1] + int((box[3] - box[1]) * 0.18)
	d.text((tx, ty), headline, font=head_font, fill=(255, 255, 255, 245))

	if cta:
		ty2 = ty + int((box[3] - box[1]) * 0.55)
		d.text((tx, ty2), cta, font=cta_font, fill=(255, 220, 180, 245))

	out = Image.alpha_composite(pil_img.convert("RGBA"), overlay).convert("RGB")
	return out


def process_one_image(pil_img, headline, cta):
	img_cv = pil_to_cv(pil_img)
	img_cv = mild_food_enhance(img_cv)
	pil_img = cv_to_pil(img_cv)

	if headline:
		pil_img = draw_headline(pil_img, headline=headline, cta=cta)

	pil_img = draw_footer(pil_img)
	return pil_img


def export_variants(pil_img, base_name, out_dir):
	out_files = []

	post = resize_cover(pil_img, 1080, 1350)
	post_name = f"{base_name}_post_1080x1350.jpg"
	post_path = os.path.join(out_dir, post_name)
	post.save(post_path, "JPEG", quality=92, optimize=True)
	out_files.append(post_path)

	vertical = resize_cover(pil_img, 1080, 1920)
	vert_name = f"{base_name}_vertical_1080x1920.jpg"
	vert_path = os.path.join(out_dir, vert_name)
	vertical.save(vert_path, "JPEG", quality=92, optimize=True)
	out_files.append(vert_path)

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


def clean_local_tmp():
	if os.path.isdir(LOCAL_WORKDIR):
		shutil.rmtree(LOCAL_WORKDIR, ignore_errors=True)


def main():
	if not GITHUB_TOKEN:
		die("GITHUB_TOKEN is missing. Create a .env file next to this script and add: GITHUB_TOKEN=...\n")

	log("Starting media_bridge.py")
	log(f"Repo: {REPO_OWNER}/{REPO_NAME} (branch: {BRANCH})")
	log(f"Input: {INPUT_DIR}")
	log(f"Output: {OUTPUT_DIR}")
	log(f"Archive: {ARCHIVE_DIR}")
	log(f"Polling every {POLL_INTERVAL}s")
	if not FONT_PATH:
		log("NOTE: FONT_PATH is not set. Arabic text may not render perfectly. Set FONT_PATH to an Arabic TTF if needed.")

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
				base = os.path.splitext(name)[0]

				raw, sha, _ = gh_download_file(path)
				if not raw:
					log(f"Skip: cannot download {path}")
					continue

				pil_img = Image.open(BytesIO(raw)).convert("RGB")

				headline = DEFAULT_HEADLINE
				cta = DEFAULT_CTA

				final_img = process_one_image(pil_img, headline=headline, cta=cta)
				out_files = export_variants(final_img, base_name=base, out_dir=LOCAL_OUT)

				for local_path in out_files:
					remote = OUTPUT_DIR.rstrip("/") + "/" + os.path.basename(local_path)
					ok, resp = upload_output_file(local_path, remote)
					if ok:
						log(f"Uploaded: {remote}")
					else:
						log(f"Upload failed: {remote} -> {resp[:200]}")

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
