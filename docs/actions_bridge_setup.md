# Actions Bridge — دليل الإعداد والاستخدام

## نظرة عامة

`bridge/actions_bridge.py` هو نسخة محسّنة من `bridge/local_bridge.py` مصمّمة
للعمل داخل **GitHub Actions** بدلاً من الجهاز المحلي.

الفروقات الرئيسية عن النسخة المحلية:

| الميزة | local_bridge.py | actions_bridge.py |
|--------|-----------------|-------------------|
| آلية التشغيل | Polling كل 10 ثوان | Single-run عند كل workflow trigger |
| GITHUB_TOKEN | ملف .env | GitHub Secrets تلقائياً |
| نظام التشغيل | Windows / Linux / Mac | Ubuntu (GitHub-hosted runner) |
| POWERSHELL | native | يُحوَّل تلقائياً إلى BASH |
| CMD | مدعوم | غير مدعوم (Linux) |
| python | python / py | python3 / python |

---

## الإعداد

### 1. Secrets المطلوبة

لا تحتاج إلى إضافة أي secret يدوياً — `GITHUB_TOKEN` يُحقن تلقائياً بواسطة
GitHub Actions في كل workflow run.

إن أردت دعم محرك **ANALYZER**، أضف secret اختيارياً:

```
Settings → Secrets and variables → Actions → New repository secret

Name : CODE_ANALYZER_PATH
Value: /path/to/CodeAnalyzer  (مسار على runner أو على artifact مرفوع مسبقاً)
```

### 2. الـ Workflow

الملف `.github/workflows/run_bridge.yml` يُطلَق تلقائياً عند:

- **push** يغيّر `inbox/local_task.json` (يحدث عند كتابة task جديد)
- **workflow_dispatch** (تشغيل يدوي من صفحة Actions في GitHub)

لا حاجة لأي إعداد إضافي.

---

## كيفية الاستخدام

### 1. إنشاء task جديد

اكتب ملف JSON في `inbox/local_task.json` بالصيغة التالية وادفعه إلى الـ branch:

```json
{
  "task_id": "task_001",
  "engine": "BASH",
  "command": "echo 'Hello from GitHub Actions!' && ls -la",
  "description": "اختبار بسيط",
  "timeout": 60
}
```

### 2. انتظر تشغيل الـ Workflow

بعد الـ push، يُطلَق workflow تلقائياً ويمكن متابعته من:

```
Repository → Actions → Run Actions Bridge
```

### 3. قراءة النتيجة

بعد انتهاء الـ workflow، تجد النتيجة في `outbox/bridge_result_<timestamp>.json`:

```json
{
  "task_id": "task_001",
  "status": "SUCCESS",
  "return_code": 0,
  "engine": "BASH",
  "description": "اختبار بسيط",
  "command_preview": "echo 'Hello from GitHub Actions!' && ls -la",
  "output": "Hello from GitHub Actions!\n...",
  "timestamp": "2025-01-01T00:00:00+00:00",
  "executed_on": "github_actions",
  "repo": "bahoma31-eng/Cloud-Controlled-Agent",
  "bridge_version": "3.0"
}
```

ويُعاد تصفير `inbox/local_task.json` إلى `waiting` تلقائياً.

---

## المحركات المدعومة

| Engine | الوصف | ملاحظة |
|--------|-------|--------|
| `PYTHON` | تنفيذ كود Python | يستخدم python3 |
| `BASH` | تنفيذ أوامر Bash | الأمثل لبيئة Linux |
| `POWERSHELL` | تنفيذ أوامر PowerShell | يُحوَّل تلقائياً إلى BASH على Linux |
| `CMD` | أوامر Windows CMD | **غير مدعوم** على GitHub Actions |
| `ANALYZER` | تحليل كود بـ CodeAnalyzer | يتطلب secret: CODE_ANALYZER_PATH |

---

## أمثلة على Tasks

### PYTHON
```json
{
  "task_id": "py_001",
  "engine": "PYTHON",
  "command": "import platform; print(platform.uname())",
  "description": "طباعة معلومات النظام"
}
```

### BASH
```json
{
  "task_id": "bash_001",
  "engine": "BASH",
  "command": "pip install requests && python3 -c \"import requests; print(requests.__version__)\"",
  "description": "تثبيت مكتبة واختبارها"
}
```

### POWERSHELL (يُحوَّل إلى BASH)
```json
{
  "task_id": "ps_001",
  "engine": "POWERSHELL",
  "command": "Get-Location",
  "description": "طباعة المسار الحالي — سيُنفَّذ كـ bash"
}
```

---

## التشغيل اليدوي

من صفحة GitHub Actions:

```
Repository → Actions → Run Actions Bridge → Run workflow
```

يمكنك تحديد الـ branch المراد استخدامه (الافتراضي: `main`).

---

## استكشاف الأخطاء

| المشكلة | السبب | الحل |
|---------|-------|-------|
| `GITHUB_TOKEN is missing` | لم يُمرَّر التوكن | تأكد من وجود `env: GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}` في الـ workflow |
| `No pending task found` | `inbox/local_task.json` فارغ أو `waiting` | ادفع task جديداً بصيغة JSON صحيحة |
| `Engine 'CMD' not supported` | CMD لا يعمل على Linux | استخدم `BASH` أو `PYTHON` بدلاً من `CMD` |
| نتيجة لم تُرفع | صلاحيات الـ token | تأكد من `permissions: contents: write` في الـ workflow |

---

## ملاحظات أمنية

- **لا تضع أسراراً** (API keys, passwords) مباشرةً في `inbox/local_task.json`
  لأن الملف يُدفع إلى الـ repository ويبقى في التاريخ.
- استخدم **GitHub Secrets** لتمرير القيم الحسّاسة عبر environment variables.
- الـ `GITHUB_TOKEN` المُستخدم هو توكن مؤقت يصلح لـ run واحد فقط.
