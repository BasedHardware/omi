import { EventEmitter } from 'expo-modules-core';
import { ModuleType } from './Hardware.types';

const emitter = new EventEmitter({} as any);

export default {
  async startAsync(): Promise<void> {
    // noop
  },
  async stopAsync(): Promise<void> {
    // noop
  },
  async connectAsync(device: string, psm: number): Promise<void> {
    // noop
  },
  async disconnectAsync(): Promise<void> {
    // noop
  }
} satisfies ModuleType;
