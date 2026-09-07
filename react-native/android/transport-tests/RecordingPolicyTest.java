package com.rnruntime;

public final class RecordingPolicyTest {
  public static void main(String[] args) {
    assert OmiRecordingPolicy.rememberedIdentity("device", "Omi");
    assert !OmiRecordingPolicy.rememberedIdentity(null, "Omi");
    assert !OmiRecordingPolicy.rememberedIdentity("device", "");
    assert !OmiRecordingPolicy.rememberedIdentity("x".repeat(129), "Omi");
    assert !OmiRecordingPolicy.rememberedIdentity("device", "x".repeat(257));
    assert OmiRecordingPolicy.rememberedCurrent(1, 1, "login", "login", true);
    assert !OmiRecordingPolicy.rememberedCurrent(1, 2, "login", "login", true);
    assert !OmiRecordingPolicy.rememberedCurrent(1, 1, "login", "other", true);
    assert !OmiRecordingPolicy.rememberedCurrent(1, 1, "login", null, true);
    assert !OmiRecordingPolicy.rememberedCurrent(1, 1, "login", "login", false);
    assert OmiRecordingPolicy.offline(new java.net.SocketTimeoutException());
    assert OmiRecordingPolicy.offline(new java.net.ConnectException());
    assert OmiRecordingPolicy.offline(new java.net.UnknownHostException());
    assert !OmiRecordingPolicy.offline(new javax.net.ssl.SSLHandshakeException("certificate"));
    assert !OmiRecordingPolicy.offline(new java.net.ProtocolException());
    assert !OmiRecordingPolicy.offline(new java.io.InterruptedIOException());
    assert !OmiRecordingPolicy.offline(new java.io.IOException());
    assert !OmiRecordingPolicy.offline(new java.net.SocketException("Socket closed"));
    assert OmiRecordingPolicy.sameContext("login-a", "login-a", "origin-a", "origin-a");
    assert !OmiRecordingPolicy.sameContext("login-a", "login-b", "origin-a", "origin-a");
    assert !OmiRecordingPolicy.sameContext("login-a", "login-a", "origin-a", "origin-b");
    assert !OmiRecordingPolicy.sameContext("login-a", null, "origin-a", "origin-a");
    System.out.println("Android recording offline fallback policy tests passed");
  }
}
