import 'dart:typed_data';

import 'package:image/image.dart' as img;

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/models.dart';

/// Rotates an image based on its orientation metadata.
///
/// This function decodes the image, applies the necessary rotation,
/// and re-encodes it as a JPEG.
///
/// Note: This implementation uses a lossy rotation method (decode, rotate, re-encode).
/// True lossless JPEG rotation is complex and not supported by the current image library.
/// This method serves as a reliable fallback for all rotation cases.
Uint8List rotateImage(OrientedImage orientedImage) {
  // Decode the image from bytes
  final image = img.decodeImage(orientedImage.imageBytes);
  if (image == null) {
    // If decoding fails, return the original bytes
    return orientedImage.imageBytes;
  }

  img.Image rotatedImage;

  // Apply rotation based on the orientation enum
  switch (orientedImage.orientation) {
    case ImageOrientation.orientation90:
      rotatedImage = img.copyRotate(image, angle: 90);
      break;
    case ImageOrientation.orientation180:
      rotatedImage = img.copyRotate(image, angle: 180);
      break;
    case ImageOrientation.orientation270:
      rotatedImage = img.copyRotate(image, angle: -90);
      break;
    case ImageOrientation.orientation0:
    default:
      // No rotation needed
      return orientedImage.imageBytes;
  }

  // Re-encode the rotated image to JPEG format
  return Uint8List.fromList(img.encodeJpg(rotatedImage));
}
