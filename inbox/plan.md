# MISSION PLAN
GOAL: ابحث عن الحزم المثبتة داخل مجلد المشروع الأول وقارنها بالحزم المثبتة داخل مجلد المشروع الثاني. حدد الحزم المشتركة الثقيلة واقترح حلاً لمشاركتها بين المشروعين لتفادي التكرار. أنشئ تقرير HTML بالنتائج.
STATE: IN_PROGRESS
UPDATED_AT: 2026-03-16T18:48:00+01:00

## STEP 1
TITLE: تحديد مجلدات المشاريع وجمع قوائم الحزم وأحجامها
STATUS: IN_PROGRESS
ENGINE: POWERSHELL
TASK_ID: 4
SUCCESS_CRITERIA:
- تحديد مسارات مجلدات المشاريع الموجودة على الجهاز.
- جمع قائمة الحزم المثبتة وأحجامها لكل مشروع.
COMMAND_HINT:
- البحث عن مجلدات المشاريع التي تحتوي على package.json.
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
- يجب الحذر من مجلدات antigravity و .gemini المحمية.
- إنشاء تقرير HTML بالنتائج.
- تم تجميع الخطوات 1-3 الأصلية في خطوة واحدة لتسريع التنفيذ.
