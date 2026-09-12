package com.rnruntime;

import java.net.ConnectException;
import java.net.NoRouteToHostException;
import java.net.SocketTimeoutException;
import java.net.UnknownHostException;

final class OmiRecordingPolicy {
  static Long capturedAt(Object value) {
    if (value == null) return null;
    if (!(value instanceof Number)) throw new IllegalArgumentException("Invalid capture timestamp");
    double number = ((Number) value).doubleValue();
    if (!OmiBackendTransport.recordingCapturedAtValid(number))
      throw new IllegalArgumentException("Invalid capture timestamp");
    return (long) number;
  }
  static boolean capturedAtMatches(Object expected, Object actual) {
    Long left = capturedAt(expected), right = capturedAt(actual);
    return OmiBackendTransport.recordingCapturedAtEqual(
      left != null, left == null ? 0d : left.doubleValue(),
      right != null, right == null ? 0d : right.doubleValue());
  }
  static boolean rememberedIdentity(String id, String name) {
    return OmiBackendTransport.recordingRememberedIdentity(id, name);
  }
  static boolean rememberedCurrent(long ticket, long generation, String expectedLogin, String currentLogin, boolean ready) {
    return OmiBackendTransport.recordingRememberedCurrent(ticket, generation, expectedLogin, currentLogin, ready);
  }
  static boolean retryableOwnershipStatus(int status) {
    return OmiBackendTransport.recordingRetryableStatus(status);
  }
  static boolean offline(Throwable error) {
    return error instanceof ConnectException || error instanceof NoRouteToHostException
      || error instanceof SocketTimeoutException || error instanceof UnknownHostException;
  }
  static boolean sameContext(String expectedLogin, String currentLogin, String expectedOrigin, String currentOrigin) {
    return OmiBackendTransport.recordingSameContext(expectedLogin, currentLogin, expectedOrigin, currentOrigin);
  }
  static boolean deviceValid(String deviceId, String deviceName, double codec) {
    return OmiBackendTransport.recordingDeviceValid(deviceId, deviceName, codec);
  }
  static boolean budgetOk(long totalBytes, long extraBytes, boolean creating, int fileCount) {
    return OmiBackendTransport.recordingBudgetOk(totalBytes, extraBytes, creating, fileCount);
  }
}
