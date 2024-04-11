// import { BTDevice, BTService, BTStartResult, KnownBTServices } from "./bt_common";

// export async function startBluetooth(): Promise<BTStartResult> {
//     // if (await navigator.bluetooth.getAvailability()) {
//     //     return 'failure';
//     // } else {
//     //     return 'started';
//     // }
//     return 'started';
// }

// export async function openDevice(params: { name: string } | { services: string[] }): Promise<BTDevice | null> {

//     // Request device
//     let device: BluetoothDevice | null = null;
//     try {
//         device = await navigator.bluetooth.requestDevice({
//             filters: 'name' in params ? [{ name: params.name }] : [{ services: params.services }],
//             optionalServices: KnownBTServices
//         });
//     } catch (e) {
//         console.error(e);
//         return null;
//     }

//     // Check if gatt is available
//     if (!device.gatt) {
//         console.error('Gatt is not available');
//         return null;
//     }

//     // Extract device
//     let id = device.id;
//     let name = device.name || 'Unknown';
//     let services: BTService[] = [];

//     // Connect to gatt
//     let gatt = await device.gatt.connect();
//     let btservices = await gatt.getPrimaryServices();
//     for (let s of btservices) {
//         let ch = await s.getCharacteristics();
//         let subsciptionsCount = 0;
//         let characteristics = ch.map(c => {
//             return {
//                 id: c.uuid,
//                 canRead: c.properties.read,
//                 canWrite: c.properties.write,
//                 canNotify: c.properties.notify,
//                 read: async () => {
//                     let value = await c.readValue();
//                     return new Uint8Array(value.buffer);
//                 },
//                 write: async (data: Uint8Array) => {
//                     await c.writeValue(data);
//                 },
//                 subscribe: (callback: (data: Uint8Array) => void) => {
//                     c.addEventListener('characteristicvaluechanged', (e) => {
//                         let value = (e.target as BluetoothRemoteGATTCharacteristic).value!;
//                         callback(new Uint8Array(value.buffer));
//                     });
//                     if (subsciptionsCount === 0) {
//                         c.startNotifications();
//                     }
//                     subsciptionsCount++;
//                     let exited = false;
//                     return () => {
//                         if (exited) {
//                             return;
//                         }
//                         exited = true;
//                         c.removeEventListener('characteristicvaluechanged', () => { });
//                         subsciptionsCount--;
//                         if (subsciptionsCount === 0) {
//                             c.stopNotifications();
//                         }
//                     };
//                 }
//             };
//         });
//         services.push({
//             id: s.uuid,
//             characteristics
//         });
//     }

//     return {
//         id,
//         name,
//         services,
//         close: () => {
//             gatt.disconnect();
//         }
//     };
// }