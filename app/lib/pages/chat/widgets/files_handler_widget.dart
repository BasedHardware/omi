import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/message.dart';

class FilesHandlerWidget extends StatelessWidget {
  final ServerMessage message;
  const FilesHandlerWidget({super.key, required this.message});

  @override
  Widget build(BuildContext context) {
    if (message.files.isEmpty) {
      return const SizedBox.shrink();
    } else {
      if (message.areFilesOfSameType()) {
        if (message.files.first.mimeTypeToFileType() == 'image') {
          return CachedNetworkImage(
            imageUrl: message.files.first.thumbnail ?? '',
            imageBuilder: (context, imageProvider) => Container(
              decoration: BoxDecoration(
                color: Theme.of(context).primaryColor,
                borderRadius: const BorderRadius.all(Radius.circular(10.0)),
              ),
              width: MediaQuery.sizeOf(context).width * 0.4,
              height: MediaQuery.sizeOf(context).width * 0.3,
            ),
            placeholder: (context, url) => const SizedBox(
              width: 48,
              height: 48,
              child: CircularProgressIndicator(
                valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
              ),
            ),
            errorWidget: (context, url, error) => const Icon(Icons.error, color: Colors.white),
          );
        } else {
          return Container(
            decoration: BoxDecoration(
              color: Theme.of(context).primaryColor,
              borderRadius: const BorderRadius.all(Radius.circular(10.0)),
            ),
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 12),
            width: MediaQuery.sizeOf(context).width * 0.5,
            child: Row(
              children: [
                const Icon(Icons.insert_drive_file, color: Colors.white),
                const SizedBox(width: 8),
                Column(
                  children: [
                    Text(
                      message.files.first.name,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 14,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          );
        }
      } else {
        return Container();
      }
    }
  }
}
