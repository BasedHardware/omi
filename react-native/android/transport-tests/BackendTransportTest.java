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
    assert OmiBackendTransport.readTimeoutMillis("GET", "/v1/device-sessions/id/transcribe") == 60_000;
    assert OmiBackendTransport.readTimeoutMillis("POST", "/v1/device-sessions/id/complete") == 60_000;
    assert OmiBackendTransport.readTimeoutMillis("POST", "/v1/device-sessions//transcribe") == 60_000;
    for (String path : new String[] {
      "/v1/settings", "/v1/live/sessions", "/v1/chat-messages", "/v1/chat-generations/id/events",
      "/v1/chat-generations/id", "/v1/chat-attachments", "/v1/chat-attachments/id/complete",
      "/v1/device-sessions", "/v1/device-sessions/id/audio", "/v1/conversations",
      "/v1/memories", "/v1/tasks", "/v1/tasks/ops"
    }) {
      assert OmiBackendTransport.isV5BackendPath(path) : path;
      assert OmiBackendTransport.isV5BackendPath(path + "?limit=10") : path;
    }
    for (String path : new String[] {
      "/v1/users/me", "/v1/tasks/one", "/v1/tasks-extra", "/v1/device-sessions-extra",
      "/v1/live/sessions-extra"
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
    assert OmiBackendTransport.examplePlatformSupported("GET", "/v1/tasks?limit=2");
    assert OmiBackendTransport.examplePlatformSupported("POST", "/v1/tasks/ops");
    assert !OmiBackendTransport.examplePlatformSupported("DELETE", "/v1/tasks/ops");
    assert !OmiBackendTransport.examplePlatformSupported("POST", "/v1/tasks");
    OmiBackendTransport.RequestPlan transcribe = OmiBackendTransport.planRequest(
      "POST", "/v1/device-sessions/id/transcribe");
    assert transcribe.valid;
    assert transcribe.timeoutMillis == 150_000;
    assert transcribe.capturePath;
    OmiBackendTransport.RequestPlan users = OmiBackendTransport.planRequest("GET", "/v1/users/me");
    assert users.valid;
    assert users.timeoutMillis == 60_000;
    assert !users.capturePath;
    assert !OmiBackendTransport.httpRequestValid("GET", "//evil");
    assert !OmiBackendTransport.planRequest("PUT", "/v1/tasks").valid;
    String session = "11111111-2222-4333-8444-555555555555";
    assert OmiBackendTransport.recordingPathOwned("POST", "/v1/device-sessions", null);
    assert OmiBackendTransport.recordingPathOwned("POST", "/v1/device-sessions/" + session + "/audio", session);
    assert !OmiBackendTransport.recordingPathOwned("POST", "/v1/device-sessions/other/audio", session);
    String partition = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
    assert (partition + "/" + session + ".journal").equals(
      OmiBackendTransport.recordingJournalRelpath(partition, session));
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
