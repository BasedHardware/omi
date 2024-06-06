import 'package:flutter/material.dart';
import 'package:friend_private/backend/storage/message.dart';

class HumanMessage extends StatelessWidget {
  final Message message;

  const HumanMessage({super.key, required this.message});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.max,
      mainAxisAlignment: MainAxisAlignment.end,
      children: [
        Container(
          constraints: BoxConstraints(
            maxWidth: () {
              if (MediaQuery.sizeOf(context).width >= 1170.0) {
                return 700.0;
              } else if (MediaQuery.sizeOf(context).width <= 470.0) {
                return 330.0;
              } else {
                return 530.0;
              }
            }(),
          ),
          decoration: BoxDecoration(
            color: Theme.of(context).scaffoldBackgroundColor,
            borderRadius: BorderRadius.circular(12.0),
          ),
          margin: const EdgeInsets.only(bottom: 12, top: 8),
          child: Padding(
            padding: const EdgeInsets.all(12.0),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  message.text,
                  style: TextStyle(
                    color: Theme.of(context).primaryColor,
                    fontWeight: FontWeight.w500
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}
