# تصدير محادثات Omi إلى Markdown (لتطبيقات Obsidian / Notion / Second Brain)

استخدم هذا الدليل لتصدير نصوص محادثات Omi وملخصاتها إلى ملفات Markdown نظيفة ومهيكلة. تأتي الملفات الناتجة مهيأة مسبقاً بترويسة YAML (frontmatter)، وقوائم مهام قابلة للتحديد (action item checklists)، ونصوص محادثة مسجلة مع طوابع زمنية، وجاهزة للإدراج المباشر في خزينة **Obsidian** أو **Notion** أو **Logseq** أو أرشيفك الشخصي.

## المتطلبات

- بايثون 3.10+ (`Python 3.10+`)
- واجهة سطر أوامر `omi-cli` مصادق عليها (`omi auth login`)

## البدء السريع

### الخيار 1: التمرير المباشر عبر Stdin (موصى به)

اجلب أحدث محادثاتك (بما في ذلك المقاطع الصوتية الكاملة للنصوص) وصدّرها مباشرة إلى خزينة Obsidian الخاصة بك:

```bash
omi --json conversation list --include-transcript --limit 50 | python conversations_to_markdown.py - --output-dir ~/Documents/ObsidianVault/Omi/
```

### الخيار 2: التصدير من ملف JSON محفوظ

1. تصدير المحادثات إلى ملف JSON محلي:
   ```bash
   omi --json conversation list --include-transcript --limit 100 > conversations.json
   ```

2. تحويل ملف JSON المُصدَّر إلى ملاحظات Markdown فردية:
   ```bash
   python conversations_to_markdown.py conversations.json --output-dir ./notes/
   ```

### الخيار 3: تصدير محادثة محددة واحدة

```bash
omi --json conversation get <CONVERSATION_ID> --include-transcript > conversation.json
python conversations_to_markdown.py conversation.json --output-dir ./notes/
```

---

## هيكل المخرجات

تتم تسمية كل ملف مُصدَّر باستخدام النمط `YYYY-MM-DD_slugified_title_shortid.md` (على سبيل المثال `2026-09-13_ai_wearables_architecture_review_conva1b2.md`).

### نموذج لملاحظة مُصدَّرة

```markdown
---
id: "conv-a1b2c3d4-e5f6-7890-1234-56789abcdef0"
title: "AI Wearables Architecture Review"
category: "engineering"
date: "2026-09-13T10:30:00Z"
source: "omi_necklace"
tags:
  - omi
  - conversation
  - "engineering"
---

# AI Wearables Architecture Review

**Date:** 2026-09-13 10:30:00 UTC | **Category:** `engineering` | **Source:** `omi_necklace`

## Summary

Discussion on reducing latency for real-time audio transcript streaming and integrating local on-device cache for memories.

## Action Items

- [ ] Benchmark on-device Opus compression vs raw PCM
- [x] Implement exponential backoff for Redis transcript buffer reconnects

## Transcript

> **[00:00] Speaker 0:** Good morning team, let's review the audio streaming pipeline.
>
> **[00:05] Speaker 1:** We ran benchmarks on the Opus codec and observed a 60% bandwidth reduction with sub-80ms latency.
>
> **[00:12] Speaker 0:** That's fantastic. Let's document the findings and prepare the pull request.
```

---

## الميزات

- **جاهز لـ Obsidian و Notion:** يتضمن ترويسة YAML frontmatter مع وسوم (`#omi` و `#conversation` و `#<category>`) للفهرسة والتصفية التلقائية في عروض الرسم البياني (Graph view).
- **قوائم مهام تفاعلية:** يتم تحويل عناصر الإجراءات المولدة بواسطة Omi إلى مربعات اختيار قياسية في Markdown (`- [ ]` و `- [x]`).
- **نصوص محادثة بطوابع زمنية:** يتم تنسيق حوارات المحادثة كاقتباسات سهلة القراءة مع إسناد المتحدث وطوابع زمنية بتنسيق `[MM:SS]` (أو `[HH:MM:SS]` للمحادثات التي تتجاوز مدتها ساعة).
- **مكتبة قياسية نقية:** لا يتطلب أي مكتبات خارجية من طرف ثالث (لا حاجة لـ `pip install`).
- **معالجة آمنة:** يتعامل بأمان مع الحقول المفقودة، الرموز الخاصة، ترميز UTF-8 مع BOM، ويتجنب تضارب الملفات وهجمات تجاوز المسار (directory traversal).
