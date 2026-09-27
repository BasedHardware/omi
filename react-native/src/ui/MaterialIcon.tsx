import React from 'react';
import {
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
  return (
    <Text
      allowFontScaling={false}
      {...rest}
      style={[
        {
          fontFamily: 'Material Symbols Rounded',
          fontSize: size,
          lineHeight: size * 1.2,
          color,
        },
        style,
      ]}>
      {String.fromCodePoint(GLYPHS[name])}
    </Text>
  );
}
