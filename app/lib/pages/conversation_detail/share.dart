import 'dart:convert';
import 'dart:io';
import 'dart:ui';

import 'package:flutter/widgets.dart' show StringCharacters;

import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/widgets.dart' show conversationDurationLabel;
import 'package:omi/ui/format/omi_date_format.dart';
import 'package:omi/utils/conversations/conversation_title.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/utils/share_links.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// Opens the system share sheet with the conversation's public link. Resolves with the platform's
/// result: [ShareResultStatus.dismissed] means the reader closed the sheet without sharing
/// (reported on iOS and Android 5.1+); [ShareResultStatus.unavailable] means the platform could
/// not tell.
Future<ShareResult> shareConversationLink(ServerConversation conversation, {Rect? sharePositionOrigin}) async {
  // The share subject is a display surface: legacy titles lose citation debris (`[s01234]`).
  final subject = presentableConversationTitle(conversation);
  final sid = newShareId();
  final outcome = await SharePlus.instance.share(
    ShareParams(
      text: conversationShareUrl(conversation.id, sid: sid),
      subject: subject.isEmpty ? null : subject,
      sharePositionOrigin: sharePositionOrigin,
    ),
  );
  final analytics = PlatformManager.instance.analytics;
  final targetApp = outcome.status == ShareResultStatus.success ? shareTargetApp(outcome.raw) : null;
  analytics.track('Conversation Shared', properties: {
    ...analytics.getConversationEventProperties(conversation),
    'share_method': 'url_share',
    'share_id': sid,
    'share_status': outcome.status.name,
    if (targetApp != null) 'target_app': targetApp,
  });
  return outcome;
}

/// The whole conversation as a plain-text document: title, when it started and how long it ran (the
/// detail page's own rule, [conversationDurationLabel]), then every line as "[time] Name: text", the
/// same text Copy Transcript puts on the clipboard.
String conversationTranscriptDocument(
  ServerConversation conversation, {
  required OmiDateFormat dates,
  required AppLocalizations l10n,
  String? transcript,
}) {
  final title = presentableConversationTitle(conversation);
  final start = (conversation.startedAt ?? conversation.createdAt).toLocal();
  final duration = conversationDurationLabel(conversation, l10n);
  final when = [dates.dateTime(start), if (duration.isNotEmpty) duration].join(' · ');
  final body = transcript ?? conversation.getTranscript(generate: true);
  return '${[if (title.isNotEmpty) title, when, '', body].join('\n').trimRight()}\n';
}

/// The most a file name may take, in UTF-8 bytes. Android's file systems refuse names over 255
/// bytes, and a title in Devanagari or Thai reaches that well before 60 characters.
const int _maxFileNameBytes = 180;

/// A file name the share sheet and Files can show: the start as YYYY-MM-DD HHMM, then the title,
/// with nothing a file system refuses.
///
/// Built from numbers rather than a locale pattern on purpose: a file name is not shown copy, and
/// the same stamp in every language keeps exported transcripts sorting by date.
String conversationTranscriptFileName(ServerConversation conversation) {
  final start = (conversation.startedAt ?? conversation.createdAt).toLocal();
  String two(int n) => n.toString().padLeft(2, '0');
  final stamp = '${start.year}-${two(start.month)}-${two(start.day)} ${two(start.hour)}${two(start.minute)}';
  final title = presentableConversationTitle(conversation)
      .replaceAll(RegExp(r'[\\/:*?"<>|\x00-\x1f\x7f]'), ' ')
      .replaceAll(RegExp(r'\s+'), ' ')
      .trim();
  // Whole graphemes only, so an emoji or a conjunct is never cut in half.
  var name = stamp;
  for (final grapheme in title.characters) {
    final next = name == stamp ? '$stamp $grapheme' : '$name$grapheme';
    if (utf8.encode('$next.txt').length > _maxFileNameBytes) break;
    name = next;
  }
  return '${name.trimRight()}.txt';
}

/// Exports live in a folder of their own and are swept a day later, so private transcripts do not
/// pile up in plain text. Not deleted as soon as the sheet closes: on Android the receiving app may
/// still be reading the file.
const Duration _exportRetention = Duration(days: 1);

/// Removes exports last modified before [cutoff]. Best effort: an old export that cannot be removed
/// (still open in the app it was shared to) must not fail the new one. [delete] is a test seam.
Future<void> sweepTranscriptExports(Directory folder, DateTime cutoff, {Future<void> Function(File)? delete}) async {
  await for (final old in folder.list()) {
    try {
      if (old is File && (await old.stat()).modified.isBefore(cutoff)) await (delete ?? (f) => f.delete())(old);
    } on FileSystemException {
      continue;
    }
  }
}

/// Writes the transcript to `<temp>/transcript_exports/<name>.txt`, first removing exports older
/// than [_exportRetention].
Future<File> writeConversationTranscript(
  ServerConversation conversation, {
  required OmiDateFormat dates,
  required AppLocalizations l10n,
  Directory? temporaryDirectory,
  DateTime? now,
}) async {
  final root = temporaryDirectory ?? await getTemporaryDirectory();
  final folder = Directory('${root.path}/transcript_exports');
  if (await folder.exists()) {
    await sweepTranscriptExports(folder, (now ?? DateTime.now()).subtract(_exportRetention));
  } else {
    await folder.create(recursive: true);
  }
  final file = File('${folder.path}/${conversationTranscriptFileName(conversation)}');
  await file.writeAsString(conversationTranscriptDocument(conversation, dates: dates, l10n: l10n), flush: true);
  return file;
}

/// Opens the share sheet with a written transcript: Save to Files, AirDrop, Mail, Messages.
Future<ShareResult> shareConversationTranscriptFile(File file, ServerConversation conversation,
    {Rect? sharePositionOrigin}) {
  final subject = presentableConversationTitle(conversation);
  return SharePlus.instance.share(
    ShareParams(
      files: [XFile(file.path, mimeType: 'text/plain')],
      subject: subject.isEmpty ? null : subject,
      sharePositionOrigin: sharePositionOrigin,
    ),
  );
}
