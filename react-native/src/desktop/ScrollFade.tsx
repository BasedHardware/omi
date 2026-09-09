import React, {useRef, useState} from 'react';
import {
  type LayoutChangeEvent,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
  Platform,
  View,
  type ViewProps,
} from 'react-native';
import {requireNativeComponent} from '../native-component';

const FadeView =
  Platform.OS === 'macos'
    ? requireNativeComponent<ViewProps & {fadeVisible: boolean}>(
        'OmiScrollFade',
      )
    : View;

export function useScrollFade() {
  const size = useRef({height: 0, content: 0, offset: 0});
  const [visible, setVisible] = useState(false);
  const update = () =>
    setVisible(
      size.current.content > size.current.height + size.current.offset + 8,
    );
  return {
    visible,
    onLayout: (event: LayoutChangeEvent) => {
      size.current.height = event.nativeEvent.layout.height;
      update();
    },
    onContentSizeChange: (_width: number, height: number) => {
      size.current.content = height;
      update();
    },
    onScroll: (event: NativeSyntheticEvent<NativeScrollEvent>) => {
      size.current.offset = event.nativeEvent.contentOffset.y;
      update();
    },
  };
}

export function ScrollFade({
  visible,
  children,
  ...props
}: ViewProps & {visible: boolean}) {
  return (
    <FadeView {...props} fadeVisible={visible}>
      {children}
    </FadeView>
  );
}
