package com.rnruntime;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.function.Predicate;

public final class OmiGenerationStream {
  public interface Opener {
    HttpURLConnection open(String lastEventId) throws Exception;
  }

  public interface Sender { void send(HttpURLConnection connection) throws Exception; }

  public interface ResponseObserver {
    void received(int status) throws Exception;
  }

  public interface FrameListener {
    void onFrame(String frame);
  }

  public static final class Result {
    public final int status;
    public final String body;
    public final Integer retryAfterSeconds;
    Result(int status, String body, Integer retryAfterSeconds) {
      this.status = status;
      this.body = body;
      this.retryAfterSeconds = retryAfterSeconds;
    }
  }

  private final CountDownLatch cancelled = new CountDownLatch(1);
  private volatile HttpURLConnection connection;
  private String lastEventId;
  private long deadline;
  private final boolean omi;
  private int receivedBytes;
  private FrameListener frames;

  public OmiGenerationStream(String lastEventId) { this(lastEventId, false); }

  public OmiGenerationStream(String lastEventId, boolean omi) {
    this.omi = omi;
    if (lastEventId != null && (lastEventId.isEmpty() || lastEventId.length() > 1024 ||
        lastEventId.indexOf('\r') >= 0 || lastEventId.indexOf('\n') >= 0 || lastEventId.indexOf('\0') >= 0)) {
      throw new IllegalArgumentException("Invalid event cursor");
    }
    this.lastEventId = lastEventId;
  }

  public void setFrameListener(FrameListener listener) {
    this.frames = listener;
  }

  public void cancel() {
    cancelled.countDown();
    HttpURLConnection active = connection;
    if (active != null) active.disconnect();
  }

  public Result run(Opener opener, Predicate<String> terminal, ResponseObserver observer) throws Exception {
    return run(opener, terminal, observer, connection -> {});
  }

  public Result run(Opener opener, Predicate<String> terminal, ResponseObserver observer, Sender sender) throws Exception {
    java.util.Timer timer = omi ? new java.util.Timer(true) : null;
    if (timer != null) timer.schedule(new java.util.TimerTask() { public void run() { cancel(); } }, 150_000);
    try { return runInternal(opener, terminal, observer, sender); }
    finally { if (timer != null) timer.cancel(); }
  }

  private Result runInternal(Opener opener, Predicate<String> terminal, ResponseObserver observer, Sender sender) throws Exception {
    deadline = System.nanoTime() + (omi ? TimeUnit.SECONDS.toNanos(150) : TimeUnit.HOURS.toNanos(1));
    int attempts = omi ? 1 : 6;
    for (int attempt = 0; attempt < attempts; attempt++) {
      if (System.nanoTime() > deadline) throw new IOException("Generation exceeded time limit");
      if (cancelled.getCount() == 0) throw new IOException("Generation cancelled");
      HttpURLConnection active = opener.open(lastEventId);
      connection = active;
      try {
        if (cancelled.getCount() == 0) throw new IOException("Generation cancelled");
        sender.send(active);
        if (cancelled.getCount() == 0) throw new IOException("Generation cancelled");
        int status = active.getResponseCode();
        observer.received(status);
        if (cancelled.getCount() == 0) throw new IOException("Generation cancelled");
        Integer retry = retryAfter(active.getHeaderField("Retry-After"));
        if (status != 200) {
          InputStream input = status >= 400 ? active.getErrorStream() : active.getInputStream();
          return new Result(status, input == null ? "" : body(input), retry);
        }
        String type = active.getHeaderField("Content-Type");
        if (type == null || !type.toLowerCase(java.util.Locale.US).startsWith("text/event-stream")) {
          throw new ProtocolException("Generation response is not an event stream");
        }
        String frame = terminalFrame(bounded(active.getInputStream()), terminal);
        if (frame != null) return new Result(status, frame, retry);
      } catch (ProtocolException error) {
        throw error;
      } catch (IOException error) {
        if (cancelled.getCount() == 0 || attempt == attempts - 1) throw error;
      } finally {
        active.disconnect();
        connection = null;
      }
      if (attempt == attempts - 1) break;
      if (cancelled.await(250L << attempt, TimeUnit.MILLISECONDS)) throw new IOException("Generation cancelled");
    }
    throw new IOException("Generation ended without a terminal frame");
  }

  private InputStream bounded(InputStream input) {
    return new java.io.FilterInputStream(input) {
      public int read() throws IOException { int value = super.read(); if (value >= 0) count(1); return value; }
      public int read(byte[] buffer, int offset, int length) throws IOException { int n = in.read(buffer, offset, length); if (n > 0) count(n); return n; }
      private void count(int n) throws IOException { if (omi && (receivedBytes += n) > 3_145_728) throw new ProtocolException("Omi response exceeds limit"); }
    };
  }

  private String terminalFrame(InputStream input, Predicate<String> terminal) throws IOException {
    BufferedReader reader = new BufferedReader(new InputStreamReader(input, StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(java.nio.charset.CodingErrorAction.REPORT)
        .onUnmappableCharacter(java.nio.charset.CodingErrorAction.REPORT)));
    StringBuilder frame = new StringBuilder();
    StringBuilder data = new StringBuilder();
    String eventId = null;
    boolean first = true;
    String line;
    while ((line = line(reader)) != null) {
      if (first && line.startsWith("\uFEFF")) line = line.substring(1);
      first = false;
      if (cancelled.getCount() == 0) throw new IOException("Generation cancelled");
      if (line.isEmpty()) {
        if (eventId != null) lastEventId = eventId.isEmpty() ? null : eventId;
        if (frame.length() > 0 && frames != null) frames.onFrame(frame + "\n");
        if (data.length() > 0) {
          String payload = data.substring(0, data.length() - 1);
          if (omi) {
            try { payload = StandardCharsets.UTF_8.newDecoder().decode(java.nio.ByteBuffer.wrap(java.util.Base64.getDecoder().decode(payload))).toString(); }
            catch (Exception error) { throw new ProtocolException("Invalid Omi terminal frame"); }
          }
          if (terminal.test(payload)) return frame + "\n";
          if (omi) throw new ProtocolException("Invalid Omi terminal message");
        }
        frame.setLength(0);
        data.setLength(0);
        eventId = null;
        continue;
      }
      frame.append(line).append('\n');
      if (frame.length() > (omi ? 3_145_728 : 1_048_576)) throw new ProtocolException("Generation frame exceeds limit");
      int colon = line.indexOf(':');
      String name = colon < 0 ? line : line.substring(0, colon);
      String value = colon < 0 ? "" : line.substring(colon + 1);
      if (value.startsWith(" ")) value = value.substring(1);
      if (name.equals(omi ? "done" : "data")) data.append(value).append('\n');
      if (name.equals("id") && value.indexOf('\0') < 0) {
        if (value.length() > 1024) throw new ProtocolException("Generation cursor exceeds limit");
        eventId = value;
      }
    }
    return null;
  }

  private String line(BufferedReader reader) throws IOException {
    StringBuilder value = new StringBuilder();
    int item;
    while ((item = reader.read()) != -1) {
      if (cancelled.getCount() == 0 || System.nanoTime() > deadline) throw new IOException("Generation cancelled or timed out");
      if (item == '\n') return value.toString();
      if (item == '\r') {
        reader.mark(1);
        if (reader.read() != '\n') reader.reset();
        return value.toString();
      }
      value.append((char) item);
      if (value.length() > (omi ? 3_145_728 : 1_048_576)) throw new ProtocolException("Generation line exceeds limit");
    }
    return value.length() == 0 ? null : value.toString();
  }

  private String body(InputStream input) throws IOException {
    try (InputStream stream = bounded(input)) {
      java.io.ByteArrayOutputStream bytes = new java.io.ByteArrayOutputStream();
      byte[] buffer = new byte[4096];
      int count;
      while ((count = stream.read(buffer)) != -1) {
        if (bytes.size() + count > (omi ? 3_145_728 : 1_048_576)) throw new ProtocolException("Generation response exceeds limit");
        bytes.write(buffer, 0, count);
      }
      return bytes.toString("UTF-8");
    }
  }

  private static Integer retryAfter(String value) {
    try {
      int seconds = Integer.parseInt(value);
      return seconds > 0 && seconds <= 3600 ? seconds : null;
    } catch (RuntimeException error) {
      return null;
    }
  }

  private static final class ProtocolException extends IOException {
    ProtocolException(String message) { super(message); }
  }
}
