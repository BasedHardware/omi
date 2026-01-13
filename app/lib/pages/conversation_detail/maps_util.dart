import 'dart:io';

import 'package:map_launcher/map_launcher.dart';

import 'package:omi/env/env.dart';

class MapsUtil {
  static String getMapImageUrl(double lat, double lng) {
    // Dark theme Google Maps with minimal labels
    const String baseUrl = "https://maps.googleapis.com/maps/api/staticmap";
    final String center = "center=$lat,$lng";
    const String zoom = "zoom=15";
    const String size = "size=800x500";
    const String scale = "scale=2";
    const String format = "format=png";

    // Custom marker styling
    final String marker = "markers=color:0x9C27B0%7Clabel:%20%7C$lat,$lng";

    final String styles = [
      // Base geometry
      "style=element:geometry%7Ccolor:0x1a1a1a",
      // Hide icons
      "style=element:labels.icon%7Cvisibility:off",
      // Text styling
      "style=element:labels.text.fill%7Ccolor:0x4a4a4a",
      "style=element:labels.text.stroke%7Ccolor:0x1a1a1a",
      // Hide administrative labels
      "style=feature:administrative%7Celement:geometry%7Cvisibility:off",
      "style=feature:administrative%7Celement:labels%7Cvisibility:off",
      "style=feature:administrative.locality%7Celement:labels.text.fill%7Ccolor:0x8a8a8a",
      "style=feature:administrative.neighborhood%7Cvisibility:off",
      "style=feature:administrative.land_parcel%7Cvisibility:off",
      // Hide POI labels
      "style=feature:poi%7Celement:labels%7Cvisibility:off",
      "style=feature:poi.business%7Cvisibility:off",
      "style=feature:poi.government%7Cvisibility:off",
      "style=feature:poi.medical%7Cvisibility:off",
      "style=feature:poi.place_of_worship%7Cvisibility:off",
      "style=feature:poi.school%7Cvisibility:off",
      "style=feature:poi.sports_complex%7Cvisibility:off",
      // Parks
      "style=feature:poi.park%7Celement:geometry%7Ccolor:0x263c3f",
      "style=feature:poi.park%7Celement:labels.text%7Cvisibility:simplified",
      "style=feature:poi.park%7Celement:labels.text.fill%7Ccolor:0x5a7a5f",
      // Roads
      "style=feature:road%7Celement:geometry%7Ccolor:0x2c2c2c",
      "style=feature:road%7Celement:labels%7Cvisibility:simplified",
      "style=feature:road%7Celement:labels.text.fill%7Ccolor:0x6a6a6a",
      "style=feature:road.arterial%7Celement:geometry%7Ccolor:0x373737",
      "style=feature:road.arterial%7Celement:labels%7Cvisibility:off",
      "style=feature:road.highway%7Celement:geometry%7Ccolor:0x444444",
      "style=feature:road.highway%7Celement:labels.text.fill%7Ccolor:0x8a8a8a",
      "style=feature:road.highway.controlled_access%7Celement:geometry%7Ccolor:0x555555",
      "style=feature:road.local%7Celement:labels%7Cvisibility:off",
      // Hide transit labels
      "style=feature:transit%7Celement:labels%7Cvisibility:off",
      // Water
      "style=feature:water%7Celement:geometry%7Ccolor:0x0e1626",
      "style=feature:water%7Celement:labels.text.fill%7Ccolor:0x3d5a5d",
      "style=feature:water%7Celement:labels.text%7Cvisibility:simplified",
    ].join("&");

    final String key = "key=${Env.googleMapsApiKey}";

    return "$baseUrl?$center&$zoom&$size&$scale&$format&$marker&$styles&$key";
  }

  static String getGoogleMapsPlaceUrl(String googlePlaceId) {
    return "https://www.google.com/maps/place/?q=place_id=$googlePlaceId";
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
