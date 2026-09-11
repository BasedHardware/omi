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

  private static native boolean nativeHttpRequestValid(String method, String path);

  private static native boolean nativeRecordingPathOwned(String method, String path, String sessionId);

  private static native String nativeRecordingJournalRelpath(String partitionHex, String captureId);

  public static final class RequestPlan {
    public final boolean valid;
    public final int timeoutMillis;
    public final boolean capturePath;

    RequestPlan(boolean valid, int timeoutMillis, boolean capturePath) {
      this.valid = valid;
      this.timeoutMillis = timeoutMillis;
      this.capturePath = capturePath;
    }
  }

  public static RequestPlan planRequest(String method, String path) {
    if (HAS_NATIVE_POLICY) {
      boolean valid = nativeHttpRequestValid(method, path);
      return new RequestPlan(
        valid,
        valid ? nativeRequestTimeoutSeconds(method, path) * 1000 : 0,
        valid && nativeIsCapturePath(path));
    }
    boolean valid = mirrorHttpRequestValid(method, path);
    return new RequestPlan(
      valid,
      valid ? mirrorRequestTimeoutSeconds(method, path) * 1000 : 0,
      valid && mirrorIsCapturePath(path));
  }

  public static int readTimeoutMillis(String method, String path) {
    return planRequest(method, path).timeoutMillis;
  }

  public static boolean httpRequestValid(String method, String path) {
    return planRequest(method, path).valid;
  }

  public static boolean recordingPathOwned(String method, String path, String sessionId) {
    if (HAS_NATIVE_POLICY) {
      return nativeRecordingPathOwned(method, path, sessionId);
    }
    return mirrorRecordingPathOwned(method, path, sessionId);
  }

  public static String recordingJournalRelpath(String partitionHex, String captureId) {
    if (HAS_NATIVE_POLICY) {
      return nativeRecordingJournalRelpath(partitionHex, captureId);
    }
    return mirrorRecordingJournalRelpath(partitionHex, captureId);
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

  static boolean mirrorHttpRequestValid(String method, String path) {
    if (method == null || path == null) return false;
    if (!method.equals("GET") && !method.equals("POST") && !method.equals("PATCH") && !method.equals("DELETE")) {
      return false;
    }
    return path.startsWith("/") && !path.startsWith("//") && !path.contains("://");
  }

  static boolean mirrorRecordingPathOwned(String method, String path, String sessionId) {
    if ("POST".equals(method) && "/v1/device-sessions".equals(path)) return true;
    if (sessionId == null || !sessionId.matches("[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")) {
      return false;
    }
    String base = "/v1/device-sessions/" + sessionId;
    return ("POST".equals(method) && (path.equals(base + "/audio") || path.equals(base + "/complete") || path.equals(base + "/transcribe")))
      || ("GET".equals(method) && (path.equals(base) || path.equals(base + "/transcript")));
  }

  static String mirrorRecordingJournalRelpath(String partitionHex, String captureId) {
    if (partitionHex == null || captureId == null) return null;
    if (!partitionHex.matches("[0-9a-f]{64}")) return null;
    if (!captureId.matches("[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")) return null;
    return partitionHex + "/" + captureId + ".journal";
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
