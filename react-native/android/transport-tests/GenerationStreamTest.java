package com.rnruntime;

import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;

public final class GenerationStreamTest {
  public static void main(String[] args) throws Exception {
    HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
    AtomicInteger requests = new AtomicInteger();
    server.createContext("/events", exchange -> {
      int request = requests.incrementAndGet();
      assert "Bearer test-only".equals(exchange.getRequestHeaders().getFirst("Authorization"));
      assert request == 1 ? exchange.getRequestHeaders().getFirst("Last-Event-ID") == null :
          "resume-1".equals(exchange.getRequestHeaders().getFirst("Last-Event-ID"));
      String frame = request == 1 ? "\uFEFF: heartbeat\r\nid: resume-1\r\ndata: snapshot\r\n\r\n" :
          "id: terminal-2\r\ndata: done\r\ndata: 你好\r\n\r\n";
      byte[] bytes = frame.getBytes(StandardCharsets.UTF_8);
      exchange.getResponseHeaders().set("Content-Type", "text/event-stream; charset=utf-8");
      exchange.sendResponseHeaders(200, 0);
      for (byte item : bytes) { exchange.getResponseBody().write(item); exchange.getResponseBody().flush(); }
      exchange.close();
    });
    server.createContext("/denied", exchange -> {
      exchange.getResponseHeaders().set("Retry-After", "8");
      byte[] bytes = "denied".getBytes(StandardCharsets.UTF_8);
      exchange.sendResponseHeaders(401, bytes.length);
      exchange.getResponseBody().write(bytes);
      exchange.close();
    });
    server.createContext("/html", exchange -> {
      exchange.getResponseHeaders().set("Content-Type", "text/html");
      exchange.sendResponseHeaders(200, 0);
      exchange.close();
    });
    server.createContext("/cancel", exchange -> {
      byte[] bytes = "data: snapshot\n\ndata: done\n\n".getBytes(StandardCharsets.UTF_8);
      exchange.getResponseHeaders().set("Content-Type", "text/event-stream");
      exchange.sendResponseHeaders(200, bytes.length);
      exchange.getResponseBody().write(bytes);
      exchange.close();
    });
    server.start();
    try {
      String base = "http://127.0.0.1:" + server.getAddress().getPort();
      OmiGenerationStream stream = new OmiGenerationStream(null);
      OmiGenerationStream.Result result = stream.run(cursor -> {
        HttpURLConnection connection = open(base + "/events");
        connection.setRequestProperty("Authorization", "Bearer test-only");
        if (cursor != null) connection.setRequestProperty("Last-Event-ID", cursor);
        return connection;
      }, data -> data.equals("done\n你好"), status -> { assert status == 200; });
      assert requests.get() == 2;
      assert result.status == 200 && result.body.equals("id: terminal-2\ndata: done\ndata: 你好\n\n");
      assert result.retryAfterSeconds == null;
      AtomicInteger denied = new AtomicInteger();
      result = new OmiGenerationStream(null).run(cursor -> open(base + "/denied"), data -> false,
          status -> { if (status == 401) denied.incrementAndGet(); });
      assert denied.get() == 1 && result.status == 401 && result.body.equals("denied") && result.retryAfterSeconds == 8;
      boolean rejected = false;
      try { new OmiGenerationStream(null).run(cursor -> open(base + "/html"), data -> true, status -> {}); }
      catch (java.io.IOException expected) { rejected = true; }
      assert rejected : "HTML accepted as generation events";
      OmiGenerationStream cancelled = new OmiGenerationStream(null);
      cancelled.cancel();
      rejected = false;
      try { cancelled.run(cursor -> { throw new AssertionError("Cancelled stream opened a connection"); }, data -> true, status -> {}); }
      catch (java.io.IOException expected) { rejected = true; }
      assert rejected;
      OmiGenerationStream reading = new OmiGenerationStream(null);
      rejected = false;
      try {
        reading.run(cursor -> open(base + "/cancel"), data -> {
          if (data.equals("snapshot")) { reading.cancel(); return false; }
          throw new AssertionError("Terminal frame delivered after cancellation");
        }, status -> {});
      } catch (java.io.IOException expected) { rejected = true; }
      assert rejected : "Cancellation during stream reading ignored";
      for (String invalid : new String[] {"", "bad\rheader", "bad\nheader", "bad\0cursor"}) {
        rejected = false;
        try { new OmiGenerationStream(invalid); } catch (IllegalArgumentException expected) { rejected = true; }
        assert rejected;
      }
      System.out.println("Android SSE fragmented UTF-8, CRLF, resume, terminal, HTTP error and cancellation tests passed");
    } finally {
      server.stop(0);
    }
  }

  private static HttpURLConnection open(String value) throws Exception {
    HttpURLConnection connection = OmiBackendTransport.openConnection(new URL(value));
    connection.setConnectTimeout(1000);
    connection.setReadTimeout(1000);
    return connection;
  }
}
