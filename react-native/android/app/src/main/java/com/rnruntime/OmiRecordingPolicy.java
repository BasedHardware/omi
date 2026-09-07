package com.rnruntime;

import java.net.ConnectException;
import java.net.NoRouteToHostException;
import java.net.SocketTimeoutException;
import java.net.UnknownHostException;

final class OmiRecordingPolicy {
  static boolean rememberedIdentity(String id, String name) {
    return id != null && !id.isEmpty() && id.length() <= 128 && name != null && !name.isEmpty() && name.length() <= 256;
  }
  static boolean rememberedCurrent(long ticket, long generation, String expectedLogin, String currentLogin, boolean ready) {
    return ticket == generation && ready && expectedLogin != null && !expectedLogin.isEmpty() && expectedLogin.equals(currentLogin);
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
