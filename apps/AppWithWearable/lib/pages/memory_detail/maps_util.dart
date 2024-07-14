import 'dart:io';

import 'package:friend_private/env/env.dart';
import 'package:map_launcher/map_launcher.dart';

class MapsUtil {
  static String getMapImageUrl(double lat, double lng) {
    return "https://maps.googleapis.com/maps/api/staticmap?center=$lat,$lng&zoom=14&size=450x450&markers=color:red%7C$lat,$lng&key=${Env.googleMapsApiKey}";
  }

  static void launchMap(double lat, double lng) async {
    if (Platform.isIOS) {
      await MapLauncher.showMarker(
        mapType: MapType.apple,
        coords: Coords(lat, lng),
        title: '',
      );
    } else {
      await MapLauncher.showMarker(
        mapType: MapType.google,
        coords: Coords(lat, lng),
        title: '',
      );
    }
  }
}
