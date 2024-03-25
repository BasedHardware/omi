// ignore_for_file: unnecessary_getters_setters

import 'package:cloud_firestore/cloud_firestore.dart';

import '/backend/schema/util/firestore_util.dart';

import '/flutter_flow/flutter_flow_util.dart';

class LocaleStruct extends FFFirebaseStruct {
  LocaleStruct({
    String? name,
    String? id,
    FirestoreUtilData firestoreUtilData = const FirestoreUtilData(),
  })  : _name = name,
        _id = id,
        super(firestoreUtilData);

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
  Map<String, dynamic> fieldValues = const {},
  bool clearUnsetFields = true,
  bool create = false,
  bool delete = false,
}) =>
    LocaleStruct(
      name: name,
      id: id,
      firestoreUtilData: FirestoreUtilData(
        clearUnsetFields: clearUnsetFields,
        create: create,
        delete: delete,
        fieldValues: fieldValues,
      ),
    );

LocaleStruct? updateLocaleStruct(
  LocaleStruct? locale, {
  bool clearUnsetFields = true,
  bool create = false,
}) =>
    locale
      ?..firestoreUtilData = FirestoreUtilData(
        clearUnsetFields: clearUnsetFields,
        create: create,
      );

void addLocaleStructData(
  Map<String, dynamic> firestoreData,
  LocaleStruct? locale,
  String fieldName, [
  bool forFieldValue = false,
]) {
  firestoreData.remove(fieldName);
  if (locale == null) {
    return;
  }
  if (locale.firestoreUtilData.delete) {
    firestoreData[fieldName] = FieldValue.delete();
    return;
  }
  final clearFields =
      !forFieldValue && locale.firestoreUtilData.clearUnsetFields;
  if (clearFields) {
    firestoreData[fieldName] = <String, dynamic>{};
  }
  final localeData = getLocaleFirestoreData(locale, forFieldValue);
  final nestedData = localeData.map((k, v) => MapEntry('$fieldName.$k', v));

  final mergeFields = locale.firestoreUtilData.create || clearFields;
  firestoreData
      .addAll(mergeFields ? mergeNestedFields(nestedData) : nestedData);
}

Map<String, dynamic> getLocaleFirestoreData(
  LocaleStruct? locale, [
  bool forFieldValue = false,
]) {
  if (locale == null) {
    return {};
  }
  final firestoreData = mapToFirestore(locale.toMap());

  // Add any Firestore field values
  locale.firestoreUtilData.fieldValues.forEach((k, v) => firestoreData[k] = v);

  return forFieldValue ? mergeNestedFields(firestoreData) : firestoreData;
}

List<Map<String, dynamic>> getLocaleListFirestoreData(
  List<LocaleStruct>? locales,
) =>
    locales?.map((e) => getLocaleFirestoreData(e, true)).toList() ?? [];
