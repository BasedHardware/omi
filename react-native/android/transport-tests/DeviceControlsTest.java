package com.rnruntime;

public final class DeviceControlsTest {
  public static void main(String[] args) {
    OmiDeviceControls.FindPattern pattern = new OmiDeviceControls.FindPattern();
    long ticket = pattern.begin();
    assert OmiDeviceControls.FindPattern.LEVEL == 3 && OmiDeviceControls.FindPattern.DELAY_MS == 750;
    for (int index = 0; index < 3; index++) {
      assert pattern.send(ticket);
      assert !pattern.send(ticket);
      assert !pattern.complete();
      assert pattern.acknowledge(ticket);
      assert !pattern.acknowledge(ticket);
      assert pattern.complete() == (index == 2);
    }
    assert !pattern.send(ticket);
    ticket = pattern.begin();
    assert pattern.send(ticket);
    assert pattern.acknowledge(ticket);
    pattern.cancel();
    assert !pattern.send(ticket);
    assert !pattern.acknowledge(ticket);
    long replacement = pattern.begin();
    assert !pattern.send(ticket);
    assert pattern.send(replacement);
    pattern.cancel();
    assert !pattern.acknowledge(replacement);
    assert OmiDeviceControls.storageSupported(64L);
    assert !OmiDeviceControls.storageSupported(null);
    assert !OmiDeviceControls.storageSupported(32L);
    byte[] status = new byte[] {-1,-1,-1,-1, 1,0,0,0, 0,16,0,0, 1,0,0,0};
    long[] storage = OmiDeviceControls.storage(status);
    assert storage != null && storage[0] == 4294967295L && storage[1] == 1 && storage[2] == 4096 && storage[3] == 1;
    assert OmiDeviceControls.storage(new byte[8]) == null;
    assert OmiDeviceControls.storage(new byte[15]) == null;
    assert OmiDeviceControls.storage(new byte[17]) == null;
    assert OmiDeviceControls.storage(new byte[16]) == null;
    status[12] = 2;
    assert OmiDeviceControls.storage(status) == null;
    status[12] = 0;
    assert OmiDeviceControls.storage(status)[3] == 0;
    Long features = OmiDeviceControls.features(new byte[] {(byte) 128, 1, 0, 0});
    assert features != null && features == 384;
    assert OmiDeviceControls.features(new byte[3]) == null;
    assert OmiDeviceControls.features(new byte[5]) == null;
    assert OmiDeviceControls.features(new byte[] {-1, -1, -1, -1}) == 4294967295L;
    assert OmiDeviceControls.validWrite(features, "ledBrightness", 100);
    assert OmiDeviceControls.validWrite(features, "microphoneGain", 8);
    assert OmiDeviceControls.validWrite(features, "microphoneGain", 0);
    assert !OmiDeviceControls.validWrite(features, "microphoneGain", 9);
    assert !OmiDeviceControls.validWrite(features, "ledBrightness", 101);
    assert !OmiDeviceControls.validWrite(features, "ledBrightness", -1);
    assert !OmiDeviceControls.validWrite(features, "ledBrightness", 0.5);
    assert !OmiDeviceControls.validWrite(features, "ledBrightness", Double.NaN);
    assert !OmiDeviceControls.validWrite(null, "ledBrightness", 50);
    assert !OmiDeviceControls.validWrite(0L, "ledBrightness", 50);
    assert !OmiDeviceControls.validWrite(128L, "microphoneGain", 5);
    assert !OmiDeviceControls.validWrite(features, "firmware", 1);
    assert OmiDeviceControls.value("microphoneGain", new byte[] {8}) == 8;
    assert OmiDeviceControls.value("microphoneGain", new byte[] {9}) == null;
    assert OmiDeviceControls.value("ledBrightness", new byte[] {101}) == null;
    assert OmiDeviceControls.value("ledBrightness", new byte[0]) == null;
    System.out.println("Device feature gates and firmware setting bounds passed");
  }
}
