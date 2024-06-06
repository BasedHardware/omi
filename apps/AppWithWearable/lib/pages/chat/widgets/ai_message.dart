import 'package:auto_size_text/auto_size_text.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:friend_private/backend/storage/message.dart';

class AIMessage extends StatelessWidget {
  final Message message;

  const AIMessage({super.key, required this.message});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.max,
      children: [
        Column(
          mainAxisSize: MainAxisSize.max,
          crossAxisAlignment: CrossAxisAlignment.start,
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
                color: const Color(0x1AF7F4F4),
                boxShadow: const [
                  BoxShadow(
                    blurRadius: 3.0,
                    color: Color(0x33000000),
                    offset: Offset(0.0, 1.0),
                  )
                ],
                borderRadius: BorderRadius.circular(12.0),
                border: Border.all(
                  color: Theme.of(context).primaryColor,
                  width: 1.0,
                ),
              ),
              child: Padding(
                padding: const EdgeInsets.all(12.0),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SelectionArea(
                        child: AutoSizeText(
                      message.text.replaceAll(r'\n', '\n'),
                      style: TextStyle(fontSize: 14.0, fontWeight: FontWeight.w500, color: Colors.grey.shade200),
                    )),
                  ],
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(0.0, 6.0, 0.0, 0.0),
              child: InkWell(
                splashColor: Colors.transparent,
                focusColor: Colors.transparent,
                hoverColor: Colors.transparent,
                highlightColor: Colors.transparent,
                onTap: () async {
                  await Clipboard.setData(ClipboardData(text: message.text));
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: const Text(
                        'Response copied to clipboard.',
                        style: TextStyle(
                          color: Color(0x00000000),
                          fontSize: 12.0,
                        ),
                      ),
                      duration: const Duration(milliseconds: 2000),
                      backgroundColor: Theme.of(context).primaryColor,
                    ),
                  );
                },
                child: Row(
                  mainAxisSize: MainAxisSize.max,
                  children: [
                    Padding(
                      padding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 4.0, 0.0),
                      child: Icon(
                        Icons.content_copy,
                        color: Theme.of(context).primaryColor,
                        size: 10.0,
                      ),
                    ),
                    Text(
                      'Copy response',
                      style: TextStyle(color: Theme.of(context).primaryColor, fontSize: 10.0),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }
}
