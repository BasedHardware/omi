import { DeviceController } from '../domain/DeviceController.ts';
import type { DeviceState } from '../domain/DeviceController.ts';

export interface DeviceListScreenProps {
  controller: DeviceController;
}

export function renderDeviceListScreenSketch(props: DeviceListScreenProps): string {
  const devices = props.controller.getDevices();
  let output = '[React Native Screen Sketch: Device List]\n';
  if (devices.length === 0) {
    output += '  (No devices registered)\n';
    return output;
  }
  for (const dev of devices) {
    output += `  Device: ${dev.name} [${dev.id}] (${dev.type})\n`;
    output += `    Status: ${dev.status.toUpperCase()} | Valid Packets: ${dev.validPacketCount} | Corrupt: ${dev.corruptPacketCount}\n`;
    if (dev.lastChecksum !== undefined) {
      output += `    Last Checksum: 0x${dev.lastChecksum.toString(16).padStart(8, '0')}\n`;
    }
  }
  return output;
}
