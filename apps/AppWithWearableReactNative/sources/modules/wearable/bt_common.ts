export type BTStartResult = 'started' | 'denied' | 'failure';

export type BTDevice = {
    id: string,
    name: string,
    services: BTService[],
    connected: boolean,
    onDisconnected: (callback: () => void) => (() => void),
    disconnect: () => Promise<void>
};

export type BTService = {
    id: string,
    characteristics: BTCharacteristic[]
};

export type BTCharacteristic = {
    id: string,
    canRead: boolean,
    canWrite: boolean,
    canNotify: boolean,

    read: () => Promise<Uint8Array>,
    write: (data: Uint8Array) => Promise<void>,
    subscribe: (callback: (data: Uint8Array) => void) => (() => void)
};

export const KnownBTServices = ['19B10000-E8F2-537E-4F6C-D104768A1214'.toLowerCase()];