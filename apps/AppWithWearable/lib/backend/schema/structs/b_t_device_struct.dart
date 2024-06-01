// ignore_for_file: unnecessary_getters_setters

import '/backend/schema/util/schema_util.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'index.dart';

class BTDeviceStruct extends BaseStruct {
  BTDeviceStruct({
    String? name,
    String? id,
    int? rssi,
    int? fwver,
  })  : _name = name,
        _id = id,
        _rssi = rssi,
        _fwver = fwver;

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

  // "fwver" field.
  int? _fwver;
  int get fwver => _fwver ?? 0;
  set fwver(int? val) => _fwver = val;
  bool hasFwver() => _fwver != null;

  static BTDeviceStruct fromMap(Map<String, dynamic> data) => BTDeviceStruct(
        name: data['name'] as String?,
        id: data['id'] as String?,
        rssi: castToType<int>(data['rssi']),
        fwver: castToType<int>(data['fwver']),
      );

  static BTDeviceStruct? maybeFromMap(dynamic data) =>
      data is Map ? BTDeviceStruct.fromMap(data.cast<String, dynamic>()) : null;

  Map<String, dynamic> toMap() => {
        'name': _name,
        'id': _id,
        'rssi': _rssi,
        'fwver': _fwver,
      }.withoutNulls;

  @override
  Map<String, dynamic> toSerializableMap() => {
        'name': serializeParam(
          _name,
          ParamType.String,
        ),
        'id': serializeParam(
          _id,
          ParamType.String,
        ),
        'rssi': serializeParam(
          _rssi,
          ParamType.int,
        ),
        'fwver': serializeParam(
          _fwver,
          ParamType.int,
        )
      }.withoutNulls;

  static BTDeviceStruct fromSerializableMap(Map<String, dynamic> data) =>
      BTDeviceStruct(
        name: deserializeParam(
          data['name'],
          ParamType.String,
          false,
        ),
        id: deserializeParam(
          data['id'],
          ParamType.String,
          false,
        ),
        rssi: deserializeParam(
          data['rssi'],
          ParamType.int,
          false,
        ),
        fwver: deserializeParam(
          data['fwver'],
          ParamType.int,
          false,
        ),
      );

  @override
  String toString() => 'BTDeviceStruct(${toMap()})';

  @override
  bool operator ==(Object other) {
    return other is BTDeviceStruct &&
        name == other.name &&
        id == other.id &&
        rssi == other.rssi &&
        fwver == other.fwver;
  }

  @override
  int get hashCode => const ListEquality().hash([name, id, rssi]);
}

BTDeviceStruct createBTDeviceStruct({
  String? name,
  String? id,
  int? rssi,
  int? fwver,
}) =>
    BTDeviceStruct(
      name: name,
      id: id,
      rssi: rssi,
      fwver: fwver,
    );
