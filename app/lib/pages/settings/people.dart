import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/person.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/pages/settings/widgets/voice_profile_settings_section.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/settings/settings_destinations.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/extensions/functions.dart';

class UserPeoplePage extends StatelessWidget {
  const UserPeoplePage({super.key});

  @override
  Widget build(BuildContext context) {
    return const _UserPeoplePage();
  }
}

class _UserPeoplePage extends StatefulWidget {
  const _UserPeoplePage();

  @override
  State<_UserPeoplePage> createState() => _UserPeoplePageState();
}

class _UserPeoplePageState extends State<_UserPeoplePage> {
  @override
  void initState() {
    super.initState();
    () {
      context.read<PeopleProvider>().initialize();
    }.withPostFrameCallback();
  }

  Widget _showPersonDialogForm(BuildContext context, formKey, nameController) {
    return omiUsesCupertinoDialogs(context)
        ? Material(
            color: Colors.transparent,
            child: Theme(
              data: ThemeData(
                textSelectionTheme: TextSelectionThemeData(
                  cursorColor: OmiColors.textPrimary,
                  selectionColor: OmiColors.textDisabled,
                  selectionHandleColor: OmiColors.textPrimary,
                ),
              ),
              child: Form(
                key: formKey,
                child: CupertinoTextFormFieldRow(
                  padding: const EdgeInsets.only(top: 16),
                  controller: nameController,
                  placeholder: context.l10n.name,
                  keyboardType: TextInputType.name,
                  textCapitalization: TextCapitalization.words,
                  placeholderStyle: TextStyle(color: OmiColors.textTertiary),
                  style: TextStyle(color: OmiColors.textPrimary),
                  validator: _nameValidator(context),
                ),
              ),
            ),
          )
        : Form(
            key: formKey,
            child: TextFormField(
              controller: nameController,
              keyboardType: TextInputType.name,
              textCapitalization: TextCapitalization.words,
              decoration: InputDecoration(
                labelText: context.l10n.name,
                labelStyle: TextStyle(color: OmiColors.textPrimary),
                focusColor: OmiColors.textPrimary,
                focusedBorder: UnderlineInputBorder(borderSide: BorderSide(color: OmiColors.border)),
              ),
              validator: _nameValidator(context),
            ),
          );
  }

  String? Function(String?) _nameValidator(BuildContext context) {
    return (String? value) {
      if (value == null || value.isEmpty) {
        return context.l10n.pleaseEnterName;
      }
      if (value.length < 2 || value.length > 40) {
        return context.l10n.nameMustBeBetweenCharacters;
      }
      return null;
    };
  }

  Future<void> _showPersonDialog(BuildContext context, PeopleProvider provider, {Person? person}) async {
    final connectivityProvider = Provider.of<ConnectivityProvider>(context, listen: false);
    if (!connectivityProvider.isConnected) {
      ConnectivityProvider.showNoInternetDialog(context);
      return;
    }

    final nameController = TextEditingController(text: person?.name ?? '');
    final formKey = GlobalKey<FormState>();

    await showDialog(
      context: context,
      builder: (dialogContext) => OmiAlertDialog(
        title: person == null ? context.l10n.addNewPerson : context.l10n.editPerson,
        content: _showPersonDialogForm(dialogContext, formKey, nameController),
        actions: [
          OmiDialogAction(label: context.l10n.cancel, onPressed: () => Navigator.pop(dialogContext)),
          OmiDialogAction(
            label: person == null ? context.l10n.add : context.l10n.save,
            isDefault: true,
            onPressed: () {
              if (formKey.currentState!.validate()) {
                final text = nameController.text;
                final name = text[0].toUpperCase() + text.substring(1);
                if (person == null) {
                  provider.createPersonProvider(name);
                } else {
                  provider.updatePersonProvider(person, name);
                }
                Navigator.pop(dialogContext);
              }
            },
          ),
        ],
      ),
    );
  }

  /// A voice sample cannot be restored once deleted: confirm every time.
  Future<void> _confirmDeleteSample(int peopleIdx, Person person, int sampleIdx, PeopleProvider provider) async {
    final connectivityProvider = Provider.of<ConnectivityProvider>(context, listen: false);
    if (!connectivityProvider.isConnected) {
      ConnectivityProvider.showNoInternetDialog(context);
      return;
    }
    final confirmed = await showOmiConfirm(
      context,
      title: context.l10n.deleteSampleQuestion,
      message: context.l10n.deleteSampleConfirmation(person.name),
      confirmLabel: context.l10n.delete,
      destructive: true,
    );

    if (confirmed) {
      await provider.deletePersonSample(peopleIdx, sampleIdx);
    }
  }

  /// Deleting a person removes their samples too and cannot be undone: confirm every time.
  Future<void> _confirmDeletePerson(Person person, PeopleProvider provider) async {
    final confirmed = await showOmiConfirm(
      context,
      title: context.l10n.deletePersonTitle,
      message: context.l10n.deletePersonConfirmation(person.name),
      confirmLabel: context.l10n.delete,
      destructive: true,
    );

    if (confirmed) provider.deletePersonProvider(person);
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<PeopleProvider>(
      builder: (context, provider, child) {
        final l10n = context.l10n;
        return Scaffold(
          backgroundColor: OmiColors.surface0,
          appBar: OmiAppBar(
            leading: const OmiBackButton(),
            title: Text(l10n.people),
            actions: [
              if (provider.people.isNotEmpty)
                OmiIconButton(
                  icon: const Icon(Icons.help_outline),
                  label: l10n.howItWorks,
                  onPressed: () => showOmiAlert(
                    context,
                    title: l10n.howItWorksTitle,
                    message: l10n.howPeopleWorks,
                    okLabel: l10n.gotIt,
                  ),
                ),
              OmiIconButton(
                icon: const Icon(Icons.add),
                label: l10n.addPerson,
                onPressed: () => _showPersonDialog(context, provider),
              ),
            ],
          ),
          // v2 People: who Omi can recognize — you first, then everyone you named, then how it
          // learns voices.
          body: provider.loading
              ? const OmiLoadingState()
              : ListView(
                  padding: const EdgeInsets.fromLTRB(OmiSpacing.md, 0, OmiSpacing.md, 48),
                  children: [
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xxs),
                      child: Text(l10n.peopleSubtitle, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
                    ),
                    const SizedBox(height: 22),
                    OmiSettingsGroup(
                      children: [
                        OmiSettingsRow(
                          key: const Key('people_you_row'),
                          leading: OmiInitialAvatar(
                            name: SharedPreferencesUtil().givenName.trim().isNotEmpty
                                ? SharedPreferencesUtil().givenName
                                : l10n.you,
                            size: 36,
                          ),
                          title: l10n.you,
                          subtitle: l10n.speechProfile,
                          onTap: () => openVoiceProfile(context),
                        ),
                      ],
                    ),
                    const SizedBox(height: 22),
                    if (provider.people.isEmpty)
                      OmiEmptyState(
                        icon: Icons.people_outline,
                        title: l10n.noPeopleYet,
                        message: l10n.createPersonHint,
                        action: OmiButton(
                          label: l10n.addPerson,
                          icon: Icons.add,
                          size: OmiButtonSize.compact,
                          onPressed: () => _showPersonDialog(context, provider),
                        ),
                      )
                    else
                      OmiSettingsGroup(
                        header: l10n.people,
                        children: [
                          for (final (index, person) in provider.people.indexed)
                            _PersonEntry(
                              key: ValueKey('person_${person.id}'),
                              person: person,
                              onRename: () => _showPersonDialog(context, provider, person: person),
                              onDelete: () => _confirmDeletePerson(person, provider),
                              samples: [
                                for (final (j, sample) in (person.speechSamples ?? const <String>[]).indexed)
                                  _SampleRow(
                                    title: l10n.sampleNumber(j + 1),
                                    transcript: person.speechSampleTranscripts != null &&
                                            j < person.speechSampleTranscripts!.length
                                        ? person.speechSampleTranscripts![j]
                                        : null,
                                    playing: provider.currentPlayingPersonIndex == index &&
                                        provider.currentPlayingIndex == j &&
                                        provider.isPlaying,
                                    // The row plays: a tap never deletes.
                                    onPlayPause: () => provider.playPause(index, j, sample),
                                    onDelete: () => _confirmDeleteSample(index, person, j, provider),
                                  ),
                              ],
                            ),
                        ],
                      ),
                    const SizedBox(height: 22),
                    const VoiceProfileSettingsSection(),
                    Padding(
                      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.sm, OmiSpacing.md, 0),
                      child:
                          Text(l10n.howPeopleWorks, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
                    ),
                  ],
                ),
        );
      },
    );
  }
}

/// One person (v2 People): their initial, name and voice status. A tap shows or hides their voice
/// samples; Rename and Delete are on long-press (and in the accessibility actions).
class _PersonEntry extends StatefulWidget {
  const _PersonEntry({
    super.key,
    required this.person,
    required this.samples,
    required this.onRename,
    required this.onDelete,
  });

  final Person person;
  final List<Widget> samples;
  final VoidCallback onRename;
  final VoidCallback onDelete;

  @override
  State<_PersonEntry> createState() => _PersonEntryState();
}

class _PersonEntryState extends State<_PersonEntry> {
  bool _expanded = false;

  void _showMenu() {
    final l10n = context.l10n;
    showOmiRowMenu(context, title: widget.person.name, actions: [
      OmiMenuAction(icon: Icons.edit_outlined, label: l10n.editPerson, onSelected: widget.onRename),
      OmiMenuAction(
        icon: Icons.delete_outline,
        label: l10n.deletePersonLabel,
        onSelected: widget.onDelete,
        isDestructive: true,
      ),
    ]);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final person = widget.person;
    final hasSamples = widget.samples.isNotEmpty;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Semantics(
          expanded: hasSamples ? _expanded : null,
          customSemanticsActions: {
            CustomSemanticsAction(label: l10n.editPerson): widget.onRename,
            CustomSemanticsAction(label: l10n.deletePersonLabel): widget.onDelete,
          },
          child: GestureDetector(
            onLongPress: _showMenu,
            child: OmiSettingsRow(
              leading: OmiInitialAvatar(name: person.name, size: 36),
              title: person.name,
              subtitle: l10n.voiceRecognitionStatus(person.voiceReadiness),
              showChevron: false,
              trailing: hasSamples
                  ? AnimatedRotation(
                      turns: _expanded ? 0.5 : 0,
                      duration: OmiMotion.of(context).quick,
                      child: Icon(Icons.expand_more_rounded, color: OmiColors.textTertiary),
                    )
                  : null,
              // Without samples there is nothing to show, so a tap renames.
              onTap: hasSamples ? () => setState(() => _expanded = !_expanded) : widget.onRename,
            ),
          ),
        ),
        if (_expanded)
          Padding(
            padding: const EdgeInsets.fromLTRB(40, 0, OmiSpacing.xs, OmiSpacing.xs),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: widget.samples),
          ),
      ],
    );
  }
}

/// One voice sample: tapping the row (or its play button) plays or pauses it; delete is the
/// labelled trailing control, behind a confirmation.
class _SampleRow extends StatelessWidget {
  const _SampleRow({
    required this.title,
    required this.transcript,
    required this.playing,
    required this.onPlayPause,
    required this.onDelete,
  });

  final String title;
  final String? transcript;
  final bool playing;
  final VoidCallback onPlayPause;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final hasTranscript = transcript != null && transcript!.isNotEmpty;
    return InkWell(
      onTap: onPlayPause,
      borderRadius: OmiRadius.mdAll,
      child: Row(
        children: [
          OmiIconButton(
            icon: Icon(playing ? Icons.pause : Icons.play_arrow),
            label: playing ? l10n.pausePlayback : l10n.play,
            onPressed: onPlayPause,
          ),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: OmiSpacing.xs),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: OmiType.callout),
                  if (hasTranscript)
                    Padding(
                      padding: const EdgeInsets.only(top: 2),
                      child: Text(
                        '“$transcript”',
                        style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, fontStyle: FontStyle.italic),
                      ),
                    ),
                ],
              ),
            ),
          ),
          OmiIconButton(
            icon: const Icon(Icons.delete_outline, size: 20),
            label: l10n.deleteSample,
            color: OmiColors.textSecondary,
            onPressed: onDelete,
          ),
        ],
      ),
    );
  }
}
