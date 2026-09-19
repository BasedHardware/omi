# omi-cli สำหรับเอเจนต์ (Agents)

> คู่มือการใช้งานจริงสำหรับระบบที่ขับเคลื่อนด้วย LLM (Claude Code, Cursor, บอทของคุณเอง)

## ทำไม CLI นี้จึงเหมาะสำหรับเอเจนต์

* **สัญญา JSON ที่เสถียร** `--json` จะส่งออกเอกสาร JSON ที่ถูกต้องไปยัง stdout และ
  *เฉพาะ* เอกสาร JSON เท่านั้น — ไม่มีการแจ้งเตือนความคืบหน้า ไม่มีสปินเนอร์ ข้อผิดพลาดจะถูกส่งไปยัง
  stderr ในรูปแบบ `{"error": "...", "detail": "..."}`
* **รหัสออก (Exit Codes) ที่เสถียร** `0` สำเร็จ / `1` การใช้งานผิดวิธี / `2` การยืนยันตัวตนล้มเหลว / `3` ข้อผิดพลาดของเซิร์ฟเวอร์ / `4` ติดขีดจำกัดอัตราคำขอ / `5` ไม่พบข้อมูล เอเจนต์สามารถแยกเงื่อนไขการทำงานได้ทันทีโดยไม่ต้องแปลภาษาธรรมชาติ
* **ไม่มีข้อความถามตอบในบริบทอัตโนมัติ** ส่ง `--yes` (หรือ `-y`) สำหรับคำสั่งที่มีผลกระทบสูง
  ส่ง `--api-key` หรือตั้งค่า `OMI_API_KEY` เพื่อข้ามการเข้าสู่ระบบแบบโต้ตอบ
* **พฤติกรรมการลองใหม่ที่ยืดหยุ่น** รหัส `429` และ `5xx` จะถูกลองใหม่โดยอัตโนมัติพร้อมการหน่วงเวลาก่อนที่จะแสดงข้อผิดพลาด

## การยืนยันตัวตน (ทำเพียงครั้งเดียวโดยมนุษย์)

ผู้ใช้ขอรับคีย์ API สำหรับนักพัฒนาจากเว็บแอป Omi
(`https://app.omi.me` → Developer → API Keys) และเลือกอย่างใดอย่างหนึ่ง:

```bash
omi auth login                          # วางแบบโต้ตอบ; คีย์จะไม่ถูกบันทึกในประวัติเชลล์
# หรือ
export OMI_API_KEY=omi_dev_...          # แบบชั่วคราว เหมาะสำหรับสภาพแวดล้อมคอนเทนเนอร์
```

## 5 สิ่งที่เอเจนต์ทำบ่อยที่สุด

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

### 4. อ่านรายการสิ่งที่ต้องทำที่ยังเปิดอยู่

```bash
omi action-item list --json --open
```

### 5. ทำเครื่องหมายรายการสิ่งที่ต้องทำว่าเสร็จสิ้น

```bash
omi action-item complete --json a1b2c3d4
```

## Desktop API บนเครื่องท้องถิ่น

เมื่อ Omi Desktop เปิดใช้งาน API ภายในเครื่อง เอเจนต์สามารถค้นหาประวัติหน้าจอ สรุปข้อมูล
SQL และงานต่างๆ บนอุปกรณ์ได้โดยไม่ต้องเรียกใช้ Cloud API:

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

ทำเครื่องหมายว่าเสร็จสิ้นหรือลบงานต่อเมื่อผู้ใช้ร้องขออย่างชัดเจนเท่านั้น:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

คำสั่ง `omi local screenshot SCREENSHOT_ID --output PATH` จะบันทึกภาพหน้าจอลงดิสก์
และยังคงส่งออก JSON ไปยัง stdout สำหรับสคริปต์ รหัสภาพหน้าจอมักได้มาจาก
`local search-screen` หรือคำสั่ง SQL บนตาราง `screenshots` หาก Desktop
ส่งคืนข้อผิดพลาดเชิงโครงสร้าง เช่น `screenshot_pending`, `screenshot_file_missing`
หรือ `screenshot_chunk_corrupted` โหมด JSON จะคงฟิลด์ `reason`, `hint` และ
`screenshot_id` ไว้ใน stderr เพื่อให้เอเจนต์สามารถลองใหม่ด้วยรหัสที่เก่ากว่าหรือรายงานปัญหาที่แท้จริง
ตรวจสอบความถูกต้องของไฟล์ผลลัพธ์ด้วย `file PATH` ก่อนส่งไปยังโมเดลวิเคราะห์ภาพ

## ตัวอย่างการทำงาน: ลูปของเอเจนต์ใน Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """เรียกใช้ omi CLI ในโหมด JSON และสร้างข้อยกเว้นหากรหัสออกไม่เป็นศูนย์"""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI จะส่งออกข้อผิดพลาดเชิงโครงสร้างไปยัง stderr ในโหมด JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# อ่านรายการสิ่งที่ต้องทำทั้งหมดและทำเครื่องหมายสิ่งที่เก่ากว่า 30 วันว่าเสร็จสิ้น
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## การจัดการขีดจำกัดอัตราคำขอ (Rate Limits)

ความทรงจำ: 120/ชม. บทสนทนา: 25/ชม. การสร้างเป็นชุด: 15/ชม.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # ติดขีดจำกัดอัตราคำขอ
    err = json.loads(result.stderr)
    # err["detail"] จะมีลักษณะเช่น: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## เคล็ดลับ

* ใช้ `--profile <ชื่อ>` หากเอเจนต์ของคุณจัดการหลายบัญชี Omi แต่ละโปรไฟล์
  จะมีข้อมูลประจำตัวและที่อยู่ API แยกกัน
* ใช้ `--api-base http://localhost:8080` สำหรับการทดสอบกับเซิร์ฟเวอร์แบ็กเอนด์ภายในเครื่อง
* ใช้ `OMI_LOCAL_API_URL` และ `OMI_LOCAL_TOKEN` เพื่อแทนที่การตั้งค่า Desktop API
  สำหรับรอบการทำงานเดี่ยว
* ใช้ `--verbose` สำหรับการดีบัก — ระบบจะบันทึก `METHOD path → status (Ns)` ลงใน stderr
  โดยไม่กระทบต่อ stdout ทำให้รูปแบบ JSON ยังคงถูกต้อง
* หากต้องการส่งเนื้อหาเข้าสู่บทสนทนาผ่านไปป์ ให้ใช้ `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
