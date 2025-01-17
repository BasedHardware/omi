import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/message.dart';
import 'package:friend_private/widgets/extensions/string.dart';
import 'package:friend_private/utils/other/temp.dart';

class HumanMessage extends StatelessWidget {
  final ServerMessage message;

  const HumanMessage({super.key, required this.message});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 20, 0, 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Padding(
            padding: const EdgeInsets.only(right: 8.0, bottom: 4.0),
            child: Text(
              formatChatTimestamp(message.createdAt),
              style: TextStyle(
                color: Colors.grey.shade500,
                fontSize: 12,
              ),
            ),
          ),
          message.files.isNotEmpty
              ? Padding(
                  padding: const EdgeInsets.only(bottom: 4.0),
                  child: message.files.first.mimeTypeToFileType() != 'image'
                      ? CachedNetworkImage(
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
                        )
                      : Container(
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
                        ),
                )
              : Container(),
          Wrap(
            alignment: WrapAlignment.end,
            children: [
              Container(
                decoration: BoxDecoration(
                  color: Theme.of(context).primaryColor,
                  borderRadius: const BorderRadius.only(
                    topLeft: Radius.circular(16.0),
                    topRight: Radius.circular(2.0),
                    bottomRight: Radius.circular(16.0),
                    bottomLeft: Radius.circular(16.0),
                  ),
                ),
                padding: const EdgeInsets.all(16.0),
                child: Text(
                  message.text.decodeString,
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
