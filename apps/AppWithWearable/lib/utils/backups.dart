import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:encrypt/encrypt.dart' as encrypt;
import 'package:friend_private/backend/api_requests/api_calls.dart';
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

Future<String> getEncodedMemories() async {
  var password = SharedPreferencesUtil().backupPassword;
  if (password.isEmpty) return '';
  var memories = await MemoryProvider().getMemories();
  return encodeJson(memories.map((e) => e.toJson()).toList(), password);
}

Future<bool> executeBackup() async {
  var result = await getEncodedMemories();
  print(result);
  if (result == '') return false;
  await getDecodedMemories(result);
  SharedPreferencesUtil().lastBackupDate = DateTime.now().toIso8601String();
  await uploadBackupApi(result);
  return true;
}

Future<bool> retrieveBackup(String uid, String password) async {
  var retrieved = await downloadBackupApi(uid);
  if (retrieved == '') return false;
  var memories = await getDecodedMemories(retrieved);
  // TODO: password doesn't work, throw exception
  await MemoryProvider().storeMemories(memories);
  return true;
}

Future<List<Memory>> getDecodedMemories(String encodedMemories) async {
  var password = SharedPreferencesUtil().backupPassword;
  if (password.isEmpty) return [];
  var decoded = decodeJson(encodedMemories, password);
  return decoded.map((e) => Memory.fromJson(e)).toList();
}
