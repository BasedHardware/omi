import 'package:just_audio/just_audio.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/providers/base_provider.dart';
import 'package:omi/utils/logger.dart';

class PeopleProvider extends BaseProvider {
  PeopleProvider({
    Future<bool> Function(String, String)? renamePerson,
    Future<List<Person>?> Function()? loadPeople,
    Future<bool> Function(String, int)? deleteSample,
  })  : _renamePerson = renamePerson ?? updatePersonName,
        _loadPeople = loadPeople ?? getAllPeople,
        _deleteSample = deleteSample ?? deletePersonSpeechSample;
  final Future<List<Person>?> Function() _loadPeople;
  final Future<bool> Function(String, String) _renamePerson;
  final Future<bool> Function(String, int) _deleteSample;
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

  void clearUserData() {
    people = [];
    samplesUrl = {};
    currentPlayingPersonIndex = null;
    currentPlayingIndex = null;
    isPlaying = false;
    _audioPlayer.stop();
    notifyListeners();
  }

  setPeople() async {
    final value = await _loadPeople();
    loading = false;
    if (value != null) {
      people = value;
      SharedPreferencesUtil().cachedPeople = people;
    }
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

  Future<void> updatePersonProvider(Person person, String name) async {
    if (loading) return;
    loading = true;
    notifyListeners();

    final updated = await _renamePerson(person.id, name);
    final index = people.indexWhere((p) => p.id == person.id);
    if (updated && index != -1) {
      people[index] = Person(
        id: person.id,
        name: name,
        createdAt: person.createdAt,
        updatedAt: DateTime.now(),
        speechSamples: person.speechSamples,
        speechSampleTranscripts: person.speechSampleTranscripts,
        speechSamplesVersion: person.speechSamplesVersion,
        colorIdx: person.colorIdx,
        voiceReadiness: person.voiceReadiness,
      );
      people.sort((a, b) => a.name.compareTo(b.name));
      SharedPreferencesUtil().cachedPeople = people;
    }

    loading = false;
    notifyListeners();
  }

  Future<void> deletePersonSample(int personIdx, int sampleIdx) async {
    String personId = people[personIdx].id;

    bool success = await _deleteSample(personId, sampleIdx);
    if (success) {
      people[personIdx].speechSamples!.removeAt(sampleIdx);
      if (people[personIdx].speechSamples!.isEmpty) {
        people[personIdx] = Person.fromJson({
          ...people[personIdx].toJson(),
          'voice_readiness': 'not_learned',
        });
      }
      SharedPreferencesUtil().replaceCachedPerson(people[personIdx]);
      await setPeople();
      notifyListeners();
    } else {
      Logger.debug('Failed to delete speech sample at index: $sampleIdx');
    }
  }

  Future<void> deletePersonProvider(Person person) async {
    people.remove(person);
    SharedPreferencesUtil().cachedPeople = people;
    notifyListeners();

    if (await deletePerson(person.id)) return;
    if (!people.any((p) => p.id == person.id)) {
      people.add(person);
      people.sort((a, b) => a.name.compareTo(b.name));
      SharedPreferencesUtil().cachedPeople = people;
      notifyListeners();
    }
  }

  @override
  void dispose() {
    _audioPlayer.dispose();
    super.dispose();
  }
}
