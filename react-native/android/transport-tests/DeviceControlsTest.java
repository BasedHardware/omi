package com.rnruntime;

public final class DeviceControlsTest {
  public static void main(String[] args) {
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
