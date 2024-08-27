import 'dart:io';

import 'package:collection/collection.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/api/speech_profile.dart';
import 'package:friend_private/backend/http/api/users.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/person.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:just_audio/just_audio.dart';
import 'package:uuid/uuid.dart';

class UserPeoplePage extends StatefulWidget {
  const UserPeoplePage({super.key});

  @override
  State<UserPeoplePage> createState() => _UserPeoplePageState();
}

class _UserPeoplePageState extends State<UserPeoplePage> {
  List<Person> people = SharedPreferencesUtil().cachedPeople;
  Map<String, List<String>> samplesUrl = {};
  bool loading = true;
  final AudioPlayer _audioPlayer = AudioPlayer();
  int? _currentPlayingPersonIndex;
  int? _currentPlayingIndex;
  bool _isPlaying = false;

  @override
  void dispose() {
    _audioPlayer.dispose();
    super.dispose();
  }

  @override
  void initState() {
    super.initState();
    getAllPeople().then((value) {
      setState(() {
        people = value;
        SharedPreferencesUtil().cachedPeople = people;
      });
    });
    _setupAudioPlayerListeners();
  }

  void _setupAudioPlayerListeners() {
    _audioPlayer.playerStateStream.listen((playerState) {
      if (playerState.processingState == ProcessingState.completed) {
        setState(() {
          _currentPlayingPersonIndex = null;
          _currentPlayingIndex = null;
          _isPlaying = false;
        });
      }
    });
  }

  Future<void> _playPause(int personIdx, int sampleIdx, String fileUrl) async {
    if (_currentPlayingPersonIndex == personIdx && _currentPlayingIndex == sampleIdx) {
      if (_isPlaying) {
        _audioPlayer.pause();
        _isPlaying = false;
      } else {
        _audioPlayer.play();
        _isPlaying = true;
      }
    } else {
      _audioPlayer.stop();
      await _audioPlayer.setUrl(fileUrl);
      setState(() {
        _currentPlayingPersonIndex = personIdx;
        _currentPlayingIndex = sampleIdx;
        _isPlaying = true;
      });
      await _audioPlayer.play();
    }
    setState(() {});
  }

  Widget _showPersonDialogForm(formKey, nameController) {
    return Platform.isIOS
        ? Material(
            color: Colors.transparent,
            child: Theme(
              data: ThemeData(
                textSelectionTheme: const TextSelectionThemeData(
                  cursorColor: Colors.white,
                  selectionColor: Colors.white24,
                  selectionHandleColor: Colors.white,
                ),
              ),
              child: Form(
                key: formKey,
                child: CupertinoTextFormFieldRow(
                  padding: const EdgeInsets.only(top: 16),
                  controller: nameController,
                  placeholder: 'Name',
                  keyboardType: TextInputType.name,
                  textCapitalization: TextCapitalization.words,
                  placeholderStyle: const TextStyle(color: Colors.white60),
                  style: const TextStyle(color: Colors.white),
                  validator: _nameValidator,
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
                labelText: 'Name',
                labelStyle: const TextStyle(color: Colors.white),
                focusColor: Colors.white,
                focusedBorder: UnderlineInputBorder(borderSide: BorderSide(color: Colors.grey.shade300)),
              ),
              validator: _nameValidator,
            ),
          );
  }

  String? _nameValidator(String? value) {
    if (value == null || value.isEmpty) {
      return 'Please enter a name';
    }
    if (value.length < 2 || value.length > 40) {
      return 'Name must be between 2 and 40 characters';
    }
    return null;
  }

  List<Widget> _showPersonDialogActions(BuildContext context, formKey, nameController, {Person? person}) {
    onPressed() async {
      if (formKey.currentState!.validate()) {
        String name = nameController.text.toString()[0].toUpperCase() + nameController.text.toString().substring(1);

        if (person == null) {
          String newPersonTemporalId = const Uuid().v4();
          createPerson(nameController.text).then((p) {
            if (p != null) {
              final index = people.indexWhere((p) => p.id == newPersonTemporalId);
              if (index != -1) {
                people[index] = p;
                SharedPreferencesUtil().replaceCachedPerson(p);
                setState(() {});
              }
            }
          });
          Person newPerson = Person(
              id: newPersonTemporalId,
              name: name,
              createdAt: DateTime.now(),
              updatedAt: DateTime.now(),
              speechSamples: []);
          setState(() {
            people.add(newPerson);
            people.sort((a, b) => a.name.compareTo(b.name));
            SharedPreferencesUtil().cachedPeople = people;
          });
        } else {
          updatePersonName(person.id, name);
          setState(() {
            final index = people.indexWhere((p) => p.id == person.id);
            if (index != -1) {
              people[index] = Person(
                id: person.id,
                name: name,
                createdAt: person.createdAt,
                updatedAt: DateTime.now(),
                speechSamples: person.speechSamples,
              );
              people.sort((a, b) => a.name.compareTo(b.name));
              SharedPreferencesUtil().cachedPeople = people;
            }
          });
        }
        Navigator.pop(context);
      }
    }

    return Platform.isIOS
        ? [
            CupertinoDialogAction(
              onPressed: () => Navigator.pop(context),
              child: const Text('Cancel', style: TextStyle(color: Colors.white)),
            ),
            CupertinoDialogAction(
              onPressed: onPressed,
              child: Text(person == null ? 'Add' : 'Update', style: const TextStyle(color: Colors.white)),
            ),
          ]
        : [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Cancel'),
            ),
            TextButton(
              onPressed: onPressed,
              child: Text(person == null ? 'Add' : 'Update', style: const TextStyle(color: Colors.white)),
            ),
          ];
  }

  Future<void> _showPersonDialog(BuildContext context, {Person? person}) async {
    final nameController = TextEditingController(text: person?.name ?? '');
    final formKey = GlobalKey<FormState>();

    await showDialog(
      context: context,
      builder: (BuildContext context) => Platform.isIOS
          ? CupertinoAlertDialog(
              title: Text(person == null ? 'Add New Person' : 'Edit Person'),
              content: _showPersonDialogForm(formKey, nameController),
              actions: _showPersonDialogActions(context, formKey, nameController, person: person),
            )
          : AlertDialog(
              title: Text(person == null ? 'Add New Person' : 'Edit Person'),
              content: _showPersonDialogForm(formKey, nameController),
              actions: _showPersonDialogActions(context, formKey, nameController, person: person),
            ),
    );
  }

  String _getFileNameFromUrl(String url) {
    Uri uri = Uri.parse(url);
    String fileName = uri.pathSegments.last;
    return fileName.split('.').first;
  }

  Future<void> _confirmDeleteSample(int peopleIdx, String url) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (c) => getDialog(
        context,
        () => Navigator.pop(context, false),
        () => Navigator.pop(context, true),
        'Delete Sample?',
        'Are you sure you want to delete ${people[peopleIdx].name}\'s sample?',
        okButtonText: 'Confirm',
      ),
    );

    if (confirmed == true) {
      String name = _getFileNameFromUrl(url);
      var parts = name.split('_segment_');
      String memoryId = parts[0];
      int segmentIdx = int.parse(parts[1]);
      deleteProfileSample(memoryId, segmentIdx, personId: people[peopleIdx].id);
      setState(() {
        people[peopleIdx].speechSamples!.remove(url);
        SharedPreferencesUtil().replaceCachedPerson(people[peopleIdx]);
      });
    }
  }

  Future<void> _confirmDeletePerson(Person person) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (c) => getDialog(
        context,
        () => Navigator.pop(context, false),
        () => Navigator.pop(context, true),
        'Confirm Deletion',
        'Are you sure you want to delete ${person.name}? This will also remove all associated speech samples.',
        okButtonText: 'Confirm',
      ),
    );

    if (confirmed == true) {
      deletePerson(person.id);
      people.remove(person);
      SharedPreferencesUtil().cachedPeople = people;
      setState(() {});
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        title: const Text('People'),
        backgroundColor: Theme.of(context).colorScheme.primary,
        centerTitle: true,
        actions: [
          IconButton(
            icon: const Icon(Icons.add),
            onPressed: () => _showPersonDialog(context),
          ),
          people.isNotEmpty
              ? IconButton(
                  icon: const Icon(Icons.question_mark),
                  onPressed: () {
                    showDialog(
                      context: context,
                      builder: (c) => getDialog(
                        context,
                        () => Navigator.pop(context, false),
                        () => Navigator.pop(context, true),
                        'How it works?',
                        'Once a person is created, you can go to a memory transcript, and assign them their corresponding segments, that way Omi will be able to recognize their speech too!',
                        okButtonText: 'Got it',
                      ),
                    );
                  })
              : const SizedBox(),
        ],
      ),
      body: people.isEmpty
          ? const Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  Icon(Icons.question_mark, size: 40),
                  SizedBox(height: 24),
                  Padding(
                    padding: EdgeInsets.symmetric(horizontal: 32),
                    child: Text('Create a new person and train Omi to recognize their speech too!',
                        style: TextStyle(color: Colors.white, fontSize: 24), textAlign: TextAlign.center),
                  ),
                  SizedBox(height: 64),
                ],
              ),
            )
          : ListView.separated(
              itemCount: people.length,
              separatorBuilder: (context, index) => const Divider(height: 1),
              itemBuilder: (context, index) {
                final person = people[index];
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    ListTile(
                      title: Text(person.name),
                      onTap: () => _showPersonDialog(context, person: person),
                      trailing: IconButton(
                        icon: const Icon(Icons.delete, size: 20),
                        onPressed: () => _confirmDeletePerson(person),
                      ),
                    ),
                    if (person.speechSamples != null && person.speechSamples!.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(left: 8, right: 16, bottom: 8),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const SizedBox(height: 4),
                            ...person.speechSamples!.mapIndexed((j, sample) => ListTile(
                                  contentPadding: EdgeInsets.zero,
                                  leading: IconButton(
                                    padding: const EdgeInsets.all(0),
                                    icon: Icon(
                                      _currentPlayingPersonIndex == index && _currentPlayingIndex == j && _isPlaying
                                          ? Icons.pause
                                          : Icons.play_arrow,
                                    ),
                                    onPressed: () => _playPause(index, j, sample),
                                  ),
                                  title: Text(index == 0 ? 'Speech Profile' : 'Sample $index'),
                                  onTap: () => _confirmDeleteSample(index, sample),
                                  subtitle: FutureBuilder<Duration?>(
                                    future: AudioPlayer().setUrl(sample),
                                    builder: (context, snapshot) {
                                      if (snapshot.hasData) {
                                        return Text('${snapshot.data!.inSeconds} seconds');
                                      } else {
                                        return const Text('Loading duration...');
                                      }
                                    },
                                  ),
                                )),
                          ],
                        ),
                      ),
                  ],
                );
              },
            ),
    );
  }
}
