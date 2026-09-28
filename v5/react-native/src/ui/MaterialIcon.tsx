import React from 'react';
import {
  Platform,
  Text,
  type StyleProp,
  type TextProps,
  type TextStyle,
} from 'react-native';

// Material Symbols Rounded (variable font) is bundled with both app targets
// (macOS: Resources/, iOS: UIAppFonts). Glyphs are addressed by codepoint
// from the official codepoints table, so names below match Google's names.
const GLYPHS = {
  arrow_outward: 0xf8ce,
  arrow_selector_tool: 0xf82f,
  arrow_upward: 0xe5d8,
  graphic_eq: 0xe1b8,
  auto_awesome: 0xe65f,
  book: 0xe86e,
  calendar_month: 0xebcc,
  chat: 0xe0c9,
  chat_bubble: 0xe0cb,
  check: 0xe668,
  check_circle: 0xf0be,
  checklist: 0xe6b1,
  chevron_left: 0xe5cb,
  close: 0xe5cd,
  edit: 0xf097,
  expand_more: 0xe5cf,
  extension: 0xe87b,
  filter_list: 0xe152,
  folder: 0xe2c7,
  history: 0xe8b3,
  home: 0xe9b2,
  info: 0xe88e,
  keyboard_command_key: 0xeae7,
  left_panel_close: 0xf717,
  left_panel_open: 0xf716,
  mail: 0xe159,
  mic: 0xe31d,
  monitor: 0xef5b,
  neurology: 0xe10e,
  notifications: 0xe7f5,
  orbit: 0xf426,
  person: 0xf0d3,
  phone_disabled: 0xe9cc,
  search: 0xef7a,
  settings: 0xe8b8,
  stop: 0xe047,
  terminal: 0xeb8e,
  verified_user: 0xf013,
  view_timeline: 0xeb85,
  // Mobile shell (tab bar, grouped settings rows, device pill).
  forum: 0xe0bf,
  chevron_right: 0xe5cc,
  open_in_new: 0xe89e,
  logout: 0xe9ba,
  bluetooth: 0xe1a7,
} as const;

export type MaterialIconName = keyof typeof GLYPHS;

type Props = {
  name: MaterialIconName;
  size?: number;
  color?: string;
  /** Accepted for API parity with the old lucide icons; color wins. */
  fill?: string;
  style?: StyleProp<TextStyle>;
} & TextProps;

export function MaterialIcon({
  name,
  size = 16,
  color,
  fill,
  style,
  ...rest
}: Props) {
  // `fill` is accepted only for call-site parity with the old lucide icons;
  // it is deliberately not forwarded — RN macOS throws
  // "NULL CGColor argument in colorWithCGColor:" for Text color props like a
  // transparent fill.
  void fill;
  // Material Symbols Rounded rides ~12% of the glyph size above center under
  // CoreText (macOS/iOS) even with lineHeight pinned to the font size —
  // measured on the shipping chrome (filter chips render ~1.5–2 px high at
  // size 14). Nudge the ink down so flex centering in pills puts it
  // dead-center. Browsers center half-leading symmetrically, so web keeps 0.
  const coreTextNudge =
    Platform.OS === 'macos' || Platform.OS === 'ios' ? size * 0.125 : 0;
  return (
    <Text
      allowFontScaling={false}
      {...rest}
      style={[
        {
          fontFamily: 'Material Symbols Rounded',
          fontSize: size,
          // Icon glyphs carry no real descenders: a tight line box lets the
          // flex centering in buttons/pills place the ink dead-center instead
          // of riding 2–4px high the way extra leading pushes it.
          lineHeight: size,
          textAlign: 'center',
          color,
          transform: [{translateY: coreTextNudge}],
        },
        style,
      ]}>
      {String.fromCodePoint(GLYPHS[name])}
    </Text>
  );
}
