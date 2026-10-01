import type {StyleProp, TextStyle} from 'react-native';

export type ChatMessageContentProps = {
  text: string;
  style?: StyleProp<TextStyle>;
  streaming?: boolean;
  reduceMotion?: boolean;
};
