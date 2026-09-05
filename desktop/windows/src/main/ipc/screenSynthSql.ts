export type ScreenSynthFrameRow = {
  ts: number
  app: string
  windowTitle: string
  processName: string
  ocrText: string
  ocrLinesJson: string | null
  height: number
}

// Keep raw OCR geometry inside the main process. The public Rewind DTO intentionally
// omits ocr_lines_json; this query is the one narrow synthesis-only read boundary.
export const SCREEN_SYNTH_FRAMES_SQL = `
  SELECT ts,
         app,
         window_title AS windowTitle,
         process_name AS processName,
         ocr_text AS ocrText,
         ocr_lines_json AS ocrLinesJson,
         height
    FROM rewind_frames
   WHERE indexed = 1 AND ts BETWEEN ? AND ?
   ORDER BY ts
`
