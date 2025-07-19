import 'package:flutter/cupertino.dart';
import 'package:omi/backend/http/api/speech_profile.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/providers/base_provider.dart';
import 'package:just_audio/just_audio.dart';

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
    debugPrint("${SharedPreferencesUtil().cachedPeople.length} people");
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

  String _getFileNameFromUrl(String url) {
    Uri uri = Uri.parse(url);
    String fileName = uri.pathSegments.last;
    return fileName.split('.').first;
  }

  void deletePersonSample(int personIdx, String url) {
    String name = _getFileNameFromUrl(url);
    var parts = name.split('_segment_');
    String conversationId = parts[0];
    int segmentIdx = int.parse(parts[1]);
    deleteProfileSample(conversationId, segmentIdx, personId: people[personIdx].id);
    people[personIdx].speechSamples!.remove(url);
    SharedPreferencesUtil().replaceCachedPerson(people[personIdx]);
    notifyListeners();
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
