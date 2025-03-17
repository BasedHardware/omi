import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:omi/backend/schema/message.dart';

class FilesHandlerWidget extends StatelessWidget {
  final ServerMessage message;
  const FilesHandlerWidget({super.key, required this.message});

  @override
  Widget build(BuildContext context) {
    if (message.files.isEmpty || message.filesId.isEmpty) {
      return const SizedBox.shrink();
    } else {
      return SizedBox(
        width: MediaQuery.sizeOf(context).width * 0.9,
        height: MediaQuery.sizeOf(context).height * 0.12,
        child: ListView.separated(
          itemCount: message.files.length,
          shrinkWrap: true,
          reverse: true,
          scrollDirection: Axis.horizontal,
          separatorBuilder: (context, index) {
            return const SizedBox(width: 6);
          },
          itemBuilder: (context, index) {
            if (message.files[index].mimeTypeToFileType() == 'image') {
              return CachedNetworkImage(
                imageUrl: message.files[index].thumbnail ?? '',
                imageBuilder: (context, imageProvider) => Container(
                  margin: const EdgeInsets.only(bottom: 6, top: 2),
                  decoration: BoxDecoration(
                    color: Theme.of(context).primaryColor,
                    borderRadius: const BorderRadius.all(Radius.circular(10.0)),
                    image: DecorationImage(image: imageProvider, fit: BoxFit.cover),
                  ),
                  width: MediaQuery.sizeOf(context).width * 0.28,
                  height: MediaQuery.sizeOf(context).width * 0.22,
                ),
                placeholder: (context, url) => SizedBox(
                  width: MediaQuery.sizeOf(context).width * 0.28,
                  height: MediaQuery.sizeOf(context).width * 0.22,
                  child: const Center(
                    child: CircularProgressIndicator(
                      valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                    ),
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
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
                margin: const EdgeInsets.only(bottom: 6, top: 2),
                width: MediaQuery.sizeOf(context).width * 0.32,
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const Icon(Icons.insert_drive_file, color: Colors.white),
                    const SizedBox(height: 6),
                    Text(
                      message.files[index].name,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 14,
                      ),
                    ),
                  ],
                ),
              );
            }
          },
        ),
      );
    }
  }
}
