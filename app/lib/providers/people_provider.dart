import 'package:flutter/cupertino.dart';

import 'package:just_audio/just_audio.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/providers/base_provider.dart';
import 'package:omi/utils/logger.dart';

class PeopleProvider extends BaseProvider {
  List<Person> people = SharedPreferencesUtil().cachedPeople;
  Map<String, List<String>> samplesUrl = {};

  final AudioPlayer _audioPlayer = AudioPlayer();
  int? currentPlayingPersonIndex;
  int? currentPlayingIndex;
  bool isPlaying = false;

  void initialize() {
    loading = true;
    notifyListeners();
    setPeople();
    _setupAudioPlayerListeners();
  }

  setPeople() async {
    final value = await getAllPeople();
    loading = false;
    people = value;
    SharedPreferencesUtil().cachedPeople = people;
    Logger.debug("${SharedPreferencesUtil().cachedPeople.length} people");
    notifyListeners();
  }

  void _setupAudioPlayerListeners() {
    _audioPlayer.playerStateStream.listen((playerState) {
      if (playerState.processingState == ProcessingState.completed) {
        currentPlayingPersonIndex = null;
        currentPlayingIndex = null;
        isPlaying = false;
      }
    });
  }

  Future<void> playPause(int personIdx, int sampleIdx, String fileUrl) async {
    if (currentPlayingPersonIndex == personIdx && currentPlayingIndex == sampleIdx) {
      if (isPlaying) {
        _audioPlayer.pause();
        isPlaying = false;
      } else {
        _audioPlayer.play();
        isPlaying = true;
      }
      notifyListeners();
    } else {
      _audioPlayer.stop();
      await _audioPlayer.setUrl(fileUrl);
      currentPlayingPersonIndex = personIdx;
      currentPlayingIndex = sampleIdx;
      isPlaying = true; // setState?
      notifyListeners();
      await _audioPlayer.play();
    }
  }

  Future<Person?> createPersonProvider(String name) async {
    if (loading) return null;
    loading = true;
    notifyListeners();

    Person? newPerson = await createPerson(name);
    if (newPerson == null) {
      loading = false;
      notifyListeners();
      return null;
    }

    people.add(newPerson);
    people.sort((a, b) => a.name.compareTo(b.name));
    SharedPreferencesUtil().cachedPeople = people;

    loading = false;
    notifyListeners();
    return newPerson;
  }

  void updatePersonProvider(Person person, String name) async {
    if (loading) return;
    loading = true;
    notifyListeners();

    await updatePersonName(person.id, name);
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

    loading = false;
    notifyListeners();
  }

  Future<void> deletePersonSample(int personIdx, int sampleIdx) async {
    String personId = people[personIdx].id;

    bool success = await deletePersonSpeechSample(personId, sampleIdx);
    if (success) {
      people[personIdx].speechSamples!.removeAt(sampleIdx);
      SharedPreferencesUtil().replaceCachedPerson(people[personIdx]);
      notifyListeners();
    } else {
      Logger.debug('Failed to delete speech sample at index: $sampleIdx');
    }
  }

  void deletePersonProvider(Person person) {
    deletePerson(person.id);
    people.remove(person);
    SharedPreferencesUtil().cachedPeople = people;
    notifyListeners();
  }

  @override
  void dispose() {
    _audioPlayer.dispose();
    super.dispose();
  }
}
