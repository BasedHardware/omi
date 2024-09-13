import 'dart:async';
import 'package:friend_private/backend/preferences.dart';
import 'package:geolocator/geolocator.dart';
import 'package:location/location.dart';

class LocationService {
  Location location = Location();
  LocationData? locationData;
  Future<bool> enableService() async {
    bool serviceEnabled = await location.serviceEnabled();
    if (serviceEnabled) {
      return true;
    } else {
      return await location.requestService();
    }
  }

  Future<bool> displayPermissionsDialog() async {
    if (SharedPreferencesUtil().locationPermissionRequested) return false;
    if (await isServiceEnabled()) {
      SharedPreferencesUtil().locationPermissionRequested = true;
    }
    var status = await permissionStatus();
    return await isServiceEnabled() == false || (status != LocationPermission.always);
  }

  Future<bool> isServiceEnabled() => location.serviceEnabled();

  Future<LocationPermission> permissionStatus() => Geolocator.checkPermission();

  Future hasPermission() async => (await Geolocator.checkPermission()) == LocationPermission.always;

  Future<void> getDeviceLocation() async {
    locationData = await location.getLocation();
  }
}
