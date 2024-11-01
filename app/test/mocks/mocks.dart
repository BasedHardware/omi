import 'package:mockito/annotations.dart';
import 'package:flutter/services.dart';
import 'package:friend_private/providers/capture_provider.dart';
import 'package:friend_private/services/wals.dart';
import 'package:friend_private/services/devices.dart';
import 'package:friend_private/services/watch_manager.dart';

@GenerateMocks([
  MethodChannel,
  CaptureProvider,
  IWalService,
  IDeviceServiceSubsciption,
  WatchManager,
])
void main() {}
