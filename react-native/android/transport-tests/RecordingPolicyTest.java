package com.rnruntime;

public final class RecordingPolicyTest {
  public static void main(String[] args) {
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
