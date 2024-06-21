import 'package:flutter/material.dart';

import '../../../backend/database/message.dart';

class HumanMessage extends StatelessWidget {
  final Message message;

  const HumanMessage({super.key, required this.message});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 20, 0, 20),
      child: Wrap(
        alignment: WrapAlignment.end,
        children: [
          Container(
            decoration: BoxDecoration(
              color: Theme.of(context).primaryColor,
              borderRadius: const BorderRadius.all(Radius.circular(16.0)),
            ),
            padding: const EdgeInsets.all(16.0),
            child: Text(
              message.text,
              style: Theme.of(context).textTheme.bodyMedium,
            ),
          ),
        ],
      ),
    );
  }
}
