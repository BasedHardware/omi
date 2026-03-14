/// E2EE Service — AES-256-GCM encryption with locally-generated keys.
/// Key stored in iOS Keychain / Android EncryptedSharedPreferences.
/// Data format: base64(nonce[12] || ciphertext || tag[16]).
///
/// Architecture:
///   Enhanced: server-side encryption at rest, server can read data.
///   E2EE:     server-side encryption at rest PLUS API access requires
///             key hash verification. Server can still process data
///             internally, but external API reads require proof of key
///             possession via X-E2EE-Key-Hash header.
///
/// The SHA-256 hash of the key is sent to the server and stored so that
/// API endpoints can verify the caller has the correct key without the
/// server ever seeing the raw key bytes.

import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:pointycastle/export.dart';

import 'package:omi/utils/logger.dart';

class E2eeService {
  static final E2eeService _instance = E2eeService._internal();
  factory E2eeService() => _instance;
  E2eeService._internal();

  static const _secureStorage = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
    iOptions: IOSOptions(accessibility: KeychainAccessibility.first_unlock_this_device),
  );

  static const String _keyPrefKey = 'e2ee_encryption_key';

  Uint8List? _cachedKey;

  Future<bool> get hasKey async {
    if (_cachedKey != null) return true;
    return await _secureStorage.containsKey(key: _keyPrefKey);
  }

  /// Generate a new 256-bit AES key and persist it.
  Future<String> generateAndStoreKey() async {
    final secureRandom = SecureRandom('Fortuna')
      ..seed(KeyParameter(Uint8List.fromList(
        List.generate(32, (_) => Random.secure().nextInt(256)),
      )));

    final key = secureRandom.nextBytes(32);
    _cachedKey = key;

    await _secureStorage.write(key: _keyPrefKey, value: base64Encode(key));

    return base64Encode(key);
  }

  Future<Uint8List?> _loadKey() async {
    if (_cachedKey != null) return _cachedKey;
    final b64 = await _secureStorage.read(key: _keyPrefKey);
    if (b64 == null) return null;
    _cachedKey = base64Decode(b64);
    return _cachedKey;
  }

  /// Encrypt plaintext. Returns base64(nonce[12] || ciphertext || tag[16]).
  Future<String> encrypt(String plaintext) async {
    if (plaintext.isEmpty) return plaintext;

    final key = await _loadKey();
    if (key == null) throw StateError('E2EE key not initialized.');

    final nonce = Uint8List.fromList(
      List.generate(12, (_) => Random.secure().nextInt(256)),
    );

    final cipher = GCMBlockCipher(AESEngine())
      ..init(
        true,
        AEADParameters(
          KeyParameter(key),
          128,
          nonce,
          Uint8List(0),
        ),
      );

    final plaintextBytes = Uint8List.fromList(utf8.encode(plaintext));
    final ciphertext = cipher.process(plaintextBytes);

    final output = Uint8List(nonce.length + ciphertext.length);
    output.setAll(0, nonce);
    output.setAll(nonce.length, ciphertext);

    return base64Encode(output);
  }

  /// Decrypt a base64 AES-256-GCM payload. Returns plaintext on success,
  /// passes through non-E2EE data, throws on key mismatch.
  Future<String> decrypt(String encrypted) async {
    if (encrypted.isEmpty) return encrypted;

    final key = await _loadKey();
    if (key == null) throw StateError('E2EE key not initialized.');

    Uint8List payload;
    try {
      payload = base64Decode(encrypted);
    } catch (_) {
      return encrypted;
    }

    if (payload.length < 28) {
      return encrypted;
    }

    final nonce = Uint8List.sublistView(payload, 0, 12);
    final ciphertextWithTag = Uint8List.sublistView(payload, 12);

    final cipher = GCMBlockCipher(AESEngine())
      ..init(
        false,
        AEADParameters(
          KeyParameter(key),
          128,
          nonce,
          Uint8List(0),
        ),
      );

    try {
      final decrypted = cipher.process(ciphertextWithTag);
      return utf8.decode(decrypted);
    } catch (e) {
      Logger.error('[E2EE] Decryption failed: $e');
      throw StateError('E2EE decryption failed. Recovery key may not match.');
    }
  }

  Future<String?> exportKey() async {
    final key = await _loadKey();
    if (key == null) return null;
    return base64Encode(key);
  }

  Future<void> importKey(String base64Key) async {
    final key = base64Decode(base64Key);
    if (key.length != 32) {
      throw ArgumentError('Invalid key length. Expected 32 bytes.');
    }
    _cachedKey = Uint8List.fromList(key);
    await _secureStorage.write(key: _keyPrefKey, value: base64Key);
  }

  Future<String?> getKeyHash() async {
    final key = await _loadKey();
    if (key == null) return null;
    return sha256.convert(key).toString();
  }

  Future<void> clearKey() async {
    _cachedKey = null;
    await _secureStorage.delete(key: _keyPrefKey);
  }
}
