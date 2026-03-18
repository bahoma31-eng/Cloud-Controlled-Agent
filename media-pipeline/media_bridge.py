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
from PIL import Image

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
USE_GEMINI_WATCHER = (os.getenv("USE_GEMINI_WATCHER", "1").strip().lower() in ("1", "true", "yes"))
USE_GEMINI_FOOTER_WATCHER = (os.getenv("USE_GEMINI_FOOTER_WATCHER", "1").strip().lower() in ("1", "true", "yes"))
PRINT_META_TO_TERMINAL = (os.getenv("PRINT_META_TO_TERMINAL", "1").strip().lower() in ("1", "true", "yes"))
PRINT_GEMINI_RAW_TO_TERMINAL = (os.getenv("PRINT_GEMINI_RAW_TO_TERMINAL", "1").strip().lower() in ("1", "true", "yes"))
PRINT_FOOTER_META_TO_TERMINAL = (os.getenv("PRINT_FOOTER_META_TO_TERMINAL", "1").strip().lower() in ("1", "true", "yes"))
FALLBACK_TO_OPENCV_ON_GEMINI_FAIL = (os.getenv("FALLBACK_TO_OPENCV_ON_GEMINI_FAIL", "1").strip().lower() in ("1", "true", "yes"))
FALLBACK_TO_DEFAULT_FOOTER_ON_FAIL = (os.getenv("FALLBACK_TO_DEFAULT_FOOTER_ON_FAIL", "1").strip().lower() in ("1", "true", "yes"))

BRAND = os.getenv("BRAND_NAME", "boncoin restaurant")
FACEBOOK = os.getenv("FACEBOOK_NAME", "Boncoin restaurant")
INSTAGRAM = os.getenv("INSTAGRAM_HANDLE", "boncoin_fastfood")
TIKTOK = os.getenv("TIKTOK_HANDLE", "boncoin_fastfood")
WHATSAPP = os.getenv("WHATSAPP_NUMBER", "0795235138")

DEFAULT_HEADLINE = os.getenv("HEADLINE_TEXT", "عرض اليوم")
DEFAULT_CTA = os.getenv("CTA_TEXT", "اطلب الآن")

FOOTER_HEIGHT_RATIO = float(os.getenv("FOOTER_HEIGHT_RATIO", "0.20"))

LOCAL_WORKDIR = os.path.join(os.getcwd(), ".media_bridge_tmp")
LOCAL_OUT = os.path.join(LOCAL_WORKDIR, "out")
LOCAL_META = os.path.join(LOCAL_WORKDIR, "meta")
LOCAL_HTML = os.path.join(LOCAL_WORKDIR, "html")

GITHUB_API_BASE = "https://api.github.com"
ALLOWED_EXT = (".png", ".jpg", ".jpeg", ".webp")

# ==========================================================
# Parallel runner: FB watcher + publisher (image/video)
# ==========================================================
FB_WATCHER_PUBLISHER_SCRIPT = os.getenv(
    "FB_WATCHER_PUBLISHER_SCRIPT",
    r"C:\Users\Revexn\Cloud-Controlled-Agent\social_media\facebook\fb_watcher_publisher.py"
)
SOCIAL_TOKENS_PATH = os.getenv(
    "SOCIAL_TOKENS_PATH",
    r"C:\Users\Revexn\Cloud-Controlled-Agent\social_media\social_tokens.json"
)
REPO_ROOT_CWD = os.getenv(
    "REPO_ROOT_CWD",
    r"C:\Users\Revexn\Cloud-Controlled-Agent"
)


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
        "User-Agent": "media-bridge/3.4",
    }


def gh_contents_url(path):
    path = path.lstrip("/")
    return f"{GITHUB_API_BASE}/repos/{REPO_OWNER}/{REPO_NAME}/contents/{path}"


def gh_get_json(url, timeout=60):
    r = requests.get(url, headers=gh_headers(), params={"ref": BRANCH}, timeout=timeout)
    if r.status_code == 200:
        return r.json()
    if r.status_code == 404:
        return None
    log(f"GitHub GET error {r.status_code} on {url}")
    raise RuntimeError(f"GitHub GET failed {r.status_code}: {r.text[:2000]}")


def gh_list_dir(path):
    data = gh_get_json(gh_contents_url(path))
    return data if isinstance(data, list) else []


def gh_download_file(path):
    """
    تنزيل ملف من GitHub Contents API مع fallback لروابط download_url.
    هذا يحل مشكلة Skip: cannot download للصور التي لا تُرجع content/base64 مباشرة.
    """
    url = gh_contents_url(path)
    data = gh_get_json(url)
    if not data or data.get("type") != "file":
        log(f"Download miss: path={path}, branch={BRANCH}, url={url}")
        return None, None, None

    name = data.get("name")
    sha = data.get("sha")

    # 1) المسار المعتاد: content + base64
    b64_content = data.get("content")
    if isinstance(b64_content, str) and b64_content.strip():
        try:
            raw = base64.b64decode(b64_content, validate=False)
            if raw:
                return raw, sha, name
        except Exception as e:
            log(f"Base64 decode failed for {path}: {e}")

    # 2) fallback: download_url
    dl = data.get("download_url")
    if dl:
        try:
            r = requests.get(dl, headers=gh_headers(), timeout=120)
            if r.status_code == 200 and r.content:
                return r.content, sha, name
            log(f"download_url fetch failed {r.status_code} for {path}")
        except Exception as e:
            log(f"download_url exception for {path}: {e}")

    # 3) fallback أقوى: git_url (raw blob from Git API)
    git_url = data.get("git_url")
    if git_url:
        try:
            rb = requests.get(git_url, headers=gh_headers(), timeout=120)
            if rb.status_code == 200:
                blob = rb.json()
                enc = (blob.get("encoding") or "").lower()
                cont = blob.get("content") or ""
                if enc == "base64" and cont:
                    raw = base64.b64decode(cont, validate=False)
                    if raw:
                        return raw, sha, name
            else:
                log(f"git_url fetch failed {rb.status_code} for {path}")
        except Exception as e:
            log(f"git_url exception for {path}: {e}")

    log(f"Download miss: no usable content for path={path}, branch={BRANCH}, url={url}")
    return None, sha, name


def gh_put_file(path, content_bytes, message):
    url = gh_contents_url(path)
    old = requests.get(url, headers=gh_headers(), params={"ref": BRANCH}, timeout=60)
    sha = old.json().get("sha") if old.status_code == 200 else None
    payload = {"message": message, "content": base64.b64encode(content_bytes).decode("utf-8"), "branch": BRANCH}
    if sha:
        payload["sha"] = sha
    r = requests.put(url, headers=gh_headers(), json=payload, timeout=120)
    return r.status_code in (200, 201), r.text


def gh_delete_file(path, message, expected_sha=None):
    url = gh_contents_url(path)

    sha = expected_sha
    if not sha:
        old = requests.get(url, headers=gh_headers(), params={"ref": BRANCH}, timeout=60)
        if old.status_code != 200:
            return False, f"Not found: {path}"
        sha = old.json().get("sha")

    if not sha:
        return False, f"Missing sha for delete: {path}"

    r = requests.delete(
        url,
        headers=gh_headers(),
        json={"message": message, "sha": sha, "branch": BRANCH},
        timeout=120
    )
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


def get_image_size(local_img_path: str):
    with Image.open(local_img_path) as im:
        return im.width, im.height


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
        sys.executable, os.path.join(os.path.dirname(__file__), "image_watcher_gemini.py"),
        "--image_path", final_canvas_path, "--mime", mime,
        "--width", str(w), "--height", str(h),
        "--filename", filename, "--out", out_meta_path,
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        _print_raw_if_exists(out_meta_path, w, h)
        raise RuntimeError(f"gemini watcher failed:\n{p.stdout}\n{p.stderr}")


def run_watcher_footer_gemini(final_canvas_path: str, mime: str, w: int, h: int, filename: str, footer_x: int, footer_y: int, footer_w: int, footer_h: int, out_meta_path: str):
    cmd = [
        sys.executable, os.path.join(os.path.dirname(__file__), "image_watcher_footer_gemini.py"),
        "--image_path", final_canvas_path, "--mime", mime,
        "--width", str(w), "--height", str(h),
        "--filename", filename,
        "--footer_x", str(footer_x), "--footer_y", str(footer_y),
        "--footer_w", str(footer_w), "--footer_h", str(footer_h),
        "--out", out_meta_path,
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        _print_raw_if_exists(out_meta_path, w, h)
        raise RuntimeError(f"footer gemini watcher failed:\n{p.stdout}\n{p.stderr}")


def _safe_int(v, default):
    try:
        return int(v)
    except Exception:
        return int(default)


def _safe_float(v, default):
    try:
        return float(v)
    except Exception:
        return float(default)


def _footer_defaults(target_h: int):
    return {
        "gradient": {"direction": "90deg", "stops": ["#e67328", "#ffa03c"]},
        "typography": {
            "font_family": "Cairo",
            "brand_size_px": max(22, int(target_h * 0.06)),
            "row_size_px": max(16, int(target_h * 0.032)),
            "whatsapp_size_px": max(18, int(target_h * 0.038)),
            "font_weight_brand": 900,
            "font_weight_row": 700,
            "font_weight_whatsapp": 800,
            "line_height": 1.2,
        },
        "palette": {
            "brand_color": "#ffffff",
            "row_text_color": "#ffffff",
            "icon_color": "#ffffff",
            "whatsapp_bg": "rgba(255,255,255,0.12)",
            "whatsapp_text": "#00ff00",
            "whatsapp_label": "#d8ffd8",
            "card_bg": "rgba(0,0,0,0.28)",
            "card_border": "rgba(255,255,255,0.16)",
            "divider_color": "rgba(255,255,255,0.55)",
        },
        "layout_inside_footer_px": {
            "card_radius_px": 18,
            "row_gap_px": 10,
            "padding_px": 14,
        },
        "effects": {
            "card_shadow_opacity": 0.18,
            "text_shadow_opacity": 0.25,
            "text_shadow_blur_px": 8,
            "glass_blur_px": 0,
        }
    }


def build_contact_footer_html(target_w: int, target_h: int, footer_h: int, footer_meta: dict = None):
    d = _footer_defaults(target_h)
    fm = footer_meta if isinstance(footer_meta, dict) else {}

    gradient = fm.get("gradient", {})
    stops = gradient.get("stops", d["gradient"]["stops"])
    if not isinstance(stops, list) or len(stops) < 2:
        stops = d["gradient"]["stops"]
    direction = str(gradient.get("direction", d["gradient"]["direction"]))

    typography = fm.get("typography", {})
    brand_size = _safe_int(typography.get("brand_size_px", d["typography"]["brand_size_px"]), d["typography"]["brand_size_px"])
    row_size_base = _safe_int(typography.get("row_size_px", d["typography"]["row_size_px"]), d["typography"]["row_size_px"])
    wa_size = _safe_int(typography.get("whatsapp_size_px", d["typography"]["whatsapp_size_px"]), d["typography"]["whatsapp_size_px"])
    w_brand = _safe_int(typography.get("font_weight_brand", d["typography"]["font_weight_brand"]), d["typography"]["font_weight_brand"])
    w_row_base = _safe_int(typography.get("font_weight_row", d["typography"]["font_weight_row"]), d["typography"]["font_weight_row"])
    w_wa = _safe_int(typography.get("font_weight_whatsapp", d["typography"]["font_weight_whatsapp"]), d["typography"]["font_weight_whatsapp"])
    line_height = _safe_float(typography.get("line_height", d["typography"]["line_height"]), d["typography"]["line_height"])

    palette = d["palette"].copy()
    palette.update(fm.get("palette", {}) if isinstance(fm.get("palette", {}), dict) else {})

    layout = d["layout_inside_footer_px"].copy()
    layout.update(fm.get("layout_inside_footer_px", {}) if isinstance(fm.get("layout_inside_footer_px", {}), dict) else {})
    card_radius = _safe_int(layout.get("card_radius_px", d["layout_inside_footer_px"]["card_radius_px"]), d["layout_inside_footer_px"]["card_radius_px"])
    row_gap = _safe_int(layout.get("row_gap_px", d["layout_inside_footer_px"]["row_gap_px"]), d["layout_inside_footer_px"]["row_gap_px"])
    pad = _safe_int(layout.get("padding_px", d["layout_inside_footer_px"]["padding_px"]), d["layout_inside_footer_px"]["padding_px"])
    layout_mode = str(layout.get("layout_mode", "inline_single")).strip().lower()
    max_lines = 2 if _safe_int(layout.get("max_lines", 1), 1) >= 2 else 1
    icons_policy = str(layout.get("icons_policy", "auto")).strip().lower()
    if icons_policy not in ("auto", "on", "off"):
        icons_policy = "auto"

    effects = d["effects"].copy()
    effects.update(fm.get("effects", {}) if isinstance(fm.get("effects", {}), dict) else {})
    card_shadow_opacity = _safe_float(effects.get("card_shadow_opacity", d["effects"]["card_shadow_opacity"]), d["effects"]["card_shadow_opacity"])
    text_shadow_opacity = _safe_float(effects.get("text_shadow_opacity", d["effects"]["text_shadow_opacity"]), d["effects"]["text_shadow_opacity"])
    text_shadow_blur_px = _safe_int(effects.get("text_shadow_blur_px", d["effects"]["text_shadow_blur_px"]), d["effects"]["text_shadow_blur_px"])
    glass_blur_px = _safe_int(effects.get("glass_blur_px", d["effects"]["glass_blur_px"]), d["effects"]["glass_blur_px"])

    compact_width = target_w < 980
    very_compact_width = target_w < 860

    info_score = len(FACEBOOK) + len(INSTAGRAM) + len(TIKTOK) + len(WHATSAPP)
    use_icons = True
    if icons_policy == "off":
        use_icons = False
    elif icons_policy == "auto":
        if compact_width or info_score > 56:
            use_icons = False

    wrap_two = (layout_mode == "inline_wrapped") or (max_lines >= 2) or compact_width

    row_size = row_size_base
    w_row = w_row_base
    if compact_width:
        row_size = max(14, int(row_size_base * 0.92))
        w_row = max(500, min(700, int(w_row_base * 0.92)))
    if very_compact_width:
        row_size = max(13, int(row_size_base * 0.86))
        w_row = max(500, min(680, int(w_row * 0.95)))

    icon_fb = "📘" if use_icons else ""
    icon_ig = "📸" if use_icons else ""
    icon_tt = "🎵" if use_icons else ""

    social_line_1 = (
        f"{icon_fb + ' ' if icon_fb else ''}Facebook | {FACEBOOK}  •  "
        f"{icon_ig + ' ' if icon_ig else ''}Instagram | {INSTAGRAM}"
    )
    social_line_2 = (
        f"{icon_tt + ' ' if icon_tt else ''}TikTok | {TIKTOK}"
    )

    social_single = (
        f"{icon_fb + ' ' if icon_fb else ''}Facebook | {FACEBOOK}  •  "
        f"{icon_ig + ' ' if icon_ig else ''}Instagram | {INSTAGRAM}  •  "
        f"{icon_tt + ' ' if icon_tt else ''}TikTok | {TIKTOK}"
    )

    if not wrap_two and (len(social_single) > 84 or very_compact_width):
        wrap_two = True

    if wrap_two:
        social_html = f"""
            <div class="social-inline line1">{social_line_1}</div>
            <div class="social-inline line2">{social_line_2}</div>
        """
    else:
        social_html = f"""<div class="social-inline single">{social_single}</div>"""

    wa_bg = palette.get("whatsapp_bg", "rgba(255,255,255,0.12)")
    wa_text = palette.get("whatsapp_text", "#ffffff")
    wa_label = palette.get("whatsapp_label", "#d8ffd8")

    return f"""
    <div class="footer footer-base" style="background: linear-gradient({direction}, {stops[0]} 0%, {stops[1]} 100%);">
        <div class="brand">{BRAND}</div>
        <div class="footer-card">
            {social_html}
            <div class="row whatsapp">
                <div class="handles-text label">WhatsApp</div>
                <div class="handles-text">{WHATSAPP}</div>
                <div class="handles-text cta">اتصل الآن</div>
            </div>
        </div>

        <style>
            .footer-base {{
                position:absolute; left:0; right:0; bottom:0; height:{footer_h}px;
                display:flex; flex-direction:column; justify-content:center; align-items:center; gap:10px;
                padding:{pad}px {max(12, int(pad*1.2))}px;
                z-index: 3;
            }}
            .footer-card {{
                width:92%; max-width:1100px;
                background:{palette["card_bg"]};
                border:1px solid {palette["card_border"]};
                border-radius:{card_radius}px;
                padding:{pad}px {max(12, int(pad*1.2))}px;
                display:flex; flex-direction:column; gap:{max(6, row_gap - 2)}px;
                box-shadow: 0 10px 25px rgba(0,0,0,{card_shadow_opacity});
                backdrop-filter: blur({glass_blur_px}px);
            }}
            .brand {{
                font-size:{brand_size}px; font-weight:{w_brand};
                color:{palette["brand_color"]};
                text-align:center;
                text-shadow:0 2px {text_shadow_blur_px}px rgba(0,0,0,{text_shadow_opacity});
                z-index:4; line-height:{line_height};
            }}
            .social-inline {{
                color:{palette["row_text_color"]};
                font-size:{row_size}px; font-weight:{w_row}; line-height:{max(1.15, line_height)};
                text-align:center;
                unicode-bidi:plaintext;
            }}
            .social-inline.single {{
                white-space:nowrap;
                overflow:hidden;
                text-overflow:ellipsis;
            }}
            .social-inline.line1, .social-inline.line2 {{
                white-space:normal;
            }}

            .row.whatsapp {{
                display:flex; align-items:center; gap:10px;
                background:{wa_bg};
                border:1px solid rgba(255,255,255,0.20);
                border-radius:{max(10, int(card_radius*0.62))}px;
                padding:8px 10px;
                font-size:{max(16, int(wa_size * 0.92))}px; font-weight:{max(650, int(w_wa * 0.9))};
                color:{wa_text};
                text-shadow:0 1px {max(3, int(text_shadow_blur_px*0.6))}px rgba(0,0,0,{text_shadow_opacity});
            }}
            .row.whatsapp .label {{ color:{wa_label}; opacity:0.92; }}
            .row.whatsapp .cta {{
                margin-inline-start:auto;
                opacity:0.92;
            }}
            .handles-text {{ color:{palette["row_text_color"]}; opacity:0.96; }}
        </style>
    </div>
    """


def build_html(bg_data_url: str, target_w: int, target_h: int, meta: dict, footer_meta: dict = None, show_promo: bool = True):
    copy = meta.get("copy", {}) if isinstance(meta, dict) else {}
    style = meta.get("text_style", {}) if isinstance(meta, dict) else {}
    layout = meta.get("layout", {}) if isinstance(meta, dict) else {}
    filters = meta.get("filters", {}) if isinstance(meta, dict) else {}
    box = (layout.get("chosen_region_px") or {}) if isinstance(layout, dict) else {}

    title = copy.get("title") or DEFAULT_HEADLINE
    cta = copy.get("cta") or DEFAULT_CTA

    font_family = style.get("font_family", "Cairo")
    font_weight = int(style.get("font_weight", 800))
    font_size = int(style.get("font_size_px", max(30, int(target_h * 0.055))))
    color = style.get("color", "#ffffff")

    shadow = style.get("shadow", {})
    op = float(shadow.get("opacity", 0.35))
    sx = int(shadow.get("x", 0))
    sy = int(shadow.get("y", 10))
    blur = int(shadow.get("blur", 22))
    shadow_css = f"{sx}px {sy}px {blur}px rgba(0,0,0,{op})"

    brightness = float(filters.get("brightness", 1.04))
    contrast = float(filters.get("contrast", 1.08))
    saturation = float(filters.get("saturation", 1.08))

    footer_h = int(target_h * FOOTER_HEIGHT_RATIO)
    safe_bottom = footer_h + int(target_h * 0.02)

    x = int(box.get("x", int(target_w * 0.08)))
    y = int(box.get("y", int(target_h * 0.55)))
    bw = int(box.get("w", int(target_w * 0.84)))
    bh = int(box.get("h", int(target_h * 0.22)))

    x = max(0, min(x, target_w - 1))
    max_y = max(0, target_h - safe_bottom - 80)
    y = max(0, min(y, max_y))
    bw = max(180, min(bw, target_w - x))
    bh = max(100, min(bh, max(100, target_h - safe_bottom - y)))

    footer_html = build_contact_footer_html(target_w, target_h, footer_h, footer_meta=footer_meta)

    promo_html = ""
    if show_promo:
        promo_html = f"""
        <div class="gemini-overlay">
            <div class="h1">{title}</div>
            <div class="cta">{cta}</div>
        </div>
        """

    return f"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="utf-8" />
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family={font_family}:wght@400;700;800;900&display=swap" rel="stylesheet">
    <style>
        html, body {{ margin:0; padding:0; width:{target_w}px; height:{target_h}px; overflow:hidden; background:#000; }}
        .canvas {{ position:relative; width:{target_w}px; height:{target_h}px; font-family:'{font_family}', system-ui; }}

        .bg {{
            position:absolute; inset:0;
            background-image:url('{bg_data_url}');
            background-size:cover; background-position:center;
            filter: brightness({brightness}) contrast({contrast}) saturate({saturation});
            transform: scale(1.02);
            z-index: 1;
        }}

        .vignette {{
            position:absolute; inset:0;
            background: radial-gradient(circle at center, rgba(0,0,0,0) 45%, rgba(0,0,0,0.28) 100%);
            pointer-events:none;
            z-index: 2;
        }}

        .gemini-overlay {{
            position:absolute; left:{x}px; top:{y}px; width:{bw}px; height:{bh}px;
            padding:20px 24px; box-sizing:border-box; border-radius:20px;
            background: linear-gradient(180deg, rgba(0,0,0,0.32), rgba(0,0,0,0.16));
            backdrop-filter: blur(3px);
            border: 1px solid rgba(255,255,255,0.14);
            z-index: 5;
        }}

        .h1 {{
            margin:0;
            font-size:{font_size}px;
            font-weight:{font_weight};
            color:{color};
            text-shadow:{shadow_css};
            line-height:1.15;
            letter-spacing:0.2px;
            unicode-bidi:plaintext;
        }}

        .cta {{
            display:inline-block;
            margin-top:14px;
            padding:8px 14px;
            border-radius:999px;
            background:rgba(255,255,255,0.18);
            border:1px solid rgba(255,255,255,0.26);
            font-size:max(20px, {int(font_size*0.50)}px);
            font-weight:700;
            color:#fff;
            text-shadow:{shadow_css};
            unicode-bidi:plaintext;
        }}
    </style>
</head>
<body>
    <div class="canvas">
        <div class="bg"></div>
        <div class="vignette"></div>

        {footer_html}

        {promo_html}
    </div>
</body>
</html>"""


def render_with_playwright(html_path: str, out_png_path: str, w: int, h: int):
    cmd = [
        sys.executable, os.path.join(os.path.dirname(__file__), "renderer_playwright.py"),
        "--html", html_path, "--out", out_png_path,
        "--width", str(w), "--height", str(h),
        "--wait_ms", str(WAIT_FONTS_MS),
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"playwright render failed: {p.stdout}\n{p.stderr}")


def export_single(image_bytes: bytes, image_name: str, orig_w: int, orig_h: int):
    out_files = []
    mime_in = guess_mime(image_name)
    bg_url = to_data_url(image_bytes, mime_in)
    base = os.path.splitext(image_name)[0]

    w, h = orig_w, orig_h
    footer_h = int(h * FOOTER_HEIGHT_RATIO)
    footer_x, footer_y, footer_w = 0, h - footer_h, w

    bg_html = f"""<!doctype html><html><head><meta charset='utf-8'/><style>
        html,body{{margin:0;padding:0;width:{w}px;height:{h}px;overflow:hidden;}}
        .bg{{position:absolute;inset:0;background-image:url('{bg_url}');background-size:cover;background-position:center;}}
    </style></head><body><div class='bg'></div></body></html>"""
    bg_html_path = os.path.join(LOCAL_HTML, f"{base}_{w}x{h}_bg.html")
    bg_png_path = os.path.join(LOCAL_OUT, f"{base}_{w}x{h}_bg.png")
    with open(bg_html_path, "w", encoding="utf-8") as f:
        f.write(bg_html)
    render_with_playwright(bg_html_path, bg_png_path, w, h)

    footer_meta = None
    footer_meta_name = f"{image_name}.{w}x{h}.footer.json"
    local_footer_meta = os.path.join(LOCAL_META, footer_meta_name)

    if USE_GEMINI_FOOTER_WATCHER:
        try:
            run_watcher_footer_gemini(
                bg_png_path, "image/png", w, h, image_name,
                footer_x, footer_y, footer_w, footer_h,
                local_footer_meta
            )
            footer_meta = json.load(open(local_footer_meta, "r", encoding="utf-8"))
            if PRINT_FOOTER_META_TO_TERMINAL:
                log(f"Footer Meta JSON ({w}x{h}):")
                print(json.dumps(footer_meta, ensure_ascii=False, indent=2)[:4000])
        except Exception as e:
            log(str(e).strip())
            if not FALLBACK_TO_DEFAULT_FOOTER_ON_FAIL:
                raise
            log("Footer watcher failed -> using default footer style.")

    pre_meta = {
        "copy": {"title": DEFAULT_HEADLINE, "cta": DEFAULT_CTA},
        "text_style": {
            "font_family": "Cairo",
            "font_weight": 800,
            "font_size_px": max(30, int(h * 0.055)),
            "color": "#ffffff",
            "shadow": {"opacity": 0.35, "x": 0, "y": 10, "blur": 22}
        },
        "layout": {"chosen_region_px": {"x": int(w * 0.08), "y": int(h * 0.55), "w": int(w * 0.84), "h": int(h * 0.22)}},
        "filters": {"brightness": 1.04, "contrast": 1.08, "saturation": 1.08},
    }
    pre_html = build_html(bg_url, w, h, pre_meta, footer_meta=footer_meta, show_promo=False)
    pre_html_path = os.path.join(LOCAL_HTML, f"{base}_{w}x{h}_prepromo.html")
    prepromo_png_path = os.path.join(LOCAL_OUT, f"{base}_{w}x{h}_prepromo.png")
    with open(pre_html_path, "w", encoding="utf-8") as f:
        f.write(pre_html)
    render_with_playwright(pre_html_path, prepromo_png_path, w, h)

    meta_name = f"{image_name}.{w}x{h}.json"
    local_meta = os.path.join(LOCAL_META, meta_name)

    if USE_GEMINI_WATCHER:
        try:
            run_watcher_gemini(prepromo_png_path, "image/png", w, h, image_name, local_meta)
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

    html = build_html(bg_url, w, h, meta, footer_meta=footer_meta, show_promo=True)
    html_path = os.path.join(LOCAL_HTML, f"{base}_{w}x{h}.html")
    png_path = os.path.join(LOCAL_OUT, f"{base}_{w}x{h}.png")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    render_with_playwright(html_path, png_path, w, h)

    out_files.append({
        "png_path": png_path,
        "png_name": f"{base}_{w}x{h}.png",
        "meta_paths": [local_meta, local_footer_meta if os.path.isfile(local_footer_meta) else None]
    })

    return out_files


def list_input_images():
    items = gh_list_dir(INPUT_DIR)
    return [it for it in items if it.get("type") == "file" and it.get("name", "").lower().endswith(ALLOWED_EXT)]


def start_fb_watcher_publisher_parallel():
    """
    Start the FB watcher/publisher script in parallel:
    - Runs once at startup
    - Does NOT block the main media_bridge loop
    - Uses repo root as cwd so relative paths inside the FB script work
    """
    script = FB_WATCHER_PUBLISHER_SCRIPT
    repo_cwd = REPO_ROOT_CWD

    if not script:
        log("FB_WATCHER_PUBLISHER_SCRIPT is empty -> FB watcher/publisher will not start.")
        return None

    if not os.path.isfile(script):
        log(f"FB watcher/publisher script not found: {script}")
        return None

    if repo_cwd and not os.path.isdir(repo_cwd):
        log(f"REPO_ROOT_CWD not found: {repo_cwd} (FB watcher will start without cwd override)")
        repo_cwd = None

    if SOCIAL_TOKENS_PATH and not os.path.isfile(SOCIAL_TOKENS_PATH):
        log(f"Warning: SOCIAL_TOKENS_PATH not found: {SOCIAL_TOKENS_PATH}")

    env = os.environ.copy()
    env["SOCIAL_TOKENS_PATH"] = SOCIAL_TOKENS_PATH

    try:
        log("Starting FB watcher/publisher in parallel...")
        p = subprocess.Popen(
            [sys.executable, script],
            cwd=repo_cwd,
            env=env
        )
        log(f"FB watcher/publisher started (pid={p.pid})")
        return p
    except Exception as e:
        log(f"Failed to start FB watcher/publisher: {e}")
        return None


def main():
    if not GITHUB_TOKEN:
        die("GITHUB_TOKEN is missing. Add: GITHUB_TOKEN=... in .env\n")

    log("Starting media_bridge.py")
    log(f"Repo: {REPO_OWNER}/{REPO_NAME} (branch: {BRANCH})")
    log("Single output mode: ORIGINAL image size")
    log(f"Gemini watcher (headline): {'ON' if USE_GEMINI_WATCHER else 'OFF'}")
    log(f"Gemini watcher (footer): {'ON' if USE_GEMINI_FOOTER_WATCHER else 'OFF'}")

    # Start FB watcher/publisher in parallel
    _fb_proc = start_fb_watcher_publisher_parallel()

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
                listed_sha = it.get("sha")

                raw, downloaded_sha, _ = gh_download_file(path)
                if not raw:
                    log(f"Skip: cannot download {path} (listed_sha={listed_sha}, downloaded_sha={downloaded_sha})")
                    continue

                local_img = os.path.join(LOCAL_WORKDIR, name)
                os.makedirs(os.path.dirname(local_img), exist_ok=True)
                with open(local_img, "wb") as f:
                    f.write(raw)

                orig_w, orig_h = get_image_size(local_img)
                log(f"Original size detected: {orig_w}x{orig_h}")

                out_files = export_single(raw, name, orig_w, orig_h)

                for item in out_files:
                    local_path = item["png_path"]
                    out_name = item["png_name"]
                    meta_paths = [m for m in item.get("meta_paths", []) if m]

                    remote = OUTPUT_DIR.rstrip("/") + "/" + out_name
                    ok, resp = gh_put_file(remote, open(local_path, "rb").read(), f"media-bridge: add {out_name}")
                    log(f"Uploaded: {remote}" if ok else f"Upload failed: {remote} -> {resp[:200]}")

                    for mp in meta_paths:
                        if os.path.isfile(mp):
                            remote_meta = META_DIR.rstrip("/") + "/" + os.path.basename(mp)
                            okm, resp_m = gh_put_file(remote_meta, open(mp, "rb").read(), f"media-bridge: meta {os.path.basename(mp)}")
                            log(f"Uploaded meta: {remote_meta}" if okm else f"Meta upload failed: {resp_m[:200]}")

                archive_path = ARCHIVE_DIR.rstrip("/") + "/" + name
                ok_a, resp_a = gh_put_file(archive_path, raw, f"media-bridge: archive {name}")
                if ok_a:
                    ok_d, resp_d = gh_delete_file(path, f"media-bridge: remove {name} from input", expected_sha=listed_sha or downloaded_sha)
                    if ok_d:
                        log(f"Archived original: {name}")
                    else:
                        log(f"Archived but delete failed for {name}: {resp_d[:200]}")
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
