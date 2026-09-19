import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

/// Decorative marketplace artwork; the adjacent app name provides its identity.
class AppThumbnail extends StatelessWidget {
  final String imageUrl;

  const AppThumbnail({super.key, required this.imageUrl});

  Widget _placeholder({bool unavailable = false}) => Container(
        width: 60,
        height: 60,
        decoration: BoxDecoration(color: const Color(0xFF35343B), borderRadius: BorderRadius.circular(8)),
        child: unavailable ? const Icon(Icons.image_not_supported_outlined, color: Colors.white54, size: 24) : null,
      );

  @override
  Widget build(BuildContext context) => ExcludeSemantics(
        child: CachedNetworkImage(
          imageUrl: imageUrl,
          httpHeaders: const {
            'User-Agent':
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
          },
          imageBuilder: (context, imageProvider) => Container(
            width: 60,
            height: 60,
            decoration: BoxDecoration(
              shape: BoxShape.rectangle,
              borderRadius: BorderRadius.circular(8),
              image: DecorationImage(image: imageProvider, fit: BoxFit.cover),
            ),
          ),
          placeholder: (context, url) => _placeholder(),
          errorWidget: (context, url, error) => _placeholder(unavailable: true),
        ),
      );
}
