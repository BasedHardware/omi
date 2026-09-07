package com.rnruntime;

import java.net.ConnectException;
import java.net.NoRouteToHostException;
import java.net.SocketTimeoutException;
import java.net.UnknownHostException;

final class OmiRecordingPolicy {
  static boolean offline(Throwable error) {
    return error instanceof ConnectException || error instanceof NoRouteToHostException
      || error instanceof SocketTimeoutException || error instanceof UnknownHostException;
  }
  static boolean sameContext(String expectedLogin, String currentLogin, String expectedOrigin, String currentOrigin) {
    return expectedLogin != null && !expectedLogin.isEmpty() && expectedLogin.equals(currentLogin)
      && expectedOrigin != null && !expectedOrigin.isEmpty() && expectedOrigin.equals(currentOrigin);
  }
}
