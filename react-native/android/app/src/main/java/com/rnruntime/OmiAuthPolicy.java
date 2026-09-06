package com.rnruntime;

import java.net.URI;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.HashMap;
import java.util.Map;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class OmiAuthPolicy {
  public static final String REDIRECT = "omi-rnruntime://auth/callback";
  private OmiAuthPolicy() {}

  public static byte[] encrypt(SecretKey key, byte[] plaintext) throws Exception {
    Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
    cipher.init(Cipher.ENCRYPT_MODE, key);
    byte[] ciphertext = cipher.doFinal(plaintext);
    byte[] iv = cipher.getIV();
    if (iv.length != 12) throw new IllegalStateException("Invalid session nonce");
    byte[] result = Arrays.copyOf(iv, iv.length + ciphertext.length);
    System.arraycopy(ciphertext, 0, result, iv.length, ciphertext.length);
    return result;
  }

  public static byte[] decrypt(SecretKey key, byte[] encrypted) throws Exception {
    if (encrypted.length <= 28) throw new IllegalArgumentException("Invalid encrypted session");
    Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
    cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(128, Arrays.copyOfRange(encrypted, 0, 12)));
    return cipher.doFinal(Arrays.copyOfRange(encrypted, 12, encrypted.length));
  }

  public static String randomToken() {
    byte[] bytes = new byte[32];
    new SecureRandom().nextBytes(bytes);
    StringBuilder value = new StringBuilder(64);
    for (byte item : bytes) value.append(String.format("%02x", item & 255));
    return value.toString();
  }

  public static byte[] challenge(String verifier) throws Exception {
    return MessageDigest.getInstance("SHA-256").digest(verifier.getBytes(StandardCharsets.US_ASCII));
  }

  public static String callbackCode(String value, String state) {
    try {
      URI uri = URI.create(value);
      if (!"omi-rnruntime".equals(uri.getScheme()) || !"auth".equals(uri.getHost()) ||
          !"/callback".equals(uri.getRawPath()) || uri.getUserInfo() != null ||
          uri.getPort() != -1 || uri.getRawFragment() != null || state.isEmpty()) return null;
      Map<String, String> query = new HashMap<>();
      for (String pair : uri.getRawQuery().split("&")) {
        String[] parts = pair.split("=", 2);
        if (parts.length != 2) return null;
        String key = URLDecoder.decode(parts[0], "UTF-8");
        if (query.put(key, URLDecoder.decode(parts[1], "UTF-8")) != null) return null;
      }
      String code = query.get("code");
      return state.equals(query.get("state")) && !query.containsKey("error") && code != null &&
          !code.isEmpty() ? code : null;
    } catch (Exception error) {
      return null;
    }
  }
}
