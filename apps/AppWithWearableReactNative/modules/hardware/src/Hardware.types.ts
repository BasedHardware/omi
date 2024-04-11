export type L2CAPState = {
  kind: 'idle'
} | {
  kind: 'connected',
};

export type ModuleType = {
  startAsync(): Promise<void>;
  stopAsync(): Promise<void>;
  connectAsync(device: string, psm: number): Promise<void>
  disconnectAsync(): Promise<void>;
};