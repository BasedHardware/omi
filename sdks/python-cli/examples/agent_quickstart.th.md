# omi-cli สำหรับ AI Agent

> คู่มือเชิงปฏิบัติสำหรับสภาพแวดล้อมที่ขับเคลื่อนด้วย LLM (Claude Code, Cursor, บอทที่กำหนดเอง)

## ทำไม CLI จึงเป็นมิตรกับ Agent

* **สัญญา JSON ที่เสถียร:** แฟล็ก `--json` จะส่งออกเอกสาร JSON ที่ถูกต้องไปยัง stdout และ *เฉพาะ* JSON เท่านั้น — ไม่มีข้อความสถานะหรือสปินเนอร์ ข้อผิดพลาดจะส่งไปยัง stderr ในรูปแบบ `{"error": "...", "detail": "..."}`
* **รหัสทางออกที่เสถียร:** `0` สำเร็จ / `1` ข้อผิดพลาดในการใช้งาน / `2` การตรวจสอบสิทธิ์ล้มเหลว / `3` ข้อผิดพลาดของเซิร์ฟเวอร์ / `4` เกินขีดจำกัดอัตรา / `5` ไม่พบ Agent สามารถแยกการทำงานตามรหัสทางออกได้โดยตรงโดยไม่ต้องแยกวิเคราะห์ข้อความภาษาธรรมชาติ
* **ไม่มีพร้อมต์แบบโต้ตอบในโหมด Headless:** ส่ง `--yes` (หรือ `-y`) สำหรับคำสั่งที่มีผลกระทบ; ส่ง `--api-key` หรือตั้งค่า `OMI_API_KEY` เพื่อข้ามการเข้าสู่ระบบผ่านเบราว์เซอร์
* **พฤติกรรมการลองใหม่โดยอัตโนมัติ:** การตอบกลับ `429` และ `5xx` จะได้รับการลองใหม่โดยอัตโนมัติพร้อมการหน่วงเวลาแบบเลขชี้กำลังก่อนส่งข้อผิดพลาด

## การยืนยันตัวตน (ขั้นตอนครั้งเดียวโดยมนุษย์)

ผู้ใช้รับคีย์ API สำหรับนักพัฒนาจากเว็บแอป Omi
(`https://app.omi.me` → Developer → API Keys) แล้วรันคำสั่ง:

```bash
omi auth login                          # วางแบบโต้ตอบ คีย์จะไม่บันทึกลงในประวัติเชลล์
# หรือ
export OMI_API_KEY=omi_dev_...          # แบบชั่วคราว เหมาะสำหรับคอนเทนเนอร์และ CI/CD
```

## 5 การกระทำที่ Agent ใช้งานบ่อยที่สุด

### 1. อ่านความทรงจำ (Memories)

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

### 4. อ่านรายการสิ่งที่ต้องทำที่ค้างอยู่ (Action Items)

```bash
omi action-item list --json --open
```

### 5. ทำเครื่องหมายงานว่าเสร็จสมบูรณ์

```bash
omi action-item complete --json a1b2c3d4
```

## API เดสก์ท็อปในเครื่อง (Local Desktop API)

เมื่อ Omi Desktop เปิดใช้งาน API ภายในเครื่อง Agent จะสามารถสอบถามประวัติหน้าจอ สรุปผล SQL และงานต่างๆ ได้โดยไม่ต้องผ่าน Cloud Dev API:

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
omi --json local task complete task_1
```
