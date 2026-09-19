# omi-cli สำหรับ Agent

> คู่มือปฏิบัติการสำหรับสภาพแวดล้อมที่ขับเคลื่อนด้วย LLM (Claude Code, Cursor, บอทของคุณเอง)

## ทำไม CLI ถึงเหมาะสำหรับ Agent

* **สัญญา JSON ที่เสถียร** ตัวเลือก `--json` จะส่งออกเอกสาร JSON ที่ถูกต้องไปยัง stdout และมี *เฉพาะ* เอกสาร JSON เท่านั้น — ไม่มีข้อความแสดงความคืบหน้าหรือสัญลักษณ์โหลด ข้อผิดพลาดจะถูกส่งไปยัง stderr ในรูปแบบ `{"error": "...", "detail": "..."}`
* **รหัสออกจากโปรแกรม (Exit Codes) ที่เสถียร** `0` สำเร็จ / `1` ข้อผิดพลาดในการใช้งาน / `2` การยืนยันตัวตน / `3` เซิร์ฟเวอร์ / `4` ติดขีดจำกัดความถี่ / `5` ไม่พบ Agent สามารถแยกการทำงานตามรหัสเหล่านี้ได้โดยไม่ต้องแยกวิเคราะห์ข้อความภาษาธรรมชาติ
* **ไม่มีคำถามโต้ตอบในบริบทแบบ Headless** ส่ง `--yes` (หรือ `-y`) ไปกับคำสั่งที่อาจลบข้อมูล ส่ง `--api-key` หรือตั้งค่า `OMI_API_KEY` เพื่อข้ามการเข้าสู่ระบบแบบโต้ตอบ
* **พฤติกรรมการลองใหม่ที่ยืดหยุ่น** ข้อผิดพลาด `429` และ `5xx` จะถูกลองใหม่โดยอัตโนมัติพร้อมการหน่วงเวลาแบบ exponential backoff ก่อนที่จะแสดงข้อผิดพลาด

## การยืนยันตัวตน (ทำครั้งเดียวโดยผู้ใช้)

ผู้ใช้รับคีย์ API สำหรับนักพัฒนาจากเว็บแอป Omi (`https://app.omi.me` → Developer → API Keys) และเลือกอย่างใดอย่างหนึ่งดังนี้:

```bash
omi auth login                          # วางแบบโต้ตอบ คีย์จะไม่ถูกบันทึกในประวัติของเชลล์
# หรือ
export OMI_API_KEY=omi_dev_...          # ชั่วคราว เหมาะสำหรับคอนเทนเนอร์
```

## 5 สิ่งที่ Agent ทำบ่อยที่สุด

### 1. อ่านความทรงจำ

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. สร้างความทรงจำ

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. อ่านบทสนทนา

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. อ่านรายการสิ่งที่ต้องทำที่เปิดอยู่

```bash
omi action-item list --json --open
```

### 5. ทำเครื่องหมายรายการสิ่งที่ต้องทำว่าเสร็จสิ้น

```bash
omi action-item complete --json a1b2c3d4
```

## Desktop API ภายในเครื่อง

เมื่อ Omi Desktop เปิดใช้งาน API ภายในเครื่อง Agent สามารถสืบค้นประวัติหน้าจอบนอุปกรณ์ สรุปข้อมูล คำสั่ง SQL และงานต่างๆ ได้โดยไม่ต้องใช้ dev API บนคลาวด์:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# หรือสำหรับเซสชันชั่วคราว:
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

เสร็จสิ้นหรือลบงานเมื่อผู้ใช้ร้องขออย่างชัดเจนเท่านั้น:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` จะบันทึกภาพหน้าจอลงดิสก์และยังคงส่งออก JSON ไปยัง stdout สำหรับสคริปต์ รหัสภาพหน้าจอมักจะมาจาก `local search-screen` หรือคำสั่ง SQL บนตาราง `screenshots` หาก Desktop ส่งกลับข้อผิดพลาดที่มีโครงสร้าง เช่น `screenshot_pending`, `screenshot_file_missing` หรือ `screenshot_chunk_corrupted` โหมด JSON จะรักษาฟิลด์ `reason`, `hint` และ `screenshot_id` ไว้บน stderr เพื่อให้ Agent สามารถลองใหม่ด้วย ID เดิมหรือรายงานปัญหาที่แท้จริง ตรวจสอบความถูกต้องของไฟล์ด้วย `file PATH` ก่อนส่งไปยังเครื่องมือประมวลผลภาพ

## ตัวอย่างการใช้งาน: ลูป Agent ภาษา Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """เรียกใช้ omi CLI ในโหมด JSON และสร้างข้อยกเว้นเมื่อรหัสออกจากโปรแกรมไม่สำเร็จ"""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI จะพิมพ์ข้อผิดพลาดที่มีโครงสร้างไปยัง stderr ในโหมด JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi ออกจากโปรแกรมด้วยรหัส {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# อ่านรายการสิ่งที่ต้องทำที่เปิดอยู่ทั้งหมดและทำเครื่องหมายรายการที่เก่ากว่า 30 วันว่าเสร็จสิ้น
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## การจัดการขีดจำกัดความถี่ (Rate Limits)

ความทรงจำ: 120/ชม. บทสนทนา: 25/ชม. สร้างเป็นชุด: 15/ชม.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # ติดขีดจำกัดความถี่
    err = json.loads(result.stderr)
    # err["detail"] มีลักษณะเช่น: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## เคล็ดลับ

* ใช้ `--profile <ชื่อ>` หาก Agent ของคุณจัดการบัญชี Omi หลายบัญชี แต่ละโปรไฟล์จะมีข้อมูลรับรองและ URL ฐานของ API ของตัวเอง
* ใช้ `--api-base http://localhost:8080` สำหรับการทดสอบแบ็กเอนด์ภายในเครื่อง
* ใช้ `OMI_LOCAL_API_URL` และ `OMI_LOCAL_TOKEN` เพื่อแทนที่การตั้งค่า Desktop API สำหรับการรันหนึ่งครั้ง
* ใช้ `--verbose` สำหรับการดีบัก — จะบันทึก `METHOD path → status (Ns)` ไปยัง stderr โดยไม่ส่งผลกระทบต่อ stdout ทำให้โหมด JSON ยังคงถูกต้อง
* สำหรับการส่งเนื้อหาเข้าสู่บทสนทนาผ่าน pipe ให้ใช้ `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
