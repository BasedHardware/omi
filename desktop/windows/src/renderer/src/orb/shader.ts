// The orb fragment shader — a dumb rasterizer of an OrbFrame (choreography.ts
// computes ALL motion in JS). 2D SDFs: the surface is a circle ↔ rounded-rect
// interpolation (u_morph — one shape, continuous), the eight dots/pills are
// capsules blended with a smooth minimum so they merge organically into the
// "puddle" blob; a low-frequency time-varying value noise perturbs the blob's
// iso-contour; smoothstep antialiasing throughout. Colors are strictly
// neutral — near-black disc, white dots — never purple.

export const ORB_VERT = `#version 300 es
precision highp float;
layout(location = 0) in vec2 a_pos;
void main() {
  gl_Position = vec4(a_pos, 0.0, 1.0);
}
`

export const ORB_FRAG = `#version 300 es
precision highp float;

uniform vec2 u_resolution;   // canvas pixels
uniform vec4 u_dots[8];      // x, y, radius, capsule half-length (disc units)
uniform float u_dotMerge[8]; // per-dot merge 0..1 (drives that dot's smin k)
uniform float u_disc;        // disc radius (fraction of half-extent)
uniform float u_merge;       // 0 separate dots .. 1 blob
uniform float u_morph;       // 0 disc .. 1 rounded rect
uniform vec2 u_rectHalf;     // rounded-rect half extents (disc units)
uniform float u_rectCorner;  // rounded-rect corner radius (disc units)
uniform float u_genesis;     // scale 0..~1 (spring can overshoot slightly)
uniform float u_poseOffset;  // global horizontal shift of the whole pose (short-axis units)
uniform float u_noiseTime;   // seconds
uniform float u_noiseAmp;    // wobble amplitude at full merge (disc units)
uniform float u_noiseFreq;   // wobble spatial frequency
uniform float u_sminK;       // smin blend distance at full merge (disc units)
uniform float u_centerR;     // center pool-blob radius (disc units, 0 = none)
uniform float u_amplitude;   // shaped voice amplitude 0..1 (bounded upstream)

// Waveform visualizer (replaces the speech blob). TWO decoupled parameters so the
// ring visibly UNROLLS into the line rather than opacity-crossfading:
//   u_waveMix — unroll / disc-fade: fades the dark DISC out while the dots travel
//               at FULL opacity to their line positions (JS moves them).
//   u_barMix  — dot→bar handoff, staged AFTER the unroll: ON the line the white
//               dots crossfade to the bar primitives (a representation swap at the
//               same place). 0 = keep the dots, 1 = only the bars.
// u_wave[] holds up to 40 slots (x, halfWidth, halfHeight) in normalized
// short-axis units. Corner radius is min(halfWidth, halfHeight), so a slot with
// halfWidth==halfHeight is a circle (the resting dot) and a tall slot is a
// round-capped vertical bar.
#define WAVE_MAX_SLOTS 40
uniform float u_waveMix;              // 0 = ring, 1 = dots fanned out to the line
uniform float u_barMix;              // 0 = dots on the line, 1 = bars (post-unroll)
uniform int u_waveCount;             // active bars in u_wave[]
uniform vec4 u_wave[WAVE_MAX_SLOTS]; // x, halfWidth, halfHeight, (unused)

out vec4 outColor;

// --- SDFs --------------------------------------------------------------------
float sdCircle(vec2 p, float r) { return length(p) - r; }

float sdRoundBox(vec2 p, vec2 b, float r) {
  vec2 q = abs(p) - b + r;
  return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
}

// Horizontal capsule: segment from (-h,0) to (h,0), radius r, at center c.
float sdCapsule(vec2 p, vec2 c, float h, float r) {
  vec2 q = p - c;
  q.x -= clamp(q.x, -h, h);
  return length(q) - r;
}

// Polynomial smooth minimum (k = blend distance).
float smin(float a, float b, float k) {
  float h = clamp(0.5 + 0.5 * (b - a) / k, 0.0, 1.0);
  return mix(b, a, h) - k * h * (1.0 - h);
}

// --- Cheap 2D value noise (time-varying via a scrolling domain) --------------
float hash(vec2 p) {
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}
float vnoise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1, 0)), u.x),
             mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), u.x), u.y);
}

void main() {
  // Normalized coords: center origin, half-extent = 1 on the short axis.
  vec2 hr = 0.5 * u_resolution;
  vec2 p = (gl_FragCoord.xy - hr) / min(hr.x, hr.y);
  p.y = -p.y; // y up → y down parity with choreography (screen-like)

  // Genesis: scale the whole field up from 0. Guard tiny scales; fully hide
  // below a visibility floor so frame 0 is truly nothing.
  float g = max(u_genesis, 1e-4);
  vec2 q = p / g;
  // Global horizontal shake (the fail tremor). Shifting the sample point moves the
  // whole rendered pose — disc, dots, and pool together. 0 in steady operation.
  q.x -= u_poseOffset;

  // Surface: disc ↔ rounded rect, one continuous SDF.
  float dSurf = mix(sdCircle(q, u_disc), sdRoundBox(q, u_rectHalf, u_rectCorner), u_morph);

  // Dots/pills merged with smin. The blend distance is PER DOT: a dot that
  // hasn't converged yet (u_dotMerge≈0) unions near-hard, so it stays a crisp
  // separate dot with no smin haze reaching toward its neighbours; a converged
  // dot (u_dotMerge≈1) blends with the full liquid distance. Deriving k from a
  // single global u_merge instead applied the pooling blend to EVERY pair even
  // when only some dots had arrived — the faint interior webbing/mist.
  float dDots = 1e5;
  for (int i = 0; i < 8; i++) {
    vec4 d = u_dots[i];
    float di = sdCapsule(q, d.xy * u_disc, d.w * u_disc, d.z * u_disc);
    float ki = mix(0.02, u_sminK, u_dotMerge[i]) * u_disc;
    dDots = smin(dDots, di, ki);
  }
  // Center pool blob: fills the middle of the converging ring (no punched
  // hole mid-merge) and GLUES the dots into one body. Its blend distance is
  // generous once the blob is forming — larger than the dot↔dot k — so no
  // interior field dip / hole survives between the pool and the ring; dots stay
  // hard to EACH OTHER (no webbing), the pool does the liquid gluing. The bridge
  // strength RAMPS with merge (smoothstep): near-zero while the dots are still a
  // ring, full by the time the blob is holding. A constant-large bridge snapped
  // the pool onto the dots the instant it became visible — the blob's rendered
  // area jumped in one frame as a dissolve swept merge past that point (C6). The
  // ramp lets the pool glue in gradually to match its smooth radius growth.
  if (u_centerR > 0.0) {
    float kPool = u_sminK * 1.7 * smoothstep(0.12, 0.36, u_merge) * u_disc;
    dDots = smin(dDots, sdCircle(q, u_centerR * u_disc), kPool);
  }

  // Low-frequency wobble on the blob contour, scaled by merge so the resting
  // ring stays crisp. Two scrolling noise reads → gentle oscillation; the
  // finer octave is weighted by the (bounded) voice amplitude so louder
  // speech reads as finer, livelier ripples — never a spike (u_noiseAmp and
  // u_amplitude are both compressed into fixed ranges upstream).
  float o2 = 0.35 + 0.65 * u_amplitude;
  float n = vnoise(q * u_noiseFreq + vec2(u_noiseTime * 0.35, -u_noiseTime * 0.27))
          + vnoise(q * (u_noiseFreq * 2.1) - vec2(u_noiseTime * 0.22, u_noiseTime * 0.31)) * o2;
  float nspan = 1.0 + o2;
  dDots += (n / nspan - 0.5) * u_noiseAmp * u_merge * u_disc * 2.0;

  // Antialias width from the screen-space derivative of EACH field itself, not
  // of length(q). fwidth(field) is the field's change per pixel, so
  // smoothstep(-aa, aa, field) always spans ~2px regardless of how steep or
  // flat the field's gradient is. The merged blob's field is NOT unit-gradient
  // (the pool/dot smin blends and the additive noise flatten it in places);
  // keying the AA off length(q)'s constant unit gradient therefore stretched
  // the transition across many pixels wherever the field was flat — the misty
  // rim. Deriving aa from the field makes the edge a crisp, uniform ~2px
  // wherever it lands. dSurf is a clean SDF, so it gets its own (near-identical)
  // aa rather than borrowing the blob's.
  float aaSurf = fwidth(dSurf) + 1e-4;
  float aaDots = fwidth(dDots) + 1e-4;

  float surfMask = 1.0 - smoothstep(-aaSurf, aaSurf, dSurf);
  // Dots are clipped to the disc at REST (idle ring / morph), but UNCLIPPED once
  // the unroll engages (u_waveMix > 0) so they can travel out along the line
  // beyond the disc. The switch is invisible: when u_waveMix first leaves 0 the
  // dots are still on the ring (inside the disc, where surfMask is already 1), so
  // nothing off-disc is lit yet.
  float dotClip = mix(surfMask, 1.0, step(1e-4, u_waveMix));
  float dotMask = (1.0 - smoothstep(-aaDots, aaDots, dDots)) * dotClip;

  // Waveform: union (plain min — discrete bars with gaps, no smin pooling) of the
  // vertical rounded-capsule bars. Each is a rounded box of half-extent
  // (capRadius, halfHeight) with corner = capRadius, so halfHeight == capRadius
  // renders a perfect circle (the silence dot). Light on transparent — NOT clipped
  // to the disc, so it can span a wide mount.
  float dWave = 1e5;
  for (int i = 0; i < WAVE_MAX_SLOTS; i++) {
    if (i >= u_waveCount) break;
    vec4 b = u_wave[i]; // x, halfWidth, halfHeight
    dWave = min(dWave, sdRoundBox(q - vec2(b.x, 0.0), vec2(b.y, b.z), min(b.y, b.z)));
  }
  float aaWave = fwidth(dWave) + 1e-4;
  // Bar coverage is opacity-gated by u_barMix (the post-unroll handoff), NOT
  // u_waveMix — during the unroll the bars stay invisible so only the traveling
  // dots are seen; they fade in on the line once the row is formed.
  float waveCov = 1.0 - smoothstep(-aaWave, aaWave, dWave);

  // Hide entirely at (near-)zero genesis — no sub-pixel residue.
  float genesisGate = smoothstep(0.0, 0.02, u_genesis);
  surfMask *= genesisGate;
  dotMask *= genesisGate;
  waveCov *= genesisGate;

  // Neutral palette only: near-black disc with a whisper of center lift, white
  // dots and white bars. (Zero-purple is asserted per-frame by the harness.)
  float lift = 0.03 * (1.0 - smoothstep(0.0, u_disc, length(q)));
  vec3 disc = vec3(0.055 + lift);

  // Three premultiplied layers, source-over top→bottom = bars, dots, disc:
  //   • DISC — dark backing; fades out as the ring unrolls (u_waveMix). This is
  //            the only thing that fades WITH the unroll, so the ring opens up.
  //   • DOTS — white; FULL opacity while they travel (the fan-out), fading only as
  //            the bars take over ON the line (u_barMix). Keeping the dots opaque
  //            through the unroll is what makes the ring visibly fan out into the
  //            line instead of a ring↔line opacity crossfade.
  //   • BARS — white; fade in on the line post-unroll (u_barMix).
  // At u_waveMix=0,u_barMix=0 this reduces exactly to the idle disc+dots render;
  // at 1,1 only the white bars remain.
  float discA = surfMask * (1.0 - u_waveMix);
  vec3 discPre = disc * discA;

  float dotA = dotMask * (1.0 - u_barMix);
  vec3 dotPre = vec3(1.0) * dotA;

  // dots over disc
  vec3 rdPre = dotPre + discPre * (1.0 - dotA);
  float rdA = dotA + discA * (1.0 - dotA);

  float waveA = waveCov * u_barMix;
  vec3 wavePre = vec3(1.0) * waveA;

  // bars over (dots over disc)
  vec3 outPre = wavePre + rdPre * (1.0 - waveA);
  float outA = waveA + rdA * (1.0 - waveA);
  outColor = vec4(outPre, outA);
}
`
