# ☁️ Cloud Controlled Agent V13 (Modular)

وكيل سحابي ذكي يعمل بحلقة **Supervisor → Planner → Worker → Judge**، يتحكم في مستودع GitHub عن بُعد وينفذ المهام تلقائيًا.

## 🏗️ البنية المعمارية

```
Cloud-Controlled-Agent/
├── agent/                  # الوحدات الأساسية
│   ├── config.py           # الإعدادات والمتغيرات
│   ├── github_api.py       # عميل GitHub API
│   ├── llm_client.py       # عميل الذكاء الاصطناعي (Groq / GitHub Models)
│   ├── prompts.py          # جميع البرومبتات مركزيًا
│   ├── plan_engine.py      # تحليل وتوليد الخطط
│   ├── supervisor.py       # منطق الإشراف والتقييم
│   ├── worker.py           # تنفيذ المهام (PowerShell / Python)
│   ├── state.py            # إدارة الحالة
│   └── ui.py               # واجهة الطرفية
├── inbox/                  # ملفات المهام والخطط
├── outbox/                 # تقارير التنفيذ
├── logs/                   # سجلات الأخطاء
├── main.py                 # نقطة الدخول
├── requirements.txt        # المكتبات المطلوبة
└── .env.example            # نموذج متغيرات البيئة
```

## ⚡ التشغيل السريع

```bash
# 1. نسخ ملف البيئة وتعبئة القيم
cp .env.example .env

# 2. تثبيت المكتبات
pip install -r requirements.txt

# 3. تشغيل الوكيل
python main.py
```

## 🔄 دورة العمل

1. **المستخدم** يكتب المهمة في `inbox/task_mothor.txt`
2. **المشرف (Supervisor)** يقرأ المهمة ويولّد خطة في `inbox/plan.md`
3. **المخطط (Planner)** يحوّل كل خطوة إلى أمر قابل للتنفيذ
4. **العامل (Worker)** ينفذ الأمر ويكتب التقرير في `outbox/`
5. **المُقيّم (Judge)** يقيّم النتيجة: ناجح أو إعادة محاولة
6. تتكرر الدورة حتى اكتمال المهمة

## 🛡️ الأمان

- لا تُرسل ملف `.env` إلى المستودع أبدًا
- التوكنات تُقرأ من متغيرات البيئة فقط
- الأكواد المُولّدة تُنفذ في بيئة معزولة مؤقتة

## 📝 الترخيص

MIT License
