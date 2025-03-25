import 'package:flutter/material.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:provider/provider.dart';

import '../conversation_detail_provider.dart';

class NameSpeakerBottomSheet extends StatefulWidget {
  final int speakerId;
  final int segmentIdx;
  const NameSpeakerBottomSheet({super.key, required this.speakerId, required this.segmentIdx});

  @override
  State<NameSpeakerBottomSheet> createState() => _NameSpeakerBottomSheetState();
}

class _NameSpeakerBottomSheetState extends State<NameSpeakerBottomSheet> {
  final TextEditingController _controller = TextEditingController();
  String selectedPerson = '';
  String selectedPersonName = '';
  bool allSegments = false;
  bool allowSave = false;
  bool loading = false;

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

  void toggleAllSegments(bool value) {
    if (allSegments == value) return;
    setState(() {
      allSegments = value;
    });
  }

  void setSelectedPerson(String personId) {
    if (selectedPerson == personId) return;
    setState(() {
      selectedPerson = personId;
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
  Widget build(BuildContext context) {
    return Padding(
      padding: MediaQuery.of(context).viewInsets,
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
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text(
                            'Who is Speaker ${widget.speakerId}?',
                            style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                          ),
                          IconButton(
                            icon: const Icon(Icons.close, color: Colors.grey),
                            onPressed: () => Navigator.of(context).pop(),
                          ),
                        ],
                      ),
                      const SizedBox(height: 8),
                      TextField(
                        controller: _controller,
                        onChanged: (value) {
                          if ((value.isEmpty || value == SharedPreferencesUtil().givenName) && selectedPerson.isEmpty) {
                            setAllowSave(false);
                          } else {
                            setAllowSave(true);
                          }
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
                        ),
                      ),
                      const SizedBox(height: 16),
                      const Text(
                        'Recently Used Names',
                        style: TextStyle(color: Colors.grey, fontSize: 14),
                      ),
                      const SizedBox(height: 4),
                      SharedPreferencesUtil().cachedPeople.isEmpty
                          ? Text(
                              'No recently used names were found for now.',
                              style: TextStyle(color: Colors.grey[600]),
                            )
                          : SingleChildScrollView(
                              scrollDirection: Axis.horizontal,
                              child: Row(
                                  children: [
                                        Padding(
                                          padding: const EdgeInsets.only(right: 10),
                                          child: ChoiceChip(
                                            label: Text('${SharedPreferencesUtil().givenName} (You)'),
                                            selected: selectedPerson == 'user',
                                            showCheckmark: true,
                                            backgroundColor: Colors.transparent,
                                            shape: RoundedRectangleBorder(
                                              borderRadius: BorderRadius.circular(8),
                                            ),
                                            onSelected: (bool selected) {
                                              setSelectedPerson('user');
                                              setSelectedPersonName(SharedPreferencesUtil().givenName);
                                            },
                                          ),
                                        )
                                      ] +
                                      SharedPreferencesUtil().cachedPeople.map((e) {
                                        return Padding(
                                          padding: const EdgeInsets.only(right: 10),
                                          child: ChoiceChip(
                                            label: Text(e.name),
                                            selected: selectedPerson == e.id,
                                            showCheckmark: true,
                                            backgroundColor: Colors.transparent,
                                            shape: RoundedRectangleBorder(
                                              borderRadius: BorderRadius.circular(8),
                                            ),
                                            onSelected: (bool selected) {
                                              setSelectedPerson(e.id);
                                              setSelectedPersonName(e.name);
                                            },
                                          ),
                                        );
                                      }).toList()),
                            ),
                      const SizedBox(height: 16),
                      RadioListTile(
                        contentPadding: EdgeInsets.zero,
                        value: 1,
                        groupValue: allSegments ? 2 : 1,
                        onChanged: (_) {
                          toggleAllSegments(false);
                        },
                        title: const Text('Apply to Current Segment Only'),
                        activeColor: Colors.white,
                      ),
                      RadioListTile(
                        contentPadding: EdgeInsets.zero,
                        value: 2,
                        groupValue: allSegments ? 2 : 1,
                        onChanged: (_) {
                          toggleAllSegments(true);
                        },
                        title: const Text(
                          'Apply to All Segments of This Speaker',
                        ),
                        activeColor: Colors.white,
                      ),
                    ],
                  ),
            const SizedBox(height: 16),
            ElevatedButton(
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
                      var provider = Provider.of<ConversationDetailProvider>(context, listen: false);
                      if (loading) return;
                      provider.toggleEditSegmentLoading(true);
                      setLoading(true);
                      if (_controller.text.isNotEmpty && selectedPerson.isEmpty) {
                        String name =
                            _controller.text.toString()[0].toUpperCase() + _controller.text.toString().substring(1);

                        Person? person = await createPerson(name);
                        if (person == null) {
                          Navigator.pop(context);
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(
                              content: Text('Failed to create person. Please try again later.'),
                            ),
                          );
                        } else {
                          List<Person> people = SharedPreferencesUtil().cachedPeople;
                          people.add(person);
                          people.sort((a, b) => a.name.compareTo(b.name));
                          SharedPreferencesUtil().cachedPeople = people;
                          setSelectedPerson(person.id);
                          setSelectedPersonName(person.name);
                        }
                      }
                      if (allSegments) {
                        MixpanelManager().assignedSegment(selectedPerson == 'user' ? 'User' : 'User Person');
                        for (var element in provider.conversation.transcriptSegments) {
                          if (element.speakerId == widget.speakerId) {
                            element.isUser = selectedPerson == 'user';
                            element.personId = selectedPerson == 'user' ? null : selectedPerson;
                          }
                        }
                        await assignConversationSpeaker(
                          provider.conversation.id,
                          widget.speakerId,
                          selectedPerson == 'user',
                          personId: selectedPerson == 'user' ? null : selectedPerson,
                          useForSpeechTraining: selectedPerson == 'user' && SharedPreferencesUtil().hasSpeakerProfile,
                        );

                        try {
                          provider.toggleEditSegmentLoading(false);
                          Navigator.pop(context);
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              content: Text(
                                  'Segments assigned to ${selectedPerson == 'user' ? 'you' : selectedPersonName} successfully'),
                            ),
                          );
                        } catch (e) {}
                      } else {
                        MixpanelManager().assignedSegment(selectedPerson == 'user' ? 'User' : 'User Person');
                        provider.conversation.transcriptSegments[widget.segmentIdx].isUser = selectedPerson == 'user';
                        provider.conversation.transcriptSegments[widget.segmentIdx].personId =
                            selectedPerson == 'user' ? null : selectedPerson;
                        await assignConversationTranscriptSegment(provider.conversation.id, widget.segmentIdx,
                            personId: selectedPerson == 'user' ? null : selectedPerson);

                        try {
                          provider.toggleEditSegmentLoading(false);
                          Navigator.pop(context);
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              content: Text(
                                  'Segment assigned to ${selectedPerson == 'user' ? 'you' : selectedPersonName} successfully'),
                            ),
                          );
                        } catch (e) {}
                      }
                    },
              child: const Center(
                child: Text('Save'),
              ),
            ),
            const SizedBox(height: 28),
          ],
        ),
      ),
    );
  }
}
