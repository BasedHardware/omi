// ignore_for_file: unnecessary_getters_setters

import '/backend/schema/util/schema_util.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'index.dart';

class LocaleStruct extends BaseStruct {
  LocaleStruct({
    String? name,
    String? id,
  })  : _name = name,
        _id = id;

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

  static LocaleStruct fromMap(Map<String, dynamic> data) => LocaleStruct(
        name: data['name'] as String?,
        id: data['id'] as String?,
      );

  static LocaleStruct? maybeFromMap(dynamic data) =>
      data is Map ? LocaleStruct.fromMap(data.cast<String, dynamic>()) : null;

  Map<String, dynamic> toMap() => {
        'name': _name,
        'id': _id,
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
      }.withoutNulls;

  static LocaleStruct fromSerializableMap(Map<String, dynamic> data) =>
      LocaleStruct(
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
      );

  @override
  String toString() => 'LocaleStruct(${toMap()})';

  @override
  bool operator ==(Object other) {
    return other is LocaleStruct && name == other.name && id == other.id;
  }

  @override
  int get hashCode => const ListEquality().hash([name, id]);
}

LocaleStruct createLocaleStruct({
  String? name,
  String? id,
}) =>
    LocaleStruct(
      name: name,
      id: id,
    );
