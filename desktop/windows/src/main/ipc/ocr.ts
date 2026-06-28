import { helperProcess } from '../ocr/helperProcess'
import type { OcrResult } from '../../shared/types'

/** Run Windows OCR on a JPEG frame. `jpeg` arrives as an ArrayBuffer over IPC. */
export async function ocrRecognize(jpeg: ArrayBuffer): Promise<OcrResult> {
  return helperProcess.ocr(Buffer.from(jpeg))
}
