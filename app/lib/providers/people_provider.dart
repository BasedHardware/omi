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
    Future<bool> Function(String)? deletePersonById,
    Future<bool> Function(String, bool)? setPinned,
  })  : _deletePersonById = deletePersonById ?? deletePerson,
        _setPinned = setPinned ?? setPersonPinned,
        _renamePerson = renamePerson ?? updatePersonName,
        _loadPeople = loadPeople ?? (() => getAllPeople(includeStats: true)),
        _deleteSample = deleteSample ?? deletePersonSpeechSample;
  final Future<List<Person>?> Function() _loadPeople;
  final Future<bool> Function(String, String) _renamePerson;
  final Future<bool> Function(String, int) _deleteSample;
  final Future<bool> Function(String) _deletePersonById;
  final Future<bool> Function(String, bool) _setPinned;
  List<Person> people = SharedPreferencesUtil().cachedPeople;
  Map<String, List<String>> samplesUrl = {};

  final AudioPlayer _audioPlayer = AudioPlayer();
  int? currentPlayingPersonIndex;
  int? currentPlayingIndex;
  bool isPlaying = false;

  /// True when the last load failed; the list then shows what was cached, or an error state.
  bool loadFailed = false;
  bool _listening = false;

  Future<void> initialize() {
    loading = true;
    notifyListeners();
    if (!_listening) {
      _listening = true;
      _setupAudioPlayerListeners();
    }
    return setPeople();
  }

  /// Pull-to-refresh: reloads without the first-load spinner.
  Future<void> refresh() => setPeople();

  void clearUserData() {
    people = [];
    selectedIds.clear();
    selecting = false;
    samplesUrl = {};
    currentPlayingPersonIndex = null;
    currentPlayingIndex = null;
    isPlaying = false;
    _audioPlayer.stop();
    notifyListeners();
  }

  Future<void> setPeople() async {
    final value = await _loadPeople();
    loading = false;
    loadFailed = value == null;
    if (value != null) {
      people = [
        ...value,
        ...people.where((person) => person.id.startsWith('optimistic-person:')),
      ];
      SharedPreferencesUtil().cachedPeople = value;
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
    SharedPreferencesUtil().cachedPeople =
        people.where((person) => !person.id.startsWith('optimistic-person:')).toList();

    loading = false;
    notifyListeners();
    return newPerson;
  }

  void addOptimisticPerson(Person person) {
    people.add(person);
    notifyListeners();
  }

  void removeOptimisticPerson(String id) {
    people.removeWhere((person) => person.id == id);
    notifyListeners();
  }

  Future<void> updatePersonProvider(Person person, String name) async {
    if (loading) return;
    loading = true;
    notifyListeners();

    final updated = await _renamePerson(person.id, name);
    final index = people.indexWhere((p) => p.id == person.id);
    if (updated && index != -1) {
      people[index] = person.copyWith(name: name, updatedAt: DateTime.now());
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

    try {
      if (await _deletePersonById(person.id)) return;
    } catch (e) {
      Logger.debug('Failed to delete person ${person.id}: $e');
    }
    if (!people.any((p) => p.id == person.id)) {
      people.add(person);
      people.sort((a, b) => a.name.compareTo(b.name));
      SharedPreferencesUtil().cachedPeople = people;
      notifyListeners();
    }
  }

  // ---- Pinning and clean-up ----

  /// Pins or unpins at once and rolls back when the server refuses. Returns true when stored.
  Future<bool> setPinned(String personId, bool pinned) async {
    final index = people.indexWhere((p) => p.id == personId);
    if (index == -1) return false;
    final before = people[index];
    if (before.pinned == pinned) return true;
    people[index] = before.copyWith(pinned: pinned, pinnedAt: () => pinned ? DateTime.now() : null);
    selectedIds.remove(personId);
    notifyListeners();
    final ok = await _setPinned(personId, pinned);
    final current = people.indexWhere((p) => p.id == personId);
    if (!ok && current != -1) {
      people[current] = before;
      notifyListeners();
    } else if (ok) {
      SharedPreferencesUtil().cachedPeople =
          people.where((person) => !person.id.startsWith('optimistic-person:')).toList();
    }
    return ok;
  }

  /// Unverified, unpinned people: what Clean Up offers to delete. Pinned people are never included.
  List<Person> get cleanUpCandidates =>
      people.where((p) => !p.pinned && p.confidence == 'unverified' && !p.id.startsWith('optimistic-person:')).toList();

  // ---- Multi-select ----

  final Set<String> selectedIds = {};
  bool selecting = false;

  void beginSelection([String? personId]) {
    selecting = true;
    selectedIds
      ..clear()
      ..addAll(personId == null || people.any((p) => p.id == personId && p.pinned) ? const [] : [personId]);
    notifyListeners();
  }

  /// Selects every listed person except pinned ones, which are deleted one at a time from their page.
  void selectAll(Iterable<String> personIds) {
    final pinned = {
      for (final p in people)
        if (p.pinned) p.id
    };
    selectedIds.addAll(personIds.where((id) => !pinned.contains(id)));
    notifyListeners();
  }

  void toggleSelected(String personId) {
    if (people.any((p) => p.id == personId && p.pinned)) return;
    if (!selectedIds.remove(personId)) selectedIds.add(personId);
    notifyListeners();
  }

  void endSelection() {
    selecting = false;
    selectedIds.clear();
    notifyListeners();
  }

  /// Deletes the selected people, one request each (a person's samples go with them). People whose
  /// request fails stay in the list and selected. Returns how many were deleted.
  Future<int> deleteSelected() => deletePeople(selectedIds.toList());

  Future<int> deletePeople(List<String> personIds, {bool allowPinned = false}) async {
    allowPinned = allowPinned && personIds.toSet().length == 1;
    personIds = personIds.toSet().where((id) => people.any((p) => p.id == id && (!p.pinned || allowPinned))).toList();
    final results = await Future.wait(personIds.map((id) async {
      try {
        return await _deletePersonById(id);
      } catch (e) {
        Logger.debug('Failed to delete person $id: $e');
        return false;
      }
    }));
    final deleted = <String>{
      for (final (i, ok) in results.indexed)
        if (ok) personIds[i],
    };
    people.removeWhere((person) => deleted.contains(person.id));
    selectedIds.removeAll(deleted);
    if (selectedIds.isEmpty) selecting = false;
    SharedPreferencesUtil().cachedPeople =
        people.where((person) => !person.id.startsWith('optimistic-person:')).toList();
    notifyListeners();
    return deleted.length;
  }

  @override
  void dispose() {
    _audioPlayer.dispose();
    super.dispose();
  }
}
