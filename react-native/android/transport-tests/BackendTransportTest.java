package com.rnruntime;

import com.sun.net.httpserver.HttpServer;
import java.net.HttpURLConnection;
import java.net.InetSocketAddress;
import java.net.URL;
import java.util.concurrent.atomic.AtomicInteger;

public final class BackendTransportTest {
  public static void main(String[] args) throws Exception {
    assert OmiBackendTransport.readTimeoutMillis("POST", "/v1/device-sessions/id/transcribe") == 150_000;
    assert OmiBackendTransport.readTimeoutMillis("POST", "/v1/device-sessions/id/transcribe?retry=1") == 150_000;
    assert OmiBackendTransport.readTimeoutMillis("GET", "/v1/device-sessions/id/transcribe") == 30_000;
    assert OmiBackendTransport.readTimeoutMillis("POST", "/v1/device-sessions/id/complete") == 30_000;
    assert OmiBackendTransport.readTimeoutMillis("POST", "/v1/device-sessions//transcribe") == 30_000;
    for (String path : new String[] {
      "/v1/settings", "/v1/chat-messages", "/v1/chat-generations/id/events",
      "/v1/chat-generations/id", "/v1/chat-attachments", "/v1/chat-attachments/id/complete",
      "/v1/device-sessions", "/v1/device-sessions/id/audio", "/v1/conversations",
      "/v1/memories", "/v1/tasks", "/v1/tasks/ops"
    }) {
      assert OmiBackendTransport.isV5BackendPath(path) : path;
      assert OmiBackendTransport.isV5BackendPath(path + "?limit=10") : path;
    }
    for (String path : new String[] {
      "/v1/users/me", "/v1/tasks/one", "/v1/tasks-extra", "/v1/device-sessions-extra"
    }) {
      assert !OmiBackendTransport.isV5BackendPath(path) : path;
    }
    assert OmiBackendTransport.isV5BackendPath("/v1/tasks/ops?op=complete");
    assert "new".equals(OmiBackendTransport.resolvedSoftwarePlane(null, true));
    assert "old".equals(OmiBackendTransport.resolvedSoftwarePlane(null, false));
    assert "new".equals(OmiBackendTransport.resolvedSoftwarePlane("", true));
    assert "new".equals(OmiBackendTransport.resolvedSoftwarePlane("new", false));
    assert "old".equals(OmiBackendTransport.resolvedSoftwarePlane("old", true));
    assert "old".equals(OmiBackendTransport.resolvedSoftwarePlane("unexpected", true));
    assert OmiBackendTransport.softwarePlaneIsNew("new");
    assert !OmiBackendTransport.softwarePlaneIsNew("old");
    assert OmiBackendTransport.examplePlatformSupported("GET", "/v1/settings");
    assert OmiBackendTransport.examplePlatformSupported("GET", "/v1/conversations?limit=50&offset=0");
    assert OmiBackendTransport.examplePlatformSupported("GET", "/v1/memories?limit=50&cursor=next");
    assert OmiBackendTransport.examplePlatformSupported("GET", "/v1/tasks?limit=2");
    assert OmiBackendTransport.examplePlatformSupported("POST", "/v1/tasks/ops");
    assert OmiBackendTransport.examplePlatformSupported("GET", "/v1/chat-messages?limit=50");
    assert OmiBackendTransport.examplePlatformSupported("GET", "/v1/chat-messages?limit=50&olderCursor=older-1");
    assert OmiBackendTransport.examplePlatformSupported(
      "GET", "/v1/device-sessions/ad99598c-36a8-4e12-a428-63d0a3e06170/transcript");
    assert !OmiBackendTransport.examplePlatformSupported("DELETE", "/v1/tasks/ops");
    assert !OmiBackendTransport.examplePlatformSupported("POST", "/v1/tasks");
    assert !OmiBackendTransport.examplePlatformSupported("POST", "/v1/chat-messages");
    assert !OmiBackendTransport.examplePlatformSupported("POST", "/v1/settings");
    assert !OmiBackendTransport.examplePlatformSupported("POST", "/v1/chat-attachments");
    assert !OmiBackendTransport.examplePlatformSupported("GET", "/v1/chat-generations/one/events");
    assert !OmiBackendTransport.examplePlatformSupported("DELETE", "/v1/chat-generations/one");
    assert !OmiBackendTransport.examplePlatformSupported("POST", "/v1/conversations");
    assert !OmiBackendTransport.examplePlatformSupported("GET", "/v1/conversations/one");
    assert !OmiBackendTransport.examplePlatformSupported("GET", "/v1/device-sessions/ownership");
    assert !OmiBackendTransport.examplePlatformSupported(
      "GET", "/v1/device-sessions/ad99598c-36a8-4e12-a428-63d0a3e06170");
    assert !OmiBackendTransport.examplePlatformSupported(
      "GET", "/v1/device-sessions/ad99598c-36a8-1e12-a428-63d0a3e06170/transcript");
    assert !OmiBackendTransport.examplePlatformSupported(
      "POST", "/v1/device-sessions/ad99598c-36a8-4e12-a428-63d0a3e06170/transcribe");
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
