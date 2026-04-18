import 'dart:convert';
import 'package:flutter/material.dart';

import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:url_launcher/url_launcher.dart';

import 'genui_widget.dart';
import 'genui_message_widget.dart';

Widget getMarkdownWidget(
  BuildContext context, 
  String message, {
  Function(String)? onAskOmi,
  Function(String)? sendMessage,
}) {
  try {
    // Strip markdown fences (```json ... ```) that LLMs sometimes add
    var cleaned = message.trim();
    final fencePattern = RegExp(r'^```(?:json)?\s*\n?(.*?)\n?\s*```$', dotAll: true);
    final fenceMatch = fencePattern.firstMatch(cleaned);
    if (fenceMatch != null) {
      cleaned = fenceMatch.group(1)?.trim() ?? cleaned;
    }
    final decoded = jsonDecode(cleaned);
    if (decoded is Map && decoded['type'] == 'genui' && decoded['component'] == 'location_prompt') {
      return GenUIMessageWidget(message: cleaned, sendMessage: sendMessage ?? (s) {});
    }
  } catch (_) {}
  
  final genui = GenUIMessage.tryParse(message);
  
  if (genui != null) {
    return _buildGenUIWidget(genui, onAskOmi, sendMessage);
  }
  
  return MarkdownBody(
    data: message.trimRight(),
    selectable: false,
    styleSheet: MarkdownStyleSheet(
      p: const TextStyle(color: Colors.white, fontSize: 16, height: 1.4),
      a: const TextStyle(color: Colors.blue, decoration: TextDecoration.underline),
      listBullet: const TextStyle(color: Colors.white, fontSize: 16),
      blockquote: const TextStyle(color: Colors.white, fontSize: 16, height: 1.4, backgroundColor: Colors.transparent),
      blockquoteDecoration: BoxDecoration(color: const Color(0xFF35343B), borderRadius: BorderRadius.circular(4)),
      code: const TextStyle(color: Colors.white, backgroundColor: Colors.transparent, fontFamily: 'monospace'),
      codeblockDecoration: BoxDecoration(color: const Color(0xFF1F1F25), borderRadius: BorderRadius.circular(8)),
    ),
    onTapLink: (text, href, title) {
      if (href != null) {
        launchUrl(Uri.parse(href));
      }
    },
  );
}

Widget _buildGenUIWidget(GenUIMessage genui, Function(String)? onAskOmi, Function(String)? sendMessage) {
  void handleAction(String action) {
    if (sendMessage != null) {
      sendMessage(action);
    } else if (onAskOmi != null) {
      onAskOmi(action);
    }
  }

  switch (genui.component) {
    case 'location_prompt':
      return LocationSharePrompt(
        message: genui.message,
        actions: genui.actions ?? ['yes', 'no'],
        onAction: handleAction,
      );
    
    case 'location_answer':
      if (genui.location != null) {
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (genui.message.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Text(
                  genui.message,
                  style: const TextStyle(color: Colors.white, fontSize: 16),
                ),
              ),
            MapCard(
              location: genui.location!,
              message: genui.location!.label,
            ),
          ],
        );
      }
      return Text(genui.message, style: const TextStyle(color: Colors.white, fontSize: 16));
    
    case 'map_result':
      if (genui.location != null) {
        return MapCard(
          message: genui.message,
          location: genui.location!,
        );
      }
      return Text(genui.message, style: const TextStyle(color: Colors.white, fontSize: 16));
    
    case 'result_card':
    case 'result':
      return ResultCard(
        title: genui.title ?? '',
        description: genui.description,
        distance: genui.distance,
        location: genui.location,
        actions: genui.actions,
        onAction: handleAction,
      );
    
    case 'confirm_prompt':
      return ConfirmPrompt(
        message: genui.message,
        actions: genui.actions ?? ['yes', 'no'],
        onAction: handleAction,
      );
    
    default:
      return Text(genui.message, style: const TextStyle(color: Colors.white, fontSize: 16));
  }
}
