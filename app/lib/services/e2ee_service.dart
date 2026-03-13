/// End-to-End Encryption (E2EE) Service
///
/// This service manages client-side AES-256-GCM encryption for user data.
/// The encryption key is generated locally and NEVER sent to the server.
///
/// Architecture:
/// - Key is generated using a cryptographically secure random number generator
/// - Key stored in iOS Keychain / Android EncryptedSharedPreferences (hardware-backed on supported devices)
/// - Data format: base64(nonce[12] || ciphertext || tag[16])
/// - Compatible with the server-side AES-256-GCM format in backend/utils/encryption.py
///
/// The server stores encrypted data as opaque blobs. It cannot decrypt E2EE data.
/// Users MUST back up their key — if lost, data is unrecoverable.

import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:pointycastle/export.dart';

class E2eeService {
  static final E2eeService _instance = E2eeService._internal();
  factory E2eeService() => _instance;
  E2eeService._internal();

  // Key stored in iOS Keychain / Android EncryptedSharedPreferences (hardware-backed on supported devices)
  static const _secureStorage = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
    iOptions: IOSOptions(accessibility: KeychainAccessibility.first_unlock_this_device),
  );

  static const String _keyPrefKey = 'e2ee_encryption_key';

  Uint8List? _cachedKey;

  /// Whether an E2EE key exists (i.e., E2EE has been enabled).
  Future<bool> get hasKey async {
    if (_cachedKey != null) return true;
    return await _secureStorage.containsKey(key: _keyPrefKey);
  }

  /// Generate a new 256-bit AES key and persist it.
  /// Call this once when the user enables E2EE.
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

  /// Load the key from storage into memory cache.
  Future<Uint8List?> _loadKey() async {
    if (_cachedKey != null) return _cachedKey;
    final b64 = await _secureStorage.read(key: _keyPrefKey);
    if (b64 == null) return null;
    _cachedKey = base64Decode(b64);
    return _cachedKey;
  }

  /// Encrypt plaintext using AES-256-GCM.
  /// Returns base64(nonce[12] || ciphertext || tag[16]).
  Future<String> encrypt(String plaintext) async {
    if (plaintext.isEmpty) return plaintext;

    final key = await _loadKey();
    if (key == null) throw StateError('E2EE key not initialized. Call generateAndStoreKey() first.');

    // Generate 12-byte random nonce
    final nonce = Uint8List.fromList(
      List.generate(12, (_) => Random.secure().nextInt(256)),
    );

    final cipher = GCMBlockCipher(AESEngine())
      ..init(
        true, // encrypt
        AEADParameters(
          KeyParameter(key),
          128, // tag length in bits
          nonce,
          Uint8List(0), // no additional authenticated data
        ),
      );

    final plaintextBytes = Uint8List.fromList(utf8.encode(plaintext));
    final ciphertext = cipher.process(plaintextBytes);

    // ciphertext from PointyCastle GCM includes the 16-byte tag appended
    // Output format: nonce(12) + ciphertext + tag(16) — matches server format
    final output = Uint8List(nonce.length + ciphertext.length);
    output.setAll(0, nonce);
    output.setAll(nonce.length, ciphertext);

    return base64Encode(output);
  }

  /// Decrypt a base64-encoded AES-256-GCM payload.
  /// Expects format: base64(nonce[12] || ciphertext || tag[16]).
  ///
  /// If the input doesn't look like valid E2EE data (not valid base64, or too short),
  /// it is returned as-is for backward compatibility with unencrypted data.
  /// If the input IS valid E2EE data but decryption fails (wrong key, corruption),
  /// a [StateError] is thrown — callers should handle this explicitly.
  Future<String> decrypt(String encrypted) async {
    if (encrypted.isEmpty) return encrypted;

    final key = await _loadKey();
    if (key == null) throw StateError('E2EE key not initialized.');

    // Check if this looks like base64-encoded E2EE data
    Uint8List payload;
    try {
      payload = base64Decode(encrypted);
    } catch (_) {
      // Not valid base64 — likely unencrypted plaintext, return as-is
      return encrypted;
    }

    if (payload.length < 28) {
      // Too short for nonce(12) + tag(16) + any ciphertext — likely not E2EE data
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
      // GCM authentication failed — wrong key or corrupted data
      // This is a real error for E2EE data, not a graceful fallback case
      print('[E2EE] Decryption failed — possible key mismatch or data corruption: $e');
      throw StateError('E2EE decryption failed. Your recovery key may not match. Error: $e');
    }
  }

  /// Export the current key as a base64 string for user backup.
  Future<String?> exportKey() async {
    final key = await _loadKey();
    if (key == null) return null;
    return base64Encode(key);
  }

  /// Import a key from a base64 string (key recovery).
  Future<void> importKey(String base64Key) async {
    final key = base64Decode(base64Key);
    if (key.length != 32) {
      throw ArgumentError('Invalid key length. Expected 32 bytes (256-bit AES key).');
    }
    _cachedKey = Uint8List.fromList(key);
    await _secureStorage.write(key: _keyPrefKey, value: base64Key);
  }

  /// Clear the stored key. Used if user disables E2EE (data must be re-encrypted server-side first).
  Future<void> clearKey() async {
    _cachedKey = null;
    await _secureStorage.delete(key: _keyPrefKey);
  }
}
