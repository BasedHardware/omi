# omi-cli สำหรับเอเจนต์

> คู่มือภาคปฏิบัติสำหรับ LLM-driven harnesses (Claude Code, Cursor บอทของคุณเอง)

## ทำไม CLI ถึงเป็นมิตรกับเอเจนต์

* **สัญญา JSON คงที่** `--json` ส่งเอกสาร JSON ที่ถูกต้องไปยัง stdout และ
  *เฉพาะ* เอกสาร JSON เท่านั้น — ไม่มีข้อความความคืบหน้า ไม่มี spinners ข้อผิดพลาดไปที่
  stderr เป็น `{"error": "...", "detail": "..."}`.
* **รหัส exit คงที่** `0` ok / `1` usage / `2` auth / `3` server / `4`
  rate limited / `5` ไม่พบ เอเจนต์สามารถแตกกิ่งบนสิ่งเหล่านี้ได้โดยไม่ต้องแยกวิเคราะห์
  ข้อผิดพลาดภาษาธรรมชาติ
* **ไม่มี prompt เชิงโต้ตอบในบริบท headless** ส่ง `--yes` (หรือ `-y`) ไปยัง
  คำสั่งทำลายล้าง ส่ง `--api-key` หรือตั้ง `OMI_API_KEY` เพื่อข้าม
  การเข้าสู่ระบบเชิงโต้ตอบ
* **พฤติกรรม retry ที่ให้อภัย** `429` และ `5xx` จะลองใหม่พร้อม backoff
  ก่อนแสดงผล

## Auth (ครั้งเดียว โดยมนุษย์)

ผู้ใช้รับ API key สำหรับนักพัฒนาจากแอปเว็บ Omi
(`https://app.omi.me` → Developer → API Keys) และอย่างใดอย่างหนึ่ง:

```bash
omi auth login                          # interactive paste; key not in shell history
# or
export OMI_API_KEY=omi_dev_...          # ephemeral, container-friendly
```

## ห้าสิ่งที่เอเจนต์ทำบ่อยที่สุด

### 1. อ่าน memories

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. สร้าง memory

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. อ่าน conversations

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. อ่าน action items ที่เปิดอยู่

```bash
omi action-item list --json --open
```

### 5. ทำเครื่องหมาย action item ว่าเสร็จแล้ว

```bash
omi action-item complete --json a1b2c3d4
```

## Local Desktop API

เมื่อ Omi Desktop เปิด API ท้องถิ่น เอเจนต์สามารถสอบถามประวัติหน้าจอ
บนอุปกรณ์ recap, SQL และงาน โดยไม่ใช้ cloud dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# or, for ephemeral sessions:
export OMI_LOCAL_API_URL=http://127.0.0.1:47778
export OMI_LOCAL_TOKEN=...

omi --json local status
omi --json local tools
omi --json local call search_screen_history --args-json '{"query":"pricing page","days":7}'
omi --json local search-screen "pricing page" --days 7 --app Safari
omi --json local screenshot 123 --output /tmp/omi-shot.jpg
omi --json local sql "SELECT COUNT(*) AS screenshots FROM screenshots"
omi --json local task search "taxes" --include-completed
```

เสร็จสิ้นหรือลบงานเฉพาะเมื่อผู้ใช้ขออย่างชัดเจน:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` เขียนภาพหน้าจอลงดิสก์
และยังคงพิมพ์ JSON ไปยัง stdout สำหรับสคริปต์ ID ของภาพหน้าจอโดยทั่วมาจาก
`local search-screen` หรือ SQL บนตาราง `screenshots` ถ้า Desktop ส่งคืน
ความล้มเหลวที่มีโครงสร้างเช่น `screenshot_pending`, `screenshot_file_missing`
หรือ `screenshot_chunk_corrupted` JSON mode จะเก็บฟิลด์ `reason`, `hint` และ
`screenshot_id` ไว้บน stderr เพื่อให้เอเจนต์ลอง ID เก่ากว่าหรือรายงาน
สิ่งกีดขวางที่แน่นอน ตรวจสอบเอาต์พุตที่สำเร็จด้วย `file PATH` ก่อนส่งต่อ
ไปยังเครื่องมือ vision

## ตัวอย่างที่ใช้งานได้: Python agent loop

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invoke the omi CLI in JSON mode, raising on non-success exit codes."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # The CLI prints structured errors to stderr in JSON mode:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Read all open action items and mark anything older than 30 days complete.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## การจัดการ rate limits

Memories: 120/ชั่วโมง Conversations: 25/ชั่วโมง Batch creates: 15/ชั่วโมง

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## เคล็ดลับ

* ใช้ `--profile <name>` ถ้าเอเจนต์ของคุณจัดการบัญชี Omi หลายบัญชี แต่ละ
  profile มี credential และ API base ของตัวเอง
* ใช้ `--api-base http://localhost:8080` สำหรับการทดสอบ backend ท้องถิ่น
* ใช้ `OMI_LOCAL_API_URL` และ `OMI_LOCAL_TOKEN` เพื่อแทนที่การตั้งค่า
  Desktop API แบบ profile-local สำหรับหนึ่งการรัน
* ใช้ `--verbose` สำหรับดีบัก — มันบันทึก `METHOD path → status (Ns)` ไป stderr
  โดยไม่กระทบ stdout ดังนั้น JSON mode ยังคงถูกต้อง
* สำหรับป้อนเนื้อหาเข้าสู่ conversation ใช้ `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
