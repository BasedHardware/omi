import 'dart:async';

import 'package:collection/collection.dart';

import '/backend/schema/util/firestore_util.dart';

import 'index.dart';

class UsersRecord extends FirestoreRecord {
  UsersRecord._(
    super.reference,
    super.data,
  ) {
    _initializeFields();
  }

  // "email" field.
  String? _email;
  String get email => _email ?? '';
  bool hasEmail() => _email != null;

  // "display_name" field.
  String? _displayName;
  String get displayName => _displayName ?? '';
  bool hasDisplayName() => _displayName != null;

  // "photo_url" field.
  String? _photoUrl;
  String get photoUrl => _photoUrl ?? '';
  bool hasPhotoUrl() => _photoUrl != null;

  // "uid" field.
  String? _uid;
  String get uid => _uid ?? '';
  bool hasUid() => _uid != null;

  // "created_time" field.
  DateTime? _createdTime;
  DateTime? get createdTime => _createdTime;
  bool hasCreatedTime() => _createdTime != null;

  // "phone_number" field.
  String? _phoneNumber;
  String get phoneNumber => _phoneNumber ?? '';
  bool hasPhoneNumber() => _phoneNumber != null;

  // "audio" field.
  String? _audio;
  String get audio => _audio ?? '';
  bool hasAudio() => _audio != null;

  // "password" field.
  String? _password;
  String get password => _password ?? '';
  bool hasPassword() => _password != null;

  // "messages" field.
  DocumentReference? _messages;
  DocumentReference? get messages => _messages;
  bool hasMessages() => _messages != null;

  // "memoriesRef" field.
  List<DocumentReference>? _memoriesRef;
  List<DocumentReference> get memoriesRef => _memoriesRef ?? const [];
  bool hasMemoriesRef() => _memoriesRef != null;

  // "speechIsRunning" field.
  bool? _speechIsRunning;
  bool get speechIsRunning => _speechIsRunning ?? false;
  bool hasSpeechIsRunning() => _speechIsRunning != null;

  // "lastDailySummaryShown" field.
  DateTime? _lastDailySummaryShown;
  DateTime? get lastDailySummaryShown => _lastDailySummaryShown;
  bool hasLastDailySummaryShown() => _lastDailySummaryShown != null;

  // "summaries" field.
  List<DocumentReference>? _summaries;
  List<DocumentReference> get summaries => _summaries ?? const [];
  bool hasSummaries() => _summaries != null;

  // "lastWeeklySummaryShown" field.
  DateTime? _lastWeeklySummaryShown;
  DateTime? get lastWeeklySummaryShown => _lastWeeklySummaryShown;
  bool hasLastWeeklySummaryShown() => _lastWeeklySummaryShown != null;

  // "lastMonthlySummaryShown" field.
  DateTime? _lastMonthlySummaryShown;
  DateTime? get lastMonthlySummaryShown => _lastMonthlySummaryShown;
  bool hasLastMonthlySummaryShown() => _lastMonthlySummaryShown != null;

  void _initializeFields() {
    _email = snapshotData['email'] as String?;
    _displayName = snapshotData['display_name'] as String?;
    _photoUrl = snapshotData['photo_url'] as String?;
    _uid = snapshotData['uid'] as String?;
    _createdTime = snapshotData['created_time'] as DateTime?;
    _phoneNumber = snapshotData['phone_number'] as String?;
    _audio = snapshotData['audio'] as String?;
    _password = snapshotData['password'] as String?;
    _messages = snapshotData['messages'] as DocumentReference?;
    _memoriesRef = getDataList(snapshotData['memoriesRef']);
    _speechIsRunning = snapshotData['speechIsRunning'] as bool?;
    _lastDailySummaryShown = snapshotData['lastDailySummaryShown'] as DateTime?;
    _summaries = getDataList(snapshotData['summaries']);
    _lastWeeklySummaryShown =
        snapshotData['lastWeeklySummaryShown'] as DateTime?;
    _lastMonthlySummaryShown =
        snapshotData['lastMonthlySummaryShown'] as DateTime?;
  }

  static CollectionReference get collection =>
      FirebaseFirestore.instance.collection('users');

  static Stream<UsersRecord> getDocument(DocumentReference ref) =>
      ref.snapshots().map((s) => UsersRecord.fromSnapshot(s));

  static Future<UsersRecord> getDocumentOnce(DocumentReference ref) =>
      ref.get().then((s) => UsersRecord.fromSnapshot(s));

  static UsersRecord fromSnapshot(DocumentSnapshot snapshot) => UsersRecord._(
        snapshot.reference,
        mapFromFirestore(snapshot.data() as Map<String, dynamic>),
      );

  static UsersRecord getDocumentFromData(
    Map<String, dynamic> data,
    DocumentReference reference,
  ) =>
      UsersRecord._(reference, mapFromFirestore(data));

  @override
  String toString() =>
      'UsersRecord(reference: ${reference.path}, data: $snapshotData)';

  @override
  int get hashCode => reference.path.hashCode;

  @override
  bool operator ==(other) =>
      other is UsersRecord &&
      reference.path.hashCode == other.reference.path.hashCode;
}

Map<String, dynamic> createUsersRecordData({
  String? email,
  String? displayName,
  String? photoUrl,
  String? uid,
  DateTime? createdTime,
  String? phoneNumber,
  String? audio,
  String? password,
  DocumentReference? messages,
  bool? speechIsRunning,
  DateTime? lastDailySummaryShown,
  DateTime? lastWeeklySummaryShown,
  DateTime? lastMonthlySummaryShown,
}) {
  final firestoreData = mapToFirestore(
    <String, dynamic>{
      'email': email,
      'display_name': displayName,
      'photo_url': photoUrl,
      'uid': uid,
      'created_time': createdTime,
      'phone_number': phoneNumber,
      'audio': audio,
      'password': password,
      'messages': messages,
      'speechIsRunning': speechIsRunning,
      'lastDailySummaryShown': lastDailySummaryShown,
      'lastWeeklySummaryShown': lastWeeklySummaryShown,
      'lastMonthlySummaryShown': lastMonthlySummaryShown,
    }.withoutNulls,
  );

  return firestoreData;
}

class UsersRecordDocumentEquality implements Equality<UsersRecord> {
  const UsersRecordDocumentEquality();

  @override
  bool equals(UsersRecord? e1, UsersRecord? e2) {
    const listEquality = ListEquality();
    return e1?.email == e2?.email &&
        e1?.displayName == e2?.displayName &&
        e1?.photoUrl == e2?.photoUrl &&
        e1?.uid == e2?.uid &&
        e1?.createdTime == e2?.createdTime &&
        e1?.phoneNumber == e2?.phoneNumber &&
        e1?.audio == e2?.audio &&
        e1?.password == e2?.password &&
        e1?.messages == e2?.messages &&
        listEquality.equals(e1?.memoriesRef, e2?.memoriesRef) &&
        e1?.speechIsRunning == e2?.speechIsRunning &&
        e1?.lastDailySummaryShown == e2?.lastDailySummaryShown &&
        listEquality.equals(e1?.summaries, e2?.summaries) &&
        e1?.lastWeeklySummaryShown == e2?.lastWeeklySummaryShown &&
        e1?.lastMonthlySummaryShown == e2?.lastMonthlySummaryShown;
  }

  @override
  int hash(UsersRecord? e) => const ListEquality().hash([
        e?.email,
        e?.displayName,
        e?.photoUrl,
        e?.uid,
        e?.createdTime,
        e?.phoneNumber,
        e?.audio,
        e?.password,
        e?.messages,
        e?.memoriesRef,
        e?.speechIsRunning,
        e?.lastDailySummaryShown,
        e?.summaries,
        e?.lastWeeklySummaryShown,
        e?.lastMonthlySummaryShown
      ]);

  @override
  bool isValidKey(Object? o) => o is UsersRecord;
}
