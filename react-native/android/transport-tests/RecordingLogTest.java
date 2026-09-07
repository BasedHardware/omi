package com.rnruntime;

import java.io.File;
import java.io.RandomAccessFile;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.StandardOpenOption;
import java.util.Arrays;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

public final class RecordingLogTest {
  private static final OmiRecordingLog.DirectorySync SYNC = directory -> {
    try (FileChannel channel = FileChannel.open(directory.toPath(), StandardOpenOption.READ)) { channel.force(true); }
  };
  private interface Operation { void run() throws Exception; }
  private static void rejects(Operation operation) throws Exception {
    try { operation.run(); } catch (Exception expected) { return; }
    throw new AssertionError("Expected journal rejection");
  }
  public static void main(String[] args) throws Exception {
    if (args.length == 1) {
      RandomAccessFile torn = new RandomAccessFile(args[0], "rw");
      torn.seek(torn.length()); torn.writeInt(100); torn.write(new byte[]{1, 2, 3});
      Runtime.getRuntime().halt(73);
    }
    File directory = Files.createTempDirectory("omi-recording-log-").toFile();
    File path = new File(directory, "capture");
    SecretKey key = KeyGenerator.getInstance("AES").generateKey();
    byte[] owner = new byte[32]; Arrays.fill(owner, (byte) 17);
    byte[] secret = "Synthetic speech packet; never real user data".getBytes(java.nio.charset.StandardCharsets.UTF_8);
    try {
      try (OmiRecordingLog log = new OmiRecordingLog(path, key, owner, SYNC)) {
        assert log.append(secret) == 1;
        assert log.append(new byte[]{1, 2, 3}) == 2;
        rejects(() -> { try (OmiRecordingLog duplicate = new OmiRecordingLog(path, key, owner, SYNC)) { throw new AssertionError(); } });
        rejects(() -> log.append(new byte[OmiRecordingLog.MAX_ENTRY_BYTES + 1]));
      }
      OmiRecordingLog retired = new OmiRecordingLog(path, key, owner, SYNC);
      retired.close();
      retired.close();
      rejects(() -> retired.append(new byte[]{9}));
      try (OmiRecordingLog replacement = new OmiRecordingLog(path, key, owner, SYNC)) {
        assert replacement.readAll().size() == 2;
        rejects(() -> retired.append(new byte[]{9}));
        assert replacement.readAll().size() == 2;
      }
      byte[] original = Files.readAllBytes(path.toPath());
      assert !new String(original, java.nio.charset.StandardCharsets.ISO_8859_1).contains("Synthetic speech");
      Process crashed = new ProcessBuilder(new File(System.getProperty("java.home"), "bin/java").getPath(),
        "-cp", System.getProperty("java.class.path"), RecordingLogTest.class.getName(), path.getPath()).start();
      assert crashed.waitFor() == 73;
      try (OmiRecordingLog recovered = new OmiRecordingLog(path, key, owner, SYNC)) {
        assert Arrays.equals(recovered.readAll().get(0), secret);
        assert recovered.readAll().size() == 2;
        assert path.length() == original.length;
        assert recovered.append(new byte[]{4}) == 3;
      }
      byte[] wrongOwner = owner.clone(); wrongOwner[0]++;
      rejects(() -> { try (OmiRecordingLog ignored = new OmiRecordingLog(path, key, wrongOwner, SYNC)) { throw new AssertionError(); } });
      SecretKey wrongKey = KeyGenerator.getInstance("AES").generateKey();
      rejects(() -> { try (OmiRecordingLog ignored = new OmiRecordingLog(path, wrongKey, owner, SYNC)) { throw new AssertionError(); } });
      byte[] tampered = Files.readAllBytes(path.toPath()); tampered[40] ^= 1;
      Files.write(path.toPath(), tampered);
      rejects(() -> { try (OmiRecordingLog ignored = new OmiRecordingLog(path, key, owner, SYNC)) { throw new AssertionError(); } });
      assert Arrays.equals(Files.readAllBytes(path.toPath()), tampered);
      System.out.println("Encrypted recording log restart, torn tail, ownership, tamper and budget checks passed");
    } finally { Files.deleteIfExists(path.toPath()); Files.delete(directory.toPath()); }
  }
}
