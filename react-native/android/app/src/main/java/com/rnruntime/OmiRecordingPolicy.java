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
    if (!Double.isFinite(number) || number < 0 || number > 8640000000000000d || number != Math.floor(number))
      throw new IllegalArgumentException("Invalid capture timestamp");
    return (long) number;
  }
  static boolean capturedAtMatches(Object expected, Object actual) {
    return java.util.Objects.equals(capturedAt(expected), capturedAt(actual));
  }
  static boolean rememberedIdentity(String id, String name) {
    return id != null && !id.isEmpty() && id.length() <= 128 && name != null && !name.isEmpty() && name.length() <= 256;
  }
  static boolean rememberedCurrent(long ticket, long generation, String expectedLogin, String currentLogin, boolean ready) {
    return ticket == generation && ready && expectedLogin != null && !expectedLogin.isEmpty() && expectedLogin.equals(currentLogin);
  }
  static boolean retryableOwnershipStatus(int status) {
    return status == 408 || status == 429 || (status >= 500 && status <= 599);
  }
  static boolean retryableOwnershipFailure(int status, Boolean nestedRetryable) {
    if (nestedRetryable != null && !nestedRetryable.booleanValue()) return false;
    return retryableOwnershipStatus(status);
  }
  static boolean offline(Throwable error) {
    return error instanceof ConnectException || error instanceof NoRouteToHostException
      || error instanceof SocketTimeoutException || error instanceof UnknownHostException;
  }
  static boolean sameContext(String expectedLogin, String currentLogin, String expectedOrigin, String currentOrigin) {
    return expectedLogin != null && !expectedLogin.isEmpty() && expectedLogin.equals(currentLogin)
      && expectedOrigin != null && !expectedOrigin.isEmpty() && expectedOrigin.equals(currentOrigin);
  }
}
