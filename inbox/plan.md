# MISSION PLAN
GOAL: ابحث عن الحزم المثبتة داخل مجلد antigravity (سطح المكتب) وقارنها بالحزم المثبتة داخل مجلد المشروع الثاني (لم يُحدد بعد). حدد الحزم المشتركة الثقيلة واقترح حلاً لمشاركتها بين المشروعين لتفادي التكرار. أنشئ تقرير HTML بالنتائج.
STATE: WAITING_FOR_INFO
UPDATED_AT: 2026-03-16T18:50:00+01:00

## CLARIFICATION
- المستخدم وضّح أن "المشروع الأول" هو مجلد antigravity الموجود على سطح المكتب.
- مجلد antigravity محمي (يُستخدم بواسطة Google Antigravity) — يُسمح بالقراءة والتحليل فقط، بدون حذف أو تعديل.
- ⚠️ لم يُحدد المستخدم "المشروع الثاني" بعد — في انتظار التوضيح.

## STEP 1
TITLE: تحديد مجلدات المشاريع وجمع قوائم الحزم وأحجامها
STATUS: BLOCKED (في انتظار تحديد المشروع الثاني)
ENGINE: POWERSHELL
TASK_ID: 4
SUCCESS_CRITERIA:
- تحديد مسارات مجلدات المشاريع الموجودة على الجهاز.
- المشروع الأول: ~/Desktop/antigravity
- المشروع الثاني: ❓ في انتظار التوضيح
- جمع قائمة الحزم المثبتة وأحجامها لكل مشروع.
COMMAND_HINT:
- البحث عن package.json داخل مجلد antigravity على سطح المكتب.
- قراءة dependencies و devDependencies من كل package.json.
- حساب أحجام مجلدات node_modules.
RETRIES: 0

## STEP 2
TITLE: مقارنة الحزم وتحديد المشتركة الثقيلة
STATUS: PENDING
ENGINE: PYTHON
SUCCESS_CRITERIA:
- قائمة بالحزم المشتركة بين المشروعين مع أحجامها.
- تحديد الحزم الثقيلة المشتركة.
COMMAND_HINT:
- مقارنة القائمتين وترتيب الحزم المشتركة حسب الحجم.
RETRIES: 0

## STEP 3
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
- مجلد antigravity محمي — قراءة فقط، بدون حذف أو تعديل.
- مجلد .gemini محمي أيضاً.
- إنشاء تقرير HTML بالنتائج.
- ⏸️ المهمة متوقفة في انتظار تحديد المشروع الثاني.
