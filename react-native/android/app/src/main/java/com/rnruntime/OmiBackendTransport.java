package com.rnruntime;

import java.io.IOException;
import java.net.HttpURLConnection;
import java.net.URI;
import java.net.URL;

/**
 * Android transport helpers. Capture-path allowlist, request timeouts, and
 * example-platform method+path rules are owned by native-core
 * ({@code omi_backend_policy.*}). When {@code libomi_native} is loaded the JNI
 * entry points are used; host transport-tests fall back to a Java mirror of the
 * same rules.
 */
public final class OmiBackendTransport {
  private static final boolean HAS_NATIVE_POLICY;

  static {
    boolean available = false;
    try {
      System.loadLibrary("omi_native");
      available = nativePolicyAvailable();
    } catch (UnsatisfiedLinkError | RuntimeException ignored) {
      available = false;
    }
    HAS_NATIVE_POLICY = available;
  }

  private OmiBackendTransport() {}

  private static native boolean nativePolicyAvailable();

  private static native boolean nativeIsCapturePath(String path);

  private static native int nativeRequestTimeoutSeconds(String method, String path);

  private static native boolean nativeExamplePlatformSupported(String method, String path);

  public static int readTimeoutMillis(String method, String path) {
    if (HAS_NATIVE_POLICY) {
      return nativeRequestTimeoutSeconds(method, path) * 1000;
    }
    return mirrorRequestTimeoutSeconds(method, path) * 1000;
  }

  public static HttpURLConnection openConnection(URL url) throws IOException {
    HttpURLConnection connection = (HttpURLConnection) url.openConnection();
    connection.setInstanceFollowRedirects(false);
    return connection;
  }

  public static final String SOFTWARE_PLANE_PREFERENCES = "omi-backend";
  public static final String SOFTWARE_PLANE_KEY = "softwarePlane";

  public static String resolvedSoftwarePlane(String stored, boolean stampedValid) {
    if (stored != null && !stored.isEmpty()) {
      return "new".equals(stored) ? "new" : "old";
    }
    return stampedValid ? "new" : "old";
  }

  public static boolean softwarePlaneIsNew(String plane) {
    return "new".equals(plane);
  }

  public static boolean isV5BackendPath(String path) {
    if (HAS_NATIVE_POLICY) {
      return nativeIsCapturePath(path);
    }
    return mirrorIsCapturePath(path);
  }

  public static boolean examplePlatformSupported(String method, String path) {
    if (HAS_NATIVE_POLICY) {
      return nativeExamplePlatformSupported(method, path);
    }
    return mirrorExamplePlatformSupported(method, path);
  }

  /** Java mirror of native-core omi_backend_request_timeout_seconds. */
  static int mirrorRequestTimeoutSeconds(String method, String path) {
    final String route;
    try {
      route = URI.create(path).getPath();
    } catch (IllegalArgumentException error) {
      return 60;
    }
    return "POST".equals(method) && route != null &&
      route.matches("/v1/device-sessions/[^/]+/transcribe") ? 150 : 60;
  }

  /** Java mirror of native-core omi_backend_is_capture_path. */
  static boolean mirrorIsCapturePath(String path) {
    final String route;
    try {
      route = URI.create(path).getPath();
    } catch (IllegalArgumentException error) {
      return false;
    }
    if (route == null) return false;
    return route.equals("/v1/settings") ||
      route.equals("/v1/live/sessions") ||
      route.equals("/v1/chat-messages") ||
      route.startsWith("/v1/chat-generations/") ||
      route.equals("/v1/chat-attachments") ||
      route.startsWith("/v1/chat-attachments/") ||
      route.equals("/v1/device-sessions") ||
      route.startsWith("/v1/device-sessions/") ||
      route.equals("/v1/conversations") ||
      route.equals("/v1/memories") ||
      route.equals("/v1/tasks") || route.equals("/v1/tasks/ops");
  }

  /** Java mirror of native-core omi_backend_example_platform_supported. */
  static boolean mirrorExamplePlatformSupported(String method, String path) {
    final String route;
    try {
      route = URI.create(path).getPath();
    } catch (IllegalArgumentException error) {
      return false;
    }
    return (method.equals("GET") && ("/v1/conversations".equals(route) ||
      "/v1/memories".equals(route) || "/v1/tasks".equals(route))) ||
      (method.equals("POST") && "/v1/tasks/ops".equals(route));
  }
}
