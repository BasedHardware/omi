import 'dart:convert';

const int storedDeviceNameVersion = 1;
const int maxStoredDeviceNameBytes = 128;

List<int>? encodeStoredDeviceName(String name) {
  final bytes = utf8.encode(name.trim());
  if (bytes.length > maxStoredDeviceNameBytes) return null;
  return [storedDeviceNameVersion, ...bytes];
}

String? decodeStoredDeviceName(List<int> value) {
  if (value.isEmpty || value.first != storedDeviceNameVersion) return null;
  return utf8.decode(value.sublist(1), allowMalformed: true).trim();
}
