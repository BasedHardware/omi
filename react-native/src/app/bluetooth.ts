export function bluetoothStatusLabel(state: string): string {
  switch (state) {
    case 'poweredOn':
      return 'Bluetooth on';
    case 'unauthorized':
      return 'Bluetooth permission needed';
    case 'unsupported':
      return 'Web Bluetooth unavailable';
    case 'available':
      return 'Browser Bluetooth available';
    case 'selected':
      return 'Browser device selected';
    case 'denied':
      return 'Bluetooth permission denied';
    case 'error':
      return 'Bluetooth check failed';
    case 'poweredOff':
      return 'Bluetooth off';
    default:
      return 'Bluetooth status unknown';
  }
}
