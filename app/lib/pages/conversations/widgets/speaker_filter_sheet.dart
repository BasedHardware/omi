import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/person.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';

typedef SpeakerSelected = Future<void> Function(String? speakerId);

Future<void> showSpeakerFilterSheet(BuildContext context) async {
  final conversationProvider = context.read<ConversationProvider>();
  final people = context.read<PeopleProvider>().people;

  await showModalBottomSheet<void>(
    context: context,
    backgroundColor: const Color(0xFF1F1F25),
    showDragHandle: true,
    builder: (sheetContext) {
      return SpeakerFilterSheet(
        people: people,
        selectedSpeakerId: conversationProvider.selectedSpeakerId,
        title: context.l10n.phoneSpeaker,
        allLabel: context.l10n.all,
        userLabel: context.l10n.speakerLabelYou,
        onSelected: (speakerId) async {
          Navigator.of(sheetContext).pop();
          await conversationProvider.setSpeakerFilter(speakerId);
        },
      );
    },
  );
}

class SpeakerFilterSheet extends StatelessWidget {
  const SpeakerFilterSheet({
    super.key,
    required this.people,
    required this.selectedSpeakerId,
    required this.title,
    required this.allLabel,
    required this.userLabel,
    required this.onSelected,
  });

  final List<Person> people;
  final String? selectedSpeakerId;
  final String title;
  final String allLabel;
  final String userLabel;
  final SpeakerSelected onSelected;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: ConstrainedBox(
        constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.7),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 4, 20, 12),
              child: Text(title, style: Theme.of(context).textTheme.titleMedium),
            ),
            Flexible(
              child: ListView(
                shrinkWrap: true,
                children: [
                  _speakerTile(
                    key: const Key('speaker_filter_all'),
                    name: allLabel,
                    speakerId: null,
                    icon: Icons.people_outline,
                  ),
                  _speakerTile(
                    key: const Key('speaker_filter_user'),
                    name: userLabel,
                    speakerId: 'user',
                    icon: Icons.person_outline,
                  ),
                  for (final person in people)
                    _speakerTile(
                      key: Key('speaker_filter_${person.id}'),
                      name: person.name,
                      speakerId: person.id,
                      icon: Icons.person_outline,
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _speakerTile({required Key key, required String name, required String? speakerId, required IconData icon}) {
    final selected = speakerId == selectedSpeakerId;
    return ListTile(
      key: key,
      leading: Icon(icon),
      title: Text(name),
      trailing: selected ? const Icon(Icons.check, color: Colors.deepPurpleAccent) : null,
      onTap: () async {
        await onSelected(speakerId);
      },
    );
  }
}
