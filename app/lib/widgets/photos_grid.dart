import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:friend_private/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:provider/provider.dart';
import 'package:tuple/tuple.dart';

class PhotosGridComponent extends StatelessWidget {
  const PhotosGridComponent({super.key});

  @override
  Widget build(BuildContext context) {
    return Selector<ConversationDetailProvider, List<Tuple2<String, String>>>(
        selector: (context, provider) => provider.photosData,
        builder: (context, photos, child) {
          return GridView.builder(
            padding: EdgeInsets.zero,
            shrinkWrap: true,
            scrollDirection: Axis.vertical,
            itemCount: photos.length,
            physics: const NeverScrollableScrollPhysics(),
            itemBuilder: (context, idx) {
              return GestureDetector(
                onTap: () {
                  showDialog(
                      context: context,
                      builder: (c) {
                        return getDialog(
                          context,
                          () => Navigator.pop(context),
                          () => Navigator.pop(context),
                          'Description',
                          photos[idx].item2,
                          singleButton: true,
                        );
                      });
                },
                child: Container(
                  decoration: BoxDecoration(border: Border.all(color: Colors.grey.shade600, width: 0.5)),
                  child: Image.memory(base64Decode(photos[idx].item1), fit: BoxFit.cover),
                ),
              );
            },
            gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: 3,
              crossAxisSpacing: 8,
              mainAxisSpacing: 8,
            ),
          );
        });
  }
}
