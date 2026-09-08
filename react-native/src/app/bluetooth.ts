const bluetoothWireEventTokens = new Set([
  'poweredOn',
  'poweredOff',
  'unauthorized',
  'unknown',
]);

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

export function emptyDeviceListHint(
  event: string | null | undefined,
  bluetooth: string,
  scanBusy = false,
): string {
  const trimmed = event?.trim() ?? '';
  const match = /^Bluetooth is ([A-Za-z]+)$/.exec(trimmed);
  const wireToken =
    match !== null && bluetoothWireEventTokens.has(match[1]) ? match[1] : null;
  if (
    trimmed === 'Bluetooth is powered on' ||
    wireToken === 'poweredOn' ||
    (trimmed === '' && bluetooth === 'poweredOn')
  ) {
    return 'No Omi device was discovered.';
  }
  if (trimmed === 'Bluetooth is not powered on') {
    return bluetoothStatusLabel('poweredOff');
  }
  if (trimmed === 'Bluetooth permission is required') {
    return bluetoothStatusLabel('unauthorized');
  }
  if (trimmed === 'Bluetooth is unavailable') {
    return emptyDeviceListHint('', bluetooth, scanBusy);
  }
  if (trimmed === '' || wireToken !== null) {
    return bluetoothStatusLabel(wireToken ?? bluetooth);
  }
  const statusCode = /^(.+ failed): \d+$/.exec(trimmed);
  if (statusCode !== null) {
    return statusCode[1] === 'BLE scan failed'
      ? 'Bluetooth scan failed.'
      : `${statusCode[1]}.`;
  }
  if (trimmed === 'Scanning for Omi devices' && !scanBusy) {
    return 'No Omi device was discovered.';
  }
  return trimmed;
}
