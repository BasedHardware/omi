package com.rnruntime;

import java.io.IOException;
import java.net.HttpURLConnection;
import java.net.URI;
import java.net.URL;

public final class OmiBackendTransport {
  private OmiBackendTransport() {}

  public static int readTimeoutMillis(String method, String path) {
    String route = URI.create(path).getPath();
    return "POST".equals(method) && route != null &&
      route.matches("/v1/device-sessions/[^/]+/transcribe") ? 150_000 : 30_000;
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
    final String route;
    try {
      route = URI.create(path).getPath();
    } catch (IllegalArgumentException error) {
      return false;
    }
    if (route == null) return false;
    return route.equals("/v1/settings") ||
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
  public static boolean examplePlatformSupported(String method, String path) {
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
