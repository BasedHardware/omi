import 'package:omi/services/on_device/on_device_model.dart';
import 'package:omi/services/on_device/phone_power_source.dart';

/// An [OnDeviceModel] whose status the test sets directly; records calls.
class FakeOnDeviceModel extends OnDeviceModel {
  FakeOnDeviceModel([OnDeviceModelStatus? status, this.engine])
      : _status = status ?? const OnDeviceModelStatus(phase: OnDeviceModelPhase.installed);

  @override
  final String? engine;
  OnDeviceModelStatus _status;
  int downloads = 0;
  bool? lastWifiOnly;
  int cancels = 0;
  int removals = 0;

  @override
  OnDeviceModelStatus get status => _status;

  set status(OnDeviceModelStatus value) {
    _status = value;
    notifyListeners();
  }

  @override
  Future<void> refresh() async {}

  @override
  Future<void> download({required bool wifiOnly}) async {
    downloads++;
    lastWifiOnly = wifiOnly;
  }

  @override
  void cancel() => cancels++;

  @override
  Future<void> remove() async {
    removals++;
    status = const OnDeviceModelStatus(phase: OnDeviceModelPhase.notDownloaded);
  }
}

class FakePhonePowerSource implements PhonePowerSource {
  FakePhonePowerSource([this.state = PhonePowerState.unknown]);

  PhonePowerState state;

  @override
  Future<PhonePowerState> read() async => state;
}
