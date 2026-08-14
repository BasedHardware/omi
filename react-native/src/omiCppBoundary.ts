import {NativeModules} from 'react-native';

export type OmiCppCapabilities = {
  simd: boolean;
  abi_version: number;
  max_packet_bytes: number;
};

type OmiCppBoundaryNative = {
  normalizePacket(rawData: number[]): Promise<number[]>;
  getNativeCapabilities(): Promise<OmiCppCapabilities>;
};

export const omiCppBoundary = NativeModules.OmiCppBoundary as
  | OmiCppBoundaryNative
  | undefined;

export const isCppBoundaryInstalled = Boolean(omiCppBoundary);
