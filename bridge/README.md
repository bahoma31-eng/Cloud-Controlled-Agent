# 🌉 Local Bridge Agent

سكريبت جسر يربط جهازك المحلي بالوكيل السحابي عبر GitHub.

## 🔄 كيف يعمل

```
الوكيل السحابي (Notion/GitHub)
        ↓
يكتب مهمة في inbox/local_task.json
        ↓
الجسر المحلي يكتشف المهمة (polling)
        ↓
🛡️ يعرض لك المهمة ويطلب موافقتك
        ↓
ينفذ الأمر محلياً على جهازك
        ↓
يرفع النتيجة إلى outbox/bridge_result_*.json
        ↓
الوكيل السحابي يقرأ النتيجة
```

## ⚡ التشغيل

```bash
# تأكد من وجود .env مع GITHUB_TOKEN
python bridge/local_bridge.py
```

## 📨 صيغة ملف المهمة (local_task.json)

```json
{
    "task_id": "001",
    "description": "عرض قائمة الملفات في المجلد الحالي",
    "engine": "POWERSHELL",
    "command": "Get-ChildItem",
    "timeout": 60
}
```

### المحركات المدعومة

| المحرك | الوصف |
|--------|-------|
| `POWERSHELL` | أوامر PowerShell (Windows) |
| `BASH` | أوامر Bash (Linux/Mac) |
| `PYTHON` | كود Python مباشر |
| `CMD` | أوامر cmd (Windows) |

## 🛡️ الأمان

- **لا يُنفَّذ أي أمر بدون موافقتك الصريحة**
- يمكنك مراجعة وتعديل الأمر قبل التنفيذ
- يمكنك تخطي أي مهمة لا تثق بها
- جميع النتائج مسجلة في `outbox/`

## ⚙️ متغيرات اختيارية

| المتغير | الافتراضي | الوصف |
|---------|-----------|-------|
| `BRIDGE_POLL_SECONDS` | `10` | فترة الفحص بالثواني |
| `BRIDGE_TIMEOUT` | `120` | مهلة تنفيذ الأمر بالثواني |
