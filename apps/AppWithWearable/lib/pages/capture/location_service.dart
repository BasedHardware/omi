import 'dart:async';

import 'package:location/location.dart';

class LocationService {
  Location location = Location();

  Future<bool> enableService() async {
    bool serviceEnabled = await location.serviceEnabled();
    if (!serviceEnabled) {
      serviceEnabled = await location.requestService();
      if (!serviceEnabled) {
        return false;
      } else {
        return true;
      }
    } else {
      return true;
    }
  }

  Future<PermissionStatus> requestPermission() async {
    PermissionStatus permissionGranted = await location.hasPermission();
    if (permissionGranted == PermissionStatus.denied) {
      permissionGranted = await location.requestPermission();
    }
    return permissionGranted;
  }

  Future hasPermission() async {
    return await location.hasPermission() == PermissionStatus.granted;
  }

  Future<LocationData?> getLocation() async {
    if (await hasPermission()) {
      return await location.getLocation();
    } else {
      return null;
    }
  }
}
