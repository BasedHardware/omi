//! macOS-native OCR via Apple Vision (`VNRecognizeTextRequest`).
//!
//! Vision is what powers Live Text — it's trained on screen-rendered glyphs
//! and dramatically outperforms PaddleOCR's `latin_rec` (a natural-scene
//! model) on UI screenshots. It's free, in-process, and ships in macOS
//! 10.15+, so no models to bundle.
//!
//! We talk to Vision through raw `msg_send!` calls against existing
//! objc2 0.5 — the typed `objc2-vision` crate requires objc2 0.6 and a
//! cascade of framework crates we don't otherwise need.
//!
//! Threading: Vision's `perform:error:` is synchronous and safe to call
//! from any thread (including a tokio blocking worker), so we don't need
//! a dispatch hop.

use crate::ocr::{OcrTextBlock, OcrTextResult};
use objc2::class;
use objc2::encode::{Encode, Encoding, RefEncode};
use objc2::msg_send;
use objc2::rc::Retained;
use objc2::runtime::{AnyObject, Bool};
use objc2_foundation::{NSArray, NSData, NSDictionary, NSString};

/// Run Vision OCR on a JPEG buffer and return blocks + concatenated text.
///
/// Bounding boxes are converted from Vision's normalized
/// (origin bottom-left, 0..1) into pixel coordinates with origin top-left
/// to match the cross-platform `OcrTextBlock` contract used by the JS layer.
pub fn extract_text(jpeg_data: &[u8]) -> Result<OcrTextResult, String> {
    // Need image dimensions to denormalize Vision's bbox coords. Cheapest
    // way is to peek the JPEG header without decoding pixels.
    let (img_w, img_h) = image::ImageReader::with_format(
        std::io::Cursor::new(jpeg_data),
        image::ImageFormat::Jpeg,
    )
    .into_dimensions()
    .map_err(|e| format!("Failed to read JPEG dimensions: {}", e))?;

    unsafe {
        // --- Build VNImageRequestHandler from JPEG data ---
        let ns_data = NSData::with_bytes(jpeg_data);
        let empty_options: Retained<NSDictionary<NSString, AnyObject>> = NSDictionary::new();

        let handler_cls = class!(VNImageRequestHandler);
        let handler_alloc: *mut AnyObject = msg_send![handler_cls, alloc];
        let handler: *mut AnyObject = msg_send![
            handler_alloc,
            initWithData: &*ns_data,
            options: &*empty_options
        ];
        if handler.is_null() {
            return Err("VNImageRequestHandler init returned nil".to_string());
        }
        // Take ownership so the handler is released when this scope exits.
        let handler: Retained<AnyObject> = Retained::from_raw(handler)
            .ok_or_else(|| "VNImageRequestHandler retain failed".to_string())?;

        // --- Build VNRecognizeTextRequest ---
        let request_cls = class!(VNRecognizeTextRequest);
        let request_alloc: *mut AnyObject = msg_send![request_cls, alloc];
        // init (no completion handler — we read `results` synchronously after perform).
        let request: *mut AnyObject = msg_send![request_alloc, init];
        if request.is_null() {
            return Err("VNRecognizeTextRequest init returned nil".to_string());
        }
        let request: Retained<AnyObject> = Retained::from_raw(request)
            .ok_or_else(|| "VNRecognizeTextRequest retain failed".to_string())?;

        // VNRequestTextRecognitionLevel: accurate = 0, fast = 1.
        // .fast garbles dense small text (terminals, IDEs, logs): r→p, M→fff,
        // 0→B, "request"→"pequest". .accurate is ~3-5x slower but readable;
        // at our 3s capture cadence the budget is fine.
        // Language correction stays off — autocorrect mangles code identifiers.
        let _: () = msg_send![&*request, setRecognitionLevel: 0i64];
        let _: () = msg_send![&*request, setUsesLanguageCorrection: Bool::NO];
        // English + Brazilian Portuguese. Swift's upstream is en-US only;
        // pt-BR is our intentional deviation so PT screens read correctly.
        let en = NSString::from_str("en-US");
        let pt = NSString::from_str("pt-BR");
        let langs: Retained<NSArray<NSString>> = NSArray::from_slice(&[&*en, &*pt]);
        let _: () = msg_send![&*request, setRecognitionLanguages: &*langs];

        // --- perform:error: ---
        let requests: Retained<NSArray<AnyObject>> = NSArray::from_slice(&[&*request]);
        let mut err: *mut AnyObject = std::ptr::null_mut();
        let ok: Bool = msg_send![&*handler, performRequests: &*requests, error: &mut err];
        if !ok.as_bool() {
            let msg = if err.is_null() {
                "VNImageRequestHandler perform failed (no NSError)".to_string()
            } else {
                let desc: *const NSString = msg_send![err, localizedDescription];
                if desc.is_null() {
                    "VNImageRequestHandler perform failed (nil description)".to_string()
                } else {
                    (*desc).to_string()
                }
            };
            return Err(msg);
        }

        // --- Read observations ---
        let observations: *const NSArray<AnyObject> = msg_send![&*request, results];
        if observations.is_null() {
            return Ok(OcrTextResult {
                full_text: String::new(),
                blocks: Vec::new(),
            });
        }

        let count: usize = msg_send![observations, count];
        tracing::debug!(
            "[ocr_vision] {}x{} JPEG → {} raw observations from Vision",
            img_w,
            img_h,
            count
        );
        let mut blocks: Vec<OcrTextBlock> = Vec::with_capacity(count);
        let mut lines: Vec<String> = Vec::with_capacity(count);

        for i in 0..count {
            let obs: *mut AnyObject = msg_send![observations, objectAtIndex: i];
            if obs.is_null() {
                continue;
            }

            // topCandidates(1) → NSArray<VNRecognizedText>
            let candidates: *const NSArray<AnyObject> = msg_send![obs, topCandidates: 1usize];
            if candidates.is_null() {
                continue;
            }
            let cand_count: usize = msg_send![candidates, count];
            if cand_count == 0 {
                continue;
            }
            let cand: *mut AnyObject = msg_send![candidates, objectAtIndex: 0usize];
            if cand.is_null() {
                continue;
            }

            // VNRecognizedText.string : NSString
            let s_ptr: *const NSString = msg_send![cand, string];
            if s_ptr.is_null() {
                continue;
            }
            let text = (*s_ptr).to_string();
            if text.trim().is_empty() {
                continue;
            }

            // VNRecognizedText.confidence : float (VNConfidence)
            let confidence: f32 = msg_send![cand, confidence];

            // VNDetectedObjectObservation.boundingBox : CGRect
            // (origin bottom-left, normalized 0..1)
            let bbox: VnRect = msg_send![obs, boundingBox];

            let x_min_f = (bbox.origin.x * img_w as f64).max(0.0);
            let width_f = (bbox.size.width * img_w as f64).max(0.0);
            let height_f = (bbox.size.height * img_h as f64).max(0.0);
            // Vision Y is bottom-left origin; flip to top-left.
            let y_top_f =
                ((1.0 - bbox.origin.y - bbox.size.height) * img_h as f64).max(0.0);

            let x_min = x_min_f.round().min(img_w as f64) as u32;
            let y_min = y_top_f.round().min(img_h as f64) as u32;
            let x_max = (x_min_f + width_f).round().min(img_w as f64) as u32;
            let y_max = (y_top_f + height_f).round().min(img_h as f64) as u32;

            blocks.push(OcrTextBlock {
                text: text.clone(),
                confidence,
                bbox: [x_min, y_min, x_max, y_max],
            });
            lines.push(text);
        }

        tracing::debug!(
            "[ocr_vision] kept {}/{} blocks (others dropped: empty text, nil candidates)",
            blocks.len(),
            count
        );
        Ok(OcrTextResult {
            full_text: lines.join("\n"),
            blocks,
        })
    }
}

// CGRect/CGPoint/CGSize layout. We don't pull in the typed `core-graphics`
// rect types here because Vision returns CGRect by value across the
// objc msg_send boundary and the layout is a stable C ABI. The `Encode`
// impls are required for objc2's msg_send to accept these as return types.
#[repr(C)]
#[derive(Clone, Copy)]
struct VnPoint {
    x: f64,
    y: f64,
}
#[repr(C)]
#[derive(Clone, Copy)]
struct VnSize {
    width: f64,
    height: f64,
}
#[repr(C)]
#[derive(Clone, Copy)]
struct VnRect {
    origin: VnPoint,
    size: VnSize,
}

unsafe impl Encode for VnPoint {
    const ENCODING: Encoding =
        Encoding::Struct("CGPoint", &[f64::ENCODING, f64::ENCODING]);
}
unsafe impl RefEncode for VnPoint {
    const ENCODING_REF: Encoding = Encoding::Pointer(&Self::ENCODING);
}
unsafe impl Encode for VnSize {
    const ENCODING: Encoding =
        Encoding::Struct("CGSize", &[f64::ENCODING, f64::ENCODING]);
}
unsafe impl RefEncode for VnSize {
    const ENCODING_REF: Encoding = Encoding::Pointer(&Self::ENCODING);
}
unsafe impl Encode for VnRect {
    const ENCODING: Encoding =
        Encoding::Struct("CGRect", &[VnPoint::ENCODING, VnSize::ENCODING]);
}
unsafe impl RefEncode for VnRect {
    const ENCODING_REF: Encoding = Encoding::Pointer(&Self::ENCODING);
}
