import {View} from 'react-native';
import type {ComponentType} from 'react';
import type {ViewProps} from 'react-native';

export function requireNativeComponent<T extends ViewProps>(
  _name: string,
): ComponentType<T> {
  return View as ComponentType<T>;
}
