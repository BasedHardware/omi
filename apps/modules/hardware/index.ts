import { NativeModulesProxy, EventEmitter } from 'expo-modules-core';
import HardwareModule from './src/HardwareModule';
import { L2CAPState } from './src/Hardware.types';

const emitter = new EventEmitter((HardwareModule ?? NativeModulesProxy.Hardware) as any);

// export function addChangeListener(listener: (event: ChangeEventPayload) => void): Subscription {
//   return emitter.addListener<ChangeEventPayload>('onChange', listener);
// }

// export { HardwareViewProps, ChangeEventPayload };

export async function startAsync(): Promise<void> {
  await HardwareModule.startAsync();
}

export async function stopAsync(): Promise<void> {
  await HardwareModule.stopAsync();
}

export async function connectAsync(uuid: string, psm: number): Promise<void> {
  await HardwareModule.connectAsync(uuid, psm);
}

export async function disconnectAsync(): Promise<void> {
  await HardwareModule.disconnectAsync();
}