package com.rnruntime;

import com.sun.net.httpserver.HttpServer;
import java.net.HttpURLConnection;
import java.net.InetSocketAddress;
import java.net.URL;
import java.util.concurrent.atomic.AtomicInteger;

public final class BackendTransportTest {
  public static void main(String[] args) throws Exception {
    for (String path : new String[] {
      "/v1/settings", "/v1/chat-messages", "/v1/chat-generations/id/events",
      "/v1/chat-generations/id", "/v1/chat-attachments", "/v1/chat-attachments/id/complete",
      "/v1/device-sessions", "/v1/device-sessions/id/audio", "/v1/conversations",
      "/v1/memories", "/v1/tasks"
    }) {
      assert OmiBackendTransport.isV5BackendPath(path) : path;
      assert OmiBackendTransport.isV5BackendPath(path + "?limit=10") : path;
    }
    for (String path : new String[] {
      "/v1/users/me", "/v1/tasks/one", "/v1/tasks-extra", "/v1/device-sessions-extra"
    }) {
      assert !OmiBackendTransport.isV5BackendPath(path) : path;
    }
    AtomicInteger redirects = new AtomicInteger();
    HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
    server.createContext("/target", exchange -> {
      redirects.incrementAndGet();
      exchange.sendResponseHeaders(200, -1);
      exchange.close();
    });
    server.createContext("/redirect", exchange -> {
      assert "Bearer local-test-only".equals(exchange.getRequestHeaders().getFirst("Authorization"));
      exchange.getResponseHeaders().set("Location", "/target");
      exchange.sendResponseHeaders(302, -1);
      exchange.close();
    });
    server.start();
    try {
      HttpURLConnection connection = OmiBackendTransport.openConnection(
        new URL("http://127.0.0.1:" + server.getAddress().getPort() + "/redirect"));
      try {
        connection.setConnectTimeout(2000);
        connection.setReadTimeout(2000);
        connection.setRequestProperty("Authorization", "Bearer local-test-only");
        assert connection.getResponseCode() == 302;
        assert redirects.get() == 0;
      } finally {
        connection.disconnect();
      }
    } finally {
      server.stop(0);
    }
    System.out.println("Android HTTP redirects and v5 routing passed");
  }
}
