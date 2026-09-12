export let encodedCodec = '';

export function setEncodedCodec(value) {
  encodedCodec = value;
}

export class BleManager {
  async connectToDevice() {
    return {
      id: 'synthetic-device',
      async discoverAllServicesAndCharacteristics() {},
      onDisconnected() {},
      async cancelConnection() {},
      async services() {
        return [
          {
            uuid: '19b10000-e8f2-537e-4f6c-d104768a1214',
            async characteristics() {
              return [
                {
                  uuid: '19b10002-e8f2-537e-4f6c-d104768a1214',
                  async read() {
                    return { value: encodedCodec };
                  },
                },
              ];
            },
          },
        ];
      },
    };
  }
}

export class Subscription {}
export class Device {}
