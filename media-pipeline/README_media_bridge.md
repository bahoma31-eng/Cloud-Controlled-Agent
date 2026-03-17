# Media Bridge (Local)

هذا السكريبت يعمل محلياً ويقوم بأتمتة خط معالجة الصور عبر GitHub.

- **Input**: `media-pipeline/input/`
- **Meta**: `media-pipeline/meta/` (ملفات JSON ناتجة عن تحليل الصورة)
- **Output**: `media-pipeline/output/` (صور PNG بالمقاسات القياسية)
- **Archive**: `media-pipeline/archive/`

التدفق:

1. تنزيل جميع الصور من `input/`
2. تشغيل سكريبت التحليل `image_watcher.py` لإنتاج ملف ميتاداتا JSON (مناطق كتابة + ألوان + سطوع + ستايل + نصوص مقترحة)
3. توليد HTML+CSS ثم تحويله إلى PNG عبر **Playwright + Chromium** (مع انتظار 3000ms لتحميل خطوط Google Fonts)
4. رفع المخرجات إلى `output/` ورفع الميتاداتا إلى `meta/`
5. نقل الصور الأصلية إلى `archive/` وحذفها من `input/`

## 1) المتطلبات

- Python 3.9+

تثبيت الاعتماديات:

```bash
pip install requests pillow python-dotenv playwright opencv-python numpy
python -m playwright install chromium
```

## 2) الإعداد

أنشئ ملف `.env` في نفس مكان التشغيل:

```env
GITHUB_TOKEN=YOUR_GITHUB_PAT
REPO_OWNER=bahoma31-eng
REPO_NAME=Cloud-Controlled-Agent
REPO_BRANCH=main
BRIDGE_POLL_SECONDS=20

# Brand
BRAND_NAME=boncoin restaurant
FACEBOOK_NAME=Boncoin restaurant
INSTAGRAM_HANDLE=boncoin_fastfood
TIKTOK_HANDLE=boncoin_fastfood
WHATSAPP_NUMBER=0795235138

# Optional copy defaults
HEADLINE_TEXT=عرض اليوم
CTA_TEXT=اطلب الآن

# Playwright
PLAYWRIGHT_WAIT_FONTS_MS=3000
```

## 3) التشغيل

```bash
python media-pipeline/media_bridge.py
```

إيقاف: `Ctrl+C`.
