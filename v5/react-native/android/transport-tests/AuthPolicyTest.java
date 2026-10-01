package com.rnruntime;

import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Base64;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

public final class AuthPolicyTest {
  public static void main(String[] args) throws Exception {
    String state = OmiAuthPolicy.randomToken();
    assert state.matches("[a-f0-9]{64}");
    assert !state.equals(OmiAuthPolicy.randomToken());
    assert Base64.getUrlEncoder().withoutPadding().encodeToString(OmiAuthPolicy.challenge(
        "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"))
        .equals("E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM");
    String callback = OmiAuthPolicy.REDIRECT + "?code=valid%2Bcode&state=" + state;
    assert "valid+code".equals(OmiAuthPolicy.callbackCode(callback, state));
    for (String invalid : new String[] {
        callback.replace("omi-rnruntime", "omi"), callback.replace("auth/", "evil/"),
        callback.replace("/callback", "/%63allback"), callback.replace("auth/", "auth:443/"),
        callback.replace("auth/", "user@auth/"), callback + "#fragment", callback + "&code=other",
        callback + "&state=" + state, callback + "&error=denied", callback.replace(state, "wrong"),
        callback.replace("valid%2Bcode", ""), callback.replace("state=", "missing="),
        OmiAuthPolicy.REDIRECT, "not a URI"
    }) assert OmiAuthPolicy.callbackCode(invalid, state) == null : invalid;
    KeyGenerator generator = KeyGenerator.getInstance("AES");
    generator.init(256);
    SecretKey key = generator.generateKey();
    byte[] plaintext = "native-session-secret".getBytes(StandardCharsets.UTF_8);
    byte[] encrypted = OmiAuthPolicy.encrypt(key, plaintext);
    assert Arrays.equals(plaintext, OmiAuthPolicy.decrypt(key, encrypted));
    assert !Arrays.equals(encrypted, OmiAuthPolicy.encrypt(key, plaintext));
    encrypted[encrypted.length - 1] ^= 1;
    boolean rejected = false;
    try { OmiAuthPolicy.decrypt(key, encrypted); } catch (Exception expected) { rejected = true; }
    assert rejected : "Tampered session accepted";
    rejected = false;
    try { OmiAuthPolicy.decrypt(generator.generateKey(), OmiAuthPolicy.encrypt(key, plaintext)); }
    catch (Exception expected) { rejected = true; }
    assert rejected : "Different key accepted";
    System.out.println("Android auth callback, PKCE and encrypted-session tests passed");
  }
}
