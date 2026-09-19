# omi-cli สำหรับ AI Agent

> คู่มือภาคปฏิบัติสำหรับการควบคุมผ่าน LLM (Claude Code, Cursor หรือบอทที่คุณพัฒนาขึ้นเอง)

## ทำไม CLI จึงเหมาะสำหรับ AI Agent

* **สัญญา JSON ที่เสถียรและแม่นยำ.** แฟล็ก `--json` จะส่งคืนเอกสาร JSON ที่ถูกต้องไปยัง stdout
  และแสดงผล*เฉพาะ*ข้อมูล JSON เท่านั้น — ไม่แสดงข้อความความคืบหน้าหรือสปินเนอร์โหลด ข้อผิดพลาดทั้งหมด
  จะถูกส่งไปยัง stderr ในรูปแบบ `{"error": "...", "detail": "..."}`
* **รหัสสถานะการออก (Exit Codes) ที่ชัดเจน.** `0` สำเร็จ / `1` การใช้งานผิดไวยากรณ์ / `2` ปัญหาการยืนยันตัวตน /
  `3` ข้อผิดพลาดจากเซิร์ฟเวอร์ / `4` เกินขีดจำกัดความถี่ (Rate Limit) / `5` ไม่พบข้อมูล Agent สามารถแตกแขนง
  การตัดสินใจตามรหัสเหล่านี้ได้ทันทีโดยไม่ต้องแยกวิเคราะห์ข้อความธรรมดา
* **ไม่มีข้อความพร้อมต์แบบโต้ตอบในบริบท Headless.** ใช้แฟล็ก `--yes` (หรือ `-y`) สำหรับคำสั่งที่อาจมีผลกระทบ;
  ส่งผ่าน `--api-key` หรือตั้งค่าตัวแปรสภาพแวดล้อม `OMI_API_KEY` เพื่อข้ามขั้นตอนการเข้าสู่ระบบแบบอินเทอร์แอคทีฟ
* **กลไกการลองใหม่อัตโนมัติ.** ข้อผิดพลาดรหัส `429` และ `5xx` จะได้รับการลองใหม่อัตโนมัติแบบหน่วงเวลา (Backoff)
  ก่อนที่จะส่งข้อผิดพลาดออกมา

## การยืนยันตัวตน (ทำครั้งเดียวโดยผู้ใช้)

ผู้ใช้สามารถรับ API Key สำหรับนักพัฒนาได้จากเว็บแอปพลิเคชัน Omi
(`https://app.omi.me` → Developer → API Keys) และดำเนินการดังนี้:

```bash
omi auth login                          # วางคีย์แบบโต้ตอบ; คีย์จะไม่ถูกบันทึกในประวัติเชลล์
# หรือ
export OMI_API_KEY=omi_dev_...          # ชั่วคราว เหมาะสำหรับระบบคอนเทนเนอร์
```

## 5 การทำงานที่ Agent ใช้งานบ่อยที่สุด

### 1. อ่านความทรงจำ (Memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. สร้างความทรงจำใหม่

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. อ่านบทสนทนา

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. อ่านรายการสิ่งที่ต้องทำที่ยังค้างอยู่

```bash
omi action-item list --json --open
```

### 5. ทำเครื่องหมายงานว่าเสร็จสมบูรณ์

```bash
omi action-item complete --json a1b2c3d4
```

## Local Desktop API

เมื่อ Omi Desktop เปิดใช้งาน API บนเครื่องโลคัล Agent จะสามารถสอบถามประวัติหน้าจอ,
บทสรุปย้อนหลัง, ฐานข้อมูล SQL และงานต่างๆ บนอุปกรณ์ได้โดยตรงโดยไม่ต้องเรียกใช้ Cloud Dev API:

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

ทำเครื่องหมายเสร็จสิ้นหรือลบงานเฉพาะเมื่อผู้ใช้สั่งการอย่างชัดเจนเท่านั้น:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

คำสั่ง `omi local screenshot SCREENSHOT_ID --output PATH` จะบันทึกภาพหน้าจอลงดิสก์
และยังคงพิมพ์เอาต์พุต JSON ไปยัง stdout สำหรับสคริปต์อัตโนมัติ รหัสภาพหน้าจอมักจะได้มาจาก
`local search-screen` หรือคำสั่ง SQL บนตาราง `screenshots` หาก Desktop ส่งคืนข้อผิดพลาด
ที่มีโครงสร้าง เช่น `screenshot_pending`, `screenshot_file_missing` หรือ
`screenshot_chunk_corrupted` โหมด JSON จะคงฟิลด์ `reason`, `hint` และ `screenshot_id`
ไว้บน stderr เพื่อให้ Agent สามารถลองใช้รหัสเดิมที่เก่ากว่าหรือรายงานปัญหาที่แท้จริงได้
ควรตรวจสอบไฟล์ที่สร้างด้วยคำสั่ง `file PATH` ก่อนส่งต่อไปยังเครื่องมือวิเคราะห์ภาพ (Vision Tools)

## ตัวอย่างการทำงานจริง: วงรอบ Agent ด้วย Python

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

## การจัดการขีดจำกัดความถี่ (Rate Limits)

ความทรงจำ: 120 ครั้ง/ชม. บทสนทนา: 25 ครั้ง/ชม. การสร้างแบบกลุ่ม: 15 ครั้ง/ชม.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## เคล็ดลับการใช้งาน

* ใช้ `--profile <name>` หาก Agent ของคุณต้องจัดการหลายบัญชี Omi พร้อมกัน แต่ละโปรไฟล์จะมีข้อมูลรับรอง
  และ API Base แยกเป็นของตัวเอง
* ใช้ `--api-base http://localhost:8080` สำหรับการทดสอบ Backend ภายในเครื่อง
* ใช้ `OMI_LOCAL_API_URL` และ `OMI_LOCAL_TOKEN` เพื่อแทนที่การตั้งค่า Desktop API ระดับโปรไฟล์ชั่วคราวในการรันครั้งเดียว
* ใช้แฟล็ก `--verbose` สำหรับการดีบัก — จะบันทึก `METHOD path → status (Ns)` ไปยัง stderr
  โดยไม่รบกวน stdout ทำให้โหมด JSON ยังคงทำงานได้อย่างถูกต้อง
* สำหรับการส่งผ่านเนื้อหาเข้าสู่บทสนทนา ให้ใช้ `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
