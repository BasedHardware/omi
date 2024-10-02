import 'package:flutter/material.dart';
import 'package:friend_private/services/translation_service.dart';

class EmptyMemoriesWidget extends StatefulWidget {
  const EmptyMemoriesWidget({super.key});

  @override
  State<EmptyMemoriesWidget> createState() => _EmptyMemoriesWidgetState();
}

class _EmptyMemoriesWidgetState extends State<EmptyMemoriesWidget> {
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(top: 240.0),
      child: Text(
          TranslationService.translate('No memories generated yet.'),
        style: TextStyle(color: Colors.grey, fontSize: 16),
      ),
    );
  }
}
