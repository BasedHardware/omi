package com.rnruntime;

import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.UUID;

public final class DeviceInformationTest {
  public static void main(String[] args) {
    String[][] fields = {{"2a24", "model"}, {"2a26", "firmware"}, {"2a27", "hardware"}, {"2a29", "manufacturer"}, {"2a25", "serial"}};
    for (String[] field : fields) {
      UUID id = UUID.fromString("0000" + field[0] + "-0000-1000-8000-00805f9b34fb");
      Map.Entry<String, String> value = OmiDeviceInformation.decode(id, " Omi 1.2 ".getBytes(StandardCharsets.UTF_8));
      assert value != null && value.getKey().equals(field[1]) && value.getValue().equals("Omi 1.2");
      byte[][] invalid = {new byte[0], {(byte) 0xc3, 0x28}, {0}, "a\nb".getBytes(StandardCharsets.UTF_8), new byte[513]};
      for (byte[] bytes : invalid) assert OmiDeviceInformation.decode(id, bytes) == null;
    }
    assert OmiDeviceInformation.decode(UUID.randomUUID(), new byte[] {65}) == null;
    System.out.println("Device information decoding passed");
  }
}
