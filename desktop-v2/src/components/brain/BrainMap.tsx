import { useState, useMemo, type KeyboardEvent, type MouseEvent } from "react";
import { BRAIN_REGIONS, BRAIN_REGION_META, type BrainRegion } from "./regions";

interface Props {
  counts: Record<BrainRegion, number>;
  selected: BrainRegion | null;
  onSelect: (region: BrainRegion | null) => void;
}

// Each region's SVG path. Side-profile brain, facing LEFT.
// viewBox 0 0 600 420.
// Approx anatomy only — stylized.
const REGION_PATHS: Record<BrainRegion, string> = {
  // Prefrontal cortex — the frontal bulge at the front-top (LEFT side of canvas).
  prefrontal: `
    M 120 185
    C 95 165, 80 135, 95 105
    C 110 78, 145 62, 180 65
    C 215 68, 240 90, 250 120
    C 255 140, 252 165, 240 185
    C 225 205, 200 215, 175 212
    C 150 210, 130 200, 120 185 Z
  `,
  // Temporal lobe — the thumb-like lobe on the lower-left side.
  temporal: `
    M 135 235
    C 120 235, 105 245, 100 265
    C 95 285, 100 305, 115 320
    C 135 335, 165 340, 195 335
    C 220 330, 240 318, 248 298
    C 252 280, 248 262, 235 250
    C 220 238, 195 232, 170 232
    C 155 232, 142 232, 135 235 Z
  `,
  // Parietal lobe — top-back crown of the brain.
  parietal: `
    M 260 75
    C 290 60, 330 55, 370 62
    C 410 70, 440 88, 455 115
    C 465 140, 460 168, 445 188
    C 425 205, 395 212, 360 208
    C 325 204, 295 190, 275 170
    C 258 150, 250 120, 255 95
    C 257 85, 258 78, 260 75 Z
  `,
  // Occipital lobe — back of the brain (RIGHT side of canvas).
  occipital: `
    M 460 150
    C 485 150, 510 165, 522 190
    C 532 215, 530 245, 515 268
    C 498 290, 472 302, 448 298
    C 425 294, 408 278, 400 258
    C 392 235, 395 208, 410 188
    C 425 168, 445 152, 460 150 Z
  `,
  // Cerebellum — small rounded lobe at bottom-right (under occipital).
  cerebellum: `
    M 445 305
    C 470 300, 498 308, 512 328
    C 523 348, 518 372, 500 385
    C 478 398, 450 398, 430 385
    C 415 373, 408 355, 415 338
    C 422 320, 432 308, 445 305 Z
  `,
  // Hippocampus — small deep center ovaloid shape, seahorse hint.
  hippocampus: `
    M 285 215
    C 295 208, 312 208, 322 218
    C 330 228, 332 245, 325 258
    C 318 270, 302 275, 290 270
    C 278 264, 272 250, 275 236
    C 277 227, 280 220, 285 215 Z
  `,
};

// Decorative gyri (surface folds) — stylized squiggles that suggest brain texture.
// These are pointer-events: none and purely visual.
const GYRI_PATH = `
  M 155 110 C 175 105, 195 112, 210 125
  M 145 140 C 170 135, 200 140, 225 155
  M 135 170 C 165 167, 200 172, 230 185
  M 280 88 C 305 82, 335 85, 360 95
  M 290 115 C 320 110, 355 113, 390 125
  M 285 145 C 320 140, 360 143, 400 155
  M 290 175 C 325 172, 365 175, 405 185
  M 290 205 C 320 202, 350 205, 378 215
  M 150 265 C 175 262, 205 268, 225 280
  M 145 290 C 175 288, 210 295, 232 308
  M 415 200 C 440 198, 465 205, 485 220
  M 420 230 C 445 228, 470 235, 490 250
  M 420 260 C 445 258, 468 265, 485 278
  M 430 330 C 448 328, 468 335, 482 348
  M 432 355 C 450 353, 470 360, 485 372
`;

// Label positions — placed outside or near the edge of each region.
const LABEL_POSITIONS: Record<BrainRegion, { x: number; y: number; anchor: "start" | "middle" | "end" }> = {
  prefrontal: { x: 105, y: 50, anchor: "start" },
  parietal: { x: 355, y: 40, anchor: "middle" },
  occipital: { x: 555, y: 175, anchor: "middle" },
  cerebellum: { x: 555, y: 350, anchor: "middle" },
  temporal: { x: 145, y: 370, anchor: "middle" },
  hippocampus: { x: 305, y: 300, anchor: "middle" },
};

// Badge positions for count badges.
const BADGE_POSITIONS: Record<BrainRegion, { x: number; y: number }> = {
  prefrontal: { x: 230, y: 95 },
  parietal: { x: 430, y: 100 },
  occipital: { x: 495, y: 175 },
  cerebellum: { x: 495, y: 345 },
  temporal: { x: 225, y: 315 },
  hippocampus: { x: 315, y: 218 },
};

export function BrainMap({ counts, selected, onSelect }: Props) {
  const [hovered, setHovered] = useState<BrainRegion | null>(null);

  const handleRegionClick = (region: BrainRegion, e: MouseEvent) => {
    e.stopPropagation();
    onSelect(selected === region ? null : region);
  };

  const handleRegionKey = (region: BrainRegion, e: KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      e.stopPropagation();
      onSelect(selected === region ? null : region);
    }
  };

  const handleBackgroundClick = () => {
    onSelect(null);
  };

  const getRegionOpacity = (region: BrainRegion): number => {
    if (selected === region) return 1.0;
    if (selected && selected !== region) return 0.1;
    if (hovered === region) return 0.65;
    return 0.28;
  };

  const getRegionFilter = (region: BrainRegion): string => {
    if (selected === region) return "url(#glow-strong)";
    if (hovered === region) return "url(#glow-soft)";
    return "none";
  };

  const getLabelOpacity = (region: BrainRegion): number => {
    if (selected === region) return 1.0;
    if (selected && selected !== region) return 0.25;
    if (hovered === region) return 0.95;
    return 0.55;
  };

  const getStrokeColor = (region: BrainRegion): string => {
    if (selected === region) return "#ffffff";
    return BRAIN_REGION_META[region].color;
  };

  const getStrokeWidth = (region: BrainRegion): number => {
    if (selected === region) return 2;
    if (hovered === region) return 1.5;
    return 1;
  };

  // Stable unique IDs so multiple instances don't collide.
  const uid = useMemo(() => `bm-${Math.random().toString(36).slice(2, 9)}`, []);

  return (
    <div className="brain-map-container">
      <svg
        viewBox="0 0 600 420"
        xmlns="http://www.w3.org/2000/svg"
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label="Interactive brain regions"
        onClick={handleBackgroundClick}
        style={{ width: "100%", height: "auto", display: "block", cursor: "default" }}
      >
        <defs>
          {/* Radial backdrop glow for the whole brain */}
          <radialGradient id={`${uid}-backdrop`} cx="50%" cy="50%" r="60%">
            <stop offset="0%" stopColor="rgba(139, 92, 246, 0.12)" />
            <stop offset="60%" stopColor="rgba(59, 130, 246, 0.06)" />
            <stop offset="100%" stopColor="rgba(0, 0, 0, 0)" />
          </radialGradient>

          {/* Per-region radial gradients so centers are brighter */}
          {BRAIN_REGIONS.map((region) => {
            const color = BRAIN_REGION_META[region].color;
            return (
              <radialGradient
                key={region}
                id={`${uid}-grad-${region}`}
                cx="50%"
                cy="45%"
                r="65%"
              >
                <stop offset="0%" stopColor={color} stopOpacity="1" />
                <stop offset="70%" stopColor={color} stopOpacity="0.75" />
                <stop offset="100%" stopColor={color} stopOpacity="0.4" />
              </radialGradient>
            );
          })}

          {/* Soft hover glow */}
          <filter id="glow-soft" x="-30%" y="-30%" width="160%" height="160%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          {/* Strong selected glow */}
          <filter id="glow-strong" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="6" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          {/* Inner shadow to give the brain depth */}
          <filter id={`${uid}-inner-shadow`}>
            <feGaussianBlur in="SourceAlpha" stdDeviation="4" />
            <feOffset dx="0" dy="2" result="offsetblur" />
            <feFlood floodColor="#000" floodOpacity="0.45" />
            <feComposite in2="offsetblur" operator="in" />
            <feComposite in2="SourceGraphic" operator="over" />
          </filter>

          {/* Brain silhouette clip so gyri stay inside */}
          <clipPath id={`${uid}-brain-clip`}>
            <path
              d="M 100 160
                 C 85 130, 85 95, 110 72
                 C 140 45, 185 40, 220 55
                 C 235 45, 260 40, 290 45
                 C 340 38, 400 45, 445 70
                 C 490 95, 520 135, 528 180
                 C 535 225, 525 270, 505 300
                 C 500 330, 478 360, 445 382
                 C 410 402, 370 408, 335 400
                 C 280 410, 225 405, 180 385
                 C 140 368, 110 340, 95 305
                 C 82 270, 82 225, 100 160 Z"
            />
          </clipPath>
        </defs>

        {/* Backdrop glow */}
        <rect width="600" height="420" fill={`url(#${uid}-backdrop)`} />

        {/* Outer brain silhouette — subtle dark fill for the whole organ */}
        <path
          d="M 100 160
             C 85 130, 85 95, 110 72
             C 140 45, 185 40, 220 55
             C 235 45, 260 40, 290 45
             C 340 38, 400 45, 445 70
             C 490 95, 520 135, 528 180
             C 535 225, 525 270, 505 300
             C 500 330, 478 360, 445 382
             C 410 402, 370 408, 335 400
             C 280 410, 225 405, 180 385
             C 140 368, 110 340, 95 305
             C 82 270, 82 225, 100 160 Z"
          fill="rgba(255, 255, 255, 0.03)"
          stroke="rgba(255, 255, 255, 0.08)"
          strokeWidth="1"
        />

        {/* Brainstem — small neck shape under cerebellum (decorative only) */}
        <path
          d="M 430 388 C 436 405, 438 418, 434 420 L 406 420 C 408 410, 414 398, 420 390 Z"
          fill="rgba(255, 255, 255, 0.04)"
          stroke="rgba(255, 255, 255, 0.08)"
          strokeWidth="1"
        />

        {/* Interactive regions (cortex lobes first, then cerebellum, then hippocampus on top) */}
        {(["prefrontal", "parietal", "occipital", "temporal", "cerebellum", "hippocampus"] as BrainRegion[]).map(
          (region) => {
            const meta = BRAIN_REGION_META[region];
            const count = counts[region] ?? 0;
            const opacity = getRegionOpacity(region);
            const filter = getRegionFilter(region);
            const isHipp = region === "hippocampus";

            return (
              <g
                key={region}
                role="button"
                tabIndex={0}
                aria-label={`${meta.label} — ${count} memories`}
                aria-pressed={selected === region}
                onClick={(e) => handleRegionClick(region, e)}
                onKeyDown={(e) => handleRegionKey(region, e)}
                onMouseEnter={() => setHovered(region)}
                onMouseLeave={() => setHovered(null)}
                style={{
                  cursor: "pointer",
                  outline: "none",
                  transition: "opacity 0.25s ease, filter 0.25s ease",
                }}
              >
                <path
                  d={REGION_PATHS[region]}
                  fill={`url(#${uid}-grad-${region})`}
                  stroke={getStrokeColor(region)}
                  strokeWidth={getStrokeWidth(region)}
                  strokeLinejoin="round"
                  opacity={opacity}
                  filter={filter}
                  style={{
                    transition: "opacity 0.25s ease, stroke 0.25s ease, stroke-width 0.25s ease",
                  }}
                />
                {/* Hippocampus and cerebellum get a subtle inner highlight so they read as distinct */}
                {isHipp && (
                  <path
                    d={REGION_PATHS[region]}
                    fill="none"
                    stroke="rgba(255,255,255,0.25)"
                    strokeWidth="0.75"
                    strokeDasharray="2 3"
                    opacity={opacity * 0.9}
                    style={{ pointerEvents: "none", transition: "opacity 0.25s ease" }}
                  />
                )}
              </g>
            );
          },
        )}

        {/* Decorative gyri (folds) clipped to brain silhouette, non-interactive */}
        <g
          clipPath={`url(#${uid}-brain-clip)`}
          style={{ pointerEvents: "none" }}
        >
          <path
            d={GYRI_PATH}
            fill="none"
            stroke="rgba(255, 255, 255, 0.12)"
            strokeWidth="1"
            strokeLinecap="round"
          />
        </g>

        {/* Labels + count badges */}
        {BRAIN_REGIONS.map((region) => {
          const meta = BRAIN_REGION_META[region];
          const count = counts[region] ?? 0;
          const labelPos = LABEL_POSITIONS[region];
          const badgePos = BADGE_POSITIONS[region];
          const labelOpacity = getLabelOpacity(region);
          const isActive = selected === region || hovered === region;

          return (
            <g
              key={`label-${region}`}
              style={{ pointerEvents: "none", transition: "opacity 0.25s ease" }}
              opacity={labelOpacity}
            >
              <text
                x={labelPos.x}
                y={labelPos.y}
                textAnchor={labelPos.anchor}
                fill={isActive ? meta.color : "rgba(255,255,255,0.85)"}
                fontSize="12"
                fontFamily="Inter, system-ui, sans-serif"
                fontWeight={isActive ? 600 : 500}
                style={{
                  transition: "fill 0.25s ease, font-weight 0.25s ease",
                  letterSpacing: "0.02em",
                }}
              >
                {meta.shortLabel}
              </text>

              {count > 0 && (
                <g transform={`translate(${badgePos.x}, ${badgePos.y})`}>
                  <circle
                    r="11"
                    fill={meta.color}
                    stroke="rgba(0,0,0,0.4)"
                    strokeWidth="1"
                    style={{
                      filter: isActive ? "url(#glow-soft)" : "none",
                      transition: "filter 0.25s ease",
                    }}
                  />
                  <text
                    x="0"
                    y="0"
                    textAnchor="middle"
                    dominantBaseline="central"
                    fill="#ffffff"
                    fontSize="11"
                    fontFamily="Inter, system-ui, sans-serif"
                    fontWeight="700"
                  >
                    {count > 99 ? "99+" : count}
                  </text>
                </g>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
