# Media Bridge (Local)

This script runs locally and automates the GitHub media pipeline:

- **Input**: `media-pipeline/input/`
- **Output**: `media-pipeline/output/`
- **Archive**: `media-pipeline/archive/`

It downloads all images in `input/`, applies safe enhancements, adds a fixed footer for **boncoin restaurant**, places a headline in a safe area, exports post + vertical variants, uploads results to `output/`, then moves originals to `archive/`.

## 1) Requirements

- Python 3.9+

Install dependencies:

```bash
pip install requests pillow opencv-python numpy python-dotenv
```

## 2) Setup (no code edits needed)

Create a `.env` file in the same folder where you run the script (or export env vars):

```env
GITHUB_TOKEN=YOUR_GITHUB_PAT
# Optional:
REPO_OWNER=bahoma31-eng
REPO_NAME=Cloud-Controlled-Agent
REPO_BRANCH=main
BRIDGE_POLL_SECONDS=20

# Optional brand overrides:
BRAND_NAME=boncoin restaurant
FACEBOOK_NAME=Boncoin restaurant
INSTAGRAM_HANDLE=boncoin_fastfood
TIKTOK_HANDLE=boncoin_fastfood
WHATSAPP_NUMBER=0795235138

# Optional headline:
HEADLINE_TEXT=عرض اليوم
CTA_TEXT=اطلب الآن

# Optional font for better Arabic rendering:
# FONT_PATH=/path/to/arabic-font.ttf
```

> Without `FONT_PATH`, Arabic may not render perfectly depending on the system.

## 3) Run

From the repo root (after you clone it):

```bash
python media-pipeline/media_bridge.py
```

Stop with `Ctrl+C`.
