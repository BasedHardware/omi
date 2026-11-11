import 'dart:io';

import 'package:map_launcher/map_launcher.dart';
import 'package:url_launcher/url_launcher.dart';

class MapsUtil {
  static String getGoogleMapsPlaceUrl(String googlePlaceId) {
    return "https://www.google.com/maps/place/?q=place_id=$googlePlaceId";
  }

  static void launchMap(double lat, double lng) async {
    try {
      final preferredType = Platform.isIOS ? MapType.apple : MapType.google;
      if (await MapLauncher.isMapAvailable(preferredType) == true) {
        await MapLauncher.showMarker(mapType: preferredType, coords: Coords(lat, lng), title: '');
        return;
      }
      final installed = await MapLauncher.installedMaps;
      if (installed.isNotEmpty) {
        await installed.first.showMarker(coords: Coords(lat, lng), title: '');
        return;
      }
    } catch (_) {}
    // Fallback: open in browser
    final uri = Uri.parse('https://www.google.com/maps/search/?api=1&query=$lat,$lng');
    await launchUrl(uri, mode: LaunchMode.externalApplication);
  }
}
