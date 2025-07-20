import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/pages/settings/people.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/widgets/person_chip.dart';
import 'package:provider/provider.dart';

class NameSpeakerBottomSheet extends StatefulWidget {
  final int speakerId;
  final String segmentId;
  final Function(int speakerId, String personId, String personName, List<String> segmentIds) onSpeakerAssigned;
  final List<TranscriptSegment> segments;
  final SpeakerLabelSuggestionEvent? suggestion;

  const NameSpeakerBottomSheet({
    super.key,
    required this.speakerId,
    required this.segmentId,
    required this.onSpeakerAssigned,
    required this.segments,
    this.suggestion,
  });

  @override
  State<NameSpeakerBottomSheet> createState() => _NameSpeakerBottomSheetState();
}

class _NameSpeakerBottomSheetState extends State<NameSpeakerBottomSheet> {
  final TextEditingController _controller = TextEditingController();
  String selectedPerson = '';
  String selectedPersonName = '';
  List<String> _selectedSegmentIds = [];
  bool _isSegmentsExpanded = false;
  bool allowSave = false;
  bool loading = false;
  String? speakerTextSample;
  bool _isCreatingNewPerson = false;
  String? _duplicateNameError;

  void setLoading(bool value) {
    if (loading == value) return;
    setState(() {
      loading = value;
    });
  }

  void setAllowSave(bool value) {
    if (allowSave == value) return;
    setState(() {
      allowSave = value;
    });
  }

  void setSelectedPerson(String personId) {
    if (selectedPerson == personId) return;
    setState(() {
      selectedPerson = personId;
      _controller.clear();
      allowSave = true;
    });
  }

  void setSelectedPersonName(String name) {
    if (selectedPersonName == name) return;
    setState(() {
      selectedPersonName = name;
    });
  }

  @override
  void initState() {
    super.initState();
    _selectedSegmentIds.add(widget.segmentId);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final peopleProvider = context.read<PeopleProvider>();
      final people = peopleProvider.people;
      final userName = SharedPreferencesUtil().givenName;

      final currentSegment = widget.segments.firstWhereOrNull((s) => s.id == widget.segmentId);
      final sample = currentSegment?.text ?? "";
      setState(() {
        speakerTextSample = sample.isNotEmpty ? '"$sample"' : null;
      });

      // New person suggestion
      final suggestion = widget.suggestion;
      if (suggestion != null && suggestion.personName.isNotEmpty && suggestion.personId.isEmpty) {
        setState(() {
          _isCreatingNewPerson = true;
          _controller.text = suggestion.personName;
          setAllowSave(true);
        });
      }

      // Predict selected person
      if ((currentSegment != null && currentSegment.isUser) || people.isEmpty) {
        setSelectedPerson('user');
        setSelectedPersonName(userName);
      } else if (people.isNotEmpty) {
        final personFrequencies = <String, int>{};
        for (final segment in widget.segments) {
          if (segment.personId != null) {
            personFrequencies.update(segment.personId!, (count) => count + 1, ifAbsent: () => 1);
          }
        }
        final peopleList = List.from(people);
        final currentPersonId = currentSegment?.personId;
        peopleList.sort((a, b) {
          final suggestionId = widget.suggestion?.personId;

          final aIsCurrent = a.id == currentPersonId;
          final bIsCurrent = b.id == currentPersonId;
          if (aIsCurrent != bIsCurrent) return aIsCurrent ? -1 : 1;

          final aIsSuggestion = a.id == suggestionId;
          final bIsSuggestion = b.id == suggestionId;
          if (aIsSuggestion != bIsSuggestion) return aIsSuggestion ? -1 : 1;

          final freqA = personFrequencies[a.id] ?? 0;
          final freqB = personFrequencies[b.id] ?? 0;
          if (freqA != freqB) {
            return freqB.compareTo(freqA);
          }
          return a.name.compareTo(b.name);
        });
        setSelectedPerson(peopleList[0].id);
        setSelectedPersonName(peopleList[0].name);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final peopleProvider = context.watch<PeopleProvider>();
    final people = peopleProvider.people;
    final userName = SharedPreferencesUtil().givenName;

    return Padding(
      padding: MediaQuery.of(context).viewInsets,
      child: SingleChildScrollView(
        child: Padding(
          padding: const EdgeInsets.all(16.0),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              loading
                  ? const Padding(
                      padding: EdgeInsets.symmetric(vertical: 40),
                      child: Center(
                        child: CircularProgressIndicator(
                          valueColor: AlwaysStoppedAnimation(Colors.white),
                        ),
                      ),
                    )
                  : Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        _buildHeader(),
                        const SizedBox(height: 16),
                        if (_isCreatingNewPerson)
                          _buildNewPersonInput(people, userName)
                        else
                          _buildPersonSelector(people, userName),
                        const SizedBox(height: 16),
                        _buildUntaggedSegments(),
                        const SizedBox(height: 8),
                        _buildSaveButton(),
                        const SizedBox(height: 28),
                      ],
                    ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildHeader() {
    return Column(
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            Expanded(
              child: Text(
                'Tag Speaker ${widget.speakerId}',
                style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
              ),
            ),
            IconButton(
              icon: const Icon(Icons.close, color: Colors.grey),
              onPressed: () => Navigator.of(context).pop(),
            ),
          ],
        ),
        if (speakerTextSample != null && speakerTextSample!.isNotEmpty) ...[
          const SizedBox(height: 8),
          Text(
            speakerTextSample!,
            style: TextStyle(color: Colors.grey.shade400, fontStyle: FontStyle.italic),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ],
    );
  }

  Widget _buildNewPersonInput(List<Person> people, String userName) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        TextField(
          controller: _controller,
          autofocus: true,
          onChanged: (value) {
            final trimmedValue = value.trim();
            final isDuplicate = people.any((p) => p.name.toLowerCase() == trimmedValue.toLowerCase());
            final isOwnName = trimmedValue.toLowerCase() == userName.toLowerCase();

            setState(() {
              selectedPerson = ''; // When typing, deselect any chosen person.
              if (isDuplicate) {
                _duplicateNameError = 'A person with this name already exists.';
                setAllowSave(false);
              } else if (trimmedValue.isEmpty) {
                _duplicateNameError = null;
                setAllowSave(false);
              } else if (isOwnName) {
                _duplicateNameError = 'To tag yourself, please select "You" from the list.';
                setAllowSave(false);
              } else {
                _duplicateNameError = null;
                setAllowSave(true);
              }
            });
          },
          decoration: InputDecoration(
            hintText: 'Enter Person\'s Name',
            filled: true,
            contentPadding: const EdgeInsets.symmetric(horizontal: 16),
            fillColor: Colors.grey[900],
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(8),
              borderSide: BorderSide.none,
            ),
            hintStyle: const TextStyle(color: Colors.grey),
            errorText: _duplicateNameError,
          ),
        ),
        const SizedBox(height: 8),
        TextButton(
          onPressed: () {
            setState(() {
              _isCreatingNewPerson = false;
              _controller.clear();
              setAllowSave(selectedPerson.isNotEmpty);
            });
          },
          child: const Text('Cancel', style: TextStyle(color: Colors.white)),
        )
      ],
    );
  }

  Widget _buildPersonSelector(List<Person> ppl, String userName) {
    final personFrequencies = <String, int>{};
    for (final segment in widget.segments) {
      if (segment.personId != null) {
        personFrequencies.update(segment.personId!, (count) => count + 1, ifAbsent: () => 1);
      }
    }

    final currentSegment = widget.segments.firstWhereOrNull((s) => s.id == widget.segmentId);
    final currentPersonId = currentSegment?.personId;

    final List<Person> cachedPeople = List.from(ppl);
    cachedPeople.sort((a, b) {
      final suggestionId = widget.suggestion?.personId;

      final aIsCurrent = a.id == currentPersonId;
      final bIsCurrent = b.id == currentPersonId;
      if (aIsCurrent != bIsCurrent) return aIsCurrent ? -1 : 1;

      final aIsSuggestion = a.id == suggestionId;
      final bIsSuggestion = b.id == suggestionId;
      if (aIsSuggestion != bIsSuggestion) return aIsSuggestion ? -1 : 1;

      final freqA = personFrequencies[a.id] ?? 0;
      final freqB = personFrequencies[b.id] ?? 0;
      if (freqA != freqB) {
        return freqB.compareTo(freqA);
      }
      return a.name.compareTo(b.name);
    });

    final List<Person> people = [
      Person(id: 'user', name: '$userName (You)', colorIdx: 0, createdAt: DateTime.now(), updatedAt: DateTime.now())
    ];
    people.addAll(cachedPeople);

    final List<Widget> chips = [
      PersonChip(
        personName: 'Add Person',
        isSelected: _isCreatingNewPerson,
        isAddButton: true,
        onSelected: (_) {
          setState(() {
            _isCreatingNewPerson = true;
            selectedPerson = '';
            setAllowSave(false);
          });
        },
      )
    ];
    chips.addAll(people.map((person) => PersonChip(
          personName: person.name,
          isSelected: selectedPerson == person.id,
          onSelected: (bool selected) {
            setSelectedPerson(person.id);
            setSelectedPersonName(person.id == 'user' ? userName : person.name);
          },
        )));

    return Wrap(
      spacing: 8.0,
      runSpacing: 8.0,
      children: chips,
    );
  }

  Widget _buildUntaggedSegments() {
    final untaggedSegments = widget.segments
        .where((s) => s.speakerId == widget.speakerId && s.personId == null && !s.isUser && s.id != widget.segmentId)
        .toList();
    final selectedUntaggedSegmentsCount = untaggedSegments.where((s) => _selectedSegmentIds.contains(s.id)).length;

    return Column(
      children: [
        CheckboxListTile(
          title: Text(
            _isSegmentsExpanded
                ? 'Tag other segments from this speaker ($selectedUntaggedSegmentsCount/${untaggedSegments.length})'
                : 'Tag other segments',
            style: TextStyle(fontSize: 14, color: untaggedSegments.isNotEmpty ? Colors.white : Colors.grey),
          ),
          value: _isSegmentsExpanded,
          onChanged: untaggedSegments.isNotEmpty
              ? (value) {
                  setState(() {
                    _isSegmentsExpanded = value ?? false;
                    if (_isSegmentsExpanded) {
                      _selectedSegmentIds = {..._selectedSegmentIds, ...untaggedSegments.map((s) => s.id)}.toList();
                    } else {
                      final untaggedIds = untaggedSegments.map((s) => s.id).toSet();
                      _selectedSegmentIds.removeWhere((id) => untaggedIds.contains(id));
                    }
                  });
                }
              : null,
          controlAffinity: ListTileControlAffinity.leading,
          dense: true,
          activeColor: Theme.of(context).colorScheme.secondary,
          checkColor: Colors.white,
          contentPadding: EdgeInsets.zero,
          secondary: InkWell(
            onTap: () {
              Navigator.of(context).push(MaterialPageRoute(builder: (context) => const UserPeoplePage()));
            },
            child: Padding(
              padding: const EdgeInsets.only(right: 8.0),
              child: Text(
                'Manage People',
                style: TextStyle(
                  color: Colors.white70,
                  fontSize: 14,
                  decoration: TextDecoration.underline,
                  decorationColor: Colors.white70,
                ),
              ),
            ),
          ),
        ),
        if (_isSegmentsExpanded && untaggedSegments.isNotEmpty)
          Container(
            constraints: const BoxConstraints(maxHeight: 150),
            child: ListView.builder(
              shrinkWrap: true,
              itemCount: untaggedSegments.length,
              itemBuilder: (context, index) {
                final segment = untaggedSegments[index];
                return CheckboxListTile(
                  title: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        segment.text,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontSize: 12, color: Colors.white),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        segment.getTimestampString(),
                        style: TextStyle(fontSize: 10, color: Colors.grey.shade400),
                      ),
                    ],
                  ),
                  value: _selectedSegmentIds.contains(segment.id),
                  onChanged: (bool? value) {
                    setState(() {
                      if (value == true) {
                        _selectedSegmentIds.add(segment.id);
                      } else {
                        _selectedSegmentIds.remove(segment.id);
                      }
                    });
                  },
                  controlAffinity: ListTileControlAffinity.leading,
                  dense: true,
                  activeColor: Theme.of(context).colorScheme.secondary,
                  checkColor: Colors.white,
                );
              },
            ),
          ),
      ],
    );
  }

  Widget _buildSaveButton() {
    return SizedBox(
      width: double.infinity,
      child: ElevatedButton(
        style: ElevatedButton.styleFrom(
          backgroundColor: Colors.white,
          foregroundColor: Colors.black,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(8),
          ),
        ),
        onPressed: !allowSave || loading
            ? null
            : () async {
                setLoading(true);
                String personIdToAssign = selectedPerson;
                String personNameToAssign = selectedPersonName;

                if (_controller.text.isNotEmpty && selectedPerson.isEmpty) {
                  personNameToAssign =
                      _controller.text.toString()[0].toUpperCase() + _controller.text.toString().substring(1);
                  personIdToAssign = ''; // Indicates a new person
                }

                await widget.onSpeakerAssigned(
                    widget.speakerId, personIdToAssign, personNameToAssign, _selectedSegmentIds);

                setLoading(false);
                if (mounted) {
                  Navigator.pop(context);
                }
              },
        child: const Center(
          child: Text('Save'),
        ),
      ),
    );
  }
}
