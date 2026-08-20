declare module "react-native-svg" {
  import type { ViewProps } from "react-native";

  export type SvgProps = ViewProps & {
    color?: string;
    fill?: string;
    stroke?: string;
    strokeWidth?: number | string;
  };
}
