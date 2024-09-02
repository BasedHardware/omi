import 'dart:async';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/geolocation.dart';
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
    SharedPreferencesUtil().locationPermissionRequested = true;
    var status = await permissionStatus();
    return await isServiceEnabled() == false ||
        (status != PermissionStatus.granted && status != PermissionStatus.deniedForever);
  }

  Future<bool> isServiceEnabled() => location.serviceEnabled();

  Future<PermissionStatus> requestPermission() async {
    PermissionStatus permissionGranted = await location.hasPermission();
    if (permissionGranted == PermissionStatus.denied) {
      permissionGranted = await location.requestPermission();
    }
    LocationPermission perm = await Geolocator.checkPermission();
    print('Permission: $perm');
    SharedPreferencesUtil().locationPermissionState = perm.name;
    return permissionGranted;
  }

  Future requestBackgroundPermission() async {
    final result = await location.isBackgroundModeEnabled();
    if (!result) {
      await location.enableBackgroundMode(enable: true);
    }
    return result;
  }

  Future<PermissionStatus> permissionStatus() => location.hasPermission();

  Future hasPermission() async => (await location.hasPermission()) == PermissionStatus.granted;

  Future<void> getDeviceLocation() async {
    locationData = await location.getLocation();
  }

  Future<Geolocation?> getGeolocationDetails() async {
    try {
      if (await hasPermission()) {
        if (await location.isBackgroundModeEnabled()) {
          if (await location.serviceEnabled()) {
            await location.requestService();
          }
          Future<void> timeout = Future.delayed(const Duration(seconds: 1));
          await Future.any([getDeviceLocation(), timeout]);
          if (locationData == null) {
            return null;
          } else {
            return Geolocation(latitude: locationData!.latitude, longitude: locationData!.longitude);
          }
        } else {
          try {
            await getDeviceLocation();
            if (locationData != null) {
              return Geolocation(latitude: locationData!.latitude, longitude: locationData!.longitude);
            }
          } catch (e) {
            debugPrint("Error getting location data $e");
          }
          return null;
        }
      } else {
        return null;
      }
    } catch (e) {
      debugPrint("Error getting geolocation details $e");
      return null;
    }
  }
}
