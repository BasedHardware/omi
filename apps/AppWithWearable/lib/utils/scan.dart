import 'package:friend_private/backend/schema/structs/b_t_device_struct.dart';
import '/utils/actions/index.dart' as actions;

Future<BTDeviceStruct?> scanAndConnectDevice() async {
  while (true) {
    List<BTDeviceStruct> foundDevices = await actions.ble0findDevices();
    try {
      final friendDevice = foundDevices.firstWhere(
        (device) => device.name == 'Friend' || device.name == 'Super',
      );
      await actions.ble0connectDevice(friendDevice);
      return friendDevice;
    } catch (e) {
      // debugPrint('No matching device found, continue scanning');
    }

    await Future.delayed(const Duration(seconds: 2));
  }
}
