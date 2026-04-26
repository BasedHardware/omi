/**
 * coordinateMap — pure coordinate mapping from captured image pixel space
 * to overlay-window-local CSS points.
 *
 * Mapping chain:
 *   1. Scale from capture pixel space to display pixel space:
 *      px_display = p * (display_width_px / capture_width_px)
 *   2. Convert to CSS points via display_scale_factor:
 *      pt = px_display / display_scale_factor
 *   3. The overlay window is sized and positioned to cover exactly one display,
 *      so display-local points == overlay-window-local points.
 *      No further transform needed.
 *
 * Note on display_origin_pt: this is provided in case the caller ever needs
 * to go to global screen-point space (e.g. to position a non-display-local
 * element). For overlay-local math, the origin cancels out because the
 * overlay's top-left IS the display's top-left.
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface CaptureDisplayMeta {
  /** Tauri monitor index matching the overlay window label suffix. */
  display_id: number;
  /** Pixel width of the captured (possibly downscaled) image. */
  capture_width_px: number;
  /** Pixel height of the captured (possibly downscaled) image. */
  capture_height_px: number;
  /** Physical pixel width of the display. */
  display_width_px: number;
  /** Physical pixel height of the display. */
  display_height_px: number;
  /** HiDPI scale factor (e.g. 2 for Retina, 1 for non-Retina). */
  display_scale_factor: number;
  /**
   * Display origin in AppKit/macOS screen-point space.
   * Primary display origin is (0, 0); secondary displays differ.
   * Provided for completeness — not needed for overlay-local mapping.
   */
  display_origin_pt: { x: number; y: number };
  /** Display size in CSS points (display_width_px / scale_factor, etc.). */
  display_size_pt: { w: number; h: number };
}

/** A point in the captured image's pixel space (0,0 = top-left). */
export interface ImagePoint {
  x: number;
  y: number;
}

/** A point in overlay-window CSS point space (0,0 = top-left of the display). */
export interface OverlayPoint {
  x: number;
  y: number;
}

// ---------------------------------------------------------------------------
// Pure mapping function
// ---------------------------------------------------------------------------

/**
 * Map a point from the captured image's pixel space to overlay-window-local
 * CSS point space.
 *
 * @param p    - Point in the image (capture pixel coordinates).
 * @param meta - Display metadata returned by `take_screenshot_with_ocr`.
 * @returns    Point in overlay-window CSS points (top-left origin).
 */
export function imageToOverlayPoint(p: ImagePoint, meta: CaptureDisplayMeta): OverlayPoint {
  // Step 1: scale from capture pixel space to display pixel space.
  const scaleX = meta.display_width_px / meta.capture_width_px;
  const scaleY = meta.display_height_px / meta.capture_height_px;
  const displayPxX = p.x * scaleX;
  const displayPxY = p.y * scaleY;

  // Step 2: convert display pixels to CSS points via the display scale factor.
  // display_scale_factor is always > 0 (validated by caller on the Rust side).
  return {
    x: displayPxX / meta.display_scale_factor,
    y: displayPxY / meta.display_scale_factor,
  };
}
