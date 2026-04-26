/**
 * Unit tests for coordinateMap.ts — imageToOverlayPoint.
 *
 * Fixture legend (Tier 1 — basic):
 *   Retina primary:   2560×1600 display, scale 2, capture 1280×800
 *   Non-Retina ext.:  1920×1080 display, scale 1, capture 1280×720
 *
 * Fixture legend (Tier 2 — real-world multi-monitor scenarios from the plan):
 *   RETINA_2880_PRIMARY:   2880×1800 Retina primary @ scale 2, capture 1280×800
 *   NON_RETINA_1080_RIGHT: 1920×1080 non-Retina secondary @ scale 1, placed to the right
 *                          Capture: 1280×720
 *   FOUR_K_1_5X:           3840×2160 4K monitor @ scale 1.5 (effective 2560×1440 pt),
 *                          capture 1280×720
 */
import { describe, it, expect } from "vitest";
import { imageToOverlayPoint, type CaptureDisplayMeta } from "./coordinateMap";

// ---------------------------------------------------------------------------
// Fixture display metas
// ---------------------------------------------------------------------------

const RETINA_PRIMARY: CaptureDisplayMeta = {
  display_id: 0,
  capture_width_px: 1280,
  capture_height_px: 800,
  display_width_px: 2560,
  display_height_px: 1600,
  display_scale_factor: 2,
  display_origin_pt: { x: 0, y: 0 },
  display_size_pt: { w: 1280, h: 800 },
};

const RETINA_SECONDARY: CaptureDisplayMeta = {
  display_id: 1,
  capture_width_px: 1280,
  capture_height_px: 800,
  display_width_px: 2560,
  display_height_px: 1600,
  display_scale_factor: 2,
  // Simulate a secondary display placed to the right of primary.
  display_origin_pt: { x: 1280, y: 0 },
  display_size_pt: { w: 1280, h: 800 },
};

const NON_RETINA_EXT: CaptureDisplayMeta = {
  display_id: 2,
  capture_width_px: 1280,
  capture_height_px: 720,
  display_width_px: 1920,
  display_height_px: 1080,
  display_scale_factor: 1,
  display_origin_pt: { x: 1280, y: 0 },
  display_size_pt: { w: 1920, h: 1080 },
};

// ---------------------------------------------------------------------------
// Tier 2 fixtures — real-world multi-monitor scenarios
// Plan risk bullet: "Retina primary (2880×1800 @ 2x) + external non-Retina
// (1920×1080 @ 1x) to the right — coordinate drift".
// ---------------------------------------------------------------------------

/**
 * 2880×1800 Retina primary (MacBook Pro 16") @ scale 2.
 * Effective size in CSS points: 1440×900.
 * Capture is downscaled to max 1280 wide → 1280×800.
 * Scale ratios: x = 2880/1280 = 2.25, y = 1800/800 = 2.25.
 * pt = display_px / 2 → net factor = 2.25/2 = 1.125.
 */
const RETINA_2880_PRIMARY: CaptureDisplayMeta = {
  display_id: 0,
  capture_width_px: 1280,
  capture_height_px: 800,
  display_width_px: 2880,
  display_height_px: 1800,
  display_scale_factor: 2,
  display_origin_pt: { x: 0, y: 0 },
  display_size_pt: { w: 1440, h: 900 },
};

/**
 * 1920×1080 external non-Retina monitor @ scale 1, placed to the right of
 * the 2880-wide primary.  Capture is downscaled to 1280×720.
 * Scale ratios: x = 1920/1280 = 1.5, y = 1080/720 = 1.5.
 * pt = display_px / 1 → net factor = 1.5.
 * display_origin_pt.x = 1440 (primary effective width in pts).
 */
const NON_RETINA_1080_RIGHT: CaptureDisplayMeta = {
  display_id: 1,
  capture_width_px: 1280,
  capture_height_px: 720,
  display_width_px: 1920,
  display_height_px: 1080,
  display_scale_factor: 1,
  display_origin_pt: { x: 1440, y: 0 },
  display_size_pt: { w: 1920, h: 1080 },
};

/**
 * Single 27" 4K (3840×2160) at 1.5x HiDPI scaling (e.g. LG 27UK850).
 * Effective size: 2560×1440 CSS pts.
 * Capture downscaled to 1280×720 (half effective resolution).
 * Scale ratios: x = 3840/1280 = 3, y = 2160/720 = 3.
 * pt = display_px / 1.5 → net factor = 3/1.5 = 2.
 */
const FOUR_K_1_5X: CaptureDisplayMeta = {
  display_id: 0,
  capture_width_px: 1280,
  capture_height_px: 720,
  display_width_px: 3840,
  display_height_px: 2160,
  display_scale_factor: 1.5,
  display_origin_pt: { x: 0, y: 0 },
  display_size_pt: { w: 2560, h: 1440 },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function approx(actual: number, expected: number, epsilon = 0.5): boolean {
  return Math.abs(actual - expected) <= epsilon;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("imageToOverlayPoint", () => {
  describe("Retina primary display (2560×1600, scale 2, capture 1280×800)", () => {
    it("maps top-left corner (0, 0) → (0, 0) overlay pt", () => {
      const result = imageToOverlayPoint({ x: 0, y: 0 }, RETINA_PRIMARY);
      expect(result.x).toBe(0);
      expect(result.y).toBe(0);
    });

    it("maps bottom-right corner (1279, 799) → ~(640, 400) overlay pt", () => {
      // Scale up: 1279 * (2560/1280) = 2558 px → 2558/2 = 1279 pt
      // Scale up: 799 * (1600/800) = 1598 px → 1598/2 = 799 pt
      // Note: overlay pt space for this display is 1280×800 (display_size_pt).
      // The last pixel maps to 1279 pt / 799 pt (not exactly 1280/800).
      const result = imageToOverlayPoint({ x: 1279, y: 799 }, RETINA_PRIMARY);
      expect(approx(result.x, 1279)).toBe(true);
      expect(approx(result.y, 799)).toBe(true);
    });

    it("maps center (640, 400) → ~(640, 400) overlay pt", () => {
      // 640 * (2560/1280) = 1280 px → 1280/2 = 640 pt
      // 400 * (1600/800)  = 800 px  → 800/2  = 400 pt
      const result = imageToOverlayPoint({ x: 640, y: 400 }, RETINA_PRIMARY);
      expect(approx(result.x, 640)).toBe(true);
      expect(approx(result.y, 400)).toBe(true);
    });
  });

  describe("Non-primary display origin — same math, display-local result", () => {
    it("maps (0, 0) on secondary Retina display → (0, 0) overlay pt (display-local)", () => {
      // The overlay window is anchored to the secondary display's top-left,
      // so the origin is always (0, 0) in overlay-local space regardless of
      // the display's global position (display_origin_pt is not used in the
      // overlay-local transform).
      const result = imageToOverlayPoint({ x: 0, y: 0 }, RETINA_SECONDARY);
      expect(result.x).toBe(0);
      expect(result.y).toBe(0);
    });

    it("maps center (640, 400) on secondary Retina display → (640, 400) overlay pt", () => {
      const result = imageToOverlayPoint({ x: 640, y: 400 }, RETINA_SECONDARY);
      expect(approx(result.x, 640)).toBe(true);
      expect(approx(result.y, 400)).toBe(true);
    });
  });

  describe("Non-Retina external display (1920×1080, scale 1, capture 1280×720)", () => {
    it("maps (0, 0) → (0, 0) overlay pt", () => {
      const result = imageToOverlayPoint({ x: 0, y: 0 }, NON_RETINA_EXT);
      expect(result.x).toBe(0);
      expect(result.y).toBe(0);
    });

    it("maps (1280, 720) → (1920, 1080) overlay pt", () => {
      // 1280 * (1920/1280) = 1920 px → 1920/1 = 1920 pt
      // 720  * (1080/720)  = 1080 px → 1080/1 = 1080 pt
      const result = imageToOverlayPoint({ x: 1280, y: 720 }, NON_RETINA_EXT);
      expect(approx(result.x, 1920)).toBe(true);
      expect(approx(result.y, 1080)).toBe(true);
    });

    it("maps center (640, 360) → (960, 540) overlay pt", () => {
      const result = imageToOverlayPoint({ x: 640, y: 360 }, NON_RETINA_EXT);
      expect(approx(result.x, 960)).toBe(true);
      expect(approx(result.y, 540)).toBe(true);
    });
  });

  // -------------------------------------------------------------------------
  // Tier 2 — real-world multi-monitor scenarios (plan "Coordinate drift" risk)
  // -------------------------------------------------------------------------

  describe("Tier 2: Retina 2880×1800 @2x primary + non-Retina 1920×1080 @1x secondary", () => {
    describe("Capture on the primary (2880×1800 @2x, capture 1280×800)", () => {
      it("maps top-left (0, 0) → (0, 0) overlay pt", () => {
        const result = imageToOverlayPoint({ x: 0, y: 0 }, RETINA_2880_PRIMARY);
        expect(result.x).toBe(0);
        expect(result.y).toBe(0);
      });

      it("maps image-center (640, 400) → (720, 450) overlay pt", () => {
        // Step 1: scale to display px: 640 * (2880/1280) = 1440, 400 * (1800/800) = 900
        // Step 2: divide by scale factor 2:  1440/2 = 720 pt, 900/2 = 450 pt
        const result = imageToOverlayPoint({ x: 640, y: 400 }, RETINA_2880_PRIMARY);
        expect(approx(result.x, 720)).toBe(true);
        expect(approx(result.y, 450)).toBe(true);
      });

      it("maps boundary bottom-right (capture_w-1, capture_h-1) → near (1439, 899)", () => {
        // (1279 * 2880/1280) / 2 = (2878.125) / 2 ≈ 1439.06
        // (799  * 1800/800)  / 2 = (1797.75)  / 2 ≈ 898.875
        const result = imageToOverlayPoint(
          { x: RETINA_2880_PRIMARY.capture_width_px - 1, y: RETINA_2880_PRIMARY.capture_height_px - 1 },
          RETINA_2880_PRIMARY,
        );
        expect(approx(result.x, 1439, 1)).toBe(true);
        expect(approx(result.y, 899, 1)).toBe(true);
      });
    });

    describe("Capture on the secondary (1920×1080 @1x, capture 1280×720)", () => {
      it("maps top-left (0, 0) → (0, 0) overlay pt (display-local)", () => {
        // The overlay window is anchored to the secondary's top-left; display_origin_pt
        // is not applied in the overlay-local transform.
        const result = imageToOverlayPoint({ x: 0, y: 0 }, NON_RETINA_1080_RIGHT);
        expect(result.x).toBe(0);
        expect(result.y).toBe(0);
      });

      it("maps image-center (640, 360) → (960, 540) overlay pt", () => {
        // Step 1: 640 * (1920/1280) = 960 px, 360 * (1080/720) = 540 px
        // Step 2: / scale factor 1 → 960 pt, 540 pt
        const result = imageToOverlayPoint({ x: 640, y: 360 }, NON_RETINA_1080_RIGHT);
        expect(approx(result.x, 960)).toBe(true);
        expect(approx(result.y, 540)).toBe(true);
      });

      it("maps boundary top-left (0, 0) → (0, 0)", () => {
        const result = imageToOverlayPoint({ x: 0, y: 0 }, NON_RETINA_1080_RIGHT);
        expect(result.x).toBe(0);
        expect(result.y).toBe(0);
      });

      it("maps boundary bottom-right (capture_w-1, capture_h-1) → near (1919, 1079)", () => {
        // (1279 * 1920/1280) / 1 = 1918.5
        // (719  * 1080/720)  / 1 = 1078.5
        const result = imageToOverlayPoint(
          { x: NON_RETINA_1080_RIGHT.capture_width_px - 1, y: NON_RETINA_1080_RIGHT.capture_height_px - 1 },
          NON_RETINA_1080_RIGHT,
        );
        expect(approx(result.x, 1919, 1)).toBe(true);
        expect(approx(result.y, 1079, 1)).toBe(true);
      });
    });
  });

  describe("Tier 2: Single 4K 3840×2160 @1.5x (effective 2560×1440 pt), capture 1280×720", () => {
    it("maps top-left (0, 0) → (0, 0) overlay pt", () => {
      const result = imageToOverlayPoint({ x: 0, y: 0 }, FOUR_K_1_5X);
      expect(result.x).toBe(0);
      expect(result.y).toBe(0);
    });

    it("maps image-center (640, 360) → (1280, 720) overlay pt", () => {
      // Step 1: 640 * (3840/1280) = 1920 px, 360 * (2160/720) = 1080 px
      // Step 2: / 1.5 → 1280 pt, 720 pt  (== half the effective display size)
      const result = imageToOverlayPoint({ x: 640, y: 360 }, FOUR_K_1_5X);
      expect(approx(result.x, 1280)).toBe(true);
      expect(approx(result.y, 720)).toBe(true);
    });

    it("maps boundary top-left (0, 0) → (0, 0)", () => {
      const result = imageToOverlayPoint({ x: 0, y: 0 }, FOUR_K_1_5X);
      expect(result.x).toBe(0);
      expect(result.y).toBe(0);
    });

    it("maps boundary bottom-right (capture_w-1, capture_h-1) → near (2559, 1439)", () => {
      // (1279 * 3840/1280) / 1.5 = (3837) / 1.5 = 2558
      // (719  * 2160/720)  / 1.5 = (2157) / 1.5 = 1438
      const result = imageToOverlayPoint(
        { x: FOUR_K_1_5X.capture_width_px - 1, y: FOUR_K_1_5X.capture_height_px - 1 },
        FOUR_K_1_5X,
      );
      expect(approx(result.x, 2558, 1)).toBe(true);
      expect(approx(result.y, 1438, 1)).toBe(true);
    });
  });
});
