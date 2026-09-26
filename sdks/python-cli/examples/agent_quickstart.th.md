# omi-cli สำหรับ AI Agent

> คู่มือภาคปฏิบัติสำหรับสภาพแวดล้อมที่ควบคุมด้วย LLM (Claude Code, Cursor หรือบอทอัตโนมัติแบบกำหนดเอง)

## ทำไม CLI นี้จึงเป็นมิตรกับ Agent

* **โปรโตคอล JSON ที่เสถียร** แฟล็ก `--json` จะส่งออกเอกสาร JSON ที่ถูกต้องเพียงชุดเดียวไปยัง stdout และส่ง *เฉพาะ* เอกสาร JSON เท่านั้น — ไม่มีข้อความความคืบหน้า ไม่มีสปินเนอร์ ข้อผิดพลาดจะถูกพิมพ์ไปยัง stderr ในรูปแบบ `{"error": "...", "detail": "..."}`
* **รหัสออก (Exit codes) ที่คาดเดาได้** `0` สำเร็จ / `1` การใช้งานผิดพลาด / `2` การยืนยันตัวตนล้มเหลว / `3` ข้อผิดพลาดของเซิร์ฟเวอร์ / `4` ถูกจำกัดอัตราคำขอ (rate limited) / `5` ไม่พบทรัพยากร Agent สามารถแยกตรรกะได้โดยตรงจากรหัสออกโดยไม่ต้องแยกวิเคราะห์ภาษาธรรมชาติ
* **ไม่ใช่แบบโต้ตอบโดยค่าเริ่มต้นในสภาพแวดล้อม headless** ส่ง `--yes` (หรือ `-y`) สำหรับคำสั่งที่อาจลบข้อมูล; ส่ง `--api-key` หรือตั้งค่าตัวแปรสภาพแวดล้อม `OMI_API_KEY` เพื่อข้ามขั้นตอนการเข้าสู่ระบบแบบโต้ตอบ
* **การลองใหม่ในตัว** รหัสข้อผิดพลาด `429` และ `5xx` จะถูกลองใหม่โดยอัตโนมัติพร้อม backoff ก่อนที่จะรายงานข้อผิดพลาดไปยังผู้เรียก

## การยืนยันตัวตน (ครั้งเดียว โดยมนุษย์)

ผู้ใช้จะได้รับคีย์ API สำหรับนักพัฒนาจากเว็บแอป Omi (`https://app.omi.me` → Developer → API Keys) และดำเนินการอย่างใดอย่างหนึ่งดังต่อไปนี้:

```bash
omi auth login                          # วางแบบโต้ตอบ; คีย์จะไม่ถูกบันทึกในประวัติของเชลล์
# หรือ
export OMI_API_KEY=omi_dev_...          # ชั่วคราว เหมาะสำหรับคอนเทนเนอร์
```

## 5 สิ่งที่ Agent ใช้งานบ่อยที่สุด

### 1. อ่านความทรงจำ

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

### 4. อ่านรายการสิ่งที่ต้องทำที่ยังเปิดอยู่

```bash
omi action-item list --json --open
```

### 5. ทำเครื่องหมายรายการสิ่งที่ต้องทำว่าเสร็จสิ้น

```bash
omi action-item complete --json a1b2c3d4
```

## Local Desktop API (API บนเดสก์ท็อปในเครื่อง)

เมื่อแอปพลิเคชัน Omi Desktop เปิดใช้งาน API ภายในเครื่อง Agent สามารถอ่านประวัติหน้าจอ สรุปประจำวัน ฐานข้อมูล SQL และงานต่าง ๆ บนอุปกรณ์ได้โดยตรงโดยไม่ต้องเรียกใช้ Cloud Dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# หรือ สำหรับเซสชันชั่วคราว:
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

การดำเนินการแก้ไขภายในเครื่อง (งาน):

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

## ตัวอย่างการทำงาน: ลูป Agent ด้วย Python

```python
import json
import subprocess
import sys

def run_omi(*args: str) -> dict | list:
    """เรียกใช้ omi CLI ในโหมด JSON และสร้างข้อยกเว้นหากรหัสออกไม่ใช่ 0"""
    cmd = ["omi", "--json", *args]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # CLI จะพิมพ์ข้อผิดพลาดที่มีโครงสร้างไปยัง stderr ในโหมด JSON:
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"raw": result.stderr}
        raise RuntimeError(f"omi ล้มเหลว (exit {result.returncode}): {err}")
    return json.loads(result.stdout)

# อ่านรายการสิ่งที่ต้องทำที่เปิดอยู่ทั้งหมดและทำเครื่องหมายว่าเสร็จสิ้นหากเก่ากว่า 30 วัน
from datetime import datetime, timezone, timedelta

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = run_omi("action-item", "list", "--open")
for item in items:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        print(f"ทำเครื่องหมายเสร็จสิ้นรายการเก่า: {item['id']} ({item['description']})")
        run_omi("action-item", "complete", item["id"])
```

## การจัดการการจำกัดอัตราคำขอ (Rate Limits)

```python
if result.returncode == 4:                             # ถูกจำกัดอัตราคำขอ
    err = json.loads(result.stderr)
    # err["detail"] จะมีลักษณะเช่น: "Retry in 12s. ..."
    # omi CLI มีการลองใหม่ 3 ครั้งภายในตัวอยู่แล้ว หากยังคงได้รับรหัส 4 ให้หยุดรอตามเวลาที่ระบุ
```

ขีดจำกัดอัตราคำขอบนระบบคลาวด์สำหรับคีย์ API นักพัฒนา:
* อ่าน (GET): 120 คำขอ / นาที
* เขียน (POST/PUT/DELETE): 25 คำขอ / นาที
* การค้นหาเชิงความหมาย: 15 คำขอ / นาที

ขีดจำกัดภายในเครื่อง (หากใช้ Desktop API): ไม่มีการจำกัดอัตราเทียม ขึ้นอยู่กับประสิทธิภาพของฮาร์ดแวร์โฮสต์

## คำแนะนำและเคล็ดลับ

* ใช้ `--profile <name>` หาก Agent ของคุณสลับการทำงานระหว่างหลายบัญชี Omi (เช่น บัญชีทดสอบเทียบกับบัญชีใช้งานจริง) ข้อมูลประจำตัวจะถูกจัดเก็บแยกกันที่ `~/.config/omi/profiles/<name>.json`
* สำหรับการทดสอบหน่วยกับเซิร์ฟเวอร์จำลอง (mock): ส่ง `--api-base http://localhost:8080`
* อย่าแยกวิเคราะห์เอาต์พุต stdout ในรูปแบบข้อความธรรมดา — โครงสร้างข้อความออกแบบมาเพื่อให้มนุษย์อ่านและอาจเปลี่ยนแปลงระหว่างเวอร์ชัน ควรใช้ `--json` เสมอในสคริปต์อัตโนมัติ
