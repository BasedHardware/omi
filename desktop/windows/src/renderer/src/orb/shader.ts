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
uniform float u_noiseTime;   // seconds
uniform float u_noiseAmp;    // wobble amplitude at full merge (disc units)
uniform float u_noiseFreq;   // wobble spatial frequency
uniform float u_sminK;       // smin blend distance at full merge (disc units)
uniform float u_centerR;     // center pool-blob radius (disc units, 0 = none)
uniform float u_amplitude;   // shaped voice amplitude 0..1 (bounded upstream)

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
  // hole mid-merge) and carries the held blob's slow breathing. It only exists
  // once merge is substantial, so it blends with the full pooling distance.
  if (u_centerR > 0.0) {
    float kPool = mix(0.045, u_sminK, u_merge) * u_disc;
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

  // Antialias width from screen-space derivative of the (scaled) field.
  float aa = fwidth(length(q)) * 1.2 + 1e-4;

  float surfMask = 1.0 - smoothstep(-aa, aa, dSurf);
  float dotMask = (1.0 - smoothstep(-aa, aa, dDots)) * surfMask;

  // Hide entirely at (near-)zero genesis — no sub-pixel residue.
  surfMask *= smoothstep(0.0, 0.02, u_genesis);
  dotMask *= smoothstep(0.0, 0.02, u_genesis);

  // Neutral palette only: near-black disc with a whisper of center lift, pure
  // white dots. (Zero-purple is asserted per-frame by the harness.)
  float lift = 0.03 * (1.0 - smoothstep(0.0, u_disc, length(q)));
  vec3 disc = vec3(0.055 + lift);
  vec3 col = mix(disc, vec3(1.0), dotMask);

  // Premultiplied alpha over a transparent background.
  float alpha = surfMask;
  outColor = vec4(col * alpha, alpha);
}
`
