package com.rnruntime;

import java.io.IOException;
import java.net.HttpURLConnection;
import java.net.URI;
import java.net.URL;

public final class OmiBackendTransport {
  private OmiBackendTransport() {}

  public static HttpURLConnection openConnection(URL url) throws IOException {
    HttpURLConnection connection = (HttpURLConnection) url.openConnection();
    connection.setInstanceFollowRedirects(false);
    return connection;
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
      route.equals("/v1/tasks");
  }
}
