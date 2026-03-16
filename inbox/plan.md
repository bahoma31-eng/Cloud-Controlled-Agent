# MISSION PLAN
GOAL: تحليل ومقارنة الحزم المثبتة في مجلدي المشروعين داخل antigravity (سطح المكتب). تحديد الحزم المشتركة الثقيلة واقتراح حل لمشاركتها لتفادي التكرار. إنشاء تقرير HTML بالنتائج.
STATE: IN_PROGRESS
UPDATED_AT: 2026-03-16T19:12:00+01:00

## CLARIFICATION (RESOLVED)
- المستخدم وضّح أن مجلد antigravity على سطح المكتب يحتوي على مجلدين لمشروعين مختلفين.
- كل مشروع يحتوي على حزم مثبتة خاصة به.
- المطلوب: مقارنة الحزم بين المشروعين وتحديد المشتركة الثقيلة.
- الهدف: دراسة إمكانية دمج الحزم المشتركة في مجلد واحد لتفادي التكرار وتوفير المساحة.
- مجلد antigravity محمي — قراءة وتحليل فقط.
- مجلد .gemini محمي أيضاً.

## STEP 1
TITLE: اكتشاف المجلدين وتحديد نوع كل مشروع وقراءة ملفات الحزم
STATUS: READY
ENGINE: POWERSHELL
TASK_ID: 5
SUCCESS_CRITERIA:
- تحديد المجلدين داخل ~/Desktop/antigravity
- تحديد نوع كل مشروع (Node.js / Python / غيره)
- قراءة ملفات تعريف الحزم (package.json / requirements.txt / Pipfile)
RETRIES: 0

## STEP 2
TITLE: حساب أحجام الحزم المثبتة في كل مشروع
STATUS: READY
ENGINE: POWERSHELL
SUCCESS_CRITERIA:
- قائمة بالحزم وأحجامها لكل مشروع
- ترتيب حسب الحجم
RETRIES: 0

## STEP 3
TITLE: تحليل الحزم المشتركة وإنشاء تقرير HTML
STATUS: READY
ENGINE: PYTHON
SUCCESS_CRITERIA:
- قائمة بالحزم المشتركة بين المشروعين مع أحجامها
- تحديد التوفير المحتمل عند الدمج
- تقرير HTML يُحفظ على سطح المكتب
- اقتراحات عملية للدمج (npm workspaces / pnpm / venv مشترك)
RETRIES: 0

## NOTES
- المهمة وردت عبر البريد الإلكتروني من bahoma31@gmail.com (2026-03-16).
- مجلد antigravity محمي — قراءة فقط.
- مجلد .gemini محمي.
- التقرير يُحفظ كـ antigravity_packages_report.html على سطح المكتب.
- إرسال النتائج بالرد على البريد الإلكتروني.
