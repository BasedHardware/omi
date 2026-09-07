package com.rnruntime;

import java.io.File;
import java.io.RandomAccessFile;
import java.nio.ByteBuffer;
import java.nio.channels.FileLock;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import javax.crypto.SecretKey;

final class OmiRecordingLog implements AutoCloseable {
  static final int MAX_ENTRY_BYTES = 1_052_672;
  static final int MAX_FILE_BYTES = 33_554_432;
  static final int MAX_ENTRIES = 131_080;
  interface DirectorySync { void sync(File directory) throws Exception; }
  private final RandomAccessFile file;
  private final FileLock lock;
  private final SecretKey key;
  private final byte[] binding;
  private long nextSequence;
  private boolean closed;
  private boolean failed;

  OmiRecordingLog(File path, SecretKey key, byte[] binding, DirectorySync directorySync) throws Exception {
    if (binding.length != 32) throw new IllegalArgumentException("Invalid recording binding");
    this.key = key;
    this.binding = binding.clone();
    file = new RandomAccessFile(path, "rw");
    FileLock acquired = null;
    try {
      acquired = file.getChannel().tryLock();
      if (acquired == null) throw new IllegalStateException("Recording journal is busy");
      lock = acquired;
      recover();
      if (nextSequence == 0) appendEntry(new byte[0]);
      directorySync.sync(path.getParentFile());
    } catch (Exception error) {
      if (acquired != null) acquired.release();
      file.close();
      throw error;
    }
  }

  private List<byte[]> recover() throws Exception {
    if (file.length() > MAX_FILE_BYTES) throw new IllegalStateException("Recording journal exceeds its budget");
    file.seek(0);
    long sequence = 0;
    List<byte[]> entries = new ArrayList<>();
    while (file.getFilePointer() < file.length()) {
      long start = file.getFilePointer();
      if (file.length() - start < 4) { trim(start); break; }
      int length = file.readInt();
      if (length < 68 || length > MAX_ENTRY_BYTES + 68) throw new IllegalStateException("Invalid recording journal frame");
      if (file.length() - file.getFilePointer() < length) { trim(start); break; }
      byte[] encrypted = new byte[length];
      file.readFully(encrypted);
      byte[] plain = OmiAuthPolicy.decrypt(key, encrypted);
      if (plain.length < 40 || !MessageDigest.isEqual(binding, Arrays.copyOfRange(plain, 0, 32))
          || ByteBuffer.wrap(plain, 32, 8).getLong() != sequence || sequence >= MAX_ENTRIES)
        throw new IllegalStateException("Recording journal ownership or sequence mismatch");
      byte[] payload = Arrays.copyOfRange(plain, 40, plain.length);
      if (sequence == 0 && payload.length != 0) throw new IllegalStateException("Invalid recording journal header");
      if (sequence > 0) entries.add(payload);
      sequence++;
    }
    nextSequence = sequence;
    return entries;
  }

  private void trim(long length) throws Exception {
    file.setLength(length);
    file.getFD().sync();
  }

  synchronized List<byte[]> readAll() throws Exception {
    usable();
    try { return recover(); }
    catch (Exception error) { failed = true; throw error; }
  }

  synchronized long append(byte[] payload) throws Exception {
    usable();
    if (payload.length == 0 || payload.length > MAX_ENTRY_BYTES) throw new IllegalArgumentException("Invalid recording journal entry");
    return appendEntry(payload);
  }

  private long appendEntry(byte[] payload) throws Exception {
    if (nextSequence >= MAX_ENTRIES) throw new IllegalStateException("Recording journal exceeds its entry budget");
    byte[] plain = ByteBuffer.allocate(40 + payload.length).put(binding).putLong(nextSequence).put(payload).array();
    byte[] encrypted = OmiAuthPolicy.encrypt(key, plain);
    if (file.length() + 4 + encrypted.length > MAX_FILE_BYTES) throw new IllegalStateException("Recording journal exceeds its byte budget");
    try {
      file.seek(file.length());
      file.writeInt(encrypted.length);
      file.write(encrypted);
      file.getFD().sync();
      return nextSequence++;
    } catch (Exception error) { failed = true; throw error; }
  }

  private void usable() {
    if (closed || failed) throw new IllegalStateException("Recording journal is closed");
  }

  @Override public synchronized void close() throws Exception {
    if (!closed) {
      closed = true;
      try { lock.release(); } finally { file.close(); }
    }
  }
}
