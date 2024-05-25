import 'package:friend_private/backend/schema/structs/b_t_device_struct.dart';
import 'package:friend_private/utils/ble/connect.dart';
import 'package:friend_private/utils/ble/find.dart';

Future<BTDeviceStruct?> scanAndConnectDevice() async {
  while (true) {
    List<BTDeviceStruct> foundDevices = await bleFindDevices();
    try {
      final friendDevice = foundDevices.firstWhere(
        (device) => device.name == 'Friend' || device.name == 'Super',
      );
      await bleConnectDevice(friendDevice);
      return friendDevice;
    } catch (e) {
      print(e);
      // debugPrint('No matching device found, continue scanning');
    }
    await Future.delayed(const Duration(seconds: 2));
  }
}
