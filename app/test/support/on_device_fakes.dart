import 'package:omi/services/on_device/on_device_model.dart';
import 'package:omi/services/on_device/phone_power_source.dart';

/// An [OnDeviceModel] whose status the test sets directly; records calls.
class FakeOnDeviceModel extends OnDeviceModel {
  FakeOnDeviceModel(
      [OnDeviceModelStatus? status, this.engine, this.engineResolved = true, this.detectionFailed = false])
      : _status = status ?? const OnDeviceModelStatus(phase: OnDeviceModelPhase.installed);

  @override
  String? engine;

  @override
  bool engineResolved;

  @override
  bool detectionFailed;

  /// Runs at the start of [refresh], before the engine is marked resolved.
  Future<void> Function()? beforeRefresh;

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
  Future<void> refresh() async {
    final hook = beforeRefresh;
    if (hook != null) await hook();
    engineResolved = true;
    notifyListeners();
  }

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
