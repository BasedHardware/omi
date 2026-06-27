// Encryption utilities - Port from Python backend utils/encryption.py
// Used to encrypt/decrypt user data with enhanced protection level (AES-256-GCM)

use aes_gcm::{
    aead::{Aead, KeyInit, OsRng},
    AeadCore, Aes256Gcm, Nonce,
};
use base64::{engine::general_purpose::STANDARD as BASE64, Engine};
use hkdf::Hkdf;
use sha2::Sha256;
use std::fmt;

/// Errors that can occur during encryption
#[derive(Debug)]
pub enum EncryptionError {
    /// AES-GCM encryption failed
    EncryptionFailed,
}

impl fmt::Display for EncryptionError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            EncryptionError::EncryptionFailed => write!(f, "AES-GCM encryption failed"),
        }
    }
}

impl std::error::Error for EncryptionError {}

/// Errors that can occur during decryption
#[derive(Debug)]
pub enum DecryptionError {
    /// Input is not valid base64
    InvalidBase64,
    /// Decoded payload is too short (need at least 12-byte nonce + 16-byte auth tag)
    PayloadTooShort,
    /// AES-GCM decryption failed (wrong key, corrupted data, or tampered ciphertext)
    DecryptionFailed,
    /// Decrypted bytes are not valid UTF-8
    InvalidUtf8,
}

impl fmt::Display for DecryptionError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            DecryptionError::InvalidBase64 => write!(f, "invalid base64 encoding"),
            DecryptionError::PayloadTooShort => write!(f, "payload too short to contain nonce and auth tag"),
            DecryptionError::DecryptionFailed => write!(f, "AES-GCM decryption failed"),
            DecryptionError::InvalidUtf8 => write!(f, "decrypted bytes are not valid UTF-8"),
        }
    }
}

impl std::error::Error for DecryptionError {}

/// Derives a user-specific 32-byte key from the master secret and user ID (salt).
/// Matches Python: HKDF(SHA256, length=32, salt=uid, info=b'user-data-encryption')
fn derive_key(master_secret: &[u8], uid: &str) -> [u8; 32] {
    let hk = Hkdf::<Sha256>::new(Some(uid.as_bytes()), master_secret);
    let mut key = [0u8; 32];
    hk.expand(b"user-data-encryption", &mut key)
        .expect("32 bytes is a valid length for HKDF");
    key
}

/// Encrypts a string using a user-specific key.
/// Returns base64(12-byte nonce + ciphertext + auth tag).
/// Matches Python: encryption.encrypt(data, uid)
pub fn encrypt(data: &str, uid: &str, master_secret: &[u8]) -> Result<String, EncryptionError> {
    let key = derive_key(master_secret, uid);
    let cipher = Aes256Gcm::new_from_slice(&key).expect("Key is 32 bytes");
    let nonce = Aes256Gcm::generate_nonce(&mut OsRng);

    let ciphertext = cipher.encrypt(&nonce, data.as_bytes())
        .map_err(|_| EncryptionError::EncryptionFailed)?;

    // Format: base64(nonce + ciphertext)
    let mut payload = nonce.to_vec();
    payload.extend_from_slice(&ciphertext);
    Ok(BASE64.encode(&payload))
}

/// Decrypts a base64 encoded string using a user-specific key.
/// Format: base64(12-byte nonce + ciphertext + auth tag)
/// Returns the decrypted string, or an error describing the failure.
pub fn decrypt(encrypted_data: &str, uid: &str, master_secret: &[u8]) -> Result<String, DecryptionError> {
    if encrypted_data.is_empty() {
        return Ok(String::new());
    }

    // Decode base64
    let encrypted_payload = BASE64.decode(encrypted_data)
        .map_err(|_| DecryptionError::InvalidBase64)?;

    // Need at least 12 bytes nonce + 16 bytes auth tag
    if encrypted_payload.len() < 28 {
        return Err(DecryptionError::PayloadTooShort);
    }

    // Extract nonce (first 12 bytes) and ciphertext (rest)
    let (nonce_bytes, ciphertext) = encrypted_payload.split_at(12);

    // Derive key
    let key = derive_key(master_secret, uid);

    // Decrypt
    let cipher = Aes256Gcm::new_from_slice(&key).expect("Key is 32 bytes");
    let nonce = Nonce::from_slice(nonce_bytes);

    let plaintext = cipher.decrypt(nonce, ciphertext)
        .map_err(|_| DecryptionError::DecryptionFailed)?;

    String::from_utf8(plaintext).map_err(|_| DecryptionError::InvalidUtf8)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_decrypt_returns_error_on_invalid_base64() {
        let result = decrypt("not valid base64!!!", "test-uid", b"testsecret12345678901234567890123");
        assert!(matches!(result, Err(DecryptionError::InvalidBase64)));
    }

    #[test]
    fn test_decrypt_returns_ok_on_empty_string() {
        let result = decrypt("", "test-uid", b"testsecret12345678901234567890123");
        assert_eq!(result.unwrap(), "");
    }

    #[test]
    fn test_decrypt_returns_error_on_short_payload() {
        // Valid base64 but too short to be encrypted data
        let result = decrypt("SGVsbG8=", "test-uid", b"testsecret12345678901234567890123");
        assert!(matches!(result, Err(DecryptionError::PayloadTooShort)));
    }

    #[test]
    fn test_encrypt_decrypt_roundtrip() {
        let secret = b"testsecret12345678901234567890123";
        let uid = "test-user-123";
        let plaintext = "Hello, this is a test message!";

        let encrypted = encrypt(plaintext, uid, secret).unwrap();
        let decrypted = decrypt(&encrypted, uid, secret).unwrap();
        assert_eq!(decrypted, plaintext);
    }
}
