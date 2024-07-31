import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:encrypt/encrypt.dart' as encrypt;
import 'package:friend_private/backend/api_requests/api/server.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/database/memory_provider.dart';
import 'package:friend_private/backend/preferences.dart';

String encodeJson(List<dynamic> jsonObj, String password) {
  String jsonString = json.encode(jsonObj);
  final key = encrypt.Key.fromUtf8(sha256.convert(utf8.encode(password)).toString().substring(0, 32));
  final iv = encrypt.IV.fromSecureRandom(16); // Generate a random IV
  final encrypter = encrypt.Encrypter(encrypt.AES(key));
  final encrypted = encrypter.encrypt(jsonString, iv: iv);
  // Return the encrypted string with the IV prepended
  return '${iv.base64}:${encrypted.base64}';
}

List<dynamic> decodeJson(String encryptedJson, String password) {
  final parts = encryptedJson.split(':');
  if (parts.length != 2) {
    throw Exception('Invalid encrypted data format.');
  }
  final iv = encrypt.IV.fromBase64(parts[0]);
  final encryptedData = parts[1];

  final key = encrypt.Key.fromUtf8(sha256.convert(utf8.encode(password)).toString().substring(0, 32));
  final encrypter = encrypt.Encrypter(encrypt.AES(key));
  final decrypted = encrypter.decrypt64(encryptedData, iv: iv);
  return json.decode(decrypted);
}

// Future<String> getEncodedMemories() async {
//   var password = SharedPreferencesUtil().backupPassword;
//   if (password.isEmpty) return '';
//   var memories = MemoryProvider().getMemories();
//   return encodeJson(memories.map((e) => e.toJson()).toList(), password);
// }

// Future<bool> executeBackup() async {
//   if (!SharedPreferencesUtil().backupsEnabled) return false;
//   var result = await getEncodedMemories();
//   if (result == '') return false;
//   await getDecodedMemories(result, SharedPreferencesUtil().backupPassword);
//   SharedPreferencesUtil().lastBackupDate = DateTime.now().toIso8601String();
//   await uploadBackupApi(result);
//   return true;
// }

Future<bool> executeBackupWithUid({String? uid}) async {
  if (!SharedPreferencesUtil().backupsEnabled) return false;
  print('executeBackupWithUid: $uid');

  var memories = MemoryProvider().getMemories();
  if (memories.isEmpty) return true;
  var encoded = encodeJson(memories.map((e) => e.toJson()).toList(), uid ?? SharedPreferencesUtil().uid);
  // SharedPreferencesUtil().lastBackupDate = DateTime.now().toIso8601String();
  await uploadBackupApi(encoded);
  return true;
}

Future<List<Memory>> retrieveBackup(String uid) async {
  print('retrieveBackup: $uid');
  var retrieved = await downloadBackupApi(uid);
  if (retrieved == '') return [];
  var memories = await getDecodedMemories(retrieved, uid);
  MemoryProvider().storeMemories(memories);
  return memories;
}

Future<List<Memory>> getDecodedMemories(String encodedMemories, String password) async {
  if (password.isEmpty) return [];
  try {
    var decoded = decodeJson(encodedMemories, password);
    return decoded.map((e) => Memory.fromJson(e)).toList();
  } catch (e) {
    throw Exception('The password is incorrect.');
  }
}
