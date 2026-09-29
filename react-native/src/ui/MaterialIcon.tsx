import type {ReactNode} from 'react';
import {type StyleProp, type TextStyle} from 'react-native';
import Svg, {Path} from 'react-native-svg';
import {MATERIAL_PATHS, MATERIAL_VIEWBOX} from './materialIconPaths';

type MaterialIconName = keyof typeof MATERIAL_PATHS;

type Props = {
  name: MaterialIconName;
  size?: number;
  /** Glyph fill. Omit and pass `style={{color}}` to inherit like text. */
  color?: string;
  /**
   * Accepted for call-site parity with the old lucide icons. The SVG path
   * already carries the default (unfilled) Material Symbols Rounded shape.
   */
  fill?: string;
  style?: StyleProp<TextStyle>;
  children?: ReactNode;
} & Record<string, unknown>;

/**
 * Material Symbols Rounded icon rendered as the original SVG geometry
 * (FILL 0, wght 400, GRAD 0, opsz 24 — Google's default axes).
 *
 * Why not the icon font: Material Symbols' CoreText metrics are lopsided
 * (≈1.1:0.1 ascent:descent at every size), so a font glyph with
 * `lineHeight: size` parks its ink 0.2–0.4em above the flex center on
 * macOS/iOS, and every "fix" degrades into per-surface magic numbers. The
 * SVG artwork is already optically centered on its own 960-unit design
 * grid — rendering that grid square is the spec-correct placement under
 * every layout engine, no nudges.
 */
export function MaterialIcon({
  name,
  size = 16,
  color,
  fill,
  style,
  ...rest
}: Props) {
  void fill;
  const glyph = MATERIAL_PATHS[name];
  const entry =
    typeof glyph === 'string' ? {d: glyph, viewBox: MATERIAL_VIEWBOX} : glyph;
  return (
    <Svg
      width={size}
      height={size}
      viewBox={entry.viewBox}
      style={style as StyleProp<never>}
      {...rest}>
      <Path d={entry.d} fill={color ?? 'currentColor'} />
    </Svg>
  );
}

export type {MaterialIconName};
