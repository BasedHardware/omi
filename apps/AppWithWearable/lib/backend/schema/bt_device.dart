// ignore_for_file: unnecessary_getters_setters

// TODO: go
class BTDeviceStruct {
  BTDeviceStruct({
    String? name,
    String? id,
    int? rssi,
  })  : _name = name,
        _id = id,
        _rssi = rssi;

  // "name" field.
  String? _name;

  String get name => _name ?? '';

  set name(String? val) => _name = val;

  bool hasName() => _name != null;

  // "id" field.
  String? _id;

  String get id => _id ?? '';

  set id(String? val) => _id = val;

  bool hasId() => _id != null;

  // "rssi" field.
  int? _rssi;

  int get rssi => _rssi ?? 0;

  set rssi(int? val) => _rssi = val;

  void incrementRssi(int amount) => _rssi = rssi + amount;

  bool hasRssi() => _rssi != null;

  static BTDeviceStruct fromMap(Map<String, dynamic> data) => BTDeviceStruct(
        name: data['name'] as String?,
        id: data['id'] as String?,
        rssi: castToType<int>(data['rssi']),
      );

  static BTDeviceStruct? maybeFromMap(dynamic data) =>
      data is Map ? BTDeviceStruct.fromMap(data.cast<String, dynamic>()) : null;

  Map<String, dynamic> toMap() => {
        'name': _name,
        'id': _id,
        'rssi': _rssi,
      }.withoutNulls;

  @override
  String toString() => 'BTDeviceStruct(${toMap()})';
}

BTDeviceStruct createBTDeviceStruct({
  String? name,
  String? id,
  int? rssi,
}) =>
    BTDeviceStruct(
      name: name,
      id: id,
      rssi: rssi,
    );
