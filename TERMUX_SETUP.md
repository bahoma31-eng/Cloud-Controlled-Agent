# TERMUX_SETUP.md — دليل تثبيت وتشغيل الجسر على Termux

هذا الملف يشرح كيفية تثبيت وتشغيل سكريبت `bridge/local_bridge.py`
على هاتف Android عبر تطبيق Termux.

---

## المتطلبات الأساسية

1. تطبيق **Termux** مثبَّت من
[F-Droid](https://f-droid.org/packages/com.termux/)
(يُفضَّل F-Droid على متجر Google Play للحصول على نسخة محدَّثة).

2. اتصال بالإنترنت لتحميل الحزم.

---

## خطوات التثبيت

### 1. تحديث مستودعات الحزم

```bash
pkg update && pkg upgrade -y
```

### 2. تثبيت Python و Git و Bash

```bash
pkg install python git bash -y
```

### 3. استنساخ المستودع

```bash
cd ~
git clone https://github.com/bahoma31-eng/Cloud-Controlled-Agent.git
cd Cloud-Controlled-Agent
```

### 4. تثبيت مكتبات Python المطلوبة

```bash
pip install requests python-dotenv
```

### 5. إنشاء ملف `.env`

```bash
cp .env.example .env   # إن وجد، أو أنشئه يدويًا
nano .env
```

أضف المتغيرات التالية داخل الملف:

```
GITHUB_TOKEN=your_personal_access_token_here
REPO_OWNER=bahoma31-eng
REPO_NAME=Cloud-Controlled-Agent
BRIDGE_BRANCH=main
BRIDGE_POLL_SECONDS=10
BRIDGE_TIMEOUT=120

# مسار CodeAnalyzer (اختياري — فقط إن كنت تستخدم محرك ANALYZER)
CODE_ANALYZER_PATH=~/CodeAnalyzer
```

> **ملاحظة حول التوكن:** يجب أن يكون
> `GITHUB_TOKEN` توكن Personal Access Token بصلاحيات
> `repo` (Contents: read & write).

---

## تشغيل الجسر

```bash
cd ~/Cloud-Controlled-Agent
python bridge/local_bridge.py
```

ستظهر رسالة بدء مشابهة لهذه:

```
======================================================================
  Local Bridge Agent V2.3 - Termux/Android Edition
----------------------------------------------------------------------
  Repo      : bahoma31-eng/Cloud-Controlled-Agent
  Task file : inbox/local_task.json
  Polling   : every 10s
  Timeout   : 120s
  Branch    : main
  Analyzer  : ~/CodeAnalyzer

  >> Auto-execute enabled.
  >> Approval happens in Notion, not here.
  >> Engines: PYTHON | BASH | ANALYZER
  >> Press Ctrl+C to stop.
======================================================================
```

---

## المحركات المدعومة

| المحرك     | الوصف                                         | الأمر لتثبيته        |
|------------|-----------------------------------------------|----------------------|
| `PYTHON`   | تنفيذ كود Python مباشرةً                      | `pkg install python` |
| `BASH`     | تنفيذ أوامر Bash/Shell                        | `pkg install bash`   |
| `ANALYZER` | تحليل مجلد/مستودع باستخدام CodeAnalyzer       | راجع القسم أدناه     |

> **ملاحظة:** محركا `POWERSHELL` و `CMD` غير مدعومَين في Termux وتم حذفهما من هذه النسخة.

---

## إعداد CodeAnalyzer (اختياري)

إن أردت استخدام محرك `ANALYZER`، ضع أداة CodeAnalyzer الخاصة بك في المسار الافتراضي:

```bash
cd ~
mkdir -p CodeAnalyzer
# انسخ ملف code_analyzer.py الخاص بك إلى هذا المجلد
cp /path/to/code_analyzer.py ~/CodeAnalyzer/
```

أو حدِّد مسارًا مخصصًا في `.env`:

```
CODE_ANALYZER_PATH=~/MyAnalyzer
```

---

## تشغيل الجسر في الخلفية (اختياري)

لتشغيل الجسر في الخلفية دون إبقاء جلسة Termux مفتوحة، استخدم
`nohup` أو `screen`:

```bash
# باستخدام nohup
nohup python bridge/local_bridge.py > ~/bridge.log 2>&1 &
echo "PID: $!"

# أو باستخدام screen
pkg install screen -y
screen -S bridge
python bridge/local_bridge.py
# اضغط Ctrl+A ثم D للانفصال عن الجلسة
```

لإعادة الاتصال بجلسة screen:

```bash
screen -r bridge
```

---

## استكشاف الأخطاء

| المشكلة | الحل |
|---------|------|
| `GITHUB_TOKEN is missing` | تأكد من وجود `.env` وصحة التوكن |
| `Engine 'PYTHON' not found` | شغِّل `pkg install python` |
| `Engine 'BASH' not found` | شغِّل `pkg install bash` |
| `CodeAnalyzer directory not found` | تحقق من `CODE_ANALYZER_PATH` في `.env` |
| خطأ في الصلاحيات | شغِّل `chmod +x bridge/local_bridge.py` |

---

## ملاحظات أمنية

- لا تشارك ملف `.env` أو قيمة `GITHUB_TOKEN` مع أي أحد.
- استخدم توكنًا بأدنى الصلاحيات اللازمة فقط.
- راجع الأوامر الواردة في ملف المهمة قبل الموافقة عليها في Notion.
