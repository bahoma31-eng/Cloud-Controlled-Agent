# MISSION PLAN
GOAL: ابحث عن الحزم المثبتة داخل مجلد المشروع الأول وقارنها بالحزم المثبتة داخل مجلد المشروع الثاني. حدد الحزم المشتركة الثقيلة واقترح حلاً لمشاركتها بين المشروعين لتفادي التكرار. أنشئ تقرير HTML بالنتائج.
STATE: PENDING
UPDATED_AT: 2026-03-16T17:44:52+00:00

## STEP 1
TITLE: تحديد مجلدات المشاريع على الجهاز
STATUS: PENDING
ENGINE: POWERSHELL
SUCCESS_CRITERIA:
- تحديد مسارات مجلدات المشاريع الموجودة على الجهاز.
COMMAND_HINT:
- البحث عن مجلدات المشاريع التي تحتوي على node_modules أو package.json.
RETRIES: 0

## STEP 2
TITLE: جمع قائمة الحزم المثبتة في المشروع الأول
STATUS: PENDING
ENGINE: POWERSHELL
SUCCESS_CRITERIA:
- الحصول على قائمة كاملة بالحزم المثبتة وأحجامها في المشروع الأول.
COMMAND_HINT:
- قراءة package.json أو فحص node_modules وحساب أحجام المجلدات.
RETRIES: 0

## STEP 3
TITLE: جمع قائمة الحزم المثبتة في المشروع الثاني
STATUS: PENDING
ENGINE: POWERSHELL
SUCCESS_CRITERIA:
- الحصول على قائمة كاملة بالحزم المثبتة وأحجامها في المشروع الثاني.
COMMAND_HINT:
- قراءة package.json أو فحص node_modules وحساب أحجام المجلدات.
RETRIES: 0

## STEP 4
TITLE: مقارنة الحزم وتحديد المشتركة الثقيلة
STATUS: PENDING
ENGINE: PYTHON
SUCCESS_CRITERIA:
- قائمة بالحزم المشتركة بين المشروعين مع أحجامها.
- تحديد الحزم الثقيلة المشتركة.
COMMAND_HINT:
- مقارنة القائمتين وترتيب الحزم المشتركة حسب الحجم.
RETRIES: 0

## STEP 5
TITLE: اقتراح حل لمشاركة الحزم وإنشاء تقرير HTML
STATUS: PENDING
ENGINE: PYTHON
SUCCESS_CRITERIA:
- تقرير HTML يحتوي على نتائج المقارنة والاقتراحات.
- اقتراح عملي (مثل npm workspaces أو symlinks أو pnpm).
COMMAND_HINT:
- إنشاء ملف HTML بالنتائج والتوصيات.
RETRIES: 0

## NOTES
- المهمة وردت عبر البريد الإلكتروني من bahoma31@gmail.com.
- يجب الحذر من مجلدات antigravity و .gemini المحمية.
- إنشاء تقرير HTML بالنتائج.
