import {NativeEventEmitter, NativeModules, Platform} from 'react-native';

type Subscription = {remove(): void};
type DesktopCommandsModule = {
  addListener(eventName: string): void;
  removeListeners(count: number): void;
};

export function subscribeDesktopSearchCommand(
  listener: () => void,
): Subscription {
  const module = NativeModules.OmiDesktopCommands as
    | DesktopCommandsModule
    | undefined;
  if (Platform.OS !== 'macos' || module === undefined) {
    return {remove: () => undefined};
  }
  return new NativeEventEmitter(module).addListener(
    'desktopSearchCommand',
    listener,
  );
}
