package com.rnruntime;

final class OmiBleLease {
  static boolean recordingReady(boolean connected, boolean notifying, boolean hasCodec) {
    return connected && notifying && hasCodec;
  }
  private long generation;
  private long operation;
  private boolean active;
  synchronized long begin() { active = true; operation++; return ++generation; }
  synchronized void retire() { active = false; generation++; operation++; }
  synchronized boolean accepts(long token) { return active && generation == token; }
  synchronized boolean acceptsGatt(long token, Object current, Object callback) { return current != null && current == callback && accepts(token); }
  synchronized long operation() { return ++operation; }
  synchronized boolean operationPending(long token, long ticket) { return accepts(token) && operation == ticket; }
  static final class Scan<T> {
    private long generation;
    private boolean active;
    private java.util.function.Consumer<T> pending;
    private java.util.function.Consumer<RuntimeException> rejected;
    void begin(java.util.function.Consumer<T> callback, java.util.function.Consumer<RuntimeException> failure) {
      if (pending != null) throw new IllegalStateException("Previous scan is pending");
      pending = callback;
      rejected = failure;
    }
    long started() { active = true; return ++generation; }
    boolean active() { return active; }
    boolean accepts(long token) { return active && generation == token; }
    boolean stop(Runnable stopHardware, java.util.function.Supplier<T> result) {
      boolean wasActive = active;
      active = false;
      generation++;
      java.util.function.Consumer<T> callback = pending;
      java.util.function.Consumer<RuntimeException> failure = rejected;
      pending = null;
      rejected = null;
      try { if (wasActive) stopHardware.run(); }
      catch (RuntimeException error) { if (failure != null) failure.accept(error); return false; }
      if (callback != null) callback.accept(result.get());
      return true;
    }
    void fail(RuntimeException error) {
      active = false;
      generation++;
      java.util.function.Consumer<RuntimeException> failure = rejected;
      pending = null;
      rejected = null;
      if (failure != null) failure.accept(error);
    }
  }
  static final class FirstAudio {
    static final int WINDOW_MS = 4000;
    private long generation;
    private boolean started;
    private boolean waiting;
    private boolean retried;
    private boolean observed;
    boolean begin() { if (started) return false; started = true; waiting = !observed; generation++; return waiting; }
    boolean observed() { return observed; }
    long token() { return generation; }
    boolean receive(int length) { if (length <= 0 || observed) return false; observed = true; waiting = false; generation++; return true; }
    int timeout(long token) {
      if (!waiting || token != generation) return 0;
      generation++;
      if (!retried) { retried = true; return 1; }
      waiting = false; return -1;
    }
    void cancel() { generation++; started = false; waiting = false; retried = false; observed = false; }
  }
  static final class Reconnect {
    private long generation;
    private boolean armed;
    private int attempts;
    void ready() { armed = true; attempts = 0; generation++; }
    void cancel() { armed = false; attempts = 0; generation++; }
    long nextDelayMillis() {
      if (!armed || attempts == 3) { cancel(); return -1; }
      generation++;
      return 1000L << attempts++;
    }
    long token() { return generation; }
    boolean accepts(long token) { return armed && generation == token; }
    int attempts() { return attempts; }
  }
}
