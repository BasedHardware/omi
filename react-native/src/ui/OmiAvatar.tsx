import React, {useEffect, useRef} from 'react';
import {Animated, Easing, View} from 'react-native';
import {styles} from './styles';

export function omiDotColor(identity: string, index: number): string {
  let hash = 2166136261;
  for (let cursor = 0; cursor < identity.length; cursor += 1) {
    hash ^= identity.charCodeAt(cursor);
    hash = Math.imul(hash, 16777619);
  }
  const hue = (hash + index * 43) >>> 0;
  return `hsl(${hue % 360}, 84%, 66%)`;
}

const omiDotPoses = [
  {ring: {left: 17.5, top: 3.5}, smile: {left: 10, top: 12}},
  {ring: {left: 27.5, top: 7.5}, smile: {left: 26, top: 12}},
  {ring: {left: 31.5, top: 17.5}, smile: {left: 28, top: 23}},
  {ring: {left: 27.5, top: 27.5}, smile: {left: 25, top: 27}},
  {ring: {left: 17.5, top: 31.5}, smile: {left: 21, top: 30}},
  {ring: {left: 7.5, top: 27.5}, smile: {left: 15, top: 30}},
  {ring: {left: 3.5, top: 17.5}, smile: {left: 11, top: 27}},
  {ring: {left: 7.5, top: 7.5}, smile: {left: 8, top: 23}},
] as const;

function OmiAvatar({
  animate = false,
  identity = 'omi',
  reduceMotion = false,
}: {
  animate?: boolean;
  identity?: string;
  reduceMotion?: boolean;
}) {
  const smileProgress = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    smileProgress.setValue(0);
    if (!animate || reduceMotion) {
      return;
    }
    const animation = Animated.loop(
      Animated.sequence([
        Animated.timing(smileProgress, {
          duration: 520,
          easing: Easing.out(Easing.cubic),
          toValue: 1,
          useNativeDriver: true,
        }),
        Animated.timing(smileProgress, {
          duration: 900,
          easing: Easing.out(Easing.cubic),
          toValue: 0,
          useNativeDriver: true,
        }),
      ]),
    );
    animation.start();
    return () => animation.stop();
  }, [animate, reduceMotion, smileProgress]);

  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={styles.chatAvatar}>
      {omiDotPoses.map(({ring, smile}, index) => {
        const translateX = smileProgress.interpolate({
          inputRange: [0, 1],
          outputRange: [0, smile.left - ring.left],
        });
        const translateY = smileProgress.interpolate({
          inputRange: [0, 1],
          outputRange: [0, smile.top - ring.top],
        });
        return (
          <Animated.View
            key={index}
            style={[
              styles.chatAvatarDot,
              {backgroundColor: omiDotColor(identity, index)},
              ring,
              {transform: [{translateX}, {translateY}]},
            ]}
          />
        );
      })}
    </View>
  );
}

export {OmiAvatar};
