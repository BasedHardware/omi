import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';

import 'package:just_audio/just_audio.dart';
import 'package:path_provider/path_provider.dart';

import 'package:omi/backend/http/api/speaker_labels.dart';
import 'package:omi/backend/http/api/speaker_tag_prompts.dart' as clips;
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';

/// Answers one earlier voice: [same] labels it as the person, otherwise rejects that person for it.
typedef VoiceMatchAnswer = Future<bool> Function(PersonVoiceMatch match, bool same);

/// Plays the stored clip of one earlier voice; false when it cannot be played.
typedef VoiceMatchClipPlayer = Future<bool> Function(PersonVoiceMatch match);

/// "Is this also Maya?": the same voice in earlier conversations, one answer per conversation.
Future<void> showEarlierVoiceMatchesSheet(
  BuildContext context, {
  required String personName,
  required List<PersonVoiceMatch> matches,
  required VoiceMatchAnswer onAnswer,
  VoiceMatchClipPlayer? playClip,
}) {
  return showOmiSheet<void>(
    context: context,
    title: context.l10n.speakerLabelText('alsoTitle', personName),
    builder: (_) => EarlierVoiceMatchesList(
      personName: personName,
      matches: matches,
      onAnswer: onAnswer,
      playClip: playClip,
    ),
    nativeBuilder: (_) => EarlierVoiceMatchesList(
      personName: personName,
      matches: matches,
      onAnswer: onAnswer,
      playClip: playClip,
      native: true,
    ),
  );
}

class EarlierVoiceMatchesList extends StatefulWidget {
  const EarlierVoiceMatchesList({
    super.key,
    required this.personName,
    required this.matches,
    required this.onAnswer,
    this.playClip,
    this.native = false,
  });

  /// Presents the list as a native sheet whose fallback is this same list in the sheet shell.
  final bool native;
  final String personName;
  final List<PersonVoiceMatch> matches;
  final VoiceMatchAnswer onAnswer;
  final VoiceMatchClipPlayer? playClip;

  @override
  State<EarlierVoiceMatchesList> createState() => _EarlierVoiceMatchesListState();
}

class _EarlierVoiceMatchesListState extends State<EarlierVoiceMatchesList> {
  late final List<PersonVoiceMatch> _open = List.of(widget.matches);
  final Set<PersonVoiceMatch> _saving = {};
  final _player = _VoiceMatchClipPlayer();

  @override
  void dispose() {
    _player.dispose();
    super.dispose();
  }

  Future<void> _play(PersonVoiceMatch match) async {
    OmiHaptics.selection();
    final played = await (widget.playClip ?? _player.play)(match);
    if (!played && mounted) OmiFeedback.info(context, context.l10n.speakerTagPromptClipUnavailable);
  }

  Future<void> _answer(PersonVoiceMatch match, bool same) async {
    if (_saving.contains(match)) return;
    OmiHaptics.light();
    setState(() => _saving.add(match));
    final saved = await widget.onAnswer(match, same);
    if (!mounted) return;
    setState(() {
      _saving.remove(match);
      if (saved) _open.remove(match);
    });
    if (!saved) {
      OmiFeedback.error(context, context.l10n.speakerTagPromptAnswerFailed);
    } else if (_open.isEmpty && ModalRoute.of(context)?.isCurrent != false) {
      // Not while the sheet is already closing, which would pop the page beneath it.
      Navigator.of(context).pop();
    }
  }

  /// Resolves a native command: [index] is the match's position in the sheet's original
  /// [EarlierVoiceMatchesList.matches], so it never shifts when another match is answered. An
  /// answered match makes the command a no-op.
  PersonVoiceMatch? _nativeMatch(int index) {
    if (index < 0 || index >= widget.matches.length) return null;
    final match = widget.matches[index];
    return _open.any((open) => identical(open, match)) ? match : null;
  }

  /// One section per open match, identified by its index in the original
  /// [EarlierVoiceMatchesList.matches] list (stable while others are answered), never by a server id.
  Widget _native(BuildContext context, Widget fallback) {
    final l10n = context.l10n;
    final dates = OmiDateFormat.of(context);
    final title = l10n.speakerLabelText('alsoTitle', widget.personName);
    void run(int index, Future<void> Function(PersonVoiceMatch match) action) {
      final current = _nativeMatch(index);
      if (current != null) unawaited(action(current));
    }

    return IosNativeSurface(
      title: title,
      toolbar: [
        NativeRow('voice_match_close', l10n.close, symbol: 'xmark', action: (_) => Navigator.of(context).maybePop()),
      ],
      sections: [
        for (final (index, match) in widget.matches.indexed)
          if (_open.any((open) => identical(open, match)))
            NativeSection(
                'voice_match:$index',
                [
                  NativeRow('voice_match_when:$index', match.title.isEmpty ? l10n.conversationTab : match.title,
                      kind: 'label',
                      subtitle: [
                        dates.dayHeader(match.startedAt.toLocal()),
                        l10n.speakerLabelTalkTime(OmiDuration.compact(match.talkSeconds.round(), l10n)),
                      ].join(' · ')),
                  NativeRow('voice_match_play:$index', l10n.speakerTagPromptPlayClip,
                      symbol: 'play.fill', action: (_) => run(index, _play)),
                  NativeRow('voice_match_yes:$index', l10n.yes,
                      symbol: 'checkmark',
                      subtitle: _saving.contains(match) ? l10n.saving : '',
                      enabled: !_saving.contains(match),
                      action: (_) => run(index, (match) => _answer(match, true))),
                  NativeRow('voice_match_no:$index', l10n.no,
                      enabled: !_saving.contains(match), action: (_) => run(index, (match) => _answer(match, false))),
                ],
                footer: identical(match, _open.first) ? l10n.speakerLabelText('alsoBody', '') : ''),
      ],
      fallback: OmiSheetScaffold(title: title, child: fallback),
    );
  }

  @override
  Widget build(BuildContext context) {
    final body = _flutter(context);
    return widget.native ? _native(context, body) : body;
  }

  Widget _flutter(BuildContext context) {
    final l10n = context.l10n;
    final dates = OmiDateFormat.of(context);
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            l10n.speakerLabelText('alsoBody', ''),
            style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
          ),
          const SizedBox(height: OmiSpacing.sm),
          for (final match in _open)
            Container(
              key: Key('voice_match_${match.conversationId}_${match.speakerId}'),
              margin: const EdgeInsets.only(bottom: OmiSpacing.xs),
              padding: const EdgeInsets.fromLTRB(OmiSpacing.xxs, OmiSpacing.xs, OmiSpacing.sm, OmiSpacing.xs),
              decoration: BoxDecoration(
                color: OmiColors.surface2,
                borderRadius: OmiRadius.mdAll,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      OmiIconButton(
                        icon: const Icon(Icons.play_arrow, size: 20),
                        label: l10n.speakerTagPromptPlayClip,
                        onPressed: () => _play(match),
                      ),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              match.title.isEmpty ? l10n.conversationTab : match.title,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: OmiType.subhead.copyWith(fontWeight: FontWeight.w500),
                            ),
                            Text(
                              [
                                dates.dayHeader(match.startedAt.toLocal()),
                                l10n.speakerLabelTalkTime(OmiDuration.compact(match.talkSeconds.round(), l10n)),
                              ].join(' · '),
                              style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                  Padding(
                    padding: const EdgeInsets.only(left: OmiSpacing.xs),
                    child: Row(
                      children: [
                        OmiButton(
                          label: l10n.yes,
                          size: OmiButtonSize.compact,
                          isLoading: _saving.contains(match),
                          onPressed: () => _answer(match, true),
                        ),
                        const SizedBox(width: OmiSpacing.xs),
                        OmiButton.secondary(
                          label: l10n.no,
                          size: OmiButtonSize.compact,
                          onPressed: _saving.contains(match) ? null : () => _answer(match, false),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          const SizedBox(height: OmiSpacing.md),
        ],
      ),
    );
  }
}

/// Loads a voice's stored clip and plays it once; a new play replaces the one in progress.
class _VoiceMatchClipPlayer {
  AudioPlayer? _player;
  int _ticket = 0;

  Future<bool> play(PersonVoiceMatch match) async {
    final ticket = ++_ticket;
    final clip = await clips.getSpeakerTagPromptClip(
      conversationId: match.conversationId,
      start: match.clipStart,
      end: match.clipEnd,
    );
    if (ticket != _ticket) return true;
    final Uint8List wav;
    switch (clip) {
      case ApiSuccess(:final data):
        wav = data;
      case ApiFailure():
        return false;
    }
    File? file;
    try {
      final directory = await getTemporaryDirectory();
      file = File('${directory.path}/voice_match_$ticket.wav');
      await file.writeAsBytes(wav, flush: true);
      if (ticket != _ticket) return true;
      final player = _player ??= AudioPlayer();
      await player.stop();
      await player.setFilePath(file.path);
      await player.play();
      return true;
    } catch (error) {
      Logger.debug('voice match clip playback failed: ${error.runtimeType}');
      return false;
    } finally {
      try {
        await file?.delete();
      } catch (_) {}
    }
  }

  void dispose() {
    _ticket++;
    _player?.dispose();
  }
}
