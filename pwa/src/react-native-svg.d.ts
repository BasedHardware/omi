// Use the upstream native prop contracts for shared React Native components.
// The package's .web barrel does not export SvgProps under moduleSuffixes.
export { default } from "react-native-svg/lib/typescript/elements/Svg";
export type { SvgProps } from "react-native-svg/lib/typescript/elements/Svg";
export { default as Defs } from "react-native-svg/lib/typescript/elements/Defs";
export { default as LinearGradient } from "react-native-svg/lib/typescript/elements/LinearGradient";
export { default as Rect } from "react-native-svg/lib/typescript/elements/Rect";
export { default as Stop } from "react-native-svg/lib/typescript/elements/Stop";
